# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street's corners at the survey's walls and stairs, against their own street (#653).

    python -P -E tools/bench/street_at_walls.py [--lines 9,17,22,23,37] [--ground DIR] [--box X0,Y0,X1,Y1] [--list N] [--json OUT]

A ground file's corners of the street (triangles whose survey class is road, sidewalk or tram) on a level-0 wall's or
stairs' outline (within ON), each against its own street area: an area of a street class whose outline passes through
the corner. Measured IN into that area, square to the wall's or stairs' edge on the area's side: the ground there. Of
the corner's heights (an upright face holds several at one point) the nearest to it. A corner OFF or more off that
ground, and OFF or more off its own area's outline height there too, is a step or a wedge in the street.

Why not the outline's height alone (the issue's first count): a wall's outline carries its top along the foot too, and
so does the street's own outline where it runs along the top's line: by Hořejší nábřeží, line 9 (-1029, -533), the
street lies at the wall's foot, 187.5 m, and both outlines say 193.8 m. A street rightly at the foot counted as off,
and the count did not fall with batch D. Why the own outline too: where a ramp climbs along a wall from its end, the
corner at the end has the survey's height and the ramp 0.5 m in is higher already: Krejcárek's sidewalk 284 at wall
1442's foot, line 37 (3926.76, 327.18), 228.56 m in both outlines, its ramp 0.5 m in at 229.7 m.

