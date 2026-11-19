# SPDX-License-Identifier: AGPL-3.0-or-later
"""Walls the survey has as lines, with the ground's level on either side (#697).

    python -X utf8 -P -E tools/wall_lines.py [--lines 9,17,22,23,37]     # the table: what the survey's wall lines hold

The technical map's `Zeď` lines (data/lineN.zps.json, tools/zps_source.py: a wall too thin to be an area, with its
points' heights) are where a wall stands, to the survey's centimetres. A survey wall *area* (data/lineN.dtm.json class
wall) lies under 2-5 % of them; the rest the ground knew nothing of, and where the ground steps across one (a quay, a
retaining wall, a walled ramp) IPR's 1 m raster spreads the step over 2 m and the ground file drew a slope: Rašínovo
nábřeží, line 17 (-743, -1421), 8 m.

stretches(ln): the runs of those lines across which the ground steps, each a polyline with the level to its left and
to its right at every point:
- the level on a side is IPR's raster SIDE m off the line (past the raster's smear of the step), or the line's own
  surveyed height where that is within OWN of it (the survey's point is the better reading of the side it was taken
  on: about a third of the stepped length has it at the foot, a third at the top);
- a point is on a stretch where the two sides differ by STEP or more; a stretch runs at least MIN_LEN, gaps up to GAP
  closed; the levels smoothed along it over SMOOTH points.
"""
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

KIND = "Zeď"
SPACING = 1.0  # m between a line's samples
SIDE = 1.5  # m off the line: where IPR's raster is read for a side's level (its smear of a step: street_profile SW_KERB_SMEAR)
REACH = 2.5  # m off the line: the farthest reading of a side
OWN = 0.5  # m: the line's own height this near a side's raster level is that side's level
STEP = 0.7  # m: the ground steps across the line by this or more (a kerb and a garden's edge are under it)
MIN_LEN = 2.0  # m: a shorter run is no stretch
GAP = 2.0  # m: a shorter gap between two runs is closed
SMOOTH = 9  # samples: the running median along a stretch


def _median(v, n=SMOOTH):
    if len(v) < 3:
        return v
    h = n // 2
    pad = np.concatenate([np.full(h, v[0]), v, np.full(h, v[-1])])
    return np.median(np.lib.stride_tricks.sliding_window_view(pad, n), axis=1)


def sample(p, spacing=SPACING):
    """A polyline's points (n, 3; z may be NaN) every `spacing` m and at its vertices: (x, y, z, the unit normal to the
    left (nx, ny))."""
    out = []
    for a, b in zip(p, p[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        k = max(1, int(math.ceil(L / spacing)))
        t = np.arange(k) / k
        n = np.array([-(b[1] - a[1]) / L, (b[0] - a[0]) / L])
        out.append(np.column_stack([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t,
                                    np.full(k, n[0]), np.full(k, n[1])]))
    if not out:
        return np.zeros((0, 5))
    last = np.array([[p[-1][0], p[-1][1], p[-1][2], out[-1][-1, 3], out[-1][-1, 4]]])
    return np.vstack(out + [last])


def levels(S, lidar):
    """The level to the left and to the right of sampled points S (sample()), lidar(x, y) IPR's raster. Read at SIDE and
    up to REACH off the line: the raster's smear pulls the high side down and the low side up, so the high side takes
    the highest of its readings and the low side the lowest (at SIDE alone the quay's top read 194.2-197.1 m along 130 m
    of a level sidewalk)."""
    off = np.arange(SIDE, REACH + 1e-9, 0.5)
    L = np.stack([lidar(S[:, 0] + S[:, 3] * o, S[:, 1] + S[:, 4] * o) for o in off])
    R = np.stack([lidar(S[:, 0] - S[:, 3] * o, S[:, 1] - S[:, 4] * o) for o in off])
    with np.errstate(all="ignore"):
        left_high = np.nanmedian(L, 0) >= np.nanmedian(R, 0)
        zl = np.where(left_high, np.nanmax(L, 0), np.nanmin(L, 0))
        zr = np.where(left_high, np.nanmin(R, 0), np.nanmax(R, 0))
    z = S[:, 2]
    # (the line's own height is the side's it lies nearer, within OWN)
    dl, dr = np.abs(z - zl), np.abs(z - zr)
    own_l = np.isfinite(z) & (dl <= OWN) & (dl <= dr)
    own_r = np.isfinite(z) & (dr <= OWN) & (dr < dl)
    return np.where(own_l, z, zl), np.where(own_r, z, zr)


def runs(on, d):
    """[(i, j)]: the runs of `on` along distances d, gaps up to GAP closed, at least MIN_LEN long."""
    idx = np.flatnonzero(on)
    if not len(idx):
        return []
    out, a, b = [], idx[0], idx[0]
    for i in idx[1:]:
        if d[i] - d[b] <= GAP + 1e-9:
            b = i
        else:
            out.append((a, b))
            a = b = i
    out.append((a, b))
    return [(a, b) for a, b in out if d[b] - d[a] >= MIN_LEN]


def of_lines(lines, lidar):
    """The stretches of polylines ([(n, 3) arrays]): [{"p": (m, 2), "zl": (m,), "zr": (m,)}]."""
    out = []
    for p in lines:
        S = sample(np.asarray(p, float))
        if len(S) < 2:
            continue
        zl, zr = levels(S, lidar)
        d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(S[:, 0]), np.diff(S[:, 1])))])
        for a, b in runs(np.abs(zl - zr) >= STEP, d):
            out.append({"p": S[a:b + 1, :2].copy(), "zl": _median(zl[a:b + 1]), "zr": _median(zr[a:b + 1])})
    return out


