# SPDX-License-Identifier: AGPL-3.0-or-later
"""Open ballast track from the lidar (#591): where the rails stand over IPR's bare earth, the lidar sees ballast.

    python -P -E tools/open_track.py --calibrate          # the measure against the user's marks, every line
    python -P -E tools/open_track.py --runs 9,17          # the runs it finds, per line
    python -P -E tools/open_track.py --cards              # reports/review/open-track-N.json: the runs not sure
    python -P -E tools/open_track.py --import             # the answers into data/truth.json openTrackReview

The rail top comes from its own measurements, not the build (tools/track_styles.py runs before the heights): DI's
numeric height where DI's track matches the route (tools/dtmp_tracks.py `Segments`), else the archive's where its
match is unambiguous. IPR's 2023 lidar (tools/ipr_dtm.py, 1 m, bare earth) is read at the axis and 0.5 m to either
side. Every STEP m: the rail top minus the lidar; its median over WINDOW m.

Calibrated 2026-11-14 on the user's marks and answers (lines 9, 17, 22, 23, 37, `--calibrate`), rails from DI / the
archive, outside bridges and tunnels:

| what the user says | median gap | flagged at THRESHOLD over WINDOW |
|---|---|---|
| ballast | +0.13 m (DI) / +0.18 m (archive) | 87 % |
| paved: embedded, panels, setts | -0.01 m | 0 % of the marks; 3 % with the junctions and road crossings |
| grass | +0.02 / -0.03 m | 13 % (the lidar sees the grass at rail level) |

So the measure finds ballast, not grass; grass comes first from the user's marks, the grassed-track list and the
survey's green, and the measure only fills what they leave. A run is MIN_RUN m or longer, its samples less than JOIN m
apart; one whose median stands over SURE m is not sure (a cutting or a ditch beside the track reads as deep: Bertramka
+0.38 to +0.43 m, Pražský hrad +0.31 m) and goes to a review card instead (tools/open_track.py --cards, #591).
"""
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route import Route  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STEP = 2.0        # m between samples along the route
WINDOW = 20.0     # m: the running median's span
THRESHOLD = 0.10  # m: the rail top this far over the lidar is ballast
SURE = 0.25       # m: a run whose median stands over this is not sure
MIN_RUN = 40.0    # m: a shorter run is not one
JOIN = 20.0       # m: runs this near are one
SIDES = (-0.5, 0.0, 0.5)   # m across the axis the lidar is read at
NEAR = 1.0        # m: a DI or archive track this near the route is the route's
LINES = "9,17,22,23,37"
BALLAST, GRASS, PAVED, UNSURE = ("open ballast", "grass", "paved: embedded, panels or setts", "unsure")
ANSWER = {BALLAST: "ballast", GRASS: "grass", PAVED: "paved"}
TRUTH_NOTE = ("The user's answers to the open track review (reports/review/open-track-N.json, tools/open_track.py, #591):"
              " what the track is between the card's two points: `ballast`, `grass`, or `paved` (the rules decide).")
READER = "tools/track_styles.py (open_answers: the style between the two points); tools/open_track.py (no card again)"


class Rails:
    """The rail top along a route from DI, else the archive (tools/dtmp_tracks.py)."""
    def __init__(self):
        from dtmp_tracks import Segments, archive_data, di_data
        _, di = di_data()
        _, _, arch = archive_data()
        self.di, self.arch = Segments(di), Segments(arch)

    def at(self, x, y, ux, uy):
        for seg, src in ((self.di, "di"), (self.arch, "archive")):
            m = seg.match(x, y, ux, uy, radius=NEAR)
            if m.get("status") == "numeric":
                return m["z"], src
        return None, None


def gaps(data, rails, lidar):
    """[(s, gap, source)] every STEP m of the route: the rail top minus the lidar, None where either is missing.
    `lidar(xs, ys)` samples the ground (arrays, our frame)."""
    rt = Route(data["path"], data.get("pathExt"))
    ss = np.arange(0.0, rt.length, STEP)
    at = [rt.at(s) for s in ss]
    xs, ys = np.array([a[0] for a in at]), np.array([a[1] for a in at])
    hx, hy = np.array([a[2] for a in at]), np.array([a[3] for a in at])
    g = np.nanmean([lidar(xs - hy * o, ys + hx * o) for o in SIDES], axis=0)
    out = []
    for i, s in enumerate(ss):
        z, src = rails.at(xs[i], ys[i], hx[i], hy[i])
        ok = z is not None and math.isfinite(g[i]) and abs(z - g[i]) < 2
        out.append((float(s), float(z - g[i]) if ok else None, src))
    return out


