"""Where the signals and the stop points stand, decided in the build instead of at every game start (#22 stage 1):

    python -P -E tools/placement.py --line 17      # the last step after build_line (platforms, osm_signals, the
                                                   # validation of OSM's raw signals): writes data/lineN.json signals[]
                                                   # (signalsRaw: as build_line found them) and data/lineN.built.geojson
                                                   # (with the stop points)

The rules are src/game.js's, moved here whole: `_routeConflicts` (where roads, crossings and OSM's tram signals cross
the route), `_placeSignals` (each signal at its junction's stop line, dropped or on demand) and the platform rule of
`_initSignals` (a signal along a platform goes to its head, or hangs past it and the stop point moves back 3 m before
it). What stays in the game: the bridges (`profile.overBridge`, from the heights), the mounting (pole, span or island
tip, which needs the rendered street) and the stop zone, which depends on the set's length (the user, 2026-11-09: "the
stops must be universal everywhere, build the same to the real size found in the data ... the servicing stop is
handled by game code"). The game keeps its own rules as the fallback for data built before this and logs every place
where its result differs from the build's (`game.placementDiffs`).

Every decision carries its `rule` (data/lineN.built.geojson, docs/architecture.md §10.4): junctionEdge, onDemand,
afterJunction, droppedFarSide, keptPastCross, keptFar, sameStopLine, platformHead, platformHang.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STOP_AHEAD = 6.0     # m: without a sign in the data the front stops this far past the GTFS point (src/game.js STOP_AHEAD)
GAP = 20.0           # m between conflicts of one junction (a wide junction has 18 m between its streets' centre lines)


class Route:
    """The route as src/route.js Route keeps it for curved data (data.trackCurve): the points resampled every metre of
    arc length (smoothPolyline at radius 0), `at` on those 1 m chords, `nearest` from samples every 4 m refined onto the
    chords to their neighbours. The same sampling, so a position or a heading differs from the game's by nothing."""

    def __init__(self, pts):
        p = np.asarray([q[:2] for q in pts], dtype=float)
        cum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        L = float(cum[-1])
        n = max(2, round(L) + 1)
        ss = L * np.arange(n) / (n - 1)
        j = np.clip(np.searchsorted(cum, ss, side='left') - 1, 0, len(p) - 2)
        # (the game's index walks forward while cum[j + 1] < s: the segment whose end is the first at or past s)
        seg = cum[j + 1] - cum[j]
        t = np.clip((ss - cum[j]) / np.where(seg > 0, seg, 1e-9), 0, 1)
        self.p = p[j] + (p[j + 1] - p[j]) * t[:, None]
        self.s = ss
        self.length = L
        samp = np.arange(0.0, L + 1e-9, 4.0)
        self.samples = np.array([self.at(s)[:2] for s in samp])
        self.sample_s = samp
        self.tree = shapely.STRtree(shapely.points(self.samples))

    def at(self, s):
        """(x, y, hx, hy) at route position s, on the 1 m chords."""
        hi = len(self.s) - 1
        i = 0 if s <= self.s[0] else hi - 1 if s >= self.s[hi] else int(np.searchsorted(self.s, s, side='right')) - 1
        a, b = self.p[i], self.p[i + 1]
        seg = (self.s[i + 1] - self.s[i]) or 1e-9
        t = max(0.0, min(1.0, (s - self.s[i]) / seg))
        dl = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (b[0] - a[0]) / dl, (b[1] - a[1]) / dl

    def nearest(self, x, y):
        """(s, d): the nearest 4 m sample refined onto the chords to its neighbours (src/route.js nearest); (None, inf)
        beyond the game's reach (its 40 m grid, neighbouring cells)."""
        i = int(self.tree.query_nearest(Point(x, y), all_matches=False)[0])
        q = self.samples[i]
        d = math.hypot(q[0] - x, q[1] - y)
        if abs(math.floor(q[0] / 40) - math.floor(x / 40)) > 1 or abs(math.floor(q[1] / 40) - math.floor(y / 40)) > 1:
            return None, math.inf
        s = float(self.sample_s[i])
        for o in (-1, 1):
            if not 0 <= i + o < len(self.samples):
                continue
            r = self.samples[i + o]
            ex, ey = r[0] - q[0], r[1] - q[1]
            l2 = ex * ex + ey * ey
            if l2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((x - q[0]) * ex + (y - q[1]) * ey) / l2))
            dd = math.hypot(q[0] + ex * t - x, q[1] + ey * t - y)
            if dd < d:
                d, s = dd, float(self.sample_s[i] + (self.sample_s[i + o] - self.sample_s[i]) * t)
        return s, d


