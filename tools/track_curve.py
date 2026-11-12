# SPDX-License-Identifier: AGPL-3.0-or-later
"""The drawn track in plan as smooth curves through the surveyed points, continuous in direction at every node (#204).

    python -P -E tools/track_curve.py --line 17     # fit the DI edges line 17's routes run on, print what moved and what was left

The track graph's edges (tools/di_network.py `Drawn`) are polylines through DI's points, or the orthophoto's
(data/truth.json photoTracks), or OSM's where DI has no track (fill). They are joined into through tracks: at every node the
straightest pair of edges continues (a switch's diverging edge, a track's end and a crossing track end or pass
there). Each through track, longest first, is fitted with a curve that bends as little as it can (a penalised
spline in plan, bending energy on 1 m samples) while it stays within TOL of every surveyed point (FILL_TOL of fill):
the points' weights grow only where the curve misses (Lawson's reweighting). A node a longer track already fixed
keeps its position (a track through a node is fitted before one ending there), and its direction where this track
continues that one (a diverging track leaves tangent to
the through track: data/truth.json trackGeometry `switch-start`, most switches are tangential). Where the curve
bends too tight, read at two scales (`tight_at`: 18 m over 5 m as tools/lint.js reads it, data/truth.json
`min-radius-network`; KINK_RADIUS over 2 m for a bend squeezed into a metre), the tolerance of the points around it
grows by GROW up to the mean coordinate error of their records' accuracy class (data/truth.json `sourceAccuracy`: 0.14 m
for DI's class 3). Where it still bends too tight the curve stiffens there and its points may move past their
class, at most to HOLD_LIMIT, and each such place is listed with how far its points moved (the cost). A point the
curve still misses by more than TOL + REPORT is listed, and so is a curve left tight.

A Gaussian (the client's old smoothing, src/route.js) cuts inside a curve: 0.2 m on an 18 m curve with the 6 m
window (#20); a curve held to the points does not.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def geometry_fact(fact_id, truth=None):
    """A value of data/truth.json trackGeometry, read where it is used instead of copied (#224)."""
    import json
    truth = truth or json.loads((Path(__file__).resolve().parent.parent / 'data' / 'truth.json').read_text(encoding='utf-8'))
    return next(f['value'] for f in truth['trackGeometry']['facts'] if f['id'] == fact_id)


TOL = 0.02        # m: the curve within this of every surveyed point (DI, the archive)
FILL_TOL = 0.3     # m: of OSM's nodes where neither has the track
PHOTO_TOL = 0.05   # m: of track centres measured on the orthophoto (Podolská vodárna: 1.6-2.7 cm rms about a smooth
                   # curve; held within TOL the curve followed that scatter, 10 m over 2 m)
SURVEYED = ('di', 'dtmp', 'ortho')   # sources whose points the curve keeps within TOL (ortho: data/truth.json photoTracks)
UNCLASSED = '3'    # the accuracy class of surveyed records that state none (the archive): the DTM's own minimum
                   # (data/truth.json `sourceAccuracy`, the decree's § 3 odst. 7)
FILL_LIMIT = 0.5   # m: a fill point's tolerance grows at most to this (OSM against DI: p90 0.45 m at line 17's nodes)
SIGMAS = 1.0       # a point moves at most this many mean errors of its class (the decree states the mean error, no
                   # limit; 2 on line 17: 6 bends over 10° inside tracks instead of 11, 32 joins over 1° instead of 39)
GROW = 1.5         # the factor the tolerance grows by per round
MIN_RADIUS = float(geometry_fact('min-radius-network'))  # m, 18: the radius a curve is held to over BEND_LONG (`min-radius-network`:
                   # the user, "under 18m there shouldn't be anything like that"; `min-radius-passenger` says 20, but at
                   # 20 the fit moved DI's points up to 14 cm in curves DI draws at 18-20 m, all over the city)
KINK_RADIUS = 15.0 # m: the radius over BEND: a shorter window sees a bend squeezed into a metre, a longer one averages it
                   # out; a sagitta of 3.3 cm, so that most of the scatter within TOL stays below it
NETWORK_RADIUS = MIN_RADIUS  # m: under this the curve stiffens and its points may move past their class (HOLD_LIMIT)
HOLD_LIMIT = 0.5   # m: past its class's error a point moves at most this far to hold NETWORK_RADIUS
STIFFEN, STIFF_MAX = 1.5, 1.5 ** 12  # the bending weight's factor per round where the curve bends under it, and its
                                     # most (x4 at once took a 15° corner to 49 m, its points 0.49 m off; x1.5: 18.2 m, 9 cm)
SLACK = 0.995      # a curve held at MIN_RADIUS reads a few millimetres under it
BEND = 1.0         # m either side of a sample for the short radius (a 5 m window reads a 10° bend squeezed into a
                   # metre as 29 m)
BEND_LONG = 2.5    # m either side for the long radius (as tools/lint.js trackRadius; over 2 m a scatter of 2 cm alone
                   # reads as 25 m)
NEAR = 10.0        # m around a place bending too tight whose points' tolerance grows
CORNER = 0.5       # degrees: the sample a heading holds may turn this much more than the next CORNER_REACH of the curve
                   # (at 1° a branch leaving at 42 m off a through track at 120 m kept a 1.53° vertex, line 22 by
                   # 4400.9, -2364.8; at 0.5° the five lines' isolated corners fall a further third, every point in its class)
                   # bends at its rate; beyond it the turn is a corner and the points near it ease off within their class
                   # (line 9 s 15958, a trailing switch past Flora: 4.5° in its first metre, then 0.3°). A limit on the
                   # radius there instead (27 m, #477) forbade a switch curving at 18-20 m from its blade, as at Národní
                   # divadlo, and squeezed the turn into a 13 m bend further on
CORNER_REACH = 2.0 # m
BEHIND = BEND_LONG + 1.0  # m of the track fitted before that the windows near a held end read on into
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
PAIR_LOOK = 10.0   # m along an edge, on through the next nodes straightest first, for which edges continue each other:
                   # over LOOK a tangential switch's branch is still 9 cm off (Strossmayerovo náměstí, its eastern
                   # track: the turn read 0.1° straighter than the straight, which DI bends 0.9° there, and the
                   # straight was fitted as the branch, swinging ±8 cm); over 10 m the turn is 1.04 m off
CROSS = 10.0       # degrees: two tracks passing one node at more than this cross there (else they touch)
MERGE = 0.5        # m: nodes joined by a shorter edge are one
CLEAR = 0.5        # m from an end node held by a track fitted before: no data points
GAP_MAX = 1.0      # m: a gap between a track's records at a node up to this lets its points near the node move by it
GAP_REACH = 5.0    # m around such a node
OFF = 0.2          # m: a node off a track through it by more than this, where three edges meet, keeps its place and
                   # the track passes at its own point (Národní divadlo 0.34 m); a switch this near its track joins it
                   # exactly (Čechův most 2 cm: the route broke there). DI's branches start up to 0.18 m apart at a
                   # fork: at 0.1 m Strossmayerovo náměstí's crossover branches began 0.15-0.17 m beside their
                   # through tracks, which broke 1.2-1.3° there
THIN = 0.003       # m: the written points leave out samples a chord passes within this of
THIN_MAX = 10.0    # m: at most this far apart
KEEP = 2.5         # m from an edge's ends where every sample is kept
ROUNDS = 40        # reweighting rounds per fit
WIDEN = 24         # rounds of widening the tolerance where the curve bends too tight (5 reach DI's class from TOL),
                   # then of stiffening it under NETWORK_RADIUS


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


def tight_at(px, py):
    """The equivalent radius per sample for the limits: the long window's, or the short window's scaled so that
    KINK_RADIUS over BEND reads as NETWORK_RADIUS over BEND_LONG."""
    short, long_ = radii(px, py, BEND), radii(px, py, BEND_LONG)
    f = NETWORK_RADIUS / KINK_RADIUS
    return [min(l, s * f) for s, l in zip(short, long_)]


def corner_excess(px, py, s, inward):
    """Degrees by which sample s turns more than the curve after it, inward (+1 or -1) from s, over CORNER_REACH turns at
    that rate per metre: a corner where a held heading meets the points."""
    def turn(i):
        a, b, c = (px[i - 1], py[i - 1]), (px[i], py[i]), (px[i + 1], py[i + 1])
        d = math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0])
        return (d + math.pi) % (2 * math.pi) - math.pi
    if not 0 < s < len(px) - 1:
        return 0.0
    here = turn(s)
    rate, run, i = 0.0, 0.0, s + inward
    while 0 < i < len(px) - 1 and run < CORNER_REACH:
        rate += turn(i)
        run += math.dist((px[i], py[i]), (px[i - inward], py[i - inward]))
        i += inward
    if run <= 0:
        return 0.0
    seg = (math.dist((px[s - 1], py[s - 1]), (px[s], py[s])) + math.dist((px[s], py[s]), (px[s + 1], py[s + 1]))) / 2
    expect = rate / run * seg
    return math.degrees(abs(here - expect)) if here * expect >= 0 or abs(here) > abs(expect) else 0.0

