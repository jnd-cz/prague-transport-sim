"""The survey's decks (areas of level 1 and up) checked against the structures that carry them, kept flat over the
openings under them, and how thick they are (#445). Read by tools/dtm.py; numpy and shapely.

Checked heights. The source's boundary lines of a deck are often shared with level 0 (the wall under it, the street
beside it), and a deck's outline took their heights: on the Krejcárek viaduct (line 37) 53 % of the level-1 vertices
within 12 m of the route lie over 2 m under the rails, a tram area runs from 208.19 to 228.41 m; at Divadelní five of
the nine pieces over the underpass sag to its floor at the portals. A vertex counts as a deck height where it is
within TOL of its structure: the Mosty 3D model's top where the model is (tools/mosty3d.py), else the surveyed rails
(DI, DTMP: tools/dtmp_tracks.py) where they stand on a structure (RAISED over IPR) within REACH. Under it by more, the
vertex takes the structure's height plus the offset the deck's own vertices keep from it (the surveyed bed under the
ballast is 0.73 m under the rails on the Krejcárek viaduct). Only on a deck that has vertices on that structure: a
level-1 area wholly under a structure is another one (a lower deck, a railway under a road bridge) and stays, counted.

Openings. Over an OSM way that passes under a deck (`tunnel=*`, `covered=yes`, layer -1 or above: not the metro), the
deck's top stays on its plane across the opening: its length from the way, its width from the survey's level-0
street and kerbs under it (the user, 2026-11-10: "I would take hints from osm tunnel feature and perhaps keep the deck
above from sagging too much, or the zps street+kerb width where the edges shouldn't sag significantly").

Thickness. A deck no model gives a body is SLAB thick, less where the way under it carries `maxheight` and SLAB would
leave less: the gap - maxheight - MARGIN (the user, 2026-11-10: "Clearance is the 4.4 meters plus safety margin. I
would use 1m thick deck by default if it checks out"; "0.1 margin is fine. Good point about using the osm height for
tunnel/covered features"). Divadelní: 5.26 - 4.4 - 0.1 = 0.76 m. Written as the area's `t` where it differs from SLAB.
"""
import re

import numpy as np
import shapely
from shapely.ops import unary_union

# Calibrated where the rails, the model and the survey all exist (the five lines, main 973726c, #445): of the level-1
# vertices within 1.5 m of the rails (1,033) three lie over 2 m under the model's top; of those over 2 m under the
# rails (612) one lies within 2 m of it. Under the rails the survey's vertices gather from -1.0 to +0.5 m and thin out
# to -2.5 m; the sags reach -16 m. The model's top stands up to 1.7 m over the deck (parapets).
TOL = 2.0  # m under the structure: a height taken from the ground or the floor under the deck
REACH = 12.0  # m from a surveyed rail station: the deck that carries the track (the issue's 12 m)
RAISED = 3.0  # m of rail over IPR: the track stands on a structure
OVER = 2.5  # m over the rails: something over the track, not the deck it runs on
NOT_DECK = {"roof", "wall", "stairs"}  # a building's roof, a wall's top and foot, steps: not a deck's surface
SAG = 0.1  # m under the deck's plane over an opening: the target's tolerance at Divadelní
PLANE_REACH = 15.0  # m from the way under: the deck's vertices that give its plane
WALK = 2.5  # m clear over a footway or a cycleway without maxheight (the plane's vertices stand higher)
SLAB, MARGIN, MIN_SLAB = 1.0, 0.1, 0.3  # m: the default deck, the clearance's margin, the thinnest the page draws
STREET = {"road", "sidewalk", "tram", "parking", "cycle", "island", "paved", "platform"}
RAMP_OVER, RAMP_LOW = 4.0, 1.0  # a deck area this far over IPR somewhere and within RAMP_LOW of it elsewhere: a ramp


