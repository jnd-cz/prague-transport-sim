"""The inside of the survey's ground-level areas that have heights only on their outline, and the ground under the decks
(#444, part of #276's partition). Read by tools/dtm.py.

The survey draws an area as its outline, with heights from its 3D lines. A street is dense with them (kerbs, edges) and
its sheet between them is the street; a railway yard, a lawn or a paved yard has them only round its edge, and a sheet
between them misses the ground inside: on the five lines 5-53 % of the inside of `rail`, 22-29 % of `green` and 7-19 %
of `paved` lies more than 1 m off IPR's lidar, against 0-4 % for the street classes (tools/bench/ground_inside.py,
2026-11-11). Such an area takes the lidar inside: it is marked `g`, and the page drapes it on its terrain
(src/terrain.js DtmSurface: its triangles split to 5 m, the new points inside on the lidar, the outline keeping the
survey's heights; #276's ground built offline will cut the terrain mesh by it instead: on line 37 that mesh as JSON was
750,000 triangles and 24 MB more):
- a lawn always, as main's page draped every lawn, unless the rails, DMR 5G or the user hold it off IPR (HELD; the
  drape's points inside also let the page lay a lawn by a grass track to its bed: left a sheet, lawns covered the rails
  on line 22 and let the terrain through on line 17);
- a railway yard or a paved yard where it lies open on IPR's ground (DRAPE: zps_ground's verdict within its OFFSET of
  IPR, moved there, or off it unevenly along walls and slopes) and its sheet misses the ground (MISS). A sheet that fits
  stays, smooth: a paved yard draped on the lidar's 2 m terrain in 5 m triangles counts as waves on a street. The
  uneven ones measured, their inside beyond 1 m of IPR as a sheet and draped: paved 46 % and 17 % (220,000 m²), rail
  30 % and 1.7 % (green 54 % and 8.7 %). One too small for the lidar to see (a planter, a raised bed: #446) or under a
  cover (IPR interpolated under a wide deck, or the cover itself) keeps its sheet.

Under a deck: where an OSM tunnel or covered way passes under the decks (tools/zps_decks.py openings) and IPR shows its
floor (flatten's gap, WALK or more), the survey's ground-level street of the passage shares its 3D lines with the deck
and alternates between its top and the floor (Divadelní: the road at the deck's height at both portals). Its vertices
standing at the deck take IPR's ground (under_decks). Elsewhere under a level-1 area the survey's ground level
stays: IPR is interpolated under wide decks (by Hlavní nádraží the forecourt's paving at 209-210 m over IPR's
201-205 m) or reads the cover (stairs at 185 m under a deck at 189.6 m, IPR 189.5 m), and of the 14,235 ground-level outline vertices under level-1 areas on the
five lines the middle half lie within -0.25 / +0.12 m of IPR.
"""
import numpy as np
import shapely

INSIDE = {"rail", "green", "paved"}  # the classes with heights only on their outline (measured above)
DRAPE = {"fits", "lidar", "uneven"}  # zps_ground.judge's verdicts of an area lying open on IPR's ground
HELD = {"survey", "review", "changing"}  # its verdicts holding an area off IPR (the rails, DMR 5G, the user; a building site)
# m: the sheet misses the ground where the 95th percentile of |sheet - IPR| inside is over this (zps_ground's OFFSET);
# a sheet that fits stays (a paved yard draped on the lidar's 2 m terrain in 5 m triangles counted 8 cm waves the
# street check reads: line 9's streetWaviness 2348 -> 2617 with every open area draped)
MISS = 0.5
STEP, INSET = 2.0, 0.5  # m: the lattice inside an area where its sheet is compared with IPR, and its distance off the outline
REACH = 0.5  # m round an opening's streets: their vertices at its edge (the portals)
PLUG = 1.0  # m under the deck's top: a ground-level vertex this high stands at the deck, not on the floor under it
ALONG, ALONG_RATIO = np.radians(30), 1.5  # an area runs along the way: within this angle, this elongated
AROUND = 20.0  # m round the way's axis: where an area's direction is read
MIN_AXIS = 5.0  # m of the way under the decks: a shorter stub has no direction to read
WALK = 2.2  # m under the deck's top: IPR this low shows the floor at the vertex (tools/zps_decks.py WALK); higher, the cover


def filled(ring, ground):
    """The ring (n, 3) with its heights, a missing one from its nearest neighbour on the ring, else the ground (as the
    page fills them)."""
    r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in ring], float)
    ok = np.flatnonzero(np.isfinite(r[:, 2]))
    for i in np.flatnonzero(~np.isfinite(r[:, 2])):
        if len(ok):
            d = np.minimum(np.abs(ok - i), len(r) - np.abs(ok - i))
            r[i, 2] = r[ok[np.argmin(d)], 2]
        else:
            r[i, 2] = np.asarray(ground(r[i:i + 1, 0], r[i:i + 1, 1]), float)[0]
    return r


