# SPDX-License-Identifier: AGPL-3.0-or-later
"""OSM's grass over our track: candidates for the user's review, and how well the built styles' holes match OSM (#503).

    python -P -E tools/grass_review.py [--lines 9,17,22,23,37]
    python -P -E tools/grass_review.py --import [--reviews reports/reviews]

OSM has no tag for grassed track on the tram ways; mappers draw the grass as areas (landuse=grass, meadow,
village_green, flowerbed; natural=grassland; leisure=park) over it. Read from the local extract
(raw/osm/praha.osm.pbf, closed ways; multipolygon relations are not read) and laid under each line's route every
metre, on the ground only: not on our bridges or in our tunnels (line 22 at Újezd crosses Střelecký ostrov's park on
the bridge, the user 2026-11-12: "the only green area over track I see is střelecký ostrov which lies on lower level
under the bridge").

- **The calibration** (printed per line): inside the facts' grass spans (the user's marks, the grassed-track list,
  answered cards), where OSM's grass ends and the built grass (tools/track_styles.py, with its holes) ends. OSM
  lacks much of the known grass (Sídliště Řepy - Slánská has none), so only its edges are compared.
- **The cards** (reports/review/grass-track-N.json): OSM grass outside the facts, runs less than JOIN m apart one
  place, MIN_GRASS m and more. A place on several lines is one card (one id) in each line's set. OSM has false hits
  (a park drawn over the street), so a card changes nothing until answered.
- **--import** takes the answers (fetched with python -I tools/deploy.py --pull-reviews) into data/truth.json
  `grassReview`: grass between the card's pins on its lines (tools/track_styles.py lays it, holes cut), or not
  grass, or another level; unsure is held. An answered place gets no card again.
"""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import time

import shapely
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
from route import Route  # noqa: E402
import track_styles as T  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINES = "9,17,22,23,37"
GRASS, NOT, OTHER, UNSURE = ("grass track between the two pins", "not grass: another surface on the track",
                             "not our track: another level (a bridge, an underpass)", "unsure")
ANSWER = {GRASS: "grass", NOT: "not grass", OTHER: "other level"}
SAME = 20   # m: candidate places of two lines whose middles lie this close are one card
START, END = "#3e9dff", "#ffffff"


def is_grass(t):
    return (t.get("landuse") in ("grass", "meadow", "village_green", "flowerbed") or t.get("natural") == "grassland"
            or t.get("leisure") == "park")


def osm_grass():
    """OSM's grass areas in the city frame, with an STRtree."""
    import osm_local
    F, polys = Frame(), []
    for e in osm_local.ways(is_grass):
        g = e.get("geometry") or []
        if len(g) < 4 or (g[0]["lat"], g[0]["lon"]) != (g[-1]["lat"], g[-1]["lon"]):
            continue
        x, y = F.xy([q["lat"] for q in g], [q["lon"] for q in g])
        p = Polygon(list(zip(map(float, x), map(float, y))))
        p = p if p.is_valid else p.buffer(0)
        if not p.is_empty:
            polys.append(p)
    return polys, shapely.STRtree(polys)


def runs_of(flags, gap=1):
    """[(s0, s1)] of the metres flagged, gaps under `gap` m joined."""
    out = []
    for s, f in enumerate(flags):
        if not f:
            continue
        if out and s - out[-1][1] <= gap:
            out[-1][1] = s
        else:
            out.append([s, s])
    return [tuple(r) for r in out]


def under_route(data, polys, tree):
    """Per metre of the route: OSM grass under the axis, on the ground."""
    rt = Route(data["path"], data.get("pathExt"))
    off = [tuple(x) for x in data.get("bridges", []) + data.get("tunnels", [])]
    flags = []
    for s in range(int(rt.length) + 1):
        if any(a <= s <= b for a, b in off):
            flags.append(False)
            continue
        pt = Point(*rt.at(s)[:2])
        flags.append(any(polys[int(k)].covers(pt) for k in tree.query(pt)))
    return rt, flags


