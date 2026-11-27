# Running gear of six Prague articulated tram types (research for #579)

Read-only web research by a research agent, 2026-11-18; nothing downloaded. Positions are x metres rearward from the front end of the body.

**Conventions.** `x` is metres rearward from the **front end of the body** (front body face). Where a length over couplers is known, the coupler face offset is given separately. Tags on every number:
- **[S]** stated by the cited source;
- **[D]** derived by me with arithmetic from stated figures plus the assumption named (usually: equal overhangs at both ends);
- **[E]** my estimate, low confidence;
- **[?]** not found.

**Bottom line.** For KT8D5, KT4 and (roughly) K2, the bogie positions follow from published pivot spacings. For 14T, 15T and 52T, no public HTML source gives section lengths or bogie positions. The DPP driver textbooks (PDF, listed at the end) are the most likely place to find them. The maintainer's three recollections:
- **14T fixed bogies:** confirmed.
- **52T limited bogies:** confirmed for the two inner bogies, but no angle or mechanism was found.
- **KT4 fixed bogies:** not supported. The KT4 runs on pivoting T3-type bogies, and a linkage ties their rotation to the joint.

---

## 1. Tatra KT8D5 (and KT8D5R.N2P, KT8D5N)

- 3 sections, bidirectional. 4 two-axle bogies, all motored (8 motored axles) [S cs.wiki].
- The two inner bogies stand under the joints. The middle section sits on them and is not suspended. Both neighbouring sections rest on a single pin: "Na jednom čepu je posazen jak krajní, tak střední článek". The article says this is not a Jacobs bogie [S cs.wiki].
- Body 30,300 mm; 31,240 mm over couplers; pivot spacing 3 × 7,500 mm; bogie wheelbase 1,900 mm [S strassenbahn-online; de.wiki infobox; ru.wiki "база вагона 7500"].
- Wheel diameter 700 mm [S ru.wiki].
- KT8D5N has the same body, pivot spacing and wheelbase [S strassenbahn-online].
- KT8D5R.N2P (Prague): 31,340 mm over couplers [S dpp.cz]. Body 30,300 mm, given for the related R.N2 rebuild [S cs.wiki R.N2].
- The rebuild replaces only the middle section with a new low-floor one (350 mm floor). The end sections keep 900 mm, rising to about 970 mm at the joints [S cs.wiki R.N2]. No source says the bogies or pivots moved.
- Prague fleet: 60 units on 1 Jan 2026 [S dpp.cz].

| element | position x (m) | wheelbase | motored | turns relative to body | tag |
|---|---|---|---|---|---|
| S1 end section (cab A) | 0 → 11.40 (joint pin) | | | | [D] |
| S2 middle section | 11.40 → 18.90 | | | | [D] |
| S3 end section (cab B) | 18.90 → 30.30 | | | | [D] |
| B1 under S1 | 3.90 | 1.90 [S] | yes [S] | free pivot; largest angle [?] | [D] |
| B2 carries joint J1 | 11.40 | 1.90 [S] | yes [S] | free pivot, carries 2 bodies | [D] |
| B3 carries joint J2 | 18.90 | 1.90 [S] | yes [S] | free pivot, carries 2 bodies | [D] |
| B4 under S3 | 26.40 | 1.90 [S] | yes [S] | free pivot | [D] |
| J1, J2 | 11.40, 18.90 | | | yaw about the shared vertical pin, largest angle [?]; pitch free [D]; roll limited (see below) | |

[D] Overhang = (30.30 − 22.50) / 2 = 3.90 m, assuming equal ends. Add about 0.47 m for the coupler face of the original and about 0.52 m for R.N2P [D, equal ends assumed].

- **Pitch.** Every body rests on exactly two bogie pivots, so the bodies pitch independently and the shared pin has to allow it [D].
- **Roll (probable mechanism).** Czech patent CS260915B1 (Mueller, Skalický; filed 1985, when the KT8D5 was in development) covers a joint between sections of an urban multi-section rail vehicle, sitting on a bogie cradle:
  - one section's forked plate slides on the cradle seat over a radial bearing;
  - the other section's main pin sits in a resilient lower bearing and a heavy-duty articulated upper bearing;
  - a ring-in-sleeve clearance limits relative roll between the sections.

  The patent does not name a vehicle, so this is likely but unconfirmed for the KT8D5. https://patents.google.com/patent/CS260915B1/cs
- **Coupling.** Couplers at both ends [S: length over couplers]. Two coupled KT8D5 ran as a pair on Prague line X17 in 1993 and on a replacement line in 2010 [S cs.wiki].
- **Curve radii.** Horizontal [?]; vertical [?].

Sources: https://cs.wikipedia.org/wiki/Tatra_KT8D5 · https://de.wikipedia.org/wiki/Tatra_KT8D5 · https://ru.wikipedia.org/wiki/Tatra_KT8D5 · https://strassenbahn-online.de/Betriebshof/Tatra/Technische_Daten.html · https://cs.wikipedia.org/wiki/Tatra_KT8D5R.N2 · https://www.dpp.cz/vozovy-park/tramvaje/tatra-kt8d5-rn2p

## 2. Škoda 14T (Elektra / "Porsche")

- 5 sections, unidirectional. The odd sections (1, 3, 5) each carry one motored two-axle bogie attached rigidly to the body. The even sections (2, 4) have no running gear and are carried between their neighbours [S cs.wiki].
- The bogies do not turn ("neotočné"), and the floor in the joints is fixed to the even sections [S cs.wiki]. en.wiki lists "3 × fixed".
- fdrive.cz names the 14T's non-turning bogies as the main problem the 52T was designed to solve [S]. A Czech search-result snippet (source page not identified) calls them a mistake.
- Motors 6 × 90 kW; floor 350 mm in the suspended sections, 780 mm over the bogies [S en.wiki].
- Length 30,250 mm [S dpp.cz, cs.wiki "without couplers"]. A Wikipedia mirror gives 31,250 mm, which conflicts.
- Bogie wheelbase: 1,880 mm is stated for the sister type 19T (Wrocław, same Elektra family) [S pl.wiki 19T]. It is not confirmed for the 14T.
- Prototype lineage: the 05T had the same layout, and its suspended sections 2 and 4 are explicitly "zavěšeny" (hung) between the others. The 05T alone also had an experimental hydraulic steering between sections 1 and 2 [S cs.wiki 05T]. No source says the 14T has it.

| element | position x (m) | wheelbase | motored | turn | tag |
|---|---|---|---|---|---|
| S1 (bogie, cab) | [?] | | | | |
| S2 suspended | [?] | | | | |
| S3 (bogie) | about 15.1 ± 1 (middle bogie at centre) | | | | [E, symmetry] |
| S4 suspended | [?] | | | | |
| S5 (bogie) | [?] | | | | |
| B1, B2, B3 | under S1, S3, S5 [S]; x [?] | 1.88? (19T) | all [S] | **fixed**: no pivot, yaw and pitch locked to the body | [S] |
| J1–J4 | between every pair of sections; x [?] | | | yaw needed at all four; pitch/roll freedoms [?] | |

- **Joint freedoms (statics, not sourced).** Sections 1, 3 and 5 follow their own bogie's two axles in yaw and pitch. So both joints of each suspended section must allow relative yaw and pitch, or the three bogie sections would be forced into one plane. Each suspended section must also be held in roll by at least one of its joints [D].
- **Minimum radius.** 25 m / 20 m [S en.wiki infobox; the meaning of the two values is not given].
- **Vertical radii.** [?]
- **Coupling.** [?]

