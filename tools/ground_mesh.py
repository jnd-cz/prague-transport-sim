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
STAIRS_FLAT = 0.2  # m: a stairs area whose outline's points all lie this near one plane is one flight


def flight(a):
    """The plane of a stairs area that is one flight: (x0, y0, (gx, gy, z0)), z = z0 + gx (x - x0) + gy (y - y0); None
    where its outline's points do not lie within STAIRS_FLAT of a plane (a turn, a landing, a side wall's top in the
    outline: 49-67 % of a line's stairs rising over 0.5 m). The outline's heights triangulated gave a warped sheet:
    Krejcárek's eight steps (survey area 1339, line 37 (3927, 329)) strayed 0.39 m from their straight line, #447."""
    P = np.array([q for q in a["r"] if q[2] is not None], float)
    if len(P) < 3:
        return None
    x0, y0 = P[:, 0].mean(), P[:, 1].mean()
    A = np.column_stack([P[:, 0] - x0, P[:, 1] - y0, np.ones(len(P))])
    coef, _, rank, _ = np.linalg.lstsq(A, P[:, 2], rcond=None)
    if rank < 3 or np.abs(A @ coef - P[:, 2]).max() > STAIRS_FLAT:
        return None
    return x0, y0, coef


RISER = 1.0  # m: an outline rising this much between two points RISER_RUN apart or nearer climbs a wall
RISER_RUN = 1.0  # m


def climbs(a):
    """Whether a survey area's outline climbs a wall: two points next to each other on it RISER_RUN apart or nearer and
    RISER or more apart in height. Such an area lies on two levels and its outline's heights, triangulated, are no
    surface: the sidewalk at the Modřany viaduct's abutment (line 17, area 7214) is the street's sidewalk under the bridge
    at 198.2 m, the strip on the ramp at 203-204 m and the abutment's shelf at 201.7 m in one outline, which steps
    198.48 -> 200.80 m in 0.49 m; under the bridge it rose 3.4 m in 12 m to the abutment, where IPR's raster and the
    street surface are level to 0.1 m (#761)."""
    for r in [a["r"]] + a.get("h", []):
        P = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in r], float)
        if len(P) < 2:
            continue
        Q2 = np.roll(P, -1, 0)
        run = np.hypot(Q2[:, 0] - P[:, 0], Q2[:, 1] - P[:, 1])
        with np.errstate(invalid="ignore"):
            if ((run <= RISER_RUN) & (np.abs(Q2[:, 2] - P[:, 2]) >= RISER)).any():
                return True
    return False


TERRACE = 1.0  # m: a lidar-ground area's outline this far over the lidar (its points' median) beside a wall as high


def over_lidar(a, lidar):
    """How far a survey area's outline stands over the lidar: the median over its points with a height (NaN without)."""
    r = np.array([q[:3] for q in a["r"] if q[2] is not None], float)
    if not len(r):
        return np.nan
    d = r[:, 2] - np.asarray(lidar(r[:, 0], r[:, 1]), float)
    d = d[np.isfinite(d)]
    return float(np.median(d)) if len(d) else np.nan


PIT = 50.0  # m2: a green area up to this size inside a sidewalk is a tree pit or a small bed
PIT_NEAR = 0.2  # m: its outline's points lie this near a raised area or inside one


def pits(D, ids):
    """Which of the survey areas `ids` are a tree pit or a small bed in a sidewalk: {id}. A green area at level 0, up
    to PIT m2, whose every outline point lies in a raised area (RAISED) or within PIT_NEAR of one. On the lidar it
    stood 5-10 cm off the sidewalk's street surface round it, a kerb's step at its outline (STEP), and bumped inside:
    a green slab with dark sides in the sidewalk (line 22 (-772, 534.5), area 1973, 30 m2: -0.09 to +0.3 m). The user,
    2026-11-20, on pictures of alpha-4, which drew them flush, against main (#696): flush. The five lines have 82-528
    such areas up to 5 m2 and 127-290 more up to PIT; a larger one is a lawn (106-167 a line of 50-200 m2)."""
    ids = [i for i in ids if D["areas"][i].get("c") == "green" and D["areas"][i].get("l", 0) == 0 and len(D["areas"][i]["r"]) >= 3]
    if not ids:
        return set()
    small = []
    for i in ids:
        a = D["areas"][i]
        g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
        if (g if g.is_valid else g.buffer(0)).area <= PIT:
            small.append(i)
    if not small:
        return set()
    walk = []
    for a in D["areas"]:
        if a.get("c") in RAISED and a.get("l", 0) == 0 and len(a["r"]) >= 3:
            g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
            walk.append(g if g.is_valid else g.buffer(0))
    if not walk:
        return set()
    tree = shapely.STRtree(walk)
    out = set()
    for i in small:
        pts = shapely.points([q[:2] for q in D["areas"][i]["r"]])
        pi, _ = tree.query(pts, predicate="dwithin", distance=PIT_NEAR)
        if len(np.unique(pi)) == len(pts):
            out.add(i)
    return out


def bare_holes(D, ids):
    """The small holes of the raised survey areas `ids` that no other area fills: [polygons]. The survey leaves a
    shelter's or a kiosk's footprint out of the sidewalk it stands on (line 37, Krejcárek's platform, area 284: a hole
    of 5.7 m2 at (3907.3, 318.2)). The ground filled it with the terrain on the lidar, 0.1-0.2 m over the platform
    round it with step walls: a slab on the platform (the user, 2026-11-20, #776). A hole up to PIT m2 at least half
    bare is the raised area's own ground."""
    out = []
    polys, own = [], []
    for i, a in enumerate(D["areas"]):
        if a.get("l", 0) != 0 or len(a.get("r") or []) < 3:
            continue
        g = shapely.Polygon([q[:2] for q in a["r"]])
        polys.append(g if g.is_valid else g.buffer(0))
        own.append(i)
    if not polys:
        return out
    tree = shapely.STRtree(polys)
    for i in ids:
        a = D["areas"][i]
        if a.get("c") not in RAISED or a.get("l", 0) != 0:
            continue
        for h in a.get("h", []):
            if len(h) < 3:
                continue
            g = shapely.Polygon([q[:2] for q in h])
            g = g if g.is_valid else g.buffer(0)
            if g.is_empty or g.area > PIT:
                continue
            inside = [polys[k] for k in tree.query(g, predicate="intersects").tolist() if own[k] != i]
            bare = g.difference(shapely.union_all(inside)) if inside else g
            if bare.area >= 0.5 * g.area:
                out.append(bare)
    return out


PLATFORM_BAND = 4.0  # m from the track's axis: a platform's edge 1.35 m from it (data/truth.json platform-edge-offset)
# and its free width behind the edge (CSN 73 6425-1, 7.3.5: 2.20 m, 2.50 recommended)
PLATFORM_FADE = 1.5  # m past the band, and from either end inward: the plane gives way to the street surface
PLATFORM_NEAR = 0.5  # m: a corner farther from the platform's plane is something else (a ramp, a wall's top)
PLATFORM_CROSS = 0.02  # the steepest crossfall a platform takes (the norm's 6.2.2.3: 0.5-2 %)
PLATFORM_MIN = 20  # corners in a platform's band for it to have a plane


def platform_planes(L, x, y, z, ok, log=None):
    """Heights z of corners (x, y) with those `ok` (a raised area's, on its street surface) in a stop's platform laid on
    the platform's plane: (z, the corners moved). A platform stands a steady height over the top of rail along the
    track, with one crossfall; the sidewalk's street surface follows IPR's raster and the survey's points instead, and
    at Krejcárek (line 37 s 2904-2974) stood +0.01 to +0.41 m over the rail top 0.6 m behind the edge, up to 0.16 m
    apart from one metre to the next, with a mound of 0.3 m by the shelter (the user, 2026-11-20, #776: "uneven
    surface"; his photo: level asphalt). 98 of the five lines' 149 platforms were over 5 cm off a line along.
    - A platform is one of L["platforms"] along the route or the back path, not a Vienna-type one (boarding from the
      sidewalk across a lane: that sidewalk follows its street).
    - Its band: between its ends along its path, on its side, up to PLATFORM_BAND from the path's axis.
    - Its plane: over the rail top beside each corner, the height at the axis and one crossfall, fitted to the band's
      own corners (the survey's and the raster's reading, their middle); the crossfall held to PLATFORM_CROSS. No one
      height holds for every stop (the user: "the heights can vary between different stops and stop styles").
    - A corner within PLATFORM_NEAR of the plane takes it; past the band and towards the platform's ends it fades to
      the corner's own height over PLATFORM_FADE. A platform with under PLATFORM_MIN corners, or under half of them
      near its plane, is left."""
    z = np.array(z, float)
    moved = np.zeros(len(z), bool)
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.asarray(ok, bool) & np.isfinite(z)
    h_ = L.get("heights") or {}
    for pf in L.get("platforms") or []:
        key = {"route": "path", "back": "pathBack"}.get(pf.get("path"))
        if key is None or pf.get("vienna") is not None or key not in L or key not in h_:
            continue
        path = np.asarray(L[key], float)[:, :2]
        if len(path) < 2:
            continue
        line = shapely.LineString(path)
        s0, s1, side = float(pf["s0"]), float(pf["s1"]), float(pf["side"])
        if s1 - s0 < 2 * PLATFORM_FADE:
            continue
        part = shapely.ops.substring(line, max(s0, 0.0), min(s1, line.length))
        bx0, by0, bx1, by1 = part.bounds
        reach = PLATFORM_BAND + PLATFORM_FADE
        k = np.flatnonzero(ok & (x >= bx0 - reach) & (x <= bx1 + reach) & (y >= by0 - reach) & (y <= by1 + reach))
        if len(k) < PLATFORM_MIN:
            continue
        pts = shapely.points(x[k], y[k])
        s = shapely.line_locate_point(line, pts)
        A = shapely.get_coordinates(shapely.line_interpolate_point(line, np.maximum(s - 0.5, 0.0)))
        B = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 0.5, line.length)))
        t = B - A
        left = t[:, 0] * (y[k] - A[:, 1]) - t[:, 1] * (x[k] - A[:, 0])
        d = shapely.distance(line, pts)
        on = (s >= s0) & (s <= s1) & (left * side > 0) & (d <= reach)
        k, s, d = k[on], s[on], d[on]
        core = d <= PLATFORM_BAND
        if core.sum() < PLATFORM_MIN:
            continue
        zr = np.asarray(h_[key], float)
        rail = np.interp(s, np.arange(len(zr)) * float(h_["step"]), zr)
        h = z[k] - rail
        use = core.copy()
        a = b = 0.0
        for _ in range(3):  # (the fit of the corners near it: a ramp's foot or a wall's top in the band is none of it)
            if use.sum() < PLATFORM_MIN:
                break
            b = float(np.clip(np.polyfit(d[use], h[use], 1)[0], -PLATFORM_CROSS, PLATFORM_CROSS))
            a = float(np.median(h[use] - b * d[use]))
            use = core & (np.abs(h - (a + b * d)) <= 0.15)
        near = np.abs(h - (a + b * d)) <= PLATFORM_NEAR
        if use.sum() < PLATFORM_MIN or (core & near).sum() < 0.5 * core.sum():
            continue
        w = np.clip((reach - d) / PLATFORM_FADE, 0, 1) * np.clip(np.minimum(s - s0, s1 - s) / PLATFORM_FADE, 0, 1)
        z[k[near]] += (w * (rail + a + b * d - z[k]))[near]
        moved[k[near & (w > 0)]] = True
        if log:
            log(f"  platform {pf.get('name')} {pf.get('code') or ''}: {a:+.2f} m over the rail top at the axis, crossfall {b * 100:+.1f} %, "
                f"{int(near.sum())} corners")
    return z, moved


