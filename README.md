# Tatra T3 — Prague trams (browser prototype)

Arcade tram driving in a 3D Prague built from real data: OpenStreetMap track network, buildings,
roads and greenery, ČÚZK DMR 5G lidar terrain (10 m grid), and the PID GTFS timetable for
line 22 (Bílá Hora 382 m → Malostranská 189 m → Náměstí Míru 246 m → Zahradní Město 237 m).

## Run

```bash
python tools/serve.py 8740
```

Open http://localhost:8740. There's no build step: plain ES modules, with Three.js loaded from a CDN.

## Rebuild the line data

```bash
python -I tools/build_line.py --line 22 --headsign "Zahradní Město"
python -I tools/build_line.py --line 23            # any Prague tram line
python -I tools/build_line.py --line 17 --refresh  # re-download from Overpass
python -I tools/build_line.py --line 9 --then 10   # a vehicle run: 9, continuing as 10 at the terminus
```

With `--then`, the route is not taken from the OSM relations (they describe the regular route, not
diversions) but from the PID GTFS shapes of the two trips, matched onto the whole Prague OSM tram
network; arrivals of the first line and departures of the second at the shared terminus are paired
in time order (PID GTFS has no `block_id`). The current line 9 is such a run: Sídliště Řepy →
Nákladové nádraží Žižkov as 9, back to Řepy via Vinohradská as 10 (track repairs, autumn 2026).
Stop platforms come from OSM (`public_transport=platform`) for all lines.

The script finds the line's OSM route relations by `ref`, takes the GTFS direction-0 headsign
with the most trips on the service date (override with `--headsign`), checks that the GTFS stops
lie on the chosen OSM route, and writes `data/lineN.json` plus the menu index `data/lines.json`.
Downloads are cached in `raw/` (line 22) and `raw/lineN/` (other lines). Built lines: 9, 17, 22, 23.

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
city district, CC BY 4.0) — so far imported for line 22 in Praha 2 and Praha 10 (pilot):

```bash
python -m pip install --user pyproj shapely
python tools/dtm.py --line 22 raw/dtm/<..._500089_..._ZPS_OPL.gpkg> raw/dtm/<..._500224_..._ZPS_OPL.gpkg>
```

Then, optionally, the **street model** (pilot, smooth streets with fixed level steps, meshed
offline) for a stretch of the line, by route position in metres:

```bash
python tools/streets.py --line 22 --from 10850 --to 12900
```

It rewrites `data/lineN.dtm.json` (rerunning starts from the survey again; rerun it after `dtm.py`).

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

## Gameplay

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

`tools/autopilot.js` drives the game headlessly to check the rules. In the browser console:

```js
const { autopilot } = await import('/tools/autopilot.js');
autopilot(0, 99, { obstacles: 'normal', weather: 'rain' });
```

**Lints** (PLAN.md §2): each check counts one kind of problem over the whole line. With the dev server
(`tools/serve.py`, which saves the reports) and a shift started on the line:

```js
const { lint } = await import('/tools/lint.js?v=' + Date.now());
await lint();               // consist at every stop, signals in platforms, trees in buildings, bridges
await lint({ bot: true });  // + the street bot where DTM streets exist (about a minute)
```

Reports go to `reports/lineN.json`. Compare with the committed baseline (exit code 1 if a count rose):

```bash
python tools/lint_report.py
```

After an intended improvement, run it with `--accept` to make the current reports the new baseline.
Facts from the user that checks are scored against live in `data/truth.json`.

**Street bot** (where DTM streets are imported): open `index.html?line=22&bot` and start a shift. The
bot drives every car lane and walks every footway the traffic uses (1 m steps), compares the car and
walker heights with the triangles actually drawn and the DTM area class under the wheels, and lists
the places that look wrong, worst first: kerb steps, wheels on a sidewalk, height jumps, tilted cars,
floating or sunken cars and walkers, gaps in the surveyed streets, bumpy footways. Click a row (or
`n` / `b`) to fly there; arrows orbit, `+` / `−` zoom; coloured posts mark every place.
`window.streetBot` holds the result (`stats`, `findings`, `raw` samples). One run takes about a minute.

Data © OpenStreetMap contributors (ODbL); timetable PID GTFS, data.pid.cz (CC BY 4.0);
terrain ČÚZK DMR 5G (CC BY 4.0); 3D buildings, retaining walls and trees: data base © IPR Praha (CC BY 4.0).
