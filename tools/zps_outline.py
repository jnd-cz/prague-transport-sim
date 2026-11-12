# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's street outlines where the survey and IPR's lidar disagree: a vertex the survey alone sets off takes the
lidar's height there (#470). Read by tools/dtm.py, before the kerbs.

The survey gives a street area's heights only on its outline, and they scatter along straight kerbs. Measured on the
five lines' data of 2026-11-12 (tools/bench/street_scatter.py): of straight outline, 1.8-2.7 % of road, 1.7-3.3 % of
tram and 4.0-5.1 % of sidewalk lies over 8 cm off its 21 m mean. IPR's 1 m raster read 1 m inside the area is no
better a source: against DI's rails the noise left in each is alike (median 1.5 cm, 90th percentile 5-10 cm); over
15 cm off their mean on straight road outline, 0.4-0.7 % of the samples are the survey's alone (IPR within 8 cm there),
as many IPR's alone and 0.1 % both; on paved areas IPR's alone are 11-17 % (yards, steps, walls by buildings). So
neither replaces the other (the user, 2026-11-12: "yes lets go with the consensus based on your measurements"):
- at each vertex of a road, tram or sidewalk outline at level 0, survey - IPR (IPR read INNER m inside the area) against
  its local offset: the median of survey - IPR over the vertices within WIN m along the outline (widened up to WIDE m to
  reach a vertex on each side and MIN_AGREE agreeing ones) that agree with IPR within AGREE;
- a vertex off that offset by more than OFF takes IPR's height plus the offset, where IPR has no shape of its own there
  (within CALM, or a quarter of the move, of its mean CALM_REACH m either side along the edge): a lone vertex off its
  kerb;
- vertices off by more than AGREE in a row are a run, moved whole or not at all (in part they became a sawtooth); a run
  beyond the offset's reach takes the offset of its two ends. Runs are another line's height: a road edge on a wall's
  top line (a sawtooth of 1.2 m by Jižní spojka on line 22), Náhorní's sidewalk 1.3-1.6 m low on line 17 (#315);
