# Knowledge: data quirks, conventions, why the heuristics exist

What sessions learned and later work needs. Kept current and short; the full logs are in
[history/](history/) (HANDOFF.md §n, REMOTE-CHANGES.md §n). Tasks are GitHub issues, not here.

## Coordinates and heights

- **The city frame** (`tools/geo.py`, every tool; [decision](decisions/2026-10-29-city-frame-and-tiles.md)):
  game metres = S-JTSK (EPSG:5514) minus the Marian column (−742 806, −1 043 024); every line shares it
  (`data/lineN.json` `frame`). Lat/lon goes through ČÚZK's grid as a pinned PROJ pipeline (the grid file
  is in the snapshot, `raw/proj/`); survey data (DTM, DMR 5G, IPR rasters) is a plain shift. S-JTSK is
  9.6 cm/km short of true length, and grid north is 7.8° off true north.
- Until 2026-10-29 each line had its own lat/lon origin and a flat-earth scale (110 574 m per degree of
  latitude, 111 320·cos(lat0) of longitude): 0.59 % short N–S, 0.20 % E–W (line 17 was 100 m short), so
  positions quoted in older notes (route `s`, x/y) are off by up to that much.
- **Layer registration** (`tools/registration.py --line 17|22`, against the DTM survey; 2026-10-29): IPR LOD2
  buildings 0.04–0.10 m, OSM buildings 0.06–0.10 m, trees 0.2–0.3 m, tree rows 0.16 m from the trees.
  IPR's hosted feature layers are stored in Web Mercator, and each was loaded from S-JTSK with its own
  datum shift: the **tree register's lat/lon is ~10 m off** (ask its service for S-JTSK, `outSR=5514`,
  which `geoportal.py` does), while the tree rows and the archived DTM street points are right as
  lat/lon (asking those for S-JTSK puts them 6–10 m off). A new Geoportál layer gets measured both ways
  before use.
- **Heights are Bpv** (Baltic after adjustment) in DMR 5G, the DTM survey and Mosty 3D alike: measured,
  the model tops sit 0–0.5 m over the surveyed decks (an ellipsoid mix-up would be ~45 m).
- Geoportál I3S layers are Web Mercator with absolute heights; the orthophoto ImageServer is S-JTSK.
- The track ribbon is drawn 0.20 m (bed) and 0.26 m (rails) over the profile height: rendering offsets
  to redefine with "what each height means" (M2).
