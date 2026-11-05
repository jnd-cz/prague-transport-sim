# The ground built offline: the terrain mesher, the profile in Python, the format (#276)

Status: draft (PR "Part of #276"), the user's answers to its questions pending.

## Why

#276 builds one ground surface per line offline: survey areas, track beds, building plots and the lidar terrain
fused, nothing drawn under anything else (the issue's text and its comments of 2026-11-05). The partition by
priority and shapely's constrained triangulation are decided ([OSM2World ideas](2026-11-05-osm2world-ideas-not-the-tool.md),
T1-T4 of [terrain.md](../research/osm2world/terrain.md)). Three choices were open:
- how the terrain over the whole box is simplified by an error that grows with distance from the tracks;
- how the track profile and cant get out of the page;
- the format.

Measured with `tools/bench/terrain_mesh.py` and `tools/bench/ground_cut.py` (line 17, main 8f9e4c3, IPR's 1 m
raster on its own cell centres, the error against every 1 m cell). The tolerance is
`tol(d) = TOL` within `D0 = 120 m` of a track, `TOL · d / D0` beyond (the same angle seen from the track: 0.42 m at
500 m), at most 3 m.

## 1. The terrain mesher: greedy insertion

Line 17's whole terrain box (7.1 × 15.4 km, 112 tiles of 1,024 m meshed on their own; every cell had IPR lidar),
TOL 0.10 m. Errors in cm: the mean over all cells / the median tile's p99 / the worst tile's p99:

| method | triangles | time | 0-10 m | 10-120 m | 120-500 m | beyond 500 m |
|---|---|---|---|---|---|---|
| now (as the bench models it: 2 m to 128 m, 10 m beyond) | 5,028,597 | - | 2.7 / 23 / 170 | 2.6 / 27 / 69 | 17.2 / 129 / 289 | 18.0 / 139 / 251 |
| RTIN | 7,081,625 | 39 s | 1.8 / 9.4 / 12 | 1.8 / 9.4 / 12 | 4.7 / 26 / 51 | 30.2 / 125 / 284 |
| **greedy insertion** | **3,655,633** | 10 s | 2.3 / 9.0 / 9.3 | 2.2 / 9.0 / 9.5 | 5.7 / 26 / 50 | 35.1 / 114 / 239 |
| quadric collapse, greedy's count | 3,772,612 | 327 s | 2.1 / 12 / 31 | 2.2 / 14 / 18 | 3.2 / 14 / 149 | 26.3 / 139 / 314 |

Greedy insertion: **27 % fewer triangles than today**, and the error within 120 m of the tracks falls from a p99 of
23-170 cm to 9-10 cm. Beyond 500 m it is looser than today on average (35 vs 18 cm) by design: there the tolerance
grows with distance (1 m at 1.2 km), where the 10 m grid spends its triangles evenly.

One tile of 1,024 × 1,024 m beside the track at line 17's middle ((-749, -2299), 16 % of it covered by the
survey's ground areas), TOL 0.10 m. Errors in cm, mean / p99 / max per distance band:

| method | triangles | time | 0-10 m | 10-120 m | 120-500 m | beyond 500 m | cells over tol |
|---|---|---|---|---|---|---|---|
| now: 2 m blocks to 128 m, the 10 m grid beyond | 168,768 | - | 3.8 / 49 / 356 | 4.5 / 69 / 898 | 19.1 / 257 / 1388 | 14.7 / 137 / 301 | 15.5 % |
| RTIN (numpy, per-point tolerance) | 272,732 | 0.4 s | 1.9 / 9.3 / 14 | 1.8 / 9.4 / 18 | 3.3 / 24 / 68 | 10.1 / 40 / 62 | 0.29 % |
| greedy insertion (pydelatin, heights ÷ tol) | 149,628 | 0.3 s | 2.5 / 9.0 / 10 | 2.3 / 9.1 / 38 | 4.3 / 26 / 61 | 11.3 / 41 / 64 | 0.31 % |
| quadric collapse (pyfqmr) to the same count | 149,628 | 3.4 s | 2.3 / 14 / 99 | 2.5 / 18 / 236 | 1.5 / 12 / 126 | 1.7 / 10 / 108 | 1.1 % |

The corridor tolerance sets the count (greedy, the same tile): 5 cm 275,191 triangles, 10 cm 149,628, 20 cm 77,317.

- **Greedy insertion** (Garland-Heckbert: insert the worst cell until every cell is within tolerance) holds the
  tolerance within 10 m exactly and needs **half RTIN's triangles** for the same error. A per-point tolerance
  is had by meshing heights divided by `tol(d)` with one max error of 1: exact where `tol` is constant, and
  0.3 % of the cells end over their tolerance where a triangle reaches across `D0` (the 10-120 m band's 38 cm
  maximum). The build closes that with a second pass: the cells over tolerance get a smaller `tol` and the tile
  is meshed again.
- **RTIN** is the one without a dependency (numpy, written for the bench), but its triangles are halves of
  squares: it needs 1.8 × the triangles, and its error is not a bound (14 cm max at a 10 cm tolerance).