def stop_points(stops, length):
    """The front's stop point of each stop before the platform rule: beside its sign, else STOP_AHEAD past the GTFS
    point; never in the route's last 2 m (src/game.js _initStops)."""
    return [min(st['sign'] if st.get('sign') is not None else st['s'] + STOP_AHEAD, length - 2) for st in stops]


def _densify(line, step):
    out = [tuple(line[0][:2])]
    for a, b in zip(line, line[1:]):
        n = math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]
    return out


def widened(roads, tracks):
    """The roads as the game widens them before it looks for conflicts (src/world.js widenTramStreets): a road with 60 %
    of its points within 2.6 m of a track carries the track zone too, 3.2 m per track (two where tracks lie 1.6 m to
    both sides of 30 % of its points). Copies; the data's roads stay as they are."""
    segs = [LineString([a[:2], b[:2]]) for t in tracks for a, b in zip(t['p'], t['p'][1:]) if a[:2] != b[:2]]
    tree = shapely.STRtree(segs) if segs else None

    def dist(pts):
        if tree is None or not len(pts):
            return np.full(len(pts), np.inf)
        idx, d = tree.query_nearest(shapely.points(np.asarray(pts)), return_distance=True, all_matches=False)
        out = np.full(len(pts), np.inf)
        out[idx[0]] = d
        return out
    out = []
    for r in roads:
        r = dict(r)
        if not r.get('f') and (r.get('w') or 0) >= 5 and len(r['p']) >= 2:
            pts = _densify(r['p'], 5)
            near = dist(pts) < 2.6
            off = []
            for i, (x, y) in enumerate(pts):
                a, c = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
                hx, hy = c[0] - a[0], c[1] - a[1]
                hl = math.hypot(hx, hy) or 1
                off += [(x - hy / hl * 1.6, y + hx / hl * 1.6), (x + hy / hl * 1.6, y - hx / hl * 1.6)]
            d2 = dist(off)
            both = (d2[0::2] < 0.8) & (d2[1::2] < 0.8)
            if near.mean() >= 0.6:
                r['w'] = r['w'] + 3.2 * (2 if both.mean() > 0.3 else 1)
        out.append(r)
    return out


