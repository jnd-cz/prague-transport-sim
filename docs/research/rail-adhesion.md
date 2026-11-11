# Wheel–rail adhesion by weather, sand and the T3's sanders (research for #266)

Researched 2026-11-04. **M** marks a measured value, with the source and the place in it. **E** marks an estimate or a value from a review or textbook that gives no primary measurement. Where a page was bot-checked, behind a login or paywalled, the link is listed under "Not read" at the end.

## 0. Where the current game values probably came from

The game's set (dry 0.30, sand cap 0.33, snow ~0.1) matches a widely reprinted textbook table almost exactly:

- **Moore, D.F., *Principles and Applications of Tribology*** (Pergamon 1975; Elsevier 1998), reproduced as Table 3 in Zhu, Y., *Adhesion in the wheel–rail contact under contaminated conditions*, licentiate thesis, KTH 2011 (TRITA-MMK 2011:15), p. 9. PDF: https://byv.kth.se/polopoly_fs/1.266908.1600689744!/Menu/general/column-content/attachment/Zhu_licentiate_thesis.pdf

| Rail condition (Moore) | μ |
|---|---|
| dry and clean | 0.25–0.30 |
| dry with sand | 0.25–0.33 |
| wet and clean | 0.18–0.20 |
| wet with sand | 0.22–0.25 |
| greasy | 0.15–0.18 |
| moisture (damp) | 0.09–0.15 |
| light snow | 0.10 |
| light snow with sand | 0.15 |
| wet leaves | 0.07 |

The layout of the extracted PDF scrambles the right-hand column. The pairing above is the only one consistent with the text, which says moisture is worse than outright wet and sand helps snow. This is an **E**-grade source: a textbook summary for mainline railways with no method given. It is still the best single table for the job, and the primary measurements below agree with it.

## 1. Adhesion by condition

### Dry
- **M** British Rail Research (Broster, Pritchard & Smith 1973, *A Basic Study of Wheel/Rail Adhesion 6*): on parts of the UK network μ ranged 0.04–0.55, **averaging 0.3 dry**. Cited in Lewis S., Riley, Fletcher, Lewis R. (2018), *Optimisation of a railway sanding system…*, Proc IMechE F 232(1) 43–62, §1 Introduction. https://eprints.whiterose.ac.uk/110459/
- **M** Locomotives: maximum adhesion **~0.35 dry at low speed** (Polach 2005, Wear 258). Locomotive tests at 220 kN axle load: **0.3–0.4 at 5–20 m/s** (Six et al. 2015). Both cited in Trummer, Buckley-Johnstone, Voltr et al. (2017), *Wheel-rail creep force model for predicting water induced low adhesion phenomena* (WILAC), Tribology International 109, 409–415, §2. https://dk.upce.cz/handle/10195/67456
- **M (tram wheel)** Full-scale tram wheel rig (Ø700 mm, University of Pardubice, 4 kN, 5 m/s): **dry peak 0.4**. Buckley-Johnstone, Trummer, Voltr et al. (2020), *Full-scale testing of low adhesion effects with small amounts of water in the wheel/rail interface*, Tribology International 141, 105907, §3, Fig. 12. https://eprints.whiterose.ac.uk/150109/
- **E** RAIB Report 25 (Part 3)/2006 (Jan 2007), *Adhesion review*, para 9: "typical values for μ for dry rail would be at least 0.20". https://assets.publishing.service.gov.uk/media/547c907740f0b602410001c1/070108_R252006_Part_3_Adhesion_Review.pdf
- Note: hand-push tribometers read about 0.6–0.7 on sunny dry rail (Lewis & Olofsson, *Wheel-Rail Interface Handbook* 2009, in Zhu 2011 Table 2). That is a sliding-friction reading, not usable wheel adhesion, and twin-disc lab values (0.3–0.6) run higher than field values for the same reason. Use the field and full-scale numbers.

