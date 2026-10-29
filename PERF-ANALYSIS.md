# Performance analysis: line 17 (remote session, 2026-10-23)

Measured on the deployment copy in the desktop app's browser pane (Chromium, Intel Arc A770, D3D11).
The pane was hidden during the whole session (the user was on a phone), so the page ran as a
background page: frame rates could not be watched live and the CPU times swing up to 3-4x between
runs (Windows gives a background page less CPU). Shares within one run are reliable; the absolute
times are an upper bound. Everything was measured by scripts in the page (`window.loadTimes`,
`window.worldTimes`, `renderer.render` + `readPixels` for GPU time, the game stepped with
`window.headless`).

## 1. Loading (line 17, local server, so downloads are near instant)

| Step | Before the fix | After the fix (slower run) |
|---|---|---|
| scripts (Three.js from CDN, modules) | 1.5 s | 1.5 s |
| download all files (38 MB, in parallel) | 0.6-0.9 s | 0.9 s |
| terrain (Terrain, fine blocks, DTM index) | 1.8-2.0 s | (8 s, slow run) |
| profile + ground + carve | 0.5 s | (1.6 s) |
| **world (`buildWorld`)** | **81-82 s** | see below |
| tram model | 0.15 s | 0.16 s |

`buildWorld` by part (ms; first run before the fix, second after it but with the page ~3-4x slower):

| Part | Before | After |
|---|---|---|
| **terrain lowered under the tracks and the DTM streets** | **62 555** | 152 + 6 760 + 4 815 + 314 |
| buildings (LOD2) | 8 236 | (34 959) |
| DTM streets (`buildDtm`) | 5 515 | (21 024) |
| tracks, track heights, tunnel roads | 2 056 | (6 017) |
| track support | 1 194 | (2 782) |
| terrain mesh | 1 120 | (3 588) |
| OSM roads | 493 | (2 602) |
| trees, catenary, zebras, rails, bed, walls, bridges | < 0.8 s together | |

**Fixed (exactly the same terrain, checked by hashing every height of the coarse grid and all 534
fine blocks):** `Terrain.lowerAt` called `grids()` for every point, which built a new array of the
coarse grid plus all 534 fine blocks and tested each one. The DTM step alone calls it 16.9 million
times (2.8 M ground triangles x 6 points), about 3.2 us each: ~53 s. Now `finesAt(x, y)` looks up the
(at most 4) blocks around the point by index. The terrain section fell from 62.5 s to ~3 s (estimated
at normal speed; 12 s in the slowed run). Expected line 17 load on this PC: ~20-25 s instead of ~85 s.

Remaining load cost, largest first: buildings ~8 s, DTM streets ~5.5 s, the lowering itself ~3 s
(6.8 s slowed: `lowerTerrainUnderDtm` still makes 17 M calls; sampling only the triangle corners of
the 5 m split mesh, or lowering per fine vertex once like `lowerFineUnderDtm`, would cut it further),
tracks ~2 s, terrain build ~2 s.

`carveCorridor`'s `origAt` scans all blocks the same way (`origs[k].contains` for k = 1..534), but runs
only ~50 k times (< 0.2 s): worth the same index lookup when touched.

## 2. Memory

JS heap after loading: **1.5-1.6 GB** (peak 2.1 GB during the world build). Limit 4.4 GB on this PC; a
phone or a 32-bit browser would not load line 17.

| What | Size | Notes |
|---|---|---|
| **Geometry arrays (CPU copies of everything drawn)** | **664 MB** | three.js keeps them after upload; the GPU holds the same again |
| - DTM street meshes (170 meshes) | 384 MB | 3.7 M triangles as 11.2 M **non-indexed** vertices, 36 bytes each (float position, normal, color) |
| - buildings (423 meshes) | 128 MB | 1.2 M triangles, non-indexed, with uv |
| - terrain (1 248 meshes, coarse + 534 fine blocks) | 117 MB | 4.9 M triangles, indexed |
| - roads, bed, rails, support, other | ~30 MB | |
| **DTM height lookup (`DtmSurface`)** | ~400-500 MB (est.) | 3.09 M triangles as JS arrays of `[x,y,z]` arrays; the 10 m cell index holds **4.84 M entries, each a new 5-element array** (`[...tri, rank, c]`), 358 k deck entries; 116 k cloud points |
| raw `data.dtm` (parsed JSON, kept in `data`) | tens of MB | areas with rings, model vertices / triangles |
| terrain heights | 12 MB | coarse 0.85 M + fine 2.26 M floats (+ copies made in `carveCorridor`, transient) |
| textures | ~47 MB GPU (est.) | 111 textures; 80 of them are the stop name plates (256x220, one per stop post, legitimate) |

