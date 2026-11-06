# Speed limits from D 1/2's facts, OSM's posted speeds and the signs (#211)

Status: **proposed**, waiting for the user's answers (PR #362). The code in that PR follows the proposal; each rule is its own part of the diff.

## The facts against the code

Every speed fact in `data/truth.json`, what the game did before this work, and what it does now. Line km are the five lines' 86.6 km; `--checks limits` measures them.

| fact | says | source | before | now |
|---|---|---|---|---|
| `max-speed` | 50 km/h, also off the road, unless a Rychlostník allows more | D 1/2 § 25.1 | **differs:** untagged dedicated track 60, 5.97 km over 50 with no tag | 50 |
| `user-speed-signs` | signs up to 60 for now, "higher speeds to be picked up from osm" | the user, 2026-11-03 | **differs:** every speed capped at 60, 1.77 km of line 17 held back (0.89 km of it before the first stop) | the limit follows OSM up to the T3's 65; signs not changed yet |
| `restriction-start-end` | front in, rear out | § 25.1, 49.14, 49.22 | holds (`currentLimit`, lowest under the whole tram) | holds |
| `higher-speed-start-end` | rear in, front out | § 25.1 | holds (falls out of the same minimum) | holds |
| `point-restriction` | front only | § 49.16 | missing; no place known | missing |
| `switch-facing-speed` | 15 km/h facing, straight or diverging | § 25.4a | **differs:** 30 straight, 15 diverging; 18 m stretch | 15; blades to frog |
| `switch-trailing-diverging-speed` | 15 km/h | § 25.4b | missing: trailing switches not in the data | build writes them, game reads them |
| `switch-trailing-straight-speed` | 30 km/h | § 25.5a | missing | as above |
| `crossing-speed` | 15 km/h over diamonds and wire crossings | § 25.4c | missing, except where OSM tags it | build writes the diamonds, game reads them; wire crossings not |
| `small-radius-speed`, `small-radius-curves` | 15 km/h over a whole curve under 25 m | § 49.19; 11 places | **differs:** 10 at R 20 (8 of the 28 curves under 25 m) | at least 15 from a curve alone; the list is not read |
| `loop-speed` | 15 km/h in a loop's curves | § 25.4e | only where OSM tags it | unchanged |
| `switch-v-sign-speed` | 10 km/h facing diverging at a "V" | § 49.20 | missing; no list of places | missing |
| `stop-pass-speed` | 30 km/h, the front passing a stop's sign without stopping | § 25.5b | missing | missing: a rule of the game, for after W2 |
| `slow-sign-speed` | 10 km/h at *Pomalu* | § 49.13 | missing; no places | missing |
| `gradient-no-speed` | the dangerous-gradient rules set no speed; PPS Q53 marks "25 km/h" wrong | § 49.9–12 | **differs:** 25 under −6 %, 35 under −4.5 %: 4.64 km of limits with no source | unchanged: question 3 |
| `trojska-descent` | 20–25 km/h, rolling, Hercovka → Nad Trojou | website, local rule | covered by chance by the rule above | unchanged |
| `speed-switches` | R01–R09 with their speeds | register | not read | not read: [design](2026-11-07-speed-switch-signals.md) |
| `night-zones` | 40 km/h, 22–6 h | website | not read | not read: below |
| `dangerous-gradients` | Trojská 80.15 ‰, below Sídliště Modřany 69.9 ‰, the embankment curve 40 km/h | website | a board from the profile at −5.5 % | unchanged |
| `trackGeometry` `switch-speed` | Kotlářka: 15, 25 through a designed loop branch | Hradil 2020 | not read | not read: the line does not enter that loop |

**What sets the limit, km of the five lines** (86.6 km):

| cause | before | now |
|---|---|---|
| posted or general | 65.72 | 66.48 |
| curve | 15.25 | 14.00 |
| gradient (no source) | 4.64 | 4.62 |
| facing switch | 1.01 | 1.53 |

**Where a slow stretch ended** (two-car set, 30.24 m). #211 read three extensions. The window of `speedLimits` applies only to curves, not to switches, so two remained: the stretch ran to 14 m past the fork, and 5 m bins rounded it up. Measured: the limit lifted **46–48 m** past the fork.

The rule leaves one extension. `restriction-start-end` holds the limit until the rear has passed, so the stretch is only the switch itself:
- **The frog** lies a median **11.5 m** past the fork (10.5–13.5 m p10–p90), measured on the 82 facing switches: where the other leg is one gauge off the route.
- **Now 42–43 m**, which is the frog plus the tram. D 1/2 asks no less: "může být vyšší nejdříve při míjení místa ukončení platnosti omezené rychlosti zadním čelem vlaku" (§ 25.1).

