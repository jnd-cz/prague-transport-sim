"""Build steps keyed by what they read (#511): a step's run traced, what it read and wrote recorded, and the step
skipped while its tool, the modules it imported and every file it read hash as in a recorded run. Its outputs are
then put back from the store as that run left them: a file several steps rewrite in turn (data/lineN.json) comes
back as this step wrote it, so the next step reads what it read before.

    python -P -E tools/stepcache.py trace ROOT RECORD TOOL [ARGS...]   # (tools/rebuild.py runs each step so)

What a run read: files opened under the checkout (Python's open, through an audit hook; osmium's FileProcessor,
which opens its file in C), paths probed (os.stat, os.path.exists, isfile, isdir, getsize, getmtime: a cache may
test a file's date and size) and folders listed. A file read before the step wrote it is an input too. What it
wrote: files opened for writing, the targets of renames, files removed. The key also holds Python's version and the
version of every package imported from outside the checkout; other files outside the checkout are not in it.
A tool that reads a file in some other way (C code, a subprocess) is not seen: rebuild.py --from or --force then.

Kept in reports/rebuild/cache/: hashes.json (a file's SHA-256 by its size, date and file id), steps/ (each step's
last records), store/ (the files the records name, by hash).
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import threading
import time

FORMAT = 1
KEEP = 2  # records kept per step: a branch switched back finds its own
_stat, _replace = os.stat, os.replace  # (the tracer wraps os.stat; its own reads must not count)


def relpath(root, p):
    """p as a "/" path under root, or None outside it (and in __pycache__, .git: never an input)."""
    try:
        p = os.fspath(p)
    except TypeError:
        return None
    if isinstance(p, bytes):
        p = os.fsdecode(p)
    a = os.path.abspath(p)
    if os.path.normcase(a) == os.path.normcase(root):
        return "."
    if not os.path.normcase(a).startswith(os.path.normcase(root) + os.sep):
        return None
    r = a[len(root) + 1:].replace(os.sep, "/")
    if "__pycache__" in r.split("/") or r.startswith(".git/") or r == ".git":
        return None
    return r


def listing(root, r, drop=()):
    """The hash of a folder's names (None when it is not there), less the names in drop."""
    try:
        names = sorted(set(os.listdir(os.path.join(root, r))) - set(drop))
    except (FileNotFoundError, NotADirectoryError):
        return None
    return hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()


class Hashes:
    """A file's state: its SHA-256, "dir" or None (not there); hashed once per size, date and file id."""

    def __init__(self, root, path=None):
        self.root, self.path, self.lock, self.new = root, path, threading.Lock(), {}
        try:
            with open(path, encoding="utf-8") as f:
                self.known = json.load(f)
        except (TypeError, FileNotFoundError, ValueError):
            self.known = {}

    def state(self, r):
        p = os.path.join(self.root, r)
        try:
            st = _stat(p)
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError:  # (a name Windows refuses, a locked file: never equal to a recorded state)
            return "?"
        if stat.S_ISDIR(st.st_mode):
            return "dir"
        sig = [st.st_size, st.st_mtime_ns, st.st_ino]
        k = self.known.get(r)
        if k and k[:3] == sig:
            return k[3]
        try:
            with open(p, "rb") as f:
                h = hashlib.file_digest(f, "sha256").hexdigest()
        except FileNotFoundError:
            return None
        except OSError:
            return "?"
        st2 = _stat(p)
        if [st2.st_size, st2.st_mtime_ns, st2.st_ino] == sig:  # (not rewritten while it was read)
            with self.lock:
                self.known[r] = self.new[r] = [*sig, h]
        return h

    def note(self, r, h):
        """r now holds content h (put back from the store): its new size, date and id with that hash."""
        st = _stat(os.path.join(self.root, r))
        with self.lock:
            self.known[r] = self.new[r] = [st.st_size, st.st_mtime_ns, st.st_ino, h]

    def merge(self, known):
        with self.lock:
            self.known.update(known)
            self.new.update(known)

    def save(self):
        with self.lock:
            if not self.new or not self.path:
                return
            data = json.dumps(self.known, separators=(",", ":"))
            self.new = {}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = f"{self.path}.{os.getpid()}.{threading.get_ident()}.part"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        _replace(tmp, self.path)


