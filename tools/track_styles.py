# SPDX-License-Identifier: AGPL-3.0-or-later
"""The line's track styles, built offline (#276 step 2, #479): one implementation of the user's marks and the survey's
grass track, read by the page (src/heights.js) and the height import (tools/track_decks.py).

    python -P -E tools/track_styles.py --line 22     # writes `styles` into data/line22.json

- **The user's marks** (data/truth.json `trackStyles`, by stops so they hold in any frame): from the first stop of the
  mark's `from` name to the next stop of its `to` name; a mark with `between` runs between its two ends, each a lat,
  lon point (the route position nearest it) or a stop name (that stop nearest the point end).
- **The grassed-track list** (data/truth.json `grassTrack`, prazsketramvaje.cz): every line passing both stops of a
  stretch takes it, each time it passes them (an out-and-back line twice). Where the user's marks cover the track they
  win, and what is left of a stretch stays if MIN_GRASS long.
- **The survey's grass track:** a `green` area under the track axis (the survey's ground-level area at the route,
  data/lineN.dtm.json) for MIN_GRASS metres and more, read every SAMPLE m, runs less than JOIN m apart one section.
  The facts (the user's marks, the list) win where they overlap (line 22 Koh-i-noor - Slavia, whose bank fell 0.5 m
  across the rails).

- **The answered review** (data/truth.json `grassReview`, tools/grass_review.py): OSM's grass the user confirmed,
  between the card's two points; as strong as the user's marks.
- **The holes** (#503; the user, 2026-11-12: "the green cover is not placed around stop platforms on either side and
  road, pedestrian crossings, junctions. Open ballast can be nect to stops but elso end before road and pedestrian
  crossings"): grass and ballast stop at streets, paths and footways crossing at street level and OSM's crossing
  nodes; grass also at the platforms beside either track. Not at switches and diamonds (open ballast runs through
  them; one in a street lies in its hole). HOLE metres past each, measured on
  OSM's grass areas inside the known spans (tools/grass_review.py prints how near). A street across the track is an
  `embedded` section; pieces under MIN_PIECE between two holes are left out.

- **Junctions and road crossings** (#546; the user, 2026-11-13: "the track styles don't switch at the
  expected places like in junctions (expected embedded asphalt color) and crossing roadway across track isn't
  displayed in full width"): where no section says otherwise, the track is `embedded` over a carriageway crossing it
  (the survey's carriageway at our axis through the crossing point, CROSS_REACH m past OSM's width at most, else
  OSM's width at its angle; a way without OSM's car flag counts where the survey has carriageway at the crossing
  point, a service road at Řepy), a switch (SWITCH_PAD m before it to SWITCH_PAD past its frog) and a diamond (a drawn
  track crossing ours at DIAMOND_MIN° or more, where the two beds overlap). Pieces less than MIN_PIECE apart join.
  Grass yields to them too (the user, 2026-11-13: "for the roads crossing tracks and junctions I would default to
  embedded asphalt style"); open ballast keeps its switches (#503) and the user's marks of another style win. The
  survey's carriageway is read at crossing
  points only: along the route its road areas run over grass track it does not map (line 22 at Pohořelec). Embedded
  and panels stand the same height over the bed (`railAboveDeck`), so this moves no height.

- **Every other drawn track** (`track_sections`, written as the track's `styles`, [[s0, s1, style]] along its `p`; the
  page draws a track within NEAR_ROUTE m of our route in the route's style): embedded at its own road crossings,
  diamonds and switches by the same rule, grass where the survey's green lies under it, panels elsewhere. The survey
  reaches only near our route and OSM maps almost no grass over these tracks (0-380 m of 14-21 km per line), so
  they get no grass where neither has it.

`styles` is a list of {s0, s1, style, source, mark | stretch | card | hole}, by s0: `source` 'user', 'review', 'list',
'survey' or 'hole'; `mark` is the index of the user's mark in truth.json `trackStyles`, `stretch` the index in
`grassTrack.stretches`, `card` the review card's id. How high the rails stand over each style is a fact in truth.json (`railAboveDeck`), which the
page reads with the sections. Where ground-level areas overlap at a point, the higher rank counts. The page picked the
one whose surface lay nearest the lidar ground, then the rank (src/terrain.js DtmSurface._hitTri): on all five lines
the two agree at every sample (21,641, #479).
"""
import json
import math
from pathlib import Path
import sys