What the driver still feels as too far is mostly OSM. 65 stretches on the five lines are tagged 15 km/h, up to 110 m long, and 38 of them touch a facing switch. The first rise of the limit past a switch is a median **73–105 m**. Those pieces stand for the trailing switches and diamonds the game did not know. Once the data has them (W2's rebuild) they are dropped (`withoutOwnPieces`).

## OSM's speeds

`tools/speed_survey.py`, extract of 2026-11-04. The build reads `maxspeed` only, and the game had it.

| line | km | untagged | 15 | other under 50 | 50 | 60 | 65 | 70 | night zone tag |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 9 | 28.54 | 9.96 | 0.43 | 0.60 | 16.71 | 0.83 | | | 1.67 |
| 17 | 21.80 | 0.75 | 0.57 | 1.02 | 11.45 | 6.17 | 0.89 | 0.95 | 1.41 |
| 22 | 18.43 | 13.13 | 0.41 | 0.05 | 3.81 | 1.02 | | | 0.90 |
| 23 | 8.28 | 2.83 | 0.38 | 0.18 | 3.86 | 1.02 | | | 0.90 |
| 37 | 9.53 | 2.15 | 0.43 | 0.07 | 6.07 | 0.82 | | | |

Network: 2625 tram ways, 1298 with `maxspeed`; 168 km of 355 km untagged.

**Read and not used:**
- **`maxspeed:conditional`** on 58 ways: 42 "40 @ (22:00-06:00)", 6 "50 @ (06:00-22:00); 40 @ (22:00-06:00)", 8 "30 @ (22:00-06:00)" (Barrandov), and 2 "30 @ (06:30-17:30)" at Zlíchov (not a night zone). These are the night zones, on 4.88 km of our lines.
- **`note`** on the 8 ways of Belárie – Černý kůň: "max. 70 km/h pouze vozy 14T, ostatní max. 65 km/h".
- **`ref` on switches:** of the 1017 switch nodes on tram track 257 carry a number ([switches.md](../research/prazsketramvaje/switches.md)); of the speed switches, R01, R03 and R04.
- **Not worth reading:** on tram track `railway:signal:speed_limit:speed` is on 1 node (60, at 50.0932 N 14.3933 E) and `maxspeed` on 3 nodes; no node on tram track has `railway:maxspeed:*`.

**Each source misses places.** OSM has 17. listopadu on line 17, which `night-zones` left out though the website lists it. `night-zones` has Rašínovo and Masarykovo nábřeží and Klapkova, which OSM does not tag.

**Proposed:**
1. `tools/osm_speeds.py` also writes `speed.night` (km/h or 0 per sample), from `maxspeed:conditional`, for the zones.
2. It reads through `pathBack` too (`speedBack`). Oncoming trams now have no posted speed, and the tags differ by direction (Krejcárek – Ohrada: 65 one way, 60 the other). #34 needs it.
3. Zones: the website's list is the source of what exists, OSM of where where it has them. A check counts the zones with no place on the route.
4. Keep `dedicated` for the cant only (done).

## The signs

Faces and placement are in `src/speedSigns.js`, held by `tools/test_speed_signs.py`, not yet in the game. `--sheet` draws them all. Research: [signals.md](../research/prazsketramvaje/signals.md).

**Size:** 200×300 mm with a 30 mm white frame, panel 140×240 mm. D 1/2 gives none; this is the same sign family on the website, and D 1/2's drawings have that shape. Estimated from the drawings: triangle 400×300 mm, zone plate 200×312 mm.

**Where each stands, from data, with no coordinates in code:**

| sign | when | places |
|---|---|---|
| SIG-V1 *Omezení rychlosti* | a posted speed under 50, at least 25 m long, that is not a switch's or crossing's own 15 | OSM |
| SIG-V3 end | where that stretch returns to 50 | OSM |
| SIG-V4 warning | braking distance before a restriction that drops 30 km/h or more: v² / (2 × 0.7 m/s²), the game's own rate | from V1 |
| SIG-V6 *Rychlostník* | a posted speed over 50 | OSM |
| SIG-V7 end | where it returns to 50; a restriction ends it without one (§ 49.17) | OSM |
| SIG-V8 "r" | a curve under 25 m, not at a switch or crossing (§ 49.19) | the track's radius, against `small-radius-curves` |
| SIG-V10, V11 zone | the zones, once placed (above) | `night-zones` + OSM |
| SIG-G1–G4 gradient | the list, not the profile's grade | `dangerous-gradients` |
| arrow strip | a sign over a fork that holds for one branch | with V1, V8 |
| yellow backing board (§ 49.32) | any sign may have it; no rule says where | an option of the face |
| SIG-V2 *Pomalu*, V5 point, V9 "V" | faces only: no source lists their places | |

**A change from today:** a limit that comes only from a curve (14.0 km, R over 25 m) has no real sign, so it gets none. The gauge marker and the hint still show it. Today's boards stand at every change, drawn black on white, and call themselves rychlostník.

**Curves under 25 m found by the rule, against the list:** Spálená (9, 22, 23), Chotkova (22, 23), Blanická (9), Na Moráni (9), Na Žertvách (37), Klárov (22, 23, at a switch). Not found by radius: Malostranské náměstí (both), Náměstí Míru (both), Havlíčkova. These may be other directions or a radius read over 16 m; the implementation issue checks them.

## The 65 and 70 km/h stretches

See [places.md](../research/prazsketramvaje/places.md). In short:
- **No source shows these signs.** The rule makes them a Rychlostník, white number on black.
- **By type:** § 49.17 allows several signs for different car types. OSM's note fits that: a 65 for all and a 70 for the 14T.
- **How the type is written** is not in any source read. The faces draw it on a strip under the panel, as the arrow is, marked unsourced.
- **The T3's limit** there is 65 either way, its own top speed.
