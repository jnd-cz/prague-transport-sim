# D 1/2: operating rules for the driver

DP Praha's traffic and signal regulation for trams, *Dopravní a návěstní předpis pro tramvaje D 1/2*,
approved 2025-01-30, in force from 2025-09-01, 62 pages
([PDF on prazsketramvaje.cz](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/predpis_d1-2_20260201.pdf),
the site's file of 2026-02-01). Cited below as "§ paragraph.clause, page". Paraphrased; the
regulation is DP's internal document ("for work use only"), so the text is not copied here.
Signals are in [signals.md](signals.md), switches in [switches.md](switches.md).

Status against the game (main at 7cac287): **in game**, **differs** (the game does it otherwise),
**missing**, **n/a** (outside what the game simulates). IDs (`D12-…`) are used by
[truth-candidates.md](truth-candidates.md).

## Terms worth keeping

| ID | Term | Meaning | § |
|---|---|---|---|
| D12-T1 | facing switch (*rozjezdová výhybka*) | a switch run against its points in regular service; a switch run regularly in both directions counts as facing too | 2.17, p. 8 |
| D12-T2 | trailing switch (*sjezdová výhybka*) | a switch run from its frog side (*po hrotech*) in regular service | 2.18, p. 8 |
| D12-T3 | stop area (*prostor zastávky*) | from the stop sign (*označník*) to the end-of-stop marker; without one, the length of the platform edge; if neither can be told, 30 m from the sign | 2.22, p. 9 |
| D12-T4 | braking distance (*zábrzdná vzdálenost*) | the distance in which the train must stop safely with the service brake from the speed allowed in that section | 2.8, p. 8 |
| D12-T5 | train (*vlak*) | one car or coupled cars; cars are numbered from the front | 2.6, p. 8 |
| D12-T6 | stop kinds | *stálá* (every train stops), *občasná* (only listed trains), *na znamení* (request), *manipulační* (operational only) | 27.2, p. 24 |
| D12-T7 | single-track section, *kolejová splítka* | a section where opposing trains cannot run at once (shared track, or interlaced rails) | 2.19, 23, p. 8, 21 |

## Speeds (§ 25, p. 22–23)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-V1 | The highest speed on the tram network is **50 km/h**. Any other speed is set by signs; signs can lower it or raise it ("Rychlostník", white number on black). The exam set says the same for track off the road (PPS Q83). | 50 in streets; untagged dedicated track gets **60**; OSM `maxspeed` up to 70, capped at 60 (`src/route.js:323-329`, `tools/osm_speeds.py`) | differs: more than 50 needs a Rychlostník sign at a known place |
| D12-V2 | A **restriction** applies when the **front** enters it and ends when the **rear** passes its end sign ("Ukončení omezené rychlosti", also "Konec zóny"). | `Game.currentLimit` takes the lowest limit under the whole tram (`src/game.js:942`), plus `speedLimits`' window from 15 m before to 5 m after (`src/route.js:333`) | in game, with the extra window #211 lists |
| D12-V3 | A **higher** speed (Rychlostník over 50) applies only once the **rear** has passed the Rychlostník, and must be down again when the **front** reaches its end. A Rychlostník below 50 works like a restriction. | the same whole-tram minimum | in game (falls out of the minimum) |
| D12-V4 | "Místo s omezenou rychlostí" (a point restriction, sign with a black triangle under it): only the **front** must pass the point at the speed; the driver may speed up once the front has passed. | no point restrictions | missing |
| D12-V5 | **5 km/h**: coupling cars, over a pit, over a switch or place where an order sets slow careful driving. | – | n/a (no depots, orders) |
| D12-V6 | **10 km/h**: depot halls; reversing and driving from the auxiliary cab; facing a switch set diverging inside a depot yard; pushing a dead car (not uphill); past work sites; over a mobile crossover. | – | n/a |
| D12-V7 | **15 km/h**: **facing a switch, straight or diverging**, unless a sign sets otherwise; **trailing a switch from its diverging branch**; over **track and trolley-wire crossings** (*kolejové a trolejové křížení*); depot yards outside halls; **curves of turning loops**, from the first facing switch (or the switch into the loop) to the last trailing switch (or the switch out of it). | facing switches only: **15 diverging, 30 straight**, from 4 m before to 14 m after the switch (`src/game.js:118`); trailing switches, crossings and loops unlimited | differs (facing straight is 15, not 30) and missing (trailing diverging, crossings, loops); #211 |
| D12-V8 | **30 km/h**: **trailing a switch from its straight branch**, unless a sign sets otherwise; the **front passing the stop sign** of a regular or request stop where the train does not stop. | trailing switches not limited; passing a request stop has no limit | missing; #211 for the switch |
| D12-V9 | A small-radius curve sign ("r") marks curves of **radius under 25 m: 15 km/h over the whole curve** (§ 49.19, p. 55). Curves already slowed by other rules (switches, crossings, loops) do not get the sign. | `curveSpeed` gives 10 km/h at R 20 m from 0.8 m/s² unbalanced (`src/route.js:109, 323-329`) | differs (the rule gives 15 below 25 m; the formula gives 10 at 20 m) |
| D12-V10 | The speed must also suit traffic, the track and wire, gradient and curvature, view, train mass, adhesion and the train's braking (§ 25.7). | – | general |
| D12-V11 | Steep gradients have no speed in D 1/2: the "dangerous gradient" signs (§ 49.9–12, p. 52–53) set rules for entering an occupied section and for starting (D12-G1…G3). Exam question PPS Q53 offers "at most 25 km/h" on a dangerous descent as a wrong answer. A **local** rule at Trojská (line 17, 470 m at 80.15 ‰) has trams roll down at **20–25 km/h** without power, one train per block ([web-notes.md](web-notes.md) 4.5). | 25 km/h below −6 %, 35 km/h below −4.5 % (`src/game.js:119-123`) | differs: 25 km/h is Trojská's local rule, applied everywhere; the 35 has no source |

Exam questions on the same speeds (D1 PPS set, valid from 2025-09-01, cited by question number):
Q64 (15 facing straight), Q65 (15 over crossings), Q68 and Q80 (15 trailing diverging), Q69 and Q81
(30 trailing straight), Q79 (15 under R 25 m), Q86 and Q87 (30 passing a stop sign), Q88 (night zone 22–6 h).

## Gradients (§ 49.9–12, p. 52–53; § 35.6, p. 34)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-G1 | **Climb of 80 ‰ or more** marked "Nebezpečné stoupání": enter only when no other train is seen in the section ahead (otherwise only on a dispatcher's order). Below 80 ‰ the driver may follow a train in, but stops so that the trains could still be handled if the one ahead stops. A train with an **accelerator** (*zrychlovač*, the T3) climbs the section at the **highest speed it can reach**, as safety and view allow. The red number is the gradient in ‰. | – | missing |
| D12-G2 | **Descent** marked "Nebezpečné klesání": enter only when no train is seen in the section. After every stop in it the train starts by releasing the parking brake and rolling by its own weight. On a **power cut** a train may roll on to the next stop, **except a train with an accelerator, which stops at once**. | a gradient board stands at grades under −5.5 % (`src/game.js:800-809`) | missing (the rules), differs (the board's look and where it stands) |
| D12-G3 | Leaving a train on 80 ‰ or more: parking brake and track brake on, then wheel chocks (*zarážky*), then the track brake off; the reverse before starting. | – | n/a |
| D12-G4 | **Safety stopping place** (sign: green border and green diagonal): every train stops with its front before it (§ 49.3); the website adds that the driver tests the parking brake there, and lists the places (line 17: Trojská Hercovka → Nad Trojou, both boarding stops of the Vozovna Kobylisy loop; [places.md](places.md)). | – | missing |

## Stopping and stops (§ 26–28, p. 23–26)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-S1 | **Where the first train stops**: its front **next to the stop sign or as close before it as it can**. A second or later train stops **at least 1 m behind** the one ahead, with its rear inside the stop area. | the front aims 6 m **past** the projected platform point; it may stand from 20 m behind to 12 m past the stop sign (`src/game.js:12-16, 1147-1155`) | differs: D 1/2 never puts the front past the sign |
| D12-S2 | At a stop where people board **from the roadway**, only the **first two** trains may stop at once. At a platform or island, as many as fit with the last door of the last train in the stop area; the **third and later train must stop again at the sign** to let people on and off. | AI trams stop 6 m behind the tram ahead (`src/traffic.js:1563-1709`) | partly |
| D12-S3 | **Request stop** (*na znamení*): approach at a speed that lets the driver see the stop clearly and stop smoothly. The train must stop if someone is in the stop area; if a passenger pressed the door-request button (or the signals for a disabled passenger, ramp, pram); if passenger information cannot be given by the information system; **if the train has no door-request buttons**; if a button is broken; at the last stop of a pull-in route. Otherwise it may pass at the set speed (30 km/h at the sign, D12-V8) with caution. | 55 % nobody waiting, 50 % nobody getting off; passing allowed when nobody needs the stop (`src/game.js:150, 1224`) | partly: no approach speed or 30 km/h at the sign; a T3 without request buttons must stop at every request stop (check which T3 the game is, [t3.md](t3.md)) |
| D12-S4 | Wheelchair user or person with a white cane at a regular or request stop: always stop at the sign and let them board. | – | missing |
| D12-S5 | **Announce the stop** with the on-board information system before entering it, at the latest when stopping. | – | missing (the driver starts the announcement on a T3) |
| D12-S6 | **Doors**: open all doors on the boarding side (or release them for the passengers' buttons where the train has them) for the time needed. | 3 doors per car, opened by the driver | in game |
| D12-S7 | **Before leaving a stop**: look along the whole train in the mirror or stop mirror, check the **doors-closed lamp**, and look along the train again. Where the cab gives no view along the train, get out and look. | power refused until the doors are closed (`src/main.js:544`) | partly |
| D12-S8 | Two parallel tracks with one shared stop sign: while the train on the far track is boarding, the train on the near track waits before the stop area. | – | n/a (check where it applies) |
| D12-S9 | Turning a train: no passengers between the last (alighting) stop and the first (boarding) stop unless ordered (§ 17.6, p. 17). | – | check how the game treats a terminus |
| D12-S10 | In a turning loop use its full capacity; a standing train must not block trains leaving the loop or running on parallel tracks (§ 26.4). | – | n/a |
| D12-S11 | Transfers (§ 28): at a transfer point all trains (and buses) may board together; the third and later train stops again on leaving. Without a dispatcher, departure only after all marked transfers. | – | n/a |
| D12-S12 | Stopping between stops to let people on or off is forbidden (staff excepted) (§ 26.2). | – | n/a |

## Timetable (§ 16, p. 17)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-J1 | **On time** means: from an intermediate stop (*nácestná*) **0 s early to 179 s late**; from a boarding stop (*nástupní*, the first stop) **0 s early to 59 s late** (PPS Q51). | early by more than 5 s: −(20 + min(200, 1.5·s)); up to 60 s late +40; up to 180 s +10; later a penalty (`src/game.js`, departure scoring) | partly: no 5 s grace in D 1/2; the 59 s class applies at the first stop only |
| D12-J2 | The driver keeps time from the car timetable (*vozový jízdní řád*) and the on-board computer; a difference between them is reported to the dispatcher (§ 14.2). | – | n/a |

## Driving (§ 32–33, p. 29–32)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-D1 | The driver must **use the train's inertia** (coast) (§ 32.1). | coasting is a kept skill; no score for it | in game (no score) |
| D12-D2 | No start before the doors are closed; no opening before standstill; no talking, eating, phone, music while driving (§ 33.4). | doors interlocked; −100 for doors open while moving | in game |
| D12-D3 | **Following distance**: the following driver keeps a distance in which he can stop safely, also behind road vehicles (§ 33.8). | no rule; only a collision counts (−400); the HUD warns under 25 m | missing (could be scored from braking distance) |
| D12-D4 | **Standing**: at least **1 m** between two standing trains, measured from the coupler head where couplers stick out (§ 33.9). | AI trams keep 6 m | partly |
| D12-D5 | **Starting in a queue**: start only when the train ahead is at a safe distance. With trains bunched, keep **more than 50 m** when starting (the supply could be overloaded), **more than 100 m** during supply failures, or wait until the train ahead has passed the nearest **section insulator** (§ 33.7). | – | missing (no power network) |
| D12-D6 | **Trolley-wire crossings**: pass without drawing traction current, with every pantograph up, where safely possible (§ 33.14). Section insulators: the same ([signals.md](signals.md) `SIG-W1`). | – | missing |
| D12-D7 | **Lights**: by day dipped beams or daytime running lights; in poor visibility timely exterior lights on every car and marker lights the whole time; front fog lights only in fog, snow or heavy rain; rear fog lights always then (§ 33.12). Interior lights in poor visibility, emergency lighting if the main fails (§ 33.13). | lights not modelled | missing |
| D12-D8 | Watch the track and wire; stop at once for a defect that could derail the train (§ 33.6). | – | n/a (could be an event) |
| D12-D9 | Report to the dispatcher a **supply failure over 179 s** and any stop of traffic expected over 179 s; the first train's driver reports, the others ask the driver ahead (§ 33.2–3). | – | n/a |
| D12-D10 | Doors opening by themselves while moving: stop at once (§ 33.10). | – | n/a (could be a fault event) |
| D12-D11 | Check the sand supply and refill it (§ 33.16). | sand box lasts 90 s of sanding (`src/tram.js`) | in game |

## Brakes (§ 34, p. 32–33)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-B1 | Brakes: **service** (electrodynamic) to slow and stop; **parking** (*zajišťovací*, mechanical) to hold a standing train; **track brake** (*kolejnicová*), independent of adhesion; **emergency braking** (*nouzové*) = service + track brake; **rescue braking** (*záchranné*) = parking + track brake + warning bell, which passengers can also set off. | brake notches −1…−4, −5 emergency with track brake and sand (`src/tram.js`) | partly (no separate parking brake or passenger emergency brake) |
| D12-B2 | **While standing**, the whole time, the brake pedal is in **"Zaparkováno"** (parked) or the hand controller at full service brake (§ 34.3). On a slope, the second step of the mechanical brake (§ 34.13). | brake notch 2 held while doors are open | differs |
| D12-B3 | The **track brake only when service braking cannot avert the danger** (§ 34.4). | the emergency notch includes it | could be scored: use without need |
| D12-B4 | **Slippery rail**: sand in time, use brake and drive steps moderately. **Wheelspin** under power: cut power, wait until the wheels match the speed, take a lower step, sand, repeat. **Slide** under braking: reduce or release the brake step and sand; if the parking brake is signalled on, release it and repeat; in danger, track brake and sand. Rolling back: sand in time, else track brake (§ 34.7–9). | wheelspin, locked wheels, sand, rollback modelled (`src/tram.js`) | in game (the procedure could be scored) |
| D12-B5 | **Track brake used on a switch**: stop, and before moving check the brake, the switch and that the switch was not thrown; if that cannot be checked, cross slowly with an instructed person watching (§ 34.10). | – | missing |
| D12-B6 | **Service brake failure**: stop with the parking brake (and sand), then the track brake if that is not enough (§ 34.11). | – | missing (fault event) |

## Leaving the cab, reversing (§ 35, 38, p. 33–35)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-L1 | Before leaving the train: brake pedal at "Zaparkováno", control off (or "ZAPNUTO" by type), direction switch to zero, cab windows and door closed, all doors closed (except at a boarding stop). Setting a switch by hand, using a signal's contact lock, the ramp, or walking to the train ahead does not count as leaving, but the train must still be secured (cab or first door closed). | switch iron: the driver walks at 1.6 m/s, at least 9 s (`src/game.js:1000-1023`) | partly |
| D12-L2 | **Reversing** (*couvání*, driven from a cab not at the front) needs an order outside DP's premises; a **backward movement** (*zpětný pohyb*, from the auxiliary or rear cab) over **2 m** too. 10 km/h. A coupled set reverses from the last car's cab where possible; a person guides it; check the service brake right after starting from the auxiliary cab. | – | n/a |

## Priority between trams (§ 23–24, p. 21–22)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-P1 | On **track off the road** without traffic signs: the tram **from the right** has priority (also one reversing); a tram **turning left** gives way to the oncoming one. | – | missing (AI trams at junctions) |
| D12-P2 | **Two trams approaching a trailing switch side by side**: the tram on the **right** track has priority. | – | missing |
| D12-P3 | **Single track and interlaced track**: do not enter while an oncoming train is in it; signals govern it, or sight where the whole section can be seen and priority signs are set. If the signals fail: priority signs and sight, otherwise the dispatcher's order. | single-track sections with one direction at a time, 6 s clearing, 45 s timeout, −300 for passing STOP, −600 head-on (`src/game.js:395-450, 640-681`) | in game |
| D12-P4 | Light signals for trams override traffic signs and the general priority rules (§ 42.8, § 43.13). | – | general |

## Passengers and interruptions (§ 17, 36)

| ID | Rule | Game now | Status |
|---|---|---|---|
| D12-E1 | Signal "Danger – stop by all means" or a passenger's emergency brake: stop at once, find the cause, report (§ 17.7–8). | – | missing (event) |
| D12-E2 | Between stops passengers are let out only if a delay is expected over **3 minutes** (obstacle, fault, power cut), for illness, fire, or an accident that ends the run (§ 36.2). | – | n/a |

## Not for the game

§ 3–12 (staff, documents, the driver's kit: whistle, universal crank, ID card), § 15 (dispatching),
§ 18–21 (special trains, orders, work sites, inspection), § 31 (shift start and handover), § 37
(heating standards: the dispatcher declares heating on and off), § 39–40 (towing, pulling in).
