"""Pilot: lane markings from the IPR Praha orthophoto along a stretch of a line.

Orthofoto Prahy, leaf-off flight 7-8 April 2026, 7 cm/px, CC BY 4.0 (IPR Praha), ArcGIS ImageServer
`ort/mimovegetacni_letecke_snimkovani`. Along the route every 2 m a cross-section (-25..25 m, 0.1 m
steps) is sampled from the image; on the surveyed carriageway (DTM road/parking/tram areas) a lane
line is a narrow bright stripe (0.08-0.4 m, clearly brighter than the asphalt around it). Stripes that
repeat at the same lateral position within a 20 m window (solid lines, or dashes 3 m on / 6 m off)
are kept as lines; lanes are the gaps between the kerbs and the lines.

Usage:  python -P -E tools/ortho_lanes.py --line 17 --from 10400 --to 10800
Prints the lines and lanes per 20 m, writes reports/ortho_lanes_<line>_<from>.png (the image with
the detected marks: red = stripe, yellow = kept line) and reports/ortho_lanes_<line>.json.
Image tiles are cached in raw/ortho/.
"""
import io
import json
import math
import os
import sys
import urllib.request

import numpy as np
import shapely
from PIL import Image, ImageDraw
from pyproj import Transformer
from shapely.geometry import Polygon

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d  # noqa: E731
LINE, S0, S1 = arg("--line", "17"), arg("--from", 10400.0), arg("--to", 10800.0)
SERVICE = "https://gs-pub.praha.eu/imgs/rest/services/ort/mimovegetacni_letecke_snimkovani/ImageServer/exportImage"
PX = 0.1  # m per pixel of the exported tiles
TILE = 100.0  # m

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
dtm = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.dtm.json"), encoding="utf-8"))
LAT0, LON0 = line["origin"]
KX, KY = math.cos(math.radians(LAT0)) * 111320.0, 110574.0
to_jtsk = Transformer.from_crs(4326, 5514, always_xy=True)


def jtsk(x, y):
    return to_jtsk.transform(LON0 + np.asarray(x) / KX, LAT0 + np.asarray(y) / KY)


path = shapely.LineString([p[:2] for p in line["path"]])
carr = [Polygon([p[:2] for p in a.get("r0", a["r"])]).buffer(0) for a in dtm["areas"]
        if a["l"] == 0 and a["c"] in ("road", "parking", "tram") and len(a["r"]) >= 3]
carr_u = shapely.unary_union([g for g in carr if g.intersects(path.buffer(30))])

# tiles of the orthophoto, cached
cache = os.path.join(ROOT, "raw", "ortho")
os.makedirs(cache, exist_ok=True)
tiles = {}


def tile(ix, iy):
    if (ix, iy) in tiles:
        return tiles[(ix, iy)]
    f = os.path.join(cache, f"{ix}_{iy}.png")
    if not os.path.exists(f):
        x0, y0 = ix * TILE, iy * TILE
        n = int(TILE / PX)
        url = f"{SERVICE}?bbox={x0},{y0},{x0 + TILE},{y0 + TILE}&bboxSR=5514&imageSR=5514&size={n},{n}&format=png&f=image"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "tram-game-prototype/0.1"}), timeout=120) as r:
            open(f, "wb").write(r.read())
    tiles[(ix, iy)] = np.asarray(Image.open(f).convert("L"), dtype=np.float32)
    return tiles[(ix, iy)]


def lum(X, Y):
    """Luminance at S-JTSK points (arrays)."""
    out = np.zeros(len(X), np.float32)
    ix, iy = np.floor(X / TILE).astype(int), np.floor(Y / TILE).astype(int)
    for key in set(zip(ix.tolist(), iy.tolist())):
        m = (ix == key[0]) & (iy == key[1])
        img = tile(*key)
        n = img.shape[0]
        col = np.clip(((X[m] - key[0] * TILE) / PX).astype(int), 0, n - 1)
        row = np.clip((n - 1 - (Y[m] - key[1] * TILE) / PX).astype(int), 0, n - 1)  # image rows go south
        out[m] = img[row, col]
    return out


