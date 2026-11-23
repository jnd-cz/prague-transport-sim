# SPDX-License-Identifier: AGPL-3.0-or-later
"""Main's regression baseline in the data store, and the machine's heavy-job lock (#157). Stdlib only:
tools/headless.py (--baseline --publish, --compare) and tools/autodeploy.py (the nightly measurement)
use it.

A baseline is named by what its counts depend on (MEASURED: the git trees of the game, the in-page
checks, the data manifest and the user's facts in data/truth.json, which the game reads at run time),
hashed: `baselines/<key>.json` and `<key>.places.json` in the store. A
branch looks up the key of its merge base, so it gets main's numbers for exactly that code and data.

A world checkpoint's run is also stored under its name (`baselines/checkpoint-W1.json`, listed in
`baselines/checkpoints.json`, #282). What a seedless compare measures on demand at a merge base stays in this
machine's folder by the key (`measure_at`, `kept`, `keep`), not in the store: the key's name there means main's
full nightly run, and autodeploy would skip measuring it.

    python -I tools/baseline_store.py checkpoints        # the checkpoints in the store
    python -I tools/baseline_store.py rm-checkpoint NAME # remove one (a test's, or one to measure again)

Heavy jobs (headless.py, rebuild.py, frametime.py) queue for the machine with a ticket in the system temp
folder (`HeavyJob`, #280): a timing runs alone, count runs and builds side by side while their memory and
cores fit (#728); the nightly measurement does not start while any job waits or runs. A job holding its turn
watches itself (#815): far too long, over its memory, idle or orphaned, it ends with the reason, and everything it
started ends with it. Finished jobs go into a history beside the tickets, from which a job's expected time comes.
"""
import ctypes
import hashlib
import json
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# (what the counts depend on: the game, the in-page checks, the data and the facts the game loads besides
# it (truth.json: track styles and rail offsets, #126); not the build tools, whose output the manifest
# covers, nor the harness)
MEASURED = ("src", "index.html", "tools/bench", "tools/lint.js", "tools/traffic_lint.js", "tools/autopilot.js",
            "data/MANIFEST.json", "data/truth.json")
LOCKS = os.path.join(tempfile.gettempdir(), "tram-heavy")


def git(*args, root=ROOT):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, encoding="utf-8")
    return r.stdout.strip() if r.returncode == 0 else None


def trees(rev, root=ROOT):
    """The git objects the checks depend on, at a commit."""
    return {p: git("rev-parse", f"{rev}:{p}", root=root) for p in MEASURED}


def dirty(root=ROOT):
    """Uncommitted changes to what a baseline is measured on ('' when none)."""
    return git("status", "--porcelain", "--", *MEASURED, root=root)


def key(t):
    return hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()


def _store():
    from snapshot import Store
    return Store(os.environ.get("TRAMDATA_STORE", "tramdata:store"))


def _tmp():
    # (sftp gets paths relative to the checkout: a temp folder on another drive has none)
    return tempfile.mkdtemp(prefix=".baseline-", dir=ROOT)


def _put(files):
    """Upload {name: object} to baselines/; a temporary name, then rename."""
    st, d = _store(), _tmp()
    try:
        cmds = [f'-mkdir "{st.dir}/baselines"']
        for name, obj in files.items():
            p = os.path.join(d, name)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
            r = os.path.relpath(p, ROOT).replace("\\", "/")
            cmds += [f'-rm "{st.dir}/baselines/{name}.part"', f'put "{r}" "{st.dir}/baselines/{name}.part"',
                     f'-rm "{st.dir}/baselines/{name}"', f'rename "{st.dir}/baselines/{name}.part" "{st.dir}/baselines/{name}"']
        st.run(cmds)
    finally:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        os.rmdir(d)


def publish(k, base, places):
    """Upload one baseline (counts and places) under its key."""
    _put({f"{k}.json": base, f"{k}.places.json": places})


def fetch(k):
    """(counts, places) of the published baseline with this key or name, or (None, None)."""
    st, d = _store(), _tmp()
    try:
        names = (f"{k}.json", f"{k}.places.json")
        st.run([f'-get "{st.dir}/baselines/{n}" "{os.path.relpath(os.path.join(d, n), ROOT).replace(chr(92), "/")}"'
                for n in names], check=False)
        out = []
        for n in names:
            p = os.path.join(d, n)
            out.append(json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None)
        return tuple(out)
    finally:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        os.rmdir(d)


def published(k):
    return fetch(k)[0] is not None


WORLD = re.compile(r"W(\d+)$")  # (a world checkpoint; any other name is a test's and is never the latest)
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*$")


def checkpoints():
    """{name: {key, commit, time}} of the checkpoints in the store."""
    return fetch("checkpoints")[0] or {}


def latest_checkpoint(index):
    """The highest world checkpoint's name in an index, or None."""
    return max((n for n in index if WORLD.match(n)), key=lambda n: int(WORLD.match(n)[1]), default=None)


def publish_checkpoint(name, k, base, places, commit):
    """Store a run under the checkpoint's name and list it; `k` is the run's key."""
    if not NAME.match(name):
        raise ValueError(f"not a checkpoint name: {name!r}")
    index = checkpoints()
    index[name] = {"key": k, "commit": commit, "time": time.strftime("%Y-%m-%d %H:%M")}
    _put({f"checkpoint-{name}.json": base, f"checkpoint-{name}.places.json": places, "checkpoints.json": index})


def fetch_checkpoint(name):
    return fetch(f"checkpoint-{name}")


