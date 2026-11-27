# SPDX-License-Identifier: AGPL-3.0-or-later
"""Narrow deep pits in IPR's 2023 lidar under the survey's streets, filled from their rim (#867).

IPR's 1 m raster (tools/ipr_dtm.py) holds pits a few metres across with vertical sides and flat floors, 1-14 m deep,
inside the survey's level-0 roads and sidewalks, where ČÚZK's DMR 5G (the 2009-2013 lidar) has level street: open
excavations or shafts at the time of the 2023 flight, no street the player drives, walks or sees. The scan of
2026-11-26 (#867: the five lines' tiles) found 30 road and sidewalk pits the published ground showed 0.5 m or more
deep; 30 of the 34 roads' and sidewalks' pits 2 m or more deep are absent from DMR 5G. A pit in both lidars is a real
sunken part: of the 133 road, sidewalk and parking pits the rule filled at first (batch E's first build, 2026-11-27,
#757), DMR 5G has 20 too, among them the garage ramp on Na Vápence (3869, -18), 3.0 m deep, built flat (groundPlaces
`na-vapence-garage-ramp`; the user, 2026-11-20, #779: "the road ramp from underground parking").

A **pit** is a connected set of cells at least SKIRT under IPR's grey closing with a disc of radius R cells (the
cells a 9 m disc cannot reach into), DEEP or more at its deepest, no side over LONG_SIDE (longer ones are trenches,
ramps and cuttings, most of those under the streets in both lidars). Its **street cells** are those in a level-0 survey
area of a STREET class; its class, the class most of them are in. It is **filled** when
- at most SHARE of its cells lie in a level-0 KEEP area (stairs, walls: a stair's well, a wall's foot) or in a level -1
  area other than DEEP_UNDER (an underpass, its stairs: a pit over one may be its open well; a tunnel or the metro under
  the street says nothing of it, and a deck or a roof over it stands on the level-0 area's ground);
- ON_STREET or more of its cells are street cells, DEEP or more deep at the deepest of them (a pit beside the street,
  or deep only off it, stays: the user, 2026-11-26, #867: "2 - agree, it matters most on streets where player driver,
  cars and walkers use");
- its rim (the cells RIM m outside, on its own class and in no pit: a kerb beside it steps, the other side is not its
  level) holds MIN_RIM cells or more and lies on a plane within RIM_ROUGH (p90);
- the survey's own outline heights within SURVEY_NEAR (their plane, survey_level) stand at most SURVEY_OFF under that
  plane and SURVEY_OVER over it (the survey does not put the street down into the pit);
- DMR 5G at the deepest street cell stands within DMR_LEVEL of the plane (for 'paved' areas, whose yards and
  forecourts hold 22 sunken parts in both lidars, the user, 2026-11-26, #867: "1 - okay we can do that"; for every
  street class since batch E, #757: a garage ramp, a light well; without DMR 5G there the pit stays).
Its street cells under the plane take the plane's height; its cells off the survey stay.

The fills are one file for the city, data/ipr.fills.json (FILLS), from every line's survey (data/line*.dtm.json),
read by every reader of IPR (ipr_dtm.IprDtm: tile() and fill()), so the street surface, the city mesh, the walls and
the beds read one ground. It is built after every line's survey and before the heights (tools/rebuild.py); the steps
before it (tools/dtm.py, tools/track_styles.py's open_track) read the raster as it is (IprDtm(fills=None)). Each pit
the rule kept, with the reason, is in the file's `kept` (a heuristic logs what it decided).

    python -P -E tools/ipr_pits.py              # data/ipr.fills.json from every line's survey
    python -P -E tools/ipr_pits.py --check      # the pits it fills left in the raster as the readers see it
(tools/bench/street_pits.py: those left, and those the written ground shows)
"""
import glob
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from ipr_dtm import FILLS  # noqa: E402  (data/ipr.fills.json)
STREET = ("road", "sidewalk", "tram", "platform", "island", "median", "cycle", "parking", "paved")
KEEP = ("stairs", "wall")
DEEP_UNDER = ("tunnel",)  # level -1 classes that say nothing of the street over them (and every level under -1: metro)
R = 4  # cells: the closing disc's radius
SKIRT = 0.3  # m under the closing: the pit's cells
DEEP = 1.0  # m: the pit's depth at its deepest
LONG_SIDE = 16  # cells (m): a longer one is a trench (most under the streets are in both lidars: real)
MARGIN = 12  # cells read round a tile
RIM = (1, 3)  # m outside the pit: the rim
MIN_RIM = 8  # rim cells on the pit's class
RIM_ROUGH = 0.5  # m: the rim's p90 off its plane
SURVEY_OFF, SURVEY_OVER = 0.5, 1.5  # m: the survey's outline heights under the rim's plane, over it, at most
SURVEY_NEAR = 15.0  # m: the outline heights read round the pit
SHARE = 0.25  # the share of a pit's cells in stairs or walls, or under an area below ground, that keeps it
ON_STREET = 0.5  # the share of a pit's cells in street areas, at least: most of it in the street
DMR_LEVEL = 0.5  # m: DMR 5G under the plane at the deepest cell, at most (deeper: the pit is in both lidars)
NO, KEPT, OTHER = 0, 254, 255  # class codes: none, a KEEP area, an area just below ground (an underpass)


