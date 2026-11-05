# OSM2World: output formats, tiles and levels of detail (#15)

OSM2World read at commit `1d31c252cbef964b489a55e5fb8242ee253375b1` (2026-11-02), MIT. Paths below are
under `core/src/main/java/org/osm2world/` unless they start with `desktop/`. Our side: main at 595514a.
Feeds M3: #30 (preprocessed 500 m tiles) and #31 (streaming loader with a memory budget and LOD), and the
format question in #276.

## What OSM2World does

**Formats** (`output/`): glTF 2.0 as `.gltf` or `.glb` (`gltf/GltfOutput.java`, `GltfFlavor`), optionally
zipped or gzipped (`common/compression/Compression.java`); Cesium 3D Tiles (`tileset/`); Wavefront OBJ,
one file or split whenever a size threshold is reached (`obj/ObjOutput.java`, `obj/ObjMultiFileOutput.java`);
POV-Ray scenes (`povray/`); a statistics dump (`statistics/`). The OpenGL viewer and image rendering live in
other modules.

**One mesh pipeline for glTF** (`GltfOutput.writeJson`, steps in `scene/mesh/MeshStore.java`):
1. `FilterLod`: keep the meshes whose `LODRange` contains the requested level;
2. `ClipToBounds(bounds, splitTriangles = true)`: triangles crossing the boundary are cut to it, the cut
   vertices' normals, colours and texture coordinates interpolated;
3. `ConvertToTriangles(lod)`: curved and extruded geometry tessellated to a tolerance per level: 4.0, 1.0,
   0.20, 0.05, 0.01 m for LOD0-LOD4;
4. `EmulateTextureLayers`: one texture layer at LOD0-1, all layers above;
5. `MoveColorsToVertices`; `ReplaceTexturesWithAtlas` (for textures referenced, not embedded);
6. `MergeMeshes`: one mesh per material; with `keepOsmElements` off, merged across OSM elements too.

**Encoding** (`GltfOutput`): vertices welded on (position, normal, uv, colour) (`VertexKey`); indices
16-bit when they fit; `KHR_mesh_quantization` at LOD0-1 only: positions as int16 with one uniform scale,
`largest extent / (2 × 32 767)`, centred on the bounding box, undone by the root node's transform
(`PositionQuantization`: a uniform scale so renderers need not correct normals), normals as int8.
Textures embedded in the GLB, written beside it, or referenced by URL (`common/ResourceOutputSettings.java`).
Each OSM element can stay its own node with `extras` `osmId` and `osmTags`. Models placed many times
(trees, street furniture) are expanded into meshes per instance (`gltf/GltfModel.buildMeshes`): no
`EXT_mesh_gpu_instancing`.

**Levels of detail** (`scene/mesh/LevelOfDetail.java`, `LODRange.java`): five levels, LOD0 (coarsest) to
LOD4. Generators set the range of what they draw (`target.setCurrentLodRange`): a junction's surface
LOD0-4, the sidewalk and kerb pieces joining at it LOD2-4 (`RoadModule.RoadJunction`). A level is a filter
over the same scene, plus the tessellation tolerance and texture layers above: no mesh simplification.

