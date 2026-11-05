# The rest of prazsketramvaje.cz: signals, switches, power, practice

Read 2026-11-03 (69 article pages, 44 drawings and feeding maps). Page URLs are written as `[id]` =
`https://www.prazsketramvaje.cz/view.php?cisloclanku=<id>`; image paths are relative to
`https://www.prazsketramvaje.cz/` (`...m.jpg/.gif` are thumbnails of the same name without `m`).
The speed-sign page [2006041265], the radio-switch register [2006041262] and the D 1/2 PDF are in
[signals.md](signals.md), [switches.md](switches.md) and [rules-d1-2.md](rules-d1-2.md); this note
covers the site's other articles. **Game:** lines mark what the game does now, where it matters.

Many pages are fan descriptions written 2006–2015 and say so ("text does not match the current state");
switch numbers on crossing pages are older than the register. Where both exist both are given.
Descriptions of drawings marked *(drawing)* come from looking at the GIFs, not from the page text.

---

## 1. Signals (*návěsti*) by category

Index page: [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260).

### 1.1 Tram traffic lights, "lenses" (*světelné signalizační zařízení pro tramvaje*, slang *čočky*)
Source [2006041263](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041263).
- Shape: one signal plate with **four round lamps**: three in an upper row, one below the middle one.
  *(drawing)* black plate, lit lamps drawn yellow, dark lamps white (the page does not name the light colour).
- Aspects:
  - **STŮJ** (stop): both outer upper lamps.
  - **VOLNO** (proceed) always = the lower lamp + the upper lamp(s) of the permitted direction(s):
    left = upper-left; straight = upper-middle; right = upper-right; left+straight = left+middle;
    left+right = both outer; straight+right = middle+right; all three directions = all four lamps.
  - **OČEKÁVEJ STŮJ** (expect stop) and **OČEKÁVEJ VOLNO** (expect proceed), distant signals: the
    stop or straight-proceed pattern on a plate with a **yellow portrait plate 170×270 mm, 30 mm white
    border, black letter "P"** below the lamps. Tells what the next tram signal will show.
- A "proceed" may be granted only on request (*výzva*) from the tram: trolley contact, setting an
  electric switch, or by hand with a contact lock (1.3).
- Signals may also be used on bus/trolleybus reserved lanes.
- Drawings: `obrazky/navesti/cocky-stuj.gif`, `cocky.gif`, `cocky-leve.gif`, `cocky-prave.gif`,
  `cocky-leve+prime.gif`, `cocky-prime+prave.gif`, `cocky-leve+prave.gif`, `cocky-stujpredvest.gif`,
  `cocky-volnopredvest.gif`; photo `obrazky/smes/cocky.jpg`.

### 1.2 Call-acknowledge signal (*výzvové návěstidlo*)
Source [2006041281](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041281).
- Shows whether the controller has accepted the tram's request for a proceed aspect. First at Karlovo
  náměstí, 19 Jan 1998.
- Prototype: black plastic box 27×17 cm with yellow LEDs in a "V" of three double rows halved by a
  vertical row. Current form: same LED pattern behind plexiglass in a standard tram-signal housing
  31×26 cm, signal face 23×23 cm. *(drawing, speed-switch version `vyzvove_primo.gif`)*: black square,
  a **yellow dotted stripe**: vertical = straight, slanted "/" = right.
- Aspects, per direction:
  - dark = request not accepted (except directions that the cycle always serves);
  - steady yellow stripe = **request accepted** (*výzva nárokovaná*), lit from the first request until
    the last is cancelled;
  - **flashing yellow stripe = proceed follows soon** (*následuje volno*) — not on all signals; used on
    new installations and where useful, e.g. at stops.
- At a branching, the signal shows all directions, including cyclic ones (those lit permanently except
  while "proceed follows" flashes).
- **Driver:** if the stripe does not light after passing the trolley contact, it is a fault — request
  again by hand with the contact lock.
- Photos: `obrazky/navesti/vyzvovenavestidlo-01.jpg` (Vinice, old), `-04.jpg` (Ohrada, old),
  `-02.jpg`, `-03.jpg` (Komunardů single track, new).

### 1.3 Contact lock (*kontaktní zámek*)
Source [2006041264](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041264).
- Metal box (old type) or **yellow plastic box 10×21 cm, 10 cm deep** (new) with a tube opening at the
  bottom holding a square spindle; the driver turns it with a **crank (*klička*, universal key)** to
  request a direction. New type has a window 5×2.5 cm at the top where a **red LED direction arrow**
  lights to confirm; some boxes carry a white tram pictogram on a black field.
- Arrow aspects as 1.2: dark = not accepted, steady red = accepted, flashing red = proceed follows.
- Usually mounted on the traffic-light pole, sometimes 2–3 car lanes away from the track; hence the
  large call-acknowledge signal was added.
- Photos: `obrazky/navesti/kontaktnizamek-01.jpg` (old, upper Palmovka), `kontaktnizamek-02.jpg` (new).

### 1.4 Sleeper signals (*pražcová návěstidla*, BOStrab-like)
Source [2013091503](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013091503).
- First lit 18 Jul 2009 at the Třebenická underpass (Ďáblice line); Barrandov line from Dec 2010; speed
  switch R01 Prašný most 2013. Legally usable **only off public roads**; dispatcher or inspector may order
  a run past "stop".
- *(drawing)* Each direction has its own pair of **round black lamps stacked vertically** in standard
  signal chambers on a backing plate (drawn lime/yellow-green). Lamps show white LED patterns:
  - **upper lamp**: horizontal bar = **Stůj** (stop); vertical bar = **Volno přímo**; bar slanted "\\"
    (top-left to bottom-right) = **Volno vlevo**; slanted "/" = **Volno vpravo**;
  - **lower lamp**: round dot (disc of LEDs) = with the stop bar **Příprava k odjezdu** (prepare to
    depart), alone with dark upper lamp = **Pozor** (caution); small 4-LED triangle at the lower edge =
    **výzva** (request accepted), shown together with any aspect;
  - **Signalizace mimo provoz** (out of service): lower dot flashing (2 frames, 150 ms each), upper dark;
  - distant signals **Předvěst volno / Předvěst stůj**: the bar on a single lamp with a yellow "P"
    plate below, placed at least braking distance before.
  - Three directions = at most six chambers (Germany needs up to 15).
- Meanings: Stůj = stop before the stop line (or the signal if none). Příprava = a standing driver
  may get ready; a moving one must regulate speed so as not to pass the stop line before proceed
  shows. Volno = proceed only in the shown direction. Pozor = stop, unless too close to stop safely.
  Dark/out of service = not a controlled place.
- Rules shared with lenses: request automatic (trolley contact) or by crank in a contact lock (or
  button); each direction at a branching has its own signal; the new signals rank above road signs and
  the general priority rules of D 1/2; dispatcher orders rank above them. If no proceed comes even
  after a manual request: call the dispatcher, move only on their order.