### Onset of rain, damp rail, dew, drizzle (the "wet-rail phenomenon")
The user's observation is well documented. A small amount of water mixed with iron oxide and wear debris is worse than a lot of water.
- **M (tram wheel)** WILAC 2017 (above), §4 and Fig. 3, on the Pardubice tram wheel rig at 4.2 kN and 5 m/s:
  - water at **25 µL/s**: peak about the wet level, then a steep fall with slip to **0.06**, measured repeatedly at 60–90 % creep;
  - **35 µL/s**: "wet" type curve, **~0.15**, nearly flat with creep;
  - **60 µL/s and above** behaves like bulk water.
  - The abstract names the conditions as "humid weather or at the onset of rain".
- **M (tram wheel)** Buckley-Johnstone 2020 (above), §3–5:
  - bulk water brings **0.4 → 0.2**;
  - at 25 µL/s adhesion falls **below 0.1** once sliding starts, with a minimum **T/N 0.05**;
  - the slide is sustained even when torque is backed off, which matches drivers' reports;
  - the **first train in dew conditions** is named as the case.
- **M** Galas, Omasta, Shi et al. (2020), *The low adhesion problem: the effect of environmental conditions on adhesion in rolling-sliding contact*, Tribology International 151, 106521 (ball-on-disc with climate chamber, Brno University of Technology), abstract:
  - **clean surfaces under dew: ≤0.15**;
  - contaminated or oxidised surfaces, humid or wet: **≤0.05**.
  - https://www.fme.vutbr.cz/en/veda/publikace/detail/164462
- **M** Amsler drying test (Beagley & Pritchard 1975, in WILAC §2):
  - water drops μ 0.6 → 0.3;
  - as the rail dries, a debris paste brings it to a **minimum of 0.2** before it returns to dry.
  - This is lab scale; the relative drop is the useful part.
- **E** RAIB 2007, paras 29–31, quoting the Adhesion Working Group manual (2004):
  - causes listed include "light rain/drizzle after a dry period mixed with contaminants";
  - the University of Sheffield research finds "heavy rain will clean the rail";
  - "water on clean rail does not create adhesion problems … but a small amount of water in combination with contamination does".
- **E** Moore: moisture 0.09–0.15.
- **E** Incident timing: most UK wet-rail incidents fall at **morning and evening dew point** (Buckley-Johnstone 2020 §1). Leaf incidents peak **05:00–10:00 and 20:00–24:00** (Ishizaka, Lewis & Lewis 2017, Figs 3–4; full reference under Leaves).
- **No measured duration** was found for how long the first-minutes effect lasts. It is governed by water rate, not time: on the rig the transition is complete between 25 and 60 µL/s. How long a real rail takes to rinse is an estimate (below).

### Steady rain on rinsed rail
- **M** BR 1973 (Broster): water brings the average **0.3 → 0.2** (Lewis 2018 §1).
- **M (tram wheel)** fully wet **0.2** (Buckley-Johnstone 2020, Fig. 13). Locomotives in wet conditions: **0.25 at low speed** (Polach 2005, via WILAC §2). Artificially watered rail at 10 m/s: **0.25** (Six 2015, via WILAC).
- **M** Speed matters when wet. A roller rig gave **0.10–0.16 at 100 km/h** (Zhang et al. 2002, Wear 253, via WILAC §2). Beagley et al. found wet adhesion "declined considerably with increased rolling speed" (Zhu 2011 p. 10).
- **E** Moore: wet and clean **0.18–0.20**. RAIB para 9: in wet weather μ "can fall to 0.10".

### Leaves
- **M (field)** Arias-Cuevas & Li (2011), *Field investigations into the adhesion recovery in leaf-contaminated wheel–rail contacts with locomotive sanders*, Proc IMechE F 225(5) 443–456. With a locomotive (21.5 t axle load) on a leaf layer, the mean in the first run was **0.06 dry and 0.04 wet**. Tabulated in Ishizaka, Lewis & Lewis (2017), *The low adhesion problem due to leaf contamination in the wheel/rail contact*, Wear 378–379, 183–197, Table 1. https://eprints.whiterose.ac.uk/112791/
- **M (field)** Nagase, test bogie, pine needles: minimum **0.05** dry and wet (Ishizaka 2017, Table 1).
- **M (field)** BR 1973: leaves as low as **0.02** (Lewis 2018 §1).
- **M (lab)** Twin disc with a leaf layer: **< 0.05 dry and < 0.02 wet** (Gallardo-Hernández & Lewis 2008, Tribology Letters; Ishizaka Table 1). The crushed "black layer" gives **~0.1, or 0.05 or less with a little moisture** (Fulford 2004, RSSB *Review of low adhesion research*, as summarised in Zhu 2011 p. 11).
- **E** Moore: wet leaves **0.07**. Classification used in UK research (Vasić et al., in Ishizaka 2017 §2):
  - medium low 0.10–0.15;
  - low 0.05–0.10;
  - exceptionally low 0.02–0.05.