def disc(r=R):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return np.hypot(yy, xx) <= r + 0.01


def pits(a, cls, survey_z=None, dmr=None):
    """The pits of window a (heights, NaN where no ground; rows north to south) and the rule's verdict on each.
    cls: uint8 class codes per cell (1 + STREET's index, NO, KEPT, OTHER). survey_z(j, i): the survey's outline height
    near cell (row j, column i), NaN where it has none (None: not checked). dmr(j, i): DMR 5G there (None: no DMR).
    Returns [{"j", "i", "depth", "top" (the closing there), "street" (the share of its cells in street areas), "class", "rim", "rough", "survey", "dmr", "cells": (rows, cols, heights), "kept", "round"}]:
    "kept" is None for a pit to fill, else why it stays; "round" is a street pit's surroundings, (rows, cols) of the
    cells RIM m outside it that are in no pit, whatever their class (tools/bench/street_pits.py reads the ground there)."""
    from scipy import ndimage
    ok = ~np.isnan(a)
    if not ok.any():
        return []
    hi = float(np.nanmax(a)) + 1
    af = np.where(ok, a, hi)
    cl = ndimage.grey_closing(af, footprint=disc())
    dep = cl - af
    dep[~ok] = 0
    lab, n = ndimage.label(dep >= SKIRT, structure=np.ones((3, 3)))
    out = []
    for k, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        m = lab == k
        jj, ii = np.nonzero(m)
        dd = dep[jj, ii]
        if dd.max() < DEEP:
            continue
        side = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
        if side > LONG_SIDE:
            continue  # (a trench, a ramp, a cutting: no pit)
        pc = cls[jj, ii]
        st = (pc >= 1) & (pc <= len(STREET))
        d = int(np.argmax(np.where(st, dd, -1.0))) if st.any() else int(np.argmax(dd))
        dj, di = int(jj[d]), int(ii[d])
        p = {"j": dj, "i": di, "depth": round(float(dd[d]), 2), "top": round(float(cl[dj, di]), 2), "class": None, "rim": None, "rough": None,
             "survey": None, "dmr": None, "kept": None, "cells": None, "street": None, "round": None}
        out.append(p)
        if st.any():
            c = int(np.bincount(pc[st]).argmax())  # (the street's class most of its street cells are in)
            p["class"] = STREET[c - 1]
            p["round"] = np.nonzero(ndimage.binary_dilation(m, iterations=RIM[1]) & ~ndimage.binary_dilation(m, iterations=RIM[0])
                                    & ok & (dep < SKIRT))
        if (pc == KEPT).mean() > SHARE:
            p["kept"] = "stairs or a wall"
            continue
        if (pc == OTHER).mean() > SHARE:
            p["kept"] = "under the ground's level"
            continue
        p["street"] = round(float(st.mean()), 2)
        if st.mean() < ON_STREET or dd[d] < DEEP:  # (a pit beside the street: answer 2)
            p["kept"] = "off the street"
            continue
        ring = ndimage.binary_dilation(m, iterations=RIM[1]) & ~ndimage.binary_dilation(m, iterations=RIM[0]) & ok & (cls == c) & (dep < SKIRT)
        rj, ri = np.nonzero(ring)
        if len(rj) < MIN_RIM:
            p["kept"] = "no rim"
            continue
        A = np.c_[ri - di, rj - dj, np.ones(len(ri))]
        coef = np.linalg.lstsq(A, af[rj, ri], rcond=None)[0]
        rough = float(np.percentile(np.abs(af[rj, ri] - A @ coef), 90))
        p["rim"], p["rough"] = round(float(coef[2]), 2), round(rough, 2)
        if rough > RIM_ROUGH:
            p["kept"] = "rim not level"
            continue
        if survey_z is not None:
            z = survey_z(dj, di)
            p["survey"] = None if z != z else round(float(z), 2)
            if z != z or not -SURVEY_OFF <= z - coef[2] <= SURVEY_OVER:
                p["kept"] = "not at the survey's level"
                continue
        z = dmr(dj, di) if dmr else float("nan")
        p["dmr"] = None if z != z else round(float(z), 2)
        if z != z or coef[2] - z > DMR_LEVEL:
            p["kept"] = "in DMR 5G too"
            continue
        plane = coef[0] * (ii - di) + coef[1] * (jj - dj) + coef[2]
        low = (a[jj, ii] < plane) & st  # (the street's cells: those off the survey stay, #867 answer 2)
        p["cells"] = (jj[low], ii[low], plane[low].astype(np.float32))
    return out


