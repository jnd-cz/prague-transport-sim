# Changes made on the deployment copy (remote session, 2026-10-23)

**2026-10-27 track research:** See [TRACK-DATA-DECISION-2026-10-27.md](TRACK-DATA-DECISION-2026-10-27.md) for the agreed DTM/older-map/OSM source strategy, Kobylisy spacing evidence, elevation findings, and implementation handoff. This is a documentation-only update; game code and data were not changed.


(Build-side to-do list and test procedure for the original computer: `BUILD-TOOLS-HANDOFF.md`.
Architecture proposal and multi-computer / multi-agent workflow: `ARCHITECTURE-PROPOSAL.md`.
Unattended bench runs in any browser: `.claude/bench/batch.html` (see §18).)

This copy has no `tools/`, no `raw/` and no git history; only the deployed game (`index.html`,
`src/`, `data/`, `assets/`). Everything below was made here and is to be merged into the original
project. Test lines: 17 (fine terrain + DTM survey) and 22 (DTM survey).

## 1. Detailed loading screen

Request: on a slow connection the old "Loading Prague…" text gave no sign of progress.

- **New `src/loading.js`** (`Loader`): downloads counted byte by byte (`fetch` stream reader), bar +
  percent, MB loaded / total and speed, one row per file (size, %, ✓, "not for this line" for a 404 of
  an optional file, "failed"), then the build steps with their labels. Downloads fill 80 % of the bar,
  the build steps 20 % (weights: terrain 2, profile 3, world 4, tram 1). `begin(step)` yields two
  frames so the label is painted before the blocking step. A response with `Content-Encoding` has no
  usable total (the stream counts decompressed bytes): such a file counts as the average known size.
