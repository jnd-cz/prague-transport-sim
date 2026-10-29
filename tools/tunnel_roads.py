"""Add the road tunnels (OSM tunnel=yes) from the cached roads to an already built line, flagged "t".

build_line.py used to drop them (it keeps them now); this patches older data/lineN.json files without a
rebuild. Same conversion as build_line.py.

Usage:  python tools/tunnel_roads.py --line 17
"""
import json
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
dst = os.path.join(ROOT, "data", f"line{LINE}.json")
line = json.load(open(dst, encoding="utf-8"))
src = os.path.join(ROOT, "raw", f"line{LINE}", "roads.json")
if not os.path.exists(src):
    src = os.path.join(ROOT, "raw", "roads.json")
LAT0, LON0 = line["origin"]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from geo import Frame  # noqa: E402
KX, KY = Frame(LAT0, LON0).k  # the one conversion (tools/geo.py)
widths = {"motorway": 16, "trunk": 14, "primary": 12, "secondary": 10, "tertiary": 8, "primary_link": 7,
          "secondary_link": 7, "tertiary_link": 6, "trunk_link": 7, "residential": 6.5, "unclassified": 6,
          "living_street": 5, "service": 4, "pedestrian": 6, "footway": 2.5}
line["roads"] = [r for r in line["roads"] if not r.get("t")]
n = 0
for e in json.load(open(src, encoding="utf-8"))["elements"]:
    t = e.get("tags", {})
    if "geometry" not in e or t.get("tunnel") != "yes" or t.get("area") == "yes":
        continue
    hw = t.get("highway")
    w = widths.get(hw, 5)
    if "lanes" in t:
        try:
            w = max(w, int(t["lanes"].split(";")[0]) * 3.2)
        except ValueError:
            pass
    road = {"p": [[round((g["lon"] - LON0) * KX, 1), round((g["lat"] - LAT0) * KY, 1)] for g in e["geometry"]], "w": w,
            "f": 1 if hw in ("footway", "pedestrian", "living_street") else 0,
            "c": 1 if hw in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential",
                             "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
            and t.get("service") is None
            and not any(t.get(k) in ("no", "private", "destination", "delivery") for k in ("access", "vehicle", "motor_vehicle", "motorcar")) else 0,
            "t": 1}
    ow = t.get("oneway")
    if ow in ("yes", "true", "1"):
        road["o"] = 1
    elif ow == "-1":
        road["o"] = -1
    line["roads"].append(road)
    n += 1
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(line, fh, ensure_ascii=False, separators=(",", ":"))
print(f"line {LINE}: {n} tunnel ways ({sum(1 for r in line['roads'] if r.get('t') and r['c'])} for cars)")
