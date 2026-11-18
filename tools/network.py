# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network as a layer the build makes (#658): what each shift's Start built from the survey, built once here.

    python -P -E tools/network.py --lines 37                    # data/line37.network.json
    python -P -E tools/network.py --lines 9,17,22,23,37 --parity
                                    # also the page's own network (headless Chromium), compared with the build's

Steps 2-4 of the design note (docs/decisions/2026-11-18-network-layer.md): the roads, their lanes, the footways and
the doors. src/traffic.js's rules are ported whole and in its order, so that the build's network is the page's
(--parity):
- src/streets.js widenTramStreets: a road with tracks along it is 3.2 m wider a track (the page does it at load);
- the vehicle ways split at every node another way shares (the junctions), each piece smoothed (src/route.js
  smoothPolyline: every 3 m, over 6 m);
- cars only on public roads (OSM's `c`) from 5 m wide;
- `_fitRoad`: every 4 m, the survey's carriageway across ±16 m (a tram area or parking at its side trimmed, a median
  kept apart), its kerbs smoothed; `_parallelWays`: a way alongside in the same carriageway takes its own side;
- `_trackLats`: the tracks' lateral positions on the road every 4 m (ours and the opposite direction's);
- `_buildLanes`, `laneOffset`: a lane per direction and OSM lane, beside the kerbs, a median or the tracks' middle;
- the walks: OSM's footways (cut where they lie on the surveyed carriageway) and the sidewalks the survey shows beside
  the roads, away from the tracks; `_linkWalks`: their ends joined, or linked across a street clear of the tracks;
- `_findDoors`: a building's door where its outline comes nearest a walk.

The survey is read as the page reads it: the ground file's triangles (data/lineN.ground.*, tools/ground_mesh.py), the
highest holding the point and the survey's class under it (src/groundFile.js GroundLookup.survey), the 10 m cells the
survey covers (`covered`), and data/lineN.dtm.json's underground areas (src/terrain.js classUnder). The arithmetic is
the page's, in its order, with Math.hypot as V8 computes it (js_hypot).

The file, data/lineN.network.json, positions in cm (a path flat x, y):
- `roads`: each with its points `p`, its OSM tags (`w` with the tracks, `o`, `b`, `t`, `tram`, `ln`, `lf`, `lb`), its
  junctions' keys `ends` (src/traffic.js key()), and where the survey fitted it its kerbs `lo`, `hi` and median `med`
  (from the centre line, + right, every 4 m), and the tracks on it `trk`;
- `lanes`: each lane's `road` (its index), `dir`, `sel` (the lane of its direction) and points `p`;
- `walks`: each walk's points `p`, `link` for a crossing or a join, `deck` (with its `way`, data.roads' index) on a
  bridge, and its `links` at each end ([walk, s]);
- `doors`: [walk, s, x, y, ix, iy]: the point on the walk and the one 1.5 m inside the building.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

VERSION = 1
PARTS = ("roads", "lanes", "walks", "doors")  # (what the layer holds so far, in the note's steps)


# ---------------------------------------------------------------- the page's arithmetic
def js_hypot(a, b):
    """Math.hypot(a, b) as V8 computes it (src/builtins/math.tq): both scaled by the larger, the squares summed (Kahan,
    which for two adds nothing), sqrt times the larger. np.hypot (C's hypot) differs from it in the last bit."""
    a, b = np.abs(np.asarray(a, float)), np.abs(np.asarray(b, float))
    m = np.maximum(a, b)
    with np.errstate(invalid="ignore", divide="ignore"):
        n1, n2 = a / m, b / m
        out = np.sqrt(n1 * n1 + n2 * n2) * m
    return np.where(m == 0, 0.0, out)


def hyp(a, b):
    """js_hypot of two floats."""
    a, b = abs(a), abs(b)
    m = a if a > b else b
    if m == 0:
        return 0.0
    n1, n2 = a / m, b / m
    return math.sqrt(n1 * n1 + n2 * n2) * m


def js_round(v):
    """Math.round: halves toward +infinity."""
    return math.floor(v + 0.5)


def cm(v):
    return js_round(v * 100)


def smooth_polyline(pts, step=1.0, radius=6.0):
    """src/route.js smoothPolyline with a constant radius: resampled every `step` m of arc length, then a Gaussian
    window (shrinking at the ends, so they stay put). Returns the points (n, 2)."""
    p = np.asarray(pts, float)[:, :2]
    cum = [0.0]
    for i in range(1, len(p)):
        cum.append(cum[-1] + hyp(p[i, 0] - p[i - 1, 0], p[i, 1] - p[i - 1, 1]))
    cum = np.asarray(cum)
    L = float(cum[-1])
    n = max(2, js_round(L / step) + 1)
    s = L * np.arange(n) / (n - 1)
    # (the page walks j along: the last segment whose end lies before s, at most the last)
    j = np.minimum(len(p) - 2, np.searchsorted(cum[1:], s, side="left"))
    seg = cum[j + 1] - cum[j]
    seg = np.where(seg == 0, 1e-9, seg)
    t = np.clip((s - cum[j]) / seg, 0, 1)
    xs = p[j, 0] + (p[j + 1, 0] - p[j, 0]) * t
    ys = p[j, 1] + (p[j + 1, 1] - p[j, 1]) * t
    unit = L / (n - 1) or 1
    k = max(1, js_round(radius / unit)) if radius > 0 else 0
    if not k:
        return np.column_stack([xs, ys])
    w = [math.exp(-0.5 * (d / (k / 2)) * (d / (k / 2))) for d in range(k + 1)]
    i = np.arange(n)
    r = np.minimum(np.minimum(k, i), n - 1 - i)
    sx, sy, sw = np.zeros(n), np.zeros(n), np.zeros(n)
    for d in range(-k, k + 1):
        on = abs(d) <= r
        q = np.clip(i + d, 0, n - 1)
        ww = w[abs(d)]
        sx += np.where(on, xs[q] * ww, 0.0)
        sy += np.where(on, ys[q] * ww, 0.0)
        sw += np.where(on, ww, 0.0)
    return np.column_stack([sx / sw, sy / sw])


class Path:
    """src/traffic.js Path: a polyline with arc length lookups."""

    def __init__(self, pts):
        self.p = np.asarray(pts, float)[:, :2]
        s = [0.0]
        for i in range(1, len(self.p)):
            s.append(s[-1] + hyp(self.p[i, 0] - self.p[i - 1, 0], self.p[i, 1] - self.p[i - 1, 1]))
        self.s = np.asarray(s)
        self.length = float(self.s[-1])

    def at(self, s):
        """(x, y, hx, hy) arrays at the arc lengths s (an array)."""
        s = np.clip(np.asarray(s, float), 0, self.length)
        lo = np.clip(np.searchsorted(self.s, s, side="right") - 1, 0, len(self.s) - 2)
        hi = lo + 1
        a, b = self.p[lo], self.p[hi]
        seg = self.s[hi] - self.s[lo]
        seg = np.where(seg == 0, 1e-9, seg)
        t = (s - self.s[lo]) / seg
        dx, dy = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
        ln = js_hypot(dx, dy)
        ln = np.where(ln == 0, 1.0, ln)
        return a[:, 0] + dx * t, a[:, 1] + dy * t, dx / ln, dy / ln

    def at1(self, s):
        """at() of one arc length: (x, y, hx, hy) floats."""
        return tuple(float(v[0]) for v in self.at(np.array([s], float)))


