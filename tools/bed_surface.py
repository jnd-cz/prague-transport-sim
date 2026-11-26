# SPDX-License-Identifier: AGPL-3.0-or-later
"""The track beds' surface as the page lays it (src/world.js bedRows, the beds' edges, bedsNear, bedZ; #508).

The ground mesh (tools/ground_mesh.py) lays every vertex inside a bed's outline on this surface, so the rails stand on
it as on the page's bed. The rule moves here from the page (docs/decisions/2026-11-05-ground-built-offline.md section 3:
one implementation, with a parity check against the page: tools/test_bed_surface.py --browser), and the page's copy goes
when the page loads the ground (#509).

Each drawn track (lineN.json `tracks`), along its points densified to SMOOTH m:
- **top of rail** `zs` (tools/line_heights.py) at each point, by the length along `p` (world.js ownHeights);
- **lift**, the rails over the bed: the route's `lift` at the nearest route s within 6 m, the other direction's
  `liftBack` across the street by the lateral offset (src/terrain.js Profile.lift), farther the track's own `lift`
  (its own styles' offsets, tools/track_styles.py own_lifts, #548), else 0;
- **tilt**: half the rails' height difference, from the route's lean (`cant` and `crossLevel.path`, src/route.js
  rollAt) within 5 m of the route, signed by the track's direction against the route's;
- **the bed's rows**: [x, y, nx, ny, offsets, heights] across each point: its right edge, right rail, left rail, left
  edge; the rails at zBed -+ tilt, zBed = top of rail - lift - BED_BELOW, the edges on the rails' plane out to the bed's
  width (`bed`, tools/track_beds.py), where the bed meets a paired track the mean of the two near rails; then each edge
  no higher than another bed under it within 0.3 m (#165, #548);
- **the surface**: the triangles the page draws between the rows (addBed), the lowest where two beds overlap.
"""
import math

import numpy as np

GAUGE_HALF = 0.72  # m: a rail from the axis (world.js GAUGE_HALF)
BED_BELOW = 0.006  # m: the bed under the surface level the style gives (src/heights.js BED_BELOW)
SMOOTH = 1.5  # m: the tracks' drawn points (world.js buildWorld: densify(t.p, 1.5))
NEAR = 4.0  # m: a track's points this near count (world.js nearPoints)
EDGE_OVER = 0.3  # m: an edge over another bed by less than this is lowered to it (world.js edges)
ROUTE_SAMPLE, ROUTE_CELL = 4.0, 40.0  # m: src/route.js _buildSamples
# Where beds overlap (a switch, a fork, a diamond) a point takes the first of these styles of the beds holding it: the
# junction's paving over its arms' panels (#676; track_styles.py lays a junction embedded over its whole area, #546)
STYLE_OVER = ("embedded", "setts", "panels", "ballast", "grass")
STYLE_BISECT = 0.01  # m: a style's change along a track, found to this (Beds.style_runs)
COVER_TOL = 0.02  # m: a point this far past a bed's edge is still in it (the ground's faces end on its edge, on the mm grid)
FAR_CUT = 3.0  # m along a track from a change of style: past it, where every drawn point within NEAR m agrees, that style


def densify(line, maxlen=SMOOTH):
    """src/worldMesh.js densify: every segment cut into ceil(length / maxlen) equal parts."""
    out = [tuple(line[0][:2])]
    for a, b in zip(line, line[1:]):
        n = math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / maxlen)
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return np.array(out, float)


def poly_len(p):
    p = np.asarray(p, float)[:, :2]
    return float(np.hypot(*np.diff(p, axis=0).T).sum()) if len(p) > 1 else 0.0


def series(d):
    """src/heights.js series: a function of s from {step, unit, v}."""
    if not d or not d.get("v"):
        return lambda s: np.zeros_like(np.asarray(s, float))
    v, n = np.asarray(d["v"], float), len(d["v"])

    def f(s):
        s = np.asarray(s, float)
        if n < 2:
            return np.full_like(s, v[0] * d["unit"])
        x = np.clip(s / d["step"], 0, n - 1.001)
        i = np.floor(x).astype(int)
        t = x - i
        return (v[i] * (1 - t) + v[i + 1] * t) * d["unit"]
    return f


