"""Rebuild lines from the snapshot: every build step in order, one log per line.

    python -P -E tools/rebuild.py 17 22         # lines (default: all)
    python -P -E tools/rebuild.py --parallel     # lines side by side (steps of a line stay in order)

Steps: build_line → platforms → osm_speeds → clearances → geoportal → fine_terrain, then where the
line has surveyed streets dtm → streets, and the line-17 extras (OSM signals, survey points, OSM
validation report). Logs: reports/rebuild/lineN.log. After it: python -I tools/snapshot.py data-publish.
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = [sys.executable, "-P", "-E"]
DTM = {  # district packages (Prague DTM ZPS) with the line's surveyed streets
    "17": ["500054", "500089", "500119", "500186", "500208", "547107", "547174"],
    "22": ["500089", "500224"],
}
BUILD = {"9": ["--line", "9", "--then", "10"], "22": ["--line", "22", "--headsign", "Zahradní Město"]}


def steps(line):
    out = [["build_line.py", *BUILD.get(line, ["--line", line])],
           ["platforms.py", "--line", line], ["osm_speeds.py", "--line", line], ["clearances.py", "--line", line],
           ["geoportal.py", "--line", line], ["fine_terrain.py", "--line", line]]
    if line in DTM:
        dtm = sorted(os.listdir(os.path.join(ROOT, "raw", "dtm")))
        opl = [os.path.join("raw", "dtm", f) for f in dtm
               if f.endswith("_ZPS_OPL.gpkg") and any(f"_{d}_" in f for d in DTM[line])]
        out += [["dtm.py", "--line", line, *opl], ["streets.py", "--line", line]]
    if line == "17":
        out += [["osm_signals.py", line], ["dtm_points.py", line], ["osm_validate.py", line]]
    return out


def rebuild(line):
    os.makedirs(os.path.join(ROOT, "reports", "rebuild"), exist_ok=True)
    log = os.path.join(ROOT, "reports", "rebuild", f"line{line}.log")
    t0 = time.time()
    with open(log, "w", encoding="utf-8") as f:
        for st in steps(line):
            f.write(f"\n=== {' '.join(st)}\n")
            f.flush()
            t = time.time()
            r = subprocess.run([*PY, os.path.join(ROOT, "tools", st[0]), *st[1:]], cwd=ROOT, stdout=f,
                               stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            f.write(f"=== exit {r.returncode}, {time.time() - t:.0f} s\n")
            f.flush()
            if r.returncode:
                return f"line {line}: FAILED at {st[0]} (exit {r.returncode}), see {os.path.relpath(log, ROOT)}"
    return f"line {line}: done in {(time.time() - t0) / 60:.1f} min"


def main():
    lines = [a for a in sys.argv[1:] if not a.startswith("--")] or ["9", "17", "22", "23", "37"]
    if "--parallel" in sys.argv:
        with ThreadPoolExecutor(len(lines)) as ex:
            results = list(ex.map(rebuild, lines))
    else:
        results = [rebuild(line) for line in lines]
    print("\n".join(results))
    sys.exit(1 if any("FAILED" in r for r in results) else 0)


if __name__ == "__main__":
    main()
