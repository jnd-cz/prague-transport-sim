# openOMSI study (#520)

What [openOMSI](https://github.com/openOMSI-org/openOMSI) can teach our game. openOMSI is a from-scratch Rust
recreation of the OMSI 2 bus simulator's engine; it ships no game content and loads an installed OMSI 2's. Read at
commit `b2dc640b` (2026-11-12): about 500,000 lines in 47 crates. Our side at `main` 619e0e9.

- **What was read:** the code and openOMSI's own documentation. No OMSI 2 content, file or format was read or
  needed.
- **Licence:** openOMSI is **AGPL-3.0-only** (`Cargo.toml` `license`, CONTRIBUTING.md: "New contributions are
  AGPL-3.0-only"); ours is AGPL-3.0-or-later (#518).

## The notes

| note | covers | feeds |
|---|---|---|
| [map-and-streaming.md](map-and-streaming.md) | the map model, objects on splines, the ground under roads, road paint, tile streaming, memory | #31, #301, #309, #16, #276 |
| [traffic-and-people.md](traffic-and-people.md) | paths, junctions and their right of way, light programs, car following, deadlocks, walkers | #33, #450, #496, #304, #16, #367 |
| [vehicles-and-wire.md](vehicles-and-wire.md) | scripted vehicle systems, rail dynamics, the body on its springs, the pantograph, sections and insulators, trolleybus gear | #71, #277, #500, #528, #456 |
| [transit-sound-render.md](transit-sound-render.md) | duties and passengers, the sound engine and city ambience, rendering and frame time, weather, multiplayer | #40, #249, #550, #251, #308, #31 |

## Answers to #520's questions

1. **Which concepts solve something we have open.** By value to us:
   - **A waits-for graph for the traffic.** Each car records whom it waits for and why. Circles are found as
     strongly connected parts, and the longest waiter goes by the rules after 8 s. A report names the head of
     every chain standing over 60 s.
     - Our 7,200 s jams are chains headed by a walker, or circles our ring walks (`src/traffic.js` :753, :811)
       miss (#496 and five others).
   - **Right of way at junctions without signals:**
     - the priority sign first, then a turn across oncoming traffic waits, then first come by 0.5 s;
     - gaps in time, and room on the exit promised once.
     - OSM decides few junctions: of Prague's 31,192 car junctions, 6 % have a signal nearby and 7 % a give-way
       or stop sign; 88 % have neither.
   - **Section insulators** as a dead gap at 0 V, with an arc where current breaks (½LI²). This serves the
     coasting rule over insulators, a car stopped on one, the buzzer, and #493.
   - **Tile streaming,** designed in numbers:
     - two centres (the camera and the player's vehicle), 1,200 m out, and unloading 450 m further;
     - the loading screen waits for the first 700 m only;
     - on the drawing thread, 6 ms a frame for upload and placement plus 2 ms for textures, sliced below one tile.

     Two done-when checks for #31: a streamed drive equals a whole-line load, and the simulation never takes
     tile data per frame.
   - **The car body on its springs:** heave, pitch and roll as damped modes, instead of the cab's sine sway.
     #500's accelerometer rides can fit it.
   - **Sound rules for #550:**
     - a triggered sound keeps the loudest volume its curves gave since it fired;
     - in the cab, the outside comes through a low-pass that opens with the doors (500 Hz all shut);
     - at most 200 voices, the nearest kept;
     - OMSI's distance law is Web Audio's `PannerNode` "inverse".
   - **City ambience** chosen by what stands around the listener, the hour, the season and the weather. Our
     build holds the inputs.
   - **Smaller points into open issues:**
     - **#71:** sample the pantograph head's height over its clip and invert it.
     - **#500:** curve resistance: openOMSI's is 5× ours at R 25 m; the rides settle it.
     - **#528:** a parameter a vehicle type lacks reads `null`.
     - **#456:** cab needles turned by a parameter times a factor.
     - **#301:** a junction's heights from its arms.
     - **#309:** a paint classifier.
     - **#16:** lanes from the same cross-section as the surface.
     - **#367:** amber light kept per head.
     - **#33, #450:** light programs as data.
     - **#40, #249:** passengers built up by the time since their line's last tram; they give up at a shut door
       after 25 s.
     - **#251:** far figures posed less often.
     - **#308:** occlusion, roughness and metalness packed in one texture.
2. **Where our model is already more realistic, so nothing is taken:**
   - real Prague geometry from the survey, DI and the 1 m lidar, against hand-made splines and a 5 m terrain;
   - the ground built once, offline;
   - networks kept global, not per tile;
   - the tram among the cars: turning across a moving tram, queueing on shared rails, the driver who sees a car
     on the track. openOMSI lets a train always go first;
   - adhesion, sand, slip and brakes from measurements;
   - the TR 37 electrics from ČKD's wiring, and supply along the wire from real substations;
   - the timetable from GTFS;
   - comfort scoring for trams.
3. **Tiles and memory against our per-line loading:**
   - **Tiles:** openOMSI parses, cuts and fits 300 m tiles at load, and needs neighbouring tiles staged first. M3
     plans prebuilt 500 m tiles cut offline, which needs no neighbours.
   - **Memory:** it counts its own bytes and drops texture mips to stay in budget. For us geometry dominates (656
     MB against about 47 MB of textures on line 17), so #31 should count our own geometry bytes; WebGL reports
     none.
   - Details: [map-and-streaming.md](map-and-streaming.md), "Streaming and memory side by side".
4. **How to take what is useful.** Ideas and numbers only, written anew in our code: none of the takes above needs
   openOMSI's code.
   - **A port changes the licence.** A file translated from it would have to stay AGPL-3.0-only, against our
     `-or-later` SPDX header rule (#518): a decision for the user before any port.
   - **Published models are cited directly.** Where a model is published (the Intelligent Driver Model, Tarjan's
     strongly connected parts, Curtius–Kniffler), the paper is cited, not openOMSI.
   - **Numbers name their source.** A number taken from openOMSI names its file and commit in a comment.
   - **Rules from `Omsi.exe`:** openOMSI's comments mark which rules it took from the original `Omsi.exe`, with its
     addresses (79 files of `omsi-sim` cite them), and which are its own. Our takes prefer its own rules,
     published models and Prague facts. Where a rule is `Omsi.exe`'s (traffic-and-people.md says so per rule),
     only the behaviour is taken, written anew with our numbers.

**How openOMSI checks its own changes** (`docs/REFACTOR_CHECKS.md`). This is beyond #520's questions, but it
bears on our check tiers:
- **Golden pictures:** nine fixed, seeded offscreen scenes per build, compared pixel by pixel with an allowance
  per scene, and a difference picture written. Ours compares one scene at a time (`tools/shot.py`).
- **Audio traces:** every voice the mixer is asked for, compared between builds.
- **A size budget:** files may grow at most 5 %, a new file stays under 1,500 lines and a function under 300.
- **A layer guard:** the simulation never depends on the renderer, with each exception listed until it is
  removed.

For us, a golden set over all lines would make the drawing tier's "screenshots main vs branch" one command
(proposal 11). The layer guard is a check for #422's split of `world.js`.

## Proposed issues (the user picks)

| # | issue | lane | milestone | blocked by | details |
|---|---|---|---|---|---|
| 1 | One waits-for graph for cars, AI trams and walkers: circles broken by their holds, chain heads in the stuck report | sim | M4 | — | traffic-and-people.md A |
| 2 | Right of way at unsignalled junctions: signs and road class from OSM, turns across the oncoming give way, gaps in time, meeting stretches | sim | M4 | — | traffic-and-people.md B |
| 3 | Section insulators in the game: the dead gap, the arc, the buzzer, a car stopped on one | sim | Backlog | #277 | vehicles-and-wire.md A |
| 4 | The car body on its springs: heave, pitch and roll for the cab view and the cars | assets | Backlog | — | vehicles-and-wire.md B |
| 5 | Flat things on the ground at their true height: a depth pull instead of lifts | world | W4 | #509 | map-and-streaming.md |
| 6 | Car following by the Intelligent Driver Model, drivers of their own, brake lamps | sim | Backlog | — | traffic-and-people.md C |
| 7 | Traffic scene tests: small junctions built in code, run headless | sim | M5 | #228 | traffic-and-people.md D |
| 8 | City ambience chosen by place, hour, season and weather | assets | Backlog | #528 | transit-sound-render.md P1 |
| 9 | Weather that changes during a shift: the rail wet from the first drops, drying after | sim | Backlog | #266 | transit-sound-render.md P2 |
| 10 | Fogged windows from the cabin climate | sim | Backlog | 9 | transit-sound-render.md P3 |
| 11 | Golden scenes: a fixed seeded set over every line, compared pixel by pixel with allowances | tooling | Backlog | — | this README |

Points for existing issues (#31, #71, #301, #309, #16, #500, #528, #456, #550, #40, #249, #251, #308, #367, #33,
#450) go as one comment each, citing the note.

## Questions for the user

1. Which of proposals 1–11 to open? 1, 2 and 3 do the most for what we have open.
2. May the points for existing issues go to them as comments?
3. Do the T3s the game models announce stops? (a) No. (b) A recording ("Příští zastávka …" on leaving, the name at
   the stop), and on which cars. (c) The driver by microphone. With (b), a sound pack gets an event per stop.
4. A driver's record across shifts (distance, stops on time, comfort, kept in the browser): for the closed alpha
   (#350), later, or not at all?
