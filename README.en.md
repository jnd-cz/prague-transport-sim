# Tatra T3 — Prague trams

**English** · [Česky](README.md) · [For developers](DEVELOPING.md) · [Your own vehicles](docs/vehicles.md)

Tram driving on a Tatra T3 in a 3D Prague built from real data, on lines 9, 17, 22, 23 and 37 (lines 17
and 22 with their surveyed streets): OpenStreetMap (track network, roads, greenery), the Prague Digital
Technical Map (surveyed streets, the transport layer DI for the track), IPR Praha 3D buildings and
bridges, lidar terrain, and the PID GTFS timetable.

## Run

```bash
python tools/serve.py 8742
```

Open http://localhost:8742. There's no build step: plain ES modules, with Three.js loaded from a CDN.

A fresh clone first needs the game data: [Set up](DEVELOPING.md#set-up).

<!-- help -->

## Gameplay

### Your shift

- Line selection in the menu (each line loads its own world). Stop posts list the day lines serving
  each stop; trams of those lines run ahead of you.
- Stops come with real departure times. Open the doors, wait for boarding and depart on time; early
  departures cost the most. Request stops (✋) can be passed when nobody waits.
- You serve a stop when the tram stands in the place set by its front:
  - **At a platform at least 15 m long,** where the data has one: the whole set stands alongside it, its rear
    at most 3 m short of the platform's start and its front at most 4 m past its end. A second set can serve
    the stop behind the first, on a longer platform even two 2×T3 sets in a row (about three stops in four).
    At a platform shorter than the set, the front between 8 m before its end and 4 m past it is enough.
  - **Elsewhere:** the front between 20 m before and 12 m past the stop sign.
  - **A signal right after the stop:** the front at most 0.5 m before it.
- The stopping point is the stop sign: within 3 m of it earns a precision bonus of 15 points. Stopping a little
  past it happens in reality too and people still get on and off, so up to 4 m past the sign costs nothing;
  more than 4 m costs 20 points, even though the stop is served. Stopping further back in the allowed place costs
  nothing.
- Passengers: an on-board counter (normal capacity 110, crush 160 per car). Demand follows the time of day:
  morning (7–9:30) and afternoon (15:30–17:30) peaks bring crowds, nights are quiet; a packed car boards
  slowly and a full one leaves people for the next tram.
- Line changes: a trip can change its number along the line's route and at a terminus (line 9 continues as 10 at Nákladové
  nádraží Žižkov): everybody gets out, the route boxes and the HUD switch, the tram departs as 10.

### Keys

| key | what it does |
|---|---|
| `W` / `↑` | towards drive (steps J1–J5; advanced: a tap to the next step, held on) |
| `S` / `↓` | towards brake (B1–B5) |
| `Space` | emergency and track brakes (held) |
| `N` or `0` | both pedals released (coast) |
| `1`–`5` | a drive step; with `Shift` a brake step |
| `R` | park and unpark the brake pedal (advanced controls) |
| `A` | sand (held) |
| `D` | doors |
| `B` | bell |
| `Y` | the **Výhybka** button: current through the contact (held) |
| `C` | heating cut-out (held under a contact, to coast through) |
| `X` | set a switch with the switch iron (tram stopped) |
| `H` / `K` / `F` | saloon seat heaters / cab heater / waste-heat flap |
| `Q` / `E` or `←` / `→` | look out of the left / right window (held) |
| `G` | zoom the cab view three times, as a driver looks into the distance: a sign reads at 75 m (held, also while paused) |
| `Z` | right mirror on and off |
| `,` / `.` | indicators left / right (again: off); given before a turn at a junction and at a stop where passengers cross a car lane (right, from braking into it until pulling away) |
| `/` (on a Czech keyboard `-`) | hazard lights |
| `L` | high beams: held, a flash; with `Shift`, on and off |
| `V` | cab or outside view |
| `O` | autopilot on and off |
| `M` | sound on and off |
| `P` / `Esc` | pause |
| `F9` | write to us (feedback) |

