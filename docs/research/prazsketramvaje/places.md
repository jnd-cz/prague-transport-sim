# Places on our lines

Lists published on prazsketramvaje.cz, matched by street and stop names to the game's lines (stops in
`data/lineN.json`). "Check" means the match rests on the street name only; the track graph decides
which direction and which branch. These are facts keyed by place, the kind `data/truth.json` keeps.

## Small-radius curves (R < 25 m, 15 km/h; sign SIG-V8)

From the speed-signal page [2006041265](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041265)
(list undated; photo of the sign at Moráň 2004). The page lists inner and outer curves; a curve
already slowed by other rules (switch, crossing, loop) has no sign (D 1/2 § 49.19).

| Place (as listed) | Curve | Our line |
|---|---|---|
| Na Moráni, from Karlovo náměstí | inner | 9/10 (Karlovo náměstí → Moráň) |
| Národní – Spálená | inner and outer | 9, 22, 23 (Národní třída) |
| Malostranské náměstí, by Beseda | inner | 22, 23 |
| Malostranské náměstí, from Karmelitská by Mostecká | inner | 22, 23 |
| Letenská, interlaced track (entry and exit at Klárov) | inner and outer | 22, 23 (the game's interlaced section, README) |
| Chotkova, by Jelení příkop | inner and outer | 22, 23 |
| Havlíčkova, before Hybernská | inner | 23 (Masarykovo nádraží → Bílá labuť; check) |
| Náměstí Míru, under the stop towards the centre | inner | 22; 9/10 (check) |
| Náměstí Míru x Jugoslávská, by the Praha 2 office | inner | 22; 9/10 (check) |
| Blanická – Korunní | inner and outer | 10 (check) |
| Na Žertvách x U Balabenky | inner | 37 (check) |
| Kotlářka loop, after the boarding stops | inner and outer | (9 does not enter the loop in service) |

Others on the list (not on our lines): Vinohradská x Škrétova; Svobodova x Na Slupi (both
directions); Ortenovo náměstí x Komunardů; Myslíkova by Mánes; Na Veselí x Soudní; Na Pankráci x Na
Veselí; 17. listopadu x Pařížská; Radlická by Křížová; Černokostelecká before the bridge to ÚDDP.

Game now: curve limits come from √(a·R) with 0.8 m/s² (10 km/h at R 20 m); no sign. The list gives
15 km/h through the whole curve at these places, and a place to stand the "r" sign.

## Night speed zones (SIG-V10, 22–6 h)

Same page. Zone 40 unless noted; DC = towards the centre, ZC = away from it. Start and end places.

| Line | Start | End |
|---|---|---|
| 17 | Rašínovo nábřeží, before Vnislavova (DC) | Rašínovo nábřeží, after Vnislavova (ZC) |
| 17 | Masarykovo nábřeží, before Myslíkova (DC) | Masarykovo nábřeží, after Myslíkova (ZC) |
| 17 | Dukelských hrdinů, before Strossmayerovo náměstí | Dukelských hrdinů, after Strossmayerovo náměstí |
| 17 | Klapkova, before Veltěžská (DC); Klapkova, after Ke Stírce | Klapkova, at Veltěžská (ZC); Klapkova, before Ke Stírce |
| 9, 22, 23 | Národní, after Masarykovo nábřeží (DC) | Národní, before Smetanovo nábřeží (ZC) |
| 9, 22, 23 | Vítězná, after Most Legií (ZC) | Vítězná, before Most Legií (DC) |
| 9, 23 | Lazarská, after Spálená towards Václavské náměstí | Lazarská, before Spálená from Václavské náměstí |
| 9, 23 | Senovážné náměstí, before the junction from Václavské náměstí | Senovážné náměstí, after the junction towards Václavské náměstí (check) |
| 9 | Štefánikova, before Anděl from Újezd; Štefánikova, after Holečkova (DC) | Štefánikova, after Anděl towards Újezd; before Holečkova (ZC) |
| 9 | Plzeňská, after U Trojice (DC) | Plzeňská, before U Trojice (ZC) (check) |
| 9/10 | Olšanská, before Jičínská | Olšanská, after Jičínská (ZC) |
| 9/10 | Jana Želivského, before Nákladové nádraží Žižkov stop (ZC) | Jana Želivského, after the stop (DC) |
| 10 | Vinohradská, after Želivského stop (DC) | Vinohradská, before Želivského stop (ZC) (check) |
| 22 | Bělohorská: after Myslbekova; before Pod Královkou; after Malý Břevnov stop (ZC) | Bělohorská: before Myslbekova; after Pod Královkou; before Malý Břevnov stop (DC) |
| 22, 23 | Karmelitská, before Mostecká (DC) | Karmelitská, before Mostecká (ZC) |
| 22, 23 | Keplerova, before Hládkov (ZC) (check) | – (no end listed) |
| 22 | Francouzská, before Blanická (DC) | Francouzská, after Blanická (ZC) (check) |
| 22 | V Olšinách, before Průběžná from Starostrašnická; Starostrašnická, before Krátká (DC) | V Olšinách, after Průběžná; Starostrašnická, after Krátká (ZC) (check) |

Zone 30: Poliklinika Barrandov only (not on our lines). The full list is on the page.

Game now: no time of day for limits, no zones. Needed: the game clock (it has one: departure times),
the zone's hours, the places.

## Dangerous gradients and safety stopping places

From the website ([web-notes.md](web-notes.md) 4.5–4.6, 5); signs SIG-G1–G4 and SIG-O3.

| Place | Fact | Line | Game now |
|---|---|---|---|
| Trojská street, Hercovka – Nad Trojou | **470 m at 80.15 ‰** (43 ‰ before Nad Trojou from the river). Downhill: stop at the light signal (safety stopping place), test the parking brake, then **roll without power at 20–25 km/h**, two blocks with tram signals, **one train per block**. Uphill: one train in the section, the T3 at full power. Track-brake test (battery voltmeter dip, a click) at the last stop before the section; two wheel chocks per car. | 17 | 25 km/h on every grade under −6 %; no stop, test or blocks |
| below Sídliště Modřany | gradients up to **69.9 ‰** | 17 | – |
| embankment curve before Nádraží Modřany | **40 km/h** | 17 | from OSM tags and curvature |
| Vozovna Kobylisy loop, both boarding stops; Kobylisy depot exit gate | safety stopping places, start with power | 17 | – |
| Jičínská, Flora → Olšanské náměstí | safety stopping place, start by gravity | 10 (check) | – |
| Blatiny towards Vozovna Motol | safety stopping place, start with power | 9 | – |
| Malovanka towards Hládkov / Pohořelec; Pohořelec towards Hládkov / Malovanka | safety stopping places, start with power | 22, 23 (check) | – |
| Jana Masaryka towards Krymská | safety stopping place, start with power | 22 | – |
| Krejcárek → Palmovka, ~120 m before Sokolovská | safety stopping place, start by gravity | 37 | – |

## Stop positions on Podolské nábřeží (line 17)

The website gives each stop's place in metres from a landmark (rebuilt 2011, platforms for two
2×T3 sets): Pobřežní cesta, Přístaviště, Dvorce, Kublov, Podolská vodárna, Výtoň, Palackého náměstí
([web-notes.md](web-notes.md) 5). A check for the game's stop positions on line 17. The Vyšehrad
tunnel: 32 m long, radius 100 m, 9 m wide.

