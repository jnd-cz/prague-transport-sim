# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the OSM tram ways say about speed along each built line, for the speed limits and signs (#211).

    python -P -E tools/speed_survey.py [--lines 9,17,22,23,37] [--json reports/speed_survey.json]

Every 5 m of a line's `path`: the tram way under the track (the same match as tools/osm_speeds.py: within 2 m and
in line with it) and its `maxspeed`, `maxspeed:conditional` and `note`. Prints per line the track-km by posted speed,
what the game's data holds for the same samples, the stretches over 50 km/h and the night zones, each between its
stops. Also the tagged speed switches (`ref` R01, ...) against the line's facing switches and the list in
data/truth.json `operation` `speed-switches`. Reads the local extract only and writes nothing but --json.
"""
import argparse
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from geo import Frame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = (9, 17, 22, 23, 37)
STEP = 5.0
CELL = 20.0
REACH = 2.0      # m: the way under the track (tools/osm_speeds.py)
IN_LINE = 0.7    # |cos| of the angle between the way and the track
SWITCH_NEAR = 8.0  # m: a tagged switch is on the route, and is one of its facing switches, this near

CONDITIONAL = re.compile(r"(\d+)\s*@\s*\((\d\d):(\d\d)-(\d\d):(\d\d)\)")
TYPED_NOTE = re.compile(r"max\.?\s*(\d+)\s*km/h\s+pouze\s+vozy\s+([\w.]+)\s*,\s*ostatn\S*\s+max\.?\s*(\d+)", re.I)


def posted(v):
    """The speed in a `maxspeed` value: km/h, or 0 where there is no number (untagged, CZ:pedestrian_zone)."""
    try:
        return int(str(v or "").split(";")[0].split()[0])
    except (ValueError, IndexError):
        return 0


def conditional(v):
    """`maxspeed:conditional` as [(km/h, 'HH:MM-HH:MM')]: '40 @ (22:00-06:00)' -> [(40, '22:00-06:00')]."""
    return [(int(m[1]), f"{m[2]}:{m[3]}-{m[4]}:{m[5]}") for m in CONDITIONAL.finditer(v or "")]


def night(v):
    """The speed of a conditional that holds at night (it covers 22:00-06:00), or 0: the ones during the day (Zlíchov,
    06:30-17:30, a school) are not the night zones of D 1/2 § 49.21."""
    return next((km for km, hours in conditional(v) if hours == "22:00-06:00"), 0)


def typed(note):
    """The note on a way whose speed holds for one car type: (speed, car type, speed for the others), or None."""
    m = TYPED_NOTE.search(note or "")
    return (int(m[1]), m[2], int(m[3])) if m else None


def stretches(values, step=STEP, min_len=0.0):
    """Runs of equal values along the samples, zeros left out: [(from s, to s, value)], shorter than min_len dropped."""
    out, i, n = [], 0, len(values)
    while i < n:
        j = i
        while j < n and values[j] == values[i]:
            j += 1
        if values[i] and (j - i) * step >= min_len:
            out.append((i * step, j * step, values[i]))
        i = j
    return out


def km_by_value(values, step=STEP):
    """{value: km}, in value order."""
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + step
    return {k: round(out[k] / 1000, 2) for k in sorted(out, key=str)}


def stop_between(stops, s):
    """'A .. B', the stops around route position s."""
    names = [st["name"] for st in stops]
    at = [st.get("s", 0) for st in stops]
    k = sum(1 for a in at if a <= s)
    return f"{names[max(0, k - 1)]} .. {names[min(len(names) - 1, k)]}"


def seg_dist(p, a, b):
    sx, sy = b[0] - a[0], b[1] - a[1]
    l2 = sx * sx + sy * sy or 1e-9
    u = max(0.0, min(1.0, ((p[0] - a[0]) * sx + (p[1] - a[1]) * sy) / l2))
    return math.hypot(a[0] + sx * u - p[0], a[1] + sy * u - p[1]), sx, sy


class Ways:
    """The tram ways in a 20 m grid, to find the way under a track."""

    def __init__(self, ways):
        self.grid = {}
        for w in ways:
            for a, b in zip(w["pts"], w["pts"][1:]):
                for ix in range(int(min(a[0], b[0]) // CELL), int(max(a[0], b[0]) // CELL) + 1):
                    for iy in range(int(min(a[1], b[1]) // CELL), int(max(a[1], b[1]) // CELL) + 1):
                        self.grid.setdefault((ix, iy), []).append((a, b, w))

    def under(self, p, heading):
        best, bd = None, REACH
        for a, b, w in self.grid.get((int(p[0] // CELL), int(p[1] // CELL)), ()):
            d, sx, sy = seg_dist(p, a, b)
            if d < bd and abs((sx * heading[0] + sy * heading[1]) / (math.hypot(sx, sy) or 1)) > IN_LINE:
                best, bd = w, d
        return best


def samples(path, step=STEP):
    """(point, heading) every `step` m along a polyline."""
    out, i, s = [], 0, 0.0
    acc = [0.0]
    for a, b in zip(path, path[1:]):
        acc.append(acc[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    while s <= acc[-1]:
        while i < len(path) - 2 and acc[i + 1] < s:
            i += 1
        a, b = path[i], path[i + 1]
        seg = acc[i + 1] - acc[i] or 1e-9
        u = (s - acc[i]) / seg
        out.append(((a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u), ((b[0] - a[0]) / seg, (b[1] - a[1]) / seg)))
        s += step
    return out


def along(path, ways):
    """Per sample: the way under the track, or None."""
    return [ways.under(p, h) for p, h in samples(path)]


def nearest_on(path, p):
    """(distance, route s) of point p to a polyline."""
    best, at, acc = 1e18, 0.0, 0.0
    for a, b in zip(path, path[1:]):
        d, sx, sy = seg_dist(p, a, b)
        seg = math.hypot(sx, sy)
        if d < best:
            u = max(0.0, min(1.0, ((p[0] - a[0]) * sx + (p[1] - a[1]) * sy) / (seg * seg or 1e-9)))
            best, at = d, acc + u * seg
        acc += seg
    return best, at


def survey_line(line, data, ways):
    under = along(data["path"], ways)
    tags = [w["tags"] if w else {} for w in under]
    osm = [posted(t.get("maxspeed")) for t in tags]
    zones = [night(t.get("maxspeed:conditional")) for t in tags]
    held = (data.get("speed") or {}).get("osm") or []
    n = min(len(osm), len(held))
    fast = [v if v > 50 else 0 for v in osm]
    notes = {}
    for t in tags:
        tn = typed(t.get("note"))
        if tn:
            notes[tn] = notes.get(tn, 0) + STEP
    stops = data["stops"]
    return {
        "line": line,
        "km": round(len(osm) * STEP / 1000, 2),
        "tagged": km_by_value(osm),
        "differsFromData": sum(1 for a, b in zip(osm[:n], held[:n]) if a != b),
        "fast": [{"from": a, "to": b, "v": v, "between": stop_between(stops, (a + b) / 2)}
                 for a, b, v in stretches(fast, min_len=25)],
        "nightKm": km_by_value([v for v in zones if v]),
        "night": [{"from": a, "to": b, "v": v, "between": stop_between(stops, (a + b) / 2)}
                  for a, b, v in stretches(zones, min_len=25)],
        "typedNotes": [{"v": k[0], "for": k[1], "others": k[2], "km": round(m / 1000, 2)} for k, m in notes.items()],
    }


def speed_switches(lines, nodes, listed):
    """Each tagged speed switch: where it lies, the list's speeds, the built lines it is on, and facing there or not."""
    out = []
    for n in nodes:
        rows = []
        for line, data in lines.items():
            for key, back in (("path", False), ("pathBack", True)):
                if not data.get(key):
                    continue
                d, s = nearest_on(data[key], n["xy"])
                if d > SWITCH_NEAR:
                    continue
                facing = None if back else any(abs(w["s"] - s) < SWITCH_NEAR for w in data.get("switches", []))
                rows.append({"line": line, "dir": "back" if back else "out", "s": round(s), "off": round(d, 1), "facing": facing})
        fact = listed.get(n["ref"]) or {}
        out.append({"ref": n["ref"], "lat": n["lat"], "lon": n["lon"], "electric": n.get("electric"),
                    "place": fact.get("place"), "straight": fact.get("straight"), "diverging": fact.get("diverging"), "on": rows})
    return sorted(out, key=lambda r: r["ref"])