import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
from route import Route  # noqa: E402
import track_beds  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE, MIN_GRASS, JOIN = 4, 20, 30   # m (src/heights.js trackStyles until #479)
# The holes (#503), m beyond the thing itself: where OSM maps grass inside the known spans (2026-11-12), its areas
# end 2-5 m short of a footway crossing, 5-15 m of a street's edge and 3-4 m of a platform.
HOLE = {"footway": 3, "road": 8, "node": 5, "platform": 3}
PLATFORM_NEAR = 6      # m from our axis: our platform and the other direction's beside the other track
MIN_PIECE = MIN_GRASS  # m: a shorter piece left between two holes is not laid (OSM maps none of the 12-14 m ones)
MIN_EMBEDDED = 5       # m: a street's hole the section's end cuts shorter is not an embedded section of its own
# Junctions and road crossings in paved track (#546): embedded over the junction and the carriageway's width
SWITCH_PAD = 3         # m before a switch's start and past its frog: the switch's own length beyond the two points
DIAMOND_MIN = 20       # degrees: another track crossing ours more shallowly is a turnout leaving it, not a diamond
BED = 2.7              # m: a bed's width (src/world.js), the extent a diamond covers on ours
PAVED_IN = ("embedded", "setts")   # the styles a junction's pieces join across (#574: setts as embedded)
SURFACE_STYLE = {"setts": "setts", "embedded": "embedded", "panels": "panels", "grass": "grass"}  # answer -> style
CROSS_REACH = 6        # m past OSM's carriageway half-width that the survey's road at the axis may still extend it
BRIDGE_HEAD = 6        # m inside a bridge's ends (OSM's) where a way across still meets the track at grade (on_bridge)
CARRIAGEWAY = ("road", "parking")   # survey classes of a carriageway
NEAR_ROUTE = 6         # m: a drawn track this near our route takes the route's style (src/world.js styleAt)
BRANCH = 15            # m of a track along where another one leaves it, or it leaves another: the switch
RAMP, LIFT_STEP = 15, 2  # m: a style's offset blends in over RAMP inside its section; `lift` every LIFT_STEP m
RANK = {"tram": 9, "road": 8, "island": 7, "platform": 7, "sidewalk": 6, "parking": 5, "cycle": 5, "paved": 4,
        "stairs": 3, "green": 2, "water": 1}   # (src/terrain.js SURFACE_RANK)


def ground_area(a):
    """A survey area the page lays at ground level (src/terrain.js groundArea)."""
    return a.get("l") == 0 and a["c"] not in ("wall", "roof", "deck") and (a["c"] != "rail" or a.get("g"))


class Survey:
    """The survey's ground-level class at a point."""

    def __init__(self, dtm):
        self.areas, polys = [], []
        for a in dtm.get("areas", []):
            if not ground_area(a) or len(a["r"]) < 3:
                continue
            p = Polygon([q[:2] for q in a["r"]], [[q[:2] for q in h] for h in a.get("h", []) if len(h) >= 3])
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty:
                continue
            self.areas.append(a["c"])
            polys.append(p)
        self.polys = polys
        self.tree = shapely.STRtree(polys) if polys else None

    def class_at(self, x, y):
        if self.tree is None:
            return None
        pt = Point(x, y)
        hits = [int(k) for k in self.tree.query(pt) if self.polys[int(k)].covers(pt)]
        if not hits:
            return None
        return self.areas[max(hits, key=lambda k: RANK.get(self.areas[k], 1))]

    def classes_at(self, x, y):
        if self.tree is None:
            return set()
        pt = Point(x, y)
        return {self.areas[int(k)] for k in self.tree.query(pt) if self.polys[int(k)].covers(pt)}

    def carriageway(self, x, y):
        """Only a carriageway at the point: a road or parking area and no track or green area over it. Read where a way
        crosses the route, not along it: the survey's road areas run over grass track it does not map (line 22 at
        Pohořelec, 522 m of the user's grass with no green or tram area within 4 m of the axis)."""
        c = self.classes_at(x, y)
        return bool(c & set(CARRIAGEWAY)) and not c & {"tram", "green", "rail"}


def passes(stops, a, b):
    """Each pass of the route between stop names a and b, either way: (s0, s1), no other stop of either name between."""
    idx = [(i, st["name"]) for i, st in enumerate(stops) if st["name"] in (a, b)]
    return [(min(stops[i]["s"], stops[j]["s"]), max(stops[i]["s"], stops[j]["s"]))
            for (i, n), (j, m) in zip(idx, idx[1:]) if n != m]


def minus(s0, s1, cover):
    """What of [s0, s1] the sections in cover leave."""
    out = [(s0, s1)]
    for c in cover:
        out = [p for a, b in out for p in ((a, min(b, c["s0"])), (max(a, c["s1"]), b)) if p[1] > p[0]]
    return out


