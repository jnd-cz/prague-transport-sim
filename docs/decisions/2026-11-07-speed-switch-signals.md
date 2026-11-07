# Speed switches: their LED signals in the game (#211)

Status: **proposed**, waiting for the user's answers (PR #362). Nothing here is in the game yet; the panels are drawn in `src/speedSigns.js` (`drawLedPanel`).

Sources: D 1/2 § 30, 46; PPS Q103–105, Q109, Q111–112; the website's page on R01; [switches.md](../research/prazsketramvaje/switches.md) SW-R.

## Which ones the game would meet

| no. | place | speeds | on our lines | the driven direction meets it |
|---|---|---|---|---|
| R07 | Kotlářka | 50 / 15 in the register, 50 / 35 in the 2023 press | 9 | **yes**, by name: s 23460, straight, on the way back from the centre. To check |
| R09 | Podolské nábřeží od Dvorců | 30 / 15 | 17 | **yes**, by name: s 9773, straight. To check |
| R03 | Letenský tunel | 50 / 40 | 17 | no: `pathBack` (OSM `ref`, 0.1 m) |
| R04 | Nádraží Braník, into the loop | 30 / 15 | 17 | no: `pathBack` (OSM `ref`, 0.1 m) |
| R05 | Průběžná od Strašnické | 30 / 15 | 22 | no: `pathBack`, by name |

Today's player drives `path` only, so **two** speed switches matter now and five once both directions are drivable (#34). R01, R02, R06 and R08 come with the full network (#340).

## What stands along the track

Distances are R01's, the only ones known: "cca 190", "dalších cca 30", "cca 27". Each switch's own are unknown, so these are defaults.

| at | element | states | panel |
|---|---|---|---|
| −190 m | **number sign** "R 09", white on black, upright; the radio receiver is here. A train may pass it with another in the circuit | fixed; orange cross when radio is out (SW-R5) | a plate, 170×400 mm estimated |
| −160 m | **call signal**: three LED bars `\ | /` | yellow bar of the registered direction for about 5 s; dark if not registered | black, 400×400 mm estimated |
| −27 m | **entry sleeper signal**: round black disc between or beside the rails | white vertical bar: enter; horizontal: do not; dark | disc, 300 mm estimated |
| 0 | the switch; the track circuits run from the sleeper signal to the end of the switch | | |
| about +12 m, at the frog | **switch signal**: two stacked boxes on a pole bracket | chevron of white LEDs, blinking = blocked; under it a seven-segment number; or a dot: undetermined; dark before the train is in the circuit | 2 boxes, 600×420 mm estimated from the photo, about 5 m up |

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

**Models.** `makeSpeedSwitchSignal` in `src/models.js`, drawn with `drawLedPanel` to textures, one for each state, in the manner of `arrowTexture`, with `userData.set(state)`. It replaces `makeSwitchIndicator` (red chevron, −8 m) for these switches. Standing elements go through `_mount`; the sleeper signal stands low by the rail.

**Parts by lane:**
- **Now possible without traffic (lane:assets, after W2's data):** the models, registration, the number and the limit. The entry signal always shows "enter".
- **After W2 (lane:sim, `src/traffic.js`):** a horizontal bar while an AI tram is in the circuit, and AI trams using the number. Faults (dark signals, a stuck bar, out-of-service crosses) as events.

**Trailing a speed switch set the wrong way is forbidden** (`trailing-locked-forbidden`); the game has no such event yet.

## Checks when it is built

`tools/test_speed_signs.py` for the states; a page test driving line 17 through s 9773 with and without registering (the limit is 30 or 15); screenshots main vs branch and `tools/frametime.py`; `u3,redruns,traffic,lint` on lines 9 and 17, since it changes the tram's timing.
