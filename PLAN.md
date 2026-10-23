# Plan — Tatra T3 Prague (updated 2026-10-22, night)

Priorities and next steps after the DTM, street-bot and street-model work. HANDOFF.md keeps the
history and findings; this file says what to do next and how. Update it when a step lands.

## 1. Where we are

**Status 2026-10-22, evening:** tier A done, tier B done except the rest of B9 (below); all four
lines drive to the end in the headless traffic run; all static lints are 0 on all lines; deploy zip
rebuilt (`dist/tatra-t3-prague.zip`, 12 MB). Details: HANDOFF.md §16, §4 below.

**Status 2026-10-22, night:** line 17 rebuilt on the surveyed streets (DTM) end to end, with two
levels at bridges and underpasses (traffic and drawing), the surveyed decks in the track profile,
step walls along the embankment; new lints `bridgeLevels` and `trackLevels` (0 on all lines).
Details and numbers: HANDOFF.md §17.

**New from the user (2026-10-22, night), to schedule:**
- **U1 Rebuild every line on the detailed DTM** like line 17 (9 and 23 have no survey yet, 22 only
  Praha 2/10): download the districts (links on the Geoportál "ke stažení" pages, uuids change
  monthly), `dtm.py`, `streets.py` for the whole line, lints. Watch the JS heap (line 17: 1.1 GB).
- **U2 Line number plates on the trams**: front blue plates without the white border; the top one
  the size of the model's built-in plate; the one hanging on the mirror assembly smaller and
  rectangular; the rear one inverted (blue on white) on the bottom edge of the rear glass (mounted
  inside); in front a similar blue-on-white card behind the glass with the terminus. User can send
  photos.
- **U3 Cars turning left in front of the tram** (a major accident cause, at signals and at unsignalled
  crossings): car indicators; the driver and the autopilot watch for a car about to turn left across
  the track, ring the bell, which makes the car yield and stop before the track in time; cars
  standing well ahead are safe. Needs blinkers on the car models and a "turning across" state in the
  lane graph (the connector already knows it), plus a lint (left-turners crossing in front of us).
