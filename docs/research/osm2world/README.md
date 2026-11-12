# OSM2World study (#15)

What of [OSM2World](https://github.com/tordanik/OSM2World)'s road, terrain, object and railway building our
pipeline should take. Read at commit `1d31c25` (2026-11-02); its assets in
[OSM2World-default-style](https://github.com/tordanik/OSM2World-default-style) at `3d82b2e` (2026-10-25); our
side at `main` 595514a. Prague counts are from our extract `raw/osm/praha.osm.pbf` (2026-10-22).

| note | question | feeds |
|---|---|---|
| [roads.md](roads.md) | 1 roads and junctions | #16, #276 |
| [terrain.md](terrain.md) | 2 terrain and elevation | #276 |
| [objects.md](objects.md) | 3 placed objects | #14, #252 |
| [buildings.md](buildings.md) | 4 buildings | #55 |
| [railways.md](railways.md) | 5 railways and trams | #65, #277, #71 |
| [output.md](output.md) | 6 output, tiles, LOD | #30, #31 |
| [assets.md](assets.md) | 7 models and textures, licences | #65, #276, #252 |

## Two pipelines

| | OSM2World | ours |
|---|---|---|
| source | OSM alone; heights optional (SRTM), flat by default | several pinned sources per layer, OSM the fallback (`tools/sources.py`, DATA.md): DTM survey, DI track centrelines, IPR lidar terrain and LOD2 buildings, Geoportál trees, GTFS |
| run | per tile, on demand, Java | per line, offline Python into `data/lineN*.json`; the page builds meshes (`src/world.js`, `src/terrain.js`) |
| widths, kerbs, positions | guessed from tags and class defaults | measured where the survey has them (lines 17, 22); OSM ribbons elsewhere |
| heights | declared constraints, mostly not enforced at this commit; buildings stand at their lowest point | track profile from survey and lidar with held structures (`docs/decisions/2026-11-02-vertical-profile.md`) |
| ground | a partition: each area minus the footprints of higher-priority ones, nothing drawn under anything | layers drawn over each other (survey over terrain, ribbons over terrain) |
| facts | none beyond tags | `data/truth.json`, the user's answers |

So OSM2World's guesses lose wherever we have measured data; what it offers is method: the ground as a
priority partition, junction areas, attaching objects to the nearest wall or pole, texture coordinates fitted
to whole window bays, and the tile encoding.

## How to take what is useful (question 7)

- **Ideas, reimplemented in our tools: yes.** Every item below is a reimplementation in Python (build) or
  JavaScript (page). No OSM2World code is ported; a file that ends up a close translation carries OSM2World's
  MIT notice in its header (MIT code may go into our AGPL-3.0 project with the notice kept).
- **Running OSM2World as a build step: no.** It brings a JVM, its outputs carry its guesses where we have
  measurements, its per-tile conversion lets neighbouring tiles disagree at junctions ([output.md](output.md)),
  and its height constraints are not enforced at this commit ([terrain.md](terrain.md)).
- **Its libraries: none needed.** The constrained triangulation #276 asks for is in shapely 2.1+
  (`constrained_delaunay_triangles`, GEOS 3.10+), already a build dependency: on line 17's 9,437 ground-level
  survey areas (348,482 vertices) 334,932 triangles in 4.95 s, no boundary edge lost ([terrain.md](terrain.md)).
- **Its textures: some, from their origin.** The style repo is CC0 throughout; take the ambientCG sets
  (asphalt, sett, paving, gravel, concrete, steel) from ambientCG itself and enter them in `ASSETS.md`. Not its
  cars, its DE / PL signs or its power towers ([assets.md](assets.md)).

Decision record: [2026-11-05-osm2world-ideas-not-the-tool.md](../../decisions/2026-11-05-osm2world-ideas-not-the-tool.md).

## Candidates and the user's picks

Picked by the user in the OSM2World Picks page (2026-11-05), with their notes; each taken one is an issue or a
comment on the issue named.

| # | candidate | pick | where now | the user's note |
|---|---|---|---|---|
| 1 | The ground as a priority partition, shapely's constrained Delaunay along the lidar grid, buildings as holes | take | #276 (decision comment) | "does this mean the fused ground model?" (yes: its method) |
| 2 | Streets outside the survey: junction areas, cut-back ribbons with kerb fillets, widths calibrated on the survey | take | #301 | |
| 3 | Sidewalks outside the survey joined to the kerb line | take | #302 (blocked by #301) | |
| 4 | Lowered kerbs at crossings | take | #303 | "Take if not in zps layer" (the ZPS has no kerb type; its heights first, OSM as fallback) |
| 5 | Car lane graph from `lanes` / `turn:lanes` | take | #304 | "Check where available" (11-16 % of car ways along our lines carry `turn:lanes`) |
| 6 | Lane markings from OSM's lane layout where the orthophoto has none | later | fallback in #309 | "which lane layout is meant by that?" (OSM2World's cross-section from `lanes`, `divider`) |
| 7 | OSM street furniture into the feature layer, the DTM first | take | #305 (blocked by #14) | "Osm as fallback for lamps" |
| 8 | Orientation and mounting of placed objects | take | #14 (comment) | "Please explain orientation of what" |
| 9 | Trees | take | #306 | "Our current trees (source?), then newly found tree holes in dtm, osm as fallback" |
| 10 | Ballast with sleepers | take | #65 (comment) | "We already have different types of track styles, ballasted track is one of them, remains to be visualized for each" |
| 11 | OSM catenary masts as a check on poles | take | #277 (comment) | "Yes only as a check, DTM should have the data more precisely" |
| 12 | No contact wire on `electrified=no` tram ways | later | – | "Explore where it exists": all 37 are depot and yard tracks (Pankrác ~25, Hostivař workshops 8, Hloubětín 1, 2 short), none on our lines |
| 13 | Facades: RÚIAN joined to LOD2, bays per storey, roof textures down the slope | take | #55 (comment) | |
| 14 | Tile container: GLB + `KHR_mesh_quantization` against #276's format | take | #307 | "Try and see what's better" |
| 15 | Tile levels as content filters, clipping, rebuild only what changed | take | #30, #31 (comments) | "Please explain what it means" |
| 16 | ambientCG textures | take | #308 | "If we don't find or generate anything better" |
| 17 | Road paint from the orthophoto: stop lines, zebras, arrows, lane lines | take | #309 | "Evaluate compute resources needed to scan ortophotos at highest detail across the whole city" (7 cm: 1.5 s and 2.3 MB per ha; the city 116 GB / ~21 h, our lines' streets ~2 GB / 20 min) |

The decision record is accepted.

Not taken: OSM2World's terrain interpolators, its ±5 m bridge and tunnel offsets, its constraint solver, roof
shapes from tags (IPR's LOD2 roofs are measured), indoor, its sidewalk-as-a-lane model (Prague maps 17,802
separate sidewalk ways), its per-tile conversion, the 3D Tiles tree, catenary (it has none), its cars and signs.
