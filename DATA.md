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
5. **Machine cache** (optional; worth it from the second checkout on, e.g. several agents or worktrees):
   one folder of store files that every checkout on this computer shares. Set the user environment
   variable once, then open a new terminal:
   ```bash
   setx TRAMDATA_CACHE C:\tramdata\cache
   ```
   (Windows: or System Properties → Environment Variables → User variables; elsewhere `export
   TRAMDATA_CACHE=…` in the shell profile; per command `--cache DIR`, or `--no-cache`.) Put it on the
   same drive as the checkouts. Then `fetch` and `data-fetch` download into the cache and hard-link the
   files into `raw/` and `data/`: an extra checkout costs no disk space and fetches without the
   network. The cached files deny writing their data (Windows: an ACL entry, `icacls … /deny
   <user>:(WD,AD)`; elsewhere read-only), through every link: a tool writing such a file in place fails
   with PermissionError instead of changing every checkout's copy. The tools write whole files
   (`tools/atomic.py`: temp + rename), which replaces only the checkout's own link.
   - Not set: files are copied into the checkout, as before.
   - Set but not usable (can't be created or written): a note, then the same as not set.
   - On another drive than the checkout: hard links can't cross drives, so files are copied out of the
     cache (still no download).
   - `python -I tools/snapshot.py cache-prune [--dry-run]` removes cached files that no checkout links
     any more (after deleting a checkout or moving to a new snapshot).

## Everyday use

```bash
python -I tools/snapshot.py data-fetch     # data/ for this commit (data/MANIFEST.json)
python -I tools/snapshot.py fetch          # raw/ for snapshots/CURRENT (~2 GB; unpacks the DTM packages)
python -I tools/snapshot.py status         # local raw/ and data/ against the manifests
```

After pulling a commit that changed `data/MANIFEST.json` or `snapshots/CURRENT`, fetch again (only
changed files are downloaded, or linked from the machine cache).

Tools write `data/` and `raw/` files whole, via `tools/atomic.py` (`with replacing(path, "w") as fh:`),
never in place: a file there may be a protected link into the machine cache.

## Publishing

**Built data** (after rebuilding lines):
```bash
python -I tools/snapshot.py data-publish --note "line 17 rebuilt: …"
python -I tools/snapshot.py verify         # all in the store, the new files fetched back and hashed
git add data/MANIFEST.json && git commit
```
The manifest records the snapshot the build used and the commit it was built at. Commit it together with
the tool changes that produced it.

**A new source snapshot** (new OSM, GTFS, survey packages, …), a deliberate step:
1. Refresh the inputs in `raw/` (each group's `refresh` in the manifest; OSM: download Geofabrik's
   `czech-republic-latest.osm.pbf` + `.md5`, `python -P -E tools/osm_local.py cut <file>`, remove the old
   files; GTFS: `https://data.pid.cz/PID_GTFS.zip`, and adjust `SERVICE_DATE` in `tools/build_line.py`).
   For a DTM refresh, remove the superseded month's ZIPs and extracted package folders for the replaced
   districts from `raw/dtm/` before rebuilding; an available snapshot pair keeps priority over a newer one.
2. Rebuild and check the lines (lints, benches).
3. `python -I tools/snapshot.py publish <YYYY-MM-DD> --note "what changed"`: uploads the new files,
   writes `snapshots/<id>.json` and sets `snapshots/CURRENT`.
4. `data-publish`, then commit `snapshots/` and `data/MANIFEST.json` together.

**Checking a publish:** `python -I tools/snapshot.py verify` (#107). It lists the store once and fetches
back only what this publish added: source files no earlier snapshot in `snapshots/` has, built files not in
`main`'s `data/MANIFEST.json` (`--base REF` for another). Files an earlier snapshot had were checked when
it was published. Don't restore the whole snapshot into a fresh checkout to check a publish: on
2026-10-29c that is 1,117 store objects (~2 GB) against 147 for `verify` (35 s).

Derived files in `raw/` (the OSM answers `build_line.py` caches in `raw/lineN/`, unpacked `.gpkg`) are
not part of a snapshot; they are recomputed from it (each OSM answer is keyed by the extract, its query
and the code of `tools/osm_local.py` and `tools/geo.py`, and recomputed when any of them changes).

## Regional DTM monthly downloads and JVF transition (#63)

**Status checked 2026-10-30:** the two live ZPS indexes each list all **57 Prague districts** and only
state **2026-09-30**. No October (`2026-10-31`) package is listed yet. Existing source and built-data
manifests remain unchanged. Snapshotting a newer month is a separate decision after inspection.

The [regional distribution page](https://portal.dtm-praha-sck.cz/poskytovani-dat) links to Geoportál's
monthly public ZPS packages. [Provider guidance](https://portal.dtm-praha-sck.cz/poskytovani-dat/zpusoby-poskytovani-prazskych-dat-dtm)
lists JVF, DGN, SHP and GPKG; the same four formats are present in both current ZPS indexes.
The [provider's announcement](https://portal.dtm-praha-sck.cz/archiv-zprav?typ=Praha) says monthly
packages have the state of the last calendar day of the month. The month in a filename is the
**data-state date**, not necessarily the export/publication date.

| Set | Content | Catalogue / download page | Website JSON index |
|---|---|---|---|
| 2 | ZPS_OPL, derived surface polygons | [ZPS Sada 2](https://geoportalpraha.cz/data-a-sluzby/225F0FAF-C041-439D-A3B5-B2BADA225683), [downloads](https://geoportalpraha.cz/data-a-sluzby/ke-stazeni/225F0FAF-C041-439D-A3B5-B2BADA225683) | `https://geoportalpraha.cz/api/get-dtm-download-metadata?code=02` |
| 3 | ZPS_KR, drawing lines and points | [ZPS Sada 3](https://geoportalpraha.cz/data-a-sluzby/28A24EB4-5EE8-436E-B0BB-357025258211), [downloads](https://geoportalpraha.cz/data-a-sluzby/ke-stazeni/28A24EB4-5EE8-436E-B0BB-357025258211) | `https://geoportalpraha.cz/api/get-dtm-download-metadata?code=03` |

**When the index or the download server fails** (2026-10-31: both answered 502 for hours, the download
server for every client): wait, or read the index in a browser and save the entries
(`tools/dtm_packages.py --fetch --index FILE`, #125). Requests are never disguised as a browser's.

**Finding each month's UUID:** these are the working JSON endpoints used by the website, rather than
a promised, versioned public API. Each response is an array of districts (`obec`), each containing
`formats`. Select records by `obec_kod`, `format` and `platnost`; use the **returned** `kod_stazeni`,
which contains both UUID and filename. Prepend
`https://isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/`. Do not guess the UUID or replace
the month in an older URL. `soubor_nazev` and `velikost` give the expected filename and byte count.
Current pattern: `VS_CZ010_MOMC_<district>_<yyyymmdd>_ZPS_OPL|KR.gpkg.zip`.

`python -I tools/dtm_packages.py --fetch` does this for every district in `DTM` that lacks a pair in
`raw/dtm/`: the index's newest month, the size checked against `velikost`, the ZIP tested, and the URL
and state recorded in `raw/dtm/provenance.json` (in the `dtm` group). Packages pinned before #125 have
no recorded URL.

For example (PowerShell; the same two requests work with `curl`), stage the latest advertised Praha 2
GPKG and matching JVF header reference **outside raw/** before deciding whether to replace pinned
sources:

```powershell
$dtmStage = 'reports/rebuild/dtm-transition'
New-Item -ItemType Directory -Force -Path $dtmStage | Out-Null
foreach ($dtmSet in @('02', '03')) {
    $dtmRows = Invoke-RestMethod "https://geoportalpraha.cz/api/get-dtm-download-metadata?code=$dtmSet"
    foreach ($dtmFormat in @('GPKG', 'JVF')) {
        $dtmPackage = $dtmRows.formats |
            Where-Object { $_.obec_kod -eq '500089' -and $_.format -eq $dtmFormat } |
            Sort-Object platnost -Descending | Select-Object -First 1
        if (-not $dtmPackage) { throw "No Praha 2 $dtmFormat package in set $dtmSet" }
        $dtmUrl = 'https://isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/' + $dtmPackage.kod_stazeni
        $dtmFile = Join-Path $dtmStage $dtmPackage.soubor_nazev
        Invoke-WebRequest $dtmUrl -OutFile $dtmFile
        if ((Get-Item -LiteralPath $dtmFile).Length -ne [long]$dtmPackage.velikost) { throw 'Download size mismatch' }
        Get-FileHash -Algorithm SHA256 -LiteralPath $dtmFile
    }
}
```

ZPS catalogue records advertise **WMS** map services (`dtm_zps_plochy_seda` and
`dtm_zps_linie_body` under `https://isdtmk.dtm-praha-sck.cz/api/wms/v1/…/service.svc/get`).
The checked provider pages/catalogue records do not identify a public **WFS** download endpoint;
the verified vector-data route here is the package index above. This is not a claim that no WFS
exists elsewhere. E-výdej provides registered, area-specific exports (125 ha free limit); it is not
needed to fetch the public monthly packages. See [access guidance](https://portal.dtm-praha-sck.cz/poskytovani-dat/zpusoby-poskytovani-prazskych-dat-dtm).

**What our tools rely on** in these packages (file and folder names, layer names and type codes,
`UrovenUmisteniObjektuZPS`, geometry types, EPSG:5514) and the measured pre-transition baseline of
the 16 pinned packages: `docs/knowledge.md`, "Regional DTM ZPS packages". The comparison below checks
exactly those.

**Schema inspector and comparison:** stdlib-only, read-only inputs; ZIPs are inspected through
temporary copies. Full names, type codes, columns/types/defaults, geometry declarations/dimensions
and CRS definitions go to the JSON report. Human output groups repeated attribute sets as A1, A2,
etc. XML/JVF input reports its explicit header separately. Exit codes: 0 inspection/identical schema,
1 schema differences, 2 invalid input. Feature contents, hashes and data-state/write dates are
reported separately and do not create false schema differences.

```powershell
python -I tools/dtm_schema.py 'raw/dtm/*500089*.gpkg.zip' --output reports/dtm-praha2-before.json
python -I tools/dtm_schema.py OLD_OPL.gpkg.zip NEW_OPL.gpkg.zip --compare --output reports/dtm-opl-diff.json
python -I tools/dtm_schema.py OLD_KR.gpkg.zip NEW_KR.gpkg.zip --compare --output reports/dtm-kr-diff.json
python -I tools/dtm_schema.py NEW_OPL.jvf.zip NEW_KR.jvf.zip --output reports/dtm-jvf-headers.json
python -I tools/test_dtm_schema.py
```

**Post-transition check remains pending:** the [2026-09-29 provider notice](https://portal.dtm-praha-sck.cz/archiv-zprav?typ=Praha)
stops accepting updates **2026-11-10 22:00** and resumes **2026-11-18 23:59**, accepting only JVF
**1.5.0.2** afterwards (Prague local time). This is a submission-format notice; it does not establish
that monthly GPKG schemas change or that downloads stop during the submission freeze.

After the switch, fetch the first genuinely **newly generated** Praha 2 OPL/KR export and its JVF
companions. A download made on 19 November can still be an old export; check `platnost`, the filename,
`DatumZapisu` and `VerzeJVFDTM`. With monthly publication the first relevant package may arrive later.
Compare both GPKGs against the pinned September archives and record the exact differences and new
header version in #63 and here. If a consumed name, code, attribute, encoding or CRS changes, open a
tool-change issue with the diff. If there are no differences, record that **only for the tested new
exports**. Until those packages exist, no post-1.5 compatibility conclusion has been made.

## Snapshots

| id | note |
|---|---|
| `2026-10-30c` | `2026-10-30b` + IPR Praha's 1 m terrain raster (`raw/ipr-dtm/`, lidar 2023, resampled 2025-07-10), the first level of the terrain chain (#10). |
| `2026-10-30b` | `2026-10-30` + complete archived DTMP tram-axis layer (55010) with Z, IDs, metadata and provenance; assessed as a height fallback in the same 16 DI districts. |
| `2026-10-30` | `2026-10-29c` + DI set 7 JVF packages for the 16 districts crossed by lines 9, 17, 22, 23 and 37 (state 2026-09-30), exact download provenance and provider access/licence evidence. |
| `2026-10-29` | `2026-10-23` + the archived technical map's street furniture points for line 17 (`raw/dtmpoints/`, state 2024-06-30, fetched 2026-10-24). |
| `2026-10-23` | First pinned snapshot: the inputs of the lines built until 2026-10-29 (OSM Geofabrik 2026-10-22, PID GTFS 2026-10-21..11-03, DTM ZPS 2026-09-30, Geoportál and DMR 5G caches of 2026-10-21..23). The data built before it partly came from Overpass caches of 2026-10-21..23; a rebuild from the snapshot may differ slightly there. |

### Transport infrastructure (DI set 7)

Acquisition and offline inspection: `python -P -E tools/dtm_di.py --fetch`, then
`python -P -E tools/dtm_di.py`. It selects districts from both route directions of the five built
lines and the snapshot's OSM district boundaries. Sources go to `raw/dtm-di/`, separately from the
ZPS street survey: public **JVF ZIPs**, catalogue, exact download provenance and provider terms.
The snapshot scanner includes them; the report reads the ZIPs directly, without unpacking or
altering generated line data. [Access/licence distinction and measurements](docs/decisions/2026-10-27-track-source.md#district-acquisition-2026-10-30-61).
The first acquisition is published in snapshot `2026-10-30` (#61).

### IPR 1 m terrain

`python -P -E tools/ipr_dtm.py --fetch` downloads `DTM.zip` (2.05 GB, one BigTIFF) with its catalogue
records and writes `raw/ipr-dtm/provenance.json` (URLs, date, sizes, SHA-256); `fetch` unzips it into
`raw/ipr-dtm/DTM/`. `python -P -E tools/ipr_dtm.py` checks the file's layout and prints a few heights. The
build reads only the tiles it needs. Its datum and what was measured: [source per
layer](docs/decisions/2026-10-30-source-per-layer.md).

### Archived DTMP track heights

`python -P -E tools/dtmp_tracks.py --fetch --acquire-only` acquires the archived tram-axis layer
(`CTMTP_KOD=55010`, MapServer layer 10), preserving the feature-ID inventory, metadata, complete
3D query batches and provenance in `raw/dtmp-tracks/`. `python -P -E tools/dtmp_tracks.py` compares
it offline with DI in the same 16 district export polygons and on both paths of all five lines.
The city-wide archive is only about 15 MB; the assessment clips it to the DI area. Results and the
matching/structure checks are documented in [the fallback assessment](docs/decisions/2026-10-30-track-height-fallback.md).

## The store (admin)

An SFTP-only account `tramdata` on the storage server, chrooted to its folder (`store/sources`,
`store/builds`), keys only. Setup: `ChrootDirectory` owned by root, `ForceCommand internal-sftp`,
`PasswordAuthentication no` in a `Match User tramdata` block of `sshd_config`. Other hosts: pass
`--store HOST:DIR` or set `TRAMDATA_STORE`.

Licences of the stored sources are listed per group in each snapshot manifest; the game's attribution
line repeats them. The store is private: the DPP textbook in `reference/` is for private reference only.
