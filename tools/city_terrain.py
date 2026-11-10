"""The whole city's terrain as one greedy mesh of IPR's 1 m raster, 10 cm at the track (#428, #276's step 1).

The decisions (docs/decisions/2026-11-05-ground-built-offline.md, the user's): greedy insertion with pydelatin; the
error tolerance tol(d) = TOL up to D0 from a tram track, TOL * d / D0 beyond, at most TOL_MAX (tools/bench/
terrain_mesh.py), d the distance to DI's track network (tools/di_network.py); the city is meshed once and cut into
tiles afterwards (#276's later steps).

The ground of each cell of IPR's raster (35,001 x 26,001 cells of 1 m, rows north to south) is the first of:
  0 IPR's cell (tools/ipr_dtm.py), at or over the floor (sources.TERRAIN_FLOOR);
  1 inside Prague's administrative boundary (OSM relation CITY in the snapshot's extract): ČÚZK DMR 5G, bilinear at the
    cell's centre (tools/dmr5g.py: the 500 m tiles in raw/dem/; --fetch downloads the missing ones);
  2 inside it still: the lines' 10 m grids (raw/line*/terrain5514.tif, build_line.py);
  else no ground, and no triangles. Outside the boundary, IPR's own cells only.
No passages rule (fine_terrain.py's): IPR's ground stays where it has ground, the floors of underpasses and culverts and
the streets through building passages included; a street or track over a passage becomes a deck in #276's partition (the
user, 2026-11-10: "keeping IPR lidar everywhere to keep the actual lowest points. Then bridge the gaps on streets and
track/rail passes with other data"; tools/bench/terrain_compare.py --passages measured what the rule took and why).

The mesh, in three steps:
  1. pydelatin over s = (z - base) / tol(d) with one max error of 1, which is exact where tol is constant. The base is
     the ground smoothed over ~BASE_SIGMA blocks of BASE_BLOCK m: dividing the heights themselves by a tol that grows
     with d bends even a plane by z / tol, and the mesher spends triangles on that bend (tools/bench/terrain_city.py
     does; on a 3 x 3 km box by line 17 the base saves 8 % of the triangles, 15 % at 120-500 m, and leaves a quarter of
     the cells over their tolerance). No-ground cells take s from the ground around them (BLOCK m means) rising RAMP a
     cell away from it, so the mesh follows the ground's edge.
  2. every cell against the mesh, its vertices' heights rounded to cm as stored; a triangle over no ground cell is
     dropped.
  3. the second pass: each triangle with a ground cell over its own tolerance takes its worst cell as a vertex (split in
     three, or in four with its neighbour when the cell lies on their edge), until no cell is over.

Output in the machine cache, TRAMDATA_CACHE/city-terrain/<key>/ (nothing in data/; #276's later steps read it):
  mesh.npz  v (n, 3) int32: column, row and height in cm of each vertex; t (m, 3) uint32: vertex indices; origin: the
            city-frame x, y of cell (0, 0): x = origin x + column, y = origin y - row
  report.json  triangles and the error per distance band, the fallbacks' shares, the no-ground area, the zero areas
  zero-areas.png  the city limits with the areas where IPR has no ground, by what fills them
The key hashes the raster, the DMR 5G tiles in raw/dem/, the 10 m grids, DI's network, the OSM extract (the boundary),
the floor, the tolerance and mesh parameters and the code; a rerun with the same key reads the cache. The
report and the picture are copied to reports/city-terrain/.

    python -P -E tools/city_terrain.py [--fetch] [--box x0,y0,x1,y1] [--force] [--min-free 6] [--threads 8]
Waits its turn among the heavy jobs (baseline_store.HeavyJob) and stops itself when the free memory falls under
--min-free GB; the whole city took 13 min and 15.0 GB on the dev PC (2026-11-10: 16.6 M triangles). --box: a part of the
raster (city frame, m), for trials; one of SMALL cells or fewer is no heavy job (under 2 GB) and runs at once.
"""
import hashlib
import json
import math
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from sources import TERRAIN_FLOOR  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL, D0, TOL_MAX = 0.10, 120.0, 3.0  # m: the user's 10 cm at the track (2026-11-06), growing beyond D0, at most 3 m
LAT = 8  # cells: the distance to the tracks is exact on this lattice, bilinear between (the bench's)
CAP = 3700.0  # m: tol is TOL_MAX from D0 * TOL_MAX / TOL = 3,600 m on: farther distances are held at this
BASE_BLOCK, BASE_SIGMA = 64, 8  # the base: the ground's 64 m block means, a Gaussian of 8 blocks (512 m)
BLOCK = 16  # cells: no-ground cells take s from the ground's 16 m block means
RAMP, RAMP_R = 0.25, 16  # s a cell, cells: no-ground cells rise this much a cell away from the ground, up to RAMP_R
BANDS = ((0, 10), (10, 120), (120, 500), (500, 1000), (1000, 2000), (2000, math.inf))
CITY = 435514  # OSM relation: Praha, boundary=administrative, admin_level 4
# the cells' levels (uint8): bits 0-1 the fallback level (0 IPR, 1 DMR 5G, 2 the 10 m grids, 3 no ground), bit 2 inside
# the city, bits 3-4 what IPR's file holds there (KINDS)
LEVEL, NO, INSIDE = 3, 3, 4
KINDS = ("ground", "0.00 m", "no-data", "under the floor")
LEVELS = ("IPR", "DMR 5G", "10 m grid", "none")
NB = 30000  # error histogram: 1 mm bins up to 30 m
CHUNK = 2_000_000  # cells a worker rasterises at once
GROUND_BLOCK = 64  # cells: the blocks that say where any ground is
SMALL = 30_000_000  # cells: a --box this small (30 km²) runs without a turn among the heavy jobs
CODE = ("city_terrain.py", "dmr5g.py", "ipr_dtm.py")


def tol(d, t=TOL, d0=D0, tmax=TOL_MAX):
    return np.minimum(t * np.maximum(d, d0) / d0, tmax)


def peak_gb():
    """The process's peak memory so far (Windows: the peak working set; elsewhere ru_maxrss)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                       [(k, ctypes.c_size_t) for k in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                       "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                       "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        c = PMC()
        c.cb = ctypes.sizeof(c)
        k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE  # (the default int would cut the 64-bit pseudo handle)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            raise OSError("GetProcessMemoryInfo failed")
        return c.PeakWorkingSetSize / 2**30
    except (AttributeError, OSError):
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20


# ---------------------------------------------------------------- grids of block values
def block_sums(a, b, rows=None):
    """Sums and counts of the non-NaN values of a 2-D array per b x b block (rows in bands, for arrays on disk)."""
    h, w = a.shape
    nby, nbx = -(-h // b), -(-w // b)
    s, n = np.zeros((nby, nbx)), np.zeros((nby, nbx))
    for by in range(nby):
        v = np.asarray(a[by * b:(by + 1) * b], np.float64)
        if nbx * b > w:
            v = np.pad(v, ((0, 0), (0, nbx * b - w)), constant_values=np.nan)
        v = v.reshape(v.shape[0], nbx, b)
        ok = ~np.isnan(v)
        s[by], n[by] = np.where(ok, v, 0).sum((0, 2)), ok.sum((0, 2))
    return s, n


def block_any(g, b):
    """One row of b x b blocks of a band of b rows (or fewer): whether any cell is set."""
    w = g.shape[1]
    nbx = -(-w // b)
    if nbx * b > w:
        g = np.pad(g, ((0, 0), (0, nbx * b - w)))
    return g.reshape(g.shape[0], nbx, b).any((0, 2))[None, :]


def upsample(c, h, w):
    """A grid twice as fine (h x w), bilinear between the coarse cells' centres."""
    y = np.clip((np.arange(h) + 0.5) / 2 - 0.5, 0, c.shape[0] - 1)
    x = np.clip((np.arange(w) + 0.5) / 2 - 0.5, 0, c.shape[1] - 1)
    j0, i0 = np.minimum(y.astype(int), max(c.shape[0] - 2, 0)), np.minimum(x.astype(int), max(c.shape[1] - 2, 0))
    j1, i1 = np.minimum(j0 + 1, c.shape[0] - 1), np.minimum(i0 + 1, c.shape[1] - 1)
    ty, tx = (y - j0)[:, None], (x - i0)[None, :]
    return (c[j0][:, i0] * (1 - tx) + c[j0][:, i1] * tx) * (1 - ty) + (c[j1][:, i0] * (1 - tx) + c[j1][:, i1] * tx) * ty


