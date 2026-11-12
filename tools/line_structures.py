# SPDX-License-Identifier: AGPL-3.0-or-later
"""The route's structures for the game (#480, #276 step 2): where it runs on a bridge, which spans have a deck the track
lies on, and the roads under it with their clearance. Built once here, read by the page (src/terrain.js Profile, which
worked them out at every load until #480).

    python -P -E tools/line_structures.py --line 17     # after tools/line_heights.py: writes `spans`, `realDecks`,
                                                         # `underpasses` into data/line17.json

Every PROFILE_STEP m of the route (the page's profile step):
- **spans**: OSM's bridges of the route (`bridges`, tools/build_line.py) and the runs of at least BED_RUN m where the
  survey's tram bed on a structure (data/lineN.dtm.json, an area of class `tram` at level 1 or more) lies under the
  axis, not within TUNNEL_NEAR m of a tunnel; spans less than MERGE m apart are one.
- **realDecks**: the spans the track lies on a deck in: the survey's bed under more than half of the span, or the
  bridge model (Geoportál Mosty 3D, data/lineN.geo.json buildings of kind 1) under more than DECK_SHARE of it. On
  OSM's bridges a sample without the model under the axis takes it 3.3 m to either side: the Krejcárek viaduct's
  model has its deck under one track only.
- **underpasses**: the roads under the route with a maximum height (`clearances`, tools/clearances.py) where the
  track stands at least AT_GRADE m over the road (lower, the road meets the track at grade: nábřeží Edvarda Beneše
  at Čechův most), with the road's surface `zr` (the survey's ground-level area there, else the lidar) and the
  height the track needs over it, `need` = zr + maxheight + STRUCTURE.
"""
import json
import math
from pathlib import Path
import struct
import sys

import shapely
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from route import Route  # noqa: E402
from track_styles import RANK, ground_area  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROFILE_STEP = 2      # m (src/terrain.js Profile step)
BED_RUN = 10          # m of surveyed bed on a structure that make a span
MERGE = 6             # m: spans this near are one
TUNNEL_NEAR = 10      # m: no bed is taken this near a tunnel (the deck over the portal is not ours)
DECK_SHARE = 0.3      # of a span: the bridge model under this much of it makes it a deck
SIDE = 3.3            # m: on an OSM bridge, the model this far to either side (the other track's half)
AT_GRADE, STRUCTURE = 2.0, 0.8  # m: under this the road is at grade; the deck's depth over the clearance


def polys(areas):
    out = []
    for a in areas:
        if len(a["r"]) < 3:
            continue
        p = Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
        p = p if p.is_valid else p.buffer(0)
        if not p.is_empty:
            out.append((p, a))
    return out


def fill(ring):
    """A ring's missing heights from its neighbours on the ring (src/terrain.js DtmSurface `fill`; the terrain where
    none has one is left out here)."""
    out = [list(q) for q in ring]
    for i, q in enumerate(out):
        if q[2] is None:
            q[2] = next((out[(i + k) % len(out)][2] if out[(i + k) % len(out)][2] is not None else out[(i - k) % len(out)][2]
                         for k in range(1, len(out)) if out[(i + k) % len(out)][2] is not None or out[(i - k) % len(out)][2] is not None), None)
    return [q for q in out if q[2] is not None]


def cut(ring, piece=4.0):
    """A ground-level outline cut into equal pieces of at most `piece` m (src/terrain.js DtmSurface `cut`)."""
    out = []
    for i, p in enumerate(ring):
        q = ring[(i + 1) % len(ring)]
        k = max(1, math.ceil(math.hypot(q[0] - p[0], q[1] - p[1]) / piece))
        out += [[p[0] + (q[0] - p[0]) * j / k, p[1] + (q[1] - p[1]) * j / k, p[2] + (q[2] - p[2]) * j / k] for j in range(k)]
    return out


class Surface:
    """The survey's ground-level surface height at a point: the highest-ranked area covering it, linear on the
    constrained Delaunay triangles of its outline cut to 4 m (src/terrain.js DtmSurface.heightAt; the page splits them
    finer, linearly)."""

    def __init__(self, dtm):
        self.items = polys([a for a in dtm.get("areas", []) if ground_area(a)])
        self.tree = shapely.STRtree([p for p, _ in self.items]) if self.items else None

    def at(self, x, y):
        if self.tree is None:
            return None
        pt = Point(x, y)
        hits = [self.items[int(k)] for k in self.tree.query(pt) if self.items[int(k)][0].covers(pt)]
        if not hits:
            return None
        _, a = max(hits, key=lambda h: RANK.get(h[1]["c"], 1))
        rings = [cut(fill(r)) for r in [a["r"], *[h for h in a.get("h", []) if len(h) >= 3]]]
        zs = {(round(q[0], 3), round(q[1], 3)): q[2] for r in rings for q in r}
        poly = Polygon([q[:2] for q in rings[0]], [[q[:2] for q in r] for r in rings[1:]])
        poly = poly if poly.is_valid else poly.buffer(0)
        for t in shapely.constrained_delaunay_triangles(poly).geoms:
            if not t.covers(pt):
                continue
            (x1, y1), (x2, y2), (x3, y3) = list(t.exterior.coords)[:3]
            d = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
            if abs(d) < 1e-9:
                continue
            w1 = ((y2 - y3) * (x - x3) + (x3 - x2) * (y - y3)) / d
            w2 = ((y3 - y1) * (x - x3) + (x1 - x3) * (y - y3)) / d
            z = [zs.get((round(u, 3), round(v, 3))) for u, v in ((x1, y1), (x2, y2), (x3, y3))]
            if None in z:
                continue
            return w1 * z[0] + w2 * z[1] + (1 - w1 - w2) * z[2]
        return None


