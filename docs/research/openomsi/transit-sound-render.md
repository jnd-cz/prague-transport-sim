# openOMSI: transit, sound, rendering, weather and multiplayer (#520)

openOMSI read at commit `b2dc640b` (2026-11-12), licence `AGPL-3.0-only` (its workspace `Cargo.toml`). Paths
are under its `crates/` unless they start with `docs/` or `tools/`. Our side: main at 619e0e9. The texture
budget and tile streaming are in [map-and-streaming.md](map-and-streaming.md); the vehicle scripts and the wire's
sounds in [vehicles-and-wire.md](vehicles-and-wire.md).

## Transit: timetable, duties, stops, passengers

**What openOMSI does**

- **Timetable data** (`omsi-timetable/src/lib.rs`): a line holds *tours* (one vehicle's day of trips); a trip
  lists its stations and *profiles* (a time factor, hand-set times per stop). The newer `transport/routes.cfg`
  (`omsi-transit/src/routes.rs`, `docs/TRANSPORT_FORMATS.md`) gives a service as segments plus `headway`,
  `from`, `to`, `days`; times come from length, speed (trams 50 km/h by default), accelerating, braking and
  `dwell` (30 s). A depot `gate` sends the first departure out at a yard pace of 8 m/s at most.
- **Running it** (`omsi-sim/src/timetable_run/sim.rs`, `sim/dispatch.rs`, `sim/choice.rs`): a tour keeps one
  vehicle all day, so the vehicles of the next 25 min are known and loaded ahead; a set undrawn for 90 s is freed
  (`docs/ARCHITECTURE.md`, Memory). At a terminus the bus waits for its tour's next trip when that leaves within
  30 min (`TOUR_LAYOVER_MAX`), else it goes.
- **Departure boards** (`sim/boards.rs`): per stop the trips due within 2 h, 20 a page; a bus on the road shows
  its time plus its delay, growing once its next stop is overdue; stops away, load, "last trip of the line".
- **Passengers** (`omsi-sim/src/people/pax.rs`, `pax_task.rs`, `populate.rs`), each a person with a task:
  - they turn up for a trip from 15 min before it is due to 15 min after (`PAX_SPAWN_AHEAD`, `PAX_LATE_WAIT`); a
    stop in range gains one every 10–15 s up to its `pass_enter` mean × a random factor × the density × the
    share of trips due; with no trip due, nobody;
  - a destination drawn by weight among the stops the trips reach, as likely as people get off there;
  - a seat or standing place reserved before walking to the door (none free: nobody boards); a shut door asked
    for and given up after 25 s (`DOOR_GIVE_UP`); 1 s at the validator; the stop requested at a random point
    between departure and approach;
  - transfers (`try_connection`): a set percentage, at most two, to a stop within 80 m over walkable ground;
  - no avoidance: somebody within 0.6 m in front stops them.
- **Runners** (`people/runners.rs`): 5 % per bus at a stop near the player; out of sight 25–60 m along the
  pavement, before the stop (running once the bus passes within 25 m) or beyond it; 3.0–3.6 m/s; a timetable bus
  waits 12 s at most; left behind they stand 2 s and walk back.
- **Announcements** (`timetable_run/announce.rs`): "next stop" on leaving, "arrived" at the stop.
- **Career** (`omsi-career/src/career.rs`, `journey.rs`): late over 180 s, early over 120 s; a driving penalty
  moved by jolts (over 3 m/s² across, 5 m/s² along) and pedal see-saws, worn down by km / 30; comfort as the
  share of riders without a complaint; a journey log per stop; a clock that follows the device (`real_time.rs`).

**What we do**

- Timetable: the PID GTFS trips of the service date (`tools/build_line.py` l. 943–953), through-running pairs by
  `block_id` (9 → 10, l. 468; `src/game.js` l. 115); run numbers by chaining over measured layovers (#26; #103:
  medians 13–22 min, max 56). The menu offers the trip next due (`src/main.js` l. 460–472).
- Stops (`src/game.js` `_initStops` l. 158–193): `waiting` drawn once at load from `demandAt` (l. 28–37) × a
  central factor (l. 166), `ambient` people for other lines (l. 180), `alightFrac` per stop. Exchange: 3 doors ×
  1.1 people/s per car, × 0.45–1 when crowded (l. 1357–1358).
- Runners (l. 1204–1242): 35 % of stops get 1–3, at 3.4–4.0 m/s from behind; one left behind costs 15.
- Scoring: early from 5 s, a bonus up to 60 s late (l. 1404–1413); comfort from |a| over 1.5 m/s², jerk over
  2.2 m/s³, lateral over 1.0 m/s², weighted by the load (l. 1790–1801); `game.log` per stop.
- AI trams run no trips: dwell 12–24 s, 6–8 s while we close in, oncoming 10–20 s (`src/traffic.js` l. 1747,
  1848).

**Take or not**

1. **Passengers come for trips** → #40. Take, one step further with our data: a stop's people for a line build up
   at a rate × the time since that line's previous tram (GTFS), so a late tram finds more people and the one
   behind it fewer. Today's count (l. 166) ignores the headway.
2. **Destinations by where people get off; at most two transfers within 80 m** → #40's "transfers". `alightFrac`
   stays until #40 builds an origin–destination model.
3. **Give up at a shut door after 25 s; 1 s at the validator** → #249. The rest is in the lab's core already, in
   more detail (two streams per door, exit reservations, packing).
4. **Runners' two approaches (overtaken before the stop, coming from beyond it); AI trams holding up to 12 s** →
   #251's runner figures and #243. Our 35 % against its 5 % is a game choice.
5. **A tour keeps its vehicle; the next 25 min of vehicles loaded ahead, freed after 90 s** → #103 and #38 once AI
   trams run trips; #530 / #339 for their models. The 30 min layover cap is not taken: ours are measured per line.
6. **Departure boards with the delay carried forward** → #38 (the tiers keep delay and load); nothing before AI
   trams run trips.
7. **Times from length, speed and dwell; a service as headway + from / to / days** → not for GTFS lines; the form
   for hand-added timetables of the historic lines 4x (#26). The depot gate and yard pace → #35.
8. **Career ratings** → not taken: ours suit a tram with standing riders (1.5 m/s² against 5) and count early
   from 5 s (its 120 s). A record across shifts is the user's call (questions).
9. **Stop announcements** → only if our T3s have them (questions).

## Sound

**What openOMSI does** (`omsi-audio/src/soundset.rs`, `mixer.rs`, `mixer/render.rs`; `omsi-vehicle/src/sound.rs`)

- A loop is pitched by `rate × |variable| / reference`; a one-shot plays on a trigger. Volume: the entry's × every
  `[volcurve]` (piecewise linear, held at the ends, multiplied) × `min(range / distance, 1)` when positioned.
  Conditions compare a variable with `<> = < > <= >=`. A volcurve may read −1 (seconds since active: a fade-in)
  or −2 (how much the sound faces the listener).
- A triggered sound keeps the loudest volume its curves gave since it fired: door hits read the leaf's speed,
  0 once it stops, and were cut to a click (its issues #611, #1268, #2552).
- Views (`[viewpoint]`): in the cab the bus's outside sounds come in at `Snd_OutsideVol` (how open doors and
  windows are) through a low-pass of 500 × 40^(open / 0.95) Hz (`cab_lowpass_hz`: 500 Hz shut, none from 0.95);
  other vehicles heard from a cab at × (0.2 + that share). An articulated part has its own set (`parts`).
- 200 voices (`MAX_VOICES`): over it the nearest are kept by distance, not loudness (which flickered at the edge);
  `[important]` and unpositioned voices never cut; cut voices keep advancing so a loop returns in phase. Pan at
  most 5 dB; Doppler on positioned loops only, never the player's own vehicle (frame jitter became flutter).
- `spec_random`: a value fixed by the fleet number picks a vehicle's optional sounds (one bus always rattles).
- Clips unused for a minute leave the cache (140 MB). The trolleybus gear's sounds are synthesised from noise
  and tones, replaced by a vehicle's file on the same trigger (`omsi-audio/src/trolley.rs`).
- **Soundscape** (`omsi-soundscape/src/place.rs`, `rules.rs`, `voices.rs`, `pack.rs`; `tools/ambience/`):
  - the place around the listener from the tiles: built-up share and height within ~150 m, trees (crown over
    distance²), open land, water within 150 m, roads by speed, tracks within 40 m, the nearest wire, a tunnel,
    people within 40 m, objects filed as church, school, workshop;
  - 126 slots (49 beds, 46 events, 31 points at objects, 4 echo impulse responses) weighted by place, hour, the
    sun's height, day of the year, rain (light to heavy, on asphalt, on leaves, downpipes, drips), snow, wind (in
    trees; in wires within 8–30 m at 6–12 m/s), temperature and the day's kind (Sunday bells, shop hours);
  - a bed crossfades between 45 s takes (4 s overlap, 1.5 s glide); beds at −27 LUFS, events by their loudest 3 s;
  - the pack: CC0, CC BY, public-domain and one CC BY-SA recordings cut by `build_pack.py` into under 300 MB of
    32 kHz MP3, credited per take, tagged by country (`de`, `uk`); four takes labelled CC0 come from an author
    who forbids redistribution (its README).

**What we do**: `src/audio.js` synthesises everything into one gain (l. 15–113): the motor by speed and current
(l. 145–151), rolling noise, the motor-generator by its rpm from `src/electric.js` (l. 161–166), the pilot motor
and contactors (l. 167–175), squeal under 20 m radius (l. 154), joints every 18 m (l. 178–185), bell, buzzer.
Nothing is positioned; cab and street sound the same; the street has no sound of its own. #528 (in work) brings
events and a basic pack; #550 curves, conditions, positions, views and an AI subset, after OMSI's `sound.cfg`
(`docs/decisions/2026-11-10-vehicle-packages.md` §5).

**Take or not**

1. **A triggered sound keeps its loudest curve value** → #550, as a rule; a door or frog sound on a speed curve is
   otherwise cut off.
2. **Curve inputs "seconds active" and "facing"** → #550, two built-in parameters.
3. **The cab low-pass by how open the cab is, other vehicles at a share** → #550's `cabin` default, driven by our
   `doors` (0–1): the street comes in brighter at every stop. 500 Hz and 0.2 are starting values, tuned by ear.
4. **The voice cap by distance, our tram never cut, cut voices keeping time** → #550's AI subset (a gain of 0 on a
   running source).
