"""Fine terrain along a line (PLAN B3): bare-earth lidar on a 2 m lattice near the tracks.

The game's terrain is a 10 m grid over the whole line (build_line.py), too coarse for the ground
beside the tracks (jagged slopes, walls, tunnel mouths). This samples the terrain chain (tools/sources.py,
#10) at STEP m in the city frame, in blocks of B x B cells that touch a band of BAND m either side of
either track; elsewhere the coarse grid stays. Per lattice point, the first level that has a height:
  0 IPR Praha's 1 m raster (tools/ipr_dtm.py; lidar 2023),
  1 ČÚZK DMR 5G (ags.cuzk.gov.cz ImageServer, 2 m TIN-based raster, Bpv; CC BY 4.0 ČÚZK),
  2 the line's coarse grid (outside both: beyond the republic's model).
IPR states no height datum: every run compares it with DMR 5G (Bpv) where both have data and stops if
the median differs by more than DATUM_TOLERANCE.
IPR is bare earth without structures: over a passage (an underpass, a culvert) it shows the passage, not
the surface over it, which DMR 5G kept. Near an OSM passage, a point where IPR is more than PASSAGE_DROP
below DMR 5G takes DMR 5G (level 1): measured 2026-10-30, the track would otherwise dip 5-6 m into
Divadelní's underpass at Národní divadlo (lines 9, 22, 23) and the Rokytka culvert (line 37).

Usage:  python -P -E tools/fine_terrain.py --line 17 [--band 120] [--step 2]
Writes data/lineN.fine.bin (Int16, centimetres over `base`, block after block, rows north to south
like the coarse grid: y = y0 - j * step) and data/lineN.fine.json {step, B, base, scale, x0, y0, blocks:
[[bi, bj], ...]}: block (bi, bj) covers x0 + bi*B*step .. +(B)*step, y0 - bj*B*step .. down, with B+1
samples a side (shared edges, so neighbouring blocks meet exactly). Export tiles are cached in raw/dem/.
"""
import io
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image
import shapely
from shapely.geometry import LineString, box
from shapely.ops import unary_union

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
LINE, BAND, STEP, B = arg("--line", "17"), arg("--band", 120.0), arg("--step", 2.0), 64
SERVICE = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer/exportImage"
TILE, PX = 500.0, 1.0  # export tiles: 500 m at 1 m pixels (S-JTSK)
CACHE = os.path.join(ROOT, "raw", "dem")
os.makedirs(CACHE, exist_ok=True)

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
import sources  # noqa: E402

# m, |median of IPR minus DMR 5G| over a line's band. Measured 2026-10-30: lines 9, 17, 22, 23, 37
# -0.032..+0.031 (lidar of different years); Bpv vs EVRF2007 is 0.13 m in Prague (ČÚZK, in PROJ).
DATUM_TOLERANCE = 0.07
F = Frame()  # the city frame: the one conversion (tools/geo.py)
paths = [LineString([p[:2] for p in line["path"]])]
if line.get("pathBack"):
    paths.append(LineString([p[:2] for p in line["pathBack"]]))
band = paths[0].buffer(BAND)
for p in paths[1:]:
    band = band.union(p.buffer(BAND))

