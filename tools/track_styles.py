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

`styles` is a list of {s0, s1, style, source, mark | stretch | card | hole}, by s0: `source` 'user', 'review', 'list',
'survey' or 'hole'; `mark` is the index of the user's mark in truth.json `trackStyles`, `stretch` the index in
`grassTrack.stretches`, `card` the review card's id. How high the rails stand over each style is a fact in truth.json (`railAboveDeck`), which the
page reads with the sections. Where ground-level areas overlap at a point, the higher rank counts. The page picked the
one whose surface lay nearest the lidar ground, then the rank (src/terrain.js DtmSurface._hitTri): on all five lines
the two agree at every sample (21,641, #479).
"""
import json
from pathlib import Path
import sys

import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402
from route import Route  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE, MIN_GRASS, JOIN = 4, 20, 30   # m (src/heights.js trackStyles until #479)
# The holes (#503), m beyond the thing itself: where OSM maps grass inside the known spans (2026-11-12), its areas
# end 2-5 m short of a footway crossing, 5-15 m of a street's edge and 3-4 m of a platform.
HOLE = {"footway": 3, "road": 8, "node": 5, "platform": 3}
PLATFORM_NEAR = 6      # m from our axis: our platform and the other direction's beside the other track
MIN_PIECE = MIN_GRASS  # m: a shorter piece left between two holes is not laid (OSM maps none of the 12-14 m ones)
MIN_EMBEDDED = 5       # m: a street's hole the section's end cuts shorter is not an embedded section of its own
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


def holes(data):
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
        kind = "road" if r.get("c") and not r.get("f") else "footway"
        for a, b in zip(r["p"], r["p"][1:]):
            segs.append(LineString([a[:2], b[:2]]))
            kinds.append((kind, r.get("w") or 3))
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
                c = s + step.project(seg.intersection(step).representative_point())
                half = w / 2 / max(0.3, (1 - cos * cos) ** 0.5)
                out.append({"s0": c - half - HOLE[kind], "s1": c + half + HOLE[kind], "kind": kind, "grass": False})
    for s in data.get("crossings", []):   # (OSM's crossing nodes on the track)
        out.append({"s0": s - HOLE["node"], "s1": s + HOLE["node"], "kind": "footway", "grass": False})
    # (no holes at switches and diamonds: the user, 2026-11-12, #503: "I wouldn't make holes for switches and
    # diamonds, the branch to depo hostivař loop has open ballast including switches. They are covered if they lie
    # on paved surface", which the streets' holes already are)
    return sorted(out, key=lambda h: h["s0"])


def cut(secs, hs):
    """The grass and ballast sections with their holes cut out; a road crossing inside one is embedded track."""
    out = []
    for x in secs:
        if x["style"] not in ("grass", "ballast"):
            out.append(x)
            continue
        mine = [h for h in hs if (x["style"] == "grass" or not h["grass"]) and h["s1"] > x["s0"] and h["s0"] < x["s1"]]
        out += [{**x, "s0": a, "s1": b} for a, b in minus(x["s0"], x["s1"], mine) if b - a >= MIN_PIECE]
        out += [{"s0": max(h["s0"], x["s0"]), "s1": min(h["s1"], x["s1"]), "style": "embedded", "source": "hole", "hole": "road"}
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


def sections(data, truth, survey):
    """The style sections along the route, by s0, with their holes (src/heights.js trackStyles until #479)."""
    return cut(spans(data, truth, survey), holes(data))


def spans(data, truth, survey):
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
    return sorted(facts + found, key=lambda x: x["s0"])


def offsets(truth):
    """How high the rails stand over each style's bed, m (truth.json trackHeights.railAboveDeck, scope all), as
    src/heights.js trackStyleOffsets reads them: one value per style, else an error."""
    out = {}
    for style in ("embedded", "panels", "grass", "ballast"):
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
    survey = Survey(json.loads(dp.read_text(encoding="utf-8"))) if dp.exists() else None
    data["styles"] = sections(data, truth, survey)
    data["lift"] = lift_series(data, data["styles"], offsets(truth))
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"line {line}: " + ", ".join(f"{x['style']} {x['s0']:.0f}-{x['s1']:.0f} ({x['source']})" for x in data["styles"]) or "none")


if __name__ == "__main__":
    main()