- one height per place: every level-0 vertex at the same position with the same old height takes it.
Kept as the survey has them: the classes where IPR scatters more than the survey (CLASSES), a platform's edge (KERB_TOPS),
vertices under a cover (the survey's upper levels, OSM's bridges, buildings and covered ways: IPR reads the cover or a
guess under it), areas held off IPR (zps_ground's verdicts), the shapes IPR sees too (lowered kerbs, driveways, ramps),
faces the survey drew (FACE: IPR's 1 m raster has no 20 cm step within a metre) and runs that cannot move whole.
On the five lines (2026-11-12) straight outline over 8 cm off its mean went from 1.8-2.7 to 1.4-1.7 % on roads, 1.7-3.3 to
0.7-2.5 % on tram areas and 4.0-5.1 to 3.1-4.0 % on sidewalks; vertices over 0.3 m off from 1,135-3,540 to 91-325 per
line.
"""
import numpy as np
import shapely

# the classes where IPR read 1 m inside scatters no more than the survey along straight outline (over 8 cm off the 21 m
# mean on the five lines, survey / IPR: road 1.8-2.7 / 1.6-2.3 %, tram 1.7-3.3 / 0.4-2.1 %, sidewalk 4.0-5.1 / 3.6-5.9 %).
# Not parking (1.5-4.3 / 4.5-9.6 %), cycle, island, platform (small or narrow: IPR inside reads their edges; with them
# the rule raised the platforms' share on line 37 from 0.95 to 5.3 %) and paved (6-11 / 22-33 %)
CLASSES = {"road", "tram", "sidewalk"}
# m along the outline either side for the local offset, widened up to WIDE until it holds a vertex on each side (79 % of
# straight street outline lies in gaps over 5 m between vertices, line 22) and MIN_AGREE vertices agreeing with IPR
WIN, WIDE = 10.0, 30.0
MIN_AGREE = 2  # vertices agreeing with IPR in the window, for its offset
OFF = 0.08  # m: survey - IPR at a vertex this far off its local offset (lint streetWaviness' threshold) ...
CALM = 0.04  # m: ... while IPR at the vertex stays within this of its mean CALM_REACH m either side along the edge
CALM_REACH = 2.0  # (a line fitted over the window instead read a street's crest or sag: 0.45 m over 30 m at R 1000 m)
MAX = 2.0  # m: a larger move is another level, not an error of this one
# m: the vertices whose survey - IPR lies within this give the local offset (survey - IPR at straight road outline: 5th /
# 95th percentile -0.26 / +0.30 m on the five lines; with every vertex voting, the run by Jižní spojka outnumbered its
# neighbours and pulled them up)
AGREE = 0.30
# m inside the area where IPR is read: on straight road outline IPR's share over 8 cm off its mean is 2.0-3.0 % at 0.5 m
# (the raster rounds the kerb), 1.6-2.3 % at 1 m, 1.3-2.0 % at 1.5 m (narrow sidewalks have no 1.5 m)
INNER = 1.0
KERB_TOPS = {"platform"}  # areas whose shared edge is their top (above)
HELD = {"survey", "review", "changing", "covered"}  # zps_ground's verdicts that keep an area off IPR
# m: a vertex this near its neighbour on the ring and more than OFF off its height is a face the survey drew (a kerb
# corner at a crossing: line 22, three vertices within 0.3 m at -0.24 / -0.24 / +0.22 m off IPR): kept
FACE = 0.5
SIZES = (0.15, 0.30, 1.0, MAX)  # the report's classes of moves (m)


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


def ring_fixes(r, poly, ground, skip=None, covered=None):
    """{vertex index: new height} for one closed ring (n, 3) (no closing point) of an area (its polygon `poly`).
    ground: IPR at arrays (x, y) in the ring's frame; skip: a boolean per vertex left out, neither moved nor in the
    offset; covered: a boolean per vertex IPR does not see (it stays, and so does its run)."""
    n = len(r)
    if n < 3:
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
    if skip is not None:
        e[skip] = np.nan
    seg = np.hypot(*np.diff(np.vstack([xy, xy[:1]]), axis=0).T)
    L = seg.sum()
    d = np.r_[0, np.cumsum(seg)[:-1]]
    face = np.zeros(n, bool)
    for j in (-1, 1):
        nb = np.roll(np.arange(n), -j)
        face |= (np.hypot(*(xy[nb] - xy).T) < FACE) & (np.abs(s[nb] - s) > OFF)
    off = np.zeros(n, bool)  # (off the local offset, or far off IPR with no offset in reach)
    far = np.zeros(n, bool)  # (off by more than AGREE: what makes a run)
    new = np.full(n, np.nan)
    for k in range(n):
        if not np.isfinite(e[k]):
            continue
        rel = (d - d[k] + L / 2) % L - L / 2  # (signed distance along the ring, wrapped)
        cand = np.flatnonzero((np.abs(rel) <= WIDE) & (np.arange(n) != k) & np.isfinite(e))
        lo, hi = rel[cand][rel[cand] < 0], rel[cand][rel[cand] > 0]
        ag = cand[np.abs(e[cand]) <= AGREE]
        ag = ag[np.argsort(np.abs(rel[ag]))]
        if not len(lo) or not len(hi) or len(ag) < MIN_AGREE:
            off[k] = far[k] = abs(e[k]) > AGREE
            continue
        w = max(WIN, -lo.max(), hi.min())
        # (the agreeing vertices within w, or the MIN_AGREE nearest within WIDE: a run longer than the window)
        o = float(np.median(e[ag[(np.abs(rel[ag]) <= w) | (np.arange(len(ag)) < MIN_AGREE)]]))
        if abs(e[k] - o) > OFF:
            off[k], far[k] = True, abs(e[k] - o) > AGREE
            new[k] = g[k] + o
    # a run (the vertices far off in a row along the ring) moves whole or not at all: moved in part, a stretch 1-3 m off
    # IPR became a sawtooth on line 22 (at -4224, 80 and 1892, -1931). A vertex off by less (a kerb's scatter) is one of
    # its own: left, it makes no jump; joined to a run, one beside Náhorní's held the run back.
    out = {}
    if far.all():
        return out
    still = ~far & np.isfinite(e)  # (a run's ends: their own offset, scatter or not)
    k0 = int(np.flatnonzero(~far)[0])
    run = []
    for j in range(1, n + 1):
        k = (k0 + j) % n
        if far[k]:
            run.append(k)
            continue
        units = [run] if run else []
        if off[k]:
            units.append([k])
        for run in units:
            z = new[run]
            a, b = (run[0] - 1) % n, (run[-1] + 1) % n  # (the vertices either side of the run)
            if not np.isfinite(z).all() and still[a] and still[b]:
                # a run longer than the offset's reach (Náhorní on line 17: 18 of a sidewalk's 30 vertices 1.3-1.6 m
                # under IPR): the offset from its two ends, along the ring between them
                t = np.array([(d[i] - d[a]) % L for i in run]) / max((d[b] - d[a]) % L, 1e-9)
                z = g[run] + e[a] + (e[b] - e[a]) * t
            dz = np.abs(z - s[run])
            # (IPR's own shape blocks a move only where it is a fair part of it: CALM, or a quarter of the move)
            ok = (np.isfinite(z) & ~face[run] & (np.abs(bend[run]) <= np.maximum(CALM, dz / 4)) & (dz <= MAX)
                  & (True if covered is None else ~covered[run]))
            if ok.all():
                out.update({i: float(v) for i, v in zip(run, z)})
        run = []
    return out


def correct(areas, ground, held=(), covers=None):
    """Correct the street outlines in place. ground: IPR at city-frame arrays (x, y); held: indexes of the areas
    zps_ground keeps off IPR; covers: a polygon (city frame) under which IPR does not see the ground
    (zps_ground.cover_union). Returns {"vertices": moved per class, "places": positions moved, "sizes": places per
    size of the move, "moved": the largest moves}."""
    held = set(held)
    # a platform's edge: the survey's line is its top on the carriageway's side (line 17: +0.17 m over the road), and the
    # kerbs measure each platform's step from it (tools/kerbs.py); taken into a tram area's offset beside its foot-level
    # vertices it split the edge on line 37 (part pulled to the floor, part raised by the step: platforms over 8 cm off
    # their mean 0.95 -> 4.55 %)
    edge = {(q[0], q[1]) for a in areas if a["l"] == 0 and a["c"] in KERB_TOPS for ring in [a["r"]] + a.get("h", [])
            for q in ring}
    new = {}  # (x, y, old z) -> [candidate heights]
    count = {}
    for i, a in enumerate(areas):
        if a["l"] != 0 or a["c"] not in CLASSES or i in held or len(a["r"]) < 3:
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
            under = (shapely.contains_xy(covers, r[:, 0], r[:, 1]) if covers is not None and not covers.is_empty
                     else None)
            fx = ring_fixes(r, poly, ground, np.array([(q[0], q[1]) in edge for q in r.tolist()]), under)
            for k in sorted(fx):
                new.setdefault((round(float(r[k, 0]), 2), round(float(r[k, 1]), 2), round(float(r[k, 2]), 2)), []).append(fx[k])
                count[a["c"]] = count.get(a["c"], 0) + 1
    z_at = {(x, y): (z, round(float(np.mean(v)), 2)) for (x, y, z), v in new.items()}
    for a in areas:
        if a["l"] != 0:
            continue
        for ring in [a["r"]] + a.get("h", []):
            for q in ring:
                hit = z_at.get((q[0], q[1]))
                if hit and q[2] is not None and abs(q[2] - hit[0]) < 0.011:
                    q[2] = hit[1]
    moves = sorted(({"x": x, "y": y, "from": z0, "to": z1} for (x, y), (z0, z1) in z_at.items()),
                   key=lambda m: -abs(m["to"] - m["from"]))
    sizes = {f"<={s}": 0 for s in SIZES}
    for m in moves:
        sizes[f"<={next(s for s in SIZES if abs(m['to'] - m['from']) <= s + 1e-9)}"] += 1
    return {"vertices": dict(sorted(count.items())), "places": len(z_at), "sizes": sizes, "moved": moves[:20]}
