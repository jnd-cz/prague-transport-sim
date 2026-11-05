"""Where are the stop signs? OSM's stop positions against the timetable's (GTFS) stop points, for the
review page (#258): python -P -E tools/stop_signs_review.py [--lines 9,17,22,23,37] [--over 5]

For each line's stops (data/lineN.json stops[].s: the GTFS point projected onto the route), the OSM stop
position with the same name on the route's track (within ON_TRACK m) and 100 m along it (public_transport=stop_position +
tram=yes, or railway=tram_stop; the local extract raw/osm/praha.osm.pbf). Stops where the two differ by
more than --over metres along the track are written to reports/review/stop-signs-N.json, a pin at OSM's
point, for the user to say where the sign really stands (?line=N&review=reports/review/stop-signs-N.json).
Prints per line how the two compare, and the platform's front end against OSM's point.

    python -P -E tools/stop_signs_review.py --import [--reviews reports/reviews]

takes the user's answers (fetched with python -I tools/deploy.py --pull-reviews) into data/truth.json
stopSigns: per stop and direction (the stop, the next stop or for a last stop the previous one) the sign's
point, which tools/build_line.py makes the stop's point. The newest answer per card counts; a point placed on
the map wins over the answer's pin. The card's OSM node and timetable point are kept with it, so a later
source that moves away from the fact can be told apart (the user, 2026-11-05: "significant shift away from
open data should trigger review later")."""
import argparse
import csv
import io
import json
import math
import os
import statistics
import sys
import time
import zipfile
from collections import Counter, defaultdict

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


def stop_positions():
    """[(name, lat, lon, node id)] of the extract's tram stop positions"""
    import osmium
    from osm_local import is_stop_position
    out = []
    for n in osmium.FileProcessor(os.path.join(ROOT, "raw", "osm", "praha.osm.pbf"), osmium.osm.NODE):
        if n.tags and is_stop_position(n.tags):
            out.append((n.tags.get("name", ""), n.location.lat, n.location.lon, n.id))
    return out


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


