"""Pinned source snapshots and built game data, kept in the data store (not in git). See DATA.md.

The world is built from raw sources (OSM, PID GTFS, the Prague street survey, Geoportál, terrain) that
change or disappear upstream, so every computer builds from the same files: a **snapshot**. Its manifest
(`snapshots/<id>.json`, in git) lists every input file with its size and SHA-256 and where it came
from; the files themselves live in the data store under their hash (`store/sources/<sha256>`), so a
file that did not change between snapshots is stored once. `snapshots/CURRENT` names the snapshot the
build uses.

The **built game data** (`data/`, except the hand-made `truth.json`) travels the same way:
`data/MANIFEST.json` (in git) lists the files of the build that goes with this commit,
`store/builds/<sha256>` holds them.

Usage (python -I is enough; the store is reached with the system's `sftp`, ssh config host `tramdata`):
    python -I tools/snapshot.py fetch              # raw/ for snapshots/CURRENT (checks every hash)
    python -I tools/snapshot.py data-fetch         # data/ for data/MANIFEST.json
    python -I tools/snapshot.py status             # what differs locally
    python -I tools/snapshot.py publish 2026-11-05 --note "new OSM and GTFS"   # raw/ -> new snapshot
    python -I tools/snapshot.py data-publish --note "line 17 rebuilt"        # data/ -> MANIFEST
    python -I tools/snapshot.py verify [--base main]   # after a publish: all in the store, new files intact
    python -I tools/snapshot.py cache-prune [--dry-run]   # drop cached files no checkout links any more
Options: --store HOST:DIR (default tramdata:store, or $TRAMDATA_STORE); --cache DIR (default
$TRAMDATA_CACHE; none: files are copied into the checkout only) or --no-cache.

The machine cache (#77, class Cache): every checkout on a computer shares one folder of store files,
hard-linked into raw/ and data/ and protected against writing in place; see DATA.md.

A new snapshot is a deliberate step: refresh the inputs (instructions per source group below and in
DATA.md), check the build, then `publish`. The Overpass API is not a source any more.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I leaves it out)
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPDIR = os.path.join(ROOT, "snapshots")
DATA_MANIFEST = os.path.join(ROOT, "data", "MANIFEST.json")
DATA_KEEP = {"truth.json", "MANIFEST.json"}  # in git, not in the store

# The input groups of a snapshot: which files, where they come from, how to refresh them.
SOURCES = [
    {"name": "osm", "globs": ["raw/osm/*.osm.pbf", "raw/osm/*.osm.pbf.md5"],
     "source": "Geofabrik extract europe/czech-republic (download.geofabrik.de), cut to Prague by tools/osm_local.py",
     "licence": "ODbL, © OpenStreetMap contributors",
     "refresh": "download czech-republic-latest.osm.pbf (+ .md5), python -P -E tools/osm_local.py cut <file>, delete the old files"},
    {"name": "gtfs", "globs": ["raw/PID_GTFS.zip"],
     "source": "PID open data, https://data.pid.cz/PID_GTFS.zip",
     "licence": "CC BY 4.0, ROPID",
     "refresh": "download the zip; tools/build_line.py's SERVICE_DATE must fall inside the feed"},
    {"name": "dtm", "globs": ["raw/dtm/*.zip", "raw/dtm/provenance.json"], "unzip": True,
     "source": "Prague digital technical map, ZPS district packages (isdtmk.dtm-praha-sck.cz, OPL + KR)",
     "licence": "CC BY 4.0, datový podklad © IPR Praha / DTM Praha",
     "refresh": "DATA.md, Regional DTM monthly downloads (the monthly index, then tools/dtm_schema.py --compare); fetch unzips them"},
    {"name": "dtm-di", "globs": ["raw/dtm-di/*.jvf.zip", "raw/dtm-di/*.json",
                                  "raw/dtm-di/terms.pdf", "raw/dtm-di/access.html"],
     "source": "Prague DTM DI set 7 public JVF district packages; exact URLs, state dates and hashes in raw/dtm-di/provenance.json",
     "licence": "CC BY 4.0, datový podklad © IPR Praha; download-service terms I.8 (raw/dtm-di/terms.pdf); catalogue openData=false retained",
     "refresh": "python -P -E tools/dtm_di.py --fetch; review access/licence evidence before publishing; ZIPs read directly"},
    {"name": "geoportal", "globs": ["raw/geoportal/**/*"],
     "source": "Geoportál Praha services: Budovy 3D, Mosty 3D (I3S), opěrné zdi, stromy (tools/geoportal.py caches)",
     "licence": "CC BY 4.0, datový podklad © IPR Praha",
     "refresh": "delete raw/geoportal/lineN and run python -I tools/geoportal.py --line N"},
    {"name": "dem", "globs": ["raw/dem/*.tif", "raw/terrain*.tif", "raw/terrain*.json", "raw/line*/terrain*.tif",
                              "raw/line*/terrain*.json", "raw/run*/terrain*.tif", "raw/run*/terrain*.json"],
     "source": "ČÚZK DMR 5G ImageServer exports (fine terrain tiles: tools/fine_terrain.py; line grids: build_line.py)",
     "licence": "CC BY 4.0, ČÚZK",
     "refresh": "delete the tiles / terrain.* and rerun the tools"},
    {"name": "ipr-dtm", "globs": ["raw/ipr-dtm/DTM.zip", "raw/ipr-dtm/*.json"], "unzip": True,
     "source": "IPR Praha, Digitální model terénu - rastr (1 m, lidar 2023), opendata.geoportalpraha.cz item "
               "97d2c9c11aa9478cb21b469b8a4f820e; URLs, date and hashes in raw/ipr-dtm/provenance.json",
     "licence": "CC BY 4.0, datový podklad © IPR Praha",
     "refresh": "python -P -E tools/ipr_dtm.py --fetch (2 GB); fetch unzips it; rebuild checks the datum (fine_terrain.py)"},
    {"name": "dtmpoints", "globs": ["raw/dtmpoints/*.json"],
     "source": "Archivní DTM Prahy – povrchové znaky (DTMP_CUR_TMISZNAK_B FeatureServer, state 2024-06-30), tools/dtm_points.py",
     "licence": "CC BY 4.0, datový podklad © IPR Praha",
     "refresh": "python -I tools/dtm_points.py N --refresh"},
    {"name": "dtmp-tracks", "globs": ["raw/dtmp-tracks/*.json"],
     "source": "Archived DTMP tram track axes, CTMTP_KOD=55010, https://gs-pub.praha.eu/arcgis/rest/services/dtmp/dtmp/MapServer/10; query batches, dates and hashes in provenance.json",
     "licence": "CC BY 4.0, datový podklad © IPR Praha; download-service terms I.8, retained in raw/dtm-di/terms.pdf",
     "refresh": "python -P -E tools/dtmp_tracks.py --fetch --acquire-only; inspect offline with tools/dtmp_tracks.py before snapshot publication"},
    {"name": "ortho", "globs": ["raw/ortho/*"],
     "source": "IPR Praha orthophoto, leaf-off flight 2026 (ImageServer, tools/ortho_lanes.py tiles)",
     "licence": "CC BY 4.0, IPR Praha", "refresh": "rerun tools/ortho_lanes.py"},
    {"name": "proj", "globs": ["raw/proj/*.tif"],
     "source": "ČÚZK correction grid ETRS89 -> S-JTSK (cdn.proj.org/cz_cuzk_table_-y-x_3_v1710.tif), used by tools/geo.py",
     "licence": "CC BY 4.0, ČÚZK (PROJ-data)",
     "refresh": "only if PROJ-data publishes a new version: download it and update tools/geo.py's GRID"},
    {"name": "reference", "globs": ["raw/reference/*"],
     "source": "reference documents (DPP T3 driver's textbook, the user's stop research)",
     "licence": "for private reference only", "refresh": "by hand"},
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


# ---------------------------------------------------------------- the store (sftp)
class Store:
    def __init__(self, spec):
        self.host, _, self.dir = spec.partition(":")
        self.dir = self.dir or "store"

    def run(self, cmds, check=True):
        """One sftp session running cmds (a command prefixed with '-' may fail)."""
        with tempfile.NamedTemporaryFile("w", suffix=".sftp", delete=False, encoding="utf-8") as f:
            f.write("\n".join(cmds) + "\n")
            batch = f.name
        try:
            r = subprocess.run(["sftp", "-q", "-o", "BatchMode=yes", "-b", batch, self.host], cwd=ROOT,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        finally:
            os.remove(batch)
        if check and r.returncode:
            raise SystemExit(f"sftp failed ({r.returncode}): {r.stderr.strip()[:500]}")
        return r.stdout

    def listing(self, kind):
        out = self.run([f'ls -1 "{self.dir}/{kind}"'])
        names = set()
        for line in out.splitlines():
            n = line.strip().rsplit("/", 1)[-1]
            if len(n) == 64 and all(c in "0123456789abcdef" for c in n):
                names.add(n)
        return names

    def upload(self, kind, files):
        """files: [(local path, sha)]; put under a temporary name, then rename (no half files)."""
        if not files:
            return
        cmds = []
        for path, h in files:
            tmp = f"{self.dir}/{kind}/{h}.part"
            cmds += [f'-rm "{tmp}"', f'put "{rel(path)}" "{tmp}"', f'rename "{tmp}" "{self.dir}/{kind}/{h}"']
        total = sum(os.path.getsize(p) for p, _ in files)
        print(f"uploading {len(files)} files, {total / 1e6:.0f} MB ...", flush=True)
        t0 = time.time()
        self.run(cmds)
        print(f"  done in {time.time() - t0:.0f} s ({total / 1e6 / max(1, time.time() - t0):.1f} MB/s)")

    def download(self, kind, items, cache=None):
        """items: [(sha, final local path)]: fetched to a temporary file, checked, then put in place
        (through the machine cache when there is one)."""
        if cache:  # (what the cache already has is only linked)
            here = [(h, p) for h, p in items if cache.has(kind, h)]
            for h, p in here:
                cache.place(kind, h, p)
            if here:
                print(f"{len(here)} files from the cache {cache.root}")
            items = [(h, p) for h, p in items if not cache.has(kind, h)]
        if not items:
            return
        # (inside the project: sftp gets relative paths, and a temp folder on another drive has none)
        tmpdir = tempfile.mkdtemp(prefix=".snap-", dir=ROOT)
        try:
            want = sorted({h for h, _ in items})
            print(f"downloading {len(want)} files ...", flush=True)
            t0 = time.time()
            # (in sessions of 200 files, each retried for what is missing or cut off: one session of 1117
            # files was reset by the server on 2026-10-29)
            good = set()
            for i in range(0, len(want), 200):
                for attempt in range(4):
                    todo = [h for h in want[i:i + 200] if h not in good]
                    if not todo:
                        break
                    if attempt:
                        print(f"  retrying {len(todo)} files", flush=True)
                        time.sleep(5 * attempt)
                    self.run([f'get "{self.dir}/{kind}/{h}" "{rel(os.path.join(tmpdir, h))}"' for h in todo], check=False)
                    for h in todo:
                        p = os.path.join(tmpdir, h)
                        if os.path.exists(p) and sha256(p) == h:
                            good.add(h)
                        elif os.path.exists(p):
                            os.remove(p)  # (cut off: fetched again)
            if bad := [h for h in want if h not in good]:
                raise SystemExit(f"{len(bad)} files not fetched intact from the store (e.g. {kind}/{bad[0]})")
            for h in want:
                if cache:
                    cache.add(kind, h, os.path.join(tmpdir, h))
            if cache:
                cache.protect(os.path.join(cache.root, kind))
            for h, dst in items:
                if cache:
                    cache.place(kind, h, dst)
                else:
                    put(os.path.join(tmpdir, h), dst)
            print(f"  done in {time.time() - t0:.0f} s")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


def put(src, dst):
    """A copy of src at dst, written whole (dst may be a protected link into a cache: replaced, not written)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = f"{dst}.{os.getpid()}.part"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


