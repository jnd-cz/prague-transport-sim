# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the track is laid in, by OSM, for the user to check: the setts and concrete stretches, where OSM's surface
changes, and the junctions in them (#574).

    python -P -E tools/surface_review.py --cards           # reports/review/track-surface-N.json
    python -P -E tools/surface_review.py --import          # the answers into data/truth.json trackSurfaceReview

The user, 2026-11-13, on the setts style's source: OSM first, calibrated against the user's answers; "One per street,
stretch where it switches and per junction would make it more efficient to label"; on OSM's concrete: "osm could help
but should be checked if it's up to date".

OSM's surface along our route, every STEP m: the tram way's own `surface` within TRAM m of the axis, else the
`surface` of the carriageway carrying the tracks (`embedded_rails=tram`) within ROAD m. Classes: setts (sett,
cobblestone, unhewn_cobblestone), concrete (concrete, concrete:plates: panels, if OSM is current), asphalt, other.
Runs shorter than MIN_RUN m join their neighbours.

Cards (a place on two lines' track is asked once, on the first line):
- a **stretch** of setts or concrete: what the track is laid in there;
- a **switch**, where OSM's class changes and one side is setts or concrete: whether the surface changes there;
- a **junction** (#546's embedded pieces) in or within NEAR m of a setts stretch, or at a switch: what it is laid in.
The answers go to data/truth.json `trackSurfaceReview` by the place's two ends (lat/lon), for tools/track_styles.py's
setts and the OSM rule's calibration (#574).
"""
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from atomic import replacing  # noqa: E402

LINES = "9,17,22,23,37"
STEP = 2.0
TRAM, ROAD = 2.5, 6.0   # m from our axis: the tram way, the carriageway around the tracks
MIN_RUN = 12            # m: a shorter run of one class joins its neighbours
NEAR = 20               # m: a junction this near a setts stretch, or a switch, gets a card
SAME = 25               # m: two lines' cards this near are one
CLASS = {"sett": "setts", "cobblestone": "setts", "unhewn_cobblestone": "setts", "concrete": "concrete",
         "concrete:plates": "concrete", "asphalt": "asphalt"}
SETTS, ASPHALT, PANELS, GRASS, UNSURE = "setts", "asphalt (embedded)", "panels", "grass", "unsure"
TRACKS_DIFFER = "each track differently (say which in the note)"
CHANGES, NO_CHANGE = "the surface changes here", "no change here"
ANSWER = {SETTS: "setts", ASPHALT: "embedded", PANELS: "panels", GRASS: "grass", CHANGES: "changes", NO_CHANGE: "same"}
TRUTH_NOTE = ("The user's answers to the track surface review (reports/review/track-surface-N.json, "
              "tools/surface_review.py, #574): what the track is laid in between two points (`setts`, `embedded`, "
              "`panels`, `grass`), and at OSM's surface changes whether it changes there (`changes`, `same`). The setts "
              "style and the OSM rule's calibration read them.")
READER = "tools/surface_review.py (an answered place gets no card); tools/track_styles.py's setts (#574) once it reads them"


def osm_ways(pbf, frame):
    """[(kind 'tram' | 'road', class, name, LineString, osm id)] of the tram ways and the carriageways with tracks."""
    import osmium
    from shapely.geometry import LineString

    class H(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.out = []

        def way(self, w):
            t = w.tags
            kind = "tram" if t.get("railway") == "tram" else "road" if "highway" in t and t.get("embedded_rails") == "tram" else None
            if not kind:
                return
            try:
                pts = [frame.xy(n.lat, n.lon) for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            if len(pts) >= 2:
                s = t.get("surface")
                self.out.append((kind, CLASS.get(s, "other") if s else None, t.get("name", ""), LineString(pts), w.id))
    h = H()
    h.apply_file(str(pbf), locations=True)
    return h.out


def surface_along(path, ways, step=STEP):
    """OSM's class along the route every `step` m: [(s, class or None, name, way id)]."""
    import shapely
    from shapely.geometry import LineString, Point
    rt = LineString(path)
    tree = shapely.STRtree([w[3] for w in ways])
    out = []
    s = 0.0
    while s <= rt.length:
        p = rt.interpolate(s)
        best = None
        for kind, reach in (("tram", TRAM), ("road", ROAD)):
            for k in tree.query(p.buffer(reach)):
                w = ways[int(k)]
                if w[0] != kind or w[1] is None:
                    continue
                d = w[3].distance(Point(p.x, p.y))
                if d <= reach and (best is None or d < best[0]):
                    best = (d, w)
            if best:
                break
        out.append((round(s, 1), best[1][1] if best else None, best[1][2] if best else "", best[1][4] if best else None))
        s += step
    return out


def runs(along, min_run=MIN_RUN):
    """Runs of one class: [[s0, s1, class, {names}, {way ids}]], shorter ones joined to their neighbours."""
    rs = []
    for s, c, n, w in along:
        if rs and rs[-1][2] == c:
            rs[-1][1] = s
            rs[-1][3].add(n)
            rs[-1][4].add(w)
        else:
            rs.append([s, s, c, {n}, {w}])
    changed = True
    while changed and len(rs) > 1:
        changed = False
        for i, r in enumerate(rs):
            if r[1] - r[0] < min_run:
                j = i - 1 if i > 0 and (i + 1 >= len(rs) or rs[i - 1][1] - rs[i - 1][0] >= rs[i + 1][1] - rs[i + 1][0]) else i + 1
                a, b = sorted((i, j))
                keep = rs[j]
                rs[a:b + 1] = [[rs[a][0], rs[b][1], keep[2], rs[a][3] | rs[b][3], rs[a][4] | rs[b][4]]]
                changed = True
                break
        # (neighbours of one class, after a join, are one run)
        k = 0
        while k + 1 < len(rs):
            if rs[k][2] == rs[k + 1][2]:
                rs[k:k + 2] = [[rs[k][0], rs[k + 1][1], rs[k][2], rs[k][3] | rs[k + 1][3], rs[k][4] | rs[k + 1][4]]]
            else:
                k += 1
    return rs


def cards_for(line, data, rs, frame):
    """The cards of one line from its OSM runs and #546's junction pieces."""
    from shapely.geometry import LineString
    rt = LineString([q[:2] for q in data["path"]])
    at = lambda s: rt.interpolate(max(0.0, min(s, rt.length))).coords[0]  # noqa: E731
    ll = lambda x, y: [round(float(v), 7) for v in frame.ll(x, y)]  # noqa: E731
    style = lambda s: next((x["style"] for x in data.get("styles") or [] if x["s0"] <= s <= x["s1"]), "panels")  # noqa: E731
    stop = lambda s: min(data["stops"], key=lambda q: abs(q["s"] - s))["name"]  # noqa: E731
    named = lambda r: ", ".join(sorted(n for n in r[3] if n)) or "unnamed"  # noqa: E731
    out = []

    def card(kind, s0, s1, options, info):
        a, b = at(s0), at(s1)
        x, y = at((s0 + s1) / 2)
        lat, lon = ll(x, y)
        out.append({"kind": "track surface", "what": kind, "id": f"surface-{kind}-{lat:.5f}-{lon:.5f}", "line": line,
                    "x": round(x, 1), "y": round(y, 1), "s0": round(s0), "s1": round(s1), "status": "review",
                    "place": [round(lat, 6), round(lon, 6)], "between": [ll(*a), ll(*b)],
                    "marks": [{"x": round(a[0], 1), "y": round(a[1], 1), "label": "from", "color": "#3e9dff"},
                              {"x": round(b[0], 1), "y": round(b[1], 1), "label": "to", "color": "#ffffff"}],
                    "options": options, "info": info})
    stretch_opts = [SETTS, ASPHALT, PANELS, GRASS, TRACKS_DIFFER, UNSURE]
    for r in rs:
        if r[2] in ("setts", "concrete"):
            card("stretch", r[0], r[1], stretch_opts,
                 f"{named(r)} near {stop((r[0] + r[1]) / 2)} (s {r[0]:.0f}-{r[1]:.0f}, {r[1] - r[0]:.0f} m): OSM says "
                 f"{'setts' if r[2] == 'setts' else 'concrete (panels?)'} here, the game draws {style((r[0] + r[1]) / 2)}. "
                 f"What is the track laid in between the two marks? (Where one track differs from the other, as at "
                 f"Drinopol, say which in the note: that answer is kept for per-track styles, not imported.)")
    for r, q in zip(rs, rs[1:]):
        if {r[2], q[2]} & {"setts", "concrete"}:
            s = r[1]
            card("switch", s - 10, s + 10, [CHANGES, NO_CHANGE, UNSURE],
                 f"near {stop(s)} (s {s:.0f}): OSM's surface changes here from {r[2] or 'nothing'} ({named(r)}) to "
                 f"{q[2] or 'nothing'} ({named(q)}). Does the track's surface change within these 20 m?")
    sett_runs = [r for r in rs if r[2] == "setts"]
    switches = [r[1] for r, q in zip(rs, rs[1:]) if {r[2], q[2]} & {"setts", "concrete"}]
    for j in data.get("styles") or []:
        if j.get("source") != "junction":
            continue
        near = any(r[0] - NEAR <= j["s1"] and j["s0"] <= r[1] + NEAR for r in sett_runs) or \
            any(j["s0"] - NEAR <= s <= j["s1"] + NEAR for s in switches)
        if near:
            kinds = ", ".join(j.get("junction") or [])
            card("junction", j["s0"], j["s1"], [SETTS, ASPHALT, PANELS, UNSURE],
                 f"a junction ({kinds}) near {stop((j['s0'] + j['s1']) / 2)} (s {j['s0']:.0f}-{j['s1']:.0f}), in or "
                 f"beside OSM's setts or where OSM's surface changes. The game draws it asphalt (#546). What is it laid "
                 f"in?")
    return out


def cards(lines):
    from geo import Frame
    F = Frame()
    ways = osm_ways(ROOT / "raw" / "osm" / "praha.osm.pbf", F)
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    done = [a["id"] for a in (truth.get("trackSurfaceReview") or {}).get("answers", [])]
    asked = []
    for line in sorted(lines, key=int):
        data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        rs = runs(surface_along([q[:2] for q in data["path"]], ways))
        cs = [c for c in cards_for(line, data, rs, F) if c["id"] not in done
              and all(math.hypot(c["x"] - x, c["y"] - y) >= SAME for x, y, w in asked if w == c["what"])]
        asked += [(c["x"], c["y"], c["what"]) for c in cs]
        p = ROOT / "reports" / "review" / f"track-surface-{line}.json"
        if not cs:
            if p.exists():
                p.unlink()
            print(f"line {line}: no cards")
            continue
        body = {"schema": 1, "issue": 574, "line": line, "title": "Track surface: setts, asphalt or panels (OSM's surface checked)",
                "findings": cs}
        with replacing(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        n = {k: sum(1 for c in cs if c["what"] == k) for k in ("stretch", "switch", "junction")}
        print(f"line {line}: {len(cs)} cards ({n['stretch']} stretches, {n['switch']} switches, {n['junction']} junctions)")


def do_import(lines, reviews):
    found, newest = {}, {}
    for line in lines:
        cp = ROOT / "reports" / "review" / f"track-surface-{line}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                found.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{line}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "track surface" and r.get("v") in ANSWER and r.get("id") in found:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    sec = json.loads(truth_p.read_text(encoding="utf-8")).get("trackSurfaceReview", {})
    got = {a["id"]: a for a in sec.get("answers", [])}
    for i, r in newest.items():
        c = found[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "what": c["what"], "line": c["line"], "between": c["between"], "answer": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, track surface review (reports/review/track-surface-{c['line']}.json), {day} (#574)"}
    from cross_level import write_truth
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": sorted(got.values(), key=lambda a: a["id"])}, "trackSurfaceReview")
    readers = json.loads(truth_p.read_text(encoding="utf-8"))["readers"]
    if "trackSurfaceReview" not in readers:
        write_truth(truth_p, {**readers, "trackSurfaceReview": READER}, "readers")
    print(f"data/truth.json trackSurfaceReview: {len(got)} answers ({len(newest)} from this import)")


def main():
    lines = (sys.argv[sys.argv.index("--lines") + 1] if "--lines" in sys.argv else LINES).split(",")
    if "--cards" in sys.argv:
        cards(lines)
    elif "--import" in sys.argv:
        do_import(lines, sys.argv[sys.argv.index("--reviews") + 1] if "--reviews" in sys.argv else "reports/reviews")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
