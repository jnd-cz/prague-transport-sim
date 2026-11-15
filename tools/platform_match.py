# SPDX-License-Identifier: AGPL-3.0-or-later
"""The rules tools/platforms.py builds the tram platforms by (#407): which OSM platforms are tram platforms, which
stops are tram stops, which PID stop stands on which OSM platform, and what is left without one.

    python -P -E tools/test_platform_match.py      # its tests; tools/platforms.py --line N uses it
"""
import math


def _num(v):
    try:
        return float(str(v).split(";")[0])
    except (TypeError, ValueError):
        return None


def tram_platform(t):
    """A tram platform at street level, by its OSM tags. The user, 2026-11-09: metro and underground stops are not drawn,
    "they're not tram stops and don't use their stop sign, besides not being visible to the player". Tagged tram=yes:
    a tram platform wherever it is (Nádraží Zahradní Město's lies under the railway viaduct: tunnel=yes, layer -1).
    Otherwise an untagged railway=platform on the street, not a metro, train or bus one (the metro A platform at
    Náměstí Míru, 119 m under line 9's stop, was drawn as a tram platform and read as a Vienna-type stop)."""
    if t.get("tram") == "yes":
        return True
    if any(t.get(k) == "yes" for k in ("subway", "train", "light_rail", "bus")) or t.get("station") in ("subway", "train"):
        return False
    if t.get("railway") != "platform":
        return False
    level, layer = _num(t.get("level")), _num(t.get("layer"))
    return not ((level is not None and level < 0) or (layer is not None and layer != 0)
                or t.get("tunnel") in ("yes", "building_passage") or t.get("location") == "underground"
                or t.get("indoor") == "yes")


def tram_lines(rd, active):
    """{PID stop id: {line, ...}}: the tram stops and the lines on their signs. The lines of route_stops.txt, the
    regular network a sign shows (the service date's trips run its diversions: on 2026-10-21 line 17 stopped at
    Národní divadlo C/D instead of A/B, line 11 not at Krymská). Where it lists no route, at stops only some trips
    serve, the service date's tram trips that stop there (`rd`, `active` from tools/build_line.py gtfs_open): their
    regular ones, else the irregular (`exceptional`: runs to and from the depots). route_stops.txt alone left Pražský
    hrad and Královský letohrádek of lines 22 and 23 without (#407)."""
    trams = {r["route_id"]: r["route_short_name"] for r in rd("routes.txt")
             if r["route_type"] == "0" and r.get("is_substitute_transport") != "1"}
    listed = {}
    for r in rd("route_stops.txt"):
        if r["route_id"] in trams:
            listed.setdefault(r["stop_id"], set()).add(trams[r["route_id"]])
    trips = {t["trip_id"]: (trams[t["route_id"]], t.get("exceptional") == "1") for t in rd("trips.txt")
             if t["route_id"] in trams and t["service_id"] in active}
    regular, other = {}, {}
    for r in rd("stop_times.txt"):
        t = trips.get(r["trip_id"])
        if t and r["stop_id"] not in listed:
            (other if t[1] else regular).setdefault(r["stop_id"], set()).add(t[0])
    return {**{s: regular.get(s) or other[s] for s in regular.keys() | other.keys()}, **listed}


def dist(q, pts, area):
    """From the point q to an OSM platform: its line, or its area (0 inside)."""
    if area and _inside(q, pts):
        return 0.0
    best = math.inf
    segs = list(zip(pts, pts[1:] + [pts[0]])) if area else list(zip(pts, pts[1:])) or [(pts[0], pts[0])]
    for a, b in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1e-9
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / l2))
        best = min(best, math.hypot(q[0] - a[0] - dx * t, q[1] - a[1] - dy * t))
    return best


def _inside(q, pts):
    x, y, c = q[0], q[1], False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + [pts[0]]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


SIDE = 12.0    # m: a platform beside a path lies within this of it (src/game.js _buildPlatforms)
AHEAD = 45.0   # m: a stop point past the end OSM drew its platform to (Klamovka A on line 9: 38 m)
PIECES = 15.0  # m: the gap between OSM's pieces of one platform (Lazarská on Spálená: 11 and 14 m)
ON_TRACK = 1.5  # m off a path's centre line: a point within the tram's outline, on neither side