def holes(data, survey=None):
    """Where grass and ballast track stop along the route (#503): [{s0, s1, kind, grass}], `grass` the holes only grass
    track has (platforms). The route is walked every metre, so a place passed twice (an out-and-back line) has a hole
    on each pass."""
    rt = Route(data["path"], data.get("pathExt"))
    n = int(rt.length) + 1
    pts = [rt.at(min(s, rt.length))[:2] for s in range(n + 1)]
    out = []
    # platforms beside either track: both directions' (PLATFORM_NEAR of the axis), and our stops' own extents
    plats = [Polygon([q[:2] for q in pl["p"]]) for pl in data.get("platforms", []) if len(pl["p"]) >= 3]
    plats = [p if p.is_valid else p.buffer(0) for p in plats]
    if plats:
        tree, run, hit = shapely.STRtree(plats), None, set()
        for s in range(n + 2):
            near = {int(k) for k in tree.query(Point(pts[s]), predicate="dwithin", distance=PLATFORM_NEAR)} if s <= n else set()
            if near and run is None:
                run = s
            hit |= near
            if not near and run is not None:
                # (the platforms' own length along this pass, not the reach of PLATFORM_NEAR past their ends)
                a = max(0, run - 2 * PLATFORM_NEAR)
                piece = LineString(pts[a:min(n, s + 2 * PLATFORM_NEAR) + 1])
                ss = [a + piece.project(Point(q)) for k in hit for q in plats[k].exterior.coords]
                out.append({"s0": min(ss) - HOLE["platform"], "s1": max(ss) + HOLE["platform"], "kind": "platform", "grass": True})
                run, hit = None, set()
    for st in data["stops"]:
        if st.get("p0") is not None:
            out.append({"s0": st["p0"] - HOLE["platform"], "s1": st["p1"] + HOLE["platform"], "kind": "platform", "grass": True})
    # streets, paths and footways across the route at street level (as src/game.js _routeConflicts finds them)
    segs, kinds = [], []
    for r in data.get("roads", []):
        if r.get("t") or r.get("b"):
            continue
        # (a way that is no footway is a road where OSM lets cars on it, or where the survey has carriageway where it
        # crosses: a service road, #546)
        kind = "road" if r.get("c") and not r.get("f") else "footway" if r.get("f") else "way"
        for a, b in zip(r["p"], r["p"][1:]):
            segs.append(LineString([a[:2], b[:2]]))
            kinds.append((kind, r.get("w") or 3))
    bridged = on_bridge(data)
    if segs:
        tree = shapely.STRtree(segs)
        for s in range(n):
            step = LineString([pts[s], pts[s + 1]])
            for k in tree.query(step, predicate="intersects"):
                seg, (kind, w) = segs[int(k)], kinds[int(k)]
                (ax, ay), (bx, by) = seg.coords
                L = seg.length or 1e-9
                hx, hy = pts[s + 1][0] - pts[s][0], pts[s + 1][1] - pts[s][1]
                hl = (hx * hx + hy * hy) ** 0.5 or 1e-9
                cos = abs(((bx - ax) * hx + (by - ay) * hy) / (L * hl))
                if cos >= 0.95:   # (a street along the track, not across it)
                    continue
                at = seg.intersection(step).representative_point()
                c = s + step.project(at)
                if bridged(c):
                    continue
                if kind == "way":
                    kind = "road" if survey is not None and survey.carriageway(at.x, at.y) else "footway"
                half = w / 2 / max(0.3, (1 - cos * cos) ** 0.5)
                out.append({"s0": c - half - HOLE[kind], "s1": c + half + HOLE[kind], "kind": kind, "grass": False})
    for s in data.get("crossings", []):   # (OSM's crossing nodes on the track)
        out.append({"s0": s - HOLE["node"], "s1": s + HOLE["node"], "kind": "footway", "grass": False})
    # (no holes at switches and diamonds: the user, 2026-11-12, #503: "I wouldn't make holes for switches and
    # diamonds, the branch to depo hostivař loop has open ballast including switches. They are covered if they lie
    # on paved surface", which the streets' holes already are)
    return sorted(out, key=lambda h: h["s0"])