Sources: https://cs.wikipedia.org/wiki/Škoda_14T · https://en.wikipedia.org/wiki/Škoda_14_T · https://www.dpp.cz/vozovy-park/tramvaje/skoda-14t · https://fdrive.cz/clanky/praha-se-po-16-letech-docka-novych-tramvaji-umeji-samy-brzdit-pred-prekazkou-11795 · https://cs.wikipedia.org/wiki/Škoda_05T · https://pl.wikipedia.org/wiki/Škoda_19T

## 3. Škoda 15T (ForCity Alfa)

- **Sections.** 3, unidirectional, 100 % low floor.
  - Prague body length 31,400 mm "over the body ends" [S cs.wiki; dpp.cz; prazsketramvaje.cz 2008].
  - Riga: 31,600 mm with 3 sections; 41,000 mm [S cs.wiki] or 41,200 mm [S en.wiki] with 4 sections.
  - The 2008 presentation calls the three sections "very similar" and says middle sections can be added [S prazsketramvaje.cz].
- **Bogies.** 4, all pivoting: 2 end bogies and 2 Jacobs bogies at the section boundaries [S cs/de/en.wiki; prazsketramvaje.cz 2008].
  - Prague: all 16 wheels motored, one permanent-magnet motor per wheel, independent wheels with no conventional axles [S cs/de.wiki]. In Riga the first bogie is unpowered.
  - The bogies are of two designs, front and intermediate ("čelní a mezičlánkové"). Pivot distances were set as large as the clearance standard ČSN 28 0337 allows [S prazsketramvaje.cz 2008].
- **Minimum radius.** 18 m [S de.wiki]; en.wiki gives 18 m / 15 m.

| element | position x (m) | wheelbase | motored | turn relative to body | tag |
|---|---|---|---|---|---|
| S1 end section | 0 → about 10.95 | | | | [E] |
| S2 middle section | about 10.95 → about 20.45 | | | | [E] |
| S3 end section | about 20.45 → 31.40 | | | | [E] |
| B1 end bogie under S1 | centre about 2–3 [E]; driver's door "above the front bogie" [S] | [?] | yes | free pivot on a swing bolster; pivot offset (below) | |
| B2 Jacobs bogie | centre about 10.95 | [?] | yes | two pivots, one per section (below) | [E] |
| B3 Jacobs bogie | centre about 20.45 | [?] | yes | as B2 | [E] |
| B4 end bogie under S3 | centre about 28.4–29.4 | [?] | yes | as B1, mirrored | [E] |

[E] Basis for the Jacobs bogie positions: the Riga 4-section car is 9.4–9.6 m longer than the 3-section one, so one middle module repeats every about 9.5 m between Jacobs bogie centres. With equal ends, Prague's end sections then measure about (31.4 − 9.5) / 2 = 10.95 m to the first Jacobs bogie centre. Error is perhaps ±0.4 m.

- **Coupling.** An emergency coupler that is removable, with the standard Prague hook head. It comes in parts light enough to handle by hand and is fitted when the car must be towed after a failure [S prazsketramvaje.cz 2008]. A prototype was towed with a device called the "krab" [S prazsketramvaje.cz 2008, photo caption].
- **Vertical radii.** [?]
- **Joint details.** See §7.

Sources: https://cs.wikipedia.org/wiki/Škoda_15T · https://de.wikipedia.org/wiki/Škoda_15_T · https://en.wikipedia.org/wiki/Škoda_15_T · https://www.prazsketramvaje.cz/view.php?cisloclanku=2008041001 · https://www.dpp.cz/vozovy-park/tramvaje/skoda-15t · patents in §7

### 3a. The 15T measured on Škoda's drawing (2026-11-18)

The side view on page 2 of Škoda's product sheet *Tramvaj ForCity Alfa Praha* (2022;
`raw/reference/skoda/forcity-alfa-praha-produktovy-list.pdf`) was rendered at 8× with pdf.js, and the axle
centres, the bogie centres and the end bogies' pivot lines were read off it.
- **Scale:** the body from end to end, 4,982 px = 31.40 m [S, the sheet and the DPP 15T textbook: "bez spřáhel"]. That is 6.30 mm a pixel, about ±10 mm a reading.
- **Orientation:** the cab is at the right (the pantograph over the front section, the front view beside it).

Positions are x m from the cab's end of the body [M, measured on the drawing]:

| element | axles | centre | pivot |
|---|---|---|---|
| B1 end bogie, front | 0.90, 2.80 | 1.85 | 2.16 [D: w/6 toward the middle, as the rear one] |
| B2 bogie between S1 and S2 | 9.95, 11.84 | 10.90 (the bellows' middle) | two: over each axle [S patent] |
| B3 bogie between S2 and S3 | 19.57, 21.46 | 20.51 (the bellows' middle) | two: over each axle [S patent] |
| B4 end bogie, rear | 28.62, 30.52 | 29.57 | 29.22 (a line on the drawing) [M] |

- **Wheelbase:** 1.90 m on all four bogies [M].
- **Symmetry:** the overhangs are 0.90 and 0.88 m, and the bogie centres stand 10.90 m from either end of the body.
- **The end bogie's pivot:** 0.35 m off its centre toward the middle. The patent's w/6 is 0.32 m, so the drawing bears it out.
- **What each section rests on:**
  - S1 rests on 2.16 and 9.95: 7.79 m apart.
  - S2 rests on 11.84 and 19.57: 7.73 m.
  - S3 rests on 21.46 and 29.22: 7.76 m.
- **The bellows:** about 1.55 m long, centred over B2 and B3.

## 4. Škoda 52T (ForCity Plus Praha)

- **Sections.** 5, unidirectional, 100 % low floor. 31,990 mm over bumpers [S urban-transport-magazine; dpp.cz]. Width 2,500 mm. Wheel 640 mm new [S de.wiki; dpp.cz].
- **Bogies.** 4, all motored. In each bogie, two asynchronous motors each drive the wheel pair on one side [S cs.wiki].
  - Sections 1 and 5 have fully pivoting bogies: "dvou běžných a plně otočných podvozků v krajních článcích" [S fdrive.cz].
  - Sections 2 and 4 have partially pivoting bogies ("částečně otočné", "teilweise schwenkbar") [S fdrive.cz; dpp.cz "pivot semi-freely"; urban-transport-magazine DE].
  - Section 3 has no bogie and hangs between sections 2 and 4 [S fdrive.cz; de.wiki].
- **End cars.** de.wiki describes the type as "Gelenkwagen mit aufgesattelten Endwagen (jeweils auf einem Drehgestell)". Each end car stands on one bogie at its outer end and rests at its inner end on the joint of the neighbouring bogie section.

| element | position x (m) | motored | turn relative to body | tag |
|---|---|---|---|---|
| S1 end car (cab) | [?] | | | |
| S2 (bogie) | [?] | | | |
| S3 suspended | [?] | | | |
| S4 (bogie) | [?] | | | |
| S5 end car | [?] | | | |
| B1 under S1, B4 under S5 | [?] | yes | free pivot [S] | |
| B2 under S2, B3 under S4 | [?] | yes | limited ("partially pivoting") [S]; largest angle and mechanism [?] | |
| J1–J2, J4–J5 | [?] | | carry the end car's inner end vertically (saddle) [S de.wiki]; must allow pitch [D statics]; yaw limits [?] | |
| J2–J3, J3–J4 | [?] | | carry the suspended S3; freedoms [?] | |

- **What "partially pivoting" likely means [D].** S2 and S4 each stand on a single bogie and also carry the end car and half of S3. So the bogie must be able to carry pitching moment, presumably through secondary springs set apart along the vehicle. Its yaw relative to the body is then limited to a small angle.
- **Product family.** Škoda's catalogue describes the ForCity Plus as combining pivoting and non-pivoting bogies [S Škoda catalogue snippet]. On the Bratislava ForCity Plus 29T the two inner bogies are fixed [S en.wiki 29T], so the 52T's inner bogies are an evolution of that.
- **Minimum radius, vertical radii, coupling.** [?] The vehicle is single-ended (Prague lines end in loops) [S denik.cz].

Sources: https://www.dpp.cz/spolecnost/o-spolecnosti/vozovy-park/tramvaje/skoda-52t · https://dpp.cz/en/company/news/detail/342_2455-new-trams-for-prague-introduced · https://fdrive.cz/clanky/praha-se-po-16-letech-docka-novych-tramvaji-umeji-samy-brzdit-pred-prekazkou-11795 · https://de.wikipedia.org/wiki/Škoda_52T · https://cs.wikipedia.org/wiki/Škoda_52T · https://www.urban-transport-magazine.com/neue-strassenbahnen-fuer-prag-enthuellt-forcity-plus-52t/

## 5. Tatra K2

- **In Prague.** Prototypes 7000 and 7001 made test runs in 1966. The K2 never ran in regular Prague service; the article attributes this mainly to the hilly routes [S cs.wiki]. In 2021 DPP bought a former Bratislava driver-training car. It was presented in February 2023 as heritage car **7000** and runs on historic lines 23 and 42 [S cs.wiki].
- **Layout.** 2 sections, unidirectional, 3 bogies (6 axles) [S cs.wiki].
  - The two end bogies are motored and taken from the T3 [S cs.wiki; praha.eu technical annex via search snippet].
  - The middle bogie is unmotored and has shoe and rail brakes. It sits centred under the joint and carries both bodies [S cs.wiki; de.wiki].
- **Dimensions.** Body 20,400 mm [S cs.wiki; imhd.sk]; de.wiki says 20,260 mm. Over couplers 21,504 mm [S imhd.sk].
- **Wheelbase.** The T3 bogie wheelbase is 1,900 mm [S de.wiki T3], so it applies to the end bogies. Middle bogie wheelbase [?].
- **Coupler.** The de.wiki infobox names a Prague-type coupler.

| element | position x (m) | wheelbase | motored | turn | tag |
|---|---|---|---|---|---|
| S1 | 0 → about 10.2 | | | | [E equal halves] |
| S2 | about 10.2 → 20.4 | | | | [E] |
| B1 under S1 | about 3.8 | 1.90 (T3) | yes | free pivot | [E] |
| B2 under joint | about 10.2 | [?] | no | carries both bodies | [E] |
| B3 under S2 | about 16.6 | 1.90 (T3) | yes | free pivot | [E] |
| J1 | about 10.2, over B2 | | | yaw about the joint on B2; pitch free [D, each body on 2 bogies]; largest angles [?] | |

[E] Positions assume the K2 keeps the T3's end overhang, (14.0 − 6.4) / 2 = 3.8 m, from the T3's stated length of 14,000 mm and pivot spacing of 6,400 mm [S de.wiki T3]. The K2's own pivot spacing was not found. Add about 0.55 m for the coupler face [D].

- Minimum radius [?]; vertical radii [?]. Whether the K2 joint is a single shared pin like the KT8D5's [?].

Sources: https://cs.wikipedia.org/wiki/Tatra_K2 · https://de.wikipedia.org/wiki/Tatra_K2 · https://imhd.sk/ba/vehicle-type-description/21/Tatra-CKD-K2 · https://de.wikipedia.org/wiki/Tatra_T3

## 6. Tatra KT4 (KT4D, KT4Dt)

- **Prague.** No regular service. Prague saw only prototypes and test cars [S cs.wiki; strassenbahn-online]:
  - car 7000, rebuilt in 1969 from a K1 to test the new joint steering (later numbered 8004, scrapped 1977);
  - prototypes 8001 and 8002, built 1972/73, tested in Prague 1973–74, then Potsdam;
  - the KT4SU (1976) and KT4t (1983) prototypes, tested in Prague before going to Lviv and Berlin.
- **Layout.** 2 sections, unidirectional, 2 bogies (Bo'Bo'), one under each section. There is no bogie under the joint [S cs/de.wiki].
- **Dimensions.** Body 18,110 mm; 19,054 mm over couplers (de.wiki: 19,015) [S strassenbahn-online]. Pivot spacing 8,900 mm; wheelbase 1,900 mm [S strassenbahn-online; de.wiki]. The bogies are the T3 type [S en.wiki].

| element | position x (m) | wheelbase | motored | turn | tag |
|---|---|---|---|---|---|
| S1 | 0 → 9.055 | | | | [D equal halves] |
| S2 | 9.055 → 18.11 | | | | [D] |
| B1 under S1 | 4.605 | 1.90 [S] | yes | pivoting; rotation coupled to the joint by linkage | [D] |
| B2 under S2 | 13.505 | 1.90 [S] | yes | as B1 | [D] |
| J1 | 9.055, no bogie | | | yaw set by the linkage from the bogies; pitch and roll held stiff | [D] |

[D] Overhang = (18.11 − 8.90) / 2 = 4.605 m. Add about 0.47 m for the coupler face.

- **The bogies pivot.** The maintainer remembered fixed KT4 bogies; the sources say otherwise.
  - en.wiki: with no bogie at the joint, the design "necessitates a scissor joint connecting both bogies".
  - ru.wiki: the joint is two hinges, one at the floor and one at the roof, both on one vertical axis. Rods between the bogies and both sections deflect the joint according to the relative bogie rotation, which keeps the car steady on straight track and limits overhang in curves. (The section carries uncited-source tags.)
  - strassenbahn-online: the steering mechanism for the middle joint was newly developed for the KT4.
- **Consequence for the solver [D].** Two hinges on one vertical axis allow yaw only. Vertically, the whole car behaves as one rigid beam on its two bogie pivots 8.9 m apart.
- **Not found.** Exact linkage geometry and ratio [?]; it is probably in I. Köhler, *KT4 – Der Kurzgelenkwagen aus Prag* (GVE 2009). Minimum radius [?]; vertical radii [?].

**The steering linkage, from photos (the maintainer's find, 2026-11-18).** The k-report.net forum thread "Archiv diskuse
Tramvaje Tatra typů T a K do 15. 10. 2023" (https://www.k-report.net/discus/messages/48/337217.html), posts of
5–11 October 2023, has:
- ten photos from under a Potsdam KT4D in the workshop's pit, by a Potsdam tram worker (forum images 1530026–1530035);
- a removed bogie with its rods (1529888);
- the joint's lever plates, from Prague, where Potsdam's KT4s were overhauled in early 2017
  (https://www.prazsketramvaje.cz/obrazky/vozyosobni/potsdam_0251-001.jpg);
- two photos from the preview of Köhler's book (1530440–1530441);
- a brass model (1529859).

All 16 are kept in `raw/reference/photos/kt4/`, listed in `raw/reference/SOURCES.md`.

Read off them [M, from the photos; no dimensions]:
- **The rods.** From each half's bogie two rods run to the joint, one from each side of the bogie frame's end facing
  the joint, on ball joints (1529888, 1530027). They converge toward the car's centreline as they near the joint
  (1530031, 1530028). Each rod has a spring link near its joint end: a coil spring in a rubber boot (1530031–1530034).
  The two rods of a half then pass a cross guide under the floor and go into a canvas-booted box at the joint, one
  box on either side of the bellows (1530030, 1530033).
- **The joint.** Two bow-tie-shaped plates turn on the joint's central vertical pin (the prazsketramvaje.cz photo).
  Their outer ends are arcs that slide in arc guides centred on the pin. One half's rods act on one plate, the other
  half's on the other, at bolts off the pin; two smaller pins above and below the main one link the plates. With the
  bogies turning one way, the levers set the angle between the halves: the "scissor joint connecting both bogies"
  (en.wiki).
- **The full-scale gauge.** The book's preview shows a full-size frame of the KT4's outline on two bogies with the
  steered joint. A forum member (2023-10-10) says it was used to check the clearance profile.

What the forum members say:
- **The spring links** (UT, 2023-10-11): thanks to them the KT4 runs on straight track roughly aligned and calm,
  without swaying from side to side. Entering a curve, the mechanism takes hold late, only once the bogies have
  turned noticeably. There is also an emergency lock that fixes the mechanism for lifting the car (rerailing) or
  when it fails.
- **Cables tried on the prototype** (Pvvs, 2023-10-11): the functional prototype tried cables instead of rods.

For the solver:
- The steered joint's `steer` (assumed 0.5: the two halves are equal and the levers symmetric, which puts the joint
  over the track centreline) acts only past `steerFrom`, the bogies' relative turn below which the springs hold the
  joint straight.
- Neither the ratio nor that threshold is measured.
- **Coupling.** Couplers at both ends [S over-coupler length]. Multiple working: Potsdam ran pairs from 1980 and tried a three-car set in 1983 [S strassenbahn-online].

Sources: https://de.wikipedia.org/wiki/Tatra_KT4 · https://cs.wikipedia.org/wiki/Tatra_KT4 · https://en.wikipedia.org/wiki/Tatra_KT4 · https://ru.wikipedia.org/wiki/Tatra_KT4 · https://strassenbahn-online.de/Betriebshof/Tatra/KT4D/index.html

---

## 7. The 15T joint geometry (the atypical part)

**Source.** Patent CZ297213B6 / EP1741610B1 "Low-floor articulated rail vehicle, especially a tram". Applicants VÚKV a.s. and Škoda Transportation; inventors include M. Zelingr and T. Heptner; priority 4 July 2005. Its description matches the 15T as de.wiki describes it: Jacobs bogies with one pivot over each wheelset, end-bogie pivots shifted toward the car centre, and floor ramps of at most 1:10 over the bogies. The patent does not name the 15T.
- https://patents.google.com/patent/CZ297213B6/cs
- https://patents.google.com/patent/EP1741610B1/en

1. **There is no joint between sections.** The bodies are not pinned to each other. Each section rests on the Jacobs bogie through its own pivot; the only direct link between bodies is hydraulic dampers, and the passage is covered by bellows [S cs.wiki].
2. **Jacobs bogie: two pivots, each over an axle.**
   - Each section's pivot lies on the vertical through the centre of one wheel pair's common axis, not over the bogie centre [S patent claim 2; de.wiki says the same].
   - Each pivot is an axial ball bearing or a tilting spherical bearing on its own cradle (swing bolster) [S patent]. en.wiki: inner bogies carry two swing bolsters, outer ones one.
   - The two pivots are therefore one wheelbase *w* apart. Each section sits over the axle on its own side of the bogie centre [D: the other arrangement would make the bodies overlap; the patent text does not say which].
3. **Longitudinal link.**
   - A tie rod joins the two cradles. It carries traction and buffing forces between the sections and allows relative rotation about the longitudinal and transverse axes, i.e. roll and pitch [S patent].
   - A second rod ties one cradle to the bogie frame and carries longitudinal force into the bogie [S patent].
   - With spherical bearings, the two cradles may be one rigid piece [S patent].
4. **End bogie: pivot offset.**
   - The pivot is on the bogie's longitudinal axis, about *w*/3 from the axle farther from the vehicle end: "pair of bogie wheels more distant form the vehicle end" [S EP claim 2].
   - So it sits *w*/6 from the bogie centre, toward the car centre [D].
   - The body sits on an asymmetric cradle, cantilevered over the secondary springs. Its bearing carries the moment of that eccentric load [S patent].
   - Purpose: less lateral swing of the bogie's wheels relative to the body, so seats can stand over the outer wheels [S patent]. cs.wiki notes the wheels nearer the car end swing out much more when the bogie turns.
   - The bearing allows the bogie to turn fully under the body [S en.wiki, citing Škoda].
5. **Support points per body [D, from items 2 and 4].** Let *x_e* be the end bogie centre and *x_J1*, *x_J2* the Jacobs bogie centres.
   - End section S1 rests on two points: *x_e* + *w*/6 (end bogie pivot) and *x_J1* − *w*/2 (over the near axle of B2).
   - Middle section S2 rests on *x_J1* + *w*/2 and *x_J2* − *w*/2.
   - Every support point lies on the bogie centreline. At a Jacobs bogie it lies exactly over an axle centre, so it stays on the track centreline in curves.
   - In plan, each body is the chord between its two support points. On a vertical curve, its pitch is the slope between their heights.
   - Neighbouring sections meet through a "link" of length *w*: the Jacobs bogie frame, which follows the rails. There is no common articulation point.
6. **Angles.**
   - en.wiki lists the Jacobs bogies as "pivoting Jacobs (25°)" without saying what the 25° measures.
   - The patent gives no yaw limit for the invention. Its "about 3°" is for the prior-art non-pivoting design.
   - Floor over the bogies rises from 350 to 450 mm with a passage about 700 mm wide [S de.wiki]. Passage widths are 100 % of standard over the middle bogies and about 70 % over the end bogies [S patent].
7. **Not found.** *w*; the absolute positions; yaw stops or the largest yaw angle between a section and its cradle; the damper layout.

## 8. Joint pitch across types

| type | pitch at joints | basis |
|---|---|---|
| KT8D5 / R.N2P / N | free: each body rests on two bogie pivots; the shared pin lets the bodies pitch independently. Relative roll limited by clearance (if CS260915B1 applies). | [S layout] + [D] |
| K2 | free: each body rests on an end bogie and the middle bogie | [S layout] + [D] |
| KT4 | **stiff in pitch and roll**: floor and roof hinges on one vertical axis; the car pitches as one body on two pivots | [S ru.wiki, uncited section] + [D] |
| 15T | free: no joint; each body on two pivots; the cradle tie rod allows rotation about the transverse axis | [S patent] |
| 14T | [?]. Statics require both joints of each suspended section (2, 4) to allow pitch, because sections 1, 3, 5 are each held level on their own fixed bogie | [D] |
| 52T | [?]. The end-car saddle joints (1–2, 4–5) must allow pitch; joints 2–3 and 3–4 [?] | [D] |

For multi-articulated cars as a class (14T, 52T), de.wiki *Multigelenkwagen* says the split between pitch-movable and pitch-stiff joints is not fixed for the class and differs between designs, so the per-type answer needs the manufacturer's drawings.
https://de.wikipedia.org/wiki/Multigelenkwagen

## 9. Curve radii

- **Horizontal.**
  - 15T: 18 m [S de.wiki]; en.wiki 18 m / 15 m.
  - 14T: 25 m / 20 m [S en.wiki, values not explained].
  - KT8D5, K2, KT4, 52T: [?].
  - Context: a University of Pardubice paper (via search snippet) calls 20 m the usual smallest radius on Brno's tram network and 18 m exceptional (depots). It computes bogie yaw angles at those radii for several tram types.
- **Vertical (crest and sag).** Not found for any type.

## 10. Coupling summary

| type | couplers | Prague practice | protrusion per end |
|---|---|---|---|
| KT8D5 / R.N2P | both ends (bidirectional) | coupled pairs ran in 1993 and 2010 [S cs.wiki] | about 0.47 / 0.52 m [D] |
| 14T | [?] | [?] | [?] |
| 15T | emergency removable coupler with Prague hook head, fitted in parts by hand [S] | towing a failed car; "krab" device for prototypes [S] | none permanent |
| 52T | [?] | [?] | 31.99 m is over bumpers |
| K2 | Prague-type coupler [S de.wiki] | heritage car | about 0.55 m [D] |
| KT4 | both ends [S] | multiple working in Potsdam [S] | about 0.47 m [D] |

Coupler pivot positions: not found for any type.

## 11. Documents not downloaded (likely to hold the missing positions)

| document | URL | size |
|---|---|---|
| DPP driver textbook, Škoda 15T ForCity Alfa (2015) | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_15t.pdf | 1.84 MB |
| DPP driver textbook, Škoda 14T | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_14t.pdf | 0.61 MB |
| DPP driver textbook, KT8D5R.N2P | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/ucebnice_kt8d5rn2p.pdf | 0.25 MB |
| DPP test questions, technical, 52T (2026) | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_52t_20260201.pdf | 0.23 MB |
| DPP test questions, technical, KT8D5 (2026) | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/testy_d1_4_technicka_priprava_kt8d5_20260201.pdf | 0.06 MB |
| DPP regulation D 1/2 (probably the towing rules) | https://www.prazsketramvaje.cz/obrazky/stahuj/testy/predpis_d1-2_20260201.pdf | 1.35 MB |
| Škoda product sheet, ForCity Alfa Praha (side-view drawing likely) | https://admin.skodagroup.com/wp-content/uploads/2023/04/TRAMVAJ-FORCITY-ALFA-PRAHA_Produktovy-list_skoda_A3_A4_CZ_EN.pdf | 3.81 MB |
| Škoda product sheet, ForCity Alfa Riga | https://admin.skodagroup.com/wp-content/uploads/2023/04/TRAMVAJ-FORCITY-ALFA-RIGA_Produktovy-list_Skoda_A3_A4_CZ_EN.pdf | 3.96 MB |
| Hofman, Schienenfahrzeugtagung 2014, MiV06 (VDV classes: pivoting / conditionally pivoting / non-pivoting) | https://www.schienenfahrzeugtagung.at/download/PDF2014/MiV06-Hofman.pdf | 1.97 MB |
| DPP technical annex "Tramvaj Tatra K2" (the car 7000 purchase) | https://www.praha.eu/file/3555191/Priloha___Tramvaj_Tatra_K2_.pdf | unknown (certificate error) |
| Škoda 15T presentation, SDP 2008 (floor and passage over the bogies) | http://www.sdp-cr.cz/skup/OSTRAM/prezentace/05_2008/15T20080515SDP.pdf | unknown |
| Univ. Pardubice paper, bogie yaw at 18/20 m radii | https://dk.upce.cz/bitstreams/35ecbc6a-9812-46ab-a4b1-cc60a2fd9646/download | unknown |
| J. Vik, bachelor thesis, ZČU (has a 15T bogie chapter; server was down) | https://dspace.zcu.cz/bitstream/11025/25276/1/BP-Jiri_Vik_kompletni.pdf | unknown |
| MVB Typenblatt KT4D | https://www.mvbnet.de/files/2021/05/2021_mvb_typenblaetter-fahrzeuge_KT4d.pdf | unknown |
| Book: I. Köhler, *KT4 – Der Kurzgelenkwagen aus Prag*, GVE 2009 (KT4 joint linkage) | n/a | n/a |

## 12. ForCity Plus: 29T, 30T and 52T (second research run, 2026-11-18)

The maintainer (2026-11-18): the 52T's development is said to come from Bratislava's trams of a similar construction.

Read-only web research, 2026-11-18. Tags: [S] stated by the cited source, [D] derived (arithmetic shown),
[E] my estimate, [?] not found. No PDFs were opened. The ones that look worth opening are listed at the end
with their sizes from HEAD requests.

### Bottom line

- **No public source gives section lengths, bogie pivot positions, wheelbases, a pivot limit, a minimum
  horizontal radius or vertical radii for the 29T, 30T or 52T.** Every source found gives only the overall
  length, width, wheel diameter (52T) and how each bogie turns. All figures below that are tagged [E] are my
  estimates.
- **Layout (all three types).** Five sections and four bogies. The end sections 1 and 5 are saddled: each
  rests on one bogie under its outer part, and its inner end rests on the joint to section 2 or 4. Sections 2
  and 4 are short bogie sections. Section 3 floats between them and has no bogie.
  [S] de.wikipedia, *Škoda ForCity*, ForCity Plus section: https://de.wikipedia.org/wiki/%C5%A0koda_ForCity
  It describes the floating middle section as a "freischwebendes Mittelteil (Sänfte)".
  The 52T's short sections 2 and 4 are also [S] in Railvolution:
  https://www.railvolution.net/news/skoda-presented-first-52t-tram-for-praha
- **29T/30T inner bogies.** Most sources say they do not pivot. One source says they pivot a limited amount.
  - Non-pivoting: [S] prazsketramvaje.cz says "Krajní podvozky jsou otočné, vnitřní neotočné."
    https://www.prazsketramvaje.cz/view.php?cisloclanku=2015080401
  - Non-pivoting: [S] de.wikipedia says the middle car bodies run on "nicht ausdrehbaren Laufwerken".
  - Non-pivoting: [S] cs.wikipedia *Tramvaje Škoda* defines ForCity Plus as a combination of pivoting and
    fixed ("pevných") bogies. https://cs.wikipedia.org/wiki/Tramvaje_%C5%A0koda
  - Limited pivoting: [S] railway-technology.com calls the two inner bogies "limitedly pivotable" (one powered,
    one trailing). https://www.railway-technology.com/?p=16793
  - [E] Both descriptions can be true: the bogie is fixed in yaw but has some elastic yaw give through its
    secondary suspension and stops.
- **52T inner bogies: partially pivoting.**
  - [S] DPP press release: "dvěma částečně otočnými podvozky pod vnitřními podvozkovými články".
    https://www.dpp.cz/spolecnost/pro-media/tiskove-zpravy/detail/278_2449-nove-tramvaje-pro-prahu-odhaleny-v-hlavnim-meste-zacnou-za-necele-dva-roky-jezdit-prvni-vozy-skoda-forcity-plus-praha-52t
  - [S] Urban Transport Magazine (German edition): "teilweise schwenkbaren Drehgestellen unter den inneren
    Fahrwerksgliedern".
    https://www.urban-transport-magazine.com/neue-strassenbahnen-fuer-prag-enthuellt-forcity-plus-52t/
  - [S] Railvolution: "limited pivotability".
  - The first press report in January 2024 still called them fixed. [S] ČT24 (10 Jan 2024): "krajní otočné a
    prostřední pevné".
    https://ct24.ceskatelevize.cz/clanek/regiony/nove-prazske-tramvaje-52t-budou-nizkopodlazni-s-peti-clanky-prvni-prijdou-napresrok-344822
  - All later Škoda and DPP texts say partially pivoting.
- **Are the 52T inner bogies the 29T/30T inner bogies? No, it is a different design.** [D] from five facts:
  1. The gauges differ: 1435 mm for the 52T, 1000 mm for the 29T/30T.
  2. The 52T bogie frames come from the ForCity Smart trams for Ostrava, Plzeň and Brno (39T, 40T, 45T), not
     from Bratislava. [S] DPP press release: "Podvozkové rámy jsou převzaty z tramvají ForCity Smart pro
     Ostravu, Plzeň a Brno". [S] de.wikipedia *Škoda 52T*: https://de.wikipedia.org/wiki/%C5%A0koda_52T
  3. All four 52T bogies are motored. The 29T/30T has one unpowered inner bogie.
  4. The 52T is 100% low-floor with no step over any bogie. On the 29T/30T, the inner-section seats stand on
     platforms.
  5. fdrive.cz calls the 52T inner bogies "special", the end bogies "běžné" (standard).
     https://fdrive.cz/clanky/praha-se-po-16-letech-docka-novych-tramvaji-umeji-samy-brzdit-pred-prekazkou-11795
  - Only the body concept was taken from Bratislava. [S] DPP press release: "inspirací byla pětičlánková
    tramvaj ForCity Plus pro Bratislavu".
- **52T turning limit and mechanism: [?].** Nothing published gives the angle, whether springs, stops or
  rubber restore the bogie, or a VDV class. No Škoda patent on a partially pivoting bogie was found; the
  patents found are listed under "Patents".
- **Other ForCity Plus types.** Only the 29T, 30T (with their batches 29T3 and 30T3) and the 52T have this
  layout.
  - The FCB types 46T (Frankfurt/Oder), 47T (Cottbus) and 48T (Brandenburg) are ForCity Plus but have three
    sections, two radial bogies and one non-radial bogie, and are 70% low-floor. [S] de.wikipedia
    *Škoda ForCity*; Railway Gazette search snippet. de.wikipedia's overview table gives them 28.96 m.
  - The 26T (Miskolc) is ForCity Classic, with fixed bogies and 100% low floor. [S] cs.wikipedia
    *Tramvaje Škoda*.
  - The 40T (Plzeň) is ForCity Smart: three sections, four pivoting bogies, 29 m. [S] technickytydenik.cz,
    via a search snippet.
  - No "33T" tram exists. 33Tr is a trolleybus.

### Škoda 29T (single-ended) and 30T (double-ended), Bratislava, 1000 mm gauge

**Vehicle**

| item | value | tag / source |
|---|---|---|
| sections | 5, named from the cab end A, C01, D, C02, B | [S] prazsketramvaje.cz |
| length | 32,495 mm without couplers | [S] https://imhd.sk/ba/popis-typu-vozidla/743/%C5%A0koda-29T-ForCity-Plus, https://imhd.sk/ba/popis-typu-vozidla/740/%C5%A0koda-30T-ForCity-Plus, sk.wikipedia |
| width, height, floor | 2,480 mm; 3,560 mm; 350 mm | [S] imhd.sk |
| low-floor share | 29T 87%, 30T 89% (prazsketramvaje.cz); 30T 92% (Škoda, Rolling Stock World) | [S] sources differ |
| raised floor | only over the end bogies, which hide under the floor behind the cabs | [S] prazsketramvaje.cz photo captions |
| inner-section seats | on platforms one step above the aisle | [S] de.wikipedia *Škoda ForCity* |
| section lengths A, C01, D, C02, B | not published | [?] |
| section lengths, estimate | A = B ≈ 10.5 m, C01 = C02 ≈ 3.0 m, D ≈ 5.5 m | [E] from door and bogie layout; check: 10.5·2 + 3.0·2 + 5.5 = 32.5 |

**Bogies**

| bogie | under | turns | powered | position from the front | wheelbase | wheel diameter |
|---|---|---|---|---|---|---|
| 1 | A | free ("plne otočné") [S imhd.sk] | yes [S] | ≈3.0 m [E] | ≈1.8 m [E] | 620 mm new, 540 mm worn [S, imhd.sk reader comment only, https://imhd.sk/ba/doc/sk/23204/] |
| 2 | C01 | not pivoting [S prazsketramvaje.cz, de.wikipedia]; "limitedly pivotable" [S railway-technology.com] | one of bogies 2/3 is powered, which one [?] | ≈ middle of C01, about 12 m [E] | ≈1.8 m [E] | as bogie 1 |
| 3 | C02 | as bogie 2 | the other of bogies 2/3 is unpowered [S] | ≈20.5 m [E] | ≈1.8 m [E] | as bogie 1 |
| 4 | B | free [S] | yes [S] | ≈29.5 m [E] | ≈1.8 m [E] | as bogie 1 |

- Three of the four bogies are motored ("Tři podvozky jsou motorové, jeden běžný", prazsketramvaje.cz):
  6 × 100 kW, two motors per motored bogie [S] imhd.sk.
- The pantograph is on the second section (C01) [S] prazsketramvaje.cz. That suggests C01's bogie is the
  powered inner one, but this is unconfirmed [E].
- The 1.8 m wheelbase is [E]. The only Škoda figure found is 1,800 mm for the ForCity Classic Bergamo bogie,
  seen in a search snippet. A PRORAIL 2023 paper puts city tram bogies at 1,900 mm or less.
- de.wikipedia says the ForCity Plus types use classic wheelsets with through axles. It does not say which
  bogies. With a low aisle between the inner-section platforms, independent wheels or cranked axles are
  likelier on bogies 2 and 3 [E].
- Origins:
  - The middle chain C01–D–C02 is arranged like a ForCity Classic. [S] Škoda reference page, quoted in a
    search snippet (the page itself would not render): "arrangement of inner components and bogies are similar
    to the ForCity Classic". https://www.skodagroup.com/reference/tramcar-forcity-plus-bratislava
  - The design is "based on 15T ForCity Alfa and 26T ForCity Classic" [S] prazsketramvaje.cz, and on the
    Miskolc 26T [S] railway-technology.com.

**Joints**

| joint | between | carries | yaw | pitch | roll |
|---|---|---|---|---|---|
| J1 | A–C01 | inner end of A, which is saddled on C01 [S de.wikipedia] | free [E] | free [E] | [?] |
| J2 | C01–D | D, which floats [S de.wikipedia] | free [E] | one of J2/J3 is stiff, the other free [E] | constrained at one of J2/J3 at least [E] |
| J3 | D–C02 | D | free [E] | see J2 [E] | see J2 [E] |
| J4 | C02–B | inner end of B | free [E] | free [E] | [?] |

- Joint positions: one at each section boundary, ≈10.5 / 13.5 / 19.0 / 22.0 m from the front [E].
- The only published joint detail is that the joints have gangway bellows and turntable floor plates.
  [S] imhd.sk: "kĺbovými spojmi, ktoré vybavili prechodovými mechmi s točňami".
- None of the freedoms are published. The [E] values are the arrangement needed to keep the chain statically
  determinate.

**Curve radii and couplers**

- Smallest horizontal radius: [?]. Crest and sag radii: [?].
- Couplers at both ends: covered, folding, "Prague-type" couplers [S] imhd.sk. They are mounted under the cab
  floor at the front ends and are normally folded behind the front cover [S] prazsketramvaje.cz.
- [E] As folding couplers, they are deployed by hand.
- Coupler pivot positions: [?].

**29T versus 30T**

- The 29T has five double doors on the right side and no second cab: section B has seats where the 30T has a
  cab.
- The 30T has five doors on each side and two cabs.
- [S] prazsketramvaje.cz. Running gear is the same as far as the sources say. For the 29T3 and 30T3 batches
  (2022–24), no source reports a change in running gear [?]. One imhd.sk reader says they have
  "2 neotočne podvozky".

### Škoda 52T, Prague, 1435 mm gauge

**Vehicle**

| item | value | tag / source |
|---|---|---|
| sections | 5, single-ended, 100% low floor, no step even over the bogies | [S] DPP press release; cs.wikipedia |
| length | 31,990 mm over bumpers | [S] DPP; UTM; en.wikipedia text. The en.wikipedia infobox says 31.8 m, which conflicts. |
| width; floor | 2,500 mm; 350 mm | [S] DPP |
| doors | 5 double doors with 1,300 mm clear width: two in each end section between its bogie and the joint, one in section 3 | [S] de.wikipedia *Škoda 52T*; cs.wikipedia (doors in sections 1, 3, 5) |
| sections 2 and 4 | short, no doors | [S] Railvolution ("two short sections"); [D] from the door layout |
| joints | short, wider than before | [S] DPP: "krátkými, širšími a prostornými klouby" |
| section lengths | not published | [?] |
| section lengths, estimate | 1 = 5 ≈ 10.5 m, 2 = 4 ≈ 2.8 m, 3 ≈ 5.4 m | [E]; check: 10.5·2 + 2.8·2 + 5.4 = 32.0 |
| difference from the 29T/30T | 0.505 m shorter | [D] 32.495 − 31.990 = 0.505 m. Part of this may come from the different length definitions (without couplers vs over bumpers). |

[E] How the section estimate was built, for section 1 from the front:

- cab ≈ 1.8 m
- bogie zone ≈ 2.5 m (1.8 m wheelbase plus a 0.64 m wheel)
- first door ≈ 1.5 m
- window bay ≈ 3 m
- second door ≈ 1.5 m
- end bay ≈ 0.5 m

That totals ≈ 10.8 m. Section 3 is one door plus two seat bays. The short sections take what is left of the
31.99 m.

**Bogies**

| bogie | under | turns | powered | position from the front | wheelbase | wheel diameter |
|---|---|---|---|---|---|---|
| 1 | section 1 | free ("volně otočné", "běžné") [S DPP; fdrive.cz] | yes, both axles [S] | ≈3.0 m [E] | [?], ≈1.8 m [E] | 640 mm new [S DPP, Railvolution, UTM] |
| 2 | section 2 | partially pivoting ("částečně otočné", "limited pivotability", "special") [S DPP; Railvolution; fdrive.cz]. Angle and mechanism [?] | yes [S] | middle of section 2, ≈11.9 m [E] | [?] | 640 mm [S] |
| 3 | section 4 | as bogie 2 | yes [S] | ≈20.1 m [E] | [?] | 640 mm [S] |
| 4 | section 5 | free [S] | yes [S] | ≈29.0 m [E] | [?] | 640 mm [S] |

- All eight axles are powered, and all bogies have wheelsets with axles. [S] Railvolution: "all with
  wheelsets with axles". de.wikipedia gives Bo'Bo'Bo'Bo' and 8 × 100 kW.
- Each motor drives the pair of wheels on one side of its bogie. [S] cs.wikipedia, via a fetch summary.
- The motor type comes from the FCB trams [S] DPP. The bogie frames come from the ForCity Smart 39T, 40T and
  45T [S] DPP and de.wikipedia.
- On those ForCity Smart trams all bogies pivot. The Brno 45T has three sections, with two bogies under the
  middle section and one under each end section. [S] fdrive.cz and technickytydenik.cz, via search snippets.

**Joints**

| joint | between | carries | yaw | pitch | roll |
|---|---|---|---|---|---|
| J1 | 1–2 | inner end of section 1, which is saddled [S de.wikipedia *Škoda 52T*: "aufgesattelten Endwagen (jeweils auf einem Drehgestell)"] | free [E] | free [E] | [?] |
| J2 | 2–3 | floating section 3 [S de.wikipedia: "eines fahrwerkslos dazwischen eingehängt"] | free [E] | one of J2/J3 is stiff [E] | constrained at one of J2/J3 at least [E] |
| J3 | 3–4 | section 3 | free [E] | see J2 [E] | see J2 [E] |
| J4 | 4–5 | inner end of section 5 | free [E] | free [E] | [?] |

- Joint positions: ≈10.5 / 13.3 / 18.7 / 21.5 m from the front [E], from the section estimate.
- None of the 52T joint freedoms are published.

**Turning angles, radii and couplers**

- 52T pivot limit of the inner bogies: [?].
- [D] End bogie yaw against section 1: about 11–12° in a 20 m curve, about 12° at 18 m.
  - This uses a = 7.5 m [E], the distance from the bogie pivot to J1, with both points on the track centreline.
  - Body chord against the tangent at the pivot = asin(a / 2R).
  - R = 20 m: asin(7.5 / 40) = 10.8°. R = 18 m: asin(7.5 / 36) = 12.0°. R = 25 m: 8.6°.
  - For comparison, a 2006 ČVUT utility model for an end-section pivoting tram bogie states about ±12° body
    rotation, and ±15° for classic tram bogies. [S] https://patents.google.com/patent/CZ16360U1/cs
    It is not a ForCity design.
- [D] For an inner bogie fixed in yaw at the middle of a short section (half-length 1.4 m [E]), each joint at
  R = 20 m sits 1.4² / (2·20) = 0.049 m outside the track centreline. A partial pivot would let the bogie
  follow the track instead of the section.
- Smallest horizontal radius: [?]. Crest and sag radii: [?].
- Couplers: [?]. Nothing found on whether the 52T has couplers at both ends, how they are deployed, or where
  they pivot.
- Context only, other networks:
  - The Ostrava 39T tender required a 20 m radius (contract annex on smlouvy.gov.cz, search snippet).
  - In Brno the smallest standard radius is 20 m, and 18 m in depots (PRORAIL 2023 paper, search snippet).

### Patents (searched; none covers the ForCity Plus partial pivot)

- **EP1741610 / CZ297213** (Škoda Transportation and VÚKV, priority 2005): low-floor articulated tram with
  rotatable end bogies. https://patents.google.com/patent/EP1741610A3/en
- **EP2020355** (VÚKV, 2007): low bogie with a downward-cranked axle, with a pivoting and a non-pivoting
  variant.
- **CZ304298** (ČKD, 1998): bogie fixed in yaw, with limited rotation through a Z-mechanism.
- **CZ16360U1** (ČVUT, 2006): pivoting traction bogie for partly low-floor trams, about ±12°.
- None of these is tied to the 29T, 30T or 52T, and none gives a restoring torque. A search of the Czech
  patent office (UPV) by owner "Škoda Transportation" was not possible with these tools.

### Documents not opened (URL, title, size from HEAD)

1. https://www.prazsketramvaje.cz/clanky/29t_prospekt.pdf
   - Škoda 29T ForCity Plus brochure, 731,333 B, dated 2015-08-04.
   - A search snippet attributes the "limitedly pivotable inner bogies" wording to it.
   - May contain a side view.
2. https://www.prazsketramvaje.cz/clanky/30t_prospekt.pdf
   - 30T brochure, 512,994 B.
3. https://www.prazsketramvaje.cz/clanky/29t+30t_prospekt.pdf
   - 29T+30T catalogue, 1,101,363 B.
4. https://admin.skodagroup.com/wp-content/uploads/2023/04/TRAMVAJ-FORCITY-SMART-BRATISLAVA_Produktovy-list_Skoda_A3_A4_CZ_EN.pdf
   - Škoda product sheet for the Bratislava ForCity Plus, despite "SMART" in the file name. 3,055,325 B.
   - Its snippets say "koncové podvozky jsou plně otočné" and mention "basic technical parameters".
   - The best candidate for a dimensioned side view and a radius figure.
5. https://admin.skodagroup.com/wp-content/uploads/2023/03/Skoda-catalogue-City-EN.pdf
   - Škoda City catalogue, 16,831,396 B. The Czech version (…City-CZ.pdf) is 16,825,215 B.
6. https://wikibus.blob.core.windows.net/sources5121/S%CC%8Ckoda%20trams.pdf
   - "Škoda trams", origin unknown, 31,257,615 B.
7. https://dk.upce.cz/bitstreams/35ecbc6a-9812-46ab-a4b1-cc60a2fd9646/download
   - PRORAIL 2023 paper with a table of bogie yaw angles in 18 m and 20 m curves per tram type. Size unknown:
     the HEAD request got no answer.
8. https://spkv.upce.cz/index.php/spkv/article/download/2655/2402/5782
   - 2025 Česká Třebová paper on active wheelset steering for articulated trams with non-pivoting bogies, in
     a Škoda context.
   - The site is behind a bot wall (Anubis). Not bypassed.
9. https://www.opii.gov.sk/ckfinder/userfiles/files/Obnova%20vozoveho%20parku%20elektriciek%20BA%20-%20Studia%20realizovatelnosti_v_3.docx
   - Bratislava fleet-renewal feasibility study, 5,365,873 B. May state the DPB tender's curve requirements.
   - Related: https://www.opii.gov.sk/download/b/zamery/21RV/1_dpb_elektricky_pre_bratislavu.pdf, 902,668 B.
10. Not online: the print magazine articles de.wikipedia cites for the ForCity Plus design.
    - H. Hondius, *stadtverkehr* 1-2/2021.
    - S. Göbel, *stadtverkehr* 5/2024, pp. 30–36.

A practical route to the missing lengths: measure a perpendicular side photo of a 52T or 30T, using the
1,300 mm door clear width or the 640 mm / 620 mm wheel as scale.

### Source notes

- skodagroup.com pages render only with JavaScript. Their content here comes from search-engine snippets.
- Wikipedia (cs/de/en) refused or reset connections at times; the pages that did load are cited above.
- railwaynews.net (https://railwaynews.net/?p=237764) reads as machine-generated text and was not used as
  evidence.
- No page contained instructions aimed at AI tools. AI-related text was only site interface:
  - the wikiwand page title "Loading AI tools";
  - an "AI a MCP server" navigation link on hlidacstatu.cz;
  - spkv.upce.cz's bot-protection wall.

## 13. The 14T and the 52T measured on pictures, and the best guesses (2026-11-18)

The maintainer (2026-11-18), on the open questions: no further information; a best guess for each, from all the material found so far. The pictures and documents are kept in `raw/reference/` (`photos/52t/`, `photos/14t/`, `skoda/`), listed in its `SOURCES.md`.

**The 52T, measured on the side view the maintainer sent** (DPP's render of the livery, both sides, 1778 × 1000; `photos/52t/user-52t-sides.jpg`):
- The upper view: the cab at the right, its end at x 1615, the rear end at 169. 1,446 px = 31.99 m over the bumpers, 22.1 mm a pixel.
- Positions from the cab end, m [M, ±0.1; a bogie's middle is its fairing's]:

  | element | from the cab end | from the rear end (mirrored) | used |
  |---|---|---|---|
  | front end bogie | 2.23 | 2.28 | 2.25 |
  | joint 1 (bellows' middle) | 9.36 | 9.40 | 9.38 |
  | inner bogie under section 2 | 11.52 | 11.60 | 11.56 |
  | joint 2 | 13.69 | 13.74 | 13.72 |

  The rest are mirrored about the middle.
- Section lengths: the end sections 9.38 m each, the bogie sections 4.34 m each (their bogie in the middle), the carried section 4.55 m (with the middle double door).
- The wheelbase does not show (the bogies are covered): 1.8 m [E].
- Škoda's City catalogue (2023, `skoda/skoda-catalogue-city-en.pdf`, the Prague page) words the layout: two swivel bogies under the outermost sections and two partially swivelling ones under the inner sections. Its joints are "short, wide and spacious", without steps.
- The 29T/30T brochures (2015) call the Bratislava cars' inner bogies "omezeně otočné" / "limitedly pivotable"; neither they nor the catalogue give an angle.

**The 14T, measured on DPP's photo of car 9160** (`photos/14t/dpp-2840-mhd-tram-885a_01.webp`, 894 × 596, nearly side-on in perspective):
- Method: along the car's side, a point's position is an affine function of (x − 447) / h. Here x is its column, 447 the image's middle, and h the height between the upper and the lower red stripe there. h was fitted along the side as 136.0 − 0.0869 x (212 columns, worst residual 9 px).
- Scale: section 1's bogie, its wheels 1.88 m apart (the sister 19T's wheelbase, pl.wikipedia), measured from the nose.
- Measured [M, ±0.3 m near the front, ±0.5 m further]:
  - section 1: its wheels at 3.18 and 5.06 m;
  - joints at 6.35, 12.55, 16.86 and 23.22 m;
  - section 3's wheels at 13.59 and 15.38 m.
- Check: section 3's wheelbase comes out 1.78 m against 1.88, so the far side reads about 5 % short.
- Made symmetric about the middle of the 30.25 m body [E]:
  - section 1: 0 – 6.35 m, its fixed bogie at 4.12 m;
  - sections 2 and 4: 6.62 m each, carried;
  - section 3: 12.97 – 17.28 m, its fixed bogie at 15.13 m;
  - section 5: mirrored.

**Best guesses** (as asked above):

| question | guess | why |
|---|---|---|
| the 52T's inner bogies' largest turn | 5° (0.087 rad) | They are "partially" or "limitedly" pivotable. That is more than the ~3° the 2005 patent gives for designs called non-pivoting, and well under the ~12° an end section's bogie needs on 18 m (ČVUT utility model CZ16360U1). A bogie in the middle of a 4.3 m section needs little: the section is nearly the chord between its joints. |
| the KT4's rod ratio | 0.5 | The two halves are equal and the bow-tie plates symmetric. 0.5 keeps the joint over the track centreline, which the rods are there for ("limits overhang in curves"). |
| the KT4's springs' threshold (`steerFrom`) | 0.05 rad (~3°) of the bogies' relative turn | "Only at a larger turn of the bogies" (a KT4 driver, k-report.net, 2023-10-11). The joint stays straight on curves wider than ~180 m (8.9 m / 0.05) and steers in street curves (20–50 m: 0.18–0.45 rad). |
| the 52T's and 14T's wheelbases | 1.8 m and 1.88 m | The 52T's bogie frames come from the ForCity Smart (DPP); Škoda's figure seen for a ForCity bogie is 1.8 m. The 14T has the 19T's (its sister, same length). |
