# SPDX-License-Identifier: AGPL-3.0-or-later
"""Terrain meshes from IPR's 1 m lidar, simplified by an error that grows with distance from the tracks (#276).

Measures candidate meshers on IPR cells (the raster's own cell centres, no resampling): triangles, vertices,
time and the error against every 1 m cell, by distance band from the line's tracks. The error tolerance is
tol(d) = TOL for d <= D0, TOL * d / D0 beyond (a constant angle seen from the track), at most TOL_MAX.

    python -P -E tools/bench/terrain_mesh.py --line 17 [--at E,N] [--size 1024] [--tol 0.10] [--d0 120]
        [--methods now,rtin,delatin,fqmr] [--box] [--out reports/terrain_mesh.json]

--at: the tile's centre in the city frame (default: the line's middle); --box: every tile of the line's terrain box
(tiles of --size cells, each meshed on its own). Methods:
  now      today's ground: a 2 m lattice where d <= D0 + 8 (the fine blocks), the 10 m grid beyond (regular grids)
  rtin     right-triangulated irregular network (Martini's), numpy, split while |error| / tol(d) > 1 at any
           hypotenuse midpoint below: a per-point tolerance, no dependency
  delatin  greedy insertion of the worst point (Garland-Heckbert), pydelatin (MIT), on heights divided by
           tol(d): one max_error = 1 then stands for the per-point tolerance (exact only where tol is constant)
  fqmr     quadric edge collapse (pyfqmr, MIT) of the full 1 m mesh to delatin's triangle count
Cells without lidar (outside Prague) take the line's 10 m grid; their share is reported. pydelatin and pyfqmr
are bench-only: a method whose module is missing is skipped.
"""
import json
import os
import sys
import time

import numpy as np
import shapely
from shapely.geometry import LineString

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402

arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
LINE, SIZE, TOL, D0, TOL_MAX = arg("--line", "17"), arg("--size", 1024), arg("--tol", 0.10), arg("--d0", 120.0), 3.0
METHODS = arg("--methods", "now,rtin,delatin,fqmr").split(",")
BANDS = [(0, 10), (10, 120), (120, 500), (500, 1e9)]
F = Frame()


