"""ČÚZK DMR 5G in 500 m tiles at 1 m pixels, and the passages rule: level 1 of the terrain chain (tools/sources.py).

Source: the dmr5g ImageServer at ags.cuzk.gov.cz (bare earth from the 2009-2013 lidar, a 2 m TIN raster, Bpv;
CC BY 4.0 ČÚZK), exported in S-JTSK tiles of TILE m at PX m pixels: raw/dem/{ix}_{iy}.tif covers E ix*TILE ..
+TILE, N iy*TILE .. +TILE. The tiles come from the snapshot (the `dem` group); a tile that is not in raw/ is an
error unless the reader was made with fetch=True, which downloads it (then publish a snapshot with it, #223).
Read by tools/fine_terrain.py (a line's band) and tools/city_terrain.py (IPR's gaps inside the city).

The passages rule: IPR is bare earth without structures, so over a passage (an underpass, a culvert) it shows the
passage, not the surface over it, which DMR 5G kept. Near an OSM passage (PASSAGE_R), a point where IPR lies more
than PASSAGE_DROP below DMR 5G takes DMR 5G: measured 2026-10-30, the track would otherwise dip 5-6 m into
Divadelní's underpass at Národní divadlo (lines 9, 22, 23) and the Rokytka culvert (line 37).
"""
import io
import os
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "https://ags.cuzk.gov.cz/arcgis2/rest/services/dmr5g/ImageServer/exportImage"
TILE, PX = 500.0, 1.0  # export tiles: 500 m at 1 m pixels (S-JTSK)
DIR = os.path.join(ROOT, "raw", "dem")
USER_AGENT = "tram-game-prototype/0.1"
PASSAGE_R, PASSAGE_DROP = 8.0, 0.5  # m: half a passage's width with its walls; IPR under DMR 5G by more


def passage(t):
    """OSM tags of a way under the surface: tunnels, culverts, covered ways, ways below ground level; not the deep metro."""
    if t.get("location") == "underground" or t.get("railway") == "subway":
        return False
    try:
        below = float(t.get("layer", 0)) < 0
    except ValueError:
        below = False
    return t.get("tunnel", "no") != "no" or t.get("covered") == "yes" or t.get("culvert") == "yes" or below


def name(ix, iy):
    return f"{ix}_{iy}.tif"


def download(ix, iy, path, tries=6, out=print):
    """One tile from the ImageServer into `path` (whole, tools/atomic.py), retried after 5, 10, .. s; SystemExit when
    every try failed. An error page is no image: it is never written."""
    x0, y0, n = ix * TILE, iy * TILE, int(TILE / PX)
    q = urllib.parse.urlencode({"bbox": f"{x0},{y0},{x0 + TILE},{y0 + TILE}", "bboxSR": 5514, "imageSR": 5514,
                                "size": f"{n},{n}", "format": "tiff", "pixelType": "F32",
                                "interpolation": "RSP_BilinearInterpolation", "f": "image"})
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(SERVICE + "?" + q, headers={"User-Agent": USER_AGENT}), timeout=180) as r:
                data = r.read()
            Image.open(io.BytesIO(data))  # (an error page is no image)
            with replacing(path, "wb") as fh:
                fh.write(data)
            return
        except Exception as e:  # noqa: BLE001
            out(f"  tile {ix},{iy}: {str(e)[:60]}; retry", flush=True)
            time.sleep(5 * (k + 1))
    raise SystemExit(f"tile {ix},{iy} failed")


class Tiles:
    """The tiles as float32 arrays (rows north to south), read once each; `fetched` lists the tiles downloaded."""

    def __init__(self, fetch=False, directory=DIR):
        self.fetch, self.dir = fetch, directory
        self.tiles, self.fetched = {}, []
        os.makedirs(directory, exist_ok=True)

    def path(self, ix, iy):
        return os.path.join(self.dir, name(ix, iy))

    def have(self, ix, iy):
        return (ix, iy) in self.tiles or os.path.exists(self.path(ix, iy))

    def tile(self, ix, iy):
        if (ix, iy) in self.tiles:
            return self.tiles[(ix, iy)]
        f = self.path(ix, iy)
        if not os.path.exists(f):
            # (a cache miss used to download silently: the 2026-11-03 snapshot had to add 8 such tiles, #223)
            if not self.fetch:
                raise SystemExit(f"raw/dem/{ix}_{iy}.tif: not in raw/ (the snapshot, tools/snapshot.py fetch); --fetch downloads it, then publish a new snapshot before data-publish")
            self.fetched.append(f)
            download(ix, iy, f)
        self.tiles[(ix, iy)] = np.asarray(Image.open(f), dtype=np.float32)
        return self.tiles[(ix, iy)]

    def sample(self, X, Y):
        """Bilinear DMR 5G at S-JTSK points (arrays); pixel centres at (i + 0.5) m."""
        out = np.full(X.shape, np.nan, np.float32)
        ix, iy = np.floor(X / TILE).astype(int), np.floor(Y / TILE).astype(int)
        for key in set(zip(ix.ravel().tolist(), iy.ravel().tolist())):
            m = (ix == key[0]) & (iy == key[1])
            img = self.tile(*key)
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
