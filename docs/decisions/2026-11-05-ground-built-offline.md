# The ground built offline: the terrain mesher, the profile in Python, the format (#276)

Status: accepted by the user, 2026-11-06 ("Pydelatin it is"; the mesher, the profile in Python, 10 cm); the format: [integer differences](2026-11-06-tile-container.md), #307.

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

## 1. The terrain mesher: greedy insertion, the line's whole box at once

Line 17's whole terrain box (7.1 × 15.4 km; every cell had IPR lidar), TOL 0.10 m, in 112 tiles of 1,024 m meshed
on their own. Errors in cm: the mean over all cells / the median tile's p99 / the worst tile's p99:

| method | triangles | time | 0-10 m | 10-120 m | 120-500 m | beyond 500 m |
|---|---|---|---|---|---|---|
| now (as the bench models it: 2 m to 128 m, 10 m beyond) | 5,145,063 | - | 4.3 / 33 / 335 | 2.8 / 28 / 71 | 18.1 / 137 / 345 | 17.8 / 136 / 260 |
| RTIN | 7,236,156 | 39 s | 1.9 / 9.4 / 10 | 1.8 / 9.4 / 9.6 | 5.0 / 28 / 39 | 30.6 / 134 / 282 |
| **greedy insertion** | **3,803,712** | 10 s | 2.4 / 8.8 / 9.2 | 2.2 / 8.9 / 9.5 | 5.9 / 27 / 46 | 35.3 / 123 / 244 |
| quadric collapse, greedy's count | 3,921,312 | 335 s | 2.5 / 14 / 171 | 2.6 / 15 / 34 | 3.6 / 19 / 138 | 26.0 / 135 / 314 |

**The whole box as one greedy mesh** (one call on 109 M cells: 18 s, after 224 s reading the raster):
3,746,981 triangles; mean / p99 / max 2.4 / 8.8 / 10.0 cm within 10 m, 2.2 / 9.0 / 55 cm at 10-120 m, 5.9 / 28 /
82 cm at 120-500 m, 36 / 175 / 376 cm beyond; 0.15 % of the cells over their tolerance.

- **Greedy insertion** (Garland-Heckbert: insert the worst cell until every cell is within tolerance): **27 % fewer
  triangles than today**, and the error within 120 m of the tracks falls from a p99 of 28-33 cm (335 cm in the
  worst tile: walls, cutting edges) to 9 cm. Beyond 500 m it is looser than today on average (35 vs 18 cm) by
  design: the tolerance grows with distance (1 m at 1.2 km), where the 10 m grid spends its triangles evenly. It
  needs half RTIN's triangles for the same error.
- **The per-point tolerance** is had by meshing heights divided by `tol(d)` with one max error of 1: exact where
  `tol` is constant; 0.15 % of the cells end over theirs where a triangle reaches across `D0` (the 55 cm maximum at
  10-120 m). The build closes that with a second pass: the cells over tolerance get a smaller `tol`, meshed again.
- **RTIN** is the one without a dependency (numpy, written for the bench), but its triangles are halves of
  squares: 1.9 × the triangles, and its error is not a bound (14.5 cm max at a 10 cm tolerance on the tile below).
- **Quadric edge collapse** reaches a count, not an error: at greedy's count it spreads the triangles evenly
  (better at 120-500 m) but leaves walls and cutting edges off by up to 1.7 m in the corridor; it starts from the
  full 1 m mesh.

One tile of 1,024 × 1,024 m beside the track at line 17's middle ((-749, -2299)), errors in cm, mean / p99 / max:

| method | triangles | time | 0-10 m | 10-120 m | 120-500 m | beyond 500 m | cells over tol |
|---|---|---|---|---|---|---|---|
| now | 155,573 | - | 5.4 / 117 / 711 | 3.1 / 57 / 663 | 22.2 / 279 / 1388 | 13.4 / 117 / 301 | 16.7 % |
| RTIN | 234,944 | 0.5 s | 1.9 / 9.5 / 14.5 | 1.0 / 8.8 / 16 | 4.5 / 27 / 62 | 9.3 / 41 / 58 | 0.31 % |
| greedy insertion | 129,380 | 0.2 s | 2.2 / 8.7 / 10.0 | 1.5 / 8.7 / 16 | 5.5 / 28 / 61 | 10.4 / 34 / 44 | 0.39 % |
| quadric collapse | 129,380 | 2.9 s | 2.6 / 34 / 188 | 1.7 / 16 / 159 | 2.1 / 15 / 247 | 1.8 / 11 / 52 | 1.1 % |