def peak_gb():
    """The process's peak memory so far (Windows: the peak working set; elsewhere ru_maxrss)."""
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] +                        [(k, ctypes.c_size_t) for k in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
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


def tol(d):
    return np.minimum(TOL * np.maximum(d, D0) / D0, TOL_MAX)


# --- inputs ---------------------------------------------------------------------------------------------
line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
T = line["terrain"]
coarse_h = np.frombuffer(__import__("base64").b64decode(T["data"]), "<i2").reshape(T["ny"], T["nx"]) * T["scale"] + T["base"]
paths = [line["path"]] + ([line["pathBack"]] if line.get("pathBack") else [])
segs = []
for p in paths:  # the tracks as short pieces for a nearest-neighbour index
    a = np.array([q[:2] for q in p], float)
    segs += [LineString(a[i:i + 2]) for i in range(len(a) - 1) if np.any(a[i] != a[i + 1])]
tree = shapely.STRtree(segs)
dtm = IprDtm()


def coarse(X, Y):
    fx = np.clip((X - T["x0"]) / T["dx"], 0, T["nx"] - 1.0001)
    fy = np.clip((Y - T["y0"]) / T["dy"], 0, T["ny"] - 1.0001)
    i, j = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - i, fy - j
    h = coarse_h
    return (h[j, i] * (1 - tx) + h[j, i + 1] * tx) * (1 - ty) + (h[j + 1, i] * (1 - tx) + h[j + 1, i + 1] * tx) * ty


def distance(X, Y, step=4):
    """Distance to the nearest track at every cell: exact on a `step` lattice, bilinear between (<= 2.9 m off)."""
    xs, ys = X[0, ::step], Y[::step, 0]
    xs = np.append(xs, X[0, -1]) if xs[-1] != X[0, -1] else xs
    ys = np.append(ys, Y[-1, 0]) if ys[-1] != Y[-1, 0] else ys
    gx, gy = np.meshgrid(xs, ys)
    _, d = tree.query_nearest(shapely.points(gx.ravel(), gy.ravel()), return_distance=True, all_matches=False)
    d = d.reshape(gx.shape)
    fi = np.interp(X[0], xs, np.arange(len(xs)))
    fj = np.interp(-Y[:, 0], -ys, np.arange(len(ys)))  # (rows go south: np.interp wants rising points)
    i0, j0 = np.minimum(fi.astype(int), len(xs) - 2), np.minimum(fj.astype(int), len(ys) - 2)
    tx, ty = (fi - i0)[None, :], (fj - j0)[:, None]
    I0, J0 = i0[None, :], j0[:, None]
    return ((d[J0, I0] * (1 - tx) + d[J0, I0 + 1] * tx) * (1 - ty) + (d[J0 + 1, I0] * (1 - tx) + d[J0 + 1, I0 + 1] * tx) * ty)


def tile(cx, cy, n, m=None):
    """(Z, X, Y) of n+1 x n+1 IPR cells around (cx, cy) in the city frame, rows north to south; NaN filled."""
    e, nn = F.to_jtsk(cx, cy)
    m = n if m is None else m  # (n columns, m rows)
    i0 = int(round(e - dtm.e0)) - n // 2
    j0 = int(round(dtm.n0 - nn)) - m // 2
    I, J = np.meshgrid(np.arange(i0, i0 + n + 1), np.arange(j0, j0 + m + 1))
    Z = np.empty(I.shape)
    for r in range(0, I.shape[0], 512):  # in strips: cells() scans its whole input once per raster tile
        for q in range(0, I.shape[1], 512):
            Z[r:r + 512, q:q + 512] = dtm.cells(I[r:r + 512, q:q + 512], J[r:r + 512, q:q + 512])
    X, Y = F.from_jtsk(dtm.e0 + I, dtm.n0 - J)
    miss = np.isnan(Z)
    if miss.any():
        Z[miss] = coarse(X[miss], Y[miss])
    return Z, X, Y, float(miss.mean())


# --- mesh evaluation ----------------------------------------------------------------------------------------
def rasterize(V, Tr, shape):
    """Heights of the triangle mesh (vertices (col, row, z)) at every cell of the grid."""
    out = np.full(shape, np.nan)
    a, b, c = V[Tr[:, 0]], V[Tr[:, 1]], V[Tr[:, 2]]
    x0 = np.floor(np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0])).astype(np.int64)
    x1 = np.ceil(np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])).astype(np.int64)
    y0 = np.floor(np.minimum(np.minimum(a[:, 1], b[:, 1]), c[:, 1])).astype(np.int64)
    y1 = np.ceil(np.maximum(np.maximum(a[:, 1], b[:, 1]), c[:, 1])).astype(np.int64)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    cnt = w * h
    cum = np.cumsum(cnt)
    cuts = np.searchsorted(cum, np.arange(0, cum[-1], 20_000_000), side="right")  # chunks of ~20 M cells
    for lo, hi in zip(cuts, list(cuts[1:]) + [len(Tr)]):
        if hi <= lo:
            continue
        sl = slice(lo, hi)
        k = np.repeat(np.arange(lo, hi), cnt[sl])
        st = np.repeat(np.cumsum(cnt[sl]) - cnt[sl], cnt[sl])
        o = np.arange(len(k)) - st
        px, py = x0[k] + o % w[k], y0[k] + o // w[k]
        ax, ay, bx, by, cx, cy = a[k, 0], a[k, 1], b[k, 0], b[k, 1], c[k, 0], c[k, 1]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        l3 = 1 - l1 - l2
        ok = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9) & (px >= 0) & (py >= 0) & (px < shape[1]) & (py < shape[0])
        out[py[ok], px[ok]] = l1[ok] * a[k[ok], 2] + l2[ok] * b[k[ok], 2] + l3[ok] * c[k[ok], 2]
    return out


def report(name, Z, D, M, ntri, nver, secs):
    err = np.abs(M - Z)
    r = {"method": name, "triangles": int(ntri), "vertices": int(nver), "s": round(secs, 2),
         "over_tol_%": round(100 * float(np.mean(err > tol(D) + 1e-6)), 3), "bands": {}}
    for lo, hi in BANDS:
        m = (D >= lo) & (D < hi)
        if m.any():
            e = err[m]
            r["bands"][f"{lo}-{int(hi) if hi < 1e9 else ''}"] = {"cells": int(m.sum()), "mean_cm": round(100 * float(e.mean()), 2),
                                                               "p99_cm": round(100 * float(np.percentile(e, 99)), 1),
                                                               "max_cm": round(100 * float(e.max()), 1)}
    return r