def medians(samples, window=WINDOW):
    """The running median of the gaps over `window` m: [(s, median or None)]."""
    s = np.array([x[0] for x in samples])
    v = np.array([np.nan if x[1] is None else x[1] for x in samples])
    out = []
    for i in range(len(s)):
        m = (np.abs(s - s[i]) <= window / 2) & np.isfinite(v)
        out.append((float(s[i]), float(np.median(v[m])) if m.sum() >= 3 else None))
    return out


def runs(med, skip=(), threshold=THRESHOLD, min_run=MIN_RUN, join=JOIN):
    """The runs where the median stands at `threshold` or over: [{s0, s1, median, sure}]. Samples inside `skip`
    ([[a, b]]: the bridges and tunnels, where the lidar reads the ground under or over the track) are left out."""
    hits = [(s, m) for s, m in med if m is not None and m >= threshold and not any(a <= s <= b for a, b in skip)]
    out, cur = [], None
    for s, m in hits:
        if cur and s - cur[1] <= join:
            cur[1] = s
            cur[2].append(m)
        else:
            cur = [s, s, [m]]
            out.append(cur)
    res = []
    for a, b, ms in out:
        if b - a >= min_run:
            med_ = float(np.median(ms))
            res.append({"s0": a, "s1": b, "median": round(med_, 3), "sure": med_ <= SURE})
    return res


def skip_of(data, pad=10.0):
    """The route's bridges and tunnels (build_line's `bridges` and `tunnels`), `pad` m past their ends."""
    return [[a - pad, b + pad] for a, b in (data.get("bridges") or []) + [list(t) for t in data.get("tunnels") or []]]


_LIDAR = None


def lidar():
    """IPR's lidar in our frame: f(xs, ys) -> heights (NaN where it has none)."""
    global _LIDAR
    if _LIDAR is None:
        from geo import Frame
        from ipr_dtm import IprDtm
        D, F = IprDtm(), Frame()
        _LIDAR = lambda xs, ys: D.sample(*F.to_jtsk(xs, ys))  # noqa: E731
    return _LIDAR


_RAILS = None


def found(data):
    """The runs on a line (tools/track_styles.py reads them): [{s0, s1, median, sure}]."""
    global _RAILS
    if _RAILS is None:
        _RAILS = Rails()
    return runs(medians(gaps(data, _RAILS, lidar())), skip_of(data))


def calibrate(lines):
    """The measure against what the user's marks and answers say the track is (the line's built `styles`, sources
    user, review, list and surface), and against the junctions and road crossings (#546's paved rule)."""
    TRUTH = {"user", "review", "list", "surface"}
    rails = Rails()
    by = {}
    for line in lines:
        d = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        smp = gaps(d, rails, lidar())
        med = dict(medians(smp))
        sk = skip_of(d)
        for s, v, src in smp:
            if v is None or any(a <= s <= b for a, b in sk):
                continue
            lab = None
            for x in d["styles"]:
                if x["s0"] <= s < x["s1"]:
                    if x["source"] in TRUTH:
                        lab = x["style"] if x["style"] in ("grass", "ballast") else "paved"
                    elif x["source"] in ("junction", "hole"):
                        lab = "junction"
            by.setdefault((lab, src), []).append((v, med.get(s)))
    print("| what | rails | m | median gap | p25 / p75 | flagged |")
    print("|---|---|---|---|---|---|")
    for (lab, src), vs in sorted(by.items(), key=lambda k: (str(k[0][0]), k[0][1])):
        v = np.array([x[0] for x in vs])
        f = np.mean([m is not None and m >= THRESHOLD for _, m in vs])
        print(f"| {lab or '(none)'} | {src} | {2 * len(v)} | {np.median(v):+.2f} | {np.percentile(v, 25):+.2f} / "
              f"{np.percentile(v, 75):+.2f} | {f:.0%} |")