def triangulate(rings):
    """(n, 3, 3) triangles of the linear sheet over an outline and its holes ((m, 3) arrays): shapely's constrained
    Delaunay (#276's T2; the page's earcut keeps the same outline)."""
    try:
        poly = shapely.Polygon(rings[0], rings[1:])
        if not poly.is_valid:
            poly = shapely.make_valid(poly)
        tris = shapely.constrained_delaunay_triangles(poly)
    except shapely.errors.GEOSException:
        return np.zeros((0, 3, 3))
    out = [shapely.get_coordinates(t, include_z=True)[:3] for t in shapely.get_parts(tris)]
    out = [t for t in out if t.shape == (3, 3) and np.isfinite(t).all()]
    return np.array(out, float) if out else np.zeros((0, 3, 3))


def at(tris, x, y):
    """Heights of a surface of triangles (n, 3, 3) at points (NaN off it): the first triangle holding each, barycentric."""
    z = np.full(len(x), np.nan)
    if not len(tris) or not len(x):
        return z
    tree = shapely.STRtree(shapely.polygons(tris[:, :, :2]))
    pi, ti = tree.query(shapely.points(x, y), predicate="intersects")
    t = tris[ti]
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = (t[:, k].T for k in range(3))
    d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    ok = np.abs(d) > 1e-12
    d = np.where(ok, d, 1)
    w0 = ((y1 - y2) * (x[pi] - x2) + (x2 - x1) * (y[pi] - y2)) / d
    w1 = ((y2 - y0) * (x[pi] - x2) + (x0 - x2) * (y[pi] - y2)) / d
    zz = w0 * z0 + w1 * z1 + (1 - w0 - w1) * z2
    first = np.r_[True, pi[1:] != pi[:-1]] & ok
    z[pi[first]] = zz[first]
    return z


def lattice(poly, step=STEP):
    """Points every `step` m inside a polygon, INSET m or more off its outline."""
    x0, y0, x1, y1 = poly.bounds
    xs, ys = np.meshgrid(np.arange(np.floor(x0 / step) * step + step / 2, x1, step),
                         np.arange(np.floor(y0 / step) * step + step / 2, y1, step))
    xs, ys = xs.ravel(), ys.ravel()
    inner = poly.buffer(-INSET)
    keep = shapely.contains_xy(inner, xs, ys) if not inner.is_empty else np.zeros(len(xs), bool)
    return xs[keep], ys[keep]


def misses(a, ground):
    """How far the area's sheet misses the ground inside it: the 95th percentile of |sheet - IPR| on the lattice, or
    None where no point of the lattice lies in it (a narrow or small area)."""
    rings = [filled(a["r"], ground)] + [filled(h, ground) for h in a.get("h", []) if len(h) >= 3]
    poly = shapely.Polygon(rings[0][:, :2], [r[:, :2] for r in rings[1:]]).buffer(0)
    x, y = lattice(poly)
    if not len(x):
        return None
    d = np.abs(at(triangulate(rings), x, y) - np.asarray(ground(x, y), float))
    d = d[np.isfinite(d)]
    return float(np.percentile(d, 95)) if len(d) else None


def inside(areas, verdicts, ground):
    """The areas of INSIDE classes that take the lidar inside (in place: `g` 1): lawns unless HELD, railway and paved
    yards open on IPR's ground whose sheet misses it. verdicts: zps_ground.judge's; ground: IPR at city-frame arrays.
    Returns {"classes": {class: {"areas", "m2"}}, "fit": {class: areas whose sheet fits}, "kept": {verdict: areas}}."""
    out = {"classes": {}, "fit": {}, "kept": {}}
    for i, a in enumerate(areas):
        if a["l"] != 0 or a["c"] not in INSIDE or len(a["r"]) < 3:
            continue
        v = verdicts.get(i, {})
        verdict = v.get("verdict")
        if verdict in HELD or (a["c"] != "green" and verdict not in DRAPE):
            k = verdict or "none"
            out["kept"][k] = out["kept"].get(k, 0) + 1
            continue
        if a["c"] != "green":
            miss = misses(a, ground)
            if miss is None or miss <= MISS:
                out["fit"][a["c"]] = out["fit"].get(a["c"], 0) + 1
                continue
        a["g"] = 1
        c = out["classes"].setdefault(a["c"], {"areas": 0, "m2": 0.0})
        c["areas"] += 1
        c["m2"] += v.get("m2", 0.0)
    for c in out["classes"].values():
        c["m2"] = round(c["m2"])
    return out


def _bearing(g):
    """The direction (radians, modulo pi) of a geometry's longest extent and its elongation (long / short side of its
    minimum rotated rectangle)."""
    rect = shapely.minimum_rotated_rectangle(g)
    if rect.is_empty or rect.geom_type != "Polygon":  # (a line, a point: no extent across)
        c = shapely.get_coordinates(rect)
        if len(c) < 2:
            return 0.0, 0.0
        return float(np.arctan2(c[-1, 1] - c[0, 1], c[-1, 0] - c[0, 0]) % np.pi), float("inf")
    c = np.asarray(rect.exterior.coords)[:4]
    e = np.diff(np.vstack([c, c[:1]]), axis=0)[:2]
    n = np.hypot(e[:, 0], e[:, 1])
    k = int(np.argmax(n))
    return float(np.arctan2(e[k, 1], e[k, 0]) % np.pi), float(n.max() / max(n.min(), 1e-6))


