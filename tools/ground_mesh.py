# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground triangulated, welded and encoded: one mesh file per line (#508, #276 step 4).

    python -P -E tools/ground_mesh.py --line 37          # data/line37.ground.bin and .json, the report
    python -P -E tools/ground_mesh.py --lines 9,17,22,23,37
    (--mesh DIR: a city mesh folder other than the current inputs', for trials; --no-write: the report only)

From the partition (tools/ground_partition.py partition(): survey, bed, plot and terrain, nothing under anything else):

1. **Faces.** Per TILE m square of the box, every class's outline, the cut terrain triangles' remains, the beds' outline
   on the ground, the rails (each drawn track's, at the bed's rows: tools/bed_surface.py) and the square's own border are
   noded and polygonized into faces, so two faces meeting along an edge share every vertex on it (no T-junction). The
   terrain's triangles that nothing crosses stay as they are. Each face takes the class at its inner point.
2. **Triangles.** Each face by shapely's constrained Delaunay (its edges kept: kerbs, bed edges, footprints, rails).
3. **Heights.** Each face's vertices by its class:
   - inside the beds' outline (but a raised area: a platform, a sidewalk, an island): the bed surface, the lowest bed
     there (bed_surface.Beds.surface: the rails at top of rail - lift -+ the cant's tilt, as the page lays the bed);
   - survey: the generated street surface (data/lineN.streets.*, #512) on roads, tram areas and sidewalks; elsewhere
     the survey area's own surface (its outline's heights, triangulated);
   - plot: its height (the partition's);
   - terrain: the city mesh triangle's plane.
4. **The weld.** At a vertex the faces share, one height by priority, not averaged: the bed, then the survey (by rank),
   then the terrain. A face keeps its own height (a step: two vertices at one point) where it differs from the weld's
   by more than STEP for its pair: a kerb (a raised area beside a street or a bed), a building plot, a wall between the
   survey and the terrain. Every step's edge gets its vertical faces, so every edge is used by two triangles.
5. **The file.** data/lineN.ground.bin: vertices in mm (x, y from the box's corner, z over its base) sorted by row and
   column, as zigzag varint differences; per class, its triangles' indexes as differences. lineN.ground.json: the
   layout, the counts, the provenance. Decoded by decode() (and by the page, #509).

The report (reports/ground-mesh/lineN.json): triangles per class against what the page draws today, the error against
IPR's 1 m raster by distance band, the fallback levels, the steps by pair, the file's size raw, gzip and brotli, the
rails' check (the mesh under each rail within RAIL_TOL of the bed's row), the edge check, the build time.
"""
import gzip
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TILE = 512.0  # m: the squares the faces are built in (one future tile edge each, #30)
Q = 1000  # vertices per m: positions and heights in mm
CLASS_IDS = {"terrain": 0, "survey": 1, "bed": 2, "plot": 3, "wall": 4}
RAISED = {"sidewalk", "island", "median", "platform"}  # (src/world.js RAISED: they keep their height over a bed)
STREETS_ROAD, STREETS_WALK = {"road", "tram"}, {"sidewalk"}  # (the classes the generated street surface covers, #512)
# m: a face's height differing from the weld's by more than this at a shared vertex stays a step (to measure: the
# report counts every pair's differences)
STEP = {"kerb": 0.03, "plot": 0.01, "wall": 0.5}
BED_REACH = 0.5  # m: a corner in the beds' outline this far past a row's edge takes the edge's height (bed_surface)
RAIL_TOL = 0.001  # m: the mesh under a rail against the bed's row (#508's done-when)
BANDS = ((0, 10), (10, 120), (120, 500), (500, math.inf))
LATTICE = 4  # m: the error's samples, every LATTICE-th cell of IPR's 1 m raster


# ---------------------------------------------------------------- heights
class SurveySurface:
    """Each survey area's own surface: its outline's heights, triangulated (the page's DtmSurface)."""

    def __init__(self, D, areas):
        self.tris, self.area = [], []
        for i in sorted(set(areas)):
            a = D["areas"][i]
            if any(q[2] is None for q in a["r"]):
                continue
            g = shapely.Polygon([tuple(q) for q in a["r"]],
                                [[tuple(q) for q in h] for h in a.get("h", []) if len(h) >= 3 and all(p[2] is not None for p in h)])
            if not g.is_valid:
                g = shapely.make_valid(g)
            for t in shapely.get_parts(shapely.constrained_delaunay_triangles(g)):
                c = shapely.get_coordinates(t, include_z=True)[:3]
                if np.isfinite(c).all():
                    self.tris.append(c)
                    self.area.append(i)
        self.tris = np.asarray(self.tris, float).reshape(-1, 3, 3)
        self.area = np.asarray(self.area, int)
        self.tree = shapely.STRtree(shapely.polygons(self.tris[:, [0, 1, 2, 0], :2])) if len(self.tris) else None

    def at(self, area, x, y):
        """Heights of points of one area (NaN where none of its triangles holds them)."""
        out = np.full(len(x), np.nan)
        if self.tree is None or not len(x):
            return out
        pi, ti = self.tree.query(shapely.points(x, y), predicate="intersects")
        ok = self.area[ti] == area
        pi, ti = pi[ok], ti[ok]
        z = plane(self.tris[ti], x[pi], y[pi])
        out[pi] = z
        miss = np.isnan(out)
        if miss.any():  # (on the outline, a hair outside every triangle: the nearest vertex's height)
            mine = self.tris[self.area == area].reshape(-1, 3)
            if len(mine):
                d = (mine[None, :, 0] - x[miss, None]) ** 2 + (mine[None, :, 1] - y[miss, None]) ** 2
                out[miss] = mine[d.argmin(1), 2]
        return out


def plane(tri, x, y):
    """Heights on the planes of triangles (n, 3, 3) at (x, y), barycentric."""
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    d = np.where(np.abs(d) < 1e-12, 1e-12, d)
    w0 = ((b[:, 1] - c[:, 1]) * (x - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y - c[:, 1])) / d
    w1 = ((c[:, 1] - a[:, 1]) * (x - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y - c[:, 1])) / d
    return w0 * a[:, 2] + w1 * b[:, 2] + (1 - w0 - w1) * c[:, 2]


class Streets:
    """The generated street surface (data/lineN.streets.*, #512): road and sidewalk heights on its grid, bilinear, the
    nearest cell of the class within NEAR cells where a point lies on the class's edge."""
    NEAR = 2

    def __init__(self, ln):
        import street_profile
        try:
            self.sq, self.meta = street_profile.read_streets(ln, ROOT)
        except OSError:
            self.sq, self.meta = {}, None

    def at(self, kind, x, y):
        out = np.full(len(x), np.nan)
        if not self.meta:
            return out
        cell, g, n = self.meta["cell"], self.meta["grid"], self.meta["side"]
        k = 2 if kind == "road" else 3
        i = np.floor(x / cell).astype(int)
        j = np.floor(y / cell).astype(int)
        for key in set(zip(i.tolist(), j.tolist())):
            if key not in self.sq:
                continue
            m = (i == key[0]) & (j == key[1])
            x0, y1 = self.sq[key][0], self.sq[key][1]
            Z = self.sq[key][k]
            c = (x[m] - x0) / g - 0.5
            r = (y1 - y[m]) / g - 0.5
            c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
            fc, fr = c - c0, r - r0

            def cellz(rr, cc, Z=Z):
                ok = (rr >= 0) & (rr < n) & (cc >= 0) & (cc < n)
                v = np.full(len(rr), np.nan)
                v[ok] = Z[rr[ok], cc[ok]]
                return v
            a, b = cellz(r0, c0), cellz(r0, c0 + 1)
            cc_, d = cellz(r0 + 1, c0), cellz(r0 + 1, c0 + 1)
            z = (a * (1 - fc) + b * fc) * (1 - fr) + (cc_ * (1 - fc) + d * fc) * fr
            bad = np.isnan(z)
            if bad.any():  # (an edge: the nearest cell of the class)
                rr, cc = np.round(r[bad]).astype(int), np.round(c[bad]).astype(int)
                best = np.full(bad.sum(), np.nan)
                bd = np.full(bad.sum(), np.inf)
                for dr in range(-self.NEAR, self.NEAR + 1):
                    for dc in range(-self.NEAR, self.NEAR + 1):
                        v = cellz(rr + dr, cc + dc)
                        dd = (rr + dr - r[bad]) ** 2 + (cc + dc - c[bad]) ** 2
                        better = np.isfinite(v) & (dd < bd)
                        best[better], bd[better] = v[better], dd[better]
                z[bad] = best
            out[m] = z
        return out


# ---------------------------------------------------------------- faces
def rail_lines(beds, outline):
    """The rails of every drawn track, at the bed's rows, inside the beds' outline on the ground."""
    out = []
    for rows in beds.rows:
        if len(rows) < 2:
            continue
        for j in (1, 2):
            pts = [(x + nx * off[j], y + ny * off[j]) for x, y, nx, ny, off, _ in rows]
            out.append(shapely.LineString(pts))
    if not out:
        return []
    clipped = shapely.intersection(np.array(out, dtype=object), outline)
    return [g for g in shapely.get_parts(clipped) if g.geom_type == "LineString" and g.length > 1e-3]


def tile_faces(rect, lines_tree, lines, kept_tree, kept_tris):
    """The faces of one square: its lines (and its border) noded and polygonized, those inside a terrain triangle kept
    whole left out (that triangle is the mesh there)."""
    R = shapely.box(*rect)
    idx = lines_tree.query(R, predicate="intersects")
    parts = [shapely.clip_by_rect(lines[i], *rect) for i in idx.tolist()]
    parts = [g for g in parts if not g.is_empty]
    # (the border with every point a line meets it at, the lines of the square beside included: a vertex lying on the
    # border with its piece on the other side only is in both squares' border, or the two borders differ: a T-junction)
    border = R.boundary
    hits = shapely.get_coordinates(shapely.intersection(border, lines[idx])) if len(idx) else np.zeros((0, 2))
    if len(hits):
        ring = shapely.get_coordinates(border)[:-1]
        t = np.concatenate([shapely.line_locate_point(border, shapely.points(ring)), shapely.line_locate_point(border, shapely.points(hits))])
        pts = np.vstack([ring, hits])
        t[:len(ring)][0] = 0.0
        o = np.argsort(t, kind="stable")
        pts = pts[o]
        keep = np.concatenate([[True], np.hypot(*np.diff(pts, axis=0).T) > 1e-9])
        border = shapely.LineString(np.vstack([pts[keep], pts[:1]]))
    noded = shapely.node(shapely.union_all([border] + parts)) if parts else border
    faces = np.asarray(shapely.get_parts(shapely.polygonize(shapely.get_parts(noded))))
    if not len(faces):
        return faces
    faces = faces[shapely.area(faces) > 0]
    if kept_tree is not None and len(faces):
        pi, _ = kept_tree.query(shapely.point_on_surface(faces), predicate="intersects")
        drop = np.zeros(len(faces), bool)
        drop[pi] = True
        faces = faces[~drop]
    return faces


# ---------------------------------------------------------------- the build
def build(ln, mesh=None, threads=8, log=print):
    import bed_surface
    import ground_partition as gp
    t0 = time.time()
    pieces, prep, _ = gp.partition(ln, mesh, threads, geometry=True)
    G = pieces["_"]
    L, D, box = G["L"], G["D"], G["box"]
    x, y, z, T = G["x"], G["y"], G["z"], G["T"]
    t_part = time.time() - t0
    log(f"line {ln}: partition in {t_part:.0f} s")
    t1 = time.time()
    beds = bed_surface.Beds(L)
    outline = G["beds outline"]
    rails = rail_lines(beds, outline)
    log(f"  beds: {sum(len(r) for r in beds.rows)} rows, {len(rails)} rail pieces on the ground, {time.time() - t1:.0f} s")
    bx0, by0, bx1, by1 = box.bounds

    # the lines that make the faces, and what each face can be
    tri_xy = np.stack([np.column_stack([x[T[:, k]], y[T[:, k]]]) for k in range(3)], 1)
    kept = np.asarray(G["kept"], int)
    tb = np.stack([tri_xy[kept, :, 0].min(1), tri_xy[kept, :, 1].min(1), tri_xy[kept, :, 0].max(1), tri_xy[kept, :, 1].max(1)], 1)
    ti = np.floor((tb[:, [0, 2]] - bx0) / TILE).astype(int)
    tj = np.floor((tb[:, [1, 3]] - by0) / TILE).astype(int)
    whole = (ti[:, 0] == ti[:, 1]) & (tj[:, 0] == tj[:, 1])  # (inside one square: no square's border crosses it)
    kept_whole, kept_border = kept[whole], kept[~whole]
    lines, owners = [], []  # (owners: what the face inside a line's polygon is: (class, id))
    for k, q in enumerate(pieces["survey"]):
        lines.append(q["g"].boundary)
        owners.append(("survey", k, q["g"]))
    for k, q in enumerate(pieces["bed"]):
        lines.append(q["g"].boundary)
        owners.append(("bed", k, q["g"]))
    for k, q in enumerate(pieces["plot"]):
        lines.append(q["g"].boundary)
        owners.append(("plot", k, q["g"]))
    for parent, g in G["remains"]:
        lines.append(g.boundary)
        owners.append(("terrain", int(parent), g))
    for t in kept_border.tolist():
        g = shapely.Polygon(tri_xy[t])
        lines.append(g.boundary)
        owners.append(("terrain", t, g))
    if not outline.is_empty:
        lines.append(outline.boundary)
    lines += rails
    lines = np.asarray(lines, dtype=object)
    lines_tree = shapely.STRtree(lines)
    own_geoms = np.asarray([o[2] for o in owners], dtype=object)
    own_tree = shapely.STRtree(own_geoms)
    kept_polys = shapely.polygons(np.concatenate([tri_xy[kept_whole], tri_xy[kept_whole][:, :1]], 1)) if len(kept_whole) else None
    kept_tree = shapely.STRtree(kept_polys) if kept_polys is not None else None

    nx_, ny_ = int(math.ceil((bx1 - bx0) / TILE)), int(math.ceil((by1 - by0) / TILE))
    rects = [(bx0 + i * TILE, by0 + j * TILE, min(bx1, bx0 + (i + 1) * TILE), min(by1, by0 + (j + 1) * TILE))
             for i in range(nx_) for j in range(ny_)]
    t1 = time.time()
    with ThreadPoolExecutor(threads) as ex:
        faces = list(ex.map(lambda r: tile_faces(r, lines_tree, lines, kept_tree, kept_polys), rects))
    faces = np.concatenate([f for f in faces if len(f)]) if any(len(f) for f in faces) else np.zeros(0, object)
    log(f"  {len(faces):,} faces in {len(rects)} squares, {time.time() - t1:.0f} s")

    # each face's owner: the piece holding its inner point (the smallest, where a remains polygon lies on its triangle)
    t1 = time.time()
    inner = shapely.point_on_surface(faces)
    fi, oi = own_tree.query(inner, predicate="intersects")
    owner = np.full(len(faces), -1)
    order = np.argsort(shapely.area(own_geoms[oi]))[::-1]  # (smallest last: it wins)
    owner[fi[order]] = oi[order]
    lost = owner < 0
    if lost.any():  # (slivers between the pieces, under SLIVER: the nearest piece's class)
        li, lo = own_tree.query_nearest(inner[lost], all_matches=False)
        owner[np.flatnonzero(lost)[li]] = lo
    n_lost, a_lost = int(lost.sum()), float(shapely.area(faces[lost]).sum())
    lost = owner < 0
    shapely.prepare(outline)
    in_bed = shapely.contains_xy(outline, *shapely.get_coordinates(inner).T) if not outline.is_empty else np.zeros(len(faces), bool)
    log(f"  owners: {n_lost} faces in no piece ({a_lost:.3f} m²) took the nearest's, {time.time() - t1:.0f} s")
    faces, owner, in_bed = faces[~lost], owner[~lost], in_bed[~lost]

    # triangles of the faces
    t1 = time.time()
    tris, tf = shapely.get_parts(shapely.constrained_delaunay_triangles(faces), return_index=True)
    fc = shapely.get_coordinates(tris).reshape(-1, 4, 2)[:, :3]
    log(f"  {len(fc):,} face triangles, {time.time() - t1:.0f} s")

    # per triangle corner: its class, its own height, its weld priority
    fcls = np.array([owners[o][0] for o in owner])
    tcls = fcls[tf]
    t_in_bed = in_bed[tf]
    cx, cy = fc[:, :, 0].ravel(), fc[:, :, 1].ravel()
    corner_face = np.repeat(tf, 3)
    corner_cls = np.repeat(tcls, 3)
    zc = np.full(len(cx), np.nan)
    prio = np.full(len(cx), 9.0)
    kind = np.full(len(cx), "", dtype=object)
    from track_styles import RANK
    surface = SurveySurface(D, [pieces["survey"][owners[o][1]]["area"] for o in owner if owners[o][0] == "survey"])
    streets = Streets(ln)
    # terrain: the parent triangle's plane
    m = corner_cls == "terrain"
    par = np.array([owners[o][1] for o in owner])[corner_face[m]]
    tri3 = np.stack([np.column_stack([x[T[par, k]], y[T[par, k]], z[T[par, k]]]) for k in range(3)], 1)
    zc[m], prio[m], kind[m] = plane(tri3, cx[m], cy[m]), 3.0, "terrain"
    # plots
    m = corner_cls == "plot"
    zc[m] = [pieces["plot"][owners[o][1]]["z"] for o in owner[corner_face[m]]]
    prio[m], kind[m] = 4.0, "plot"
    # survey
    m = np.flatnonzero(corner_cls == "survey")
    sv = [pieces["survey"][owners[o][1]] for o in owner[corner_face[m]]]
    sc = np.array([q["c"] for q in sv])
    sa = np.array([q["area"] for q in sv])
    zs = np.full(len(m), np.nan)
    for kd, cls in (("road", STREETS_ROAD), ("sidewalk", STREETS_WALK)):
        mm = np.isin(sc, list(cls))
        if mm.any():
            zs[mm] = streets.at(kd, cx[m][mm], cy[m][mm])
    need = np.isnan(zs)
    for a in np.unique(sa[need]).tolist():
        mm = need & (sa == a)
        zs[mm] = surface.at(a, cx[m][mm], cy[m][mm])
    zc[m] = zs
    prio[m] = 2.0 + np.array([(10 - RANK.get(c, 1)) / 100 for c in sc])
    kind[m] = np.where(np.isin(sc, list(RAISED)), "raised", "survey")
    # the beds' outline: the bed surface (not a raised area)
    m = np.flatnonzero(np.repeat(t_in_bed, 3) & (kind != "raised") & (corner_cls != "plot"))
    zb = np.array([np.nan if (v := beds.surface(a, b, BED_REACH)) is None else v for a, b in zip(cx[m], cy[m])], float)
    ok = np.isfinite(zb)
    zc[m[ok]], prio[m[ok]], kind[m[ok]] = zb[ok], 1.0, "bed"
    nan = np.isnan(zc)
    no_height = {str(c): int(n) for c, n in zip(*np.unique(np.where(kind[nan] == "", corner_cls[nan], kind[nan]), return_counts=True))}
    log(f"  heights: {int(nan.sum())} corners without one {no_height}, {time.time() - t1:.0f} s")
    if nan.any():  # (a survey area without heights: the lidar's)
        from geo import Frame
        from ipr_dtm import IprDtm
        F_ = Frame()
        zc[nan] = np.asarray(IprDtm().sample(cx[nan] + F_.E0, cy[nan] + F_.N0), float)

    # the weld
    t1 = time.time()
    key = np.round(cx * Q).astype(np.int64) * 10_000_000_000 + np.round(cy * Q).astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    top_p = np.full(len(uk), np.inf)
    np.minimum.at(top_p, inv, prio)
    is_top = prio == top_p[inv]
    top_z = np.full(len(uk), np.nan)
    first = np.full(len(uk), -1)
    tops = np.flatnonzero(is_top)
    first[inv[tops[::-1]]] = tops[::-1]  # (the first top corner of each vertex)
    top_z = zc[first]
    top_kind = kind[first]
    dz = zc - top_z[inv]
    pair = np.where(kind == "plot", "plot",
                    np.where((kind == "raised") != (top_kind[inv] == "raised"), "kerb",
                             np.where((kind == "terrain") != (top_kind[inv] == "terrain"), "wall", "")))
    lim = np.array([STEP.get(p, np.inf) for p in pair]) if len(pair) else np.zeros(0)
    step = ~is_top & (np.abs(dz) > lim)
    zf = np.where(step, zc, top_z[inv])
    steps = {p: {"corners": int((step & (pair == p)).sum()),
                 "|dz| at shared corners, p50 / p90 / p99 / max m": [round(float(np.percentile(np.abs(dz[(pair == p) & ~is_top]), q)), 3)
                                                                     for q in (50, 90, 99, 100)] if ((pair == p) & ~is_top).any() else None}
             for p in STEP}
    # vertex ids: (x, y, z in mm)
    zq = np.round(zf * Q).astype(np.int64)
    vkey = np.stack([np.round(cx * Q).astype(np.int64), np.round(cy * Q).astype(np.int64), zq], 1)
    V, vid = np.unique(vkey, axis=0, return_inverse=True)
    F = vid.reshape(-1, 3)
    fcls_id = np.array([CLASS_IDS[c] for c in tcls])
    log(f"  weld: {len(uk):,} points, {len(V):,} vertices, steps {[(p, s['corners']) for p, s in steps.items()]}, "
        f"{time.time() - t1:.0f} s")

    # the kept terrain triangles, as they are
    kv = np.stack([np.round(x * Q), np.round(y * Q), np.round(z * Q)], 1).astype(np.int64)
    KT = T[kept_whole]
    used = np.unique(KT)
    allv = np.vstack([V, kv[used]])
    V2, inv2 = np.unique(allv, axis=0, return_inverse=True)
    F = inv2[:len(V)][F]
    remap = np.full(len(x), -1)
    remap[used] = inv2[len(V):]
    KF = remap[KT]
    F = np.vstack([F, KF])
    fcls_id = np.concatenate([fcls_id, np.zeros(len(KF), int)])
    V = V2

    # the steps' walls: an edge whose two sides hold different vertices at an end
    t1 = time.time()
    walls = step_walls(V, F)
    F = np.vstack([F, walls]) if len(walls) else F
    fcls_id = np.concatenate([fcls_id, np.full(len(walls), CLASS_IDS["wall"])])
    # (no degenerate triangles)
    good = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F, fcls_id = F[good], fcls_id[good]
    log(f"  {len(walls):,} wall triangles, {time.time() - t1:.0f} s")

    rep = {"line": ln, "partition": {k: prep[k] for k in ("box", "box_km2", "classes", "cover", "terrain")},
           "faces": len(faces), "vertices": int(len(V)), "triangles": int(len(F)),
           "triangles per class": {c: int((fcls_id == i).sum()) for c, i in CLASS_IDS.items()},
           "steps": steps, "corners without a height (IPR's)": no_height, "seconds": {"partition": round(t_part, 1)}}
    rep["edges"] = edge_check(V, F, box)
    rep["rails"] = rail_check(cx, cy, zf, kind, beds, outline)
    rep["page today"] = page_counts(L, D)
    rep["seconds"]["mesh"] = round(time.time() - t0 - t_part, 1)
    return {"V": V, "F": F, "cls": fcls_id, "box": box, "L": L, "rep": rep}


def xy_ids(V):
    """Each vertex's point in the plane as an id (vertices at one point, a step's two, share it)."""
    return np.unique(V[:, :2], axis=0, return_inverse=True)[1].ravel()


def step_walls(V, F):
    """Vertical faces along every edge where the two triangles beside it hold different vertices at the same point."""
    k = xy_ids(V)
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    ka, kb = k[e[:, 0]], k[e[:, 1]]
    lo, hi = np.minimum(ka, kb), np.maximum(ka, kb)
    flip = ka > kb
    a = np.where(flip, e[:, 1], e[:, 0])
    b = np.where(flip, e[:, 0], e[:, 1])
    order = np.lexsort((hi, lo))
    lo, hi, a, b = lo[order], hi[order], a[order], b[order]
    same = (lo[1:] == lo[:-1]) & (hi[1:] == hi[:-1])
    i = np.flatnonzero(same)
    a1, b1, a2, b2 = a[i], b[i], a[i + 1], b[i + 1]
    out = []
    for p, q, r, s in zip(a1.tolist(), b1.tolist(), a2.tolist(), b2.tolist()):
        if p == r and q == s:
            continue
        if p != r:
            out.append((p, q, r) if q == s else (p, q, s))
        if q != s:
            out.append((p, s, r) if p != r else (p, s, q))
    return np.asarray(out, int).reshape(-1, 3)


def edge_check(V, F, box):
    """Every edge in the plane used by two triangles, or on the box's border (the walls left out: they stand on the steps'
    edges): the edges used once, inside the box."""
    flat = F[~is_wall(V, F)]
    k = xy_ids(V)
    first = np.zeros(k.max() + 1, int)
    first[k] = np.arange(len(k))
    e = np.vstack([flat[:, [0, 1]], flat[:, [1, 2]], flat[:, [2, 0]]])
    a, b = k[e[:, 0]], k[e[:, 1]]
    pairs = np.stack([np.minimum(a, b), np.maximum(a, b)], 1)
    u, cnt = np.unique(pairs, axis=0, return_counts=True)
    ax, ay = V[first[u[:, 0]], 0], V[first[u[:, 0]], 1]
    bxx, byy = V[first[u[:, 1]], 0], V[first[u[:, 1]], 1]
    x0, y0, x1, y1 = (round(v * Q) for v in box.bounds)
    on_border = ((ax == bxx) & ((ax == x0) | (ax == x1))) | ((ay == byy) & ((ay == y0) | (ay == y1)))
    once = (cnt == 1) & ~on_border
    more = cnt > 2
    out = {"edges": int(len(u)), "used once inside the box": int(once.sum()), "used more than twice": int(more.sum())}
    if once.any():
        w = np.flatnonzero(once)[:5]
        out["first used once"] = [[[int(ax[i]) / Q, int(ay[i]) / Q], [int(bxx[i]) / Q, int(byy[i]) / Q]] for i in w]
    return out


def is_wall(V, F):
    """Triangles standing upright: two corners on one point."""
    xy = V[F][:, :, :2]
    return ((xy[:, 0] == xy[:, 1]).all(1) | (xy[:, 1] == xy[:, 2]).all(1) | (xy[:, 0] == xy[:, 2]).all(1))


def mesh_at(V, F, px, py):
    """The mesh's height at points (the upright walls left out): NaN off it; the highest where triangles overlap."""
    flat = F[~is_wall(V, F)]
    P = V[flat].astype(float) / Q
    tree = shapely.STRtree(shapely.polygons(np.concatenate([P[:, :, :2], P[:, :1, :2]], 1)))
    pi, ti = tree.query(shapely.points(px, py), predicate="intersects")
    out = np.full(len(px), np.nan)
    if len(pi):
        zz = plane(P[ti], px[pi], py[pi])
        np.fmax.at(out, pi, zz)
    return out


def rail_check(cx, cy, zf, kind, beds, outline):
    """The ground under every rail point of every bed row on the ground (the welded height of the bed's corner there)
    against the row's height (#508: within RAIL_TOL). Where two beds overlap (a switch, a crossing) the ground takes the
    lower one: those points are counted apart."""
    pts, want = [], []
    for rows in beds.rows:
        for x, y, nx, ny, off, z in rows:
            for j in (1, 2):
                pts.append((x + nx * off[j], y + ny * off[j]))
                want.append(z[j])
    if not pts:
        return {}
    pts, want = np.asarray(pts), np.asarray(want)
    on = shapely.contains_xy(outline, pts[:, 0], pts[:, 1]) if not outline.is_empty else np.zeros(len(pts), bool)
    pts, want = pts[on], want[on]
    on_bed = kind == "bed"
    kq = np.round(cx[on_bed] * Q).astype(np.int64) * 10_000_000_000 + np.round(cy[on_bed] * Q).astype(np.int64)
    zq = dict(zip(kq.tolist(), zf[on_bed].tolist()))
    pk = np.round(pts[:, 0] * Q).astype(np.int64) * 10_000_000_000 + np.round(pts[:, 1] * Q).astype(np.int64)
    got = np.array([zq.get(k, np.nan) for k in pk.tolist()])
    lowest = np.array([np.nan if (v := beds.surface(a, b)) is None else v for a, b in pts], float)
    d = got - want
    under = np.isfinite(lowest) & (lowest < want - RAIL_TOL)  # (another bed lower there)
    own = ~under & np.isfinite(d)
    return {"rail points on the ground": int(len(pts)),
            "within the tolerance": int((np.abs(d[own]) <= RAIL_TOL + 0.5 / Q).sum()),
            "off by more": int((np.abs(d[own]) > RAIL_TOL + 0.5 / Q).sum()),
            "worst, mm": round(float(np.abs(d[own]).max()) * 1000, 2) if own.any() else None,
            "where another bed lies lower (the ground takes it)": int(under.sum()),
            "not a corner of the bed (left out)": missing_kinds(cx, cy, kind, pk[np.isnan(d)])}


def missing_kinds(cx, cy, kind, keys):
    """What holds the rail points that no bed corner holds: the kinds of the corners there, or none (not a vertex)."""
    ka = np.round(cx * Q).astype(np.int64) * 10_000_000_000 + np.round(cy * Q).astype(np.int64)
    by = {}
    for k, kd in zip(ka.tolist(), kind.tolist()):
        by.setdefault(k, set()).add(kd)
    out = {}
    for k in keys.tolist():
        name = "+".join(sorted(by[k])) if k in by else "not a vertex"
        e = out.setdefault(name, {"points": 0, "first": []})
        e["points"] += 1
        if len(e["first"]) < 4:
            e["first"].append([k // 10_000_000_000 / Q, (k - k // 10_000_000_000 * 10_000_000_000) / Q])
    return out


def page_counts(L, D):
    """The triangles the page draws today for the ground: the 10 m grid, the fine blocks, the survey's ground areas."""
    T = L["terrain"]
    out = {"10 m grid": 2 * (T["nx"] - 1) * (T["ny"] - 1)}
    fine = os.path.join(ROOT, "data", f"line{L['line']}.fine.json")
    if os.path.exists(fine):
        f = json.load(open(fine, encoding="utf-8"))
        out["fine blocks"] = len(f.get("blocks", [])) * 2 * f["B"] * f["B"]  # (B x B cells of `step` m a block)
    from track_styles import ground_area
    n = 0
    for a in D.get("areas", []):
        if ground_area(a) and len(a["r"]) >= 3:
            n += len(a["r"]) - 2 + sum(len(h) for h in a.get("h", []))
    out["survey (outline triangulation, about)"] = n
    return out


# ---------------------------------------------------------------- the file
def zigzag(v):
    v = np.asarray(v, np.int64)
    return ((v << 1) ^ (v >> 63)).astype(np.uint64)


def varints(u):
    """Unsigned integers as LEB128 bytes."""
    u = np.asarray(u, np.uint64)
    out = bytearray()
    for v in u.tolist():
        while v >= 0x80:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        out.append(v)
    return bytes(out)


def read_varints(buf, n, off=0):
    out = np.empty(n, np.uint64)
    for i in range(n):
        v, sh = 0, 0
        while True:
            b = buf[off]
            off += 1
            v |= (b & 0x7F) << sh
            if b < 0x80:
                break
            sh += 7
        out[i] = v
    return out, off


def unzigzag(u):
    u = np.asarray(u, np.uint64)
    return ((u >> np.uint64(1)).astype(np.int64)) ^ -((u & np.uint64(1)).astype(np.int64))


def encode(V, F, cls, box):
    """(bytes, layout): vertices sorted by row (y down, in metres) then x, as differences of x, y, z in mm from the box's
    north-west corner and its base; per class its triangles, each the first index's difference to the previous one's
    and the other two as differences to it."""
    x0, y1 = round(box.bounds[0] * Q), round(box.bounds[3] * Q)
    base = int(V[:, 2].min())
    rel = np.stack([V[:, 0] - x0, y1 - V[:, 1], V[:, 2] - base], 1)
    order = np.lexsort((rel[:, 0], rel[:, 1] // Q))
    rank = np.empty(len(order), np.int64)
    rank[order] = np.arange(len(order))
    R = rel[order]
    d = np.diff(np.vstack([[0, 0, 0], R]), axis=0)
    parts = [varints(zigzag(d.ravel()))]
    layout = {"unit": 1 / Q, "x0": x0 / Q, "y1": y1 / Q, "base": base / Q, "vertices": int(len(V)), "classes": {}}
    for c, i in CLASS_IDS.items():
        t = rank[F[cls == i]]
        t = t[np.argsort(t[:, 0], kind="stable")]
        first = t[:, 0]
        dd = np.column_stack([np.diff(np.concatenate([[0], first])), t[:, 1] - first, t[:, 2] - first])
        parts.append(varints(zigzag(dd.ravel())))
        layout["classes"][c] = int(len(t))
    blob = b"".join(parts)
    layout["sections"] = [len(p) for p in parts]
    return blob, layout


def decode(blob, layout):
    """(V (n, 3) float m, {class: (m, 3) indexes})."""
    n = layout["vertices"]
    u, off = read_varints(blob, 3 * n)
    R = np.cumsum(unzigzag(u).reshape(n, 3), axis=0)
    q = layout["unit"]
    V = np.column_stack([layout["x0"] + R[:, 0] * q, layout["y1"] - R[:, 1] * q, layout["base"] + R[:, 2] * q])
    out = {}
    for c, m in layout["classes"].items():
        u, off = read_varints(blob, 3 * m, off)
        d = unzigzag(u).reshape(m, 3)
        first = np.cumsum(d[:, 0])
        out[c] = np.column_stack([first, first + d[:, 1], first + d[:, 2]])
    return V, out


def write(ln, built, rep):
    import sources
    from atomic import replacing
    blob, layout = encode(built["V"], built["F"], built["cls"], built["box"])
    layout["provenance"] = sources.stamp("ground_mesh.py", {
        "ground": sources.single("terrain", "ipr-dtm", int(len(built["F"])), "triangles: the city mesh (IPR), the survey, "
                                 "the beds, the building plots, welded")})
    layout["attribution"] = sources.attribution(layout["provenance"])
    p = os.path.join(ROOT, "data", f"line{ln}.ground.bin")
    with replacing(p, "wb") as fh:
        fh.write(blob)
    with replacing(os.path.join(ROOT, "data", f"line{ln}.ground.json"), "w", encoding="utf-8") as fh:
        json.dump(layout, fh, separators=(",", ":"), ensure_ascii=False)
    size = {"raw MB": round(len(blob) / 1e6, 2), "gzip MB": round(len(gzip.compress(blob, 9)) / 1e6, 2)}
    try:
        import brotli
        size["brotli MB"] = round(len(brotli.compress(blob, quality=11)) / 1e6, 2)
    except ImportError:
        pass
    V, by = decode(blob, layout)
    size["round trip"] = bool(len(V) == len(built["V"]) and sum(len(v) for v in by.values()) == len(built["F"]))
    rep["file"] = size


# ---------------------------------------------------------------- the error against the raster
def raster_error(built, ln):
    """The mesh against IPR's 1 m raster at every LATTICE-th cell in the box, by distance from DI's tracks: mean and
    p99 of |error| (cm), all the ground and the terrain class alone."""
    import di_network
    from geo import Frame
    from ipr_dtm import IprDtm
    from scipy.spatial import cKDTree
    V, F, cls, box = built["V"], built["F"], built["cls"], built["box"]
    x0, y0, x1, y1 = box.bounds
    gx, gy = np.meshgrid(np.arange(math.ceil(x0) + 0.5, x1, LATTICE), np.arange(math.ceil(y0) + 0.5, y1, LATTICE))
    px, py = gx.ravel(), gy.ravel()
    F_ = Frame()
    zi = np.asarray(IprDtm().sample(px + F_.E0, py + F_.N0), float)
    zm = mesh_at(V, F, px, py)
    zt = mesh_at(V, F[cls == CLASS_IDS["terrain"]], px, py)
    net = di_network.load_network()
    segs = []
    for e in net.edges.values():
        c = np.asarray(e["line"].coords)[:, :2]
        for a, b in zip(c, c[1:]):
            n = max(1, int(math.hypot(*(b - a)) / 1.0))
            segs.append(a + (b - a) * np.linspace(0, 1, n + 1)[:, None])
    d, _ = cKDTree(np.vstack(segs)).query(np.column_stack([px, py]), distance_upper_bound=5000)
    out = {}
    for name, zz in (("all ground", zm), ("terrain class", zt)):
        e = np.abs(zz - zi) * 100
        ok = np.isfinite(e)
        out[name] = {}
        for a, b in BANDS:
            m = ok & (d >= a) & (d < b)
            out[name][f"{a}-{b if b < math.inf else ''} m"] = (
                {"cells": int(m.sum()), "mean cm": round(float(e[m].mean()), 2), "p99 cm": round(float(np.percentile(e[m], 99)), 1)}
                if m.any() else None)
    out["lattice m"] = LATTICE
    out["fallback levels"] = "IPR on every cell the box's city mesh holds (the city mesh's report: DMR 5G and the 10 m grid fill none)"
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line")
    ap.add_argument("--lines")
    ap.add_argument("--mesh")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    lines = a.lines.split(",") if a.lines else [a.line]
    rep_dir = os.path.join(ROOT, "reports", "ground-mesh")
    os.makedirs(rep_dir, exist_ok=True)
    from baseline_store import HeavyJob
    with HeavyJob("ground_mesh"):
        for ln in lines:
            built = build(ln, a.mesh, a.threads)
            rep = built["rep"]
            t1 = time.time()
            rep["error"] = raster_error(built, ln)
            rep["seconds"]["error"] = round(time.time() - t1, 1)
            if not a.no_write:
                write(ln, built, rep)
            with open(os.path.join(rep_dir, f"line{ln}.json"), "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=1, ensure_ascii=False)
            print(json.dumps({k: v for k, v in rep.items() if k != "partition"}, indent=1, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
