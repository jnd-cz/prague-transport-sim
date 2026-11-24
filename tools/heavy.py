#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heavy jobs take turns (#280, #536): a command, or a tool run alone, waits for the machine's other heavy jobs
(baseline_store.HeavyJob, first come first served) and holds its turn while it runs.

    python -I tools/heavy.py "profile line_heights" -- python -P -E profile.py ...   # any command, in its turn
    python -I tools/heavy.py "#516 options" -- bash job.sh
    python -I tools/heavy.py --shared 4,2 "#707 pictures" -- bash shots.sh   # beside other counts and builds (#728)
    python -I tools/heavy.py --expect 20m "#812 trace" -- python -P -E trace.py   # its expected time (#815)
    python -I tools/heavy.py --day --expect 2h "#800 places" -- bash all.sh   # long, by day, on the user's word (#851)
    python -I tools/heavy.py --stop PID      # asks a job of this checkout to end, with all it started
    python -I tools/heavy.py --history       # the finished jobs' times per kind: the time rule's calibration

A timing needs the machine to itself: the plain form, which waits for every other job and holds them. --shared GB,CORES
is for a command whose result does not depend on what runs beside it (pictures, counts, a build): its peak memory and
the cores it keeps busy, by which it runs beside the other shared jobs while they fit (HeavyJob has the rule).
What the command starts (rebuild.py, headless.py, a heavy step) runs in its turn and does not wait again. On Windows a
plain `bash` or `sh` runs Git Bash's, next to git (Windows finds WSL's bash.exe in System32 before it reads PATH, #645).
A tool that is a heavy job when run alone calls turn(what) at its start (DEVELOPING.md, Heavy jobs, lists them). tools/board.py shows the
queue; TRAM_HEAVY_NOWAIT=1 runs a job at once beside the others (it slows both).