class Route:
    """src/route.js Route: the build's points as they are with the run past both termini (`ext`), s from the path's
    start; samples every 4 m in 40 m cells for `nearest`."""

    def __init__(self, pts, ext=None):
        before, after = (ext or {}).get("before") or [], (ext or {}).get("after") or []
        al = [[float(q[0]), float(q[1])] for q in [*before, *pts, *after]]
        s = [0.0]
        for i in range(1, len(al)):
            s.append(s[-1] + hyp(al[i][0] - al[i - 1][0], al[i][1] - al[i - 1][1]))
        s0 = s[len(before)]
        L = 0.0
        for i in range(1, len(pts)):
            L += hyp(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
        self.pts, self.s, self.length = al, [v - s0 for v in s], L
        self.samples, self.grid = [], {}
        v = 0.0
        while v <= self.length:
            x, y, _, _ = self.at(v)
            q = (x, y, v, len(self.samples))
            self.samples.append(q)
            self.grid.setdefault(self.key(x, y), []).append(q)
            v += 4

    @staticmethod
    def key(x, y):
        return math.floor(x / 40) * 100003 + math.floor(y / 40)

    def _index(self, s):
        S, hi = self.s, len(self.s) - 1
        if s <= S[0]:
            return 0
        if s >= S[hi]:
            return hi - 1
        lo = 0
        while hi - lo > 1:
            mid = (lo + hi) >> 1
            if S[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo

    def at(self, s):
        i = self._index(s)
        a, b = self.pts[i], self.pts[i + 1]
        seg = (self.s[i + 1] - self.s[i]) or 1e-9
        t = max(0.0, min(1.0, (s - self.s[i]) / seg))
        dl = hyp(b[0] - a[0], b[1] - a[1]) or 1e-9
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (b[0] - a[0]) / dl, (b[1] - a[1]) / dl

    def nearest(self, x, y):
        """(d, s) of the nearest point within ~40 m, or None: the nearest sample refined onto its neighbours' chords."""
        cx, cy = math.floor(x / 40), math.floor(y / 40)
        best, bd = None, math.inf
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in self.grid.get((cx + dx) * 100003 + (cy + dy), ()):
                    ex, ey = q[0] - x, q[1] - y
                    d = ex * ex + ey * ey
                    if d < bd:
                        bd, best = d, q
        if best is None:
            return None
        od, os_ = math.sqrt(bd), best[2]
        for o in (-1, 1):
            k = best[3] + o
            if k < 0 or k >= len(self.samples):
                continue
            r = self.samples[k]
            ex, ey = r[0] - best[0], r[1] - best[1]
            l2 = ex * ex + ey * ey
            if l2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((x - best[0]) * ex + (y - best[1]) * ey) / l2))
            d = hyp(best[0] + ex * t - x, best[1] + ey * t - y)
            if d < od:
                od, os_ = d, best[2] + (r[2] - best[2]) * t
        return od, os_


# ---------------------------------------------------------------- the survey, as the page reads it
def read_varints(buf, n, off):
    """n LEB128 varints from buf[off:]: (uint64 array, the offset after them). ground_mesh.read_varints at numpy speed."""
    if n == 0:
        return np.zeros(0, np.uint64), off
    b = np.frombuffer(buf, np.uint8, offset=off)
    ends = np.flatnonzero(b < 0x80)[:n]
    if len(ends) < n:
        raise ValueError("the ground file ends inside its varints")
    m = int(ends[-1]) + 1
    starts = np.concatenate([[0], ends[:-1] + 1])
    pos = np.arange(m)
    idx = np.repeat(np.arange(n), np.diff(np.concatenate([starts, [m]])))
    shift = (7 * (pos - starts[idx])).astype(np.uint64)
    v = (b[:m] & 0x7F).astype(np.uint64) << shift
    return np.add.reduceat(v, starts), off + m


def unzigzag(u):
    return ((u >> np.uint64(1)).astype(np.int64)) ^ -((u & np.uint64(1)).astype(np.int64))


def decode_tile(blob, layout):
    """One tile of the ground file as src/groundWorker.js decodeOne reads it: vertices (n, 3) in m, the triangles per
    class (in the layout's order) and per class with them the survey's class names under its triangles."""
    n, q = layout["vertices"], layout["unit"]
    u, off = read_varints(blob, 3 * n, 0)
    R = np.cumsum(unzigzag(u).reshape(n, 3), axis=0).astype(float)
    V = np.column_stack([layout["x0"] + R[:, 0] * q, layout["y1"] - R[:, 1] * q, layout["base"] + R[:, 2] * q])
    tris = {}
    for c, m in layout["classes"].items():
        u, off = read_varints(blob, 3 * m, off)
        d = unzigzag(u).reshape(m, 3)
        first = np.cumsum(d[:, 0])
        tris[c] = np.column_stack([first, first + d[:, 1], first + d[:, 2]])
    for c, runs in (layout.get("drawRuns") or {}).items():
        _, off = read_varints(blob, 2 * runs, off)
    area = {}
    for c, runs in (layout.get("areaRuns") or {}).items():
        u, off = read_varints(blob, 2 * runs, off)
        rl = u.astype(np.int64).reshape(runs, 2)
        area[c] = np.repeat(np.asarray(layout["area"][c], dtype=object)[rl[:, 0]], rl[:, 1])
    return V, tris, area


COVER_CELL = 10  # m (src/groundWorker.js: src/terrain.js TriIndex's cover)
LOOKUP_CELL = 16  # m (src/groundFile.js: a tile's lookup grid)
GRID = 2.0  # m: this lookup's own grid of candidates (the answer is the page's: every triangle holding the point)


