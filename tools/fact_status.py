# SPDX-License-Identifier: AGPL-3.0-or-later
"""The data/truth.json facts that override a source, by their state in the built data (#670).

    python -I tools/fact_status.py                # the facts to look at, and the counts
    python -I tools/fact_status.py --all          # every fact
    python -I tools/fact_status.py --json reports/fact_status.json

Each build tool that applies such a fact over a source states it in the provenance of the file it writes
(`provenance.facts`, tools/sources.py fact_state). This reads them from every built file in data/ and lists each
fact once, with the lines whose files state it. To look at:
  matches  the source gives the fact's value now: the fact can be retired, deleted from data/truth.json on the
           maintainer's word in a PR that quotes it and names the snapshot that matches (git history keeps it, #670);
  changed  the source gives neither the value recorded with the fact nor the fact's: look at the place again;
  moved    a confirmation (the maintainer said the source was right) the source has since left: the fact holds against it.
The others: holds (a correction still needed) and agrees (a confirmation the source still gives). A fact of a section
in sources.OVERRIDES that no built file states is "not stated": no built line applies it, or its tool does not state
it yet. A stated fact whose id is no longer in data/truth.json is "retired" until the lines are rebuilt.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I leaves it out)
import sources  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOK = ("matches", "changed", "moved")
ORDER = ("changed", "moved", "matches", "holds", "agrees")  # where a fact's files differ, the first of these leads
SKIP = {"truth.json", "MANIFEST.json"}


def built_files(root=ROOT):
    """(name, provenance) of every built JSON file in data/ that states facts."""
    d = os.path.join(root, "data")
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if not name.endswith(".json") or name in SKIP:
            continue
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            js = json.load(fh)
        p = js.get("provenance") if isinstance(js, dict) else None
        if isinstance(p, dict) and p.get("facts"):
            yield name, p


def line_of(name):
    m = re.match(r"line([^.]+)\.", name)
    return m.group(1) if m else name


def collect(root=ROOT, files=None, truth=None):
    """Every fact of sources.OVERRIDES and every stated one: [{section, id, state, lines, states, tool, detail}]."""
    if truth is None:
        with open(os.path.join(root, "data", "truth.json"), encoding="utf-8") as fh:
            truth = json.load(fh)
    stated = {}
    for name, p in (built_files(root) if files is None else files):
        for section, block in p["facts"].items():
            for e in block.get("facts", []):
                k = (section, str(e["id"]))
                s = stated.setdefault(k, {"section": section, "id": str(e["id"]), "tool": block.get("tool"),
                                          "states": {}, "detail": {}})
                s["states"][line_of(name)] = e["state"]
                if not s["detail"] or ORDER.index(e["state"]) < ORDER.index(s["state"]):
                    s["detail"] = {k2: v for k2, v in e.items() if k2 not in ("id", "state")}
                s["state"] = min(s["states"].values(), key=ORDER.index)
    known = set()
    out = []
    for section, (_, _, tool, *_) in sources.OVERRIDES.items():
        for f in sources.overriding(truth, section):
            k = (section, str(sources.fact_id(section, f)))
            known.add(k)
            out.append(stated.get(k) or {"section": section, "id": k[1], "tool": tool, "state": "not stated",
                                         "states": {}, "detail": {}})
    for k, s in stated.items():
        if k not in known:
            out.append(s | {"state": "retired"})
    for s in out:
        s["lines"] = sorted(s.pop("states").items()) if "states" in s else s.get("lines", [])
    return out


def counts(facts):
    c = {}
    for f in facts:
        c[f["state"]] = c.get(f["state"], 0) + 1
    return c


def summary(facts):
    """One line: the count per state."""
    c = counts(facts)
    names = list(sources.FACT_STATES) + ["not stated", "retired"]
    return " · ".join(f"{s} {c[s]}" for s in names if c.get(s))


def describe(f):
    d = f["detail"]
    lines = ", ".join(f"{ln}" + ("" if st == f["state"] else f" ({st})") for ln, st in f["lines"])
    parts = [f"{f['section']} {f['id']}"]
    if lines:
        parts.append(f"lines {lines}")
    if d:
        parts.append(", ".join(f"{k} {v}" for k, v in d.items()))
    return ": ".join(parts[:1]) + (" (" + "; ".join(parts[1:]) + ")" if parts[1:] else "")


HEAD = {
    "matches": "matches: the source gives the fact's value now (retire it: delete it from truth.json on the user's word)",
    "changed": "changed: the source gives neither the recorded value nor the fact's (look at the place again)",
    "moved": "moved: a confirmation the source has left (the fact holds against it)",
    "retired": "retired: stated by the built data, no longer in truth.json (rebuild the lines)",
    "holds": "holds: still needed",
    "agrees": "agrees: a confirmation the source still gives",
    "not stated": "not stated: no built line applies it, or its tool does not state it yet",
}


def report(facts, everything=False):
    out = ["facts that override a source: " + (summary(facts) or "none")]
    for state in LOOK + ("retired",) + (("holds", "agrees", "not stated") if everything else ()):
        fs = [f for f in facts if f["state"] == state]
        if fs:
            out += ["", HEAD[state] + ":"] + [f"  {describe(f)}" for f in fs]
    return "\n".join(out)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="every fact, not only those to look at")
    ap.add_argument("--json", help="write the facts to this file too")
    a = ap.parse_args()
    facts = collect()
    print(report(facts, a.all))
    if a.json:
        with open(a.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"counts": counts(facts), "facts": facts}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