- **U4 Shared city world loaded in chunks** around the tram with a buffer ahead, instead of one
  prebuilt line that shows other mapped lines as unknown land. See §7 (Codex's proposal and my take).

**Next, in order:**
1. Traffic counts: average 3 seeds per line (lint option; the runs differ with timing after the
   street bot), then the largest causes (walker slides, walkers inside vehicles, junction slides).
2. Oncoming trams through red (line 9: 36): find why they do not commit to stopping.
3. Tier C: C11 line ends and depots (loops in the path, layovers, depots), C12 line 37 (dedicated
   Ohrada – Palmovka corridor and bridge), C13 stops (curved platform kerbs, stop-type classifier
   validated against truth, then Vienna-type stops for B9).
4. C15 sounds as soon as the user's samples are there.

**Done and verified (autopilot clean on lines 9, 17, 22, 23):**
- Game: T3 physics and controller, stops/passengers/timetable (PID GTFS), Prague tram signals with
  call indicator, contacts and switches (manual skill kept on purpose), heating and climate, line
  change during a run (9 → 10), two-car sets, mirror and look left/right, cs/en UI, autopilot.
- World: OSM tracks and roads, lidar terrain, LOD2 buildings with classes, retaining walls, city tree
  register, catenary with kerb poles / wall rosettes / bracket arms, zebras, Mosty 3D bridge decks.
- Surveyed streets (DTM, line 22 in Praha 2 + 10): importer with level/border/underground fixes;
  one drawn-surface height for cars and walkers; the Zahradní Město underpass.
- Street bot (`?bot`): drives every car lane and walks every footway, ranks the bad places.
- Street model pilot (Karlovo nám. – Jana Masaryka): smooth carriageway + raised surface, fixed
  kerbs, offline mesh; triangles halved, car steps and tilts down by more than half.

**Checked for this plan (2026-10-22):**
- **Bridges**: all 11 bridge spans on our lines (Most Legií on 9/22/23, Palackého most on 9,
  Čechův most, Holešovice and the six Modřany spans on 17) have Mosty 3D geometry, and the track
  height uses it (`profile.realDecks` covers every span). They render as a flat grey slab on thin
  posts: Most Legií shows no stone arches, piers or parapets.
- **Signals in platforms**: line 9 has 5 of 55 signal heads within a platform's length, all in its
  last 3–10 m before the crossing (Kavalírka ×2, Švandovo divadlo, U Zvonu, Poštovka).
- **Trees**: `buildTrees` has no building test. Register trees with the trunk inside an OSM footprint:
  line 9: 763, 17: 205, 22: 518, 23: 57. Part of these are courtyard trees, because OSM blocks have no
  holes, so check against LOD2. Crowns are up to ~4 m wide and reach into facades.
- **Vienna-type stops**: the streets.py test was wrong. It flagged Štěpánská and Jana Masaryka, which
  have normal islands (user). Survey profile beside the track: an island = a ~2.4 m raised strip with
  carriageway behind it; Krymská (truly Vienna-type) = raised surface continuous from the track to
  the facade (the lane is raised to platform level); Štěpánská shows carriageway right beside the
  track (island on the other side or missing in the survey).

## 7. Shared city world (U4): Codex's proposal (2026-10-22) and my take

Codex (a second opinion the user asked for, `CODEX_HANDOFF.md`, not in the repo) proposes: one
city-wide track graph with stable ids, route-independent world geometry in a common city frame,
streamed ~500 m tiles (surfaces, terrain, scenery with LOD) with prefetch along the expected route,
services (line variants, timetables) as references into the graph, explicit surface ids and levels
for roads, decks and underpass floors, persistent simulation identity across tiles; migration in
steps (common coordinates and graph → one shared test district → two services see identical
geometry → tiles all loaded → streaming → coverage).

**Agree**, with these notes from where the code is now:
- The step that matters first is **route-independent geometry**. Today the world is shaped around
  our route (`flushDtm` lays streets to *our* profile, `carveCorridor` cuts a bench along *our* track,
  the profile itself comes from our route). A shared world needs a profile per **track** (every track
  edge of the graph gets its height once, from the survey + structures), and the street flush
  against all tracks. That is also what fixes "other lines' tracks" heights for good.
- **Explicit levels** are half done (this session): every road and footway carries its level (OSM
  bridge → deck), one height function per level used by drawing and traffic, obstacle checks ignore
  other levels. Next: OSM `layer` and road tunnels (today dropped in `build_line.py`), and DTM level
  −1 areas (underpass floors, Výtoň) as a surface of their own.
- **Coordinates**: one city origin (S-JTSK or a fixed local origin), tiles store vertices relative to
  the tile origin. Line files today each have their own origin; the converter is mechanical.
- **Tiles**: the street model is already chunked along the route (1.5 km, fits reach 40 m beyond);
  move that to square tiles with overlapping input margins. The triangle index, lane graph and
  walker paths must be incremental (register/unregister per tile).
- Start with the **Čechův most – Národní – Výtoň district** (several lines share it, plus the embankment),
  which has bridges, an underpass and the embankment levels: the hardest cases first.
- Cost: a few sessions of refactor before anything looks different; worth it before more lines.

## 2. How we build and test — approach changes

The last sessions fixed many spots one at a time. To scale to the whole network:

1. **Every issue becomes a measurement first.** Before fixing, add a lint that counts the problem on
   every line (e.g. "signal head inside a platform", "tree crown inside a building", "car sliding
   sideways"). Fix the rule, not the spot, and watch the count drop. The street bot is the model.
2. **One lint report per line, with a baseline.** `tools/lint` (browser, headless via the page) writes
   `reports/lineN.json` with counts per check and the worst places. A committed baseline makes a rise
   a regression. Lints to start with:
   - street bot: kerb, sidewalk, jump, tilt, gap, bumpy, slide;
   - placement: signals/signs in platforms or carriageway, poles in roads, buildings or platforms;
   - trees in buildings; terrain above streets or track bed;
   - bridges without a deck or model; stop zones without a platform;
   - AI tram and car collisions or overlaps per minute.
3. **Test the real code, not a re-implementation.** The bot re-samples paths the way traffic
   should behave. Next, step the actual `Traffic.update` headless (fixed dt, fixed seed) for
   simulated minutes along the route, recording every car and walker pose. That catches:
   - sliding sideways (motion vs heading), lane jumps and teleports;
   - overlaps between vehicles, deadlocks at junctions, vanishing.
   Same harness as `tools/autopilot.js`.
4. **Ground truth from the user goes in data, not in code.** `data/truth.json` collects facts like:
   - the Vienna-type stops;
   - "Štěpánská has an island";
   - Zahradní Město = tram under a railway station.

   Every detector is scored against it (precision/recall) before the game relies on it. A new fact
   from the user = one line in that file + a passing test.
5. **One spatial model that every placement rule asks.** Poles, signals, signs, trees, cars and
   walkers all ask "what is here": carriageway, sidewalk, platform, track bed, building, bridge. Today
   each rule has its own guess (OSM widths, OSM footprints, DTM classes). Build per tile a semantic
   layer stack from DTM + LOD2 + OSM tracks: a class raster at 0.5–1 m plus height, and a 3D
   free-space query. This replaces the triangle height index (220 MB) and the scattered heuristics.
6. **Bake offline, render and simulate in the browser.** Move derivations into the Python pipeline as
   a per-tile world model, emitting typed layers the game only loads:
   - street meshes, lanes, pole and signal mounts, tree trimming, stop types.
   
   Python checks run in seconds, against the 90 s reload-and-bot cycle in the browser. That is also
   the path to the whole network and on-demand tiles (HANDOFF §10).
7. **Generic rules over special cases.** E.g.:
   - poles at curve centres from curve geometry, not per terminus;
   - junction phases from the lane graph, not per junction;
   - stop type from the survey profile, not a list.
   
   Lists exist only as test truth.

## 3. Priorities (reordered 2026-10-22, evening)

**Done:** lint runner + baselines, headless traffic run, two-car set at the terminus (routes
continue 60 m past both ends), coasting cars keep their lane, fitted lanes drift at most 5 %.
Details and baseline tables in §4.

Order: first the small fixes that are visibly wrong and each measurable by a lint or a run
(tier A), then the traffic core (tier B), then the network and new content (tier C), then later
ideas (tier D). Every item names its measurement.

**Tier A — done 2026-10-22** (each measured; numbers are line 9 / 17 / 22 / 23 where not noted)

1. ~~No invented walls on surveyed streets~~ — the corridor carve gets the DTM and adds no wall
   where the survey describes the ground at the wall's foot (line 22: 1 272 m of walls on streets
   -> 0; synthetic walls 2 700 m -> 1 419 m, all outside the survey). Lint `inventedWalls`.
2. ~~Vegetation by category~~ — `geoportal.py --trees-only` writes the register kind (tree, conifer,
   bush/hedge, planter, tree-row sample; climbers dropped). Bushes are low shrubs, planters pots;
   trees inside a building are dropped, crowns shrink until they clear the facades (also woodland
   fill), row samples on a carriageway are dropped. Trunks under a roof 612/215/390/73 -> 0, crowns
   into a building 219/176/292/41 -> 0. `roofIndex` shared by the game and the lint.
3. ~~Signals and signs clear of the tram~~ — a signal along a platform moves to the platform head
   (past the tram's stop point) or hangs from a span or bracket arm when the crossing follows too
   closely; hung signals and signs sit right of the tram's envelope (`tramClearance`: body + curve
   overhang 19.5/R + margin). Signals along platforms 5/7/1/0 -> 0; new lint `tramEnvelope`
   (signals and signs inside the swept space): line 9 115/239 -> 0.
4. ~~Curve speeds, OpenRailwayMap speeds, cant~~ — `tools/osm_speeds.py` maps the OSM tram ways'
   `maxspeed` (what OpenRailwayMap shows; on 29–97 % of the route) and a dedicated-track flag onto
   each route every 5 m. Limit = min(√(a·R) with a = 0.8 m/s² (+0.65 with cant), posted speed,
   cap 50 street / 60 dedicated; 65–70 km/h OSM pilots capped for now). Cant up to 100 mm on
   dedicated curves: outer rail raised, trams and the cab lean into the curve (line 17: 5.6 km
   canted, 6.3 km at 60 km/h). User GPS recordings (curves, crossings) to come — then calibrate.
5. ~~Driving feel~~ — autopilot heating with hysteresis and ≥ 20 s between knob changes (traffic
   run check `heatingKnobs`: line 23 34 088 -> 9 changes in 31 min); cab pitch follows a smoothed
   acceleration (no jump at a dead stop); a parked car drives off forwards and steers out (all 6
   on line 23 with obstacles "many", no collision).
6. ~~Cab view and diagnostics~~ — the mirror sits inside the window frame (the right pillar hid
   42 of 150 px) and its camera on an arm 0.3 m outside the body (it was 0.7 m out, by the red
   stop posts), showing the tram's side; menu option performance overlay (FPS, average/worst frame
   time, draw calls, triangles, JS heap).
