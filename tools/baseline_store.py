"""Main's regression baseline in the data store, and the machine's heavy-job lock (#157). Stdlib only:
tools/headless.py (--baseline --publish, --compare) and tools/autodeploy.py (the nightly measurement)
use it.

A baseline is named by what its counts depend on (MEASURED: the git trees of the game, the in-page
checks and the data manifest), hashed: `baselines/<key>.json` and `<key>.places.json` in the store. A
branch looks up the key of its merge base, so it gets main's numbers for exactly that code and data.

Heavy jobs (headless.py, rebuild.py) hold a lock file in the system temp folder while they run; the
nightly measurement does not start while one is held by a live process.
"""
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# (what the counts depend on: the game, the in-page checks, the data; not the build tools, whose output
# the manifest covers, nor the harness)
MEASURED = ("src", "index.html", "tools/bench", "tools/lint.js", "tools/traffic_lint.js", "tools/autopilot.js",
            "data/MANIFEST.json")
LOCKS = os.path.join(tempfile.gettempdir(), "tram-heavy")


def git(*args, root=ROOT):
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def trees(rev, root=ROOT):
    """The git objects the checks depend on, at a commit."""
    return {p: git("rev-parse", f"{rev}:{p}", root=root) for p in MEASURED}


def key(t):
    return hashlib.sha256(json.dumps(t, sort_keys=True).encode()).hexdigest()


def _store():
    from snapshot import Store
    return Store(os.environ.get("TRAMDATA_STORE", "tramdata:store"))


def _tmp():
    # (sftp gets paths relative to the checkout: a temp folder on another drive has none)
    return tempfile.mkdtemp(prefix=".baseline-", dir=ROOT)


def publish(k, base, places):
    """Upload one baseline (counts and places) under its key; a temporary name, then rename."""
    st, d = _store(), _tmp()
    try:
        cmds = [f'-mkdir "{st.dir}/baselines"']
        for name, obj in ((f"{k}.json", base), (f"{k}.places.json", places)):
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


def fetch(k):
    """(counts, places) of the published baseline with this key, or (None, None)."""
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


class HeavyJob:
    """with HeavyJob('headless'): ... holds a lock file while the job runs."""
    def __init__(self, what):
        self.path = os.path.join(LOCKS, f"{os.getpid()}.lock")
        self.what = what

    def __enter__(self):
        os.makedirs(LOCKS, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"{self.what} {ROOT}\n")
        return self

    def __exit__(self, *exc):
        try:
            os.remove(self.path)
        except OSError:
            pass


def busy():
    """The heavy jobs running on this machine now (stale lock files of dead processes are removed)."""
    out = []
    if not os.path.isdir(LOCKS):
        return out
    for n in os.listdir(LOCKS):
        p = os.path.join(LOCKS, n)
        try:
            pid = int(n.split(".")[0])
        except ValueError:
            continue
        if pid != os.getpid() and alive(pid):
            with open(p, encoding="utf-8") as f:
                out.append(f.read().strip())
        elif pid != os.getpid():
            try:
                os.remove(p)
            except OSError:
                pass
    return out