def crossing_roads(data, rt):
    """Ways across the route at street level that may be carriageways (not footways; as `holes` finds them):
    [(s, half, w, cars)], `half` the half length a way of width w covers along the route at its angle, `cars` OSM's
    car road flag."""
    segs, ws = [], []
    for r in data.get("roads", []):
        if r.get("t") or r.get("b") or r.get("f"):
            continue
        for a, b in zip(r["p"], r["p"][1:]):
            segs.append(LineString([a[:2], b[:2]]))
            ws.append((r.get("w") or 3, bool(r.get("c"))))
    out = []
    if not segs:
        return out
    bridged = on_bridge(data)
    tree = shapely.STRtree(segs)
    n = int(rt.length) + 1
    pts = [rt.at(min(s, rt.length))[:2] for s in range(n + 1)]
    for s in range(n):
        step = LineString([pts[s], pts[s + 1]])
        for k in tree.query(step, predicate="intersects"):
            seg, (w, cars) = segs[int(k)], ws[int(k)]
            (ax, ay), (bx, by) = seg.coords
            hx, hy = pts[s + 1][0] - pts[s][0], pts[s + 1][1] - pts[s][1]
            cos = abs(((bx - ax) * hx + (by - ay) * hy) / ((seg.length or 1e-9) * ((hx * hx + hy * hy) ** 0.5 or 1e-9)))
            if cos >= 0.95:
                continue
            c = s + step.project(seg.intersection(step).representative_point())
            if bridged(c):
                continue
            out.append((c, w / 2 / max(0.3, (1 - cos * cos) ** 0.5), w, cars))
    return out


def on_bridge(data):
    """Whether route position s lies on one of the route's bridges (`bridges`, OSM's, build_line.py) more than BRIDGE_HEAD
    m inside its ends: a way the route crosses there runs under the deck, not across the track (line 37's Krejcárek
    viaduct: two streets under it, 25 and 53 m inside, were embedded sections and would cut holes in its ballast; line
    17's bridges in Modřany, 8-18 m inside, #549). Nearer the ends the street meets the bridge's head at grade (line 9 at
    Jiráskovo náměstí 1.6 m inside, Janáčkovo nábřeží 3.9 m)."""
    spans = data.get("bridges") or []
    return lambda s: any(a + BRIDGE_HEAD < s < b - BRIDGE_HEAD for a, b in spans)


def junctions(data, survey):
    """Where paved track is embedded (#546; the user, 2026-11-13: "the track styles don't switch at the expected places
    like in junctions (expected embedded asphalt color) and crossing roadway across track isn't displayed in full
    width"): [{s0, s1, kind}].
    - a road crossing: a car road of OSM's, or another way (a service road; not a footway) where the survey has
      carriageway at the crossing point (line 9 s 360, Řepy). Over the survey's carriageway at our axis around it (its
      run through the crossing point, within CROSS_REACH m past OSM's half-width), else OSM's width at its angle;
    - a switch: from SWITCH_PAD m before it to SWITCH_PAD m past its frog;
    - a diamond: another drawn track crossing ours at DIAMOND_MIN° or more, over where the two beds overlap."""
    rt = Route(data["path"], data.get("pathExt"))
    out = []
    road = (lambda s: survey.class_at(*rt.at(min(max(s, 0), rt.length))[:2]) in CARRIAGEWAY) if survey else None
    for c, half, _, cars in crossing_roads(data, rt):
        if not cars and not (road and road(c)):
            continue
        s0, s1 = c - half, c + half
        if road:
            if road(c):
                a = c
                while a > c - half - CROSS_REACH and road(a - 1):
                    a -= 1
                b = c
                while b < c + half + CROSS_REACH and road(b + 1):
                    b += 1
                s0, s1 = min(s0, a), max(s1, b)
        out.append({"s0": s0, "s1": s1, "kind": "road"})
    for w in data.get("switches") or []:
        out.append({"s0": w["s"] - SWITCH_PAD, "s1": w["s"] + (w.get("frog") or 0) + SWITCH_PAD, "kind": "switch"})
    path = LineString([p[:2] for p in data["path"]])
    for tr in data.get("tracks") or []:
        if len(tr.get("p") or []) < 2:
            continue
        tl = LineString([q[:2] for q in tr["p"]])
        x = path.intersection(tl)
        for g in [g for g in getattr(x, "geoms", [x]) if g.geom_type == "Point"] if not x.is_empty else []:
            s = path.project(g)
            h = rt.at(min(max(s, 0), rt.length))[2:]
            d = tl.project(g)
            a, b = tl.interpolate(max(0, d - 1)), tl.interpolate(min(tl.length, d + 1))
            v = (b.x - a.x, b.y - a.y)
            vl = (v[0] ** 2 + v[1] ** 2) ** 0.5 or 1e-9
            sin = abs(h[0] * v[1] - h[1] * v[0]) / vl
            if sin < math.sin(math.radians(DIAMOND_MIN)):
                continue
            half = BED / 2 / sin + BED / 2 * (1 - sin * sin) ** 0.5 / sin
            out.append({"s0": s - half, "s1": s + half, "kind": "diamond"})
    return sorted(out, key=lambda j: j["s0"])