7. ~~Automatic switches option~~ — every facing switch becomes an onboard-computer (radio) switch
   set to the route; the default stays manual contacts.

**Tier B — traffic core — done 2026-10-22 except the rest of B9** (counts: HANDOFF.md §16)

8. ~~**Lane graph from the surveyed carriageway**~~ — **done 2026-10-22** (`Traffic._buildLanes`):
   one smooth lane per road and direction (two on one-way roads from 7 m) at the kerb-fitted lane
   position, trimmed back from both junctions; connector curves (cubic Hermite with the lanes'
   tangents) through junctions; cars follow their path's own tangent (no sideways motion by
   construction), slow for curves and turns (2.5 m/s² sideways, braking 3 m/s² ahead, across the
   junction), keep their distance across the junction, and wait at a junction while a car is on, or
   nearer to, a connector crossing theirs (connectors closer than 2.4 m or merging = conflict). The
   separate "cars beside the tram" are gone: the tram street is an ordinary part of the network with
   spawns near the tram. The 5 % drift limit is gone. The street bot drives every lane and every
   junction connector.

   | (line 9 / 17 / 22 / 23) | before | lane graph |
   |---|---|---|
   | slide | 6 839 / 5 243 / 8 671 / 3 513 | 368 / 156 / 311 / 200 |
   | jump | 641 / 294 / 788 / 270 | 88 / 90 / 73 / 11 |
   | overlap episodes | 734 / 329 / 539 / 271 | 551 / 293 / 492 / 133 |
   | walker inside a vehicle | 1 708 / 723 / 657 / 239 | 2 180 / 1 151 / 737 / 417 |
   | street bot: wheels on sidewalk (22) | 4 645 | 2 008 (incl. junction turns) |

   Left for B9: cars on lanes that lie on the tracks (narrow tram streets — shared lanes in reality)
   overlap trams (line 22: car/our tram 110, car/oncoming 102): they must follow the tram ahead and
   not enter the track zone in front of one; walkers inside vehicles rose with more cars near the
   footways (walkers must yield at crossings, cars stop for walkers on a crossing).