def versions(names):
    """Versions of the packages named (outside the checkout): __version__, else the installed distribution's."""
    out = {}
    for n in names:
        m = sys.modules.get(n)
        v = getattr(m, "__version__", None) if m else None
        if v is None:
            try:
                import importlib.metadata
                v = importlib.metadata.version(n)
            except Exception:
                v = ""
        out[n] = str(v)
    return out


# ---- the traced run (a child process) ----

def trace(root, record, tool, args):
    """Run tool as __main__ with args, recording what it reads and writes; the record is written on success."""
    import runpy
    root = os.path.abspath(root)
    hashes = Hashes(root, os.path.join(root, "reports", "rebuild", "cache", "hashes.json"))
    inputs, lists, written, removed, moved = {}, {}, set(), set(), set()
    lock, busy, on = threading.RLock(), threading.local(), [True]
    used_osmium = [False]

    def seen(p, kind="read"):
        if not on[0] or getattr(busy, "v", False):
            return
        busy.v = True
        try:
            r = relpath(root, p)
            if r is None:
                return
            with lock:
                if kind == "write":
                    written.add(r)
                elif kind == "remove":
                    removed.add(r)
                elif kind == "move":
                    moved.add(r)
                elif kind == "list":
                    if r not in lists:
                        try:
                            lists[r] = set(os.listdir(os.path.join(root, r)))
                        except (FileNotFoundError, NotADirectoryError):
                            lists[r] = None
                elif r not in inputs and r not in written:
                    inputs[r] = hashes.state(r)
        finally:
            busy.v = False

    def hook(event, a):
        if event == "open":
            if isinstance(a[0], int):
                return
            mode, flags = a[1], a[2] or 0
            if isinstance(mode, str):  # (open(): "r+" and "a" keep what was there, "w", "w+" and "x" do not)
                r, w = "r" in mode or "a" in mode, any(c in mode for c in "wax+")
            else:  # (os.open)
                acc = flags & 3
                w = acc in (os.O_WRONLY, os.O_RDWR) or bool(flags & (os.O_CREAT | os.O_APPEND | os.O_TRUNC))
                r = acc != os.O_WRONLY and not flags & (os.O_TRUNC | os.O_EXCL) or bool(flags & os.O_APPEND)
            if r:
                seen(a[0])
            if w:
                seen(a[0], "write")
        elif event == "os.rename":
            seen(a[0], "move")
            seen(a[1], "write")
        elif event in ("os.remove", "os.rmdir"):
            seen(a[0], "remove")
        elif event in ("os.listdir", "os.scandir"):
            # (not the import system's own listings of sys.path: a new tool beside them changes no step)
            if sys._getframe(1).f_globals.get("__name__") not in ("_frozen_importlib_external", "importlib._bootstrap_external"):
                seen(a[0] if a[0] is not None else ".", "list")

    def probe(f):
        def wrapped(p, *a, **k):
            if not isinstance(p, int):
                seen(p)
            return f(p, *a, **k)
        wrapped.__wrapped__ = f
        return wrapped

    os.stat = probe(os.stat)
    for n in ("exists", "isfile", "isdir", "getsize", "getmtime"):
        setattr(os.path, n, probe(getattr(os.path, n)))
    try:  # (osmium opens its file in C, past the audit hook)
        import osmium
        fp = osmium.FileProcessor

        def file_processor(src, *a, **k):
            used_osmium[0] = True
            seen(src)
            return fp(src, *a, **k)
        osmium.FileProcessor = file_processor
    except ImportError:
        pass
    sys.addaudithook(hook)
    before = set(sys.modules)
    sys.argv = [tool, *args]
    t0, code = time.time(), 0
    try:
        runpy.run_path(tool, run_name="__main__")
    except SystemExit as e:
        code = e.code
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    on[0] = False
    sys.stdout.flush()
    if code not in (0, None):
        sys.exit(code)
    modules, pkgs = {}, set()
    tools = relpath(root, tool)
    for name, m in list(sys.modules.items()):
        if name == "__main__":
            continue  # (this tracer: FORMAT says when its records change)
        f = getattr(m, "__file__", None)
        r = relpath(root, f) if f else None
        if r:
            modules[r] = hashes.state(r)
        elif f and "." not in name and name not in sys.stdlib_module_names and (name not in before or name == "osmium" and used_osmium[0]):
            pkgs.add(name)  # (imported by the tool; osmium, imported here first, only when it read with it)
    modules[tools] = hashes.state(tools)
    outputs = {}
    for r in written | removed:
        s = hashes.state(r)
        if s is None and r not in removed:
            continue  # (a temporary file, renamed or removed)
        outputs[r] = s
    for r in moved - set(outputs):
        if r in inputs:
            outputs[r] = None  # (an input moved away)
    rec = {"format": FORMAT, "tool": tools, "args": args, "python": sys.version.split()[0],
           "packages": versions(sorted(pkgs)), "modules": modules,
           "inputs": {r: s for r, s in sorted(inputs.items()) if r not in modules and r != "."},
           "listings": {r: (None if names is None else
                            hashlib.sha256("\n".join(sorted(names - {o.rsplit("/", 1)[-1] for o in outputs if o.rsplit("/", 1)[0] == r})).encode("utf-8")).hexdigest())
                        for r, names in sorted(lists.items())},
           "outputs": dict(sorted(outputs.items())), "secs": round(time.time() - t0, 1),
           "when": time.strftime("%Y-%m-%d %H:%M"), "hashes": hashes.new}
    tmp = f"{record}.part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    _replace(tmp, record)


