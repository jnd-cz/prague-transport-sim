"""Where are the stop signs? The archive DTM's signs against OSM's stop positions and the timetable's (GTFS)
stop points, both directions, for the review page (#258):
    python -P -E tools/stop_signs_review.py [--lines 9,17,22,23,37] [--over 5]

For each line's stops (data/lineN.json stops[].s: the GTFS point projected onto the route; the other direction's
from GTFS onto pathBack): the DTM sign as tools/build_line.py takes it (raw/dtmpoints/lineN.signs.json, right of
travel, within 6 m of the track and 40 m of OSM's point), and the OSM stop position with the same name on the
route's track (within ON_TRACK m) and 100 m along it (public_transport=stop_position + tram=yes, or
railway=tram_stop; the local extract raw/osm/praha.osm.pbf). A stop without the user's sign (data/truth.json
stopSigns) gets a card in reports/review/stop-signs-N.json when it has no DTM sign, or when the DTM sign lies
more than --over metres along the track from OSM's point (else the GTFS point): the DTM's 2024 state misses
rebuilt streets (Výstaviště, 15 m). The pin is the DTM sign, else OSM's point, else the GTFS point
(?line=N&review=reports/review/stop-signs-N.json). Prints per line and direction how the sources compare.

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
OPTIONS = ["sign at the pin", "sign at the timetable point (GTFS)", "unsure"]
OSM, GTFS, END, DTM = "#3e9dff", "#ff9e31", "#ffffff", "#ff3b30"
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


def side(path, s, x, y):
    """>0: left of the direction of travel"""
    ax, ay = at(path, s - 1)
    bx, by = at(path, s + 1)
    return (bx - ax) * (y - ay) - (by - ay) * (x - ax)


def review(line, path, stops, nodes, dtm, facts, over, back=False):
    """Cards for one direction's stops on its path; and per stop what each source says (for the summary)"""
    rows, findings, seen = [], [], {}
    tag, dirn = ("back-", " (the other direction)") if back else ("", "")
    for k, st in enumerate(stops):
        osm = []
        for name, x, y, nid in nodes:
            if name == st["name"]:
                d, s = project(path, x, y)
                if d < ON_TRACK and abs(s - st["s"]) < ALONG:
                    osm.append((abs(s - st["s"]), s, x, y, nid))
        o = min(osm) if osm else None
        ref = o[1] if o else st["s"]
        near = []
        for x, y in dtm:
            d, s = project(path, x, y)
            if d < 6 and abs(s - ref) < 40 and side(path, s, x, y) < 0:
                near.append((abs(s - ref), s, x, y))
        m = min(near) if near else None
        nxt = stops[k + 1]["name"] if k + 1 < len(stops) else None
        prv = stops[k - 1]["name"] if k else None
        key = {"stop": st["name"], "towards": nxt, "from": prv, "back": back}
        seen[st["name"]] = seen.get(st["name"], 0) + 1
        sid = f"stop-sign-{line}-{tag}{st['name']}-{seen[st['name']]}"
        fact = next((f for f in facts if f["stop"] == st["name"] and (f.get("towards") == nxt if nxt else f.get("from") == prv)), None)
        rows.append({"gtfs": st["s"], "osm": o[1] if o else None, "dtm": m[1] if m else None, "fact": bool(fact)})
        if fact or (m and abs(m[1] - ref) <= over):
            continue
        gx, gy = at(path, st["s"])
        marks = []
        if m:
            marks.append({"x": round(m[2], 1), "y": round(m[3], 1), "label": "DTM stop sign, state 2024", "color": DTM})
        if o:
            marks.append({"x": round(o[2], 1), "y": round(o[3], 1), "label": "OSM stop position", "color": OSM})
        marks.append({"x": round(gx, 1), "y": round(gy, 1), "label": "timetable (GTFS) point", "color": GTFS})
        if st.get("p1") is not None:
            ex, ey = at(path, st["p1"])
            marks.append({"x": round(ex, 1), "y": round(ey, 1), "label": "platform's front end (OSM)", "color": END})
        px, py, ps, what = (m[2], m[3], m[1], "the DTM stop sign") if m else (o[2], o[3], o[1], "OSM's stop position") if o \
            else (gx, gy, st["s"], "the timetable (GTFS) point")
        if m:
            d = m[1] - ref
            why = (f"the DTM's sign (2024) lies {abs(d):.0f} m {'before' if d < 0 else 'after'} "
                   f"{'OSM' if o else 'the timetable'}'s point: rebuilt since?")
        else:
            why = "no DTM sign beside the track"
        towards = nxt or "end"
        findings.append({"kind": "stop sign", "id": sid, "line": line, **key, "x": round(px, 1), "y": round(py, 1), "s": round(ps, 1),
                         "mag": round(abs(m[1] - ref), 1) if m else 10, "status": "review", "pick": True, "marks": marks,
                         **({"osm_node": o[4]} if o else {}), "gtfs_s": st["s"],
                         "info": f"{st['name']} (towards {towards}){dirn}: {why} The pin is {what}. Where is the stop sign? "
                                 f"(Not at the pin: place it on the map.)"})
    return findings, rows


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
            elif r["v"].startswith("sign at the pin"):
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
    # (answers whose cards are gone: a stop answered drops out of the queue, its fact stays)
    key = lambda f: (f["stop"], f.get("towards", ""), f.get("from", ""))  # noqa: E731
    new = {key(f) for f in facts}
    old = json.load(open(TRUTH, encoding="utf-8")).get("stopSigns", {}).get("signs", [])
    facts = sorted(facts + [f for f in old if key(f) not in new], key=key)
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
    facts = json.load(open(TRUTH, encoding="utf-8")).get("stopSigns", {}).get("signs", [])
    for line in args.lines.split(","):
        data = json.load(open(os.path.join(ROOT, "data", f"line{line}.json"), encoding="utf-8"))
        path, stops, back = data["path"], data["stops"], data.get("pathBack") or []
        sp = os.path.join(ROOT, "raw", "dtmpoints", f"line{line}.signs.json")
        dtm = [tuple(float(v) for v in frame.xy(g["lat"], g["lon"])) for g in json.load(open(sp, encoding="utf-8"))["signs"]] \
            if os.path.exists(sp) else []
        dirs = [("", path, stops, False)]
        # (a run that returns to its start, line 9's, drives both directions on its own path)
        if back and math.dist(back[0][:2], path[-1][:2]) < math.dist(back[0][:2], path[0][:2]):
            dirs.append(("other direction", back, back_stops(line, path, back), True))
        findings = []
        for name, p_, st_, b in dirs:
            f, rows = review(line, p_, st_, nodes, dtm, facts, args.over, back=b)
            findings += f
            dd = [r["dtm"] - (r["osm"] if r["osm"] is not None else r["gtfs"]) for r in rows if r["dtm"] is not None]
            print(f"line {line}{' ' + name if name else ''}: {len(rows)} stops; the user's sign {sum(r['fact'] for r in rows)}, "
                  f"DTM sign {len(dd)} (DTM - OSM/GTFS median {statistics.median(dd) if dd else float('nan'):+.1f} m, "
                  f"over {args.over:.0f} m {sum(abs(x) > args.over for x in dd)}), OSM {sum(r['osm'] is not None for r in rows)}; "
                  f"{len(f)} to review")
        out = {"schema": 1, "issue": 258, "options": OPTIONS, "over_m": args.over, "findings": findings}
        with replacing(os.path.join(ROOT, "reports", "review", f"stop-signs-{line}.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
