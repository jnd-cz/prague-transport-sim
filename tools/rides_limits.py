"""The game's speed limits against the GPS rides in raw/reference/rides/ (#451).

    python -P -E tools/rides_limits.py                      # every ride in RIDES on line 23
    python -P -E tools/rides_limits.py --lines 37            # T3M 8088 on line 37 (#500)
    python -P -E tools/rides_limits.py --lines 22,23 --json reports/rides_limits.json

It starts its own server on a free port (as tools/headless.py), loads each line and reads the limit the tram's front
has at every metre (`game.limits` over the tram's length, as Game.currentLimit), with the curve's, the posted and the
restriction's. Each ride is mapped onto the line's track where it runs the line's way (GPS within MAX_OFF of the
track, moving along it). Listed: every place the ride went more than OVER km/h faster than our limit for MIN_RUN m or
more, with what sets the limit there; and per stretch between stops the ride's top speed, ours, and a quickest run
(RUN_A up, RUN_B down, standing at every stop) at our limits and at our limits raised to where the ride went faster.
A ride's phone rides somewhere in the car and its fixes stray a few metres in the streets, so the ride's speed at a
metre is its fastest within SMEAR m and our limit there the highest within NEAR m.
"""
import argparse
import datetime as dt
import faulthandler
import json
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RIDES_DIR = os.path.join(ROOT, "raw", "reference", "rides")
# the rides in a line's direction (raw/reference/SOURCES.md); the others run the opposite way or on a diversion
RIDES = [("6312, 2026-10-31", "20261031-172412_-_Kr_lovka_b_l__labu__23_6312.gpx"),
         ("6921, 2026-11-08", "20261108-183144_-_T3_6921_to_Strossmayerovo_T3M_to_Bulovka_52T_to_Palmovka_T3R_PLF_to_str__n_.gpx"),
         ("8088, 2026-11-11", "20261111-081934_-_T3M_8088_2nd_car_Strazni_-_Palmovka.gpx"),  # (line 37: T3M, the second car, #500)
         ("8088, 2026-11-12", "20261112-081938_-_T3M_8088_Strazni_-_Palmovka_linka_37.gpx")]  # (line 37: the second car's end, #500)
MAX_OFF = 8      # m from the track for a fix to count
SMEAR = 5        # m: the ride's speed at a metre is its fastest fix within this
NEAR = 10        # m: our limit at a metre is the highest within this (the phone rides behind the front)
OVER, MIN_RUN = 3, 10   # km/h over our limit, for at least this many m
RUN_A, RUN_B = 0.9, 0.8  # m/s²: the quickest run's start and braking
CURVE_AHEAD = 5          # m, as src/route.js

DUMP = """() => {
  const g = window.game, r = g.route, L = Math.floor(r.length), len = g.tram.length;
  const raw = [], eff = [], curve = [], osm = [], restr = [], xy = [];
  for (let m = 0; m <= L; m++) {
    raw.push(g.limits.at(m)); curve.push(r.curveSpeed(m)); osm.push(r._speedInfo(m).osm || 0); restr.push(g.limits.restriction(m));
    if (m % 2 === 0) { const p = r.at(m); xy.push([+p.x.toFixed(2), +p.y.toFixed(2)]); }
  }
  for (let m = 0; m <= L; m++) { let v = 99; for (let s = m - len; s <= m + 0.1; s += 1) v = Math.min(v, g.limits.at(s)); eff.push(v); }
  return { L, len, past: g.opts.speedFacts.past, raw, eff, curve, osm, restr, xy, stops: g.stops.map((s) => ({ name: s.name, s: s.target })) };
}"""
FIX = re.compile(r'<trkpt lat="([\d.]+)" lon="([\d.]+)">(?:<ele>[^<]*</ele>)?<time>([^<]+)</time>(?:<speed>([\d.\-]+)</speed>)?')