def tight_with(px, py, behind):
    """tight_at with the track beyond each end: behind {0 or n-1: points going outward from that end, nearest first} (the
    track fitted before that this one leaves or continues). Without it the windows near an end reach only the end on one
    side: easing a branch off its switch at Národní divadlo bent it 14.5 m over 5 m 2 m from the node, unseen."""
    n = len(px)
    head = list(reversed(behind.get(0, ())))
    tail = list(behind.get(n - 1, ()))
    if not head and not tail:
        return tight_at(px, py)
    r = tight_at([q[0] for q in head] + list(px) + [q[0] for q in tail], [q[1] for q in head] + list(py) + [q[1] for q in tail])
    return r[len(head):len(head) + n]


def class_errors(truth=None):
    """{accuracy class: mean coordinate error in metres} (data/truth.json `sourceAccuracy`, the decree's table)."""
    import json
    path = truth or Path(__file__).resolve().parent.parent / 'data' / 'truth.json'
    return {k: v['mxy'] * SIGMAS for k, v in json.loads(Path(path).read_text(encoding='utf-8'))['sourceAccuracy']['classes'].items()}


def fit(pts, tol, fixed=None, heading=None, step=STEP, limit=None, behind=None):
    """A smooth curve through polyline `pts` within `tol` of each of its points (None: not data). `fixed`
    {point index: (x, y)} holds positions; `heading` {point index: (ux, uy)} holds the direction the curve leaves
    that (fixed, end) point in, into the polyline; `limit` per point: how far its tolerance may grow where the curve
    would bend tighter than MIN_RADIUS (default: as far as it starts); where it still bends tighter than
    NETWORK_RADIUS the curve stiffens there and its points may move up to HOLD_LIMIT. Returns (samples, each point's sample index, the final tolerance per point,
    the radius per sample over 2 m). `behind` {point index of an end: the points of the track beyond it, going out}: the
    radius windows near that end read on into it. A point's miss is its distance to the curve (the
    samples slide along it)."""
    fixed, heading, behind = fixed or {}, heading or {}, behind or {}
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
    hinges = []   # (sample a heading holds, inward): the curve turns there from the held direction to its points
    for i, (hx, hy) in heading.items():
        s = at[i]
        nxt = s + 1 if i == 0 else s - 1   # (an end: the first point or the last)
        if not 0 <= nxt < n:
            continue
        h = abs(u[nxt] - u[s])
        p0 = held.get(s, (xs[s], ys[s]))
        held[nxt] = (p0[0] + hx * h, p0[1] + hy * h)
        if 0 < nxt < n - 1:
            hinges.append((nxt, 1 if i == 0 else -1))
    beyond = {at[i]: q for i, q in behind.items() if at[i] in (0, n - 1) and q}
    weight = [0.0] * n
    for i, t in enumerate(tol):
        if t is not None and at[i] not in held:
            weight[at[i]] = 1.0 if t <= TOL + 1e-9 else FILL_WEIGHT
    rows = []   # k_i = a p[i-1] + b p[i] + c p[i+1], the curvature vector at sample i, and its length of track
    for i in range(1, n - 1):
        h0, h1 = u[i] - u[i - 1], u[i + 1] - u[i]
        a, c = 2 / ((h0 + h1) * h0), 2 / ((h0 + h1) * h1)
        rows.append((a, -(a + c), c, (h0 + h1) / 2))
    stiff = [1.0] * len(rows)   # the bending weight's factor per sample, raised where the curve bends under 18 m

    def bending():
        d0, d1, d2 = [0.0] * n, [0.0] * max(0, n - 1), [0.0] * max(0, n - 2)
        for j, (a, b, c, l) in enumerate(rows):
            i, w = j + 1, LAMBDA * l * stiff[j]
            d0[i - 1] += w * a * a
            d0[i] += w * b * b
            d0[i + 1] += w * c * c
            d1[i - 1] += w * a * b
            d1[i] += w * b * c
            d2[i - 1] += w * a * c
        return d0, d1, d2
    d0, d1, d2 = bending()
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
        return list(zip(px, py)), at, tol, tight_with(px, py, beyond)
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
        r = tight_with(px, py, beyond)
        tight = [u[i] for i in range(n) if r[i] < MIN_RADIUS * SLACK]
        tight += [u[s] for s, inward in hinges if corner_excess(px, py, s, inward) > CORNER]
        grow = [i for i in data if tol[i] < limit[i] - 1e-9 and any(abs(u[at[i]] - t) <= NEAR for t in tight)]
        if not grow:
            # every point near a curve under 20 m is at its class: under 18 m the curve stiffens there and its points'
            # tolerance grows on up to HOLD_LIMIT (a wider tolerance alone only lets the curve go: on a 30° corner the
            # bend moved to where the points at their class begin, 15 m)
            under = [u[i] for i in range(n) if r[i] < NETWORK_RADIUS * SLACK]
            zone = [j for j in range(len(rows)) if any(abs(u[j + 1] - t) <= NEAR for t in under)]
            if not zone or max(stiff[j] for j in zone) >= STIFF_MAX:
                break
            for j in zone:
                stiff[j] *= STIFFEN
            for i in data:
                if tol[i] < max(limit[i], HOLD_LIMIT) and any(abs(u[at[i]] - t) <= NEAR for t in under):
                    tol[i] = min(max(limit[i], HOLD_LIMIT), tol[i] * GROW)
                    weight[at[i]] = 1.0
            d0, d1, d2 = bending()
            px, py = solve()
            continue
        for i in grow:
            tol[i] = min(limit[i], tol[i] * GROW)
            weight[at[i]] = 1.0
        px, py = solve()
    return list(zip(px, py)), at, tol, tight_with(px, py, beyond)


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
    """The fitted track graph. pos {node: (x, y)}, pts {(a, b): points from a to b} keyed by their nodes
    (a before b as strings), kind {(a, b): 'di' | 'dtmp' | 'osm'}, `loose` {(node, edge)}: a node off
    the surveyed track its edge runs on (no data point for it: the point nearest all of a node's tracks), `limit`
    {(a, b): metres} how far a surveyed edge's points may move where a curve would bend too tight (the mean coordinate
    error of its records' accuracy class; default the class UNCLASSED). After construction: `pos` and
    `pts` fitted, `report` (counts, the largest misses and the curves left tighter than MIN_RADIUS, with places)."""

    def __init__(self, pos, pts, kind, loose=(), limit=None, continues=None, solid=(), approach=None):
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        # nodes joined by an edge under MERGE are one (a switch's node and a neighbour moved onto one fork; two nodes
        # 4 cm apart at Národní divadlo, each fitted onto another track, would join with a 0.2 m radius)
        root = {n: n for n in pos}

        def find(n):
            while root[n] != n:
                root[n] = root[root[n]]
                n = root[n]
            return n
        # (the node with more edges stays, and the absorbed node's edges start at its point: a switch on its fork,
        # not OSM's next node on its branch 0.21 m off, which bent the straight track 8 cm at Strossmayerovo náměstí)
        degree = defaultdict(int)
        for a, b in pts:
            degree[a] += 1
            degree[b] += 1
        for (a, b), p in pts.items():
            # (never two nodes of `solid`, each exactly on its tracks: three chains crossing within 0.4 m at Palackého
            # náměstí, merged, passed one point 13 cm off)
            if sum(math.dist(x, y) for x, y in zip(p, p[1:])) < MERGE and not (a in solid and b in solid):
                ra, rb = find(a), find(b)
                if ra != rb:
                    keep, gone = (ra, rb) if degree[ra] >= degree[rb] else (rb, ra)
                    root[gone] = keep
                    degree[keep] += degree[gone]
        errors = class_errors()
        members = defaultdict(list)
        for n in pos:
            members[find(n)].append(n)
        adj, edges = defaultdict(set), {}
        for (a, b), p in pts.items():
            ra, rb = find(a), find(b)
            if ra != rb:
                p = [pos[ra] if a != ra else p[0], *p[1:-1], pos[rb] if b != rb else p[-1]]
                key = k(ra, rb)
                src = kind.get((a, b), 'osm')
                lim = (limit or {}).get((a, b)) or errors[UNCLASSED] if src in SURVEYED else FILL_LIMIT
                edges[key] = (list(p) if key == (ra, rb) else list(p[::-1]), src, lim)
                adj[ra].add(rb)
                adj[rb].add(ra)
        loose = {(find(n), k(find(a), find(b))): (loose[(n, (a, b))] if isinstance(loose, dict) else 0.5) for n, (a, b) in loose}
        # `approach` {node: the node its approaching track comes from}: a Y (an interlaced tip, tools/di_network.py
        # splay_ends): no two tracks continue each other there, the approaching one is fitted first and the others leave
        # along it, each easing off to its own side
        appr = {find(n): find(m) for n, m in (approach or {}).items()}

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

        def reach(n, m):
            """The direction from n to the point PAIR_LOOK on along edge n-m, then the straightest edge at each node."""
            pts, prev, cur, seen = list(along(n, m)), n, m, {n, m}
            while sum(math.dist(a, b) for a, b in zip(pts, pts[1:])) < PAIR_LOOK:
                d0 = direction(cur, prev)
                nxt = [x for x in adj[cur] if x not in seen]
                if not nxt:
                    break
                x = max(nxt, key=lambda x: -(d0[0] * direction(cur, x)[0] + d0[1] * direction(cur, x)[1]))
                pts += along(cur, x)[1:]
                prev, cur = cur, x
                seen.add(x)
            d, q = 0.0, pts[-1]
            for a, b in zip(pts, pts[1:]):
                d += math.dist(a, b)
                if d >= PAIR_LOOK:
                    q = b
                    break
            l = math.dist(pts[0], q) or 1.0
            return ((q[0] - pts[0][0]) / l, (q[1] - pts[0][1]) / l)

        # at every node the straightest pairs of edges continue each other
        pair = {}
        for n, ms in adj.items():
            if n in appr:
                continue
            ms = list(ms)
            dirs = {m: reach(n, m) if len(ms) > 2 else direction(n, m) for m in ms}
            limit = PAIR_TWO if len(ms) == 2 else PAIR
            cands = []
            # (`continues` {node: {frozenset((a, b))}}: the edges to a and b continue each other through the node, as the
            # network lets a train pass, tools/di_network.py; other edges meet there at their own angle, #237)
            ok = None
            if continues is not None:
                ok = {frozenset(find(x) for x in pr) for m0 in members[n] for pr in continues.get(m0, ())}
            for i, a in enumerate(ms):
                for b in ms[:i]:
                    dev = math.degrees(math.acos(max(-1.0, min(1.0, -(dirs[a][0] * dirs[b][0] + dirs[a][1] * dirs[b][1])))))
                    if (dev < limit) if ok is None else frozenset((a, b)) in ok:
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
        # a track that comes back into a node it passes through (a turning loop: through its switch, round and back
        # into it) is cut in the middle, so its end is held at the switch like any track ending there (Dvorce: the
        # free end landed 0.21 m off the switch, and the edge jumped to it in a 2.3 m kink)
        cut = []
        for seq in chains:
            if len(seq) > 3 and (seq[0] in seq[1:-1] or seq[-1] in seq[1:-1]):
                half, run, m = length(seq) / 2, 0.0, 1
                for i in range(1, len(seq) - 1):
                    run += length(seq[i - 1:i + 1])
                    if run >= half:
                        m = i
                        break
                cut += [seq[:m + 1], seq[m:]]
            else:
                cut.append(seq)
        chains = cut
        chains.sort(key=lambda s: -length(s))
        # longest first, but a track passing through a node before a track ending there: the one through it fixes it
        # (Holešovice: a longer track ending at a node 2 m off its own line fixed it, and the track through it bent
        # at 4 m to reach it)
        through = defaultdict(set)
        for c, seq in enumerate(chains):
            for n in seq[1:-1]:
                through[n].add(c)
            for n, m in ((seq[0], seq[1]), (seq[-1], seq[-2])):
                if appr.get(n) == m:   # (the track approaching a Y holds it, as a track through a node does)
                    through[n].add(c)
        order, done, left = [], set(), list(range(len(chains)))
        while left:
            c = next((c for c in left if all(through[n] <= done | {c} for n in (chains[c][0], chains[c][-1]))), left[0])
            order.append(c)
            done.add(c)
            left.remove(c)
        chains = [chains[c] for c in order]

        # node -> {'pos', 'dirs': directions of the tracks through it, 'at': [(track, index in its seq)]}
        node, fitted, found = {}, {}, {}

        def fit_chain(c, seq):
            # the points and their tolerance: a node off its surveyed tracks is no data point (the point nearest
            # all of them: 0.2 m off each at a junction at Národní divadlo, where the tracks run 1.3 m apart); the
            # longer track fixes it, the shorter one passes through. A node on them is (a crossing point stands in
            # for DI's vertex at a 5° bend, Strossmayerovo náměstí)
            pts_c, tol, lim, node_at = [], [], [], []
            for i, (a, b) in enumerate(zip(seq, seq[1:])):
                line, src, l = along(a, b), edges[k(a, b)][1], edges[k(a, b)][2]
                t = PHOTO_TOL if src == 'ortho' else TOL if src in SURVEYED else FILL_TOL
                # (on a track measured on the orthophoto only the measured centres are data: a node there is OSM's
                # projected onto its chords, 0.3 m inside the arc at Podolská vodárna)
                photo = src == 'ortho'
                if i == 0:
                    pts_c.append(line[0])
                    tol.append(None if photo or t == TOL and (a, k(a, b)) in loose else t)
                    lim.append(l)
                    node_at.append(0)
                else:
                    lim[-1] = min(lim[-1], l)   # (a node between two edges: the stricter limit)
                    if t == TOL:
                        tol[-1] = None if tol[-1] is None or (a, k(a, b)) in loose else TOL
                    elif photo:
                        tol[-1] = None
                for q in line[1:-1]:
                    pts_c.append(q)
                    tol.append(t)
                    lim.append(l)
                pts_c.append(line[-1])
                tol.append(None if photo or t == TOL and (b, k(a, b)) in loose else t)
                lim.append(l)
                node_at.append(len(pts_c) - 1)
            # where this track's records meet with a gap at a node (a branch DI starts 0.21 m off the through track's
            # line, Strossmayerovo náměstí), its points within GAP_REACH of it may move by the gap besides their class
            for j, n in enumerate(seq):
                gap = max([loose.get((n, k(n, m)), 0.0) for m in (seq[j - 1] if j else None, seq[j + 1] if j + 1 < len(seq) else None)
                           if m is not None and edges[k(n, m)][1] in SURVEYED] or [0.0])
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
            heading, behind = {}, {}
            for j, inward in ((0, 1), (len(seq) - 1, -1)):
                n = seq[j]
                if n not in node or not node[n]['dirs'] or (j and seq[0] == seq[-1]) or len(pts_c) < 2 or length(seq) < 2 * STEP:
                    continue
                d = own(j)
                d = (d[0] * inward, d[1] * inward)
                t0 = max(node[n]['dirs'], key=lambda t: abs(d[0] * t[0] + d[1] * t[1]))
                dot = d[0] * t0[0] + d[1] * t0[1]
                # (a track measured on the orthophoto always joins tangent: the user, "try to join smootly on both
                # ends if possible (smallest angle)"; its points start metres from the switch)
                photo = edges[k(n, seq[1] if j == 0 else seq[-2])][1] == 'ortho'
                if abs(dot) >= math.cos(math.radians(START)) or photo:
                    sg = 1 if dot > 0 else -1
                    heading[node_at[j]] = (sg * t0[0], sg * t0[1])
                    # the track it leaves, from the node back against the heading: the curve's windows read on into it
                    cc, jj = node[n]['at'][node[n]['dirs'].index(t0)]
                    f = fitted[cc]
                    seg = f['cut'][jj][0]
                    idx = range(seg, -1, -1) if sg > 0 else range(seg + 1, len(f['px']))
                    back = []
                    for i in idx:
                        q = (f['px'][i], f['py'][i])
                        d = math.dist(q, node[n]['pos'])
                        if d > BEHIND:
                            break
                        if d > 0.05:
                            back.append(q)
                    behind[node_at[j]] = back
            samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim, behind=behind)
            px, py = [q[0] for q in samples], [q[1] for q in samples]
            for j in crossing:
                n = seq[j]
                oc, oj = next((cc, jj) for cc, jj in node[n]['at'] if 0 < jj < len(chains[cc]) - 1)
                other = fitted[oc]
                hit = crossing_point(px, py, at[node_at[j]], other['px'], other['py'], other['cut'][oj][0])
                if hit is None:   # (the curves do not cross near it: hold it after all)
                    fixed[node_at[j]] = node[n]['pos']
                    samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim, behind=behind)
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
                    samples, at, tol_out, rad = fit(pts_c, tol, fixed, heading, limit=lim, behind=behind)
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
                    gap = max(loose.get((n, k(n, m)), 0.0) for m in (seq[j - 1], seq[j + 1])) if 0 < j < len(seq) - 1 else 0.0
                    if tol[node_at[j]] is None and gap > (0.0 if len(adj[n]) >= 4 else OFF):
                        # (a node off this track's line where it passes through: it stays where it is, the track
                        # crosses at its own point; the long track fixing it would move it off the tracks that do pass
                        # through it. A switch near its track joins it: OFF)
                        node[n] = {'pos': tuple(pts_c[node_at[j]]), 'dirs': [], 'at': [], 'off': True}
                        own_point[j] = q
                    else:
                        node[n] = {'pos': q, 'dirs': [], 'at': []}
                cut.append((seg, t))
                a, b = samples[max(0, seg - (t == 0.0 and seg > 0))], samples[min(len(samples) - 1, seg + 1)]
                l = math.dist(a, b) or 1.0
                node[n]['dirs'].append(((b[0] - a[0]) / l, (b[1] - a[1]) / l))
                node[n]['at'].append((c, j))
            fitted[c] = {'px': px, 'py': py, 'cut': cut, 'own': own_point}
            misses, tight, held, widened = [], [], [], 0
            for i, p in enumerate(pts_c):
                if tol[i] is None or tol[i] > TOL + 1e-9:
                    continue
                widened += tol_out[i] > tol[i] + 1e-9
                d, seg, t = nearest(px, py, at[i] - 3, at[i] + 3, p)
                if tol_out[i] > lim[i] + 1e-9:   # (moved past its class to hold NETWORK_RADIUS)
                    held.append({'m': round(d, 3), 'class_m': round(lim[i], 3), 'xy': [round(p[0], 1), round(p[1], 1)],
                                 'radius_m': round(min(rad[max(0, at[i] - int(NEAR)):at[i] + int(NEAR) + 1]), 1)})
                if d > TOL + REPORT:
                    misses.append({'m': round(d, 3), 'xy': [round(p[0], 1), round(p[1], 1)], 'widened': tol_out[i] > tol[i] + 1e-9})
            for i, r in enumerate(rad):
                if r < MIN_RADIUS * SLACK:
                    tight.append({'radius_m': round(r, 1), 'xy': [round(px[i], 1), round(py[i], 1)]})
            found[c] = (misses, tight, held, widened)

        first = {}   # chain -> its end nodes no track held when it was fitted
        for c, seq in enumerate(chains):
            first[c] = [j for j in (0, len(seq) - 1) if seq[j] not in node and not (j and seq[0] == seq[-1])]
            fit_chain(c, seq)
        # where the order rule deadlocks (each of two tracks passes through the other's end node, and the longer went
        # first), the end fitted free is refitted with the heading of the track fitted through it after it (line 37 s 3700,
        # a facing switch: the through track passed the branch's end 1.66° off it)
        for c, seq in enumerate(chains):
            again = False
            for j in first[c]:
                n = seq[j]
                mine = [d for (cc, jj), d in zip(node[n]['at'], node[n]['dirs']) if cc == c]
                for (cc, jj), d in zip(node[n]['at'], node[n]['dirs']):
                    if cc != c and 0 < jj < len(chains[cc]) - 1 and mine and                             abs(mine[0][0] * d[0] + mine[0][1] * d[1]) >= math.cos(math.radians(START)):
                        again = True
            if again:
                for n in set(seq):
                    keep = [(a, d) for a, d in zip(node[n]['at'], node[n]['dirs']) if a[0] != c]
                    node[n]['at'], node[n]['dirs'] = [a for a, _ in keep], [d for _, d in keep]
                fit_chain(c, seq)
                self.refitted = getattr(self, 'refitted', 0) + 1
        misses = [m for c in found for m in found[c][0]]
        tight = [m for c in found for m in found[c][1]]
        held = [m for c in found for m in found[c][2]]
        widened = sum(found[c][3] for c in found)
        # the edges: each track's samples between its nodes' cuts, ending at the nodes' final positions
        out_pts = {}
        for seq, f in zip(chains, (fitted[c] for c in range(len(chains)))):
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
        self.report = {'through_tracks': len(chains), 'refitted': getattr(self, 'refitted', 0), 'points_widened': widened, 'missed_over_cm': len(misses),
                       'missed_unwidened': sum(not m['widened'] for m in misses),
                       'misses': self._places(misses, 'm', -1)[:15],
                       'held_to_network_radius': self._places(held, 'm', -1),
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
    import json
    import time
    import di_network
    from geo import Frame
    line = sys.argv[sys.argv.index('--line') + 1] if '--line' in sys.argv else '17'
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / 'data' / f'line{line}.json').read_text(encoding='utf-8'))
    frame = Frame()
    t0 = time.time()
    net = di_network.load_network()
    edges = set()
    for key in ('path', 'pathBack'):
        if data.get(key):
            edges |= di_network.Match(net, [tuple(p[:2]) for p in data[key]]).edges
    t1 = time.time()
    drawn = di_network.Drawn(net, edges)
    print(f"network and the line's routes: {t1 - t0:.0f} s, curves {time.time() - t1:.0f} s")
    r = drawn.report
    print({k: v for k, v in r.items() if not isinstance(v, list)})
    for key in ('misses', 'held_to_network_radius', 'tighter_than_min_radius'):
        print(f'{key}:')
        for x in r[key]:
            lat, lon = frame.ll(*x['xy'])
            print(f"  {x.get('m', x.get('radius_m'))}  {float(lat):.5f} N {float(lon):.5f} E  {x['xy']}"
                  + (f"  (class {x['class_m']} m, {x['radius_m']} m over 2 m)" if 'class_m' in x else ''))


if __name__ == '__main__':
    main()
