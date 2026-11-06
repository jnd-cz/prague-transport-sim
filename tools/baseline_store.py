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
folder and run one at a time (`HeavyJob`, #280); the nightly measurement does not start while any job
waits or runs.
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
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
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


def measure_at(rev, lines, checks, want, run=subprocess.run, out=None):
    """Main's seedless runs at a commit: a pinned worktree with that commit's code and data, its own
    headless.py (which takes its turn in the heavy-job queue), removed afterwards. Returns (counts, places)
    of the runs measured on exactly `want`, the commit's trees."""
    out = out or sys.stderr
    wt = tempfile.mkdtemp(prefix=f"{os.path.basename(ROOT)}-base-{rev[:7]}-", dir=os.path.dirname(ROOT))
    os.rmdir(wt)  # (git worktree add wants to create it)
    py = sys.executable
    try:
        print(f"measuring {','.join(checks)} of lines {','.join(lines)} at {rev[:7]} in {wt}", file=out, flush=True)
        run(["git", "worktree", "add", "-q", "--detach", wt, rev], cwd=ROOT, check=True)
        run([py, "-I", "tools/snapshot.py", "data-fetch"], cwd=wt, check=True)
        # (exit 1 only says a check is over its threshold: the counts are stored all the same)
        run([py, "-P", "-E", "tools/headless.py", "--lines", ",".join(lines), "--checks", ",".join(checks),
             "--baseline", "--port", "0"], cwd=wt)
        counts, places = {}, {}
        for name, to in (("headless.json", counts), ("headless-places.json", places)):
            p = os.path.join(wt, "reports", "baseline", name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    to.update(json.load(f))
        wanted = {f"line{line}-{c}" for line in lines for c in checks}
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


class HeavyJob:
    """with HeavyJob('headless'): ... waits its turn among the machine's heavy jobs, then runs (#280).

    One heavy job at a time, first come first served: two of them side by side (two sessions' check
    runs, a rebuild beside a check run) each sized itself by the memory free at its start and both
    slowed. A ticket in LOCKS says what waits or runs, where, and since when; tools/board.py shows the
    queue. TRAM_HEAVY_NOWAIT=1 runs a job at once beside the others (it still shows in the queue)."""
    POLL = 5.0
    TELL = 300.0  # (seconds between "still waiting" lines)

    def __init__(self, what, wait=None, out=None):
        self.path = os.path.join(LOCKS, f"{os.getpid()}.lock")
        self.what = what
        parent = os.environ.get(HELD, "")
        nested = parent.isdigit() and int(parent) != os.getpid() and alive(int(parent))
        self.wait = (os.environ.get("TRAM_HEAVY_NOWAIT") != "1" and not nested) if wait is None else wait
        self.out = out or sys.stderr
        self.t = None

    def _write(self, state):
        tmp = f"{self.path}.{state}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"what": self.what, "root": ROOT, "pid": os.getpid(), "t": self.t, "state": state,
                       "since": time.time()}, f)
        os.replace(tmp, self.path)

    def ahead(self):
        """The jobs this one waits for: every ticket before it, and any job running now."""
        me = (self.t, os.getpid())
        return [j for j in queue() if j["pid"] != os.getpid() and ((j["t"], j["pid"]) < me or j["state"] == "running")]

    def __enter__(self):
        os.makedirs(LOCKS, exist_ok=True)
        self.t = time.time()
        self._write("waiting" if self.wait else "running")
        told, last = None, 0.0
        while self.wait and (ahead := self.ahead()):
            now = time.time()
            ids = [(j["pid"], j["state"]) for j in ahead]  # (said again when they change, or every TELL s)
            if ids != told or now - last > self.TELL:
                print(f"heavy jobs: {self.what} waits for {'; '.join(describe(j, now) for j in ahead)}",
                      file=self.out, flush=True)
                told, last = ids, now
            time.sleep(self.POLL)
        if self.wait and told:
            print(f"heavy jobs: {self.what} starts after {time.time() - self.t:.0f} s", file=self.out, flush=True)
        self._write("running")
        os.environ[HELD] = str(os.getpid())
        return self

    def __exit__(self, *exc):
        if os.environ.get(HELD) == str(os.getpid()):
            del os.environ[HELD]
        try:
            os.remove(self.path)
        except OSError:
            pass


def queue():
    """The machine's heavy jobs, first come first: dicts with what, root, pid, t (queued at), state
    (waiting / running) and since. Tickets of dead processes are removed; a lock in the older format
    ("what root" text) counts as running since its file's time."""
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
    """'headless in transport-game-268, running 12 min'"""
    mins = ((now or time.time()) - j["since"]) / 60
    return f"{j['what']} in {os.path.basename(os.path.normpath(j['root']))}, {j['state']} {mins:.0f} min"


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
