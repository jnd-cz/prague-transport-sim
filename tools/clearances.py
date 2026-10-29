"""Clearances of the roads passing under our route, from OSM `maxheight` (user idea, 2026-10-23).

Where a road crosses our route (path or pathBack) on a tagged bridge of ours, or carries a posted
`maxheight` / `maxheight:physical`, the crossing is listed with its clearance: the posted metres, or
for `default` (no sign: the full legal height) 4.2 m on car roads, 2.5 m on footways and cycleways.
`below_default` (a sign we do not have the number of) is kept as null. The lint (underpassClearance)
and the profile check that our track over it stands at least the clearance plus the structure above
the road surface.

Usage:  python -P -E tools/clearances.py --line 17
Adds "clearances": [{"s", "x", "y", "mh", "src", "kind", "name"}] to data/lineN.json.
"""
import json
import math
import os
import re
import sys

import shapely
from shapely.geometry import LineString

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "17"
dst = os.path.join(ROOT, "data", f"line{LINE}.json")
line = json.load(open(dst, encoding="utf-8"))
src = os.path.join(ROOT, "raw", f"line{LINE}", "roads.json")
if not os.path.exists(src):
    src = os.path.join(ROOT, "raw", "roads.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from geo import Frame  # noqa: E402
F = Frame()  # the city frame: the one conversion (tools/geo.py)
CAR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
       "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}
WALK = {"footway", "cycleway", "path", "pedestrian", "steps", "track", "bridleway"}

path = LineString([p[:2] for p in line["path"]])
back = LineString([p[:2] for p in line["pathBack"]]) if line.get("pathBack") else None
bridges = line.get("bridges", [])


def metres(v):
    if v is None:
        return None
    m = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m)?\s*$", v)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.match(r"^\s*([0-9]+)'\s*([0-9]+)?\"?\s*$", v)  # feet and inches
    if m:
        return round(int(m.group(1)) * 0.3048 + int(m.group(2) or 0) * 0.0254, 2)
    return None


out = []
for e in json.load(open(src, encoding="utf-8"))["elements"]:
    t = e.get("tags", {})
    hw = t.get("highway")
    if e.get("type") != "way" or "geometry" not in e or not hw or t.get("bridge") not in (None, "no"):
        continue  # (a road on a bridge passes over, not under)
    kind = "car" if hw in CAR else "walk" if hw in WALK else None
    if not kind:
        continue
    g = LineString(list(zip(*F.xy([p["lat"] for p in e["geometry"]], [p["lon"] for p in e["geometry"]]))))
    raw_mh = t.get("maxheight:physical") or t.get("maxheight")
    for rt in (path, back):
        if rt is None or not g.intersects(rt):
            continue
        for pt in shapely.get_parts(g.intersection(rt)):
            if pt.geom_type != "Point":
                continue
            s = path.project(pt)
            on_bridge = any(a - 5 <= s <= b + 5 for a, b in bridges)
            if raw_mh is None and not on_bridge:
                continue  # an ordinary level crossing
            if raw_mh in (None, "default", "none"):
                mh, srcv = (4.2 if kind == "car" else 2.5), raw_mh or "assumed"
            elif raw_mh == "below_default":
                mh, srcv = None, raw_mh
            else:
                mh, srcv = metres(raw_mh), raw_mh
            out.append({"s": round(s, 1), "x": round(pt.x, 2), "y": round(pt.y, 2), "mh": mh, "src": srcv,
                        "kind": kind, "name": t.get("name"), "tunnel": t.get("tunnel")})
# one per crossing place (both of our tracks cross the same road)
out.sort(key=lambda c: c["s"])
dedup = []
for c in out:
    if dedup and abs(dedup[-1]["s"] - c["s"]) < 8 and dedup[-1]["name"] == c["name"]:
        if (c["mh"] or 0) > (dedup[-1]["mh"] or 0):
            dedup[-1] = c
        continue
    dedup.append(c)
line["clearances"] = dedup
# (written whole and renamed: tools/rebuild.py runs other steps that read this file at the same time)
with open(dst + ".part", "w", encoding="utf-8") as fh:
    json.dump(line, fh, ensure_ascii=False, separators=(",", ":"))
os.replace(dst + ".part", dst)
for c in dedup:
    print(f"s {c['s']:7.0f}  {c['kind']:4} {str(c['mh']):5} ({c['src']})  {c['name'] or ''}{'  [tunnel]' if c['tunnel'] else ''}")
print(f"{len(dedup)} crossings under the route")
