"""The survey's decks (areas of level 1 and up) checked against the structures that carry them, kept flat over the
openings under them, and how thick they are (#445). Read by tools/dtm.py; numpy and shapely.

Checked heights. The source's boundary lines of a deck are often shared with level 0 (the wall under it, the street
beside it), and a deck's outline took their heights: on the Krejcárek viaduct (line 37) 53 % of the level-1 vertices
within 12 m of the route lie over 2 m under the rails, a tram area runs from 208.19 to 228.41 m; at Divadelní five of
the nine pieces over the underpass sag to its floor at the portals. A vertex counts as a deck height where it is
within TOL of its structure: the Mosty 3D model's top where the model is (tools/mosty3d.py), else the surveyed rails
(DI, DTMP: tools/dtmp_tracks.py) where they stand on a structure (RAISED over IPR) within REACH. Under it by more, the
vertex takes the structure's height plus the offset the deck's own vertices keep from it (the surveyed bed under the
ballast is 0.73 m under the rails on the Krejcárek viaduct). Only on a deck that has vertices on that structure, or
an area that lies inside a model with every vertex under it (Výtoň's railway on Železniční most); any other level-1
area under a structure is another one (a lower deck) and stays, counted. The model reaches EDGE past its faces: the
survey's outlines and its edges part by up to a metre.

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
# not a deck's surface: a building's roof, a wall's top and foot, steps, and what lies under things (an underpass, a
# tunnel; at level 1 on line 17 by Modřany an underpass area sat 5.5 m under the model's top) or is level (water)
NOT_DECK = {"roof", "wall", "stairs", "underpass", "tunnel", "water"}
# the survey's outlines and Mosty 3D's edges part by up to a metre or so: of the deck vertices left on the ground off a
# model next to its vertices on it (the spikes along Krejcárek's road deck), 223 of 246 on line 37 lie within 1 m of a
# face, 237 within 1.5 m, and all of lines 9 and 17 within 1 m
EDGE = 1.5  # m outside a model's faces: still on it
TRUSS = 1.0  # m off a deck's median top: a truss, a pylon or a portal over the deck, not the deck (Výtoň: 210.4 m on 197.5)
SAG = 0.1  # m under the deck's plane over an opening: the target's tolerance at Divadelní
PLANE_REACH = 15.0  # m from the way under: the deck's vertices that give its plane
# m clear over a footway, a cycleway or steps without maxheight (with MARGIN, 2.3 m); the user, 2026-11-10, from street
# view of the passages: "The underpasses have enough clearance, for walkway I would keep lower limit of 2.2-2.3 and then
# whatever slab it leaves"
WALK = 2.2
SIDEWALK = 10.0  # m from a street's way under a deck: its sidewalk, not a passage of its own
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
        self._foot = {}

    def _faces(self, x, y, pi, ti):
        """z of faces ti at points pi (each face's plane at its point nearest to the point: within it, the point itself)."""
        t = self.tris[ti]
        if not len(ti):
            return np.zeros(0)
        q = shapely.get_coordinates(shapely.shortest_line(shapely.polygons(t[:, :, :2]), shapely.points(x[pi], y[pi])))[0::2]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = (t[:, k].T for k in range(3))
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        ok = np.abs(d) > 1e-9
        d = np.where(ok, d, 1)
        a = ((y1 - y2) * (q[:, 0] - x2) + (x2 - x1) * (q[:, 1] - y2)) / d
        b = ((y2 - y0) * (q[:, 0] - x2) + (x0 - x2) * (q[:, 1] - y2)) / d
        return np.where(ok, a * z0 + b * z1 + (1 - a - b) * z2, -np.inf)

    def top(self, x, y, reach=None, only=None):
        """The highest face over each point and its feature id: (z, id) arrays, NaN and -1 where none. A point within
        `reach` (default EDGE) outside every face takes the highest face that near; `only`: of that feature alone."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        z, fid = np.full(len(x), np.nan), np.full(len(x), -1)
        if self.tree is None or not len(x):
            return z, fid
        reach = EDGE if reach is None else reach
        pts = shapely.points(x, y)
        pi, ti = self.tree.query(pts, predicate="intersects")
        if only is not None:
            pi, ti = pi[self.owner[ti] == only], ti[self.owner[ti] == only]
        if reach > 0:
            miss = np.setdiff1d(np.arange(len(x)), pi)
            if len(miss):
                mi, mt = self.tree.query(shapely.buffer(pts[miss], reach, quad_segs=2), predicate="intersects")
                if only is not None:
                    mi, mt = mi[self.owner[mt] == only], mt[self.owner[mt] == only]
                pi, ti = np.r_[pi, miss[mi]], np.r_[ti, mt]
        if not len(pi):
            return z, fid
        zz = self._faces(x, y, pi, ti)
        o = np.lexsort((zz, pi))  # by point, the highest last
        last = np.r_[pi[o][1:] != pi[o][:-1], True]
        p, k = pi[o][last], o[last]
        good = np.isfinite(zz[k])
        z[p[good]], fid[p[good]] = zz[k][good], self.owner[ti[k][good]]
        return z, fid

    def faces(self, x, y, only=None):
        """Every face of feature `only` over each point (within EDGE where none is right over it): a list of arrays."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = [np.zeros(0) for _ in x]
        if self.tree is None or not len(x):
            return out
        pts = shapely.points(x, y)
        pi, ti = self.tree.query(pts, predicate="intersects")
        miss = np.setdiff1d(np.arange(len(x)), pi)
        if len(miss):
            mi, mt = self.tree.query(shapely.buffer(pts[miss], EDGE, quad_segs=2), predicate="intersects")
            pi, ti = np.r_[pi, miss[mi]], np.r_[ti, mt]
        if only is not None:
            pi, ti = pi[self.owner[ti] == only], ti[self.owner[ti] == only]
        zz = self._faces(x, y, pi, ti)
        for p, z_ in zip(pi, zz):
            out[p] = np.r_[out[p], z_]
        return out

    def footprint(self, fid):
        """A feature's faces in plan (cached)."""
        if fid not in self._foot:
            self._foot[fid] = unary_union(shapely.polygons(self.tris[self.owner == fid][:, :, :2]).tolist()).buffer(EDGE)
        return self._foot[fid]


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
    model: Model; rails: Rails. Returns counts by reason, the areas left under a structure no vertex of their deck is on,
    and the vertices a structure checks with its height there (flatten keeps them within TOL of it):
    {"vertices": {"model": n, "rails": n, "inside": n}, "held": n, "heldAreas": [...], "over": n,
    "checked": {(area, ring, vertex): z}}.

    An area that lies inside a model's faces (its footprint, EDGE wide) with every vertex more than TOL under them is on
    that structure with the survey's ground heights, and takes the model's top: Výtoň's railway and its walkway on
    Železniční most's land span, 5 m over the street (the user, 2026-11-10: "there are really three levels: the highest
    is the railway bridge and walkway alongside. Middle level is the one with our tram tracks and car road, sidewalk
    towards the river. And finally there's the lowest level right next to the water"); the road over the two arches
    on line 22 at 50.0850 N 14.3835 E. Each vertex takes the model's face nearest to its deck's median top (a portal or a
    truss over part of the deck is not the deck), the median where none is within TRUSS."""
    where, xyz = _vertices(areas)
    out = {"vertices": {"model": 0, "rails": 0, "inside": 0}, "held": 0, "heldAreas": [], "over": 0, "checked": set()}
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
    out["checked"] = {where[n]: float(ref[n]) for n in np.flatnonzero(np.isfinite(ref))}
    group = deck_groups(areas)
    ok, by_area, by_class, by_group = set(), {}, {}, {}
    # (a vertex on a model that also agrees with raised rails within REACH counts for the rails too: with the model's
    # EDGE most of Krejcárek's deck is the model's, and its tram areas past the model's side found no deck on the rails)
    on_rail_too = np.isfinite(rz) & (z <= rz + OVER) & (np.abs(z - rz) <= TOL)
    for (ai, _, _), k, o, g, rt, zr in zip(where, key, off, agree, on_rail_too, z - rz):
        gr, c = group.get(ai, ai), areas[ai]["c"]
        for kk, oo, yes in ((k, o, g), (("rails", 0), zr, rt and k != ("rails", 0))):
            if not yes:
                continue
            ok.add((gr, kk))
            by_area.setdefault((ai, kk), []).append(oo)
            by_class.setdefault((gr, c, kk), []).append(oo)
            by_group.setdefault((gr, kk), []).append(oo)
    held = {}
    for n in np.flatnonzero(low):
        ai, ri, vi = where[n]
        k, gr, rn = key[n], group.get(ai, ai), ref[n]
        if (gr, k) not in ok and k[0] == "model":
            # (where two features meet, a vertex near one's face belongs to the one its deck is on: Libeň's viaducts,
            # side by side at 210.3 and 212.0 m)
            for g2, k2 in ok:
                if g2 == gr and k2[0] == "model":
                    zf = model.top(x[n:n + 1], y[n:n + 1], only=k2[1])[0][0]
                    if np.isfinite(zf) and z[n] < zf - TOL:
                        k, rn = k2, zf
                        break
        if (gr, k) not in ok:
            held.setdefault(ai, []).append(k)
            continue
        o = by_area.get((ai, k)) or by_class.get((gr, areas[ai]["c"], k)) or by_group[(gr, k)]
        _ring(areas[ai], ri)[vi][2] = round(float(rn + np.median(o)), 2)
        out["vertices"][k[0]] += 1
    mine = {}
    for n, (ai, _, _) in enumerate(where):
        if ai in held:
            mine.setdefault(ai, []).append(n)
    inside = {}  # (deck, feature): the areas lying inside that feature with every vertex under it
    for ai in list(held):
        ns = mine[ai]
        k = key[ns[0]]
        if k is None or k[0] != "model" or not all(low[n] and key[n] == k for n in ns):
            continue
        poly = shapely.Polygon(np.asarray(areas[ai]["r"], float)[:, :2]).buffer(0)
        if poly.area <= 0 or poly.difference(model.footprint(k[1])).area > 0.1 * poly.area:
            continue
        inside.setdefault((group.get(ai, ai), k[1]), []).append(ai)
    for (gr, f), ais in inside.items():
        # (the deck's level: the median top over all its vertices; each vertex takes its face nearest to it, the median
        # where none is within TRUSS: a portal or a truss over part of the deck, 210.4 m over Výtoň's 197.5 m)
        ns = [n for ai in ais for n in mine[ai]]
        med = float(np.median(ref[ns]))
        fz = model.faces(x[ns], y[ns], only=f)
        for n, zs in zip(ns, fz):
            _, ri, vi = where[n]
            best = zs[np.argmin(np.abs(zs - med))] if len(zs) else med
            _ring(areas[where[n][0]], ri)[vi][2] = round(float(best if abs(best - med) <= TRUSS else med), 2)
        out["vertices"]["inside"] += len(ns)
        for ai in ais:
            del held[ai]
    out["held"] = sum(len(v) for v in held.values())
    for ai, ks in held.items():
        r = np.asarray(areas[ai]["r"], float)[:, :2]
        out["heldAreas"].append({"area": ai, "c": areas[ai]["c"], "n": len(ks), "by": ks[0][0],
                                 "x": round(float(r[:, 0].mean()), 1), "y": round(float(r[:, 1].mean()), 1)})
    return out


def _rings(poly):
    """A polygon's outer ring and holes as coordinate lists (without the closing vertex)."""
    return [np.asarray(poly.exterior.coords)[:-1]] + [np.asarray(h.coords)[:-1] for h in poly.interiors]


def split(areas, model, checked=None):
    """A deck area whose vertices on structures stand at levels more than TOL apart lies over several decks: one piece
    per level, cut along the model's faces at that level (EDGE wide), each piece's vertices on its deck's faces with the
    offset the area's own vertices keep from them; the parts beyond every structure keep their survey heights, the
    slivers between the decks go (in place: the area keeps its index for its first piece, the others are appended).
    Libeň's railway (line 37): the survey's railway areas span three viaducts side by side at 205.7, 210 and 212 m and
    sloped 7 m across the gaps between them (the user, 2026-11-10: "Libeň viaduct's are several different one but they
    should all hold straight across the spans"). checked: check's record, kept true for the pieces.
    Returns {"areas": n split, "pieces": n}."""
    out = {"areas": 0, "pieces": 0}
    if model.tree is None:
        return out
    centroid_z = (model.tris[:, :, 2]).mean(axis=1)
    for ai in range(len(areas)):
        a = areas[ai]
        if a["l"] < 1 or a["c"] in NOT_DECK or len(a["r"]) < 3:
            continue
        r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in a["r"]], float)
        mz = model.top(r[:, 0], r[:, 1])[0]
        on = np.isfinite(mz) & np.isfinite(r[:, 2])
        if on.sum() < 2:
            continue
        zs = np.sort(r[on, 2])
        cuts = np.flatnonzero(np.diff(zs) > TOL)
        if not len(cuts):
            continue
        poly = shapely.Polygon(r[:, :2], [np.asarray(h)[:, :2] for h in a.get("h", []) if len(h) >= 3]).buffer(0)
        near = model.tree.query(poly.buffer(EDGE))
        levels = sorted(np.split(zs, cuts + 1), key=len, reverse=True)
        taken, pieces = shapely.Polygon(), []
        for lv in levels:
            lo, hi, zc = lv.min() - TOL, lv.max() + TOL, float(np.median(lv))
            band = [t for t in near if lo <= centroid_z[t] <= hi]
            if not band:
                continue
            region = unary_union(shapely.polygons(model.tris[band][:, :, :2]).tolist()).buffer(EDGE, join_style="mitre")
            part = poly.intersection(region).difference(taken)
            taken = taken.union(part)
            # (the level's offset from its faces: the area's own vertices at this level)
            own = on & (r[:, 2] >= lv.min()) & (r[:, 2] <= lv.max())
            fz = model.faces(r[own, 0], r[own, 1])
            offs = [z - f[np.argmin(np.abs(f - z))] for z, f in zip(r[own, 2], fz) if len(f)]
            off = float(np.median(offs)) if offs else 0.0
            for g in getattr(part, "geoms", [part]):
                if g.geom_type != "Polygon" or g.area < 1:
                    continue
                g = g.simplify(0.05)
                rings = []
                for ring in _rings(g):
                    fz = model.faces(ring[:, 0], ring[:, 1])
                    z = [round(float(f[np.argmin(np.abs(f - zc))] + off), 2) if len(f) else round(zc, 2) for f in fz]
                    rings.append([[round(float(x), 2), round(float(y), 2), zz] for (x, y), zz in zip(ring, z)])
                pieces.append((rings, True))
        # (beyond every structure: the parts that hold some of the area's own vertices off them, at the survey's heights)
        off_pts = r[~on & np.isfinite(r[:, 2])]
        rest = poly.difference(taken)
        for g in getattr(rest, "geoms", [rest]):
            if g.geom_type != "Polygon" or g.area < 1 or not len(off_pts):
                continue
            inside = shapely.distance(g, shapely.points(off_pts[:, 0], off_pts[:, 1])) < 0.01
            if not inside.any():
                continue  # (a sliver between the decks)
            src = off_pts[inside]
            rings = []
            for ring in _rings(g.simplify(0.05)):
                d = np.hypot(ring[:, None, 0] - src[None, :, 0], ring[:, None, 1] - src[None, :, 1])
                z = src[np.argmin(d, axis=1), 2]
                rings.append([[round(float(x), 2), round(float(y), 2), round(float(zz), 2)] for (x, y), zz in zip(ring, z)])
            pieces.append((rings, False))
        if not pieces:
            continue
        base = {k: v for k, v in a.items() if k not in ("r", "h", "k")}
        if checked is not None:
            for key in [k for k in checked if k[0] == ai]:
                del checked[key]
        for n, (rings, on_structure) in enumerate(pieces):
            piece = {**base, "r": rings[0], **({"h": rings[1:]} if len(rings) > 1 else {})}
            idx = ai if n == 0 else len(areas)
            if n == 0:
                areas[ai] = piece
            else:
                areas.append(piece)
            if checked is not None and on_structure:
                for ri, ring in enumerate(rings):
                    for vi, q in enumerate(ring):
                        checked[(idx, ri, vi)] = q[2]
        out["areas"] += 1
        out["pieces"] += len(pieces)
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
                        "width": width, "decks": over, "foot": t.get("highway") in ("footway", "cycleway", "steps", "path", "pedestrian"),
                        "sidewalk": t.get("footway") == "sidewalk"})
    # a street's sidewalk passes under with it: its opening joins the street's beside it, and the deck over it is the
    # street's (the user, 2026-11-10, on Divadelní's: "there's not really any sidealk from what I can see, only thin kerb
    # alongside each side"; OSM's footway=sidewalk tunnel there lay under its own three pieces of the deck)
    streets = [o for o in out if not o["foot"]]
    for o in [o for o in out if o["sidewalk"]]:
        near = [s for s in streets if s["axis"].distance(o["axis"]) <= SIDEWALK]
        if near:
            s = min(near, key=lambda s: s["axis"].distance(o["axis"]))
            s["decks"] = sorted(set(s["decks"]) | set(o["decks"]))
            s["poly"] = s["poly"].union(o["poly"])
            out.remove(o)
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


