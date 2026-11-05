# T3 / T3SUCS driver's panel: what each control and lamp does

Read 2026-11-04. This builds on [t3-accelerator.md](t3-accelerator.md) and does not repeat what is already there. Photos:
car 6921 (the user, 2026-10-31, not in the repo) and three photos the user found (a T3M, a T3 with
Norwegian labels, a T3 with a digital speedometer).

Confidence:
- **[A]**: a ČKD document.
- **[B]**: the DPP textbook or a DPP exam.
- **[C]**: a web or forum source.
- **[photo]**: read from the photos only.
- **[inf]**: my own inference.

"p." is the printed page, which equals the PDF page for ckd03 and ckd02. For ckd24 the printed page
is the PDF page minus 1 (from PDF p. 12 on).

## Sources used (new or newly read)

| key | what | where |
|---|---|---|
| ckd02 | ČKD *Soupis elektrické výzbroje* T-50405 (equipment list, TKS/Vk-05/82), pp. 1–4 | https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-02-Soupis.elektricke.vyzbroje.pdf |
| ckd03 | ČKD *Funkce a obsluha el. výzbroje TR 37* T-50172, pp. 3, 8–14 | https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-03-Funkce.a.obsluha.El.vyzbroje.TR.37.pdf |
| ckd24 | ČKD *Popis funkcí el. výzbroje TR 37* T-50413, printed pp. 15–22 | https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-24-Popis.funkci.elektricke.vyzbroje.TR.37.pdf |
| ckd05 | ČKD *MB 225 – BR 232, LA 13* (brake actuator), pp. 2–3 | https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-05-Celistova.brzda.a.brzdic.pdf |
| schema | ČKD drawing 1-38-370 444, legend of device codes | https://k5.sh.cvut.cz/~oskar/T3SU/T3SU-schema.pdf |
| ucebnice | DPP textbook *Tramvaje T3.SUCS, T3M, T3R.P, T3R.PLF* (03/09), pp. 4–8, 13–14, 19 | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_t3.pdf |
| tech26 | DPP exam *Technická příprava*, valid from 2025-09-01 (file 2026-02-01), Q2849, Q2856, Q2858, Q2855, Q4097, Q4100, Q4101 | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_20260201.pdf |
| tech12 | DPP exam *Technika* 2012, Q1–2, 4, 11–13 | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_technika_20120101.pdf |
| mt6921 | car 6921 page | https://tram.mobilnitabla.cz/vuz/6921 |
| busatlas | Prague tram types (last unmodernised T3s) | https://prague.busatlas.uk/trams.html |
| exam 2017 | DPP exam *Technická příprava* valid from 2017-04-30, Q2873 (T3R.P loss of traction power: LED and buzzer) | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_20170430.pdf |
| kia | Kia's Czech owner's manual: *světelná houkačka* = headlight flasher (the term) | https://ownersmanual.kia.com/full_webhelp/SG2/2024/cs_CZ/topics/chapter5_16_2.html |

All ČKD documents describe the **T3SU/ČSSR** car of 1982–87. Car 6921 is an older plain T3 (Q5),
so its wiring may differ in details.

## Q1. Meters

