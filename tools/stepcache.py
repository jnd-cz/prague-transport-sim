# SPDX-License-Identifier: AGPL-3.0-or-later
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
A tool that reads a file in some other way (C code, a subprocess, a child forked by an explicit fork context) is not
seen: rebuild.py --from or --force then. Multiprocessing children are spawned (Linux too) and traced like the step.
Files outside the checkout are not seen either; a step that reads one has it declared (Cache.save's `declared`: a name
and a value that changes with the file, as the city mesh's key for the ground, #702), and a changed value runs it.

Kept in reports/rebuild/cache/: hashes.json (a file's SHA-256 by its size, date and file id), steps/ (each step's
last records), store/ (the files the records name, by hash). A rebuild on a machine with a data cache (TRAMDATA_CACHE)
keeps it there instead, in stepcache/ (machine_dir, Cache(root, dir)): the records name files by their path under the
checkout, so they hold in any checkout, and a batch's worktree is removed when its PR merges (#797: ground batch C's
rebuild ran every step of every line with no record).

A file of facts (SECTIONED: data/truth.json) is keyed by the top-level sections a step read, not whole (#816: every
ground PR adds a place to groundPlaces, and build_line, dtm and the rest ran again on every line). A step that parses
it with json.load or json.loads gets a dict that notes the keys read from it (Sections); the record then holds each
section's hash, and a change elsewhere in the file leaves the step skipped. A step that reads the file whole (iterates
it, copies it, writes it), opens it without parsing it, or reads no section keeps the file's hash.
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
KEEP = 4  # records kept per step: a branch switched back finds its own, and so do the checkouts that share a cache
DIR_ENV = "TRAMSTEP_CACHE"  # the cache's folder where it is not the checkout's own: Cache sets it, the tracers read it
# (the threads of numpy's BLAS: its sums are split by them, so results differ in the last bits with their number)
ENV = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")
_stat, _replace = os.stat, os.replace  # (the tracer wraps os.stat; its own reads must not count)
_loads = json.loads  # (the tracer wraps json.load and json.loads; its own parses must not count)
WAIT = 10.0  # s: how long a file another thread or process holds open is waited for
SECTIONED = ("data/truth.json",)  # (files keyed by the top-level sections a step read, #816)
SECTIONS = "sections:"  # (an input's value keyed by its sections: never a file's hash, so a checkout from before #816
                        # sharing the cache sees it changed and runs the step)


def section_hash(v):
    """The hash of one section of a sectioned file: its JSON value, keys sorted."""
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def sections_key(secs):
    """A record's input value for a file keyed by sections {name: hash or None}."""
    return SECTIONS + hashlib.sha256(json.dumps(secs, sort_keys=True).encode("utf-8")).hexdigest()


class Sections(dict):
    """A sectioned file as a step parsed it: note(key) for each top-level key read; note(None) when the step reads it
    whole (iterates it or its keys, values or items, takes its length, compares, copies, pickles or changes it). Its
    truth value notes nothing (a step that reads no section keeps the file's hash: Tracer.sections)."""
    __slots__ = ("_note",)

    def __init__(self, d, note):
        super().__init__(d)
        self._note = note

    def __getitem__(self, k):
        self._note(k)
        return dict.__getitem__(self, k)

    def get(self, k, default=None):
        self._note(k)
        return dict.get(self, k, default)

    def __contains__(self, k):
        self._note(k)
        return dict.__contains__(self, k)

    def pop(self, k, *default):
        self._note(None)
        return dict.pop(self, k, *default)

    def setdefault(self, k, default=None):
        self._note(None)
        return dict.setdefault(self, k, default)

    def __bool__(self):
        return dict.__len__(self) > 0

    def __reduce_ex__(self, protocol):  # (copy, deepcopy and a multiprocessing argument: a plain dict, all of it read)
        self._note(None)
        return dict, (dict.copy(self),)


def _whole(name):
    def f(self, *a, **k):
        self._note(None)
        return getattr(dict, name)(self, *a, **k)
    f.__name__ = name
    return f


