# SPDX-License-Identifier: AGPL-3.0-or-later
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

The terrain is the wrong reference in most of what that finds: in the maintainer's review of line 17's 19 largest (#136,
#142) 18 were not the kerb's fault. So it decides a side only where it lies within AGREE of the line on one side, and
what it disagrees with leaves the list, counted by why (`notKerb`):
  level: an OSM tunnel, bridge or other layer, or a survey area off level 0, along the kerb (the terrain is an
    underpass floor or an embankment under a bridge);
  wall: a survey wall or terrain edge along the kerb;
  terrain: off by more than AGREE with neither (greenery, terrain older than the street).
A place the maintainer said is a real ramp stays on the list (data/truth.json kerbFacts).

OSM's lowered and flush kerbs are also named on a listed area's card (`osmKerb`).

Lowered kerbs (#303): the survey does not show them. At OSM's kerb=lowered nodes and crossing ends its kerb line has the
code, and the height against its neighbours, of plain kerb (lines 17 and 22: dip median 0.000 / -0.004 m against 0.000 /
0.001 m), while IPR's step there is half a plain kerb's (0.058 / 0.062 m against 0.12 / 0.11 m), at untagged crossing
ends too (0.057 / 0.063 m). So OSM places them: where a crossing way meets a kerb edge, and at a kerb=lowered or flush
node on one; a kerb=* node at the crossing end gives its height (raised: none lowered), an untagged crossing end takes
the norm's crossing kerb (data/truth.json kerbFacts.crossing: ČSN 73 6110, 0.02 m over the crossing's 4 m, ramps of 1:8).
The stretch gets vertices of its own at its ends and its ramps' ends, in the raised area's ring and the carriageway's
that shares the edge; the report lists each stretch with its source (the debug overlay draws them). Platforms keep
their measured step: their crossings are the survey's own ramps.
"""
import bisect
import json
import math
import os
import statistics
from collections import Counter

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree

KERB = 0.10  # m: sidewalk over the kerb foot (measured median, #21)
PLATFORM = (0.08, 0.40)  # m: a platform's measured step is kept within this
CHECK, CHECK_LEN = 0.05, 10.0  # m: terrain disagreeing by more than this, along at least this
CARR = {"road", "tram", "parking"}
RAISED = {"sidewalk", "island", "median", "platform"}
SIDE = 1.0  # m: where the terrain is read on either side of the kerb line
# m: the terrain agrees with a kerb line within this (a platform's largest step, PLATFORM). On the maintainer's
# 19 answers (#142) the five cases where the terrain was the wrong reference and nothing stands near are off by
# 0.61-1.42 m
AGREE = 0.40
# along a kerb: at least SHARE of its points within these of a structure (OSM's lines are centre lines) or an
# off-level area, or a wall or terrain edge. Measured on the 19 answers (#142): the 10 other-level cases have 0.57-1.00
# of their points within them, the terrain-only cases none
NEAR_OSM, NEAR_AREA, NEAR_WALL, SHARE = 8.0, 5.0, 3.0, 0.3
LOW_KERB = ("lowered", "flush")  # OSM's kerb=* values a review card names
NEAR_LOW = 3.0  # m: such a node this near the area's kerb edges


def crossing_rule(truth=None):
    """data/truth.json kerbFacts.crossing: the kerb's height at a crossing (m over the road), the stretch's width (m) and
    its ramps' steepest grade."""
    if truth is None:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "truth.json"), encoding="utf-8") as fh:
            truth = json.load(fh)
    c = truth["kerbFacts"]["crossing"]
    return float(c["kerb"]), float(c["width"]), float(c["ramp"])


try:
    LOW_H, LOW_W, LOW_RAMP = crossing_rule()
except FileNotFoundError:  # (a checkout without data/truth.json, as test_dtm_packages' fixtures: no stretches asked)
    LOW_H = LOW_W = LOW_RAMP = None
