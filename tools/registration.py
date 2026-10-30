"""Layer registration check (#8): how far each built layer sits from the survey, as an offset per layer.

    python -P -E tools/registration.py --line 17          # lines with surveyed streets (DTM ZPS): 17, 22
    python -P -E tools/registration.py --line 17 --tiles  # also per 1 km tile (is the offset uniform?)

Reference: the Prague DTM survey (ZPS, native S-JTSK, cm): building outlines, tree pits, pole carriers,
water and sewer connection points. Tested: the built layers in game metres (data/lineN.*):
- points (Geoportál trees, archived DTM street points) against the nearest reference point within
  15 m: the offset is the peak of the 2D histogram of those vectors (robust to wrong pairs);
- outlines (IPR LOD2 buildings from bld.bin, OSM buildings) against the survey outlines: a trimmed
  point-to-line fit (ICP) of points every metre along the test edges.
Writes reports/registration_lineN.json. An offset over ~0.5 m means the layer's conversion is wrong.
"""
import json
import math
import os
import struct
import sys
from functools import cache

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
import gpkg  # noqa: E402
from geo import ROOT, Frame  # noqa: E402
from dtm_packages import DTM, select_packages  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "17"
TILES = "--tiles" in sys.argv
F = Frame()

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
xs = [p[0] for p in line["path"]]
ys = [p[1] for p in line["path"]]
BOX = (min(xs) - 150, min(ys) - 150, max(xs) + 150, max(ys) + 150)
inbox = lambda x, y: BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3]  # noqa: E731


# ------------------------------------------------------------------ reference: the survey
@cache
def survey_packages():
    return select_packages(ROOT, districts=DTM[LINE])


def survey(kind, code):
    """Survey features of one object type (code) in the line's box, in game metres."""
    out = []
    for package in survey_packages():
        path = package.path(kind)
        table = next((t for t in gpkg.layers(path) if t.endswith(code) or f"#{code}_" in t), None)
        if not table:
            continue
        for feat in gpkg.features(path, table):
            g = feat["geom"]
            if g:
                out.append(g)
    return out


def rings(g):
    """The coordinate lists of a decoded geometry (gpkg: (type, coords)): lines and polygon rings."""
    kind, c = g
    if kind == "Point":
        return [[c]]
    if kind == "LineString":
        return [c]
    if kind == "Polygon":
        return c
    return [r for part in c for r in rings(part)]


def flat(g):
    return [p for r in rings(g) for p in r]


def ref_points(kind, code):
    pts = []
    for g in survey(kind, code):
        c = flat(g)
        if not c:
            continue
        e, n = sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c)  # (a pit: its centre)
        x, y = F.from_jtsk(e, n)
        if inbox(x, y):
            pts.append((float(x), float(y)))
    return np.array(pts)


def ref_lines(kind, code):
    segs = []
    for g in survey(kind, code):
        for c in rings(g):
            if len(c) < 2:
                continue
            p = [tuple(float(v) for v in F.from_jtsk(q[0], q[1])) for q in c]
            if any(inbox(*q) for q in p):
                segs.append(LineString(p))
    return segs


# ------------------------------------------------------------------ the offsets
def peak(vecs, bin_=0.25, r=15):
    """The densest offset: the peak of the 2D histogram of vectors (smoothed 3 x 3)."""
    n = int(2 * r / bin_)
    h, ex, ey = np.histogram2d(vecs[:, 0], vecs[:, 1], bins=n, range=[[-r, r], [-r, r]])
    k = np.ones((3, 3))
    hs = sum(np.roll(np.roll(h, i, 0), j, 1) * k[i + 1, j + 1] for i in (-1, 0, 1) for j in (-1, 0, 1))
    i, j = np.unravel_index(np.argmax(hs), hs.shape)
    c = np.array([(ex[i] + ex[i + 1]) / 2, (ey[j] + ey[j + 1]) / 2])
    near = vecs[np.hypot(*(vecs - c).T) < 1.0]
    return (near.mean(0) if len(near) else c), len(near)


def point_offset(test, ref):
    if len(test) == 0 or len(ref) == 0:
        return None
    tree = STRtree([Point(p) for p in ref])
    vecs = []
    for p in test:
        i = tree.nearest(Point(p))
        q = ref[i]
        if math.dist(p, q) < 15:
            vecs.append((p[0] - q[0], p[1] - q[1]))
    if len(vecs) < 10:
        return None
    v = np.array(vecs)
    off, n = peak(v)
    return {"dx": round(float(off[0]), 2), "dy": round(float(off[1]), 2), "pairs": len(v), "atPeak": n}


