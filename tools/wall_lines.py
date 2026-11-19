# SPDX-License-Identifier: AGPL-3.0-or-later
"""Walls the survey has as lines, with the ground's level on either side (#697).

    python -X utf8 -P -E tools/wall_lines.py [--lines 9,17,22,23,37]     # the table: what the survey's wall lines hold

The technical map's `Zeď` lines (data/lineN.zps.json, tools/zps_source.py: a wall too thin to be an area, with its
points' heights; at level 0 and on structures, a walled ramp's sides being level 1) are where a wall stands, to the
survey's centimetres. A survey wall *area* (data/lineN.dtm.json class
wall) lies under 2-5 % of them; the rest the ground knew nothing of, and where the ground steps across one (a quay, a
retaining wall, a walled ramp) IPR's 1 m raster spreads the step over 2 m and the ground file drew a slope: Rašínovo
nábřeží, line 17 (-743, -1421), 8 m.

stretches(ln): the runs of those lines across which the ground steps, each a polyline with the level to its left and
to its right at every point:
- a side's ground is IPR's raster read FIT m off the line, past the raster's smear of the step, as a straight line
  across: its level at the wall and its slope away from it (`zl`, `gl`; `zr`, `gr`). A level sidewalk gives its
  level; a bank rising behind a low wall gives the bank's foot at the wall, not the bank's height 2 m up it (the
  highest reading made a 1 m wall under Chotkova's lawn 4-7 m, line 23 (-887, 721));
- the line's own surveyed height is a side's level where it is within OWN of it (the survey's point is the better
  reading of the side it was taken on: about a third of the stepped length has it at the foot, a third at the top);
- a side is read up to the next wall only: its readings stop CLEAR short of the first other wall line (or survey wall
  area's outline) across it. Where none is left (terraces narrower than the raster's smear: under Chotkova, line 23
  (-896, 720), three walls of 3 m stand 1.2-2.7 m apart and the raster is one slope through them), the strip's level
  is a surveyed height: this line's own or the facing line's, the nearer to the raster at the strip's middle; a strip
  under PAIR wide lies at the lower of the two: either a wall's top between its two faces, both at one height, or a
  wall's face between its foot's line and its top's (the same walls: the two lines 0.15 m apart, 208.6 and 211.6 m),
  and then the wall stands at the higher line;
- a point is on a stretch where the two sides' levels at the wall differ by STEP or more; a stretch runs at least
  MIN_LEN, gaps up to GAP closed; levels and slopes smoothed along it over SMOOTH points.
"""
import json
import math
import os
import sys
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

KIND = "Zeď"
SPACING = 1.0  # m between a line's samples
FIT = (2.5, 3.0, 3.5, 4.0)  # m off the line: where IPR's raster is read for a side (its smear of the quay's 8 m reaches 2 m)
SLOPE = 1.5  # rise over run: a side's slope is held to this (a reading on another wall or a tree's foot tilts the fit)
FLAT = 0.15  # rise over run: a side sloping less is level (a sidewalk's crossfall is 2 %, a kerb in the readings 10 %)
CLEAR = 0.3  # m: a side's readings stop this short of the next wall line across it
PAIR = 1.0  # m: two wall lines nearer than this are one wall's (its two faces, or its face's foot and top)
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


def _cross(P, Q, A, B):
    """Per ray P->Q (n, 2) the parameter t in (0, 1] of its first crossing with segments A->B (m, 2) and the crossed
    segment's index and parameter there: (t (inf where none), index, u)."""
    import shapely
    t = np.full(len(P), np.inf)
    seg = np.full(len(P), -1)
    us = np.zeros(len(P))
    if not len(A) or not len(P):
        return t, seg, us
    tree = shapely.STRtree(shapely.linestrings(np.stack([A, B], 1)))
    ri, si = tree.query(shapely.linestrings(np.stack([P, Q], 1)), predicate="intersects")
    if not len(ri):
        return t, seg, us
    r, e, w = Q[ri] - P[ri], B[si] - A[si], A[si] - P[ri]
    den = r[:, 0] * e[:, 1] - r[:, 1] * e[:, 0]
    with np.errstate(all="ignore"):
        tt = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
        uu = (w[:, 0] * r[:, 1] - w[:, 1] * r[:, 0]) / den
    ok = (np.abs(den) > 1e-12) & (tt > 0) & (tt <= 1) & (uu >= -1e-9) & (uu <= 1 + 1e-9)
    ri, si, tt, uu = ri[ok], si[ok], tt[ok], uu[ok]
    order = np.lexsort((tt, ri))
    first = np.concatenate([[True], ri[order][1:] != ri[order][:-1]]) if len(order) else np.zeros(0, bool)
    k = order[first]
    t[ri[k]], seg[ri[k]], us[ri[k]] = tt[k], si[k], np.clip(uu[k], 0, 1)
    return t, seg, us


