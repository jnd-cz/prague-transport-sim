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
2. **Triangles.** Each face by shapely's constrained Delaunay (its edges kept: kerbs, bed edges, footprints, rails),
   every triangle wound counter-clockwise seen from above and every step's wall facing down the step (face_up()).
3. **Heights.** Each face's vertices by its class:
   - inside the beds' outline (but a raised area: a platform, a sidewalk, an island): the bed surface, the lowest bed
     there (bed_surface.Beds.surface: the rails at top of rail - lift -+ the cant's tilt, as the page lays the bed);
   - survey: the generated street surface (data/lineN.streets.*, #512) on roads, tram areas and sidewalks; elsewhere
     the survey area's own surface (its outline's heights, triangulated);
   - plot: the city mesh's (#632);
   - water (OSM's, and the survey's in it; the file's terrain class drawn as water): the level its banks give past its
     weirs (ground_partition.WaterLevels, #632), its faces cut to WATER_LATTICE;
   - terrain: the city mesh triangle's plane.
4. **The weld.** At a vertex the faces share, one height by priority, not averaged: the bed, then the survey (by rank),
   then the water, then the terrain. A face keeps its own height (a step: two vertices at one point) where it differs
   from the weld's by more than STEP for its pair: a kerb (a raised area beside a street or a bed), a building plot, a
   wall between the survey and the terrain, the water below a quay or a bed and at a weir; the terrain comes down to the
   water. Every step's edge gets its vertical faces, so every edge is used by two triangles.
5. **The file.** data/lineN.ground.bin: vertices in mm (x, y from the box's corner, z over its base) along a Hilbert
   curve, as zigzag varint differences; per class, its triangles' indexes as differences (encode()). lineN.ground.json: the
   layout, the counts, the provenance. Decoded by decode() (and by the page, #509).
6. **The network.** data/lineN.network.json (tools/network.py, #658): it reads the survey from this file, so it is built
   again after it, every time.

The report (reports/ground-mesh/lineN.json): triangles per class against what the page draws today, the error against
IPR's 1 m raster by distance band, the fallback levels, the steps by pair, the file's size raw, gzip and brotli, the
rails' check (the mesh under each rail within RAIL_TOL of the bed's row), the edge check, the build time.
"""
import collections
import gzip
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely
import shapely.ops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from geo import TILE, on_grid, tile_box, tile_index, tile_name  # noqa: E402 (the squares the faces are built in: the world's tiles, #30)
Q = 1000  # vertices per m: positions and heights in mm
CLASS_IDS = {"terrain": 0, "survey": 1, "bed": 2, "plot": 3, "wall": 4}
RAISED = {"sidewalk", "island", "median", "platform"}  # (src/world.js RAISED: they keep their height over a bed)
from kerbs import LOWERS as LOWERED  # noqa: E402 (the raised classes a lowered kerb is in: platforms keep their step)
CARRIAGEWAY = {"road", "tram", "parking"}  # (the classes a lowered kerb stands over: tools/bench/surfaces.js ROAD)
STREETS_ROAD, STREETS_WALK = {"road", "tram"}, {"sidewalk"}  # (the classes the generated street surface covers, #512)
# m: a face's height differing from the weld's by more than this at a shared vertex stays a step (to measure: the
# report counts every pair's differences)
# (a step's pairs: the water stands level, a wall up to what stands over it (a quay's survey, a bed: "water") and down
# at a weir ("weir"); the terrain or a plot round it comes down to it ("bank"), #632)
STEP = {"kerb": 0.03, "plot": 0.01, "wall": 0.5, "weir": 0.01, "water": 0.01, "bank": math.inf}
BORDER_NEAR = 0.002  # m: vertices this near a square's border are put onto it in both squares (tile_faces)
CROSS_EXT = 0.3  # m: a row's line across the bed reaches this far past its edges, to the beds' outline
BED_REACH = 0.5  # m: a corner in the beds' outline this far past a row's edge takes the edge's height (bed_surface)
PLACE_NEAR = 10.0  # m: the rail points around a named place (heads_check)
BORDER_TOL = 0.002  # m: an edge this near the border of the line's ground lies on it (edge_check; the grid's 0.71 mm)
RAIL_CLEAR = 0.05  # m: a rail's head either side of its line (src/world.js draws it 0.1 m wide): no kerb or plot within it
SURVEY_LATTICE = 5.0  # m: a street's or a lidar ground's faces cut to this inside (main's DtmSurface split to 5 m)
WATER_LEVEL = 0.1  # a survey water area's level outside OSM's water: this quantile of its outline's heights
WATER_LATTICE = 25.0  # m: the water's faces cut to this (the page's lookup bins triangles in 16 m cells by their box; it
# divides TILE, so its lines meet a tile's border)
WATER_PRIO = 2.95  # the water's weld priority: under the survey's (2.x) and the beds' (1), over the terrain's (3)
YIELD = 0.001  # at a corner shared with a survey area of its rank on its own outline, one that is not yields: laid on the
# lidar (`g`), or survey water at OSM's level (under the ranks' 0.01). The surveyed edge holds, as alpha-4 drew both from
# their outlines: 98% of line 9's and line 37's corners whose equal-rank heights parted by over 20 cm were a paved area on
# the lidar beside one on its outline, p50 0.5 m; the water keeps its level and a wall stands up to the quay (STEP's
# "water"): line 17's Vltava edge took the middle of the two, 187.33 m between 184.68 and 189.97, #664
TIE_STEP = 0.1  # m: equal-rank survey corners more than this off the middle of their range are a step (weld)
LIDAR_APART = 0.5  # m: a lidar corner that yielded keeps the lidar's height, a step, where its area's own outline stands
# more than this off the surveyed edge it yielded to (as STEP's wall). Line 37's 4,438 such corners: own outline within
# 2 cm of the edge at 2,848 (one edge surveyed twice), over 0.5 m at 394 (two levels: (4430, 1469) 199.65 against 205.43)
WATER_NUDGE = 3.0  # m: a water corner on a cut is seen from this far off it, on its triangle's side (off_cuts: past the
# cut's cells on WaterLevels' raster; seen from inside a triangle 2 m along it, it lay in them and read both sides)
BRIDGE_NEAR = 12.0  # m: around a bridge's track the survey keeps its own level (src/groundDraw.js flushDtm's 12 m)
LAYERS = ("draw", "area")  # the file's names per triangle, in this order after the triangles (encode)
SLIVER_BAND = 1e-6  # m²: a band piece smaller is float noise along a piece's edge
RAIL_NEAR = 0.0008  # m: the bed corner a rail point reads (snap-rounding to the mm grid moves a vertex by up to 0.71 mm;
# where two tracks' rails lie within a mm or two, at a join or a switch, the nearer track's corner is another rail)
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


def off_cuts(px, py, tx, ty, cuts, step=None):
    """Where points on the cuts (weirs, dams, lock gates) are seen from: `step` m (WATER_NUDGE) off the cut's segment
    nearest each, square to it, on the side of (tx, ty) (the point's triangle's centre)."""
    step = WATER_NUDGE if step is None else step
    S = []
    for part in shapely.get_parts(cuts):
        if part.geom_type == "LineString":
            c = shapely.get_coordinates(part)
            S += list(zip(c[:-1], c[1:]))
    if not S:
        return px, py
    S = np.asarray(S, float)
    qi, j = shapely.STRtree(shapely.linestrings(S)).query_nearest(shapely.points(px, py), all_matches=False)
    seg = np.empty(len(px), int)
    seg[qi] = j
    t = S[seg, 1] - S[seg, 0]
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-12)[:, None]
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    s = np.sign((np.column_stack([tx - px, ty - py]) * nrm).sum(1))
    s[s == 0] = 1.0
    return px + s * nrm[:, 0] * step, py + s * nrm[:, 1] * step


def lowered_kerbs(D):
    """tools/kerbs.py's lowered stretches (#303) in the survey's provenance: ((n, 3) x, y, height over the road; the
    stretch's width; its ramps' grade). A stretch at a kerb=raised node (no height) is none."""
    k = ((((D.get("provenance") or {}).get("lists") or {}).get("areas") or {}).get("checks") or {}).get("kerbs") or {}
    lo = k.get("lowered") or {}
    rule = lo.get("rule") or {}
    st = [(s["x"], s["y"], s["h"]) for s in lo.get("stretches") or [] if s.get("h") is not None and s.get("c") in LOWERED]
    return np.array(st, float).reshape(-1, 3), float(rule.get("width", 4.0)), float(rule.get("ramp", 0.125))


def lowered_heights(px, py, z, zroad, low, width, ramp):
    """Kerb corners' heights at the lowered stretches `low` ((n, 3): x, y, height over the road): within width / 2 of a
    stretch the road's plus its height, rising at `ramp` along the kerb back to the plain kerb (z, as it was), the
    lowest a stretch gives (tools/kerbs.py lowered_stretches' rule)."""
    from scipy.spatial import cKDTree
    out = np.asarray(z, float).copy()
    if not len(low) or not len(px):
        return out
    reach = width / 2 + 0.5 / ramp  # (no kerb rises 0.5 m)
    tree = cKDTree(low[:, :2])
    for i, near in enumerate(tree.query_ball_point(np.column_stack([px, py]), reach)):
        for k in near:
            d = math.hypot(px[i] - low[k, 0], py[i] - low[k, 1])
            out[i] = min(out[i], zroad[i] + low[k, 2] + max(0.0, d - width / 2) * ramp)
    return out


def lattice(g, step=None):
    """Lines every `step` m (SURVEY_LATTICE) in x and in y on the tiles' grid (S-JTSK, geo.on_grid), inside g (None when
    none crosses it)."""
    step = step or SURVEY_LATTICE
    x0, y0, x1, y1 = g.bounds
    xs = np.arange(on_grid(x0, step, 0), x1, step)
    ys = np.arange(on_grid(y0, step, 1), y1, step)
    segs = [((x, y0 - 1), (x, y1 + 1)) for x in xs.tolist()] + [((x0 - 1, y), (x1 + 1, y)) for y in ys.tolist()]
    if not segs:
        return None
    return shapely.intersection(shapely.MultiLineString(segs), g)


def city_at(G, px, py):
    """The city mesh's height at points under the classes above the terrain (ground_partition's "under" triangles):
    its triangle's plane, NaN where none holds a point."""
    out = np.full(len(px), np.nan)
    U = np.asarray(G["under"], int)
    if not len(px) or not len(U):
        return out
    x, y, z, T = G["x"], G["y"], G["z"], G["T"][U]
    tri = np.stack([np.column_stack([x[T[:, k]], y[T[:, k]], z[T[:, k]]]) for k in range(3)], 1)
    tree = shapely.STRtree(shapely.polygons(tri[:, [0, 1, 2, 0], :2]))
    pi, ti = tree.query(shapely.points(px, py), predicate="intersects")
    out[pi] = plane(tri[ti], px[pi], py[pi])
    return out


OWN_PLANE = ("paved", "parking", "median", "cycle")  # (survey classes on their outline's plane: own_heights, #638)
# m: an area whose outline lies within this of IPR's ground (its ring's median |difference|) is on the ground and laid on
# the lidar inside. Calibrated on the five lines (median |outline - IPR| per area): medians 100 % within it (76), cycle
# paths 98 % (48), parking 95 % (947); paved areas spread (11,030: p50 0.16 m, 32 % over it: yards over cellars, terraces)
OWN_GROUND = 0.3
OWN_ON = 0.01  # m: a corner this near its area's outline lies on it
# m: the street surface (street_profile) is taken where it lies this near the lidar; further it reached past its
# street, 0.8 m off on a slope (line 23 s 248), and stepped against the lidar beside it
OWN_STREET = 0.15


def own_ground(D, a, ipr=None):
    """Whether survey area `a` lies on the ground: its outline's median |height - IPR's| within OWN_GROUND."""
    from geo import Frame
    from ipr_dtm import IprDtm
    r = np.array([q[:3] for q in D["areas"][a]["r"] if q[2] is not None], float)
    if len(r) < 3:
        return False
    F = Frame()
    g = np.asarray((ipr or IprDtm()).sample(r[:, 0] + F.E0, r[:, 1] + F.N0), float)
    ok = np.isfinite(g)
    return bool(ok.sum() >= 3 and np.median(np.abs(r[ok, 2] - g[ok])) <= OWN_GROUND)


def own_heights(D, G, streets, sc, sa, x, y, zs, need, ipr=None):
    """The OWN_PLANE classes' corners but their surveyed points (a median's and a parking area's: off their outline;
    `need`: those the loop above gave their outline's plane), where the area lies on the ground (own_ground): the
    street surface where it reaches and lies within OWN_STREET of the lidar (a parking area the carriageway's, the
    others the sidewalks'), else the lidar (city_at), else the plane. An area off the ground keeps its plane whole.
    Returns (zs, per corner what gave it: "", "street", "lidar", "plane")."""
    from ipr_dtm import IprDtm
    src = np.full(len(zs), "", dtype=object)
    cand = np.flatnonzero(need & np.isin(sc, OWN_PLANE))
    if not len(cand):
        return zs, src
    from scipy.spatial import cKDTree
    ipr = ipr or IprDtm()
    zs = zs.copy()
    # (per area only which corners; the street and the city mesh are read once for all of them: city_at builds its
    # tree on each call, and per area it took the heights from 5 to 25 min a line)
    offs = []
    for a in np.unique(sa[cand]).tolist():
        k = cand[sa[cand] == a]
        segs = ring_segments(D["areas"][a])
        if not len(segs):
            continue
        if not own_ground(D, a, ipr):  # (a yard over a cellar, a terrace: the street's or the lidar's height on part
            src[k] = "plane"           # of it stepped inside it, 0.8 m on line 9 s 596)
            continue
        if D["areas"][a]["c"] in RAISED or D["areas"][a]["c"] == "parking":
            # (a median's outline is its kerb's top, a parking area's its kerb's foot: kept, only off it the street
            # or the lidar; on it they took the sidewalk's height and flattened 400 kerbs on the five lines)
            ring = shapely.MultiLineString([s_[:, :2] for s_ in segs])
            offs.append(k[shapely.distance(ring, shapely.points(x[k], y[k])) > OWN_ON])
        else:  # (elsewhere every corner but its surveyed points: its outline's long edges ran between far points too)
            d, _ = cKDTree(segs[:, 0, :2]).query(np.column_stack([x[k], y[k]]))
            offs.append(k[d > OWN_ON])
    off = np.concatenate(offs) if offs else np.zeros(0, int)
    if not len(off):
        return zs, src
    zl = city_at(G, x[off], y[off])
    zt = np.full(len(off), np.nan)
    park = sc[off] == "parking"
    if park.any():
        zt[park] = streets.at("road", x[off][park], y[off][park])
    if (~park).any():
        zt[~park] = streets.at("sidewalk", x[off][~park], y[off][~park])
    st = np.isfinite(zt) & ~(np.abs(zt - zl) > OWN_STREET)  # (no lidar there: the street's)
    # (neither further than OWN_GROUND from the outline's plane: on a slope steeper than its corners the lidar folded
    # at them, 0.4-0.6 m seams inside a yard on line 9 s 2140 and line 23 s 248, where the plane runs straight)
    pz = zs[off]
    st &= np.abs(zt - pz) <= OWN_GROUND
    zl = np.where(np.abs(zl - pz) <= OWN_GROUND, zl, np.nan)
    z = np.where(st, zt, zl)
    src[off] = np.where(st, "street", np.where(np.isfinite(zl), "lidar", "plane"))
    zs[off] = np.where(np.isfinite(z), z, zs[off])
    return zs, src


WALL_LATTICE = 1.0  # m: a survey wall's faces cut to this, their corners between its sides (across_outline, #653)
WALL_SNAP = 0.3  # m: a street corner on a wall's or stairs' outline this near its height there takes it (#653)
WALL_ON = 0.01  # m: a corner this near the outline lies on it (the faces are noded on it)
WALL_CLASSES = ("wall", "stairs")


def across_outline(ring_segs, x, y):
    """Heights of points inside a survey area between its sides: the outline's height at the nearest point on it, and at
    the nearest point on its other side (the direction from the point turned past 90 degrees), weighted by the other's
    distance. On the outline, its height. A battered wall's strip, 0.9 m across and 35 m long with 3 and 4 outline points
    along its foot and its top (line 37 (3915, 316), area 1444), triangulated on its outline alone folded into a W 2 m
    tall (#653); between its sides it runs straight across. ring_segs: (n, 2, 3) the outline's edges."""
    a, b = ring_segs[:, 0], ring_segs[:, 1]
    e = b[:, :2] - a[:, :2]
    l2 = np.maximum((e ** 2).sum(1), 1e-12)
    out = np.full(len(x), np.nan)
    for k in range(0, len(x), 2000):
        px, py = x[k:k + 2000, None], y[k:k + 2000, None]
        t = np.clip(((px - a[:, 0]) * e[:, 0] + (py - a[:, 1]) * e[:, 1]) / l2, 0, 1)
        qx, qy = a[:, 0] + e[:, 0] * t, a[:, 1] + e[:, 1] * t
        qz = a[:, 2] + (b[:, 2] - a[:, 2]) * t
        d = np.hypot(qx - px, qy - py)
        r = np.arange(len(px))
        j = d.argmin(1)
        d1, z1 = d[r, j], qz[r, j]
        ux, uy = qx[r, j] - px[:, 0], qy[r, j] - py[:, 0]
        back = (qx - px) * ux[:, None] + (qy - py) * uy[:, None] < 0
        d2m = np.where(back, d, np.inf)
        j2 = d2m.argmin(1)
        d2, z2 = d2m[r, j2], qz[r, j2]
        with np.errstate(invalid="ignore"):  # (no other side: inf, its own height taken)
            z = np.where(np.isfinite(d2) & (d1 > 1e-6), (z1 * d2 + z2 * d1) / np.maximum(d1 + d2, 1e-12), z1)
        out[k:k + 2000] = z
    return out


def ring_segments(a):
    """A survey area's outline edges with heights at both ends: (n, 2, 3)."""
    segs = []
    for r in [a["r"]] + a.get("h", []):
        for i in range(len(r)):
            p, q = r[i], r[(i + 1) % len(r)]
            if p[2] is not None and q[2] is not None and (p[0], p[1]) != (q[0], q[1]):
                segs.append([p[:3], q[:3]])
    return np.asarray(segs, float).reshape(-1, 2, 3)


def snap_to_walls(D, x, y, z, street):
    """Heights `z` of points (x, y) with each `street` one on a level-0 survey wall's or stairs' outline set to the
    outline's height there (along the edge it lies on, between its ends), the nearest within WALL_SNAP of its own. The
    street surface reads IPR, whose 1 m raster spreads a wall's face over 1-2 m; outranking the wall in the weld, it set
    the wall's top along Krejcárek's ramp (line 37 (3929, 331)) to its own heights, a fringe of 3 cm steps (#653). A wall
    holds its top and its foot at one place: of the two, the one within WALL_SNAP; past it is a level the street surface
    does not meet, and its step stays."""
    z = np.array(z, float)
    a, b = [], []
    for ar in D["areas"]:
        if ar["c"] not in WALL_CLASSES or ar.get("l", 0) != 0:
            continue
        for r in [ar["r"]] + ar.get("h", []):
            for i in range(len(r)):
                p, q = r[i], r[(i + 1) % len(r)]
                if p[2] is not None and q[2] is not None:
                    a.append(p[:3])
                    b.append(q[:3])
    s = np.flatnonzero(street & np.isfinite(z))
    if not a or not len(s):
        return z
    a, b = np.asarray(a, float), np.asarray(b, float)
    tree = shapely.STRtree(shapely.linestrings(np.stack([a[:, :2], b[:, :2]], 1)))
    pi, si = tree.query(shapely.points(x[s], y[s]), predicate="dwithin", distance=WALL_ON)
    if not len(pi):
        return z
    e = b[si, :2] - a[si, :2]
    t = np.clip(((x[s][pi] - a[si, 0]) * e[:, 0] + (y[s][pi] - a[si, 1]) * e[:, 1]) / np.maximum((e ** 2).sum(1), 1e-12), 0, 1)
    zw = a[si, 2] + (b[si, 2] - a[si, 2]) * t
    d = np.abs(zw - z[s][pi])
    o = np.lexsort((d, pi))  # (per point, its nearest height first)
    pi, zw, d = pi[o], zw[o], d[o]
    first = np.r_[True, pi[1:] != pi[:-1]]
    pi, zw, d = pi[first], zw[first], d[first]
    near = d <= WALL_SNAP
    z[s[pi[near]]] = zw[near]
    return z


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
    """The rails of every drawn track and its rows' lines across the bed (edge to edge, CROSS_EXT m past each edge), inside
    the beds' outline on the ground: the rails and the rows close cells as the page's bed quads do. (A rail alone would
    end inside the outline at a track's join or end, and polygonize drops what closes no face: on line 37, 6,307 rail
    points had no vertex within 1.25 m.)"""
    out = []
    for rows in beds.rows:
        if len(rows) < 2:
            continue
        for j in (1, 2):
            out.append(shapely.LineString([(x + nx * off[j], y + ny * off[j]) for x, y, nx, ny, off, _ in rows]))
        for x, y, nx, ny, off, _ in rows:
            a, b = off[0] - CROSS_EXT, off[3] + CROSS_EXT
            out.append(shapely.LineString([(x + nx * a, y + ny * a), (x + nx * off[1], y + ny * off[1]),
                                           (x + nx * off[2], y + ny * off[2]), (x + nx * b, y + ny * b)]))
    if not out:
        return []
    clipped = shapely.intersection(np.array(out, dtype=object), outline)
    return [g for g in shapely.get_parts(clipped) if g.geom_type == "LineString" and g.length > 1e-3]


def chunks(lines, most=64):
    """The lines as LineStrings of at most `most` vertices: a ring around a big piece (the beds' outline, a survey area)
    has a box as big as the piece, and every square's query found it."""
    out = []
    for g in shapely.get_parts(np.asarray(lines, dtype=object)):
        if g.geom_type == "Polygon":
            g = g.boundary
        for q in shapely.get_parts(g):
            c = shapely.get_coordinates(q)
            if len(c) < 2:
                continue
            for i in range(0, len(c) - 1, most - 1):
                out.append(shapely.LineString(c[i:i + most]))
    return np.asarray(out, dtype=object)


def tile_faces(rect, lines_tree, lines, kept_tree, kept_tris):
    """The faces of one square: its lines (and its border) noded and polygonized, those inside a terrain triangle kept
    whole left out (that triangle is the mesh there)."""
    R = shapely.box(*rect)
    idx = lines_tree.query(R, predicate="intersects")
    parts = [shapely.clip_by_rect(lines[i], *rect) for i in idx.tolist()]
    parts = [g for g in parts if not g.is_empty]
    # (the border with every point a line meets it at, and every vertex within BORDER_NEAR of it put onto it, from the
    # lines of both squares beside it: snap-rounding nodes a line ending a hair from the border onto it, in the square
    # it lies in only; both borders must hold the same points, or they differ: a T-junction)
    border = R.boundary
    near = lines_tree.query(R.buffer(BORDER_NEAR, join_style="mitre"), predicate="intersects")
    near = near[shapely.dwithin(lines[near], border, BORDER_NEAR)] if len(near) else near
    hits = np.zeros((0, 2))
    if len(near):
        cut = shapely.get_coordinates(shapely.intersection(border, lines[near]))
        v = shapely.get_coordinates(lines[near])
        close = v[shapely.dwithin(shapely.points(v), border, BORDER_NEAR)]
        onto = shapely.get_coordinates(shapely.line_interpolate_point(border, shapely.line_locate_point(border, shapely.points(close)))) if len(close) else np.zeros((0, 2))
        hits = np.vstack([cut.reshape(-1, 2), onto.reshape(-1, 2)])
    if len(hits):
        ring = shapely.get_coordinates(border)[:-1]
        t = np.concatenate([shapely.line_locate_point(border, shapely.points(ring)), shapely.line_locate_point(border, shapely.points(hits))])
        pts = np.vstack([ring, hits])
        t[:len(ring)][0] = 0.0
        o = np.argsort(t, kind="stable")
        pts = pts[o]
        keep = np.concatenate([[True], np.hypot(*np.diff(pts, axis=0).T) > 1e-9])
        border = shapely.LineString(np.vstack([pts[keep], pts[:1]]))
    # (noded on the mm grid, snap-rounded: every face's vertex on the grid the file keeps, so no two vertices a hair
    # apart make slivers that collapse to zero-area triangles when rounded, line 37 had three edges used four times)
    noded = shapely.union_all([border] + parts, grid_size=1 / Q) if parts else shapely.set_precision(border, 1 / Q)
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
def weld(cx, cy, zc, prio, kind, label=None, zown=None):
    """The corners' heights welded at each point: (each corner's height, the steps kept by pair, the points). A point takes
    its top-priority corners' height, whatever their order (#664: it took the first top corner's, the order of the
    partition's pieces; drawing the survey's walls reordered them and moved line 22's corner at (-1114, -537), shared by
    roads #16 and #23 by a bridge's track, 193.49 and 193.32 m, by 0.17 m):
    - top corners within 2 TIE_STEP of each other: the middle of their range;
    - the survey's top corners farther apart: a step the survey recorded, each corner takes the nearer end of the range;
    - a corner below the top keeps its own height where it differs by more than its pair's STEP (a kerb, a wall, the
      water); the pair is judged against the lowest top corner's kind;
    - a lidar corner (`label` "lidar") that yielded to its rank (YIELD) keeps its own where its area's outline there
      (`zown`) stands over LIDAR_APART off.
    `label`: what gave each corner its height (default `kind`), for the report and the lidar's rule."""
    key = np.round(cx * Q).astype(np.int64) * 10_000_000_000 + np.round(cy * Q).astype(np.int64)
    uk, inv = np.unique(key, return_inverse=True)
    top_p = np.full(len(uk), np.inf)
    np.minimum.at(top_p, inv, prio)
    is_top = prio == top_p[inv]
    tops = np.flatnonzero(is_top)
    lo, hi = np.full(len(uk), np.inf), np.full(len(uk), -np.inf)
    np.minimum.at(lo, inv[tops], zc[tops])
    np.maximum.at(hi, inv[tops], zc[tops])
    with np.errstate(invalid="ignore"):  # (a point whose top corners have no height: NaN, as before)
        top_z = np.where(np.isfinite(lo) & np.isfinite(hi), (lo + hi) / 2, np.nan)
    # (each point's lowest top corner, by height then kind: whatever the corners' order)
    o = tops[np.lexsort((kind[tops], zc[tops], inv[tops]))]
    first = np.full(len(uk), -1)
    first[inv[o[::-1]]] = o[::-1]
    top_kind = kind[first]
    # (a point whose top corners are all the survey's and part by more than 2 TIE_STEP is a step the survey recorded:
    # every corner there takes the nearer end of their range, the top ones their own, as alpha-4 drew each area from its
    # outline; line 37's parking areas #3121 and #3130 share (6459.6, 827.4) at 203.19 and 202.06 m)
    not_sv = np.zeros(len(uk), bool)
    not_sv[inv[tops[~np.isin(kind[tops], ("survey", "raised"))]]] = True
    split = ~not_sv & (hi - lo > 2 * TIE_STEP)
    target = top_z[inv]
    s = split[inv]
    target[s] = np.where(np.abs(zc[s] - lo[inv[s]]) <= np.abs(zc[s] - hi[inv[s]]), lo[inv[s]], hi[inv[s]])
    dz = zc - target
    pk, pt = kind == "pool", top_kind[inv] == "pool"
    pair = np.where(pk & pt, "weir", np.where(pk, "water", np.where(pt, "bank", np.where(kind == "plot", "plot",
                    np.where((kind == "raised") != (top_kind[inv] == "raised"), "kerb",
                             np.where((kind == "terrain") != (top_kind[inv] == "terrain"), "wall", ""))))))
    lim = np.array([STEP.get(p, np.inf) for p in pair]) if len(pair) else np.zeros(0)
    # (a weir's two sides share the water's priority: both are top, each keeps its own level more than STEP off the
    # middle; welded to the first's, the second's triangles sloped 1.5 m up to the weir at Šítkovský)
    step = (~is_top | (pair == "weir")) & (np.abs(dz) > lim)
    # (a corner on the lidar that yielded to a surveyed one of its rank keeps the lidar's height where its own outline
    # stands more than LIDAR_APART off that one's: two levels, not one edge)
    rank = np.round(prio, 2) == np.round(top_p[inv], 2)
    label = kind if label is None else label
    apart = np.zeros(len(zc), bool)
    if zown is not None:
        with np.errstate(invalid="ignore"):
            apart = (label == "lidar") & ~is_top & rank & (np.abs(zown - target) > LIDAR_APART)
    step |= apart
    zf = np.where(step, zc, target)
    steps = {p: {"corners": int((step & (pair == p)).sum()),
                 "|dz| at shared corners, p50 / p90 / p99 / max m": [round(float(np.percentile(np.abs(dz[(pair == p) & ~is_top]), q)), 3)
                                                                     for q in (50, 90, 99, 100)] if ((pair == p) & ~is_top).any() else None}
             for p in STEP}
    # (the points whose top corners differ, by the pair of what gave their heights: the middle up to 2 TIE_STEP, a step
    # over it)
    names, code = np.unique(label.astype(str), return_inverse=True)
    c_lo, c_hi = np.full(len(uk), len(names)), np.full(len(uk), -1)
    np.minimum.at(c_lo, inv[tops], code[tops])
    np.maximum.at(c_hi, inv[tops], code[tops])
    rng = hi - lo
    ties = {}
    for c in (1, 5, 20):
        w = np.flatnonzero(rng > c / 100)
        pairs = collections.Counter(str(names[a]) if a == b else f"{names[a]}/{names[b]}" for a, b in zip(c_lo[w], c_hi[w]))
        ties[f"over {c} cm"] = dict(sorted(pairs.items()))
    ties["max m"] = round(float(np.nanmax(rng[np.isfinite(rng)])), 3) if np.isfinite(rng).any() else 0.0
    ties["survey steps"] = int(split.sum())
    ties["lidar apart"] = int(apart.sum())
    # (the corners that yielded to one of their rank, YIELD: by how far each moved, a step kept for the water and where
    # apart)
    for lb in ("lidar", "pool"):
        gone = (label == lb) & ~is_top & rank & np.isfinite(dz)
        ties[f"{lb} corners yielded"] = {f"over {c} cm": int((np.abs(dz[gone]) > c / 100).sum()) for c in (1, 5, 20)}
    steps["ties"] = ties
    return zf, steps, len(uk)


def build(ln, mesh=None, threads=8, log=print):
    import bed_surface
    import ground_partition as gp
    from city_terrain import peak_gb
    log0 = log

    def log(msg):  # (each step with the peak memory so far: lines 22 and 17 hold 9 M terrain triangles, 21 GB)
        log0(f"{msg} (peak {peak_gb():.1f} GB)")
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
    log(f"  beds: {sum(len(r) for r in beds.rows)} rows, {len(rails)} rail and row pieces on the ground, {time.time() - t1:.0f} s")
    t1 = time.time()
    bx0, by0, bx1, by1 = box.bounds

    # the lines that make the faces, and what each face can be
    tri_xy = np.stack([np.column_stack([x[T[:, k]], y[T[:, k]]]) for k in range(3)], 1)
    kept = np.asarray(G["kept"], int)
    tb = np.stack([tri_xy[kept, :, 0].min(1), tri_xy[kept, :, 1].min(1), tri_xy[kept, :, 0].max(1), tri_xy[kept, :, 1].max(1)], 1)
    ti, tj = tile_index(tb[:, [0, 2]], tb[:, [1, 3]])
    whole = (ti[:, 0] == ti[:, 1]) & (tj[:, 0] == tj[:, 1])  # (inside one square: no square's border crosses it)
    lines, owners = [], []  # (owners: what the face inside a line's polygon is: (class, id))
    for k, q in enumerate(pieces["survey"]):
        lines.append(q["g"].boundary)
        owners.append(("survey", k, q["g"]))
        # (a street or a ground on the lidar has a surface between its outline's points: lattice lines inside it, so its
        # faces are cut to SURVEY_LATTICE m and their corners lie on that surface, #632)
        if q["c"] in STREETS_ROAD | STREETS_WALK or (D.get("areas") or [{}] * (q["area"] + 1))[q["area"]].get("g"):
            g = lattice(q["g"])
            if g is not None and not g.is_empty:
                lines.append(g)
        elif q["c"] == "water":
            g = lattice(q["g"], WATER_LATTICE)
            if g is not None and not g.is_empty:
                lines.append(g)
        elif q["c"] == "wall":  # (a wall's face, its corners between its two sides: across_outline, #653)
            g = lattice(q["g"], WALL_LATTICE)
            if g is not None and not g.is_empty:
                lines.append(g)
    for k, q in enumerate(pieces["bed"]):
        lines.append(q["g"].boundary)
        owners.append(("bed", k, q["g"]))
    for k, q in enumerate(pieces["plot"]):
        lines.append(q["g"].boundary)
        owners.append(("plot", k, q["g"]))
    # (OSM's water, level between lattice lines: its faces' corners on the level its banks give, WaterLevels; and its
    # weirs, dams and lock gates across it and the survey's water: the level steps there, #632)
    for k, q in enumerate(pieces["water"]):
        lines.append(q["g"].boundary)
        owners.append(("water", k, q["g"]))
        g = lattice(q["g"], WATER_LATTICE)
        if g is not None and not g.is_empty:
            lines.append(g)
    wet = G["water"].intersection(box) if not G["water"].is_empty else shapely.Polygon()
    cuts = shapely.intersection(shapely.union_all(G["cuts"]), wet) if G["cuts"] and not wet.is_empty else None
    if cuts is not None and not cuts.is_empty:
        lines.append(cuts)
    for parent, g in G["remains"]:
        lines.append(g.boundary)
        owners.append(("terrain", int(parent), g))
    for t in kept[~whole].tolist():
        g = shapely.Polygon(tri_xy[t])
        lines.append(g.boundary)
        owners.append(("terrain", t, g))
    if not outline.is_empty:
        lines.append(outline.boundary)
    # (the line's border too: where it passes within cm of a terrain triangle's corner, the partition drops that cut
    # triangle's remains as a sliver, and only the border closes the face there; lines 23, 9, 22, 17 had 6-52 open edges)
    lines.append(box.boundary)
    lines += rails
    # (a raised area beside a track or a plot that reaches a rail: within RAIL_CLEAR of it at the bed's height, its kerb
    # or wall RAIL_CLEAR past the rail; its edge in the lines. The user, 2026-11-16: "any structure crossing the track
    # should be at most level with the rail head", data/truth.json groundRules)
    across = crossing_pieces(pieces["survey"], beds)
    band = rail_band(beds, outline, [q["g"] for k, q in enumerate(pieces["survey"]) if q["c"] in RAISED and not across[k]] +
                     [q["g"] for q in pieces["plot"]])
    if not band.is_empty:
        lines.append(band.boundary)
    lines = chunks(lines)
    lines_tree = shapely.STRtree(lines)
    # (a whole triangle that a line touches, within float noise, is noded with the lines: a piece's vertex on its edge
    # would be a T-junction, line 37 had one)
    cand = kept[whole]
    polys = shapely.polygons(np.concatenate([tri_xy[cand], tri_xy[cand][:, :1]], 1))
    touch = np.zeros(len(cand), bool)
    ti_, _ = lines_tree.query(polys, predicate="dwithin", distance=1e-6)
    touch[ti_] = True
    kept_whole = cand[~touch]
    more = []  # (one concatenation: an append per triangle copies the whole array each time)
    for t in cand[touch].tolist():
        g = shapely.Polygon(tri_xy[t])
        more.append(g.boundary)
        owners.append(("terrain", t, g))
    lines = np.concatenate([lines, np.array(more, dtype=object)]) if more else lines
    lines_tree = shapely.STRtree(lines)
    own_geoms = np.asarray([o[2] for o in owners], dtype=object)
    own_tree = shapely.STRtree(own_geoms)
    kept_polys = shapely.polygons(np.concatenate([tri_xy[kept_whole], tri_xy[kept_whole][:, :1]], 1)) if len(kept_whole) else None
    kept_tree = shapely.STRtree(kept_polys) if kept_polys is not None else None

    log(f"  {len(lines):,} lines, {int(touch.sum()):,} whole triangles noded with them, {time.time() - t1:.0f} s")
    (e0, e1), (n0, n1) = tile_index([bx0, bx1], [by0, by1])
    rects = [(max(bx0, b[0]), max(by0, b[1]), min(bx1, b[2]), min(by1, b[3]))
             for b in (tile_box(e, n) for e in range(int(e0), int(e1) + 1) for n in range(int(n0), int(n1) + 1))]
    t1 = time.time()
    with ThreadPoolExecutor(threads) as ex:
        faces = list(ex.map(lambda r: tile_faces(r, lines_tree, lines, kept_tree, kept_polys), rects))
    faces = np.concatenate([f for f in faces if len(f)]) if any(len(f) for f in faces) else np.zeros(0, object)
    log(f"  {len(faces):,} faces in {len(rects)} squares, {time.time() - t1:.0f} s")

    # each face's owner: the piece holding its inner point (the smallest, where a remains polygon lies on its triangle)
    t1 = time.time()
    inner = shapely.point_on_surface(faces)
    # (a square reaching past the line's ground, ground_partition.line_area: its faces there are no one's)
    shapely.prepare(box)
    keep = shapely.contains_xy(box, *shapely.get_coordinates(inner).T)
    faces, inner = faces[keep], inner[keep]
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
    shapely.prepare(band)
    in_band = shapely.contains_xy(band, *shapely.get_coordinates(inner).T) if not band.is_empty else np.zeros(len(faces), bool)
    log(f"  owners: {n_lost} faces in no piece ({a_lost:.3f} m²) took the nearest's, {time.time() - t1:.0f} s")
    faces, owner, in_bed, in_band = faces[~lost], owner[~lost], in_bed[~lost], in_band[~lost]

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
    # the water: its level at each corner, a corner on a cut seen from inside its own triangle (the level steps there)
    from geo import Frame
    from ipr_dtm import IprDtm
    levels = gp.WaterLevels(G["water"], G["cuts"], IprDtm(), Frame(), extent=box.buffer(gp.WATER_REACH)) if not wet.is_empty else None

    def water_level(ci):
        out = np.full(len(ci), np.nan)
        if levels is None or not len(ci):
            return out
        vx, vy = cx[ci].copy(), cy[ci].copy()
        if cuts is not None and not cuts.is_empty:
            on = shapely.dwithin(shapely.points(vx, vy), cuts, 1e-3)
            if on.any():
                cen = fc[ci[on] // 3].mean(1)
                vx[on], vy[on] = off_cuts(vx[on], vy[on], cen[:, 0], cen[:, 1], cuts)
        key = np.round(vx * Q).astype(np.int64) * 10_000_000_000 + np.round(vy * Q).astype(np.int64)
        uk_, first_, back = np.unique(key, return_index=True, return_inverse=True)
        return levels.at(vx[first_], vy[first_])[back]
    m = np.flatnonzero(corner_cls == "water")
    zc[m], prio[m], kind[m] = water_level(m), WATER_PRIO, "pool"
    # plots: the ground under a building's footprint, the city mesh's (a flat pad at the median ground round it stood on walls
    # up to 2 m on a slope, a grey slab where no building of the 3D city model stands on the footprint: a shed, a garden hut;
    # the model's buildings carry their own walls down to their own base, #632); the pad's height where the mesh has none
    m = corner_cls == "plot"
    zp = np.array([pieces["plot"][owners[o][1]]["z"] for o in owner[corner_face[m]]], float)
    zg = city_at(G, cx[m], cy[m])
    zc[m] = np.where(np.isfinite(zg), zg, zp)
    prio[m], kind[m] = 4.0, "plot"
    # survey
    m = np.flatnonzero(corner_cls == "survey")
    sv = [pieces["survey"][owners[o][1]] for o in owner[corner_face[m]]]
    sc = np.array([q["c"] for q in sv])
    sa = np.array([q["area"] for q in sv])
    zs = np.full(len(m), np.nan)
    # (on a bridge, within BRIDGE_NEAR of the route's span or of a bridge's track, the street below keeps the survey's own
    # level, as the page's flushDtm left it (profile.onBridge: the route's spans, src/terrain.js Profile.bridges): the
    # street surface follows the tracks onto the deck, and a level-0 tram area running up a ramp onto a viaduct stood at
    # its deck, line 37 s 3464-3484, area 2091; that viaduct's tracks carry no `b`)
    route = shapely.LineString([p[:2] for p in L["path"]])
    spans = [shapely.ops.substring(route, a, b) for a, b in L.get("spans") or L.get("bridges") or []]
    spans += [shapely.LineString([p[:2] for p in t["p"]]) for t in L.get("tracks") or [] if t.get("b") and len(t.get("p") or []) > 1]
    on_span = np.zeros(len(m), bool)
    if spans:
        deck = shapely.union_all(shapely.buffer(np.asarray(spans, dtype=object), BRIDGE_NEAR, cap_style="flat"))
        shapely.prepare(deck)
        on_span = shapely.contains_xy(deck, cx[m], cy[m])
    for kd, cls in (("road", STREETS_ROAD), ("sidewalk", STREETS_WALK)):
        mm = np.isin(sc, list(cls)) & ~on_span
        if mm.any():
            zs[mm] = streets.at(kd, cx[m][mm], cy[m][mm])
    # (a lawn, a yard, a railway yard on the lidar ground (`g`, tools/zps_inside.py) has surveyed heights on its outline
    # only, and the page laid it on the lidar inside (src/terrain.js DtmSurface, #444): here the city mesh's, its outline
    # too, so it meets the terrain beside it. Its outline on a slope stood up to 5.5 m under the terrain, a wall, and a
    # hillside of them terraced: line 37 s 3472, area 2705)
    need = np.isnan(zs)
    on_lidar = need & np.array([bool(D["areas"][a].get("g")) for a in sa.tolist()], bool)
    if on_lidar.any():
        zs[on_lidar] = city_at(G, cx[m][on_lidar], cy[m][on_lidar])
    need = np.isnan(zs)
    for a in np.unique(sa[need]).tolist():
        mm = need & (sa == a)
        segs = ring_segments(D["areas"][a]) if D["areas"][a]["c"] == "wall" else None
        if segs is not None and len(segs):  # (a wall's face between its sides, #653)
            zs[mm] = across_outline(segs, cx[m][mm], cy[m][mm])
        else:
            zs[mm] = surface.at(a, cx[m][mm], cy[m][mm])
    # (a paved yard, a parking area or a cycle path but at its surveyed points, a median off its outline (on an edge a
    # higher area cut through its inside, another's lattice on it, a long edge of its outline): its outline's plane there
    # ran between far points: line 23 s 557 (-2564.4, 434.0), a yard 0.33 m under the sidewalk on their shared edge,
    # its nearest surveyed point 4 m off, a step with its wall. It meets its neighbours instead:
    # the street surface where it reaches, else the lidar where the area lies on the ground, else its outline, #638)
    zs, own_src = own_heights(D, G, streets, sc, sa, cx[m], cy[m], zs, need)
    # (a river or a pond is level: in OSM's water, at the level its banks give (WaterLevels, as OSM's water above: two of
    # line 17's survey water areas span a weir, Helmovský and Troja's, their own level 3.4-3.9 m under the water above it,
    # #632); elsewhere, as the page laid it (src/terrain.js DtmSurface), at its outline's WATER_LEVEL quantile: its
    # outline's heights are its banks' tops; triangulated between them it ran in steps along line 17's Vltava)
    wet = sc == "water"
    in_osm = np.zeros(len(m), bool)
    if wet.any() and levels is not None:
        shapely.prepare(G["water"])
        cen = fc[m[wet] // 3].mean(1)
        in_osm[np.flatnonzero(wet)] = shapely.contains_xy(G["water"], cen[:, 0], cen[:, 1])
        zs[in_osm] = water_level(m[in_osm])
    for a in np.unique(sa[wet & ~in_osm]).tolist():
        zr = [q[2] for q in D["areas"][a]["r"] if q[2] is not None]
        if zr:
            zs[wet & ~in_osm & (sa == a)] = sorted(zr)[int(len(zr) * WATER_LEVEL)]
    # (a lowered kerb at a crossing (tools/kerbs.py's stretches, #303): a raised area's corner on the kerb, shared with the
    # carriageway, stands the stretch's height over the road beside it, ramped back to the plain kerb along it. The
    # street surface is a smooth fit 1 m in from the kerbs and carries none: line 37's 352 sites stood 9 cm over the road
    # (median), 3 cm on main's layers, #630)
    low, low_w, low_ramp = lowered_kerbs(D)
    if len(low):
        road = np.isin(sc, list(CARRIAGEWAY)) & np.isfinite(zs)
        kr = np.round(cx[m][road] * Q).astype(np.int64) * 10_000_000_000 + np.round(cy[m][road] * Q).astype(np.int64)
        ko, zo = np.unique(kr, return_index=True)
        rz = zs[road][zo]
        up = np.flatnonzero(np.isin(sc, list(LOWERED)) & np.isfinite(zs))
        ku = np.round(cx[m][up] * Q).astype(np.int64) * 10_000_000_000 + np.round(cy[m][up] * Q).astype(np.int64)
        j = np.clip(np.searchsorted(ko, ku), 0, max(len(ko) - 1, 0))
        on = (ko[j] == ku) if len(ko) else np.zeros(len(up), bool)
        up, j = up[on], j[on]
        zs[up] = lowered_heights(cx[m][up], cy[m][up], zs[up], rz[j], low, low_w, low_ramp)
    # (a street corner shared with a survey wall or stairs takes its height within WALL_SNAP, #653)
    zs = snap_to_walls(D, cx[m], cy[m], zs, np.isin(sc, list(STREETS_ROAD | STREETS_WALK)) & ~on_span)
    zc[m] = zs
    prio[m] = 2.0 + np.array([(10 - RANK.get(c, 1)) / 100 for c in sc]) + np.where(on_lidar | in_osm, YIELD, 0.0)
    kind[m] = np.where(np.isin(sc, list(RAISED)), "raised", np.where(in_osm, "pool", "survey"))
    # (the weld's report: what gave a survey corner its height)
    sv_m = m
    sv_label = np.where(on_lidar, "lidar", np.where(np.isin(sc, list(STREETS_ROAD | STREETS_WALK)) & ~on_span, "street",
                                                    kind[m]))
    # (a lidar corner shared with a survey area off the lidar: its own outline's height there, for the weld's
    # LIDAR_APART)
    zown = np.full(len(cx), np.nan)
    if on_lidar.any():
        k = np.round(cx[m] * Q).astype(np.int64) * 10_000_000_000 + np.round(cy[m] * Q).astype(np.int64)
        shared = on_lidar & np.isin(k, k[~on_lidar])
        for a in np.unique(sa[shared]).tolist():
            mm = shared & (sa == a)
            zown[m[mm]] = surface.at(a, cx[m][mm], cy[m][mm])
    # (a raised area across a track, its axis in it, is a crossing: within the beds' outline it lies flush with the rails,
    # its kerb at the outline's edge. #512's sidewalk stood 8-21 cm over the rails at line 37's stops; the 11 raised
    # areas over line 37's rails all cross a track. One beside a track keeps its height, as on the page: world.js RAISED,
    # but not over a rail: within RAIL_CLEAR of one (the band) it lies at the bed's height, as a plot does there)
    c_across = np.zeros(len(cx), bool)
    c_across[m] = across[[owners[o][1] for o in owner[corner_face[m]]]] if len(m) else False
    c_band = np.repeat(in_band[tf], 3)
    # the beds' outline: the bed surface (not a raised area, unless it crosses the track); and a corner on a rail on the
    # ground whatever face holds it, at the rail's height, or the bed's under it where another bed lies lower (where two
    # tracks join, the beds' outline, sampled along `p`, and the drawn rows part by mm: 29-95 rail points a line were
    # 2-54 mm off)
    zr, zl = on_rails(cx, cy, beds, outline)
    on_rail = np.isfinite(zr)
    m = np.flatnonzero(((np.repeat(t_in_bed, 3) | on_rail) & ((kind != "raised") | c_across) & (corner_cls != "plot")) | c_band)
    zb = beds.surface_at(cx[m], cy[m], BED_REACH)
    zb = np.where(on_rail[m], np.where(zl[m] < zr[m] - RAIL_TOL, zl[m], zr[m]), zb)
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
    label = kind.copy()
    keep = kind[sv_m] != "bed"
    label[sv_m[keep]] = sv_label[keep]
    zf, steps, n_points = weld(cx, cy, zc, prio, kind, label, zown)
    # vertex ids: (x, y, z in mm)
    zq = np.round(zf * Q).astype(np.int64)
    vkey = np.stack([np.round(cx * Q).astype(np.int64), np.round(cy * Q).astype(np.int64), zq], 1)
    V, vid = np.unique(vkey, axis=0, return_inverse=True)
    F = vid.reshape(-1, 3)
    # (what the page draws each triangle as, #509: inside the beds' outline at the bed's height the bed, by its track
    # style, as the page draws its bed over the survey there; the survey by its area's class (src/groundDraw.js DTM_COLORS,
    # a median under grass green, #555); else the class)
    tcls = np.where((kind.reshape(-1, 3) == "bed").all(1) & (tcls != "plot"), "bed", tcls)
    draw = np.full(len(tcls), "", dtype=object)
    sv = np.flatnonzero(tcls == "survey")
    if len(sv):
        areas = D.get("areas") or []

        def colour(q):
            a = areas[q["area"]] if q["area"] < len(areas) else {}
            return "green" if q["c"] == "median" and a.get("s") == "green" else q["c"]
        draw[sv] = [colour(pieces["survey"][owners[o][1]]) for o in owner[tf[sv]].tolist()]
    bd = np.flatnonzero(tcls == "bed")
    if len(bd):
        cen = fc[bd].mean(1)
        draw[bd] = beds.style_at(cen[:, 0], cen[:, 1])
    tr = np.flatnonzero((tcls == "terrain") | (tcls == "plot"))  # (a plot is ground: drawn by its land cover, #632)
    if len(tr):
        cen = fc[tr].mean(1)
        draw[tr] = land_cover(L, cen[:, 0], cen[:, 1], G["water"])
    n_water = int((tcls == "water").sum())
    draw[tcls == "water"] = "water"
    tcls = np.where(tcls == "water", "terrain", tcls)  # (the file's terrain class, drawn as water)
    # (the survey's class under each triangle, a bed's on the survey too: what the page's lookup answers to traffic, kerbs,
    # stops and walkers, as the survey's own triangles did, #509; "" off the survey)
    area = np.full(len(tcls), "", dtype=object)
    sf = np.flatnonzero(fcls[tf] == "survey")
    if len(sf):
        area[sf] = [pieces["survey"][owners[o][1]]["c"] for o in owner[tf[sf]].tolist()]
    fcls_id = np.array([CLASS_IDS[c] for c in tcls])
    log(f"  weld: {n_points:,} points, {len(V):,} vertices, steps {[(p, s['corners']) for p, s in steps.items() if p != 'ties']}, ties over 1 cm {steps['ties']['over 1 cm']}, survey steps {steps['ties']['survey steps']}, yielded over 5 cm: lidar {steps['ties']['lidar corners yielded']['over 5 cm']}, pool {steps['ties']['pool corners yielded']['over 5 cm']}, "
        f"{time.time() - t1:.0f} s")

    # the kept terrain triangles, as they are
    KT = T[kept_whole]
    kv = np.stack([np.round(x * Q), np.round(y * Q), np.round(z * Q)], 1).astype(np.int64)
    used = np.unique(KT)
    allv = np.vstack([V, kv[used]])
    V2, inv2 = np.unique(allv, axis=0, return_inverse=True)
    F = inv2[:len(V)][F]
    remap = np.full(len(x), -1)
    remap[used] = inv2[len(V):]
    KF = remap[KT]
    F = np.vstack([F, KF])
    fcls_id = np.concatenate([fcls_id, np.zeros(len(KF), int)])
    draw = np.concatenate([draw, land_cover(L, x[KT].mean(1), y[KT].mean(1), G["water"]) if len(KT) else np.zeros(0, dtype=object)])
    area = np.concatenate([area, np.full(len(KF), "", dtype=object)])
    V = V2
    F = face_up(V, F)

    # the steps' walls: an edge whose two sides hold different vertices at an end; each drawn as the face above it
    t1 = time.time()
    walls, up = step_walls(V, F, above=True)
    names = {i: c for c, i in CLASS_IDS.items()}
    wall_draw = np.array([f"{names[int(fcls_id[u])]}:{draw[u]}" if draw[u] else names[int(fcls_id[u])] for u in up.tolist()],
                         dtype=object)
    F = np.vstack([F, walls]) if len(walls) else F
    fcls_id = np.concatenate([fcls_id, np.full(len(walls), CLASS_IDS["wall"])])
    draw = np.concatenate([draw, wall_draw]) if len(walls) else draw
    area = np.concatenate([area, np.full(len(walls), "", dtype=object)]) if len(walls) else area
    # (no degenerate triangles)
    good = (F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])
    F, fcls_id, draw, area = F[good], fcls_id[good], draw[good], area[good]
    log(f"  {len(walls):,} wall triangles, {time.time() - t1:.0f} s")

    rep = {"line": ln, "partition": {k: prep[k] for k in ("box", "box_km2", "classes", "cover", "terrain", "bed window") if k in prep},
           "faces": len(faces), "vertices": int(len(V)), "triangles": int(len(F)),
           "triangles per class": {c: int((fcls_id == i).sum()) for c, i in CLASS_IDS.items()},
           "water triangles (the terrain's, OSM's water)": n_water, "water": prep.get("water"),
           "steps": steps, "corners without a height (IPR's)": no_height, "seconds": {"partition": round(t_part, 1)},
           "corners but their surveyed points (own_heights)": {c: dict(collections.Counter(own_src[(sc == c) & (own_src != "")].tolist()))
                                                   for c in OWN_PLANE if ((sc == c) & (own_src != "")).any()}}
    t1 = time.time()
    rep["edges"] = edge_check(V, F, box)
    log(f"  edges checked, {time.time() - t1:.0f} s")
    t1 = time.time()
    rep["rails"] = rail_check(cx, cy, zf, kind, beds, outline)
    rep["rails"]["ground over the top of rail"] = heads_check(V, F, fcls_id, beds, outline, rail_places(ln, L))
    rep["rails"]["raised areas across a track (laid flush within the beds' outline)"] = int(across.sum())
    log(f"  rails checked, {time.time() - t1:.0f} s")
    rep["page today"] = page_counts(L, D)
    rep["seconds"]["mesh"] = round(time.time() - t0 - t_part, 1)
    rep["draw classes"] = {c: dict(zip(*np.unique(draw[fcls_id == i].astype(str), return_counts=True)))
                           for c, i in CLASS_IDS.items() if (fcls_id == i).any()}
    rep["draw classes"] = {c: {k or "-": int(v) for k, v in d.items()} for c, d in rep["draw classes"].items()}
    rep["survey classes"] = {c: {k or "-": int(v) for k, v in zip(*np.unique(area[fcls_id == i].astype(str), return_counts=True))}
                             for c, i in CLASS_IDS.items() if (area[fcls_id == i] != "").any()}
    return {"V": V, "F": F, "cls": fcls_id, "draw": draw, "area": area, "box": box, "L": L, "rep": rep}


def xy_ids(V):
    """Each vertex's point in the plane as an id (vertices at one point, a step's two, share it)."""
    return np.unique(V[:, :2], axis=0, return_inverse=True)[1].ravel()


def face_up(V, F):
    """The triangles wound counter-clockwise seen from above (an upright one as it is). The page averages a corner's
    normal over the triangles of its draw class beside it (src/groundWorker.js): the constrained Delaunay's faces
    (clockwise) beside the city mesh's triangles kept whole (counter-clockwise) cancelled there, and drew a dark seam a
    triangle wide round every piece of the terrain (#632)."""
    P = V[F][:, :, :2].astype(np.float64)
    s = (P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - (P[:, 1, 1] - P[:, 0, 1]) * (P[:, 2, 0] - P[:, 0, 0])
    F = F.copy()
    F[s < 0] = F[s < 0][:, [0, 2, 1]]
    return F


def step_walls(V, F, above=False):
    """Vertical faces along every edge where the two triangles beside it hold different vertices at the same point, each
    facing away from the higher triangle (seen from below the step; face_up's reason). With `above`: also each wall's
    triangle on the higher side (its draw class is the wall's)."""
    k = xy_ids(V)
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    tri = np.tile(np.arange(len(F)), 3)
    ka, kb = k[e[:, 0]], k[e[:, 1]]
    lo, hi = np.minimum(ka, kb), np.maximum(ka, kb)
    flip = ka > kb
    a = np.where(flip, e[:, 1], e[:, 0])
    b = np.where(flip, e[:, 0], e[:, 1])
    order = np.lexsort((hi, lo))
    lo, hi, a, b, tri = lo[order], hi[order], a[order], b[order], tri[order]
    same = (lo[1:] == lo[:-1]) & (hi[1:] == hi[:-1])
    i = np.flatnonzero(same)
    a1, b1, a2, b2 = a[i], b[i], a[i + 1], b[i + 1]
    up = np.where(V[a1, 2] + V[b1, 2] >= V[a2, 2] + V[b2, 2], tri[i], tri[i + 1])
    out, side = [], []
    for p, q, r, s, u in zip(a1.tolist(), b1.tolist(), a2.tolist(), b2.tolist(), up.tolist()):
        if p == r and q == s:
            continue
        if p != r:
            out.append((p, q, r) if q == s else (p, q, s))
            side.append(u)
        if q != s:
            out.append((p, s, r) if p != r else (p, s, q))
            side.append(u)
    walls = np.asarray(out, int).reshape(-1, 3)
    side = np.asarray(side, int)
    if len(walls):
        W = V[walls].astype(np.float64)
        n = np.cross(W[:, 1] - W[:, 0], W[:, 2] - W[:, 0])
        away = W[:, :, :2].mean(1) - V[F[side]][:, :, :2].astype(np.float64).mean(1)
        back = (n[:, :2] * away).sum(1) < 0
        walls[back] = walls[back][:, [0, 2, 1]]
    return (walls, side) if above else walls


def edge_check(V, F, box):
    """Every edge in the plane used by two triangles, or on the border of the line's ground (`box`: a box or the
    corridor's polygon, ground_partition.line_area; the walls left out: they stand on the steps' edges): the edges used
    once, inside it."""
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
    once = cnt == 1
    if once.any():  # (an edge on the border: both ends and its middle within BORDER_TOL of it, the points on the 1 mm grid)
        i = np.flatnonzero(once)
        line = box.boundary
        d = np.maximum.reduce([shapely.distance(line, shapely.points(px / Q, py / Q)) for px, py in
                               ((ax[i], ay[i]), (bxx[i], byy[i]), ((ax[i] + bxx[i]) / 2, (ay[i] + byy[i]) / 2))])
        once[i[d <= BORDER_TOL]] = False
    more = cnt > 2
    out = {"edges": int(len(u)), "used once inside the box": int(once.sum()), "used more than twice": int(more.sum())}
    for name, m in (("first used once", once), ("first used more than twice", more)):
        if m.any():
            out[name] = [[[int(ax[i]) / Q, int(ay[i]) / Q], [int(bxx[i]) / Q, int(byy[i]) / Q], int(cnt[i])] for i in np.flatnonzero(m)[:5]]
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


def axes(beds):
    """The axes of the tracks on the ground (not a bridge's: the bridge carries it, the page lays nothing under it)."""
    return [shapely.LineString([r[:2] for r in rows]) for k, rows in enumerate(beds.rows)
            if len(rows) > 1 and not beds.tracks[k].get("b")]


def on_rails(cx, cy, beds, outline):
    """Per point on a rail of a track on the ground (within RAIL_NEAR, off bridges): (the rail's height there, between
    its rows as the page draws the bed's edge, the lowest where rails meet; the lowest bed's surface at that rail point),
    NaN off them. Both are taken at the point's foot on the rail, and the beds' outline there decides "on the ground".
    (The faces' points lie on a 1 mm grid: at a joint of two tracks one 0.5 mm off the rail fell between their quads,
    and the bed surface carried out from the nearest gave 6 mm over the rail, line 37 s ~4000; one 0.1 mm off line 17's
    rail lay across another bed's edge, 6.4 mm lower; one 0.17 mm off line 37's lay outside the outline)"""
    lines = np.array([shapely.LineString([(x + nx * off[j], y + ny * off[j], z[j]) for x, y, nx, ny, off, z in rows])
                      for k, rows in enumerate(beds.rows) if len(rows) > 1 and not beds.tracks[k].get("b")
                      for j in (1, 2)], dtype=object)
    zr, zl = np.full(len(cx), np.nan), np.full(len(cx), np.nan)
    if not len(lines) or outline.is_empty:
        return zr, zl
    key = np.round(cx * Q).astype(np.int64) * 10_000_000_000 + np.round(cy * Q).astype(np.int64)
    uk, first, inv = np.unique(key, return_index=True, return_inverse=True)
    pts = shapely.points(cx[first], cy[first])
    pi, li = shapely.STRtree(lines).query(pts, predicate="dwithin", distance=RAIL_NEAR)
    if not len(pi):
        return zr, zl
    foot = shapely.line_interpolate_point(lines[li], shapely.line_locate_point(lines[li], pts[pi]))
    fc = shapely.get_coordinates(foot, include_z=True)
    shapely.prepare(outline)
    keep = shapely.dwithin(outline, shapely.points(fc[:, 0], fc[:, 1]), 1e-6)
    pi, fc = pi[keep], fc[keep]
    z, low = np.full(len(uk), np.nan), np.full(len(uk), np.nan)
    if len(pi):
        np.fmin.at(z, pi, fc[:, 2])
        np.fmin.at(low, pi, beds.surface_at(fc[:, 0], fc[:, 1]))
    return z[inv], low[inv]


def rail_band(beds, outline, pieces):
    """Where the given pieces (raised areas beside a track, plots) come within RAIL_CLEAR of a rail on the ground: one
    polygon. (Line 17 s 17128, #507: a stop's island classed sidewalk lies along the outer rail, 9.5 cm over it; line 9's
    depot hall, a plot, 13.6 cm over its tracks' ends at the door)"""
    lines = [shapely.LineString([(x + nx * off[j], y + ny * off[j]) for x, y, nx, ny, off, _ in rows])
             for k, rows in enumerate(beds.rows) if len(rows) > 1 and not beds.tracks[k].get("b") for j in (1, 2)]
    if not lines or outline.is_empty or not pieces:
        return shapely.Polygon()
    on = [g for g in shapely.get_parts(shapely.intersection(np.array(lines, dtype=object), outline))
          if g.geom_type == "LineString" and not g.is_empty]
    if not on:
        return shapely.Polygon()
    buf = shapely.buffer(np.array(on, dtype=object), RAIL_CLEAR)
    tree = shapely.STRtree(buf)
    parts = []
    for g in pieces:
        hit = tree.query(g, predicate="intersects")
        if len(hit):
            parts += [p for p in shapely.get_parts(shapely.intersection(g, shapely.union_all(buf[hit])))
                      if p.geom_type == "Polygon" and p.area > SLIVER_BAND]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def land_cover(L, x, y, water=None):
    """Per point: the terrain's draw class as the page colours its terrain (src/world.js buildTerrain: OSM's green, wood
    and water in the line data): "grass", "wood", "water" or "" (bare ground). (The page marks its 10 m cells in the
    data's order, water last; here grass, then wood, then water.) `water`: OSM's water with its islands
    (ground_partition.osm_water) in place of the line data's, which keeps outer rings only: its islands lay in it, #632."""
    out = np.full(len(x), "", dtype=object)

    def union(rings):
        polys = [shapely.Polygon([p[:2] for p in r]) for r in rings if len(r) >= 3]
        polys = [p if p.is_valid else shapely.make_valid(p) for p in polys]
        return shapely.union_all(polys) if polys else None
    green = L.get("green") or []
    for name, rings in (("grass", [g["p"] for g in green if g.get("t") != "wood"]),
                        ("wood", [g["p"] for g in green if g.get("t") == "wood"]), ("water", L.get("water") or [])):
        u = water if name == "water" and water is not None else union(rings)
        if u is not None and not u.is_empty:
            shapely.prepare(u)
            out[shapely.contains_xy(u, x, y)] = name
    return out


def crossing_pieces(survey, beds):
    """Per survey piece: a raised one with a track's axis in it (a crossing over the track)."""
    out = np.zeros(len(survey), bool)
    ax = axes(beds)
    ri = [k for k, q in enumerate(survey) if q["c"] in RAISED]
    if ax and ri:
        hit, _ = shapely.STRtree(ax).query(np.asarray([survey[k]["g"] for k in ri], dtype=object), predicate="intersects")
        out[np.asarray(ri)[np.unique(hit)]] = True
    return out


def heads_check(V, F, cls, beds, outline, named=()):
    """The written ground against the top of rail (a rail's row z + lift + BED_BELOW) at every rail point on the ground
    off bridges: the highest triangle there over it by more than RAIL_TOL buries the rail head (#508's done-when; the
    page's lint, tools/lint.js buriedRails). The places: per track and 20 m along it, the worst. `named`: (name, x, y)
    each, the rail points within PLACE_NEAR m of it on their own (#165's and #166's, ground_partition.RAIL_PLACES)."""
    import bed_surface
    pts, top, where = [], [], []
    for k, rows in enumerate(beds.rows):
        if beds.tracks[k].get("b"):
            continue
        for i, (x, y, nx, ny, off, z) in enumerate(rows):
            for j in (1, 2):
                pts.append((x + nx * off[j], y + ny * off[j]))
                top.append(z[j] + beds.lift[k][i] + bed_surface.BED_BELOW)
                where.append((k, i))
    if not pts:
        return {}
    pts, top, where = np.asarray(pts), np.asarray(top), np.asarray(where)
    on = shapely.contains_xy(outline, pts[:, 0], pts[:, 1]) if not outline.is_empty else np.zeros(len(pts), bool)
    pts, top, where = pts[on], top[on], where[on]
    from scipy.spatial import cKDTree
    # (only the triangles near a rail: line 17 holds 10.8 M)
    P = V[F].astype(float) / Q
    cen = P[:, :, :2].mean(1)
    rad = np.linalg.norm(P[:, :, :2] - cen[:, None], axis=2).max(1)
    d, _ = cKDTree(pts).query(cen, distance_upper_bound=float(rad.max()) + 0.01)
    near = d <= rad + 0.01
    z = mesh_at(V, F[near], pts[:, 0], pts[:, 1])
    over = z - top
    bad = np.flatnonzero(over > RAIL_TOL + 0.5 / Q)
    names = {i: c for c, i in CLASS_IDS.items()}
    # (the class of the highest triangle at each point over the rail)
    sub = F[near]
    kinds = {}
    if len(bad):
        Pn = V[sub].astype(float) / Q
        tree = shapely.STRtree(shapely.polygons(np.concatenate([Pn[:, :, :2], Pn[:, :1, :2]], 1)))
        pi, ti = tree.query(shapely.points(pts[bad, 0], pts[bad, 1]), predicate="intersects")
        zz = plane(Pn[ti], pts[bad[pi], 0], pts[bad[pi], 1])
        best = {}
        for a, t, h in zip(pi.tolist(), ti.tolist(), zz.tolist()):
            if a not in best or h > best[a][0]:
                best[a] = (h, names[int(cls[near][t])])
        kinds = {a: c for a, (h, c) in best.items()}
    places = {}
    for n, i in enumerate(bad.tolist()):
        k, r = where[i]
        key = (int(k), int(r * 1.5 // 20))  # (rows every ~1.5 m)
        if key not in places or over[i] > places[key][2]:
            places[key] = (round(float(pts[i, 0]), 2), round(float(pts[i, 1]), 2), float(over[i]), kinds.get(n, ""))
    worst = sorted(places.values(), key=lambda v: -v[2])
    by = {}
    for n in range(len(bad)):
        by[kinds.get(n, "")] = by.get(kinds.get(n, ""), 0) + 1
    out = {"rail points": int(len(pts)), "under the ground": int(len(bad)), "by the class over them": by,
           "places (track, 20 m)": len(places),
           "worst places: x, y, cm over, class": [[x, y, round(o * 100, 1), c] for x, y, o, c in worst[:12]]}
    for name, px, py in named:
        m = np.hypot(pts[:, 0] - px, pts[:, 1] - py) <= PLACE_NEAR
        o = over[m]
        out[name] = {"rail points": int(m.sum()), "under the ground": int((o > RAIL_TOL + 0.5 / Q).sum()),
                     "highest over the top of rail, mm": round(float(np.nanmax(o)) * 1000, 1) if np.isfinite(o).any() else None}
    return out


def rail_places(ln, L):
    """#165's and #166's places on this line (ground_partition.RAIL_PLACES): (name, x, y) on the route."""
    import ground_partition as gp
    from route import Route
    rt = Route(L["path"])
    return [(f"line {ln} s {s}", *rt.at(s)[:2]) for line, s, _ in gp.RAIL_PLACES if line == ln]


def rail_check(cx, cy, zf, kind, beds, outline):
    """The ground under every rail point of every bed row on the ground (the welded height of the bed's corner there)
    against the row's height (#508: within RAIL_TOL). Where two beds overlap (a switch, a crossing) the ground takes the
    lower one: those points are counted apart. A bridge's track is left out: the bridge carries it."""
    pts, want, n_bridge = [], [], 0
    for k, rows in enumerate(beds.rows):
        if beds.tracks[k].get("b"):
            n_bridge += 2 * len(rows)
            continue
        for x, y, nx, ny, off, z in rows:
            for j in (1, 2):
                pts.append((x + nx * off[j], y + ny * off[j]))
                want.append(z[j])
    if not pts:
        return {}
    pts, want = np.asarray(pts), np.asarray(want)
    on = shapely.contains_xy(outline, pts[:, 0], pts[:, 1]) if not outline.is_empty else np.zeros(len(pts), bool)
    pts, want = pts[on], want[on]
    from scipy.spatial import cKDTree
    on_bed = kind == "bed"
    pk = np.round(pts[:, 0] * Q).astype(np.int64) * 10_000_000_000 + np.round(pts[:, 1] * Q).astype(np.int64)
    got = np.full(len(pts), np.nan)
    if on_bed.any():  # (the bed's corner at the rail point; where tracks join, their rails lie a mm or two apart)
        dd, ii = cKDTree(np.column_stack([cx[on_bed], cy[on_bed]])).query(pts, distance_upper_bound=RAIL_NEAR)
        ok = np.isfinite(dd)
        got[ok] = zf[on_bed][ii[ok]]
    lowest = beds.surface_at(pts[:, 0], pts[:, 1])
    d = got - want
    under = np.isfinite(lowest) & (lowest < want - RAIL_TOL)  # (another bed lower there)
    own = ~under & np.isfinite(d)
    return {"rail points on the ground": int(len(pts)), "on bridges, left out": n_bridge,
            "within the tolerance": int((np.abs(d[own]) <= RAIL_TOL + 0.5 / Q).sum()),
            "off by more": int((np.abs(d[own]) > RAIL_TOL + 0.5 / Q).sum()),
            "worst, mm": round(float(np.abs(d[own]).max()) * 1000, 2) if own.any() else None,
            "first off": [[round(float(pts[i, 0]), 3), round(float(pts[i, 1]), 3), round(float(d[i]) * 1000, 1)]
                          for i in np.flatnonzero(own & (np.abs(np.nan_to_num(d)) > RAIL_TOL + 0.5 / Q))[:6]],
            "where another bed lies lower (the ground takes it)": int(under.sum()),
            "no bed corner within RAIL_NEAR (left out)": missing_kinds(cx, cy, kind, pk[np.isnan(d)]),
            "the nearest corner to those, mm p50 / p90 / max": nearest_mm(cx, cy, pts[np.isnan(d)])}


def nearest_mm(cx, cy, pts):
    from scipy.spatial import cKDTree
    if not len(pts):
        return None
    dd, _ = cKDTree(np.column_stack([cx, cy])).query(pts)
    return [round(float(np.percentile(dd, q)) * 1000, 1) for q in (50, 90, 100)]


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
            xk = (k + 5_000_000_000) // 10_000_000_000
            e["first"].append([xk / Q, (k - xk * 10_000_000_000) / Q])
    return out


def page_counts(L, D):
    """The triangles the page drew for the ground before the ground file (#509): the 10 m grid and the survey's ground
    areas (the fine blocks, tools/fine_terrain.py, went with #510)."""
    T = L["terrain"]
    out = {"10 m grid": 2 * (T["nx"] - 1) * (T["ny"] - 1)}
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


def hilbert(x, y, order=20):
    """The index of cells (x, y) along a Hilbert curve over 2^order cells a side."""
    x, y = np.asarray(x, np.int64).copy(), np.asarray(y, np.int64).copy()
    d = np.zeros(len(x), np.int64)
    s = 1 << (order - 1)
    while s > 0:
        rx = ((x & s) > 0).astype(np.int64)
        ry = ((y & s) > 0).astype(np.int64)
        d += s * s * ((3 * rx) ^ ry)
        m = ry == 0
        flip = m & (rx == 1)
        x[flip], y[flip] = s - 1 - x[flip], s - 1 - y[flip]
        x[m], y[m] = y[m].copy(), x[m].copy()
        s >>= 1
    return d


def encode(V, F, cls, box, draw=None, area=None):
    """(bytes, layout): the vertices along a Hilbert curve over the box's 1 m cells, as differences of x, y, z in mm from
    the box's north-west corner and its base; per class its triangles, each turned to start at its lowest index (its
    winding kept), sorted by it: that index's difference to the previous one's and the other two as differences to it.
    (Line 37, 2.45 M triangles: by rows 12.0 MB gzip, along the curve 8.7 MB, brotli 7.3 MB.)
    Per triangle names, "" for none, after all the triangles: `draw` (what the page draws it as) and then `area` (the
    survey's class under it, what the page's lookup answers), each per class with names in the same order as runs (index
    into layout[layer][class], run length; their counts in layout[layer + "Runs"]), #509."""
    x0, y1 = round(box.bounds[0] * Q), round(box.bounds[3] * Q)
    base = int(V[:, 2].min())
    rel = np.stack([V[:, 0] - x0, y1 - V[:, 1], V[:, 2] - base], 1)
    order = np.argsort(hilbert(rel[:, 0] // Q, rel[:, 1] // Q), kind="stable")
    rank = np.empty(len(order), np.int64)
    rank[order] = np.arange(len(order))
    R = rel[order]
    d = np.diff(np.vstack([[0, 0, 0], R]), axis=0)
    parts = [varints(zigzag(d.ravel()))]
    layout = {"unit": 1 / Q, "x0": x0 / Q, "y1": y1 / Q, "base": base / Q, "vertices": int(len(V)), "classes": {}}
    runs = {name: {} for name in LAYERS}
    for c, i in CLASS_IDS.items():
        m = cls == i
        t = rank[F[m]]
        r = t.argmin(1) if len(t) else np.zeros(0, int)
        k = np.arange(len(t))
        t = np.stack([t[k, r], t[k, (r + 1) % 3], t[k, (r + 2) % 3]], 1) if len(t) else t.reshape(0, 3)
        o = np.argsort(t[:, 0], kind="stable")
        t = t[o]
        first = t[:, 0]
        dd = np.column_stack([np.diff(np.concatenate([[0], first])), t[:, 1] - first, t[:, 2] - first])
        parts.append(varints(zigzag(dd.ravel())))
        layout["classes"][c] = int(len(t))
        for name, per in (("draw", draw), ("area", area)):
            if per is None or not len(t):
                continue
            d = np.asarray(per, dtype=object)[m][o].astype(str)
            if (d != "").any():
                names, ids = np.unique(d, return_inverse=True)
                cut = np.flatnonzero(np.diff(ids)) + 1
                starts = np.concatenate([[0], cut])
                lens = np.diff(np.concatenate([starts, [len(ids)]]))
                runs[name][c] = (names.tolist(), np.column_stack([ids[starts], lens]).ravel())
    for name in LAYERS:
        if not runs[name]:
            continue
        layout[name], layout[name + "Runs"] = {}, {}
        for c, (names, rl) in runs[name].items():
            parts.append(varints(rl.astype(np.int64)))
            layout[name][c], layout[name + "Runs"][c] = names, int(len(rl) // 2)
    blob = b"".join(parts)
    layout["sections"] = [len(p) for p in parts]
    return blob, layout


def encode_tiles(V, F, cls, draw=None, area=None):
    """(bytes, layout): the mesh as the world's tiles (geo.TILE m squares on the S-JTSK grid, #30), one after another, each
    encoded on its own (encode(): its own vertices, those on its border repeated in its neighbour), so the page decodes
    the tiles it needs. A triangle goes to the tile holding its centre: the faces are built square by square on the same
    grid, so it lies in it. The layout: per tile its name, index, byte range and own layout; the totals; and per class
    every draw and area name a tile uses (the page's styles, src/groundDraw.js groundStyles)."""
    cen = V[F].mean(1) / Q
    e, n = tile_index(cen[:, 0], cen[:, 1])
    keys, inv = np.unique(np.column_stack([e, n]), axis=0, return_inverse=True)
    inv = inv.ravel()
    order = np.argsort(inv, kind="stable")
    cut = np.searchsorted(inv[order], np.arange(len(keys) + 1))
    per = {name: (None if v is None else np.asarray(v, dtype=object)) for name, v in (("draw", draw), ("area", area))}
    parts, tiles, off, names = [], [], 0, {name: {} for name in LAYERS}
    for k, (te, tn) in enumerate(keys.tolist()):
        m = order[cut[k]:cut[k + 1]]
        used, fl = np.unique(F[m], return_inverse=True)
        b, lay = encode(V[used], fl.reshape(-1, 3), cls[m], shapely.box(*tile_box(te, tn)),
                        None if per["draw"] is None else per["draw"][m], None if per["area"] is None else per["area"][m])
        tiles.append({"name": tile_name(te, tn), "e": te, "n": tn, "offset": off, "bytes": len(b), "layout": lay})
        for name in LAYERS:
            for c, v in (lay.get(name) or {}).items():
                names[name].setdefault(c, set()).update(v)
        parts.append(b)
        off += len(b)
    from geo import ORIGIN
    layout = {"tile": TILE, "origin": list(ORIGIN), "unit": 1 / Q, "vertices": int(sum(t["layout"]["vertices"] for t in tiles)),
              "triangles": int(len(F)), "classes": {c: int((cls == i).sum()) for c, i in CLASS_IDS.items()}, "tiles": tiles}
    for name in LAYERS:
        if names[name]:
            layout[name] = {c: sorted(v) for c, v in names[name].items()}
    return b"".join(parts), layout


def decode(blob, layout, draw=False, area=False):
    """(V (n, 3) float m, {class: (m, 3) indexes}); with `draw` also {class: per triangle its draw class's name}, with
    `area` also {class: per triangle the survey's class under it}. A tiled file (encode_tiles) as one mesh: its tiles
    decoded and the vertices they share on their borders welded (the same mm position)."""
    if "tiles" not in layout:
        return decode_one(blob, layout, draw, area)
    Vs, by, names, nv = [], {}, {"draw": {}, "area": {}}, 0
    for t in layout["tiles"]:
        got = decode_one(blob[t["offset"]:t["offset"] + t["bytes"]], t["layout"], draw, area)
        Vs.append(got[0])
        for c, f in got[1].items():
            by.setdefault(c, []).append(f + nv)
        k = 2
        for name, want in (("draw", draw), ("area", area)):
            if want:
                # (a tile names a class's triangles only where one has a name: the others' are "")
                for c, f in got[1].items():
                    v = got[k].get(c)
                    names[name].setdefault(c, []).append((v, len(f)))
                k += 1
        nv += len(got[0])
    V = np.vstack(Vs) if Vs else np.zeros((0, 3))
    keys, first, inv = np.unique(np.round(V * Q).astype(np.int64), axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    V = V[first]
    out = {c: inv[np.vstack(f)] if f else np.zeros((0, 3), np.int64) for c, f in by.items()}
    extra = ()
    for name, want in (("draw", draw), ("area", area)):
        if want:
            extra += ({c: np.concatenate([np.full(m, "", dtype=object) if a is None else a for a, m in v])
                       for c, v in names[name].items() if any(a is not None for a, _ in v)},)
    return (V, out) + extra


def decode_one(blob, layout, draw=False, area=False):
    """decode() of one encode() blob (a tile, or a whole file before #30)."""
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
    if not (draw or area):
        return V, out
    names = {}
    for name in LAYERS:
        names[name] = {}
        for c, n in (layout.get(name + "Runs") or {}).items():
            u, off = read_varints(blob, 2 * n, off)
            rl = np.asarray(u, np.int64).reshape(n, 2)
            names[name][c] = np.repeat(np.asarray(layout[name][c], dtype=object)[rl[:, 0]], rl[:, 1])
    return (V, out) + ((names["draw"],) if draw else ()) + ((names["area"],) if area else ())


# ---------------------------------------------------------------- the road tunnels' mouths
MOUTH_FIT = {"road", "parking", "paved", "sidewalk", "cycle", "island", "median", "tram"}  # (src/structures.js until #682)
MOUTH_OVER, MOUTH_ON, MOUTH_NEAR = 0.3, 0.05, 5  # m, m, mm


def fit_mouths(ln, built, log=print):
    """The survey's street areas round a road tunnel's mouth often take the portal's crown into their outline (a road
    area at the Letenský tunel ran 191-206 m: a grey ramp across the opening). In each mouth's footprint (3 m out of it
    to its depth inward, its width + 1.5 m to each side: tools/ground_at.py Ground.mouths), a vertex of a street triangle
    (MOUTH_FIT, as the page's lookup holds it: not a wall, not upright) more than MOUTH_OVER over the tunnel road comes
    down to MOUTH_ON over it, and every vertex at one of those points (within MOUTH_NEAR in plan and height: a lawn, a
    bed or a step's wall sharing the corner) with it. The page did this at load until #682 (src/structures.js mouthFix);
    the tunnel road's height comes from the ground as it was before (its portals: the lowest ground out of the mouth).
    Changes built["V"]; returns the counts."""
    import ground_at
    import network
    L, V, F, cls, area = built["L"], built["V"], built["F"], built["cls"], built["area"]
    if not any(r.get("t") and r.get("c") and not r.get("z") for r in L.get("roads") or []):
        return {"mouths": 0}
    L = {**L, "roads": [dict(r) for r in L["roads"]]}
    network.widen_tram_streets(L)  # (the roads as the page has them: a tram street is wider, src/streets.js)
    blob, layout = encode_tiles(V, F, cls, built.get("draw"), area)
    mouths = ground_at.Ground(ln, L, file=(layout, blob)).mouths()
    if not mouths:
        return {"mouths": 0}
    x, y, z = V[:, 0] / Q, V[:, 1] / Q, V[:, 2] / Q
    # (the lookup's triangles: no walls, none upright)
    a, b, c = F[:, 0], F[:, 1], F[:, 2]
    flat = ~(((x[a] == x[b]) & (y[a] == y[b])) | ((x[b] == x[c]) & (y[b] == y[c])) | ((x[a] == x[c]) & (y[a] == y[c])))
    street = (cls != CLASS_IDS["wall"]) & flat & np.isin(area.astype(str), sorted(MOUTH_FIT))
    cand = np.zeros(len(V), bool)
    cand[F[street].ravel()] = True
    near = np.zeros(len(V), bool)
    for m in mouths:
        r = m["D"] + m["w"] + 5
        near |= (np.abs(x - m["p"][0]) <= r) & (np.abs(y - m["p"][1]) <= r)
    moved = {}  # vertex -> its new height (m)
    for v in np.flatnonzero(cand & near).tolist():
        for m in mouths:
            d = (x[v] - m["p"][0]) * m["hx"] + (y[v] - m["p"][1]) * m["hy"]
            lat = (x[v] - m["p"][0]) * m["nx"] + (y[v] - m["p"][1]) * m["ny"]
            if d < -3 or d > m["D"] or abs(lat) > m["w"] + 1.5:
                continue
            zt = m["zAt"](d) + MOUTH_ON
            if float(np.float32(z[v])) > zt + MOUTH_OVER:
                moved[v] = zt
                break
    if not moved:
        return {"mouths": len(mouths), "points": 0, "vertices": 0}
    # every vertex at a moved point follows it (the page: each drawn vertex within MOUTH_NEAR of a moved one)
    P = V[list(moved)]
    to = np.array(list(moved.values()))
    from scipy.spatial import cKDTree
    tree = cKDTree(P.astype(float))
    idx = np.flatnonzero(near)
    hits = tree.query_ball_point(V[idx].astype(float), MOUTH_NEAR * math.sqrt(3) + 1e-6)
    n = 0
    for v, hs in zip(idx.tolist(), hits):
        if v in moved:
            V[v, 2] = int(round(moved[v] * Q))
            n += 1
            continue
        for h in sorted(hs):
            if (np.abs(V[v] - P[h]) <= MOUTH_NEAR).all():
                V[v, 2] = int(round(to[h] * Q))
                n += 1
                break
    walls = weld_coincident(built)
    log(f"  tunnel mouths: {len(mouths)}, {len(moved)} street points brought down, {n} vertices with them, {walls} "
        f"step walls between two of them gone")
    return {"mouths": len(mouths), "points": len(moved), "vertices": n, "walls gone": walls}


def weld_coincident(built):
    """Vertices at one position (mm) as one, and the triangles that loses (a step's wall between two vertices both brought
    down onto the tunnel road: fit_mouths) dropped with their names. The file holds each position once, as decode() reads
    it. Returns the triangles dropped."""
    V, F = built["V"], built["F"]
    u, inv = np.unique(V, axis=0, return_inverse=True)
    if len(u) == len(V):
        return 0
    F2 = inv.ravel()[F]
    good = (F2[:, 0] != F2[:, 1]) & (F2[:, 1] != F2[:, 2]) & (F2[:, 0] != F2[:, 2])
    built["V"], built["F"] = u, F2[good]
    for k in ("cls", "draw", "area"):
        if built.get(k) is not None:
            built[k] = built[k][good]
    return int((~good).sum())


def write(ln, built, rep):
    import sources
    from atomic import replacing
    blob, layout = encode_tiles(built["V"], built["F"], built["cls"], built.get("draw"), built.get("area"))
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


COLORS = {"terrain": (130, 175, 110), "survey": (150, 150, 158), "bed": (150, 90, 60), "plot": (210, 120, 120)}


def picture(ln, window, path, px=5):
    """The written ground seen from above at a window (x0, y0, x1, y1): each triangle its class's colour, shaded by its
    slope (light from the north-west), the steps' walls as red lines."""
    from PIL import Image, ImageDraw
    layout = json.load(open(os.path.join(ROOT, "data", f"line{ln}.ground.json"), encoding="utf-8"))
    with open(os.path.join(ROOT, "data", f"line{ln}.ground.bin"), "rb") as f:
        V, by = decode(f.read(), layout)
    x0, y0, x1, y1 = window
    n = int((x1 - x0) * px)
    im = Image.new("RGB", (n, n), (255, 255, 255))
    d = ImageDraw.Draw(im)
    light = np.array([-1.0, 1.0, 1.5])
    light /= np.linalg.norm(light)
    for c in ("terrain", "plot", "survey", "bed"):
        t = by[c]
        P = V[t]
        inside = ((P[:, :, 0] >= x0 - 5).any(1) & (P[:, :, 0] <= x1 + 5).any(1) & (P[:, :, 1] >= y0 - 5).any(1) &
                  (P[:, :, 1] <= y1 + 5).any(1))
        P = P[inside]
        nrm = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        nrm *= np.sign(nrm[:, 2:3] + 1e-12)
        shade = 0.55 + 0.45 * np.clip((nrm / (np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12)) @ light, 0, 1)
        for tri, sh in zip(P, shade):
            d.polygon([((a - x0) * px, (y1 - b) * px) for a, b, _ in tri], fill=tuple(int(v * sh) for v in COLORS[c]))
    W = V[by["wall"]]
    for tri in W:
        xy = np.unique(np.round(tri[:, :2], 3), axis=0)
        if len(xy) == 2 and (x0 <= xy[:, 0]).all() and (xy[:, 0] <= x1).all() and (y0 <= xy[:, 1]).all() and (xy[:, 1] <= y1).all():
            d.line([((a - x0) * px, (y1 - b) * px) for a, b in xy], fill=(220, 30, 30), width=1)
    im.save(path)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line")
    ap.add_argument("--lines")
    ap.add_argument("--mesh")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--min-free", type=float, default=4.0, help="GB: the run stops itself when free memory falls under it")
    a = ap.parse_args(argv)
    lines = a.lines.split(",") if a.lines else [a.line]
    rep_dir = os.path.join(ROOT, "reports", "ground-mesh")
    import threading
    import sysinfo

    def guard():  # (the machine is shared: this run ends itself rather than push it into swapping, as city_terrain.py)
        while True:
            if (sysinfo.available_gb() or 99) < a.min_free:
                print(f"free memory under {a.min_free} GB: stopped", flush=True)
                os._exit(3)
            time.sleep(2)
    threading.Thread(target=guard, daemon=True).start()
    os.makedirs(rep_dir, exist_ok=True)
    from baseline_store import HeavyJob
    with HeavyJob("ground_mesh"):
        for ln in lines:
            built = build(ln, a.mesh, a.threads)
            rep = built["rep"]
            t1 = time.time()
            rep["tunnel mouths"] = fit_mouths(ln, built)
            rep["seconds"]["mouths"] = round(time.time() - t1, 1)
            t1 = time.time()
            rep["error"] = raster_error(built, ln)
            rep["seconds"]["error"] = round(time.time() - t1, 1)
            if not a.no_write:
                write(ln, built, rep)
                # (the network reads the survey from this file: built after it, every time, #658)
                import network
                rep["network"] = network.write(ln, network.build(ln, log=lambda m: print(m, flush=True)))
            if not a.no_write:
                import ground_partition as gp
                wins = {k: w for k, (l2, w) in gp.place_windows({ln: built["L"]}).items() if l2 == ln}
                bw = rep["partition"].get("bed window")
                if bw:
                    wins["bed"] = bw
                for name, w in wins.items():
                    pth = os.path.join(rep_dir, f"{name}-line{ln}.png")
                    picture(ln, w, pth)
                    rep.setdefault("pictures", []).append(os.path.relpath(pth, ROOT).replace(os.sep, "/"))
            with open(os.path.join(rep_dir, f"line{ln}.json"), "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=1, ensure_ascii=False)
            print(json.dumps({k: v for k, v in rep.items() if k != "partition"}, indent=1, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
