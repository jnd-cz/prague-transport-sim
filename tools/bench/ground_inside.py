"""The inside of the survey's level-0 areas against IPR's lidar, per line and class (#444).

    python -P -E tools/bench/ground_inside.py [--lines 9,17,22,23,37] [--dtm DIR] [--page main] [--edge 5] [--step 2]
                                              [--json PATH]

--dtm reads lineN.dtm.json from DIR instead of data/ (main's copies, to compare); --page main drapes as main's page
did (every ground-level `green`), not by the build's mark (`g`, #444); --edge M drapes to M m triangles (the page: 5).

Each level-0 area (not a wall or a roof) is sampled on a lattice of STEP m inside its outline, 0.5 m or more off it.
The surface there, as the page draws it (src/terrain.js DtmSurface): the linear sheet between its outline vertices
(shapely's constrained Delaunay, #276's T2, for the page's earcut over the same outline), and for an area the build
marked `g` the page's drape: the outline cut to 4 m, the triangles halved to 5 m, each new point on the ground (here
IPR's raster, where the page reads its terrain: IPR sampled every 2 m near the tracks). Against IPR's 1 m raster at
the point, per class: areas, m², samples, the 5th / 50th / 95th percentile of surface − IPR and the share beyond 1 m.
The parts under a deck (inside a level-1 area that is not a roof or a wall) are one row of their own, "under a deck",
and left out of their class; on data the build marked, the areas of the draped classes it left as sheets too ("green
(sheet)" ...).
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import shapely  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import zps_inside as zi  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402

F = Frame()
SKIP = {"wall", "roof"}
UNDER = "under a deck"


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def pieces(ring, piece=4.0):
    """The page's cut of a ground-level outline into equal pieces of at most 4 m, heights linear (DtmSurface)."""
    out = []
    for i in range(len(ring)):
        p, q = ring[i], ring[(i + 1) % len(ring)]
        n = max(1, int(np.ceil(np.hypot(q[0] - p[0], q[1] - p[1]) / piece)))
        out += [p + (q - p) * j / n for j in range(n)]
    return np.array(out, float)


def drape(tris, ground, edge=10.0):
    """The page's drape (DtmSurface._split with the terrain): each triangle halved at its longest edge until none is
    over `edge`, the new point on the ground."""
    done, todo = [], tris
    for _ in range(16):
        if not len(todo):
            break
        e = np.stack([np.hypot(*(todo[:, (k + 1) % 3, :2] - todo[:, k, :2]).T) for k in range(3)], 1)
        big = e.max(axis=1) > edge
        done.append(todo[~big])
        t, e = todo[big], e[big]
        k = e.argmax(axis=1)  # the longest edge: from corner k to k+1
        idx = np.arange(len(t))
        p, q, r = t[idx, k], t[idx, (k + 1) % 3], t[idx, (k + 2) % 3]
        m = (p + q) / 2
        m[:, 2] = np.asarray(ground(m[:, 0], m[:, 1]), float)
        m[:, 2] = np.where(np.isfinite(m[:, 2]), m[:, 2], (p[:, 2] + q[:, 2]) / 2)
        todo = np.concatenate([np.stack([p, m, r], 1), np.stack([m, q, r], 1)])
    done.append(todo)
    return np.concatenate(done)


DRAPED = lambda a: a.get("g")  # noqa: E731 (main's page: --page main)
EDGE = 5.0  # m: the page's drape (src/terrain.js DRAPE_EDGE); --edge to try another


def triangles(a, ground):
    """(n, 3, 3) triangles of the area's surface as the page draws it: the sheet over its outline (tools/zps_inside.py
    triangulate), draped on the ground where the build marked it (`g`, #444)."""
    rings = [zi.filled(a["r"], ground)] + [zi.filled(h, ground) for h in a.get("h", []) if len(h) >= 3]
    if DRAPED(a):
        rings = [pieces(r) for r in rings]
    out = zi.triangulate(rings)
    return drape(out, ground, EDGE) if DRAPED(a) and len(out) else out


def main():
    global DRAPED, EDGE
    if arg("--page", "") == "main":
        DRAPED = lambda a: a["l"] == 0 and a["c"] == "green"  # noqa: E731
        EDGE = 10.0  # (main's page draped its lawns to 10 m)
    EDGE = float(arg("--edge", EDGE))
    lines = arg("--lines", "9,17,22,23,37").split(",")
    src = arg("--dtm", os.path.join(ROOT, "data"))
    step = float(arg("--step", "2"))
    ipr = IprDtm()
    ground = lambda x, y: ipr.sample(*F.to_jtsk(np.asarray(x, float), np.asarray(y, float)))  # noqa: E731
    out = {}
    for L in lines:
        areas = json.load(open(os.path.join(src, f"line{L}.dtm.json"), encoding="utf-8"))["areas"]
        decks = unary_union([shapely.Polygon([q[:2] for q in a["r"]]).buffer(0) for a in areas
                             if a["l"] >= 1 and a["c"] not in SKIP and len(a["r"]) >= 3])
        rows = {}
        marked = any(a.get("g") for a in areas)
        for a in areas:
            if a["l"] != 0 or a["c"] in SKIP or len(a["r"]) < 3:
                continue
            poly = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3]).buffer(0)
            if poly.is_empty:
                continue
            x, y = zi.lattice(poly, step)
            # (an area of a draped class the build left as a sheet: its own row)
            name = a["c"] + (" (sheet)" if marked and a["c"] in zi.INSIDE and not a.get("g") else "")
            row = rows.setdefault(name, {"areas": 0, "m2": 0.0, "d": []})
            row["areas"] += 1
            row["m2"] += poly.area
            if not len(x):
                continue
            z = zi.at(triangles(a, ground), x, y)
            g = ground(x, y)
            d = z - g
            under = shapely.contains_xy(decks, x, y) if not decks.is_empty else np.zeros(len(x), bool)
            row["d"].append(d[~under & np.isfinite(d)])
            if under.any():
                u = rows.setdefault(UNDER, {"areas": 0, "m2": 0.0, "d": []})
                u["areas"] += 1
                u["m2"] += poly.intersection(decks).area
                u["d"].append(d[under & np.isfinite(d)])
        print(f"== line {L}")
        print(f"{'class':14s} {'areas':>6s} {'m2':>10s} {'samples':>9s} {'p5':>7s} {'p50':>7s} {'p95':>7s} {'>1 m':>7s}")
        res = {}
        for c in sorted(rows, key=lambda c: -rows[c]["m2"]):
            r = rows[c]
            d = np.concatenate(r["d"]) if r["d"] else np.zeros(0)
            p = np.percentile(d, [5, 50, 95]) if len(d) else [np.nan] * 3
            share = float(np.mean(np.abs(d) > 1)) if len(d) else np.nan
            res[c] = {"areas": r["areas"], "m2": round(r["m2"]), "samples": int(len(d)),
                      "p5": round(float(p[0]), 2), "p50": round(float(p[1]), 2), "p95": round(float(p[2]), 2),
                      "beyond1": round(share, 3)}
            print(f"{c:14s} {r['areas']:6d} {r['m2']:10,.0f} {len(d):9,d} {p[0]:7.2f} {p[1]:7.2f} {p[2]:7.2f} {share:7.1%}")
        out[L] = res
    if "--json" in sys.argv:
        with open(arg("--json", ""), "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