def read_gpx(path):
    """(t s from the first fix, lat, lon, km/h) of a GPX track whose fixes carry a speed in m/s."""
    with open(path, encoding="utf-8") as f:
        rows = FIX.findall(f.read())
    t0 = dt.datetime.fromisoformat(rows[0][2].replace("Z", "+00:00"))
    t = np.array([(dt.datetime.fromisoformat(r[2].replace("Z", "+00:00")) - t0).total_seconds() for r in rows])
    return t, np.array([float(r[0]) for r in rows]), np.array([float(r[1]) for r in rows]), np.array([float(r[3] or 0) for r in rows]) * 3.6


def project(P, x, y):
    """s along the polyline P (2 m apart) and the distance of each fix, the motion along the track's way only."""
    a, b = P[:-1], P[1:]
    ab = b - a
    n2 = np.maximum(1e-9, (ab ** 2).sum(1))
    hx, hy = np.gradient(x), np.gradient(y)
    s, d = np.full(len(x), np.nan), np.full(len(x), np.inf)
    for k in range(len(x)):
        t = np.clip(((x[k] - a[:, 0]) * ab[:, 0] + (y[k] - a[:, 1]) * ab[:, 1]) / n2, 0, 1)
        q = a + ab * t[:, None]
        dd = np.hypot(q[:, 0] - x[k], q[:, 1] - y[k])
        if np.hypot(hx[k], hy[k]) > 1.0:
            dd = np.where(ab[:, 0] * hx[k] + ab[:, 1] * hy[k] > 0, dd, np.inf)
        i = int(dd.argmin())
        s[k], d[k] = 2.0 * (i + t[i]), dd[i]
    return s, d


def ride_speed(s, kmh, length):
    """The ride's speed at each metre (its fastest fix within SMEAR m; NaN where none), over the part it ran forward."""
    real = np.full(length + 1, np.nan)
    last = None
    for sv, v in zip(s, kmh):
        if last is not None and sv < last - 30:
            continue  # (a jump back: the end of this pass)
        last = sv
        a0, a1 = max(0, int(sv - SMEAR)), min(length, int(sv + SMEAR))
        seg = real[a0:a1 + 1]
        real[a0:a1 + 1] = np.where(np.isnan(seg), v, np.maximum(seg, v))
    return real


def quickest(cap, s0, s1):
    """Seconds from standing at s0 to standing at s1 under cap (m/s at each metre)."""
    c = np.asarray(cap[s0:s1 + 1], dtype=float)
    v = np.zeros(len(c))
    for i in range(1, len(c)):
        v[i] = min(c[i], (v[i - 1] ** 2 + 2 * RUN_A) ** 0.5)
    v[-1] = 0
    for i in range(len(c) - 2, -1, -1):
        v[i] = min(v[i], (v[i + 1] ** 2 + 2 * RUN_B) ** 0.5)
    v[0] = 0
    return float((1.0 / np.maximum(0.05, (v[1:] + v[:-1]) / 2)).sum())


def cause(lim, m):
    """What sets the front's limit at m: the metre under the tram with the lowest limit, and its rule."""
    raw = lim["raw"]
    lo = max(0, int(m - lim["len"]))
    j = lo + int(np.argmin(raw[lo:m + 1]))
    if lim["restr"][j] <= raw[j]:
        return "restriction", j
    w0, w1 = max(0, j - lim["past"]), min(lim["L"], j + CURVE_AHEAD)
    k = w0 + int(np.argmin(lim["curve"][w0:w1 + 1]))
    if lim["osm"][k] and lim["curve"][k] >= lim["osm"][k]:
        return "posted", k
    return "curve", k