- **E** Requirements: 0.2 for traction and 0.09 for braking (UK; Ishizaka 2017 §2, Lewis 2018). RAIB para 9: 0.3 m/s² of braking needs μ ≥ 0.03, and 1.2 m/s² needs μ ≥ 0.12.
- No measured value was found for a whole route's autumn average. Leaf layers are local: patches at trees and stops, with clean rail between.

### Snow, ice, frost
- **E** Moore: light snow **0.10**, and **0.15** with sand. No primary wheel–rail field measurement was found.
- **M (lab, qualitative)** Lyu, Bergseth & Olofsson (2016), pin-on-disc in a climate chamber (Civil-Comp Proc. 110; Sci. Rep. 6:32455):
  - from +3 to −15 °C without snow, friction **rises** (low-temperature brittleness of the steel);
  - at −25 °C condensed ice melts in the contact and lubricates, so friction drops sharply;
  - with snow, friction falls through pressure-melt water, and the warmer the air (more water), the lower the friction.
  - https://lup.lub.lu.se/record/6d25a38b-0345-45d6-9bad-c955dc7db3a9 (the numbers are in the paywalled full text).
- **E** RAIB 2007 para 29 lists "ice on the rail" as a cause, with no value.
- **E (Czech)** Balounová, H. (2011), *Konstrukce pískovacích zařízení pro drážní vozidla*, bachelor's thesis, VUT Brno, §2.2, p. 11, citing Kotrba & Vašíček, *Nová železniční technika* 1/2009:
  - rail is slippery mainly when damp (dew, biological dirt, leaves);
  - **"námraza nebo mokrá kolej"** (frost or wet rail) is less bad;
  - **in tram service, road salting** makes rail especially slippery because salt is hygroscopic.
  - https://www.vut.cz/www_base/zav_prace_soubor_verejne.php?file_id=39404
- Summary: snow is about 0.10 (E). For ice and frost no wheel–rail number exists; the game's 0.08 stays an assumption.

### Grease and oil
- **E** Moore: greasy 0.15–0.18. **M** Zhang et al. full-scale rig: oil gives very low adhesion, nearly independent of speed (Zhu 2011 p. 10).
- Lewis 2018 §1, citing [5, 6]: **mud deposited on rails at road crossings by road vehicle tyres** is a recognised cause of low adhesion. This is relevant to street track.

### Grooved street rail versus ballasted track
- **No measured comparison was found.** All the data above is from mainline (Vignole) rail or rigs. The tram rig used a full-size tram wheel, but a smooth roller as the rail.
- Qualitative sources:
  - mud and dirt carried by road tyres (Lewis 2018);
  - hygroscopic road salt on tram track (Balounová 2011);
  - oil from road traffic (inference, not measured).
- Proposal: no separate base value for street track. A small extra chance of a low-adhesion patch at road crossings and on shared lanes is defensible as a rule, but the size of that chance is an estimate.

## 2. Speed and slip (the creep curve)