The dead-man pedal, when it is on in the menu, is `Shift` held.

### Driving

- **The T3's TR 37 equipment:** two pedals without detents. A drive step (J1–J5) sets a current, which the
  accelerator holds by stepping through its 99 positions (resistors to 75, field weakening at 80–95); a
  brake step (B1–B5) sets a brake current; the electric brake fades below ≈6 km/h, where the shoe brakes
  come in (partly on steps 3–4, fully from step 5 or parked); the end of the brake stroke adds the track
  brakes. An open door or a brake pedal off zero cuts traction. Right after driving the brake builds
  slowly, and step 5 then brings the shoes in at speed: wait 2–3 s between them, for the accelerator to return
  to its base position. The dashboard's pedal
  bar shows the pedal (drive up, brake down, P parked) and the accelerator.
- **The accelerator** (*zrychlovač*, the yellow bar beside the pedals, position 1 at the bottom, 99 at the top) is
  turned only by its pilot motor, about 20 positions a second at most, and steered by the limiting relay from the
  current: driving it cuts out resistance, the faster the higher the step. Pedal off it holds a small preparation
  current, so it comes back as the speed falls (about 31 at 20 km/h, 50 at 30 km/h) and rises again going
  downhill; braking it holds the step's current: the higher the step, the lower it stands. High means little
  resistance when driving and much when braking.
