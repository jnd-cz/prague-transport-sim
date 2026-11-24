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
  MIN_LEN, gaps up to GAP closed; levels and slopes smoothed along it over SMOOTH points;
- the survey's paved strips up to STRIP across are wall lines where it has no wall line within GEO_NEAR (strip_lines,
  #770): one with heights by its outline, one on the lidar's ground by its low side's edge;
- Geoportál's retaining walls are wall lines too where the survey has none within GEO_NEAR (geoportal_lines, #765),
  their top from their own height over the foot (retained);
- a stretch is cut where its line turns by over TURN, and a piece under PIECE between two turns is none: a side is
  read square to the line, so at a corner it is another ground, and smoothed round the corner it was carried there.
  At the Modřany abutment's corner (line 17 (-2392.7, -9250.8)) the wall's line jogs 0.5 m before it runs along the
  ramp; the ramp's top (204 m), carried round the jog, stood as shards on the sidewalk under the bridge (198.3 m).
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
TURN = 30.0  # degrees: a stretch is cut where its line turns by more
PIECE = 1.0  # m: a piece between two turns shorter than this is no stretch
GEO_NEAR = 2.0  # m: Geoportál's retaining wall this near a survey wall line or wall area's outline is that wall
HOLD = 1.5  # m: the ground is held to a wall's levels this far from its line (ground_mesh.WALL_HOLD)
STAIRS_NEAR = 1.0  # m: a stairs' side (of_lines `own`) steps where IPR this far out of the stairs ...
STAIRS_SEEN = 0.5  # ... already has this share of the step (the raster smears a wall over 2 m: half of it 1 m out)


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
    """(the level at the line, the slope away from it, whether a survey height gave it, IPR past the next wall where
    one did) of the ground on one side of
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
    past = np.full(len(S), np.nan)
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
        with warnings.catch_warnings():  # (the ground past the next wall: FIT m beyond it)
            warnings.simplefilter("ignore", RuntimeWarning)
            past[i] = np.nanmedian(np.stack([np.asarray(lidar(S[i, 0] + sign * S[i, 3] * (reach[i] + o),
                                                              S[i, 1] + sign * S[i, 4] * (reach[i] + o)), float) for o in d]), 0)
    return lvl, g, surveyed, past


def levels(S, lidar, walls=None, strips=False):
    """The ground to the left and to the right of sampled points S (sample()), lidar(x, y) IPR's raster, walls the
    segments ((A, B), each (m, 3)) a side's readings stop at: (zl, gl, zr, gr), each side's level at the line and its
    slope away from it (see the module's text). strips: and per side, where it is the strip to the next wall line (a
    surveyed height, _side) and IPR past that line (of_lines: a slot)."""
    (zl, gl, sl, pl), (zr, gr, sr, pr) = _side(S, lidar, 1.0, walls), _side(S, lidar, -1.0, walls)
    z = S[:, 2]
    # (the line's own height is the side's it lies nearer, within OWN; a strip's level is a surveyed height already)
    dl, dr = np.abs(z - zl), np.abs(z - zr)
    own_l = np.isfinite(z) & (dl <= OWN) & (dl <= dr) & ~sl
    own_r = np.isfinite(z) & (dr <= OWN) & (dr < dl) & ~sr
    if strips:
        return np.where(own_l, z, zl), gl, np.where(own_r, z, zr), gr, (sl, pl), (sr, pr)
    return np.where(own_l, z, zl), gl, np.where(own_r, z, zr), gr


def retained(S, lidar, h, walls=None):
    """(zl, gl, zr, gr) of sampled points S of a retaining wall known by its line and its height h over its foot
    (Geoportál's, geoportal_lines), where the ground behind it stands STEP or more over its foot; else no step.
    Such a line lies a metre or so off the raster's rise, and under a steep bank the raster has no step to read: under
    Letná (line 17 (150, 806), a wall of 3.5 m along the road) it rises 1 m per metre for 4 m, and a side's fit read
    back to the line gave the top anywhere between 191.3 and 195.3 m within 30 m of wall, teeth instead of a wall.
    - The foot is the lower side's level, read as any side's (_side); the line has one high side, the one the raster
      rises to at FIT along most of it.
    - The top is the foot plus h, no higher than the ground FIT m behind (a retaining wall ends at the ground it
      holds) and no lower than the ground HOLD m behind.
    - Behind the top the ground runs straight to the raster's height HOLD m behind, where the hold ends: no step there.
      (Where the line lies before the real wall the ground dips behind the top, as the slab the page drew stood proud
      of it, src/structures.js buildWalls until #765.)"""
    d = np.asarray(FIT, float)
    (zl, gl, _, _), (zr, gr, _, _) = _side(S, lidar, 1.0, walls), _side(S, lidar, -1.0, walls)

    def behind(sign, offs):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmax(np.stack([np.asarray(lidar(S[:, 0] + sign * S[:, 3] * o, S[:, 1] + sign * S[:, 4] * o), float) for o in offs]), 0)
    fl, fr = behind(1.0, d), behind(-1.0, d)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        left = bool(np.nanmedian(fl - fr) > 0)
    sign = 1.0 if left else -1.0
    foot, far = (zr, fl) if left else (zl, fr)
    near = behind(sign, [HOLD])
    with np.errstate(invalid="ignore"):
        top = np.fmax(np.fmin(foot + h, far), near)
        top = np.where(np.isfinite(far) & (far - foot >= STEP), top, foot)
    top = _median(np.where(np.isfinite(top), top, foot))
    g = np.where(np.isfinite(near), (near - top) / HOLD, 0.0)
    g = np.where(top - foot >= STEP, np.clip(g, -SLOPE, 0.0), 0.0)
    return (top, g, zr, gr) if left else (zl, gl, top, g)


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


def straight(S, d, a, b):
    """The run a..b of sampled points S (distances d) cut at its turns over TURN: [(i, j, whether it ends at a turn)],
    the pieces under PIECE left out (the whole run where it has no turn)."""
    if b - a < 2:
        return [(a, b, False)]
    v = np.diff(S[a:b + 1, :2], axis=0)
    ang = np.arctan2(v[:, 1], v[:, 0])
    turn = np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi) > math.radians(TURN)
    cuts = [a] + [a + 1 + int(k) for k in np.flatnonzero(turn)] + [b]
    if len(cuts) == 2:
        return [(a, b, False)]
    return [(i, j, j != b) for i, j in zip(cuts, cuts[1:]) if d[j] - d[i] >= PIECE]


def of_lines(lines, lidar, others=(), meeting=(), heights=None, outside=None, own=None):
    """The stretches of polylines ([(n, 3) arrays]): [{"p": (m, 2), "zl", "gl", "zr", "gr": (m,)}]. others: more lines
    a side's readings stop at (the survey's wall areas' outlines). meeting: the lines (their indexes) whose two ends
    stand on other walls (an abutment's line between its wing walls' corners, ground_mesh.abutments): an end's
    readings run along that wall, through the raster's smear of it, and the point next to the end stands for it.
    heights: {a line's index: its wall's height over its foot}, for the lines known by a height (retained).
    outside: {a line's index: "l" or "r"}, for a strip's outline: the side that is not the strip (`out` of its
    stretches: ground_mesh.hold_at_walls). A stretch one of whose sides is a slot carries `sl` / `sr`, per point whether
    that side is: the strip to the next wall line there (levels()), its level STEP or more under the ground on both
    sides of the pair, the stretch's other side and IPR past the next line (a
    stairwell, an areaway; between a terrace's foot line and top line the strip is level with the lower ground). The
    slot ends where the pair does, and its level holds nothing past the stretch's end (hold_at_walls).
    own: {a line's index: "l" or "r"}, for a stairs' side (ground_mesh.stairs_sides): that side's level is the line's
    own height, level across (the stairs' own heights; IPR read inside a flight lies on the steps below or above), and
    the stretch carries it as `stairs`. The other side steps from it only where IPR STAIRS_NEAR m out already has
    STAIRS_SEEN of that step: read FIT m out and carried back by its slope, a bank rising a metre off the Dobeška
    stairs' curb (line 17 (-1203, -4790)) stood 1.1 m over them at their side, the raster 0.05 m."""
    out = []
    walls = segments(list(lines) + list(others))
    for n_line, p in enumerate(lines):
        S = sample(np.asarray(p, float))
        if len(S) < 2:
            continue
        h = (heights or {}).get(n_line)
        if h is None:
            zl, gl, zr, gr, sl, sr = levels(S, lidar, walls, strips=True)
        else:
            zl, gl, zr, gr = retained(S, lidar, h, walls)
            sl = sr = (np.zeros(len(S), bool), np.full(len(S), np.nan))
        stairs = (own or {}).get(n_line)
        if stairs is not None:
            none = (np.zeros(len(S), bool), np.full(len(S), np.nan))
            o = -1.0 if stairs == "l" else 1.0  # (out of the stairs: the normal is to the left)
            near = np.asarray(lidar(S[:, 0] + o * S[:, 3] * STAIRS_NEAR, S[:, 1] + o * S[:, 4] * STAIRS_NEAR), float)
            zi, zo = S[:, 2].copy(), (zr if stairs == "l" else zl).copy()
            with np.errstate(invalid="ignore"):
                seen = (zi - near) * np.sign(zi - zo) >= STAIRS_SEEN * np.abs(zi - zo)
            zo = np.where(seen, zo, zi)
            if stairs == "l":
                zl, gl, sl, zr = zi, np.zeros(len(S)), none, zo
            else:
                zr, gr, sr, zl = zi, np.zeros(len(S)), none, zo
        if n_line in meeting and len(S) > 3:
            for q in (zl, gl, zr, gr):
                q[0], q[-1] = q[1], q[-2]
        d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(S[:, 0]), np.diff(S[:, 1])))])
        for a, b, turns in (q for r in runs(np.abs(zl - zr) >= STEP, d) for q in straight(S, d, *r)):
            v = [np.array(q[a:b + 1], float) for q in (zl, gl, zr, gr)]
            if turns:  # (the point at the turn is read square to the line past it: the one before it stands for it)
                for q in v:
                    q[-1] = q[-2]
            out.append({"p": S[a:b + 1, :2].copy(), "zl": _median(v[0]), "gl": _median(v[1]), "zr": _median(v[2]), "gr": _median(v[3])})
            for key, (strip, past), mine, other in (("sl", sl, "zl", "zr"), ("sr", sr, "zr", "zl")):
                with np.errstate(invalid="ignore"):
                    slot = strip[a:b + 1] & (past[a:b + 1] - out[-1][mine] >= STEP) & (out[-1][other] - out[-1][mine] >= STEP)
                if slot.any():
                    out[-1][key] = slot
            if h is not None:
                out[-1]["h"] = h
            if n_line in meeting:  # (a line across a structure: ground_mesh.hold_at_walls leaves the deck's own surface)
                out[-1]["across"] = True
            if n_line in (outside or {}):
                out[-1]["out"] = outside[n_line]
            if stairs is not None:
                out[-1]["stairs"] = stairs
    return out