def resample(arr, step, n, at):
    """src/heights.js resampleHeights: arr every `step` read at n points `at` apart (NaN where a neighbour is null)."""
    out = np.full(n, np.nan)
    m = len(arr)
    for i in range(n):
        k = i * at / step
        i0 = min(int(math.floor(k)), m - 1)
        f = k - i0
        a, b = arr[i0], arr[min(i0 + 1, m - 1)]
        out[i] = np.nan if a is None else a if (f < 1e-6 or i0 + 1 >= m) else np.nan if b is None else a + (b - a) * f
    return out


class RouteNear:
    """The route's lookups the beds read: nearest (src/route.js nearest: the nearest 4 m sample, refined onto the chords
    to its neighbours), at, the lean (rollAt) and the lift across (Profile.lift)."""

    def __init__(self, L):
        from scipy.spatial import cKDTree
        from route import Route
        self.rt = Route(L["path"], L.get("pathExt"))
        ss = np.arange(0, self.rt.length + 1e-9, ROUTE_SAMPLE)
        self.samples = np.array([self.rt.at(s)[:2] + (s,) for s in ss])
        self.tree = cKDTree(self.samples[:, :2])

        def arr(d, key="c"):
            return (d["step"], np.asarray(d[key], float) * d["unit"]) if d and d.get(key) else None
        self.cant = arr(L.get("cant"))
        self.cross = arr(L.get("crossLevel"), "path")
        self.lift_f = series(L.get("lift"))
        self.lift_back = series(L["liftBack"]) if L.get("liftBack") else None
        h = L.get("heights") or {}
        n = math.ceil(self.rt.length / 2) + 1
        self.back_off = resample(h["backOff"], h["step"], n, 2) if h.get("backOff") else None

    def nearest(self, x, y):
        """(d, s), or None past ROUTE_CELL m: the page's grid finds no sample there."""
        d, k = self.tree.query((x, y))
        if d > ROUTE_CELL:  # (the page searches its 40 m cell and the eight around it: a sample within 40 m is found)
            return None
        bx, by, bs = self.samples[k]
        out = (d, bs)
        for o in (-1, 1):
            j = k + o
            if j < 0 or j >= len(self.samples):
                continue
            rx, ry, rs = self.samples[j]
            ex, ey = rx - bx, ry - by
            l2 = ex * ex + ey * ey
            if l2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((x - bx) * ex + (y - by) * ey) / l2))
            dd = math.hypot(bx + ex * t - x, by + ey * t - y)
            if dd < out[0]:
                out = (dd, bs + (rs - bs) * t)
        return out

    @staticmethod
    def _interp(a, s):
        step, c = a
        f = max(0.0, min(len(c) - 1.001, s / step))
        i = int(math.floor(f))
        u = f - i
        return c[i] * (1 - u) + c[i + 1] * u

    def roll(self, s):
        c = (self._interp(self.cant, s) if self.cant else 0.0) + (self._interp(self.cross, s) if self.cross else 0.0)
        return math.atan2(max(-0.1, min(0.1, c)), 1.5)

    def lift(self, s, lateral=0.0):
        a = float(self.lift_f(s))
        if not lateral or self.back_off is None or self.lift_back is None:
            return a
        o = self.back_off[max(0, min(len(self.back_off) - 1, int(round(s / 2))))]
        if not abs(o) > 0.5:
            return a
        return a + (float(self.lift_back(s)) - a) * max(0.0, min(1.0, lateral / o))

    def lateral(self, s, x, y):
        qx, qy, hx, hy = self.rt.at(s)
        return hx * (y - qy) - hy * (x - qx)

    def on_back(self, s, lateral):
        """`lateral` m across from our track lies nearer the other direction's (src/terrain.js Profile.onBack, #584)."""
        if self.back_off is None or not lateral:
            return False
        o = self.back_off[max(0, min(len(self.back_off) - 1, int(round(s / 2))))]
        return bool(abs(o) > 0.5 and lateral / o > 0.5)


