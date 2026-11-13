# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every drawn track's bed width, each side, by its style and the survey (#547).

    python -P -E tools/track_beds.py --line 37              # the widths' report (track_styles.py writes them)
    python -P -E tools/track_beds.py --calibrate 9,17,22,23,37   # the style widths, measured on the survey

The user, 2026-11-13: "The track style is too narrow, it should cover wider area, particularly in between the tracks
running together in both direction should be filled with the same style". Until #547 every bed was a 2.7 m ribbon.

Each side of a track, every `heights.step` m along its `p` (as `zs`), from its axis:
- **in the survey's area of its style** (tram for paved track, green for grass, rail for ballast: GROUP): out to that
  area's edge, MIN to MAX m;
- **elsewhere** (a paved track in the carriageway, a line without survey): the style's WIDTH, the median of the first
  case measured on the five lines (`--calibrate`);
- **a paired track beside it** (another drawn track within PAIR m, parallel): to the middle of the strip between them,
  the side marked `meet` (the page lays the edge at the two tracks' mean height there, as terrain.js heightAt lays the
  street between them);
- **another track nearer** (a diamond, a track leaving at a switch): no further than where its axis is nearer than
  ours (the bisector), so no bed lies over another's rail (#165) except where the two axes are within a gauge (a
  switch's tongue, a diamond's middle), and never inside its own rails.
The widths of the first two are smoothed by a running median over SMOOTH samples before the others cut them.

