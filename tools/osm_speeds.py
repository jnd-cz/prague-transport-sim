# SPDX-License-Identifier: AGPL-3.0-or-later
"""Posted speeds and dedicated track along a built line, from the OSM tram ways (the data
OpenRailwayMap shows: `maxspeed` on railway=tram ways).

Every 5 m along the route: the `maxspeed` of the OSM tram way under the track (0 = untagged), and
whether the track is dedicated (no vehicle road along it: its own corridor, where curves may be
canted). Reads the Overpass cache written by build_line.py, writes `speed` into data/lineN.json:
  {"step": 5, "osm": [km/h or 0, ...], "dedicated": [0/1, ...], "source": "..."}
A posted speed in data/truth.json `postedSpeeds` (seen by the user, keyed by the OSM way id) holds over that way's
`maxspeed` (#612); each one applied is printed.

Usage:  python tools/osm_speeds.py --line 22
"""
import glob
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = 5.0
CELL = 20.0  # m: the grids' cell
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)


def speed(tags):
    v = (tags or {}).get("maxspeed", "")
    try:
        return int(str(v).split(";")[0].split()[0])
    except (ValueError, IndexError):  # untagged, "none", "walk"
        return 0


def corrections(truth):
    """data/truth.json `postedSpeeds` by OSM way id."""
    return {f["way"]: f for f in truth.get("postedSpeeds", [])}


def way_speeds(els, fixes, log=print):
    """Each tram way's posted speed: its `maxspeed`, or the correction for it. A correction holds whatever OSM tags;
    the log says where OSM now tags the same (no longer needed) and where it tags neither the speed the fact corrects
    nor the corrected one (the way was edited since: look at it again)."""
    out = {}
    for w in els:
        if w["type"] != "way":
            continue
        v = speed(w.get("tags"))
        f = fixes.get(w["id"])
        if f:
            if v == f["maxspeed"]:
                log(f"way {w['id']}: OSM tags {v} as {f['id']} says: the correction is no longer needed")
            elif v != f["osm"]:
                log(f"way {w['id']}: OSM tags {v or 'none'}, not the {f['osm']} {f['id']} corrects: "
                    f"{f['maxspeed']} holds, look at the way again")
            else:
                log(f"way {w['id']}: {f['maxspeed']} over OSM's {v} ({f['id']})")
            v = f["maxspeed"]
        out[w["id"]] = v
    return out


def seg_dist(p, a, b):
    sx, sy = b[0] - a[0], b[1] - a[1]
    l2 = sx * sx + sy * sy or 1e-9
    u = max(0.0, min(1.0, ((p[0] - a[0]) * sx + (p[1] - a[1]) * sy) / l2))
    return math.hypot(a[0] + sx * u - p[0], a[1] + sy * u - p[1]), sx, sy


def along(path, els, nodes, roads, speeds):
    """speed.osm and speed.dedicated every STEP m of path, and how many samples each way gave."""
    # way segments with their speed, in a 20 m grid
    grid = {}
    for w in els:
        if w["type"] != "way":
            continue
        pts = [nodes[n] for n in w["nodes"] if n in nodes]
        for a, b in zip(pts, pts[1:]):
            for ix in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                for iy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                    grid.setdefault((ix, iy), []).append((a, b, speeds[w["id"]], w["id"]))

    # vehicle roads (centre line + width) for the dedicated test
    rgrid = {}
    for r in roads:
        half = r.get("w", 6) / 2
        for a, b in zip(r["p"], r["p"][1:]):
            for ix in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                for iy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                    rgrid.setdefault((ix, iy), []).append((a, b, half))

    acc = [0.0]
    for a, b in zip(path, path[1:]):
        acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    osm, ded, by_way = [], [], {}
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
        best, bd, way = 0, 2.0, None
        for ca, cb, v, wid in grid.get(key, []):
            d, sx, sy = seg_dist(p, ca, cb)
            l = math.hypot(sx, sy) or 1
            if d < bd and abs((sx * hx + sy * hy) / l) > 0.7:
                best, bd, way = v, d, wid
        osm.append(best)
        if way is not None:
            by_way[way] = by_way.get(way, 0) + 1
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
    return osm, ded, by_way


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from geo import Frame
    from atomic import replacing
    import sources
    line_id = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
    dst = os.path.join(ROOT, "data", f"line{line_id}.json")
    line = json.load(open(dst, encoding="utf-8"))
    F = Frame()  # the city frame: the one conversion (tools/geo.py)

    # the Overpass cache of this line's tracks (a run like 9 -> 10 has its own folder, line 22 the raw/ root;
    # another line's answers there are not this line's, #87)
    cands = glob.glob(os.path.join(ROOT, "raw", f"run{line_id}-*", "tracks.json")) + [
        os.path.join(ROOT, "raw", f"line{line_id}", "tracks.json")] + (
        [os.path.join(ROOT, "raw", "tracks.json")] if line_id == "22" else [])
    src = next((p for p in cands if os.path.exists(p)), None) or sys.exit(
        f"no cached tracks for line {line_id}: run build_line.py first")
    els = json.load(open(src, encoding="utf-8"))["elements"]
    nodes = {e["id"]: tuple(float(v) for v in F.xy(e["lat"], e["lon"])) for e in els if e["type"] == "node"}
    fixes = corrections(json.load(open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8")))
    roads = [r for r in line["roads"] if not r.get("f") and r.get("c")]
    osm, ded, by_way = along(line["path"], els, nodes, roads, way_speeds(els, fixes))
    held = sum(by_way.get(w, 0) for w in fixes)
    for w in sorted(w for w in fixes if by_way.get(w)):
        print(f"{fixes[w]['id']}: {by_way[w]} samples at {fixes[w]['maxspeed']} km/h")

    line["speed"] = {"step": STEP, "osm": osm, "dedicated": ded,
                     "source": "OpenStreetMap railway=tram maxspeed (as shown by OpenRailwayMap)"}
    # (a sample without a posted speed is 0: the game's curvature and switch limits hold there)
    tagged = sum(1 for v in osm if v)
    line["provenance"] = sources.stamp("osm_speeds.py", {"speed": sources.entry(
        "speeds", [held, tagged - held, len(osm) - tagged], f"{STEP:g} m samples")}, line.get("provenance"))
    line["attribution"] = sources.attribution(line["provenance"])
    # (written whole and renamed: tools/rebuild.py runs other steps that read this file at the same time)
    with replacing(dst, "w", encoding="utf-8") as fh:
        json.dump(line, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"line {line_id}: {len(osm)} samples, maxspeed on {100 * tagged / len(osm):.0f} % "
          f"({', '.join(f'{v}: {osm.count(v)}' for v in sorted(set(osm)) if v)}), dedicated {100 * sum(ded) / len(ded):.0f} %")


if __name__ == "__main__":
    main()