def remove_checkpoint(name):
    index = checkpoints()
    index.pop(name, None)
    st = _store()
    st.run([f'-rm "{st.dir}/baselines/checkpoint-{name}.json"', f'-rm "{st.dir}/baselines/checkpoint-{name}.places.json"'], check=False)
    _put({"checkpoints.json": index})


def _kept_dir():
    cache = os.environ.get("TRAMDATA_CACHE")
    return os.path.join(cache, "baselines") if cache else os.path.join(tempfile.gettempdir(), "tram-baselines")


def kept(k):
    """(counts, places) this machine measured on demand under this key ({}, {} when none)."""
    try:
        with open(os.path.join(_kept_dir(), f"{k}.json"), encoding="utf-8") as f:
            o = json.load(f)
        return o["counts"], o["places"]
    except (OSError, ValueError, KeyError):
        return {}, {}


def keep(k, counts, places):
    """Add runs measured on demand to this machine's folder, for the next branch on the same base."""
    have, where = kept(k)
    have, where = {**have, **counts}, {**where, **places}
    d = _kept_dir()
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f"{k}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"counts": have, "places": where}, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(d, f"{k}.json"))


def measure_at(rev, lines, checks, want, run=subprocess.run, out=None, seeds=None):
    """Main's runs at a commit: a pinned worktree with that commit's code and data, its own headless.py (which takes
    its turn in the heavy-job queue), removed afterwards. Seedless checks without `seeds`; seeded checks with the
    seeds to run (#709). Returns (counts, places) of the runs measured on exactly `want`, the commit's trees."""
    out = out or sys.stderr
    wt = tempfile.mkdtemp(prefix=f"{os.path.basename(ROOT)}-base-{rev[:7]}-", dir=os.path.dirname(ROOT))
    os.rmdir(wt)  # (git worktree add wants to create it)
    py = sys.executable
    try:
        seeded = ["--seeds", ",".join(str(s) for s in seeds)] if seeds else []
        print(f"measuring {','.join(checks)} of lines {','.join(lines)}" + (f", seeds {seeded[1]}," if seeds else "")
              + f" at {rev[:7]} in {wt}", file=out, flush=True)
        run(["git", "worktree", "add", "-q", "--detach", wt, rev], cwd=ROOT, check=True)
        run([py, "-I", "tools/snapshot.py", "data-fetch"], cwd=wt, check=True)
        # (exit 1 only says a check is over its threshold: the counts are stored all the same)
        run([py, "-P", "-E", "tools/headless.py", "--lines", ",".join(lines), "--checks", ",".join(checks),
             *seeded, "--baseline", "--port", "0"], cwd=wt)
        counts, places = {}, {}
        for name, to in (("headless.json", counts), ("headless-places.json", places)):
            p = os.path.join(wt, "reports", "baseline", name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    to.update(json.load(f))
        wanted = {f"line{line}-{c}" + (f"-seed{s}" if seeds else "") for line in lines for c in checks for s in (seeds or [0])}
        counts = {j: v for j, v in counts.items() if j in wanted and v.get("measured_on") == want}
        return counts, {j: v for j, v in places.items() if j in counts}
    finally:
        if run(["git", "worktree", "remove", "--force", wt], cwd=ROOT, capture_output=True).returncode:
            print(f"note: {wt} was not removed", file=out)
        shutil.rmtree(wt, ignore_errors=True)
        run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)


def alive(pid):
    if os.name == "nt":  # (os.kill(pid, 0) would send Ctrl+C there)
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(h)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    s = _stat(pid)
    return not (s and s[0] == "Z")  # (an ended process its parent has not reaped yet answers the signal too)


HELD = "TRAM_HEAVY_HELD"  # (set for a job's children: a step of a heavy job runs in its parent's turn)


def processes():
    """{pid: its parent's pid} of every process on the machine (Windows: a Toolhelp snapshot; elsewhere /proc); {} where
    neither answers."""
    parent = {}
    if os.name == "nt":
        class Entry(ctypes.Structure):  # (PROCESSENTRY32W)
            _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong), ("th32ProcessID", ctypes.c_ulong),
                        ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", ctypes.c_ulong),
                        ("cntThreads", ctypes.c_ulong), ("th32ParentProcessID", ctypes.c_ulong),
                        ("pcPriClassBase", ctypes.c_long), ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_wchar * 260)]
        k = ctypes.windll.kernel32
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        snap = k.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
        if snap in (None, ctypes.c_void_p(-1).value):
            return parent
        try:
            e = Entry()
            e.dwSize = ctypes.sizeof(Entry)
            ok = k.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(e))
            while ok:
                parent[e.th32ProcessID] = e.th32ParentProcessID
                ok = k.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(e))
        finally:
            k.CloseHandle(ctypes.c_void_p(snap))
    elif os.path.isdir("/proc"):
        for n in os.listdir("/proc"):
            if n.isdigit() and (s := _stat(int(n))):
                parent[int(n)] = int(s[1])
    return parent


