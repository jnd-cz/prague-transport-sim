"""The review directory's index (#288): every review set in reports/review/, the issue that waits for it, its
lines, and the open PRs' questions for the user, for reviews.html.

    python -I tools/review_sets.py             # writes reports/review/index.json (for tools/serve.py)
    python -I tools/review_sets.py --print     # the same to stdout

tools/deploy.py builds it at each deploy, so a new file in reports/review/ shows up without a list to edit.
The answers are not in it: the page counts them live from the answer store (src/reviewIndex.js), with the
findings read as review mode reads them (src/reviewFindings.js).

A set is a JSON file in reports/review/ with findings (a span queue another file names in `span_file`, or
a file without findings, is not). Its title, issue and lines come from the file itself (`title` or
`about`, `issue`, `line` or `lines`), else from its findings (`line`, `lines_near`), else from its name
(`stop-signs-17.json`: line 17), else from KNOWN; what is still unknown is listed with the set.

The kerb review lists are sets too (#334), though no file holds them: they lie in each line's survey data
(tools/kerbs.py), where review mode reads them, so they always match the published build. Their entries carry the
findings' ids, for the page to count answers without loading a 10 MB survey file for each line.
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import board  # noqa: E402  (gh, git and the PRs' question sections)

FOLDER = os.path.join(ROOT, "reports", "review")
OUT = os.path.join(FOLDER, "index.json")
# sets whose tool does not write its issue or lines yet (the file's own fields win; drop an entry once its
# tool writes them)
KNOWN = {
    "track-heights.json": {"title": "Track heights: structure and street decisions", "issue": 202, "lines": ["17"]},
    "track-radius.json": {"title": "Track radius: where the design radius gave way", "issue": 197},
}
# issues closed into another, whose sets wait for that one now (the issue's closing comment says so)
MOVED = {20: 237}
KERB_ISSUE = 142  # (the kerb review lists wait for it)


def lines_of(root=ROOT):
    """The game's lines (data/lines.json), as strings."""
    try:
        with open(os.path.join(root, "data", "lines.json"), encoding="utf-8") as f:
            return [str(x["line"]) for x in json.load(f)]
    except (OSError, ValueError, KeyError, TypeError):
        return ["9", "17", "22", "23", "37"]


def findings(d):
    """The objects with numeric x and y (as review mode takes them: src/reviewFindings.js fileFindings)."""
    out = []

    def walk(o):
        if isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, dict):
            if isinstance(o.get("x"), (int, float)) and isinstance(o.get("y"), (int, float)):
                out.append(o)
                return
            for v in o.values():
                walk(v)
    walk(d)
    return out


def describe(name, d, known_lines):
    """One set's entry: its title, issue and lines, and what of them is unknown."""
    k = KNOWN.get(name, {})
    fs = findings(d)
    lines = d.get("lines") or ([d["line"]] if d.get("line") is not None else [])
    if not lines:
        lines = sorted({str(x) for f in fs for x in ([f["line"]] if f.get("line") is not None else []) + list(f.get("lines_near") or [])},
                       key=lambda v: (len(v), v))
    if not lines and (m := re.search(r"-(\d+)\.json$", name)) and m.group(1) in known_lines:
        lines = [m.group(1)]
    lines = [str(x) for x in (lines or k.get("lines") or [])]
    issue = d.get("issue") if isinstance(d.get("issue"), int) else k.get("issue")
    title = d.get("title") or k.get("title") or (d.get("about") if isinstance(d.get("about"), str) else None)
    unknown = [what for what, v in (("issue", issue), ("lines", lines)) if not v]
    return {"file": f"reports/review/{name}", "title": title, "issue": issue, "waitsFor": MOVED.get(issue, issue),
            "lines": lines, "findings": len(fs), "unknown": unknown}


