# SPDX-License-Identifier: AGPL-3.0-or-later
"""The whole city's terrain as one greedy mesh: what it costs (#276). Waits its turn among the heavy jobs.

Reads every tile of IPR's 1 m raster into one float32 array of height / tol(d) (terrain_mesh.py's tolerance, d the
distance to the nearest tram track in the local OSM extract, on an 8 m lattice) and meshes it in one pydelatin call. No
data outside the city: the tile's mean there (a tile with no data: its neighbours'), so a boundary costs few triangles;
triangles with their centroid there are not counted. Reports triangles per distance band, time and peak memory; the error
is terrain_mesh.py's to measure. Stops itself when the machine's free memory falls under --min-free GB.

    python -P -E tools/bench/terrain_city.py [--tol 0.10] [--d0 120] [--min-free 6] [--out reports/terrain_city.json]
(needs pydelatin, bench-only)
"""
import json
import os
import sys
import threading
import time

import numpy as np
import shapely
from shapely.geometry import LineString

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_store import HeavyJob  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
import osm_local  # noqa: E402
import sysinfo  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
TOL, D0, TOL_MAX, MIN_FREE, LAT = arg("--tol", 0.10), arg("--d0", 120.0), 3.0, arg("--min-free", 6.0), 8
BANDS = [(0, 10), (10, 120), (120, 500), (500, 1000), (1000, 2000), (2000, 1e9)]
F = Frame()


def peak_gb():
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
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.PeakWorkingSetSize / 2**30


def guard():
    """The machine is shared: this run ends itself rather than push other jobs into swapping."""
    while True:
        if sysinfo.available_gb() < MIN_FREE:
            print(f"stopped: free memory under {MIN_FREE} GB, peak {peak_gb():.1f} GB", flush=True)
            os._exit(3)
        time.sleep(1)


