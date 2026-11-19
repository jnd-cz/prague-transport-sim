# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground of one place, built in about a minute with the full build's code (#757):

    python -P -E tools/ground_place.py krejcarek-ramp           # a place of data/truth.json groundPlaces
    python -P -E tools/ground_place.py --all | --list
    python -P -E tools/ground_place.py --line 37 --at 3915,316 [--reach 60]
    (--ring N: tiles built round the place's own, default 1; --rings: also built with one ring more and the two
    compared; --mesh DIR: a city mesh folder other than the current inputs')

A place is a point of a line and a reach round it. Its ground is built for the tiles its reach touches (the middle) and
`ring` tiles round them, by tools/ground_mesh.py build(within=...): the same partition, faces, heights and weld as the
line's build, of that box only. Then, per place, into reports/places/NAME/:

- **locality**: the middle tiles against the line's written file (data/lineN.ground.*), vertex for vertex and triangle
  for triangle. A tile's ground should depend on the tile and its ring only; a vertex at another height or a triangle
  cut another way is a rule that read something farther off, or the written file is of other tools or data: after a
  rule's change the written file says what the change moved, and --rings (the same tools, one ring more) says what
  still reads farther off. Each moved point is named by what gave it its height (the weld's label).
- **measures** inside the reach, of the place's build and of the written file: the steps' walls (their length by
  height), the steep faces that are no wall (a crumpled slope), the area per class.
- **pictures**: built.png and written.png, the ground from above at the reach (ground_mesh.picture).

Several places take a shared heavy-job turn (3 GB, the threads); one runs as it is.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from geo import tile_box, tile_index, tile_name  # noqa: E402

REACH = 60.0  # m: a place's reach where it names none
WALL_BANDS = (0.1, 0.3, 1.0)  # m: the walls' lengths are counted over each height
STEEP = 1.0  # rise over run: a face that is no wall and steeper than this (45 degrees) is counted as steep
Q = 1000


def places(root=ROOT):
    """data/truth.json groundPlaces: {name: {line, at, reach?, issue, ...}}."""
    with open(os.path.join(root, "data", "truth.json"), encoding="utf-8") as f:
        return {k: v for k, v in (json.load(f).get("groundPlaces") or {}).items() if isinstance(v, dict)}


def tiles_of(at, reach, ring=1):
    """(the middle tiles [(e, n)], the box (x0, y0, x1, y1) of them and `ring` tiles round them)."""
    (e0, e1), (n0, n1) = tile_index([at[0] - reach, at[0] + reach], [at[1] - reach, at[1] + reach])
    mid = [(e, n) for e in range(int(e0), int(e1) + 1) for n in range(int(n0), int(n1) + 1)]
    a, b = tile_box(int(e0) - ring, int(n0) - ring), tile_box(int(e1) + ring, int(n1) + ring)
    return mid, (a[0], a[1], b[2], b[3])


def in_tiles(x, y, mid):
    e, n = tile_index(x, y)
    return np.isin(e * 100003 + n, [a * 100003 + b for a, b in mid])


def keys(a):
    """Rows of an integer array as one comparable value each."""
    a = np.ascontiguousarray(a, np.int64)
    return a.view([("", np.int64)] * a.shape[1]).ravel()


def tri_keys(V, F):
    """Each triangle as its three corners' (x, y, z) mm, the corners in a fixed order."""
    P = V[F]
    order = np.lexsort((P[:, :, 2], P[:, :, 1], P[:, :, 0]), axis=1)
    return keys(np.take_along_axis(P, order[:, :, None], 1).reshape(len(F), 9))


def written(ln, mid, root=ROOT):
    """The written file's middle tiles: (V mm, F, cls ids), or None where the line has no tiled file or lacks one."""
    import ground_mesh as gm
    p = os.path.join(root, "data", f"line{ln}.ground.json")
    if not os.path.exists(p):
        return None
    layout = json.load(open(p, encoding="utf-8"))
    by_name = {t["name"]: t for t in layout.get("tiles") or []}
    with open(os.path.join(root, "data", f"line{ln}.ground.bin"), "rb") as f:
        blob = f.read()
    Vs, Fs, Cs, n = [], [], [], 0
    for e, t in mid:
        tl = by_name.get(tile_name(e, t))
        if tl is None:
            continue
        V, by = gm.decode_one(blob[tl["offset"]:tl["offset"] + tl["bytes"]], tl["layout"])
        Vs.append(np.round(V * Q).astype(np.int64))
        for c, f in by.items():
            Fs.append(f + n)
            Cs.append(np.full(len(f), gm.CLASS_IDS[c]))
        n += len(V)
    if not Vs:
        return None
    V = np.vstack(Vs)
    u, inv = np.unique(V, axis=0, return_inverse=True)  # (the tiles' shared border vertices as one)
    return u, inv.ravel()[np.vstack(Fs)], np.concatenate(Cs)


def middle(built, mid):
    """A build's triangles whose centre lies in the middle tiles, as a tile of the file holds them: (V mm, F, cls)."""
    V, F = built["V"], built["F"]
    cen = V[F].mean(1) / Q
    m = in_tiles(cen[:, 0], cen[:, 1], mid)
    used, fl = np.unique(F[m], return_inverse=True)
    return V[used], fl.reshape(-1, 3), built["cls"][m]


def locality(mine, theirs, corners=None):
    """The place's build against the written file on the middle tiles (each (V mm, F, cls)): the vertices and triangles
    of one that the other lacks; the points both hold at another height, by what gave the build's vertex its height
    (corners: the build's {x, y, z, label})."""
    (V, F, _), (W, G, _) = mine, theirs
    kv, kw = keys(V), keys(W)
    only_v, only_w = V[~np.isin(kv, kw)], W[~np.isin(kw, kv)]
    kt, ku = tri_keys(V, F), tri_keys(W, G)
    rep = {"vertices": {"built": len(V), "written": len(W), "only built": len(only_v), "only written": len(only_w)},
           "triangles": {"built": len(F), "written": len(G), "only built": int((~np.isin(kt, ku)).sum()),
                         "only written": int((~np.isin(ku, kt)).sum())}}
    rep["same %"] = round(100 * (1 - len(only_w) / max(len(W), 1)), 3)
    # the same point in the plane at another height
    pa, pb = keys(only_v[:, :2]), keys(only_w[:, :2])
    both = np.intersect1d(pa, pb)
    moved, where = [], []
    zb = {}
    for k, z in zip(pb.tolist(), only_w[:, 2].tolist()):
        zb.setdefault(k, []).append(z)
    for k, v in zip(pa.tolist(), only_v.tolist()):
        if k in zb:
            moved.append(min(abs(v[2] - z) for z in zb[k]) / Q)
            where.append(v)
    moved = np.asarray(moved)
    rep["points at another height"] = {
        "points": int(len(both)), "median cm": round(float(np.median(moved)) * 100, 1) if len(moved) else 0,
        "max cm": round(float(moved.max()) * 100, 1) if len(moved) else 0,
        "over 1 / 5 / 20 cm": [int((moved > c / 100).sum()) for c in (1, 5, 20)]}
    rep["points in one only"] = {"built": int((~np.isin(pa, pb)).sum()), "written": int((~np.isin(pb, pa)).sum())}
    if corners is not None and len(where):
        ck = keys(np.column_stack([np.round(corners["x"] * Q), np.round(corners["y"] * Q), np.round(corners["z"] * Q)]).astype(np.int64))
        order = np.argsort(ck)
        j = np.clip(np.searchsorted(ck[order], keys(np.asarray(where, np.int64))), 0, len(ck) - 1)
        lab = np.asarray(corners["label"], dtype=object)[order[j]]
        by = {}
        for name, d in zip(lab.tolist(), moved.tolist()):
            by.setdefault(str(name), []).append(d)
        rep["points at another height"]["by what gave the height"] = {
            k: {"points": len(v), "max cm": round(max(v) * 100, 1)} for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))}
        worst = np.argsort(-moved)[:5]
        rep["points at another height"]["the farthest"] = [
            {"at": [where[i][0] / Q, where[i][1] / Q], "cm": round(float(moved[i]) * 100, 1), "by": str(lab[i])} for i in worst.tolist()]
    return rep


