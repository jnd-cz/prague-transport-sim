# Switches: kinds, control, signals, registers

From D 1/2 § 29–30, 45–48, 52 ([rules-d1-2.md](rules-d1-2.md) names the document), the exam set
*Provozně předpisová soustava* (D1 PPS, valid from 2025-09-01,
[PDF](https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_1_pps_20260201.pdf)), and the
register of radio-controlled and speed switches on prazsketramvaje.cz
([2006041262](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041262)). How the T3 driver
works switches from the cab is in [t3.md](t3.md).

## Kinds (§ 29, p. 27–28)

| ID | Kind | What it is | Driver's duty |
|---|---|---|---|
| SW-K1 | hand-set (*ručně ovládaná*) | thrown with the **setting key** (*stavěcí klíč*) | throw it, check the blades |
| SW-K2 | remote-controlled (*dálkově ovládaná*) | thrown from the train's controls (radio), or by a control outside the train; **always has a light signal**, part of the switch circuit. The circuit **starts at the "radio receiver" sign** and ends at the **unblocking device** (§ 29.14). The website ([web-notes.md](web-notes.md) 2.3): the receiver lies in the ground **right of the track, 25–35 m before the switch**; the driver sets a **left / straight / right selector** on the panel **at least 40 m before**; the switch is thrown and **blocked when the car's front passes the receiver**; two switches close together are thrown together; once blocked by radio, a trolley contact cannot throw it | set the selector, check the signal; pass the receiver sign **only when no other train is in the circuit** (§ 29.16) |
| SW-K3 | lockable (*uzamykatelná*) | blades locked in their end positions; a light signal or the "U" sign (§ 29.3) | after throwing it by hand: **hand test** that the blades are locked: the key cannot push the blade off the stock rail near its tip (§ 29.10–11) |
| SW-K4 | safety / spring-return (*zajišťovací*, *vratná*) | returns to its normal position by a spring after the car has passed (§ 29.4); the "Z" sign | – |
| SW-K5 | speed switch (*rychlostní*) | always lockable, with a call signal, an entry sleeper signal and a light switch signal; track circuits (§ 30) | below, SW-R |
| SW-K6 | contact-worked (*elektricky ovládaná*, *pracovní trolejový kontakt*) | thrown by the pantograph passing a contact in the wire; **transitional**: D 1/2 leaves it to a director's circular until the contacts are removed (§ 52.1, p. 62) | below, SW-C |

All radio switches in the register are "spring blades, lockable" (*pružné jazyky, uzamykatelná*).

## Rules for the driver (§ 29, 34.10)

| ID | Rule | Game now | Status |
|---|---|---|---|
| SW-D1 | The driver is responsible for entering a facing switch with its blades **correctly set and closed** (§ 29.5). | a wrongly set switch stops the tram 0.3 m before it, holds it 6 s, +30 s, −150 (`src/game.js:1264-1276`) | partly (the game stops the tram for the driver) |
| SW-D2 | Facing a switch is **forbidden** when the blades cannot be seen; when the train trailed through and **threw** the switch and would now go back over it with the switch under the train; at a **free switch** (blades held to neither side) (§ 29.6). | – | missing |
| SW-D3 | **Trailing a lockable, speed, or strut-secured switch set the wrong way is forbidden** (the wheels would force the blades) (§ 29.7). Ordinary spring switches may be trailed through. | trailing switches not in the data | missing |
| SW-D4 | Before running **against the points of a trailing switch** (e.g. backing), throw it to check it is not free (§ 29.13). | – | n/a |
| SW-D5 | After **remotely setting a lockable switch**, check the lock on its light signal; if the signal shows "not locked", hand-test it; without a signal, or with a broken one, hand-test it (§ 29.8–10). | – | missing |
| SW-D6 | A **faulty** switch, or one that will not lock even after cleaning: go on only with the dispatcher's consent, possibly slowly with a person watching the blades (§ 29.12). | – | n/a (event) |
| SW-D7 | **Blocking**: the light signal shows when the switch is blocked against being thrown; without it, assume it may be thrown under the train (§ 29.15). | the indicator blinks "while the switch is locked" (`src/models.js:778-780`) | differs: see SW-S1 |
| SW-D8 | **Track brake used on a switch**: stop and check the brake, the switch, and that it was not thrown (§ 34.10). | – | missing |
| SW-D9 | Work on a switch: do not enter its circuit; once a train is in it, the work waits until it has passed (§ 20.3; PPS Q90). | – | n/a |
| SW-D10 | Speeds: facing **15 km/h** straight or diverging; trailing from the diverging branch **15**, from the straight branch **30**; a switch with the "V" sign **10** facing diverging; speed switches up to the number shown (§ 25.4–5, § 49.20). | 15 diverging / 30 straight, facing only (`src/game.js:118`) | differs; #211 |

