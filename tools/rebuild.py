"""Rebuild lines from the snapshot: every build step, one log per step.

    python -P -E tools/rebuild.py 17 22         # lines (default: all)
    python -P -E tools/rebuild.py --parallel     # also the lines side by side

build_line first; then, side by side (each step reads only build_line's output, and only the first
group writes data/lineN.json, each writer whole and renamed):
  platforms → osm_speeds → clearances (→ for line 17: OSM signals, survey points, OSM validation)
  geoportal
  fine_terrain
  dtm → zps_source (lines with surveyed streets, not those in dtm_packages.HOLD: the areas, then
    the source lines for review mode)
Logs: reports/rebuild/lineN.<step>.log, summary in lineN.log. After it: python -I tools/snapshot.py data-publish.
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from dtm_packages import DTM, HOLD, select_packages  # noqa: E402

PY = [sys.executable, "-P", "-E"]
BUILD = {"9": ["--line", "9", "--then", "10"], "22": ["--line", "22", "--headsign", "Zahradní Město"]}


def steps(line):
    """build_line, then the groups that run side by side (each group's steps in order)."""
    first = ["build_line.py", *BUILD.get(line, ["--line", line])]
    writers = [["platforms.py", "--line", line], ["osm_speeds.py", "--line", line], ["clearances.py", "--line", line]]
    if line == "17":
        writers += [["osm_signals.py", line], ["dtm_points.py", line], ["osm_validate.py", line]]
    groups = [writers, [["geoportal.py", "--line", line]], [["fine_terrain.py", "--line", line]]]
    if line in HOLD:
        print(f"line {line}: survey held, not built ({HOLD[line]}; tools/dtm_packages.py HOLD)", flush=True)
    elif line in DTM:
        opl = [str(p.opl) for p in select_packages(ROOT, districts=DTM[line])]
        groups.append([["dtm.py", "--line", line, *opl], ["zps_source.py", "--line", line]])
    return first, groups


def run_steps(line, sts):
    """Steps in order, each with its own log; (failed step or None, seconds per step)."""
    times = []
    for st in sts:
        log = os.path.join(ROOT, "reports", "rebuild", f"line{line}.{st[0][:-3]}.log")
        t = time.time()
        with open(log, "w", encoding="utf-8") as f:
            r = subprocess.run([*PY, os.path.join(ROOT, "tools", st[0]), *st[1:]], cwd=ROOT, stdout=f,
                               stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        times.append((st[0], round(time.time() - t), r.returncode))
        if r.returncode:
            return st[0], times
    return None, times


def rebuild(line):
    os.makedirs(os.path.join(ROOT, "reports", "rebuild"), exist_ok=True)
    t0 = time.time()
    first, groups = steps(line)
    fail, times = run_steps(line, [first])
    if not fail:
        with ThreadPoolExecutor(len(groups)) as ex:  # (threads only wait on the step processes)
            for f, ts in ex.map(lambda g: run_steps(line, g), groups):
                times += ts
                fail = fail or f
    with open(os.path.join(ROOT, "reports", "rebuild", f"line{line}.log"), "w", encoding="utf-8") as f:
        for name, secs, code in times:
            f.write(f"{name:18s} {secs:5d} s  exit {code}\n")
        f.write(f"wall clock {time.time() - t0:.0f} s\n")
    if fail:
        return f"line {line}: FAILED at {fail}, see reports/rebuild/line{line}.{fail[:-3]}.log"
    return f"line {line}: done in {(time.time() - t0) / 60:.1f} min"


def main():
    # (any other flag, --help too, used to fall through to a rebuild of every line)
    flags = [a for a in sys.argv[1:] if a.startswith("-") and a != "--parallel"]
    if flags:
        sys.stdout.reconfigure(encoding="utf-8")  # (the docstring's arrows on a cp1252 console)
        print(__doc__)
        sys.exit(0 if flags in (["-h"], ["--help"]) else 2)
    lines = [a for a in sys.argv[1:] if not a.startswith("--")] or ["9", "17", "22", "23", "37"]
    if "--parallel" in sys.argv:
        # (lines side by side, as many as free memory holds: a line's build with its parallel steps
        # takes ~2.5 GB at its peak: build_line 1.3 GB, then its steps side by side)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sysinfo import workers
        with ThreadPoolExecutor(min(len(lines), workers(2.5, most=len(lines)))) as ex:
            results = list(ex.map(rebuild, lines))
    else:
        results = [rebuild(line) for line in lines]
    print("\n".join(results))
    sys.exit(1 if any("FAILED" in r for r in results) else 0)


if __name__ == "__main__":
    from baseline_store import HeavyJob
    with HeavyJob("rebuild"):  # (the nightly baseline waits while this runs)
        main()
