# Track geometry and elevation: research decision and handoff

> Moved 2026-10-29 into docs/decisions/. Other documents it names: TRACK-DATA-DECISION → [2026-10-27-track-source.md](2026-10-27-track-source.md); PLAN, BUILD-TOOLS-HANDOFF, REMOTE-CHANGES → [../history/](../history/).

**Date:** 2026-10-27  
**Status:** agreed direction; research and comparison only, not implemented in the game.  
**Scope:** Prague tram-track placement, depot coverage and heights. Metro and railway observations are included where relevant. The measured game is the line 17 code and data in `transport-game-remote-2026-10-24.zip`; this is a deployed copy without the original build tools, raw caches or Git history.

## Decision

Use the **current Prague DTM transport-infrastructure tram track centrelines** as the preferred source for track geometry where the relevant record is current, usable and consistent with the actual network. Use the older Prague technical-map track layer and OpenStreetMap (OSM) to fill confirmed gaps, preserving useful depot, siding and other track coverage.

This is a source preference, not a blind union. Rebuilding can move or remove a track. A newer extract or record-update timestamp does not necessarily mean the underlying geometry was surveyed more recently. Before importing an older or unmatched line, compare its observation/survey and change dates, status, position, connectivity and available recent imagery or other evidence. Suppress or flag an obsolete alignment; do not automatically add it as a second physical track. OSM may be the more current source at a particular location. If currency or identity cannot be resolved, retain the uncertainty for review instead of inventing a connection.

The decision is about **horizontal track centrelines and network coverage**. Height selection and visual integration remain separate tasks; no terrain or rail-height change has been approved or implemented as part of this research.

## Why this matters: Kobylisy–Vozovna Kobylisy

The principal issue is the horizontal position of **both** tracks, their spacing and unwanted lateral kinks on a largely straight north–south section, rather than just elevation above sea level.

At cross sections every 5 m on the roughly 200 m of line between 300 and 500 m from the Kobylisy stop, north of Březiněveská:

| Source / processing stage | Measured track centre-to-centre spacing |
| --- | --- |
| Current DTM | approximately 3.49–3.52 m |
| Live OSM | approximately 2.53–3.31 m |
| Current game after its spacing adjustment and drawing smooth | approximately 3.00–3.31 m |

At one cross section about 220 m from Kobylisy (roughly 41 m before Březiněveská), the DTM pair is about 3.38 m apart, OSM about 2.44 m, and the adjusted game pair about 3.00 m. These are **distances between track centrelines, not rail gauge**. Cross sections were taken perpendicular to the game’s driven route; tracks were paired geometrically. Avoid applying the pairing method blindly at switches, crossings, diverging routes, depots or grade-separated structures.

The game’s `src/trackfix.js` currently moves the opposite-direction OSM track outward in some places to achieve a 3 m minimum; `src/world.js` then smooths the drawn tracks. The original OSM spacing varies, and the adjustment changes the shape further. The measured examples support a geometry problem; they do not isolate every visible kink to one processing step or independently establish absolute survey accuracy. The current and older Prague maps often agree but may share provenance.

A previous game-to-DTM horizontal median of about **0.147 m** measured the driven route against a nearest DTM line. It does **not** establish that the opposite track or the two-track spacing is accurate. The paired-track comparison above is the relevant finding for the observed issue.

Near the Vozovna loop, junctions and multiple parallel tracks require explicit track-by-track and connection matching before drawing the same conclusion. Existing smoothing must not create or erase switch branches or force genuinely diverging tracks to remain parallel.

## Coverage and data status

