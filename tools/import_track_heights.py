# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stage guarded DI/archive height proposals for #20; never rewrites game geometry (#106).

    python -P -E tools/import_track_heights.py
    python -P -E tools/import_track_heights.py --evidence reviewed-heights.json --output reports/track-heights.json

Optional evidence file resolves flagged cases: {"evidence": [...], "alignment_reviews": [...]}.
Ordinary heights use DI, then archive, then surveyed deck plus truth fact; candidates/flags are retained.
See docs/decisions/2026-10-30-track-height-fallback.md for the contracts.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import shapely
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dtmp_tracks import (
    ROOT,
    Segments,
    archive_data,
    di_data,
    good_z,
    load_line,
    samples,
    structure_mask,
    surface_evidence,
    write_json,
)
from geo import Frame
from ipr_dtm import IprDtm
from track_heights import HeightGuard, TERRAIN_EXTEND
import track_bridges
from track_decks import load_decks
from track_context import load_context


def lengths(rows):
    counts, flags = Counter(), Counter()
    sources = Counter({'di':0, 'archive':0, 'deck':0})
    for row in rows:
        d = row['decision']
        counts[d['status'] + '_m'] += row['weight']
        if d['status'] == 'selected':
            sources[d['height_source']['dataset']] += row['weight']
        for flag in d['review_flags']:
            flags[flag] += row['weight']
    return {'lengths': {k: round(v, 3) for k, v in sorted(counts.items())},
            'selected_by_source_m':{k:round(v,3) for k,v in sources.items()},
            'flag_lengths': {k: round(v, 3) for k, v in sorted(flags.items())}}


def conflict_records(observations):
    """Hold out every known large disagreement, including short records below the research's 10 m test."""
    conflicts = set()
    for obs in observations:
        match = obs['archive']
        if not good_z(obs['z']):
            continue
        near = match['candidates']
        for c in near:
            if c['distance'] <= near[0]['distance'] + .25 and good_z(c['z']) and abs(c['z'] - obs['z']) > 1:
                conflicts.add(str(c['id']))
    return conflicts


def observations(current, archive, area):
    rows = list(samples(current, area))
    for obs in rows:
        obs['archive'] = archive.match(obs['x'], obs['y'], obs['ux'], obs['uy'], details=True)
    return rows


class Terrain:
    """The 2023 lidar terrain at our frame's points: the check for archive heights nothing else confirms."""
    def __init__(self):
        self.dtm, self.frame = IprDtm(), Frame()

    def __call__(self, xs, ys):
        return self.dtm.sample([x + self.frame.E0 for x in xs], [y + self.frame.N0 for y in ys]).tolist()


def extend_holds(rows, guard, reach=6):
    """A terrain hold spreads along the track to neighbours (within reach metres, rows in track order) whose
    archive is still more than TERRAIN_EXTEND off the terrain, until none is left (#190)."""
    flag = 'archive_terrain_height_disagreement'
    changed = True
    while changed:
        changed = False
        for i, row in enumerate(rows):
            if 'choice' not in row or flag in row['decision'].get('review_flags', []):
                continue
            if not any(0 <= j < len(rows) and flag in rows[j]['decision'].get('review_flags', [])
                       and abs(rows[j]['x'] - row['x']) + abs(rows[j]['y'] - row['y']) <= reach for j in (i - 1, i + 1)):
                continue
            decision = guard.choose(*row['choice'], terrain_limit=TERRAIN_EXTEND)
            if flag in decision['review_flags']:
                row['decision'], changed = decision, True
    return rows


def truth_structures(root, structures, ids, width=6):
    """The user's structures that no source maps (data/truth.json trackHeights.structures, #190), added to the
    OSM structure mask as a corridor from 'from' to 'to'."""
    path = root / 'data/truth.json'
    truth = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    facts = truth.get('trackHeights', {}).get('structures', [])
    if not facts:
        return structures, ids
    frame = Frame()
    corridors = []
    for f in facts:
        x, y = frame.xy([f['from'][0], f['to'][0]], [f['from'][1], f['to'][1]])
        corridors.append(shapely.LineString(list(zip(x, y))).buffer(width))
    return unary_union([structures, *corridors]), ids + ['truth:' + f['id'] for f in facts]


def bridge_structures(structures, ids, paths, current, archive, terrain):
    """Track on a Mosty 3D bridge, decided from the heights where it enters and leaves (tools/track_bridges.py, #192),
    added to the OSM structure mask."""
    geom, found, pieces = track_bridges.mask(track_bridges.decide(paths, current, archive, terrain))
    return (unary_union([structures, geom]) if found else structures), ids + found, pieces


POOL = 20000  # samples: fewer are decided in this process (a worker takes a few seconds to start with the decks)
CHUNK = 5000  # samples a worker decides at a time
_W = {}


def _worker(decks, context, guard):
    _W.update(decks=decks, context=context, guard=guard)