def sets(folder=FOLDER, known_lines=None):
    known_lines = known_lines or lines_of()
    docs = {}
    for name in sorted(os.listdir(folder)) if os.path.isdir(folder) else []:
        if not name.endswith(".json") or name == "index.json":
            continue
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                docs[name] = json.load(f)
        except (OSError, ValueError):
            continue
    queues = {os.path.basename(d["span_file"]) for d in docs.values() if isinstance(d, dict) and d.get("span_file")}
    return [describe(n, d, known_lines) for n, d in docs.items()
            if isinstance(d, dict) and n not in queues and findings(d)]


def kerb_report(o):
    """The kerb report in a survey file's provenance, wherever the stamp put it (src/review.js findKerbs)."""
    if isinstance(o, dict):
        if isinstance(o.get("review"), list) and "platformSteps" in o:
            return o
        o = list(o.values())
    for v in o if isinstance(o, list) else []:
        r = kerb_report(v)
        if r:
            return r
    return None


def kerb_sets(root, known_lines):
    """One set per line with a kerb list; ids as review mode keys its findings (src/review.js kerbFindings,
    src/reviewFindings.js fid)."""
    out = []
    for line in known_lines:
        try:
            with open(os.path.join(root, "data", f"line{line}.dtm.json"), encoding="utf-8") as f:
                report = kerb_report(json.load(f).get("provenance"))
        except (OSError, ValueError):
            continue
        ids = [f"kerbs|{e['c']} {e['line']}|{e['x']:.1f},{e['y']:.1f}" for e in (report or {}).get("review", [])]
        if ids:
            out.append({"file": f"data/line{line}.dtm.json", "title": "Kerb review list", "issue": KERB_ISSUE,
                        "waitsFor": MOVED.get(KERB_ISSUE, KERB_ISSUE), "lines": [line], "findings": len(ids), "unknown": [], "ids": ids})
    return out


def issues(numbers):
    """{number: {title, state}} from GitHub; {} where it cannot be asked (the page then shows the number)."""
    def one(n):
        return n, board.gh("issue", "view", str(n), "--json", "title,state")
    with ThreadPoolExecutor(6) as ex:
        return {n: {"title": v["title"], "state": v["state"]} for n, v in ex.map(one, sorted(numbers)) if v}


def questions():
    """The open PRs' question sections for the user (tools/board.py's reading of the descriptions)."""
    prs = board.gh("pr", "list", "--state", "open", "--limit", "100", "--json", "number,title,body,url,isDraft") or []
    out = []
    for p in sorted(prs, key=lambda p: p["number"]):
        q = board.questions(p.get("body"), width=None)
        if q:
            out.append({"pr": p["number"], "title": p["title"], "url": p["url"], "draft": p.get("isDraft"),
                        "sections": [{"title": t, "items": items} for t, items in q]})
    return out


def build(root=ROOT, github=True):
    known_lines = lines_of(root)
    ss = sets(os.path.join(root, "reports", "review"), known_lines) + kerb_sets(root, known_lines)
    info = issues({s["issue"] for s in ss if s["issue"]} | {s["waitsFor"] for s in ss if s["waitsFor"]}) if github else {}
    for s in ss:
        s["issueInfo"] = info.get(s["issue"])
        s["waitsForInfo"] = info.get(s["waitsFor"])
    # (no file to delete once its issue is closed: it only leaves the directory, and review mode still shows it)
    ss = [s for s in ss if not ("ids" in s and (s["waitsForInfo"] or {}).get("state") == "CLOSED")]
    commit = board.git("rev-parse", "--short", "HEAD", cwd=root)
    return {"built": time.strftime("%Y-%m-%d %H:%M"), "commit": commit, "repo": "jnd-cz/prague-transport-sim",
            "lines": known_lines, "sets": ss, "questions": questions() if github else []}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    index = build()
    text = json.dumps(index, ensure_ascii=False, indent=1)
    if "--print" in sys.argv:
        print(text)
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    waiting = [s for s in index["sets"] if s["unknown"]]
    print(f"{OUT}: {len(index['sets'])} sets, {sum(s['findings'] for s in index['sets'])} findings, "
          f"{len(index['questions'])} PRs with questions" + (f"; unknown issue or lines: {', '.join(s['file'] for s in waiting)}" if waiting else ""))


if __name__ == "__main__":
    main()
