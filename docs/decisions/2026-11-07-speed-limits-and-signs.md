# Speed limits from D 1/2's facts, OSM's posted speeds and the signs (#211)

Status: **decided; the signs in the game** (PR #362 for the limits and faces, #364 for the boards in the game). The user answered PR 362's questions 1, 2, 3 and 9 on 2026-11-07 (applied in 78fd584). On 2026-11-08 the user answered questions 4–8: 200 % for testing, as a parameter (`SIGN_SCALE`); R07 and R09 at the places marked; `restriction-past` 0 m; and R07's diverging speed 35 km/h, the press release, the register's 15 kept to confirm. Night zones, held with the simulation work, are #380.

## The facts against the code

Every speed fact in `data/truth.json`, what the game did before this work, and what it does now. Line km are the five lines' 86.6 km; `--checks limits` measures them.

| fact | says | source | before | now |
|---|---|---|---|---|
| `max-speed` | 50 km/h, also off the road, unless a Rychlostník allows more | D 1/2 § 25.1 | **differs:** untagged dedicated track 60, 5.97 km over 50 with no tag | 50 |
| `user-speed-signs` | signs up to 60 for now, "higher speeds to be picked up from osm" | the user, 2026-11-03 | **differs:** every speed capped at 60, 1.77 km of line 17 held back (0.89 km of it before the first stop) | the limit follows OSM up to the T3's 65; signs not changed yet |
| `restriction-start-end` | front in, rear out | § 25.1, 49.14, 49.22 | holds (`currentLimit`, lowest under the whole tram) | holds |
| `restriction-past` | a restriction ends right at a curve's end, a switch's frog or a crossing: "keep it simply right after", since "the tram bogie leaves the switch sooner than the end of car" | the user, 2026-11-08 (2 m on 2026-11-07) | **differs:** a curve's limit ran 15 m past its last low 5 m bin; a switch's ended at the frog's bin | 0 m, to the metre |
| `higher-speed-start-end` | rear in, front out | § 25.1 | holds (falls out of the same minimum) | holds |
| `point-restriction` | front only | § 49.16 | missing; no place known | the stop signs' points (below) |
| `switch-facing-speed` | 15 km/h facing, straight or diverging | § 25.4a | **differs:** 30 straight, 15 diverging; 18 m stretch | 15; blades to frog |
| `switch-trailing-diverging-speed` | 15 km/h | § 25.4b | missing: trailing switches not in the data | build writes them, game reads them |
| `switch-trailing-straight-speed` | 30 km/h | § 25.5a | missing | as above |
| `crossing-speed` | 15 km/h over diamonds and wire crossings | § 25.4c | missing, except where OSM tags it | build writes the diamonds, game reads them; wire crossings not |
| `small-radius-speed`, `small-radius-curves` | 15 km/h over a whole curve under 25 m | § 49.19; 11 places | **differs:** 10 at R 20 (8 of the 28 curves under 25 m) | at least 15 from a curve alone; the list is not read |
| `loop-speed` | 15 km/h in a loop's curves | § 25.4e | only where OSM tags it | 15 from the switch into a loop to the switch out of it, the loops found by the user's rule (below) |
| `switch-v-sign-speed` | 10 km/h facing diverging at a "V" | § 49.20 | missing; no list of places | missing |
| `stop-pass-speed` | 30 km/h, the front passing a stop's sign without stopping | § 25.5b | missing | a point at each stop's sign for the front; the autopilot keeps it, passing it 3 km/h over costs the overspeed (below) |
| `slow-sign-speed` | 10 km/h at *Pomalu* | § 49.13 | missing; no places | missing |
| `gradient-no-speed` | the dangerous-gradient rules set no speed; PPS Q53 marks "25 km/h" wrong | § 49.9–12, the user | **differs:** 25 under −6 %, 35 under −4.5 %: 4.64 km of limits with no source | holds: no limit from a slope |
| `trojska-descent` | 20–25 km/h, rolling, Hercovka → Nad Trojou | website, local rule | covered by chance by the rule above | 25 by its `place`, only where OSM tags no speed (the user: a backup after OSM) |
| `speed-switches` | R01–R09 with their speeds | register | not read | not read: [design](2026-11-07-speed-switch-signals.md) |
| `night-zones` | 40 km/h, 22–6 h | website | not read | not read: below |
| `dangerous-gradients` | Trojská 80.15 ‰, below Sídliště Modřany 69.9 ‰, the embankment curve 40 km/h | website | a board from the profile at −5.5 % | unchanged |
| `trackGeometry` `switch-speed` | Kotlářka: 15, 25 through a designed loop branch | Hradil 2020 | not read | not read: the line does not enter that loop |

**What sets the limit, km of the five lines** (86.6 km):

| cause | before | proposed (84640ad) | decided (78fd584) | decided, with W2's rebuild (local) |
|---|---|---|---|---|
| posted or general | 65.72 | 66.48 | 73.75 | 71.36 |
| curve | 15.25 | 14.00 | 11.14 | 10.93 |
| gradient (no source) | 4.64 | 4.62 | – | – |
| switch, and with the rebuild the diamonds | 1.01 | 1.53 | 1.74 | 4.35 |

**Where a slow stretch ended** (two-car set, 30.24 m). #211 read three extensions. The window of `speedLimits` applies only to curves, not to switches, so two remained: the stretch ran to 14 m past the fork, and 5 m bins rounded it up. Measured: the limit lifted **46–48 m** past the fork.

The rule leaves one extension. `restriction-start-end` holds the limit until the rear has passed, so the stretch is only the switch itself (with the user's 2 m until 2026-11-08, none since):
- **The frog** lies a median **11.5 m** past the fork (10.5–13.5 m p10–p90), measured on the 82 facing switches: where the other leg is one gauge off the route.
- **Now 42–43 m** at a switch with no other trackwork after it: the frog and the tram (44–45 m with the 2 m). D 1/2 asks no less: "může být vyšší nejdříve při míjení místa ukončení platnosti omezené rychlosti zadním čelem vlaku" (§ 25.1). A one-car tram: 28–29 m.

On today's data, what the driver still feels as too far is mostly OSM. 65 stretches on the five lines are tagged 15 km/h, up to 110 m long, and 38 of them touch a facing switch. The first rise of the limit past a switch is a median **73–105 m**. Those pieces stand for the trailing switches and diamonds the game did not know. Once the data has them (W2's rebuild) they are dropped (`withoutOwnPieces`).

**With the trackwork in the data (all five lines rebuilt locally, not published).** Only `trackwork` and each switch's `frog` are new; `path`, `pathBack`, the rest of `switches` and every sidecar are unchanged. `lint,surfaces,canted,crossing,spacing,heights` read the same as main at the merge base on all 30 runs (line 17's `crossing` is the known #146), and the smoke drive (`u3` seed 1) passes on every line. A frog was found at 80 of 82 facing switches and 88 of 89 trailing ones; the others take the median.

| line | trailing switches (from diverging) | diamonds | km at 15 km/h | first rise past a fork, median m |
|---|---|---|---|---|
| 9 | 23 (7) | 29 | 1.67 → 1.34 | 85 → 73 |
| 17 | 19 (4) | 26 | 1.11 → 0.81 | 89 → 73 |
| 22 | 24 (4) | 23 | 1.53 → 1.44 | 73 → 73 |
| 23 | 14 (5) | 12 | 1.11 → 1.00 | 85 → 75 |
| 37 | 9 (3) | 11 | 0.69 → 0.45 | 105 → 64 |

OSM's pieces go, but the first rise stays at a median 64–75 m. `--checks limits` says what holds a two-car set last, at the 82 facing switches (before the 2 m rule):

| holds it last | forks |
|---|---|
| another trailing switch or diamond of the junction | 42 |
| the window below, carrying a curve's limit on | 20 |
| the switch itself: frog plus tram | 18 |
| the window below, carrying a posted piece on | 2 |

So at most forks the limit is what the rules ask: 39 of the 82 have a trailing switch or a diamond within 15 m past the frog, and each holds the limit until the rear has passed. `liftPast.twoCars` counts the pieces that start in the first 20 m past the fork, so 51 m is its ceiling: on the rebuild with the 2 m rule its median is 45–46 m on lines 22, 23 and 37 and that ceiling on 9 and 17.

**Right at the end, no margin** (`restriction-past` 0 m, the user, 2026-11-08: "Can we discard the 2 metre rule and keep it simply right after? I realize this because the tram bogie leaves the switch sooner than the end of car so we don't need to hold safety tolerance."). The rear still has to leave each restriction (§ 25.1); the 2 m on top of it are gone. Measured on the published W2 data (`--checks limits`):

| line | two-car lift past a fork, median m (2 m → 0 m) | one car, m | curve: back at the posted speed past its end, median / p90 m | km at 15 km/h or less (2 m → 0 m) |
|---|---|---|---|---|
| 9 | 51 → 49 | 34 | 0 / 2 | 1.32 → 1.25 |
| 17 | 51 → 51 | 36 | 0 / 2 | 1.00 → 0.94 |
| 22 | 45 → 43 | 28 | 1 / 2 | 1.39 → 1.31 |
| 23 | 45 → 43 | 28 | 1 / 2 | 0.91 → 0.88 |
| 37 | 46 → 44 | 29 | 0 / 3 | 0.47 → 0.46 |

At a switch with nothing after it the two-car lift is the frog and the tram, 42–43 m. 51 m is the measure's ceiling: on lines 9 and 17 another trailing switch or diamond of the junction holds the limit at most forks. Across the five lines what holds it last is that trackwork at 52 forks, the switch itself at 19, a curve at 9 and a posted piece at 2.

**2 m past the end** (`restriction-past`, the user, 2026-11-07; 0 m since 2026-11-08, above). Since the initial commit `speedLimits` had taken each 5 m bin's lowest limit over 15 m behind and 5 m ahead ("a curve limit applies to the whole curve"), with no source. Now:
- **The table is per metre.** A curve's limit follows the radius at each metre (`Route._radius`), from 5 m before it asks for less (`CURVE_AHEAD`, unchanged) to 2 m after. A switch's stretch ends 2 m past the frog, a trailing switch's 2 m past its blades, a diamond's 2 m past its rails. `Game.currentLimit` reads the metres under the tram; the 5 m `values` (the signs, the overlay) keep each bin's lowest.
- **The curve's end** is where the game's radius estimate (16 m of heading) last asks for less than the posted speed. Against a short estimate (6 m), the limit is back at the posted speed a median **2–3 m** past the curve's end on lines 9, 17, 22 and 23 and −1 m on line 37, p90 at most 5 m (published data, 222 curves). The 16 m estimate is close to the true radius because most curves here have transitions: the limit climbs step by step along the transition and leaves its lowest speed a median 7–8 m before that end. The p10 of −15 m on lines 23 and 37 is the measure's search reach.
- **The radius estimate smears a sharp end** by about 12 m each way, so on a curve without a transition the limit would run that far past its end. Most curves here have one.
- **Km at 15 km/h or less** on the rebuild: 5.22 → 5.09. The window's spill goes; each of the 272 pieces of trackwork gains 2 m.

**What it does to a run.** `u3,redruns,traffic,lint` on all lines, seeds 1–5, on 78fd584 with the published data, against checkpoint W1: **80 of 80 runs pass**, lint does not move, no run is stuck or unfinished. Line 23's seed 1, which had not finished on 84640ad (the tram behind car 112, which waited for a walker pacing 1.4 m in front of it: #269's scene), now finishes. Outside main's seed spread:

| line | count | W1 mean [min–max] → branch |
|---|---|---|
| 17 | `heatingKnobs` | 14 [13–14] → 13, better |
| 22 | `cyclesBroken` | 0 → 0.6 (seed 3: 1, seed 4: 2) |
| 23 | u3 `green` | 106 [99–113] → 97 |
| 37 | `cyclesBroken` | 0 → 0.2 (seed 5: 1) |
| 37 | `warnPasses` | 0.8 [0–2] → 2.4 |

The earlier moves of 84640ad (`cyclesBroken` on line 9, `jump` on line 22) are inside the spread now. New timing reshuffles traffic like a new seed (#156).

**The broken cycles**, traced in a scratch copy of `traffic.js`, are the scene the breaker was made for (#154, #168): our tram stands short of a car on its track, and the car waits for a tram, until the car leaves after 30 s. Line 22, seeds 3 and 4, at s 5018, 28 m past Pohořelec (the car waits for our tram, limit 50); line 22, seed 4, at s 8407, 73 m before Malostranské náměstí (another tram, 15); line 37, seed 5, at s 4723, 32 m past Balabenka beyond its diverging switch, #168's place (another tram, 15). The redruns check records no places for line 37's warn passes.

**Trip time**, the traffic check's run to the last stop, seeds 1–5, against main's own run at 38024b5 (mean [min–max]):

| line | main, s | branch, s | change |
|---|---|---|---|
| 9 | 5173 [5059–5293] | 5119 [5038–5160] | −1.0 % |
| 17 | 3414 [3394–3439] | 3341 [3251–3424] | −2.2 % |
| 22 | 3630 [3575–3703] | 3575 [3522–3617] | −1.5 % |
| 23 | 2019 [1913–2103] | 1912 [1878–1976] | −5.3 % |
| 37 | 1696 [1644–1745] | 1672 [1621–1703] | −1.4 % |

Dropping the slope limits (4.6 km at 25 or 35) and the 15 m window gains more than 50 on untagged track and 15 over a straight switch cost. On 84640ad, with the slope limits and the window, two seeds had read −2.3 % to +2.2 %.

## Turning loops and stop signs (2026-11-09)

The user, on PR 362's open points: the stop-pass limit is "point limit with overspeed penalty, autopilot has to follow", and where a loop is comes from a rule, not a list: "it's loop at the end of gtfs route, or any loop where two track diverge and come back together with larger than 180 degree turn, that's for double track loop (Sídliště Petřiny). There are side loops like Dvorce or Hlubočepy which are not used by regular service but still need the limit." Both quotes are on their facts in `data/truth.json`.

**Loops** (`tools/track_loops.py`; `python -P -E tools/track_loops.py` lists them). A loop is a path over DI's passes from a switch entered by its toe to a switch left by its toe (the same switch for a balloon) that:
- turns 170° or more from the heading arriving at the first switch to the heading leaving the second: the street's two tracks run opposite ways. From the switch's own leg the turn falls short by the switch's angle: Divoká Šárka 173°;
- has its two switches within 120 m. Sídliště Petřiny's are 72 m apart, the farthest of the termini; circuits round city blocks come back 160–510 m away (Čechovo náměstí's other circuit, Palmovka, Strossmayerovo náměstí, Masarykovo nádraží, Náměstí Míru);
- runs at most 600 m;
- has a mean radius of at least `min-radius-network`, 18 m. A 52 m path turning 276° at Radošovická is a junction drawn in pieces.

On DI's network (2026-09-30) the rule finds 47 loops: the termini, the depots, Dvorce, Hlubočepy and both of Petřiny's loop tracks. Of the 50 GTFS termini with 90 or more trips, the rule misses eight:
- Karlovo náměstí and Zvonařka are short workings round city blocks;
- DI does not draw the loops at Libuš, Nádraží Holešovice, Nákladové nádraží Žižkov, Pankrác and Slivenec yet;
- Nádraží Hostivař lies outside DI's districts.

None of the eight is on the five lines' routes.

A route takes the loop's limit where it follows the loop's whole path, or the part of it from its own start or to its own end. A line that runs over one street of a circuit is not slowed. `tools/build_line.py` writes the stretches as `trackwork.loops`:

| line | stretch | where |
|---|---|---|
| 9 | its first 44 m and last 79 m | Sídliště Řepy, where the run starts and ends |
| 17 | its last 74 m | Vozovna Kobylisy |
| 22 | its first 50 m | Bílá Hora |
| 23 | its first 27 m | Královka |

Line 9's run does not turn at Nákladové nádraží Žižkov: it goes on there as line 10, 89° round the corner.

**Stop signs** are a point limit for the front (`point-restriction`), at each stop's sign (`stopPassPoints`, the game's stop target):
- The game brings the next point to the autopilot through `nextLimitChange`. A train that stops comes to its sign at a crawl anyway.
- A front passing a point more than 3 km/h over costs the overspeed penalty, counted as if the limit held over the set's own length. A point passes in a few frames, so the per-second penalty alone would cost almost nothing.