def bridge_triangles(data, root=ROOT):
    """The bridge models' triangles (kind 1) from the line's quantised buildings (tools/geoportal.py
    write_buildings): [(x, y) * 3]."""
    b = (data.get("geo") or {}).get("buildings") if "geo" in data else None
    gp = root / "data" / f"line{data['line']}.geo.json"
    if b is None and gp.exists():
        b = json.loads(gp.read_text(encoding="utf-8")).get("buildings")
    if not b:
        return []
    raw = (root / "data" / b["file"]).read_bytes()
    q, out = b["q"], []
    for ch in b["chunks"]:
        if not ch.get("k"):
            continue
        ox, oy, _ = ch["o"]
        v = ch["v"]
        for bi, count in enumerate(ch["b"]):
            if ch["k"][bi] != 1:
                v += count
                continue
            for t in range(0, count, 3):
                tri = []
                for k in range(3):
                    x, y, _ = struct.unpack_from("<hhh", raw, (v + t + k) * 6)
                    tri.append((ox + x * q, oy + y * q))
                out.append(tri)
            v += count
    return out


def structures(data, dtm, tris, surface_at, lidar_at):
    rt = Route(data["path"], data.get("pathExt"))
    n = math.ceil(rt.length / PROFILE_STEP) + 1
    tunnels, bridges = data.get("tunnels") or [], data.get("bridges") or []
    beds = polys([a for a in (dtm or {}).get("areas", []) if a.get("l", 0) >= 1 and a["c"] == "tram"])
    btree = shapely.STRtree([p for p, _ in beds]) if beds else None
    tpolys = [Polygon(t) for t in tris if Polygon(t).area > 1e-6]
    ttree = shapely.STRtree(tpolys) if tpolys else None

    def model_under(x, y):
        pt = Point(x, y)
        return ttree is not None and any(tpolys[int(k)].covers(pt) for k in ttree.query(pt))

    bed, deck = [False] * n, [False] * n
    for i in range(n):
        s = i * PROFILE_STEP
        x, y, hx, hy = rt.at(s)
        under = any(a - TUNNEL_NEAR < s < b + TUNNEL_NEAR for a, b in tunnels)
        if btree is not None and not under:
            pt = Point(x, y)
            bed[i] = any(beds[int(k)][0].covers(pt) for k in btree.query(pt))
        deck[i] = model_under(x, y)
        if not deck[i] and any(a < s < b for a, b in bridges):
            deck[i] = any(model_under(x - hy * SIDE * side, y + hx * SIDE * side) for side in (1, -1))
    spans = [[a, b] for a, b in bridges]
    i = 0
    while i < n:
        if bed[i]:
            j = i
            while j + 1 < n and bed[j + 1]:
                j += 1
            if (j - i) * PROFILE_STEP >= BED_RUN:
                spans.append([i * PROFILE_STEP, j * PROFILE_STEP])
            i = j
        i += 1
    spans.sort()
    merged = []
    for sp in spans:
        if merged and sp[0] <= merged[-1][1] + MERGE:
            merged[-1][1] = max(merged[-1][1], sp[1])
        else:
            merged.append(list(sp))

    def share(flags, a, b):
        ks = [k for k in range(math.ceil(a / PROFILE_STEP), int(b / PROFILE_STEP) + 1) if k < n]
        return sum(flags[k] for k in ks) / max(1, len(ks))
    real = [sp for sp in merged
            if sum(deck[k] for k in range(math.ceil(sp[0] / PROFILE_STEP), int(sp[1] / PROFILE_STEP) + 1) if k < n)
            * PROFILE_STEP > (sp[1] - sp[0]) * DECK_SHARE or share(bed, *sp) > 0.5]
    zs = data["heights"]["path"]
    clear = []
    for c in data.get("clearances") or []:
        if c.get("mh") is None:
            continue
        j = round(c["s"] / PROFILE_STEP)
        k = c["s"] / data["heights"]["step"]
        i0 = min(int(k), len(zs) - 2)
        if j < 0 or j >= n or zs[i0] is None or zs[i0 + 1] is None:
            continue
        z = zs[i0] + (zs[i0 + 1] - zs[i0]) * (k - i0)
        zr = surface_at(c["x"], c["y"])
        zr = lidar_at(c["x"], c["y"]) if zr is None else zr
        if zr is None or z - zr < AT_GRADE:
            continue
        clear.append({**c, "zr": round(zr, 3), "need": round(zr + c["mh"] + STRUCTURE, 3)})
    r1 = lambda v: round(v, 1)  # noqa: E731
    return [[r1(a), r1(b)] for a, b in merged], [[r1(a), r1(b)] for a, b in real], clear


def main():
    if "--line" not in sys.argv:
        sys.exit(__doc__)
    line = sys.argv[sys.argv.index("--line") + 1]
    p = ROOT / "data" / f"line{line}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    dp = ROOT / "data" / f"line{line}.dtm.json"
    dtm = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else None
    surf = Surface(dtm) if dtm else None
    from import_track_heights import Terrain
    T = Terrain()
    spans, real, clear = structures(data, dtm, bridge_triangles(data), surf.at if surf else (lambda x, y: None),
                                    lambda x, y: T([x], [y])[0])
    data["spans"], data["realDecks"], data["underpasses"] = spans, real, clear
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"line {line}: spans {spans}; decks {real}; {len(clear)} clearances over the road")


if __name__ == "__main__":
    main()