def flatten(areas, opens, ground, checked=None):
    """Each opening's decks stay on their plane across it, and are SLAB thick or less by maxheight (in place).
    ground: IPR at city-frame arrays (the floor: the user, 2026-11-10, on the sections: "The lidar floor generally looks
    better and sits lower, have smooth believable curve, so I would prefer that one"); checked: the vertices a structure
    checks and its height there (check's record): the plane lifts none of them over TOL above it (by Hlavní nádraží,
    decks of 195-211 m over the same ways took one plane, which lifted a vertex Mosty 3D holds at 199.5 m to 206.4 m).
    Each area keeps its own plane where it has three of the plane's vertices, else the opening's.
    Returns {"vertices": n, "openings": [...per opening...], "src": {...}}."""
    where, xyz = _vertices(areas)
    out = {"vertices": 0, "openings": [], "src": {}}
    if not len(where):
        return out
    pts = shapely.points(xyz[:, 0], xyz[:, 1])
    cap = np.array([(checked or {}).get(w, np.inf) + TOL for w in where])
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
        sag = inside & (xyz[:, 2] < pz - SAG) & (pz <= cap)
        for n in np.flatnonzero(sag):
            ai, ri, vi = where[n]
            _ring(areas[ai], ri)[vi][2] = round(float(pz[n]), 2)
            xyz[n, 2] = pz[n]
        # (the gap under the deck's plane, less SAG: the deck is drawn between its corners, and the plane through them ran
        # 3 cm over the drawn top at Divadelní; a gap under WALK is no floor the lidar saw: by Hlavní nádraží it reads the
        # station's forecourt over the tram's tunnel, 1.0 m under the deck)
        gap_min = float(np.nanmin(plane(ax[:, 0], ax[:, 1]) - floor)) - SAG
        t, src = SLAB, "default"
        need = o["maxheight"] or (WALK if o["foot"] else None)  # (a walkway without the tag: the clear height to walk)
        if gap_min < WALK:
            src = "unseen"
        elif need and gap_min - need - MARGIN < SLAB:
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
    return {"vertices": {**checked["vertices"], "opening": flat["vertices"]}, "split": checked.get("split", {}),
            "held": checked["held"],
            "heldAreas": checked["heldAreas"], "over": checked["over"], "ramps": n_ramps, "decks": decks,
            "openings": [o for o in flat["openings"] if o.get("sagging") or o.get("src", "default") != "default"]}


def is_short(o):
    """An opening whose deck could not leave maxheight (or WALK over a walkway) + MARGIN under it even at MIN_SLAB."""
    need = o.get("maxheight") or (WALK if o.get("src") == "walk" else 0)
    return o.get("src") in ("maxheight", "walk") and o["clearance"] < need + MARGIN - 1e-6
