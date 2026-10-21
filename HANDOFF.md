# Handoff notes — Tatra T3 Prague tram game

State as of 2026-10-21. Read with README.md (how to run/build/play). This file records what was
found while building it, what is unfinished, and what needs attention.

## 1. Current state

- Browser game, plain ES modules + Three.js 0.160 from jsDelivr (import map in `index.html`), no build step.
- Playable lines: **9, 17, 22, 23** (menu "Line" selector; `?line=N`). All four complete end to end
  under the autopilot in dry weather with no stop/signal/switch/collision errors (rain also passes; the
  only penalties are comfort/speed/lateness from the conservative driver).
- Features: T3 pedal-style controller and force-based physics, gradients from lidar terrain, weather
  adhesion + sanding, GTFS timetable + stops + passengers with rush-hour demand, doors, contact and IRC
  switches, Prague 4-lamp tram signals with call (výzva) indicator and distant (P) signals, the Letenská
  single-track (gauntlet) block, traffic (trams ahead/oncoming, cars, pedestrians), obstacles,
  Czech/English UI, scoring, results screen, **watch-the-ride autopilot** (menu or `O`).
- World: OSM tracks/roads/greenery/water, ČÚZK DMR 5G terrain, and (where imported) IPR Praha LOD2 3D
  buildings, surveyed retaining walls and the city tree register.
- **Not play-tested by a human beyond the user's own sessions.** Verification so far = headless
  autopilot runs + screenshots in the desktop app's browser pane.
- **The project is not a git repository.** Recommend `git init` with `raw/` (420 MB cache) ignored.

## 2. Run, build, test

```bash
python tools/serve.py 8740                                     # dev server, no-cache headers
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
Last baseline (dry, obstacles normal): line 22 ≈ 3550–3760 s sim time, 23 ≈ 1870 s, 17 ≈ 3390 s,
9 ≈ 2630 s; all `finished: true`, no `bad:` messages except speeding/lateness.

## 3. Code map

| File | Role |
|---|---|
| `src/main.js` | loading (line JSON + optional geo sidecar), renderer, weather/world rebuild, menu, input, camera, frame loop, results |
| `src/route.js` | `Route` (arc-length polyline, **smoothed** with original s preserved), `smoothPolyline`, nearest/radius/speed limits |
| `src/terrain.js` | `Terrain` (DMR 5G grid), `Profile` (track z(s): bridges, tunnels, 9 % grade limiter, smoothing), `carveCorridor` (bench + synthetic retaining walls), `makeGround` |
| `src/world.js` | static scenery: terrain chunks, roads, tracks (+smoothed heights), Most Legií deck/piers, walls, buildings (LOD2 or OSM fallback), trees, catenary |
| `src/tram.js` | T3 constants and longitudinal dynamics (forces, adhesion, slip/slide, sand, rollback, electrics) |
| `src/game.js` | rules: stops/passengers/demand, doors, signals, gauntlets, distant signals, switches/IRC/contacts, obstacles, cross traffic, scoring |
| `src/traffic.js` | ambient cars (street lanes + road network), pedestrians, AI trams ahead/oncoming |
| `src/autopilot.js` | shared driver (watch mode + headless tests) |
| `src/models.js` | T3, cars, people, signal head + call box, LED switch indicator, signs, red stop post |
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
- **Contacts** at switch s − 22 m (real positions unknown). A switch becomes **IRC** if a stop or a
  signal lies within 60 m before its contact (otherwise you'd have to coast/power from standstill).
  ~16–22 of ~33 switches per line end up IRC.
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
6. **Street cars** never use lanes that overlap a track, so streets where cars share the tram lanes
   (common in Prague) have no parallel traffic. Cars ignore each other at junctions.
7. **AI trams** ahead appear at a stop 450–900 m ahead and fade out 1 km ahead; they never turn off.
8. **Asset sizes**: per line ~3.5 MB JSON + 2.6–4.6 MB building binary; `serve.py` doesn't gzip;
   JS heap ~190 MB on line 23. Fine locally; compress for hosting.
9. **Draco**: importer reads the uncompressed geometry buffer; if IPR switches to Draco-only it breaks.
10. **Audio** was never listened to by me; mixing levels are guesses.
11. Only tested in the desktop app's Chromium browser pane; keyboard only (no gamepad/touch).
12. `hud.js` minimap draws all track chains every frame (cheap enough now; watch on long lines).

## 7. Backlog (user requests and agreed ideas)

- **Cab dashboard**: more detailed 3D/realistic T3 control panel — deferred by the user (no good
  reference photo yet).
- **Orthophoto** ground texture (10 cm IPR ImageServer) — explicitly skipped "for now".
- **Mosty 3D** bridge models (Most Legií etc.) instead of the synthetic deck.
- Two-car T3 set (double length/mass, stop position), night/dusk with lights, snow/ice, gamepad
  (triggers = pedals), real speed-sign positions, more lines (any Prague line works via the two tools).
- Better pedestrians (walking animation, boarding into doors), cars on shared tram lanes as obstacles.
- Hosting: static site; gzip/brotli data; maybe stream building chunks.

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

## 9. User context

Prague-based, knows DPP/Prague trams in detail (signals, IRC, stop posts, Letenská gauntlet) and
supplies reference photos and sources. Prefers realism grounded in real data, Czech-specific detail,
and a fully localized cs/en UI. Asked to keep the game playable while it grows (autopilot "watch the
ride" mode).
