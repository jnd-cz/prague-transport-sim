# SPDX-License-Identifier: AGPL-3.0-or-later
"""Review cards for the curves drawn in steps (#368): every place tools/lint.js `steppedCurves` flags on a line's path or
opposite path, the places of one curve on several lines and both tracks merged, with how large each step is.

    python -P -E tools/stepped_review.py reports/headless     # a `headless.py --checks lint` run's folder (lineN-lint.json)

Writes reports/review/stepped-curves.json. A step's size is read on the track as the game draws it (data/lineN.json `path`,
`pathBack`): its corner, the turn over 5 m beyond the curve's own (5/R5 - 5/R25, the radii over 5 and 25 m as the check
reads them), and how far the track leaves the one circle fitted to it over those 25 m. A place the user answered
(data/truth.json trackSources.steppedAnswers, read by tools/di_network.py) leaves the list.
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
SHORT, LONG = 2.5, 12.5  # m either side: the check's STEP_SHORT and STEP_LONG (tools/lint.js)
SAMPLE = 0.5    # m between the points the smooth curve is fitted to
SCAN = 3.0      # m either side of the check's place where the step is looked for
GROUP = 20.0    # m: places this near each other are one curve (its two tracks, the lines sharing it)
SWITCH_NEAR = 15.0  # m: a step this near where drawn tracks meet is named with it (11 of the 20 are, #368)
ISSUE = 368
OPTIONS = ['smooth into one curve', 'keep as drawn', 'unsure']
WHY = {'smooth into one curve': "DI's vertices within 10 m of the place leave the curve fit, which draws one curve through: "
                                "the track moves by about the step's size.",
       'keep as drawn': 'A real corner (a switch, a joint, a short straight between curves): the track stays as it is.',
       'unsure': 'This answer stays held for review.'}


def along(p):
    """(length, at(s)) of a polyline of [x, y, ...] points, linear between them."""
    cum = [0.0]
    for a, b in zip(p, p[1:]):
        cum.append(cum[-1] + math.dist(a[:2], b[:2]))

    def at(s):
        s = max(0.0, min(cum[-1], s))
        lo, hi = 0, len(cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if cum[mid] <= s else (lo, mid)
        t = (s - cum[lo]) / ((cum[hi] - cum[lo]) or 1e-9)
        return (p[lo][0] + (p[hi][0] - p[lo][0]) * t, p[lo][1] + (p[hi][1] - p[lo][1]) * t)
    return cum[-1], at


def circle_radius(a, b, c):
    """The radius of the circle through three points, at most 1e6 m (a line), as the check computes it."""
    ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
    cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    return 1e6 if cross <= 1e-9 else min(1e6, ab * bc * ca / (2 * cross))


def step_offset(at, t):
    """How far the track within SHORT of route t leaves the smooth curve of its flanks (m): a cubic across the chord of the
    25 m, least squares on the points SHORT to LONG either side. Over 25 m a cubic follows a 127 m circle within 2 mm, a
    transition and an S-bend too (one circle read an S as metres off it); what the flanks' curve cannot follow in the middle
    is the step."""
    import numpy as np
    pts = [at(t - LONG + j * SAMPLE) for j in range(int(2 * LONG / SAMPLE) + 1)]
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    d = math.hypot(x1 - x0, y1 - y0) or 1e-9
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    u = np.array([(x - x0) * ux + (y - y0) * uy for x, y in pts])
    v = np.array([-(x - x0) * uy + (y - y0) * ux for x, y in pts])
    mid = np.abs(np.arange(len(pts)) * SAMPLE - LONG) <= SHORT
    fit = np.polyfit(u[~mid], v[~mid], 3)
    return float(np.abs(v[mid] - np.polyval(fit, u[mid])).max())


def measure(path, s, info=None, scan=SCAN):
    """How large the step at route s is: the radii over 5 and 25 m as the check read them (its `info`, else read here), the
    corner they imply (degrees: the turn over 5 m beyond the curve's own) and the step's offset (m) from the smooth curve of
    its flanks, the largest within `scan` m (the check reads the game's route, whose s can lie a metre or two off the data's
    path, and in a stepped curve the radii change by tens of times within 2 m)."""
    L, at = along(path)
    m = re.search(r'(\d+) m over 5 m in a (\d+) m curve', info or '')
    r5, r25 = (float(m.group(1)), float(m.group(2))) if m else (circle_radius(at(s - SHORT), at(s), at(s + SHORT)),
                                                                 circle_radius(at(s - LONG), at(s), at(s + LONG)))
    off, t = max((step_offset(at, min(L - LONG, max(LONG, s + k / 2))), s + k / 2) for k in range(-int(2 * scan), int(2 * scan) + 1))
    corner = math.degrees(2 * SHORT / r5 - 2 * SHORT / r25)
    return {'r5': r5, 'r25': r25, 'corner_deg': corner, 'offset_m': off, 'xy': at(t)}


def groups(places, near=GROUP):
    """The places joined where they lie within `near` of each other (single linkage), each group a list of places."""
    out = []
    for p in places:
        hit = [g for g in out if any(math.dist(p['xy'], q['xy']) <= near for q in g)]
        for g in hit:
            out.remove(g)
        out.append(sum(hit, []) + [p])
    return out


def card(group, frame):
    """One finding for review mode (src/reviewFindings.js): the worst place's spot, every place's step."""
    worst = max(group, key=lambda p: p['offset_m'])
    lat, lon = (float(v) for v in frame.ll(*worst['xy']))
    lines = sorted({p['line'] for p in group}, key=int)
    parts = []
    for p in sorted(group, key=lambda p: (int(p['line']), p['kind'], p['s'])):
        sw = (f", {p['switch']:.0f} m from where drawn tracks meet (a switch, a crossing or a joint)"
              if p['switch'] is not None and p['switch'] <= SWITCH_NEAR else '')
        parts.append(f"line {p['line']} {p['kind']} track, s {p['s']}: {p['r5']:.0f} m over 5 m in a {p['r25']:.0f} m curve, a corner of "
                     f"{p['corner_deg']:.1f}° that leaves one smooth curve by {p['offset_m'] * 100:.0f} cm{sw}")
    name, at = worst['stop']
    near = f" {math.dist(worst['xy'], at):.0f} m from the stop {name}" if name else ''
    info = (f"A curve drawn in steps{near}: the step is {worst['offset_m'] * 100:.0f} cm off one smooth curve, a "
            f"{worst['corner_deg']:.1f}° corner. " + '; '.join(parts) + '.')
    return {'kind': 'stepped curve', 'id': f'stepped-{lat:.4f}-{lon:.4f}', 'x': round(worst['xy'][0], 2), 'y': round(worst['xy'][1], 2),
            'mag': round(worst['offset_m'] * 100, 1), 'status': 'review', 'place': [round(lat, 5), round(lon, 5)],
            'line': int(lines[0]), 'lines_near': lines, 'stop': name, 'info': info,
            'step': {'offset_cm': round(worst['offset_m'] * 100, 1), 'corner_deg': round(worst['corner_deg'], 2),
                     'r5_m': round(worst['r5']), 'r25_m': round(worst['r25'])},
            'places': [{'line': int(p['line']), 'track': p['kind'], 's': p['s'], 'offset_cm': round(p['offset_m'] * 100, 1),
                        'corner_deg': round(p['corner_deg'], 2), 'r5_m': round(p['r5']), 'r25_m': round(p['r25']),
                        'meet_m': None if p['switch'] is None else round(p['switch'], 1)} for p in group],
            'options': OPTIONS, 'answer_explanations': WHY}


def build(lint_dir, root=ROOT, answers=None):
    """The cards from a lint run's folder and the lines' data."""
    import di_tracks
    from geo import Frame
    frame = Frame()
    answered = di_tracks.stepped_answers(answers) if answers is not None else di_tracks.stepped_answers()
    places = []
    for f in sorted(Path(lint_dir).glob('line*-lint.json')):
        line = f.name[4:-10]
        res = json.loads(f.read_text(encoding='utf-8')).get('result') or {}
        flagged = ((res.get('checks') or {}).get('steppedCurves') or {}).get('places', [])
        if not flagged:
            continue
        d = json.loads((root / 'data' / f'line{line}.json').read_text(encoding='utf-8'))
        # (where drawn track pieces end: a switch, a crossing, a joint of two records, on either track; the line's
        # switches are only those on its own route)
        _, on_path = along(d['path'])
        ends = [tuple(t['p'][k][:2]) for t in d.get('tracks', []) if len(t.get('p') or []) >= 2 for k in (0, -1)]
        ends += [on_path(w['s']) for w in d.get('switches', [])]  # (a through track has no end at its switch)
        stops = [(x['name'], on_path(x['s'])) for x in d.get('stops', [])]
        for q in flagged:
            p = measure(d['path'] if q['kind'] == 'our' else d['pathBack'], q['s'], q.get('info'))
            p.update(line=line, kind=q['kind'], s=q['s'], switch=min((math.dist(p['xy'], w) for w in ends), default=None),
                     stop=min(stops, key=lambda x: math.dist(p['xy'], x[1]), default=(None, None)))
            places.append(p)
    out = []
    for g in groups(places):
        c = card(g, frame)
        if not any(math.dist((c['x'], c['y']), xy) <= r for xy, _, r in answered):
            out.append(c)
    out.sort(key=lambda c: -c['mag'])
    return out


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    from atomic import replacing
    found = build(sys.argv[1])
    snap = (ROOT / 'snapshots' / 'CURRENT').read_text().strip()
    dst = ROOT / 'reports' / 'review' / 'stepped-curves.json'
    with replacing(dst, 'w', encoding='utf-8', newline='') as fh:
        json.dump({'schema': 1, 'snapshot': snap, 'issue': ISSUE, 'title': 'Curves drawn in steps',
                   'lines': sorted({n for c in found for n in c['lines_near']}, key=int), 'findings': found}, fh, ensure_ascii=False, indent=1)
    print(f'{dst.relative_to(ROOT)}: {len(found)} places')
    for c in found:
        print(f"  {c['id']} lines {','.join(c['lines_near'])}: {c['step']['offset_cm']} cm, {c['step']['corner_deg']}°, "
              f"{c['step']['r5_m']} m over 5 m in {c['step']['r25_m']} m ({len(c['places'])} places)")


if __name__ == '__main__':
    main()
