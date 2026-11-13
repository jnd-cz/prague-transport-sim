# SPDX-License-Identifier: AGPL-3.0-or-later
"""The places where the rail as built steps, for the user's review (#344): reports/review/track-steps.json.

    python -P -E tools/track_steps.py [--checkpoint W1]

A place is where one of these holds, and places within REACH m of each other are one card:
- a coupling step (`coupling_steps`): two rigid cars on their bogies, each carrying its coupler head along its own pitch,
  would meet that far apart in height; over STEP m is a kink in the profile, not a wave;
- numeric DI jumps (`di_jumps`): a record's segment of at least JUMP_LENGTH m climbing over JUMP_GRADE and JUMP_RISE m,
  steeper than any track (the rule of #202's comment of 2026-11-06), where the rail as built still steps near it;
- with --checkpoint, the lint's places of that checkpoint's run (`trackLevels`, `railSupport`, `verticalCurves`).
A place the user answered (`stepAnswers`, or an area where the tracks follow the ground: `radiusAnswers` with `area`;
within ANSWERED m) is left out; one that still steps is printed.

Each card holds the heights of every line and direction through the place: numeric DI, the archive's records, the
survey's surfaces, the 2023 terrain and the game's profile (src/trackHeightProfile.js draws them). The answers are read
from data/truth.json `trackHeights.stepAnswers` by tools/import_track_heights.py once the place is decided.
"""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
LINES = ('17', '9', '22', '23', '37')
OPTIONS = ['archive profile ok', 'DI is right', 'follows survey surface', 'unsure']
STEP = 0.10          # m: a coupling step this large is listed
JUMP_LENGTH, JUMP_GRADE, JUMP_RISE = 2.0, 0.12, 0.5  # m, grade, m: a DI segment steeper than any track (MAX_GRADE 9 %)
REACH = 60.0         # m: findings this near each other are one card
AROUND = 70.0        # m: the heights shown either side of the place
CAR_BOGIE, CAR_PITCH = 3.2, 15.04  # m: a car's centre to its bogie pivots, between coupled cars' centres (src/tram.js)
ROUTE_NEAR = 8.0     # m: a DI jump this near a line's route is on it
ANSWERED = 15.0      # m: a place this near one the user answered (data/truth.json stepAnswers) is that place


def interp(xs, ys, x):
    """ys at x, linear between the even samples xs[0], xs[0] + h, ..."""
    h = xs[1] - xs[0]
    k = (x - xs[0]) / h
    i = min(len(ys) - 2, max(0, int(k)))
    return ys[i] + (ys[i + 1] - ys[i]) * (k - i)


def coupling_steps(z, step):
    """Per position of the coupling along a run of heights every `step` m: the height between the two heads, each
    carried on its own rigid car, as (s, metres). On a constant grade or a constant curve it is 0: only a change of
    the curvature between the cars makes one."""
    n = len(z)
    xs = [i * step for i in range(n)]
    half = CAR_PITCH / 2
    out = []
    for i in range(n):
        s = xs[i]
        if s - half - CAR_BOGIE < 0 or s + half + CAR_BOGIE > xs[-1]:
            continue
        a0, a1 = interp(xs, z, s + half - CAR_BOGIE), interp(xs, z, s + half + CAR_BOGIE)
        b0, b1 = interp(xs, z, s - half - CAR_BOGIE), interp(xs, z, s - half + CAR_BOGIE)
        pa, pb = (a1 - a0) / (2 * CAR_BOGIE), (b1 - b0) / (2 * CAR_BOGIE)
        out.append((s, ((a0 + a1) / 2 - half * pa) - ((b0 + b1) / 2 + half * pb)))
    return out


def runs_of(z):
    """The runs of a heights list without a null, as (first index, last index + 1)."""
    out, a = [], None
    for i, v in enumerate(z):
        if v is None and a is not None:
            out.append((a, i))
            a = None
        elif v is not None and a is None:
            a = i
    if a is not None:
        out.append((a, len(z)))
    return out


def at_s(path, s):
    """The point at distance s along a polyline."""
    left = s
    for a, b in zip(path, path[1:]):
        d = math.dist(a[:2], b[:2])
        if left <= d and d > 0:
            t = left / d
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        left -= d
    return tuple(path[-1][:2])


def line_steps(line, data, limit=STEP):
    """The coupling steps over `limit` of a line's two directions, the largest of each stretch."""
    out = []
    for key in ('path', 'pathBack'):
        z, h = data['heights'].get(key) or [], data['heights']['step']
        for a, b in runs_of(z):
            if (b - a) * h < 3 * CAR_PITCH:
                continue
            steps = sorted(coupling_steps(z[a:b], h), key=lambda v: -abs(v[1]))
            taken = []
            for s, d in steps:
                if abs(d) < limit:
                    break
                if all(abs(s - t) > REACH for t in taken):
                    taken.append(s)
                    x, y = at_s(data[key], s + a * h)
                    out.append({'x': x, 'y': y, 'cm': abs(d) * 100, 'what': f'{abs(d) * 100:.0f} cm coupling step (line {line}, {key}, s {s + a * h:.0f})'})
    return out