for _n in ("__iter__", "__reversed__", "__len__", "__eq__", "__ne__", "__repr__", "__or__", "__ror__", "__ior__",
           "__setitem__", "__delitem__", "keys", "values", "items", "copy", "update", "popitem", "clear"):
    setattr(Sections, _n, _whole(_n))  # (dict(s), {**s} and json.dumps(s) go through __iter__, keys or items)


def _waiting(f, *a):
    """f(*a), again while it fails with PermissionError, for up to WAIT s. On Windows a file open elsewhere cannot be
    replaced, nor opened while it is being replaced: a step's tracer reading hashes.json as the parallel rebuild's
    threads replaced it, or two threads replacing it at once (WinError 5, #521). POSIX lets both through."""
    end, d = time.monotonic() + WAIT, 0.005
    while True:
        try:
            return f(*a)
        except PermissionError:
            if time.monotonic() > end:
                raise
            time.sleep(d)
            d = min(2 * d, 0.05)


def replace(tmp, path):
    """tmp renamed over path, waited for while path is held (_waiting)."""
    try:
        _waiting(_replace, tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cache_dir(root):
    """Where root's step cache is: the folder a rebuild set (DIR_ENV, Cache(root, dir)), else the checkout's own."""
    return os.environ.get(DIR_ENV) or os.path.join(os.path.abspath(root), "reports", "rebuild", "cache")


def machine_dir():
    """The step cache's folder beside the machine's data cache (TRAMDATA_CACHE/stepcache), None without one."""
    c = os.environ.get("TRAMDATA_CACHE")
    return os.path.join(c, "stepcache") if c else None


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


def names(root, r):
    """A folder's names (None when it is not there), less the temporary files of writes in flight (tools/atomic.py's
    `<name>.<pid>.part`: a step listing raw/ while another line's step wrote there ran again the next time, #511)."""
    try:
        return {n for n in os.listdir(os.path.join(root, r)) if not n.endswith(".part")}
    except (FileNotFoundError, NotADirectoryError):
        return None


def listing(root, r, drop=()):
    """The hash of a folder's names (None when it is not there), less the names in drop."""
    got = names(root, r)
    if got is None:
        return None
    return hashlib.sha256("\n".join(sorted(got - set(drop))).encode("utf-8")).hexdigest()


class Hashes:
    """A file's state: its SHA-256, "dir" or None (not there); hashed once per size, date and file id."""

    def __init__(self, root, path=None):
        self.root, self.path, self.lock, self.new = root, path, threading.Lock(), {}
        self.saving = threading.Lock()  # (one writer of path at a time, the latest state last)
        try:
            self.known = _waiting(_load, path)
        except (TypeError, FileNotFoundError, ValueError, PermissionError):
            self.known = {}  # (hashed again as files are met)

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
        """The known hashes written to path, if any are new. Threads take turns (rebuild.py's lines each save as their
        steps are kept): each writes what was known when its turn came, so the last write holds every hash noted."""
        with self.saving:
            with self.lock:
                if not self.new or not self.path:
                    return
                data = json.dumps(self.known, separators=(",", ":"))
                self.new = {}
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.{os.getpid()}.part"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(data)
            replace(tmp, self.path)


def versions(names):
    """Versions of the packages named (outside the checkout): __version__, else the installed distribution's. A
    package only a step's child process imported (street_profile's workers read the raster with PIL) is imported here
    for its version: its distribution has another name (Pillow), so the record held "" and Cache.versions, which
    imports it, read 13.0.0: the step ran at every rebuild (#797)."""
    out = {}
    for n in names:
        m = sys.modules.get(n)
        if m is None:
            try:
                import importlib
                m = importlib.import_module(n)
            except Exception:
                m = None
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

class _Tracer:
    """What one process reads and writes under root, from its install() on; its multiprocessing children run under a
    tracer of their own (`child` below) and leave their part beside the step's record, merged at the end."""

    def __init__(self, root, record):
        self.root, self.record = os.path.abspath(root), record
        self.hashes = Hashes(self.root, os.path.join(cache_dir(self.root), "hashes.json"))
        self.inputs, self.lists, self.written, self.removed, self.moved = {}, {}, set(), set(), set()
        self.lock, self.busy, self.on, self.osmium, self.parts = threading.RLock(), threading.local(), True, False, []
        # (each sectioned file read: how often opened for reading and parsed, its texts as opened, the keys read, read whole)
        self.sec = {}

    def opened(self, p):
        """A sectioned file opened for reading: counted, and its text kept to know its parse (parsed())."""
        if not self.on or getattr(self.busy, "v", False):
            return
        r = relpath(self.root, p)
        if r not in SECTIONED:
            return
        self.busy.v = True
        try:
            with open(os.path.join(self.root, r), "rb") as f:
                raw = f.read()
        except OSError:
            raw = None
        finally:
            self.busy.v = False
        with self.lock:
            s = self.sec.setdefault(r, {"opens": 0, "parses": 0, "texts": [], "keys": set(), "all": False})
            s["opens"] += 1
            if raw is not None:
                text = raw.decode("utf-8", "replace")
                for t in (raw, text, text.replace("\r\n", "\n").replace("\r", "\n")):  # (as bytes, read, newlines read)
                    if t not in s["texts"]:
                        s["texts"].append(t)

    def parsed(self, src, obj):
        """obj as json.loads(src) gave it: a Sections that notes its keys when src is a sectioned file's text."""
        if not isinstance(obj, dict) or not self.on or getattr(self.busy, "v", False):
            return obj
        for s in self.sec.values():
            if any(len(t) == len(src) and t == src for t in s["texts"] if type(t) is type(src)):
                with self.lock:
                    s["parses"] += 1

                def note(k, s=s):
                    with self.lock:
                        if isinstance(k, str):
                            s["keys"].add(k)
                        else:
                            s["all"] = True
                return Sections(obj, note)
        return obj

    def sections(self):
        """{file: {"opens", "parses", "all", "keys": {name: hash or None}}} of the sectioned files this process read;
        the hashes from the file as it was first opened."""
        out = {}
        for r, s in self.sec.items():
            try:
                whole = _loads(next(t for t in s["texts"] if isinstance(t, str)))
            except (StopIteration, ValueError):
                whole = None
            if not isinstance(whole, dict):
                s["all"] = True
                whole = {}
            out[r] = {"opens": s["opens"], "parses": s["parses"], "all": s["all"],
                      "keys": {k: section_hash(whole[k]) if k in whole else None for k in sorted(s["keys"])}}
        return out

    def seen(self, p, kind="read"):
        if not self.on or getattr(self.busy, "v", False):
            return
        self.busy.v = True
        try:
            r = relpath(self.root, p)
            if r is None:
                return
            with self.lock:
                if kind == "write":
                    self.written.add(r)
                elif kind == "remove":
                    self.removed.add(r)
                elif kind == "move":
                    self.moved.add(r)
                elif kind == "list":
                    if r not in self.lists:
                        self.lists[r] = names(self.root, r)
                elif r not in self.inputs and r not in self.written:
                    self.inputs[r] = self.hashes.state(r)
        finally:
            self.busy.v = False

    def hook(self, event, a):
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
                self.seen(a[0])
                self.opened(a[0])
            if w:
                self.seen(a[0], "write")
        elif event == "os.rename":
            self.seen(a[0], "move")
            self.seen(a[1], "write")
        elif event in ("os.remove", "os.rmdir"):
            self.seen(a[0], "remove")
        elif event in ("os.listdir", "os.scandir"):
            # (not the import system's own listings of sys.path: a new tool beside them changes no step)
            if sys._getframe(1).f_globals.get("__name__") not in ("_frozen_importlib_external", "importlib._bootstrap_external"):
                self.seen(a[0] if a[0] is not None else ".", "list")

    def install(self):
        def probe(f):
            def wrapped(p, *a, **k):
                if not isinstance(p, int):
                    self.seen(p)
                return f(p, *a, **k)
            wrapped.__wrapped__ = f
            return wrapped

        os.stat = probe(os.stat)
        for n in ("exists", "isfile", "isdir", "getsize", "getmtime"):
            setattr(os.path, n, probe(getattr(os.path, n)))

        def loads(s, *a, **k):  # (json.load reads the file and calls loads: one parse, seen once)
            return self.parsed(s, _loads(s, *a, **k))

        def load(fp, *a, **k):
            return loads(fp.read(), *a, **k)
        json.loads, json.load = loads, load
        try:  # (osmium opens its file in C, past the audit hook)
            import osmium
            fp = osmium.FileProcessor

            def file_processor(src, *a, **k):
                self.osmium = True
                self.seen(src)
                return fp(src, *a, **k)
            osmium.FileProcessor = file_processor
        except ImportError:
            pass
        import multiprocessing
        import multiprocessing.spawn as mps
        # (children spawned on every system, as on Windows: a forked one never passes through the command line below,
        # and what it did would not reach the record; Linux forks by default)
        multiprocessing.set_start_method("spawn", force=True)
        command = mps.get_command_line

        def child_command(**kw):  # (a child of the step, spawned: this file runs it, under a tracer of its own)
            c = command(**kw)
            if "-c" not in c:
                return c
            with self.lock:
                part = f"{self.record}.{os.getpid()}.{len(self.parts)}.child"
                self.parts.append(part)
            i = c.index("-c")
            return [*c[:i], os.path.abspath(__file__), "child", self.root, part, *c[i:]]
        mps.get_command_line = child_command
        sys.addaudithook(self.hook)
        self.before = set(sys.modules)

    def found(self):
        """What this process read and wrote, its children's merged in: (modules, packages, the merged sets)."""
        self.on = False
        modules, pkgs = set(), set()
        me = os.path.normcase(os.path.abspath(__file__))
        for name, m in list(sys.modules.items()):
            f = getattr(m, "__file__", None)
            if f and os.path.normcase(os.path.abspath(f)) == me:
                continue  # (this tracer, as __main__ and multiprocessing's __mp_main__: FORMAT says when its records change)
            r = relpath(self.root, f) if f else None
            if r:
                modules.add(r)
            elif f and "." not in name and name not in sys.stdlib_module_names and (
                    name not in self.before or name == "osmium" and self.osmium):
                pkgs.add(name)  # (imported by the tool; osmium, imported here first, only when it read with it)
        cpu, missing = time.process_time(), 0
        self.found_sections = secs = self.sections()
        for part in self.parts:
            try:
                with open(part, encoding="utf-8") as f:
                    c = json.load(f)
                os.remove(part)
            except FileNotFoundError:
                missing += 1  # (a child that was killed: what it did is not known)
                continue
            for r, s in c["inputs"].items():
                if r not in self.inputs and r not in self.written:
                    self.inputs[r] = s
            for r, names in c["lists"].items():
                self.lists.setdefault(r, None if names is None else set(names))
            self.written.update(c["written"])
            self.removed.update(c["removed"])
            self.moved.update(c["moved"])
            modules.update(c["modules"])
            pkgs.update(c["packages"])
            self.hashes.merge(c["hashes"])
            cpu += c["cpu"]
            missing += c["missing"]
            for r, s in c.get("sections", {}).items():
                m = secs.setdefault(r, {"opens": 0, "parses": 0, "all": False, "keys": {}})
                m["opens"] += s["opens"]
                m["parses"] += s["parses"]
                m["all"] = m["all"] or s["all"]
                for k, h in s["keys"].items():
                    if m["keys"].setdefault(k, h) != h:
                        m["all"] = True  # (the file changed between the two reads: keyed whole)
        return modules, pkgs, cpu, missing

    def part(self, path):
        """A child's part for its parent's record."""
        modules, pkgs, cpu, missing = self.found()
        tmp = f"{path}.part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"inputs": self.inputs, "lists": {r: None if n is None else sorted(n) for r, n in self.lists.items()},
                       "written": sorted(self.written), "removed": sorted(self.removed), "moved": sorted(self.moved),
                       "modules": sorted(modules), "packages": sorted(pkgs), "cpu": cpu, "missing": missing,
                       "hashes": self.hashes.new, "sections": self.found_sections}, f)
        replace(tmp, path)


