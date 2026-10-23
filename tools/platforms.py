"""Tram platforms of both directions along a built line, from the cached OSM platforms.

build_line.py keeps only where our stops' platforms begin and end (p0/p1). This adds every tram
platform within 12 m of the route or the opposite one, as drawn in OSM: usually a line along the
platform (sometimes an area), with its tags. The game builds the platforms from them, curved along
the track, on both sides (where the surveyed streets (DTM) have the platform, the survey draws it).

Usage:  python tools/platforms.py --line 17      (reads raw/lineN/platforms.json; fetches it from
        Overpass when missing or with --fetch)
Adds "platforms": [{"p": [[x, y], ...], "area": 0|1, "w": width, "shelter": 0|1, "name": ...}] to data/lineN.json.
"""
import json
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"

dst = os.path.join(ROOT, "data", f"line{LINE}.json")
line = json.load(open(dst, encoding="utf-8"))
LAT0, LON0 = line["origin"]
KX, KY = math.cos(math.radians(LAT0)) * 111320.0, 110574.0
src = os.path.join(ROOT, "raw", f"line{LINE}", "platforms.json")
if "--fetch" in sys.argv:
    # platform ways in ~800 m boxes along both directions' paths (small cached queries, slow, retried:
    # one query for the whole line came back empty); the 12 m filter below picks the ones on our tracks
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
    from overpass import pieces, query
    els = {}
    # (the opposite direction only where it runs off our path: elsewhere our boxes, padded 40 m, hold it)
    ours = [(p[0], p[1]) for p in line["path"]]
    off = lambda q: min((q[0] - a) ** 2 + (q[1] - b) ** 2 for a, b in ours[::2]) > 50 ** 2  # noqa: E731
    runs, cur = [line["path"]], []
    for q in line.get("pathBack", []):
        if off(q):
            cur.append(q)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    for path in runs:
        boxes = pieces([(LAT0 + y / KY, LON0 + x / KX) for x, y, *_ in path])
        for i, bb in enumerate(boxes):
            js = query(f"[out:json][timeout:90];(way({bb})[public_transport=platform];way({bb})[railway=platform];);out tags geom qt;")
            for e in js["elements"]:
                els[(e["type"], e["id"])] = e
            print(f"  piece {i + 1}/{len(boxes)}: {len(js['elements'])} ways", flush=True)
    os.makedirs(os.path.dirname(src), exist_ok=True)
    json.dump({"elements": list(els.values())}, open(src, "w", encoding="utf-8"))
    print(f"fetched {len(els)} platform ways")
if not os.path.exists(src):
    src = os.path.join(ROOT, "raw", "platforms.json")
osm = json.load(open(src, encoding="utf-8"))


def P(g):
    return [round((g["lon"] - LON0) * KX, 2), round((g["lat"] - LAT0) * KY, 2)]


# both directions' paths as segments in 20 m cells
cells = {}
for path in (line["path"], line.get("pathBack", [])):
    for a, b in zip(path, path[1:]):
        for cx in range(int(min(a[0], b[0]) // 20) - 1, int(max(a[0], b[0]) // 20) + 2):
            for cy in range(int(min(a[1], b[1]) // 20) - 1, int(max(a[1], b[1]) // 20) + 2):
                cells.setdefault((cx, cy), []).append((a, b))


def dist(q):
    best = math.inf
    for a, b in cells.get((int(q[0] // 20), int(q[1] // 20)), ()):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / l2))
        best = min(best, math.hypot(q[0] - a[0] - dx * t, q[1] - a[1] - dy * t))
    return best


# PID GTFS: every tram platform (a stop of a tram route, one per direction) with its exact position,
# name, platform code and lines; those within 10 m of either path
import csv  # noqa: E402
import io  # noqa: E402
import zipfile  # noqa: E402

z = zipfile.ZipFile(os.path.join(ROOT, "raw", "PID_GTFS.zip"))
rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), "utf-8-sig"))  # noqa: E731
trams = {r["route_id"]: r["route_short_name"] for r in rd("routes.txt") if r["route_type"] == "0" and r.get("is_substitute_transport") != "1"}
lines_of = {}
for r in rd("route_stops.txt"):
    if r["route_id"] in trams:
        lines_of.setdefault(r["stop_id"], set()).add(trams[r["route_id"]])
gtfs = []
for r in rd("stops.txt"):
    if r["stop_id"] not in lines_of:
        continue
    q = [round((float(r["stop_lon"]) - LON0) * KX, 2), round((float(r["stop_lat"]) - LAT0) * KY, 2)]
    if dist(q) <= 10:
        gtfs.append({"id": r["stop_id"], "name": r["stop_name"], "code": r["platform_code"], "q": q,
                     "lines": sorted(lines_of[r["stop_id"]], key=lambda x: (len(x), x))})

out = []
for e in osm["elements"]:
    t = e.get("tags", {})
    if "geometry" not in e or len(e["geometry"]) < 2:
        continue
    # tram platforms only (a bus-only platform beside the track is not ours)
    if t.get("tram") != "yes" and not (t.get("railway") == "platform" and t.get("bus") != "yes"):
        continue
    pts = [P(g) for g in e["geometry"]]
    if min(dist(q) for q in pts) > 12:
        continue
    area = int(pts[0] == pts[-1] and len(pts) > 3)
    try:
        w = float(str(t.get("width", "")).replace(",", ".").split()[0])
    except (ValueError, IndexError):
        w = 0
    out.append({"p": pts[:-1] if area else pts, "area": area, "w": w,
                "shelter": int(t.get("shelter") == "yes"), "name": t.get("name", "")})
# each OSM platform takes the GTFS platform standing on it (within 4 m of its line or area, else the
# nearest within 25 m); GTFS platforms without an OSM one are platforms of their own ("gtfs": 1)
def seg_dist(q, pts):
    best = math.inf
    for a, b in zip(pts, pts[1:] + ([pts[0]] if len(pts) > 2 else [])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / l2))
        best = min(best, math.hypot(q[0] - a[0] - dx * t, q[1] - a[1] - dy * t))
    return best


used = set()
for pl in out:
    cand = sorted((seg_dist(g["q"], pl["p"]), i) for i, g in enumerate(gtfs))
    if cand and cand[0][0] < 25 and cand[0][1] not in used:
        g = gtfs[cand[0][1]]
        used.add(cand[0][1])
        pl.update({"name": g["name"], "code": g["code"], "stop": g["q"], "lines": g["lines"], "id": g["id"]})
for i, g in enumerate(gtfs):
    if i not in used:
        out.append({"p": [g["q"]], "gtfs": 1, "area": 0, "w": 0, "shelter": 0, "name": g["name"], "code": g["code"],
                    "stop": g["q"], "lines": g["lines"], "id": g["id"]})
line["platforms"] = out
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(line, fh, ensure_ascii=False, separators=(",", ":"))
print(f"line {LINE}: {len(out)} tram platforms ({sum(p['area'] for p in out)} OSM areas, {sum(p.get('gtfs', 0) for p in out)} "
      f"from GTFS only); {len(gtfs)} PID tram platforms, {len(used)} matched to OSM")
