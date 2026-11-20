# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street profiles: the carriageways' heights along their centrelines fitted as the track's are, grades joined by
vertical curves, with IPR's lidar as the weighted target (#512).

    python -P -E tools/street_profile.py --calibrate [--lines 9,17,22,23,37] [--json PATH]
    python -P -E tools/street_profile.py --pilot 3945,1270 [--line 37] [--radius 160] [--out DIR]   # Palmovka
    python -P -E tools/street_profile.py --sidewalks [--lines ...] [--out DIR]   # the survey's sidewalks against IPR
    python -P -E tools/street_profile.py --wide 300 [--lines 9,17,22,23,37] [--out DIR]   # every line, in squares

--calibrate measures, on the clean streets of the lines' corridors (OSM carriageways of a car class, not a bridge,
tunnel or other layer, whose 1 m samples lie on the survey's level-0 road or tram areas), what a street's profile is:
- noise: IPR along the centreline less its smooth (order-3 Whittaker, 15 m), the scatter the fit may ignore;
- grade: of the 10 m smooth, per OSM class;
- change of grade over a car's length (CAR m), the jolt a driver feels;
- radius: per street stretch (up to PIECE m), the tightest vertical radius a profile within the noise band (BAND) needs:
  the largest rmin at which track_profile.banded_profile still fits. Its low percentiles are the limit that holds the
  generated surfaces (AGENTS.md: calibrate a check before it holds).
"""
import argparse
import json
import math
import os
import sys
import time
import warnings
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from geo import Frame  # noqa: E402
import track_profile as tp  # noqa: E402

# OSM's carriageways cars drive on (service roads, tracks and paths left out: their own rules, #301)
CAR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
       "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
STEP = 1.0  # m between samples along a centreline
CAR_LEN = 4.5  # m: a car's length, over which the change of grade is read
PIECE = 400.0  # m: the longest stretch one fit takes (the solver's system is dense in its points)
MIN_LEN = 60.0  # m: shorter clean stretches are left out of the calibration
BAND = 0.05  # m: the profile keeps within this of the smoothed lidar (the noise's 90th percentile is set against it)
BACK = math.cos(math.radians(120))  # a joint turning more than 120 degrees: the street coming back (Hartigova: 141)
SW_STEP = 2.0  # m between a sidewalk's samples along its kerb (--sidewalks)
SW_REACH = 15.0  # m: the widest sidewalk read across
SW_KERB_SMEAR = 1.5  # m: how far into a sidewalk IPR's 1 m raster still carries the kerb
SW_WALK = 5.0  # m from the kerb: the walkway, a plane at the norm's crossfall; a wider area follows the ground
SW_CELL = 0.5  # m: the sidewalks' fill grid (a 3 m sidewalk is 6 cells across)
SCATTER_CLASSES = ("road", "tram", "sidewalk")  # (the classes the generated surface covers)
SCATTER_IN = 0.3  # m inside an outline where the generated surface is read for the scatter table (on it, a point can
# fall just outside the road the surface covers)
MESH_TOL = (0.02, 0.05)  # m: the triangles' error tolerances, the generated surface's and the lidar's alike (IPR's
# noise p90 on clean streets 0.7-1.7 cm, the calibration)
SW_WAVE = 4.0  # m: the sidewalks' fill halves IPR's waves of this length (the junctions' 10 m flattened a 4 m
# sidewalk rising 2 %: 3 cm under the ground 3 m from the kerb)
WALK_STEP = 0.12  # m within 1 m against the slope so far: a walker's step (src/streetbot.js walk-kerb)
WALK_BUMP = 0.06  # m: a walker's 1 m bend (src/streetbot.js bumpy)
RADII = (25, 50, 75, 100, 150, 200, 300, 400, 500, 700, 1000, 1500, 2000, 3000)  # m: the radii tried, tightest first


def is_car(t):
    if t.get("highway") not in CAR or t.get("area") == "yes":
        return False
    try:
        layer = float(t.get("layer", 0))
    except ValueError:
        layer = 1
    return layer == 0 and t.get("bridge", "no") == "no" and t.get("tunnel", "no") == "no" \
        and t.get("covered", "no") == "no"


def ways(F, pts, margin=150):
    """The car ways around local points, as {id, name, highway, nodes, xy (n, 2)}."""
    import osm_local
    out = []
    for w in osm_local.ways(is_car, bbox=F.bbox(pts, margin)):
        g = w["geometry"]
        x, y = F.xy([p["lat"] for p in g], [p["lon"] for p in g])
        out.append({"id": w["id"], "name": w["tags"].get("name", ""), "highway": w["tags"]["highway"],
                    "oneway": w["tags"].get("oneway", "no"), "nodes": w["nodes"],
                    "xy": np.column_stack([x, y])})
    return out


def _turn(a, b):
    """The cosine of the turn where polyline a's end meets polyline b's start (1: straight on, -1: back on itself)."""
    u, v = a[-1] - a[-2], b[1] - b[0]
    nu, nv = np.hypot(*u), np.hypot(*v)
    return float(u @ v / (nu * nv)) if nu > 1e-9 and nv > 1e-9 else 1.0


def chains(ws):
    """Ways of one name and class joined end to end into longer chains (OSM splits a street at every change of tag),
    never where the street turns back on itself: Hartigova's two one-way carriageways meet at their west end, and joined
    there in a V (a 141 degree turn), and joined into one U-shaped chain its profile was fitted round the turn, 0.58 m
    over IPR and a 1.6 m step to the link beside it."""
    left = list(ws)
    out = []
    while left:
        c = left.pop(0)
        xy, nodes, ids = c["xy"], list(c["nodes"]), [c["id"]]
        grew = True
        while grew:
            grew = False
            for k, w in enumerate(left):
                if w["name"] != c["name"] or w["highway"] != c["highway"] or not c["name"]:
                    continue
                if w["nodes"][0] == nodes[-1]:
                    a, b, end = xy, w["xy"], True
                elif w["nodes"][-1] == nodes[0]:
                    a, b, end = w["xy"], xy, False
                elif w["nodes"][-1] == nodes[-1] and w["oneway"] == "no" and c["oneway"] == "no":
                    a, b, end = xy, w["xy"][::-1], True
                elif w["nodes"][0] == nodes[0] and w["oneway"] == "no" and c["oneway"] == "no":
                    a, b, end = w["xy"][::-1], xy, False
                else:
                    continue
                if len(a) < 2 or len(b) < 2 or _turn(a, b) < BACK:
                    continue
                wn = w["nodes"] if (w["nodes"][0] == nodes[-1] or w["nodes"][-1] == nodes[0]) else w["nodes"][::-1]
                if end:
                    xy, nodes = np.vstack([a, b[1:]]), nodes + wn[1:]
                else:
                    xy, nodes = np.vstack([a[:-1], b]), wn[:-1] + nodes
                ids.append(w["id"])
                left.pop(k)
                grew = True
                break
        out.append({"ids": ids, "name": c["name"], "highway": c["highway"], "nodes": nodes, "xy": xy})
    return out


def resample(xy, step=STEP):
    """Points every `step` m along a polyline: (s, points (n, 2), unit tangents (n, 2))."""
    d = np.hypot(*np.diff(xy, axis=0).T)
    keep = np.concatenate([[True], d > 1e-6])
    xy, d = xy[keep], d[d > 1e-6]
    cs = np.concatenate([[0], np.cumsum(d)])
    if cs[-1] < 2 * step:
        return cs[:0], xy[:0], xy[:0]
    s = np.arange(0, cs[-1], step)
    p = np.column_stack([np.interp(s, cs, xy[:, 0]), np.interp(s, cs, xy[:, 1])])
    i = np.clip(np.searchsorted(cs, s, side="right") - 1, 0, len(d) - 1)
    t = (xy[i + 1] - xy[i]) / d[i][:, None]
    return s, p, t


def runs(mask):
    """(start, end) index pairs of the True runs of a boolean array (end exclusive)."""
    m = np.concatenate([[False], mask, [False]]).astype(int)
    e = np.flatnonzero(np.diff(m))
    return list(zip(e[::2], e[1::2]))


def tightest(s, z):
    """The largest of RADII at which a profile within BAND of z (its smooth) fits: the tightest radius the street needs."""
    best = None
    for r in RADII:
        if tp.banded_profile(s, z, r, BAND)["fits"]:
            best = r
        else:
            break
    return best


def street_areas(dtm):
    """The survey's level-0 road and tram areas as one shapely geometry, and the decks (covers)."""
    import shapely
    from shapely.geometry import Polygon
    def poly(a):
        g = Polygon([p[:2] for p in a["r"]], [[p[:2] for p in h] for h in a.get("h", []) if len(h) >= 3])
        return g if g.is_valid else g.buffer(0)
    road = [poly(a) for a in dtm["areas"] if a["l"] == 0 and a["c"] in ("road", "tram") and len(a["r"]) >= 3]
    cover = [poly(a) for a in dtm["areas"] if (a["l"] > 0 or a["c"] == "deck") and len(a["r"]) >= 3]
    return shapely.union_all(road), shapely.union_all(cover) if cover else None


def clean_stretches(F, ipr, ln):
    """The line's clean car stretches: [{name, highway, s, z (IPR), xy}] at least MIN_LEN long, at most PIECE."""
    import shapely
    line = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
    dtm = json.load(open(os.path.join(ROOT, "data", f"line{ln}.dtm.json"), encoding="utf-8"))
    road, cover = street_areas(dtm)
    shapely.prepare(road)
    if cover is not None:
        shapely.prepare(cover)
    pts = line["path"] + line.get("pathBack", [])
    out = []
    for c in chains(ways(F, pts)):
        s, p, _ = resample(c["xy"])
        if not len(s):
            continue
        z = np.asarray(ipr.sample(p[:, 0] + F.E0, p[:, 1] + F.N0), float)
        ok = shapely.contains_xy(road, p[:, 0], p[:, 1]) & np.isfinite(z)
        if cover is not None:
            ok &= ~shapely.contains_xy(cover, p[:, 0], p[:, 1])
        for a, b in runs(ok):
            for k in range(a, b, int(PIECE / STEP)):
                e = min(b, k + int(PIECE / STEP))
                if (e - k) * STEP >= MIN_LEN:
                    out.append({"name": c["name"], "highway": c["highway"], "s": s[k:e] - s[k], "z": z[k:e],
                                "xy": p[k:e]})
    return out


def pct(v, qs):
    v = np.asarray(v, float)
    return [round(float(np.percentile(v, q)), 4) for q in qs] if len(v) else None


