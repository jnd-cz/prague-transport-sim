# SPDX-License-Identifier: AGPL-3.0-or-later
"""The terrain mesh cut by the survey's ground areas (#276, T1-T3 of docs/research/osm2world/terrain.md).

Builds terrain_mesh.py's greedy (delatin) mesh on one tile, removes what the survey's level-0 ground areas cover
and triangulates the cut triangles' remains with shapely's constrained Delaunay (their edges kept; a piece of
one planar triangle needs no interior points). Reports the terrain's triangles before and after, what lay
hidden, the survey's own triangles, the times and a check that no remaining terrain overlaps the survey.

    python -P -E tools/bench/ground_cut.py --line 17 [--at X,Y] [--size 1024] [--tol 0.10]
(needs pydelatin, bench-only: see terrain_mesh.py)
"""
import json
import os
import sys
import time

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_mesh as tm  # noqa: E402

ROOT = tm.ROOT
dtm = json.load(open(os.path.join(ROOT, "data", f"line{tm.LINE}.dtm.json"), encoding="utf-8"))
ground = lambda a: a["l"] == 0 and a["c"] not in ("wall", "roof", "deck", "rail") and len(a.get("r") or []) > 2  # noqa: E731 (src/terrain.js groundArea)

at = tm.arg("--at", "")
p = tm.line["path"][len(tm.line["path"]) // 2]
cx, cy = (float(v) for v in at.split(",")) if at else (p[0], p[1])
Z, X, Y, _ = tm.tile(cx, cy, tm.SIZE)
D = tm.distance(X, Y)
t0 = time.perf_counter()
V, Tr = tm.m_delatin(Z, D)
t_mesh = time.perf_counter() - t0
# vertices (col, row) to the city frame: the cells are 1 m apart, rows going south
x = X[0, 0] + V[:, 0]
y = Y[0, 0] - V[:, 1]
tile = shapely.box(X[0, 0], Y[-1, 0], X[0, -1], Y[0, 0])

t0 = time.perf_counter()
polys = []
for a in dtm["areas"]:
    if not ground(a):
        continue
    g = shapely.make_valid(shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) > 2]))
    if g.intersects(tile):
        polys.append(g.intersection(tile))
polys = [g for g in polys if not g.is_empty]
cover = shapely.union_all(polys)
shapely.prepare(cover)
t_cover = time.perf_counter() - t0

t0 = time.perf_counter()
tris = shapely.polygons(np.stack([np.column_stack([x[Tr[:, k]], y[Tr[:, k]]]) for k in (0, 1, 2, 0)], 1))
inside = shapely.within(tris, cover)
touch = shapely.intersects(tris, cover) & ~inside
rest = shapely.difference(tris[touch], cover)
rest = rest[~shapely.is_empty(rest)]
parts = shapely.get_parts(rest)
parts = parts[shapely.area(parts) > 1e-4]
cut_tris = shapely.get_parts(shapely.constrained_delaunay_triangles(parts))
t_cut = time.perf_counter() - t0

t0 = time.perf_counter()
survey_tris = sum(len(shapely.get_parts(shapely.constrained_delaunay_triangles(g))) for g in shapely.get_parts(cover))
t_survey = time.perf_counter() - t0

kept = int((~inside & ~touch).sum())
after = kept + len(cut_tris)
overlap = float(shapely.area(shapely.intersection(shapely.union_all(cut_tris), cover))) if len(cut_tris) else 0.0
print(f"tile {tm.SIZE} m at ({cx:.0f}, {cy:.0f}): {len(polys)} survey ground areas cover {100 * cover.area / tile.area:.1f} % of it")
print(f"terrain mesh (delatin, tol {tm.TOL} m): {len(Tr):,} triangles in {t_mesh:.1f} s")
print(f"  under the survey (dropped): {int(inside.sum()):,}; crossing its edges (cut): {int(touch.sum()):,}; untouched: {kept:,}")
print(f"  the cut remains: {len(parts):,} pieces -> {len(cut_tris):,} triangles; terrain after: {after:,} "
      f"({100 * (after - len(Tr)) / len(Tr):+.1f} %), cut in {t_cut:.1f} s (+{t_cover:.1f} s the cover)")
print(f"  terrain left over the survey: {overlap:.3f} m² (should be ~0)")
print(f"survey ground: {survey_tris:,} constrained triangles in {t_survey:.1f} s")