# m over the road by OSM's kerb=* at a lowered stretch (raised: no stretch; an untagged crossing end: LOW_H)
LOW_BY_TAG = {"lowered": LOW_H, "rolled": LOW_H, "flush": 0.0, "no": 0.0}
LOWERS = {"sidewalk", "island", "median"}  # (platforms keep their measured step)
CROSSING_END = 3.0  # m: a crossing way's end this near a kerb edge meets it (OSM's end nodes stop short of the survey's)
TAG_NEAR = 2.0  # m: a kerb=* node this near a crossing's meeting point is its kerb
NODE_NEAR = 1.0  # m: a lowered or flush node away from crossings this near a kerb edge lowers it
SAME = 2.0  # m: meeting points this near on one ring are one stretch
SPLIT_MIN = 0.15  # m: a stretch's end this near a vertex uses it instead of a new one
WALKWAYS = ("footway", "path", "cycleway", "pedestrian", "bridleway")


def is_crossing(t):
    """An OSM way a pedestrian or cyclist crosses the road on (footway=crossing, or a walkway with crossing=*)."""
    return (t.get("footway") == "crossing" or t.get("cycleway") == "crossing" or t.get("path") == "crossing"
            or (t.get("highway") in WALKWAYS and t.get("crossing", "no") != "no"))


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


def _share_near(tree, points, reach):
    if tree is None:
        return 0.0
    near = tree.query(points, predicate="dwithin", distance=reach)[0]
    return len(set(near.tolist())) / len(points)


def lines(coords):
    """shapely lines of point lists, without the degenerate ones."""
    out = [LineString(c) for c in coords if len({(p[0], p[1]) for p in c}) > 1]
    return out


def surroundings(areas, walls=(), structures=()):
    """why(points): 'level', 'wall' or None for a kerb's points (x, y). walls and structures: shapely lines."""
    off = [Polygon([p[:2] for p in a["r"]]) for a in areas if a["l"] != 0 and len(a["r"]) > 2]
    off = [g if g.is_valid else g.buffer(0) for g in off]
    trees = [shapely.STRtree(list(g)) if len(g) else None for g in (structures, off, walls)]

    def why(points):
        pts = shapely.points(points)
        if _share_near(trees[0], pts, NEAR_OSM) >= SHARE or _share_near(trees[1], pts, NEAR_AREA) >= SHARE:
            return "level"
        return "wall" if _share_near(trees[2], pts, NEAR_WALL) >= SHARE else None
    return why


def _cum(ring):
    """Distance along a closed ring at each vertex, and the perimeter last."""
    c = [0.0]
    for i in range(len(ring)):
        c.append(c[-1] + math.dist(ring[i][:2], ring[(i + 1) % len(ring)][:2]))
    return c


def _split(ring, cuts):
    """Points into a ring, in place: cuts {edge index: [(t along it, x, y)]}; z interpolated along the edge."""
    out = []
    for i, p in enumerate(ring):
        out.append(p)
        q = ring[(i + 1) % len(ring)]
        for t, x, y in sorted(cuts.get(i, ())):
            z = None if p[2] is None or q[2] is None else round(p[2] + (q[2] - p[2]) * t, 3)
            out.append([x, y, z])
    ring[:] = out