class Model:
    """The Mosty 3D models' near-horizontal faces (decks, parapet tops, undersides) and their top at points."""

    def __init__(self, bridges=None):
        tris = bridges.tris if bridges is not None and len(bridges.tris) else np.zeros((0, 3, 3))
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]) if len(tris) else np.zeros((0, 3))
        flat = np.abs(n[:, 2]) > 0.7 * np.maximum(np.linalg.norm(n, axis=1), 1e-12) if len(tris) else np.zeros(0, bool)
        self.tris = tris[flat]
        self.owner = np.asarray(bridges.ids)[bridges.owner[flat]] if len(self.tris) else np.zeros(0, int)
        self.tree = shapely.STRtree(shapely.polygons(self.tris[:, :, :2])) if len(self.tris) else None

    def top(self, x, y):
        """The highest face over each point and its feature id: (z, id) arrays, NaN and -1 where none."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        z, fid = np.full(len(x), np.nan), np.full(len(x), -1)
        if self.tree is None or not len(x):
            return z, fid
        pi, ti = self.tree.query(shapely.points(x, y), predicate="intersects")
        if not len(pi):
            return z, fid
        t = self.tris[ti]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = (t[:, k].T for k in range(3))
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        ok = np.abs(d) > 1e-9
        d = np.where(ok, d, 1)
        a = ((y1 - y2) * (x[pi] - x2) + (x2 - x1) * (y[pi] - y2)) / d
        b = ((y2 - y0) * (x[pi] - x2) + (x0 - x2) * (y[pi] - y2)) / d
        zz = np.where(ok, a * z0 + b * z1 + (1 - a - b) * z2, -np.inf)
        o = np.lexsort((zz, pi))  # by point, the highest last
        last = np.r_[pi[o][1:] != pi[o][:-1], True]
        p, k = pi[o][last], o[last]
        good = np.isfinite(zz[k])
        z[p[good]], fid[p[good]] = zz[k][good], self.owner[ti[k][good]]
        return z, fid


class Rails:
    """Surveyed rail stations (zps_ground.rail_points) that stand on a structure: RAISED over IPR."""

    def __init__(self, rails, ground):
        x, y, z = (np.asarray(v, float) for v in rails)
        g = np.asarray(ground(x, y), float) if len(x) else np.zeros(0)
        keep = np.isfinite(g) & (z - g > RAISED)
        self.x, self.y, self.z = x[keep], y[keep], z[keep]
        self.tree = shapely.STRtree(shapely.points(self.x, self.y)) if len(self.x) else None

    def at(self, x, y):
        """Top of rail of the nearest raised station within REACH of each point, NaN where none."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(len(x), np.nan)
        if self.tree is None or not len(x):
            return out
        pi, si = self.tree.query_nearest(shapely.points(x, y), max_distance=REACH)
        first = np.r_[True, pi[1:] != pi[:-1]]
        out[pi[first]] = self.z[si[first]]
        return out


def _polys(areas, keep):
    return {i: shapely.Polygon(np.asarray(a["r"], float)[:, :2]).buffer(0) for i, a in enumerate(areas)
            if keep(a) and len(a["r"]) >= 3}


def deck_groups(areas):
    """Connected decks: level-1+ areas (not NOT_DECK) whose outlines touch, as {area index: group}."""
    polys = _polys(areas, lambda a: a["l"] >= 1 and a["c"] not in NOT_DECK)
    ids = list(polys)
    parent = {i: i for i in ids}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    if ids:
        tree = shapely.STRtree([polys[i].buffer(0.3) for i in ids])
        for a, b in zip(*tree.query([polys[i] for i in ids], predicate="intersects")):
            parent[root(ids[a])] = root(ids[b])
    return {i: root(i) for i in ids}


def _vertices(areas):
    """(area, ring, vertex) and x, y, z of every deck vertex with a height."""
    where, xyz = [], []
    for ai, a in enumerate(areas):
        if a["l"] < 1 or a["c"] in NOT_DECK:
            continue
        for ri, r in enumerate([a["r"], *a.get("h", [])]):
            for vi, q in enumerate(r):
                if q[2] is not None:
                    where.append((ai, ri, vi))
                    xyz.append(q[:3])
    return where, np.asarray(xyz, float).reshape(-1, 3)