def terraces(D, ids, lidar):
    """Which of the lidar-ground areas `ids` are terraces: {id}. A lawn or a yard on the lidar (`g`) has surveyed heights
    on its outline only and lies on the lidar inside (#444). On a raised courtyard the lidar's ground is the ground
    round it: line 37 (7590, 743), six beds whose outlines stand 2.1-3.7 m over IPR's raster inside walls as high; laid
    on the lidar they were pits and their walls blades (#663). A terrace is a level-0 `g` area whose outline stands
    TERRACE or more over the lidar and that touches a wall (wall_like) whose outline does too: it keeps its own
    outline's surface. lidar(x, y): IPR's raster in the line's frame."""
    ids = [i for i in ids if D["areas"][i].get("g") and D["areas"][i].get("l", 0) == 0 and len(D["areas"][i]["r"]) >= 3]
    if not ids:
        return set()
    high = [i for i in ids if (over_lidar(D["areas"][i], lidar) or 0) >= TERRACE]  # (NaN: not over)
    if not high:
        return set()
    walls = []
    for a in D["areas"]:
        if a.get("l", 0) != 0 or len(a["r"]) < 3 or not wall_like(a):
            continue
        walls.append(a)
    if not walls:
        return set()
    polys = shapely.polygons([shapely.LinearRing([q[:2] for q in a["r"]]) for a in walls])
    tree = shapely.STRtree(polys)
    over = {}
    out = set()
    for i in high:
        g = shapely.Polygon([q[:2] for q in D["areas"][i]["r"]])
        for k in tree.query(g, predicate="dwithin", distance=0.05).tolist():
            if k not in over:
                over[k] = over_lidar(walls[k], lidar)
            if over[k] >= TERRACE:
                out.add(i)
                break
    return out


TERRACE_SHARE = 0.25  # of a footpath's outline points TERRACE over the lidar: it runs onto the terrace it touches


def beside(D, ids, raised, lidar):
    """Which of the areas `ids` touch one of the areas `raised` and stand on it: {id}, those with TERRACE_SHARE of their
    outline's points TERRACE or more over the lidar. A footpath between a raised courtyard's beds (line 37, sidewalk
    2962: 30 % of its points) has their heights in its outline; on the street surface, which reads the lidar, it ran
    in a trench 2-3 m under them (#663). A street's sidewalk along a terrace's foot touches it too and stays on the
    street surface: 2-3 a line, up to 2.3 ha, none of their points over."""
    if not raised or not ids:
        return set()
    R = sorted(raised)
    tree = shapely.STRtree(shapely.polygons([shapely.LinearRing([q[:2] for q in D["areas"][i]["r"]]) for i in R]))
    out = set()
    for i in ids:
        r = D["areas"][i]["r"]
        if len(r) < 3 or not len(tree.query(shapely.Polygon([q[:2] for q in r]), predicate="dwithin", distance=0.05)):
            continue
        P = np.array([q[:3] for q in r if q[2] is not None], float)
        if len(P):
            d = P[:, 2] - np.asarray(lidar(P[:, 0], P[:, 1]), float)
            if np.isfinite(d).any() and (d[np.isfinite(d)] >= TERRACE).mean() >= TERRACE_SHARE:
                out.add(i)
    return out


class SurveySurface:
    """Each survey area's own surface: its outline's heights, triangulated (the page's DtmSurface); a stairs area that is
    one flight, its plane (flight())."""

    def __init__(self, D, areas):
        self.tris, self.area, self.flights = [], [], {}
        for i in sorted(set(areas)):
            a = D["areas"][i]
            if a["c"] == "stairs":
                f = flight(a)
                if f is not None:
                    self.flights[i] = f
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
        if area in self.flights:
            x0, y0, (gx, gy, z0) = self.flights[area]
            return z0 + gx * (np.asarray(x, float) - x0) + gy * (np.asarray(y, float) - y0)
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


LATTICE_FINE = 1.0  # m: a lattice cell its surface bends in is cut to this
LATTICE_BEND = 0.50  # m: a surface this far off the plane through its lattice cell bends in it (a road's crown over a
# 5 m cell is 3 cm off; a wall the survey has no area for crosses a cell by metres)


def bends(g, at, step=None, fine=LATTICE_FINE, tol=LATTICE_BEND):
    """Lines every `fine` m, on the tiles' grid, inside the lattice cells of g in which the surface at(x, y) leaves the
    plane through its samples there by more than tol (None when none does). The mesh reads a surface at its corners
    only: a wall between level grounds that the survey has no area for (Rašínovo nábřeží, line 17 (-743, -1421): the
    sidewalk level to the quay wall's top, 8 m over the lower quay) crossed a 5 m cell as one straight slope from the
    kerb down, #697."""
    step = step or SURVEY_LATTICE
    x0, y0, x1, y1 = g.bounds
    gx, gy = on_grid(x0, step, 0) - step, on_grid(y0, step, 1) - step
    nx, ny = int(math.ceil((x1 - gx) / step)), int(math.ceil((y1 - gy) / step))
    if nx < 1 or ny < 1:
        return None
    h = fine / 2
    m = int(round(step / h))
    # (samples at the cells' insides: half a sample in from their edges, so each belongs to one cell)
    X, Y = np.meshgrid(gx + (np.arange(nx * m) + 0.5) * h, gy + (np.arange(ny * m) + 0.5) * h)
    shapely.prepare(g)
    ok = shapely.contains_xy(g, X.ravel(), Y.ravel())
    if not ok.any():
        return None
    Z = np.full(X.size, np.nan)
    Z[ok] = at(X.ravel()[ok], Y.ravel()[ok])
    Z = Z.reshape(ny, m, nx, m).transpose(0, 2, 1, 3).reshape(ny, nx, m * m)
    Xc = X.reshape(ny, m, nx, m).transpose(0, 2, 1, 3).reshape(ny, nx, m * m)
    Yc = Y.reshape(ny, m, nx, m).transpose(0, 2, 1, 3).reshape(ny, nx, m * m)
    segs = []
    for j, i in zip(*np.nonzero(np.isfinite(Z).sum(2) >= 4)):
        z = Z[j, i]
        f = np.isfinite(z)
        A = np.column_stack([Xc[j, i][f], Yc[j, i][f], np.ones(int(f.sum()))])
        coef = np.linalg.lstsq(A, z[f], rcond=None)[0]
        if np.abs(A @ coef - z[f]).max() <= tol:
            continue
        cx, cy = gx + i * step, gy + j * step
        for k in range(1, int(round(step / fine))):
            segs.append(((cx + k * fine, cy), (cx + k * fine, cy + step)))
            segs.append(((cx, cy + k * fine), (cx + step, cy + k * fine)))
    if not segs:
        return None
    return shapely.intersection(shapely.MultiLineString(segs), g)


BED_OVER = 2.0  # m: a survey area this far under the bed over it in plan is under a structure, not on the bed (#761; the
# troughs beside a bed, #548, are under 1 m)
WALL_HOLD = 1.5  # m: a corner this near a wall's line stands at the level of its side (IPR's raster smears a step this
# far, street_profile.SW_KERB_SMEAR; the street surface and the city mesh carry the smear)


ABUT_AHEAD = (2.5, 3.0, 3.5, 4.0)  # m past a bed's end: where the lidar is read for the ground a deck leaves (wall_lines.FIT)
ABUT_BACK = 4.0  # m back from a bed's end: the abutment's face is looked for this far under an overhanging bed
ABUT_STEP = 0.25  # m between the lidar's readings back from the end
ABUT_SNAP = 1.5  # m along the track: a wing wall's point this near the face is the face's end (the raster's smear)
ABUT_WING = 8.0  # m: an abutment's line reaches this far either side of the track for a surveyed wing wall
ABUT_JOIN = 6.0  # m: bed ends this near each other are one abutment (a double track's two)


def span_decks(L):
    """The line's bridges in plan: its route's spans and the tracks marked as a bridge's, BRIDGE_NEAR either side (one
    polygon; None where it has none)."""
    route = shapely.LineString([p[:2] for p in L["path"]])
    spans = [shapely.ops.substring(route, a, b) for a, b in L.get("spans") or L.get("bridges") or []]
    spans += [shapely.LineString([p[:2] for p in t["p"]]) for t in L.get("tracks") or [] if t.get("b") and len(t.get("p") or []) > 1]
    if not spans:
        return None
    return shapely.union_all(shapely.buffer(np.asarray(spans, dtype=object), BRIDGE_NEAR, cap_style="flat"))


TUNNEL_ROCK = 8.0  # m: the lidar this far over the rails on average along a tunnel of the route: through rock (src/terrain.js rockTunnels)
TUNNEL_OUT = 0.5  # m: the page's hole in the terrain begins this far before the tunnel (src/world.js inTunnel)
TUNNEL_ACROSS = 8.5  # m either side of the route: the vault's half width (src/world.js TUN_W)
TUNNEL_OVER = 0.5  # m: a survey corner in a rock tunnel's corridor this far over the rails stands on the hill, not the floor


def rail_top(L, s):
    """The top of rail at distances s along the route (data/lineN.json heights: every `step` m)."""
    h = L["heights"]
    z = np.asarray(h["path"], float)
    return np.interp(np.asarray(s, float), np.arange(len(z)) * float(h["step"]), z)


def rock_tunnels(L, lidar):
    """The route's tunnels through rock, as the page judges them (src/terrain.js rockTunnels, there on the 10 m terrain
    grid): [(a, b)] of L["tunnels"] with the lidar TUNNEL_ROCK or more over the rails on average, every 4 m along."""
    path = np.asarray(L.get("path") or [], float)[:, :2]
    if len(path) < 2 or "heights" not in L:
        return []
    route = shapely.LineString(path)
    out = []
    for a, b in L.get("tunnels") or []:
        ss = np.arange(float(a), float(b) + 1e-9, 4.0)
        pts = shapely.get_coordinates(shapely.line_interpolate_point(route, ss))
        over = np.asarray(lidar(pts[:, 0], pts[:, 1]), float) - rail_top(L, ss)
        if len(ss) and np.isfinite(over).any() and np.nanmean(over) > TUNNEL_ROCK:
            out.append((float(a), float(b)))
    return out