# ---------------------------------------------------------------- the survey
def survey_level(V, x, y):
    """The survey's level at (x, y) from its outline points V [[x, y, z]] round it: their plane where they span one (a
    street on a slope), else their median; NaN without points."""
    if not len(V):
        return float("nan")
    if len(V) >= 4:
        A = np.c_[V[:, 0] - x, V[:, 1] - y, np.ones(len(V))]
        if np.linalg.matrix_rank(A[:, :2] - A[:, :2].mean(0)) == 2:
            return float(np.linalg.lstsq(A, V[:, 2], rcond=None)[0][2])
    return float(np.median(V[:, 2]))


def areas(root=ROOT):
    """Every line's survey areas once (data/line*.dtm.json; an area in several lines' files is read once):
    [(class, level, outer ring [[x, y, z]], holes)] in the city frame."""
    seen, out, lines = set(), [], []
    for f in sorted(glob.glob(os.path.join(root, "data", "line*.dtm.json"))):
        lines.append(os.path.basename(f)[4:-9])
        with open(f, encoding="utf-8") as fh:
            for a in json.load(fh)["areas"]:
                k = (a["c"], a.get("l", 0), tuple(map(tuple, a["r"][:3])), len(a["r"]))
                if k in seen or len(a["r"]) < 3:
                    continue
                seen.add(k)
                out.append((a["c"], a.get("l", 0), a["r"], a.get("h") or []))
    return out, lines


def paint(shape, origin, polys):
    """uint8 codes (rows, cols) of cells whose centre lies in the polygons, later ones over earlier: polys is
    [(code, ring, holes)] in the city frame, origin the city coordinates of cell (0, 0)'s centre (Pillow draws)."""
    from PIL import Image, ImageDraw
    h, w = shape
    im = Image.new("L", (w, h), NO)
    d = ImageDraw.Draw(im)
    ox, oy = origin
    for code, ring, holes in polys:
        under = im.copy() if holes else None
        d.polygon([(q[0] - ox, oy - q[1]) for q in ring], fill=code)
        for hl in holes:  # (a hole shows what lay under the area)
            mask = Image.new("1", (w, h), 0)
            ImageDraw.Draw(mask).polygon([(q[0] - ox, oy - q[1]) for q in hl], fill=1)
            im.paste(under, (0, 0), mask)
    return np.asarray(im, dtype=np.uint8)