def measures(V, F, cls, box):
    """What stands in a box (x0, y0, x1, y1) of a mesh (V mm): the steps' walls by height, the steep faces that are no
    wall, the area per class."""
    import ground_mesh as gm
    P = V[F] / Q
    cen = P.mean(1)
    m = (cen[:, 0] >= box[0]) & (cen[:, 0] <= box[2]) & (cen[:, 1] >= box[1]) & (cen[:, 1] <= box[3])
    P, c = P[m], cls[m]
    wall = c == gm.CLASS_IDS["wall"]
    out = {"triangles": int(m.sum())}
    # a wall stands on one edge in the plane: the edge's length, and its height the taller of its two ends (whichever
    # way its triangles cut it)
    ends = {}
    for tri in np.round(P[wall] * Q).astype(np.int64).tolist():
        at = {}
        for x, y, z in tri:
            at.setdefault((x, y), []).append(z)
        if len(at) != 2:
            continue
        e = ends.setdefault(tuple(sorted(at)), {})
        for p, zs in at.items():
            lo, hi = e.get(p, (zs[0], zs[0]))
            e[p] = (min(lo, *zs), max(hi, *zs))
    run = np.array([np.hypot(a[0] - b[0], a[1] - b[1]) / Q for a, b in ends])
    rise = np.array([max(hi - lo for lo, hi in e.values()) / Q for e in ends.values()])
    out["walls"] = {"m": round(float(run.sum()), 1), "tallest m": round(float(rise.max()), 2) if len(rise) else 0.0,
                    **{f"m over {b} m": round(float(run[rise > b].sum()), 1) if len(rise) else 0.0 for b in WALL_BANDS}}
    G = P[~wall]
    n = np.cross(G[:, 1] - G[:, 0], G[:, 2] - G[:, 0])
    area = np.abs(n[:, 2]) / 2
    slope = np.hypot(n[:, 0], n[:, 1]) / np.maximum(np.abs(n[:, 2]), 1e-12)
    names = {i: k for k, i in gm.CLASS_IDS.items()}
    out["steep faces that are no wall"] = {
        "m2 in plan": round(float(area[slope > STEEP].sum()), 1), "triangles": int((slope > STEEP).sum()),
        "by class": {names[int(i)]: round(float(area[(slope > STEEP) & (c[~wall] == i)].sum()), 1)
                     for i in np.unique(c[~wall][slope > STEEP]).tolist()}}
    out["m2 by class"] = {names[int(i)]: round(float(area[c[~wall] == i].sum()), 1) for i in np.unique(c[~wall]).tolist()}
    return out