## 3. Rendering (1280x720, pixel ratio 1, cab-height camera looking along the track)

| Place | Draw calls | Triangles | CPU | CPU + GPU |
|---|---|---|---|---|
| Levského | 458 | 1.47 M | 6.5 ms | 8.1 ms |
| Čechova čtvrť | 87 | 0.75 M | 2.0 ms | 3.8 ms |
| Černý kůň | 343 | 1.71 M | 3.2 ms | 5.4 ms |
| Dvorce | 354 | 1.30 M | 2.9 ms | 4.9 ms |
| Palackého náměstí | 427 | 1.68 M | 3.1 ms | 5.7 ms |
| Čechův most | 492 | 2.04 M | 3.2 ms | 5.6 ms |
| Nádraží Holešovice | 587 | 1.82 M | 4.5 ms | 6.2 ms |
| Ke Stírce | 151 | 0.91 M | 2.3 ms | 4.1 ms |

Fine on this GPU (well under 16.7 ms). Not measured: the cab view also renders the whole scene a second
time for the rear-view mirror (`renderMirror`, far plane 700 m), which roughly adds the draw-call CPU
cost again. On a laptop iGPU, 2 M triangles twice per frame is the first thing to hurt.

## 4. Simulation (per game step of 1/30 s, at a stop and pulling out, 25 cars, 90 walkers)

| Part | ms per step |
|---|---|
| **traffic.update** | **1.55** |
| - `_updateWalkers` (90 walkers) | 0.81 |
| - `_updateRoadCars` (25 cars) | 0.77, of which `_poseCar` 0.54 (24 us per car) |
| - everything else in traffic | < 0.1 |
| game.update | 0.06 |
| autopilot | 0.01 |
| visuals | 0.01 |

The cost is the ground height lookup: `ground.surface(x, y)` takes ~7 us (DTM `_hitTri`: a string-keyed
fine-block lookup for the reference height, then every triangle in the 10 m cell). A walker asks once
per step, a car several times (`carPose`: wheel points). At normal speed (1 step per frame) 1.5 ms is
fine. **Inspect mode at 32x runs ~32 steps per frame: ~50 ms of traffic alone (~20 FPS cap).**

## 5. Optimizations, by value for effort

1. **Done**: index lookup of the fine blocks in `Terrain.lowerAt` (load 85 s → ~20-25 s, line 17).
2. **Done (§7).** **Inspect mode: pose cars and walkers only on the last step of a frame** (matrix / height work for
   the in-between steps is never seen). Small change in `traffic.update` (a `draw` flag from
   main.js). Inspect at 32x: ~50 ms → ~10-15 ms per frame. No change to normal play.
3. **Done (§7).** **Walker height only when moved** (e.g. > 0.3 m, or every 4th step): walkers at 1.3 m/s; ~90 % of
   their 0.8 ms. Same idea for parked / queued cars (speed 0: keep the pose).
4. **Done (§7)**, as references + typed arrays (the triangles stay the areas' own arrays, since world.js
   edits their heights after the index is built). **DTM lookup in typed arrays**: triangles in one `Float32Array` (9 floats) + a class / rank
   `Uint8Array`; the cell index as cell → `Int32Array` of triangle ids (built in two passes). Heap
   ~400 MB → ~60 MB, and a faster `_hitTri` (no array destructuring, contiguous memory), which speeds
   up traffic, the world build and the street bot. Touches `DtmSurface` only, if the callers keep
   using `surfaceAt` / `heightAt` / `deckAt` (the `area.mesh` arrays are also used by `buildDtm` and the
   lowering; they could become index ranges into the same typed array).
