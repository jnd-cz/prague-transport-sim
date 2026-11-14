# openOMSI: map, scenery and streaming (#520)

openOMSI read at commit `b2dc640b4db64a09ddfc0d00b8e78c463c81c842` (2026-11-12), licence **AGPL-3.0-only**
(`Cargo.toml` `[workspace.package] license`, README "License"). Paths below are under `crates/` unless they
start with `docs/`. Our side: main at 619e0e9. Feeds M3 (#30, #31, #339), the ground (#276's steps #508, #509),
#301, #309, #16 and #14.

## What openOMSI does

**The map model** (`omsi-map/src/lib.rs`, `tile.rs`; `omsi-scenery/src/sli.rs`; `omsi-geometry/src/lib.rs`).
A map is a grid of tiles, 300 m on a side (371.9 m on `[worldcoordinates]` maps: a zoom-16 Web Mercator tile,
scaled onto one grid by its median row so roads meet across tile borders). Each tile has a terrain of 61 × 61
heights (5 m) and lists of objects and splines in tile-local metres.
- A **spline** is one analytic piece: start, heading, length, a constant radius (0 = straight), gradients at both
  ends (a cubic in height with `[spline_h]`), cant at both ends, skew at both ends (mitred joints), the chain's
  texture offset, prev/next ids (`MapSpline`, `SplineCurve`).
- Its **type** (`.sli`) is a cross-section: profile points (x across, z up, texture u, v per metre) per texture,
  height profiles, a half cant width, and **paths** (`PathDef` in `omsi-scenery/src/lib.rs`: kind 0 street,
  1 sidewalk, 2 rail; lateral offset, width, direction). One file gives the drawn road, the ground under it and
  its lanes.
- The mesh is extruded at load with a cross-section every half degree of turn or gradient change, at least one
  per 10 m, at most 2,580 vertices a piece (`spline_station_count`, `omsi-geometry/src/lib.rs:265`).

**Objects carried by splines** (`omsi-map/src/tile.rs` `SplineAttachment`; `omsi-world/src/map_index.rs`).
`[splineAttachement]` puts a row of objects along a spline chain: lateral offset, height, the first object's
distance along the chain, interval, range, a tilt flag (lean with gradient and cant: parking bays, arrows) or
upright (lamps, catenary masts). Where the chain enters another tile a `[splineAttachement_repeater]` continues
the row, and its first position depends on the chain's length back to its start, which may lie in tiles that are
not loaded. So `MapIndex` holds every spline's length and links and all 345,000 object positions of a big map
for the whole session. `[attachObj]` hangs objects on a parent's attachment points (signal heads on a beam).

**The ground under the roads** (`omsi-scene/src/cut_terrain.rs`, `omsi-geometry/src/tile_surface.rs`,
`terrain_fit.rs`, `terrain_constraints.rs`, `terrain_fit_sampling.rs`). Four mechanisms, per tile at load:
1. A **surface raster** of 512² texels a tile (0.59 m; `SURFACE_RASTER`, `omsi-scene/src/world.rs:505`) holds,
   per texel, the highest, the lowest and the drivable surface height, in 16² blocks made only where a surface
   touches (5 MB a tile before, 0.6 MB now). The terrain is drawn with an **alpha mask** cut from it: the ground
   goes where a surface lies between 4 m under it (`DEEP_CUT`) and 0.12 m over it (`surface_flush`,
   `omsi-sim/src/world_data/ground.rs:48`; higher is a bridge or an embankment). Along a spline's outline the
   mask is decided on 4 × 4 points a texel, the ground kept up to 8 cm inside the outline (`OUTLINE_KEEP`) and
   20 cm inside an object's cutter (`HOLE_KEEP`):
   cut by whole 1.5-3 m texels the sky showed along kerbs. Cutting under every road at its height is off by
   default (`road_cut`, `tile_surface.rs:15`).
2. **Explicit holes**: an object's `[terrainhole]` mesh (junctions, underpasses, tunnel mouths) and a spline's
   `[terrainholeprofile]`, or a trough derived from its profiles (`terrain_hole_profiles`, `lib.rs:511`).
3. **The terrain fitted to the roads**: splines laid with `[spline_terrain_align]` get a constrained Delaunay
   triangulation (the `spade` crate) of the tile's terrain with the road rims as constraints. The constraints
   are planarized first (snapped to 0.1 mm keys, crossings split in a broad phase, all vertices before edges:
   "never ask Spade's incremental constraint splitter to resolve nearly touching roads"), probes are inserted
   only where the surface misses its height budget (at most 16 passes), and work is bounded (160,000 probes,
   80,000 segments, `terrain_fit.rs:11-12`) with the old hole cut as the fallback. A spline whose rim lies more
   than 1 m under the saved ground (`CUTTING_DEPTH`) is a cutting and keeps the hole and soil walls.
4. **Junction plates** (`omsi-scene/src/place.rs:5-60`): a junction object covering ~200 m is raised by its own
   coarse height field so its arms meet their roads (Juliusturm: a 3.5 % plane, −0.62 m under the west arm,
   +0.76 m under the east; draping it on the terrain and nearby roads instead made a trough with a 0.8 m wall).
A check (`OMSI_CHECK_ROADS`, `cut_terrain.rs:45-60`) counts ground cut away with nothing under it and ground
standing over a road, by depth band (3-10 cm, 10-30, 30-60, 60 cm-1.5 m). Wheels read a per-tile grid of the
upward faces (`omsi-geometry/src/drive_grid.rs`: 4 m cells, a 5 mm seam tolerance because neighbouring
pieces compute their shared edge separately).

**Layers in the picture** (`omsi-render/src/frame_plan.rs:300-325`, `shaders/scene/03_vertex.wgsl:181-227`).
Ground layers are not lifted: each class is **pulled towards the eye along its line of sight** in the vertex
shader, by a share of the distance (roads 0.3 %, surface objects 0.4 % + 1 cm, painted lines 0.45 % + 1.5 cm,
shadow blobs 0.5 % + 5 cm), capped at 5 cm on upright faces, at most 0.3 × the distance. The pixel does not move,
only its depth, and a share of the distance keeps a flat road one plane however it is cut into triangles: a fixed
offset per vertex bowed long triangles over short ones and rails went under the road (their #1196); a capped
share turned the road into a bowl and the lines on it vanished at 40 m (their #3085). Raster slope bias is kept
for explicit `Zbias` materials only. A plain object whose points all lie within 5 cm of one height, between 5 cm
under and 25 cm over its origin, is classed as paint and drawn after the roads (`paint_at_foot`,
`omsi-scene/src/staging.rs:771`).

**Road paint read from pictures** (`omsi-scene/src/road_paint.rs:51-218`), for the 2D map: the asphalt is the
darker quarter of a texture's luma; paint is ≥ asphalt + 0.26 and ≥ 0.5; yellow by hue (r > 0.55, g > 0.42,
b < 0.62 × max, r − b > 0.25), white by low chroma (min > 0.45, spread < 0.28); a picture over 55 % bright
(concrete, setts) has none; clumps under max(6, n/8000) texels, ragged clumps (outline > 1.7 × their box's) and
pictures with over 80 clumps are dirt; a clump filling ≥ 85 % of its box is a bar (lane line, stop line, zebra
bar), the rest free-form (arrows).

**Streaming** (`omsi-scene/src/tiles.rs` `Streamer`, `stage.rs`, `staging.rs`, `upload.rs`, `place_step.rs`;
`omsi-app/src/app.rs:436-455, 1069-1101`):
- **Centres:** the camera and the player's bus (and every LAN player on a host), so a free camera flying off
  never takes the ground from under the bus.
- **Radii:** load within the view distance, 1,200 m by default (menu 600-2,500 m); unload beyond it plus 1.5
  tiles (450 m); the loading screen waits for the first 700 m only.
- **Work off the drawing thread:** a loader thread takes the nearest missing tiles, 6 a batch for the first area
  (on every core), then 3 a batch on a pool of a third of the cores (at least 2) at lower priority, so the
  frame's own parallel work never waits (`tiles.rs:21, 457`). A tile is **staged** (parsed, typed) first and
  placed only when every tile its ground depends on is staged (`TileLayout::sources_of`, `staging.rs:981`: its neighbours and
  tiles with splines reaching it), so "a tile streamed in gets exactly the ground and the cut a whole-map load
  gives it" (`stage.rs:241-247`).
- **The frame's share:** upload and placement run on the drawing thread for **6 ms a frame** plus 2 ms of texture
  swaps, sliced: a tile's new textures and object types first, then its ground, splines, trees and objects a few
  at a time (a main-station tile took a third of a second in one piece; `place_step.rs:73-78`). Unloading has its
  own half budget, farthest first, at least one tile a frame (a camera jump had dropped 42 tiles in one 400 ms
  frame). A tile that leaves the radius while in flight is abandoned with what it holds; a tile that fails is
  left out and not asked for again.
- **Lists the simulation reads** (stops, obstacles, lights) are rebuilt for all loaded tiles at once, 0.4 s after
  the first new tile (0.3-6 ms on Berlin-Spandau), at once when a tile goes. The simulation reads the ground
  through an immutable snapshot swapped in when a tile's ground comes or goes (`docs/ARCHITECTURE.md`, "Known
  debt"). The handover runs per frame, not per tick, so the AI traffic is not yet the same at every frame rate.
- **Checks:** frames over 16 ms and the worst frame share are counted; `OMSI_CHURN` checks offscreen that a
  picture drawn from recycled GPU slots is the right one.

**Memory** (`docs/ARCHITECTURE.md` "Memory"): textures stay compressed on the GPU (BC1/BC3, encoded on the
loader threads); a texture budget of an eighth of the machine's memory, met once a second by dropping the finest
mip of textures only tiles beyond 150 m use (down to 64 texels), restored within 400 m when a tenth is free; the
video memory held under nine tenths of the card (driver counts on DX12/Vulkan/Metal, own byte counts on OpenGL);
freed slots reused lowest first and the arrays' free tail cut; sound clips unused for a minute dropped. Ahlheim's
main station: peak 8.75 → 1.93 GB, a flight over the map 8.54 → 2.05 GB; frames over 50 ms 2 → 0. Separately,
joining short spline pieces of one material in 48 m cells took a heavy scene from 17.8 to 36.7 fps (31,221 →
6,135 batches a frame, `docs/performance-th-wald.md`).

**A prebuilt map container** (`docs/MAP_PACKAGE.md`, `omsi-map/src/package.rs`): `surface.oms` is one file with
an index of chunks (cx, cy, offset, length; e.g. 2,000 m chunks), positions as `f32` offsets from an `f64` origin,
triangles ready to draw; "loading costs a file read, never a geometry pipeline". The game's own map picture is
derived once per map and cached under a key of the tiles' sizes and dates (`omsi-scene/src/mapgen.rs`).

## What we do

- **One line at a time, built in the page.** `src/main.js:48` fetches every file of the line at once;
  `buildWorld` (`src/world.js:393`, parts in `WORLD_PARTS` `:383`) builds terrain, survey, streets, buildings,
  trees and catenary; `uploadWorld` (`src/main.js:207-230`) puts everything on the GPU in one frame with culling
  off and drops the JS copies (~660 MB on line 17) unless `?keepgeo`/`?bot`. Line 17 loads in 16.4 s (#509, main
  19f587f); the JS heap is 1.1-1.6 GB after load (`docs/knowledge.md` #205; `docs/history/PERF-ANALYSIS.md` §2).
- **Merged meshes** in 350 m cells per material (`ChunkedGeometry`, `src/world.js:11, 141`).
- **The ground as layers fitted at load:** terrain lowered 0.25 m under the survey and the tracks
  (`src/world.js:877-906`), the survey laid flush with the rails (`flushDtm` `:920`), surfaces lifted by class
  (`DTM_LIFT` 1-6 cm, `src/terrain.js:464`), OSM ribbons at 0.12/0.16 m, zebras at ground + 0.135 m
  (`src/world.js:1685`). #276 replaces it: one surface built offline, constrained triangulation per area
  (#508), the page loading it with one height lookup (#509), the old layers removed (#510).
- **Decided for M3:** 500 m tiles on the S-JTSK grid, vertices tile-relative, networks global and not cut, clip
  points written to both tiles (`docs/decisions/2026-10-29-city-frame-and-tiles.md`); the ground as one greedy
  mesh at 10 cm cut along tile lines (the benches used 1,024 m tiles, `2026-11-05-ground-built-offline.md`);
  integer differences decoded in a worker: 3.9 ms decode + 3.3 ms normals a 1,024 m tile, a 0.8 ms page stall,
  the GPU upload not measured (`2026-11-06-tile-container.md`); content-hashed tile files in the Cache API (#339).
- **Rows along a line:** catenary poles are placed at load every 12/18/25/32 m by curve radius
  (`src/world.js:2017-2021`); street furniture and trees come from data with their own positions (#252, #305,
  #306).
- **Lanes and surfaces from two sources:** car lanes from OSM centrelines (`src/traffic.js:523` `_buildLanes`),
  the drawn street from the survey or an OSM ribbon (`tools/build_line.py:1107`); cars stand on the ground
  triangles (`carPose`, `src/traffic.js:136`; `TriIndex` in 3 m cells, `src/terrain.js:754`).
- **Paint:** zebras from OSM, stop lines from OSM signals or the junction edge; `tools/ortho_lanes.py` reads lane
  lines from the 7 cm orthophoto along cross-sections (#309).
- **Minimap:** tracks, the route, signals and switches within 700 m (`src/hud.js:271`).

## Streaming and memory side by side (question 3)

| | openOMSI | ours now | ours planned (M3) |
|---|---|---|---|
| unit | 300 m tile, parsed and built at load | the whole line | 500 m tile (1,024 m in the ground benches), prebuilt |
| what the tile carries | source records; meshes, ground cut and fit made at load | - | finished ground, decisions and edits (#30) |
| neighbour dependency | staged neighbours before placing | - | none: cut offline, clip points in both tiles |
| reach | 1,200 m (600-2,500), unload +450 m, first area 700 m | the line's box, fog at 950 m (`src/main.js:198`) | ~1 km, 12-16 tiles at start (`docs/architecture.md` §5) |
| off-thread | a third of the cores, batches of 3 | none | 1-2 decode workers (PERF §8) |
| drawing-thread budget | 6 ms upload/place + 2 ms textures, sliced | one frame for everything | open |
| memory limit | texture budget by mip drop; video memory 90 % | none; heap 1.1-1.6 GB | open (#31) |
| simulation data | lanes, stops, lights come and go with tiles | global | networks global |

## Ideas: take or not

1. **The streamer's mechanics** (two centres, radius with hysteresis, a first area, nearest-first batches, a
   per-frame budget sliced below a tile, unloading with its own budget, abandoning tiles that left the radius,
   leaving out tiles that fail). **Take the design for #31**, no new issue. In WebGL a geometry goes to the GPU at
   its mesh's first draw, so a slice is "add a few of the tile's meshes a frame within a byte budget". The first
   measurement for #31: a centre tile's upload on the GPU (`tools/gpu.py` or `tools/frametime.py` headed), which
   decides the slice size. Centres for us: the tram, the camera in `?review`/`?inspect` and the street bot.
2. **The guarantee "streamed equals whole load"** and its check. **Take for #31's done-when:** a drive with
   streaming gives the same lint and seeded counts as the same line loaded whole, and the ground lookup the same
   heights at sampled points. openOMSI needs staging to get there; our offline cut gets it by construction, and the
   check proves it.
3. **The simulation's handover off the frame.** openOMSI's per-frame handover makes AI traffic depend on the frame
   rate. **Take as a rule for #31 and #37:** the simulation reads only global data (networks, stops, signals) and a
   ground lookup loaded wherever the micro tier runs (load radius ≥ the micro tier's ~1 km); a tile never hands the
   simulation anything per frame, so the seeded checks stay deterministic.
4. **A memory budget counted in our own bytes.** WebGL reports no memory; openOMSI counts its own on OpenGL.
   **Take for #31:** each tile records its bytes (positions, normals, indices, textures); the budget orders
   unloading and level of detail. Our weight is geometry (656 MB float32 on line 17, PERF §6), not textures
   (~47 MB), so the levers are the radius, a looser greedy tolerance for far tiles and 8-byte quantized vertices
   (the tile-container decision). The **mip-drop texture budget** waits until #308's textures make textures count.
5. **The depth pull for flat things on the ground.** **Take, new issue (below).** After #509 the ground is one
   surface at its true height; zebras (+0.135 m), the manhole discs of `buildStreetDetail`, leaf litter
   (`polygonOffset`) and #309's paint all need to lie on it without lifts or slope bias. The share-of-distance
   rule and its lessons (no fixed offset per vertex, no cap on flat faces) are the part to take.
6. **Junction plates raised by their arms** (`place.rs`). **Take the idea for #301:** a junction polygon's heights
   come from its arms' cut ends (a plane or a smooth fit through them), not from the terrain under it; report the
   step at each arm.
7. **The paint classifier** (`road_paint.rs`). **Take as an idea for #309:** dark-quartile asphalt, a luma margin,
   hue for yellow, speck and ragged-clump filters, "≥ 85 % of the box is a bar". On the orthophoto the box is the
   oriented box in the street's frame, and the thresholds are fitted on photos (shadows, cars), not textures.
8. **Splines carrying lanes:** one cross-section gives the surface and its lanes, so they cannot drift apart, and a
   lane carries the surface's height. **Take as an idea for #16:** lanes and footways from the same polygons the
   ground uses (the survey's carriageway, #301's streets), with the build's heights; whether cars then still need
   the ground triangles (`carPose`, #245: ~9 s of a 66 s run) is #16's to measure.
9. **The constrained fit of the terrain to the roads** (`terrain_fit.rs`). **Nothing new for #508:** our partition
   (#507) hands shapely planar areas on a centimetre lattice, so the snapping and crossing splits openOMSI needs
   before `spade` are done; error-driven insertion is what pydelatin's greedy mesher does. Its depth-band check of
   ground over road matches #509's "no hidden ground triangles" and `terrainOverSurvey` (`tools/lint.js:299`).
10. **Objects in rows along a chain** (`[splineAttachement]` and repeaters). **Not taken:** the repeaters exist
    because rows are placed at load per tile. Ours belong in the build's feature layer (#14) on global networks,
    before any tile cut; catenary poles move there with the power data (W4).
11. **Spline batching in 48 m cells.** **Nothing to take:** we merge per material in 350 m cells already; the cell
    size within a tile is a `tools/frametime.py` question for #31.
12. **The map picture derived and cached** (`mapgen.rs`). **Not now:** a minimap of the ground classes from #508's
    file is a Backlog idea; not filed.

## Where ours is already better (question 2)

- **Geometry from survey and DI, not authored arcs:** kerbs, carriageways and islands from IPR's survey, track
  curves from DI's chains, heights from a banded solve; OMSI's splines are constant-radius pieces with a cubic
  height, its ground 5 m heights a tile edited by hand. Our terrain is IPR's 1 m lidar at 10 cm.
- **The ground built offline:** openOMSI cuts, fits and deforms at every load and needs staged neighbours for it;
  #276 does it once, welds shared vertices exactly on a centimetre lattice (openOMSI's wheels need a 5 mm seam
  tolerance) and leaves the page a decode.
- **Networks global, not per tile:** nothing waits for a tile to learn its lanes or stops (openOMSI's timetable buses
  wait for "the part of its route it is on").
- **Tile files named by content** (#339) suit HTTP caching better than one package file with an index.

## How to take it (question 4)

Ideas only; nothing above needs ported code. The depth pull is a few lines of vertex shader, written for
Three.js's material hooks from the rule, not from the WGSL. If any file is translated closely, it keeps openOMSI's
licence: **AGPL-3.0-only**, not our `-or-later`, so that file says `SPDX-License-Identifier: AGPL-3.0-only`, names
the source file and commit b2dc640b, and gets an entry in `ASSETS.md` as OSM2World's code would. No OMSI 2 content,
sample files or assets: openOMSI holds none, and none is needed.

## Proposed new issue

**Flat things on the ground at their true height: a depth pull by a share of the eye distance instead of lifts.**
Lane `lane:world`, milestone W4 (with #309), blocked by #509.
- **Now:** zebras at ground + 0.135 m (`src/world.js:1685`), the survey's classes lifted 1-6 cm (`DTM_LIFT`), leaf
  litter and the street detail with `polygonOffset`; #309 adds stop lines and arrows.
- **Do:** one material hook pulls a flat class towards the eye by a fixed share of the distance (openOMSI: 0.3 %
  for surfaces, 0.45 % + 1.5 cm for paint), with the logarithmic depth buffer the page uses; the lifts go.
- **Done when:** no paint or disc is lifted, none flickers or vanishes from the cab at 5-200 m (screenshots main
  against branch at named zebras, stop lines and manholes), the same frame time (`tools/frametime.py`).
- **Checks:** the drawn-geometry tier (`lint,surfaces,crossing,canted`), screenshots, frame time.
