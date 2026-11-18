# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network as a layer the build makes (#658): what each shift's Start built from the survey, built once here.

    python -P -E tools/network.py --lines 37                    # data/line37.network.json (after ground_mesh.py)

The design note (docs/decisions/2026-11-18-network-layer.md): the roads, their lanes, the footways, the doors, the
signals, and what the platforms and stops read of the survey. The page builds none
of it (src/traffic.js, src/platforms.js read the file): its rules were ported here whole and in its order, and before
the page's went its network and this one were the same to the cm on lines 9, 17, 22, 23 and 37 (#667, #668):
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
- `_findDoors`: a building's door where its outline comes nearest a walk;
- the signals (src/game.js `_initSignals`, `_initGauntlets`, `_crossRoad`; src/traffic.js `_bindSignals`, `_stopLine`,
  `_bindPedHeads`): the game's signals bound to the lanes ending at their junctions, each lane's stop line (OSM's where
  data/lineN.signals.json has one, else the junction's edge, never on a zebra) and its head; the pedestrian heads at
  OSM's signalled crossings;
- src/platforms.js `buildPlatforms`, `buildStop`: whether the survey draws each OSM platform, and for each of our stops
  with each set's stop point (src/game.js `_stopZone`) whether it draws the stand-in platform and where its platform's
  edge holds the shelter.

The survey is read as the page reads it: the ground file's triangles (data/lineN.ground.*, tools/ground_mesh.py), the
highest holding the point and the survey's class under it (src/groundFile.js GroundLookup.survey), the 10 m cells the
survey covers (`covered`), and data/lineN.dtm.json's underground areas (src/terrain.js classUnder). The arithmetic is
the page's, in its order, with Math.hypot as V8 computes it (js_hypot).

The file, data/lineN.network.json, positions and heights in cm (a path flat x, y):
- `roads`: each with its points `p`, its OSM tags (`w` with the tracks, `o`, `b`, `t`, `tram`, `ln`, `lf`, `lb`), its
  junctions' keys `ends` (src/traffic.js key()), and where the survey fitted it its kerbs `lo`, `hi` and median `med`
  (from the centre line, + right, every 4 m), and the tracks on it `trk`; on a bridge or in a tunnel its OSM `way`
  (data.roads' index: the chain its height function spans, src/terrain.js way());
- `lanes`: each lane's `road` (its index), `dir`, `sel` (the lane of its direction) and points `p`;
- `walks`: each walk's points `p`, `link` for a crossing or a join, `deck` (with its `way`, data.roads' index) on a
  bridge, and its `links` at each end ([walk, s]);
- `doors`: [walk, s, x, y, ix, iy]: the point on the walk and the one 1.5 m inside the building;
- `lights`: each lane bound to a signal: its `lane`, the `sig` (data.signals' index), `kind` ('along' the tram street or
  'cross'), its `head`, the stop line `back` m before the lane's end and where it came from (`src`: osm, edge, short);
- `heads`: each car signal head's `p` and `face` (mrad); `lightSigs`: the signals with lanes, in order;
- `pedCross`: each signalled crossing's node `p`, its walking direction `c` (×10⁴), `sig`, `along` and `heads`;
  `pedHeads`: their heads' `p` and `face`;
- `overBridge`: the signals (data.signals' indexes) over a bridge, on the road under it: the game leaves them out;
- `platforms`: each placed OSM platform's index `i` in data.platforms, its `name` and whether the survey draws it
  (`surveyed`: no strip of the page's);
- `stops`: each of our stops (data.stops), by the set (1 car, 2 cars): `stand`, whether its stand-in platform is drawn,
  and `outer`, the shelter's outer edge (cm right of the track) where our OSM platform stands, else null.

No heights: what Start places stands on the drawn ground, the page reading it at load while every tile's lookup is held
(src/main.js settleNetwork), or once its tile's lookup comes (ground.later). The ground file is not yet the settled
surface: the page fits the road tunnels' mouths into it and blends the track's profile beside the route (measured
against the page, the file's heights stood up to 7.8 m off at a head by the Blanka tunnel's mouth, 2.8 m at a bridge's
abutment beside the route).
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

    def heading(self, s, span=6):
        """heading(): the chord between s - span and s + span, (hx, hy)."""
        a, b = self.at(s - span), self.at(s + span)
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = hyp(dx, dy) or 1
        return dx / ln, dy / ln

    def nearest_on_heading(self, x, y, hx, hy, min_align=0.5):
        """nearestOnHeading(): the nearest point whose heading is within acos(min_align) of (hx, hy): (d, s) or None."""
        near = self.nearest(x, y)
        if near:
            h = self.heading(near[1], 3)
            if h[0] * hx + h[1] * hy > min_align:
                return near
        cx, cy = math.floor(x / 40), math.floor(y / 40)
        out = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in self.grid.get((cx + dx) * 100003 + cy + dy, ()):
                    if q[3] + 1 >= len(self.samples):
                        continue
                    r = self.samples[q[3] + 1]
                    ex, ey = r[0] - q[0], r[1] - q[1]
                    l2 = ex * ex + ey * ey
                    if l2 < 1e-9 or (ex * hx + ey * hy) / math.sqrt(l2) <= min_align:
                        continue
                    t = max(0.0, min(1.0, ((x - q[0]) * ex + (y - q[1]) * ey) / l2))
                    d = hyp(q[0] + ex * t - x, q[1] + ey * t - y)
                    if out is None or d < out[0]:
                        out = (d, q[2] + (r[2] - q[2]) * t)
        return out

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


class TerrainGrid:
    """src/terrain.js Terrain: the line's coarse terrain grid (data.terrain: int16 in base64, rows going south), heights
    on the two triangles of each cell as the page draws them; what answers past the ground file's tiles."""

    def __init__(self, t):
        import base64
        raw = np.frombuffer(base64.b64decode(t["data"]), "<i2").astype(float)
        self.h = (t["base"] + raw * t["scale"]).astype(np.float32).astype(float)
        self.x0, self.y0, self.dx, self.dy, self.nx, self.ny = t["x0"], t["y0"], t["dx"], t["dy"], t["nx"], t["ny"]

    def height(self, x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        fx, fy = (x - self.x0) / self.dx, (y - self.y0) / self.dy
        ix, iy = np.floor(fx).astype(np.int64), np.floor(fy).astype(np.int64)
        tx, ty = fx - ix, fy - iy

        def cell(i, j):
            return self.h[np.clip(j, 0, self.ny - 1) * self.nx + np.clip(i, 0, self.nx - 1)]

        a, b, c, d = cell(ix, iy), cell(ix + 1, iy), cell(ix, iy + 1), cell(ix + 1, iy + 1)
        return np.where(tx + ty <= 1, a + (b - a) * tx + (c - a) * ty, d + (c - d) * (1 - tx) + (b - d) * (1 - ty))


class Survey:
    """The page's survey reads: classAt (GroundLookup.survey's class), covered and classUnder, for arrays of points."""

    def __init__(self, ln, terrain=None):
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
        self.grid = TerrainGrid(terrain) if terrain else None

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
    """The line data as src/main.js loads it: data/lineN.json, OSM's traffic signals where the line has them
    (data/lineN.signals.json as `osmSignals`), the tram streets widened."""
    with open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8") as f:
        data = json.load(f)
    p = os.path.join(ROOT, "data", f"line{ln}.signals.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            data["osmSignals"] = json.load(f)
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


# ---------------------------------------------------------------- the signals
def resample_heights(arr, step, n, at):
    """src/heights.js resampleHeights: `arr` every `step` m read every `at` m, n samples, 32-bit (NaN without one)."""
    out, L = np.empty(n, np.float32), len(arr)
    for i in range(n):
        k = (i * at) / step
        i0 = min(math.floor(k), L - 1)
        f = k - i0
        a, b = arr[i0], arr[min(i0 + 1, L - 1)]
        out[i] = np.nan if a is None else a if f < 1e-6 or i0 + 1 >= L else np.nan if b is None else a + (b - a) * f
    return out


class Profile:
    """src/terrain.js Profile, what the signals read of it: the top of rail every 2 m and the spans on bridges."""

    def __init__(self, route, data):
        self.step, self.route = 2, route
        self.n = math.ceil(route.length / self.step) + 1
        h = data["heights"]
        self.z = [float(v) for v in resample_heights(h["path"], h["step"], self.n, self.step)]
        self.bridges = data.get("spans") or []

    def height(self, s):
        f = max(0, min(self.n - 1.001, s / self.step))
        i = math.floor(f)
        t = f - i
        return self.z[i] * (1 - t) + self.z[i + 1] * t


class Signals:
    """The junctions' car signals as the page binds them (src/game.js _initSignals, _initGauntlets, _crossRoad;
    src/traffic.js _bindSignals, _stopLine): the game's signals (the build's placement, without those dropped, those over
    a bridge on the road under it, and those an interlaced track's signal replaces), each with a crossing road bound to
    the lanes ending at its junction: the stop line, the kind of approach and a head 4 m past the line."""

    def __init__(self, data, survey, route, back, net):
        self.data, self.survey, self.route, self.back, self.net = data, survey, route, back, net
        self.profile = Profile(route, data)
        self.signals = self.live()
        self.bind()

    def over_bridge(self, s):
        """profile.overBridge(): well inside a span and over 3 m above the ground under it (the road underneath's):
        dtm.heightAt, else the ground's (the highest triangle there), past the tiles the terrain grid."""
        if not any(a + 8 < s < b - 8 for a, b in self.profile.bridges):
            return False
        x, y, _, _ = self.route.at(s)
        _, z = self.survey.survey([x], [y])
        zg = float(z[0]) if not np.isnan(z[0]) or self.survey.grid is None else float(self.survey.grid.height([x], [y])[0])
        return self.profile.height(s) - zg > 3

    def live(self):
        built = self.data.get("signals") or []
        if not any("rule" in d for d in built):
            raise ValueError("the signals have no placement (tools/placement.py): the network binds the build's")
        sigs = [{**d, "i": k} for k, d in enumerate(built) if not d.get("drop") and not self.over_bridge(d["cross"])]
        sigs.sort(key=lambda d: d["s"])
        sigs = self.gauntlets(sigs)
        for sig in sigs:
            sig["xroad"] = None if sig.get("gauntlet") else self.cross_road(sig["cross"])
        return sigs

    def gauntlets(self, sigs):
        """_initGauntlets(): where the opposite track shares ours over 25 m (interlaced track), the signals in it and
        30 m before it go, and its own signal comes (never bound to lanes)."""
        back = self.back
        if not back:
            return sigs
        segs, cur, s = [], None, 0
        while s < self.route.length:
            x, y, hx, hy = self.route.at(s)
            n = back.nearest_on_heading(x, y, -hx, -hy)
            if n and n[0] < 1.8:
                if not cur or n[1] > cur[2] or cur[2] - n[1] > 15:
                    cur = [s, s, n[1]]
                    segs.append(cur)
                else:
                    cur[1], cur[2] = s, n[1]
            else:
                cur = None
            s += 3
        for a, b, _ in segs:
            if b - a < 25:
                continue
            s0, s1 = a - 6, b + 6
            pa, pb = self.route.at(s0), self.route.at(s1)
            enter = back.nearest_on_heading(pb[0], pb[1], -pb[2], -pb[3])
            ext = back.nearest_on_heading(pa[0], pa[1], -pa[2], -pa[3])
            if not enter or not ext or enter[1] >= ext[1]:
                continue
            sigs = [x for x in sigs if not (s0 - 30 < x["s"] < s1)]
            sigs.append({"s": s0 - 4, "cross": s0, "gauntlet": True})
        sigs.sort(key=lambda d: d["s"])
        return sigs

    def cross_road(self, s_cross):
        """_crossRoad(): whether a car road crosses the route at the crossing (within 15 m along it, at over ~37°), with
        15 m of it each side to queue on (its way followed on through OSM's splits); True or None."""
        R, roads = self.route, self.data["roads"]
        px, py, _, _ = R.at(s_cross)
        hx, hy = R.heading(s_cross, 6)

        def side(p):
            return hx * (p[1] - py) - hy * (p[0] - px)

        best = None
        for ri, r in enumerate(roads):
            if not r.get("c") or r["w"] < 5 or r.get("b") or r.get("f"):
                continue
            P = r["p"]
            for i in range(1, len(P)):
                a, b = P[i - 1], P[i]
                if min(hyp(a[0] - px, a[1] - py), hyp(b[0] - px, b[1] - py)) > 80:
                    continue
                fa, fb = side(a), side(b)
                if fa * fb >= 0:
                    continue
                t = fa / (fa - fb)
                x, y = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                along = abs((x - px) * hx + (y - py) * hy)
                ln = hyp(b[0] - a[0], b[1] - a[1]) or 1
                cos = abs(((b[0] - a[0]) * hx + (b[1] - a[1]) * hy) / ln)
                if along > 15 or cos > 0.8:
                    continue
                if best is None or along < best[4]:
                    best = (ri, i, x, y, along)
        if best is None:
            return None
        ri, i = best[0], best[1]
        X0 = [best[2], best[3]]

        def walk(pts):
            out, acc, prev, used = [], 0, X0, {ri}
            while acc < 45:
                for q in pts:
                    acc += hyp(q[0] - prev[0], q[1] - prev[1])
                    out.append(q)
                    prev = q
                    if acc >= 45:
                        break
                if acc >= 45 or len(out) < 1:
                    break
                end = out[-1]
                before = out[-2] if len(out) > 1 else X0
                dx, dy = end[0] - before[0], end[1] - before[1]
                dl = hyp(dx, dy) or 1
                nxt = None
                for oi, o in enumerate(roads):
                    if oi in used or o.get("f") or len(o["p"]) < 2:
                        continue
                    for first, rest in ((o["p"][0], o["p"][1:]), (o["p"][-1], o["p"][:-1][::-1])):
                        if hyp(first[0] - end[0], first[1] - end[1]) > 1 or not rest:
                            continue
                        ex, ey = rest[0][0] - end[0], rest[0][1] - end[1]
                        el = hyp(ex, ey) or 1
                        if (dx * ex + dy * ey) / (dl * el) > 0.7:
                            nxt = (oi, rest)
                            break
                    if nxt:
                        break
                if not nxt:
                    break
                used.add(nxt[0])
                pts = nxt[1]
            return out

        P = roads[ri]["p"]
        bk, fw = walk(P[:i][::-1]), walk(P[i:])
        if len(bk) < 1 or len(fw) < 1:
            return None
        line = [*bk[::-1], X0, *fw]
        cum = [0.0]
        for k in range(1, len(line)):
            cum.append(cum[-1] + hyp(line[k][0] - line[k - 1][0], line[k][1] - line[k - 1][1]))
        sx, length = cum[len(bk)], cum[-1]
        return None if sx < 15 or length - sx < 15 else True

    # ------------------------------------------------------------ the binding
    def bind(self):
        net = self.net
        jpos = {}
        for road in net.roads:
            p = net.pieces[road["piece"]]["p"]
            jpos[road["ends"][0]] = p[0]
            jpos[road["ends"][1]] = p[-1]
        self.jpos = jpos
        lanes_to = {}
        for k, ln in enumerate(net.lanes):
            ln["id"] = k
            lanes_to.setdefault(ln["to"], []).append(ln)
        self.zebras = [r["p"] for r in self.data["roads"] if r.get("z")]
        self.road_pts = [(k, np.asarray(r["path"].p)) for k, r in enumerate(net.roads) if not r["t"] and not r["b"]]
        self.osm_stops = (self.data.get("osmSignals") or {}).get("stop") or []
        self.heads, self.lights, self.light_sigs = [], [], []
        bound = set()
        for sig in self.signals:
            if not sig.get("xroad") or sig.get("gauntlet") or sig.get("demand"):
                continue
            Px, Py, _, _ = self.route.at(sig["cross"])
            hx, hy = self.route.heading(sig["cross"], 6)
            near = None  # (the roads within 35 m of the crossing: _stopLineAt's streets crossing ours)
            n = 0
            for key, pos in jpos.items():
                far = hyp(pos[0] - Px, pos[1] - Py)
                if far > 50:
                    continue
                for lane in lanes_to.get(key, ()):
                    if lane["id"] in bound:
                        continue
                    if far > 25 and self.osm_stop(lane, Px, Py) is None:
                        continue  # (one 25-50 m off only where OSM has its stop line: the bridge end at Palackého náměstí)
                    if near is None:
                        near = [k for k, P in self.road_pts if (js_hypot(P[:, 0] - Px, P[:, 1] - Py) < 35).any()]
                    sx, sy, _, _ = lane["path"].at1(0)
                    if hyp(sx - Px, sy - Py) < 25:
                        continue
                    L = lane["path"].length
                    _, _, ehx, ehy = lane["path"].at1(L)
                    kind = "along" if abs(ehx * hx + ehy * hy) > 0.7 else "cross"
                    back, src = self.stop_line(lane, kind, Px, Py, near)
                    ex, ey, ehx, ehy = lane["path"].at1(min(L, L - back + 4))
                    x, y, face = ex + ehy * 2.2, ey - ehx * 2.2, math.atan2(-ehx, ehy)
                    head = next((i for i, o in enumerate(self.heads)
                                 if hyp(o[0] - x, y - o[1]) < 4 and math.cos(o[2] - face) > 0.9), -1)
                    if head < 0:
                        head = len(self.heads)
                        self.heads.append((x, y, face))
                    bound.add(lane["id"])
                    self.lights.append({"lane": lane["id"], "sig": sig["i"], "kind": kind, "head": head, "back": back, "src": src})
                    n += 1
            if n:
                self.light_sigs.append(sig["i"])
        self.bind_peds()
        # (the signals over a bridge on the road under it: the game leaves them out)
        self.over = [k for k, d in enumerate(self.data.get("signals") or []) if not d.get("drop") and self.over_bridge(d["cross"])]

    def bind_peds(self):
        """_bindPedHeads(): at each OSM signalled crossing (data.osmSignals.peds) of one of the game's signals (its
        crossing or stop point within 45 m), a head on each kerb of the car road it lies on (its half width + 0.6 m out,
        not on the rails), facing across; `along` when the crossing walks along the tram street."""
        nodes = (self.data.get("osmSignals") or {}).get("peds") or []
        self.ped_cross, self.ped_heads = [], []
        if not nodes:
            return
        sigs = [s for s in self.signals if not s.get("gauntlet")]  # (every other one has its cycle)
        A, D, L2, R = [], [], [], []
        for k, r in enumerate(self.net.roads):
            P = r["path"].p
            dx, dy = np.diff(P[:, 0]), np.diff(P[:, 1])
            l2 = dx * dx + dy * dy
            A.append(P[:-1])
            D.append(np.column_stack([dx, dy]))
            L2.append(np.where(l2 == 0, 1e-9, l2))
            R.append(np.full(len(dx), k))
        A, D, L2, R = np.vstack(A), np.vstack(D), np.concatenate(L2), np.concatenate(R)
        for o in nodes:
            ox, oy = o["x"], o["y"]
            if any(hyp(c["x"] - ox, c["y"] - oy) < 3 for c in self.ped_cross):
                continue
            sig, best = None, 45
            for s in sigs:
                for sp in (s["cross"], s["s"]):
                    qx, qy, _, _ = self.route.at(sp)
                    d = hyp(qx - ox, qy - oy)
                    if d < best:
                        best, sig = d, s
            if sig is None:
                continue
            # (the street it crosses: the nearest car road within 6 m)
            t = np.clip(((ox - A[:, 0]) * D[:, 0] + (oy - A[:, 1]) * D[:, 1]) / L2, 0, 1)
            d = js_hypot(A[:, 0] + D[:, 0] * t - ox, A[:, 1] + D[:, 1] * t - oy)
            k = int(np.argmin(d))
            if not d[k] < 6:
                continue
            road = self.net.roads[R[k]]
            ln = math.sqrt(float(L2[k]))
            rh = (float(D[k, 0]) / ln, float(D[k, 1]) / ln)
            cx, cy, half = -rh[1], rh[0], road["w"] / 2 + 0.6
            hx, hy = self.route.heading(sig["cross"], 6)
            along = bool(abs(cx * hx + cy * hy) > 0.6)
            ids = []
            for side in (1, -1):
                x, y = ox + cx * half * side, oy + cy * half * side
                if self.net.track_dist(x, y) < 1.8:
                    continue
                fx, fy = -cx * side, -cy * side
                ids.append(len(self.ped_heads))
                self.ped_heads.append((x, y, math.atan2(fx, -fy)))
            if ids:
                self.ped_cross.append({"x": ox, "y": oy, "cx": cx, "cy": cy, "sig": sig.get("i"), "along": along, "heads": ids})

    def osm_stop(self, lane, Px, Py):
        """_stopLineAt()'s OSM stop line: an OSM signal node within 70 m of the crossing (not on the junction's own node)
        within 4.5 m of the lane's last 40 m, serving its direction: `back` (m before the lane's end), or None."""
        path = lane["path"]
        L = path.length
        if L < 12 or not self.osm_stops:
            return None
        max_back = max(0, min(40, L - 3))
        J = self.jpos.get(lane["to"])
        best = None
        qs = None
        for o in self.osm_stops:
            if hyp(o["x"] - Px, o["y"] - Py) > 70 or (J and hyp(o["x"] - J[0], o["y"] - J[1]) < 6):
                continue
            if qs is None:
                qs = [(b, *path.at1(L - b)) for b in np.arange(math.floor(max_back / 0.5) + 1) * 0.5]
            for b, qx, qy, qhx, qhy in qs:
                d = hyp(o["x"] - qx, o["y"] - qy)
                if d < 4.5 and (o.get("both") or o["hx"] * qhx + o["hy"] * qhy > 0.7) and (best is None or d < best[0]):
                    best = (d, float(b))
        return None if best is None else best[1]

    def stop_line(self, lane, kind, Px, Py, near):
        """_stopLine(): the stop line `back` m before the lane's end (_stopLineAt), moved back to 2 m before a zebra
        under or ahead of a waiting car's front: (back, src)."""
        back, src = self.stop_line_at(lane, kind, Px, Py, near)
        if src == "short":
            return back, src
        path = lane["path"]
        L = path.length
        ex, ey, ehx, ehy = path.at1(L)
        pts = [*path.p.tolist(), [ex + ehx * 4, ey + ehy * 4]]
        stop, acc = L - back, 0
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            sl = hyp(b[0] - a[0], b[1] - a[1])
            if acc + sl > stop - 6:
                for z in self.zebras:
                    for j in range(1, len(z)):
                        c, d = z[j - 1], z[j]
                        rx, ry, sx, sy = b[0] - a[0], b[1] - a[1], d[0] - c[0], d[1] - c[1]
                        den = rx * sy - ry * sx
                        if abs(den) < 1e-9:
                            continue
                        t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den
                        u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den
                        if 0 <= t <= 1 and 0 <= u <= 1 and acc + t * sl > stop - 2.5:
                            stop = min(stop, acc + t * sl - 2)
            acc += sl
        return min(L - 1, max(back, L - stop)), src

    def stop_line_at(self, lane, kind, Px, Py, near):
        """_stopLineAt(): back from the lane's end (at most 40 m) to where the line is clear of the streets crossing it
        (their half width + 1.5 m) and, crossing the tram street away from the rails, 4.5 m clear of the tracks."""
        path = lane["path"]
        L = path.length
        max_back = max(0, min(40, L - 3))
        if L < 12:
            return L, "short"
        b = self.osm_stop(lane, Px, Py)
        if b is not None:
            return b, "osm"
        _, _, ehx, ehy = path.at1(L)
        cross = [self.net.roads[k] for k in near if k != lane["road"]]
        segs = []
        for r in cross:
            P = r["path"].p
            dx, dy = np.diff(P[:, 0]), np.diff(P[:, 1])
            l2 = dx * dx + dy * dy
            l2 = np.where(l2 == 0, 1e-9, l2)
            segs.append((r, P[:-1], dx, dy, l2))

        def dist_to(sg, x, y):
            r, A, dx, dy, l2 = sg
            t = np.clip(((x - A[:, 0]) * dx + (y - A[:, 1]) * dy) / l2, 0, 1)
            d = js_hypot(A[:, 0] + dx * t - x, A[:, 1] + dy * t - y)
            k = int(np.argmin(d))
            cos = abs((dx[k] * ehx + dy[k] * ehy) / math.sqrt(l2[k]))
            return float(d[k]) if cos < 0.7 else math.inf

        b = 0
        while b <= max_back:
            qx, qy, qhx, qhy = path.at1(L - b)
            q = self.route.nearest(qx, qy)
            h = q and self.route.at(q[1])
            along_rails = bool(h) and abs(qhx * h[2] + qhy * h[3]) > 0.8
            if not (kind == "cross" and not along_rails and self.net.track_dist(qx, qy) < 4.5) and \
                    not any(dist_to(sg, qx, qy) < sg[0]["w"] / 2 + 1.5 for sg in segs):
                return b, "edge"
            b += 0.5
        return max_back, "edge"


# ---------------------------------------------------------------- the platforms and our stops
def set_lengths():
    """{cars: the set's length over couplers} as src/tram.js gives it (Tram.length: T3.length a car, COUPLING_GAP =
    -T3.couplerOverlap between them), for the consists the menu offers (index.html optCars)."""
    import re
    with open(os.path.join(ROOT, "src", "tram.js"), encoding="utf-8") as f:
        js = f.read()
    length = float(re.search(r"^\s*length:\s*([\d.]+),", js, re.M).group(1))
    overlap = float(re.search(r"^\s*couplerOverlap:\s*([\d.]+),", js, re.M).group(1))
    return {cars: length * cars + (-overlap) * (cars - 1) for cars in (1, 2)}


SURVEYED = {"platform", "island", "sidewalk"}  # (where the survey draws the platform: no strip of the page's)


class Stops:
    """What src/platforms.js reads of the survey (buildPlatforms, buildStop): whether the survey draws each OSM platform
    off the doors' kerb (its middle a platform, island or sidewalk), and for each of our stops, with the stop point each
    set gives it (src/game.js _stopZone), whether the survey draws its stand-in platform and how far out the shelter
    stands (no further than the surveyed platform's edge)."""

    def __init__(self, data, survey, route, back):
        self.data, self.survey, self.route, self.back = data, survey, route, back
        self.platforms = []  # (the page's game.platforms: each placed OSM platform, then the ones both paths share)
        also = []
        for i, pl in enumerate(data.get("platforms") or []):
            if "path" not in pl:
                raise ValueError("the platforms have no placement (tools/placement.py, #419)")
            rt = (back if pl["path"] == "back" else route) if pl["path"] else None
            if not rt:
                continue
            s0, s1, side, far = pl["s0"], pl["s1"], pl["side"], pl.get("far")
            inner = 1.5
            outer = (min(inner + 6, max(inner + 2, far)) if pl.get("area") else
                     inner + (pl.get("w") or max(2.4, min(3.5, far + 1 - inner if pl.get("gtfs") else 2 * far - 2 * inner))))
            plat = {"i": i, "rt": rt, "back": rt is not route, "s0": s0, "s1": s1, "side": side, "inner": inner,
                    "outer": outer, "name": pl.get("name"), "stop": pl.get("stop"), "twin": bool(pl.get("twin")),
                    "ours": {"s0": pl["ours"][0], "s1": pl["ours"][1]} if pl.get("ours") else None}
            self.platforms.append(plat)
            if pl.get("also"):
                also.append((plat, pl["also"]))
            if side < 0 and "vienna" not in pl:
                raise ValueError(f"platform {pl.get('name')}: no stop type from the build (tools/placement.py vienna)")
            plat["kerb"] = pl["vienna"] if side < 0 else None
            if plat["kerb"] is not None:
                plat.update(inner=plat["kerb"], outer=plat["kerb"] + 2, surveyed=True)
                continue
            mx, my = self.offset(rt, (s0 + s1) / 2, side * (inner + outer) / 2)
            plat["surveyed"] = self.class_at(mx, my) in SURVEYED
        for plat, lst in also:
            for a in lst:
                art = back if a["path"] == "back" else route
                if art:
                    self.platforms.append({**plat, "rt": art, "back": art is not route, "s0": a["s0"], "s1": a["s1"],
                                           "side": a["side"], "ours": None, "shared": True})
        self.stops = [self.stop(i, s) for i, s in enumerate(data["stops"])]

    @staticmethod
    def offset(rt, s, lateral):
        """Route.offset(): the point `lateral` m left of the route at s (its heading the chord over ±3 m)."""
        x, y, _, _ = rt.at(s)
        hx, hy = rt.heading(s, 3)
        return x - hy * lateral, y + hx * lateral

    def class_at(self, x, y):
        return self.survey.class_at(np.array([x]), np.array([y]))[0]

    def stop(self, i, st):
        """buildStop()'s survey reads for each set: {"stand": whether the survey draws the stand-in platform (none of
        ours there, no Vienna type), "outer": the shelter's outer edge (m right of the track) where our OSM platform
        stands, else None}, lists by cars."""
        out = {"stand": [], "outer": []}
        for cars, L in set_lengths().items():
            target = min(st["sign"] if st.get("sign") is not None else st["s"] + 6, self.route.length - 2)
            if "p0" in st and st["p1"] - st["p0"] >= 15:
                hi = st["p1"] + 4
                lo = min(hi - 8, st["p0"] + L - 3 if st["p1"] - st["p0"] + 3 >= L else st["p1"] - 8)
                target = max(lo + 2.5, min(target, hi - 3))
            osm = next((p for p in self.platforms if not p["back"] and p["side"] < 0 and p["s0"] < target - 8
                        and p["s1"] > target - 20), None) or \
                next((p for p in self.platforms if p["back"] and p["ours"] and p["ours"]["s0"] < target - 8
                      and p["ours"]["s1"] > target - 20), None)
            kerb = osm["kerb"] if osm else st["vienna"]
            ax, ay = self.offset(self.route, target - 30 / 2 - 1, -2.8)
            out["stand"].append(not osm and kerb is None and self.class_at(ax, ay) not in SURVEYED)
            outer = osm["outer"] if osm else None
            if osm:
                lat, last = osm["inner"] + 0.5, None
                while lat <= osm["outer"] + 0.01:
                    ox, oy = self.offset(self.route, target - 12, -lat)
                    if self.class_at(ox, oy) == "platform":
                        last = lat
                    elif last is not None:
                        break
                    lat += 0.25
                if last is not None:
                    outer = min(outer, last + 0.25)
            out["outer"].append(outer)
        return out


# ---------------------------------------------------------------- the file
def platform_record(p):
    """A placed OSM platform: its index `i` in data.platforms, `name` and whether the survey draws it."""
    return {"i": p["i"], "name": p["name"], "surveyed": p["surveyed"]}


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
    if r["b"] or r["t"]:
        out["way"] = r["src"]  # (data.roads' index: the chain its height function spans, src/terrain.js way())
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
    survey = Survey(ln, data.get("terrain"))
    route = Route(data["path"], data.get("pathExt"))
    back = Route(data["pathBack"]) if len(data.get("pathBack") or ()) > 1 else None
    net = Network(data, survey, route, back)
    sg = Signals(data, survey, route, back, net)
    st = Stops(data, survey, route, back)
    recs = [road_record(r) for r in net.roads]
    fitted = sum(1 for r in net.roads if r["fitLo"] is not None)
    links = sum(1 for w in net.walks if w["link"])
    log(f"line {ln}: {len(recs)} roads ({fitted} fitted to the survey, {sum(1 for r in net.roads if r['fitMed'])} with a "
        f"median, {sum(1 for r in net.roads if r['trk'])} with tracks), {len(net.lanes)} lanes, {len(net.walks)} walks "
        f"({links} links), {len(net.doors)} doors, {len(sg.lights)} lanes bound to {len(sg.light_sigs)} signals with "
        f"{len(sg.heads)} heads, {time.time() - t0:.1f} s")
    return {"line": str(ln), "version": VERSION, "roads": recs, "lanes": [lane_record(x) for x in net.lanes],
            "walks": [walk_record(w) for w in net.walks], "doors": [door_record(d) for d in net.doors],
            "lights": [{**x, "back": cm(x["back"])} for x in sg.lights],
            "heads": [{"p": [cm(x), cm(y)], "face": js_round(f * 1000)} for x, y, f in sg.heads],
            "lightSigs": [{"sig": i} for i in sg.light_sigs],
            "pedCross": [{"p": [cm(c["x"]), cm(c["y"])], "c": [js_round(c["cx"] * 1e4), js_round(c["cy"] * 1e4)],
                          "sig": c["sig"], "along": c["along"], "heads": c["heads"]} for c in sg.ped_cross],
            "pedHeads": [{"p": [cm(x), cm(y)], "face": js_round(f * 1000)} for x, y, f in sg.ped_heads],
            "overBridge": sg.over,
            "platforms": [platform_record(p) for p in st.platforms if not p.get("shared")],
            "stops": [{"stand": s["stand"], "outer": [None if o is None else cm(o) for o in s["outer"]]} for s in st.stops],
            "fitted": fitted}


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
        "doors": sources.single("buildings", "osm", len(net["doors"]), "doors: where a building comes nearest a walk"),
        "lights": sources.entry("signals", [sum(x["src"] == "osm" for x in net["lights"]),
                                            sum(x["src"] != "osm" for x in net["lights"])],
                                "lanes bound to a signal: OSM's stop line, else the junction's edge"),
        "pedHeads": sources.single("signals", "osm", len(net["pedHeads"]), "pedestrian heads at OSM's signalled crossings"),
        "platforms": sources.single("stops", "osm", len(net["platforms"]), "OSM's platforms the survey draws"),
        "stops": sources.single("stops", "osm", len(net["stops"]), "our stops' stand-in platforms and shelters by the survey")})
    net["attribution"] = sources.attribution(net["provenance"])
    p = os.path.join(ROOT, "data", f"line{ln}.network.json")
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(net, f, separators=(",", ":"), ensure_ascii=False)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    for ln in [s.strip() for s in a.lines.split(",") if s.strip()]:
        net = build(ln)
        if not a.no_write:
            print(write(ln, net))
    return 0


if __name__ == "__main__":
    sys.exit(main())
