# Architecture proposal: from one line to a city network

Written in the remote session (2026-10-24) for the original project, after a long stretch of work on
line 17: performance, signals, traffic, pedestrians, weather and OSM data. The companions are
`REMOTE-CHANGES.md` (what changed, by section), `BUILD-TOOLS-HANDOFF.md` (build-side to-do list and
test procedure) and `PERF-ANALYSIS.md` (numbers).

## 0. Where the project stands

**Strengths**
- Built from real data: OSM, the DTM street survey, Geoportál buildings and the PID timetable. Many
  details (run cards, the Czech light sequence, signal phases) give it a feel hand-made worlds rarely
  have.
- No build step means fast iteration.
- The seeded headless benches (`tools/bench/*.js`) found every real bug in this session. They are
  the most valuable tool the project has.

**The recurring problem**
- Most fixes in this session were the runtime guessing at meaning from imperfect data:
  - where a signal really stands;
  - where a stop line goes;
  - whether a crossing really crosses the track;
  - which projection a dataset uses.
- Each fix is a heuristic with a line number in a comment.
- That works for one line. It won't hold up for a city network.

## 1. Split the project into a world compiler and a runtime

**The compiler (offline, `tools/`)** turns raw sources into clean, checked meaning:
- **One geo module** for all coordinate conversion. Two different formulas in two tools caused up to
  45 m of error (handoff §1).
- **One semantic model:**
  - track graph, road lane graph, footpath graph;
  - stops and platforms, signals and junction controllers, crossings, doors.
  - Every feature is attached to a **network edge** with an offset, not to a line's route position.
- **All placement heuristics live here,** with a validation report on every build (handoff §3).
  Today they live in `game.js` (`_placeSignals`, the platform rule) and `traffic.js` (`_stopLine`,
  `_bindSignals`).
- **Output:** versioned schemas (`schemaVersion` in every file), compact binary tiles (PERF §6) and a
  small city-wide network index.

**The runtime** trusts the data, simulates and draws. Its remaining heuristics are safety nets that
log what they do.

Data bugs then surface at build time ("71 crossings without a match"), where someone can look at a
map, instead of as a collision in seed 2.

## 2. Model a network, not a line

Today everything is a position along one route: signals, stops, conflicts, platforms, even the
traffic spawn. For many lines:
- **A track graph:** nodes at switches, crossings and the ends of tracks; edges with geometry,
  gradient, speed limits and clearance. A vehicle's position is `(edge, offset)`.
- **Lines as paths over the graph,** taken from the timetable data. Each run follows its path.
  Switches are set by route requests, as at a real interlocking.
- **One controller per junction,** not per tram signal:
  - its inputs: tram requests (by radio or loop), car detectors, pedestrian buttons;
  - its outputs: the tram signal aspects, car heads and pedestrian heads;
  - its phases and priorities as data.
  - Several lines sharing a junction then work naturally (REMOTE-CHANGES §16 lists that gap).
- **Route-relative views** (distance to the next signal, stop or crossing) are computed from the
  graph for each vehicle's path. The tram UI and autopilot keep their current simple interface.

## 3. Level of detail for the simulation, not just the graphics

Simulating a whole city at full detail won't be playable. Use three tiers with clean handoffs:

| tier | where | what runs |
|---|---|---|
| **Micro** | ~1 km around the player | Full tram physics, lane-level cars, walkers, signal phases (today's code) |
| **Meso** | the rest of the nearby network | Trams as block-section movers obeying signals and dwell times; cars as flows and queues per link |
| **Macro** | the rest of the city | The timetable plus a delay model; passengers as counts per stop |

- Vehicles and passengers change tier as the player moves, **keeping their state**: delay, load, run
  number, destination. A tram met at Palackého náměstí then really came from Modřany, 3 minutes late
  and full.
- A handoff must not teleport anything visible. Promote at the edge of the micro area, and fade
  where nothing can be promoted cleanly. The camera spawn ring is the first version of this.

## 4. Separate the simulation core from rendering

- **A fixed-step, deterministic core** with no Three.js inside it, and seeded random numbers
  everywhere (the benches depend on that; `Math.random` must not leak into the simulation).
- **State in flat typed arrays** (structure of arrays) for the numerous things: cars, walkers,
  passengers. The WASM benchmark (PERF §9) showed data layout matters more than the language. WASM
  is worth it only for hot kernels later.
- **The core runs in a Web Worker;** the renderer reads a state snapshot each frame. Then:
  - rendering and tile loading stop competing with the simulation;
  - the same core runs **in Node** for tests and CI;
  - replays and recorded bug scenes come almost for free (seed + inputs).
- **Systems with explicit interfaces:** TrackNetwork, Interlocking (junction controllers),
  Vehicles, RoadTraffic, Pedestrians, Passengers, Weather, Scoring. They talk through queries and
  events, not by reaching into each other: today `traffic.js` reads `game.signals`, `game.stops` and
  `game.tram` directly, and `game.js` reads `traffic.carsCrossing`.

## 5. A streaming world

- **500 m tiles** loaded ahead of the vehicle and unloaded behind it. Sizes are in PERF §6: ~0.1–0.2
  MB each on average, ~1 MB in the centre, data that arrives GPU-ready.
- **A GPU memory budget** with mesh levels of detail (buildings and DTM at distance). This is the
  real answer to "what if GPU memory runs out". REMOTE-CHANGES §14 covers the lost-context
  handling meanwhile.
- **Startup in seconds:** ~12–16 tiles around the start.

## 6. Other modes of transport

- **Buses and trolleybuses:** vehicles on the lane graph with stops and timetables. The car logic,
  lights and giving way already exist.
- **Metro and trains:** mostly the meso and macro tiers. Little geometry underground, but their
  stations matter as entrances, passenger sources and transfers.
- **One passenger model across all modes:**
  - demand from the timetable and land use (building classes are already in the data);
  - origin–destination counts, transfers, crowding.
  - A crowd at a stop is then consistent: people waiting for line 17 differ from those for line 3.

## 7. Realism per unit of effort

Ranked by impact versus cost:
1. **Sound:** `src/audio.js` synthesises the tram (motor, rolling, rail joints, flange squeal, bell,
   doors), but it is very simplified and does not sound like a real T3 (user, 2026-10-24).
   - **The tram itself:** move from pure synthesis to recorded or sampled sources layered by speed and
     load: the traction motor and its accelerator and resistor-stepping steps, gear whine, the
     compressor cycling, the brakes, door mechanisms, bogie noise over switches and joints, and the
     flange squeal in curves.
     - Pitch and blend layers by speed and current.
     - Model the space: in the cab vs outside, tunnels, under bridges, open streets.
     - Licensing matters: own recordings of a T3 (the cab, standing at stops, passing) are worth
       planning.
   - **The city around it:** passing cars and their horns, crossing ticks, crowds at stops, rain and
     wind, the other trams.
   - The sound system should read the same simulation state the renderer does (§4), so it works with
     the Worker split.
2. **Light:** time of day and the lighting that comes with it.
3. **Dispatcher-driven operations:** delays, short turns, diversions, disruptions on the network.
4. **Coherent traffic and pedestrians around junctions:** mostly done now; walkers crossing the
   tracks with push buttons come once junction controllers exist.
5. **Cab procedures, weather and adhesion:** already started.

## 8. A possible order

1. **Hygiene:**
   - a remote for git (§9);
   - the shared geo module;
   - the benches running in Node (they need a headless core, or Playwright first);
   - JSDoc types with `tsc --checkJs` in CI.
2. **Compiler and semantic model for line 17 only,** with the runtime consuming it. The runtime
   heuristics stay as logging fallbacks; the benches must stay green.
3. **Tiles and streaming.**
4. **Track graph,** several lines, controllers per junction.
5. **Simulation tiers and the Worker.**
6. **Buses,** then the city-wide passenger model and the other modes.

Each step keeps the game playable, and the benches show whether it still behaves.

## 9. Working from several computers and with several agents

### Repository and data
- **Put the repository on a private remote** (GitHub or GitLab; or a bare repository on a NAS or
  server reachable by SSH). Everything goes in: `src/`, `tools/`, benches, docs, launch configs.
  This session started from a partial deployment copy with no tools and no history: that is the
  failure to avoid.
- **Large and raw data outside the code history:**
  - `raw/` (OSM caches, DTM, GTFS) and generated `data/*.bin`/`*.json` either in Git LFS, or in a
    shared store (cloud drive, NAS, S3-like bucket);
  - a committed `data/MANIFEST.json` with file, size, sha256, source and date;
  - a `tools/fetch_data.py` that downloads or verifies against the manifest;
  - generated files are reproducible from `raw/` plus the tools, so the manifest also records which
    tool version built them.
- **The deployment** is built from a tag, never edited in place. A deployed copy can be traced to its
  commit if a file `VERSION` carries the commit hash.

### Branches and reviews
- `main` always passes the benches. Every task goes on its own branch (`feature/…`, `fix/…`, `data/…`)
  and is merged by pull request, even when working alone: the PR is where the bench results and
  screenshots go.
- **One task, one branch, one agent.** Parallel agents work in separate **git worktrees** (Claude
  Code can make them), each on its own branch, so they never edit the same checkout.
- Split work so parallel tasks touch different files. Today `game.js` and `traffic.js` are hotspots
  that collide; the module split in §4 helps here as much as for design.

### CI
On every push and PR:
- the type check;
- a quick lint (syntax and unused code);
- the benches on line 17, seeds 1–3, with the thresholds from the handoff doc §4.2;
- a nightly longer run (more seeds, all lines) posting a report.

This needs the headless core (§4) or Playwright with Chromium in CI. Until then, run
`tools/bench/batch.html` on any machine.

### Instructions for agents (`CLAUDE.md` at the repository root)
- how to serve (the no-cache server), the test lines (17 first), and how to run the benches with
  their expected results;
- conventions: comment density, naming, every heuristic with its "why" and the place it was seen
  (line, s, seed);
- rules:
  - never edit generated data by hand;
  - the shared geo module for coordinates;
  - log every heuristic's decisions to the console;
- a **handoff convention:** a session that cannot commit (like this remote one) writes a
  `REMOTE-CHANGES.md`-style log with files, reasons and results. The receiving session applies it on a
  branch, runs the benches and merges.

## 10. Ground truth: an annotation editor that scores the rules

**Goal:** a world rebuilt from current open data by general rules, with as little hand editing as
possible. The editor therefore records **ground truth that the rules are scored against**, not edits
to the world. Hand work then improves every stop in the city, not the one that was looked at. (Until
now the truth came as screenshots painted over on a phone, e.g. Palackého náměstí, REMOTE-CHANGES §18.)

### 10.1 Three kinds of annotation

| kind | records | the build |
|---|---|---|
| `truth` | where a real thing is (a stop post, a signalled track crossing, a car stop line, …) | matches it with what the rules made: position error, missed, extra |
| `verdict` | a judgement on one built feature ("road-only crossing", "stop line right") | counts it as correct or wrong for that rule |
| `override` | "use this, whatever the rules say" | applies it, **only as a last resort**, and flags it as stale when the source data under it changes |

- **Reviewed areas:** polygons where the annotations are complete. Built features inside them with
  no truth are false positives, so precision is meaningful.
- **Fix the source where the source is wrong:** many failures are OSM gaps (crossings without a tag,
  missing stop lines and stop positions). Correcting OSM itself, following its rules, improves every
  future rebuild. The editor shows "looks like an OSM data issue" next to such a failure.

### 10.2 The editor

- **A static page in the repository** (`tools/annotate/index.html`, no build step) that works on a
  phone.
- **Base layer:** the orthophoto the project already uses, with its capture date always visible. A map
  library from a CDN (MapLibre GL or Leaflet).
- **Overlays, each toggleable:** OSM (from the build's cached raw data), the **compiled world** (§10.4),
  the annotations, and the validation flags (`osm_validate.py`, the build report).
- **A to-do queue:** "next flagged item" jumps to the next suspicious spot (a crossing inside a
  platform, a stop far from OSM, a signal kept short of its junction, a failed score). The user
  confirms, marks it wrong, or drags in the truth. Seconds per item.
- **A link to the game:** "open in game here" (`?line=17&debug&at=<s>`, F8 overlay) for what an
  orthophoto cannot show: heights, and what the driver sees.
- **Storage:** `annotations/lineN.geojson` in the repository (or per area once the network grows),
  reviewed in git like code. The editor saves through a download or upload until there is a small
  write endpoint.

### 10.3 Workflow

1. Build → **score** against the annotations → flag what is suspicious.
2. Work the queue in the editor: mostly verdicts, some truth points.
3. Change a rule → rebuild → compare the scores. Scores must not drop, and the benches keep behaviour
   safe.
4. Correct OSM where it is wrong; the next rebuild picks it up.
5. Overrides only for what no rule or source can get right; they expire with the source.

**Start:** ~20 hand-checked stops and junctions on line 17 (Palackého nám., Kublov, Hodkovičky,
Staroměstská, Čechův most, Přístaviště, Kobylisy, the four platform crossings of REMOTE-CHANGES §18,
…) as a reviewed area. That is enough to measure the current rules and pick the first one to improve.

**Lead to check:** whether IPR Praha or TSK publish open data on traffic signal installations or road
markings. That would cover the biggest gaps (tram signals, stop lines, zebras) from an authoritative
source.

### 10.4 Formats (shared by the build, the game's export and the editor)

Both are **GeoJSON FeatureCollections in WGS84** (RFC 7946: `[lon, lat]`), so the orthophoto, OSM, the
built world and the annotations line up without any game-specific conversion. The build converts with
the shared geo module (handoff §1.1): `y = (lat − lat0)·110574`, `x = (lon − lon0)·111320·cos(lat0)`.

**Feature types** (one vocabulary for both files):

| `type` | geometry | main properties |
|---|---|---|
| `tram_stop_point` | Point (on our track) | `stop` (name), `s` |
| `stop_post` | Point | `stop` |
| `platform` | Polygon, or LineString for an edge | `stop`, `side` (`left`/`right` of travel), `surveyed` |
| `shelter` | Point | `stop` |
| `tram_signal` | Point (the head) | `stopAt` (the route position the tram stops for it), `mount` (`kerb`/`span`/`platform_head`) |
| `tram_signal_stop` | LineString across the track | `signal` (id) |
| `track_crossing` | LineString, or Point where it crosses | `signalled` (bool), `kind` (`road`/`foot`) |
| `road_crossing` | LineString | `signalled`, `zebra` (bool), `fromPlatform` (bool) |
| `car_stop_line` | LineString across the lane | `heading` (degrees), `junction` (id), `source` (`osm`/`edge`/`short`) |
| `car_signal_head` | Point | `heading`, `junction` |
| `pedestrian_signal_head` | Point | `heading`, `crossing` (id) |
| `conflict` | Point (near edge, on the route) | `car` (bool) |
| `reviewed_area` | Polygon | annotations only |

**Common properties:**
- `id`: stable across rebuilds, so verdicts keep pointing at the right thing. It comes from the
  source where there is one (`track_crossing:osm:node/123`, `stop_post:pid:U388Z2P`), else from the
  rule and its input (`tram_signal:17:sig@12343`). As a last resort a spatial key: type + coordinates
  rounded to 2 m.
- `line`, `s` (route position, informative), `rule` (which rule made it, e.g. `platformEnd`,
  `junctionEdge`, `osmNode`), `build` (data and tool version).

**Compiled world** (`data/lineN.built.geojson`, written by the build; the game can export the same
from what it decided at run time, `window.exportBuiltGeoJSON()`, see `src/debugOverlay.js`):

```json
{ "type": "FeatureCollection",
  "properties": { "line": "17", "build": "2026-10-24 remote", "origin": [50.0655, 14.4273] },
  "features": [
    { "type": "Feature", "geometry": { "type": "Point", "coordinates": [14.41365, 50.07402] },
      "properties": { "id": "tram_stop_point:17:Palackého náměstí", "type": "tram_stop_point",
                      "stop": "Palackého náměstí", "s": 12360.5, "rule": "platformEnd" } } ] }
```

**Annotations** (`annotations/lineN.geojson`):

```json
{ "type": "FeatureCollection",
  "properties": { "line": "17", "imagery": { "source": "<orthophoto name>", "date": "2023-06-04" } },
  "features": [
    { "type": "Feature", "geometry": { "type": "Point", "coordinates": [14.41368, 50.07405] },
      "properties": { "kind": "truth", "type": "stop_post", "stop": "Palackého náměstí",
                      "author": "jt", "date": "2026-10-24", "note": "red dot in the orthophoto" } },
    { "type": "Feature", "geometry": null,
      "properties": { "kind": "verdict", "target": "road_crossing:17:@12353", "value": "wrong_type",
                      "correct": "road_crossing", "note": "zebra from the island across the road only" } },
    { "type": "Feature", "geometry": { "type": "Point", "coordinates": [14.41371, 50.07409] },
      "properties": { "kind": "override", "type": "tram_signal", "mount": "platform_head",
                      "basis": { "osm": "sha1 of the OSM elements within 30 m", "imageryDate": "2023-06-04" },
                      "reason": "on its own pole at the island tip, street view" } },
    { "type": "Feature", "geometry": { "type": "Polygon", "coordinates": [[[14.4131, 50.0735], [14.4142, 50.0735], [14.4142, 50.0746], [14.4131, 50.0746], [14.4131, 50.0735]]] },
      "properties": { "kind": "truth", "type": "reviewed_area", "covers": ["stop_post", "tram_signal", "track_crossing", "road_crossing", "car_stop_line"] } } ] }
```

- **Verdict `value`:** `ok`, `wrong_position` (add a truth point), `wrong_type` (with `correct`),
  `should_not_exist`, `missing` (with a truth point).
- **Scoring** (printed by the build per type, kept over time to spot regressions): match truth and
  built features of one type within a tolerance (stop posts and points 3 m, signals 3 m, stop lines
  2 m, crossings 3 m); report recall, precision inside reviewed areas, and the median and 90th
  percentile position error. Verdicts count directly.

## 11. Bringing this remote session's work home
This copy has no git:
1. Make a branch `remote/2026-10-line17` from the commit this deployment was made from (or from
   `main` if unknown).
2. Copy the changed files over. `REMOTE-CHANGES.md` lists them per section:
   - `src/`, `index.html`;
   - `.claude/` tools and benches;
   - `data/line17.signals.json`;
   - the three docs.
3. Diff against the branch. Where the original project has moved on in the same files, merge by
   section using the change log.
4. Run the benches (handoff §4.2) and the lints (with `?keepgeo`); re-baseline `traffic_lint`.
5. Merge, then move `tools/osm_signals.py` into `tools/` (handoff §2.1).