9. **Cars at stops and in queues** — **partly done 2026-10-22:**
   - every car scans its own path 40 m ahead (across the junction too) for trams (ours and AI, as
     boxes with their velocity), walkers and other cars; it follows or stops behind the first one.
     Two cars that see each other on crossing paths: the lower id goes first. At a junction a car
     also waits from braking distance on, and for cars standing in the mouth of a lane its turn
     passes close to;
   - sidewalks run 1.5 m beyond the (surveyed) kerb as their own paths; walkers never turn back
     while standing in a car lane (a walker turning back and forth there blocked a car for minutes);
     walker hits are counted per episode now, like overlaps;
   - line 22: overlaps 492 -> 133, car jumps 73 -> 0; line 23: overlaps 133 -> 46.
   Done later the same day: trams (AI both ways and the autopilot) stop behind a car going their way
   on their track (`game.carsOnTrack`); the "give way to the tram" wait applies only to cars that
   cross the track (a car driving along it waited for the tram behind it — deadlock); cars never
   enter a junction whose exit lane is full ("don't block the box") and ignore a car in the
   junction that waits for them; the lane-mouth rule ignores cars approaching the same junction
   (two of them waited for each other); unique car ids; walkers always turn at the end of their
   path and are clamped into it (one spawned past the end and stood in a lane for good, with eight
   cars and our tram queued behind); oncoming trams keep their distance to each other.
   Each was found by a traffic run that did not finish, followed back along the chain of who waits
   for whom. Also: an obstacle behind a car never stops it (a car beside the front of our tram
   waited for it); a car whose own path is blocked does not hold its junction priority; tram
   priority jumps to the start of the tram phases, not straight to ours (our turning phase starved
   the opposite direction, which then blocked the Letenská single track for good).
   Still open in B9: lanes of different roads that touch
   (line 22: 45); Vienna-type stops (cars wait beside a tram with open doors) need the stop
   classifier first (C13). Original items:
   - Cars merge onto the tracks past islands and wait behind a tram at Vienna-type stops.
   - One following model for every vehicle; walkers yield at crossings.
   - Lints: overlaps per minute, walkers inside vehicles.
