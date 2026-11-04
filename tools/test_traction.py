"""The T3's traction and brakes (#221, src/tr37.js through src/tram.js), without the game:
python -P -E tools/test_traction.py
(its own server on a free port; a blank page imports the two modules). An empty car on the level:
- a start on each drive step: the acceleration over 3 s once the current is up, against [rubook]'s 0.6 / 0.95 / 1.2 /
  1.5 / 1.8 m/s² (within 10 %), and the end of the resistors (accelerator position 75) at 26–37 km/h
  ([calc] t3-accelerator.md § 5.3, the forum's 30–35 km/h);
- the top speed on the last step: ≈80 km/h by the motor chart (65 km/h is the legal limit, the user, #221,
  2026-11-04: "The 65 km/h is only a legal limit, reaching top 80 km/h is fine.");
- coasting: no more than 0.14 m/s² from the preparation current ([rubook]);
- brake step 5 from 40 km/h after 3 s coasting: ≈1.2–1.5 m/s² ([ckd26] p. 5), the shoe brakes take over
  near 4 km/h and the car stops; straight from drive to step 5: the shoe brakes come in at speed (LO);
- parked: the car holds on 80 ‰; an open door or the brake pedal off zero: no traction."""
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUN = """async () => {
  const { Tram } = await import('/src/tram.js');
  const { TR37_SPEC: S } = await import('/src/tr37.js');
  const dt = 0.02, out = {};
  const fresh = () => { const t = new Tram(1); t.eq.mode = 'advanced'; t.eq.park(false); return t; };
  const run = (t, sec, o = {}, each = null) => { for (let i = 0; i < sec / dt; i++) { t.update(dt, o); if (each && each(t) === false) break; } };
  // starts on each step
  out.steps = [];
  for (let k = 1; k <= 5; k++) {
    const t = fresh(); t.eq.setStep(k);
    // (measured once the current is up: the accelerator first has to reach it, 0.3–2.3 s, § 8.4)
    let tA = null, vA = 0, a = null, endRes = null, T = 0;
    run(t, 120, {}, (x) => {
      T += dt;
      if (tA === null && x.current >= 0.95 * S.driveCurrent[k - 1]) { tA = T; vA = x.v; }
      if (tA !== null && a === null && (x.eq.p >= 75 || T - tA >= 3)) a = (x.v - vA) / (T - tA);
      if (endRes === null && x.eq.p >= 75) endRes = x.kmh;
      return !(a !== null && endRes !== null);
    });
    out.steps.push({ step: k, a: a && +a.toFixed(3), endRes: endRes && +endRes.toFixed(1), upS: tA && +tA.toFixed(2) });
  }
  // top speed
  { const t = fresh(); t.eq.setStep(5); run(t, 240); out.top = +t.kmh.toFixed(1); out.topP = Math.round(t.eq.p); }
  // coasting from 40 km/h
  { const t = fresh(); t.eq.setStep(3); run(t, 120, {}, (x) => x.kmh < 40); t.eq.setStep(0); run(t, 3); const v0 = t.v; run(t, 5); out.coast = +((v0 - t.v) / 5).toFixed(3); out.coastI = Math.round(t.current); }
  // brake step 5 after coasting: deceleration 40 → 10 km/h, then the stop
  {
    const t = fresh(); t.eq.setStep(3); run(t, 120, {}, (x) => x.kmh < 40); t.eq.setStep(0); run(t, 3);
    t.eq.setStep(-5); let T = 0, t10 = null, shoeAt = null; const v0 = t.v;
    run(t, 60, {}, (x) => { T += dt; if (t10 === null && x.kmh <= 10) t10 = T; if (shoeAt === null && x.eq.shoe === 2) shoeAt = x.kmh; return x.v > 0; });
    out.brake5 = +((v0 - 10 / 3.6) / t10).toFixed(3); out.shoeAtKmh = shoeAt && +shoeAt.toFixed(1); out.stopped = t.v === 0;
  }
  // straight from drive to brake step 5: LO drops, the shoes at speed
  { const t = fresh(); t.eq.setStep(3); run(t, 120, {}, (x) => x.kmh < 40); t.eq.setStep(-5); let shoeAt = null; run(t, 3, {}, (x) => { if (shoeAt === null && x.eq.shoe === 2) shoeAt = x.kmh; }); out.fastShoeKmh = shoeAt && +shoeAt.toFixed(1); }
  // parked on 80 ‰, doors, brake pedal
  { const t = new Tram(1); t.eq.mode = 'advanced'; run(t, 10, { grade: 0.08 }); out.parkedV = +t.v.toFixed(3); }
  { const t = fresh(); t.eq.setStep(3); run(t, 3, { doorsOpen: true }); out.doorsV = +t.v.toFixed(3); }
  { const t = fresh(); t.eq.pedal.drive = 22; t.eq.pedal.brake = 2.5; run(t, 3); out.bothV = +t.v.toFixed(3); }
  return out;
}"""


def main():
    faulthandler.dump_traceback_later(300, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/README.md")
            r = page.evaluate(RUN)
            browser.close()
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    print(json.dumps(r))
    fails = []
    for s, want in zip(r["steps"], [0.6, 0.95, 1.2, 1.5, 1.8]):
        if abs(s["a"] - want) > 0.1 * want:
            fails.append(f"step {s['step']}: {s['a']} m/s², want {want} ±10 %")
        if not s["endRes"] or not 23 <= s["endRes"] <= 40:
            fails.append(f"step {s['step']}: end of the resistors at {s['endRes']} km/h, want 23–40")
    # (65 km/h is the legal limit, not the balance: the user, #221, 2026-11-04)
    if not 72 <= r["top"] <= 88:
        fails.append(f"top speed {r['top']} km/h, want ≈80 (the motor chart)")
    if not 0 < r["coast"] <= 0.14:
        fails.append(f"coasting {r['coast']} m/s², want 0–0.14")
    if not 1.1 <= r["brake5"] <= 1.6:
        fails.append(f"brake step 5: {r['brake5']} m/s², want 1.1–1.6")
    if not r["stopped"] or not r["shoeAtKmh"] or not 2.5 <= r["shoeAtKmh"] <= 5.5:
        fails.append(f"stop on step 5: shoes at {r['shoeAtKmh']} km/h, stopped {r['stopped']} (want ≈4 km/h, stopped)")
    if not r["fastShoeKmh"] or r["fastShoeKmh"] < 20:
        fails.append(f"drive straight to brake 5: shoes at {r['fastShoeKmh']} km/h, want at speed (LO dropped)")
    if r["parkedV"] != 0 or r["doorsV"] != 0 or r["bothV"] != 0:
        fails.append(f"held / interlocks: parked on 80 ‰ {r['parkedV']}, doors open {r['doorsV']}, both pedals {r['bothV']} m/s (want 0)")
    if errors:
        fails.append(f"page errors: {errors[:3]}")
    if fails:
        sys.exit("; ".join(fails))
    print("traction: five starts, top speed, coasting, brake step 5 and the stop, LO at speed, holds and interlocks: pass")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    main()