def source_lines(ln, root=ROOT, box=None):
    """The survey's level-0 wall lines of line ln ([(n, 3)]), those reaching a box (x0, y0, x1, y1) where one is given."""
    path = os.path.join(root, "data", f"line{ln}.zps.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if KIND not in d["kinds"]:
        return []
    k = d["kinds"].index(KIND)
    out = []
    for r in d["lines"]:
        if r[0] != k or r[1] != 0:
            continue
        p = np.array([[v if v is not None else np.nan for v in r[i:i + 3]] for i in range(3, len(r), 3)], float)
        if len(p) < 2:
            continue
        if box is not None and (p[:, 0].max() < box[0] or p[:, 0].min() > box[2] or p[:, 1].max() < box[1] or p[:, 1].min() > box[3]):
            continue
        out.append(p)
    return out


def ipr_lidar():
    from geo import Frame
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    return lambda x, y: np.asarray(ipr.sample(np.asarray(x) + F.E0, np.asarray(y) + F.N0), float)


def stretches(ln, root=ROOT, box=None, lidar=None):
    """The stepped stretches of line ln's wall lines (of_lines), those reaching a box where one is given (with SIDE's
    margin: a stretch is found from its own line alone, so a box's build finds what the line's build does)."""
    if box is not None:
        box = (box[0] - SIDE, box[1] - SIDE, box[2] + SIDE, box[3] + SIDE)
    return of_lines(source_lines(ln, root, box), lidar or ipr_lidar())


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    a = ap.parse_args(argv)
    lidar = ipr_lidar()
    print("| line | wall lines, km | stretches | their km | by step: 0.7-1 / 1-2 / 2-4 / over 4 m, km |")
    print("|---|---|---|---|---|")
    for ln in a.lines.split(","):
        src = source_lines(ln)
        km = sum(float(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])).sum()) for p in src) / 1000
        st = of_lines(src, lidar)
        seg = [(np.hypot(np.diff(s["p"][:, 0]), np.diff(s["p"][:, 1])), np.abs(s["zl"] - s["zr"])) for s in st]
        L = np.concatenate([q[0] for q in seg]) if seg else np.zeros(0)
        H = np.concatenate([(q[1][:-1] + q[1][1:]) / 2 for q in seg]) if seg else np.zeros(0)
        bands = [float(L[(H >= lo) & (H < hi)].sum()) / 1000 for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 1e9))]
        print(f"| {ln} | {km:.2f} | {len(st)} | {L.sum() / 1000:.2f} | " + " / ".join(f"{b:.2f}" for b in bands) + " |")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
