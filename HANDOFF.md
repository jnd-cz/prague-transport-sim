# Handoff notes — Tatra T3 Prague tram game

State as of 2026-10-22, evening (sections 13–16 are from 2026-10-22). Read with README.md (how to
run/build/play).
This file records what was found while building it, what is unfinished, and what needs attention.
**Priorities and next steps: PLAN.md.**

## 1. Current state

- Browser game, plain ES modules + Three.js 0.160 from jsDelivr (import map in `index.html`), no build step.
- Playable lines: **9, 17, 22, 23** (menu "Line" selector; `?line=N`). All four complete end to end
  under the autopilot in dry weather with no stop/signal/switch/collision errors (rain also passes; the
  only penalties are comfort/speed/lateness from the conservative driver).
- Features: T3 pedal-style controller and force-based physics, gradients from lidar terrain, weather
  adhesion + sanding, GTFS timetable + stops + passengers with rush-hour demand, doors, overhead
  contact switches (worked by the pantograph), one- or two-car T3 sets, Prague 4-lamp tram signals with call (výzva) indicator and distant (P) signals, the Letenská
  single-track (gauntlet) block, traffic (trams ahead/oncoming, cars, pedestrians), obstacles,
  Czech/English UI, scoring, results screen, **watch-the-ride autopilot** (menu or `O`).
- Since 2026-10-22: curve speeds from lateral acceleration + OSM posted speeds, banked (canted)
  curves on dedicated track, junction controllers with fixed cycles and tram priority (oncoming AI
  trams obey them), cars on a lane graph (smooth lanes, junction turns, give-way, following trams on
  shared track), menu options for automatic switches and a performance overlay (see §16).
- Testing since 2026-10-22: lints per line with a committed baseline, including a deterministic
  headless traffic run of the whole line (`tools/lint.js`, `tools/traffic_lint.js`; §2, §16).
- World: OSM tracks/roads/greenery/water, ČÚZK DMR 5G terrain, and (where imported) IPR Praha LOD2 3D
  buildings, surveyed retaining walls and the city tree register.
- **Not play-tested by a human beyond the user's own sessions.** Verification so far = headless
  autopilot runs + screenshots in the desktop app's browser pane.
- Git repository on branch `main` (initial commit `998c94d`). `raw/` (420 MB download cache) is
  ignored; the generated `data/` files (~26 MB) are committed so the game runs without rebuilding.
  No remote is configured.

## 2. Run, build, test

```bash
python tools/serve.py 8742                                     # dev server, no-cache headers (any free port)
python -I tools/build_line.py --line 22 --headsign "Zahradní Město"   # OSM + GTFS + terrain -> data/line22.json
python -I tools/build_line.py --line 23                        # other lines: headsign auto-picked
python -I tools/geoportal.py --line 22                         # LOD2 buildings, walls, trees -> line22.geo.json + .bld.bin
```

Headless rule test (browser console on the running page):

```js
const { autopilot } = await import('/tools/autopilot.js?v=' + Date.now());
autopilot(0, 99, { obstacles: 'normal', weather: 'rain', maxT: 5400 });   // returns {T, finished, score, pen, out}
```

One full-line run takes ~15–20 s; a browser script call times out at 45 s, so run one line per call.
Last baseline (dry, obstacles normal; two-car sets except 23): line 22 ≈ 3550–3580 s sim time (also at −6 °C),
23 ≈ 1880 s (rain, summer), 17 ≈ 3240 s, 9→10 run ≈ 2580 s (stops 0–29) + 3250 s (28–59); all finish, no `bad:`
messages except comfort/lateness.

Lints (counts per line vs a committed baseline): `tools/lint.js` + `python tools/lint_report.py`, see
README → Dev and PLAN.md §2. `lint({ traffic: true })` drives the whole line headless with the real
traffic (asynchronous, poll for the result: line 23 ~1 min, 17 ~2.5 min, 22 with `bot: true` ~4 min,
9 ~4 min). Run each line on a **freshly loaded page** (deterministic per page load). A traffic run
that does not finish (`traffic.finished: false`) means a jam: follow `car.seen.car` from the car in
front of our tram to the car that waits for something else (§16 has the cases found so far).
After an intended change: `python tools/lint_report.py` (traffic counts have a 15 % + 5 noise band),
then `--accept` and commit `reports/baseline/`.

Debug hooks on the running page: `window.game`, `window.traffic`, `window.camera`, `window.world`,
`window.tramModel`; set
`window.freeCam = true` to position the camera from the console (the frame loop stops moving it).

## 3. Code map

| File | Role |
|---|---|
| `src/main.js` | loading (line JSON + optional geo sidecar), renderer, weather/world rebuild, menu, input, camera, frame loop, results |
| `src/route.js` | `Route` (arc-length polyline, **smoothed** with original s preserved), `smoothPolyline`, nearest/radius/speed limits |
| `src/terrain.js` | `Terrain` (DMR 5G grid), `Profile` (track z(s): bridges, tunnels, 9 % grade limiter, smoothing), `carveCorridor` (bench + synthetic retaining walls), `makeGround` |
| `src/world.js` | static scenery: terrain chunks, roads, tracks (+smoothed heights), Most Legií deck/piers, walls, buildings (LOD2 or OSM fallback), trees, catenary |
| `src/tram.js` | T3 constants and longitudinal dynamics (forces, adhesion, slip/slide, sand, rollback, electrics); `Tram(cars)` scales mass, forces, length, capacity; `panto` = pantograph position |
| `src/game.js` | rules: stops/passengers/demand, doors, signals, gauntlets, distant signals, switches/IRC/contacts, obstacles, cross traffic, scoring |
| `src/traffic.js` | ambient cars (street lanes + road network), pedestrians, AI trams ahead/oncoming |
| `src/autopilot.js` | shared driver (watch mode + headless tests) |
| `src/models.js` | T3 set (`makeT3({line, cars})` + `placeConsist`), cars, people, signal head + call box, LED switch indicator, signs, red stop post |
| `src/hud.js` | dashboard gauges/lamps, top bar (incl. passenger counter), hint chips, minimap |
| `src/i18n.js` | all UI strings, cs/en, `t()`, live language switch |
| `src/audio.js` | Web Audio synthesis (motors, rolling, joints, squeal, bell, doors) |
| `tools/build_line.py` | Overpass + GTFS + ČÚZK terrain → `data/lineN.json`, `data/lines.json` index |
| `tools/geoportal.py` | IPR Praha I3S buildings + walls + trees → `data/lineN.geo.json`, `data/lineN.bld.bin` |
| `tools/autopilot.js` | headless test harness around `src/autopilot.js` |
| `tools/serve.py` | static server with `Cache-Control: no-store`; `POST /report/<name>.json` saves lint reports to `reports/` |
| `src/streetbot.js` | street bot (`?bot`): samples every lane, junction turn and footway against the drawn surfaces |
| `tools/lint.js` | per-line lints (consist, signals in platforms, trees in buildings, bridges, invented walls, tram envelope, grade separation, street bot, traffic run) |
| `tools/traffic_lint.js` | headless traffic run: slide, jump, overlap, walker hit, heating knobs, red runs |
| `tools/lint_report.py` | compares `reports/lineN.json` with `reports/baseline/`, `--accept` |
| `tools/osm_speeds.py` | OSM `maxspeed` of the tram ways + dedicated-track flag every 5 m → `speed` in `data/lineN.json` |
| `tools/dtm.py`, `tools/gpkg.py` | Prague DTM (ZPS) importer → `data/lineN.dtm.json` |
| `tools/streets.py` | street model (smooth surfaces, offline mesh) for a stretch of a DTM line |
| `data/truth.json` | ground truth from the user (stop types, rules, places) that lints are scored against |

## 4. Data sources and findings

**OpenStreetMap (Overpass)** — route relations (PTv2), tram track ways, traffic signals, crossings,
buildings (fallback), roads (with `oneway` → `o`, vehicle class → `c`), greenery, water.
- Public Overpass servers are frequently overloaded (502/504). `overpass.private.coffee` returned
  **empty results** silently and was removed. Current order: `maps.mail.ru` mirror, then overpass-api.de,
  10 attempts with exponential backoff; empty results count as failure. Green/water are optional.
- Cache keys: `raw/route_<relationId>.json` (keyed by relation!), other queries by name in `raw/`
  (line 22) or `raw/lineN/`. Use `--refresh` to re-download.
- Water must be fetched with `out geom` (not `out tags geom`) or relation members are dropped.
- Track ways are merged into chains (split only at junctions/bridge ends) so smoothing has no kinks.
- **Switch detection** (facing only): a node on the route with an extra track neighbour whose branch
  heads forward. Trailing switches are skipped (the branch heads backwards). A neighbour that is part
  of a track passing straight *through* the node is a **diamond crossing**, not a switch. On line 22
  this removed 16 of 33 "switches" (side-street curves crossing our track to join the opposite
  track). The remaining facing switches were checked on plots: all real turnouts.
- Roads: `c` (vehicle class) now also excludes `vehicle`/`motor_vehicle`/`motorcar` = no / private /
  destination / delivery; `z` = painted crossing (`footway=crossing` + zebra / marked / uncontrolled /
  signal-controlled, or `crossing:markings`).
- Tunnels/underpasses on the route come from `tunnel`, `covered=yes`, negative `layer` tags.

**PID GTFS** (`raw/PID_GTFS.zip`, data.pid.cz) — trips, stops, stop_times, route_stops (line numbers
on stop posts; night lines excluded via `is_night`). Service date fixed: **2026-10-21**.
- Headsign auto-choice = direction-0 headsign with most trips on that date. **Line 22 must be built
  with `--headsign "Zahradní Město"`** (auto picks the Vypich → Nádraží Hostivař variant).
- Build aborts if >15 % of GTFS stops are >25 m from the chosen OSM route (wrong relation/variant).
- **Line 9:** the route is 17.3 km but the last stop is at 14.3 km — the OSM relation continues past
  the terminus (probably a depot/turning run). Check and trim.

**ČÚZK DMR 5G** (ags.cuzk.gov.cz ImageServer `exportImage`, uncompressed float32 TIFF, 10 m grid) —
bare-earth lidar. Heights verified (Bílá Hora 382 m, Malostranská 189 m). Being bare-earth it contains
embankments over underpasses → handled by tunnel spans + the 9 % grade limiter.