### Speed
- **Curtius–Kniffler (1950), dry, from train tests:** μ = 0.161 + 7.5/(v + 44), v in km/h.
  - μ(0) = 0.33, μ(20) = 0.28, μ(40) = 0.25, μ(60) = 0.23.
  - As a ratio to standstill: **1.00 / 0.84 / 0.75 / 0.70**.
  - The formula is reproduced in Jernbaneteknologi, *Railway Engineering Compendium*, ch. 9 (https://jernbaneteknologi.no/en/chapters/09-train-track-interaction/). The same chapter gives the "UIC" curve 0.139 + 4.48/(v + 34.2) and warns that both are historical empirical fits, not guaranteed values.
  - Open Rails uses Curtius–Kniffler as its default, with a weather multiplier (https://open-rails.readthedocs.io/en/latest/physics.html).
- **M** Wet adhesion falls with speed much more than dry: 0.25 at low speed against 0.10–0.16 at 100 km/h (WILAC §2). Oil is nearly speed-independent (Zhu 2011).
- **E** RSSB SPARK summary: all but one published study show adhesion falling with speed.
- For a T3 (top speed about 65 km/h) the dry curve costs about 30 % between standstill and full speed. That is plausible to model, since locomotive-derived curves include a slipping wheel's losses.

### Creep curve (WILAC §2 and §4, Buckley-Johnstone 2020 §3)
- **Dry:** the peak is at low creep, typically about 1–3 % on these rigs; read from Figs 12/3 and the Arias-Cuevas 2010 twin-disc 0.5–3 % slip curves. Beyond the peak adhesion falls steeply.
- **Wet:** a lower level, the maximum shifted to higher creep, and "reduces the decrease of adhesion with increasing creep" (Polach 2005, quoted in WILAC). The curve is nearly flat, so a spinning wheel keeps most of the wet value.
- **Damp (small water):** the peak is near the wet level, then it collapses with slip to 0.06 at 60–90 % creep. The slide is self-sustaining: adhesion stays low as torque is reduced, so the driver must cut power well back to recover.
- **Model form:** Polach's falling friction law, μ(w) = μ0·[(1 − A)·e^(−B·w) + A], with w the slip velocity in m/s. A is μ at infinite slip divided by μ0.
  - Polach 2005 (Wear 258, 992–1000; paywalled, not read) gives typical dry and wet parameters.
  - From memory, **unverified**:
    - dry: A ≈ 0.40, B ≈ 0.6 s/m;
    - wet: A ≈ 0.40, B ≈ 0.1–0.2 s/m.
  - So a fully spinning or sliding wheel keeps roughly **40–50 % of peak dry**. Check this against the paper before citing it.
- **E** Open Rails' simple model drops tractive force to 10 % on exceeding adhesion, which is crude.
- **T3 context:** the original T3/T3SUCS has **no anti-slip or anti-slide protection** ("Vůz nemá SSO – protismykovou a protiskluzovou ochranu", DPP textbook, p. 5; source in §4). Spin and slide control is left to the driver, which fits the "keep the driver's skills" rule.

## 3. Sand

### Gain by condition
- **E** Moore:
  - dry 0.25–0.30 → 0.25–0.33 (≈ +0 to 0.03);
  - wet 0.18–0.20 → 0.22–0.25 (≈ +0.04 to 0.05);
  - light snow 0.10 → 0.15 (+0.05).
- **M (lab)** In a **dry** contact sand *reduced* adhesion at all densities, 0.75–7.5 g/m (Arias-Cuevas et al.; Skipper, Chalisey & Lewis 2018, *A review of railway sanding system research: adhesion restoration and leaf layer removal*, Tribology – Materials, Surfaces & Interfaces 12(4), §4.1.1). https://eprints.whiterose.ac.uk/139102/ So sanding dry rail should give no gain, not +0.1.
- **M (lab)** On leaves, sand restores adhesion to the level without leaves (Gallardo-Hernández & Lewis 2008, Tribology Letters 33, 97–109; and Skipper 2018 §5). Recovery grows with more sanding axles, more slip and medium grains of 0.3–0.6 mm.
- **M (full-scale rig)** On wet paper tape the minimum effective density was **7.5 g/m**. At 106 g/m recovery was lower, because sand plus contaminant makes a paste (Lewis et al. in Skipper 2018 §4.1.2).
- **M (field, braking)** From Skipper 2018 §4.1.3:
  - Waring, sanding at **2 kg/min/rail**: retardation **1.5 %g → 4.5 %g**; at **5 kg/min/rail**: **2 %g → 9 %g**;
  - RSSB trials: 4 kg/min/rail sanders held **> 6 %g** on rail below 0.02.
  - So on very low adhesion sand roughly **triples** usable adhesion, but does not reach the dry level.
- **M (field)** Southern Railway tests, from 60 mph: stopping distance improved **~33 %** with sand against none, and 3 kg/min was ~10 % better than 2 kg/min (RAIB 2007 para 180).

### Persistence for trailing axles
- **M (field)** Arias-Cuevas & Li 2011: "sanding was effective for the wheelsets after the sanding axle, showing the sand was staying indented into the leaf layer". The improvement reached even non-sanded axles because the leaf film was removed (Skipper 2018 §5.1.3; Ishizaka 2017 §3).
- **E** UK standard GM/RT2461: at most **7.5 g/m** under the last two axles, and units with **fewer than 6 axles behind the sander** may not have sanders, because the following wheels must clear the sand off the rail for track circuits (RAIB 2007 para 177). This implies the wheels behind clean the sand off within a few axles.
- No measured distance or time for how long sand stays on the rail was found. Estimate: sand laid at the front axle helps all four axles of a T3 (about 8.6 m of wheelbase span) while sanding and for a few seconds after. A leaf patch that has been sanded stays improved for the following axles.

## 4. T3 sanding equipment (Prague)

Source: **DPP (Dopravní podnik hl. m. Prahy), oddělení Výcvik a vzdělávání – Tramvaje, *TRAMVAJE T3.SUCS, T3M, T3R.P, T3R.PLF – učební pomůcka*, leden 2009, verze 03/09**. https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_t3.pdf

- **T3.SUCS (p. 5):**
  - control is mechanical: the driver pulls a lever fully up, which opens flaps in the sanders through a spring and Bowden cable;
  - sand falls **in front of both wheels of the first axle**;
  - the sanders are heated and sit **under the first seats, right and left**;
  - there is no anti-slip or anti-slide protection.
- **T3M (p. 12):** the sanders are the same as on the T3SU.
- **T3R.P (p. 18):**
  - two kinds: a **mechanical** sander (lever) **left, in front of the first bogie**, which also triggers the electric ones and is the only one that works when the car is pushed or towed;
  - **electric** sanders **right in front of the first bogie and left in front of the third axle**, driven by the bogie regulator (automatic on slip or slide); they work only with the car started;
  - a yellow "skluz" lamp shows them working;
  - they are heated;
  - the last seat on the left holds the battery switch and fuses instead of a sand box.
- **T3A 6554 (TV Progress test car, 1999–2000):** a third sand box was added to sand **the left wheel of the first axle of the second bogie**, housed in an asymmetric seat by the middle door. Source: prazsketramvaje.cz, article T3A. https://www.prazsketramvaje.cz/view.php?cisloclanku=2006040811
- **Heating:** the first heating step is the sanders: "První stupeň – pískovače" (DPP textbook, p. 18).
- **Braking context** (cs.wikipedia *Tatra T3*): magnetic track brakes act on the rear bogie in the first stage and all four in the second. They do not depend on adhesion and are the real emergency fallback on slippery rail.
- **Capacity and delivery rate: not found in any public source.** Searched in Czech, Russian and German, and in the DPP textbook, prazsketramvaje.cz and the Wikipedias.

### Reference rates for other trams and trains
- **Tram, measured spec:** Melbourne & Metropolitan Tramways Board tram specification, §4-15 Sanding equipment, Victorian Collections, Tramway Museum Society of Victoria (MMTB drawing T.3000 series, 1970s, probably the Z class):
  - **4 sand boxes, each ≥ 50 kg** usable;
  - sand ahead of the leading truck's wheels;
  - the valve delivers **35–45 g/s to each wheel**.
  - https://victoriancollections.net.au/media/collectors/61c11435820f25839e392b96/items/65c1d93d1c532628e873509e/item-media/65c1f6971c532628e8737f1f/original.pdf
- **UK rail standard:** GM/RT2461 guidance is at most **2 kg/min per rail (33 g/s)**.
  - In surveys the measured average was **1.15 kg/min (SD 0.6)** over 330 tests (Lewis 2018 §1).
  - Some operators accept as little as 0.2 kg/min (Balounová 2011 §3.3.2, after an RSSB report).
- **IBEG "Sand Step" tram sander:** up to **4000 g/min** (Balounová 2011, §3.2.4).
- Unverified search snippets, not read on the pages themselves:
  - Rheinbahn (Düsseldorf) up to 270 g/min;
  - DVG Duisburg 8 boxes × ~20 kg;
  - DSW21 Dortmund 350–650 g per 30 s.

### Estimate for the T3 (E)
- **Boxes:** 2 sand boxes in seat pedestals (T3SUCS), feeding the 2 wheels of axle 1.
- **Capacity:** the usable volume of a seat-pedestal box is perhaps 15–25 L. Dry quartz sand weighs about 1.5 kg/L, so **≈ 25–35 kg per box, 50–70 kg per car**.
- **Rate:** a gravity flap valve with no air is likely at or below the Melbourne pneumatic figure. Take **20–40 g/s per sander, so 40–80 g/s per car**.
- **Duration:** this gives **≈ 10–25 minutes of continuous sanding** per filling. Boxes are refilled at the depot, not per run.
- So a fixed 90 s per run is far below the hardware. If the game wants scarcity, base it on a box mass that empties at that rate over a shift, starting at a random fill level; **ask the user** (the Prague tram expert) for the real box size and refill practice, and cite his answer in `data/truth.json`.

## 5. Proposed values for the game

Peak μ at low speed; each row's evidence grade is in the Basis column.

| condition | now | proposed μ | basis |
|---|---|---|---|
| dry, clean | 0.30 | **0.30** | M: BR average 0.3; locomotive 0.35; tram rig 0.4 peak. E: Moore 0.25–0.30 |
| rain, first minutes / drizzle / dew / damp | — (0.17) | **0.10–0.12**, falling with slip to ~0.06 | M: tram rig 0.15 (35 µL/s), 0.06 at high creep (25 µL/s), T/N 0.05 minimum. M: Galas 2020 dew ≤0.15. E: Moore 0.09–0.15; RAIB/AWG |
| steady rain, rinsed rail | 0.17 | **0.18–0.20** | M: BR 0.2; tram rig 0.2. E: Moore 0.18–0.20 |
| autumn, general (rail between patches) | 0.15 | **0.20–0.25** (E; dew mornings → damp row) | no route-average measurement; leaves act through local patches |
| leaf patch (crushed film), dry | 0.06 | **0.06** | M: Arias-Cuevas & Li field mean 0.06 |
| leaf patch, wet | (0.06) | **0.03–0.04** | M: field mean 0.04; twin disc < 0.02. E: Fulford ≤0.05 |
| light snow | 0.12 | **0.10** | E: Moore 0.10 |
| icy spot / frost | 0.08 | **0.08** (assumption stays) | no wheel–rail measurement; RAIB lists ice as a cause; a Czech source says frost is milder than damp |
| grease / oil / road mud at crossings | — | **0.15** (E) | E: Moore greasy 0.15–0.18; M: oil very low and speed-independent (no number) |
| speed factor | none | **×(0.161 + 7.5/(v + 44))/0.3315** (1.00 at 0, 0.75 at 40, 0.70 at 60 km/h); stronger for wet | Curtius–Kniffler (dry); M wet 0.25 → 0.10–0.16 at 100 km/h |
| beyond peak slip | ? | dry falls to ~40–50 % of peak when spinning; wet nearly flat; damp collapses to 0.06 | WILAC / Polach (parameters to verify) |

Sand, replacing "+0.1, cap 0.33":

| base condition | sanded μ | basis |
|---|---|---|
| dry | **no gain** (max 0.33) | E: Moore 0.25–0.33; M: lab, sand lowers a dry contact |
| wet | **+0.04 → 0.22–0.25** | E: Moore |
| damp / onset of rain | **→ ~0.20** (E) | no direct measurement; similar to wet with sand |
| leaf patch | **×2–3, up to ~0.15–0.20** | M: field braking 1.5 → 4.5 %g at 2 kg/min; lab restores the no-leaf level |
| snow | **+0.05 → 0.15** | E: Moore |

- **Sand reach (E):** while sanding, all axles benefit. A sanded leaf patch stays improved for the following axles, as measured in the field; no distance is known.
- **T3 sand capacity and rate (E):**
  - 2 boxes (T3SUCS: axle 1, both wheels; T3R.P: 3 sanders, adding one before axle 3);
  - ≈ 25–35 kg each;
  - ≈ 20–40 g/s per sander;
  - ≈ 10–25 min of continuous sanding per filling.
  - Confirm with the user.

**Follow-up issue for weather that changes during a run:** supported by the measurements. Small water on oxidised rail gives the lowest wet-weather values. Bulk water gives about 0.2, and drying rail passes back through a minimum.
- **E** Model "rain starts" as the damp value until the water rate is high enough, then rinsed wet. The time to rinse is unmeasured: assume a few minutes in steady rain, longer in drizzle.
- **E** When rain stops, pass through the damp value again before dry. Dew mornings use the damp value.

## Not read (blocked, login or paywall; links for the user)
- VUT Brno theses on sanding units, bot-checked (Anubis):
  - https://dspace.vut.cz/items/cc025f0f-8b2b-4c50-b672-34ce75aefad3 (*Vývoj pískovacích jednotek pro kolejová vozidla*; tested for tram conditions);
  - https://dspace.vut.cz/items/2b37cb9b-b5c4-4dec-a509-bc8a3176562e (*Koncepční návrh dávkovače písku*);
  - https://dspace.vut.cz/items/2e2bcce8-ca63-4988-9571-adbb08ac670a
- Arias-Cuevas & Li 2011 field paper (TU Delft repository refused the connection): https://repository.tudelft.nl/record/uuid:99eef3ee-b084-46bc-8047-00fd1dcf9acd
- Fulford 2004, *Review of Low Adhesion Research* (RSSB SPARK, login): https://www.rssb.co.uk/spark/sparkitem/pb022135 ; RSSB T354 leaf characteristics: https://www.rssb.co.uk/research-catalogue/CatalogueItem/T354
- Polach 2005, *Creep forces in simulations of traction vehicles running on adhesion limit*, Wear 258 (paywall), for the dry and wet A and B parameters: doi 10.1016/j.wear.2004.03.046
- Lyu et al. 2016, Sci. Rep. 6:32455 (snow, sub-zero numbers; nature.com redirected to a login): https://www.nature.com/articles/srep32455
- Rheinbahn sand page (JS-only): https://www.rheinbahn.de/warum-braucht-die-strassenbahn-sand/

## The user's sand figures (2026-11-04)

The user ran a Gemini query that gave no links: "my simple gemini query turned up with some estimates we could use … no specific links giben sadly". The figures are unverified estimates (**E**).
- **Sanders on the original T3 / T3SUCS:** gravity-fed, with an electromagnetic flap; the outlet size sets the flow.
- **Hopper:** 12–15 l, with a gravity flow of 3–6 kg/min per bogie (attributed to ČKD technical descriptions).
- **Sand:** dry quartz of 0.4–1.2 mm weighs 1.4–1.6 kg/l, so a hopper holds 17–24 kg.
- **Pneumatic sanders:** metered at 1.0–2.5 kg/min per rail. The answer cites "EN 15594 / VDV 154"; which standard actually covers sanders is not checked.

Together: 2 hoppers last about 3–8 min of continuous sanding. The game uses 5 min per filling (`src/tram.js` `SAND_TIME`).

The user, on practice (2026-11-04): "Sand can be refilled at each terminus, starts with full from the depot." A run in the game is one trip, so it starts full.

## Used in the game (#265, #266)

`src/tram.js` holds the values; this note gives their sources:
- `ADHESION` (dry 0.30, rain 0.18, leaves 0.22 between the patches, snow 0.10);
- `muSpeed` (Curtius–Kniffler);
- `sandedMu`;
- the creep curve (`CREEP_PEAK`, `SPIN_LEFT`);
- `SAND_TIME`.

`src/game.js` `muAt` sets leaf patches at 0.06 and icy crossings at 0.08; the latter is still an assumption.
