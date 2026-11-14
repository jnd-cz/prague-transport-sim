# Snapshots

The pinned source snapshots, newest first: what each one added to the one before. Each row goes in with
its `<id>.json` (written by `python -I tools/snapshot.py publish`); `CURRENT` names the one builds read.
How to publish, fetch and verify one: [DATA.md](../DATA.md).

| id | note |
|---|---|
| `2026-11-12s` | `2026-11-12r` + T3M 8088 on line 37 on 2026-11-12, from Strážní to Palmovka with the phone at the end of the second car, in `raw/reference/rides/`, private reference only (#500). Read by `tools/rides_limits.py` and `docs/knowledge.md`, not by a build. |
| `2026-11-12r` | `2026-11-11r` + the user's rides of 2026-11-11 in `raw/reference/rides/`, private reference only (#500): T2R 6003 and T2R 6004 on line 23's diverted route, each with a phone's accelerometer for the whole ride; T3M 8088 (second car) from Strážní to Palmovka on line 37. Read by the ride comparisons in `docs/knowledge.md` and `tools/rides_limits.py`, not by a build. |
| `2026-11-11r` | `2026-11-10` + the four ČKD T3SU manual parts the research sessions never fetched, in `raw/reference/ckd-t3su/`, private reference only, from the user on 2026-11-11 (#493): 07 small motors' maintenance, 11 the pantograph puller, 21 the PA system, 28 fluorescent lighting. The set now has all 29 parts. No build reads them. |
| `2026-11-10` | `2026-11-09r` + ČÚZK DMR 5G under IPR's whole coverage: 2,383 more 500 m tiles at 1 m in `raw/dem/` (2,502 MB, 2,646 in all), downloaded 2026-11-10 by `python -P -E tools/dmr5g.py --under-ipr` (#428; the user, 2026-11-10: "I would still download the full dmr 5g terrain under ipr lidar tiles coverage"). Read by `tools/bench/terrain_compare.py`; the city mesh reads them only where IPR has no ground inside the city (none). |
| `2026-11-09r` | `2026-11-08r` + the user's ride recordings in `raw/reference/rides/`, private reference only (#396): GPS of T3 6921 and T3 6312 on line 23 (2026-10-31), T2R 6004 and T3SUCS 7290 on its diverted route with 11 minutes of a phone's accelerometer (2026-11-07), T3SUCS 7122 westbound and T3 6921 eastbound with two hand-held phone parts (2026-11-08). Read by the ride comparisons in `docs/knowledge.md`, not by a build. |
| `2026-11-08r` | `2026-11-06r` + two VUT Brno theses on rail sanders, written with TriboTec, in `raw/reference/adhesion/`, private reference only, from the user on 2026-11-08 (#266). M. Jíša 2014 surveys sand dosers. M. Matečka 2015 measures tram dosers and gives ČSN 28 1300's minimum tram sand box of 17 dm³. No build reads them. |
| `2026-11-06r` | `2026-11-06c` + the research sessions' documents in `raw/reference/`, private reference only: ČKD's TR 37 manuals and wiring diagram (their site returned 404 on 2026-11-06), DP Praha's tests and D 1/2, theses, adhesion papers, saved web pages, photos; each file's origin in `raw/reference/SOURCES.md` (#353). No build reads them. |
| `2026-11-06c` | `2026-11-06b` + the archive DTM's street furniture points of lines 9, 22, 23 and 37 (`raw/dtmpoints/lineN.json`, `python -P -E tools/dtm_points.py N`), 72,070 points, downloaded 2026-11-06 (#349). |
| `2026-11-06b` | `2026-11-06` with the Geoportál feature answers (walls, trees, tree rows) named per 500 m cell, shared by the lines (`raw/geoportal/cells/`, #326), downloaded 2026-11-06. |
| `2026-11-06` | `2026-11-05b` + OSM Geofabrik 2026-11-04 (was 2026-10-22); 9 more Geoportál answers for lines 9 and 22 (#237). |
| `2026-11-05b` | `2026-11-05` with the ZPS street survey at state 2026-10-31 instead of 2026-09-30 for the 17 districts of lines 9, 17, 22, 23 and 37 (34 packages, 263 MB, `python -I tools/dtm_packages.py --fetch --refresh`): the last state before the JVF 1.5.0.2 switch, schema as September's (#63). |
| `2026-11-05` | `2026-11-03b` + the archive DTM's stop signs along lines 9, 17, 22, 23 and 37, both point layers (`raw/dtmpoints/lineN.signs.json`, `python -P -E tools/dtm_points.py N --signs`, fetched 2026-11-05): the stop sign's second source after the user's (#258). |
| `2026-11-03b` | `2026-11-03` + DI set 7 at state 2026-10-31 for the same 16 districts (#209): Dvorecký most's tracks (2.9 km new, entered 2026-10-07 and 10-22) and records re-entered with heights. |
| `2026-11-03` | `2026-11-02` + 8 Geoportál tiles of line 17's corridor (I3S buildings, trees, tree rows, walls) at its edge, moved by the DI track (#20). |
| `2026-11-02` | `2026-11-01` + IPR Mosty 3D, the whole layer (`raw/geoportal/mosty3d/`, 49 meshes, 672 bridges, `python -I tools/mosty3d.py fetch`): a structure source for track heights (#192). |
| `2026-11-01` | `2026-10-30c` + ZPS 2026-09-30 for lines 9, 23 and 37: 9 more districts (#125). |
| `2026-10-30c` | `2026-10-30b` + IPR Praha's 1 m terrain raster (`raw/ipr-dtm/`, lidar 2023, resampled 2025-07-10), the first level of the terrain chain (#10). |
| `2026-10-30b` | `2026-10-30` + complete archived DTMP tram-axis layer (55010) with Z, IDs, metadata and provenance; assessed as a height fallback in the same 16 DI districts. |
| `2026-10-30` | `2026-10-29c` + DI set 7 JVF packages for the 16 districts crossed by lines 9, 17, 22, 23 and 37 (state 2026-09-30), exact download provenance and provider access/licence evidence. |
| `2026-10-29` | `2026-10-23` + the archived technical map's street furniture points for line 17 (`raw/dtmpoints/`, state 2024-06-30, fetched 2026-10-24). |
| `2026-10-23` | First pinned snapshot: the inputs of the lines built until 2026-10-29 (OSM Geofabrik 2026-10-22, PID GTFS 2026-10-21..11-03, DTM ZPS 2026-09-30, Geoportál and DMR 5G caches of 2026-10-21..23). The data built before it partly came from Overpass caches of 2026-10-21..23; a rebuild from the snapshot may differ slightly there. |
