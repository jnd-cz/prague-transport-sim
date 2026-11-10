"""IPR's 1 m terrain against ČÚZK DMR 5G: where the two lidar models disagree, and what the passages rule takes (#428).

    python -P -E tools/bench/terrain_compare.py [--step 2] [--partial]   # the city-wide comparison
    python -P -E tools/bench/terrain_compare.py --passages               # the passages rule's cells, by class

The comparison takes IPR's raster every --step cells (2 m) against DMR 5G bilinear at the same cell centres, where both
have ground (tools/sources.py TERRAIN_FLOOR). It needs the DMR 5G tiles under IPR's coverage (python -P -E tools/dmr5g.py
--under-ipr; --partial compares where tiles are at hand). Cells within dmr5g.PASSAGE_R of an OSM passage are left out,
and those in OSM building footprints and on OSM water are counted apart (both models interpolate under a building;
over water they show different surfaces). It reports the difference per district, the area over 0.5 / 1 / 2 / 5 m, and
the largest connected areas over 1 m on land with what OSM maps there, and draws a map of the city and a panel per top
area. 5 GB and ~4 min at 2 m: it takes a turn among the heavy jobs (baseline_store.HeavyJob).

--passages runs the rule as tools/city_terrain.py does (inside the city, near an OSM passage, a DMR 5G tile of the
snapshot at hand, IPR more than PASSAGE_DROP under DMR 5G) and splits its cells by the class of the nearest passage
(tunnel=building_passage, other tunnels by what they carry, culverts, covered=yes, layer<0 only): the jump it makes,
how much lies in OSM building footprints and in the LOD2 buildings at hand (data/line*.bld.bin, 110 m around the
lines), and panels of chosen places (IPR and DMR 5G hillshades, IPR - DMR 5G, the ways, the outlines, the cells taken).

Writes reports/city-terrain/ compare.json, compare-map.png, compare-NN.png; passages.json, passages-NN.png.
"""
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import city_terrain as ct  # noqa: E402
import dmr5g  # noqa: E402
from sources import TERRAIN_FLOOR  # noqa: E402

OUT = os.path.join(ROOT, "reports", "city-terrain")
LOD2_REACH = 110.0  # m: the LOD2 buildings at hand lie this near a line's route (tools/geoportal.py)
OVER = (0.5, 1.0, 2.0, 5.0)  # m: |IPR - DMR 5G| thresholds
BLOCK = 5  # comparison cells: the connected areas are found on blocks of 5 x 5 (10 m at --step 2)


def polylines(arrs):
    """Shapely line strings of coordinate arrays of different lengths."""
    import shapely
    return np.array([shapely.LineString(a) for a in arrs], dtype=object)


def mapy(lat, lon):
    return f"https://mapy.cz/letecka?x={lon:.6f}&y={lat:.6f}&z=19"


def snapshot_tiles():
    """The DMR 5G tiles (ix, iy) the current snapshot holds."""
    sid = open(os.path.join(ROOT, "snapshots", "CURRENT"), encoding="utf-8").read().strip()
    snap = json.load(open(os.path.join(ROOT, "snapshots", f"{sid}.json"), encoding="utf-8"))
    out = set()
    for g in snap["groups"]:
        for f in g["files"]:
            p = f["path"]
            if p.startswith("raw/dem/") and p.endswith(".tif"):
                ix, iy = os.path.basename(p)[:-4].split("_")
                out.add((int(ix), int(iy)))
    return sid, out


def sample(dem, E, N, allowed=None):
    """DMR 5G bilinear at S-JTSK points, NaN where no tile is at hand (or not in `allowed`) or under the floor; the
    points grouped by tile once (dmr5g.Tiles.sample scans all points per tile)."""
    shape, E, N = E.shape, E.ravel(), N.ravel()
    out = np.full(E.shape, np.nan, np.float32)
    ix, iy = np.floor(E / dmr5g.TILE).astype(np.int64), np.floor(N / dmr5g.TILE).astype(np.int64)
    key = (ix + (1 << 16)) * (1 << 18) + iy + (1 << 16)
    order = np.argsort(key, kind="stable")
    ks = key[order]
    cuts = np.flatnonzero(np.diff(ks)) + 1
    for part in np.split(order, cuts):
        t = (int(ix[part[0]]), int(iy[part[0]]))
        if (allowed is not None and t not in allowed) or not dem.have(*t):
            continue
        out[part] = dem.sample(E[part], N[part])
    out[~(out >= TERRAIN_FLOOR)] = np.nan
    return out.reshape(shape)


def ipr_cells(ipr, cols, rows):
    """IPR's cells at raster columns, rows (arrays inside the image), NaN where no ground; tile by tile."""
    out = np.full(cols.shape, np.nan, np.float32)
    key = (rows // ipr.th) * ipr.ntx + cols // ipr.tw
    order = np.argsort(key, kind="stable")
    cuts = np.flatnonzero(np.diff(key[order])) + 1
    for part in np.split(order, cuts):
        tx, ty = int(cols[part[0]] // ipr.tw), int(rows[part[0]] // ipr.th)
        a = ipr.decode(tx, ty)
        out[part] = a[rows[part] - ty * ipr.th, cols[part] - tx * ipr.tw]
    out[~(out >= TERRAIN_FLOOR)] = np.nan
    return out


def kind(t):
    """The class of an OSM passage (dmr5g.passage's tags)."""
    tun = t.get("tunnel", "no")
    if tun == "building_passage":
        return "building_passage"
    if tun == "culvert" or t.get("culvert") == "yes":
        return "culvert"
    if tun != "no":
        if t.get("waterway"):
            return "tunnel: waterway"
        if t.get("railway"):
            return "tunnel: railway"
        if t.get("highway") in ("footway", "path", "steps", "pedestrian", "cycleway", "corridor"):
            return "tunnel: footway"
        if t.get("highway"):
            return "tunnel: highway"
        return "tunnel: other"
    if t.get("covered") == "yes":
        return "covered"
    return "layer<0 only"


LIFECYCLE = ("proposed", "construction", "abandoned", "disused", "razed")


def unbuilt(t):
    """An OSM way that is no passage on the ground yet or any more: proposed, under construction, abandoned."""
    return any(t.get(k) in LIFECYCLE for k in ("railway", "highway", "waterway")) or any(k in t for k in LIFECYCLE)


def passages(F):
    """OSM passage ways (dmr5g.passage) in the city frame: [(id, tags, class, xy (n, 2))]."""
    import osm_local
    out = []
    for w in osm_local.ways(dmr5g.passage):
        x, y = F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]])
        out.append((w["id"], w["tags"], kind(w["tags"]), np.column_stack([x, y])))
    return out


