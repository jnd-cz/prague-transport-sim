# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross level of street track from the road's crossfall (#538): the rails of a track in a sloping street junction
lie in the road and tilt with it, one rail above the other.

    python -P -E tools/cross_level.py --line 37      # writes `crossLevel` into data/line37.json
    python -P -E tools/cross_level.py --cards        # the review cards, reports/review/cross-level-N.json
    python -P -E tools/cross_level.py --import       # the answers (tools/deploy.py --pull-reviews) into truth.json

The user, 2026-11-13 (#538), on the Sokolovská junction at Palmovka: "it's noticeable in real ride and I know this as
famous, albeit extreme example where single straight track in junction tilts sideways".

Every STEP m along our route (`path`, s from 0 as tools/route.py and the page count it):
- **Where:** paved track (the line's `styles`: not grass or ballast; not within NEAR_SPAN of a span or a tunnel), with
  the opposite track beside ours (`heights.backOff`, ACROSS m off). Not OSM's dedicated flag: Sokolovská's tilted
  junction is dedicated track by it for all but 34 of its 50 m. Across one track IPR's 1 m raster reads the bed's
  own edges and kerbs (6-7 % "tilts" along Plzeňská, line 9), so single track stays level.
- **The plane:** one plane fitted to IPR across both tracks (from BEYOND m outside ours to BEYOND m outside the
  opposite one) over ±ALONG m along. Its fall across, where its residual is under RESID (a crown between the tracks,
  a kerb or a platform in the band make it larger: such a road is not one plane).
- **Level** where the plane falls less than LEVEL. The norm's road crossfall is 2.5 %, but the tracks' band is laid
  level across a crowned street; measured on the five lines' clean planes the fall is 0.3-0.7 % (p50), 1-2.4 % (p90).
  A stretch that reaches LEVEL keeps its flanks down to FLANK.
- **Smoothed** over ±SMOOTH m and capped at CANT_MAX. Ramps of at most CANT_MAX per 30 m (tools/cant.py's limit): where the
  road tilts faster, the ramp starts earlier and ends later, keeping the full tilt (`extend`).

Written as cant is (the page's `atan2(c, 1.5)`, + = the left rail lower), in 0.01 mm every STEP m, for our route and
for the opposite one where it runs beside ours (the same plane, the sign as its direction reads it). Kept apart from
`cant`: the lean, the rails and the crossings take it (src/route.js `rollAt`); the curves' speed credit does not.
`places` lists every stretch with cross level (the debug overlay's log of this heuristic).

**The review:** a card for each stretch of CARD_MM or more (one card for a place on several lines), its pins where
the stretch starts and ends. The answers go to data/truth.json `crossLevelReview`: "level" makes paved track between
the pins level on every line, "tilts" keeps it (and the place gets no card again); unsure is held. The rule has no
independent source to be calibrated on: the answers are its check.
"""
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from cant import CANT_MAX  # noqa: E402
from route import Route  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STEP = 2.0               # m, as `cant` and `heights`
GAUGE = 1.5              # m between the rails' centres, as the page's lean (src/route.js rollAt)
ACROSS = (2.0, 6.0)      # m: the opposite track beside ours (tools/line_heights.py ACROSS_MIN, ACROSS_MAX)
BEYOND = 1.4             # m: the band outside each track's centre (half the bed, 2.7 m, src/world.js)
ALONG = 3.0              # m either side along
RESID = 0.02             # m: the plane's residual (std) under which the band is one plane
LEVEL = 0.02             # fall under which the tracks are level
FLANK = 0.005            # a tilted stretch's flanks: the fall down to this on either side
SMOOTH = 6.0             # m either side
NEAR_SPAN = 10.0         # m around a span or a tunnel
OPEN_BED = {"grass", "ballast"}  # styles whose rails stand on sleepers, not in a paved surface
CARD_MM = 20             # mm: a stretch this tilted gets a review card
SAME = 20                # m: two lines' stretches whose largest values lie this close are one card
LINES = "9,17,22,23,37"
TILTS, LEVEL_ANSWER, UNSURE = ("the rails tilt across like this", "level: the road tilts, the rails do not", "unsure")
ANSWER = {TILTS: "tilts", LEVEL_ANSWER: "level"}


def stations(rt, n):
    s = np.arange(n) * STEP
    a = [rt.at(v) for v in s]
    return s, np.array([q[:2] for q in a]), np.array([q[2:] for q in a])


def masks(data, s):
    """Paved track: not a grass or ballast section of the line's `styles` (tools/track_styles.py; 'panels' where none
    says), not near a span or a tunnel."""
    out = np.ones(len(s), bool)
    for st in data.get("styles") or []:
        if st["style"] in OPEN_BED:
            out &= ~((s >= st["s0"]) & (s <= st["s1"]))
    for a, b in data.get("spans") or []:
        out &= ~((s > a - NEAR_SPAN) & (s < b + NEAR_SPAN))
    for t in data.get("tunnels") or []:
        a, b = (t["s0"], t["s1"]) if isinstance(t, dict) else t[:2]
        out &= ~((s > a - NEAR_SPAN) & (s < b + NEAR_SPAN))
    return out


def planes(sample, xy, h, off):
    """Fall across (left up > 0) and residual of the plane through IPR across the band of each sample: from BEYOND
    outside ours to BEYOND outside the opposite track at `off` (left > 0). NaN where too few cells read."""
    n = len(xy)
    nl = np.column_stack([-h[:, 1], h[:, 0]])
    lo = np.minimum(0, off) - BEYOND
    hi = np.maximum(0, off) + BEYOND
    u = np.linspace(0, 1, 9)
    al = np.array([-ALONG, -ALONG / 2, 0, ALONG / 2, ALONG])
    o = (lo[:, None] + (hi - lo)[:, None] * u[None, :])[:, :, None] * np.ones(len(al))
    a = np.ones(len(u))[None, :, None] * al[None, None, :] * np.ones((n, 1, 1))
    o, a = o.reshape(n, -1), a.reshape(n, -1)
    X = xy[:, 0:1] + nl[:, 0:1] * o + h[:, 0:1] * a
    Y = xy[:, 1:2] + nl[:, 1:2] * o + h[:, 1:2] * a
    Z = np.asarray(sample(X.ravel(), Y.ravel()), float).reshape(X.shape)
    fall, res = np.full(n, np.nan), np.full(n, np.nan)
    for i in range(n):
        ok = np.isfinite(Z[i])
        if ok.sum() < 0.8 * Z.shape[1]:
            continue
        A = np.column_stack([o[i][ok], a[i][ok], np.ones(ok.sum())])
        c = np.linalg.lstsq(A, Z[i][ok], rcond=None)[0]
        fall[i], res[i] = c[0], float(np.std(Z[i][ok] - A @ c))
    return fall, res


def ramp(c, d):
    """Ramps of at most d per sample, each sign's stretches on their own (tools/cant.py's ramps), lowering values: after
    a level answer, and where two opposite tilts meet closer than their ramps."""
    out = []
    for part in (np.maximum(c, 0), np.maximum(-c, 0)):
        x = part.copy()
        for i in range(1, len(x)):
            x[i] = min(x[i], x[i - 1] + d)
        for i in range(len(x) - 2, -1, -1):
            x[i] = min(x[i], x[i + 1] + d)
        out.append(x)
    return out[0] - out[1]


def cross_level(fall, res, street, pair):
    """Signed cross level (m, + = the left rail lower) from the planes' fall: smoothed, level under LEVEL, ramped,
    capped."""
    ok = street & pair & np.isfinite(fall) & (res < RESID)
    f = np.where(ok, fall, 0.0)
    w = ok.astype(float)
    k = int(round(SMOOTH / STEP))
    ker = np.ones(2 * k + 1)
    num, den = np.convolve(f, ker, "same"), np.convolve(w, ker, "same")
    # (a sample whose own plane was not clean takes its clean neighbours' within SMOOTH: one rejected fit in the middle
    # of Sokolovská's tilt, at s 3746, made it level there and the ramps pulled the 75 mm down to a 67 mm peak)
    sm = np.where(street & pair & (den > 0), num / np.maximum(den, 1e-9), 0.0)
    # (a stretch falling LEVEL or more keeps the fall's own flanks down to FLANK on either side: the road's tilt comes
    # and goes over them, and a cut at LEVEL would leave a step for the ramp to spread inwards, 47 of Sokolovská's
    # 78 mm)
    keep = np.zeros(len(sm), bool)
    for sg in (1, -1):
        run = sg * sm >= FLANK
        i = 0
        while i < len(sm):
            if not run[i]:
                i += 1
                continue
            j = i
            while j + 1 < len(sm) and run[j + 1]:
                j += 1
            if (sg * sm[i:j + 1] >= LEVEL).any():
                keep[i:j + 1] = True
            i = j + 1
    sm = np.where(keep, sm, 0.0)
    c = np.clip(-sm * GAUGE, -CANT_MAX, CANT_MAX)
    c = extend(c, CANT_MAX / 30 * STEP)
    return np.where(np.abs(c) < 0.002, 0.0, c), ok


def extend(c, d):
    """Ramps of at most d per sample that keep every value: where the road tilts faster than the ramp allows, the
    ramp starts earlier and ends later instead (the user, 2026-11-13, #538: "If the road tilts faster then extend the
    start/end of twist back/forward"). Each sign's stretches on their own."""
    out = []
    for part in (np.maximum(c, 0), np.maximum(-c, 0)):
        x = part.copy()
        for i in range(1, len(x)):
            x[i] = max(x[i], x[i - 1] - d)
        for i in range(len(x) - 2, -1, -1):
            x[i] = max(x[i], x[i + 1] - d)
        out.append(x)
    return out[0] - out[1]


def opposite(c, xy, h, xyb, hb):
    """The cross level on the opposite route: our value where its sample has ours within ACROSS, the sign as its own
    direction reads it."""
    out = np.zeros(len(xyb))
    for a in range(0, len(xyb), 2000):
        q = xyb[a:a + 2000]
        d = np.hypot(q[:, None, 0] - xy[None, :, 0], q[:, None, 1] - xy[None, :, 1])
        j = d.argmin(axis=1)
        near = d[np.arange(len(q)), j] <= ACROSS[1]
        same = np.sign((hb[a:a + 2000] * h[j]).sum(axis=1))
        out[a:a + 2000] = np.where(near, c[j] * same, 0.0)
    return out


def places(s, xy, c):
    """Each stretch with cross level: where it starts, its length, its largest value (mm) and where."""
    out, i, n = [], 0, len(c)
    while i < n:
        if not c[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and c[j + 1] and np.sign(c[j + 1]) == np.sign(c[i]):
            j += 1
        k = i + int(np.argmax(np.abs(c[i:j + 1])))
        out.append({"s": round(float(s[i])), "length": round(float(s[j] - s[i] + STEP)), "x": round(float(xy[k, 0]), 1),
                    "y": round(float(xy[k, 1]), 1), "mm": round(float(c[k]) * 1000, 1)})
        i = j + 1
    return out


def between(xy, a, b, r=ACROSS[1]):
    """Samples within r m of the segment a-b (local x, y)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    u = np.clip(((xy - a) @ d) / max(float(d @ d), 1e-9), 0, 1)
    return np.hypot(*(xy - (a + u[:, None] * d)).T) <= r


def answered(c, xy, truth):
    """The user's answers (truth.json `crossLevelReview`): level between a "level" card's pins."""
    from geo import Frame
    F = Frame()
    for a in (truth.get("crossLevelReview") or {}).get("answers", []):
        if a["answer"] == "level":
            p, q = (F.xy(*ll) for ll in a["between"])
            c = np.where(between(xy, p, q), 0.0, c)
    return c


def build(data, sample, truth=None):
    rt = Route(data["path"])
    H = data["heights"]
    n = int(math.floor(rt.length / STEP)) + 1
    s, xy, h = stations(rt, n)
    off = np.array([np.nan if v is None else v for v in (H.get("backOff") or [])][:n] + [np.nan] * max(0, n - len(H.get("backOff") or [])), float)
    pair = np.isfinite(off) & (np.abs(off) >= ACROSS[0]) & (np.abs(off) <= ACROSS[1])
    street = masks(data, s)
    fall, res = planes(sample, xy, h, np.where(pair, off, 0.0))
    c, _ = cross_level(fall, res, street, pair)
    c = ramp(answered(c, xy, truth or {}), CANT_MAX / 30 * STEP)  # (a level answer's ends ramp too)
    out = {"step": STEP, "unit": 1e-5, "path": [int(round(v * 1e5)) for v in c]}
    if len(data.get("pathBack") or []) > 1:
        rb = Route(data["pathBack"])
        _, xyb, hb = stations(rb, int(math.floor(rb.length / STEP)) + 1)
        out["pathBack"] = [int(round(v * 1e5)) for v in opposite(c, xy, h, xyb, hb)]
    out["places"] = places(s, xy, c)
    return out


def cards(lines):
    """reports/review/cross-level-N.json: a card for each stretch of CARD_MM or more, not yet answered."""
    from geo import Frame
    F = Frame()
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    # (a place answered, or a fact from the user, by its two points: its card is not asked again)
    done = [[F.xy(*ll) for ll in a["between"]] for a in (truth.get("crossLevelReview") or {}).get("answers", [])]
    per = {}
    for line in lines:
        data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        rt = Route(data["path"])
        out = []
        for q in data["crossLevel"]["places"]:
            if abs(q["mm"]) < CARD_MM:
                continue
            a, b = rt.at(q["s"])[:2], rt.at(q["s"] + q["length"])[:2]
            lat, lon = (float(v) for v in F.ll(q["x"], q["y"]))
            near = min(data["stops"], key=lambda st: abs(st["s"] - q["s"]))
            side = "left" if q["mm"] > 0 else "right"
            out.append({
                "kind": "cross level", "id": f"cross-{lat:.4f}-{lon:.4f}", "line": line, "x": q["x"], "y": q["y"],
                "s0": q["s"], "s1": q["s"] + q["length"], "mag": abs(q["mm"]), "status": "review",
                "place": [round(lat, 6), round(lon, 6)],
                "between": [[round(float(v), 7) for v in F.ll(*a)], [round(float(v), 7) for v in F.ll(*b)]],
                "marks": [{"x": round(a[0], 1), "y": round(a[1], 1), "label": "the tilt starts", "color": "#3e9dff"},
                          {"x": round(b[0], 1), "y": round(b[1], 1), "label": "the tilt ends", "color": "#ffffff"}],
                "options": [TILTS, LEVEL_ANSWER, UNSURE],
                "info": f"near {near['name']}: the road falls across both tracks here and the build tilts the rails "
                        f"with it, the {side} rail up to {abs(q['mm']):.0f} mm lower ({abs(q['mm']) / 15:.1f} % across "
                        f"the gauge) for {q['length']} m (s {q['s']}-{q['s'] + q['length']}). Do the rails tilt across "
                        f"here in reality?"})
        per[line] = out
    flat = [c for cs in per.values() for c in cs]
    for c in flat:
        twin = next((o for o in flat if o is not c and o["id"] != c["id"] and o["line"] != c["line"]
                     and math.hypot(o["x"] - c["x"], o["y"] - c["y"]) < SAME), None)
        if twin and int(twin["line"]) < int(c["line"]):
            c["id"] = twin["id"]
    for c in flat:
        c["lines"] = sorted({o["line"] for o in flat if o["id"] == c["id"]}, key=int)
    for line, cs in per.items():
        cs = [c for c in cs if not any(between(np.array([[c["x"], c["y"]]]), p, q)[0] for p, q in done)]
        p = ROOT / "reports" / "review" / f"cross-level-{line}.json"
        if not cs:
            if p.exists():
                os.remove(p)
            print(f"line {line}: no cards")
            continue
        body = {"schema": 1, "issue": 538, "line": line, "title": "Cross level: rails tilted with the road", "findings": cs}
        with replacing(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(body, f, ensure_ascii=False, indent=1)
        print(f"line {line}: {len(cs)} cards")


TRUTH_NOTE = ("The user's answers to the cross level review (reports/review/cross-level-N.json, tools/cross_level.py, "
              "#538): `level` makes paved track between the two points level on every line; `tilts` keeps the build's "
              "cross level there and takes the place off the review.")


def do_import(lines, reviews):
    found, newest = {}, {}
    for line in lines:
        cp = ROOT / "reports" / "review" / f"cross-level-{line}.json"
        if cp.exists():
            for c in json.loads(cp.read_text(encoding="utf-8"))["findings"]:
                found.setdefault(c["id"], c)
        ap = ROOT / reviews / f"line{line}.json"
        if ap.exists():
            a = json.loads(ap.read_text(encoding="utf-8"))
            items = a.get("items", a) if isinstance(a, dict) else a
            for r in (items.values() if isinstance(items, dict) else items):
                if r.get("kind") == "cross level" and r.get("v") in ANSWER and r.get("id") in found:
                    if r["id"] not in newest or r.get("t", 0) > newest[r["id"]].get("t", 0):
                        newest[r["id"]] = r
    truth_p = ROOT / "data" / "truth.json"
    sec = json.loads(truth_p.read_text(encoding="utf-8")).get("crossLevelReview", {})
    got = {a["id"]: a for a in sec.get("answers", [])}
    for i, r in newest.items():
        c = found[i]
        day = time.strftime("%Y-%m-%d", time.gmtime(r["t"] / 1000)) if r.get("t") else "?"
        got[i] = {"id": i, "lines": c["lines"], "between": c["between"], "answer": ANSWER[r["v"]],
                  **({"note": r["note"]} if r.get("note") else {}),
                  "source": f"user, cross level review (reports/review/cross-level-{c['line']}.json), {day} (#538)"}
    write_truth(truth_p, {**sec, "note": TRUTH_NOTE, "answers": sorted(got.values(), key=lambda a: a["id"])})
    print(f"data/truth.json crossLevelReview: {len(got)} answers ({len(newest)} from this import)")


def write_truth(p, section, name="crossLevelReview"):
    """data/truth.json's section, the rest of the file as it is (as tools/grass_review.py write_truth)."""
    text = p.read_text(encoding="utf-8")
    before = json.loads(text)
    key = f'\n "{name}": '
    body = json.dumps(section, ensure_ascii=False, indent=1).replace("\n", "\n ")
    if key in text:
        i = text.index(key) + len(key)
        text = text[:i] + body + text[json.JSONDecoder().raw_decode(text, i)[1]:]
    else:
        text = text.rstrip()[:-1].rstrip() + "," + key + body + "\n}\n"
    after = json.loads(text)
    assert after[name] == section
    assert {k: v for k, v in after.items() if k != name} == {k: v for k, v in before.items() if k != name}
    with replacing(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def main():
    if "--cards" in sys.argv or "--import" in sys.argv:
        lines = (sys.argv[sys.argv.index("--lines") + 1] if "--lines" in sys.argv else LINES).split(",")
        if "--import" in sys.argv:
            do_import(lines, sys.argv[sys.argv.index("--reviews") + 1] if "--reviews" in sys.argv else "reports/reviews")
        else:
            cards(lines)
        return
    if "--line" not in sys.argv:
        sys.exit(__doc__)
    line = sys.argv[sys.argv.index("--line") + 1]
    from geo import Frame
    from ipr_dtm import IprDtm
    F, ipr = Frame(), IprDtm()
    p = ROOT / "data" / f"line{line}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    data["crossLevel"] = build(data, lambda x, y: ipr.sample(x + F.E0, y + F.N0), truth)
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    pl = data["crossLevel"]["places"]
    big = sorted(pl, key=lambda q: -abs(q["mm"]))[:5]
    print(f"line {line}: cross level on {sum(q['length'] for q in pl)} m in {len(pl)} stretches"
          + (", the largest " + "; ".join(f"{q['mm']:+.0f} mm at ({q['x']:.0f}, {q['y']:.0f})" for q in big) if big else ""))


if __name__ == "__main__":
    main()
