# OSM2World: terrain and elevation (#15, question 2)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT licence. Paths below are
under `core/src/main/java/org/osm2world/` unless they start with a module name. Our side: main at 595514a.
Feeds #276 (one ground surface built offline).

## What OSM2World does

**Pipeline** (`O2WConverterImpl.java`, `runConversion`, `calculateElevations`, `attachConnectors`):

1. The world modules turn OSM elements into world objects. Each object lists its **elevation connectors**
   (`map_elevation/data/EleConnector.java`): a point in plan, an optional reference (a node, an intersection)
   and a ground state `ON`, `ABOVE`, `BELOW` or `ATTACHED` (`GroundState.java`). Connectors at the same position
   join when they share a reference or are both `ON` (`EleConnector.connectsTo`).
2. A **terrain interpolator** gives every connector the terrain height at its position from SRTM sites
   (`map_elevation/creation/SRTMData.java`, sites padded 10 m around the data bounds). Choices (`O2WConfig.terrainInterpolator`):
   `ZeroInterpolator` (the default: flat), `LinearInterpolator` (its own incremental Delaunay triangulation,
   `DelaunayTriangulation.java`, 834 lines, bounding box padded 100 m), `NaturalNeighborInterpolator` (the same
   triangulation's Voronoi dual), `InverseDistanceWeightingInterpolator`, `LeastSquaresInterpolator` (a polynomial
   per site fitted by QR to its 9 nearest sites, interpolated from the 29 nearest, 50 m index cells; commons-math3).
3. An **elevation calculator** refines the heights (`O2WConfig.eleCalculator`). The default is
   `BridgeTunnelEleCalculator`: a bridge at terrain + 0.1 m, a tunnel at terrain + 0. The alternative
   `ConstraintEleCalculator` lets every object declare constraints (`defineEleConstraints`) on an
   `EleConstraintEnforcer` (`EleConstraintEnforcer.java`): same height, vertical distance (MIN, MAX, EXACT) to a
   connector or a segment, incline along a sequence, smoothness over three connectors.
4. The only enforcer at this commit, `SimpleEleConstraintEnforcer.java`, keeps one kind: connectors required to be
   at the same height form **stiff sets** (merged like union-find) and take the **mean** terrain height of the set.
   Then every `ABOVE` connector goes up 5 m and every `BELOW` connector down 5 m. Vertical distance, incline and
   smoothness are empty methods (`// TODO`). The declared constraints still document the intent:
   - road cross-section: left, right and centre connectors at the same height
     (`world/network/AbstractNetworkWaySegmentWorldObject.java`);
   - `incline=N %`: between 0.5 × and 1.1 × the tagged grade; `up`/`down`: at least ±10 %; `0`: same height;
     smoothness over every three centreline connectors and across the joint to the previous segment (same file);
   - a road without `incline` at most ±35 % (`world/modules/RoadModule.java`, "the world's steepest residential street");
   - a bridge or tunnel at least a clearance above or below the ways and areas it crosses
     (`world/modules/common/BridgeOrTunnel.java`); a tunnel entrance's top exactly 10 m over its bottom
     (`world/modules/TunnelModule.java`); a surface area at least 1 m under a bridge, 10 m over a tunnel
     (`world/modules/SurfaceAreaModule.java`).
5. **Attachment** (`O2WConverterImpl.attachConnectors`): objects that stand on something (a rooftop pool, a
   bench on a bridge) carry attachment connectors with compatible surface types (`roof`, `floor1`, …); surfaces are
   indexed in 100 m cells; a connector takes the closest compatible surface in 3D, for roofs the topmost one within
   0.1 m of the nearest in plan, and its preferred height above that surface is held within 1 mm when a face allows it.

**How the terrain meets features: a partition, no carving.**

- Empty land is covered by fake areas: a 30 m point grid in patches of 10 × 10 points, each patch an area tagged
  `surface=osm2world:empty_terrain` (`map_data/creation/EmptyTerrainBuilder.java`, `POINT_GRID_DIST = 30`,
  `PATCH_SIZE_POINTS = 10`).
