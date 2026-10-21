"""Build a compact game data file for one Prague tram line.

Sources:
  - OpenStreetMap via Overpass API (route geometry, tram track network, crossings,
    traffic signals, buildings, roads, green areas, water)  -- (c) OSM contributors, ODbL
  - PID GTFS (stops + timetable)  -- ROPID / data.pid.cz, CC BY 4.0
  - ČÚZK DMR 5G bare-earth terrain (lidar) via the ags.cuzk.gov.cz ImageServer  -- CC BY 4.0

Usage:  python -I tools/build_line.py [--refresh]
Raw downloads are cached in raw/, output goes to data/line22.json.
"""
import base64
import csv
import datetime as dt
import io
import json
import math
import os
import struct
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1250

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
OUT = os.path.join(ROOT, "data")

def _arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


LINE = _arg("--line", "22")
GTFS_ROUTE = f"L{LINE}"
GTFS_DIRECTION = "0"
SERVICE_DATE = dt.date(2026, 10, 21)
GTFS_ZIP = os.path.join(RAW, "PID_GTFS.zip")
# per-line download cache (line 22 keeps the original location)
if LINE != "22":
    RAW = os.path.join(RAW, f"line{LINE}")
    os.makedirs(RAW, exist_ok=True)

DEM_SERVICE = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer/exportImage"
DEM_STEP = 10.0     # terrain grid spacing (m)
DEM_MARGIN = 700.0  # terrain extends this far around the route bbox (m)

OVERPASS = ["https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass-api.de/api/interpreter"]
REFRESH = "--refresh" in sys.argv


