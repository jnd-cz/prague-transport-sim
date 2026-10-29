"""OSM from a local extract instead of the public Overpass servers (user, 2026-10-23: build the whole city
network and keep the servers less loaded).

Source: Geofabrik's daily Czech Republic extract (download.geofabrik.de/europe/czech-republic, ODbL), kept
in raw/osm/. `cut` makes raw/osm/praha.osm.pbf (Prague and a margin, complete ways and relations: every
node a way uses and every member a relation has, even outside the box). `query` answers like Overpass
(`{"elements": [{"type": "way", "id", "tags", "geometry": [{"lat", "lon"}]}]}`), so the import tools
switch over by calling it instead of overpass.query.

Usage:  python -P -E tools/osm_local.py cut [raw/osm/czech-republic-YYMMDD.osm.pbf]
        python -P -E tools/osm_local.py stats
In a tool:  from osm_local import available, ways
            if available(): els = ways(lambda t: t.get("public_transport") == "platform", bbox=(s, w, n, e))
"""
import glob
import math
import os
import sys
import time

import osmium

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
from geo import Frame  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw", "osm")
PRAHA = os.path.join(DIR, "praha.osm.pbf")
BOX = (49.90, 14.15, 50.21, 14.75)  # s, w, n, e: Prague (49.94-50.18, 14.22-14.71) and ~3 km around


def available():
    return os.path.exists(PRAHA)


