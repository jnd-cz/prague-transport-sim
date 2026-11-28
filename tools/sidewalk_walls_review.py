# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sidewalks at a wall where the survey's level and IPR's lidar part: measured per line, and the longest for the user's
review (#653).

    python -P -E tools/sidewalk_walls_review.py [--lines 9,17,22,23,37]     # the table, and the review sets
    python -P -E tools/sidewalk_walls_review.py --table [--list N]           # the table alone (and N stretches a kind)
    python -P -E tools/sidewalk_walls_review.py --import [--reviews reports/reviews]

The street surface holds a sidewalk's cells along its edge on a survey wall or stairs (street_profile.sidewalks,
wall_edges) at one of three heights there: the edge's own, and the wall's top and foot within WALL_LOCAL (WallLevels.pick),
whichever is nearest IPR SW_KERB_SMEAR in on the sidewalk's side; within that smear IPR does not pull. Where the survey's
outline carries the wall's other side, all three can be that side's level, and the walkway wedges to it in its last
metre and a half: at Vyšehrad, line 17 (-586, -2311), it climbs 6 m up the fortification wall, where a cobbled path runs
along the wall's foot and a walkway along its parapet (maintainer, #899).

- **The table** (per line): the sidewalk edges on walls, stairs and the paved strips that are a wall's face
  (ground_mesh.wall_areas), read every SAMPLE m where the sidewalk runs RUN m in unbroken (so that IPR SW_KERB_SMEAR in
  is its own walkway, street_profile.runs_in); those whose three heights all lie over OFF m from IPR there, by KINDS
  (all over it, all under it, it between the wall's foot and top); the stretches they make (points within JOIN m).
  Read with IPR under covers as the build reads it (covers.CoveredIpr).
- **The cards** (reports/review/sidewalk-walls-N.json): of each of GROUPS (the kind and what the edge lies on) the
  longest stretches of SHORT m or more (PER_GROUP, those of SPREAD m or more on another line first, APART), the lines
  merged (one city frame: a stretch on two lines' files is one card in both sets). Each asks at which level the walkway meets the wall there; the pins mark the survey's edge, IPR's reading
  SW_KERB_SMEAR in and the stretch's ends. The answers are what a rule for the hold is calibrated on (#653).
- **--import** takes the answers (python -P -E tools/deploy.py --pull, in the deploy checkout) into data/truth.json
  `sidewalkWallsReview`, keyed by place: the edge's point and IPR's, lat/lon (survey area numbers change with a rebuild).
  A stretch holding an answered place (NEAR) gets no card again.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import warnings

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINES = "9,17,22,23,37"
SAMPLE = 0.5    # m between the points read along an edge (the street surface's cell)
RUN = 2.0       # m: the sidewalk runs this far in unbroken, so IPR SW_KERB_SMEAR in reads its own walkway
OFF = 1.0       # m: an edge whose three heights all lie this far off IPR meets another level (a kerb is 0.15 m)
JOIN = 2.0      # m: off points this near each other make one stretch
SHORT = 3.0     # m: a shorter stretch gets no card (two outlines meeting at a corner)
PER_GROUP = 3   # the cards of each group
SPREAD = 10.0   # m: a stretch this long goes first where its lines have no card of its group yet
APART = 20.0    # m: a stretch whose worst point lies this near a chosen card's is the same place (two outlines along a wall)
NEAR = 5.0      # m: a stretch with a point this near an answered place gets no card
KINDS = [  # (the kind, what it says on the card)
    ("over", "every height the survey has here lies over IPR's walkway"),
    ("under", "every height the survey has here lies under IPR's walkway"),
    ("between", "IPR's walkway lies between the wall's foot and its top, far from both"),
]
CLASSES = {"wall": "wall", "stairs": "stairs", "paved": "paved strip drawn as a wall's face"}
GROUPS = ["over, wall", "over, strip", "under, wall", "under, strip", "stairs"]   # (between: under 3 m a stretch, 2026-11-28)


def group(s):
    """A stretch's group: its kind and what the edge lies on (stairs either way; between: none)."""
    if s["side"] == "between":
        return None
    return "stairs" if s["cls"] == "stairs" else f"{s['side']}, {'wall' if s['cls'] == 'wall' else 'strip'}"
ANSWERS = [  # (the answer on the card, its key in data/truth.json)
    ("IPR's level: the walkway runs on at the blue pin's height up to the wall", "lidar"),
    ("the survey's level: the walkway meets the wall at the white pin's height", "survey"),
    ("no walkway along the wall here (a bed, a fence, a building's face)", "no walkway"),
]
UNSURE = "unsure"
ANSWER = {**dict(ANSWERS), UNSURE: UNSURE}
KIND = "sidewalk at a wall"   # (the cards' kind: review mode keys an answer by it and the card's place)
EDGE, IPR, END = "#ffffff", "#3e9dff", "#ffb000"


def edge_points(segs):
    """Points every SAMPLE m along wall edges ((n, 2, 3), the sidewalk on their left: street_profile.wall_edges): the
    points (m, 2), their normals into the sidewalk (m, 2) and the edge's own height there (m,)."""
    P, N, z = [], [], []
    for a, b in np.asarray(segs, float).reshape(-1, 2, 3):
        e = b[:2] - a[:2]
        L = float(np.hypot(*e))
        if L <= 0:
            continue
        k = max(1, int(round(L / SAMPLE)))
        t = (np.arange(k) + 0.5) / k
        P.append(a[:2] + e * t[:, None])
        N.append(np.repeat([[-e[1] / L, e[0] / L]], k, 0))
        z.append(a[2] + (b[2] - a[2]) * t)
    if not P:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0)
    return np.concatenate(P), np.concatenate(N), np.concatenate(z)


def measure(D, walk, lidar):
    """A survey file's sidewalk edges at walls read as the street surface holds them, where the sidewalk runs RUN m in:
    {p, n, own, foot, top, ipr, off, side, cls, wall}, a value per point (off: the nearest height's distance from IPR
    SW_KERB_SMEAR in; side: one of KINDS where off > OFF; cls and wall: the class and index of the area whose outline the
    point lies on); and the metres read."""
    import shapely
    import ground_mesh as gm
    import street_profile as sp
    ids = gm.wall_areas(D)
    walls = [D["areas"][i] for i in ids]
    P, N, own = edge_points(sp.wall_edges(D, walls))
    keep = sp.runs_in(walk, P, N, RUN)
    P, N, own = P[keep], N[keep], own[keep]
    r = P + N * sp.SW_KERB_SMEAR
    ref = np.asarray(lidar(r[:, 0], r[:, 1]), float).reshape(-1)
    foot, top = sp.WallLevels(D, walls).around(P[:, 0], P[:, 1])
    c = np.stack([own, foot, top])
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # (a point with no wall height near it: NaN)
        d = np.abs(c - ref[None])
        off = np.min(np.where(np.isfinite(d), d, np.inf), axis=0)
        lo, hi = np.nanmin(c, axis=0), np.nanmax(c, axis=0)
    off = np.where(np.isfinite(ref) & np.isfinite(off), off, np.nan)
    side = np.full(len(P), "", object)
    bad = off > OFF
    side[bad & (lo - ref > OFF)] = "over"
    side[bad & (ref - hi > OFF)] = "under"
    side[bad & (side == "")] = "between"
    rings, owner = [], []
    for i in ids:
        a = D["areas"][i]
        for ring in [a["r"]] + a.get("h", []):
            if len(ring) >= 2:
                rings.append(shapely.LineString([q[:2] for q in ring] + [ring[0][:2]]))
                owner.append(i)
    wall = np.full(len(P), -1)
    if rings and len(P):
        k, j = shapely.STRtree(rings).query_nearest(shapely.points(P), all_matches=False)
        wall[k] = np.asarray(owner)[j]
    cls = np.array([D["areas"][w]["c"] if w >= 0 else "" for w in wall], object)
    return {"p": P, "n": N, "own": own, "foot": foot, "top": top, "ipr": ref, "off": off, "side": side, "cls": cls,
            "wall": wall}, len(P) * SAMPLE


def held(m, i):
    """The height the street surface holds point i at: of its own and the wall's foot and top, the nearest IPR."""
    c = np.array([m["own"][i], m["foot"][i], m["top"][i]], float)
    return float(c[np.argmin(np.where(np.isfinite(c), np.abs(c - m["ipr"][i]), np.inf))])


def table(counts):
    out = [f"| line | sidewalk edge at walls, m | over {OFF} m off IPR, m | " + " | ".join(f"{k}, m" for k, _ in KINDS)
           + " | on walls / stairs / strips, m | stretches (of them " + f"{SHORT:.0f} m or more) |",
           "|---|---|---|" + "---|" * len(KINDS) + "---|---|"]
    for ln, n in counts.items():
        out.append(f"| {ln} | {n['read']:,.0f} | {n['off']:,.0f} | " + " | ".join(f"{n[k]:,.0f}" for k, _ in KINDS)
                   + f" | {n['wall']:,.0f} / {n['stairs']:,.0f} / {n['paved']:,.0f} | {n['stretches']} ({n['long']}) |")
    return "\n".join(out)


def count(m, read):
    bad = m["off"] > OFF
    n = {"read": read, "off": bad.sum() * SAMPLE}
    for k, _ in KINDS:
        n[k] = (m["side"] == k).sum() * SAMPLE
    for c in CLASSES:
        n[c] = (bad & (m["cls"] == c)).sum() * SAMPLE
    S, _ = stretches({"0": m})
    n["stretches"], n["long"] = len(S), sum(s["length"] >= SHORT for s in S)
    return n


def stretches(per_line):
    """The off points of every line ({line: measure()}), merged (a point on two lines' files once) and joined into
    stretches (points within JOIN m): [{i: their points, lines, length, worst: the point furthest off, side, cls}] with
    each point's values in `at` (the measure's arrays, the lines' points concatenated)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from scipy.spatial import cKDTree
    keys = ("p", "n", "own", "foot", "top", "ipr", "off", "side", "cls", "wall")
    parts, lines = [], []
    for ln in sorted(per_line, key=int):
        m = per_line[ln]
        k = np.flatnonzero(m["off"] > OFF)
        parts.append({key: m[key][k] for key in keys})
        lines += [ln] * len(k)
    at = {key: np.concatenate([p[key] for p in parts]) if parts else np.zeros(0) for key in keys}
    at["line"] = np.asarray(lines, object)
    if not len(lines):
        return [], at
    tree = cKDTree(at["p"])
    same = tree.query_pairs(0.05, output_type="ndarray")   # (one point on two lines' files)
    first = np.arange(len(lines))
    for a, b in same:
        first[max(a, b)] = min(first[a], first[b])
    pairs = tree.query_pairs(JOIN, output_type="ndarray")
    n = len(lines)
    g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n)) if len(pairs) else coo_matrix((n, n))
    _, lab = connected_components(g, directed=False)
    out = []
    for s in np.unique(lab):
        i = np.flatnonzero(lab == s)
        own = i[first[i] == i]   # (each place once)
        w = i[np.argmax(at["off"][i])]
        sides, cls = at["side"][own], at["cls"][own]
        out.append({"i": i, "lines": sorted(set(at["line"][i]), key=int), "length": len(own) * SAMPLE, "worst": int(w),
                    "side": max(set(sides), key=list(sides).count), "cls": max(set(cls), key=list(cls).count)})
    return out, at


def answered(truth):
    """The answered places in the city frame: [(x, y)]."""
    got = truth.get("sidewalkWallsReview", {}).get("answers", [])
    if not got:
        return np.zeros((0, 2))
    F = Frame()
    return np.array([[float(v) for v in F.xy(*a["place"])] for a in got], float).reshape(-1, 2)


def choose(S, at, done):
    """The stretches that get a card: of each of GROUPS the PER_GROUP longest of SHORT m or more, those of SPREAD m
    or more on a line without a card of the group yet first; none with a point within NEAR of an answered place (done: (k, 2)), nor its worst point within APART of
    a chosen one's."""
    def free(s):
        return not len(done) or np.min(np.hypot(*(at["p"][s["i"]][:, None, :] - done[None]).transpose(2, 0, 1))) > NEAR
    out = []

    def apart(s):
        return all(np.hypot(*(at["p"][s["worst"]] - at["p"][c["worst"]])) > APART for c in out)
    for g in GROUPS:
        ks = sorted((s for s in S if group(s) == g and s["length"] >= SHORT and free(s)), key=lambda s: -s["length"])
        pick, seen = [], set()
        for first in (True, False):
            for s in ks:
                later = seen & set(s["lines"]) or s["length"] < SPREAD
                if len(pick) < PER_GROUP and all(s is not c for c in pick) and not (first and later) and apart(s):
                    pick.append(s)
                    out.append(s)
                    seen |= set(s["lines"])
    return out


def ends(p):
    """The two points of a stretch furthest apart along its main direction."""
    if len(p) < 2:
        return p[0], p[0]
    c = p - p.mean(0)
    t = c @ np.linalg.svd(c, full_matrices=False)[2][0]
    return p[np.argmin(t)], p[np.argmax(t)]


def card(s, at, F=None):
    import street_profile as sp
    F = F or Frame()
    w = s["worst"]
    x, y = at["p"][w]
    q = at["p"][w] + at["n"][w] * sp.SW_KERB_SMEAR
    lat, lon = (float(v) for v in F.ll(x, y))
    qlat, qlon = (float(v) for v in F.ll(*q))
    z, ref = held(at, w), float(at["ipr"][w])
    own, foot, top = (float(at[k][w]) for k in ("own", "foot", "top"))
    a, b = ends(at["p"][s["i"]])
    ln = at["line"][w]
    shared = f" (on lines {', '.join(s['lines'])})" if len(s["lines"]) > 1 else ""
    wall = (f"the wall's outline near it from {foot:.2f} m to {top:.2f} m" if np.isfinite(foot) else
            f"no point of the wall's outline within {sp.WALL_LOCAL:.0f} m")
    info = (f"A sidewalk's edge along a survey {CLASSES.get(s['cls'], s['cls'])} for {s['length']:.0f} m{shared}, where "
            f"{dict(KINDS)[s['side']]}. At the white pin the survey has the edge at {own:.2f} m and {wall}; "
            f"IPR's lidar reads {ref:.2f} m {sp.SW_KERB_SMEAR} m in on the "
            f"sidewalk's side (the blue pin). The street surface holds the edge at {z:.2f} m, the nearest of the survey's, "
            f"so the walkway {'rises' if z > ref else 'falls'} {abs(z - ref):.1f} m in its last {sp.SW_KERB_SMEAR} m to "
            f"the wall (area {int(at['wall'][w])} of line {ln} in this build). At which level does the walkway meet the "
            "wall here? The orange pins are the stretch's ends.")
    return {"kind": KIND, "id": f"sidewalk-wall-{lat:.5f}-{lon:.5f}", "line": ln, "lines": s["lines"],
            "x": round(float(x), 1), "y": round(float(y), 1), "mag": round(s["length"], 1), "status": "review",
            "place": [round(lat, 7), round(lon, 7)], "inside": [round(qlat, 7), round(qlon, 7)], "side": s["side"],
            "survey": round(z, 2), "lidar": round(ref, 2),
            "marks": [{"x": round(float(x), 1), "y": round(float(y), 1), "label": f"survey {z:.2f} m", "color": EDGE},
                      {"x": round(float(q[0]), 1), "y": round(float(q[1]), 1), "label": f"IPR {ref:.2f} m", "color": IPR},
                      {"x": round(float(a[0]), 1), "y": round(float(a[1]), 1), "label": "the stretch's end", "color": END},
                      {"x": round(float(b[0]), 1), "y": round(float(b[1]), 1), "label": "the stretch's end", "color": END}],
            "options": [k for k, _ in ANSWERS] + [UNSURE], "info": info}


def listing(S, at, n):
    out = []
    for g in GROUPS + [None]:
        ks = sorted((s for s in S if group(s) == g), key=lambda s: -s["length"])
        out.append(f"{g or 'between'}: {len(ks)} stretches, {sum(s['length'] for s in ks):,.0f} m "
                   f"({sum(s['length'] >= SHORT for s in ks)} of {SHORT:.0f} m or more)")
        for s in ks[:n]:
            w = s["worst"]
            out.append(f"    ({at['p'][w][0]:.1f}, {at['p'][w][1]:.1f}) lines {','.join(s['lines'])}: {s['length']:.1f} m on "
                       f"a {s['cls']} (area {int(at['wall'][w])}), own {at['own'][w]:.2f}, wall {at['foot'][w]:.2f}-"
                       f"{at['top'][w]:.2f}, IPR in {at['ipr'][w]:.2f}, held {held(at, w):.2f}")
    return "\n".join(out)


def load(ln):
    import street_profile as sp
    ctx = sp.context(ln)
    F, ipr = ctx["F"], ctx["ipr"]

    def lidar(x, y):
        return np.asarray(ipr.sample(np.asarray(x) + F.E0, np.asarray(y) + F.N0), float)
    return measure(ctx["dtm"], ctx["walk"], lidar)


def write_sets(lines, per_line):
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    S, at = stretches(per_line)
    chosen = choose(S, at, answered(truth))
    F = Frame()
    cards = [card(s, at, F) for s in chosen]
    print(f"\n{len(S)} stretches, {sum(s['length'] >= SHORT for s in S)} of {SHORT:.0f} m or more; cards: {len(cards)}")
    for ln in lines:
        cs = [c for c in cards if ln in c["lines"]]
        path = ROOT / "reports" / "review" / f"sidewalk-walls-{ln}.json"
        if not cs:
            if path.exists():
                os.remove(path)
            print(f"line {ln}: no cards")
            continue
        body = {"schema": 1, "issue": 653, "line": ln, "title": "Sidewalks at a wall: at which level the walkway meets it",
                "findings": cs}
        with replacing(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {ln}: {len(cs)} cards ({path.relative_to(ROOT).as_posix()})")


TRUTH_NOTE = ("The user's answers to the review of sidewalks at a wall (reports/review/sidewalk-walls-N.json, "
              "tools/sidewalk_walls_review.py, #653): at which level the walkway meets the wall where the survey's heights "
              "there and IPR's lidar part. `place` is the sidewalk's edge on the wall's line, `inside` IPR's reading "
              "1.5 m in on the sidewalk's side (lat, lon), `survey` and `lidar` the heights the card showed there (m); "
              "`level` is lidar, survey, no walkway, or unsure (which no rule reads).")


def do_import(lines, reviews, truth_p=None, folder=None):
    """The answers of review mode's files (reviews/lineN.json) to the cards of `folder` (reports/review) into the truth
    file's sidewalkWallsReview, the newest answer of a card; an answer already there stays unless answered again."""
    truth_p = truth_p or ROOT / "data" / "truth.json"
    folder = folder or ROOT / "reports" / "review"
    cards, newest = {}, {}
    for ln in lines:
        cp = Path(folder) / f"sidewalk-walls-{ln}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                cards.setdefault(c["id"], c)
        ap = Path(reviews) / f"line{ln}.json"
        ap = ap if ap.is_absolute() else ROOT / ap
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == KIND and r.get("v") in ANSWER and r.get("id") in cards:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    old = json.loads(truth_p.read_text(encoding="utf-8")).get("sidewalkWallsReview", {}).get("answers", [])
    got = {a["id"]: a for a in old}
    for i, r in newest.items():
        c = cards[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "lines": c["lines"], "place": c["place"], "inside": c["inside"], "survey": c["survey"],
                  "lidar": c["lidar"], "level": ANSWER[r["v"]], **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, review of sidewalks at a wall (reports/review/sidewalk-walls-{c['line']}.json), {day} (#653)"}
    answers = sorted(got.values(), key=lambda a: a["id"])
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": answers})
    print(f"{truth_p.name} sidewalkWallsReview: {len(answers)} answers ({len(newest)} from this import)")


def write_truth(p, section, key="sidewalkWallsReview"):
    """data/truth.json's `key` section, the rest of the file as it is (as tools/stairs_review.py write_truth)."""
    import stairs_review
    stairs_review.write_truth(p, section, key)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default=LINES)
    ap.add_argument("--table", action="store_true", help="the table alone, no review sets written")
    ap.add_argument("--list", type=int, default=0, metavar="N", help="and each kind's N longest stretches")
    ap.add_argument("--import", dest="imp", action="store_true", help="the user's answers into data/truth.json")
    ap.add_argument("--reviews", default="reports/reviews")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    lines = a.lines.split(",")
    if a.imp:
        do_import(lines, a.reviews)
        return
    import snapshot
    snapshot.require_current_data()  # (#835)
    t0 = time.time()
    per_line, counts = {}, {}
    for ln in lines:
        per_line[ln], read = load(ln)
        counts[ln] = count(per_line[ln], read)
    print(table(counts))
    print(f"({time.time() - t0:.0f} s)")
    if a.list:
        print()
        print(listing(*stretches(per_line), a.list))
    if not a.table:
        write_sets(lines, per_line)


if __name__ == "__main__":
    main()