The corridor tolerance sets the count (greedy, the same tile): 5 cm 239,709 triangles, **10 cm 129,380 (the
user's pick, 2026-11-06: "10cm sounds good enough now")**, 20 cm 65,983.

**Tiles from one mesh.** Tiles meshed on their own pick their own vertices along a shared edge, so neighbours
crack. Meshing the line's box once and cutting it along the tile lines avoids that: both tiles cut the same
triangle along the same line, so they share the border's vertices exactly. On line 17's box cut into 1,024 m
tiles, 28,435 triangles cross a tile line and become 81,764 (+53,329, **+1.4 % of the mesh, 1.6 s**). No fixed
vertices are needed, so no mesher of our own.

**The whole city, measured** (`tools/bench/terrain_city.py`; IPR's raster, 35,001 × 26,001 cells, 660 km² with data;
the tolerance from the 355 km of tram track in OSM; the user, 2026-11-06: "My only concern is hardware resources"):

| | |
|---|---|
| triangles | 18,321,030 (9,160,703 vertices); line 17's densities per distance band scaled by the city's areas gave 18.3 M beforehand (`tools/bench/city_area.py`) |
| time | 7 min on this PC: the distances 173 s, reading the raster 39 s, the mesh 197 s |
| peak memory | 13.9 GB (the raster as float32 3.4 GB, the rest pydelatin's) |
| download, at the 3.4 bytes a triangle of section 4 | ~62 MB gzip for the whole city's terrain, before the survey's cut |

| from the tracks | triangles |
|---|---|
| 0-10 m | 523,650 |
| 10-120 m | 6,715,291 |
| 120-500 m | 8,345,645 |
| 500-1000 m | 1,383,954 |
| 1-2 km | 481,649 |
| over 2 km | 283,054 |
| tiles with no lidar at all | 587,787 |

So the build does not need blocks or stitching: the city is one mesh, cut into tiles. A rebuild needs it only when the
raster or the tolerance's tracks change, so it is a step with its own cached output, not part of every line's build. The
tolerance follows the tracks: when buses and trains get their corridors, the same run covers them, and at the corridor's density
(~200 k triangles per km²) all 660 km² would be 130 M triangles at most, which needs a coarser tolerance off the routes.

**The decision: greedy insertion with `pydelatin`** (MIT; a wheel for Windows / Python 3.12; numpy only), a new
build dependency (the user's pick), over the whole city once, cut into tiles afterwards.

**Our own compiled mesher, weighed and not taken:** its gain would be fixed border vertices and an exact per-point
tolerance (no division trick, no second pass). The cut above makes the first unnecessary, the second pass costs
one more call. Its costs: a build step on every machine that rebuilds (a C extension needs the MSVC build tools;
numba is a ~50 MB dependency with llvmlite that follows new Python releases late), and a port of the algorithm
for us to test and keep.

## 2. The survey and the terrain together

`ground_cut.py`, the same tile: the greedy mesh cut by the survey's 354 level-0 ground areas (16 % of the tile).

- 129,380 terrain triangles: 37,142 lie under the survey (dropped), 16,003 cross its edges, 76,235 untouched.
- The crossing ones' remains, 16,369 pieces, each part of one planar triangle, are triangulated by shapely's
  constrained Delaunay without interior points: 30,899 triangles. The terrain after: 107,134 (-17 %), no area
  left over the survey.
- 5.9 s for the cut on this tile (+0.5 s the cover): offline, the corridor tiles of a line in minutes.

This replaces T3's lattice cut (whole 1-2 m cells, cut cells triangulated): the cut runs on the simplified mesh,
so the terrain keeps its triangle count instead of every lidar sample becoming a vertex. The tile cut above is
the same operation with the tile lines.

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
- **The route geometry moves too, and the page reads it as it is** (the user, 2026-11-06: "I want to prebuilt as
  accurate and smooth as possible, so no further smoothing should be needed. Ideally the server prepared data
  should closely match the browser running version"). The page already draws surveyed track and the build's
  curves (`trackCurve`, #204) unsmoothed, resampled only (`src/route.js:94-110`); what it still smooths is OSM
  fill without the build's curves. After #237 (the track from DI) the build draws all of it, the cant is
  computed from the built geometry, and the page smooths nothing. A check holds it: the page's resampling of the
  built route moves no point by more than 1 cm, and the page's own cant and profile from the built data match the
  built ones (the parity check above).

## 4. The format

The greedy mesh of the tile above (129,380 triangles, 64,882 vertices):

| encoding | bytes |
|---|---|
| float32 vertices + uint32 indices, as three.js takes them | 2,276 kB, gzip 1,411 kB |
| integers: vertices row by row as differences (cm heights), indices as differences, varints | 796 kB, gzip 424 kB, xz 364 kB |

3.4 bytes a triangle after gzip. The difference encoding is decoded into the same typed arrays at load. #307's
GLB with quantisation was compared on this mesh and lost by 17 % after brotli: [the tile container](2026-11-06-tile-container.md).

## What it changes

The benches in `tools/bench/` (they need `pydelatin` and `pyfqmr`), and the city's terrain mesh, built offline into
the machine cache by `tools/city_terrain.py` (#428; nothing in the game reads it yet). The page's loading follows in
#276.

**The city mesh as built** (#428, 2026-11-10; IPR's raster, DI's 335 km of track; the whole city in 13 min, 15.0 GB):
16,646,113 triangles, no cell over its tolerance. Two changes to section 1, both measured:
- **(z − base) / tol(d), not z / tol(d):** the base is the ground smoothed over ~1 km. Divided by a tol that grows with
  d, the heights themselves bend even a plane, and the mesher spends triangles on the bend. On a 3 × 3 km box by line 17
  the base gives 1,475,219 triangles against 1,600,628 (120-500 m: 640,119 against 753,103), and 0.14 % of the cells
  over their tolerance after pydelatin against 0.51 %. The city: 16,496,105 triangles from pydelatin against the
  bench's 18,314,418 (17,733,132 without its tiles with no data).
- **The second pass inserts cells, it does not mesh again:** each triangle with a cell over its tolerance takes its
  worst cell as a vertex (split in three, or in four with its neighbour on an edge). The city: 1,513,496 cells over
  (0.23 %) after pydelatin, 76,391 vertices added in 17 rounds.

| from the tracks | triangles | error mean / p99 / max (cm) |
|---|---|---|
| 0-10 m | 511,551 | 2.4 / 8.7 / 10.0 |
| 10-120 m | 6,611,342 | 2.4 / 8.9 / 10.0 |
| 120-500 m | 7,452,617 | 5.8 / 25.0 / 41.7 |
| 500-1000 m | 1,324,496 | 14.1 / 52.1 / 83.2 |
| 1-2 km | 477,763 | 28.8 / 104.3 / 166.0 |
| over 2 km | 268,344 | 65.4 / 219.4 / 300.0 |

**No passages rule in the city mesh** (the user, 2026-11-10: "I would lean towards keeping IPR lidar everywhere to keep
the actual lowest points. Then bridge the gaps on streets and track/rail passes with other data including dmr5g showing
the deck height. But we can keep the culvert passing under", then "point 1 yes"). IPR's ground stays everywhere: the
floors of underpasses and culverts, and the streets through building passages. A street or track over a passage becomes
a deck in #276's partition (step 3). Measured by `tools/bench/terrain_compare.py --passages` on the snapshot's 263 DMR 5G
tiles, the rule (`fine_terrain.py`'s) took 161,164 cells inside the city:
- **Under buildings:** for building passages, 89 % of the cells it took lay in OSM buildings. It raised the hidden ground
  there by a median 1.5 m, up to 14 m, where both models only interpolate.
- **Not a deck:** it took roofs (`covered=yes`) and garages (`layer<0`) as surfaces.
- **No tunnel:** 9.6 % of its cells lay on proposed or disused ways.
- **Where it was right:** only 26 % lay under a street, rail, footway or track, where the deck is needed.

The first build above still had the rule. Without it, the city has 16,566,821 triangles (79,292 fewer). The bands'
errors are the same to 0.1 cm, and the build took 807 s with a 14.8 GB peak.
