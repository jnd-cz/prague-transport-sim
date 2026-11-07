# The T3SUCS: pedals, accelerator (*zrychlovač*), interlocks

Read 2026-11-03 for #215 (the user: "you can research that and how to simulate zrychlovač behavior"). Scope: the resistance-controlled T3 with ČKD electrical equipment
**TR 37** (*elektrická výzbroj TR 37*), used on T3, T3SU and T3SUCS ([imhd]; [cswikiT3] infobox).
The thyristor T3M has equipment **TV1** ([cswikiT3M]); the T3R.P has TV Progress; neither is
covered here. The German T3D had UB 13 equipment ([cswikiT3]).

The best source found is ČKD's own **T3SU equipment documentation** (scanned typescript, 1982 with
changes to 1986–1988), 30 parts, on a ČVUT student server ([ckd-dir]; linked from [cswikiZ] as
"original description"). T3SUCS is the Czechoslovak version of the T3SU (built 1983–1989 for
Czechoslovak cities, [cswikiT3] tables), so this set is the closest available to the Prague
T3SUCS. Prague-specific changes are not documented in it.

Conventions
- Paraphrased; Czech terms in italics. Source keys in square brackets are links (definitions at the
  end); "p." is the **PDF page** (for [ckd24] PDF p. 11 is a duplicate scan of p. 10, so PDF p. N ≥ 12
  is printed page N−1).
- Confidence: **[A]** manufacturer document; **[B]** professional textbook or exam; **[C]** wiki,
  forum, hearsay; **[calc]** my calculation from sourced numbers; **[inferred]** my reading of a
  circuit or text, not a sentence of a source; **[assumed]** a value proposed for the game with no
  source.
- "Car current" = total current of all four motors (two parallel branches, each two motors in series).
  The cab ammeter's shunt is in the 4M+3M group; its scale is said to show car current (3.8, 8.1).

## 0. Answers to the open questions of the brief (short)

| question | answer | source |
|---|---|---|
| drive pedal positions | 5 acceleration steps (*stupně zrychlení*), not detented, at 5°, 12°, 20°, 27°, 35° of 40°; each sets a current limit 220/290/360/420/480 A | [ckd16] p. 6, [ckd03] p. 4, [rubook] [A]/[B] |
| brake pedal positions | 5 electric brake steps at 3°, 7°, 12°, 18°, 23°; parking (*stanicování*, "zaparkováno") at 27°; track brake rear bogie ≈37°, both bogies at the stop 40° | [ckd16] p. 6, [ckd03] p. 6–8 [A] |
| shunting position | none on the pedals; the rear auxiliary station (*manipulační zpětný pojezd*) starts on drive step 2 and brakes on brake step 2 | [ckd03] p. 15 [A] |
| park / unpark | press to the station position and tip the pedal plate forward (toe) into a ratchet (*ozubec*); tip it back (heel) to release, springs return it to 0 | [ckd16] p. 1, [ckd03] p. 8 [A] |
| coast between drive and brake | ČKD recommends about 2–3 s of coasting between service braking and driving | [ckd03] p. 11 [A] |
| doors | a door relay contact (DBR, *relé blokování rozjezdu*) is in the line contactor circuit: an open door cuts traction at any speed; no brake from the doors | [ckd24] p. 7 (hand-added), [ckd-schema] (8.2), [mf1] [A]/[C] |
| dead-man | not on Czechoslovak T3 (dropped from the T2 design); the Soviet T-3 had a safety pedal; T3SU(CS) has a safety button (ČKD change 82-09-018 of 1982 replaced the pedal with it) | [cswikiT3], [rubook], [ckd03] p. 3, 7, [ckd-schema] |

## Game now (main at 7cac287)

| | Game (`src/tram.js`, `src/main.js`) | Sources (below) |
|---|---|---|
| controls | keys: drive notches +1…+4, brake −1…−4, emergency −5 (held), neutral | two pedals without detents: drive 5 steps at 5/12/20/27/35° of 40°, brake 5 steps at 3/7/12/18/23°, parking 27°, track brakes ≈37° (rear bogie) and 40° (both) |
| what a step sets | a force: drive 8.5 / 16 / 23 / 28.8 kN per car, limited by 172 kW·(0.4 + 0.15·notch); brake 7.5 / 14.5 / 21.5 / 28.8 kN | a **current** held by the limiting relay: drive 220 / 290 / 360 / 420 / 480 A per car (≈0.6–1.8 m/s² empty); brake step 5 340–360 A (≈1.2 m/s²) |
| how force builds | rate limits: drive +24 / −30 kN/s, brake +28 kN/s (90 in emergency) | the accelerator steps through 99 positions at ≈20 per second under the relay; damping resistors at the start; end of resistors at step 75 (≈26–37 km/h by step), then four field-weakening stages |
| coasting | neutral, no force | a small electric brake current ("příprava", 25–90 A by source, ≤ 0.14 m/s²) keeps the accelerator tracking speed |
| drive → brake | immediate | coast 2–3 s first (ČKD); too fast and the shoe brakes apply at speed |
| stopping | the electric brake's fade below 2.5 m/s changes only the readouts | on step 5 or parked, the shoe brakes take over below 120 A (≈4 km/h); after parking, full release only with the drive pedal |
| top speed | 65 km/h (force fades above 16.5 m/s) | 65 km/h empty on the level |
| doors | power refused until closed; brake notch 2 held while open | a door relay in the line contactor circuit blocks traction; no brake from the doors found |
| dead-man | optional dead-man pedal: emergency brake after 2.0 s, −50 | Czechoslovak T3s have none; a safety button instead |
| track brake | 44 kN per car in the emergency notch | 4 × FC33, 60 kN attraction each; emergency average ≈2.3 m/s² |

## 1. Sources

| key | what | date | reliability |
|---|---|---|---|
| [ckd03] | ČKD, *Funkce a obsluha elektrické výzbroje TR 37* (operation of TR 37), doc. T-50172, 15 p. | TKS/Vk-05/82, hand corrections later | [A], with crossed-out older text |
| [ckd24] | ČKD, *Popis funkcí elektrické výzbroje TR 37* (circuit function description), T-50413, 26 p. incl. traction circuit diagrams 3-40-507060 (PDF p. 26) | c. 1982, hand additions | [A] |
| [ckd17] | ČKD, *Zrychlovač typ TR 37/040* (accelerator), T-50408, 9 p. incl. auxiliary contact program | TKS/Vk-05/82 | [A] |
| [ckd16] | ČKD, *Šlapkový řadič typ HG 14* (pedal controller), T-50407, 6 p.; contact program 4-40-500174a with pedal angles (PDF p. 6) | 1982, drawing changed 11/86 | [A] |
| [ckd19] | ČKD, *Omezovací relé RC 36* (limiting relay), T-50937, 8 p. | TKS1 11/86 | [A] |
| [ckd18] | ČKD, *Řídící elektromotor typ E506* (pilot motor), T-50409 | 1982 | [A] |
| [ckd04] | ČKD, *Trakční motor TE 022*, T-50272, 14 p., characteristic 4-40-500171 (PDF p. 14) | 1982 | [A] |
| [ckd05] | ČKD, *Čelisťová brzda MB 225, brzdič BR 232 / LA 13* (drum brake and actuator), T-50273 | 1982 | [A] |
| [ckd22] | ČKD, *Kolejnicová brzda FC33* (track brake), T-50496 | 9/1988 | [A] |
| [ckd26] | ČKD, *TR 37 – Zkoušení ve voze* (tests in the car), T-50361, 7 p.; values marked "informative" | 1982 | [A] |
| [rubook] | Soviet textbook chapter *Электрическая схема вагона Т-3* (from *Электрооборудование трамваев и троллейбусов*), web copy with OCR errors | 1980s (not stated) | [B]; describes the Soviet T-3 (T3SU) incl. a safety pedal |
| [ruwiki] | ru.wikipedia *Tatra T3*, citing the book *Вагоны Т-3* (1977) for data | read 2026-11-03 | [C], data cited to [B] |
| [cswikiZ] | cs.wikipedia *Zrychlovač* (marked as insufficiently sourced) | read 2026-11-03 | [C] |
| [cswikiT3] | cs.wikipedia *Tatra T3* (cites Vandas 1969, Mara 2001) | read 2026-11-03 | [C] |
| [mf1] | milanfon.cz forum, user *jirkasta* (tram driver 3 years, moderator): basic control circuits of the T3, with schematics; he does not guarantee correctness | 2018-08-15/23 | [C] |
| [mf2] | same author: T3 traction circuits | 2018-08-27, 2018-10-24 | [C] |
| [imhd] | imhd.sk type description ČKD Tatra T3 (equipment, motor data) | read 2026-11-03 | [C] |
| [vsb] | Leksa M., *Elektrická trakce v kolejové MHD*, bachelor thesis VŠB-TU Ostrava, ch. 4.1 | 2017 | [B]/[C], secondary |
| [t3zr] | DP Praha exam *T3 – zrychlovač* (22 questions) | valid from 2023-08-23, file 2026-02-01 | [B] |
| [ucebnice] | DP Praha training booklet *Tramvaje T3.SUCS, T3M, T3R.P, T3R.PLF*; notes in [t3.md](t3.md) | 2009 | [B] |
| [prco] | Pittsburgh Railways mailing list: J. Holland on the PCC (Westinghouse) accelerator | 2007-09-01 | [C] |
| [rypn] | Railway Preservation forum: PCC limit relay settings quoted from GE GEI-21676 and Westinghouse R-994 | 2020-01 | [C] quoting [A] |
| [tmsv] | Tramway Museum Society of Victoria, *ČKD-Tatra* (brochure data) | c. 1967–68 (inferred) | [B] |
| [ckd-schema] | ČKD, *Základní schema tramvaje T3SU/ČSSR*, drawing 1-38-370 444, issue F, one sheet (`T3SU-schema.pdf`) | drawn 1981-11-10, revised to 1987-03-10 | [A] |