5. **Smaller vertex formats for the big static meshes**: color as normalized `Uint8` (12 → 4 bytes),
   normal as normalized `Int8` (12 → 4 bytes): 36 → 20 bytes per vertex, the DTM meshes 384 → 213 MB,
   buildings similar. **Indexing the DTM meshes** (shared vertices of the split triangles; kerb faces
   keep their own) would roughly halve them again.
6. **Done (REMOTE-CHANGES §12: heap 1 374 → 682 MB, `?keepgeo` keeps them).** **Free the CPU copies after upload** (`geometry.attributes.*.onUpload(() => array = null)` or a
   dispose of the arrays): -664 MB heap. But `streetbot.js`, `world.js:1464` and the lints
   (`tools/lint.js` reads `window.world`) read mesh geometry, so it needs a switch (keep them with
   `?bot`, `?lint`, or when `window.headless`).
7. **Drop `data.dtm` after `DtmSurface` is built** if nothing reads it later (check: `data.dtm.under`,
   attribution only?).
8. **Mirror**: render it every 2nd frame, at a shorter far plane (200-300 m), or with the buildings and
   terrain layers only near; cuts the second pass by half or more.
9. **Mobile / weak GPU**: a far-plane / fog distance option (950 → 500 m) with chunk culling by
   distance; the DTM and fine terrain only within ~600 m of the camera.
10. Load: buildings 8 s and DTM 5.5 s are the next targets (profile them the same way with laps); the
    world could also be built in pieces with a yield between them so the page stays responsive.

## 6. Preprocessing for chunked loading: what to ship to the client

Question: with the world loaded in chunks, how much of the client's build can move offline, and what
does it do to the download? Measured on line 17 by encoding the finished world (every mesh
`buildWorld` made) in compact binary and gzipping it in the page (`CompressionStream`).

**Today's download (line 17):** 40.3 MB raw, **13.5 MB gzip**, 8.8 MB xz (xz ≈ what Brotli-class
compression reaches). `dtm.json` 23.3 / 6.7 / 4.1, `bld.bin` 6.4 / 1.7 / 1.2, `fine.bin` 4.5 / 2.6 / 1.9,
`line17.json` 3.9 / 1.5 / 1.0, T3 model 2.1 / 0.9 / 0.6.

**The finished meshes, compact:** positions Uint16 quantized per mesh (1 cm), oct-encoded Int8 normals
(or none: recomputed on the client), palette colour index (1 byte), Uint16 uv, vertices welded
(shared), Uint16/32 indices, streams kept apart (better compression).

| Part | GPU now (float32) | compact | gzip | gzip, no normals | its source today (gzip) |
|---|---|---|---|---|---|
| DTM streets | 384 MB | 79 MB | 39.0 MB | **27.9 MB** | dtm.json 6.7 MB |
| terrain | 117 MB | 50 MB | 34.0 MB | **30.2 MB** | fine.bin 2.6 MB + coarse in line17.json |
| buildings | 128 MB | 22 MB | 11.3 MB | **10.3 MB** | bld.bin 1.7 MB |
| rails | 11 MB | 2.3 MB | 1.6 MB | 1.5 MB | (line17.json) |
| track bed, roads, support | 16 MB | 3.2 MB | 1.8 MB | 1.2 MB | (line17.json) |
| **total** | **656 MB** | | | **~41 MB** | **13.5 MB** |

Welding: buildings 3.6 M → 1.3 M vertices (1.1 M without normals), DTM 11.2 M → 5.8 M (2.3 M without
normals: the flat-shaded normals are what keeps the vertices apart), terrain already indexed.

