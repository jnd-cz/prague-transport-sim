# SPDX-License-Identifier: AGPL-3.0-or-later
"""The city's lidar area by distance from its tram tracks (#276: to scale terrain_mesh.py's line 17 to Prague).

Decodes every tile of IPR's 1 m raster once and keeps a cell every STEP m where it has data, then measures each
kept cell's distance to the nearest tram track in the local OSM extract (railway=tram, not disused). Prints the
km² per distance band and, with --density reports/tm_whole.json (terrain_mesh.py --whole), the triangles that
line 17's densities per band give.

    python -P -E tools/bench/city_area.py [--step 16] [--density reports/tm_whole.json]
"""
import json
import os
import sys
import time

import numpy as np
import shapely
from shapely.geometry import LineString

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
import osm_local  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
STEP = arg("--step", 16)
BANDS = [(0, 10), (10, 120), (120, 500), (500, 1000), (1000, 2000), (2000, 1e9)]
F = Frame()

t0 = time.perf_counter()
dtm = IprDtm()
E, N = [], []
off = STEP // 2
for ty in range(-(-dtm.h // dtm.th)):
    for tx in range(dtm.ntx):
        a = dtm.tile(tx, ty)[off::STEP, off::STEP]
        dtm.tiles.clear()
        j, i = np.nonzero(~np.isnan(a))
        E.append(dtm.e0 + tx * dtm.tw + off + i * STEP)
        N.append(dtm.n0 - (ty * dtm.th + off + j * STEP))
E, N = np.concatenate(E), np.concatenate(N)
print(f"raster {dtm.w} x {dtm.h} cells ({dtm.w * dtm.h / 1e6:.0f} km² box), with data {len(E) * STEP * STEP / 1e6:.0f} km² "
      f"({time.perf_counter() - t0:.0f} s)")

ways = osm_local.ways(lambda t: t.get("railway") == "tram")
segs = []
for w in ways:
    x, y = F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]])
    p = np.column_stack([x, y])
    segs += [LineString(p[k:k + 2]) for k in range(len(p) - 1) if np.any(p[k] != p[k + 1])]
print(f"tram tracks: {len(ways)} OSM ways, {sum(s.length for s in segs) / 1000:.0f} km of track")
X, Y = F.from_jtsk(E, N)
_, d = shapely.STRtree(segs).query_nearest(shapely.points(X, Y), return_distance=True, all_matches=False)
dens = json.load(open(os.path.join(ROOT, arg("--density", "reports/tm_whole.json"))))["whole"]["density"] if "--density" in sys.argv else None
total = 0
for lo, hi in BANDS:
    km2 = float(((d >= lo) & (d < hi)).sum()) * STEP * STEP / 1e6
    key = f"{lo}-{int(hi) if hi < 1e9 else ''}"
    tri = ""
    if dens and dens.get(key, {}).get("per_km2"):
        n = km2 * dens[key]["per_km2"]
        total += n
        tri = f", {n / 1e6:.2f} M triangles at line 17's {dens[key]['per_km2']:,} per km²"
    print(f"  {key} m: {km2:.1f} km²{tri}")
if dens:
    print(f"the city's terrain: {total / 1e6:.1f} M triangles")
