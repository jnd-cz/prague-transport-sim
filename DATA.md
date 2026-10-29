# Data: source snapshots and built game data

Git holds the code, the tools and small hand-made data (`data/truth.json`). Everything large lives in
the **data store** and is fetched by `tools/snapshot.py`, checked by SHA-256:

| what | in git | in the store | needed for |
|---|---|---|---|
| raw sources (`raw/`): OSM, GTFS, street survey, Geoportál, terrain, imagery | `snapshots/<id>.json` (manifest), `snapshots/CURRENT` | `store/sources/<sha256>` | building the world |
| built game data (`data/`, except `truth.json`) | `data/MANIFEST.json` | `store/builds/<sha256>` | playing, tuning the engine, lints |

Files are stored by their hash, so one that did not change between snapshots or builds is stored once.

## Why snapshots

Most sources keep no history: PID GTFS, the Geoportál services and ČÚZK's terrain service always serve
today's state, Geofabrik keeps dated OSM files only for a while, and newer district packages replace the
DTM ones. A **snapshot** pins the exact input files, with where and when each came from
(`snapshots/<id>.json`: per group `source`, `licence`, `refresh`, per file `path`, `size`, `sha256`), so
every computer builds the same world. The OSM data is the snapshot's extract (`raw/osm/`), not Overpass
queries.

## One-time setup on a computer

1. **SSH key** for the store (Windows 10/11 has OpenSSH; Git Bash or PowerShell):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/tramdata_ed25519 -C "tramdata@<computer-name>"
   ```
   Send the `.pub` line to the store's admin: it goes into the `tramdata` account's
   `authorized_keys` (one line per computer; delete the line to revoke it).
2. **SSH config** (`~/.ssh/config`). The store's address, port and host key are not public: the
   maintainer shares them privately with each contributor who gets access.
   ```
   Host tramdata
       HostName <store host>
       Port <store port>
       User tramdata
       IdentityFile ~/.ssh/tramdata_ed25519
       IdentitiesOnly yes
       PasswordAuthentication no
   ```
   Check the server's key on first connection against the fingerprint you were given.
   Test: `sftp tramdata` then `ls store` lists `sources` and `builds`.
3. **Git identity** in the clone: `git config user.email "2506000+jnd-cz@users.noreply.github.com"`.
4. **Python** 3.12+; the OSM tools need pyosmium (`python -m pip install --user osmium`) and run with
   `python -P -E` (`-I` hides the user site-packages); the build tools need pyproj, shapely, numpy, Pillow;
   the headless checks need Playwright (`python -m pip install --user playwright`, then
   `python -m playwright install chromium`).

## Everyday use

```bash
python -I tools/snapshot.py data-fetch     # data/ for this commit (data/MANIFEST.json)
python -I tools/snapshot.py fetch          # raw/ for snapshots/CURRENT (~2 GB; unpacks the DTM packages)
python -I tools/snapshot.py status         # local raw/ and data/ against the manifests
```

After pulling a commit that changed `data/MANIFEST.json` or `snapshots/CURRENT`, fetch again (only
changed files are downloaded).

## Publishing

**Built data** (after rebuilding lines):
```bash
python -I tools/snapshot.py data-publish --note "line 17 rebuilt: …"
git add data/MANIFEST.json && git commit
```
The manifest records the snapshot the build used and the commit it was built at. Commit it together with
the tool changes that produced it.

**A new source snapshot** (new OSM, GTFS, survey packages, …), a deliberate step:
1. Refresh the inputs in `raw/` (each group's `refresh` in the manifest; OSM: download Geofabrik's
   `czech-republic-latest.osm.pbf` + `.md5`, `python -P -E tools/osm_local.py cut <file>`, remove the old
   files; GTFS: `https://data.pid.cz/PID_GTFS.zip`, and adjust `SERVICE_DATE` in `tools/build_line.py`).
2. Rebuild and check the lines (lints, benches).
3. `python -I tools/snapshot.py publish <YYYY-MM-DD> --note "what changed"`: uploads the new files,
   writes `snapshots/<id>.json` and sets `snapshots/CURRENT`.
4. `data-publish`, then commit `snapshots/` and `data/MANIFEST.json` together.

Derived files in `raw/` (the OSM answers `build_line.py` caches in `raw/lineN/`, unpacked `.gpkg`) are
not part of a snapshot; they are recomputed from it (each OSM answer is marked with the extract it came
from and recomputed when that changes).

## Snapshots

| id | note |
|---|---|
| `2026-10-29` | `2026-10-23` + the archived technical map's street furniture points for line 17 (`raw/dtmpoints/`, state 2024-06-30, fetched 2026-10-24). |
| `2026-10-23` | First pinned snapshot: the inputs of the lines built until 2026-10-29 (OSM Geofabrik 2026-10-22, PID GTFS 2026-10-21..11-03, DTM ZPS 2026-09-30, Geoportál and DMR 5G caches of 2026-10-21..23). The data built before it partly came from Overpass caches of 2026-10-21..23; a rebuild from the snapshot may differ slightly there. |

## The store (admin)

An SFTP-only account `tramdata` on the storage server, chrooted to its folder (`store/sources`,
`store/builds`), keys only. Setup: `ChrootDirectory` owned by root, `ForceCommand internal-sftp`,
`PasswordAuthentication no` in a `Match User tramdata` block of `sshd_config`. Other hosts: pass
`--store HOST:DIR` or set `TRAMDATA_STORE`.

Licences of the stored sources are listed per group in each snapshot manifest; the game's attribution
line repeats them. The store is private: the DPP textbook in `reference/` is for private reference only.
