#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Heavy jobs take turns (#280, #536): a command, or a tool run alone, waits for the machine's other heavy jobs
(baseline_store.HeavyJob, first come first served) and holds its turn while it runs.

    python -I tools/heavy.py "profile line_heights" -- python -P -E profile.py ...   # any command, in its turn
    python -I tools/heavy.py "#516 options" -- bash job.sh

What the command starts (rebuild.py, headless.py, a heavy step) runs in its turn and does not wait again. On Windows a
plain `bash` or `sh` runs Git Bash's, next to git (Windows finds WSL's bash.exe in System32 before it reads PATH, #645).
A tool that is a heavy job when run alone calls turn(what) at its start (AGENTS.md lists them). tools/board.py shows the
queue; TRAM_HEAVY_NOWAIT=1 runs a job at once beside the others (it slows both).
"""
import atexit
import os
import shutil
import subprocess
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
SHELLS = ("bash", "sh")  # (a command's program by these plain names runs Git Bash's on Windows)
HELD = "TRAM_HEAVY_HELD"  # (baseline_store.HELD: set for a heavy job's children, the pid whose turn they run in)


def held():
    """Whether this process runs in another heavy job's turn: a step of rebuild.py, a command of this tool."""
    v = os.environ.get(HELD, "")
    return v.isdigit() and int(v) != os.getpid()


def turn(what):
    """This process's turn among the heavy jobs, held until it exits: for a tool that is a heavy job when run alone. In
    another job's turn it does nothing: no ticket, and baseline_store is not imported (a build step's key holds the
    modules it imports, tools/stepcache.py; the queue's code is not what the step builds from)."""
    if held():
        return None
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    from baseline_store import HeavyJob
    job = HeavyJob(what)
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


def main(argv):
    if len(argv) < 3 or argv[1] != "--":
        print(__doc__.split("\n\n")[1].rstrip(), file=sys.stderr)
        return 2
    what, cmd = argv[0], program(argv[2:])
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    from baseline_store import HeavyJob
    with HeavyJob(what):
        t = time.time()
        print(f"heavy.py: {what} starts {time.strftime('%H:%M:%S')}", file=sys.stderr, flush=True)
        rc = subprocess.call(cmd)
        print(f"heavy.py: {what} done in {time.time() - t:.0f} s, exit {rc}", file=sys.stderr, flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
