# One city frame (S-JTSK) and the tile grid

**Date:** 2026-10-29
**Status:** agreed 2026-10-29 (issue #7), with the Marian column as the origin (user).

## Measured

- **Today's per-line frames** (one lat/lon origin per line, 110 574 m per degree of latitude and
  111 320·cos lat0 per degree of longitude): 0.59 % short north–south and 0.20 % east–west; line 17
  is 100 m short. Each line has its own origin, so two lines' worlds do not meet.
- **WGS 84 / ETRS89 → S-JTSK (EPSG:5514).** PROJ offers several operations. The best is ČÚZK's correction
  grid `cz_cuzk_table_-y-x_3_v1710.tif` (35 mm, 199 kB from cdn.proj.org; not in the default PROJ install).
  Against it, on a 2 km lattice over Prague:
  - what the tools use today (`Transformer.from_crs(4326, 5514)` → "S-JTSK to WGS 84 (5)"): shifted
    4–9 cm, varying 5 cm over the city: **today's conversions are good**;
  - "(1)": 14 cm; "(4)": 1.6 m; "(3)": 10.4 m. PROJ picks the operation by what is installed, so an
    unpinned call can silently move the world by metres on another computer or PROJ version.
- **S-JTSK distortion in Prague:** scale 0.999904 (−9.6 cm per km, varying 0.6 cm/km over the city):
  line 17 comes out 2.1 m short of its true length. Grid north and true north **differ by 7.8°** (meridian convergence −7.8°).
- **Prague in S-JTSK:** x −759 354 … −720 971 (38.4 km), y −1 062 047 … −1 030 838 (31.2 km).
  Staroměstské náměstí is at (−742 812, −1 043 017).
- **float32** (the GPU's precision): a step of 0.06 mm at 1 km, 1 mm at 10–16 km, 2 mm at 16–32 km,
  but 62–125 mm at S-JTSK's raw magnitudes (750 km, 1 050 km).

## Proposal

1. **Build frame: S-JTSK / Krovak East North (EPSG:5514) metres, heights Bpv (EPSG:8357).** This is native
   to DMR 5G, the IPR rasters, the DTM survey and Mosty, so no resampling of the survey data. x points
   east and y north, as in the game today.
2. **One pinned conversion** for everything non-native (OSM, GTFS, Geoportál's Web Mercator): ETRS89 →
   S-JTSK through the ČÚZK grid, as an explicit PROJ pipeline in `tools/geo.py`, with the grid file in
   the snapshot. Other operations are not allowed, so every computer builds the same world. OSM's WGS 84 is
   taken as ETRS89: the 2026 difference of ~0.9 m is within OSM's own accuracy, and the operation the
   tools use today treats it the same way (within 9 cm).
3. **Game coordinates: S-JTSK minus one fixed city origin, the Marian column on Staroměstské náměstí:
   `(−742 806, −1 043 024)`** (the centre of its footprint, OSM way 815041625, through the ČÚZK grid,
   rounded to whole metres). The Prague meridian line (Pražský poledník), by which Prague time was once
   kept from the original column's noon shadow, runs 10 m beside it. Every line and tile shares the
   origin; the whole city lies within 25 km of it. The origin is a defined constant: how accurately the
   column itself is mapped does not matter, it only has to be one number for everyone. Tiles stay on the
   absolute S-JTSK 500 m grid, so the origin is not a tile corner (the corner of its own tile is at (−194, +24) m).
4. **No scale correction.** The −9.6 cm/km is 0.01 %: 2 m on line 17, below every other error, and the
   game stays registered exactly to the survey numbers. Revisit only if timing ever needs it.
5. **Grid north ≠ true north (7.8°):** one constant (`TRUE_NORTH = 7.8°`, from PROJ at the origin) for
   what needs real directions: sun and shadows, a compass, wind.
6. **Tiles: 500 m squares on the S-JTSK grid**, edges at whole multiples of 500 m in absolute S-JTSK,
   named by absolute index (e.g. `e-1486_n-2086` for the tile whose SW corner is (−743 000, −1 043 000),
   the one with the origin in it).
   Names do not depend on the origin.
   - The source rasters (DMR 5G 2 m, IPR 1 m, 10 m) divide 500 m exactly, so tiles cut between cells
     and never resample.
   - **Seams:** neighbouring tiles carry the same edge vertices from the same source cells. Terrain LOD
     levels use cells that divide 500 m (2, 4, 10, 20, 50 m), so a coarse level still shares its edge
     vertices with a finer neighbour. Skirts hide the T-junctions between levels.
   - Networks (tracks, lanes, footways) are global graphs, not cut. Their meshes are clipped at tile
     edges in the build, with the clip points computed once and written to both tiles.
7. **Precision:** each tile's meshes hold vertices relative to the tile's SW corner (≤ 500 m: 0.03 mm in
   float32), with the tile placed at its offset from the city origin. Three.js computes model-view
   matrices in float64 on the CPU, so the GPU only sees camera-relative values. The simulation (JS
   numbers are float64) works in city coordinates directly.

## Migration (the implementation issues)

- `tools/geo.py`: a `CityFrame` with the pinned pipeline and the origin; `Frame.xy/ll` become S-JTSK
  minus the origin, while the tools still call the same methods (#3 put every tool on `geo.py`).
  Tools that use `KX, KY` in vectorised formulas switch to `Frame.xy` on arrays.
- Line data is rebuilt in the city frame (`origin` = the city origin for every line), so lines meet
  before the tiles exist. The game reads `origin` only in the debug GeoJSON export.
- Snapshot: add `raw/proj/cz_cuzk_table_-y-x_3_v1710.tif` (sha256 `9f7b519e…`).
- Then the layer registration check (#8) in the new frame.
