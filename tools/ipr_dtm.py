"""IPR Praha's 1 m terrain raster (the first level of the terrain chain, tools/sources.py; #10).

Source: "Digitální model terénu - rastr" (opendata.geoportalpraha.cz item 97d2c9c11aa9478cb21b469b8a4f820e,
CC BY 4.0, datový podklad © IPR Praha), one ZIP in the snapshot (raw/ipr-dtm/DTM.zip, unzipped by fetch
into raw/ipr-dtm/DTM/). Bare earth from the 2023 lidar (~40 points/m²), corrected and resampled cubic
from 25 cm to 1 m on 2025-07-10 (lineage in dtm_1m.tif.xml).

The file: BigTIFF, 35001 x 26001 float32, tiled 128 x 128, LZW without predictor, S-JTSK, no-data
-3.4e38 outside the city. Its cell centres are not on whole metres: the top-left centre is
(-757500.2778, -1034000.3889), so it is sampled bilinear at our lattice points, never copied cell by
cell. It states no vertical datum (Bpv assumed and checked against DMR 5G on every build: fine_terrain.py).

Only the tiles a build touches are decoded (a line's band is ~1000 of the 55896), with the small
TIFF-LZW decoder below: Pillow decodes LZW only through libtiff, for whole images (3.6 GB here).

    python -P -E tools/ipr_dtm.py --fetch      # download the ZIP (2.05 GB), its catalogue records, provenance.json
    python -P -E tools/ipr_dtm.py              # check the file and print a few heights
"""
import hashlib
import json
import os
import struct
import sys
import time
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw", "ipr-dtm")
TIF = os.path.join(DIR, "DTM", "dtm_1m.tif")
ITEM = "97d2c9c11aa9478cb21b469b8a4f820e"
URLS = {"DTM.zip": f"https://www.arcgis.com/sharing/rest/content/items/{ITEM}/data",
        "item.json": f"https://www.arcgis.com/sharing/rest/content/items/{ITEM}?f=json",
        "catalogue.json": f"https://opendata.geoportalpraha.cz/api/search/v1/collections/all/items/{ITEM}"}


def lzw(data):
    """TIFF LZW (MSB-first codes of 9-12 bits, clear 256, end 257, the width grows one code early)."""
    d = bytes(data) + b"\0\0\0"
    out, table, prev = bytearray(), [bytes([i]) for i in range(256)] + [b"", b""], None
    pos, nb, end = 0, 9, len(data) * 8
    while pos + nb <= end:
        i = pos >> 3
        code = ((d[i] << 16 | d[i + 1] << 8 | d[i + 2]) >> (24 - (pos & 7) - nb)) & ((1 << nb) - 1)
        pos += nb
        if code == 257:
            break
        if code == 256:
            del table[258:]
            nb, prev = 9, None
            continue
        if prev is None:
            entry = table[code]
        else:
            entry = table[code] if code < len(table) else prev + prev[:1]
            table.append(prev + entry[:1])
            if len(table) >= (1 << nb) - 1 and nb < 12:
                nb += 1
        out += entry
        prev = entry
    return bytes(out)