def line_offset(test_segs, ref_segs, step=1.0):
    """Trimmed point-to-line ICP: the shift that best puts test edge points on the reference edges."""
    if not test_segs or not ref_segs:
        return None
    pts = []
    for s in test_segs:
        L = s.length
        for k in range(max(1, int(L / step))):
            q = s.interpolate((k + 0.5) * L / max(1, int(L / step)))
            pts.append((q.x, q.y))
    P = np.array(pts)
    tree = STRtree(ref_segs)
    t = np.zeros(2)
    for it in range(8):
        cut = 3.0 if it < 3 else 1.0
        A, b = [], []
        for p in P + t:
            i = tree.nearest(Point(p))
            q = ref_segs[i].interpolate(ref_segs[i].project(Point(p)))
            d = np.array([q.x - p[0], q.y - p[1]])
            L = np.hypot(*d)
            if 0.02 < L < cut:
                nrm = d / L
                A.append(nrm)
                b.append(L)
        if len(A) < 20:
            return None
        A, b = np.array(A), np.array(b)
        dt, *_ = np.linalg.lstsq(A, b, rcond=None)
        t = t + dt
        if np.hypot(*dt) < 0.01:
            break
    # residuals after the fit
    return {"dx": round(float(-t[0]), 2), "dy": round(float(-t[1]), 2), "points": len(P), "fitted": len(A)}


# ------------------------------------------------------------------ the tested layers
def lod2_walls():
    geo = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.geo.json"), encoding="utf-8"))
    tab = geo["buildings"]
    raw = open(os.path.join(ROOT, "data", tab["file"]), "rb").read()
    q, segs = tab["q"], []
    for ch in tab["chunks"]:
        ox, oy, oz = ch["o"]
        v = np.frombuffer(raw, dtype="<i2", count=ch["n"] * 3, offset=ch["v"] * 6).reshape(-1, 3) * q + (ox, oy, oz)
        start = 0
        for bi, cnt in enumerate(ch["b"]):
            if ch.get("k", [0] * len(ch["b"]))[bi] == 0:  # buildings only, not bridges
                tri = v[start:start + cnt].reshape(-1, 3, 3)
                for t in tri:
                    nz = np.cross(t[1] - t[0], t[2] - t[0])
                    if np.hypot(*nz[:2]) > 4 * abs(nz[2]):  # a wall
                        xy = {(round(p[0], 1), round(p[1], 1)) for p in t}
                        if len(xy) == 2:
                            a, b = sorted(xy)
                            if math.dist(a, b) > 1.5:
                                segs.append(LineString([a, b]))
            start += cnt
    return segs


def osm_buildings():
    return [LineString(b["p"] + [b["p"][0]]) for b in line.get("buildings", []) if len(b.get("p", [])) > 2]


def dtm_points(kinds):
    p = os.path.join(ROOT, "data", f"line{LINE}.dtmpoints.json")
    if not os.path.exists(p):
        return np.zeros((0, 2))
    pts = json.load(open(p, encoding="utf-8"))["points"]
    return np.array([(q["x"], q["y"]) for q in pts if q["k"] in kinds])


def trees(kinds=(0, 1, 2, 3)):
    """Geoportál vegetation by kind (geoportal.py: 0-3 the tree register, 4 tree-row samples)."""
    geo = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.geo.json"), encoding="utf-8"))
    return np.array([(t[0], t[1]) for t in geo.get("trees", []) if t[2] in kinds])


def main():
    if LINE not in DTM:
        raise SystemExit(f"line {LINE} has no surveyed streets (lines {', '.join(DTM)})")
    print(f"line {LINE}: reference = DTM ZPS survey (S-JTSK); offsets = layer minus survey, game metres")
    for package in survey_packages():
        print(f"  survey district {package.district}: {package.date}")
    walls = ref_lines("OPL", "010000000103")
    rows = {
        "LOD2 buildings (IPR I3S, Web Mercator)": lambda: line_offset(lod2_walls(), walls),
        "OSM buildings": lambda: line_offset(osm_buildings(), walls),
        "trees (IPR tree register) vs tree pits": lambda: point_offset(trees(), ref_points("OPL", "010000033803")),
        # (tree rows: no survey counterpart; their samples against the register's trees, 9 m apart)
        "tree-row samples vs register trees": lambda: point_offset(trees((4,)), trees((0, 1))),
        "poles, lights, signals (archived DTM points) vs carriers": lambda: point_offset(
            dtm_points({"pole", "light_on_pole", "signal", "traffic_sign", "stop_sign"}), ref_points("KR", "010000020101")),
        "valve caps (archived DTM points) vs water connections": lambda: point_offset(
            dtm_points({"valve_cap", "hydrant_cap"}), ref_points("KR", "010000011601")),
        "manholes, inlets (archived DTM points) vs sewer connections": lambda: point_offset(
            dtm_points({"manhole", "gutter_inlet"}), ref_points("KR", "010000012401")),
    }
    report = {}
    for name, fn in rows.items():
        r = fn()
        report[name] = r
        if r is None:
            print(f"  {name:60s} not enough data")
        else:
            extra = {k: v for k, v in r.items() if k not in ("dx", "dy")}
            # a point layer whose peak holds few pairs has no counterpart in the survey to speak of: no verdict
            r["weak"] = r.get("atPeak", 99) < 10
            print(f"  {name:60s} ({r['dx']:+6.2f}, {r['dy']:+6.2f}) m  |{math.hypot(r['dx'], r['dy']):5.2f}|  {extra}"
                  + ("  WEAK: few pairs agree, no verdict" if r["weak"] else ""))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    json.dump({"line": LINE, "offsets": report}, open(os.path.join(ROOT, "reports", f"registration_line{LINE}.json"), "w",
                                                      encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