The ČKD parts are scans without a text layer: every number was read from the page images (PDF page
cited). Checked again for this note: the step currents ([ckd03] p. 4) and the drive pedal angles
([ckd16] p. 6).

Searched without result: a description of the accelerator's sound; Czech/Slovak theses on the TR 37
accelerator in detail (only [vsb], secondary); tram-forum threads (not reached). The complete
wiring diagram ([ckd-schema]) was read on 2026-11-04: section 8.

## 2. Pedals (*šlapkový řadič* HG 14)

Hardware ([ckd16] p. 1, 3–4) [A]: one pedal controller in the cab, two pedals: **drive** (*šlapka
jízdní*, right) on a hollow shaft with cam discs, **brake** (*šlapka brzdová*, left) on a shaft
inside it. Both return to the top rest position by springs; working angle about 40°. Contacts: 6 on
the drive drum (JK1–JK6), 10 on the brake drum (BK1–BK10), 24 V, 6 A. Rest positions: drive lever
13°, brake lever 20° below horizontal. Program tolerance ±10 % in intermediate positions. Russian
book: the positions are not fixed (*нефиксированные*), i.e. no detents ([rubook]) [B].

### 2.1 Drive pedal

| step | pedal angle [ckd16] p. 6 | current limit, car [ckd03] p. 4 | acceleration, empty car [rubook] | how the limit is set [ckd24] p. 12 |
|---|---|---|---|---|
| 0 | 0° | – | coasting | – |
| (pre-step) | ≈1–3° (JK2, JK6 close) | – | none | prepares R1 circuit, maximum-relay hold |
| 1 | 5° (JK1 closes: M1, LS) | 220 A ±5 % | ≈0.6 m/s² | regulating coil RC on full 24 V |
| 2 | 12° | 290 A ±5 % | ≈0.95 m/s² | divider RP1–3 via JK4 |
| 3 | 20° | 360 A ±5 % | ≈1.2 m/s² | divider via JK4+JK5 |
| 4 | 27° | 420 A ±5 % | ≈1.5 m/s² | divider via JK5 |
| 5 | 35° | 480 A max | ≈1.8 m/s² | RC switched off |
| max | 40° | as 5 | as 5 | – |

- [rubook] gives 200–230 A on step 1 and 280–300 A on step 2; [ckd26] p. 4 sets step 1 to 220–240 A
  and step 5 to 460–480 A in the depot. The step-1 setting depends on the battery voltage feeding RC:
  240 A at 26 V, 250 A at 25 V, 260 A at 24 V, 270 A at 23 V ([ckd26] p. 4) [A].
- The forum describes the pre-step circuit as closing "about half way between the zero stop and the
  first acceleration step" ([mf1]) [C]; the drum program shows JK2/JK6 closing just off zero
  ([ckd16] p. 6) [A].
- The pedal only selects the current (= acceleration). Whatever step is chosen, the car runs up to
  its balancing speed: 65 km/h empty on the level ([ckd03] p. 2, 4) [A]. Every step ends with full
  field weakening ([rubook]) [B].
- No shunting (*posun*) position, no series/parallel transition: the two motor pairs are permanently
  in parallel, each pair in series ([ckd24] p. 3; [cswikiZ]) [A].
- Driving advice from the manufacturer ([ckd03] p. 4–6) [A]:
  - Do not select a high or the highest step at once, let go, and press again: current peaks (up to
    480 A) and the car "jerks" (*trhání vozu*), because the selected acceleration turns at once into
    coasting with deceleration. From a high step, go back through a lower step before coasting.
  - Normally, especially on the level, steps 1 to 3 suffice (about 300 A, max 360 A); higher steps only
    at higher speed, where they hardly raise the current.
  - Small accelerations lower the current peaks but use more energy; large ones save energy.
  - Coast as much as possible, e.g. into stops; enter curves coasting at the speed for the radius,
    restart on a low step about mid-curve, a higher one just before the exit.
- Gradients: service on up to 80 ‰, exceptionally 90 ‰ for at most 800 m (car up to 28 t). On
  gradients over 45 ‰ keep distance so the climb is made with the resistors cut out, without stopping
  and restarting on the gradient ([ckd03] p. 3–4) [A]. Prague practice: starting uphill at Nad Trojou
  needs the full pedal; speed limits on long descents (Trojská 20–25 km/h); some lines banned for
  these cars ([cswikiZ]) [C].
- Drive is impossible while the brake pedal is off zero: brake contact BK2 is in series in the M1 and
  LS coil circuits ([ckd24] p. 7) [A]; so pressing both pedals gives braking only [inferred].

### 2.2 Brake pedal

| position | angle [ckd16] p. 6 | what happens | source |
|---|---|---|---|
| 0 | 0° | released; LO relay voltage coil fed (BK8) → BR2 → shoe brake partly released; full release only after drive (M1 → BR1) | [ckd24] p. 6, 15–16 [A] |
| off zero | ≈2° | BK2 opens: drive circuits dead, field shunt F2 off → resistor RCP into the preparation coil → limiting relay set for brake currents | [ckd24] p. 14 [A] |
| 1 | 3° | electric brake step 1 (BK3) | [ckd16] p. 6 |
| 2 | 7° | step 2 (BK3/BK4); BK9 opens just past step 2 | [ckd16] p. 6 |
| 3 | 12° | step 3 (BK4/BK5) | [ckd16] p. 6 |
| 4 | 18° | step 4 (BK5); BK8 opens between 18° and 23° | [ckd16] p. 6 |
| 5 | 23° | BK3, BK4, BK5 all open, RC off: maximum brake current 340–360 A; LO now held only by its series coil (automatic shoe brake below ≈4 km/h) | [ckd26] p. 4, [ckd24] p. 15–16, [rubook] |
| parking, *stanicování* | 27° ("St.", the "middle" or "half" of the stroke in the text) | ratchet lock by tipping the plate; car held by the shoe brakes; pedal out of action | [ckd03] p. 6, 8; [ckd16] p. 1 [A] |
| track brake 1 | ≈37° (BK7 → contactor K2) | track brakes of the **rear** bogie at full force | [ckd24] p. 16; [ckd03] p. 7 [A] |
| track brake 2 | ≈40° (BK6 → K1), pedal at its stop | track brakes on **both** bogies | same |

- Five selectable electric brake steps ([ckd03] p. 6; [ckd24] p. 14; [rubook]) [A]. Only the step-5
  current is documented (340–360 A, at ≈25° in the test). Steps 1–4: inferred from the wiring
  diagram as 160 / 211 / 262 / 306 A (8.2).
- The electric brake works above about 4 km/h; below it the motor shoe brake (*motorová čelisťová
  brzda*) stops the car by itself ([ckd03] p. 6–7) [A]. DP Praha: comes in by itself at 5–3 km/h
  ([ucebnice] via [t3.md](t3.md)) [B].
- Emergency brake (*nouzová brzda*) = pedal pressed at once to its end: electric + track brakes,
  shoe brakes join at the end ([ckd03] p. 7) [A].
- Contacts BK1 (closed from the station position to the end) and BK10 (closed from ≈2° to the end)
  exist; their purpose is not described in the pages read (probably signalling, e.g. brake lights)
  [inferred].
- Wording differences: [ckd24] p. 15 says LO is held only by its current coil "from the 3rd brake step";
  the HG 14 program (BK8 open from ≈20°) and [rubook] ("BK8 (0–4)") say from step 5; the forum says
  "near the 5th step, close to the parked position" ([mf1]). Step 5: the wiring diagram's program
  opens BK8 between steps 4 and 5 (8.3); the drawing carries a change of 11/86.
- Parking at higher speed is "bad style" that wears the linings (forum, [mf1]) [C]. ČKD's own brake
  test pushes the pedal into the station position from 30–50 km/h and measures the electric brake
  ([ckd26] p. 5) [A], so parking at speed brakes electrically first.

### 2.3 Safety devices

- **No dead-man pedal on Czechoslovak T3s**: the T3 dropped the *šlapka bdělosti* of the T2
  ([cswikiT3] citing Vandas 1969, p. 77–78) [C/B]. In the ČKD T3SU texts the vigilance pedal is
  crossed out and replaced by a **safety button on the driver's stand** (*bezpečnostní tlačítko*)
  ([ckd03] p. 3, 7; [ckd24] p. 5) [A]. The ČKD test sheet still lists a braking test "by the vigilance
  pedal": track + shoe brakes, about 2.3 m/s² ([ckd26] p. 5) [A].