def source_lines(ln, root=ROOT, box=None):
    """The survey's wall lines of line ln at level 0 and above ([(n, 3)]), those reaching a box (x0, y0, x1, y1) where one is given."""
    path = os.path.join(root, "data", f"line{ln}.zps.json")
    if not os.path.exists(path):
        return []
    # (kept while the file is the same one: a line's street squares each ask for their own box, #786)
    key = (path, os.path.getmtime(path))
    if source_lines.kept[0] != key:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        lines = []
        k = d["kinds"].index(KIND) if KIND in d["kinds"] else None
        for r in d["lines"] if k is not None else ():
            # (level 0 and above: a walled ramp's sides are surveyed at level 1, the Modřany viaduct's, line 17 (-2385, -9250),
            # with the ground stepping 5 m across them; a bridge's parapet at level 1 has no step in the raster and makes no
            # stretch. Underground levels are left out)
            if r[0] != k or r[1] < 0:
                continue
            p = np.array([[v if v is not None else np.nan for v in r[i:i + 3]] for i in range(3, len(r), 3)], float)
            if len(p) >= 2:
                lines.append(p)
        source_lines.kept = (key, lines)
    return [p for p in source_lines.kept[1] if _reaches(p, box)]


source_lines.kept = (None, [])


STRIP = 1.0  # m: a paved survey area this wide or narrower is a strip: a parapet, an edging, a wall's top


