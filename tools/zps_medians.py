# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's medians (Dělící pás, 010000001503) among its other areas (#555): python -P -E tools/test_zps_medians.py.

A median between two carriageways is its own class (`median`), raised behind kerbs like an island
(tools/kerbs.py) and a boundary between carriageways where the cars fit their lanes (src/traffic.js _fitRoad).
The survey gives it no surface, and it maps some twice:
- a median mostly (COVERED or more of it) under a ground-level `tram` area is the tram reservation between the
  carriageways, mapped as both (8 of line 22's 31 within 40 m of the route, 2026-11-14): the tram area stays and the
  median goes;
- a median mostly under OSM's green (the line's `green`, grass, parks) is grass (`s: "green"`), paved otherwise.
"""
from shapely.geometry import Polygon
import shapely

COVERED = 0.5   # share of a median's area under another area that makes it that area's


def _poly(ring, holes=()):
    p = Polygon([q[:2] for q in ring], [[q[:2] for q in h] for h in holes if len(h) >= 3])
    return p if p.is_valid else p.buffer(0)


def _share(p, tree, polys):
    if p.is_empty or p.area <= 0:
        return 0.0
    hits = [polys[int(k)] for k in tree.query(p)] if tree is not None else []
    if not hits:
        return 0.0
    return shapely.union_all([h.intersection(p) for h in hits]).area / p.area


def sort(areas, green):
    """Drop the medians that are tram reservations and mark the green ones, in place: areas as tools/dtm.py writes them
    ({c, l, r, h}), green as the line's OSM green ({p}). Returns the counts {medians, tram, green, paved}."""
    trams = [_poly(a["r"], a.get("h", ())) for a in areas if a["c"] == "tram" and a["l"] == 0 and len(a["r"]) >= 3]
    greens = [_poly(g["p"]) for g in green if len(g.get("p") or []) >= 3]
    tt = shapely.STRtree(trams) if trams else None
    gt = shapely.STRtree(greens) if greens else None
    out, n = [], {"medians": 0, "tram": 0, "green": 0, "paved": 0}
    for a in areas:
        if a["c"] != "median":
            out.append(a)
            continue
        n["medians"] += 1
        p = _poly(a["r"], a.get("h", ()))
        if a["l"] == 0 and _share(p, tt, trams) >= COVERED:
            n["tram"] += 1
            continue
        if _share(p, gt, greens) >= COVERED:
            a["s"] = "green"
            n["green"] += 1
        else:
            n["paved"] += 1
        out.append(a)
    areas[:] = out
    return n
