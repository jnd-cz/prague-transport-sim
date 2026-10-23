"""Street model (pilot): smooth street surfaces with fixed level steps, meshed offline.

The surveyed DTM areas (tools/dtm.py) are draped on their own noisy corner heights, so
neighbouring areas disagree (steps, bumpy footways, uneven kerbs), and splitting their long
kerb-shaped outlines in the browser makes ~1.7 M sliver triangles. Here, as BeamNG.Earth does for
its roads, heights come from a few smooth rules instead (inspired by its grading.py):

  carriageway (road, parking, tram bed)  Z0: one smooth surface, a Gaussian-weighted average of the
                                         surveyed carriageway points (outliers rejected)
  sidewalk, island, cycle, paved         Z0 + kerb (0.13 m), or Z0 for paving at road level
  platform                               Z0 + one constant step per platform
Areas whose survey disagrees with the rule (a terrace, a ramp, a wall: median off by more than
0.3 m, or spread over 0.35 m) keep their surveyed heights. Snapped areas are meshed on an 8 m grid
(4 m within 7 m of a track, where the street is laid flush with the track bed in the game), every
piece split at 4 m along its edges so neighbouring cells share their vertices (no cracks). Kerb
faces are flagged only on edges that touch the carriageway.

Also lists the stops without an island or platform beside the track (Vienna-type stops: boarding
from the sidewalk across the car lane).

Usage:  python tools/streets.py --line 17                 the whole line, in 1.5 km chunks
        python tools/streets.py --line 22 --from 10850 --to 12900   one stretch (the first pilot)
Rewrites data/lineN.dtm.json: snapped areas get "v" (vertices [x, y, z]), "t" (triangle indices),
"k" (kerb flag per ring edge, per ring) and "s" (offset above Z0); rerunning starts from the survey.
"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
import shapely
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
LINE, S0, S1, CHUNK = arg("--line", "22"), arg("--from", 0.0), arg("--to", 1e9), arg("--chunk", 1500.0)
KERB = 0.13
# carriageway fit: Gaussian scale (m) and outlier rejection (m); σ 3 m followed the survey's noise
# (tram-bed corners, inner division lines): ±0.1-0.2 m waves within a few metres on line 17
SIGMA, REJECT = arg("--sigma", 6.0), arg("--reject", 0.15)
CARRIAGEWAY = {"road", "parking", "tram"}
SNAP = {"road", "parking", "tram", "sidewalk", "island", "cycle", "paved", "platform"}
GRID = 2.0

dst = os.path.join(ROOT, "data", f"line{LINE}.dtm.json")
dtm = json.load(open(dst, encoding="utf-8"))
line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))

# start from the survey again (a previous run's model is replaced)
for a in dtm["areas"]:
    if "v" in a:
        a["r"], a["h"] = a.pop("r0"), a.pop("h0", [])
        if not a["h"]:
            a.pop("h")
        for k in ("v", "t", "k", "s"):
            a.pop(k, None)

# route positions s along the path; the pilot stretch
path = line["path"]
acc = [0.0]
for p, q in zip(path, path[1:]):
    acc.append(acc[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))


def poly(a):
    try:
        g = Polygon([p[:2] for p in a["r"]], [[p[:2] for p in h] for h in a.get("h", [])])
        return g if g.is_valid else g.buffer(0)
    except Exception:
        return None


ground = [a for a in dtm["areas"] if a["l"] == 0]
geoms = {id(a): poly(a) for a in ground}
def surv(a):
    """The surveyed ring (a model area from an earlier chunk keeps its survey in r0)."""
    return a.get("r0", a["r"])


def run(S0, S1):
    """Model the areas whose nearest route position lies in S0..S1 (fits use everything around)."""
    pilot = [a for a in ground if a["c"] in SNAP and geoms[id(a)] is not None and S0 <= s_of[id(a)] < S1
             and route_ls.distance(geoms[id(a)].representative_point()) < 90]
    if not pilot:
        return
    print(f"stretch s {S0:.0f}..{S1:.0f}: {len(pilot)} areas")

    # ------------------------------------------------------------------ Z0: the carriageway surface
    xs = [p[0] for a in pilot for p in surv(a)]
    ys = [p[1] for a in pilot for p in surv(a)]
    X0, Y0 = min(xs) - 40, min(ys) - 40
    NX, NY = int((max(xs) + 40 - X0) / GRID) + 1, int((max(ys) + 40 - Y0) / GRID) + 1
    bbox = box(X0, Y0, X0 + NX * GRID, Y0 + NY * GRID)
    carr = [geoms[id(a)] for a in ground if a["c"] in CARRIAGEWAY and geoms[id(a)] is not None and geoms[id(a)].intersects(bbox)]
    carr_u = unary_union(carr)
    inner = carr_u.buffer(-0.2)  # cloud points on a kerb line belong to the kerb top, not the road
    pts = [p for a in ground if a["c"] in CARRIAGEWAY and geoms[id(a)] is not None and geoms[id(a)].intersects(bbox) for p in surv(a)]
    px = np.array([p[0] for p in pts]); py = np.array([p[1] for p in pts]); pz = np.array([p[2] for p in pts], float)
    cz = np.array(dtm.get("z", []), float).reshape(-1, 3)
    cz = cz[(cz[:, 0] > X0) & (cz[:, 0] < X0 + NX * GRID) & (cz[:, 1] > Y0) & (cz[:, 1] < Y0 + NY * GRID)]
    cz = cz[shapely.contains_xy(inner, cz[:, 0], cz[:, 1])]
    px, py, pz = np.concatenate([px, cz[:, 0]]), np.concatenate([py, cz[:, 1]]), np.concatenate([pz, cz[:, 2]])
    print(f"carriageway points: {len(px)} ({len(cz)} inside the carriageways)")


    def gauss(a, sigma):
        r = int(3 * sigma / GRID) + 1
        k = np.exp(-0.5 * (np.arange(-r, r + 1) * GRID / sigma) ** 2)
        k /= k.sum()
        a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 0, a)
        return np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 1, a)


    def solve(keep, px, py, pz):
        """Normalized convolution: smooth where there are points (sigma 3 m), wider where sparse."""
        W = np.zeros((NY, NX)); WZ = np.zeros((NY, NX))
        ix = np.clip(((px[keep] - X0) / GRID).round().astype(int), 0, NX - 1)
        iy = np.clip(((py[keep] - Y0) / GRID).round().astype(int), 0, NY - 1)
        np.add.at(W, (iy, ix), 1.0); np.add.at(WZ, (iy, ix), pz[keep])
        Z, C = None, None
        for sigma in (SIGMA, 8.0 if SIGMA < 8 else 2 * SIGMA, 20.0, 60.0):
            w, wz = gauss(W, sigma), gauss(WZ, sigma)
            z = wz / np.maximum(w, 1e-12)
            conf = np.clip(w / 0.05, 0, 1)  # enough points around at this scale
            if Z is None:
                Z, C = z, conf
            else:
                Z = C * Z + (1 - C) * z  # the finer scale where it had points, the coarser elsewhere
                C = np.maximum(C, conf)
        return Z


    def zat(Z, x, y):
        fx = np.clip((np.asarray(x) - X0) / GRID, 0, NX - 1.001); fy = np.clip((np.asarray(y) - Y0) / GRID, 0, NY - 1.001)
        ix, iy = fx.astype(int), fy.astype(int); tx, ty = fx - ix, fy - iy
        return (Z[iy, ix] * (1 - tx) + Z[iy, ix + 1] * tx) * (1 - ty) + (Z[iy + 1, ix] * (1 - tx) + Z[iy + 1, ix + 1] * tx) * ty


    keep = np.ones(len(px), bool)
    for it in range(3):
        Z = solve(keep, px, py, pz)
        res = pz - zat(Z, px, py)
        keep = np.abs(res) < REJECT
        print(f"pass {it}: rms {np.sqrt(np.mean(res[keep] ** 2)):.3f} m, {np.sum(~keep)} outliers")

    # ------------------------------------------------------------------ snap the areas to the rule
    tracks = unary_union([shapely.LineString(t["p"]) for t in line["tracks"] if len(t["p"]) > 1]).intersection(bbox.buffer(50))
    near_track = tracks.buffer(7)
    snapped, kept = defaultdict(int), defaultdict(int)


    def mesh(g, field, off):
        """Triangles of polygon g on the 8 m / 4 m grid, z = field + off. Returns (verts, tris)."""
        vid, verts, tris = {}, [], []
        gx0, gy0, gx1, gy1 = g.bounds
        for size, zone in ((8.0, g.difference(near_track)), (4.0, g.intersection(near_track))):
            if zone.is_empty:
                continue
            for cx in np.arange(math.floor(gx0 / size) * size, gx1, size):
                for cy in np.arange(math.floor(gy0 / size) * size, gy1, size):
                    piece = zone.intersection(box(cx, cy, cx + size, cy + size))
                    if piece.is_empty or piece.area < 0.01:
                        continue
                    piece = shapely.segmentize(piece, 4.0)
                    for tri in shapely.constrained_delaunay_triangles(piece).geoms:
                        c = list(tri.exterior.coords)[:3]
                        if abs((c[1][0] - c[0][0]) * (c[2][1] - c[0][1]) - (c[1][1] - c[0][1]) * (c[2][0] - c[0][0])) < 1e-4:
                            continue
                        ids = []
                        for x, y in c:
                            k = (round(x, 2), round(y, 2))
                            if k not in vid:
                                vid[k] = len(verts)
                                verts.append([k[0], k[1], 0.0])
                            ids.append(vid[k])
                        tris += ids
        if verts:
            v = np.array(verts)
            v[:, 2] = zat(field, v[:, 0], v[:, 1]) + off
            verts = [[round(a, 2), round(b, 2), round(c, 3)] for a, b, c in v]
        return verts, tris


    def kerb_flags(ring):
        out = []
        for p, q in zip(ring, ring[1:] + ring[:1]):
            m = Point((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            out.append(1 if carr_u.distance(m) < 0.4 else 0)
        return out


    # ------------------------------------------------------------------ R: the raised surface
    # Sidewalks, islands, cycle paths and paving at sidewalk level share one smooth surface fitted to
    # their own survey (real crossfall towards the facades kept), at least MIN_KERB above the road.
    # Paving and cycle paths at road level belong to the carriageway. Areas far off the smooth surface
    # (a terrace, steps, a ramp behind a wall) keep their survey and are left out of the fit.
    RAISED = {"sidewalk", "island", "cycle", "paved"}
    MIN_KERB = 0.06


    def ring_dev(a, field):
        r = surv(a)
        zs = np.array([p[2] for p in r], float)
        dev = zs - zat(field, [p[0] for p in r], [p[1] for p in r])
        med = float(np.median(dev))
        return med, float(np.percentile(np.abs(dev - med), 90))


    level = {}
    for a in pilot:
        if a["c"] in CARRIAGEWAY:
            level[id(a)] = "road"
        elif a["c"] in RAISED:
            med, spread = ring_dev(a, Z)
            level[id(a)] = "road" if a["c"] in ("paved", "cycle") and abs(med) < 0.05 and spread < 0.1 else "raised"
        else:
            level[id(a)] = "platform"
    raised = [a for a in ground if a["c"] in RAISED and geoms[id(a)] is not None and geoms[id(a)].intersects(bbox)
              and level.get(id(a), "raised") == "raised"]
    for it in range(3):
        rp = np.array([p for a in raised for p in surv(a)], float)
        R = solve(np.ones(len(rp), bool), rp[:, 0], rp[:, 1], rp[:, 2])
        out = [a for a in raised if (lambda m, sp: abs(m) > 0.25 or sp > 0.3)(*ring_dev(a, R))]
        print(f"raised pass {it}: {len(rp)} points, {len(out)} areas off the smooth surface")
        if not out:
            break
        raised = [a for a in raised if a not in out]
    R = np.maximum(R, Z + MIN_KERB)
    in_fit = {id(a) for a in raised}

    ntri_new = 0
    for a in pilot:
        g = geoms[id(a)].simplify(0.05)
        if g.is_empty or g.geom_type != "Polygon":
            kept[a["c"]] += 1
            continue
        c, lv = a["c"], level[id(a)]
        if lv == "road":
            field, off = Z, 0.0
        elif lv == "raised":
            if id(a) not in in_fit:
                kept[c] += 1
                continue
            field, off = R, 0.0
        else:  # platform: one constant step above the road
            med, spread = ring_dev(a, Z)
            if spread > 0.35:
                kept[c] += 1
                continue
            field, off = Z, min(0.35, max(0.10, med))
        verts, tris = mesh(g, field, off)
        if not tris:
            kept[c] += 1
            continue
        ntri_new += len(tris) // 3
        ring = [list(p) for p in g.exterior.coords][:-1]
        holes = [[list(p) for p in h.coords][:-1] for h in g.interiors]
        rz = lambda r: [[round(x, 2), round(y, 2), round(float(z) + off, 3)] for (x, y), z in zip(r, zat(field, [p[0] for p in r], [p[1] for p in r]))]  # noqa: E731
        a["r0"], a["h0"] = a["r"], a.get("h", [])
        a["r"], a["h"] = rz(ring), [rz(h) for h in holes]
        if lv != "road":
            a["k"] = [kerb_flags(r) for r in [a["r"]] + a["h"]]
        a["v"], a["t"], a["s"] = verts, tris, off
        snapped[c] += 1

    print("snapped:", dict(snapped))
    print("kept surveyed (terrace, ramp, wall or odd shape):", dict(kept))
    print(f"triangles of the snapped areas: {ntri_new}")



# the whole line (or --from/--to) in chunks along the route: every area is modelled once, in the
# chunk of its nearest route position; the fits reach 40 m beyond each chunk, so seams agree
route_ls = shapely.LineString(path)
s_of = {id(a): route_ls.project(geoms[id(a)].representative_point()) for a in ground if geoms[id(a)] is not None}
S1 = min(S1, acc[-1] + 1)  # (no --to: the whole route)
for c0 in np.arange(S0, S1, CHUNK):
    run(c0, min(S1, c0 + CHUNK))

# ------------------------------------------------------------------ Vienna-type stops
# What lies right of the track along the platform (2.2..3.4 m from the track centre, doors on the
# right): an island or sidewalk = boarding from a raised edge; carriageway = boarding from the
# sidewalk across the car lane (Vienna-type stop: cars stop behind the tram while its doors are open)
tree_g = [geoms[id(a)] for a in ground if geoms[id(a)] is not None]
tree_c = [a["c"] for a in ground if geoms[id(a)] is not None]
tree = shapely.STRtree(tree_g)


def class_at(x, y):
    for i in tree.query(Point(x, y), predicate="intersects"):
        return tree_c[i]
    return None


def at_s(s):
    i = max(1, min(len(acc) - 1, next((k for k, a in enumerate(acc) if a >= s), len(acc) - 1)))
    p, q = path[i - 1], path[i]
    u = (s - acc[i - 1]) / max(1e-6, acc[i] - acc[i - 1])
    l = math.hypot(q[0] - p[0], q[1] - p[1]) or 1
    return p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u, (q[0] - p[0]) / l, (q[1] - p[1]) / l


vienna = []
for st in line["stops"]:
    if not (S0 - 50 <= st["s"] <= S1 + 50):
        continue
    seen = defaultdict(int)
    p0, p1 = st.get("p0", st["s"] - 30), st.get("p1", st["s"])
    for s in np.arange(p0 + 3, p1 - 2, 4):
        x, y, hx, hy = at_s(s)
        for off in (2.2, 2.8, 3.4):
            seen[class_at(x + hy * off, y - hx * off)] += 1
    raised = sum(v for k, v in seen.items() if k in ("island", "platform", "sidewalk", "paved"))
    lane = sum(v for k, v in seen.items() if k in CARRIAGEWAY)
    share = lane / max(1, lane + raised)
    kind = "Vienna-type (boarding across the car lane)" if share > 0.5 else "mixed: check" if share > 0.25 else "island / raised edge"
    if share > 0.25:
        vienna.append(st["name"])
    print(f"stop {st['name']} (platform {st['off']} m from the track): {kind}  {dict(seen)}")
dtm["vienna"] = vienna

with open(dst, "w", encoding="utf-8") as fh:
    json.dump(dtm, fh, ensure_ascii=False, separators=(",", ":"))
print(f"wrote {dst} ({os.path.getsize(dst) / 1e6:.2f} MB)")