def _next_wall(S, sign, walls):
    """Along each sampled point's normal on one side: (the distance to the first wall segment across it, inf where none
    within the readings' reach; that segment's height there, NaN where it has none). walls: (A, B) (m, 3) segments."""
    n = len(S)
    if walls is None or not len(walls[0]):
        return np.full(n, np.inf), np.full(n, np.nan)
    A, B = walls
    far = FIT[-1] + CLEAR
    nrm = sign * S[:, 3:5]
    P = S[:, :2] + nrm * 0.05  # (off the line itself: its own segments start no crossing)
    Q = S[:, :2] + nrm * far
    t, seg, u = _cross(P, Q, A[:, :2], B[:, :2])
    hit = seg >= 0
    reach = np.where(hit, 0.05 + t * (far - 0.05), np.inf)
    z = np.full(n, np.nan)
    z[hit] = A[seg[hit], 2] + (B[seg[hit], 2] - A[seg[hit], 2]) * u[hit]
    return reach, z


def _side(S, lidar, sign, walls=None):
    """(the level at the line, the slope away from it, whether a survey height gave it) of the ground on one side of
    sampled points: the least-squares line through IPR's readings FIT m off, up to the next wall, where the ground slopes
    by FLAT or more; where it does not, the readings' median and no slope (a line through a sidewalk, its kerb and the
    road beyond falls a little, and carried back to the wall it raised the sidewalk against the Modřany ramp's wall by
    half a metre, line 17 (-2385, -9250)). Where the next wall leaves no reading: the strip's surveyed height (see the
    module's text)."""
    d = np.asarray(FIT, float)
    reach, zhit = _next_wall(S, sign, walls)
    Z = np.stack([lidar(S[:, 0] + sign * S[:, 3] * o, S[:, 1] + sign * S[:, 4] * o) for o in d])
    ok = np.isfinite(Z) & (d[:, None] < reach[None, :] - CLEAR)
    n = ok.sum(0)
    with np.errstate(all="ignore"):
        dm = np.where(ok, d[:, None], 0).sum(0) / n
        zm = np.where(ok, Z, 0).sum(0) / n
        dd = np.where(ok, d[:, None] - dm, 0)
        g = (dd * np.where(ok, Z - zm, 0)).sum(0) / (dd ** 2).sum(0)
    with warnings.catch_warnings():  # (a side with no reading: NaN, said once per call otherwise)
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(np.where(ok, Z, np.nan), 0)
    g = np.clip(np.where(n >= 3, g, 0.0), -SLOPE, SLOPE)
    flat = np.abs(g) < FLAT
    g = np.where(flat, 0.0, g)
    lvl = np.where(n >= 1, np.where(flat, med, zm - g * dm), np.nan)
    # (the next wall nearer than the readings: a strip between two walls)
    strip = (n == 0) & np.isfinite(reach)
    surveyed = np.zeros(len(S), bool)
    if strip.any():
        i = np.flatnonzero(strip)
        own, other = S[i, 2], zhit[i]
        mid = np.asarray(lidar(S[i, 0] + sign * S[i, 3] * reach[i] / 2, S[i, 1] + sign * S[i, 4] * reach[i] / 2), float)
        with np.errstate(all="ignore"):
            pick_other = np.isfinite(other) & (~np.isfinite(own) | (np.abs(other - mid) < np.abs(own - mid)))
        z = np.where(pick_other, other, own)
        z = np.where(reach[i] < PAIR, np.fmin(own, other), z)
        surveyed[i] = np.isfinite(z)
        lvl[i] = np.where(np.isfinite(z), z, mid)
        g[i] = 0.0
    return lvl, g, surveyed


