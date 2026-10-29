# Knowledge: data quirks, conventions, why the heuristics exist

What sessions learned and later work needs. Kept current and short; the full logs are in
[history/](history/) (HANDOFF.md §n, REMOTE-CHANGES.md §n). Tasks are GitHub issues, not here.

## Coordinates and heights

- **Today's line frame** (`tools/geo.py`, every tool): local metres around a per-line origin, 110 574 m
  per degree of latitude and 111 320·cos(lat0) per degree of longitude. It squeezes the world 0.59 %
  N–S and 0.20 % E–W (line 17 is 100 m short of 21 799 m), and two lines' worlds do not meet. To be
  replaced by one city-wide S-JTSK (EPSG:5514) frame (M2).
- **Heights are Bpv** (Baltic after adjustment) in DMR 5G, the DTM survey and Mosty 3D alike: measured,
  the model tops sit 0–0.5 m over the surveyed decks (an ellipsoid mix-up would be ~45 m).
- Geoportál I3S layers are Web Mercator with absolute heights; the orthophoto ImageServer is S-JTSK.
- The track ribbon is drawn 0.20 m (bed) and 0.26 m (rails) over the profile height: rendering offsets
  to redefine with "what each height means" (M2).

## Sources and their quirks

- **OSM** (local extract only, [decision](decisions/2026-10-23-local-osm-extract.md)): route relations
  PTv2; track ways are merged into chains split only at junctions and bridge ends (no smoothing kinks).
  Tunnels from `tunnel`, `covered=yes`, negative `layer`. OSM splits tunnels and bridges into many ways:
  heights must run along the whole chain (`chainTunnels`), or inner ends take the hill top or the river.
  Interlaced track is tagged `railway:interlaced=yes` (Letenská).
- **Switch detection** (facing only): a route node with an extra track neighbour heading forward; a
  neighbour on a track passing straight through is a diamond crossing (line 22: 16 of 33 "switches").
- **PID GTFS**, service date fixed at 2026-10-21. Line 22 needs `--headsign "Zahradní Město"`. Line 9 is
  built as a 9 → 10 run. Line 37 (a substitute line) has no OSM relation: built from its GTFS shapes,
  which run between the two tracks in places; the matcher prefers the right-hand track (regular
  service always uses it, `data/truth.json`).
- **ČÚZK DMR 5G**: bare-earth lidar (embankments over underpasses are in it), 2 m TIN raster; coarse
  10 m grid + fine 2 m blocks within 120 m of the tracks (`tools/fine_terrain.py`, `?nofine`).
- **Prague DTM / ZPS survey** (street areas, kerbs, points): all of line 17, part of 22. Its vertices are
  far apart (big river triangles), so terrain is lowered vertex by vertex under surveyed areas.
- **IPR Geoportál** (CC BY 4.0): LOD2 buildings (untextured, gzipped I3S, we read the non-Draco buffer:
  breaks if IPR goes Draco-only), retaining walls with `vyska` (which side is retained is not in the
  data), tree register (multipoint) and tree rows.
- **Mosty 3D**: photogrammetry 2001–2008, ±0.5 m, blocks from the highest surface seen from the air
  (parapets) down; can predate rebuilds. **The survey deck wins wherever it exists**; the model gives
  sides, piers and spans elsewhere, and is trimmed over surveyed decks.
- **OSM `maxheight`** under the route gives underpass clearances (`tools/clearances.py`; default 4.2 m
  car roads, 2.5 m footways), applied only where the track is already ≥ 2 m over the road.
- Tatra T3 figures (ČKD pamphlet, unverified): 16 t empty, 4 × 40 kW, ~39 kN, 1.8 m/s² service accel and
  brake, 5 m/s² emergency, 24 seated + 86 standing.
- Prague signals: 4 white lamps on a white plate (stop = outer two), call box with three orange LED bars,
  distant signal with a yellow "P"; switch indicator a red LED chevron on the span wire.