def _decide(todo, decks=None, context=None, guard=None):
    """decide's loop over (x, y, DI id, DI z, ux, uy, archive match, structure hint, tunnel hint, terrain) samples: each
    one's (surfaces, construction, decision). Each sample reads only its own place, so the workers share them out."""
    if decks is None:
        decks, context, guard = _W['decks'], _W['context'], _W['guard']
    out = []
    for x, y, i, z, ux, uy, match, hint, tunnel, ground in todo:
        surfaces = decks.candidates(x, y, i, hint, z)
        construction = context.classify(x, y, ux, uy, surfaces)
        out.append((surfaces, construction, guard.choose({'id': i, 'z': z}, match, x, y, hint, surfaces, tunnel,
                                                         construction, ground)))
    return out


def _decide_all(todo, decks, context, guard, pool=None):
    """_decide over todo, in the pool's workers (in order) when there is one."""
    if pool is None:
        return _decide(todo, decks, context, guard)
    return [g for part in pool.map(_decide, [todo[k:k + CHUNK] for k in range(0, len(todo), CHUNK)]) for g in part]


def _pool(decks, context, guard):
    """Worker processes with the decks, OSM's tracks and the guard (#516: one process decided the 285 000 DI samples and
    the lines' 60 000 in ~70 s of the heights' 97 s staging)."""
    from concurrent.futures import ProcessPoolExecutor
    import sysinfo
    return ProcessPoolExecutor(sysinfo.workers(1.0, most=12), initializer=_worker, initargs=(decks, context, guard))


def decide(rows, guard, structures, decks, tunnels, context, terrain, pool=None):
    hints = shapely.intersects(structures, shapely.points([(r['x'], r['y']) for r in rows]))
    tunnel_hints = shapely.intersects(tunnels, shapely.points([(r['x'], r['y']) for r in rows]))
    ground = terrain([r['x'] for r in rows], [r['y'] for r in rows])
    todo = [(r['x'], r['y'], r['id'], r['z'], r['ux'], r['uy'], r['archive'], bool(h), bool(t), z)
            for r, h, t, z in zip(rows, hints, tunnel_hints, ground)]
    for row, t, (surfaces, construction, decision) in zip(rows, todo, _decide_all(todo, decks, context, guard, pool)):
        row['choice'] = ({'id': row['id'], 'z': row['z']}, row['archive'], row['x'], row['y'], t[7], surfaces, t[8],
                         construction, t[9])
        row['decision'] = decision
    return extend_holds(rows, guard)


