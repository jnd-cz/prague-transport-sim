# SPDX-License-Identifier: AGPL-3.0-or-later
"""A checks folder's flat kerb samples sorted by what each source has across the kerb there (#800).

    python -X utf8 -P -E tools/bench/kerb_causes.py DIR [--lines 9,17,22,23,37] [--list] [--json OUT]

DIR is a `tools/headless.py --checks surfaces --out DIR` folder: its lineN-surfaces.json lists the flat kerbs
(`result.samples.flatKerbs`: a raised area and a carriageway side by side on a row across the route, the step between
them under 5 cm in 0.25 m, tools/bench/surfaces.js). The checkout's data must be the data those checks ran on. Per
sample, SIDE m into the raised area against SIDE m out on the carriageway, across the route:
- IPR's raster (tools/ipr_dtm.py);
- the written ground (data/lineN.ground.*);
- the generated street surface (data/lineN.streets.*), for a sidewalk beside a road or the tram's area.
The first cause that holds:
- **raster flat:** IPR has under FLAT m: no kerb in the raster either (flush, lowered, or too fine for its 1 m cells);
- **ramp:** the written ground has RAMP m or more: the kerb is there, spread over more than the check's 0.25 m;
- **beside a wall:** IPR rises WALL m or more in the BEYOND m past its reading on the raised side: the raised area is
  a strip at a wall's foot, and the raster's 1 m cells spread the wall over it, so the kerb it has is the wall's and
  says nothing of a kerb the ground lacks (line 17's islands along the retaining walls at s 15500-15800, 2.7-3.6 m);
- **street flat:** a sidewalk on the street surface, whose surface has under FLAT m where IPR has FLAT m or more;
- **outline flat:** a raised area drawn from its own outline (a platform, an island, a median, a sidewalk beside
  parking): IPR has the kerb, the ground has not;
- **other:** a sidewalk whose street surface has the kerb and the ground has not.
Prints a table per line (markdown) and per cause the commonest pairs, how many lie at a stop's platform and the
medians of IPR and of the ground.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

import numpy as np
import shapely
import shapely.ops

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SIDE = 0.75   # m: how far either side of the kerb's line the sources are read
HALF = 0.125  # m: the check's own two samples, either side of the site (surfaces.js: a row every 0.25 m)
FLAT = 0.05   # m: under it a kerb is flat (surfaces.js)
RAMP = 0.07   # m: the ground over 2 * SIDE: a kerb that is there
PLATFORM = 8.0  # m: a sample this near a stop's platform stretch lies at a platform
BEYOND = 1.5  # m: past the reading on the raised side, ...
WALL = 0.3    # m: ... IPR rising this much has a wall within its cells' reach
RAISED = {"sidewalk", "island", "median", "platform"}
CAUSES = ("raster flat", "beside a wall", "outline flat", "ramp", "street flat", "other")  # (the table's columns)


def cause(ipr, gnd, sur, on_street, beyond=np.nan):
    """A sample's cause from the kerb each source has (raised side minus carriageway, m; NaN: not read) and IPR's rise
    past its reading on the raised side (beyond)."""
    if np.isfinite(ipr) and ipr < FLAT:
        return "raster flat"
    if np.isfinite(gnd) and gnd >= RAMP:
        return "ramp"
    if np.isfinite(beyond) and beyond >= WALL:
        return "beside a wall"
    if on_street and np.isfinite(sur) and sur < FLAT:
        return "street flat"
    return "other" if on_street else "outline flat"


def across(line, s):
    """Unit vectors across the route (to the left of its direction) at the lengths s along a LineString."""
    a = shapely.get_coordinates(shapely.line_interpolate_point(line, np.maximum(s - 0.5, 0)))
    b = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 0.5, line.length)))
    t = (b - a) / np.maximum(np.hypot(*(b - a).T), 1e-9)[:, None]
    return np.column_stack([-t[:, 1], t[:, 0]])


def sort_sites(sites, line, ground, lidar, street, plat=None):
    """The samples' rows: dicts with the cause, the pair (raised|carriageway), whether at a platform, x, y, s, the
    check's step and the kerb in IPR, in the ground and on the street surface (NaN where the pair is not a street's).
    ground(x, y) and lidar(x, y) give heights at arrays of points; street(kind, x, y) the street surface's ("sidewalk"
    or "road")."""
    if not sites:
        return []
    xy = np.array([[st["x"], st["y"]] for st in sites], float)
    s = np.array([float(st["s"]) for st in sites])
    u = across(line, s)
    offs = np.array([-SIDE, -HALF, HALF, SIDE])
    P = xy[:, None, :] + u[:, None, :] * offs[None, :, None]
    Z = np.asarray(ground(P[..., 0].ravel(), P[..., 1].ravel()), float).reshape(-1, 4)
    rows = []
    for i, st in enumerate(sites):
        a, b = st["classes"]
        raised, other = (b, a) if b in RAISED else (a, b)
        # the check's row runs one way across: the way whose two middle heights give back the recorded ones
        fwd = abs(Z[i, 1] - st["heights"][0]) + abs(Z[i, 2] - st["heights"][1])
        back = abs(Z[i, 2] - st["heights"][0]) + abs(Z[i, 1] - st["heights"][1])
        sg = (1.0 if fwd <= back else -1.0) * (1.0 if raised == b else -1.0)  # (+u * sg points into the raised side)
        zin, zout = (Z[i, 3], Z[i, 0]) if sg > 0 else (Z[i, 0], Z[i, 3])
        pin, pout = xy[i] + u[i] * sg * SIDE, xy[i] - u[i] * sg * SIDE
        pfar = pin + u[i] * sg * BEYOND
        zin_ipr = float(lidar(pin[:1], pin[1:])[0])
        ipr = zin_ipr - float(lidar(pout[:1], pout[1:])[0])
        beyond = float(lidar(pfar[:1], pfar[1:])[0]) - zin_ipr
        on_street = raised == "sidewalk" and other in ("road", "tram")
        sur = float(street("sidewalk", pin[:1], pin[1:])[0] - street("road", pout[:1], pout[1:])[0]) if on_street else np.nan
        gnd = float(zin - zout)
        rows.append({"cause": cause(ipr, gnd, sur, on_street, beyond), "pair": f"{raised}|{other}",
                     "platform": bool(plat is not None and shapely.contains_xy(plat, xy[i, 0], xy[i, 1])),
                     "x": float(xy[i, 0]), "y": float(xy[i, 1]), "s": float(s[i]), "step": float(st["step"]),
                     "ipr": ipr, "ground": gnd, "street": sur, "beyond": beyond, "off": float(min(fwd, back))})
    return rows


def written_ground(ln, root=ROOT):
    """The written ground's height at points, each read from its own tile."""
    import ground_mesh as gm
    import ground_place as gpl
    from geo import tile_index

    def at(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        te, tn = tile_index(x, y)
        out = np.full(len(x), np.nan)
        for key in sorted(set(zip(te.tolist(), tn.tolist()))):
            k = np.flatnonzero((te == key[0]) & (tn == key[1]))
            got = gpl.written(ln, [key], str(root))
            if got is not None and len(got[1]):
                out[k] = gm.mesh_at(got[0], got[1], x[k], y[k])
        return out
    return at


def platforms(L):
    """The stops' platform stretches of a line file, PLATFORM m round each: where a sample lies at a platform."""
    parts = []
    for pf in L.get("platforms") or []:
        key = {"route": "path", "back": "pathBack"}.get(pf.get("path"))
        if key and key in L:
            track = shapely.LineString(np.asarray(L[key], float)[:, :2])
            parts.append(shapely.ops.substring(track, float(pf["s0"]), float(pf["s1"])).buffer(PLATFORM))
    return shapely.union_all(parts) if parts else shapely.Polygon()


def table(by_line):
    """The markdown table of {line: rows} and the lines' sum."""
    out = ["| line | flat kerb samples | " + " | ".join(CAUSES) + " |", "|---|---|" + "---|" * len(CAUSES)]
    total = collections.Counter()
    for ln, rows in by_line.items():
        by = collections.Counter(r["cause"] for r in rows)
        total.update(by)
        out.append(f"| {ln} | {len(rows)} | " + " | ".join(str(by.get(c, 0)) for c in CAUSES) + " |")
    out.append(f"| all | {sum(total.values())} | " + " | ".join(str(total.get(c, 0)) for c in CAUSES) + " |")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dir", help="a headless.py --out folder with lineN-surfaces.json")
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--list", action="store_true", help="every sample, not the groups alone")
    ap.add_argument("--json", help="write the rows here")
    a = ap.parse_args()
    import ground_mesh as gm
    import wall_lines

    lidar = wall_lines.ipr_lidar()
    by_line, detail = {}, []
    for ln in a.lines.split(","):
        res = json.load(open(Path(a.dir) / f"line{ln}-surfaces.json", encoding="utf-8"))["result"]
        L = json.load(open(ROOT / "data" / f"line{ln}.json", encoding="utf-8"))
        line = shapely.LineString(np.asarray(L["path"], float)[:, :2])
        rows = by_line[ln] = sort_sites(res["samples"]["flatKerbs"], line, written_ground(ln), lidar, gm.Streets(ln).at, platforms(L))
        for c in CAUSES:
            rr = [r for r in rows if r["cause"] == c]
            if rr:
                pairs = ", ".join(f"{k} {v}" for k, v in collections.Counter(r["pair"] for r in rr).most_common(5))
                detail.append(f"line {ln} {c}: {len(rr)}, at a platform {sum(r['platform'] for r in rr)}; {pairs}; IPR median "
                              f"{np.nanmedian([r['ipr'] for r in rr]):+.2f} m, the ground's {np.nanmedian([r['ground'] for r in rr]):+.2f} m")
        # (a sample the written ground does not give back: the checkout's data is not the checks')
        bad = sum(1 for r in rows if not r["off"] <= 0.02)
        if bad:
            detail.append(f"line {ln}: {bad} samples whose recorded heights the written ground does not give back within 2 cm")
        if a.list:
            detail += [f"      {r['cause']:13s} {r['pair']:18s} ({r['x']:.0f}, {r['y']:.0f}) s {r['s']:.0f}: step {r['step']:+.3f}, "
                       f"IPR {r['ipr']:+.2f}, ground {r['ground']:+.2f}, street {r['street']:+.2f}" for r in rows]
    print("\n".join(table(by_line) + detail))
    if a.json:
        from atomic import replacing
        # (NaN, a source not read there, is no JSON: null)
        plain = {ln: [{k: (None if isinstance(v, float) and v != v else v) for k, v in r.items()} for r in rows]
                 for ln, rows in by_line.items()}
        with replacing(a.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(plain, f, indent=1)


if __name__ == "__main__":
    main()
