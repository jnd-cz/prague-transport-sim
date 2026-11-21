# SPDX-License-Identifier: AGPL-3.0-or-later
"""The facts a source now matches, for the user's review before they retire (#670):
    python -P -E tools/fact_review.py            reports/review/fact-matches-N.json from the built data
    python -P -E tools/fact_review.py --import   the answers (reports/reviews/lineN.json) into data/truth.json

The user, 2026-11-18: "I will need to review each case of new match to make sure we get proper fact replacement."
A card per fact whose state is `matches` (tools/fact_status.py) and whose state gives its point (`at`): the user's
fact in yellow, the source's point (`src`) in red, over the orthophoto on the review page. Its answers:
- retire: a placed stop sign becomes a confirmation of the DTM's sign (the user: "Yes turn them into confirmation of
  the DTM sign"): the build takes the same sign, the stop-sign review keeps its card away, and a DTM refresh that
  moves the sign shows as `moved`. Any other fact is deleted from data/truth.json (the user: "I would delete them
  from the file, git history is good enough"): its own text is cut out, the rest of the file stays as it is.
- keep, unsure: the fact stays.
A matching fact without a point (a speed, a structure, a style answer) is listed by fact_status.py and retired by hand
in a PR that quotes it.
"""
import argparse
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fact_status  # noqa: E402
import sources  # noqa: E402
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
from stop_signs_review import BY_SOURCE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISSUE = 670
YOURS, SOURCE = "#ffd60a", "#ff3b30"
RETIRE_SIGN = "retire: the DTM sign is right (mine becomes a confirmation of it)"
RETIRE = "retire: the source is right (delete my fact)"
KEEP, UNSURE = "keep my fact", "unsure"
# the marks' labels: the user's fact, the source's point
WHAT = {"stopSigns": ("your placed stop sign", "the DTM's sign (state 2024)"),
        "switchTips": ("your switch tip", "DI's fork"),
        "photoTracks": ("your orthophoto track", "DI's track"),
        "steppedAnswers": ("your 'smooth' answer", "DI's line")}


def card_id(section, fid):
    return f"fact-{section}-{fid}"


def cards(facts, frame=None):
    """{line: [card]}: a card per fact in state `matches` whose state gives its point, on the first line it matches
    on, the farthest first (`mag`: cm). `frame`: the city frame (tools/geo.py), for each card's lat, lon."""
    frame, out = frame or Frame(), {}
    for f in facts:
        d = f.get("detail") or {}
        if f["state"] != "matches" or not d.get("at"):
            continue
        line = next(ln for ln, s in f["lines"] if s == "matches")
        yours, theirs = WHAT.get(f["section"], ("your fact", "the source"))
        x, y = d["at"]
        lat, lon = frame.ll(x, y)
        marks = [{"x": x, "y": y, "label": yours, "color": YOURS}]
        if d.get("src"):
            marks.append({"x": d["src"][0], "y": d["src"][1], "label": theirs, "color": SOURCE})
        off = d.get("off")
        retire = RETIRE_SIGN if f["section"] == "stopSigns" else RETIRE
        info = (f"{f['id']}: {theirs} lies {off} m from {yours} (data/truth.json {f['section']}); without it the build "
                f"takes {theirs}. Is the source right? \"{retire}\" or keep yours.")
        if f["section"] == "steppedAnswers":  # (#672: no point of the source's, the step is gone from DI's line)
            info = (f"{f['id']}: {theirs} has no stepped curve within reach of {yours} now (tools/lint.js steppedCurves' "
                    f"rule on DI's own line); without it the build fits DI's points there. Is the source right? "
                    f"\"{retire}\" or keep yours.")
        out.setdefault(line, []).append({
            "kind": "fact match", "id": card_id(f["section"], f["id"]), "section": f["section"], "fact": f["id"],
            "line": line, "lines": [ln for ln, _ in f["lines"]], "x": x, "y": y,
            "place": [round(float(lat), 7), round(float(lon), 7)], "mag": round((off or 0) * 100), "status": "review",
            "marks": marks, "options": [retire, KEEP, UNSURE],
            "info": info})
    for cs in out.values():
        cs.sort(key=lambda c: -c["mag"])
    return out


