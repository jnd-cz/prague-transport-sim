# openOMSI: AI traffic, paths and people (#520)

openOMSI read at commit `b2dc640b4db64a09ddfc0d00b8e78c463c81c842` (2026-11-12), AGPL-3.0-only (`Cargo.toml`).
Paths below are under `crates/omsi-sim/src/` unless they name another crate. Its comments mark which rules are
Omsi.exe's (with addresses) and which are its own; both are given here as openOMSI runs them. Our side: main at
619e0e9. Answers the issue's row "paths in `omsi-sim` / `omsi-scenery`".

## What openOMSI does

**The network** (`traffic/mod.rs`, `traffic/lane.rs`, `traffic/network.rs`; `omsi-scenery/src/lib.rs` `PathDef`).
One `Lane` per `[path]` of a spline (along it at a lateral offset) or of a scenery object (arcs in the object's
frame); kind street, sidewalk, rail or air. Lane ends within 1.5 m are linked (`traffic/extend.rs`
`LINK_TOLERANCE`). A junction is a scenery object: its lanes are its paths. Each lane carries its rules: `no_cars`,
`bus`, `trucks` (who may use it, `Lane::allows`), a traffic density per vehicle group, `overtaking_prohib`,
`priority` (the stock maps put 192 on a main road's straight paths, 64 on paths out of a side road; 128 unset) and
`crossingproblem`. `[blockpath]` is read and has no effect (none in Omsi.exe either, per `Lane::blocks`).

**Conflicts are stretches, not points** (`Network::conflicts_from`). Only lanes of one junction object conflict.
A pair conflicts where the lanes cross (ends excluded), merge (ends within 1.5 m, or within 2.6 m leading into
the same lane) or pass closer than 2.0 m (`near_pass`: two turns sweeping past each other). Each `Crossing` keeps
the distance along both lanes and how far before and after it the centre lines stay within 2.6 m (`MEET_DIST`, two
bus half widths; at most 14 m each way). A vehicle holds that stretch until its tail has left it;
`crossingproblem` widens it to both whole lanes. The footpaths of the object crossing a street lane are listed
per lane (`Network::walks`).

**Who goes first** (`Network::must_yield`, `ai_traffic/junctions.rs`), in this order: a train; the higher
`priority`; the ring before its entry (roundabouts found as loops of street lanes under 190 m, `traffic/rings.rs`);
a turn across the oncoming traffic waits for it; between equals, whoever reaches the meeting place more than 0.5 s
earlier (`FIRST_COME_MARGIN`), within 0.3 s the lower id, but within 1 s the one that can no longer stop firmly
(`firm_stop`: v²/8 + 0.3v + 1 m) before one that can (`goes_first`). No priority to the right: Omsi.exe has none,
and a right-before-left of openOMSI's own stopped the main road's cars for every side-road car on maps without
priorities (its #2058).

**Claims and the exit** (`TrafficSim::junction_stop`, `ClaimBook`):
- A car decides from v²/2b + 12 m before the junction (20–70 m). Deciding to go claims the junction's lanes; the
  claim stands until the car's tail is out. Only a car that gives way by a sign and can still stop gives up an
  early claim: weighing the gap anew every step made two cars take turns at stopping.
- It gives way to a vehicle in a meeting place, to a claim that arrives before it is through, and to traffic with
  the right of way inside its gap: `accept_gap` + 2 s, at least its own clearing time + 1 s. `accept_gap` is
  N(4, 1) s per driver, at least 2 s; the gap shrinks by up to a third after 40 s of waiting. At a merge: the
  `accept_gap` or its own arrival + 3 s.
- It enters only with room on its exit: the length it needs, a queue counted where it will stop braking at 2 m/s²
  (`queued_exit_vehicle`: a crawling queue leaves no more room than a standing one), 3 m of hysteresis, minus the
  room promised to cars admitted before it (15 m behind a queue take one 10 m bus, not two cars and the bus).
- Courtesy (`lets_in`): a car that has stood 20 s at a side road's line is let in by a main-road driver slower than
  6 m/s who can stop comfortably (StVO §11(3)); it replaced a forced claim after 25 s.
- A left turn at a signal pulls into the junction to its meeting place with the oncoming traffic (at least 3 m past
  the line), one car at a time; without a signal it waits at the line.

**Circles of waiting cars** (`ai_traffic/deadlock.rs`, `ai_traffic/stats.rs`). Every car notes whom it waits for and
why (`Hold`: body, claim, rule, courtesy, exit, lead). The circles of that waits-for graph (Tarjan's strongly
connected parts of two cars or more) are sorted: a red light in it is lawful and clears on green; claims alone are
stale, the longest waiter keeps his and the others let go; cars yielding to each other by the rules: after 8 s
(`YIELD_CYCLE_WAIT`) the longest waiter goes by the rules for 12 s (`YIELD_PASS`), still stopping for bodies,
people, lights and a full exit; rules and followers tangled: claims let go but the longest waiter's; else the road
is full and nobody is forced through. A random car that has stood 200 s with no light holding it is taken off once
out of sight (`ai_traffic/tick.rs` `GIVE_UP_STOOD`, Omsi.exe's value). `OMSI_TRAFFIC_STATS` writes a CSV line a
minute: cars standing and how long, the circles, for every car standing over a minute the head of its chain and why
that one stands, junction entries, red runs, emergency braking, give-ups, bodies inside each other.

**Following** (`traffic/ai_state.rs` `desired_accel_bend`): the Intelligent Driver Model with the
constant-acceleration heuristic (its ACC variant: a car cutting in close at nearly the same speed asks a firm brake,
not an emergency stop). Per driver, from the car's seed (`ai_traffic/model.rs` `personality`): desired speed
1.01 ± 0.11 × the limit (heavy 0.93 ± 0.05), time headway 1.4 ± 0.2 s, standstill gap 1.6–3.0 m, acceleration
1.3–2.3 m/s² (heavy 0.8–1.2), comfortable braking 2.0–2.8 (heavy 1.6), hardest ordinary braking 4.6–5.4
(heavy 4.5), emergency 8, jerk 8 m/s³, reaction 0.8 ± 0.2 s. A lower limit ahead is reached at 1.2 m/s², a bend
at 1.2 m/s² (`BEND_DECEL`). A stop line: the model's term, blending into the constant deceleration that stops the
car 0.6 m short as that grows from 0.35 to 0.5 of its comfortable braking. A car standing within 0.75 m of its gap
stays put.
Brake lamps on below −1.0 m/s², off above −0.4 after at least 0.6 s. Vehicles are looked for v²/3 + 2v + 20 m
ahead, 70–150 m (`ai_traffic/obstacles.rs` `look_ahead`).

**Lights** (`traffic/lights.rs`, `ai_traffic/lights.rs`, `ai_traffic/light_paths.rs`):
- One controller per crossing object (`TrafficLightController`): per light a list of (aspect, seconds), a cycle and
  offset, an approach distance per light (50 m when unset, 600 m for a train; a vehicle within 3 m of the line
  always asks), and stop and jump points: at time t the clock waits or jumps while somebody asks at light k, or
  while nobody does (`if_request`). The stock maps keep a level crossing's road green until a train asks, skip a
  bus phase nobody waits for, hold a depot gate green while buses come.
- A path marked as a turn is a detector: a vehicle standing on it with that indicator on asks its light.
- A car finds the light that holds it along its whole way up to 150 m (`light_stop`, `entry_light`: a light passed
  inside the same object does not hold again, a second stop line of the same movement does).
- Amber: it goes when it cannot stop comfortably (v²/(2 · 1.4b) + 1 m) or, by a per-driver draw, 3 ± 1 % of the
  time anyway; on red only when it went on amber, is still on its way (3 m/s, `AMBER_KEEP_SPEED`, or rolling over
  the line) and cannot stop comfortably, or cannot stop at 0.8 × 8 m/s². The decision is kept per light, not lane;
  the first car standing at the line when green came keeps going (a 1 s green otherwise let nobody through); a car
  standing over the line does not set off on red.

**Lane changes** (`ai_traffic/lateral.rs`, `planning.rs`). One function owns a car's sideways target each step,
in one order of urgency: a change under way, a bus at its stop, making way, the change the route needs, the
driver's own wish, going round something standing. A wish must hold 0.6 s; no change back within 8 s; into one lane
one car per 40 m per step; the turn lane within 150 m of the junction; a car waiting for its gap stands 13 m short of
where it must be over (a change from standstill is 12 m long) and moves over anyway after 12 s; at a zip merge each
takes its turn after 3 s standing.

**People on foot** (`people/pednet.rs`, `people/walk.rs`, `crowd.rs`, `ai_traffic/obstacles.rs`):
- The pavements are one graph: sidewalk lane ends closer than 1 m are one node whatever their heading; an end
  meeting another lane's middle (0.3 m from its ends, within 1.2 m and 2.5 m in height) splits it there (a "tap").
  Where a pavement lane crosses a street lane's centre line is a crossing (`crosses_street`).
- At the kerb (`may_cross`): with a light, green, and the green plus the clearance until the cars' green at least the
  crossing time (length at the walker's pace + 1 s); after 150 s any green, never red; a stroller turns back after
  180 s at a red. Without a light: no car within 90 m whose line passes within 3.5 m and that gets there within the
  crossing time + 2.5 s (1 s after 20 s of waiting, 0 after 45 s); a car standing on the crossing holds them. Once
  on the crossing they go on.
- Walkers avoid each other and the vehicles with the time-to-collision force of Karamouzas, Skinner and Guy (2014;
  `crowd.rs`: k 1.5, horizon 3 s, relaxation 0.45 s, at most 2.2 m/s², looking 4 m; vehicles as boxes with their
  velocity), step right when head on; a contact pass puts anybody inside a vehicle's box outside it; standing
  people give less than walkers. (Omsi.exe's passengers do not avoid each other: one 0.6 m ahead stops them,
  `people/pax.rs`.)
- Cars stop 2.5 m before a crossing of their junction with somebody within 3 m of it, within 30 m of their front
  (`people_crossing`), and anywhere 1.5 m before somebody in the strip they sweep, where the person is now or will
  be when the car gets there, at most 2 s on (`people_stop`: reach v²/5 + v + 6 m, 8–45 m; half width + 0.3 m).

**AI trains, buses at stops** (`ai_traffic/blocks.rs`, `berths.rs`). A block holds one train; points are held while
a train stands on them, locked while their signal shows go, and go back to their default 15 s after the last
request. One timetable bus serves a stop at a time, the others queue 3 m behind; one standing within 25 m behind
serves the stop where it stands.

**Step and tests** (`ai_traffic/fixed_step.rs`, `*_tests.rs`). Steps of 0.02 s at any frame rate (`SIM_DT`, at
most 4 a frame); every car plans from the state at the step's start, so the list's order decides nothing (tests
`the_same_scene_drives_the_same_at_any_frame_rate`, `the_order_the_cars_stand_in_the_list_decides_nothing`).
Scenes are built in code and run headless (37 junction, 15 whole-scene, 26 lane-change tests), e.g.
`four_cars_at_a_junction_without_priorities_all_get_through`, `a_car_does_not_drive_into_a_junction_it_cannot_leave`,
`a_side_road_car_gets_into_a_main_road_that_never_leaves_a_gap`,
`a_queue_moves_off_without_closing_up_or_braking_hard`, `somebody_on_the_crossing_holds_the_car`.

## What we do

- **Network** (`src/traffic.js`): one lane per road and direction from OSM's count (`lanesOf` :127), placed from the
  survey's kerb (`laneOffset` :500); a junction is an OSM node, lane ends joined by cubic Hermite connectors
  (`connector` :606). Any lane turns anywhere: the straightest way on plus a random 0–0.8 (`_chooseNext` :593). Two
  connectors conflict when they cross, come within 2.4 m or end in one lane (`_conflict` :633): yes or no, no place.
- **Junctions** (:867–890): from max(9, v²/8 + 3) m before its lane's end a car waits while a car is on a
  conflicting connector, while one coming to a conflicting connector is nearer its lane's end (a tie to the lower
  id), while one stands in the mouth of a lane its connector passes close to, or while a car stands within 7 m of
  its exit lane's start. No signs, no turn-across rule, no gap in time, no claim kept.
- **Following** (`following` :104): the speed behind a leader is max(0, min(v_lead + 0.4 (gap − 8),
  0.9 (gap − 3.5))), approached at +2 / −5 m/s² (`_approach` :682); all drivers alike but `bold`, one in eight, at
  track crossings (:737). Curves at 2.5 m/s² sideways, braked for at 3 m/s² (:899). Obstacles every 2 m up to 40 m
  (`_obstacleAhead` :1074). No brake lamps on cars.
- **Lights** (:897–921): the stop line of the car's lane, of the next lane within 60 m, or after its connector;
  amber: it goes when its front is within v²/6 + v of the line; kept per lane (`lightGo`, `lightHold`). Car heads hang
  on a tram signal's controller (`_bindSignals` :1236; `src/game.js` `_runController` :1546): one fixed cycle per
  tram signal, 60–90 s (:425); a tram's call from 140 m cuts the cross green after 8 s of it; a committed tram holds
  the phase up to 10 s (`PHASE_HOLD` :22); an on-demand crossing rests on GO. Gauntlets: a block taking the
  directions in turn (`_updateGauntlets` :731).
- **The tram** (:771–858): a car turning across the track waits 1.5 m before its band while the tram's body is on
  the crossing or the tram would get there before the car is across with 2.5 s to spare (bold: 0.5 s); a car
  turning onto the track along it goes only when the tram could stop behind it; none drives onto the track without
  room beyond; cars on and crossing the track go to the autopilot (`src/autopilot.js` :214–218).
- **Circles**: three walks of up to 6–8 links (:752–764 what each car sees, :815–826 the car ahead: the lowest id
  goes), a car on our track whose chain ends at a standing tram leaves after 30 s (:946–976), the AI trams' rings
  (`_clearAiTramCycles` :1653). A chain whose head is a walker is in none of them.
- **Walkers** (`_linkWalks` :1134, `_updateWalkers` :1470): footway pieces, each end linked to walks within 3 m, else
  the nearest within 15 m; within 1 m of a piece's end a walker picks the next; it turns back before the tracks
  unless it stands in a car lane (:1543); at the kerb it waits for its red (`_pedRed` :1417) or a car within 40 m
  heading at the spot that would reach it within 4 s (`_carComing` :1431). To cars a walker is a still 0.4 m box
  (`_pathObstacles` :1067, `vx: 0`).

## Measured for this note

Right-of-way tagging in `raw/osm/praha.osm.pbf` (scratch script, 2026-11-13; car classes motorway to living_street
and their links, no service roads):

| | count |
|---|---|
| `highway=give_way` / `highway=stop` nodes | 1 899 / 483 |
| `highway=traffic_signals` nodes | 2 234 |
| ways with `priority_road=designated` or `yes_unposted` | 35 |
| car-way nodes with 3 or more arms | 31 192 |
| … a signals node within 30 m | 1 752 (6 %) |
| … else a give_way or stop node within 25 m | 2 096 (7 %) |
| … neither | 27 344 (88 %) |

OSM's signs decide few junctions; the rest need a rule.

## Ideas: take or not

1. **One waits-for graph with typed holds and chain heads** (`deadlock.rs`, `stats.rs`). Our 7200 s jams are chains
   with a walker at the head (#496, #393, #366, #269) or circles through a tram that no walk sees (#373, #281).
   **Take, reimplemented:** every car, AI tram and walker records whom it waits for and why (lead, junction rule,
   claim, exit, tram, light, walker); circles from the strongly connected parts, sorted as openOMSI sorts them; the
   stuck report and the traffic check name the head of every chain standing over 60 s and its reason. It replaces
   the three ring walks. The 200 s give-up out of sight: **only as the game's last net**, counted by the checks like
   `cyclesBroken`, so a rule bug still shows. **New issue A.**
2. **Walkers as moving bodies that keep out of a car's way.** **Take for #496** (and #269, #366): a walker in
   `_pathObstacles` carries its velocity; a car stops only for a walker in its swept strip now or within 2 s
   (`people_stop`); a walker never stands or turns round in a car lane or the track band, and one inside a car's box
   is put outside it (the contact pass). The full time-to-collision crowd: **not now**. Our walkers move along lines;
   it fits when footways are areas (#16) and passengers board as figures (#249, #40), written from the paper.
3. **Crossing by the time to cross** (`may_cross`). **Take for #121** (walker hits) and #43 / #42 (pedestrian heads,
   push buttons): the crossing's length at the walker's pace decides, a long wait shortens the margin but never
   below the crossing time, and a pedestrian green counts with its clearance. Our 4 s ignores the width (13 m across
   four lanes takes 10 s at 1.3 m/s), and `_carComing`'s 40 m is under 4 s for a car at 50 km/h (56 m). Cars give way
   at a zebra to somebody on it or within 3 m of it (`people_crossing`).
4. **The pavement graph** (`pednet.rs`). **Take the idea for #16:** the footway network built once as nodes (ends
   merged, taps where an end meets a middle) and edges with their crossings; a walker picks its next edge at a node.
   That removes the 1 m end test behind #393's loops and #41's hops. Our 3 m / 15 m link distances stay (measured on
   line 17, `_linkWalks`).
5. **Right of way at unsignalled junctions:** the order of `must_yield`, claims kept until the tail is out, gaps in
   time per driver shrinking with the wait, the car that cannot stop first, room on the exit promised once, courtesy
   in a slow queue. **Take, reimplemented,** with priorities from our data: `give_way` / `stop` nodes and
   `priority_road` where tagged, else the road class (OSM `highway`, TSK's class from #556), else the rule for
   unmarked junctions in Czech road law (right before left, the tram's own rules there from the user). openOMSI
   dropped right-before-left because its maps carry no priorities; our class rule gives them. Conflicts become
   meeting stretches (the place along both connectors and how far they stay within 2.6 m) instead of `_conflict`'s
   yes or no, so a car is released when the other's tail leaves the stretch: offsets on edges, as #32 wants.
   **New issue B.**
6. **Light programs as data** (`TrafficLightController`). **Take the form for #33** (docs/architecture.md §2: "its
   phases and priorities as data"): our tram call (a jump to the tram phase after 8 s of cross green), the dilemma
   hold (a stop while a committed tram asks, at most 10 s) and the on-demand rest (a stop while nobody asks) are each
   a stop or a jump; car, tram and pedestrian heads of a junction in one program; detectors as places with a
   condition (`light_paths.rs`) for push buttons (#42) and tram loops. TSK's programs would fill the same table
   (#64). The gauntlet (#450) is such a program too; openOMSI's blocks are as plain as ours, nothing to take there.
7. **Amber per head, along the way.** **Take for #367:** find the light that holds a car along its way (up to 150 m,
   `light_stop`), not lane by lane, and keep the go-on-amber decision per head, so a 3 m lane in a junction's mouth
   cannot lose it; a car standing over the line stays. The per-driver 3 % that go on amber anyway: **not taken**,
   our `redruns` check counts each as a broken rule.
8. **Following: IDM with the ACC heuristic, drivers of their own.** **Take, written from the papers** (Treiber,
   Hennecke, Helbing 2000; Kesting, Treiber, Helbing 2010) with openOMSI's spreads as starting values: a queue moves
   off a green as a wave, braking grows with need, a stop line is met at constant deceleration, brake lamps switch
   with hysteresis. It moves every seeded count (#156): a simulation-tier change on its own. **New issue C.**
9. **Lane changes with one owner of the sideways target** (`lateral.rs`; the order of urgency and the numbers
   above). **Take the rules for #304** (cars into their turn lane) and #46. Who may use a lane (`Lane::allows`:
   no cars, bus) is #556's strips put on the lanes.
10. **Scene tests:** small junctions built in code, run headless with assertions, and planning from the state at the
    step's start (order-free). **Take once the traffic core is apart from the meshes (#228):** a junction without
    signs, a queue beyond a junction, a side road into a busy main road, a walker in a car lane, a car on the track
    behind a waiting car, each in seconds, where today a 7200 s seeded run finds them by chance. **New issue D.**
11. **Berths** (`berths.rs`): **an idea for #39** (buses) and #260 (an AI tram behind ours at a stop); for trams the
    rule is D 1/2 § 27.6 (cited in #260), not openOMSI's.
12. **Not taken:** emergency vehicles and their corridor, the horn (presentation only), AI cars keeping out of scenery
    meshes (ours drive on the surveyed carriageway), passing on the other half of the road, traffic density groups,
    the 50 m lane grid (30 cars), roundabout detection (until a line passes a roundabout).

## Where ours is already more realistic

- **The tram among the cars.** openOMSI: a train always goes first, a level crossing is a light, rail and street
  lanes meet only as bodies. No car turning across a moving tram by its braking, none queueing on the rails of a
  shared lane, no tram driver who sees a car on the track (bell, braking). Ours does all three (:771–858,
  `carsOnTrack`, `carsCrossing`, the autopilot) from the user's facts (U3, #268). Nothing to take.
- **Where things stand.** Our stop lines, car heads, crossings and kerbs come from OSM and the survey (`_stopLine`,
  `src/pedestrianCrossings.js`, #146); openOMSI's are placed by hand in map objects.
- **The tram's priority.** Our call from 140 m, the dilemma hold and the on-demand crossing follow Prague practice;
  openOMSI's programs know generic requests only. Its form (idea 6) holds ours; its rules add nothing.

## How to take it

openOMSI is AGPL-3.0-only; ours is AGPL-3.0-or-later. A function translated from it makes that file
AGPL-3.0-only, with openOMSI's notice and a source link. Nothing above needs that: the following model, the
crowd force and Tarjan's algorithm are published (cite the papers), the rest are rules and numbers, re-implemented
in our structure with a comment naming the openOMSI file a number comes from. No OMSI 2 content or format is
involved: our paths come from OSM and the survey.

## Proposed issues

| | title | lane | milestone | blocked by | feeds |
|---|---|---|---|---|---|
| A | One waits-for graph for cars, AI trams and walkers: circles sorted by their holds, chain heads in the stuck report | sim | M4 | – | #496, #393, #366, #269, #373, #281 |
| B | Right of way at unsignalled junctions: signs and road class from OSM, turns across the oncoming give way, gaps in time, meeting stretches | sim | M4 | – (with #32's offsets) | #16, #304 |
| C | Car following by the Intelligent Driver Model, drivers of their own, brake lamps | sim | Backlog | – | #250 |
| D | Traffic scene tests: small junctions built in code, run headless | sim | M5 | #228 | A, B, C |

Each is checked by the simulation tier (`u3,redruns,traffic,lint`, all lines, seeds 1–5, `--compare`); A also by
`cyclesBroken` and the chain heads per kind, B by junction waits per line, D by its own scenes.