HALF = {**{k: 6.0 for k in ("motorway", "trunk", "primary", "secondary", "tertiary", "motorway_link", "trunk_link",
                             "primary_link", "secondary_link", "tertiary_link")},
        **{k: 4.0 for k in ("residential", "unclassified", "living_street", "service", "pedestrian", "road", "busway")},
        **{k: 1.5 for k in ("footway", "path", "steps", "cycleway", "bridleway", "track", "corridor")}}
RAIL = {"rail": 2.0, "tram": 2.0, "light_rail": 2.0, "narrow_gauge": 2.0, "funicular": 2.0}
DECKS = ("track (DI)", "rail", "street", "footway", "building", "none")  # (what lies over a cell, first that applies)


def deck_ways(F):
    """OSM highways and railways that are no passage (at the surface or over it): [(kind, half width, xy)]."""
    import osm_local
    out = []
    for w in osm_local.ways(lambda t: (t.get("highway") in HALF or t.get("railway") in RAIL) and not dmr5g.passage(t)):
        t = w["tags"]
        x, y = F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]])
        if t.get("railway") in RAIL:
            kind, half = "rail", RAIL[t["railway"]]
        else:
            kind, half = ("footway" if HALF[t["highway"]] < 2 else "street"), HALF[t["highway"]]
        out.append((kind, half, np.column_stack([x, y])))
    return out


def decks(x, y, ways, track_dist, in_building):
    """What lies over each point: a DI track within 2 m, else an OSM railway, street or footway within its half width,
    else a building, else none (DECKS index)."""
    import shapely
    pts = shapely.points(x, y)
    lines = polylines([w[2] for w in ways])
    i, j = shapely.STRtree(lines).query(pts, predicate="dwithin", distance=max(HALF.values()))
    ok = shapely.distance(pts[i], lines[j]) <= np.array([w[1] for w in ways])[j]
    i, j = i[ok], j[ok]
    out = np.full(len(x), DECKS.index("none"))
    out[in_building] = DECKS.index("building")
    for kind in ("footway", "street", "rail"):
        hit = i[np.array([ways[k][0] == kind for k in j], bool)] if len(j) else i[:0]
        out[hit] = DECKS.index(kind)
    out[track_dist <= 2.0] = DECKS.index("track (DI)")
    return out


def survey_areas():
    """The street survey's areas in the lines' corridors (data/line*.dtm.json): [(class, level, xyz (n, 3))]."""
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if f.endswith(".dtm.json"):
            for a in json.load(open(os.path.join(ROOT, "data", f), encoding="utf-8")).get("areas", []):
                if len(a["r"]) >= 3:
                    out.append((a.get("c", "?"), a.get("l", 0), np.array(a["r"], np.float64)))
    return out


def line_heights():
    """Per line and direction: the path (n, 2), its distance along, its top-of-rail heights every `step` m and their
    sources as spans [s0, s1, source] (tools/line_heights.py)."""
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if f.startswith("line") and f.endswith(".json") and f[4:-5].isdigit():
            ln = json.load(open(os.path.join(ROOT, "data", f), encoding="utf-8"))
            h, src = ln.get("heights") or {}, ln.get("heightSource") or {}
            for k in ("path", "pathBack"):
                if ln.get(k) and h.get(k):
                    xy = np.array([q[:2] for q in ln[k]], np.float64)
                    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
                    out.append((f[4:-5], k, xy, s, h[k], h.get("step", 2.0), src.get(k, [])))
    return out


def osm_areas(F):
    """OSM areas by what they are (buildings, water, quarries, landfills, construction, forest, railway land, bridges),
    city frame: {category: [(outer, xy (n, 2))]}, each area's outer rings before its inner ones."""
    import osmium
    import osm_local

    def category(t):
        if t.get("building") and t.get("building") != "no":
            return "building"
        lu, nat = t.get("landuse"), t.get("natural")
        if nat == "water" or t.get("waterway") in ("riverbank", "dock") or lu in ("reservoir", "basin"):
            return "water"
        if lu in ("quarry", "landfill"):
            return lu
        if lu in ("construction", "brownfield"):
            return "construction"
        if lu == "forest" or nat in ("wood", "scrub"):
            return "forest"
        if lu == "railway":
            return "railway"
        if t.get("man_made") == "bridge":
            return "bridge"
        return None
    rings, ll = [], []
    for o in osmium.FileProcessor(osm_local.PRAHA).with_areas(
            osmium.filter.KeyFilter("building", "landuse", "natural", "waterway", "man_made")):
        if not o.is_area():
            continue
        c = category(dict(o.tags))
        if not c:
            continue
        for r in o.outer_rings():
            for outer, ring in [(True, r)] + [(False, i) for i in o.inner_rings(r)]:
                pts = [(n.lat, n.lon) for n in ring]
                rings.append((c, outer, len(ll), len(ll) + len(pts)))
                ll += pts
    a = np.array(ll, np.float64)
    x, y = F.xy(a[:, 0], a[:, 1])
    xy = np.column_stack([x, y])
    out = {}
    for c, outer, i, j in rings:
        out.setdefault(c, []).append((outer, xy[i:j]))
    return out


def paint_rings(rings, shape, origin, step=1.0):
    """bool (rows, cols) of a grid of `step` m cells from (origin) whose centre lies in the rings' areas."""
    from PIL import Image, ImageDraw
    h, w = shape
    im = Image.new("1", (w, h), 0)
    d = ImageDraw.Draw(im)
    ox, oy = origin
    for outer, xy in rings:
        if len(xy) >= 3:
            d.polygon([((x - ox) / step, (oy - y) / step) for x, y in xy], fill=1 if outer else 0)
    return np.asarray(im, dtype=bool)


