# Notes from prazsketramvaje.cz (#215)

Prague tram rules, signals, switches and the T3, gathered on 2026-11-03 from
[prazsketramvaje.cz](https://www.prazsketramvaje.cz) and the DP Praha documents it publishes, each fact
set against what the game does now (main at 7cac287). The user picks from
[truth-candidates.md](truth-candidates.md) what goes into `data/truth.json`.

| Note | What |
|---|---|
| [rules-d1-2.md](rules-d1-2.md) | D 1/2: speeds, gradients, stops, timetable, driving, brakes, priority |
| [signals.md](signals.md) | every signal and sign in D 1/2, its look (for procedural drawing) and the website's photos |
| [switches.md](switches.md) | switch kinds, the driver's duties, switch signals, speed switches, the register of radio switches on our lines |
| [t3.md](t3.md) | the T3 from DP's textbook and exam sets: start-up, pedals, brakes, sanding, switches from the cab, lights, faults |
| [t3-accelerator.md](t3-accelerator.md) | the T3SUCS pedals, accelerator and interlocks from ČKD's TR 37 documentation, numbers and a simulation model |
| [places.md](places.md) | small-radius curves, night zones, speed switches on our lines |
| [web-notes.md](web-notes.md) | the rest of the website: switch types and registers, signal photos, power, operating practice |
| [truth-candidates.md](truth-candidates.md) | the facts proposed for `data/truth.json`, with priorities |

## Sources

| Document | Version | URL |
|---|---|---|
| DP Praha, *D 1/2 Dopravní a návěstní předpis pro tramvaje* | approved 2025-01-30, in force 2025-09-01, 62 p.; the site's file of 2026-02-01 | [PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/predpis_d1-2_20260201.pdf) |
| DP Praha exam set D1 *Provozně předpisová soustava* (PPS) | valid from 2025-09-01, 41 p. | [PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_1_pps_20260201.pdf) |
| DP Praha exam sets *Technická příprava* and *T3 – zrychlovač* | valid from 2025-09-01 and 2023-08-23 | [PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_20260201.pdf), [PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_t3zr_20260201.pdf) |
| DP Praha, *Tramvaje T3.SUCS, T3M, T3R.P, T3R.PLF, učební pomůcka* | January 2009 (03/09); the game's copy is in the store's `reference/` (DATA.md) | [PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_t3.pdf) |
| prazsketramvaje.cz articles (speed signals, switch registers, signals, operation) | undated pages, read 2026-11-03 | listed in each note |
| Index of DP's regulations, exams and textbooks on the site | | [2012112501](https://www.prazsketramvaje.cz/view.php?cisloclanku=2012112501) |

D 1/2 is marked "for work use only"; the notes paraphrase it and cite paragraph and page, and copy no
text. If the PDFs should be kept, they belong in the store's private `reference/` group like the T3
textbook (a snapshot publish, not part of this issue). Other documents on the index page not read
here: road traffic rules for drivers (PSP), line routing and tariff, the D 2/2 rules for two-axle
trams, the textbooks of other types.

The D 1/2 and exam drawings were looked at as page images (Inkscape renders, not committed); each
note gives the page.

## Where the game differs from the sources

1. **Switch and crossing speeds** (#211): facing a switch is **15 km/h straight as well as
   diverging** (the game: 30 straight); trailing **15 from the diverging branch, 30 from the straight
   one** (the game: none); **15 over track and wire crossings** and **in loop curves** (the game:
   none). D 1/2 § 25.4–5.
2. **Where a limit ends**: from the front's entry until the **rear** passes the end sign (§ 25.1);
   a point restriction needs only the front. The game's whole-tram minimum matches; #211's extra
   window does not.
3. **50 km/h is the network's maximum** unless a Rychlostník sign allows more (§ 25.1; PPS Q83).
   The game gives 60 on dedicated track without a sign; line 17's OSM tags of 60–70 likely stand for
   real Rychlostník signs whose places are not known yet.
4. **Steep descents**: D 1/2 sets no speed (the exam marks "25 km/h" wrong, PPS Q53); its "dangerous
   gradient" rules are about entering an occupied section and starting. The game's 25 km/h matches a
   **local rule on Trojská street (line 17)**: 470 m at 80.15 ‰, stop and test the brake, then roll
   without power at 20–25 km/h, one train per block; uphill one train in the section at full power.
   The game applies 25 km/h to every grade under −6 % and 35 km/h under −4.5 % (no source), with no
   stop, test or blocks ([places.md](places.md)).
5. **Small-radius curves**: under R 25 m, **15 km/h** over the whole curve, with an "r" sign; 11 such
   places lie on our lines ([places.md](places.md)). The game's formula gives 10 km/h at R 20 m.
6. **Stopping point**: the first train's front stands **next to the stop sign or just before it**
   (§ 27.6); the game aims 6 m past the platform point and accepts up to 12 m past the sign.
7. **Switch control**: the register lists the switches on our lines as **radio-controlled, their
   trolley contacts removed in 2007 or never fitted**; D 1/2 keeps contact control only as a
   transitional case (§ 52.1). The driver sets a **left / straight / right selector at least 40 m
   before** the switch; the switch is thrown and blocked when the front passes the **receiver, 25–35 m
   before it**. Two line 17 switches are **hand-set lockable** ones that stay straight in service:
   **U07** at Podolská vodárna (from Kublov, next to the #204 work) and **U17** at Ke Stírce. The game
   works every switch by contact, by design; the user keeps both, the player chooses (answer 1 below).
8. **Switch signal**: a **steady** arrow already means "set and locked"; **blinking** adds "blocked
   by a train in the circuit"; a centre dot means "assume not locked" (§ 45). The game blinks the
   arrow "while locked" and has no centre-dot aspect.
9. **Section insulators and wire crossings** are passed **coasting with the pantograph up** (§ 33.14,
   § 49.23): a skill of the same kind as the contacts, missing from the game; their places are needed.
10. **Speed signs**: a restriction is a **black number on yellow**; a Rychlostník (higher speed) a
    **white number on black**; warning boards are yellow triangles; ends have a diagonal
    ([signals.md](signals.md)). The game draws one board, black on white, placed from its limit profile.
11. **Timetable**: on time is **0 s early to 179 s late** from an intermediate stop and **0–59 s** from
    the first stop (§ 16.2); the game allows 5 s early and scores 60 s and 180 s classes.
12. **Request stops**: passing one, the front passes the sign at **30 km/h at most** (§ 25.5 b), and a
    list of cases forces a stop, among them a train **without door-request buttons** (§ 27.14).
13. **The T3SUCS**: the brake pedal's **parked** position whenever standing; a fast change from drive
    to brake loses the dynamic brake; the mechanical brake comes in by itself at 5–3 km/h; the
    emergency button rings the bell; lights by day and night ([t3.md](t3.md)).
14. **Safety stopping places**: every train stops before the sign and tests the parking brake; on
    line 17 before the Trojská descent and at both boarding stops of the Vozovna Kobylisy loop
    ([places.md](places.md)). Missing from the game.
15. **On-board timetable display**: DP's dispatch system shows on time as 0–179 s late, early by more
    than 1 s red (over 60 s flashing), 180–419 s late yellow, 420 s and more flashing yellow
    ([web-notes.md](web-notes.md) 4.7): a ready design for the game's deviation display.

## The user's answers (session 2026-11-03)

Quoted as given; they go into `data/truth.json` as the user's facts (picker: "Your answers").

1. Switches: "For game purposes I'm keeping both historic current switch and new radios at the same
   time. It costs nothing and player can choose which ones to use." OSM can mark which switches are
   remote-controlled (`railway:switch:electric=yes` on 525 of 1017 tram switch nodes) and carries DP's
   number in `ref` on 257 ([switches.md](switches.md)).
2. Speeds: "For now the game uses 60 km/h spped sign at most, higher speeds to be picked up from osm
   (openrailwaymap) track info."
3. The T3 pedals: "currently there are only placeholder simplified controls without pedals, you can
   research that and how to simulate zrychlovač behavior." Done: [t3-accelerator.md](t3-accelerator.md).
4. Request stops: the game's T3 has no request buttons; "In short driver should stop for any
   passengers waiting on the stop." This agrees with D 1/2 § 27.14 a and d.
5. Doors: "open door currently block adding power, not sure if brake is auto applied as well." ČKD:
   a door relay blocks traction; no brake from the doors found ([t3-accelerator.md](t3-accelerator.md) 4).
6. Section insulators: not known. No public list was found; OSM does not tag them (its 57
   `power=insulator` nodes in Prague all sit on 22 kV and 110 kV lines) and the DTM snapshot (ZPS, DI)
   has no overhead-line equipment ([signals.md](signals.md) SIG-W1).
7. Pantographs: "for t3 we use both cars pantographs as it is in real operation". The second car's
   pantograph is why contact-worked switches are blocked until the whole set has passed
   ([switches.md](switches.md) SW-C6).

## Still open

1. Where are line 17's Rychlostník signs (OSM tags 60, 65, 70)? With answer 2 only OSM's values are
   needed.
2. If contacts stay: which direction does current set (the game: current = diverging), and how far
   before the switch is the contact? The T3SUCS side is known: its switch button draws current only
   with drive off and below about 12 km/h ([t3-accelerator.md](t3-accelerator.md) 8.2).
3. Section insulators on our lines: a survey from street-level imagery (the green diamond signs), or
   DP's data.