- The Soviet T-3 had a safety pedal (*педаль безопасности*): released → safety relay drops → drive
  off, shoe brakes, track brakes, bell ([rubook]; [ruwiki]) [B].
- **Rescue brake** (*záchranná brzda*): buttons at the middle and rear doors and the driver's safety
  button drop the safety relay RB → LS and M1 open (no traction), BR1/BR2 open (full shoe brake),
  K1 and K2 (all track brakes), warning bell ([ckd03] p. 7; [ckd24] p. 17) [A]. DP Praha: plus the
  electric brake if the brake pedal is parked ([ucebnice] via [t3.md](t3.md)) [B].
- Rear auxiliary station for reversing/coupling ([ckd03] p. 15) [A]: buttons JT+BT = start on drive
  step 2; BT = braking on step 2; BS = rescue brake; TZV = bell; VDV = doors. Activated with the main
  stand's control switch on, brake pedal parked, direction switch to "back".

## 3. The accelerator (*zrychlovač* TR 37/040)

### 3.1 What it is ([ckd17] p. 1, 4, 6) [A]

- A multi-step, automatically driven **resistor** in the main motor circuit, used for starting and
  for electric braking. An insulating cylinder carries **99 sprung contact fingers** (*palce*) on its
  inner side; radial bolts connect each finger to resistor elements on the outside. Inside, a
  **rotating cross** (*otočný kříž*) on a vertical shaft carries **two opposite rollers** that press
  fingers onto a **copper collector ring**. The cross is turned through a **worm gear** by the **pilot
  motor** (*řídící elektromotorek*, *pilotmotor*). Enclosed, blown permanently by the
  motor-generator fans.
- Data: 99 steps, total resistance **3.614 Ω**, max current **480 A**, cooling air 2 × 28 m³/min,
  192 kg (Russian source: 180 kg, [ruwiki]).
- Elements: types KA (0.9 mm strip) and KB (0.8 mm). Odd fingers 3–99 carry 1.825 Ω, even fingers
  4–98 1.789 Ω, in groups of 9–15 elements (≈0.035–0.041 Ω per element, so roughly uniform per step).
- When one roller presses one finger, the opposite one must press two; the steps therefore alternate
  between the two halves. Roller force on a finger 300 ± 30 N; finger stroke 3 mm.
- [cswikiZ] calls the contact cross the *osmička* ("figure eight"), turning 180°, the two halves
  regulating independently and connected in parallel [C]. [ckd24] p. 26 draws the accelerator as two
  strips, entered at end "A" from M1 and left at end "B" toward R1/R2 in drive, and connected between
  brake contactors B2 and B1 in braking, "returning from B to A" ([ckd24] p. 4) [A]. How the halves are
  wired (series or parallel, which ends) is not stated in text (Open questions).
- PCC heritage: the Westinghouse PCC accelerator also had 99 points, turned about 180° by a pilot
  motor, and was set for dynamic braking when the power pedal was released ([prco]) [C].

### 3.2 Pilot motor ([ckd18] p. 1; [ckd24] p. 10; [ckd17] p. 5) [A]

- E506: DC, 26 W (15 min rating), 300 rpm, armature 10.5 V / 6 A, field 24 V (fed whenever control is
  on). Armature fed from the **battery mid-point** through fuse, contactor R2 (drive) or B2 (coasting /
  braking, reversed polarity), auxiliary accelerator contacts, the limiting relay contact and the
  regulating resistor RPM; a resistor RSh permanently bridges the armature.
- **Running speed: 1 → 99 in 5 ± 0.5 s, and 99 → 1 in 5 ± 0.5 s**, set in the shop at 24 V with the
  armature series resistor ([ckd17] p. 5). That is ≈20 steps/s, ≈0.05 s per step [calc]. The rate in
  the car (10.5 V armature supply) is not stated separately (Open questions).
- The pilot motor is switched without contacts by a transistor switch driven by the relay contact
  (RC 36 version of 11/86, [ckd19] p. 1, 3) [A].

### 3.3 Limiting relay RC 36 (*omezovací relé* OR): how stepping is controlled

Four coils on one core ([ckd19] p. 2–3; [ckd24] p. 10) [A]:

| coil | turns | rating | connected | role |
|---|---|---|---|---|
| OR, current coil (*proudová*) | 2 | 250 A | in series with **one motor group** (4M+3M) | main: pulls the armature with motor current |
| RC, regulating (*regulační / řídící*) | 3550 | 210 Ω, 0.2 A | from a resistor divider RP1–3 (30 Ω) via RCR (210 Ω), switched by the pedal contacts | sets the current limit; acts in the same sense as OR against the spring, so more RC current = lower traction current |
| PC, interrupter (*přerušovací*) | 16 | 0.061 Ω, 4 A | carries the pilot-motor armature current | makes the moving contact vibrate constantly → pulsed, stable regulation and instant stop |
| CP, preparation (*přípravy*) | 160 | 0.95 Ω, 2 A | across the field windings of one motor group, via contacts F2 and B1 (coasting and braking only); RCP 42 Ω in series when braking | lets the relay regulate the tiny coasting current |

- Action: below the set current the moving contact touches one fixed contact → pilot motor advances
  (resistance cut out); at the set current it lifts → the motor stops; the relay chatters at this
  point. If the current far exceeds the setting, the contact touches the other side → the motor runs
  backwards and re-inserts resistance ([ruwiki], drive description; [ckd24] p. 13 for coasting) [C]/[A].
- Accuracy: the current is held within ±5 % on every step ([ckd03] p. 4; [rubook]) [A]/[B].
- Result: constant current and constant motor torque while on resistors, i.e. constant acceleration
  set by pedal depth; the driver can sit ([cswikiZ]) [C]; ČKD: "the limiting relay keeps a constant
  starting current proportional to the pedal depression" ([ckd03] p. 2) [A].
- The PCC equivalent: Westinghouse "limit relay", GE "accelerating and braking relay"; settings per
  motor group about 250–265 A in acceleration and 165–180 A in braking; GE coasting load 27–28 A
  ([rypn]) [C].

### 3.4 Starting sequence and positions (drive)

From [ckd24] p. 3–9, [rubook], [mf1] [A]/[B]/[C]:

1. Brake pedal unparked to 0 → LO → BR2 (shoe brakes partly released); F2 closed (field shunt on
   motors 1M+2M).
2. Drive pedal to step 1: JK1 → **M1** (motors to the accelerator) → its rest contact drops brake
   contactors B1/B2 → **line contactor LS** closes (conditions: brake pedal at 0, reverser set,
   charging contactor SN = motor-generator running on line voltage, door relay DBR, maximum relay MR
   not tripped, safety relay RB up). M1 also closes **BR1** → shoe brakes fully released.
3. LS → **R1** bypasses damping resistor 1 (0.35 Ω); R1 → **R2** bypasses resistor 2 (0.7 Ω) and opens
   F2 (field shunt off). The dampers and the brief field shunt soften the first current rush and take
   up gear backlash ([ckd24] p. 7; values from [ckd-schema], [rubook] has 0.7 + 0.7 Ω). The cs.wiki
   says they are bridged
   "within the first seconds" ([cswikiZ]) [C].
4. The pilot motor turns the accelerator from step 1 upward under the limiting relay.
5. **Step 75: contactor M2 bridges the whole accelerator** ([ckd24] p. 8; [ckd03] p. 2). The
   accelerator lamp (auxiliary contact ZR1) goes out. Forum: at about 30–35 km/h, checked in service
   ([mf1]) [C]; cs.wiki: about 35 km/h ([cswikiZ]) [C]. Calculated end-of-resistor speed per step:
   37/32/29/27/26 km/h for steps 1–5 [calc, section 5.3].
6. **Field weakening, 4 stages**, still under the limiting relay, staggered between the bogies
   ([ckd24] p. 8; [rubook]): 80 → F4 (1st stage, motors 2M+1M); 85 → F1 (1st stage, 4M+3M); 90 → F3
   (2nd stage, 4M+3M); 95 → F2 (2nd stage, 2M+1M). The accelerator's own contact program drawing
   shows the contacts at about 85, 89, 93 and 97 instead ([ckd17] p. 9, scan reading) [A, low
   legibility]; the wiring diagram's program reads 80 / 85 / 90 / 95 clearly (8.3). Motor field at
   full weakening 55 % ([ckd04] p. 2); the intermediate stage is not given.