# ---------------------------------------------------------------- downloads
def overpass(name, query, optional=False):
    path = os.path.join(RAW, name + ".json")
    if os.path.exists(path) and not REFRESH:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    print("overpass:", name)
    body = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(10):
        req = urllib.request.Request(OVERPASS[attempt % len(OVERPASS)], data=body,
                                     headers={"User-Agent": "tram-game-prototype/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            if not json.loads(data).get("elements"):
                raise ValueError("empty result")
            break
        except Exception as e:  # rate limit / timeout: back off and retry
            print("  retry", attempt, e)
            time.sleep(min(90, 5 * 2 ** (attempt // 2)))  # back off: the public servers are often overloaded
    else:
        if optional:
            print("  ! skipped (optional):", name)
            return {"elements": []}
        raise SystemExit("overpass failed: " + name)
    with open(path, "wb") as f:
        f.write(data)
    return json.loads(data)


def route_query(rel_id):
    return f"[out:json][timeout:120];relation({rel_id})->.r;way(r.r)->.w;.r out body;.w out body;.w >;out skel qt;"


def norm_name(n):
    return " ".join((n or "").lower().replace("-", " ").split())


def pick_relations(headsign):
    """OSM route relations of the line: the one ending at the GTFS headsign, and its opposite."""
    rels = overpass("relations", "[out:json][timeout:60];relation[type=route][route=tram]"
                    f"[ref=\"{LINE}\"](49.9,14.2,50.2,14.7);out tags;")["elements"]
    if not rels:
        raise SystemExit(f"no OSM relation for tram {LINE}")
    hs = norm_name(headsign)
    main = (next((r for r in rels if norm_name(r["tags"].get("to")) == hs), None)
            or next((r for r in rels if hs and hs in norm_name(r["tags"].get("to"))), None) or rels[0])
    f, t = norm_name(main["tags"].get("from")), norm_name(main["tags"].get("to"))
    back = (next((r for r in rels if r is not main and norm_name(r["tags"].get("from")) == t and norm_name(r["tags"].get("to")) == f), None)
            or next((r for r in rels if r is not main and norm_name(r["tags"].get("from")) == t), None)
            or next((r for r in rels if r is not main), None))
    print(f"relations: {main['id']} {main['tags'].get('name')} / back {back and back['id']}")
    return main["id"], back["id"] if back else None


def gtfs_headsign():
    """Direction-0 headsign with the most trips on the service date (or --headsign)."""
    if "--headsign" in sys.argv:
        return _arg("--headsign", "")
    z = zipfile.ZipFile(GTFS_ZIP)
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig"))
    ymd, wd = SERVICE_DATE.strftime("%Y%m%d"), SERVICE_DATE.strftime("%A").lower()
    active = {c["service_id"] for c in rd("calendar.txt") if c["start_date"] <= ymd <= c["end_date"] and c[wd] == "1"}
    for c in rd("calendar_dates.txt"):
        if c["date"] == ymd:
            (active.add if c["exception_type"] == "1" else active.discard)(c["service_id"])
    c = Counter(r["trip_headsign"] for r in rd("trips.txt")
                if r["route_id"] == GTFS_ROUTE and r["direction_id"] == GTFS_DIRECTION and r["service_id"] in active)
    if not c:
        raise SystemExit(f"no GTFS trips for {GTFS_ROUTE}")
    return c.most_common(1)[0][0]


GTFS_HEADSIGN = gtfs_headsign()
OSM_RELATION, OSM_RELATION_BACK = pick_relations(GTFS_HEADSIGN)
R = f"relation({OSM_RELATION})->.r;way(r.r)->.w;"
Q_ROUTE = route_query(OSM_RELATION)
Q_ROUTE_BACK = route_query(OSM_RELATION_BACK) if OSM_RELATION_BACK else None
Q_TRACKS = f"[out:json][timeout:120];{R}way(around.w:60)[railway~\"^(tram|light_rail)$\"]->.t;.t out body;.t >;out body qt;"
Q_POINTS = (f"[out:json][timeout:120];{R}"
            "(node(around.w:35)[highway=traffic_signals];"
            "node(around.w:6)[railway~\"^(tram_level_crossing|level_crossing|tram_crossing|crossing)$\"];"
            "node(around.w:15)[highway=crossing];);out body qt;")
Q_BUILDINGS = f"[out:json][timeout:180];{R}way(around.w:110)[building];out tags geom qt;"
Q_ROADS = (f"[out:json][timeout:180];{R}way(around.w:90)[highway~\"^(motorway|trunk|primary|secondary|tertiary|"
           "residential|unclassified|living_street|service|pedestrian|footway|primary_link|secondary_link|"
           "tertiary_link|trunk_link)$\"];out tags geom qt;")
Q_GREEN = (f"[out:json][timeout:180];{R}(way(around.w:120)[landuse~\"^(grass|forest|meadow|recreation_ground|"
           "village_green|cemetery|allotments)$\"];way(around.w:120)[leisure~\"^(park|garden|pitch)$\"];"
           "way(around.w:120)[natural~\"^(wood|scrub|grassland)$\"];);out tags geom qt;")
Q_WATER = f"[out:json][timeout:180];{R}(relation(around.w:250)[natural=water];way(around.w:250)[natural=water];);out geom qt;"


# ---------------------------------------------------------------- geometry
class Proj:
    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = math.cos(math.radians(lat0)) * 111320.0
        self.ky = 110574.0

    def __call__(self, lat, lon):
        # x = east, y = north (metres)
        return ((lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def norm(v):
    l = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / l, v[1] / l)


def angle_between(u, v):
    u, v = norm(u), norm(v)
    return math.degrees(math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))))


class Polyline:
    def __init__(self, pts):
        self.pts = pts
        self.s = [0.0]
        for i in range(1, len(pts)):
            self.s.append(self.s[-1] + dist(pts[i - 1], pts[i]))
        self.length = self.s[-1]
        # spatial hash of segments for fast projection
        self.cell = 50.0
        self.grid = defaultdict(list)
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            for cx in range(int(math.floor(min(x0, x1) / self.cell)), int(math.floor(max(x0, x1) / self.cell)) + 1):
                for cy in range(int(math.floor(min(y0, y1) / self.cell)), int(math.floor(max(y0, y1) / self.cell)) + 1):
                    self.grid[(cx, cy)].append(i)

    def project(self, p, s_min=-1e9, s_max=1e9, radius=1):
        """Return (s, distance, side) of nearest point; side>0 means p is left of the direction of travel."""
        best = (None, 1e18, 0)
        cx, cy = int(math.floor(p[0] / self.cell)), int(math.floor(p[1] / self.cell))
        segs = set()
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                segs.update(self.grid.get((cx + dx, cy + dy), ()))
        if not segs:
            segs = range(len(self.pts) - 1)
        for i in segs:
            a, b = self.pts[i], self.pts[i + 1]
            ab = (b[0] - a[0], b[1] - a[1])
            l2 = ab[0] ** 2 + ab[1] ** 2 or 1e-9
            t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
            q = (a[0] + ab[0] * t, a[1] + ab[1] * t)
            s = self.s[i] + t * math.sqrt(l2)
            if s < s_min or s > s_max:
                continue
            d = dist(p, q)
            if d < best[1]:
                side = ab[0] * (p[1] - a[1]) - ab[1] * (p[0] - a[0])
                best = (s, d, side)
        return best

    def at(self, s):
        s = max(0.0, min(self.length, s))
        lo, hi = 0, len(self.s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        a, b = self.pts[lo], self.pts[hi]
        seg = self.s[hi] - self.s[lo] or 1e-9
        t = (s - self.s[lo]) / seg
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


# ---------------------------------------------------------------- route chaining
def chain_route(rel, ways):
    members = [m["ref"] for m in rel["members"] if m["type"] == "way" and m["role"] in ("", "forward", "backward")]
    members = [m for m in members if m in ways]
    chain = []
    for idx, wid in enumerate(members):
        w = ways[wid]
        nxt = set(ways[members[idx + 1]]) if idx + 1 < len(members) else None
        if not chain:
            # orient the first way so that its end touches the next one
            if nxt and w[0] in nxt and w[-1] not in nxt:
                w = w[::-1]
            chain = list(w)
            continue
        end = chain[-1]
        closed = w[0] == w[-1]
        opts = []
        for k in [i for i, n in enumerate(w) if n == end]:
            if closed:
                ring = w[:-1]
                k %= len(ring)
                opts.append(ring[k:] + ring[:k] + [ring[k]])
                rev = ring[::-1]
                kk = rev.index(ring[k])
                opts.append(rev[kk:] + rev[:kk] + [rev[kk]])
            else:
                opts.append(w[k:])
                opts.append(w[:k + 1][::-1])
        opts = [o for o in opts if len(o) > 1]
        if not opts:
            print(f"  ! gap before way {wid} (chain end {end})")
            # attach nearest end anyway; gaps are reported, and bridged geometrically
            opts = [w, w[::-1]]
            chain.append(None)
        best = None
        for o in opts:
            if nxt is None:
                cand = o
            else:
                hit = next((i for i, n in enumerate(o) if n in nxt and i > 0), None)
                if hit is None:
                    continue
                cand = o[:hit + 1]
            if best is None or (nxt is None and len(cand) > len(best)):
                best = cand
        if best is None:
            best = max(opts, key=len)
        chain.extend(best[1:] if chain[-1] is not None else best)
    return [n for n in chain if n is not None]


# ---------------------------------------------------------------- terrain (ČÚZK DMR 5G)
def read_tiff_f32(data):
    """Minimal reader for an uncompressed single-band float32 TIFF (strips or tiles)."""
    bo = "<" if data[:2] == b"II" else ">"
    (ifd,) = struct.unpack(bo + "I", data[4:8])
    (n,) = struct.unpack(bo + "H", data[ifd:ifd + 2])
    sizes = {1: 1, 3: 2, 4: 4, 11: 4, 12: 8, 16: 8}
    fmt = {1: "B", 3: "H", 4: "I", 11: "f", 12: "d", 16: "Q"}
    tags = {}
    for i in range(n):
        tag, typ, cnt, val = struct.unpack(bo + "HHI4s", data[ifd + 2 + i * 12: ifd + 14 + i * 12])
        if typ not in fmt:
            continue
        size = sizes[typ] * cnt
        raw = val if size <= 4 else data[struct.unpack(bo + "I", val)[0]:][:size]
        tags[tag] = struct.unpack(bo + fmt[typ] * cnt, raw[:size])
    w, h = tags[256][0], tags[257][0]
    if tags.get(259, (1,))[0] != 1 or tags.get(258, (32,))[0] != 32:
        raise ValueError("expected an uncompressed float32 TIFF")
    out = [[0.0] * w for _ in range(h)]
    if 324 in tags:  # tiled layout
        tw, th = tags[322][0], tags[323][0]
        across = (w + tw - 1) // tw
        for t, off in enumerate(tags[324]):
            ty, tx = divmod(t, across)
            vals = struct.unpack(bo + "f" * (tw * th), data[off:off + tw * th * 4])
            for r in range(th):
                y = ty * th + r
                if y >= h:
                    break
                for c in range(tw):
                    x = tx * tw + c
                    if x < w:
                        out[y][x] = vals[r * tw + c]
    else:  # strips
        rps = tags.get(278, (h,))[0]
        for k, off in enumerate(tags[273]):
            rows = min(rps, h - k * rps)
            vals = struct.unpack(bo + "f" * (w * rows), data[off:off + w * rows * 4])
            for r in range(rows):
                out[k * rps + r] = list(vals[r * w:(r + 1) * w])
    return out


def fetch_terrain(P, lat_min, lat_max, lon_min, lon_max):
    """Bare-earth elevation grid (~DEM_STEP m) for the bbox, cached in raw/terrain.*"""
    nx = int((lon_max - lon_min) * P.kx / DEM_STEP) + 1
    ny = int((lat_max - lat_min) * P.ky / DEM_STEP) + 1
    path, meta_path = os.path.join(RAW, "terrain.tif"), os.path.join(RAW, "terrain.json")
    if not (os.path.exists(path) and os.path.exists(meta_path)) or REFRESH:
        q = urllib.parse.urlencode({
            "bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}", "bboxSR": 4326, "imageSR": 4326,
            "size": f"{nx},{ny}", "format": "tiff", "pixelType": "F32", "noData": -9999,
            "interpolation": "RSP_BilinearInterpolation", "compression": "None", "f": "json"})
        print(f"terrain: requesting {nx}x{ny} grid")
        hdr = {"User-Agent": "tram-game-prototype/0.1"}
        with urllib.request.urlopen(urllib.request.Request(DEM_SERVICE + "?" + q, headers=hdr), timeout=300) as r:
            meta = json.loads(r.read())
        if "href" not in meta:
            raise SystemExit(f"terrain export failed: {meta}")
        with urllib.request.urlopen(urllib.request.Request(meta["href"], headers=hdr), timeout=300) as r:
            tif = r.read()
        with open(path, "wb") as f:
            f.write(tif)
        with open(meta_path, "w") as f:
            json.dump(meta, f)
    with open(path, "rb") as f:
        grid = read_tiff_f32(f.read())
    with open(meta_path) as f:
        ext = json.load(f)["extent"]
    h, w = len(grid), len(grid[0])
    dlon = (ext["xmax"] - ext["xmin"]) / w
    dlat = (ext["ymax"] - ext["ymin"]) / h
    # fill nodata cells from their neighbours
    valid = [[v > -1000 for v in row] for row in grid]
    for _ in range(100):
        holes = 0
        for y in range(h):
            for x in range(w):
                if valid[y][x]:
                    continue
                acc = [grid[yy][xx] for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1))
                       if 0 <= yy < h and 0 <= xx < w and valid[yy][xx]]
                if acc:
                    grid[y][x] = sum(acc) / len(acc)
                    valid[y][x] = True
                else:
                    holes += 1
        if not holes:
            break
    flat = [v for row in grid for v in row]
    base = math.floor(min(flat))
    packed = struct.pack("<" + "h" * len(flat), *[max(-32768, min(32767, round((v - base) * 10))) for v in flat])
    x0, y0 = P(ext["ymax"] - dlat / 2, ext["xmin"] + dlon / 2)  # centre of the north-west cell
    print(f"terrain: {w}x{h} cells, {min(flat):.1f}-{max(flat):.1f} m")
    return {"x0": round(x0, 2), "y0": round(y0, 2), "dx": round(dlon * P.kx, 4), "dy": round(-dlat * P.ky, 4),
            "nx": w, "ny": h, "base": base, "scale": 0.1, "data": base64.b64encode(packed).decode()}


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    route = overpass(f"route_{OSM_RELATION}", Q_ROUTE)
    rel = next(e for e in route["elements"] if e["type"] == "relation")
    nodes = {e["id"]: (e["lat"], e["lon"]) for e in route["elements"] if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in route["elements"] if e["type"] == "way"}
    bridge_pairs, tunnel_pairs = set(), set()
    for e in route["elements"]:
        if e["type"] != "way":
            continue
        t = e.get("tags", {})
        pairs = None
        if t.get("bridge") not in (None, "no"):
            pairs = bridge_pairs
        # underpasses / tunnels / covered track: the bare-earth DEM has the embankment above
        elif t.get("tunnel") not in (None, "no") or t.get("covered") == "yes" or t.get("layer", "0").lstrip("-").isdigit() and int(t.get("layer", "0")) < 0:
            pairs = tunnel_pairs
        if pairs is not None:
            for a, b in zip(e["nodes"], e["nodes"][1:]):
                pairs.update({(a, b), (b, a)})

    path_ids = chain_route(rel, ways)
    # drop consecutive duplicates
    path_ids = [n for i, n in enumerate(path_ids) if i == 0 or n != path_ids[i - 1]]
    lat0 = sum(nodes[n][0] for n in path_ids) / len(path_ids)
    lon0 = sum(nodes[n][1] for n in path_ids) / len(path_ids)
    P = Proj(lat0, lon0)
    pts = [P(*nodes[n]) for n in path_ids]
    for i in range(1, len(pts)):
        if dist(pts[i - 1], pts[i]) > 400:
            print(f"  ! long segment {dist(pts[i-1], pts[i]):.0f} m at index {i}")
    path = Polyline(pts)
    print(f"route: {len(pts)} nodes, {path.length/1000:.2f} km")
    def spans(pairs, min_len):
        out = []
        for i in range(len(path_ids) - 1):
            if (path_ids[i], path_ids[i + 1]) in pairs:
                if out and abs(out[-1][1] - path.s[i]) < 1:
                    out[-1][1] = path.s[i + 1]
                else:
                    out.append([path.s[i], path.s[i + 1]])
        return [[round(a, 1), round(b, 1)] for a, b in out if b - a > min_len]
    bridges = spans(bridge_pairs, 8)
    tunnels = spans(tunnel_pairs, 3)
    print(f"route bridges: {bridges}  underpasses/tunnels: {tunnels}")

    # ---------------- track network
    tracks = overpass("tracks", Q_TRACKS)
    tnodes = {e["id"]: e for e in tracks["elements"] if e["type"] == "node"}
    tways = [e for e in tracks["elements"] if e["type"] == "way"]
    adj = defaultdict(set)
    for w in tways:
        ns = w["nodes"]
        for a, b in zip(ns, ns[1:]):
            adj[a].add(b)
            adj[b].add(a)
    tpos = {nid: P(e["lat"], e["lon"]) for nid, e in tnodes.items()}
    for nid in path_ids:
        tpos.setdefault(nid, P(*nodes[nid]))

    def walk(start, first, length=14.0):
        """Follow track from `start` through `first`, taking the straightest continuation."""
        prev, cur = start, first
        travelled = dist(tpos[start], tpos[first])
        while travelled < length:
            d = norm((tpos[cur][0] - tpos[prev][0], tpos[cur][1] - tpos[prev][1]))
            cands = [n for n in adj[cur] if n != prev and n in tpos]
            if not cands:
                break
            nxt = min(cands, key=lambda n: angle_between(d, (tpos[n][0] - tpos[cur][0], tpos[n][1] - tpos[cur][1])))
            travelled += dist(tpos[cur], tpos[nxt])
            prev, cur = cur, nxt
        return tpos[cur]

    switches = []
    for i in range(1, len(path_ids) - 1):
        nid = path_ids[i]
        others = [n for n in adj[nid] if n not in (path_ids[i - 1], path_ids[i + 1]) and n in tpos]
        if not others:
            continue
        here = tpos[nid]
        d_in = norm((here[0] - tpos[path_ids[i - 1]][0], here[1] - tpos[path_ids[i - 1]][1]))
        route_tgt = walk(nid, path_ids[i + 1])
        v_route = (route_tgt[0] - here[0], route_tgt[1] - here[1])
        for o in others:
            alt_tgt = walk(nid, o)
            v_alt = (alt_tgt[0] - here[0], alt_tgt[1] - here[1])
            if angle_between(v_alt, v_route) > 50 or angle_between(v_alt, d_in) > 60:
                continue  # diamond crossing or trailing switch
            dev_route = angle_between(d_in, v_route)
            dev_alt = angle_between(d_in, v_alt)
            cross_r = d_in[0] * v_route[1] - d_in[1] * v_route[0]
            cross_a = d_in[0] * v_alt[1] - d_in[1] * v_alt[0]
            route_side = "left" if cross_r > cross_a else "right"
            s = path.s[i]
            if switches and s - switches[-1]["s"] < 3:
                continue
            switches.append({
                "s": round(s, 1),
                "routeDiverging": dev_route > dev_alt,   # route takes the more curved branch
                "routeSide": route_side,                 # route branch is left/right of the alternative
                "alt": [round(alt_tgt[0], 1), round(alt_tgt[1], 1)],
            })
            break
    print(f"facing switches on route: {len(switches)}")

    # merge ways into continuous chains (split only at junctions/switches and bridge ends),
    # so the client can smooth each chain without kinks at way boundaries
    edge_bridge = {}
    for w in tways:
        b = w.get("tags", {}).get("bridge") not in (None, "no")
        for a, c in zip(w["nodes"], w["nodes"][1:]):
            if a in tpos and c in tpos and a != c:
                edge_bridge[frozenset((a, c))] = b
    used = set()

    def extend(chain, flag):
        while True:
            end, prev = chain[-1], chain[-2]
            if len(adj[end]) != 2:
                return
            nxt = next((n for n in adj[end] if n != prev), None)
            e = frozenset((end, nxt))
            if nxt is None or e in used or edge_bridge.get(e) != flag:
                return
            used.add(e)
            chain.append(nxt)
            if nxt == chain[0]:
                return

    track_lines = []
    for e, flag in edge_bridge.items():
        if e in used:
            continue
        used.add(e)
        a, c = tuple(e)
        chain = [a, c]
        extend(chain, flag)
        chain.reverse()
        extend(chain, flag)
        t = {"p": [[round(tpos[n][0], 2), round(tpos[n][1], 2)] for n in chain]}
        if flag:
            t["b"] = 1
        track_lines.append(t)
    print(f"track chains: {len(track_lines)} (from {len(tways)} ways)")

    # opposite direction of the line, for oncoming trams
    path_back = []
    if Q_ROUTE_BACK:
        back = overpass(f"route_{OSM_RELATION_BACK}", Q_ROUTE_BACK)
        brel = next(e for e in back["elements"] if e["type"] == "relation")
        bnodes = {e["id"]: (e["lat"], e["lon"]) for e in back["elements"] if e["type"] == "node"}
        bways = {e["id"]: e["nodes"] for e in back["elements"] if e["type"] == "way"}
        bids = chain_route(brel, bways)
        bids = [n for i, n in enumerate(bids) if i == 0 or n != bids[i - 1]]
        path_back = [[round(x, 2), round(y, 2)] for x, y in (P(*bnodes[n]) for n in bids)]
    print(f"opposite route: {len(path_back)} nodes")

    # ---------------- crossings and signals
    pts_osm = overpass("points", Q_POINTS)
    sig_s, cross_s = [], []
    for e in pts_osm["elements"]:
        p = P(e["lat"], e["lon"])
        s, d, side = path.project(p)
        if s is None:
            continue
        t = e.get("tags", {})
        if t.get("highway") == "traffic_signals" and d < 30:
            sig_s.append(s)
        elif t.get("railway") in ("tram_level_crossing", "level_crossing") and d < 4:
            cross_s.append(s)
        elif t.get("railway") in ("tram_crossing", "crossing") or t.get("highway") == "crossing":
            if d < 8:
                cross_s.append(s)
    sig_s.sort()
    clusters = []
    for s in sig_s:
        if clusters and s - clusters[-1][-1] < 45:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    signals = []
    for c in clusters:
        s0 = min(c) - 6
        if s0 < 30 or s0 > path.length - 30:
            continue
        signals.append({"s": round(s0, 1), "cross": round((min(c) + max(c)) / 2, 1)})
    cross_s.sort()
    crossings = []
    for s in cross_s:
        if crossings and s - crossings[-1] < 25:
            continue
        crossings.append(round(s, 1))
    print(f"signals: {len(signals)}, crossings: {len(crossings)}")

    # ---------------- GTFS
    z = zipfile.ZipFile(GTFS_ZIP)

    def rd(name):
        return csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"))

    ymd = SERVICE_DATE.strftime("%Y%m%d")
    wd = SERVICE_DATE.strftime("%A").lower()
    active = set()
    for c in rd("calendar.txt"):
        if c["start_date"] <= ymd <= c["end_date"] and c[wd] == "1":
            active.add(c["service_id"])
    for c in rd("calendar_dates.txt"):
        if c["date"] == ymd:
            (active.add if c["exception_type"] == "1" else active.discard)(c["service_id"])

    trips = [t for t in rd("trips.txt")
             if t["route_id"] == GTFS_ROUTE and t["direction_id"] == GTFS_DIRECTION
             and t["trip_headsign"] == GTFS_HEADSIGN and t["service_id"] in active]
    shape = Counter(t["shape_id"] for t in trips).most_common(1)[0][0]
    trips = [t for t in trips if t["shape_id"] == shape]
    trip_ids = {t["trip_id"] for t in trips}
    print(f"gtfs: {len(trips)} trips on {ymd}, shape {shape}")

    st = defaultdict(list)
    for r in rd("stop_times.txt"):
        if r["trip_id"] in trip_ids:
            st[r["trip_id"]].append(r)

    def secs(hms):
        h, m, s = (int(x) for x in hms.split(":"))
        return h * 3600 + m * 60 + s

    patterns = Counter(tuple(r["stop_id"] for r in sorted(v, key=lambda r: int(r["stop_sequence"]))) for v in st.values())
    pattern = patterns.most_common(1)[0][0]
    stop_rows = {}
    for r in rd("stops.txt"):
        if r["stop_id"] in pattern:
            stop_rows[r["stop_id"]] = r

    # request stops: take flags from the first trip with that pattern
    flags = {}
    timetable = []
    for tid, rows in st.items():
        rows.sort(key=lambda r: int(r["stop_sequence"]))
        if tuple(r["stop_id"] for r in rows) != pattern:
            continue
        if not flags:
            flags = {r["stop_id"]: (r["pickup_type"] == "3" or r["drop_off_type"] == "3") for r in rows}
        timetable.append([secs(r["departure_time"]) for r in rows])
    timetable.sort(key=lambda t: t[0])

    # tram lines serving each platform (for the stop sign's line plate)
    tram_routes = {r["route_id"]: r["route_short_name"] for r in rd("routes.txt")
                   if r["route_type"] == "0" and r.get("is_night") != "1"}  # day trams only
    stop_lines = defaultdict(set)
    for r in rd("route_stops.txt"):
        if r["stop_id"] in pattern and r["route_id"] in tram_routes:
            stop_lines[r["stop_id"]].add(tram_routes[r["route_id"]])

    stops = []
    s_last = 0.0
    for sid in pattern:
        r = stop_rows[sid]
        p = P(float(r["stop_lat"]), float(r["stop_lon"]))
        s, d, side = path.project(p, s_min=s_last - 5, radius=2)
        if s is None or d > 60:
            s, d, side = path.project(p, s_min=s_last - 5, radius=40)
        lines = sorted(stop_lines[sid] | {LINE}, key=lambda x: (len(x), x))
        stops.append({"name": r["stop_name"], "s": round(s, 1), "off": round(d, 1),
                      "side": "left" if side > 0 else "right", "request": flags.get(sid, False), "lines": lines})
        s_last = s
    print(f"stops: {len(stops)}  first {stops[0]['name']} @ {stops[0]['s']}  last {stops[-1]['name']} @ {stops[-1]['s']}")
    far = [st_ for st_ in stops if st_["off"] > 25]
    for st_ in far:
        print(f"  ! stop {st_['name']} is {st_['off']} m from the track")
    if len(far) > len(stops) * 0.15:
        raise SystemExit(f"GTFS stops do not match OSM relation {OSM_RELATION} (headsign {GTFS_HEADSIGN}); try --headsign")

    # ---------------- scenery
    def ring(geom):
        out = []
        for g in geom:
            p = P(g["lat"], g["lon"])
            if not out or dist(out[-1], p) > 0.6:
                out.append(p)
        if len(out) > 2 and dist(out[0], out[-1]) < 0.6:
            out.pop()
        return [[round(x, 1), round(y, 1)] for x, y in out]

    bjs = overpass("buildings", Q_BUILDINGS)
    buildings = []
    for e in bjs["elements"]:
        t = e.get("tags", {})
        if t.get("building") in ("roof", "construction", "no") or "geometry" not in e:
            continue
        r = ring(e["geometry"])
        if len(r) < 3:
            continue
        h = None
        try:
            if "height" in t:
                h = float(t["height"].split()[0].replace(",", "."))
            elif "building:levels" in t:
                h = float(t["building:levels"].split(";")[0]) * 3.2 + 1.5
        except ValueError:
            pass
        if h is None:
            kind = t.get("building")
            if kind in ("garage", "garages", "shed", "kiosk", "hut", "service", "carport"):
                h = 3.0
            elif kind in ("house", "detached", "semidetached_house", "bungalow"):
                h = 7.0 + (e["id"] % 3)
            elif kind in ("church", "cathedral"):
                h = 22.0
            else:
                h = 14.0 + (e["id"] % 7) * 1.6
        if t.get("building:min_level") or t.get("min_height"):
            continue  # overhangs/passages: skip in the prototype
        buildings.append({"p": r, "h": round(min(h, 120), 1), "k": t.get("building", "yes")[:12]})
    print(f"buildings: {len(buildings)}")

    widths = {"motorway": 16, "trunk": 14, "primary": 12, "secondary": 10, "tertiary": 8, "primary_link": 7,
              "secondary_link": 7, "tertiary_link": 6, "trunk_link": 7, "residential": 6.5, "unclassified": 6,
              "living_street": 5, "service": 4, "pedestrian": 6, "footway": 2.5}
    rjs = overpass("roads", Q_ROADS)
    roads = []
    for e in rjs["elements"]:
        t = e.get("tags", {})
        if "geometry" not in e or t.get("tunnel") in ("yes", "building_passage") or t.get("area") == "yes":
            continue
        line = [P(g["lat"], g["lon"]) for g in e["geometry"]]
        w = widths.get(t.get("highway"), 5)
        if "lanes" in t:
            try:
                w = max(w, int(t["lanes"].split(";")[0]) * 3.2)
            except ValueError:
                pass
        hw = t.get("highway")
        road = {"p": [[round(x, 1), round(y, 1)] for x, y in line], "w": w,
                "f": 1 if hw in ("footway", "pedestrian", "living_street") else 0,
                "c": 1 if hw in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                                 "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
                and t.get("service") is None and t.get("access") not in ("no", "private", "destination") else 0}
        if t.get("bridge") not in (None, "no"):
            road["b"] = 1
        ow = t.get("oneway")
        if ow in ("yes", "true", "1") or t.get("junction") == "roundabout":
            road["o"] = 1
        elif ow == "-1":
            road["o"] = -1
        roads.append(road)
    print(f"roads: {len(roads)}")

    gjs = overpass("green", Q_GREEN, optional=True)
    green = []
    for e in gjs["elements"]:
        if "geometry" not in e:
            continue
        t = e.get("tags", {})
        r = ring(e["geometry"])
        if len(r) >= 3:
            wood = t.get("landuse") == "forest" or t.get("natural") in ("wood", "scrub")
            green.append({"p": r, "t": "wood" if wood else "grass"})

    wjs = overpass("water", Q_WATER, optional=True)
    water = []
    for e in wjs["elements"]:
        if e["type"] == "way" and "geometry" in e:
            r = ring(e["geometry"])
            if len(r) >= 3:
                water.append(r)
        elif e["type"] == "relation":
            # assemble outer rings from member ways
            segs = [[(g["lat"], g["lon"]) for g in m["geometry"]] for m in e.get("members", [])
                    if m["type"] == "way" and m.get("role") == "outer" and "geometry" in m]
            while segs:
                cur = segs.pop(0)
                changed = True
                while changed and cur[0] != cur[-1]:
                    changed = False
                    for j, sg in enumerate(segs):
                        if sg[0] == cur[-1]:
                            cur += sg[1:]
                        elif sg[-1] == cur[-1]:
                            cur += sg[::-1][1:]
                        elif sg[-1] == cur[0]:
                            cur = sg + cur[1:]
                        elif sg[0] == cur[0]:
                            cur = sg[::-1] + cur[1:]
                        else:
                            continue
                        segs.pop(j)
                        changed = True
                        break
                if cur[0] == cur[-1] and len(cur) > 3:
                    water.append(ring([{"lat": a, "lon": b} for a, b in cur]))
    print(f"green: {len(green)}, water: {len(water)}")

    lats = [nodes[n][0] for n in path_ids]
    lons = [nodes[n][1] for n in path_ids]
    mlat, mlon = DEM_MARGIN / P.ky, DEM_MARGIN / P.kx
    terrain = fetch_terrain(P, min(lats) - mlat, max(lats) + mlat, min(lons) - mlon, max(lons) + mlon)

    out = {
        "line": LINE,
        "name": rel["tags"].get("name"),
        "origin": [lat0, lon0],
        "attribution": "Map data © OpenStreetMap contributors (ODbL). Timetable: PID GTFS, data.pid.cz (CC BY 4.0). "
                       "Terrain: ČÚZK DMR 5G (CC BY 4.0).",
        "path": [[round(x, 2), round(y, 2)] for x, y in pts],
        "bridges": bridges,
        "tunnels": tunnels,
        "terrain": terrain,
        "stops": stops,
        "timetable": timetable,
        "switches": switches,
        "signals": signals,
        "crossings": crossings,
        "tracks": track_lines,
        "pathBack": path_back,
        "buildings": buildings,
        "roads": roads,
        "green": green,
        "water": water,
    }
    dst = os.path.join(OUT, f"line{LINE}.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {dst} ({os.path.getsize(dst)/1e6:.2f} MB)")
    # index of built lines for the menu
    idx_path = os.path.join(OUT, "lines.json")
    idx = {}
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as f:
            idx = {l["line"]: l for l in json.load(f)}
    idx[LINE] = {"line": LINE, "from": stops[0]["name"], "to": stops[-1]["name"],
                 "km": round(path.length / 1000, 1), "stops": len(stops)}
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(sorted(idx.values(), key=lambda l: int(l["line"])), f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