def _ring(a, ri):
    return a["r"] if ri == 0 else a["h"][ri - 1]


def check(areas, model, rails):
    """Level-1+ vertices more than TOL under their structure take its height and their deck's offset from it (in place).
    model: Model; rails: Rails. Returns counts by reason and the areas left under a structure no vertex of their deck
    is on: {"vertices": {"model": n, "rails": n}, "held": n, "heldAreas": [...], "over": n}."""
    where, xyz = _vertices(areas)
    out = {"vertices": {"model": 0, "rails": 0}, "held": 0, "heldAreas": [], "over": 0}
    if not len(where):
        return out
    x, y, z = xyz.T
    mz, mid = model.top(x, y)
    rz = rails.at(x, y)
    on_model = np.isfinite(mz)
    on_rails = ~on_model & np.isfinite(rz) & (z <= rz + OVER)
    ref = np.where(on_model, mz, np.where(on_rails, rz, np.nan))
    key = [("model", int(f)) if m else ("rails", 0) if r else None for m, f, r in zip(on_model, mid, on_rails)]
    off = z - ref
    agree = np.abs(off) <= TOL
    low = off < -TOL
    out["over"] = int((off > TOL).sum())
    group = deck_groups(areas)
    ok, by_area, by_class, by_group = set(), {}, {}, {}
    for (ai, _, _), k, o, g in zip(where, key, off, agree):
        if not g:
            continue
        gr, c = group.get(ai, ai), areas[ai]["c"]
        ok.add((gr, k))
        by_area.setdefault((ai, k), []).append(o)
        by_class.setdefault((gr, c, k), []).append(o)
        by_group.setdefault((gr, k), []).append(o)
    held = {}
    for n in np.flatnonzero(low):
        ai, ri, vi = where[n]
        k, gr = key[n], group.get(ai, ai)
        if (gr, k) not in ok:
            held.setdefault(ai, []).append(k)
            continue
        o = by_area.get((ai, k)) or by_class.get((gr, areas[ai]["c"], k)) or by_group[(gr, k)]
        _ring(areas[ai], ri)[vi][2] = round(float(ref[n] + np.median(o)), 2)
        out["vertices"][k[0]] += 1
    out["held"] = sum(len(v) for v in held.values())
    for ai, ks in held.items():
        r = np.asarray(areas[ai]["r"], float)[:, :2]
        out["heldAreas"].append({"area": ai, "c": areas[ai]["c"], "n": len(ks), "by": ks[0][0],
                                 "x": round(float(r[:, 0].mean()), 1), "y": round(float(r[:, 1].mean()), 1)})
    return out


