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
Options: --store HOST:DIR (default tramdata:store, or $TRAMDATA_STORE).

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
    {"name": "dtm", "globs": ["raw/dtm/*.zip"], "unzip": True,
     "source": "Prague digital technical map, ZPS district packages (isdtmk.dtm-praha-sck.cz, OPL + KR)",
     "licence": "CC BY 4.0, datový podklad © IPR Praha / DTM Praha",
     "refresh": "download the districts' *_ZPS_OPL / *_ZPS_KR .gpkg.zip (README: DTM), fetch unzips them"},
    {"name": "geoportal", "globs": ["raw/geoportal/**/*"],
     "source": "Geoportál Praha services: Budovy 3D, Mosty 3D (I3S), opěrné zdi, stromy (tools/geoportal.py caches)",
     "licence": "CC BY 4.0, datový podklad © IPR Praha",
     "refresh": "delete raw/geoportal/lineN and run python -I tools/geoportal.py --line N"},
    {"name": "dem", "globs": ["raw/dem/*.tif", "raw/terrain.tif", "raw/terrain.json", "raw/line*/terrain.tif",
                              "raw/line*/terrain.json", "raw/run*/terrain.tif", "raw/run*/terrain.json"],
     "source": "ČÚZK DMR 5G ImageServer exports (fine terrain tiles: tools/fine_terrain.py; line grids: build_line.py)",
     "licence": "CC BY 4.0, ČÚZK",
     "refresh": "delete the tiles / terrain.* and rerun the tools"},
    {"name": "ortho", "globs": ["raw/ortho/*"],
     "source": "IPR Praha orthophoto, leaf-off flight 2026 (ImageServer, tools/ortho_lanes.py tiles)",
     "licence": "CC BY 4.0, IPR Praha", "refresh": "rerun tools/ortho_lanes.py"},
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

    def download(self, kind, items):
        """items: [(sha, final local path)]: fetched to a temporary file, checked, moved in place."""
        if not items:
            return
        # (inside the project: sftp gets relative paths, and a temp folder on another drive has none)
        tmpdir = tempfile.mkdtemp(prefix=".snap-", dir=ROOT)
        try:
            cmds = [f'get "{self.dir}/{kind}/{h}" "{rel(os.path.join(tmpdir, h))}"' for h, _ in {h: p for h, p in items}.items()]
            print(f"downloading {len(cmds)} files ...", flush=True)
            t0 = time.time()
            self.run(cmds)
            for h, dst in items:
                src = os.path.join(tmpdir, h)
                if sha256(src) != h:
                    raise SystemExit(f"hash mismatch for {rel(dst)} (store file {h})")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copyfile(src, dst)
            print(f"  done in {time.time() - t0:.0f} s")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


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


def fetch(store, sid):
    snap = load_snapshot(sid)
    need, unzip = [], []
    for g in snap["groups"]:
        for f in g["files"]:
            p = os.path.join(ROOT, f["path"])
            if not (os.path.exists(p) and os.path.getsize(p) == f["size"] and sha256(p) == f["sha256"]):
                need.append((f["sha256"], p))
            if g.get("unzip"):
                unzip.append(p)
    print(f"snapshot {sid}: {sum(len(g['files']) for g in snap['groups'])} files, {len(need)} to fetch")
    store.download("sources", need)
    for z in unzip:  # (the street survey: the tools read the .gpkg)
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                out = os.path.join(os.path.dirname(z), os.path.basename(n))
                if not os.path.exists(out):
                    print("  unzip", rel(out))
                    with zf.open(n) as src, open(out, "wb") as dst:
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


def data_publish(store, note, sid=None):
    files = {}
    for f in data_files():
        p = os.path.join(ROOT, "data", f)
        files[f] = {"size": os.path.getsize(p), "sha256": sha256(p)}
    have = store.listing("builds")
    store.upload("builds", [(os.path.join(ROOT, "data", f), m["sha256"]) for f, m in files.items() if m["sha256"] not in have])
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    man = {"snapshot": sid or (current_id() if os.path.exists(os.path.join(SNAPDIR, "CURRENT")) else None),
           "built_at_commit": head, "published": time.strftime("%Y-%m-%d %H:%M"), "note": note, "files": files}
    json.dump(man, open(DATA_MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"data: {len(files)} files, {sum(m['size'] for m in files.values()) / 1e6:.0f} MB; data/MANIFEST.json written: commit it")


def data_fetch(store):
    if not os.path.exists(DATA_MANIFEST):
        raise SystemExit("no data/MANIFEST.json")
    man = json.load(open(DATA_MANIFEST, encoding="utf-8"))
    need = []
    for f, m in man["files"].items():
        p = os.path.join(ROOT, "data", f)
        if not (os.path.exists(p) and os.path.getsize(p) == m["size"] and sha256(p) == m["sha256"]):
            need.append((m["sha256"], p))
    print(f"data (snapshot {man.get('snapshot')}, built at {man.get('built_at_commit')}): {len(man['files'])} files, {len(need)} to fetch")
    store.download("builds", need)


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
    cmd = args[0] if args else ""
    if cmd == "fetch":
        fetch(store, opt("--snapshot") or current_id())
    elif cmd == "publish" and len(args) > 1:
        publish(store, args[1], opt("--note", ""))
    elif cmd == "status":
        status(opt("--snapshot") or current_id())
    elif cmd == "data-publish":
        data_publish(store, opt("--note", ""), opt("--snapshot"))
    elif cmd == "data-fetch":
        data_fetch(store)
    else:
        print(__doc__)
