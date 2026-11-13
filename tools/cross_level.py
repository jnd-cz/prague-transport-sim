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
- **Where it tilts:** IPR says so. A plane fitted to IPR across both tracks (from BEYOND m outside ours to BEYOND m
  outside the opposite one, ±ALONG m along) with a residual under RESID that falls LEVEL or more. A crown between the
  tracks, a kerb or a platform in the band make the residual larger: such a street is not one plane.
- **How much:** the slope between our two tracks' own tops of rail (`heights.path` and `backZ` across `backOff`),
  where it tilts the same way. The tracks lead (DI's survey and the vertical-curve fit along each): the rails, the
  street between them (the page's `heightAt`, linear between the two) and the road laid flush to them (src/world.js
  flushDtm) are then one plane (the user, 2026-11-13: "the tracks should lie on single plane with the road/street").
  At the first review's 58 places the two tracks' slope differed from IPR's plane by 0.5 % (median), the survey's by
  1.1 %; at Sokolovská the tracks and the survey say 2.7 %, IPR 5.2 %. Elsewhere the two tracks often differ by
  3-7 % where IPR says 0-2 % (line 22): a track's height is off there, so where the two disagree on a tilt of LEVEL
  or more the track stays level, listed in `disagree` (#539).
- **Level** where the fall is less than LEVEL. The norm's road crossfall is 2.5 %, but the tracks' band is laid
  level across a crowned street; measured on the five lines' clean planes the fall is 0.3-0.7 % (p50), 1-2.4 % (p90).
  A stretch that reaches LEVEL keeps its flanks down to FLANK.
- **Smoothed** over ±SMOOTH m and capped at CANT_MAX. Ramps of at most CANT_MAX per 30 m (tools/cant.py's limit): where the
  road tilts faster, the ramp starts earlier and ends later, keeping the full tilt (`extend`).

Written as cant is (the page's `atan2(c, 1.5)`, + = the left rail lower), in 0.01 mm every STEP m, for our route and
for the opposite one where it runs beside ours (the same plane, the sign as its direction reads it). Kept apart from
`cant`: the lean, the rails and the crossings take it (src/route.js `rollAt`); the curves' speed credit does not.
`places` lists every stretch with cross level (the debug overlay's log of this heuristic); `disagree` every stretch
where IPR's plane and the two tracks' slope disagree on a tilt of LEVEL or more (a track's height is off: #539).

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


def smooth(v, ok, around):
    """v's mean over ±SMOOTH m of the samples `ok`, at the samples `around` that have any (a sample whose own value was
    not clean takes its clean neighbours': one rejected plane in the middle of Sokolovská's tilt, at s 3746, made it
    level there and the ramps pulled the 75 mm down to a 67 mm peak)."""
    k = int(round(SMOOTH / STEP))
    ker = np.ones(2 * k + 1)
    num, den = np.convolve(np.where(ok, v, 0.0), ker, "same"), np.convolve(ok.astype(float), ker, "same")
    return np.where(around & (den > 0), num / np.maximum(den, 1e-9), 0.0)


def cross_level(fall, res, street, pair, tracks=None):
    """Signed cross level (m, + = the left rail lower): IPR's plane (`fall`, `res`) says where the street tilts, the
    two tracks' own slope (`tracks`, when given) how much, where it tilts the same way; smoothed, level under LEVEL,
    ramped, capped. Returns (c, ok, disagree): `disagree` the samples where IPR tilts and the tracks do not, or the
    other way."""
    ok = street & pair & np.isfinite(fall) & (res < RESID)
    sm = smooth(fall, ok, street & pair)
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
    disagree = np.zeros(len(sm), bool)
    if tracks is not None:
        okt = street & pair & np.isfinite(tracks)
        st = smooth(tracks, okt, street & pair)
        # (the tracks' slope where IPR's plane tilts and theirs the same way; where one tilts LEVEL or more and the
        # other not, or the other way, a track's height is off: level, and listed)
        same = keep & (np.sign(st) == np.sign(sm)) & (np.abs(st) >= FLANK)
        disagree = ok & ((np.abs(sm) >= LEVEL) | (np.abs(st) >= LEVEL)) & ~same
        sm = np.where(same, st, 0.0)
    c = np.clip(-sm * GAUGE, -CANT_MAX, CANT_MAX)
    c = extend(c, CANT_MAX / 30 * STEP)
    return np.where(np.abs(c) < 0.002, 0.0, c), ok, disagree


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
    fall_ipr, res = planes(sample, xy, h, np.where(pair, off, 0.0))
    z = np.array([np.nan if v is None else v for v in H["path"]][:n] + [np.nan] * max(0, n - len(H["path"])), float)
    zb = np.array([np.nan if v is None else v for v in (H.get("backZ") or [])][:n] + [np.nan] * max(0, n - len(H.get("backZ") or [])), float)
    fall = np.where(pair, (zb - z) / np.where(pair, off, 1.0), np.nan)  # (left up > 0, as the plane's)
    c, _, disagree = cross_level(fall_ipr, res, street, pair, tracks=fall)
    c = ramp(answered(c, xy, truth or {}), CANT_MAX / 30 * STEP)  # (a level answer's ends ramp too)
    out = {"step": STEP, "unit": 1e-5, "path": [int(round(v * 1e5)) for v in c]}
    if len(data.get("pathBack") or []) > 1:
        rb = Route(data["pathBack"])
        _, xyb, hb = stations(rb, int(math.floor(rb.length / STEP)) + 1)
        out["pathBack"] = [int(round(v * 1e5)) for v in opposite(c, xy, h, xyb, hb)]
    out["places"] = places(s, xy, c)
    # (where IPR's plane and the two tracks' heights disagree on a tilt of LEVEL or more: a track's height is off, #539)
    out["disagree"] = places(s, xy, np.where(disagree, fall - fall_ipr, 0.0) * 1000 / 1000)
    for q in out["disagree"]:
        k = int(round(q["s"] / STEP))
        q.pop("mm")
        j = min(range(k, min(n, k + int(q["length"] / STEP))), key=lambda i: -abs(fall[i] - fall_ipr[i])) if q["length"] > STEP else k
        q.update({"tracks %": round(float(fall[j]) * 100, 1), "IPR %": round(float(fall_ipr[j]) * 100, 1)})
    return out


def survey_tris(areas, near, r=30.0):
    """The survey's level-0 areas within r m of the points `near` as triangles with heights ((k, 3, 3)): the page
    fills an area linearly from its outline."""
    import shapely
    from shapely.geometry import Polygon
    pts = shapely.points(np.asarray(near, float))
    tris = []
    for a in areas:
        if a.get("l") != 0 or len(a.get("r") or []) < 3:
            continue
        xyz = [(q[0], q[1], np.nan if q[2] is None else q[2]) for q in a["r"]]
        g = Polygon(xyz, [[(q[0], q[1], np.nan if q[2] is None else q[2]) for q in hh] for hh in a.get("h", []) if len(hh) >= 3])
        if not g.is_valid or not shapely.dwithin(g, pts, r).any():
            continue
        for t in shapely.get_parts(shapely.constrained_delaunay_triangles(g)):
            c = np.asarray(t.exterior.coords)[:3]
            if c.shape[1] == 3 and np.all(np.isfinite(c)):
                tris.append(c)
    return np.array(tris)


def sample_tris(tris, x, y):
    """Heights of triangles at points, NaN outside every one (barycentric; as tools/street_profile.py, #512)."""
    import shapely
    z = np.full(len(x), np.nan)
    if not len(tris):
        return z
    tree = shapely.STRtree(shapely.polygons(tris[:, :, :2]))
    pi, ti = tree.query(shapely.points(x, y), predicate="intersects")
    a, b, c = tris[ti, 0], tris[ti, 1], tris[ti, 2]
    d = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(d) > 1e-9
    w1 = ((b[:, 1] - c[:, 1]) * (x[pi] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    w2 = ((c[:, 1] - a[:, 1]) * (x[pi] - c[:, 0]) + (a[:, 0] - c[:, 0]) * (y[pi] - c[:, 1])) / np.where(ok, d, 1)
    v = w1 * a[:, 2] + w2 * b[:, 2] + (1 - w1 - w2) * c[:, 2]
    z[pi[ok][::-1]] = v[ok][::-1]
    return z


PLANE_BEYOND = 5.0       # m past the outer track that the street continues the tracks' plane (src/terrain.js)
STREET_BELOW = 0.052     # m: a surveyed street vertex next to the track under its surface level (src/heights.js)


def street_line(u, z0, off, zb, zs, lift, w):
    """The street as the game lays it across the route (src/terrain.js heightAt, src/world.js flushDtm), approximately:
    the tracks' surface level (linear between the two tracks; past the outer one level, or the tracks' plane for
    PLANE_BEYOND m by w) less STREET_BELOW, fully within 5 m of our track, faded into the survey by 15 m."""
    if np.isfinite(off) and np.isfinite(zb) and abs(off) > 0.5:
        q = u / off
        past = np.where(q < 0, -q, np.where(q > 1, q - 1, 0)) * abs(off)
        h = z0 + (zb - z0) * np.clip(q, 0, 1) + np.sign(q) * np.minimum(past, PLANE_BEYOND) / abs(off) * (zb - z0) * w
    else:
        h = np.full(len(u), z0)
    flush = h - lift - STREET_BELOW
    k = np.clip((np.abs(u) - 5) / 10, 0, 1)
    f = 1 - k * k * (3 - 2 * k)
    return np.where(np.isfinite(zs), zs + (flush - zs) * f, np.where(f > 0.999, flush, np.nan))


def section_svg(line, s, p, hd, z0, off, zb, c, ipr_at, tris, lift=0.0, w=0.0):
    """A cross-section across the tracks at route position s (point p, heading hd), seen along the line: IPR, the
    survey's own surface, the street as the game lays it before (level past the tracks, as main) and after (the tracks'
    plane past them by w), and each track's rails before (level) and after (the cross level c, + = the left rail
    lower). Heights exaggerated."""
    nl = np.array([-hd[1], hd[0]])
    has_b = np.isfinite(off) and np.isfinite(zb)
    lo = (min(0.0, off) if has_b else 0.0) - 8.0
    hi = (max(0.0, off) if has_b else 0.0) + 8.0
    u = np.arange(lo, hi + 1e-9, 0.25)
    along = np.array([-1.0, -0.5, 0.0, 0.5, 1.0])
    X = p[0] + nl[0] * u[:, None] + hd[0] * along[None, :]
    Y = p[1] + nl[1] * u[:, None] + hd[1] * along[None, :]
    zi = np.nanmean(np.asarray(ipr_at(X.ravel(), Y.ravel()), float).reshape(X.shape), axis=1)
    zs = sample_tris(tris, p[0] + nl[0] * u, p[1] + nl[1] * u)
    tracks = [(0.0, z0)] + ([(off, zb)] if has_b else [])
    allz = np.concatenate([zi[np.isfinite(zi)], zs[np.isfinite(zs)], [t[1] for t in tracks]]) - z0
    zr = math.ceil(min(1.6, max(0.2, float(np.percentile(np.abs(allz), 98)) + 0.05)) * 5) / 5  # (grid every 5 cm multiple)
    W, H, L, R, T, B = 640, 300, 46, 14, 34, 54
    px = lambda v: L + (hi - v) / (hi - lo) * (W - L - R)  # noqa: E731  (seen along the line: its left on the left)
    py = lambda z: T + (zr - (z - z0)) / (2 * zr) * (H - T - B)  # noqa: E731
    ex = ((H - T - B) / (2 * zr)) / ((W - L - R) / (hi - lo))

    def poly(z, col, w, dash=""):
        segs, cur = [], []
        for v, q in zip(u, z):
            if np.isfinite(q):
                cur.append(f"{px(v):.1f},{py(q):.1f}")
            elif cur:
                segs.append(cur)
                cur = []
        if cur:
            segs.append(cur)
        return "".join(f'<polyline fill="none" stroke="{col}" stroke-width="{w}"{dash} points="{" ".join(sg)}"/>' for sg in segs)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="12">',
           f'<rect width="{W}" height="{H}" fill="#1d2127"/>']
    for k in range(-4, 5):  # height grid every zr / 4
        z = z0 + k * zr / 4
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{py(z):.1f}" y2="{py(z):.1f}" stroke="#333a44"/>'
                   f'<text x="{L - 4}" y="{py(z) + 4:.1f}" fill="#8a94a3" text-anchor="end">{k * zr / 4 * 100:+.0f}</text>')
    for v in range(int(math.ceil(lo / 2)) * 2, int(hi) + 1, 2):
        out.append(f'<text x="{px(v):.1f}" y="{H - B + 16}" fill="#8a94a3" text-anchor="middle">{abs(v)}</text>')
    out.append(poly(zs, "#8d8d8d", 1, ' stroke-dasharray="4 3"'))
    out.append(poly(zi, "#3e9dff", 2))
    out.append(poly(street_line(u, z0, off, zb, zs, lift, 0.0), "#ff9e31", 1.5, ' stroke-dasharray="6 4"'))
    out.append(poly(street_line(u, z0, off, zb, zs, lift, w), "#ff4d4d", 1.5))
    for k, (uc, zc) in enumerate(tracks):
        name = "our track" if k == 0 else "the opposite track"
        out.append(f'<line x1="{px(uc):.1f}" x2="{px(uc):.1f}" y1="{T}" y2="{H - B}" stroke="#555" stroke-dasharray="3 3"/>'
                   f'<text x="{px(uc):.1f}" y="{T - 6}" fill="#cfd6df" text-anchor="middle">{name}</text>')
        for col, dz in (("#ff9e31", 0.0), ("#ff4d4d", c / 2)):
            a, b = (uc + 0.75, zc - dz), (uc - 0.75, zc + dz)  # (left rail, right rail)
            out.append(f'<line x1="{px(a[0]):.1f}" y1="{py(a[1]):.1f}" x2="{px(b[0]):.1f}" y2="{py(b[1]):.1f}" stroke="{col}" stroke-width="2"/>'
                       + "".join(f'<circle cx="{px(q[0]):.1f}" cy="{py(q[1]):.1f}" r="3.5" fill="{col}"/>' for q in (a, b)))
    out.append(f'<text x="{L}" y="{H - B + 32}" fill="#cfd6df">'
               f'<tspan fill="#3e9dff">— lidar</tspan>  <tspan fill="#8d8d8d">- - survey (raw)</tspan>  '
               f'<tspan fill="#ff9e31">●- - main: rails and street</tspan>  '
               f'<tspan fill="#ff4d4d">●— now: rails ({abs(c) * 1000:.0f} mm) and street</tspan></text>'
               f'<text x="{L}" y="{H - 6}" fill="#8a94a3">line {line}, s {s:.0f}, seen along the line: m left | right, '
               f'cm from our rail top (×{ex:.0f})</text></svg>')
    return "".join(out)


def cards(lines):
    """reports/review/cross-level-N.json: a card for each stretch of CARD_MM or more, not yet answered, with a
    cross-section picture (reports/review/cross-level/)."""
    from geo import Frame
    from ipr_dtm import IprDtm
    F = Frame()
    ipr = IprDtm()
    pics = ROOT / "reports" / "review" / "cross-level"
    pics.mkdir(parents=True, exist_ok=True)
    for old in pics.glob("*.svg"):
        old.unlink()
    truth = json.loads((ROOT / "data" / "truth.json").read_text(encoding="utf-8"))
    # (a place answered, or a fact from the user, by its two points: its card is not asked again)
    done = [[F.xy(*ll) for ll in a["between"]] for a in (truth.get("crossLevelReview") or {}).get("answers", [])]
    per = {}
    for line in lines:
        data = json.loads((ROOT / "data" / f"line{line}.json").read_text(encoding="utf-8"))
        rt = Route(data["path"])
        H, CL = data["heights"], data["crossLevel"]
        big = [q for q in CL["places"] if abs(q["mm"]) >= CARD_MM]
        dtm_p = ROOT / "data" / f"line{line}.dtm.json"
        tris = survey_tris(json.loads(dtm_p.read_text(encoding="utf-8"))["areas"], [(q["x"], q["y"]) for q in big]) \
            if big and dtm_p.exists() else np.zeros((0, 3, 3))
        out = []
        for q in big:
            a, b = rt.at(q["s"])[:2], rt.at(q["s"] + q["length"])[:2]
            # (the section at the stretch's largest value)
            k = min(range(int(q["s"] / STEP), int((q["s"] + q["length"]) / STEP) + 1),
                    key=lambda i: math.hypot(rt.at(i * STEP)[0] - q["x"], rt.at(i * STEP)[1] - q["y"]))
            pt = rt.at(k * STEP)
            val = lambda arr, k=k: np.nan if k >= len(arr) or arr[k] is None else float(arr[k])  # noqa: E731
            pic = f"{line}-{q['s']}.svg"
            o_k, zb_k, c_k = val(H.get("backOff") or []), val(H.get("backZ") or []), val(CL["path"]) * CL["unit"]
            slope = abs((zb_k - val(H["path"])) / o_k) if np.isfinite(o_k) and abs(o_k) > 0.5 else 0.0
            w_k = min(1.0, abs(c_k) / (slope * GAUGE)) if slope > 1e-4 else 0.0
            lv = data["lift"]["v"]
            lift_k = lv[min(int(round(k * STEP / data["lift"]["step"])), len(lv) - 1)] * data["lift"]["unit"]
            (pics / pic).write_text(section_svg(line, k * STEP, pt[:2], pt[2:], val(H["path"]), val(H.get("backOff") or []),
                                                val(H.get("backZ") or []), val(CL["path"]) * CL["unit"],
                                                lambda x, y: ipr.sample(x + F.E0, y + F.N0), tris, lift_k, w_k),
                                    encoding="utf-8", newline="\n")
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
                        f"here in reality?"
                        f'<a href="reports/review/cross-level/{pic}" target="_blank" rel="noopener">'
                        f'<img src="reports/review/cross-level/{pic}" alt="the cross-section" '
                        f'style="display:block;width:100%;margin:6px 0"></a>'})
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
