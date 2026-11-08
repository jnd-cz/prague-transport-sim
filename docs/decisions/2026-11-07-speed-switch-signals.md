# Speed switches: their LED signals in the game (#211)

Status: **the elements in the game** (#365): at R07 and R09 the number plate, the call signal, the entry sleeper signal and the switch signal stand at R01's distances (`Game._initSpeedSwitch`, matched by the OSM node's lat, lon in `data/truth.json`). The call signal stays dark and the number box dark, so the switch is passed at 15 km/h. Registration, the number and its limit wait with the simulation work: #380.

Sources: D 1/2 § 30, 46; PPS Q103–105, Q109, Q111–112; the website's page on R01; [switches.md](../research/prazsketramvaje/switches.md) SW-R.

## Which ones the game would meet

| no. | place | speeds | on our lines | the driven direction meets it |
|---|---|---|---|---|
| R07 | Kotlářka | **50 / 35**, the 2023 press release (the user, 2026-11-08: "I will go with the press release"); the register says 50 / 15, kept in `data/truth.json` to confirm later | 9 | **yes**, by name: s 23460, straight, on the way back from the centre; Plzeňská between Kavalírka and Kotlářka, 50.06971 N 14.36516 E, heading west; OSM node 4533725474 (electric, no `ref`). **The place is right** (the user, 2026-11-08: "Kotlářka looks right"); the diverging speed is still to check |
| R09 | Podolské nábřeží od Dvorců | 30 / 15 | 17 | **yes**, by name: s 9773, straight; Podolské nábřeží between Dvorce and Kublov, just before the junction westwards, 50.04992 N 14.41556 E, heading north; OSM node 6660333413, no `ref`. The user (2026-11-08): "Dvorce maybe". The register names three switches at Podolské nábřeží: R09 "od Dvorců", 801 "od Lihovaru", 802 "od Podolské vodárny"; OSM tags `ref` 802 on the same junction's southbound facing switch, 65 m north (node 9412314524). So this is the junction's northbound facing switch, R09 by the register's names. **Confirmed** by the user ("yes", 2026-11-08) |
| R03 | Letenský tunel | 50 / 40 | 17 | no: `pathBack` (OSM `ref`, 0.1 m) |
| R04 | Nádraží Braník, into the loop | 30 / 15 | 17 | no: `pathBack` (OSM `ref`, 0.1 m) |
| R05 | Průběžná od Strašnické | 30 / 15 | 22 | no: `pathBack`, by name |

Today's player drives `path` only, so **two** speed switches matter now and five once both directions are drivable (#34). R01, R02, R06 and R08 come with the full network (#340).

## What stands along the track

Distances are R01's, the only ones known: "cca 190", "dalších cca 30", "cca 27". Each switch's own are unknown, so these are defaults.

| at | element | states | panel |
|---|---|---|---|
| −190 m | **number sign** "R 09", white on black, upright; the radio receiver is here. A train may pass it with another in the circuit | fixed; orange cross when radio is out (SW-R5) | a plate, 170×400 mm estimated |
| −160 m | **call signal**: three LED strips `\ | /`, each 7 pairs; the leaning ones are the vertical strip turned 24°, apart from it at the bottom (D 1/2 p. 45; photos; the user, 2026-11-08) | yellow strip of the registered direction for about 5 s; dark if not registered | black, 400×400 mm estimated; the junctions' call signal, `src/ledPanels.js` (#376) |
| −27 m | **entry sleeper signal**: round black disc between or beside the rails | white vertical bar: enter; horizontal: do not; dark | disc, 300 mm estimated; a solid bar, not LED dots (the user, 2026-11-08) |
| 0 | the switch; the track circuits run from the sleeper signal to the end of the switch | | |
| about +12 m, at the frog | **switch signal**: two stacked boxes with cut corners on a pole bracket | a dart of white LEDs, blinking = blocked; under it a seven-segment number, each segment a single line of LEDs, the unlit ones faint (D 1/2 draws outlined segments filling the box; the photos win, the user 2026-11-08): each figure 0.69 of the box's height, 0.52 as wide as high, the two 0.26 of that height apart; or a dot: undetermined; dark before the train is in the circuit | 2 boxes, 600×420 mm estimated from the photo, about 5 m up. The dart, measured on the two R01 photos in the box's heights: straight 0.76 long and 0.45 wide, sideways 1.0 long and 0.51 wide, a notch at its tail (the user, 2026-11-08: "make the arrow smaller") |

## How it behaves

| event | signal | the driver |
|---|---|---|
| the front passes the receiver with a direction set | call: that bar for 5 s | checks it |
| not registered | call stays dark | "extra care": the number will not come; 15 km/h |
| the circuit is free | entry: vertical bar | enters |
| another train in the circuit | entry: horizontal bar | waits; stuck after the train has left: dispatcher |
| train in the circuit, switch locked and blocked | switch signal: blinking chevron and the number | up to that number |
| route set, no number | chevron only | 15 km/h |
| dark though in the circuit | dark | counts as a lockable switch: 15 km/h (§ 30.4) |
| rear past the end of the circuit | switch signal dark, entry about 4 s later | |

The higher speed needs all three together: full symbol, blinking, number (website).

**A correction to the sources:** the website's "15 km/h straight, 10 diverging" without a number is older text. D 1/2 (2025) and PPS Q104 give 15.

## How it fits the game

**Data.** `tools/build_line.py` gives each facing switch of a speed switch `speedSwitch: {ref, straight, diverging}`.
- The number comes from OSM's `ref` where it has one, or from a new `truth.json` list by place, with the user's answer for R07 and R09.
- The speeds come from `operation` `speed-switches`.

**Limits.** `trackworkStretches` gives such a switch its number instead of `facing`. Because the number depends on what the signal shows, `Game.currentLimit` needs a run-time part: `min(limits, speedSwitch.allowed)`, where `allowed` is 15 until the switch signal shows the number. `nextLimitChange` and the autopilot read the same, so they brake for 15 unless registered.

**Registration.** Speed switches are radio-worked, so `sw.auto` holds and the existing `irc(dir)` buttons set them, within reach of the receiver rather than today's 80 m of the switch. With "onboard computer" (`autoIrc`) they register by themselves.

**Models.** `makeSpeedSwitchSignal` in `src/models.js`, drawn with `drawLedPanel` to textures, one for each state, in the manner of `arrowTexture`, with `userData.set(state)`. The call signal is the junctions' own, `drawCallSignal` in `src/ledPanels.js` (#376); `drawLedPanel` can move there with it. It replaces `makeSwitchIndicator` (red chevron, −8 m) for these switches. Standing elements go through `_mount`; the sleeper signal stands low by the rail.

**Parts by lane:**
- **Now possible without traffic (lane:assets, after W2's data):** the models, registration, the number and the limit. The entry signal always shows "enter".
- **After W2 (lane:sim, `src/traffic.js`):** a horizontal bar while an AI tram is in the circuit, and AI trams using the number. Faults (dark signals, a stuck bar, out-of-service crosses) as events.

**Trailing a speed switch set the wrong way is forbidden** (`trailing-locked-forbidden`); the game has no such event yet.

## Checks when it is built

`tools/test_speed_signs.py` for the states; a page test driving line 17 through s 9773 with and without registering (the limit is 30 or 15); screenshots main vs branch and `tools/frametime.py`; `u3,redruns,traffic,lint` on lines 9 and 17, since it changes the tram's timing.
