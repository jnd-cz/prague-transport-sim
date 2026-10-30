"""Stage guarded DI/archive height proposals for #20; never rewrites game geometry (#106).

    python -P -E tools/import_track_heights.py
    python -P -E tools/import_track_heights.py --evidence reviewed-heights.json --output reports/track-heights.json

Optional evidence file: {"evidence": [...], "alignment_reviews": [...]}; see track_heights.py and
docs/decisions/2026-10-30-track-height-fallback.md. Default output retains candidates for review.
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
from dtmp_tracks import (ROOT, Segments, archive_data, di_data, good_z, load_line, quantile,
                         samples, structure_mask, surface_evidence, write_json)
from geo import Frame
from track_heights import HeightGuard


def lengths(rows):
    counts, flags = Counter(), Counter()
    for row in rows:
        d = row['decision']
        counts[d['status'] + '_m'] += row['weight']
        for flag in d['review_flags']:
            flags[flag] += row['weight']
    return {'lengths': {k: round(v, 3) for k, v in sorted(counts.items())},
            'flag_lengths': {k: round(v, 3) for k, v in sorted(flags.items())}}


def conflict_records(observations):
    """Hold out every known large disagreement, including short records below the research's 10 m test."""
    pairs, conflicts = {}, set()
    for obs in observations:
        match = obs['archive']
        if not good_z(obs['z']):
            continue
        near = match['candidates']
        for c in near:
            if c['distance'] <= near[0]['distance'] + .25 and good_z(c['z']) and abs(c['z'] - obs['z']) > 1:
                conflicts.add(str(c['id']))
        if match['status'] == 'numeric':
            pairs.setdefault(str(match['id']), []).append((abs(match['z'] - obs['z']), obs['weight']))
    for identity, values in pairs.items():
        v, w = zip(*values)
        if sum(w) >= 10 and quantile(v, w, .9) > .3:
            conflicts.add(identity)
    return conflicts


def observations(current, archive, area):
    rows = list(samples(current, area))
    for obs in rows:
        obs['archive'] = archive.match(obs['x'], obs['y'], obs['ux'], obs['uy'], details=True)
    return rows


def decide(rows, guard, structures):
    hints = shapely.intersects(structures, shapely.points([(r['x'], r['y']) for r in rows]))
    for row, hint in zip(rows, hints):
        row['decision'] = guard.choose({'id': row['id'], 'z': row['z']}, row['archive'],
                                      row['x'], row['y'], bool(hint))
    return rows


def stage(review):
    districts, paths = di_data()
    provenance, _, archived_paths = archive_data()
    current, archive = Segments(paths), Segments(archived_paths)
    structures, structure_ids = structure_mask()
    area = unary_union([d['polygon'] for d in districts])
    rows = observations(current, archive, area)
    conflicts = conflict_records(rows)
    guard = HeightGuard(review.get('evidence', []), review.get('alignment_reviews', []), conflicts)
    decide(rows, guard, structures)
    lines = []
    for line in (9, 17, 22, 23, 37):
        data = load_line(line)
        route = Segments([{'id': key, 'coords': [(p[0], p[1], None) for p in data[key]], 'attrs': {}}
                          for key in ('path', 'pathBack') if data.get(key)])
        selected = []
        for row in samples(route, None):
            hit = current.match(row['x'], row['y'], row['ux'], row['uy'], radius=2)
            if hit['status'] in ('numeric', 'missing_z'):
                match = archive.match(hit['x'], hit['y'], row['ux'], row['uy'], details=True)
                row['decision'] = guard.choose({'id': hit['id'], 'z': hit['z']}, match,
                    hit['x'], hit['y'], structures.intersects(Point(hit['x'], hit['y'])))
            else:
                row['decision'] = {'status': 'review', 'review_flags': ['no_unambiguous_current_geometry']}
            selected.append(row)
        lines.append({'line': line, **lengths(selected)})
        print(f'line {line}: {json.dumps(lines[-1])}', flush=True)
    # Geometry and raw source Z are separate from decisions; no archived alignment is added.
    geometry = [{'dataset': 'di', 'id': p['id'], 'xy': [v[:2] for v in p['coords']],
                 'raw_z': [v[2] for v in p['coords']], 'attributes': p['attrs'], 'sources': p['sources'],
                 'alignment_review': guard.reviews.get(('di', str(p['id'])), {'status': 'unreviewed'})}
                for p in paths]
    archive_sources = {str(p['id']): {'dataset': 'archive', 'attributes': p['attrs'], 'sources': p['sources'],
                                    'alignment_review': guard.reviews.get(('archive', str(p['id'])), {'status': 'unreviewed'})}
                       for p in archived_paths}
    staged = [{'di_id': r['id'], 'xy': [r['x'], r['y']], 'weight_m': r['weight'],
               'raw_di_z': r['z'], **r['decision']} for r in rows]
    examples = []
    for r in rows:
        m = r['archive']
        if good_z(r['z']) and m['status'] == 'numeric' and abs(m['z'] - r['z']) > 1:
            examples.append({'di_id': r['id'], 'archive_objectid': m['id'], 'xy': [r['x'], r['y']],
                             'di_z': r['z'], 'archive_z': m['z'], 'delta_m': m['z'] - r['z']})
    examples.sort(key=lambda e: -abs(e['delta_m']))
    unique = {}
    for e in examples:
        unique.setdefault((e['di_id'], e['archive_objectid']), e)
    examples = list(unique.values())[:20]
    surface_evidence(examples)  # diagnostic vertices; never fed to HeightGuard as reviewed rail evidence
    return {'schema': 1, 'snapshot': (ROOT / 'snapshots/CURRENT').read_text().strip(),
            'frame': {'crs': 'EPSG:5514', 'origin': list(Frame().to_jtsk(0, 0)), 'height_datum': 'Bpv'},
            'scope': 'height proposals at DI midpoint samples <=5m; topology and game integration are #20',
            'structure_hint_osm_ways': structure_ids, 'known_conflicting_archive_ids': sorted(conflicts),
            'evidence': review, 'archive_acquired': provenance['acquired'],
            'geometry': geometry, 'archive_sources': archive_sources, 'height_samples': staged,
            'overall': lengths(rows), 'lines': lines, 'large_disagreement_diagnostics': examples}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/track-heights.json')
    args = parser.parse_args()
    review = json.loads(args.evidence.read_text(encoding='utf-8')) if args.evidence else {}
    HeightGuard(review.get('evidence', []), review.get('alignment_reviews', []))  # fail before the expensive scan
    report = stage(review)
    write_json(args.output, report)
    print(json.dumps(report['overall'], indent=2))
    print(f'Report: {args.output}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