- Current public DTM transport-infrastructure data is supplied by district. The Praha 8 package examined was the **2026-09-30** snapshot. The full comparison rectangle included **339 current DTM tram features**: 278 all-zero Z, 59 with plausible numeric Z and two mixed; all carried an incomplete-data flag. These are segmented features, not 339 physical tracks. The package covers 99.67% of the rectangle; its uncovered corner contained no OSM tram way in the extract. Do not infer that all possible track data or all missing depot lines are present.
- The older Prague technical-map centreline layer returned 301 tram features with plausible numeric heights in this rectangle; OSM returned 80 active tram ways and no `ele` on the ways or fetched nodes. Results depend on the area and filters; numeric Z values alone do not prove survey accuracy or physical track status.
- Depo Hostivař shows why all sources matter. The current DTM extract contains the 2022 terminal tram loop and plausible track heights there, while the fetched OSM extract included broader metro-depot and railway-yard linework. Track records from one source can be absent or represent a different date, scope or classification in another. Treat zero Z as missing/suspect, not sea level; inspect mixed Z and flags individually.
- Maintain provenance per geometry and per height: provider, dataset and feature ID, extraction date, available observation/update dates, quality and incomplete flags, height source, coordinate system and confidence/review status. DTM owner identifiers and the operator can help interpret records, but ownership alone is not proof of current physical status.

## District acquisition, 2026-10-30 (#61)

