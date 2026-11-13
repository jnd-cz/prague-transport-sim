# profily-ulic study (#553)

What [profily-ulic](https://github.com/barasoukup/profily-ulic) knows about a carriageway that we don't, and how
we would divide ours into lanes, parking, cycle and tram space, for drawing and for the cars. Read at commit
`21aafe0` (2026-11-13); our side at `main` d293388.

- **Licence:** its code is MIT (© 2026 Bára Soukupová), so code ported from it keeps that notice (ASSETS.md, as
  for OSM2World). Its vehicle and street art is Streetmix's (CC BY-SA 4.0) and is not for us.
- **The other note:** its rules with their numbers are in [rules.md](rules.md).

## Two pipelines

| | profily-ulic | ours |
|---|---|---|
| unit | one cut across a street, facade to facade, at a click; 15 m from junctions, 6 m from crossings | every street near a line, continuous, through junctions; built offline per line |
| surfaces | IPR's MTVU (701 road, 702 sidewalk, 703 cycle, 704 parking, 705 tram), queried live | the ZPS survey (OPL areas, KR lines) from the pinned snapshot; the same classes (`tools/dtm.py` `CLASSES`) |
| tracks | the technical map's track axes (code 55010), else OSM | DI's centrelines |
| lanes | OSM's count, split from the kerbs inwards: parking, cycle, tram envelopes, lanes capped by class, the rest a shoulder ([rules.md](rules.md)) | OSM's count (`src/traffic.js` `lanesOf` :127). A lane is a line 1.7 m in from the kerb, lanes 2.6–3.25 m apart (`laneOffset` :500). There is no width, no shoulder and no turn lane |
| parking | TSK's sections (stall count, kind), OSM's parking areas and tags, and an estimate by § 25 | none. The survey's `parking` class is drawn and trimmed off the carriageway's edge (`_fitRoad` :375), and nothing parks on it. The game's parked cars are random obstacles beside the track (`src/game.js` :1010) |
| road class | TSK's street sections (MK I–IV, motorway): the lane cap and the width warnings | OSM `highway` only |
| cycle, bus | OSM `cycleway:*`, `busway`, `bus:lanes`, `psv:lanes` | not read (`tools/build_line.py` reads only `lanes`, `lanes:forward`, `lanes:backward`, `oneway`; :1143) |
| markings | the orthophoto's lane lines, picked as a set whose gaps look like lanes | the pilot `tools/ortho_lanes.py` (one stretch, a report only, not in the build) |
| checking | 100 random cuts per city judged on the orthophoto by people; A/B per rule or source ([evaluation/ZPRAVA.md](https://github.com/barasoukup/profily-ulic/blob/21aafe0/evaluation/ZPRAVA.md)) | `tools/lint.js` `lanes-realistic` and the street bot (`src/streetbot.js`) check lanes against the survey; nothing against the paint |

**What it does not do: junctions.** It moves its cut out of them. Our cars need lanes into, through and out of
junctions (#301, #304, #33). On that it has nothing to teach.

Its first evaluation on 100 random Prague cuts (2026-11-06) found 51 right, 32 partly right and 17 wrong. The
gaps by impact were:
- **An even split of the carriageway into its lanes** (about 25 cuts): 4.5–8 m lanes that hide shoulders, bays
  and widenings. The fix is the class cap plus a shoulder.
- **Parking that neither TSK nor OSM knows** (about 10): it vanishes into a 6–7 m lane. The fix is the § 25
  estimate.
- **Divided streets** and the medians inside one surface.

That is where our cars stand today too.

## What its sources give our lines (measured 2026-11-13)

**TSK's parking sections.** These are open data on Geoportál Praha, CC BY 4.0, a download, no live query:
"Úseky parkování v zónách placeného stání", item `7cbfdf9f9d87418ba62b35762cd46ca7`, updated 2026-11-10.
- **In Prague:** 16,876 polygons with 168,452 stalls. By depth and stall count: 11,849 parallel, 3,642
  perpendicular, 1,296 angled.
- **Along our lines,** within 30 m of the route:

  | line | sections | stalls | kerb length | parallel / perpendicular / angled |
  |---|---|---|---|---|
  | 9 | 238 | 1,605 | 10.2 km | 199 / 23 / 13 |
  | 17 | 124 | 1,081 | 6.3 km | 98 / 19 / 6 |
  | 22 | 209 | 1,501 | 10.1 km | 190 / 12 / 5 |
  | 23 | 108 | 582 | 4.1 km | 93 / 8 / 6 |
  | 37 | 57 | 497 | 3.3 km | 53 / 2 / 2 |

- **The sections lie on the survey's `road`.** Of their area inside each line's survey corridor:

  | line | road | parking | sidewalk | outside the survey |
  |---|---|---|---|---|
  | 9 | 83.8 % | 4.6 % | 8.8 % | 2.3 % |
  | 17 | 81.4 % | 8.2 % | 7.4 % | 2.1 % |
  | 22 | 82.8 % | 4.2 % | 9.9 % | 2.8 % |
  | 23 | 89.3 % | 2.6 % | 5.5 % | 2.2 % |
  | 37 | 79.1 % | 4.9 % | 10.7 % | 4.1 % |

  The survey draws the carriageway kerb to kerb, parking lanes included. Its `parking` class is mostly off-street
  lots and bays. For example, Mánesova has parked cars along both kerbs and is one road area, kerb to kerb, in
  the survey.

  So our cars' lanes, 1.7 m from the kerb, run through the parked cars wherever a street has parking. The
  sidewalk share is cars on the kerb (`on_kerb`, `half_on_kerb`), or the sections drawn a little wide.
- **Not covered:** outside the paid zones there are no sections.
- **More of the same service, also open data:** reserved stalls for deliveries, disabled drivers and special
  use, and the no-parking sections.

**TSK's street sections with their class.** "Uliční úseky TSK včetně zatřídění komunikací", item
`1bbe08c6c9f44c70810957c5e10f22db`, updated 2026-07-13, CC BY 4.0. Along the lines, in km of section with that
class:

| line | MK I | MK II | MK III | MK IV |
|---|---|---|---|---|
| 9 | 20.9 | 10.1 | 1.6 | 0.7 |
| 17 | 21.7 | 5.4 | 1.9 | 0.7 |
| 22 | 22.3 | 6.5 | 0.6 | 0.3 |
| 23 | 6.0 | 3.1 | 0.7 | 0.0 |
| 37 | 15.0 | 0.4 | 0.1 | 1.4 |

Our trams run mostly along MK I, the main network: lanes of about 3.5 m by ČSN 73 6110, capped at 3.75 m in
profily-ulic's A/B.

**OSM's cross-section tags in our Prague extract** (`raw/osm/praha.osm.pbf`, 7,203 km of car roads; share of
that length tagged):

| tag | share |
|---|---|
| `lanes` | 32.7 % |
| `sidewalk*` | 22.1 % |
| `cycleway*` | 16.6 % |
| `parking:*` (the current scheme) | 4.1 % |
| `turn:lanes*` | 3.5 % |
| `width` | 3.0 % |
| `lanes:forward` / `lanes:backward` | 1.2 % |
| `bus:lanes`, `psv:lanes`, `busway` | 0.6 % |
| `width:lanes*` | 0.1 % |

- **`parking:<side>` values:** `no` 2,493, `lane` 681, `separate` 436, `yes` 221, `street_side` 114,
  `half_on_kerb` 56, `on_kerb` 35.
- **Parking areas:** OSM also has 10,186 `street_side` parking areas (bays), 1,080 `lane` and 68 on the kerb.
- **What follows:**
  - OSM tells the parking side of few streets, so TSK's sections are the parking source inside the zones.
  - `width` is too rare to divide by. The survey's kerbs give the width.

**The survey's own layers that we don't read:**
- **Medians** (`Dělící pás`, code 010000001503) and associated road areas (`Přidružená plocha pozemní komunikace`,
  010000032003). Our 17 districts have 390 and 828 of them. Neither is in `tools/dtm.py` `CLASSES` (:36), so the
  build drops them.
- **Internal divisions of a traffic area** (`Vnitřní členění dopravní plochy`, 010000032302, KR lines). Praha 2
  alone has 4,423 of them, 47.7 km, median 4.8 m long. Drawn over the areas, they are surface edges (gutters,
  paving strips, kerbside paving) and stall outlines on off-street lots. They are not lane lines.
- **No lane-marking layer.** profily-ulic looked in IPR's `dtmp` and `dop` services and found none either. Only
  the orthophoto has the paint.

How these were measured: scratch scripts outside the repository. The two TSK files were downloaded once; the
sections were sampled on a 0.5 m grid against each line's `data/lineN.dtm.json` level-0 areas; the OSM tags were
counted with pyosmium. Each ran through `tools/heavy.py`.

## How we would build the division

A build step after #512, whose stations along each car axis give the carriageway's half-widths from the survey.
At each station it writes the carriageway's strips from kerb to kerb, in profily-ulic's order but on our data:
1. **The extent.** The survey's kerbs: `road`, `tram` and `parking` areas, with medians and associated areas read
   (the class table above). A median splits the carriageway.
2. **The tram space.** DI's track axes ± a tram envelope of ±1.75 m (IPR's manual: 6.5 m for two tracks 3 m
   apart), where the tracks are not on a separate bed (the user's answer 3 below; a fact for `data/truth.json`).
   From the envelope and the counted lanes, the kind: a separate bed (the survey's `tram`), a reserved lane
   (every counted lane fits beside it), or shared (cars drive on the rails).

   Today this is one test in `laneOffset`: a band under 3.2 m puts the car on its own track.
3. **Parking strips,** from these sources in turn:
   1. TSK's sections where one meets the station's cross line: the side, the depth, the orientation from the
      depth and the stall count, and the kind (deliveries, disabled, special);
   2. OSM's parking areas and `parking:<side>` tags;
   3. profily-ulic's § 25 estimate outside the zones, logged as a heuristic (AGENTS.md: heuristics log what they
      decided) and measured on the calibration sample (the user's answer 2 below).

   Cars on the kerb take their strip out of the sidewalk.
4. **Cycle and bus lanes** from OSM: `cycleway:<side>=lane`, `busway`, and `bus:lanes` / `psv:lanes` only where
   `designated`.
5. **Driving lanes.** The count from OSM; at a junction's approach, `turn:lanes` (#304). The width is an even
   share of what is left, capped by TSK's class. The rest is a shoulder at the kerb, or at the outer edge of a
   divided road's carriageway.
6. **The paint, later.** Where the orthophoto shows a full set of lane lines, the boundaries move onto them:
   `tools/ortho_lanes.py` with profily-ulic's set selection (`m5`), calibrated on labelled stretches first (#309,
   #46). Against independent labels it found 76 % of the lines on IPR's summer 10 cm flight (89 % of them real)
   but 45 % on the spring leaf-off 5 cm one, for shadow. Our ortho source is IPR's leaf-off 2026 flight (`tools/sources.py` `ortho`), so the summer
   flight should be measured beside it.
7. **Along the street.** A strip keeps its offset from station to station, so a change is an event: a lane
   added, parking ending, a bay. Lanes taper over a set length instead of jumping.

**The output** is a sidecar, `data/lineN.lanes.json`. Per carriageway:
- the stations' strip boundaries;
- the lane centrelines with direction, kind, width and turn;
- the parking rows with stall positions and orientation.

**Who reads it:**
- **The drawing:**
  - the road paint (#309): solid and dashed lines from the strip boundaries, hatched shoulders;
  - the parking strips and bays as strips, with no cars, shown apart in `?review` and the F8 overlay (the
    user's answer 1 below).
- **The traffic** (#304, #32):
  - cars drive the built lane centrelines instead of `laneOffset`;
  - turn lanes come from `turn:lanes`;
  - parked cars are static obstacles outside the lanes;
  - the shared-tram flag comes from the division.
- **The checks:** `lanes-realistic` and the street bot's drive lines check the built lanes.

**Calibration before it holds** (AGENTS.md). Take a sample of stations per line, stratified by TSK class, drawn
over the orthophoto as a `?review` set. The answers are "right", "lane count wrong", "parking wrong",
"width off" and "tram kind wrong". They measure the rules, as profily-ulic's 100 cuts measured theirs, and they
measure each change as an A/B on the same sample.

## Not to take

- **Live queries per click,** its own MTVU cache and the national DMVS fallback. Our survey comes from the
  snapshot, and Prague is all we cover.
- **Streetmix's art** (CC BY-SA), the building floors (we have LOD2), the signs row, the water-management parts.
- **Car detection on the orthophoto,** for the reasons its author left it out (rules.md, the last section). A
  photo is one moment anyway; TSK's stalls say where cars may stand.
- **The cut's per-click geometry fixes** (snapping the cut, reach, edges). Our division is along the street.

## The user's answers (2026-11-13)

1. Parking: "only draw the strips and perhaps show them differently in review mode or debug overlay". There are
   no parked cars.
2. The § 25 estimate: "we can try to apply this rule and see how it holds up". It is measured on the calibration
   sample.
3. The tram envelope ±1.75 m: "if not sitting on separate track bed then we can go with that figure".
4. Where: "this can go to the issue and milestone where we start working with the network graph, which will be
   for trams, trains, cars+buses, pedestrians". That is #16 in M4.

## What became of the proposals

| proposal | where |
|---|---|
| Survey: medians and associated road areas read; a median splits the carriageway | #555 (W3) |
| Snapshot TSK's open data (parking sections, reserved stalls, no-parking, street classes) | in #556 |
| The carriageway's division: `data/lineN.lanes.json`, strips per station, the § 25 trial, the strips in `?review` and F8, a calibration sample | #556 (M4). Blocked by #512 and #555; blocks #16 |
| Parked cars on TSK's stalls | dropped (answer 1): strips only |
| The traffic drives the built lanes | #16's road lane graph, with #304's turn lanes |
| Lane paint from the orthophoto: set selection, the summer flight against the leaf-off one | a comment on #309 |