def calibrate(lines, out_path):
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    seen, res = set(), defaultdict(lambda: defaultdict(list))
    n_st = 0
    for ln in lines:
        for st in clean_stretches(F, ipr, ln):
            key = (round(float(st["xy"][0, 0]), 0), round(float(st["xy"][0, 1]), 0))
            if key in seen:  # (a street in two lines' corridors once)
                continue
            seen.add(key)
            n_st += 1
            s, z, h = st["s"], st["z"], st["highway"].replace("_link", "")
            sm = tp.whittaker(s, z, 15.0)
            g = np.gradient(tp.whittaker(s, z, 10.0), s)
            k = int(round(CAR_LEN / 2 / STEP))
            dg = np.abs(g[2 * k:] - g[:-2 * k]) if len(g) > 2 * k else np.array([])
            for cls in (h, "all"):
                res[cls]["noise"].extend(np.abs(z - sm).tolist())
                res[cls]["grade"].extend(np.abs(g).tolist())
                res[cls]["dgrade"].extend(dg.tolist())
                res[cls]["km"].append(float(s[-1]) / 1000)
            r = tightest(s, sm)
            for cls in (h, "all"):
                res[cls]["radius"].append(r if r is not None else 0)
            if r is not None and r <= 100:
                lat, lon = F.ll(float(st["xy"][len(s) // 2, 0]), float(st["xy"][len(s) // 2, 1]))
                res["tight"]["places"].append({"line": ln, "name": st["name"], "highway": st["highway"], "radius": r,
                                               "x": round(float(st["xy"][len(s) // 2, 0]), 1),
                                               "y": round(float(st["xy"][len(s) // 2, 1]), 1),
                                               "lat": round(float(lat), 5), "lon": round(float(lon), 5)})
    rep = {"stretches": n_st, "classes": {}}
    for cls, d in res.items():
        if cls == "tight":
            continue
        rep["classes"][cls] = {
            "km": round(sum(d["km"]), 1), "stretches": len(d["radius"]),
            "noise p50/90/99 m": pct(d["noise"], (50, 90, 99)),
            "grade p50/95/99/100 %": [round(v * 100, 2) for v in pct(d["grade"], (50, 95, 99, 100))],
            "change of grade over 4.5 m p50/95/99/100 %": [round(v * 100, 2) for v in pct(d["dgrade"], (50, 95, 99, 100))],
            "tightest radius needed p1/5/25/50 m": pct(d["radius"], (1, 5, 25, 50))}
    rep["tight"] = res["tight"]["places"]
    for cls, d in sorted(rep["classes"].items(), key=lambda kv: -kv[1]["km"]):
        print(cls, json.dumps(d, ensure_ascii=False))
    print(len(rep["tight"]), "stretches need a radius of 100 m or less")
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    return rep


def calibrate_sidewalks(lines, out_path, margin=SW_KERB_SMEAR):
    """The survey's level-0 sidewalks against IPR, from every kerb edge (an edge shared with a carriageway, `k`) every
    SW_STEP m, where the walkway is 1 m wide or more past the margins: the width (inwards to the area's far side, up to
    SW_REACH), the crossfall (a line through IPR from `margin` off the kerb to 1 m before the far side or SW_WALK from
    the kerb, the nearer; + rises away from the kerb) and the kerb step (IPR 1 m into the sidewalk less 1.5 m into the
    road, as #21). What ČSN 73 6110's 0.5-2 % (9.5.5) is held against."""
    import shapely
    from shapely.geometry import Polygon
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    seen = set()
    rows = []
    for ln in lines:
        dtm = json.load(open(os.path.join(ROOT, "data", f"line{ln}.dtm.json"), encoding="utf-8"))
        _, cover = street_areas(dtm)
        for a in dtm["areas"]:
            if a["c"] != "sidewalk" or a["l"] != 0 or "k" not in a or len(a["r"]) < 3:
                continue
            g = Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
            if not g.is_valid:
                continue
            for ring, ks in zip([a["r"]] + a.get("h", []), a["k"]):
                xy = np.asarray([q[:2] for q in ring], float)
                for i, k in enumerate(ks):
                    if not k:
                        continue
                    p0, p1 = xy[i], xy[(i + 1) % len(xy)]
                    L = float(np.hypot(*(p1 - p0)))
                    if L < 1.0:
                        continue
                    t = (p1 - p0) / L
                    n = np.array([-t[1], t[0]])
                    for u in np.arange(SW_STEP / 2, L, SW_STEP):
                        q = p0 + t * u
                        key = (round(float(q[0])), round(float(q[1])))
                        if key in seen:
                            continue
                        seen.add(key)
                        if not g.contains(shapely.Point(*(q + n * 0.5))):
                            n = -n
                            if not g.contains(shapely.Point(*(q + n * 0.5))):
                                continue
                        d = np.arange(0.25, SW_REACH, 0.25)
                        pts = q[None] + n[None] * d[:, None]
                        inside = shapely.contains_xy(g, pts[:, 0], pts[:, 1])
                        w = float(d[np.argmin(inside)] - 0.25) if not inside.all() else SW_REACH
                        end = min(w - 1.0, SW_WALK)
                        if end - margin < 1.0 or (cover is not None and shapely.contains_xy(cover, q[0], q[1])):
                            continue
                        # (the crossfall: a line through IPR across the walkway, every 0.25 m. IPR's 1 m raster smears
                        # the kerb 1-1.5 m into the sidewalk and a wall's foot or a front garden 1 m into its far side;
                        # a wider area beyond the walkway is a forecourt or a slope: at Hartigova (3687, -70) the first
                        # 5 m rise 1.2 %, the 10 m behind them 0.8 m, and the whole width read 7 %)
                        dd = np.arange(margin, end + 1e-6, 0.25)
                        xs = np.concatenate([q[0] + n[0] * dd, [q[0] - n[0] * 1.5]])
                        ys = np.concatenate([q[1] + n[1] * dd, [q[1] - n[1] * 1.5]])
                        zz = np.asarray(ipr.sample(xs + F.E0, ys + F.N0), float)
                        if not np.all(np.isfinite(zz)):
                            continue
                        fall = float(np.polyfit(dd, zz[:-1], 1)[0])
                        rows.append((ln, float(q[0]), float(q[1]), w, fall, float(zz[0] - zz[-1])))
    if not rows:
        return {}
    A = np.array([r[1:] for r in rows])
    w, fall, step = A[:, 2], A[:, 3], A[:, 4]

    def summary(m):
        f = fall[m]
        return {"samples": int(m.sum()), "crossfall p5/25/50/75/95 %": [round(v * 100, 2) for v in pct(f, (5, 25, 50, 75, 95))],
                "within the norm's 0.5-2 % rising from the kerb": round(float(np.mean((f >= 0.005) & (f <= 0.02))), 3),
                "falling away from the kerb": round(float(np.mean(f < 0)), 3),
                "flatter than 0.5 %": round(float(np.mean((f >= 0) & (f < 0.005))), 3),
                "steeper than 2 % / 4 %": [round(float(np.mean(f > 0.02)), 3), round(float(np.mean(f > 0.04)), 3)],
                "kerb step p25/50/75 m": pct(step[m], (25, 50, 75))}
    rep = {"samples": len(rows), "all": summary(np.ones(len(rows), bool)),
           "by width": {k: summary(m) for k, m in (("3-3.5 m", (w >= 3.0) & (w < 3.5)), ("3.5-5 m", (w >= 3.5) & (w < 5)),
                                                    ("5-8 m", (w >= 5) & (w < 8)), (">= 8 m", w >= 8)) if m.any()},
           "by line": {str(ln): summary(np.array([r[0] == ln for r in rows])) for ln in lines}}
    big = sorted(rows, key=lambda r: -abs(r[4]))
    far = []
    for r in big:
        if len(far) >= 25:
            break
        if all(math.hypot(r[1] - f["x"], r[2] - f["y"]) > 30 for f in far):
            lat, lon = F.ll(r[1], r[2])
            far.append({"line": r[0], "x": round(r[1], 1), "y": round(r[2], 1), "width": r[3],
                        "crossfall %": round(r[4] * 100, 1), "lat": round(float(lat), 5), "lon": round(float(lon), 5)})
    rep["steepest (one per 30 m)"] = far
    print(json.dumps({k: v for k, v in rep.items() if k != "steepest (one per 30 m)"}, ensure_ascii=False, indent=1))
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
    return rep


RANK = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "unclassified": 5, "residential": 6,
        "living_street": 7}  # the governing street at a junction: the higher class, then the longer
REACH = 15.0  # m: the farthest a cross-section reads across from its centreline
LANE = 1.75  # m: a drive line's offset from the centreline (half a lane)
AXLE = 1.6  # m: a car's track width, over which its wheels' left-to-right difference is read
JUMP = 0.15  # m within 1 m: the street bot's jump (src/streetbot.js)
NOISE = 0.03  # m: the lidar's noise along a centreline, Tukey's scale for the fit (calibration: set from --calibrate)


def street_geometry(truth=None):
    """data/truth.json streetGeometry: the vertical radius a street's profile holds by OSM class (measured by
    --calibrate, backed by ČSN 73 6110's tables 13 and 14), the other classes' radius, the raised belt's height and
    the steepest crossfall, and a sidewalk's crossfall range."""
    if truth is None:
        with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as fh:
            truth = json.load(fh)
    f = {x["id"]: x["value"] for x in truth["streetGeometry"]["facts"]}
    r = {k[len("street-radius-"):].replace("-", "_"): float(v) for k, v in f.items()
         if k.startswith("street-radius-") and k != "street-radius-other"}
    return (r, float(f["street-radius-other"]), float(f["raised-belt"]), float(f["street-crossfall-max"]),
            tuple(float(v) for v in f["sidewalk-crossfall"]))


# (m: by class, the other classes'; m: a belt raised more is a kerb; rise per m: the steepest crossfall, a sidewalk's)
R_CLASS, R_STREET, RAISED_BED, FALL_MAX, SW_FALL = street_geometry()
# (the places the user confirmed as a raised tram corridor: the line-wide report measures raised_bed() on them)
with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as _fh:
    RAISED_PLACES = next(x["value"] for x in json.load(_fh)["streetGeometry"]["facts"] if x["id"] == "raised-corridors")
SMOOTH_M = 15.0  # m: IPR along a centreline smoothed over this before the fit (its noise: 1 cm p90 against it)
SEAM = 1.0  # m: the samples within this of a point's nearest one's distance weigh in its height (governing_height)
BLEND = 10.0  # m along a street from where it meets its governing street over which it takes on its own crown
JUNCTION_WAVE = 10.0  # m: the fill's curvature penalty halves IPR's waves of this length (as whittaker's)
PARALLEL = 30.0  # degrees: a centreline this near another's heading, beside it, runs beside it (pilot)
STEP_CUT = 0.3  # m between neighbouring cells of the junctions' fill: a step (a wall, a kerb), not a slope
KERB_WALL = 0.7  # m: a sidewalk's kerb edge whose own height stands this far over a kerb on the road beyond it is a
# wall's top (wall_lines.STEP: a kerb and a garden's edge are under it)
KERB_OWN = 0.5  # m: a kerb edge's own height this near IPR inside the sidewalk is the walkway's (wall_lines.OWN)
BED = 2.0  # m beyond the centre of the outer track: the track bed, held at the tracks' surface level
USUAL = 20  # samples (m) either side over which a street's usual width is its running median (a mouth is shorter)
MOUTH = 1.0  # m: the most a street's width reaches beyond its usual width (a widening for a turn, not a side street)
OFF_LIDAR = 0.10  # m: a fit further than this off the smoothed lidar is held by its radius, not noise (BAND 5 cm)
LOOSEN = 20.0  # m either side of such a place over which the radius is halved
R_FLOOR = 25.0  # m: the tightest radius a street is given (the calibration's tightest, RADII[0])
OWN_LANES = 3.0  # m either side of a street's centreline where it lies inside the street that governs it (a lane)
FALL_FIT = 0.15  # m: a street's crown (its centre's height and its side's crossfall) further than this off IPR for 1 m
# across is not the road's surface there: the street's width ends before it
FALL_CLOSE = 0.05  # m: the width ends at the last point before that where the crown lies this near IPR (BAND)
FALL_ALONG = 3  # samples either side: a street's width is the least its neighbours' crowns reach
FALL_MIN = 3.0  # m: the least half width that leaves a street (OWN_LANES: a lane, with the drive line LANE from the centre
# and a car's wheels AXLE / 2 past it; left 1.5 m, the drive lines ran on the fill and line 23's jumps went from 45 to 75)


def surface_tris(areas, classes):
    """The survey's level-0 areas of `classes` as triangles with heights (the page fills an area linearly from its
    outline): ((k, 3, 3) array, class per triangle)."""
    import shapely
    from shapely.geometry import Polygon
    tris, cls = [], []
    for a in areas:
        if a["l"] != 0 or a["c"] not in classes or len(a["r"]) < 3:
            continue
        def xyz(q):  # (a vertex without a height: NaN, its triangles left out below)
            return (q[0], q[1], np.nan if q[2] is None else q[2])
        g = Polygon([xyz(p) for p in a["r"]], [[xyz(p) for p in h] for h in a.get("h", []) if len(h) >= 3])
        if not g.is_valid:
            continue
        for t in shapely.get_parts(shapely.constrained_delaunay_triangles(g)):
            c = np.asarray(t.exterior.coords)[:3]
            if c.shape[1] == 3 and np.all(np.isfinite(c)):
                tris.append(c)
                cls.append(a["c"])
    return np.array(tris), np.array(cls)


_TREES = {}


def inside_edge(ctx, key):
    """ctx[key] (the road, the sidewalks) 1 m in from its edge, where IPR's 1 m raster no longer rounds the kerbs:
    made and prepared once per line, not per square."""
    import shapely
    k = key + " inside"
    if k not in ctx:
        ctx[k] = ctx[key].buffer(-1.0)
        shapely.prepare(ctx[k])
    return ctx[k]


def near_box(ctx, key, box, margin=15.0):
    """ctx[key] (or inside_edge's, key ending ' inside') cut to a square's box and `margin` m round it, prepared:
    every point tested against it lies within the margin (a walkway reaches SW_WALK from a kerb SW_WALK outside the box),
    and point tests on the whole line's sidewalks took 18 of three squares' 49 s."""
    import shapely
    k = (key, tuple(map(tuple, box)))
    hit = ctx.get("near box", {}).get(k)
    if hit is None:
        g = inside_edge(ctx, key[:-len(" inside")]) if key.endswith(" inside") else ctx[key]
        hit = g.intersection(shapely.box(box[0][0] - margin, box[0][1] - margin, box[1][0] + margin, box[1][1] + margin))
        shapely.prepare(hit)
        ctx["near box"] = {k: hit, **{q: v for q, v in ctx.get("near box", {}).items() if q[1] == k[1]}}
    return hit


def sample_tris(tris, x, y):
    """Heights of triangles at points (NaN outside every one): barycentric, the first triangle that holds a point."""
    import shapely
    z = np.full(len(x), np.nan)
    if not len(tris):
        return z
    # (the tree is built once per triangle set: rebuilt per call, a line's survey triangles took 137 of three 300 m
    # squares' 194 s on line 9)
    hit = _TREES.get(id(tris))
    if hit is None or hit[0] is not tris:
        hit = _TREES[id(tris)] = (tris, shapely.STRtree(shapely.polygons(tris[:, :, :2])))
    pi, ti = hit[1].query(shapely.points(x, y), predicate="intersects")
    a, b, c = tris[ti, 0], tris[ti, 1], tris[ti, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-9
    w1 = ((b[:, 1] - c[:, 1]) * (x[pi] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    w2 = ((c[:, 1] - a[:, 1]) * (x[pi] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    v = w1 * a[:, 2] + w2 * b[:, 2] + (1 - w1 - w2) * c[:, 2]
    z[pi[ok][::-1]] = v[ok][::-1]  # (reversed: the first triangle per point wins)
    return z


def smooth_pins(s, pins, pin_z, smooth=SMOOTH_M):
    """The heights a street is held to, smoothed along each run of them (gaps up to 5 m joined): they are another street's
    surface read along this one's centreline, across that one's crown and edges. Held as read, Hartigova's two
    carriageways converging (8 cm between neighbouring pins) forced the fit 0.71 m over IPR 25 m before them."""
    pins = np.asarray(pins, int)
    out = np.asarray(pin_z, float).copy()
    order = np.argsort(pins)
    ps, zs = pins[order], out[order]
    cut = np.flatnonzero(np.diff(ps) > 5) + 1
    for idx in np.split(np.arange(len(ps)), cut):
        if len(idx) >= 3 and smooth:
            zs[idx] = tp.whittaker(s[ps[idx]], zs[idx], smooth)
    out[order] = zs
    return out


def profile(s, z, rmin=None, pins=(), pin_z=None, smooth=SMOOTH_M):
    """A centreline's heights: IPR's samples (NaN skipped) fitted by the track's vertical-curve solver at rmin, robust
    to the lidar's noise (NOISE); pins: sample indices held at pin_z (where the street meets its governing one)."""
    rmin = rmin or R_STREET
    ok = np.isfinite(z)
    zz = np.where(ok, z, np.interp(s, s[ok], z[ok]) if ok.any() else 0.0)
    if smooth and len(s) > 8:
        zz = tp.whittaker(s, zz, smooth)
    if pin_z is not None:
        zz = zz.copy()
        zz[list(pins)] = smooth_pins(s, pins, pin_z, smooth)
    w = np.where(ok, 1.0, 0.0)
    w[list(pins)] = 1.0
    # (where the fit stays off the smoothed lidar, the street bends tighter than its class: the radius is halved within
    # LOOSEN m of it and the fit run again. At the class radius Goldscheiderova (line 9) could not turn from Plzeňská
    # into its 11 % climb in 5 m; behind by more than the noise, the lidar's points stopped pulling (Tukey) and it fell
    # 1.4 m under IPR, then climbed at 18 % to meet it. 5 % of the calibration's stretches need a tighter radius)
    r = np.full(len(s), float(rmin))
    for _ in range(4):
        f = np.asarray(tp.vertical_profile(list(s), list(zz), list(r), weight=list(w), pins=list(pins), scale=NOISE)["z"])
        off = ok & (np.abs(f - zz) > OFF_LIDAR)
        if not off.any() or r.min() <= R_FLOOR:
            break
        near = np.zeros(len(s), bool)
        for i in np.flatnonzero(off):
            near |= np.abs(s - s[i]) <= LOOSEN
        r = np.where(near, np.maximum(r / 2, R_FLOOR), r)
    return f


def crossfall(F, ipr, p, t, road, s):
    """Per sample, the road's crossfall either side of the centreline (a crown: left, right, as rise per metre
    outwards) and its half widths, from IPR across the road area within REACH; smoothed along the street."""
    import shapely
    n = np.column_stack([-t[:, 1], t[:, 0]])
    off = np.arange(-REACH, REACH + 0.01, 0.5)
    X = p[:, None, 0] + n[:, None, 0] * off[None]
    Y = p[:, None, 1] + n[:, None, 1] * off[None]
    inside = shapely.contains_xy(road, X, Y)
    Z = np.asarray(ipr.sample(X.ravel() + F.E0, Y.ravel() + F.N0), float).reshape(X.shape)
    # (the road's extent: the run of road samples through the centreline, up to a step in IPR over STEP_CUT within 0.5 m:
    # the survey's road areas of two levels touch at a wall, and a crown across it set Palmovka's bus terminal 2 m off)
    cut = np.abs(np.diff(Z, axis=1)) > STEP_CUT
    mid = len(off) // 2
    width = np.zeros((len(p), 2))
    for k in range(len(p)):
        row = inside[k]
        if not row[mid]:
            continue
        lo = mid
        while lo > 0 and row[lo - 1] and not cut[k, lo - 1]:
            lo -= 1
        hi = mid
        while hi < len(off) - 1 and row[hi + 1] and not cut[k, hi]:
            hi += 1
        width[k] = (-off[lo], off[hi])
    z0 = Z[:, mid]
    fall = np.full((len(p), 2), np.nan)
    for side, sel in ((0, off < -0.25), (1, off > 0.25)):
        o = np.abs(off[sel])
        for k in range(len(p)):
            m = (o <= width[k, side] - 0.5) & np.isfinite(Z[k, sel])
            if m.sum() >= 3:
                fall[k, side] = np.polyfit(o[m], Z[k, sel][m] - z0[k], 1)[0] if np.isfinite(z0[k]) else np.nan
    for side in (0, 1):
        ok = np.isfinite(fall[:, side])
        if ok.sum() >= 5:
            v = np.interp(s, s[ok], fall[ok, side])
            fall[:, side] = np.clip(tp.whittaker(s, v, 20.0, robust=0.02), -FALL_MAX, FALL_MAX)
        else:
            fall[:, side] = 0.0
    # (a street's surface is its crown only as far across as the crown holds IPR: the crossfall is smoothed along the
    # street, and where a side street leaves it downhill the smooth is not the ground. Nad Ohradou, line 37
    # (3877, -10): its road area runs 10 m south into Na Vápence's mouth, the ground falling 6.5 % there and the
    # smoothed crossfall 1.3 %; carried across, the crown lay 0.55 m over IPR 9 m out, Na Vápence was pinned to it and
    # 69 m2 of road stood 0.3-0.6 m up beside the garage ramp, #780. Past the crown's reach the road is the junctions'
    # fill, which follows IPR. The width ends where the crown still lies on IPR (FALL_CLOSE), and no further than its
    # neighbours' along the street: ended where the crown had left IPR by FALL_FIT, sample by sample, the fill met the
    # street across a step and between single samples of it: line 23's jumps over 0.15 m in 1 m went from 45 to 71)
    for side, sel in ((0, off < -0.25), (1, off > 0.25)):
        order = np.argsort(np.abs(off[sel]))
        o = np.abs(off[sel])[order]
        with np.errstate(invalid="ignore"):
            d = np.abs(Z[:, sel][:, order] - (z0[:, None] + fall[:, side][:, None] * o[None]))
            miss = d > FALL_FIT
            close = d <= FALL_CLOSE
        run = miss[:, :-1] & miss[:, 1:]
        first = np.argmax(run, axis=1)
        before = close & (np.arange(len(o))[None] <= first[:, None])
        last = np.where(before.any(1), len(o) - 1 - np.argmax(before[:, ::-1], axis=1), -1)
        reach = np.where(run.any(1), np.maximum(np.where(last >= 0, o[np.maximum(last, 0)], 0.0), FALL_MIN), np.inf)
        reach = np.array([reach[max(k - FALL_ALONG, 0):k + FALL_ALONG + 1].min() for k in range(len(reach))])
        width[:, side] = np.where(width[:, side] > 0, np.minimum(width[:, side], reach), width[:, side])
    return fall, width


def _along(arr, step, s):
    """A per-`step` m series of the line data (None where there is none) read at route positions s (NaN outside)."""
    v = np.array([np.nan if a is None else a for a in arr], float)
    return np.interp(s, np.arange(len(v)) * step, v, left=np.nan, right=np.nan)


def track_streets(L, road, box):
    """The line's tracks as the governing streets where they run in the survey's road areas: the centre between the
    route and the opposite track, its height their surface level (top of rail less the style's lift), and the plane
    through the two tracks carried across the road (the user, 2026-11-12: the tracks from Ohrada to Palmovka "are
    tilted by the straight Sokolovská slope, roads lie flush besides tracks"). Where one track runs alone, crossfall()
    reads it from IPR."""
    import shapely
    # (the whole line's centre is worked out once per line: per 300 m square it took 5.5 of three squares' 49 s)
    hit = _TRACKS.get(id(L))
    if hit is None or hit[0] is not L:
        hit = _TRACKS[id(L)] = (L, _track_centre(L))
    s, c, t, zc, g, half = hit[1]
    inbox = (c[:, 0] >= box[0][0]) & (c[:, 0] <= box[1][0]) & (c[:, 1] >= box[0][1]) & (c[:, 1] <= box[1][1])
    on = inbox & np.isfinite(zc)
    on[on] = shapely.contains_xy(road, c[on, 0], c[on, 1])
    out = []
    for a, b in runs(on):
        if b - a >= 10:
            out.append({"name": f"tracks of line {L['line']}", "highway": "tracks", "s": s[a:b] - s[a], "p": c[a:b],
                        "t": t[a:b], "track_z": zc[a:b], "tilt": g[a:b], "half": np.abs(half[a:b])})
    return out


_TRACKS = {}


def _track_centre(L):
    """track_streets()' whole line: every STEP along the route, the centre between the tracks, its tangent, surface
    height and tilt, and the half distance between the tracks."""
    import shapely
    from shapely.geometry import LineString
    path = np.asarray(L["path"], float)
    cs = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(path, axis=0).T))])
    back = LineString(L["pathBack"]) if L.get("pathBack") else None
    s = np.arange(0, cs[-1], STEP)
    p = np.column_stack([np.interp(s, cs, path[:, 0]), np.interp(s, cs, path[:, 1])])
    i = np.clip(np.searchsorted(cs, s, side="right") - 1, 0, len(path) - 2)
    t = path[i + 1] - path[i]
    t /= np.hypot(*t.T)[:, None]
    n = np.column_stack([-t[:, 1], t[:, 0]])
    H, lift = L["heights"], L.get("lift")
    zr = _along(H["path"], H["step"], s)
    zb = _along(H.get("backZ", []), H["step"], s) if H.get("backZ") else np.full(len(s), np.nan)
    off = _along(H.get("backOff", []), H["step"], s) if H.get("backOff") else np.full(len(s), np.nan)
    lf = _along(lift["v"], lift["step"], s) * lift["unit"] if lift else np.zeros(len(s))
    lf = np.where(np.isfinite(lf), lf, 0.0)
    # (which side the opposite track lies: the side whose offset point is on it)
    side = np.ones(len(s))
    if back is not None:
        ok = np.isfinite(off)
        q1 = shapely.points(p[ok] + n[ok] * off[ok, None])
        q2 = shapely.points(p[ok] - n[ok] * off[ok, None])
        side[ok] = np.where(shapely.distance(q1, back) <= shapely.distance(q2, back), 1.0, -1.0)
    two = np.isfinite(zb) & np.isfinite(off) & (off > 1.5) & (off < 6)
    half = np.where(two, side * off / 2, 0.0)
    c = p + n * half[:, None]
    zc = np.where(two, (zr + zb) / 2, zr) - lf
    g = np.where(two, side * (zb - zr) / np.where(two, off, 1), np.nan)  # rise per metre towards +n
    return s, c, t, zc, g, half


def raised_bed(c, F, ipr, road):
    """Per sample of a tracks string and side (0: -n, 1: +n), whether its bed stands over RAISED_BED above the road
    beside it in IPR: IPR on the tracks (between them and at each) against IPR 1-2 m beyond the bed's edge, where that
    is road; held over 5 m runs (a crossing's ramp, where IPR beside the bed is at its level, is a gap in the run).
    (IPR against itself, not against the tracks' heights: those stood 0.13 m under IPR's corridor at Hartigova, which
    the user confirmed raised, and read it unraised (2 % of its samples); 0.25 m over IPR's level corridor at
    Olšanské hřbitovy (#606) read it raised behind a 0.25 m kerb)"""
    import shapely
    n = np.column_stack([-c["t"][:, 1], c["t"][:, 0]])
    out = np.zeros((len(c["p"]), 2), bool)
    on = []
    for o in (-1.0, 0.0, 1.0):
        q = c["p"] + n * (o * c["half"])[:, None]
        on.append(np.asarray(ipr.sample(q[:, 0] + F.E0, q[:, 1] + F.N0), float))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        bed = np.nanmedian(np.array(on), axis=0)
    for side, sg in ((0, -1.0), (1, 1.0)):
        zs = []
        for d in (1.0, 1.5, 2.0):
            q = c["p"] + n * (sg * (c["width"][:, side] + d))[:, None]
            z = np.asarray(ipr.sample(q[:, 0] + F.E0, q[:, 1] + F.N0), float)
            z[~shapely.contains_xy(road, q[:, 0], q[:, 1])] = np.nan
            zs.append(z)
        with warnings.catch_warnings():  # (a sample with no road beside it: all NaN)
            warnings.simplefilter("ignore", RuntimeWarning)
            beside = np.nanmedian(np.array(zs), axis=0)
        up = np.isfinite(beside) & (bed - beside > RAISED_BED)
        for a, b in runs(up):
            if c["s"][b - 1] - c["s"][a] >= 5.0:
                out[a:b, side] = True
    return out


def usual_width(width, half=None):
    """Per sample and side, the running median of a street's half widths over ±USUAL samples (the width a junction's
    mouth or a short widening does not move)."""
    from numpy.lib.stride_tricks import sliding_window_view
    half = half or USUAL
    w = np.pad(width, ((half, half), (0, 0)), mode="edge")
    return np.median(sliding_window_view(w, 2 * half + 1, axis=0), axis=-1)


def pilot(at, radius, ln, out_dir, ctx=None):
    """Palmovka's streets (or any place): profiles and cross-sections built from the tracks and IPR, against the
    survey's surface. The tracks govern first (their own profile and tilt), then the OSM streets by class and length:
    each later street's samples inside an earlier one's road width take that one's surface and are pinned there (its
    profile ends at the governing street's edge and takes the height there)."""
    import shapely
    ctx = ctx or context(ln)
    F, ipr, dtm, L, road, cover = (ctx[k] for k in ("F", "ipr", "dtm", "L", "road", "cover"))
    box = [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)]
    tracks = track_streets(L, road, box)
    cs = []
    for c in chains(ways(F, box, 0)):
        s, p, t = resample(c["xy"])
        if len(s) < 10:
            continue
        inbox = (np.abs(p[:, 0] - at[0]) <= radius) & (np.abs(p[:, 1] - at[1]) <= radius)
        on = shapely.contains_xy(road, p[:, 0], p[:, 1]) & inbox
        if cover is not None:
            on &= ~shapely.contains_xy(cover, p[:, 0], p[:, 1])
        for a, b in runs(on):
            if b - a >= 10:
                cs.append({"name": c["name"], "highway": c["highway"], "s": s[a:b] - s[a], "p": p[a:b], "t": t[a:b]})
    cs.sort(key=lambda c: (RANK.get(c["highway"].replace("_link", ""), 9), -c["s"][-1]))
    cs = tracks + cs
    for c in cs:
        c["ipr"] = np.asarray(ipr.sample(c["p"][:, 0] + F.E0, c["p"][:, 1] + F.N0), float)
        c["fall"], c["width"] = crossfall(F, ipr, c["p"], c["t"], road, c["s"])
        if "track_z" in c:
            c["z"] = c["track_z"]
            ok = np.isfinite(c["tilt"])
            c["fall"][ok, 1] = c["tilt"][ok]
            c["fall"][ok, 0] = -c["tilt"][ok]
            # (only the bed is the tracks': carried across a 15 m junction, their tilt (cant included) set the fill up
            # to 0.4 m off IPR and met the side streets in a seam; the road beside it is junctions()' fill)
            c["width"] = np.minimum(c["width"], (c["half"] + BED)[:, None])
            c["raised"] = raised_bed(c, F, ipr, road)
    # a street's width at a junction's mouth is held to its width along the street: Bělohorská's mouth reached 22 m up
    # Liborova (line 23) with its own crossfall, 1 m under IPR where Liborova starts its 15 % climb, which then lagged
    # 3 m behind it; the mouth is the junctions' fill's
    for c in cs:
        if "track_z" not in c:
            c["width"] = np.minimum(c["width"], usual_width(c["width"]) + MOUTH)
    # a street's width ends half way to a centreline running beside it (the other carriageway of a dual one, the tracks
    # on their own bed, a parallel street): Hartigova's first carriageway reached over the median and held the second
    # one to its crown for 71 m (jumps of 0.4-0.7 m on line 37)
    par = {}
    for k, c in enumerate(cs):
        n = np.column_stack([-c["t"][:, 1], c["t"][:, 0]])
        par[k] = {}
        for j, g in enumerate(cs):
            if j == k:
                continue
            d = c["p"][:, None, :] - g["p"][None, :, :]
            m = np.argmin((d ** 2).sum(-1), axis=1)
            rel = g["p"][m] - c["p"]
            o, along = (rel * n).sum(-1), (rel * c["t"]).sum(-1)
            beside = (np.abs((c["t"] * g["t"][m]).sum(-1)) > math.cos(math.radians(PARALLEL))) & (np.abs(along) < 3)                 & (np.abs(o) > 0.5)
            par[k][j] = beside
            for side, sel in ((1, beside & (o > 0)), (0, beside & (o < 0))):
                c["width"][sel, side] = np.minimum(c["width"][sel, side], np.abs(o[sel]) / 2)
    for k, c in enumerate(cs):
        if "track_z" in c:
            c["pins"] = []
            continue
        pins, pz, by, pin_by = [], [], {}, []
        for j, g in enumerate(cs[:k]):
            zg = governing_height(g, c["p"])
            zg[par[k][j]] = np.nan  # (held only by a street it meets, not one beside it)
            for i in np.flatnonzero(np.isfinite(zg)):
                if i not in pins:
                    pins.append(int(i))
                    pz.append(float(zg[i]))
                    pin_by.append(j)
                    by[j] = by.get(j, 0) + 1
        c["pins"] = pins
        # (inside the street that governs it, a street holds its own lanes only, the rest is the governor's or the
        # fill's: at Hartigova, Buchovcova's 15 m junction mouth carried the bed's height 13 m along the carriageway,
        # 0.2 m over IPR and a 0.22 m jump on Hartigova's drive line)
        if pins:
            c["width"][pins] = np.minimum(c["width"][pins], OWN_LANES)
        if by:
            c["gov"] = cs[max(by, key=by.get)]
            c["pin_s"] = c["s"][pins]
            c["pin_gov"] = [cs[j] for j in pin_by]
        c["z"] = profile(c["s"], c["ipr"], rmin=R_CLASS.get(c["highway"].replace("_link", ""), R_STREET), pins=pins,
                         pin_z=np.array(pz) if pins else None)
    return cs, dtm, F, ipr, road


def governing_height(g, pts, reach=None, own=False, ahead=1.0):
    """The surface of street g (its profile and crown) at points within its road width (or `reach` m of its centreline)
    and `ahead` m along past its nearest sample, NaN elsewhere: the nearest samples' heights carried along by their
    grade and across by their crossfall, weighted across SEAM m. own: g's own surface only, without its blend into the
    street that governs it (below)."""
    if "z" not in g:
        return np.full(len(pts), np.nan)
    if "grade" not in g:
        g["grade"] = np.gradient(g["z"], g["s"]) if len(g["s"]) > 1 else np.zeros(len(g["s"]))
    d2 = ((pts[:, None, :] - g["p"][None, :, :]) ** 2).sum(-1)
    k = np.argmin(d2, axis=1)

    def at(r, kk):  # (points r read from samples kk: offset, along, side, inside, height)
        rel = pts[r] - g["p"][kk]
        o = (rel * np.column_stack([-g["t"][kk, 1], g["t"][kk, 0]])).sum(-1)
        along = (rel * g["t"][kk]).sum(-1)
        side = (o > 0).astype(int)
        w = g["width"][kk, side]
        ok = (np.abs(o) <= (w if reach is None else reach)) & (np.abs(along) <= ahead) & ((w > 0) if reach is None else True)
        return o, along, side, ok, g["z"][kk] + g["grade"][kk] * along + g["fall"][kk, side] * np.abs(o)

    r0 = np.arange(len(pts))
    o, along, side, inside, z = at(r0, k)
    # (every sample within SEAM m of the nearest one's distance weighs in, the nearest most: where the nearest sample
    # changes legs at a sharp corner, each leg's crossfall tilts the other way; U Lesoparku's 117 deg corner (line 9)
    # stepped 0.2 m across that seam)
    d0 = np.sqrt(d2[r0, k])
    pr, pk = np.nonzero(d2 <= (d0[:, None] + SEAM) ** 2)
    if len(pr) > len(pts):
        _, _, _, ok, zc = at(pr, pk)
        wt = np.where(ok, np.clip(1.0 - (np.sqrt(d2[pr, pk]) - d0[pr]) / SEAM, 0.0, 1.0), 0.0)
        ws = np.bincount(pr, wt, len(pts))
        zw = np.bincount(pr, wt * np.where(ok, zc, 0.0), len(pts))
        z = np.where(ws > 0, zw / np.where(ws > 0, ws, 1.0), z)
    # (a street that meets its governing one takes that one's surface where they meet and blends into its own crown
    # over BLEND m: crowned up to the edge, the two met in a seam, 3 jumps and a 7.7 deg roll at Palmovka)
    # (each point blends into the street of its nearest pin: the link by Hartigova's end, held to Hartigova there and to
    # Pod Krejcárkem 30 m on, blended into Pod Krejcárkem's surface carried 30 m and came out 0.9 m under IPR)
    if g.get("gov") is not None and not own and len(g.get("pin_s", ())):
        dd = np.abs(g["s"][k][:, None] - np.asarray(g["pin_s"])[None, :])
        nearest, ds = np.argmin(dd, axis=1), np.min(dd, axis=1)
        u = np.clip(ds / BLEND, 0, 1)
        u = u * u * (3 - 2 * u)
        near = inside & (u < 1)
        govs = g["pin_gov"]
        for gid in {id(govs[i]) for i in nearest[near]}:
            sel = near & np.array([id(govs[i]) == gid for i in nearest])
            gov = next(govs[i] for i in nearest[sel])
            # (carried up to BLEND past the governing street's end: held to 1 m, the blend stopped 5 m into Pohořelec
            # where Strahovská ends, a 0.6 m drop (line 23))
            zg = governing_height(gov, pts[sel], reach=1e9, ahead=BLEND + 1.0)
            ok = np.isfinite(zg)
            idx = np.flatnonzero(sel)[ok]
            z[idx] = u[idx] * z[idx] + (1 - u[idx]) * zg[ok]
    return np.where(inside, z, np.nan)


def bed_kerb(g, pts):
    """Points on a tracks string's bed where the bed is raised on that side (raised_bed): its cells hold their height
    but the road beside them is not drawn up to it (a kerb)."""
    if "raised" not in g:
        return np.zeros(len(pts), bool)
    d = pts[:, None, :] - g["p"][None, :, :]
    k = np.argmin((d ** 2).sum(-1), axis=1)
    n = np.column_stack([-g["t"][k, 1], g["t"][k, 0]])
    rel = pts - g["p"][k]
    o, along = (rel * n).sum(-1), (rel * g["t"][k]).sum(-1)
    side = (o > 0).astype(int)
    w = g["width"][k, side]
    return (np.abs(o) <= w) & (np.abs(along) <= 1.0) & (w > 0) & g["raised"][k, side]


def fill_2d(known, free, data, lam, iters=3000, tol=1e-7, kerb=None):
    """A smooth surface over the `free` cells of a grid: nearest `data` (NaN: no pull) under a curvature penalty `lam`
    (the graph Laplacian squared over the free and known cells), meeting the `known` cells (finite: held), except those
    behind a kerb (`kerb`: a raised bed's cells, not joined to a free neighbour). Conjugate gradients, matrix-free (no
    scipy here)."""
    act = free | np.isfinite(known)
    # (neighbours across a step in IPR over STEP_CUT are not joined: a wall between the bus terminal by Palmovka and the
    # street under it, smeared, set the terminal's edge 2.5 m off)
    ref = np.where(np.isfinite(known), known, data)
    kerb = np.zeros(known.shape, bool) if kerb is None else kerb

    pairs = []
    for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                       ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                       ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                       ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
        apart = (kerb[sl_a] & free[sl_b]) | (free[sl_a] & kerb[sl_b])
        pairs.append((sl_a, sl_b, act[sl_a] & act[sl_b] & ~(np.abs(ref[sl_a] - ref[sl_b]) > STEP_CUT) & ~apart))

    def lap(v):
        out = np.zeros_like(v)
        deg = np.zeros_like(v)
        for sl_a, sl_b, both in pairs:
            out[sl_a] += np.where(both, v[sl_b], 0)
            deg[sl_a] += both
        return np.where(act, out - deg * v, 0)

    w = np.where(free & np.isfinite(data), 1.0, 0.0)
    d0 = np.where(np.isfinite(data), data, 0.0)
    zk = np.where(np.isfinite(known), known, 0.0)

    def A(v):  # v on the free cells only
        return np.where(free, w * v + lam * lap(lap(v)), 0)

    b = np.where(free, w * d0 - lam * lap(lap(zk)), 0)
    # (start from the known cells' mean: the solve converges from there, not from 0 m)
    start = np.nanmean(np.where(np.isfinite(known), known, np.nan)) if np.isfinite(known).any() else np.nanmean(data)
    x = np.where(free, start, 0.0)
    r = b - A(x)
    p = r.copy()
    rr = (r * r).sum()
    nb = max((b * b).sum(), 1e-12)
    for _ in range(iters):
        Ap = A(p)
        a = rr / max((p * Ap).sum(), 1e-30)
        x += a * p
        r -= a * Ap
        rn = (r * r).sum()
        if rn < tol * tol * nb:
            break
        p = r + (rn / rr) * p
        rr = rn
    return np.where(free, x, known)


def junctions(cs, F, ipr, road, box, cell=1.0):
    """The road no street's width holds (a junction's middle, a kerb radius at a corner, the road beside a tram street's
    tracks): fill_2d over it, held to the streets' surfaces around it and to the track bed.
    Returns (x0, y1, cell, grid) for bilinear lookups."""
    import shapely
    xs = np.arange(box[0][0], box[1][0] + cell, cell)
    ys = np.arange(box[1][1], box[0][1] - cell, -cell)
    X, Y = np.meshgrid(xs, ys)
    x, y = X.ravel(), Y.ravel()
    on = shapely.contains_xy(road, x, y)
    zs = np.full(len(x), np.nan)
    for c in cs:
        left = np.flatnonzero(np.isnan(zs) & on)
        for a in range(0, len(left), 4000):
            part = left[a:a + 4000]
            zs[part] = governing_height(c, np.column_stack([x[part], y[part]]))
    # (every road cell of the grid: the fill follows IPR, smoothed, and meets the streets; filled from the streets
    # alone without IPR's pull, the bus terminal by Palmovka came out 2.9 m low)
    free = (on & np.isnan(zs)).reshape(X.shape)
    known = zs.reshape(X.shape)
    data = np.asarray(ipr.sample(x + F.E0, y + F.N0), float).reshape(X.shape)
    lam = (JUNCTION_WAVE / (2 * math.pi)) ** 4 / cell ** 4
    kerb = np.zeros(len(x), bool)
    for c in cs:
        if "raised" in c and c["raised"].any():
            idx = np.flatnonzero(on & ~kerb)
            for a in range(0, len(idx), 4000):
                part = idx[a:a + 4000]
                kerb[part] = bed_kerb(c, np.column_stack([x[part], y[part]]))
    kerb = kerb.reshape(X.shape)
    grid = fill_2d(known, free, data, lam, kerb=kerb)
    # (the bed's own cells left out of the lookup: generated() reads the bed from its string, and a cell beside the kerb
    # takes the road's corners, not a slope up to the bed)
    grid[kerb] = np.nan
    # (the streets' heights too: the lookup at the fill's edge reads them; and IPR, for a cell across a step)
    return xs[0], ys[0], cell, grid, lambda a, b: np.asarray(ipr.sample(np.asarray(a) + F.E0, np.asarray(b) + F.N0), float)


def bilinear(field, x, y):
    x0, y1, cell, g = field[:4]
    fx, fy = (np.asarray(x) - x0) / cell, (y1 - np.asarray(y)) / cell
    i, j = np.floor(fy).astype(int), np.floor(fx).astype(int)
    ok = (i >= 0) & (j >= 0) & (i < g.shape[0] - 1) & (j < g.shape[1] - 1)
    i, j = np.where(ok, i, 0), np.where(ok, j, 0)
    u, v = fy - i, fx - j
    z = (g[i, j] * (1 - u) * (1 - v) + g[i, j + 1] * (1 - u) * v + g[i + 1, j] * u * (1 - v) + g[i + 1, j + 1] * u * v)
    # (at the road's edge a corner cell lies off the road: the mean of the corners that have a height)
    c4 = np.stack([g[i, j], g[i, j + 1], g[i + 1, j], g[i + 1, j + 1]])
    edge = ~np.isfinite(z) & np.isfinite(c4).any(0)
    if edge.any():
        z[edge] = np.nanmean(c4[:, edge], axis=0)
    # (a cell whose corners lie either side of a step (a wall by the bus terminal at Palmovka, 2 m): interpolated, the
    # edge hung between the two; the corner nearest IPR at the point instead)
    spread = np.nanmax(c4, axis=0, initial=-np.inf) - np.nanmin(c4, axis=0, initial=np.inf) if c4.size else c4
    step = ok & (spread > STEP_CUT)
    if len(field) > 4 and step.any():
        zp = field[4](np.asarray(x)[step], np.asarray(y)[step])
        c = c4[:, step]
        k = np.nanargmin(np.where(np.isfinite(c), np.abs(c - np.where(np.isfinite(zp), zp, z[step])), np.inf), axis=0)
        z[step] = c[k, np.arange(c.shape[1])]
    return np.where(ok, z, np.nan)


def generated(cs, x, y, road=None, field=None):
    """The generated surface at points: the first (governing) street whose road width holds a point, else the junctions'
    fill (`field`, junctions()). NaN elsewhere."""
    pts = np.column_stack([x, y])
    z = np.full(len(x), np.nan)
    for c in cs:
        left = np.isnan(z)
        if not left.any():
            break
        idx = np.flatnonzero(left)
        for a in range(0, len(idx), 4000):
            part = idx[a:a + 4000]
            z[part] = governing_height(c, pts[part])
    if field is not None:
        left = np.isnan(z)
        z[left] = bilinear(field, x[left], y[left])
    return z


def surface_source(cs, x, y, road=None, field=None):
    """Which surface generated() takes at points: the index in cs of the first street whose width holds a point, -1
    the junctions' fill, -2 none."""
    pts = np.column_stack([x, y])
    src = np.full(len(x), -2)
    for k, c in enumerate(cs):
        left = np.flatnonzero(src == -2)
        if not len(left):
            break
        src[left[np.isfinite(governing_height(c, pts[left]))]] = k
    if field is not None:
        left = src == -2
        src[left & np.isfinite(bilinear(field, x, y))] = -1
    return src


def drive_measures(zfun, cs, raw=False, road=None):
    """The street bot's measures on a surface (zfun(x, y) -> z) along every street's two drive lines (LANE m either
    side of its centreline, every metre): jumps over JUMP within 1 m against the slope so far, the change of grade over a car, the wheels'
    left-to-right difference (roll) and the 1 m bend (bumpy). With `road`, only where a drive line is on it (an OSM
    centreline 1.75 m off a carriageway's middle crossed Hartigova's island, a 0.32 m "jump" no car drives)."""
    import shapely
    jumps, dgrade, roll, bend, places = 0, [], [], [], []
    for c in cs:
        n = np.column_stack([-c["t"][:, 1], c["t"][:, 0]])
        for side in (-1, 1):
            q = c["p"] + n * side * LANE
            z = zfun(q[:, 0], q[:, 1])
            if road is not None:
                z = np.where(shapely.contains_xy(road, q[:, 0], q[:, 1]), z, np.nan)
            zl = zfun(*(q + n * AXLE / 2).T)
            zr = zfun(*(q - n * AXLE / 2).T)
            ok = np.isfinite(z)
            # (against the slope so far, as src/streetbot.js: a 15 % street rises 0.15 m in every metre and is no step.
            # A metre is a jump when it breaks both the last metre that was none and the metre before it: a step counts
            # once, and a street turning into a steep climb at most once)
            d1 = np.diff(z)
            dz = np.full(len(d1), np.nan)
            g = dp = None
            for i, d in enumerate(d1):
                if not np.isfinite(d):
                    g = dp = None
                    continue
                if g is not None:
                    dz[i] = min(abs(d - g), abs(d - dp))
                if g is None or dz[i] <= JUMP:
                    g = d
                dp = d
            big = np.flatnonzero(np.isfinite(dz) & (dz > JUMP))
            jumps += len(big)
            for i in big:
                places.append({"street": c["name"], "x": round(float(q[i, 0]), 1), "y": round(float(q[i, 1]), 1),
                               "jump": round(float(dz[i]), 2), "t": [round(float(v), 3) for v in c["t"][i]]})
            k = int(round(CAR_LEN / STEP))
            if len(z) > k + 1:
                g = np.diff(z) / STEP
                d = np.abs(g[k:] - g[:-k])
                dgrade.extend(d[np.isfinite(d)].tolist())
            r = np.degrees(np.abs(np.arctan((zl - zr) / AXLE)))
            roll.extend(r[np.isfinite(r)].tolist())
            if ok.sum() > 3:
                b = np.abs(z[2:] - 2 * z[1:-1] + z[:-2])
                bend.extend(b[np.isfinite(b)].tolist())
    nan3 = [float("nan")] * 3
    return {"jumps": jumps, "change of grade over 4.5 m p50/99/100 %": [round(v * 100, 2) for v in pct(dgrade, (50, 99, 100)) or nan3],
            "roll p50/99/100 deg": pct(roll, (50, 99, 100)), "rolls over 7 deg": int(np.sum(np.asarray(roll) > 7)),
            "bend in 1 m p50/99/100 m": pct(bend, (50, 99, 100)), "places": places if raw else places[:40],
            **({"_raw": {"dgrade": dgrade, "roll": roll, "bend": bend}} if raw else {})}


def hillshade(z, cell):
    gy, gx = np.gradient(np.where(np.isfinite(z), z, np.nanmean(z)), cell)
    sl = np.arctan(np.hypot(gx, gy) * 3)  # (exaggerated three times: the bumps are centimetres)
    asp = np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(40)
    h = np.sin(alt) * np.cos(sl) + np.cos(alt) * np.sin(sl) * np.cos(az - asp)
    return np.clip(h, 0, 1)


def pictures(cs, dtm, F, ipr, at, radius, out_dir, svy, road, field):
    """Three hillshades of the streets (the survey's surface, IPR's lidar, the generated one) side by side, and the
    governing street's profile."""
    from PIL import Image, ImageDraw
    cell = 0.5
    xs = np.arange(at[0] - radius, at[0] + radius, cell)
    ys = np.arange(at[1] + radius, at[1] - radius, -cell)
    X, Y = np.meshgrid(xs, ys)
    x, y = X.ravel(), Y.ravel()
    import shapely
    zg = generated(cs, x, y, road, field)
    zs = svy(x, y)
    zi = np.asarray(ipr.sample(x + F.E0, y + F.N0), float)
    on = shapely.contains_xy(road, x, y)
    mask = np.isfinite(zg) | on
    imgs = []
    for name, z in (("survey (today)", zs), ("IPR lidar", zi), ("generated", zg)):
        Z = np.where(mask, z, np.nan).reshape(X.shape)
        h = hillshade(Z, cell)
        rgb = np.dstack([h * 230 + 20] * 3).astype(np.uint8)
        rgb[~mask.reshape(X.shape)] = (245, 245, 240)
        rgb[mask.reshape(X.shape) & ~np.isfinite(Z)] = (255, 120, 120)
        im = Image.fromarray(rgb)
        ImageDraw.Draw(im).text((8, 8), name, fill=(200, 0, 0))
        imgs.append(im)
    W, H = imgs[0].size
    sheet = Image.new("RGB", (W * 3 + 20, H), (255, 255, 255))
    for k, im in enumerate(imgs):
        sheet.paste(im, (k * (W + 10), 0))
    os.makedirs(out_dir, exist_ok=True)
    sheet.save(os.path.join(out_dir, "hillshade.png"))
    contours(cs, F, ipr, svy, road, field, (at[0], at[1]), min(radius, 60.0), out_dir)
    # the governing street's profile: IPR, the survey's surface along its centreline, the generated profile
    for c in cs[:2]:
        s, p = c["s"], c["p"]
        series = [("IPR", (40, 110, 200), c["ipr"]), ("survey", (150, 150, 150), svy(p[:, 0], p[:, 1])),
                  ("generated", (220, 30, 30), c["z"])]
        # (the grade taken off, so centimetres show: each height less the generated profile's chord)
        chord = np.interp(s, [s[0], s[-1]], [c["z"][0], c["z"][-1]])
        Wp, Hp = 1400, 500
        im = Image.new("RGB", (Wp, Hp), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        allv = np.concatenate([v - chord for _, _, v in series])
        allv = allv[np.isfinite(allv)]
        lo, hi = np.percentile(allv, 0.5) - 0.05, np.percentile(allv, 99.5) + 0.05

        def P(si, v, s=s, lo=lo, hi=hi, Wp=Wp, Hp=Hp):
            return 40 + (Wp - 60) * si / s[-1], Hp - 30 - (Hp - 60) * (v - lo) / (hi - lo)
        for gz in np.arange(math.floor(lo * 10) / 10, hi, 0.1):
            dr.line([P(0, gz), P(s[-1], gz)], fill=(235, 235, 235))
            dr.text((2, P(0, gz)[1] - 6), f"{gz:+.1f}", fill=(120, 120, 120))
        for name, col, v in series:
            d = v - chord
            pts = [P(si, di) for si, di in zip(s, d) if np.isfinite(di)]
            dr.line(pts, fill=col, width=2 if name == "generated" else 1)
        for i in c["pins"][::10]:
            dr.ellipse([P(s[i], c["z"][i] - chord[i])[0] - 2, P(s[i], c["z"][i] - chord[i])[1] - 2,
                        P(s[i], c["z"][i] - chord[i])[0] + 2, P(s[i], c["z"][i] - chord[i])[1] + 2], outline=(0, 140, 0))
        dr.text((40, 6), f"{c['name']} ({c['highway']}), {s[-1]:.0f} m, heights less the chord "
                f"{c['z'][0]:.2f} -> {c['z'][-1]:.2f} m; blue IPR, grey survey, red generated, green: held to the "
                "governing street", fill=(0, 0, 0))
        im.save(os.path.join(out_dir, f"profile_{c['name'] or 'street'}_{int(s[-1])}.png".replace(" ", "_")))
    return zg, zs, zi, mask


def contours(cs, F, ipr, svy, road, field, at, radius, out_dir, cell=0.25, step=0.05):
    """The streets around `at` as heights with contours every `step` m, the survey's, IPR's and the generated surface
    side by side: a tilt shows as parallel lines, a bump as a closed or wiggling one."""
    import shapely
    from PIL import Image, ImageDraw
    xs = np.arange(at[0] - radius, at[0] + radius, cell)
    ys = np.arange(at[1] + radius, at[1] - radius, -cell)
    X, Y = np.meshgrid(xs, ys)
    x, y = X.ravel(), Y.ravel()
    on = shapely.contains_xy(road, x, y).reshape(X.shape)
    zs = {"survey (today)": svy(x, y), "IPR lidar": np.asarray(ipr.sample(x + F.E0, y + F.N0), float),
          "generated": generated(cs, x, y, road, field)}
    allz = np.concatenate([v[on.ravel() & np.isfinite(v)] for v in zs.values()])
    lo, hi = np.percentile(allz, 1), np.percentile(allz, 99)
    imgs = []
    for name, z in zs.items():
        Z = z.reshape(X.shape)
        u = np.clip((Z - lo) / max(hi - lo, 1e-6), 0, 1)
        rgb = np.dstack([90 + 150 * u, 140 + 60 * (1 - abs(2 * u - 1)), 240 - 170 * u])
        band = np.floor(Z / step)
        edge = np.zeros(Z.shape, bool)
        edge[:, 1:] |= band[:, 1:] != band[:, :-1]
        edge[1:, :] |= band[1:, :] != band[:-1, :]
        rgb[edge] = (30, 30, 30)
        rgb[~on | ~np.isfinite(Z)] = (245, 245, 240)
        rgb[on & ~np.isfinite(Z)] = (255, 150, 150)
        im = Image.fromarray(rgb.astype(np.uint8))
        ImageDraw.Draw(im).text((6, 6), f"{name}: contours every {step * 100:.0f} cm, {lo:.2f}-{hi:.2f} m", fill=(0, 0, 0))
        imgs.append(im)
    W, H = imgs[0].size
    sheet = Image.new("RGB", (W * 3 + 20, H), (255, 255, 255))
    for k, im in enumerate(imgs):
        sheet.paste(im, (k * (W + 10), 0))
    sheet.save(os.path.join(out_dir, f"contours_{at[0]:.0f}_{at[1]:.0f}.png"))


def pilot_report(at, radius, ln, out_dir):
    ctx = context(ln)
    cs, dtm, F, ipr, road = pilot(at, radius, ln, out_dir, ctx)
    field = junctions(cs, F, ipr, road, [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)])
    tris = ctx["tris"]

    def svy(x, y):
        return sample_tris(tris, np.asarray(x, float), np.asarray(y, float))

    def gen(x, y):
        return generated(cs, np.asarray(x, float), np.asarray(y, float), road, field)

    def lidar(x, y):
        return np.asarray(ipr.sample(np.asarray(x) + F.E0, np.asarray(y) + F.N0), float)

    zg, zs, zi, mask = pictures(cs, dtm, F, ipr, at, radius, out_dir, svy, road, field)
    rep_gap = int(np.sum(mask & ~np.isfinite(zg)))
    rep = {"at": list(at), "radius": radius, "line": ln, "rmin": dict(R_CLASS, other=R_STREET), "noise": NOISE,
           "road left without a surface m2": rep_gap * 0.25,
           "streets": [{"name": c["name"], "highway": c["highway"], "m": round(float(c["s"][-1]), 1),
                        "pinned": len(c["pins"]),
                        "moved from IPR p50/99 m": pct(np.abs(c["z"] - c["ipr"])[np.isfinite(c["ipr"])], (50, 99)),
                        "crossfall left/right median %": [round(float(np.median(c["fall"][:, k])) * 100, 2) for k in (0, 1)],
                        "grade max %": round(float(np.max(np.abs(np.diff(c["z"])))) * 100, 2)} for c in cs]}
    import shapely
    m = mask & np.isfinite(zi)
    xg, yg = np.meshgrid(np.arange(at[0] - radius, at[0] + radius, 0.5), np.arange(at[1] + radius, at[1] - radius, -0.5))
    inner = shapely.contains_xy(road.buffer(-1.0), xg.ravel(), yg.ravel())  # (IPR's 1 m raster rounds the kerbs)
    for name, z in (("survey", zs), ("generated", zg)):
        for where, mm in (("on the streets' surface", m), ("1 m inside their edge", m & inner)):
            d = (z - zi)[mm & np.isfinite(z)]
            rep[f"{name} - IPR {where} (mean, p99 |.|, m)"] = [round(float(np.mean(d)), 3),
                                                              round(float(np.percentile(np.abs(d), 99)), 3)]
    d = np.where(m & np.isfinite(zg), np.abs(zg - zi), 0).reshape(-1)
    xs_, ys_ = np.meshgrid(np.arange(at[0] - radius, at[0] + radius, 0.5), np.arange(at[1] + radius, at[1] - radius, -0.5))
    far = []
    for i in np.argsort(-d)[:4000]:
        if d[i] < 0.2:
            break
        q = (float(xs_.ravel()[i]), float(ys_.ravel()[i]))
        if all(math.dist(q, (f["x"], f["y"])) > 10 for f in far):
            far.append({"x": round(q[0], 1), "y": round(q[1], 1), "off": round(float((zg - zi)[i]), 2)})
    rep["generated over 0.2 m off IPR (largest per 10 m)"] = far[:20]
    rep["drive lines"] = {"survey": drive_measures(svy, cs, road=road), "IPR": drive_measures(lidar, cs, road=road),
                          "generated": drive_measures(gen, cs, road=road)}
    box = [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)]
    swf = sidewalks(ctx, gen, box)
    sw_tris = ctx["sw_tris"]
    rep["sidewalks"] = {
        "survey": sidewalk_measures(ctx, lambda x, y: sample_tris(sw_tris, np.asarray(x, float), np.asarray(y, float)), svy, box),
        "IPR": sidewalk_measures(ctx, lidar, lidar, box),
        "generated": sidewalk_measures(ctx, lambda x, y: bilinear(swf, x, y), gen, box)}
    with open(os.path.join(out_dir, "pilot.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("drive lines", "sidewalks")}, ensure_ascii=False, indent=1))
    for k, v in rep["drive lines"].items():
        print(k, {a: b for a, b in v.items() if a != "places"})
    for k, v in rep["sidewalks"].items():
        print("sidewalks", k, {a: b for a, b in v.items() if a != "places"})
    return rep


def kerb_edges(dtm):
    """The survey's level-0 sidewalks' kerb edges (`k`, shared with a carriageway) 3 m or longer, as (points every
    0.25 m, unit normals into the sidewalk, the sidewalk's own surveyed height at each point, NaN where an end has
    none), and the sidewalks as one geometry."""
    import shapely
    from shapely.geometry import Polygon
    out, polys = [], []
    for a in dtm["areas"]:
        if a["c"] != "sidewalk" or a["l"] != 0 or len(a["r"]) < 3:
            continue
        g = Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
        if not g.is_valid:
            g = g.buffer(0)
        polys.append(g)
        for ring, ks in zip([a["r"]] + a.get("h", []), a.get("k", [])):
            xy = np.asarray([q[:2] for q in ring], float)
            for i, k in enumerate(ks):
                p0, p1 = xy[i], xy[(i + 1) % len(xy)]
                L = float(np.hypot(*(p1 - p0)))
                if not k or L < 3.0:
                    continue
                t = (p1 - p0) / L
                n = np.array([-t[1], t[0]])
                mid = (p0 + p1) / 2
                if not g.contains(shapely.Point(*(mid + n * 0.5))):
                    n = -n
                u = np.arange(0.125, L, 0.25)
                z0, z1 = ring[i][2], ring[(i + 1) % len(ring)][2]
                own = z0 + (z1 - z0) * u / L if z0 is not None and z1 is not None else np.full(len(u), np.nan)
                out.append((p0[None] + t[None] * u[:, None], np.tile(n, (len(u), 1)), own))
    walk = shapely.union_all(polys) if polys else None
    if walk is not None:
        shapely.prepare(walk)
    return out, walk


WALL_CLASSES = ("wall", "stairs")
WALL_ON = 0.05  # m: a sidewalk's outline edge on a wall's or stairs' outline (the survey shares their vertices)


def wall_edges(dtm):
    """The level-0 sidewalks' outline edges along a survey wall or stairs (#653), with the sidewalk's own heights at
    their ends: (n, 2, 3), each running with its sidewalk on its left. A wall's outline holds its top and its foot at
    one place; the sidewalk's own edge says which it meets, and its side which cells it holds (a sidewalk wrapping round
    a wall has its foot and its top within a cell of each other: Krejcárek's ramp, line 37 (3926, 327))."""
    import shapely
    from shapely.geometry import Polygon
    walls = [shapely.LineString([q[:2] for q in r] + [r[0][:2]]) for a in dtm["areas"]
             if a["c"] in WALL_CLASSES and a["l"] == 0 for r in [a["r"]] + a.get("h", []) if len(r) >= 2]
    if not walls:
        return np.zeros((0, 2, 3))
    tree = shapely.STRtree(walls)
    segs = []
    for a in dtm["areas"]:
        if a["c"] != "sidewalk" or a["l"] != 0 or len(a["r"]) < 3:
            continue
        g = None
        for ring in [a["r"]] + a.get("h", []):
            for i in range(len(ring)):
                p, q = ring[i], ring[(i + 1) % len(ring)]
                if p[2] is None or q[2] is None or (p[0], p[1]) == (q[0], q[1]):
                    continue
                pts = shapely.points([p[0], q[0], (p[0] + q[0]) / 2], [p[1], q[1], (p[1] + q[1]) / 2])
                hit, _ = tree.query(pts, predicate="dwithin", distance=WALL_ON)
                if len(set(hit.tolist())) < 3:
                    continue
                if g is None:
                    g = Polygon([r[:2] for r in a["r"]], [[r[:2] for r in h] for h in a.get("h", []) if len(h) >= 3])
                    g = g if g.is_valid else g.buffer(0)
                dx, dy = q[0] - p[0], q[1] - p[1]
                L = math.hypot(dx, dy)
                left = ((p[0] + q[0]) / 2 - dy / L * 0.1, (p[1] + q[1]) / 2 + dx / L * 0.1)
                segs.append([p[:3], q[:3]] if g.contains(shapely.Point(left)) else [q[:3], p[:3]])
    return np.asarray(segs, float).reshape(-1, 2, 3)


WALL_LOCAL = 1.0  # m: a wall's or stairs' outline heights within this of a place are its top and its foot there


class WallLevels:
    """The level-0 survey walls' and stairs' outline heights: at a place, its top and its foot (the highest and lowest
    within WALL_LOCAL), and of a few heights there the level nearest a reference (#653). The sidewalks' own outlines
    along a wall zigzag between its top and its foot: Krejcárek's ramp, line 37 (3927, 322), 228.56 and 230.65 m a metre
    apart along one wall."""

    def __init__(self, dtm):
        from scipy.spatial import cKDTree
        p = [q[:3] for a in dtm["areas"] if a["c"] in WALL_CLASSES and a.get("l", 0) == 0
             for r in [a["r"]] + a.get("h", []) for q in r if q[2] is not None]
        self.p = np.asarray(p, float).reshape(-1, 3)
        self.tree = cKDTree(self.p[:, :2]) if len(self.p) else None

    def around(self, x, y):
        lo, hi = np.full(len(x), np.nan), np.full(len(x), np.nan)
        if self.tree is None:
            return lo, hi
        for i, js in enumerate(self.tree.query_ball_point(np.column_stack([x, y]), WALL_LOCAL)):
            if js:
                z = self.p[js, 2]
                lo[i], hi[i] = z.min(), z.max()
        return lo, hi

    def pick(self, x, y, own, ref):
        """Of `own` and the wall's top and foot at (x, y), the nearest `ref` (own where ref is NaN)."""
        lo, hi = self.around(np.asarray(x, float), np.asarray(y, float))
        c, ref = np.stack([np.asarray(own, float), lo, hi]), np.asarray(ref, float)
        k = np.argmin(np.where(np.isfinite(c), np.abs(c - np.where(np.isfinite(ref), ref, 0.0)[None]), np.inf), axis=0)
        return np.where(np.isfinite(ref), c[k, np.arange(c.shape[1])], own)


def wall_heights(segs, X, Y, on, reach):
    """Per grid cell (`on` ones only): the nearest wall edge on whose left the cell lies (its sidewalk's side, WALL_ON's
    leeway), within `reach`: its own height at its nearest point, the distance, that point and the edge's inward normal
    (NaN, inf and NaN past it)."""
    z, d = np.full(X.shape, np.nan), np.full(X.shape, np.inf)
    q, n = np.full(X.shape + (2,), np.nan), np.full(X.shape + (2,), np.nan)
    if segs is None or not len(segs) or not on.any():
        return z, d, q, n
    x0, x1, y0, y1 = X.min() - reach, X.max() + reach, Y.min() - reach, Y.max() + reach
    lo, hi = segs[:, :, :2].min(1), segs[:, :, :2].max(1)
    s = segs[(hi[:, 0] >= x0) & (lo[:, 0] <= x1) & (hi[:, 1] >= y0) & (lo[:, 1] <= y1)]
    if not len(s):
        return z, d, q, n
    px, py = X[on], Y[on]
    a, b = s[:, 0], s[:, 1]
    ex, ey = b[:, 0] - a[:, 0], b[:, 1] - a[:, 1]
    l2 = np.maximum(ex * ex + ey * ey, 1e-12)
    bz, bd, bq, bn = np.full(len(px), np.nan), np.full(len(px), np.inf), np.full((len(px), 2), np.nan), np.full((len(px), 2), np.nan)
    for k in range(0, len(px), 20000):  # (cells × edges at once, in parts)
        sl = slice(k, k + 20000)
        t = np.clip(((px[sl, None] - a[None, :, 0]) * ex + (py[sl, None] - a[None, :, 1]) * ey) / l2, 0, 1)
        dd = np.hypot(a[None, :, 0] + ex * t - px[sl, None], a[None, :, 1] + ey * t - py[sl, None])
        side = (ex * (py[sl, None] - a[None, :, 1]) - ey * (px[sl, None] - a[None, :, 0])) / np.sqrt(l2)
        dd = np.where(side >= -WALL_ON, dd, np.inf)
        j = dd.argmin(1)
        r = np.arange(len(j))
        bd[sl] = dd[r, j]
        tj = t[r, j]
        bz[sl] = a[j, 2] + (b[j, 2] - a[j, 2]) * tj
        bq[sl] = np.column_stack([a[j, 0] + ex[j] * tj, a[j, 1] + ey[j] * tj])
        bn[sl] = np.column_stack([-ey[j], ex[j]]) / np.sqrt(l2[j])[:, None]
    near = bd <= reach
    zz, dz = np.full(len(px), np.nan), np.full(len(px), np.inf)
    qq, nn = np.full((len(px), 2), np.nan), np.full((len(px), 2), np.nan)
    zz[near], dz[near], qq[near], nn[near] = bz[near], bd[near], bq[near], bn[near]
    z[on], d[on], q[on], n[on] = zz, dz, qq, nn
    return z, d, q, n


def wall_tops(q, n, own, zr, ground=None):
    """Which points of one kerb edge (q, normals n into the sidewalk, the sidewalk's own heights `own`, the road's
    surface zr beyond them) are a wall's top and no kerb, and those as wall edges ((m, 2, 3), the sidewalk on their
    left, wall_edges()): where the sidewalk's own height stands STEP_CUT or more over a kerb on that road, along an
    edge that stands KERB_WALL or more over it somewhere. A garage ramp sunk between walls is a road in the survey and
    its side a kerb edge: on Na Vápence, line 37 (3868, -22), the walkway held at the ramp's surface plus a kerb sank
    2.2 m into the ramp along its edge, its own edge surveyed at 260.4 m (the user's Street View viewpoint,
    2026-11-20: a level sidewalk behind a wall with a railing, #779). The wall grows from nothing at the ramp's head:
    the edge is its top from STEP_CUT on.
    ground: IPR SW_KERB_SMEAR in from each point, on the sidewalk. Only a point whose own height lies within KERB_OWN
    of it counts (the ramp's sidewalk rises to the building behind it: its edge 260.43 m, 260.82 m 1.5 m in): a sidewalk's outline along a parapet on its kerb carries the parapet's top, not the walkway's
    (by the Modřany viaduct, line 17 (-2396, -9241), 199.24 m over a walkway at 198.1 m: held at it, the edge stood
    1.1 m up)."""
    from kerbs import KERB
    with np.errstate(invalid="ignore"):
        up = np.asarray(own, float) - np.asarray(zr, float) - KERB
        if ground is not None:
            up = np.where(np.abs(np.asarray(own, float) - np.asarray(ground, float)) <= KERB_OWN, up, np.nan)
        top = (up >= STEP_CUT) if np.isfinite(up).any() and np.nanmax(up) >= KERB_WALL else np.zeros(len(q), bool)
    t = np.column_stack([n[top, 1], -n[top, 0]]) * 0.125
    z = np.asarray(own, float)[top]
    return top, np.stack([np.column_stack([q[top] - t, z]), np.column_stack([q[top] + t, z])], 1)


def sidewalks(ctx, road_z, box, cell=SW_CELL):
    """The sidewalks around the generated road. The walkway, up to SW_WALK from the kerb, is a plane: at the kerb the
    road's surface 0.5 m beyond it plus KERB (tools/kerbs.py, the measured step), rising across at IPR's crossfall held
    to SW_FALL (data/truth.json sidewalk-crossfall: ČSN 73 6110's 0.5-2 % and the user's "small angle is good for
    draining water but shouldn't be noticeably too much"); where it cannot be read (a walkway under 1 m past the
    kerb's smear), the edge's median. Beyond the walkway a wider area (a forecourt, a slope) is a fill to IPR held to
    the walkway's edge. Returns a field for bilinear()."""
    import shapely
    from kerbs import KERB
    F, ipr, walk = ctx["F"], ctx["ipr"], ctx["walk"]
    if walk is not None:
        walk = near_box(ctx, "walk", box)
    xs = np.arange(box[0][0], box[1][0] + cell, cell)
    ys = np.arange(box[1][1], box[0][1] - cell, -cell)
    X, Y = np.meshgrid(xs, ys)
    on = shapely.contains_xy(walk, X.ravel(), Y.ravel()).reshape(X.shape) if walk is not None else np.zeros(X.shape, bool)
    # (every kerb's plane reaching a cell, weighted by 1 / its distance: between two kerbs, a strip between two
    # carriageways, a straight line from one kerb's top to the other's; at a corner, the two blended. The nearest kerb
    # alone set a 13-15 cm step down the middle of Vinohradská's 3 m strip, its two roads at other heights)
    acc = np.zeros(X.shape)
    wsum = np.zeros(X.shape)
    lo, hi = SW_FALL
    tops = []
    for q, n, *own in ctx["kerb_edges"]:
        ok = (q[:, 0] >= box[0][0] - SW_WALK) & (q[:, 0] <= box[1][0] + SW_WALK) \
            & (q[:, 1] >= box[0][1] - SW_WALK) & (q[:, 1] <= box[1][1] + SW_WALK)
        if not ok.any():
            continue
        q, n = q[ok], n[ok]
        zr = np.asarray(road_z(*(q - n * 0.5).T), float)
        # (an edge standing over the road beyond it is a wall's top, held below as a wall's edge: wall_tops, #779)
        if own:
            g = q + n * SW_KERB_SMEAR
            top, segs = wall_tops(q, n, own[0][ok], zr, np.asarray(ipr.sample(g[:, 0] + F.E0, g[:, 1] + F.N0), float))
            if top.any():
                tops.append(segs)
                q, n, zr = q[~top], n[~top], zr[~top]
                if not len(q):
                    continue
        # (each kerb point's walkway: its width inwards and IPR's crossfall across it, past the kerb's smear)
        d = np.arange(0.25, SW_WALK + 1e-6, 0.25)
        P = q[:, None, :] + n[:, None, :] * d[None, :, None]
        inside = shapely.contains_xy(walk, P[..., 0], P[..., 1])
        w = np.where(inside.all(1), SW_WALK, d[np.argmin(inside, axis=1)] - 0.25)
        Z = np.asarray(ipr.sample(P[..., 0].ravel() + F.E0, P[..., 1].ravel() + F.N0), float).reshape(P.shape[:2])
        # (a least-squares line per kerb point over its walkway, all at once)
        m = (d[None] >= SW_KERB_SMEAR) & (d[None] <= np.minimum(w - 1.0, SW_WALK)[:, None]) & np.isfinite(Z)
        cnt = m.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            dm = (m * d[None]).sum(1) / cnt
            zm = np.where(m, Z, 0).sum(1) / cnt
            dd_ = np.where(m, d[None] - dm[:, None], 0)
            c = (dd_ * np.where(m, Z - zm[:, None], 0)).sum(1) / (dd_ ** 2).sum(1)
        c = np.where(cnt >= 4, c, np.nan)
        c = np.clip(c, lo, hi)
        c = np.where(np.isfinite(c), c, np.nanmedian(c) if np.isfinite(c).any() else (lo + hi) / 2)
        # (a walkway ends where its plane leaves IPR by over STEP_CUT, a wall: on line 17 by (-2493, -8477) one survey
        # sidewalk spans a 4 m wall between two roads, and the two kerbs' planes blended across it made 116 walker's
        # steps of 0.5-1 m in a square where the survey has 9; beyond, the fill follows IPR and does not join the step)
        wall = (np.abs(zr[:, None] + KERB + c[:, None] * d[None] - Z) > STEP_CUT) & (d[None] >= 0.5) & np.isfinite(Z)
        w = np.where(wall.any(1), np.minimum(w, d[np.argmax(wall, axis=1)] - 0.25), w)
        for kd, dk in enumerate(d):
            p = P[:, kd]
            i = np.round((ys[0] - p[:, 1]) / cell).astype(int)
            j = np.round((p[:, 0] - xs[0]) / cell).astype(int)
            good = np.isfinite(zr) & (dk <= w) & (i >= 0) & (j >= 0) & (i < X.shape[0]) & (j < X.shape[1])
            good[good] &= on[i[good], j[good]]
            np.add.at(acc, (i[good], j[good]), (zr[good] + KERB + c[good] * dk) / dk)
            np.add.at(wsum, (i[good], j[good]), 1.0 / dk)
    with np.errstate(invalid="ignore", divide="ignore"):
        known = np.where(wsum > 0, acc / wsum, np.nan)
    data = np.asarray(ipr.sample(X.ravel() + F.E0, Y.ravel() + F.N0), float).reshape(X.shape)
    # (a sidewalk's edge on a survey wall or stairs is a breakline (#653): the cells along it held at the wall's level the
    # sidewalk meets, its top or its foot, whichever is nearer IPR SW_KERB_SMEAR in on the sidewalk's side; and no pull
    # from IPR within that smear: IPR's 1 m raster spreads a wall's face over 1-2 m, and the fill sank the walkway 0.5 m
    # into the top of Krejcárek's ramp wall, line 37 (3929, 331))
    edges = ctx.get("wall_edges")
    if tops:
        edges = np.concatenate(([] if edges is None or not len(edges) else [np.asarray(edges, float).reshape(-1, 2, 3)]) + tops)
    wz, wd, wq, wn = wall_heights(edges, X, Y, on, SW_KERB_SMEAR)
    hold = on & (wd <= cell * 0.75)
    if hold.any() and ctx.get("wall_levels") is not None:
        q, n = wq[hold], wn[hold]
        r = q + n * SW_KERB_SMEAR
        ref = np.asarray(ipr.sample(r[:, 0] + F.E0, r[:, 1] + F.N0), float)
        wz[hold] = ctx["wall_levels"].pick(q[:, 0], q[:, 1], wz[hold], ref)
    known = np.where(hold, wz, known)
    data = np.where(on & (wd <= SW_KERB_SMEAR), np.nan, data)
    free = on & np.isnan(known)
    lam = (SW_WAVE / (2 * math.pi)) ** 4 / cell ** 4
    grid = fill_2d(known, free, data, lam)
    return xs[0], ys[0], cell, np.where(on, grid, np.nan)


def sidewalk_measures(ctx, walk_z, road_z, box, raw=False):
    """A sidewalk surface (walk_z) against IPR and the road beside it (road_z): off IPR 1 m inside the sidewalks
    (IPR's raster rounds the kerb), the kerb step (0.5 m in less 0.5 m out, every metre along the kerbs), and a walker's
    line 1.5 m in from each kerb: steps over WALK_STEP within 1 m against the slope so far, and the 1 m bend."""
    import shapely
    F, ipr, walk = ctx["F"], ctx["ipr"], ctx["walk"]
    if walk is None:
        return {}
    xg, yg = np.meshgrid(np.arange(box[0][0], box[1][0], 0.5), np.arange(box[1][1], box[0][1], -0.5))
    x, y = xg.ravel(), yg.ravel()
    inner = shapely.contains_xy(near_box(ctx, "walk inside", box), x, y)
    walk = near_box(ctx, "walk", box)
    zw = np.asarray(walk_z(x[inner], y[inner]), float)
    zi = np.asarray(ipr.sample(x[inner] + F.E0, y[inner] + F.N0), float)
    d = (zw - zi)[np.isfinite(zw) & np.isfinite(zi)]
    steps, bend, kerb, places, walls = 0, [], [], [], 0
    for q, n, *_ in ctx["kerb_edges"]:
        q, n = q[::4], n[::4]  # (every metre)
        ok = (q[:, 0] >= box[0][0]) & (q[:, 0] <= box[1][0]) & (q[:, 1] >= box[0][1]) & (q[:, 1] <= box[1][1])
        if ok.sum() < 3:
            continue
        q, n = q[ok], n[ok]
        k = np.asarray(walk_z(*(q + n * 0.5).T), float) - np.asarray(road_z(*(q - n * 0.5).T), float)
        kerb.extend(k[np.isfinite(k)].tolist())
        p = q + n * 1.5
        z = np.asarray(walk_z(p[:, 0], p[:, 1]), float)
        z[~shapely.contains_xy(walk, p[:, 0], p[:, 1])] = np.nan
        # (no walker's line on a wall: where IPR rises over STEP_CUT across 1 m, a survey sidewalk along a wall's top
        # (line 17 by (-1734, -5567): 1.5 m wide over a 6 m wall), for every surface alike)
        a_, b_ = p + n * 0.5, p - n * 0.5
        on_wall = np.abs(np.asarray(ipr.sample(a_[:, 0] + F.E0, a_[:, 1] + F.N0), float)
                         - np.asarray(ipr.sample(b_[:, 0] + F.E0, b_[:, 1] + F.N0), float)) > STEP_CUT
        walls += int((on_wall & np.isfinite(z)).sum())
        z[on_wall] = np.nan
        g = dp = None
        for i, dz in enumerate(np.diff(z)):
            if not np.isfinite(dz):
                g = dp = None
                continue
            off = 0.0 if g is None else min(abs(dz - g), abs(dz - dp))
            if off > WALK_STEP:
                steps += 1
                if len(places) < 30:
                    places.append({"x": round(float(p[i + 1, 0]), 1), "y": round(float(p[i + 1, 1]), 1), "step": round(off, 2)})
            else:
                g = dz
            dp = dz
        b = np.abs(z[2:] - 2 * z[1:-1] + z[:-2])
        bend.extend(b[np.isfinite(b)].tolist())
    bend = np.asarray(bend)
    return {"off IPR 1 m inside, mean / p99 |.| m": [round(float(np.mean(d)), 3), round(float(np.percentile(np.abs(d), 99)), 3)] if len(d) else None,
            "kerb step p5/50/95 m": pct(kerb, (5, 50, 95)), "walker's steps": steps,
            "walker's metres on a wall, left out": walls,
            "bumps (bend in 1 m over WALK_BUMP)": int((bend > WALK_BUMP).sum()),
            "bend in 1 m p50/99 m": pct(bend.tolist(), (50, 99)), "places": places,
            **({"_raw": {"dev": d.tolist(), "kerb": kerb, "bend": bend.tolist()}} if raw else {})}


def context(ln):
    """What every square of a line reads: the frame, IPR, the line's survey and data, its road, covers and triangles."""
    import shapely
    from ipr_dtm import IprDtm
    dtm = json.load(open(os.path.join(ROOT, "data", f"line{ln}.dtm.json"), encoding="utf-8"))
    L = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
    road, cover = street_areas(dtm)
    shapely.prepare(road)
    if cover is not None:
        shapely.prepare(cover)
    tris, _ = surface_tris(dtm["areas"], {"road", "tram"})
    sw_tris, _ = surface_tris(dtm["areas"], {"sidewalk"})
    edges, walk = kerb_edges(dtm)
    # (a street over a passage is the ground there, not the passage's floor the raster shows: covers.py, #783)
    import covers
    F, raw = Frame(), IprDtm()
    xy = np.array([q[:2] for a in dtm["areas"] for q in a["r"]], float).reshape(-1, 2)
    ways = covers.tunnel_ways((*xy.min(0), *xy.max(0))) if len(xy) else ()
    ipr = covers.CoveredIpr(raw, covers.Covers(dtm, lambda x, y: np.asarray(raw.sample(np.asarray(x) + F.E0, np.asarray(y) + F.N0), float), ways=ways), F)
    return {"F": F, "ipr": ipr, "dtm": dtm, "L": L, "road": road, "cover": cover, "tris": tris,
            "sw_tris": sw_tris, "kerb_edges": edges, "walk": walk, "tram": class_area(dtm, ("tram",)),
            "rings": outlines(dtm), "wall_edges": wall_edges(dtm), "wall_levels": WallLevels(dtm)}


def class_area(dtm, classes):
    """The survey's level-0 areas of `classes` as one geometry."""
    import shapely
    from shapely.geometry import Polygon
    g = []
    for a in dtm["areas"]:
        if a["l"] == 0 and a["c"] in classes and len(a["r"]) >= 3:
            q = Polygon([p[:2] for p in a["r"]], [[p[:2] for p in h] for h in a.get("h", []) if len(h) >= 3])
            g.append(q if q.is_valid else q.buffer(0))
    return shapely.union_all(g) if g else shapely.Polygon()


def outlines(dtm):
    """The level-0 road, tram and sidewalk outlines with heights on every vertex, for the scatter table (#470's
    statistic, tools/bench/street_scatter.py): (class, (n, 3) ring, its inside on the left, its box)."""
    out = []
    for a in dtm["areas"]:
        if a["l"] != 0 or a["c"] not in SCATTER_CLASSES:
            continue
        for ring, outer in [(a["r"], True)] + [(h, False) for h in a.get("h", [])]:
            if len(ring) < 3 or any(q[2] is None for q in ring):
                continue
            r = np.asarray(ring, float)
            ccw = np.sum(r[:, 0] * np.roll(r[:, 1], -1) - np.roll(r[:, 0], -1) * r[:, 1]) > 0
            out.append((a["c"], r, ccw == outer, (r[:, 0].min(), r[:, 1].min(), r[:, 0].max(), r[:, 1].max())))
    return out


def scatter(ctx, box, heights):
    """#470's scatter on one square: each straight outline sample (straight over +-10 m) against its 21 m running mean,
    survey (the outline's heights), generated (heights(class, x, y) SCATTER_IN m inside the area) and IPR at that point
    (the shapes the lidar sees there too: a wall, a ramp), at the samples of the square where all three have a window.
    {class: {"survey": |residual|..., "ipr": ..., "generated": ...}}."""
    sys.path.insert(0, os.path.join(ROOT, "tools", "bench"))
    import street_scatter as ss
    (x0, y0), (x1, y1) = box
    out = {}
    for cls, r, left, bb in ctx["rings"]:
        if bb[2] < x0 - ss.HALF or bb[0] > x1 + ss.HALF or bb[3] < y0 - ss.HALF or bb[1] > y1 + ss.HALF:
            continue
        p, nin = ss.samples(r)
        if p is None:
            continue
        if not left:
            nin = -nin
        own = (p[:, 0] >= x0) & (p[:, 0] < x1) & (p[:, 1] >= y0) & (p[:, 1] < y1)
        ok = ss.straight(p) & own
        if not ok.any():
            continue
        q = p[:, :2] + nin * SCATTER_IN
        zg = heights(cls, q[:, 0], q[:, 1])
        zi = np.asarray(ctx["ipr"].sample(q[:, 0] + ctx["F"].E0, q[:, 1] + ctx["F"].N0), float)
        rs, ri, rg = ss.resid(p[:, 2]), ss.resid(zi), ss.resid(zg)
        both = ok & np.isfinite(rs) & np.isfinite(ri) & np.isfinite(rg)
        o = out.setdefault(cls, {"survey": [], "ipr": [], "generated": []})
        for k, v in (("survey", rs), ("ipr", ri), ("generated", rg)):
            o[k] += np.abs(v[both]).tolist()
    return out


def triangles(z, mask, tol):
    """Triangles a mesh of the raster z (rows north to south) within `tol` m keeps over `mask` (their centroid on it):
    pydelatin's greedy refinement, as tools/city_terrain.py meshes the lidar."""
    from pydelatin import Delatin
    h, w = z.shape
    t = Delatin(np.ascontiguousarray(z, np.float32), width=w, height=h, max_error=tol)
    v, f = t.vertices, t.triangles
    cx = np.clip(np.round(v[f, 0].mean(1)).astype(int), 0, w - 1)
    cy = np.clip(np.round((h - 1) - v[f, 1].mean(1)).astype(int), 0, h - 1)
    return int(mask[cy, cx].sum())


_WIDE = {}  # (a pool worker's line: its context, loaded once)


def _wide_init(ln):
    _WIDE["ln"], _WIDE["ctx"] = ln, context(ln)


def wide_square(ln, cell, ij, raised_xy, ctx=None):
    """One square of line_wide: the line's streets built in it and measured, as sums and samples to merge in square
    order (survey and generated: the road 1 m inside its edge against IPR, the drive lines, the sidewalks), the
    generated jumps' places, and per confirmed raised corridor (raised_xy) its tracks' samples within 50 m and how many
    read raised. None where the square holds no street."""
    import shapely
    ctx = ctx or (_WIDE["ctx"] if _WIDE.get("ln") == ln else context(ln))
    i, j = ij
    at, radius = ((i + 0.5) * cell, (j + 0.5) * cell), cell / 2
    box = [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)]
    cs, _, F, ipr, road = pilot(at, radius, ln, None, ctx)
    if not cs:
        return None
    out = {"acc": {}, "sw": {}, "places": [], "raised": []}
    for xy in raised_xy:
        n = r = 0
        for c in cs:
            if "raised" in c:
                near = np.hypot(*(c["p"] - xy).T) <= 50.0
                n += int(near.sum())
                r += int(c["raised"][near].any(1).sum())
        out["raised"].append((n, r))
    field = junctions(cs, F, ipr, road, box)
    xg, yg = np.meshgrid(np.arange(at[0] - radius, at[0] + radius, 0.5), np.arange(at[1] + radius, at[1] - radius, -0.5))
    x, y = xg.ravel(), yg.ravel()
    inner = shapely.contains_xy(near_box(ctx, "road inside", box), x, y)
    zi = np.asarray(ipr.sample(x[inner] + F.E0, y[inner] + F.N0), float)
    zs = sample_tris(ctx["tris"], x[inner], y[inner])
    zg = generated(cs, x[inner], y[inner], road, field)
    fns = {"survey": lambda a, b, tris=ctx["tris"]: sample_tris(tris, np.asarray(a, float), np.asarray(b, float)),
           "generated": lambda a, b: generated(cs, np.asarray(a, float), np.asarray(b, float), road, field)}
    for k, z in (("survey", zs), ("generated", zg)):
        d = z - zi
        m = drive_measures(fns[k], [c for c in cs if c["highway"] != "tracks"], raw=True, road=road)
        out["acc"][k] = {"dev": d[np.isfinite(d)].tolist(), "jumps": m["jumps"], "rolls": m["rolls over 7 deg"],
                         **{q: m["_raw"][q] for q in ("dgrade", "roll", "bend")}}
        if k == "generated":
            # (each jump with what holds the road either side of it and IPR's own jump there: a seam between two
            # surfaces, or the ground's own step)
            for pl in m["places"]:
                t = np.array(pl.pop("t"))
                q = np.array([[pl["x"], pl["y"]]]) + np.array([[-1.0], [0.0], [1.0], [2.0]]) * t
                src = surface_source(cs, q[:, 0], q[:, 1], road, field)
                zq = np.asarray(ipr.sample(q[:, 0] + F.E0, q[:, 1] + F.N0), float)
                names = ["fill" if v == -1 else "none" if v == -2 else
                         ("tracks" if cs[v]["highway"] == "tracks" else cs[v]["name"] or "unnamed") for v in src]
                pl["from"], pl["to"] = names[1], names[2]
                pl["ipr jump"] = round(float(min(abs((zq[2] - zq[1]) - (zq[1] - zq[0])), abs((zq[3] - zq[2]) - (zq[2] - zq[1])))), 2)
            out["places"] = m["places"]
    # (the road's deviation split by class: the tram areas, the rest)
    tram = shapely.contains_xy(near_box(ctx, "tram", box), x[inner], y[inner])
    out["tram"] = {k: (z - zi)[tram & np.isfinite(z - zi)].tolist() for k, z in (("survey", zs), ("generated", zg))}
    swf = sidewalks(ctx, fns["generated"], box)
    for k, wz in (("survey", lambda a, b, t=ctx["sw_tris"]: sample_tris(t, np.asarray(a, float), np.asarray(b, float))),
                  ("generated", lambda a, b, f=swf: bilinear(f, a, b))):
        m = sidewalk_measures(ctx, wz, fns[k], box, raw=True)
        if m:
            out["sw"][k] = {**{q: m["_raw"][q] for q in ("dev", "kerb", "bend")}, "steps": m["walker's steps"],
                            "bumps": m["bumps (bend in 1 m over WALK_BUMP)"],
                            "walls": m["walker's metres on a wall, left out"]}
    out["scatter"] = scatter(ctx, box, lambda c, a, b: bilinear(swf, a, b) if c == "sidewalk" else fns["generated"](a, b))
    # triangles over the streets (road, tram, sidewalks) at MESH_TOL: the generated surface, the lidar, the survey's
    sr = surface_raster(ctx, cs, road, field, swf, box, F, ipr)
    st = np.vstack([ctx["tris"], ctx["sw_tris"]]) if len(ctx["sw_tris"]) else ctx["tris"]
    cen = st[:, :, :2].mean(1)
    on = (cen[:, 0] >= box[0][0]) & (cen[:, 0] < box[1][0]) & (cen[:, 1] >= box[0][1]) & (cen[:, 1] < box[1][1])
    # (off the streets each raster takes its nearest street cell: with the terrain there, the edge between the two drew
    # most of the triangles, at Palmovka 23,731 against 17,774 at 2 cm)
    from scipy import ndimage
    near = tuple(ndimage.distance_transform_edt(~sr["street"], return_distances=False, return_indices=True))
    zg_f, zi_f = sr["z"][near], np.where(sr["street"], sr["ipr"], sr["ipr"][near])
    out["triangles"] = {f"{k} at {t} m": triangles(z, sr["street"], t) for t in MESH_TOL
                        for k, z in (("generated", zg_f), ("lidar", zi_f))}
    out["triangles"]["survey"] = int(on.sum())
    return out


def surface_raster(ctx, cs, road, field, swf, box, F, ipr, cell=SW_CELL):
    """The generated street surface on a `cell` m grid over a square (rows north to south, from its north-west
    corner): heights where the road (road and tram areas) or a sidewalk is, NaN elsewhere; IPR on every cell (NaN
    where it has none, filled with the street's or the square's mean for a mesher)."""
    import shapely
    (x0, y0), (x1, y1) = box
    xs, ys = np.arange(x0 + cell / 2, x1, cell), np.arange(y1 - cell / 2, y0, -cell)
    xg, yg = np.meshgrid(xs, ys)
    x, y = xg.ravel(), yg.ravel()
    on_road = shapely.contains_xy(near_box(ctx, "road", box), x, y)
    walk = near_box(ctx, "walk", box) if ctx.get("walk") is not None else None
    on_walk = shapely.contains_xy(walk, x, y) & ~on_road if walk is not None else np.zeros(len(x), bool)
    z = np.full(len(x), np.nan)
    if on_road.any():
        z[on_road] = generated(cs, x[on_road], y[on_road], road, field)
    if on_walk.any():
        z[on_walk] = bilinear(swf, x[on_walk], y[on_walk])
    zi = np.asarray(ipr.sample(x + F.E0, y + F.N0), float)
    fill = np.nanmean(zi) if np.isfinite(zi).any() else 0.0
    zi = np.where(np.isfinite(zi), zi, fill)
    street = np.isfinite(z)
    shape = xg.shape
    return {"x0": float(x0), "y1": float(y1), "cell": cell, "z": z.reshape(shape), "ipr": zi.reshape(shape),
            "street": street.reshape(shape), "road": (on_road & street).reshape(shape)}


def line_wide(lines, cell, out_path, jobs=None):
    """Every line's corridor in squares of `cell` m (each square holding the line's track), built as the pilot builds
    Palmovka and measured: the surface against IPR 1 m inside the road's edge, and the drive lines, survey against
    generated, summed per line. The squares run in `jobs` processes (sysinfo.workers by free memory, a line's context
    about 0.7 GB in each), merged in square order: the result is the serial one's."""
    import sysinfo
    # (one thread each for the solvers' BLAS: the workers are the parallelism; read when a worker imports numpy)
    for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    jobs = jobs or sysinfo.workers(1.0, most=os.cpu_count() or 4)
    out = {}
    for ln in lines:
        F = Frame()
        L = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
        pts = np.asarray(L["path"] + L.get("pathBack", []), float)
        sq = sorted({(int(math.floor(x / cell)), int(math.floor(y / cell))) for x, y in pts})
        acc = {k: {"dev": [], "jumps": 0, "rolls": 0, "dgrade": [], "roll": [], "bend": []} for k in ("survey", "generated")}
        sw = {k: {"dev": [], "kerb": [], "bend": [], "steps": 0, "bumps": 0, "walls": 0} for k in ("survey", "generated")}
        places, tram = [], {"survey": [], "generated": []}
        scat, tri = {}, {}
        # (the places the user confirmed raised (data/truth.json raised-corridors): how much of each raised_bed() reads)
        raised_at = []
        for r in RAISED_PLACES:
            if r["line"] == ln:
                x, y = F.xy([r["lat"]], [r["lon"]])
                raised_at.append({"place": r["place"], "xy": np.array([float(np.ravel(x)[0]), float(np.ravel(y)[0])]),
                                  "n": 0, "raised": 0})
        xy = [r["xy"] for r in raised_at]
        if jobs > 1:
            ex = sysinfo.pool(min(jobs, len(sq)), _wide_init, ln)
            results = ex.map(wide_square, *zip(*[(ln, cell, ij, xy) for ij in sq]))
        else:
            ex, ctx = None, context(ln)
            results = (wide_square(ln, cell, ij, xy, ctx) for ij in sq)
        try:
            for n, part in enumerate(results):
                print(f"line {ln}: square {n + 1}/{len(sq)}", flush=True)
                if part is None:
                    continue
                for r, (k, q) in zip(raised_at, part["raised"]):
                    r["n"] += k
                    r["raised"] += q
                for k, m in part["acc"].items():
                    for q in ("dev", "dgrade", "roll", "bend"):
                        acc[k][q].extend(m[q])
                    acc[k]["jumps"] += m["jumps"]
                    acc[k]["rolls"] += m["rolls"]
                places.extend(part["places"])
                for k in tram:
                    tram[k].extend(part["tram"][k])
                for c, v in part["scatter"].items():
                    for k, q in v.items():
                        scat.setdefault(c, {"survey": [], "ipr": [], "generated": []})[k].extend(q)
                for k, v in part["triangles"].items():
                    tri[k] = tri.get(k, 0) + v
                for k, m in part["sw"].items():
                    for q in ("dev", "kerb", "bend"):
                        sw[k][q].extend(m[q])
                    for q in ("steps", "bumps", "walls"):
                        sw[k][q] += m[q]
        finally:
            if ex is not None:
                ex.shutdown()
        res = {}
        for k, a in acc.items():
            d = np.asarray(a["dev"])
            res[k] = {"off IPR 1 m inside the edge, mean / p99 |.| m": [round(float(d.mean()), 3),
                                                                        round(float(np.percentile(np.abs(d), 99)), 3)],
                      "jumps": a["jumps"], "rolls over 7 deg": a["rolls"],
                      "change of grade over 4.5 m p99 / max %": [round(v * 100, 2) for v in pct(a["dgrade"], (99, 100))],
                      "roll p99 / max deg": pct(a["roll"], (99, 100)), "bend in 1 m p99 m": pct(a["bend"], (99,))[0]}
        for k, a in sw.items():
            d = np.asarray(a["dev"])
            res[k]["sidewalks"] = {
                "off IPR 1 m inside, mean / p99 |.| m": [round(float(d.mean()), 3), round(float(np.percentile(np.abs(d), 99)), 3)]
                if len(d) else None,
                "kerb step p5/50/95 m": pct(a["kerb"], (5, 50, 95)), "walker's steps": a["steps"], "bumps": a["bumps"],
                "walker's metres on a wall, left out": a["walls"],
                "bend in 1 m p99 m": pct(a["bend"], (99,))[0] if a["bend"] else None}
        for k in ("survey", "generated"):
            d = np.asarray(tram[k])
            res[k]["tram areas, off IPR 1 m inside the edge, mean / p99 |.| m"] = (
                [round(float(d.mean()), 3), round(float(np.percentile(np.abs(d), 99)), 3)] if len(d) else None)
        # (#470's table: straight outline samples over 8 / 15 cm off their 21 m running mean, %)
        res["scatter, % over 8 / 15 cm: survey, IPR, generated"] = {
            c: {"km": round(len(v["survey"]) / 1000, 1),
                **{k: [round(float((np.asarray(v[k]) > t).mean() * 100), 2) for t in (0.08, 0.15)] for k in v}}
            for c, v in sorted(scat.items()) if v["survey"]}
        res["triangles over the streets (road, tram, sidewalks)"] = tri
        res["squares"] = len(sq)
        res["confirmed raised corridors, share of the tracks within 50 m read raised"] = {
            r["place"]: round(r["raised"] / r["n"], 2) if r["n"] else None for r in raised_at}
        res["generated jumps, places"] = places
        out[ln] = res
        print(ln, json.dumps({k: v for k, v in res.items() if k != "generated jumps, places"}, ensure_ascii=False))
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
    return out


STREETS_SCALE = 0.002  # m per unit of lineN.streets.bin's heights (int16 over each square's lowest: 65 m of range,
# doubled for a square that spans more: line 9's at Petřín, 191-256 m)


def build_square(ln, cell, ij, ctx=None):
    """One square of build(): the generated surface's raster (surface_raster) with its masks packed: (ij, base, road
    mask bits, sidewalk mask bits, int16 heights of the road cells then the sidewalk cells, row by row, the counts and
    the scale), or None where the square holds no street."""
    ctx = ctx or (_WIDE["ctx"] if _WIDE.get("ln") == ln else context(ln))
    i, j = ij
    at, radius = ((i + 0.5) * cell, (j + 0.5) * cell), cell / 2
    box = [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)]
    cs, _, F, ipr, road = pilot(at, radius, ln, None, ctx)
    if not cs:
        return None
    field = junctions(cs, F, ipr, road, box)
    swf = sidewalks(ctx, lambda a, b: generated(cs, np.asarray(a, float), np.asarray(b, float), road, field), box)
    sr = surface_raster(ctx, cs, road, field, swf, box, F, ipr)
    on_road, on_walk = sr["road"], sr["street"] & ~sr["road"]
    if not sr["street"].any():
        return None
    z = sr["z"]
    base, scale = float(np.floor(np.nanmin(z))), STREETS_SCALE
    while (np.nanmax(z) - base) / scale > 32767:
        scale *= 2
    q = np.round((np.concatenate([z[on_road], z[on_walk]]) - base) / scale)
    return (ij, base, np.packbits(on_road.ravel()), np.packbits(on_walk.ravel()), q.astype(np.int16),
            int(on_road.sum()), int(on_walk.sum()), scale)


def squares(L, cell=300.0):
    """The squares of `cell` m reaching the line's ground (ground_partition.line_area), sorted."""
    import shapely
    from ground_partition import line_area
    A = line_area(L)
    shapely.prepare(A)
    x0, y0, x1, y1 = A.bounds
    return sorted((i, j) for i in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1)
                  for j in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1)
                  if A.intersects(shapely.box(i * cell, j * cell, (i + 1) * cell, (j + 1) * cell)))


def build(ln, cell=300.0, jobs=None, root=ROOT):
    """data/lineN.streets.bin and .json: the generated street surface (#512) of every square of `cell` m reaching the
    line's ground (ground_partition.line_area: 1.2 km around its route and tracks, the ground file's area; the squares
    holding the route only left the file's sidewalks beyond 50-200 m on the survey's outline heights, tilted to its
    facade lines, #632), on a SW_CELL grid. The .bin: per square in the .json's order a zlib block holding its road mask
    (road and tram areas) and sidewalk mask as bits (rows north to south from the square's north-west corner,
    np.packbits), then the int16 heights of the road cells and the sidewalk cells in row order, each the difference to
    the one before, in units of the square's `scale` m over its `base`. Read by
    #507 and #508 (the ground partition and the weld), not by the game."""
    import sources
    import sysinfo
    from atomic import replacing
    for v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ.setdefault(v, "1")
    t0 = time.time()
    L = json.load(open(os.path.join(root, "data", f"line{ln}.json"), encoding="utf-8"))
    sq = squares(L, cell)
    jobs = jobs or sysinfo.workers(1.0, most=os.cpu_count() or 4)
    if jobs > 1:
        ex = sysinfo.pool(min(jobs, len(sq)), _wide_init, ln)
        results = list(ex.map(build_square, [ln] * len(sq), [cell] * len(sq), sq))
        ex.shutdown()
    else:
        _wide_init(ln)
        results = [build_square(ln, cell, ij) for ij in sq]
    import zlib
    parts, meta_sq, off, n_road, n_walk = [], [], 0, 0, 0
    for r in results:
        if r is None:
            continue
        ij, base, mr, mw, q, nr, nw, scale = r
        # (each height as the difference to the one before it: a smooth surface's are small, and deflated a fifth of
        # the heights' size on line 37, 1.9 against 9.3 MB; the data store keeps files as they are)
        d = np.diff(q.astype(np.int32), prepend=0).astype(np.int16)
        blob = zlib.compress(mr.tobytes() + mw.tobytes() + d.tobytes(), 9)
        parts.append(blob)
        meta_sq.append({"i": ij[0], "j": ij[1], "base": base, "scale": scale, "offset": off, "bytes": len(blob),
                        "road": nr, "sidewalk": nw})
        off += len(blob)
        n_road, n_walk = n_road + nr, n_walk + nw
    with replacing(os.path.join(root, "data", f"line{ln}.streets.bin"), "wb") as fh:
        fh.write(b"".join(parts))
    side = int(round(cell / SW_CELL))
    meta = {"cell": cell, "grid": SW_CELL, "side": side, "squares": meta_sq,
            "layout": "per square a zlib block of `bytes` at `offset`: road mask bits, sidewalk mask bits (side x side, "
                      "rows north to south from the square's north-west corner (i * cell, (j + 1) * cell), cell centres "
                      "half a grid in), then the int16 heights of the road cells and the sidewalk cells in row order, "
                      "each as the difference to the one before (the first to 0), the square's scale m over its base"}
    meta["provenance"] = sources.stamp("street_profile.py", {
        "road": sources.entry("streets", [n_road, 0, 0], "cells (0.5 m, the survey's road and tram areas)"),
        "sidewalk": sources.entry("streets", [n_walk, 0, 0], "cells (0.5 m, the survey's sidewalks)"),
        "heights": sources.entry("terrain", [n_road + n_walk, 0, 0], "cells (profiles fitted to IPR)")})
    meta["attribution"] = sources.attribution(meta["provenance"])
    with replacing(os.path.join(root, "data", f"line{ln}.streets.json"), "w") as fh:
        json.dump(meta, fh, separators=(",", ":"))
    print(f"wrote data/line{ln}.streets.bin ({off / 1e6:.1f} MB): {len(meta_sq)} squares, road {n_road}, sidewalk {n_walk} "
          f"cells, {time.time() - t0:.0f} s")
    return meta


def read_streets(ln, root=ROOT):
    """data/lineN.streets.*: {(i, j): (x0, y1, road heights, sidewalk heights)} as side x side arrays (NaN off the class)
    over the square from its north-west corner (x0, y1), and the .json."""
    meta = json.load(open(os.path.join(root, "data", f"line{ln}.streets.json"), encoding="utf-8"))
    import zlib
    buf = open(os.path.join(root, "data", f"line{ln}.streets.bin"), "rb").read()
    n, nb, out = meta["side"], (meta["side"] ** 2 + 7) // 8, {}
    for sq in meta["squares"]:
        b = zlib.decompress(buf[sq["offset"]:sq["offset"] + sq["bytes"]])
        mr = np.unpackbits(np.frombuffer(b, np.uint8, nb, 0))[:n * n].astype(bool)
        mw = np.unpackbits(np.frombuffer(b, np.uint8, nb, nb))[:n * n].astype(bool)
        d = np.frombuffer(b, np.int16, sq["road"] + sq["sidewalk"], 2 * nb).astype(np.int64)
        q = np.cumsum(d).astype(float) * sq["scale"] + sq["base"]
        zr, zw = np.full(n * n, np.nan), np.full(n * n, np.nan)
        zr[mr], zw[mw] = q[:sq["road"]], q[sq["road"]:]
        out[(sq["i"], sq["j"])] = (sq["i"] * meta["cell"], (sq["j"] + 1) * meta["cell"], zr.reshape(n, n), zw.reshape(n, n))
    return out, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--json", default=os.path.join(ROOT, "reports", "street_profile", "calibration.json"))
    ap.add_argument("--pilot", help="X,Y: build the streets around this place (local frame) and measure them")
    ap.add_argument("--line", type=int, default=37, help="--pilot: the line whose survey data to read")
    ap.add_argument("--radius", type=float, default=150.0, help="--pilot: half the square's side, m")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "street_profile"))
    ap.add_argument("--sidewalks", action="store_true", help="the survey's sidewalks against IPR: crossfall, kerb")
    ap.add_argument("--wide", type=float, metavar="CELL", help="every line of --lines in squares of CELL m (300)")
    ap.add_argument("--jobs", type=int, help="--wide, --build: squares at once (default: by cores and free memory)")
    ap.add_argument("--build", type=int, metavar="LINE", help="write data/lineN.streets.bin and .json (the build step)")
    a = ap.parse_args(argv)
    if a.build:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):
            build(a.build, jobs=a.jobs)
    elif a.sidewalks:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):
            calibrate_sidewalks([int(v) for v in a.lines.split(",")], os.path.join(a.out, "sidewalks.json"))
    elif a.wide:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):
            line_wide([int(v) for v in a.lines.split(",")], a.wide, os.path.join(a.out, "lines.json"), a.jobs)
    elif a.pilot:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):
            pilot_report(tuple(float(v) for v in a.pilot.split(",")), a.radius, a.line, a.out)
    elif a.calibrate:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):  # (minutes of solver on every core's share: waits its turn, #280)
            calibrate([int(v) for v in a.lines.split(",")], a.json)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
