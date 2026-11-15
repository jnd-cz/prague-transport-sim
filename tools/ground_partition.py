# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground partition of a line's box: survey, OSM street, track bed, building plots and terrain (#507, #276 step 3).

    python -P -E tools/ground_partition.py --line 37            # the partition, its report and pictures
    python -P -E tools/ground_partition.py --lines 9,17,22,23,37
    python -P -E tools/ground_partition.py --calibrate 9,17,22,23,37   # the plot height rule against the survey
    (--mesh DIR: a city mesh folder other than the current inputs', for trials)

The decided priority (#15's T1, docs/decisions/2026-11-05-ground-built-offline.md): each class is cut by the ones above
it, so nothing lies under anything else, and the five cover the box once:
- **survey:** the level-0 ground areas of data/lineN.dtm.json (track_styles.ground_area, src/terrain.js groundArea) as
  they are, their kerbs on their rings. Where two overlap, the higher rank holds the overlap (track_styles.RANK, the
  page's SURFACE_RANK), the smaller area between equal ranks (placement.py).
- **street:** OSM's streets outside the survey: none until #301; the terrain fills them.
- **bed:** every drawn track's bed outline (track_beds.outline: its style's width, the middle of the strip to a paired
  track), the tracks merged where they overlap at switches and crossings (#165). A bed sample whose ground (top of rail
  - lift) lies over LEVEL m from IPR's ground is on a structure (a bridge, a deck, a tunnel) and is left out: bridges
  and decks stand on the ground (the user, 2026-11-10), and the terrain stays under them.
- **plot:** OSM's building footprints (lineN.json `buildings`), flat at PLOT_RULE of IPR's ground along the footprint,
  PLOT_OUT m outside it (calibrated on the survey's building outlines, --calibrate).
- **terrain:** the city mesh (tools/city_terrain.py, in the machine cache) cut by the classes above: a triangle under
  them dropped, one across their edges cut and its remains triangulated by shapely's constrained Delaunay
  (tools/bench/ground_cut.py's method, the decision's section 2), the rest kept.

Writes data/lineN.partition.json (read by the next step, #508; not by the game, not deployed: make_dist BUILD_ONLY):
the box, each class's pieces with their source IDs (the survey's area index and class, the bed's track indexes, the
plot's building index and height), the terrain's counts and the mesh's key. reports/ground-partition/: lineN.json
(the report), pictures at the places of PLACES.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import shapely
from shapely.geometry import Point, Polygon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

CLASSES = ("survey", "street", "bed", "plot", "terrain")
LEVEL = 2.5  # m: a bed's ground this far from IPR's lies on a structure (src/world.js LEVEL, a bridge or an underpass)
PLOT_OUT, PLOT_STEP = 0.5, 1.0  # m: the plot height's samples, outside the footprint and along it
PLOT_RULE = "median"  # the plot height (--calibrate on the five lines, 17,240 buildings: |error| median 0.29 m, p90 1.42;
# the 10th percentile 0.49 / 2.13, the lowest 0.67 / 2.48)
RULES = {"min": lambda z: float(np.min(z)), "p10": lambda z: float(np.percentile(z, 10)),
         "p25": lambda z: float(np.percentile(z, 25)), "median": lambda z: float(np.median(z))}
SLIVER = 1e-4  # m²: pieces smaller than this are left out (float noise of the cuts)
TILE = 512.0  # m: the terrain is cut tile by tile, side by side
GAUGE = 0.72  # m: a rail from the axis (track_beds.GAUGE)
# #166's and #165's places: (line, route s, the city-frame sample where the issue gives one)
RAIL_PLACES = (("17", 2352, (-742.275, -8964.692)), ("17", 17128, None), ("9", 1194, None), ("37", 3768, (3920.091, 1082.375)))
# the pictures (#507's done-when): (name, line, a stop's name or a point)
PLACES = (("vystaviste", "17", "Výstaviště"), ("palmovka", "37", "Palmovka"), ("switch-fan", None, None))
WINDOW = 160.0  # m: a picture's side
BUILDINGS_KR = "010000029902_Hranice_budovy"  # the survey's 3D building outlines (ZPS KR), the plot rule's reference


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
def survey_pieces(D, box):
    """The survey's level-0 ground areas inside the box, each without what a higher one holds: [{area, c, g}]."""
    from track_styles import RANK, ground_area
    items = []
    for i, a in enumerate(D.get("areas", [])):
        if not ground_area(a) or len(a["r"]) < 3:
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


def bed_pieces(L, box, ipr, F, log=None):
    """The beds' union inside the box, without their samples on structures: (the union, [(track index, outline)],
    the samples on the ground and on structures). The structure test (|top of rail - lift - IPR| > LEVEL) is logged
    against the route's spans and tunnels where a track runs along the route (log: a dict for the report)."""
    from track_beds import outline
    path = shapely.LineString([p[:2] for p in L["path"]])
    lift = lift_at(L)
    struct = [tuple(v) for v in (L.get("spans") or []) + (L.get("tunnels") or [])]
    outs, n_ground, n_struct = [], 0, 0
    confusion = {"structure, on a span or in a tunnel": 0, "structure, elsewhere": 0, "ground, on a span or in a tunnel": 0,
                 "ground, elsewhere": 0}
    for i, tr in enumerate(L.get("tracks") or []):
        if not tr.get("bed") or len(tr.get("p") or []) < 2 or not tr.get("zs"):
            continue
        xy = bed_samples(tr)
        zs = np.asarray(tr["zs"], float)[:len(xy)]
        pts = shapely.points(xy)
        d = shapely.distance(path, pts)
        s = shapely.line_locate_point(path, pts)
        lf = np.where(d < 3.0, lift(s), 0.0)
        g = np.asarray(ipr.sample(xy[:, 0] + F.E0, xy[:, 1] + F.N0), float)
        ground = ~(np.abs(zs - lf - g) > LEVEL)  # (no lidar: on the ground)
        n_ground += int(ground.sum())
        n_struct += int((~ground).sum())
        on = d < 3.0
        in_s = np.array([any(a <= v <= b for a, b in struct) for v in s]) & on
        for k, (gr, ins) in enumerate(zip(ground.tolist(), in_s.tolist())):
            if on[k]:
                confusion[f"{'ground' if gr else 'structure'}, {'on a span or in a tunnel' if ins else 'elsewhere'}"] += 1
        o = outline(tr, tr["bed"], keep=ground.tolist())
        o = polygonal(o.intersection(box))
        if o.area > SLIVER:
            outs.append((i, o))
    if log is not None:
        log.update({"samples on the ground": n_ground, "samples on structures, left out": n_struct,
                    "along the route (within 3 m): the test against the route's spans and tunnels": confusion})
    union = shapely.union_all([o for _, o in outs]) if outs else shapely.Polygon()
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
    """OSM's footprints inside the box without the classes above and without an earlier footprint: [{building, z, g}].
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
    tree_above = shapely.STRtree(shapely.get_parts(above)) if not above.is_empty else None
    above_parts = shapely.get_parts(above) if not above.is_empty else []
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


def cut_terrain(x, y, T, cover, box, threads=8, window=None):
    """The terrain triangles against the cover (the classes above) and the box, tile by tile side by side (shapely's
    vectorised calls release the GIL): counts and areas, and the triangles inside `window` (a box) for the pictures."""
    tris = shapely.polygons(np.stack([np.column_stack([x[T[:, k]], y[T[:, k]]]) for k in (0, 1, 2, 0)], 1))
    cx, cy = x[T].mean(1), y[T].mean(1)
    tile = np.floor(cx / TILE).astype(np.int64) * 1000003 + np.floor(cy / TILE).astype(np.int64)
    order = np.argsort(tile, kind="stable")
    bounds = np.flatnonzero(np.diff(tile[order])) + 1
    groups = np.split(order, bounds)
    shapely.prepare(box)

    def one(ids):
        P = tris[ids]
        b = shapely.bounds(P)
        bb = (b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max())
        C = shapely.clip_by_rect(cover, *bb)
        inbox = shapely.contains(box, P)
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
             "kept_area": float(shapely.area(P[kept]).sum()), "new": 0, "new_area": 0.0, "lost_area": 0.0, "win": []}
        if cut.any():
            rest = shapely.intersection(shapely.difference(P[cut], C) if not C.is_empty else P[cut], box)
            parts = shapely.get_parts(rest[~shapely.is_empty(rest)])
            parts = parts[np.isin(shapely.get_type_id(parts), (3,))]
            a = shapely.area(parts)
            r["lost_area"] = float(a[a <= SLIVER].sum())
            parts = parts[a > SLIVER]
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
    return tot


# ---------------------------------------------------------------- the run
def partition(ln, mesh=None, threads=8, windows=()):
    """The partition of line ln: (the pieces per class, the report, the terrain triangles in each window)."""
    from geo import Frame
    from ipr_dtm import IprDtm
    t0 = time.time()
    L, D = load(ln)
    F, ipr = Frame(), IprDtm()
    box = line_box(L)
    rep = {"line": ln, "box": [round(v, 2) for v in box.bounds], "box_km2": round(box.area / 1e6, 4)}
    survey = survey_pieces(D, box)
    S = shapely.union_all([q["g"] for q in survey]) if survey else shapely.Polygon()
    blog = {}
    B0, outs = bed_pieces(L, box, ipr, F, blog)
    B = polygonal(B0.difference(S))
    beds = []
    for g in shapely.get_parts(B):
        if g.area > SLIVER:
            beds.append({"tracks": [i for i, o in outs if o.intersects(g)], "g": g})
    above = shapely.union_all([S, B])
    plots = plot_pieces(L, box, above, ipr, F)
    P = shapely.union_all([q["g"] for q in plots]) if plots else shapely.Polygon()
    cover = shapely.union_all([S, B, P])
    terrain = polygonal(box.difference(cover))
    t_classes = time.time() - t0
    if mesh is None:
        import city_terrain
        mesh, key = city_terrain.cached()
    else:
        key = os.path.basename(os.path.normpath(mesh))
    x, y, _, T = mesh_in_box(mesh, box)
    win = shapely.union_all([shapely.box(*w) for w in windows]) if windows else None
    t1 = time.time()
    cut = cut_terrain(x, y, T, cover, box, threads, win)
    mesh_area = cut["kept_area"] + cut["new_area"]
    A = box.area
    areas = {"survey": S.area, "street": 0.0, "bed": B.area, "plot": P.area, "terrain": terrain.area}
    over = {"survey/bed": S.intersection(B).area, "survey/plot": S.intersection(P).area, "bed/plot": B.intersection(P).area,
            "terrain/the rest": terrain.intersection(cover).area}
    rep.update({
        "classes": {c: {"km2": round(areas[c] / 1e6, 4), "share %": round(100 * areas[c] / A, 3),
                        "pieces": {"survey": len(survey), "street": 0, "bed": len(beds), "plot": len(plots),
                                   "terrain": len(shapely.get_parts(terrain))}[c]} for c in CLASSES},
        "cover": {"sum of the classes over the box, %": round(100 * sum(areas.values()) / A, 5),
                  "overlap between classes, cm²": {k: round(v * 1e4, 3) for k, v in over.items()}},
        "beds": blog,
        "terrain": {"mesh": key, "triangles in the box": cut["triangles"], "dropped (under the classes above)": cut["dropped"],
                    "cut": cut["cut"], "their remains, triangles": cut["new"], "kept": cut["kept"],
                    "after": cut["kept"] + cut["new"],
                    "mesh area over the terrain's, %": round(100 * mesh_area / max(terrain.area, 1), 4),
                    "slivers left out, m²": round(cut["lost_area"], 3)},
        "seconds": {"classes": round(t_classes, 1), "terrain cut": round(time.time() - t1, 1), "all": round(time.time() - t0, 1)},
    })
    pieces = {"survey": survey, "street": [], "bed": beds, "plot": plots, "terrain": terrain}
    rep["rail places"] = rail_places(ln, L, pieces)
    return pieces, rep, cut["win"]


def class_at(pieces, x, y):
    pt = Point(x, y)
    for c in ("survey", "bed", "plot"):
        for q in pieces[c]:
            if q["g"].covers(pt):
                return c + (f" ({q['c']}, area {q['area']})" if c == "survey" else f" (tracks {q['tracks']})" if c == "bed"
                            else f" (building {q['building']})")
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
    """data/lineN.partition.json, whole."""
    import sources
    from atomic import replacing
    out = {"box": rep["box"], "mesh": rep["terrain"]["mesh"],
           "survey": [{"area": q["area"], "c": q["c"], "g": geo_json(q["g"])} for q in pieces["survey"]],
           "street": [],
           "bed": [{"tracks": q["tracks"], "g": geo_json(q["g"])} for q in pieces["bed"]],
           "plot": [{"building": q["building"], "z": q["z"], "g": geo_json(q["g"])} for q in pieces["plot"]],
           "terrain": {k: rep["terrain"][k] for k in ("triangles in the box", "dropped (under the classes above)", "cut", "kept", "after")}}
    out["provenance"] = sources.stamp("ground_partition.py", {
        "survey": sources.single("streets", "zps", len(out["survey"]), "pieces of the survey's level-0 areas"),
        "plot": sources.single("buildings", "osm", len(out["plot"]), "building footprints"),
        "terrain": sources.single("terrain", "ipr-dtm", rep["terrain"]["after"], "triangles of the city mesh (IPR, its "
                                  "fallbacks inside the city, tools/city_terrain.py)")})
    out["attribution"] = sources.attribution(out["provenance"])
    p = os.path.join(ROOT, "data", f"line{ln}.partition.json")
    with replacing(p, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    return os.path.getsize(p)


# ---------------------------------------------------------------- the pictures
COLORS = {"survey": (120, 120, 128), "street": (200, 160, 100), "bed": (150, 90, 60), "plot": (210, 120, 120),
          "terrain": (130, 175, 110)}


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
        for p in shapely.get_parts(polygonal(g.intersection(wb))):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            d.polygon(to(ox, p.exterior.coords), fill=col, outline=tuple(max(0, v - 50) for v in col))
            for h in p.interiors:
                d.polygon(to(ox, h.coords), fill=(255, 255, 255))
    for k, name in enumerate(panels):
        ox = k * n
        d.text((ox + 4, 4), name, fill=(0, 0, 0))
        for c in CLASSES:
            if name not in ("all", c):
                continue
            if c == "terrain":
                fill(ox, pieces["terrain"], COLORS[c])
                for t in win_tris:
                    d.line(to(ox, t.exterior.coords), fill=(60, 110, 50), width=1)
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
    ap.add_argument("--no-write", action="store_true", help="the report only, no data/lineN.partition.json")
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
