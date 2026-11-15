# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shelter footprints in the survey's platforms: the hole a shelter leaves is filled, and its place and size kept for
the street furniture (#523). Read by tools/dtm.py, after the kerbs.

The survey (ZPS) draws a stop's shelter as a hole in the platform area. Nothing filled it, so the game drew a gap in the
platform. The user, 2026-11-12: "I would fill the hole to keep our ground flat there, however store it's dimensions and
place so the street furniture worker can build shelter there". A hole of a level-0 platform with no survey area of its
own in it is dropped from the platform, whose surface spans it from its outline, and written to `shelters` in
lineN.dtm.json: its centre, length and width (the minimum rotated rectangle), bearing, the platform's height there, the
hole's ring, and the stop (line.json's platforms: name, code, PID id) whose platform holds it. A hole with an area of its own in it stays
a hole: a stair or a shaft (line 9's metro entrance at Želivského, 21.5 m^2, a stairs area that ends at the hole's edge).
An area that also lies under the rest of the platform is not the hole's: a road under an island platform (Pohořelec,
Slánská, Palackého náměstí: the road's polygon spans the whole platform, and its hole showed the road 1-2 m below) or a
tunnel under it (Brusnice over Blanka, Malostranská). Read by the street furniture (#252, #67, #419).

Measured on main's data of 2026-11-12: 1-22 holes in level-0 platforms per line; on lines 22 and 23 almost all 4.0 x
1.8 m (Prague's single shelter), some 7.8 x 1.4-1.9 m (double), one 0.3 x 0.3 m (a post).
"""
import math

import shapely
from shapely.geometry import Polygon

# m^2: an area overlapping a hole by more than this, and the rest of its platform by no more, is the hole's own (a stair,
# a shaft); slivers along the shared edge are neither
INSIDE = 0.05


def _rect(poly):
    """(length, width, bearing in degrees from the x axis, 0-180) of a polygon's minimum rotated rectangle."""
    c = list(poly.minimum_rotated_rectangle.exterior.coords)[:4]
    e = [(c[(i + 1) % 4][0] - c[i][0], c[(i + 1) % 4][1] - c[i][1]) for i in range(2)]
    ln = [math.hypot(*v) for v in e]
    k = 0 if ln[0] >= ln[1] else 1
    return ln[k], ln[1 - k], math.degrees(math.atan2(e[k][1], e[k][0])) % 180


def fill(areas, platforms=()):
    """Drop the empty holes of level-0 platforms (in place) and return {"filled", "kept", "byKind", "shelters"}.
    platforms: line.json's platforms ({"p": polygon, "name", "code", "id"}) to name the stop a shelter belongs to."""
    others = [(i, Polygon([p[:2] for p in a["r"]])) for i, a in enumerate(areas) if len(a["r"]) >= 3]
    others = [(i, g if g.is_valid else g.buffer(0)) for i, g in others]
    tree = shapely.STRtree([g for _, g in others])
    stops = [(Polygon(q["p"]), q) for q in platforms if len(q.get("p", ())) >= 3]
    shelters, kept, by = [], 0, {}
    for i, a in enumerate(areas):
        if a["c"] != "platform" or a["l"] != 0 or not a.get("h"):
            continue
        body = Polygon([p[:2] for p in a["r"]], [[p[:2] for p in h] for h in a["h"]])
        body = body if body.is_valid else body.buffer(0)
        stay, flags = [], []
        for n, h in enumerate(a["h"]):
            hole = Polygon([p[:2] for p in h])
            hole = hole if hole.is_valid else hole.buffer(0)
            full = any(others[j][0] != i and others[j][1].intersection(hole).area > INSIDE
                       and others[j][1].intersection(body).area <= INSIDE for j in tree.query(hole))
            if full or hole.area <= 0:
                stay.append(h)
                if "k" in a:  # (tools/kerbs.py's edge flags, one list per ring: the outline's, then the holes')
                    flags.append(a["k"][n + 1])
                kept += 1
                continue
            ln, wd, brg = _rect(hole)
            c = hole.centroid
            zs = [p[2] for p in h if p[2] is not None]
            s = {"x": round(c.x, 2), "y": round(c.y, 2), "length": round(ln, 2), "width": round(wd, 2),
                 "bearing": round(brg, 1), "z": round(sum(zs) / len(zs), 2) if zs else None,
                 "ring": [[round(p[0], 2), round(p[1], 2)] for p in h]}
            near = min(stops, key=lambda t: t[0].distance(c), default=None)
            if near and near[0].distance(c) < 15:
                s["stop"] = {k: near[1].get(k) for k in ("name", "code", "id")}
            shelters.append(s)
            kind = "single" if ln < 6 and wd > 1 else "double" if ln >= 6 else "post" if ln < 1 else "other"
            by[kind] = by.get(kind, 0) + 1
        if stay:
            a["h"] = stay
        else:
            del a["h"]
        if "k" in a:
            a["k"] = a["k"][:1] + flags
    shelters.sort(key=lambda s: (s["x"], s["y"]))
    return {"filled": len(shelters), "kept": kept, "byKind": dict(sorted(by.items())), "shelters": shelters}