def fill_gaps(a):
    """The NaN cells of a grid from the means of the coarser grids around them (pull-push), so the fill is smooth."""
    miss = np.isnan(a)
    if not miss.any():
        return a
    if miss.all():
        return np.zeros_like(a)
    h, w = a.shape
    p = np.pad(a, ((0, h % 2), (0, w % 2)), constant_values=np.nan).reshape((h + h % 2) // 2, 2, (w + w % 2) // 2, 2)
    ok = ~np.isnan(p)
    with np.errstate(invalid="ignore"):
        c = np.where(ok, p, 0).sum((1, 3)) / ok.sum((1, 3))
    out = a.copy()
    out[miss] = upsample(fill_gaps(c), h, w)[miss]
    return out


def gauss(a, sigma):
    """A separable Gaussian of `sigma` cells, the edges held."""
    r = int(3 * sigma)
    if r < 1:
        return a
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 1, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, "valid"), 0, p)


def at_blocks(g, b, rows, cols):
    """A grid of b x b block values (at the blocks' centres) at cells (rows, cols: 1-D, the result rows x cols)."""
    def axis(v, n):
        f = np.clip((v + 0.5) / b - 0.5, 0, n - 1)
        i0 = np.minimum(f.astype(int), max(n - 2, 0))
        return i0, np.minimum(i0 + 1, n - 1), (f - i0).astype(np.float32)
    j0, j1, ty = axis(np.asarray(rows, np.float64), g.shape[0])
    i0, i1, tx = axis(np.asarray(cols, np.float64), g.shape[1])
    g = g.astype(np.float32)
    ty, tx = ty[:, None], tx[None, :]
    return (g[j0][:, i0] * (1 - tx) + g[j0][:, i1] * tx) * (1 - ty) + (g[j1][:, i0] * (1 - tx) + g[j1][:, i1] * tx) * ty


def at_points(g, b, rows, cols):
    """A grid of b x b block values at cells (rows, cols: arrays of one shape)."""
    fj = np.clip((np.asarray(rows, np.float64) + 0.5) / b - 0.5, 0, g.shape[0] - 1)
    fi = np.clip((np.asarray(cols, np.float64) + 0.5) / b - 0.5, 0, g.shape[1] - 1)
    j0, i0 = np.minimum(fj.astype(int), max(g.shape[0] - 2, 0)), np.minimum(fi.astype(int), max(g.shape[1] - 2, 0))
    j1, i1 = np.minimum(j0 + 1, g.shape[0] - 1), np.minimum(i0 + 1, g.shape[1] - 1)
    ty, tx = fj - j0, fi - i0
    return (g[j0, i0] * (1 - tx) + g[j0, i1] * tx) * (1 - ty) + (g[j1, i0] * (1 - tx) + g[j1, i1] * tx) * ty


def at_lattice(dl, rows, cols, lat=LAT):
    """The distance lattice (every `lat` cells) bilinear at cells (arrays of one shape)."""
    fj, fi = np.asarray(rows, np.float32) / lat, np.asarray(cols, np.float32) / lat
    j, i = fj.astype(np.int64), fi.astype(np.int64)
    tj, ti = fj - j, fi - i
    return (dl[j, i] * (1 - ti) + dl[j, i + 1] * ti) * (1 - tj) + (dl[j + 1, i] * (1 - ti) + dl[j + 1, i + 1] * ti) * tj


def ground_steps(g, steps):
    """Steps from the nearest ground cell (growing by turns over 4 and 8 neighbours: close to the distance in cells),
    `steps` where farther."""
    d = np.full(g.shape, steps, np.uint8)
    d[g] = 0
    reach = g.copy()
    for k in range(1, steps):
        grown = reach.copy()
        grown[1:] |= reach[:-1]
        grown[:-1] |= reach[1:]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        if k % 2 == 0:
            grown[1:, 1:] |= reach[:-1, :-1]
            grown[1:, :-1] |= reach[:-1, 1:]
            grown[:-1, 1:] |= reach[1:, :-1]
            grown[:-1, :-1] |= reach[1:, 1:]
        d[grown & ~reach] = k
        reach = grown
    return d