5. **The distance law** `min(range / d, 1)` is `PannerNode` with `distanceModel: 'inverse'`, `refDistance` = the
   pack's `radius`, `rolloffFactor` 1 → #550. Doppler not taken (Web Audio has none).
6. **Optional sounds fixed by fleet number** → #550 (`pick: "byNumber"`) with #527's numbers.
7. **Synthesis replaced by a file on the same event** → #528's design already.
8. **The soundscape** → new issue P1. Our build holds what `place.rs` sums (buildings, trees, water, tracks, wires,
   tunnels), so the place table can be built offline along the route. The rules carry over as weights; recordings
   come from their original pages, with Czech takes for speech, bells and sirens, without the four withheld.
9. **Lock-free mixer rings, radio, voice chat** → not taken: the browser mixes on its own thread; a tram has no
   radio for its riders.

## Rendering and frame time

**What openOMSI does** (`omsi-render/src/scene/upload.rs`, `scene/lod.rs`; `omsi-app/src/view_sync/people.rs`;
`omsi-texture/src/pbr.rs`; `docs/ARCHITECTURE.md`, `docs/USER_GUIDE.md`, `docs/performance-th-wald.md`)

- **Only changed instances are rewritten** (`Scene::changed`); a full rebuild only when instances are added or the
  origin moves. With parallel AI scripts and a 50 m lane grid: Spandau with traffic ~34 → ~240 fps.
