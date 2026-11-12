# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rebuild lines from the snapshot: every build step, one log per step.

    python -P -E tools/rebuild.py 17 22         # lines (default: all)
    python -P -E tools/rebuild.py --parallel     # also the lines side by side
    python -P -E tools/rebuild.py 9 --from build_line   # that step runs again (track = build_line, heights =
                                                        # line_heights), the others as their inputs say
    python -P -E tools/rebuild.py --force        # every step runs

build_line first; then, side by side (each step reads only build_line's output, and only the first
group writes data/lineN.json, each writer whole and renamed):
  platforms → osm_speeds → cant → clearances → survey points (→ for line 17: OSM signals) → the OSM validation
  geoportal
  fine_terrain
  dtm → zps_source (lines with surveyed streets, not those in dtm_packages.HOLD: the areas, then
    the source lines for review mode)
then track_styles (the user's marks, the grassed-track list and the survey's grass track with their holes, and the
rails' height over the bed, #479, #503, #480: it reads the survey's areas and writes data/lineN.json), then line_heights
once for all the lines rebuilt (the top of rail, #197: the network's profile reads every line's survey sidecar and the
lines' lift, so it runs after them all), then line_structures per line (the spans, decks and underpasses: they read the
built top of rail, #480), then the validation report (tools/validation.py, #23).

A step whose tool, the modules it imports and the files it read hash as in one of its recorded runs is skipped, and
its outputs and log are put back as that run left them (tools/stepcache.py, #511): a rebuild after a change to one
rule runs the steps that read what changed. The steps side by side are keyed with data/lineN.json as build_line
left it (what they read of it; the writers rewrite it meanwhile).
Logs: reports/rebuild/lineN.<step>.log, summary in lineN.log (each step's seconds, or "skip", and why it ran),
reports/rebuild/heights.log, validation.md. After it: python -I tools/snapshot.py data-publish.
"""
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from dtm_packages import DTM, HOLD, select_packages  # noqa: E402
import stepcache  # noqa: E402

PY = [sys.executable, "-P", "-E"]
BUILD = {"9": ["--line", "9", "--then", "10"], "22": ["--line", "22", "--headsign", "Zahradní Město"]}
ALIAS = {"track": "build_line", "heights": "line_heights", "structures": "line_structures"}
CACHE = None  # (stepcache.Cache of ROOT, made by main)
FORCE = set()  # steps that run whatever their records say ("*": all)
CPU = []  # (the CPU seconds of each step run)
# numpy's BLAS threads per step: by default one per core in every process, and with the steps and lines side by side
# hundreds of them fought for 24 cores (an ADMM-sized inverse and 300 products, n 1200: 5.1 s against 0.08 s with 4
# threads, #511). A line's steps run four at a time (and lines side by side), the heights alone. The same numbers
# whatever runs beside them: they enter the results' last bits, so the steps' keys (tools/stepcache.py ENV). An
# OPENBLAS_NUM_THREADS of the caller's own is kept.
BLAS = {"line": "1", "heights": "4"}


def step_env(phase):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if "OPENBLAS_NUM_THREADS" not in os.environ:
        env["OPENBLAS_NUM_THREADS"] = BLAS[phase]
    return env


def writers(line):
    """The steps that read build_line's output and write beside it, in order."""
    out = [["platforms.py", "--line", line], ["osm_speeds.py", "--line", line], ["cant.py", "--line", line], ["clearances.py", "--line", line],
           ["dtm_points.py", line]]
    # (the user, 2026-11-06, #348: "should solve their placement before we populate them elsewhere", #22)
    if line == "17":
        out.append(["osm_signals.py", line])
    # (placement last: it reads the platforms and OSM's signals, and the validation counts OSM's signals as found, #22)
    return out + [["osm_validate.py", line], ["placement.py", "--line", line]]


def steps(line):
    """build_line, then the groups that run side by side (each group's steps in order)."""
    first = ["build_line.py", *BUILD.get(line, ["--line", line])]
    groups = [writers(line), [["geoportal.py", "--line", line]], [["fine_terrain.py", "--line", line]]]
    if line in HOLD:
        print(f"line {line}: survey held, not built ({HOLD[line]}; tools/dtm_packages.py HOLD)", flush=True)
    elif line in DTM:
        opl = [str(p.opl) for p in select_packages(ROOT, districts=DTM[line])]
        groups.append([["dtm.py", "--line", line, *opl], ["zps_source.py", "--line", line]])
    return first, groups


def names():
    """Every step's name (for --from)."""
    out = {"build_line", "geoportal", "fine_terrain", "dtm", "zps_source", "track_styles", "line_heights", "line_structures"}
    return out | {st[0][:-3] for st in writers("17")}


def run_step(label, st, log, phase0=None, phase="line"):
    """One step, or its outputs put back when a record of it holds: (name, seconds, exit code or "skip", why, key,
    record, ran)."""
    key, t, env = CACHE.name(label, st[0], st[1:]), time.time(), step_env(phase)
    name = st[0][:-3]
    rec, why = (None, "--force" if "*" in FORCE else "--from") if FORCE & {"*", name} else CACHE.match(key, phase0, env)
    if rec:
        CACHE.restore(rec, stepcache.relpath(ROOT, log))
        return st[0], round(time.time() - t), "skip", f"as run {rec['when']}, {rec['secs']:.0f} s", key, rec, False
    tmp = CACHE.tmp_record(key)
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(CACHE.command(PY, st[0], st[1:], tmp), cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, env=env)
    rec = CACHE.save(key, tmp, log) if r.returncode == 0 else None
    if rec:
        CPU.append(rec.get("cpu", 0))
    return st[0], round(time.time() - t), r.returncode, why, key, rec, True


def run_steps(line, sts, phase0=None):
    """Steps in order, each with its own log; (failed step or None, run_step's results)."""
    times = []
    for st in sts:
        log = os.path.join(ROOT, "reports", "rebuild", f"line{line}.{st[0][:-3]}.log")
        times.append(run_step(f"line{line}", st, log, phase0))
        if times[-1][2] not in (0, "skip"):
            return st[0], times
    return None, times


def side_by_side(line, groups, first):
    """The groups side by side. A file one group rewrites while another reads it (data/lineN.json) enters the
    reader's key as it was before the groups started: phase0, those files' states then."""
    paths = set(first[5]["outputs"] if first[5] else ())
    for g in groups:
        for st in g:
            recs = CACHE.records(CACHE.name(f"line{line}", st[0], st[1:]))
            paths.update(recs[0]["outputs"] if recs else ())
    phase0 = {r: CACHE.hashes.state(r) for r in paths}
    with ThreadPoolExecutor(len(groups)) as ex:  # (threads only wait on the step processes)
        res = list(ex.map(lambda g: run_steps(line, g, phase0), groups))
    owner = {}
    for gi, (_, ts) in enumerate(res):
        for t in ts:
            for r in (t[5]["outputs"] if t[5] else ()):
                owner.setdefault(r, set()).add(gi)
    for gi, (_, ts) in enumerate(res):
        for t in ts:
            rec = t[5]
            if not (t[6] and rec):
                continue
            moved = [r for r in rec["inputs"] if r in phase0 and owner.get(r, set()) - {gi}]
            if moved:
                for r in moved:
                    rec["inputs"][r] = phase0[r]
                rec["phase"] = moved
                CACHE.amend(t[4], rec)
    return res


def rebuild(line):
    os.makedirs(os.path.join(ROOT, "reports", "rebuild"), exist_ok=True)
    t0 = time.time()
    first, groups = steps(line)
    fail, times = run_steps(line, [first])
    if not fail:
        for f, ts in side_by_side(line, groups, times[0]):
            times += ts
            fail = fail or f
    if not fail:   # (the track styles read the survey's areas, and the heights read the styles: #479)
        fail, ts = run_steps(line, [["track_styles.py", "--line", line]])
        times += ts
    with open(os.path.join(ROOT, "reports", "rebuild", f"line{line}.log"), "w", encoding="utf-8") as f:
        f.write(summary(times))
        cpu = sum(t[5].get("cpu", 0) for t in times if t[6] and t[5])
        f.write(f"wall clock {time.time() - t0:.0f} s, cpu {cpu:.0f} s\n")
    ran = [t[0][:-3] for t in times if t[6]]
    if fail:
        return f"line {line}: FAILED at {fail}, see reports/rebuild/line{line}.{fail[:-3]}.log"
    return f"line {line}: done in {(time.time() - t0) / 60:.1f} min, {ran_text(ran, len(times))}"


def summary(times):
    """A line per step: its seconds, the CPU seconds of its process when it ran (all its threads: CPU over seconds is the
    cores it kept busy), and why it ran or what it was skipped for."""
    out = []
    for name, secs, code, why, _, rec, _ in times:
        cpu = f"cpu {rec.get('cpu', 0):5.0f} s  " if code != "skip" and rec else ""
        out.append(f"{name:18s} {secs:5d} s  {cpu}{'skip  ' if code == 'skip' else f'exit {code}'}  ({why})\n")
    return "".join(out)


def ran_text(ran, n):
    return f"ran {', '.join(ran)}" + (f"; {n - len(ran)} skipped" if len(ran) < n else "") if ran else f"all {n} steps skipped"


def heights(lines):
    """The top of rail of the lines rebuilt (tools/line_heights.py), after all their steps."""
    t = time.time()
    log = os.path.join(ROOT, "reports", "rebuild", "heights.log")
    times = [run_step("heights", ["line_heights.py", *lines], log, phase="heights")]
    if times[0][2] != "skip" and times[0][2]:
        return f"heights of {', '.join(lines)}: FAILED, see reports/rebuild/heights.log"
    # (the spans, decks and underpasses read the built top of rail: tools/line_structures.py, #480)
    for line in lines:
        log = os.path.join(ROOT, "reports", "rebuild", f"line{line}.line_structures.log")
        times.append(run_step(f"line{line}", ["line_structures.py", "--line", line], log, phase="heights"))
        if times[-1][2] not in (0, "skip"):
            return f"structures of line {line}: FAILED, see reports/rebuild/line{line}.line_structures.log"
    with open(os.path.join(ROOT, "reports", "rebuild", "heights.summary.log"), "w", encoding="utf-8") as f:
        f.write(summary(times))
    ran = [t[0][:-3] for t in times if t[6]]
    return f"heights and structures of {', '.join(lines)}: done in {(time.time() - t) / 60:.1f} min, {ran_text(ran, len(times))}"


def args(argv):
    """(lines, --parallel, the steps forced) from the command line; None when it does not parse."""
    lines, par, force, it = [], False, set(), iter(argv)
    for a in it:
        if a == "--parallel":
            par = True
        elif a == "--force":
            force.add("*")
        elif a == "--from":
            s = next(it, None)
            s = ALIAS.get(s, s)
            if s not in names():
                print(f"--from: no step {s!r}; the steps: {', '.join(sorted(names()))} (or {', '.join(ALIAS)})")
                return None
            force.add(s)
        elif a.startswith("-"):
            return None
        else:
            lines.append(a)
    return lines or ["9", "17", "22", "23", "37"], par, force


def main():
    global CACHE
    got = args(sys.argv[1:])
    if got is None:  # (any other flag, --help too, used to fall through to a rebuild of every line)
        sys.stdout.reconfigure(encoding="utf-8")  # (the docstring's arrows on a cp1252 console)
        print(__doc__)
        sys.exit(0 if sys.argv[1:] in (["-h"], ["--help"]) else 2)
    lines, par, force = got
    FORCE.update(force)
    CACHE = stepcache.Cache(ROOT)
    t0 = time.time()
    if par:
        # (lines side by side, as many as free memory holds: a line's build with its parallel steps
        # takes ~2.5 GB at its peak: build_line 1.3 GB, then its steps side by side)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from sysinfo import workers
        with ThreadPoolExecutor(min(len(lines), workers(2.5, most=len(lines)))) as ex:
            results = list(ex.map(rebuild, lines))
    else:
        results = [rebuild(line) for line in lines]
    built = [line for line, r in zip(lines, results) if "FAILED" not in r]
    if built:
        results.append(heights(built))
    CACHE.hashes.save()
    n, size = CACHE.prune()
    print("\n".join(results))
    wall = time.time() - t0
    print(f"total {wall:.0f} s, the steps' cpu {sum(CPU):.0f} s ({sum(CPU) / wall:.1f} cores busy on average)" + (f"; store: {n} files no record names removed ({size / 1e6:.0f} MB)" if n else ""))
    if built:  # (the report does not fail a build: most of what it counts waits for #22)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import validation
        validation.write_report(built)
    sys.exit(1 if any("FAILED" in r for r in results) else 0)


if __name__ == "__main__":
    if args(sys.argv[1:]) is None:
        main()  # (prints the usage and exits: no turn in the queue for that)
    from baseline_store import HeavyJob
    from board import check_rebuild_label
    check_rebuild_label("rebuild", warn_only=True)  # (a local rebuild is fine; its publish needs the label, #280)
    with HeavyJob("rebuild"):  # (waits its turn among the heavy jobs, and the nightly baseline for it)
        main()