def track_sections(data, survey):
    """Every drawn track's own style sections beyond our route (#546; the user, 2026-11-13, on the tracks that branch
    off and run elsewhere: they "don't have consistent styles"): {track index: [[s0, s1, style], ...]}, s along the
    track's `p`. Grass where the survey's green lies under the track (MIN_GRASS m or more, gaps under JOIN m joined),
    embedded over a carriageway crossing it, a diamond (another track or our route crossing it at DIAMOND_MIN° or more)
    and a switch (BRANCH m from where another track's end meets it, or it ends on another), panels elsewhere (no
    section). The page draws a track within NEAR_ROUTE m of our route in the route's style instead."""
    near = LineString([q[:2] for q in data["path"]]).buffer(NEAR_ROUTE)
    lines = []
    for tr in data.get("tracks") or []:
        pts = [q[:2] for q in tr.get("p") or []]
        lines.append(LineString(pts) if len(pts) >= 2 else None)
    out = {}
    for i, (tr, tl) in enumerate(zip(data.get("tracks") or [], lines)):
        if tl is None or tl.length < 1 or near.covers(tl):
            continue
        rt = Route(tr["p"])
        L = rt.length
        secs = []
        if survey is not None:
            run, s = None, 0.0
            while s <= L + SAMPLE:
                green = s <= L and survey.class_at(*rt.at(s)[:2]) == "green"
                if green and run is None:
                    run = s
                if not green and run is not None:
                    s1 = min(s - SAMPLE, L)
                    if secs and run - secs[-1][1] < JOIN:
                        secs[-1][1] = s1
                    elif s1 - run >= MIN_GRASS:
                        secs.append([run, s1, "grass"])
                    run = None
                s += SAMPLE
        js = []
        road = (lambda v, rt=rt, L=L: survey.carriageway(*rt.at(min(max(v, 0), L))[:2])) if survey else None
        for c, half, _, cars in crossing_roads(data, rt):
            if cars or (road and road(c)):
                js.append((c - half, c + half))
        for j, ol in enumerate(lines):
            if j == i or ol is None:
                continue
            for other in (ol,):
                x = tl.intersection(other)
                for g in [g for g in getattr(x, "geoms", [x]) if g.geom_type == "Point"] if not x.is_empty else []:
                    s = tl.project(g)
                    d = other.project(g)
                    a, b = other.interpolate(max(0, d - 1)), other.interpolate(min(other.length, d + 1))
                    h = rt.at(min(max(s, 0), L))[2:]
                    v = (b.x - a.x, b.y - a.y)
                    sin = abs(h[0] * v[1] - h[1] * v[0]) / ((v[0] ** 2 + v[1] ** 2) ** 0.5 or 1e-9)
                    if sin >= math.sin(math.radians(DIAMOND_MIN)):
                        half = BED / 2 / sin + BED / 2 * (1 - sin * sin) ** 0.5 / sin
                        js.append((s - half, s + half))
            # (a switch: the other track's end on this one, or this one's end on the other)
            for e in (Point(ol.coords[0]), Point(ol.coords[-1])):
                s = tl.project(e)
                if tl.distance(e) < 0.5 and 1 < s < L - 1:
                    js.append((s - BRANCH / 2, s + BRANCH / 2))
            for k, e in ((0, Point(tl.coords[0])), (1, Point(tl.coords[-1]))):
                if ol.distance(e) < 0.5 and 1 < ol.project(e) < ol.length - 1:
                    js.append((0, BRANCH) if k == 0 else (L - BRANCH, L))
        js = sorted((max(0.0, a), min(L, b)) for a, b in js if b > 0 and a < L)
        emb = []
        for a, b in js:
            if emb and a - emb[-1][1] < MIN_PIECE:
                emb[-1][1] = max(emb[-1][1], b)
            else:
                emb.append([a, b])
        grass = [[a, b, "grass"] for g in secs for a, b in minus(g[0], g[1], [{"s0": e[0], "s1": e[1]} for e in emb])
                 if b - a >= MIN_PIECE]
        own = sorted(grass + [[a, b, "embedded"] for a, b in emb if b - a >= 1])
        if own:
            out[i] = [[round(a, 1), round(b, 1), st] for a, b, st in own]
    return out