- **LOD by screen size**: diameter over distance as a share of the vertical field of view, the same level for the
  picture, its shadows and the ray-traced scene.
- **People posed by distance**: every frame within 45 m in view (and within 30 m), every 2nd to 90 m, 3rd to
  160 m, 6th beyond, 12th out of view, half as often standing beyond 20 m, spread by index. Every other frame at
  12–30 m made walkers step and planted feet shiver.
- **Far detail**: an AI vehicle's display textures beyond 50 m are one texel of their mean colour, back within 40 m.
- **Batching**: short spline pieces of one material joined in 48 m cells: 17.8 → 36.7 fps, 31 221 → 6 135 batches.
- **Graphics modes**: Vanilla (OMSI 2's picture), Vanilla+ (default: sun shadows, ambient occlusion, grain, snow,
  drops), Enhanced (physically based, computed atmosphere, auto exposure), Enhanced+ (ray tracing within 420 m);
  presets Low…Ultra; volumetric clouds 0.8 ms, street light 0.5 ms (M4, 1080p); an optimiser turns street light
  off when the GPU is the limit.
- **PBR maps** beside the diffuse texture by suffix (`_nn`, `_rr`, `_orm` …), packed into one occlusion /
  roughness / metalness picture; normal maps uncompressed (DXT1 ruins them).

