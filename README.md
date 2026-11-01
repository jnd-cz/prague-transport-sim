# Tatra T3 — Prague trams (browser prototype)

Arcade tram driving in a 3D Prague built from real data: OpenStreetMap track network, buildings,
roads and greenery, ČÚZK DMR 5G lidar terrain (10 m grid), and the PID GTFS timetable for
line 22 (Bílá Hora 382 m → Malostranská 189 m → Náměstí Míru 246 m → Zahradní Město 237 m).

Project docs: [ROADMAP.md](ROADMAP.md) (milestones; tasks are GitHub issues), [AGENTS.md](AGENTS.md)
(working rules for agents and contributors), [docs/knowledge.md](docs/knowledge.md),
[docs/architecture.md](docs/architecture.md), [docs/decisions/](docs/decisions/).

## Run

```bash
python tools/serve.py 8742
```

Open http://localhost:8742. There's no build step: plain ES modules, with Three.js loaded from a CDN.

The game data (`data/`) and the raw sources (`raw/`) are not in git: a fresh clone gets them from the
data store, see **[DATA.md](DATA.md)** (one-time SSH setup, then):

```bash
python -I tools/snapshot.py data-fetch     # data/ to play and tune the game (~85 MB)
python -I tools/snapshot.py fetch          # raw/ to build the world (~2 GB, the pinned source snapshot)
```

## Rebuild the line data

Every build reads the pinned source snapshot in `raw/` (DATA.md); OSM comes from its local extract
(`raw/osm/praha.osm.pbf`, pyosmium, so the OSM tools run with `-P -E`). The Overpass API is not used.
All lines share one frame: S-JTSK metres from the Marian column (`tools/geo.py`).

The whole chain for a line (logs in `reports/rebuild/`): `build_line` first, then its independent steps
side by side; `--parallel` also builds the lines side by side, as many as free memory holds (~2.5 GB each).
The OSM extract is read once per build (~1 min), and a line takes ~2-4 min:

```bash
python -P -E tools/rebuild.py 17 22          # or all lines: python -P -E tools/rebuild.py --parallel
```

The single steps:

```bash
python -P -E tools/build_line.py --line 37         # no OSM route relation: from its GTFS shapes
python -P -E tools/build_line.py --line 22 --headsign "Zahradní Město"
python -P -E tools/build_line.py --line 23         # any Prague tram line
python -P -E tools/build_line.py --line 17 --refresh  # recompute the OSM answers cached in raw/line17/
python -P -E tools/build_line.py --line 9 --then 10   # a vehicle run: 9, continuing as 10 at the terminus
```

After a rebuild: `python -I tools/snapshot.py data-publish --note "…"` and commit `data/MANIFEST.json`.

With `--then`, the route is not taken from the OSM relations (they describe the regular route, not
diversions) but from the PID GTFS shapes of the two trips, matched onto the whole Prague OSM tram
network; trips are paired only when the next trip in the GTFS vehicle block starts at the same terminus
on the selected pattern. Unmatched or ambiguous trips are reported by the build. The current line 9 is
such a run: Sídliště Řepy → Nákladové nádraží Žižkov as 9, back to Řepy via Vinohradská as 10
(track repairs, autumn 2026).
Stop platforms come from OSM (`public_transport=platform`) for all lines.

The script finds the line's OSM route relations by `ref`, takes the GTFS direction-0 headsign
with the most trips on the service date (override with `--headsign`), checks that the GTFS stops
lie on the chosen OSM route, and writes `data/lineN.json` plus the menu index `data/lines.json`.
The OSM answers are cached in `raw/` (line 22), `raw/runN-M/` (a run such as 9 → 10) and `raw/lineN/`
(other lines), each marked with a key of the extract, the query and the code that answers it
(`tools/osm_local.py`, `tools/geo.py`): a new snapshot's extract or an edit to either file recomputes
them. A line without an OSM route
relation (a substitute line such as 37) is built like a run, from its GTFS shapes (`--gtfs` forces
it). Built lines: 9, 17, 22, 23, 37.

