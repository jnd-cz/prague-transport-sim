"""Import the Prague Digital Technical Map (DTM, open part: ZPS) along a built line.

DTM Praha open data, "Základní prostorová situace" per city district (městská část), GeoPackage,
CC BY 4.0, data base © IPR Praha / Hlavní město Praha: https://geoportalpraha.cz (DTM kraje - ZPS
Sada 2 = areas, ZPS Sada 3 = 3D boundary lines). Areas are 2D; every vertex gets its height from the
3D boundary lines at the same position (they share vertices), else from the nearest boundary point.
Track-axis import is separate (#20): public DI JVF acquisition and archived DTMP height assessment
are documented in docs/decisions/2026-10-27-track-source.md. This tool imports ZPS surfaces only.

Usage:  python tools/dtm.py --line 22 raw/dtm/<district OPL dir> raw/dtm/<district KR dir> ...
        (pass the unzipped *_ZPS_OPL.gpkg and *_ZPS_KR.gpkg folders of every district on the line)
Writes data/lineN.dtm.json: {"attribution", "areas": [{"c": class, "l": level, "r": [[x,y,z]...], "h": [holes],
"k": kerb edges (raised areas)}]}; kerbs: tools/kerbs.py
"""
import json
import math
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atomic import replacing  # noqa: E402
import sources  # noqa: E402
import gpkg  # noqa: E402
from dtm_packages import DTM, select_packages  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = sys.argv[sys.argv.index("--line") + 1] if "--line" in sys.argv else "22"
SOURCES = [a for a in sys.argv[1:] if a not in ("--line", LINE)]

# area classes by the DTM object type code at the end of the layer name
CLASSES = {
    "010000000503": "road", "010000001703": "road", "010000001103": "parking", "010000000903": "cycle",
    "010000000703": "sidewalk", "010000001303": "island", "010000002403": "tram", "010000005303": "platform",
    "010000005803": "deck", "010000006203": "tunnel", "010000006603": "underpass", "010000031203": "rail",
    "010000021503": "green", "010000020903": "green", "010000015203": "green", "010000018703": "paved",
    "010000018903": "paved", "010000005503": "paved", "010000016603": "stairs", "010000031503": "roof",
    "010000016803": "wall", "010000020303": "water",
}

line = json.load(open(os.path.join(ROOT, "data", f"line{LINE}.json"), encoding="utf-8"))
from geo import Frame  # noqa: E402
F = Frame()  # the city frame: the one conversion (tools/geo.py)

# lidar ground (DMR 5G grid of the line): a ground-level street corner far below it is a mislabelled
# underground line (e.g. a floor 20 m under Náměstí Míru tagged as level 0)
_T = line["terrain"]
_raw = __import__("array").array("h", __import__("base64").b64decode(_T["data"]))
LIDAR = [_T["base"] + v * _T["scale"] for v in _raw]


def lidar(x, y):
    fx, fy = (x - _T["x0"]) / _T["dx"], (y - _T["y0"]) / _T["dy"]
    ix = min(max(int(math.floor(fx)), 0), _T["nx"] - 2)
    iy = min(max(int(math.floor(fy)), 0), _T["ny"] - 2)
    tx, ty = min(max(fx - ix, 0), 1), min(max(fy - iy, 0), 1)
    a, b = LIDAR[iy * _T["nx"] + ix], LIDAR[iy * _T["nx"] + ix + 1]
    c, d = LIDAR[(iy + 1) * _T["nx"] + ix], LIDAR[(iy + 1) * _T["nx"] + ix + 1]
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def local(x, y):
    # the survey is native S-JTSK: the city frame is a shift of it
    return (x - F.E0, y - F.N0)