def wall_outlines(ln, root=ROOT, box=None, strips=False):
    """The outlines of the survey's wall areas of line ln ([(n, 3)], closed), those reaching a box where one is given.
    strips: and of its paved strips up to STRIP wide (twice the area over the perimeter): the survey has many a wall's
    top as one (under Letná, line 17 (26..317, 800), area 4166: 0.44 m wide and 290 m long at 191.4-196.3 m, the
    wall Geoportál has as a line)."""
    out = []
    for a in _dtm(ln, root):
        if a.get("c") not in (("wall", "paved") if strips else ("wall",)) or len(a.get("r") or []) < 3:
            continue
        p = np.array([[v if v is not None else np.nan for v in q[:3]] for q in a["r"] + a["r"][:1]], float)
        if a["c"] == "paved":
            x, y = p[:, 0], p[:, 1]
            per = float(np.hypot(np.diff(x), np.diff(y)).sum())
            if a.get("g") or not per or abs(float((x[:-1] * y[1:] - x[1:] * y[:-1]).sum())) / per > STRIP:
                continue
        if box is not None and (p[:, 0].max() < box[0] or p[:, 0].min() > box[2] or p[:, 1].max() < box[1] or p[:, 1].min() > box[3]):
            continue
        out.append(p)
    return out


def off_survey(lines, survey, near=GEO_NEAR):
    """The runs of polylines ([(n, 3)]) farther than `near` from the lines `survey` ([(m, 3)]), MIN_LEN or longer:
    [(k, 3)], sampled every SPACING."""
    import shapely
    if not len(lines):
        return []
    if isinstance(survey, shapely.STRtree):
        tree = survey
    else:
        tree = shapely.STRtree([shapely.LineString(np.asarray(q, float)[:, :2]) for q in survey]) if len(survey) else None
    out = []
    for p in lines:
        S = sample(np.asarray(p, float))
        if len(S) < 2:
            continue
        far = np.ones(len(S), bool)
        if tree is not None:
            qi, _ = tree.query(shapely.points(S[:, 0], S[:, 1]), predicate="dwithin", distance=near)
            far[np.unique(qi)] = False
        d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(S[:, 0]), np.diff(S[:, 1])))])
        edge = np.flatnonzero(np.diff(np.concatenate([[False], far, [False]]).astype(int)))
        for a, b in zip(edge[::2], edge[1::2] - 1):
            if d[b] - d[a] >= MIN_LEN:
                out.append(S[a:b + 1, :3].copy())
    return out


