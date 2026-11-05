"""Where are the stop signs? OSM's stop positions against the timetable's (GTFS) stop points, for the
review page (#258): python -P -E tools/stop_signs_review.py [--lines 9,17,22,23,37] [--over 5]

For each line's stops (data/lineN.json stops[].s: the GTFS point projected onto the route), the OSM stop
position with the same name on the route's track (within ON_TRACK m) and 100 m along it (public_transport=stop_position +
tram=yes, or railway=tram_stop; the local extract raw/osm/praha.osm.pbf). Stops where the two differ by
more than --over metres along the track are written to reports/review/stop-signs-N.json, a pin at OSM's
point, for the user to say where the sign really stands (?line=N&review=reports/review/stop-signs-N.json).
Prints per line how the two compare, and the platform's front end against OSM's point."""
import argparse
import json
import math
import os
import statistics
import sys

import osmium

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402

# (elsewhere: "Place it on the map", the point saved with the answer as px, py)
OPTIONS = ["sign at the pin (OSM)", "sign at the timetable point (GTFS)", "unsure"]
OSM, GTFS, END = "#3e9dff", "#ff9e31", "#ffffff"
# The other direction's stop position lies on the parallel track, 3.1-5.9 m off ours: within 6 m it was taken
# at 5 stops (Hercovka on 17, Vršovické náměstí on 22: the user, review 2026-11-05), while our direction's
# node lies on our track (under 1.5 m) at all 174 stops of the 5 lines. Hercovka's own is 86 m past the GTFS point.
ON_TRACK, ALONG = 1.5, 100


class StopPositions(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.nodes = []

    def node(self, n):
        t = n.tags
        if t.get("railway") == "tram_stop" or (t.get("public_transport") == "stop_position" and t.get("tram") == "yes"):
            self.nodes.append((t.get("name", ""), n.location.lat, n.location.lon, n.id))


def project(path, x, y):
    """(distance from the path, route s) of the nearest point"""
    best, s0 = (1e9, None), 0.0
    for i in range(1, len(path)):
        (ax, ay), (bx, by) = path[i - 1][:2], path[i][:2]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (l2 or 1e-9)))
        d = math.hypot(ax + u * dx - x, ay + u * dy - y)
        if d < best[0]:
            best = (d, s0 + u * math.sqrt(l2))
        s0 += math.sqrt(l2)
    return best


def at(path, s):
    s0 = 0.0
    for i in range(1, len(path)):
        (ax, ay), (bx, by) = path[i - 1][:2], path[i][:2]
        seg = math.hypot(bx - ax, by - ay)
        if s0 + seg >= s:
            u = (s - s0) / (seg or 1e-9)
            return ax + u * (bx - ax), ay + u * (by - ay)
        s0 += seg
    return path[-1][0], path[-1][1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--over", type=float, default=5.0, help="m along the track: list stops differing by more")
    args = ap.parse_args()
    h = StopPositions()
    h.apply_file(os.path.join(ROOT, "raw", "osm", "praha.osm.pbf"))
    frame = Frame()
    nodes = [(name, *frame.xy(lat, lon), nid) for name, lat, lon, nid in h.nodes]
    for line in args.lines.split(","):
        data = json.load(open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8"))
        path, stops = data["path"], data["stops"]
        diffs, ends, findings, seen = [], [], [], {}
        for k, st in enumerate(stops):
            cands = []
            for name, x, y, nid in nodes:
                if name != st["name"]:
                    continue
                d, s = project(path, x, y)
                if d < ON_TRACK and abs(s - st["s"]) < ALONG:
                    cands.append((abs(s - st["s"]), s, x, y, nid))
            nxt = stops[k + 1]["name"] if k + 1 < len(stops) else "end"
            seen[st["name"]] = seen.get(st["name"], 0) + 1
            sid = f"stop-sign-{line}-{st['name']}-{seen[st['name']]}"
            if not cands:
                gx, gy = at(path, st["s"])
                findings.append({"kind": "stop sign", "id": sid, "line": line, "x": round(gx, 1), "y": round(gy, 1), "s": st["s"],
                                 "mag": 10, "status": "review", "pick": True,
                                 "marks": [{"x": round(gx, 1), "y": round(gy, 1), "label": "timetable (GTFS) point", "color": GTFS}],
                                 "info": f"{st['name']} (towards {nxt}): no OSM stop position near the track. The pin is the timetable "
                                         f"(GTFS) point. Where is the stop sign?"})
                continue
            _, s_osm, x, y, nid = min(cands)
            diff = s_osm - st["s"]
            diffs.append(diff)
            end = st["p1"] - s_osm if st.get("p0") is not None and st.get("p1") is not None and st["p1"] - st["p0"] >= 15 else None
            if end is not None:
                ends.append(end)
            if abs(diff) > args.over:
                where = f"{abs(diff):.0f} m {'before' if diff < 0 else 'after'}"
                plat = f" The platform's front end is {end:.0f} m past the pin." if end is not None else ""
                gx, gy = at(path, st["s"])
                marks = [{"x": round(x, 1), "y": round(y, 1), "label": "OSM stop position (the pin)", "color": OSM},
                         {"x": round(gx, 1), "y": round(gy, 1), "label": "timetable (GTFS) point", "color": GTFS}]
                if end is not None:
                    ex, ey = at(path, st["p1"])
                    marks.append({"x": round(ex, 1), "y": round(ey, 1), "label": "platform's front end", "color": END})
                findings.append({"kind": "stop sign", "id": sid, "line": line, "x": round(x, 1), "y": round(y, 1), "s": round(s_osm, 1),
                                 "mag": round(abs(diff), 1), "status": "review", "osm_node": nid, "gtfs_s": st["s"], "pick": True, "marks": marks,
                                 "info": f"{st['name']} (towards {nxt}): OSM's stop position (the pin, node {nid}) is {where} "
                                         f"the timetable (GTFS) point.{plat} Where is the stop sign? (Not at either: place it on the map.)"})
        out = {"schema": 1, "issue": 258, "options": OPTIONS, "over_m": args.over, "findings": findings}
        with replacing(os.path.join(ROOT, "reports", "review", f"stop-signs-{line}.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        q = lambda a, f: sorted(a)[int(f * (len(a) - 1))]  # noqa: E731
        print(f"line {line}: {len(diffs)}/{len(stops)} matched; OSM - GTFS median {statistics.median(diffs):+.1f} m "
              f"[10 % {q(diffs, .1):+.1f}, 90 % {q(diffs, .9):+.1f}]; platform end - OSM median {statistics.median(ends):+.1f} m; "
              f"{len(findings)} to review")


if __name__ == "__main__":
    main()