def card(line, data, r, frame):
    rt = Route(data["path"], data.get("pathExt"))
    a, b, m = rt.at(r["s0"]), rt.at(r["s1"]), rt.at((r["s0"] + r["s1"]) / 2)
    la, lb, lm = ([round(float(v), 6) for v in frame.ll(p[0], p[1])] for p in (a, b, m))
    st = min(data["stops"], key=lambda q: abs(q["s"] - (r["s0"] + r["s1"]) / 2))
    return {
        "kind": "open track", "id": f"open-{lm[0]:.5f}-{lm[1]:.5f}", "line": line, "x": m[0], "y": m[1],
        "mag": round(r["median"] * 100), "status": "review", "place": lm, "between": [la, lb],
        "marks": [{"x": a[0], "y": a[1], "label": "from", "color": "#3e9dff"},
                  {"x": b[0], "y": b[1], "label": "to", "color": "#3e9dff"}],
        "options": [BALLAST, GRASS, PAVED, UNSURE],
        "info": f"near {st['name']}, route s {r['s0']:.0f}-{r['s1']:.0f} ({r['s1'] - r['s0']:.0f} m): the rails stand "
                f"{r['median'] * 100:.0f} cm over the lidar's ground, more than on open ballast elsewhere (13-18 cm). "
                "What is the track laid in here? (A cutting or a ditch beside the track can read this deep.)"}


def cards(lines):
    from geo import Frame
    F = Frame()
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    done = [F.xy(*a["place"]) for a in (truth.get("openTrackReview") or {}).get("answers", [])]
    asked = []
    for line in sorted(lines, key=int):
        data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        cs = []
        for r in found(data):
            if r["sure"]:
                continue
            c = card(line, data, r, F)
            if all(math.hypot(c["x"] - d[0], c["y"] - d[1]) >= MIN_RUN for d in done + asked):
                cs.append(c)
        asked += [(c["x"], c["y"]) for c in cs]
        p = ROOT / "reports" / "review" / f"open-track-{line}.json"
        if not cs:
            if p.exists():
                p.unlink()
            print(f"line {line}: no cards")
            continue
        from atomic import replacing
        body = {"schema": 1, "issue": 591, "line": line, "title": "Open track from the lidar: ballast, grass or paved",
                "findings": cs}
        with replacing(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {line}: {len(cs)} cards")


def do_import(lines, reviews):
    got_cards, newest = {}, {}
    for line in lines:
        cp = ROOT / "reports" / "review" / f"open-track-{line}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                got_cards.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{line}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "open track" and r.get("v") in ANSWER and r.get("id") in got_cards:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    sec = json.loads(truth_p.read_text(encoding="utf-8")).get("openTrackReview", {})
    got = {a["id"]: a for a in sec.get("answers", [])}
    for i, r in newest.items():
        c = got_cards[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "line": c["line"], "place": c["place"], "between": c["between"], "answer": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, open track review (reports/review/open-track-{c['line']}.json), {day} (#591)"}
    from cross_level import write_truth
    write_truth(truth_p, {"note": TRUTH_NOTE, "answers": sorted(got.values(), key=lambda a: a["id"])}, "openTrackReview")
    readers = json.loads(truth_p.read_text(encoding="utf-8"))["readers"]
    if "openTrackReview" not in readers:
        write_truth(truth_p, {**readers, "openTrackReview": READER}, "readers")
    print(f"data/truth.json openTrackReview: {len(got)} answers ({len(newest)} from this import)")


def main():
    lines = (sys.argv[sys.argv.index("--lines") + 1] if "--lines" in sys.argv else LINES).split(",")
    if "--calibrate" in sys.argv:
        calibrate(lines)
    elif "--cards" in sys.argv:
        cards(lines)
    elif "--import" in sys.argv:
        do_import(lines, sys.argv[sys.argv.index("--reviews") + 1] if "--reviews" in sys.argv else "reports/reviews")
    elif "--runs" in sys.argv:
        for line in sys.argv[sys.argv.index("--runs") + 1].split(","):
            d = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
            rs = found(d)
            print(f"line {line}: {len(rs)} runs, {sum(r['s1'] - r['s0'] for r in rs):.0f} m "
                  f"({sum(r['s1'] - r['s0'] for r in rs if not r['sure']):.0f} m not sure)")
            for r in rs:
                print(f"   s {r['s0']:.0f}-{r['s1']:.0f}  median {r['median']:+.2f}{'' if r['sure'] else '  (not sure)'}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
