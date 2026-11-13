# openOMSI: vehicles, physics and the overhead wire (#520)

openOMSI read at commit `b2dc640b4db64a09ddfc0d00b8e78c463c81c842` (2026-11-12), licence **AGPL-3.0-only**
(`Cargo.toml` `[workspace.package]`, README "License"). Paths below are under `crates/`. Our side: main at 619e0e9.
This note answers #520's questions 1, 2 and 4 for vehicle logic, physics, the cockpit, scripts and the wire.

## What openOMSI does

**Vehicle systems are scripts** (`omsi-script/src/`). OMSI 2's `.osc` language re-implemented: `compile.rs` turns
the text into ops (RPN: push, load/store of variables, arithmetic, macros, callbacks, sound triggers), `vm.rs` runs
them on an 8-slot float stack, ten registers and an 8-slot string stack; one `Program` per vehicle type, one
`State` per instance; `constfile.rs` holds constants and piecewise-linear curves. Every system of a bus (engine,
gearbox, doors, brakes, electrics, IBIS) is a script. The engine reads `M_Wheel` (drive torque) and
`Axle_Brakeforce_*` and writes `Velocity`, `n_Wheel`, wheel and suspension variables back (`omsi-sim/src/physics.rs`
head); the host supplies system variables, callbacks and sound triggers (`omsi-sim/src/host/mod.rs`). `compat.rs`
patches known mod scripts by their text. Scenery objects may run sandboxed Lua with events (`docs/OBJECT_SCRIPTS.md`).
A model animates meshes by variables: `[newanim]` `anim_rot`/`anim_trans` on a variable times a factor (`anim.rs`).

**Rail dynamics** (`omsi-sim/src/rail/dynamics.rs`, `class.rs`), one mass per consist, sub-steps of 10 ms:
- adhesion: Curtius–Kniffler `0.161 + 7.5 / (v + 44)` (km/h) as an absolute value, 0.33 dry at a stand; ×0.7 wet,
  ×0.4 leaves or snow, ×0.2 ice (wet at or under 0 °C); sand brings it back to at least 0.85 of dry;
- drive capped at μ × weight on driven axles (spinning flagged above it); wheel brakes capped at 0.9 μ × weight,
  a sliding wheel holds 0.75 of that; the track brake is added without an adhesion limit;
- running resistance `m g (a + b v)`: tram a = 3.5 N/kN, b = 0.04 N/kN per m/s, times a start factor
  `1 + 0.8 / (1 + (v / 0.6)²)` for every class (1.8 at a stand);
- air `½ ρ (Cd A + 0.4 m² per extra car) v²`, twice in a tunnel, ρ from the temperature, headwind;
- curve resistance by Röckl, `650 / (R − 55)` N/kN from 300 m, `500 / (R − 30)` under it
  (R held ≥ 30, R − 30 ≥ 10), ×1.2 for trams;
- rotating parts +6 % of the mass;
- a vehicle without scripted drive gets its class's figures (`pedal_forces`): tram 14 kW/t, 1.2 m/s² start,
  1.3 service, 2.8 emergency (service through the wheels, the rest from the magnets); AI trams cap their
  acceleration at `11.9 / v` m/s² (`ai_traffic/model.rs:643`, `traffic/ai_state.rs:1221`).

**Brakes and couplers** (`rail/brake.rs`, `rail/chain.rs`, `omsi-vehicle/src/rail_spec.rs`): `air`, `ep` or `direct`
brakes; an air brake's pipe drop runs down the train at `pipe_wave` 250 m/s, each cylinder fills in `apply_time` 4 s and
empties in 12 s; `blend` puts the electric brake first. Couplers: per-car masses with `slack` 0.03 m, draft gear
3000 kN/m and 80 kN s/m, a train breaks above `max_force` 900 kN. All are openOMSI keywords in the vehicle file.