Spread over 500 m tiles (triangles assigned to tiles, each part's gzip size shared by triangle count):
120 tiles for line 17, median 0.19 MB, 90th percentile 0.89 MB, max 1.97 MB (centre: half DTM, half
buildings).

**Conclusions:**
- **Shipping the finished world is ~3x the download** (41 vs 13.5 MB). The generated meshes are bigger
  than the data they come from: terrain 12x (a height grid has implicit x/y and no indices), buildings
  6x, DTM 4x (the client splits every area to ≤ 5 m triangles: 3.7 M of them).
- **Preprocess the decisions and the edits, ship compact sources.** Same size as now or smaller, most of
  the CPU gone:
  - terrain: the height grids **after** lowering under tracks / DTM, carving, tunnel mouths (the edits
    that took 62 s, now ~3 s, become 0); the client only builds the grid mesh (~1 s for the line).
    Same size as fine.bin (Int16, ~5 KB gzip per 128 m block).
  - buildings: `bld.bin`-style quantized triangles already **trimmed / lifted / classed** (a class byte
    per building), so the client does no route tests or bridge trimming (8 s now). ~1.7-2 MB gzip.
  - DTM: two options.
    (a) the surveyed outlines and points as a binary (Int32 cm, delta-coded) instead of JSON: probably
    ~3-4 MB gzip (the JSON compresses to 4.1 MB with xz, so the content is that small); the client still
    triangulates and splits (several seconds per line).
    (b) the final ground mesh, **simplified offline**: within 3 cm, 49 % of its interior vertices are
    removable in one pass (38 % at 1 cm, 54 % at 5 cm; area edges, 31 % of the vertices, not counted),
    and a full edge-collapse simplification typically gets 2-4x: ~7-14 MB gzip, no normals, plus a class
    byte per triangle. **The same mesh is then the height lookup** (the rule already is "the lookup uses
    exactly the drawn triangles"), so `DtmSurface` needs no build and no 400 MB of JS arrays: typed
    arrays straight from the file.
    (b) costs ~2-3x the bytes of (a) and saves the client's 7+ s. With chunks of ~0.1-0.5 MB loaded
    ahead while driving, (b) is the better fit.
  - roads, track bed, rails, support: small either way (~3 MB of meshes, < 1.5 MB as source); keep
    building them on the client from preprocessed polylines with heights.
- **Estimate, line 17 preprocessed:** terrain 2.6 + buildings ~2 + DTM 7-14 (b) or 3-4 (a) + roads,
  tracks, stops ~1.5 = **~13-20 MB gzip** (a: ~9-10 MB), about 0.1-0.2 MB per 500 m tile on average,
  ~1 MB in the centre. Brotli instead of gzip: another ~25-35 % less (xz numbers above).
- **Startup with chunks:** the tiles within ~1 km of the start (~12-16 tiles) ≈ 2-4 MB; then a tile
  every ~500 m (one a minute at 30 km/h): negligible bandwidth, and nothing to build that blocks the
  page if the data arrive in GPU-ready typed arrays.

## 7. Done after the analysis (items 1 and 2 of §5)

- Inspect mode poses cars and walkers only on the last game step of each frame
  (`traffic.update(dt, camera, draw)`), walkers ask the ground height only after moving 0.3 m, and a
  car whose pose inputs did not change keeps its pose. Same run, same place (90 walkers, 22 cars):
  traffic per step 0.63-0.66 ms → **0.39-0.41 ms in normal play (-38 %)** and **0.17-0.18 ms in
  inspect mode at 32x (-73 %)**. Checked: all walkers at their exact ground height and matrix, all
  active cars posed exactly on their lanes.

- **Street-height lookup** (`DtmSurface` → `TriIndex` in terrain.js): triangles by reference, numbered,
  rank / level / class in typed arrays, 3 m cells in one `Int32Array` (CSR) instead of 10 m cells of
  new 5-element arrays. Identical answers (300 k points hashed; terrain heights hashed). `surfaceAt`
  6.4 → **2.2 us**, heap ~240 MB less, traffic 0.40 → **0.26 ms** per step in normal play.

**Line 17 after all of it** (normal CPU speed, local server): load **20.8 s** (was ~85 s): scripts
1.8, download 0.6, terrain 2.0, profile 0.4, world 17.5 (lowering under DTM 4.7, DTM streets 3.8,
buildings 3.3, tracks 1.6, track support 1.2, terrain mesh 1.1), tram 0.2. Heap after start ~1.36 GB
(was ~1.6 GB). The next memory target is the 664 MB of geometry kept in JS after upload (§5 item 6),
the next load target the lowering under the DTM (17 M `lowerAt` calls, §1).

## 8. Multi-threading

**Today: none.** No Web Workers anywhere; loading, simulation and rendering all run on the main thread
(this PC: 24 logical cores). The page is not cross-origin isolated (no COOP/COEP headers), so there is
no `SharedArrayBuffer` either.

Measured costs of moving work to a worker (line 17):
- Parsing the JSON is not the problem: `dtm.json` 23 MB 104 ms, `line17.json` 16 ms.
- Handing a parsed JSON object to/from a worker costs more than parsing it (structured clone of the
  parsed DTM: 181 ms). Typed arrays are transferred for free (40 MB: 0.1 ms). So workers must take and
  return typed arrays, never the nested arrays the code uses now.

**Load** (world 17.5 s, normal CPU speed): what could run side by side once the track and street heights
are final (tracks 1.6 s first):
- terrain lowering under the DTM 4.7 + fine 0.75 + mouths 0.1, then the terrain mesh 1.1 (one chain,
  but spatially splittable: the fine blocks are independent, the coarse grid by area)
- DTM street meshes 3.8 (by area)
- buildings 3.3 (by chunk)
- track support 1.2, roads 0.3, trees, catenary, zebras < 0.5

Serial 17.5 s; in parallel the critical path is roughly tracks + the longest group: ~6-8 s, ~4-5 s
with the lowering and the DTM split over several workers. Cost: every worker needs the inputs it reads
(terrain grids, DTM triangles, route, track heights) as typed arrays, so the DTM lookup is copied per
worker (no shared memory), and world.js has to be split into worker-safe pieces that return geometry
arrays (THREE is fine in a module worker for math; meshes are made on the main thread from the
transferred arrays, which is cheap).

**Recommendation:** don't parallelize the whole-line load in the browser. Everything slow in it is
deterministic from the source data (lowering, flush to the tracks, triangulation and splitting,
building trimming), so it belongs in the offline build (§6), where Python / Node can use all cores
(multiprocessing per tile) and the client is left with assembling meshes (~2-3 s per line now, tens of
ms per chunk). Workers become essential with **chunked loading**: one or two chunk workers that fetch,
decompress and decode the next tiles into GPU-ready typed arrays and transfer them, so streaming while
driving never costs a frame (a 1 MB centre tile decoded on the main thread would be a visible hitch).

**Runtime:** no gain. Per frame: game 0.06 ms, autopilot 0.01, traffic 0.26 (inspect 32x: ~5.5),
render 2-6.5 ms CPU (WebGL calls must stay with the context; moving the whole renderer to an
`OffscreenCanvas` worker frees the main thread but saves no total time). The main thread is mostly idle
at 60 FPS.

**Cheap meanwhile:** yield a frame between the `buildWorld` parts (as the loading steps already do), so
the loading bar keeps moving during the 17 s instead of freezing per step; no time saved.

**Done:** the loading bar now moves through the city build part by part (REMOTE-CHANGES §6).

## 9. WebAssembly vs JavaScript

Toolchain on this PC: Rust 1.67; `wasm32-unknown-unknown` added with the user's OK (no MSVC linker,
so no native build). Kernel: `.claude/bench/tri.rs` (built to `tri.wasm` and `tri_simd.wasm` with
`+simd128`), the DTM lookup's inner loop (barycentric test per triangle, two divisions), run over
3.85 M triangle tests at 200 k points around line 17, best of 7, all four giving the same sum:

| Version | ns per triangle test | vs the game now |
|---|---|---|
| JS, as the game has it: triangles as arrays of `[x, y, z]` arrays | 93.5 | 1x |
| JS, the same arithmetic over one flat `Float64Array` (9 doubles per triangle) | 31.1 | **3.0x** |
| WASM (Rust, `-O`), same flat data in WASM memory | 23.1 | **4.0x** (1.35x over flat JS) |
| WASM with `simd128` | 23.1 | no gain (the loop does not vectorize) |

(The page may have been in its slowed background mode; the ratios count.) The loop is bound by memory
access (each test reads a triangle at a scattered address), like most of the game's work: that is why
the layout matters 3x and the language 1.35x. Independent of both: precomputing each triangle's
barycentric coefficients (no divisions per test) and sorting triangles by cell (contiguous reads)
would help JS and WASM alike.

What this means for more world detail and more traffic:
- **Data layout first.** The game keeps geometry and lookups in nested JS arrays (points as `[x, y, z]`,
  triangles as arrays of them). Flat typed arrays are ~3x faster in JS already, use far less memory,
  transfer to workers for free, and are exactly what WASM (and the GPU) need. That change is the
  prerequisite for WASM anyway, and most of its gain comes without WASM.
- **JS vs WASM on flat numeric data:** V8's optimizing JIT usually runs such loops within ~1.2-2x of
  native; WASM within ~1.1-1.5x. So WASM over well-laid-out JS is typically 1-1.5x, more where WASM
  SIMD applies (4 floats per instruction: height-grid edits, mesh decoding and building, culling), which
  JS has no access to. Confirmed here: 1.35x on the lookup kernel, SIMD nothing there (scattered
  reads); SIMD pays on streaming work over contiguous arrays (grids, vertex buffers).
- **WASM costs:** data must live in WASM memory (copied in, or designed to live there), each JS↔WASM call
  costs a little (batch work per call, not per point), a second language and build step, harder
  debugging; three.js and the game logic stay in JS.
- **Where it would pay off:** chunk decoding and mesh building in the chunk workers (meshoptimizer's
  decoder and Draco are WASM already), the terrain / DTM edits if they stay on the client, and the
  traffic simulation if it grows to thousands of agents. Traffic now costs ~2.4 us per agent per step
  (0.26 ms for ~110 cars and walkers), mostly height lookups and lane logic: 1 000 agents ≈ 2.5 ms per
  step in JS, still fine at 60 FPS. Beyond that, level of detail (simulate far agents coarsely or only
  as flows) gains more than any language.
- **Not:** rendering (WebGL calls stay in JS, and the GPU time does not change), game logic, UI.

## 10. Weather rebuilds the whole world (done: REMOTE-CHANGES §8)

Why: the weather is baked into the vertex colours. `wet` (rain, leaves) darkens asphalt, paving,
track bed, ballast, zebras, tunnel and portal stone and the DTM surfaces (except green and water) by
~20-25 % and makes the rails glossier (roughness 0.4 → 0.2); `leaves` gives the terrain's grass and
woods and the tree crowns autumn colours. The geometry is the same in every weather, but a colour
change means `buildWorld` again: 17.5 s on line 17 plus the GPU upload of 600+ MB.

Proposal: build the world once, weather-independent, and make the weather a **material state**:
- wet: `material.color` multiplies the vertex colours in three.js: one grey factor per material
  (0.75-0.8), with green / water on their own material (or a per-vertex "wets" attribute and a
  `onBeforeCompile` uniform); rail roughness is already a material value.
- autumn: tree crowns are instanced: rewrite `instanceColor` (milliseconds); terrain land cover as a
  class attribute and a palette uniform (or rewrite the colour attribute in place, ~2.6 M vertices,
  tens of ms).
- future winter / leaves on the track: as shader layers over the same geometry (snow where the
  normal points up, by a `snow` amount and noise; leaf / wet-rail decals along the track; puddles from
  a mask texture), not as new geometry.
Gains: no 17.5 s rebuild when the weather changes, weather that can change during a shift (rain
starting, the street drying, snow building up), and one set of chunk files for all weathers (chunked
loading would otherwise need weather variants or a rebuild per chunk).

## 11. Dev aids added for these measurements (kept, all cheap)

- `window.loadTimes` (loading.js) and `window.worldTimes` (world.js `buildWorld` laps), both logged.
- `window.renderer`, `window.scene` (main.js, next to `window.camera`).