def lowered_stretches(areas, carr, crossings=(), kerb_nodes=()):
    """Lowered kerb stretches (#303) into the sidewalks', islands' and medians' kerb edges, in place: vertices of their
    own at the stretch's ends and its ramps' ends, in the raised ring and in the carriageway ring with the same edge
    (added to carr). crossings: OSM crossing ways (shapely lines); kerb_nodes: OSM kerb=* nodes (x, y, value).
    Returns ({id(raised vertex): how far under KERB its step is}, the stretches, carriageway edges not found)."""
    segs, refs = [], []
    for ai, a in enumerate(areas):
        if a["l"] != 0 or a["c"] not in LOWERS:
            continue
        for ri, r in enumerate(_rings(a)):
            for i, p in enumerate(r):
                q = r[(i + 1) % len(r)]
                if (p[0], p[1]) in carr and (q[0], q[1]) in carr and (p[0], p[1]) != (q[0], q[1]):
                    segs.append(LineString([p[:2], q[:2]]))
                    refs.append((ai, ri, i))
    if not segs or not (len(crossings) or len(kerb_nodes)):
        return {}, [], 0
    if LOW_H is None:
        raise FileNotFoundError("data/truth.json kerbFacts.crossing: the lowered kerb's rule")
    tree = STRtree(segs)
    ntree = STRtree(shapely.points([k[:2] for k in kerb_nodes])) if len(kerb_nodes) else None

    def tag_at(x, y):
        near = ntree.query(Point(x, y), predicate="dwithin", distance=TAG_NEAR) if ntree is not None else []
        return kerb_nodes[min(near, key=lambda j: math.dist(kerb_nodes[j][:2], (x, y)))][2] if len(near) else None

    def on_kerb(P, reach):
        near = tree.query(P, predicate="dwithin", distance=reach)
        if not len(near):
            return None
        k = min(near, key=lambda k: segs[k].distance(P))
        q = segs[k].interpolate(segs[k].project(P))
        return q.x, q.y, k

    meets = []  # (x, y, kerb segment, height over the road or None, source)
    for w in crossings:
        pts = []
        for k in tree.query(w, predicate="intersects"):
            pts += [(g.x, g.y, k) for g in shapely.get_parts(w.intersection(segs[k])) if g.geom_type == "Point"]
        for end in (Point(w.coords[0]), Point(w.coords[-1])):
            m = on_kerb(end, CROSSING_END)
            if m:
                pts.append(m)
        for x, y, k in pts:
            tag = tag_at(x, y)
            if tag == "raised":
                meets.append((x, y, k, None, "osm kerb=raised"))
            elif tag in LOW_BY_TAG:
                meets.append((x, y, k, LOW_BY_TAG[tag], f"osm kerb={tag}"))
            else:
                meets.append((x, y, k, LOW_H, "crossing"))
    for x, y, v in kerb_nodes:
        m = on_kerb(Point(x, y), NODE_NEAR) if v in LOW_BY_TAG else None
        if m:
            meets.append((*m, LOW_BY_TAG[v], f"osm kerb={v}"))
    # (one stretch per place on a ring: a crossing's two ways or its end and its node; crossings first, with their tag)
    by_ring = {}
    for x, y, k, h, src in meets:
        ai, ri, i = refs[k]
        kept = by_ring.setdefault((ai, ri), [])
        if not any(math.dist((x, y), s[:2]) < SAME for s in kept):
            kept.append((x, y, i, h, src))
    stretches, cuts, road_cuts, places = [], {}, {}, {}
    for (ai, ri), kept in by_ring.items():
        a = areas[ai]
        ring = _rings(a)[ri]
        cum = _cum(ring)
        per = cum[-1]
        for x, y, i, h, src in kept:
            stretches.append({"x": round(x, 1), "y": round(y, 1), "c": a["c"], "src": src, "h": h})
            if h is None:
                continue
            # (its place along the ring: points put on the edges keep every distance along it)
            s0 = cum[i] + math.dist(ring[i][:2], (x, y))
            places.setdefault((ai, ri), []).append((s0, h))
            half, ramp = LOW_W / 2, (KERB - h) / LOW_RAMP
            for d in (-half - ramp, -half, half, half + ramp):
                s = (s0 + d) % per
                j = min(len(ring) - 1, bisect.bisect_right(cum, s) - 1)
                p, q = ring[j], ring[(j + 1) % len(ring)]
                L = cum[j + 1] - cum[j]
                if (p[0], p[1]) not in carr or (q[0], q[1]) not in carr or L <= 0:
                    continue
                t = (s - cum[j]) / L
                if t * L < SPLIT_MIN or (1 - t) * L < SPLIT_MIN:
                    continue
                px, py = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                cuts.setdefault((ai, ri), {}).setdefault(j, []).append((t, px, py))
                road_cuts.setdefault(frozenset([(p[0], p[1]), (q[0], q[1])]), []).append(((p[0], p[1]), px, py))
    for (ai, ri), c in cuts.items():
        _split(_rings(areas[ai])[ri], c)
    # (the carriageway rings with the same edge get the same points: the kerb's two sides keep one outline)
    unmatched = len(road_cuts)
    road = {}
    for a in areas:
        if a["l"] == 0 and a["c"] in CARR:
            for r in _rings(a):
                for i, p in enumerate(r):
                    q = r[(i + 1) % len(r)]
                    key = frozenset([(p[0], p[1]), (q[0], q[1])])
                    if key in road_cuts:
                        L = math.dist(p[:2], q[:2])
                        road.setdefault(id(r), (r, {}))[1].setdefault(i, []).extend(
                            (math.dist(p[:2], (x, y)) / L, x, y) for _, x, y in road_cuts[key])
    found = set()
    for r, c in road.values():
        for i in c:
            found.add(frozenset([(r[i][0], r[i][1]), (r[(i + 1) % len(r)][0], r[(i + 1) % len(r)][1])]))
        _split(r, c)
        for p in r:
            if p[2] is not None:
                lst = carr.setdefault((p[0], p[1]), [])
                if not any(q is p for q in lst):
                    lst.append(p)
    unmatched -= len(found & set(road_cuts))
    for key, pts in road_cuts.items():  # (no carriageway edge to share them: the raised side's points still kerb)
        if key not in found:
            for _, x, y in pts:
                carr.setdefault((x, y), [])
    # each kerb vertex's step under KERB: the whole difference over the stretch's width, falling off over its ramps
    drop = {}
    for (ai, ri), at in places.items():
        ring = _rings(areas[ai])[ri]
        cum = _cum(ring)
        per = cum[-1]
        for s0, h in at:
            half, ramp, full = LOW_W / 2, (KERB - h) / LOW_RAMP, KERB - h
            for n, p in enumerate(ring):
                d = abs(cum[n] - s0)
                d = min(d, per - d)
                v = full if d <= half + 1e-6 else full * (1 - (d - half) / ramp) if d < half + ramp else 0.0
                if v > drop.get(id(p), 0.0):
                    drop[id(p)] = v
    return drop, stretches, unmatched


