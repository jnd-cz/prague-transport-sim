# Running gear of six Prague articulated tram types (research for #579)

Read-only web research by a research agent, 2026-11-18; nothing downloaded. Positions are x metres rearward from the front end of the body.

**Conventions.** `x` is metres rearward from the **front end of the body** (front body face). Where a length over couplers is known, the coupler face offset is given separately. Tags on every number:
- **[S]** stated by the cited source;
- **[D]** derived by me with arithmetic from stated figures plus the assumption named (usually: equal overhangs at both ends);
- **[E]** my estimate, low confidence;
- **[?]** not found.

**Bottom line.** For KT8D5, KT4 and (roughly) K2, the bogie positions follow from published pivot spacings. For 14T, 15T and 52T, no public HTML source gives section lengths or bogie positions. The DPP driver textbooks (PDF, listed at the end) are the most likely place to find them. The user's three recollections:
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

- **The bogies pivot.** The user remembered fixed KT4 bogies; the sources say otherwise.
  - en.wiki: with no bogie at the joint, the design "necessitates a scissor joint connecting both bogies".
  - ru.wiki: the joint is two hinges, one at the floor and one at the roof, both on one vertical axis. Rods between the bogies and both sections deflect the joint according to the relative bogie rotation, which keeps the car steady on straight track and limits overhang in curves. (The section carries uncited-source tags.)
  - strassenbahn-online: the steering mechanism for the middle joint was newly developed for the KT4.
- **Consequence for the solver [D].** Two hinges on one vertical axis allow yaw only. Vertically, the whole car behaves as one rigid beam on its two bogie pivots 8.9 m apart.
- **Not found.** Exact linkage geometry and ratio [?]; it is probably in I. Köhler, *KT4 – Der Kurzgelenkwagen aus Prag* (GVE 2009). Minimum radius [?]; vertical radii [?].
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