- Every object has an **overlap priority** (`world/data/WorldObject.java`): `MAX_VALUE` linear roads (the default),
  50 road areas, 30 distinct surfaces (car parking), 20 mapped surface or landcover, 10 implied surface (parks),
  5 implied surface around features (ballast), `MIN_VALUE` the empty terrain.
- An area's **ground footprint** is its outline minus the raw footprints of every overlapping object that is also
  `ON` the ground and has a higher priority (`WorldObject.getGroundFootprint`, JTS `difference` in
  `math/algorithms/CAGUtil.java`). Nothing is drawn under anything else on the same level. Bridges (`ABOVE`) and
  tunnels (`BELOW`) cut nothing.
- Buildings cut nothing: `Building.getRawGroundFootprint` is empty, so the terrain runs on under them, hidden. A
  building's ground level is the **minimum** height of its outline connectors (`Building.getGroundLevelEle`); walls
  start there.
- The footprints are triangulated with **earcut4j** (`math/algorithms/TriangulationUtil.java` →
  `Earcut4JTriangulationUtil.java`): ear clipping, edges kept, no Delaunay quality. Interior points (the 30 m grid
  inside a surface, `SurfaceAreaModule.getTriangulationXZ`) are disabled: "points are currently disabled - not only
  do they not work properly, they cause OutOfMemory errors". Each triangle vertex is an elevation connector
  (`EleConnectorGroup.addConnectorsForTriangulation`), so heights come per vertex from step 2–4.
- A conforming Delaunay triangulation with Steiner points exists (`JTSTriangulationUtil.java`, JTS
  `ConformingDelaunayTriangulationBuilder`, tolerance 0.01 m) and `Poly2TriTriangulationUtil.java`; neither is on
  the default path.

**Libraries** (`core/pom.xml`): JTS 1.19 (`jts-core`; EPL-2.0 or EDL-1.0), earcut4j 2.2.2 (ISC), poly2tri-core
0.1.2 (BSD-3-Clause), commons-math3 3.6.1 (Apache-2.0), trove4j 3.0.3 (LGPL-2.1), Guava (Apache-2.0).

## What we do

- **Terrain:** a 10 m grid per line, and 2 m blocks within 120 m of the tracks sampled from IPR's 1 m lidar, then
  DMR 5G, then the coarse grid (`tools/fine_terrain.py`; datum check 0.07 m; DMR 5G over passages where IPR drops
  more than `PASSAGE_DROP`).
- **Survey:** ZPS areas with a class and a level, heights from the 3D boundary lines (`tools/dtm.py`).
- **Track heights:** DI, the archive, then the surveyed deck plus a per-style offset, staged with flags
  (`tools/import_track_heights.py`, `tools/track_decks.py`); one meaning per height, top of rail
  (`docs/decisions/2026-10-29-what-each-height-means.md`); the profile solved to the ČSN design radius by ADMM with
  Tukey weights, junctions pinned (`tools/track_profile.py`, `docs/decisions/2026-11-02-vertical-profile.md`).
- **In the page:** the survey triangulated per area with three.js `ShapeUtils.triangulateShape` (earcut, as
  OSM2World), outlines cut to ≤ 4 m pieces so neighbours share points; streets pressed flush to the rails
  (`flushDtm`), the terrain lowered 0.25 m under the survey and the tracks, a corridor carved with benches and
  retaining walls (`carveCorridor`, `BENCH = 7`, `WALL_MIN = 1.5`) (`src/terrain.js`, `src/world.js`).
- **Buildings on the ground:** OSM boxes from the lowest terrain corner − 1 m; IPR LOD2 meshes at their absolute
  heights with vertices within 0.3 m of the lowest sunk 2.5 m (`src/world.js` `buildOsmBuildings`, `buildLod2`).

Where we stand against OSM2World: our heights come from 1–2 m lidar, a survey and track data at centimetres, not
from 30–90 m SRTM, so its interpolators and its ±5 m bridge/tunnel offsets have nothing to give. Its ground model
does: a partition by priority instead of layers drawn over each other and lowered.