def main():
    from pydelatin import Delatin
    threading.Thread(target=guard, daemon=True).start()
    t0 = time.perf_counter()
    dtm = IprDtm()
    ways = osm_local.ways(lambda t: t.get("railway") == "tram")
    segs = []
    for w in ways:
        p = np.column_stack(F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]]))
        segs += [LineString(p[k:k + 2]) for k in range(len(p) - 1) if np.any(p[k] != p[k + 1])]
    # the distance on a lattice of the raster's cells (rows north to south)
    cols, rows = np.arange(0, dtm.w + LAT, LAT), np.arange(0, dtm.h + LAT, LAT)
    x, y = F.from_jtsk(dtm.e0 + cols.astype(float), dtm.n0 - rows.astype(float))
    gx, gy = np.meshgrid(x, y)
    _, dist = shapely.STRtree(segs).query_nearest(shapely.points(gx.ravel(), gy.ravel()), return_distance=True, all_matches=False)
    dist = dist.reshape(gx.shape).astype(np.float32)
    del gx, gy
    t_dist = time.perf_counter() - t0
    print(f"{sum(s.length for s in segs) / 1000:.0f} km of track, the distances on {dist.size / 1e6:.0f} M points in {t_dist:.0f} s, "
          f"peak {peak_gb():.1f} GB", flush=True)

    t0 = time.perf_counter()
    W = np.empty((dtm.h, dtm.w), np.float32)
    ntx, nty = dtm.ntx, -(-dtm.h // dtm.th)
    means, valid = np.full((nty, ntx), np.nan), 0
    cj, ci = np.arange(dtm.th) / LAT, np.arange(dtm.tw) / LAT
    for ty in range(nty):
        for tx in range(ntx):
            a = dtm.tile(tx, ty)
            dtm.tiles.clear()
            j0, i0 = ty * dtm.th, tx * dtm.tw
            h, w = min(dtm.th, dtm.h - j0), min(dtm.tw, dtm.w - i0)
            a = a[:h, :w]
            fj, fi = j0 / LAT + cj[:h], i0 / LAT + ci[:w]
            J, I = fj.astype(int), fi.astype(int)
            tj, ti = (fj - J)[:, None].astype(np.float32), (fi - I)[None, :].astype(np.float32)
            Ja, Ia = J[:, None], I[None, :]
            d = (dist[Ja, Ia] * (1 - ti) + dist[Ja, Ia + 1] * ti) * (1 - tj) + (dist[Ja + 1, Ia] * (1 - ti) + dist[Ja + 1, Ia + 1] * ti) * tj
            t = np.minimum(TOL * np.maximum(d, D0) / D0, TOL_MAX)
            v = a / t
            ok = ~np.isnan(v)
            valid += int(ok.sum())
            if ok.any():
                means[ty, tx] = float(v[ok].mean())
            W[j0:j0 + h, i0:i0 + w] = v
    while np.isnan(means).any():  # (tiles with no data take their neighbours' mean)
        m = np.pad(means, 1, constant_values=np.nan)
        near = np.stack([m[:-2, 1:-1], m[2:, 1:-1], m[1:-1, :-2], m[1:-1, 2:]])
        have = ~np.isnan(near)
        fill = np.where(have.any(0), np.nansum(near, 0) / np.maximum(have.sum(0), 1), np.nan)
        means = np.where(np.isnan(means), fill, means)
    nodata = []
    for ty in range(nty):
        for tx in range(ntx):
            j0, i0 = ty * dtm.th, tx * dtm.tw
            s = W[j0:j0 + dtm.th, i0:i0 + dtm.tw]
            miss = np.isnan(s)
            s[miss] = means[ty, tx]
            nodata.append(float(miss.mean()) == 1.0)
    t_read = time.perf_counter() - t0
    print(f"raster {dtm.w} x {dtm.h}: {valid / 1e6:.0f} km² with data, read in {t_read:.0f} s, peak {peak_gb():.1f} GB", flush=True)

    t0 = time.perf_counter()
    d = Delatin(W, max_error=1.0)
    V, Tr = d.vertices, d.triangles
    t_mesh = time.perf_counter() - t0
    print(f"meshed: {len(Tr):,} triangles, {len(V):,} vertices in {t_mesh:.0f} s, peak {peak_gb():.1f} GB", flush=True)

    g = V[Tr, :2].mean(1)
    row = dtm.h - 1 - g[:, 1]
    fj, fi = np.clip(row / LAT, 0, dist.shape[0] - 1), np.clip(g[:, 0] / LAT, 0, dist.shape[1] - 1)
    dc = dist[fj.astype(int), fi.astype(int)]
    ty, tx = (row // dtm.th).astype(int).clip(0, nty - 1), (g[:, 0] // dtm.tw).astype(int).clip(0, ntx - 1)
    outside = np.array(nodata).reshape(nty, ntx)[ty, tx]
    rows_out = {}
    for lo, hi in BANDS:
        m = (dc >= lo) & (dc < hi) & ~outside
        rows_out[f"{lo}-{int(hi) if hi < 1e9 else ''}"] = int(m.sum())
        print(f"  {lo}-{int(hi) if hi < 1e9 else ''} m: {int(m.sum()):,} triangles", flush=True)
    print(f"  in tiles with no data at all: {int(outside.sum()):,}", flush=True)
    out = {"tol": TOL, "d0": D0, "cells": dtm.w * dtm.h, "with_data": valid, "triangles": int(len(Tr)), "vertices": int(len(V)), "bands": rows_out,
           "outside": int(outside.sum()), "s": {"distance": t_dist, "read": t_read, "mesh": t_mesh}, "peak_gb": peak_gb()}
    dst = arg("--out", "")
    if dst:
        with open(os.path.join(ROOT, dst), "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    print(f"peak memory {peak_gb():.1f} GB")


if __name__ == "__main__":
    with HeavyJob("terrain_city"):
        main()