Then, optionally, import the Geoportál Praha data for the line (recommended):

```bash
python -I tools/geoportal.py --line 22
```

This fetches, for the corridor 110 m either side of the route, the IPR Praha LOD2 3D buildings
and the Mosty 3D bridges (I3S scene services: real roof shapes, absolute heights matching the
terrain), retaining walls with
their heights and the city tree register (individual trees and tree rows). It writes
`data/lineN.geo.json` and the quantised building geometry `data/lineN.bld.bin` (2.6–4.6 MB per
line). Without it the game falls back to extruded OSM footprints. Underpasses and tunnels on the
route (OSM `tunnel`/`covered`/negative `layer`) are spanned in the track profile.

Optionally, the surveyed streets from the Prague Digital Technical Map (DTM, open part "ZPS", per
city district, CC BY 4.0) — imported for line 22 (Praha 2 and 10) and all of line 17 (Praha 1, 2, 4,
7, 8, 12 and Troja):

```bash
python -m pip install --user pyproj shapely
python tools/dtm.py --line 22 raw/dtm/<..._500089_..._ZPS_OPL.gpkg> raw/dtm/<..._500224_..._ZPS_OPL.gpkg>
python -P -E tools/dtm.py --line 17 raw/dtm/*_{500054,500089,500119,500186,500208,547107,547174}_*_ZPS_OPL.gpkg
```

(`-P -E` instead of `-I`: pyproj and shapely live in the user site-packages.)

Posted speeds and dedicated track (after `build_line.py`; needed for the speed limits and banked
curves):

```bash
python -I tools/osm_speeds.py --line 22
```

Only the vegetation from Geoportál again (tree categories): `python -I tools/geoportal.py --line 22 --trees-only`.

