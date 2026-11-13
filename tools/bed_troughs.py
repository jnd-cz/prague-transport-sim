# SPDX-License-Identifier: AGPL-3.0-or-later
"""The troughs beside the track beds, for the user to review (#548).

    python -P -E tools/headless.py --lines 9,17,22,23,37 --checks canted --out reports/troughs
    python -P -E tools/bed_troughs.py --cards reports/troughs          # reports/review/bed-troughs-N.json
    python -P -E tools/bed_troughs.py --import                         # the answers into data/truth.json bedTroughReview

The `canted` check's `buriedRails` (tools/lint.js) measures every drawn track's bed: where the ground 1 m past its edge
lies lower than both the edge and the ground 4 m out, by 10 cm to 1 m, it is a trough. What it is the measure cannot
tell: a ditch or a cutting's foot is real, a missing retaining wall leaves the terrain sloping where a wall stands, and
our ground laid wrongly sinks a ring around the bed. The user, 2026-11-13: "i would review those places to see what's
there. The one screenshot on line 37 shows there should be a wall there".

A card per place: the deepest trough of its line within SAME m, CARD_CM deep or more, not answered yet. The answers go
to data/truth.json `bedTroughReview`, keyed by the place's lat/lon: `real` (a ditch, a cutting: the measure leaves it),
`wall` (a retaining wall missing there: evidence for the walls step), `ours` (our ground is wrong: a defect of the
ground under the beds).
"""
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from atomic import replacing  # noqa: E402

LINES = "9,17,22,23,37"
CARD_CM = 40           # cm: a trough this deep gets a card (at 20 cm: 326 cards on the five lines)
SAME = 50              # m: troughs this near are one place (its deepest)
DONE = 15              # m: a card this near an answered place is not asked again
REAL, WALL, OURS, UNSURE = ("a ditch or a cutting: the ground is right", "a retaining wall is missing here",
                            "our ground is wrong here (sunk around the bed)", "unsure")
ANSWER = {REAL: "real", WALL: "wall", OURS: "ours"}
READER = ("tools/bed_troughs.py (an answered place gets no card); reference for the walls step (`wall`) until an issue "
          "reads it")
TRUTH_NOTE = ("The user's answers to the bed trough review (reports/review/bed-troughs-N.json, tools/bed_troughs.py, "
              "#548), by the place's lat/lon: `real` is a ditch or a cutting (the trough measure leaves it), `wall` a "
              "retaining wall missing there, `ours` our ground sunk around the bed.")


def find(o, key):
    """The first value under key anywhere in o."""
    if isinstance(o, dict):
        if key in o:
            return o[key]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            x = find(v, key)
            if x is not None:
                return x
    return None


def places(troughs, card_cm=CARD_CM, same=SAME):
    """The troughs ([x, y, depth m, track, rise m]) as places: the deepest first, none within `same` m of a deeper
    one, `card_cm` deep or more."""
    out = []
    for t in sorted(troughs, key=lambda t: -t[2]):
        if t[2] * 100 < card_cm:
            break
        if all(math.hypot(t[0] - o[0], t[1] - o[1]) >= same for o in out):
            out.append(t)
    return out


def card(line, t, frame, stops_near):
    x, y, depth, track, rise = (list(t) + [None])[:5]
    lat, lon = (float(v) for v in frame.ll(x, y))
    beyond = ("the ground 4 m out stands {:.0f} cm over the bed's edge".format(rise * 100) if rise is not None and rise > 0
              else "the ground 4 m out lies {:.0f} cm under the bed's edge".format(-rise * 100) if rise is not None else "")
    return {
        "kind": "bed trough", "id": f"trough-{lat:.5f}-{lon:.5f}", "line": line, "x": x, "y": y,
        "mag": round(depth * 100), "status": "review", "place": [round(lat, 6), round(lon, 6)],
        "marks": [{"x": x, "y": y, "label": "the trough", "color": "#3e9dff"}],
        "options": [REAL, WALL, OURS, UNSURE],
        "info": f"{stops_near}: beside track {track}'s bed the ground 1 m past its edge lies {depth * 100:.0f} cm under "
                f"the edge and under the ground 4 m out" + (f" ({beyond})" if beyond else "") +
                ". What is there in reality: a ditch or a cutting's side, a retaining wall, or is our ground sunk "
                "around the bed?"}


