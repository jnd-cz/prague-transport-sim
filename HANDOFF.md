# Handoff notes — Tatra T3 Prague tram game

State as of 2026-10-21 (sections 13–15: 2026-10-22). Read with README.md (how to run/build/play).
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
README → Dev and PLAN.md §2.

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
| `tools/serve.py` | static server with `Cache-Control: no-store` |

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
3. **Tree species flag** (`kod_drevin == 1` assumed conifer) is unverified and unused in rendering.
4. **Retaining walls** are drawn freestanding from the lower ground up to `vyska`; which side is
   retained is not in the data.
5. **Line 9** route extends ~3 km past the last stop (see §4).
6. **Street cars** now use lanes beside the track zone, but never drive *on* the tracks (shared
   lanes) and ignore each other at junctions (they do follow each other within a road/lane).
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
- **Mosty 3D** bridge models (Most Legií etc.) instead of the synthetic deck.
- Two-car T3 set (double length/mass, stop position), night/dusk with lights, snow/ice, gamepad
  (triggers = pedals), real speed-sign positions, more lines (any Prague line works via the two tools).
- Better pedestrians (walking animation, boarding into doors), cars on shared tram lanes as obstacles.
- Hosting: static site; gzip/brotli data; stream tiles (§10).
- **Whole network** (§10): every OSM tram track, tiles loaded on demand, AI trams on their real
  lines and timetables.

## 8. Environment gotchas (Windows dev machine)

- Run Python tools with `python -I`; `-I` ignores `PYTHONIOENCODING`, so scripts call
  `sys.stdout.reconfigure(encoding="utf-8")`. PIL is only available without `-I`.
- Bash heredocs with apostrophes or backticks in the body break the tool's shell parsing — write
  patch scripts to a file (scratchpad) and run them instead.
- The browser caches ES modules aggressively; the dev server moved from port 8737 to **8740** with
  `no-store` headers. Use `import('/tools/autopilot.js?v=' + Date.now())` in the console.
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