# ---- the cache (rebuild.py's side) ----

class Cache:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.dir = os.path.join(self.root, "reports", "rebuild", "cache")
        self.hashes = Hashes(self.root, os.path.join(self.dir, "hashes.json"))
        self.lock, self.pkgs = threading.Lock(), {}

    def name(self, label, tool, args):
        """The file of a step's records: label (line9, heights) and tool, and a hash of its arguments."""
        a = [relpath(self.root, x) or x if os.path.isabs(x) else x for x in args]
        h = hashlib.sha256(json.dumps([tool, a]).encode("utf-8")).hexdigest()[:10]
        return f"{label}.{os.path.basename(tool)[:-3]}.{h}"

    def records(self, name):
        try:
            with open(os.path.join(self.dir, "steps", f"{name}.json"), encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return []

    def blob(self, h):
        return os.path.join(self.dir, "store", h[:2], h)

    def versions(self, names):
        missing = [n for n in names if n not in self.pkgs]
        if missing:
            import importlib
            for n in missing:
                try:
                    importlib.import_module(n)
                except Exception:
                    pass
            with self.lock:
                self.pkgs.update(versions(missing))
        return {n: self.pkgs[n] for n in names}

    def why(self, rec, phase0=None):
        """None when rec still holds (the step may be skipped), else the first thing that differs."""
        if rec.get("format") != FORMAT:
            return "the record's format"
        if rec["python"] != sys.version.split()[0]:
            return f"Python {rec['python']} → {sys.version.split()[0]}"
        for n, v in self.versions(sorted(rec["packages"])).items():
            if v != rec["packages"][n]:
                return f"{n} {rec['packages'][n]} → {v}"
        st = self.hashes.state
        for r, h in rec["modules"].items():
            if st(r) != h:
                return f"{r} changed"
        out = rec["outputs"]
        for r, h in rec["inputs"].items():
            cur = phase0[r] if phase0 is not None and r in rec.get("phase", ()) and r in phase0 else st(r)
            if cur != h and not (r in out and cur == out[r]):
                return f"{r} {'not there' if cur is None else 'there' if h is None else 'changed'}"
        for r, h in rec["listings"].items():
            drop = [o.rsplit("/", 1)[-1] for o in out if o.rsplit("/", 1)[0] == r]
            if listing(self.root, r, drop) != h:
                return f"the files in {r}/"
        for r, h in out.items():
            if h not in (None, "dir") and not os.path.exists(self.blob(h)):
                return f"{r}: not in the store"
        if rec.get("log") and not os.path.exists(self.blob(rec["log"])):
            return "the log: not in the store"
        return None

    def match(self, name, phase0=None):
        """(the record that holds, None) or (None, why the latest does not)."""
        recs = self.records(name)
        if not recs:
            return None, "no record"
        first = None
        for rec in recs:
            w = self.why(rec, phase0)
            if w is None:
                return rec, None
            first = first or w
        return None, first

    def put(self, r, h):
        """r's content (hash h) into the store."""
        b = self.blob(h)
        if os.path.exists(b):
            return
        os.makedirs(os.path.dirname(b), exist_ok=True)
        tmp = f"{b}.{os.getpid()}.{threading.get_ident()}.part"
        shutil.copyfile(os.path.join(self.root, r), tmp)
        _replace(tmp, b)

    def restore(self, rec, log=None):
        """rec's outputs (and its log at log) as its run left them, each file written whole."""
        items = list(rec["outputs"].items()) + ([(log, rec["log"])] if log and rec.get("log") else [])
        for r, h in items:
            p = os.path.join(self.root, r)
            if self.hashes.state(r) == h:
                continue
            if h is None:
                os.remove(p)
                continue
            if h == "dir":
                os.makedirs(p, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.part"
            shutil.copyfile(self.blob(h), tmp)
            _replace(tmp, p)
            self.hashes.note(r, h)

    def command(self, py, tool, args, record):
        return [*py, os.path.join(self.root, "tools", "stepcache.py"), "trace", self.root, record,
                os.path.join(self.root, "tools", tool), *args]

    def tmp_record(self, name):
        os.makedirs(os.path.join(self.dir, "steps"), exist_ok=True)
        return os.path.join(self.dir, "steps", f"{name}.{os.getpid()}.{threading.get_ident()}.run")

    def save(self, name, tmp, log=None):
        """The run's record (from the tracer's file tmp) kept as the step's latest; its outputs into the store."""
        with open(tmp, encoding="utf-8") as f:
            rec = json.load(f)
        os.remove(tmp)
        self.hashes.merge(rec.pop("hashes", {}))
        for r, h in rec["outputs"].items():
            if h not in (None, "dir", "?"):
                self.put(r, h)
        if log:
            rlog = relpath(self.root, log)
            h = self.hashes.state(rlog)
            if h:
                self.put(rlog, h)
                rec["log"] = h
        self.keep(name, rec)
        return rec

    def keep(self, name, rec, amend=False):
        """rec first among name's records (one equal in its key replaced), at most KEEP of them; amend: rec
        replaces the first, the same run's record changed after it was kept."""
        with self.lock:
            same = lambda o: all(o.get(k) == rec.get(k) for k in ("modules", "inputs", "listings", "packages"))  # noqa: E731
            old = self.records(name)
            if amend and old and (old[0]["when"], old[0]["outputs"]) == (rec["when"], rec["outputs"]):
                old = old[1:]
            recs = [rec] + [o for o in old if not same(o)]
            p = os.path.join(self.dir, "steps", f"{name}.json")
            tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(recs[:KEEP], f, indent=0)
            _replace(tmp, p)
        self.hashes.save()

    def amend(self, name, rec):
        self.keep(name, rec, amend=True)

    def prune(self):
        """Files in the store that no record names any more: removed. (count, bytes)"""
        keep = set()
        sd = os.path.join(self.dir, "steps")
        for fn in os.listdir(sd) if os.path.isdir(sd) else ():
            if fn.endswith(".json"):
                for rec in self.records(fn[:-5]):
                    keep.update(h for h in rec["outputs"].values() if h)
                    keep.add(rec.get("log"))
        n = size = 0
        store = os.path.join(self.dir, "store")
        for d in os.listdir(store) if os.path.isdir(store) else ():
            for fn in os.listdir(os.path.join(store, d)):
                if fn not in keep:
                    p = os.path.join(store, d, fn)
                    size += os.path.getsize(p)
                    os.remove(p)
                    n += 1
        return n, size


if __name__ == "__main__":
    if len(sys.argv) < 5 or sys.argv[1] != "trace":
        print(__doc__)
        sys.exit(2)
    trace(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