def back_stops(line, path, back):
    """The opposite direction's stops on pathBack: the GTFS pattern of route L<line> (direction 0 or 1,
    whichever lies along pathBack) most trips run, each stop's point projected onto pathBack."""
    z = zipfile.ZipFile(os.path.join(ROOT, "raw", "PID_GTFS.zip"))
    rd = lambda n: csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig"))  # noqa: E731
    trips = {t["trip_id"]: t["direction_id"] for t in rd("trips.txt") if t["route_id"] == f"L{line}"}
    seq = defaultdict(list)
    for r in rd("stop_times.txt"):
        if r["trip_id"] in trips:
            seq[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"]))
    pats = Counter((trips[t], tuple(i for _, i in sorted(v))) for t, v in seq.items())
    ids = {i for (_, p), _ in pats.items() for i in p}
    frame = Frame()
    xy = {r["stop_id"]: (frame.xy(float(r["stop_lat"]), float(r["stop_lon"])), r["stop_name"]) for r in rd("stops.txt") if r["stop_id"] in ids}
    best = None
    for dirn in ("0", "1"):
        top = max(((n, p) for (d, p), n in pats.items() if d == dirn), default=None)
        if not top:
            continue
        pr = [(project(back, *xy[i][0]), xy[i][1]) for i in top[1]]
        fit = statistics.median(d for (d, _), _ in pr)
        if best is None or fit < best[0]:
            best = (fit, [{"name": nm, "s": round(sb, 1)} for (d, sb), nm in pr if d < 25])
    return best[1] if best else []


def review(line, path, stops, nodes, over, back=False):
    """Findings for one direction's stops on its path; (findings, OSM - GTFS diffs, platform end - OSM)"""
    diffs, ends, findings, seen = [], [], [], {}
    tag, dirn = ("back-", " (the other direction)") if back else ("", "")
    for k, st in enumerate(stops):
        cands = []
        for name, x, y, nid in nodes:
            if name != st["name"]:
                continue
            d, s = project(path, x, y)
            if d < ON_TRACK and abs(s - st["s"]) < ALONG:
                cands.append((abs(s - st["s"]), s, x, y, nid))
        nxt = stops[k + 1]["name"] if k + 1 < len(stops) else "end"
        key = {"stop": st["name"], "towards": stops[k + 1]["name"] if k + 1 < len(stops) else None,
               "from": stops[k - 1]["name"] if k else None, "back": back}
        seen[st["name"]] = seen.get(st["name"], 0) + 1
        sid = f"stop-sign-{line}-{tag}{st['name']}-{seen[st['name']]}"
        if not cands:
            gx, gy = at(path, st["s"])
            findings.append({"kind": "stop sign", "id": sid, "line": line, **key, "x": round(gx, 1), "y": round(gy, 1), "s": st["s"],
                             "mag": 10, "status": "review", "pick": True,
                             "marks": [{"x": round(gx, 1), "y": round(gy, 1), "label": "timetable (GTFS) point", "color": GTFS}],
                             "info": f"{st['name']} (towards {nxt}){dirn}: no OSM stop position near the track. The pin is the timetable "
                                     f"(GTFS) point. Where is the stop sign?"})
            continue
        _, s_osm, x, y, nid = min(cands)
        diff = s_osm - st["s"]
        diffs.append(diff)
        end = st["p1"] - s_osm if st.get("p0") is not None and st.get("p1") is not None and st["p1"] - st["p0"] >= 15 else None
        if end is not None:
            ends.append(end)
        if abs(diff) > over:
            where = f"{abs(diff):.0f} m {'before' if diff < 0 else 'after'}"
            plat = f" The platform's front end is {end:.0f} m past the pin." if end is not None else ""
            gx, gy = at(path, st["s"])
            marks = [{"x": round(x, 1), "y": round(y, 1), "label": "OSM stop position (the pin)", "color": OSM},
                     {"x": round(gx, 1), "y": round(gy, 1), "label": "timetable (GTFS) point", "color": GTFS}]
            if end is not None:
                ex, ey = at(path, st["p1"])
                marks.append({"x": round(ex, 1), "y": round(ey, 1), "label": "platform's front end", "color": END})
            findings.append({"kind": "stop sign", "id": sid, "line": line, **key, "x": round(x, 1), "y": round(y, 1), "s": round(s_osm, 1),
                             "mag": round(abs(diff), 1), "status": "review", "osm_node": nid, "gtfs_s": st["s"], "pick": True, "marks": marks,
                             "info": f"{st['name']} (towards {nxt}){dirn}: OSM's stop position (the pin, node {nid}) is {where} "
                                     f"the timetable (GTFS) point.{plat} Where is the stop sign? (Not at either: place it on the map.)"})
    return findings, diffs, ends


def sign_facts(cards, answers):
    """truth.json stopSigns from the review cards and the user's answers (per line: {card id: record});
    the newest answer per stop and direction"""
    by_id = {c["id"]: c for c in cards}
    best = {}
    for line, recs in answers.items():
        newest = {}
        for r in recs:
            if r.get("kind") == "stop sign" and r.get("id") in by_id and r.get("v"):
                if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                    newest[r["id"]] = r
        for i, r in newest.items():
            c = by_id[i]
            gtfs = next((m for m in c["marks"] if m["label"].startswith("timetable")), None)
            if "px" in r:
                x, y, how = r["px"], r["py"], "placed on the map"
            elif r["v"] == OPTIONS[0] and "osm_node" in c:
                x, y, how = c["x"], c["y"], r["v"]
            elif r["v"] == OPTIONS[1] and gtfs:
                x, y, how = gtfs["x"], gtfs["y"], r["v"]
            else:
                continue  # (unsure, or a placed answer whose point was lost: held)
            k = (c["stop"], c["towards"] or "", c["from"] if not c["towards"] else "")
            f = {"stop": c["stop"], **({"towards": c["towards"]} if c["towards"] else {"from": c["from"]}),
                 "x": round(x, 2), "y": round(y, 2), "how": how,
                 **({"note": r["note"]} if r.get("note") else {}),
                 "osm_node": c.get("osm_node"), "gtfs": [gtfs["x"], gtfs["y"]] if gtfs else None,
                 "line": c["line"], "t": r.get("t", 0)}
            if k not in best or f["t"] > best[k]["t"]:
                best[k] = f
    out = []
    for f in sorted(best.values(), key=lambda f: (f["stop"], f.get("towards", ""), f.get("from", ""))):
        day = time.strftime("%Y-%m-%d", time.gmtime(f.pop("t") / 1000)) if f.get("t") else "?"
        f["source"] = f"user, stop-sign review (reports/review/stop-signs-{f.pop('line')}.json) on the test host, {day} (#258)"
        out.append(f)
    return out


TRUTH_NOTE = ("Where the stop signs (označníky) stand: the point the tram front stops at (D 1/2 § 27.6), from the "
              "user's stop-sign review (#258), imported by tools/stop_signs_review.py --import; the build makes it the "
              "stop's point (tools/build_line.py). x, y in the city frame (tools/geo.py). osm_node and gtfs: the open "
              "data at the time of the answer. The user, 2026-11-05: \"Hercovka on gtfs mapy pid looks indeed wrong, "
              "malostranské náměstí on osm maps is too short\"; the sign usually stands \"slightly before platform's "
              "front end\" (2026-11-04).")


TRUTH = os.path.join(ROOT, "data", "truth.json")


def write_truth(facts, p=TRUTH):
    """data/truth.json stopSigns (its last section), the rest of the file as it is"""
    text = open(p, encoding="utf-8").read()
    json.loads(text)
    tail = '\n "stopSigns": '
    if tail in text:
        text = text[:text.index(tail)].rstrip().rstrip(",") + "\n}\n"
    body = json.dumps({"note": TRUTH_NOTE, "signs": facts}, ensure_ascii=False, indent=1).replace("\n", "\n ")
    text = text.rstrip()[:-1].rstrip() + "," + tail + body + "\n}\n"
    assert json.loads(text)["stopSigns"]["signs"] == facts
    with replacing(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def do_import(lines, reviews):
    cards, answers = [], {}
    for line in lines:
        cp = os.path.join(ROOT, "reports", "review", f"stop-signs-{line}.json")
        if os.path.exists(cp):
            cards += json.load(open(cp, encoding="utf-8"))["findings"]
        ap_ = os.path.join(ROOT, reviews, f"line{line}.json")
        if os.path.exists(ap_):
            a = json.load(open(ap_, encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            answers[line] = list(items.values()) if isinstance(items, dict) else items
    facts = sign_facts(cards, answers)
    write_truth(facts)
    print(f"data/truth.json stopSigns: {len(facts)} signs ({Counter(f['how'] for f in facts)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--over", type=float, default=5.0, help="m along the track: list stops differing by more")
    ap.add_argument("--import", dest="imp", action="store_true", help="the user's answers into data/truth.json")
    ap.add_argument("--reviews", default=os.path.join("reports", "reviews"))
    args = ap.parse_args()
    if args.imp:
        return do_import(args.lines.split(","), args.reviews)
    frame = Frame()
    nodes = [(name, *frame.xy(lat, lon), nid) for name, lat, lon, nid in stop_positions()]
    q = lambda a, f: sorted(a)[int(f * (len(a) - 1))] if a else float("nan")  # noqa: E731
    med = lambda a: statistics.median(a) if a else float("nan")  # noqa: E731
    for line in args.lines.split(","):
        data = json.load(open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8"))
        path, stops, back = data["path"], data["stops"], data.get("pathBack") or []
        findings, diffs, ends = review(line, path, stops, nodes, args.over)
        print(f"line {line}: {len(diffs)}/{len(stops)} matched; OSM - GTFS median {med(diffs):+.1f} m "
              f"[10 % {q(diffs, .1):+.1f}, 90 % {q(diffs, .9):+.1f}]; platform end - OSM median {med(ends):+.1f} m; "
              f"{len(findings)} to review")
        # a run that returns to its start (line 9's) drives both directions on its own path
        if back and math.dist(back[0][:2], path[-1][:2]) < math.dist(back[0][:2], path[0][:2]):
            bst = back_stops(line, path, back)
            bf, bd, _ = review(line, back, bst, nodes, args.over, back=True)
            findings += bf
            print(f"  other direction: {len(bd)}/{len(bst)} matched; OSM - GTFS median {med(bd):+.1f} m "
                  f"[10 % {q(bd, .1):+.1f}, 90 % {q(bd, .9):+.1f}]; {len(bf)} to review")
        out = {"schema": 1, "issue": 258, "options": OPTIONS, "over_m": args.over, "findings": findings}
        with replacing(os.path.join(ROOT, "reports", "review", f"stop-signs-{line}.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