- Drawings: `obrazky/navesti/prazce_stuj.gif`, `prazce_stuj+vyzva.gif`, `prazce_priprava.gif`,
  `prazce_priprava+vyzva.gif`, `prazce_volno_vlevo.gif`, `prazce_volno_primo.gif`,
  `prazce_volno_vpravo.gif` (+`+vyzva` variants), `prazce_pozor.gif`, `prazce_pozor+vyzva.gif`,
  `prazce_mimoprovoz.gif`, `prazce_predvest_volno_vlevo|primo|vpravo.gif`, `prazce_predvest_stuj.gif`,
  `prazce_volno_primo_jen.gif`, `prazce_stuj_jen.gif`. Photos `obrazky/navesti/prazce-001.jpg`
  (proceed straight + call), `-002` (caution + call), `-003` (stop + call), `-004` (prepare + call),
  `-005`, `-006`, `-007` (Třebenická).

### 1.5 Coloured signals (*barevná návěstidla*) — Nádraží Braník, line 17, 2009–2011, removed
Source [2013091502](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013091502).
- Trial at the entry to Nádraží Braník loop from June 2009 to 30 Jun 2011 (start of the Podolské
  nábřeží rebuild); not switched on again, removed in winter 2011/12, no further use planned. Not needed
  for today's game, but photos show the loop junction: `obrazky/navesti/barevne-001.jpg` (exit of the
  loop, stop), `-002`, `-003` (from the Nádraží Braník through stop), `-004` (with the switch signal
  showing locked, route left).
- One signal per direction stacked; arrows built from coloured LED triangles, white frame; same
  aspects and rules as 1.4. Drawings `obrazky/navesti/barevne_<aspect>_<dir>.gif`.

### 1.6 Signs on the overhead (plates hung near the trolley wire)