def lod2_triangles(kind=0):
    """The LOD2 buildings' triangles at hand (data/line*.bld.bin; kind 0 buildings, 1 Mosty 3D's bridges), city frame:
    (m, 3, 2)."""
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if not f.endswith(".geo.json"):
            continue
        b = json.load(open(os.path.join(ROOT, "data", f), encoding="utf-8")).get("buildings")
        if not b:
            continue
        raw = np.fromfile(os.path.join(ROOT, "data", b["file"]), "<i2").reshape(-1, 3).astype(np.float64) * b["q"]
        for ch in b["chunks"]:
            v = raw[ch["v"]:ch["v"] + ch["n"], :2] + ch["o"][:2]
            kinds = ch.get("k", [0] * len(ch["b"]))
            s = 0
            for n, k in zip(ch["b"], kinds):
                if k == kind:
                    out.append(v[s:s + n].reshape(-1, 3, 2))
                s += n
    return np.concatenate(out) if out else np.zeros((0, 3, 2))


def line_paths():
    out = []
    for f in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if f.startswith("line") and f.endswith(".json") and f[4:-5].isdigit():
            ln = json.load(open(os.path.join(ROOT, "data", f), encoding="utf-8"))
            for k in ("path", "pathBack"):
                if ln.get(k):
                    out.append(np.array([p[:2] for p in ln[k]], np.float64))
    return out


# ---------------------------------------------------------------- pictures
def hillshade(z, az=315.0, alt=45.0):
    gy, gx = np.gradient(np.where(np.isnan(z), np.nanmean(z) if np.isfinite(z).any() else 0, z))
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, b = math.radians(az), math.radians(alt)
    s = np.sin(b) * np.cos(slope) + np.cos(b) * np.sin(slope) * np.cos(a - aspect)
    g = np.clip(255 * (0.15 + 0.85 * np.clip(s, 0, 1)), 0, 255).astype(np.uint8)
    rgb = np.stack([g, g, g], -1)
    rgb[np.isnan(z)] = (255, 240, 240)
    return rgb


def diverging(d, lim):
    """Blue where IPR lies under DMR 5G, red where over, white at 0; `lim` m saturates."""
    t = np.clip(np.nan_to_num(d) / lim, -1, 1)
    r = np.where(t < 0, 1 + t, 1.0)
    g = 1 - np.abs(t)
    b = np.where(t > 0, 1 - t, 1.0)
    rgb = (np.stack([r * 0.95 + 0.05 * (t > 0), g, b * 0.95 + 0.05 * (t < 0)], -1) * 255).astype(np.uint8)
    rgb[np.isnan(d)] = (200, 200, 200)
    return rgb


def font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def near(rings, ctx, key, box):
    """The rings' coordinates whose bounds meet box (minx, miny, maxx, maxy); the bounds kept in ctx[key]."""
    if key not in ctx:
        ctx[key] = np.array([(xy[:, 0].min(), xy[:, 1].min(), xy[:, 0].max(), xy[:, 1].max()) for _, xy in rings]).reshape(-1, 4)
    b = ctx[key]
    hit = np.flatnonzero((b[:, 2] >= box[0]) & (b[:, 0] <= box[2]) & (b[:, 3] >= box[1]) & (b[:, 1] <= box[3]))
    return [rings[i][1] for i in hit]


def panel(path, ctx, cx, cy, size, title, lines=(), taken=None, lim=3.0, px=450):
    """Three views of a square of `size` m around (cx, cy) in the city frame: IPR's hillshade, DMR 5G's, IPR - DMR 5G
    (blue under, red over, +-lim m), with OSM building outlines (black), passages (magenta) and the cells taken
    (`taken`: (x, y) cell centres, outlined in green)."""
    from PIL import Image, ImageDraw
    ipr, F, dem, osm, ways = ctx["ipr"], ctx["F"], ctx["dem"], ctx["osm"], ctx["ways"]
    n = int(size)
    e0, n0 = cx + F.E0 - size / 2, cy + F.N0 + size / 2
    c0, r0 = int(math.floor(e0 - ipr.e0)), int(math.floor(ipr.n0 - n0))
    cols, rows = np.meshgrid(np.arange(c0, c0 + n), np.arange(r0, r0 + n))
    ok = (cols >= 0) & (rows >= 0) & (cols < ipr.w) & (rows < ipr.h)
    z0 = np.full(cols.shape, np.nan, np.float32)
    z0[ok] = ipr_cells(ipr, cols[ok], rows[ok])
    E, N = ipr.e0 + cols, ipr.n0 - rows
    z1 = sample(dem, E.astype(np.float64), N.astype(np.float64))
    x0, y0 = ipr.e0 + c0 - F.E0, ipr.n0 - r0 - F.N0  # (city frame of the top-left cell's centre)
    k = px / n
    views = [hillshade(z0), hillshade(z1), diverging(z0 - z1, lim)]
    names = ["IPR 1 m (lidar 2023), hillshade", "DMR 5G (lidar 2009-2013), hillshade", f"IPR - DMR 5G, ±{lim:g} m"]
    W, H = 3 * px + 4 * 12, px + 120
    im = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.text((12, 8), title, fill=(0, 0, 0), font=font(18))

    def pt(x, y, ox):
        return (ox + (x - x0 + 0.5) * k, 44 + (y0 - y + 0.5) * k)
    tset = None
    if taken is not None and len(taken):
        ti = np.round((taken[:, 0] - x0)).astype(int)
        tj = np.round((y0 - taken[:, 1])).astype(int)
        m = (ti >= 0) & (tj >= 0) & (ti < n) & (tj < n)
        tset = np.zeros((n, n), bool)
        tset[tj[m], ti[m]] = True
    for v, (rgb, nm) in enumerate(zip(views, names)):
        ox = 12 + v * (px + 12)
        im.paste(Image.fromarray(rgb).resize((px, px), Image.NEAREST), (ox, 44))
        box = (x0 - 1, y0 - n - 1, x0 + n + 1, y0 + 1)
        for xy in near(osm.get("building", []), ctx, "bld_box", box):
            d.line([pt(x, y, ox) for x, y in xy], fill=(0, 0, 0), width=1)
        for xy in near([(True, w[3]) for w in ways], ctx, "way_box", box):
            d.line([pt(x, y, ox) for x, y in xy], fill=(220, 0, 200), width=3)
        for xy in lines:
            d.line([pt(x, y, ox) for x, y in xy], fill=(0, 140, 0), width=2)
        if tset is not None:  # (the taken cells' outline: cell edges between taken and not)
            jj, ii = np.nonzero(tset[:, 1:] != tset[:, :-1])
            for j, i in zip(jj, ii):
                a, b = pt(x0 + i + 0.5, y0 - j + 0.5, ox), pt(x0 + i + 0.5, y0 - j - 0.5, ox)
                d.line([a, b], fill=(0, 200, 60), width=2)
            jj, ii = np.nonzero(tset[1:, :] != tset[:-1, :])
            for j, i in zip(jj, ii):
                a, b = pt(x0 + i - 0.5, y0 - j - 0.5, ox), pt(x0 + i + 0.5, y0 - j - 0.5, ox)
                d.line([a, b], fill=(0, 200, 60), width=2)
        d.rectangle([ox, 44, ox + px, 44 + px], outline=(0, 0, 0))
        d.text((ox, 44 + px + 6), nm, fill=(0, 0, 0), font=font(15))
    # the colour scale under the third view, and a 50 m bar
    ox = 12 + 2 * (px + 12)
    for i in range(px):
        c = diverging(np.array([[(i / (px - 1) * 2 - 1) * lim]]), lim)[0, 0]
        d.line([(ox + i, 44 + px + 30), (ox + i, 44 + px + 46)], fill=tuple(int(v) for v in c))
    for v in (-lim, -lim / 2, 0, lim / 2, lim):
        x = ox + (v / lim + 1) / 2 * (px - 1)
        d.line([(x, 44 + px + 46), (x, 44 + px + 52)], fill=(0, 0, 0))
        d.text((x - 14, 44 + px + 54), f"{v:+g} m" if v else "0", fill=(0, 0, 0), font=font(13))
    d.text((ox, 44 + px + 76), "blue: IPR under DMR 5G   red: IPR over", fill=(0, 0, 0), font=font(13))
    d.line([(12, 44 + px + 40), (12 + 50 * k, 44 + px + 40)], fill=(0, 0, 0), width=3)
    d.text((12, 44 + px + 46), "50 m", fill=(0, 0, 0), font=font(13))
    d.text((12, 44 + px + 70), "black: OSM buildings   magenta: OSM passages   green outline: cells the rule took",
           fill=(0, 0, 0), font=font(13))
    im.save(path)


