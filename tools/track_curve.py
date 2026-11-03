"""The drawn track in plan as smooth curves through the surveyed points, continuous in direction at every node (#204).

    python -P -E tools/track_curve.py --line 17     # fit line 17's track graph, print what moved and what was left

The track graph's edges (tools/di_tracks.py `TrackGeometry`) are polylines through DI's or the archive's points,
or OSM's nodes where neither has the track (fill). They are joined into through tracks: at every node the
straightest pair of edges continues (a switch's diverging edge, a track's end and a crossing track end or pass
there). Each through track, longest first, is fitted with a curve that bends as little as it can (a penalised
spline in plan, bending energy on 1 m samples) while it stays within TOL of every surveyed point (FILL_TOL of fill):
the points' weights grow only where the curve misses (Lawson's reweighting). A node a longer track already fixed
keeps its position (a track through a node is fitted before one ending there), and its direction where this track
continues that one (a diverging track leaves tangent to
the through track: data/truth.json trackGeometry `switch-start`, most switches are tangential). Where the curve
would bend tighter than MIN_RADIUS (data/truth.json `min-radius-passenger`), the tolerance of the points around it
grows by GROW, at most to the mean coordinate error of their records' accuracy class (data/truth.json
`sourceAccuracy`: 0.14 m for DI's class 3), and the curve is fitted again; a point the curve still misses by more than
TOL + REPORT is listed, and so is a curve left tighter than MIN_RADIUS.

A Gaussian (the client's old smoothing, src/route.js) cuts inside a curve: 0.2 m on an 18 m curve with the 6 m
window (#20); a curve held to the points does not.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TOL = 0.02         # m: the curve within this of every surveyed point (DI, the archive)
FILL_TOL = 0.3     # m: of OSM's nodes where neither has the track
UNCLASSED = '3'    # the accuracy class of surveyed records that state none (the archive): the DTM's own minimum
                   # (data/truth.json `sourceAccuracy`, the decree's § 3 odst. 7)
FILL_LIMIT = 0.5   # m: a fill point's tolerance grows at most to this (OSM against DI: p90 0.45 m at line 17's nodes)
SIGMAS = 1.0       # a point moves at most this many mean errors of its class (the decree states the mean error, no
                   # limit; 2 on line 17: 6 bends over 10° inside tracks instead of 11, 32 joins over 1° instead of 39)
GROW = 1.5         # the factor the tolerance grows by per round
MIN_RADIUS = 20.0  # m: data/truth.json trackGeometry `min-radius-passenger`
SLACK = 0.995      # a curve held at MIN_RADIUS reads a few millimetres under it
BEND = 1.0         # m either side of a sample for the fit's radius (a 5 m window reads a 10° bend squeezed into a
                   # metre as 29 m; the fitted curve has no noise to average out)
NEAR = 10.0        # m around a place bending too tight whose points' tolerance grows
REPORT = 0.01      # m: a surveyed point the final curve misses by more than TOL + this is listed
STEP = 1.0         # m between the curve's samples
LAMBDA = 300.0     # bending weight: a smoothing length of (LAMBDA / point density)^(1/4), 5 m at a point per 2 m
FILL_WEIGHT = 0.1  # a fill point's starting weight against a surveyed one's 1
FIX = 1e6          # the weight that holds a fixed position or direction
PAIR = 45.0        # degrees: two edges at a junction continue each other within this; at a two-edge node, PAIR_TWO
PAIR_TWO = 60.0
START = 6.0        # degrees: a track ending at a node leaves tangent to the track through it it starts within this of
                   # (113 ends on line 17: 96 within 4°, 9 at 8-40°); beyond, at its own angle (`switch-start`: some
                   # designs start abruptly), listed by tools/lint.js trackJoins
LOOK = 3.0         # m along an edge for its direction at a node
CROSS = 10.0       # degrees: two tracks passing one node at more than this cross there (else they touch)
MERGE = 0.5        # m: nodes joined by a shorter edge are one
CLEAR = 0.5        # m from an end node held by a track fitted before: no data points
GAP_MAX = 1.0      # m: a gap between a track's records at a node up to this lets its points near the node move by it
GAP_REACH = 5.0    # m around such a node
THIN = 0.003       # m: the written points leave out samples a chord passes within this of
THIN_MAX = 10.0    # m: at most this far apart
KEEP = 2.5         # m from an edge's ends where every sample is kept
ROUNDS = 40        # reweighting rounds per fit
WIDEN = 8          # rounds of widening the tolerance where the curve bends too tight


def _solve(d0, d1, d2, rhs):
    """A symmetric positive definite pentadiagonal system (diagonal d0, first and second sub-diagonals d1, d2) for
    several right-hand sides, by LDL^T."""
    n = len(d0)
    D, l1, l2 = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(n):
        di = d0[i]
        if i >= 2:
            l2[i] = d2[i - 2] / D[i - 2]
            di -= l2[i] * l2[i] * D[i - 2]
        if i >= 1:
            l1[i] = (d1[i - 1] - (l2[i] * l1[i - 1] * D[i - 2] if i >= 2 else 0.0)) / D[i - 1]
            di -= l1[i] * l1[i] * D[i - 1]
        D[i] = di
    out = []
    for b in rhs:
        z = list(b)
        for i in range(1, n):
            z[i] -= l1[i] * z[i - 1] + (l2[i] * z[i - 2] if i >= 2 else 0.0)
        for i in range(n):
            z[i] /= D[i]
        for i in range(n - 2, -1, -1):
            z[i] -= l1[i + 1] * z[i + 1] + (l2[i + 2] * z[i + 2] if i + 2 < n else 0.0)
        out.append(z)
    return out


def nearest(px, py, lo, hi, q):
    """The point of the sampled curve (px, py) between samples lo and hi nearest q: (distance, segment, t)."""
    best = (math.inf, max(0, min(lo, len(px) - 2)), 0.0)
    for s in range(max(0, lo), min(len(px) - 1, hi)):
        dx, dy = px[s + 1] - px[s], py[s + 1] - py[s]
        t = max(0.0, min(1.0, ((q[0] - px[s]) * dx + (q[1] - py[s]) * dy) / (dx * dx + dy * dy or 1e-12)))
        d = math.hypot(px[s] + t * dx - q[0], py[s] + t * dy - q[1])
        if d < best[0]:
            best = (d, s, t)
    return best


def radii(px, py, half=2.5):
    """The radius at every sample over a 5 m window: the circle through the curve's points `half` either side (as
    tools/lint.js trackRadius measures the drawn track)."""
    n = len(px)
    cum = [0.0]
    for i in range(1, n):
        cum.append(cum[-1] + math.hypot(px[i] - px[i - 1], py[i] - py[i - 1]))
    out, j0, j1 = [math.inf] * n, 0, 0
    for i in range(n):
        while j0 + 1 <= i and cum[i] - cum[j0 + 1] >= half:
            j0 += 1
        j1 = max(j1, i)
        while j1 < n - 1 and cum[j1] - cum[i] < half:
            j1 += 1
        # (near an end, what the track has on that side, from 0.2 m: a branch starts with its tightest bend)
        if cum[i] - cum[j0] < min(half * 0.99, max(0.2, cum[i])) or cum[j1] - cum[i] < min(half * 0.99, max(0.2, cum[-1] - cum[i])):
            continue
        if cum[i] - cum[j0] < 0.2 or cum[j1] - cum[i] < 0.2:
            continue
        ax, ay, bx, by, cx, cy = px[j0], py[j0], px[i], py[i], px[j1], py[j1]
        area2 = abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))
        if area2 > 1e-12:
            out[i] = math.hypot(bx - ax, by - ay) * math.hypot(cx - bx, cy - by) * math.hypot(ax - cx, ay - cy) / (2 * area2)
    return out


def class_errors(truth=None):
    """{accuracy class: mean coordinate error in metres} (data/truth.json `sourceAccuracy`, the decree's table)."""
    import json
    path = truth or Path(__file__).resolve().parent.parent / 'data' / 'truth.json'
    return {k: v['mxy'] * SIGMAS for k, v in json.loads(Path(path).read_text(encoding='utf-8'))['sourceAccuracy']['classes'].items()}


def fit(pts, tol, fixed=None, heading=None, step=STEP, limit=None):
    """A smooth curve through polyline `pts` within `tol` of each of its points (None: not data). `fixed`
    {point index: (x, y)} holds positions; `heading` {point index: (ux, uy)} holds the direction the curve leaves
    that (fixed, end) point in, into the polyline; `limit` per point: how far its tolerance may grow where the curve
    would bend tighter than MIN_RADIUS (default: as far as it starts). Returns (samples, each point's sample index,
    the final tolerance per point, the radius per sample over 2 m). A point's miss is its distance to the curve (the
    samples slide along it)."""
    fixed, heading = fixed or {}, heading or {}
    xs, ys, at = [], [], []
    for i, p in enumerate(pts):
        if i:
            a = pts[i - 1]
            m = max(1, math.ceil(math.dist(a, p) / step))
            for j in range(1, m):
                xs.append(a[0] + (p[0] - a[0]) * j / m)
                ys.append(a[1] + (p[1] - a[1]) * j / m)
        at.append(len(xs))
        xs.append(p[0])
        ys.append(p[1])
    n = len(xs)
    u = [0.0]
    for i in range(1, n):
        u.append(u[-1] + max(1e-6, math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])))
    tol = list(tol)
    limit = list(limit) if limit is not None else list(tol)
    # held samples: fixed points, and the sample next to a fixed end along its heading
    held = {at[i]: q for i, q in fixed.items()}
    for i, (hx, hy) in heading.items():
        s = at[i]
        nxt = s + 1 if i == 0 else s - 1   # (an end: the first point or the last)
        if not 0 <= nxt < n:
            continue
        h = abs(u[nxt] - u[s])
        p0 = held.get(s, (xs[s], ys[s]))
        held[nxt] = (p0[0] + hx * h, p0[1] + hy * h)
    weight = [0.0] * n
    for i, t in enumerate(tol):
        if t is not None and at[i] not in held:
            weight[at[i]] = 1.0 if t <= TOL + 1e-9 else FILL_WEIGHT
    rows = []   # k_i = a p[i-1] + b p[i] + c p[i+1], the curvature vector at sample i, and its length of track
    for i in range(1, n - 1):
        h0, h1 = u[i] - u[i - 1], u[i + 1] - u[i]
        a, c = 2 / ((h0 + h1) * h0), 2 / ((h0 + h1) * h1)
        rows.append((a, -(a + c), c, (h0 + h1) / 2))
    d0, d1, d2 = [0.0] * n, [0.0] * max(0, n - 1), [0.0] * max(0, n - 2)
    for j, (a, b, c, l) in enumerate(rows):
        i, w = j + 1, LAMBDA * l
        d0[i - 1] += w * a * a
        d0[i] += w * b * b
        d0[i + 1] += w * c * c
        d1[i - 1] += w * a * b
        d1[i] += w * b * c
        d2[i - 1] += w * a * c
    tx, ty = list(xs), list(ys)
    for s, q in held.items():
        tx[s], ty[s] = q

    def solve():
        w = [weight[i] + (FIX if i in held else 0.0) for i in range(n)]
        if n < 3:
            return tx, ty
        return _solve([d0[i] + w[i] for i in range(n)], d1, d2, [[w[i] * tx[i] for i in range(n)], [w[i] * ty[i] for i in range(n)]])

    data = [i for i, t in enumerate(tol) if t is not None and at[i] not in held]
    px, py = solve()
    if n < 3 or not data:
        return list(zip(px, py)), at, tol, radii(px, py, BEND)
    for _ in range(WIDEN):
        for _ in range(ROUNDS):
            worst = 1.0
            for i in data:
                s = at[i]
                miss = nearest(px, py, s - 3, s + 3, (xs[s], ys[s]))[0] / tol[i]
                if miss > 1.0:
                    weight[s] *= min(100.0, miss * miss)
                    worst = max(worst, miss)
            if worst < 1.02:
                break
            px, py = solve()
        r = radii(px, py, BEND)
        tight = [u[i] for i in range(n) if r[i] < MIN_RADIUS * SLACK]
        grow = [i for i in data if tol[i] < limit[i] - 1e-9 and any(abs(u[at[i]] - t) <= NEAR for t in tight)]
        if not grow:
            break
        for i in grow:
            tol[i] = min(limit[i], tol[i] * GROW)
            weight[at[i]] = 1.0
        px, py = solve()
    return list(zip(px, py)), at, tol, radii(px, py, BEND)


