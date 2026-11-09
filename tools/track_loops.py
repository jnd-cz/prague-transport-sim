"""Turning loops on DI's track network, found by rule, for the loop speed (D 1/2 § 25.4 e; data/truth.json operation
`loop-speed`; #211):

    python -P -E tools/track_loops.py          # every loop on the network by its nearest stop, and the GTFS termini
                                               # without one (the rule's calibration)

The user's rule (Claude Code session 2026-11-09, #211): "it's loop at the end of gtfs route, or any loop where two track
diverge and come back together with larger than 180 degree turn, that's for double track loop (Sídliště Petřiny). There
are side loops like Dvorce or Hlubočepy which are not used by regular service but still need the limit."

**A loop** is a path over the network's passes (tools/di_network.py) from a switch entered by its toe (the switch into
the loop) to a switch left by its toe (the switch out of it; the same one for a balloon) that:
- turns TURN or more from the heading in to the heading out: the street's tracks run back, 180° give or take their own
  bends. (From the switch's leg instead it falls short by the switch's angle: Divoká Šárka 173°.)
- ends within NECK of where it starts: a loop's switches lie together (Lehovec's whole loop 120 m apart, the farthest;
  Sídliště Petřiny's 72 m); a circuit round city blocks comes back 214-510 m away (Palmovka, Strossmayerovo náměstí,
  Masarykovo nádraží, Náměstí Míru);
- runs at most BOUND m;
- is drivable: its mean radius at least `min-radius-network` (data/truth.json trackGeometry): a 52 m path turning 276°
  at Radošovická is a junction drawn in pieces, not a track.
The user reviewed the 47 it finds (2026-11-09): all are real loops.

**On a route** (rule 1 as well as 2): a route is in a loop where it follows the loop's whole path, or the part of it
from its own start or to its own end (a route that starts or ends in its loop). A route that runs over a circuit's
street only in part does not take it. The stretch runs from the switch into the loop to the switch out of it, as the
fact says; src/speedRules.js limits it.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TURN = 170.0     # degrees, heading in to heading out
NECK = 150.0     # m between the switch into the loop and the switch out of it
BOUND = 600.0    # m: the longest loop path searched
MIN_TRIPS = 90   # GTFS trips ending at a stop for the calibration to count it a terminus (fewer: pull-in and pull-out runs)
NEAR = 400.0     # m: a terminus this near a loop's track has it


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _min_radius():
    from track_curve import geometry_fact
    return float(geometry_fact('min-radius-network'))


class _Geometry:
    """Each edge's turn (signed, radians) and its headings at both ends, travelled either way."""

    def __init__(self, net):
        self.net, self.g = net, {}
        for e, ed in net.edges.items():
            c = list(ed['line'].coords)
            hs = [math.atan2(c[i + 1][1] - c[i][1], c[i + 1][0] - c[i][0]) for i in range(len(c) - 1)
                  if math.dist(c[i][:2], c[i + 1][:2]) > 1e-6]
            if hs:
                self.g[e] = (sum(_wrap(hs[i + 1] - hs[i]) for i in range(len(hs) - 1)), hs[0], hs[-1], ed['line'].length)

    def trav(self, e, entered):
        """turn, heading in, heading out, length of edge e entered by its end `entered` (0: its start)"""
        t, h0, h1, L = self.g[e]
        return (t, h0, h1, L) if entered == 0 else (-t, _wrap(h1 + math.pi), _wrap(h0 + math.pi), L)

    def out_heading(self, x):
        d = self.net.out_dir(*x)
        return math.atan2(d[1], d[0])