def di_jumps(geometry):
    """The numeric DI segments steeper than any track (#202), as places."""
    out = []
    for g in geometry:
        if g.get('dataset') != 'di':
            continue
        xy, z = g['xy'], g['raw_z']
        for i in range(len(xy) - 1):
            if not all(isinstance(v, (int, float)) and v > 100 for v in (z[i], z[i + 1])):
                continue
            length = math.dist(xy[i][:2], xy[i + 1][:2])
            rise = abs(z[i + 1] - z[i])
            if length >= JUMP_LENGTH and rise > JUMP_RISE and rise / length > JUMP_GRADE:
                out.append({'x': (xy[i][0] + xy[i + 1][0]) / 2, 'y': (xy[i][1] + xy[i + 1][1]) / 2, 'cm': rise * 100,
                            'what': f'DI record {g["id"]} climbs {rise:.2f} m over {length:.1f} m ({rise / length * 100:.0f} %)'})
    return out


def merged(places):
    """One group per place: those within REACH m of the largest finding."""
    groups = []
    for p in sorted(places, key=lambda q: -q['cm']):
        for g in groups:
            if math.dist((g[0]['x'], g[0]['y']), (p['x'], p['y'])) <= REACH:
                g.append(p)
                break
        else:
            groups.append([p])
    return groups


def lint_places(name):
    """The checkpoint's lint places of the height checks (#344), as places."""
    import baseline_store
    _, stored = baseline_store.fetch_checkpoint(name)
    out = []
    for line in LINES:
        for check in ('trackLevels', 'railSupport', 'verticalCurves'):
            for row in (stored or {}).get(f'line{line}-lint', {}).get(check, []):
                out.append({'line': line, 'check': check, 'x': row[0], 'y': row[1], 's': row[2]})
    return out