Tram platforms of both directions (PID GTFS positions, names and lines; OSM shapes where mapped):
`python -P -E tools/platforms.py --line 22` (`--fetch` re-reads the OSM platforms from the snapshot's extract).
`python -P -E tools/clearances.py --line 17` lists the roads passing under the route with their OSM `maxheight` (the profile keeps the track over them).

The **fine terrain** near the tracks (ČÚZK DMR 5G on a 2 m grid in 128 m blocks within 120 m of either
track; the 10 x 15 m grid stays elsewhere): `python -P -E tools/fine_terrain.py --line 17` writes
`data/lineN.fine.bin` + `.fine.json` (2-5 MB; export tiles cached in raw/dem/). `?nofine` loads
without it.

`dtm.py` also puts the kerbs back: the survey records a kerb as one line with one height, and
`tools/kerbs.py` decides per sidewalk, island and platform which side that line belongs to and moves
the other side by the step (0.10 m, platforms measured; #21). Surfaces are drawn straight between the
surveyed vertices.

Download the district GeoPackages from geoportalpraha.cz → Data a služby → "DTM kraje - ZPS Sada 2"
(areas, `*_ZPS_OPL.gpkg.zip`) and "ZPS Sada 3" (3D lines, `*_ZPS_KR.gpkg.zip`), unzip both into
`raw/dtm/` (the tool pairs each OPL folder with its KR folder). It writes `data/lineN.dtm.json`.

Expects `raw/PID_GTFS.zip` (download from https://data.pid.cz/PID_GTFS.zip). Terrain comes from the
ČÚZK DMR 5G ImageServer (`exportImage`, cached as `raw/terrain.tif`). Writes `data/line22.json`.
The service date is a constant at the top of the script.

## Deploy

The game is static files: `index.html`, `src/`, `assets/`, `data/`. Three.js comes from jsDelivr and
the outdoor temperature from Open-Meteo, both fetched by the browser. `python tools/make_dist.py`
packs them into `dist/tatra-t3-prague.zip`; unzip it into any web server directory. Enable gzip or
brotli for `.json` and `.bin` on the server (~3x smaller downloads). The detailed tram model is
CC BY-NC 4.0: fine for a non-commercial public test, with its attribution shown in the menu.

To a web host over FTPS (#131): `python -I tools/deploy.py` uploads the same files from a clean commit
whose data matches the manifest:
- only the changed files go up (the server keeps `.deploy-manifest.json`), and removed ones are deleted;
- it adds `version.json`, shown in the menu's credits, and an `.htaccess` with compression;
- `--dry-run` lists the changes, `--reports` adds `reports/headless/*.json` for review mode, and a rollback is a deploy from the older commit.

The host, the FTP user and the folder go in `deploy.local.json` (git-ignored; format at the top of the tool). The password is asked for each time, or read from `TRAM_DEPLOY_PASSWORD` or `~/.netrc`. The site's own protection is the host's: in Plesk, Password-Protected Directories on `/`. After each upload the tool checks that `version.json` answers 401 without a login.

Automatic (#131): `python -I tools/autodeploy.py` in a checkout kept for deploys (detached HEAD, with
`deploy.local.json`, as `../tg-deploy`) deploys `origin/main` when it moved since the last deploy:
checkout, `snapshot.py data-fetch`, `deploy.py`. `--install` registers a Windows scheduled task that runs
it every 10 minutes while you are logged on (`--uninstall` removes it). It needs the password in
`~/.netrc` (`machine <host> login <user> password <password>`); a failed deploy is retried after an
hour. Log: `reports/autodeploy.log`.

## Gameplay

- **On a phone or tablet** (#79): on-screen buttons, shown on a touch screen by default and switched by
  🎮 in the menu (remembered per device). They send the keyboard's keys:
  - the row above the dashboard: ▼ brake, 0 neutral, ▲ drive, STOP (the emergency brake, held), and
    the dead-man button when that option is on;
  - the left column: doors, bell, sand (held), look left / right (held), view, mirror, pause;
  - ⋯ for the rest: switch contact, switch iron, heating cut-out, heating, autopilot, sound, ⚑ report.

  On a small screen the dashboard and the top bar are smaller and the minimap is hidden.
- **Outside view** (V): the camera orbits the tram. Drag to turn and tilt it; the wheel or two fingers
  zoom; a double click brings it back behind the tram.
- **The right mirror** grows with the window (a quarter of its height, 110–420 px) and keeps its
  aspect, so its field of view stays the same; its picture is drawn at the frame's size in device
  pixels.
- Pedal-style controller: J1–J4 drive, B1–B4 electrodynamic brake, emergency with magnetic track brake.
  Forces follow the ČKD T3 pamphlet (1.8 m/s² acceleration and service braking for an empty 16 t car),
  so a full car is slower; gravity on gradients (Chotkova ~7 %), curve resistance, rolling back
  when the brake is released on a hill, lateral comfort in curves.
- Weather: dry / rain / autumn leaves sets wheel–rail adhesion. Too much power spins the wheels,
  too much brake locks them (flats). Hold A to sand; the emergency brake sands automatically and its
  magnetic track brakes don't depend on adhesion.
- Line selection in the menu (each line loads its own world). Stop posts list the day lines serving
  each stop (GTFS `route_stops`); trams of those lines run ahead of you.
- Line changes: a run can change its number at a terminus (line 9 continues as 10 at Nákladové
  nádraží Žižkov): everybody gets out, the route boxes and the HUD switch, the tram departs as 10.
- Speeds: each curve allows √(a·R) with 0.8 m/s² unbalanced lateral acceleration, never above the
  posted speed of the OSM tram way (`tools/osm_speeds.py`, the data OpenRailwayMap shows) and 50 km/h
  in streets / 60 on dedicated track. Curves on dedicated track are banked (up to 100 mm cant, level
  at stops and near the termini); the tram and the view lean into them.
- Junctions: each signal belongs to a junction controller with a fixed cycle (trams straight in both
  directions, a turning phase, the cross street) and tram priority; oncoming trams obey it.
- Traffic: cars drive a lane graph (smooth lanes, turning curves through junctions), give way at
  junctions, queue behind trams on shared track, stop for walkers; trams stop behind cars on their track.
- Menu options: automatic switches (onboard computer sets every switch by radio instead of the
  overhead contacts), performance overlay (FPS, frame time, draw calls, triangles, JS heap).
- Sets: most lines run two-car T3 multiple-unit sets (2 × 15.2 m over couplers, both cars powered,
  six doors); line 23
  runs a single heritage car. "Set" in the menu overrides it. Each car follows the track on its own
  bogies.
- Passengers: an on-board counter (normal capacity 110, crush 160 per car). Demand follows the time of day
  — morning (7–9:30) and afternoon (15:30–17:30) peaks bring crowds, nights are quiet; a packed car
  boards slowly and a full one leaves people for the next tram.
- Stops from GTFS with real departure times. Where OSM maps the platform, the whole set must stand
  alongside it (so a second tram can stop behind one already at a long platform); otherwise stop at
  the sign. Open the doors, wait for boarding and depart on time; early departures cost the most.
  Request stops (✋) can be passed when nobody waits.
- Switches: every facing switch has an overhead contact (yellow plate, white sign with a black
  triangle), worked by the pantograph: pass under it drawing current to set the turn, or coasting to go
  straight — also right after a stop, at a signal or on a hill (judging that is part of the driver's
  skill). Current also flows with the **Výhybka** button (Y, as on T3SUCS) and — in winter — through
  the heating, unless you hold the heating cut-out (C) while coasting under the contact. Contacts are ~22 m before the switch but never where a tram stands with its pantograph at a
  stop or signal. Trailing switches (where tracks join) need nothing; diamond crossings are not
  switches. The red LED arrow before each switch shows the blade position and blinks while the switch
  is locked. If you got it wrong, stop and use the crowbar (X). (Radio/IRC switching remains in the
  code for switches the data marks as such; none are marked now.)
- Stops: the tram counts as at the platform when its front is between 20 m before and 12 m past the
  stop sign; within 3 m of the sign earns a precision bonus.
- Prague tram signals (four lamps: three on top, one below): the two outer top lamps = stop; top middle +
  bottom = go straight; top left/right + bottom = go left/right; a blinking GO aspect means it is ending.
  The call signal below shows three LED bars (\ | /): the bar of the coming direction lights orange
  once the tram is detected and blinks just before GO. Distant signals with a
  yellow "P" plate stand before signals hidden behind curves. Tram priority; cross traffic drives
  along the real crossing street and stops at its line while the tram has GO.
- Interlaced track in Letenská (under the building near Malostranské náměstí): both directions share
  ~65 m of track, detected automatically from the two OSM route relations. Signals at both ends grant
  the section to one direction at a time, return to STOP behind the entering tram, and hold the other
  side until the section is clear plus 6 s clearance. Oncoming trams obey it.
- Signs: classic red Prague stop signs, speed limit boards (rychlostník), contact signs, dangerous
  gradient boards. Zebra crossings painted where OSM marks them (not across the tracks).
- Traffic: other trams ahead on the same track (they stop at stops and red signals: keep your distance)
  and oncoming on the opposite track — each carries a line that really serves that stop (GTFS) and
  turns off (fades out) after the last stop it shares with your line. Cars in the lanes beside the
  tracks (following the real road geometry and one-way streets) and on the surrounding road network
  (continuing across junctions); they keep their distance, queue, and pitch/roll with the road
  surface. Pedestrians on footways and sidewalks who keep off the tracks. Everything fades in and out. Obstacles: parked cars fouling the track (ring the bell) and
  pedestrians crossing.
- Terrain: the track corridor is carved into the lidar terrain; retaining walls where the line is cut
  into a hillside (Chotkova), Most Legií on a deck with piers. OSM track geometry is smoothed into curves,
  and the terrain is lowered under every track bed so it never pokes through.
- Heating (DPP T3SUCS manual): saloon seat heaters 0/1/2 (H: three seats each side / all seats),
  cab heater (kalorifer) 0–3 (K: off / fan / half / full) and the flap that lets the accelerator
  resistors' waste heat into the saloon (F). The info panel shows the outside, saloon and cab
  temperatures. Outside temperature: Prague now (Open-Meteo, hourly) or a fixed winter / autumn /
  summer day (menu). Cold passengers (< 12 °C) and heat you caused cost points; open doors let the
  heat out; in summer passengers open the windows.
- Looking around: hold Q / E (or ← / →) to look out of the left / right window; the right
  rear-view mirror (Z toggles) shows the side of the set and the doors.
- Signals and signs stand off the road: on catenary poles, hung from span wires beside the contact
  wire, or at the kerb — not on platforms.
- Buildings are textured by type (old tenement, panel block, church, industrial hall, glass office)
  from the OSM tag under each LOD2 building, its roof shape and size. Real 3D bridges (Mosty 3D) set
  the deck height on tagged bridges and the clearance under structures (station canopies included).
- Tram model: detailed ("Tatra T3" by Jakub Vaja (conflig), [Sketchfab](https://sketchfab.com/3d-models/tatra-t3-76aa08d7c06340fc89229551c45e3c3a), CC BY-NC 4.0, simplified — see `assets/t3/LICENSE.txt`)
  or the built-in simple one (menu).
- Overhead line: span wires anchored on poles at the kerb (between carriageway and sidewalk), on wall
  rosettes where a building stands close, or a bracket arm where one side has no room; closer spacing
  on curves. Street trees are kept (pruned) clear of all tracks.

## Autopilot

Tick "Autopilot — just watch the ride" in the menu, or press **O** during a shift. It drives like the
headless test bot: plans speed from limits, stops, signals, obstacles and the tram ahead, picks the
notch from the forces needed on the gradient, works the doors, departs on time, rings the bell, sands
on slippery rail, and gives a short pulse of power (turn) or coasts (straight) under contacts. Press **V** for the outside
view. Any controller or door key (W/S/Space/N/D) takes over; O hands back to the autopilot. The
same driver lives in `src/autopilot.js` and is used by `tools/autopilot.js`.

## Language

The interface is in Czech or English (Settings → Language in the menu; remembered in the browser).
Strings live in `src/i18n.js`.

## Dev

**Headless checks from the command line** (Playwright, see DATA.md setup): the benches and lints below,
each in a fresh headless page, with pass / fail per run (exit code 1 on a failure) and the results in
`reports/headless/`:

For a combined GTFS run, independently check every logged pair and the built timetable against the
pinned GTFS, including eligible pairs omitted from both the log and timetable:

```bash
python -I tools/audit_run_timetable.py --line 9 --log reports/rebuild/line9.build_line.log
```

The audit takes the service date from the build log (`service date …`, `SERVICE_DATE` in
`tools/build_line.py`).

```bash
python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
python -P -E tools/headless.py --lines 23 --checks traffic,lint --seeds 22,7,1234
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,lint --jobs 3
```

`--jobs N` runs N pages at once, each in its own browser process (default: by cores and free memory,
up to ~4 GB a page for line 17). The runs are seeded per page, so the counts are the same as one after another.

The harness verifies its own server before launching a job. An occupied `--port` fails without using
or stopping the existing listener; use `--port 0` to allocate a free port atomically. `--url` explicitly
uses an already-running server.

Regression checks compare with main's baseline in `reports/baseline/headless.json`: the key counts of
each run, with the code and data they were measured on.

```bash
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --seeds 1 --compare
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --seeds 1 --baseline
```

`--compare` prints baseline → now per run (also in `reports/headless/compare.md`, for the PR) and marks
problem counts that rose (traffic counts beyond a 15 % + 5 noise band). It warns when the baseline was not
measured on main's code and data. `--baseline` stores the run as the new baseline; it needs the game,
the in-page checks and `data/MANIFEST.json` committed and `data/` matching the manifest.

`tools/autopilot.js` drives the game headlessly to check the rules. In the browser console:

```js
const { autopilot } = await import('/tools/autopilot.js');
autopilot(0, 99, { obstacles: 'normal', weather: 'rain' });
```

**Lints** ([docs/knowledge.md](docs/knowledge.md)): each check counts one kind of problem over the whole line. With the dev server
(`tools/serve.py`, which saves the reports), the page loaded with **`?keepgeo`** (the game otherwise frees
the meshes' CPU copies after loading) and a shift started on the line:

```js
const { lint } = await import('/tools/lint.js?v=' + Date.now());
await lint();               // consist at every stop, signals in platforms, trees in buildings, bridges
await lint({ bot: true });  // + the street bot where DTM streets exist (about a minute)
await lint({ traffic: true }); // + the whole line driven headless with the real traffic (1–2 minutes)
```

The traffic run (`tools/traffic_lint.js`) starts a shift at the first stop and lets the autopilot drive
to the end with a fixed time step; the page's frame loop only draws meanwhile (`window.headless`).
Every 0.2 s it records every visible car, walker and tram and counts: cars or walkers moving sideways
(`slide`), teleporting (`jump`), vehicles intersecting (`overlap`, once per episode) and walkers inside
a vehicle (`walkerHit`), each with its cause where known (next road, lane beside the tram, …). It is
seeded and uses the first trip, autumn and dry weather, so a run on a **freshly loaded page** gives
the same counts every time (a second run in the same page differs slightly).

Reports go to `reports/lineN.json`. Compare with the in-page baseline (exit code 1 if a count rose).
That baseline (`reports/baseline/lineN.json`) dates from 2026-10-23, before the city frame (#7) and top of
rail (#84), and is no longer maintained: for regression checks use `tools/headless.py --compare`, whose
baseline follows main.

```bash
python tools/lint_report.py
```

After an intended improvement, run it with `--accept` to make the current reports the new baseline.
Facts from the user that checks are scored against live in `data/truth.json`.

**Inspect mode** (looking around fast): open `index.html?line=17&inspect` and start a shift, or press
**I** during one. The autopilot drives, time runs at 4× (Space pause, + / − from 1/4× to 32×), the cab
overlay is hidden and the mouse moves the camera: **orbit** around the tram (drag to turn, wheel to zoom)
or **fly** (C; drag to look, W/A/S/D, R/F up/down, Shift faster, wheel = flying speed). PgDn / PgUp
(or . / ,) put the camera at the next / previous stop, T back to the tram, I leaves (the autopilot keeps
driving: O hands back the controls). The camera's route position is on the panel, handy with the lints.

**Review mode** (the checks' findings on the map, desktop or phone; #129): open
`index.html?line=17&review`, no shift needed. The panel lists findings worst first:
- the kerb review list from the survey's provenance (`tools/kerbs.py`);
- seams and flat or sunk kerbs between neighbouring survey areas, grouped per 30 m;
- with `&review=reports/x.json`, every `{x, y}` in that file (a lint or headless result, a hand-made list).

Choosing one (a row, a tapped pin, N / B) moves the camera there. The card says:
- the street (OSM name) and the nearest stop;
- `s`, `x, y` and lat/lon;
- links to Mapillary, Panoramax, the Mapy.com aerial and Google Street View at that place (facing the camera's heading).

**Layers** toggles the survey classes as colours, the wireframe of the survey triangles, the survey's own lines (**Source**), kerb edges, seam posts, pins, our track, the buildings and the trees.
The classes and the wireframe are the game's build of the survey (`tools/dtm.py`: merged areas,
fitted heights). **Source** draws the survey's 3D lines as they come (`data/lineN.zps.json`,
`tools/zps_source.py`, lines with surveyed streets) at their own heights: white at ground level, cyan
below, orange above, red dots where a vertex has no height. The card then lists the source lines
within 5 m with their kind, level, height there and height accuracy class.
- **Mouse:** drag pans, right-drag (or Shift-drag) turns and tilts, the wheel zooms.
- **Touch:** one finger pans; two fingers pinch, twist and tilt.
- **Keys:** W/A/S/D, Q/E, R/F.

The address follows the camera (`&at=x,y,yaw,pitch,dist`), so a place can be bookmarked or sent. From a phone at home: `python tools/serve.py 8742 --lan` (only the game's files; read-only apart from review answers) prints the address to open; Windows asks once to allow it through the firewall.

**Answers** (#136): the card has a button per answer (1–4 on the keyboard) and a note. The answers compare
the game with reality (the imagery): kerbs wrong in game / matches reality / other level or wall / unsure;
which of the source and the build is wrong is for the agent to find. An answer is saved
and the card moves to the next finding without one; **to do** hides the answered ones, and their pins turn
grey. The answers are kept per line in the browser and sent to the server, which merges them per finding
(the newer wins), so a phone and a computer share one review:
- on the test host: `review.php` (uploaded by `tools/deploy.py`, behind the site's login), stored in
  `reviews/`; `tools/autodeploy.py` pulls them into `reports/reviews/lineN.json` of the deploy checkout
  on every run, and `python -I tools/deploy.py --pull-reviews` does it at once;
- with `tools/serve.py`: straight into `reports/reviews/lineN.json`.

Each answer keeps the finding's kind, place, street and info with it, so it can be read without the page.
A findings file can bring its own answers (`"options": [...]`). Lists for review are committed in
`reports/review/` and deployed with the site: `?line=17&review=reports/review/track-z.json` is #106's
large track-height disagreements (`tools/dtmp_tracks.py --findings`).

**Report an issue** (#138): **⚑ Report** at the bottom left of a shift, or F9 (also in inspect mode),
pauses the game and asks for a kind and a note. Send stores the note with the moment's state and a
screenshot of the 3D view. The state covers the line, trip, clock, weather, seed, tram position, speed
and notch, the camera, lat/lon, a review-mode link to the place and the deployed version. The record is
stored as `report-<date>-<time>-<code>`; the id is shown so it can be quoted in chat. It goes into the
same store as the review answers: on the test host it comes back through `autodeploy.py` as
`reports/reviews/report-….json` and `.jpg` in the deploy checkout; locally `serve.py` writes it there
directly. Without a server the record is downloaded as a file instead.

**Street bot** (where DTM streets are imported): open `index.html?line=22&bot` and start a shift. The
bot drives every car lane and walks every footway the traffic uses (1 m steps), compares the car and
walker heights with the triangles actually drawn and the DTM area class under the wheels, and lists
the places that look wrong, worst first: kerb steps, wheels on a sidewalk, height jumps, tilted cars,
floating or sunken cars and walkers, gaps in the surveyed streets, bumpy footways. Click a row (or
`n` / `b`) to fly there; arrows orbit, `+` / `−` zoom; coloured posts mark every place.
`window.streetBot` holds the result (`stats`, `findings`, `raw` samples). One run takes about a minute.

Code: GNU GPL v3 ([LICENSE](LICENSE)). Assets: [ASSETS.md](ASSETS.md) (the detailed T3 model is CC BY-NC 4.0). Data sources and attribution: [NOTICE.md](NOTICE.md).

Data © OpenStreetMap contributors (ODbL); timetable PID GTFS, data.pid.cz (CC BY 4.0);
terrain ČÚZK DMR 5G (CC BY 4.0); 3D buildings, retaining walls and trees: data base © IPR Praha (CC BY 4.0).