What it cannot see: a step that a street's own outline heights make between its corners. A corner at its own outline's
height counts as right, and a street's outline along a wall mixes the foot's heights and the top's: a rule that set
such corners to their outline's height took the count at two places from 20 and 13 to 0 while the sections along those
roads grew worse (#653, not taken). A rule is judged on places' sections too (tools/ground_place.py).

Batch E's ground (main 9c98999), the five lines: 4,940-16,406 corners on such outlines, 32-345 off (#653).
--ground: the folder of the ground file (a place's overlay/data, tools/ground_place.py --overlay); --box: only the
corners in a box. Exit 0.
"""
import argparse
import collections
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

STREET = ("road", "sidewalk", "tram")  # the classes measured
ON = 0.05  # m: a corner this near an outline lies on it
IN = 0.5  # m into the street area: its ground there
OFF = 0.3  # m: a corner this far off both is a step or a wedge


def edges(areas, classes):
    """The outline edges ((n, 2, 3), with heights) of survey areas [(index, area)] of `classes`, and each one's area."""
    import ground_mesh as gm
    segs, ids = [], []
    for i, a in areas:
        if a["c"] in classes:
            s = gm.ring_segments(a)
            if len(s):
                segs.append(s)
                ids += [i] * len(s)
    return (np.concatenate(segs), np.asarray(ids)) if segs else (np.zeros((0, 2, 3)), np.zeros(0, int))


def at_edges(segs, x, y, d=ON):
    """(point index, edge index, the edge's height there) for the edges within d of points (x, y)."""
    import shapely
    if not len(segs) or not len(x):
        return np.zeros(0, int), np.zeros(0, int), np.zeros(0)
    pi, si = shapely.STRtree(shapely.linestrings(segs[:, :, :2])).query(shapely.points(x, y), predicate="dwithin", distance=d)
    e = segs[si, 1, :2] - segs[si, 0, :2]
    t = np.clip(((np.column_stack([x[pi], y[pi]]) - segs[si, 0, :2]) * e).sum(1) / np.maximum((e * e).sum(1), 1e-12), 0, 1)
    return pi, si, segs[si, 0, 2] + (segs[si, 1, 2] - segs[si, 0, 2]) * t


def measure(D, V, F, P, box=None):
    """The street corners P ((n, 3), m) on D's level-0 walls' and stairs' outlines against their own street: rows
    {at, z, area, ground in, off, edge of, stairs}, one per corner position and street area, `off` 0 where the corner
    is at its area's outline height; and how many positions lie on such an outline. V (mm) and F: the street's
    triangles, for the ground in."""
    import ground_mesh as gm
    import shapely
    if box is not None:
        P = P[(P[:, 0] >= box[0]) & (P[:, 0] <= box[2]) & (P[:, 1] >= box[1]) & (P[:, 1] <= box[3])]
    lvl0 = [(i, a) for i, a in enumerate(D["areas"]) if a.get("l", 0) == 0 and len(a.get("r") or []) >= 3]
    W, wid = edges(lvl0, gm.WALL_CLASSES)
    S, sid = edges(lvl0, STREET)
    if not len(P) or not len(W) or not len(S):
        return [], 0
    poly = {}
    for i, a in lvl0:
        if a["c"] in STREET:
            g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
            poly[i] = g if g.is_valid else g.buffer(0)
    # (each corner's nearest wall or stairs edge, and the street areas whose outline passes through it)
    pw, wi, _ = at_edges(W, P[:, 0], P[:, 1])
    d = shapely.distance(shapely.points(P[pw, 0], P[pw, 1]), shapely.linestrings(W[wi, :, :2]))
    o = np.lexsort((d, pw))
    keep = np.r_[True, pw[o][1:] != pw[o][:-1]] if len(o) else np.zeros(0, bool)
    pw, wi = pw[o][keep], wi[o][keep]
    ps, si, _ = at_edges(S, P[pw, 0], P[pw, 1])
    pairs = sorted(set(zip(pw[ps].tolist(), wi[ps].tolist(), sid[si].tolist())))
    if not pairs:
        return [], len(pw)
    pp, ww, aa = (np.array(v) for v in zip(*pairs))
    e = W[ww, 1, :2] - W[ww, 0, :2]
    n = np.column_stack([-e[:, 1], e[:, 0]]) / np.maximum(np.hypot(e[:, 0], e[:, 1]), 1e-9)[:, None]
    key = np.round(P[:, 0] * 1000).astype(np.int64) * 10_000_000_000 + np.round(P[:, 1] * 1000).astype(np.int64)
    _, inv = np.unique(key, return_inverse=True)
    inv = inv.ravel()
    heights = collections.defaultdict(list)
    for i, g in enumerate(inv.tolist()):
        heights[g].append(P[i, 2])

    def nearest(p, z0):
        return min(abs(z - z0) for z in heights[inv[p]])
    # (into the area on each side of the edge it lies on: an area on both sides of a wall standing in it, two levels
    # of one sidewalk, is read on the side nearer the corner; by Modřany's wall 7821, line 17 (-2455, -8516), the low
    # side's corners were read against the high side's ground, 1.9 m)
    off, zin = np.full(len(pp), np.nan), np.full(len(pp), np.nan)
    for s in (1.0, -1.0):
        c = P[pp, :2] + s * n * IN
        hit = np.array([shapely.contains_xy(poly[a], x, y) for a, (x, y) in zip(aa.tolist(), c.tolist())], bool)
        z = np.full(len(pp), np.nan)
        if hit.any():
            z[hit] = gm.mesh_at(V, F, c[hit, 0], c[hit, 1])
        d = np.array([nearest(p, zi) if np.isfinite(zi) else np.nan for p, zi in zip(pp.tolist(), z.tolist())])
        better = np.isfinite(d) & ~(d >= off)
        off[better], zin[better] = d[better], z[better]
    # (at its own area's outline height there: no defect)
    qs, qi, zo = at_edges(S, P[pp, 0], P[pp, 1])
    mine = sid[qi] == aa[qs]
    own = np.full(len(pp), np.inf)
    for j, z0 in zip(qs[mine].tolist(), zo[mine].tolist()):
        own[j] = min(own[j], nearest(pp[j], z0))
    off = np.where(own <= OFF, 0.0, off)
    rows = {}
    for p, a, w, z, zi in zip(pp.tolist(), aa.tolist(), ww.tolist(), off.tolist(), zin.tolist()):
        k = (int(inv[p]), a)
        if np.isfinite(z) and (k not in rows or z < rows[k]["off"]):
            rows[k] = {"at": [round(float(P[p, 0]), 2), round(float(P[p, 1]), 2)], "z": round(float(P[p, 2]), 2), "area": int(a),
                       "ground in": round(float(zi), 2), "off": round(float(z), 2), "edge of": int(wid[w]),
                       "stairs": D["areas"][int(wid[w])]["c"] == "stairs"}
    return list(rows.values()), len(set(pw.tolist()))


def street_corners(meta, blob):
    """A ground file's street corners (n, 3) in m, and its street triangles (V in mm, F)."""
    import ground_mesh as gm
    V, by, area = (lambda g: (np.asarray(g[0], float), g[1], g[-1]))(gm.decode(blob, meta, area=True))
    tris = []
    for c, f in by.items():
        names = np.asarray(area.get(c, []), dtype=object)
        if len(f) and len(names) == len(f):
            tris.append(f[np.isin(names, list(STREET))])
    F = np.concatenate(tris) if tris else np.zeros((0, 3), int)
    return np.unique(V[F].reshape(-1, 3), axis=0), np.round(V * gm.Q).astype(np.int64), F


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--ground", help="the ground file's folder (default data/)")
    ap.add_argument("--box", help="X0,Y0,X1,Y1: only the corners in it")
    ap.add_argument("--list", type=int, default=0, help="the worst N places per line, by 4 m cells")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    box = [float(v) for v in a.box.split(",")] if a.box else None
    out = {}
    print(f"| line | street corners on a wall's or stairs' outline | off their own street {IN} m in by over {OFF} m | at stairs / walls | p99, max m |")
    print("|---|---|---|---|---|")
    for ln in a.lines.split(","):
        with open(os.path.join(ROOT, "data", f"line{ln}.dtm.json"), encoding="utf-8") as f:
            D = json.load(f)
        g = a.ground or os.path.join(ROOT, "data")
        with open(os.path.join(g, f"line{ln}.ground.json"), encoding="utf-8") as f:
            meta = json.load(f)
        with open(os.path.join(g, f"line{ln}.ground.bin"), "rb") as f:
            P, V, F = street_corners(meta, f.read())
        rows, n = measure(D, V, F, P, box)
        offs = np.array([r["off"] for r in rows]) if rows else np.zeros(1)
        bad = [r for r in rows if r["off"] > OFF]
        st = sum(r["stairs"] for r in bad)
        print(f"| {ln} | {n:,} | {len(bad):,} | {st:,} / {len(bad) - st:,} | {np.percentile(offs, 99):.2f}, {offs.max():.2f} |", flush=True)
        out[ln] = bad
        if a.list:
            cells = collections.defaultdict(list)
            for r in bad:
                cells[(int(r["at"][0] // 4), int(r["at"][1] // 4))].append(r)
            for v in sorted(cells.values(), key=lambda v: -len(v) * max(x["off"] for x in v))[:a.list]:
                w = max(v, key=lambda x: x["off"])
                print(f"    line {ln} ({w['at'][0]:.1f}, {w['at'][1]:.1f}) z {w['z']:.2f}: {len(v)} corners up to {w['off']:.2f} m off "
                      f"area {w['area']} ({D['areas'][w['area']]['c']}) {IN} m in ({w['ground in']:.2f}), "
                      f"at {'stairs' if w['stairs'] else 'wall'} {w['edge of']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