# corridor test on a 40 m grid of route points (ours and the opposite direction)
cells = set()
for p in line["path"] + line.get("pathBack", []):
    for dx in (-2, -1, 0, 1, 2):
        for dy in (-2, -1, 0, 1, 2):
            cells.add((int(p[0] // 40) + dx, int(p[1] // 40) + dy))


def in_corridor(q):
    return (int(q[0] // 40), int(q[1] // 40)) in cells


def walk(geom):
    t, c = geom
    if t == "Polygon":
        yield c
    elif t == "MultiPolygon":
        for part in c:
            yield from walk(part)


areas, n_z, n_near, n_none, dropped = [], 0, 0, 0, 0
# heights: every vertex of the 3D boundary lines of all districts (areas along a district border
# take heights from the neighbour's lines too), keyed by its S-JTSK position (1 cm)
zkey = defaultdict(set)  # several heights where lines of two levels share a 2D position (wall top/foot)
zgrid = defaultdict(list)
wall_lines = []  # the survey's walls and terrain edges (tools/kerbs.py: an edge along one is not a kerb)
WALLS = ("Hranice_zdi", "Zeď", "Terénní_hrana")
packages = select_packages(ROOT, sources=SOURCES) if SOURCES else select_packages(ROOT, districts=DTM[LINE])
for package in packages:
    kr = package.kr
    print(f"district: {package.district}, month {package.date}")
    for t, info in gpkg.layers(kr).items():
        wall = t.split("#")[-1].split("_", 1)[-1].startswith(WALLS)
        if info["type"] not in ("LINESTRING", "MULTILINESTRING") or ("Hranice" not in t and not wall):
            continue
        for f in gpkg.features(kr, t):
            g = f["geom"]
            if not g:
                continue
            parts = [g[1]] if g[0] == "LineString" else [p[1] for p in g[1]]
            lvl = f.get("UrovenUmisteniObjektuZPS") or 0
            if wall:
                wall_lines += [[local(x, y) for x, y, _ in pts] for pts in parts if len(pts) > 1]
            if "Hranice" not in t:
                continue
            for pts in parts:
                for x, y, z in pts:
                    if z:
                        zkey[(round(x, 2), round(y, 2))].add((z, lvl))
                        zgrid[(int(x // 5), int(y // 5))].append((x, y, z, lvl))

def candidates(x, y, level):
    """Possible heights of a polygon vertex: the 3D line vertices at the same position, else
    the boundary points within 2.5 m (the nearest and any within 0.5 m more). Lines of the area's
    own level win: a ground-level street must not take the height of a metro vestibule or a deck
    outline that shares the position in 2D, and a bridge deck must not take the heights of the road
    under it (on the Modřany estakáda that made a slab sloping from the deck down into the
    underpass): only lines of the area's own level are used."""
    strict = True
    global n_z, n_near, n_none
    zs = zkey.get((round(x, 2), round(y, 2)))
    if zs:
        n_z += 1
        own = {z for z, lv in zs if lv == level}
        if own or not strict:
            return sorted(own or {z for z, _ in zs})
    near = []
    for i in range(int(x // 5) - 1, int(x // 5) + 2):
        for j in range(int(y // 5) - 1, int(y // 5) + 2):
            for px, py, pz, lv in zgrid.get((i, j), ()):
                d = math.hypot(px - x, py - y)
                if d < 2.5:
                    near.append((d, pz, lv))
    own = [n for n in near if n[2] == level] or ([] if strict else near)
    if not own:
        n_none += 1
        return []
    n_near += 1
    d0 = min(n[0] for n in own)
    return sorted({n[1] for n in own if n[0] <= d0 + 0.5})

def ring_heights(cands):
    """One height per vertex: where lines of two levels meet in 2D (the top and the foot of a
    wall), take the candidate that continues from the neighbouring vertex, walking the ring
    from a vertex with a single candidate."""
    n = len(cands)
    out = [None] * n
    start = next((i for i, c in enumerate(cands) if len(c) == 1), None)
    if start is None:
        start = next((i for i, c in enumerate(cands) if c), None)
        if start is None:
            return out
        c = cands[start]
        out[start] = c[len(c) // 2]
    else:
        out[start] = cands[start][0]
    prev = out[start]
    for k in range(1, n):
        i = (start + k) % n
        c = cands[i]
        if c:
            out[i] = min(c, key=lambda z: abs(z - prev))
            prev = out[i]
    return out


def fill_along(r, zs):
    """Vertices without a height: linear along the ring between the known neighbours."""
    n = len(zs)
    known = [i for i, z in enumerate(zs) if z is not None]
    if not known or len(known) == n:
        return zs
    dist = [0.0]
    for (x0, y0, *_), (x1, y1, *_) in zip(r, r[1:] + r[:1]):
        dist.append(dist[-1] + math.hypot(x1 - x0, y1 - y0))
    total = dist[-1]
    out = list(zs)
    for k, i in enumerate(known):
        j = known[(k + 1) % len(known)]
        gap = (j - i) % n or n
        if gap == 1:
            continue
        span = (dist[j] - dist[i]) % total if total else 0
        for m in range(1, gap):
            v = (i + m) % n
            u = ((dist[v] - dist[i]) % total) / span if span else 0
            out[v] = zs[i] + (zs[j] - zs[i]) * u
    return out


# surfaces driven or walked on: they never jump a metre between nearby outline points (a kerb is a
# few cm, a ramp a slope; stairs and walls are their own classes)
SMOOTH = {"road", "tram", "parking", "cycle", "sidewalk", "island", "platform", "paved"}
n_spikes = defaultdict(int)
import numpy as np  # noqa: E402
from ipr_dtm import IprDtm  # noqa: E402
import zps_ground  # noqa: E402
_ipr = IprDtm()  # (the IPR 1 m terrain: the ground level's reference, the spikes' judge, the kerbs' reference below)


def terrain(x, y):
    """The bare earth at a survey (S-JTSK) position, or None outside the terrain."""
    v = float(_ipr.sample(x, y))
    return v if math.isfinite(v) else None


def despike(r, zs, cls):
    """Outline points of a smooth surface more than 1 m off the median of their neighbours (3 each
    side), steeper than 1:5 to the nearest neighbour, and further from the terrain than that median
    take the height along the ring instead. Where an outline follows a retaining wall the source gives
    its vertices the wall's top and foot by turns (beside the tram embankment at Belárie, line 17:
    195.8 / 199.7 / 196.8 / 200.3 m, the terrain ~198.5, #147). On a steady slope the median is the
    point's own height, so hills stay; an outline that really runs on two levels (a riverside walk
    under the street wall, Novoměstská náplavka) keeps the points the terrain confirms."""
    n = len(zs)
    if cls not in SMOOTH or n < 7:
        return zs
    xy = [(x, y) for x, y, *_ in r]
    bad = []
    for i, z in enumerate(zs):
        if z is None:
            continue
        w = sorted(zs[(i + k) % n] for k in (-3, -2, -1, 1, 2, 3) if zs[(i + k) % n] is not None)
        if len(w) < 4:
            continue
        m = (w[len(w) // 2 - 1] + w[len(w) // 2]) / 2
        near = min(math.dist(xy[i], xy[(i - 1) % n]), math.dist(xy[i], xy[(i + 1) % n]))
        if abs(z - m) > max(1.0, 0.2 * near):
            g = terrain(*xy[i])
            if g is not None and abs(m - g) < abs(z - g):
                bad.append(i)
    if not bad or len(bad) > 0.4 * n:
        return zs  # (most of the ring disagrees: no trend to trust)
    n_spikes[cls] += len(bad)
    out = list(zs)
    for i in bad:
        out[i] = None
    return fill_along(r, out)


DECK_OVER = 2.0  # m over a ground-level area's own ground: a deck's height on a shared line, not a kerb or a step
n_deck = 0


def ground_refs(r):
    """IPR's ground 1 m inside the area from each vertex of a ring (S-JTSK), the line's coarse grid where IPR has none.
    Not the coarse grid first: under Divadelní's deck it reads the deck (192.99 m, DMR 5G), which threw out the road
    5 m below it and the area with it (#446)."""
    xy = np.array([q[:2] for q in r], float)
    closed = len(xy) > 1 and (xy[0] == xy[-1]).all()
    body = xy[:-1] if closed else xy
    pin = zps_ground.inner_points(body)[0] if len(body) >= 3 else body
    g = np.asarray(_ipr.sample(pin[:, 0], pin[:, 1]), float)
    out = [float(z) if math.isfinite(z) else lidar(*local(x, y)) for z, (x, y) in zip(g, body)]
    return out + out[:1] if closed else out


def ring(r, level, cls=None):
    """Local coordinates and heights of a ring, and how many vertices had no surveyed height."""
    loc = [local(x, y) for x, y, *_ in r]
    cands = [candidates(x, y, level) for x, y, *_ in r]
    if level == 0:
        ref = ground_refs(r)
        # (and nothing at ground level stands 8 m above the bare earth: source typos, a corner at
        # 298.9 m for 198.9 m beside the Modřany estakáda, a group of streets ~75 m too high)
        cands = [[z for z in c if g - 5 < z < g + 8] for c, g in zip(cands, ref)]
    if level == 0 and cls not in zps_ground.NOT_GROUND:  # (a wall's or a stair's outline has its top and foot by design)
        # a ground-level outline that shares its lines with a deck carries the deck's heights with them: under Divadelní's
        # deck the road's outline reads 193.2-193.3 m at 11 of its 16 corners, 5.3 m over its floor (IPR 187.95), and the
        # floor's 187.6-187.8 at the rest (#446). A height a line of an upper level has at the same place, over DECK_OVER
        # above the area's own ground, is the deck's; a corner left with none takes that ground.
        global n_deck
        deck = [{z for z, lv in zkey.get((round(x, 2), round(y, 2)), ()) if lv >= 1} for x, y, *_ in r]
        kept = [[z for z in c if not (z > g + DECK_OVER and z in dz)] for c, g, dz in zip(cands, ref, deck)]
        n_deck += sum(1 for c, k in zip(cands, kept) if c and not k)
        cands = [k if k or not c else [round(g, 2)] for c, k, g in zip(cands, kept, ref)]
        # where lines share the place (a wall's top and foot), the height at the area's own ground
        cands = [[min(c, key=lambda z: abs(z - g))] if len(c) > 1 else c for c, g in zip(cands, ref)]
    zs = ring_heights(cands)
    missing = sum(1 for z in zs if z is None)
    zs = fill_along(r, zs)
    closed = len(r) > 1 and r[0][:2] == r[-1][:2]
    if closed:
        zs = despike(r[:-1], zs[:-1], cls)
        zs = zs + [zs[0]]
    else:
        zs = despike(r, zs, cls)
    out = []
    for (lx, ly), z in zip(loc, zs):
        out.append([round(lx, 2), round(ly, 2), None if z is None else round(z, 2)])
    if len(out) > 1 and out[0][:2] == out[-1][:2]:
        out.pop()
    return out, missing


seen_areas, n_copies = set(), 0  # (an area on a district border is in both districts' packages, #316)
for package in packages:
    opl = package.opl
    for t in gpkg.layers(opl):
        cls = CLASSES.get(t.split("#")[-1].split("_")[0])
        if not cls:
            continue
        for f in gpkg.features(opl, t):
            if not f["geom"]:
                continue
            for rings in walk(f["geom"]):
                outer = rings[0]
                loc = [local(x, y) for x, y, *_ in outer]
                if not any(in_corridor(q) for q in loc[:: max(1, len(loc) // 50)]) and not any(in_corridor(q) for q in loc):
                    continue
                level = f.get("UrovenUmisteniObjektuZPS") or 0
                same = (cls, level, tuple((p[0], p[1]) for p in outer))
                if same in seen_areas:
                    n_copies += 1
                    continue
                seen_areas.add(same)
                r0, miss = ring(outer, level, cls)
                if miss / max(1, len(r0)) > 0.3:
                    dropped += 1
                    continue  # mostly unknown heights: would be a flat sheet at a guessed level
                a = {"c": cls, "l": level, "r": r0}
                holes = [ring(h, level, cls)[0] for h in rings[1:] if len(h) > 3]
                if holes:
                    a["h"] = holes
                areas.append(a)

# the survey's ground level against the lidar: an area steadily off IPR moves where the rails or DMR 5G confirm IPR,
# stays where they confirm the survey, and waits for the user's review where neither does (tools/zps_ground.py, #446)
import dmr5g  # noqa: E402
_truth_path = os.path.join(ROOT, "data", "truth.json")
_facts = json.load(open(_truth_path, encoding="utf-8")) if os.path.exists(_truth_path) else {}
_osm_cover, _changing, _buildings = [], [], []
try:
    import osm_local
    if osm_local.available():
        _pts = line["path"] + line.get("pathBack", [])
        _osm_cover = zps_ground.osm_covers(osm_local.ways(zps_ground.is_cover, bbox=F.bbox(_pts, 150)), F)
        _changing = zps_ground.osm_covers(osm_local.ways(zps_ground.is_changing, bbox=F.bbox(_pts, 150)), F)
        _buildings = zps_ground.osm_covers(osm_local.ways(lambda t: "building" in t, bbox=F.bbox(_pts, 220)), F)
except ImportError:
    pass
if not _osm_cover:
    print("survey ground: no OSM covers read (no extract, or no pyosmium): only the survey's upper levels cover")
_dem = dmr5g.Tiles(directory=os.path.join(ROOT, "raw", "dem"))


def _older(E, N):
    try:
        return _dem.sample(E, N)
    except (OSError, ValueError, SystemExit) as e:  # (a tile not in the snapshot: the area goes to review)
        print(f"survey ground: DMR 5G missing ({e})")
        return np.full(len(E), np.nan)


try:  # (DI's and DTMP's surveyed tracks from raw/: without them the rails decide nothing, and the build says so)
    from dtmp_tracks import archive_data, di_data
    _rails = zps_ground.rail_points(di_data()[1] + archive_data()[2])
except (ImportError, OSError) as e:
    print(f"survey ground: no surveyed rails ({e}): only DMR 5G decides")
    _rails = zps_ground.rail_points([])
ground_verdicts = zps_ground.judge(areas, lambda E, N: _ipr.sample(E, N), _older, zps_ground.cover_union(areas, _osm_cover),
                                   _rails, F, _facts.get("surveyGround", {}).get("places", []),
                                   zps_ground.cover_union([], _changing), _facts.get("surveyGround", {}).get("heldRule"),
                                   zps_ground.cover_union([], _buildings))
ground_moved = zps_ground.apply(areas, ground_verdicts)
ground_report = zps_ground.summary(ground_verdicts, ground_moved)
print("survey ground:", ground_report["areas"], ground_report["m2"], f"{ground_moved} vertices moved")
_review = zps_ground.review_set(LINE, ground_verdicts)
_review_path = os.path.join(ROOT, "reports", "review", f"survey-ground-{LINE}.json")
if _review:
    with replacing(_review_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_review, fh, ensure_ascii=False, indent=1)
elif os.path.exists(_review_path):
    os.remove(_review_path)  # (nothing held any more: the set is this build's own)

# one kerb line, two heights: the sidewalk or the road edge moves by the step (tools/kerbs.py, #21)
import kerbs  # noqa: E402
kerb_structures, kerb_low = [], []
try:  # (OSM's tunnels, bridges and other layers, and its lowered kerbs, from the snapshot's extract)
    import osm_local
    import numpy as np
    from shapely.geometry import LineString

    def _structure(t):
        if "highway" not in t and "railway" not in t:
            return False
        try:
            other = float(t.get("layer", 0)) != 0
        except ValueError:
            other = False
        return other or t.get("tunnel", "no") != "no" or t.get("bridge", "no") != "no" or t.get("covered", "no") != "no"

    if osm_local.available():
        pts = line["path"] + line.get("pathBack", [])
        for w in osm_local.ways(_structure, bbox=F.bbox(pts, 100)):
            if len(w["geometry"]) > 1:
                kerb_structures.append(LineString(np.column_stack(F.xy([g["lat"] for g in w["geometry"]], [g["lon"] for g in w["geometry"]]))))
        low = osm_local.nodes(lambda t: t.get("kerb") in kerbs.LOW_KERB)
        kerb_low = [(float(x), float(y), n["tags"]["kerb"]) for n, x, y in zip(low, *F.xy([n["lat"] for n in low], [n["lon"] for n in low]))]
except ImportError:
    pass
if not kerb_structures:
    print("kerbs: no OSM structures read (no extract, or no pyosmium): only the survey says what is on another level")
_truth = os.path.join(ROOT, "data", "truth.json")
kerb_facts = json.load(open(_truth, encoding="utf-8")).get("kerbFacts", {}).get("places", []) if os.path.exists(_truth) else []
kerb_report = kerbs.apply(areas, lambda x, y: _ipr.sample(x + F.E0, y + F.N0),
                          kerbs.surroundings(areas, kerbs.lines(wall_lines), kerb_structures), kerb_facts, kerb_low)
print("kerbs:", kerb_report["areas"], f"platform steps {kerb_report['platformSteps']}",
      f"{len(kerb_report['review'])} areas where the terrain disagrees",
      f"({sum('osmKerb' in e for e in kerb_report['review'])} with an OSM lowered or flush kerb);",
      "not kerbs:", {k: len(v) for k, v in kerb_report["notKerb"].items()})

counts = defaultdict(int)
for a in areas:
    counts[(a["c"], a["l"])] += 1
print("areas:", dict(sorted(counts.items())))
print(f"dropped {dropped} areas with >30 % unknown heights, {n_copies} copies of an area")
print(f"vertex heights: {n_z} exact, {n_near} from a boundary point within 2.5 m, {n_none} missing, "
      f"{n_deck} ground-level corners on a deck's line given the ground")
print(f"spikes along smooth outlines, taken along the ring: {sum(n_spikes.values())} {dict(sorted(n_spikes.items()))}")
out = {"areas": areas}
# the vertex heights within the survey: a 3D line's vertex at the same place, else a boundary point
# within 2.5 m, else interpolated along the ring; areas with > 30 % unknown are dropped
vertex = {"exact": n_z, "near": n_near, "missing": n_none, "deckToGround": n_deck, "droppedAreas": dropped,
          "spikes": dict(sorted(n_spikes.items()))}
nc = lambda f: sum(1 for a in areas if f(a["c"]))  # noqa: E731
out["provenance"] = sources.stamp("dtm.py", {
    "areas": sources.entry("streets", [nc(lambda c: c not in ("deck", "wall")), 0, 0],
                           checks={"vertexHeights": vertex, "kerbs": kerb_report, "surveyGround": ground_report}),
    "areas[c=deck]": sources.single("structures", "zps", nc(lambda c: c == "deck")),
    "areas[c=wall]": sources.single("walls", "zps", nc(lambda c: c == "wall"))})
out["attribution"] = sources.attribution(out["provenance"])
dst = os.path.join(ROOT, "data", f"line{LINE}.dtm.json")
with replacing(dst, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))
print(f"wrote {dst} ({os.path.getsize(dst) / 1e6:.2f} MB)")