def route_conflicts(R, roads, crossings, osm_tram, stops, targets):
    """[{s, start, car}] by s: where streets, crossings and OSM's tram signals cross the route (src/game.js
    _routeConflicts). `osm_tram`: [(x, y)] or None where the line has no OSM signal data."""
    out = []
    for r in roads:
        if r.get('t'):
            continue
        chain = (r.get('way') or r['p']) if r.get('b') else None
        ends = (chain[0], chain[-1]) if chain else None
        P = r['p']
        for i in range(1, len(P)):
            a, b = P[i - 1], P[i]
            L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
            _, md = R.nearest((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            if md > L / 2 + 3:
                continue
            t = 0.0
            while t <= L:
                x, y = a[0] + (b[0] - a[0]) * t / L, a[1] + (b[1] - a[1]) * t / L
                s, d = R.nearest(x, y)
                t += 1.0
                if d > 1.2:
                    continue
                if ends and min(math.hypot(e[0] - x, e[1] - y) for e in ends) > 25:
                    break
                _, _, hx, hy = R.at(s)
                cos = abs(((b[0] - a[0]) * hx + (b[1] - a[1]) * hy) / L)
                if cos < 0.95:
                    out.append({'s': s, 'start': s - (r.get('w') or 3) / 2 / max(0.3, math.sqrt(1 - cos * cos)),
                                'car': bool(not r.get('f') and r.get('c'))})
                break
    tram = []
    for x, y in osm_tram or ():
        s, d = R.nearest(x, y)
        if d < 4:
            tram.append(s)

    def in_platform(s):
        return osm_tram is not None and any(st.get('p0') is not None and st['p0'] + 2 < s < st['p1'] - 0.5 for st in stops) \
            and not any(abs(t - s) < 5 for t in tram)
    out += [{'s': s, 'start': s - 2, 'car': False} for s in crossings if not in_platform(s)]
    out += [{'s': s, 'start': s - 2.5, 'car': False} for s in tram]
    return sorted(out, key=lambda c: c['s'])


def place_signals(signals, C, stops, targets):
    """The signals at their junctions (src/game.js _placeSignals): a list of dicts with s, s0, cross, and as decided
    edge, farEdge, demand, drop and the `rule`; and the moves as the game logs them."""
    def edge(lo, hi):
        return min(c['start'] for c in C[lo:hi + 1])

    def cluster_of(k):
        lo = hi = k
        while lo > 0 and C[lo]['s'] - C[lo - 1]['s'] < GAP:
            lo -= 1
        while hi < len(C) - 1 and C[hi + 1]['s'] - C[hi]['s'] < GAP:
            hi += 1
        return lo, hi
    out = [dict(d) for d in signals]
    moved = []
    for d in out:
        s0 = d['s']
        d['s0'] = s0
        plat = next((i for i, st in enumerate(stops)
                     if d['s'] > (st['p0'] if st.get('p0') is not None else targets[i] - 30) - 1 and d['s'] < targets[i] + 2), None)
        frm = max(d['s'], targets[plat]) if plat is not None else d['s']
        k = next((i for i, c in enumerate(C) if c['s'] > frm - 3), -1)
        best = C[k]['s'] - frm if k >= 0 else math.inf
        if best > 40:
            k, best = -1, math.inf
            for i, c in enumerate(C):
                e = abs(c['s'] - d['cross'])
                if e < best:
                    best, k = e, i
            if best > 30:
                k = -1
        if k < 0:
            d['demand'], d['rule'] = True, 'onDemand'
            moved.append(f"{round(s0)} on demand")
            continue
        lo, hi = cluster_of(k)
        own_street = any(c['car'] for c in C[lo:hi + 1])
        behind = [c for c in C if c['car'] and d['s'] - 25 < c['s'] < d['s']]
        if not own_street and behind:
            blo, bhi = cluster_of(C.index(behind[-1]))
            first = edge(blo, bhi)
            if not any(o is not d and first - 30 < o['s'] < first for o in signals):
                d['s'], d['edge'] = first - 4, first
                d['cross'] = next(c for c in C[blo:] if c['car'])['s']
                d['rule'] = 'afterJunction'
                moved.append(f"{round(s0)}→{round(d['s'])} (it stood after its junction)")
                continue
            d['drop'], d['rule'] = True, 'droppedFarSide'
            moved.append(f"{round(s0)} dropped (a far-side crossing of the junction before it)")
            continue
        d['edge'] = edge(lo, hi)
        if plat is None and d.get('cross') is not None and d['edge'] > d['cross'] + 5 and d['cross'] > d['s']:
            moved.append(f"{round(s0)} kept (the first conflict at {round(d['edge'])} lies past its own crossing {round(d['cross'])})")
            d['edge'], d['rule'] = d['cross'], 'keptPastCross'
            continue
        want = d['edge'] - 4
        if want > d['s'] + 25:
            moved.append(f"{round(s0)} kept (its junction edge {round(want - d['s'])} m on)")
            d['farEdge'], d['edge'], d['rule'] = d['edge'], d['s'] + 4, 'keptFar'
            continue
        d['rule'] = 'junctionEdge'
        if abs(want - d['s']) > 1:
            d['s'] = want
            moved.append(f"{round(s0)}→{round(d['s'])}")
    live = sorted([d for d in out if not d.get('drop')], key=lambda d: d['s'])
    for i in range(1, len(live)):
        a, b = live[i - 1], live[i]
        if b['s'] - a['s'] >= 8 or a.get('drop'):
            continue
        later = b if b.get('cross', b['s']) >= a.get('cross', a['s']) else a
        later['drop'], later['rule'] = True, 'sameStopLine'
        moved.append(f"{round(later['s0'])} dropped (at the stop line of {round((a if later is b else b)['s0'])})")
    return out, moved


def platform_rule(placed, stops, targets):
    """A signal never stands along a platform (src/game.js _initSignals): it moves to the platform head, or, where the
    crossing follows too closely, hangs past it and the stop's point moves back to 3 m before it. Changes `placed`
    and `targets` in place; the signals' `head` is the stop's index."""
    for d in placed:
        if d.get('drop'):
            continue
        for i, st in enumerate(stops):
            a = (st['p0'] if st.get('p0') is not None else targets[i] - 30) - 1
            b = targets[i] + 2
            if not a < d['s'] < b:
                continue
            if b < d.get('edge', d['cross']) - 1:
                d['s'], d['rule'] = b, 'platformHead'
            else:
                d['hang'], d['head'], d['rule'] = True, i, 'platformHang'
                far = d.get('farEdge', d.get('edge', d['cross']))
                d['s'] = max(d['s'], min(targets[i], far) + 3)
                if d['s'] - 3 < targets[i]:
                    targets[i] = d['s'] - 3
    return placed, targets


def place(data, osm_tram):
    """(signals, stop targets, moves, conflicts) for a line's data."""
    R = Route(data['path'])
    stops = data['stops']
    targets = stop_points(stops, R.length)
    C = route_conflicts(R, widened(data.get('roads', []), data.get('tracks', [])), data.get('crossings', []), osm_tram, stops, targets)
    placed, moved = place_signals(data.get('signals', []), C, stops, targets)
    placed, targets = platform_rule(placed, stops, list(targets))
    return placed, targets, moved, C, R


def built_geojson(line, data, placed, targets, C, R, build):
    """data/lineN.built.geojson: what the build decided (docs/architecture.md §10.4), in S-JTSK like the game's export."""
    e0, n0 = data['frame']['origin']
    ll = lambda x, y: [round(e0 + x, 2), round(n0 + y, 2)]  # noqa: E731
    feats = []

    def feat(geom, **p):
        feats.append({'type': 'Feature', 'geometry': geom, 'properties': {'line': line, **p}})
    for st, t in zip(data['stops'], targets):
        x, y, _, _ = R.at(t)
        feat({'type': 'Point', 'coordinates': ll(x, y)}, id=f"tram_stop_point:{line}:{st['name']}", type='tram_stop_point',
             stop=st['name'], s=round(t, 1), rule='platformHang' if st.get('sign') is not None and abs(t - st['sign']) > 0.05 else 'sign' if st.get('sign') is not None else 'gtfsAhead')
    for d in placed:
        sid = f"tram_signal:{line}:sig@{round(d['s0'])}"
        x, y, hx, hy = R.at(d['s'])
        props = {'id': sid, 'type': 'tram_signal', 's': round(d['s'], 1), 'stopAt': round(d['s'] - 3, 1), 'rule': d.get('rule')}
        if d.get('drop'):
            props['dropped'] = True
        feat({'type': 'Point', 'coordinates': ll(x, y)}, **props)
        if not d.get('drop'):
            qx, qy, qhx, qhy = R.at(d['s'] - 3)
            feat({'type': 'LineString', 'coordinates': [ll(qx + qhy * 1.6, qy - qhx * 1.6), ll(qx - qhy * 1.6, qy + qhx * 1.6)]},
                 id=f"tram_signal_stop:{line}:sig@{round(d['s0'])}", type='tram_signal_stop', signal=sid, s=round(d['s'] - 3, 1))
    for c in C:
        x, y, _, _ = R.at(c['start'])
        feat({'type': 'Point', 'coordinates': ll(x, y)}, id=f"conflict:{line}:@{round(c['start'])}", type='conflict',
             s=round(c['start'], 1), car=c['car'])
    return {'type': 'FeatureCollection', 'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:EPSG::5514'}},
            'properties': {'line': line, 'build': build, 'origin': [e0, n0]}, 'features': feats}