def geoportal_lines(ln, root=ROOT, box=None, survey=()):
    """Geoportál's retaining walls of line ln (data/lineN.geo.json `walls`: a line in plan and a height over its foot,
    tools/geoportal.py) as wall lines without heights of their points: ([(n, 3)] with z NaN, [each one's height over
    its foot]), their runs off the survey's own walls (off_survey). 54-75 % of their length lies within GEO_NEAR of a survey wall line or wall area, the same wall a
    second time; of the rest 107-679 m a line step by STEP or more (line 17 (145, 806): 215 m, up to 4.4 m), walls the
    survey lacks. The page drew every one as a slab on the ground (src/structures.js buildWalls, until #765)."""
    path = os.path.join(root, "data", f"line{ln}.geo.json")
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out, hs = [], []
    for w in d.get("walls") or []:
        p = np.array([[q[0], q[1], np.nan] for q in w.get("p") or []], float)
        if len(p) < 2:
            continue
        if box is not None and (p[:, 0].max() < box[0] or p[:, 0].min() > box[2] or p[:, 1].max() < box[1] or p[:, 1].min() > box[3]):
            continue
        runs = off_survey([p], survey)
        out += runs
        hs += [float(w.get("h") or 2.0)] * len(runs)
    return out, hs


def _dtm(ln, root):
    """data/lineN.dtm.json's areas (kept while the file is the same one)."""
    path = os.path.join(root, "data", f"line{ln}.dtm.json")
    if not os.path.exists(path):
        return []
    key = (path, os.path.getmtime(path))
    if _dtm.kept[0] != key:
        with open(path, encoding="utf-8") as f:
            _dtm.kept = (key, json.load(f).get("areas") or [])
    return _dtm.kept[1]


