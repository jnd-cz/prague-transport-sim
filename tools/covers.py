# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street over a passage the survey has under it (#783). Read by tools/ground_mesh.py and tools/street_profile.py;
numpy and shapely.

Where a street crosses a pedestrian underpass at grade, the survey has the street's areas at level 0 right across
and the passage as areas of its own under them (level -1: `underpass`, its `sidewalk`). IPR's raster is bare earth
with the bridges taken out, and it takes such a cover out too: over the passage it shows the floor. By the tunnel
south of Čechova čtvrť, line 17 s 3084 (-1453, -9105), the survey's roads, verges and tram area stand at
214.7-215.4 m and the raster has 211.2 m in a slot 43 m long and 5-7 m wide. Everything laid on the raster fell into
it: the verges 3.6 m, the generated roads up to 1.8 m (the user's note fb-20261120-153903-93585637, 2026-11-20:
"Looks like a ditch but OSM has pedestrian tunnel here. Both tram tracks and road should lie flat on surface and
tunnel be placed under than ground level.").

The passages. The survey's areas one level under the ground (level -1), and OSM's ways in a tunnel of layer -1 or
above (tunnel_ways: from the local extract; the user's note names OSM's tunnel): the survey has no area under the
cycleway's underpass by line 17 (1787, 2800), a slot 4 m deep across a road, and OSM has the way. The metro's tubes
(level -2, `railway=subway`) are no passages under a street's cover: by them the railway yard north of Hlavní
nádraží, line 9 (1240, -15), has a cutting 3.7 m deep, a track's under the others. A road whose outline stands over the raster with neither near is
left: the garage ramp on Na Vápence, line 37 (3871, -20), has its walls' tops in the road's outline, 2.5 m over the
ramp the raster shows rightly (#779).

The cover. A level-0 area's own outline is the ground where it stands CUT or more over the raster in a slot that
lies over a passage (OVER of it within TOUCH) and closes within LIMIT of it: its outline's triangles (the constrained Delaunay
ones, as ground_mesh.SurveySurface), but for those steeper than GRADE that rise more than SPAN. Such a triangle
joins a point on the cover with one on the floor: the sidewalk of a stair well that the survey draws as one area
with the sidewalk above it, a verge round a portal; it is no surface, and what lies in it stays on the raster. (By
the slope alone the verge's triangle between a kerb's top and its foot 2 m apart, 0.7 m and 35 %, left a hole in the
cover, and the verge a notch 3 m deep.) Stairs and walls are not covers: the
stairs into the passage go down where the raster does. A cut that runs on past LIMIT is no slot under a street:
Nádraží Holešovice, line 17 (1512, 1330), stands on a structure 55 m across that the raster leaves out whole, its
rail area at 193.4 m over 186 m, and the cover of its two underpasses alone would stand as two blocks in it. The
A slot that only touches the passage's end is the open ramp or the stairs down to it, which the survey outlines at
their rim: by Nádraží Braník, line 17 (-2034, -6277), the ramp between the stop and the road, its outline at
197.3 m and its floor 3 m down at the portal, where OSM's tunnel way begins. Where such a ramp joins a slot (the
stairs' ramp at the east end of the tunnel by line 17 (-2471, -7871), 10 m of it), the cover ends REACH from the
passage. The cover holds over the slot and NEAR round it (the raster spreads the slot's faces over 1-1.5 m, and its slot is
wider than the survey's passage: 90 % of its points within 1.2 m of it on line 17), and only where it is the higher
of the two: a road tunnel deep under a hill (Letná, Strahov) has the hill's ground over it in both, and nothing
changes there.

A level-1 street over a passage (#824). Where the passage is at grade with its own street's ground (a road under a
bridgehead), the survey has the street over it at level 1 and the passage's areas at level 0, their outlines the
street's point for point: Národní divadlo's bridgehead, line 9 (-625, -585), road 24 and sidewalks 151-156 at 193.2 m
over Divadelní's underpass (OSM's tunnel way, maxheight 4.4), its roads 18, 16 and 17 on the floor at 187.6-188 m.
The ground fell into the floor, a pit 5 m deep in the street, and the page drew the level-1 areas as slabs over it.
The user, 2026-11-23: "for now we draw the ground as in 783 with future update waiting in 449 to draw the actual low
ground for all the underpasses and then put invented deck cover over them". So a level-1 area is a cover too, judged
apart from level 0's (UPPER: judged together, a bridge's cut beside a level-0 cover ran on past LIMIT, and two of the
lines' covers were lost), and the ground's corners under it lie on it (ground_mesh.build); the page draws no slab of
the areas it holds (covered). A bridge is none: the survey's deck (`deck`) and the areas ON_DECK on one. Under
Slánská's road bridge, line 9 (-8253, -1375), OSM has a footway in a tunnel, and a railway bridge over the tram's
street on line 22 (5490, -3591) is a slot within LIMIT of its footways in a tunnel: as a cover it buried the track.
The level-1 covers on the five lines: Národní divadlo (lines 9, 17, 22, 23), Wilsonova over the route's tram tunnel
by Hlavní nádraží (line 9 (1095, -330)), the railway and the tram's bridge over U Kina and a pedestrian underpass
(line 17 (-2560, -9068), (-2515, -9064), (-2478, -8572)), a platform over Simbirská and Turkmenská (line 22 (2812,
-2572)) and two pedestrian underpasses (line 37 (9247, 996), (9265, 962)).
"""
import json
import os
import sys

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CUT = 2.0  # m: a level-0 outline this far over the raster above a lower area stands on a cover the raster left out
# (a walkway's clearance and its slab: tools/zps_decks.py WALK 2.2 m, MIN_SLAB 0.3 m)
LIMIT = 15.0  # m from the passage: a cut that reaches further is no slot over it (a road tunnel's is 20-30 m across)
TOUCH = 1.0  # m from the passage: a slot's point this near lies over it
REACH = 2.5  # m from the passage: the cover ends here (the raster's slot is up to this much wider than the passage)
OVER = 0.5  # of a slot's points over the passage: less, and it lies before the passage's end (its ramp, its stairs)
MIN_CUT = 4.0  # m2: a smaller cut is the raster's noise at a wall
WAY = 2.5  # m either side of an OSM tunnel way: the passage (a footway's or a cycleway's underpass, 4-5 m across)
NEAR = 3.0  # m round the raster's cut: the cover holds this far (the smear, and the lattice's step)
GRADE = 0.15  # rise over run: an outline triangle steeper, rising more than SPAN, joins the cover with the floor
SPAN = 1.0  # m (half of CUT)
STEP = 0.5  # m: the lattice the cut is looked for on
WINDOW = 2 * LIMIT  # m round a world tile: the cut's parts its points are judged by (#812)
NOT_COVER = {"stairs", "wall", "roof", "water"}
UPPER = (0, 1)  # the levels whose areas can be a cover, each judged on its own
ON_DECK = 0.5  # of a level-1 area's own: on a survey deck of its level this much, it is the bridge's
IN_COVER = 0.5  # of a level-1 area's own: in a cover of its level this much, the ground there is its street
# m: a corner whose triangle lies under a cover takes the cover's plane this near it: the level-0 passage's outline is
# the level-1 street's, point for point (Národní divadlo's sidewalk 138 and road 25), and a corner on it fell a
# fraction of a mm outside the street's triangles and stayed on the floor, a notch 5 m deep at the cover's edge
NEAR_EDGE = 0.05


def _poly(a):
    p = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
    return p if p.is_valid else p.buffer(0)


def _over(A, lv):
    """The areas at level lv that can cover a passage: not NOT_COVER; above level 0 neither a survey deck nor lying
    ON_DECK on one of their level (a bridge, see the module's text)."""
    out = [a for a in A if a.get("l", 0) == lv and len(a["r"]) >= 3 and a.get("c") not in NOT_COVER]
    if lv < 1:
        return out
    decks = [_poly(a) for a in out if a.get("c") == "deck"]
    tree = shapely.STRtree(decks) if decks else None
    keep = []
    for a in out:
        if a.get("c") == "deck":
            continue
        p = _poly(a)
        on = sum(p.intersection(decks[i]).area for i in tree.query(p, predicate="intersects").tolist()) if tree else 0.0
        if on < ON_DECK * p.area:
            keep.append(a)
    return keep


def _triangles(a):
    """An area's outline triangles with heights, (n, 3, 3): but for those steeper than GRADE that rise over SPAN."""
    if any(q[2] is None for q in a["r"]):
        return np.zeros((0, 3, 3))
    g = shapely.Polygon([tuple(q) for q in a["r"]],
                        [[tuple(q) for q in h] for h in a.get("h", []) if len(h) >= 3 and all(p[2] is not None for p in h)])
    if not g.is_valid:
        g = shapely.make_valid(g)
    out = []
    for t in shapely.get_parts(shapely.constrained_delaunay_triangles(g)):
        c = shapely.get_coordinates(t, include_z=True)[:3]
        if c.shape != (3, 3) or not np.isfinite(c).all():
            continue
        n = np.cross(c[1] - c[0], c[2] - c[0])
        if abs(n[2]) > 1e-9 and (np.ptp(c[:, 2]) <= SPAN or np.hypot(n[0], n[1]) / abs(n[2]) <= GRADE):
            out.append(c)
    return np.asarray(out, float).reshape(-1, 3, 3)


def _plane(t, x, y):
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = (t[:, k].T for k in range(3))
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    d = np.where(np.abs(d) > 1e-12, d, 1e-12)
    w0 = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / d
    w1 = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / d
    return w0 * z0 + w1 * z1 + (1 - w0 - w1) * z2


def is_tunnel(t):
    """An OSM way in a tunnel a street may run over at grade: not a building's passage, not the metro."""
    if not ("highway" in t or "railway" in t) or t.get("railway") == "subway" or t.get("tunnel", "no") in ("no", "building_passage"):
        return False
    try:
        return float(str(t.get("layer", "-1")).split(";")[0]) >= -1
    except ValueError:
        return True


def tunnel_ways(box):
    """OSM's ways in a tunnel (is_tunnel) that touch a box (x0, y0, x1, y1) of local metres, as lines; none without
    the local extract (tools/osm_local.py)."""
    try:
        import osm_local
    except ImportError:
        return []
    if not osm_local.available():
        return []
    from geo import Frame
    F = Frame()
    out = []
    for w in osm_local.ways(is_tunnel, bbox=F.bbox([box[:2], box[2:]], 20.0)):
        g = w["geometry"]
        if len(g) >= 2:
            out.append(shapely.LineString(np.column_stack(F.xy([q["lat"] for q in g], [q["lon"] for q in g]))))
    return out


class Covers:
    """The covers of a line's survey D (lineN.dtm.json) over IPR's raster lidar(x, y) (local metres), ways OSM's
    tunnel ways there (tunnel_ways): `places`, each {"at" (the middle of each part of its zone), "zone", "tris",
    "cut m2", "deepest m"}; within box (x0, y0, x1, y1) where one is given."""

    def __init__(self, D, lidar, box=None, ways=()):
        from scipy import ndimage
        from geo import tile_box, tile_index
        A = D["areas"]
        self.places = []
        low = [_poly(a) for a in A if a.get("l", 0) == -1 and len(a["r"]) >= 3] + [w.buffer(WAY, cap_style="flat") for w in ways]
        if box is not None:
            b = shapely.box(*box).buffer(LIMIT + NEAR)
            low = [p for p in low if p.intersects(b)]
        if not low:
            return
        over = {lv: _over(A, lv) for lv in UPPER}
        tree = {lv: shapely.STRtree([_poly(a) for a in over[lv]]) for lv in UPPER}
        parts = shapely.get_parts(shapely.union_all([p.buffer(0.05) for p in low])).tolist()
        for lv, g in ((lv, g) for lv in UPPER for g in parts):
            near = g.buffer(LIMIT + 2 * STEP)
            tris = [_triangles(over[lv][i]) for i in sorted(tree[lv].query(near, predicate="intersects").tolist())]
            tris = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
            if not len(tris):
                continue
            tris = tris[shapely.intersects(shapely.polygons(tris[:, [0, 1, 2, 0], :2]), near)]
            if not len(tris):
                continue
            place = {"tris": tris, "tree": shapely.STRtree(shapely.polygons(tris[:, [0, 1, 2, 0], :2]))}
            # (on STEP's grid, not from the passages' bounds: a larger box takes in a passage joining this one, and from
            # its bounds the lattice moved and the cut with it, hlavni-nadrazi-under-the-magistrala's lidar 3.4 cm, #812)
            x0, y0, x1, y1 = near.bounds
            X, Y = np.meshgrid(np.arange(np.floor(x0 / STEP), np.ceil(x1 / STEP) + 1) * STEP,
                               np.arange(np.floor(y0 / STEP), np.ceil(y1 / STEP) + 1) * STEP)
            k = shapely.contains_xy(near, X.ravel(), Y.ravel())
            d = np.full(X.size, np.nan)
            with np.errstate(invalid="ignore"):
                d[k] = self._own(place, X.ravel()[k], Y.ravel()[k]) - np.asarray(lidar(X.ravel()[k], Y.ravel()[k]), float)
                cut = (d >= CUT).reshape(X.shape)
            if not cut.any():
                continue
            # (the slots: the cut's connected parts that lie over the passage and close within LIMIT of it; each world
            # tile's points judged by the parts of the cut within WINDOW of the tile, so a tile reads that far and no
            # further: the cut along a passage joined by one only a larger box holds was a part of another size, #812)
            far = np.full(cut.shape, np.inf)
            far[cut] = shapely.distance(shapely.points(X[cut], Y[cut]), g)
            sel = np.zeros(cut.shape, bool)
            xs, ys = X[0, :], Y[:, 0]
            te, tn = tile_index(X[cut], Y[cut])
            for e, n_ in sorted(set(zip(te.tolist(), tn.tolist()))):
                bx = tile_box(e, n_)
                c0, c1 = np.searchsorted(xs, bx[0] - WINDOW), np.searchsorted(xs, bx[2] + WINDOW, "right")
                r0, r1 = np.searchsorted(ys, bx[1] - WINDOW), np.searchsorted(ys, bx[3] + WINDOW, "right")
                win, fw = cut[r0:r1, c0:c1], far[r0:r1, c0:c1]
                lab, n = ndimage.label(win, structure=np.ones((3, 3)))
                lc = lab[win]
                size = np.bincount(lc, minlength=n + 1)
                on_it = np.bincount(lc, weights=fw[win] <= TOUCH, minlength=n + 1) >= OVER * np.maximum(size, 1)
                runs_on = np.zeros(n + 1, bool)
                np.logical_or.at(runs_on, lc, fw[win] > LIMIT)
                slot = on_it & ~runs_on & (size * STEP * STEP >= MIN_CUT)
                we, wn = tile_index(X[r0:r1, c0:c1], Y[r0:r1, c0:c1])
                mine = win & (we == e) & (wn == n_)
                sel[r0:r1, c0:c1][mine] = slot[lab[mine]] & (fw[mine] <= REACH)
            if not sel.any():
                continue
            spots = shapely.union_all(shapely.buffer(shapely.points(X[sel], Y[sel]), STEP * 0.75, quad_segs=2))
            place["zone"] = spots.buffer(NEAR, quad_segs=4).intersection(g.buffer(REACH + TOUCH))
            shapely.prepare(place["zone"])
            place.update({"at": [[round(q.centroid.x, 1), round(q.centroid.y, 1)] for q in shapely.get_parts(place["zone"])],
                          "cut m2": round(float(sel.sum()) * STEP * STEP, 1), "deepest m": round(float(d.reshape(X.shape)[sel].max()), 2),
                          "level": lv})
            self.places.append(place)

    @staticmethod
    def _own(place, x, y, near=0.0):
        out = np.full(len(x), np.nan)
        pts = shapely.points(x, y)
        pi, ti = (place["tree"].query(pts, predicate="dwithin", distance=near) if near
                  else place["tree"].query(pts, predicate="intersects"))
        if len(pi):
            np.fmax.at(out, pi, _plane(place["tris"][ti], x[pi], y[pi]))
        return out

    def at(self, x, y, level=None, near=0.0):
        """The cover's height at points, of the covers of one level where one is given; NaN off the covers. near: a
        point this close to a cover's triangle takes its plane (a corner on an outline the cover shares, NEAR_EDGE)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(x.shape, np.nan)
        fx, fy, fo = x.ravel(), y.ravel(), out.reshape(-1)
        for p in self.places:
            if level is not None and p["level"] != level:
                continue
            x0, y0, x1, y1 = p["zone"].bounds
            k = np.flatnonzero((fx >= x0 - near) & (fx <= x1 + near) & (fy >= y0 - near) & (fy <= y1 + near))
            if not len(k):
                continue
            k = k[shapely.dwithin(p["zone"], shapely.points(fx[k], fy[k]), near) if near else shapely.contains_xy(p["zone"], fx[k], fy[k])]
            if len(k):
                fo[k] = np.fmax(fo[k], self._own(p, fx[k], fy[k], near))
        return out

    def covered(self, D, level=1):
        """The indexes of survey D's areas at `level` that can cover (_over) and lie IN_COVER or more in a cover of that
        level: the ground there is their street, and the page draws no slab of theirs (src/groundDraw.js buildDtm)."""
        zones = [p["zone"] for p in self.places if p["level"] == level]
        if not zones:
            return []
        z = shapely.union_all(zones)
        ok = {id(a) for a in _over(D["areas"], level)}
        out = []
        for i, a in enumerate(D["areas"]):
            if id(a) in ok:
                g = _poly(a)
                if g.intersects(z) and g.intersection(z).area >= IN_COVER * g.area:
                    out.append(i)
        return out

    def over(self, lidar):
        """lidar(x, y) with the covers on it: the higher of the two at each point."""
        if not self.places:
            return lidar
        return lambda x, y: np.fmax(np.asarray(lidar(x, y), float), self.at(x, y))


class CoveredIpr:
    """IPR's raster (ipr_dtm.IprDtm) with a line's covers on it: sample(E, N) in S-JTSK, as IprDtm's."""

    def __init__(self, ipr, covers, frame):
        self.ipr, self.covers, self.frame = ipr, covers, frame

    def sample(self, E, N):
        z = np.asarray(self.ipr.sample(E, N), float)
        if not self.covers.places:
            return z
        return np.fmax(z, self.covers.at(np.asarray(E, float) - self.frame.E0, np.asarray(N, float) - self.frame.N0))


def of_line(ln, root=ROOT, lidar=None, box=None):
    """The covers of line ln's survey, within box where one is given."""
    if lidar is None:
        import wall_lines
        lidar = wall_lines.ipr_lidar()
    p = os.path.join(root, "data", f"line{ln}.dtm.json")
    D = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"areas": []}
    if box is None and D["areas"]:
        xy = np.array([q[:2] for a in D["areas"] for q in a["r"]], float)
        bounds = (*xy.min(0), *xy.max(0))
    else:
        bounds = box
    return Covers(D, lidar, box, tunnel_ways(bounds) if bounds is not None else ())


if __name__ == "__main__":
    for ln in sys.argv[1:]:
        C = of_line(ln)
        print(f"line {ln}: {len(C.places)} covers, the raster cut out under {sum(p['cut m2'] for p in C.places):.0f} m2")
        for p in C.places:
            print(f"  {p['at']}: cut {p['cut m2']} m2, deepest {p['deepest m']} m, the cover holds {p['zone'].area:.0f} m2")