## Steep descents

The user (2026-11-07): drop the limits from the slope. Both steep descents the user knows are tagged in OSM: 25 km/h on the Trojská way (1256351697, 440 m) and 35 on Hlubočepy – Geologická (465270521, 465270522, 1246102955, 1246102956). `trojska-descent` stays as the backup, 25 km/h between Hercovka and Nad Trojou in that order of stops, where OSM tags no speed (`placeStretches`). Line 17's route climbs Trojská, so it fires on no built line today.

`--checks limits` lists every stretch of at least 20 m steeper than −4.5 % on our track profile, with what is posted on it: 48 on the five lines, 14 of them untagged. The steepest:

| line | between | grade, length | posted | limit now |
|---|---|---|---|---|
| 22 | Jana Masaryka – Krymská | −8.8 %, 415 m | untagged | 50 |
| 23 | Královka – Malovanka | −8.6 %, 70 m | untagged | 15 (a curve) |
| 23 | Malovanka – Hládkov | −8.6 %, 155 m | untagged | 50 |
| 37 | Ohrada – Krejcárek | −8.2 %, 300 m | 50, 60 | 45 |
| 17 | Sídliště Modřany – Modřanská rokle | −8.1 %, 205 m | 60 | 60 |
| 9 | Blatiny – Slánská | −7.7 %, 285 m | 50 | 30 |