_dtm.kept = (None, [])


def _reaches(p, box):
    return box is None or not (p[:, 0].max() < box[0] or p[:, 0].min() > box[2] or p[:, 1].max() < box[1] or p[:, 1].min() > box[3])


def low_edges(p, lidar):
    """The runs ([(n, 3)], z NaN) of a strip's outline (closed, (n, 3)) along its low side: where IPR's raster FIT m
    out of the strip lies STEP or more under the raster FIT m in, past the strip. A strip on the lidar's ground has no
    heights to go by (tools/zps_inside.py: its outline's sheet misses the ground), only its place in plan: the wall's
    face stands at its edge to the lower ground."""
    x, y = p[:, 0], p[:, 1]
    turn = float((x[:-1] * y[1:] - x[1:] * y[:-1]).sum())  # (over 0: anticlockwise, the inside to the left)
    S = sample(np.column_stack([x, y, np.full(len(p), np.nan)]))
    if len(S) < 2:
        return []
    sign = 1.0 if turn > 0 else -1.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        zin, zout = (np.nanmedian(np.stack([np.asarray(lidar(S[:, 0] + sg * S[:, 3] * o, S[:, 1] + sg * S[:, 4] * o), float)
                                            for o in FIT]), 0) for sg in (sign, -sign))
    d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(S[:, 0]), np.diff(S[:, 1])))])
    with np.errstate(invalid="ignore"):
        low = zin - zout >= STEP
    return [S[a:b + 1, :3].copy() for a, b in runs(low, d)]


def strips(ln, root=ROOT, box=None):
    """Line ln's paved strips at ground level, STRIP wide or narrower (wall_outlines), that are no wall's face in plan
    (ground_mesh.wall_like stands those by their own outline): ([outlines (n, 3), closed], [whether on the lidar's
    ground])."""
    import ground_mesh
    out, on_lidar = [], []
    for a in _dtm(ln, root):
        if a.get("c") != "paved" or a.get("l", 0) != 0 or len(a.get("r") or []) < 3:
            continue
        p = np.array([[v if v is not None else np.nan for v in q[:3]] for q in a["r"] + a["r"][:1]], float)
        if not _reaches(p, box):
            continue
        x, y = p[:, 0], p[:, 1]
        per = float(np.hypot(np.diff(x), np.diff(y)).sum())
        if not per or abs(float((x[:-1] * y[1:] - x[1:] * y[:-1]).sum())) / per > STRIP or ground_mesh.wall_like(a):
            continue
        out.append(p)
        on_lidar.append(bool(a.get("g")))
    return out, on_lidar