- **Quadric edge collapse** reaches a count, not an error: at greedy's count it spreads the triangles evenly
  (better far out, 1.5 cm mean beyond 120 m) but leaves walls and cutting edges off by up to 2.4 m in the corridor
  (1.1 % of the cells over tolerance); it starts from the full 1 m mesh (1 M vertices a tile).
- **The decision:** greedy insertion. As a library, `pydelatin` (MIT; wheels for Windows / Python 3.12; numpy
  only), a new build dependency, or the same algorithm in our own tool (a priority queue of triangles by their
  worst cell; plain Python runs per inserted point, ~75 k a tile, so it needs compiled code). Question 1.

**Tiles must meet.** Each tile meshed on its own picks its own vertices along the shared edge, so neighbours open
cracks. The build fixes the border: the tile edge's cells are meshed as a 1-D greedy polyline first (shared by
both tiles), then each tile's interior with those vertices fixed (the greedy start set). pydelatin takes no
fixed vertices; our own implementation would, which weighs for question 1.

## 2. The survey and the terrain together

`ground_cut.py`, the same tile: the greedy mesh cut by the survey's 354 level-0 ground areas.

- 149,628 terrain triangles: 38,219 lie under the survey (dropped), 17,164 cross its edges, 94,245 untouched.
- The crossing ones' remains, 17,546 pieces, each part of one planar triangle, are triangulated by shapely's
  constrained Delaunay without interior points: 32,778 triangles. The terrain after: 127,023 (-15 %), no area
  left over the survey.
- 7.7 s for the cut on this tile (+0.6 s the cover): offline, the corridor tiles of a line in minutes.

This replaces T3's lattice cut (whole 1-2 m cells, cut cells triangulated): the cut runs on the simplified mesh,
so the terrain keeps its triangle count instead of every lidar sample becoming a vertex.

## 3. The track profile and cant: moved to Python

What the page computes at load today (src/ references as of 8f9e4c3):
- `trackStyles` (`src/heights.js:76`, ~40 lines): the track style per section and `lift(s)`, the rail over the surface;
- `Profile` (`src/terrain.js:295-630`, ~300 lines): the surface sampled every 2 m, bridges and decks, soffit
  clearance, tunnels, the 9 % grade limit, vertical curves (up to 300 passes), then `data.heights` from
  `tools/line_heights.py` where the line has them (only line 17 does);
- the cant (`Route.prepareCant`, `src/route.js:281`, ~30 lines) over the smoothed route (`smoothPolyline`,
  `extendAlongTracks`, `src/route.js:10-110`) and the speeds;
- `carveCorridor` (`src/terrain.js:640`, ~100 lines), `flushDtm` (`src/world.js:956`, ~150 lines), the lowering
  (`src/world.js:913`, 1456).

All of it is plain math over typed arrays, but it reads the survey through `DtmSurface`, which triangulates with
three.js (`ShapeUtils`). The simulation reads only lookups: `profile.height`, `grade`, `heightAt`, `onBridge`,
`route.rollAt`, `cantAt`, `radiusAt`, and the ground under cars and walkers.

The two paths:

| | the build runs the page headless and exports | the rules move to Python |
|---|---|---|
| what moves | an export call in the page; the build waits for a page load per line (~28 s, line 17) | Profile, styles, cant and the route smoothing to `tools/`; carve, flush and lowering are not ported: the fused ground makes them unnecessary |
| what stays one implementation | the rules stay in JS | the rules are in Python; the page keeps the lookups over arrays from the data |
| the order | the page's Profile reads the old layers (10 m grid, 2 m blocks, survey) that the new ground replaces: the old layers would stay as build inputs | the profile reads the sources the ground build reads (IPR, the survey), before the ground is fused |
| the toolchain | Chromium in every rebuild | Python only; `tools/track_profile.py` (the vertical-radius solver) and `tools/line_heights.py` are already there |

- **The decision:** the rules move to Python, one at a time, each with a parity check against the page's result
  on every line (a headless export used by that check only, removed with the page's code). The page then loads
  `z`, `grades`, the cant and the bed from the line's data and keeps no profile rule.
- The cant depends on the smoothed route, so the route smoothing moves with it (question 2).

## 4. The format

The greedy mesh of the tile above (149,628 triangles, 75,004 vertices):

| encoding | bytes |
|---|---|
| float32 vertices + uint32 indices, as three.js takes them | 2,632 kB, gzip 1,647 kB |
| integers: vertices row by row as differences (cm heights), indices as differences, varints | 921 kB, gzip 478 kB, xz 409 kB |

3.2 bytes a triangle after gzip. The difference encoding is decoded into the same typed arrays at load. #307's
GLB with quantisation is compared on this mesh there; the format is decided after it (question 3).

## Questions for the user

1. **The greedy mesher:** pydelatin as a new build dependency (MIT, a wheel, numpy only; no fixed border vertices,
   so tiles are stitched afterwards), or our own implementation in the build (fixed border vertices; compiled
   code or numba, also a new dependency, since plain Python is too slow)?
2. **The profile in Python:** move the route smoothing and the cant with it (the page then computes no route
   geometry), or the cant only, over a route the build exports?
3. **The corridor tolerance:** 10 cm (150 k terrain triangles per km² beside the track) or 5 cm (275 k)?

## What it changes

Nothing yet: two benches in `tools/bench/`. The build tool and the page's loading follow in #276 once the answers
are in.