def base_id():
    """Identity of the extract the answers come from (the first 16 hex of its SHA-256): derived caches
    (build_line.py's raw/lineN/*.json) are reused only while it is the same file."""
    side = PRAHA + ".sha256"
    st = os.stat(PRAHA)
    key = f"{st.st_size}:{int(st.st_mtime)}"
    if os.path.exists(side):
        k, _, h = open(side, encoding="utf-8").read().strip().partition(" ")
        if k == key:
            return h
    import hashlib
    hs = hashlib.sha256()
    with open(PRAHA, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            hs.update(b)
    h = hs.hexdigest()[:16]
    open(side, "w", encoding="utf-8").write(f"{key} {h}\n")
    return h


def answer_key(query):
    """Identity of one emulated answer: the extract, the query text, and the code that answers it (this
    file and geo.py: the corridor queries measure their radius in the city frame). The extract alone kept
    answers from the old per-line frames after #7 (lines 9 and 23 published with them, #87). Any edit to
    either file recomputes the answers, ~1 min a line."""
    import hashlib
    hs = hashlib.sha256(query.encode("utf-8"))
    for f in (__file__, os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo.py")):
        with open(f, "rb") as fh:
            hs.update(fh.read().replace(b"\r\n", b"\n"))  # (the same key on a CRLF checkout)
    return f"{base_id()}-{hs.hexdigest()[:12]}"


def cut(src=None):
    src = src or sorted(glob.glob(os.path.join(DIR, "czech-republic-*.osm.pbf")))[-1]
    s, w, n, e = BOX
    t0 = time.time()
    ids = osmium.IdTracker()  # the box's nodes and the ways using them
    counts = {"n": 0, "w": 0, "r": 0}
    tmp = PRAHA.replace(".osm.pbf", ".part.osm.pbf")  # (the writer takes the format from the extension)
    if os.path.exists(tmp):
        os.remove(tmp)
    with osmium.BackReferenceWriter(tmp, ref_src=src, overwrite=True) as out:
        # (a PBF holds nodes, then ways, then relations: one pass sees the box's nodes before the ways)
        for o in osmium.FileProcessor(src):
            if o.is_node():
                if o.location.valid() and s <= o.location.lat <= n and w <= o.location.lon <= e:
                    ids.add_node(o.id)
                    out.add_node(o)
                    counts["n"] += 1
            elif o.is_way():
                if ids.contains_any_references(o):
                    ids.add_way(o.id)
                    out.add_way(o)
                    counts["w"] += 1
            elif o.is_relation():
                if ids.contains_any_references(o):
                    out.add_relation(o)
                    counts["r"] += 1
    os.replace(tmp, PRAHA)
    print(f"{PRAHA}: {counts['n']} nodes, {counts['w']} ways, {counts['r']} relations in the box "
          f"(+ their references), {os.path.getsize(PRAHA) / 1e6:.0f} MB, {time.time() - t0:.0f} s")


def ways(match, bbox=None, src=None):
    """Ways whose tags satisfy match(tags: dict) and that touch bbox (s, w, n, e), as Overpass elements."""
    src = src or PRAHA
    out = []
    # (the nodes are read too, for the location cache; only tagged ways get past the filter)
    fp = osmium.FileProcessor(src, osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for o in fp.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(osmium.filter.EmptyTagFilter()):
        tags = dict(o.tags)
        if not match(tags):
            continue
        geom = [{"lat": r.location.lat, "lon": r.location.lon} for r in o.nodes if r.location.valid()]
        if len(geom) < 2:
            continue
        if bbox and not any(bbox[0] <= g["lat"] <= bbox[2] and bbox[1] <= g["lon"] <= bbox[3] for g in geom):
            continue
        out.append({"type": "way", "id": o.id, "tags": tags, "nodes": [r.ref for r in o.nodes], "geometry": geom})
    return out


def relations(match, src=None):
    """Relations whose tags satisfy match(tags), with their members (type n/w/r as node/way/relation)."""
    kinds = {"n": "node", "w": "way", "r": "relation"}
    return [{"type": "relation", "id": o.id, "tags": dict(o.tags),
             "members": [{"type": kinds[m.type], "ref": m.ref, "role": m.role} for m in o.members]}
            for o in osmium.FileProcessor(src or PRAHA, osmium.osm.RELATION) if match(dict(o.tags))]


def nodes(match, src=None):
    """Tagged nodes whose tags satisfy match(tags), as Overpass `out body` nodes."""
    out = []
    for o in osmium.FileProcessor(src or PRAHA, osmium.osm.NODE).with_filter(osmium.filter.EmptyTagFilter()):
        tags = dict(o.tags)
        if o.location.valid() and match(tags):
            out.append({"type": "node", "id": o.id, "lat": o.location.lat, "lon": o.location.lon, "tags": tags})
    return out


def node_coords(ids, src=None):
    want, out = set(ids), {}
    for o in osmium.FileProcessor(src or PRAHA, osmium.osm.NODE):
        if o.id in want and o.location.valid():
            out[o.id] = (o.location.lat, o.location.lon)
    return out


# ---------------------------------------------------------------- tools/build_line.py's queries
# build_line asks Overpass by name; with the extract present the same answers come from here. The
# corridor queries select things "around" the route ways (.w: a relation's ways, or way(id:...)).
HW = "^(motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street|service|pedestrian|footway|primary_link|secondary_link|tertiary_link|trunk_link)$"
GREEN = ("^(grass|forest|meadow|recreation_ground|village_green|cemetery|allotments)$", "^(park|garden|pitch)$",
         "^(wood|scrub|grassland)$")


def _kinds(t):
    """Which of build_line's way queries a way's tags can answer (the same tests as emulate's)."""
    import re
    k = []
    if t.get("railway") in ("tram", "light_rail"):
        k.append("tracks")
    if t.get("public_transport") == "platform" or t.get("railway") == "platform":
        k.append("platforms")
    if "building" in t:
        k.append("buildings")
    if re.match(HW, t.get("highway", "")):
        k.append("roads")
    if (re.match(GREEN[0], t.get("landuse", "")) or re.match(GREEN[1], t.get("leisure", ""))
            or re.match(GREEN[2], t.get("natural", ""))):
        k.append("green")
    if t.get("natural") == "water":
        k.append("water")
    return k


_STORE = None
# build_line's "points": which tagged nodes, and how far around the route ways (m)
POINT_RULES = [(lambda t: t.get("highway") == "traffic_signals", 35),
               (lambda t: t.get("railway") in ("tram_level_crossing", "level_crossing", "tram_crossing", "crossing"), 6),
               (lambda t: t.get("highway") == "crossing", 15)]


def _store():
    """Everything build_line's queries read, from one pass over the extract (once per process; a line's
    build asked for ~25 passes before): relations, tagged nodes, and the tagged ways any query can return,
    each list in file order, so the answers are the same as from the separate passes. Kept compact (the
    store is per build process, and lines build side by side): a way is (file sequence, id, tags as JSON
    text, node refs, lat/lon pairs) in arrays, and tags are decoded only for what a query returns
    (Prague: ~0.6 GB, against 2.9 GB as dicts)."""
    global _STORE
    if _STORE is not None:
        return _STORE
    import json
    from array import array
    t0 = time.time()
    rels = relations(lambda t: True)
    ways_, by_kind = {}, {k: [] for k in ("tracks", "platforms", "buildings", "roads", "green", "water")}
    node_tags, points = {}, []
    member_ways = {m["ref"] for r in rels for m in r["members"] if m["type"] == "way"}
    seq = 0
    fp = osmium.FileProcessor(PRAHA, osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for o in fp.with_filter(osmium.filter.EmptyTagFilter()):
        if o.is_node():
            if o.location.valid():
                tags = dict(o.tags)
                node_tags[o.id] = json.dumps(tags)
                if any(f(tags) for f, _ in POINT_RULES):
                    points.append({"type": "node", "id": o.id, "lat": o.location.lat, "lon": o.location.lon, "tags": tags})
            continue
        seq += 1
        tags = dict(o.tags)
        kinds = _kinds(tags)
        if not kinds and o.id not in member_ways:
            continue
        c = array("d")
        for q in o.nodes:
            if q.location.valid():
                c.append(q.location.lat)
                c.append(q.location.lon)
        if len(c) < 4:
            continue
        w = (seq, o.id, json.dumps(tags), array("q", (q.ref for q in o.nodes)), c)
        ways_[o.id] = w
        for k in kinds:
            by_kind[k].append(w)
    _STORE = {"rels": rels, "node_tags": node_tags, "points": points, "ways": ways_, "kinds": by_kind}
    print(f"  local extract read once: {len(rels)} relations, {len(node_tags)} tagged nodes, {len(ways_)} ways, "
          f"{time.time() - t0:.0f} s")
    return _STORE


def _way(w):
    """A stored way as the Overpass-like element `ways()` gives."""
    import json
    _, wid, tags, refs, c = w
    return {"type": "way", "id": wid, "tags": json.loads(tags), "nodes": list(refs),
            "geometry": [{"lat": c[i], "lon": c[i + 1]} for i in range(0, len(c), 2)]}


def _ways_by_id(ids):
    """The tagged ways with these ids, in file order (as `ways(lambda t: True)` filtered by id); a way
    the store did not keep (not a relation member, no query's tags) costs one more pass."""
    from array import array
    st = _store()
    got = [st["ways"][i] for i in ids if i in st["ways"]]
    missing = set(ids) - set(st["ways"])
    if missing:
        import json
        seq = 0
        fp = osmium.FileProcessor(PRAHA, osmium.osm.NODE | osmium.osm.WAY).with_locations()
        for o in fp.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)).with_filter(osmium.filter.EmptyTagFilter()):
            seq += 1
            if o.id not in missing:
                continue
            c = array("d", (v for q in o.nodes if q.location.valid() for v in (q.location.lat, q.location.lon)))
            if len(c) >= 4:
                got.append((seq, o.id, json.dumps(dict(o.tags)), array("q", (q.ref for q in o.nodes)), c))
    return [_way(w) for w in sorted(got, key=lambda w: w[0])]


def emulate(name, query):
    """Overpass JSON for one of build_line.py's named queries, from the local extract."""
    import re

    import shapely
    from shapely.geometry import LineString, Point
    t0 = time.time()
    if name == "relations":
        ref = re.search(r'\[ref="([^"]+)"\]', query).group(1)
        els = [{k: v for k, v in r.items() if k != "members"} for r in _store()["rels"]
               if r["tags"].get("type") == "route" and r["tags"].get("route") == "tram" and r["tags"].get("ref") == ref]
        return {"elements": els}
    if name.startswith("route_"):
        rid = int(name[6:])
        rel = next(r for r in _store()["rels"] if r["tags"].get("route") == "tram" and r["id"] == rid)
        wids = {m["ref"] for m in rel["members"] if m["type"] == "way"}
        ws = _ways_by_id(wids)
        nds = {}
        for w in ws:
            for nid, g in zip(w["nodes"], w["geometry"]):
                nds[nid] = g
        out = [rel] + [{"type": "way", "id": w["id"], "nodes": w["nodes"], "tags": w["tags"]} for w in ws]
        out += [{"type": "node", "id": k, "lat": g["lat"], "lon": g["lon"]} for k, g in nds.items()]
        return {"elements": out}
    if name == "network_tracks":
        ws = [_way(w) for w in _store()["kinds"]["tracks"]]
        out = [{"type": "way", "id": w["id"], "nodes": w["nodes"], "tags": w["tags"]} for w in ws]
        seen = {}
        for w in ws:
            for nid, g in zip(w["nodes"], w["geometry"]):
                seen[nid] = g
        out += [{"type": "node", "id": k, "lat": g["lat"], "lon": g["lon"]} for k, g in seen.items()]
        return {"elements": out}
    # the corridor: the route ways .w as local metres (equirectangular about their middle)
    m = re.search(r"relation\((\d+)\)->\.r;way\(r\.r\)->\.w;", query)
    if m:
        rid = int(m.group(1))
        rel = next(r for r in _store()["rels"] if r["tags"].get("route") == "tram" and r["id"] == rid)
        wids = {mm["ref"] for mm in rel["members"] if mm["type"] == "way"}
    else:
        wids = {int(x) for x in re.search(r"way\(id:([0-9,]+)\)->\.w;", query).group(1).split(",")}
    rw = _ways_by_id(wids)
    F = Frame()
    xy = lambda g: tuple(float(v) for v in F.xy(g["lat"], g["lon"]))  # noqa: E731
    route = shapely.union_all([LineString([xy(g) for g in w["geometry"]]) for w in rw if len(w["geometry"]) > 1])
    zones = {}

    def zone(r):
        if r not in zones:
            zones[r] = route.buffer(r)
            shapely.prepare(zones[r])
        return zones[r]

    def near(geom, r):
        g = Point(xy(geom[0])) if len(geom) == 1 else LineString([xy(q) for q in geom])
        return zone(r).intersects(g)

    def near_way(w, r):
        """near() for a stored way (its lat/lon pairs converted at once)."""
        c = __import__("numpy").frombuffer(w[4], dtype=float)
        x, y = F.xy(c[0::2], c[1::2])
        return zone(r).intersects(LineString(list(zip(x.tolist(), y.tolist()))))

    radius = lambda: int(re.search(r"around\.w:(\d+)", query).group(1))  # noqa: E731
    if name == "tracks":
        ws = [_way(w) for w in _store()["kinds"]["tracks"] if near_way(w, radius())]
        nds = {}
        for w in ws:
            for nid, g in zip(w["nodes"], w["geometry"]):
                nds[nid] = g
        nt = _store()["node_tags"]
        tagged = {k: __import__("json").loads(nt[k]) for k in nds if k in nt}
        out = [{"type": "way", "id": w["id"], "nodes": w["nodes"], "tags": w["tags"]} for w in ws]
        out += [{"type": "node", "id": k, "lat": g["lat"], "lon": g["lon"], **({"tags": tagged[k]} if k in tagged else {})} for k, g in nds.items()]
        res = {"elements": out}
    elif name == "points":
        res = {"elements": [n for n in _store()["points"] if any(f(n["tags"]) and near([n], r) for f, r in POINT_RULES)]}
    else:
        r = radius()
        ws = [_way(w) for w in _store()["kinds"][name] if near_way(w, r)]
        els = [{"type": "way", "id": w["id"], "tags": w["tags"], "geometry": w["geometry"]} for w in ws]
        if name == "water":
            # multipolygons: members with their geometry (Overpass `out geom`)
            rels = [rr for rr in _store()["rels"] if rr["tags"].get("natural") == "water"]
            mids = {mm["ref"] for rr in rels for mm in rr["members"] if mm["type"] == "way"}
            geo = {w["id"]: w["geometry"] for w in _ways_by_id(mids)} if mids else {}
            untagged = mids - set(geo)
            if untagged:  # (member ways without tags: the location pass over all ways)
                fp = osmium.FileProcessor(PRAHA, osmium.osm.NODE | osmium.osm.WAY).with_locations()
                for o in fp.with_filter(osmium.filter.EntityFilter(osmium.osm.WAY)):
                    if o.id in untagged:
                        geo[o.id] = [{"lat": q.location.lat, "lon": q.location.lon} for q in o.nodes if q.location.valid()]
            for rr in rels:
                mem = [{**mm, "geometry": geo[mm["ref"]]} for mm in rr["members"] if mm["type"] == "way" and mm["ref"] in geo]
                if any(len(mm["geometry"]) > 1 and near(mm["geometry"], r) for mm in mem):
                    els.append({"type": "relation", "id": rr["id"], "tags": rr["tags"], "members": mem})
        res = {"elements": els}
    print(f"  local {name}: {len(res['elements'])} elements, {time.time() - t0:.0f} s")
    return res


def stats():
    t0 = time.time()
    k = {"nodes": 0, "ways": 0, "relations": 0, "tram ways": 0, "tram routes": 0, "platforms": 0}
    for o in osmium.FileProcessor(PRAHA):
        if o.is_node():
            k["nodes"] += 1
        elif o.is_way():
            k["ways"] += 1
            if o.tags.get("railway") == "tram":
                k["tram ways"] += 1
            if o.tags.get("public_transport") == "platform" or o.tags.get("railway") == "platform":
                k["platforms"] += 1
        else:
            k["relations"] += 1
            if o.tags.get("route") == "tram":
                k["tram routes"] += 1
    print(k, f"{time.time() - t0:.0f} s")


if __name__ == "__main__":
    if sys.argv[1:2] == ["cut"]:
        cut(sys.argv[2] if len(sys.argv) > 2 else None)
    elif sys.argv[1:2] == ["stats"]:
        stats()
    else:
        print(__doc__)