9b. ~~**Grade separation: no crossings where the track is on a bridge.**~~ **done 2026-10-22:**
    signals whose junction lies well inside a bridge span of the route (more than 8 m from its ends:
    a junction at a bridge end is real) are dropped, no jaywalkers there, and cars under the bridge do
    not wait for a tram passing above (`profile.overBridge`). Line 17: the three junctions under the
    Modřany estakáda (s 4 082, 5 818, 6 523) and four crossings; lint `gradeSeparated`. Original text: Where our track runs on a deck
    (Mosty 3D / OSM bridge, e.g. the Modřany estakáda), roads crossing beneath must not create
    at-grade crossings, signals, cross traffic or give-way; they pass under at their own height
    (and the same where a road is in a tunnel under the track). Generic rule from the deck spans
    (`profile.realDecks`) and OSM `bridge`/`layer`/`tunnel` tags. Lint: crossings on a deck = 0.
9c. ~~**Lint noise for traffic checks.**~~ **done:** `lint_report.py` flags a traffic count only beyond
    15 % + 5 of the baseline. Original text: The traffic counts move ±10–20 % when trajectories change
    (line 9 walkers inside vehicles 921 -> 1 708 after tier A, which did not touch walkers): compare
    rates with a noise band, or average a few seeds, so the comparer only flags real regressions.
10. ~~**Junction controllers with real cycles.**~~ **done 2026-10-22** (`Game._runController`): one
    fixed cycle per signal (60-90 s): trams straight in both directions (20-30 s), a 10 s turning
    phase when our route turns there, then the cross street; tram priority cuts the cross street's
    green after its minimum 8 s, the dilemma zone holds our GO up to 10 s. Oncoming AI trams stop at
    the junction's line on the opposite track unless the straight phase runs (they commit with
    braking distance + 2 s reaction, stop 3 m before the line, never spawn in front of a red line).
    Traffic run check `redRuns`: an oncoming tram past the line on red although it was far enough to
    stop while it was red (one that could no longer stop when it changed passes on amber).
    Original text:
    - Compatible movements share a phase, so trams going straight from both directions get GO together.
    - Lint: conflicting GOs = 0.

**Tier C — network and content**

11. **Line ends and depots as part of the network.** Today a route ends 60 m past its last stop
    (§5). Next:
    - the terminus loop is part of the path (drive on past the final stop and start the return run);
    - AI trams lay over at the terminus and run their next service;
    - depots (OSM vozovna tracks near our lines, e.g. Vozovna Žižkov on line 37; others to be
      checked) where runs can start and end.

    This joins the old item "both directions, line variants, stops on both sides".
12. **Line 37** (temporary; GTFS: Spojovací – Vozovna Žižkov – Ohrada – Krejcárek – Palmovka – …
    – Lehovec, 366 trips).
    - The Ohrada – Krejcárek – Palmovka section is a dedicated corridor with its own bridge over the
      park and railway.
    - It's the test case for cant (A4), bridges (C16) and a depot.
    - Check whether Mosty 3D and the DTM already contain the new bridge.