def embed(secs, js):
    """Embedded over the junctions `js`, whatever the section there, but open ballast (the user, #503: "the branch to
    depo hostivař loop has open ballast including switches") and the user's own marks of another style than grass.
    Grass yields to them (the user, 2026-11-13: "for the roads crossing tracks and junctions I would default to
    embedded asphalt style which will be also easier to judge if the transition happens at the correct place").
    Embedded pieces less than MIN_PIECE apart join over the panels between."""
    # (an answered asphalt stretch yields to a junction inside it: the junction is one surface from fork to fork, the
    # user 2026-11-14, #574, and the card's ends are OSM's surface changes, metres off)
    yields = lambda x: x.get("source") == "surface" and x["style"] == "embedded"  # noqa: E731
    wins = [x for x in secs if not yields(x) and (x["style"] in ("ballast", "embedded", "setts")
            or (x["source"] in ("user", "surface") and x["style"] != "grass"))]
    free = []
    for j in js:
        free += [(a, b, j["kind"]) for a, b in minus(j["s0"], j["s1"], wins)]
    free.sort()
    merged = []
    for a, b, k in free:
        if merged and a - merged[-1][1] < MIN_PIECE and not any(
                x["s1"] > merged[-1][1] and x["s0"] < a and x.get("source") != "hole" and x["style"] not in PAVED_IN
                for x in secs):
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2].add(k)
        else:
            merged.append([a, b, {k}])
    # (a piece joined across a section that wins keeps out of it: a setts stretch through a junction, #574)
    add = [{"s0": p, "s1": q, "style": "embedded", "source": "junction", "junction": sorted(k)} for a, b, k in merged
           for p, q in minus(a, b, wins) if q - p >= 1]
    # (the grass around them keeps what is left, MIN_PIECE or longer; the holes they cover go)
    out = []
    for x in secs:
        if x["style"] == "grass":
            out += [{**x, "s0": a, "s1": b} for a, b in minus(x["s0"], x["s1"], add) if b - a >= MIN_PIECE]
        elif x.get("source") == "hole" and any(y["s0"] <= x["s0"] and x["s1"] <= y["s1"] for y in add):
            continue
        elif yields(x):
            out += [{**x, "s0": a, "s1": b} for a, b in minus(x["s0"], x["s1"], add) if b - a >= 1]
        else:
            out.append(x)
    return sorted(out + add, key=lambda x: x["s0"])


def cut(secs, hs):
    """The grass and ballast sections with their holes cut out; a road crossing inside one is embedded track."""
    out = []
    for x in secs:
        if x["style"] not in ("grass", "ballast"):
            out.append(x)
            continue
        mine = [h for h in hs if (x["style"] == "grass" or not h["grass"]) and h["s1"] > x["s0"] and h["s0"] < x["s1"]]
        out += [{**x, "s0": a, "s1": b} for a, b in minus(x["s0"], x["s1"], mine) if b - a >= MIN_PIECE]
        out += [{"s0": max(h["s0"], x["s0"]), "s1": min(h["s1"], x["s1"]), "style": "embedded", "source": "hole", "hole": h["kind"]}
                for h in mine if h["kind"] == "road" and min(h["s1"], x["s1"]) - max(h["s0"], x["s0"]) >= MIN_EMBEDDED]
    out.sort(key=lambda x: x["s0"])
    merged = []   # (road holes overlapping one another: one section)
    for x in out:
        last = merged[-1] if merged else None
        if last and x["source"] == "hole" and last["source"] == "hole" and x["s0"] <= last["s1"]:
            last["s1"] = max(last["s1"], x["s1"])
        else:
            merged.append(dict(x))
    return merged


def reviewed(data, truth):
    """The user's answers to the OSM grass review (truth.json `grassReview`, tools/grass_review.py): grass between
    the card's two points on every line it lists."""
    path = LineString([p[:2] for p in data["path"]])
    out = []
    for a in truth.get("grassReview", {}).get("answers", []):
        if a.get("answer") != "grass" or str(data["line"]) not in [str(v) for v in a.get("lines", [])]:
            continue
        pts = [Point(*map(float, Frame().xy(*e))) for e in a["between"]]
        if any(path.distance(p) > 15 for p in pts):
            continue
        s0, s1 = sorted(path.project(p) for p in pts)
        out.append({"s0": s0, "s1": s1, "style": "grass", "source": "review", "card": a["id"]})
    return out


def sections(data, truth, survey, opens=()):
    """The style sections along the route, by s0, with their holes (src/heights.js trackStyles until #479), the
    paved track embedded at junctions and road crossings (#546), and the junctions the user's surface answers lay in
    setts (#574). `opens`: the lidar's runs of open ballast (tools/open_track.py `found`, #591)."""
    return setts_junctions(embed(cut(spans(data, truth, survey, opens), holes(data, survey)), junctions(data, survey)),
                           data, truth)


def surface_places(data, truth):
    """The user's answers to the track surface review (truth.json `trackSurfaceReview`, tools/surface_review.py, #574)
    that lie on this line's route, whichever line's card asked: [(s0, s1, what, answer, id)]. A place both of whose
    ends lie within 15 m of the route."""
    path = LineString([p[:2] for p in data["path"]])
    out = []
    for a in truth.get("trackSurfaceReview", {}).get("answers", []):
        if a.get("answer") not in SURFACE_STYLE:
            continue
        pts = [Point(*map(float, Frame().xy(*e))) for e in a["between"]]
        if any(path.distance(p) > 15 for p in pts):
            continue
        s0, s1 = sorted(path.project(p) for p in pts)
        out.append((s0, s1, a["what"], SURFACE_STYLE[a["answer"]], a["id"]))
    return out


