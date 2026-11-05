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
  MIT notice in its header (MIT code may go into our GPL-3.0 project with the notice kept).
- **Running OSM2World as a build step: no.** It brings a JVM, its outputs carry its guesses where we have
  measurements, its per-tile conversion lets neighbouring tiles disagree at junctions ([output.md](output.md)),
  and its height constraints are not enforced at this commit ([terrain.md](terrain.md)).
- **Its libraries: none needed.** The constrained triangulation #276 asks for is in shapely 2.1+
  (`constrained_delaunay_triangles`, GEOS 3.10+), already a build dependency: on line 17's 9,437 ground-level
  survey areas (348,482 vertices) 334,932 triangles in 4.95 s, no boundary edge lost ([terrain.md](terrain.md)).
- **Its textures: some, from their origin.** The style repo is CC0 throughout; take the ambientCG sets
  (asphalt, sett, paving, gravel, concrete, steel) from ambientCG itself and enter them in `ASSETS.md`. Not its
  cars, its DE / PL signs or its power towers ([assets.md](assets.md)).

A decision record draft: [2026-11-05-osm2world-ideas-not-the-tool.md](../../decisions/2026-11-05-osm2world-ideas-not-the-tool.md).

## Candidates (for the user to pick)

Each becomes an issue once picked, or a point on the issue named. Lane / milestone as proposed.

| # | candidate | note | lane, milestone | where |
|---|---|---|---|---|
| 1 | The ground as a priority partition (survey > OSM street > track bed > building plot > terrain, each cut by those above), triangulated with shapely's constrained Delaunay along the lidar grid; buildings as holes, the 2.5 m foundation sink gone | terrain, roads | world, W3 | a decision comment on #276 |
| 2 | Streets outside the survey: junction areas and cut-back ribbons with kerb fillets, carriageway width from tags, the class defaults measured on lines 17 and 22's survey | roads | world, W3 | new issue; feeds #16, #276 for lines 23, 37, 9 |
| 3 | Sidewalks outside the survey: `footway=sidewalk` ways joined to the carriageway's kerb line | roads | world, W3 | new issue, after 2 |
| 4 | Lowered kerbs at crossings from OSM `kerb=*` nodes (5,863 `kerb=lowered`) | roads | world, W3 | new issue; related #142 |
| 5 | Car lane graph from `lanes` / `turn:lanes` with OSM2World's lane matching | roads | sim, Backlog | new issue; feeds #16, #46 |
| 6 | Lane markings and arrows from the lane layout where the orthophoto pilot has none | roads | world, W4 | new issue; feeds #46 |
| 7 | OSM street furniture (19,569 benches, 6,411 bins, 2,692 bicycle parkings, bollards…) into the feature layer, the DTM first where it records the kind; OSM lamps measured against DTM lamps first | objects | world, W4 | new issue; blocked by #14, feeds #252 |
| 8 | Orientation and mounting: `direction`, else facing the nearest street; a mount field (ground / wall / pole / span) for the nearest surface within 10 m | objects | world, W4 | a point on #14 |
| 9 | Tree rows minus register trees, sizes from attributes | objects | world, W4 | new issue |
| 10 | Ballasted track with sleepers, near and far LOD, our own dimensions | railways | world, W4 | a point on #65 |
| 11 | OSM catenary masts (988 within 15 m of tram track) as a check on pole placement; the 42 combined lamp-and-traction poles | railways | world, W4 | a point on #277 |
| 12 | No contact wire on `electrified=no` tram ways (37) | railways | world, Backlog | new issue |
| 13 | Facades: RÚIAN use and storeys joined to LOD2 buildings, a defaults table per type, facade texture coordinates fitted to whole window bays per storey, roof textures down the slope | buildings | world + assets, W4 | points on #55 |
| 14 | Tile container: GLB with `KHR_mesh_quantization` measured against #276's ground format on line 17 | output | world, M3 | new issue; feeds #30 |
| 15 | Tile levels as content filters switched by screen-space error from tight per-tile bounds; clipping with interpolated attributes, tiles rebuilt only when their inputs change | output | world, M3 | points on #30, #31 |
| 16 | ambientCG textures for asphalt, sett, paving, ballast, concrete, steel | assets | assets, W3 / W4 | new issue; feeds #65, #276 |

Not taken: OSM2World's terrain interpolators, its ±5 m bridge and tunnel offsets, its constraint solver, roof
shapes from tags (IPR's LOD2 roofs are measured), indoor, its sidewalk-as-a-lane model (Prague maps 17,802
separate sidewalk ways), its per-tile conversion, the 3D Tiles tree, catenary (it has none), its cars and signs.
