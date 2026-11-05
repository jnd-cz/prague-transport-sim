# OSM2World: roads, junctions, kerbs and footways (#15)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT. Paths below are
under `core/src/main/java/org/osm2world/`. Our side: main at 595514a. Feeds #16 (networks) and #276
(the ground built offline) where the survey has no street.

## What OSM2World does

**One object per way segment** (`world/modules/RoadModule.java`, `applyTo`). Every node-to-node segment of
a highway way is a `Road`; a highway area is a `RoadArea`. Per node: 3+ roads make a `RoadJunction`; two
roads and `highway=crossing` a `RoadCrossingAtConnector`; two roads of different width a `RoadConnector`;
otherwise nothing is drawn at the node and the two segments are mitred.

**Cross-section as lanes** (`Road.buildBasicLaneLayout`, `LaneLayout`, `LaneType`). A road is a list of
lanes left and right of the centre: vehicle lanes, dividers (lines are 0.1 m lanes of their own), cycle
lanes (1.5 m, red on asphalt), bus bays, a `KERB` lane (0.15 m) and a `SIDEWALK` lane (1.0 m) per side.
- Vehicle lanes: `lanes:forward`/`lanes:backward`, or per-lane tags (`*:lanes`, `*:lanes:forward`,
  split on `|`, `getPerLaneTags`; an inconsistent count drops them all), else `lanes`, else a default by
  class (`getDefaultLanes`: 1 for paths, links, service, residential, living_street, pedestrian; 2 for
  motorway and other two-way roads). An odd total puts the extra lane in the way's forward direction.
- Sidewalk lanes only from `sidewalk=left|right|both` on the road; `sidewalk:*:width` etc. are passed
  to the lane by prefix (`getTagsWithPrefix`). `sidewalk=separate` gives no lane.
- Centre divider: dashed by default; `divider=solid_line|dashed_line|no`; solid when `overtaking`
  forbids both directions; none with `lane_markings=no` or an unpaved surface (earth, gravel, ice,
  pebblestone, rock, sand, snow). Dashed dividers between lanes of one direction.

**Width** (`Road.calculateWidth`, `estimateVehicleLanesWidth`), in this order:
1. the sum of the lane widths when every lane has one (`width:lanes`, `sidewalk:left:width` …);
2. `width`;
3. with `lanes`/`lanes:*`/`divider` tagged: the lanes at their defaults, 3.5 m per vehicle lane;
4. otherwise the special lanes plus a guess for the carriageway: path 1.0, track 2.5, service 3.5
   (parking aisle 2.8), primary/secondary 7.0, motorway 8.75, one-way 3.5, anything else 4.0 m.

`LaneLayout.setCalculatedValues` gives the lanes without a width an equal share of what is left; when the
known widths exceed the road, those lanes get 1 m and everything is scaled down to fit.

**Kerbs** (`KERB` lane type): a horizontal strip and, if raised, a vertical face; the sidewalk lane sits
on top (heights accumulate outward). Height from `kerb` (`sidewalk:<side>:kerb`, `sidewalk:both:kerb`):
0.12 m by default, 0.03 m `lowered`/`rolled`, 0 `flush`, no kerb lane for `kerb=no`. (Lines 1059-1061
read `sidewalk:left:kerb` for the right side: a slip not to copy.) Kerb nodes (`barrier=kerb`) are not read.

**Bends between two segments** (`world/network/NetworkCalculator.calculateConnectorNodeEffects`): the cut
across both ends runs along the angle bisector (`out − in`, normalised), each side at half its own width:
a mitre with no cap. A sharp bend makes the outline clockwise and the segment is marked `broken` and not
drawn (`AbstractNetworkWaySegmentWorldObject.calculateXZGeometry`).

**Junction areas** (`NetworkCalculator.calculateJunctionNodeEffects`, `JunctionNodeWorldObject`):
1. the segments at the node, sorted by angle (`MapNode.sortLinesByAngle`);
2. for each neighbouring pair, the left edge line of one (centre ± half width) intersected with the right
   edge line of the next; pairs within 10° of straight-through (`PARALLEL_ROAD_THRESHOLD_ANGLE = π/18`)
   give no point;
3. per segment, the node and the two neighbouring intersections are projected onto its centre line; the
   one farthest back from the node is where the segment ends;
4. the segment end is a square cut there, ± half width; the junction polygon runs through the cut ends
   and the intersection points between them (points closer than 1 cm merged).

