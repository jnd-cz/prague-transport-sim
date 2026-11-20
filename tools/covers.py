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
touches a passage (within TOUCH) and closes within LIMIT of it: its outline's triangles (the constrained Delaunay
ones, as ground_mesh.SurveySurface), but for those steeper than GRADE that rise more than SPAN. Such a triangle
joins a point on the cover with one on the floor: the sidewalk of a stair well that the survey draws as one area
with the sidewalk above it, a verge round a portal; it is no surface, and what lies in it stays on the raster. (By
the slope alone the verge's triangle between a kerb's top and its foot 2 m apart, 0.7 m and 35 %, left a hole in the
cover, and the verge a notch 3 m deep.) Stairs and walls are not covers: the
stairs into the passage go down where the raster does. A cut that runs on past LIMIT is no slot under a street:
Nádraží Holešovice, line 17 (1512, 1330), stands on a structure 55 m across that the raster leaves out whole, its
rail area at 193.4 m over 186 m, and the cover of its two underpasses alone would stand as two blocks in it. The
cover holds over the slot and NEAR round it (the raster spreads the slot's faces over 1-1.5 m, and its slot is
wider than the survey's passage: 90 % of its points within 1.2 m of it on line 17), and only where it is the higher
of the two: a road tunnel deep under a hill (Letná, Strahov) has the hill's ground over it in both, and nothing
changes there.
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
TOUCH = 1.0  # m from the passage: a slot this near is over it
MIN_CUT = 4.0  # m2: a smaller cut is the raster's noise at a wall
WAY = 2.5  # m either side of an OSM tunnel way: the passage (a footway's or a cycleway's underpass, 4-5 m across)
NEAR = 3.0  # m round the raster's cut: the cover holds this far (the smear, and the lattice's step)
GRADE = 0.15  # rise over run: an outline triangle steeper, rising more than SPAN, joins the cover with the floor
SPAN = 1.0  # m (half of CUT)
STEP = 0.5  # m: the lattice the cut is looked for on
NOT_COVER = {"stairs", "wall", "roof", "water"}


def _poly(a):
    p = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
    return p if p.is_valid else p.buffer(0)


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
        A = D["areas"]
        self.places = []
        low = [_poly(a) for a in A if a.get("l", 0) == -1 and len(a["r"]) >= 3] + [w.buffer(WAY, cap_style="flat") for w in ways]
        if box is not None:
            b = shapely.box(*box).buffer(LIMIT + NEAR)
            low = [p for p in low if p.intersects(b)]
        if not low:
            return
        over = [a for a in A if a.get("l", 0) == 0 and len(a["r"]) >= 3 and a.get("c") not in NOT_COVER]
        tree = shapely.STRtree([_poly(a) for a in over])
        for g in shapely.get_parts(shapely.union_all([p.buffer(0.05) for p in low])):
            near = g.buffer(LIMIT + 2 * STEP)
            tris = [_triangles(over[i]) for i in sorted(tree.query(near, predicate="intersects").tolist())]
            tris = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
            if not len(tris):
                continue
            tris = tris[shapely.intersects(shapely.polygons(tris[:, [0, 1, 2, 0], :2]), near)]
            if not len(tris):
                continue
            place = {"tris": tris, "tree": shapely.STRtree(shapely.polygons(tris[:, [0, 1, 2, 0], :2]))}
            x0, y0, x1, y1 = near.bounds
            X, Y = np.meshgrid(np.arange(x0, x1 + STEP, STEP), np.arange(y0, y1 + STEP, STEP))
            k = shapely.contains_xy(near, X.ravel(), Y.ravel())
            d = np.full(X.size, np.nan)
            with np.errstate(invalid="ignore"):
                d[k] = self._own(place, X.ravel()[k], Y.ravel()[k]) - np.asarray(lidar(X.ravel()[k], Y.ravel()[k]), float)
                cut = (d >= CUT).reshape(X.shape)
            if not cut.any():
                continue
            # (the slots: the cut's connected parts that touch the passage and close within LIMIT of it)
            lab, n = ndimage.label(cut, structure=np.ones((3, 3)))
            lc = lab[cut]
            far = shapely.distance(shapely.points(X[cut], Y[cut]), g)
            touch, runs_on = np.zeros(n + 1, bool), np.zeros(n + 1, bool)
            np.logical_or.at(touch, lc, far <= TOUCH)
            np.logical_or.at(runs_on, lc, far > LIMIT)
            slot = touch & ~runs_on & (np.bincount(lc, minlength=n + 1) * STEP * STEP >= MIN_CUT)
            sel = cut & slot[lab]
            if not sel.any():
                continue
            spots = shapely.union_all(shapely.buffer(shapely.points(X[sel], Y[sel]), STEP * 0.75, quad_segs=2))
            place["zone"] = spots.buffer(NEAR, quad_segs=4)
            shapely.prepare(place["zone"])
            place.update({"at": [[round(q.centroid.x, 1), round(q.centroid.y, 1)] for q in shapely.get_parts(place["zone"])],
                          "cut m2": round(float(sel.sum()) * STEP * STEP, 1), "deepest m": round(float(d.reshape(X.shape)[sel].max()), 2)})
            self.places.append(place)

    @staticmethod
    def _own(place, x, y):
        out = np.full(len(x), np.nan)
        pi, ti = place["tree"].query(shapely.points(x, y), predicate="intersects")
        if len(pi):
            np.fmax.at(out, pi, _plane(place["tris"][ti], x[pi], y[pi]))
        return out

    def at(self, x, y):
        """The cover's height at points; NaN off the covers."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        out = np.full(x.shape, np.nan)
        fx, fy, fo = x.ravel(), y.ravel(), out.reshape(-1)
        for p in self.places:
            x0, y0, x1, y1 = p["zone"].bounds
            k = np.flatnonzero((fx >= x0) & (fx <= x1) & (fy >= y0) & (fy <= y1))
            if not len(k):
                continue
            k = k[shapely.contains_xy(p["zone"], fx[k], fy[k])]
            if len(k):
                fo[k] = np.fmax(fo[k], self._own(p, fx[k], fy[k]))
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
