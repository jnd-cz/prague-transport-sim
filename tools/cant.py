# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cant and the curve radius of a line's route, built offline (#276 step 2, #478).

    python -I tools/cant.py --line 17      # writes `cant` and `curvature` into data/line17.json

The page used to work both out at every load (src/route.js `prepareCant`, `_radius`); it now reads them.

- The radius at s is the heading change over 16 m (the chords 4 m either side of s - 8 and s + 8). `curvature` holds
  it for our route (`path`, with the run past the termini) and the opposite one (`pathBack`) at every metre from 0 to
  the route's length, as K / r rounded (K = 1e9) (0 where the heading turns under 1e-4 rad: the page's 1e6 m).
- The cant, every 2 m, signed (+ = the left rail lower): only on dedicated track (the line data's `speed.dedicated`),
  level within 150 m of the route's ends and 25 m around each platform (`p0`-`p1`, else the 30 m behind the stop),
  60 % of the balanced cant at the speed the curve allows with full cant, at most CANT_MAX; ramps of at most CANT_MAX
  per 30 m, then smoothed over ±6 m. Written in 0.01 mm. The page's array was float32: so are the steps here.
"""
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing  # noqa: E402
from route import Route  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
A_LAT, CANT_MAX = 0.8, 0.1   # the cant's layout: m/s² unbalanced, m at most (src/route.js until #478)
STEP = 2                     # m between cant samples
LEVEL_ENDS, LEVEL_STOP = 150, 25
K = 1e9                      # curvature unit: 1e-9 per metre (1e-6 left the radius 0.07 % off near 1500 m and moved
                             # three 5 m limit bins 1 km/h on lines 17 and 23, where a whole km/h sat on the edge)


def f32(x):
    return struct.unpack("f", struct.pack("f", x))[0]


def radius(rt, s):
    """The page's `_radius`: unsigned turn over 16 m."""
    a, b = rt.heading(s - 8, 4), rt.heading(s + 8, 4)
    d = math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))
    return 16 / d if d > 1e-4 else 1e6


def curvature(rt):
    """K / radius at every metre 0..ceil(length), integers; 0 for the page's straight (1e6 m)."""
    out = []
    for m in range(math.ceil(rt.length) + 1):
        r = radius(rt, m)
        out.append(0 if r >= 1e6 else round(K / r))
    return out


def design_speed(osm, dedicated, r):
    """km/h a curve allows with full cant (src/route.js `_designSpeed(s, r, true)`)."""
    vd = math.floor((math.sqrt((A_LAT + (CANT_MAX if dedicated else 0) * 9.81 / 1.5) * r) * 3.6) / 5) * 5
    return max(10, min(min(60, osm or (60 if dedicated else 50)), vd))


def cant(rt, speed, stops):
    """Signed cant in metres every STEP m from 0 (src/route.js `prepareCant` until #478)."""
    n = math.ceil(rt.length / STEP) + 1
    c = [0.0] * n
    sp = speed or None

    def info(s):
        if not sp:
            return 0, False
        k = max(0, min(len(sp["osm"]) - 1, round(s / sp["step"])))   # (JS Math.round: halves up; s / step is whole or .4)
        return sp["osm"][k], bool(sp["dedicated"][k])
    for i in range(n):
        s = i * STEP
        osm, ded = info(s)
        if not ded or s < LEVEL_ENDS or s > rt.length - LEVEL_ENDS or any(st[0] - LEVEL_STOP < s < st[1] + LEVEL_STOP for st in stops):
            continue
        t = rt.turn(s)
        r = 16 / abs(t) if abs(t) > 1e-4 else 1e6
        if r > 1500:
            continue
        v = design_speed(osm, ded, r) / 3.6
        c[i] = f32(math.copysign(1, t) * min(CANT_MAX, 0.6 * 1.5 * v * v / (9.81 * r)))
    d = (CANT_MAX / 30) * STEP
    sign = lambda x: (x > 0) - (x < 0)  # noqa: E731
    for _ in range(2):
        for i in range(1, n):
            c[i] = f32(sign(c[i]) * min(abs(c[i]), abs(c[i - 1]) + d) * (1 if sign(c[i]) == sign(c[i - 1]) or not c[i - 1] else 0))
        for i in range(n - 2, -1, -1):
            c[i] = f32(sign(c[i]) * min(abs(c[i]), abs(c[i + 1]) + d) * (1 if sign(c[i]) == sign(c[i + 1]) or not c[i + 1] else 0))
    out = []
    for i in range(n):
        acc = w = 0.0
        for k in range(-3, 4):
            j = i + k
            if 0 <= j < n:
                ww = 4 - abs(k)
                acc += c[j] * ww
                w += ww
        out.append(f32(acc / w))
    return out


def build(data):
    rt = Route(data["path"], data.get("pathExt"))
    stops = [(st["p0"] if st.get("p0") is not None else st["s"] - 30, st["p1"] if st.get("p1") is not None else st["s"])
             for st in data["stops"]]
    c = cant(rt, data.get("speed"), stops)
    curv = {"path": curvature(rt)}
    if len(data.get("pathBack") or []) > 1:
        curv["pathBack"] = curvature(Route(data["pathBack"]))
    return {"step": STEP, "c": [round(v * 1e5) for v in c], "unit": 1e-5}, {"step": 1, "unit": 1 / K, **curv}


def main():
    if "--line" not in sys.argv:
        sys.exit(__doc__)
    line = sys.argv[sys.argv.index("--line") + 1]
    p = ROOT / "data" / f"line{line}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["cant"], data["curvature"] = build(data)
    with replacing(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    c = data["cant"]["c"]
    print(f"line {line}: cant on {sum(1 for v in c if v)} of {len(c)} samples, at most {max(map(abs, c)) / 100:.1f} mm; "
          f"curvature at {len(data['curvature']['path'])} metres" + (f" (+{len(data['curvature']['pathBack'])} opposite)" if "pathBack" in data["curvature"] else ""))


if __name__ == "__main__":
    main()