def compare(lim, real):
    """Places the ride went faster than our limit, and the stretches between stops it covers."""
    L, eff = lim["L"], np.asarray(lim["eff"], dtype=float)
    near = np.array([eff[max(0, m - NEAR):m + NEAR + 1].max() for m in range(L + 1)])
    covered = ~np.isnan(real)
    over = covered & (real > near + OVER)
    places, m = [], 0
    while m <= L:
        if not over[m]:
            m += 1
            continue
        e = m
        while e + 1 <= L and over[e + 1]:
            e += 1
        if e - m + 1 >= MIN_RUN:
            worst = m + int(np.nanargmax(real[m:e + 1] - near[m:e + 1]))
            why, at = cause(lim, worst)
            st = min(lim["stops"], key=lambda q: abs(q["s"] - worst))
            places.append({"from": m, "to": e, "limit": float(eff[worst]), "real": round(float(real[worst]), 1), "cause": why, "causeAt": at,
                           "curve": float(lim["curve"][at]), "posted": float(lim["osm"][at]), "near": st["name"], "fromStop": round(worst - st["s"])})
        m = e + 1
    raised = np.where(covered, np.maximum(eff, np.nan_to_num(real, nan=0)), eff)
    stretches = []
    for a, b in zip(lim["stops"][:-1], lim["stops"][1:]):
        s0, s1 = int(a["s"]), int(b["s"])
        if s1 <= s0 or covered[s0:s1 + 1].mean() < 0.9:
            continue
        stretches.append({"to": b["name"], "m": s1 - s0, "realTop": round(float(np.nanmax(real[s0:s1 + 1])), 1), "ourTop": float(eff[s0:s1 + 1].max()),
                          "quickOurs": round(quickest(eff / 3.6, s0, s1)), "quickRaised": round(quickest(raised / 3.6, s0, s1)),
                          "overM": int(over[s0:s1 + 1].sum())})
    return places, stretches


def dump_limits(lines):
    from playwright.sync_api import sync_playwright
    import headless
    server, url = headless.serve(0)
    out = {}
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            for line in lines:
                page = b.new_page()
                page.add_init_script("window.headlessDraw = false")
                page.goto(f"{url}/index.html?line={line}&keepgeo", timeout=120_000)
                page.wait_for_function(f"() => document.getElementById('loading')?.classList.contains('hidden') && document.title.includes('{line}')",
                                       timeout=300_000, polling=1000)
                page.evaluate("document.getElementById('btnStart').click()")
                page.wait_for_function("() => !!window.game && !!window.game.limits", timeout=60_000, polling=500)
                out[line] = page.evaluate(DUMP)
                page.close()
            b.close()
    finally:
        server.terminate()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="23")
    ap.add_argument("--json", help="also write the places and stretches here")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    faulthandler.dump_traceback_later(1200, exit=True)
    missing = [f for _, f in RIDES if not os.path.exists(os.path.join(RIDES_DIR, f))]
    if missing:
        raise SystemExit(f"rides missing in {RIDES_DIR}: python -I tools/snapshot.py fetch ({len(missing)} files)")
    lines = a.lines.split(",")
    limits = dump_limits(lines)
    frame, report = geo.Frame.of_line(), {}
    for line in lines:
        lim = limits[line]
        P = np.array(lim["xy"], dtype=float)
        for name, f in RIDES:
            t, lat, lon, kmh = read_gpx(os.path.join(RIDES_DIR, f))
            x, y = frame.xy(lat, lon)
            s, d = project(P, x, y)
            ok = d < MAX_OFF
            if ok.sum() < 100:
                print(f"line {line}, {name}: {int(ok.sum())} fixes on the track the line's way, skipped")
                continue
            real = ride_speed(s[ok], kmh[ok], lim["L"])
            places, stretches = compare(lim, real)
            report[f"{line} {name}"] = {"places": places, "stretches": stretches}
            q0, q1 = sum(x["quickOurs"] for x in stretches), sum(x["quickRaised"] for x in stretches)
            print(f"\nline {line}, ride {name}: {len(stretches)} stretches, {sum(x['m'] for x in stretches)} m; quickest run at our limits {q0} s, "
                  f"raised to the ride {q1} s ({q0 - q1} s)")
            print("  to | m | ride's top | ours | quickest ours | raised | m over")
            for x in stretches:
                print(f"  {x['to']} | {x['m']} | {x['realTop']} | {x['ourTop']:.0f} | {x['quickOurs']} | {x['quickRaised']} | {x['overM']}")
            print(f"  faster than our limit by {OVER} km/h for {MIN_RUN} m or more: {len(places)}")
            for p in places:
                print(f"    s {p['from']}-{p['to']}, {p['fromStop']:+d} m from {p['near']}: ours {p['limit']:.0f}, the ride {p['real']}; {p['cause']} at {p['causeAt']} "
                      f"(curve {p['curve']:.0f}, posted {p['posted']:.0f})")
    if a.json:
        json.dump(report, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