LATS = np.arange(-25, 25.001, 0.1)
rows = []  # per section: s, marks (laterals), carriageway mask
for s in np.arange(S0, S1, 2.0):
    p, q = path.interpolate(s), path.interpolate(min(path.length, s + 1))
    hx, hy = q.x - p.x, q.y - p.y
    l = math.hypot(hx, hy) or 1
    hx, hy = hx / l, hy / l
    xs, ys = p.x - hy * LATS, p.y + hx * LATS  # + = left
    inside = shapely.contains_xy(carr_u, xs, ys)
    X, Y = jtsk(xs, ys)
    L = lum(np.asarray(X), np.asarray(Y))
    # bright narrow stripes: above the local median (1.5 m window) by 35, at least 140
    k = 15
    med = np.array([np.median(L[max(0, i - k):i + k + 1]) for i in range(len(L))])
    hot = (L > med + 35) & (L > 140) & inside
    marks, i = [], 0
    while i < len(hot):
        if hot[i]:
            j = i
            while j + 1 < len(hot) and hot[j + 1]:
                j += 1
            if 1 <= j - i + 1 <= 4:  # 0.1-0.4 m wide
                marks.append(float(LATS[(i + j) // 2]))
            i = j + 1
        else:
            i += 1
    rows.append({"s": float(s), "marks": marks, "inside": inside, "xs": xs, "ys": ys})

# lines: lateral positions (0.3 m bins) with stripes in at least 2 sections of a 20 m window
out = []
for w0 in np.arange(S0, S1, 20.0):
    sec = [r for r in rows if w0 <= r["s"] < w0 + 20]
    hist = {}
    for r in sec:
        for m in set(round(m / 0.3) for m in r["marks"]):
            hist[m] = hist.get(m, 0) + 1
    lines = sorted(b * 0.3 for b, c in hist.items() if c >= 2 and hist.get(b - 1, 0) <= c and hist.get(b + 1, 0) <= c)
    # carriageway runs across (kerb to kerb) in the window's middle section
    mid = sec[len(sec) // 2]
    runs, cur = [], None
    for lat, ins in zip(LATS, mid["inside"]):
        if ins and cur is None:
            cur = [lat, lat]
        elif ins:
            cur[1] = lat
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    lanes = []
    for a, b in runs:
        edges = [a] + [x for x in lines if a + 0.5 < x < b - 0.5] + [b]
        lanes += [[round(u, 1), round(v, 1)] for u, v in zip(edges, edges[1:]) if v - u >= 2.4]
    out.append({"s": float(w0), "lines": [round(x, 1) for x in lines], "carriageway": [[round(a, 1), round(b, 1)] for a, b in runs], "lanes": lanes})
    print(f"s {w0:6.0f}: carriageway {[(round(a, 1), round(b, 1)) for a, b in runs]}  lines {[round(x, 1) for x in lines]}  lanes {len(lanes)}")

os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "reports", f"ortho_lanes_{LINE}.json"), "w"), indent=1)

# debug image: the stretch's first 80 m, marks in red, kept lines in yellow
c = path.interpolate(S0 + 40)
cx, cy = jtsk(c.x, c.y)
cx, cy = float(cx), float(cy)
n = 900
img = Image.new("RGB", (n, n))
for ix in range(int((cx - 45) // TILE), int((cx + 45) // TILE) + 1):
    for iy in range(int((cy - 45) // TILE), int((cy + 45) // TILE) + 1):
        tile(ix, iy)
        t = Image.open(os.path.join(cache, f"{ix}_{iy}.png")).convert("RGB")
        img.paste(t, (int((ix * TILE - (cx - 45)) / PX), int(((cy + 45) - (iy + 1) * TILE) / PX)))
d = ImageDraw.Draw(img)
for r in rows:
    if r["s"] > S0 + 85:
        break
    win = next(o for o in out if o["s"] <= r["s"] < o["s"] + 20)
    for lat in r["marks"]:
        X, Y = jtsk(r["xs"][0] + 0, r["ys"][0] + 0)
        i = int(round((lat + 25) / 0.1))
        X, Y = jtsk(r["xs"][i], r["ys"][i])
        u, v = (float(X) - (cx - 45)) / PX, ((cy + 45) - float(Y)) / PX
        col = (255, 220, 0) if any(abs(lat - x) < 0.35 for x in win["lines"]) else (255, 40, 40)
        d.ellipse([u - 3, v - 3, u + 3, v + 3], outline=col, width=2)
img.save(os.path.join(ROOT, "reports", f"ortho_lanes_{LINE}_{int(S0)}.png"))
print("wrote", os.path.join("reports", f"ortho_lanes_{LINE}_{int(S0)}.png"))