def calibrate(data, truth, flags):
    """OSM's grass edges inside the facts' grass spans against the built grass's: [distance m]."""
    facts = [x for x in T.spans(data, truth, None) if x["style"] == "grass" and x["source"] in ("user", "list", "review")]
    built = [x for x in T.sections(data, truth, None) if x["style"] == "grass"]
    ends = [e for x in built for e in (x["s0"], x["s1"])]
    out = []
    for sp in facts:
        a, b = int(sp["s0"]), int(sp["s1"])
        for r0, r1 in runs_of([f if a <= s <= b else False for s, f in enumerate(flags)]):
            for e in (r0, r1):
                if min(abs(e - sp["s0"]), abs(e - sp["s1"])) > 2 and ends:
                    out.append(min(abs(e - x) for x in ends))
    return out


def candidates(data, truth, rt, flags):
    """OSM grass places outside the facts: [(s0, s1)]."""
    facts = [x for x in T.spans(data, truth, None) if x["source"] in ("user", "list", "review")]
    answered = [a for a in truth.get("grassReview", {}).get("answers", [])
                if str(data["line"]) in [str(v) for v in a.get("lines", [])]]
    path = shapely.LineString([p[:2] for p in data["path"]])
    done = []
    for a in answered:
        ss = sorted(path.project(Point(*map(float, Frame().xy(*e)))) for e in a["between"])
        done.append({"s0": ss[0], "s1": ss[1]})
    out = []
    for s0, s1 in runs_of(flags, T.JOIN):
        if s1 - s0 < T.MIN_GRASS:
            continue
        cover = sum(max(0, min(s1, x["s1"]) - max(s0, x["s0"])) for x in facts + done)
        if cover < (s1 - s0) / 2:
            out.append((s0, s1))
    return out


def card(line, data, rt, s0, s1):
    F = Frame()
    (ax, ay), (bx, by), (mx, my) = rt.at(s0)[:2], rt.at(s1)[:2], rt.at((s0 + s1) / 2)[:2]
    lat, lon = (float(v) for v in F.ll(mx, my))
    stops = data["stops"]
    prev = max((st for st in stops if st["s"] <= s0), key=lambda st: st["s"], default=None)
    nxt = min((st for st in stops if st["s"] >= s1), key=lambda st: st["s"], default=None)
    where = f"{prev['name'] if prev else 'the start'} - {nxt['name'] if nxt else 'the end'}"
    return {"kind": "grass track", "id": f"grass-{lat:.4f}-{lon:.4f}", "line": line, "x": round(mx, 1), "y": round(my, 1),
            "s0": s0, "s1": s1, "mag": s1 - s0, "status": "review", "place": [round(lat, 6), round(lon, 6)],
            "between": [[round(float(v), 7) for v in F.ll(ax, ay)], [round(float(v), 7) for v in F.ll(bx, by)]],
            "marks": [{"x": round(ax, 1), "y": round(ay, 1), "label": "start of OSM's grass", "color": START},
                      {"x": round(bx, 1), "y": round(by, 1), "label": "end of OSM's grass", "color": END}],
            "options": [GRASS, NOT, OTHER, UNSURE],
            "info": f"{where}: OSM maps grass over the track for {s1 - s0} m (s {s0}-{s1}), and nothing we know says "
                    f"so. Is the track grassed here? The pins are where OSM's grass starts and ends; grass track stops "
                    f"at platforms, crossings and junctions by itself."}