def crossing_point(px, py, s, qx, qy, r, reach=12):
    """Where curve (px, py) near its sample s crosses curve (qx, qy) near its sample r: ((x, y), (segment of the
    second, t)), or None."""
    best = None
    for i in range(max(0, s - reach), min(len(px) - 1, s + reach)):
        ax, ay, bx, by = px[i], py[i], px[i + 1], py[i + 1]
        for j in range(max(0, r - reach), min(len(qx) - 1, r + reach)):
            cx, cy, dx, dy = qx[j], qy[j], qx[j + 1], qy[j + 1]
            den = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
            if abs(den) < 1e-12:
                continue
            u = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / den
            v = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / den
            if 0 <= u <= 1 and 0 <= v <= 1:
                d = abs(i - s) + abs(j - r)
                if best is None or d < best[0]:
                    best = (d, (ax + u * (bx - ax), ay + u * (by - ay)), (j, v))
    return best and best[1:]


def thin(pts):
    """Points without the samples a chord passes within THIN of, at most THIN_MAX apart; every sample within
    KEEP of either end (where tracks meet, tools/lint.js trackJoins reads the direction over 2 m)."""
    if len(pts) <= 2:
        return list(pts)
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    out, last = [pts[0]], 0
    for i in range(1, len(pts) - 1):
        if cum[i] < KEEP or cum[-1] - cum[i] < KEEP:
            out.append(pts[i])
            last = i
            continue
        a, b = pts[last], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy) or 1e-9
        if l > THIN_MAX or any(abs((pts[j][0] - a[0]) * dy - (pts[j][1] - a[1]) * dx) / l > THIN for j in range(last + 1, i + 1)):
            out.append(pts[i])
            last = i
    out.append(pts[-1])
    return out


