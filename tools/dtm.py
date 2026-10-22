"""Import the Prague Digital Technical Map (DTM, open part: ZPS) along a built line.

DTM Praha open data, "Základní prostorová situace" per city district (městská část), GeoPackage,
CC BY 4.0, data base © IPR Praha / Hlavní město Praha: https://geoportalpraha.cz (DTM kraje - ZPS
Sada 2 = areas, ZPS Sada 3 = 3D boundary lines). Areas are 2D; every vertex gets its height from the
3D boundary lines at the same position (they share vertices), else from the nearest boundary point.
The tram track axes (DI) are not open data, so tracks stay from OSM.

Usage:  python tools/dtm.py --line 22 raw/dtm/<district OPL dir> raw/dtm/<district KR dir> ...
        (pass the unzipped *_ZPS_OPL.gpkg and *_ZPS_KR.gpkg folders of every district on the line)
Writes data/lineN.dtm.json: {"attribution", "areas": [{"c": class, "l": level, "r": [[x,y,z]...], "h": [holes]}]}
"""
import glob
import json
import math
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpkg  # noqa: E402
from pyproj import Transformer  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
SOURCES = [a for a in sys.argv[1:] if a not in ("--line", LINE)]
CORRIDOR = 80.0

# area classes by the DTM object type code at the end of the layer name
CLASSES = {
    "010000000503": "road", "010000001703": "road", "010000001103": "parking", "010000000903": "cycle",
    "010000000703": "sidewalk", "010000001303": "island", "010000002403": "tram", "010000005303": "platform",
    "010000005803": "deck", "010000006203": "tunnel", "010000006603": "underpass", "010000031203": "rail",
    "010000021503": "green", "010000020903": "green", "010000015203": "green", "010000018703": "paved",
    "010000018903": "paved", "010000005503": "paved", "010000016603": "stairs", "010000031503": "roof",
    "010000016803": "wall", "010000020303": "water",
}

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
LAT0, LON0 = line["origin"]
KX, KY = math.cos(math.radians(LAT0)) * 111320.0, 110574.0
to_wgs = Transformer.from_crs(5514, 4326, always_xy=True)

# lidar ground (DMR 5G grid of the line): a ground-level street corner far below it is a mislabelled
# underground line (e.g. a floor 20 m under Náměstí Míru tagged as level 0)
_T = line["terrain"]
_raw = __import__("array").array("h", __import__("base64").b64decode(_T["data"]))
LIDAR = [_T["base"] + v * _T["scale"] for v in _raw]


