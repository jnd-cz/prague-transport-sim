"""The survey's decks against the structures that carry them, as built (#445).

    python -P -E tools/bench/decks.py [--lines 9,17,22,23,37] [--dtm DIR]

--dtm reads lineN.dtm.json from DIR instead of data/ (main's copies, to compare).

Per line: the level-1+ vertices (not roofs, walls, stairs) against their structure as tools/zps_decks.py finds it (the
Mosty 3D model's top, else the surveyed rails standing on a structure within 12 m): within 0.5 m, 0.5-2 m, more than
2 m under or over it, and those with neither; the deck-class ramps (zps_decks.ramps); the build's record
(provenance checks.decks) where the file has one. The places of #445:
- the Krejcárek viaduct (line 37, route s 3028-3494): level-1 vertices within 12 m of the route against the rails and
  the model (the nearer of the two);
- Divadelní (lines 9, 22, 23; OSM way 141140410 under the deck): the deck's top over the opening against the plane of
  the rails over it, the deck's thickness and its clearance over the carriageway's axis (IPR's floor).
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import shapely  # noqa: E402

import osm_local  # noqa: E402
import zps_decks as zd  # noqa: E402
import zps_ground as zg  # noqa: E402
from dtmp_tracks import archive_data, di_data  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
from mosty3d import Bridges  # noqa: E402

F = Frame()
DIVADELNI = 141140410
KREJCAREK = ("37", 3028.0, 3494.0)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def route_s(line, x, y):
    """Route s and distance of points (the line's path)."""
    p = np.array(line["path"], float)
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    ln = shapely.LineString(p)
    pts = shapely.points(x, y)
    return shapely.line_locate_point(ln, pts), shapely.distance(ln, pts), s


def main():
    lines = arg("--lines", "9,17,22,23,37").split(",")
    ipr = IprDtm()
    ground = lambda x, y: ipr.sample(*F.to_jtsk(np.asarray(x, float), np.asarray(y, float)))  # noqa: E731
    model = zd.Model(Bridges())
    rails = zd.Rails(zg.rail_points(di_data()[1] + archive_data()[2]), ground)
    for L in lines:
        line = json.load(open(os.path.join(ROOT, "data", f"line{L}.json"), encoding="utf-8"))
        doc = json.load(open(os.path.join(arg("--dtm", os.path.join(ROOT, "data")), f"line{L}.dtm.json"), encoding="utf-8"))
        areas = doc["areas"]
        where, xyz = zd._vertices(areas)
        x, y, z = xyz.T
        mz, _ = model.top(x, y)
        rz = rails.at(x, y)
        ref = np.where(np.isfinite(mz), mz, np.where(np.isfinite(rz) & (z <= rz + zd.OVER), rz, np.nan))
        off = z - ref
        has = np.isfinite(off)
        a = np.abs(off[has])
        print(f"\n== line {L}: {len(z)} deck vertices, {has.sum()} on a structure: within 0.5 m {(a <= 0.5).sum()}, "
              f"0.5-2 m {((a > 0.5) & (a <= 2)).sum()}, over 2 m under {(off[has] < -2).sum()}, over 2 m over "
              f"{(off[has] > 2).sum()}; ramps {zd.ramps(areas, ground)}")
        rec = doc.get("provenance", {}).get("lists", {}).get("areas", {}).get("checks", {}).get("decks")
        if rec:
            print(f"  build: moved {rec['vertices']}, held {rec['held']} ({len(rec['heldAreas'])} areas), over {rec['over']}, "
                  f"decks by thickness {rec['decks']}")
            for h in rec["heldAreas"][:8]:
                print(f"    held: {h['c']} {h['n']} vertices under the {h['by']}, {h['lat']}, {h['lon']}")
        if L == KREJCAREK[0]:
            s, d, _ = route_s(line, x, y)
            sel = (s >= KREJCAREK[1]) & (s <= KREJCAREK[2]) & (d <= 12)
            both = np.fmin(np.where(np.isfinite(rz), np.abs(z - rz), np.inf), np.where(np.isfinite(mz), np.abs(z - mz), np.inf))
            dr = (z - rz)[sel & np.isfinite(rz)]
            print(f"  Krejcárek viaduct: {sel.sum()} level-1 vertices within 12 m of the route; off the rails and the model "
                  f"by over 0.5 m {(both[sel] > 0.5).sum()}, over 1 m {(both[sel] > 1).sum()}, over 2 m {(both[sel] > 2).sum()} "
                  f"(none near {np.isinf(both[sel]).sum()}); against the rails p5/p50/p95 {np.percentile(dr, [5, 50, 95]).round(2) if len(dr) else '-'}")
        if L in ("9", "22", "23") and osm_local.available():
            ways = [w for w in osm_local.ways(lambda t: t.get("name") == "Divadelní" and t.get("tunnel") == "yes",
                                              bbox=F.bbox(line["path"], 100)) if w["id"] == DIVADELNI]
            op = zd.openings(ways, areas, F)
            if not op:
                print("  Divadelní: no opening found")
                continue
            o = op[0]
            pts = shapely.points(x, y)
            inside = (shapely.distance(pts, o["poly"]) <= 0.5) & np.array([w[0] in o["decks"] for w in where])
            near = shapely.distance(shapely.points(rails.x, rails.y), o["axis"]) <= 15
            plane = zd._plane(np.column_stack([rails.x[near], rails.y[near], rails.z[near]]))
            dz = z[inside] - plane(x[inside], y[inside])
            cls = [areas[where[n][0]]["c"] for n in np.flatnonzero(inside)]
            ax = np.array([o["axis"].interpolate(f, normalized=True).coords[0] for f in np.linspace(0.1, 0.9, 9)])
            floor = np.asarray(ground(ax[:, 0], ax[:, 1]), float)
            tops, ts = [], []
            for px, py in ax:
                hit = [i for i in o["decks"] if shapely.Polygon(np.array(areas[i]["r"])[:, :2]).buffer(0).contains(shapely.Point(px, py))]
                if hit:
                    r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in areas[hit[0]]["r"]], float)
                    tops.append(zg.surface_at(r, px, py))
                    ts.append(areas[hit[0]].get("t", zd.SLAB))
                else:
                    tops.append(np.nan)
                    ts.append(np.nan)
            clear = np.array(tops) - np.array(ts) - floor
            print(f"  Divadelní: {inside.sum()} deck vertices over the opening ({', '.join(sorted(set(cls)))}), against the "
                  f"rails' plane min/median/max {dz.min():+.2f}/{np.median(dz):+.2f}/{dz.max():+.2f}"
                  + "".join(f"; {c} {np.abs(dz[np.array(cls) == c]).max():.2f}" for c in sorted(set(cls)))
                  + f"; thickness {sorted({areas[i].get('t', zd.SLAB) for i in o['decks']})}; over the carriageway's axis "
                  f"top {np.nanmin(tops):.2f}-{np.nanmax(tops):.2f}, floor {np.nanmin(floor):.2f}-{np.nanmax(floor):.2f}, "
                  f"clearance min {np.nanmin(clear):.2f} m")


if __name__ == "__main__":
    main()
