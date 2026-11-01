"""The street survey's 3D lines as they come, for review mode's Source layer (#140):
    python -P -E tools/zps_source.py --line 17      -> data/lineN.zps.json

dtm.py turns the survey (ZPS) into areas with fitted heights; review mode shows those. This keeps the
source next to them: every boundary line (Hranice_*), wall and terrain edge of the line's districts
within the corridor (80 m around the route), with its own vertex heights, its level
(UrovenUmisteniObjektuZPS) and its height accuracy class (TridaPresnostiVyska), so a reviewer can tell a
wrong source from a wrong build. Not read by the game outside review mode.
{"kinds": [names], "lines": [[kind index, level, height class, x, y, z, x, y, z, ...]]} (city frame;
z null where the source has none).
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import replacing  # noqa: E402
import gpkg  # noqa: E402
import sources  # noqa: E402
from dtm_packages import DTM, select_packages  # noqa: E402
from geo import Frame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "17"
KEEP = ("Hranice", "Zeď", "Terénní_hrana")
F = Frame()

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
# (dtm.py's corridor: 40 m cells, two around every route point of both directions)
cells = {(int(p[0] // 40) + dx, int(p[1] // 40) + dy) for p in line["path"] + line.get("pathBack", [])
         for dx in range(-2, 3) for dy in range(-2, 3)}

kinds, out, seen = [], [], set()
for package in select_packages(ROOT, districts=DTM[LINE]):
    for t, info in gpkg.layers(package.kr).items():
        name = t.split("#")[-1].split("_", 1)[-1]
        if info["type"] not in ("LINESTRING", "MULTILINESTRING") or not name.startswith(KEEP):
            continue
        for f in gpkg.features(package.kr, t):
            g = f["geom"]
            if not g:
                continue
            # (a line on a district border is in both districts' packages)
            key = f.get("ID") and (t, f["ID"])
            if key and key in seen:
                continue
            seen.add(key)
            for pts in [g[1]] if g[0] == "LineString" else [p[1] for p in g[1]]:
                loc = [(x - F.E0, y - F.N0, z) for x, y, z in pts]
                if not any((int(x // 40), int(y // 40)) in cells for x, y, _ in loc):
                    continue
                if name not in kinds:
                    kinds.append(name)
                row = [kinds.index(name), f.get("UrovenUmisteniObjektuZPS") or 0, f.get("TridaPresnostiVyska")]
                for x, y, z in loc:
                    row += [round(x, 2), round(y, 2), round(z, 2) if z else None]
                out.append(row)

res = {"kinds": kinds, "lines": out}
res["provenance"] = sources.stamp("zps_source.py", {"lines": sources.single("streets", "zps", len(out))})
res["attribution"] = sources.attribution(res["provenance"])
dst = os.path.join(ROOT, "data", f"line{LINE}.zps.json")
with replacing(dst, "w", encoding="utf-8") as fh:
    json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
print(f"line {LINE}: {len(out)} source lines of {len(kinds)} kinds -> {dst} ({os.path.getsize(dst) / 1e6:.1f} MB)")