def order(c, lv):
    """A survey area's code and its order of painting: streets, then other levels, then stairs and walls over them."""
    if lv == -1 and c not in DEEP_UNDER:
        return OTHER, 1  # (an underpass, its stairs and sidewalks: a pit over one may be its open well)
    if lv != 0:
        return None, None  # (a deck or a roof over the ground, a tunnel under it: the ground is the level-0 area's)
    if c in KEEP:
        return KEPT, 2
    if c in STREET:
        return 1 + STREET.index(c), 0
    return None, None


# ---------------------------------------------------------------- the city
def tiles_of(survey):
    """The 500 m tiles holding a level-0 street area's vertex: {(e, n): [area indices touching the tile and its margin]}."""
    from geo import tile_index
    out = {}
    for k, (c, lv, ring, _) in enumerate(survey):
        if order(c, lv)[0] is None:
            continue
        xy = np.asarray(ring, float)[:, :2]
        (x0, y0), (x1, y1) = xy.min(0) - MARGIN, xy.max(0) + MARGIN
        (e0, e1), (n0, n1) = tile_index([x0, x1], [y0, y1])
        for e in range(int(e0), int(e1) + 1):
            for n in range(int(n0), int(n1) + 1):
                out.setdefault((e, n), []).append(k)
    street = {t for t, ks in out.items() if any(survey[k][0] in STREET and survey[k][1] == 0 for k in ks)}
    return {t: ks for t, ks in out.items() if t in street}


def scan(ipr, survey, dmr=None, log=print):
    """The pits of every tile with a survey street: [(pit, (E, N) of its deepest cell, tile)] with each pit's cells as
    raster columns and rows (i, j) in its "cells"."""
    from geo import Frame, tile_box
    F = Frame()
    found, t0 = [], time.time()
    tiles = tiles_of(survey)
    log(f"{len(tiles)} tiles with survey streets", flush=True)
    for n_t, ((te, tn), ks) in enumerate(sorted(tiles.items())):
        x0, y0, x1, y1 = tile_box(te, tn)
        E0, N1 = x0 + F.E0 - MARGIN, y1 + F.N0 + MARGIN
        i0, j0 = int(math.floor(E0 - ipr.e0)), int(math.floor(ipr.n0 - N1))
        n = int(x1 - x0) + 2 * MARGIN + 1
        J, I = np.mgrid[j0:j0 + n, i0:i0 + n]
        a = ipr.cells(I.ravel(), J.ravel()).reshape(I.shape).astype(np.float64)
        if np.isnan(a).all():
            continue
        origin = (ipr.e0 + i0 - F.E0, ipr.n0 - j0 - F.N0)  # (cell (0, 0)'s centre, city frame)
        polys = sorted(((order(survey[k][0], survey[k][1]), k) for k in ks if order(survey[k][0], survey[k][1])[0] is not None),
                       key=lambda t: (t[0][1], t[1]))
        cls = paint(a.shape, origin, [(o[0], survey[k][2], survey[k][3]) for o, k in polys])
        verts = [np.asarray(survey[k][2] + [q for h in survey[k][3] for q in h], float) for _, k in polys]

        def survey_z(j, i, cls=cls, polys=polys, verts=verts, origin=origin):
            code = int(cls[j, i])
            x, y = origin[0] + i, origin[1] - j
            zs = [V[np.hypot(V[:, 0] - x, V[:, 1] - y) < SURVEY_NEAR] for (o, _), V in zip(polys, verts)
                  if o[0] == code and V.shape[1] >= 3]
            return survey_level(np.vstack(zs) if zs else np.zeros((0, 3)), x, y)

        def dmr_at(j, i, origin=origin):
            return float(dmr(np.array([origin[0] + i + F.E0]), np.array([origin[1] - j + F.N0]))[0]) if dmr else float("nan")

        for p in pits(a, cls, survey_z, dmr_at):
            x, y = origin[0] + p["i"], origin[1] - p["j"]
            if not (x0 <= x < x1 and y0 <= y < y1):
                continue  # (its own tile has it)
            if p["cells"] is not None:
                rr, cc, z = p["cells"]
                p["cells"] = (cc + i0, rr + j0, z)
            if p["round"] is not None:  # (city frame: the cells' centres)
                rr, cc = p["round"]
                p["round"] = (origin[0] + cc, origin[1] - rr)
            p["x"], p["y"] = round(float(x), 1), round(float(y), 1)
            found.append(p)
        if n_t % 50 == 0:
            log(f"{n_t}/{len(tiles)} tiles, {time.time() - t0:.0f} s, {len(found)} pits", flush=True)
    return found