- **`src/main.js`**:
  - `Loader` imported; `applyStatic()` called at the start too (loading text in the user's language).
  - All files of the line are requested at once right after `lines.json` (`line.json`, `geo.json`,
    `bld.bin`, `dtm.json`, `fine.json` + `fine.bin` unless `?nofine`, and the three T3 model files);
    the code below reads them with `load.get(url)` (fetch-like: `ok`, `json()`, `arrayBuffer()`) in
    the same order as before. Side effect: loading is faster (parallel instead of one after another).
    `bld.bin` is prefetched as `line<N>.bld.bin`; the name from `geo.json` is still what is read (a
    different name is simply fetched then).
  - Build steps marked: `load.begin('terrain' | 'profile' | 'world' | 'tram')`; `load.finish()`
    replaces the final `$('loading').classList.add('hidden')`.
  - The T3 model is built from the prefetched files (blob URLs passed to `loadDetailedT3`).
- **`src/models.js`** `loadDetailedT3(url, files = {})`: optional map url → blob URL, applied through a
  `THREE.LoadingManager` URL modifier (the glTF's relative `t3.bin` / `t3_color.jpg` resolve to
  `assets/t3/…`, which the map catches). Called without `files` it behaves as before.
- **`index.html`**: `#loading` now holds `.loadBox` (title with `data-i18n="loading"` on an inner
  span, so `applyStatic` no longer overwrites the box), `#loadPct`, `#loadBar`, `#loadStep`
  (initially "Loading the 3D engine…", shown while Three.js comes from the CDN), `#loadBytes`,
  `#loadFiles`; CSS for them (bar in `--amber`, no width transition: it lagged the percent).
- **`src/i18n.js`**: keys `load.download`, `load.terrain`, `load.profile`, `load.world`, `load.tram`,
  `load.missing`, `load.error` in en and cs.
- Verified in the browser pane on lines 22 and 17 with a throttled server (1.5 MB/s per file), at
  desktop and phone width; the menu and a line 22 shift start normally; no console errors besides the
  expected 404s of the files a line does not have.
- Not done: the Three.js download itself has no percentage (it is a module import before our code
  runs). Pre-existing: changing the weather in the menu rebuilds the world synchronously in `start()`,
  so its loading screen is never painted.

- Follow-up: `begin()` and the redraw also fire on a timer (100 ms / 250 ms), because a hidden
  tab draws no frames and the loading stalled at "Building the terrain…" until the tab was shown.

## 2. Performance analysis of line 17 and the load-time fix

Full report: `PERF-ANALYSIS.md` (load, memory, rendering, simulation, ten proposals by value).

- **`src/terrain.js`** (the fix): `Terrain.lowerAt` no longer scans every grid. New
  `Terrain.finesAt(x, y)` (the at most 4 fine blocks around the point, by index) and
  `Terrain.coarse()` (the cached plain-`Grid` view of the coarse grid, which `grids()` now uses too).
  Line 17's lowering under the DTM streets took 62.5 s of an 85 s load (16.9 M calls x 535 grids).
  Result checked identical: hash of every height of the coarse grid and all 534 fine blocks before =
  after.
- **`src/world.js`** `buildWorld`: timing laps (`mark('…')` after each part), stored in
  `window.worldTimes` and logged as "world build (ms)". The former single "lowering" section is split
  into terrain under tracks / under DTM / fine under DTM / fine to tunnel mouths. Note: world.js was
  saved with LF line endings by the edit script (it may have had CRLF before; terrain.js has CRLF):
  check the diff for a whole-file line-ending change before committing.
- **`src/loading.js`**: per-step times; `window.loadTimes` ({ scripts, download, terrain, profile,
  world, tram, total } in ms), logged as "load times (ms)".
- **`src/main.js`**: `window.renderer` and `window.scene` for console checks (with the other debug
  globals in `start()`).

## 3. Preprocessing study for chunked loading

No code change. `PERF-ANALYSIS.md` §6: the finished world encoded compactly is ~41 MB gzip for line 17
against 13.5 MB of sources today; ship preprocessed sources (edited terrain grids, trimmed / classed
buildings, the DTM as binary or as an offline-simplified final mesh that doubles as the height lookup)
for ~9-20 MB and almost no client build time. §8: multi-threading (none today; where workers would
help, why the offline build is the better place for the load work, chunk workers for streaming).

## 4. Traffic: less work per step (PERF-ANALYSIS §5 items 2 and 3, §7)

- **`src/traffic.js`**:
  - `update(dt, camera, draw = true)`; `_updateRoadCars` and `_updateWalkers` take `draw`. With
    `draw = false` cars and walkers move and decide as before but are not posed: no `_poseCar`, no
    walker height / matrix, no `instanceMatrix` upload. `c.z` / `w.z` then keep the last drawn step's
    value (they are only compared with `LEVEL_APART`, levels metres apart). A walker dropped in an
    undrawn step still gets its zero matrix right away. Default `true`: callers that pass nothing
    (normal play, `tools/traffic_lint.js`) get the old behaviour.
  - Walkers: the ground height (`walk.hf` / `ground.surface`) is looked up again only after the walker
    moved 0.3 m (`w.zx`, `w.zy` remember where it was taken).
  - `_poseCar(mesh, x, y, hx, hy, hf)`: returns at once when x, y, hx, hy and hf equal the last pose of
    that mesh (`mesh.userData.pose`): cars standing in a queue. The default height function is now
    applied inside (`hf || ground.surface`) so the cache compares what the caller passed.
- **`src/main.js`** frame loop: in inspect mode `traffic.update(h, camera, i === steps.length - 1)`.
- Measured: traffic 0.65 → 0.40 ms per step in normal play, 0.17 ms in inspect mode at 32x; outputs
  checked (walker heights and matrices, car positions).
- Lint note: `tools/traffic_lint.js` counts may move slightly through the 0.3 m walker height reuse
  (walker `z` feeds the obstacle list); re-baseline if a count changes.

## 5. Street-height lookup in compact arrays (PERF-ANALYSIS §5 item 4)

- **`src/terrain.js`**: new `TriIndex` (below `DtmSurface`) replaces the two `Map`s of `DtmSurface`
  (`grid`, `deckGrid`) and `DtmSurface._index`.
  - Triangles are kept **by reference** (the areas' own `mesh` triangles, numbered in `tris`), so the
    height edits world.js makes afterwards (`flushDtm`, bridge decks, `fitDtmToMouths`: all `p[2]` in
    place) are seen exactly as before. Rank / level in a `Float32Array` (`val`), class as a `Uint8Array`
    index into `classes`.
  - **3 m cells** instead of 10 m, in CSR form: `cells` (key → cell number), `start` (Int32Array),
    `ids` (Int32Array). A lookup tests ~20 triangles instead of ~100.
  - `covered()` keeps its 10 m meaning (a `Set` of 10 m keys): traffic and the street bot ask whether
    the survey is about.
  - `_hitTri` and `deckAt` loop over the cell's numbers; candidates come in the same order as before
    (ascending triangle number), so ties resolve the same way.
- Checked identical: 300 k fixed points around line 17, every answer of `surfaceAt` (with and without
  `ref`), `classAt`, `deckAt` (with and without `ref`/`tol`), `covered` hashed: same hash, same hit
  counts; terrain heights (coarse + 534 fine blocks, which are lowered through these lookups) same hash.
- Measured: `surfaceAt` 6.4 → 2.2 us; heap ~240 MB less (index 65 MB instead of ~250 MB of small
  arrays); line 17 load 28.7 → 20.8 s at normal CPU speed ("fine under DTM" 4.8 → 0.75 s, buildings
  8.2 → 3.3 s); traffic 0.40 → 0.26 ms per step in normal play.

## 6. Loading bar through the city build; weather rebuild with a loading screen

- **`src/world.js`**: `buildWorld` is now **async** with an optional `onPart(name)` callback, awaited after
  each part (the 16 `mark('…')` calls are `await mark('…')`). New export `WORLD_PARTS`: the parts in order
  with their usual milliseconds on line 17 and a label key. Lines without the DTM skip its two parts.
- **`src/loading.js`**:
  - `parts(list)` (async, paints) and `partDone(name)` move the bar through the current step and show
    "Building the city… · <part>"; a paint (a frame or two) only when the label changes or 150 ms
    passed, so the yields cost ~0.2-0.5 s on line 17.
  - The bar is shared by expected **time**: the step weights are now milliseconds, and the downloads'
    share is their expected time at the speed so far against the build steps' total (at least 5 %,
    fixed once they finish); the bar never goes back. Line 17 locally: 5 % at 2.5 s, 50 % at 12.5 s,
    96 % at 23 s.
  - `restart(steps)`: the loading screen again without files (rebuild); the bar is then the steps only.
- **`src/main.js`**: `applyWeather` is async (calls `load.parts(WORLD_PARTS)` and awaits `buildWorld`);
  the start awaits it; step weights from `WORLD_PARTS`. `start()` is **async**: when the weather
  changes, the last shift is paused, `load.restart` + `begin('world')`, the world is rebuilt with the
  bar, `load.finish()`. Before, that loading screen was never painted (synchronous rebuild).
  `audio.start()` stays the first line (needs the click).
- **`src/i18n.js`**: `load.w.tracks / terrain / streets / roads / buildings / wires` (en, cs).
- Checked: all six part labels appear in order; a rain shift after a dry load shows the rebuild
  0-100 % and starts with rain. Seen: after the last part the first frame with a new world takes
  seconds (geometry upload to the GPU, 600+ MB); it was there before, unseen.
- Note: `favicon.ico` 404s in the console come from this copy having no favicon.

## 7. WebAssembly benchmark and the weather rebuild (analysis only)

- `rustup target add wasm32-unknown-unknown` installed on this PC (user's OK).
- **`.claude/bench/tri.rs`** (+ built `tri.wasm`, `tri_simd.wasm`): benchmark kernel, not part of the
  game. Results in `PERF-ANALYSIS.md` §9: nested JS arrays 93.5 ns, flat Float64Array 31.1 ns, WASM
  23.1 ns per triangle test (SIMD no gain).
- `PERF-ANALYSIS.md` §10: why a weather change rebuilds the world (colours baked per vertex) and the
  proposal to make weather a material / shader state.

## 8. Weather as a material state; winter (snow); more realistic autumn

The world is built **once**, in its dry colours; the weather is applied by shader uniforms and instance
colours, instantly (no 17.5 s rebuild, could change during a shift; one set of chunk files for every
weather later).

- **New `src/weather.js`**:
  - `WEATHER_UNIFORMS` (`uWet`, `uSnow`, `uAutumn`, shared by every patched material) and
    `WEATHER_LOOK` (their values for dry / rain / leaves / snow).
  - `weatherize(material, { wet, snow, slush, veg })`: an `onBeforeCompile` patch (Lambert and Standard,
    instancing included) after `color_fragment`: colour × `wet` factor when wet; snow on faces pointing
    up (world normal, smoothstep 0.45-0.8), patchy (two octaves of value noise on world x/z), `snow` =
    how much stays (1 ground and roofs, 0.7 footways, 0.35 carriageways, 0.15 crowns), `slush` = grey
    slush instead of white; `veg` = the terrain: per-vertex `landCls` (0 ground, 1 grass, 2 wood, 3
    water): only bare ground wets, grass / woods take autumn colours (uniforms), water no snow.
  - Wet factors reproduce the old wet colours: `wetFactor(dryHex, wetHex)` = their linear ratio (the old
    code wrote sRGB pairs; the DTM's 0.8 was already linear).
  - `crownColor(i, weather, summer)`: autumn by species (lime 32 % yellow, Norway maple 18 % yellow /
    orange / red, horse chestnut 14 % rusty, plane 10 % yellow-brown, oak / hornbeam 10 % brown, birch /
    cherry 8 % orange, conifers 8 % green), each tree at its own stage between green and turned (hash of
    its index: stable); winter: bare crowns dark grey-brown, conifers green. `crownThinning`: crowns
    0.86-1.0 in autumn, 0.8 in winter.
  - `leafTexture(crushed)`: canvas texture of fallen leaves (alpha cut out), or the dark wet mash.
- **`src/world.js`**:
  - `buildWorld(scene, data, route, ground, onPart)`: **the `weather` parameter is gone** (tools that call
    it must drop it); returns the group with `userData.setWeather(w)` (uniforms, rail roughness 0.4 /
    0.2 wet, trees).
  - All `wet ? … : …` colours removed; materials `weatherize`d instead: OSM roads, footways (now their own
    material, wet factor of paving), road tunnels (no snow), track bed, zebras, track support, rock tunnel
    outside (inside vault and floor: new separate dry material; they used to darken in rain), road
    portals (frame; floor inside dry), portal earth cover, DTM (split by class into street / other /
    green / water materials), terrain coarse and fine (+ `landCls` attribute, Uint8), the far ground,
    buildings (OSM and LOD2: snow on roofs), bridge decks, planters, crowns.
  - `buildTrees` returns `{ setWeather }`; summer greens drawn from the rng in the same order as before
    (dry look unchanged). New `buildLeafLitter`: fallen-leaf patches (2-4.2 m, 6 + 8k per tree within
    1.3 crown radii, 75 % skipped on carriageways, none within 2 m of a track), one InstancedMesh per
    350 m cell (culling), visible only in 'leaves'. Line 17: 117 k patches.
  - `STREET_SNOW`, `FOOT_SNOW`, `GROUND_SNOW` constants; `buildTerrain`, `buildDtm`, `buildTrackSupport`,
    `buildZebras`, `buildRockTunnels`, `buildRoadPortals` lost their weather / wet parameter.
- **`src/main.js`**: `buildCity()` once in the loading step; `applyWeather(w)` sets sky, fog, light, rain
  / snow particles and `world.userData.setWeather(w)`. `WEATHER.snow` (sky #c3c9cf, fog 70-480 m).
  Snowflakes: `makeSnow` / `updateSnow` (4 000 points, ~1 m/s down, drifting). The weather-rebuild path
  in `start()` is gone (start is synchronous again), and `Loader.restart` with it.
- **`src/tram.js`**: `ADHESION.snow = 0.12`.
- **`src/game.js`**: snow: μ 0.08 within ±4 m of each pedestrian crossing (packed snow / ice; ~5 % of
  line 17); autumn leaf patches drawn as overlapping rotated smears of the crushed-leaf texture (every
  1.6-3 m, larger mid-patch, ±0.6 m across) instead of flat brown 1.9 x 4.2 m planes.
- **`index.html`**, **`src/i18n.js`**: weather option "snow" / "sníh", adhesion label.
- Checked in the browser on line 17 (Palackého náměstí, Sídliště Modřany): all four weathers switch
  instantly without shader errors; autumn crowns in mixed yellow / orange / rust / green with leaves
  under them; snow on lawns, roofs, embankment and ballast, slush on carriageways and the track, bare
  dark crowns; leaf mash on the rails. Load time unchanged (22.7 s).
- Not done: snow on the trams and cars, traffic driving slower in snow, icy road junctions, the
  temperature option is independent of the weather (snow at the "live" summer temperature is possible).

## 9. Number plates and cards on the trams (PLAN U2, from the user's photos)

Photos (2026-10-23): T3 8085 rear on line 23, T3 #801-card on line 23 (front three-quarter), T3 7192
on line 9 (front). Detailed model only; the built-in low-poly model just loses the plate's white edge.

- **`src/models.js`**:
  - Textures: `numberTexture(text, w, h, fg, bg, fill)` and from it the roof plate (white digits on
    DPP blue `#1f57a8`, **no white border**), the mirror plate (same, taller than wide), the rear plate
    (**inverted**: blue digits on white), the run number card (white on black); `destinationTexture`
    (blue capitals on white, blue frame, split into two lines nearest the middle when more than one
    word, shrunk to fit).
  - `glassCards(proto)` (in `loadDetailedT3`): the model's windows are painted in its opaque texture,
    so the cards lie 5 mm proud of the glass, placed by raycasting the model from outside. The
    windscreen's middle pane runs x −0.62 … +0.58 between the frame supports (raycast scan; a wiper arm
    stands out at −0.36): destination card 0.46 x 0.19 m **centred** on the pane (x −0.02), run card
    0.15 x 0.1 m **white on black** at x −0.75, on the side pane just past the frame support (left seen
    from the front), both from 1.75 m up (user's corrections after the first versions); the rear plate
    0.34 x 0.3 m at the bottom of the rear window.
  - The rear plate is no longer a mirror of the roof box (`paintedBoxes` returns the two painted boxes
    only).
  - `makeDetailedSet`: the leading car gets the roof plate, the mirror plate (0.22 x 0.28 m on the
    painted box's place) and the two cards; the last car the rear plate (a two-car set: front plates
    on car 1, rear plate on car 2). Cards are Lambert (lit), plates Basic as before.
  - `makeT3({ …, dest, run })`; no `dest` = no destination card (other lines' trams).
  - `setConsistLine(model, line, dest, run)` swaps only what changed.
- **`src/game.js`**: `get destination()`: the stop where the run changes its number (9 → 10), else the
  last stop.
- **`src/main.js`**: `runNumber(trip)`. The scheme (user): **depot digit + two-digit run** (801 = depot 8,
  run 01); a tram keeps its run number for its whole time in service; night and late-evening runs
  (single cars) are numbered from 51. **Prepared for data**: `data.runs[tripIndex] = { depot, run }`
  is used when a line file has it; until then a placeholder (depot 8, day run 01-49 from the trip's
  place). The model shows the last stop until a shift starts, then `game.destination` and the run
  number (and again on a line change).
- **For the original project (needs the tools):** fill `data.runs` in `build_line.py`: which run serves
  each GTFS trip and which depot runs it. The PID GTFS (open data zip) has no `block_id` (HANDOFF);
  check whether its trips carry a run / block reference after all, else the run lists published by
  enthusiasts (pražské tramvaje, forums). Then also: a run that is a night / late-evening one is a
  single car (today only line 23 is single-car, `lineCars` in main.js).
- **`src/traffic.js`**: other lines' trams get a run number from a counter (not `this.rand`, so the seeded
  traffic runs are unchanged) and no destination card.
- Checked in the browser on line 17: roof and mirror "17", "VOZOVNA KOBYLISY" card, "801", rear "17"
  inverted on the second car.

## 10. Red runs of the AI trams (PLAN 1.5 item 4: line 17 s 20829, 11785, 10263)

User's rule: a tram that cannot stop any more passes legitimately and the controller must allow for
it; with the blinking-GO phase red runs should be rare. Measured with `.claude/bench/redruns.js`
(whole line 17 headless, autopilot, seeded; a red run is "avoidable" when the tram was once far
enough to stop with full service braking during that red). Before: **5-8 oncoming red runs per run,
all avoidable**: none was the "picked up speed" case.

Causes found and fixed:
1. **One red-stop slot per oncoming tram** (`t.redStop`): with two red signals close together the
   farther one took the slot every frame, and the nearer one could not take it back once the tram was
   within its braking distance: drove through it (s 9791, 20819, 11050). Now `t.redStops`, a set: every
   signal decided on is kept until it shows GO.
2. **Braking lag**: AI trams followed their braking curve's speed with `a = (vt − v) × 0.8`, ~1.1 m/s
   above it: they over-ran stop points by 3-4 m, onto the stop line at 0.1-0.3 m/s, 10-40 s into the red.
   Now on the curve they brake with what it takes to stop at the point (`v²/2d`, up to 1.3 m/s²):
   `aStop` in `_updateOncoming` and `_updateAhead` (applies to every stop point: platforms, cars,
   trams, signals, gauntlets).
3. **No blinking phase for the opposite direction**: `backState` went straight go → stop at `gS − 3`.
   Now `go` until `gS − 6`, **`warn` (blinking) `gS − 6 … gS − 3`**, then `stop` at the same moment as
   before (the cross street's clearance unchanged).
4. **No dilemma-zone hold for AI trams**: trams decide when the GO starts blinking: stop if comfortable
   (`stopDistance(v, 'warn')` = v²/1.8 + 2v + 1), else go on, and the controller holds the phase for
   them like for ours: `sig.backCommitted` (oncoming), `sig.aheadCommitted` (AI trams ahead), set by
   traffic.js each step. Facing a red a driver stops whenever full service braking allows
   (`stopDistance(v, 'stop')` = v²/2.6 + v + 0.5); a standing tram (v < 0.5) always stays (one leaving
   a platform ending at the stop line crept over).
5. **AI trams ahead** checked only the next signal and stopped for any non-GO even when too close; now
   every signal within 150 m, the same rules (s 10251: the red 68 m beyond a junction passed on a blinking
   GO was seen too late). A tram at a platform whose signal stands at the platform head stays.
6. **Controller hold budgets** (`_runController`): 10 s each for our tram (`ext`), an AI tram ahead
   (`extAhead`) and an oncoming one (`extBack`; window `gS − 6 … gS − 3`); a shared budget used up by
   another tram gave **our** tram a red it could not stop for (s 3158, 10251). `committed` (our tram)
   needs `v > 1` (a tram standing at its stop line is not in the dilemma zone).
7. **Autopilot** (`autopilot.js`): when the GO starts blinking it stops if comfortable, else keeps
   going (`this.goThrough`): braking at 0.65 m/s² for a blinking GO it could not stop for took it over
   the line on red. Only when moving (`v > 1`): standing at the stop point it waits.
- Measured after: see the table at the end of §11.
- **`.claude/bench/redruns.js`**: the check (headless: keeps the camera at the cab, cars spawn around
  the camera; `tools/traffic_lint.js` in the original project may need the same).

## 11. U3: cars turning across the track in front of the tram

- **`src/traffic.js`**:
  - `_trackCrossings(path)`: where a car path (lane or junction connector) crosses our track (comes
    within 2.6 m of the centre line, |cos| < 0.7), cached on the path; none where our track is on a bridge.
    Line 17: 118 of 3 403 lanes and 199 of 5 815 junction connectors cross it.
  - **Give way**, replacing the 6 m look-ahead (and its abrupt stop): the first crossing within 45 m on the
    car's way (this path, the junction, the next lane); the car waits with its **front bumper 1.5 m before
    the 2.6 m band** (`CAR_HALF` 2.2: the position is the car's middle; `TRACK_ZONE`, `YIELD_GAP`) while the
    tram's body stands on the crossing, or while the moving tram would reach it before the car is across
    plus a margin (2.5 s; **bold drivers, one in eight** by car id: 0.5 s). A standing tram does not hold
    cars (user rule, unchanged). A car that can no longer stop (5 m/s²) is committed and crosses. Smooth
    stop through `following()` (it halts 8 m short of its gap: `xGap = front − YIELD_GAP + 8`).
  - `game.carsCrossing`: cars on the track band, or moving onto it (v > 1, front < 8 m); a car standing
    before it in a queue is not (that deadlocked the tram, s 11629). AI trams ahead stop short of them.
  - A crossing car where the tram's front is: `_collision('obj.crossingCar')` once per car.
  - **Indicators**: `turnOf(connector)` (left / right over ~30°, cached); blinking from 35 m before the
    junction and through it (`mesh.userData.blink`).
  - `c.bold`, `c.id` set together (no `this.rand`: the seeded runs stay comparable); `tx` = i18n `t`.
- **`src/models.js`** `makeCar`: four amber indicator lamps (+X = the car's left), `userData.blink(side, on)`.
- **`src/autopilot.js`**: stops short of a car crossing or committed to it (`c.s − 6`), rings the bell for
  one within 60 m while moving.
- **`.claude/bench/u3.js`**: the check: yields, crossings ahead, close cuts (on the track inside the tram's
  stopping distance), bells, collisions, our signal penalties (with a trail), where yielding cars' front
  bumpers stand, deadlock detection.

**Results, line 17, whole line, seeds 1 / 2 / 3, all changes of §10 and §11:**

| | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| cars that gave way to our tram | 32 | 35 | 33 |
| cars crossing ahead of the moving tram (within 100 m) | 37 | 28 | 33 |
| close cut-ins (inside its stopping distance; of them bold) | 3 (2) | 3 (1) | 2 (1) |
| collisions with crossing cars | 0 | 0 | 0 |
| **our tram's red passes** | 0 | 0 | 0 |
| **oncoming red runs** (before: 5-8, all avoidable) | **0** | **0** | **0** |
| AI trams ahead: red runs | 0 | 0 | 0 |
| passes on a blinking GO: oncoming / ahead | 2 / 7 | 2 / 2 | 2 / 7 |
| controller holds for oncoming trams | 2 | 4 | 2 |

- Yielding cars standing still: the first car's front bumper **3.2-4.5 m from the track centre line**
  (4.1 m designed for a square crossing; less on a slanted one); medians 6-9 m include queued cars. One
  0.1 m reading on seeds 1 and 3 is likely where our route passes near a car away from the crossing it
  waits for (the check measures to the nearest route point): to look at.
- Found on the way: in headless runs nothing moves the camera, and road cars spawn around the camera,
  so they stayed near the start of the line. Both bench checks keep the camera at the cab;
  `tools/traffic_lint.js` should be checked for the same (its car counts may come from the start area only).
- The traffic lint baselines will move (AI braking, signal decisions, give-way rule, crossing stops):
  re-baseline in the original project.
- Seen in the browser: a car turning right with its right indicators blinking.

## 12. Memory: the world's geometry dropped from JS after upload (PERF-ANALYSIS §5 item 6)

- **`src/main.js`**: new loading step **`gpu`** ("Handing the city to the graphics card…", i18n
  `load.gpu`): `uploadWorld()` draws one frame of the whole world with frustum culling off (all buffers
  and shaders to the GPU; before, geometry uploaded piecemeal as it came into view and the first frame
  after loading took seconds), and every world geometry attribute / index gets `onUpload(() => array =
  null)`; bounding spheres computed first (culling reads them).
- Kept with **`?bot`** (the street bot reads the meshes) and **`?keepgeo`**: **dev tools that read
  `window.world`'s geometry (`tools/lint.js`) must pass `?keepgeo`.** A lost WebGL context cannot be
  restored without reloading.
- Line 17: world geometry held in JS 659 MB → 0; **heap after loading 1 374 → 682 MB**; the gpu step
  0.7 s. Checked: shift in autumn with trees and litter (per-instance attributes are not geometry and
  stay), weather switching, no errors.

## 13. Pedestrians: a footway network, doors; B9 (walkers at the kerb); C14 (runners, switch iron)

- **`src/traffic.js`**:
  - `_linkWalks()`: the walks (OSM footways, generated sidewalks, cut where the survey has none; line 17:
    3 262, median 64 m; ends within 1 m of another walk 41 %, 1-3 m 28 %, 3-8 m 11 %, 8-15 m 12 %, more
    8 %) get links at both ends: to every walk within 3 m, else the nearest within 15 m (a street
    crossing), by straight link walks (`walk.link`), never across the tram's tracks. Line 17: 7 032 link
    walks.
  - Walkers at the end of a walk go on along a link: the one that best continues their way (`w.travel`,
    kept across link walks), not back to the walk they came from; at a dead end back. (Random links: a
    U-turn every 7 m, onto the parallel sidewalk / footway and back.)
  - `_findDoors(buildings)`: a door per OSM building footprint where the network passes within 8 m
    (line 17: 1 597 of 2 214), with a point 1.5 m inside; `this.doors`, `this.doorIdx` (50 m cells),
    `walk.doors`. Ready for more kinds (metro exits, stations) as entries of the same shape.
  - Spawning: 75 % out of a door (walking out of the building, which hides them; no fade), the rest on a
    footway far off as before (parks, squares). A walker has a goal of 80-480 m and then goes into the
    first door it passes.
  - **B9**: at the kerb, about to step into a car lane, a walker waits while a car would reach the spot
    within 4 s (`_carComing`); in the lane it goes on (cars stop for walkers on their path, as before).
  - Measured (`.claude/bench/walkers.js`, 4 game minutes at Palackého nám., tram standing): one U-turn per
    **153-165 m** walked (was: at the end of every walk, median 64 m); 109-111 out of doors, 29-33 in;
    295 steps (~10 s) of kerb waits.
- **`src/game.js`** (C14):
  - **Late runners** are people now: on arrival at a stop with runners they come running from behind the
    tram along the platform side (3.4-4 m/s, timed to arrive about `runnerDelay` later) to the rear door;
    doors open: they join `st.waiting` and board; doors closed: they wait at the door (the driver may open
    again); the tram leaving: left behind, penalty 15 (`msg.runnerLeft`). `game.runners`,
    `_spawnRunners`, `_updateRunners`, `runnersFor(st)`; the old instant "+runners to waiting" is gone.
  - **The switch iron** (X): a driver figure in a high-visibility vest walks from the cab door to the points
    at 1.6 m/s, crouches over them for 2 s and walks back (`_poseDriver`); the action lasts that long, at
    least 9 s as before (line 17 s 9125, switch 18 m ahead: 25.6 s).
- **`src/autopilot.js`**: does not close the doors while someone is still running for the tram.
- **`src/i18n.js`**: English "crowbar" → **"switch iron"** (user asked for a fitting word; British
  tramways: "point iron"); Czech keeps "stavědlo". The code keeps the name `crowbar()`.
- Whole line 17 with the autopilot (u3 check, seed 1): 25 runners, none left behind; no collisions, no
  signal penalty; cars gave way 27 times.
- Not done from B9: lanes of different roads that touch (line 22: 45), Vienna-type stops (needs the stop
  classifier, C13).

## 14. Lost WebGL context

- **`src/main.js`**: `webglcontextlost` on the canvas: the shift pauses and a card says the graphics
  stopped (the browser took the GPU back, possibly out of graphics memory) with a Reload button; before
  it was a frozen black screen, and since §12 the world cannot be rebuilt without a reload anyway.
  i18n `gl.lost`, `gl.lostWhy`, `gl.reload` (en, cs).
- GPU memory, for the record: WebGL tells nothing about VRAM; a dedicated GPU pages to system RAM
  (slower), an integrated one shares RAM, a phone / weak GPU loses the context. Remedies, in order:
  compact vertex formats + indexed DTM (PERF-ANALYSIS §5 item 5, ~half the 660 MB), tiles by distance
  (chunked loading: a ceiling on GPU memory), a quality option (view distance, DTM detail).

## 15. Tram signal placement

User: signals inside stops, in the middle of nowhere, after the junction (Kobylisy). Measured on line 17
(44 signals): 8 with no road, footway or crossing node within 30 m; several 28-62 m before their first
conflict; Kobylisy's junction signal (s 20819) stood after the whole junction (streets crossing 20766-
20798), matched by the builder to the far-side zebra at 20821.

- **`src/game.js`** `_routeConflicts()`: where streets, footways (OSM ways, not on bridges / in tunnels)
  and pedestrian-crossing nodes cross the route, `{ s, start, car }`; `start` = the near edge (half the
  way's width, longer at a slant); slanted crossings down to ~18° (Kobylisy's streets meet the curving
  track at a slant: "> 37°" missed most of the junction).
- `_placeSignals(list)` (before the platform rule in `_initSignals`): conflicts in clusters (gaps < 20 m)
  = a junction; a signal stands **4 m before its cluster's near edge** (`d.edge`); a signal matched to a
  pedestrian crossing right after an unsignalled street junction (within 25 m) moves to before that
  junction; **a far-side crossing of a junction that has its own signal is dropped** (Kobylisy 20819);
  **no conflict within 30 m: an on-demand crossing** (`d.demand`: a cycle path or footway we do not have).
  The platform rule moves a signal to the platform head only while that is before the junction's edge.
  Line 17: 6 on demand (7630, 7955, 8519, 8719, 14898, 19665), 1 dropped, the rest moved by -17 … +47 m
  (`game.signalMoves`, logged).
- `_runController`: an on-demand signal (straight ones) rests on GO for the trams until someone asks to
  cross (about every 2 min), then runs one cycle.

## 16. D2: traffic lights for cars and pedestrians

- **`src/traffic.js`** `_bindSignals()`: each street signal's controller gets the lane-graph junctions
  within 25 m of its crossing point; lanes ending there (not pieces starting inside the junction) are
  approaches, `lane.light = { sig, kind, head }`, kind `along` the tram street or `cross`. Line 17: 64
  heads (neighbouring lanes facing the same way share one), 99 lanes, 18 junctions (2-5 heads each).
- `lightAspect(L)`: along = green while the trams go straight (`backState` go), amber while their GO
  blinks, red, red-amber the last 2 s before green; cross = green in the cross phase, amber 3 s, all-red
  3 s, red-amber 2 s before green.
- **Cars**: stop at the stop line (front 1 m before the lane end) on red / red-amber, on amber when they
  can (3 m/s² after 1 s), else go and keep to it (`c.lightGo`); one that stopped keeps stopping until
  green even if it overran the line a little (`c.lightHold`); a lit lane shorter than 12 m has its light
  at the end of the lane before it (cars crossed such pieces on red in one step).
- **Pedestrians** (`_pedRed`): at the kerb within 30 m of a controlled junction: across the tram street
  with the cross phase, across the side street with the trams going straight (plus the car check, §13).
- **AI trams ask for priority** like ours (`sig.aiRequest`, from 140 m); the call lamp stays ours.
- **Priority cut through amber**: cutting the cross street's green now jumps to its amber (`C − 6`), not
  straight to 0 (that turned its cars from green to red at once).
- **Gridlock fix**: the waiting-cycle breaker follows "the car ahead on my way" (`c.lead`) too, not only
  what a car sees: three cars at an uncontrolled junction waited for each other for good and the tram
  behind them (line 17 s 21178).
- No car spawns within 50 m of a stop line that is not green (two came in at 10 m/s and ran the red).
- **U3 fixes found on the way** (collisions with crossing cars):
  - every track crossing within 45 m is checked, nearest first, and the car stops before the first one
    it must give way at (where the route loops, a car path crosses it twice; the car went by the first
    and met the tram at the second, line 17 s 21530);
  - **looking past short lanes**: `_seq` also chooses the lane after a next lane shorter than 45 m
    (`c.next2`, kept when the car gets there, `_advance`): a crossing two lanes ahead, beyond a 4 m piece
    in a junction's mouth, was seen only 5 m before the track (line 17 s 16855, seeds 1 and 2).
- Checked in the browser: Palackého nám. junction (s 12441) heads red / green as the phases run; the
  lost-context card (`WEBGL_lose_context`) pauses the shift and offers Reload.

**Results, line 17, whole line, seeds 1 / 2 / 3, after §15 and §16:**

| | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| cars into lit junctions: green / amber / **red** | 185 / 7 / **0** | 185 / 11 / **0** | 201 / 11 / **0** |
| cars that gave way to our tram | 51 | 51 | 50 |
| close cut-ins | 1 | 4 | 4 |
| **collisions with crossing cars** | **0** | **0** | **0** |
| deadlocks | 0 | 0 | 0 |
| our tram's red passes | 0 | 0 | 0 |
| oncoming / ahead AI tram red runs | 0 / 0 | 0 / 0 | 0 / 0 |

(Before the fixes in this section: 4-5 red entries per run, a deadlock on seed 1, a collision on seeds
1 and 2.)
- **`src/models.js`** `makeTrafficLights(heads)`: all car heads of the line as instanced meshes (pole,
  housing, backplate, 3 lamps with per-instance colour): ~5 draw calls in all. Czech sequence with
  red-amber.
- Not done: pedestrian signal heads; turn arrows / turn phases for cars; one controller per junction
  shared by several tram signals (needed where lines share a junction; on line 17 none do); the game's
  older "cross-street cars" at each signal (`_crossTraffic`) still run beside the lane-graph cars.

## 17. Signals at the junction edges, OSM signal data

The user saw tram signals and car heads in the middle of Palackého náměstí. Three causes, all fixed:

- **Car stop lines were the lane ends**: lanes run to 5 m short of the OSM junction node, the middle
  of the junction (a head stood on the tracks). Now `lane.light.back` = how far before the lane end
  the stop line is (`traffic._stopLine`):
  - an OSM `highway=traffic_signals` node on the approach in its last 40 m, matching direction
    (`src: 'osm'`; nodes within 6 m of the junction node are the old one-node-per-junction tagging,
    skipped);
  - else the junction edge: back from the end until clear of every street crossing it (half its
    width + 1.5 m) and, for approaches across the tram street, 4.5 m clear of the tracks (`'edge'`);
  - lanes under 12 m: at their start, as before (`'short'`).
  The head stands there; the car loop stops at `c.toEnd - L.back`. Approaches whose lane ends 25-50 m
  from the crossing point are bound too when OSM has a stop line on them.
  Line 17: 70 heads, 103 lit lanes (23 OSM, 72 edge, 8 short).
- **Tram signal matched to the far side of the junction** (`game._placeSignals`): it took the conflict
  nearest the crossing point; at Palackého (12435) that point lies between two clusters 27 m apart and
  the far one won (signal moved 36 m into the junction). Now the first conflict ahead of the signal
  (within 40 m) anchors it; nearest-to-crossing only as the fallback. Forward moves capped at 25 m.
  Results: Palackého 12405→12412, Kobylisy 20325→20327 (was →20343), 11733→11738 (was →11780),
  15997→15999 (was →16021).
- **Hung from a span over the junction** (`game._mount`): a signal took the nearest catenary span
  within 16 m, often one after its stop line. Now only spans at or before it (+2 m); a signal that
  must hang (platform) takes a later one only when there is none before. Every tram signal head on
  line 17 now stands at or before its stop line.
- **Bridge roads** count in `_routeConflicts` where they meet the track within 25 m of their chain's
  ends (the road off Palackého most enters the junction at street level).

**OSM data (`.claude/tools/osm_signals.py N` → `data/lineN.signals.json`)**: Overpass, in boxes of
~1.5 km of route, 5 s apart. Loaded optionally by `main.js` as `data.osmSignals`:
- `stop`: `highway=traffic_signals` with `traffic_signals:direction` (forward/backward along the
  way): the car stop lines (line 17: 201);
- `peds`: `crossing=traffic_signals` (198), not used yet (pedestrian heads, later);
- `tram`: `railway=tram_crossing` (319, 64 of them signalled: `sig`), added to the route conflicts.
- No `railway=signal` nodes for trams in Prague's OSM: the tram signals' positions still come from
  the game data, now placed by the rules above.
- Belongs in `tools/build_line.py` later; ODbL attribution (OpenStreetMap contributors).

Known gaps: the Palackého most approach has no inbound lane in the lane graph (one-way in our data);
several approaches at Kobylisy end farther than 25 m off and have no OSM stop node, so they stay unlit.

**U3 fixes found by the re-run** (seed 1 hit a car at s 9903, an unlit spot where cars turn into a lane
running on the tracks; the new lights changed the random sequence and exposed it), `traffic.js`:
- a car **standing or crawling** (< 1 m/s) always counts as able to stop (`canStop`): one held by the
  queue 0.9 m from the track band, inside `YIELD_GAP`, counted as committed and pulled out in front of
  the tram when the queue moved on (the actual cause);
- one crossing seen twice (the next path starting inside the band) counts once;
- a car **turning onto the track** (its way still on it 12 m past the band's edge, `x.along`) waits
  while the tram is within its stopping distance + 20 m, bold or not: it does not clear the band in a
  few seconds like a crossing car.

**Results, line 17, seeds 1 / 2 / 3, after §17:**

| | seed 1 | seed 2 | seed 3 |
|---|---|---|---|
| cars into lit junctions: green / amber / **red** | 206 / 16 / **0** | 208 / 17 / **0** | 217 / 14 / **0** |
| cars that gave way to our tram | 50 | 53 | 61 |
| close cut-ins | 3 | 1 | 2 |
| **collisions with crossing cars** | **0** | **0** | **0** |
| deadlocks / our signal penalties | 0 / 0 | 0 / 0 | 0 / 0 |

`redruns.js` seed 1: 0 AI tram red runs (2 passes on a blinking GO, 2 controller holds).

### 17b. Follow-up checks (zebras, stop posts vs OSM)

- **Projection bug in the OSM import (fixed)**: `osm_signals.py` used 111320 m per degree of latitude;
  the line data uses **110574** (latitude) and 111320·cos(lat0) (longitude). Fitted against all OSM
  tram ways along line 17: median 0.05 m off with 110574, the old one put the nodes up to 45 m off
  north-south at the line's ends (~1 m near Palackého, which is why the first screenshots looked
  right). Data re-fetched. The original build tool already uses the right conversion; note it for
  any other OSM import.
- **Stops vs OSM** (with the right conversion): 27 of 38 stops' tram front positions within 3 m of
  OSM's `public_transport=stop_position`, most others 3-8 m past it (the game stops the front at the
  platform end, OSM's node is often a few metres before). Outliers: Právnická fakulta +13 m,
  Hercovka +92 m and Vozovna Kobylisy −84 m (the nearest OSM node may be another direction's or the
  loop's, not checked further). Hodkovičky is correct: the platforms are staggered, the tram
  crossing (5981) lies between the end of ours (5976) and the start of the opposite one (5986).
- **Signal at a platform end** (`game._initSignals`): where the crossing follows right after the
  platform, the signal hung 12-15 m back over the platform, so at red the tram had to stop short of
  the platform end (Kublov: stop point 10246, the tram's stop 10261). Now its stop point is where the
  front stops for the passengers (or the crossing's edge if that comes first), hung from a span;
  a signal kept short of its junction by the 25 m cap uses the real edge for this (`d.farEdge`,
  Nádraží Modřany 4392 → 4418). Where the crossing begins before the platform's end, the stop's
  target and zone end move back to the signal's stop point (Staroměstská: the tram served the stop
  3 m past its red stop point and got a red-pass penalty leaving).
- **Signal along a platform matched from the platform end** (`_placeSignals`): Přístaviště's signal
  stood mid-platform 72 m before the crossing after the platform, matched nothing and ran on demand
  with its stop point 43 m before the platform end. Now the conflict search starts at the platform's
  end for such a signal. All 7 platform signals on line 17 now stop the tram at the platform end or
  at a crossing just before it. Left: Palackého náměstí stops at 12351 (the line data has a
  crossing at 12353 inside the platform; OSM's tram crossing is at 12363, the platform ends 12365);
  71 of the line data's 136 crossings have no OSM `railway=tram_crossing` within 5 m, too many to
  drop by that alone: worth a look in the build tool.
- **No car spawns within 50 m of the camera** (`_updateRoadCars`): the spawn ring's random point
  only picks an index cell, and a cell can reach the camera: a car appeared at 8 m/s 6 m before the
  track with the tram 4 m away (seed 2, s 19919; also cars popping into view next to the player).
- **Cars on zebras** (`traffic._stopLine`): 13 of the 56 lit approaches with a zebra had the waiting
  car's front bumper on it (computed edges and OSM nodes mapped on the crossing node alike). A zebra
  (OSM way with `z`) under the front or ahead, up to 4 m into the junction, now pushes the stop line
  to 2 m before its middle.
- **Pedestrian push buttons: not implemented.** Walkers never cross the tram tracks (they turn back
  before them); only the obstacle "jaywalkers" at unsignalled crossings do. On-demand tram signals
  get a random request about every 2 minutes (`sig.request`). Proposal: walkers crossing at signalled
  crossings (OSM `peds` nodes now loaded), pressing the button (`sig.request`) and crossing in the
  cross phase.
- With the corrected OSM data: 72 car heads, 105 lit lanes, 53 stop lines from OSM (was 23), 44 at the
  computed edge, 8 short lanes; 0 of 25 approaches with a zebra stop on it (closest 1.5 m before).

**Results after 17b, line 17, seeds 1 / 2 / 3:** cars into lit junctions on red 0 / 0 / 0 (green
244 / 219 / 210, amber 17 / 15 / 15); gave way to our tram 59 / 45 / 49; close cut-ins 0 / 0 / 0;
collisions 0 / 0 / 0; deadlocks 0; our signal penalties 0. `redruns.js` seed 1: 0 AI tram red runs.

## 18. Batch bench runner (dev tool), open item

- **`.claude/bench/batch.html`** runs the headless benches unattended, each in a fresh copy of the game
  in an iframe, and lists pass/fail per run, with thresholds as in `BUILD-TOOLS-HANDOFF.md` §4.2.
  - Results are kept in the page's localStorage; "Download JSON" saves them.
  - No Node or Playwright needed: any browser on the served project. Example:
    `http://localhost:8743/.claude/bench/batch.html?lines=17&seeds=1-20&benches=u3,redruns&autorun`
  - Keep the tab visible; ~3 min per run.
- **Found by the first batch runs, fixed:**
  - **Autopilot red pass** at Čechův most (s 14907, seed 4), in `src/autopilot.js`:
    - the tram rolled up to the stop on a blinking GO and marked the signal `goThrough`;
    - it then stopped at the platform, whose stop point (since §17b) is the signal's;
    - the "red after all" cancel only fires while the tram can still brake before the line, which a
      standing tram at 0 m cannot, so it drove off on red after the doors closed.
    - Fix: a standing tram (< 0.3 m/s) always drops `goThrough`.
  - **Car spawned before a red line** (seed 5), in `traffic.js`:
    - the no-spawn zone near a non-green light was measured from the lane end;
    - the stop line is now up to 40 m before it (§17), so a car could appear 10 m before a red line at
      11.5 m/s.
    - It is now measured from the stop line.
  - **Cars crossing a stop line on red near a lane's start** (`traffic.js`):
    - since §17 a stop line can sit 2-6 m into a short lane (OSM nodes, junction edges);
    - cars looked at the next lane's light only for lanes under 12 m, so they came onto such a lane
      already at the line at 4-11 m/s and crossed it on red (s 11785, 14839, 16161, 17244; 3-5 per
      run);
    - the old bench missed them because it judged only junction entry.
    - Fix: a car looks ahead to the next lane's stop line (from its lane or from a junction connector)
      whenever it is within 60 m.
  - **A stop line 38 m before its junction** (s 14839): the "4.5 m clear of the tracks" rule walked
    back along a lane running on the rails. It no longer applies where the lane runs along them
    (|cos| > 0.8 with the track).
- **Palackého náměstí checked against the user's orthophoto and street view** (`src/game.js`):
  - **The layout:** our platform is an island between our track and the northbound road. Two zebras
    run from the island across the road only. A signalled track crossing ("pozor tramvaj" signs, no
    zebra paint) is at the platform's north end (OSM 12363). The red post stands just before it,
    where OSM has its stop position.
  - **Road-only crossings no longer stop the tram** (`_routeConflicts`): a crossing of the line data
    inside our platform with no OSM track crossing within 5 m (only when OSM data is loaded) is a
    zebra from the island across the road, projected onto the track by the build. Also Jiráskovo nám.,
    Strossmayerovo nám. and Veletržní palác (screenshots in the session). Palackého's signal now stops
    the tram at 12360.5, the passenger stop point too (was 12351 since §17b; 12366, on the crossing,
    before that).
  - **The stop post follows the stop point** when the signal rule pulls it back (`stop.signPlace`); it
    stood 6 m past the real one, on the crossing.
  - **The tram signal at a platform end stands on the platform head** (`d.head`), not hung from a span
    20 m back over the platform. Following the user's close-up photo, it stands on its own pole at the
    island's tip: a few metres past the post (at the signal's s, at most 0.5 m before the platform end)
    and 3.5 m from our track, against the post's 2.3 m. The post therefore no longer hides it from the
    driver (checked from the cab position).
    - In reality the same pole carries the crossing's pedestrian heads, which are not modelled yet.
    - The real head has a different side design.
  - **The shelter stays on the drawn platform** (`_buildStop`): OSM's island is 6.2 m out from our track,
    the surveyed (DTM) one ends at 4.5 m, and the shelter, 0.6 m inside OSM's edge, stood on the road.
    The outer edge is now the DTM platform's where the survey draws one.
  - **Still missing:** zebra paint on those two road crossings, and car heads for them (the road's
    stop lines are in OSM, the yellow marks in the user's image). This is pedestrian-signal work (§17b
    proposal).
- **`u3.js` judges car red entries where the car crosses its stop line** (falling back to junction
  entry), and records the lane, its stop-line source and `back`, the spawn position and the junction.
- **Batch results** (line 17): `u3` seeds 1-6 clean (0 red at the stop line, 0 collisions, no
  deadlock, no signal penalty); `redruns` seeds 4 and 5 clean. After the Palackého changes: `u3` seeds
  1-3 and `redruns` seeds 1-2 clean; the `redruns` seed 3 run was cut off by a page navigation and not
  repeated.
- **`src/debugOverlay.js` (new)**: press **F8** (or load with `?debug`) during a shift for the markers
  used in the screenshots:
  - tram signals (magenta ball) and where the tram stops for them (magenta bar);
  - car stop lines: cyan = OSM, yellow = edge, white = short lane; car heads as yellow balls;
  - raw OSM stop nodes as red dots;
  - route conflicts' near edges as white bars;
  - platform ends (green bars) and the passenger stop point (green ball).
  - It is wired into `main.js`: the import, the F8 key, `?debug`, and a reset on each new shift.
- **`.claude/tools/osm_validate.py` (new)**: the handoff §3 checks from the data files plus a cached
  Overpass download (`.claude/tools/cache/lineN.osm.json`), written to `data/lineN.validate.json`.
  It checks:
  - the coordinate fit;
  - stops vs OSM stop positions;
  - crossings without an OSM crossing node;
  - tram signals along platforms;
  - crossings inside platforms.
  - Run it as `python -I .claude/tools/osm_validate.py 17` (add `--refresh` to re-fetch).

## 19. Annotation and compiled-world formats (proposal + runtime export)

- `ARCHITECTURE-PROPOSAL.md` §10: an annotation editor whose output is **ground truth that the rules
  are scored against** (`truth` / `verdict` / `override` with expiry, reviewed areas), plus the shared
  GeoJSON formats (WGS84) for the compiled world and the annotations, and the scoring.
- **`src/debugOverlay.js` `builtGeoJSON(game, traffic)`**, exposed as **`window.exportBuiltGeoJSON()`**
  in `main.js` (saves `data-lineN.built.geojson`; pass `false` to only return it). It exports what the
  rules decided at run time in that format:
  - stop points and posts, tram signals (`mount`, `rule`) and their stop lines;
  - conflicts, car stop lines (`source`), car heads.
  - Line 17: 1,079 features.
  - Signal ids come from their input position (`d.s0`, kept by `_placeSignals`), so they stay stable
    when the placement rules change.
- The build should write the same file (`data/lineN.built.geojson`) once the rules move into the
  compiler.

## 20. Open data search: signals, poles, markings

See `BUILD-TOOLS-HANDOFF.md` §2.7b. Found: the archived Prague technical map's street furniture
points (CC BY):
- traffic signal heads, including tram signals;
- public transport stop signs, poles and lights.

They are accurate where present (Palackého náměstí: stop sign ~3 m, tram signal pole ~1 m), but
coverage is patchy. Not found as open data: a traffic signal installation dataset, road markings.
New `.claude/tools/dtm_points.py` writes `data/line17.dtmpoints.json` (223 KB).

- **Head labelling prototype:** `.claude/bench/heads.js`; results and the plan are in
  `BUILD-TOOLS-HANDOFF.md` §2.7c.
- **First fit applied** (`traffic._bindSignals`): car signal heads stand 4 m past the stop line (the
  surveyed poles' median is +4.2 m), never past the lane end.
  - Distance to the nearest surveyed car pole: median 5.5 → 4.7 m, 10th percentile 3.0 → 0.7 m.
  - Visual only: cars still stop at the stop line (`lane.light.back`).

## 21. Pedestrian signal heads, zebras at OSM signalled crossings

- **`src/models.js` `makePedLights(heads)`:** instanced pedestrian heads (pole, housing, red over
  green square lamps), the same interface as `makeTrafficLights`.
- **`traffic._bindPedHeads()`:**
  - **Which crossings:** every OSM signalled crossing (`data.osmSignals.peds`) whose node is within
    45 m of one of our tram signals' crossing or stop point.
  - **Heads:** one on each kerb of the nearest car road (half its width + 0.6 m out), facing the
    opposite kerb; none on the rails. `this.pedCross` lists the crossings.
  - **Phases (`_pedAspect`):** walking across the tram street or a road along it, green in the cross
    phase; across a side street, green while the trams go straight. These are the same rules walkers
    already followed.
  - **Walkers obey the heads:** `_pedRed` gives them priority within 6 m of a crossing node, walking
    along it.
  - **Line 17:** 188 heads at 110 crossings.
  - **Palackého náměstí:** the two crossings from the island over the road (12353, 12363, the user's
    orthophoto) have heads. Checked: both face the opposite kerb; red while the trams go, green in
    the cross phase.
- **`world.js` `buildZebras`:** also paints OSM signalled crossings that have no zebra way of their
  own, across the nearest car road kerb to kerb (Palackého's two had no paint).
- **Not done:**
  - snapping the heads to the surveyed poles (`dtmpoints`), e.g. the shared pole at the island tip;
  - the walking and standing figures on the lamps;
  - the blinking green before red.
- **Walkers bench, 120 s at the start stop:** 365 m per U-turn, no stuck walkers.

## 22. Street detail from the technical map

- **`dtm_points.py`** also fetches covers and small furniture:
  - manholes (several networks' shafts), gutter inlets, hydrant caps, above-ground hydrants, valve caps;
  - phone booths, transformer stations, fountains.
  - Line 17: 5,815 manholes, 5,271 valve caps, 2,571 gutter inlets, 766 hydrant caps, 43 hydrants, …
  - `data/line17.dtmpoints.json` is now 836 KB.
- **`main.js`** loads it optionally as `data.dtmPoints` (prefetched with the line's files) and adds
  the IPR attribution.
- **`world.js` `buildStreetDetail(data, ground)`**, added to the world after `buildWorld`:
  - **Kinds:** manhole covers and valve and hydrant caps as flat discs; gutter inlets as grates
    turned along the nearest street; above-ground hydrants as small red posts.
  - **Cost:** one instanced mesh per kind (5 meshes, 14,089 instances on line 17).
  - **Doubles:** one shaft recorded under two networks' codes gives one cover (within 0.3 m).
  - **Covers in the track** sit on the paved track bed (track height + 0.16 m) where that is above the
    street's height. Otherwise they were hidden under it; most covers at Strossmayerovo náměstí lie
    between the rails.
  - Checked from above at s 16260: covers on the pavement, the road and in the track.
  - Coverage follows the survey, so some places have none (Palackého náměstí).
- **Not drawn yet:** phone booths, transformer stations, fountains (they need models); street lights
  and poles from the same file (see `BUILD-TOOLS-HANDOFF.md` §2.7c step 3).
- **Caps made smaller** (user): valve caps 0.12 m and hydrant caps 0.2 m across (were 0.18 and
  0.26 m). Reference photos of the covers will follow.
- **Safety benches after §20–22** (line 17, seeds 1–3; car heads moved 4 m, pedestrian heads with
  walkers obeying them, zebras, street detail, smaller caps):
  - `u3`: all clean: 0 red at the stop line, 0 collisions, no deadlock, no signal penalty; gave way 36 /
    36 / 44.
  - `redruns`: all clean: 0 AI tram red runs, our signal penalty 0.
  - The page was navigated away twice during a batch (to a blank `data:` page, not by a bench); the
    cut-off run was repeated alone.
- **Notes for future rebuilds** in `BUILD-TOOLS-HANDOFF.md` §2.7d: track bed styles, cover sizes,
  IPR's photorealistic 3D mesh, and the DTM exchange format change to JVF 1.5.0.2 (10–18 Nov 2026).

## Dev server for this copy (not part of the game)

- `.claude/serve_nocache.py [port] [KB/s]`: static server with `Cache-Control: no-store` (Python's
  `http.server` let the browser keep stale modules after edits); optional per-response rate limit.
- `.claude/launch.json`: added `tram-static` (port 8743) and `tram-slow` (port 8744, 1500 KB/s);
  the original `tram` entry (tools/serve.py) is unchanged.