class IprDtm:
    """Heights at S-JTSK points: bilinear between the four nearest cells, NaN where one is no-data."""

    def __init__(self, path=TIF):
        if not os.path.exists(path):
            raise SystemExit(f"no {path}: python -I tools/snapshot.py fetch (it unzips raw/ipr-dtm/DTM.zip)")
        self.f = open(path, "rb")
        h = self.f.read(16)
        if h[:4] != b"II+\0":
            raise ValueError(f"{path}: not a little-endian BigTIFF")
        self.f.seek(struct.unpack("<Q", h[8:16])[0])
        tags = {}
        for _ in range(struct.unpack("<Q", self.f.read(8))[0]):
            e = self.f.read(20)
            tag, typ = struct.unpack("<HH", e[:4])
            tags[tag] = (typ, struct.unpack("<Q", e[4:12])[0], e[12:20])

        def val(tag, k=0):
            typ, n, raw = tags[tag]
            fmt = {3: "H", 4: "I", 12: "d", 16: "Q"}[typ]
            size = struct.calcsize(fmt) * n
            if size > 8:
                self.f.seek(struct.unpack("<Q", raw)[0])
                raw = self.f.read(size)
            return np.frombuffer(raw[:size], dtype="<" + {"H": "u2", "I": "u4", "d": "f8", "Q": "u8"}[fmt]) if k is None else struct.unpack("<" + fmt, raw[struct.calcsize(fmt) * k:struct.calcsize(fmt) * (k + 1)])[0]

        # what the decoder below handles; anything else (a re-export by IPR) must fail loudly
        want = {258: 32, 259: 5, 277: 1, 339: 3, 284: 1, 317: 1}
        got = {t: val(t) for t in want if t in tags}
        got.setdefault(317, 1)
        if got != want:
            raise ValueError(f"{path}: layout {got}, the reader handles {want}")
        self.w, self.h, self.tw, self.th = val(256), val(257), val(322), val(323)
        scale, tie = val(33550, None), val(33922, None)
        if scale[0] != 1 or scale[1] != 1:
            raise ValueError(f"{path}: cell size {scale[:2]}, not 1 m")
        self.e0, self.n0 = tie[3] + 0.5, tie[4] - 0.5  # the top-left cell's centre (PixelIsArea)
        self.offs, self.cnts = val(324, None), val(325, None)
        self.ntx = -(-self.w // self.tw)
        self.tiles = {}

    def tile(self, tx, ty):
        k = (tx, ty)
        if k not in self.tiles:
            i = ty * self.ntx + tx
            self.f.seek(int(self.offs[i]))
            a = np.frombuffer(lzw(self.f.read(int(self.cnts[i]))), dtype="<f4").reshape(self.th, self.tw).copy()
            a[a < -1e30] = np.nan
            self.tiles[k] = a
        return self.tiles[k]

    def cells(self, i, j):
        """Cell values at integer column i, row j (arrays); NaN outside the raster or no-data."""
        out = np.full(i.shape, np.nan, np.float32)
        ok = (i >= 0) & (i < self.w) & (j >= 0) & (j < self.h)
        tx, ty = i // self.tw, j // self.th
        for key in set(zip(tx[ok].tolist(), ty[ok].tolist())):
            m = ok & (tx == key[0]) & (ty == key[1])
            out[m] = self.tile(*key)[j[m] - key[1] * self.th, i[m] - key[0] * self.tw]
        return out

    def sample(self, E, N):
        E, N = np.asarray(E, np.float64), np.asarray(N, np.float64)
        fi, fj = E - self.e0, self.n0 - N
        i0, j0 = np.floor(fi).astype(np.int64), np.floor(fj).astype(np.int64)
        tx, ty = (fi - i0).astype(np.float32), (fj - j0).astype(np.float32)
        a, b = self.cells(i0, j0), self.cells(i0 + 1, j0)
        c, d = self.cells(i0, j0 + 1), self.cells(i0 + 1, j0 + 1)
        return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def fetch():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from atomic import replacing
    os.makedirs(DIR, exist_ok=True)
    for name, url in URLS.items():
        print("fetch", url, flush=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tram-game-prototype/0.1"}), timeout=600) as r, \
                replacing(os.path.join(DIR, name), "wb") as fh:
            while b := r.read(1 << 22):
                fh.write(b)
    provenance(time.strftime("%Y-%m-%d"))
    print("then: python -I tools/snapshot.py publish <id> (fetch unzips DTM.zip into raw/ipr-dtm/DTM/)")


def provenance(acquired):
    """raw/ipr-dtm/provenance.json: where each file came from, when, and its hash."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from atomic import replacing
    files = []
    for name, url in URLS.items():
        h = hashlib.sha256()
        with open(os.path.join(DIR, name), "rb") as fh:
            while b := fh.read(1 << 24):
                h.update(b)
        files.append({"file": name, "url": url, "size": os.path.getsize(os.path.join(DIR, name)), "sha256": h.hexdigest()})
    item = json.load(open(os.path.join(DIR, "item.json"), encoding="utf-8"))
    out = {"title": item["title"], "owner": item["owner"], "item": ITEM, "licence": item["licenseInfo"],
           "attribution": "datový podklad © IPR Praha", "acquired": acquired,
           "itemModified": time.strftime("%Y-%m-%d", time.gmtime(item["modified"] / 1000)),
           "lineage": "lidar 2023 (DTM2023_opr), corrected 2025 (oprava2025), 25 cm resampled cubic to 1 m on 2025-07-10 "
                      "(DTM/dtm_1m.tif.xml)", "verticalDatum": "not stated in the files (#62)", "files": files}
    with replacing(os.path.join(DIR, "provenance.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--fetch" in sys.argv:
        fetch()
        sys.exit()
    if "--provenance" in sys.argv:  # (for files fetched by hand: the date they were downloaded)
        provenance(sys.argv[sys.argv.index("--provenance") + 1])
        sys.exit()
    r = IprDtm()
    print(f"{r.w} x {r.h} cells, tiles {r.tw} x {r.th}, top-left centre ({r.e0:.4f}, {r.n0:.4f})")
    meta = json.load(open(os.path.join(DIR, "item.json"), encoding="utf-8"))
    print(meta["title"], meta["licenseInfo"], meta["size"], "bytes")
    for name, (e, n) in {"Marian column": (-742806, -1043024), "Výtoň": (-743280, -1045180),
                         "Kobylisy": (-740900, -1038200)}.items():
        print(f"{name:14} {float(r.sample(e, n)):.3f} m")
