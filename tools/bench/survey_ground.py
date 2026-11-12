# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street survey's ground-level areas against IPR's lidar and the surveyed rails, as built (#446).

    python -P -E tools/bench/survey_ground.py [--lines 9,17,22,23,37] [--top 10] [--dtm DIR] [--json reports/survey-ground.json]

--dtm reads lineN.dtm.json from DIR instead of data/ (main's copies, to compare).

Judges each line's data/lineN.dtm.json as tools/dtm.py does (tools/zps_ground.py: IPR 1 m inside the outline, the
covers, the rails, DMR 5G, OSM's construction sites; no facts), so on main's data it shows what the rule would do and on
rebuilt data what it left. Per line: the level-0 areas and m² by verdict and by offset, and the rails: at each 2 m
station of DI's and DTMP's tracks with heights under open sky inside a level-0 area of a paved class, the survey's
surface (its three nearest outline vertices) and IPR against the top of rail.
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import shapely  # noqa: E402

import dmr5g  # noqa: E402
import osm_local  # noqa: E402
import zps_ground as zg  # noqa: E402
from dtmp_tracks import archive_data, di_data  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402

F = Frame()
PAVED = {"tram", "road", "paved", "parking", "island", "platform", "sidewalk", "cycle"}


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    lines = arg("--lines", "9,17,22,23,37").split(",")
    top = int(arg("--top", "10"))
    ipr = IprDtm()
    dem = dmr5g.Tiles(directory=os.path.join(ROOT, "raw", "dem"))
    rails = zg.rail_points(di_data()[1] + archive_data()[2])
    rx, ry, rz = rails
    report = {}
    for L in lines:
        line = json.load(open(os.path.join(ROOT, "data", f"line{L}.json"), encoding="utf-8"))
        areas = json.load(open(os.path.join(arg("--dtm", os.path.join(ROOT, "data")), f"line{L}.dtm.json"),
                               encoding="utf-8"))["areas"]
        pts = line["path"] + line.get("pathBack", [])
        osm_c, osm_ch = [], []
        if osm_local.available():
            osm_c = zg.osm_covers(osm_local.ways(zg.is_cover, bbox=F.bbox(pts, 150)), F)
            osm_ch = zg.osm_covers(osm_local.ways(zg.is_changing, bbox=F.bbox(pts, 150)), F)
        cover = zg.cover_union(areas, osm_c)
        v = zg.judge(areas, ipr.sample, dem.sample, cover, rails, F, (), zg.cover_union([], osm_ch))
        n, m2 = {}, {}
        for x in v.values():
            n[x["verdict"]] = n.get(x["verdict"], 0) + 1
            m2[x["verdict"]] = m2.get(x["verdict"], 0) + x["m2"]
        offs = np.array([abs(x.get("offset", 0)) for x in v.values()])
        am = np.array([x["m2"] for x in v.values()])
        print(f"\n== line {L}: {len(v)} level-0 areas, {am.sum():,.0f} m2")
        print("  by verdict: " + ", ".join(f"{k} {n[k]} ({m2[k]:,.0f} m2)" for k in sorted(n, key=lambda k: -m2[k])))
        print("  |offset| from IPR: " + ", ".join(
            f"{lo}-{hi} m {((offs >= lo) & (offs < hi)).sum()} ({am[(offs >= lo) & (offs < hi)].sum():,.0f} m2)"
            for lo, hi in ((0.5, 1), (1, 2), (2, 1e9))))
        # the rails
        geoms = {i: (shapely.Polygon(np.array(areas[i]["r"])[:, :2]).buffer(0),
                     np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in areas[i]["r"]], float))
                 for i, x in v.items() if x["c"] in PAVED}
        keys = list(geoms)
        tree = shapely.STRtree([geoms[i][0] for i in keys])
        bb = shapely.box(*shapely.MultiPoint(np.array(pts)).bounds).buffer(100)
        near = shapely.contains_xy(bb, rx, ry)
        k = np.nonzero(near)[0]
        if len(k) and not cover.is_empty:
            k = k[~shapely.contains_xy(cover, rx[k], ry[k])]
        hit_p, hit_a = tree.query(shapely.points(rx[k], ry[k]), predicate="within")
        sv, iv = [], []
        gE, gN = F.to_jtsk(rx[k], ry[k])
        gi = np.asarray(ipr.sample(gE, gN), float)
        for p, a in zip(hit_p, hit_a):
            j = k[p]
            sv.append(zg.surface_at(geoms[keys[a]][1], rx[j], ry[j]) - rz[j])
            iv.append(gi[p] - rz[j])
        sv, iv = np.array(sv), np.array(iv)
        ok = np.isfinite(sv) & np.isfinite(iv)
        sv, iv = sv[ok], iv[ok]
        if len(sv):
            print(f"  rails: {len(sv)} stations under open sky in paved level-0 areas; within 0.3 m of the top of rail: "
                  f"survey {(abs(sv) <= 0.3).mean() * 100:.1f} %, IPR {(abs(iv) <= 0.3).mean() * 100:.1f} %; "
                  f"survey p5/p50/p95 {np.percentile(sv, [5, 50, 95]).round(2)}, IPR {np.percentile(iv, [5, 50, 95]).round(2)}")
            bad = abs(sv) > 0.5
            print(f"    survey > 0.5 m off: {bad.sum()} (IPR within 0.3 m there: {(abs(iv[bad]) <= 0.3).sum()}); "
                  f"IPR > 0.5 m off: {(abs(iv) > 0.5).sum()} (the survey within 0.3 m there: {(abs(sv[abs(iv) > 0.5]) <= 0.3).sum()})")
        for verdict in ("lidar", "survey", "review", "changing"):
            sel = sorted([x for x in v.values() if x["verdict"] == verdict], key=lambda x: -x["m2"])[:top]
            for x in sel:
                print(f"    {verdict:8} {x['c']:9} {x['m2']:8.0f} m2  offset {x['offset']:+6.2f}  spread {x['spread']:.2f}  "
                      f"{x.get('by', ''):6} {x.get('rails', '')} {'dmr5g ' + str(x['older']) if 'older' in x else ''}  "
                      f"{x['lat']}, {x['lon']}")
        report[L] = {"verdicts": {str(i): x for i, x in v.items()}, "rails": {"survey": sv.round(3).tolist(), "ipr": iv.round(3).tolist()}}
    out = arg("--json", os.path.join(ROOT, "reports", "survey-ground.json"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(report, open(out, "w", encoding="utf-8"))
    print("\nwritten", out)


if __name__ == "__main__":
    main()