| item | finding | confidence |
|---|---|---|
| Voltmeter 0–40 V | **Battery / control voltage (24 V system).** The equipment list gives "V Voltmetr Metra DPPIL 4/D 0–40 V" (ckd02 p. 2, item 49). After the motor-generator starts, "the voltmeter must show the battery voltage, about 26 V" (ckd03 p. 3, B3). DPP exam: with control **off** it shows the battery voltage; with control **on** it shows the charging value (tech26 Q2849 and the question before it; tech12 Q1–2). The user's ~28 V when charging fits; 6921's photo reads ≈28 V. | A + B; photo |
| Ammeter | Metra DPPIL 4/D, listed as **0–550 A**, with shunt Sh **300 A / 60 mV** (ckd02 p. 2, items 47–48). 6921's scale reads 0–600 A (photo). The shunt sits in one motor group, so a scale twice the shunt rating shows car current [inf]. This agrees with the existing note's 3.8. | A; photo; inf |
| Speedometer | **Not in ČKD's 1982 equipment list.** There is no rychloměr item. "Svorkovnice tachografu" (terminal board for a tachograph, item 42a) is **hand-added** (ckd02 p. 2), so a speed recorder came as a later change. 6921 has a round 0–80 km/h speedometer with odometer and a green LED to the left of the panel, mounted on its own pedestal: a retrofit [photo + inf]. DPP's exam shows a later **digital** speedometer (seven-segment km/h, LCD "Baterie 26.1 V", buttons MODE/up/down, "Test", "Vmax"), which is photo 3's "C.T.M." unit (t3.md § 10). | A; photo; inf |
| Middle slot | 6921 has a blank plate between the ammeter and voltmeter [photo]. Photo 1 has a km/h meter there. Photo 1 also has a **MAX. RELÉ** button and a lamp strip with an extra field after VLAK, likely NADPROUD. The T3M has an "MR" button and "NADPROUD" lamps (ucebnice p. 13–14). So photo 1 is most likely a **T3M** (thyristor rebuild), not a T3SUCS [inf]. The middle slot was a provision filled differently per rebuild; no source dates the change. | B; inf |
| Line-voltage meter | **None.** The equipment list has only "KN signální světlo (napětí sítě)" (110 V lamp) and "KN doutnavka" (glow lamps) (ckd02 p. 3, items 77–78). "The trolley voltage is signalled by a glow lamp on the driver's panel" (ckd03 p. 9; ckd24 p. 20, § 7.7). It lights while there is voltage. On 6921 the lamp **NAPĚTÍ V TROLEJI** glows orange [photo]. | A |

## Q2. Controls

