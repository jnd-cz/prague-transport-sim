# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's stairs as the ground draws them: measured per line, and the worst for the user's review (#447).

    python -P -E tools/stairs_review.py [--lines 9,17,22,23,37]        # the table, and the review sets
    python -P -E tools/stairs_review.py --table [--lines ...]           # the table alone
    python -P -E tools/stairs_review.py --import [--reviews reports/reviews]

- **The table** (per line): the level-0 stairs areas with a height at every outline point; those that are one flight
  (ground_mesh.flight, #762); the rest, drawn on their outline's triangles (ground_mesh.SurveySurface); the plan area
  of the rest steeper than 1:1 on a STEP grid (no stair is: 17 / 29 cm is 0.59); the areas with ODD m² or more of it.
  It measures each area's own surface, before the ground fuses it with its neighbours.
- **The cards** (reports/review/stairs-N.json): the WORST places with the most steep area, and the places the issue's
  thread asked about (ASKED). The lines are merged: an area on two lines' files (one city frame) is one card in both
  sets. Each asks what kind of stairs stand there; the kinds are what #447's rules are written for. Pins mark the
  outline's lowest and highest points.
- **--import** takes the answers (python -P -E tools/deploy.py --pull, in the deploy checkout) into data/truth.json
  `stairsReview`, keyed by place: a point inside the area, as lat/lon (survey area numbers change with a rebuild).
  An area holding an answered place gets no card again, unsure included: the user answers unsure where the imagery
  does not show the stairs (a private garden, 2026-11-22), and another look would not either.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
import ground_mesh as gm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINES = "9,17,22,23,37"
STEP = 0.25   # m: the grid the steep area is counted on
ODD = 0.5     # m²: an area with this much steeper than 1:1 is drawn wrong (rounding on the grid stays under it)
WORST = 20    # the places with the most steep area that get a card
SAME = 0.5    # two lines' areas overlapping by this share of the smaller are one place
KINDS = [  # (the answer on the card, its key in data/truth.json)
    ("one flight, or flights in a straight line with landings", "flight"),
    ("flights that turn (a dog-leg, a U, round a tower)", "turning"),
    ("sunk: steps down between walls, below the ground round them", "sunk"),
    ("a wide step or steps between two levels side by side (a terrace's edge)", "two levels"),
    ("more than stairs: a wall, a bed or a ramp inside the area", "more than stairs"),
    ("a structure: stairs in the air, on a bridge or on a building", "structure"),
    ("no stairs here", "not stairs"),
]
UNSURE = "unsure"
ANSWER = {**dict(KINDS), UNSURE: UNSURE}   # (unsure: no card again, no rule reads it)
# Places the issue's thread asked about (x, y in the city frame, metres): a card wherever they are.
ASKED = [
    (4001.4, 1411.9, "a flight's 14 step noses lead 4 m down along a building's wall, the sidewalk's level on the other "
                     "side; the lidar shows only the sidewalk's level (#447, 2026-11-20)"),
    (-619.9, -565.0, "beside the National Theatre, near the Divadelní underpass, where the user first asked for stairs' "
                     "own rule (2026-11-10)"),
    (-2126.1, -6511.4, "Modřany's stair tower on the estakáda: the stairs at its foot, the flight up to the deck beside "
                       "them at level 1 (#445, 2026-11-10)"),
    (1417.7, 2496.9, "stairs partly under a level-1 cover; IPR reads the cover's top, 3-5 m over the survey's stairs "
                     "(#444, 2026-11-11)"),
    (1458.2, 2502.8, "the pair of the stairs beside them, partly under the same cover (#444, 2026-11-11)"),
]
FOOT, TOP = "#3e9dff", "#ffffff"


def stairs(D):
    """The level-0 stairs areas of a survey file with a height at every outline point: [index]."""
    return [i for i, a in enumerate(D["areas"]) if a["c"] == "stairs" and a.get("l", 0) == 0 and len(a["r"]) >= 3
            and all(q[2] is not None for q in a["r"])]


def outline(a):
    g = shapely.Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
    return g if g.is_valid else shapely.make_valid(g)


def steep(z):
    """Plan area (m²) of a STEP grid of heights steeper than 1:1 (NaN outside)."""
    gy, gx = np.gradient(z, STEP)
    s = np.hypot(gx, gy)
    return float(np.count_nonzero(np.isfinite(s) & (s > 1.0)) * STEP * STEP)


def measure(D):
    """(counts, rows) of a survey file's stairs: the counts for the table, a row for each area that is not one flight."""
    ids = stairs(D)
    rest = [i for i in ids if gm.flight(D["areas"][i]) is None]
    S = gm.SurveySurface(D, rest)
    n = {"stairs": len(ids), "m2": sum(outline(D["areas"][i]).area for i in ids), "flight": len(ids) - len(rest),
         "rest": len(rest), "rest m2": 0.0, "steep": 0.0, "odd": 0, "tall": 0}
    rows = []
    for i in rest:
        a = D["areas"][i]
        g = outline(a)
        lo, hi = min(a["r"], key=lambda q: q[2]), max(a["r"], key=lambda q: q[2])
        n["tall"] += hi[2] - lo[2] > 10
        s = 0.0
        if g.area >= 0.5:
            x0, y0, x1, y1 = g.bounds
            X, Y = np.meshgrid(np.arange(x0, x1 + STEP, STEP), np.arange(y0, y1 + STEP, STEP))
            inside = shapely.contains_xy(g, X, Y)
            if inside.sum() >= 8:
                z = np.full(X.shape, np.nan)
                z[inside] = S.at(i, X[inside], Y[inside])
                s = steep(z)
        n["rest m2"] += g.area
        n["steep"] += s
        n["odd"] += s >= ODD
        p = g.representative_point()
        rows.append({"area": i, "g": g, "x": p.x, "y": p.y, "m2": g.area, "steep": s, "points": len(a["r"]),
                     "foot": lo[:3], "top": hi[:3]})
    return n, rows


def table(counts):
    out = ["| line | stairs (level 0) | m² | one flight | the rest | their m² | steeper than 1:1, m² | "
           f"areas with {ODD} m² or more of it | the rest rising over 10 m |", "|---|---|---|---|---|---|---|---|---|"]
    for ln, n in counts.items():
        out.append(f"| {ln} | {n['stairs']:,} | {n['m2']:,.0f} | {n['flight']:,} | {n['rest']:,} | {n['rest m2']:,.0f} | "
                   f"{n['steep']:,.0f} | {n['odd']} | {n['tall']} |")
    return "\n".join(out)


def places(rows):
    """{line: rows} merged into places: [{row of the first line, 'lines'}], an area on several lines once."""
    out = []
    for ln in sorted(rows, key=int):
        for r in rows[ln]:
            for p in out:
                if p["g"].intersects(r["g"]):
                    shared = p["g"].intersection(r["g"]).area
                    if shared >= SAME * min(p["g"].area, r["g"].area):
                        p["lines"].append(ln)
                        p["steep"] = max(p["steep"], r["steep"])
                        break
            else:
                out.append({**r, "line": ln, "lines": [ln]})
    return out


def answered(truth):
    """The answered places in the city frame: [(x, y)]."""
    got = truth.get("stairsReview", {}).get("answers", [])
    if not got:
        return []
    F = Frame()
    return [tuple(float(v) for v in F.xy(*a["place"])) for a in got]


def choose(P, truth):
    """The places that get a card: the WORST by steep area, and those ASKED; none holding an answered place."""
    done = [shapely.Point(x, y) for x, y in answered(truth)]
    todo = [p for p in P if not any(p["g"].covers(q) for q in done)]
    pick = {id(p): (p, None) for p in sorted((p for p in todo if p["steep"] >= ODD), key=lambda p: -p["steep"])[:WORST]}
    for x, y, why in ASKED:
        q = shapely.Point(x, y)
        hit = min(todo, key=lambda p: p["g"].distance(q), default=None)
        if hit is not None and hit["g"].distance(q) <= 5:
            pick[id(hit)] = (hit, why)   # (one of the worst keeps its place in the list)
    return list(pick.values())


def card(p, why=None):
    F = Frame()
    lat, lon = (float(v) for v in F.ll(p["x"], p["y"]))
    (fx, fy, fz), (tx, ty, tz) = p["foot"], p["top"]
    drawn = (f"{p['steep']:.1f} m² of it steeper than 1:1, which no stair is" if p["steep"] >= ODD else
             "none of it steeper than 1:1")
    info = (f"A survey stairs area of {p['m2']:.0f} m², its outline from {fz:.2f} m to {tz:.2f} m ({p['points']} points; "
            f"area {p['area']} of line {p['line']} in this build). The game draws it on the outline's triangles, "
            f"{drawn}. What stands here? The pins are the outline's lowest and highest points.")
    if why:
        info += f" Asked in #447: {why}."
    return {"kind": "stairs", "id": f"stairs-{lat:.5f}-{lon:.5f}", "line": p["line"], "lines": p["lines"],
            "x": round(p["x"], 1), "y": round(p["y"], 1), "mag": round(p["steep"], 1), "status": "review",
            "place": [round(lat, 7), round(lon, 7)],
            "marks": [{"x": round(fx, 1), "y": round(fy, 1), "label": f"lowest {fz:.2f} m", "color": FOOT},
                      {"x": round(tx, 1), "y": round(ty, 1), "label": f"highest {tz:.2f} m", "color": TOP}],
            "options": [k for k, _ in KINDS] + [UNSURE], "info": info}


def load(lines):
    counts, rows = {}, {}
    for ln in lines:
        D = json.loads((ROOT / "data" / f"line{ln}.dtm.json").read_text(encoding="utf-8"))
        counts[ln], rows[ln] = measure(D)
    return counts, rows


def write_sets(lines, counts, rows):
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    P = places(rows)
    chosen = choose(P, truth)
    print(f"\n{len(P)} places not one flight, {sum(p['steep'] >= ODD for p in P)} with {ODD} m² or more steeper than "
          f"1:1 ({sum(p['steep'] for p in P):,.0f} m²); cards: {len(chosen)}")
    cards = [card(p, why) for p, why in chosen]
    for ln in lines:
        cs = [c for c in cards if ln in c["lines"]]
        path = ROOT / "reports" / "review" / f"stairs-{ln}.json"
        if not cs:
            if path.exists():
                os.remove(path)
            print(f"line {ln}: no cards")
            continue
        body = {"schema": 1, "issue": 447, "line": ln, "title": "Stairs: what kind stands here", "findings": cs}
        with replacing(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {ln}: {len(cs)} cards ({path.relative_to(ROOT).as_posix()})")


TRUTH_NOTE = ("The user's answers to the stairs review (reports/review/stairs-N.json, tools/stairs_review.py, #447): what "
              "kind of stairs stand at a place, for the rules that draw the ground under the survey's stairs. `place` is a "
              "point inside the survey's stairs area (lat, lon); `kind` is one of flight, turning, sunk, two levels, more "
              "than stairs, structure, not stairs, or unsure (the imagery does not show them; no rule reads it).")


def do_import(lines, reviews):
    cards, newest = {}, {}
    for ln in lines:
        cp = ROOT / "reports" / "review" / f"stairs-{ln}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                cards.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{ln}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "stairs" and r.get("v") in ANSWER and r.get("id") in cards:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    old = json.loads(truth_p.read_text(encoding="utf-8")).get("stairsReview", {}).get("answers", [])
    got = {a["id"]: a for a in old}
    for i, r in newest.items():
        c = cards[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "lines": c["lines"], "place": c["place"], "kind": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, stairs review (reports/review/stairs-{c['line']}.json), {day} (#447)"}
    answers = sorted(got.values(), key=lambda a: a["id"])
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": answers})
    print(f"data/truth.json stairsReview: {len(answers)} answers ({len(newest)} from this import)")


def write_truth(p, section, key="stairsReview"):
    """data/truth.json's `key` section, the rest of the file as it is (as tools/grass_review.py write_truth)."""
    text = p.read_text(encoding="utf-8")
    before = json.loads(text)
    k = f'\n "{key}": '
    body = json.dumps(section, ensure_ascii=False, indent=1).replace("\n", "\n ")
    if k in text:
        i = text.index(k) + len(k)
        text = text[:i] + body + text[json.JSONDecoder().raw_decode(text, i)[1]:]
    else:
        text = text.rstrip()[:-1].rstrip() + "," + k + body + "\n}\n"
    after = json.loads(text)
    assert after[key] == section
    assert {a: v for a, v in after.items() if a != key} == {a: v for a, v in before.items() if a != key}
    with replacing(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default=LINES)
    ap.add_argument("--table", action="store_true", help="the table alone, no review sets written")
    ap.add_argument("--import", dest="imp", action="store_true", help="the user's answers into data/truth.json")
    ap.add_argument("--reviews", default="reports/reviews")
    a = ap.parse_args()
    lines = a.lines.split(",")
    if a.imp:
        do_import(lines, a.reviews)
        return
    t0 = time.time()
    counts, rows = load(lines)
    print(table(counts))
    print(f"({time.time() - t0:.0f} s)")
    if not a.table:
        write_sets(lines, counts, rows)


if __name__ == "__main__":
    main()