def surfaced(data, truth):
    """The answered stretches as sections: the style the user gave between the card's two points (as strong as the
    user's marks)."""
    return [{"s0": s0, "s1": s1, "style": st, "source": "surface", "card": i}
            for s0, s1, what, st, i in surface_places(data, truth) if what == "stretch"]


def setts_junctions(secs, data, truth):
    """A junction the user answered setts is setts over its whole junction section, from the switches' forks to the
    others' (the user, 2026-11-14, #574: "sett style inside a junction usually means the whole track junction from
    switch fork to the other switch forks is covered by setts, this is for easy repairs and replacements"); so is a
    junction section that touches a setts stretch. #546's junction sections already run from SWITCH_PAD before the
    first switch to past the last frog, its pieces less than MIN_PIECE apart joined."""
    places = surface_places(data, truth)
    setts = [(s0, s1, i) for s0, s1, what, st, i in places if what == "junction" and st == "setts"]
    stretches = [x for x in secs if x["style"] == "setts"]
    out = []
    for x in secs:
        if x.get("source") == "junction" and x["style"] == "embedded":
            card = next((i for s0, s1, i in setts if s1 >= x["s0"] and s0 <= x["s1"]), None)
            near = any(y["s1"] >= x["s0"] - 1 and y["s0"] <= x["s1"] + 1 for y in stretches)
            if card or near:
                x = {**x, "style": "setts", **({"card": card} if card else {"beside": "setts"})}
        out.append(x)
    return out


def spans(data, truth, survey, opens=()):
    """The style sections from end to end, before the holes."""
    user = []
    for mark, t in enumerate(truth.get("trackStyles", [])):
        if str(t["line"]) != str(data["line"]):
            continue
        if "between" in t:   # (two ends, each a lat, lon point or a stop: points within 15 m of the route, by position)
            path = LineString([p[:2] for p in data["path"]])
            pts = [None if isinstance(e, str) else Point(*map(float, Frame().xy(*e))) for e in t["between"]]
            if any(p is not None and path.distance(p) > 15 for p in pts):
                continue
            ss = [None if p is None else path.project(p) for p in pts]
            known = [v for v in ss if v is not None]
            for i, e in enumerate(t["between"]):
                if isinstance(e, str):   # (the stop of that name nearest the point end)
                    at = [st["s"] for st in data["stops"] if st["name"] == e]
                    ss[i] = min(at, key=lambda v: abs(v - known[0]) if known else v) if at else None
            if None in ss:
                continue
            s0, s1 = sorted(ss)
        else:
            a = next((i for i, st in enumerate(data["stops"]) if st["name"] == t["from"]), -1)
            b = next((i for i, st in enumerate(data["stops"]) if a >= 0 and i > a and st["name"] == t["to"]), -1)
            if a < 0 or b < 0:
                continue
            s0, s1 = data["stops"][a]["s"], data["stops"][b]["s"]
        user.append({"s0": s0, "s1": s1, "style": t["style"], "source": "user", "mark": mark})
    user += reviewed(data, truth)
    # (the surface answers where no mark or grass answer says otherwise, #574)
    user += [{**x, "s0": a, "s1": b} for x in surfaced(data, truth) for a, b in minus(x["s0"], x["s1"], user) if b - a >= 1]
    user.sort(key=lambda x: x["s0"])
    listed = []
    for k, t in enumerate(truth.get("grassTrack", {}).get("stretches", [])):
        if "from" not in t or t.get("removed"):
            continue
        for s0, s1 in passes(data["stops"], t["from"], t["to"]):
            listed += [{"s0": a, "s1": b, "style": "grass", "source": "list", "stretch": k}
                       for a, b in minus(s0, s1, user) if b - a >= MIN_GRASS]
    facts, found = user + listed, []
    if survey is not None:
        rt = Route(data["path"], data.get("pathExt"))
        start, s = None, 0
        while s <= rt.length + SAMPLE:
            x, y = rt.at(s)[:2]
            green = s <= rt.length and survey.class_at(x, y) == "green"
            if green and start is None:
                start = s
            if not green and start is not None:
                s1 = s - SAMPLE
                last = found[-1] if found else None
                if last and start - last["s1"] < JOIN:
                    last["s1"] = s1
                elif s1 - start >= MIN_GRASS and not any(s1 > x["s0"] and start < x["s1"] for x in facts):
                    found.append({"s0": start, "s1": s1, "style": "grass", "source": "survey"})
                start = None
            s += SAMPLE
    # The lidar's open ballast (tools/open_track.py, #591) where nothing above says what the track is: the sure runs,
    # pieces of MIN_GRASS m and more; a place the user answered on its card decides there (truth.json openTrackReview).
    have = facts + found
    ans = open_answers(data, truth)
    lid = []
    for r in opens:
        if not r["sure"] and not any(a["s0"] < r["s1"] and a["s1"] > r["s0"] for a in ans):
            continue
        lid += [{"s0": a, "s1": b, "style": "ballast", "source": "lidar", "median": r["median"]}
                for a, b in minus(r["s0"], r["s1"], have + ans) if b - a >= MIN_GRASS]
    return sorted(have + lid + [a for a in ans if a["style"] != "paved"], key=lambda x: x["s0"])


