"""Posted speeds and dedicated track along a built line, from the OSM tram ways (the data
OpenRailwayMap shows: `maxspeed` on railway=tram ways).

Every 5 m along the route: the `maxspeed` of the OSM tram way under the track (0 = untagged), and
whether the track is dedicated (no vehicle road along it: its own corridor, where curves may be
canted). Reads the Overpass cache written by build_line.py, writes `speed` into data/lineN.json:
  {"step": 5, "osm": [km/h or 0, ...], "dedicated": [0/1, ...], "source": "..."}

Usage:  python tools/osm_speeds.py --line 22
"""
import glob
import json
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
STEP = 5.0

dst = os.path.join(ROOT, "data", f"line{LINE}.json")
line = json.load(open(dst, encoding="utf-8"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from geo import Frame  # noqa: E402
from atomic import replacing  # noqa: E402
F = Frame()  # the city frame: the one conversion (tools/geo.py)

# the Overpass cache of this line's tracks (a run like 9 -> 10 has its own folder, line 22 the raw/ root;
# another line's answers there are not this line's, #87)
cands = glob.glob(os.path.join(ROOT, "raw", f"run{LINE}-*", "tracks.json")) + [
    os.path.join(ROOT, "raw", f"line{LINE}", "tracks.json")] + ([os.path.join(ROOT, "raw", "tracks.json")] if LINE == "22" else [])
src = next((p for p in cands if os.path.exists(p)), None) or sys.exit(f"no cached tracks for line {LINE}: run build_line.py first")
els = json.load(open(src, encoding="utf-8"))["elements"]
nodes = {e["id"]: tuple(float(v) for v in F.xy(e["lat"], e["lon"])) for e in els if e["type"] == "node"}


def speed(tags):
    v = (tags or {}).get("maxspeed", "")
    try:
        return int(str(v).split(";")[0].split()[0])
    except (ValueError, IndexError):  # untagged, "none", "walk"
        return 0


# way segments with their speed, in a 20 m grid
CELL = 20.0
grid = {}
for w in els:
    if w["type"] != "way":
        continue
    v = speed(w.get("tags"))
    pts = [nodes[n] for n in w["nodes"] if n in nodes]
    for a, b in zip(pts, pts[1:]):
        for ix in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
            for iy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                grid.setdefault((ix, iy), []).append((a, b, v))

# vehicle roads (centre line + width) for the dedicated test
roads = [r for r in line["roads"] if not r.get("f") and r.get("c")]
rgrid = {}
for r in roads:
    half = r.get("w", 6) / 2
    for a, b in zip(r["p"], r["p"][1:]):
        for ix in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
            for iy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                rgrid.setdefault((ix, iy), []).append((a, b, half))


def seg_dist(p, a, b):
    sx, sy = b[0] - a[0], b[1] - a[1]
    l2 = sx * sx + sy * sy or 1e-9
    u = max(0.0, min(1.0, ((p[0] - a[0]) * sx + (p[1] - a[1]) * sy) / l2))
    return math.hypot(a[0] + sx * u - p[0], a[1] + sy * u - p[1]), sx, sy


path = line["path"]
acc = [0.0]
for a, b in zip(path, path[1:]):
    acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
osm, ded = [], []
i = 0
s = 0.0
while s <= acc[-1]:
    while i < len(path) - 2 and acc[i + 1] < s:
        i += 1
    a, b = path[i], path[i + 1]
    seg = acc[i + 1] - acc[i] or 1e-9
    u = (s - acc[i]) / seg
    p = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
    hx, hy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
    key = (int(p[0] // CELL), int(p[1] // CELL))
    best, bd = 0, 2.0
    for ca, cb, v in grid.get(key, []):
        d, sx, sy = seg_dist(p, ca, cb)
        l = math.hypot(sx, sy) or 1
        if d < bd and abs((sx * hx + sy * hy) / l) > 0.7:
            best, bd = v, d
    osm.append(best)
    street = False
    for ix in (key[0] - 1, key[0], key[0] + 1):
        for iy in (key[1] - 1, key[1], key[1] + 1):
            for ca, cb, half in rgrid.get((ix, iy), []):
                if seg_dist(p, ca, cb)[0] < half + 1.0:
                    street = True
    ded.append(0 if street else 1)
    s += STEP

# dedicated stretches shorter than 60 m are junction gaps, not corridors
n = len(ded)
k = 0
while k < n:
    if ded[k]:
        j = k
        while j < n and ded[j]:
            j += 1
        if (j - k) * STEP < 60:
            for m in range(k, j):
                ded[m] = 0
        k = j
    else:
        k += 1

line["speed"] = {"step": STEP, "osm": osm, "dedicated": ded, "source": "OpenStreetMap railway=tram maxspeed (as shown by OpenRailwayMap)"}
# (written whole and renamed: tools/rebuild.py runs other steps that read this file at the same time)
with replacing(dst, "w", encoding="utf-8") as fh:
    json.dump(line, fh, ensure_ascii=False, separators=(",", ":"))
tagged = sum(1 for v in osm if v)
print(f"line {LINE}: {len(osm)} samples, maxspeed on {100 * tagged / len(osm):.0f} % "
      f"({', '.join(f'{v}: {osm.count(v)}' for v in sorted(set(osm)) if v)}), dedicated {100 * sum(ded) / n:.0f} %")