def levels(S, lidar, walls=None):
    """The ground to the left and to the right of sampled points S (sample()), lidar(x, y) IPR's raster, walls the
    segments ((A, B), each (m, 3)) a side's readings stop at: (zl, gl, zr, gr), each side's level at the line and its
    slope away from it (see the module's text)."""
    (zl, gl, sl), (zr, gr, sr) = _side(S, lidar, 1.0, walls), _side(S, lidar, -1.0, walls)
    z = S[:, 2]
    # (the line's own height is the side's it lies nearer, within OWN; a strip's level is a surveyed height already)
    dl, dr = np.abs(z - zl), np.abs(z - zr)
    own_l = np.isfinite(z) & (dl <= OWN) & (dl <= dr) & ~sl
    own_r = np.isfinite(z) & (dr <= OWN) & (dr < dl) & ~sr
    return np.where(own_l, z, zl), gl, np.where(own_r, z, zr), gr


def segments(lines):
    """Polylines ([(n, 3)]) as segments (A, B), each (m, 3)."""
    if not len(lines):
        return np.zeros((0, 3)), np.zeros((0, 3))
    return (np.concatenate([np.asarray(p, float)[:-1] for p in lines]), np.concatenate([np.asarray(p, float)[1:] for p in lines]))


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


def of_lines(lines, lidar, others=()):
    """The stretches of polylines ([(n, 3) arrays]): [{"p": (m, 2), "zl", "gl", "zr", "gr": (m,)}]. others: more lines
    a side's readings stop at (the survey's wall areas' outlines)."""
    out = []
    walls = segments(list(lines) + list(others))
    for p in lines:
        S = sample(np.asarray(p, float))
        if len(S) < 2:
            continue
        zl, gl, zr, gr = levels(S, lidar, walls)
        d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(S[:, 0]), np.diff(S[:, 1])))])
        for a, b in runs(np.abs(zl - zr) >= STEP, d):
            out.append({"p": S[a:b + 1, :2].copy(), "zl": _median(zl[a:b + 1]), "gl": _median(gl[a:b + 1]),
                        "zr": _median(zr[a:b + 1]), "gr": _median(gr[a:b + 1])})
    return out


def source_lines(ln, root=ROOT, box=None):
    """The survey's wall lines of line ln at level 0 and above ([(n, 3)]), those reaching a box (x0, y0, x1, y1) where one is given."""
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
        # (level 0 and above: a walled ramp's sides are surveyed at level 1, the Modřany viaduct's, line 17 (-2385, -9250),
        # with the ground stepping 5 m across them; a bridge's parapet at level 1 has no step in the raster and makes no
        # stretch. Underground levels are left out)
        if r[0] != k or r[1] < 0:
            continue
        p = np.array([[v if v is not None else np.nan for v in r[i:i + 3]] for i in range(3, len(r), 3)], float)
        if len(p) < 2:
            continue
        if box is not None and (p[:, 0].max() < box[0] or p[:, 0].min() > box[2] or p[:, 1].max() < box[1] or p[:, 1].min() > box[3]):
            continue
        out.append(p)
    return out


def wall_outlines(ln, root=ROOT, box=None):
    """The outlines of the survey's wall areas of line ln ([(n, 3)], closed), those reaching a box where one is given."""
    path = os.path.join(root, "data", f"line{ln}.dtm.json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for a in d.get("areas") or []:
        if a.get("c") != "wall" or len(a.get("r") or []) < 3:
            continue
        p = np.array([[v if v is not None else np.nan for v in q[:3]] for q in a["r"] + a["r"][:1]], float)
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
        box = (box[0] - FIT[-1], box[1] - FIT[-1], box[2] + FIT[-1], box[3] + FIT[-1])
    return of_lines(source_lines(ln, root, box), lidar or ipr_lidar(), wall_outlines(ln, root, box))


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
        st = of_lines(src, lidar, wall_outlines(ln))
        seg = [(np.hypot(np.diff(s["p"][:, 0]), np.diff(s["p"][:, 1])), np.abs(s["zl"] - s["zr"])) for s in st]
        L = np.concatenate([q[0] for q in seg]) if seg else np.zeros(0)
        H = np.concatenate([(q[1][:-1] + q[1][1:]) / 2 for q in seg]) if seg else np.zeros(0)
        bands = [float(L[(H >= lo) & (H < hi)].sum()) / 1000 for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 1e9))]
        print(f"| {ln} | {km:.2f} | {len(st)} | {L.sum() / 1000:.2f} | " + " / ".join(f"{b:.2f}" for b in bands) + " |")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
