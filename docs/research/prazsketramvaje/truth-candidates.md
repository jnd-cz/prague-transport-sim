# Candidates for `data/truth.json`

Facts from these notes that the game could use, for the user to pick. Each points to its note
(where the source, page and the game's current value are). Tick the ones to record; a follow-up PR
writes them and nothing else.

Priority: **A** the game uses a different value now (fixing it needs the fact); **B** a feature the
game lacks would need it; **C** reference.

## Shape

`truth.json` has no section for operating rules yet (`rules` holds the user's short statements;
`trackGeometry.facts` holds design values with a `source` object). Proposed: a new top-level
`operation` with the same fact shape as `trackGeometry.facts`, plus `section`, and keyed lists for
places and switches.

```json
"operation": {
  "note": "Operating rules, signals and places from DP Praha's own documents, paraphrased; each with the year it was written.",
  "facts": [
    {
      "id": "switch-facing-speed",
      "value": 15,
      "unit": "km/h",
      "scope": "facing a switch, set straight or diverging, unless a sign sets another speed",
      "basis": "operating rule",
      "source": {
        "document": "DP Praha: D 1/2 Dopravní a návěstní předpis pro tramvaje (in force 2025-09-01)",
        "year": 2025,
        "url": "https://www.prazsketramvaje.cz/obrazky/stahuj/testy/predpis_d1-2_20260201.pdf",
        "page": 22,
        "section": "§ 25.4 a"
      }
    }
  ],
  "places": [
    { "id": "curve-moran", "kind": "small-radius-curve", "place": "Na Moráni, inner curve from Karlovo náměstí",
      "value": 15, "unit": "km/h", "source": { "document": "prazsketramvaje.cz: Návěsti upravující rychlost tramvaje", "url": "https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041265", "year": 2026 } }
  ],
  "switches": [
    { "number": "690", "place": "Podolská vodárna", "from": "Výtoň", "control": "radio", "contact": "never fitted",
      "source": { "document": "prazsketramvaje.cz: Radiově ovládané výhybky – evidenční čísla", "url": "https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041262", "year": 2026 } }
  ]
}
```

The website's pages carry no date; "year" is the year read (2026), the register's newest entries are
the Dvorecký most junctions. A user's answer to an open question goes in with the user's quote and
date, as AGENTS.md asks.

## Speeds (D 1/2 § 25, 49; [rules-d1-2.md](rules-d1-2.md))

| ☐ | id | Value | Scope | Source | Prio | Serves |
|---|---|---|---|---|---|---|
| ☐ | `max-speed` | 50 km/h | the whole network, also off the road, unless a Rychlostník allows more | § 25.1 p. 22; PPS Q83 | A | the 60 km/h on dedicated track (`src/route.js`) |
| ☐ | `restriction-start-end` | front / rear | a restriction applies from the front's entry until the **rear** passes its end sign | § 25.1 p. 22, § 49.14 p. 53 | A | #211 (where a slow stretch ends) |
| ☐ | `point-restriction` | front | at a "Místo s omezenou rychlostí" only the front must be at the speed; speed up once the front has passed | § 49.16 p. 54 | B | – |
| ☐ | `higher-speed-start-end` | rear / front | above 50: faster only after the rear passes the Rychlostník, back down when the front reaches its end | § 25.1 p. 22 | B | – |
| ☐ | `switch-facing-speed` | 15 km/h | facing, straight or diverging, unless signed | § 25.4 a p. 22; PPS Q64 | **A** | #211: the game has 30 straight |
| ☐ | `switch-trailing-diverging-speed` | 15 km/h | trailing from the diverging branch, unless signed | § 25.4 b p. 22; PPS Q80 | **A** | #211 |
| ☐ | `switch-trailing-straight-speed` | 30 km/h | trailing from the straight branch, unless signed | § 25.5 a p. 23; PPS Q69, Q81 | **A** | #211 |
| ☐ | `crossing-speed` | 15 km/h | over track crossings and trolley-wire crossings, unless signed | § 25.4 c p. 22; PPS Q65 | **A** | #211: diamond crossings unlimited now |
| ☐ | `loop-speed` | 15 km/h | in the curves of a turning loop, from the first switch into it to the last switch out | § 25.4 e p. 23 | **A** | loops at Levského, Sídliště Modřany, Nádraží Braník, Vozovna Kobylisy (line 17) |
| ☐ | `switch-v-sign-speed` | 10 km/h | facing into the diverging branch of a switch with the "V" sign | § 49.20 p. 55 | B | needs the signs' places |
| ☐ | `small-radius-speed` | 15 km/h | the whole of a curve under R 25 m (sign "r"); not signed where another rule already slows | § 49.19 p. 55; PPS Q79 | A | `curveSpeed` gives 10 km/h at R 20 m |
| ☐ | `stop-pass-speed` | 30 km/h | the front passing the stop sign of a stop where the train does not stop | § 25.5 b p. 23; PPS Q86, Q87 | A | request stops passed at any speed now |
| ☐ | `slow-sign-speed` | 10 km/h | "Pomalu" sign, hand signal or work site | § 49.13, 51.5, 25.3 e | C | – |
| ☐ | `gradient-no-speed` | – | D 1/2 sets no speed for steep descents; the "dangerous gradient" rules are about entering and starting | § 49.9–12; PPS Q53 | A | the 25 / 35 km/h on descents (`src/game.js:119-123`) |
| ☐ | `trojska-descent` | 20–25 km/h | Trojská street, Hercovka → Nad Trojou (470 m, 80.15 ‰, line 17): stop and test the parking brake, then roll without power, one train per block (two blocks with signals); uphill one train in the section | website 2006041635, 2006041282 | **A** | the game's 25 km/h on every steep grade |

## Stops, timing, distances

| ☐ | id | Value | Scope | Source | Prio | Serves |
|---|---|---|---|---|---|---|
| ☐ | `stop-front-position` | at the sign | the first train stops with its front next to the stop sign or as close before it as possible | § 27.6 p. 24 | **A** | the game aims 6 m past the platform point (`src/game.js:13`) |
| ☐ | `stop-second-train-gap` | 1 m | a second train stops at least 1 m behind the first, rear inside the stop area | § 27.6 p. 24 | B | AI trams keep 6 m |
| ☐ | `standing-gap` | 1 m | between two standing trains (from the coupler head) | § 33.9 p. 31 | B | – |
| ☐ | `stop-area-default` | 30 m | the stop area without an end marker or platform edge | § 2.22 p. 9 | B | the game's 20 m before / 12 m past window |
| ☐ | `stop-roadway-two-trains` | 2 | trains boarding at once at a stop without island; the third stops again at the sign | § 27.4–5 p. 24 | C | AI trams |
| ☐ | `on-time-window` | 0–179 s late | departure from an intermediate stop | § 16.2 a p. 17; PPS Q51 | A | the game's 5 s grace and 60 / 180 s classes |
| ☐ | `on-time-window-first-stop` | 0–59 s late | departure from the first (boarding) stop | § 16.2 b p. 17 | A | the same |
| ☐ | `start-gap-bunched` | 50 m | gap to the train ahead when starting in a queue; 100 m during supply failures, or after the train ahead has passed the section insulator | § 33.7 p. 31 | B | AI trams, a power model |
| ☐ | `following-distance` | braking distance | the following train keeps a distance in which it can stop safely | § 33.8 p. 31 | B | scoring the player's following |
| ☐ | `request-stop-must-stop` | list | cases in which a request stop must be served (someone there, button, no buttons on the train, broken button, last stop of a pull-in) | § 27.14 p. 25 | B | request stops are random now |
| ☐ | `doors-warning` | 3 s | the "doors closing" warning is sound and light together, at least 3 s | § 51.12 p. 60 | B | – |
| ☐ | `bell-warning` | 2 s | the driver's "Pozor": two short mechanical rings or one electric ring up to 2 s | § 51.6 p. 60 | C | – |
| ☐ | `parked-while-standing` | – | the brake pedal stays at "Zaparkováno" the whole time the train stands | § 34.3 p. 32 | B | the game holds brake notch 2 with open doors |

## Power and wire

| ☐ | id | Value | Scope | Source | Prio | Serves |
|---|---|---|---|---|---|---|
| ☐ | `section-insulator-coast` | no current | pass a section insulator (green diamond, three dots) with pantographs up and no traction current; a diode insulator may be passed drawing current | § 49.23, 49.27 p. 56–57 | B | a skill like the contacts; needs places |
| ☐ | `trolley-crossing-coast` | no current | pass trolley-wire crossings without traction current | § 33.14 p. 32 | B | the same |
| ☐ | `insulator-roll-off` | – | stopped on an insulator, a T3SUCS rolls off by gravity: unpark, "Mycí stroj" + drive pedal | ucebnice p. 7 | C | – |
| ☐ | `power-cut-accelerator-stop` | – | on a dangerous descent a car with an accelerator stops at once when power fails | § 49.11 p. 52 | C | – |

## Switches ([switches.md](switches.md))

| ☐ | id | Fact | Source | Prio | Serves |
|---|---|---|---|---|---|
| ☐ | `switch-signal-steady` | steady red arrow = route set **and locked**; blinking = also blocked against remote throwing; centre dot = assume unlocked | § 45.3–5 p. 44 | A | the game blinks "while locked" |
| ☐ | `radio-switch-distances` | the driver sets the left / straight / right selector at least 40 m before the switch; the receiver lies 25–35 m before it, right of the track; the switch is thrown and blocked as the front passes the receiver | website 2006041278 | B | radio switches in the game (`game.irc()` works within 80 m) |
| ☐ | `hand-set-switches-17` | U07 Podolská vodárna from Kublov and U17 Ke Stírce from Trojská: hand-set lockable switches, straight in service | website 2010083001 | A | #204 (Podolská vodárna), the game's contacts there |
| ☐ | `radio-circuit-entry` | pass the radio-receiver sign only when no other train is in the switch circuit | § 29.16 p. 28 | B | AI trams and the player at radio switches |
| ☐ | `trailing-locked-forbidden` | trailing a lockable or speed switch set against the train is forbidden | § 29.7 p. 27 | B | trailing switches |
| ☐ | `contacts-transitional` | working-contact control is transitional (director's circular until removed) | § 52.1 p. 62 | **A** (decision) | the game's contacts on every switch |
| ☐ | `switch-register` (list) | the radio switches on our lines with number, place, "from", contact removed or never fitted | register 2006041262 | B | number plates; radio vs contact per switch |
| ☐ | `speed-switches` (list) | R03, R04, R05, R07, R09 with straight / diverging speeds | register 2006041262 | A | limits at those switches |
| ☐ | `t3sucs-switch-button` | the "Výhybka" button is pressed under the contact while coasting or braking; not pressed = switch left as it is; radio switches through the on-board computer (auto or manual) | ucebnice p. 6 | C | already in the game |

## Places ([places.md](places.md))

| ☐ | List | Count on our lines | Prio |
|---|---|---|---|
| ☐ | small-radius curves (R < 25 m) | 11 places on lines 9, 10, 22, 23, 37 | A |
| ☐ | night zones 40 km/h, 22–6 h | about 18 start/end pairs, 4 on line 17 | B |
| ☐ | speed switches | 5 | A |
| ☐ | safety stopping places | 8 places (2 kinds: start by gravity, start with power), 3 on line 17 | B |
| ☐ | dangerous gradients | Trojská 80.15 ‰ (line 17); up to 69.9 ‰ below Sídliště Modřany | A |
| ☐ | stop positions on Podolské nábřeží | 7 stops of line 17, in metres from landmarks | B |
| ☐ | meeting ban at Národní divadlo ("T - KT") | 1 | C |

## Operation ([web-notes.md](web-notes.md))

| ☐ | id | Value | Source | Prio | Serves |
|---|---|---|---|---|---|
| ☐ | `deviation-display` | on time 0–179 s late; early > 1 s red, > 60 s flashing red; 180–419 s late yellow; ≥ 420 s flashing yellow | website 2013010201 | B | the HUD's timetable display |
| ☐ | `relief-point-17` | line 17 drivers are relieved at Nádraží Braník on weekdays | website 2018010201 (2018) | C | shifts |
| ☐ | `depot-run-marking` | a run into the depot shows the depot or stop in green on white; a reserve train shows "X" | website 2006041446 | C | route boxes |

## The T3 ([t3.md](t3.md))

| ☐ | id | Value | Source | Prio | Serves |
|---|---|---|---|---|---|
| ☐ | `t3sucs-drive-steps` | 5 steps at 5/12/20/27/35° of 40°; 220/290/360/420/480 A per car | ČKD T-50172 p. 4, T-50407 p. 6 | A | the game's 4 force notches ([t3-accelerator.md](t3-accelerator.md)) |
| ☐ | `t3sucs-brake-steps` | 5 steps at 3/7/12/18/23°; park 27°; track 37° / 40°; 160 / 211 / 262 / 306 / 350 A (1–4 inferred) | ČKD T-50407 p. 6, T-50361 p. 4; drawing 1-38-370 444 | A | the game's 4 brake notches |
| ☐ | `t3sucs-accelerator` | 99 positions, 3.614 Ω (2.835 Ω in drive), 5 s sweep; bridged at 75; fields at 80/85/90/95; dampers 0.35 + 0.7 Ω | ČKD T-50408 p. 1, 5; T-50413 p. 8; drawing 1-38-370 444 | A | not modelled |
| ☐ | `t3sucs-parking` | ratchet at 27°; full release only with the drive pedal | ČKD T-50407 p. 1, T-50413 p. 16 | B | no parked position |
| ☐ | `t3sucs-door-interlock` | door relay cuts traction at any speed; no brake | ČKD T-50413 p. 7; drawing 1-38-370 444 | A | the user's answer 5 |
| ☐ | `t3sucs-switch-button` | the switch button works only with drive off and the accelerator at 1–30 (≈ below 12 km/h) | drawing 1-38-370 444 | B | the contact switches |
| ☐ | `t3-no-deadman` | no dead-man pedal; safety button | ČKD T-50172 p. 7 | B | the game's optional dead-man pedal |
| ☐ | `t3sucs-max-relay` | 750 A, latched until the drive pedal is at 0 | ČKD T-50413 p. 9 | C | fault events |
| ☐ | `te022-motor` | 40 kW, 300 V, 150 A, 1750 rpm (max 4200); gear 7.43; wheel 700 mm | ČKD T-50272 p. 2; ru.wikipedia | B | the game's 172 kW table |
| ☐ | `t3sucs-coasting-current` | 40–90 A | t3zr Q2853 | C | the ammeter while coasting |
| ☐ | `t3sucs-mech-brake-cut-in` | 5–3 km/h | ucebnice p. 5 | B | the end of a stop |
| ☐ | `t3sucs-track-brake-stages` | 2 (rear bogie, then both) | ucebnice p. 5 | C | – |
| ☐ | `t3sucs-drive-to-brake` | coast 2–3 s between braking and driving; a fast change drops the dynamic brake | ČKD T-50172 p. 11; ucebnice p. 4 | B | a coasting skill |
| ☐ | `t3sucs-sand-axle` | first axle, both wheels | ucebnice p. 6 | C | – |
| ☐ | `t3-dimensions` | 15.20 m, 2.50 m, 16 t, 24 + 86 | ucebnice p. 4 | C | already in the game |
| ☐ | `t3rplf-profile` | 16.30 m, 20.5 t, profile "KT" | ucebnice p. 20 | C | KT meeting bans later |