def apply(areas, terrain, why=None, facts=(), low_kerbs=(), crossings=(), kerb_nodes=()):
    """Kerbs into the ground-level areas, in place. terrain(x, y): IPR height in the city frame (NaN
    outside). why: surroundings(...). facts: the maintainer's places (x, y, kind) that stay on the review list.
    low_kerbs: OSM's lowered and flush kerb nodes (x, y, value), named on the list's items. crossings, kerb_nodes:
    OSM's crossing ways and kerb=* nodes, the lowered stretches' places (lowered_stretches).
    Returns the report for the provenance checks."""
    low_tree = shapely.STRtree(shapely.points([k[:2] for k in low_kerbs])) if len(low_kerbs) else None
    carr = {}
    for a in areas:
        if a["l"] == 0 and a["c"] in CARR:
            for r in _rings(a):
                for p in r:
                    if p[2] is not None:
                        carr.setdefault((p[0], p[1]), []).append(p)
    drop, stretches, unmatched = lowered_stretches(areas, carr, crossings, kerb_nodes)
    lowered = set()  # carriageway vertices already moved down to a kerb's foot
    count, steps, review, seen = {}, [], [], set()
    notkerb = {"level": [], "wall": [], "terrain": []}
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
                    sides.append((*sd, drop.get(id(p), 0.0)))
        info.append((a, rings, shared, poly, rises, sides))
    for n, (a, rings, shared, poly, rises, sides) in enumerate(info):
        # which side the line belongs to (the terrain first: it reads both sides of the same line. The
        # far edge decided 109 of line 22's 380 sidewalks the other way, 78 of them with the terrain
        # +0.11 m over the line: a far edge often meets a lawn, a parking area or a wall's foot)
        inside = statistics.median(i for i, _, _ in sides) if sides else None
        road = statistics.median(b for _, b, _ in sides) if sides else None
        if len(sides) >= 3 and min(abs(inside), abs(road)) <= AGREE:
            foot, basis = abs(road) <= abs(inside), "terrain"
        elif a["c"] != "platform" and len(rises) >= 3:
            foot, basis = statistics.median(rises) >= KERB / 2, "survey"
        else:
            foot, basis = True, "default"
        step = KERB
        if a["c"] == "platform" and len(sides) >= 3:
            step = min(PLATFORM[1], max(PLATFORM[0], statistics.median(i - o for i, o, _ in sides)))
            steps.append(round(step, 2))
        k = (a["c"], "foot" if foot else "top", basis)
        count[k] = count.get(k, 0) + 1
        for r, s in zip(rings, shared):
            for i, p in enumerate(r):
                if not s[i]:
                    continue
                # (a lowered stretch's vertex: its step under KERB, lowered_stretches)
                st = step - drop.get(id(p), 0.0)
                if foot:
                    p[2] = round(p[2] + st, 3)
                else:
                    for q in carr[(p[0], p[1])]:
                        if id(q) not in lowered:
                            lowered.add(id(q))
                            q[2] = round(q[2] - st, 3)
        # the check: terrain behind the kerb against the result, on plain kerb only (behind a lowered stretch IPR reads
        # +6 cm, up its ramp. Before #303 those readings were half the median of a sidewalk with many crossings and hid
        # plain kerb standing 13-15 cm: lines 17 / 22 list 280 / 276 areas, 257 / 244 with the crossings' readings in)
        plain = [i for i, _, d in sides if d == 0.0]
        if plain:
            res = statistics.median(i - (step if foot else 0) for i in plain)
            length = sum(math.dist(r[i][:2], r[(i + 1) % len(r)][:2]) for r, s in zip(rings, shared)
                         for i in range(len(r)) if s[i] and s[(i + 1) % len(r)])
            if abs(res) > CHECK and length >= CHECK_LEN:
                c = poly.representative_point()
                item = {"c": a["c"], "x": round(c.x, 1), "y": round(c.y, 1), "kerb": round(length),
                        "terrainOff": round(res, 2), "line": "foot" if foot else "top", "basis": basis}
                key = (a["c"], item["x"], item["y"])
                if key in seen:  # (the same area from two districts' packages)
                    continue
                seen.add(key)
                if low_tree is not None:
                    edges = lines([[r[i][:2], r[(i + 1) % len(r)][:2]] for r, s in zip(rings, shared)
                                   for i in range(len(r)) if s[i] and s[(i + 1) % len(r)]])
                    hits = low_tree.query(edges, predicate="dwithin", distance=NEAR_LOW)[1]
                    tagged = Counter(low_kerbs[i][2] for i in set(hits.tolist()))
                    if tagged:
                        item["osmKerb"] = dict(sorted(tagged.items()))
                fact = next((f for f in facts if poly.buffer(0.5).contains(Point(f["x"], f["y"]))), None)
                pts = [p[:2] for r, s in zip(rings, shared) for i, p in enumerate(r) if s[i]]
                reason = None if fact else (why(pts) if why else None) or ("terrain" if abs(res) > AGREE else None)
                if fact:
                    item["fact"] = fact["kind"]
                (notkerb[reason] if reason else review).append(item)
    low = {"rule": {"kerb": LOW_H, "width": LOW_W, "ramp": LOW_RAMP, "byTag": LOW_BY_TAG},
           "bySource": dict(sorted(Counter(s["src"] for s in stretches).items())),
           "carriagewayEdgesNotFound": unmatched, "stretches": stretches}
    return {"kerb": KERB, "areas": {"/".join(k): v for k, v in sorted(count.items())},
            "platformSteps": sorted(steps), "review": review, "notKerb": notkerb, "lowered": low}