- Bpv vs EVRF2007 in Prague: 0.13 m (ČÚZK's `vertoffset` in PROJ, EPSG:8357 → 5621).

## Sources and their quirks

- **OSM** (local extract only, [decision](decisions/2026-10-23-local-osm-extract.md)): route relations
  PTv2; track ways are merged into chains split only at junctions and bridge ends (no smoothing kinks).
  Tunnels from `tunnel`, `covered=yes`, negative `layer`. OSM splits tunnels and bridges into many ways:
  heights must run along the whole chain (`chainTunnels`), or inner ends take the hill top or the river.
  Interlaced track is tagged `railway:interlaced=yes` (Letenská).
- **Switch detection** (facing only): a route node with an extra track neighbour heading forward; a
  neighbour on a track passing straight through is a diamond crossing (line 22: 16 of 33 "switches").
- **PID GTFS**, service date fixed at 2026-10-21. Line 22 needs `--headsign "Zahradní Město"`. Line 9 is
  built as a 9 → 10 run. Line 37 (a substitute line) has no OSM relation: built from its GTFS shapes,
  which run between the two tracks in places; the matcher prefers the right-hand track (regular
  service always uses it, `data/truth.json`).
- **PID GTFS `block_id` links through-running trips only** (older notes said it had none): on
  2026-10-21 each of line 9's 427 blocks is one 9 trip and the 10 trip it becomes, and lines 17, 22,
  23 and 37 have no `block_id` at all. It is not a vehicle's day (no run numbers, no depot runs).
  A two-line run pairs trips by it, never by time (#96): 195 of 200 line 9 arrivals at Nákladové
  nádraží Žižkov continue as line 10 with a 0 s gap; the old 2–25 min time window had paired 198, none
  in the same block. `tools/audit_run_timetable.py` checks a built run against the GTFS.
- **A two-line run's `pathBack` holds both directions** of the streets the run covers twice (9 → 10
  leaves Řepy and returns to it over the same tracks: s 0–8 km and 20–28 km): the closest piece of it can be our own track. Matching
  onto another route takes the heading into account (`Route.nearestOnHeading`); plain `nearest` there
  spawned oncoming trams on our track and made two false 8 km gauntlets on line 9 (28 signals lost).
- **Sources per layer** ([decision](decisions/2026-10-30-source-per-layer.md)): the order and dates are in
  `tools/sources.py`; every built file says per list where its features came from (`provenance`, `fb`).
- **IPR 1 m terrain** (`tools/ipr_dtm.py`): bare earth from the 2023 lidar, one 2 GB BigTIFF (tiled,
  LZW). Its cell centres sit 0.72 m / 0.61 m off the S-JTSK metre grid (sampled bilinear, never copied);
  it states no datum, and measures Bpv (+0.016 m over the ZPS street lines on line 17, ±0.03 m against
  DMR 5G per line; a Bpv / EVRF2007 mix-up is 0.13 m). The fine 2 m blocks within 120 m of the tracks
  come from it (`tools/fine_terrain.py`, `?nofine`). It has no covers over passages (underpasses,
  culverts: bare earth shows the passage); near OSM passages DMR 5G, which kept them, takes over.
- **ČÚZK DMR 5G**: bare-earth lidar (embankments over underpasses are in it), 2 m TIN raster; the coarse
  10 m grid of a line, and the fine blocks' fallback where IPR has no data.
- **Prague DTM / ZPS survey** (street areas, kerbs, points): all of line 17, part of 22. Its vertices are
  far apart (big river triangles), so terrain is lowered vertex by vertex under surveyed areas.
- **A kerb is one 3D line in the ZPS survey**, with one height, shared by the road's and the sidewalk's
  outlines (`Hranice dopravní stavby nebo plochy`; a second line one kerb higher lies within 0.6 m at 4 %
  of them). Measured with IPR 1.5 m to either side (#21): along sidewalks it is the kerb's **foot**
  (road −0.005 / +0.006 m, sidewalk +0.095 / +0.109 m on lines 17 / 22); along line 17's platforms the
  **top** (+0.17 m over the road). The sidewalks' far edges lie +0.100 m over the foot: sidewalks are
  nearly flat across (a 2 % crossfall would leave 2–3 cm kerbs).
- **Street surfaces from the survey**: smoothing fits through the outline vertices (on straight kerbs only
  the corners, tens of metres apart) wave by ±0.5–1 m over 15–30 m; linear between the surveyed vertices
  is the smoothest surface (line 17: 3.6 % of samples over 8 cm against 7.3 % for the old street
  model, #21).
- **Track heights against each other** (#106 staging, 2026-10-31, where DI has Z): the archive minus DI
  median 0.00 m, p90 +0.04 (n 71 727); DI minus the surveyed tram area + style offset +0.02 m (p10–p90
  −0.09…+0.20, n 6 964) and minus surveyed road +0.04 m: these samples are street track. On open track
  the tram area's surveyed outline is its edges, not rail level (line 17 Levského – Přístaviště: archive
  +0.4…+0.9 m over it). DI minus surveyed green surface +0.22 m (n 219): the survey there is probably the
  track bed, not the grass.
- **IPR Geoportál** (CC BY 4.0): LOD2 buildings (untextured, gzipped I3S, we read the non-Draco buffer:
  breaks if IPR goes Draco-only), retaining walls with `vyska` (which side is retained is not in the
  data), tree register (multipoint) and tree rows.
- **Mosty 3D**: photogrammetry 2001–2008, ±0.5 m, blocks from the highest surface seen from the air
  (parapets) down; can predate rebuilds. **The survey deck wins wherever it exists**; the model gives
  sides, piers and spans elsewhere, and is trimmed over surveyed decks.
- **Regional DTM ZPS packages: what our tools rely on** (`tools/dtm.py`, `tools/gpkg.py`,
  `tools/registration.py`; audit of the 16 pinned packages of 2026-09-30, #63). What to compare after a
  format change (JVF 1.5.0.2 from 18 Nov 2026; refresh steps in DATA.md):
  - Files: each ZIP holds exactly `ZPS_OPL.gpkg` or `ZPS_KR.gpkg`; `fetch` unzips into the archive's
    name without `.zip`. `tools/dtm_packages.py` selects one OPL/KR month per district for the import,
    registration and rebuild: CURRENT's `dtm` group wins; unpinned districts use the newest local date
    with a warning when several are present. If the pinned pair is unavailable, a newer local month
    may be used with a snapshot/month warning for rebuild-before-publish refreshes; incomplete pairs fail.
  - Layers: classified by the type code, `table.split('#')[-1].split('_')[0]` (the codes in `dtm.py`'s
    table; registration matches a table ending in the code or containing `#<code>_`). Full names matter
    too: height lines need `Hranice` in the name. (The ground-height cloud built from the
    `Hranice_dopravní_stavby_nebo_plochy` … `Terénní_hrana` lines was retired in #21: surfaces are
    linear between their surveyed vertices.)
  - Attributes: only `UrovenUmisteniObjektuZPS` (nullable INTEGER on 981 of the 1,062 layers, absent on
    81; absent or null = level 0). The geometry column is found from `gpkg_geometry_columns` (now
    `shape`).
  - Geometry: OPL polygons / multipolygons (XY); KR line strings with Z (boundary heights) and points
    (registration). `gpkg.py`'s WKB reader takes base types 1–7 with ISO / EWKB Z and M (M dropped) and
    envelope codes 0–4: curved types would need work.
  - CRS: everything is EPSG:5514 metres, M = 0, and no tool reprojects or rejects another CRS.
  - Per district (OPL polygon / KR line / KR point layers): Praha 1 50/28/61, 2 43/26/52, 4 49/28/60,
    7 45/28/56, 8 53/29/63, 10 49/27/62, 12 50/29/58, 17 43/26/47.
  - Versions: the GPKG `user_version` 10301 is GeoPackage 1.3.1, not the JVF version. The GPKG ZIPs
    carry no JVF header; the matching Praha 2 JVF packages say `VerzeJVFDTM=1.4.3`,
    `DatumZapisu=2026-10-01` (OPL SHA-256 `ba86e8f6…`, KR `3384bf02…`; not in the snapshot).
- **OSM `maxheight`** under the route gives underpass clearances (`tools/clearances.py`; default 4.2 m
  car roads, 2.5 m footways), applied only where the track is already ≥ 2 m over the road.
- Tatra T3 figures (ČKD pamphlet, unverified): 16 t empty, 4 × 40 kW, ~39 kN, 1.8 m/s² service accel and
  brake, 5 m/s² emergency, 24 seated + 86 standing.
- T3s can meet anywhere in the Prague network, tight curves included (user, 2026-10-30): a tram/tram
  overlap between T3s is a geometry error (track spacing), not a place where they must not meet. A few
  tight places forbid KT8 and T3R.PLF from meeting; that matters once those models exist.
- Prague signals: 4 white lamps on a white plate (stop = outer two), call box with three orange LED bars,
  distant signal with a yellow "P"; switch indicator a red LED chevron on the span wire.

## Heuristics that stand in for missing data

Review these when realism matters; most move into the build in M2.
- **Signals**: from OSM `traffic_signals` clusters near the route; never past the crossing they were
  made for (except along platforms, where the platform-head rules decide); two at one stop line are one.
  GO held for a tram in its dilemma zone (15 + v²/1.6 m). Distant signals where R < 110 m within 140 m.
- **Gauntlets**: opposite route < 1.8 m away for ≥ 25 m along one continuous opposing traversal
  (needs exact `Route.nearest`, which refines onto the chords: 4 m samples read 0.3 m tracks as up to
  1.9 m apart).
- **Contacts** at switch − 22 m (real positions unknown), worked by the pantograph, moved out of stop
  zones and signal queues; all switches manual on purpose (driver skill).
- **Catenary poles** march out past tracks and carriageway to the kerb; a building within 5.5 m gets a
  wall rosette, else bracket arms.
- **Tram streets**: a road within 2.6 m of a track over 60 % of its length is widened 3.2 m per track.
- **Vienna-type stops**: carriageway on the doors' side 2.2–3.4 m from the track along the stop (the
  tram bed is not a car lane); facts per stop and direction in `truth.json` `stopTypes`.
- **Bridges on the model deck**: on tagged spans with model samples, the model deck is fixed like a
  surveyed bed (floor and ceiling, ±3.3 m sideways search on our own bridges); not on surveyed beds.
- **Tunnel mouths**: chains < 60 m are open roads; longer ones get a portal with a 24 m throat, heights
  from the approach road, the terrain re-covered over it.
- **Trees** ≥ 3.2 m from a track, crowns ≥ 1.9 m; **LOD2 buildings** within 2.5 m of the route lifted to
  track + 6.3 m (passages like Letenská).
- **Speed limits** from curvature, posted OSM speeds and switches; stop zone −20…+12 m; adhesion dry
  0.30, rain 0.17, leaves 0.15; demand peaks 7–9:30 and 15:30–17:30.
- **Traffic**: cars wait at the track only while the tram's body is on the crossing or it is about to
  arrive (16 m / 4 s); AI trams ahead run at the limit, spawned 700–1300 m ahead, board 6–8 s when ours
  is within 300 m; oncoming trams stop at the far end of their own platform.

## Checks and what they measure

- `tools/lint.js` (page with `?keepgeo`): consist at stops, signals in platforms (exempts island-tip
  poles marked at placement and heads hung over the track), trees in buildings, bridges, invented walls, tram
  envelope, grade separation, railSupport, verticalCurves, terrainOverSurvey, streetWaviness,
  `deckClip` (ray down against drawn buildings and bridges), `underpassClearance`, lanes, street bot.
- `lint({ traffic: true })` / `tools/traffic_lint.js`: slide, jump, overlap, walker hits, red runs;
  averages seeds 22, 7, 1234; a run that does not finish is a jam (follow `car.seen.car`).
- `tools/bench/`: u3 (signals, junctions, collisions), redruns, walkers, heads; `batch.html` runs them.
- Line 17's full lint after the merge is the pre-rebuild reference (`reports/line17.json`).

## Environment (Windows dev machines)

- Python `-I` ignores `PYTHONIOENCODING`: scripts call `sys.stdout.reconfigure(encoding="utf-8")`.
- Shell heredocs with quotes or backticks break: write scripts to a file.
- ES modules are cached hard: the dev server sends `no-store`; import tools with `?v=` + `Date.now()`.
- A full listen backlog refuses connections on Windows (Linux queues them). Python's HTTP server
  defaults to 5, which several pages loading their ~20 modules at once overflow: every page hung on
  "Loading the 3D engine" (`ERR_CONNECTION_REFUSED`). `tools/serve.py` sets 128; a `headless.py --jobs N
  --url` server needs the same.
- Browser script calls time out at 45 s; a hidden pane throttles `requestAnimationFrame`, so step the
  simulation in JS (`window.headless`) rather than waiting in real time.
- Memory: the whole line is built at load (no streaming); fine terrain adds ~0.15–0.2 GB.
- The `gh` CLI lives in `C:\Program Files\GitHub CLI` (not always on the Bash PATH).
