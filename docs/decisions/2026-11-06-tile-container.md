# The tile container: integer differences, not GLB, for the ground (#307)

Status: accepted by the user (2026-11-06, PR #313, on the slower decode: "it can be loaded and decoded by separate thread to not slow down the playthrough when we do dynamic tile loading ... If yes then then go with it").

## Measured

`tools/bench/tile_container.py`: the greedy terrain mesh of one tile beside line 17's middle at the 10 cm tolerance ([the ground's decision](2026-11-05-ground-built-offline.md)), vertices row by row and triangles sorted the same way in both files. The page: fetched once, then decoded 15 times in headless Chromium (median); Three.js 0.160.

| 1,024 m tile: 129,380 triangles, 64,882 vertices | integer differences | GLB, `KHR_mesh_quantization` (ushort) |
|---|---|---|
| raw | 854 kB | 1,139 kB |
| gzip | 545 kB | 775 kB |
| **brotli** | **452 kB** (3.58 B/triangle) | 547 kB (4.33 B/triangle) |
| decode into a geometry | 5.2 ms | 1.4 ms (`GLTFLoader.parseAsync`) |
| normals computed | 11.1 ms | 9.9 ms |
| position error against the source | 0.5 cm in z (rounded to cm); x, y exact | 0.78 cm in x, y; 0.5 cm in z |
| vertex in memory | 12 B (`Float32Array`) | 6 B + 2 B padding (`Uint16Array`) |

On a 512 m tile (48,538 triangles): brotli 157 kB against 200 kB, x, y error 0.39 cm with GLB.

## The decision

**The ground's tiles use the integer differences** (#276's format; a decoder of ~30 lines, `tools/bench/tile_container.html`):
- **17 % smaller after brotli** (30 % after gzip): ~14 MB less for the whole city's 18.3 M terrain triangles;
- **exact shared vertices:** every position is whole centimetres in the city frame, so tiles and the classes in them weld exactly, and a cut kerb stays where the survey has it. GLB's ushort cannot hold a 1,024 m tile at 1 cm (the step is 1.6 cm), and each tile's own scale would round a shared border differently: it would need one lattice for all tiles;
- the decode's extra 4 ms a tile is nothing beside what it replaces (the 8 s flush and the rest, #244).

**The tiles are decoded in a worker.** The decoder and the normals need no Three.js and no page, and their arrays come back without a copy. Measured the same way (15 loads of the tile in the page's bench, a second run, where the page's own decode took 3.9 ms and its normals 7.8 ms):

| in a worker | |
|---|---|
| decode | 3.9 ms |
| normals | 3.5 ms |
| building the geometry on the page's thread | below the timer (< 0.1 ms) |
| the page's longest stall during all 15 loads | 4.4 ms |

Not measured: the upload to the GPU, which happens on the page's thread in any format, at the first draw of a tile (headless Chromium draws in software, so a number from it would say nothing). A tile's arrays are 778 kB of positions, 778 kB of normals and 1.55 MB of indices; #244's frame time check is where a hitch from it shows.

What GLB would give and this gives up:
- a third less vertex memory (8 B against 12 B): 260 kB a tile, 26 MB for 100 tiles in memory. The decoder can write ushort itself later if memory matters;
- a standard file that opens in any viewer. A debug export can write GLB when someone wants one.

**For #30's tiles:** the ground in integer differences; objects keep what they have, buildings as quantized binary (`lineN.bld.bin`) and models as GLB. The tile's objects were not measured against each other (the issue's step): neither of them changes format here, and #30 measures them if it wants one container.

The sizes are the terrain alone. The classes, levels and survey outlines #276 adds will move them, but the same way in both formats.
