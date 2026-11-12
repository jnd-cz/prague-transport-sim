# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a track rebuild moved (#20): route-keyed layers of two builds of a line, compared by position.

    python -I tools/track_moves.py OLD/line17.json data/line17.json [--json reports/track-moves-17.json]

Per layer (stops, signals and their crossing points, crossings, switches, bridges, tunnels, clearances): where each
item lies on the old route and on the new one (the route point at its s), the distance between them, and its
along-route shift (the new s minus the old position projected on the new route). Items are paired in order
within a layer; a different count is reported. Fails (exit 1) on nothing: the PR explains every move over
MOVE metres.
"""
import json
import math
import sys

MOVE = 2.0   # m: a move worth explaining (#20)


class Route:
    def __init__(self, pts):
        self.pts = pts
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + math.dist(a, b))
        self.length = self.s[-1]

    def at(self, s):
        s = max(0.0, min(self.length, s))
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if self.s[mid] <= s else (lo, mid)
        a, b = self.pts[lo], self.pts[hi]
        t = (s - self.s[lo]) / ((self.s[hi] - self.s[lo]) or 1e-9)
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def project(self, p, near=None, reach=300.0):
        """s of the nearest route point (within reach of s=near when given: the route passes some places twice)."""
        best = (math.inf, None)
        for i in range(len(self.pts) - 1):
            if near is not None and (self.s[i + 1] < near - reach or self.s[i] > near + reach):
                continue
            a, b = self.pts[i], self.pts[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            l2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
            d = math.dist(p, (a[0] + dx * t, a[1] + dy * t))
            if d < best[0]:
                best = (d, self.s[i] + t * math.sqrt(l2))
        return best[1]


def items(data):
    out = {
        'stops': [(s['name'], s['s']) for s in data.get('stops', [])],
        'signals': [('signal', s['s']) for s in data.get('signals', [])],
        'signal crossings': [('cross', s['cross']) for s in data.get('signals', []) if s.get('cross') is not None],
        'crossings': [('crossing', s) for s in data.get('crossings', [])],
        'switches': [('switch', s['s']) for s in data.get('switches', [])],
        'bridges': [(f'bridge {i}', a) for i, (a, b) in enumerate(data.get('bridges', []))],
        'tunnels': [(f'tunnel {i}', a) for i, (a, b) in enumerate(data.get('tunnels', []))],
        'clearances': [(c.get('name') or c.get('kind') or 'clearance', c['s']) for c in data.get('clearances', [])],
    }
    return out


def compare(old, new):
    ro, rn = Route(old['path']), Route(new['path'])
    report = {'length_m': [round(ro.length, 1), round(rn.length, 1)], 'layers': {}}
    io, inew = items(old), items(new)
    for layer in io:
        a, b = io[layer], inew[layer]
        rows = []
        # pair by the old position projected on the new route: the nearest new item along it
        for name, s_old in a:
            p_old = ro.at(s_old)
            s_proj = rn.project(p_old, near=s_old * rn.length / (ro.length or 1))
            best = min(b, key=lambda it: abs(it[1] - s_proj), default=None)
            if best is None:
                continue
            p_new = rn.at(best[1])
            rows.append({'name': name, 's_old': round(s_old, 1), 's_new': round(best[1], 1),
                         'moved_m': round(math.dist(p_old, p_new), 2), 'along_m': round(best[1] - s_proj, 2)})
        big = [r for r in rows if r['moved_m'] > MOVE]
        report['layers'][layer] = {'count': [len(a), len(b)],
                                   'moved_m_max': max((r['moved_m'] for r in rows), default=0),
                                   'over': sorted(big, key=lambda r: -r['moved_m'])}
    return report


def main():
    argv = sys.argv[1:]
    out = argv[argv.index('--json') + 1] if '--json' in argv else None
    args = [a for a in argv if not a.startswith('--') and a != out]
    if len(args) != 2:
        sys.exit(__doc__)
    old, new = (json.load(open(p, encoding='utf-8')) for p in args)
    report = compare(old, new)
    print(f"route length {report['length_m'][0]} -> {report['length_m'][1]} m")
    for layer, r in report['layers'].items():
        print(f"{layer:17} {r['count'][0]:4} -> {r['count'][1]:4}  max move {r['moved_m_max']:6.2f} m, "
              f"{len(r['over'])} over {MOVE} m")
        for row in r['over'][:8]:
            print(f"    {row['name']}: {row['moved_m']} m (along {row['along_m']} m), s {row['s_old']} -> {row['s_new']}")
    if out:
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