7. **Step 97**: contact ZR7 cuts the pilot motor; the cross coasts on to **99** and stays
   ([ckd24] p. 12; [rubook]). From then on the car runs on the motor characteristic ("on the
   trolley", [mf2]) up to 65 km/h; letting the pedal partly back has no effect until it returns to 0
   ([ckd24] p. 12) [A].

Auxiliary accelerator contacts ([ckd17] p. 9, [ckd-schema]) [A]: ZR1 lamp (1–80); ZR2 M2 (75–99);
ZR3/ZR4/ZR5/ZR6 field stages; ZR7 pilot motor stop at 97; ZR8 pilot-motor return path (3–99); ZR10
holds BR1 (3–99); ZR9 (1–30) enables the switch button (8.3).

### 3.5 Coasting (*doběh*) and "preparation" (*příprava*)

- Pedal back to 0 ([ckd24] p. 8–9; [rubook]; [mf1]): JK1 opens but R2 keeps LS and M1; just before
  zero JK2 opens → R1 drops → R2 drops → the two damping resistors come back in (traction force and
  current fall softly) → only then LS and M1 open. Then B1 and B2 close and F2 closes again.
- In coasting the motors are **never fully disconnected**: B1/B2 form two **cross-connected brake
  loops** (armatures of one pair feed the fields of the other pair, through the accelerator) — the T3
  "has no pure coasting" ([rubook]) [B]; [ckd24] p. 4, 13 [A].
- The preparation coil CP (RCP bridged by F2) makes the limiting relay hold a **small brake current**;
  B2 reverses the pilot motor so the accelerator moves back from 99 toward 1 as speed falls, keeping a
  position that matches the speed ([ckd24] p. 12–13) [A].
- If speed rises when coasting downhill, the coasting current rises, the relay touches its other
  contact and the accelerator moves up (more brake resistance) until the current is small again
  ([ckd24] p. 13; [rubook] "until 25–30 A") [A]/[B].
- Size of the coasting current — sources disagree:
  - ČKD: a "negligible" brake current, practically no effect on speed ([ckd24] p. 13) [A].
  - [rubook]: relay setting (25 ± 5) A, coasting deceleration from it at most 0.14 m/s² [B].
  - [ruwiki]: 30–60 A [C]. Forum: about 50 A ([mf2]) [C].
  - DP Praha exam: 40–90 A (ammeter) ([t3zr] Q2) [B]. The ammeter shows car current (3.8), so the
    Russian 25 A may be per motor group (≈50 A on the ammeter) [inferred].
- Purpose: when drive or brake is selected again, the part of the resistance matching the speed is
  already cut out, so the car responds without delay ([ckd03] p. 2, 5–6) [A]. "The lower the speed,
  the larger the part of the resistors cut out" ([ckd03] p. 5, said of the brake) [A].
- In coasting F2 shunts the fields of 1M+2M so that the accelerator's resistance suffices at high
  speed when braking ([ckd24] p. 9) [A]; [rubook]: this also reduces the coasting brake force [B].
- Section insulators and trolleybus crossings must be passed coasting, pedal at 0 ([ckd03] p. 11) [A].
- Loss of line voltage: SN drops → LS, M1, M2 out → car coasts; when voltage returns the car restarts
  through the damping resistors ([rubook]; [ckd24] p. 5) [B]/[A].

### 3.6 Electric braking

- Brake pedal off zero: BK2 opens → F2 out → RCP (42 Ω) in series with CP → the relay is now set for
  brake currents; circuits as in coasting; pilot motor control as in coasting; BK3/BK4/BK5 replace
  JK3/JK4/JK5 to give five current settings ([ckd24] p. 14) [A].
- The accelerator runs back toward step 1 as speed falls, cutting out brake resistance to keep the
  current (and deceleration) constant; all 99 steps are used in braking, 76–99 only in braking
  ([ckd03] p. 2; [cswikiZ]; [rubook]) [A]/[C].
- Brake loops: motors 1M+2M armatures → B2 → accelerator → B1 → OR coil → fields 3M+4M → back; the
  second loop likewise with 3M+4M armatures and 1M+2M fields; the cross connection stabilises the
  brake ([ckd24] p. 4) [A].
- **Fade-out and shoe brake**: relay LO has a voltage coil (fed through BK8 at brake steps 0–4) and a
  series coil in the brake circuit. From step 5 (see 2.2 for the step-3 variant) only the series coil
  holds it; when the brake current falls below **120 A ±5 %** (about **4 km/h**) LO drops, BR1 and
  BR2 open and the shoe brakes apply fully ([ckd24] p. 15–16; [rubook]) [A].
- BR1 (full release) is held by its own contact while BK9 (brake steps 0–2) **or** ZR10 (accelerator
  3–99) is closed. So braking on step 3 or more drops BR1 when the accelerator reaches step 2
  (very low speed): shoe brake stage 1 [inferred from [ckd24] p. 15].
- On steps 1–2 (and up to 4 by the HG 14 program) LO stays up through its voltage coil, so the shoe
  brake does **not** come in automatically; the electric brake simply fades [inferred]. To stop, the
  driver goes to step 5 or parks.
- After a stop in the parked position: return the pedal to 0 → LO → BR2 → partial release (shoe brake
  stage 1 still on); **full release only when the drive pedal is pressed** (M1 → BR1) ([ckd24] p.
  16; [rubook]) [A]. Stage-1 shoe brake on a gradient: DP Praha warns that a pedal let go instead of
  parked releases the shoes and the car rolls (T3R.P / T3M remarks in [ucebnice]) [B].
- If the electric brake fails, the shoe brake takes over by itself; the car must then be taken out
  of service ([ckd03] p. 7) [A].
- **Fast change drive → brake**: DP Praha: the electric brake drops out and the mechanical brake comes
  in early ([ucebnice] via [t3.md](t3.md)) [B]. ČKD: wait about 2–3 s coasting between service braking
  and driving ([ckd03] p. 11) [A]. Mechanism [inferred]: right after drive the brake loops are not yet
  self-excited and the accelerator is not yet at the speed position (it moves at most ≈20 steps/s);
  on brake step 5 or parked, LO is held only by its series coil, so while the brake current is below
  120 A LO drops and the shoe brakes apply at speed; they stay partly on until the pedal is back at 0
  and the drive pedal pressed.
- Faults ([cswikiZ]; [ruwiki]) [C]: a **stuck finger** (*připečení palce*) after wheel slip/slide or
  after pressing a pedal before the preparation current settled shows as too much coasting current —
  the car brakes when it should coast; the Russian article: the car starts and brakes abruptly.
  **Burnt resistor bands**: long starts uphill on a low step, long braking downhill, cooling failure.

### 3.7 Protection

- Maximum relay MR in the line contactor: trips at **750 A**, opens LS; held tripped by a 24 V coil
  until the drive pedal returns to 0 (JK6 opens); pressing again restarts ([ckd24] p. 9; [rubook];
  [mf2]) [A]. An overcurrent lamp (*kontrolka nadproudu*) appears in DP Praha exam answers ([t3zr]
  Q5, as an answer option; T3M question tech Q2867 in [t3.md](t3.md)) [B].
- Differential relay between the two motor groups for partial earth faults ([rubook]; [ruwiki]) [B].
- Driving with a failed motor-generator (no cooling): fuse out, hold the "washing plant" button,
  maximum acceleration, few restarts, empty car, to the nearest depot only ([ckd03] p. 14) [A].

### 3.8 What the driver sees and hears

- **Ammeter**: shunt in the 3M+4M group, scale calibrated for the total of all four motors, 600 A
  ([ruwiki]) [C]. So readings are car current: 220–480 A when starting, ≈40–90 A coasting ([t3zr]),
  up to ≈350 A braking. Whether braking deflects the needle the other way is not stated.
- **Accelerator lamp** (*kontrolka zrychlovače*): lit while running on the accelerator resistors, out
  when M2 bridges it ([ckd03] p. 9; [mf1]; [t3zr] Q3). [ruwiki]: it warns against overheating the
  resistors [C].
- Shoe-brake lamps, one per bogie plus one for the second car ([ruwiki]); door lamp; line-voltage glow
  lamp ([ckd03] p. 9) [A]/[C].
- **Sound**: no source describes it. Physically present [assumed]: contactor clunks in quick sequence
  at start (M1, LS, R1, R2), M2 at the end of the resistors, four field-shunt clicks, LS/M1 out and
  B1/B2 in at coasting; the pilot motor and worm gear whirring whenever the cross moves (a full sweep
  takes ≈5 s; fingers pressed at up to ≈20 per second); constant motor-generator and fan hum; the
  shoe-brake actuators thumping in at ≈4 km/h. Holland saw the PCC accelerator follow the pedal "with
  no visible lag" ([prco]) [C].

## 4. Door and other interlocks

- **Doors block traction**: a break contact of the door relay DBR (*relé blokování rozjezdu*, start
  blocking relay) sits in the coil circuit of the line contactor LS ([ckd24] p. 7, handwritten
  addition) [A]; the forum calls it the check of closed doors ([mf1]) [C]. With a door open LS cannot
  close, so no traction.
- **Doors and brakes**: no source says an open door applies a brake on T3SU/T3SUCS. If a door opened
  while running, LS would drop and the car would coast with the preparation current [inferred]. (On
  the T3M, door 1 opened while moving applies the shoe brake — T3M only, [ucebnice] via [t3.md](t3.md).)
  The wiring diagram shows no speed condition (8.2).
- Door indication: lamp lit when all doors are closed ([ckd03] p. 9) [A]; [ruwiki]: lamp for "a door
  not closed" [C].
- Other conditions for LS ([ckd24] p. 7) [A]: brake pedal at 0 (BK2), drive pedal ≥ step 1 (JK1),
  reverser in a running position, SN (motor-generator on line voltage), M1 in (B1 out), MR not tripped,
  safety relay RB up.
- Reverser and controller have no mechanical interlock; moving the reverser while running is possible
  but forbidden ([ruwiki]) [C].
- Electric points (*elektrické ovládání výhybek*): the button TV, through a contact of M1, closes
  contactor SV, which draws line current through the points resistor RV and R1/R2 so the overhead
  points contact registers current; the button must not be held over 10 s ([ckd24] p. 18; [ckd03]
  p. 10–11) [A]. The diagram puts M1's rest contact and ZR9 (accelerator 1–30) in series with TV:
  drive off, below about 12 km/h (8.2).

## 5. Numbers for the simulation

### 5.1 Table

| quantity | value | unit | source | confidence |
|---|---|---|---|---|
| line voltage | 600 | V | [ckd24] p. 3 | A |
| motors | 4 × TE 022, DC series, 2 in series per bogie, bogies in parallel | – | [ckd24] p. 3; [ckd04] p. 1 | A |
| motor rating | 40 kW, 300 V, 150 A, 1750 rpm (hourly 45 kW per [ruwiki]) | – | [ckd04] p. 2 | A |
| motor max speed | 4200 | rpm | [ckd04] p. 2 | A |
| field weakening | 100 / 55 % (chart drawn for 50 %) | – | [ckd04] p. 2, 14 | A |
| gear ratio | 7.43 (hypoid; also 7.36 plain two-stage, 9.36 "mountain") | – | [ruwiki] citing *Вагоны Т-3* 1977; 7.43 on [ckd-schema] | A |
| wheel diameter | 700 new (min. 600 turned) | mm | [ruwiki]; [vsb] | B |
| speed per motor rpm | 1750 rpm = 31.1 km/h; 4200 rpm = 74.6 km/h (ratio 7.43, 700 mm) | – | – | calc |
| max speed | 65 (empty, level) | km/h | [ckd03] p. 4; [imhd] | A |
| empty mass | 16 (Prague booklet); 17.0 (Soviet T-3 book) | t | [ucebnice]; [ruwiki] | B |
| drive current limits steps 1–5 | 220, 290, 360, 420, 480 (±5 %) | A (car) | [ckd03] p. 4 | A |
| acceleration steps 1–5, empty | 0.6, 0.95, 1.2, 1.5, 1.8 | m/s² | [rubook] | B |
| max acceleration, empty | 1.8 | m/s² | [tmsv] | B |
| brake current step 5 | 340–360 | A (car) | [ckd26] p. 4 | A |
| electric brake, avg decel from 30–50 km/h, pedal in parking position | ≈1.2 | m/s² | [ckd26] p. 5 | A |
| electric brake range over 5 steps | 1.4–1.8 | m/s² | [rubook] | B |
| max service decel, empty | 1.8 | m/s² | [tmsv] | B |
| emergency brake (pedal to the end), avg | ≈2.3 | m/s² | [ckd26] p. 5 | A |
| max decel, empty | 5 | m/s² | [tmsv] | B (conditions unknown) |
| electric brake works down to | ≈4 | km/h | [ckd03] p. 7 | A |
| shoe brake cuts in | brake current < 120 A ±5 % (≈4 km/h); DP Praha: 5–3 km/h | – | [ckd24] p. 16; [ucebnice] | A/B |
| coasting (preparation) current | 25 ± 5 (relay) / 30–60 / 40–90 (ammeter) / ≈50 | A | [rubook]; [ruwiki]; [t3zr]; [mf2] | disagree |
| coasting decel from preparation | ≤ 0.14 | m/s² | [rubook] | B |
| accelerator steps | 99 total; drive 1–75 resistive, 80–95 field stages; brake 1–99 | – | [ckd17] p. 1; [ckd24] p. 8 | A |
| accelerator resistance | 3.614 total (brake), 2.835 in drive; ≈0.037 per position | Ω | [ckd17] p. 1, 6; [ckd-schema] | A / inferred |
| accelerator full sweep | 5 ± 0.5 each way (≈20 steps/s) | s | [ckd17] p. 5 | A (shop setting) |
| M2 (end of resistors) | step 75; 30–35 km/h (forum), ≈35 km/h (cs.wiki); 26–37 km/h by step | – | [ckd24] p. 8; [mf1]; [cswikiZ]; 5.3 | A/C/calc |
| damping resistors R1, R2 | 0.35 + 0.7 (Soviet car 0.7 + 0.7) | Ω | [ckd-schema]; [rubook] | A |
| brake currents steps 1–5 | 160, 211, 262, 306, 350 | A (car) | step 5 [ckd26] p. 4; 1–4 inferred (8.2) | A / inferred |
| switch button | drive off and accelerator at 1–30 (≈ below 12 km/h); RV ≈3.5 Ω, 63 A fuse, ≈80–130 A, ≤ 10 s | – | [ckd-schema]; [ckd24] p. 18 | A / calc |
| pilot motor | 26 W, 300 rpm, 10.5 V armature, 24 V field | – | [ckd18] p. 1 | A |
| maximum relay | 750 | A | [ckd24]; [rubook]; [mf2] | A |
| drive pedal angles, steps 1–5 / max | 5, 12, 20, 27, 35 / 40 | ° | [ckd16] p. 6 | A |
| brake pedal angles, steps 1–5 / park / track 1 / track 2 | 3, 7, 12, 18, 23 / 27 / ≈37 / 40 | ° | [ckd16] p. 6 | A |
| track brakes | 4 × FC33 (2 per bogie), 60 kN attraction each, 24 V battery, 0.632 Ω | – | [ckd22] p. 1; [ckd24] p. 16 | A |
| shoe brakes | MB 225 on each motor shaft, drum 280 mm, spring-applied, solenoid-released (BR 232: spring 1320 N, rod force 540 N) | – | [ckd05] p. 1, 3 | A |
| gradients | up to 80 ‰ (90 ‰ for ≤ 800 m) | – | [ckd03] p. 3 | A |
| between brake and drive | coast 2–3 | s | [ckd03] p. 11 | A |
| ammeter | shunt in the 4M+3M group's lead; 600 A scale for car current | – | [ckd-schema]; [ruwiki] | A / C |

### 5.2 TE 022 characteristic at 300 V (read from the scanned chart, [ckd04] p. 14, ±5 %)

| motor current A | 60 | 80 | 100 | 125 | 150 | 175 | 200 | 250 | 300 | 350 | 390 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rpm, full field | 3280 | 2610 | 2170 | 1945 | 1775 | 1670 | 1570 | 1430 | 1320 | 1235 | 1165 |
| torque Nm, full field | ≈45 | ≈72 | 125 | 168 | 216 | 267 | 330 | 466 | 574 | ≈680 | ≈750 |
| rpm, weakened field (50 %) | – | – | ≈4000 | 3460 | 3090 | 2820 | 2610 | 2300 | 2100 | 1910 | 1720 |
| torque Nm, weakened field | – | – | 62 | ≈95 | 133 | ≈175 | 216 | 307 | 406 | 511 | ≈550 |

Check: 150 A, 1775 rpm, 216 Nm = 40 kW, the rating [calc].

### 5.3 Cross-check [calc]

Car current = 2 × motor current. Rail force = 4 × T × 7.43 × 0.97 / 0.35 m. Mass 17 t, rotating-mass
factor 1.15 [assumed], rolling resistance 0.004 [assumed]:

| step | motor A | torque Nm | force kN | accel. calc m/s² | [rubook] m/s² | end of resistors (full field, 600 V) km/h |
|---|---|---|---|---|---|---|
| 1 | 110 | 142 | 11.7 | 0.56 | 0.6 | 37 |
| 2 | 145 | 206 | 17.0 | 0.84 | 0.95 | 32 |
| 3 | 180 | 280 | 23.0 | 1.14 | 1.2 | 29 |
| 4 | 210 | 357 | 29.4 | 1.47 | 1.5 | 27 |
| 5 | 240 | 439 | 36.1 | 1.81 | 1.8 | 26 |

The ČKD current table, the Russian acceleration table, the motor chart, 7.43 and 700 mm agree, which
confirms that the step currents are **car** currents. Electric brake on step 5 (350 A car, 175 A per
motor): ≈23 kN, ≈1.2–1.3 m/s², matching ČKD's 1.2 m/s² measurement.

## 6. Proposed simulation model

### 6.1 What the sources fix

- Pedals: drive 0/1–5 at 5/12/20/27/35°, brake 0/1–5/park/track1/track2 at 3/7/12/18/23/27/37/40°,
  continuous travel without detents; step = whichever contact range the angle is in.
- Drive = current regulation: I_set(step) = 220/290/360/420/480 A until the accelerator reaches 75;
  then M2, then 4 field-weakening stages at accelerator positions 80/85/90/95 (also current-paced),
  pilot motor off at 97, rest at 99; from there the motor characteristic with 55 % field.
- Accelerator moves at most ≈20 positions/s in either direction.
- Coasting = small electric brake current, accelerator tracks speed (preparation).
- Brake = current regulation on 5 settings (step 5: 350 A); fade-out at low speed; on step 5/park the
  shoe brakes take over when the brake current falls below 120 A (≈4 km/h); on lower steps no
  automatic stop.
- Shoe brake states: released (BR1), stage 1 partly applied (BR2 only), stage 2 fully applied (none);
  full release only by the drive pedal.
- Track brakes: rear bogie at ≈37°, both at 40°; also rescue brake.
- Interlocks: brake pedal off zero kills drive; doors open block LS; MR 750 A latches until the drive
  pedal returns to 0.

### 6.2 State machine

States of the traction circuit (contactors in brackets):

```
PARKED  (brake pedal locked: LO off, BR1 off, BR2 off: shoe brake stage 2)
  └─ brake pedal unlocked to 0 ─▶ READY (LO, BR2: shoe stage 1; B1/B2 in; F2 in)
READY / COAST ── drive ≥ step 1, brake at 0, doors closed, no MR trip ──▶ START
START  (M1, LS; BR1 → shoes released; dampers in)          ~0.1 s → R1 → ~0.1 s → R2  [assumed timing]
  └─▶ DRIVE_RES (pilot motor regulates, p rises to 75; lamp on)
DRIVE_RES ── p = 75 ──▶ DRIVE_FULL (M2; lamp off) ── p 80/85/90/95 ──▶ field stages ── p 97 ──▶ DRIVE_END (p→99)
any DRIVE ── drive pedal to 0 ──▶ RELEASE (R1, R2 drop: dampers in, ~0.1–0.2 s) ──▶ COAST (LS, M1 out; B1, B2, F2 in)
COAST ── brake pedal off 0 ──▶ BRAKE (F2 out, RCP in; set I_brake(step))
BRAKE ── brake pedal to 0 ──▶ COAST
BRAKE (step ≥ 5 or parked) ── I_brake < 120 A ──▶ LO off: shoes stage 2 (stays until pedal to 0 → stage 1; drive → released)
any ── MR (I > 750 A) ──▶ LS out, latched until drive pedal at 0
any ── rescue button ──▶ RB off: LS, M1 out, shoes stage 2, all track brakes, bell
```

### 6.3 Equations (sourced numbers, assumed structure)

Variables: v (m/s), p (accelerator position 1–99, continuous), I (car current), I_m = I/2.

- Motor speed n = 202.7 × v rpm (7.43, 700 mm) [calc].
- Motor at terminal voltage U_m and current I_m with field factor φ (1, or field stage): back-EMF
  E = (300 − I_m·R_m) × n / n300(I_m, φ), with n300 from table 5.2 and R_m ≈ 0.11 Ω per motor
  [assumed from 91 % efficiency]. Torque T(I_m, φ) from table 5.2. (Section 8.4 replaces R_acc,
  R_damp and the start currents below with the wiring diagram's values.)
- **Drive, p < 75**: 600 = I·(R_acc(p) + R_damp) + 2·(E + I_m·R_m). R_acc(p) [assumed]: linear,
  R_acc = 2.835 Ω × (77 − p)/76 [inferred, 8.1]. R_damp = 1.05 Ω, then 0.7, then 0 in the first
  ≈0.2 s [A, 8.1]. Solve for I each tick (bisection on I_m).
- **Limiting relay**: if I < I_set·0.97 → p += 20·dt; if I > I_set·1.15 → p −= 20·dt; else hold
  (band [assumed]; the real relay chatters). Under this rule the current at standstill reaches its
  setting once p ≈ 7 (step 1) to ≈46 (step 5), after 0.3–2.3 s; with the dampers the very first
  current is ≈150 A, then ≈165 A, then ≈204 A [calc, 8.4].
- **Drive, p ≥ 75**: R_acc = 0 (M2), fields step at 80/85/90/95 to φ = 0.89, 0.78, 0.66, 0.55 of
  full flux on average over the car [assumed, evenly spaced; real stages alternate bogies], each step
  taken only while I < I_set; p frozen at 99 after 97.
- **Coasting**: a drag force equivalent to the preparation current: F_prep ≈ 4·T(I_prep/2)·21.2 with
  I_prep ≈ 50 A car current, i.e. ≈0.05–0.1 m/s² above ≈5 km/h, fading to 0 below [assumed within the
  sourced 0–0.14 m/s²]. p tracks p_match(v) at ≤ 20 /s, where p_match is the drive equilibrium position
  for step 1 at speed v [assumed]; after drive it runs back from 99.
- **Braking**: I_brake(step) = 160, 211, 262, 306, 350 A for steps 1–5 [step 5 sourced; 1–4 inferred
  from the wiring diagram, 8.2]. Brake force = 4·T(I_brake/2)·7.43/0.97/0.35. Available current is
  limited by speed: the accelerator must first reach the needed position (≤ 20 /s, starting from
  p_match or from 99 after drive) and at low speed the loop resistance cannot fall further; model
  I_avail = I_brake × min(1, v / v_fade) with v_fade ≈ 5 km/h [assumed], plus a build-up ramp of
  ≈0.5–1 s from coasting and ≈2 s right after drive [assumed, consistent with ČKD's 2–3 s advice].
- **LO / shoe brakes**: if brake step ≥ 5 (or parked) and I_avail < 120 A → shoes stage 2. Shoe brake
  force: not documented; assume stage 2 ≈1.5 m/s² and stage 1 ≈0.5 m/s² equivalent [assumed], both
  enough to hold the car on 80 ‰.
- **Track brakes**: 2 or 4 magnets × 60 kN × μ ≈ 0.1 [μ assumed] = 12 or 24 kN, immediate, independent
  of adhesion; with electric + shoe brakes the emergency average should come out ≈2.3 m/s² ([ckd26]).
- **Fast drive→brake**: the brake current starts from ~0 and builds over ≈2 s [assumed]; if the pedal
  is at step 5/park during that time, I < 120 A → shoe stage 2 at speed (sourced behaviour of LO,
  [inferred] timing). Recovery as in 6.2.
- **Indications**: ammeter = I (drive), I_prep (coast), I_brake (brake), scale 0–600 A; accelerator
  lamp on while LS is in and p < 75 (ZR1); shoe-brake lamps when BR1 is off; door lamp.

Faults worth a later issue (sourced as possibilities, not values): stuck finger (extra coasting drag),
accelerator overheating on long resistor running (lamp), MR trip from slamming steps.

## 7. Open questions

1. ~~Brake currents on steps 1–4~~: inferred from the wiring diagram as drive × 350/480 (8.2); a
   measurement in a car would confirm them.
2. ~~Accelerator resistance profile and wiring~~: drive 2.835 Ω up to finger ≈77, brake 3.614 Ω, uniform
   per position (8.1). How the two halves share the current inside the device is still not drawn.
3. ~~Pilot motor rate in the car~~: read as the same 5 s (9.1) [inferred]; no measurement.
4. ~~LO from brake step 3 or 5~~: step 5 (8.3).
5. **Coasting current**: 25 ± 5 A (relay, maybe per group) vs 30–60 vs 40–90 A (ammeter) vs ≈50 A.
6. **Ammeter in braking**: same direction, centre zero, or not shown?
7. ~~Door relay DBR~~: always, no speed condition, no brake (8.2). Whether Prague's T3SUCS kept it in
   this form is not known.
8. ~~Field-weakening positions~~: 80 / 85 / 90 / 95 (8.3). Still open: the flux of the intermediate
   stage.
9. **Shoe-brake retarding force** for stages 1 and 2 and its response time; track brake friction.
10. **Brake pedal "half stroke"**: the text calls the parking position the middle of the stroke, the
    drum program puts it at 27° of 40°.
11. **Sound**: no description or recording found; a recording from a historic Prague T3SUCS
    (e.g. car 7122, [fdrive]) would settle the pilot-motor whir and contactor sequence.
12. Prague modifications to the TR 37 after 1987 (the drawing's revisions end in March 1987).
13. The points resistor RV: ≈3.5 Ω with its first digit written over (8.1); which bogie the first
    track-brake pair KB3 + KB4 is on.

## 8. What the wiring diagram adds (read 2026-11-04)

ČKD drawing **1-38-370 444**, *Základní schema tramvaje T3SU/ČSSR*, drawn 10 Nov 1981, issue F
([ckd-schema]): one sheet, a 10363 × 6991 px scan, read from enlarged crops. The Czechoslovak version
of the circuit, with its revisions in the title block [A]:

| rev. | date | change |
|---|---|---|
| a | 20 Sep 1982 | change 82-09-018: the vigilance pedal (*šlapka bdělosti*) removed and replaced by a button |
| b | 28 Apr 1983 | interference filter added; the line contactor circuit changed: blocking by DBR |
| C | 24 Jan 1984 | control from the rear station added (84-01-032) |
| d | 16 Oct 1984 | resistors R1 + R2 + RV rewired |
| E | 19 Nov 1986 | changes for the 1987 series |
| F | 10 Mar 1987 | relay RK removed |

The sheet also says the motor terminal names in brackets apply to the **gear ratio 1:7.43**, which
confirms 7.43 for these cars [A].

### 8.1 Power circuit

- Pantograph → lightning arrester BL; trolley–earth disconnector OT → line contactor LS → maximum
  relay MR → the two motor groups in parallel: **4M+3M** (armatures, the limiting relay's current
  coil OR, reverser contactors P3/P4/Z3/Z4, fields, field-shunt contactors F1/F3 with the shunt SHM)
  and **2M+1M** (fields with P1/P2/Z1/Z2 and F2/F4, then armatures). They join at wire 9 → M1 → the
  accelerator → the damping resistors → earth [A].
- **Ammeter**: its shunt Sh lies in the 4M+3M group's lead before the groups join, so the meter
  measures one group [A]. That the scale is calibrated for the whole car ([ruwiki], 3.8) is not on the
  drawing.
- **Accelerator ZR**: drawn as two strips. The whole is labelled **3.614 Ω** (the [ckd17] total); the
  strip M1 feeds in drive is labelled **2.835 Ω**. Its terminals carry finger numbers: 77 and 79 on one
  strip, 78 on the other, matching [ckd17]'s odd and even halves [A]. Drive current enters at finger 79
  (wire 24 from M1) and leaves at finger 78 (wire 91 to R1/R2, where M2 bridges it) [A]. Reading
  [inferred]: drive uses the fingers up to about 77–79, 2.835 Ω; fingers 79–99 (3.614 − 2.835 =
  0.779 Ω) only brake. Both parts give 0.037 Ω per finger (2.835 / 76 and 0.779 / 21) [calc], so
  the resistance per position is uniform. At position 75, where M2 bridges, about 0.075 Ω is left
  [calc]: no current jump, which settles open question 2's misfit of a uniform 3.6 Ω chain.
- **Damping resistors**: **0.35 Ω** bridged by R1, then **0.7 Ω** bridged by R2 [A], not 0.7 + 0.7
  ([rubook], the Soviet car; revision d rewired them in 1984).
- **Points (switch) circuit**: wire 70 taken behind OT but ahead of LS, so independent of the line
  contactor → fuse **63 A** → contactor SV → resistor **RV ≈ 3.5 Ω** (the first digit is written over)
  → wire 90 → accelerator finger 77 → finger 78 → damping resistors → earth [A]. Line current while the
  button is held ≈ 600 V / (3.5 + 1.05 Ω + part of the accelerator) ≈ 80–130 A [calc]: hence ČKD's
  "not over 10 s".
- Auxiliaries: motor-generator behind a 20 A fuse, its series resistor RMG ≈ 4 Ω and the coil of SN in
  series with the MG motor (SN = "motor-generator running on line voltage"); calorifer (SK1, SK2),
  heating, lighting on 10 / 10 / 6 / 10 A fuses; line-voltage glow lamp KN through 160 kΩ [A].

### 8.2 Control circuits (24 V)

- **LS coil**: BK2 (brake pedal at 0) → JK1 (drive ≥ step 1, or R2's holding contact) → reverser PZ
  → SN → DBR → B2 rest contact → MR → LS, with the safety relay RB in the return [A]. **M1** via P1 or
  Z1 (a direction chosen); **M2** via ZR2 (75–99); **F2** in coasting via R1's rest contact (behind
  BK2), in drive via ZR3 (95–99) and M2; **F1** via ZR6 (85–99) [A].
- The button **TLM** (*tlačítko průjezdu mycím strojem*, "washing plant") bridges SN and DBR [A]: LS
  and M1 close without line voltage. M1 releases the shoe brakes (BR1), so this is the circuit behind
  DP's procedure for a car stopped on a section insulator: unpark, press "Mycí stroj" with the drive
  pedal and roll off by gravity ([ucebnice] via [t3.md](t3.md)) [B + inferred], and behind ČKD's
  procedure for a failed motor-generator (3.7).
- **Doors**: DBR's coil is fed through the door contacts DK1–DK3, one per door, in parallel; DBR's
  contact is in series in the LS coil circuit [A]. Nothing in DBR's circuit depends on speed and DBR
  has no contact in a brake circuit [A]. So an open door drops LS at any speed (traction off, the car
  coasts) and applies no brake [inferred]. The door contacts change over within the first 10–20 % of
  the door's travel from closed (contact program A–D) [A].
- **Regulating coil RC** (current setting): 24 V → RC (210 Ω) → RCR (210 Ω) → a divider RP1–RP3
  (3 × 10 Ω); RP4 15 kΩ across RC [A]. The tap per step: step 1 → 0 V (JK3 in series with BK3),
  step 2 → 8 V (JK4 or BK4), step 3 → 12 V (JK4 + JK5 short RP2), step 4 → 16 V (JK5 or BK5),
  step 5 → RC open [A]. The brake pedal's BK3–BK5 reach **the same taps in the same pattern** as
  JK3–JK5 [A], so brake step n has drive step n's RC current: 57 / 38 / 28 / 19 / 0 mA [calc]. A linear
  ampere-turn balance of OR (2 turns) and RC (3550 turns), set on step 5, gives 277 / 347 / 380 / 413 /
  480 A against ČKD's 220 / 290 / 360 / 420 / 480 A: close on steps 3–5, too high on 1–2, so the
  relay is not modelled from the circuit; the game uses ČKD's table [calc].
- **Brake currents on steps 1–4** [inferred]: in braking, the relay differs from drive only by the
  preparation coil CP, which sits across one group's fields through RCP (42 Ω; F2 is open). Its current,
  and so its ampere-turns, are proportional to the brake current. With RC the same per step,
  I_brake(n) = I_drive(n) × 350 / 480: **160 / 211 / 262 / 306 / 350 A** car current. Section 6.3
  assumed this scaling; the circuit supports it.
- **Switch button TV**: 24 V → **M1's rest contact** → TV → **ZR9** → SV coil [A]. ZR9 is closed only at
  accelerator positions **1–30** [A]. The button works only with drive off (coasting or braking) and
  the accelerator at 1–30. In coasting the accelerator tracks speed; position 30 is about 12 km/h
  matched to drive step 1, or 8–14 km/h for a self-excited brake loop of 1.3–2.4 Ω [calc]. So a switch
  can be set from the cab only below roughly 10–15 km/h, in line with D 1/2's 15 km/h over a facing
  switch [inferred].
- The accelerator lamp is ZR1, closed at positions **1–80**, fed through BK9 (brake pedal 0–2) or ZR10
  (positions 3–99) [A]: it can light in coasting and braking too, whenever the accelerator is below 80
  [inferred].
- **Track brakes**: K2 via BK7 → magnets KB3 + KB4; K1 via BK6, or via RB's rest contact → KB1 + KB2,
  and K1's contact also feeds K2, so the rescue brake applies all four [A]. 60 A fuse per pair. Which
  bogie KB3 + KB4 are is not on the sheet; [ckd24] says the rear bogie comes first.
- **Shoe brakes**: the release magnets Č1–Č4 get full current through BR1 (fully released) or reduced
  current through BR2 and the economy resistor RČ (partly released); selenium diode SČ across them;
  40 A fuse [A].
- **Safety relay RB** latches: an on-coil RBZ and an off-coil RBV; two rescue buttons (2 × ZS) and BS
  (the former vigilance pedal, a button since revision a) drop it [A].

### 8.3 Contact programs on the sheet [A]

| contact | closed at | does |
|---|---|---|
| JK1 | step 1 to max | M1, LS |
| JK2, JK6 | just off 0 to max | R1 circuit; MR hold |
| JK3 / JK4 / JK5 | 0–2 / ≈1.7–4 / 3–5 | current settings (overlap of JK3 and JK4 at step 2) |
| BK1 | past step 5 to the end | parking and track-brake range |
| BK2 | 0 to step 1 | LS, M1, F2 (drive possible) |
| BK3 / BK4 / BK5 | 0–2 / ≈1.5–4 / 3–5 | current settings |
| BK7, then BK6 | the last part of the stroke | track brakes K2, then K1 |
| BK8 | 0 to between steps 4 and 5 | LO's voltage coil: **LO hand-over from step 5** (answers open question 4) |
| BK9 | 0 to between steps 2 and 3 | BR1 hold |
| BK10 | just off 0 to the end | (not traced) |
| ZR1 | 1–80 | accelerator lamp |
| ZR2 | 75–99 | M2 |
| ZR4 / ZR6 / ZR5 / ZR3 | 80 / 85 / 90 / 95–99 | field stages F4 / F1 / F3 / F2 |
| ZR7 | 1–97 | pilot motor stops at 97 |
| ZR8, ZR10 | ≈3–99 | pilot-motor return path; BR1 hold |
| ZR9 | 1–30 | switch button |

The field stages at **80 / 85 / 90 / 95** are legible here; the 85 / 89 / 93 / 97 read from [ckd17]
p. 9 (3.4) was a misreading of a poor scan (answers open question 8).

### 8.4 What changes in the model (section 6)

- R_acc(p) = 2.835 Ω × (77 − p) / 76 in drive, M2 at 75; braking uses the whole 3.614 Ω.
- R_damp = 1.05 Ω (0.35 + 0.7), then 0.7, then 0. First currents at standstill on position 1:
  150 → 165 → 204 A [calc] (the old 0.7 + 0.7 gave ≈120–140 A).
- At standstill the current reaches its setting at positions ≈7 / 25 / 35 / 42 / 46 for steps 1–5,
  that is after **0.3 / 1.2 / 1.7 / 2.0 / 2.3 s** of accelerator travel at 20 positions/s [calc]: a
  full-pedal start builds its force over about 2 s, a step-1 start almost at once.
- I_brake(1–5) = 160 / 211 / 262 / 306 / 350 A [inferred, was assumed].
- Switch button: only with drive off and the accelerator at 1–30 (below ≈12 km/h).
- Doors: traction cut at any speed, no brake.

## 9. The electric system as simulated (#351, #355, read 2026-11-06/07)

Read from the scans in `raw/reference/ckd-t3su/` again. What this section adds to 3–8, and how `src/tr37.js` and `src/electric.js` model it.

### 9.1 The accelerator outside drive

- **The sources.** T3SU-24 § 4.2: coasting reverses the pilot motor's armature current, and the rollers return slowly towards the start; the relay
  (coil CP strong, so only a negligible brake current through OR) lets them go on while that current is too small. Speed rising downhill: more current,
  contact 100, rollers up, more resistance, until it is small again; speed falling: slowly back. § 4.3: the brake circuit is the same, with RCP in CP's
  circuit and RC set to one of five currents. § 1.4: loops cross-connected, the accelerator "returning from B to A", so its resistance falls with
  the position in the brake, the opposite of drive. T3SU-03 B5: this keeps the resistance matched to the speed, so drive or brake takes up at once.
- **The model: no lookup.** The current in the loops at position p and speed v comes from the motor chart: E(Im, n) = Im·(Rm + Rloop + R(p)), R(p) = 3.614 Ω ·
  (p − 1)/98, flux from the chart (§ 5.2), below 60 A falling linearly to a remanence of 3 %. The relay then turns the accelerator towards its setting
  (preparation 50 A, or the step's current), at the pilot motor's rate, in pulses near it.
- **Field in the loops.** F1 and F3 hang on ZR6 and ZR5 alone (T3SU-24 p. 8), so they shunt 4M+3M from 85 and 90 in the brake too; F4 and the drive's F2
  need M2. F2 is in while coasting (R2's rest contact, "so that the given resistance is enough at higher speeds", p. 9) and out on the brake pedal.
  In a crossed loop two groups' fields count as their harmonic mean [calc]: 2ab/(a + b). F2 alone: 65 %, from the first-stage and both-stage shunts in parallel [calc].
- **Calibrated:** Rloop = 0.17 Ω, so 120 A at the bottom of the accelerator falls at ≈4 km/h ([ckd24] p. 16). It also makes step 5's current start falling at ≈6 km/h
  and step 1's at ≈4.3 km/h, as the old fade table had them; below ≈4 km/h the loops no longer excite.
- **Follows without being set:** the coasting position at a speed comes out near where drive step 1 holds its current, so drive takes up at once
  (170–190 A against 220 A at 20–40 km/h [calc]), which T3SU-03 B5 asks for; the 2–3 s between drive and brake are the way back from the drive position; and a fast change
  drops LO because the loops are not excited yet.
- **Assumed:** remanence 3 %, a 0.2 s lag of the loop current, 0.25 s from LS out to B1 and B2 in (the pilot motor's way back goes through B2), the relay's band.
- **ZR8, ZR10:** T3SU-17 p. 7 has ZR8 closed at 3–99, the end of the way back: position ≈2.5 with the cross coasting on. It has ZR10 at 33–99, against 3–99 in T3SU-24 p. 14 and on
  the wiring diagram (§ 8.3): the game takes 3.
- **The rate.** T3SU-17 p. 5: 5 ± 0.5 s a sweep each way at 24 V, set by the armature's added resistor. T3SU-18 p. 1: 300 rpm at 10.5 V; the armature is always fed from the battery's
  mid-point through RPM (T3SU-24 p. 10–12), so "24 V" reads as the control voltage, and the rate is the same both ways and in the car [inferred]; it scales with the 24 V side here.
  This closes open question 3 unless a measurement says otherwise. "Slowly" in § 4.2 reads as following the falling speed.

### 9.2 The motor-generator and the 24 V side

- **One machine.** T3SU-15: series motor TMN 16 Ab (600 V, 720 V at most, 13 A, 5 kW, 1,750 rpm, 2,500 at most), shunt dynamo TDN 16 Ab (1.6 kW, 50 A; 70 A at 30 V at 1,500 rpm for 30 min), two
  fans on the one shaft, which cool the traction motors and the accelerator. T3SU-24 § 2.1: the current coil SN in its circuit drops LS when it stops, so no fans, no traction.
- **Series motor.** U = I·R + K·I/(I + I0)·ω, R ≈ 12 Ω with RMG ≈ 4 Ω (§ 8.1). Fans as ω² take the rest of the rated 5 kW [assumed]. So its speed follows the wire between √U and U, and any load on the dynamo slows it.
- **What slows it on a start** [inferred, no measurement]: the wire's voltage (a two-car set at 700–900 A), and BR1 closing: four release magnets of 2.7 Ω (T3SU-05 p. 3), ≈38 A at 26 V more on the dynamo.
- **Regulator** GC 11 (T3SU-23): switches the dynamo's field to hold 26 ± 0.5 V, field 12 A at most; a diode keeps the battery from feeding back; fuse 100 A. T3SU-26 p. 3: in all modes, checked at 550–600 V on the wire.
- **Battery** NKS 100 (T3SU-13): 17 NiCd cells of 1.2 V, 100 Ah, 30 A charging, so ≈22 V at rest when charged: below the regulator's speed margin the side falls to that.
- **On traction.** T3SU-26 p. 4: step 1's setting rises 10 A per volt below 26 (RC's current falling); other steps by their RC current. The pilot motor's rate scales with it.
- **Track brakes** run on the battery too (T3SU-13 p. 1): 0.632 Ω a magnet, ≈150 A a car with all four, beyond the dynamo: the side sags while they are on.

### 9.3 The wire

- **Substations:** `data/truth.json` `substations`, the 30 DPP traction substations in the OSM extract (`tools/substations.py`). Their feeding maps are in `raw/reference/web/prazsketramvaje/img/*-napajeni.gif`, schematic, c. 2009 (web-notes § 3.2); not used yet.
- **The model** (`src/electric.js`): a tram hangs on the feed with the least resistance: source 0.03 Ω, feeder cables 0.04 Ω/km, wire and rails 0.08 Ω/km for the first 0.8 km. No-load 650 V, 400 V at the least (the low limit of EN 50163, from memory). All [assumed]: nothing found measures them. Section ends and feed points wait for #277.
- **What depends on it:** force on the resistors no (the relay holds the current; the position stands higher for the same speed); the motor curve and top speed yes; the electric brake no (no line current, only the fans slow down); 26 V hardly; the fans' tone yes; heaters as U².

### 9.4 How a careful driver works it (T3SU-03)

p. 4: wrong to choose a high step at once, let go and press again; on the level steps 1–3 are enough (≈300 A, 360 A at most), more only at speed or uphill; from a high step, a lower one before letting go. p. 5–6: coast as much as possible, above all into stops.
`src/tr37.js` `autoDrive` and `src/autopilot.js` follow it.

[ckd-dir]: https://k5.sh.cvut.cz/~oskar/T3SU/
[ckd-schema]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-schema.pdf
[ckd03]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-03-Funkce.a.obsluha.El.vyzbroje.TR.37.pdf
[ckd04]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-04-Trakcni.motor.TE.022.pdf
[ckd05]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-05-Celistova.brzda.a.brzdic.pdf
[ckd16]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-16-Slapkovy.radic.HG.14.pdf
[ckd17]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-17-Zrychlovac.pdf
[ckd18]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-18-Ridici.elektromotor.E506.pdf
[ckd19]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-19-Omezovaci.rele.RC.36.pdf
[ckd22]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-22-Kolejnicova.brzda.pdf
[ckd24]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-24-Popis.funkci.elektricke.vyzbroje.TR.37.pdf
[ckd26]: https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-26-Zkouseni.ve.voze.pdf
[rubook]: https://poezdvl.com/electrooborudovanie-tramvaev-i-troleybusov/elektricheskaya-skhema-vagona-t-3.html
[ruwiki]: https://ru.wikipedia.org/wiki/Tatra_T3
[cswikiZ]: https://cs.wikipedia.org/wiki/Zrychlova%C4%8D
[cswikiT3]: https://cs.wikipedia.org/wiki/Tatra_T3
[cswikiT3M]: https://cs.wikipedia.org/wiki/Tatra_T3M
[mf1]: https://milanfon.cz/topic/2869-z%C3%A1kladn%C3%AD-%C5%99%C3%ADd%C3%ADc%C3%AD-obvody-tramvaje-t3-v-%C4%8Dinnosti/
[mf2]: https://milanfon.cz/topic/2968-trak%C4%8Dn%C3%AD-obvody-tramvaje-t3-v-%C4%8Dinnosti/
[imhd]: https://imhd.sk/ba/vehicle-type-description/20/%C4%8CKD-Tatra-T3
[vsb]: https://dspace.vsb.cz/server/api/core/bitstreams/45e9b392-d58d-49da-b8e1-899a7af9d752/content
[t3zr]: https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_t3zr_20260201.pdf
[ucebnice]: https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_t3.pdf
[prco]: https://mailman.dementix.org/pipermail/pittsburgh-railways/2007-September/019500.html
[rypn]: https://www.rypn.org/forums/viewtopic.php?p=298870
[tmsv]: https://tramway.org.au/reflections_ckd-tatra.html
[fdrive]: https://fdrive.cz/clanky/do-prazskeho-provozu-vyrazily-dve-opravene-retrotramvaje-obe-t3-ale-kazda-jina-17375