# the block lattice: anchored on the coarse grid's corner so both share x0 / y0
T = line["terrain"]
X0, Y0, BS = T["x0"], T["y0"], B * STEP
minx, miny, maxx, maxy = band.bounds
blocks = []
for bi in range(int((minx - X0) // BS), int((maxx - X0) // BS) + 1):
    for bj in range(int((Y0 - maxy) // BS), int((Y0 - miny) // BS) + 1):
        bx, by = X0 + bi * BS, Y0 - bj * BS
        if band.intersects(box(bx, by - BS, bx + BS, by)):
            blocks.append((bi, bj))
print(f"line {LINE}: {len(blocks)} blocks of {B}x{B} at {STEP} m ({len(blocks) * B * B / 1e6:.2f} M cells)")

# passages under the surface in the band, from the snapshot's OSM extract (cached per line like
# platforms.py's answer): tunnels, culverts, covered ways, ways below ground level; not the deep metro
PASSAGE_R, PASSAGE_DROP = 8.0, 0.5  # m: half a passage's width with its walls; IPR under DMR 5G by more


def passage(t):
    if t.get("location") == "underground" or t.get("railway") == "subway":
        return False
    try:
        below = float(t.get("layer", 0)) < 0
    except ValueError:
        below = False
    return t.get("tunnel", "no") != "no" or t.get("covered") == "yes" or t.get("culvert") == "yes" or below


src = os.path.join(ROOT, "raw", f"line{LINE}", "passages_box.json")
pbox = tuple(round(float(v), 7) for v in F.bbox(line["path"] + line.get("pathBack", []), BAND + 20))
osm = json.load(open(src, encoding="utf-8")) if os.path.exists(src) else None
try:
    import osm_local
    key = osm_local.answer_key(f"passages in box {pbox}") if osm_local.available() else None
except ImportError:
    osm_local = key = None
if key and (osm is None or osm.get("osm_key") != key):
    osm = {"elements": osm_local.ways(passage, bbox=pbox), "osm_key": key}
    os.makedirs(os.path.dirname(src), exist_ok=True)
    with replacing(src, "w", encoding="utf-8") as fh:
        json.dump(osm, fh)
if osm is None:
    raise SystemExit("no OSM extract for the passages: python -I tools/snapshot.py fetch (needs pyosmium, -P -E)")
plines = [LineString(np.column_stack(F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]])))
          for w in osm["elements"] if passage(w.get("tags", {}))]
covers = unary_union([p.buffer(PASSAGE_R) for p in plines]).intersection(band) if plines else None
if covers is not None:
    shapely.prepare(covers)
print(f"passages: {len(plines)} OSM ways in the box")

tiles = {}


def tile(ix, iy):
    if (ix, iy) in tiles:
        return tiles[(ix, iy)]
    f = os.path.join(CACHE, f"{ix}_{iy}.tif")
    if not os.path.exists(f):
        x0, y0, n = ix * TILE, iy * TILE, int(TILE / PX)
        q = urllib.parse.urlencode({"bbox": f"{x0},{y0},{x0 + TILE},{y0 + TILE}", "bboxSR": 5514, "imageSR": 5514,
                                    "size": f"{n},{n}", "format": "tiff", "pixelType": "F32",
                                    "interpolation": "RSP_BilinearInterpolation", "f": "image"})
        for k in range(6):
            try:
                with urllib.request.urlopen(urllib.request.Request(SERVICE + "?" + q, headers={"User-Agent": "tram-game-prototype/0.1"}), timeout=180) as r:
                    data = r.read()
                Image.open(io.BytesIO(data))  # (an error page is no image)
                with replacing(f, "wb") as fh:
                    fh.write(data)
                break
            except Exception as e:  # noqa: BLE001
                print(f"  tile {ix},{iy}: {str(e)[:60]}; retry", flush=True)
                time.sleep(5 * (k + 1))
        else:
            raise SystemExit(f"tile {ix},{iy} failed")
    tiles[(ix, iy)] = np.asarray(Image.open(f), dtype=np.float32)
    return tiles[(ix, iy)]


def sample(X, Y):
    """Bilinear DMR 5G at S-JTSK points (arrays); pixel centres at (i + 0.5) m."""
    out = np.full(X.shape, np.nan, np.float32)
    ix, iy = np.floor(X / TILE).astype(int), np.floor(Y / TILE).astype(int)
    for key in set(zip(ix.ravel().tolist(), iy.ravel().tolist())):
        m = (ix == key[0]) & (iy == key[1])
        img = tile(*key)
        n = img.shape[0]
        fx = (X[m] - key[0] * TILE) / PX - 0.5
        fy = (key[1] * TILE + TILE - Y[m]) / PX - 0.5  # image rows go south
        i0 = np.clip(np.floor(fx).astype(int), 0, n - 2)
        j0 = np.clip(np.floor(fy).astype(int), 0, n - 2)
        tx, ty = np.clip(fx - i0, 0, 1), np.clip(fy - j0, 0, 1)
        a, b = img[j0, i0], img[j0, i0 + 1]
        c, d = img[j0 + 1, i0], img[j0 + 1, i0 + 1]
        out[m] = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty
    return out


_coarse = np.frombuffer(__import__("base64").b64decode(T["data"]), "<i2").reshape(T["ny"], T["nx"]) * T["scale"] + T["base"]


def coarse(GX, GY):
    """Bilinear in the line's 10 m grid (city frame; x0, y0 the NW cell centre), clamped at its edges."""
    fx = np.clip((GX - T["x0"]) / T["dx"], 0, T["nx"] - 1.0001)
    fy = np.clip((GY - T["y0"]) / T["dy"], 0, T["ny"] - 1.0001)
    i, j = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - i, fy - j
    a, b, c, d = _coarse[j, i], _coarse[j, i + 1], _coarse[j + 1, i], _coarse[j + 1, i + 1]
    return ((a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty).astype(np.float32)


ipr = IprDtm()
t0 = time.time()
grids, fb, cells, diffs, passed = [], [], [0, 0, 0], [], 0
for k, (bi, bj) in enumerate(blocks):
    xs = X0 + bi * BS + np.arange(B + 1) * STEP
    ys = Y0 - bj * BS - np.arange(B + 1) * STEP
    GX, GY = np.meshgrid(xs, ys)  # rows north to south
    X, Y = F.to_jtsk(GX, GY)  # (the city frame is a shift of S-JTSK)
    z0 = ipr.sample(X, Y)
    z1 = sample(np.asarray(X), np.asarray(Y))
    z1[z1 < 0] = np.nan  # (no data: outside the republic's model)
    both = np.isfinite(z0) & np.isfinite(z1)
    diffs.append((z0 - z1)[both])
    if covers is not None:  # (IPR shows the passage, not its cover)
        cov = both & (z0 < z1 - PASSAGE_DROP) & shapely.contains_xy(covers, GX, GY)
        z0[cov] = np.nan
        passed += int(cov.sum())
    lv = np.where(np.isfinite(z0), 0, np.where(np.isfinite(z1), 1, 2))
    z = np.where(lv == 0, z0, np.where(lv == 1, z1, coarse(GX, GY)))
    grids.append(z)
    fb.append(int(lv.max()))
    for v in range(3):
        cells[v] += int((lv == v).sum())
    if (k + 1) % 50 == 0:
        print(f"  {k + 1}/{len(blocks)} blocks, {len(ipr.tiles)} IPR tiles, {len(tiles)} DMR 5G tiles, {time.time() - t0:.0f} s", flush=True)

# the datum check: IPR states none; DMR 5G is Bpv. Both are bare earth from lidar of different years,
# so single cells differ (new buildings, earthworks); a datum shift moves the median.
d = np.concatenate(diffs)
check = {"iprMinusDmr5g": {"cells": int(d.size), "median": round(float(np.median(d)), 3),
                           "p10": round(float(np.percentile(d, 10)), 3), "p90": round(float(np.percentile(d, 90)), 3),
                           "within0.25": round(float((np.abs(d) <= 0.25).mean()), 3)},
         "cells": cells, "passageCovers": passed}
print(f"terrain chain: cells IPR {cells[0]}, DMR 5G {cells[1]} ({passed} over passages), coarse {cells[2]}; blocks by worst level "
      f"{[fb.count(v) for v in range(3)]}; IPR - DMR 5G on {d.size} cells: median {check['iprMinusDmr5g']['median']:+.3f} m, "
      f"p10 {check['iprMinusDmr5g']['p10']:+.3f}, p90 {check['iprMinusDmr5g']['p90']:+.3f}")
if d.size and abs(np.median(d)) > DATUM_TOLERANCE:
    raise SystemExit(f"IPR's heights differ from DMR 5G (Bpv) by a median {np.median(d):+.3f} m: a datum change? (#62)")

allz = np.concatenate([g.ravel() for g in grids])
base = float(np.floor(allz.min()))
SCALE = 0.01
if (allz.max() - base) / SCALE > 32767:
    SCALE = 0.02
q = np.concatenate([np.round((g.ravel() - base) / SCALE).astype(np.int16) for g in grids])
with replacing(os.path.join(ROOT, "data", f"line{LINE}.fine.bin"), "wb") as fh:
    fh.write(q.tobytes())
meta = {"step": STEP, "B": B, "base": base, "scale": SCALE, "x0": X0, "y0": Y0, "band": BAND,
        "blocks": [list(b) for b in blocks], "fb": fb}  # fb: per block the worst level of its points
meta["provenance"] = sources.stamp("fine_terrain.py", {"blocks": sources.entry(
    "terrain", [fb.count(v) for v in range(3)], "blocks (worst level of a block's points)", check)})
meta["attribution"] = sources.attribution(meta["provenance"])
with replacing(os.path.join(ROOT, "data", f"line{LINE}.fine.json"), "w") as fh:
    json.dump(meta, fh, separators=(",", ":"))
print(f"wrote data/line{LINE}.fine.bin ({q.nbytes / 1e6:.1f} MB), {len(blocks)} blocks, heights {base:.0f}-{allz.max():.0f} m, {time.time() - t0:.0f} s")
