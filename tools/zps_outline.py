# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's street outlines: a vertex the survey sets off its neighbours where IPR's lidar beside it runs smooth takes
the lidar's height there (#470). Read by tools/dtm.py, before the kerbs.

The survey gives a street area's heights only on its outline, and they scatter along straight kerbs: on the five lines
2-5 % of straight road and sidewalk outline lies over 8 cm off its 21 m mean (tools/bench/street_scatter.py). IPR's 1 m
raster read 1 m inside the area scatters as much: against DI's rails, the noise left in each is alike (median 1.5 cm,
90th percentile 5-10 cm), and of the samples over 15 cm off their mean on straight road outline 0.4-0.8 % are the
survey's alone (IPR within 8 cm there), 0.4-0.7 % IPR's alone, 0.1 % both (2026-11-12). Neither source replaces the
other; where they disagree the smooth one wins:
- each vertex of a street outline (dtm.py SMOOTH) at level 0 against a line fitted along the outline over WIN m either
  side (the survey's own trend, and the same for IPR read INNER m inside the area);
- the survey's vertex off its trend by more than OFF while IPR's stays within CALM takes IPR's height plus the local
  offset between the two (the median of survey - IPR over the window: a sidewalk's foot line lies under IPR inside it);
- one height per place: every level-0 vertex at the same position with the same old height takes it.
Kept as the survey has them: vertices under a deck (IPR reads the deck or a guess under it), areas held off IPR
(zps_ground's verdicts `survey`, `review`, `changing`), and shapes IPR sees too (lowered kerbs, driveways, ramps).
"""
import numpy as np
import shapely

STREETS = {"road", "tram", "parking", "cycle", "sidewalk", "island", "platform", "paved"}
# m along the outline either side: the trend a vertex is held to, widened up to WIDE until it holds MIN_SIDE vertices on
# each side (79 % of straight street outline lies in gaps over 5 m between vertices, line 22)
WIN, WIDE, MIN_SIDE = 10.0, 30.0, 1
MIN_AGREE = 2  # vertices agreeing with IPR in the window, for its offset
OFF = 0.08  # m: survey - IPR at a vertex this far off its local median (lint streetWaviness' threshold) ...
CALM = 0.04  # m: ... while IPR at the vertex stays within this of its mean CALM_REACH m either side along the edge
CALM_REACH = 2.0  # (a line fitted over the window instead read a street's crest or sag: 0.45 m over 30 m at R 1000 m)
MAX = 2.0  # m: a larger move is another level, not an error of this one
# m: the vertices whose survey - IPR lies within this give the local offset (survey - IPR at straight road outline: 5th / 95th
# percentile -0.26 / +0.30 m on the five lines; a run of vertices on a wall's top line, +1.0-1.8 m by Jižní spojka on line
# 22, outnumbered its neighbours and pulled them up when every vertex voted)
AGREE = 0.30
# m inside the area where IPR is read: on straight road outline IPR's share over 8 cm off its mean is 2.0-3.0 % at 0.5 m
# (the raster rounds the kerb), 1.6-2.3 % at 1 m, 1.3-2.0 % at 1.5 m (narrow sidewalks have no 1.5 m)
INNER = 1.0
HELD = {"survey", "review", "changing"}
NOT_UNDER = {"roof", "wall"}  # level-1 areas that are no deck over the ground


def _inner(xy, poly):
    """A point INNER m inside the area from each vertex of one of its rings, along the bisector (NaN where neither side
    lies in it), and the unit tangent there."""
    a = xy - np.roll(xy, 1, axis=0)
    b = np.roll(xy, -1, axis=0) - xy
    a /= np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-9)
    b /= np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-9)
    nrm = np.column_stack([-(a[:, 1] + b[:, 1]), a[:, 0] + b[:, 0]])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    out = np.full(xy.shape, np.nan)
    for sgn in (1, -1):
        q = xy + sgn * INNER * nrm
        ok = ~np.isfinite(out[:, 0]) & shapely.contains_xy(poly, q[:, 0], q[:, 1])
        out[ok] = q[ok]
    return out, np.column_stack([nrm[:, 1], -nrm[:, 0]])


def ring_fixes(r, poly, ground):
    """{vertex index: new height} for one closed ring (n, 3) (no closing point) of an area (its polygon `poly`)."""
    n = len(r)
    if n < 2 * MIN_SIDE + 1:
        return {}
    xy = r[:, :2]
    s = r[:, 2]
    pin, tan = _inner(xy, poly)
    ok = np.isfinite(pin[:, 0])
    g, bend = np.full(n, np.nan), np.full(n, np.nan)
    if ok.any():
        g[ok] = np.asarray(ground(pin[ok, 0], pin[ok, 1]), float)
        a = np.asarray(ground(*(pin[ok] - CALM_REACH * tan[ok]).T), float)
        b = np.asarray(ground(*(pin[ok] + CALM_REACH * tan[ok]).T), float)
        bend[ok] = g[ok] - (a + b) / 2  # (IPR's own shape at the vertex: a lowered kerb, a driveway, a drain)
    e = s - g
    seg = np.hypot(*np.diff(np.vstack([xy, xy[:1]]), axis=0).T)
    L = seg.sum()
    d = np.r_[0, np.cumsum(seg)[:-1]]
    out = {}
    for k in range(n):
        if not np.isfinite(e[k]):
            continue
        rel = (d - d[k] + L / 2) % L - L / 2  # (signed distance along the ring, wrapped)
        cand = np.flatnonzero((np.abs(rel) <= WIDE) & (np.arange(n) != k) & np.isfinite(e))
        lo = cand[rel[cand] < 0][np.argsort(-rel[cand][rel[cand] < 0])]
        hi = cand[rel[cand] > 0][np.argsort(rel[cand][rel[cand] > 0])]
        if len(lo) < MIN_SIDE or len(hi) < MIN_SIDE:
            continue
        w = max(WIN, -rel[lo[MIN_SIDE - 1]], rel[hi[MIN_SIDE - 1]])
        idx = cand[np.abs(rel[cand]) <= w]
        near = e[idx][np.abs(e[idx]) <= AGREE]
        if len(near) < MIN_AGREE:
            continue
        o = float(np.median(near))
        if not OFF < abs(e[k] - o) <= MAX:
            continue
        if not abs(bend[k]) <= CALM:
            continue
        out[k] = g[k] + o
    return out


def correct(areas, ground, held=(), covers=None):
    """Correct the street outlines in place. ground: IPR at city-frame arrays (x, y); held: indexes of areas zps_ground
    holds off IPR; covers: a polygon (city frame) where IPR does not see the ground (OSM bridges,
    buildings, covered ways). Returns {"vertices": by class, "places": positions moved, "moved": [the largest moves]}."""
    decks = [shapely.Polygon(np.asarray(a["r"], float)[:, :2]).buffer(0) for a in areas
             if a["l"] >= 1 and a["c"] not in NOT_UNDER and len(a["r"]) >= 3]
    under = shapely.union_all(decks + ([covers] if covers is not None else [])) if decks or covers is not None else None
    held = set(held)
    new = {}  # (x, y, old z) -> [candidate heights]
    count = {}
    for i, a in enumerate(areas):
        if a["l"] != 0 or a["c"] not in STREETS or i in held or len(a["r"]) < 3:
            continue
        rings = [a["r"]] + [h for h in a.get("h", []) if len(h) >= 3]
        if any(q[2] is None for ring in rings for q in ring):
            continue
        arr = [np.asarray(ring, float) for ring in rings]
        try:
            poly = shapely.Polygon(arr[0][:, :2], [h[:, :2] for h in arr[1:]])
            if not poly.is_valid:
                poly = shapely.make_valid(poly)
        except (ValueError, shapely.errors.GEOSException):
            continue
        for r in arr:
            fx = ring_fixes(r, poly, ground)
            if not fx:
                continue
            ks = np.array(sorted(fx))
            if under is not None:
                ks = ks[~shapely.contains_xy(under, r[ks, 0], r[ks, 1])]
            for k in ks:
                new.setdefault((round(r[k, 0], 2), round(r[k, 1], 2), round(r[k, 2], 2)), []).append(fx[k])
                count[a["c"]] = count.get(a["c"], 0) + 1
    if not new:
        return {"vertices": {}, "places": 0, "moved": []}
    z_at = {(x, y): (z, float(np.mean(v))) for (x, y, z), v in new.items()}
    moved = []
    for a in areas:
        if a["l"] != 0:
            continue
        for ring in [a["r"]] + a.get("h", []):
            for q in ring:
                hit = z_at.get((q[0], q[1]))
                if hit and q[2] is not None and abs(q[2] - hit[0]) < 0.011:
                    q[2] = round(hit[1], 2)
    for (x, y), (z0, z1) in z_at.items():
        moved.append({"x": x, "y": y, "from": z0, "to": round(z1, 2)})
    moved.sort(key=lambda m: -abs(m["to"] - m["from"]))
    return {"vertices": dict(sorted(count.items())), "places": len(z_at), "moved": moved[:20]}