def maxheight(tags):
    """OSM's maxheight in metres, None where it is missing, `default`, `none` or not a number."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(m)?\s*$", str(tags.get("maxheight", "")).replace(",", "."))
    return float(m.group(1)) if m else None


def is_under(t):
    """An OSM way that may pass under a deck at grade: a tunnel or a covered way, layer -1 or above (not the metro's)."""
    if not ("highway" in t or "railway" in t) or t.get("railway") == "subway":
        return False
    if t.get("tunnel", "no") == "no" and t.get("covered", "no") == "no":
        return False
    try:
        return float(str(t.get("layer", "0")).split(";")[0]) >= -1
    except ValueError:
        return True


def openings(ways, areas, frame):
    """The ways under the decks: [{"way", "name", "maxheight", "axis" (the way under the decks), "poly" (the opening:
    the survey's level-0 street areas the way crosses there, else the way 3 m wide), "width" ("survey" or "way"),
    "decks" (area indices over it)}]. ways: osm_local.ways results; frame: tools/geo.Frame."""
    decks = _polys(areas, lambda a: a["l"] >= 1 and a["c"] not in NOT_DECK)
    if not decks:
        return []
    ids = list(decks)
    dtree = shapely.STRtree([decks[i] for i in ids])
    ground = _polys(areas, lambda a: a["l"] == 0 and a["c"] in STREET)
    gids = list(ground)
    gtree = shapely.STRtree([ground[i] for i in gids]) if gids else None
    out = []
    for w in ways:
        g, t = w["geometry"], w["tags"]
        if len(g) < 2 or not is_under(t):
            continue
        ln = shapely.LineString(np.column_stack(frame.xy([q["lat"] for q in g], [q["lon"] for q in g])))
        over = [ids[k] for k in dtree.query(ln, predicate="intersects")]
        if not over:
            continue
        cover = unary_union([decks[i] for i in over]).buffer(1.0)
        axis = ln.intersection(cover)
        if axis.length < 1:
            continue
        crossed = [ground[gids[k]] for k in gtree.query(axis, predicate="intersects")] if gtree is not None else []
        poly = unary_union(crossed).intersection(cover) if crossed else shapely.Polygon()
        width = "survey"
        if poly.area < 1:
            poly, width = axis.buffer(1.5).intersection(cover), "way"
        over = [i for i in over if decks[i].intersection(poly).area > 0.5]
        if over:
            out.append({"way": w["id"], "name": t.get("name"), "maxheight": maxheight(t), "axis": axis, "poly": poly,
                        "width": width, "decks": over, "foot": t.get("highway") in ("footway", "cycleway", "steps", "path", "pedestrian")})
    return out


def _plane(pts):
    """z = a + b x + c y through points (least squares), the median where they don't span a plane."""
    p = np.asarray(pts, float)
    c = p[:, :2].mean(axis=0)
    A = np.column_stack([np.ones(len(p)), p[:, 0] - c[0], p[:, 1] - c[1]])
    if len(p) >= 3 and np.linalg.matrix_rank(A, tol=0.5) == 3:
        k = np.linalg.lstsq(A, p[:, 2], rcond=None)[0]
        return lambda x, y: k[0] + k[1] * (np.asarray(x) - c[0]) + k[2] * (np.asarray(y) - c[1])
    m = float(np.median(p[:, 2]))
    return lambda x, y: np.full(np.shape(x), m)


def flatten(areas, opens, ground):
    """Each opening's decks stay on their plane across it, and are SLAB thick or less by maxheight (in place).
    ground: IPR at city-frame arrays. Returns {"vertices": n, "openings": [...per opening...]}."""
    where, xyz = _vertices(areas)
    out = {"vertices": 0, "openings": [], "src": {}}
    if not len(where):
        return out
    pts = shapely.points(xyz[:, 0], xyz[:, 1])
    for o in opens:
        ax = np.array([o["axis"].interpolate(f, normalized=True).coords[0]
                       for f in np.linspace(0, 1, max(2, int(o["axis"].length) + 1))])
        floor = np.asarray(ground(ax[:, 0], ax[:, 1]), float)
        if not np.isfinite(floor).any():
            continue
        top_floor = float(np.nanmax(floor))
        clear = (o["maxheight"] + MARGIN + MIN_SLAB) if o["maxheight"] else (WALK + MIN_SLAB) if o["foot"] else 4.0 + MIN_SLAB
        near = shapely.distance(pts, o["axis"]) <= PLANE_REACH
        mine = np.array([where[n][0] in o["decks"] for n in range(len(where))])
        cand = near & mine & (xyz[:, 2] >= top_floor + clear)
        rec = {"way": o["way"], "name": o["name"], "maxheight": o["maxheight"], "width": o["width"], "areas": len(o["decks"])}
        if cand.sum() < 1:
            rec["plane"] = None  # (no vertex of the deck stands clear of the way: nothing to keep it on)
            out["openings"].append(rec)
            continue
        plane = _plane(xyz[cand])
        inside = mine & (shapely.distance(pts, o["poly"]) <= 0.5)
        pz = plane(xyz[:, 0], xyz[:, 1])
        sag = inside & (xyz[:, 2] < pz - SAG)
        for n in np.flatnonzero(sag):
            ai, ri, vi = where[n]
            _ring(areas[ai], ri)[vi][2] = round(float(pz[n]), 2)
            xyz[n, 2] = pz[n]
        # (the gap under the lowest of the deck's corners over the opening near each point of the way: the deck is drawn
        # between its corners, and the plane through them ran 3 cm over the drawn top at Divadelní)
        corner = pts[inside]
        top = np.array([np.min(xyz[inside, 2][shapely.distance(corner, shapely.Point(p)) <= PLANE_REACH], initial=np.inf)
                        for p in ax])
        gap = np.where(np.isfinite(top), top, plane(ax[:, 0], ax[:, 1])) - floor
        gap_min = float(np.nanmin(gap))
        t, src = SLAB, "default"
        need = o["maxheight"] or (WALK if o["foot"] else None)  # (a walkway without the tag: the clear height to walk)
        if need and gap_min - need - MARGIN < SLAB:
            t, src = max(MIN_SLAB, round(gap_min - need - MARGIN, 2)), "maxheight" if o["maxheight"] else "walk"
            for ai in o["decks"]:
                if t < areas[ai].get("t", SLAB):
                    areas[ai]["t"], out["src"][ai] = t, src
        out["vertices"] += int(sag.sum())
        rec.update({"sagging": int(sag.sum()), "gap": round(gap_min, 2), "t": t, "src": src,
                    "clearance": round(gap_min - t, 2)})
        out["openings"].append(rec)
    return out


def ramps(areas, ground):
    """Deck-class areas that stand RAMP_OVER over IPR somewhere and within RAMP_LOW of it (or under it) elsewhere: the
    ramps to the abutments the survey draws as one area with the deck (kept as they are)."""
    n = 0
    for a in areas:
        if a["l"] < 1 or a["c"] != "deck":
            continue
        r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in a["r"]], float)
        d = r[:, 2] - np.asarray(ground(r[:, 0], r[:, 1]), float)
        if np.nanmax(d, initial=-np.inf) >= RAMP_OVER and np.nanmin(d, initial=np.inf) <= RAMP_LOW:
            n += 1
    return n