def grid_mesh(n, step, mask=None):
    """A regular grid of `step` cells over an (n+1)^2 tile, two triangles a cell (only cells touching mask)."""
    idx = np.arange(0, n + 1, step)
    if idx[-1] != n:
        idx = np.append(idx, n)
    gx, gy = np.meshgrid(idx, idx)
    k = lambda i, j: j * len(idx) + i  # noqa: E731
    I, J = np.meshgrid(np.arange(len(idx) - 1), np.arange(len(idx) - 1))
    I, J = I.ravel(), J.ravel()
    if mask is not None:
        keep = mask[idx[J], idx[I]] | mask[idx[J + 1], idx[I + 1]] | mask[idx[J], idx[I + 1]] | mask[idx[J + 1], idx[I]]
        I, J = I[keep], J[keep]
    tri = np.concatenate([np.stack([k(I, J), k(I + 1, J), k(I + 1, J + 1)], 1), np.stack([k(I, J), k(I + 1, J + 1), k(I, J + 1)], 1)])
    return np.stack([gx.ravel(), gy.ravel()], 1), tri


def m_now(Z, D):
    n = Z.shape[0] - 1
    fine = D <= D0 + 8
    out, ntri, nver = np.full(Z.shape, np.nan), 0, 0
    for step, mask in ((10, ~fine), (2, fine)):  # the fine blocks are drawn over the coarse grid
        if not mask.any():
            continue
        P, tri = grid_mesh(n, step, mask if step == 2 else None)
        V = np.column_stack([P, Z[P[:, 1], P[:, 0]]])
        M = rasterize(V, tri, Z.shape)
        sel = mask if step == 2 else np.ones_like(mask)
        out[sel & ~np.isnan(M)] = M[sel & ~np.isnan(M)]
        ntri += len(tri) if step == 2 else int(len(tri) * (~fine).mean() + 0.5)  # the 10 m grid's share of the tile
        nver += len(np.unique(tri))
    return out, ntri, nver