def write_sets(by_line, root=ROOT):
    """reports/review/fact-matches-N.json per line with cards; a line's set without any is removed (an empty one
    would wait in the review directory)."""
    folder = os.path.join(root, "reports", "review")
    for name in os.listdir(folder):
        if name.startswith("fact-matches-") and name.endswith(".json") and name[13:-5] not in by_line:
            os.remove(os.path.join(folder, name))
    for line, cs in sorted(by_line.items()):
        out = {"schema": 1, "issue": ISSUE, "line": line, "title": "Facts a source now matches: retire them?", "findings": cs}
        with replacing(os.path.join(folder, f"fact-matches-{line}.json"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


# ------------------------------------------------------------------ data/truth.json, edited in place
def _ws(text, i):
    while text[i] in " \t\r\n":
        i += 1
    return i


def _spans(text, i):
    """The members of the object or the items of the list that starts at text[i]: [(key or index, start, end)]."""
    dec, close = json.JSONDecoder(), {"{": "}", "[": "]"}[text[i]]
    obj, out, i = text[i] == "{", [], i + 1
    while True:
        i = _ws(text, i)
        if text[i] == close:
            return out
        key = len(out)
        if obj:
            key, i = dec.raw_decode(text, i)
            i = _ws(text, i) + 1  # (the colon)
            i = _ws(text, i)
        _, j = dec.raw_decode(text, i)
        out.append((key, i, j))
        i = _ws(text, j)
        if text[i] == ",":
            i += 1


def _items(text, path):
    i = _ws(text, 0)
    for k in path:
        i = next(s for key, s, _ in _spans(text, i) if key == k)
    return _spans(text, i)


def drop(text, path, index):
    """The text without the list item `index` at `path` (and its comma); everything else as it was."""
    items = _items(text, path)
    _, s, e = items[index]
    if index > 0:
        s = items[index - 1][2]
    elif len(items) > 1:
        e = items[1][1]
    else:  # (the last one: the list reads [])
        s, e = text.rindex("[", 0, s) + 1, text.index("]", e)
    return text[:s] + text[e:]


def put(text, path, index, value):
    """The text with the list item `index` at `path` replaced by `value`, dumped at the item's own indent."""
    _, s, e = _items(text, path)[index]
    col = s - text.rindex("\n", 0, s) - 1
    return text[:s] + json.dumps(value, ensure_ascii=False, indent=1).replace("\n", "\n" + " " * col) + text[e:]


def retire(text, card, day):
    """data/truth.json's text with the card's fact retired: a stop sign confirms the DTM's sign, any other goes."""
    path, idf = sources.OVERRIDES[card["section"]][:2]
    lst = json.loads(text)
    for k in path:
        lst = lst[k]
    i = next(i for i, f in enumerate(lst) if str(idf(f)) == card["fact"])
    if card["section"] != "stopSigns":
        return drop(text, path, i)
    src = next(m for m in card["marks"] if m["color"] == SOURCE)
    f = dict(lst[i])
    f.update(x=src["x"], y=src["y"], how=BY_SOURCE["DTM"], pin=[src["x"], src["y"]], pinFrom="DTM",
             source=f"user, fact-match review (reports/review/fact-matches-{card['line']}.json) {day} (#670): the DTM's "
                    f"sign confirmed in place of the user's, placed {card['mag'] / 100} m from it")
    return put(text, path, i, f)


def answers(lines, reviews, root=ROOT):
    """The newest answer per card ({id: record}) from the review store (per line: {card id: record} or [record])."""
    newest = {}
    for line in lines:
        p = os.path.join(root, reviews, f"line{line}.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            a = json.load(fh)
        items = a.get("items", a) if isinstance(a, dict) else a
        for r in (items.values() if isinstance(items, dict) else items):
            if r.get("kind") == "fact match" and r.get("v") and r.get("t", 0) >= newest.get(r.get("id"), {}).get("t", 0):
                newest[r["id"]] = r
    return newest


def do_import(lines, reviews, root=ROOT):
    truth_p = os.path.join(root, "data", "truth.json")
    with open(truth_p, encoding="utf-8") as fh:
        text = fh.read()
    folder = os.path.join(root, "reports", "review")
    by_id = {}
    for n in sorted(os.listdir(folder)):
        if n.startswith("fact-matches-") and n.endswith(".json"):
            with open(os.path.join(folder, n), encoding="utf-8") as fh:
                by_id.update((c["id"], c) for c in json.load(fh)["findings"])
    got = answers(lines, reviews, root)
    done = []
    for cid, r in sorted(got.items()):
        c = by_id.get(cid)
        if c and r["v"] in (RETIRE, RETIRE_SIGN):
            day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
            text = retire(text, c, day)
            done.append(c)
    json.loads(text)
    with replacing(truth_p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    for c in done:
        print(f"retired: {c['section']}: {c['fact']}" + (" (now a confirmation of the DTM's sign)" if c["section"] == "stopSigns" else ""))
    kept = [c for cid, c in by_id.items() if cid in got and c not in done]
    print(f"{len(done)} retired, {len(kept)} kept or unsure, {len(by_id) - len(done) - len(kept)} not answered")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--import", dest="imp", action="store_true", help="the user's answers into data/truth.json")
    ap.add_argument("--reviews", default=os.path.join("reports", "reviews"))
    args = ap.parse_args()
    if args.imp:
        return do_import(args.lines.split(","), args.reviews)
    by_line = cards(fact_status.collect())
    write_sets(by_line)
    for line, cs in sorted(by_line.items()):
        print(f"line {line}: {len(cs)} facts a source matches: reports/review/fact-matches-{line}.json")
    if not by_line:
        print("no fact a source matches")


if __name__ == "__main__":
    main()