13. **Stops.**
    - The platform kerb follows a curved track (offset curve of the track, no clipping into the rails).
    - Stop types from the survey, validated against truth.
    - DTM for Praha 1, 5, 7, 12; street model rollout, dropped kerbs, DTM walls (Zahradní Město ramp),
      greenery as terrain colour.
14. **People.**
    - Late runners shown running to the doors (today only a counter and a message).
    - The driver walking out to throw a switch with the crowbar (today key X, a timed action, no
      figure).
15. **Sounds from the user's samples** (waiting for the samples).
    - Traction motor whine of the old commutator type, following current and speed (now it sounds
      like a car).
    - Curve squeal as metallic scraping by radius and speed (now a mosquito-like whine).
16. Poles at curve centres (loops); bridges as models by type (stone arches, steel arch, viaduct).
16b. **Buildings.** Today five classes guessed from shape (old town house, panel block, church,
    industrial, glass) with a texture each. Next: real building types from RÚIAN (use, floors),
    facades with whole window bays per floor, street-facing facades in more detail than courtyard
    sides (facade within ~3 m of a DTM sidewalk), roof shapes and colours.
16c. **Street-level imagery** (investigate): Mapillary (CC BY-SA, open API) and Panoramax are free
    to use; Mapy.cz panoramas and Google Street View are not. Mapillary also publishes detected
    objects with positions (traffic signs, poles, traffic lights): test truth for our signal, sign
    and pole placement, possibly facade colours.

**Tier D — later**

17. Road markings and signs on the ground; bike lanes and cyclists as a traffic mode.
18. Performance and scale: height/class raster per tile, offline meshes, tiles on demand, the whole
    network with AI trams on real lines.

## 4. Done (2026-10-22)

1. **Lint runner and baselines**: `tools/lint.js` checks:
   - consist at every stop;
   - signals in platforms;
   - tree trunks/crowns in drawn buildings;
   - bridges without a deck;
   - street bot on DTM lines.

   Reports are saved by `tools/serve.py`, and `tools/lint_report.py` compares them with
   `reports/baseline/`.

   | check | 9 | 17 | 22 | 23 |
   |---|---|---|---|---|
   | consist broken at a stop | 0/60 | 0/37 | 0/39 | 0/18 |
   | signal head along a platform | 5/55 | 7/44 | 1/45 | 0/12 |
   | tree trunk under a roof | 612 | 215 | 390 | 73 |
   | tree crown into a building | 219 | 176 | 292 | 41 |
   | bridge span without a deck | 0/2 | 0/8 | 0/1 | 0/1 |
   | street bot places (DTM only) | – | – | 3685 | – |
2. **Headless traffic run**: `tools/traffic_lint.js` (`lint({ traffic: true })`) drives the whole
   line with the real game and traffic.
   - It runs at a fixed step, seeded, on the first trip, autumn, dry. It's deterministic per page
     load; the frame loop only draws while `window.headless`.
   - Tram electrics now run on simulation time; the wall clock made contacts, and so runs, differ.

   Fixed on the way:
   - cars handing over to "coast" at the data edge hopped sideways — 626 → 0 on line 23;
   - fitted DTM lanes changed sideways too fast — lane drift limited to 5 % (line 22 same-road
     slides 16 245 → 1 330). Trade-off: street-bot sidewalk samples 2 338 → 4 645 (at 7.5 %:
     7 720 / 3 736). Lanes must become smooth curves inside the carriageway (B8) to win both.

   | check | 9 | 17 | 22 | 23 |
   |---|---|---|---|---|
   | slide (samples) | 6 619 | 4 554 | 8 611 | 3 756 |
   | jump | 642 | 316 | 863 | 250 |
   | overlap (episodes / minutes) | 652 / 93 | 296 / 52 | 580 / 58 | 331 / 31 |
   | walker inside a vehicle | 921 | 808 | 718 | 333 |

   Causes (line 22):
   - slides: lane beside the tram 3 714, next road 3 510 (no turning curves), same road 1 330;
   - jumps: almost all "next road";
   - overlaps: car/car at junctions, car/our tram, a few tram/tram (line 9 near the far terminus,
     s ≈ 27 090);
   - walkers inside vehicles: mostly cars (walkers do not yield; walk paths use OSM widths, cars the
     fitted lanes).
