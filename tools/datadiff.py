"""Compare working data with published cache blobs, per class and place (#158).

    python -I tools/datadiff.py --line 17 dtm
    python -I tools/datadiff.py --line 17 zps --at 100,-500 --radius 3
    python -I tools/datadiff.py --line 17 dtm --ref origin/main

Default reference: this checkout's data/MANIFEST.json. --ref selects a directory's or git revision's
published manifest; it never restores or changes working data. XY edits are additions/removals;
height histograms compare only matching XY geometry, class and level. Closed-ring duplicates count once.
"""
import argparse
from collections import Counter, defaultdict
import json
import hashlib
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
from data_reference import ROOT, digest, manifest, published

BINS = (0, .01, .05, .1, .3, 1, 3, 10, math.inf)
LABELS = ['0'] + [f'({a:g},{b:g}]' for a, b in zip(BINS, BINS[1:])]


def closed(points):
    return points[:-1] if len(points) > 1 and points[0][:2] == points[-1][:2] else points


def canonical(points, ring=False):
    xy = tuple(tuple(p[:2]) for p in (closed(points) if ring else points))
    if not xy:
        return xy
    if not ring:
        return min(xy, xy[::-1])
    # Rotate only at the minimum vertex; avoid quadratic work on large outlines.
    first = min(xy)
    return min(seq[i:] + seq[:i] for seq in (xy, xy[::-1]) for i, p in enumerate(seq) if p == first)


def features(data, kind):
    if kind == 'dtm':
        for i, a in enumerate(data.get('areas', [])):
            rings = [a['r'], *a.get('h', [])]
            shape = (canonical(rings[0], True), tuple(sorted(canonical(r, True) for r in rings[1:])))
            points = []
            for r in rings:
                role = hashlib.sha256(repr(canonical(r, True)).encode()).hexdigest()
                points.extend((role, p) for p in closed(r))
            yield {'class': a['c'], 'level': a.get('l', 0), 'key': (a['c'], a.get('l', 0), shape),
                   'points': points, 'id': f'areas/{i}'}
    elif kind == 'zps':
        for i, row in enumerate(data.get('lines', [])):
            pts = [row[j:j + 3] for j in range(3, len(row), 3)]
            cls = data['kinds'][row[0]]
            yield {'class': cls, 'level': row[1], 'key': (cls, row[1], row[2], canonical(pts)),
                   'points': [((), p) for p in pts], 'id': f'lines/{i}'}
    else:
        # Route order matters: reversing a route changes its meaning. Other line fields are diffed too.
        for key in ('path', 'pathBack'):
            if data.get(key):
                yield {'class': key, 'level': 0, 'key': (key, tuple(tuple(p[:2]) for p in data[key])),
                       'points': [((), p) for p in data[key]], 'id': key}


def heights(feature):
    values = defaultdict(list)
    for role, p in feature['points']:
        z = p[2] if len(p) > 2 else None
        if z is not None and (not isinstance(z, (int, float)) or not math.isfinite(z)):
            z = None
        values[(role, *p[:2])].append(z)
    return {k: sorted(v, key=lambda z: (z is not None, z or 0)) for k, v in values.items()}


def compare(before, after, kind, limit=20):
    groups = []
    for data in (before, after):
        g = defaultdict(list)
        for f in features(data, kind):
            g[f['key']].append(f)
        groups.append(g)
    classes, places = defaultdict(Counter), []
    hist = Counter({label: 0 for label in LABELS})
    for key in sorted(set(groups[0]) | set(groups[1])):
        old, new = groups[0].get(key, []), groups[1].get(key, [])
        cls = key[0]
        stats = classes[cls]
        stats.update(before=len(old), after=len(new), removed=max(0, len(old) - len(new)),
                     added=max(0, len(new) - len(old)))
        # Duplicate geometries can be emitted by several district packages. Pair by their height
        # signatures, so reordering a duplicate list does not invent a height edit.
        order = lambda f: repr(heights(f))
        for a, b in zip(sorted(old, key=order), sorted(new, key=order)):
            za, zb = heights(a), heights(b)
            changed = False
            for vertex in sorted(za):
                for z0, z1 in zip(za[vertex], zb[vertex]):
                    stats['matched_vertices'] += 1
                    if z0 is None or z1 is None:
                        if z0 != z1:
                            stats['height_gained' if z0 is None else 'height_lost'] += 1
                            changed = True
                        continue
                    dz = abs(z1 - z0)
                    hist[next(label for edge, label in zip(BINS, LABELS) if dz <= edge)] += 1
                    if dz <= 1e-9:
                        continue
                    changed = True
                    stats['changed_vertices'] += 1
                    places.append({'class': cls, 'level': b['level'], 'x': vertex[-2], 'y': vertex[-1],
                                   'before_z': z0, 'after_z': z1, 'dz': round(z1 - z0, 6),
                                   'before_record': a['id'], 'after_record': b['id']})
            stats['changed' if changed else 'unchanged'] += 1
    places.sort(key=lambda p: (-abs(p['dz']), p['class'], p['x'], p['y']))
    result = {'classes': {k: dict(v) for k, v in sorted(classes.items())},
              'abs_dz_histogram': dict(hist), 'largest_places': places[:limit]}
    if kind == 'line':
        result['changed_fields'] = [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
        result['field_counts'] = {k: {'before': len(before.get(k, [])), 'after': len(after.get(k, [])),
                                     'changed_positions': sum(a != b for a, b in zip(before.get(k, []), after.get(k, [])))}
                                  for k in sorted(set(before) | set(after))
                                  if isinstance(before.get(k, []), list) and isinstance(after.get(k, []), list)}
    return result


def segment_distance(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = dx * dx + dy * dy
    t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / d)) if d else 0
    return math.hypot(x - a[0] - t * dx, y - a[1] - t * dy)


