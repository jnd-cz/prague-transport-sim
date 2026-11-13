# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user's answers to the survey-ground review cards into data/truth.json surveyGround.places (#446).

    python -I tools/survey_ground_answers.py reports/reviews/line37.json [...]   # answer files of review mode
    python -I tools/survey_ground_answers.py --dry-run reports/reviews/line37.json

tools/dtm.py holds a ground-level survey area for review when it sits steadily off IPR's lidar and neither the surveyed
rails nor DMR 5G say which is right (tools/zps_ground.py); it writes those to reports/review/survey-ground-N.json. Review
mode stores an answer per card (reports/reviews/lineN.json, keyed by the card's place). An answer that is one of the
cards' options becomes a fact keyed by the area's place (lat/lon), which dtm.py's next build obeys; other answers
("unsure", notes) stay held and are listed. Only the surveyGround section of data/truth.json is rewritten.
"""
import datetime
import glob
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRUTH = os.path.join(ROOT, "data", "truth.json")
SECTION = "surveyGround"
# the review cards' answers (tools/zps_ground.py review_set) and the verdicts they record
ANSWERS = {"The survey is right: the ground changed since the lidar": "survey",
           "The lidar is right: move the survey to it": "lidar"}
KIND = "survey ground"


def cards(folder):
    """The held areas of every line's set, by the place review mode keys their answers with."""
    out = {}
    for f in glob.glob(os.path.join(folder, "survey-ground-*.json")):
        d = json.load(open(f, encoding="utf-8"))
        for c in d.get("findings", []):
            out[f"file|{KIND}|{c['x']:.1f},{c['y']:.1f}"] = dict(c, line=d.get("line"))
    return out


def facts(answer_files, held_cards):
    """The new facts and the answers left held (with why)."""
    new, held = [], []
    for path in answer_files:
        items = json.load(open(path, encoding="utf-8")).get("items", {})
        for key, a in items.items():
            if not key.startswith(f"file|{KIND}|"):
                continue
            card = held_cards.get(key)
            if card is None:
                held.append((key, "no such card in reports/review/ (rebuilt away?)"))
                continue
            verdict = ANSWERS.get(a.get("v"))
            if verdict is None:
                held.append((key, f"answer {a.get('v')!r}" + (f", note: {a['note']}" if a.get("note") else "")))
                continue
            day = datetime.datetime.fromtimestamp((a.get("t") or 0) / 1000, datetime.timezone.utc).date().isoformat()
            said = a["v"] + (f" ({a['note']})" if a.get("note") else "")
            # (the area's class and size pick it among those holding the point: a courtyard's lawn is a hole in the
            # sidewalk around it; cards before #446's last build carry them only in their text)
            cls = card.get("c") or card["info"].split(",")[0]
            m2 = card.get("m2") or float(re.search(r"([\d.]+) m²", card["info"]).group(1))
            new.append({"lat": card["lat"], "lon": card["lon"], "c": cls, "m2": m2, "verdict": verdict, "line": card["line"],
                        "said": said, "where": f"review mode, {day} (reports/reviews/{os.path.basename(path)}, #446)",
                        "card": card["info"]})
    return new, held


def merged(old, new):
    """The old places with the new ones replacing any at the same place."""
    at = {(round(p["lat"], 6), round(p["lon"], 6)): p for p in old}
    for p in new:
        at[(round(p["lat"], 6), round(p["lon"], 6))] = p
    return sorted(at.values(), key=lambda p: (p["lat"], p["lon"]))


def rewrite_section(text, value):
    """data/truth.json's text with the SECTION's value replaced, the rest byte for byte (the file is formatted by hand)."""
    key = f'\n "{SECTION}": '
    i = text.index(key) + len(key)
    _, end = json.JSONDecoder().raw_decode(text, i)
    body = json.dumps(value, ensure_ascii=False, indent=1).replace("\n", "\n ")
    return text[:i] + body + text[end:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    new, held = facts(args, cards(os.path.join(ROOT, "reports", "review")))
    text = open(TRUTH, encoding="utf-8").read()
    section = json.loads(text)[SECTION]
    section["places"] = merged(section.get("places", []), new)
    for p in new:
        print(f"line {p['line']} {p['lat']}, {p['lon']}: {p['verdict']} ({p['said']})")
    for key, why in held:
        print(f"held {key}: {why}")
    if "--dry-run" in sys.argv:
        return
    with replacing(TRUTH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(rewrite_section(text, section))
    print(f"{len(new)} facts recorded in data/truth.json {SECTION}, {len(held)} answers held")


if __name__ == "__main__":
    main()