**IPR Praha / Geoportál Praha** (CC BY 4.0, credit "data base © IPR Praha"). 226 datasets; useful ones:
- *Budovy 3D* — I3S 1.7 SceneServer `services5.arcgis.com/SBTXIEUGWbqzUecw/.../Budovy_3D_WSL1`,
  mesh pyramids, Web Mercator, absolute heights (same datum as DMR 5G), **untextured** LOD2
  (~25 % sloped roof triangles, ~130 tris/building). Node pages and geometry are **gzipped**; geometry
  buffer 0 is uncompressed (we ignore the Draco buffer). Leaf nodes ≈ 600 × 350 m.
- *Opěrné zdi* (retaining walls) FeatureServer, attribute `vyska` (height); includes Chotkova tram walls.
- *Sdílená data o zeleni – vegetační prvky – body* (individual trees; geometry is **multipoint**),
  *Stromořadí* (tree rows, sampled every 9 m).
- Not imported yet: *Mosty 3D* (bridges SceneServer), *Ortofotomapa 10 cm* (ImageServer
  `gs-pub.praha.eu/imgs/rest/services/ort/letecke_snimkovani/ImageServer`, S-JTSK), roof eave heights,
  floor counts, DMP 1 m, contours, PID lines layer.
- **No** tram rails/platforms/poles/signals in the open catalogue (DTM is archive utilities only).

**Tatra T3 figures** (ČKD pamphlet via Tramway Museum Society of Victoria; not verified against the
original): 16 t empty, 4×40 kW, max tractive effort ~39 kN, max accel 1.8 m/s² and max service decel
1.8 m/s² (empty), max decel 5 m/s², 24 seated + 86 standing, crush 160. Implemented as fixed forces
(J4/B4 ≈ 28.8 kN, track brake 44 kN), so loaded trams are slower.

**Prague signalling** (asokol.cz illustrations, user photos): main head = 4 white lamps (3 top + 1
bottom) on a white backplate; stop = outer two, go = top-middle/left/right + bottom; call box below
with three LED bars \ | / lit orange for the coming direction, blinking before GO (TSK guideline ~3 s);
distant signal with yellow "P" plate. Switch indicator = red LED chevron box hung on the span wire,
blinking while locked. Modern red stop post with blue tram pictogram (user photo).

## 5. Heuristics that stand in for missing data (review if realism matters)

- **Signal positions**: clusters of OSM `highway=traffic_signals` within 30 m of the route, placed 6 m
  before the cluster; moved past a stop sign if they'd block the platform. Phase timing random with
  tram priority; GO is held for a tram in its "dilemma zone" (`15 + v²/1.6` m).
- **GO direction** from heading change across the junction (±0.45 rad).
- **Distant signals** where the curve radius within 140 m before a signal is < 110 m.
- **Gauntlets** = stretches where the opposite-direction route is < 1.8 m away for ≥ 25 m (only
  Letenská found on these lines). 6 s clearance.
- **Contacts** at switch s − 22 m (real positions unknown), all switches manual: the user wants the
  skill of powering/coasting near stops, signals and hills, so the IRC conversion was removed. The
  contact is triggered by the **pantograph** (5.4 m behind the front). If it would lie where a tram
  stands with its pantograph (stop zone, 25 m queue before a signal) it is moved after that area (if
  at least 10 m remain before the switch) or else just before it. Consecutive switches keep their
  contacts ordered and at least 4 m apart (Anděl three-way). Switches whose contact is behind the
  tram at the start are pre-set.
- **Two-car sets**: lines other than 23 default to two cars (menu "Set" overrides). Forces, mass,
  resistance, capacity and door flow x2; length 28.4 m. Real 2026 operation differs (T3s are mostly
  retired); the default follows the user's request.
- **Tram streets**: a road whose centre line runs within 2.6 m of a track for at least 60 % of its
  length is widened by 3.2 m per track (OSM `lanes` counts only car lanes). Street car lanes then sit
  at ±(w/2 − 1.7) m, beside the track zone.
- **Catenary poles**: per station (12/18/25/32 m by curve radius) march outwards on each side past the
  tracks (2.3 m clearance) and the carriageway; the first free spot is the kerb and gets a pole, unless
  an OSM building footprint is within 5.5 m behind it, which gets a wall rosette. If one side has no
  anchor, a bracket arm (anchor at most 9 m out). Only along our route; other tracks get wire only.
- **Cross traffic** at signals drives along the real crossing street (extended through connecting
  ways), only where one exists (pedestrian signals get none), with a red phase while the tram has GO
  plus 3 s, and yields to a tram entering.
- **Trees**: real trees at least 3.2 m from any track, crown limited to stay 1.9 m from the track
  centre; duplicates (register + sampled tree rows) merged per 1.5 m cell.
- **Terrain under tracks**: `Terrain.height` interpolates on the mesh's own triangles; after track
  heights are computed, the three vertices of the triangle under every bed sample (centre, ±1.4 m)
  are lowered by any excess. Verified: 0 bed samples under the terrain on line 9.
- **Speed limits** from curvature (R<25 → 10 km/h … ≥250 → 50), 15/30 km/h over switches, 25/35 on
  steep descents; HUD/autopilot report the most restrictive limit ahead by braking need.
- **Stop zone**: front within −20…+12 m of the sign; precision bonus ±3 m.
- **Demand curve** by time of day (peaks 7–9:30 and 15:30–17:30) scales waiting passengers.
- **Adhesion**: dry 0.30, rain 0.17 (±0.02), leaves 0.15 with 0.06 patches; sand +0.1.
- **Terrain carve**: bench ±7 m at track level; synthetic wall + cap where the hillside rises >1.5 m;
  synthetic wall faces suppressed within ~8 m of a surveyed wall.
- **LOD2 buildings near the track**: if any vertex is < 2.5 m from the route, every vertex below
  track + 6.3 m is lifted (makes passages like Letenská). Others: bottom vertices sunk 2.5 m.
- **Facades**: generic window texture, u along wall / v from building base, colour per building;
  roofs tile colour if sloped, grey if flat.

## 6. Needs attention / known issues

1. **LOD2 alignment not measured** — looks right visually, but the Mercator→local conversion has not
   been checked numerically against OSM footprints/tracks. Do a quick offset check.
2. **Building lift heuristic** may also lift buildings that merely overhang near the track.
3. ~~Tree species flag~~ — resolved: the layer's coded values say 1 = conifer; the vegetation kind
   (tree / bush / planter / climber) is used since 2026-10-22 (§16).
4. **Retaining walls** are drawn freestanding from the lower ground up to `vyska`; which side is
   retained is not in the data.
5. **Line 9** route extends ~3 km past the last stop (see §4).
6. ~~Street cars~~ — replaced by the lane graph (§16): cars drive on shared track and follow the
   tram there; junctions have give-way. Remaining traffic issues: see §16 "Open".
7. **AI trams** carry a line that serves the stop where they appear and fade out after the last stop
   they share with us. They do not actually drive off along their own branch, and they have no
   timetable (random spawn every 40–120 s). See §10 for the proper fix.
8. **Asset sizes**: 26 MB raw / 8.6 MB gzip for four lines (see §10); `serve.py` doesn't gzip.
13. **Pole placement** depends on OSM road widths (class guesses or lanes x 3.2 + tracks) and OSM
    building footprints (not LOD2); wide junctions and squares fall back to bracket arms or no poles.
14. **Signals** without a real crossing street get no cross traffic (28 of 45 on line 22 have one);
    at a complex junction the nearest of several streets is picked.
9. **Draco**: importer reads the uncompressed geometry buffer; if IPR switches to Draco-only it breaks.
10. **Audio** was never listened to by me; mixing levels are guesses.
11. Only tested in the desktop app's Chromium browser pane; keyboard only (no gamepad/touch).
12. `hud.js` minimap draws all track chains every frame (cheap enough now; watch on long lines).

## 7. Backlog (user requests and agreed ideas)

- **Cab dashboard**: more detailed 3D/realistic T3 control panel — deferred by the user (no good
  reference photo yet).
- **Day/night cycle**: headlights and interior lights (passenger comfort) — see §11 item 4.
- **RÚIAN building attributes** for real panel/church/industrial classes (see §9a).
- **Orthophoto** ground texture (10 cm IPR ImageServer) — explicitly skipped "for now".
- **Mosty 3D** bridge models: used for deck heights and drawn as a plain slab (since 2026-10-21);
  bridges as models by type (arches, steel arch, viaduct) are PLAN.md C16.
- Two-car T3 set (double length/mass, stop position), night/dusk with lights, snow/ice, gamepad
  (triggers = pedals), real speed-sign positions, more lines (any Prague line works via the two tools).
- Better pedestrians (walking animation, boarding into doors). (Cars on shared tram lanes: done.)
- Hosting: static site; gzip/brotli data; stream tiles (§10).
- **Whole network** (§10): every OSM tram track, tiles loaded on demand, AI trams on their real
  lines and timetables.

## 8. Environment gotchas (Windows dev machine)

- Run Python tools with `python -I`; `-I` ignores `PYTHONIOENCODING`, so scripts call
  `sys.stdout.reconfigure(encoding="utf-8")`. PIL is only available without `-I`.
- Bash heredocs with apostrophes or backticks in the body break the tool's shell parsing — write
  patch scripts to a file (scratchpad) and run them instead.
- The browser caches ES modules aggressively; the dev server sends `no-store` headers. It runs on
  **port 8742** now (`.claude/launch.json`): the user runs another session's server on 8740 — do not
  use or stop that one. Use `import('/tools/autopilot.js?v=' + Date.now())` in the console.
- A browser script call times out at 45 s: start long runs without awaiting them (store the result in
  `window.__…`) and poll in further calls. While `window.headless` is set the page's frame loop only
  draws (the test steps the game itself); the mirror pauses too.
- When the browser pane is hidden, `requestAnimationFrame` is throttled: screenshots can show stale
  frames and real-time waits barely advance the game. Prefer stepping the sim in JS.
- The frame loop schedules the next frame first, so one exception doesn't freeze the game; still
  check the console after changes.
- Old console entries `t.forEach is not a function` (hud.js:228) are stale from before a fix.

## 9a. Session 2026-10-21 (evening): what changed

