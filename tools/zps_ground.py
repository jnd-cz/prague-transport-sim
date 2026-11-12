# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's ground-level areas against the lidar (#446): which of the two is wrong where they part.

Read by tools/dtm.py and tools/bench/survey_ground.py.

An area of level 0 lies where lidar saw it unless something covers it (a survey area of level 1 or more, an OSM building,
bridge, tunnel or covered way). Its offset is the median of its outline vertices' heights against IPR's 1 m ground read
INNER m inside the outline (an outline along a retaining wall has the wall's top and foot by turns; inside lies the
area's own ground), its spread the 80th percentile of their distance from that median. An open area whose whole outline
sits OFFSET or more off IPR, steadily, is either the survey's error or a change since IPR's lidar (2023). Two
independent references decide, in this order:
- the tracks surveyed by DI and DTMP, where they run through the area: whichever of IPR and the survey agrees with
  their top of rail;
- DMR 5G (ČÚZK's lidar of 2009-2013): where it agrees with IPR, the ground has stayed the same for a decade and the
  survey alone differs.
Neither deciding, the area is held for the user's review (reports/review/survey-ground.json); their answers are facts in
data/truth.json `surveyGround` keyed by place. An area judged wrong moves by its offset, and so do the same heights at
the same places in the other ground-level areas (they took them from the same survey line).
"""
import math

import numpy as np
import shapely
from shapely.ops import unary_union

from survey_ground_answers import ANSWERS, KIND  # (the review cards' answers, and the verdicts they record)

# Calibrated on the five lines' level-0 areas against DI's and DTMP's top of rail at 2 m stations under open sky
# (tools/bench/survey_ground.py, 2026-11-10): IPR - rail p5/p50/p95 -0.23/-0.04/+0.21 m at worst per line, within
# 0.3 m at 97.8-100 % of the 84,387 stations; the survey within 0.3 m at 86.2-93.5 %. Where the survey was more than
# 0.5 m off the rail (2,849 stations), IPR was within 0.3 m of it at 2,738 (96 %).
OFFSET = 0.5  # m: an area this far from IPR (over twice IPR's own p95 at the rails, three kerbs)
STEADY = 0.3  # m: the spread under which the whole area moved, not a slope, a wall or a few bad points
AGREE = 0.3  # m: a reference agrees with IPR or with the survey
RAIL_MIN = 5  # rail stations in an area for the rails to decide
COVERED = 1 / 3  # share of an area's inner points under a cover that makes it covered
INNER = 1.0  # m: how far inside the outline IPR is read
# A bare-earth model leaves out what its filter takes for objects, and a 1 m raster can't hold a small one: a planter,
# a raised bed, a light well or a short flight of steps (line 37, 2026-11-10: 94 of the 158 areas DMR 5G would have
# moved were under 10 m², 137 under 50 m²). Only an area wide and large enough for lidar to see it as open ground moves.
MIN_M2 = 100.0
MIN_INNER = 2 / 3  # share of its vertices with a point INNER m inside it
# (water: lidar reads its surface, not ground; stairs: a 1 m raster reads another step 1 m in, and they have their
# own rule, #447)
NOT_GROUND = {"wall", "roof", "deck", "tunnel", "underpass", "water", "stairs"}
RAIL_STEP = 2.0  # m between rail stations
# Areas neither the rails nor DMR 5G decide: the user's rule (data/truth.json surveyGround.heldRule), a courtyard to the
# lidar, greenery outside to the survey. A courtyard: OSM buildings within COURT_REACH in COURT_SHARE of COURT_RAYS
# directions from the area's point. On the user's 19 answered cards of 2026-11-10: the courtyards 7 of 9 answered
# lidar; outside, greenery 4 of 7 survey, paved 3 of 3 lidar (14 of 19; "outside to the survey" alone matches 11).
COURT_RAYS, COURT_REACH, COURT_SHARE = 16, 60.0, 0.75
FLOOR = 170.0  # m: no ground under it (tools/sources.py TERRAIN_FLOOR; DI writes 0 for a missing height)


def inner_points(xy):
    """A point INNER m inside the polygon from each vertex, along the bisector of its two edges, and whether it is
    inside (a narrow piece keeps the vertex itself). xy: (n, 2), the ring without its closing point."""
    xy = np.asarray(xy, float)
    poly = shapely.Polygon(xy).buffer(0)
    a = xy - np.roll(xy, 1, axis=0)
    b = np.roll(xy, -1, axis=0) - xy
    a /= np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)
    b /= np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-9)
    nrm = np.column_stack([-(a[:, 1] + b[:, 1]), a[:, 0] + b[:, 0]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    out, inside = xy.copy(), np.zeros(len(xy), bool)
    for sgn in (1, -1):
        q = xy + sgn * INNER * nrm
        ok = ~inside & shapely.contains_xy(poly, q[:, 0], q[:, 1])
        out[ok], inside[ok] = q[ok], True
    return out, inside, poly


def osm_covers(ways, frame):
    """OSM buildings, bridges, tunnels and covered ways (osm_local.ways results) as polygons in the city frame."""
    out = []
    for w in ways:
        g, t = w["geometry"], w["tags"]
        if len(g) < 2:
            continue
        xy = np.column_stack(frame.xy([q["lat"] for q in g], [q["lon"] for q in g]))
        if ("building" in t or t.get("man_made") == "bridge" or is_changing(t)) and len(xy) >= 4 and (xy[0] == xy[-1]).all():
            out.append(shapely.Polygon(xy).buffer(0))
        elif "highway" in t or "railway" in t or "waterway" in t:
            half = 4.0
            if t.get("bridge", "no") != "no":
                try:
                    half = float(str(t.get("width", "")).split()[0]) / 2
                except (ValueError, IndexError):
                    pass
            out.append(shapely.LineString(xy).buffer(half))
    return out


def is_changing(t):
    """OSM's construction sites (the extract is newer than either lidar): their ground may have moved since."""
    return any(t.get(k) == "construction" for k in ("landuse", "building", "highway", "railway"))


def is_cover(t):
    """The OSM tags osm_covers takes (for osm_local.ways)."""
    return ("building" in t or t.get("man_made") == "bridge"
            or (("highway" in t or "railway" in t or "waterway" in t)
                and any(t.get(k, "no") != "no" for k in ("bridge", "tunnel", "covered"))))


def cover_union(areas, osm_polys=()):
    """What lidar can't see through: the survey's areas of level 1 or more and the OSM covers."""
    polys = [shapely.Polygon(np.asarray(a["r"])[:, :2]).buffer(0) for a in areas if a["l"] >= 1 and len(a["r"]) >= 3]
    polys += [p for p in osm_polys if not p.is_empty]
    return unary_union(polys) if polys else shapely.Polygon()


def rail_points(paths):
    """Stations every RAIL_STEP m along surveyed tracks with heights: x, y, top of rail (arrays). paths: records with
    `coords` [(x, y, z)] in the city frame (tools/dtmp_tracks.py di_data / archive_data); a stretch between two
    vertices with heights only."""
    xs, ys, zs = [], [], []
    for p in paths:
        c = [q for q in p["coords"] if len(q) > 2 and q[2] is not None]
        for (x0, y0, z0), (x1, y1, z1) in zip(c, c[1:]):
            if z0 < FLOOR or z1 < FLOOR:
                continue
            n = max(1, int(math.hypot(x1 - x0, y1 - y0) / RAIL_STEP))
            u = np.arange(n) / n
            xs.append(x0 + (x1 - x0) * u)
            ys.append(y0 + (y1 - y0) * u)
            zs.append(z0 + (z1 - z0) * u)
    if not xs:
        return np.zeros(0), np.zeros(0), np.zeros(0)
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs)


def surface_at(r, x, y):
    """The area's surface at a point from its three nearest outline vertices with heights, weighted by 1 / distance."""
    d = np.hypot(r[:, 0] - x, r[:, 1] - y)
    d = np.where(np.isfinite(r[:, 2]), d, np.inf)
    o = np.argsort(d)[:3]
    o = o[np.isfinite(d[o])]
    if not len(o):
        return math.nan
    w = 1 / np.maximum(d[o], 0.1)
    return float((r[o, 2] * w).sum() / w.sum())


def enclosed(x, y, buildings):
    """The share of COURT_RAYS directions from a point in which a building (a geometry, or None) lies within COURT_REACH."""
    if buildings is None or buildings.is_empty:
        return 0.0
    a = np.arange(COURT_RAYS) * 2 * np.pi / COURT_RAYS
    rays = [shapely.LineString([(x, y), (x + COURT_REACH * np.cos(t), y + COURT_REACH * np.sin(t))]) for t in a]
    return float(np.mean([buildings.intersects(ray) for ray in rays]))


def held_verdict(v, rule, buildings):
    """The user's rule for an area nothing else decides: the verdict, or None without the rule."""
    if not rule:
        return None
    v["enclosed"] = round(enclosed(v["x"], v["y"], buildings), 2)
    if v["enclosed"] >= COURT_SHARE:
        return rule["courtyard"]
    return rule["outsideGreen"] if v["c"] == "green" else rule["outside"]


def facts_to_areas(areas, facts, frame):
    """{area index: verdict} for the user's answers: the ground-level area that holds the answer's point (its holes
    left out: a courtyard's lawn is a hole in the sidewalk around it), of the card's class, the nearest the card's size."""
    if not facts:
        return {}
    ground = [(i, a) for i, a in enumerate(areas) if a["l"] == 0 and a["c"] not in NOT_GROUND and len(a["r"]) >= 3]
    polys = [with_holes(a) for _, a in ground]
    outer = [shapely.Polygon(np.asarray(a["r"])[:, :2]).buffer(0) for _, a in ground]
    out = {}
    for f in facts:
        x, y = frame.xy(f["lat"], f["lon"])
        p = shapely.Point(float(np.ravel(x)[0]), float(np.ravel(y)[0]))
        # (then the outlines alone: cards before 2026-11-10's last build took their point from the outline, and one,
        # an island in the water on line 9, fell into a hole of its own area)
        for shapes in (polys, outer):
            hit = [j for j in shapely.STRtree(shapes).query(p, predicate="intersects") if f.get("c") in (None, ground[j][1]["c"])]
            if hit:
                j = min(hit, key=lambda j: abs(polys[j].area - f.get("m2", 0)))
                out[ground[j][0]] = f["verdict"]
                break
    return out


def with_holes(a):
    """An area's polygon with its holes."""
    return shapely.Polygon(np.asarray(a["r"])[:, :2], [np.asarray(h)[:, :2] for h in a.get("h", []) if len(h) >= 3]).buffer(0)


def judge(areas, ground, older, cover, rails, frame, facts=(), changing=None, rule=None, buildings=None):
    """A verdict per ground-level area (the index into areas): "fits" (within OFFSET of IPR), "small" (too small or
    narrow for the lidar), "covered", "uneven" (no steady offset), "lidar" (the survey is wrong: move it), "survey" (IPR
    is out of date there), "changing" (a construction site), "review" (held).
    ground / older: IPR and DMR 5G at S-JTSK arrays (NaN where none); cover: cover_union; rails: rail_points; frame:
    tools/geo.Frame (areas in its city frame); facts: data/truth.json surveyGround.places ({lat, lon, verdict});
    changing: the union of OSM's construction sites; rule: data/truth.json surveyGround.heldRule, with buildings (the
    union of OSM's building footprints) for what neither the rails nor DMR 5G decide, else such an area is held."""
    out = {}
    rx, ry, rz = rails
    rtree = shapely.STRtree(shapely.points(rx, ry)) if len(rx) else None
    fact_of = facts_to_areas(areas, facts, frame)
    for i, a in enumerate(areas):
        if a["l"] != 0 or a["c"] in NOT_GROUND or len(a["r"]) < 3:
            continue
        r = np.array([[q[0], q[1], math.nan if q[2] is None else q[2]] for q in a["r"]], float)
        pin, inside, poly = inner_points(r[:, :2])
        E, N = frame.to_jtsk(pin[:, 0], pin[:, 1])
        g = np.asarray(ground(E, N), float)
        d = r[:, 2] - g
        ok = np.isfinite(d)
        c = with_holes(a).representative_point() if a.get("h") else poly.representative_point()
        v = {"c": a["c"], "m2": round(poly.area, 1), "x": round(c.x, 1), "y": round(c.y, 1)}
        out[i] = v
        if ok.sum() < 3:
            v["verdict"] = "fits"  # (nothing to compare: outside IPR)
            continue
        off = float(np.median(d[ok]))
        v["offset"], v["spread"] = round(off, 2), round(float(np.percentile(np.abs(d[ok] - off), 80)), 2)
        if abs(off) < OFFSET:
            v["verdict"] = "fits"
            continue
        if i in fact_of:
            v["verdict"], v["by"] = fact_of[i], "fact"
            continue
        if poly.area < MIN_M2 or inside.mean() < MIN_INNER:
            v["verdict"] = "small"
            continue
        if not cover.is_empty and shapely.contains_xy(cover, pin[:, 0], pin[:, 1]).mean() > COVERED:
            v["verdict"] = "covered"
            continue
        if v["spread"] >= STEADY:
            v["verdict"] = "uneven"
            continue
        # the rails through it, under open sky
        if rtree is not None:
            k = rtree.query(poly, predicate="contains")
            if len(k) and not cover.is_empty:
                k = k[~shapely.contains_xy(cover, rx[k], ry[k])]
            if len(k) >= RAIL_MIN:
                sv = np.array([surface_at(r, rx[j], ry[j]) for j in k]) - rz[k]
                gE, gN = frame.to_jtsk(rx[k], ry[k])
                iv = np.asarray(ground(gE, gN), float) - rz[k]
                s_off, i_off = float(np.nanmedian(sv)), float(np.nanmedian(iv))
                v["rails"] = {"n": int(len(k)), "survey": round(s_off, 2), "ipr": round(i_off, 2)}
                if abs(i_off) <= AGREE < abs(s_off):
                    v["verdict"], v["by"] = "lidar", "rails"
                    continue
                if abs(s_off) <= AGREE < abs(i_off):
                    v["verdict"], v["by"] = "survey", "rails"
                    continue
        if changing is not None and not changing.is_empty and shapely.contains_xy(changing, pin[:, 0], pin[:, 1]).mean() > COVERED:
            v["verdict"] = "changing"
            continue
        o = np.asarray(older(E, N), float) - g
        o = o[np.isfinite(o)]
        if len(o) >= 3:
            v["older"] = round(float(np.median(o)), 2)
            if abs(v["older"]) <= AGREE:
                v["verdict"], v["by"] = "lidar", "dmr5g"
                continue
        held = held_verdict(v, rule, buildings)
        v["verdict"], v["by"] = (held, "rule") if held else ("review", None)
        if v["by"] is None:
            del v["by"]
    # the places of the areas a report names, in one call (lat/lon needs the projection grid: not for every area)
    named = [v for v in out.values() if v["verdict"] != "fits"]
    if named:
        try:
            lat, lon = frame.ll(np.array([v["x"] for v in named]), np.array([v["y"] for v in named]))
        except SystemExit as e:  # (tools/geo.py without its projection grid: a test's stand-in root)
            print(f"survey ground: the areas named without their places ({e})")
            return out
        for v, la, lo in zip(named, np.atleast_1d(lat), np.atleast_1d(lon)):
            v["lat"], v["lon"] = round(float(la), 6), round(float(lo), 6)
    return out




def review_set(line, verdicts):
    """The findings file of a line's held areas (reports/review/survey-ground-N.json), or None when none is held."""
    held = sorted([v for v in verdicts.values() if v["verdict"] == "review" and "lat" in v], key=lambda v: -v["m2"])
    if not held:
        return None
    return {
        "title": f"Survey ground off the lidar, line {line}", "issue": 446, "line": str(line),
        "about": "Ground-level survey areas that sit steadily off IPR's 2023 lidar where no surveyed rail runs and DMR 5G "
                 "(2009-2013) disagrees with IPR too, so the ground changed between the two lidars. The survey may be "
                 "newer than both; the orthophoto shows which. Answers become data/truth.json surveyGround "
                 "(python -I tools/survey_ground_answers.py).",
        "options": list(ANSWERS),
        "findings": [{"kind": KIND, "x": v["x"], "y": v["y"], "lat": v["lat"], "lon": v["lon"], "c": v["c"], "m2": v["m2"],
                      "mag": round(abs(v["offset"]), 2),
                      "info": f"{v['c']}, {v['m2']:.0f} m²: the survey {v['offset']:+.2f} m off IPR (2023); DMR 5G "
                              f"{v['older']:+.2f} m off IPR"
                              + (", with the survey" if abs(v["older"] - v["offset"]) <= AGREE else "")} for v in held],
    }


def summary(verdicts, moved):
    """The build's record (provenance checks.surveyGround): areas and m² per verdict, the vertices moved, and the
    places of the areas moved, kept against IPR and held."""
    out = {"areas": {}, "m2": {}, "movedVertices": moved}
    for v in verdicts.values():
        k = v["verdict"]
        out["areas"][k] = out["areas"].get(k, 0) + 1
        out["m2"][k] = round(out["m2"].get(k, 0) + v["m2"])
    for k, name in (("lidar", "moved"), ("survey", "kept"), ("review", "review")):
        out[name] = [{f: v[f] for f in ("c", "m2", "offset", "spread", "lat", "lon", "by", "rails", "older", "enclosed") if f in v}
                     for v in sorted(verdicts.values(), key=lambda v: -v["m2"]) if v["verdict"] == k]
    return out


def apply(areas, verdicts):
    """Moves the areas judged "lidar" by their offset, holes included, and the same heights at the same places in the
    other ground-level areas (not those the rails or a fact keep). Returns how many vertices moved, in all."""
    moves = {}
    for i, v in verdicts.items():
        if v["verdict"] != "lidar":
            continue
        for ring in [areas[i]["r"], *areas[i].get("h", [])]:
            for q in ring:
                if q[2] is not None:
                    moves[(q[0], q[1], q[2])] = round(q[2] - v["offset"], 2)
    keep = {i for i, v in verdicts.items() if v["verdict"] == "survey"}
    n = 0
    for i, a in enumerate(areas):
        if a["l"] != 0 or i in keep:
            continue
        for ring in [a["r"], *a.get("h", [])]:
            for q in ring:
                z = moves.get((q[0], q[1], q[2])) if q[2] is not None else None
                if z is not None:
                    q[2] = z
                    n += 1
    return n
