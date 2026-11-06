# Snapshots

The pinned source snapshots, newest first: what each one added to the one before. Each row goes in with
its `<id>.json` (written by `python -I tools/snapshot.py publish`); `CURRENT` names the one builds read.
How to publish, fetch and verify one: [DATA.md](../DATA.md).

| id | note |
|---|---|
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
