# The tile container: integer differences, not GLB, for the ground and a tile's objects (#307)

Status:
- **The ground:** accepted by the user (2026-11-06, PR #313, on the slower decode: "it can be loaded and decoded by separate thread to not slow down the playthrough when we do dynamic tile loading ... If yes then then go with it").
- **A tile's objects:** accepted by the user (2026-11-06, PR #324: "yes integer differences for objects look really good as well, go for it and merge").

## The ground, measured

`tools/bench/tile_container.py`: the greedy terrain mesh of one tile beside line 17's middle at the 10 cm tolerance ([the ground's decision](2026-11-05-ground-built-offline.md)), vertices row by row and triangles sorted the same way in both files. The page: fetched once, then decoded 15 times in headless Chromium (median); Three.js 0.160.

| 1,024 m tile: 129,380 triangles, 64,882 vertices | integer differences | GLB, `KHR_mesh_quantization` (ushort) |
|---|---|---|
| raw | 854 kB | 1,266 kB |
| gzip | 545 kB | 788 kB |
| **brotli** | **452 kB** (3.58 B/triangle) | 548 kB (4.34 B/triangle) |
| decode into a geometry | 3.8 ms | 1.2 ms (`GLTFLoader.parseAsync`) |
| normals computed | 8.8 ms | 9.0 ms |
| position error against the source | 0.5 cm in z (rounded to cm); x, y exact | 0.78 cm in x, y; 0.5 cm in z |
| vertex in memory | 12 B (`Float32Array`) | 6 B + 2 B padding (`Uint16Array`) |

PR #313's GLB left out the 2 B of padding glTF requires (1,139 kB raw, 547 kB brotli); these numbers have it. On a 512 m tile (48,538 triangles, without the padding): brotli 157 kB against 200 kB, x, y error 0.39 cm with GLB.

**The ground's tiles use the integer differences** (#276's format; a decoder of ~30 lines, `tools/bench/tile_container.html`):
- **17 % smaller after brotli** (31 % after gzip): ~14 MB less for the whole city's 18.3 M terrain triangles;
- **exact shared vertices:** every position is whole centimetres in the city frame, so tiles and the classes in them weld exactly, and a cut kerb stays where the survey has it. GLB's ushort cannot hold a 1,024 m tile at 1 cm (the step is 1.6 cm), and each tile's own scale would round a shared border differently: it would need one lattice for all tiles;
- the decode's extra 3 ms a tile is nothing beside what it replaces (the 8 s flush and the rest, #244).

**The tiles are decoded in a worker.** The decoder and the normals need no Three.js and no page, and their arrays come back without a copy.

| in a worker, 15 loads of the tile | |
|---|---|
| decode | 3.9 ms |
| normals | 3.3 ms |
| building the geometry on the page's thread | below the timer (< 0.1 ms) |
| the page's longest stall during all 15 loads | 0.8 ms (4.4 ms in an earlier run) |

Not measured: the upload to the GPU, which happens on the page's thread in any format, at the first draw of a tile (headless Chromium draws in software, so a number from it would say nothing). A tile's arrays are 778 kB of positions, 778 kB of normals and 1.55 MB of indices; #244's frame time check is where a hitch from it shows.

What GLB would give and this gives up:
- a third less vertex memory (8 B against 12 B): 260 kB a tile, 26 MB for 100 tiles in memory. The decoder can write ushort itself later if memory matters;
- a standard file that opens in any viewer. A debug export can write GLB when someone wants one.

The sizes are the terrain alone. The classes, levels and survey outlines #276 adds will move them, but the same way in both formats.

## A tile's objects, measured

`tools/bench/object_container.py`: the objects of all five lines cut into 1,024 m tiles, each tile encoded every way and compressed on its own, the sizes summed. Every format stays on the data's own lattice, so none loses position: unlike the ground, GLB gives up nothing in accuracy here. The page checks that all formats give the same triangles, normals and per-building table (differences 0) on the densest tile.

**Buildings and bridges** (`lineN.bld.bin`, 5 cm), 1,828,599 triangles:

| all five lines | today's int16 triangles + JSON table | GLB, triangles | GLB, indexed | integer differences |
|---|---|---|---|---|
| raw | 32.3 MB | 43.1 MB | 18.9 MB | 9.7 MB |
| gzip | 8,681 kB | 9,001 kB | 9,707 kB | 6,579 kB |
| **brotli** | 6,927 kB | 6,737 kB | 7,294 kB | **5,889 kB** |

