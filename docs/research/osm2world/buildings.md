# OSM2World: buildings (#15, question 4)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT licence. Paths below are
under `core/src/main/java/org/osm2world/world/modules/building/` unless they start otherwise. Our side: main at
595514a. Feeds #55 (real types, facades, roofs), #199 (passages), #276 (building plots).

## What OSM2World does

**Model:** Simple 3D Buildings. A `Building` (`Building.java`) holds `BuildingPart`s (`BuildingPart.java`, 728 lines),
each with exterior walls (`ExteriorBuildingWall.java`), a roof (`roof/`), an optional bottom (`BuildingBottom.java`)
and, with `indoor=*` data, rooms, walls, floors and ceilings (`indoor/`).

**Defaults by type** (`BuildingDefaults.java`): 3 levels of 2.5 m, flat roof, windows, default wall and roof
materials; per `building=*` value: greenhouse (1 level, glass, no windows), garage (1 level, concrete), carport (no
walls), hut and shed (1 level), cabin (wood), roof (no walls), church, hangar and industrial (no windows);
`parking=multi-storey` 5 levels without windows; a chimney 1 level of 10 m in brick. A tagged flat roof is concrete.

**Heights** (`LevelAndHeightData.java`): `height`, `min_height`, `building:levels`, `building:min_level`,
`building:levels:underground`, `roof:levels`, per-level `height` from S3DB level data. Roof height: `roof:height`;
else `roof:angle` as tan(angle) × the largest distance of an outline vertex to the ridge
(`roof/RoofWithRidge.calculatePreliminaryHeight`); else `roof:levels` × 2.5 m; else a dome half its diameter, a
one-level building 1 m, anything else 5 m (`BuildingPart.DEFAULT_RIDGE_HEIGHT`). Total height defaults to levels ×
2.5 m + roof height.

**Roofs** (`roof/Roof.createRoofForShape`): flat, pyramidal, onion, skillion, saltbox, gabled, hipped, side_hipped,
half-hipped, side_half-hipped, gambrel, mansard, sawtooth, dome, round, cone, chimney, and `complex` (explicitly
mapped `roof:ridge` / `roof:edge` ways, `roof/ComplexRoof.java`).
- **Ridge** (`roof/RoofWithRidge.java`): direction from `roof:direction` (snapped to a direction parallel or
  orthogonal to an outline segment when within 45° for compass letters, 10° for whole degrees, 0.5° for decimals,
  `Roof.snapDirection`), else `roof:ridge:direction`, else `roof:orientation` (along / across the longest side of the
  minimum rotated bounding box). The ridge is the line through the centroid in that direction, clipped by the
  simplified outline; hipped roofs pull its ends in by 1/3 of the cap (`HippedRoof.RIDGE_OFFSET`), a saltbox puts it
  at 0.7 of the depth, mansard and gambrel break the slope at 1/3.
- **Faces** (`roof/HeightfieldRoof.java`, `roof/RoofWithInnerLines.java`): the outline is split into faces by the
  ridge and edge lines (`FaceDecompositionUtil.splitPolygonIntoFaces`, points snapped within 0.01 m), each face
  triangulated, each vertex lifted by the roof's height function; a point off the function takes the nearest
  outline segment's interpolated height. Rooftop objects attached to the roof are cut out of it.

**Walls and windows** (`ExteriorBuildingWall.java`, `WallSurface.java`, `WindowParameters.java`):
- a wall is one surface per outline segment and level range, in wall coordinates (u along, v up);
- default windows per level: columns = round(wall length / (2 × window width)), width 1 m, height 0.5 × the level
  height, breast 0.3 × the level height, centred in equal bays (`placeDefaultWindows`); placed only where they fit
  (`addElementsIfSpaceFree`); `window:*` tags override, with regions and pane layouts;
- **texture fitted in whole entities**: a texture that declares a width or height per entity (a window, a tile) gets
  max(1, round(wall length / entity width)) repeats along and max(1, round(wall height / entity height)) up, so a
  wall never ends in a cut window (`WallSurface.texCoords`);
- level of detail (`chooseWindowImplementations`): no windows at LOD0–1, the facade window texture
  (`BUILDING_WINDOWS` layered over the wall material) at LOD2–3, window geometry (`GeometryWindow.java`: frame, panes,
  recess) at LOD4; mapped windows switch one level earlier;
- materials from `building:material` / `building:colour` and `roof:material` / `roof:colour`
  (`BuildingPart.java` around line 566).

**Texture coordinates** (`scene/texcoord/`): `STRIP_WALL` for walls (u along the wall, v up); `SLOPED_TRIANGLES`
for roofs (each triangle's plan coordinates rotated by the plan angle of its normal, so the texture runs down the
slope; angles within 0.02 rad of one seen before reuse it, so one roof face stays seamless).