The job watches itself (#815, HeavyJob.verdict has the rules): past 2× its expected time it warns; over its --shared
memory it warns at 1.25× and ends at 2×; with its processes idle for 10 min, or the process that started it gone, it
ends. Ending stops the command with everything it started (on Windows a Job Object: stopping heavy.py stops them too)
and exits 86 with one line saying why. --expect DURATION (90s, 20m, 1.5h; plain: minutes) gives its time; without it
the median of the same command's last runs. --no-limit keeps the warnings and ends nothing, for a run the user lets go
on. --stop PID ends a job that lost its owner (a stopped background task whose command outlived it); a job of another
checkout only with --force.

By day (07:00-23:00) a job expected over 30 min, or whose time is not known, waits for the night (#851; the user,
2026-11-24): it stands ahead of no other job meanwhile, and the board shows it held. --day (or TRAM_HEAVY_DAY=1 for a
tool that takes its own turn) runs it by day, on the user's word only. A waiting job of 10 min or less goes before
longer ones queued earlier, but not before one that has waited 2 h.
"""
import atexit
import os
import shutil
import statistics
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
SHELLS = ("bash", "sh")  # (a command's program by these plain names runs Git Bash's on Windows)
HELD = "TRAM_HEAVY_HELD"  # (baseline_store.HELD: set for a heavy job's children, the pid whose turn they run in)


def held():
    """Whether this process runs in another heavy job's turn: a step of rebuild.py, a command of this tool."""
    v = os.environ.get(HELD, "")
    return v.isdigit() and int(v) != os.getpid()


def turn(what, share=None, expect=None):
    """This process's turn among the heavy jobs, held until it exits: for a tool that is a heavy job when run alone
    (share: HeavyJob's, for one that may run beside others; expect: its expected seconds, else the history's). In
    another job's turn it does nothing: no ticket, and baseline_store is not imported (a build step's key holds the
    modules it imports, tools/stepcache.py; the queue's code is not what the step builds from)."""
    if held():
        return None
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    from baseline_store import HeavyJob
    job = HeavyJob(what, share=share, expect=expect)
    job.__enter__()
    atexit.register(job.__exit__)
    return job


def git_shell(name, git=None):
    """Git for Windows' `bash` or `sh`, found from git (git.exe lies in <Git>/cmd, <Git>/bin, <Git>/mingw64/bin or
    <Git>/ucrt64/bin); None without one. <Git>/bin/<name>.exe first: it puts Git's tools (sed, uname …) on PATH before it
    starts <Git>/usr/bin/<name>.exe, which run alone from PowerShell finds none of them."""
    git = git or shutil.which("git")
    if not git:
        return None
    d = os.path.dirname(os.path.abspath(git))
    for _ in range(3):
        for sub in ("bin", os.path.join("usr", "bin")):
            exe = os.path.join(d, sub, f"{name}.exe")
            if os.path.isfile(exe):
                return exe
        d = os.path.dirname(d)
    return None


def program(cmd, windows=os.name == "nt", git=None):
    """The command to run: on Windows a plain `bash` or `sh` (no directory) is Git Bash's. CreateProcess looks in
    System32 before PATH, so it would start WSL's bash.exe, which fails without a distribution (#645). Any other
    program, or a path, runs as given."""
    if not windows or not cmd or os.path.dirname(cmd[0]):
        return cmd
    name = cmd[0].lower()
    name = name[:-4] if name.endswith(".exe") else name
    exe = git_shell(name, git) if name in SHELLS else None
    return [exe, *cmd[1:]] if exe else cmd


def shared(text):
    """--shared's "GB,CORES" as HeavyJob's share; None when it is not two numbers."""
    try:
        gb, cores = text.split(",")
        return {"gb": float(gb), "cores": int(cores)}
    except ValueError:
        return None


def options(argv, seconds):
    """(--shared, --expect, --no-limit and --day before the job's name as HeavyJob's share, expect, limits and day; the
    rest), or (None, the rest) when one of them is wrong."""
    o = {"share": None, "expect": None, "limits": None, "day": None}
    while argv and argv[0].startswith("--") and argv[0] != "--":
        if argv[0] == "--no-limit":
            o["limits"], argv = False, argv[1:]
        elif argv[0] == "--day":
            o["day"], argv = True, argv[1:]
        elif argv[0] in ("--shared", "--expect") and len(argv) > 1:
            name, v = ("share", shared(argv[1])) if argv[0] == "--shared" else ("expect", seconds(argv[1]))
            if v is None:
                return None, argv
            o[name], argv = v, argv[2:]
        else:
            return None, argv
    return o, argv


def stop(pid, force=False, out=sys.stderr, wait=15.0):
    """Asks the job of that pid to end with everything it started (HeavyJob reads the request in its watch): one of
    this checkout's, another's only with force. 0 once it has ended, 1 when it is not there, refused or still runs."""
    import baseline_store as b
    jobs = {j["pid"]: j for j in b.queue()}
    j = jobs.get(pid)
    if j is None:
        print(f"heavy.py: no heavy job has pid {pid} ({len(jobs)} in the queue: python -I tools/board.py)", file=out)
        return 1
    if os.path.normcase(os.path.normpath(j["root"])) != os.path.normcase(os.path.normpath(ROOT)) and not force:
        print(f"heavy.py: {b.describe(j)} is another checkout's job; --force asks it to end all the same", file=out)
        return 1
    if "stops" not in j:
        print(f"heavy.py: {b.describe(j)} does not watch itself (its checkout is from before #815): end process {pid} "
              f"and what it started by hand", file=out)
        return 1
    os.makedirs(b.LOCKS, exist_ok=True)
    with open(os.path.join(b.LOCKS, f"{pid}.stop"), "w", encoding="utf-8") as f:
        f.write(f"{os.getpid()} {time.time():.0f}\n")
    end = time.time() + wait
    while b.alive(pid) and time.time() < end:
        time.sleep(0.25)
    if b.alive(pid):
        print(f"heavy.py: {b.describe(j)} was asked to end and still runs after {wait:.0f} s", file=out)
        return 1
    print(f"heavy.py: {b.describe(j)} ended on request", file=out)
    return 0


def show_history(out=sys.stdout):
    """The finished jobs that ran to their end, per kind: how many, their median time and the spread the time rule
    must allow (HeavyJob.LATE); then the jobs a watch ended."""
    import baseline_store as b
    rs = b.history()
    by = {}
    for r in rs:
        if r.get("wall", 0) >= 60 and r.get("rc") in (0, None) and not r.get("ended"):
            by.setdefault(r["kind"], []).append(r)
    print("kind | runs | median min | longest / median | most GB", file=out)
    for k, v in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        w = [r["wall"] for r in v]
        m = statistics.median(w)
        print(f"{k} | {len(w)} | {m / 60:.1f} | {max(w) / m:.1f} | {max(r.get('gb') or 0 for r in v):.1f}", file=out)
    for r in rs:
        if r.get("ended"):
            print(f"ended: {r['what']} ({r['kind']}) at {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['t'] + r['wall']))}"
                  f" after {r['wall'] / 60:.0f} min: {r['ended']}", file=out)
    return 0


def main(argv):
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    import baseline_store as b
    if argv == ["--history"]:
        return show_history()
    if argv[:1] == ["--stop"]:
        ids = [a for a in argv[1:] if a != "--force"]
        if len(ids) == 1 and ids[0].isdigit():
            return stop(int(ids[0]), force="--force" in argv)
        argv = []
    o, argv = options(argv, b.seconds)
    if o is None or len(argv) < 3 or argv[1] != "--":
        print(__doc__.split("\n\n")[1].rstrip(), file=sys.stderr)
        return 2
    what, cmd = argv[0], program(argv[2:])
    with b.HeavyJob(what, share=o["share"], expect=o["expect"], kind=b.kind_of(cmd), limits=o["limits"], day=o["day"]) as job:
        t = time.time()
        print(f"heavy.py: {what} starts {time.strftime('%H:%M:%S')}", file=sys.stderr, flush=True)
        rc = subprocess.call(cmd)
        job.rc = rc
        print(f"heavy.py: {what} done in {time.time() - t:.0f} s, exit {rc}", file=sys.stderr, flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