## Light signals of remote-controlled and hand-set lockable switches (§ 45, 47, p. 43–48)

| ID | Aspect | Look (p. 44, 48) | Meaning |
|---|---|---|---|
| SW-S1 | *Postavení vlakové cesty vpravo / přímo / vlevo* | black panel with a dot matrix of **red LEDs**; the lit LEDs form a broad **arrow** pointing right, up or left; the unlit LEDs of the other symbols show dark grey | route set that way **and the switch locked**. **Blinking** = in addition **blocked** against being thrown by remote control (a train is in the circuit) |
| SW-S2 | *Neurčitá vlaková cesta* (undetermined) | a small red **cluster in the middle** | the route may not be set properly: **assume the switch is not locked**. Blinking = blocked. |
| SW-S3 | two switches close together | signals side by side or stacked; the **lower signal belongs to the first switch** in the direction of travel, the upper to the second; plates "L", "P", "1", "2" (white on black) say which | |
| SW-S4 | second (auxiliary) signal | where one signal cannot be seen both from where the switch is set remotely and where it is set by hand | |
| SW-S5 | *Dálkově ovládaná výhybka mimo provoz* | a **white St Andrew's cross** over the signal panel | not remote-controlled; the switch counts as an ordinary one (PPS Q108) |
| SW-S6 | *Přijímač rádiového signálu* (radio receiver) | white square, black **radio symbol** (a dot with three arcs widening downwards); plates "L", "P", "1", "2" if only one of a pair is radio-controlled | start of the switch circuit; the train registers here |
| SW-S7 | *Rádiové ovládání výhybky mimo provoz* | the receiver sign crossed by an **orange X** | the switch cannot be set by radio |
| SW-S8 | *Číselné označení výhybky* (number) | black number on a white plate with a black edge, e.g. "768" | identifies the switch (register below) |
| SW-S9 | *Číselné označení výhybky s pomocným návěstidlem* | white "U07" on black | a hand-set lockable switch with an auxiliary light signal |
| SW-S10 | *Uzamykatelná výhybka* | yellow panel framed by a **red "U"** (red left, bottom and right edges) on a white plate | hand-set lockable switch without a number |
| SW-S11 | *Zajišťovací výhybka* | yellow panel with a **red "Z"** | spring-return switch, or one secured against throwing |
| SW-S12 | working contact of a remote-controlled switch | white square, **black triangle** with an **orange square** inside (PPS Q102) | marks the place of the trolley contact |

Game now: SW-S1 as a red LED chevron hung 8 m before the switch, blinking "while the switch is
locked" (`src/models.js:778-819`, `src/game.js:729, 1250-1254`); SW-S6 exists as
`makeRadioSwitchSign` but no switch uses it; SW-S12 is the game's contact sign
(`src/models.js:861-871`), with a yellow plate on the wire. SW-S2, SW-S3, SW-S5, SW-S8 to SW-S11
are missing. **Differs**: in D 1/2 a steady arrow already means "set and locked"; blinking adds
"blocked by a train in the circuit".

## Speed switches (§ 30, 46, p. 28, 45–47)

Order along the track (diagram p. 46): the number sign "R 01" (white on black; it also marks the
radio receiver) → the **call signal** → the **entry sleeper signal** → the track circuits begin →
the switch → the **light switch signal** at the end of the circuit.