## Speed switches on our lines

From the register [2006041262](https://www.prazsketramvaje.cz/view.php?cisloclanku=2006041262); signals
in [switches.md](switches.md) SW-R.

| No. | Place | Straight / diverging, km/h | Line |
|---|---|---|---|
| R04 | Nádraží Braník, into the loop | 30 / 15 | 17 |
| R09 | Podolské nábřeží od Dvorců | 30 / 15 | 17 (new junction of the Dvorecký most line, #209) |
| R03 | Letenský tunel od Strossmayerova náměstí | 50 / 40 | 17 (check which way 17 passes it) |
| R07 | Kotlářka, into the loop | 50 / 15 | 9 |
| R05 | Průběžná od Strašnické | 30 / 15 | 22 (check) |

## Higher speeds (Rychlostník) on line 17

OSM tags line 17's track with 60, 65 and 70 km/h in places (`tools/speed_survey.py`, extract 2026-11-04):

| km/h | line 17, s | between | OSM's note |
|---|---|---|---|
| 65 | 515–1405 | towards Libuš, before the first stop Levského (opened 2023-05-27); the game does not drive it | |
| 60 | 2040–2910, 4190–5490 | Modřanská rokle – U Libušského potoka; Nádraží Modřany – Belárie | |
| **70** | 5490–6440 | Belárie – Hodkovičky – Černý kůň, 950 m | "max. 70 km/h pouze vozy 14T, ostatní max. 65 km/h" on all 8 ways |
| 60 | 6440–7505, 7560–8680, 9980–10730, 18705–19770 | Černý kůň – Nádraží Braník; Pobřežní cesta – Přístaviště; Kublov – Podolská vodárna; Trojská – Nad Trojou | |

Off our lines the extract has 65 at Geologická – Hlubočepy, Smíchovské nádraží – Lihovar, Sídliště Barrandov –
Poliklinika Barrandov (with a 30 km/h night zone, the list's Zone 30) and Krejcárek – Ohrada (one way, the opposite track
60). In total: 65 km/h on 4.6 km and 70 km/h on 1.9 km of track, each way counted.

**What the signs look like there** (searched 2026-11-06; nothing found that shows one):
- **The rule:** more than 50 km/h needs a Rychlostník, white number on black (§ 25.1, § 49.17). A road sign does not do
  it: PSP Q28 marks "50 km/h unless the section is marked by speed signals" as the right answer where a road sign allows
  70, and gives "70 km/h with 14T and 52T, 65 with T3 and KT8D5R.N2P, 60 with 15T" as a wrong one (so that line is no fact,
  though it agrees with OSM's note for the T3).
- **By type:** § 49.17 is the only text on it: a section may carry several Rychlostník signs, the driver follows the one
  for his car type and the others the one without a type. So OSM's note reads as a 65 for everyone and a 70 for the 14T.
  D 1/2 draws the sign only with "60" and no type; how the type is written (a strip under the panel, as the arrow; on the
  plate; a plate of its own) is not in any source read. Inferred, not seen: no separate sign kind for 65 or 70.
- **Seen since:** the user's photo of a Rychlostník for **60** (2026-11-08): white condensed DIN figures on black, a white
  frame, hung by a clamp from the span wire over the track.
- **Sources read for this:** the speed-sign page (no places, no type); the Modřany line's Wikipedia page (no speeds; R04);
  the e15 article of 2019-10-31 (DPP planning up to 10 km/h more on separate track, naming Koněvova and Švehlova; "some
  signs allow 70"); Tram-fórum, 2022-08-15 (drivers: 65 is driven legally and routinely; no sign described).
- **Speeds by car:** T3 65 km/h by design (ČKD, `src/tram.js`), so a T3's limit on the 70 stretch is its own 65 either way.
  DPP's page gives the 14T 60 km/h, which disagrees with OSM's note; not settled here.