def ring_inside(x, y, ring):
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def near_point(root, line, xy, radius):
    x, y = xy
    result = {'xy': [x, y], 'radius_m': radius, 'areas': [], 'source_lines': [], 'missing_files': []}
    for kind in ('dtm', 'zps'):
        path = root / 'data' / f'line{line}.{kind}.json'
        if not path.exists():
            result['missing_files'].append(path.name)
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        if kind == 'dtm':
            for i, area in enumerate(data['areas']):
                rings = [area['r'], *area.get('h', [])]
                inside = ring_inside(x, y, rings[0]) and not any(ring_inside(x, y, r) for r in rings[1:])
                d = 0 if inside else min(segment_distance(x, y, a, b) for r in rings
                                         for a, b in zip(r, r[1:] + r[:1]))
                if d <= radius:
                    result['areas'].append({'record': f'areas/{i}', 'distance_m': round(d, 3), **area})
        else:
            for i, row in enumerate(data['lines']):
                pts = [row[j:j + 3] for j in range(3, len(row), 3)]
                d = min((segment_distance(x, y, a, b) for a, b in zip(pts, pts[1:])), default=math.inf)
                if d <= radius:
                    result['source_lines'].append({'record': f'lines/{i}', 'kind': data['kinds'][row[0]],
                                                   'level': row[1], 'height_class': row[2],
                                                   'distance_m': round(d, 3), 'points': pts})
    return result


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--line', required=True, type=int)
    ap.add_argument('kind', choices=('dtm', 'zps', 'line'), nargs='?', default='dtm')
    ap.add_argument('--ref', help='published manifest from a directory or git revision')
    ap.add_argument('--cache', help='machine cache (default TRAMDATA_CACHE), read only')
    ap.add_argument('--at', help='city-frame X,Y; list nearby working survey areas and source lines')
    ap.add_argument('--radius', type=float, default=2)
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--output', type=Path)
    a = ap.parse_args(argv)
    if a.radius < 0 or not math.isfinite(a.radius) or a.limit < 0:
        ap.error('radius must be finite and nonnegative; limit must be nonnegative')
    name = f'line{a.line}' + ('' if a.kind == 'line' else '.' + a.kind) + '.json'
    current = root / 'data' / name
    try:
        man = manifest(root, a.ref)
        reference = published(root, name, man, a.cache, a.ref if a.ref and Path(a.ref).is_dir() else None)
        before = json.loads(reference.read_text(encoding='utf-8'))
        after = json.loads(current.read_text(encoding='utf-8'))
        if before.get('frame') != after.get('frame'):
            raise ValueError('coordinate frames differ; heights cannot be compared by XY')
        line_name = f'line{a.line}.json'
        if a.kind != 'line' and line_name in man['files'] and (root / 'data' / line_name).exists():
            old_line = json.loads(published(root, line_name, man, a.cache,
                                           a.ref if a.ref and Path(a.ref).is_dir() else None).read_text(encoding='utf-8'))
            new_line = json.loads((root / 'data' / line_name).read_text(encoding='utf-8'))
            if old_line.get('frame') != new_line.get('frame'):
                raise ValueError('line coordinate frames differ; survey XY cannot be compared')
        report = {'line': a.line, 'kind': a.kind, 'reference': a.ref or 'data/MANIFEST.json',
                  'reference_sha256': digest(reference), 'working_sha256': digest(current),
                  **compare(before, after, a.kind, a.limit)}
        if a.at:
            xy = [float(v) for v in a.at.split(',')]
            if len(xy) != 2 or not all(math.isfinite(v) for v in xy):
                raise ValueError('--at needs finite X,Y in city metres')
            report['at'] = near_point(root, a.line, xy, a.radius)
        output = a.output or root / 'reports/diffs' / f'line{a.line}-{a.kind}.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        with replacing(output, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        display = dict(report)
        if 'at' in display:
            display['at'] = {**report['at'],
                             'areas': [{k: v for k, v in r.items() if k not in ('r', 'h')} for r in report['at']['areas']],
                             'source_lines': [{k: v for k, v in r.items() if k != 'points'} for r in report['at']['source_lines']]}
        print(json.dumps(display, ensure_ascii=False, indent=2))
        print(f'Report: {output}')
        return report
    except (OSError, ValueError, KeyError) as e:
        ap.exit(1, f'datadiff: {e}\n')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