# ---------------------------------------------------------------- the mesh
def rasterise(P, zc, T, ids, shape, own=None):
    """The cells in or on the triangles `ids` and the mesh's height there (m). P: (n, 2) int64 column, row; zc: (n,)
    heights in cm. own: each vertex's owning triangle, to mark the cells each triangle owns, every cell exactly one
    triangle's (on an edge the one whose edge points up, or right when level, or the one on the mesh's outer edge; on a
    vertex its owner). Returns (k: index into ids, columns, rows, heights, owned)."""
    h, w = shape
    tri = T[ids].astype(np.int64)
    a, b, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    ar = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    flip = ar < 0  # (one orientation for the edge functions)
    b, c = np.where(flip[:, None], c, b), np.where(flip[:, None], b, c)
    tri[flip] = tri[flip][:, [0, 2, 1]]
    ar = np.abs(ar)
    x0, x1 = np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0]), np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])
    y0, y1 = np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1]), np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])
    bw, cnt = x1 - x0 + 1, (x1 - x0 + 1) * (y1 - y0 + 1)
    k = np.repeat(np.arange(len(tri)), cnt)
    o = np.arange(len(k)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    px, py = x0[k] + o % bw[k], y0[k] + o // bw[k]
    del o

    def edge(u, v):
        return (v[k, 0] - u[k, 0]) * (py - u[k, 1]) - (v[k, 1] - u[k, 1]) * (px - u[k, 0])
    w0, w1, w2 = edge(b, c), edge(c, a), edge(a, b)
    keep = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    k, px, py, w0, w1, w2 = k[keep], px[keep], py[keep], w0[keep], w1[keep], w2[keep]
    mine = np.ones(len(k), bool)
    if own is not None:
        def owns(u, v):
            dx, dy = v[:, 0] - u[:, 0], v[:, 1] - u[:, 1]
            border = ((dx == 0) & ((u[:, 0] == 0) | (u[:, 0] == w - 1))) | ((dy == 0) & ((u[:, 1] == 0) | (u[:, 1] == h - 1)))
            return (dy < 0) | ((dy == 0) & (dx > 0)) | border
        on_edge = ((w0 > 0) | owns(b, c)[k]) & ((w1 > 0) | owns(c, a)[k]) & ((w2 > 0) | owns(a, b)[k])
        zeros = (w0 == 0).astype(np.int8) + (w1 == 0) + (w2 == 0)
        vid = np.where(w0 > 0, tri[k, 0], np.where(w1 > 0, tri[k, 1], tri[k, 2]))
        mine = np.where(zeros == 2, own[vid] == np.asarray(ids)[k], on_edge)
    z = (w0 * zc[tri[k, 0]] + w1 * zc[tri[k, 1]] + w2 * zc[tri[k, 2]]) / ar[k] / 100.0
    return k, px, py, z, mine


def pieces(P, T, ids, most=CHUNK):
    """`ids` in runs whose triangles' boxes hold at most `most` cells (a bigger triangle alone)."""
    tri = T[ids]
    xy = P[tri]  # (m, 3, 2)
    cnt = (xy[:, :, 0].max(1) - xy[:, :, 0].min(1) + 1) * (xy[:, :, 1].max(1) - xy[:, :, 1].min(1) + 1)
    cum = np.cumsum(cnt)
    cuts = [0]
    while cuts[-1] < len(ids):
        nxt = int(np.searchsorted(cum, (cum[cuts[-1] - 1] if cuts[-1] else 0) + most, side="right"))
        cuts.append(max(nxt, cuts[-1] + 1))
    return [ids[a:b] for a, b in zip(cuts, cuts[1:])]


class Mesh:
    """The triangles, their vertices and the checks: vertices P (column, row) and zc (cm), triangles T, alive."""

    def __init__(self, P, zc, T, Z, ground, dl, shape, tolf, threads=8, blocks=None):
        self.P, self.zc = np.asarray(P, np.int64), np.asarray(zc, np.int64)
        self.T, self.alive = np.asarray(T, np.int64), np.ones(len(T), bool)
        self.Z, self.ground, self.dl, self.shape, self.tolf, self.threads = Z, ground, dl, shape, tolf, threads
        self.blocks = None  # (the ground blocks' running sums: a triangle whose box holds none is not rasterised)
        if blocks is not None:
            self.blocks = np.zeros((blocks.shape[0] + 1, blocks.shape[1] + 1), np.int64)
            self.blocks[1:, 1:] = blocks.astype(np.int64).cumsum(0).cumsum(1)

    def near_ground(self, ids):
        """Which of the triangles `ids` have a GROUND_BLOCK block holding ground in their box."""
        if self.blocks is None:
            return np.ones(len(ids), bool)
        tri = self.T[ids]
        x, y = self.P[:, 0][tri], self.P[:, 1][tri]
        x0, x1 = x.min(1) // GROUND_BLOCK, x.max(1) // GROUND_BLOCK + 1
        y0, y1 = y.min(1) // GROUND_BLOCK, y.max(1) // GROUND_BLOCK + 1
        I = self.blocks
        return I[y1, x1] - I[y0, x1] - I[y1, x0] + I[y0, x0] > 0

    def _check(self, ids, own):
        """Per run of triangles: the ground cells in or on each triangle and the no-ground cells it owns, the error
        histogram per band over the cells each owns, the cells over their tolerance."""
        k, px, py, m, mine = rasterise(self.P, self.zc, self.T, ids, self.shape, own)
        g = self.ground(py, px)
        n = len(ids)
        out = {"ground": np.bincount(k[g], minlength=n), "other": np.bincount(k[~g & mine], minlength=n),
               "cells": int((g & mine).sum())}
        k, px, py, m, mine = k[g], px[g], py[g], m[g], mine[g]
        err = np.abs(m - self.Z[py, px])
        d = at_lattice(self.dl, py, px)
        t = self.tolf(d)
        over = err > t
        out["over"] = (py[over] * self.shape[1] + px[over], np.asarray(ids)[k[over]], (err[over] / t[over]))
        err, d = err[mine], d[mine]
        band = np.searchsorted(np.array([b[1] for b in BANDS[:-1]]), d, side="right")
        out["hist"] = np.bincount(band * NB + np.minimum((err * 1000).astype(np.int64), NB - 1), minlength=len(BANDS) * NB)
        out["sum"] = np.bincount(band, weights=err, minlength=len(BANDS))
        mx = np.zeros(len(BANDS))
        np.maximum.at(mx, band, err)
        out["max"] = mx
        return out

    def check(self, ids=None, own=True):
        """Every cell under the triangles `ids` (all alive ones by default) against the mesh, in parallel runs."""
        ids = np.flatnonzero(self.alive) if ids is None else np.asarray(ids)
        owner = None
        if own:
            owner = np.full(len(self.P), np.iinfo(np.int64).max)
            al = np.flatnonzero(self.alive)
            np.minimum.at(owner, self.T[al].ravel(), np.repeat(al, 3))
        ids = ids[self.near_ground(ids)] if len(ids) else ids
        runs = pieces(self.P, self.T, ids) if len(ids) else []
        res = {"ground": np.zeros(len(self.T), np.int64), "other": np.zeros(len(self.T), np.int64), "cells": 0,
               "hist": np.zeros(len(BANDS) * NB, np.int64), "sum": np.zeros(len(BANDS)), "max": np.zeros(len(BANDS)),
               "over": []}
        with ThreadPoolExecutor(self.threads) as ex:
            for r, part in zip(runs, ex.map(lambda r: self._check(r, owner), runs)):
                res["ground"][r] += part["ground"]
                res["other"][r] += part["other"]
                res["cells"] += part["cells"]
                res["hist"] += part["hist"]
                res["sum"] += part["sum"]
                res["max"] = np.maximum(res["max"], part["max"])
                res["over"].append(part["over"])
        res["over"] = tuple(np.concatenate(v) for v in zip(*res["over"])) if res["over"] else \
            (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
        return res

    def refine(self, over, log=print, most=500):
        """The second pass: the worst cell of each triangle with a cell over its tolerance becomes a vertex (the triangle
        split in three, or with its neighbour in four when the cell lies on their edge), until no cell is over. The
        first pass's triangles stay in arrays (their edges sorted for the neighbour across one); the new ones in lists."""
        w = self.shape[1]
        P0, z0, T0, alive0 = self.P, self.zc, self.T, self.alive.copy()
        n0, m0, big = len(P0), len(T0), 1 << 32
        al = np.flatnonzero(alive0)
        e = np.concatenate([np.sort(T0[al][:, [0, 1]], 1), np.sort(T0[al][:, [1, 2]], 1), np.sort(T0[al][:, [2, 0]], 1)])
        ek, et = e[:, 0] * big + e[:, 1], np.tile(al, 3)
        o = np.argsort(ek, kind="stable")
        ek, et = ek[o], et[o]
        del e, o
        nP, nz, nT, nalive, nk = [], [], [], [], {}

        def tri(i):
            return tuple(T0[i].tolist()) if i < m0 else nT[i - m0]

        def alive(i):
            return alive0[i] if i < m0 else nalive[i - m0]

        def xy(v):
            return tuple(P0[v].tolist()) if v < n0 else nP[v - n0]

        def across(u, v, t):
            key = min(u, v) * big + max(u, v)
            lo, hi = np.searchsorted(ek, key), np.searchsorted(ek, key, side="right")
            for c in et[lo:hi].tolist() + nk.get(key, []):
                if c != t and alive(c):
                    return c
            return None
        added, rounds = 0, 0
        cells, tris, ratio = over
        while len(cells):
            rounds += 1
            if rounds > most:
                raise SystemExit(f"second pass: cells still over their tolerance after {most} rounds")
            o = np.lexsort((-ratio, tris))
            first = np.r_[True, tris[o][1:] != tris[o][:-1]]
            new = []
            for ti, cell in zip(tris[o][first].tolist(), cells[o][first].tolist()):
                if not alive(ti):
                    continue
                px, py = cell % w, cell // w
                a, b, c = tri(ti)
                (ax, ay), (bx, by), (cx, cy) = xy(a), xy(b), xy(c)
                s = 1 if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0 else -1
                ws = [s * ((cx - bx) * (py - by) - (cy - by) * (px - bx)), s * ((ax - cx) * (py - cy) - (ay - cy) * (px - cx)),
                      s * ((bx - ax) * (py - ay) - (by - ay) * (px - ax))]
                if sum(x == 0 for x in ws) > 1:
                    raise SystemExit(f"second pass: cell {px},{py} over its tolerance on a vertex")
                p = n0 + len(nP)
                nP.append((px, py))
                nz.append(int(round(float(self.Z[py, px]) * 100)))
                added += 1
                if 0 not in ws:
                    split = [(ti, 0), (ti, 1), (ti, 2)]  # (each vertex in turn swapped for p: the orientation holds)
                else:
                    j = ws.index(0)  # p on the edge opposite vertex j
                    u, v = [x for i, x in enumerate((a, b, c)) if i != j]
                    split = [(ti, (j + 1) % 3), (ti, (j + 2) % 3)]
                    n = across(u, v, ti)
                    if n is not None:
                        tn = tri(n)
                        split += [(n, tn.index(u)), (n, tn.index(v))]
                for t0 in {t for t, _ in split}:
                    if t0 < m0:
                        alive0[t0] = False
                    else:
                        nalive[t0 - m0] = False
                for t0, j in split:
                    t = list(tri(t0))
                    t[j] = p
                    nT.append(tuple(t))
                    nalive.append(True)
                    i = m0 + len(nT) - 1
                    new.append(i)
                    for u2, v2 in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                        nk.setdefault(min(u2, v2) * big + max(u2, v2), []).append(i)
            self.P = np.vstack([P0, np.array(nP, np.int64).reshape(-1, 2)])
            self.zc = np.concatenate([z0, np.array(nz, np.int64)])
            self.T = np.vstack([T0, np.array(nT, np.int64).reshape(-1, 3)])
            self.alive = np.concatenate([alive0, np.array(nalive, bool)])
            new = [i for i in new if self.alive[i]]
            cells, tris, ratio = self.check(new, own=False)["over"]
            log(f"  second pass, round {rounds}: {len(new):,} new triangles, {len(np.unique(tris)):,} still with cells over")
        return added, rounds


def greedy(S, shape):
    """pydelatin's greedy insertion over S (rows north to south) to one max error of 1: vertices (column, row, s), triangles.
    S may be a memmap: pydelatin copies it, so the caller can let it go while the mesh runs."""
    from _pydelatin import PydelatinTriangulator
    h, w = shape
    tri = PydelatinTriangulator(w, h, 1.0, 1.0, 1.0, 0, 0, False, False, 0, 0.0, 0, 1.0, 0.0)
    tri.setData(S.reshape(-1))
    return tri


def scaled(Z, ground_of, dl, shape, S, log=print, tolf=tol):
    """S = (z - base) / tol(d) on ground cells, the ground's s around them rising away from it elsewhere; returns the base."""
    h, w = shape
    s, n = block_sums(Z, BASE_BLOCK)
    with np.errstate(invalid="ignore"):
        base = gauss(fill_gaps(s / n), BASE_SIGMA)
    cols = np.arange(w)
    band = 512
    for r0 in range(0, h, band):
        rows = np.arange(r0, min(h, r0 + band))
        t = tolf(at_lattice(dl, rows[:, None], cols[None, :]))
        S[r0:r0 + len(rows)] = (np.asarray(Z[r0:r0 + len(rows)]) - at_blocks(base, BASE_BLOCK, rows, cols)) / t
    s, n = block_sums(S, BLOCK)
    with np.errstate(invalid="ignore"):
        ext = fill_gaps(s / n)
    for r0 in range(0, h, band):
        r1 = min(h, r0 + band)
        a0, a1 = max(0, r0 - RAMP_R), min(h, r1 + RAMP_R)
        g = ground_of(slice(a0, a1))
        steps = ground_steps(g, RAMP_R)[r0 - a0:r1 - a0]
        g = g[r0 - a0:r1 - a0]
        v = np.asarray(S[r0:r1])
        fill = at_blocks(ext, BLOCK, np.arange(r0, r1), cols) + RAMP * steps
        S[r0:r1] = np.where(g, v, fill)
    if hasattr(S, "flush"):
        S.flush()
    return base


def build(Z, lev, dl, shape, tmp=None, log=print, threads=8, tolf=tol):
    """The mesh of the cells: Z (rows, cols) float32 heights, NaN where no ground, or the path of such a file (then its
    pages leave memory while pydelatin runs); lev their levels (LEVEL bits); dl the distance lattice (LAT). tmp: a folder
    for the scaled field on disk (None: in memory). Returns (V (n, 3) int32 column, row, cm; T (m, 3) uint32; the
    report's numbers)."""
    h, w = shape
    t0 = time.perf_counter()
    rep, secs = {}, {}
    zpath = Z if isinstance(Z, str) else None
    if zpath:
        Z = np.memmap(zpath, np.float32, "r", shape=shape)

    def ground_of(rows):
        return (np.asarray(lev[rows]) & LEVEL) != NO

    if tmp:
        path = os.path.join(tmp, "s.f32")
        S = np.memmap(path, np.float32, "w+", shape=shape)
    else:
        S = np.empty(shape, np.float32)
    base = scaled(Z, ground_of, dl, shape, S, log, tolf)
    secs["scaled"] = time.perf_counter() - t0
    log(f"scaled field in {secs['scaled']:.0f} s, peak {peak_gb():.1f} GB")
    t0 = time.perf_counter()
    tri = greedy(S, shape)
    del S
    if zpath:  # (the heights wait on disk while the mesh runs)
        del Z
    tri.run()
    pts, T = tri.getPoints().reshape(-1, 3), tri.getTriangles().reshape(-1, 3).astype(np.int64)
    del tri
    if zpath:
        Z = np.memmap(zpath, np.float32, "r", shape=shape)
    if tmp:
        os.remove(path)
    secs["mesh"] = time.perf_counter() - t0
    rep["first"] = int(len(T))
    log(f"greedy mesh: {len(T):,} triangles, {len(pts):,} vertices in {secs['mesh']:.0f} s, peak {peak_gb():.1f} GB")

    t0 = time.perf_counter()
    col, row = pts[:, 0].astype(np.int64), (h - 1 - pts[:, 1]).astype(np.int64)
    z = np.asarray(Z[row, col], np.float64)
    off = np.isnan(z)  # (vertices on no ground keep the fill's height: s * tol + base)
    if off.any():
        z[off] = pts[off, 2] * tolf(at_lattice(dl, row[off], col[off])) + at_points(base, BASE_BLOCK, row[off], col[off])
    gb = np.vstack([block_any(ground_of(slice(r, r + GROUND_BLOCK)), GROUND_BLOCK) for r in range(0, h, GROUND_BLOCK)])
    mesh = Mesh(np.column_stack([col, row]), np.round(z * 100), T, Z, lambda r, c: (lev[r, c] & LEVEL) != NO, dl, shape,
                tolf, threads, gb)
    first = mesh.check()
    mesh.alive &= first["ground"] > 0  # (no ground cell under it: dropped)
    rep["dropped"] = int(len(T) - mesh.alive.sum())
    rep["over_first"] = int(len(np.unique(first["over"][0])))
    rep["over_first_share"] = rep["over_first"] / max(first["cells"], 1)
    secs["check"] = time.perf_counter() - t0
    log(f"checked: {first['cells']:,} ground cells, {rep['over_first']:,} over their tolerance "
        f"({100 * rep['over_first_share']:.3f} %), {rep['dropped']:,} triangles on no ground dropped, {secs['check']:.0f} s")
    t0 = time.perf_counter()
    keep = mesh.alive.copy()
    rep["added"], rep["rounds"] = mesh.refine(first["over"], log) if rep["over_first"] else (0, 0)
    secs["second"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    final = mesh.check()
    keep = mesh.alive & (final["ground"] > 0)
    secs["final"] = time.perf_counter() - t0
    if len(final["over"][0]):
        raise SystemExit(f"{len(final['over'][0])} cells over their tolerance after the second pass")
    ngr = int(sum(int(ground_of(slice(r, r + 1024)).sum()) for r in range(0, h, 1024)))
    if final["cells"] != ngr:
        raise SystemExit(f"the mesh covers {final['cells']} ground cells once, of {ngr}: a crack or an overlap")
    T2 = mesh.T[keep]
    used, inv = np.unique(T2.ravel(), return_inverse=True)
    V = np.column_stack([mesh.P[used], mesh.zc[used]]).astype(np.int32)
    T2 = inv.reshape(-1, 3).astype(np.uint32)
    # per band: the triangles by their centroid's distance, the error of the ground cells
    g = mesh.P[mesh.T[keep]].mean(1)
    dc = at_lattice(dl, g[:, 1], g[:, 0])
    rep["bands"] = {}
    for bi, (lo, hi) in enumerate(BANDS):
        hist = final["hist"][bi * NB:(bi + 1) * NB]
        n = int(hist.sum())
        p99 = int(np.searchsorted(np.cumsum(hist), 0.99 * n)) / 10 if n else 0.0
        rep["bands"][label(lo, hi)] = {"triangles": int(((dc >= lo) & (dc < hi)).sum()), "cells": n,
                                       "mean_cm": round(100 * final["sum"][bi] / n, 2) if n else 0.0,
                                       "p99_cm": p99, "max_cm": round(100 * final["max"][bi], 1)}
    rep["triangles"], rep["vertices"] = int(len(T2)), int(len(V))
    rep["rim_cells"] = int(final["other"][keep].sum())  # (no-ground cells under kept triangles: along the ground's edge)
    rep["ground_cells"] = ngr
    rep["s"] = {k: round(v, 1) for k, v in secs.items()}
    return V, T2, rep


def label(lo, hi):
    return f"{lo}-{int(hi)}" if hi < math.inf else f"{lo}-"


# ---------------------------------------------------------------- inputs
def window(ipr, box, frame):
    """The cells (i0, j0, i1, j1) of IPR's raster inside box (x0, y0, x1, y1, city frame), all of it without one."""
    if not box:
        return 0, 0, ipr.w, ipr.h
    x0, y0, x1, y1 = box
    ox, oy = ipr.e0 - frame.E0, ipr.n0 - frame.N0
    return (max(0, int(math.floor(x0 - ox))), max(0, int(math.floor(oy - y1))),
            min(ipr.w, int(math.ceil(x1 - ox)) + 1), min(ipr.h, int(math.ceil(oy - y0)) + 1))


def classify(a):
    """IPR's values as the file holds them: the heights (NaN where no ground) and the levels (0 or NO, with KINDS)."""
    kind = np.where(a >= TERRAIN_FLOOR, 0, np.where(a == 0, 1, np.where(a < -1e30, 2, 3))).astype(np.uint8)
    return np.where(kind == 0, a, np.nan).astype(np.float32), np.where(kind == 0, 0, NO).astype(np.uint8) | (kind << 3)


def read_ipr(ipr, win, Z, lev):
    """IPR's cells of the window into Z and lev (classify); the counts per kind. Each tile is cropped to the image: the
    edge tiles' padding past it is no cell of it (#325)."""
    i0, j0, i1, j1 = win
    counts = np.zeros(4, np.int64)
    for ty in range(j0 // ipr.th, (j1 - 1) // ipr.th + 1):
        for tx in range(i0 // ipr.tw, (i1 - 1) // ipr.tw + 1):
            a = ipr.decode(tx, ty)
            r0, c0 = ty * ipr.th, tx * ipr.tw
            rs, re, cs, ce = max(j0, r0), min(j1, r0 + ipr.th, ipr.h), max(i0, c0), min(i1, c0 + ipr.tw, ipr.w)
            z, lv = classify(a[rs - r0:re - r0, cs - c0:ce - c0])
            Z[rs - j0:re - j0, cs - i0:ce - i0] = z
            lev[rs - j0:re - j0, cs - i0:ce - i0] = lv
            counts += np.bincount((lv >> 3).ravel(), minlength=4)
    return counts


def boundaries(frame):
    """Prague's limits, its districts (admin_level 9) and cadastral areas from the snapshot's OSM extract, city frame:
    (city, [(kind, name, polygon)])."""
    import osmium
    import osm_local
    import shapely
    from shapely.geometry import MultiPolygon, Polygon

    def xy(ring):
        pts = [(n.lat, n.lon) for n in ring]
        x, y = frame.xy([p[0] for p in pts], [p[1] for p in pts])
        return list(zip(x, y))
    city, parts = None, []
    for o in osmium.FileProcessor(osm_local.PRAHA).with_areas(osmium.filter.KeyFilter("boundary")):
        if not o.is_area() or o.from_way():
            continue
        t = dict(o.tags)
        kind = "city" if o.orig_id() == CITY else "district" if t.get("boundary") == "administrative" and \
            t.get("admin_level") == "9" else "cadastral" if t.get("boundary") == "cadastral" else None
        if not kind:
            continue
        g = shapely.make_valid(MultiPolygon([Polygon(xy(r), [xy(i) for i in o.inner_rings(r)]) for r in o.outer_rings()]))
        if kind == "city":
            city = g
        else:
            parts.append((kind, t.get("name", "?"), g))
    if city is None:
        raise SystemExit(f"no relation {CITY} (Praha) in {osm_local.PRAHA}")
    return city, [p for p in parts if p[2].intersection(city).area > 0.5 * p[2].area]


def paint(geom, shape, origin):
    """bool (rows, cols): the cells whose centre lies in the polygons (city frame), drawn by Pillow."""
    from PIL import Image, ImageDraw
    h, w = shape
    im = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(im)
    ox, oy = origin
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon":
            continue
        d.polygon([(x - ox, oy - y) for x, y in p.exterior.coords], fill=1)
        for r in p.interiors:
            d.polygon([(x - ox, oy - y) for x, y in r.coords], fill=0)
    return np.asarray(im, dtype=bool)


def segments(net):
    """DI's network as straight pieces (n, 4): x0, y0, x1, y1 in the city frame."""
    out = []
    for e in net.edges.values():
        a = np.asarray(e["line"].coords, np.float64)[:, :2]
        keep = np.any(a[1:] != a[:-1], axis=1)
        out.append(np.hstack([a[:-1][keep], a[1:][keep]]))
    return np.vstack(out)


def distances(segs, shape, origin, lat=LAT, cap=CAP, threads=8):
    """The distance to the nearest track at every `lat`-th cell (rows, cols of the lattice), `cap` where farther."""
    import shapely
    h, w = shape
    nj, ni = (h - 1) // lat + 2, (w - 1) // lat + 2
    tree = shapely.STRtree(shapely.linestrings(segs.reshape(-1, 2, 2)))
    xs = origin[0] + np.arange(ni) * lat

    def rows(j0):
        j = np.arange(j0, min(nj, j0 + 64))
        gx, gy = np.meshgrid(xs, origin[1] - j * lat)
        # (no max_distance: with it, shapely 2.2's search took 140 s for what takes 1 s without)
        idx, d = tree.query_nearest(shapely.points(gx.ravel(), gy.ravel()), return_distance=True, all_matches=False)
        out = np.full(gx.size, cap, np.float32)
        out[idx[0]] = np.minimum(d, cap)
        return out.reshape(gx.shape)
    with ThreadPoolExecutor(threads) as ex:
        return np.vstack(list(ex.map(rows, range(0, nj, 64))))


class Grids:
    """The lines' 10 m grids of DMR 5G (raw/**/terrain5514.tif with their extent), bilinear, NaN under the floor or off."""

    def __init__(self, paths):
        from PIL import Image
        self.grids = []
        for p in paths:
            a = np.asarray(Image.open(p), dtype=np.float32).copy()
            a[~(a >= TERRAIN_FLOOR)] = np.nan
            ext = json.load(open(p[:-4] + ".json", encoding="utf-8"))["extent"]
            self.grids.append((a, ext))

    def sample(self, E, N):
        out = np.full(E.shape, np.nan, np.float32)
        for a, ext in self.grids:
            h, w = a.shape
            de, dn = (ext["xmax"] - ext["xmin"]) / w, (ext["ymax"] - ext["ymin"]) / h
            fx, fy = (E - ext["xmin"]) / de - 0.5, (ext["ymax"] - N) / dn - 0.5
            m = np.isnan(out) & (fx >= 0) & (fy >= 0) & (fx <= w - 1) & (fy <= h - 1)
            if not m.any():
                continue
            i, j = np.minimum(fx[m].astype(int), w - 2), np.minimum(fy[m].astype(int), h - 2)
            tx, ty = fx[m] - i, fy[m] - j
            out[m] = (a[j, i] * (1 - tx) + a[j, i + 1] * tx) * (1 - ty) + (a[j + 1, i] * (1 - tx) + a[j + 1, i + 1] * tx) * ty
        return out


def fallbacks(Z, lev, origin, frame, dem, grids, log=print):
    """IPR's gaps inside the city from DMR 5G (dem: dmr5g.Tiles), then the 10 m grids (grids.sample). Returns the counts."""
    h, w = Z.shape
    ox, oy = origin
    e0, n0 = ox + frame.E0, oy + frame.N0
    out = {"dmr5g": 0, "grids": 0}
    for r0 in range(0, h, 256):
        r1 = min(h, r0 + 256)
        lv = np.asarray(lev[r0:r1])
        gap = ((lv & LEVEL) == NO) & ((lv & INSIDE) != 0)
        if not gap.any():
            continue
        rr, cc = np.nonzero(gap)
        E, N = e0 + cc, n0 - (r0 + rr)
        z1 = dem.sample(E, N).astype(np.float32)
        z1[~(z1 >= TERRAIN_FLOOR)] = np.nan
        fill1 = np.isfinite(z1)
        rest = ~fill1
        z2 = np.full(len(rr), np.nan, np.float32)
        if rest.any():
            z2[rest] = grids.sample(E[rest].astype(np.float64), N[rest].astype(np.float64))
        fill2 = rest & np.isfinite(z2)
        for m, v, L in ((fill1, z1, 1), (fill2, z2, 2)):
            if m.any():
                Z[r0 + rr[m], cc[m]] = v[m]
                lev[r0 + rr[m], cc[m]] = (lev[r0 + rr[m], cc[m]] & ~np.uint8(LEVEL)) | np.uint8(L)
        out["dmr5g"] += int(fill1.sum())
        out["grids"] += int(fill2.sum())
    return out


def needed_tiles(lev, origin, frame):
    """The DMR 5G tiles holding IPR's gaps inside the city: {(ix, iy): gap cells}."""
    import dmr5g
    h, w = lev.shape
    e0, n0 = origin[0] + frame.E0, origin[1] + frame.N0
    out = {}
    for r0 in range(0, h, 256):
        lv = np.asarray(lev[r0:r0 + 256])
        rr, cc = np.nonzero(((lv & LEVEL) == NO) & ((lv & INSIDE) != 0))
        if not len(rr):
            continue
        ix = np.floor((e0 + cc) / dmr5g.TILE).astype(np.int64)
        iy = np.floor((n0 - r0 - rr) / dmr5g.TILE).astype(np.int64)
        u, n = np.unique(np.stack([ix, iy], 1), axis=0, return_counts=True)
        for (a, b), k in zip(u.tolist(), n.tolist()):
            out[(a, b)] = out.get((a, b), 0) + k
    return out


# ---------------------------------------------------------------- the zero areas
def zero_areas(lev, origin, parts, b=32, small=0.01):
    """The general areas inside the city where IPR holds no ground: blocks of b cells with such cells, joined across one
    block; per area its km², what IPR holds, what fills it, the district and cadastral areas it lies in."""
    import shapely
    h, w = lev.shape
    nby, nbx = -(-h // b), -(-w // b)
    by_level = np.zeros((4, nby, nbx), np.int64)
    by_kind = np.zeros((4, nby, nbx), np.int64)
    for by in range(nby):
        lv = np.asarray(lev[by * b:(by + 1) * b])
        if nbx * b > w:
            lv = np.pad(lv, ((0, 0), (0, nbx * b - w)))
        lv = lv.reshape(lv.shape[0], nbx, b)
        gap = ((lv & INSIDE) != 0) & (((lv >> 3) & 3) != 0)
        for v in range(1, 4):
            by_level[v, by] = (gap & ((lv & LEVEL) == v)).sum((0, 2))
            by_kind[v, by] = (gap & (((lv >> 3) & 3) == v)).sum((0, 2))
    any_ = by_kind.sum(0) > 0
    grown = any_.copy()  # (areas a block apart are one)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown[max(0, dy):nby + min(0, dy), max(0, dx):nbx + min(0, dx)] |= \
                any_[max(0, -dy):nby + min(0, -dy), max(0, -dx):nbx + min(0, -dx)]
    lab = np.zeros((nby, nbx), np.int64)
    n = 0
    for sy, sx in zip(*np.nonzero(grown)):
        if lab[sy, sx]:
            continue
        n += 1
        stack = [(sy, sx)]
        lab[sy, sx] = n
        while stack:
            y, x = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < nby and 0 <= xx < nbx and grown[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = n
                        stack.append((yy, xx))
    lab[~any_] = 0
    ox, oy = origin
    areas, rest = [], {"areas": 0, "km2": 0.0}
    for k in range(1, n + 1):
        m = lab == k
        cells = int(by_kind[:, m].sum())
        if not cells:
            continue
        if cells / 1e6 < small:
            rest["areas"] += 1
            rest["km2"] += cells / 1e6
            continue
        ys, xs = np.nonzero(m)
        wts = by_kind[:, m].sum(0)
        cx, cy = ox + (xs + 0.5) * b, oy - (ys + 0.5) * b
        names = {}
        for kind in ("district", "cadastral"):
            got = {}
            for kd, name, g in parts:
                if kd == kind:
                    inside = shapely.contains_xy(g, cx, cy)
                    if inside.any():
                        got[name] = got.get(name, 0) + int(wts[inside].sum())
            tot = sum(got.values()) or 1
            names[kind] = [[nm, round(v / tot, 2)] for nm, v in sorted(got.items(), key=lambda kv: -kv[1]) if v / tot >= 0.05]
        areas.append({"km2": round(cells / 1e6, 3),
                      "holds": {KINDS[v]: round(int(by_kind[v][m].sum()) / 1e6, 3) for v in range(1, 4) if by_kind[v][m].sum()},
                      "filled": {LEVELS[v]: round(int(by_level[v][m].sum()) / 1e6, 3) for v in range(1, 4) if by_level[v][m].sum()},
                      "district": names["district"], "cadastral": names["cadastral"],
                      "box": [round(float(cx.min() - b / 2)), round(float(cy.min() - b / 2)), round(float(cx.max() + b / 2)),
                              round(float(cy.max() + b / 2))],
                      "centre": [round(float(np.average(cx, weights=wts))), round(float(np.average(cy, weights=wts)))]})
    areas.sort(key=lambda a: -a["km2"])
    for i, a in enumerate(areas):
        a["n"] = i + 1
    rest["km2"] = round(rest["km2"], 3)
    return areas, rest


def draw(path, lev, origin, city, parts, segs, areas, px=20):
    """The picture: IPR's ground grey (darker inside the city), the city limits and districts, the tracks, the cells
    inside the city where IPR has no ground, coloured by what fills them, with the areas' numbers. The legend lists what
    the picture shows."""
    from PIL import Image, ImageDraw, ImageFont
    h, w = lev.shape
    nby, nbx = -(-h // px), -(-w // px)
    img = np.full((nby, nbx, 3), 255, np.uint8)
    col = {0: (235, 235, 235), 4: (210, 210, 210), "dmr5g": (43, 108, 176), "grid": (221, 107, 32), "none": (197, 48, 48),
           "out": (255, 205, 210)}
    for by in range(nby):
        lv = np.asarray(lev[by * px:(by + 1) * px])
        if nbx * px > w:
            lv = np.pad(lv, ((0, 0), (0, nbx * px - w)), constant_values=NO)
        lv = lv.reshape(lv.shape[0], nbx, px)
        lvl, ins, kind = lv & LEVEL, (lv & INSIDE) != 0, (lv >> 3) & 3
        share_in = ins.mean((0, 2))
        ground = (lvl != NO).mean((0, 2)) > 0.5
        row = img[by]
        row[ground & (share_in > 0.5)] = col[4]
        row[ground & (share_in <= 0.5)] = col[0]
        gap = ins & (kind != 0)
        row[(~ins & (kind != 0) & (kind != 2)).any((0, 2))] = col["out"]  # (0.00 m or under the floor outside: no ground)
        for key, v in (("dmr5g", 1), ("grid", 2), ("none", 3)):
            row[(gap & (lvl == v)).any((0, 2))] = col[key]
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    ox, oy = origin

    def pt(x, y):
        return ((x - ox) / px, (oy - y) / px)
    for s in segs:
        d.line([pt(s[0], s[1]), pt(s[2], s[3])], fill=(40, 120, 40), width=1)
    for kd, _, g in parts:
        if kd == "district":
            for p in getattr(g, "geoms", [g]):
                if p.geom_type == "Polygon":
                    d.line([pt(x, y) for x, y in p.exterior.coords], fill=(120, 120, 120), width=1)
    for p in getattr(city, "geoms", [city]):
        if p.geom_type == "Polygon":
            d.line([pt(x, y) for x, y in p.exterior.coords], fill=(0, 0, 0), width=3)
    try:
        font, small = ImageFont.truetype("arial.ttf", 22), ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = small = ImageFont.load_default()
    for a in areas:
        x, y = pt(*a["centre"])
        d.text((x + 8, y - 12), str(a["n"]), fill=(0, 0, 0), font=font, stroke_width=3, stroke_fill=(255, 255, 255))
    legend = [((235, 235, 235), "IPR ground outside the city"), ((210, 210, 210), "IPR ground inside the city"),
              (col["dmr5g"], "no IPR ground inside the city: DMR 5G fills it"),
              (col["grid"], "no IPR ground inside the city: a 10 m grid fills it"),
              (col["none"], "no ground inside the city"), (col["out"], "IPR 0.00 m / under 170 m outside the city: no ground")]
    legend = [(c, t) for c, t in legend if (img == c).all(2).any()] + [
        ((0, 0, 0), "city limits (OSM relation 435514)"), ((120, 120, 120), "districts"), ((40, 120, 40), "tram tracks (DI)")]
    if not areas and not (img == col["dmr5g"]).all(2).any():
        legend.insert(0, (None, "IPR has ground in every cell inside the city: no zero areas"))
    y = 12
    d.rectangle([8, 6, 470, 14 + 24 * len(legend)], fill=(255, 255, 255), outline=(0, 0, 0))
    for c, text in legend:
        if c is not None:
            d.rectangle([16, y + 3, 34, y + 17], fill=c, outline=(0, 0, 0))
        d.text((42 if c is not None else 16, y), text, fill=(0, 0, 0), font=small)
        y += 24
    d.line([(16, nby - 30), (16 + 5000 / px, nby - 30)], fill=(0, 0, 0), width=3)
    d.text((16, nby - 54), f"5 km ({px} m a pixel)", fill=(0, 0, 0), font=small)
    im.save(path)


# ---------------------------------------------------------------- the key and the cache
def sha256(path, h=None):
    h = h or hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def key(raster, tiles, grids, tracks, osm, floor=TERRAIN_FLOOR, tolerance=(TOL, D0, TOL_MAX, LAT, CAP), code="",
        box=None):
    """The cache key: the raster's hash, the DMR 5G tiles' and 10 m grids' hashes ({name: sha256}), the track network
    (segments, hashed at 1 mm), the OSM extract's id, the floor, the tolerance's and the mesh's parameters, the code."""
    parts = {"raster": raster, "tiles": tiles, "grids": grids, "osm": osm, "floor": float(floor),
             "tolerance": [float(v) for v in tolerance],
             "mesh": [BASE_BLOCK, BASE_SIGMA, BLOCK, RAMP, RAMP_R], "code": code, "box": list(box) if box else None,
             "tracks": hashlib.sha256(np.round(np.asarray(tracks, np.float64) * 1000).astype(np.int64).tobytes()).hexdigest()}
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()[:32]


def cache_root():
    c = os.environ.get("TRAMDATA_CACHE")
    if not c:
        import tempfile
        c = os.path.join(tempfile.gettempdir(), "tramdata-cache")
        print(f"TRAMDATA_CACHE is not set: the mesh goes to {c}")
    return os.path.join(c, "city-terrain")


def save(d, V, T, origin, report):
    """The mesh and its report into folder d, whole (a temp name, then renamed)."""
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f"mesh.{os.getpid()}.tmp.npz")
    np.savez(tmp, v=V, t=T, origin=np.array(origin, np.float64))
    os.replace(tmp, os.path.join(d, "mesh.npz"))
    tmp = os.path.join(d, f"report.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "report.json"))


def show(rep):
    print(f"city terrain {rep['key']}: {rep['mesh']['triangles']:,} triangles, {rep['mesh']['vertices']:,} vertices")
    for k, b in rep["mesh"]["bands"].items():
        print(f"  {k:>10} m: {b['triangles']:>11,} triangles, {b['cells']:>12,} cells, error mean {b['mean_cm']} cm, "
              f"p99 {b['p99_cm']} cm, max {b['max_cm']} cm")
    for k, v in rep.get("cells", {}).items():
        print(f"  {k}: {v}")
    for a in rep.get("zero_areas", []):
        print(f"  zero area {a['n']}: {a['km2']} km², {a['district']} {a['cadastral']}, holds {a['holds']}, filled {a['filled']}")


# ---------------------------------------------------------------- the run
def main(argv):
    arg = lambda k, d: type(d)(argv[argv.index(k) + 1]) if k in argv else d  # noqa: E731
    box = tuple(float(v) for v in arg("--box", "").split(",")) if "--box" in argv else None
    threads, min_free = arg("--threads", 8), arg("--min-free", 6.0)
    import dmr5g
    import di_network
    import osm_local
    from geo import Frame
    from ipr_dtm import IprDtm, TIF
    F = Frame()
    ipr = IprDtm()
    win = window(ipr, box, F)
    i0, j0, i1, j1 = win
    shape = (j1 - j0, i1 - i0)
    origin = (ipr.e0 - F.E0 + i0, ipr.n0 - F.N0 - j0)
    t_all = time.perf_counter()
    origin = (float(origin[0]), float(origin[1]))
    print(f"window {shape[1]} x {shape[0]} cells, cell (0, 0) at ({origin[0]:.4f}, {origin[1]:.4f})", flush=True)
    net = di_network.load_network()
    segs = segments(net)
    print(f"DI's network: {len(net.edges)} edges, {sum(e['line'].length for e in net.edges.values()) / 1000:.0f} km of track", flush=True)
    grid_paths = sorted(p for p in __import__("glob").glob(os.path.join(ROOT, "raw", "**", "terrain5514.tif"), recursive=True))
    here = os.path.dirname(os.path.abspath(__file__))
    code = hashlib.sha256(b"".join(open(os.path.join(here, f), "rb").read() for f in CODE)).hexdigest()

    def tile_hashes():
        return {f: sha256(os.path.join(dmr5g.DIR, f)) for f in sorted(os.listdir(dmr5g.DIR)) if f.endswith(".tif")}
    t0 = time.perf_counter()
    raster = sha256(TIF)
    grids_h = {os.path.relpath(p, ROOT).replace(os.sep, "/"): sha256(p) for p in grid_paths}
    parts = dict(raster=raster, tiles=tile_hashes(), grids=grids_h, tracks=segs, osm=osm_local.base_id(), code=code, box=box)
    k = key(**parts)
    print(f"key {k} ({time.perf_counter() - t0:.0f} s hashing the inputs)", flush=True)
    out = os.path.join(cache_root(), k)
    rep_dir = os.path.join(ROOT, "reports", "city-terrain")
    os.makedirs(rep_dir, exist_ok=True)
    if os.path.exists(os.path.join(out, "report.json")) and "--force" not in argv:
        rep = json.load(open(os.path.join(out, "report.json"), encoding="utf-8"))
        print(f"from the cache: {out}")
        for f in ("report.json", "zero-areas.png"):
            if os.path.exists(os.path.join(out, f)):
                shutil.copy(os.path.join(out, f), os.path.join(rep_dir, f))
        show(rep)
        return rep
    from baseline_store import HeavyJob
    import contextlib
    import sysinfo
    heavy = shape[0] * shape[1] > SMALL
    with HeavyJob("city_terrain") if heavy else contextlib.nullcontext():
        def guard():  # (the machine is shared: this run ends itself rather than push other jobs into swapping)
            while True:
                if (sysinfo.available_gb() or 99) < min_free:
                    print(f"stopped: free memory under {min_free} GB, peak {peak_gb():.1f} GB", flush=True)
                    os._exit(3)
                time.sleep(1)
        threading.Thread(target=guard, daemon=True).start()
        t_run = time.perf_counter()
        secs = {}
        tmp = os.path.join(cache_root(), f"tmp-{os.getpid()}")
        os.makedirs(tmp, exist_ok=True)
        try:
            t0 = time.perf_counter()
            dl = distances(segs, shape, origin, threads=threads)
            secs["distances"] = time.perf_counter() - t0
            print(f"distances on {dl.size / 1e6:.1f} M lattice points in {secs['distances']:.0f} s", flush=True)
            t0 = time.perf_counter()
            Z = np.memmap(os.path.join(tmp, "z.f32"), np.float32, "w+", shape=shape)
            lev = np.zeros(shape, np.uint8)
            kinds = read_ipr(ipr, win, Z, lev)
            secs["read"] = time.perf_counter() - t0
            print(f"IPR read in {secs['read']:.0f} s: " + ", ".join(f"{KINDS[v]} {kinds[v]:,}" for v in range(4))
                  + f"; peak {peak_gb():.1f} GB", flush=True)
            t0 = time.perf_counter()
            city, parts_ = boundaries(F)
            lev[paint(city, shape, origin)] |= INSIDE
            secs["boundaries"] = time.perf_counter() - t0
            print(f"city limits {city.area / 1e6:.2f} km², {sum(p[0] == 'district' for p in parts_)} districts, "
                  f"{sum(p[0] == 'cadastral' for p in parts_)} cadastral areas, "
                  f"{secs['boundaries']:.0f} s", flush=True)
            need = needed_tiles(lev, origin, F)
            dem = dmr5g.Tiles(fetch="--fetch" in argv)
            missing = sorted(t for t in need if not dem.have(*t))
            print(f"DMR 5G: {len(need)} tiles hold IPR's gaps inside the city, {len(missing)} not in raw/dem/", flush=True)
            if missing and "--fetch" not in argv:
                raise SystemExit(f"{len(missing)} DMR 5G tiles not in raw/dem/ ({', '.join(dmr5g.name(*t) for t in missing[:5])} ...):"
                                 " --fetch downloads them, then publish a snapshot with them")
            for n_, t in enumerate(missing):
                dem.tile(*t)
                dem.tiles.pop(t, None)
                if (n_ + 1) % 20 == 0:
                    print(f"  {n_ + 1}/{len(missing)} tiles downloaded", flush=True)
            t0 = time.perf_counter()
            grids = Grids(grid_paths)
            fb = fallbacks(Z, lev, origin, F, dem, grids)
            secs["fallbacks"] = time.perf_counter() - t0
            print(f"fallbacks: {fb} in {secs['fallbacks']:.0f} s", flush=True)
            if dem.fetched:
                parts["tiles"] = tile_hashes()
                k = key(**parts)
                out = os.path.join(cache_root(), k)
                print(f"{len(dem.fetched)} tiles downloaded: key {k}", flush=True)
            areas, rest = zero_areas(lev, origin, parts_)
            # the cells by level, inside and outside the city
            cnt = np.zeros((2, 4, 4), np.int64)  # inside, level, kind
            for r0 in range(0, shape[0], 512):
                lv = lev[r0:r0 + 512]
                cnt += np.bincount((((lv & INSIDE) != 0).astype(np.int64) * 16 + (lv & LEVEL) * 4 + ((lv >> 3) & 3)).ravel(),
                                   minlength=32).reshape(2, 4, 4)
            Z.flush()
            zpath = Z.filename
            del Z
            V, T, mesh = build(zpath, lev, dl, shape, tmp, threads=threads, log=lambda s: print(s, flush=True))
            secs.update(mesh.pop("s"))
            secs["all"] = time.perf_counter() - t_run
            draw(os.path.join(tmp, "zero-areas.png"), lev, origin, city, parts_, segs, areas)
        finally:
            for f in ("z.f32", "s.f32"):
                try:
                    os.remove(os.path.join(tmp, f))
                except OSError:
                    pass
        km2 = lambda v: round(int(v) / 1e6, 3)  # noqa: E731
        rep = {"key": k, "window": list(win), "origin": list(origin), "tolerance": {"tol": TOL, "d0": D0, "tol_max": TOL_MAX,
               "lattice": LAT, "floor": TERRAIN_FLOOR}, "inputs": {"raster": raster, "tiles": len(parts["tiles"]),
               "grids": grids_h, "osm": parts["osm"], "track_km": round(sum(e["line"].length for e in net.edges.values()) / 1000, 1),
               "code": code},
               "mesh": mesh, "cells": {
                   "inside": {LEVELS[v]: km2(cnt[1, v].sum()) for v in range(4)},
                   "outside": {LEVELS[v]: km2(cnt[0, v].sum()) for v in range(4)},
                   "ipr inside": {KINDS[v]: km2(cnt[1, :, v].sum()) for v in range(4)},
                   "ipr outside": {KINDS[v]: km2(cnt[0, :, v].sum()) for v in range(4)},
                   "rim (no ground under kept triangles)": km2(mesh["rim_cells"])},
               "fallbacks": fb, "dmr5g": {"needed": len(need), "downloaded": len(dem.fetched),
                                          "fetched": [os.path.basename(f) for f in dem.fetched]},
               "zero_areas": areas, "zero_areas_small": rest, "s": {a: round(b, 1) for a, b in secs.items()},
               "peak_gb": round(peak_gb(), 1), "ipr_kinds": {KINDS[v]: int(kinds[v]) for v in range(4)}}
        save(out, V, T, origin, rep)
        shutil.move(os.path.join(tmp, "zero-areas.png"), os.path.join(out, "zero-areas.png"))
        shutil.rmtree(tmp, ignore_errors=True)
        for f in ("report.json", "zero-areas.png"):
            shutil.copy(os.path.join(out, f), os.path.join(rep_dir, f))
        print(f"written {out} in {time.perf_counter() - t_all:.0f} s, peak {peak_gb():.1f} GB")
        show(rep)
        return rep


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