## Ideas

| # | Idea | Take? | How |
|---|---|---|---|
| T1 | **Ground as a partition by priority**: each piece is its footprint minus the footprints of higher-priority pieces on the same level; the empty land fills what is left | **Take** | Reimplement in the #276 build tool with shapely (`difference`, `unary_union`). Our order: track bed > survey classes by `SURFACE_RANK` (`src/terrain.js`) > building plots > lidar terrain. Per level (`l` of the survey), so a deck or an underpass cuts nothing on level 0 (the Výtoň overlap). |
| T2 | **Constrained triangulation keeping every outline edge** | **Take, with shapely** | OSM2World's earcut keeps edges but has no quality and no interior points. shapely 2.1+ has `constrained_delaunay_triangles` (GEOS `ConstrainedDelaunayTriangulator`, GEOS ≥ 3.10): a polygon with holes, its edges kept, no Steiner points. Installed here: shapely 2.2.0, GEOS 3.14.1. Measured on line 17's survey (9,437 valid level-0 areas, 348,482 vertices): 334,932 triangles in 4.95 s, 0 of the boundary edges missing, no failure; the unconstrained `delaunay_triangles` on the same areas 0.47 s and 583,399 triangles that cross the edges. No new dependency. |
| T3 | **Interior height points in the terrain pieces** | **Take, differently** | OSM2World disabled its interior points (out of memory). The terrain left by T1 is cut by the lidar lattice instead (`intersection` with the 2 m or 1 m cells): a whole cell is two triangles at four lidar samples, a cut cell is triangulated by T2. Every lidar sample is a vertex, every kerb, bed edge and footprint is an edge, and no library needs interior points. |
| T4 | **Shared vertices welded to one height** (stiff sets) | **Take, not the mean** | Weld vertices by position and level (union-find over the noded outlines, `shapely.node`), so neighbouring pieces cannot open a seam. The height is chosen by priority (the track bed's profile, then the survey, then the lidar), not averaged: a mean moves a surveyed kerb towards the terrain. |
| T5 | **Declared constraints solved together** (vertical clearance, incline, smoothness) | **No** | Declared but not enforced at this commit. Our profile solver already enforces the curvature limit exactly; clearance belongs to the structures (#13, #54). |
| T6 | **Attachment surfaces by type** (roof, floor, deck; topmost roof; 1 mm height tolerance) | **Later** | For W4 placement on decks and platforms: the #276 ground keeps its level per triangle, so a lookup by (x, y, level) answers what attachment does. An idea for #252, not code. |
| T7 | Terrain interpolators (Delaunay linear, natural neighbour, IDW, least squares) | **No** | Built for sparse SRTM sites; we sample a 1 m raster. |
| T8 | Building ground level = lowest outline height, terrain under the building kept | **No** | #276 wants nothing under anything else. The footprint becomes a hole in the ground (T1), the wall bottoms follow the ground's heights along the footprint (a skirt from the ring down to the building's base), and the plot inside is not drawn. See buildings.md B5. |

## For #276's open decisions

- **Library:** shapely's `constrained_delaunay_triangles` (BSD-3-Clause; GEOS LGPL-2.1, both already used by the
  build tools). Alternatives looked at: `mapbox_earcut` (ISC; ear clipping as OSM2World and three.js, no quality),
  `triangle` (the wrapper LGPL-3.0; Shewchuk's Triangle itself is not free for commercial use), `PythonCDT` (MPL-2.0;
  takes interior points and edges in one call). None is needed once T3 cuts the terrain into cells.
- **Order of work in the tool:** node all outlines of a level → T1 priorities → T3 lattice cut of the terrain
  pieces → T2 per piece → T4 weld and heights → encode per class.
- **Check:** every source edge (kerb, bed edge, footprint) is an edge of the mesh, counted per class; no two
  triangles of one level overlap in plan.

Port of OSM2World code: none needed. Its algorithms here are short (priority subtraction, union-find of
connectors); the reimplementation is in Python over shapely, so no MIT notice is carried.