The grades are our profile's, before #358's denoising; they are read again on its data before anything is built on them.

## Anticipating the end of a restriction

The user asked whether the autopilot rises toward the limit as a restriction ends. **It does not, on main or on #351's branch:** its target is the limit in force less 0.6 m/s, so it reaches the end of a 15 km/h stretch at 11.8–13.9 km/h. Test drives with the real `Tram` and `Autopilot` on 11 made-up lines, seconds saved per restriction left, median (range):

| autopilot | rising to the limit as it lifts (1.5 s early) | margin 0.45 m/s | margin 0.3 m/s |
|---|---|---|---|
| main's | 0.03 (−1.63 to 0.4) | 1.03 (−0.23 to 2.67), never over | 2.13, over by up to 0.53 km/h for up to 3.3 s |
| #351's | 0.43 (0 to 0.87) | 1.06 (0.33 to 2.0); over only on the 40 ‰ climb | 1.36 |

The margin is the larger lever. Neither is on this branch: #351 rewrites those lines, and the same change behaves differently there. [#370](https://github.com/jnd-cz/prague-transport-sim/issues/370) holds the numbers and the code, blocked by #351.

**Line 17's curve limits since #204.** Before #204 (019c86b, its own data) against main (38024b5, which also has #210, #218 and #237), by place: 34 of 4360 bins moved by 5 km/h or more, in 31 stretches, 17 up and 14 down. Nearly all are one 5 m bin at a 5 km/h step, with the radius changed by under 17 %: `curveSpeed` rounds down to 5 km/h, so a small change crosses a step. The five large moves are not curves: there the sample fell on another OSM way, whose posted speed is the one shown.