3. **Two-car set at the terminus**: routes continue 60 m past both ends along the OSM tracks
   (`extendAlongTracks`). The second car was clamped into the first at Sídliště Řepy (s = 0) and
   Bílá Hora (3.4 m), very likely the earlier "dual-car set broken" report too.

## 5. Findings for the 2026-10-22 evening questions

**Curve speeds.** Not measured on real trams. They come from commonly used design values for
unbalanced lateral acceleration (0.65 m/s² comfortable, ~1.0 m/s² upper bound) and cant (100 mm on
1 435 mm gauge ≈ +0.65 m/s²), with v = √(a·R):

| R (m) | now (km/h) | a = 0.65 | a = 1.0 | 100 mm cant + 0.65 |
|---|---|---|---|---|
| 20 | 10 | 13 | 16 | 18 |
| 30 | 15 | 16 | 20 | 23 |
| 45 | 20 | 19 | 24 | 28 |
| 60 | 20 | 22 | 28 | 32 |
| 80 | 30 | 26 | 32 | 37 |
| 100 | 30 | 29 | 36 | 41 |
| 140 | 40 | 34 | 43 | 49 |
| 200 | 40 | 41 | 51 | 58 |
| 250 | 50 | 46 | 57 | 65 |
| 400 | 50 | 58 | 72 | 82 |

The step table sits around 0.65 m/s² on average but jumps at its band edges (30 km/h at R 80 =
0.87 m/s²; 10 km/h at R 20 is below even the comfortable value).

Proposal:
- continuous √(a·R) with a ≈ 0.8 in streets;
- cant on dedicated corridors;
- capped by the line maximum (50 km/h in streets, 60 on dedicated track — to confirm with the user).

Ground truth would be phone accelerometer recordings on real rides (data/truth.json).

**Walls inside sidewalks and road** come from the synthetic retaining walls of the corridor carve
(built where the lidar terrain rises > 1.5 m beside the track bench), not from the surveyed walls.
Line 22 has 900 synthetic segments, 2 700 m, of which 1 272 m stand on a DTM street surface. Of the
53 surveyed Geoportál wall segments, none stands with street at the same level on both sides.
Fix A1.

**Trees.** Geoportál "vegetační prvky" (body) has no size (no height or crown width), only
categories (`kod_vp`, from the layer's coded values):
- Strom 71 (25 548 points on our lines);
- Keř 51 (3 206);
- Zeleň v nádobách 21 (124);
- Popínavá dřevina 101 (33).

`kod_drevin`: 1 conifer, 2 deciduous, 3 fruit, 4 mixed; `kod_tvar`: 1 shaped, 2 free.

All are drawn as full trees today; the bushes, planters and climbers explain part of the trees in
streets and on facades. Tree rows (Stromořadí, lines) are resampled every 9 m, which can put points
in a road or a building. Fix A2.

**Line ends.** The GTFS path ends at the terminus stop; since today the route runs 60 m further
along the OSM tracks at both ends (enough for a two-car set). The loop itself is not driven; AI
trams fade out before the end and have no timetable. Fix C11.

**Already there, without visuals:**
- late runners: each stop may get 1–3; they add to the waiting count after a delay, with a message;
- the crowbar: key X, a 9 s action that throws the switch.

## 6. Ground truth from the user (data/truth.json)

| Fact | Source |
|---|---|
| Vienna-type stops: Čechův most towards Kobylisy; Krymská both directions; Újezd from Národní třída. They are few in the city | user 2026-10-22 |
| Štěpánská and Jana Masaryka have normal islands (ostrůvek) | user 2026-10-22 |
| Nádraží Zahradní Město: tram and bus stop in a lowered underpass under the railway platforms, block retaining walls along the Průběžná ramp | user photos 2026-10-22 |
| Trams straight through a junction from both directions get GO together | user 2026-10-22 |
| Signals not in the middle of stops | user 2026-10-22 |