- **Runs with a line change** (`build_line.py --then`): GTFS shapes map-matched on the city-wide
  OSM track graph (`raw/run9-10/network_tracks.json`, 24 k nodes): piecewise Dijkstra in 250 m
  windows, cost ∝ distance from the shape, extra for the left track and for running against the
  shape, no turns > 75°. Goal = first node at/after the window end along the shape (OSM nodes can
  be 100 m apart on straights). Corridor queries use `way(id:…)` of the matched ways. Output gets
  `segments: [{line, from}]`; the game switches `game.line` after the last passenger of the old
  line has left at the change stop (`onLineChange` → HUD, route boxes via `setConsistLine`).
  GTFS: 9 and 10 share stop pole U469Z4P; 212 arrivals / 212 departures, layover 4–11 min.
  Old line-9 data (relation-based, ran 3 km past the terminus) is replaced.
- **Platforms** (OSM `public_transport=platform` / `railway=platform` ways projected with a
  ±150 m s-window, right side preferred) → `p0/p1` per stop; 58/60, 37/39, 16/18 stops have one
  (20–108 m). Stop zone: rear ≥ p0 − 3 m, front ≤ p1 + 4 m, at least 8 m long; target clamped in.
- **Car length** 15.2 m over couplers (manual), set pitch 15.2 m, body 14 m starting 0.6 m behind.
- **Signals/signs**: `route.catenary` (span stations with anchors) and `route.kerbAt(s, side)`
  from the world builder; `game._mount(obj, s, order)` tries 'pole' / 'span' / 'kerb'. Signals:
  pole → kerb → span; signs: span → pole → kerb; speed/gradient signs on a platform move before it.
- **Poles**: retaining walls (surveyed + synthetic cutting walls) stop the anchor search → pole at
  the wall foot; on bridges poles on the parapet (8.4 m); far side > 9 m with near side < 5 m →
  bracket arm. Bílá Hora / Zahradní Město had poles, but 9–14 m away beyond the carriageways.
- **Mosty 3D** (`Mosty_3D_WSL1` SceneServer, same I3S layout as buildings) imported into the same
  `.bld.bin`, chunk field `k` (1 = bridge). `bridgeDecks()` samples bridge triangles under the
  track every 2 m. On OSM-tagged bridges the track follows the deck top (±3 m); in OSM
  covered/tunnel spans any surface at/above the lidar height is a roof (the bare-earth DMR sampled
  the canopy at Nádraží Zahradní Město, as the user suspected); elsewhere only structures > 2.5 m
  above count. The track keeps 5.3 m under them with ≤ 6 % ramps. The synthetic deck is skipped
  where a real model covers > 30 % of a tagged bridge.
- **Building types**: LOD2 has no type (fields: OBJECTID, ID_BUD, AKTUALIZAC, ML, ZMENA,
  KATUZE_KOD). Class from the OSM footprint tag under the centroid + roof flatness + height + area
  (`buildingClass` in world.js). Better source, not yet used: **ČÚZK RÚIAN** `StavebniObjekt`
  (ags.cuzk.gov.cz/arcgis/rest/services/RUIAN/MapServer/3): `zpusobvyuzitikod` (use),
  `druhkonstrukcekod` (load-bearing construction — prefab panels), `pocetpodlazi`, `dokonceni`,
  `pocetbytu`; join by `isknbudovaid` / location. Code lists still to be looked up.