def by_class(V, F, cls):
    import ground_mesh as gm
    return V / Q, {c: F[cls == i] for c, i in gm.CLASS_IDS.items()}


def run(name, pl, ring=1, mesh=None, threads=4, out=None, log=print, rings=False):
    """One place built, compared and measured: its report (also written to reports/places/NAME/place.json)."""
    import ground_mesh as gm
    ln, at, reach = str(pl["line"]), pl["at"], float(pl.get("reach") or REACH)
    mid, within = tiles_of(at, reach, ring)
    box = (at[0] - reach, at[1] - reach, at[0] + reach, at[1] + reach)
    t0 = time.time()
    built = gm.build(ln, mesh, threads, log=lambda s: None, within=within)
    gm.fit_mouths(ln, built, log=lambda s: None)
    secs = time.time() - t0
    mine, theirs = middle(built, mid), written(ln, mid)
    rep = {"place": name, "line": ln, "at": at, "reach": reach, "issue": pl.get("issue"),
           "tiles": [tile_name(e, n) for e, n in mid], "ring": ring, "seconds": round(secs, 1),
           "built": measures(*mine, box)}
    if theirs is not None:
        rep["written"] = measures(*theirs, box)
        rep["locality"] = locality(mine, theirs, built.get("corners"))
    if rings:  # (the same tools with one ring more: what in the middle depends on what lies past the ring)
        wider = gm.build(ln, mesh, threads, log=lambda s: None, within=tiles_of(at, reach, ring + 1)[1])
        gm.fit_mouths(ln, wider, log=lambda s: None)
        rep["rings"] = locality(mine, middle(wider, mid), built.get("corners"))
        rep["seconds with the wider ring"] = round(time.time() - t0, 1)
    out = out or os.path.join(ROOT, "reports", "places", name)
    os.makedirs(out, exist_ok=True)
    px = max(2, min(8, int(900 / (2 * reach))))
    gm.picture(ln, box, os.path.join(out, "built.png"), px, by_class(*mine))
    if theirs is not None:
        gm.picture(ln, box, os.path.join(out, "written.png"), px, by_class(*theirs))
    with open(os.path.join(out, "place.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, indent=1, ensure_ascii=False)
    log(line_of(rep))
    return rep


def line_of(rep):
    b, w, loc = rep["built"], rep.get("written"), rep.get("locality")
    s = (f"{rep['place']} (line {rep['line']}, {rep['at'][0]:.0f}, {rep['at'][1]:.0f}, #{rep['issue']}): {rep['seconds']:.0f} s; "
         f"walls over 0.3 m {b['walls']['m over 0.3 m']} m, tallest {b['walls']['tallest m']} m; "
         f"steep faces {b['steep faces that are no wall']['m2 in plan']} m2")
    if w:
        s += f" (written: {w['walls']['m over 0.3 m']} m, {w['walls']['tallest m']} m, {w['steep faces that are no wall']['m2 in plan']} m2)"
    if loc:
        p = loc["points at another height"]
        s += (f"; locality {loc['same %']} %: {p['points']} points at another height (max {p['max cm']} cm), "
              f"{loc['triangles']['only built']} triangles cut another way")
    if rep.get("rings"):
        p, r = rep["rings"]["points at another height"], rep["rings"]
        s += (f"; against one ring more {r['same %']} %: {p['points']} points at another height (max {p['max cm']} cm), "
              f"{r['triangles']['only built']} triangles cut another way")
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--line")
    ap.add_argument("--at", help="X,Y of a place not in the list (with --line)")
    ap.add_argument("--reach", type=float)
    ap.add_argument("--ring", type=int, default=1)
    ap.add_argument("--rings", action="store_true", help="also build with one ring more and compare the two")
    ap.add_argument("--mesh")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args(argv)
    known = places()
    if a.list:
        for k, v in known.items():
            print(f"{k}: line {v['line']} ({v['at'][0]}, {v['at'][1]}), reach {v.get('reach') or REACH} m, #{v.get('issue')}: {v.get('what', '')}")
        return 0
    todo = {}
    if a.at:
        x, y = (float(v) for v in a.at.split(","))
        todo[f"line{a.line}_{x:.0f}_{y:.0f}"] = {"line": a.line, "at": [x, y], "reach": a.reach, "issue": None}
    for k in (known if a.all else a.names):
        if k not in known:
            raise SystemExit(f"ground_place: no place {k} in data/truth.json groundPlaces (--list)")
        todo[k] = dict(known[k], **({"reach": a.reach} if a.reach else {}))
    if not todo:
        ap.error("a place's name, --all, --list, or --line with --at")
    if len(todo) == 1 and not a.rings:
        for k, v in todo.items():
            run(k, v, a.ring, a.mesh, a.threads)
        return 0
    from baseline_store import HeavyJob
    with HeavyJob("ground places", share={"gb": 5 if a.rings else 3, "cores": a.threads}):
        for k, v in todo.items():
            run(k, v, a.ring, a.mesh, a.threads, rings=a.rings)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
