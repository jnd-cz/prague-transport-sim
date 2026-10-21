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
```

The script finds the line's OSM route relations by `ref`, takes the GTFS direction-0 headsign
with the most trips on the service date (override with `--headsign`), checks that the GTFS stops
lie on the chosen OSM route, and writes `data/lineN.json` plus the menu index `data/lines.json`.
Downloads are cached in `raw/` (line 22) and `raw/lineN/` (other lines). Built lines: 9, 17, 22, 23.

Then, optionally, import the Geoportál Praha data for the line (recommended):

```bash
python -I tools/geoportal.py --line 22
```

This fetches, for the corridor 110 m either side of the route, the IPR Praha LOD2 3D buildings
(I3S scene service: real roof shapes, absolute heights matching the terrain), retaining walls with
their heights and the city tree register (individual trees and tree rows). It writes
`data/lineN.geo.json` and the quantised building geometry `data/lineN.bld.bin` (2.6–4.6 MB per
line). Without it the game falls back to extruded OSM footprints. Underpasses and tunnels on the
route (OSM `tunnel`/`covered`/negative `layer`) are spanned in the track profile.

Expects `raw/PID_GTFS.zip` (download from https://data.pid.cz/PID_GTFS.zip). Terrain comes from the
ČÚZK DMR 5G ImageServer (`exportImage`, cached as `raw/terrain.tif`). Writes `data/line22.json`.
The service date is a constant at the top of the script.

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
- Passengers: an on-board counter (normal capacity 110, crush 160). Demand follows the time of day
  — morning (7–9:30) and afternoon (15:30–17:30) peaks bring crowds, nights are quiet; a packed car
  boards slowly and a full one leaves people for the next tram.
- Stops from GTFS with real departure times. Stop at the sign, open the doors, wait for boarding and
  depart on time; early departures cost the most. Request stops (✋) can be passed when nobody waits.
- Switches: pass under the overhead contact (yellow plate, white sign with a black triangle) drawing
  current to set the turn, or coasting to go straight. Switches whose contact would fall within 60 m
  after a stop are radio (IRC) switches (white sign with a radio symbol): select the direction with
  Q / R / E (left / straight / right) within 80 m — each press sets the next radio switch not yet set —
  or tick "Automatic IRC switches". The red LED arrow before each switch shows the blade position and
  blinks while the switch is locked. If you got it wrong, stop and use the crowbar (X).
- Stops: the tram counts as at the platform when its front is between 20 m before and 12 m past the
  stop sign; within 3 m of the sign earns a precision bonus.
- Prague tram signals (four lamps: three on top, one below): the two outer top lamps = stop; top middle +
  bottom = go straight; top left/right + bottom = go left/right; a blinking GO aspect means it is ending.
  The call signal below shows three LED bars (\ | /): the bar of the coming direction lights orange
  once the tram is detected and blinks just before GO. Distant signals with a
  yellow "P" plate stand before signals hidden behind curves. Tram priority and cross traffic.
- Interlaced track in Letenská (under the building near Malostranské náměstí): both directions share
  ~65 m of track, detected automatically from the two OSM route relations. Signals at both ends grant
  the section to one direction at a time, return to STOP behind the entering tram, and hold the other
  side until the section is clear plus 6 s clearance. Oncoming trams obey it.
- Signs: classic red Prague stop signs, speed limit boards (rychlostník), contact and radio-switch
  signs, dangerous gradient boards.
- Traffic: other trams ahead on the same track (they stop at stops and red signals: keep your distance)
  and oncoming on the opposite track, cars in the street lanes beside the tram (following the real road
  geometry and one-way streets) and on the surrounding road network (continuing across junctions),
  pedestrians on footways and sidewalks who keep off the tracks. Everything fades in and out. Obstacles: parked cars fouling the track (ring the bell) and
  pedestrians crossing.
- Terrain: the track corridor is carved into the lidar terrain; retaining walls where the line is cut
  into a hillside (Chotkova), Most Legií on a deck with piers. OSM track geometry is smoothed into curves.

## Autopilot

Tick "Autopilot — just watch the ride" in the menu, or press **O** during a shift. It drives like the
headless test bot: plans speed from limits, stops, signals, obstacles and the tram ahead, picks the
notch from the forces needed on the gradient, works the doors, departs on time, rings the bell, sands
on slippery rail, sets IRC switches and coasts or powers under contacts. Press **V** for the outside
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

Data © OpenStreetMap contributors (ODbL); timetable PID GTFS, data.pid.cz (CC BY 4.0);
terrain ČÚZK DMR 5G (CC BY 4.0); 3D buildings, retaining walls and trees: data base © IPR Praha (CC BY 4.0).