**What we do**: world geometry merged per material in 350 m chunks (`src/world.js` l. 11, `ChunkedGeometry`
l. 141–191), sent once and its JS copy dropped (`src/main.js` l. 213–230); people in three levels with hysteresis
(full 40/46 m, animated 80/88 m and 64 at most, one instanced far batch: `src/people.js` l. 19); rigged trams'
lighter level at 50–60 m (`docs/vehicles.md` l. 144); instance buffers rewritten whole each frame
(`src/game.js` l. 1852, `src/traffic.js` l. 1584, `src/people.js` l. 248); one quality (pixel ratio ≤ 1.75,
antialias: `src/main.js` l. 142–143); frame time by `tools/frametime.py` and on players' machines `src/perf.js`.

**Take or not**

1. **Batching in spatial cells** → done (350 m chunks); #30's tiles keep one mesh per material per cell.
2. **Far figures posed less often, never every other frame within 30 m** → #251: the animated figures beyond 45 m
   every 2nd frame, spread by index; measured with `tools/frametime.py` at line 17's busiest stop.
3. **Only changed instances written** → when #250's cars and the crowds grow (a few hundred instances today); a
   `BufferAttribute` uploads a part of itself through its update ranges.
4. **LOD by screen size** → #31: one rule for buildings, vehicles and people instead of a distance per kind.
5. **ORM packing** → #308: three.js reads occlusion from red, roughness from green, metalness from blue, the same
   order, so ambientCG's three maps make one file per material. Normal maps stay uncompressed.
6. **Modes, presets, an optimiser** → idea only for #350 / #485; the user (2026-11-06, #350): "not to
   prematurely optimize".

## Weather

**What openOMSI does** (`omsi-weather/src/`, `docs/WEATHER_REGIONS.md`): a physical column model (planetary waves
of 4–10 days, surface energy balance, boundary layer); a cycle changing the weather every 25–60 min to a
neighbouring one; or real weather (METAR, Tomorrow.io), blended over 60 s. Road wetness (`conditions.rs`): rain
soaks at its rate / 180 per second, sunshine dries in 1200 s. Condensation (`condensation.rs`): the cabin's heat
and vapour (45 g an hour per person, more with wet coats) against the glass, the defroster clearing the windscreen
from below. Seasons with a phase, each plant taking the other look by its own id (`season_phase.rs`).

