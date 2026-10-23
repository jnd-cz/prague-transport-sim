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
import os
import sys
import time

import osmium

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "raw", "osm")
PRAHA = os.path.join(DIR, "praha.osm.pbf")
BOX = (49.90, 14.15, 50.21, 14.75)  # s, w, n, e: Prague (49.94-50.18, 14.22-14.71) and ~3 km around


def available():
    return os.path.exists(PRAHA)


def cut(src=None):
    src = src or sorted(glob.glob(os.path.join(DIR, "czech-republic-*.osm.pbf")))[-1]
    s, w, n, e = BOX
    t0 = time.time()
    ids = osmium.IdTracker()  # the box's nodes and the ways using them
    counts = {"n": 0, "w": 0, "r": 0}
    tmp = PRAHA + ".part"
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
    for o in osmium.FileProcessor(src, osmium.osm.WAY).with_locations().with_filter(osmium.filter.EmptyTagFilter()):
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
