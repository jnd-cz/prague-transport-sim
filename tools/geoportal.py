"""Import Geoportál Praha (IPR Praha) open data for a built line: LOD2 3D buildings, retaining
walls and individual trees along the route.

Sources (CC BY 4.0, "data base © IPR Praha"):
  - Budovy 3D (I3S SceneServer, mesh pyramids, Web Mercator, absolute heights)
  - Opěrné zdi (retaining walls, lines with height)
  - Sdílená data o zeleni - vegetační prvky - body (individual trees)
  - Stromořadí (tree rows)

Usage:  python -I tools/geoportal.py --line 22 [--refresh]
Needs data/lineN.json (from build_line.py). Writes data/lineN.geo.json + data/lineN.bld.bin.
"""
import gzip
import json
import math
import os
import struct
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
REFRESH = "--refresh" in sys.argv
CACHE = os.path.join(ROOT, "raw", "geoportal", f"line{LINE}")
os.makedirs(os.path.join(CACHE, "i3s"), exist_ok=True)

BLD = "https://services5.arcgis.com/SBTXIEUGWbqzUecw/arcgis/rest/services/Budovy_3D_WSL1/SceneServer/layers/0"
BRIDGES = "https://services5.arcgis.com/SBTXIEUGWbqzUecw/arcgis/rest/services/Mosty_3D_WSL1/SceneServer/layers/0"
WALLS = "https://mp.iprpraha.cz/arcgis/rest/services/Hosted/HM_CUR_HM_HLUKOCHR_OPERNEZDI_L/FeatureServer/0"
TREES = "https://mp.iprpraha.cz/arcgis/rest/services/Hosted/OPK_CUR_OPK_SMZ_VP_B/FeatureServer/0"
TREE_ROWS = "https://mp.iprpraha.cz/arcgis/rest/services/Hosted/URK_CUR_URK_SS_STROMORADI_L/FeatureServer/0"

CORRIDOR = 220.0     # m either side of the route, like the OSM buildings
CHUNK = 400.0        # m, building mesh chunks (frustum culling)
Q = 0.05             # m, vertex quantisation
R_EARTH = 6378137.0


def fetch(url, cache_name=None, binary=False):
    path = os.path.join(CACHE, cache_name) if cache_name else None
    if path and os.path.exists(path) and not REFRESH:
        with open(path, "rb") as f:
            data = f.read()
    else:
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "tram-game-prototype/0.1"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                break
            except Exception as e:
                print("  retry", attempt, e)
                time.sleep(3 * (attempt + 1))
        else:
            raise SystemExit("download failed: " + url)
        if data[:2] == b"\x1f\x8b":
            data = gzip.decompress(data)
        if path:
            with open(path, "wb") as f:
                f.write(data)
    return data if binary else json.loads(data)


# ------------------------------------------------------------------ coordinates
with open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8") as f:
    line = json.load(f)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from geo import Frame  # noqa: E402
F = Frame()  # the city frame: the one conversion (tools/geo.py)


def to_local(lat, lon):
    x, y = F.xy(lat, lon)
    return float(x), float(y)


def merc_to_latlon(mx, my):
    return math.degrees(2 * math.atan(math.exp(my / R_EARTH)) - math.pi / 2), math.degrees(mx / R_EARTH)


def latlon_to_merc(lat, lon):
    return math.radians(lon) * R_EARTH, math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R_EARTH


# route samples (local) + spatial hash for distance queries
path = line["path"]
samples = []
for (x0, y0), (x1, y1) in zip(path, path[1:]):
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 5))
    for k in range(n):
        samples.append((x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n))
samples.append(tuple(path[-1]))
for p in line.get("pathBack", [])[::2]:
    samples.append(tuple(p))