def lidar(x, y):
    fx, fy = (x - _T["x0"]) / _T["dx"], (y - _T["y0"]) / _T["dy"]
    ix = min(max(int(math.floor(fx)), 0), _T["nx"] - 2)
    iy = min(max(int(math.floor(fy)), 0), _T["ny"] - 2)
    tx, ty = min(max(fx - ix, 0), 1), min(max(fy - iy, 0), 1)
    a, b = LIDAR[iy * _T["nx"] + ix], LIDAR[iy * _T["nx"] + ix + 1]
    c, d = LIDAR[(iy + 1) * _T["nx"] + ix], LIDAR[(iy + 1) * _T["nx"] + ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def local(x, y):
    lon, lat = to_wgs.transform(x, y)
    return ((lon - LON0) * KX, (lat - LAT0) * KY)


# corridor test on a 40 m grid of route points (ours and the opposite direction)
cells = set()
for p in line["path"] + line.get("pathBack", []):
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            cells.add((int(p[0] // 40) + dx, int(p[1] // 40) + dy))


def in_corridor(q):
    return (int(q[0] // 40), int(q[1] // 40)) in cells


def walk(geom):
    t, c = geom
    if t == "Polygon":
        yield c
    elif t == "MultiPolygon":
        for part in c:
            yield from walk(part)


areas, n_z, n_near, n_none, dropped = [], 0, 0, 0, 0
cloud = {}  # (x*2, y*2) rounded -> z: one surveyed ground height per 0.5 m
# lines whose heights describe the ground-level street surface (not walls, stairs, buildings)
CLOUD_LINES = ("Hranice_dopravní_stavby_nebo_plochy", "Vnitřní_členění_dopravní_plochy", "Hranice_ostatní_plochy",
               "Hranice_udržované_zeleně", "Hranice_přírodního", "Terénní_hrana")
# heights: every vertex of the 3D boundary lines of all districts (areas along a district border
# take heights from the neighbour's lines too), keyed by its S-JTSK position (1 cm)
zkey = defaultdict(set)  # several heights where lines of two levels share a 2D position (wall top/foot)
zgrid = defaultdict(list)
districts = []
for src in SOURCES:
    opl = glob.glob(os.path.join(src, "*.gpkg"))[0] if os.path.isdir(src) else src
    if "OPL" not in opl:
        continue
    kr_dir = src.replace("ZPS_OPL", "ZPS_KR")
    kr = glob.glob(os.path.join(kr_dir, "*.gpkg"))[0]
    districts.append((src, opl))
    print("district:", os.path.basename(src))
    for t, info in gpkg.layers(kr).items():
        if info["type"] not in ("LINESTRING", "MULTILINESTRING") or "Hranice" not in t:
            continue
        for f in gpkg.features(kr, t):
            g = f["geom"]
            if not g:
                continue
            parts = [g[1]] if g[0] == "LineString" else [p[1] for p in g[1]]
            lvl = f.get("UrovenUmisteniObjektuZPS") or 0
            ground_line = lvl == 0 and any(k in t for k in CLOUD_LINES)
            for pts in parts:
                for x, y, z in pts:
                    if z:
                        zkey[(round(x, 2), round(y, 2))].add((z, lvl))
                        zgrid[(int(x // 5), int(y // 5))].append((x, y, z, lvl))
                # height cloud: ground-level traffic and surface lines, densified to 3 m
                if ground_line:
                    for (x0, y0, z0), (x1, y1, z1) in zip(pts, pts[1:]):
                        if not z0 or not z1:
                            continue
                        n = max(1, int(math.hypot(x1 - x0, y1 - y0) // 3))
                        for k in range(n + (1 if (x1, y1) == pts[-1][:2] else 0)):
                            u = k / n
                            q = local(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u)
                            if in_corridor(q):
                                cloud[(round(q[0] * 2), round(q[1] * 2))] = round(z0 + (z1 - z0) * u, 2)

def candidates(x, y, level):
    """Possible heights of a polygon vertex: the 3D line vertices at the same position, else
    the boundary points within 2.5 m (the nearest and any within 0.5 m more). Lines of the area's
    own level win: a ground-level street must not take the height of a metro vestibule or a deck
    outline that shares the position in 2D (for ground-level areas they are the only ones used)."""
    strict = level == 0
    global n_z, n_near, n_none
    zs = zkey.get((round(x, 2), round(y, 2)))
    if zs:
        n_z += 1
        own = {z for z, lv in zs if lv == level}
        if own or not strict:
            return sorted(own or {z for z, _ in zs})
    near = []
    for i in range(int(x // 5) - 1, int(x // 5) + 2):
        for j in range(int(y // 5) - 1, int(y // 5) + 2):
            for px, py, pz, lv in zgrid.get((i, j), ()):
                d = math.hypot(px - x, py - y)
                if d < 2.5:
                    near.append((d, pz, lv))
    own = [n for n in near if n[2] == level] or ([] if strict else near)
    if not own:
        n_none += 1
        return []
    n_near += 1
    d0 = min(n[0] for n in own)
    return sorted({n[1] for n in own if n[0] <= d0 + 0.5})

def ring_heights(cands):
    """One height per vertex: where lines of two levels meet in 2D (the top and the foot of a
    wall), take the candidate that continues from the neighbouring vertex, walking the ring
    from a vertex with a single candidate."""
    n = len(cands)
    out = [None] * n
    start = next((i for i, c in enumerate(cands) if len(c) == 1), None)
    if start is None:
        start = next((i for i, c in enumerate(cands) if c), None)
        if start is None:
            return out
        c = cands[start]
        out[start] = c[len(c) // 2]
    else:
        out[start] = cands[start][0]
    prev = out[start]
    for k in range(1, n):
        i = (start + k) % n
        c = cands[i]
        if c:
            out[i] = min(c, key=lambda z: abs(z - prev))
            prev = out[i]
    return out


def fill_along(r, zs):
    """Vertices without a height: linear along the ring between the known neighbours."""
    n = len(zs)
    known = [i for i, z in enumerate(zs) if z is not None]
    if not known or len(known) == n:
        return zs
    dist = [0.0]
    for (x0, y0, *_), (x1, y1, *_) in zip(r, r[1:] + r[:1]):
        dist.append(dist[-1] + math.hypot(x1 - x0, y1 - y0))
    total = dist[-1]
    out = list(zs)
    for k, i in enumerate(known):
        j = known[(k + 1) % len(known)]
        gap = (j - i) % n or n
        if gap == 1:
            continue
        span = (dist[j] - dist[i]) % total if total else 0
        for m in range(1, gap):
            v = (i + m) % n
            u = ((dist[v] - dist[i]) % total) / span if span else 0
            out[v] = zs[i] + (zs[j] - zs[i]) * u
    return out


def ring(r, level):
    """Local coordinates and heights of a ring, and how many vertices had no surveyed height."""
    loc = [local(x, y) for x, y, *_ in r]
    cands = [candidates(x, y, level) for x, y, *_ in r]
    if level == 0:
        cands = [[z for z in c if z > lidar(*q) - 5] for c, q in zip(cands, loc)]
    zs = ring_heights(cands)
    missing = sum(1 for z in zs if z is None)
    zs = fill_along(r, zs)
    out = []
    for (lx, ly), z in zip(loc, zs):
        out.append([round(lx, 2), round(ly, 2), None if z is None else round(z, 2)])
    if len(out) > 1 and out[0][:2] == out[-1][:2]:
        out.pop()
    return out, missing


for src, opl in districts:
    for t in gpkg.layers(opl):
        cls = CLASSES.get(t.split("#")[-1].split("_")[0])
        if not cls:
            continue
        for f in gpkg.features(opl, t):
            if not f["geom"]:
                continue
            for rings in walk(f["geom"]):
                outer = rings[0]
                loc = [local(x, y) for x, y, *_ in outer]
                if not any(in_corridor(q) for q in loc[:: max(1, len(loc) // 50)]) and not any(in_corridor(q) for q in loc):
                    continue
                level = f.get("UrovenUmisteniObjektuZPS") or 0
                r0, miss = ring(outer, level)
                if miss / max(1, len(r0)) > 0.3:
                    dropped += 1
                    continue  # mostly unknown heights: would be a flat sheet at a guessed level
                a = {"c": cls, "l": level, "r": r0}
                holes = [ring(h, level)[0] for h in rings[1:] if len(h) > 3]
                if holes:
                    a["h"] = holes
                areas.append(a)

counts = defaultdict(int)
for a in areas:
    counts[(a["c"], a["l"])] += 1
print("areas:", dict(sorted(counts.items())))
print(f"dropped {dropped} areas with >30 % unknown heights")
print(f"vertex heights: {n_z} exact, {n_near} from a boundary point within 2.5 m, {n_none} missing")
print(f"height cloud: {len(cloud)} points")
flat = []
for (kx, ky), z in cloud.items():
    flat += [kx / 2, ky / 2, z]
out = {"attribution": "Streets: DTM Praha, data base © IPR Praha (CC BY 4.0)", "areas": areas, "z": flat}
dst = os.path.join(ROOT, "data", f"line{LINE}.dtm.json")
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
print(f"wrote {dst} ({os.path.getsize(dst) / 1e6:.2f} MB)")
