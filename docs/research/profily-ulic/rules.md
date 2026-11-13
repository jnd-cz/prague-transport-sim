# profily-ulic's rules for a carriageway (#553)

How [profily-ulic](https://github.com/barasoukup/profily-ulic) divides a carriageway, at commit `21aafe0`
(2026-11-13). Files are under `pilot/public/` unless named otherwise. Each rule says where it comes from and how
it was checked: an A/B over the orthophoto, with a person's verdict per cut.

## Order of the division (`derive.js` `splitRoadway`, :595)

The carriageway is one run of the technical map's road surface between two kerbs. The division works from the
kerbs inwards:

1. **Cars half on the kerb** (`parking:<side>=half_on_kerb`). The roadway half of the car comes first, as long
   as one lane of 2.5 m stays.
2. **Lane count.** As many lanes as OSM counts (`lanes`, `lanes:forward|backward`), at most as many as fit at
   2.5 m each (`MIN_LANE`), and at least one.
3. **Kerb strips,** while every lane keeps 2.5 m:
   - **Cycle lanes** (`cycleway:<side>=lane` 1.5 m; 1.75 m beside parallel parking, 2.0 m beside perpendicular,
     `BIKE_WIDTH` :549);
   - **OSM parking lanes** (`parking:<side>=lane|street_side`).
4. **Estimated parallel parking,** 2.0 m, where nothing else says so (§ 25 of act 361/2000 Sb., `LAW_LANE`,
   `LAW_RAIL` :579). Every one of these must hold:
   - **The law:** a parked car leaves 3 m free per direction (para. 3), and keeps 3.5 m from the nearest rail
     (para. 2). So a two-way street takes it from 8 m of roadway on one side and 10 m on both, a one-way street
     from 5 m and 7 m.
   - **Where:** residential and unclassified streets only (`PARK_GUESS` :575), outside the paid parking zones
     (TSK surveyed those), and not in a living street (§ 39).
   - **The kerb:** an outer kerb with a sidewalk or a building within 40 m. Not at a median, a tram bed or
     another roadway.
5. **Tracks in the roadway** (`tramLanes` :821). Each track axis gets a tram envelope of ±1.75 m (`TRAM_HALF`
   :15). That is IPR's *Manuál tvorby veřejných prostranství* ch. C.2: a two-track tram strip is 6.5 m at 3 m
   track spacing, 7 m at 3.5 m.
   - Envelopes closer than 2.5 m merge.
   - A gap of 2.5 m or more beside the tracks becomes car lanes of about 2.75 m.
   - A narrower gap goes to the tram, so the cars share it.
6. **Three kinds of tram** (`evaluation/pravidla-11-2026/ZPRAVA.md` § 2; the kind changed in 10 cuts and was
   right in 9):
   - `tramvaj_v_pruhu`: cars drive on the rails, because the counted lanes don't fit beside them;
   - `tramvaj_pruh`: a reserved lane level with the road. Every OSM lane fits beside the tracks (Národní,
     Spálená), with the envelope cut to ±1.5 m if needed;
   - `tramvaj`: a separate bed between kerbs, from the map's tram surface (MTVU 705) or tracks in grass.
7. **Driving lanes with a cap** (`LANE_CAP` :559, `LANE_CAP_CLASS` :569). A lane is at most:
   - 3.75 m on motorways, trunks and TSK's class MK I;
   - 4.5 m on residential, unclassified and service roads;
   - 4 m elsewhere.

   The rest, from 1 m (`KRAJNICE_MIN`), is a shoulder or hatched area at the kerbs, marked as an estimate. A
   divided road's carriageway has its shoulder only at the outer edge.
   - Measured on 100 Prague cuts: lanes over 4.6 m wide went from 27 cuts to 3.
   - A cap of 4 m for MK II and 4.5 m for MK IV was tried: it didn't help (1 better, 3 neither).
8. **Lane direction** comes from the nearest OSM axis inside the roadway, so both carriageways of a divided road
   are right. **Turns** come from `turn:lanes(:forward|:backward)`, with `slight_*` drawn as the turn.
9. **Bus lanes** count only where tagged `designated`. A `yes` in `psv:lanes` made three bus lanes on
   Strakonická where there is one (`evaluation/ZPRAVA.md`, code bug 2).
10. **Medians.** A guard rail line with a road axis on each side splits the carriageway with a 0.6 m median.
    Two one-way axes with the same name move the cut's centre between them.

## Parking strips

- **The sources, in order:**
  1. TSK's parking sections. These are polygons in the paid zones, one per stretch of kerb, with the stall count
     `PS_ZPS`. Layers 5–8 of the same service add deliveries, disabled and special stalls; layer 9 the no-parking
     sections.
  2. OSM's parking areas: `amenity=parking` with `parking=street_side|lane|on_kerb|half_on_kerb`.
  3. OSM's `parking:<side>` tags.
  4. The estimate above.
- **Orientation of a TSK section** (`orientFromStalls`, `derive.js` :272). Its mean depth is the area divided by
  its length:
  - from 4.9 m deep: perpendicular;
  - under 3 m: parallel;
  - in between, by the length per stall: under 3.4 m perpendicular, 3.4–4.8 m angled, more parallel.
  - Without a TSK section, the depth of the strip decides: up to 3.2 m parallel, up to 4.6 m angled, deeper
    perpendicular. An estimated perpendicular strip beside under 5 m of roadway becomes angled: a car enters a
    perpendicular stall from about 6 m, an angled one from 3.5 m (ČSN 73 6056).
- **On the kerb** (`on_kerb`, `half_on_kerb`, README "Stání na chodníku"): the car's strip is taken out of the
  sidewalk, or half out of it. At least 0.5 m of sidewalk stays.
- **Their no-parking sections are ignored** (the author, 2026-11-11). They are gaps of a few metres inside one
  stretch of parking: driveways, bins, trees between the stalls.

## Widths checked against the IPR manual (`rules.js`)

The warnings in the design view. Red is under the minimum, orange under the basic width:

| part | red under | orange under |
|---|---|---|
| sidewalk | 1.5 m | 2 m |
| lane | 2.5 m | 3 m |
| cycle lane | 1.5 / 1.75 / 2 m (by the parking beside it) | |
| parallel parking | 2 m | |
| perpendicular parking | 4.5 m | 5 m |
| two-track tram strip | 6.5 m | 7 m; 8 m with poles |

In Prague the lane widths go by TSK's class (ČSN 73 6110 groups; act 13/1997 Sb. can't tell rapid from collector
roads in MK I and II, so both are group B):