def open_answers(data, truth):
    """The user's answers to the open track review (truth.json `openTrackReview`, tools/open_track.py --cards, #591)
    on this line's route: the style between the card's two points (`paved` leaves the track to the rules)."""
    path = LineString([p[:2] for p in data["path"]])
    out = []
    for a in truth.get("openTrackReview", {}).get("answers", []):
        pts = [Point(*map(float, Frame().xy(*e))) for e in a["between"]]
        if any(path.distance(p) > 15 for p in pts):
            continue
        s0, s1 = sorted(path.project(p) for p in pts)
        out.append({"s0": s0, "s1": s1, "style": a["answer"], "source": "review", "card": a["id"]})
    return out


def offsets(truth):
    """How high the rails stand over each style's bed, m (truth.json trackHeights.railAboveDeck, scope all), as
    src/heights.js trackStyleOffsets reads them: one value per style, else an error."""
    out = {}
    for style in ("embedded", "setts", "panels", "grass", "ballast"):
        fs = [f for f in truth.get("trackHeights", {}).get("railAboveDeck", [])
              if f.get("scope") == "all" and (not f.get("styles") or style in f["styles"])]
        if not fs or len({f["metres"] for f in fs}) != 1:
            raise SystemExit(f"missing or conflicting rail offset facts: {style}")
        out[style] = fs[0]["metres"]
    return out


def lift(secs, off, s):
    """The rails' height over the bed at route position s: the section's style offset, blended in over RAMP m inside
    each end of its section (#480: blended outside, the ballast bed fell 8-12 cm under the footway crossing before line
    17's open ballast at s 3236, a hole of #503); a section shorter than 2 RAMP blends over half its length."""
    v = 0.0
    for x in secs:
        d = off.get(x["style"], 0)
        if not d or s < x["s0"] or s > x["s1"]:
            continue
        r = min(RAMP, (x["s1"] - x["s0"]) / 2)
        k = min(1.0, (s - x["s0"]) / r, (x["s1"] - s) / r) if r > 0 else 1.0
        v = max(v, d * k * k * (3 - 2 * k))
    return v


def lift_series(data, secs, off):
    """`lift` every LIFT_STEP m of the route (the page's profile step), in mm."""
    n = int(Route(data["path"], data.get("pathExt")).length / LIFT_STEP) + 2
    return {"step": LIFT_STEP, "unit": 0.001, "v": [round(lift(secs, off, k * LIFT_STEP) * 1000) for k in range(n)]}


def main():
    if "--line" not in sys.argv:
        sys.exit(__doc__)
    line = sys.argv[sys.argv.index("--line") + 1]
    p = ROOT / "data" / f"line{line}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    dp = ROOT / "data" / f"line{line}.dtm.json"
    dtm = json.loads(dp.read_text(encoding="utf-8")) if dp.exists() else None
    survey = Survey(dtm) if dtm else None
    import open_track
    data["styles"] = sections(data, truth, survey, open_track.found(data))
    own = track_sections(data, survey)
    for i, tr in enumerate(data.get("tracks") or []):
        if i in own:
            tr["styles"] = own[i]
        else:
            tr.pop("styles", None)
    # (every drawn track's bed width by its style, #547: tools/track_beds.py)
    bs = track_beds.beds(data, dtm)
    for i, tr in enumerate(data.get("tracks") or []):
        if i in bs:
            tr["bed"] = bs[i]
        else:
            tr.pop("bed", None)
    data["lift"] = lift_series(data, data["styles"], offsets(truth))
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"line {line}: " + ", ".join(f"{x['style']} {x['s0']:.0f}-{x['s1']:.0f} ({x['source']})" for x in data["styles"]) or "none")
    print(f"line {line}: other tracks: " + ", ".join(f"{st} {sum(b - a for v in own.values() for a, b, s in v if s == st):.0f} m"
                                                    for st in ("grass", "embedded")) + f" on {len(own)} tracks")
    print(f"line {line}: beds: " + json.dumps(track_beds.report(data, dtm, bs)))


if __name__ == "__main__":
    main()