| ID | Item | Look | Meaning |
|---|---|---|---|
| SW-R1 | *Číselné označení rychlostní výhybky* | white "R 01" on black | start of the circuit, radio receiver. The train may pass it even with another train in the circuit (§ 30.2). |
| SW-R2 | call signal (*výzvové návěstidlo*) | black panel with **yellow LED bars**: vertical (straight), leaning right, leaning left | the system has registered the train for that direction; lit **about 5 s** after registration, so keep enough distance behind the train ahead to see it (§ 46.2). Not lit: go on with extra care (§ 30.2). |
| SW-R3 | entry sleeper signal (*vjezdové pražcové návěstidlo*) | round black disc: **white vertical bar** = may enter, **white horizontal bar** = may not | entry into the track circuits. Stop shown permanently, even after the train ahead has left: call the dispatcher (§ 30.3; PPS Q103). Dark: go on carefully only if no train is in the circuits. |
| SW-R4 | light switch signal | black panel with a white **chevron** (pointing up for straight, sideways for a branch), blinking = blocked; under it a white **seven-segment number** (e.g. "50", "40") | route set and locked; the number is the **speed allowed over the switch** that way. No number: pass as a lockable switch (15 km/h; PPS Q104). Dark although the train is in the circuits: pass as a lockable switch (§ 30.4). |
| SW-R5 | *Ovládání rychlostní výhybky mimo provoz* | "R 01" crossed by an orange X | no radio control; other rules stay |
| SW-R6 | *Rychlostní výhybka mimo provoz* | white crosses over the call signal and the switch signal | counts as a lockable switch |

Speed switches in the register (speeds straight / diverging, km/h):

| No. | Place | Straight | Diverging | Our lines |
|---|---|---|---|---|
| R01 | Prašný most od Hradčanské | 50 | 40 | – |
| R02 | Vozovna Střešovice, into the depot | 30 | 15 | – |
| R03 | Letenský tunel od Strossmayerova náměstí | 50 | 40 | 17 passes Strossmayerovo náměstí (check) |
| R04 | Nádraží Braník, into the loop | 30 | 15 | **17** |
| R05 | Průběžná od Strašnické | 30 | 15 | **22** (check) |
| R06 | Depo Hostivař od Ústředních dílen | 30 | 15 | – |
| R07 | Kotlářka, into the loop | 50 | 15 | **9** |
| R08 | Lihovar od Hlubočep | 30 | 30 | – (new; Dvorecký most) |
| R09 | Podolské nábřeží od Dvorců | 30 | 15 | **17** (new; Dvorecký most junction, #209) |

## Contact-worked switches (SW-C)

| ID | Fact | Source | Game now |
|---|---|---|---|
| SW-C1 | Control by working contact is **transitional**, governed by a director's circular until the contacts are removed. | D 1/2 § 52.1, p. 62 | every facing switch is contact-worked, by design ("a driver skill"; `src/game.js:719-722`) |
| SW-C2 | The register lists every radio-controlled switch with its trolley contact as **"no / removed on <date>"** (most in April–August 2007, e.g. Výtoň 614–616, Strossmayerovo náměstí 529–532, Palmovka 617–622, Ohrada 626–628) or **"no / never fitted"**. | register 2006041262 | – |
| SW-C3 | A remote-controlled switch may still have a **working trolley contact**, marked by SW-S12. | PPS Q102 | the game's contact sign |
| SW-C5 | Two switches in a row: a black plate with a white **L** or **P** under the contact sign says which branches that contact serves; a contact out of use is covered by a **black plate with a yellow cross**. | website 2006041276 | – |
| SW-C6 | Blocking is released when the **pantograph** passes the release contact; in a 2×T3 set the **second car's pantograph** is up too (the user, 2026-11-03: both cars' pantographs, as in real operation), so the switch is released only after the whole set has passed. | website 2006041394; user | only the first car's pantograph counts (`src/tram.js:34`) |
| SW-C7 | Why switches are blocked: with 2×T3 sets the **second car's pantograph sometimes threw the switch** under the set and tore it apart. The blocking system: a **blocking contact** right after the working contact, an **auxiliary contact about 15 m** (a car length) past the switch, an **unblocking contact about 30 m** past it; the switch unblocks when a pantograph closes the unblocking contact **while the auxiliary contact is not closed**. Modern switches block by resonant track circuits and ultrasonic detectors instead. | student club slides *Technika pražských tramvají* (undated; [PDF](https://k5.sh.cvut.cz/~oskar/stah/technika_tramvaji_darkblue.pdf)) | the game sets a switch at the contact and has no second pantograph |
| SW-C8 | On the T3SUCS the switch button (TV) draws line current through a ≈3.5 Ω resistor so the working contact sees current; it works only with **drive off** (M1 out) and the accelerator at positions **1–30**, i.e. coasting or braking below roughly 12 km/h. | ČKD wiring diagram 1-38-370 444 F ([t3-accelerator.md](t3-accelerator.md) 8.2) | the game's contact: power or not |
| SW-C4 | With work going on at a switch, the driver must not enter its circuit (PPS Q90 offers "must not stop before the working contact" as a wrong answer). | PPS Q90; § 20.3 | – |