class Beds:
    """Every drawn track's bed rows as the page builds them, and the bed surface at a point."""

    def __init__(self, L):
        from scipy.spatial import cKDTree
        self.L, self.R = L, RouteNear(L)
        step = L["heights"]["step"]
        tracks = L.get("tracks") or []
        self.tracks = tracks
        self.smooth = [densify(t["p"]) for t in tracks]
        self.zBed, self.tilt, self.lift = [], [], []  # (top of rail = a rail's row z + lift + BED_BELOW)
        for k, (t, sm) in enumerate(zip(tracks, self.smooth)):
            z = self._own_heights(t, sm, step)
            own, sk = series(t.get("lift")), poly_len(t["p"]) / (poly_len(sm) or 1)
            lift = np.array([self._lift_at(x, y, own, a * sk) for (x, y), a in zip(sm, self.acc(k))])
            self.lift.append(lift)
            self.zBed.append(z - lift - BED_BELOW)
            self.tilt.append(self._tilt(sm))
        self.owner = np.concatenate([np.full(len(sm), k) for k, sm in enumerate(self.smooth)]) if tracks else np.zeros(0, int)
        self.index = np.concatenate([np.arange(len(sm)) for sm in self.smooth]) if tracks else np.zeros(0, int)
        allp = np.vstack(self.smooth) if tracks else np.zeros((0, 2))
        self.tree = cKDTree(allp)
        self.rows = [self._rows(k, step) for k in range(len(tracks))]
        self._lower_edges()

    @staticmethod
    def _own_heights(t, sm, step):
        zs = t["zs"]
        k = poly_len(t["p"]) / (poly_len(sm) or 1)
        acc = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(sm, axis=0).T))]) if len(sm) > 1 else np.zeros(1)
        out = np.empty(len(sm))
        for i, a in enumerate(acc):
            f = a * k / step
            i0 = min(int(math.floor(f)), len(zs) - 1)
            za, zb = zs[i0], zs[min(i0 + 1, len(zs) - 1)]
            if za is None or zb is None:
                raise ValueError("a track without a height: data built before #480")
            out[i] = za + (zb - za) * (f - i0)
        return out

    def _lift_at(self, x, y, own=None, s=0.0):
        """The rails over the bed: the route's within 6 m of it, else the track's own (its `lift` at s along its `p`,
        tools/track_styles.py own_lifts, #548: another line's open ballast, 0.17 m)."""
        n = self.R.nearest(x, y)
        if n and n[0] < 6:
            return self.R.lift(n[1], self.R.lateral(n[1], x, y))
        return float(own(s)) if own is not None else 0.0

    def _tilt(self, sm):
        out = np.zeros(len(sm))
        for i, (x, y) in enumerate(sm):
            n = self.R.nearest(x, y)
            if not n or n[0] > 5:
                continue
            roll = self.R.roll(n[1])
            if not roll:
                continue
            a, b = sm[max(0, i - 1)], sm[min(len(sm) - 1, i + 1)]
            _, _, hx, hy = self.R.rt.at(n[1])
            same = 1 if (b[0] - a[0]) * hx + (b[1] - a[1]) * hy >= 0 else -1
            out[i] = -0.72 * math.tan(roll) * same
        return out

    def _point_style(self, k, x, y, a):
        """Track k's style at (x, y), `a` m along its drawn points (src/world.js styleAt, ownStyles): the route's at the
        nearest route point within 6 m (the other direction's track beside the route takes `stylesBack`, #584), else the
        track's own sections (`styles`, along `p`), else panels."""
        n = self.R.nearest(x, y)
        if n and n[0] < 6:
            secs = self.L.get("styles") or []
            lst = (self.L.get("stylesBack") or secs) if self.R.on_back(n[1], self.R.lateral(n[1], x, y)) else secs
            return next((q["style"] for q in lst if q["s0"] <= n[1] <= q["s1"]), "panels")
        s = a * poly_len(self.tracks[k]["p"]) / (poly_len(self.smooth[k]) or 1)
        return next((st for a0, b0, st in self.tracks[k].get("styles") or [] if a0 <= s <= b0), "panels")

    def acc(self, k):
        """Track k's drawn points' distances along it."""
        if not hasattr(self, "_accs"):
            self._accs = [np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(sm, axis=0).T))]) if len(sm) > 1 else np.zeros(1)
                          for sm in self.smooth]
        return self._accs[k]

    def row_styles(self):
        """Per track, per drawn point: the bed's style as the page colours it (_point_style)."""
        return [[self._point_style(k, x, y, a) for (x, y), a in zip(sm, self.acc(k))] for k, sm in enumerate(self.smooth)]

    def style_runs(self):
        """Per track, its style along its drawn points: (cuts, styles), styles[i] from cuts[i] m on. A change between two
        drawn points is found to STYLE_BISECT m (the page changed it at a row, every 1.5 m: two paired tracks' rows,
        offset along, left a stepped edge across the beds, #676)."""
        if hasattr(self, "_runs"):
            return self._runs
        out = []
        for k, (sm, st) in enumerate(zip(self.smooth, self.row_styles())):
            acc = self.acc(k)
            cuts, sty = [0.0], [st[0]]
            for i in range(1, len(st)):
                if st[i] == st[i - 1]:
                    continue
                lo, hi = acc[i - 1], acc[i]
                p0, p1 = sm[i - 1], sm[i]
                while hi - lo > STYLE_BISECT:
                    mid = (lo + hi) / 2
                    u = (mid - acc[i - 1]) / ((acc[i] - acc[i - 1]) or 1)
                    if self._point_style(k, p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u, mid) == st[i - 1]:
                        lo = mid
                    else:
                        hi = mid
                cuts.append((lo + hi) / 2)
                sty.append(st[i])
            out.append((np.array(cuts), sty))
        self._runs = out
        return out

    def style_on(self, k, a):
        """Track k's style `a` m along its drawn points."""
        cuts, sty = self.style_runs()[k]
        return sty[max(0, int(np.searchsorted(cuts, a, "right")) - 1)]

    def style_at(self, x, y):
        """The bed's style at each point: of the beds holding it (between their edges, at the point's own length along
        each), the first in STYLE_OVER, the nearer bed between equals; where none holds it (the beds' outline closes
        gaps of mm between them), the nearest drawn point's. The ground's faces are cut where a style changes and along
        every bed's edges (tools/ground_mesh.py rail_lines), so each face lies in one style. (By the nearest drawn
        point's row, a face spanning two paired tracks' rows or two beds at a fork took one style whole: saw-teeth along
        the paved outline, line 37 s 1681, #676.)"""
        runs = self.style_runs()
        x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
        n = len(self.owner)
        if not n:
            return ["panels"] * len(x)
        if not hasattr(self, "_flat_name"):
            accs = [self.acc(k) for k in range(len(self.smooth))]
            # (each drawn point's style and its distance along its track to the nearest change of style)
            self._flat_name = np.array([runs[k][1][int(r)] for k, a in enumerate(accs)
                                        for r in np.searchsorted(runs[k][0], a, "right") - 1], dtype=object)
            self._flat_near_cut = np.concatenate([np.abs(a[:, None] - runs[k][0][None, 1:]).min(1) if len(runs[k][0]) > 1
                                                  else np.full(len(a), np.inf) for k, a in enumerate(accs)])
        kq = min(8, n)
        d, j = self.tree.query(np.column_stack([x, y]), k=kq, distance_upper_bound=NEAR)
        d, j = d.reshape(len(x), kq), j.reshape(len(x), kq)
        valid = np.isfinite(d)
        jj = np.where(valid, j, 0)
        sty = self._flat_name[jj]
        # (the quick answer: every drawn point within NEAR m has one style, none within FAR_CUT m of a change along)
        same = valid[:, 0] & (~valid | (sty == sty[:, :1])).all(1) & (~valid | (self._flat_near_cut[jj] > FAR_CUT)).all(1)
        out = [None] * len(x)
        for i in np.flatnonzero(same).tolist():
            out[i] = sty[i, 0]
        for i in np.flatnonzero(~same).tolist():
            best = None
            for row, o, k, r, v in self._near_rows(x[i], y[i]):
                off = row[4]
                if not (min(off[0], off[3]) - COVER_TOL <= o <= max(off[0], off[3]) + COVER_TOL):
                    continue
                acc = self.acc(k)
                st = self.style_on(k, acc[r] + (acc[r + 1] - acc[r]) * v)
                rank = (STYLE_OVER.index(st) if st in STYLE_OVER else len(STYLE_OVER), abs(o))
                if best is None or rank < best[0]:
                    best = (rank, st)
            if best is not None:
                out[i] = best[1]
            else:  # (in no bed: the nearest drawn point's style)
                out[i] = sty[i, 0] if valid[i, 0] else self._flat_name[int(self.tree.query((x[i], y[i]))[1])]
        return out

    def near_points(self, x, y, skip=-1):
        """world.js nearPoints: each track's nearest point within NEAR m: [(track, index, distance)]."""
        best = {}
        for j in self.tree.query_ball_point((x, y), NEAR):
            k = int(self.owner[j])
            if k == skip:
                continue
            p = self.smooth[k][self.index[j]]
            d = math.hypot(p[0] - x, p[1] - y)
            if d < NEAR and not (k in best and best[k][1] <= d):
                best[k] = (int(self.index[j]), d)
        return [(k, i, d) for k, (i, d) in best.items()]

    def other_rail(self, own, x, y):
        best = None
        for h in self.near_points(x, y, own):
            if best is None or h[2] < best[2]:
                best = h
        if best is None:
            return None
        k, i, _ = best
        sm = self.smooth[k]
        a, b = sm[max(0, i - 1)], sm[min(len(sm) - 1, i + 1)]
        side = 1 if (b[0] - a[0]) * (y - sm[i][1]) - (b[1] - a[1]) * (x - sm[i][0]) >= 0 else -1
        return self.zBed[k][i] + self.tilt[k][i] * side

    def _rows(self, k, step):
        t, line, zb, tl = self.tracks[k], self.smooth[k], self.zBed[k], self.tilt[k]
        bed = t.get("bed")
        k_len = poly_len(t["p"]) / (poly_len(line) or 1)
        n = len(bed["l"]) if bed else 0
        rows, acc = [], 0.0
        for i, p in enumerate(line):
            if i:
                acc += math.hypot(p[0] - line[i - 1][0], p[1] - line[i - 1][1])
            f = min(n - 1, acc * k_len / step) if n else 0
            i0 = min(int(math.floor(f)), max(0, n - 1))
            i1 = min(i0 + 1, max(0, n - 1))
            u = f - i0
            near = i0 if u < 0.5 else i1
            prev, nxt = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
            dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
            ln = math.hypot(dx, dy) or 1
            dx, dy = dx / ln, dy / ln
            scale = 1.0
            if 0 < i < len(line) - 1:
                ax, ay = p[0] - prev[0], p[1] - prev[1]
                al = math.hypot(ax, ay) or 1
                scale = min(2.0, 1 / max(0.5, (ax / al) * dx + (ay / al) * dy))
            nx, ny, slope = -dy * scale, dx * scale, tl[i] / GAUGE_HALF
            off = [0.0, -GAUGE_HALF, GAUGE_HALF, 0.0]
            z = [0.0, zb[i] - tl[i], zb[i] + tl[i], 0.0]
            for side, key, bit, j in ((-1, "r", 2, 0), (1, "l", 1, 3)):
                w = (bed[key][i0] * (1 - u) + bed[key][i1] * u) / 100 if bed else 1.35
                off[j] = side * w
                z[j] = zb[i] + slope * side * w
                if bed and bed["meet"][near] & bit:
                    o = self.other_rail(k, p[0] + nx * side * w, p[1] + ny * side * w)
                    if o is not None:
                        z[j] = (zb[i] + tl[i] * side + o) / 2
            rows.append([p[0], p[1], nx, ny, off, z])
        return rows

    def beds_near(self, x, y):
        """world.js bedsNear: [(row at the point, offset across, track)] of the beds near (x, y)."""
        return [(row, o, k) for row, o, k, _, _ in self._near_rows(x, y)]

    def _near_rows(self, x, y):
        """beds_near's rows, each with the row before it and how far on to the next: (row, offset, track, row index, v)."""
        out = []
        for k, i, _ in self.near_points(x, y):
            if self.tracks[k].get("b"):
                continue
            rows = self.rows[k]
            best = None
            for j in (i - 1, i):
                if j < 0 or j + 1 >= len(rows):
                    continue
                A, B = rows[j], rows[j + 1]
                ex, ey = B[0] - A[0], B[1] - A[1]
                el = ex * ex + ey * ey or 1
                u = ((x - A[0]) * ex + (y - A[1]) * ey) / el
                if u < -0.01 or u > 1.01:
                    continue
                v = max(0.0, min(1.0, u))
                d = math.hypot(x - (A[0] + ex * v), y - (A[1] + ey * v))
                if best is None or d < best[0]:
                    best = (d, A, B, v, j)
            if best is None:
                continue
            _, A, B, v, j = best
            row = [A[q] * (1 - v) + B[q] * v for q in range(4)] + [[a * (1 - v) + b * v for a, b in zip(A[4], B[4])],
                                                                  [a * (1 - v) + b * v for a, b in zip(A[5], B[5])]]
            nl = math.hypot(row[2], row[3]) or 1
            o = ((x - row[0]) * row[2] + (y - row[1]) * row[3]) / nl / nl
            out.append((row, o, k, j, v))
        return out

    def _lower_edges(self):
        edges = []
        for k, rows in enumerate(self.rows):
            e = []
            for x, y, nx, ny, off, z in rows:
                pair = []
                for j in (0, 3):
                    m = z[j]
                    for row, o, kk in self.beds_near(x + nx * off[j], y + ny * off[j]):
                        if kk == k:
                            continue
                        zs = bed_z(row, o)
                        if zs is not None and zs < m < zs + EDGE_OVER:
                            m = zs
                    pair.append(m)
                e.append(pair)
            edges.append(e)
        for k, rows in enumerate(self.rows):
            for row, (a, b) in zip(rows, edges[k]):
                row[5][0], row[5][3] = a, b

    def triangles(self):
        """The beds' triangles as the page draws them (world.js addBed: between two rows, the right edge-rail, the rails'
        and the rail-left edge strips, each quad (a, b, d), (a, d, e) as ChunkedGeometry.quad): ((n, 3, 3), track)."""
        if getattr(self, "_tris", None) is None:
            out, own = [], []
            for k, rows in enumerate(self.rows):
                if self.tracks[k].get("b") or len(rows) < 2:
                    continue
                P = np.array([[(x + nx * o, y + ny * o, z) for o, z in zip(off, zz)] for x, y, nx, ny, off, zz in rows])
                for j in range(3):
                    a, b, d, e = P[:-1, j], P[1:, j], P[1:, j + 1], P[:-1, j + 1]
                    out += [np.stack([a, b, d], 1), np.stack([a, d, e], 1)]
                    own += [np.full(len(a), k)] * 2
            self._tris = (np.concatenate(out), np.concatenate(own)) if out else (np.zeros((0, 3, 3)), np.zeros(0, int))
            import shapely
            T = self._tris[0]
            self._tree = shapely.STRtree(shapely.polygons(np.concatenate([T[:, :, :2], T[:, :1, :2]], 1)))
        return self._tris

    def surface_at(self, x, y, reach=0.0):
        """The bed surface as drawn at points: the lowest of the beds' triangles holding each (two beds overlap at a
        junction); where none does, the nearest within `reach` m, its plane carried out (the ground's bed outline,
        tools/track_beds.py outline, samples the track along `p`, the rows along its drawn points: their edges differ by a
        few cm); NaN farther."""
        import shapely
        T, _ = self.triangles()
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(len(x), np.nan)
        if not len(T) or not len(x):
            return out
        pts = shapely.points(x, y)
        pi, ti = self._tree.query(pts, predicate="intersects")
        if len(pi):
            np.fmin.at(out, pi, plane(T[ti], x[pi], y[pi]))
        miss = np.flatnonzero(np.isnan(out))
        if reach and len(miss):
            import ties  # (of triangles as near, the first by where it lies, not by the tree's order, #812)
            if getattr(self, "_rank", None) is None:
                self._rank = ties.rank(*(T[:, i, j] for i in range(3) for j in range(3)))
            mi, mt = ties.nearest(self._tree, self._rank, pts[miss], max_distance=reach)
            out[miss[mi]] = plane(T[mt], x[miss[mi]], y[miss[mi]])
        return out

    def surface(self, x, y, reach=0.0):
        """surface_at for one point, or None."""
        v = self.surface_at([x], [y], reach)[0]
        return None if np.isnan(v) else float(v)


def plane(tri, x, y):
    """Heights on the planes of triangles (n, 3, 3) at (x, y)."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    w0 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
    w1 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
    return w0 * a[:, 2] + w1 * b[:, 2] + (1 - w0 - w1) * c[:, 2]


def bed_z(row, o):
    """world.js bedZ: the bed's surface at offset o (m, + left) of a row; None past its edges."""
    off, z = row[4], row[5]
    if o < off[0] or o > off[3]:
        return None
    for j in range(3):
        if o <= off[j + 1]:
            return z[j] + (z[j + 1] - z[j]) * (o - off[j]) / ((off[j + 1] - off[j]) or 1)
    return z[3]