**Tiles** (`desktop/.../console/commands/TilesetCommand.java`):
- Web Mercator tiles at zoom 15 (`ZOOM = 15`: 1 223 m at the equator, ~785 m square at Prague's latitude);
- each tile converted on its own from the OSM features that touch it (`OSMDataReaderView` with the tile),
  then clipped to the tile (`clipToBounds = true`), elements merged (`keepOsmElements = false`), quantization
  allowed;
- one GLB and one `tileset.json` per tile and level: `lod<n>/<zoom>/<x>/<y>.glb`;
  tiles converted in parallel; `--overwrite OLDER` skips a tile whose file is newer than the input;
- `--precompressedTiles`: `.glb.gz` on disk, referenced without `.gz`, the web server's rewrite serves it
  (`TilesetOutput.TRANSPARENT_COMPRESSION`).

**The tileset tree** (`output/tileset/TilesetTreeUtil.java`), written after the tiles because it reads
their actual bounds:
- per tile, a chain of its levels, each refining the one above (`refine: REPLACE`), with geometric errors
  32, 16, 8, 4, 2 m by level and 0 for the finest one present (`GEOMETRIC_ERROR_BY_LOD`);
- above them, a quadtree of empty tiles with geometric error `100 m × 2^(maxZoom − zoom)`, up to 4 levels per
  `tileset.json` file, the levels spread evenly over the files;
- explicit tiles, not implicit tiling: a `region` volume subdivides linearly in latitude while tile numbers
  follow Web Mercator, and explicit tiles carry the real content bounds;
- bounding regions from the content, min/max height included, propagated up: the client computes the
  screen-space error from the distance to the volume, and a loose volume loads a tile too early;
- the root transform is east-north-up to ECEF at the projection origin (`TilesetOutput.writeTilesetJson`).

A 3D Tiles client refines a tile when `geometricError × screenHeight / (2 × distance × tan(fov/2))`
exceeds its error budget (16 px by default in CesiumJS): with a 2 m error at 1080 px and 60° that is about
117 m, 32 m about 1.9 km.

## What we do

- **Now:** each line ships its sources (`data/lineN.json`, `.dtm.json`, `.fine.bin`, `.bld.bin`), and the page
  builds every mesh at load (`src/world.js`, `src/terrain.js`). `ChunkedGeometry` merges triangles per
  material into 350 m cells (`CELL`) so frustum culling skips far ones; no levels of detail for the world;
  the walkers have a near and a far GLB (`src/people.js`). Line 17: 13.5 MB gzip download, 656 MB of float32
  GPU buffers (`docs/history/PERF-ANALYSIS.md` §6), 28 s load (`docs/knowledge.md`).
- **The plan:** 500 m squares on the S-JTSK grid, vertices relative to each tile's SW corner, networks
  global with their meshes clipped at tile edges once in the build and the clip points written to both
  tiles, terrain levels on cells that divide 500 m (2, 4, 10, 20, 50 m) with skirts
  ([city frame and tiles](../../decisions/2026-10-29-city-frame-and-tiles.md) §6-7). PERF §6 measured a
  compact encoding (Uint16 positions at 1 cm, oct-encoded normals or none, palette colour index, welded
  vertices) and chose to ship decisions and edits; spread over 500 m tiles: median 0.19 MB, 90th
  percentile 0.89 MB, max 1.97 MB. #276 opens the format of the prebuilt ground (per area class,
  delta-encoded, brotli). `docs/architecture.md` §5: tiles ahead of the vehicle, a GPU memory budget,
  12-16 tiles at start.

## Ideas: take or not

1. **GLB with `KHR_mesh_quantization` as the container for tile meshes.** **Measure, then decide in #30.**
   It is the encoding PERF §6 sketched (int16 positions, int8 normals, welded vertices, 16-bit indices) in a
   standard file: Three.js's `GLTFLoader` (already loaded for the models) reads the extension, the
   accessors arrive as typed arrays ready for the GPU, and viewers and `gltf-transform` can open a tile. A
   Python writer needs only `json` and `struct`. With one uniform scale a 500 m tile quantizes to 7.6 mm.
   Against it: the height lookup, the class per triangle and the networks are not meshes (a class can be a
   primitive per class, a lookup can read the ground's accessors; the networks stay JSON). The measurement:
   line 17's prebuilt ground as GLB versus #276's delta-encoded format, raw and brotli.
2. **Levels as content filters** (`LODRange` per piece, one file per tile and level). **Take**: the build
   marks what each level keeps (kerb faces, markings, zebras, small furniture only near), terrain levels
   come from the grid cells the decision names; no generic mesh simplification. One file per level lets
   the loader fetch the coarse level first and the fine one when near.
3. **Switching by screen-space error from tight bounds** (geometric error per level, bounds from the content
   with min/max height). **Take the formula and the tight bounds** for #31; not the 3D Tiles tree: with a
   flat 500 m grid and a known camera (a driver's eye, a fog distance), a flat index of tiles with their
   bounds and per-level errors does it, and a 3D Tiles renderer would be a new dependency.
4. **Clipping by splitting triangles at the tile edge with interpolated attributes** (`ClipToBounds`).
   **Take the algorithm** for the tile cutter. **Not** its per-tile conversion: a tile built only from the
   features that touch it can differ from its neighbour wherever a shape depends on what lies beyond
   (junctions, heights). Our decision already builds once and cuts.
5. **Merging per material per tile, element identity optional.** We merge per material per 350 m cell
   already; the build keeps the ranges our checks need (`trackRanges`, `footwayRanges`) as a side table,
   as OSM2World keeps `extras`.
6. **Instances expanded into meshes.** **Not taken**: trees, poles and people are instanced in the page
   (`src/models.js`); a tile ships an instance table (model, position, rotation, scale), or
   `EXT_mesh_gpu_instancing` if tiles are GLB.
7. **Incremental tile builds** (`--overwrite OLDER`). **Take as an idea** for the tile build: skip a tile
   whose inputs are unchanged, keyed by the content hashes the data store already has, not file times.
8. **Precompressed files with transparent names.** Ours is #275 (brotli at deploy). Nothing to take.
9. **OBJ, POV-Ray, texture atlases, emulated texture layers.** Not needed now; atlases come back with
   street and facade textures (assets).

No code to port: the glTF writer and the tileset classes sit on OSM2World's scene model and its JSON
data classes; a GLB writer in Python is a short tool of our own.