| class | red under | orange under |
|---|---|---|
| motorway | 3 m | 3.5 m |
| MK I, MK II, I/II roads | 3 m | |
| MK III | 2.75 m | 3 m |
| MK IV | 2.5 m | 2.75 m |

## Lane markings from the orthophoto (`lanes-ortho.js`, `evaluation/ortofoto/ZPRAVA.md`)

**What it does.** It reads a ±25 m crop around the cut (IPR 10 cm in Prague, ČÚZK 12.5 cm elsewhere):
1. On each carriageway, it finds the bright lines along the street, with one direction and one arc per
   carriageway. Lines are solid or dashed by their gaps.
2. It picks the set of lines whose gaps look like lanes: 2.5–4.75 m, up to 7.5 m at the edge for a shoulder or
   parking. The pick is a dynamic programme (`m5`, after Máttyus et al. 2016).
3. Lanes and shoulders are re-measured from that set. Where it doesn't fit (a lane under 2.3 m or over 5 m), the
   rules stay.

**Checked against people's labels** (the third round: three independent labellers, 56 roadways that could be
judged, 127 lines; two labellers agree on a line within 5 cm):

| | Prague, IPR summer 2024, 10 cm | Prague, IPR spring leaf-off 2025, 5 cm | ČÚZK 12.5 cm, Plzeň, Hradec, Ostrava |
|---|---|---|---|
| lines found (recall, `m5`) | 76 % | 45 % | 65–82 % |
| lines found that are real (precision) | 89 % | | 82–92 % |
| lane boundaries within 0.3 m, rules alone | 23 % | | 24–30 % |
| lane boundaries within 0.3 m, orthophoto | 90 % | | 70–80 % (Prague 53 %) |

The second round's labels came from the detector's own candidates and gave higher figures: 94 % / 91 % on the
summer flight, 66 % / 72 % on the spring one.

- **The map and the ortho line up as they are.** The median offset of the map against the orthophoto is
  0.1–0.25 m, about the labels' own error. Fitting the image to the kerbs made it worse.
- **Shadow is the main loss.** 46 % of the images couldn't be judged even by eye. The spring flight's low sun
  hurts more than its missing leaves help.
- **The lane count improves less than the positions:**
  - rules 52 % against ortho 51–53 % (117 roadways, prototype in the app);
  - the ortho misses faded lines and takes kerb-side lines for lane lines.
- **Shoulder surfaces and hatching from the image are not used.** Hatching is rare (1 roadway in 20), so 15 %
  false finds would make most reported hatching false.
- **Cars at the kerb were tried and left out:**
  - a pretrained YOLO11-OBB found 84 % of the strips with cars, 79 % precise;
  - the author left it out over the weights' AGPL licence, the DOTA training data's academic-only licence and
    the 3 MB download.