**Ground and passages:** the building's ground level is the lowest terrain height on its outline
(`Building.getGroundLevelEle`); the terrain is not cut under it (terrain.md). A `tunnel=building_passage` way, or a
road crossing a part whose floor is above the passage's clearance, is subtracted from that part's walls and floor;
the part over it is raised (`BuildingPart.java` lines 155–280).

**Textures and models:** none in this repository. They live in
[OSM2World-default-style](https://github.com/tordanik/OSM2World-default-style) (`README.md`); `CONTRIBUTING.md` asks
contributors to release textures and models there under CC0. That repository was not read; each file's terms are
checked before use.

## What we do

- **Source:** IPR Praha's LOD2 buildings (Budovy 3D, I3S mesh, absolute Bpv heights) and Mosty 3D bridges within
  220 m of the route, vertices quantised to 5 cm, 400 m chunks (`tools/geoportal.py` → `lineN.geo.json`,
  `lineN.bld.bin`). The roofs are the real shapes from the mesh. Fallback without them: OSM footprints extruded to
  `b.h` with a flat roof (`src/world.js` `buildOsmBuildings`).
- **Class per building** (`src/world.js` `buildingClass`): the OSM `building=*` under the centroid, the flat share of
  the roof, the height and the footprint area choose old / panel / church / industrial / glass.
- **Facades:** one procedural canvas texture per class, fixed tiles (old 3.5 × 3.2 m, panel 3.6 × 2.8, church 5 × 9,
  industrial 6 × 4, glass 1.5 × 3.6), u = position along the wall's plan direction / tile width, v from the
  building's lowest point + 0.4 m; colour per building from a palette (`facadeTexture`, `panelTexture`, …).
- **Roofs:** vertex colour only: flat (|n_z| > 0.97) grey, sloped one of three tile colours.
- **Ground:** vertices within 0.3 m of the mesh's lowest point sunk 2.5 m; a building the track passes under
  (within 2.5 m of the route) lifted to 6.3 m over the ground; OSM boxes from the lowest corner − 1 m, lifted 6.4 m.

Where we stand against OSM2World: our shapes and heights are measured, so its roof generator and height rules have
nothing to add near the track. What it has that we lack is the facade: storeys, bays fitted to each wall, types
with their own defaults, and texture laid along the roof slope.

## Ideas

| # | Idea | Take? | How |
|---|---|---|---|
| B1 | **A defaults table per building type** (levels, storey height, wall and roof material, windows or not) | **Take, keyed by RÚIAN** | Reimplement: RÚIAN's building record (use, number of storeys, construction) joined to each LOD2 building by footprint, a table in code from those codes to facade class, storey height and windows. Replaces the OSM-tag guess in `buildingClass`. A RÚIAN snapshot first (tools/sources.py, DATA.md). |
| B2 | **Facade texture in whole entities per wall** (`round(length / bay)` bays, `round(height / storey)` rows) | **Take** | Reimplement in `buildLod2`: group a building's vertical triangles into walls (same plan normal within a tolerance, same plane offset), give each wall u = along / (length / round(length / tile w)) from its own start, v = (z − wall base) / (height / storeys), storeys from B1 or round(h / tile h). No more windows cut at corners or floors that drift with the base. Offline in the build once the buildings are prebuilt. |
| B3 | **Window texture far, window geometry near** (LOD ranges per implementation) | **Later** | For M3 (#31's LOD): recessed windows only on facades within some tens of metres of the track. Not before B2. |
| B4 | **Roof shapes from tags** (19 shapes, ridge rules, 1/3 hip offsets, 5 m default) | **No** | IPR's LOD2 roofs are measured for all of Prague. Kept in mind only if a source without roof shapes is used (a tile beyond IPR's area). |
| B5 | **Building base on the ground** | **Take the opposite of OSM2World** | OSM2World uses the lowest outline height and leaves the terrain under the building. With #276 the footprint is a hole in the ground and the wall bottom follows the ground's heights along the footprint; the 2.5 m sink goes. Part of #276. |
| B6 | **Roof texture down the slope** (`SLOPED_TRIANGLES`, face angles merged within 0.02 rad) | **Take** | Reimplement for LOD2 roof triangles: uv = plan position rotated by −atan2(n_y, n_x), the angle shared by triangles of one face; a CC0 or own tile texture tinted by the current palette. |
| B7 | **Passages cut from walls and floor, the part above raised** | **Take as #199's design** | For LOD2 meshes: cut the passage footprint (OSM `tunnel=building_passage`, the survey's passage areas) out of the triangles below the clearance, instead of lifting the whole building. #199. |
| B8 | `building:colour`, `roof:colour`, `building:material` | **Later** | Where tagged, over the palette; part of B1. |
| B9 | Indoor (`indoor/`), doors, garage doors | **No** | The game does not enter buildings. |

Port of OSM2World code: none. The pieces worth having (entity fitting, slope rotation, the defaults table) are a
few lines each; they are reimplemented in our tools and `src/`, so no MIT notice is carried. Textures: none taken
from OSM2World until a file of the default style with a stated CC0 licence is chosen.