def trace(root, record, tool, args):
    """Run tool as __main__ with args, recording what it reads and writes; the record is written on success."""
    import runpy
    t = _Tracer(root, record)
    t.install()
    sys.argv = [tool, *args]
    env = {k: os.environ.get(k) for k in ENV}  # (as the step was given it: a tool may set its workers' own)
    t0, code = time.time(), 0
    try:
        runpy.run_path(tool, run_name="__main__")
    except SystemExit as e:
        code = e.code
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    modules, pkgs, cpu, missing = t.found()
    if code not in (0, None):
        sys.exit(code)
    root, hashes = t.root, t.hashes
    tools = relpath(root, tool)
    modules = {r: hashes.state(r) for r in sorted(modules | {tools})}
    outputs = {}
    for r in t.written | t.removed:
        s = hashes.state(r)
        if s is None and r not in t.removed:
            continue  # (a temporary file, renamed or removed)
        outputs[r] = s
    for r in t.moved - set(outputs):
        if r in t.inputs:
            outputs[r] = None  # (an input moved away)
    inputs = {r: s for r, s in sorted(t.inputs.items()) if r not in modules and r != "."}
    secs = {}
    for r, s in sorted(t.found_sections.items()):
        # (by its sections only where every read of it was a parse, some section was read and none read it whole)
        if r in inputs and inputs[r] not in (None, "dir", "?") and r not in outputs and not s["all"] \
                and s["keys"] and s["opens"] and s["opens"] == s["parses"]:
            secs[r] = s["keys"]
            inputs[r] = sections_key(s["keys"])
    rec = {"format": FORMAT, "tool": tools, "args": args, "python": sys.version.split()[0],
           "env": env, "packages": versions(sorted(pkgs)), "modules": modules,
           "inputs": inputs, **({"sections": secs} if secs else {}),
           "listings": {r: (None if names is None else
                            hashlib.sha256("\n".join(sorted(names - {o.rsplit("/", 1)[-1] for o in outputs if o.rsplit("/", 1)[0] == r})).encode("utf-8")).hexdigest())
                        for r, names in sorted(t.lists.items())},
           "outputs": dict(sorted(outputs.items())), "secs": round(time.time() - t0, 1),
           "cpu": round(cpu, 1),  # (all the process's threads and its children's, imports too: the cores it kept busy)
           "when": time.strftime("%Y-%m-%d %H:%M"), "hashes": hashes.new}
    if missing:
        rec["untraced"] = f"{missing} child process(es) left no trace"
    tmp = f"{record}.part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    replace(tmp, record)


