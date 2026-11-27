# SPDX-License-Identifier: AGPL-3.0-or-later
"""IPR's pits under the survey's streets, in the raster as the readers see it and in the written ground (#867).

    python -P -E tools/bench/street_pits.py [--lines 9,17,22,23,37] [--json OUT]

Every pit tools/ipr_pits.py finds on the tiles with survey streets (the raster as it is, IprDtm(fills=None)), with
the rule's verdict, and per street pit of a SHOWN class (road, sidewalk) 1 m or more deep:
- **left in the raster**: a pit the rule fills, read from the raster as every reader reads it (IprDtm with
  data/ipr.fills.json) still DEEP or more under its rim. 0 once the fills are built (tools/ipr_pits.py).
- **shown in the ground**: a hole in the written ground (data/lineN.ground.*, tools/ground_at.py file_at, the survey's
  height where it has one): at the pit's deepest cell it lies SHOW or more under the rim (its plane; the closing where
  the rule fit none) and as far under the low side of the ground round the pit (LOW: that share of the written
  ground's heights at the cells 1-3 m outside it, ipr_pits `round`), per line whose tiles hold it: those the rule
  fills (0 after the lines are rebuilt on the fills) and those it keeps, by why.
  The scan of 2026-11-26 on the data of 2026-11-23: 30 road and sidewalk pits shown 0.5 m or more (#867).
  Under the ground round it too, not the rim's plane alone: at a wall's or a slope's foot the pit's rim is the top on one side
  and the foot on the other, its plane lies between them, and the ground, held to the wall's foot by the survey's wall
  lines, lay under that plane with no hole in it: line 9 (-3326.3, -1457.4), a sidewalk at 222.08 m under a plane of
  222.92, the sidewalk beside it to the south at 221.9-222.0; line 17 (2726.7, 3455.6); lines 22 and 23
  (-438.3, 377.6), on a wall 6 m tall (ground batch E, #757: 3 of the 106 pits filled counted as shown). And under
  the rim's plane, not the ground round it alone: a ramp's foot lies under the ramp beside it (line 9
  (-7378.3, -1291.4), a road ramp between walls, 0.52 m).
Exit 1 when a pit the rule fills is left in the raster, or shown in a ground built after the fills file.
"""
import argparse
import json
import os
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

SHOWN = ("road", "sidewalk")  # the classes counted (#867: "30 → 0 on the five lines")
SHOW = 0.5  # m under the ground round it: shown in the ground
LOW = 10  # percent: the low side of the ground round a pit
DEEP = 1.0  # m under the rim: left in the raster


def ground(G, xs, ys):
    """The written ground at points: the survey's height where it has one, else the ground's; NaN where the line's
    file has no triangle (network.Survey.hit past its tiles)."""
    try:
        rows = G.file_at(xs, ys)
    except IndexError:
        rows = []
        for x, y in zip(xs, ys):
            try:
                rows.append(G.file_at([x], [y])[0])
            except IndexError:
                rows.append((None, float("nan"), None))
    return np.array([zs if zs is not None else zg for zs, zg, _ in rows], float)


def hole(z, around, level):
    """How far a pit's ground z lies under its rim's level and under the low side of the ground round it (the heights
    `around`), the lesser of the two; without any ground round it, under its rim's level."""
    around = np.asarray(around, float)
    around = around[np.isfinite(around)]
    return float(min(level, np.percentile(around, LOW)) - z) if len(around) else float(level - z)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    import dmr5g
    import ground_at
    import ipr_pits as ip
    from geo import Frame, tile_index
    from ipr_dtm import FILLS, IprDtm
    survey, _ = ip.areas()
    found = ip.scan(IprDtm(fills=None), survey, dmr5g.Tiles(fetch=False).sample, log=lambda *a, **k: None)
    street = [p for p in found if p["class"] in SHOWN]
    F, read = Frame(), IprDtm()
    filled = [p for p in street if p["kept"] is None]
    for p in street:
        p["level"] = p["rim"] if p["rim"] is not None else p["top"]
    if filled:
        z = read.sample(np.array([p["x"] for p in filled]) + F.E0, np.array([p["y"] for p in filled]) + F.N0)
        for p, v in zip(filled, z):
            p["read"] = round(float(v), 2)
    left = [p for p in filled if not p["read"] >= p["level"] - DEEP]
    print(f"street pits ({', '.join(SHOWN)}) 1 m or more deep: {len(street)}; the rule fills {len(filled)}; "
          f"left in the raster as read: {len(left)}")
    fills_t = os.path.getmtime(FILLS) if os.path.exists(FILLS) else None
    shown, late = {}, []
    for ln in a.lines.split(","):
        path = os.path.join(ROOT, "data", f"line{ln}.ground.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            tiles = {(t["e"], t["n"]) for t in json.load(fh)["tiles"]}
        mine = [p for p in street if tuple(int(v) for v in tile_index(p["x"], p["y"])) in tiles]
        G = ground_at.Ground(ln)
        rows = []
        for p in mine:
            z = float(ground(G, [p["x"]], [p["y"]])[0])
            if z != z:
                continue
            h = hole(z, ground(G, *p["round"]) if p["round"] is not None and len(p["round"][0]) else [], p["level"])
            if h >= SHOW:
                rows.append({**{k: p[k] for k in ("x", "y", "class", "depth", "level", "kept")}, "shown": round(h, 2),
                             "under its rim": round(p["level"] - z, 2)})
        shown[ln] = rows
        after = fills_t is not None and os.path.getmtime(path) > fills_t
        if after:
            late += [r for r in rows if r["kept"] is None]
        by = Counter(r["kept"] or "filled by the rule" for r in rows)
        print(f"line {ln}: shown {SHOW} m or more: {len(rows)} ({dict(by)}){'' if after else ' (ground built before the fills)'}")
    every = {(r["x"], r["y"]): r for rows in shown.values() for r in rows}
    by = Counter(r["kept"] or "filled by the rule" for r in every.values())
    print(f"every line, each place once: {len(every)} ({dict(by)})")
    for r in sorted(every.values(), key=lambda r: -r["shown"]):
        print(f"  ({r['x']}, {r['y']}) {r['class']} {r['depth']} m deep, shown {r['shown']} m: {r['kept'] or 'filled by the rule'}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"left": left, "shown": shown}, fh, ensure_ascii=False, indent=1, default=str)
    return 1 if left or late else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