class Network:
    """The fitted track graph. pos {node: (x, y)}, pts {(a, b): points from a to b} keyed as tools/di_tracks.py
    keys its edges (a before b as strings), kind {(a, b): 'di' | 'dtmp' | 'osm'}, `loose` {(node, edge)}: a node off
    the surveyed track its edge runs on (no data point for it: the point nearest all of a node's tracks), `limit`
    {(a, b): metres} how far a surveyed edge's points may move where a curve would bend too tight (the mean coordinate
    error of its records' accuracy class; default the class UNCLASSED). After construction: `pos` and
    `pts` fitted, `report` (counts, the largest misses and the curves left tighter than MIN_RADIUS, with places)."""

    def __init__(self, pos, pts, kind, loose=(), limit=None):
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        # nodes joined by an edge under MERGE are one (a switch's node and a neighbour moved onto one fork; two nodes
        # 4 cm apart at Národní divadlo, each fitted onto another track, would join with a 0.2 m radius)
        root = {n: n for n in pos}

        def find(n):
            while root[n] != n:
                root[n] = root[root[n]]
                n = root[n]
            return n
        for (a, b), p in pts.items():
            if sum(math.dist(x, y) for x, y in zip(p, p[1:])) < MERGE:
                root[find(a)] = find(b)
        errors = class_errors()
        adj, edges = defaultdict(set), {}
        for (a, b), p in pts.items():
            ra, rb = find(a), find(b)
            if ra != rb:
                key = k(ra, rb)
                src = kind.get((a, b), 'osm')
                lim = (limit or {}).get((a, b)) or errors[UNCLASSED] if src in ('di', 'dtmp') else FILL_LIMIT
                edges[key] = (list(p) if key == (ra, rb) else list(p[::-1]), src, lim)
                adj[ra].add(rb)
                adj[rb].add(ra)
        loose = {(find(n), k(find(a), find(b))): (loose[(n, (a, b))] if isinstance(loose, dict) else 0.5) for n, (a, b) in loose}

        def along(n, m):
            p = edges[k(n, m)][0]
            return p if k(n, m)[0] == n else p[::-1]

        def direction(n, m):
            p, d, q = along(n, m), 0.0, None
            for a, b in zip(p, p[1:]):
                d += math.dist(a, b)
                q = b
                if d >= LOOK:
                    break
            l = math.dist(p[0], q) or 1.0
            return ((q[0] - p[0][0]) / l, (q[1] - p[0][1]) / l)

        # at every node the straightest pairs of edges continue each other
        pair = {}
        for n, ms in adj.items():
            ms = list(ms)
            dirs = {m: direction(n, m) for m in ms}
            limit = PAIR_TWO if len(ms) == 2 else PAIR
            cands = []
            for i, a in enumerate(ms):
                for b in ms[:i]:
                    dev = math.degrees(math.acos(max(-1.0, min(1.0, -(dirs[a][0] * dirs[b][0] + dirs[a][1] * dirs[b][1])))))
                    if dev < limit:
                        cands.append((dev, a, b))
            for _, a, b in sorted(cands, key=lambda c: c[0]):
                if (n, a) not in pair and (n, b) not in pair:
                    pair[(n, a)], pair[(n, b)] = b, a
        used, chains = set(), []
        for key in edges:
            if key in used:
                continue
            used.add(key)
            seq = list(key)
            for forward in (True, False):
                while True:
                    end, prev = (seq[-1], seq[-2]) if forward else (seq[0], seq[1])
                    nxt = pair.get((end, prev))
                    if nxt is None or k(end, nxt) in used:
                        break
                    used.add(k(end, nxt))
                    if forward:
                        seq.append(nxt)
                    else:
                        seq.insert(0, nxt)
            chains.append(seq)
        length = lambda seq: sum(math.dist(x, y) for a, b in zip(seq, seq[1:]) for x, y in zip(along(a, b), along(a, b)[1:]))
        chains.sort(key=lambda s: -length(s))
        # longest first, but a track passing through a node before a track ending there: the one through it fixes it
        # (Holešovice: a longer track ending at a node 2 m off its own line fixed it, and the track through it bent
        # at 4 m to reach it)
        through = defaultdict(set)
        for c, seq in enumerate(chains):
            for n in seq[1:-1]:
                through[n].add(c)
        order, done, left = [], set(), list(range(len(chains)))
        while left:
            c = next((c for c in left if all(through[n] <= done | {c} for n in (chains[c][0], chains[c][-1]))), left[0])
            order.append(c)
            done.add(c)
            left.remove(c)
        chains = [chains[c] for c in order]

        # node -> {'pos', 'dirs': directions of the tracks through it, 'at': [(track, index in its seq)]}
        node, fitted, misses, tight, widened = {}, [], [], [], 0
        for c, seq in enumerate(chains):
            # the points and their tolerance: a node off its surveyed tracks is no data point (the point nearest
            # all of them: 0.2 m off each at a junction at Národní divadlo, where the tracks run 1.3 m apart); the
            # longer track fixes it, the shorter one passes through. A node on them is (a crossing point stands in
            # for DI's vertex at a 5° bend, Strossmayerovo náměstí)
            pts_c, tol, lim, node_at = [], [], [], []
            for i, (a, b) in enumerate(zip(seq, seq[1:])):
                line, src, l = along(a, b), edges[k(a, b)][1], edges[k(a, b)][2]
                t = TOL if src in ('di', 'dtmp') else FILL_TOL
                if i == 0:
                    pts_c.append(line[0])
                    tol.append(None if t == TOL and (a, k(a, b)) in loose else t)
                    lim.append(l)
                    node_at.append(0)
                else:
                    lim[-1] = min(lim[-1], l)   # (a node between two edges: the stricter limit)
                    if t == TOL:
                        tol[-1] = None if tol[-1] is None or (a, k(a, b)) in loose else TOL
                for q in line[1:-1]:
                    pts_c.append(q)
                    tol.append(t)
                    lim.append(l)
                pts_c.append(line[-1])
                tol.append(None if t == TOL and (b, k(a, b)) in loose else t)
                lim.append(l)
                node_at.append(len(pts_c) - 1)
            # where this track's records meet with a gap at a node (a branch DI starts 0.21 m off the through track's
            # line, Strossmayerovo náměstí), its points within GAP_REACH of it may move by the gap besides their class
            for j, n in enumerate(seq):
                gap = max([loose.get((n, k(n, m)), 0.0) for m in (seq[j - 1] if j else None, seq[j + 1] if j + 1 < len(seq) else None)
                           if m is not None and edges[k(n, m)][1] in ('di', 'dtmp')] or [0.0])
                if 0.0 < gap <= GAP_MAX:
                    i0 = node_at[j]
                    for i in range(len(pts_c)):
                        if math.dist(pts_c[i], pts_c[i0]) <= GAP_REACH:
                            lim[i] = max(lim[i], min(lim[i], errors[UNCLASSED]) + gap)

            def own(j):
                """This track's direction at its j-th node, from its points LOOK either side."""
                i0 = node_at[j]
                a = next((pts_c[i] for i in range(i0, -1, -1) if math.dist(pts_c[i], pts_c[i0]) >= LOOK), pts_c[0])
                b = next((pts_c[i] for i in range(i0, len(pts_c)) if math.dist(pts_c[i], pts_c[i0]) >= LOOK), pts_c[-1])
                l = math.dist(a, b) or 1.0
                return ((b[0] - a[0]) / l, (b[1] - a[1]) / l)

            def angle(d, dirs):
                return min((math.degrees(math.acos(min(1.0, abs(d[0] * t[0] + d[1] * t[1])))) for t in dirs), default=90.0)
            # nodes fitted before are held, except a crossing (this track passes a node another passes at an angle):
            # it slides to where the two curves cross (the node's position is the point nearest all its tracks,
            # 0.4 m off the long track at Strossmayerovo náměstí, where the crossing track ran through it)
            # (only while the track that fixed it is its only one: a track ending there holds it.) A node off this
            # track's line where it crosses tracks fitted before keeps the node; this track crosses them at its own
            # point (OSM joins two crossings 0.65 m apart in one node at Strossmayerovo náměstí)
            fixed, crossing, private = {}, [], []
            for j, n in enumerate(seq):
                if n not in node:
                    continue
                inner = 0 < j < len(seq) - 1 and all(0 < jj < len(chains[cc]) - 1 for cc, jj in node[n]['at'])
                crosses = 0 < j < len(seq) - 1 and angle(own(j), node[n]['dirs']) > CROSS
                if inner and crosses and len(node[n]['at']) == 1 and not node[n].get('off'):
                    crossing.append(j)
                elif crosses and tol[node_at[j]] is None and any(0 < jj < len(chains[cc]) - 1 for cc, jj in node[n]['at']):
                    private.append(j)
                else:
                    fixed[node_at[j]] = node[n]['pos']
            # points within CLEAR of an end a track fitted before holds say no more than that node: they stand for
            # its old position (Strossmayerovo náměstí: DI's record end 0.1 m from where the node landed bent the
            # branch 64° in its first 0.1 m)
            for j, inward in ((0, 1), (len(seq) - 1, -1)):
                if seq[j] in node:
                    i, i0 = node_at[j] + inward, node_at[j]
                    while 0 <= i < len(pts_c) and math.dist(pts_c[i], pts_c[i0]) < CLEAR:
                        tol[i] = None
                        i += inward
            # a track continuing one fitted before (a diverging track, a track's end at a joint) leaves along the
            # track through the node nearest its own direction (a node of a crossing and a switch at Strossmayerovo
            # náměstí: the first track through it lay 11° off the one the branch leaves)
            heading = {}
            for j, inward in ((0, 1), (len(seq) - 1, -1)):
                n = seq[j]
                if n not in node or (j and seq[0] == seq[-1]) or len(pts_c) < 2 or length(seq) < 2 * STEP:
                    continue
                d = own(j)
                d = (d[0] * inward, d[1] * inward)
                t0 = max(node[n]['dirs'], key=lambda t: abs(d[0] * t[0] + d[1] * t[1]))
                dot = d[0] * t0[0] + d[1] * t0[1]
                if abs(dot) >= math.cos(math.radians(START)):
                    sg = 1 if dot > 0 else -1
                    heading[node_at[j]] = (sg * t0[0], sg * t0[1])
            samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim)
            px, py = [q[0] for q in samples], [q[1] for q in samples]
            for j in crossing:
                n = seq[j]
                oc, oj = next((cc, jj) for cc, jj in node[n]['at'] if 0 < jj < len(chains[cc]) - 1)
                other = fitted[oc]
                hit = crossing_point(px, py, at[node_at[j]], other['px'], other['py'], other['cut'][oj][0])
                if hit is None:   # (the curves do not cross near it: hold it after all)
                    fixed[node_at[j]] = node[n]['pos']
                    samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim)
                    px, py = [q[0] for q in samples], [q[1] for q in samples]
                    continue
                q, (s_o, t_o) = hit
                node[n]['pos'] = q
                other['cut'][oj] = (s_o, t_o)
            own_point = {}
            for j in private:
                n = seq[j]
                hit = None
                for oc, oj in node[n]['at']:
                    if 0 < oj < len(chains[oc]) - 1:
                        hit = crossing_point(px, py, at[node_at[j]], fitted[oc]['px'], fitted[oc]['py'], fitted[oc]['cut'][oj][0])
                        if hit:
                            break
                if hit is None:   # (no crossing near it: hold the node after all)
                    fixed[node_at[j]] = node[n]['pos']
                    samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim)
                    px, py = [q[0] for q in samples], [q[1] for q in samples]
                    own_point.clear()
                    continue
                own_point[j] = hit[0]
            # each node where the curve passes nearest its position (the samples slide along the curve); a node
            # fitted before where it is
            cut = []
            for j, n in enumerate(seq):
                s = at[node_at[j]]
                _, seg, t = nearest(px, py, s - 10, s + 10, own_point[j] if j in own_point else
                                    node[n]['pos'] if n in node else pts_c[node_at[j]])
                if cut and (seg, t) < cut[-1]:
                    seg, t = cut[-1]
                if n not in node:
                    q = (px[seg] + t * (px[seg + 1] - px[seg]), py[seg] + t * (py[seg + 1] - py[seg])) if len(px) > 1 else samples[0]
                    if tol[node_at[j]] is None and any((n, k(n, m)) in loose for m in (seq[j - 1] if j else None,
                                                       seq[j + 1] if j + 1 < len(seq) else None) if m is not None):
                        # (a node off this track's line: it stays where it is, the track crosses at its own point;
                        # the long track fixing it would move it off the tracks that do pass through it)
                        node[n] = {'pos': tuple(pts_c[node_at[j]]), 'dirs': [], 'at': [], 'off': True}
                        own_point[j] = q
                    else:
                        node[n] = {'pos': q, 'dirs': [], 'at': []}
                cut.append((seg, t))
                a, b = samples[max(0, seg - (t == 0.0 and seg > 0))], samples[min(len(samples) - 1, seg + 1)]
                l = math.dist(a, b) or 1.0
                node[n]['dirs'].append(((b[0] - a[0]) / l, (b[1] - a[1]) / l))
                node[n]['at'].append((c, j))
            fitted.append({'px': px, 'py': py, 'cut': cut, 'own': own_point})
            for i, p in enumerate(pts_c):
                if tol[i] is None or tol[i] > TOL + 1e-9:
                    continue
                widened += tol_out[i] > tol[i] + 1e-9
                d, seg, t = nearest(px, py, at[i] - 3, at[i] + 3, p)
                if d > TOL + REPORT:
                    misses.append({'m': round(d, 3), 'xy': [round(p[0], 1), round(p[1], 1)], 'widened': tol_out[i] > tol[i] + 1e-9})
            for i, r in enumerate(rad):
                if r < MIN_RADIUS * SLACK:
                    tight.append({'radius_m': round(r, 1), 'xy': [round(px[i], 1), round(py[i], 1)]})
        # the edges: each track's samples between its nodes' cuts, ending at the nodes' final positions
        out_pts = {}
        for seq, f in zip(chains, fitted):
            px, py, cut = f['px'], f['py'], f['cut']
            for j, (a, b) in enumerate(zip(seq, seq[1:])):
                p0, p1 = f['own'].get(j, node[a]['pos']), f['own'].get(j + 1, node[b]['pos'])
                piece = [p0]
                for i in range(cut[j][0] + 1, cut[j + 1][0] + 1):
                    if math.dist((px[i], py[i]), piece[-1]) > 1e-3 and math.dist((px[i], py[i]), p1) > 1e-3:
                        piece.append((px[i], py[i]))
                piece.append(p1)
                out_pts[k(a, b)] = piece if k(a, b) == (a, b) else piece[::-1]
        self.pos = {n: node[find(n)]['pos'] if find(n) in node else p for n, p in pos.items()}
        self.pts = {}
        for (a, b) in pts:
            ra, rb = find(a), find(b)
            if ra == rb:
                self.pts[(a, b)] = [self.pos[a], self.pos[b]]
                continue
            piece = out_pts[k(ra, rb)]
            self.pts[(a, b)] = thin([tuple(q) for q in (piece if k(ra, rb) == (ra, rb) else piece[::-1])])
        self.report = {'through_tracks': len(chains), 'points_widened': widened, 'missed_over_cm': len(misses),
                       'missed_unwidened': sum(not m['widened'] for m in misses),
                       'misses': self._places(misses, 'm', -1)[:15],
                       'tighter_than_min_radius': self._places(tight, 'radius_m', 1)[:15]}

    @staticmethod
    def _places(items, key, sign):
        """One place per 20 m, the worst first."""
        out = []
        for it in sorted(items, key=lambda x: sign * x[key]):
            if all(math.dist(it['xy'], o['xy']) > 20 for o in out):
                out.append(it)
        return out