def strip_lines(ln, root=ROOT, box=None, survey=(), lidar=None):
    """The survey's paved strips (strips) as wall lines, the runs off the survey's own walls (off_survey). A retaining
    wall's top is often such a strip and nothing else: along the tram's cutting north of Ohrada (line 37
    (3358..3403, -65..14), area 1847: 0.32 m across and 87 m long at 248.2-248.6 m) the track lies 4.7 m under it and
    the paved ground beside it lay on the raster, a bank 2.5 m across where a concrete wall stands (the user's photos
    from the footbridge, 2026-11-20, #770).
    - A strip with the survey's heights: its outline with them. They are its level (_side: a strip under PAIR across),
      so the stretch runs along the edge the ground steps at.
    - A strip on the lidar's ground (the cutting's other wall, area 1818: 0.53 m across, 250 m long): its low side's
      edge alone (low_edges), without heights.
    Returns (the lines, per line the side that is outside its strip, "l" or "r", None for a low edge): whatever lies
    beside a strip's outline is outside it, also in the wedge past its corner (the sidewalk at the end of the wing
    wall by the Vyšehrad tunnel's north mouth, line 17 (-728.42, -2547.90), took the wall's 194.57 m over its own
    193.15, #771)."""
    import shapely
    tree = shapely.STRtree([shapely.LineString(np.asarray(q, float)[:, :2]) for q in survey]) if len(survey) else ()
    out, sides = [], []
    for p, g in zip(*strips(ln, root, box)):
        if g:
            runs_ = off_survey(low_edges(p, lidar or ipr_lidar()), tree)
            side = None
        else:
            runs_ = off_survey([p], tree)
            x, y = p[:, 0], p[:, 1]  # (anticlockwise: the strip to the left of its outline)
            side = "r" if float((x[:-1] * y[1:] - x[1:] * y[:-1]).sum()) > 0 else "l"
        out += runs_
        sides += [side] * len(runs_)
    return out, sides


def ipr_lidar():
    from geo import Frame
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    return lambda x, y: np.asarray(ipr.sample(np.asarray(x) + F.E0, np.asarray(y) + F.N0), float)


def stretches(ln, root=ROOT, box=None, lidar=None, extra=(), stairs=None):
    """The stepped stretches of line ln's wall lines (of_lines), those reaching a box where one is given (with SIDE's
    margin: a stretch is found from its own line alone, so a box's build finds what the line's build does). stairs: the
    stairs' sides as wall lines and the side the stairs lie on (ground_mesh.stairs_sides, #447): their stretches come
    after the walls', each carrying `stairs`; their readings stop at the walls, the walls' do not stop at them."""
    if box is not None:
        box = (box[0] - FIT[-1], box[1] - FIT[-1], box[2] + FIT[-1], box[3] + FIT[-1])
    # (extra: more lines taken as wall lines, ground_mesh.abutments, #763)
    lidar = lidar or ipr_lidar()
    src, areas = source_lines(ln, root, box), wall_outlines(ln, root, box)
    # (the survey's strips where it has no wall line, #770; Geoportal's walls where it has neither, #765)
    walls, sides = strip_lines(ln, root, box, src + areas, lidar)
    known = src + wall_outlines(ln, root, box, strips=True) + [p for p, g in zip(*strips(ln, root, box)) if g]
    geo, hs = geoportal_lines(ln, root, box, known)
    lines = src + walls + geo
    out = of_lines(lines + list(extra), lidar, areas, set(range(len(lines), len(lines) + len(extra))),
                   {len(src) + len(walls) + k: h for k, h in enumerate(hs)},
                   {len(src) + k: v for k, v in enumerate(sides) if v})
    if stairs is not None and len(stairs[0]):
        out += of_lines(stairs[0], lidar, lines + list(extra) + areas, own=dict(enumerate(stairs[1])))
    return out


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