**Finding for the user:** the register says the switches on our lines are radio-controlled without
trolley contacts, while the game makes every facing switch contact-worked. AGENTS.md lists contacts
among the driver's real skills. Whether to keep contacts, switch to radio control (the T3's
direction buttons, [t3.md](t3.md)), or mark each switch by the register, is the user's decision.
Electrically controlled switches with contacts have their own register on the site
([2006041261](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041261), see
[web-notes.md](web-notes.md)).

## Hand-set lockable switches on our lines (website [2010083001](https://www.prazsketramvaje.cz/view.php?cisloclanku=2010083001), [2006041279](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041279))

| No. | Place | Line | Note |
|---|---|---|---|
| U07 | Podolská vodárna, from Kublov (into the loop) | 17 | hand-set, lockable, auxiliary light signal; the city-bound track passes it straight. Going north on that track: the diamond crossing with the loop's exit track, the trailing switch from the loop, then U07 (relevant to #204) |
| U17 | Ke Stírce, from Trojská | 17 | the same kind |
| U09 | Ke Stírce, from Bulovka | – | |
| U14 | U Balabenky, from Palmovka (upper) | 37 (check) | |
| U05 | Plzeňská × Radlická, from Bertramka | 9 (check) | |
| U03 | Motol depot exit | – (depot) | |
| "U" (no number) | Levského loop, stub track | 17 (terminus) | |

Their number plates are **white on black** (radio and electric switches: black on white). In
service they stay set for the regular route; the driver sets them only for diversions.

## Line 17's switches, place by place

The website's crossing and loop pages (2006–2019) give each junction's switches, which curves are
used in service, and older numbers next to the register's ([web-notes.md](web-notes.md) 2.6):
Levského loop, Nádraží Braník (relief point; hand-set pivot switches in the loop), Dvorce (691, 692),
Podolská vodárna (690, U07), Výtoň (614–616), Palackého náměstí (646–649), Národní divadlo (685, 771,
788; meeting ban "T - KT"), Staroměstská (689, 512), Čechův most (566, 733; a gauntlet on the bridge),
Letenský tunel, Strossmayerovo náměstí (529–532), Výstaviště (783–787), Ke Stírce (656, U09, U17),
Kobylisy (658–660), Vozovna Kobylisy (663, 664; safety stopping places in the loop).

## Switches in OSM

The local extract (`raw/osm/praha.osm.pbf`, 2026-10-22) has **1017 `railway=switch` nodes on tram
track**: **257 carry DP's number in `ref`** (e.g. 616 at Výtoň, 625 "dolní Klárov", 674.L1 Lehovec),
**525 have `railway:switch:electric=yes`**, 494 a `survey:date` (mostly September 2025). The build
(`tools/build_line.py`, switches from OSM topology) could take the number for the plate (SW-S8) and mark
remote-controlled switches from these tags instead of from the register's place names.

## Radio-controlled switches on our lines (register 2006041262)

Matched by place name to the lines' stops. Whether the line passes each switch, and facing or
trailing, has to come from the track graph. Rows the register marks red (cancelled: 515, 534, 537,
541, 542, 570, 679) are left out; their replacements are listed (806 for 534, 807 for 679).