def stage(review):
    districts, paths = di_data()
    provenance, _, archived_paths = archive_data()
    current, archive = Segments(paths), Segments(archived_paths)
    structures, structure_ids, tunnels = structure_mask(separate_tunnels=True)
    structures, structure_ids = truth_structures(ROOT, structures, structure_ids)
    terrain = Terrain()
    structures, structure_ids, bridge_pieces = bridge_structures(structures, structure_ids, paths, current, archive,
                                                                 terrain)
    decks = load_decks(ROOT)
    context = load_context(decks)
    area = unary_union([d['polygon'] for d in districts])
    print(f'Matching {len(paths)} DI paths for guarded height staging', flush=True)
    rows = observations(current, archive, area)
    conflicts = conflict_records(rows)
    guard = HeightGuard(review.get('evidence', []), review.get('alignment_reviews', []), conflicts,
                        review.get('span_reviews', []))
    pool = _pool(decks, context, guard) if len(rows) >= POOL else None
    try:
        decide(rows, guard, structures, decks, tunnels, context, terrain, pool)
        # the lines' route samples: each matched to DI here, then decided as DI's samples are (in the workers)
        lines, route_samples, along, hits = [], [], [], []
        for line in (9, 17, 22, 23, 37):
            data = load_line(line)
            route = Segments(
                [
                    {'id': key, 'coords': [(p[0], p[1], None) for p in data[key]], 'attrs': {}}
                    for key in ('path', 'pathBack')
                    if data.get(key)
                ]
            )
            selected = []
            positions = Counter()
            for row in samples(route, None):
                row['s'] = positions[row['id']] + row['weight']/2
                positions[row['id']] += row['weight']
                hit = current.match(row['x'], row['y'], row['ux'], row['uy'], radius=2, details=True)
                if hit['status'] in ('numeric', 'missing_z'):
                    tangent = hit['candidates'][0]
                    match = archive.match(hit['x'], hit['y'], tangent['ux'], tangent['uy'], details=True)
                    hits.append((row, hit, tangent, match))
                    row['di_id'], row['raw_di_z'], row['di_xy'] = hit['id'], hit['z'], [hit['x'],hit['y']]
                else:
                    row['decision'] = {'status': 'review', 'review_flags': ['no_unambiguous_current_geometry']}
                selected.append(row)
            along.append((line, selected))
        at = shapely.points([(h['x'], h['y']) for _, h, _, _ in hits] or [(0.0, 0.0)])[:len(hits)]
        on = shapely.intersects(structures, at)
        under = shapely.intersects(tunnels, at)
        ground = terrain([h['x'] for _, h, _, _ in hits], [h['y'] for _, h, _, _ in hits]) if hits else []
        todo = [(h['x'], h['y'], h['id'], h['z'], t['ux'], t['uy'], m, bool(a), bool(b), g)
                for (_, h, t, m), a, b, g in zip(hits, on, under, ground)]
        for (row, hit, _, match), t, (surfaces, construction, decision) in zip(
                hits, todo, _decide_all(todo, decks, context, guard, pool)):
            row['choice'] = ({'id': hit['id'], 'z': hit['z']}, match, hit['x'], hit['y'], t[7], surfaces, t[8],
                             construction, t[9])
            row['decision'] = decision
    finally:
        if pool is not None:
            pool.shutdown()
    for line, selected in along:
        for row in extend_holds(selected, guard):
            route_samples.append({'line':line, 'direction':row['id'], 's':row['s'],
                                  'xy':[row['x'],row['y']], 'tangent':[row['ux'],row['uy']],
                                  'weight_m':row['weight'], 'di_id':row.get('di_id'),
                                  'di_xy':row.get('di_xy'),
                                  'raw_di_z':row.get('raw_di_z'), **row['decision']})
        lines.append({'line': line, **lengths(selected)})
        print(f'line {line}: {json.dumps(lines[-1])}', flush=True)
    # Geometry and raw source Z are separate from decisions; no archived alignment is added.
    geometry = [
        {
            'dataset': 'di',
            'id': p['id'],
            'xy': [v[:2] for v in p['coords']],
            'raw_z': [v[2] for v in p['coords']],
            'attributes': p['attrs'],
            'sources': p['sources'],
            'alignment_review': guard.reviews.get(('di', str(p['id'])), {'status': 'unreviewed'}),
        }
        for p in paths
    ]
    archive_sources = {
        str(p['id']): {
            'dataset': 'archive',
            'attributes': p['attrs'],
            'sources': p['sources'],
            'alignment_review': guard.reviews.get(('archive', str(p['id'])), {'status': 'unreviewed'}),
        }
        for p in archived_paths
    }
    di_sources = {
        str(p['id']): {
            'record': str(p['id']),
            'date': sorted({s['state'] for s in p['sources']}),
            'date_kind': 'export_state',
        }
        for p in paths
    }
    archived_sources = {
        str(p['id']): {
            'record': str(p['id']),
            'date': p['attrs'].get('DAT_ZMENA') or p['attrs'].get('DAT_VZNIK'),
            'date_kind': 'record_change_or_creation',
        }
        for p in archived_paths
    }
    staged = []
    for r in rows:
        d = r['decision']
        source = d['height_source']
        if source and source['dataset'] in ('di', 'archive'):
            catalog = di_sources if source['dataset'] == 'di' else archived_sources
            source.update(catalog[str(source['id'])])
        staged.append(
            {'di_id': r['id'], 'xy': [r['x'], r['y']], 'tangent': [r['ux'], r['uy']],
             'weight_m': r['weight'], 'raw_di_z': r['z'], **d}
        )
    examples = []
    for r in rows:
        m = r['archive']
        if good_z(r['z']) and m['status'] == 'numeric' and abs(m['z'] - r['z']) > 1:
            examples.append(
                {
                    'di_id': r['id'],
                    'archive_objectid': m['id'],
                    'xy': [r['x'], r['y']],
                    'di_z': r['z'],
                    'archive_z': m['z'],
                    'delta_m': m['z'] - r['z'],
                }
            )
    examples.sort(key=lambda e: -abs(e['delta_m']))
    unique = {}
    for e in examples:
        unique.setdefault((e['di_id'], e['archive_objectid']), e)
    examples = list(unique.values())[:20]
    surface_evidence(examples)
    return {
        'schema': 1,
        'snapshot': (ROOT / 'snapshots/CURRENT').read_text().strip(),
        'frame': {'crs': 'EPSG:5514', 'origin': list(Frame().to_jtsk(0, 0)), 'height_datum': 'Bpv'},
        'scope': 'height proposals at DI midpoint samples <=5m; topology and game integration are #20',
        'structure_hint_osm_ways': structure_ids,
        'mosty3d_structures': bridge_pieces,
        'known_conflicting_archive_ids': sorted(conflicts),
        'evidence': review,
        'rail_above_deck_facts': decks.facts,
        'archive_acquired': provenance['acquired'],
        'geometry': geometry,
        'route_samples': route_samples,
        'archive_sources': archive_sources,
        'height_samples': staged,
        'overall': lengths(rows),
        'lines': lines,
        'large_disagreement_diagnostics': examples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/track-heights.json')
    args = parser.parse_args()
    review = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else {}
    HeightGuard(review.get('evidence', []), review.get('alignment_reviews', []),
                span_reviews=review.get('span_reviews', []))  # fail before the expensive scan
    report = stage(review)
    write_json(args.output, report)
    print(json.dumps(report['overall'], indent=2))
    print(f'Report: {args.output}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