def load_ways():
    from osm_local import ways as osm_ways
    F = Frame()
    out = []
    for e in osm_ways(lambda t: t.get("railway") == "tram"):
        pts = [tuple(float(v) for v in F.xy(g["lat"], g["lon"])) for g in e["geometry"]]
        out.append({"id": e["id"], "tags": e.get("tags", {}), "pts": pts})
    return out


def load_switches():
    from osm_local import nodes as osm_nodes
    F = Frame()
    out = []
    for e in osm_nodes(lambda t: t.get("railway") == "switch" and re.fullmatch(r"R\d\d", t.get("ref", ""))):
        out.append({"ref": e["tags"]["ref"], "lat": e["lat"], "lon": e["lon"], "electric": e["tags"].get("railway:switch:electric"),
                    "xy": tuple(float(v) for v in F.xy(e["lat"], e["lon"]))})
    return out


def table(rows):
    print("| line | km | posted km/h: km | samples unlike the data | night zones km |")
    print("|---|---:|---|---:|---|")
    for r in rows:
        tagged = ", ".join(f"{'untagged' if k == 0 else k}: {v}" for k, v in r["tagged"].items())
        print(f"| {r['line']} | {r['km']} | {tagged} | {r['differsFromData']} | {r['nightKm'] or '-'} |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", default=",".join(str(n) for n in LINES))
    ap.add_argument("--json")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    numbers = [int(n) for n in a.lines.split(",")]
    lines = {}
    for n in numbers:
        with open(os.path.join(ROOT, "data", f"line{n}.json"), encoding="utf-8") as f:
            lines[n] = json.load(f)
    ways = Ways(load_ways())
    rows = [survey_line(n, d, ways) for n, d in lines.items()]
    table(rows)
    for r in rows:
        print(f"\nline {r['line']}: over 50 km/h")
        for f in r["fast"]:
            print(f"  {f['v']} km/h  s {f['from']:.0f}-{f['to']:.0f} ({f['to'] - f['from']:.0f} m)  {f['between']}")
        for t in r["typedNotes"]:
            print(f"  note on {t['km']} km: {t['v']} km/h for {t['for']} only, the others {t['others']}")
        print(f"line {r['line']}: night zones")
        for f in r["night"]:
            print(f"  {f['v']} km/h  s {f['from']:.0f}-{f['to']:.0f} ({f['to'] - f['from']:.0f} m)  {f['between']}")
    with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    listed = next(x for x in truth["operation"]["lists"] if x["id"] == "speed-switches")["entries"]
    sw = speed_switches(lines, load_switches(), {e["number"]: e for e in listed})
    print("\ntagged speed switches")
    for r in sw:
        print(f"  {r['ref']} {r['lat']:.5f},{r['lon']:.5f} electric={r['electric']} list: {r['place']} {r['straight']}/{r['diverging']}  on: {r['on']}")
    print("  on the list, not tagged:", sorted(set(e["number"] for e in listed) - {r["ref"] for r in sw}) or "none")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"lines": rows, "speedSwitches": sw}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