## Heuristics that stand in for missing data

Review these when realism matters; most move into the build in M2.
- **Signals**: from OSM `traffic_signals` clusters near the route; never past the crossing they were
  made for (except along platforms, where the platform-head rules decide); two at one stop line are one.
  GO held for a tram in its dilemma zone (15 + v²/1.6 m). Distant signals where R < 110 m within 140 m.
- **Gauntlets**: opposite route < 1.8 m away for ≥ 25 m (needs exact `Route.nearest`, which refines
  onto the chords: 4 m samples read 0.3 m tracks as up to 1.9 m apart).
- **Contacts** at switch − 22 m (real positions unknown), worked by the pantograph, moved out of stop
  zones and signal queues; all switches manual on purpose (driver skill).
- **Catenary poles** march out past tracks and carriageway to the kerb; a building within 5.5 m gets a
  wall rosette, else bracket arms.
- **Tram streets**: a road within 2.6 m of a track over 60 % of its length is widened 3.2 m per track.
- **Vienna-type stops**: carriageway on the doors' side 2.2–3.4 m from the track along the stop (the
  tram bed is not a car lane); facts per stop and direction in `truth.json` `stopTypes`.
- **Bridges on the model deck**: on tagged spans with model samples, the model deck is fixed like a
  surveyed bed (floor and ceiling, ±3.3 m sideways search on our own bridges); not on surveyed beds.
- **Tunnel mouths**: chains < 60 m are open roads; longer ones get a portal with a 24 m throat, heights
  from the approach road, the terrain re-covered over it.
- **Trees** ≥ 3.2 m from a track, crowns ≥ 1.9 m; **LOD2 buildings** within 2.5 m of the route lifted to
  track + 6.3 m (passages like Letenská).
- **Speed limits** from curvature, posted OSM speeds and switches; stop zone −20…+12 m; adhesion dry
  0.30, rain 0.17, leaves 0.15; demand peaks 7–9:30 and 15:30–17:30.
- **Traffic**: cars wait at the track only while the tram's body is on the crossing or it is about to
  arrive (16 m / 4 s); AI trams ahead run at the limit, spawned 700–1300 m ahead, board 6–8 s when ours
  is within 300 m; oncoming trams stop at the far end of their own platform.

## Checks and what they measure

- `tools/lint.js` (page with `?keepgeo`): consist at stops, signals in platforms (counts the remote's
  platform-head signals: 6 on line 17 is expected), trees in buildings, bridges, invented walls, tram
  envelope, grade separation, railSupport, verticalCurves, terrainOverSurvey, streetWaviness,
  `deckClip` (ray down against drawn buildings and bridges), `underpassClearance`, lanes, street bot.
- `lint({ traffic: true })` / `tools/traffic_lint.js`: slide, jump, overlap, walker hits, red runs;
  averages seeds 22, 7, 1234; a run that does not finish is a jam (follow `car.seen.car`).
- `tools/bench/`: u3 (signals, junctions, collisions), redruns, walkers, heads; `batch.html` runs them.
- Line 17's full lint after the merge is the pre-rebuild reference (`reports/line17.json`).

## Environment (Windows dev machine)

- Python `-I` ignores `PYTHONIOENCODING`: scripts call `sys.stdout.reconfigure(encoding="utf-8")`.
- Shell heredocs with quotes or backticks break: write scripts to a file.
- ES modules are cached hard: the dev server sends `no-store`; import tools with `?v=` + `Date.now()`.
- Browser script calls time out at 45 s; a hidden pane throttles `requestAnimationFrame`, so step the
  simulation in JS (`window.headless`) rather than waiting in real time.
- Memory: the whole line is built at load (no streaming); fine terrain adds ~0.15–0.2 GB.
- The `gh` CLI lives in `C:\Program Files\GitHub CLI` (not always on the Bash PATH).