def osm_tram_signals(line):
    """OSM's tram signals of the line ([(x, y)]; data/lineN.signals.json, tools/osm_signals.py), or None without them."""
    p = ROOT / 'data' / f'line{line}.signals.json'
    if not p.exists():
        return None
    return [(c['x'], c['y']) for c in json.loads(p.read_text(encoding='utf-8')).get('tram', [])]


SIGNAL_KEYS = ('s', 's0', 'cross', 'edge', 'farEdge', 'demand', 'drop', 'hang', 'head', 'rule')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--line', required=True)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    path = ROOT / 'data' / f'line{a.line}.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    # (the build's own signals, before any placement: rebuilt data has them as build_line wrote them)
    raw = data.get('signalsRaw') or [{'s': d['s0'], 'cross': d['cross']} if 's0' in d else {'s': d['s'], 'cross': d['cross']}
                                     for d in data.get('signals', [])]
    data['signals'] = raw
    placed, targets, moved, C, R = place(data, osm_tram_signals(a.line))
    data['signalsRaw'] = raw
    data['signals'] = [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in d.items() if k in SIGNAL_KEYS} for d in placed]
    with replacing(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    gj = built_geojson(a.line, data, placed, targets, C, R, os.environ.get('BUILD_ID', 'build'))
    with replacing(ROOT / 'data' / f'line{a.line}.built.geojson', 'w', encoding='utf-8') as f:
        json.dump(gj, f, ensure_ascii=False, separators=(',', ':'))
    rules = {}
    for d in placed:
        rules[d.get('rule')] = rules.get(d.get('rule'), 0) + 1
    print(f"line {a.line}: {len(C)} conflicts, {len(placed)} signals {rules}, "
          f"{sum(1 for st, t in zip(data['stops'], targets) if st.get('sign') is not None and abs(t - st['sign']) > 0.05)} stop points moved back")
    print(f"signals placed: {', '.join(moved)}")


if __name__ == '__main__':
    main()
