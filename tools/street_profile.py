# SPDX-License-Identifier: AGPL-3.0-or-later
"""Street profiles: the carriageways' heights along their centrelines fitted as the track's are, grades joined by
vertical curves, with IPR's lidar as the weighted target (#512).

    python -P -E tools/street_profile.py --calibrate [--lines 9,17,22,23,37] [--json PATH]
    python -P -E tools/street_profile.py --pilot 3945,1270 [--line 37] [--radius 160] [--out DIR]   # Palmovka
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


def chains(ws):
    """Ways of one name and class joined end to end into longer chains (OSM splits a street at every change of tag)."""
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
                    xy, nodes = np.vstack([xy, w["xy"][1:]]), nodes + w["nodes"][1:]
                elif w["nodes"][-1] == nodes[0]:
                    xy, nodes = np.vstack([w["xy"][:-1], xy]), w["nodes"][:-1] + nodes
                elif w["nodes"][-1] == nodes[-1] and w["oneway"] == "no" and c["oneway"] == "no":
                    xy, nodes = np.vstack([xy, w["xy"][::-1][1:]]), nodes + w["nodes"][::-1][1:]
                elif w["nodes"][0] == nodes[0] and w["oneway"] == "no" and c["oneway"] == "no":
                    xy, nodes = np.vstack([w["xy"][::-1][:-1], xy]), w["nodes"][::-1][:-1] + nodes
                else:
                    continue
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


RANK = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "unclassified": 5, "residential": 6,
        "living_street": 7}  # the governing street at a junction: the higher class, then the longer
REACH = 15.0  # m: the farthest a cross-section reads across from its centreline
LANE = 1.75  # m: a drive line's offset from the centreline (half a lane)
AXLE = 1.6  # m: a car's track width, over which its wheels' left-to-right difference is read
JUMP = 0.15  # m within 1 m: the street bot's jump (src/streetbot.js)
NOISE = 0.03  # m: the lidar's noise along a centreline, Tukey's scale for the fit (calibration: set from --calibrate)
# m: the vertical radius a street's profile holds, by OSM class: the 5th percentile of the tightest radius the clean
# streets of the five lines need (--calibrate, 2026-11-13, 384 km in 1864 stretches: primary 490, trunk 350, secondary
# and tertiary 300, residential 150, living street 100 m)
R_CLASS = {"motorway": 500.0, "trunk": 350.0, "primary": 500.0, "secondary": 300.0, "tertiary": 300.0,
           "living_street": 100.0}
R_STREET = 150.0  # m: the other classes' (residential, unclassified)
SMOOTH_M = 15.0  # m: IPR along a centreline smoothed over this before the fit (its noise: 1 cm p90 against it)
BLEND = 10.0  # m along a street from where it meets its governing street over which it takes on its own crown
JUNCTION_WAVE = 10.0  # m: the fill's curvature penalty halves IPR's waves of this length (as whittaker's)
PARALLEL = 30.0  # degrees: a centreline this near another's heading, beside it, runs beside it (pilot)
STEP_CUT = 0.3  # m between neighbouring cells of the junctions' fill: a step (a wall, a kerb), not a slope
BED = 2.0  # m beyond the centre of the outer track: the track bed, held at the tracks' surface level


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


def sample_tris(tris, x, y):
    """Heights of triangles at points (NaN outside every one): barycentric, the first triangle that holds a point."""
    import shapely
    z = np.full(len(x), np.nan)
    if not len(tris):
        return z
    tree = shapely.STRtree(shapely.polygons(tris[:, :, :2]))
    pi, ti = tree.query(shapely.points(x, y), predicate="intersects")
    a, b, c = tris[ti, 0], tris[ti, 1], tris[ti, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-9
    w1 = ((b[:, 1] - c[:, 1]) * (x[pi] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    w2 = ((c[:, 1] - a[:, 1]) * (x[pi] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    v = w1 * a[:, 2] + w2 * b[:, 2] + (1 - w1 - w2) * c[:, 2]
    z[pi[ok][::-1]] = v[ok][::-1]  # (reversed: the first triangle per point wins)
    return z


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
        zz[list(pins)] = pin_z
    w = np.where(ok, 1.0, 0.0)
    w[list(pins)] = 1.0
    f = tp.vertical_profile(list(s), list(zz), rmin, weight=list(w), pins=list(pins), scale=NOISE)
    return np.asarray(f["z"])


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
            fall[:, side] = tp.whittaker(s, v, 20.0, robust=0.02)
        else:
            fall[:, side] = 0.0
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
    inbox = (c[:, 0] >= box[0][0]) & (c[:, 0] <= box[1][0]) & (c[:, 1] >= box[0][1]) & (c[:, 1] <= box[1][1])
    on = inbox & shapely.contains_xy(road, c[:, 0], c[:, 1]) & np.isfinite(zc)
    out = []
    for a, b in runs(on):
        if b - a >= 10:
            out.append({"name": f"tracks of line {L['line']}", "highway": "tracks", "s": s[a:b] - s[a], "p": c[a:b],
                        "t": t[a:b], "track_z": zc[a:b], "tilt": g[a:b], "half": np.abs(half[a:b])})
    return out


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
        pins, pz, by = [], [], {}
        for j, g in enumerate(cs[:k]):
            zg = governing_height(g, c["p"])
            zg[par[k][j]] = np.nan  # (held only by a street it meets, not one beside it)
            for i in np.flatnonzero(np.isfinite(zg)):
                if i not in pins:
                    pins.append(int(i))
                    pz.append(float(zg[i]))
                    by[j] = by.get(j, 0) + 1
        c["pins"] = pins
        if by:
            c["gov"] = cs[max(by, key=by.get)]
            c["pin_s"] = c["s"][pins]
        c["z"] = profile(c["s"], c["ipr"], rmin=R_CLASS.get(c["highway"].replace("_link", ""), R_STREET), pins=pins,
                         pin_z=np.array(pz) if pins else None)
    return cs, dtm, F, ipr, road


def governing_height(g, pts, reach=None, own=False):
    """The surface of street g (its profile and crown) at points within its road width (or `reach` m of its centreline),
    NaN elsewhere: the nearest sample's height carried along by its grade and across by its crossfall. own: g's own
    surface only, without its blend into the street that governs it (below)."""
    if "z" not in g:
        return np.full(len(pts), np.nan)
    d = pts[:, None, :] - g["p"][None, :, :]
    k = np.argmin((d ** 2).sum(-1), axis=1)
    n = np.column_stack([-g["t"][k, 1], g["t"][k, 0]])
    rel = pts - g["p"][k]
    o = (rel * n).sum(-1)
    along = (rel * g["t"][k]).sum(-1)
    side = (o > 0).astype(int)
    w = g["width"][k, side]
    if reach is None:
        inside = (np.abs(o) <= w) & (np.abs(along) <= 1.0) & (w > 0)
    else:
        inside = (np.abs(o) <= reach) & (np.abs(along) <= 1.0)
    if "grade" not in g:
        g["grade"] = np.gradient(g["z"], g["s"]) if len(g["s"]) > 1 else np.zeros(len(g["s"]))
    z = g["z"][k] + g["grade"][k] * along + g["fall"][k, side] * np.abs(o)
    # (a street that meets its governing one takes that one's surface where they meet and blends into its own crown
    # over BLEND m: crowned up to the edge, the two met in a seam, 3 jumps and a 7.7 deg roll at Palmovka)
    gov = g.get("gov")
    if gov is not None and not own and len(g.get("pin_s", ())):
        ds = np.min(np.abs(g["s"][k][:, None] - np.asarray(g["pin_s"])[None, :]), axis=1)
        u = np.clip(ds / BLEND, 0, 1)
        u = u * u * (3 - 2 * u)
        near = inside & (u < 1)
        if near.any():
            zg = governing_height(gov, pts[near], reach=1e9)
            ok = np.isfinite(zg)
            idx = np.flatnonzero(near)[ok]
            z[idx] = u[idx] * z[idx] + (1 - u[idx]) * zg[ok]
    return np.where(inside, z, np.nan)


def fill_2d(known, free, data, lam, iters=3000, tol=1e-7):
    """A smooth surface over the `free` cells of a grid: nearest `data` (NaN: no pull) under a curvature penalty `lam`
    (the graph Laplacian squared over the free and known cells), meeting the `known` cells (finite: held). Conjugate
    gradients, matrix-free (no scipy here)."""
    act = free | np.isfinite(known)
    # (neighbours across a step in IPR over STEP_CUT are not joined: a wall between the bus terminal by Palmovka and the
    # street under it, smeared, set the terminal's edge 2.5 m off)
    ref = np.where(np.isfinite(known), known, data)

    pairs = []
    for sl_a, sl_b in (((slice(1, None), slice(None)), (slice(None, -1), slice(None))),
                       ((slice(None, -1), slice(None)), (slice(1, None), slice(None))),
                       ((slice(None), slice(1, None)), (slice(None), slice(None, -1))),
                       ((slice(None), slice(None, -1)), (slice(None), slice(1, None)))):
        pairs.append((sl_a, sl_b, act[sl_a] & act[sl_b] & ~(np.abs(ref[sl_a] - ref[sl_b]) > STEP_CUT)))

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
    grid = fill_2d(known, free, data, lam)
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


def drive_measures(zfun, cs, raw=False):
    """The street bot's measures on a surface (zfun(x, y) -> z) along every street's two drive lines (LANE m either
    side of its centreline, every metre): jumps over JUMP within 1 m, the change of grade over a car, the wheels'
    left-to-right difference (roll) and the 1 m bend (bumpy)."""
    jumps, dgrade, roll, bend, places = 0, [], [], [], []
    for c in cs:
        n = np.column_stack([-c["t"][:, 1], c["t"][:, 0]])
        for side in (-1, 1):
            q = c["p"] + n * side * LANE
            z = zfun(q[:, 0], q[:, 1])
            zl = zfun(*(q + n * AXLE / 2).T)
            zr = zfun(*(q - n * AXLE / 2).T)
            ok = np.isfinite(z)
            dz = np.abs(np.diff(z))
            big = np.flatnonzero(np.isfinite(dz) & (dz > JUMP))
            jumps += len(big)
            for i in big:
                places.append({"street": c["name"], "x": round(float(q[i, 0]), 1), "y": round(float(q[i, 1]), 1),
                               "jump": round(float(dz[i]), 2)})
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
            "bend in 1 m p50/99/100 m": pct(bend, (50, 99, 100)), "places": places[:40],
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
    rep["drive lines"] = {"survey": drive_measures(svy, cs), "IPR": drive_measures(lidar, cs),
                          "generated": drive_measures(gen, cs)}
    with open(os.path.join(out_dir, "pilot.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in rep.items() if k != "drive lines"}, ensure_ascii=False, indent=1))
    for k, v in rep["drive lines"].items():
        print(k, {a: b for a, b in v.items() if a != "places"})
    return rep


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
    return {"F": Frame(), "ipr": IprDtm(), "dtm": dtm, "L": L, "road": road, "cover": cover, "tris": tris}


def line_wide(lines, cell, out_path):
    """Every line's corridor in squares of `cell` m (each square holding the line's track), built as the pilot builds
    Palmovka and measured: the surface against IPR 1 m inside the road's edge, and the drive lines, survey against
    generated, summed per line."""
    import shapely
    out = {}
    for ln in lines:
        ctx = context(ln)
        L = ctx["L"]
        pts = np.asarray(L["path"] + L.get("pathBack", []), float)
        sq = sorted({(int(math.floor(x / cell)), int(math.floor(y / cell))) for x, y in pts})
        acc = {k: {"dev": [], "jumps": 0, "rolls": 0, "dgrade": [], "roll": [], "bend": []} for k in ("survey", "generated")}
        places = []
        for n, (i, j) in enumerate(sq):
            at, radius = ((i + 0.5) * cell, (j + 0.5) * cell), cell / 2
            cs, _, F, ipr, road = pilot(at, radius, ln, None, ctx)
            if not cs:
                continue
            field = junctions(cs, F, ipr, road, [(at[0] - radius, at[1] - radius), (at[0] + radius, at[1] + radius)])
            xg, yg = np.meshgrid(np.arange(at[0] - radius, at[0] + radius, 0.5),
                                 np.arange(at[1] + radius, at[1] - radius, -0.5))
            x, y = xg.ravel(), yg.ravel()
            inner = shapely.contains_xy(road.buffer(-1.0), x, y)
            zi = np.asarray(ipr.sample(x[inner] + F.E0, y[inner] + F.N0), float)
            zs = sample_tris(ctx["tris"], x[inner], y[inner])
            zg = generated(cs, x[inner], y[inner], road, field)
            fns = {"survey": lambda a, b, tris=ctx["tris"]: sample_tris(tris, np.asarray(a, float), np.asarray(b, float)),
                   "generated": lambda a, b, cs=cs, road=road, field=field: generated(
                       cs, np.asarray(a, float), np.asarray(b, float), road, field)}
            for k, z in (("survey", zs), ("generated", zg)):
                d = z - zi
                acc[k]["dev"].extend(d[np.isfinite(d)].tolist())
                m = drive_measures(fns[k], [c for c in cs if c["highway"] != "tracks"], raw=True)
                acc[k]["jumps"] += m["jumps"]
                acc[k]["rolls"] += m["rolls over 7 deg"]
                for q in ("dgrade", "roll", "bend"):
                    acc[k][q].extend(m["_raw"][q])
                if k == "generated":
                    places.extend(m["places"])
            print(f"line {ln}: square {n + 1}/{len(sq)}", flush=True)
        res = {}
        for k, a in acc.items():
            d = np.asarray(a["dev"])
            res[k] = {"off IPR 1 m inside the edge, mean / p99 |.| m": [round(float(d.mean()), 3),
                                                                        round(float(np.percentile(np.abs(d), 99)), 3)],
                      "jumps": a["jumps"], "rolls over 7 deg": a["rolls"],
                      "change of grade over 4.5 m p99 / max %": [round(v * 100, 2) for v in pct(a["dgrade"], (99, 100))],
                      "roll p99 / max deg": pct(a["roll"], (99, 100)), "bend in 1 m p99 m": pct(a["bend"], (99,))[0]}
        res["squares"] = len(sq)
        res["generated jumps, places"] = places[:30]
        out[ln] = res
        print(ln, json.dumps({k: v for k, v in res.items() if k != "generated jumps, places"}, ensure_ascii=False))
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--json", default=os.path.join(ROOT, "reports", "street_profile", "calibration.json"))
    ap.add_argument("--pilot", help="X,Y: build the streets around this place (local frame) and measure them")
    ap.add_argument("--line", type=int, default=37, help="--pilot: the line whose survey data to read")
    ap.add_argument("--radius", type=float, default=150.0, help="--pilot: half the square's side, m")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "street_profile"))
    ap.add_argument("--wide", type=float, metavar="CELL", help="every line of --lines in squares of CELL m (300)")
    a = ap.parse_args(argv)
    if a.wide:
        from baseline_store import HeavyJob
        with HeavyJob("street_profile"):
            line_wide([int(v) for v in a.lines.split(",")], a.wide, os.path.join(a.out, "lines.json"))
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