| sign (Czech) | looks like | meaning / driver | source |
|---|---|---|---|
| Stop (*Stůj*), fixed | red portrait plate ≥200×300 mm, 30 mm white border | stop with the front before it; marks **end of the trolley wire**; a larger version covers track works and is set by workers on a closed track | [2006072301](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006072301), [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260) |
| Stop, portable | red board (as above), red lamp or red flag, placed **between the rails** | protects a work site; proceed only after the instructed worker removes it. With a supplementary plate naming a car type it bars only that type (depot tracks; T3 is not on the lists) | [2006072301](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006072301) |
| Light stop (*světelná návěst Stůj*) | **illuminated red rectangle 155×230 mm, white frame** *(drawing: on a black housing)* | as fixed stop; at a facing switch stop **before the switch**; passing only on dispatcher's or inspector's order; dark = no aspect | [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260) |
| Working trolley contact (*Pracovní trolejový kontakt*) | white square ≥300×300, black equilateral triangle (point up), orange square inside | marks the setting contact of an electric switch; see 2.2 | [2006041276](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041276) |
| Radio receiver (*Přijímač radiového signálu*) | white square 400×400, 30 mm black border, black radio pictogram | radio-controlled switch; see 2.3 | [2006041278](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041278) |
| Safety switch "Z", lockable switch "U" | yellow portrait 200×300, 30 mm white border, red letter | see 2.1 | [2006041280](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041280), [2006041279](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041279) |
| Priority over / give way to oncoming tram (*Přednost v jízdě před protijedoucí tramvají* / *Dej přednost v jízdě protijedoucí tramvaji*) | portrait 200×300 split vertically into two 100×300 halves: **priority = left red, right green; give way = left green, right red**; optional black letters at the top "T - KT", "KT", "14T X 14T" or "T-KT X 14T"; **end** = same plate with a 30 mm black diagonal from bottom-left to top-right; before a branching a **white plate with a black arrow (150×25 mm)** below tells which curve it applies to | marks where two trams (of the given types) must not meet (curves, narrow track spacing, single-track spots). Rule of thumb: the colour on the driver's **right**: green = he has priority (unless a forbidden oncoming train is already inside), red = **stop before the sign** if a forbidden oncoming train is in or approaching the section. "T - KT": T-cars (T3) must not meet KT8D5/RT6N1 (those not each other either), T-cars may meet each other; "KT": only KT8D5/RT6N1 may not meet each other (T3 unaffected); no letters: no two trams at all. Classic spot: **Národní divadlo** (track spacing cannot be widened) | [2006041267](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041267) |
| Dangerous climb / descent (*Nebezpečné stoupání / klesání*), and their ends | **grey plate ≥450×500 mm**, white field showing the slope with a **red number = gradient in ‰** *(drawing of descent: white downward-pointing pentagon, red "80")*; end = black diagonal bottom-left to top-right | enter only if no other tram is seen ahead in the section; into an occupied section only on dispatcher/inspector order. Climb: a car with an accelerator controller (*zrychlovač*, i.e. T3) must climb at the **highest attainable speed**. Descent: after every stop inside, start **only by releasing the parking brake and rolling by own weight**; on loss of traction power the train may roll on to the next stop. Sections may be protected by a signal system allowing one train per direction | [2010090101](https://www.prazsketramvaje.cz/view.php?cisloclanku=2010090101) |
| Safety stopping place (*Bezpečnostní zastavení / zastavovací místo*) | white portrait 200×300, **green 30 mm border and green 30 mm diagonal from top-left to bottom-right** | **every train stops with its front before it and tests the parking brake** (jaw or disc). Set before sections of **≥70‰** and where needed. Two kinds: start by own weight (brake release only) or start with a power notch. List in 4.6 | [2006041282](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041282) |
| Frequent-accident section (*Úsek častých nehod*) | **blue plate ≥500×300 mm** with two white panels: upper with **three red "!"**, lower with a **black number = section length in m** *(drawing shows 1000)* | informative: extra attention | [2006041266](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041266) |
| No entry for the stated train type, left / straight / right (*Zákaz vjezdu vlaků uvedeného typu*) | red square ≥300×300, 30 mm white border; a **black rectangle with white border** with a **white rectangle perpendicular to it**, placed at the left, top or right of the plate for the barred branch *(drawing, left: black vertical bar at left, white bar to the right)* | from 1 Feb 2006 barred single-ended cars from stub-ended branches after the last switch; since 1 Nov 2015 bars the train type named on a supplementary plate | [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260) |
| Text sign (*Textová návěst*) | white plate, black text | any order not expressible otherwise; Prague used one only at Letenský tunel until Aug 2007 (KT8D5 restriction on the advance branch tracks) | [2006041268](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041268) |
| Level crossing with tram priority (*Přejezd s předností v jízdě tramvaje*) | **green portrait 200×300**, 30 mm border *(drawing: white)* | warns at braking distance before a crossing where road signs give the tram priority | [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260) |
| Pantograph signs: section insulator, insulator with magnets, lower / raise pantograph | see 3.1 | | [2011111101](https://www.prazsketramvaje.cz/view.php?cisloclanku=2011111101) |
| Speed signs (*Rychlostník, Konec rychlostníku, Předvěstní štít, Omezení rychlosti, Místo s omezenou rychlostí, Rychlost přes výhybku, Maximální rychlost přes výhybku, Oblouk o malém poloměru, Zóna s omezením rychlosti*) | — | in [signals.md](signals.md) | [2006041265](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041265) |
| Disused: rail S49 sign (green square ≥500×500 with white rail profile, until 15 Oct 2013); free/occupied section light (yellow 100 mm disc on black, white frame; steady = free, flashing = occupied; Barrandov, until 1 Dec 2010) | | not for the game | [2006041260](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041260) |

Placement facts that the pages give: Z and U plates on the cross span wire above the switch, facing the
direction of travel; radio sign on the span wire at or just before the receiver; switch light signal
right of the switch; contact sign at the contact on the trolley wire; distant tram signals and the
level-crossing sign at braking distance. No mounting heights are given.

### 1.7 Driver's hand signal for direction (*návěst o dalším směru jízdy*)
Source [2006041485](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041485).
When a switchman (or other instructed worker) sets the route and the train's marking does not show which
branch it takes, or the train runs off its regular route, the driver puts the **right palm on the
windscreen, closed fingers pointing the way: up = straight, right = right, left = left**. Not needed when
the route was changed during the day by service order. (Switchman posts were gone by Feb 1998; one came
back at Vltavská for switch 132 after the 2002 floods, until 18 Nov 2002.)

---

## 2. Switches (*výhybky*)

### 2.1 Construction and hand-thrown types
- **Pivot-tongue switch, system SPS (*čepová výměna*, 1927)**: tongue turns on a visible pin at its
  heel; held in end positions by a flat spring with a tooth — a **spring switch that is not locked**
  (a wheel can push it over; the drive "smacks" the tongues). Laid as facing switches until 1990, trailing
  until 1992; now only as replacements. Electrically driven ones are numbered 001–110, 112–199.
  [2006041496](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041496)
- **Flexible-tongue switch (*pružné jazyky*)**: only type in reconstructions since 1993; replaceable
  bolted tongues since 1995/96; lockable with drives EMP2 (1984) or EMP40 (1993), controls R92, R95, R96,
  TMPK, TMPM, TMPKM (Elektroline). Electromagnetic drives run on **600 V DC traction power**. Drive box
  34–38 cm high; special low boxes 20 cm (switch 111) and ~18 cm (Čechův most, rail height).
  [2006041496](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041496),
  [2006041276](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041276),
  [2006041386](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041386)
- **Single-tongue switch (*jednojazyková*)**: one moving tongue on the outside of the diverging curve
  (straight + right: tongue in the left rail); thrown with the point key (*stavěcí klíč*) whose hole is
  beside the tongue. Trial Pankrác depot 2002.
  [2006041497](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041497)
- **Three-way switches (*trojcestné*)**: symmetric four-tongue pivot switches, ~20 m branch radius, 25 in
  all, gone by 1980 (Národní divadlo had one 1910–1968). Replaced by two switches in close succession when
  T-cars came. [2011021601](https://www.prazsketramvaje.cz/view.php?cisloclanku=2011021601)
- **Safety switch "Z" (*zajišťovací výhybka*)**: switch secured or wedged; extra care when moving the
  train over it. Plate see 1.6; hung on the span wire above it per direction. All listed ones are in
  Zvonařka loop and depots Hloubětín, Pankrác, Strašnice, Žižkov — none on our lines.
  [2006041280](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041280)
- **Lockable switch "U" (*uzamykatelná výhybka*)**, without electric drive and without number; since
  1 Feb 2006. List: Kobylisy depot yard (2), Plzeňská × Radlická from Radlická, Starý Hloubětín loop inner
  track, Lihovar from Smíchovské nádraží and from Hlubočepy, Vysočanská into the loop from Kolbenova,
  Levského loop stub track (line 17 terminus).
  [2006041279](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041279)
- **Lockable switches with an auxiliary light signal (*uzamykatelné s pomocným světelným
  návěstidlem*)**, numbers **U02–U18**, hand-thrown, flexible tongues; their number plate is **white on
  black** (electric and radio switches: black on white). Register (complete): U02 Myslíkova from Karlovo
  nám.; U03 Motol depot exit; U04 Pankrác depot to stub; U05 Plzeňská × Radlická from Bertramka; U06
  Sídliště Řepy loop to stub; **U07 Podolská vodárna from Kublov** (line 17); U08 Zámecká from Nádraží
  Vršovice; **U09 Ke Stírce from Bulovka**; U10 Čechovo nám. from Koh-i-noor; U12 Octárna from Hládkov;
  U13 Čechovo nám. from Vršovické nám.; **U14 U Balabenky from Palmovka (upper)**; U16 Vokovice depot;
  **U17 Ke Stírce from Trojská** (line 17); U18 Octárna from Petřiny.
  [2010083001](https://www.prazsketramvaje.cz/view.php?cisloclanku=2010083001)
- **Trailing over a wrongly set switch is forbidden** where the wheels could throw its tongues (the
  page cites the older D 1/2; today § 29.7); U16 had a temporary exception until 16 Oct 2015.
  [2010083001](https://www.prazsketramvaje.cz/view.php?cisloclanku=2010083001)
- **Manual locking test (*ruční zkouška uzamčení*)**: tongues count as locked if the point key cannot
  push the tongue off the stock rail at the point nearest its tip — **3.6 m from the tip, at the 8th
  sleeper** (first place the key fits). Required when the switch signal shows "route uncertain" or is
  dark (stated for the speed switch; the general rule is in D 1/2).
  [2013041401](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013041401)

### 2.2 Electrically controlled switches with trolley contacts (*elektricky ovládané výhybky*)
Source [2006041276](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041276),
[2017080101](https://www.prazsketramvaje.cz/view.php?cisloclanku=2017080101).
- Equipment: working-trolley-contact sign, light signal, number plate, direction plate where two switches
  follow each other.
- **Contact sign with two switches in a row**: a black plate ≥170×270 mm with a white **L** or **P**
  (≥120 mm high, 30 mm stroke) under the contact sign: **P** = this contact sets the switch for the right
  and middle branches, **L** = middle and left (photo `obrazky/navesti/navestidlo-stavecikontaktdve.jpg`).
- **Contact out of use**: covered by a **black plate ≥350×310 mm with a yellow cross** (photo
  `obrazky/navesti/navestidlo-stavecikontaktodpojen.jpg`).
- **Light signal**: usually on a pole, bracket or span wire **right of the switch**, visible from the
  setting contact and from where the driver would throw it by hand; sometimes doubled (second box same
  size or much smaller). Number plate **under the main box only**: black digits ≥120 mm on white (since
  1996). Three-way splits: L/P plate under each signal; **lower signal = first switch** in the direction
  of travel, upper = second; plates "1"/"2" where two switches branch into equal directions. **Electric
  control out of use: signal covered by a white cross** (`obrazky/navesti/navestidlovyhybky-diodovex.jpg`).
- **Pantograph and blocking**: a switch stays blocked until the pantograph passes the release contact;
  in a 2×T3 set the **pantograph is on the second car**, so the blocking releases only after the whole
  set has passed (why the 35 m advance gauntlet at Ke Stírce barely helps).
  [2006041394](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041394)
  **Game:** only the first car's pantograph, 4.5 m behind the front, works the contacts
  (`src/tram.js:34`); which car's pantograph is up in a 2×T3 is a question for the user.
- **Oerlikon toggle drive (old pivot switches)**: any pulse from the contact throws the switch to the
  other position, whatever it is in; hand-throwing also re-arms it. Last one burnt out 17 Sep 2012
  (Kubánské náměstí).

**Switch signal (*výhybkové návěstidlo*) variants** — four in use when written:
1. **Triangular box** (pivot switches 001–199): two arrows (left, right) and a square **blocking light
   on top**; 4 lamps. Shows only "tongues left/right": a straight+right switch set straight shows the
   left arrow; often both arrows light. Photos `obrazky/navesti/navestidlovyhybky-trojuhelnik.jpg`,
   `obrazky/smes/vyhybky/oerlikon-016.jpg` (007 with direction plate), `oerlikon-017.jpg` (104 left),
   `oerlikon-019.jpg` (048 out of use).
2. **Square box** (from 1993, pivot switches 001–199): a square **standing on its corner**, its four
   sides lit segments for left / straight / right; a **lit square point in the centre = blocked**; 16
   lamps (later 14). Photos `navestidlovyhybky-ctverec.jpg`, `oerlikon-020.jpg` (045 straight),
   `oerlikon-021.jpg` (034 right).
3. **LED box (*diodové*)** for lockable switches 200–999: **red LED arrows** left / straight / right
   showing tongue position reliably; **flashing = switch blocked**; **lit centre point = switch not
   locked**. Large main and small supplementary size; newest with a plexiglass dust cover. Photo
   `obrazky/navesti/navestidlovyhybky-diodovec.jpg` (516, Vítězné náměstí).
4. **Hybrid**, switch 111 only (Čechův most): LED box with the square-type segment layout and **yellow**
   LEDs; flexible tongues but **not lockable**. Photo `navestidlovyhybky-diodovez.jpg`.
- Historic: Palmovka 022L/022P had an extra single lamp labelled "Blok"; Želivského had three round lamps
  in a column (Hanning & Kahl).

### 2.3 Radio-controlled switches (*radiově ovládané*)
Source [2006041278](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041278).
- Receiver in the ground **right of the track, ~25–35 m before the switch**; sign on the span wire at or
  just before it. Transmitter on the tram at the front steps.
- Driver: three-position selector **left / straight / right** on the panel, set any time before, **at
  least 40 m before the switch**. T3R.P with the Apex announcer: route follows the entered line number;
  manual override via the terminal. The switch is thrown **and blocked** when the car front passes the
  receiver — before the trolley contacts; if already right, it is only blocked. Two switches close behind
  each other are thrown together. Once blocked by radio the trolley contact cannot throw it.
- Trolley contacts kept as fallback (removed experimentally at 370 Červený Vrch, 8 Nov 2006); the
  register shows them removed at most radio switches in April–August 2007 ([switches.md](switches.md)
  SW-C2).
- **Game:** every facing switch is worked by an overhead contact ~22 m before it; the radio path
  (`game.irc()`, direction buttons within 80 m) exists with no key bound and no switch marked radio.
- First signed place: **Národní divadlo** (20 Jul 2001); all back in service 1 Apr 2006 after the 2004
  shutdown (transmitters threw switches on the opposite track).

### 2.4 Speed switch (*rychlostní výhybka*) R01, Prašný most (not on our lines)
Source [2013041401](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013041401).
- Sequence: number sign **"R 01"** *(drawing: black plate, white text)* ~**190 m** before (radio
  receiver, start of the circuit; may be passed with another train inside) → ~30 m later the
  call-acknowledge signal (direction lit ~5 s after registration) → **~27 m before** the switch a sleeper
  signal guarding the track circuits (proceed shown as "straight", also for right) → switch signal at
  the end of the circuit.
- Switch signal *(drawing)*: two stacked black squares with white frames: upper a white chevron (^ =
  straight, > = right) or a dot; lower a white 7-segment number. **Full symbol = route set and locked;
  flashing = blocked; number = permitted speed** (up to 50 km/h; photo 30). **No number = normal switch
  speed, 15 km/h straight, 10 km/h diverging.** Dot = route uncertain, assume unlocked → locking test.
  Dark when not blocked. Goes dark when the train leaves; sleeper signal ~4 s later.
- Faults: wrong direction on call signal → drive up to the switch per the sleeper signal and throw it by
  hand; no call light → proceed with extra care; sleeper dark → proceed only if no train in the circuits;
  sleeper stuck at stop after the previous train left → call dispatcher, move only on order.
- Out of use: cross over the number sign = no radio control; crosses over call and switch signals = run
  as over an ordinary lockable switch, locking test after throwing.

### 2.5 Default speeds over switches and temporary crossovers
- Ordinary switch: **15 km/h straight, 10 km/h diverging** (the page's text, 2013; D 1/2 of 2025 gives
  15 km/h both ways facing and keeps 10 km/h for switches with the "V" sign, [switches.md](switches.md)
  SW-D10). [2013041401](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013041401)
- Surface crossover **Californien** (bolted on top of street track for possessions): 75 mm high, branch
  radius 25 m without transition, for 3 m track spacing (to 4.5 m with spacers), ~30 m long, **10 km/h**.
  [2006041299](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041299)

### 2.6 Switches on line 17's route
Crossing/loop pages (dated, mostly 2006–2011) give the older number; "register" = the radio-switch
register [2006041262] (newer). "used" = movements in regular service per
the page.

| place | switches (page) | register | notes | source |
|---|---|---|---|---|
| Levského loop (Modřany terminus) | 227L into the outer loop track, 227P splitting outer/inner; crossover 228 from the line track (electric only in trial, then wedged, now hand-thrown); trailing switches flexible | 599P/599L Sídliště Modřany into loop; 773 Levského to Libuš | only a boarding stop in the loop; alighting at Sídliště Modřany; the former city-bound running track serves as inner loop track; a "U" switch on the stub track | [2006041531](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041531), [2006041279](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041279) |
| Nádraží Braník junction & loop | 209 (flexible) into loop; loop: hand-thrown pivot switches, last diamond crossover outside depots, all 4 trailing switches pivot | — | loop capacity 84 T-cars; **driver relief point of line 17** (4.2) | [2006041532](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041532) |
| Dvorce loop | **691 from Podolí/Kublov, 692 from Braník**, radio, flexible; 691 can also be set from the loop exit curve toward Braník; loop switches pivot | 691, 692 | exit toward the centre closed since 8 Aug 2019 (pit); occasional boarding stop ~30 m before the exit; capacity 8 T | [2006041521](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041521) |
| Podolská vodárna loop | entries from both directions hand-thrown flexible (2006 text); exit via one hand-thrown pivot switch (to centre or Modřany); trailing switches flexible except the merge of the two entry curves (pivot) | **690 from Výtoň (radio); U07 from Kublov (hand-thrown, lockable, auxiliary signal)** | single-track block loop: in via Podolská street, out via Vodárenská; capacity 16 T; manipulation only. City-bound track, going north: diamond crossing with the loop exit track → trailing switch from the loop → facing switch into the loop (from Braník) | [2006041538](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041538), [2015071901](https://www.prazsketramvaje.cz/view.php?cisloclanku=2015071901), [2010083001](https://www.prazsketramvaje.cz/view.php?cisloclanku=2010083001) |
| Výtoň | **614 from Palackého nám., 615 from Albertov, 616 from Podolská vodárna**, radio, flexible; 3 trailing flexible; wooden sleepers, asphalt | 614–616 (contacts removed June 2007) | used: straight Výtoň–Podolská vodárna; left curves Palackého nám.→Albertov; right curves Podolská vodárna–Albertov daily for Pankrác depot runs | [2006041441](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041441) |
| Palackého náměstí | radio, flexible: 646L/P from Moráň, **647L/P from Výtoň**, 648P/L from Anděl, **649L/P from Mánes** | 647L/P, 649L/P | 5 directions used; Moráň–Jiráskovo nám. curve manipulation only; 10 km/h over the S-curve after 1985 (historic) | [2006041415](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041415) |
| Mánes | pivot switches; 026 from Jiráskovo nám. | 666 | straight Národní divadlo–Jiráskovo nám. both ways | [2006041404](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041404) |
| Národní divadlo | after 2001 only electric flexible: **523P/523L from Národní třída, 524 from Staroměstská, 525 from Jiráskovo nám.** | 685P/L from Národní třída, 771 from Staroměstská, 788 from Mánes | first radio-switch place with signs (2001); used: straight Újezd–ND, straight Staroměstská–Jiráskovo nám., right curves ND→Smetanovo nábř.; granite setts; tight track spacing (meeting bans, 1.6) | [2006041410](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041410) |
| Staroměstská | 245 from Mánesův most, 246 from Právnická fakulta (electric), **689 from Národní divadlo (radio)** | 512 from Právnická fakulta; 689 | partly fixed to the steel roof slab of an underground garage | [2006041423](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041423) |
| Čechův most | radio: **111 from Právnická fakulta** (hybrid yellow signal, not lockable), **526 from Letenský tunel**, 527 from Malostranská | 566 from Právnická fakulta, 733 from Letenský tunel | gauntlet (*splítka*) on the bridge; ~18 cm drive boxes; curve radius may not go below 20 m | [2006041386](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041386) |
| Letenský tunel | 302 from Strossmayerovo nám., **373 from Čechův most (radio)**; hand-thrown pivot from Štefánikův most | 645 from Čechův most | advance branching, ~90 m on BKV panels; page itself says it is out of date | [2006041402](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041402) |
| Strossmayerovo náměstí | 8 radio, flexible: 529L/P from Letná, 530P/L from Vltavská, 531P/L from Výstaviště, 532P/L from nábř. kpt. Jaroše | 530–532 (contacts removed 9 Apr 2007) | all six directions; five used | [2006041426](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041426) |
| Výstaviště Holešovice | 018 pivot toward the loop (electric control long out of use); 314 from Výstaviště, 420 from Veletržní | 783–787 (loop and junction) | short line 17 turned here | [2006041440](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041440) |
| Elektrárna Holešovice | — | 709 from Dělnická, 710 from Trojská, 711 from Výstaviště Holešovice | not read | — |
| Ke Stírce | only 290 electric, from Ke Stírce stop, ~35 m ahead of the crossing (first advance gauntlet in Prague, 1993); all flexible exchangeable tongues | 656 from Kobylisy; **U09 from Bulovka, U17 from Trojská** | used: Ke Stírce–Hercovka, Ke Stírce–Okrouhlická | [2006041394](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041394) |
| Kobylisy | — | 658 from Zenklova, 659 from Vozovna Kobylisy, 660 from Ďáblice | not read | — |
| Vozovna Kobylisy junction & loop | 322 electric flexible; trailing pivot; in the loop a hand-thrown pivot switch after the alighting stop, pivot trailing switch | 663 into loop, 664 in loop | loop joined only from the centre direction; capacity 20 T; **safety stopping place at both boarding stops** (start with power) | [2006041439](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041439), [2006041554](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041554) |

### 2.7 Places on the site's lists possibly on lines 9, 22, 23, 37
The site's line articles ([2019100701], [2011060202], [2012122501]) are history; they do not give today's
routes, so the line membership below is not from the site — check it against the game's routes.
- Hand-thrown lockable with auxiliary signal: U03 Motol depot exit, U05 Plzeňská × Radlická from Bertramka,
  U12 / U18 Octárna (from Hládkov / from Petřiny), U10 / U13 Čechovo nám., U08 Zámecká, U14 U Balabenky
  from Palmovka (line 37's Balabenka area). [2010083001]
- Electric with trolley contact: 305 Malovanka from Hládkov, 316 Vysočanská from Balabenka.
  [2006041261](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041261)
- Safety stopping places: Blatiny toward Vozovna Motol, Malovanka toward Hládkov/Pohořelec, Pohořelec
  toward Hládkov/Malovanka, Jana Masaryka toward Krymská (all start with power). [2006041282]

---

## 3. Power supply

### 3.1 Pantograph signs (*návěsti pro sběrač*)
Source [2011111101](https://www.prazsketramvaje.cz/view.php?cisloclanku=2011111101).
- Shape: square ≥300×300 mm **set on its point (diamond)**, its diagonal parallel to the line joining the
  rails (i.e. across the track); **green field with black and white border** *(drawing: thin black
  outline on white, thick black frame, green field)*; white circles inside. Optionally mounted on a
  **reflective yellow backing board** forming a yellow border, supplementary text or symbol below on the
  board.
  - **Section insulator (*Úsekový dělič*)**: white circles in a straight row along the horizontal
    diagonal *(drawing: 4)*. **Pass with all pantographs up, drawing no traction current and with
    regenerative braking switched off** (if the car has that switch) — i.e. coast through.
    Most used of the four.
  - **Section insulator with magnets (*Úsekový dělič s magnety*)**: the circles joined into one white bar.
    A supply division that **may be passed drawing current**. First used on the climb onto
    **Trojský most** (line 17), photo 29 Sep 2014.
  - **Lower pantograph (*Stáhni sběrač*)**: circles in a **V** *(drawing: 5)*. Obstacle on the overhead;
    no train may enter with a raised pantograph.
  - **Raise pantograph (*Zvedni sběrač*)**: circles in an inverted V. Pantograph may be raised and
    current drawn.
- Drawings `obrazky/navesti/navest_usekovyizolator-001.gif`, `-003.gif`, `navest_stahnisberac-001.gif`,
  `navest_zvednisberac-001.gif`; photos `navest_usekovyizolator-002.jpg` (Na Zámecké), `-004.jpg` (Trojský
  most), `navest_stahnisberac-002.jpg` (with Stop at a wire end), `navest_zvednisberac-002.jpg`.

### 3.2 Substations (*měnírny*) feeding line 17
Index [2007082501](https://www.prazsketramvaje.cz/view.php?cisloclanku=2007082501); each page has only
the opening year and a feeding map `obrazky/menirny/<name>-napajeni.gif` (800×600, red = sections fed).
Overall plan `obrazky/menirny/praha-napajeni_2009.gif` (2009). Reading of the maps, south to north:

| substation | opened | sections fed on line 17's route (map reading) | page |
|---|---|---|---|
| Modřany | 1995 | Sídliště Modřany loop and the line northward, ending part-way toward Braník | [2007092303](https://www.prazsketramvaje.cz/view.php?cisloclanku=2007092303) |
| Braník | 1968 | Nádraží Braník junction – Dvorce – up to just south of Podolská vodárna (substation drawn at Dvorce) | [2007082505](https://www.prazsketramvaje.cz/view.php?cisloclanku=2007082505) |
| Vyšehrad | 1977 | Podolská vodárna – Výtoň – Palackého náměstí, plus Výtoň–Albertov and Na Moráni | [2009042904](https://www.prazsketramvaje.cz/view.php?cisloclanku=2009042904) |
| Perštýn | 1965 | Jiráskovo nám. – Národní divadlo embankment, Národní, most Legií, Myslíkova, Spálená/Vodičkova | [2009041201](https://www.prazsketramvaje.cz/view.php?cisloclanku=2009041201) |
| Holešovice | 1989 | Výstaviště Holešovice junction and loop, Veletržní, Dukelských hrdinů south toward Strossmayerovo nám. | [2007090905](https://www.prazsketramvaje.cz/view.php?cisloclanku=2007090905) |
| Trojská | 1999 | Trojský most – Trojská street up to Ke Stírce | [2009041904](https://www.prazsketramvaje.cz/view.php?cisloclanku=2009041904) |
| Střelničná | 1976 | Kobylisy – Vozovna Kobylisy loop and depot, Březiněveská, Ďáblice | [2009041901](https://www.prazsketramvaje.cz/view.php?cisloclanku=2009041901) |

Podolí (1955) feeds only the Pankrác depot line, not line 17
([2009041205](https://www.prazsketramvaje.cz/view.php?cisloclanku=2009041205)). The section
Palackého nám. – Jiráskovo nám. and the Právnická fakulta – Čechův most – Letenský tunel part are not red on
any map read (likely Klárov [2007091204] or Střed [2009041902], not read). Section boundaries between two
substations are where a section insulator sign (3.1) would hang; the maps are schematic and from ~2009
(before the 2014 Trojský most).

### 3.3 Other power facts
- Switch drives use the 600 V DC traction supply. [2006041496]
- On a dangerous descent a train that loses traction power may roll on to the next stop. [2010090101]
- Trojská climb: only one train in the section, partly to limit current draw (T3 climbs at full power).
  [2006041635](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041635)
- Modřany line was the first in Prague with **catenary (*řetězovka*)** overhead. [2006041603](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041603)

---

## 4. Operating practice

### 4.1 Train marking (*označování vlaků*)
Source [2006041446](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041446).
- Front of the train: **destination** — blue letters on white (long planned diversion: black on yellow);
  LED panels: yellow on black.
- Front of every car: **line number** — white on blue; panels yellow on black.
- Side (boarding side), outside: line number and stops — blue on white (diversion black on yellow);
  inside: blue on white (magnetic foil); internal side panels green on black.
- Rear of every car: line number blue on white.
- **First car of T3 trains: line number on the right mirror arm** — white on blue. (**Game:** the
  mirror plate exists, `src/models.js:39-49`.)
- **Running into the depot**: destination = depot name or stop in **green on white**; side text covered
  by a green-on-white "to depot" notice where the route skips stops.
- Reserve trains: **"X"** instead of the number (front white on blue, rear blue on white), destination
  replaced by the line number they cover; carry a full set of number plates ("calendar").

### 4.2 Driver breaks (*bezpečnostní přestávka*, BP)
Source [2018010201](https://www.prazsketramvaje.cz/view.php?cisloclanku=2018010201).
- Law 589/2006 § 19: break after at most **4 h of driving**, at least **30 min**, splittable into parts
  of ≥10 min.
- Three ways: at the terminus (weekends, nights, and termini with one line only); relieved by a
  "**svačinář**" (relief driver who takes the tram for a stretch while the regular driver rests);
  "**oddělení od vozu**" (driver leaves the car and later takes another).
- Weekday scheme (2018): **line 17 — relief at Nádraží Braník**; line 9 — separation at Vozovna Motol
  and Vozovna Žižkov; line 22 — separation at I. P. Pavlova; line 23 — breaks at the terminus Královka.
- Example shift 9/201: report 3:53 at Motol depot, take keys from the dispatcher (*výpravčí*), check the
  train, run run 1 of line 9…

### 4.3 The job (*Povolání: řidič tramvaje*)
Source [2006042401](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006042401).
- Minimum age 21, car driving licence required since 2007; basic course 10 weeks (4 theory, 6 practice)
  at Pankrác depot; then **at least 50 h** on a regular line under a driver-instructor.
- Shifts (approx.): morning 3:30–15:00, afternoon 12:00–1:30, split 4:30–9:00 + 12:30–20:00, day
  9:00–19:00, night 20:30–5:00.

### 4.4 Single-track two-way working (*jednokolejný obousměrný provoz*)
Sources [2018051201](https://www.prazsketramvaje.cz/view.php?cisloclanku=2018051201) (Zenklova 2018),
[2014032601](https://www.prazsketramvaje.cz/view.php?cisloclanku=2014032601) (Trojská 2014, line 17's
street).
- ~600 m single-track sections with Californien crossovers; double-ended cars (KT8D5).
- **Token (*Souhlas k povolení vjezdu*, "kolík")**: a long wooden staff, red (2018) or yellow (2014),
  marked **"A"**. The first driver collects it from the depot dispatcher (entry in the driver's log),
  hands it over at stops written in the car timetable, returns it at the end. **Entry into the single
  track only with the staff or on the tram dispatcher's order.** Handed over **window to window from
  the left cab windows**; the first train to arrive stops at the stop sign, the other stops level for
  the exchange without serving passengers, then pulls up; if both arrive together, the city-bound one
  takes the stop.
- At the stub end: open right doors, switch off all consumers, fold the mirrors, change ends, check
  along the car, take control, open the doors again (now on the left); on the wrong (left) track serve
  passengers by left doors; a temporary mirror was put up where the left-door stop lay in a right curve.
- Crossovers 10 km/h (2.5).

### 4.5 Dangerous gradient: Trojská street (line 17)
Source [2006041635](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041635) (page partly out of
date), [2006041282](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041282),
[2006041394](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041394).
- **470 m at 80.15‰** between Hercovka and Nad Trojou (Trojská street, opened 5 May 1977); 43‰ before
  Nad Trojou from the river side.
- **Downhill (from Hercovka)**: stop at the light signal (safety stopping place), **test the parking
  brake, then only release the brake and roll by own weight — no motoring**; speed **20–25 km/h, no more
  and no less** (elsewhere: max 25 km/h). The 470 m are split into **two blocks covered by tram signals,
  one train per block**.
- **Uphill**: one signal; **only one train in the section**; T3 climbs at full power ("*plný kotel*").
- **Game:** 25 km/h wherever the grade is steeper than −6 % and 35 km/h below −4.5 % (`src/game.js:119-123`),
  a gradient board below −5.5 %; no stop before the section, no brake test, no one-train-per-block
  signals, no "no motoring" rule. The 25 km/h matches this local rule at Trojská, not a rule of D 1/2.
- **Track (magnetic) brake test** in the last stop before the section, both directions: voltmeter drop
  of the battery and an audible click. Each car must carry **two wheel chocks**.
- Old tram bridge (pre-2014) limited to 30 km/h.

### 4.6 Safety stopping places (*bezpečnostní zastavovací místa*)
Source [2006041282](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041282).
- Start by own weight (release only): Geologická (Hlubočepy line); Jičínská street Flora→Olšanské nám.;
  Krejcárek→Palmovka ~120 m before Sokolovská; Pod Karlovem stop; **Trojská street Hercovka→Nad Trojou
  (line 17)**.
- Start with power: Blatiny toward Vozovna Motol; Jana Masaryka toward Krymská; Malovanka toward
  Hládkov/Pohořelec; Pohořelec toward Hládkov/Malovanka; **Vozovna Kobylisy both boarding stops in the
  loop**; **Kobylisy depot exit gate** (line 17 terminus area).

### 4.7 Radio and dispatch (DORIS)
Sources [2013010202](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013010202),
[2013010201](https://www.prazsketramvaje.cz/view.php?cisloclanku=2013010201).
- Call sign of a tram run: **KGX 8LL/R** — 8 = tram, LL = line, R = run number: run 7 of line 9 is
  "KGX 809/7". Line codes: 1–29 day lines, 30–40 diversion lines, 69/73 training, 79 manipulation runs,
  90–99 night lines; dispatcher **KGX 5**.
- Driver calls the dispatch by one of **four buttons**: **yellow = train dispatcher** (vehicle faults),
  **blue = traffic dispatcher** (external: accidents, power loss, track faults), **white = operations
  dispatcher** (regularity, intervals at termini), **red = emergency**.
- On power-up the on-board unit waits for the driver to enter **line and run number** (a "logged-in"
  train, *přihlášený*); with no input for **30 s** it reports under its fixed address only ("registered",
  *registrovaný*). A logged-in train is checked against its timetabled route. Infrared beacons at control
  points (listed in the driver's car timetable) correct the stop announcer.
- Timetable deviation shown to dispatch: **on time = 0–179 s late**; early by >1 s red, by >60 s
  flashing red; 180–419 s late yellow, ≥420 s flashing yellow; white = late by the terminus layover.
  **Game:** the HUD and scoring use their own classes (5 s early grace, 60 s, 180 s); these colours
  would make a realistic on-board deviation display.

### 4.8 Other
- Platform lengths on the site are given in 2×T3 sets ("island for two 2xT").
- Before stops on Podolské nábřeží ~5 m of grooveless rail with an expansion joint is inserted in the
  grooved track on the approach side. [2015071901](https://www.prazsketramvaje.cz/view.php?cisloclanku=2015071901)

---

## 5. Line 17 (route facts the game could check)

Source [2019032701](https://www.prazsketramvaje.cz/view.php?cisloclanku=2019032701) unless noted.
- Route "now" (article ~2019): **Vozovna Kobylisy – Trojská – Výstaviště Holešovice – Strossmayerovo nám.
  – Právnická fakulta – Národní divadlo – Výtoň – Nádraží Braník – Sídliště Modřany – Levského** (long);
  short version Výstaviště Holešovice – Levského. The north end moved from Ďáblice to Vozovna Kobylisy on
  25 Jul 2012. The game's line 17 has the same stops (`data/line17.json`, 37 stops).
- Consists: from 1 Oct 2010 weekdays all runs 2×T3, KT or 14T; from 30 Jun 2013 also weekends for the
  short 17. Backbone line since 29 Nov 2009: peak 4 min, off-peak 5 min, Saturday 7.5 min, Sunday morning
  and evenings 10 min (Modřany–Výstaviště); every second run to the north end.
- Modřany line (opened 26 May 1995): gradients up to **69.9‰** below Sídliště Modřany; 40 km/h on the
  embankment curve before Nádraží Modřany; ~1 m concrete walls along the first section; stops Levského
  (boarding only), Sídliště Modřany (alighting from the centre, through stop to the centre), U Libušského
  potoka, Poliklinika Modřany, Čechova čtvrť, Nádraží Modřany, Modřanská škola, Belárie, Černý kůň,
  Nádraží Braník. [2006041603](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041603)
- Nádraží Braník – Podolská vodárna (rebuilt 2011 on S49 grooveless rails in open track; before that
  40 km/h, partly 10 km/h): stops with positions — **Pobřežní cesta** (toward Přístaviště: 4 m before the
  subway stairs; toward Braník: 72 m past them), **Přístaviště** (toward Dvorce: 70 m before the crossing
  into the middle of Modřanská; toward Pobřežní cesta: 135 m past it), **Dvorce** (toward Kublov: 75 m
  past Jeremenkova junction; toward Přístaviště: 10 m before it), **Kublov** (toward Podolská vodárna:
  454 m before Vodárenská; toward Dvorce: 449 m past it), **Podolská vodárna** toward Kublov at the level
  of Vodárenská; all platforms for two 2×T sets. The track passes under Barrandovský most in a right
  curve. [2015071901](https://www.prazsketramvaje.cz/view.php?cisloclanku=2015071901)
- Podolská vodárna – Palackého nám.: **Podolská vodárna** toward Výtoň 70 m past the Podolská street
  junction (two 2×T); **Výtoň** toward Palackého nám. 48 m past Svobodova (one 2×T), toward Podolí 10 m
  before Svobodova (two 2×T); **Palackého náměstí** toward Jiráskovo nám. 35 m before the Palackého most
  junction, toward Výtoň 40 m before Dřevná (both two 2×T). **Vyšehrad tunnel: 32 m long, curve radius
  100 m, 9 m wide.** [2011042401](https://www.prazsketramvaje.cz/view.php?cisloclanku=2011042401)
- Trojská street gradient and rules: 4.5. Stops Hercovka, Nad Trojou, Trojská, Nádraží Holešovice (old
  alignment). [2006041635]
- Switch numbers, used curves and loops: 2.6. Substations: 3.2. Relief point Nádraží Braník: 4.2.

---

## 6. Figures for later study

Signal drawings (all `obrazky/navesti/`): 
- `cocky*.gif` — tram lights, every aspect incl. expect-stop/expect-proceed with "P" plate.
- `prazce_*.gif` — sleeper-signal aspects (2×1 lamp chamber, white LED bars/dot/triangle).
- `vyzvove_primo.gif`, `vyzvove_vpravo.gif` — call-acknowledge signal (yellow dotted stripe).
- `rychlostni_001.gif`, `rychlostni_primo.gif`, `rychlostni_odbocka.gif`, `rychlostni_bod.gif`,
  `rychlostni_tma.gif`, `rychlostni_mimoprovoz.gif` — speed switch signals (animated, 6 frames).
- `navest-pracovnikontakt.gif` — working trolley contact sign.
- `navest-radiovysignal.gif` — radio receiver sign.
- `navest-z.gif`, `navest-u.gif` — Z / U plates.
- `navest-potkavacic-z.gif`, `navest-potkavaciz-c.gif`, `…-konec.gif`, `…-tkt.gif`, `…-kt.gif`,
  `navest-potkavaciz-14t.gif`, `navest-sipka.gif` — meeting-ban plates and arrow.
- `navest_stoupani-001.gif/-002.gif`, `navest_klesani-001.gif/-002.gif` — dangerous gradient plates.
- `navest-bz.gif` — safety stopping place.
- `navest-nehody.gif` — accident section.
- `navest-zakaz-vlevo|primo|vpravo.gif` — no entry for train type.
- `navest-stuj.gif`, `navest-stujsvetelna.gif`, `navest-stujprenosna.jpg`, `navest-stujdoplnkova-001.jpg`
  — stop signs (fixed, light, portable, with type plate).
- `navest-prejezd.gif` — crossing with tram priority.
- `navest_usekovyizolator-001.gif`, `-003.gif`, `navest_stahnisberac-001.gif`,
  `navest_zvednisberac-001.gif` — pantograph signs.
- `navest-textova-01.jpg`, `-02.jpg` — text sign at Letenský tunel.

Switch signal photos: `obrazky/navesti/navestidlovyhybky-trojuhelnik.jpg` (triangular),
`-ctverec.jpg` (square), `-diodovec.jpg` (LED, 516), `-diodovez.jpg` (hybrid 111), `-diodovecislo.jpg`
(number plate), `-diodovedve.jpg` (two signals with L/P), `-diodovex.jpg` (white cross = out of use),
`-blok.jpg`, `-ctverecdvojity.jpg` (Palmovka), `navestidlo-stavecikontaktdve.jpg` (contact sign with L/P),
`navestidlo-stavecikontaktodpojen.jpg` (yellow-cross cover); `obrazky/smes/vyhybky/oerlikon-016…021.jpg`
(boxes with numbers and states), `oerlikon-022…024.jpg` (opened point box with the flat locking spring),
`oerlikon-009…013.jpg` (old drive boxes beside the right rail).

Track and places: `obrazky/prasnymost/k-prasnymost-rychlostnivyhybka-034.jpg`, `-035.jpg` (whole speed
switch layout with signals); `obrazky/navesti/barevne-001…004.jpg` (Nádraží Braník junction 2011);
`obrazky/podolskenabrezi/t-podolskenabrezi-zastavka_podolskavodarna-001.jpg`, `-002.jpg`,
`…zastavka_kublov-001/002.jpg`, `…zastavka_dvorce-001/002.jpg` (line 17 stops); `obrazky/nadrazibranik/
s-nadrazibranik-trat-01…20.jpg` and `-51.jpg` (loop walk-through); `obrazky/narodnidivadlo/
k-narodnidivadlo-trat-01…03.jpg`; `obrazky/letenskytunel/k-letenskytunel-trat-01…08.jpg`;
`obrazky/smes/kolik-001…004.jpg` (single-track staff); `obrazky/smes/linka_30_zenklova_mapa-001.jpg`,
`linka_37_trojska_mapa-001.jpg` (single-track sections on aerial photos); `obrazky/vozyosobni/
6915-004.jpg` (2×T3 on line 17 under Vyšehrad rock), `9201-026.jpg` (leaving Podolská vodárna stop),
`8645-016.jpg` (climbing Trojská to Hercovka), `9131-003.jpg`, `9147-008.jpg` (single track at Trojský
most 2013).

Power: `obrazky/menirny/praha-napajeni_2009.gif` (whole-network feeding plan 2009) and
`obrazky/menirny/{modrany,branik,vysehrad,perstyn,holesovice,trojska,strelnicna,podoli}-napajeni.gif`.

Plans (PDF, not fetched): `obrazky/letenskytunel/k-letenskytunel-plan-01.pdf`,
`obrazky/kestirce/k-kestirce-plan-01.pdf`, `obrazky/strossmayerovonam/k-strossmayerovonam-plan-01.pdf`,
`obrazky/prejezdy/p-trojskymost-plan-01.pdf`, legend `obrazky/smes/planky-legenda-01.pdf`.

---

## 7. Other promising pages (not read)

- [2006041390] Elektrárna Holešovice crossing; [2006041437] Vltavská crossing; [2006041558] Výstaviště
  loop; [2006041550] Březiněveská loop; [2006041324] Vozovna Kobylisy depot — rest of line 17's switches.
- [2008090701] track on Masarykovo nábřeží (Národní divadlo – Mánes); [2011022206] Křížovnická track
  (Staroměstská – Čechův most); [2006041642] Dukelských hrdinů; [2015072001] old Podolská street line —
  line 17 track pages with stop positions like 5.
- [2006041636], [2006041637] provisional single track and gauntlet in Trojská street (2001);
  [2006041451] Nad Trojou crossover; [2006041479] diamond crossovers; [2006041298] use of surface
  crossovers.
- [2007091204] Klárov and [2009041902] Střed substations — the missing feeders of line 17's centre part;
  substation pages for lines 9/22/23 (same map pattern).
- [2006112701] Barrandov signalling (occupied/free section lights, sleeper signals) — not our lines.
- [2010031701] S49 grooveless track, [2006041296] BKV panels, [2013022701] W-tram, [2006041490] grassed
  track, [2006041492] Vienna-type stops — track-bed construction for drawing surfaces.
- [2006041328] stub tracks; [2006041329] mechanical barriers against cars on the track.
- PDFs of DP orders linked from [2017080101]: `clanky/odr_2012_028.pdf` (operation on electric switch
  044), `clanky/odr_2011_317-04.pdf`.
- Line articles for timetables and consists: [2019100701] line 9, [2011060202] line 22,
  [2012122501] line 23 (read only their ends; history-heavy).
