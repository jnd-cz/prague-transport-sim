"""Fine terrain along a line (PLAN B3): ČÚZK DMR 5G bare-earth lidar on a 2 m lattice near the tracks.

The game's terrain is a 10 x 15 m grid over the whole line (build_line.py), too coarse for the ground
beside the tracks (jagged slopes, walls, tunnel mouths). This samples DMR 5G (ags.cuzk.gov.cz ImageServer,
2 m TIN-based raster, Bpv heights, S-JTSK; CC BY 4.0 ČÚZK) at STEP m in the line's local metres, in
blocks of B x B cells that touch a band of BAND m either side of either track. Elsewhere the coarse grid
stays.

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
from shapely.geometry import LineString, box

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


t0 = time.time()
grids = []
for k, (bi, bj) in enumerate(blocks):
    xs = X0 + bi * BS + np.arange(B + 1) * STEP
    ys = Y0 - bj * BS - np.arange(B + 1) * STEP
    GX, GY = np.meshgrid(xs, ys)  # rows north to south
    X, Y = F.to_jtsk(GX, GY)  # (the city frame is a shift of S-JTSK)
    z = sample(np.asarray(X), np.asarray(Y))
    if np.isnan(z).any() or (z < 0).any():  # (no data: outside the republic's model) the coarse grid holds
        bad = np.isnan(z) | (z < 0)
        z[bad] = np.nanmedian(z[~bad]) if (~bad).any() else 0
    grids.append(z)
    if (k + 1) % 50 == 0:
        print(f"  {k + 1}/{len(blocks)} blocks, {len(tiles)} tiles, {time.time() - t0:.0f} s", flush=True)

allz = np.concatenate([g.ravel() for g in grids])
base = float(np.floor(allz.min()))
SCALE = 0.01
if (allz.max() - base) / SCALE > 32767:
    SCALE = 0.02
q = np.concatenate([np.round((g.ravel() - base) / SCALE).astype(np.int16) for g in grids])
with replacing(os.path.join(ROOT, "data", f"line{LINE}.fine.bin"), "wb") as fh:
    fh.write(q.tobytes())
meta = {"attribution": "Terrain: ČÚZK DMR 5G (CC BY 4.0)", "step": STEP, "B": B, "base": base, "scale": SCALE,
        "x0": X0, "y0": Y0, "band": BAND, "blocks": [list(b) for b in blocks]}
with replacing(os.path.join(ROOT, "data", f"line{LINE}.fine.json"), "w") as fh:
    json.dump(meta, fh, separators=(",", ":"))
print(f"wrote data/line{LINE}.fine.bin ({q.nbytes / 1e6:.1f} MB), {len(blocks)} blocks, heights {base:.0f}-{allz.max():.0f} m, {time.time() - t0:.0f} s")