Written by tools/track_styles.py as `tracks[i].bed`: {l, r} in cm (left and right of `p`'s direction), `meet` the
sides that meet a paired track (1 left, 2 right). Drawn by src/world.js.
"""
import json
import math
from pathlib import Path
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from route import Route  # noqa: E402

GAUGE = 0.72           # m: a rail from the axis (src/world.js)
RAIL = 1.35            # m: the bed's half width before #547 (the report's before)
MIN, MAX = 1.0, 3.0    # m: the bed's half width from the survey's area (MAX: the track corridor the street is laid to,
                       # src/world.js flushDtm)
PAIR = (2.0, 6.0)      # m: a parallel track this far is the paired one (the opposite track, heights.backOff)
PARALLEL = 0.95        # |cos| of the angle between two tracks counted parallel
STEP_OUT = 0.1         # m: the survey read across the track
SMOOTH = 5             # samples of the running median
GROUP = {"embedded": ("tram",), "panels": ("tram",), "grass": ("green", "tram"), "ballast": ("rail", "tram")}
# m: the half width where the survey holds no area of the style, the median of its areas' half width measured on lines
# 9, 17, 22, 23 and 37 (`--calibrate`, 2026-11-13)
WIDTH = {"embedded": 1.7, "panels": 1.9, "grass": 2.0, "ballast": 2.5}
NEAR_ROUTE = 6         # m: a track this near our route takes the route's style (src/world.js styleAt)
RANK = {"tram": 3, "rail": 3, "green": 2}


class Areas:
    """The survey's ground-level areas, read for many points at once."""

    def __init__(self, dtm):
        from track_styles import ground_area
        self.c, polys = [], []
        for a in dtm.get("areas", []):
            if not ground_area(a) or len(a["r"]) < 3:
                continue
            p = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
            if not p.is_valid:
                p = p.buffer(0)
            if not p.is_empty:
                self.c.append(a["c"])
                polys.append(p)
        self.polys = polys
        self.tree = shapely.STRtree(polys) if polys else None

    def classes(self, xy):
        """The set of classes at each point of xy (n x 2)."""
        out = [set() for _ in range(len(xy))]
        if self.tree is None or not len(xy):
            return out
        pi, ai = self.tree.query(shapely.points(xy), predicate="within")
        for p, a in zip(pi, ai):
            out[int(p)].add(self.c[int(a)])
        return out

    def street(self):
        """The ground-level street areas, one geometry (what shows beside a bed)."""
        from track_styles import ground_area  # noqa: F401
        keep = [p for p, c in zip(self.polys, self.c) if c in ("road", "parking", "tram", "paved", "cycle", "green")]
        return shapely.union_all(keep) if keep else shapely.Polygon()


def styles_along(data, i, ss, xy):
    """The style at each sample of track i: the route's within NEAR_ROUTE m of it, else the track's own sections."""
    route = LineString([q[:2] for q in data["path"]])
    secs = data.get("styles") or []
    own = data["tracks"][i].get("styles") or []
    pts = shapely.points(xy)
    near = shapely.distance(pts, route) < NEAR_ROUTE
    rs = shapely.line_locate_point(route, pts)
    out = []
    for k, s in enumerate(ss):
        if near[k]:
            out.append(next((q["style"] for q in secs if q["s0"] <= rs[k] <= q["s1"]), "panels"))
        else:
            out.append(next((c for a, b, c in own if a <= s <= b), "panels"))
    return out


def neighbours(lines, tree, i, x, y, nx, ny, reach):
    """Other tracks across from (x, y) along (nx, ny) within reach: [(d, parallel)], nearest first."""
    ray = LineString([(x + nx * 0.05, y + ny * 0.05), (x + nx * reach, y + ny * reach)])
    hits = []
    for k in tree.query(ray, predicate="intersects"):
        k = int(k)
        if k == i:
            continue
        o = lines[k]
        g = ray.intersection(o)
        for pt in getattr(g, "geoms", [g]):
            if pt.geom_type != "Point":
                continue
            d = math.hypot(pt.x - x, pt.y - y)
            op = o.project(pt)
            a, b = o.interpolate(max(0, op - 1)), o.interpolate(min(o.length, op + 1))
            v = (b.x - a.x, b.y - a.y)
            vl = math.hypot(*v) or 1
            hits.append((d, abs(v[0] * ny - v[1] * nx) / vl >= PARALLEL))
    return sorted(hits)


def track_bed(data, i, lines, tree, areas, step, probe=None):
    """Track i's bed: {l, r, meet} (module docstring), or None for a track too short to sample. `probe` collects
    {style: [half width]} where the survey's area holds the track and no other track is across (`--calibrate`)."""
    tr = data["tracks"][i]
    tl = lines[i]
    if tl is None or tl.length < 0.5:
        return None
    rt = Route(tr["p"])
    L = rt.length
    n = len(tr.get("zs") or []) or int(L / step) + 2
    ss = [min(k * step, L) for k in range(n)]
    at = [rt.at(s) for s in ss]
    xy = np.array([[a[0], a[1]] for a in at])
    st = styles_along(data, i, ss, xy)
    offs = np.arange(GAUGE + 0.08, MAX + 1e-6, STEP_OUT)
    no = len(offs)
    others = [lines[int(k)] for k in tree.query(tl.buffer(MAX + 1)) if int(k) != i and lines[int(k)] is not None]
    others = shapely.union_all(others) if others else None
    out = {"l": [], "r": [], "meet": [0] * n}
    for side, key, bit in ((1, "l", 1), (-1, "r", 2)):
        nrm = np.array([[-a[3] * side, a[2] * side] for a in at])
        q = (xy[:, None, :] + nrm[:, None, :] * offs[None, :, None]).reshape(-1, 2)
        cls = areas.classes(q) if areas is not None else None
        # (the bisector to every other track: no further than where another axis is nearer than ours)
        if others is not None:
            pts = shapely.points(q)
            nearer = (shapely.distance(pts, others) < shapely.distance(pts, tl)).reshape(n, no)
        w, cut, pair = [], [], []
        for k in range(n):
            ok = set(GROUP[st[k]])
            if cls is not None and cls[k * no] & ok:
                ext = offs[0]
                for j in range(no):
                    if not cls[k * no + j] & ok:
                        break
                    ext = offs[j]
                wk, held = max(MIN, min(MAX, ext)), True
            else:
                wk, held = WIDTH[st[k]], False
            across = neighbours(lines, tree, i, xy[k, 0], xy[k, 1], nrm[k, 0], nrm[k, 1], 2 * MAX)
            if probe is not None and held and not across:
                probe.setdefault(st[k], []).append(wk)
            w.append(wk)
            c = MAX
            if others is not None and nearer[k].any():
                j = int(np.argmax(nearer[k]))
                c = offs[j - 1] if j else offs[0]
            cut.append(c)
            d, par = across[0] if across else (None, False)
            pair.append(d / 2 if par and PAIR[0] <= d <= PAIR[1] else None)
        w = np.array(w)
        if len(w) >= SMOOTH:
            pad = np.pad(w, SMOOTH // 2, mode="edge")
            w = np.median(np.lib.stride_tricks.sliding_window_view(pad, SMOOTH), axis=1)
        w = np.minimum(w, cut)
        for k in range(n):
            if pair[k] is not None:
                w[k] = pair[k]
                out["meet"][k] |= bit
        out[key] = [int(round(v * 100)) for v in w]
    return out


def beds(data, survey_dtm, probe=None):
    """{track index: bed} for every drawn track."""
    step = (data.get("heights") or {}).get("step", 2.0)
    lines = []
    for tr in data.get("tracks") or []:
        pts = [q[:2] for q in tr.get("p") or []]
        lines.append(LineString(pts) if len(pts) >= 2 else None)
    tree = shapely.STRtree([g if g is not None else Point(1e9, 1e9) for g in lines])
    areas = Areas(survey_dtm) if survey_dtm else None
    out = {}
    for i in range(len(lines)):
        b = track_bed(data, i, lines, tree, areas, step, probe)
        if b is not None:
            out[i] = b
    return out


def outline(tr, bed, old=False, strip=False):
    """The bed's outline as a polygon (old: the 2.7 m ribbon before #547; strip: only its sides that meet a paired
    track, beyond the rail)."""
    rt = Route(tr["p"])
    n = len(bed["l"])
    step = rt.length / max(1, n - 1)
    quads = []
    prev = None
    for k in range(n):
        x, y, hx, hy = rt.at(min(k * step, rt.length))
        cur = []
        for key, bit, side in (("l", 1, 1), ("r", 2, -1)):
            w = RAIL if old else bed[key][k] / 100
            inner = GAUGE if strip else 0
            if strip and not bed["meet"][k] & bit:
                w = inner
            cur.append(((x - hy * side * inner, y + hx * side * inner), (x - hy * side * w, y + hx * side * w)))
        if prev is not None:
            for j in range(2):
                q = shapely.Polygon([prev[j][0], prev[j][1], cur[j][1], cur[j][0]])
                if q.area > 1e-6:
                    quads.append(q if q.is_valid else q.buffer(0))
        prev = cur
    return shapely.union_all(quads) if quads else shapely.Polygon()


def report(data, survey_dtm, bs):
    """Per line, before (2.7 m ribbons) and after: the bed area, the bed between paired tracks beyond their rails, the
    survey's street showing within 3 m of a track (m²)."""
    lines = [LineString([q[:2] for q in tr["p"]]) for i, tr in enumerate(data["tracks"]) if i in bs]
    near = shapely.union_all([g.buffer(3) for g in lines])
    tr = data["tracks"]
    old = shapely.union_all([outline(tr[i], b, True) for i, b in bs.items()])
    new = shapely.union_all([outline(tr[i], b) for i, b in bs.items()])
    so = shapely.union_all([outline(tr[i], b, True, True) for i, b in bs.items()])
    sn = shapely.union_all([outline(tr[i], b, False, True) for i, b in bs.items()])
    street = Areas(survey_dtm).street().intersection(near) if survey_dtm else shapely.Polygon()
    return {"bed m2": [round(old.area), round(new.area)], "between paired m2": [round(so.area), round(sn.area)],
            "street showing m2": [round(street.difference(old).area), round(street.difference(new).area)]}


def calibrate(lines):
    """The median half width of the survey's area of each style beside its tracks, where it holds them and no other
    track is across."""
    vals = {}
    for line in lines:
        dp = ROOT / "data" / f"line{line}.dtm.json"
        if dp.exists():
            beds(json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8")),
                 json.loads(dp.read_text(encoding="utf-8")), vals)
    for k, v in sorted(vals.items()):
        print(f"{k}: n {len(v)}, p10 {np.percentile(v, 10):.2f}, median {np.median(v):.2f}, p90 {np.percentile(v, 90):.2f}")


def main():
    if "--calibrate" in sys.argv:
        calibrate(sys.argv[sys.argv.index("--calibrate") + 1].split(","))
        return
    if "--line" not in sys.argv:
        sys.exit(__doc__)
    line = sys.argv[sys.argv.index("--line") + 1]
    data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
    dp = ROOT / "data" / f"line{line}.dtm.json"
    dtm = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else None
    bs = beds(data, dtm)
    print(f"line {line}: " + json.dumps(report(data, dtm, bs)))


if __name__ == "__main__":
    main()
