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
cores fit (#728); the nightly measurement does not start while any job waits or runs.
"""
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
        return True
    except OSError:
        return False


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
    child)."""
    POLL = 5.0
    TELL = 300.0  # (seconds between "still waiting" lines)
    KEEP = 8.0  # (GB left free beside shared jobs: city_terrain.py stops itself under 6, ground_mesh.py under 4)
    IDLE, IDLE_CPU, LOOK = 600.0, 2.0, 60.0  # (a job ahead does nothing: under IDLE_CPU s of CPU in IDLE s, read every LOOK s)
    CORES = os.cpu_count() or 2
    FREE = staticmethod(_free_gb)  # (the machine's free memory in GB, None if unknown: a test's own)

    def __init__(self, what, wait=None, out=None, share=None):
        self.path = os.path.join(LOCKS, f"{os.getpid()}.lock")
        self.what = what
        self.share = None if share is None else {"gb": float(share.get("gb", 0)), "cores": int(share.get("cores", 1))}
        parent = os.environ.get(HELD, "")
        nested = parent.isdigit() and int(parent) != os.getpid() and alive(int(parent))
        self.wait = (os.environ.get("TRAM_HEAVY_NOWAIT") != "1" and not nested) if wait is None else wait
        self.out = out or sys.stderr
        self.t = None
        self.state, self.since = None, None
        self.why = ""  # (what a shared job waits for beside the jobs running: "memory …", "cores …")
        self.held = None  # (HELD as __enter__ found it, put back by __exit__: a nested job's end must not end its parent's turn)

    def _write(self, state):
        if state != self.state:
            self.state, self.since = state, time.time()
        tmp = f"{self.path}.{state}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"what": self.what, "root": ROOT, "pid": os.getpid(), "t": self.t, "state": state,
                       "since": self.since, "share": self.share}, f)
        for wait in (0.05, 0.2, 0.5, 1, 2, 0):  # (Windows refuses while a queue() in another process reads the ticket;
            try:                                # measured 2026-11-06: a check run died at its turn, #282)
                os.replace(tmp, self.path)
                return
            except PermissionError:
                if not wait:
                    raise
                time.sleep(wait)

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
        marks: {pid: (when, CPU)} of each job when first seen or when its CPU last moved (or fell: a child ended)."""
        table = processes()
        for j in ahead:
            if j["state"] != "running" or not (u := usage(j["pid"], table, skip=(os.getpid(),))):
                continue
            at = marks.get(j["pid"])
            if at is None or u[0] - at[1] >= self.IDLE_CPU or u[0] < at[1]:
                marks[j["pid"]] = (now, u[0])
            elif now - at[0] >= self.IDLE:
                return j, u[0] - at[1], now - at[0]
        return None

    def __enter__(self):
        os.makedirs(LOCKS, exist_ok=True)
        self.t = time.time()
        if self.wait and (up := set(ancestors())) and (mine := [j for j in queue() if j["pid"] in up]):
            print(f"heavy jobs: {self.what} runs in the turn of {describe(mine[0])}, a process that started it",
                  file=self.out, flush=True)
            self.wait = False
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
        self._write("running")
        self.held = os.environ.get(HELD)
        os.environ[HELD] = str(os.getpid())
        return self

    def __exit__(self, *exc):
        if os.environ.get(HELD) == str(os.getpid()):
            if self.held is None:
                del os.environ[HELD]
            else:
                os.environ[HELD] = self.held
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
        if not n.endswith(".lock"):
            continue
        try:
            pid = int(n.split(".")[0])
        except ValueError:
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
    """'frametime in transport-game-268, running 12 min'; a shared job: '…, running 12 min (shared: 16 GB, 8 cores)'"""
    mins = max(0.0, ((now or time.time()) - j["since"]) / 60)  # (a ticket written after `now` was read: "-0 min")
    s = j.get("share")
    return (f"{j['what']} in {os.path.basename(os.path.normpath(j['root']))}, {j['state']} {mins:.0f} min"
            + (f" (shared: {s['gb']:.0f} GB, {s['cores']} core{'s' * (s['cores'] != 1)})" if s else ""))


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