# ---------------------------------------------------------------- the passages rule
def audit():
    from geo import Frame
    from ipr_dtm import IprDtm
    import shapely
    t0 = time.time()
    F, ipr = Frame(), IprDtm()
    shape, origin = (ipr.h, ipr.w), (ipr.e0 - F.E0, ipr.n0 - F.N0)
    sid, allowed = snapshot_tiles()
    city, parts = ct.boundaries(F)
    ways = passages(F)
    print(f"{len(ways)} OSM passages, {len(allowed)} DMR 5G tiles in snapshot {sid}, {time.time() - t0:.0f} s", flush=True)
    covers, _ = ct.passage_covers(F, shape, origin, city)
    covers &= ct.paint(city, shape, origin)
    rows, cols = np.nonzero(covers)
    del covers
    E, N = ipr.e0 + cols, ipr.n0 - rows
    tk = (np.floor(E / dmr5g.TILE).astype(np.int64), np.floor(N / dmr5g.TILE).astype(np.int64))
    hand = np.array([t in allowed for t in zip(tk[0].tolist(), tk[1].tolist())])
    rows, cols, E, N = rows[hand], cols[hand], E[hand], N[hand]
    dem = dmr5g.Tiles()
    z0 = ipr_cells(ipr, cols, rows)
    z1 = sample(dem, E.astype(np.float64), N.astype(np.float64), allowed)
    rule = np.isfinite(z0) & np.isfinite(z1) & (z0 < z1 - dmr5g.PASSAGE_DROP)
    rows, cols, z0, z1 = rows[rule], cols[rule], z0[rule], z1[rule]
    x, y = ipr.e0 - F.E0 + cols, ipr.n0 - F.N0 - rows
    print(f"the rule takes {len(rows):,} cells ({len(rows) / 1e6:.3f} km²) of {int(hand.sum()):,} near passages with a "
          f"tile at hand, {time.time() - t0:.0f} s", flush=True)
    # the passage each cell belongs to: the nearest
    tree = shapely.STRtree(polylines([w[3] for w in ways]))
    idx, dist = tree.query_nearest(shapely.points(x, y), return_distance=True, all_matches=False)
    way = np.full(len(x), -1)
    way[idx[0]] = idx[1]
    cls = np.array([ways[i][2] for i in way])
    osm = osm_areas(F)
    in_osm = paint_rings(osm.get("building", []), shape, origin)[rows, cols]
    tri = lod2_triangles()
    from PIL import Image, ImageDraw
    im = Image.new("1", (shape[1], shape[0]), 0)
    dr = ImageDraw.Draw(im)
    ox, oy = origin
    for t in tri:
        dr.polygon([(px_ - ox, oy - py_) for px_, py_ in t], fill=1)
    in_lod2 = np.asarray(im, dtype=bool)[rows, cols]
    del im
    paths = line_paths()
    ptree = shapely.STRtree(polylines(paths))
    _, pd = ptree.query_nearest(shapely.points(x, y), return_distance=True, all_matches=False)
    lod2_here = pd <= LOD2_REACH
    import di_network
    segs = ct.segments(di_network.load_network())
    _, td = shapely.STRtree(shapely.linestrings(segs.reshape(-1, 2, 2))).query_nearest(
        shapely.points(x, y), return_distance=True, all_matches=False)
    jump = z1 - z0
    gone = np.array([unbuilt(ways[i][1]) for i in way])
    dways = deck_ways(F)
    deck = decks(x, y, dways, td, in_osm)
    classes = sorted(set(cls), key=lambda c: -int((cls == c).sum()))
    table = []
    n_ways = {}
    shapely.prepare(city)
    for w, inc in zip(ways, shapely.intersects(city, polylines([w[3] for w in ways]))):
        if inc:
            n_ways[w[2]] = n_ways.get(w[2], 0) + 1
    for c in classes:
        m = cls == c
        lm = m & lod2_here
        table.append({"class": c, "cells": int(m.sum()), "km2": round(int(m.sum()) / 1e6, 4),
                      "share": round(float(m.mean()), 3), "ways_fired": int(len(np.unique(way[m]))),
                      "ways_in_city": n_ways.get(c, 0),
                      "in_osm_buildings": round(float(in_osm[m].mean()), 3),
                      "lod2_at_hand": int(lm.sum()), "in_lod2": round(float(in_lod2[lm].mean()), 3) if lm.any() else None,
                      "jump_m": {"median": round(float(np.median(jump[m])), 2), "p90": round(float(np.percentile(jump[m], 90)), 2),
                                 "max": round(float(jump[m].max()), 2)},
                      "within_3m_of_track": int((td[m] <= 3).sum()), "unbuilt": round(float(gone[m].mean()), 3),
                      "over": {k: round(float((deck[m] == i).mean()), 3) for i, k in enumerate(DECKS)}})
    print(f"{'class':22} {'cells':>8} {'share':>6} {'ways':>9} {'in OSM bld':>10} {'in LOD2':>8} {'jump med/p90/max':>18} {'by track':>8}")
    for r in table:
        print(f"{r['class']:22} {r['cells']:8,} {r['share']:6.1%} {r['ways_fired']:4}/{r['ways_in_city']:<4} "
              f"{r['in_osm_buildings']:10.1%} {('-' if r['in_lod2'] is None else f'{r['in_lod2']:.1%}'):>8} "
              f"{r['jump_m']['median']:5.2f}/{r['jump_m']['p90']:5.2f}/{r['jump_m']['max']:5.2f} {r['within_3m_of_track']:8}  "
              + " ".join(f"{k} {v:.0%}" for k, v in r["over"].items() if v))
    over_all = {k: round(float((deck == i).mean()), 3) for i, k in enumerate(DECKS)}
    print(f"on unbuilt ways (proposed, construction, abandoned, disused): {int(gone.sum()):,} cells "
          f"({gone.mean():.1%})", flush=True)
    print("over the rule's cells: " + ", ".join(f"{k} {v:.1%}" for k, v in over_all.items()), flush=True)
    sareas = survey_areas()
    stree = shapely.STRtree([shapely.Polygon(a[2][:, :2]).buffer(0) for a in sareas])
    lh = line_heights()
    # the built lines' tracks over the rule's cells: what gives their height there (tools/line_heights.py's sources; a
    # null height or 'surface' is the game's surface profile, which reads the terrain)
    ctree = shapely.STRtree(shapely.points(x, y))
    on_track = {}
    for ln, k, xy_, sl, hz, step, spans in lh:
        sv = np.arange(len(hz)) * step  # (the heights' own points along the path)
        px_, py_ = np.interp(sv, sl, xy_[:, 0]), np.interp(sv, sl, xy_[:, 1])
        hit = ctree.query(shapely.points(px_, py_), predicate="dwithin", distance=1.5)
        for pi_ in np.unique(hit[0]):
            src = next((sp[2] for sp in spans if sp[0] <= sv[pi_] <= sp[1]), None)
            key = "surface (terrain)" if hz[pi_] is None or src == "surface" else src
            on_track.setdefault(f"line {ln}", {}).setdefault(key, 0)
            on_track[f"line {ln}"][key] += 1
    print(f"the lines' heights (every 2 m) within 1.5 m of the rule's cells, by what gives them: {on_track}", flush=True)
    bridges = lod2_triangles(kind=1)
    btree = shapely.STRtree(shapely.polygons(bridges)) if len(bridges) else None
    # the places: per passage way its cells
    per = {}
    for i in np.unique(way):
        m = way == i
        lat, lon = F.ll(float(np.median(x[m])), float(np.median(y[m])))
        t = ways[i][1]
        per[int(i)] = {"i": int(i), "way": int(ways[i][0]), "class": ways[i][2], "cells": int(m.sum()),
                       "x": float(np.median(x[m])), "y": float(np.median(y[m])), "lat": float(lat), "lon": float(lon),
                       "unbuilt": unbuilt(t),
                       "name": t.get("name") or t.get("highway") or t.get("waterway") or t.get("railway") or "",
                       "jump_median": round(float(np.median(jump[m])), 2), "in_osm_buildings": round(float(in_osm[m].mean()), 2),
                       "track_m": round(float(td[m].min()), 1), "tags": {k: v for k, v in t.items() if k in (
                           "tunnel", "covered", "culvert", "layer", "highway", "railway", "waterway", "name", "footway")}}
    chosen = choose(per, F)
    ctx = {"ipr": ipr, "F": F, "dem": dem, "osm": osm, "ways": ways}
    district = {}
    for i, (why, p) in enumerate(chosen):
        dn = [nm for kd, nm, g in parts if kd == "district" and shapely.contains_xy(g, p["x"], p["y"])]
        p["district"] = dn[0] if dn else "outside the city"
        p["why"], p["mapy"] = why, mapy(p["lat"], p["lon"])
        m = (way == p["i"]) & (np.abs(x - p["x"]) < 75) & (np.abs(y - p["y"]) < 75)  # (this way's cells in the panel)
        inbox = (np.abs(x - p["x"]) < 76) & (np.abs(y - p["y"]) < 76)
        title = (f"{i + 1}. {p['name'] or 'unnamed'} ({p['district']}): {p['class']}, way {p['way']} — "
                 f"{p['lat']:.5f} N, {p['lon']:.5f} E — rule takes {p['cells']} cells, jump median {p['jump_median']} m")
        f = os.path.join(OUT, f"passages-{i + 1}.png")
        here = (np.abs(segs[:, 0] - p["x"]) < 120) & (np.abs(segs[:, 1] - p["y"]) < 120)
        panel(f, ctx, p["x"], p["y"], 150.0, title, lines=[s.reshape(2, 2) for s in segs[here]],
              taken=np.column_stack([x[inbox], y[inbox]]))
        district[i] = p["district"]
        # what could give the deck its height here, at the cells the rule took
        mx, my, mz0, mz1 = x[m], y[m], z0[m], z1[m]
        pts = shapely.points(mx, my)
        pi, ai = stree.query(pts, predicate="within")
        sv = {}
        for a_i in np.unique(ai):
            c, lvl, xyz = sareas[a_i]
            got = pi[ai == a_i]
            dz = [float(xyz[np.argmin(np.hypot(xyz[:, 0] - mx[g], xyz[:, 1] - my[g])), 2]) for g in got]
            key = f"{c} (level {lvl})"
            sv.setdefault(key, []).extend(np.array(dz) - mz0[got])
        p["survey"] = {k: {"cells": len(v), "over_ipr_median": round(float(np.median(v)), 2)} for k, v in sv.items()}
        p["survey_cells"] = int(len(np.unique(pi)))
        p["mosty3d_cells"] = int(len(np.unique(btree.query(pts, predicate="within")[0]))) if btree is not None else 0
        p["dmr5g_over_ipr_median"] = round(float(np.median(mz1 - mz0)), 2)
        p["decks"] = {k: int((deck[m] == j).sum()) for j, k in enumerate(DECKS) if (deck[m] == j).any()}
        trk = []
        for ln, k, xy, sl, hz, step, spans in lh:
            dd = np.hypot(xy[:, 0] - p["x"], xy[:, 1] - p["y"])
            near_ = np.flatnonzero(dd <= 40)
            if not len(near_):
                continue
            s_ = sl[near_]
            src = sorted({sp[2] for sp in spans for v in s_ if sp[0] <= v <= sp[1]})
            idx = np.clip(np.round(s_ / step).astype(int), 0, len(hz) - 1)
            zz = [hz[j_] for j_ in idx]
            trk.append({"line": ln, "dir": k, "s": [round(float(s_.min())), round(float(s_.max()))], "sources": src,
                        "null": int(sum(v is None for v in zz)), "points": len(zz)})
        p["track_heights_within_40m"] = trk
        print(f"  {i + 1}. {why}: {p['name']} ({p['district']}), {p['class']}, {p['cells']} cells, jump {p['jump_median']} m, "
              f"in OSM buildings {p['in_osm_buildings']:.0%}, track {p['track_m']} m — {p['mapy']}\n"
              f"     over it {p['decks']}; survey {p['survey']}; Mosty 3D {p['mosty3d_cells']} cells; "
              f"tracks within 40 m {p['track_heights_within_40m']}", flush=True)
    res = {"snapshot": sid, "tiles": len(allowed), "cells": int(len(x)), "km2": round(len(x) / 1e6, 4), "classes": table,
           "over": over_all, "track_points_over_rule_cells": on_track,
           "examples": [p for _, p in chosen], "ways": sorted(per.values(), key=lambda p: -p["cells"]),
           "s": round(time.time() - t0)}
    json.dump(res, open(os.path.join(OUT, "passages.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"written {OUT}/passages.json and passages-*.png in {time.time() - t0:.0f} s", flush=True)


# ---------------------------------------------------------------- the city-wide comparison
def compare(step=2, partial=False):
    from geo import Frame
    from ipr_dtm import IprDtm
    import shapely
    from PIL import Image, ImageDraw
    t0 = time.time()
    F, ipr = Frame(), IprDtm()
    tiles = dmr5g.under_ipr(ipr)
    dem = dmr5g.Tiles()
    missing = [t for t in tiles if not dem.have(*t)]
    if missing and not partial:
        raise SystemExit(f"{len(missing)} of the {len(tiles)} DMR 5G tiles under IPR are not in raw/dem/: "
                         "python -P -E tools/dmr5g.py --under-ipr (or --partial)")
    h, w = -(-ipr.h // step), -(-ipr.w // step)
    origin = (ipr.e0 - F.E0, ipr.n0 - F.N0)  # (cell (r, c) of the comparison is the raster's (r * step, c * step))
    D = np.full((h, w), np.nan, np.float32)
    for ty in range(-(-ipr.h // ipr.th)):
        r0 = ty * ipr.th
        rr = np.arange(r0, min(r0 + ipr.th, ipr.h))
        kr = rr % step == 0
        for tx in range(ipr.ntx):
            c0 = tx * ipr.tw
            cc = np.arange(c0, min(c0 + ipr.tw, ipr.w))
            kc = cc % step == 0
            a = ipr.decode(tx, ty)[:len(rr), :len(cc)][kr][:, kc]
            a[~(a >= TERRAIN_FLOOR)] = np.nan
            D[np.ix_(rr[kr] // step, cc[kc] // step)] = a
    print(f"IPR every {step} m: {h} x {w}, {time.time() - t0:.0f} s", flush=True)
    seen = np.zeros((h, w), bool)
    for ix, iy in tiles:
        if not dem.have(ix, iy):
            continue
        ea, eb = ix * dmr5g.TILE, ix * dmr5g.TILE + dmr5g.TILE
        na, nb = iy * dmr5g.TILE, iy * dmr5g.TILE + dmr5g.TILE
        c_lo, c_hi = max(0, math.ceil((ea - ipr.e0) / step)), min(w, math.ceil((eb - ipr.e0) / step))
        r_lo, r_hi = max(0, math.floor((ipr.n0 - nb) / step) + 1), min(h, math.floor((ipr.n0 - na) / step) + 1)
        if c_lo >= c_hi or r_lo >= r_hi:
            continue
        cols, rows = np.meshgrid(np.arange(c_lo, c_hi), np.arange(r_lo, r_hi))
        E, N = ipr.e0 + cols * step, ipr.n0 - rows * step
        z1 = dem.sample(E.astype(np.float64), N.astype(np.float64))
        dem.tiles.pop((ix, iy), None)
        z1[~(z1 >= TERRAIN_FLOOR)] = np.nan
        D[r_lo:r_hi, c_lo:c_hi] -= z1
        seen[r_lo:r_hi, c_lo:c_hi] = True
    D[~seen] = np.nan
    del seen
    valid = np.isfinite(D)
    print(f"IPR - DMR 5G on {int(valid.sum()) * step * step / 1e6:.1f} km², {time.time() - t0:.0f} s", flush=True)
    # what lies where: passages (left out), buildings (apart), the city and its districts
    city, parts = ct.boundaries(F)
    ways = passages(F)

    def rings(g):
        qs = getattr(g, "geoms", [g])
        return [(True, np.asarray(q.exterior.coords)) for q in qs] + [(False, np.asarray(r.coords)) for q in qs for r in q.interiors]
    pas = []
    for g in shapely.buffer(polylines([wy[3] for wy in ways]), dmr5g.PASSAGE_R):
        pas += rings(g)
    near_pas = paint_rings(pas, (h, w), origin, step)
    osm = osm_areas(F)
    bld = paint_rings(osm.get("building", []), (h, w), origin, step)
    water = paint_rings(osm.get("water", []), (h, w), origin, step)
    inside = paint_rings(rings(city), (h, w), origin, step)
    dist = Image.new("L", (w, h), 0)
    dd = ImageDraw.Draw(dist)
    districts = [p for p in parts if p[0] == "district"]
    names = [nm for _, nm, _ in districts]
    for i, (_, _, g) in enumerate(districts):
        for outer, xy in rings(g):
            dd.polygon([((x - origin[0]) / step, (origin[1] - y) / step) for x, y in xy], fill=i + 1 if outer else 0)
    dist = np.asarray(dist)
    print(f"masks: passages, buildings, city, {len(names)} districts, {time.time() - t0:.0f} s", flush=True)
    cell = step * step / 1e6  # (km² a cell)
    open_ = valid & ~near_pas & ~bld & ~water
    inbld = valid & ~near_pas & bld & ~water
    onwater = valid & ~near_pas & water

    def stats(m):
        v = D[m]
        if not len(v):
            return {"km2": 0}
        q = np.percentile(v, [5, 25, 50, 75, 95])
        return {"km2": round(len(v) * cell, 2), "median": round(float(q[2]), 3), "p5": round(float(q[0]), 2),
                "p25": round(float(q[1]), 2), "p75": round(float(q[3]), 2), "p95": round(float(q[4]), 2),
                "mean": round(float(v.mean()), 3),
                "over_km2": {f"{t:g}": round(float((np.abs(v) > t).sum()) * cell, 3) for t in OVER}}
    res = {"step": step, "tiles": len(tiles), "missing": len(missing), "km2": round(int(valid.sum()) * cell, 1),
           "near_passages_km2": round(int((valid & near_pas).sum()) * cell, 2),
           "open": {"inside": stats(open_ & inside), "outside": stats(open_ & ~inside), "all": stats(open_)},
           "buildings": {"inside": stats(inbld & inside), "outside": stats(inbld & ~inside), "all": stats(inbld)},
           "water": {"inside": stats(onwater & inside), "outside": stats(onwater & ~inside), "all": stats(onwater)},
           "districts": []}
    for i, nm in enumerate(names + ["(outside the city)"]):
        v = D[open_ & (dist == i + 1)] if i < len(names) else D[open_ & ~inside]
        if len(v):
            res["districts"].append({"district": nm, "km2": round(len(v) * cell, 2), "median": round(float(np.median(v)), 3),
                                     "p10": round(float(np.percentile(v, 10)), 2), "p90": round(float(np.percentile(v, 90)), 2),
                                     "over1_km2": round(float((np.abs(v) > 1).sum()) * cell, 3)})
    print(f"statistics, {time.time() - t0:.0f} s", flush=True)
    # the connected areas over 1 m on land (outside passages and OSM water), on blocks of BLOCK x BLOCK cells
    over = valid & ~near_pas & ~water & (np.abs(np.nan_to_num(D)) > 1)
    nby, nbx = -(-h // BLOCK), -(-w // BLOCK)

    def blocks(a):
        return np.pad(a, ((0, nby * BLOCK - h), (0, nbx * BLOCK - w))).reshape(nby, BLOCK, nbx, BLOCK).sum((1, 3))
    cnt, nval = blocks(over), blocks(valid & ~near_pas & ~water)
    flag = (cnt > 0) & (cnt >= 0.25 * nval)
    lab = np.zeros((nby, nbx), np.int64)
    n = 0
    for sy, sx in zip(*np.nonzero(flag)):
        if lab[sy, sx]:
            continue
        n += 1
        stack, lab[sy, sx] = [(sy, sx)], n
        while stack:
            yy, xx = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    y2, x2 = yy + dy, xx + dx
                    if 0 <= y2 < nby and 0 <= x2 < nbx and flag[y2, x2] and not lab[y2, x2]:
                        lab[y2, x2] = n
                        stack.append((y2, x2))
    sizes = np.bincount(lab.ravel(), weights=cnt.ravel(), minlength=n + 1)
    sizes[0] = 0
    top = [k for k in np.argsort(-sizes)[:15] if sizes[k] > 0]
    cat_tree = {}
    for c, rs in osm.items():
        polys = [shapely.Polygon(xy) for outer, xy in rs if outer and len(xy) >= 4]
        polys = [p if p.is_valid else p.buffer(0) for p in polys]
        cat_tree[c] = shapely.STRtree(polys)
    areas = []
    for k in top:
        bys, bxs = np.nonzero(lab == k)
        b0, b1, a0, a1 = bys.min(), bys.max() + 1, bxs.min(), bxs.max() + 1
        r0, c0 = b0 * BLOCK, a0 * BLOCK
        mine = np.repeat(np.repeat(lab[b0:b1, a0:a1] == k, BLOCK, 0), BLOCK, 1)
        sub = over[r0:r0 + mine.shape[0], c0:c0 + mine.shape[1]]
        jj, ii = np.nonzero(sub & mine[:sub.shape[0], :sub.shape[1]])
        dv = D[r0 + jj, c0 + ii]
        x, y = origin[0] + (c0 + ii) * step, origin[1] - (r0 + jj) * step
        lat, lon = F.ll(float(x.mean()), float(y.mean()))
        pick = np.linspace(0, len(x) - 1, min(len(x), 3000)).astype(int)
        share = {}
        for c, tree in cat_tree.items():
            hit = tree.query(shapely.points(x[pick], y[pick]), predicate="within")
            share[c] = round(len(np.unique(hit[0])) / len(pick), 2)
        dn = np.bincount(dist[r0 + jj, c0 + ii], minlength=len(names) + 1)
        areas.append({"m2": int(len(x) * step * step), "max": round(float(np.abs(dv).max()), 2),
                      "mean": round(float(dv.mean()), 2), "x": float(x.mean()), "y": float(y.mean()),
                      "box": [float(x.min()), float(y.min()), float(x.max()), float(y.max())],
                      "lat": round(float(lat), 6), "lon": round(float(lon), 6), "mapy": mapy(lat, lon),
                      "district": names[int(np.argmax(dn[1:]))] if dn[1:].any() else "(outside the city)",
                      "in_buildings": round(float(bld[r0 + jj, c0 + ii].mean()), 2),
                      "osm": {c: v for c, v in share.items() if v}})
    res["areas"] = areas
    for i, a in enumerate(areas):
        a["n"] = i + 1
        print(f"  {i + 1}. {a['m2']:,} m², max {a['max']} m, mean {a['mean']:+} m, {a['district']}, in buildings "
              f"{a['in_buildings']:.0%}, OSM {a['osm']} — {a['mapy']}", flush=True)
    print(f"areas, {time.time() - t0:.0f} s", flush=True)
    # the map: the median per 20 m block, in the frame of city_terrain.py's zero-areas.png
    px = max(1, 20 // step)
    mh, mw = -(-h // px), -(-w // px)
    img = np.full((mh, mw, 3), 255, np.uint8)
    for by in range(mh):
        band = D[by * px:(by + 1) * px].copy()
        band[near_pas[by * px:(by + 1) * px]] = np.nan
        band = np.pad(band, ((0, px - band.shape[0]), (0, mw * px - w)), constant_values=np.nan)
        with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
            __import__("warnings").simplefilter("ignore")
            med = np.nanmedian(band.reshape(px, mw, px).transpose(1, 0, 2).reshape(mw, -1), axis=1)
        img[by] = diverging(med[None, :], 2.0)[0]
        img[by][np.isnan(med)] = (255, 255, 255)
    im = Image.fromarray(img)
    dr = ImageDraw.Draw(im)

    def pt(x, y):
        return ((x - origin[0]) / (px * step), (origin[1] - y) / (px * step))
    for _, _, g in districts:
        for outer, xy in rings(g):
            dr.line([pt(x, y) for x, y in xy], fill=(120, 120, 120), width=1)
    for outer, xy in rings(city):
        dr.line([pt(x, y) for x, y in xy], fill=(0, 0, 0), width=3)
    for a in areas:
        x, y = pt(a["x"], a["y"])
        dr.text((x + 6, y - 12), str(a["n"]), fill=(0, 0, 0), font=font(22), stroke_width=3, stroke_fill=(255, 255, 255))
    dr.rectangle([8, 6, 560, 98], fill=(255, 255, 255), outline=(0, 0, 0))
    dr.text((16, 10), f"IPR 1 m (2023) - DMR 5G (2009-2013), median per {px * step} m, outside OSM passages",
            fill=(0, 0, 0), font=font(15))
    for i in range(400):
        c = diverging(np.array([[(i / 399 * 2 - 1) * 2.0]]), 2.0)[0, 0]
        dr.line([(16 + i, 36), (16 + i, 52)], fill=tuple(int(v) for v in c))
    for v in (-2, -1, 0, 1, 2):
        dr.text((16 + (v / 2 + 1) / 2 * 399 - 10, 56), f"{v:+d} m" if v else "0", fill=(0, 0, 0), font=font(13))
    dr.text((16, 76), "blue: IPR under DMR 5G   red: IPR over   numbers: the largest areas over 1 m", fill=(0, 0, 0),
            font=font(13))
    dr.line([(16, mh - 30), (16 + 5000 / (px * step), mh - 30)], fill=(0, 0, 0), width=3)
    dr.text((16, mh - 54), "5 km", fill=(0, 0, 0), font=font(13))
    im.save(os.path.join(OUT, "compare-map.png"))
    D = None  # (the panels read the rasters again)
    ctx = {"ipr": ipr, "F": F, "dem": dem, "osm": osm, "ways": ways}
    for a in areas[:6]:
        size = float(min(800, max(150, a["box"][2] - a["box"][0] + 60, a["box"][3] - a["box"][1] + 60)))
        cx, cy = (a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2
        lim = float(min(10, max(2, math.ceil(a["max"] / 2))))
        panel(os.path.join(OUT, f"compare-{a['n']}.png"), ctx, cx, cy, size,
              f"{a['n']}. {a['district']}: {a['m2']:,} m² over 1 m, max {a['max']} m, mean {a['mean']:+} m — "
              f"{a['lat']:.5f} N, {a['lon']:.5f} E", lim=lim)
    res["s"] = round(time.time() - t0)
    res["peak_gb"] = round(ct.peak_gb(), 1)
    json.dump(res, open(os.path.join(OUT, "compare.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("km2", "near_passages_km2", "open", "buildings", "water")}, indent=1))
    print(f"written {OUT}/compare.json, compare-map.png, compare-*.png in {time.time() - t0:.0f} s, peak {res['peak_gb']} GB",
          flush=True)


def choose(per, F):
    """The places to draw: Divadelní's underpass at Národní divadlo and the Rokytka culvert by line 37 (the rule's own
    cases, docs of 2026-10-30), the three largest building passages, the largest built passage within 3 m of a track not
    among them, and the largest proposed one (no passage on the ground)."""
    ps = [p for p in per.values()]
    out = []
    div = [p for p in ps if p["name"] == "Divadelní"]
    if div:
        out.append(("Divadelní at Národní divadlo (an underpass the rule was made for)", max(div, key=lambda p: p["cells"])))
    rok = [p for p in ps if "Rokytka" in p["name"] and p["track_m"] <= 3]
    if rok:
        out.append(("the Rokytka under line 37 (a culvert the rule was made for)", min(rok, key=lambda p: p["track_m"])))
    k = 0
    for p in sorted([p for p in ps if p["class"] == "building_passage"], key=lambda p: -p["cells"]):
        if k < 3 and all(math.hypot(p["x"] - q["x"], p["y"] - q["y"]) > 300 for _, q in out):
            out.append((f"building passage, the {['largest', 'second', 'third'][k]} the rule takes", p))
            k += 1
    used = {q["way"] for _, q in out}
    tr = sorted([p for p in ps if p["track_m"] <= 3 and not p["unbuilt"] and p["way"] not in used], key=lambda p: -p["cells"])
    if tr:
        out.append(("the largest built one by a track", tr[0]))
    pr = sorted([p for p in ps if p["unbuilt"]], key=lambda p: -p["cells"])
    if pr:
        out.append(("the largest proposed one: no passage on the ground", pr[0]))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.makedirs(OUT, exist_ok=True)
    if "--passages" in sys.argv:
        audit()
    else:
        from baseline_store import HeavyJob
        with HeavyJob("terrain_compare"):  # (~5 GB at 2 m)
            compare(int(sys.argv[sys.argv.index("--step") + 1]) if "--step" in sys.argv else 2, "--partial" in sys.argv)