GRID = 50.0
grid = defaultdict(list)
for p in samples:
    grid[(int(p[0] // GRID), int(p[1] // GRID))].append(p)


def route_dist(x, y, reach=CORRIDOR + 60):
    cx, cy, r = int(x // GRID), int(y // GRID), int(reach // GRID) + 1
    best = float("inf")
    for i in range(cx - r, cx + r + 1):
        for j in range(cy - r, cy + r + 1):
            for p in grid.get((i, j), ()):
                d = (p[0] - x) ** 2 + (p[1] - y) ** 2
                if d < best:
                    best = d
    return math.sqrt(best)


# ------------------------------------------------------------------ buildings (I3S)
def i3s_buildings(service=BLD, cache="i3s", label="buildings"):
    """Meshes of an IPR I3S SceneServer (Budovy 3D, Mosty 3D share the geometry layout)."""
    pages = {}
    os.makedirs(os.path.join(CACHE, cache), exist_ok=True)

    def node(i):
        p = i // 64
        if p not in pages:
            pages[p] = fetch(f"{service}/nodepages/{p}?f=json", f"{cache}/np{p}.json")["nodes"]
        return pages[p][i % 64]

    # descend into every node whose bounding sphere comes near the route corridor
    leaves, stack = [], [0]
    while stack:
        n = node(stack.pop())
        c, hs = n["obb"]["center"], n["obb"]["halfSize"]
        lat, lon = merc_to_latlon(c[0], c[1])
        x, y = to_local(lat, lon)
        scale = math.cos(math.radians(lat))  # mercator metres -> ground metres
        radius = math.hypot(hs[0], hs[1]) * scale
        if radius < 3000 and route_dist(x, y, reach=radius + CORRIDOR + 50) > radius + CORRIDOR:
            continue
        if n.get("children"):
            stack.extend(n["children"])
        elif n.get("mesh"):
            leaves.append(n)
    print(f"{label}: {len(leaves)} leaf nodes along the route")

    seen, out = set(), []
    for k, n in enumerate(leaves):
        res = n["mesh"]["geometry"]["resource"]
        raw = fetch(f"{service}/nodes/{res}/geometries/0", f"{cache}/g{res}.bin", binary=True)
        vc, fc = struct.unpack_from("<II", raw, 0)
        off = 8
        pos = struct.unpack_from(f"<{vc * 3}f", raw, off); off += vc * 12
        off += vc * 12 + vc * 8 + vc * 4            # normals, uv0, colour
        fids = struct.unpack_from(f"<{fc}Q", raw, off); off += fc * 8
        ranges = struct.unpack_from(f"<{fc * 2}I", raw, off)
        cx, cy, cz = n["obb"]["center"]
        for f in range(fc):
            if fids[f] in seen:
                continue
            t0, t1 = ranges[2 * f], ranges[2 * f + 1]
            verts = []
            for t in range(t0, t1 + 1):
                for v in range(3):
                    i = (t * 3 + v) * 3
                    lat, lon = merc_to_latlon(cx + pos[i], cy + pos[i + 1])
                    x, y = to_local(lat, lon)
                    verts.append((x, y, cz + pos[i + 2]))
            if not verts:
                continue
            mx = sum(v[0] for v in verts) / len(verts)
            my = sum(v[1] for v in verts) / len(verts)
            if route_dist(mx, my) > CORRIDOR:
                continue
            seen.add(fids[f])
            out.append(verts)
        if (k + 1) % 20 == 0:
            print(f"  {k + 1}/{len(leaves)} nodes, {len(out)} {label}")
    return out


def write_buildings(buildings, kinds=None):
    """Quantised binary: per chunk an origin, then Int16 x,y,z triangles (non-indexed).
    `kinds` (parallel to buildings): 0 building, 1 bridge; stored per chunk as "k"."""
    kinds = kinds or [0] * len(buildings)
    kind_of = {id(b): k for b, k in zip(buildings, kinds)}
    chunks = defaultdict(list)
    for b in buildings:
        mx = sum(v[0] for v in b) / len(b)
        my = sum(v[1] for v in b) / len(b)
        chunks[(math.floor(mx / CHUNK), math.floor(my / CHUNK))].append(b)
    table, blob, voff = [], bytearray(), 0
    for (ci, cj), bs in sorted(chunks.items()):
        allv = [v for b in bs for v in b]
        ox = (ci + 0.5) * CHUNK
        oy = (cj + 0.5) * CHUNK
        oz = round(sum(v[2] for v in allv) / len(allv), 1)
        counts = []
        for b in bs:
            for x, y, z in b:
                blob += struct.pack("<hhh", *(max(-32768, min(32767, round(c / Q))) for c in (x - ox, y - oy, z - oz)))
            counts.append(len(b))
        entry = {"o": [ox, oy, oz], "v": voff, "n": len(allv), "b": counts}
        if any(kind_of[id(b)] for b in bs):
            entry["k"] = [kind_of[id(b)] for b in bs]
        table.append(entry)
        voff += len(allv)
    dst = os.path.join(ROOT, "data", f"line{LINE}.bld.bin")
    with open(dst, "wb") as f:
        f.write(blob)
    print(f"buildings: {len(buildings)} in {len(table)} chunks, {voff} vertices, {len(blob) / 1e6:.1f} MB")
    return {"file": f"line{LINE}.bld.bin", "q": Q, "chunks": table}


# ------------------------------------------------------------------ feature services
def corridor_boxes(step=600.0):
    """lat/lon envelopes covering the route corridor in ~600 m pieces."""
    boxes, acc, start = [], 0.0, 0
    for i in range(1, len(path)):
        acc += math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
        if acc >= step or i == len(path) - 1:
            seg = path[start:i + 1]
            xs, ys = [p[0] for p in seg], [p[1] for p in seg]
            la0, lo0, la1, lo1 = (float(v) for v in F.bbox(seg, CORRIDOR))
            boxes.append((lo0, la0, lo1, la1))
            acc, start = 0.0, i
    return boxes


def query(service, name, fields, out_sr=4326):
    """Features in the corridor; geometry as lat/lon, or as S-JTSK with out_sr=5514 (see trees())."""
    feats = {}
    for k, (lo0, la0, lo1, la1) in enumerate(corridor_boxes()):
        offset = 0
        while True:
            q = urllib.parse.urlencode({
                "where": "1=1", "geometry": f"{lo0},{la0},{lo1},{la1}", "geometryType": "esriGeometryEnvelope",
                "inSR": 4326, "outSR": out_sr, "spatialRel": "esriSpatialRelIntersects", "outFields": fields,
                "returnGeometry": "true", "resultOffset": offset, "resultRecordCount": 2000, "f": "json"})
            d = fetch(f"{service}/query?{q}", f"{name}{'' if out_sr == 4326 else out_sr}_{k}_{offset}.json")
            for ft in d.get("features", []):
                at = ft["attributes"]
                feats[at.get("objectid", at.get("OBJECTID", id(ft)))] = ft
            if not d.get("exceededTransferLimit"):
                break
            offset += 2000
    return list(feats.values())


def walls():
    out = []
    for ft in query(WALLS, "walls", "*"):
        for part in ft["geometry"].get("paths", []):
            pts = [to_local(lat, lon) for lon, lat in part]
            if min(route_dist(x, y) for x, y in pts) > 40:
                continue
            out.append({"p": [[round(x, 2), round(y, 2)] for x, y in pts], "h": round(ft["attributes"].get("vyska") or 2.0, 2)})
    print(f"retaining walls: {len(out)}")
    return out


# vegetation element (kod_vp, the layer's coded values) -> kind in the game:
# 0 deciduous tree, 1 conifer, 2 bush / hedge, 3 plants in a container, 4 tree-row sample;
# climbers (101, on facades and walls) and beds / lawns are not drawn
VP_KIND = {71: "tree", 61: "tree", 81: "tree", 51: 2, 41: 2, 131: 2, 21: 3}


def trees():
    out, kinds = [], {}
    # The tree register is stored in Web Mercator by the service, converted from the survey's S-JTSK with
    # a poor datum shift: its lat/lon lies ~10 m off the survey (the service gives the same shift back
    # when asked for S-JTSK). Asked for S-JTSK, the trees sit 0.3 m from the surveyed tree pits; the tree
    # rows and the other layers are right as lat/lon (tools/registration.py, #8).
    for ft in query(TREES, "trees", "*", out_sr=5514):
        g = ft.get("geometry") or {}
        pts = g.get("points") or ([[g["x"], g["y"]]] if "x" in g else [])  # multipoint or point
        a = ft["attributes"]
        kind = VP_KIND.get(a.get("kod_vp"))
        if kind is None:
            continue
        if kind == "tree":
            kind = 1 if a.get("kod_drevin") == 1 else 0
        for e, n in pts:
            x, y = (float(v) for v in F.from_jtsk(e, n))
            if route_dist(x, y) <= CORRIDOR:
                out.append([round(x, 1), round(y, 1), kind])
                kinds[kind] = kinds.get(kind, 0) + 1
    rows = 0
    for ft in query(TREE_ROWS, "treerows", "*"):
        for part in (ft.get("geometry") or {}).get("paths", []):
            pts = [to_local(lat, lon) for lon, lat in part]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                n = max(1, int(math.hypot(x1 - x0, y1 - y0) / 9))
                for k in range(n):
                    x, y = x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n
                    if route_dist(x, y) <= CORRIDOR:
                        out.append([round(x, 1), round(y, 1), 4]); rows += 1
    print(f"trees: {len(out)} ({rows} from tree rows), register kinds {dict(sorted(kinds.items()))}")
    return out


def main():
    dst = os.path.join(ROOT, "data", f"line{LINE}.geo.json")
    if "--trees-only" in sys.argv:
        # refresh only the vegetation of an existing file (from the download cache)
        geo = json.load(open(dst, encoding="utf-8"))
        geo["trees"] = trees()
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(geo, f, ensure_ascii=False, separators=(",", ":"))
        print(f"wrote {dst}")
        return
    geo = {"attribution": "3D buildings, retaining walls, trees: data base © IPR Praha (CC BY 4.0)"}
    geo["walls"] = walls()
    geo["trees"] = trees()
    blds = i3s_buildings()
    bridges = i3s_buildings(BRIDGES, "i3s_bridges", "bridges")
    geo["buildings"] = write_buildings(blds + bridges, [0] * len(blds) + [1] * len(bridges))
    geo["attribution"] = "3D buildings and bridges, retaining walls, trees: data base © IPR Praha (CC BY 4.0)"
    dst = os.path.join(ROOT, "data", f"line{LINE}.geo.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(geo, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