def _deck_top(areas, decks):
    """The decks' surface: z at points (the linear sheet over their outlines, constrained Delaunay), NaN off them."""
    tris = []
    for i in decks:
        r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in areas[i]["r"]], float)
        if len(r) < 3 or not np.isfinite(r[:, 2]).all():
            continue
        p = shapely.Polygon(r).buffer(0) if not shapely.Polygon(r).is_valid else shapely.Polygon(r)
        for t in shapely.get_parts(shapely.constrained_delaunay_triangles(p)):
            c = shapely.get_coordinates(t, include_z=True)[:3]
            if c.shape == (3, 3) and np.isfinite(c).all():
                tris.append(c)
    tris = np.array(tris, float)

    def at(x, y):
        z = np.full(len(x), np.nan)
        if not len(tris):
            return z
        tree = shapely.STRtree(shapely.polygons(tris[:, :, :2]))
        pi, ti = tree.query(shapely.points(x, y), predicate="intersects")
        t = tris[ti]
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = (t[:, k].T for k in range(3))
        d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        d = np.where(np.abs(d) > 1e-12, d, 1e-12)
        w0 = ((y1 - y2) * (x[pi] - x2) + (x2 - x1) * (y[pi] - y2)) / d
        w1 = ((y2 - y0) * (x[pi] - x2) + (x0 - x2) * (y[pi] - y2)) / d
        zz = w0 * z0 + w1 * z1 + (1 - w0 - w1) * z2
        np.fmax.at(z, pi, zz)  # (the top one where decks overlap)
        return z
    return at


def under_decks(areas, opens, flat, ground):
    """In each opening whose floor IPR shows, the ground-level areas that run along the way under the decks (the street
    of the passage, its sidewalks and kerbs) take IPR's ground at their vertices that stand at the deck (within PLUG under
    its top or over it: the survey's lines shared with the deck). An area across the way is the one over the passage at
    grade (the tram over a footway's underpass at the east end of line 37: its vertices at the rails' top, IPR 2.3-4.2 m
    under them), a vertex well under the deck is the survey's floor, and one where IPR stands within WALK of the deck's top
    reads the cover there (the forecourt by Hlavní nádraží): all stay. In place. opens: zps_decks.openings;
    flat: zps_decks.flatten's record (its "openings": the gap per way); ground: IPR at city-frame arrays.
    Returns {"openings": n, "areas": n, "vertices": n, "moved": [p5, p50, p95 of the moves]}."""
    seen = {o["way"] for o in flat["openings"] if o.get("gap") is not None and o.get("src") != "unseen"}
    out = {"openings": 0, "areas": 0, "vertices": 0, "moved": []}
    moves, touched = [], set()
    for o in opens:
        if o["way"] not in seen or o["poly"].is_empty or o["axis"].length < MIN_AXIS:
            continue
        out["openings"] += 1
        cover = o["poly"].buffer(REACH)
        way_dir, _ = _bearing(o["axis"].buffer(0.5))
        top = _deck_top(areas, o["decks"])
        for ai, a in enumerate(areas):
            if a["l"] != 0 or a["c"] in ("wall", "roof", "water") or len(a["r"]) < 3:
                continue
            poly = shapely.Polygon([q[:2] for q in a["r"]]).buffer(0)
            if poly.intersection(cover).area < 1:
                continue
            # (its direction round the way, not within the opening: a piece cut by a strip along the way runs along it)
            d, elong = _bearing(poly.intersection(o["axis"].buffer(AROUND)))
            off = min(abs(d - way_dir), np.pi - abs(d - way_dir))
            if elong < ALONG_RATIO or off > ALONG:
                continue
            for ring in [a["r"]] + a.get("h", []):
                r = np.array([[q[0], q[1], np.nan if q[2] is None else q[2]] for q in ring], float)
                hit = np.flatnonzero(shapely.contains_xy(cover, r[:, 0], r[:, 1]))
                if not len(hit):
                    continue
                t = top(r[hit, 0], r[hit, 1])
                g = np.asarray(ground(r[hit, 0], r[hit, 1]), float)
                for i, zt, zg in zip(hit, t, g):
                    z0 = r[i, 2]
                    if not np.isfinite(zg) or not np.isfinite(zt) or (np.isfinite(z0) and z0 < zt - PLUG) or zg > zt - WALK:
                        continue
                    if np.isfinite(z0):
                        moves.append(zg - z0)
                    ring[i][2] = round(float(zg), 2)
                    out["vertices"] += 1
                    touched.add(ai)
    out["areas"] = len(touched)
    out["moved"] = [round(float(v), 2) for v in np.percentile(moves, [5, 50, 95])] if moves else []
    return out
