# Plan — Tatra T3 Prague (2026-10-22)

Priorities and next steps after the DTM, street-bot and street-model work. HANDOFF.md keeps the
history and findings; this file says what to do next and how. Update it when a step lands.

## 1. Where we are

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

## 3. Priorities

**P1 — foundation and what the driver sees every minute**

1. **Lint harness + baselines** (§2.1–2.3), including the headless real-traffic run with the slide
   and overlap checks. Everything below is measured with it.
2. **Lanes from the surveyed carriageway (lane graph).**
   - Build directed lanes per tile from DTM carriageway polygons (offsets from the kerb lines, lane
     count from width) joined with OSM topology (direction, oneway, turn connections).
   - Mark lanes that share the tram tracks.
   - This replaces OSM centre line + fitted offsets + `lanes beside tram`, and fixes cars on sidewalks
     at junction corners and sliding from lateral jumps.
3. **Cars at tram stops and in queues.**
   - **Island stops:** where the lane is blocked or narrowed by a stop island, cars merge onto the
     tracks (shared lane), as in Prague.
   - **Vienna-type stops:** cars stop behind a tram with open doors.
   - **One following model:** every vehicle (cars, AI trams, our tram) keeps its gap to whatever is
     ahead in its lane, including on shared track, and nobody overlaps.
   - Lint: overlaps per minute = 0.
4. **Junction controllers with real cycles.**
   - One controller per junction (OSM signal cluster + lane graph). Phases in a fixed cycle (60–90 s)
     with tram priority (call at the výzva contact).
   - Compatible movements share a phase, so trams straight in both directions get GO together.
   - Cars, AI trams and our tram all obey the same controller.
   - Lint: conflicting GOs = 0.
5. **Signal and sign mounting rule.**
   - The head stands at the platform head: past its end, on the island nose, or hung from a span.
     Never along the platform.
   - Lint "signal in platform" = 0 on all lines (today 5 on line 9).

**P2 — scenery correctness**

6. **Trees vs buildings.**
   - Drop register trees whose trunk is inside an LOD2 footprint.
   - Scale each crown to clear the nearest facade (as is done for the tracks).
   - Lint "crown in building" ≈ 0.
7. **Poles at curve centres.**
   - Where the track turns more than 120° (turning loops, terminus loops) and the centre is free
     (no building, track or carriageway), place a centre pole with radial pull-offs, as on real
     loops. Otherwise fall back to the outside poles.
   - Lint "wire without a support within 40 m" on loops.
8. **Stop types from the survey, validated against truth.**
   - Classify each platform side from the lateral class profile: island strip / raised lane to the
     facade (Vienna, raised) / carriageway to the sidewalk (Vienna, at grade).
   - Score it against truth: Vienna = Čechův most towards Kobylisy, Krymská both directions, Újezd
     from Národní třída; island = Štěpánská, Jana Masaryka.
   - Needs DTM for Praha 1, 5, 7 (Újezd, Čechův most) — import those districts.
9. **Street model rollout.**
   - The rest of line 22 (Praha 10), then lines 9/17/23 once their districts are imported.
   - Dropped kerbs at crossings (OSM crossing nodes).
   - DTM retaining walls where level-0 areas meet with a step (the Zahradní Město ramp).
   - Greenery as terrain colour away from streets.

**P3 — bigger features and scale**

10. **Bridges as models.**
    - Keep Mosty 3D for the deck height and outline.
    - Build the look from a parametric kit chosen by OSM `bridge:structure`/material plus pier
      positions (Mosty supports, else OSM `bridge:support`):
      - stone arches with cornices for Most Legií and Palackého most;
      - steel arch for Čechův most;
      - concrete viaduct with pier rows for the Modřany estakáda.
    - First check whether the Mosty I3S nodes carry piers/arches at finer LODs (we read only one level).
11. **Both directions, line variants, stops on both sides** (HANDOFF §12.3) and the terminus loop
    at Zahradní Město (§12.4).
12. **Performance and scale:** height/class raster per tile instead of the triangle index; offline
    meshes; tiles on demand; then the whole network with AI trams on real lines (HANDOFF §10).
13. Still waiting on the user: the two-car set screenshot (HANDOFF §12.1).
14. ~~**Two-car set at the start**~~ — **done 2026-10-22**: the route ended at the terminus stop,
    so the second car's position was clamped onto the first (Sídliště Řepy s = 0, Bílá Hora 3.4 m;
    very likely also the "dual-car set broken" report, HANDOFF §12.1). Every route now continues
    60 m past both ends along the OSM tracks (`extendAlongTracks` in route.js, negative s before the
    start). Lint `consist` places a two-car set at every stop: 0 failures on all lines.

## 4. Next steps (in order)

1. ~~`data/truth.json`, lint runner, baselines~~ — **done 2026-10-22**: `tools/lint.js` (consist at
   every stop, signals in platforms, tree trunks/crowns in drawn buildings, bridges without a deck,
   street bot on DTM lines), reports saved by `tools/serve.py`, `tools/lint_report.py` compares with
   `reports/baseline/`. Baseline (2026-10-22):

   | check | 9 | 17 | 22 | 23 |
   |---|---|---|---|---|
   | consist broken at a stop | 0/60 | 0/37 | 0/39 | 0/18 |
   | signal head along a platform | 5/55 | 7/44 | 1/45 | 0/12 |
   | tree trunk under a roof | 612 | 215 | 390 | 73 |
   | tree crown into a building | 219 | 176 | 292 | 41 |
   | bridge span without a deck | 0/2 | 0/8 | 0/1 | 0/1 |
   | street bot places (DTM only) | – | – | 3510 | – |
2. Headless real-traffic run + slide/overlap lints.
3. Signal mounting rule (small, closes a P1 item, proves the lint loop).
4. Trees vs LOD2 footprints (small).
5. Lane graph from the carriageway (largest P1 item); then stops/queues; then junction controllers.
6. Import DTM for Praha 1, 5, 7 and 12; validate the stop classifier; extend the street model.
7. Curve-centre poles; bridge kit.

## 5. Ground truth from the user (to go into data/truth.json)

| Fact | Source |
|---|---|
| Vienna-type stops: Čechův most towards Kobylisy; Krymská both directions; Újezd from Národní třída. They are few in the city | user 2026-10-22 |
| Štěpánská and Jana Masaryka have normal islands (ostrůvek) | user 2026-10-22 |
| Nádraží Zahradní Město: tram and bus stop in a lowered underpass under the railway platforms, block retaining walls along the Průběžná ramp | user photos 2026-10-22 |
| Trams straight through a junction from both directions get GO together | user 2026-10-22 |
| Signals not in the middle of stops | user 2026-10-22 |
