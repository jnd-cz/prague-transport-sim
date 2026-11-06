"""The validation report of a build (#23): data/lineN.validate.json (tools/osm_validate.py) against limits.

    python -I tools/validation.py 9 17 22 23 37      # prints the table, writes reports/rebuild/validation.md

tools/rebuild.py runs it after the lines it built. A count over its limit is reported, not fatal: most of them
are placement rules still to be moved into the build (#22). The limits are measured, on the five lines of 2026-11-06
(main 8f9e4c3), so a rebuild that makes one worse stands out:

| check | 9 | 17 | 22 | 23 | 37 |
|---|---|---|---|---|---|
| fit: median, m | 0.0 | 0.2 | 0.0 | 0.0 | 0.0 |
| fit: 90th percentile, m | 3.16 | 4.51 | 4.28 | 3.55 | 5.0 |
| stops over 10 m from OSM, or not in it | 5/60 | 4/37 | 3/39 | 2/18 | 0/20 |
| crossings without an OSM crossing | 106/250 | 63/137 | 83/183 | 38/88 | 32/73 |
| tram signals along a platform | 7 | 8 | 2 | 0 | 9 |
| crossings inside a platform | 7 | 4 | 8 | 3 | 0 |
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOP_FAR = 10.0  # m: (osm_validate.py's list of the stops far from OSM)
# (name, what it measures, limit; shares in %). The fit's 90th percentile counts OSM's points of other tracks within 12 m
LIMITS = {"fitMedian": ("fit: median, m", 0.5), "fitP90": ("fit: 90th percentile, m", 6.0),
          "stopsFar": ("stops over 10 m from OSM or not in it, %", 15.0),
          "crossingsLone": ("crossings without an OSM crossing, %", 50.0),
          "signalsOnPlatforms": ("tram signals along a platform", 10),
          "crossingsInPlatforms": ("crossings inside a platform", 10),
          "platformOverlaps": ("platforms overlapping on the route", 0)}


def measures(r):
    """{check: value} of one line's validate.json; a value is None where the build has nothing to count."""
    stops = r.get("stops", [])
    far = [s for s in stops if s.get("osm", 1) is None or abs(s.get("diff", 0)) > STOP_FAR]
    crossings = r.get("crossings")
    lone = r.get("crossingsWithoutOsm", [])
    return {"fitMedian": r.get("fit", {}).get("median"), "fitP90": r.get("fit", {}).get("p90"),
            "stopsFar": round(100 * len(far) / len(stops), 1) if stops else None,
            "crossingsLone": round(100 * len(lone) / crossings, 1) if crossings else None,
            "signalsOnPlatforms": len(r.get("signalsOnPlatforms", [])),
            "crossingsInPlatforms": len(r.get("crossingsInPlatforms", [])),
            "platformOverlaps": len(r.get("platformOverlaps", []))}


def over(m):
    """The checks over their limit, or with no value where a line must have one (no OSM track near ours)."""
    return [k for k, (_, limit) in LIMITS.items() if m.get(k) is None or m[k] > limit]


def table(reports):
    """{line: validate.json} -> (markdown lines, {line: checks over}). A missing file is a line of its own."""
    lines = sorted(reports, key=int)
    rows = ["| check | limit | " + " | ".join(lines) + " |", "|---|---|" + "---|" * len(lines)]
    ms = {ln: measures(reports[ln]) for ln in lines}
    bad = {ln: over(ms[ln]) for ln in lines}
    for k, (name, limit) in LIMITS.items():
        cells = [("—" if ms[ln][k] is None else str(ms[ln][k])) + (" **over**" if k in bad[ln] else "") for ln in lines]
        rows.append(f"| {name} | {limit} | " + " | ".join(cells) + " |")
    return rows, bad


def report(lines, root=ROOT):
    have, missing = {}, []
    for ln in lines:
        p = os.path.join(root, "data", f"line{ln}.validate.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                have[ln] = json.load(f)
        else:
            missing.append(ln)
    rows, bad = table(have) if have else ([], {})
    if missing:
        rows.append(f"\nNo report: line {', '.join(missing)} (tools/osm_validate.py did not run).")
    return rows, bad, missing


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    lines = sys.argv[1:] or ["9", "17", "22", "23", "37"]
    rows, bad, missing = report(lines)
    text = "\n".join(rows)
    print(text)
    os.makedirs(os.path.join(ROOT, "reports", "rebuild"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "rebuild", "validation.md"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    worse = {ln: b for ln, b in bad.items() if b}
    print("validation: " + ("every line within its limits" if not worse and not missing else f"over a limit: {worse or 'none'}; no report: {missing or 'none'}"))


if __name__ == "__main__":
    main()
