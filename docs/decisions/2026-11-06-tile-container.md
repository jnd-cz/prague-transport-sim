# The tile container: integer differences, not GLB, for the ground (#307)

Status: picked on the measurements below (the user, 2026-11-05: "Try and see what's better"), open to the user's veto in PR #313.

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

What GLB would give and this gives up:
- a third less vertex memory (8 B against 12 B): 260 kB a tile, 26 MB for 100 tiles in memory. The decoder can write ushort itself later if memory matters;
- a standard file that opens in any viewer. A debug export can write GLB when someone wants one.

**Not measured:** the tile's objects. Buildings are already quantized binary (`lineN.bld.bin`) and models are GLB already; this decision is the ground's only, and #30 can keep GLB for objects.

The sizes are the terrain alone. The classes, levels and survey outlines #276 adds will move them, but the same way in both formats.
