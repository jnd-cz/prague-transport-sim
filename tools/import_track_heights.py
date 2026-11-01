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
from shapely.geometry import Point
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
from track_heights import HeightGuard
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


def decide(rows, guard, structures, decks, tunnels, context):
    hints = shapely.intersects(structures, shapely.points([(r['x'], r['y']) for r in rows]))
    tunnel_hints = shapely.intersects(tunnels, shapely.points([(r['x'], r['y']) for r in rows]))
    for row, hint, tunnel in zip(rows, hints, tunnel_hints):
        surfaces = decks.candidates(row['x'], row['y'], row['id'], bool(hint), row['z'])
        row['decision'] = guard.choose(
            {'id': row['id'], 'z': row['z']},
            row['archive'],
            row['x'],
            row['y'],
            bool(hint),
            surfaces,
            bool(tunnel),
            context.classify(row['x'], row['y'], row['ux'], row['uy'], surfaces),
        )
    return rows


def stage(review):
    districts, paths = di_data()
    provenance, _, archived_paths = archive_data()
    current, archive = Segments(paths), Segments(archived_paths)
    structures, structure_ids, tunnels = structure_mask(separate_tunnels=True)
    decks = load_decks(ROOT)
    context = load_context(decks)
    area = unary_union([d['polygon'] for d in districts])
    print(f'Matching {len(paths)} DI paths for guarded height staging', flush=True)
    rows = observations(current, archive, area)
    conflicts = conflict_records(rows)
    guard = HeightGuard(review.get('evidence', []), review.get('alignment_reviews', []), conflicts,
                        review.get('span_reviews', []))
    decide(rows, guard, structures, decks, tunnels, context)
    lines, route_samples = [], []
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
                hint = structures.intersects(Point(hit['x'], hit['y']))
                surfaces = decks.candidates(hit['x'], hit['y'], hit['id'], hint, hit['z'])
                row['decision'] = guard.choose(
                    {'id': hit['id'], 'z': hit['z']},
                    match,
                    hit['x'],
                    hit['y'],
                    hint,
                    surfaces,
                    tunnels.intersects(Point(hit['x'], hit['y'])),
                    context.classify(hit['x'], hit['y'], tangent['ux'], tangent['uy'], surfaces),
                )
                row['di_id'], row['raw_di_z'], row['di_xy'] = hit['id'], hit['z'], [hit['x'],hit['y']]
            else:
                row['decision'] = {'status': 'review', 'review_flags': ['no_unambiguous_current_geometry']}
            selected.append(row)
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