def card(group, samples, lines_data, frame, terrain):
    """One finding: what is flagged here, and each line's and direction's heights around it."""
    from shapely.geometry import LineString, Point
    head = group[0]
    lat, lon = (float(v) for v in frame.ll(head['x'], head['y']))
    ident = f'step-{lat:.4f}-{lon:.4f}'
    spans, near, step, apart = [], [], 0.0, 0.0
    for line, data in lines_data.items():
        for key in ('path', 'pathBack'):
            route = LineString([p[:2] for p in data[key]])
            pt = Point(head['x'], head['y'])
            if route.distance(pt) > ROUTE_NEAR:
                continue
            s = route.project(pt)
            rows = [r for r in samples.get((int(line), key), ()) if abs(r['s'] - s) <= AROUND]
            if len(rows) < 3:
                continue
            e, n = frame.to_jtsk([r['xy'][0] for r in rows], [r['xy'][1] for r in rows])
            ground = [float(v) if math.isfinite(v) and 100 < v < 500 else None for v in terrain.sample(e, n)]
            profile = []
            for r, g in zip(rows, ground):
                archived = [{'id': c['id'], 'z': c.get('z'), 'excluded': c.get('excluded')}
                            for c in r.get('candidates', []) if c['dataset'] == 'archive']
                surveyed = [{'id': c['id'], 'class': c['class'], 'level': c.get('level'), 'z': c.get('z'),
                             'surface_z': c.get('surface_z'), 'excluded': c.get('excluded'),
                             'rail_height_eligible': (r.get('construction') or {}).get('kind') == 'paved'
                             and c['class'] in ('deck', 'tram', 'road', 'paved', 'parking')}
                            for c in r.get('candidates', []) if c['dataset'] in ('deck', 'survey') and c.get('inside')]
                profile.append({'s': round(r['s'], 1), 'xy': [round(v, 2) for v in (r.get('di_xy') or r['xy'])],
                                'archive': archived, 'di_z': r.get('raw_di_z'), 'surfaces': surveyed, 'ipr_terrain_z': g})
            spans.append({'id': f'{ident}:line{line}:{key}', 'line': int(line), 'direction': key,
                          'structure': {'kind': 'step'}, 'status': 'review', 'start_s': round(rows[0]['s'], 1),
                          'length_m': round(rows[-1]['s'] - rows[0]['s'], 1), 'profile': profile})
            if line not in near:
                near.append(line)
            z, h = data['heights'].get(key) or [], data['heights']['step']
            around = z[max(0, int((s - AROUND) / h)):int((s + AROUND) / h)]
            if len(around) * h > 3 * CAR_PITCH and all(v is not None for v in around):
                step = max(step, max((abs(d) for _, d in coupling_steps(around, h)), default=0.0))
            apart = max([apart] + [abs(p['di_z'] - c['z']) for p in profile if isinstance(p['di_z'], (int, float)) and p['di_z'] > 100
                                   for c in p['archive'] if isinstance(c['z'], (int, float)) and c['z'] > 100 and not c['excluded']])
    if not spans:
        return None
    info = f"The rail here: a coupling step of up to {step * 100:.0f} cm; DI and the archive up to {apart:.2f} m apart. Listed for: "
    return {'kind': 'trackheight', 'id': ident, 'x': head['x'], 'y': head['y'], 'mag': round(step * 100, 1), 'status': 'review',
            'place': [round(lat, 5), round(lon, 5)], 'lines_near': sorted(near, key=int), 'info': info + '; '.join(p['what'] for p in group[:5]) + '.',
            'decision': {'span_ids': [sp['id'] for sp in spans], 'structure': {'kind': 'step'}, 'status': 'review'},
            'spans': spans, 'options': OPTIONS, 'answer_explanations': {}, 'answer_previews': {}}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--checkpoint', default='', help="also list this checkpoint's lint places (e.g. W1; none by default: "
                    "a checkpoint's places are those of its build, not of today's)")
    ap.add_argument('--output', type=Path, default=ROOT / 'reports/review/track-steps.json')
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    from atomic import replacing
    from ipr_dtm import IprDtm
    from geo import Frame
    import height_answers
    truth = json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8'))
    height_answers.RADIUS_ANSWERS = height_answers.load_radius_answers(truth)
    staged = height_answers.staged_heights()
    lines_data = {n: json.loads((ROOT / f'data/line{n}.json').read_text(encoding='utf-8')) for n in LINES}
    places = [p for n, d in lines_data.items() for p in line_steps(n, d)]
    from shapely import STRtree
    from shapely.geometry import LineString, Point
    routes = [LineString([p[:2] for p in d[k]]) for d in lines_data.values() for k in ('path', 'pathBack')]
    tree = STRtree(routes)
    # (a DI jump is listed where the rail as built still steps near it: the build drops what is steeper than any track,
    # height_answers MAX_GRADE, and a jump it smoothed away is no question)
    steps = list(places)
    places += [p for p in di_jumps(staged['geometry']) if len(tree.query(Point(p['x'], p['y']).buffer(ROUTE_NEAR), predicate='intersects'))
               and any(math.dist((p['x'], p['y']), (q['x'], q['y'])) <= REACH for q in steps)]
    if a.checkpoint:
        for q in lint_places(a.checkpoint):
            # (verticalCurves has only the route position)
            x, y = (q['x'], q['y']) if q['x'] is not None else at_s(lines_data[q['line']]['path'], q['s'])
            places.append({'x': x, 'y': y, 'cm': 0.0, 'what': f"lint {q['check']} (line {q['line']}, s {q['s']})"})
    samples = {}
    for r in staged['route_samples']:
        samples.setdefault((r['line'], r['direction']), []).append(r)
    frame, terrain = Frame(), IprDtm()
    # (a place the user answered is not asked again: its answer is in the build; one that still steps is printed)
    answered = [(tuple(float(v) for v in frame.xy(*s['place'])), s.get('decision'))
                for s in (truth.get('trackHeights') or {}).get('stepAnswers', [])]
    # (and an area where the user had the tracks follow the ground, steps of the ground and all: radiusAnswers `area`)
    from shapely.geometry import Polygon
    areas = [(Polygon([tuple(float(v) for v in frame.xy(*p)) for p in a['area']]), a.get('decision'))
             for a in (truth.get('trackHeights') or {}).get('radiusAnswers', []) if a.get('area')]
    groups, still = [], []
    for g in merged(places):
        here = (g[0]['x'], g[0]['y'])
        hit = next((d for xy, d in answered if math.dist(xy, here) <= ANSWERED), None) or \
            next((d for poly, d in areas if poly.distance(Point(here)) <= ANSWERED), None)
        if hit is None:
            groups.append(g)
        elif g[0]['cm'] >= STEP * 100:
            still.append(f"{hit}: {g[0]['what']}")
    try:
        out = [c for c in (card(g, samples, lines_data, frame, terrain) for g in groups) if c]
    finally:
        terrain.f.close()
    for s in still:
        print(f'answered, still stepping: {s}')
    out.sort(key=lambda f: -f['mag'])
    doc = {'schema': 1, 'snapshot': staged['snapshot'], 'title': 'Track heights: where the rail as built steps', 'issue': 344,
           'lines': list(LINES), 'findings': out}
    with replacing(a.output, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(doc, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(out)} places, {sum(f["mag"] >= 10 for f in out)} with a step of 10 cm or more: {a.output}')


if __name__ == '__main__':
    main()
