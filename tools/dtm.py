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
for src in SOURCES:
    opl = glob.glob(os.path.join(src, "*.gpkg"))[0] if os.path.isdir(src) else src
    if "OPL" not in opl:
        continue
    kr_dir = src.replace("ZPS_OPL", "ZPS_KR")
    kr = glob.glob(os.path.join(kr_dir, "*.gpkg"))[0]
    print("district:", os.path.basename(src))
    # heights: every vertex of the 3D boundary lines, keyed by its S-JTSK position (1 cm)
    zkey = {}
    zgrid = defaultdict(list)
    for t, info in gpkg.layers(kr).items():
        if info["type"] not in ("LINESTRING", "MULTILINESTRING") or "Hranice" not in t:
            continue
        for f in gpkg.features(kr, t):
            g = f["geom"]
            if not g:
                continue
            parts = [g[1]] if g[0] == "LineString" else [p[1] for p in g[1]]
            ground_line = (f.get("UrovenUmisteniObjektuZPS") or 0) == 0 and any(k in t for k in CLOUD_LINES)
            for pts in parts:
                for x, y, z in pts:
                    if z:
                        zkey[(round(x, 2), round(y, 2))] = z
                        zgrid[(int(x // 5), int(y // 5))].append((x, y, z))
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

    def height(x, y):
        global n_z, n_near, n_none
        z = zkey.get((round(x, 2), round(y, 2)))
        if z is not None:
            n_z += 1
            return z
        best, bd = None, 2.5
        for i in range(int(x // 5) - 1, int(x // 5) + 2):
            for j in range(int(y // 5) - 1, int(y // 5) + 2):
                for px, py, pz in zgrid.get((i, j), ()):
                    d = math.hypot(px - x, py - y)
                    if d < bd:
                        best, bd = pz, d
        if best is None:
            n_none += 1
        else:
            n_near += 1
        return best

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
                def ring(r):
                    out = []
                    for (x, y, *_), (lx, ly) in zip(r, [local(x, y) for x, y, *_ in r]):
                        z = height(x, y)
                        out.append([round(lx, 2), round(ly, 2), None if z is None else round(z, 2)])
                    if len(out) > 1 and out[0][:2] == out[-1][:2]:
                        out.pop()
                    return out
                r0 = ring(outer)
                missing = sum(1 for p in r0 if p[2] is None) / max(1, len(r0))
                if missing > 0.3:
                    dropped += 1
                    continue  # mostly unknown heights: would be a flat sheet at a guessed level
                a = {"c": cls, "l": f.get("UrovenUmisteniObjektuZPS") or 0, "r": r0}
                holes = [ring(h) for h in rings[1:] if len(h) > 3]
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