# ---------------------------------------------------------------- the machine's store cache (#77)
class Cache:
    """A folder every checkout on this computer shares, laid out like the store: sources/<sha256>,
    builds/<sha256>, and unzipped/<zip sha256>/ for the unzipped archives (DTM packages, terrain). Set it with TRAMDATA_CACHE (or
    --cache DIR); without one, files are copied into each checkout as before.

    Its files are hard-linked into the checkouts' raw/ and data/, so an extra checkout costs no space
    and fetches locally. Each cached file denies writing its data (Windows: an ACL entry for this user,
    `icacls /deny user:(WD,AD)`; elsewhere: read-only mode), and that holds through every link: a tool
    writing a linked file in place fails loudly instead of changing every checkout's copy, while the
    tools' temp + rename (tools/atomic.py) replaces only its own link. Linking needs the same volume;
    on another one the files are copied out of the cache (no download, no saving of space)."""

    def __init__(self, root):
        self.root = root
        self.copies = False  # (set once linking failed: another volume)

    @staticmethod
    def open(spec):
        if not spec:
            return None
        root = os.path.abspath(os.path.expanduser(spec))
        try:
            os.makedirs(root, exist_ok=True)
            probe = os.path.join(root, f".probe-{os.getpid()}")
            open(probe, "w").close()
            os.remove(probe)
        except OSError as e:
            print(f"note: the cache {root} is not usable ({e.strerror}): files go into the checkout only")
            return None
        return Cache(root)

    def path(self, kind, h):
        return os.path.join(self.root, kind, h)

    def has(self, kind, h):
        return os.path.isfile(self.path(kind, h))

    def add(self, kind, h, src):
        """A checked file into the cache (copied: src stays where it is)."""
        dst = self.path(kind, h)
        if not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            put(src, dst)

    def adopt(self, kind, h, path):
        """A checkout's own file (just built) into the cache, linked when it can be: the checkout keeps
        it, now protected like any cached file."""
        dst = self.path(kind, h)
        if os.path.exists(dst):
            self.place(kind, h, path)  # (the same bytes are cached already: link to those)
            return
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            os.link(path, dst)
        except OSError:
            put(path, dst)

    def place(self, kind, h, dst, src=None):
        """The cached file at dst: a hard link (or a copy on another volume), replacing what was there."""
        src = src or self.path(kind, h)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst) and os.path.samefile(src, dst):
            return
        tmp = f"{dst}.{os.getpid()}.part"
        if not self.copies:
            try:
                os.link(src, tmp)
                os.replace(tmp, dst)
                return
            except OSError as e:
                self.copies = True
                print(f"note: no hard links from {self.root} to {rel(os.path.dirname(dst))} ({e.strerror}): copying")
        put(src, dst)

    def holds(self, kind, h, p):
        """Whether checkout file p is this cached file (a link: no need to hash it)."""
        c = self.path(kind, h)
        return os.path.exists(p) and os.path.exists(c) and os.path.samefile(p, c)

    def protect(self, folder):
        """Deny writing the data of every file in folder (idempotent; one call per folder)."""
        if not os.path.isdir(folder):
            return
        if os.name == "nt":
            user = os.environ.get("USERNAME") or os.getlogin()
            subprocess.run(["icacls", os.path.join(folder, "*"), "/deny", f"{user}:(WD,AD)", "/Q"],
                           capture_output=True)
        else:
            for f in os.listdir(folder):
                p = os.path.join(folder, f)
                if os.path.isfile(p):
                    os.chmod(p, 0o444)

    def unzipped(self, zh, zpath):
        """The folder with zip zh's members (unzipped once per cache)."""
        d = os.path.join(self.root, "unzipped", zh)
        if not os.path.isdir(d):
            part = f"{d}.{os.getpid()}.part"
            shutil.rmtree(part, ignore_errors=True)
            os.makedirs(part)
            with zipfile.ZipFile(zpath) as zf:
                for n in zf.namelist():
                    if not n.endswith("/"):
                        with zf.open(n) as src, open(os.path.join(part, os.path.basename(n)), "wb") as dst:
                            shutil.copyfileobj(src, dst)
            os.replace(part, d)
            self.protect(d)
        return d

    def prune(self, dry):
        """Remove what no checkout links any more (a file with one link is only the cache's)."""
        n = size = 0
        for kind in ("sources", "builds"):
            d = os.path.join(self.root, kind)
            for f in os.listdir(d) if os.path.isdir(d) else []:
                p = os.path.join(d, f)
                st = os.stat(p)
                if st.st_nlink == 1:
                    n, size = n + 1, size + st.st_size
                    if not dry:
                        os.remove(p)
        u = os.path.join(self.root, "unzipped")
        for z in os.listdir(u) if os.path.isdir(u) else []:
            d = os.path.join(u, z)
            files = [os.path.join(d, f) for f in os.listdir(d)]
            if all(os.stat(p).st_nlink == 1 for p in files):
                n, size = n + len(files), size + sum(os.path.getsize(p) for p in files)
                if not dry:
                    shutil.rmtree(d)
        print(f"cache {self.root}: {n} files, {size / 1e6:.0f} MB linked by no checkout"
              + (" (dry run: nothing removed)" if dry else ": removed"))