**Published in source snapshot `2026-10-30`, with the user's approval.** The game and its built
data are unchanged. Importing these tracks is [#20](https://github.com/jnd-cz/prague-transport-sim/issues/20).

### Access, formats and the HANDOFF contradiction

The distinction is between the catalogue's **open-data classification**, **public download access**,
and the format offered. Checked on 2026-10-30:

- The [set 7 catalogue record](https://geoportalpraha.cz/data-a-sluzby/50DF58EE-2B3B-42B7-A414-3D2809159B8C)
  still has `openData=false`, `eVydej=true`, `dtmDatasetCode=07`, data date 2026-09-30 and metadata
  update 2026-10-23. This explains HANDOFF §13's *Neotevřená data* observation; the flag was not invented.
- The [regional provider's access guidance](https://portal.dtm-praha-sck.cz/poskytovani-dat/zpusoby-poskytovani-prazskych-dat-dtm)
  describes ZPS and DI as public, with monthly district downloads under its open-data heading. Its
  [distribution overview](https://portal.dtm-praha-sck.cz/poskytovani-dat) mentions only ZPS for the
  Geoportál package route, so the provider's own pages are inconsistent too.
- The Geoportál's [actual set 7 download index](https://geoportalpraha.cz/api/get-dtm-download-metadata?code=07)
  lists 57 Prague districts, **JVF ZIP only**, all state 2026-09-30. The listed
  `isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/<uuid>/<filename>` links work without login.
  The 16 required ZIPs were downloaded, checked against the listed byte sizes and ZIP CRCs, and
  hashed. They contain XML, JVF **1.4.3**, horizontal **EPSG:5514** and three coordinates per track
  vertex. The catalogue identifies the vertical reference as Baltic 1977 height. The format menu's
  absence of GPKG matters: do not invent a `.gpkg.zip` URL from a JVF URL or call these ZPS packages.
- Licence basis for these publicly served packages: IPR's
  [data-provision rules](https://geoportalpraha.cz/backend/getdokument/1), approved 2024-01-22,
  **I.8**, cover map viewing/download services as well as open data under **CC BY 4.0**, with
  attribution **“datový podklad © IPR Praha”**, licence link and changes indicated. I.7 separately
  addresses terms for non-open deliveries. We use I.8 for the public download-service route and
  retain the contradictory catalogue flag and provider guidance with the source evidence; this
  does not establish that a separately ordered GPKG delivery has the same terms.

Thus HANDOFF's conclusion that tram axes cannot be obtained from public downloads is superseded;
its statement about the catalogue label remains accurate. Public JVF is available even though the
catalogue does not label set 7 open. If confirmation of this classification or GPKG delivery is
needed, use [IPR's request route](https://geoportalpraha.cz/data-a-sluzby/jak-ziskat-data):
`vydej@ipr.praha.eu` (dataset contact `dtm@ipr.praha.eu`). Ask for **DTM kraje – DI Sada 7**, the
district codes below, latest state before the 2026-11-10 transition, format, and explicit reuse and
redistribution terms. No request or order was sent. If a delivery cannot be used, #20 falls back to
reviewed **archived DTMP layer 10** and **OSM**, as already agreed above.

### Which districts and what is in them

`tools/dtm_di.py` intersects **complete segments of both `path` and `pathBack`** for lines 9, 17, 22,
23 and 37 with all 57 level-9 district boundaries in the pinned local OSM extract (district code
`ref:cobe`); conversion uses `tools/geo.py`. The union covers every route segment, with no uncovered
length above the 0.01 m numerical tolerance. A route touching a district boundary selects both
districts. This is district acquisition, not a corridor clip or a track importer.

All rows below are whole-district **`OsaKolejeTramvajoveDrahy`** records, state **2026-09-30**,
JVF **1.4.3**. `OsaTramvajoveDrahy` (alignment rather than individual track) is reported separately
in the JSON, never added to these counts. “Numeric” means finite, nonzero Z on every vertex; it
does **not** certify plausible elevation or accuracy. Mixed means some zero and some nonzero Z.

| District | Code | Lines | Track features | Zero Z | Numeric Z | Mixed Z | `NeuplnaData=true` |
|---|---|---|---:|---:|---:|---:|---:|
| Praha 1 | 500054 | 9, 17, 22, 23 | 1052 | 786 | 266 | 0 | 1052 |
| Praha 2 | 500089 | 9, 17, 22, 23 | 887 | 862 | 25 | 0 | 887 |
| Praha 3 | 500097 | 9, 37 | 662 | 552 | 110 | 0 | 662 |
| Praha 4 | 500119 | 17 | 1010 | 974 | 36 | 0 | 1005 |
| Praha 5 | 500143 | 9, 22, 23 | 1295 | 948 | 347 | 0 | 1295 |
| Praha 6 | 500178 | 22, 23 | 1349 | 1213 | 136 | 0 | 1349 |
| Praha 7 | 500186 | 17 | 806 | 559 | 247 | 0 | 802 |
| Praha 8 | 500208 | 17, 37 | 1175 | 791 | 382 | 2 | 1175 |
| Praha 9 | 500216 | 37 | 719 | 635 | 78 | 6 | 719 |
| Praha 10 | 500224 | 9, 22 | 1061 | 277 | 784 | 0 | 1061 |
| Praha 12 | 547107 | 17 | 234 | 185 | 49 | 0 | 234 |
| Praha 13 | 539694 | 9 | 3 | 0 | 3 | 0 | 3 |
| Praha 14 | 547361 | 37 | 67 | 66 | 1 | 0 | 67 |
| Praha 17 | 547174 | 9, 22 | 135 | 23 | 112 | 0 | 135 |
| Praha-Libuš | 547051 | 17 | 7 | 0 | 7 | 0 | 7 |
| Praha-Troja | 547328 | 17 | 42 | 0 | 42 | 0 | 42 |
| **Package totals** | | | **10504** | **7871** | **2625** | **8** | **10495** |

These are feature instances across packages, not deduplicated physical tracks. The earlier Praha 8
count of 339 used a comparison rectangle; 1175 here covers the whole district. Neither contradicts
the other. Roughly three quarters of the package records have no height; an accuracy flag does not
make their zero Z usable.

Quality flags in every district are position class **3**, height class **3**, acquisition method
**1**, placement level **0**, and incomplete **true**, except:

- Praha 4: five records are incomplete **false** with position/height class **2**; acquisition is
  **1** on 1007 records and **99** on three. Placement is still 0 on all 1010.
- Praha 7: four records are incomplete **false**; two have position/height class **2**, the other
  804 class **3**. Acquisition is **1** on 804 and **99** on two; level is 0 on all 806.

These are raw code values, not an interpretation of survey quality. The report retains distributions
per district and `DatumVkladu` / `DatumZmeny` ranges. Record changes span 2025-01-30 to 2026-08-31;
package date, insertion date and change date do not establish the actual observation date.

### Reproduce and publish

```powershell
python -P -E tools/test_dtm_di.py
python -P -E tools/dtm_di.py                 # offline report -> reports/dtm-di.json
python -P -E tools/dtm_di.py --fetch         # deliberately refresh upstream sources
```

The published source group is `raw/dtm-di/`: **16 ZIPs + catalogue.json + provenance.json + terms.pdf +
access.html**, **21,933,947 bytes**. Provenance records exact per-package URL, date and SHA-256; the
catalogue and terms are retained as received. ZIPs are read directly; snapshot fetch need not unpack
them. The snapshot scanner includes these 20 files. No built-data publication or game regression
baseline update is needed, because neither the runtime nor generated line files changed.

Publication command (2026-10-30, after approval):
`python -I tools/snapshot.py publish 2026-10-30 --note "DI set 7: 16 districts for lines 9,17,22,23,37, state 2026-09-30"`.
The SFTP store accepted all 20 new files (21,933,947 bytes). The complete snapshot contains 1549
files (2,111,750,063 bytes); every previously pinned source is unchanged.

Verified on 2026-10-30 in a fresh clone, with no local source or built-data cache:

- `python -I tools/snapshot.py fetch --no-cache`: fetched all 1549 source paths (1137 distinct
  content-addressed objects) from the SFTP server, hash-checked and unpacked the ZPS packages;
  download completed in 324 s.
- `python -I tools/snapshot.py data-fetch --no-cache`: fetched the 31 existing built-data files.
- `python -I tools/snapshot.py status`: **0 missing/changed, 0 new input files**, and **0 built-data
  differences**.
- `python -P -E tools/dtm_di.py`: the entire JSON report exactly matches the pre-publication report,
  including all 16 district rows and 10,504 track-feature records.
- `tools/test_dtm_di.py` and `tools/test_data_publish.py`: **4 + 1 tests pass** in the fresh clone.

This completes the published-snapshot and reproducibility checks for #61. Existing built data still
records its original source snapshot; no world rebuild was performed for this acquisition.

## Height and terrain findings

Do not confuse “DTM” as **digital technical map** (transport objects and surveyed street surfaces) with **digital terrain model** (a bare-earth elevation raster). They are different datasets.

- Prague IPR publishes a city terrain raster at **1 m** resolution derived from lidar. The downloaded GeoTIFF is float32 and uses S-JTSK / Krovak East North, EPSG:5514, horizontally. Its processing metadata records cubic resampling to 1 m in 2025; intermediate file names suggest a 25 cm raster, but neither that intermediate’s actual resolution nor its public availability was confirmed. The Hostivař and Kobylisy local capture dates and the TIFF’s explicit vertical datum were not established. Check the vertical reference against Bpv and the track data before treating differences as an engineering-grade comparison.
- On the Hostivař tram loop, 186 samples taken at 5 m intervals had a median **track Z minus Prague 1 m terrain of +0.046 m**, with a 90th-percentile absolute difference of 0.076 m; the range was −0.073 to +0.216 m. This measures agreement, not independent accuracy, and adjacent samples are correlated. The current DPP loop records had plausible numeric heights, but the incomplete-data flag needs interpretation. On ten earlier selected loop points, track minus the national ČÚZK DMR 5G image-service result ranged from −0.30 to +1.34 m. ČÚZK DMR 5G was originally derived from 2009–2013 scanning and has since been updated; the local observation date remains unverified.
- Along the approximately 962 m scheduled line 17 route from Kobylisy to Vozovna Kobylisy, 193 points were tested using the game’s actual `Route`, `Terrain`, DTM-surface and `Profile` code with default settings. The game’s track reference minus Prague terrain had a median **+0.036 m** and 90th-percentile absolute difference **0.167 m**. Against the older track-centreline Z it was **+0.019 m** median / **0.150 m** 90th-percentile absolute difference across 192 matches within 1 m. Against usable current-DTM Z the median was **+0.027 m** across 126 matches. The comparisons can match the wrong line at switches and are not independent validation.
- All 193 points were inside the game’s existing line 17 2 m fine terrain and had a surveyed street-area lookup. The stored, unmodified 2 m terrain input was a median **0.061 m above** Prague’s 1 m raster at these points, before runtime terrain carving. Near the Vozovna terminus, the game reference flattened while reference heights rose: the last sampled point was about **0.58 m below Prague terrain** and **0.55 m below the older track Z**. Investigate smoothing and endpoint handling; neither was isolated as the cause.
- The game’s track reference used for the tram and the visible rail height are different. In `src/world.js`, the rail ribbons have a **+0.26 m** lift above the smoothed track height, plus opposite cant adjustments; the bed has a separate **+0.20 m** lift. In the tested corridor, the average of the two drawn rail heights was a median **0.296 m above** the Prague terrain across 192 matched points. This is a rendering offset, not evidence that real rails are 26 cm high. Its original purpose is unconfirmed. Assess rail, bed, street and vehicle contact together before changing it.
- For future height selection, use trustworthy, appropriately referenced track Z when available. Prague’s 1 m terrain and surveyed street surfaces are candidates for **surface-track fallback** after datum, capture date and local fit checks. Avoid forcing tunnels, metro infrastructure, elevated tracks or bridges onto bare-earth terrain. At Hostivař the existing line 22 terrain grid does not cover the loop; extend the source coverage rather than accepting an edge-clamped terrain value. The supplied project has a 2 m fine terrain grid for line 17, not for line 22.

## Implementation handoff

1. **Inventory and reconcile source records.** Read current transport-centreline district packages; load older map and OSM features as fallback candidates. Keep geometry, Z, timestamps, status and source identifiers. Filter unusable or implausible heights without discarding otherwise useful 2D geometry. Resolve repeated district records by identity and geometry, and examine changed/obsolete alignments before combining them.
2. **Build a connected network.** Preserve distinct track centrelines, switches, crossings, turnouts, depots, direction and operational attributes. Match geometries by local alignment, segment continuity, level and topology; never assume a geometric crossing is a connection. Preserve OSM operational data and route relationships when they carry information not present in the DTM. Do not create duplicate tracks by overlaying unmatched sources without review.
3. **Adapt the game’s route and distance-dependent features together.** Rebuild or remap the driven and opposite paths, cumulative distance, stop positions, platforms, signals, crossings, switches, speed metadata, traffic routes, overhead and depot access from the reconciled graph. The current `Route` smooths geometry while preserving distances from the original OSM polyline; a new path changes those distances. Decide how the current spacing adjustment in `src/trackfix.js` should apply to verified DTM geometry, rather than blindly moving an already surveyed pair.
4. **Keep geometry and height processing separate.** Define the vertical reference and what each height measures before combining track Z, street surfaces and terrain. Interpolate along valid track records, avoid zero/mixed Z, handle missing values and source transitions explicitly, and verify bridges/tunnels independently. Shape nearby terrain and surfaces to the resulting track-bed model where appropriate, then revisit the separate bed/rail lifts, cant and vehicle contact together. Do not mask an incorrect alignment by globally lifting rails.
5. **Validate with concrete regressions.** Recheck the Březiněveská straight section (both centreline positions, spacing and lateral curvature), the full Kobylisy–Vozovna approach and its terminal endpoint, the loop’s switches and depot connections, and Hostivař’s loop and metro/railway yard. Compare metres of coverage and separate both directions, rather than only median nearest-track distance. Test source transitions, vertical profiles, terrain clipping, tram/rail/bed contact and complete route driving; run the project’s normal lints/autopilot checks on the actual development copy. Verify real-world geometry and dates with suitable independent reference data where available.

## Inspectable comparisons and sources

- [Kobylisy corridor, track spacing, game profile and downloadable samples](https://kobylisy-track-comparison.jnd-cz.chatgpt.site/corridor.html).
- [Depo Hostivař tracks and height comparison](https://hostivar-track-elevation.jnd-cz.chatgpt.site/).
- [Public DTM datasets](https://dmvs.cuzk.gov.cz/portal/vydej-dat/verejne-datove-sady); the previous comparison used public transport-infrastructure set 7.
- [Older Prague technical-map centreline layer](https://gs-pub.praha.eu/arcgis/rest/services/dtmp/dtmp/MapServer/10).
- [Prague terrain model description](https://geoportalpraha.cz/data-a-sluzby/clanky-a-projekty/3D-model/3D-model-dtm) and [published 1 m raster item](https://opendata.geoportalpraha.cz/maps/97d2c9c11aa9478cb21b469b8a4f820e).
- [ČÚZK DMR 5G service](https://ags.cuzk.cz/arcgis2/rest/services/dmr5g/ImageServer) and [OpenStreetMap attribution](https://www.openstreetmap.org/copyright).

IPR’s open-data guidance specifies CC BY and “datový podklad © IPR Praha”; OSM has ODbL attribution and share-alike considerations. Verify the applicable terms, attribution and compatibility for each selected DTM package and for redistribution of the final combined dataset before release. The hosted comparison pages are convenient research aids, not a guaranteed permanent data archive.