**The body on its springs** (`rail/body.rs`): heave, pitch and roll as damped second-order systems on the secondary
suspension. Tram: 1.25 / 1.45 / 1.15 Hz, damping ratio 0.3, centre of gravity 0.95 m over the rail, springs 1.5 m
apart, pitch radius 0.35 × the bogie span, roll radius 1.0 m. Driven by `a_long` (pitch), `v × yaw rate` at the centre
of gravity (roll; railways' cant takes up to 0.1 g off) and the rails' heights at each bogie: eight sines from 2.5 to
60 m wavelength, amplitude `0.35 mm × √λ × quality × 0.55`, quality 1.8 for street track. It outputs what a
passenger feels, `a_side + g sin(roll)`. Static: 0.7° of roll at R 25 m and 15 km/h, 0.16° of pitch at 1.2 m/s².

**Pantograph** (`omsi-trolley/src/panto.rs`, `omsi-sim/src/vehicle/panto.rs`, `omsi-app/src/rail_drive.rs:171-215`):
- the head's height is sampled over the raising animation on the model (`PantoShape.heights`) and inverted
  (`travel_for(h)`), so the animation is shown at the travel where the head touches the wire;
- raised, the head is a 9 kg mass on a 70 N spring, damped 45 N s/m, against a wire of 2500 N/m and 25 N s/m;
- the wire's unevenness under the head: droppers every 8 m ±2.5 mm, spans of 40 m ±5 mm, wear ±3.5 mm, +16 mm at
  hard points (forks and crossings, ramped over 4 m), times a roughness of 1.3 dry, +0.5 per unit of wetness,
  +1.5 in frost;
- contact lost for under 60 ms keeps the power (the arc and the drive's filter bridge it); a break above 15 A
  strikes an arc of `½ L I²` with L = 12 mH; under load at speed the strip throws sparks at
  `(I/200)(v/10) × roughness × 0.35` per second;
- the wire for trams is 5.7 m over the rail where the pantograph reaches it between 15 and 92 % of its travel,
  else at 60 % of its travel; staggered ±0.2 m in a 60 m sine; no wire geometry from the map.

**Supply** (`omsi-transit/src/power.rs`, `omsi-trolley/src/wire.rs:832-873`): sections with `live`, `feeder_ohm`
and `regen_kw`; a vehicle's voltage is the nominal less `(others + own) × feeder_ohm` of its section; a pantograph
must be within 2.5 m of a live span and not in an insulator's gap; the drive falls linearly from 80 % to 50 % of
the nominal voltage. Regenerated power is taken only up to the section's `regen_kw` plus what other vehicles draw.

**Trolleybus gear** (`omsi-trolley/src/pole.rs`, `rig.rs`, `traction.rs`, `wire.rs`; `docs/TROLLEYBUS.md`):
- two wires 0.6 m apart in spans whose ends within 1.2 m are joined (`wire.rs:279`; the doc says 25 cm);
  insulators 0.8 m dead between sections;
- frogs set by a contact plate 9 m ahead that reads the current (12 A), by the indicator, or by radio (a 150 m
  circle, channels, route codes), locked 2.5 s;
- poles with elevation and swing, 120 N at the shoe, 16 kg boom and 3 kg head; dewiring causes: lateral (40°),
  kink (shoe faster than 3 m/s sideways), bounce, out of reach, end of wire;
- a rheostat drive (series motor `V = (Ra + Rx) I + K I/(I + Ih) ω`, 14 resistor steps and two field steps),
  an inverter with regeneration, an optional battery;
- arcs where current breaks: frogs and insulators above 3 A (`wire/arcs.rs`), `½ L I²` on entering a gap,
  `I × 60 V × 2 ms` on leaving it (`rig.rs:439-448`);
- sounds as events (`ev_trolleyarc`, `ev_trolleyinsulator`, `ev_trolleyfrog`, contactor click, a hiss by current
  and speed with 300 Hz ripple). Only the player's vehicle has gear; AI trolleybuses run as buses.

**The rest of the vehicle:** `vehicle_api.rs` turns a bus's own variable names into one snapshot with fixed names,
`null` for what a bus lacks; `ibis.rs` finds how to type a duty into any IBIS by trying keys on copies of the
script state; `door_keys.rs` finds doors from the scripts; `omsi-vehicle/src/cabin.rs`, `paths.rs` hold seats and
an interior walk graph; `rigid/` is a road vehicle's rigid body with stretched-string tyres and ISO 8608 road
roughness; `collision.rs` tests oriented boxes in the ground plane.

## What we do

- **One equipment class per vehicle type**, not scripts: `src/tram.js:1-5` (body table `T3` 12-34),
  `src/tr37.js:20-22` (the interface: `update(dt, ctx)` → forces, current, notch, lamps). Vehicles from players are
  data only (`docs/decisions/2026-11-10-vehicle-packages.md` § 1-2, "No code in a package").
- **TR 37 from the manuals** (`src/tr37.js`): the TE 022 motor chart at 300 V (92-117), current steps 220–480 A held
  by the limiting relay turning the 99-position accelerator, field stages, cross-connected brake loops with fade,
  shoe-brake hand-over at 120 A, FC33 magnets 60 kN each with μ by speed (76-81).
- **Adhesion** (`src/tram.js:37-60`, `docs/research/rail-adhesion.md`): per weather from the research, the CK speed
  factor, sand by the rail's state, per axle with the sand trail, a creep curve with what is left when spinning
  (dry 0.5, rain 0.85 of the peak), the wheels' own inertia while slipping (`_slipStep` 221-252).
- **Running resistance** (`src/tram.js:177-179`): 650 N + 28 N per m/s a car, `4.2 (0.7 + 0.3 k) v²` of air, curve
  `min(0.015, 0.3 / R)`; matched on the coasting of car 7290 (`docs/knowledge.md:576-579`), the rise with speed open.
- **The wire** (`src/electric.js:12-77`): substations from data, wire and feeder resistance along the track, the
  drop shared with other trams on the same side of a feed; the motor-generator a series motor on the line
  (115-142). Section ends are not known (#277).
- **The overhead line drawn** (`src/world.js:1969-2094`): the contact wire 5.34 m over every track
  (`src/models.js:306`), no stagger, cross-spans on poles or rosettes. The collector posed by contact height,
  linear in the clip between `minContactHeight` and `maxContactHeight` (`src/rigged.js:313-317`).
- **Switch contacts** worked by current through the pantograph, the VÝHYBKA button and the heating cut-out
  (`src/game.js:1451-1456`); radio switches only through the "Automatic switches" option, their Prague rules
  (`docs/research/prazsketramvaje/switches.md` SW-K2) waiting in #296.
- **The cab's motion** (`src/main.js:942-958`): pitch from the track and `−0.006 × a`, a 0.002 rad sine sway at
  1.3 rad/s and a 12 mm bob at 9 rad/s; the cars posed on their bogie pivots with the cant (`src/models.js:538-551`).

| two empty T3 cars (32 t) | openOMSI | ours |
|---|---|---|
| adhesion dry, wet, leaves, snow | 0.33, 0.23, 0.13, 0.13 (ice 0.07) | 0.30, 0.17, 0.15, 0.12 (patches 0.06) |
| rotating mass | 6 % | 15 % (2.4 t a car, t3-accelerator.md § 5.3) |
| running resistance at 0 / 10 m/s, without air | 1.10 / 1.22 kN (×1.8 at a stand) | 1.30 / 1.86 kN |
| curve at R 25 m | 18.8 kN, 0.59 m/s² | 3.8 kN, 0.12 m/s² |
| emergency stop | 2.8 m/s² fixed | from the FC33 magnets' μ(v): 2.2–3.0 m/s² (VUT Brno measured 2.65–2.85) |
| contact wire | 5.7 m | 5.34 m |
| voltage at the collector | nominal − section current × feeder Ω | substations from data, resistance along the track |

## Ideas: take or not

1. **Section insulators as a dead gap, and arcs where current breaks** (`wire.rs` gaps, `rig.rs:439-448`,
   `panto.rs`). **Take the idea for a new issue (A below)**: the gap gives 0 V at the pantograph for its length;
   our motor-generator and line contactor then decide what a T3 does, where openOMSI needs a 60 ms ride-through
   constant. An arc's flash and crack from `½ L I²` of the current broken (L of the T3's circuit to be found; at
   12 mH a car's 480 A burns 1.4 kJ, the motor-generator's 12 A under 1 J). The same flash serves sparks on an iced
   wire (openOMSI's roughness and spark rate). Feeds the D 1/2 rule (`section-insulator-coast`,
   `truth-candidates.md:93`; SIG-W1, `signals.md:122`), a car stopped on an insulator (T3-E2, `t3.md:95`), the
   buzzer (#246 item 6) and the finger weld over an insulator (#493).
2. **The body on its springs** (`rail/body.rs`). **Take, rewritten** (≈80 lines): replace the cab's sines with
   heave, pitch and roll driven by the acceleration, `v²/R` and the rails' unevenness, and pose the model cars the
   same way. The phone in #500's rides reads exactly openOMSI's `a_side + g sin(roll)`: with v and R known, its
   lateral axis gives the T3's roll per curve, its vertical axis the ride's unevenness by track style. New issue B.
3. **The pantograph's head sampled over its clip** (`PantoShape.travel_for`). **Take for #71**: when the wire
   height varies (under the Výtoň bridge), the head must meet it at any height; our linear `collectorU` is right
   only where the clip moves the head linearly. Sample the head's height at ~20 clip times when the rig is built
   or loaded and invert. The head's mass-spring (millimetres) and the standard 5.7 m are not taken.
4. **Curve resistance by Röckl and the slower rise of running resistance with speed**: **not taken**. Röckl's fit is
   for railway radii and gives 5× ours at R 25 m; openOMSI's own tram test asks for over 0.3 m/s² of extra
   deceleration there. A point for #500: the accelerometer files settle both, coasting through the curves under
   50 m and at 15–50 km/h on the level.
5. **Adhesion, slide, sand, brakes, track brake**: **nothing to take**. Ours come from #266's measurements, the
   T3's FC33 magnets and VUT Brno's stops; openOMSI's are generic factors and fixed decelerations. The start
   factor 1.8 belongs to plain bearings; not taken unless a ride shows a start needing more than the running
   resistance.
6. **Traction electrics**: **nothing to take** for the T3. The rheostat drive is the series-motor equation our
   motor-generator already uses (`src/electric.js:124-129`) with generic steps; TR 37 is modelled from ČKD's
   wiring. The inverter's regeneration limit (taken only up to the substation's capacity plus what others on the
   section draw) is the rule for a later regenerating type (a T3R.P, #456 § 8), with our `Feeding`'s `others`.
7. **Supply sections**: ours is more detailed (positions, resistance along the wire). Take openOMSI's explicit
   `live` flag per section into issue A, for a supply failure (D12-D5, `rules-d1-2.md:87`: 100 m gaps when
   starting during one).
8. **Couplers with slack and draft gear** (`rail/chain.rs`): **not taken**. A two-car T3 set is one mass here;
   a coupler model comes only if #500's accelerometer shows a jerk at starts that one mass cannot make.
9. **Scripted vehicle systems**: **not taken**. #456 decided that a package is data bound to the game's named
   states and parameters; equipment stays a class in the repository. Scripts would also be code from players
   in a web page.
10. **A fixed-name vehicle snapshot with `null` for what a vehicle lacks** (`vehicle_api.rs`). **Take the rule for
    #528**: parameters a type lacks (a T3M has no accelerator position) read `null`, never missing, so a sound pack
    or panel written for one type runs on another.
11. **Animation bound to a variable by a factor** (`[newanim]`, `anim.rs`). **Idea for #456's tier 3** when the cab
    gets a 3D panel (#68, #246): needles, pedals and the controller as nodes turned by a published parameter times a
    factor, with no code in the package.
12. **Sound events of the wire**: add `arc` and `insulator` to #528's event list with issue A; a collector hiss by
    current and speed is a loop for #550.
13. **Wire switches by current, indicator or radio**: **nothing to take**. Our contacts read the current the T3's
    circuits draw (traction, the button, the heaters); #296's radio switches follow the Prague receiver 25–35 m
    before the switch and the selector 40 m before it, not a 150 m circle.
14. **AI trams' power cap** (`11.9 / v` m/s²): #243 plans a capability per type from `src/tr37.js` with the load;
    nothing to take. For #69's AI trains openOMSI's train class (9 kW/t, 0.9 m/s²) is a generic default only.
15. **Trolleybus poles, dewiring, rheostat, battery**: **not now**. #39 runs trolleybuses as AI on the lane graph,
    which needs none of it; a drivable trolleybus would start from `pole.rs` and `TROLLEYBUS.md`.
16. **IBIS typing, interior paths, doors from scripts, tyres, box collisions**: **not taken**. The T3's onboard
    computer is out of #246's scope and would follow its manual; #249's cabin layout from the asset lab (24 seats,
    standing layouts, two streams a door) is richer than `paths.cfg`; our doors follow the T3's interlocks; street
    vehicles stay kinematic (#250).

## Proposed issues

**A. Section insulators in the game: the dead gap, the arc, the buzzer, a car stopped on one** (`lane:sim`,
Backlog, blocked by #277).
- Now: no insulators; `Feeding` takes the nearest substation (`src/electric.js:24-58`); no arcs.
- What: each insulator from #277 is a dead gap (its length from the source); the feed changes there; 0 V at the
  pantograph over it; an arc flash at the collector and a crack sized by the current broken; the buzzer as the
  T3SUCS's SN contact gives it; a car stopped in the gap rolls off as T3-E2 says; Advanced scores drawing current
  under one; a section can be switched dead (a supply failure). Sparks on an iced wire with the same flash.
- Done when: line 17's insulators work as above; the arc and buzzer events are in #528's list.
- Checks: `u3,redruns,traffic,lint` with `--compare` on all lines, seeds 1–5; `stops`; `tools/test_electric.py`.

**B. The car body on its springs: heave, pitch and roll for the cab view and the cars** (`lane:assets`, Backlog,
no blocker; drawing only).
- Now: the cab's sway and bob are sines (`src/main.js:942-958`); the cars are rigid on their pivots.
- What: the three modes as second-order systems from `a`, `v²/R` and the rails' unevenness by track style;
  frequencies and damping fitted on #500's accelerometer files (the lateral axis less `v²/R`).
- Done when: the cab rolls out of curves and pitches under drive and brake as the rides show; the AI trams'
  near cars move the same way.
- Checks: screenshots main vs branch, `tools/frametime.py`.

## How to take it (question 4)

Every take above is an idea or a short equation, rewritten in our code and units with our numbers: none needs
openOMSI's code. openOMSI is **AGPL-3.0-only**; ours is AGPL-3.0-or-later (#518). A ported file would carry
`SPDX-License-Identifier: AGPL-3.0-only`, openOMSI's notice, its URL and commit, and the game as a whole could then
be offered under AGPL-3.0 only: a decision for the user before any port. Nothing here reads OMSI 2's files or
formats, and no OMSI 2 content or sample file is needed.
