# The network as a layer the build makes (#658)

Status: **accepted** with the user's answers (Claude Code session 2026-11-18), quoted at the end: (a) the port, heights
stored, one file a line.

## Why

The user, 2026-11-17 (#654): "I realize when the game was keeping all the data it was easier to work with it for both
driving and putting correctly sized platforms on top. So the lanes, footpaths, basically the whole network graph for
different transport modes will have to come as lightweight metadata layer and be used together with the single drawn
grown surface. A lot of work but seems like it should be divided this way. Game start won't build anything new, only
place things on the settled surface and use data to drive traffic there."

Each Start builds the network from the survey: roads fitted to their kerbs, lanes, footways, their links, doors,
signals bound to lanes, platforms and their stop types (#658's table). Those reads go through the ground's lookups.
Until #657 the tile window (#30) trimmed them:
- A player's Start judged 3-24 platforms a line surveyed, out of the 39-120 that every check sees.
- It fitted the lanes with most of the survey missing.

#657 keeps every lookup instead: 48 MB on line 37, 120 MB on line 17 (`tools/bench/ground_tiles.py`). The ground's
tiles are drawn as streamed, and only this build needs the rest.

The [architecture](../architecture.md) §1 already puts the road lane graph, the footpath graph, stops, platforms,
signals and doors in the world compiler, "all placement heuristics" with them. Its runtime "trusts the data". This
note is the step that does it for what Start builds.

## What Start builds, measured

`tools/bench/network_layer.py` (main 279e609). For each line it does three things:
- starts a shift as a player does;
- builds the network again, timed;
- counts the survey's reads and writes the network out as plain JSON (positions in cm).

| line | Start | the network built again | the platforms | `classAt` reads | `covered` | `classUnder` | roads | lanes | footways (of them links) | doors | lanes with a signal | platforms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 9 | 6.5 s | 5.5 s | 31 ms | 2.74 M | 112 k | 82 k | 2,125 | 3,473 | 13,559 (9,452) | 4,565 | 174 | 121 |
| 17 | 4.1 s | 3.7 s | 33 ms | 2.56 M | 110 k | 23 k | 1,986 | 3,395 | 10,326 (7,062) | 2,920 | 109 | 85 |
| 22 | 5.7 s | 5.2 s | 39 ms | 2.61 M | 113 k | 130 k | 2,251 | 3,538 | 14,060 (9,890) | 4,641 | 147 | 85 |
| 23 | 3.1 s | 2.6 s | 13 ms | 1.01 M | 43 k | 128 k | 963 | 1,436 | 5,425 (3,714) | 1,563 | 29 | 44 |
| 37 | 2.1 s | 1.7 s | 15 ms | 1.19 M | 54 k | 2 k | 1,018 | 1,718 | 5,698 (3,942) | 1,534 | 62 | 40 |

Most of a Start is this build: the second build alone takes 81-91% of the whole Start's time. The platforms' share is small, 13-39 ms.

The reads are the survey's classes along and across every road and footway:
- `_fitRoad`: 65 samples across ±16 m every 4 m;
- the kerb-offset footways: 0.5-8 m off the kerb every 3 m;
- an OSM footway: every 2 m.

The platforms read the classes beside the track (`vienna`, the surveyed check, the shelter's edge every 0.25 m).

None of it is random: the build never calls the run's RNG. Its first use is `_chooseNext`, as cars drive. The lazy
parts are filled in a run's order, but each value is the same in every run:
- connectors between lanes;
- conflicts;
- a path's crossings.

So the network is a function of the data alone, and the build can make it once. `tools/test_network_layer.py` holds
it on line 37: the network built twice comes out the same, and neither build calls the run's RNG or `Math.random` (but for
Three.js's object ids).

## 1. Where the network is built

**(a) Ported to Python** (`tools/network.py`, run by `rebuild.py` after `placement.py`):
- It follows #22's pattern: `placement.py` decides the platforms, signals and stop types at build time. The page ran its
  own rule beside it (`placementDiffs`, required empty by `tools/test_placement.py`) until the build's was trusted.
- What moves is about 790 lines of the page:
  - `src/traffic.js`, 628 lines: the constructor's graph part 223, `_fitRoad` 81, `_stopLine` with `_stopLineAt` 64,
    `_linkWalks` 45, `_findDoors` 45, `_bindSignals` 43, `_bindPedHeads` 36, `_buildLanes` 33, `laneOffset` 21,
    `_parallelWays` 19, `_trackLats` 18;
  - `src/platforms.js`, 164 lines: `buildPlatforms` 60, `buildStop` 49, `platformStrip` 36, `vienna` 19.
- The build reads the survey from `data/lineN.dtm.json` with shapely, as `placement.py` does, not through the ground
  file's lookups.
- A parity test compares the build's network with the page's on every line, as long as both exist.

**(b) The page's own code, run by the build:**
- The network code moves into modules without Three.js or the DOM (`src/network/`); the page imports them.
- A build step loads them in headless Chromium (as `tools/headless.py` loads the game) with the ground file's
  lookups, and writes the result.
- There is no port and nothing to keep in parity, and the modules are a first part of the architecture's §4 core.
- The world's build would then need a browser: today only the checks do.
- AGENTS.md allows Node or Deno only once the simulation core is split out; this step would start that split.

**Recommended: (a).**
- The build stays one language with one survey reader (`placement.py`'s).
- The rules become build rules a test can hold, as the placement's did.
- The parity test is the proof the user asked for in #658 ("the build's lanes are the page's lanes"). It runs only
  until the page's code is removed.

## 2. What the layer holds

One file a line, `data/lineN.network.json`, beside `lineN.json` and the ground file. Each mode's graph:
- **roads:** the joined OSM ways, each with its fitted kerbs and median (the page's `fitLo`, `fitHi`, `fitMed`) and
  the tracks' lateral positions on it;
- **lanes:** each lane's path, its road and direction, its two junctions;
- **footways:** paths with their links at each end (crossings and joins as link footways), doors on them;
- **signals:** a lane's signal and head, its stop line; pedestrian heads bound to crossings;
- **platforms and stops:** placed, with their stop types: `placement.py` writes most of this into `lineN.json` today.

Positions are in cm, in the city frame. **Heights are stored** on every point:
- They come from the build's own ground surface (`ground_mesh.py`'s, the same file the page draws).
- A car or a walker then stands on the data without reading the ground's lookups.
- A road on a deck or in a tunnel keeps its level, as `ground.way` gives it now.

Things placed near the camera (a platform's mesh, a head on its pole) still sit on the drawn ground.

Size (the bench, plain JSON, before heights):
- 3.5-9.3 MB raw a line, 1.4-3.4 MB gzip, 0.76-1.82 MB brotli.
- Footways are half of it, lanes a third, roads an eighth.
- The ground file is 12 MB raw, 6.7 MB brotli on line 37.
- The lookups it frees take 48-120 MB of memory (#657).

A line's network loads whole at the menu, beside `lineN.json`. A
city-wide network would be split by tile like the ground (the architecture's "small city-wide network index"). One
line's does not need it.

## 3. What Start does then

- Start reads the layer, makes the paths and their indexes, and binds them to the shift's game:
  - which stops are ours;
  - the signals' phases;
  - the cars.
- It reads no survey: `classAt`, `classUnder` and `covered` are not called while a shift is built, and a test holds it.
- The tile window trims the lookups again (as before #657); `tools/bench/ground_tiles.py` shows their MB back near the
  drawn tiles'.

## 4. Steps

Each step is its own PR, with its tests and the parity test on every line. Each step moves only its part, so a step's
seeded `u3,redruns,traffic,stops` should not move outside main's spread.

1. This note, and the bench.
2. Roads: joined, fitted, and the tracks on them; the parity test's frame.
3. Lanes and junctions; the page builds its lanes from the layer.
4. Footways, links and doors.
5. Platforms and stops: `placement.py`'s placement drawn as placed, the page's rule (`vienna`, the surveyed check) gone.
6. Signals: stop lines, heads, pedestrian heads.
7. Start reads only the layer. The lookups are trimmed to the window again, and the test of the reads is added.

## The user's answers (2026-11-18, PR #665)

To 1: "sounds good, go ahead with the port". To 2: "yes". To 3: "yes".

The questions were:

1. Where is the network built: (a) ported to Python in the build, beside `placement.py` (recommended), or (b) the
   page's code moved into modules without Three.js and run by the build in headless Chromium?
2. Heights stored in the layer from the build's ground (recommended), or read from the drawn ground as now?
3. One file a line now, split by tile only when lines share a city network: agreed?

## How it went (2026-11-18)

- **Steps 2-6** (#667, #668): the port, every part the page's to the cm on lines 9, 17, 22, 23 and 37.
- **The page switched in one step** (step 7, the user: "go with the switch as recommended"), after the parity held. The
  page's own builders went.
- **Heights: read from the drawn ground at the load, not stored.** Answer 2 chose stored heights. Measured against the
  page, the ground file is not yet the surface the page settles things on:
  - the page fits the road tunnels' mouths into it (src/structures.js mouthFix);
  - beside the route, the page's `ground.at` takes the track's profile.
  The file's heights stood up to 7.8 m off at a pedestrian head by the Blanka tunnel's mouth (line 17), 2.2 m at a
  tunnel's portal and 2.8 m at a bridge's abutment beside the route. The page therefore reads them itself at the end of
  the load, while every tile's lookup is held: the bridges' and tunnels' ends, the signal heads, the platforms' strips and
  signs. What moves with the set or the signals (our stops' signs and shelters, a signal on a pole past 9 m from the
  track) settles once its tile's lookup comes (`ground.later`). Cars and walkers read the ground where they are, which
  is always in the window. Heights can move into the layer once the build makes the settled surface (the mouths in the
  ground file).
- **Measured** (`tools/bench/network_layer.py`):
  - Start takes 0.4-1.1 s on the five lines, against 2.1-6.5 s.
  - The lookups held after it are 9-17 MB, against 48-120 MB.
  - No read at Start misses a tile.