def near_stop(data, x, y):
    """Where (x, y) is: the nearest route position and the stop nearest to it, and how far off the route."""
    best, s0 = None, 0.0
    p = data["path"]
    for a, b in zip(p, p[1:]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ex, ey) or 1e-9
        u = max(0.0, min(1.0, ((x - a[0]) * ex + (y - a[1]) * ey) / L / L))
        d = math.hypot(x - a[0] - ex * u, y - a[1] - ey * u)
        if best is None or d < best[0]:
            best = (d, s0 + u * L)
        s0 += L
    d, s = best
    st = min(data["stops"], key=lambda q: abs(q["s"] - s))
    return f"near {st['name']} (route s {s:.0f}, {d:.0f} m off the route)"


def cards(folder, lines):
    from geo import Frame
    F = Frame()
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    done = [F.xy(*a["place"]) for a in (truth.get("bedTroughReview") or {}).get("answers", [])]
    # (a place on two lines' track is asked once, on the first line: lines 22 and 23 share Malostranská to Klárov)
    asked = []
    for line in sorted(lines, key=int):
        r = json.loads((ROOT / folder / f"line{line}-canted.json").read_text(encoding="utf-8"))
        b = find(r, "buriedRails")
        if not b or "all" not in (b.get("sunken") or {}):
            sys.exit(f"{folder}/line{line}-canted.json: no trough places (run the canted check with this lint.js)")
        data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        cs = [card(line, t, F, near_stop(data, t[0], t[1])) for t in places(b["sunken"]["all"])
              if all(math.hypot(t[0] - d[0], t[1] - d[1]) >= DONE for d in done)
              and all(math.hypot(t[0] - d[0], t[1] - d[1]) >= SAME for d in asked)]
        asked += [(c["x"], c["y"]) for c in cs]
        p = ROOT / "reports" / "review" / f"bed-troughs-{line}.json"
        if not cs:
            if p.exists():
                p.unlink()
            print(f"line {line}: no cards")
            continue
        body = {"schema": 1, "issue": 548, "line": line, "title": "Troughs beside the track beds: ditch, wall or our ground",
                "findings": cs}
        with replacing(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {line}: {len(cs)} cards")


def do_import(lines, reviews):
    found, newest = {}, {}
    for line in lines:
        cp = ROOT / "reports" / "review" / f"bed-troughs-{line}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                found.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{line}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "bed trough" and r.get("v") in ANSWER and r.get("id") in found:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    sec = json.loads(truth_p.read_text(encoding="utf-8")).get("bedTroughReview", {})
    got = {a["id"]: a for a in sec.get("answers", [])}
    for i, r in newest.items():
        c = found[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "line": c["line"], "place": c["place"], "answer": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, bed trough review (reports/review/bed-troughs-{c['line']}.json), {day} (#548)"}
    from cross_level import write_truth
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": sorted(got.values(), key=lambda a: a["id"])}, "bedTroughReview")
    readers = json.loads(truth_p.read_text(encoding="utf-8"))["readers"]
    if "bedTroughReview" not in readers:
        write_truth(truth_p, {**readers, "bedTroughReview": READER}, "readers")
    print(f"data/truth.json bedTroughReview: {len(got)} answers ({len(newest)} from this import)")


def main():
    lines = (sys.argv[sys.argv.index("--lines") + 1] if "--lines" in sys.argv else LINES).split(",")
    if "--cards" in sys.argv:
        cards(sys.argv[sys.argv.index("--cards") + 1], lines)
    elif "--import" in sys.argv:
        do_import(lines, sys.argv[sys.argv.index("--reviews") + 1] if "--reviews" in sys.argv else "reports/reviews")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