- **Power:** the voltage on the wire falls with your current, your distance from the substation and the current of
  other trams on the same feed (the line's resistances are an estimate, the substations from OSM). On the resistors
  that does not change the force, the accelerator only stands higher; above them a weak wire means less pull and a
  lower top speed. The electric brake does not care. The motor-generator and both fans share one shaft and its
  series motor runs with the voltage: so the tone falls as you pull away, and falls too when the shoes' release
  magnets load the dynamo; the regulator holds the on-board 26 V. The info panel shows the voltage, the
  substation, the on-board voltage and the rpm.
- **Controls** (menu): *Simple* moves a lever by steps (W/S, 1–5, Shift+1–5) and works the pedals as a
  driver would, parking whenever the car stands; *Advanced* moves the pedals themselves (a tap to the next
  step, held on at 20°/s; held keys stop at brake step 5) and R parks and unparks the brake pedal; after
  parking the shoes release fully only with the drive pedal. Space is the emergency stop in both.
- An empty car accelerates at 0.6–1.8 m/s² by step, a full car more slowly; gravity on gradients (Chotkova
  ~7 %), curve resistance, rolling back when the brake is released on a hill, lateral comfort in curves.
- Weather: dry / rain / autumn leaves sets wheel–rail adhesion. Too much power spins the wheels, too much
  brake locks them (flats). Hold A to sand; the emergency brake sands automatically and its magnetic track
  brakes don't depend on adhesion.
- Speeds: 50 km/h unless the track's posted speed says otherwise, up to the T3's 65 km/h. Each curve allows
  √(a·R) with 0.8 m/s² unbalanced lateral acceleration, at least 15 km/h unless the track is posted lower. A facing
  switch is 15 km/h from its blades to its frog, whichever way it is set, until the rear of the tram has passed.
  A turning loop is 15 km/h from the switch into it to the switch out of it. The front passes the sign of a stop
  where the train does not stop at 30 km/h at most (a point limit: the train may speed up once the front is past).
  Curves on dedicated track are banked (up to 100 mm cant, level at stops and near the termini); the tram and the
  view lean into them.
- Sets: most lines run two-car T3 multiple-unit sets (2 × 15.2 m over couplers, both cars powered, six
  doors); line 23 runs a single heritage car. "Set" in the menu overrides it. Each car follows the track
  on its own bogies.

### Switches

- Every facing switch has an overhead contact (yellow plate, white sign with a black triangle), worked by
  the pantograph: pass under it drawing current to set the turn, or coasting to go straight — also right
  after a stop, at a signal or on a hill (judging that is part of the driver's skill).
- Current also flows with the **Výhybka** button (Y, as on T3SUCS: only with drive off and the accelerator up to
  position 30, about 20 km/h) and — in winter — through the heating,
  unless you hold the heating cut-out (C) while coasting under the contact.
- Contacts are ~22 m before the switch but never where a tram stands with its pantograph at a stop or
  signal. Trailing switches (where tracks join) need nothing; diamond crossings are not switches.
- The red LED signal before each switch shows the blade position (an arrow left or right, a vertical bar for
  straight) and blinks while the switch is locked. If you got it wrong, stop and use the switch iron (X).
- The speed switches R07 (Kotlářka, line 9) and R09 (Podolské nábřeží, line 17) have their own signals: the
  number plate, the call signal, the entry sleeper signal and the white LED arrow over the number. Without
  registration the number stays dark and the switch is passed like any other, at 15 km/h.

### Signals

- Prague tram signals (four lamps: three on top, one below): the two outer top lamps = stop; top middle +
  bottom = go straight; top left/right + bottom = go left/right; a blinking GO aspect means it is ending.
- The call signal below shows three LED bars (\ | /): the bar of the coming direction lights yellow once
  the tram is detected and blinks just before GO. Distant signals with a yellow "P" plate stand before
  signals hidden behind curves.
- Junctions: each signal belongs to a junction controller with a fixed cycle (trams straight in both
  directions, a turning phase, the cross street) and tram priority; oncoming trams obey it. Cross traffic
  drives along the real crossing street and stops at its line while the tram has GO.
- Interlaced track in Letenská (under the building near Malostranské náměstí): both directions share ~65 m
  of track. Signals at both ends grant the section to one direction at a time, return to STOP behind the
  entering tram, and hold the other side until the section is clear plus 6 s clearance. Oncoming trams
  obey it.

### Heating

Heating follows the DPP T3SUCS manual: saloon seat heaters 0/1/2 (H: three seats each side / all seats),
cab heater (kalorifer) 0–3 (K: off / unheated air / half / full) and the flap that lets the accelerator resistors'
waste heat into the saloon (F). The info panel shows the outside, saloon and cab temperatures. Outside
temperature: Prague now or a fixed winter / autumn / summer day (menu). Cold passengers (< 12 °C) and heat
you caused cost points; open doors let the heat out; in summer passengers open the windows.

### Looking around

- Hold Q / E (or ← / →) to look out of the left / right window; the right rear-view mirror (Z toggles)
  shows the side of the set and the doors. It grows with the window and keeps its field of view.
- **Outside view** (V): the camera orbits the tram. Drag to turn and tilt it; the wheel or two fingers
  zoom; a double click brings it back behind the tram.

### Traffic

- Other trams run ahead on the same track (they stop at stops and red signals: keep your distance) and
  oncoming on the opposite track; each carries a line that really serves that stop and turns off (fades
  out) after the last stop it shares with your line.
- Cars drive in the lanes beside the tracks, following the real road geometry and one-way streets, and on
  the surrounding road network, continuing across junctions. They give way at junctions, keep their
  distance, queue behind trams on shared track and stop for walkers; trams stop behind cars on their track.
- Pedestrians walk footways and sidewalks and keep off the tracks. Everything fades in and out.
- Obstacles: parked cars fouling the track (ring the bell) and pedestrians crossing.

### The city

- Terrain: the track corridor is carved into the lidar terrain; retaining walls where the line is cut into
  a hillside (Chotkova), Most Legií on a deck with piers.
- Signs: classic red Prague stop signs; the speed signs of the D 1/2 rules (a restriction in black on yellow,
  a Rychlostník in white on black, the warning triangle, the "r" of a small-radius curve, the dangerous climb
  and descent), twice their real size so they can be read on a screen. Contact
  signs. Zebra crossings are painted where they are mapped (not across the tracks). Signals and signs
  stand off the road: on catenary poles, hung from span wires beside the contact wire, or at the kerb — not
  on platforms.
- Overhead line: span wires anchored on poles at the kerb (between carriageway and sidewalk), on wall
  rosettes where a building stands close, or a bracket arm where one side has no room; closer spacing on
  curves. Street trees are kept (pruned) clear of all tracks.
- Buildings are textured by type (old tenement, panel block, church, industrial hall, glass office). Real
  3D bridges set the deck height and the clearance under structures (station canopies included).

### Menu options

- Automatic switches (the onboard computer sets every switch by radio instead of the overhead contacts);
  performance overlay (FPS, frame time, draw calls, triangles, JS heap); Performance test and Reference test (a minute
  of the autopilot on a fixed stretch, [Testing](#testing)).
- Tram model: detailed and animated (a hybrid of "Tatra T3" by SimonStrikesBack, CC BY 4.0, and "Tatra T3"
  by Jakub Vaja (conflig), CC BY-NC 4.0, both on Sketchfab; CC BY-NC 4.0): its doors, collector, brake lamps
  and track-brake shoes follow the game, the second car of a set hangs on the coupling; detailed classic
  (conflig's model alone, CC BY-NC 4.0, downloaded when picked); or the built-in simple one, with the
  dimensions and livery of the T3's general-arrangement drawing, no saloon and no moving parts, the lightest
  to draw. With it the other trams run as T3 (a silver bumper with red stripes), T3SUCS and T3M sets (the T3M
  with the resistors' box on its roof and its green route display), each type as often as its range of fleet
  numbers is long.
- Fleet number: the set you drive, such as the historic 6892 + 6921, 7269 + 7290 or 8080 + 8074, or one number
  (the second car gets a number of the same type); the game remembers it for each model. "Any" deals yours
  like the others'. No number runs twice on the street, and no other set is dealt yours.
- Livery: only for a model with liveries besides its own (none yet): its own, one of them, or "Any", dealt like the
  others'; the game remembers it for each model. Some of the other sets wear the liveries too.

### On a phone or tablet

On-screen buttons, shown on a touch screen by default and switched by 🎮 in the menu (remembered per
device; switched off, 🎮 brings them back during a shift too). They send the keyboard's keys:

- the row above the dashboard (sideways, a column at the right): ▼ brake, 0 neutral, ▲ drive (a step each), STOP (the emergency brake, held),
  and the dead-man button when that option is on;
- the left column: doors, bell, sand (held), look left / right (held), 🔍 zoom (held), view, mirror, pause;
- ⋯ for the rest: indicators ⇦ ⇨, hazard lights ⚠, high beams (a flash held, on and off), park (advanced controls), switch contact, switch iron, heating cut-out, heating,
  autopilot, sound, ✉ feedback.

On a small screen the dashboard and the top bar are smaller and the minimap is hidden. A phone held sideways has the
controller as a column at the right thumb (▲ at the top, STOP at the bottom), the other buttons in two columns at the
left and the dashboard between them.

**Full screen:** a phone asks once in the menu; with "Full screen", every shift starts in full screen, turned
sideways where the browser allows it (Chrome on Android), elsewhere the game asks you to turn the phone. ⛶ in the
menu switches it any time; the back gesture leaves it until the next start. Safari on an iPhone doesn't allow a page
full screen: the game says once to use Share ⬆ → Add to Home Screen, and started from that icon it runs full screen.

### With a gamepad

An Xbox or PlayStation pad in Chrome, Edge or Firefox; the browser shows it to the game after its first button. The pad sends
the keyboard's keys, so the keys work beside it. While a pad is connected, the dead-man pedal counts as held.
In advanced controls a trigger puts the pedal straight on its step: how fast you go from one step to another is up to
your finger. The tram starts with the parking brake on: LB releases it before the drive trigger moves the pedal.

| pad | does |
|---|---|
| right trigger | drive step 1–5, by how far it is pressed |
| left trigger | brake step 1–5, by how far it is pressed (over the right one); both released: both pedals free |
| D-pad ↑ / ↓ | a step towards drive / brake (as `W` / `S`) |
| D-pad ← / → | indicators left / right |
| A / ✕ | doors |
| B / ○ | bell |
| X / □ | sand (held) |
| Y / △ | emergency brake (held) |
| LB / L1 | parking brake on and off (advanced controls) |
| RB / R1 | look closer (held) |
| right stick ← / → | look out of the left / right window |
| Back / Share | cab or outside view |
| Start / Options | pause |
| L3 | mirror |

## Autopilot

Tick "Autopilot — just watch the ride" in the menu, or press **O** during a shift. It plans speed from
limits, stops, signals, obstacles and the tram ahead, picks the force needed on the gradient and lets the
equipment work the pedals as a careful driver (the advanced model: pulls away on steps 1–3 on the level, brakes
step by step, into a stop on one curve and without going back to the drive pedal unless a tram stands ahead,
parks while standing, steps 1–4 only within 2.5 s of driving), works the doors, departs on time, rings the bell, sands on
slippery rail, and under contacts draws current for a turn (the switch button when slow enough, otherwise a short pulse of
the drive pedal) or coasts (straight), and indicates before a turn at a junction and at stops where passengers cross a car
lane. Press **V** for
the outside view. Any controller or door key (W/S/Space/N/D/R, 0–5) takes over, in the controls chosen in the
menu; O hands back to the autopilot.

## Language

The interface and this help are in Czech or English (Settings → Language in the menu; remembered in the
browser).

## Testing

The game is in alpha: it can be driven end to end, but the world and the driving are still being built. What
helps most is how driving and the traffic feel to you.

- **What we ask:** how the controller, pulling away, coasting and braking feel; stops and the timetable;
  signals, switches and the rules; which terms don't sound like tram drivers'; what breaks the spell.
- **How to write:** ✉ Feedback (**F9**, on a phone under ⋯) pauses the game and opens a note. It adds the place
  on the line, the tram's state, the game's version and, if you like, a screenshot, so it's enough to write what
  you see and how it should be. When the game doesn't start or the graphics stop, the "Send the error to the
  authors" button sends what happened.
- **Smoothness:** a performance test in the menu drives a fixed stretch of a line by autopilot for a minute and
  shows how the game keeps up; you can send the result. Please run the Reference test at least once: always
  line 17 with the detailed model, so machines compare; the Performance test measures the line you have
  loaded. After a shift the game asks whether to send its performance summary.
- **Leave for now:** the ground and kerbs, buildings and street furniture (they come with the next layers of the
  world), the simplified cars and pedestrians, the synthesised sound, power in steps instead of current through
  the accelerator, driving in one direction only and the missing depots.
- **What is sent:** only what you send: the note and with it the place, the game's settings and version, the
  browser, graphics card, screen size and errors. No name, account or address.

## Licences

The game runs at [sim.8b.cz](https://sim.8b.cz/); its source code is on [GitHub](https://github.com/jnd-cz/prague-transport-sim).

Code and the project's own models (the built-in tram, the pedestrians): GNU AGPL v3 ([LICENSE](https://github.com/jnd-cz/prague-transport-sim/blob/main/LICENSE)). Whoever changes the game and offers it to people over a network must offer them its source code too. Other models and textures: [ASSETS.md](https://github.com/jnd-cz/prague-transport-sim/blob/main/ASSETS.md) (the detailed T3 models are CC BY-NC 4.0). Data sources and attribution: [NOTICE.md](https://github.com/jnd-cz/prague-transport-sim/blob/main/NOTICE.md).

Data © OpenStreetMap contributors (ODbL); timetable PID GTFS, data.pid.cz (CC BY 4.0);
terrain ČÚZK DMR 5G (CC BY 4.0); 3D buildings, retaining walls and trees: data base © IPR Praha (CC BY 4.0).

<!-- /help -->