| Line | Switches (number, place, "from") |
|---|---|
| 17 | 773 Levského do Libuše; 599P/599L Sídliště Modřany into the loop; R04 Nádraží Braník into the loop; 692 Dvorce od Nádraží Braník; 691 Dvorce od Kublova; R09 Podolské nábřeží od Dvorců; 801 Podolské nábřeží od Lihovaru; 802 Podolské nábřeží od Podolské vodárny; 690 Podolská vodárna od Výtoně; 647L/647P Palackého náměstí od Výtoně; 646L/646P od Moráně; 648L/648P od Anděla; 649L/649P od Mánesa; 788 Národní divadlo od Mánesa; 771 od Staroměstské; 685P/685L od Národní třídy; 689 Staroměstská od Národního divadla; 522 od Mánesova mostu; 512 od Právnické fakulty; 566 Čechův most od Právnické fakulty; 733 od Letenského tunelu; R03 Letenský tunel od Strossmayerova náměstí; 786 Výstaviště Holešovice od Nádraží Holešovice; 787 od Veletržní; 783–785 in the loop; 656 Ke Stírce od Kobylis; 658 Kobylisy od Zenklovy; 659 od Vozovny Kobylisy; 660 od Ďáblic; 663 Vozovna Kobylisy into the loop; 664 in the loop |
| 9 (10) | 803 Sídliště Řepy into the loop; 683 in the loop; 568/569 Vozovna Motol; R07 Kotlářka into the loop; 678 in the loop; 642P/642L Anděl od Plzeňské; 798 od Palackého náměstí; 747 Plzeňská x Radlická; 806 Újezd od Národního divadla; 535 od Malé Strany; 536 od Anděla; 685P/685L Národní divadlo od Národní třídy; 807 Lazarská od Národní třídy; 643 od Myslíkovy; 781 od Vodičkovy; 680 Myslíkova od Lazarské; 782 Senovážné náměstí od Jindřišské; 719 od Hlavního nádraží; 780 od Masarykova nádraží; 761 Hlavní nádraží od Senovážného náměstí; 762 in the loop; 514 Olšanské náměstí; 608–610 Nákladové nádraží Žižkov; 797 Želivského od Nákladového nádraží Žižkov; 743 od Flory; 695 od Vinice; 739–742 Olšanské hřbitovy; 693 Flora od Olšanského náměstí; 694 od Orionky; 520P/520L od Želivského; 634P/634L Tylovo náměstí od Náměstí Míru; 682 od Štěpánské; 723P/723L od Bruselské; 521 od Muzea; 652 Francouzská od Náměstí Míru; 712–714 Karlovo náměstí; 715 Moráň; 648P/648L Palackého náměstí od Anděla |
| 22 | 665 Bílá Hora into the loop; 718 Vypich in the loop; 624 into the loop; 716 Královka od Vypichu; 672 Malovanka od Královky; 805 od Hládkova; 751L/751P Dlabačov a Malovanka od Pohořelce; 523 Brusnice od Pohořelce; 744 od Milady Horákové; 804 od Pražského hradu; 748 Chotkovy sady od Malostranské; 750 od Pražského hradu; 774 od Badeniho; 638 Malostranská od Letenské; 511 od Mánesova mostu; 625 od Klárova; 640/641/790 Klárov; 806, 535, 536 Újezd; 685P/685L Národní divadlo; 712–714 Karlovo náměstí; 682, 634P/634L, 723P/723L Tylovo náměstí; 701 Francouzská od Jana Masaryka; 651 od Korunní; 652 od Náměstí Míru; 724, 728, 538 Koh-i-noor; 725 Minská; 732, 578, 572, 697 Kubánské náměstí; R05, 605–607 Průběžná; 717 Radošovická od Průběžné; 639 Vinice od Strašnické; 752/753 Vozovna Strašnice; 759/760 Zahradní Město |
| 23 | 673 Královka od Malovanky; 672, 805 Malovanka; 746 Myslbekova do ulice Hládkov; 523, 744, 804 Brusnice; 748, 750, 774 Chotkovy sady; 638, 511, 625 Malostranská; 806, 535, 536 Újezd; 685P/685L Národní divadlo; 807, 643, 781 Lazarská; 782, 780 Senovážné náměstí; 779 Na Poříčí od Masarykova nádraží; 795 od náměstí Republiky; 555 od Bílé labutě |
| 37 | 813L1/813L2 Spojovací in the loop; 650 Vápenka in the loop; 629–632 Vápenka; 626–628 Ohrada; 619–622 Palmovka (upper); 617, 618, 544, 574 Palmovka (lower); 737 Balabenka od Palmovky; 623 od Vysočanské; 575 od Harfy; 735, 736, 796 U Balabenky; 563–565, 600 Harfa; 705 Starý Hloubětín od Lehovce; 545–547 Starý Hloubětín; 654, 671, 789 Vozovna Hloubětín; 674L1/674L2 Lehovec in the loop |

Uses: real number plates (SW-S8) at each switch, the radio-receiver sign (SW-S6) where the circuit
starts, and a check that the game's switches (17 facing on line 17) match the register's places.