def beside(pts, rt):
    """(side, s0, s1, d) of points beside a path (`rt`: tools/placement.py Route, the game's sampling): side -1 right of
    it, +1 left, d their mean distance; None over SIDE m from it."""
    proj = [rt.nearest(x, y) for x, y in pts]
    if any(s is None for s, _ in proj) or sum(d for _, d in proj) / len(proj) > SIDE:
        return None
    lat = 0.0
    for (x, y), (s, _) in zip(pts, proj):
        qx, qy, hx, hy = rt.at(s)
        lat += hx * (y - qy) - hy * (x - qx)
    return (1 if lat > 0 else -1), min(s for s, _ in proj), max(s for s, _ in proj), sum(d for _, d in proj) / len(proj)


def nearest_path(pts, paths):
    """(path, beside(...)) for the path the points lie nearest, as the game draws a platform along; None off them."""
    return min(((rt, b) for rt in paths if (b := beside(pts, rt))), key=lambda t: t[1][3], default=None)


def match(platforms, stops, paths=(), reach=25.0):
    """{platform index: stop index}: each PID stop on the OSM platform nearest to it, the nearest pairs first, one stop
    per platform. Beside a path (`paths`: the routes) only on the platform's side of the track, its direction's: within
    `reach` m, or up to AHEAD m past its end (the stop point is where the tram front stops, which can stand past the end
    OSM drew). Off the paths within `reach` m. (Each platform in the extract's order taking its nearest stop while free
    gave a stop to the neighbour that came first: Lazarská, Výstaviště, Klamovka ... were left without theirs; by
    distance alone Vršovické náměstí's B went across the tracks to A's platform, #407.)"""
    on = [nearest_path([q[:2] for q in p["p"]], paths) for p in platforms]
    pairs = []
    for j, p in enumerate(platforms):
        for i, s in enumerate(stops):
            d = dist(s["q"], p["p"], p.get("area"))
            if d >= AHEAD:
                continue
            if on[j]:
                rt, (side, s0, s1, _) = on[j]
                b = beside([s["q"]], rt)
                # (a point on the track itself has no side: PID's Pražský hrad B stands 0.6 m off the centre line)
                if not b or (b[0] != side and b[3] > ON_TRACK) or not (d < reach or s1 < b[1] < s1 + AHEAD):
                    continue
            elif d >= reach:
                continue
            pairs.append((d, j, i))
    out, used = {}, set()
    for d, j, i in sorted(pairs):
        if j in out or i in used:
            continue
        out[j] = i
        used.add(i)
    return out


def near(a, b):
    """The least distance between two OSM platforms' outlines (their points against the other's lines)."""
    return min(min(dist(q, b["p"], b.get("area")) for q in a["p"]), min(dist(q, a["p"], a.get("area")) for q in b["p"]))


TWIN = 2.5  # m: off the routes, a platform's other OSM way touches it


def leftovers(platforms, paths=()):
    """Marks each OSM platform without a PID stop (`stop`): `twin` where it is a piece of one with it (OSM draws one
    platform as several ways: Flora and Malostranská overlap theirs, Lazarská's lie 11-14 m apart along Spálená): on
    the same side of a path it is beside, overlapping or under PIECES m apart along it, or off the paths touching it;
    else `unused` (no tram stops there on the service date: drawn, its sign without the lines' plate; the user,
    2026-11-09: "If they are real I would draw them but mark them as not currently in use")."""
    with_stop = [p for p in platforms if p.get("stop")]
    for p in platforms:
        if p.get("stop"):
            continue
        on = nearest_path([q[:2] for q in p["p"]], paths)
        if on:
            rt, b = on
            twin = any((c := beside([x[:2] for x in q["p"]], rt)) and c[0] == b[0] and c[1] < b[2] + PIECES and b[1] < c[2] + PIECES
                       for q in with_stop)
        else:
            twin = any(near(p, q) <= TWIN for q in with_stop)
        p["twin" if twin else "unused"] = 1
