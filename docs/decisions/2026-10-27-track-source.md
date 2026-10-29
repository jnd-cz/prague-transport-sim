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