class Survey:
    """The page's survey reads: classAt (GroundLookup.survey's class), covered and classUnder, for arrays of points."""

    def __init__(self, ln):
        with open(os.path.join(ROOT, "data", f"line{ln}.ground.json"), encoding="utf-8") as f:
            self.layout = json.load(f)
        with open(os.path.join(ROOT, "data", f"line{ln}.ground.bin"), "rb") as f:
            self.blob = f.read()
        self.T = self.layout["tile"]
        self.E0, self.N0 = self.layout["origin"]
        self.tiles = {(t["e"], t["n"]): t for t in self.layout["tiles"]}
        self.names = [""]  # the survey's classes (0: none)
        self.ids = {"": 0}
        self.cache = {}
        with open(os.path.join(ROOT, "data", f"line{ln}.dtm.json"), encoding="utf-8") as f:
            dtm = json.load(f)
        self.under = [(a["c"], np.asarray(a["r"], float)[:, :2]) for a in dtm["areas"] if a["l"] < 0 and len(a.get("r") or ()) > 2]

    def _tile(self, key):
        if key in self.cache:
            return self.cache[key]
        t = self.tiles[key]
        V, tris, area = decode_tile(self.blob[t["offset"]:t["offset"] + t["bytes"]], t["layout"])
        x0, y0 = t["e"] * self.T - self.E0, t["n"] * self.T - self.N0
        vx, vy = V[:, 0], V[:, 1]
        TV, TA = [], []
        for c, F in tris.items():
            if c == "wall":
                continue
            a, b, d = F[:, 0], F[:, 1], F[:, 2]
            up = (((vx[a] == vx[b]) & (vy[a] == vy[b])) | ((vx[b] == vx[d]) & (vy[b] == vy[d])) |
                  ((vx[a] == vx[d]) & (vy[a] == vy[d])))
            names = area.get(c)
            ids = (np.array([self._id(s) for s in names], np.int32) if names is not None else np.zeros(len(F), np.int32))
            TV.append(F[~up])
            TA.append(ids[~up])
        TV = np.vstack(TV) if TV else np.zeros((0, 3), np.int64)
        TA = np.concatenate(TA) if TA else np.zeros(0, np.int32)
        # (the 10 m cells the survey's triangles touch, from their corners as decoded)
        cover = set()
        sv = TV[TA > 0]
        if len(sv):
            X, Y = vx[sv], vy[sv]
            i0, i1 = np.floor(X.min(1) / COVER_CELL).astype(np.int64), np.floor(X.max(1) / COVER_CELL).astype(np.int64)
            j0, j1 = np.floor(Y.min(1) / COVER_CELL).astype(np.int64), np.floor(Y.max(1) / COVER_CELL).astype(np.int64)
            for a0, a1, b0, b1 in set(zip(i0.tolist(), i1.tolist(), j0.tolist(), j1.tolist())):
                for i in range(a0, a1 + 1):
                    for j in range(b0, b1 + 1):
                        cover.add(i * 100003 + j)
        # (the page's lookup: 32-bit corners from the tile's corner, heights 32-bit)
        lx = (vx - x0).astype(np.float32).astype(float)
        ly = (vy - y0).astype(np.float32).astype(float)
        lz = V[:, 2].astype(np.float32).astype(float)
        # candidates: each triangle in the GRID cells its box touches (a hair wider: the page's tolerance)
        P = lx[TV], ly[TV]
        side = int(math.ceil(self.T / GRID)) + 1
        gi0 = np.clip(np.floor((P[0].min(1) - 1e-4) / GRID).astype(np.int64), 0, side - 1)
        gi1 = np.clip(np.floor((P[0].max(1) + 1e-4) / GRID).astype(np.int64), 0, side - 1)
        gj0 = np.clip(np.floor((P[1].min(1) - 1e-4) / GRID).astype(np.int64), 0, side - 1)
        gj1 = np.clip(np.floor((P[1].max(1) + 1e-4) / GRID).astype(np.int64), 0, side - 1)
        wi, wj = gi1 - gi0 + 1, gj1 - gj0 + 1
        cnt = wi * wj
        tri = np.repeat(np.arange(len(TV)), cnt)
        k = np.arange(len(tri)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        cell = (gj0[tri] + k // wi[tri]) * side + gi0[tri] + k % wi[tri]
        order = np.argsort(cell, kind="stable")
        start = np.searchsorted(cell[order], np.arange(side * side + 1))
        out = {"x0": x0, "y0": y0, "lx": lx, "ly": ly, "lz": lz, "TV": TV, "TA": TA, "cover": cover, "side": side,
               "start": start, "tris": tri[order]}
        self.cache[key] = out
        return out

    def _id(self, s):
        if s not in self.ids:
            self.ids[s] = len(self.names)
            self.names.append(s)
        return self.ids[s]

    def _keys(self, x, y):
        return (np.floor((x + self.E0) / self.T).astype(np.int64), np.floor((y + self.N0) / self.T).astype(np.int64))

    def survey(self, x, y):
        """(class id per point, 0 where the ground is not the survey's or there is none; its height, NaN off the
        ground): GroundLookup.survey, the highest triangle holding the point (the first of equals)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        cid, zz = np.zeros(len(x), np.int32), np.full(len(x), np.nan)
        ke, kn = self._keys(x, y)
        for e, n in set(zip(ke.tolist(), kn.tolist())):
            if (e, n) not in self.tiles:
                continue
            m = np.flatnonzero((ke == e) & (kn == n))
            g = self._tile((e, n))
            px, py = x[m] - g["x0"], y[m] - g["y0"]
            gi, gj = np.floor(px / GRID).astype(np.int64), np.floor(py / GRID).astype(np.int64)
            ok = (gi >= 0) & (gj >= 0) & (gi < g["side"]) & (gj < g["side"])
            ok &= (np.floor(px / LOOKUP_CELL) < math.floor(self.T / LOOKUP_CELL) + 1) & (np.floor(py / LOOKUP_CELL) < math.floor(self.T / LOOKUP_CELL) + 1)
            c = np.where(ok, gj * g["side"] + gi, 0)
            a, b = g["start"][c], g["start"][c + 1]
            cnt = np.where(ok, b - a, 0)
            pt = np.repeat(np.arange(len(m)), cnt)
            t = g["tris"][np.repeat(a, cnt) + np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)]
            V = g["TV"][t]
            lx, ly, lz = g["lx"], g["ly"], g["lz"]
            ax, ay, bx, by, cx, cy = lx[V[:, 0]], ly[V[:, 0]], lx[V[:, 1]], ly[V[:, 1]], lx[V[:, 2]], ly[V[:, 2]]
            qx, qy = px[pt], py[pt]
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            with np.errstate(invalid="ignore", divide="ignore"):
                w0 = ((by - cy) * (qx - cx) + (cx - bx) * (qy - cy)) / d
                w1 = ((cy - ay) * (qx - cx) + (ax - cx) * (qy - cy)) / d
            w2 = 1 - w0 - w1
            eps = -1e-7
            hit = (d != 0) & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
            z = w0 * lz[V[:, 0]] + w1 * lz[V[:, 1]] + w2 * lz[V[:, 2]]
            pt, t, z = pt[hit], t[hit], z[hit]
            o = np.lexsort((t, -z, pt))
            pt, t, z = pt[o], t[o], z[o]
            first = np.r_[True, pt[1:] != pt[:-1]]
            cid[m[pt[first]]] = g["TA"][t[first]]
            zz[m[pt[first]]] = z[first]
        return cid, zz

    def class_at(self, x, y):
        """dtm.classAt: the survey's class names per point (None off the survey)."""
        cid, _ = self.survey(x, y)
        return np.asarray([self.names[i] or None for i in range(len(self.names))], dtype=object)[cid]

    def covered(self, x, y):
        """dtm.covered: whether the survey is about the point's 10 m cell (the tile's own cells)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.zeros(len(x), bool)
        ke, kn = self._keys(x, y)
        cell = np.floor(x / COVER_CELL).astype(np.int64) * 100003 + np.floor(y / COVER_CELL).astype(np.int64)
        for e, n in set(zip(ke.tolist(), kn.tolist())):
            if (e, n) not in self.tiles:
                continue
            m = np.flatnonzero((ke == e) & (kn == n))
            cv = self._tile((e, n))["cover"]
            out[m] = [c in cv for c in cell[m].tolist()]
        return out

    def class_under(self, x, y):
        """dtm.classUnder: the first underground area holding the point (even-odd), its class; else None."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(len(x), None, dtype=object)
        left = np.ones(len(x), bool)
        for c, r in self.under:
            inside = np.zeros(len(x), bool)
            xj, yj = r[-1]
            for xi, yi in r:
                with np.errstate(invalid="ignore", divide="ignore"):
                    cross = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
                inside ^= cross
                xj, yj = xi, yi
            hit = inside & left
            out[hit] = c
            left &= ~hit
        return out


# ---------------------------------------------------------------- the line, as the page loads it
def load_line(ln):
    with open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8") as f:
        data = json.load(f)
    widen_tram_streets(data)
    return data


def densify(line, max_len=4.0):
    out = [line[0]]
    for i in range(1, len(line)):
        a, b = line[i - 1], line[i]
        n = math.ceil(hyp(b[0] - a[0], b[1] - a[1]) / max_len)
        for k in range(1, n + 1):
            out.append([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n])
    return out


class SegmentIndex:
    """src/worldMesh.js SegmentIndex (no widths): distance to the nearest segment, up to about a cell."""

    def __init__(self, cell=10):
        self.cell, self.map = cell, {}

    def add_line(self, line):
        c = self.cell
        for i in range(1, len(line)):
            a, b = line[i - 1], line[i]
            seg = (a[0], a[1], b[0], b[1])
            for ii in range(math.floor(min(a[0], b[0]) / c), math.floor(max(a[0], b[0]) / c) + 1):
                for jj in range(math.floor(min(a[1], b[1]) / c), math.floor(max(a[1], b[1]) / c) + 1):
                    self.map.setdefault((ii, jj), []).append(seg)

    def dist(self, x, y):
        c = self.cell
        ci, cj = math.floor(x / c), math.floor(y / c)
        best = math.inf
        for i in range(ci - 1, ci + 2):
            for j in range(cj - 1, cj + 2):
                for ax, ay, bx, by in self.map.get((i, j), ()):
                    dx, dy = bx - ax, by - ay
                    l2 = (dx * dx + dy * dy) or 1e-9
                    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
                    best = min(best, hyp(ax + dx * t - x, ay + dy * t - y))
        return best


def widen_tram_streets(data):
    """src/streets.js widenTramStreets: a road with a track along most of it (within 2.6 m of 60 % of its points every
    5 m) is a tram street, 3.2 m wider a track (tracks on both sides of the centre at 30 % of them: two)."""
    idx = SegmentIndex(10)
    for t in data["tracks"]:
        idx.add_line(t["p"])
    for r in data["roads"]:
        if r.get("f") or r["w"] < 5 or len(r["p"]) < 2:
            continue
        n = near = both = 0
        pts = densify(r["p"], 5)
        for i, (x, y) in enumerate(pts):
            n += 1
            if idx.dist(x, y) < 2.6:
                near += 1
            a, c = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
            hx, hy = c[0] - a[0], c[1] - a[1]
            hl = hyp(hx, hy) or 1
            ox, oy = (-hy / hl) * 1.6, (hx / hl) * 1.6
            if idx.dist(x + ox, y + oy) < 0.8 and idx.dist(x - ox, y - oy) < 0.8:
                both += 1
        if near / n < 0.6:
            continue
        r["tram"] = 2 if both / n > 0.3 else 1
        r["w"] += 3.2 * r["tram"]


# ---------------------------------------------------------------- the roads
def pieces(data):
    """The vehicle ways split at every node another vehicle way shares (src/traffic.js: real junctions); footways
    whole. Each piece a dict of its way's tags with its own `p`."""
    uses = {}
    for r in data["roads"]:
        if r.get("f") or len(r["p"]) < 2:
            continue
        for k in {(p[0], p[1]) for p in r["p"]}:
            uses[k] = uses.get(k, 0) + 1
    out = []
    for k, r in enumerate(data["roads"]):
        if len(r["p"]) < 2:
            continue
        if r.get("f"):
            out.append({**r, "src": k})
            continue
        cur = [r["p"][0]]
        for i in range(1, len(r["p"])):
            cur.append(r["p"][i])
            if i < len(r["p"]) - 1 and uses.get((r["p"][i][0], r["p"][i][1]), 0) > 1:
                out.append({**r, "p": cur, "src": k})
                cur = [r["p"][i]]
        out.append({**r, "p": cur, "src": k})
    return out


def jkey(p):
    """src/traffic.js key(): a junction's key."""
    return f"{js_round(p[0])},{js_round(p[1])}"


class Network:
    """The page's traffic network (src/traffic.js Traffic's constructor) built from the line data: the roads and their
    lanes, the footways (OSM's, and the sidewalks beside the roads) linked into one network, and the doors on them."""

    def __init__(self, data, survey, route, back):
        self.survey, self.route, self.back = survey, route, back
        self.pieces = pieces(data)
        # centre lines of all vehicle ways in 20 m cells (_parallelWays), in the page's order
        self.way_idx = {}
        for pi, r in enumerate(self.pieces):
            if r.get("f") or not r.get("c") or len(r["p"]) < 2:
                continue
            for i in range(1, len(r["p"])):
                a, b = r["p"][i - 1], r["p"][i]
                sg = (a[0], a[1], b[0], b[1], pi, bool(r.get("b")), bool(r.get("t")))
                for ix in range(math.floor(min(a[0], b[0]) / 20), math.floor(max(a[0], b[0]) / 20) + 1):
                    for iy in range(math.floor(min(a[1], b[1]) / 20), math.floor(max(a[1], b[1]) / 20) + 1):
                        self.way_idx.setdefault(ix * 100003 + iy, []).append(sg)
        self.roads, foot = [], []
        for pi, r in enumerate(self.pieces):
            if len(r["p"]) < 2:
                continue
            if not r.get("f") and (not r.get("c") or r["w"] < 5):
                continue  # (cars only on public vehicle roads; the page smooths them first, to no effect)
            path = Path(smooth_polyline(r["p"], 3, 6) if len(r["p"]) > 2 else r["p"])
            if path.length < (15 if r.get("f") else 2):
                continue
            if r.get("f"):
                if not r.get("t"):  # (pedestrian underpasses: nobody walks under the ground here)
                    foot.append((pi, path, r))
                continue
            road = {"piece": pi, "src": r["src"], "path": path, "w": r["w"], "o": r.get("o") or 0, "tram": r.get("tram"),
                    "b": r.get("b") or 0, "t": r.get("t") or 0, "ln": r.get("ln"), "lf": r.get("lf"), "lb": r.get("lb"),
                    "ends": [jkey(r["p"][0]), jkey(r["p"][-1])], "fitLo": None, "fitHi": None, "fitMed": None,
                    "along": self.along(path)}
            self.roads.append(road)
        self.fit()
        for road in self.roads:
            self.track_lats(road)
        self.walks = self.build_walks(foot)
        self.lanes = []
        for k, road in enumerate(self.roads):
            self.build_lanes(k, road)
        self.link_walks()
        self.find_doors(data.get("buildings") or [])

    # ------------------------------------------------------------ the tracks
    def track_dist(self, x, y):
        """trackDist(): the distance to the nearest track centre, ours or the opposite direction's."""
        q = self.route.nearest(x, y) if self.route else None
        d = q[0] if q else math.inf
        if self.back:
            q = self.back.nearest(x, y)
            d = min(d, q[0] if q else math.inf)
        return d

    def near_track_share(self, path):
        """nearTrackShare(): the share of the points every 5 m within 4 m of a track."""
        L = path.length
        X, Y, _, _ = path.at(np.arange(math.floor(L / 5) + 1) * 5.0)
        near = sum(1 for x, y in zip(X.tolist(), Y.tolist()) if self.track_dist(x, y) < 4)
        return near / max(1, len(X))

    def along(self, path):
        """The street the tram runs in: over 40 % of its points every 10 m within 7 m of our track (no sidewalks of its
        own: the tram street's footways cover them)."""
        if not self.route:
            return False
        X, Y, _, _ = path.at(np.arange(math.ceil(path.length / 10)) * 10.0)
        near = 0
        for x, y in zip(X.tolist(), Y.tolist()):
            q = self.route.nearest(x, y)
            near += bool(q) and q[0] < 7
        return near / len(X) > 0.4

    # (the samples every 4 m of each road and the 65 points across ±16 m, read in one go)
    def fit(self):
        S = self.survey
        jobs, xs, ys = [], [], []
        L_ = np.arange(65) * 0.5 - 16
        for road in self.roads:
            if road["b"]:
                continue
            L = road["path"].length
            n = math.floor(L / 4) + 1
            x, y, hx, hy = road["path"].at(np.minimum(L, np.arange(n) * 4.0))
            on = np.ones(n, bool) if road["t"] else S.covered(x, y)
            jobs.append((road, n, x, y, hx, hy, on, len(xs)))
            i = np.flatnonzero(on)
            xs.append((x[i, None] + hy[i, None] * L_).ravel())
            ys.append((y[i, None] - hx[i, None] * L_).ravel())
        if not jobs:
            return
        X, Y = np.concatenate(xs), np.concatenate(ys)
        # (a road tunnel: the underground survey of its floor)
        tun = np.concatenate([np.full(len(xs[j[7]]), bool(j[0]["t"])) for j in jobs])
        names = np.full(len(X), None, dtype=object)
        if (~tun).any():
            names[~tun] = S.class_at(X[~tun], Y[~tun])
        if tun.any():
            names[tun] = S.class_under(X[tun], Y[tun])
        k0 = 0
        for road, n, x, y, hx, hy, on, _ in jobs:
            m = int(on.sum()) * 65
            self._fit_one(road, n, x, y, hx, hy, on, names[k0:k0 + m].reshape(-1, 65))
            k0 += m

    def _fit_one(self, road, n, x, y, hx, hy, on, names):
        code = {"road": 1, "tram": 2, "parking": 3, "median": 0 if road["o"] else 4}
        lo, hi, med = [None] * n, [None] * n, [None] * n
        anyfit = False
        rows = iter(names.tolist())
        for i in range(n):
            if not on[i]:
                continue
            row = [code.get(c, 0) for c in next(rows)]
            k, d = 32, 0
            while d <= 16 and not row[k]:
                k = 32 + d if row[32 + d] else 32 - d if row[32 - d] else 32
                d += 1
            if not row[k]:
                continue
            a = b = k
            while a > 0 and (row[a - 1] or (a > 1 and row[a - 2])):
                a -= 1
            while b < 64 and (row[b + 1] or (b < 63 and row[b + 2])):
                b += 1
            while a < b and row[a] != 1:
                a += 1
            while b > a and row[b] != 1:
                b -= 1
            if row[a] != 1:
                continue
            m0 = m1 = -1
            j = a
            while j <= b:
                if row[j] != 4:
                    j += 1
                    continue
                e = j
                while e < b and row[e + 1] == 4:
                    e += 1
                if m0 < 0 or abs((j + e) / 2 - 32) < abs((m0 + m1) / 2 - 32):
                    m0, m1 = j, e
                j = e + 1
            width = (b - a) * 0.5 + 0.5 - ((m1 - m0 + 1) * 0.5 if m0 >= 0 else 0)
            if width > max(road["w"] * 2.2, road["w"] + 9) or a == 0 or b == 64:
                continue
            lo[i] = a * 0.5 - 16.25
            hi[i] = b * 0.5 - 15.75
            if m0 >= 0:
                med[i] = [m0 * 0.5 - 16.25, m1 * 0.5 - 15.75]
            for o in self._parallel_ways(road, float(x[i]), float(y[i]), float(hx[i]), float(hy[i])):
                if 1 < o < hi[i]:
                    hi[i] = max(o / 2, lo[i] + 2.5)
                if lo[i] < o < -1:
                    lo[i] = min(o / 2, hi[i] - 2.5)
            anyfit = True
        if not anyfit:
            return

        def fill(arr, dflt):
            out = []
            for i, v in enumerate(arr):
                if v is not None:
                    out.append(v)
                    continue
                best, bd = dflt, 4
                for d in range(1, 4):
                    if i - d >= 0 and arr[i - d] is not None and d < bd:
                        best, bd = dflt + (arr[i - d] - dflt) * (1 - d / 4), d
                    if i + d < len(arr) and arr[i + d] is not None and d < bd:
                        best, bd = dflt + (arr[i + d] - dflt) * (1 - d / 4), d
                out.append(best)
            return out

        def smooth(arr):
            out = []
            for i in range(len(arr)):
                s = m = 0
                for d in range(-5, 6):
                    if 0 <= i + d < len(arr):
                        w = 6 - abs(d)
                        s += arr[i + d] * w
                        m += w
                out.append(s / m)
            return out

        def limit(arr):
            for i in range(1, len(arr)):
                arr[i] = max(arr[i - 1] - 0.4, min(arr[i - 1] + 0.4, arr[i]))
            for i in range(len(arr) - 2, -1, -1):
                arr[i] = max(arr[i + 1] - 0.4, min(arr[i + 1] + 0.4, arr[i]))
            return arr

        road["fitLo"] = limit(smooth(fill(lo, -road["w"] / 2)))
        road["fitHi"] = limit(smooth(fill(hi, road["w"] / 2)))
        if any(med):
            mid = [(v + road["fitHi"][i]) / 2 for i, v in enumerate(road["fitLo"])]
            road["fitMed"] = [limit([m[0] if m else mid[i] for i, m in enumerate(med)]),
                              limit([m[1] if m else mid[i] for i, m in enumerate(med)])]

    def _parallel_ways(self, road, px, py, phx, phy):
        out, seen = [], set()
        cx, cy = math.floor(px / 20), math.floor(py / 20)
        b, t = bool(road["b"]), bool(road["t"])
        for i in range(cx - 1, cx + 2):
            for j in range(cy - 1, cy + 2):
                for sg in self.way_idx.get(i * 100003 + j, ()):
                    if sg[4] == road["piece"] or sg[5] != b or sg[6] != t or sg in seen:
                        continue
                    seen.add(sg)
                    dx, dy = sg[2] - sg[0], sg[3] - sg[1]
                    ln = hyp(dx, dy) or 1
                    if abs((dx * phx + dy * phy) / ln) < 0.82:
                        continue
                    nx, ny = phy, -phx
                    den = dx * ny - dy * nx
                    if abs(den) < 1e-9:
                        continue
                    u = ((px - sg[0]) * ny - (py - sg[1]) * nx) / den
                    if u < 0 or u > 1:
                        continue
                    qx, qy = sg[0] + dx * u, sg[1] + dy * u
                    off = (qx - px) * nx + (qy - py) * ny
                    if abs(off) < 12:
                        out.append(off)
        return out

    def track_lats(self, road):
        """_trackLats: every 4 m, the lateral offsets (+ right) of the tracks running along the road."""
        path = road["path"]
        L = path.length
        n = math.floor(L / 4) + 1
        X, Y, HX, HY = path.at(np.minimum(L, np.arange(n) * 4.0))
        out, anyt = [], False
        for x, y, hx, hy in zip(X.tolist(), Y.tolist(), HX.tolist(), HY.tolist()):
            lats = []
            for rt in (self.route, self.back):
                if not rt:
                    continue
                q = rt.nearest(x, y)
                if not q or q[0] > road["w"] / 2 + 6:
                    continue
                h = rt.at(q[1])
                if abs(h[2] * hx + h[3] * hy) < 0.85:
                    continue
                lats.append((h[0] - x) * hy - (h[1] - y) * hx)
            out.append(lats)
            anyt = anyt or bool(lats)
        road["trk"] = out if anyt else None

    # ------------------------------------------------------------ lanes
    @staticmethod
    def kerbs(r, s):
        """kerbs(): the two kerb lines at s (m from the centre line, + right): fitted, else the OSM width."""
        if r["fitLo"] is None:
            return -r["w"] / 2, r["w"] / 2
        lo, hi = r["fitLo"], r["fitHi"]
        f = max(0, min(len(lo) - 1, s / 4))
        i = math.floor(f)
        j, u = min(len(lo) - 1, i + 1), f - i
        return lo[i] * (1 - u) + lo[j] * u, hi[i] * (1 - u) + hi[j] * u

    @staticmethod
    def tracks_at(r, s):
        if r["trk"] is None:
            return []
        return r["trk"][max(0, min(len(r["trk"]) - 1, js_round(s / 4)))] or []

    @staticmethod
    def lanes_of(r, d):
        """lanesOf(): lanes in a direction as OSM tags them, else one (half of `lanes` from 4 on a two-way road)."""
        if r["o"]:
            return r["ln"] or 1
        own = r["lf"] if d > 0 else r["lb"]
        if own:
            return own
        return math.floor(r["ln"] / 2) if (r["ln"] or 0) >= 4 else 1

    def lane_offset(self, r, s, d, k=0):
        """laneOffset(): a car's lateral position (+ right of its direction) on lane k of its direction at s."""
        lo, hi = self.kerbs(r, s)
        tk = [t for t in self.tracks_at(r, s) if lo - 0.5 < t < hi + 0.5]
        if d < 0:
            lo, hi = -hi, -lo
            tk = [-t for t in tk]
        n = self.lanes_of(r, d)
        if r["o"]:
            div = lo
        elif r["fitMed"] is not None:
            mL, mR = r["fitMed"]
            f = max(0, min(len(mL) - 1, s / 4))
            i = math.floor(f)
            j, u = min(len(mL) - 1, i + 1), f - i
            div = max(lo, min(hi, -(mL[i] * (1 - u) + mL[j] * u) if d < 0 else mR[i] * (1 - u) + mR[j] * u))
        elif len(tk) >= 2:
            div = (min(tk) + max(tk)) / 2
        else:
            div = (lo + hi) / 2
        band = max(0.1, hi - div)
        step = max(2.6, min(3.25, (band - 1.7) / (n - 0.5))) if n > 1 else 0
        own = [t for t in tk if t > div]
        if band < 3.2 and own:
            return min(own)
        right = hi - min(1.7, band / 2)
        return max(right - k * step, div + min(1.1, band / 2))

    def build_lanes(self, k, r):
        """_buildLanes(): a lane per direction (and per OSM lane) at laneOffset every ~2 m, trimmed 5 m back from both
        junctions, smoothed."""
        L = r["path"].length
        trim = min(5, L * 0.2)
        for d in ([r["o"]] if r["o"] else [1, -1]):
            for sel in range(self.lanes_of(r, d)):
                n = max(2, math.ceil((L - 2 * trim) / 2))
                u = trim + ((L - 2 * trim) * np.arange(n + 1)) / n
                sr = u if d > 0 else L - u
                X, Y, HX, HY = r["path"].at(sr)
                pts = []
                for x, y, hx, hy, s_ in zip(X.tolist(), Y.tolist(), HX.tolist(), HY.tolist(), sr.tolist()):
                    hx, hy = hx * d, hy * d
                    off = self.lane_offset(r, s_, d, sel)
                    pts.append([x + hy * off, y - hx * off])
                path = Path(smooth_polyline(pts, 1, 6) if len(pts) > 3 else pts)
                self.lanes.append({"road": k, "dir": d, "sel": sel, "trim": trim, "path": path,
                                   "from": r["ends"][0 if d > 0 else 1], "to": r["ends"][1 if d > 0 else 0]})

    # ------------------------------------------------------------ footways
    def build_walks(self, foot):
        """The constructor's walks, in its order (by the ways' pieces): each OSM footway over 30 m and away from the
        tracks, cut where it lies on the surveyed carriageway for more than 6 m; and beside each road from 6 m wide (not
        the tram street, not on a bridge or in a tunnel) a sidewalk each side, 1 m into the first sidewalk, paving or
        cycle way within 8 m out from the kerb where the survey is about, else 1.5 m beyond the kerb."""
        S, out = self.survey, []
        # footways: the survey's class every 2 m (a footway on a bridge: whole)
        reads = [(pi, path, r, path.at(np.arange(math.floor(path.length / 2) + 1) * 2.0))
                 for pi, path, r in foot if S is not None and not r.get("b")]
        cls = (S.class_at(np.concatenate([q[3][0] for q in reads]), np.concatenate([q[3][1] for q in reads]))
               if reads else [])
        on_all, k0, runs_of = np.isin(cls, ["road", "parking", "tram"]), 0, {}
        for pi, path, r, (X, Y, _, _) in reads:
            on = on_all[k0:k0 + len(X)].tolist()
            k0 += len(X)
            keep, cur, i = [], [], 0
            while i < len(on):
                j = i
                while j < len(on) and on[j]:
                    j += 1
                if j - i > 3:
                    if len(cur) > 1:
                        keep.append(cur)
                    cur, i = [], j
                    continue
                for k in range(i, min(max(j, i + 1), len(on))):
                    cur.append([float(X[k]), float(Y[k])])
                i = max(j, i + 1)
            if len(cur) > 1:
                keep.append(cur)
            runs_of[pi] = [Path(pts) for pts in keep]
        for pi, path, r in foot:
            for wp in runs_of.get(pi, [path]):
                if wp.length > 30 and self.near_track_share(wp) < 0.2:
                    out.append((pi, 0, {"path": wp, "deck": bool(r.get("b")), "way": r["src"], "link": False}))
        # sidewalks: every 3 m, whether the survey is about, and its classes 0.5-8 m out from each kerb
        side_roads = [r for r in self.roads if not r["along"] and r["w"] >= 6 and not r["b"] and not r["t"]]
        D = np.arange(1, 17) * 0.5
        for road in side_roads:
            L = road["path"].length
            s = np.arange(math.floor(L / 3) + 1) * 3.0
            X, Y, HX, HY = road["path"].at(np.minimum(s, L))
            cov = S.covered(X, Y) if S is not None else np.zeros(len(X), bool)
            kb = [self.kerbs(road, v) for v in s.tolist()]
            for order, side in enumerate((1, -1)):
                kerb = np.array([k[1] if side > 0 else k[0] for k in kb])
                off = kerb + side * 1.5
                c = np.flatnonzero(cov)
                if len(c):
                    o = kerb[c, None] + side * D
                    names = S.class_at((X[c, None] + HY[c, None] * o).ravel(), (Y[c, None] - HX[c, None] * o).ravel())
                    walk = np.isin(names, ["sidewalk", "paved", "cycle"]).reshape(len(c), len(D))
                    first = walk.argmax(1)
                    off[c] = np.where(walk.any(1), o[np.arange(len(c)), first] + side * 1.0, np.nan)
                runs, cur = [], []
                for x, y, hx, hy, v in zip(X.tolist(), Y.tolist(), HX.tolist(), HY.tolist(), off.tolist()):
                    if math.isnan(v):
                        if len(cur) > 2:
                            runs.append(cur)
                        cur = []
                        continue
                    cur.append([x + hy * v, y - hx * v])
                if len(cur) > 2:
                    runs.append(cur)
                for pts in runs:
                    wp = Path(smooth_polyline(pts, 1, 4))
                    if wp.length > 15 and self.near_track_share(wp) < 0.2:
                        out.append((road["piece"], 1 + order, {"path": wp, "deck": False, "way": road["src"], "link": False}))
        out.sort(key=lambda e: (e[0], e[1]))  # (stable: each piece's own runs in order)
        return [w for _, _, w in out]

    def link_walks(self):
        """_linkWalks(): each footway's ends joined to the other walks: up to the four nearest within 3 m (else the nearest
        within 15 m); one under 0.5 m away directly, else by a link walk where the straight way there keeps clear of the
        tracks (2.8 m)."""
        C, grid = 5, {}
        base = list(self.walks)
        for wi, w in enumerate(base):
            w["links"] = [[], []]
            X, Y, _, _ = w["path"].at(np.arange(math.floor(w["path"].length) + 1, dtype=float))
            for s, (x, y) in enumerate(zip(X.tolist(), Y.tolist())):
                grid.setdefault(math.floor(x / C) * 100003 + math.floor(y / C), []).append((wi, s, x, y))

        def around(me, x, y, R):
            best, n, ci, cj = {}, math.ceil(R / C), math.floor(x / C), math.floor(y / C)
            for i in range(ci - n, ci + n + 1):
                for j in range(cj - n, cj + n + 1):
                    for w, s, px, py in grid.get(i * 100003 + j, ()):
                        if w == me:
                            continue
                        d = hyp(px - x, py - y)
                        if d <= R and (w not in best or d < best[w][2]):
                            best[w] = (w, s, d, px, py)
            return sorted(best.values(), key=lambda c: c[2])

        def clear(x0, y0, x1, y1):
            L = hyp(x1 - x0, y1 - y0)
            t = 0
            while t <= L:
                u = t / (L or 1)
                if self.track_dist(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u) < 2.8:
                    return False
                t += 1
            return True

        for wi, w in enumerate(base):
            for e in (0, 1):
                s0 = w["path"].length if e else 0
                px, py, _, _ = w["path"].at1(s0)
                cands = around(wi, px, py, 3)[:4] or around(wi, px, py, 15)[:1]
                for cw, cs, d, cx, cy in cands:
                    if d < 0.5:
                        w["links"][e].append((cw, cs))
                        continue
                    if not clear(px, py, cx, cy):
                        continue
                    self.walks.append({"path": Path([[px, py], [cx, cy]]), "deck": False, "way": None, "link": True,
                                       "links": [[(wi, s0)], [(cw, cs)]]})
                    w["links"][e].append((len(self.walks) - 1, 0))

    def find_doors(self, buildings):
        """_findDoors(): a building's door where its outline (every 3 m) comes nearest a footway point (every 2 m) within
        8 m: on that walk, 1.5 m into the building towards its middle."""
        from scipy.spatial import cKDTree
        pts, C = [], 5
        for wi, w in enumerate(self.walks):
            if w["link"]:
                continue
            X, Y, _, _ = w["path"].at(np.arange(math.floor(w["path"].length / 2) + 1) * 2.0)
            pts += [(wi, s * 2, x, y) for s, (x, y) in enumerate(zip(X.tolist(), Y.tolist()))]
        self.doors = []
        if not pts:
            return
        P = np.array([(p[2], p[3]) for p in pts])
        tree = cKDTree(P)
        for b in buildings:
            ring = b.get("p")
            if not ring or len(ring) < 3:
                continue
            cx = cy = 0
            for q in ring:
                cx += q[0]
                cy += q[1]
            cx /= len(ring)
            cy /= len(ring)
            fs = []
            for i in range(len(ring)):
                a, c = ring[i], ring[(i + 1) % len(ring)]
                L = hyp(c[0] - a[0], c[1] - a[1])
                t = 0
                while t <= L:
                    fs.append((a[0] + (c[0] - a[0]) * (t / (L or 1)), a[1] + (c[1] - a[1]) * (t / (L or 1))))
                    t += 3
            best = None
            for k, near in enumerate(tree.query_ball_point(fs, 8.001)):
                fx, fy = fs[k]
                for m in near:
                    d = hyp(P[m, 0] - fx, P[m, 1] - fy)
                    if d > 8:
                        continue
                    # (the page's order: the outline's points, then the 5 m cells x, y, then the points in a cell)
                    key = (d, k, math.floor(P[m, 0] / C), math.floor(P[m, 1] / C), m)
                    if best is None or key < best[0]:
                        best = (key, m, fx, fy)
            if best is None:
                continue
            (_, m, fx, fy) = best
            wi, s, x, y = pts[m]
            to_c = hyp(cx - fx, cy - fy) or 1
            self.doors.append({"walk": wi, "s": s, "x": x, "y": y, "ix": fx + ((cx - fx) / to_c) * 1.5,
                               "iy": fy + ((cy - fy) / to_c) * 1.5})


# ---------------------------------------------------------------- the file
def walk_record(w):
    """A walk as the file keeps it: its points (cm), whether it is a link (a crossing or a join) or on a bridge's deck
    (with its way, data.roads' index: the deck's height, src/terrain.js way()), its links at each end ([walk, s cm])."""
    out = {"p": [cm(v) for v in w["path"].p.ravel().tolist()]}
    if w["link"]:
        out["link"] = 1
    if w["deck"]:
        out["deck"] = 1
        out["way"] = w["way"]
    out["links"] = [[[k, cm(s)] for k, s in e] for e in w["links"]]
    return out


def door_record(d):
    """A door: [its walk, s, the point on the walk, the point 1.5 m inside the building] (cm)."""
    return [d["walk"], cm(d["s"]), cm(d["x"]), cm(d["y"]), cm(d["ix"]), cm(d["iy"])]


def lane_record(ln):
    """A lane as the file keeps it: its road (the index), direction, lane and points (cm)."""
    return {"road": ln["road"], "dir": ln["dir"], "sel": ln["sel"], "p": [cm(v) for v in ln["path"].p.ravel().tolist()]}


def road_record(r):
    """A road as the file keeps it (positions in cm)."""
    out = {"p": [cm(v) for v in r["path"].p.ravel().tolist()], "w": r["w"], "ends": r["ends"]}
    for k in ("o", "b", "t"):
        if r[k]:
            out[k] = r[k]
    for k in ("tram", "ln", "lf", "lb"):
        if r[k] is not None:
            out[k] = r[k]
    if r["fitLo"] is not None:
        out["lo"] = [cm(v) for v in r["fitLo"]]
        out["hi"] = [cm(v) for v in r["fitHi"]]
    if r["fitMed"] is not None:
        out["med"] = [[cm(v) for v in a] for a in r["fitMed"]]
    if r["trk"] is not None:
        out["trk"] = [[cm(v) for v in a] for a in r["trk"]]
    return out


def build(ln, log=print):
    t0 = time.time()
    data = load_line(ln)
    survey = Survey(ln)
    route = Route(data["path"], data.get("pathExt"))
    back = Route(data["pathBack"]) if len(data.get("pathBack") or ()) > 1 else None
    net = Network(data, survey, route, back)
    recs = [road_record(r) for r in net.roads]
    fitted = sum(1 for r in net.roads if r["fitLo"] is not None)
    links = sum(1 for w in net.walks if w["link"])
    log(f"line {ln}: {len(recs)} roads ({fitted} fitted to the survey, {sum(1 for r in net.roads if r['fitMed'])} with a "
        f"median, {sum(1 for r in net.roads if r['trk'])} with tracks), {len(net.lanes)} lanes, {len(net.walks)} walks "
        f"({links} links), {len(net.doors)} doors, {time.time() - t0:.1f} s")
    return {"line": str(ln), "version": VERSION, "roads": recs, "lanes": [lane_record(x) for x in net.lanes],
            "walks": [walk_record(w) for w in net.walks], "doors": [door_record(d) for d in net.doors], "fitted": fitted}


def write(ln, net):
    import sources
    from atomic import replacing
    n, fitted = len(net["roads"]), net.pop("fitted")
    net["provenance"] = sources.stamp("network.py", {
        "roads": sources.entry("streets", [fitted, 0, n - fitted],
                               "roads: OSM's ways split at their junctions; kerbs fitted to the survey where it has them"),
        "lanes": sources.single("streets", "osm", len(net["lanes"]), "lanes: each road's, beside its kerbs and tracks"),
        "walks": sources.single("streets", "osm", len(net["walks"]),
                                "walks: OSM's footways, the sidewalks the survey shows beside the roads, their links"),
        "doors": sources.single("buildings", "osm", len(net["doors"]), "doors: where a building comes nearest a walk")})
    net["attribution"] = sources.attribution(net["provenance"])
    p = os.path.join(ROOT, "data", f"line{ln}.network.json")
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(net, f, separators=(",", ":"), ensure_ascii=False)
    return p


# ---------------------------------------------------------------- the parity with the page
# (the page's network as the file keeps it: src/traffic.js Traffic of the shift started as a player starts it)
PAGE_ROADS = """async () => {
  const { startShift } = await import('/tools/bench/shift.js');
  await startShift({ timeout: 300 });
  const cm = (v) => Math.round(v * 100), T = window.traffic, wi = new Map(T.walks.map((w, i) => [w, i]));
  const pts = (path) => path.p.flatMap(([x, y]) => [cm(x), cm(y)]);
  const lanes = T.laneList.map((l) => ({ road: l.k, dir: l.dir, sel: l.sel, p: pts(l.path) }));
  const walks = T.walks.map((w) => {
    const o = { p: pts(w.path) };
    if (w.link) o.link = 1;
    if (w.deck) o.deck = 1;
    o.links = w.links.map((e) => e.map((x) => [wi.get(x.walk), cm(x.s)]));
    return o;
  });
  const doors = T.doors.map((d) => [wi.get(d.walk), cm(d.s), cm(d.x), cm(d.y), cm(d.ix), cm(d.iy)]);
  const roads = T.roads.map((r) => {
    const o = { p: r.path.p.flatMap(([x, y]) => [cm(x), cm(y)]), w: r.w, ends: r.ends };
    for (const k of ['o', 'b', 't']) if (r[k]) o[k] = r[k];
    for (const k of ['tram', 'ln', 'lf', 'lb']) if (r[k] != null) o[k] = r[k];
    if (r.fitLo) { o.lo = r.fitLo.map(cm); o.hi = r.fitHi.map(cm); }
    if (r.fitMed) o.med = r.fitMed.map((a) => a.map(cm));
    if (r.trk) o.trk = r.trk.map((a) => a.map(cm));
    return o;
  });
  return { roads, lanes, walks, doors };
}"""


def page_roads(lines, browser=None):
    """{line: {part: the page's records}} from headless Chromium (tools/headless.py's page; `browser`, else one launched on the
    GPU, tools/gpu.py)."""
    import faulthandler

    from headless import load_page, serve, stop_server
    faulthandler.dump_traceback_later(900 * len(lines) + 600, exit=True)
    out = {}
    server, url = serve(0)
    try:
        if browser is None:
            from playwright.sync_api import sync_playwright

            import gpu
            with sync_playwright() as pw:
                b = gpu.launch(pw)[0]
                try:
                    return page_roads(lines, b)
                finally:
                    b.close()
        for ln in lines:
            page, errors, load = load_page(browser, url, ln, 600, {"keepgeo": False})
            if isinstance(load, dict):
                raise RuntimeError(f"line {ln}: the load failed: {load} {errors[:3]}")
            out[ln] = page.evaluate(PAGE_ROADS)
            page.close()
    finally:
        stop_server(server)
        faulthandler.cancel_dump_traceback_later()
    return out


POSITIONS = ("p", "lo", "hi", "med", "trk")  # (the fields in cm: a gap of 1 cm is the rounding's)


def ident(r):
    """A record's identity where the lists' lengths differ: a road's junctions, a lane's road, direction and lane."""
    return tuple(r["ends"]) if "ends" in r else (r.get("road"), r.get("dir"), r.get("sel"))


def comparable(r):
    """A record as the parity compares it: a door's list as {walk, p}; without what only the file keeps (a deck walk's
    way: the page keeps the way's height function instead)."""
    if isinstance(r, list):
        return {"walk": r[0], "p": r[1:]}
    return {k: v for k, v in r.items() if k != "way"}


def compare(page, built):
    """The build's records (roads, lanes, walks, doors) against the page's, in order: those the same to the cm (`exact`)
    and within 1 cm (`equal`), and per field those over 1 cm apart (with the largest gap, cm, and the first one)."""
    page, built = [comparable(r) for r in page], [comparable(r) for r in built]
    rep = {"page": len(page), "build": len(built), "exact": 0, "equal": 0, "fields": {}}
    if len(page) != len(built):
        pe, be = {ident(r) for r in page}, {ident(r) for r in built}
        rep["only page"] = sorted(pe - be, key=str)[:10]
        rep["only build"] = sorted(be - pe, key=str)[:10]
        return rep

    def flat(v):
        if v is None:
            return None
        if v and isinstance(v[0], list):
            return [len(v)] + [len(a) for a in v] + [x for a in v for x in a]
        return v

    for i, (a, b) in enumerate(zip(page, built)):
        rep["exact"] += a == b
        same = True
        for k in sorted(set(a) | set(b)):
            va, vb = a.get(k), b.get(k)
            if va == vb:
                continue
            if k in POSITIONS:
                fa, fb = flat(va), flat(vb)
                if fa is not None and fb is not None and len(fa) == len(fb):
                    gap = max(abs(x - y) for x, y in zip(fa, fb))
                    if gap <= 1:
                        continue
                else:
                    gap = None
            else:
                gap = None
            same = False
            f = rep["fields"].setdefault(k, {"roads": 0, "max cm": 0, "first": None})
            f["roads"] += 1
            if gap is not None:
                f["max cm"] = max(f["max cm"], gap)
            if f["first"] is None:
                f["first"] = {"i": i, "id": ident(a), "page": str(va)[:120], "build": str(vb)[:120]}
        rep["equal"] += same
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--parity", action="store_true", help="also compare with the page's own roads (headless Chromium)")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    lines = [s.strip() for s in a.lines.split(",") if s.strip()]
    built = {}
    for ln in lines:
        net = build(ln)
        built[ln] = {k: net[k] for k in PARTS}
        if not a.no_write:
            print(write(ln, net))
    if a.parity:
        from baseline_store import HeavyJob
        with HeavyJob("network parity"):
            page = page_roads(lines)
        bad = 0
        for ln in lines:
            for part in PARTS:
                rep = compare(page[ln][part], built[ln][part])
                print(f"line {ln} {part}: {json.dumps(rep, ensure_ascii=False)}")
                bad += rep["equal"] != rep["page"] or rep["page"] != rep["build"]
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
