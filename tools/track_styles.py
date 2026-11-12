"""The line's track styles, built offline (#276 step 2, #479): one implementation of the user's marks and the survey's
grass track, read by the page (src/heights.js) and the height import (tools/track_decks.py).

    python -P -E tools/track_styles.py --line 22     # writes `styles` into data/line22.json

- **The user's marks** (data/truth.json `trackStyles`, by stops so they hold in any frame): from the first stop of the
  mark's `from` name to the next stop of its `to` name; a mark with `between` (two lat, lon points) runs between the
  route positions nearest them.
- **The grassed-track list** (data/truth.json `grassTrack`, prazsketramvaje.cz): every line passing both stops of a
  stretch takes it, each time it passes them (an out-and-back line twice). Where the user's marks cover the track they
  win, and what is left of a stretch stays if MIN_GRASS long.
- **The survey's grass track:** a `green` area under the track axis (the survey's ground-level area at the route,
  data/lineN.dtm.json) for MIN_GRASS metres and more, read every SAMPLE m, runs less than JOIN m apart one section.
  The facts (the user's marks, the list) win where they overlap (line 22 Koh-i-noor - Slavia, whose bank fell 0.5 m
  across the rails).

`styles` is a list of {s0, s1, style, source, mark | stretch}, by s0: `source` 'user', 'list' or 'survey'; `mark` is
the index of the user's mark in truth.json `trackStyles`, `stretch` the index in `grassTrack.stretches`. How high the rails stand over each style is a fact in truth.json (`railAboveDeck`), which the
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


def sections(data, truth, survey):
    """The style sections along the route, by s0 (src/heights.js trackStyles until #479)."""
    user = []
    for mark, t in enumerate(truth.get("trackStyles", [])):
        if str(t["line"]) != str(data["line"]):
            continue
        if "between" in t:   # (two points: the route positions nearest them, where the route passes within 15 m)
            path = LineString([p[:2] for p in data["path"]])
            pts = [Point(*map(float, Frame().xy(lat, lon))) for lat, lon in t["between"]]
            if max(path.distance(p) for p in pts) > 15:
                continue
            s0, s1 = sorted(path.project(p) for p in pts)
        else:
            a = next((i for i, st in enumerate(data["stops"]) if st["name"] == t["from"]), -1)
            b = next((i for i, st in enumerate(data["stops"]) if a >= 0 and i > a and st["name"] == t["to"]), -1)
            if a < 0 or b < 0:
                continue
            s0, s1 = data["stops"][a]["s"], data["stops"][b]["s"]
        user.append({"s0": s0, "s1": s1, "style": t["style"], "source": "user", "mark": mark})
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
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"line {line}: " + ", ".join(f"{x['style']} {x['s0']:.0f}-{x['s1']:.0f} ({x['source']})" for x in data["styles"]) or "none")


if __name__ == "__main__":
    main()