| s | between | km/h before → after | tightest R before → after, m |
|---|---|---|---|
| 1640 | Levského (before the first stop) | 50 → 30 | straight: OSM's way |
| 11880 | Podolská vodárna – Výtoň | 30 → 50 | straight: OSM's way |
| 14055 | Karlovy lázně – Staroměstská | 50 → 30 | 511 → 516: OSM's way |
| 20845 | Kobylisy – Březiněveská | 60 → 15 | straight: OSM's way |
| 20425 | Hercovka – Ke Stírce | 30 → 10 | 99 → 91: OSM's 10 km/h way (`maxspeed` 10) |
| 14920 | Právnická fakulta – Čechův most | 10 → 15 | 22 → 22 |
| 8700, 13750, 16075, 17710, 18535, 18755, 20640, 20685, 20910, 11275 | ten places | 5 down | 2–13 % tighter |
| 325, 2325, 4140, 11185, 11220, 12970, 13400, 13980, 17450, 17740, 18590, 20615, 20665, 20705, 20765 | fifteen places | 5 up | 0–16 % wider |

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

Faces and placement are in `src/speedSigns.js`, held by `tools/test_speed_signs.py`; `Game._initSigns` stands them (#364) and lists each in `game.signBoards`. `--sheet` draws them all. Research: [signals.md](../research/prazsketramvaje/signals.md).

**Size:** 200×300 mm with a 30 mm white frame, panel 140×240 mm. D 1/2 gives none; this is the same sign family on the website, and D 1/2's drawings have that shape. Estimated from the drawings: triangle 400×300 mm, zone plate 200×312 mm.

**Figures and shapes from photos (the user's of 2026-11-08, the website's):** shapes and colours follow D 1/2; the figures follow the photos.
- Every sign's figures are a heavy condensed DIN, as on the user's 60 Rychlostník and 80 climb board and the website's 10 and 30. D 1/2 draws a heavy face filling the panel, and a serif on the gradient boards.
- The faces use Bahnschrift Condensed Bold, Windows' DIN 1451 (the user, 2026-11-08: "Bahnschrift bold looks good"); elsewhere the nearest condensed face.
- Its figures are wider than the signs': two are 1.18 as wide as high, the photos' 0.86–1.01. They are drawn at 0.8 of their width, which matches the photos side by side, the vertical strokes as heavy as theirs (the user: "stretch it so it looks close to the real signs").
- They are the photos' size, 113 mm (0.47 of the panel), on every plate: restriction, point, Rychlostník and zone.
- Text on the plates (ZÓNA, the hours, a car type) keeps the font's own width ("keep the type under number, unsqueezed").
- The gradient boards' figures are larger and heavier than the photos', to read in the game (the user, 2026-11-08). They are 0.30 of the board high (the photos: 0.23), bold with an outline of 0.035 of their height.
- The gradient board's pentagon has its shoulders 0.56 of the height from its point's edge, as on both photos and D 1/2 p. 52. They were drawn at 0.42.
- The speed switch's arrow is measured on the two R01 photos ([speed-switch signals](2026-11-07-speed-switch-signals.md)).

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

**Limits that come only from a curve** (11.1 km since the 2 m rule; R over 25 m) have no real sign. The user (2026-11-08): "I would still keep them for now for diagnostic purposes, we can drop them later with more stable release". So they keep a board, today's black on white one, marked as a diagnostic in the code. The gauge marker and the hint show them too. In the driving view they read as real signs in the old design, three to one against the real ones (301 to 83 on the five lines), and 13 stood within 20 m of a real sign. So they show only with the debug overlay (F8), and none stands within 20 m of a real sign (the user, 2026-11-08, #389: "Only with F8"). Today's boards stand at every change and call themselves rychlostník; the real signs replace them everywhere else.

**Size in the game:** the user (2026-11-08): "because of monitor's low dpi and resolution we need larger signs". Measured in the game's cab view at 1920×1080 (about 96° across, 15 px per degree), boards hung over the track. The figures need about 8 px to read.

| scale | board | figures 113 mm × scale read up to | at 50 m | at 100 m |
|---|---|---|---|---|
| 100 % | 200×300 mm | about 12 m | 2 px: colour and shape only | 1 px, specks |
| 150 % | 300×450 mm | about 18 m | 3 px | 1.5 px |
| 200 % | 400×600 mm | about 24 m | 4 px: colour and shape | 2 px |

An eye reads the real 113 mm figures at about 75 m (5′ per character). No board size the scene can hold matches that on a 1080p screen: 100 % would need about 6 times its size. Where the driver must act (a restriction 90–125 m ahead at 50 km/h, a warning board 140–200 m ahead), the board shows its kind by colour and shape, and the number has to come from elsewhere: the gauge marker and the hint, or a zoom key that narrows the view as an eye would. The user chose from the screenshots ([the review page](https://claude.ai/artifact/Hx86b3fvNzVYjJnGWDfazq)): "pick 200% now for testing, can you keep the size of signs a parameter that can be changed later?" `SIGN_SCALE` in `src/speedSigns.js` is 2; `shownSize(sign)` gives the size the game shows, `signSize(sign)` the real one.

**Where Bahnschrift is missing** (macOS, Linux, phones, browsers that hide installed fonts), the faces use **D-DIN Condensed Bold**. It is Datto's DIN 1451 recreation under the SIL Open Font License. `loadFigureFont()` loads it from Datto's repository through jsDelivr, pinned to commit e199c84 (the user, 2026-11-08: "Can we load the font externally anyway and use the din one as fallback?"). Bahnschrift itself may not be redistributed.
- The game must await `loadFigureFont()` before it draws the faces (#364). If the load fails, the next condensed face in `FIGURES` draws.
- Each face is narrowed by what the canvas measures of it, so two figures come out 0.94 as wide as high whatever face draws: Bahnschrift at 0.79 of its width, D-DIN at 0.88. `test_speed_signs` holds that between the photos' 0.86 and 1.01.
- Side by side, D-DIN is closer to the photos in two places. Its 3 has a flat top, as on the website's 30, where Bahnschrift's is round. Its strokes are heavier, as on the 80 board. Its 6 and 9 end in a curved hook, where Bahnschrift's run straight.
- This is the game's first font from a third-party host. Hosting the file with the game instead would remove that; under the OFL the licence must go with the file.

**Curves under 25 m found by the rule, against the list:** Spálená (9, 22, 23), Chotkova (22, 23), Blanická (9), Na Moráni (9), Na Žertvách (37), Klárov (22, 23, at a switch). Not found by radius: Malostranské náměstí (both), Náměstí Míru (both), Havlíčkova. These may be other directions or a radius read over 16 m; the implementation issue checks them.

## The 65 and 70 km/h stretches

See [places.md](../research/prazsketramvaje/places.md). In short:
- **No source shows these signs.** The rule makes them a Rychlostník, white number on black. The user's photo of one for 60 (2026-11-08) shows it: white DIN figures on black, a white frame, hung from the span wire.
- **By type:** § 49.17 allows several signs for different car types. OSM's note fits that: a 65 for all and a 70 for the 14T.
- **How the type is written** is not in any source read. The faces draw it on a strip under the panel, as the arrow is, marked unsourced.
- **The T3's limit** there is 65 either way, its own top speed.