def candidates(net, bound=BOUND):
    """Every path from a switch entered by its toe to a switch left by its toe within `bound` m: {'s1', 's2', 'path':
    [(edge, dir)] (dir 1: along the edge's line), 'turn' degrees (signed), 'len' m, 'neck' m}."""
    geo, out = _Geometry(net), []
    switches = {n: th for n in net.nodes if (th := net.through(n))}
    node_of = lambda e, end: net.edges[e]['a'] if end == 0 else net.edges[e]['b']  # noqa: E731
    for s1, (toe, a, b) in switches.items():
        if toe[0] not in geo.g:
            continue
        h_in = _wrap(geo.out_heading(toe) + math.pi)
        for leg in (a, b):
            if leg[0] not in geo.g:
                continue
            t, h0, h1, L = geo.trav(*leg)
            stack = [(leg, _wrap(h0 - h_in) + t, L, h1, (leg,))]
            while stack:
                (e, en), turn, length, hout, path = stack.pop()
                n = node_of(e, 1 - en)
                sw = switches.get(n)
                if sw and (e, 1 - en) in (sw[1], sw[2]):
                    out.append({'s1': s1, 's2': n, 'path': [(x, 1 if xe == 0 else -1) for x, xe in path],
                                'turn': math.degrees(turn + _wrap(geo.out_heading(sw[0]) - hout)), 'len': length,
                                'neck': math.dist(net.nodes[s1]['xy'], net.nodes[n]['xy'])})
                seen = {x for x, _ in path}
                for y in net.passes.get((e, 1 - en), ()):
                    if y[0] not in geo.g or y[0] in seen:
                        continue
                    ty, hy0, hy1, Ly = geo.trav(*y)
                    if length + Ly <= bound:
                        stack.append((y, turn + _wrap(hy0 - hout) + ty, length + Ly, hy1, path + (y,)))
    return out


def why_not(c, turn=TURN, neck=NECK, radius=None):
    """None for a loop, else what the candidate fails."""
    if abs(c['turn']) < turn:
        return f"turns {abs(c['turn']):.0f}°"
    if c['neck'] > neck:
        return f"ends {c['neck']:.0f} m from its start"
    if radius and c['len'] < radius * math.radians(abs(c['turn'])):
        return f"mean radius {c['len'] / math.radians(abs(c['turn'])):.1f} m"
    return None


def find(net, turn=TURN, neck=NECK, bound=BOUND, radius=None):
    """The loops: the candidates that pass the rule (`radius`: min-radius-network unless given)."""
    radius = _min_radius() if radius is None else radius
    return [c for c in candidates(net, bound) if why_not(c, turn, neck, radius) is None]


def groups(loops):
    """Loops sharing an edge or a switch, together: [[loop]] (one terminus, a double-track loop's two tracks)."""
    parent = list(range(len(loops)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    by_edge = defaultdict(list)
    for i, c in enumerate(loops):
        for k in [e for e, _ in c['path']] + [('node', c['s1']), ('node', c['s2'])]:
            by_edge[k].append(i)
    for ids in by_edge.values():
        for j in ids[1:]:
            parent[root(j)] = root(ids[0])
    out = defaultdict(list)
    for i, c in enumerate(loops):
        out[root(i)].append(c)
    return list(out.values())


def on_route(pieces, ends, loops):
    """The route's stretches in loops, [{'from', 'to'}] in route metres, merged: `pieces` a Match's [(edge, dir, t0, t1) |
    ('off', pts)], `ends` the route position where each piece ends (Drawn.route)."""
    seq = []      # (edge, dir, start s, end s) of the route's pieces on the network, consecutive ones of an edge merged
    for i, p in enumerate(pieces):
        if p[0] == 'off':
            seq.append(None)
            continue
        a, d = ends[i - 1] if i else 0.0, 1 if p[1] > 0 else -1
        if seq and seq[-1] and seq[-1][:2] == (p[0], d):
            seq[-1] = (p[0], d, seq[-1][2], ends[i])
        else:
            seq.append((p[0], d, a, ends[i]))
    on = [x for x in seq if x]
    first, last = (seq.index(on[0]), len(seq) - 1 - seq[::-1].index(on[-1])) if on else (0, -1)
    out = []
    for c in loops:
        path, k = c['path'], len(c['path'])
        for i in range(len(seq)):
            for j in range(k):
                # the route's piece i is the loop's j-th edge: it follows on from there while both agree
                if not seq[i] or seq[i][:2] != path[j]:
                    continue
                if j and i != first:
                    continue      # (enters the loop's path in its middle: only a route starting there)
                m = 0
                while j + m < k and i + m < len(seq) and seq[i + m] and seq[i + m][:2] == path[j + m]:
                    m += 1
                if j + m < k and i + m - 1 != last:
                    continue      # (leaves the loop's path before its end: only a route ending there)
                out.append([seq[i][2], seq[i + m - 1][3]])
    out.sort()
    merged = []
    for a, b in out:
        if merged and a <= merged[-1][1] + 0.5:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [{'from': round(a, 1), 'to': round(b, 1)} for a, b in merged if b - a > 0.5]


def _termini(root):
    """{name: [(x, y, trips)]}: where the GTFS's tram trips start and end, MIN_TRIPS or more, in city metres."""
    import csv
    import io
    import zipfile
    from geo import Frame
    rows = lambda z, n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding='utf-8-sig'))  # noqa: E731
    with zipfile.ZipFile(root / 'raw' / 'PID_GTFS.zip') as z:
        trams = {r['route_id'] for r in rows(z, 'routes.txt') if r['route_type'] == '0'}
        trips = {r['trip_id'] for r in rows(z, 'trips.txt') if r['route_id'] in trams}
        ends = {}
        for r in rows(z, 'stop_times.txt'):
            if r['trip_id'] in trips:
                k, lo, hi = int(r['stop_sequence']), *ends.get(r['trip_id'], ((1 << 30, None), (-1, None)))
                ends[r['trip_id']] = (min(lo, (k, r['stop_id'])), max(hi, (k, r['stop_id'])))
        stops = {r['stop_id']: r for r in rows(z, 'stops.txt')}
    count = defaultdict(int)
    for lo, hi in ends.values():
        count[lo[1]] += 1
        count[hi[1]] += 1
    f, out = Frame(), defaultdict(list)
    for sid, n in count.items():
        r = stops[sid]
        x, y = f.xy(float(r['stop_lat']), float(r['stop_lon']))
        out[r['stop_name']].append((float(x), float(y), n))
    return {k: v for k, v in out.items() if sum(t[2] for t in v) >= MIN_TRIPS}, stops, f