def m_rtin(Z, D):
    """Martini's RTIN with the error propagated as error / tol at each point, levels vectorised."""
    n = Z.shape[0] - 1
    assert n & (n - 1) == 0, "rtin needs --size a power of two"
    S = n + 1
    Zf, tl = Z.ravel(), tol(D).ravel()
    # every level's triangles: (a, b) the hypotenuse, c the apex
    lv = [np.array([[n, n, 0, 0, 0, n], [0, 0, n, n, n, 0]], np.int64)]  # (ax, ay, bx, by, cx, cy)
    while True:
        t = lv[-1]
        ax, ay, bx, by, cx, cy = t.T
        if max(abs(ax - bx).max(), abs(ay - by).max()) <= 1:
            break
        mx, my = (ax + bx) >> 1, (ay + by) >> 1
        lv.append(np.concatenate([np.stack([cx, cy, ax, ay, mx, my], 1), np.stack([bx, by, cx, cy, mx, my], 1)]))
    lv.pop()  # the last level's hypotenuses have no midpoint
    ratio = np.zeros(S * S)
    for t in reversed(lv):  # smallest first: the children's ratios are final when the parent reads them
        ax, ay, bx, by, cx, cy = t.T
        mid = ((ay + by) >> 1) * S + ((ax + bx) >> 1)
        e = np.abs((Zf[ay * S + ax] + Zf[by * S + bx]) / 2 - Zf[mid]) / tl[mid]
        lc = ((ay + cy) >> 1) * S + ((ax + cx) >> 1)
        rc = ((by + cy) >> 1) * S + ((bx + cx) >> 1)
        if max(abs(ax - cx).max(), abs(ay - cy).max()) > 1:  # (legs longer than one cell have midpoints)
            e = np.maximum(e, np.maximum(ratio[lc], ratio[rc]))
        np.maximum.at(ratio, mid, e)
    leaves, t = [], lv[0]
    for _ in range(len(lv)):
        ax, ay, bx, by, cx, cy = t.T
        mid = ((ay + by) >> 1) * S + ((ax + bx) >> 1)
        split = ratio[mid] > 1
        leaves.append(t[~split])
        t = t[split]
        ax, ay, bx, by, cx, cy = t.T
        mx, my = (ax + bx) >> 1, (ay + by) >> 1
        t = np.concatenate([np.stack([cx, cy, ax, ay, mx, my], 1), np.stack([bx, by, cx, cy, mx, my], 1)])
    leaves.append(t)
    L = np.concatenate(leaves)
    ids = np.concatenate([L[:, 1] * S + L[:, 0], L[:, 3] * S + L[:, 2], L[:, 5] * S + L[:, 4]])
    u, inv = np.unique(ids, return_inverse=True)
    V = np.column_stack([u % S, u // S, Zf[u]]).astype(np.float64)
    return V, inv.reshape(3, -1).T


def m_delatin(Z, D):
    from pydelatin import Delatin
    tl = tol(D)
    d = Delatin(Z / tl, max_error=1.0)
    V = d.vertices.astype(np.float64).copy()
    V[:, 1] = Z.shape[0] - 1 - V[:, 1]  # (its y counts rows from the bottom)
    V[:, 2] =Z[V[:, 1].astype(int), V[:, 0].astype(int)]  # back to metres at the vertices (they lie on cells)
    return V, d.triangles.astype(np.int64)


def m_fqmr(Z, ntarget):
    import pyfqmr
    n = Z.shape[0] - 1
    P, tri = grid_mesh(n, 1)
    s = pyfqmr.Simplify()
    s.setMesh(np.column_stack([P, Z.ravel()]).astype(np.float64), tri.astype(np.int32))
    s.simplify_mesh(target_count=int(ntarget), aggressiveness=7, preserve_border=True, verbose=False)
    V, Tr, _ = s.getMesh()
    return np.asarray(V, np.float64), np.asarray(Tr, np.int64)


def encode_sizes(V, Tr):
    """Bytes of one mesh: float32 + uint32 as three.js takes them, and integer differences (vertices in a
    grid-walk order, heights in cm, triangle indices as differences to the previous triangle's largest), gzip."""
    import gzip
    import lzma
    o = np.lexsort((V[:, 0], V[:, 1]))  # row by row: neighbours in the file are neighbours on the ground
    rank = np.empty(len(o), np.int64)
    rank[o] = np.arange(len(o))
    W = V[o]
    T2 = np.sort(rank[Tr], 1)
    T2 = T2[np.lexsort((T2[:, 0], T2[:, 2]))]
    zz = lambda a: ((a << 1) ^ (a >> 63)).astype(np.uint64)  # noqa: E731 (zigzag)

    def varint(a):
        out = bytearray()
        for v in a.tolist():
            while v >= 0x80:
                out.append(v & 0x7F | 0x80)
                v >>= 7
            out.append(v)
        return bytes(out)
    q = np.column_stack([W[:, 0], W[:, 1], np.round(W[:, 2] * 100)]).astype(np.int64)
    dv = np.diff(q, axis=0, prepend=q[:1] * 0)
    prev = np.concatenate([[0], T2[:-1, 2]])
    dt = T2 - prev[:, None]
    delta = varint(zz(dv.ravel())) + varint(zz(dt.ravel()))
    plain = np.column_stack([V[:, :2], V[:, 2]]).astype("<f4").tobytes() + Tr.astype("<u4").tobytes()
    return {"float32_kB": len(plain) // 1024, "float32_gzip_kB": len(gzip.compress(plain, 6)) // 1024,
            "delta_kB": len(delta) // 1024, "delta_gzip_kB": len(gzip.compress(delta, 9)) // 1024,
            "delta_xz_kB": len(lzma.compress(delta)) // 1024}


def run(cx, cy, n, methods):
    Z, X, Y, miss = tile(cx, cy, n)
    D = distance(X, Y)
    rows = []
    for m in methods:
        t0 = time.perf_counter()
        try:
            if m == "now":
                M, ntri, nver = m_now(Z, D)
                rows.append(report(m, Z, D, M, ntri, nver, time.perf_counter() - t0))
                continue
            if m == "rtin":
                V, Tr = m_rtin(Z, D)
            elif m == "delatin":
                V, Tr = m_delatin(Z, D)
            elif m == "fqmr":
                ref = next((r for r in rows if r["method"] == "delatin"), None) or next((r for r in rows if r["method"] == "rtin"), None)
                V, Tr = m_fqmr(Z, ref["triangles"] if ref else 200000)
        except ImportError as ex:
            print(f"  {m}: skipped ({ex})")
            continue
        secs = time.perf_counter() - t0
        rows.append(report(m, Z, D, rasterize(V, Tr, Z.shape), len(Tr), len(V), secs))
        if "--encode" in sys.argv:
            rows[-1]["bytes"] = encode_sizes(V, Tr)
    return {"at": [round(cx), round(cy)], "cells": int(Z.size), "no_lidar_%": round(100 * miss, 2),
            "d_min": round(float(D.min()), 1), "rows": rows}


def show(res):
    print(f"tile at {res['at']}: {res['cells']} cells, no lidar {res['no_lidar_%']} %, nearest track {res['d_min']} m")
    for r in res["rows"]:
        b = "  ".join(f"{k}: {v['mean_cm']}/{v['p99_cm']}/{v['max_cm']}" for k, v in r["bands"].items())
        print(f"  {r['method']:8s} {r['triangles']:>9,} tri {r['vertices']:>9,} v {r['s']:6.1f} s  over tol {r['over_tol_%']:6.3f} %  "
              f"[mean/p99/max cm by band] {b}")


if __name__ == "__main__":
    out = {"line": LINE, "size": SIZE, "tol": TOL, "d0": D0, "tol_max": TOL_MAX, "tiles": []}
    if "--whole" in sys.argv:  # the whole box as one greedy mesh, then cut into tiles of --size along their lines
        x1, y1 = T["x0"] + (T["nx"] - 1) * T["dx"], T["y0"] + (T["ny"] - 1) * T["dy"]
        n, m = int(x1 - T["x0"]) // 2 * 2, int(T["y0"] - y1) // 2 * 2
        t0 = time.perf_counter()
        Z, X, Y, miss = tile((T["x0"] + x1) / 2, (T["y0"] + y1) / 2, n, m)
        D = distance(X, Y)
        del X, Y
        t_in, gb_in = time.perf_counter() - t0, peak_gb()
        t0 = time.perf_counter()
        V, Tr = m_delatin(Z, D)
        t_mesh, gb_mesh = time.perf_counter() - t0, peak_gb()
        r = report("delatin whole", Z, D, rasterize(V, Tr, Z.shape), len(Tr), len(V), t_mesh)
        # the triangles a tile line crosses, cut by the tiles they overlap (each piece by the constrained Delaunay):
        # both tiles cut the same triangle along the same line, so they share the border's vertices exactly
        a, b, c = V[Tr[:, 0], :2], V[Tr[:, 1], :2], V[Tr[:, 2], :2]
        lo, hi = np.minimum(np.minimum(a, b), c), np.maximum(np.maximum(a, b), c)
        cross = np.any(np.floor(lo / SIZE) != np.floor(np.nextafter(hi, -np.inf) / SIZE), axis=1)
        t0 = time.perf_counter()
        polys = shapely.polygons(np.stack([a[cross], b[cross], c[cross], a[cross]], 1))
        boxes = np.array([shapely.box(x, y, x + SIZE, y + SIZE) for y in range(0, m, SIZE) for x in range(0, n, SIZE)])
        pi, bi = shapely.STRtree(boxes).query(polys, predicate="intersects")
        pieces = shapely.intersection(polys[pi], boxes[bi])
        pieces = shapely.get_parts(pieces)
        pieces = pieces[(shapely.get_type_id(pieces) == 3) & (shapely.area(pieces) > 1e-6)]
        after = len(shapely.get_parts(shapely.constrained_delaunay_triangles(pieces)))
        t_cut = time.perf_counter() - t0
        k = int(cross.sum())
        print(f"whole box {n} x {m} cells (read {t_in:.0f} s), no lidar {100 * miss:.2f} %; peak memory "
              f"{gb_in:.1f} GB after the read, {gb_mesh:.1f} GB after the mesh")
        print(f"  {r['triangles']:,} triangles, {r['vertices']:,} vertices in {t_mesh:.0f} s, over tol {r['over_tol_%']} %")
        for key, v in r["bands"].items():
            print(f"  {key} m: mean {v['mean_cm']} cm, p99 {v['p99_cm']} cm, max {v['max_cm']} cm")
        print(f"  cut into {SIZE} m tiles: {k:,} triangles cross a tile line -> {after:,} "
              f"({after - k:+,}, {100 * (after - k) / len(Tr):+.2f} % of the mesh) in {t_cut:.1f} s")
        # triangles per km² by the distance of their centroid from the tracks (to scale to other areas)
        g = (a + b + c) / 3
        dc = D[np.clip(np.round(g[:, 1]).astype(int), 0, m), np.clip(np.round(g[:, 0]).astype(int), 0, n)]
        dens = {}
        for lo, hi in BANDS + [(500, 1000), (1000, 2000), (2000, 1e9)]:
            km2 = float(((D >= lo) & (D < hi)).sum()) / 1e6
            nt = int(((dc >= lo) & (dc < hi)).sum())
            dens[f"{lo}-{int(hi) if hi < 1e9 else ''}"] = {"km2": round(km2, 2), "triangles": nt, "per_km2": round(nt / km2) if km2 else None}
            print(f"  {lo}-{int(hi) if hi < 1e9 else ''} m: {km2:.2f} km², {nt:,} triangles, {nt / km2 if km2 else 0:,.0f} per km²")
        out["whole"] = {**r, "cross": k, "after_cut": after, "density": dens, "peak_gb": [gb_in, gb_mesh], "s": [t_in, t_mesh]}
        dst = arg("--out", "")
        if dst:
            json.dump(out, open(os.path.join(ROOT, dst), "w"), indent=1)
        sys.exit(0)
    if "--box" in sys.argv:
        x1, y1 = T["x0"] + (T["nx"] - 1) * T["dx"], T["y0"] + (T["ny"] - 1) * T["dy"]
        centres = [(x + SIZE / 2, y - SIZE / 2) for y in np.arange(T["y0"], y1, -SIZE) for x in np.arange(T["x0"], x1, SIZE)]
    else:
        at = arg("--at", "")
        if at:
            centres = [tuple(float(v) for v in at.split(","))]
        else:
            p = line["path"][len(line["path"]) // 2]
            centres = [(p[0], p[1])]
    for k, (cx, cy) in enumerate(centres):
        res = run(cx, cy, SIZE, METHODS)
        for r in res["rows"]:
            r.pop("_mesh", None)
        show(res) if len(centres) < 4 else print(f"{k + 1}/{len(centres)}", end="\r")
        out["tiles"].append(res)
    if len(centres) > 1:  # the whole box: sums and cell-weighted errors per method and band
        tot = {}
        for t in out["tiles"]:
            for r in t["rows"]:
                s = tot.setdefault(r["method"], {"triangles": 0, "vertices": 0, "s": 0.0, "bands": {}})
                s["triangles"] += r["triangles"]
                s["vertices"] += r["vertices"]
                s["s"] += r["s"]
                for k, v in r["bands"].items():
                    b = s["bands"].setdefault(k, {"cells": 0, "sum": 0.0, "p99": [], "max_cm": 0})
                    b["cells"] += v["cells"]
                    b["sum"] += v["mean_cm"] * v["cells"]
                    b["p99"].append((v["p99_cm"], v["cells"]))
                    b["max_cm"] = max(b["max_cm"], v["max_cm"])
        print()
        for m, s in tot.items():
            bands = "  ".join(f"{k}: {b['sum'] / b['cells']:.2f}/{max(p for p, _ in b['p99']):.1f}(worst tile p99)/{b['max_cm']}"
                              for k, b in s["bands"].items())
            print(f"box {m:8s} {s['triangles']:>11,} tri {s['vertices']:>11,} v {s['s']:7.0f} s  {bands}")
        out["box"] = tot
        no = [t["no_lidar_%"] * t["cells"] for t in out["tiles"]]
        print(f"no lidar: {sum(no) / sum(t['cells'] for t in out['tiles']):.2f} % of the box's cells")
    dst = arg("--out", "")
    if dst:
        json.dump(out, open(os.path.join(ROOT, dst), "w"), indent=1, default=lambda o: o.get("p99") if isinstance(o, dict) else str(o))
