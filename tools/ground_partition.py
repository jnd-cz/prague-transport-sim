# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground partition of a line's box: survey, OSM street, track bed, building plots and terrain (#507, #276 step 3).

    python -P -E tools/ground_partition.py --line 37            # the partition, its report and pictures
    python -P -E tools/ground_partition.py --lines 9,17,22,23,37
    python -P -E tools/ground_partition.py --calibrate 9,17,22,23,37   # the plot height rule against the survey
    (--mesh DIR: a city mesh folder other than the current inputs', for trials)

The decided priority (#15's T1, docs/decisions/2026-11-05-ground-built-offline.md): each class is cut by the ones above
it, so nothing lies under anything else, and the five cover the box once:
- **survey:** the level-0 ground areas of data/lineN.dtm.json (track_styles.ground_area, src/terrain.js groundArea) and
  its walls (drawn_area), as they are, their kerbs on their rings. Where two overlap, the higher rank holds the overlap
  (track_styles.RANK, the page's SURFACE_RANK), the smaller area between equal ranks (placement.py).
- **street:** OSM's streets outside the survey: none until #301; the terrain fills them.
- **bed:** every drawn track's bed outline (track_beds.outline: its style's width, the middle of the strip to a paired
  track), the tracks merged where they overlap at switches and crossings (#165). A bed sample whose ground (top of rail
  - lift) lies over LEVEL m from IPR's ground is on a structure (a bridge, a deck, a tunnel) and is left out: bridges
  and decks stand on the ground (the user, 2026-11-10), and the terrain stays under them.
- **plot:** OSM's building footprints (lineN.json `buildings`), flat at PLOT_RULE of IPR's ground along the footprint,
  PLOT_OUT m outside it (calibrated on the survey's building outlines, --calibrate).
- **water:** OSM's water areas with their islands (osm_water), level at the banks it sees past its weirs (WaterLevels,
  #632): the city mesh over water is IPR's fills, in steps.
- **terrain:** the city mesh (tools/city_terrain.py, in the machine cache) cut by the classes above: a triangle under
  them dropped, one across their edges cut and its remains triangulated by shapely's constrained Delaunay
  (tools/bench/ground_cut.py's method, the decision's section 2), the rest kept.

Writes reports/ground-partition/: lineN.partition.json, the pieces for review (the box, each class's pieces with their
source IDs: the survey's area index and class, the bed's track indexes, the plot's building index and height; the
terrain's counts and the mesh's key), lineN.json (the report) and pictures at the places of PLACES. The next step
(#508) calls partition() itself: it needs the geometry and the city mesh, which only a building machine holds.
"""
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely
from shapely.geometry import Point, Polygon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import ties  # noqa: E402 (of candidates as near, the first by where they lie, not by an STRtree's order, #812)

CLASSES =("survey", "street", "bed", "plot", "water", "terrain")
LEVEL = 2.5  # m: a bed's ground this far from IPR's lies on a structure (src/world.js LEVEL, a bridge or an underpass)
# m: near a span's end (DECK_END), a track this near the route and its height lies on the route's deck or on the ground
# where the route does (bed_pieces; a paired track 3.5-4.4 m from the route on line 17's bridges)
DECK_END, DECK_NEAR, DECK_LEVEL = 12.0, 6.0, 1.0
PLOT_OUT, PLOT_STEP = 0.5, 1.0  # m: the plot height's samples, outside the footprint and along it
PLOT_RULE = "median"  # the plot height (--calibrate on the five lines, 17,240 buildings: |error| median 0.29 m, p90 1.42;
# the 10th percentile 0.49 / 2.13, the lowest 0.67 / 2.48)
RULES = {"min": lambda z: float(np.min(z)), "p10": lambda z: float(np.percentile(z, 10)),
         "p25": lambda z: float(np.percentile(z, 25)), "median": lambda z: float(np.median(z))}
STRIP = 1.0  # m: terrain narrower than this between a plot and the classes above joins the plot (thin_strips)
GAP = 0.01  # m: gaps between beds narrower than twice this are closed (bed_pieces)
SLIVER = 1e-4  # m²: pieces smaller than this are left out (float noise of the cuts)
GRID = 1e-3  # m: the pieces' vertices on this grid, the ground file's (ground_mesh.Q)
TILE = 500.0  # m: the terrain is cut in squares this size side by side (threads; the world's tiles are geo.TILE)
GAUGE = 0.72  # m: a rail from the axis (track_beds.GAUGE)
# (the line's ground reaches this far from its route and tracks: the fog ends at 950 m (src/main.js), nothing farther is
# seen. The user, 2026-11-16, #509: "I want to get to tile streaming as soon as possible so let's do just option 1": the
# crop, lines 17 and 22 keeping 63 % of their triangles)
CORRIDOR = 1200.0  # m
CORRIDOR_SIMPLIFY = 1.0  # m: the corridor's outline, simplified (its arcs need no more)
# #166's and #165's places: (line, route s, the city-frame sample where the issue gives one)
RAIL_PLACES = (("17", 2352, (-742.275, -8964.692)), ("17", 17128, None), ("9", 1194, None), ("37", 3768, (3920.091, 1082.375)))
# the pictures (#507's done-when): (name, line, a stop's name or a point)
PLACES = (("vystaviste", "17", "Výstaviště"), ("palmovka", "37", "Palmovka"), ("switch-fan", None, None))
WINDOW = 160.0  # m: a picture's side
BUILDINGS_KR = "010000029902_Hranice_budovy"  # the survey's 3D building outlines (ZPS KR), the plot rule's reference
WATER_CUTS = ("weir", "dam", "lock_gate")  # OSM's waterway=* ways a river's level steps at (pools)
WATER_CUT_EXT, WATER_CUT_NEAR = 3.0, 2.0  # m: a cut extended past its ends; its banks' heights read this far from it
WATER_LEVEL = 0.1  # a pool's level: this quantile of IPR's ground along its banks (src/terrain.js DtmSurface's water)
WATER_STEP = 10.0  # m: the banks' samples where they cross the lines of this grid (bank_samples)
# m, samples, m: the banks a level is read from (WaterLevels). WATER_FAR is a tile's side (geo.TILE): a tile's ground
# reads its ring of tiles and nothing farther, or a tile has one level in a line's build and another in a place's or
# the city's (#812: 1,000 m read past lattice-cell's ring)
WATER_REACH, WATER_FEW, WATER_FAR = 250.0, 10, 500.0
WATER_SEE, WATER_RES, WATER_CUT_W = 1.0, 1.0, 3  # m, m, cells: the lines of sight (WaterLevels._seen)


def load(ln):
    L = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
    p = os.path.join(ROOT, "data", f"line{ln}.dtm.json")
    D = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"areas": []}
    return L, D


def line_box(L):
    """The line's box: its terrain grid's cell centres (lineN.json `terrain`), as the page's terrain covers."""
    T = L["terrain"]
    xs = (T["x0"], T["x0"] + T["dx"] * (T["nx"] - 1))
    ys = (T["y0"], T["y0"] + T["dy"] * (T["ny"] - 1))
    return shapely.box(min(xs), min(ys), max(xs), max(ys))


def line_area(L, reach=CORRIDOR):
    """The line's ground: its box within `reach` of its route and its tracks (a polygon, simplified to CORRIDOR_SIMPLIFY)."""
    lines = [shapely.LineString([p[:2] for p in L["path"]])] if len(L.get("path") or []) > 1 else []
    lines += [shapely.LineString([p[:2] for p in t["p"]]) for t in L.get("tracks") or [] if len(t.get("p") or []) > 1]
    box = line_box(L) if L.get("terrain") else None  # (a line without its 10 m grid: a test's fixture)
    if not lines:
        return box if box is not None else Polygon()
    near = polygonal(shapely.union_all(shapely.buffer(np.asarray(lines, dtype=object), reach, quad_segs=4)).simplify(CORRIDOR_SIMPLIFY))
    return near if box is None else polygonal(near.intersection(box))


def polygonal(g):
    """The polygons of g (a cut can leave lines and points beside them)."""
    if g.is_empty:
        return shapely.Polygon()
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = [q for q in shapely.get_parts(g) if q.geom_type in ("Polygon", "MultiPolygon")]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def area_poly(r, holes=()):
    q = Polygon([p[:2] for p in r], [[p[:2] for p in h] for h in holes if len(h) >= 3])
    return q if q.is_valid else polygonal(shapely.make_valid(q))


# ---------------------------------------------------------------- the classes
def drawn_area(a):
    """A survey area the ground draws: a ground area (track_styles.ground_area) or a level-0 wall. Nobody stands on a wall
    (the page's groundArea), but the page drew it from its own outline before #509 (alpha-4's buildDtm drew every area):
    left out, a battered wall's strip was the city mesh's lidar triangles, a 1.6 m face of teeth along Krejcárek's ramp,
    line 37 (3915, 316), #653."""
    from track_styles import ground_area
    return ground_area(a) or (a.get("l") == 0 and a["c"] == "wall")


def survey_pieces(D, box):
    """The survey's level-0 drawn areas (drawn_area) inside the box, each without what a higher one holds: [{area, c, g}]."""
    from track_styles import RANK
    items = []
    for i, a in enumerate(D.get("areas", [])):
        if not drawn_area(a) or len(a["r"]) < 3:
            continue
        g = polygonal(area_poly(a["r"], a.get("h", [])).intersection(box))
        if g.area > SLIVER:
            items.append((-RANK.get(a["c"], 1), g.area, i, a["c"], g))
    items.sort(key=lambda t: t[:3])
    geoms = [t[4] for t in items]
    tree = shapely.STRtree(geoms)
    out = []
    for k, (_, _, i, c, g) in enumerate(items):
        above = [j for j in tree.query(g, predicate="intersects").tolist() if j < k]
        if above:
            g = polygonal(g.difference(shapely.union_all([geoms[j] for j in above])))
        if g.area > SLIVER:
            out.append({"area": i, "c": c, "g": g})
    return out


def bed_samples(tr):
    """A track's bed samples as track_beds.outline places them: (x, y) each."""
    from route import Route
    rt = Route(tr["p"])
    n = len(tr["bed"]["l"])
    step = rt.length / max(1, n - 1)
    return np.array([rt.at(min(k * step, rt.length))[:2] for k in range(n)])


def lift_at(L):
    """lift(s) along the route (the rail over its bed, #479): a function of route s, 0 without it."""
    lf = L.get("lift") or {}
    v = np.asarray(lf.get("v") or [0], float) * lf.get("unit", 0.001)
    st = lf.get("step", 2.0)
    return lambda s: np.interp(np.asarray(s, float) / st, np.arange(len(v)), v)


def route_decks(L):
    """The route's decks: its spans less their ramps (tools/line_structures.py), as [(s0, s1)]."""
    out = []
    for a, b in L.get("spans") or []:
        s = a
        for r0, r1 in sorted((max(a, r0), min(b, r1)) for r0, r1 in L.get("ramps") or [] if r0 < b and r1 > a):
            if r0 > s:
                out.append((s, r0))
            s = max(s, r1)
        if b > s:
            out.append((s, b))
    return out


def bed_pieces(L, box, ipr, F, log=None):
    """The beds' union inside the box, without their samples on structures: (the union, [(track index, outline)],
    the samples on the ground and on structures). The structure test (|top of rail - lift - IPR| > LEVEL) is logged
    against the route's spans and tunnels where a track runs along the route (log: a dict for the report).
    Within DECK_END m of a span, a track along the route at its level (within DECK_NEAR m of it and DECK_LEVEL m of its
    height) is on a structure on the route's decks (route_decks) and on the ground off them, and its bed ends at the
    deck's end: the lidar's test and the ramps (tools/line_structures.py RAMP_GAP) parted there by a sample, and the bed
    ended up to 2 m before the deck, the terrain or the survey falling under the rails between them (#594: line 17
    s 4062, 5076, 6540, 0.07-1.67 m off the bed top; Krejcárek's south ramp, line 37 s 3032-3036)."""
    from track_beds import outline
    path = shapely.LineString([p[:2] for p in L["path"]])
    lift = lift_at(L)
    struct = [tuple(v) for v in (L.get("spans") or []) + (L.get("tunnels") or [])]
    decks = route_decks(L)
    hp = (L.get("heights") or {}).get("path")
    deck_area = None
    if decks and hp:
        zp = np.asarray(hp, float)
        zroute = lambda v: np.interp(np.asarray(v, float) / L["heights"]["step"], np.arange(len(zp)), zp)  # noqa: E731
        from shapely.ops import substring
        deck_area = shapely.union_all([substring(path, a, b).buffer(DECK_NEAR + 6, cap_style="flat")
                                       for a, b in decks if b - a > 0.1])
    n_route = 0
    outs, n_ground, n_struct = [], 0, 0
    confusion = {"structure, on a span or in a tunnel": 0, "structure, elsewhere": 0, "ground, on a span or in a tunnel": 0,
                 "ground, elsewhere": 0}
    for i, tr in enumerate(L.get("tracks") or []):
        # (a bridge's track, `b`: the bridge carries it, and the page lays no ground bed under it (world.js bedsNear,
        # lowerTerrainUnderTracks); its ends on the ground made bed pieces without a bed surface, 961 corners on line 17)
        if not tr.get("bed") or len(tr.get("p") or []) < 2 or not tr.get("zs") or tr.get("b"):
            continue
        xy = bed_samples(tr)
        zs = np.asarray(tr["zs"], float)[:len(xy)]
        pts = shapely.points(xy)
        d = shapely.distance(path, pts)
        s = shapely.line_locate_point(path, pts)
        lf = np.where(d < 3.0, lift(s), 0.0)
        g = np.asarray(ipr.sample(xy[:, 0] + F.E0, xy[:, 1] + F.N0), float)
        ground = ~(np.abs(zs - lf - g) > LEVEL)  # (no lidar: on the ground)
        keep = ground
        if deck_area is not None:
            near_end = np.array([any(a - DECK_END <= v <= b + DECK_END for a, b in L["spans"]) for v in s])
            along = (d < DECK_NEAR) & (np.abs(zs - zroute(s)) < DECK_LEVEL) & near_end
            if along.any():
                on_deck = np.array([any(a <= v <= b for a, b in decks) for v in s])
                n_route += int((along & (ground == on_deck)).sum())
                ground = np.where(along, ~on_deck, ground)
                # (the stretch across a deck's end kept whole, then cut at the deck's end below)
                keep = ground.copy()
                keep[1:] |= ground[:-1] & along[1:]
                keep[:-1] |= ground[1:] & along[:-1]
        n_ground += int(ground.sum())
        n_struct += int((~ground).sum())
        on = d < 3.0
        in_s = np.array([any(a <= v <= b for a, b in struct) for v in s]) & on
        for k, (gr, ins) in enumerate(zip(ground.tolist(), in_s.tolist())):
            if on[k]:
                confusion[f"{'ground' if gr else 'structure'}, {'on a span or in a tunnel' if ins else 'elsewhere'}"] += 1
        o = outline(tr, tr["bed"], keep=keep.tolist())
        if (keep & ~ground).any():  # (only round those samples: the same track elsewhere keeps its bed)
            o = o.difference(deck_area.intersection(shapely.union_all(shapely.buffer(pts[keep & ~ground], 4.0))))
        o = polygonal(o.intersection(box))
        if o.area > SLIVER:
            outs.append((i, o))
    if log is not None:
        log.update({"samples on the ground": n_ground, "samples on structures, left out": n_struct,
                    "along the route (within 3 m): the test against the route's spans and tunnels": confusion,
                    "samples near a span's end the route's decks decided against the lidar": n_route})
    union = shapely.union_all([o for _, o in outs]) if outs else shapely.Polygon()
    # (two tracks' beds that meet, paired or at a switch, leave gaps of a few mm between them: line 17 had 2,248, median
    # 3.5 mm wide; closed here, a gap under 2 * GAP wide)
    union = polygonal(union.buffer(GAP, join_style="mitre").buffer(-GAP, join_style="mitre").intersection(box))
    return union, outs


def ring_samples(g, out=PLOT_OUT, step=PLOT_STEP):
    """Points along the outside of a footprint, `out` m out, every `step` m."""
    e = g.buffer(out, join_style="mitre", mitre_limit=2.0).exterior if g.geom_type == "Polygon" else \
        max(shapely.get_parts(g), key=lambda q: q.area).buffer(out, join_style="mitre", mitre_limit=2.0).exterior
    n = max(4, int(e.length / step))
    return np.array([e.interpolate(k * e.length / n).coords[0] for k in range(n)])


def plot_height(g, ipr, F, rule=PLOT_RULE):
    xy = ring_samples(g)
    z = np.asarray(ipr.sample(xy[:, 0] + F.E0, xy[:, 1] + F.N0), float)
    z = z[np.isfinite(z)]
    return round(RULES[rule](z), 2) if len(z) else None


def plot_pieces(L, box, above, ipr, F):
    """OSM's footprints inside the box without the classes above (`above`: their pieces, each small: the union of the
    survey is one polygon of a million vertices, and cutting by it took 10 min on line 9) and without an earlier
    footprint: [{building, z, g}].
    The height is measured on the whole footprint."""
    out = []
    for i, b in enumerate(L.get("buildings") or []):
        if len(b.get("p") or []) < 3:
            continue
        g0 = area_poly(b["p"])
        if g0.is_empty or not g0.intersects(box):
            continue
        g = polygonal(g0.intersection(box))
        out.append({"building": i, "g": g, "g0": g0})
    tree = shapely.STRtree([q["g"] for q in out])
    above_parts = [q for g in above for q in shapely.get_parts(g)]
    tree_above = shapely.STRtree(above_parts) if above_parts else None
    res = []
    for k, q in enumerate(out):
        g = q["g"]
        earlier = [j for j in tree.query(g, predicate="intersects").tolist() if j < k]
        cut = [out[j]["g"] for j in earlier]
        if tree_above is not None:
            cut += [above_parts[j] for j in tree_above.query(g, predicate="intersects").tolist()]
        if cut:
            g = polygonal(g.difference(shapely.union_all(cut)))
        if g.area > SLIVER:
            res.append({"building": q["building"], "z": plot_height(q["g0"], ipr, F), "g": g})
    return res


def on_the_grid(qs):
    """Pieces ([{g, ...}], in place) with their vertices on the mm grid the ground file keeps (GRID), those left under
    SLIVER dropped. The cuts run over the whole box, and where pieces meet they leave needles and slivers of float
    noise that differ with the box: lattice-cell's tile held a plot with a needle 9 m long and 1e-13 m wide in one box
    and not in the other, and its edges were among the faces' lines (#812). On the grid they are gone."""
    for q in qs:
        q["g"] = polygonal(shapely.set_precision(q["g"], GRID))
    qs[:] = [q for q in qs if q["g"].area > SLIVER]
    return qs


def thin_strips(terrain, plots, width=STRIP):
    """Terrain narrower than `width` that touches a plot joins that plot (in place): OSM's footprints lie up to a metre
    off the survey's outlines of the same walls, and the strip between them is under the wall. {pieces, area}."""
    thin = polygonal(terrain.difference(terrain.buffer(-width / 2).buffer(width / 2, join_style="mitre")))
    parts = [g for g in shapely.get_parts(thin) if g.geom_type == "Polygon" and g.area > SLIVER]
    if not parts or not plots:
        return {"pieces": 0, "area": 0.0}
    tree = shapely.STRtree([q["g"] for q in plots])
    joined = {}
    n, a = 0, 0.0
    for g in parts:
        near = tree.query(g, predicate="dwithin", distance=1e-3).tolist()
        if not near:
            continue
        k = max(near, key=lambda j: g.buffer(1e-3).intersection(plots[j]["g"].boundary).length)
        joined.setdefault(k, []).append(g)
        n, a = n + 1, a + g.area
    for k, gs in joined.items():
        plots[k]["g"] = polygonal(shapely.union_all([plots[k]["g"]] + gs))
    return {"pieces": n, "area": a}


# ---------------------------------------------------------------- the water
_WAYS = {}  # (ways' points in the city frame by id, once per process: the lines build one after another)


def _way_xy(ids, F):
    """The points of OSM's ways `ids` in the city frame ({id: (n, 2)}): from the extract's index, which keeps tagged ways
    only, and the rest (a river's outline is untagged member ways) from one pass over its ways and one over its nodes."""
    import osm_local
    want = [w for w in ids if w not in _WAYS]
    if want:
        ix = osm_local._index()
        if "w_at" not in ix:
            ix["w_at"] = {w: i for i, w in enumerate(ix["w_id"].tolist())}
        co, c, rest = ix["w_co"], ix["w_c"], set()
        for w in want:
            i = ix["w_at"].get(w)
            if i is None:
                rest.add(w)
                continue
            ll = np.asarray(c[co[i]:co[i + 1]], float).reshape(-1, 2)
            _WAYS[w] = np.column_stack(F.xy(ll[:, 0], ll[:, 1]))
        if rest:
            import osmium
            refs = {o.id: [n.ref for n in o.nodes] for o in osmium.FileProcessor(osm_local.PRAHA, osmium.osm.WAY) if o.id in rest}
            ll = osm_local.node_coords({r for v in refs.values() for r in v})
            for w, rr in refs.items():
                p = np.array([ll[r] for r in rr if r in ll], float)
                if len(p) >= 2:
                    _WAYS[w] = np.column_stack(F.xy(p[:, 0], p[:, 1]))
    return {w: _WAYS[w] for w in ids if w in _WAYS}


def _wet(t):
    """An OSM water area's tags (the old riverbank tagging too), not a covered or underground one."""
    return ((t.get("natural") == "water" or t.get("waterway") == "riverbank")
            and t.get("covered") != "yes" and not t.get("tunnel") and t.get("location") not in ("underground", "underwater"))


def osm_water(box, F):
    """OSM's water areas that reach the box, whole, with their islands: closed ways and multipolygons, outer rings less
    inner rings. (The line data keeps outer rings only, tools/build_line.py: an island lay in its river, Štvanice and
    Střelecký ostrov levelled with the Vltava and drawn as water, #632.) One geometry in the city frame."""
    import osm_local
    x0, y0, x1, y1 = box.bounds
    (s, w), (n, e) = F.ll(x0, y0), F.ll(x1, y1)
    parts = []
    for el in osm_local.ways(_wet, bbox=(s, w, n, e)):
        if el["nodes"][0] != el["nodes"][-1] or len(el["geometry"]) < 4:
            continue
        ll = np.array([(g["lat"], g["lon"]) for g in el["geometry"]], float)
        g = Polygon(np.column_stack(F.xy(ll[:, 0], ll[:, 1])))
        parts.append(g if g.is_valid else polygonal(shapely.make_valid(g)))
    rels = osm_local.relations(lambda t: t.get("type") == "multipolygon" and _wet(t))
    xy = _way_xy({m["ref"] for r in rels for m in r["members"] if m["type"] == "way"}, F)

    def faces(ways):
        if not ways:
            return Polygon()
        return polygonal(shapely.union_all(shapely.get_parts(shapely.polygonize(shapely.get_parts(shapely.union_all(ways))))))
    shapely.prepare(box)
    for r in rels:
        outer = [shapely.LineString(xy[m["ref"]]) for m in r["members"] if m["type"] == "way" and m["ref"] in xy and m["role"] != "inner"]
        inner = [shapely.LineString(xy[m["ref"]]) for m in r["members"] if m["type"] == "way" and m["ref"] in xy and m["role"] == "inner"]
        o = faces(outer)
        if not o.is_empty and o.intersects(box):
            parts.append(polygonal(o.difference(faces(inner))))
    parts = [g for g in parts if not g.is_empty and g.intersects(box)]
    return polygonal(shapely.union_all(parts)) if parts else Polygon()


def water_cuts(W, F, ext=None):
    """OSM's weirs, dams and lock gates (ways) across the water W, each extended `ext` m (WATER_CUT_EXT) past its ends:
    one drawn a hair short of its bank still splits the water."""
    import osm_local
    ext = WATER_CUT_EXT if ext is None else ext
    x0, y0, x1, y1 = W.bounds
    (s, w), (n, e) = F.ll(x0, y0), F.ll(x1, y1)
    out = []
    for el in osm_local.ways(lambda t: t.get("waterway") in WATER_CUTS, bbox=(s, w, n, e)):
        ll = np.array([(g["lat"], g["lon"]) for g in el["geometry"]], float)
        p = np.column_stack(F.xy(ll[:, 0], ll[:, 1]))
        if len(p) < 2:
            continue
        a, b = p[0] - p[1], p[-1] - p[-2]
        a = p[0] + ext * a / max(np.hypot(*a), 1e-9)
        b = p[-1] + ext * b / max(np.hypot(*b), 1e-9)
        g = shapely.LineString(np.vstack([a, p, b]))
        if g.intersects(W):
            out.append(g)
    return out


def bank_samples(line, step=WATER_STEP):
    """The points where a line crosses the S-JTSK grid's lines every `step` m (x and y; geo.ORIGIN), each once: a
    bank's samples that depend on the bank near them alone. (Spaced evenly from a ring's first point, they moved with
    where the ring started and how long it ran: the union with water past the ring started a pond's ring elsewhere,
    and its level moved by up to 12.8 cm in lattice-cell's tile, #812.) About one sample every `step` m along a
    bank, up to 1.41 on a diagonal."""
    from geo import ORIGIN
    out = [np.zeros((0, 2))]
    for q in shapely.get_parts(line):
        c = shapely.get_coordinates(q)
        if len(c) < 2:
            continue
        a, b = c[:-1], c[1:]
        for ax in (0, 1):
            u, w = a[:, ax] + ORIGIN[ax], b[:, ax] + ORIGIN[ax]
            k0, k1 = np.ceil(np.minimum(u, w) / step), np.floor(np.maximum(u, w) / step)
            n = np.where(u != w, np.maximum(k1 - k0 + 1, 0), 0).astype(int)
            if not n.sum():
                continue
            seg = np.repeat(np.arange(len(a)), n)
            k = k0[seg] + np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
            t = (k * step - u[seg]) / (w[seg] - u[seg])
            out.append(a[seg] + t[:, None] * (b[seg] - a[seg]))
    P = np.concatenate(out)
    if not len(P):
        return P
    _, first = np.unique(np.round(P * 1000).astype(np.int64), axis=0, return_index=True)  # (a point on two segments)
    return P[np.sort(first)]


class WaterLevels:
    """The water's level at points: the `level` quantile (WATER_LEVEL) of IPR's ground along the banks of the point's own
    water (W's polygon holding it) within `reach` m (WATER_REACH) that a straight line from the point reaches over the
    water without crossing a cut (a weir, a dam, a lock gate). Where fewer than WATER_FEW do, the nearest WATER_FEW
    within WATER_FAR it reaches so, else the nearest WATER_FEW within WATER_FAR on its side of the cuts. A river falls
    at its weirs: line 17's Modřany weir 2.2 m, Štvanice's 3.9; the level from every bank within 150 m put the step
    50-100 m upstream of the weir (#632). The cuts close no pools: the Vltava passes Prague's weirs through Čertovka and
    side channels with no weir mapped across them, so a point's level is the banks' it sees, not its pool's outline's.
    The lines of sight run on a raster of WATER_RES m on the S-JTSK grid: the water, one cell grown (a line along a
    bank), less the cuts drawn WATER_CUT_W cells wide.
    A level reads the banks within WATER_FAR of its point and nothing else: the samples where the banks cross a fixed
    grid (bank_samples), the raster's cells on that grid whatever the extent (from the water's bounds in the box they
    moved with the box, and a pond saw 17, 18 or 19 of its 23 banks, #812)."""

    def __init__(self, W, cuts, ipr, F, reach=None, level=None, extent=None):
        from PIL import Image, ImageDraw
        from scipy.ndimage import binary_dilation
        from scipy.spatial import cKDTree
        self.reach = WATER_REACH if reach is None else reach
        self.level = WATER_LEVEL if level is None else level
        C = shapely.union_all(cuts) if cuts else None
        self.C = C
        if C is not None:
            shapely.prepare(C)
        near = C.buffer(WATER_CUT_NEAR) if C is not None else None
        self.parts = [g for g in shapely.get_parts(W) if g.geom_type == "Polygon"]
        self.part_tree = shapely.STRtree(self.parts) if self.parts else None
        self.part_rank = ties.by_place(self.parts)
        P, lab = [np.zeros((0, 2))], [np.zeros(0, int)]
        for j, g in enumerate(self.parts):
            bank = g.boundary if near is None else g.boundary.difference(near)
            q = bank_samples(bank)
            if len(q):
                P.append(q)
                lab.append(np.full(len(q), j))
        P, lab = np.concatenate(P), np.concatenate(lab)
        z = np.asarray(ipr.sample(P[:, 0] + F.E0, P[:, 1] + F.N0), float) if len(P) else np.zeros(0)
        ok = np.isfinite(z)
        self.P, self.z, self.lab = P[ok], z[ok], lab[ok]
        self.trees = {}
        for j in np.unique(self.lab).tolist():
            ids = np.flatnonzero(self.lab == j)
            self.trees[j] = (ids, cKDTree(self.P[ids]))
        # the raster the lines of sight run on (the extent's water: the line's ground grown by WATER_FAR), its cells on
        # the S-JTSK grid
        from geo import ORIGIN
        ex = W if extent is None else W.intersection(extent)
        r = WATER_RES
        bx0, y0, x1, by1 = ex.bounds if not ex.is_empty else (0, 0, 1, 1)
        self.x0 = math.floor((bx0 + ORIGIN[0]) / r) * r - ORIGIN[0]
        self.y1 = math.ceil((by1 + ORIGIN[1]) / r) * r - ORIGIN[1]
        nx, ny = int((x1 - self.x0) / r) + 2, int((self.y1 - y0) / r) + 2
        im = Image.new("1", (nx, ny), 0)
        d = ImageDraw.Draw(im)

        def px(c):
            c = np.asarray(c)
            return list(zip(((c[:, 0] - self.x0) / r).tolist(), ((self.y1 - c[:, 1]) / r).tolist()))
        for g in shapely.get_parts(polygonal(ex)):
            if g.geom_type != "Polygon":
                continue
            d.polygon(px(g.exterior.coords), fill=1)
            for h in g.interiors:
                d.polygon(px(h.coords), fill=0)
        grid = binary_dilation(np.asarray(im, bool))
        im = Image.fromarray(grid)
        d = ImageDraw.Draw(im)
        for c in cuts or []:
            d.line(px(c.coords), fill=0, width=WATER_CUT_W)
        self.grid = np.asarray(im, bool)

    def _seen(self, v, idx):
        """Of the bank samples idx, those a straight line from v reaches over the water without crossing a cut (its first
        and last WATER_SEE m not tested: v may lie on a bank, a sample does)."""
        idx = np.asarray(idx, int)
        if not len(idx):
            return idx
        d = self.P[idx] - v
        n = np.hypot(d[:, 0], d[:, 1])
        h = WATER_RES
        t = np.arange(WATER_SEE, max(float(n.max()) - WATER_SEE, WATER_SEE) + h, h)
        q = v[None, None, :] + d[:, None, :] * (t[None, :, None] / np.maximum(n, 1e-9)[:, None, None])
        c = ((q[..., 0] - self.x0) / WATER_RES).astype(int)
        rr = ((self.y1 - q[..., 1]) / WATER_RES).astype(int)
        ny, nx = self.grid.shape
        inside = (c >= 0) & (c < nx) & (rr >= 0) & (rr < ny)
        wet = np.zeros(c.shape, bool)
        wet[inside] = self.grid[rr[inside], c[inside]]
        return idx[(wet | (t[None, :] > n[:, None] - WATER_SEE)).all(1)]

    def at(self, px, py, vx=None, vy=None):
        """Levels at the points, NaN where their water's banks have no IPR ground; seen from (vx, vy) where given (a
        corner on a cut seen from inside its own face: from the cut itself both sides are in sight)."""
        out = np.full(len(px), np.nan)
        if not self.trees or not len(px):
            return out
        V = np.column_stack([px if vx is None else vx, py if vy is None else vy]).astype(float)
        pts = shapely.points(V)
        own = np.full(len(V), -1)
        # (a point on two parts, or as near two: the first part by where it lies, not by the tree's order, #812)
        pi, gi = self.part_tree.query(pts, predicate="intersects")
        k = ties.firsts(pi, self.part_rank[gi])
        own[pi[k]] = gi[k]
        lost = np.flatnonzero(own < 0)
        if len(lost):
            li, lo = ties.nearest(self.part_tree, self.part_rank, pts[lost])
            own[lost[li]] = lo
        for j in np.unique(own).tolist():
            if j not in self.trees:
                continue
            ids, tree = self.trees[j]
            sel = np.flatnonzero(own == j)
            for k, loc in zip(sel.tolist(), tree.query_ball_point(V[sel], self.reach)):
                idx = self._seen(V[k], ids[np.asarray(loc, int)])
                if len(idx) < WATER_FEW:
                    # (the nearest 4 WATER_FEW within WATER_FAR; of samples as near, the first by place, not by the KD
                    # tree's order, which every sample in the box moves, #812)
                    loc = np.asarray(tree.query_ball_point(V[k], WATER_FAR), int)
                    q = self.P[ids[loc]]
                    dist = np.hypot(q[:, 0] - V[k, 0], q[:, 1] - V[k, 1])
                    loc = loc[np.lexsort((q[:, 1], q[:, 0], dist))][:4 * WATER_FEW]
                    idx = self._seen(V[k], ids[loc])[:WATER_FEW]
                    if len(idx) < WATER_FEW:  # (the nearest on its side of the cuts, over the land too; else the nearest)
                        near = ids[loc]
                        side = self._this_side(V[k], near)[:WATER_FEW]
                        idx = side if len(side) else near[:WATER_FEW]
                if len(idx):
                    out[k] = np.quantile(self.z[idx], self.level)
        return out

    def _this_side(self, v, idx):
        """Of the bank samples idx, those a straight line from v reaches without crossing a cut."""
        if self.C is None or not len(idx):
            return idx
        seg = shapely.linestrings(np.stack([np.broadcast_to(v, (len(idx), 2)), self.P[idx]], 1))
        return idx[~shapely.intersects(seg, self.C)]


# ---------------------------------------------------------------- the terrain
def mesh_in_box(mesh_dir, box):
    """The city mesh's triangles whose box meets the line's: (x, y, z of the vertices used, (m, 3) indexes), the key."""
    m = np.load(os.path.join(mesh_dir, "mesh.npz"))
    V, T, o = m["v"], m["t"], m["origin"]
    x = o[0] + V[:, 0].astype(float)
    y = o[1] - V[:, 1].astype(float)
    x0, y0, x1, y1 = box.bounds
    tx, ty = x[T], y[T]
    keep = (tx.max(1) >= x0) & (tx.min(1) <= x1) & (ty.max(1) >= y0) & (ty.min(1) <= y1)
    T = T[keep]
    used, T = np.unique(T, return_inverse=True)
    return x[used], y[used], V[used, 2] / 100.0, T.reshape(-1, 3)


def cut_terrain(x, y, T, cover, box, threads=8, window=None, geometry=False):
    """The terrain triangles against the cover (the classes above) and the box, tile by tile side by side (shapely's
    vectorised calls release the GIL): counts and areas, and the triangles inside `window` (a box) for the pictures.
    geometry: also "kept" (the indexes of the triangles kept whole), "remains" ([(the cut triangle's index, a polygon of
    what is left of it)]) and "under" (the indexes of those the cover reaches: dropped or cut), for the mesh
    (tools/ground_mesh.py)."""
    tris = shapely.polygons(np.stack([np.column_stack([x[T[:, k]], y[T[:, k]]]) for k in (0, 1, 2, 0)], 1))
    cx, cy = x[T].mean(1), y[T].mean(1)
    tile = np.floor(cx / TILE).astype(np.int64) * 1000003 + np.floor(cy / TILE).astype(np.int64)
    order = np.argsort(tile, kind="stable")
    bounds = np.flatnonzero(np.diff(tile[order])) + 1
    groups = np.split(order, bounds)

    def one(ids):
        P = tris[ids]
        b = shapely.bounds(P)
        bb = (b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max())
        C = shapely.clip_by_rect(cover, *bb)
        # (each tile its own piece of the box: a prepared geometry builds its index at its first use, and the corridor's
        # polygon shared by the threads crashed GEOS with an access violation)
        Bx = shapely.clip_by_rect(box, *bb)
        shapely.prepare(Bx)
        inbox = shapely.contains(Bx, P)
        if C.is_empty:
            hit = within = np.zeros(len(P), bool)
        else:
            shapely.prepare(C)
            hit = shapely.intersects(C, P)
            within = np.zeros(len(P), bool)
            within[hit] = shapely.contains(C, P[hit])
        kept = ~hit & inbox
        cut = (hit & ~within) | (~hit & ~inbox)
        r = {"triangles": len(P), "dropped": int(within.sum()), "cut": int(cut.sum()), "kept": int(kept.sum()),
             "kept_area": float(shapely.area(P[kept]).sum()), "new": 0, "new_area": 0.0, "lost_area": 0.0, "win": [],
             "kept_ids": ids[kept] if geometry else None, "under_ids": ids[hit] if geometry else None, "remains": []}
        if cut.any():
            rest = shapely.intersection(shapely.difference(P[cut], C) if not C.is_empty else P[cut], Bx)
            parts, pi = shapely.get_parts(rest, return_index=True)
            poly = np.isin(shapely.get_type_id(parts), (3,))
            parts, pi = parts[poly], pi[poly]
            a = shapely.area(parts)
            r["lost_area"] = float(a[a <= SLIVER].sum())
            parts, pi = parts[a > SLIVER], pi[a > SLIVER]
            if geometry:
                r["remains"] = list(zip(ids[cut][pi].tolist(), parts))
            new = shapely.get_parts(shapely.constrained_delaunay_triangles(parts)) if len(parts) else []
            r["new"], r["new_area"] = len(new), float(shapely.area(new).sum()) if len(new) else 0.0
            if window is not None and len(new):
                r["win"] += [t for t in new if t.intersects(window)]
        if window is not None:
            r["win"] += [t for t in P[kept] if t.intersects(window)]
        return r

    with ThreadPoolExecutor(threads) as ex:
        res = list(ex.map(one, groups))
    tot = {k: sum(r[k] for r in res) for k in ("triangles", "dropped", "cut", "kept", "new", "kept_area", "new_area", "lost_area")}
    tot["win"] = [t for r in res for t in r["win"]]
    if geometry:
        tot["kept_ids"] = np.concatenate([r["kept_ids"] for r in res]) if res else np.zeros(0, int)
        tot["under_ids"] = np.concatenate([r["under_ids"] for r in res]) if res else np.zeros(0, int)
        tot["remains"] = [q for r in res for q in r["remains"]]
    return tot


# ---------------------------------------------------------------- the run
def partition(ln, mesh=None, threads=8, windows=(), geometry=False, within=None):
    """The partition of line ln: (the pieces per class, the report, the terrain triangles in each window). within: a box
    (x0, y0, x1, y1) the line's ground is cut to, for one place's ground (tools/ground_place.py, #757)."""
    from geo import Frame
    from ipr_dtm import IprDtm
    t0 = time.time()
    L, D = load(ln)
    F, ipr = Frame(), IprDtm()
    box = line_area(L)  # (the box within CORRIDOR of the route and tracks: `box` below is that polygon)
    if within is not None:
        box = polygonal(box.intersection(shapely.box(*within)))
    rep = {"line": ln, "box": [round(v, 2) for v in box.bounds], "box_km2": round(box.area / 1e6, 4),
           "corridor m": CORRIDOR, "of the box, %": round(100 * box.area / line_box(L).area, 1)}
    tm, last = {}, [time.time()]

    def lap(k):
        tm[k] = round(time.time() - last[0], 1)
        last[0] = time.time()
    survey = survey_pieces(D, box)
    S = shapely.union_all([q["g"] for q in survey]) if survey else shapely.Polygon()
    lap("survey")
    blog = {}
    B0, outs = bed_pieces(L, box, ipr, F, blog)
    B = polygonal(B0.difference(S))
    lap("beds")
    beds = []
    for g in shapely.get_parts(B):
        if g.area > SLIVER:
            beds.append({"tracks": [i for i, o in outs if o.intersects(g)], "g": g})
    plots = plot_pieces(L, box, [q["g"] for q in survey] + [q["g"] for q in beds], ipr, F)
    P = shapely.union_all([q["g"] for q in plots]) if plots else shapely.Polygon()
    lap("plots")
    terrain = polygonal(box.difference(shapely.union_all([S, B, P])))
    lap("terrain area")
    strips = thin_strips(terrain, plots)
    lap("strips")
    if strips["area"]:
        P = shapely.union_all([q["g"] for q in plots])
    # (OSM's water with its islands, whole: its banks give its level, ground_mesh.py; its pieces in the box under the
    # classes above, #632)
    W = osm_water(box, F)
    cuts = water_cuts(W, F) if not W.is_empty else []
    Wp = polygonal(W.intersection(box).difference(shapely.union_all([S, B, P]))) if not W.is_empty else Polygon()
    water = [{"g": g} for g in shapely.get_parts(Wp) if g.geom_type == "Polygon" and g.area > SLIVER]
    lap("water")
    for qs in (survey, beds, plots, water):
        on_the_grid(qs)
    S, B, P, Wp = (shapely.union_all([q["g"] for q in qs], grid_size=GRID) if qs else Polygon() for qs in (survey, beds, plots, water))
    B0 = polygonal(shapely.set_precision(B0, GRID))
    lap("on the grid")
    cover = shapely.union_all([S, B, P, Wp], grid_size=GRID)
    terrain = polygonal(box.difference(cover, grid_size=GRID))
    rep["strips joined to plots"] = {"pieces": strips["pieces"], "m2": round(strips["area"], 1)}
    tp = [g for g in shapely.get_parts(terrain) if g.geom_type == "Polygon"]
    thin = [g for g in tp if 2 * g.area / max(g.length, 1e-9) < 2 * GAP]
    rep["terrain pieces under 2 cm wide"] = {"pieces": len(thin), "m2": round(sum(g.area for g in thin), 2)}
    t_classes = time.time() - t0
    if mesh is None:
        import city_terrain
        mesh, key = city_terrain.cached()
    else:
        key = os.path.basename(os.path.normpath(mesh))
    x, y, z, T = mesh_in_box(mesh, box)
    windows = list(windows)
    if beds:  # (a picture of the largest bed piece: the survey holds most of the beds, PLACES show none)
        c = max(beds, key=lambda q: q["g"].area)["g"].representative_point()
        rep["bed window"] = [c.x - WINDOW / 2, c.y - WINDOW / 2, c.x + WINDOW / 2, c.y + WINDOW / 2]
        windows.append(rep["bed window"])
    win = shapely.union_all([shapely.box(*w) for w in windows]) if windows else None
    t1 = time.time()
    cut = cut_terrain(x, y, T, cover, box, threads, win, geometry)
    mesh_area = cut["kept_area"] + cut["new_area"]
    A = box.area
    areas = {"survey": S.area, "street": 0.0, "bed": B.area, "plot": P.area, "water": Wp.area, "terrain": terrain.area}
    over = {"survey/bed": S.intersection(B).area, "survey/plot": S.intersection(P).area, "bed/plot": B.intersection(P).area,
            "terrain/the rest": terrain.intersection(cover).area}
    rep.update({
        "classes": {c: {"km2": round(areas[c] / 1e6, 4), "share %": round(100 * areas[c] / A, 3),
                        "pieces": {"survey": len(survey), "street": 0, "bed": len(beds), "plot": len(plots), "water": len(water),
                                   "terrain": len(shapely.get_parts(terrain))}[c]} for c in CLASSES},
        "cover": {"sum of the classes over the box, %": round(100 * sum(areas.values()) / A, 5),
                  "overlap between classes, cm²": {k: round(v * 1e4, 3) for k, v in over.items()}},
        "beds": blog,
        "terrain": {"mesh": key, "triangles in the box": cut["triangles"], "dropped (under the classes above)": cut["dropped"],
                    "cut": cut["cut"], "their remains, triangles": cut["new"], "kept": cut["kept"],
                    "after": cut["kept"] + cut["new"],
                    "mesh area over the terrain's, %": round(100 * mesh_area / max(terrain.area, 1), 4),
                    "slivers left out, m²": round(cut["lost_area"], 3)},
        "seconds": {"classes": round(t_classes, 1), "of them": tm, "terrain cut": round(time.time() - t1, 1), "all": round(time.time() - t0, 1)},
    })
    pieces = {"survey": survey, "street": [], "bed": beds, "plot": plots, "water": water, "terrain": terrain}
    rep["water"] = {"OSM water reaching the box, km2": round(W.area / 1e6, 4), "islands": sum(len(g.interiors) for g in
                    shapely.get_parts(W) if g.geom_type == "Polygon"), "weirs, dams and lock gates": len(cuts)}
    rep["rail places"] = rail_places(ln, L, pieces)
    if geometry:  # (for the mesh, tools/ground_mesh.py: the box, the beds' outline on the ground, the city mesh's
        # triangles in the box, those kept whole, the remains of those cut and those under the classes above)
        pieces["_"] = {"L": L, "D": D, "box": box, "beds outline": B0, "x": x, "y": y, "z": z, "T": T, "water": W, "cuts": cuts,
                       "kept": cut["kept_ids"], "remains": cut["remains"], "under": cut["under_ids"]}
    return pieces, rep, cut["win"]


def class_at(pieces, x, y):
    pt = Point(x, y)
    for c in ("survey", "bed", "plot", "water"):
        for q in pieces[c]:
            if q["g"].covers(pt):
                return c + (f" ({q['c']}, area {q['area']})" if c == "survey" else f" (tracks {q['tracks']})" if c == "bed"
                            else f" (building {q['building']})" if c == "plot" else "")
    return "terrain" if pieces["terrain"].covers(pt) else "outside the box"


def rail_places(ln, L, pieces):
    """#165's and #166's places on this line: the class holding each rail head there (#507's done-when)."""
    from route import Route
    out = []
    rt = Route(L["path"])
    for line, s, sample in RAIL_PLACES:
        if line != ln:
            continue
        x, y, hx, hy = rt.at(s)
        q = {"s": s, "left rail": class_at(pieces, x - hy * GAUGE, y + hx * GAUGE),
             "right rail": class_at(pieces, x + hy * GAUGE, y - hx * GAUGE)}
        if sample:
            q["the issue's sample"] = class_at(pieces, *sample)
        out.append(q)
    return out


def geo_json(g, nd=3):
    """A polygon or multipolygon as [[ring, hole ...] ...], coordinates rounded to mm."""
    def ring(r):
        return [[round(a, nd), round(b, nd)] for a, b in r.coords[:-1]]
    return [[ring(p.exterior)] + [ring(h) for h in p.interiors] for p in shapely.get_parts(g) if p.geom_type == "Polygon"]


def write(ln, pieces, rep):
    """reports/ground-partition/lineN.partition.json, whole."""
    import sources
    from atomic import replacing
    out = {"box": rep["box"], "mesh": rep["terrain"]["mesh"],
           "survey": [{"area": q["area"], "c": q["c"], "g": geo_json(q["g"])} for q in pieces["survey"]],
           "street": [],
           "bed": [{"tracks": q["tracks"], "g": geo_json(q["g"])} for q in pieces["bed"]],
           "plot": [{"building": q["building"], "z": q["z"], "g": geo_json(q["g"])} for q in pieces["plot"]],
           "water": [{"g": geo_json(q["g"])} for q in pieces["water"]],
           "terrain": {k: rep["terrain"][k] for k in ("triangles in the box", "dropped (under the classes above)", "cut", "kept", "after")}}
    out["provenance"] = sources.stamp("ground_partition.py", {
        "survey": sources.single("streets", "zps", len(out["survey"]), "pieces of the survey's level-0 areas"),
        "plot": sources.single("buildings", "osm", len(out["plot"]), "building footprints"),
        "water": sources.single("areas", "osm", len(out["water"]), "pieces of OSM's water areas with their islands"),
        "terrain": sources.single("terrain", "ipr-dtm", rep["terrain"]["after"], "triangles of the city mesh (IPR, its "
                                  "fallbacks inside the city, tools/city_terrain.py)")})
    out["attribution"] = sources.attribution(out["provenance"])
    p = os.path.join(ROOT, "reports", "ground-partition", f"line{ln}.partition.json")
    with replacing(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    return os.path.getsize(p)


# ---------------------------------------------------------------- the pictures
COLORS = {"survey": (120, 120, 128), "street": (200, 160, 100), "bed": (150, 90, 60), "plot": (210, 120, 120),
          "water": (90, 140, 200), "terrain": (130, 175, 110)}


def place_windows(lines_data):
    """The pictures' windows: {name: (line, box)}; the switch fan is the 80 m square with the most switches."""
    out = {}
    for name, ln, stop in PLACES:
        if ln is None:
            best = None
            for l2, L in lines_data.items():
                from route import Route
                rt = Route(L["path"])
                sw = np.array([rt.at(q["s"])[:2] for q in L.get("switches") or [] if "s" in q], float).reshape(-1, 2)
                for c in sw:
                    n = int((np.hypot(*(sw - c).T) < 40).sum())
                    if best is None or n > best[0]:
                        best = (n, l2, c)
            if best:
                out[name] = (best[1], tuple(best[2]))
            continue
        if ln not in lines_data:
            continue
        L = lines_data[ln]
        st = [q for q in L.get("stops") or [] if q.get("name") == stop]
        if st:
            q = st[0]
            p = q.get("p") or q.get("at") or q.get("xy")
            if p is None and "s" in q:
                from route import Route
                p = Route(L["path"]).at(q["s"])[:2]
            out[name] = (ln, tuple(p[:2]))
    return {k: (ln, (c[0] - WINDOW / 2, c[1] - WINDOW / 2, c[0] + WINDOW / 2, c[1] + WINDOW / 2)) for k, (ln, c) in out.items()}


def draw(path, pieces, win_tris, w, px=4):
    """One picture: the classes filled, then a panel per class, the terrain's triangles drawn as lines."""
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = w
    n = int((x1 - x0) * px)
    panels = ("all",) + CLASSES
    im = Image.new("RGB", (n * len(panels), n + 24), (255, 255, 255))
    d = ImageDraw.Draw(im)
    wb = shapely.box(*w)

    def to(ox, xy):
        return [(ox + (a - x0) * px, (y1 - b) * px + 24) for a, b in xy]

    def fill(ox, g, col):
        # (through a mask: a hole shows what lies under the polygon, not white)
        for p in shapely.get_parts(polygonal(g.intersection(wb))):  # (clipped: big triangles reach past the window)
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            m = Image.new("L", im.size, 0)
            dm = ImageDraw.Draw(m)
            dm.polygon(to(ox, p.exterior.coords), fill=255)
            for h in p.interiors:
                dm.polygon(to(ox, h.coords), fill=0)
            im.paste(col, mask=m)
            dark = tuple(max(0, v - 50) for v in col)
            for r in [p.exterior, *p.interiors]:
                d.line(to(ox, r.coords), fill=dark, width=1)
    for k, name in enumerate(panels):
        ox = k * n
        d.text((ox + 4, 4), name, fill=(0, 0, 0))
        for c in ("terrain",) + CLASSES[:-1]:  # (the terrain first: its holes are painted white)
            if name not in ("all", c):
                continue
            if c == "terrain":
                fill(ox, pieces["terrain"], COLORS[c])
                for t in win_tris:
                    for e in shapely.get_parts(shapely.intersection(t.exterior, wb)):
                        if e.geom_type == "LineString":
                            d.line(to(ox, e.coords), fill=(60, 110, 50), width=1)
            else:
                for q in pieces[c]:
                    if q["g"].intersects(wb):
                        fill(ox, q["g"], COLORS[c])
        d.line([(ox + n - 1, 24), (ox + n - 1, n + 24)], fill=(0, 0, 0))
    im.save(path)


# ---------------------------------------------------------------- the plot rule's calibration
def calibrate(lines):
    """Each rule of RULES against the survey's building outlines (ZPS KR Hranice_budovy: their vertices within 1 m of an
    OSM footprint's ring, at least 4, their median height): the error's median and 90th percentile per rule."""
    import gpkg
    from dtm_packages import DTM, select_packages
    from geo import Frame
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    err = {r: [] for r in RULES}
    seen = set()
    for ln in lines:
        if ln not in DTM:
            continue
        L, _ = load(ln)
        foot = [area_poly(b["p"]) for b in L.get("buildings") or [] if len(b.get("p") or []) >= 3]
        foot = [g for g in foot if not g.is_empty]
        boxes = [tuple(np.add(g.bounds, (F.E0, F.N0, F.E0, F.N0))) for g in foot]
        keep = gpkg.near_boxes(boxes, 50)
        pts = []
        for pk in select_packages(ROOT, districts=DTM[ln]):
            t = next((t for t in gpkg.layers(pk.kr) if t.endswith(BUILDINGS_KR)), None)
            if t is None:
                continue
            for f in gpkg.features(pk.kr, t, keep=keep):
                g = f["geom"]
                if not g:
                    continue
                for part in ([g[1]] if g[0] == "LineString" else [p[1] for p in g[1]]):
                    pts += [(a - F.E0, b - F.N0, z) for a, b, z in part if z]
        if not pts:
            continue
        P = np.unique(np.round(np.array(pts), 2), axis=0)
        tree = shapely.STRtree(shapely.points(P[:, :2]))
        for g in foot:
            k = (round(g.centroid.x, 1), round(g.centroid.y, 1))
            if k in seen:
                continue
            seen.add(k)
            idx = tree.query(g.boundary, predicate="dwithin", distance=1.0)
            if len(idx) < 4:
                continue
            ref = float(np.median(P[idx, 2]))
            xy = ring_samples(g)
            z = np.asarray(ipr.sample(xy[:, 0] + F.E0, xy[:, 1] + F.N0), float)
            z = z[np.isfinite(z)]
            if len(z) < 4:
                continue
            for r, f in RULES.items():
                err[r].append(f(z) - ref)
    out = {}
    for r, e in err.items():
        e = np.asarray(e)
        out[r] = {"buildings": len(e), "mean, m": round(float(e.mean()), 3), "median |error|, m": round(float(np.median(np.abs(e))), 3),
                  "p90 |error|, m": round(float(np.percentile(np.abs(e), 90)), 3)}
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line")
    ap.add_argument("--lines")
    ap.add_argument("--calibrate")
    ap.add_argument("--mesh", help="a city mesh folder (default: the current inputs', city_terrain.cached())")
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--no-write", action="store_true", help="the report only, no lineN.partition.json")
    a = ap.parse_args(argv)
    rep_dir = os.path.join(ROOT, "reports", "ground-partition")
    os.makedirs(rep_dir, exist_ok=True)
    if a.calibrate:
        r = calibrate(a.calibrate.split(","))
        print(json.dumps(r, indent=1, ensure_ascii=False))
        json.dump(r, open(os.path.join(rep_dir, "calibration.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        return
    lines = a.lines.split(",") if a.lines else [a.line]
    from baseline_store import HeavyJob
    with HeavyJob("ground_partition"):
        data = {ln: load(ln)[0] for ln in lines}
        wins = place_windows(data)
        allrep = {}
        for ln in lines:
            mine = {k: w for k, (l2, w) in wins.items() if l2 == ln}
            pieces, rep, tris = partition(ln, a.mesh, a.threads, list(mine.values()))
            if not a.no_write:
                rep["file bytes"] = write(ln, pieces, rep)
            if "bed window" in rep:
                mine["bed"] = rep["bed window"]
            for name, w in mine.items():
                p = os.path.join(rep_dir, f"{name}-line{ln}.png")
                wb = shapely.box(*w)
                draw(p, pieces, [t for t in tris if t.intersects(wb)], w)
                rep.setdefault("pictures", []).append(os.path.relpath(p, ROOT).replace(os.sep, "/"))
            with open(os.path.join(rep_dir, f"line{ln}.json"), "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=1, ensure_ascii=False)
            allrep[ln] = rep
            print(json.dumps(rep, indent=1, ensure_ascii=False), flush=True)
    return allrep


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