The corners are straight lines from cut end to edge intersection: no kerb radius. The junction surface
takes the node's `surface`, else the majority of the roads weighted 100 (roads), 10 (service), 1 (paths).
Sidewalk and kerb lanes of neighbouring roads are joined across the junction as straight quads between
their end points (`buildLaneConnections`, LOD2 and up): a chamfered corner. Footways meeting a road at a
junction are a `TODO` in the source (comment after `RoadJunction`).

**Lane matching** (`findMatchingLanes`) at connectors and junctions: lanes of the same type paired from the
inside out (connectors only, so a motorway exit keeps its through lanes), then from the outside in
(sidewalks); a junction of one-way roads only (a split or merge) pairs the inbound lanes left to right
with the outbound ones (`buildLaneConnections_allOneway`). Lanes left over get no connection (`TODO`).

**Crossings** (`RoadCrossingAtConnector`): a strip across the road at the node, `width` long or 3.0 m.
Marking from `crossing:markings`, else `zebra` for `crossing=zebra` or `crossing_ref=zebra`, none for
`crossing=unmarked`, plain marks otherwise. Only sidewalk and kerb lanes continue across it.

**Turn arrows** from `turn` per lane (`addTurnArrows`), on lane pieces over 4 m, not on motorways.

**Overlaps with other ground** (`world/data/WorldObject.getGroundFootprint`, `getOverlapPriority`): an area
on the ground subtracts the footprints of overlapping ground objects of higher priority (polygon
difference, `CAGUtil.subtractPolygons`). Priorities: road segments and junctions `MAX_VALUE` (never cut),
highway areas 50 (`RoadArea`), parking 30, surfaces with a tag 20 (`SurfaceAreaModule`), implied surfaces
10, ballast around rails 5, default terrain `MIN_VALUE`. Road ribbons themselves overlap each other freely.

