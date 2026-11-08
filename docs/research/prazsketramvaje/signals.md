# Signals (*návěsti*) for Prague trams

From D 1/2 part VIII (§ 41–51, p. 36–61; see [rules-d1-2.md](rules-d1-2.md) for the document) and
prazsketramvaje.cz's signal pages. Looks are described so they can be drawn procedurally; the
drawings are on the D 1/2 page given, the photos at the URLs. Switch signals are in
[switches.md](switches.md). Status as in [rules-d1-2.md](rules-d1-2.md).

General (§ 41, p. 36): a doubtful or unclear signal counts as the more restrictive one; every fault
of a signal is reported. Where tram and trolleybus wires run together, the sign on the right of the
tram wire applies, possibly with a "TRAM"/"TBUS" plate. Any sign may sit on a **yellow reflective
backing board** that frames it, with any extra text below the sign on the board (§ 49.32).

Photos and drawings on prazsketramvaje.cz are under `https://www.prazsketramvaje.cz/obrazky/navesti/`
(written below as `navesti/…`); the `…m.gif`/`…m.jpg` files are thumbnails.

## Light signals for trams at road junctions (§ 42, p. 37–38)

The aspects are set by the road traffic act and its decree, not by D 1/2.

| ID | What | Look | Meaning, driver's action | Game now | Status |
|---|---|---|---|---|---|
| SIG-L1 | tram signal (*signál pro tramvaje*) | black square head with four round white lamps: three in the top row, one under the middle. Stop = the two outer top lamps (a horizontal bar); straight = top middle + bottom; left = top left + bottom; right = top right + bottom (p. 37–38 drawings) | as the road traffic decree | four white lamps, same aspects, on a white backplate with a black edge (`src/models.js:675-688`) | in game; the backplate's colour is to be checked against photos |
| SIG-L2 | call signal (*výzvové návěstidlo*) under the head | black square with three LED strips `\ | /`, each 2 LEDs wide and 7 long; the requested direction's strip lights **yellow** (p. 37, 45). The photos (Wikimedia, 2026-11-08): the vertical strip in the middle, the leaning ones the same strip turned about 24°, their bottom ends beside it without touching (the user: "just rotated, not stretched and shifted") | the controller has accepted the tram's request for that direction. **Blinking** while the head shows no GO that way: GO is coming. **Blinking while the head shows GO** that way: GO is about to end (§ 42.3–5). | amber strips as described (`src/ledPanels.js`, #376), lit when registered, blinking in the last 3 s before GO (`src/game.js:1355-1358`) | differs: no "GO ending" blink on the call signal (the game blinks the GO aspect itself for its last 3 s) |
| SIG-L3 | request | made by detectors, by the route set, by the **universal crank in a contact lock** (*kontaktní zámek*) at the signal, or a button (§ 42.2). The website: often a **trolley contact** before the signal; the new contact lock is a **yellow plastic box 10×21 cm** on the signal pole with a red LED arrow window (steady = accepted, flashing = GO follows); if the call signal does not light after the contact, request again by hand ([web-notes.md](web-notes.md) 1.2–1.3) | | the request is automatic | partly |
| SIG-L5 | *Pozor* (caution) for trams | set by the road traffic decree (Vyhláška 294/2015 Sb.), not read here; D 1/2 § 43.8 gives its meaning for sleeper signals: stop unless too close to stop safely | | the game has no *Pozor* aspect (`src/models.js:683-688`); the GO aspect blinks instead | missing: read the decree |
| SIG-L4 | signal that will not give GO | after a manual request: report to the dispatcher; pass only on police (or, off the road, dispatcher's) instruction (§ 42.6). Before an unclear or unreadable signal: stop and report (§ 42.7). | | – | missing (fault event) |

## Sleeper light signals (*pražcové světelné signály*, § 43, p. 38–42)

Used on tram track off the road, or where the signal is not part of the road junction's lights.
Each branch of a fork has its own signal. Head: **two round black lamps one above the other**
(p. 38–42 drawings); the request mark is a small cluster of white dots at the foot of the lower lamp.

| ID | Aspect | Upper lamp | Lower lamp | Meaning |
|---|---|---|---|---|
| SIG-P1 | *Stůj* (stop) | white horizontal bar | dark | stop before the stop line (or before the signal) |
| SIG-P2 | *Stůj + výzva* | horizontal bar | dark + request mark | stop; the request is registered |
| SIG-P3 | *Příprava k odjezdu* (get ready) | horizontal bar | full white disc of dots | a standing train may get ready; a moving one adjusts speed so as not to pass the line before GO |
| SIG-P4 | *Příprava + výzva* | horizontal bar | disc + request mark | as P3, request registered |
| SIG-P5 | *Volno* (go) | white bar: vertical (straight), leaning left `\` or right `/` | dark | go, only in that direction |
| SIG-P6 | *Volno + výzva* | as P5 | request mark | as P5 |
| SIG-P7 | *Pozor* (caution) | dark | white disc (steady) | stop before the line, unless already too close to stop safely. Without a *Pozor* aspect, the change to *Stůj* is read the same way. |
| SIG-P8 | *Pozor + výzva* | dark | disc + request mark | as P7 |
| SIG-P9 | *Signalizace mimo provoz* (out of service) | dark | disc **blinking** | not a signalled place |

Off the road these signals override traffic signs and the general priority rules (§ 43.13).
Game now: the single-track sections and crossings use the road-junction signal (SIG-L1).
**Status: missing** (the sleeper signal's look and its *Příprava* and *Pozor* aspects). Speed switches
use a simpler entry sleeper signal ([switches.md](switches.md)).

## Distant signals (§ 44, p. 43)

| ID | Look | Meaning | Game now | Status |
|---|---|---|---|---|
| SIG-D1 | *Očekávej stůj*: a small black head with the tram lamps (three on top, one below) showing the two outer top lamps, on a white plate with a **yellow "P"** panel below | expect STOP at the next signal | yellow "P" plate repeating the main signal; placed 120 m before signals with a tight curve before them (`src/game.js:683-699`) | in game (placement is a heuristic) |
| SIG-D2 | *Očekávej volno*: the same head showing top middle + bottom | expect GO at the next signal | the same | in game |

## Speed signs (§ 49.13–22, p. 53–56; website [2006041265](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041265))

All are upright rectangular plates with a white frame and a thin black edge unless said otherwise.

**Size (read 2026-11-06, #211).** Neither D 1/2 nor the speed-sign page gives one. The website's overview
([2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260)) gives the signs of the same family:
yellow panel in a white frame, **200×300 mm with a 30 mm frame** (U and Z, also the red, green and split plates), and an
arrow of 150×25 mm. D 1/2's drawings of the speed signs have the same shape: plate 2:3, frame 14–15 % of the width,
panel 0.58–0.59 wide to high (p. 53–55, measured on the rendered pages). So the speed signs are taken as **200×300 mm,
panel 140×240 mm**: an estimate from the family, not a stated size. The warning triangle (drawn 220 wide by 165 high,
p. 54) and the zone plate (111 by 171, panel 74 by 109, p. 56) have no size in any source read.

**Numbers.** A heavy condensed black figure filling the panel's width in D 1/2's drawings ("30", "20"), a plain bold
one on the zone plate ("40"). The photos show otherwise: a heavy condensed DIN (DIN 1451 Engschrift), each figure
0.37–0.48 as wide as high, strokes 0.145 of the height, the pair about half the panel's height and three quarters of its
width (the website's 10 and 30, the user's 60 of 2026-11-08; the 80 gradient board's strokes are 0.17). The photos also show an orange-yellow reflective panel, white frame with
a grey edge; a sign over a fork has its arrow on a white strip under the panel, inside the plate's outline.

**How they stand (photos on the speed-sign page).** Plates and triangles hang from the span wire by a clamp over the
track, or stand on a traction pole. D 1/2 gives no height or side: "the sign on the right of the tram wire applies"
only where tram and trolleybus wires run together (§ 41).

| ID | Sign | Look | Meaning | Drawing, photo | Game now | Status |
|---|---|---|---|---|---|---|
| SIG-V1 | *Omezení rychlosti* (restriction) | **yellow** panel with a **black number** (km/h) | at most that speed from the sign on (front at the sign); ends with SIG-V3, another restriction or a Rychlostník | p. 53; `navesti/navest-rychlost_30-001.gif`, photo `navest-rychlost_10-002.jpg` (2006, with an arrow over a fork) | **black number on white** with a black border (`src/models.js:848-859`), placed from the limit profile, not from data | differs (colours; places) |
| SIG-V2 | *Pomalu* (slow) | the same yellow panel **without a number** | **10 km/h** with extra care | p. 53; `navest-rychlost_pomalu-001.gif`, photo `-002.jpg` | – | missing |
| SIG-V3 | *Ukončení omezené rychlosti* (end) | yellow panel with a **black diagonal** from bottom left to top right | speed up only when the **whole train** has passed | p. 53; `navest-rychlost_konec-001.gif`, photo `-002.jpg` (2016) | – | missing |
| SIG-V4 | *Předzvěstní štít* (warning board) | **yellow triangle, point down**, white edge, black digit = the coming limit in **tens of km/h** (3 = 30); no digit = *Pomalu* follows | stands at **braking distance** before a restriction, *Pomalu* or point restriction when the speed drops by **30 km/h or more**; also where the view is poor for smaller drops | p. 54; `navest-rychlost_stit_30-001.gif`, photo `navest-rychlost_stit_20-001.jpg` (2016) | – | missing |
| SIG-V5 | *Místo s omezenou rychlostí* (point restriction) | yellow panel with black number, a **black triangle pointing down** under it | the **front** passes the point at that speed; speed up once the front has passed | p. 54; `navest-rychlost_misto_30-001.gif`, photo `-002.jpg` (2016) | – | missing |
| SIG-V6 | *Rychlostník* | **black** panel with a **white number** | from here a speed **above** the general one is allowed (rear past the sign first); ends with SIG-V7, another Rychlostník or restrictions. A Rychlostník for one car type applies to that type; one without a type to the rest (§ 49.17; how a type is written on the sign: no drawing, [places.md](places.md)). Inside a time-limited zone (SIG-V10) the lower of the two applies in the zone's hours. | p. 54; `navest-rychlostnik_30-001.gif`; the user's photo of a **60** (2026-11-08): white DIN figures on black, a white frame, hung by a clamp from the span wire over the track | the game's only speed board is called "rychlostník" but drawn as a restriction | differs |
| SIG-V7 | *Konec rychlostníku* | black panel with a **white diagonal** | end of the higher speed (front at the sign) | p. 55; `navest-rychlostnik_konec-001.gif` | – | missing |
| SIG-V8 | *Oblouk o malém poloměru* (small radius) | yellow panel with a black lower-case **"r"** and an arrow under it; the arrow picks the curve at a fork | curve of **R < 25 m: 15 km/h** over the whole curve | p. 55; `navest-oblouk_r-001.gif`, photo `-002.jpg` (Moráň, 2004) | – | missing ([places.md](places.md) lists the curves) |
| SIG-V9 | *Rychlost přes výhybku* (switch speed) | yellow panel with a large black **"V"** | outside depots: **10 km/h** facing this switch into its **diverging** branch | p. 55; `navest-rychlost_pres_vyhybku-001.gif`, photo `-002.jpg` | – | missing |
| SIG-V10 | *Zóna s omezením rychlosti* (zone) | taller plate: "ZÓNA" and the hours (e.g. "22 - 6 h") on white at the top, black number on a **yellow** panel below | at most that speed in the zone (front at the sign); only in the hours shown (22 = 22:00). Lower limits inside still apply. Used at night against noise. | p. 56; `navest-zona_zacatek_40-001.gif`, photos `navest-zona_zacatek_30-002.jpg`, `navest-zona_zacatek_40-002.jpg` | – | missing (no night; [places.md](places.md)) |
| SIG-V11 | *Konec zóny* | the same plate, number not on yellow, a black diagonal from bottom left to top right | speed up when the **whole train** has passed (D 1/2 § 49.22; the website says the front, older text) | p. 56; `navest-zona_konec_40-001.gif`, photos `…_konec_30-002.jpg`, `…_konec_40-002.jpg` | – | missing |

The website's text on the speed-switch signal (same page) says that without a number a switch is
passed as an ordinary one, 15 km/h straight and 10 km/h diverging. D 1/2 (2025) gives 15 km/h for both
facing directions (§ 25.4a) and keeps 10 km/h for switches with the "V" sign; the website's text is
older.

## Gradient signs (§ 49.9–12, p. 52–53)

The user's photos of 2026-11-08, a climb of 80 ‰ and the end of a descent of 80 ‰, and D 1/2's drawings agree on the
shape: the pentagon's point takes the half of the board it points to, its shoulders 0.56 of the height from that edge
(photos 0.56 and 0.56, drawings 0.56 and 0.57), the white field about 5 % in from the board's edges. The figures differ:
D 1/2 draws a red serif; the climb board has a condensed DIN (0.23 of the board high, its middle at 0.575 of the height),
the older end board a wide rounded bold one (0.24 high, 0.45 of the board wide). The game takes the DIN, as on the speed
signs.

| ID | Sign | Look | Meaning | Game now | Status |
|---|---|---|---|---|---|
| SIG-G1 | *Nebezpečné stoupání* (dangerous climb) | grey square with a white **house-shaped pentagon pointing up**, a **red number** in ‰ | rules D12-G1 | – | missing |
| SIG-G2 | *Konec nebezpečného stoupání* | the same with a black diagonal | end | – | missing |
| SIG-G3 | *Nebezpečné klesání* (dangerous descent) | grey square, white pentagon **pointing down**, red number in ‰ | rules D12-G2 | a gradient board at grades under −5.5 % (`src/game.js:800-809`) | differs (look; where it stands comes from the profile) |
| SIG-G4 | *Konec nebezpečného klesání* | the same with a black diagonal | end | – | missing |

## Overhead wire signs (§ 49.23–27, p. 56–57)

All are a **diamond** (a square on its point): white outer edge, black frame, **green** field with white
marks.

| ID | Sign | Marks on the green field | Meaning | Game now | Status |
|---|---|---|---|---|---|
| SIG-W1 | *Úsekový dělič* (section insulator) | **three white dots in a row** (the website's drawing has four); diamond at least 300 mm | pass with **every pantograph up and no traction current** | not modelled (an idea in `docs/history/HANDOFF.md:316`) | missing: a skill of the same kind as the contacts (coast under it); needs the insulators' places. No public list found (2026-11-03): OSM does not tag them in Prague (its 57 `power=insulator` nodes are on 22 / 110 kV lines), the DTM snapshot (ZPS, DI) has no overhead-line equipment, the substations' feeding maps (2009) give sections only roughly ([web-notes.md](web-notes.md) 3.2); student slides say sections are about 300 m long. A survey from street-level imagery (the sign) is the open way. |
| SIG-W2 | *Stáhni sběrač* (lower the pantograph) | five dots in a **V** (pointing down) | obstacle on the wire: no train may enter with a raised pantograph | – | missing (event) |
| SIG-W3 | *Zvedni sběrač* (raise) | five dots in an **inverted V** | the driver may raise the pantograph and draw current | – | missing |
| SIG-W4 | *Změna sběrače* | eight dots in a **ring** | double-ended trams change pantograph here when changing cab | – | n/a (T3 is single-ended) |
| SIG-W5 | *Diodový úsekový dělič* (diode insulator; the website: *úsekový dělič s magnety*) | one **white horizontal bar** | a supply split that may be passed **drawing current**; the first one was on the climb onto **Trojský most (line 17)**, 2014 | – | missing (no action needed; a sign to draw) |
| SIG-W6 | trolley-wire crossing (*trolejové křížení*) | (no sign in D 1/2) | coast through, pantographs up (§ 33.14); 15 km/h (§ 25.4c) | – | missing |

## Other fixed signs (§ 49.1–8, 28–30, p. 49–51, 58)

| ID | Sign | Look | Meaning | Game now | Status |
|---|---|---|---|---|---|
| SIG-O1 | *Stůj* (stop) | white plate with a **red** rectangle; light version: red LED dot matrix in a white frame on black | the front stops before it | – | missing |
| SIG-O2 | *Přejezd s předností v jízdě tramvaje* | white plate with a **green** rectangle | at braking distance before a level crossing where traffic signs give the tram priority | – | missing |
| SIG-O3 | *Bezpečnostní zastavení* (safety stop) | white plate 200×300 mm with a **green border and a green diagonal** from top left to bottom right | **every train stops** before it; at the stop sign's level, stopping at the stop counts. The website: the driver **tests the parking brake** there; set before sections of 70 ‰ or more; at some the train starts by gravity only ([places.md](places.md)) | – | missing (check our lines for them) |
| SIG-O4 | *Přednost v jízdě před protijedoucí tramvají* | rectangle split vertically, **red left, green right**; a plate below may give types ("T KT") and an arrow | start of a section where opposing trams may not meet; this driver has priority unless an opposing train is already in it | the single-track sections use signals | missing (sign version) |
| SIG-O5 | *Dej přednost v jízdě protijedoucí tramvaji* | **green left, red right**, plates as above | the same section, this driver gives way and stops before the sign if an opposing train is in it or coming. Rule of thumb from the website: the colour on the driver's **right** decides (green: priority; red: give way). A classic place is **Národní divadlo** (types "T - KT") | – | missing |
| SIG-O6 | *Konec úseku přednosti / Konec úseku dej přednost* | (p. 50–51) | end of those sections | – | missing |
| SIG-O7 | type letters | "T" = every type; "KT" = KT8D5, KT8D5.RN2P, **T3R.PLF** and snow ploughs with the KT profile; a plough with that profile shows an **orange warning light** before such a section | which trams may not meet there | – | n/a (the T3 in the game is not a T3R.PLF) |
| SIG-O8 | *Zákaz vjezdu vlaků určeného typu vlevo / přímo / vpravo* | (p. 51) with a text plate of types | that type may not take that branch | – | n/a |
| SIG-O9 | *Úsek zvýšeného rizika* (higher-risk section) | **blue** plate, white field with three red "!!!", white field with the length in metres | a section with more accidents; the number is its length | – | missing |
| SIG-O10 | *Námezník* (clearance marker) | white bar painted on the track bed between the tracks of a fork (photo p. 58) | the front may come up to it, or the rear stand at it, without fouling a train on the other track; also where opposing tracks meet at an interlaced section | – | missing (a stopping mark for the player and AI trams) |
| SIG-O11 | *Zúžený průjezdný průřez* (narrow clearance) | **yellow and black diagonal stripes** on a narrow upright board | the clearance is reduced here | – | missing |

## Portable signals at work sites (§ 50, p. 59)

| ID | Signal | Look | Meaning |
|---|---|---|---|
| SIG-X1 | *Stůj* | red disc, red lamp or red flag **between the rails** | stop before it; go on only after the site's guard removes it |
| SIG-X2 | *Pomalu* | **yellow disc** beside the track | 10 km/h |
| SIG-X3 | *Omezení rychlosti* | yellow disc with a **black number** | that speed |
| SIG-X4 | *Ukončení omezené rychlosti* | yellow disc with a **black diagonal** | end of X2 and X3 |

Status: missing (work sites with a 10 km/h restriction, § 25.3e, would be an event).

## Signals given by people and sounds (§ 51, p. 59–61)

| ID | Signal | Given by | Meaning | Game now |
|---|---|---|---|---|
| SIG-H1 | *Nebezpečí – zastavte všemi prostředky* (danger, stop by all means) | circling an arm, flag, lamp or anything in front of the body; rapid short whistle or bell blasts; a **continuous electric bell** | stop at once with every brake | missing (event) |
| SIG-H2 | *Stůj* | arm raised towards the train; red flag, disc or light | stop with the front before it | missing |
| SIG-H3 | *Provozní zastavení* (service stop) | two short sounds, repeated with a pause | stop at once with the service brake | n/a |
| SIG-H4 | *Vzdálenost k zastavení* | spoken metres from the front coupler to the stop point | | n/a |
| SIG-H5 | *Pomalu* | yellow flag held down at an angle; arm swung up and down; yellow lamp | 10 km/h while it is given | missing |
| SIG-H6 | *Pozor* (warning by the driver) | **two short rings of a mechanical bell** or **one electric bell sound of up to 2 s** | warns people the train is starting or moving; required before entering a pit or depot hall | bell (B) clears obstacles within 120 m | in game (no sound length rule) |
| SIG-H7 | *Příprava k odjezdu*, *Odjezd* | arm out to the side / long whistle; arm waved bent in the direction of travel / long + short whistle | dispatching at stops, coupling, reversing | n/a |
| SIG-H8 | *Směr jízdy* | the driver's right palm on the windscreen, fingers pointing the way (up = straight) | tells others which way the tram goes | missing (a small cab gesture) |
| SIG-H9 | *Spojení / Rozpojení provedeno* | long + two short whistle | coupling done | n/a |
| SIG-H10 | *Vlak se přetrhl* (train parted) | long + short sounds repeated | stop or catch the loose cars | n/a |
| SIG-H11 | *Nevystupujte – nenastupujte* (doors closing) | **sound and light together, at least 3 s**, heard and seen inside and outside, before the doors close | | check: the game's doors close in 3 s (`src/tram.js`); whether a warning precedes them |
| SIG-H12 | passenger signals | two short buzzes: a passenger with reduced mobility or a pram gets off at the next stop; buttons: ramp request, door request | the driver must stop and open (D12-S3) | partly (random "nobody gets off") |