def thickness(areas, model, flat):
    """The decks (deck_groups) by where their thickness comes from: a model under them (its body, W4), maxheight or the
    clear height to walk over the way under them (flatten's record), else the default SLAB."""
    rank = {"model": 0, "maxheight": 1, "walk": 2, "default": 3}
    src = {}
    for ai, g in deck_groups(areas).items():
        r = np.asarray([q[:2] for q in areas[ai]["r"]], float)
        s = "model" if np.isfinite(model.top(r[:, 0], r[:, 1])[0]).any() else flat.get("src", {}).get(ai, "default")
        src[g] = min(src.get(g, "default"), s, key=rank.get)
    out = dict.fromkeys(rank, 0)
    for s in src.values():
        out[s] += 1
    return out


def summary(checked, flat, n_ramps, decks):
    """The build's record (provenance checks.decks)."""
    return {"vertices": {**checked["vertices"], "opening": flat["vertices"]}, "held": checked["held"],
            "heldAreas": checked["heldAreas"], "over": checked["over"], "ramps": n_ramps, "decks": decks,
            "openings": [o for o in flat["openings"] if o.get("sagging") or o.get("src", "default") != "default"]}


def is_short(o):
    """An opening whose deck could not leave maxheight (or WALK over a walkway) + MARGIN under it even at MIN_SLAB."""
    need = o.get("maxheight") or (WALK if o.get("src") == "walk" else 0)
    return o.get("src") in ("maxheight", "walk") and o["clearance"] < need + MARGIN - 1e-6