def child(root, part, argv):
    """A multiprocessing child of a traced step: `python stepcache.py child ROOT PART -c PROG --multiprocessing-fork`."""
    t = _Tracer(root, part)
    t.install()
    prog, sys.argv = argv[1], ["-c", *argv[2:]]
    code = 0
    try:
        exec(compile(prog, "-c", "exec"), {"__name__": "__main__"})
    except SystemExit as e:
        code = e.code
    finally:
        t.part(part)
    sys.exit(code)


# ---- the cache (rebuild.py's side) ----

class Cache:
    def __init__(self, root, dir=None):
        """root's step cache: in `dir` (machine_dir(): shared by the machine's checkouts), else the checkout's own. The
        steps' tracers, child processes, find it by DIR_ENV."""
        self.root = os.path.abspath(root)
        if dir:
            os.environ[DIR_ENV] = os.path.abspath(dir)
        else:
            os.environ.pop(DIR_ENV, None)
        self.dir = cache_dir(self.root)
        self.hashes = Hashes(self.root, os.path.join(self.dir, "hashes.json"))
        self.lock, self.pkgs, self.secs = threading.Lock(), {}, {}

    def sections(self, r):
        """{name: hash} of a sectioned file's top-level sections now ({} when it is not a JSON object), None when it
        is not there; parsed once per state of the file."""
        st = self.hashes.state(r)
        if st in (None, "dir", "?"):
            return None
        with self.lock:
            if r in self.secs and self.secs[r][0] == st:
                return self.secs[r][1]
        try:
            with open(os.path.join(self.root, r), encoding="utf-8") as f:
                whole = _loads(f.read())
        except (OSError, ValueError):
            return None
        out = {k: section_hash(v) for k, v in whole.items()} if isinstance(whole, dict) else {}
        with self.lock:
            self.secs[r] = (st, out)
        return out

    def name(self, label, tool, args):
        """The file of a step's records: label (line9, heights) and tool, and a hash of its arguments."""
        a = [relpath(self.root, x) or x if os.path.isabs(x) else x for x in args]
        h = hashlib.sha256(json.dumps([tool, a]).encode("utf-8")).hexdigest()[:10]
        return f"{label}.{os.path.basename(tool)[:-3]}.{h}"

    def records(self, name):
        try:
            return _waiting(_load, os.path.join(self.dir, "steps", f"{name}.json"))
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

    def why(self, rec, phase0=None, env=None, declared=None):
        """None when rec still holds (the step may be skipped), else the first thing that differs. env: the step's
        environment (os.environ by default); declared: the step's declared inputs now (save())."""
        if rec.get("format") != FORMAT:
            return "the record's format"
        if rec.get("untraced"):
            return rec["untraced"]
        was, now = rec.get("declared") or {}, declared or {}
        for k in sorted(set(was) | set(now)):
            if was.get(k) != now.get(k):
                return f"{k} {was.get(k)} → {now.get(k)}"
        if rec["python"] != sys.version.split()[0]:
            return f"Python {rec['python']} → {sys.version.split()[0]}"
        env = os.environ if env is None else env
        for k in ENV:
            if rec.get("env", {}).get(k) != env.get(k):
                return f"{k} {rec.get('env', {}).get(k)} → {env.get(k)}"
        for n, v in self.versions(sorted(rec["packages"])).items():
            if v != rec["packages"][n]:
                return f"{n} {rec['packages'][n]} → {v}"
        st = self.hashes.state
        for r, h in rec["modules"].items():
            if st(r) != h:
                return f"{r} changed"
        out = rec["outputs"]
        for r, h in rec["inputs"].items():
            if isinstance(h, str) and h.startswith(SECTIONS):  # (keyed by the sections the step read, #816)
                was, now = rec.get("sections", {}).get(r), self.sections(r)
                if was is None or now is None:
                    return f"{r} {'not there' if now is None else 'changed'}"
                for k, v in was.items():
                    if now.get(k) != v:
                        return f"{r}: {k} {'not there' if now.get(k) is None else 'there' if v is None else 'changed'}"
                continue
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

    def match(self, name, phase0=None, env=None, declared=None):
        """(the record that holds, None) or (None, why the latest does not)."""
        recs = self.records(name)
        if not recs:
            return None, "no record"
        first = None
        for rec in recs:
            w = self.why(rec, phase0, env, declared)
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
        replace(tmp, b)

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
            replace(tmp, p)
            self.hashes.note(r, h)

    def command(self, py, tool, args, record):
        return [*py, os.path.join(self.root, "tools", "stepcache.py"), "trace", self.root, record,
                os.path.join(self.root, "tools", tool), *args]

    def tmp_record(self, name):
        os.makedirs(os.path.join(self.dir, "steps"), exist_ok=True)
        return os.path.join(self.dir, "steps", f"{name}.{os.getpid()}.{threading.get_ident()}.run")

    def save(self, name, tmp, log=None, declared=None):
        """The run's record (from the tracer's file tmp) kept as the step's latest; its outputs into the store.
        declared: what the step reads that its trace cannot see, by a name and a value that changes with it (a file
        outside the checkout by the key it is kept under: the city mesh, #702); a later run matches only with the same."""
        with open(tmp, encoding="utf-8") as f:
            rec = json.load(f)
        os.remove(tmp)
        if declared:
            rec["declared"] = dict(sorted(declared.items()))
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
            same = lambda o: all(o.get(k) == rec.get(k) for k in ("modules", "inputs", "listings", "packages", "env", "declared"))  # noqa: E731
            old = self.records(name)
            if amend and old and (old[0]["when"], old[0]["outputs"]) == (rec["when"], rec["outputs"]):
                old = old[1:]
            recs = [rec] + [o for o in old if not same(o)]
            p = os.path.join(self.dir, "steps", f"{name}.json")
            tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(recs[:KEEP], f, indent=0)
            replace(tmp, p)
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
    if len(sys.argv) >= 6 and sys.argv[1] == "child":
        child(sys.argv[2], sys.argv[3], sys.argv[4:])
    if len(sys.argv) < 5 or sys.argv[1] != "trace":
        print(__doc__)
        sys.exit(2)
    trace(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