# ---------------------------------------------------------------- sources
def scan_sources():
    groups = []
    for g in SOURCES:
        paths = sorted({p for pat in g["globs"] for p in glob.glob(os.path.join(ROOT, pat), recursive=True) if os.path.isfile(p)})
        files = []
        for p in paths:
            st = os.stat(p)
            files.append({"path": rel(p), "size": st.st_size, "sha256": sha256(p),
                          "modified": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))})
        groups.append({k: g[k] for k in ("name", "source", "licence", "refresh")} | {"unzip": bool(g.get("unzip")), "files": files})
    return groups


def current_id():
    p = os.path.join(SNAPDIR, "CURRENT")
    if not os.path.exists(p):
        raise SystemExit("no snapshots/CURRENT")
    return open(p, encoding="utf-8").read().strip()


def load_snapshot(sid):
    p = os.path.join(SNAPDIR, f"{sid}.json")
    if not os.path.exists(p):
        raise SystemExit(f"no snapshot manifest {rel(p)}")
    return json.load(open(p, encoding="utf-8"))


def publish(store, sid, note):
    if os.path.exists(os.path.join(SNAPDIR, f"{sid}.json")):
        raise SystemExit(f"snapshot {sid} exists: choose a new id")
    print("hashing raw/ ...", flush=True)
    groups = scan_sources()
    have = store.listing("sources")
    todo = {}
    for g in groups:
        for f in g["files"]:
            if f["sha256"] not in have:
                todo[f["sha256"]] = os.path.join(ROOT, f["path"])
    store.upload("sources", [(p, h) for h, p in todo.items()])
    os.makedirs(SNAPDIR, exist_ok=True)
    snap = {"id": sid, "created": time.strftime("%Y-%m-%d %H:%M"), "note": note, "groups": groups,
            "files": sum(len(g["files"]) for g in groups), "bytes": sum(f["size"] for g in groups for f in g["files"])}
    json.dump(snap, open(os.path.join(SNAPDIR, f"{sid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(SNAPDIR, "CURRENT"), "w", encoding="utf-8").write(sid + "\n")
    print(f"snapshot {sid}: {snap['files']} files, {snap['bytes'] / 1e6:.0f} MB ({len(todo)} new in the store); "
          f"snapshots/{sid}.json and CURRENT written: commit them")


def is_current(cache, kind, h, size, p):
    """Whether checkout file p holds store file h. With a cache, only a link to the cached file counts (a
    matching copy is swapped for the link), and a matching file the cache lacks is taken into it: a
    checkout fetched before the cache existed fills it without downloading (and its file is protected)."""
    if cache and cache.has(kind, h):
        return cache.holds(kind, h, p)
    ok = os.path.exists(p) and os.path.getsize(p) == size and sha256(p) == h
    if ok and cache:
        cache.adopt(kind, h, p)
    return ok


def fetch(store, sid, cache=None):
    snap = load_snapshot(sid)
    need, unzip = [], []
    for g in snap["groups"]:
        for f in g["files"]:
            p = os.path.join(ROOT, f["path"])
            if not is_current(cache, "sources", f["sha256"], f["size"], p):
                need.append((f["sha256"], p))
            if g.get("unzip") and p.endswith(".zip"):  # (a group's records beside its archives stay as they are)
                unzip.append((f["sha256"], p))
    print(f"snapshot {sid}: {sum(len(g['files']) for g in snap['groups'])} files, {len(need)} to fetch")
    if cache:
        cache.protect(os.path.join(cache.root, "sources"))  # (files taken in from the checkout)
    store.download("sources", need, cache)
    for zh, z in unzip:  # (the street survey: the tools read the .gpkg; the terrain raster's .tif)
        # into a folder named after the package (every district's package holds the same generic
        # ZPS_KR.gpkg / ZPS_OPL.gpkg; tools/dtm.py takes these folders)
        folder = z[:-4] if z.endswith(".zip") else z + ".d"
        os.makedirs(folder, exist_ok=True)
        if cache:  # (unzipped once per cache, linked like the rest)
            d = cache.unzipped(zh, z)
            for n in os.listdir(d):
                cache.place(None, None, os.path.join(folder, n), src=os.path.join(d, n))
            continue
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                out = os.path.join(folder, os.path.basename(n))
                if not os.path.exists(out):
                    print("  unzip", rel(out))
                    with zf.open(n) as src, replacing(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)


def status(sid):
    snap = load_snapshot(sid)
    listed = set()
    bad = []
    for g in snap["groups"]:
        for f in g["files"]:
            listed.add(f["path"])
            p = os.path.join(ROOT, f["path"])
            if not os.path.exists(p):
                bad.append(("missing", f["path"]))
            elif os.path.getsize(p) != f["size"] or sha256(p) != f["sha256"]:
                bad.append(("changed", f["path"]))
    extra = [g2["path"] for g2 in [f for g in scan_sources() for f in g["files"]] if g2["path"] not in listed]
    for k, p in bad:
        print(f"{k:8} {p}")
    for p in extra:
        print(f"new      {p}")
    print(f"snapshot {sid}: {len(bad)} missing/changed, {len(extra)} new input files"
          + ("" if bad or extra else ": raw/ matches"))
    data_status()


# ---------------------------------------------------------------- built data
def data_files():
    d = os.path.join(ROOT, "data")
    return sorted(f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)) and f not in DATA_KEEP)


def data_publish(store, note, sid=None, cache=None):
    files = {}
    for f in data_files():
        p = os.path.join(ROOT, "data", f)
        files[f] = {"size": os.path.getsize(p), "sha256": sha256(p)}
    have = store.listing("builds")
    store.upload("builds", [(os.path.join(ROOT, "data", f), m["sha256"]) for f, m in files.items() if m["sha256"] not in have])
    if cache:  # (other checkouts then fetch this build locally)
        for f, m in files.items():
            cache.adopt("builds", m["sha256"], os.path.join(ROOT, "data", f))
        cache.protect(os.path.join(cache.root, "builds"))
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    man = {"snapshot": sid or (current_id() if os.path.exists(os.path.join(SNAPDIR, "CURRENT")) else None),
           "built_at_commit": head, "published": time.strftime("%Y-%m-%d %H:%M"), "note": note, "files": files}
    with replacing(DATA_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    print(f"data: {len(files)} files, {sum(m['size'] for m in files.values()) / 1e6:.0f} MB; data/MANIFEST.json written: commit it")


def data_fetch(store, cache=None):
    if not os.path.exists(DATA_MANIFEST):
        raise SystemExit("no data/MANIFEST.json")
    man = json.load(open(DATA_MANIFEST, encoding="utf-8"))
    need = []
    for f, m in man["files"].items():
        p = os.path.join(ROOT, "data", f)
        if not is_current(cache, "builds", m["sha256"], m["size"], p):
            need.append((m["sha256"], p))
    print(f"data (snapshot {man.get('snapshot')}, built at {man.get('built_at_commit')}): {len(man['files'])} files, {len(need)} to fetch")
    if cache:
        cache.protect(os.path.join(cache.root, "builds"))
    store.download("builds", need, cache)


def verify(store, sid, base="main"):
    """Check a publish without a fresh checkout (#107): every file of the snapshot and of data/MANIFEST.json
    is listed in the store, and only the new ones (in no earlier snapshot; for builds, not in base's
    manifest) are downloaded to a temporary folder and hashed. A full restore to check 20 new files fetched
    1,137 store objects (#61)."""
    snap = load_snapshot(sid)
    others = set()
    for p in glob.glob(os.path.join(SNAPDIR, "*.json")):
        if os.path.basename(p)[:-5] < sid:  # (ids sort by date: a later one may share this one's new files)
            others |= {f["sha256"] for g in json.load(open(p, encoding="utf-8"))["groups"] for f in g["files"]}
    files = {"sources": {f["sha256"]: f["size"] for g in snap["groups"] for f in g["files"]}}
    old = {"sources": others, "builds": set()}
    if os.path.exists(DATA_MANIFEST):
        files["builds"] = {m["sha256"]: m["size"] for m in json.load(open(DATA_MANIFEST, encoding="utf-8"))["files"].values()}
        r = subprocess.run(["git", "show", f"{base}:data/MANIFEST.json"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            old["builds"] = {m["sha256"] for m in json.loads(r.stdout)["files"].values()}
    bad = 0
    for kind, want in files.items():
        missing = set(want) - store.listing(kind)
        new = sorted(set(want) - old[kind] - missing)
        print(f"{kind}: {len(want)} files, {len(missing)} missing in the store, "
              f"{len(new)} new to check ({sum(want[h] for h in new) / 1e6:.0f} MB)")
        for h in sorted(missing):
            print(f"  missing {kind}/{h}")
        bad += len(missing)
        if new:
            tmp = tempfile.mkdtemp(prefix=".verify-", dir=ROOT)
            try:  # (download checks every hash and stops on a file it cannot fetch intact)
                store.download(kind, [(h, os.path.join(tmp, h)) for h in new])
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    if bad:
        raise SystemExit(f"{bad} files missing in the store")
    print(f"snapshot {sid} and data/MANIFEST.json: in the store, new files intact")


def data_status():
    if not os.path.exists(DATA_MANIFEST):
        print("data: no MANIFEST.json")
        return
    man = json.load(open(DATA_MANIFEST, encoding="utf-8"))
    diff = []
    for f in sorted(set(man["files"]) | set(data_files())):
        p = os.path.join(ROOT, "data", f)
        m = man["files"].get(f)
        if not m:
            diff.append(("new", f))
        elif not os.path.exists(p):
            diff.append(("missing", f))
        elif os.path.getsize(p) != m["size"] or sha256(p) != m["sha256"]:
            diff.append(("changed", f))
    for k, f in diff:
        print(f"{k:8} data/{f}")
    print(f"data: {len(diff)} differences to data/MANIFEST.json" + ("" if diff else ": matches"))


if __name__ == "__main__":
    args = sys.argv[1:]
    opt = lambda k, d=None: args[args.index(k) + 1] if k in args else d  # noqa: E731
    store = Store(opt("--store", os.environ.get("TRAMDATA_STORE", "tramdata:store")))
    cache = None if "--no-cache" in args else Cache.open(opt("--cache", os.environ.get("TRAMDATA_CACHE")))
    cmd = args[0] if args else ""
    if cmd == "fetch":
        fetch(store, opt("--snapshot") or current_id(), cache)
    elif cmd == "publish" and len(args) > 1:
        publish(store, args[1], opt("--note", ""))
    elif cmd == "status":
        status(opt("--snapshot") or current_id())
    elif cmd == "data-publish":
        data_publish(store, opt("--note", ""), opt("--snapshot"), cache)
    elif cmd == "verify":
        verify(store, opt("--snapshot") or current_id(), opt("--base", "main"))
    elif cmd == "data-fetch":
        data_fetch(store, cache)
    elif cmd == "cache-prune":
        if not cache:
            raise SystemExit("no cache: set TRAMDATA_CACHE or pass --cache DIR")
        cache.prune("--dry-run" in args)
    else:
        print(__doc__)
