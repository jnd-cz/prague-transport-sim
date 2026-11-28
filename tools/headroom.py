# SPDX-License-Identifier: AGPL-3.0-or-later
"""The clearance posted for the ways our tracks run on or beside (#71): OSM's car roads and tram tracks with a numeric
`maxheight` (`maxheight:physical` first) that are not on a bridge, cut to what lies within NEAR m of a drawn track.
A road in a tunnel or on a layer under the ground is on another level than the track over it and is left out (Brusnický
tunel's 4.6 m under the tracks of lines 22 and 23, Divadelní under the embankment); a building's passage stays.

The page thins a bridge model's slab over a track by it (src/wire.js CLEARANCE: the clearance and a margin, a least slab
left; the rule of the survey's decks, tools/zps_decks.py, for the models). tools/clearances.py lists the roads that
cross under our route; this is the other case, the street that runs under a bridge with the track. `default`, `none`
and `below_default` say no number and are left out: the page then takes the legal height, as where nothing is posted.

Called by tools/clearances.py, which writes the list as the line's `headroom`: [{"p": [[x, y], ...], "mh", "src",
"kind": "car" | "tram", "name", "id": OSM's way}].
"""
import re

from shapely.geometry import LineString, MultiLineString

NEAR = 25.0  # m from a drawn track: the page takes a way's clearance within 20 m of a point over a track (src/wire.js HEADROOM_REACH)
CAR = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
       "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


def metres(v):
    """A posted height in metres ("4.3", "4,3 m", 13'6"), or None for a value with no number."""
    if v is None:
        return None
    m = re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*(m)?\s*$", v)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.match(r"^\s*([0-9]+)'\s*([0-9]+)?\"?\s*$", v)  # feet and inches
    if m:
        return round(int(m.group(1)) * 0.3048 + int(m.group(2) or 0) * 0.0254, 2)
    return None


def layer(tags):
    try:
        return int(tags.get("layer") or 0)
    except ValueError:
        return 0


def posted(elements, tracks, xy, near=NEAR):
    """The ways of `elements` (Overpass elements: ways with their `geometry`, or with `nodes` and the node elements
    beside them) that post a clearance, each cut to its parts within `near` m of `tracks` ([[x, y], ...] each).
    xy(lats, lons): the frame's conversion (tools/geo.py Frame.xy)."""
    lines = [LineString([p[:2] for p in t]) for t in tracks if len(t) > 1]
    if not lines:
        return []
    zone = MultiLineString(lines).buffer(near)
    nodes = {e["id"]: e for e in elements if e.get("type") == "node"}
    out, seen = [], set()
    for e in elements:
        t = e.get("tags") or {}
        if e.get("type") != "way" or e["id"] in seen or t.get("bridge") not in (None, "no"):
            continue  # (a way on a bridge passes over, not under)
        kind = "tram" if t.get("railway") == "tram" else "car" if t.get("highway") in CAR else None
        raw = t.get("maxheight:physical") or t.get("maxheight")
        mh = metres(raw)
        if not kind or not mh:
            continue
        if kind == "car" and (t.get("tunnel") not in (None, "no", "building_passage") or layer(t) < 0):
            continue  # (under the ground: another level than a track near it in plan)
        geom = e.get("geometry") or [nodes[n] for n in e.get("nodes", []) if n in nodes]
        if len(geom) < 2:
            continue
        seen.add(e["id"])
        part = LineString(list(zip(*xy([p["lat"] for p in geom], [p["lon"] for p in geom])))).intersection(zone)
        for g in getattr(part, "geoms", [part]):
            if g.geom_type != "LineString" or g.length < 1:
                continue
            out.append({"p": [[round(x, 1), round(y, 1)] for x, y in g.simplify(0.2).coords], "mh": mh, "src": raw,
                        "kind": kind, "name": t.get("name"), "id": e["id"]})
    out.sort(key=lambda w: (w["id"], w["p"][0]))
    return out
