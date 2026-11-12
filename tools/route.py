"""The route as the game drives it, built offline (#276 step 2): the track past both termini (#477), and `Route`, the
route as the page builds it, for what the build derives from it (tools/cant.py, #478).

    python -I tools/route.py 17      # the run past line 17's termini from its data/line17.json (a check; the build writes it)

The GTFS path starts and ends at the terminus stops, but a two-car set standing there reaches 30 m further back. The
run walks the drawn track chains (the line data's `tracks`) from each end for RUN metres, across chain joints in the
most aligned direction, and goes straight on where no track continues. tools/build_line.py writes it as `pathExt`;
the game builds its route from the path and `pathExt` (src/route.js Route) and walks no tracks.
"""
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
RUN = 60.0     # m past each end: a two-car set at the first stop stands on rails, its back 30 m behind the stop
SNAP = 1.5     # m: a chain this near the walk's point carries it on
ALIGN = 0.6    # the chain's segment within this cosine of the walk's heading (53°)
HOPS = 20      # chains walked at most from each end
TOUCH = 0.05   # m: a chain point this near the walk's point is where it already is


def _walk(tracks, p, hx, hy, length):
    """Points from p along the chains in direction (hx, hy) for `length` m: the walk of src/route.js until #477."""
    out = []
    cur = (p[0], p[1])
    left = length
    for _ in range(HOPS):
        if left <= 0:
            break
        best = None
        for q in tracks:
            for i in range(len(q) - 1):
                ax, ay, bx, by = q[i][0], q[i][1], q[i + 1][0], q[i + 1][1]
                sx, sy = bx - ax, by - ay
                l2 = sx * sx + sy * sy
                if not l2:
                    continue
                u = max(0.0, min(1.0, ((cur[0] - ax) * sx + (cur[1] - ay) * sy) / l2))
                d = math.hypot(ax + sx * u - cur[0], ay + sy * u - cur[1])
                if d > SNAP:
                    continue
                dot = (sx * hx + sy * hy) / math.sqrt(l2)
                if abs(dot) < ALIGN:
                    continue
                score = d - abs(dot)  # the nearest and best aligned; on a tie the first found
                if best is None or score < best[0]:
                    best = (score, q, i, dot > 0)
        if best is None:
            break
        _, q, i, fwd = best
        seq = q[i + 1:] if fwd else q[i::-1]
        moved = False
        for n in seq:
            ln = math.hypot(n[0] - cur[0], n[1] - cur[1])
            if ln < TOUCH:
                continue
            if ln >= left:
                cur = (cur[0] + (n[0] - cur[0]) * left / ln, cur[1] + (n[1] - cur[1]) * left / ln)
                out.append(cur)
                left = 0
                moved = True
                break
            hx, hy = (n[0] - cur[0]) / ln, (n[1] - cur[1]) / ln
            cur = (n[0], n[1])
            out.append(cur)
            left -= ln
            moved = True
        if not moved:
            break
    if left > 0:  # no track: straight on
        out.append((cur[0] + hx * left, cur[1] + hy * left))
    return out


def extend(tracks, pts, length=RUN):
    """{before, after}: the run past the path's first and last point, `before` ordered towards the path's start.
    `tracks`: the chains' point lists; `pts`: the path."""
    tracks = [[(q[0], q[1]) for q in t] for t in tracks]
    n = len(pts)
    h0 = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
    l0 = math.hypot(*h0) or 1
    h1 = (pts[n - 1][0] - pts[n - 2][0], pts[n - 1][1] - pts[n - 2][1])
    l1 = math.hypot(*h1) or 1
    before = _walk(tracks, pts[0], h0[0] / l0, h0[1] / l0, length)[::-1]
    after = _walk(tracks, pts[n - 1], h1[0] / l1, h1[1] / l1, length)
    return {"before": before, "after": after}


def path_ext(data, xy=3):
    """The line data's `pathExt`: the run past both termini, rounded as the build rounds coordinates."""
    ext = extend([t["p"] for t in data["tracks"]], data["path"])
    return {k: [[round(x, xy), round(y, xy)] for x, y in v] for k, v in ext.items()}


class Route:
    """The route as src/route.js Route builds it (#477): the build's points as they are, s along them from the path's
    start (negative over the run-in), `at` on their segments, `heading` the chord between two points around s. The same
    arithmetic in the same order, so what the build derives from it is what the page derived."""

    def __init__(self, pts, ext=None):
        before, after = (ext or {}).get("before", []), (ext or {}).get("after", [])
        allp = [(p[0], p[1]) for p in [*before, *pts, *after]]
        cum = [0.0]
        for a, b in zip(allp, allp[1:]):
            cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        s0 = cum[len(before)]
        L = 0.0
        for a, b in zip(pts, pts[1:]):
            L += math.hypot(b[0] - a[0], b[1] - a[1])
        self.p, self.s, self.length = allp, [c - s0 for c in cum], L

    def _index(self, s):
        lo, hi = 0, len(self.s) - 1
        if s <= self.s[0]:
            return 0
        if s >= self.s[hi]:
            return hi - 1
        while hi - lo > 1:
            mid = (lo + hi) >> 1
            if self.s[mid] <= s:
                lo = mid
            else:
                hi = mid
        return lo

    def at(self, s):
        """(x, y, hx, hy) at s."""
        i = self._index(s)
        a, b = self.p[i], self.p[i + 1]
        seg = self.s[i + 1] - self.s[i] or 1e-9
        t = max(0.0, min(1.0, (s - self.s[i]) / seg))
        dl = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
        return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, (b[0] - a[0]) / dl, (b[1] - a[1]) / dl

    def heading(self, s, span=6.0):
        a, b = self.at(s - span), self.at(s + span)
        dx, dy = b[0] - a[0], b[1] - a[1]
        l = math.hypot(dx, dy) or 1
        return dx / l, dy / l

    def turn(self, s):
        """The signed heading change over 16 m around s (+ = left), as src/route.js reads a curve."""
        a, b = self.heading(s - 8, 4), self.heading(s + 8, 4)
        return math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = json.loads((ROOT / "data" / f"line{sys.argv[1]}.json").read_text(encoding="utf-8"))
    ext = path_ext(data)
    for k, v in ext.items():
        L = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(v, v[1:]))
        end = data["path"][0] if k == "before" else data["path"][-1]
        tie = v[-1] if k == "before" else v[0]
        print(f"{k}: {len(v)} points, {L + math.hypot(tie[0] - end[0], tie[1] - end[1]):.2f} m")


if __name__ == "__main__":
    main()