def main():
    import glob
    import json
    import time
    import di_tracks as dt
    from geo import Frame
    line = sys.argv[sys.argv.index('--line') + 1] if '--line' in sys.argv else '17'
    root = Path(__file__).resolve().parent.parent
    raw = root / 'raw' / f'line{line}'
    answers = [json.loads(Path(f).read_text(encoding='utf-8')) for f in [raw / 'tracks.json', *glob.glob(str(raw / 'route_*.json'))]]
    nodes, edges = dt.osm_graph(*answers)
    frame = Frame()
    ids = list(nodes)
    x, y = frame.xy([nodes[i][0] for i in ids], [nodes[i][1] for i in ids])
    pos = {i: (float(a), float(b)) for i, a, b in zip(ids, x, y)}
    t0 = time.time()
    geo = dt.TrackGeometry(pos, edges, dt.load_sources())
    t1 = time.time()
    geo.fit_curves()
    print(f'track geometry: {t1 - t0:.0f} s, curves {time.time() - t1:.0f} s')
    r = geo.report['curve']
    print({k: v for k, v in r.items() if not isinstance(v, list)})
    for key in ('misses', 'tighter_than_min_radius'):
        print(f'{key}:')
        for x in r[key]:
            lat, lon = frame.ll(*x['xy'])
            print(f"  {x.get('m', x.get('radius_m'))}  {float(lat):.5f} N {float(lon):.5f} E  {x['xy']}")


if __name__ == '__main__':
    main()