- **Detailed T3** ("Tatra T3" by Jakub Vaja (conflig), Sketchfab, CC BY-NC 4.0; `assets/t3/LICENSE.txt`):
  textures reduced to one 2048 px JPEG with AO baked in (44 MB → 2 MB). Axes are fitted to the
  **8 wheels** (forward = rear→front axle midpoints, left = right→left wheels, origin on the wheel
  bottoms, centred between the wheels); the body PCA was off by 3° roll / 0.7° pitch and yaw.
  Measured after the fix: all wheels at y = 0, ±0.811 m; body level within 7 mm; bogie pivots
  ±3.18 m (the model's own spacing is used by `placeConsist`, the simple model keeps ±3.8 m);
  pantograph stretched up from its base so the head meets the wire (`CONTACT_WIRE` 5.6 m above
  the bed, `RAIL_TOP` 0.26 m); placed on line 22: wheels on the rail heads within 2 mm, head 1 cm
  under the wire, 1.3 cm off the track centre. Pantograph 3.1 m ahead of the car centre →
  `PANTO_FROM_FRONT` 4.5 m for the overhead contacts (simple model moved to match).
  Our route boxes are overlaid on the painted "11". Menu "Tram model" switches to the simple one.
- **Climate** (`game.climate`, `_updateClimate`): per car C = 2 MJ/K, UA 450 W/K, +1200 W/K open
  windows above 21 °C, +2500 W/K doors open; seats 3 / 10 kW, cab heater 2 / 4 kW, flap = 35 % of
  ED-brake power + 50 % of drive power below 9 m/s; 90 W per passenger. All guesses — tune.
  `contactCurrent()` = traction > 500 N or Výhybka button or (heating drawing and no cut-out).
- **Mirror / look**: render-to-texture camera outside the right front, mirrored quad drawn in the
  `#mirror` frame; Q/E (←/→) turn the head ±1.3 rad with a little lean.
- DPP training manual kept at `raw/reference/DPP_ucebnice_T3.pdf` (+ `.txt`), source
  https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_t3.pdf (DPP, January 2009; not
  committed — it is DPP's material).

## 11. From the DPP T3 manual: realistic but arcade-friendly ideas

Ordered by value for effort; each keeps one key / one rule, with assist hints.
1. **Section insulators (úsekové děliče)**: marked on the wire; pass coasting (sparks + small
   penalty under power), never stop under one (the manual has a procedure to roll off by gravity).
2. **Economy driving**: the manual stresses coasting and avoiding needless power steps and quick
   power→brake changes (ED brake drop-out, early drum brake). Score energy (we have `tram.electric`)
   and show a coasting bonus at the end.
3. **ED brake fade below 5–3 km/h**: the drum brake takes over; a "park the brake pedal" step at
   stops (released brake on a hill = rolling, already modelled) — one key, P-state lamp.
4. **Day/night lights** (needed with the day/night cycle): switch "day" (dipped) / "night" (marker
   + tail lights + front destination sign), headlights on a separate lever, saloon fluorescent
   lights switched on **each car separately** (T3SUCS) — passengers dislike a dark saloon; at
   termini turn the tubes over (fun detail, optional). Cab light only in "night".
5. **Two-car set procedures**: control switch off on the second car, heating and lights of the set
   from the first car only (T3R.P) — could be a start-of-shift checklist (3–4 keys, skippable).
6. **Start-of-shift / depot run-out**: control switch to 2, direction key, close doors, release the
   brake pedal — a short checklist mode before the first stop.
7. **Emergency button vs pedal**: track brake in two stages (rear bogie, then both), red emergency
   button = drum + track brake + bell; we have one emergency notch — could split.
8. **Reversing from the rear control box** (zpětný pohyb) for turning at a wye or after a missed
   switch instead of the crowbar penalty.
9. **Sanders**: mechanical lever, heated sand boxes; sand runs out (modelled) — refill at termini.
10. **T3R.P variant** (later Prague cars): 7 power/brake steps, anti-slip, regenerative braking that
    must be cut with "Výhybka 0" over contacts — a second tram type for variety.

## 9. User context

Prague-based, knows DPP/Prague trams in detail (signals, IRC, stop posts, Letenská gauntlet) and
supplies reference photos and sources. Prefers realism grounded in real data, Czech-specific detail,
and a fully localized cs/en UI. Asked to keep the game playable while it grows (autopilot "watch the
ride" mode).

## 10. Whole network, on-demand loading, compression (investigation 2026-10-21)

**Prague network in OSM** (Overpass, bbox 49.94–50.18 N, 14.22–14.71 E): 2 625 `railway=tram` ways,
**310 km of main track** (about 155 km of double-track route) + 41 km depot/yard + 2 km sidings;
77 `route=tram` relations (lines 1–26, 31, 41, 42, 91–99). The network touches **651 tiles of 250 m**
(41 km²; 99 km² with a one-tile margin), within an 18 x 15 km box.

**Current per-line data** (raw / gzip -9): line 22 = 3.6 MB / 1.4 MB JSON + 4.5 MB / 1.2 MB buildings;
all four lines 26.2 MB / 8.6 MB. Inside the JSON the terrain grid is the biggest part (line 22: 2.0 MB
of 3.6 MB) because it covers the route's whole bounding box (1449 x 520 cells at 10 m) as base64.

**Compression tests (line 22)**:
- Terrain: base64 + gzip 998 KB; raw Int16 + gzip 837 KB; **2D predictor (a + b − c) + gzip 548 KB**
  (xz 453 KB). Cropping to the ~1 km band that is actually rendered roughly halves it again.
- LOD2 buildings: 256 k triangles stored as an unindexed soup (769 k vertices, only 141 k unique).
  Soup + gzip 1212 KB; indexed + delta + gzip 1044 KB (xz 822 KB). A real mesh codec (meshoptimizer
  vertex/index codec, roughly 4–6 B per triangle, small JS decoder) should reach about 0.4–0.6 MB.
- Rest of the JSON (roads, OSM buildings, green, tracks, timetable): 1.6 MB, 433 KB gzip. Integer
  delta-coded arrays would roughly halve that; gzip/brotli on the server alone gives about 3x.

**Whole-network estimate**: at line 22 density (about 0.3 MB gzip per km² of buildings, 0.1 MB per km²
of vector data, terrain negligible) the 41 km² track corridor is **about 17 MB gzip (65 MB raw) as
encoded today, 8–10 MB with the encodings above**, and only a small part is needed at any moment.

**Feasible design** (not implemented):
1. `tools/build_network.py`: one Overpass / Geoportál / ČÚZK pass for the whole city (cached in `raw/`),
   output **250 m (or 500 m) tiles** `tiles/x_y.{json,bin}` with roads, footprints, green, tracks, LOD2
   (meshopt), trees, walls and a terrain patch; plus a small **network graph** (track chains, switches,
   signals, crossings) and per-line files (route as a chain of graph edges, stops, GTFS timetable,
   precomputed vertical profile) of about 100–200 KB each.
2. Client: keep the tiles within ~1 km of the camera (fog is at 950 m), about 30–50 tiles or 1–1.5 MB;
   at 50 km/h a 250 m tile boundary is crossed every ~18 s, so streaming is light on bandwidth.
   `ChunkedGeometry` already builds per-cell meshes; world building becomes per tile + dispose.
3. Any line (and diversions) can then be driven, and **AI trams can run real trips** (GTFS
   `stop_times` + shapes mapped onto the graph) and take their own branches at switches.

**Do AI trams follow the correct lines?** Before 2026-10-21: no. Each got a random number from all
lines serving any stop on the route and drove only along our route. Now the number comes from the stop
where it appears, and it fades out after the last stop it shares with us, but it still never leaves our
track physically and does not follow a timetable (needs item 3 above).

## 13. Prague DTM pilot (2026-10-22): line 22 in Praha 2 and Praha 10

**Where the data is.** geoportalpraha.cz → Data a služby → "DTM kraje - ZPS Sada 2" (areas,
`*_ZPS_OPL.gpkg`) and "ZPS Sada 3" (lines and points with Z, `*_ZPS_KR.gpkg`), per city district,
monthly, **CC BY 4.0** ("data base © IPR Praha"). Download links are on the "ke stažení" page of each
data set (`isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/<uuid>/VS_CZ010_MOMC_<code>_<date>_ZPS_OPL.gpkg.zip`;
the uuids change monthly). District codes: Praha 1 500054, 2 500089, 3 500097, 4 500119, 5 500143,
6 500178, 7 500186, 8 500208, 9 500216, 10 500224, 11 547034, 12 547107 (Modřany), 13 539694.
Sizes: Praha 2 OPL 2.4 MB / KR 5.3 MB zipped; Praha 10 7.3 / 16.6 MB.
**Not open:** "DI Sada 7" (transport infrastructure, incl. tram track axes) is marked *Neotevřená
data* — the handoff's plan to snap tracks to DTM axes does not work with open data; tracks stay OSM.

**What is in ZPS.** Areas (2D polygons): carriageway (*Provozní plocha pozemní komunikace*),
sidewalk, cycle path, parking, traffic island, **tram track area** (only where the track has its own
bed, not where it is embedded in the street), platforms, bridge deck (*Plocha mostní konstrukce*),
tunnel/underpass surfaces, railway area, greenery, steps, walls, canopies (*Zastřešení*), buildings.
Lines with **Z on every vertex** (boundaries of traffic areas = kerb lines, inner divisions of traffic
areas, terrain edges, walls, buildings …). Attribute `UrovenUmisteniObjektuZPS` = level: 0 ground,
1 on a structure (bridge decks, railway and roads on bridges), −2 metro. Accuracy classes for
position and height. Polygon vertices coincide with the 3D line vertices (97 % exact matches).

**Pipeline (`tools/dtm.py`, `tools/gpkg.py`).** Own GeoPackage/WKB reader (no GDAL); pyproj for
S-JTSK (EPSG:5514) → WGS84 → our local metres. Keeps areas with a vertex within the route corridor
(40 m grid ±80 m), heights per vertex from the 3D lines; drops areas with > 30 % unknown heights
(they became flat sheets at a wrong level, e.g. 250.6 m over a 235 m street). Exports a **height
cloud**: ground-level traffic/surface lines densified to 3 m (53 k points on line 22), because a wide
carriageway polygon has heights only on its outline and its triangles span tens of metres across
hills. Line 22: 4 k areas, 5.4 MB JSON.

**In the game (`DtmSurface` in terrain.js).** Ground height = IDW of the cloud within 5 m where a
DTM area covers the point; overlapping areas → nearest to lidar. The **track profile** uses it
(7.6 km of line 22), a level-1 deck over the route wins unless OSM marks the track covered/tunnel
(then the tram runs under it — Nádraží Zahradní Město: track at 234.3 m, railway bridge slabs at
240–243 m, lidar had sampled the station's roof at 240 m). Rendering: areas triangulated, street
surfaces split by longest-edge bisection to ≤ 5 m with cloud heights (quadtree splitting crashed the
page), kerb faces on sidewalks/islands/platforms, level-1 areas as 1 m slabs (canopies 0.3 m),
carriageway/tram areas flush with the track bed within 3 m of a track (blend to 6 m), OSM road
ribbons dropped where DTM covers, terrain pushed 0.25 m below DTM surfaces.
Cost: 1.9 M triangles and ~600 MB JS heap for line 22 with two districts — fine on a desktop, too
much for the whole network: next step is chunking/LOD (only street surfaces near the track at full
resolution, merge greenery) or baking meshes offline.

**Findings / caveats.** OSM route vs DTM: consistent (embedded track lies in carriageway areas).
Profile vs DTM within 0.4 m for 92 % of samples; the rest are bridges the two districts' data does
not contain (Francouzská over the railway cutting, 12800–12850: no level-1 deck in Praha 2/10, kept
the grade-limited profile). Retaining walls and building faces in DTM are not used yet (walls come
from Geoportál). Modřany (Praha 12, code 547107) not imported yet.

**Cars (same session).** OSM roads are now split at every shared node, so the network has real
junctions; the street the tram runs in stays in the network (it used to be lanes only, so cars from
side streets vanished at the junction); at the data edge cars roll on while fading; junction
give-way (nearest car first, ties by id). Line 22 stops 20–30: vanishing at junctions 40 % → 14 % of
road ends, of which 24/403 within 40 m of the track.

## 14. Street bot and DTM street fixes (2026-10-22, later)

User report: height discontinuities, cars on sidewalks, rough footways in the DTM areas.
`src/streetbot.js` (`?bot`) drives/walks the whole traffic network inside the DTM coverage and
reports places (see README → Dev). Line 22, 69 km of car lanes + 117 km of footways. Samples before → after:

| finding | before | after | cause / fix |
|---|---|---|---|
| wheels on sidewalk | 12 012 | 2 338 | cars on the OSM centre line + guessed width → lanes fitted to the DTM kerb lines (`Traffic._fitRoad`, `laneOffset`; a track bed in the middle joins both halves); lanes beside the tram shifted into the carriageway (`_fitLat`). Road objects never carried `tram`, so tram streets used the wrong lane rule |
| walker above/below drawn | 2 001 / 3 194 | 19 / 2 129 | one height for what is drawn: `ground.surface(x, y)` (DTM area + class lift, else ribbon + 0.12) used by cars (`carPose`) and walkers; height lookup indexes the drawn split triangles; the track flush is baked into the DTM vertices once (`flushDtm`) |
| car sunk / floating | 4 628 / 1 575 | 1 822 / 299 | same; terrain lowered exactly under every drawn DTM vertex (was only at its 10 m grid points), max 4 m |
| height jumps / tilt | 918 / 4 826 | 659 / 4 314 | importer: ground-level areas only take heights from ground-level lines, corners > 5 m under the lidar ground are dropped (an underground floor under Náměstí Míru was tagged level 0), lines of all districts are indexed before matching (areas across the Praha 2/10 border had no heights on the far side and were filled with a constant 8 m too low), missing heights interpolated along the ring; height cloud filtered by level, only for road/tram/parking (sidewalks are planar between their exact corners) |

**Still listed** (top of the bot list): the cutting of Průběžná down to Nádraží Zahradní Město (block
retaining walls along the ramp, user photos 2026-10-22: road and tracks drop between walls, island stop
with railings under the railway bridge, platform canopies above) — the DTM wall areas are not drawn, so
car paths cross from the street above to the ramp; junction squares where the fitted lane falls back to
OSM; footway kerb crossings (walk-kerb: no lowered kerbs at crossings); gaps between DTM areas (classes
not imported). Tilt counts every roll > 7°, half of them < 10° (camber, kerb-side wheels).
Heap +220 MB for the triangle index (1.65 → 1.87 GB measured the same way during a run).

## 15. Street model pilot (2026-10-22): line 22, Karlovo náměstí – Jana Masaryka (s 10850–12900)

Idea from BeamNG.Earth (`grading.py`, `sidewalks.py`): streets built from a few smooth rules instead of
draping every survey polygon on its own noisy corners. `tools/streets.py` (offline, numpy + shapely
2.1+ `constrained_delaunay_triangles`, no scipy):
- **Z0 carriageway surface**: normalized Gaussian convolution (σ 3 m, wider where sparse) of the road /
  parking / tram-bed corners and the cloud points inside the carriageways (0.2 m in from kerbs), 2 m
  grid, 3 passes rejecting > 0.25 m outliers (rms 5.5 cm).
- **R raised surface**: the same fit over sidewalk / island / cycle / paving corners (keeps the real
  crossfall towards facades), at least 6 cm above Z0; areas off it by > 0.25 m (terraces, steps) keep
  their survey and leave the fit. Paving/cycle at road level count as carriageway. Platforms: Z0 + one
  constant step.
- **Mesh**: 8 m grid cells (4 m within 7 m of a track), clipped to the (5 cm-simplified) polygon,
  edges split at 4 m so neighbours share vertices, constrained Delaunay per piece. Kerb faces flagged
  only on edges within 0.4 m of the carriageway (`k`). Areas carry `v`, `t`, `k`, `s` (+ `r0`/`h0`
  survey copy so reruns start fresh).
- **In the game** (`DtmSurface`: areas with `v`/`t` use the ready mesh; `world.js flushDtm`): model
  areas are laid to the track profile by a correction measured along (2 m) and across (1 m) the route
  on the unshifted model, full within 5 m of the route, fading out by 15 m, same for road and
  sidewalk (kerbs keep their height). Profile vs Z0 differed up to 0.85 m (grade-limited profile).
  Track heights are now computed after this, and other lines' tracks embedded in a surveyed
  carriageway sit 0.14 lower so their bed is flush with the road (it was a 17 cm raised strip).

**Result** (pilot stretch, same code and bot, survey-draped → model): triangles 187 519 → 93 830 (the
400 snapped areas take 46 k; the rest is greenery, steps and the 106 areas kept on survey);
car kerb steps 296 → 125, tilts 722 → 269, floating 72 → 23, sunk 131 → 82, jumps 79 → 67;
walkers: steps 253 → 245, bumpy 200 → 186 (walk paths cross gaps between areas and kept areas);
kerb crossings 39 → 97 (kerbs are now consistent — crossings need dropped kerbs). Cars on sidewalks
260 unchanged (lane paths at junction corners, not surfaces). Autopilot 18 → end clean.
Bot fixes in the same step: steps measured against the local slope (steep streets are not steps),
walker kerb crossings listed apart (`crossing`).

**Vienna-type stops** (user, 2026-10-22: no island, boarding from the sidewalk across the car lane,
cars must wait behind the stopped tram; only a few in the city). `streets.py` checks what lies 2.2–3.4 m
right of the track along each platform: Štěpánská and Jana Masaryka come out "mixed" (a third
carriageway) → stored as `dtm.vienna`. **Wrong**: the user confirms both have normal islands; the
real Vienna-type stops are Čechův most towards Kobylisy, Krymská both directions and Újezd from
Národní třída. A better classifier (lateral survey profile) is planned in PLAN.md §3.8; `dtm.vienna`
is not used by the game.

**Next**: dropped kerbs at crossings (OSM crossing nodes / zebras), draw DTM retaining walls where
level-0 areas meet with a step (Zahradní Město ramp), greenery as terrain colour away from streets,
then the rest of line 22 (Praha 10) and a 1 m height/class raster per tile instead of the triangle index.

## 12. Open items from the user (2026-10-21, end of session) — not done yet (merged into PLAN.md)

1. **Two-car set "broken"** — the user saw it on a screenshot that did not reach me. In my views
   both cars were coupled correctly (centres 15.2 m apart, ~1.5 m between bodies, same track).
   Ask for the screenshot / place; check AI two-car trams and the simple model too.
2. **Nádraží Zahradní Město** looks wrong. Facts (cs Wikipedia "Praha-Zahradní Město (nádraží)",
   PID 24 Sep 2021): the railway station is mostly a **bridge over Průběžná** (3 platforms × 350 m,
   5 tracks); the **tram and bus stops are in the widened and lowered underpass directly under the
   train platforms**; stairs, escalators and lifts lead up; pedestrian underpasses on both sides.
   OSM marks our track covered at 18066–18109 and 18165–18196; Mosty 3D has the bridge slabs.
   To do: carve the underpass to the real road width (not the ±7 m bench with synthetic walls),
   render the railway on top (OSM `railway=rail` on the bridge, platforms `railway=platform`,
   canopies `building=roof` — currently filtered out of buildings), maybe a passing train.
   Photos: Commons files `Praha-Zahradní_Město_train_station_II,_Praha.jpg`,
   `Praha-Zahradní_Město_train_station,_Praha.jpg`, `Praha_Strasnice_ZST_Zahradni_Mesto_mural_18.jpg`.
3. **Both directions and line variants**: a line should be drivable in both directions and in
   its variants (22: Bílá Hora / Vypich → Zahradní Město / Nádraží Hostivař and back), chosen in
   the menu. Proposed: one data file per line with the union corridor (scenery) and a list of
   routes (GTFS patterns map-matched like `--then`, each with path, stops, platforms, timetable,
   signals, switches); the menu picks a route and reloads with `?line=22&route=k` (the world
   carve/profile depend on the route). Also show **stops on both sides** (posts, platforms,
   waiting people for the opposite direction, from the reverse route's stops) and let oncoming
   NPC trams stop at the real opposite stops.
4. **Final stop Zahradní Město and the turning loop**: the user had an accident there once.
   Autopilot runs finish cleanly at the last stop; the route ends at the stop (the loop after it
   is not part of the GTFS shape). Check manual driving past the final stop (route end clamps,
   AI tram fading at the terminus) and consider adding the loop to the path.
5. **Route boxes** now sit exactly on the painted ones (found via texture coordinates, see
   `paintedBoxes` in models.js; glTF v runs downwards, u can be offset by 1). Rear box mirrored.
6. **Signals/signs** (this session): at the kerb when within 6.5 m of our track, else hung from
   the nearest span (±16 m), never on facades or platforms (`Game._mount`).
7. Model licence: done — "Tatra T3" by Jakub Vaja (conflig), Sketchfab, CC BY-NC 4.0.
8. Deploy: `dist/tatra-t3-prague.zip` (static files only; see README "Deploy").

## 16. Lint-driven work (2026-10-22, afternoon and evening)

All measured with the lints; numbers are line 9 / 17 / 22 / 23 unless noted; details in PLAN.md §3/§4.

**Fixed**
- **Two-car set at a terminus** (Sídliště Řepy): the route started at the stop, so the second car was
  clamped into the first. Routes now run 60 m past both ends along the OSM tracks
  (`extendAlongTracks`, negative s before the start). Probably also the old "dual-car set broken".
- **Invented walls**: the corridor carve built retaining walls where the 10 m lidar grid rises beside
  the track — 1 272 m of them on line 22's surveyed sidewalks. No synthetic wall where the DTM covers.
- **Vegetation**: the tree register has categories (`kod_vp`: 71 tree, 51 bush, 21 plants in
  containers, 101 climbers; no sizes). Bushes are drawn as shrubs, planters as pots, climbers dropped,
  tree-row samples off carriageways and buildings, crowns shrink to clear facades: trunks/crowns in
  buildings 612/215/390/73 → 0. `geoportal.py --trees-only` re-imports just the vegetation.
- **Signals and signs**: never along a platform (moved to the platform head or hung from a span or
  bracket arm); hung ones sit outside the tram's swept envelope (`tramClearance`: body + 19.5/R curve
  overhang + margin): line 9 115/239 inside → 0.
- **Speeds**: the step table became √(a·R) with a = 0.8 m/s², capped by the OSM `maxspeed` of the
  tram way (what OpenRailwayMap shows; on 29–97 % of each route) and 50 km/h in streets / 60 on
  dedicated track (65–70 km/h OSM pilots capped for now; user GPS recordings to come).
- **Banked curves**: on dedicated track (no road along it) up to 100 mm cant, ramping linearly
  (100 mm per 30 m) and smoothed; level at platforms (±25 m) and within 150 m of the route ends. The
  outer rail is raised, trams and the cab lean in (max 0.13°/m).
- **Autopilot**: heating with hysteresis and ≥ 20 s between changes (34 088 → 9 knob changes in 31 min
  on line 23); smoothed cab pitch (no jump at a dead stop); parked cars drive off forwards.
- **Cab**: mirror inside the window frame, its camera on a realistic arm (0.3 m outside the body);
  menu options: automatic switches (onboard computer), performance overlay.
- **Bridges** (Čechův most): poles stood on the river bed (they sampled the ground without the deck
  flag); the deck pick took a second slab 3.7 m above the deck at the north end, the track dipped
  through the drawn deck — now the track ramps at most 6 % from a span's ends, and no part of a bridge
  model is drawn inside the tram's swept space.
- **Grade separation**: a junction well inside a bridge span (> 8 m from its ends) belongs to the road
  below: no signal, jaywalkers or "wait for the tram" there (line 17: three junctions under the
  Modřany estakáda).
- **Lane graph** (`Traffic._buildLanes`): one smooth lane per road and direction at the kerb-fitted
  position, Hermite connectors through junctions, cars follow their path's tangent, slow for curves,
  scan 40 m ahead for trams, walkers and cars, give way at junctions. Slides 6 839/5 243/8 671/3 513 →
  ~300–800 (mostly walkers now), car jumps → 0, street-bot sidewalk samples on line 22 4 645 → 2 008.
- **Junction controllers** (`Game._runController`): fixed cycle per signal (straight trams both
  ways, turning phase, cross street), tram priority, dilemma-zone hold; oncoming AI trams stop at the
  junction on red.
- **Deadlocks found by traffic runs that did not finish** (each a generic rule now): a car driving
  along the track waited for the tram behind it (the crossing wait is only for cars crossing the
  track); cars entered full junctions (don't block the box); a car in the junction waited for one
  that waited for it; two cars in each other's lane mouth; a car whose own path is blocked kept its
  junction priority; a car beside the front of our tram waited for it (obstacles behind a car are
  ignored); walkers turned back and forth in a lane, or spawned past the end of their path and stood
  in a lane for good; oncoming trams drove into each other at a red light; tram priority jumped to our
  turning phase and starved the opposite direction, which then blocked the Letenská single track.
- **Determinism**: tram electrics used the wall clock (the current decides the contacts); now
  simulation time. The traffic run is seeded, first trip, autumn, dry.

**Open**
- Traffic counts rose with the junction cycles (queues): overlaps 180/91/166/39, walkers inside
  vehicles (episodes) 222/157/112/61, slides 811/449/678/319 (baseline 2026-10-22, `c0acbb8`). Part is
  real, part is that earlier runs jammed early. Next: average several seeds, then look at the causes.
- Oncoming trams through red, counted fairly (could still stop while red): 36/7/14/4.
- Lanes of different roads that touch (line 22: ~45 overlaps); Vienna-type stops need the stop
  classifier (PLAN C13); a car standing on the track blocks a tram until it moves (no overtaking).
- The street model pilot covers only Karlovo nám. – Jana Masaryka on line 22.

## 17. Line 17 on the surveyed streets, two levels at bridges and underpasses (2026-10-22, night)

User request: rebuild line 17 with the detailed DTM, underpass traffic handled and drawn on both
levels, the same for bridges; check walls, embankment, Čechův most junctions and the Modřany corridor.

**Data.** DTM for Praha 1, 4, 7, 8, 12 (Modřany) and Troja downloaded (September 2026 packages;
links from the Geoportál "ke stažení" pages, OPL `225F0FAF-…`, KR `28A24EB4-…`), with Praha 2 already
there: `data/line17.dtm.json`, 9.1 k areas. Coverage: all but 1.3 km of the 21.7 km route (Trojská
18200–18800: the district's road areas there have no surveyed heights, dropped). The importer now
uses only lines of an area's **own level** for every level (it did so only for ground level): the
estakáda's track bed outline had taken the heights of the road below and drew a slab sloping into
the underpass. `streets.py` runs the whole line in 1.5 km chunks (each area modelled once, in the
chunk of its nearest route position; fits reach 40 m beyond): 364 k model triangles, 24.7 MB, 45 s.
JS heap with line 17 loaded: 1.1 GB (raw survey without the model: 1.5 GB).

**Two levels (terrain.js, traffic.js, world.js).**
- Every OSM road and footway has a level (`bridge` → on a deck). `ground.way(line, isBridge)` is the
  one height function of a way: ground level, or on a bridge the surveyed deck nearest the way's
  straight span (`deckSurface`), else our route's deck, else the span between the ends of the whole
  way (pieces used their own ends, mid-bridge: 4 m floating at Zahradní Město). Ribbons are drawn
  with it; cars and walkers stand on it (`road.hf`, connectors blend the two lanes' surfaces).
- Cars now drive on bridge roads (they were excluded); no generated sidewalk paths along bridges
  (nothing drawn there; bridge footways are OSM ways of their own).
- `ground.at()` without the deck flag gives the ground under our bridge (it gave the deck within
  4 m of the track: cars under the Modřany estakáda drove at deck height); `surface()` is ground level only.
- Obstacles, cars on our track, "wait for the tram" and the traffic lint's overlap/walker checks
  ignore anything more than 2.5 m above or below (`LEVEL_APART`).
- `overBridge` (no junction, signal, jaywalkers) needs the deck at least 3 m above the ground under
  it: the 28 m culvert "bridge" at s 5816 with a road 1.2 m below the rails is a normal crossing.
- Lint `bridgeLevels`: lanes under our spans ≥ 2.5 m below the rails, lanes on them at rail level.
  Line 17: Modřany underpasses 4.0–6.7 m, Čechův most lanes at the rails (0/12).

**Bridges in the track profile.**
- The deck under the route counts only on an OSM-tagged bridge, or where the survey has a **level-1
  tram bed** (our track on a structure, also untagged: Nádraží Braník 7312–7470, the Trojský most
  approach); any other structure over the route (road bridge, railway, station) is above the tram.
- Inside a surveyed span the samples without bed are interpolated between bed samples (they had the
  road below: Černý kůň 198.9 m deck / 192.2 m road → 195.5 m after the grade limit, the tram ran
  through its own bridge with 3.2 m above the road); the surveyed deck is a floor after smoothing,
  falling at 6 % away from it; beyond a surveyed deck the track meets the ground at ≤ 6 % (north of
  Trojský most the survey stops on the viaduct 9 m above the lidar ground under it).
- The model of one of our own spans reaching past its OSM ends is not an overhead structure (it
  pushed the track 5.3 m under it).
- Every track within 6 m of the route (ours and the opposite one, 4.5 m apart on the Modřany
  corridor) lies on the profile: the opposite track took the raw survey and stood up to 6 m off ours
  at the span ends (rails and wire jumping). Lint `trackLevels` (0/29 825 on line 17).
- Profile vs surveyed decks now within 0.1–0.4 m (Trojský most 193.9 m mid-span, Braník 200.5 m,
  Černý kůň 198.8 m). Steepest grade on line 17: 7.2 % near Trojská (the ramp off the viaduct into
  the survey gap; check with the user's GPS recordings).

**Drawing.**
- Surveyed slabs on structures: triangles split to ≤ 5 m with heights from their own outline nearby
  (long deck outlines made long triangles); the decks of our bridges are laid to the profile like the
  streets; a structure over the track keeps its underside 5 m above the rails (thinner slab; only
  what is lower inside the tram's space is cut, as for the bridge models).
- Surveyed walls are drawn (a quay wall's area runs from its foot line to its top: a battered face);
  water areas are level (the river outline had the heights of both embankments' tops); **step faces**
  wherever the surface just outside a ground-level area's edge is more than 0.5 m lower (outside
  surface extrapolated to the edge, so a slope is not a step): the embankment shows street, quay wall,
  náplavka, river. Terrain may now be lowered up to 6 m under a surveyed surface (4).
- Street flush to the track profile (`flushDtm`, `ground.flush`) measures only the street at the
  rails' level (Codex found the north end of Čechův most lifting street vertices 5.6 m because the
  embankment road below was measured) and skips the road under our bridges.

**Traffic fixes found by the runs.**
- Two OSM ways in one surveyed carriageway (divided street, slip lane) each took the whole width:
  lanes on top of each other. A parallel way inside the carriageway now splits it halfway
  (`_parallelWays`): line 17 car/car overlaps 210 → 76.
- Gridlocks: any cycle of cars waiting for each other (three in a junction on line 9) lets the lowest
  id go; a car stopped behind a stopped obstacle does not hold its turn at a junction (line 9 s 8679).
- A walker at the end of a footway that ends by the tracks flipped between "end of path" and "tracks
  ahead" every frame, standing in a lane on the track (line 17 s 13756): after turning at an end it
  commits to walking back for 4 s.

**Numbers** (vs the committed baseline; traffic counts per run): see the commit message and
`reports/`. Line 17 all static 0, finished, overlaps 91 → 76, walker hits 157 → 112, slides 449 →
715 (walkers; more walkers on the surveyed paths), street bot 8 181 findings over 389 km of probes
(first run with DTM, no baseline). The runs are not fully deterministic after the street bot (the same
page and code jammed once and finished once on line 22): average seeds before trusting ±20 %.

**Codex second look** (user, same evening, `CODEX_HANDOFF.md`, separate working copy): its findings
used here: the level-referenced street flush, tagged-only deck in the profile (done independently
the same way), explicit surface levels. Not taken yet: analytic cubic lane paths, interior survey
overshoot check in `streets.py`, embankment source-height glitches (a sidewalk vertex at 185.5 m
between 191.5 m neighbours near (-264.8, 3234.1)), terrain refinement at survey edges, rendered-
surface lints. Its city/chunk architecture: PLAN.md §7.

**Open:** walker slides (most of the slide count); Trojská survey gap; OSM road tunnels and `layer`
still dropped by `build_line.py`; DTM level −1 floors (Výtoň) not drawn as their own surface; line
23 walker hits 61 → 94 (Královka, no bridges involved: probably the changed random sequence, check
with seeds).

## 18. Line 17 look fixes, new lints, platforms of both directions (2026-10-23)

User report: wavy streets and footpaths, jagged walls and terrain beside the tracks, oncoming trams
jumping between Nádraží Braník and Čechova čtvrť, an "obelisk" near Čechova čtvrť, overhead poles too
low (the span under the wire). Asked: measure first (lints), then fix; full-size stops of both
directions from the data, curved; platform names from GTFS.

**Causes and fixes**
- **Oncoming trams jumping (up to 3.4 m):** their height came from `ground.at()`, which returns the
  profile only within 4 m of our track; on the Modřany corridor the opposite track is 4.2-4.8 m away.
  `ground.trackAt(x, y)` (profile within 6 m, else ground/deck) is now used by the drawn tracks, the
  oncoming trams and the opposite signal: within 0.15 m.
- **Obelisk:** a survey typo, 298.9 m for 198.9 m, beside the estakáda (and a group of streets ~75 m too
  high on lines 17 and 22). `dtm.py` drops ground-level corners and cloud points more than 8 m above
  the lidar ground (it only had the "5 m below" test).
- **Wavy streets:** the street model's carriageway fit (σ 3 m) followed the survey's noise (tram-bed
  corners, inner division lines). σ 6 m and outlier rejection 0.15 m (`--sigma`, `--reject`); each
  model area stays within 0.6 m of its own survey (`--bound`: stops a neighbouring street at another
  height dragging it; tighter brings the noise back); the flush correction to the track profile is a
  smoothed field (±10 m along, ±2 m across). Line 17 street bumps > 8 cm: road 5528 → 2832 (6.4 %),
  sidewalk 3448 → 1618, tram bed 1384 → 487; street bot 8181 → ~7200.
- **Track corridor:** within 3 m of our tracks a surveyed carriageway or tram bed is laid to the bed,
  whatever the survey says (a 2 m bump at s 2420 stood 3.6 m over the rails); the "another level"
  guard applies beyond 3 m and to structures more than 4.5 m above.
- **Vertical curves:** surveyed deck floors fall along a 500 m vertical curve into the 6 % ramp, and a
  final pass eases any crest or sag under 500 m (line 17: 27 places, min 173 m → 1, the sag under the
  Holešovice railway bridge, 242-304 m, held by the clearance rule). Grades of 8-8.8 % between
  Trojská and Kobylisy are real (lint flags over 9 %).
- **Catenary:** the span hung 0.4 m under the top of each 7.4 m pole wherever the pole stood; poles on
  a lower street held the contact wire from below (164 of 692 spans on line 17, up to 6 m). Spans now
  hang 7.0 m over the rails (1 m over the wire, both ends level), poles reach up from their foot.
- **Structure under the tracks** (`buildTrackSupport`): where the bed stands > 0.6 m over the drawn
  ground beside it, walls down to the ground and a top between the tracks; on our bridges a 0.8 m deck
  where nothing is close below (approach ramps whose survey or model stops short).
- **Lawns** (survey green: heights only on the outline) follow the lidar ground inside (10 m triangles):
  terrain through the survey 192 → 55 samples (8.7 m under the Letná slope before).

**New lints** (`tools/lint.js`): `streetWaviness` (street classes only), `terrainOverSurvey`,
`railSupport` (a ray down from above the bed: covered / gap / deck below), `verticalCurves` (radius
< 500 m, grade > 9 %), `catenary` (spans over the wire, level). Line 17 after: catenary 0/692,
vertical curves 1, rail support 88/10 850 (estakáda first span, Výtoň underpass floor, a few short
spots), terrain over survey 55.

**Platforms of both directions** (`tools/platforms.py`, game `_buildPlatforms`): every PID tram
platform within 10 m of either path from GTFS (exact position, name, platform code, lines; tram routes
from `routes.txt` + `route_stops.txt`), matched to the OSM platform it stands on for the shape (OSM
lines usually along the middle, areas give the outer edge); GTFS platforms without OSM get 32 m back
from the stop position. Built as strips curved along their track (ours or the opposite one), 1.5 m
from the track centre to the width, 0.44 m above the rail foot; skipped where the survey draws a
platform, island or sidewalk there. Opposite direction: stop sign at the GTFS position with its lines,
shelter where OSM has one; our stops keep the 30 m box only without an OSM platform (35/37 on line 17
have one). Line 9: 93 platforms, 80 from GTFS only (its OSM cache has none; the Overpass polyline
query came back empty).

**Line 22** re-imported with the outlier filter and modelled whole (it had only the pilot stretch).

**Numbers after** (baselines accepted 2026-10-23; all four lines finish): new lints — line 17: waviness
5627/71 327 street samples, terrain over survey 56, rail support 85/10 850, vertical curves 1, catenary
0/692; line 22: 1395/27 849, 0, 25/9184, 1, 0/607; lines 9 and 23 (no survey): rail support 28 and 11,
vertical curves 0, catenary 0. Traffic within the noise band except line 9 walker hits 146 → 246 (222
the run before last; nothing in traffic changed) and line 17 overlaps 76 → 100. Line 22 jammed once in
three runs (stop 31, 4000 s lost; the rerun finished clean): a car stood on our track facing our tram at
Kubánské náměstí, probably a lane laid onto the track by the carriageway split. Open, intermittent.

**Inspect mode** (same day, user request: faster visual checks than an autopilot ride, with a mouse
camera): `src/inspect.js`, `?inspect` or the I key. The autopilot drives; time 1/4×-32× (game steps of
at most 1/30 s, several per frame), pause; orbit and fly cameras; camera jumps to the next/previous
stop; a panel with the camera's route position. main.js runs `inspect.steps(dt)` game steps per frame.

## 19. Plane-fitted streets, track spacing, tunnels (2026-10-23, afternoon)

User findings on line 17: footpaths fine now, nearby terrain jagged; roads still wavy (downhill from
Levského: arching between points); lanes: two lanes, driving on tracks, sharp turns on straight roads;
the Vyšehrad tunnel cut open; OSM sometimes draws the two tracks too close; Letenský tunel for cars.

- **Streets** (`tools/streets.py`): the carriageway / raised fits are now first-order normalized
  convolutions: at every grid cell the plane z = a + b dx + c dy fitted to the points around (Gaussian
  weights, slope prior), not their weighted mean (which bends between unevenly spread points on a slope:
  the arching). Convolutions by FFT (whole line 17: 2 min 44 s). Line 17 street bumps 5627 → 5006,
  street bot 7875 → 7596; line 22 1395 → 1152, 3362 → 3124.
- **Track spacing** (`src/trackfix.js`, lint `trackSpacing`): where the opposite track runs alongside
  ours the other way (≥ 40 m from switches), its axis is pushed out to 3.0 m (blended over ±20 m; the
  back route and the drawn tracks densified to 4 m and moved together; our route stays). Interlaced
  track (< 1.8 m, Letenská 0.7 m) and 40 m around it are left alone. OSM had 1.92 m on line 17, 2.45 m
  on line 9, 2.55 m on line 22; the lint is 0 on all lines. Dev switch `?nospread`.
- **Road tunnels** (Letenský, Bubenečský, nábřeží E. Beneše, Vyšehradský …): `build_line.py` keeps OSM
  `tunnel=yes` roads flagged `t` (older data patched by `tools/tunnel_roads.py`); cars run on a straight
  span between the portals (`ground.way(…, isTunnel)`), no ribbon underground, no generated sidewalks,
  a portal frame with a dark opening at each tunnel end. Dev switch `?notunnels`.
- **Vyšehrad tunnel** (our route through rock: OSM tunnel and the lidar ground > 8 m over the track):
  no corridor carve there, the terrain keeps the hill, a hole in the terrain mesh along the tunnel,
  a vault (walls 4.8 m, arch to 7.2 m, ±8.5 m), the rock top at the lidar height and portal faces;
  the road through it is drawn inside.
- **Data checked** (Geoportál catalogue): no open road markings or lanes (ZPS has no markings; "DI"
  is not open), no 3D tunnel model (Mosty 3D only). Useful and unused: "Model terénu 3D" (IPR lidar
  bare earth, ~40 points/m², elevation image service in LERC tiles, cm pixels) for the fine terrain;
  ZPS lines "Terénní hrana" (terrain edges), "Hranice zdi" (walls with heights), "Zábradlí" (railings),
  "Svodidlo", "Provozní plocha tunelu".
- **Traffic counts**: they swing ±20-30 % whenever trajectories change (line 22 overlaps 149 / 158 /
  180 for spread on / both off / tunnels on); the tunnel roads add ~30 overlaps on line 22 (cars at the
  portals). Baselines accepted; averaging seeds is next (PLAN §1).
- **Open**: line 23 has a 0.7 m close spot near Malostranská shorter than a gauntlet (no block
  control: two trams met there once); lanes (two lanes where one, cars on the tracks, sharp kinks) need
  OSM lanes/turn:lanes and the fitted kerb smoothing (no open lane data).

## 20. Wider world, lanes from basic data, Vyšehrad tunnel to the survey (2026-10-23, afternoon)

User decisions: one lane per direction unless OSM tags more; turn lanes and the orthophoto check
later; smoother kerb fits; walkers only on sidewalks; four pilot areas (Podolské nábřeží, Strossmayerovo
- Veletržní, Trojská, Palackého nám.); the newer source wins (the survey of Sept 2026 over OSM).

- **World width** (line 17 rebuilt from the cached route): OSM roads 90 → 200 m, buildings (OSM and
  Geoportál LOD2, trees) 110 → 220 m, green 120 → 240 m; the street survey stays at 80 m (memory),
  traffic everywhere. Roads 3948 → 6327, LOD2 buildings 2903 → 6064 (6.3 MB), JS heap 1.39 GB.
  (Overpass timed out on the 220 m OSM buildings query: the old cache is kept, LOD2 is drawn anyway.)
- **Lanes** (`traffic.js lanesOf`, `laneOffset`, `_trackLats`): lanes per direction from OSM `lanes:forward`
  / `lanes:backward`, `lanes` on one-way roads, half of `lanes` from 4, else one (891 of 1454 car ways
  are tagged; `build_line.py` exports `ln`, `lf`, `lb`). The carriageway is the survey's road areas
  (parking strips at the edges and tram areas at the side excluded); the divider between directions is
  the line between both tracks where they lie in the carriageway, else the middle; a lane sits 1.7 m in
  from its right kerb, never past the divider, and where the band is narrower than 3.2 m on the track of
  its own direction (the Vyšehrad tunnel). Kerb fits smoothed over ±20 m and moving at most 0.4 m per
  4 m. Road tunnels are fitted to the underground survey (`DtmSurface.classUnder`).
- **Walkers**: generated sidewalks only on the surveyed sidewalk / paving found within 8 m out from the
  kerb (1 m into it); OSM footways cut where they lie on the carriageway for more than 6 m.
- **Vyšehrad tunnel**: walls where the surveyed tunnel floor ends (1.5 m right of our track to 8 m left),
  a semicircle springing at 2.5 m (user photo), the floor drawn from the underground survey.
- **Lint `lanes`** (line 17, per sample): 3.5 % → 1.5 % (kinks 360 → 10, walkers on roads 965 → 46,
  tram bed 189 → 57, platforms 290 → 169, doubled 450 → 302; off carriageway ~1 % unchanged, 40 % of it
  on the new outer roads). Traffic: overlaps 71 → 51, walker hits 135 → 50.
- **Troja bridgehead** (s ~18 150, orthophoto): the cross road passes under the tram corridor, mapped in
  OSM as a tunnel: its cars now run below ground between portals (no survey there).
- Platform strips from OSM lines capped at 3.5 m (one reached over the car lane at Trojská).

## 21. Consolidated state (2026-10-23, evening)

PLAN.md §1 is now the single current picture: state, today's changes, proposals waiting for the user,
the user's inspection observations grouped (A bridges/tunnels, B streets/terrain, C stops, D traffic)
and one priority list. New facts are in `data/truth.json` (Ke Stírce Vienna-type, Sídliště Řepy
multi-platform, Vyšehrad tunnel shared tracks, Veletržní cars on the tracks, Troja underpass, Pobřežní
cesta and Výstaviště structures, Karlovy lázně passage, Letenský tunel, two rules). Lines 9, 22, 23 have
not been re-run since the lane rules changed.

## 22. User answers to the open proposals; Letenská gauntlet; Mosty registration (2026-10-23, night)

Decisions (PLAN §1.3): fine terrain yes if cheap enough (simplify from the precise data); the shared
city world after the current issues, traffic tuning and signals; seed averaging yes; line 23 close spot
first; OSM fetched slowly in small pieces, in the background and ahead of planned coverage; the track
(and roads) fit the bridge deck models, approaches and ramps adjusted, coordinates double-checked.

- **Line 23 "close spot" = the Letenská interlaced track, not built as a gauntlet.** OSM tags it right
  (`railway:interlaced=yes`, note "kolejová splítka", part under a `building_passage`, ~73 m between
  lon 14.40521 and 14.40623). `Route.nearest()` returned the nearest 4 m sample, up to 2 m off the true
  distance, so two tracks 0.3-0.45 m apart read 0.4-1.9 m and the stretch fell apart into 3 m pieces,
  each under the 25 m minimum: no gauntlet, no block control (the two trams that met there). Fixed at
  the rule: `nearest()` refines the sample onto the chords to its neighbours and `distance()` uses it
  (37 callers get exact distances). Line 23 now has the gauntlet s 3978-4056. The two short close
  spots at s 311-318 and 811-820 are where the two directions' tracks cross (skipped, < 25 m).
- **Traffic lint averages 3 seeds** (22, 7, 1234; `lint({ seeds })`, each run's count in `runs`). The
  same seed gives the same run, except the first run after a shift was played. Line 23 (first run since
  the lane rules, D3): slide 357 → 237, overlap 55 → 28, red runs 2 → 1, walker hits 62 → 90 (78 / 82 /
  109): cars now in walkers' crossings at Malovanka - Pohořelec (follow-up in D3).
- **Overpass**: `tools/overpass.py`: queries cached by text in raw/overpass/, 5 s between requests,
  retries with backoff over three servers. `platforms.py --fetch` asks in ~800 m boxes along both
  directions (the one-query fetch came back empty for line 9).
- **Mosty 3D vs the survey** (line 17, every 150 m of route where both have a deck): Web Mercator →
  local and the heights agree: no systematic horizontal shift (the best of ±4 m shifts scatters in
  direction and gains a few edge points), and the model top is 0.0-0.5 m over the surveyed deck on most
  bridges (Bpv on both; an ellipsoid mix-up would be ~45 m). Local outliers to fit in A2: s 4200 +4.7 m
  (the estakáda), 4950 +5.8, 5700 +6.7, 11700 +7.9, 12600 +1.2, 13350 +1.4 (other structure parts or
  levels over the surveyed areas). Script: scratch `mosty_check.py` (to become a lint with A2).

## 23. Priority 1 and A2: tunnels, bridge ways, Vienna stops, cars and a standing tram, decks (2026-10-23, night)

Rules, not spots (each measured on line 17; the lints in brackets):
- **Tunnels and bridges as whole chains** (`chainTunnels` in terrain.js, applied in main.js): OSM splits a
  tunnel or bridge into many ways; each way spanned between its own ends, so inner ends took the hill
  top (Letenský tunel cars came down the hill, A5) or the river (footways on bridge pieces hung at the
  water, A3). Every tunnel / bridge way now carries `way`, the whole chain; heights run along its length.
  A chain end with no ordinary road within 4.5 m runs past the edge of the imported roads (`way.open`):
  a tunnel end there is held 8 m under the terrain, a bridge end takes the other end's height. Portal
  heights come from the approach road (the lowest ground 0-12 m out of the mouth), not the hill face.
- **Bridge ways on the Mosty 3D deck** (`bridgeModel(geo)`: `ground.model.surfaces / topAt / deckAt`):
  a bridge way's height is the surveyed deck near the model's deck, else the model's deck (the lowest
  up-facing surface from 3 m under the span to 15 m over it, above ground + 1.5 m: piers' tops near
  the water and parapets above are skipped), else the span (never under the ground). Bridge points under
  1.5 m over the ground: 79 lifted; over water under 3 m: 71 → 24 (the rest abutments in the river
  polygon).
- **Road tunnel mouths** (A1): short tunnels (< 60 m in all: building passages, underpasses) are open
  roads at their graded height; long ones get a mouth only at real portals: a frame and a 24 m dark
  throat (floor, walls, roof, darker inward), the terrain cells over it cut out and covered again (over
  the throat at least 0.6 m above its roof, in front of it down to the road), and the survey's street
  points inside the mouth brought down to the road (a road area at the Letenský tunel ran 191-206 m: the
  grey "barrier" across the opening was that ramp, 144 points). Visual polish waits for the fine
  terrain (user: check after the detailed terrain build).
- **Cars and a standing tram** (D1, traffic.js): a car waits at the track only while the tram's body is
  on its crossing, or while the tram moves and its front is within 16 m / 4 s of it; a tram standing
  clear of it does not hold the cars.
- **Vienna-type stops at runtime, both directions** (C1, game.js `_vienna`): carriageway on the doors'
  side (2.2-3.4 m right of the track) along the stop: no platform strip or box on the road, sign and
  shelter at the kerb on the sidewalk. Line 17: Čechův most (ours), Ke Stírce from Kobylisy, and by the
  survey also Hodkovičky, Březiněveská, Čechův most towards the centre (opposite direction; to confirm).
  `dtm.vienna` from streets.py was never used before. The user's research list (vienna, vienna-cycle,
  street-level boarding, per direction; non-exhaustive, accurate to its sources' dates) is in
  `data/truth.json` (`stopTypes`); Krymská: vienna-cycle towards Jana Masaryka only, a high kerb towards
  Ruská. Not drawn yet: the raised lane of a true Vienna stop (vs street-level boarding).
- **Track on the model deck** (A2, decision 6): on a tagged span with Mosty 3D samples the model's deck
  top is fixed like a surveyed tram bed (interpolated between samples, a floor with 500 m vertical
  curves into 6 % ramps beyond). The overpass near Nádraží Modřany (s 4060-4120): 203.2-203.5 under the
  slab → 204.65-204.77 on its top (204.9), approaches at ~3 %. Where the survey has our tram bed on the
  structure, the survey wins and the model is cut instead (a coarse block up to the parapet top, 1.6-1.9 m
  over the measured bed at s 5070 and 5824).
- **Envelope cuts of bridge models** (world.js buildLod2): bridge model triangles near our track or a
  car road on a bridge are split to <= 1.5 m first, then cut where they lie in the tram's envelope (3 m,
  0.4-5.8 m over the rails) or over a bridge road (half its width, 0.4-4.5 m over its surface).
- **Underpass clearances from OSM maxheight** (user idea; `tools/clearances.py` → `data/lineN.json`
  `clearances`): roads crossing under the route with `maxheight` (posted metres; `default` = 4.2 m on car
  roads, 2.5 m on footways, assumed also under our tagged bridges); the profile keeps the track at least
  clearance + 0.8 m over the road where it is 2 m and more above it already (at grade: nábřeží Edvarda
  Beneše at the end of Čechův most lifted the track 4 m before that rule).
- **Lints**: `deckClip` (a ray down from 2.5 m over the track / bridge roads against the drawn
  buildings and bridges): 68 → 19 (rest kerb edges 0.36-0.41 m, one road 1.1 m at (-1222, 792));
  `underpassClearance`: 0 short of 19 checked. railSupport 94 → 28.
- **Overpass**: four servers (FOSSGIS, private.coffee, VK Maps, openstreetmap.fr last: fast but data
  ~3 months old, logged per answer); public servers were saturated all evening (502/504); line 9 asks
  the opposite direction only where it runs > 50 m from our path (35 pieces instead of 70).
- Open: red runs on line 17 4 → 8 (seeds 5 / 8 / 10): oncoming trams at the same signals as the baseline
  (s 20829, 11785, 10263; already 41 km/h at 11785 there): an old fault, its count moves with the seeds;
  the line 9 fetch still running.

## 24. Local OSM extract, bridge models trimmed to the survey, stop facts (2026-10-23, night)

- **What the Mosty 3D models are** (geoportalpraha.cz "Model of buildings and bridges"; the ArcGIS item
  has no description, attributes only OBJECTID / ID_BUD): one model of buildings and bridges from
  stereophotogrammetry of aerial images, built 2001-2008 from the centre outwards, cleaned (topology,
  inner walls) in 2020; accuracy "at least 0.5 m"; walls "semi-automatically derived from the roof",
  i.e. blocks from the highest surface seen from the air (parapets, railings) down. So the model top
  is 0-0.5 m over the surveyed deck (as measured, §22), coarse at small bridges (a block to the parapet
  top over the whole width), and can predate a rebuild (anything after 2008). Rule: the survey (ZPS 2026)
  wins wherever it has the deck; the model gives the shape, the sides, piers and spans without survey.
- **Bridge models trimmed to the surveyed deck** (world.js buildLod2): model triangles over a surveyed
  deck are split to <= 1.5 m and cut 0.2-4.7 m over it (Štefánikův most: the tracks and roads clean).
  deckClip on line 17: 19 → 7 (all 0.22-0.33 m).
- **Vienna detection**: the tram bed is not a car lane (Hodkovičky, on its own corridor, came out
  Vienna-type). Line 17 now: Čechův most (both), Ke Stírce and Březiněveská from Kobylisy. User facts in
  truth.json: Hodkovičky a regular kerb stop (new, separate corridor, like Belárie); Březiněveská from
  Kobylisy and Čechův most towards the centre road-level stops with the red post on the sidewalk.
- **Local OSM** (`tools/osm_local.py`, pyosmium 4.3 in the user site, run with `python -P -E`): Geofabrik's
  Czech Republic extract (raw/osm/czech-republic-261022.osm.pbf, 950 MB, md5 checked, data of
  2026-10-22) cut to raw/osm/praha.osm.pbf (Prague + ~3 km, complete ways and relations); `ways(match,
  bbox)` answers like Overpass. `platforms.py --fetch` uses it when present (Overpass only as fallback).
  To refresh: download the newest czech-republic-latest.osm.pbf (redirects to the dated file), `cut`.
- Parked by the user: red runs of oncoming trams after the line rebuild with road traffic signals and a
  detailed whole-junction cycle model (D2); Trojský most and the stretch after it (garbled sloped roads,
  also over the tunnel mouth) after the fine terrain (B3), with a detailed rebuild before the next check.

## 25. Fine terrain (B3), local OSM for every tool, line 37 (2026-10-23, late)

- **Local OSM works end to end**: raw/osm/praha.osm.pbf (75 MB; 6.1 M nodes, 801 k ways, 19.7 k relations,
  2 625 tram ways, 77 tram routes, 2 379 platforms; one full read 14 s). `osm_local.emulate(name, query)`
  answers build_line.py's named queries (relations, route_<id>, network_tracks, tracks, points,
  platforms, buildings, roads, green, water) in the Overpass shapes, "around the route ways" done in
  shapely; build_line.py uses it whenever the extract exists (python -P -E), the raw caches first as
  before. Line 9's platforms from it: 15 s, the same 87/93 matched as the slow Overpass fetch.
- **Fine terrain** (`tools/fine_terrain.py`): ČÚZK DMR 5G (2 m TIN raster, the source of the coarse grid
  too; IPR's "Model terénu 3D" is cm-resolution LERC tiles in Web Mercator, kept for pilots) sampled
  on a 2 m lattice in 64 x 64-cell blocks touching a band of 120 m either side of either track, Int16
  cm. Line 17: 534 blocks, 4.5 MB; 22: 440 / 3.7 MB; 23: 197 / 1.7 MB; 9: 487 / 4.1 MB; 37: 234 / 2.0 MB;
  43 s per line from cached tiles. In the game (terrain.js): `Grid` (coarse grid and fine blocks alike:
  cell, height, lowerAt); `Terrain` = the coarse grid + `fine` blocks: `height` asks the fine block
  first, `grids()` lists all for the edits; carveCorridor judges walls and rock tunnels on the pre-carve
  heights (fine where present) and carves every grid; lowering under tracks and streets goes to every
  grid (fine cap 15 m, coarse 6 m) and, for fine blocks, vertex by vertex under every surveyed ground
  area (`lowerFineUnderDtm`: the survey's own vertices are too far apart for 2 m: a river area of a few
  big triangles left the quay lidar 8 m over the water); the tunnel mouths are written into the fine
  heights (no hole); world.js draws coarse cells only outside fine blocks and each fine block as a mesh
  with 3 m skirts where it has no neighbour. Dev switch `?nofine`. 60 fps in the foreground (a
  background window throttles frames: not a measurement); memory: the whole line is built and kept at
  load (no streaming), the fine terrain adds ~0.15-0.2 GB; the heap gauge mostly shows uncollected
  garbage after the build (3.4 GB read with ?nofine, 1.6 GB with fine).
  Line 17: railSupport 28 → 26, terrainOverSurvey 54 → 68 (river 12.5 m off the track at Rašínovo
  nábřeží, in the carve's blend zone), streetWaviness 4935 → 4917. Line 22: railSupport 23 → 4, overlap
  180 → 44, slide 706 → 546, terrainOverSurvey 0 → 7.
- **Line 37** (Lehovec - Spojovací, a substitute line in GTFS; no OSM route relation): build_line.py
  builds a line without a relation from its GTFS shapes like a run (`plan_line`: the most common
  direction-0 pattern, its trips, the direction-1 shape; `--gtfs` forces it). 9.5 km, 20 stops, 110
  trips, all 42 PID platforms matched to OSM, 7 roads under the route, Geoportál LOD2 + trees, fine
  terrain. Drives end to end (3 seeds): static lints 0 except railSupport 8, verticalCurves 1, lanes 185,
  deckClip 11; overlap 47, walker hits 68, red runs 6. Open: the GTFS shapes run between the two tracks
  (1.6 m from each) from Spojovací to the crossover at Kněžská luka (s 1675), and the matcher put our
  direction on the left track there, so both directions share it as a 1.7 km "gauntlet" (asked the user
  how Spojovací is worked during the closure).

