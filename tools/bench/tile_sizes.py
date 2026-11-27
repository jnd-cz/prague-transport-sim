# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a tile size costs (#30): a line's ground file cut into squares of each size (m, from the city origin; a
triangle goes to the square holding its centre), each encoded on its own (ground_mesh.encode) and brotli'd, and a drive
along its route every 25 m with two windows of tiles held (round the tram, and along 1 km of route ahead): the tiles,
triangles and the page's MB held, the loads and MB fetched per km. Measured on one line for the maintainer's choice
of 500 m (#30's comment).

Usage: python -P -E tools/bench/tile_sizes.py LINE [SIZES]      (sizes in m, default 128,256,512,1024)
"""
import json
import os
import sys
import time

import brotli
import numpy as np
import shapely
import shapely.ops

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ground_mesh as gm  # noqa: E402

ln = sys.argv[1]
sizes = [float(s) for s in (sys.argv[2] if len(sys.argv) > 2 else "128,256,512,1024").split(",")]
# the windows: radius round the tram, and the route ahead held loaded (each tile within `side` of it)
WINDOWS = {"fog (950 m round, 1 km ahead)": (950.0, 1000.0, 950.0), "near (400 m round, 1 km ahead)": (400.0, 1000.0, 400.0)}
STEP = 25.0  # m along the route
layout = json.load(open(os.path.join(ROOT, "data", f"line{ln}.ground.json"), encoding="utf-8"))
V, by, draw, area = gm.decode(open(os.path.join(ROOT, "data", f"line{ln}.ground.bin"), "rb").read(), layout, draw=True, area=True)
F = np.concatenate([by[c] for c in gm.CLASS_IDS])
cls = np.concatenate([np.full(len(by[c]), gm.CLASS_IDS[c]) for c in gm.CLASS_IDS])
dr = np.concatenate([np.asarray(draw.get(c, np.full(len(by[c]), "", dtype=object)), dtype=object) for c in gm.CLASS_IDS])
ar = np.concatenate([np.asarray(area.get(c, np.full(len(by[c]), "", dtype=object)), dtype=object) for c in gm.CLASS_IDS])
cen = V[F][:, :, :2].mean(1)
L = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
route = shapely.LineString([p[:2] for p in L["path"]])
whole = len(brotli.compress(open(os.path.join(ROOT, "data", f"line{ln}.ground.bin"), "rb").read(), quality=9))
print(f"line {ln}: {len(F):,} triangles, {len(V):,} vertices, the file {whole / 1e6:.2f} MB brotli; route {route.length / 1e3:.1f} km\n")
rows, drive = [], []
for T in sizes:
    t0 = time.time()
    ti, tj = np.floor(cen[:, 0] / T).astype(int), np.floor(cen[:, 1] / T).astype(int)
    keys, inv, ntri = np.unique(np.column_stack([ti, tj]), axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind="stable")
    cut = np.searchsorted(inv[order], np.arange(len(keys) + 1))
    kb, nv, gpu = np.zeros(len(keys)), np.zeros(len(keys), int), np.zeros(len(keys), int)
    for k in range(len(keys)):
        m = order[cut[k]:cut[k + 1]]
        f = F[m]
        used, fl = np.unique(f, return_inverse=True)
        nv[k] = len(used)
        # (the page's vertices: each draw class its own, src/groundWorker.js)
        gpu[k] = len(np.unique(np.column_stack([f.ravel(), np.repeat(cls[m] * 1000 + np.unique(dr[m], return_inverse=True)[1].ravel(), 3)]), axis=0))
        i, j = int(keys[k, 0]), int(keys[k, 1])
        Vt = np.round(V[used] * 1000).astype(np.int64)
        b, _ = gm.encode(Vt, fl.reshape(-1, 3), cls[m], shapely.box(i * T, j * T, (i + 1) * T, (j + 1) * T), dr[m], ar[m])
        kb[k] = len(brotli.compress(b, quality=9)) / 1e3
    mem = (gpu * 36 + ntri * 12) / 1e6  # MB: positions, normals, colours (3 floats each) and 3 uint32 indexes
    rows.append((T, len(keys), ntri, kb, nv, mem))
    # the drive: per window, the tiles loaded at each step (their squares within the window)
    cxy = (keys + 0.5) * T
    boxes = shapely.box(keys[:, 0] * T, keys[:, 1] * T, (keys[:, 0] + 1) * T, (keys[:, 1] + 1) * T)
    tree = shapely.STRtree(boxes)
    for wname, (R, ahead, side) in WINDOWS.items():
        prev, loads, got, n_t, n_tri, n_mem = set(), 0, 0.0, [], [], []
        for s in np.arange(0, route.length, STEP):
            p = route.interpolate(s)
            win = p.buffer(R, quad_segs=8)
            if ahead > 0:
                seg = shapely.ops.substring(route, s, min(route.length, s + ahead)) if s < route.length else p
                win = win.union(seg.buffer(side, quad_segs=4))
            now = set(tree.query(win, predicate="intersects").tolist())
            new = now - prev
            loads += len(new) if prev else 0
            got += kb[list(new)].sum() if prev else 0.0
            prev = now
            idx = list(now)
            n_t.append(len(idx))
            n_tri.append(ntri[idx].sum())
            n_mem.append(mem[idx].sum())
        km = route.length / 1e3
        drive.append((T, wname, np.mean(n_t), max(n_t), np.mean(n_tri), max(n_tri), np.mean(n_mem), max(n_mem), loads / km, got / 1e3 / km))
    print(f"  {T:.0f} m: {time.time() - t0:.0f} s", file=sys.stderr, flush=True)

print("| tile | tiles | triangles per tile p50 / p90 / max | brotli kB per tile p50 / p90 / max | all tiles MB (brotli) | vertices: all tiles / the file's | GPU MB per tile p50 / max |")
print("|---|---|---|---|---|---|---|")
for T, n, ntri, kb, nv, mem in rows:
    print(f"| {T:.0f} m | {n} | {np.median(ntri):,.0f} / {np.percentile(ntri, 90):,.0f} / {ntri.max():,} | "
          f"{np.median(kb):.0f} / {np.percentile(kb, 90):.0f} / {kb.max():.0f} | {kb.sum() / 1e3:.2f} | "
          f"{nv.sum() / len(V):.3f} | {np.median(mem):.1f} / {mem.max():.1f} |")
print()
print("| tile | window | tiles loaded mean / max | triangles loaded mean / max (M) | GPU MB mean / max | tile loads per km | MB fetched per km |")
print("|---|---|---|---|---|---|---|")
for T, w, a, b, c, d, e, f, g, h in drive:
    print(f"| {T:.0f} m | {w} | {a:.1f} / {b} | {c / 1e6:.2f} / {d / 1e6:.2f} | {e:.0f} / {f:.0f} | {g:.1f} | {h:.2f} |")