def in_the_rock(L, rock, x, y):
    """(Which points lie in a rock tunnel's corridor: within TUNNEL_ACROSS of the route between TUNNEL_OUT before its
    start and after its end; the top of rail beside each, NaN for the others)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    inside, rail = np.zeros(len(x), bool), np.full(len(x), np.nan)
    if not rock or not len(x):
        return inside, rail
    route = shapely.LineString(np.asarray(L["path"], float)[:, :2])
    for a, b in rock:
        part = shapely.ops.substring(route, max(a - TUNNEL_OUT, 0.0), min(b + TUNNEL_OUT, route.length))
        x0, y0, x1, y1 = part.bounds
        k = np.flatnonzero((x >= x0 - TUNNEL_ACROSS) & (x <= x1 + TUNNEL_ACROSS) & (y >= y0 - TUNNEL_ACROSS) & (y <= y1 + TUNNEL_ACROSS))
        if not len(k):
            continue
        pts = shapely.points(x[k], y[k])
        s_ = shapely.line_locate_point(route, pts)
        ok = (shapely.distance(route, pts) < TUNNEL_ACROSS) & (s_ > a - TUNNEL_OUT) & (s_ < b + TUNNEL_OUT)
        inside[k[ok]] = True
        rail[k[ok]] = rail_top(L, s_[ok])
    return inside, rail


PORTAL_REACH = 15.0  # m past a rock tunnel's corridor, along the route and across it: a portal's wing walls


def portal_masonry(L, rock, inside, rail, x, y, z, area, is_wall):
    """in_the_rock's (inside, rail) with a portal's own masonry added: every corner, within PORTAL_REACH of a rock
    tunnel's corridor, of a wall-like survey area (is_wall(its id), `area` per corner) that stands TUNNEL_OVER or more
    over the rails at a corner inside the corridor. The survey has the Vyšehrad tunnel's north gate as one strip
    0.64 m across (line 17, area 1237): the arch's line across the road and track, and the wing wall along the
    sidewalk as a sliver from the pier, 197.22 m at s 11424.8, to a point on the ground 12 m on (193.15 m). Stood up
    as a wall its top fell with that line: seen from inside the tunnel a grey cone 4 m tall by the road. A gate is no
    ground, and nothing draws the portal's masonry yet: the whole strip lies at the rails' level (#771)."""
    x, y, z = np.asarray(x, float), np.asarray(y, float), np.asarray(z, float)
    area = np.asarray(area)
    with np.errstate(invalid="ignore"):
        high = inside & (z - rail >= TUNNEL_OVER)
    ids = [a for a in np.unique(area[high]).tolist() if is_wall(a)]
    more = np.isin(area, ids) & ~inside
    if not more.any():
        return inside, rail
    k = np.flatnonzero(more)
    route = shapely.LineString(np.asarray(L["path"], float)[:, :2])
    pts = shapely.points(x[k], y[k])
    s_ = shapely.line_locate_point(route, pts)
    near = shapely.distance(route, pts) < TUNNEL_ACROSS + PORTAL_REACH
    by = np.zeros(len(k), bool)
    for a, b in rock:
        by |= (s_ > a - TUNNEL_OUT - PORTAL_REACH) & (s_ < b + TUNNEL_OUT + PORTAL_REACH)
    k, s_ = k[near & by], s_[near & by]
    inside, rail = inside.copy(), rail.copy()
    inside[k] = True
    rail[k] = rail_top(L, s_)
    return inside, rail


def off_the_hill(z, rail):
    """(Heights z of survey corners in a rock tunnel's corridor with those TUNNEL_OVER or more over the rails beside
    them set to the rails' level, which ones). The lidar there is the hill over the tunnel, and the street surface and a
    wall's outline at the mouth rise with it: in the Vyšehrad tunnel's south mouth (line 17 s 11388.8, 1.9 m beside the
    axis) the survey's road stood 4.3 m over the track, a dark spike in the portal; the page leaves out only the terrain
    there (src/groundDraw.js attachGround), #771."""
    z, rail = np.asarray(z, float), np.asarray(rail, float)
    with np.errstate(invalid="ignore"):
        high = z - rail >= TUNNEL_OVER
    return np.where(high, rail, z), high


def bed_ends(tracks, outline, box=None):
    """Where a drawn track's line leaves the beds' outline on the ground: (n, 4) of (x, y, the track's unit direction
    out of the outline)."""
    ends = []
    if outline.is_empty:
        return np.zeros((0, 4))
    ring = outline.boundary
    shapely.prepare(outline)
    for tr in tracks:
        tr = np.asarray(tr, float)[:, :2]
        if len(tr) < 2:
            continue
        line = shapely.LineString(tr)
        if box is not None and not line.intersects(shapely.box(*box)):
            continue
        for h in shapely.get_parts(shapely.intersection(line, ring)).tolist():
            if h.geom_type != "Point" or (box is not None and not shapely.box(*box).contains(h)):
                continue
            d = line.project(h)
            a, b = line.interpolate(max(d - 0.5, 0)), line.interpolate(min(d + 0.5, line.length))
            t = np.array([b.x - a.x, b.y - a.y])
            n = np.hypot(*t)
            if n < 1e-6:
                continue
            t /= n
            for sgn in (1.0, -1.0):  # (the direction that leaves the outline)
                if not shapely.contains_xy(outline, h.x + sgn * t[0] * 0.6, h.y + sgn * t[1] * 0.6) and \
                        shapely.contains_xy(outline, h.x - sgn * t[0] * 0.6, h.y - sgn * t[1] * 0.6):
                    ends.append((h.x, h.y, sgn * t[0], sgn * t[1]))
    return np.array(ends, float).reshape(-1, 4)


def abutments(tracks, outline, bed_at, lidar, wall_lines_, box=None, log=None, decks=None):
    """The lines across a structure where a track's bed ends high over the ground: [(2, 3) arrays, z NaN], for the wall
    lines (wall_lines.of_lines reads their two sides). The survey has an abutment's wing walls along the ramp as wall
    lines and stops where the deck lands: at the Modřany viaduct (line 17 (-2393, -9247)) the ramp's side strips fell
    4.5 m in their last metre, the lidar's smear of the abutment's face (#763).
    - A bed's end (bed_ends) is an abutment's where the bed there stands BED_OVER or more over the lidar ABUT_AHEAD
      past it, on one of the line's bridges (`decks`, span_decks). Off them the lidar is no witness: where the beds
      stop for 7.5 m over an underpass the line has no span for (line 17 s 3088, (-1456, -9105)) the survey's tram
      area runs on at level 0, and two abutments' lines there pulled it down to the underpass's floor, a trench
      across the track at each (the rails 3.49 m over the first surface).
    - The face: the bed reaches a deck's end (#594) and overhangs the abutment (Modřany: by 1.3 m). Back from the end
      the lidar rises from the ground the deck leaves to the ramp's top within ABUT_BACK; the face is where it crosses
      the middle of the two. Where it does not rise as a wall's smear does, by wall_lines.SLOPE over a metre (an
      embankment's cone under the deck's end: Krejcárek, line 37 (3954, 380), 0.6 m a metre before and behind the
      bed's end; read as a face it made a wall of 0.8-2 m across the cone, 13 m² of steep faces), the face is the
      bed's end.
    - Ends within ABUT_JOIN are one abutment: its line through the faces' middle, square to the track.
    - Either way the line ends at a surveyed wall line's point within ABUT_SNAP of it along the track and ABUT_WING to
      the side that stands wall_lines.STEP or more over the ground the deck leaves (the wing wall's corner: at
      Modřany the survey's lines turn there by 0.5 m and run on along the street at its level), the nearest to the
      track; else at the first wall line across it; else at the beds' outline.
    tracks: [(n, 2)], outline: the beds' outline, bed_at(x, y) the bed's surface, lidar(x, y), wall_lines_: the survey's
    wall lines [(m, 3)] (wall_lines.source_lines)."""
    import wall_lines
    E = bed_ends(tracks, outline, box)
    if not len(E):
        return []
    ring = outline.boundary
    zb = np.asarray(bed_at(E[:, 0] - E[:, 2] * 0.3, E[:, 1] - E[:, 3] * 0.3), float)
    zg = np.nanmedian(np.stack([np.asarray(lidar(E[:, 0] + E[:, 2] * o, E[:, 1] + E[:, 3] * o), float) for o in ABUT_AHEAD]), 0)
    with np.errstate(invalid="ignore"):
        keep = np.isfinite(zb) & np.isfinite(zg) & (zb - zg >= BED_OVER)
    if decks is not None:
        keep &= shapely.contains_xy(decks, E[:, 0] + E[:, 2], E[:, 1] + E[:, 3])
    E, zg = E[keep], zg[keep]
    if not len(E):
        return []
    # (the face: back from the end, where the lidar crosses the middle between the ground ahead and its top behind)
    back = np.arange(ABUT_STEP, ABUT_BACK + 1e-9, ABUT_STEP)
    Zb = np.stack([np.asarray(lidar(E[:, 0] - E[:, 2] * o, E[:, 1] - E[:, 3] * o), float) for o in back], 1)
    face = np.zeros(len(E))
    for k in range(len(E)):
        if not np.isfinite(Zb[k]).any():
            continue
        top = np.nanmax(Zb[k])
        n1 = int(round(1.0 / ABUT_STEP))  # (a face: the raster rises as a smeared wall does, not as a bank)
        with np.errstate(invalid="ignore"):
            if top - zg[k] < wall_lines.STEP or not (Zb[k, n1:] - Zb[k, :-n1] >= wall_lines.SLOPE).any():
                continue
        over = np.flatnonzero(Zb[k] >= (top + zg[k]) / 2)
        i = int(over[0])
        if i == 0:
            face[k] = back[0] / 2
        else:  # (between the two readings either side of the middle)
            z0, z1 = Zb[k, i - 1], Zb[k, i]
            u = ((top + zg[k]) / 2 - z0) / (z1 - z0) if np.isfinite(z0) and z1 > z0 else 1.0
            face[k] = back[i - 1] + u * ABUT_STEP
    Fp = E[:, :2] - E[:, 2:4] * face[:, None]
    # (ends near each other: one abutment)
    left = list(range(len(E)))
    groups = []
    while left:
        g = [left.pop(0)]
        grew = True
        while grew:
            grew = False
            for k in left[:]:
                if min(np.hypot(E[k, 0] - E[j, 0], E[k, 1] - E[j, 1]) for j in g) <= ABUT_JOIN and \
                        E[k, 2] * E[g[0], 2] + E[k, 3] * E[g[0], 3] > 0.7:
                    g.append(k)
                    left.remove(k)
                    grew = True
        groups.append(g)
    src = [np.asarray(q, float) for q in wall_lines_ or []]
    A, B = wall_lines.segments(src)
    W = np.concatenate(src) if src else np.zeros((0, 3))
    out = []
    for g in groups:
        t = E[g, 2:4].mean(0)
        t /= max(np.hypot(*t), 1e-9)
        nrm = np.array([-t[1], t[0]])
        c = Fp[g].mean(0)
        off = (Fp[g] - c) @ nrm
        low = float(np.median(zg[g]))
        al, la = (W[:, :2] - c) @ t, (W[:, :2] - c) @ nrm
        with np.errstate(invalid="ignore"):
            wing = (np.abs(al) <= ABUT_SNAP) & ~(W[:, 2] < low + wall_lines.STEP)
        ends2, how = [], []
        for sgn, far in ((1.0, off.max()), (-1.0, off.min())):
            p0 = c + nrm * far  # (the outermost face's point on this side)
            m = wing & (sgn * (la - far) > 0.05) & (sgn * (la - far) <= ABUT_WING)
            if m.any():
                k = np.flatnonzero(m)[np.argmin(sgn * (la[m] - far))]
                ends2.append(W[k, :2].copy())
                how.append("wing")
                continue
            P, Q = p0[None, :] + sgn * nrm[None, :] * 0.05, p0[None, :] + sgn * nrm[None, :] * ABUT_WING
            tt, seg, _ = wall_lines._cross(P, Q, A[:, :2], B[:, :2])
            if seg[0] >= 0:
                reach = 0.05 + tt[0] * (ABUT_WING - 0.05)
                how.append("wall")
            else:  # (no wing wall: to the outline's edge, found a little behind the face: at a bed's end the face lies along it)
                pb = p0 - t * 0.3
                x = shapely.intersection(shapely.LineString([pb + sgn * nrm * 0.05, pb + sgn * nrm * ABUT_WING]), ring)
                ds = [float(np.hypot(q.x - pb[0], q.y - pb[1])) for q in shapely.get_parts(x).tolist() if q.geom_type == "Point"]
                reach = min(ds) if ds else 0.0
                how.append("outline")
            ends2.append(p0 + sgn * nrm * reach)
        if np.hypot(*(ends2[0] - ends2[1])) >= 1.0:
            out.append(np.array([[ends2[0][0], ends2[0][1], np.nan], [ends2[1][0], ends2[1][1], np.nan]]))
            if log:
                log(f"  abutment at ({c[0]:.1f}, {c[1]:.1f}): {len(g)} bed ends {np.round(face[g], 2).tolist()} m over the face, "
                    f"the ground {low:.2f}, ends at {how[0]} ({ends2[0][0]:.1f}, {ends2[0][1]:.1f}) and {how[1]} ({ends2[1][0]:.1f}, {ends2[1][1]:.1f})")
    return out


WALL_JOIN = 0.5  # m: a stretch's end this near another stretch is no free end: the walls meet there (a turn, an abutment's corner)


def off_the_deck(z, zl):
    """(Heights z of street corners under a span with those BED_OVER or more over the lidar zl set to it, which ones).
    The street surface follows the tracks onto a deck, so a level-0 street under the deck read the deck's level: the
    road under the Modřany viaduct, line 17 (-2428, -9241), area 7120: 205.3 m where the lidar has 197.6 m, a slab in
    the viaduct 1.04 m over the deck's underside (#761)."""
    z, zl = np.asarray(z, float), np.asarray(zl, float)
    with np.errstate(invalid="ignore"):
        low = z - zl >= BED_OVER
    return np.where(low, zl, z), low


def hold_at_walls(cx, cy, tx, ty, z, eligible, walls, deck=None, street=None):
    """Heights z of corners (cx, cy) with each eligible one within WALL_HOLD of a wall stretch (wall_lines.stretches)
    set to the ground of the side of the wall its triangle's centre (tx, ty) lies on: that side's level at the nearest
    point of the line plus its slope over the corner's distance from it. A corner on the line itself so takes the top
    in a face above the wall and the foot in one below it: two heights at one point, the weld's step, an upright face
    (#697). A corner past a stretch's free end is left; of the stretches near it a corner takes the nearest it is not
    past. An end within WALL_JOIN of another stretch is not free (walls meeting at a corner: the wedge outside it is
    past both, and stood as leaning faces between a wing wall's end and the abutment's line, #763).
    deck: corners that are a deck's own surface (a survey area kept at its own level on a span). A stretch across a
    structure (an abutment's line, `across`) does not hold them: on a short bridge the survey has the track's area at
    level 0 right across the deck, and pulled down to the ground the deck leaves it was a trench across the track
    1.5 m wide at either abutment (line 17 s 3088, (-1456, -9105): the rails 3.49 m over the first surface, #763).
    A stretch along a strip's outline (`out`: the side that is not the strip, wall_lines.strip_lines) gives a corner
    that side's level also where its triangle's centre lies on the strip's side past the stretch's end: the wedge
    outside the strip's corner, never the strip's own (#771). Beside the stretch a corner on the strip's side is the
    ground behind the strip and stands at the strip's level, as at any wall line: behind the top of the cutting's wall
    north of Ohrada (line 37 (3396, 4), a strip 0.3 m across) the ground between the road and the strip (#770).
    A side that is a slot (`sl`, `sr`, wall_lines.levels: the strip between the stretch's line and the next wall line,
    under the ground on both sides of the pair: a stairwell's two walls half a metre apart) holds nothing past the
    stretch's end: the slot ends there (a strip's own outline, `out`, has its wedge's rule above; between a terrace's
    foot line and top line the strip is level with the lower ground, and holding on past the end keeps the wall's
    end upright: Chotkova's, line 23 (-880.5, 719.1)). An end another stretch's end lies within WALL_JOIN of is none: the wall runs
    on there, cut at a turn (the low wall under the park by Krejcárek, line 37 (3916.0, 301.7): left at the joint, its
    corners stood as teeth of 0.7-0.9 m). A footpath passing the
    end of a cellar stairs' walls by line 23 (-2329.4, 571.3), one line surveyed at 271.18 m and the other at
    272.93 m, took the slot's 271.18 m in the wedge past the end, a trench 1.3 m deep and 0.5 m across in the path
    and the lawn (the lidar has 272.6 m; the end joins the top line, so it is no free end, #770).
    It does not hold a street's corners (`street`): a street has its own surface up to the strip, and line 9 alone has
    7.4 km of such stretches (1,014 of them, 637 under 5 m: parapets, edgings, low walls) whose raster levels would
    run through its sidewalks; the lidar's ground and the terrain have none and climbed the strip (#770).
    Returns (z, the corners held)."""
    held = np.zeros(len(cx), bool)
    if not walls or not eligible.any():
        return z, held
    A, B, ZL, ZR, GL, GR, END, ACROSS, OUT, TIP, SL, SR, SID, LAST = [], [], [], [], [], [], [], [], [], [], [], [], [], []
    wl = np.array([shapely.LineString(np.asarray(w["p"], float)[:, :2]) for w in walls], object)
    wtree = shapely.STRtree(wl)
    free = np.ones((len(walls), 2), bool)
    for e in (0, 1):
        ei, oi = wtree.query(shapely.points([w["p"][-e] for w in walls]), predicate="dwithin", distance=WALL_JOIN)
        free[ei[ei != oi], e] = False
    # (an end another stretch runs on from: its end within WALL_JOIN of one of another's)
    ends = np.array([w["p"][k][:2] for w in walls for k in (0, -1)], float)
    ai, bi = shapely.STRtree(shapely.points(ends)).query(shapely.points(ends), predicate="dwithin", distance=WALL_JOIN)
    runs_on = np.zeros(len(ends), bool)
    runs_on[ai[ai // 2 != bi // 2]] = True
    runs_on = runs_on.reshape(-1, 2)
    for w in walls:
        p = w["p"]
        n = len(p) - 1
        A.append(p[:-1])
        B.append(p[1:])
        for out, k in ((ZL, "zl"), (ZR, "zr"), (GL, "gl"), (GR, "gr")):
            v = w.get(k)
            v = np.zeros(n + 1) if v is None else np.asarray(v, float)
            out.append(np.column_stack([v[:-1], v[1:]]))
        for out, k in ((SL, "sl"), (SR, "sr")):
            v = w.get(k)
            v = np.zeros(n + 1, bool) if v is None else np.asarray(v, bool)
            out.append(v[:-1] | v[1:])
        SID.append(np.full(n, len(SID)))
        ACROSS.append(np.full(n, bool(w.get("across"))))
        OUT.append(np.full(n, {"l": 1, "r": -1}.get(w.get("out"), 0)))
        e = np.zeros((n, 2), bool)  # (a segment's end that is its stretch's free end)
        e[0, 0], e[-1, 1] = free[len(END)]
        END.append(e)
        e = np.zeros((n, 2), bool)  # (a segment's end that is its stretch's end, free or not)
        e[0, 0] = e[-1, 1] = True
        TIP.append(e)
        e = np.zeros((n, 2), bool)  # (a segment's end that is its stretch's end with no stretch running on from it)
        e[0, 0], e[-1, 1] = ~runs_on[len(LAST)]
        LAST.append(e)
    A, B, ZL, ZR, GL, GR, END, ACROSS, OUT, TIP, SL, SR, SID, LAST = (
        np.concatenate(v) for v in (A, B, ZL, ZR, GL, GR, END, ACROSS, OUT, TIP, SL, SR, SID, LAST))
    tree = shapely.STRtree(shapely.linestrings(np.stack([A, B], 1)))
    idx = np.flatnonzero(eligible)
    pi, si = tree.query(shapely.points(cx[idx], cy[idx]), predicate="dwithin", distance=WALL_HOLD)
    if deck is not None and len(pi):
        keep = ~(ACROSS[si] & np.asarray(deck, bool)[idx[pi]])
        pi, si = pi[keep], si[keep]
    if street is not None and len(pi):
        keep = ~((OUT[si] != 0) & np.asarray(street, bool)[idx[pi]])
        pi, si = pi[keep], si[keep]
    if not len(pi):
        return z, held
    P = np.column_stack([cx[idx[pi]], cy[idx[pi]]])
    v = B[si] - A[si]
    raw = ((P - A[si]) * v).sum(1) / np.maximum((v * v).sum(1), 1e-12)
    t = np.clip(raw, 0, 1)
    d = np.hypot(*(P - A[si] - t[:, None] * v).T)
    past = ((raw < -1e-9) & END[si, 0]) | ((raw > 1 + 1e-9) & END[si, 1])
    # (whether a corner lies past a stretch's end is its nearest segment of that stretch's to say: 1 m beyond the end it
    # is still within WALL_HOLD of the stretch's second segment, which has no end to be past)
    o = np.lexsort((d, SID[si], pi))
    lead = np.concatenate([[True], (pi[o][1:] != pi[o][:-1]) | (SID[si[o]][1:] != SID[si[o]][:-1])])
    near = o[lead][np.cumsum(lead) - 1]
    gtip = np.empty(len(pi), bool)
    gtip[o] = ((raw[near] < -1e-9) & LAST[si[near], 0]) | ((raw[near] > 1 + 1e-9) & LAST[si[near], 1])
    order = np.lexsort((d, past, pi))  # (per corner the nearest segment it is not past first)
    first = np.concatenate([[True], pi[order][1:] != pi[order][:-1]])
    k = order[first]
    # (a corner at or beyond its segment's end, at a bend or where two stretches meet: its triangle lies on one of the
    # walls there, and that one's side is the triangle's. Of the segments as near the corner (within WALL_JOIN of its
    # nearest) it takes the nearest to the triangle's centre that the centre is not beyond: read against the other's
    # line run on past its end, a triangle in the corner outside an abutment stood on the ramp's top, #763)
    C = np.column_stack([tx[idx[pi]], ty[idx[pi]]])
    rawc = ((C - A[si]) * v).sum(1) / np.maximum((v * v).sum(1), 1e-12)
    dc = np.hypot(*(C - A[si] - np.clip(rawc, 0, 1)[:, None] * v).T)
    dmin = np.full(len(idx), np.inf)
    np.minimum.at(dmin, pi, np.where(past, np.inf, d))
    order2 = np.lexsort((dc, (rawc < -1e-9) | (rawc > 1 + 1e-9), d > dmin[pi] + WALL_JOIN, past, pi))
    k2 = order2[np.concatenate([[True], pi[order2][1:] != pi[order2][:-1]])]
    k = np.where(((raw[k] < 1e-9) | (raw[k] > 1 - 1e-9)) & ~past[k], k2, k)
    c, s, t, d, raw, gtip = idx[pi[k]], si[k], t[k], d[k], raw[k], gtip[k]
    v = B[s] - A[s]
    left = v[:, 0] * (ty[c] - A[s, 1]) - v[:, 1] * (tx[c] - A[s, 0]) > 0
    rc = ((tx[c] - A[s, 0]) * v[:, 0] + (ty[c] - A[s, 1]) * v[:, 1]) / np.maximum((v * v).sum(1), 1e-12)
    left = np.where((OUT[s] != 0) & (((rc < 0) & TIP[s, 0]) | ((rc > 1) & TIP[s, 1])), OUT[s] > 0, left)

    def along(Q):
        return Q[s, 0] + (Q[s, 1] - Q[s, 0]) * t
    level = np.where(left, along(ZL) + along(GL) * d, along(ZR) + along(GR) * d)
    past = ((raw < -1e-9) & END[s, 0]) | ((raw > 1 + 1e-9) & END[s, 1])
    # (the strip to the next wall line ends with the stretch: past its end, by the triangle's centre or the corner)
    tip = gtip | ((np.minimum(rc, raw) < -1e-9) & LAST[s, 0]) | ((np.maximum(rc, raw) > 1 + 1e-9) & LAST[s, 1])
    ok = np.isfinite(level) & ~past & ~(tip & (OUT[s] == 0) & np.where(left, SL[s], SR[s]))
    z = z.copy()
    z[c[ok]] = level[ok]
    held[c[ok]] = True
    return z, held


def city_at(G, px, py):
    """The city mesh's height at points under the classes above the terrain (ground_partition's "under" triangles):
    its triangle's plane, NaN where none holds a point."""
    return city_sampler(G)(px, py)


def city_sampler(G):
    """city_at for many calls: the triangles' tree built once."""
    U = np.asarray(G["under"], int)
    if not len(U):
        return lambda px, py: np.full(len(px), np.nan)
    x, y, z, T = G["x"], G["y"], G["z"], G["T"][U]
    tri = np.stack([np.column_stack([x[T[:, k]], y[T[:, k]], z[T[:, k]]]) for k in range(3)], 1)
    tree = shapely.STRtree(shapely.polygons(tri[:, [0, 1, 2, 0], :2]))

    def at(px, py):
        out = np.full(len(px), np.nan)
        if len(px):
            pi, ti = tree.query(shapely.points(px, py), predicate="intersects")
            out[pi] = plane(tri[ti], px[pi], py[pi])
        return out
    return at


MEET = ("paved",)  # (survey classes whose plane meets the raised areas at their edge: meet_raised, #638)
MEET_STEP = 0.3  # m: a step to a raised area up to this is closed; a larger one stands (a terrace, a yard over a cellar)
MEET_FADE = 3.0  # m: the shift fades to none this far in from the edge
MEET_NEAR = 8  # edge corners weighed for each corner


def meet_raised(sc, x, y, zs):
    """The MEET classes' corners (a paved yard, a forecourt) shifted to meet the raised areas (RAISED: a sidewalk, an
    island) where they share a corner: at each such corner the step to the raised one's height when within MEET_STEP,
    pinned (no shift) where a corner is shared with any other survey class; every MEET corner within MEET_FADE of those edge
    corners takes their inverse-distance-weighted shift, faded linearly to none at MEET_FADE. All MEET corners together,
    so two yards sharing an edge shift alike. Returns (zs, per corner the shift, NaN where none applied)."""
    from scipy.spatial import cKDTree
    shift = np.full(len(zs), np.nan)
    own = np.flatnonzero(np.isin(sc, MEET) & np.isfinite(zs))
    if not len(own):
        return zs, shift
    key = np.round(x * Q).astype(np.int64) * 10_000_000_000 + np.round(y * Q).astype(np.int64)
    oth = np.flatnonzero(~np.isin(sc, MEET) & np.isfinite(zs))
    ko = np.unique(key[oth])
    if not len(ko):
        return zs, shift
    up = oth[np.isin(sc[oth], list(RAISED))]
    ku, fu = np.unique(key[up], return_index=True)
    j = np.clip(np.searchsorted(ko, key[own]), 0, len(ko) - 1)
    edge = own[ko[j] == key[own]]
    dl = np.zeros(len(edge))
    if len(ku):
        ju = np.clip(np.searchsorted(ku, key[edge]), 0, len(ku) - 1)
        at = ku[ju] == key[edge]
        dl[at] = zs[up[fu[ju[at]]]] - zs[edge[at]]
    dl[np.abs(dl) > MEET_STEP] = 0.0
    if not len(edge) or not (dl != 0).any():
        return zs, shift
    d, i = cKDTree(np.column_stack([x[edge], y[edge]])).query(np.column_stack([x[own], y[own]]), k=min(MEET_NEAR, len(edge)),
                                                              distance_upper_bound=MEET_FADE)
    d, i = d.reshape(len(own), -1), i.reshape(len(own), -1)
    ok = np.isfinite(d)
    w = np.where(ok, 1.0 / np.maximum(d, 1e-3) ** 2, 0.0)
    dv = np.where(ok, dl[np.minimum(i, len(edge) - 1)], 0.0)
    has = ok.any(1)
    s = np.zeros(len(own))
    s[has] = (w[has] * dv[has]).sum(1) / w[has].sum(1) * np.clip(1 - d[has, 0] / MEET_FADE, 0, 1)
    zs = zs.copy()
    zs[own] += s
    shift[own[has]] = s[has]
    return zs, shift


WALL_LATTICE = 1.0  # m: a survey wall's faces cut to this, their corners between its sides (across_outline, #653)
WALL_SNAP = 0.3  # m: a street corner on a wall's or stairs' outline this near its height there takes it (#653)
WALL_ON = 0.01  # m: a corner this near the outline lies on it (the faces are noded on it)
WALL_CLASSES = ("wall", "stairs")


def _sides(ring_segs, x, y):
    """Per point inside a survey area: (z1, d1, z2, d2), the outline's height at the nearest point on it and its distance,
    and the same of the nearest point on its other side (the direction from the point turned past 90 degrees; d2 inf
    where there is none). ring_segs: (n, 2, 3) the outline's edges."""
    a, b = ring_segs[:, 0], ring_segs[:, 1]
    e = b[:, :2] - a[:, :2]
    l2 = np.maximum((e ** 2).sum(1), 1e-12)
    z1, d1, z2, d2 = (np.full(len(x), np.nan) for _ in range(4))
    for k in range(0, len(x), 2000):
        px, py = x[k:k + 2000, None], y[k:k + 2000, None]
        t = np.clip(((px - a[:, 0]) * e[:, 0] + (py - a[:, 1]) * e[:, 1]) / l2, 0, 1)
        qx, qy = a[:, 0] + e[:, 0] * t, a[:, 1] + e[:, 1] * t
        qz = a[:, 2] + (b[:, 2] - a[:, 2]) * t
        d = np.hypot(qx - px, qy - py)
        r = np.arange(len(px))
        j = d.argmin(1)
        ux, uy = qx[r, j] - px[:, 0], qy[r, j] - py[:, 0]
        back = (qx - px) * ux[:, None] + (qy - py) * uy[:, None] < 0
        d2m = np.where(back, d, np.inf)
        j2 = d2m.argmin(1)
        z1[k:k + 2000], d1[k:k + 2000], z2[k:k + 2000], d2[k:k + 2000] = qz[r, j], d[r, j], qz[r, j2], d2m[r, j2]
    return z1, d1, z2, d2


def across_outline(ring_segs, x, y):
    """Heights of points inside a survey area between its sides: the outline's height at the nearest point on it, and at
    the nearest point on its other side (the direction from the point turned past 90 degrees), weighted by the other's
    distance. On the outline, its height. A battered wall's strip, 0.9 m across and 35 m long with 3 and 4 outline points
    along its foot and its top (line 37 (3915, 316), area 1444), triangulated on its outline alone folded into a W 2 m
    tall (#653); between its sides it runs straight across. ring_segs: (n, 2, 3) the outline's edges."""
    z1, d1, z2, d2 = _sides(ring_segs, x, y)
    with np.errstate(invalid="ignore"):  # (no other side: inf, its own height taken)
        return np.where(np.isfinite(d2) & (d1 > 1e-6), (z1 * d2 + z2 * d1) / np.maximum(d1 + d2, 1e-12), z1)


WALL_FACE = 0.7  # m: a survey wall area whose two sides part by this or more stands upright (wall_lines.STEP: a wall)
WALL_WIDE = 2.5  # m: across more than this it is no wall's thickness: a bastion's or an earthwork's battered face (95 % of
# lines 23's and 37's wall areas are under 2.1 m across, twice their area over their outline's length)
WALL_IN = 0.02  # m: a wall's corner is seen from this far inside its own triangle (on the outline it has no other side)


def wall_width(a):
    """How far across a survey area is: twice its area over its outline's length (a strip's width)."""
    g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
    return 2 * g.area / g.length if g.length > 0 else 0.0


SIDES_STEP = 2.0  # m between the points the outline is looked across from
SIDES_SHARE = 0.5  # of the outline's length with its other side WALL_FACE or more off it: the strip is a wall's face


def two_sided(a):
    """Whether a survey area is a wall's face in plan, its foot's line one side of it and its top's the other: from
    SIDES_SHARE or more of its outline the other side across it, within WALL_WIDE, stands WALL_FACE or more higher or
    lower. Under Letná (line 17 (26..317, 806), paved area 4166: 0.44 m across and 290 m long, a wall of 2-3.5 m along
    the road) the top's line steps 0.6 m at a time and the two lines join gradually at the ends: no two neighbouring
    points climb a wall (climbs), and its outline's triangles stood as teeth 10 m wide (#765)."""
    segs = ring_segments(a)
    if not len(segs):
        return False
    g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
    if not g.is_valid or g.is_empty:
        return False
    e = segs[:, 1, :2] - segs[:, 0, :2]
    L = np.hypot(e[:, 0], e[:, 1])
    xs, ys, ws = [], [], []
    for (p, _), v, l in zip(segs, e, L):
        k = max(1, int(math.ceil(l / SIDES_STEP)))
        t = (np.arange(k) + 0.5) / k
        n = np.array([-v[1], v[0]]) / max(l, 1e-9)
        for sgn in (1.0, -1.0):
            xs.append(p[0] + v[0] * t + sgn * n[0] * WALL_IN)
            ys.append(p[1] + v[1] * t + sgn * n[1] * WALL_IN)
            ws.append(np.full(k, l / k))
    x, y, w = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws)
    inside = shapely.contains_xy(g, x, y)
    if not inside.any():
        return False
    z1, d1, z2, d2 = _sides(segs, x[inside], y[inside])
    with np.errstate(invalid="ignore"):
        face = np.isfinite(d2) & (np.abs(z1 - z2) >= WALL_FACE) & (d1 + d2 <= WALL_WIDE)
    return float(w[inside][face].sum()) >= SIDES_SHARE * float(L.sum())


def wall_like(a):
    """Whether a survey area takes a wall's heights (wall_face): a wall; or a paved strip off the lidar, a wall's
    thickness across (WALL_WIDE), whose outline climbs a wall (climbs()) or has a wall's foot and top as its two sides
    (two_sided()). 46-128 paved areas a line are such strips
    under 1 m across, 6-35 more up to 2.5 m (parapets and low walls along paths: line 17 area 4189 at (1194, 2409),
    line 23 area 956 at (-1117, 806)): their foot's side and their top's triangulated to a leaning sheet, 0.03-0.17 ha
    a line steeper than 1:1 (#697)."""
    if a["c"] == "wall":
        return True
    return a["c"] == "paved" and not a.get("g") and wall_width(a) <= WALL_WIDE and (climbs(a) or two_sided(a))


def wall_face(ring_segs, x, y, tx, ty):
    """Heights of a survey wall area's corners (x, y), each in a triangle with centre (tx, ty), and which of them were
    lifted off the outline: (z, lifted). Where the area's two sides there part by WALL_FACE or more it is a retaining
    wall: its top is level at the higher side's height right across, and a corner on the lower side's outline stands at
    the top too (`lifted`: the weld keeps it apart from the ground at its foot, an upright face). Below WALL_FACE, and
    where it is over WALL_WIDE across there (and for a whole area that wide, wall_width: the build), as across_outline:
    the bastion at Strahov (line 23, area 860: 16.5 m up over 5 m across, 3.7 m as a whole) is a battered face, and level
    across at its top it moved 4,000 corners by up to 16.5 m. Chotkova's road wall (line 23, area 842: its foot's side at 205.3 m, 1.7 m from its top's at 208.5)
    leaned as a ramp between its sides where a stone wall stands with a footpath on its top (the user's photo,
    2026-11-19, #697)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    vx, vy = np.asarray(tx, float) - x, np.asarray(ty, float) - y
    n = np.maximum(np.hypot(vx, vy), 1e-9)
    step = np.minimum(WALL_IN, n / 2)
    z1, d1, z2, d2 = _sides(ring_segs, x + vx / n * step, y + vy / n * step)
    _, d0, _, _ = _sides(ring_segs, x, y)
    with np.errstate(invalid="ignore"):
        between = np.where(np.isfinite(d2) & (d0 > 1e-6), (z1 * d2 + z2 * d1) / np.maximum(d1 + d2, 1e-12), z1)
        face = np.isfinite(d2) & (np.abs(z1 - z2) >= WALL_FACE) & (d1 + d2 <= WALL_WIDE)
        z = np.where(face, np.fmax(z1, z2), between)
        lifted = face & (d0 <= WALL_ON) & (z2 > z1)
    return z, lifted


LOW_WALL = 0.1  # m: a wall's corner this far over the ground at its point stands apart from it (a kerb's step is STEP)


def standing(cx, cy, z, wall, street):
    """Which wall corners (`wall`, of all corners (cx, cy) with heights z) stand LOW_WALL or more over the lowest
    street corner (`street`: one on a street's own surface) at their point: the weld keeps them apart from the street
    there, an upright side. Not from the lidar's ground or the terrain: at a wall those read the raster's smear, and
    welded to the wall's top they are right; kept apart, the bank behind the wall under Letná (line 17 (91, 805.84))
    stood 1.4 m under the wall's top in a trench (#776). A wall under WALL_FACE
    took its heights between its two sides and was welded with whatever it shared a point with: the quay's low wall at
    line 17 (-755.8, -1827), area 1086 (0.18 m across, its outline 0.5 m over the ground at the median), lay as a flat
    strip. The user, 2026-11-20, on pictures of alpha-4, which drew such walls as low boxes, against main (#696):
    upright, by the survey's own heights."""
    out = np.zeros(len(cx), bool)
    wall = np.asarray(wall, bool)
    z = np.asarray(z, float)
    if not wall.any():
        return out
    key = np.round(np.asarray(cx) * Q).astype(np.int64) * 10_000_000_000 + np.round(np.asarray(cy) * Q).astype(np.int64)
    oth = np.flatnonzero(~wall & np.asarray(street, bool) & np.isfinite(z))
    if not len(oth):
        return out
    ko, inv = np.unique(key[oth], return_inverse=True)
    low = np.full(len(ko), np.inf)
    np.minimum.at(low, inv, z[oth])
    w = np.flatnonzero(wall & np.isfinite(z))
    j = np.clip(np.searchsorted(ko, key[w]), 0, len(ko) - 1)
    hit = ko[j] == key[w]
    out[w[hit]] = z[w[hit]] - low[j[hit]] >= LOW_WALL
    return out


THIN_WALL = 1.0  # m: a survey wall area this far across or less is a wall's thickness in plan (wall_lines.STRIP)
ROAD_GRADE = 0.2  # rise over run: a road's own grade towards a wall is held to this (a garage ramp's 14-17 %); a
# steeper reading is another wall's smear, and the surface runs level instead
SMEAR_MIN = 0.05  # m: a road's corner by a wall this near its surface carried on from past the smear is left as it is
SMEAR_TRUST = 1.0  # m: the road's surface out there this far off IPR is not the ground's (a deck's level over it)


def thin_walls(D):
    """The outline edges of the survey's level-0 wall areas up to THIN_WALL across (wall_width): (n, 2, 2)."""
    segs = []
    for a in D["areas"]:
        if a.get("c") != "wall" or a.get("l", 0) != 0 or len(a["r"]) < 3 or wall_width(a) > THIN_WALL:
            continue
        for r in [a["r"]] + a.get("h", []):
            for i in range(len(r)):
                p, q = r[i], r[(i + 1) % len(r)]
                if (p[0], p[1]) != (q[0], q[1]):
                    segs.append([p[:2], q[:2]])
    return np.asarray(segs, float).reshape(-1, 2, 2)


def kerb_walls(D, road_at, lidar):
    """The survey's sidewalks' kerb edges that are a wall's top (street_profile.wall_tops: their own height stands
    over the road beyond them, road_at(x, y) its surface, and is the ground's inside the sidewalk, lidar(x, y)), as
    edges (n, 2, 2): the survey has no wall area along such
    an edge, and the road at its foot carries the raster's smear of the wall as at any wall's (off_the_smear). The
    garage ramp's side along the sidewalk on Na Vápence, line 37 (3868, -19): the ramp's edge 258.84-259.35 m where
    the ramp lies at 257.9 m, a spike in the corner by the door (#779)."""
    import street_profile
    segs = []
    for q, n, own in street_profile.kerb_edges(D)[0]:
        if not np.isfinite(own).any():
            continue
        top, e = street_profile.wall_tops(q, n, own, road_at(*(q - n * 0.5).T), lidar(*(q + n * street_profile.SW_KERB_SMEAR).T))
        if top.any():
            segs.append(e[:, :, :2])
    return np.concatenate(segs) if segs else np.zeros((0, 2, 2))


def off_the_smear(walls, x, y, tx, ty, z, own, lidar=None):
    """Heights z of a road's corners (x, y), each in a triangle with centre (tx, ty), with those within WALL_HOLD of a
    thin wall's outline (walls: thin_walls) set to the road's own surface WALL_HOLD out from the outline on their side
    (own(px, py), NaN where the road has none there: the corner is left), run on to the corner at the surface's grade
    between there and twice as far out (up to ROAD_GRADE; level where it has no surface that far, or a steeper one),
    where that is SMEAR_MIN or more off its height: (z, which ones). (Whether the raster steps across the wall is not
    asked: read past the wall's end beside another wall, it showed none.) Where the surface out there lies SMEAR_TRUST
    or more off IPR (lidar(px, py)) the corner is left: the street surface follows the tracks onto a deck, and by the
    Modřany viaduct's abutment, line 17 (-2385, -9250), a road's corner beside the ramp's wall read the deck's level
    1.5 m out, 5.2 m over it. In a corner of two walls the point out from one lies in the other's
    smear: it is moved out to WALL_HOLD from that one too, and the surface runs level from there. Of the edges near a
    corner it takes the nearest whose point out its triangle's centre sees without a wall between: at a wall's end
    the short edge across it points through the wall (the road behind the door's wall, at the wall's end, read the
    pit: 259.38 m for 260.9).
    The generated road surface follows IPR, whose 1 m raster spreads a wall's face over 1-1.5 m, and nothing held it:
    at the foot of the wall over the garage ramp's door on Na Vápence, line 37 (3871, -18), wall area 1419 (0.26 m
    across, its top alone surveyed), the ramp rose from 258.00 m 1 m before the wall to 258.76 m at it, a toothed
    foot, and the road behind the wall fell from 260.91 to 259.32 m towards it (#779). A sidewalk's edge on a wall is
    held by the street surface itself (street_profile.sidewalks, #653)."""
    z = np.array(z, float)
    held = np.zeros(len(z), bool)
    s = np.flatnonzero(np.isfinite(z))
    if not len(walls) or not len(s):
        return z, held
    a, b = walls[:, 0], walls[:, 1]
    tree = shapely.STRtree(shapely.linestrings(walls))
    pi, si = tree.query(shapely.points(x[s], y[s]), predicate="dwithin", distance=WALL_HOLD)
    if not len(pi):
        return z, held
    e = b[si] - a[si]
    l2 = np.maximum((e ** 2).sum(1), 1e-12)
    t = np.clip(((x[s][pi] - a[si, 0]) * e[:, 0] + (y[s][pi] - a[si, 1]) * e[:, 1]) / l2, 0, 1)
    fx, fy = a[si, 0] + e[:, 0] * t, a[si, 1] + e[:, 1] * t
    d = np.hypot(x[s][pi] - fx, y[s][pi] - fy)
    c = s[pi]
    nx, ny = -e[:, 1] / np.sqrt(l2), e[:, 0] / np.sqrt(l2)
    side = np.where((tx[c] - fx) * nx + (ty[c] - fy) * ny >= 0, 1.0, -1.0)  # (the corner's triangle's side of the edge)
    qx, qy = fx + side * nx * WALL_HOLD, fy + side * ny * WALL_HOLD
    moved = np.zeros(len(c), bool)
    for _ in range(2):
        (k, j), dj = tree.query_nearest(shapely.points(qx, qy), max_distance=WALL_HOLD - 0.05, return_distance=True, all_matches=False)
        k, j, dj = k[dj > 1e-6], j[dj > 1e-6], dj[dj > 1e-6]
        if not len(k):
            break
        ej = b[j] - a[j]
        tj = np.clip(((qx[k] - a[j, 0]) * ej[:, 0] + (qy[k] - a[j, 1]) * ej[:, 1]) / np.maximum((ej ** 2).sum(1), 1e-12), 0, 1)
        gx, gy = a[j, 0] + ej[:, 0] * tj, a[j, 1] + ej[:, 1] * tj
        qx[k], qy[k] = gx + (qx[k] - gx) / dj * WALL_HOLD, gy + (qy[k] - gy) / dj * WALL_HOLD
        moved[k] = True
    sees = np.ones(len(c), bool)
    li, _ = tree.query(shapely.linestrings(np.stack([np.column_stack([tx[c], ty[c]]), np.column_stack([qx, qy])], 1)),
                       predicate="intersects")
    sees[np.unique(li)] = False
    o = np.lexsort((d, ~sees, pi))  # (per corner, its nearest edge with a clear point out)
    o = o[np.r_[True, pi[o][1:] != pi[o][:-1]]]
    o = o[sees[o]]
    c, fx, fy, nx, ny, side, d, qx, qy, moved = (v[o] for v in (c, fx, fy, nx, ny, side, d, qx, qy, moved))
    zq = np.asarray(own(qx, qy), float)
    with np.errstate(invalid="ignore"):
        g = (zq - np.asarray(own(fx + side * nx * 2 * WALL_HOLD, fy + side * ny * 2 * WALL_HOLD), float)) / WALL_HOLD
        g = np.where((np.abs(g) <= ROAD_GRADE) & ~moved, g, 0.0)
    zn = zq + g * (WALL_HOLD - d)
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(zn) & (np.abs(zn - z[c]) >= SMEAR_MIN)
        if lidar is not None:
            ok &= np.abs(zq - np.asarray(lidar(qx, qy), float)) < SMEAR_TRUST
    z[c[ok]] = zn[ok]
    held[c[ok]] = True
    return z, held


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
    a, b, reach = [], [], []
    for ar in D["areas"]:
        if ar["c"] not in WALL_CLASSES or ar.get("l", 0) != 0:
            continue
        for r in [ar["r"]] + ar.get("h", []):
            for i in range(len(r)):
                p, q = r[i], r[(i + 1) % len(r)]
                if p[2] is not None and q[2] is not None:
                    a.append(p[:3])
                    b.append(q[:3])
                    # (a wall's top LOW_WALL or more over the street is a low wall standing, not the street's edge: by
                    # the cheek walls at Krejcárek's ramp, line 37 s 2963-2978, the platform climbed to their tops, #776)
                    reach.append(LOW_WALL if ar["c"] == "wall" else WALL_SNAP)
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
    up = zw - z[s][pi]
    d = np.abs(up)
    lim = np.asarray(reach, float)[si]
    o = np.lexsort((d, pi))  # (per point, its nearest height first)
    pi, zw, up, lim = pi[o], zw[o], up[o], lim[o]
    first = np.r_[True, pi[1:] != pi[:-1]]
    pi, zw, up, lim = pi[first], zw[first], up[first], lim[first]
    near = (up >= -WALL_SNAP) & (up <= lim)  # (down to a wall's foot as before; up only to what is no wall standing)
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
def weld(cx, cy, zc, prio, kind, label=None, zown=None, held=None, apart=None):
    """The corners' heights welded at each point: (each corner's height, the steps kept by pair, the points). A point takes
    its top-priority corners' height, whatever their order (#664: it took the first top corner's, the order of the
    partition's pieces; drawing the survey's walls reordered them and moved line 22's corner at (-1114, -537), shared by
    roads #16 and #23 by a bridge's track, 193.49 and 193.32 m, by 0.17 m):
    - top corners within 2 TIE_STEP of each other: the middle of their range;
    - the survey's top corners farther apart: a step the survey recorded, each corner takes the nearer end of the range;
      and so the top corners a surveyed wall line holds at its two sides' levels (`held`, hold_at_walls), whatever their
      class: the terrain's two sides of a wall took the middle, and the wall stood as two ramps (#697);
    - a corner below the top keeps its own height where it differs by more than its pair's STEP (a kerb, a wall, the
      water); the pair is judged against the lowest top corner's kind;
    - a lidar corner (`label` "lidar") that yielded to its rank (YIELD) keeps its own where its area's outline there
      (`zown`) stands over LIDAR_APART off; one a wall line holds (`held`), where its held height does: the paved
      ground at the foot of the cutting's wall north of Ohrada (line 37 (3389.13, -10.60)) is one area with the ground
      behind the wall's top, its outline there at 248.44 m, and its corner on the wall's line, held at the foot's
      244.59 m, took the top strip's 248.03 m: a spike on the ledge every 2 m of wall (#770). Of any rank: the lawn
      beside the wing wall at the Vyšehrad tunnel's north mouth (line 17 (-724.65, -2546.51), a paved strip 0.86 m
      across climbing to 197.88 m), held at 193.68 m, climbed the wall to its top, a cone 4 m tall by the road (#771).
    - corners `apart` (a wall area's, lifted to its top on its foot's outline: wall_face) are welded among themselves
      only, and the others at their point without them: the wall's face stands on the ground at its foot.
    `label`: what gave each corner its height (default `kind`), for the report and the lidar's rule."""
    key = np.round(cx * Q).astype(np.int64) * 10_000_000_000 + np.round(cy * Q).astype(np.int64)
    if apart is not None:
        key = key * 2 + apart
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
    other = ~np.isin(kind[tops], ("survey", "raised"))
    if held is not None:
        other &= ~held[tops]
    not_sv[inv[tops[other]]] = True
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
            if held is not None:  # (whatever the rank of what it yielded to: a lawn at a paved strip's foot)
                apart |= (label == "lidar") & ~is_top & held & (np.abs(zc - target) > LIDAR_APART)
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


def build(ln, mesh=None, threads=8, log=print, within=None):
    """The ground of line ln; within: of a box (x0, y0, x1, y1) of it only (a place's, tools/ground_place.py, #757), and
    then also each corner's point, height and what gave it ("corners")."""
    import bed_surface
    import ground_partition as gp
    from city_terrain import peak_gb
    log0 = log

    def log(msg):  # (each step with the peak memory so far: lines 22 and 17 hold 9 M terrain triangles, 21 GB)
        log0(f"{msg} (peak {peak_gb():.1f} GB)")
    t0 = time.time()
    pieces, prep, _ = gp.partition(ln, mesh, threads, geometry=True, within=within)
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
    streets = Streets(ln)
    under_at = city_sampler(G)
    n_bent = 0
    # (the walls the survey has as lines, where the ground steps across them: their lines among the faces' lines, so
    # corners lie on them, #697)
    import wall_lines
    # (and across a structure where a bed ends high over the ground: the abutment the survey's wing walls stop at, #763)
    # (a street over a passage is the ground there, not the passage's floor the raster shows: covers, #783)
    import covers
    lidar_raw = wall_lines.ipr_lidar()
    cover = covers.Covers(D, lidar_raw, box.bounds, covers.tunnel_ways(box.bounds))
    lidar_w = cover.over(lidar_raw)
    log(f"  {len(cover.places)} covers over passages, the raster cut out under {sum(q['cut m2'] for q in cover.places):.0f} m2")
    abut = abutments([np.asarray(t["p"], float)[:, :2] for t in L.get("tracks") or [] if len(t.get("p") or []) > 1], outline,
                     lambda px, py: beds.surface_at(px, py, BED_REACH), lidar_w,
                     wall_lines.source_lines(ln, box=box.bounds), box.bounds, log, span_decks(L) or shapely.Polygon())
    walls = wall_stretches = wall_lines.stretches(ln, box=box.bounds, lidar=lidar_w, extra=abut)
    log(f"  {len(abut)} abutment lines, {len(walls)} wall stretches")
    for w in walls:
        g = shapely.LineString(w["p"]).intersection(box)
        if not g.is_empty:
            lines.append(g)
    by_walls = shapely.union_all([shapely.LineString(w["p"]).buffer(SURVEY_LATTICE) for w in walls]) if walls else None
    for k, q in enumerate(pieces["survey"]):
        lines.append(q["g"].boundary)
        owners.append(("survey", k, q["g"]))
        # (a street or a ground on the lidar has a surface between its outline's points: lattice lines inside it, so its
        # faces are cut to SURVEY_LATTICE m and their corners lie on that surface, #632; and finer where the surface
        # bends inside a cell, #697)
        on_lidar_ = bool((D.get("areas") or [{}] * (q["area"] + 1))[q["area"]].get("g"))
        if q["c"] in STREETS_ROAD | STREETS_WALK or on_lidar_:
            g = lattice(q["g"])
            if g is not None and not g.is_empty:
                lines.append(g)
            if on_lidar_:
                # (the lidar's ground is cut finer only by a wall: between Chotkova's terraces the fine cells carry the
                # levels the walls hold; on an open bank they drew the raster's bumps, a paved bank creased where it was
                # smooth, line 37 s 2348 (3397, 3), and the seams of 10 cm rose 441 -> 536 on that line, #770)
                g = bends(q["g"], under_at) if by_walls is not None and by_walls.intersects(q["g"]) else None
                if g is not None and not g.is_empty:
                    g = g.intersection(by_walls)
            else:
                kd = "road" if q["c"] in STREETS_ROAD else "sidewalk"
                g = bends(q["g"], lambda px, py, kd=kd: streets.at(kd, px, py))
            if g is not None and not g.is_empty:
                lines.append(g)
                n_bent += 1
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

    log(f"  {len(lines):,} lines, {int(touch.sum()):,} whole triangles noded with them, {n_bent} street and lidar pieces "
        f"cut finer where their surface bends, {time.time() - t1:.0f} s")
    (e0, e1), (n0, n1) = tile_index([bx0, bx1], [by0, by1])
    rects = [(max(bx0, b[0]), max(by0, b[1]), min(bx1, b[2]), min(by1, b[3]))
             for b in (tile_box(e, n) for e in range(int(e0), int(e1) + 1) for n in range(int(n0), int(n1) + 1))]
    rects = [r for r in rects if r[2] > r[0] and r[3] > r[1]]  # (a box ending on the grid: no square past its edge, #757)
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
    # terrain: the parent triangle's plane
    m = corner_cls == "terrain"
    par = np.array([owners[o][1] for o in owner])[corner_face[m]]
    tri3 = np.stack([np.column_stack([x[T[par, k]], y[T[par, k]], z[T[par, k]]]) for k in range(3)], 1)
    zc[m], prio[m], kind[m] = np.fmax(plane(tri3, cx[m], cy[m]), cover.at(cx[m], cy[m])), 3.0, "terrain"
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
    zc[m] = np.fmax(np.where(np.isfinite(zg), zg, zp), cover.at(cx[m], cy[m]))
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
    on_span = np.zeros(len(m), bool)
    deck = span_decks(L)
    if deck is not None:
        shapely.prepare(deck)
        on_span = shapely.contains_xy(deck, cx[m], cy[m])
    # (but an area whose outline climbs a wall: on two levels, its own outline is no surface, climbs(), #761)
    two_levels = {a: climbs(D["areas"][a]) for a in np.unique(sa[on_span]).tolist()}
    under_span = on_span & np.array([two_levels.get(a, False) for a in sa.tolist()], bool)
    on_span &= ~under_span
    # (a terrace keeps its own outline's surface, and so does a footpath that touches one, #663)
    lidar_ = lidar_w
    raised = terraces(D, np.unique(sa).tolist(), lidar_)
    on_terrace = np.isin(sa, sorted(raised | beside(D, np.unique(sa[np.isin(sc, list(STREETS_WALK))]).tolist(), raised, lidar_)))
    for kd, cls in (("road", STREETS_ROAD), ("sidewalk", STREETS_WALK)):
        mm = np.isin(sc, list(cls)) & ~on_span & ~on_terrace
        if mm.any():
            zs[mm] = streets.at(kd, cx[m][mm], cy[m][mm])
    # (a road beside a thin wall keeps its own surface from where the raster's smear of the wall ends: off_the_smear, #779)
    tw = np.concatenate([thin_walls(D), kerb_walls(D, lambda px, py: streets.at("road", px, py), lidar_)])
    mm = np.isin(sc, list(STREETS_ROAD)) & ~on_span & ~on_terrace
    n_smear = 0
    if len(tw) and mm.any():
        c3 = fc[m[mm] // 3].mean(1)
        zs[mm], off = off_the_smear(tw, cx[m][mm], cy[m][mm], c3[:, 0], c3[:, 1], zs[mm],
                                    lambda px, py: streets.at("road", px, py), lidar_)
        n_smear = int(off.sum())
    # (a tree pit or a small bed in a sidewalk lies flush with it, on the sidewalk's street surface: pits, #696)
    in_pit = np.isnan(zs) & ~on_terrace & ~on_span & np.isin(sa, sorted(pits(D, np.unique(sa).tolist())))
    if in_pit.any():
        zs[in_pit] = streets.at("sidewalk", cx[m][in_pit], cy[m][in_pit])
    # (such an area's part under the deck lies on the lidar, not on the deck's level the street surface has there:
    # off_the_deck, #761)
    n_under = 0
    if under_span.any():
        k = np.flatnonzero(under_span & np.isfinite(zs))
        zs[k], low = off_the_deck(zs[k], lidar_(cx[m][k], cy[m][k]))
        n_under = int(low.sum())
    # (a lawn, a yard, a railway yard on the lidar ground (`g`, tools/zps_inside.py) has surveyed heights on its outline
    # only, and the page laid it on the lidar inside (src/terrain.js DtmSurface, #444): here the city mesh's, its outline
    # too, so it meets the terrain beside it. Its outline on a slope stood up to 5.5 m under the terrain, a wall, and a
    # hillside of them terraced: line 37 s 3472, area 2705)
    need = np.isnan(zs)
    on_lidar = need & np.array([bool(D["areas"][a].get("g")) for a in sa.tolist()], bool)
    on_lidar &= ~on_terrace
    n_cover = 0
    if on_lidar.any():
        zg = city_at(G, cx[m][on_lidar], cy[m][on_lidar])
        zo = cover.at(cx[m][on_lidar], cy[m][on_lidar])
        with np.errstate(invalid="ignore"):
            n_cover = int((zo > zg).sum())
        zs[on_lidar] = np.fmax(zg, zo)
    need = np.isnan(zs)
    lifted = np.zeros(len(m), bool)
    is_wall = np.zeros(len(m), bool)
    for a in np.unique(sa[need]).tolist():
        mm = need & (sa == a)
        segs = ring_segments(D["areas"][a]) if wall_like(D["areas"][a]) else None
        if segs is not None and len(segs) and wall_width(D["areas"][a]) > WALL_WIDE:  # (a battered face, #653)
            zs[mm] = across_outline(segs, cx[m][mm], cy[m][mm])
        elif segs is not None and len(segs):  # (a wall: between its sides, #653; upright where they part, #697)
            c3 = fc[m[mm] // 3].mean(1)
            zs[mm], lifted[mm] = wall_face(segs, cx[m][mm], cy[m][mm], c3[:, 0], c3[:, 1])
            is_wall[mm] = True
        else:
            zs[mm] = surface.at(a, cx[m][mm], cy[m][mm])
    # (a paved yard meets a sidewalk on their shared edge: on its outline's plane, which ran between far points, line 23
    # s 557 (-2564.4, 434.0) stood 0.33 m under the sidewalk there, its nearest surveyed point 4 m off, a step with its
    # wall. Its plane shifts to the sidewalk's at the edge, faded over 3 m inward; per corner (the street surface, the
    # lidar, the plane, whichever reached) it seamed inside the yards wherever two met, #638)
    # (pinned also at the terrain's, the plots' and the beds' corners, line 9 seamed more inside the yards: 859 seams over
    # 10 cm against 847 unpinned, main 836)
    zs, meet = meet_raised(sc, cx[m], cy[m], zs)
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
    # (in a rock tunnel's corridor the survey's corners lie at the rails' level, not on the hill over it: off_the_hill, #771)
    rock = rock_tunnels(L, lidar_)
    in_rock, rail_z = in_the_rock(L, rock, cx[m], cy[m])
    in_rock, rail_z = portal_masonry(L, rock, in_rock, rail_z, cx[m], cy[m], zs, sa, lambda a: wall_like(D["areas"][a]))
    zs, on_hill = off_the_hill(zs, np.where(in_rock, rail_z, np.nan))
    lifted &= ~on_hill  # (no face stands there: it welds with the ground beside it)
    zc[m] = zs
    # (a shelter's footprint in a sidewalk, a hole no area fills, is the sidewalk's own ground: bare_holes, #776)
    c_hole = np.zeros(len(cx), bool)
    holes = bare_holes(D, np.unique(sa).tolist())
    if holes:
        tt = np.flatnonzero(tcls == "terrain")
        cen_t = fc[tt].mean(1)
        hit, _ = shapely.STRtree(holes).query(shapely.points(cen_t[:, 0], cen_t[:, 1]), predicate="intersects")
        idx = (np.unique(tt[hit])[:, None] * 3 + np.arange(3)).ravel()
        zt = streets.at("sidewalk", cx[idx], cy[idx]) if len(idx) else np.zeros(0)
        idx = idx[np.isfinite(zt)]
        zc[idx] = zt[np.isfinite(zt)]
        c_hole[idx] = True
    # (a stop's platform is a plane over the rail top: platform_planes, #776)
    c_plat = c_hole.copy()
    c_plat[m] = np.isin(sc, list(RAISED)) & ~on_span & ~on_terrace & ~in_rock & np.isfinite(zs)
    zc, on_plat = platform_planes(L, cx, cy, zc, c_plat)
    # (a wall the survey has as a line: the street, the lidar ground and the terrain beside it stand at its side's level
    # up to it, #697; a street under a bridge too, which keeps the survey's own outline (on_span): the sidewalk along
    # the Modřany ramp's wall, line 17 (-2385, -9250), has the wall's heights in its outline and rose 2 m against it)
    elig = corner_cls == "terrain"
    elig[m] = (np.isin(sc, list(STREETS_ROAD | STREETS_WALK)) | on_lidar) & ~in_rock
    cen = fc.mean(1)
    on_deck = np.zeros(len(cx), bool)
    on_deck[m] = on_span
    is_street = np.zeros(len(cx), bool)
    is_street[m] = np.isin(sc, list(STREETS_ROAD | STREETS_WALK))
    zc, at_wall = hold_at_walls(cx, cy, np.repeat(cen[:, 0], 3), np.repeat(cen[:, 1], 3), zc, elig, walls, on_deck, is_street)
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
    # (a survey area more than BED_OVER under the bed lies under the track's structure, not on its bed: it keeps its
    # level. The bed reaches a deck's end (#594), and at the Modřany viaduct's abutment, line 17 s 4062-4064, that end
    # stands 1.5 m past the abutment's face over the street's sidewalk (survey area 7214, 198.2 m): as a crossing the
    # sidewalk took the rails' 204.8 m there and rose against the wall in two peaks, #761)
    under_bed = (corner_cls[m] == "survey") & np.isfinite(zc[m]) & (zc[m] < zb - BED_OVER)
    ok = np.isfinite(zb) & ~under_bed
    zc[m[ok]], prio[m[ok]], kind[m[ok]] = zb[ok], 1.0, "bed"
    nan = np.isnan(zc)
    no_height = {str(c): int(n) for c, n in zip(*np.unique(np.where(kind[nan] == "", corner_cls[nan], kind[nan]), return_counts=True))}
    log(f"  heights: {int(nan.sum())} corners without one {no_height}, {len(walls)} wall stretches hold "
        f"{int(at_wall.sum()):,} corners, {n_under:,} street corners under a span on the lidar, {n_cover:,} lidar corners on a cover, {n_smear:,} road corners beside a thin wall off its smear, {int(on_hill.sum()):,} in a rock tunnel at the rails' level, {time.time() - t1:.0f} s")
    if nan.any():  # (a survey area without heights: the lidar's)
        zc[nan] = lidar_w(cx[nan], cy[nan])

    # the weld
    t1 = time.time()
    label = kind.copy()
    keep = kind[sv_m] != "bed"
    label[sv_m[keep]] = sv_label[keep]
    c_lift = np.zeros(len(cx), bool)
    c_lift[sv_m] = lifted
    # (a low wall stands: its corner over the ground at its point is the wall's own, #696)
    c_wall = np.zeros(len(cx), bool)
    c_wall[sv_m] = is_wall & ~on_hill
    c_lift |= standing(cx, cy, zc, c_wall, is_street)
    zf, steps, n_points = weld(cx, cy, zc, prio, kind, label, zown, at_wall & (kind != "bed"), c_lift & (kind != "bed"))
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
    # (the face a surveyed wall line makes is a wall's, whatever lies above it: under a lawn it was painted grass, #697)
    if len(walls) and wall_stretches:
        wall_draw[on_lines(V, walls, [w["p"] for w in wall_stretches])] = "survey:wall"
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
           "yards met to the raised areas (meet_raised)": {
               "corners shifted": int((np.abs(np.nan_to_num(meet)) > 0.005).sum()),
               "by over 5 / 10 / 20 cm": [int((np.abs(np.nan_to_num(meet)) > c / 100).sum()) for c in (5, 10, 20)]}}
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
    out = {"V": V, "F": F, "cls": fcls_id, "draw": draw, "area": area, "box": box, "L": L, "rep": rep}
    if within is not None:
        out["corners"] = {"x": cx, "y": cy, "z": zf, "label": label}
    return out


def on_lines(V, W, lines, tol=None):
    """Which triangles W (vertex ids of V, mm) have every corner within tol (WALL_ON) of the polylines `lines` ([(n, 2)]) in
    plan: the step faces standing on a line."""
    tol = WALL_ON if tol is None else tol
    tree = shapely.STRtree([shapely.LineString(p) for p in lines if len(p) > 1])
    P = V[W].astype(float) / Q
    pts = shapely.points(P[:, :, 0].ravel(), P[:, :, 1].ravel())
    pi, _ = tree.query(pts, predicate="dwithin", distance=tol)
    on = np.zeros(len(pts), bool)
    on[pi] = True
    return on.reshape(-1, 3).all(1)


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


def picture(ln, window, path, px=5, mesh=None):
    """The written ground seen from above at a window (x0, y0, x1, y1): each triangle its class's colour, shaded by its
    slope (light from the north-west), the steps' walls as red lines. mesh: (V in m, {class: triangles}) drawn in place
    of the line's written file (a place's build, tools/ground_place.py)."""
    from PIL import Image, ImageDraw
    if mesh is not None:
        V, by = mesh
    else:
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
    # (a build: beside counts and other builds while its peak, 21 GB on lines 22 and 17, and its threads fit, #728)
    with HeavyJob("ground_mesh", share={"gb": 21, "cores": a.threads}):
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