def write(found, lines, path=FILLS):
    """The fills file: the pits filled with their cells (raster column, row, height), the kept street pits with why."""
    from atomic import replacing
    fill = [p for p in found if p["kept"] is None and p["cells"] is not None and len(p["cells"][0])]
    kept = [p for p in found if p["kept"] is not None and p["class"] is not None]
    meta = ("x", "y", "class", "depth", "street", "rim", "rough", "survey", "dmr")
    out = {"about": "IPR's pits under the survey's streets, filled from their rim (tools/ipr_pits.py, #867): cells "
                    "[raster column, row, height in m]", "lines": lines,
           "rule": {k: globals()[k] for k in ("R", "SKIRT", "DEEP", "LONG_SIDE", "RIM", "MIN_RIM", "RIM_ROUGH",
                                              "SURVEY_OFF", "SURVEY_OVER", "SURVEY_NEAR", "SHARE", "ON_STREET", "DMR_LEVEL")},
           "filled": [{**{k: p[k] for k in meta},
                       "cells": [[int(i), int(j), round(float(z), 3)] for i, j, z in zip(*p["cells"])]} for p in fill],
           "kept": [{**{k: p[k] for k in meta}, "why": p["kept"]} for p in kept]}
    with replacing(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
    return fill, kept


def load(path=FILLS):
    """{(tile column, tile row): (rows, cols, heights)} of the fills file in a raster of tw x th tiles, as a function
    of (tw, th); {} without the file."""
    if not path or not os.path.exists(path):
        return lambda tw, th: {}
    with open(path, encoding="utf-8") as fh:
        cells = [c for p in json.load(fh)["filled"] for c in p["cells"]]

    def by_tile(tw, th):
        out = {}
        if not cells:
            return out
        C = np.asarray(cells, np.float64)
        i, j, z = C[:, 0].astype(np.int64), C[:, 1].astype(np.int64), C[:, 2].astype(np.float32)
        for key in set(zip((i // tw).tolist(), (j // th).tolist())):
            m = (i // tw == key[0]) & (j // th == key[1])
            out[key] = (j[m] - key[1] * th, i[m] - key[0] * tw, z[m])
        return out
    return by_tile


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    from collections import Counter
    import dmr5g
    from ipr_dtm import IprDtm
    check = "--check" in argv
    survey, lines = areas()
    ipr = IprDtm(fills=FILLS if check else None)
    T = dmr5g.Tiles(fetch=False)
    found = scan(ipr, survey, T.sample)
    if check:  # (the raster as the readers see it: the pits the rule fills are gone)
        left = [p for p in found if p["kept"] is None]
        by = Counter(p["class"] for p in left)
        print(f"street pits the rule would fill, left in the raster as read: {len(left)} {dict(by)}")
        for p in sorted(left, key=lambda p: -p["depth"])[:20]:
            print(f"  ({p['x']}, {p['y']}) {p['class']} {p['depth']} m")
        return 1 if left else 0
    fill, kept = write(found, lines)
    print(f"lines {', '.join(lines)}: {len(found)} pits; filled {len(fill)} "
          f"({dict(Counter(p['class'] for p in fill))}), {sum(len(p['cells'][0]) for p in fill)} cells")
    print("kept on the streets:", dict(Counter(p["kept"] for p in kept)))
    print("wrote", os.path.relpath(FILLS, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