**What we do**: four weathers from the menu, fixed for the shift (`src/main.js` l. 197–252); shader uniforms for
wet, snow and autumn (`src/weather.js` l. 1–23); grip per weather (`src/tram.js` l. 40, #266); the outdoor
temperature hourly from Open-Meteo (`src/main.js` l. 707–711); the cabin climate with the T3's heaters
(`src/game.js` l. 1474–1501).

**Take or not**

1. **Weather that changes in a shift, a wetness that soaks and dries** → new issue P2: #266 finds the first minutes
   of rain on a dry rail the worst grip, which a fixed weather never gives. Precipitation comes from the same
   Open-Meteo request as the temperature.
2. **The physical model** → not taken: we have the real weather.
3. **Condensation** → new issue P3: a cold cab full of wet riders fogs, and the cab heater clears it.
4. **Season phase** → not now: autumn is a weather with its own grip (#285, #474).

## Multiplayer and the frame

- **LAN state** (`omsi-net/src/wire.rs`, `vars.rs`, `docs/TRAFFIC_TABLE.md`): a vehicle bit-packed into 50–70
  bytes up to 20 times a second, every field fixed-width and clamped; other variables as changes 10 times a second
  plus key-frame slices; AI traffic as table rows written after each step (id: 12-bit slot + 8-bit generation, a
  freed slot rests 30 s). → No multiplayer on our roadmap. The table is the shape #228's `TrafficView` and #37's
  snapshot need: rows in drawing units, a generation per id so a stale reference never names the next vehicle.
- **Fixed step** (`docs/ARCHITECTURE.md`, Threading): 60 ticks a second, at most 4 a frame; view, sound and picture
  once after the last tick; its AI traffic still differs by frame rate because handover and spawning run per frame.
  → #173 and #37: our step is `min(0.05, frame time)` (`src/main.js` l. 1010); spawns (runners, walkers, cars)
  must run on ticks too.
- **Events instead of renderer calls** (`TrafficEvent`, `BodyOp`, `FrameSnapshot`, `SoundFrame`) → #227 and #228.

## Where ours is already more realistic (question 2)

- **Timetable and stops**: the day's GTFS times, through-running pairs and measured layovers; the front at the stop
  sign, zones from OSM platforms, Vienna-type stops. openOMSI: hand-made tours, a 30 min cap, a stop box.
- **Scoring and grip**: tram comfort thresholds and early departures from 5 s; measured adhesion (#266). openOMSI:
  a bus's jolts of 3–5 m/s², ±120–180 s, road wetness.
- **Sound**: ours follows the T3's electrics (the motor-generator with the wire, the pilot motor, the contactors);
  openOMSI has no tram sound of its own.
- **Boarding**: the lab's two streams per door and exit reservations (#249) against people who do not avoid each
  other.

## How to take it (question 4)

openOMSI is `AGPL-3.0-only`, ours `AGPL-3.0-or-later` (#518): a ported file would stay AGPL-3.0-only under
openOMSI's copyright, against AGENTS.md's header rule. Everything above is taken as ideas and numbers, written as
our own code with the openOMSI file named in a comment; no port is proposed. Recordings come from their original
pages under their own licences, credited per take as `tools/ambience/CREDITS.md` does; never openOMSI's built pack,
and nothing of OMSI 2.

## Proposed new issues

**P1. City ambience: beds and one-shots chosen by what stands around the tram, the hour, the season and the
weather.** lane:assets, Backlog, blocked by #528; feeds #70. Now: no sound but our tram. What: a place table along
the route built offline (built-up share and height within 150 m, trees, water, tracks within 40 m, wires, tunnels,
stop crowds); slots weighted by place, hour, day of the year, weather and people near; CC0 / CC BY recordings
credited per take, with Czech speech, bells and sirens; heard through #550's cab filter. Done when line 17's slot
weights at named places and hours match a test's table and the credits list every take. Checks: a page test of
the slot choice; `tools/frametime.py` with the ambience playing.

**P2. Weather that changes during a shift: the rail wet from the first drops, drying after.** lane:sim, Backlog,
blocked by #266. Now: weather fixed per shift (`src/main.js` l. 242), grip per weather (`src/tram.js` l. 40).
What: a wetness 0–1 soaking with the rain's rate and drying over ~20 min (openOMSI's rates as a start); grip from
wetness and #266's onset curve, lowest in the first minutes; the look and the precipitation following; Open-Meteo's
hourly precipitation for "real Prague" or a cycle, changes blended over 60 s. Checks: u3, redruns, traffic on all
lines, seeds 1–5, `--compare`; `stops`; `tools/test_traction.py`.

**P3. Fogged windows from the cabin climate.** lane:sim, Backlog, best after P2 (wet coats). Now: `_updateClimate`
(`src/game.js` l. 1474–1501) holds the saloon and cab temperatures; nothing on the glass. What: vapour from riders
(45 g an hour each) and the driver, the glass between cab air and airstream, a film below the dew point, the cab
heater and its flap clearing the windscreen from below; drawn on the cab glass. Checks: a climate test (autumn
evening, full, heater off: fogged within minutes; dry winter, empty: clear); a smoke drive (`--checks u3 --seeds 1`).

## Questions for the user

In the [README](README.md), with the other notes' questions.