def _stat(pid):
    """/proc/<pid>/stat's fields from the state on (0 state, 1 parent, 11 utime, 12 stime, 19 start, 21 rss pages)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            s = f.read().rsplit(")", 1)[1].split()
        return s if len(s) > 21 else None
    except (OSError, IndexError):
        return None


def _process(pid):
    """(started, CPU seconds so far, bytes of memory held) of one process; None where it cannot be read."""
    if os.name == "nt":
        class Counters(ctypes.Structure):  # (PROCESS_MEMORY_COUNTERS)
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                               "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                               "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        k = ctypes.WinDLL("kernel32")  # (its own: the handle's type set here is not windll's for everyone)
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            made, gone, kernel, user = (ctypes.c_ulonglong() for _ in range(4))  # (FILETIMEs: 100 ns)
            if not k.GetProcessTimes(ctypes.c_void_p(h), *(ctypes.byref(v) for v in (made, gone, kernel, user))):
                return None
            m = Counters()
            m.cb = ctypes.sizeof(m)
            held = m.WorkingSetSize if k.K32GetProcessMemoryInfo(ctypes.c_void_p(h), ctypes.byref(m), m.cb) else 0
            return made.value, (kernel.value + user.value) / 1e7, held
        finally:
            k.CloseHandle(ctypes.c_void_p(h))
    s = _stat(pid)
    if not s:
        return None
    try:
        return int(s[19]), (int(s[11]) + int(s[12])) / os.sysconf("SC_CLK_TCK"), int(s[21]) * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return None


def usage(pid, table=None, skip=()):
    """(CPU seconds so far, GB held now) of a process and of everything it started that still runs, without the pids in
    `skip` and what they started; None where the process cannot be read. The CPU of a child that has ended is gone
    from the sum: it can fall. (Windows keeps a dead parent's pid, which may be reused: a child older than its parent
    is not that process's.)"""
    table = processes() if table is None else table
    kids = {}
    for p, q in table.items():
        kids.setdefault(q, []).append(p)
    top = _process(pid)
    if top is None:
        return None
    cpu, held, seen, todo = top[1], top[2], {pid, *skip}, [(pid, top[0])]
    while todo and len(seen) < 4096:
        p, made = todo.pop()
        for c in kids.get(p, ()):
            if c in seen:
                continue
            seen.add(c)
            if (u := _process(c)) and u[0] >= made:
                cpu, held = cpu + u[1], held + u[2]
                todo.append((c, u[0]))
    return cpu, held / 1e9


def ancestors(pid=None):
    """The pids of this process's parent, its parent and so on (#585). A job whose ancestor holds a ticket runs in that
    turn even when HELD did not reach it (a child started with a clean environment): waiting would wait for itself."""
    pid = os.getpid() if pid is None else pid
    parent = {}
    if os.name == "nt":
        parent = processes()
    else:
        def ppid(p):
            s = _stat(p)
            try:
                return int(s[1]) if s else (os.getppid() if p == os.getpid() else None)
            except ValueError:
                return os.getppid() if p == os.getpid() else None
        q = pid
        while q and q not in parent and len(parent) < 64:
            parent[q] = ppid(q)
            q = parent[q]
    out, q = [], parent.get(pid)
    while q and q not in out and q != pid and len(out) < 64:  # (Windows keeps a dead parent's pid, which may be reused)
        out.append(q)
        q = parent.get(q)
    return out


def _free_gb():
    import sysinfo
    return sysinfo.available_gb()


ENDED = 86  # (the exit code of a job its own watch ended, #815)
NOLIMIT = "TRAM_HEAVY_NOLIMIT"  # (=1: a job's watch warns but ends nothing; heavy.py --no-limit)


def history_path():
    return os.path.join(LOCKS, "history.jsonl")


def history(path=None):
    """The machine's finished heavy jobs, oldest first (#815): dicts with kind, what, root, t (when it started to run),
    wall and cpu (s), gb (the most its processes held at a look), commit (Windows: the Job Object's peak commit, GB),
    expect (s or None), rc (None: not known) and ended (why its watch ended it, or None)."""
    out = []
    try:
        with open(path or history_path(), encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass  # (a line cut by a crash)
    except OSError:
        pass
    return out


def _append(rec):
    os.makedirs(LOCKS, exist_ok=True)
    with open(history_path(), "a", encoding="utf-8", newline="\n") as f:  # (one write: appends do not interleave)
        f.write(json.dumps(rec) + "\n")


def expected(kind, records=None, last=10, least=3, shortest=60.0):
    """A job's expected wall time from the history: the median of the last `last` runs of the same kind that ran to
    their end (exit 0 or not known, not ended by a watch, at least `shortest` s: a heavy job's shorter run failed
    early); None with fewer than `least` of them."""
    walls = [r["wall"] for r in (history() if records is None else records)
             if r.get("kind") == kind and r.get("rc") in (0, None) and not r.get("ended") and r.get("wall", 0) >= shortest]
    walls = walls[-last:]
    return statistics.median(walls) if len(walls) >= least else None


def recent_ends(now=None, within=3600.0, records=None):
    """The jobs a watch ended in the last `within` s, oldest first (tools/board.py shows them)."""
    now = time.time() if now is None else now
    return [r for r in (history() if records is None else records)
            if r.get("ended") and now - (r.get("t", 0) + r.get("wall", 0)) <= within]


SCRIPTS = (".py", ".sh", ".js", ".ps1")


def kind_of(argv):
    """A command's kind in the history: the script it runs (else its program) and the names of its options, without
    their values or the positional arguments, e.g. 'ground_place.py --all --rings' (#815)."""
    argv = [str(a) for a in argv]
    at = next((i for i, a in enumerate(argv) if os.path.splitext(a)[1].lower() in SCRIPTS), None)
    head = os.path.basename(argv[at if at is not None else 0]) if argv else "?"
    if at is None and head.lower().endswith(".exe"):
        head = head[:-4]
    flags = sorted({a.split("=", 1)[0] for a in argv[(at if at is not None else 0) + 1:] if a.startswith("--") and len(a) > 2})
    return " ".join([head, *flags])


def seconds(text):
    """'90s', '20m', '1.5h' or plain minutes ('20') as seconds; None when it is none of them."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh]?)\s*", str(text))
    return float(m[1]) * {"s": 1, "m": 60, "": 60, "h": 3600}[m[2]] if m and float(m[1]) > 0 else None


class _BasicLimits(ctypes.Structure):  # (JOBOBJECT_BASIC_LIMIT_INFORMATION)
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_ulong), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_ulong),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_ulong), ("SchedulingClass", ctypes.c_ulong)]


class _Limits(ctypes.Structure):  # (JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
    _fields_ = [("basic", _BasicLimits), ("io", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class _Accounting(ctypes.Structure):  # (JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: times in 100 ns)
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64), ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", ctypes.c_ulong), ("TotalProcesses", ctypes.c_ulong),
                ("ActiveProcesses", ctypes.c_ulong), ("TotalTerminatedProcesses", ctypes.c_ulong)]


_JOB = None  # (Windows: the Job Object this process runs in with everything it starts, contain(); a handle)
_K32 = None


def _k32():
    global _K32
    if _K32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)  # (its own: the types set here are not windll's for everyone)
        k.CreateJobObjectW.restype = ctypes.c_void_p
        k.GetCurrentProcess.restype = ctypes.c_void_p
        for f in (k.SetInformationJobObject, k.QueryInformationJobObject):
            f.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong] + (
                [ctypes.c_void_p] if f is k.QueryInformationJobObject else [])
        k.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        k.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        _K32 = k
    return _K32


def contain():
    """Puts this process, and so everything it starts from now on, in a Job Object that ends them all when its last
    handle closes: at this process's end, however it comes (#815: a stopped wrapper left its command running). Windows
    only, once a process; None elsewhere or where the system refuses it, and end_tree() then walks the process table."""
    global _JOB
    if _JOB is not None or os.name != "nt":
        return _JOB
    k = _k32()
    h = k.CreateJobObjectW(None, None)  # (not inherited: only this process holds it, so its end closes the job)
    if not h:
        return None
    lim = _Limits()
    lim.basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not (k.SetInformationJobObject(h, 9, ctypes.byref(lim), ctypes.sizeof(lim))  # JobObjectExtendedLimitInformation
            and k.AssignProcessToJobObject(h, k.GetCurrentProcess())):
        k.CloseHandle(ctypes.c_void_p(h))
        return None
    _JOB = h
    return _JOB


def job_totals():
    """(CPU seconds of every process the job has held, ended ones too; the job's peak commit in GB) of contain()'s Job
    Object; None without one."""
    if _JOB is None:
        return None
    k, acc, lim = _k32(), _Accounting(), _Limits()
    if not (k.QueryInformationJobObject(_JOB, 1, ctypes.byref(acc), ctypes.sizeof(acc), None)
            and k.QueryInformationJobObject(_JOB, 9, ctypes.byref(lim), ctypes.sizeof(lim), None)):
        return None
    return (acc.TotalUserTime + acc.TotalKernelTime) / 1e7, lim.PeakJobMemoryUsed / 1e9


def descendants(pid, table=None):
    """The pids of everything `pid` started that still runs, parents before their children (a child older than its
    parent is not that process's: Windows keeps a dead parent's pid, which may be reused)."""
    table = processes() if table is None else table
    kids = {}
    for p, q in table.items():
        kids.setdefault(q, []).append(p)
    top = _process(pid)
    out, seen, todo = [], {pid}, [(pid, top[0] if top else 0)]
    while todo and len(seen) < 4096:
        p, made = todo.pop(0)
        for c in kids.get(p, ()):
            if c in seen:
                continue
            seen.add(c)
            if (u := _process(c)) and u[0] >= made:
                out.append(c)
                todo.append((c, u[0]))
    return out


def end_tree(code):
    """Ends this process and everything it started with exit code `code`: the Job Object at once where contain() made
    one, else each process found under this one in the process table (children last first), then this one."""
    if _JOB is not None:
        _k32().TerminateJobObject(_JOB, code)  # (this process is in it: it ends here too)
    else:
        for pid in reversed(descendants(os.getpid())):
            try:
                os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))  # (Windows: TerminateProcess)
            except OSError:
                pass
    os._exit(code)


class Stuck(SystemExit):
    """A wait ended: the job ahead does nothing (HeavyJob.IDLE). Exits with its message and code 1 when not caught."""


class HeavyJob:
    """with HeavyJob('frametime'): ... waits its turn among the machine's heavy jobs, then runs (#280).

    Two kinds (#728; the user, 2026-11-19: count runs and builds may share the machine when memory allows, the rule of
    2026-11-12 stays for timings):
    - alone (no `share`): a timing, or a job of unknown size. It waits for every job queued before it and every job
      running, and every job queued after it waits for it: two side by side would spoil each other's times.
    - shared (`share={"gb": its peak memory, "cores": the cores it keeps busy}`): a count run or a build, which gives
      the same result beside another job, only later. It waits for the alone jobs queued before it or running and for
      the shared ones queued before it; then it runs beside the shared jobs running while its cores fit beside theirs
      and its memory fits in what is free, less what they declared and do not hold yet, less KEEP. With no other job
      running it starts whatever the memory. `room()` says what it may take, `claim()` what it then takes.
    A ticket in LOCKS says what waits or runs, where, since when and its share; tools/board.py shows the queue. A
    ticket without a share (an older checkout's too) is a job alone. TRAM_HEAVY_NOWAIT=1 runs a job at once beside the
    others (it still shows in the queue). A job that waits IDLE s behind a running one whose processes use no CPU
    ends with an error (Stuck) instead of waiting for good (#585: a night lost behind a job waiting for its own
    child).

    A job in its own turn (not a step in another's) watches itself from the start of its run (#815; the user,
    2026-11-22: "so that one misbehaving process doesn't hold up the queue"). Every EVERY s it reads its process tree
    and the machine (verdict() has the rules: time against its expected time, memory against its share, idle,
    orphaned); a warning goes on its ticket and once to `out`, a breach ends it with one line saying what, how long
    and how much, and everything it started ends with it (contain(), end_tree(), exit ENDED). A request from
    `heavy.py --stop PID` ends it the same way. TRAM_HEAVY_NOLIMIT=1 (limits=False) keeps the warnings and ends
    nothing. Its end, with its time, CPU and peak memory, goes into history(), from which expected() gives the next
    run of the same kind its time."""
    POLL = 5.0
    TELL = 300.0  # (seconds between "still waiting" lines)
    KEEP = 8.0  # (GB left free beside shared jobs: city_terrain.py stops itself under 6, ground_mesh.py under 4)
    IDLE, IDLE_CPU, LOOK = 600.0, 2.0, 60.0  # (a job ahead does nothing: under IDLE_CPU s of CPU in IDLE s, read every LOOK s)
    CORES = os.cpu_count() or 2
    FREE = staticmethod(_free_gb)  # (the machine's free memory in GB, None if unknown: a test's own)
    WATCH = True  # (a job in its own turn watches itself; a test's own may not)
    EVERY, TICK = 60.0, 5.0  # (its tree read every EVERY s; a stop request looked for every TICK s)
    LATE = (2.0, 4.0, 1800.0)  # (warns past 2× its expected time; ends past 4× and at least 30 min over it…)
    TIME_ENDS = False  # (…once a week of history has calibrated the rule, #815: until then it only warns)
    OVER = (1.25, 2.0)  # (warns over 1.25× its declared memory; ends over 2×, or over 1× with the machine short)
    TWICE = 2  # (a memory breach ends the job when seen at this many looks in a row: not a moment's peak)
    RECORD = 60.0  # (a run this long or longer goes into the history; shorter ones only when their watch ended them)

    def __init__(self, what, wait=None, out=None, share=None, expect=None, kind=None, limits=None):
        self.path = os.path.join(LOCKS, f"{os.getpid()}.lock")
        self.what = what
        self.share = None if share is None else {"gb": float(share.get("gb", 0)), "cores": int(share.get("cores", 1))}
        parent = os.environ.get(HELD, "")
        self.nested = parent.isdigit() and int(parent) != os.getpid() and alive(int(parent))
        self.wait = (os.environ.get("TRAM_HEAVY_NOWAIT") != "1" and not self.nested) if wait is None else wait
        self.out = out or sys.stderr
        self.t = None
        self.state, self.since = None, None
        self.why = ""  # (what a shared job waits for beside the jobs running: "memory …", "cores …")
        self.held = None  # (HELD as __enter__ found it, put back by __exit__: a nested job's end must not end its parent's turn)
        self.kind = kind or kind_of(sys.argv)
        self.expect_s = expect  # (s; None: from the history when the run starts)
        self.limits = os.environ.get(NOLIMIT) != "1" if limits is None else limits
        self.own = False  # (holds a turn of its own: watched, recorded)
        self.warn, self.gb, self.peak, self.cpu = "", None, 0.0, 0.0
        self.mark, self.over = None, 0  # (idle: (when, CPU) when the CPU last moved; memory: looks in a row over)
        self.parent, self.parent_made = None, None
        self.ended, self.rc = None, None
        self.lock = threading.Lock()  # (the ticket is written by the job and by its watch)
        self.done = threading.Event()
        self.thread = None

    def _write(self, state):
        with self.lock:
            if state != self.state:
                self.state, self.since = state, time.time()
            tmp = f"{self.path}.{state}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"what": self.what, "root": ROOT, "pid": os.getpid(), "t": self.t, "state": state,
                           "since": self.since, "share": self.share, "kind": self.kind, "expect": self.expect_s,
                           "warn": self.warn, "gb": self.gb, "watch": bool(self.thread) and self.limits,
                           "stops": bool(self.thread)}, f)  # (watch: it ends itself; stops: heavy.py --stop reaches it)
            for wait in (0.05, 0.2, 0.5, 1, 2, 0):  # (Windows refuses while a queue() in another process reads the
                try:                                # ticket; measured 2026-11-06: a check run died at its turn, #282)
                    os.replace(tmp, self.path)
                    return
                except PermissionError:
                    if not wait:
                        raise
                    time.sleep(wait)

    def expect(self, secs):
        """A job says how long it expects to run, once it has sized itself (headless.py: its batches' times)."""
        self.expect_s = float(secs) if secs else None
        if self.state:
            self._write(self.state)

    def verdict(self, now, cpu, gb, free, orphan):
        """(warnings, why the job ends or None) at `now`, from its tree's CPU seconds and GB, the machine's free GB
        (None: unknown) and whether the process that started it is gone. Moves the idle mark and the memory count.

        | rule   | warns                         | ends                                                          |
        | time   | past LATE[0]× expected        | past LATE[1]× and LATE[2] s over it (only with TIME_ENDS)     |
        | memory | over OVER[0]× its share's GB  | over OVER[1]×, or over 1× under KEEP / 2 free (TWICE in a row) |
        |        | alone: under KEEP free        | alone: under KEEP / 2 free (TWICE in a row)                   |
        | idle   | -                             | under IDLE_CPU s of CPU in IDLE s                             |
        | orphan | -                             | the process that started it is gone                           |
        Without limits the warnings stay and nothing ends."""
        warns, ends, run = [], [], now - self.since
        if self.expect_s:
            x = run / self.expect_s
            if x > self.LATE[0]:
                warns.append(f"LATE ×{x:.0f}" if x >= 10 else f"LATE ×{x:.1f}")
                if self.TIME_ENDS and x > self.LATE[1] and run - self.expect_s >= self.LATE[2]:
                    ends.append(f"time: running {run / 60:.0f} min, expected {self.expect_s / 60:.0f}")
        mine = self.share["gb"] if self.share else 0.0
        short = free is not None and free < self.KEEP / 2
        breach = None
        if mine:
            if gb > self.OVER[0] * mine:
                warns.append(f"{gb:.0f} of {mine:.0f} GB")
            if gb > self.OVER[1] * mine or (short and gb > mine):
                breach = (f"memory: {gb:.1f} GB held, {mine:.0f} declared"
                          + (f", {free:.1f} GB left free on the machine" if short else ""))
        elif not self.share and free is not None and free < self.KEEP:
            warns.append(f"{free:.0f} GB free")
            if short:
                breach = f"memory: {free:.1f} GB left free on the machine, {gb:.1f} GB held by this job, which runs alone"
        self.over = self.over + 1 if breach else 0
        if breach and self.over >= self.TWICE:
            ends.append(breach)
        m = self.mark
        if m is None or cpu - m[1] >= self.IDLE_CPU or cpu < m[1]:
            self.mark = (now, cpu)  # (a fall: a child ended and took its CPU from the sum)
        elif now - m[0] >= self.IDLE:
            ends.append(f"idle: {cpu - m[1]:.1f} s of CPU in {(now - m[0]) / 60:.0f} min")
        if orphan:
            ends.append(f"orphan: the process that started it (pid {self.parent}) is gone")
        return warns, (ends[0] if ends and self.limits else None)

    def _orphan(self):
        """Whether the process that started this one is gone (Windows keeps its pid as this one's parent: the pid
        no longer runs, or another process took it; an ended process whose handle another holds still reads)."""
        if os.name != "nt":
            return os.getppid() != self.parent
        if self.parent_made is None:
            return False  # (not readable at the start: not watched)
        p = _process(self.parent)
        return p is None or p[0] != self.parent_made or not alive(self.parent)

    def stop_path(self, pid=None):
        return os.path.join(LOCKS, f"{pid or os.getpid()}.stop")

    def _watch(self):
        last, told = time.time(), set()
        while not self.done.wait(self.TICK):
            now = time.time()
            if os.path.exists(self.stop_path()):
                self._end("stopped on request (heavy.py --stop)", hint=False)
            if now - last < self.EVERY:
                continue
            last = now
            u = usage(os.getpid())
            if u is None:
                continue
            self.cpu, self.gb = max(self.cpu, u[0]), round(u[1], 2)
            self.peak = max(self.peak, u[1])
            warns, why = self.verdict(now, u[0], u[1], self.FREE(), self._orphan())
            if why:
                self._end(why)
            kinds = {"time" if w.startswith("LATE") else "memory" for w in warns}
            if kinds - told:  # (said once a rule: the owner reads it with the job's output)
                told |= kinds
                ran = f"running {(now - self.since) / 60:.0f} min"
                exp = f", expected {self.expect_s / 60:.0f}" if self.expect_s else ""
                mine = f", declared {self.share['gb']:.0f} GB" if self.share else ""
                print(f"heavy jobs: {self.what} warns: {'; '.join(warns)} ({ran}{exp}{mine})", file=self.out, flush=True)
            self.warn = "; ".join(warns)
            self._write("running")  # (the board reads its warning and memory from the ticket)

    def _end(self, why, hint=True):
        """Ends the job and all it started: one line on `out`, its record, its ticket gone, exit ENDED."""
        with self.lock:
            if self.ended or self.done.is_set():
                return
            self.ended = why
        now = time.time()
        print(f"heavy jobs: {self.what} ended by its watch after {(now - self.since) / 60:.0f} min: {why}. It and "
              f"everything it started are stopped (exit {ENDED})"
              + ("; TRAM_HEAVY_NOLIMIT=1 or heavy.py --no-limit lets a job run past its limits." if hint else "."),
              file=self.out, flush=True)
        self._close(now)
        end_tree(ENDED)

    def _close(self, now):
        """The job's record in the history (a run of RECORD s or more, or one its watch ended), its files gone."""
        totals = job_totals()
        wall = now - self.since
        if self.ended or wall >= self.RECORD:
            try:
                _append({"kind": self.kind, "what": self.what, "root": ROOT, "t": round(self.since, 1),
                         "wall": round(wall, 1), "cpu": round(totals[0] if totals else self.cpu, 1),
                         "gb": round(self.peak, 2), "commit": round(totals[1], 2) if totals else None,
                         "expect": self.expect_s and round(self.expect_s), "rc": self.rc, "ended": self.ended})
            except OSError:
                pass  # (a record lost is a run the expected time does not know)
        for p in (self.path, self.stop_path()):
            try:
                os.remove(p)
            except OSError:
                pass

    def room(self, jobs=None):
        """What a shared job may take beside the shared jobs running now: {"gb", "cores"}. The free memory less KEEP
        and less what each of them declared and does not hold yet; the machine's cores less theirs."""
        jobs = queue() if jobs is None else jobs
        free, table = self.FREE(), None
        gb, cores = (1e9 if free is None else free) - self.KEEP, self.CORES
        for j in jobs:
            if j["pid"] == os.getpid() or j["state"] != "running" or not j.get("share"):
                continue
            table = processes() if table is None else table
            used = usage(j["pid"], table)
            gb -= max(0.0, j["share"]["gb"] - (used[1] if used else 0.0))
            cores -= j["share"]["cores"]
        return {"gb": gb, "cores": cores}

    def claim(self, gb=None, cores=None):
        """A shared job says what it takes, once it has sized itself (headless.py: its pages)."""
        if self.share is None:
            return
        self.share = {"gb": self.share["gb"] if gb is None else float(gb),
                      "cores": self.share["cores"] if cores is None else int(cores)}
        if self.state:
            self._write(self.state)

    def ahead(self):
        """The jobs this one waits for. Alone: every ticket before it, and any job running now. Shared: the alone jobs
        among those and the shared ones queued before it; with none, the shared jobs running while its cores or its
        memory do not fit beside them (self.why says which)."""
        me = (self.t, os.getpid())
        jobs = queue()
        others = [j for j in jobs if j["pid"] != os.getpid()]
        self.why = ""

        def first(j):
            return (j["t"], j["pid"]) < me
        if not self.share:
            return [j for j in others if first(j) or j["state"] == "running"]
        turn = [j for j in others if (first(j) or j["state"] == "running") and (not j.get("share") or j["state"] == "waiting")]
        beside = [j for j in others if j["state"] == "running"]
        if turn or not beside:
            return turn
        room = self.room(jobs)
        if room["cores"] < self.share["cores"]:
            self.why = f"cores ({max(0, room['cores'])} of {self.CORES} free, {self.share['cores']} needed)"
        elif room["gb"] < self.share["gb"]:
            self.why = f"memory ({max(0.0, room['gb']):.0f} GB free to share, {self.share['gb']:.0f} needed)"
        return beside if self.why else []

    def _idle(self, ahead, marks, now):
        """The running job ahead that does nothing, as (job, its CPU seconds since, the seconds watched), or None.
        marks: {pid: (when, CPU)} of each job when first seen or when its CPU last moved (or fell: a child ended).
        A job that watches itself ends itself after IDLE s (#815): it is given twice that before this wait ends."""
        table = processes()
        for j in ahead:
            if j["state"] != "running" or not (u := usage(j["pid"], table, skip=(os.getpid(),))):
                continue
            at = marks.get(j["pid"])
            if at is None or u[0] - at[1] >= self.IDLE_CPU or u[0] < at[1]:
                marks[j["pid"]] = (now, u[0])
            elif now - at[0] >= self.IDLE * (2 if j.get("watch") else 1):
                return j, u[0] - at[1], now - at[0]
        return None

    def __enter__(self):
        os.makedirs(LOCKS, exist_ok=True)
        self.t = time.time()
        self.own = not self.nested
        if self.wait and (up := set(ancestors())) and (mine := [j for j in queue() if j["pid"] in up]):
            print(f"heavy jobs: {self.what} runs in the turn of {describe(mine[0])}, a process that started it",
                  file=self.out, flush=True)
            self.wait, self.own = False, False
        self._write("waiting" if self.wait else "running")
        told, last, marks, looked = None, 0.0, {}, 0.0
        while self.wait and (ahead := self.ahead()):
            now = time.time()
            ids = [(j["pid"], j["state"]) for j in ahead] + [self.why[:5]]  # (said again when they change, or every TELL s)
            if ids != told or now - last > self.TELL:
                print(f"heavy jobs: {self.what} waits for {self.why + ' beside ' if self.why else ''}"
                      f"{'; '.join(describe(j, now) for j in ahead)}", file=self.out, flush=True)
                told, last = ids, now
            if now - looked >= self.LOOK:
                looked = now
                if idle := self._idle(ahead, marks, now):
                    j, cpu, secs = idle
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    raise Stuck(f"heavy jobs: {self.what} ends its wait after {(now - self.t) / 60:.0f} min: "
                                f"{describe(j, now)} (pid {j['pid']}) and what it started used {cpu:.1f} s of CPU in "
                                f"{secs / 60:.0f} min. It does nothing: look at it, end it, and start this job again.")
            time.sleep(self.POLL)
        if self.wait and told:
            print(f"heavy jobs: {self.what} starts after {time.time() - self.t:.0f} s", file=self.out, flush=True)
        if self.own and self.WATCH:
            self.parent = os.getppid()
            p = _process(self.parent) if os.name == "nt" else None
            self.parent_made = p[0] if p else None
            if self.expect_s is None:
                self.expect_s = expected(self.kind)
            contain()
            self.thread = threading.Thread(target=self._watch, name="heavy-job watch", daemon=True)
        self._write("running")
        if self.thread:
            self.thread.start()
        self.held = os.environ.get(HELD)
        os.environ[HELD] = str(os.getpid())
        return self

    def __exit__(self, *exc):
        """exc: a with statement's (type, value, traceback), or none from atexit (heavy.turn) or a direct call."""
        if os.environ.get(HELD) == str(os.getpid()):
            if self.held is None:
                del os.environ[HELD]
            else:
                os.environ[HELD] = self.held
        with self.lock:
            self.done.set()
        if self.rc is None and exc:
            e = exc[1]
            self.rc = 0 if exc[0] is None else (e.code if isinstance(e, SystemExit) and isinstance(e.code, int)
                                                 else 0 if isinstance(e, SystemExit) and e.code is None else 1)
        if self.own and self.since and self.state == "running":
            self._close(time.time())
        else:
            try:
                os.remove(self.path)
            except OSError:
                pass


def queue():
    """The machine's heavy jobs, first come first: dicts with what, root, pid, t (queued at), state
    (waiting / running), since and share (None or absent: a job alone). Tickets of dead processes are removed; a
    lock in the older format ("what root" text) counts as running since its file's time."""
    out = []
    if not os.path.isdir(LOCKS):
        return out
    for n in os.listdir(LOCKS):
        p = os.path.join(LOCKS, n)
        if not n.endswith((".lock", ".stop")):
            continue
        try:
            pid = int(n.split(".")[0])
        except ValueError:
            continue
        if n.endswith(".stop"):  # (a stop request, heavy.py --stop: dropped once its job is gone)
            if not alive(pid):
                try:
                    os.remove(p)
                except OSError:
                    pass
            continue
        if not alive(pid):
            try:
                os.remove(p)
            except OSError:
                pass
            continue
        try:
            with open(p, encoding="utf-8") as f:
                text = f.read().strip()
            mtime = os.path.getmtime(p)
        except OSError:
            continue  # (removed while being read: that job just ended)
        try:
            j = json.loads(text)
        except ValueError:
            what, _, root = text.partition(" ")
            j = {"what": what, "root": root, "pid": pid, "t": mtime, "state": "running", "since": mtime}
        out.append(j)
    return sorted(out, key=lambda j: (j["t"] or 0, j["pid"]))


def describe(j, now=None):
    """'frametime in transport-game-268, running 12 min'; a shared job: '…, running 12 min (shared: 16 GB, 8 cores)';
    one that knows its time and has a warning (#815): '…, running 100 min, expected 5 (shared: 6 GB, 4 cores): LATE
    ×20; 17 of 6 GB'"""
    mins = max(0.0, ((now or time.time()) - j["since"]) / 60)  # (a ticket written after `now` was read: "-0 min")
    s = j.get("share")
    return (f"{j['what']} in {os.path.basename(os.path.normpath(j['root']))}, {j['state']} {mins:.0f} min"
            + (f", expected {j['expect'] / 60:.0f}" if j.get("expect") and j["state"] == "running" else "")
            + (f" (shared: {s['gb']:.0f} GB, {s['cores']} core{'s' * (s['cores'] != 1)})" if s else "")
            + (f": {j['warn']}" if j.get("warn") else ""))


def schedule(jobs, now=None, records=None, free=None, cores=None, keep=None):
    """The queue's expected times and estimated starts and finishes (#826), as queue()'s dicts (in its order) with
    expect (s or None), expectFrom ("ticket", "history" or None), start and finish (epoch s; None: not known) and late
    (a running job past its expected time: its finish is taken as now).

    A job's expected time is its ticket's (the job stated it, or its run took it from the history), else the history's
    median of its kind over its runs to their end (expected() with a single run enough: an estimate, not a watch's
    limit). The jobs start as HeavyJob.ahead() lets them, in queue order: a job alone once nothing runs; a shared one
    once no job alone runs and its cores and GB fit beside the shared ones running. The memory to share is the free
    memory now (`free` GB, None: unknown, no limit) plus what the running jobs hold now (their tickets' gb), less KEEP;
    a running shared job takes the larger of its share and its hold. A job after one with no known end has none."""
    now = time.time() if now is None else now
    records = history() if records is None else records
    cores = HeavyJob.CORES if cores is None else cores
    keep = HeavyJob.KEEP if keep is None else keep
    inf = float("inf")
    run = [j for j in jobs if j["state"] == "running"]
    room = (inf if free is None else free + sum(j.get("gb") or 0.0 for j in run)) - keep
    out, ivals = [], []  # (ivals: [start, end, its share or None (alone), GB it takes])

    def est(j):
        if j.get("expect"):
            return float(j["expect"]), "ticket"
        e = expected(j.get("kind"), records, least=1) if j.get("kind") else None
        return e, "history" if e else None

    def fits(j, t):
        on = [iv for iv in ivals if iv[0] <= t < iv[1]]
        if not j.get("share"):
            return not on
        if any(iv[2] is None for iv in on):
            return False
        return not on or (sum(iv[2]["cores"] for iv in on) + j["share"]["cores"] <= cores
                          and sum(iv[3] for iv in on) + j["share"]["gb"] <= room)

    for j in run:
        e, src = est(j)
        start = j.get("since") or j.get("t") or now
        end = start + e if e else inf
        late = end < now
        s = j.get("share")
        ivals.append([start, now if late else end, s, max(s["gb"], j.get("gb") or 0.0) if s else 0.0])
        out.append({**j, "expect": e, "expectFrom": src, "start": start, "finish": None if end == inf else max(end, now),
                    "late": late})
    after = now
    for j in jobs:
        if j["state"] == "running":
            continue
        e, src = est(j)
        start = next((t for t in sorted({after} | {iv[1] for iv in ivals if after < iv[1] < inf}) if fits(j, t)), inf)
        end = start + e if e and start < inf else inf
        after = start
        s = j.get("share")
        ivals.append([start, end, s, s["gb"] if s else 0.0])
        out.append({**j, "expect": e, "expectFrom": src, "start": None if start == inf else start,
                    "finish": None if end == inf else end, "late": False})
    order = {j["pid"]: i for i, j in enumerate(jobs)}
    return sorted(out, key=lambda j: order[j["pid"]])


def busy():
    """The other heavy jobs on this machine now, waiting or running, as 'what root' (the nightly
    measurement does not start while there are any)."""
    return [f"{j['what']} {j['root']}" for j in queue() if j["pid"] != os.getpid()]


if __name__ == "__main__":
    cmd = sys.argv[1:] or ["checkpoints"]
    if cmd[0] == "checkpoints":
        idx = checkpoints()
        for n, v in sorted(idx.items()):
            print(f"{n}: {v['commit']} {v['time']} {v['key'][:12]}")
        print(f"latest: {latest_checkpoint(idx)}")
    elif cmd[0] == "rm-checkpoint" and len(cmd) == 2:
        remove_checkpoint(cmd[1])
    else:
        raise SystemExit(__doc__)