def main():
    import di_network
    sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parent.parent
    net = di_network.load_network()
    radius = _min_radius()
    cands = candidates(net)
    loops = [c for c in cands if why_not(c, radius=radius) is None]
    termini, stops, frame = _termini(root)
    named = [(float(x), float(y), r['stop_name']) for r in stops.values() if r.get('location_type', '0') in ('', '0')
             for x, y in [frame.xy(float(r['stop_lat']), float(r['stop_lon']))]]
    print(f"{len(cands)} paths from a switch's toe to a switch's toe within {BOUND:.0f} m; {len(loops)} pass the rule "
          f"(turn {TURN:.0f}°+, switches within {NECK:.0f} m, mean radius {radius:.0f} m+)")
    gs = groups(loops)
    near_terminus = set()
    print(f"\n{len(gs)} loops (by the nearest stop; neck: between the switches in and out; turn and length of the shortest path):")
    rows_ = []
    for g in gs:
        edges = {e for c in g for e, _ in c['path']}
        pts = [p for e in edges for p in net.edges[e]['line'].coords]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        name = min(named, key=lambda s: math.dist((cx, cy), s[:2]))[2]
        best = min(g, key=lambda c: c['len'])
        term = [t for t, ps in termini.items() if any(min(math.dist(p[:2], q[:2]) for q in pts) <= NEAR for p in ps)]
        near_terminus |= set(term)
        lat, lon = frame.ll(cx, cy)
        rows_.append((name, round(min(c['neck'] for c in g)), round(best['turn']), round(best['len']), len(g),
                      round(sum(net.edges[e]['line'].length for e in edges)), ', '.join(term) or '-', f"{float(lat):.5f},{float(lon):.5f}"))
    print('| nearest stop | neck m | turn ° | length m | paths | track m | GTFS terminus within 400 m | lat,lon |')
    print('|---|---|---|---|---|---|---|---|')
    for r in sorted(rows_):
        print('| ' + ' | '.join(map(str, r)) + ' |')
    missing = sorted(set(termini) - near_terminus)
    print(f"\nGTFS termini ({MIN_TRIPS}+ trips) without a loop within {NEAR:.0f} m: {len(missing)} of {len(termini)}")
    for t in missing:
        ps = termini[t]
        x, y = ps[0][:2]
        di = min(math.dist((x, y), n['xy']) for n in net.nodes.values())
        best = min((c for c in cands), key=lambda c: min(math.dist((x, y), net.nodes[c[k]]['xy']) for k in ('s1', 's2')), default=None)
        why = why_not(best, radius=radius) if best else None
        print(f"  {t} ({sum(p[2] for p in ps)} trips): DI's nearest node {di:.0f} m away"
              + (f"; the nearest candidate {why}" if why else ''))


if __name__ == '__main__':
    main()