**Heights of a road** (`AbstractNetworkWaySegmentWorldObject.defineEleConstraints`, `Road`): level across;
`incline` as a minimum or maximum gradient (0.5-1.1x the tagged value, `up`/`down` 10 %); roads without
`incline` within ±35 %; smoothness over consecutive segments. (The elevation solver is the terrain note's.)

**Texture coordinates** (`GLOBAL_X_Z`): world x/z divided by the texture size, so asphalt and paving run on
without seams across segments, connectors and junctions; markings use `STRIP_FIT_HEIGHT` along the strip.

`area:highway` is only declared an area key (`osm/ruleset/HardcodedRuleset.java`); nothing draws it.

## What we do

- **Export** (`tools/build_line.py`, the roads block after `widths = {…}`): each highway way within 200 m
  of the route as a centre line with `w` from a class table (primary 12 … footway 2.5 m), raised to
  `lanes` × 3.2 m; flags `f` (footway, pedestrian, living_street), `c` (public car road), `z` (a marked
  `footway=crossing`), `b`, `t`, `o`, `ln`/`lf`/`lb`, `n`. `width`, `sidewalk*`, `turn:lanes`, `surface`,
  `kerb` and `area:highway` are not read; `area=yes` ways are skipped.
- **Drawing** (`src/world.js`): `widenTramStreets` adds 3.2 m per track to a road along tracks;
  `addRibbon` mitres bends with the width scale capped at 2; roads are drawn widest first, each a separate
  ribbon, overlapping at junctions (no junction area); footways 4 cm over roads (lift 0.16 vs 0.12 m).
  Where the survey has the street (`uncoveredRuns`), the OSM ribbon is not drawn. `buildZebras`: 0.5 m bars
  every metre, 3 m long, none on the tracks, also across the nearest road at OSM signalled crossings.
- **The survey** (`tools/dtm.py`, `tools/kerbs.py`, lines 17 and 22): carriageway, sidewalk, island and
  platform areas with kerbs at 0.10 m (the measured median, `KERB`), faces only where they meet the road.
- **Cars** (`src/traffic.js` `_buildLanes`, `connector`): a lane per direction (two on wide one-ways),
  trimmed min(5 m, 20 %) back from each end, cubic Hermite connectors between lane ends.

**Measured for this note** (scratch script over `data/` and `raw/osm/praha.osm.pbf`, 2026-11-05):

| line | route | OSM car roads within 60 m | outside the survey | footways etc. | way ends shared by 3+ ways |
|---|---|---|---|---|---|
| 17 | 21.8 km | 70.6 km | 2 % | 70.7 km | 487 |
| 22 | 18.4 km | 60.0 km | 1 % | 84.0 km | 536 |
| 23 | 8.3 km | 21.6 km | 100 % (no survey) | 37.3 km | 247 |
| 37 | 9.5 km | 34.1 km | 100 % | 33.5 km | 213 |
| 9 | 28.5 km | 67.4 km | 100 % | 90.2 km | 591 |

Tagging in the Prague extract (87 217 car-class ways incl. 33 693 service): `lanes` 26 %, `turn:lanes`
3.5 %, `width` 2.3 %, `width:lanes` 43 ways, `divider` 15; `sidewalk` 7 322, `sidewalk:both|left|right`
4 202 / 4 402 / 4 492; separately mapped `footway=sidewalk` 17 802 ways and `footway=crossing` 14 419;
`area:highway` 2 000 polygons, of them 893 footway, 439 traffic_island, 373 service and 130 carriageway
classes; kerb nodes: `barrier=kerb` 7 499, `kerb=lowered` 5 863, `flush` 1 440, `raised` 1 139.

So on lines 23, 37 and 9 every street is an OSM ribbon; Prague's sidewalks are mostly their own ways,
which OSM2World's lane model does not join to the road (they become 1 m paths beside it); `width` is rare,
so the class guess decides almost every carriageway; `area:highway` does not cover the streets.

## Ideas: take or not

1. **Junction areas from neighbouring edge intersections** (steps 1-4 above). **Take, reimplement** in a
   build tool (shapely, our widths): the streets outside the survey get one polygon per junction and
   ribbons cut back to it, instead of overlapping ribbons. Add what OSM2World lacks: a kerb radius at each
   corner (a fillet between the two edge lines, its radius measured on the survey's junctions on lines 17
   and 22) and a check against the survey there (boundary distance of the OSM-built carriageway to the
   surveyed one, per junction). Its 10° parallel threshold and "farthest candidate" cut are worth keeping.
2. **Width precedence** (lane sum > `width` > lanes × lane width > class guess) and lane-based composition.
   **Take the order, not the constants**: 3.5 m lanes and the class guesses are generic; ours (3.2 m, the
   class table) are unmeasured too. Calibrate both on the surveyed carriageway widths of lines 17 and 22,
   split by class and `lanes`, before they build ground on lines 23, 37 and 9.
3. **Ground priorities with subtraction** (`getOverlapPriority`). **Take for #276** as the rule that makes
   "nothing drawn under anything else": survey > OSM street (junctions and ribbons) > track bed edits >
   building plots > terrain, each class cut by the ones above it. No new issue; a point in #276's design.
4. **Kerb heights from `kerb=*`** (0.12 / 0.03 / 0). **Take the tag mapping, our numbers**: 0.10 m
   measured; lowered kerbs at crossings from the 5 863 `kerb=lowered` nodes, in the survey's kerbs too
   (`tools/kerbs.py` raises every sidewalk edge by the same step today).
5. **Sidewalks as lanes of the road.** **Not taken**: in Prague they are separate ways. What we need and
   OSM2World does not do: a `footway=sidewalk` way beside a road becomes the strip from the road's kerb
   line to the footway's far edge, so road, kerb and sidewalk meet without a gap or an overlap.
6. **Lane matching and `turn:lanes`** for the car lane graph (inside-out for through lanes, outside-in,
   the one-way split rule). **Take as an idea** for #16 and #46; it is simulation work, after W2.
7. **Lane markings from the lane layout** (divider rules, 0.1 m lines; dashes from the style: 9 m period,
   0.3 m wide). **Take the rules** where the orthophoto pilot (`tools/ortho_lanes.py`) has no reading;
   the pilot reads dashes as 3 m on, 6 m off, the same period. Turn arrows from `turn:lanes`.
8. **Crossings**: our zebra rule already reads the same tags; OSM2World's 3.0 m default matches our bars.
   Nothing to take.
9. **World-space texture coordinates** for street surfaces. **Take when streets get textures** (assets).
10. **Mitred bends**: we do the same, with a cap; OSM2World drops a segment whose outline folds. Nothing
    to take.

Nothing here needs ported code: the junction step is ~150 lines of Java over its own data model. A close
translation into a tool would carry OSM2World's MIT notice in that file's header.

## Its assets for these topics

Materials are colours in `scene/material/DefaultMaterials.java` (ASPHALT, KERB, ROAD_MARKING*,
RED_ROAD_MARKING …); textures come from the separate repository
[OSM2World-default-style](https://github.com/tordanik/OSM2World-default-style) (`standard.properties`,
licence CC0-1.0 per its README and GitHub): asphalt `cc0textures/Asphalt010` (1.2 m), paving
`PavingStones072` (1 m), sett `PavingStones033` (1.5 m) from ambientCG (CC0); `KnerrKerb0001.png`
(1.6 × 0.2 m), `road_marking_dash.png`, `road_marking_crossing.png`, `road_arrow_*.png` (OSM Wiki texture
library, public domain per the README). Not checked file by file.
