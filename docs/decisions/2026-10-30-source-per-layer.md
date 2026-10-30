# A source per layer, with fallbacks and provenance

**Date:** 2026-10-30
**Status:** agreed and implemented 2026-10-30 (issue #10). The user chose: IPR's terrain ZIP whole in the
snapshot, its heights taken as Bpv behind a build check, all five lines rebuilt. Snapshot 2026-10-30c.

## Measured

- **IPR's 1 m terrain** ("Digitální model terénu - rastr", opendata.geoportalpraha.cz item `97d2c9c1…`,
  CC BY 4.0) is one public ZIP of 2.05 GB: `dtm_1m.tif`, BigTIFF 35 001 × 26 001 float32, tiled 128 × 128,
  LZW, S-JTSK, 660 025 394 cells with data (the city and a margin). Lineage in its metadata: the 2023
  lidar (~40 points/m²), corrected in 2025, resampled cubic from 25 cm to 1 m on 2025-07-10.
  - It **states no vertical datum** (#62).
  - Its cell centres are **not on whole metres**: the top-left centre is (−757 500.2778, −1 034 000.3889),
    so every cell is 0.72 m east and 0.61 m north of the S-JTSK metre grid. The frame decision's "tiles
    cut between cells, never resample" holds for DMR 5G, not for IPR: IPR is sampled bilinear at our
    lattice points.
- **Datum check.** IPR minus the ZPS survey's ground-level 3D boundary lines (Bpv, state 2026-09-30)
  within 60 m of line 17: median **+0.016 m** over 69 002 vertices, p10 −0.18, p90 +0.18 (the Výtoň study
  had +0.014 m). IPR minus DMR 5G (Bpv) over each line's fine-terrain band, per line (9, 17, 22, 23, 37):
  median +0.031, −0.032, +0.031, +0.022, +0.007 m. A Bpv / EVRF2007 mix-up would show **0.13 m** in Prague
  (ČÚZK's operation in PROJ, `vertoffset dh=0.13`). So IPR is Bpv to within the noise of the comparison.
- **Coverage.** IPR has a height at every fine-terrain point of the five lines (8.0 M points at 2 m).
- **What changes against DMR 5G** along the tracks (old minus new terrain on both route directions, every
  2 m): 8–15 % of the fine points move more than 0.5 m. Where the terrain rose 6–9 m, IPR's 2023 lidar has
  earthworks DMR 5G's older one does not: the Libuš – Modřany line (built 2020–22) and the Trojský most
  approaches (2014). Where it fell under route bridges, IPR has no bridge in it (decks are the structures
  layer). Where DMR 5G was bumpy in a track area (Palmovka, line 37, up to 1.8 m), IPR is a steady grade.
- **IPR has no covers over passages.** It is bare earth "without buildings, bridges" (its catalogue
  text): where a street or a stream passes under the track, IPR shows the passage, DMR 5G the surface
  over it. Unhandled, the track profile of a line without the street survey dropped into them: 5.3 m into
  Divadelní's underpass at Národní divadlo (lines 9, 22, 23), 6.2 m into the Rokytka culvert (line 37,
  a new 167 m sag in `verticalCurves`). At Zahradní Město (line 22's terminus, 2022) the tram itself runs
  under the railway in a new cutting, which DMR 5G predates: there IPR is the right one.
- Before this, `fine_terrain.py` filled points without DMR 5G data with the median of their block, not
  the coarse grid its comment named, and the built files said only a credits line each: which source a
  feature came from, how old it was and whether a rule made it was nowhere in the data.

## Decision

1. **One table of sources and their order per layer: `tools/sources.py`** (`SOURCES`, `LAYERS`). A source
   has its snapshot group, credits line, the date of its data (read from the snapshot's files where they
   carry it: the OSM extract's name, GTFS `feed_info`, the ZPS package months, the DI provenance) and,
   for heights, its datum. Rules are sources too (`rule:placement`, `rule:curvature`, `rule:assumed`), so
   what a heuristic decided never passes for data. A new source goes into the snapshot and this table.
2. **A layer's sources are tried in order, per feature, not per area or per line.** A level is used where
   it has data that passes its checks (no-data cells, zero or implausible Z, the datum check, the
   structure and disagreement holds of the track-height assessment); otherwise the next level. Never
   "the newest wins" or "the one with numbers wins": the track decision's rules for currency and
   identity apply to every layer.
3. **Every built file carries `provenance`**: per list (the file's JSON key) its layer, the layer's
   levels and how many features came from each, the tool that made it, and what the tool measured to
   trust a source (`checks`); and per source used its title, date, credits and datum. Several tools
   writing one file (`lineN.json`: build_line, platforms, osm_speeds, clearances) each add their lists.
   - A list whose features come from several levels gives each feature `fb`, its level (0 = preferred):
     the fine-terrain blocks (worst level of a block's points), platforms (OSM or PID's point),
     clearances (OSM `maxheight` or the default). A list from one level has no per-feature field.
   - A list holding several layers is split by a selector key: `areas[c=deck]` (structures),
     `areas[c=wall]` (walls) beside `areas` (the rest: streets); `buildings[k=1]` (Mosty 3D) beside
     `buildings` (LOD2).
   - `attribution` is made from the sources used, and the game builds its credits line from the files'
     provenance, each source once (`src/provenance.js`). The game logs the lists that came from a
     fallback level, and `window.game.provenance` holds all of them for review.
4. **Terrain: IPR 1 m → DMR 5G → the line's coarse grid** (`fine_terrain.py`, `tools/ipr_dtm.py`). Per
   lattice point the first level with a height. IPR's heights are Bpv; the build compares them with
   DMR 5G on every line and stops at a median difference over **0.07 m** (between the ±0.03 m spread of
   the lines and the 0.13 m of a datum mix-up). #62 stays open for IPR's own statement.
   - **Passages:** within 8 m of an OSM passage (`tunnel`, `covered`, `culvert`, a negative `layer`; not
     the metro underground), a point where IPR is more than 0.5 m under DMR 5G takes DMR 5G: IPR fails
     there as the surface. 0.18–0.54 % of a line's points; counted in `checks.passageCovers`. At Zahradní
     Město this keeps the old terrain too, until the track heights (#20) and structures (#13) carry the
     tram on its own level.
   - The coarse 10 m grid over a line's whole box stays DMR 5G (`build_line.py`): it is the last level.
   - The reader decodes only the TIFF tiles a build touches (~1000 of 55 896, 13 ms each), with a TIFF-LZW
     decoder checked bit for bit against libtiff on 403 tiles.

## Where each layer stands (2026-10-30)

From the five lines' provenance after the rebuild (`window.game.provenance`, or the files):

| layer | built from now | still to come |
|---|---|---|
| terrain | IPR 1 m at the tracks (99.5–99.8 % of fine points, DMR 5G over passages), DMR 5G 10 m beyond | IPR at Zahradní Město with #20 / #13 |
| streets | ZPS areas where surveyed (lines 17, 22), OSM road widths elsewhere | archived DTMP streets (not in the snapshot), level-aware (#21) |
| tracks | OSM | DI centrelines and archived axes (#20; heights #106) |
| structures | OSM bridge / tunnel tags as route ranges, Mosty 3D models, ZPS decks | the deck as the priority (#13) |
| furniture | archived DTMP points (line 17), OSM signals | current survey points, the feature layer (#14) |
| stops | OSM platforms, PID points where OSM has none | |

## Open

- IPR's confirmation of the datum (#62); the check stays either way.
- The coarse grid from IPR as well (one surface source inside the city): measure the seam between the
  fine and the coarse terrain first.