def write_sets(lines):
    t0 = time.time()
    polys, tree = osm_grass()
    print(f"OSM grass areas: {len(polys)} ({time.time() - t0:.0f} s)")
    truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
    cards = {}
    for line in lines:
        data = json.loads((ROOT / f"data/line{line}.json").read_text(encoding="utf-8"))
        rt, flags = under_route(data, polys, tree)
        d = calibrate(data, truth, flags)
        within = sum(v <= 5 for v in d)
        print(f"line {line}: OSM grass on the ground under the axis {sum(flags)} m; inside the known grass "
              f"{len(d)} OSM edges, {within} within 5 m of the built grass's"
              + (f" (median {statistics.median(d):.1f} m, worst {max(d):.0f} m)" if d else ""))
        cards[line] = [card(line, data, rt, a, b) for a, b in candidates(data, truth, rt, flags)]
    # (one place on several lines: one id, its lines listed on every line's card)
    flat = [c for cs in cards.values() for c in cs]
    for c in flat:
        twin = next((o for o in flat if o is not c and o["id"] != c["id"] and
                     ((o["x"] - c["x"]) ** 2 + (o["y"] - c["y"]) ** 2) ** 0.5 < SAME), None)
        if twin and twin["line"] < c["line"]:
            c["id"] = twin["id"]
    for c in flat:
        c["lines"] = sorted({o["line"] for o in flat if o["id"] == c["id"]}, key=int)
    for line, cs in cards.items():
        p = ROOT / "reports" / "review" / f"grass-track-{line}.json"
        if not cs:
            if p.exists():
                os.remove(p)
            print(f"line {line}: no cards")
            continue
        body = {"schema": 1, "issue": 503, "line": line, "title": "Grass track: OSM maps grass over the track",
                "findings": cs}
        with replacing(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {line}: {len(cs)} cards, " + ", ".join(f"s {c['s0']}-{c['s1']}" for c in cs))


TRUTH_NOTE = ("The user's answers to the grass track review (reports/review/grass-track-N.json, tools/grass_review.py, "
              "#503): OSM's grass over our track. `answer` grass lays grass track between the two points on the card's "
              "lines (tools/track_styles.py, its holes cut); not grass and other level keep the place as it is and off "
              "the review.")


def do_import(lines, reviews):
    cards, newest = {}, {}
    for line in lines:
        cp = ROOT / "reports" / "review" / f"grass-track-{line}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                cards.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{line}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "grass track" and r.get("v") in ANSWER and r.get("id") in cards:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    old = json.loads(truth_p.read_text(encoding="utf-8")).get("grassReview", {}).get("answers", [])
    got = {a["id"]: a for a in old}
    for i, r in newest.items():
        c = cards[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "lines": c["lines"], "between": c["between"], "answer": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, grass track review (reports/review/grass-track-{c['line']}.json), {day} (#503)"}
    answers = sorted(got.values(), key=lambda a: a["id"])
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": answers})
    print(f"data/truth.json grassReview: {len(answers)} answers ({len(newest)} from this import)")


def write_truth(p, section):
    """data/truth.json `grassReview`, the rest of the file as it is (as tools/stop_signs_review.py write_truth)."""
    text = p.read_text(encoding="utf-8")
    before = json.loads(text)
    key = '\n "grassReview": '
    body = json.dumps(section, ensure_ascii=False, indent=1).replace("\n", "\n ")
    if key in text:
        i = text.index(key) + len(key)
        text = text[:i] + body + text[json.JSONDecoder().raw_decode(text, i)[1]:]
    else:
        text = text.rstrip()[:-1].rstrip() + "," + key + body + "\n}\n"
    after = json.loads(text)
    assert after["grassReview"] == section
    assert {k: v for k, v in after.items() if k != "grassReview"} == {k: v for k, v in before.items() if k != "grassReview"}
    with replacing(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default=LINES)
    ap.add_argument("--import", dest="imp", action="store_true", help="the user's answers into data/truth.json")
    ap.add_argument("--reviews", default="reports/reviews")
    a = ap.parse_args()
    lines = a.lines.split(",")
    if a.imp:
        do_import(lines, a.reviews)
    else:
        write_sets(lines)


if __name__ == "__main__":
    main()
