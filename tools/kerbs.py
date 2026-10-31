"""Kerbs for the surveyed street areas (#21): one height becomes two.

The ZPS survey records a kerb as one 3D line (the boundary of the traffic area) with one height, and
the road and the sidewalk share its vertices, so tools/dtm.py gave both the same height: no kerb, and
a sidewalk at road level along its edge. Measured on lines 17 and 22 (#21): the line is the kerb's
foot along sidewalks (IPR 1.5 m into the road -0.005 / +0.006 m, into the sidewalk +0.095 / +0.109 m)
and the top edge along line 17's platforms (+0.17 m over the road). So, per raised area (sidewalk,
island, platform) that shares vertices with a carriageway:
  which side the line belongs to: the IPR terrain 1 m to both sides of the line (the side level with
    it), else the area's own far edge (a sidewalk's building or wall side lies a kerb above a foot
    line, level with a top line);
  the step: KERB for sidewalks and islands (the measured median: the sidewalks' far edges +0.100 m
    over the foot), measured per platform from the terrain;
  the other side moves by the step: a sidewalk's road edge up from the foot, or the road's edge down
    from a top line. Kerb faces are drawn only on the edges shared with the carriageway ("k").
The terrain is only a decision and a check, never a surface point: areas where it disagrees with the
result by more than CHECK over a kerb of CHECK_LEN or more are listed for review.
"""
import math
import statistics

from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

KERB = 0.10  # m: sidewalk over the kerb foot (measured median, #21)
PLATFORM = (0.08, 0.40)  # m: a platform's measured step is kept within this
CHECK, CHECK_LEN = 0.05, 10.0  # m: terrain disagreeing by more than this, along at least this
CARR = {"road", "tram", "parking"}
RAISED = {"sidewalk", "island", "platform"}
SIDE = 1.0  # m: where the terrain is read on either side of the kerb line


def _rings(a):
    return [a["r"]] + a.get("h", [])


def _normal(ring, i):
    p, q = ring[i - 1], ring[(i + 1) % len(ring)]
    tx, ty = q[0] - p[0], q[1] - p[1]
    n = math.hypot(tx, ty)
    return (-ty / n, tx / n) if n > 1e-6 else None


def _sides(a, poly, ring, i, terrain):
    """(terrain 1 m into the raised area, 1 m into the road) minus the vertex height, or None."""
    nv = _normal(ring, i)
    if nv is None:
        return None
    p = ring[i]
    u, v = (p[0] + SIDE * nv[0], p[1] + SIDE * nv[1]), (p[0] - SIDE * nv[0], p[1] - SIDE * nv[1])
    if poly.contains(Point(u)):
        inside, out = u, v
    elif poly.contains(Point(v)):
        inside, out = v, u
    else:
        return None
    zi, zo = float(terrain(*inside)), float(terrain(*out))
    if zi != zi or zo != zo:
        return None
    return zi - p[2], zo - p[2]


def apply(areas, terrain):
    """Kerbs into the ground-level areas, in place. terrain(x, y): IPR height in the city frame (NaN
    outside). Returns the report for the provenance checks."""
    carr = {}
    for a in areas:
        if a["l"] == 0 and a["c"] in CARR:
            for r in _rings(a):
                for p in r:
                    if p[2] is not None:
                        carr.setdefault((p[0], p[1]), []).append(p)
    lowered = set()  # carriageway vertices already moved down to a kerb's foot
    count, steps, review = {}, [], []
    info = []  # per raised area along a carriageway: rings, shared flags, polygon, rises, sides
    for a in areas:
        if a["l"] != 0 or a["c"] not in RAISED:
            continue
        rings = _rings(a)
        shared = [[(p[0], p[1]) in carr and p[2] is not None for p in r] for r in rings]
        if not any(any(s) for s in shared):
            continue
        a["k"] = [[1 if s[i] and s[(i + 1) % len(s)] else 0 for i in range(len(s))] for s in shared]
        poly = Polygon([p[:2] for p in a["r"]], [[p[:2] for p in h] for h in a.get("h", [])])
        if not poly.is_valid:
            poly = poly.buffer(0)
        # the far edge: ring edges with no shared end, at their own surveyed heights
        far = [LineString([r[i][:3], r[(i + 1) % len(r)][:3]]) for r, s in zip(rings, shared)
               for i in range(len(r)) if not s[i] and not s[(i + 1) % len(r)] and r[i][2] is not None
               and r[(i + 1) % len(r)][2] is not None]
        rises, sides = [], []
        tree = STRtree(far) if far else None
        for r, s in zip(rings, shared):
            for i, p in enumerate(r):
                if not s[i]:
                    continue
                if tree is not None:
                    seg = far[tree.nearest(Point(p[0], p[1]))]
                    w = seg.distance(Point(p[0], p[1]))
                    if 1.5 <= w <= 8:
                        (x0, y0, z0), (x1, y1, z1) = seg.coords
                        u = seg.project(Point(p[0], p[1]), normalized=True)
                        rises.append(z0 + (z1 - z0) * u - p[2])
                sd = _sides(a, poly, r, i, terrain)
                if sd:
                    sides.append(sd)
        info.append((a, rings, shared, poly, rises, sides))
    for n, (a, rings, shared, poly, rises, sides) in enumerate(info):
        # which side the line belongs to (the terrain first: it reads both sides of the same line. The
        # far edge decided 109 of line 22's 380 sidewalks the other way, 78 of them with the terrain
        # +0.11 m over the line: a far edge often meets a lawn, a parking area or a wall's foot)
        if len(sides) >= 3:
            foot, basis = abs(statistics.median(b for _, b in sides)) <= abs(statistics.median(i for i, _ in sides)), "terrain"
        elif a["c"] != "platform" and len(rises) >= 3:
            foot, basis = statistics.median(rises) >= KERB / 2, "survey"
        else:
            foot, basis = True, "default"
        step = KERB
        if a["c"] == "platform" and len(sides) >= 3:
            step = min(PLATFORM[1], max(PLATFORM[0], statistics.median(i - o for i, o in sides)))
            steps.append(round(step, 2))
        k = (a["c"], "foot" if foot else "top", basis)
        count[k] = count.get(k, 0) + 1
        for r, s in zip(rings, shared):
            for i, p in enumerate(r):
                if not s[i]:
                    continue
                if foot:
                    p[2] = round(p[2] + step, 3)
                else:
                    for q in carr[(p[0], p[1])]:
                        if id(q) not in lowered:
                            lowered.add(id(q))
                            q[2] = round(q[2] - step, 3)
        # the check: terrain behind the kerb against the result
        if sides:
            res = statistics.median(i - (step if foot else 0) for i, _ in sides)
            length = sum(math.dist(r[i][:2], r[(i + 1) % len(r)][:2]) for r, s in zip(rings, shared)
                         for i in range(len(r)) if s[i] and s[(i + 1) % len(r)])
            if abs(res) > CHECK and length >= CHECK_LEN:
                c = poly.representative_point()
                review.append({"c": a["c"], "x": round(c.x, 1), "y": round(c.y, 1), "kerb": round(length),
                               "terrainOff": round(res, 2), "line": "foot" if foot else "top", "basis": basis})
    return {"kerb": KERB, "areas": {"/".join(k): v for k, v in sorted(count.items())},
            "platformSteps": sorted(steps), "review": review}