| brotli per line (kB) | 17 | 22 | 9 | 23 | 37 |
|---|---|---|---|---|---|
| today | 1,345 | 1,812 | 2,095 | 1,015 | 659 |
| GLB, triangles | 1,306 | 1,768 | 2,036 | 987 | 641 |
| GLB, indexed | 1,416 | 1,910 | 2,198 | 1,070 | 700 |
| integer differences | 1,132 | 1,530 | 1,790 | 893 | 544 |
| differences against GLB | -13 % | -13 % | -12 % | -10 % | -15 % |

| densest tile: 72,363 triangles, 446 buildings | today | GLB, triangles | GLB, indexed | integer differences |
|---|---|---|---|---|
| brotli | 267 kB | 260 kB | 285 kB | 241 kB |
| decode | 1.0 ms | 2.8 ms | 0.3 ms | 2.0 ms |
| flat normals, triangles expanded | 3.7 ms | 3.9 ms | 3.9 ms | 3.9 ms |

The differences in a worker on that tile: decode 2.3 ms, normals 4.0 ms, the page's longest stall during 15 loads 1.2 ms.

Indexing does not help GLB: it halves the raw file and grows the compressed one, since indices compress worse than repeated positions. Buildings end up as separate triangles with flat normals in every format (`src/world.js` `buildLod2`: per-face normals, a colour and uv per wall), so the memory after decoding is the same in all of them. A densest tile's flat triangles are 5.2 MB of positions and normals, more than a ground tile, and the upload above applies to them too.

**Trees and the other placed things** (`lineN.geo.json`, 10 cm), 44,383 of them:

| all five lines | today's JSON | GLB, `EXT_mesh_gpu_instancing` (float32) | integer differences |
|---|---|---|---|
| raw | 799 kB | 658 kB | 126 kB |
| gzip | 229 kB | 273 kB | 109 kB |
| **brotli** | 174 kB | 225 kB | **98 kB** |

Decoding the densest tile's 2,918 takes under 0.5 ms in all three. GLB's are float32 because a quantized instance needs a node scale that would also scale the mesh, and each kind needs a placeholder mesh the game does not draw.

**A tile's buildings and placed things use the integer differences:**
- smaller on every line: buildings 13 % smaller than GLB after brotli (10-15 % per line) and 27 % after gzip, placed things 56 % after brotli;
- **one format, one decoder, one worker** for everything in a tile, which matters more than the size: about 850 kB over these lines. GLB would add a second path, with `GLTFLoader` on the page's thread (not tried in a worker);
- the header needs the lattice per axis, as doubles (0.05 m in float32 turned a sliver triangle over), and the per-building table goes with the mesh. The ground's header gets the same fields: its lattice is 1 m, 1 m, 1 cm.

**Models stay GLB:** the tram and the people are shared assets with materials and skins, loaded once, not per tile. They were not part of this comparison.

**Not measured:**
- What the page works out per building on load: the class, wall uv and colour, lifting, sinking. Baked into the tile, they will add to the sizes, in either format; how much is for #30 to measure.
- Walls (9 on line 17, kept as outlines) and the furniture drawn from the line's data, whose placements have the same shape as the trees'.
- Sizes are per line, so a building on two lines counts twice.

## The frame and the lattice

**The frame stays [one city frame and its tile grid](2026-10-29-city-frame-and-tiles.md):** a fixed origin at the Marian column, vertices relative to their tile, the simulation in city coordinates (the user, 2026-11-06: "I agree that fixed origin and tile local geometry is fine for our purpose"). The 1,024 m tiles above are a size to measure on, not that record's 500 m grid; #30 decides the tile size.

**The ground is stored in 1 cm on every axis, not 1 mm.** Once the survey is cut into it, x and y need the survey's lattice too, not the 1 m of the bench above. Buildings keep the 5 cm they have.

- **The sources hold nothing finer:** the survey's coordinates are whole centimetres (all of 3.0 M plan values and 323 k heights in three districts' packages, up to 3,000 features per table), with stated accuracy of 0.14 m in plan and 0.12-0.35 m in height ([knowledge](../knowledge.md)). IPR's raster has more digits, but it is resampled and states no accuracy.
- **What 1 mm costs:** +5.5 % after brotli, 347 to 366 kB on one ground tile of 85,596 triangles.
- **Rounding moves a vertex by at most 5 mm, and every copy of it the same way,** so surfaces that share a vertex still meet exactly.

**Rails may be the exception, not measured:** independent rounding of ±5 mm could show as a wiggle a few metres from the cab, where a pixel is about 3 mm, and could change the gauge by up to 1 cm. If rail meshes go into tiles, they need their own lattice or section; the header holds the lattice, so the format allows it. The simulation's track stays in doubles either way.

i32 has room for either: at 1 mm the tile origin reaches ±2,147 km.