| control (6921 label) | function | confidence |
|---|---|---|
| **VYPÍNAČ ŘÍZENÍ** 0–1–2 (cam switch) | Control switch VŘ. Turn it to **2** (spring-return) to start: the motor-generator runs up, the safety relay RB is set, and it **springs back to 1** = ready (ckd03 p. 3, B3). Position 2 also resets RB after a rescue brake (ckd24 p. 19, § 7.3). If it stays in 2, the panel's rescue button does not work (ucebnice p. 4). **0** = off: the shoe brakes apply (ucebnice p. 5) and the dipped lights go out (ucebnice p. 7). In a 2-car set the second car's switch must be at 0; with both at 1 the rescue button does not work (tech26 Q2856). | A + B |
| **BEZPEČNOSTNÍ SPÍNAČ** (red button below MYCÍ STROJ; the label reads so in an enlarged crop) | Safety button **BS**: since ČKD change 82-09-018 it replaces the vigilance pedal (ckd03 p. 3 crossed-out text "(bezpečnostní vypínač)"; p. 12 "šlapka bdělosti (bezpečnostní spínač)"). Pressing it drops RB: all track brakes (K1+K2), full shoe brakes, LS/M1 out, the bell rings (ckd24 p. 15, § 5.3; p. 19, § 7.3). DPP calls the panel button "**Záchranná brzda**" (photo 1 has that label in the same place). It works only with control on (tech26 Q2855). Electric brake too if the pedal is parked (ucebnice p. 5). | A + B; photo |
| **MYCÍ STROJ** (black button) | "Průjezd mycím strojem", TLM: bridges SN and DBR so that LS/M1 close without line voltage (existing note 8.2). Uses: (1) washing-plant passage on ≤24 V wire, held all the time (ckd03 p. 14, B22); (2) shoe-brake release for towing or rolling off a section insulator: unpark, press it with the drive pedal, the brake lamps go out (ckd03 p. 12–13, B20; ucebnice p. 7); (3) a failed motor-generator: held all the time (ckd03 p. 14, B21). | A + B |
| **FUNKCE ČB** (black button, right row) | ČB = *čelisťová brzda*, the shoe brake (DPP: "park on the 2nd stage of ČB", ucebnice p. 11). On the T3R.P the button releases the shoe brakes without line voltage: unpark, press it, the brake lamps go out, roll off a section insulator by gravity (ucebnice p. 19; tech26 Q2878). The T3SUCS does the same with **MYCÍ STROJ together with the drive pedal** (ucebnice p. 7). 6921 has both buttons: its FUNKCE ČB is a later DPP fitting, presumably the same release [inf]. The user found it in a 2009 DPP T3 document (locked on Scribd); the downloadable 03/09 textbook describes it only for the T3R.P. | B; inf |
| **BZUČÁK** (black button) | Driver's buzzer button **TLŘ**: "used in coupled cars for signalling between the leading and the trailing car" (ckd03 p. 11, item 15; ckd24 p. 19, § 7.4). The driver's buzzer **BZŘ** also sounds **by itself when the motor-generator is not running** (SN's rest contact), i.e. with no line voltage (ckd24 p. 19, § 7.4). DPP: on the T3R.P a loss of traction power is signalled "by the LED going out and the buzzer" (exam 2017, Q2873), and on the T3M "passing a section insulator is not signalled by the buzzer" (ucebnice p. 11), so on the T3SUCS it is [inf from both]. | A + B; inf |
| **NEVYSTUPOVAT** (red button, lower row) | "Door sound signal (Nevystupujte!): pressing the button sounds buzzers at **all doors** for as long as it is held" (ckd03 p. 10, item 8). Before closing the doors the driver can give "an acoustic **and optical** warning" (ckd03 p. 9, B13). The list has "Výstražné světlo PAL ×3", one warning light per door presumably (ckd02 p. 4, item 100), which supports the **user's guess of a lamp at each door** [A + inf]. Wiring: the warning button **TLV** energises the warning relay **RS**, which unlocks the door-blocking relay **RBD**. **Only then can the all-doors switch close the doors** (ckd24 p. 18, § 7.1, a hand-added line). The door buzzers BZ1–3 sound only at open doors (ckd24 p. 19). | A + inf |
| **DVEŘE I** (rotary) | Switch **VDŘ1** for the **first door alone**: relay RH1 → the door motor opens; switch back → it closes (ckd24 p. 18, § 7.1). | A |
| **DVEŘE II** (rotary) | Main door switch **HVDŘ**, all doors via relay RBD. Closing needs the TLV warning first (above) (ckd24 p. 18). Photo 1 labels the same two rotaries "DVEŘE PŘEDNÍ" and "DVEŘE" [photo]. So "II" means all doors, not door 2 alone [inf]. Motors stop at their end positions by cam contacts (ckd24 p. 18). An open door blocks traction through DBR (existing note). | A; photo; inf |
| **SVĚTELNÁ HOUKAČKA** (blue button) | "**TSH** – tlačítko světelné houkačky" (schema legend). *Světelná houkačka* is the Czech term for a headlight flasher (a car's flash-to-pass, e.g. Kia's Czech owner's manual), so: the headlights / high beams flash while it is held, as a warning [A for the name; C for the term; the user's reading agrees]. | A / C |
| **ZVONEK** (green button) | Warning bell **TZV** → bell ZV (ckd24 p. 19, § 7.3; ckd03 p. 10, item 1). The bell also rings by itself while RB is dropped, until control is set to 2. | A |
| **SVĚTELNÁ VÝSTRAHA** (rotary with a red translucent knob) | Not described in ČKD or DPP texts; not found online (2026-11-04). Likely **hazard flashers** (all direction lights flashing; the knob a pilot lamp), a later addition [inf]. The schema legend has a "relé výstrahy" (RS), but that is the door-warning relay (§ 7.1). | inf |
| **SMĚR** (toggle, lower row) | Direction-light switch **PP**, *přepínač směrových světel* (ckd02 p. 3, item 65; schema). Left/right flashing direction lights through the flasher P. In a set they work on all cars (ckd03 p. 10, item 2). | A |
| **SVĚTLOMETY** (toggle) | Headlight switch **PR**, *přepínač reflektorů* (ckd02 p. 3, item 66). DPP: headlights on by moving the dipped-light lever **back**. They stay on with control off, so the lever must go to the **middle** (ucebnice p. 7). Dipped and high beam (ckd03 p. 10, item 5). | A + B |
| **OSVĚTLENÍ** (rotary, yellow label) | External lights **den / noc** (day / night). Day: dipped lights while control is on. Night: also position and tail lights and the front destination sign (ucebnice p. 7). Brake lights come on with control on, while braking and with the pedal parked; white reversing light with the reverser at "vzad" (ucebnice p. 7; ckd24 p. 20, § 7.5). | B |
| **STĚRAČE** (rotary) | Wipers VS (schema; ckd03 p. 10, item 11). | A |
| **VÝHYBKA** (red button) | Switch button TV, at most 10 s (existing note 4/8.2). | A |
| **NOUZOVÉ OSVĚTLENÍ** (rotary) | Emergency lighting VNO: one lamp over each door, used when the main lighting fails (ucebnice p. 7; ckd03 p. 10, item 6). | A + B |
| **TOPENÍ ZRCÁTKA** (rotary) | Mirror heating **TOZ** (ckd02 p. 4, item 99; schema; ckd03 p. 11, item 17). | A |
| **VENTILÁTOR** (rotary, symbols ▭ 0 ▬) | Not in ČKD's list. The kalorifer's own fan is on the kalorifer switch (Q4). A cab fan for the driver, added later [inf; the user agrees]. Not needed in the game (the user, 2026-11-04). | inf |
| **ZÁŘIVKOVÉ OSVĚTLENÍ** (rotary, right side) | Saloon fluorescent lighting on/off (VO1–2, VSO "half lighting", schema). Half the tubes, on the side without doors, can be switched off from the driver's table (ckd24 p. 18, § 6.4). | A |
| **PŘEPÍNAČ OSVĚTLENÍ** (cam switch with the yellow warning plate) | Polarity switch **PPZ / PřZ** for the trolley-fed fluorescent tubes (ckd02 p. 4, item 98 "Přepínač zářivek"; ckd24 p. 18, § 6.4: "must be switched over and its polarity changed during service"). ckd03 p. 10, item 3 recommends doing it at termini. DPP: flip it at every terminus so the tubes keep their brightness (ucebnice p. 7). 6921's plate: switch it at every terminus, at the latest after an hour, to avoid damage to the lighting [photo]. | A + B; photo |
| **HAVARIJNÍ POJEZD** (red rotary) | "Emergency drive": cuts **all traction-fed (600 V) equipment of this car**, so the car can only be moved in a coupled set. The faulty car still needs working shoe and track brakes, control, motor-generator / charging / battery and the multiple-unit cable (ucebnice p. 8). | B |
| **PŘEPÍNAČ COUVÁNÍ** (green rotary; photo 1: "OVLÁDÁNÍ ZAD. PANELU") | Switch **PCZ** "přepínač jízdy zadním stanovištěm" (schema legend). With the reverser at "vzad" and the brake pedal **parked** it activates the rear auxiliary station: bell, doors, rescue brake, brake, drive (ucebnice p. 8; ckd03 p. 15). If the bell does not ring there, this switch is not on (ucebnice p. 8). Photos 1 and 6921 show the same switch in the same place, under two labels [photo]. | A + B |
| **MAX. RELÉ** (photo 1 only) | A T3M button: after the maximum relay trips, release drive, press MR, stop, control off and on (ucebnice p. 14). On the TR 37 car the MR resets itself when the drive pedal returns to 0 (existing note 3.7); 6921 has no such button. | B |
| Reverser | On the **left side panel**, set with the **universal crank** (*univerzální klička*) (ucebnice p. 4). Photo 2 shows the socket with the labels "Neutral / Frem / Bak" [photo]. Positions vpřed / 0 / vzad (ckd03 p. 3, 8). | A + B; photo |
| Hlášení zastávek, onboard computer | 6921: Apex DT-06 onboard computer (mt6921), "HLÁŠENÍ ZASTÁVEK" button [photo]. Modern additions. | C; photo |

## Q3. The lamp strip (6921: "ED – OPRAVNY")

ČKD's lamp colours (ckd02 p. 3, items 72–76 and 92; ckd24 p. 20–21):
- two white lamps for the direction lights;
- one orange lamp for the accelerator;
- one blue lamp for the headlights;
- one green lamp for the doors;
- three red lamps for the brakes.

| lamp | lights when | confidence |
|---|---|---|
| **SMĚR VLEVO / SMĚR VPRAVO** (arrows) | Direction lights working: "two white signal lights" (ckd24 p. 20, § 7.7), flashing with the indicators [inf]. | A |
| **V symbol** (unlabelled on 6921) | Photo 2 has the label "ŽÁDOST O VÝSTUP" there [photo]: a passenger's **stop request**, a later addition; ČKD lists "TLC 1÷3 tlačítko cestujících" in the schema legend. On the T3R.P a lit "V" shows requests (ucebnice p. 17). | photo + A/B; inf |
| **DVEŘE** (‖ symbol) | Lit (**green**) when **all doors are closed**; dark if any door is open. Fed by the door-mechanism cams DK1–3 (ckd03 p. 9, B13; ckd24 p. 18, § 7.2; ucebnice p. 7). | A + B |
| **BRZDY I** | Shoe brakes of **bogie 1** applied. Fed through the auxiliary contacts DČ1,2 of bogie 1's brake actuators (ckd24 p. 18–19, § 7.2). | A |
| **BRZDY II** | The same for bogie 2 (DČ3,4). | A |
| **VLAK** | Any shoe brake applied: contacts DČ1–4 of this car (ckd24 p. 19), **plus the trailing cars' brake lamp wire**, which is wired in parallel through the coupler (ckd24 p. 21, § 8.1, item 15 "signální světlo brzd řízených vozů"). On a solo car VLAK lights together with I and/or II. In a set, **VLAK alone = a brake on in car 2**; I+VLAK = bogie 1 of car 1; II+VLAK = bogie 2 of car 1 (tech26 Q4097, Q4100, Q4101). | A + B |
| **ZRYCHLOVAČ** (4-dot field) | **Orange**: lit while the accelerator resistors are in the traction circuit. Fed via VŘ5, ZR10 (positions 3–99), ZR1 (1–80) and RB's working contact. Lit (a) standing **unparked** (brake pedal at 0), (b) driving until accelerator position 80, (c) braking between positions 3 and 80 (ckd24 p. 20, § 7.6). Out when the resistors are cut out; DPP: "a dark accelerator lamp while driving = accelerator out of the traction circuit" (tech12 Q4). | A + B |
| **TOPENÍ ZRCÁTKA** (T symbol) | Mirror heating on [inf from the label]. | inf |
| blue lamp (not on 6921's strip) | Headlights on (ckd24 p. 20, § 7.7). | A |

**When BRZDY I / II light (stage 1 vs stage 2).** The actuator is a spring brake with a solenoid. Current through the coil releases it and the indicator reads "Odbrzděno"; without current the spring applies it (ckd05 p. 2). Its **auxiliary contacts sit under the top cover** (ckd05 p. 2) and feed the lamps. So a lamp follows the **actuator's position**, not a stage command.

| state | lamps | source |
|---|---|---|
| parked (stage 2, BR1 and BR2 off) | lit | ckd24 p. 14–15 [A]; user's photos [photo] |
| pedal back at 0 after a stop (LO → BR2 only: "partly released, 1st stage of the shoe brake") | still lit; they go out only after the drive pedal (M1 → BR1) | ucebnice p. 7 (Mycí stroj + drive → "the mechanical-brake lamps go out"); exam questions about lamps that stay lit "after applying drive" (tech26 Q4097–4101) [B]. The economy-resistor current does not pull the actuator to the released stop [inf]. |
| driving or coasting (BR1) | dark | B + inf |
| automatic shoe brake at ≈4 km/h on brake step 5 / parked | lit | inf from LO/BR |
| control switch off (car braked automatically) | **not** signalled | ckd24 p. 19 [A] |
| actuator released by hand (lever) | not signalled | ckd24 p. 19; ckd03 p. 9 [A] |

The lamps are fed via VŘ10, a 6 A fuse and resistors RS3,5,6 (ckd24 p. 18–19). ČKD's advice: while driving, check that no shoe brake drags, which wears the linings and loads the motors (ckd24 p. 19) [A]. Stage 1 vs stage 2 is not shown separately: both are "applied" [inf].

## Q4. Heating

| item | where | positions / function | confidence |
|---|---|---|---|
| Cab heater **kalorifer**, switch PKL | Left side wall (*"na levé straně bočnice"*, ucebnice p. 8). Photo 2 has a "KALORIFER" rotary low on the left panel [photo]. | 4 positions (ckd03 p. 10, item 13): **0** off; **1** fan only, outside air (also usable for summer ventilation, ckd03 p. 9); **2** half the elements (cab and windscreen); **3** full. ckd24 p. 17–18: 0 = heating off (a hand addition reads "cold air is blown in"); 1 = kalorifer motor; 2 = contactor SK1 + half the elements; 3 = SK1 + SK2, all elements. 600 V elements, 24 V control, thermostats THR / THK / RTH. DPP: 3 steps (air, half, full) (ucebnice p. 8). Also defrosts the windscreen (ckd03 p. 9). | A + B |
| Saloon heating, switch PT (*přepínač topení / temperování*) | Not located by a source. Photo 2's left panel has a second rotary (Norwegian label, illegible) next to the reverser socket; possibly this [photo/inf]. | **0 – ½ – 1**: contactors ST1 / ST2, one or both branches of the heating elements under the seats, 200 W / 200 V elements (ckd24 p. 17, § 6.2; ckd03 p. 9–10). DPP: stage 1 = three seats on each side, stage 2 = all seats (ucebnice p. 8). Also fed through the cut-out VT2. | A + B |
| **VYPÍNAČ TOPENÍ** (photo 3, left side) | Left side panel **by the reverser** (ucebnice p. 6). | Button **VT 1-2** ("odpínač topení"): cuts the saloon heaters and the kalorifer while passing an overhead switch contact, so their current does not throw the switch by mistake (ckd03 p. 11; ucebnice p. 6). | A + B |
| Waste-heat flaps (accelerator air) | **A box on the floor of the saloon by door 2**; the duct runs along the right side of the car (ucebnice p. 8). Not on the driver's panel. | A lever: **up = warm air into the car**; down = out of the car (ucebnice p. 8; tech12 Q13). | B |
| Mirror heating | Panel, TOPENÍ ZRCÁTKA | on / off | A |

## Q5. Car 6921

| fact | source |
|---|---|
| A **plain T3, not a T3SUCS**: Tatra Smíchov serial no. 162555; in service since 1974 per mt6921. Last-series T3 (series V, 6811–6992, built 1973–76). | mt6921 [C]; busatlas [C] |
| One of the **last three unmodernised T3s** in Prague (6863, 6892, 6921, Strašnice depot, July 2011, run as the rear car of a pair). Withdrawn from route 22 in **December 2011**, kept at the main works. Since 2012 at **Střešovice** (the historic fleet, nostalgic line 23 per its recent workings). | busatlas [C]; mt6921 [C] |
| Recorded equipment: accelerator 99 steps, pantograph KE 13M, controller HG14/24, brake actuator **LA 11** (the ČKD T3SU set lists BR 232 / LA 13); onboard computer **Apex DT-06**. | mt6921 [C]; ckd05 [A] |
| Original ČKD instrumentation (T3SU list, 1982): ammeter, voltmeter 0–40 V, line-voltage glow lamp, 8 signal lamps (2 white, orange, blue, green, 3 red), driver's buzzer, bell. No speedometer. | ckd02 [A] |

**Probably later on 6921** [photo + inf]:
- the round speedometer on a pedestal;
- the LED clusters in the lamp strip (red "IOI" LEDs, the 4-dot ZRYCHLOVAČ field) and the strip itself, marked "ED – opravny", presumably a DPP workshop;
- the V (stop request) lamp;
- FUNKCE ČB, SVĚTELNÁ VÝSTRAHA, VENTILÁTOR;
- the onboard computer and HLÁŠENÍ ZASTÁVEK;
- the seat.

**Probably original or 1980s** [inf]: ammeter, voltmeter, NAPĚTÍ V TROLEJI glow lamp, HAVARIJNÍ POJEZD, PŘEPÍNAČ COUVÁNÍ, VYPÍNAČ ŘÍZENÍ, MYCÍ STROJ, BEZPEČNOSTNÍ SPÍNAČ, the rotary switches with ČKD-style metal labels.

Two dates are relevant: the safety button dates from ČKD's 1982 change, and the rear-station control from revision C of 1984 (existing note § 8). On a 1974 T3 both must be retrofits [inf].

## Still unknown
1. What FUNKCE ČB does on 6921, and whether it differs from MYCÍ STROJ.
2. What SVĚTELNÁ VÝSTRAHA does (hazard flashers?), and what VENTILÁTOR's two positions are.
3. When and why Prague fitted speedometers (the side pedestal vs the middle slot vs the digital C.T.M.); no dated source.
4. Whether the warning lights at each door (Výstražné světlo ×3) flash with NEVYSTUPOVAT, and their colour.
5. Where the saloon-heating switch PT sits on a T3SUCS.
6. Whether 6921's plain-T3 wiring differs from the T3SU texts in the door blocking (TLV/RBD, DBR) and the lamp feeds.

## Brno's driver training material (Skorus 2015): what it confirms or adds

D. Skorus, *Výukový materiál pro uchazeče o práci řidiče tramvaje*, master's thesis, Masaryk University
2015 (https://is.muni.cz/th/rjmst/DP_Daniel_Skorus.pdf, behind a browser check; read from a copy the
user sent). It is training material for DPMB (Brno) drivers. Only its general parts are used here:
Brno's T3s carry the same TR 37 equipment. [B] = an operator's training text.

| topic | what it says | page | relation to our notes |
|---|---|---|---|
| preparation current | "about 50 A" in coasting. It sets the resistors to the speed for a smooth restart or brake, and keeps the motors excited, so the electric brake acts at once | 55, 60 | confirms the model's 50 A and the fast build from coasting (t3-accelerator.md § 3.5) |
| electric brake fade | it stops braking below 5 km/h, and the shoe (or disc) brakes take over | 57, 60 | agrees with ≈4–5 km/h (LO, § 3.6) |
| electric brake failure | if it does not brake, the shoe brakes act at full force whatever the speed, down to the stop | 57 | agrees with LO's hand-over below 120 A |
| ammeter | measures the drive and the brake current | 57, 61 | agrees with the positive-only scale (the user) |
| voltmeter | measures the battery voltage | 61 | agrees with Q1 |
| emergency brake | the pedal to the floor: full electric brake with the track brakes; shoes below 5 km/h; cancelled by letting the pedal back | 59 | agrees |
| track-brake order | on the T3, past the parking position, first **bogie 1's** track brakes, then bogie 2's at the floor | 59 | **differs** from [ckd24] p. 16 (the **rear** bogie first). Brno's wiring may differ; open |
| rescue brake | the safety button or the saloon rescue buttons: all track brakes and the shoe brakes, **no electric brake**; reset by the control switch to 2 or a restart. The driver may leave the cab (head-on danger) | 59 | DPP: plus the electric brake if the pedal is parked (§ 2.3); the T3SU circuit drops LS, M1 |
| maximum relay | MR in LS opens it above 750 A; a tripped MR lights the **MR lamp, and pressing it** restores LS | 59 | [ckd24]: held until the drive pedal is back at 0. The lamp-button is the T3M's "MAX. RELÉ" (photo 1); Brno's T3s may have it too |
| track brakes | 5–7 t attraction each, 4 on a T3; for a sudden obstacle only, they jerk the car and injure passengers | 58–59 | agrees with 60 kN; supports penalising their use without need |
| driving rules | forbidden: holding the car on a gradient with the motors' traction; using traction and braking together to regulate speed. Coast as much as possible to save energy | 16, 60 | candidate penalties for #221 (economy, contacts) |
| resistors | the accelerator's resistors take no long load: starts must be short; no slow running on them | 54 | the burnt-resistor fault (§ 3.6) |
| pulse control | thyristor equipment (T3M) draws only the current needed: ≈33 % less energy than the resistors | 55 | a figure for comparing models later |
| dead-man | only cars with a hand controller (K2, KT8D5…): 3 s after the handle is let go, the safety relay stops the car | 63–64 | the pedal T3 has none (§ 2.3) |
| brake lamp | the red brake lamp on the panel must go out while driving (brakes released) | 58 | agrees with BRZDY I / II / VLAK (Q3) |
| doors | the driver gives "Nevystupujte, nenastupujte" before closing; all trams block starting with doors open, set to a few centimetres, so check the mirror for trapped passengers | 73 | agrees with NEVYSTUPOVAT before closing (Q2) and DBR |
| cab heater | kalorifer: 0 off, 1 ventilation, 2 half, 3 full | 66 | agrees with Q4 |
| saloon heating | some T3s use the accelerator's waste heat, switched by a lever at door 2; otherwise heaters in the seats or the sides | 54, 66 | agrees with Q4 |
| gear ratio | the T3 / K2 motor bogie's single-stage hypoid gear: 7.36 | 53 | [ckd-schema]: 7.43 for the T3SU/ČSSR; both ratios exist (§ 5.1) |
| fuses | shoe brakes 40 A / 24 V for all four brake actuators; track brakes 60 A per bogie; control 20 A; the motor-generator 20 A (600 V) | 58, 66 | — |
