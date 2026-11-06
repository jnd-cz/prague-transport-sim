"""Test drives of the T3's electric system (#351, #355, src/tr37.js, src/electric.js through src/tram.js), without the game:
python -P -E tools/test_electric.py [--report FILE]
(its own server on a free port; a blank page imports the modules through sync_playwright; --report saves the drives' time series).
Each drive is a situation with what the manuals say should happen (raw/reference/ckd-t3su/, notes in
docs/research/prazsketramvaje/t3-accelerator.md § 9):
- coast-down from 70 km/h: the accelerator follows the speed back at no more than its 20 positions/s, with no sweep at a
  constant speed, and ends at the bottom when the car stands (T3SU-24 § 4.2);
- coasting downhill: as the speed rises the position rises and the current stays small (§ 4.2);
- taking up drive after coasting at 10–50 km/h: the current reaches the setting within 1.5 s without a surge (T3SU-03 p. 5);
- braking at a held speed: each step's current (T3SU-26 p. 4), and a lower position on a higher step (T3SU-24 § 4.3);
- drive, 2.5 s coasting, step 5: the electric brake takes it and the shoes wait for ≈4 km/h; drive straight to step 5
  with the brake pedal slammed: LO drops, the shoes at speed (T3SU-03 p. 11);
- the stops: steps 1–2 fade out and roll on, step 3 brings the shoes in partly, step 5 fully (T3SU-24 § 5);
- a weak wire: the same force on the resistors, less above them, a lower top speed;
- the motor-generator: speed against voltage (T3SU-15), the tone falling on a start under a wire with resistance, 26 V held down
  to a low wire (T3SU-23), the battery with no wire and no traction without SN (T3SU-24 § 2.1);
- step 1's setting against the 24 V side (T3SU-26 p. 4), the pilot motor's rate, the track brakes on the battery;
- the wire: the nearest feed, its resistance with distance, another tram's share."""
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
  const { TR37_SPEC: S, loopCurrent, loopField } = await import('/src/tr37.js');
  const { Feeding, WIRE, MotorGenerator, aiLineCurrent } = await import('/src/electric.js');
  const dt = 0.02, out = {}, series = {};
  const fresh = (cars = 1) => { const t = new Tram(cars); t.eq.mode = 'advanced'; t.eq.park(false); t.update(dt, {}); return t; };
  const run = (t, sec, o = {}, each = null) => { for (let i = 0; i < sec / dt; i++) { t.update(dt, o); if (each && each(t) === false) break; } };
  const log = (name, t, T, extra = {}) => { (series[name] ||= []).push({ T: +T.toFixed(2), kmh: +t.kmh.toFixed(2), p: +t.eq.p.toFixed(2), A: Math.round(t.current), U: Math.round(t.voltage), rpm: Math.round(t.eq.mg.rpm), aux: +t.eq.aux.U.toFixed(2), a: +t.a.toFixed(3), step: t.notch, shoe: t.eq.shoe, ...extra }); };
  // to a speed on a step, then the pedal off
  const toSpeed = (t, kmh, step = 3) => { t.eq.setStep(step); run(t, 200, {}, (x) => x.kmh < kmh); t.eq.setStep(0); };
  // a held speed (a gradient that just balances it): the state after sec
  const held = (t, kmh, sec) => { t.v = kmh / 3.6; for (let i = 0; i < sec / dt; i++) { t.update(dt, {}); t.v = kmh / 3.6; } };

  // the coast-down
  {
    const t = fresh(); toSpeed(t, 70, 5);
    let T = 0, maxRate = 0, last = t.eq.p, lastKmh = t.kmh, sweep = 0; const at = {};
    run(t, 800, {}, (x) => {
      T += dt; log('coastDown', x, T);
      maxRate = Math.max(maxRate, Math.abs(x.eq.p - last) / dt); last = x.eq.p;
      if (T > 8) { const dKmh = Math.abs(lastKmh - x.kmh); sweep = Math.max(sweep, Math.abs(x.eq.p - (at._p ?? x.eq.p)) / Math.max(0.02, dKmh)); }
      if (Math.floor(x.kmh / 2) !== Math.floor(lastKmh / 2)) { lastKmh = x.kmh; at._p = x.eq.p; }
      const k = Math.round(x.kmh); if (k % 10 === 0 && !(k in at)) at[k] = +x.eq.p.toFixed(1);
      return x.v > 0;
    });
    series.coastDown = series.coastDown.filter((_, i) => i % 25 === 0);
    delete at._p;
    out.coast = { at, maxRate: +maxRate.toFixed(1), perKmh: +sweep.toFixed(1), standP: +t.eq.p.toFixed(1), secs: Math.round(T) };
  }
  // downhill, pedal off
  {
    const t = fresh(); toSpeed(t, 25, 2); run(t, 4); const p0 = t.eq.p, v0 = t.kmh; let top = 0, T = 0;
    run(t, 45, { grade: -0.04 }, (x) => { T += dt; if (Math.round(T / dt) % 25 === 0) log('downhill', x, T); top = Math.max(top, Math.abs(x.current)); });
    out.downhill = { v0: +v0.toFixed(1), p0: +p0.toFixed(1), v1: +t.kmh.toFixed(1), p1: +t.eq.p.toFixed(1), maxA: Math.round(top), A: Math.round(t.current) };
  }
  // drive taken up after settled coasting
  out.takeUp = [];
  for (const kmh of [10, 20, 30, 40, 50]) {
    const t = fresh(); held(t, kmh, 6);
    const pc = t.eq.p; t.eq.setStep(1); t.v = kmh / 3.6;
    const set = S.driveCurrent[0]; let peak = 0, inBand = null, T = 0;
    run(t, 4, {}, (x) => { T += dt; if (T > 0.4) peak = Math.max(peak, x.current); if (inBand === null && x.current > 0.9 * set) inBand = T; });
    out.takeUp.push({ kmh, coastP: +pc.toFixed(1), peak: Math.round(peak), inBand: inBand && +inBand.toFixed(2), mr: t.eq.mr });
  }
  // the brake steps at held speeds
  out.brakeSteps = {};
  for (const kmh of [15, 30, 45]) {
    out.brakeSteps[kmh] = [];
    for (let k = 1; k <= 5; k++) {
      const t = fresh(); held(t, kmh, 5); t.eq.setStep(-k); held(t, kmh, 6);
      out.brakeSteps[kmh].push({ step: k, A: Math.round(-t.current), p: +t.eq.p.toFixed(1), shoe: t.eq.shoe });
    }
  }
  // drive, coast 2.5 s, step 5
  {
    const t = fresh(); toSpeed(t, 40, 3); run(t, 2.5);
    t.eq.setStep(-5); let T = 0, a1 = 0, shoeAt = null;
    run(t, 60, {}, (x) => { T += dt; log('driveCoastBrake', x, T); if (T > 2 && T < 4) a1 = Math.max(a1, -x.a); if (shoeAt === null && x.eq.shoe === 2) shoeAt = x.kmh; return x.v > 0; });
    series.driveCoastBrake = series.driveCoastBrake.filter((_, i) => i % 10 === 0);
    out.coastThenBrake = { decel: +a1.toFixed(2), shoeAt: shoeAt && +shoeAt.toFixed(1), secs: +T.toFixed(1) };
  }
  // drive with the brake pedal slammed to the parking position
  {
    const t = fresh(); t.eq.setStep(3); run(t, 200, {}, (x) => x.kmh < 40);
    t.eq.pedal.drive = 0; t.eq.goal = null; t.eq.pedal.brake = S.parkAngle - 1;
    let shoeAt = null; run(t, 2, {}, (x) => { if (shoeAt === null && x.eq.shoe === 2) shoeAt = x.kmh; });
    out.slam = { shoeAt: shoeAt && +shoeAt.toFixed(1) };
  }
  // the stops from 30 km/h on each step
  out.stops = [];
  for (let k = 1; k <= 5; k++) {
    const t = fresh(); toSpeed(t, 30, 3); run(t, 3); t.eq.setStep(-k);
    let s0 = t.s, T = 0, firstShoe = null, shoeMax = 0;
    run(t, 80, {}, (x) => { T += dt; if (x.eq.shoe > 0 && firstShoe === null) firstShoe = x.kmh; shoeMax = Math.max(shoeMax, x.eq.shoe); return x.v > 0; });
    out.stops.push({ step: k, stopped: t.v === 0, m: Math.round(t.s - s0), secs: Math.round(T), kmhAtEnd: +t.kmh.toFixed(1), shoeAt: firstShoe && +firstShoe.toFixed(1), shoeMax });
  }
  // a weak wire against the nominal
  {
    const go = (u) => {
      const t = fresh(); t.supply = { u0: u, r: 0 }; run(t, 1);
      t.eq.setStep(5); let f15 = 0, T = 0, at20 = null, p20 = null, t50 = null;
      run(t, 180, {}, (x) => { T += dt; if (x.kmh > 15 && !f15) f15 = x.drive; if (x.kmh > 20 && at20 === null) { at20 = T; p20 = x.eq.p; } if (x.kmh > 50 && t50 === null) t50 = T; });
      return { u, f15: Math.round(f15), p20: +p20.toFixed(1), t50: t50 && +t50.toFixed(1), top: +t.kmh.toFixed(1) };
    };
    out.wire = [go(650), go(600), go(500), go(420)];
  }
  // the motor-generator at voltages, with a steady 24 V load
  out.mg = [];
  for (const u of [720, 650, 600, 550, 500, 450, 400]) {
    const t = fresh(); t.supply = { u0: u, r: 0 }; t.eq.setStep(0); run(t, 60);
    out.mg.push({ u, rpm: Math.round(t.eq.mg.rpm), A: +t.eq.mg.i.toFixed(1), aux: +t.eq.aux.U.toFixed(2), kW: +((u * t.eq.mg.i) / 1000).toFixed(1) });
  }
  // the tone on a start, two cars under a wire with resistance
  {
    const t = fresh(2); t.supply = { u0: 650, r: 0.13 }; t.eq.park(true); run(t, 30); const r0 = t.eq.mg.rpm, u0 = t.voltage;
    t.eq.park(false); let T = 0, rmin = r0, umin = u0; t.eq.setStep(4);
    run(t, 22, {}, (x) => { T += dt; if (Math.round(T / dt) % 10 === 0) log('startTone', x, T); rmin = Math.min(rmin, x.eq.mg.rpm); umin = Math.min(umin, x.voltage); });
    t.eq.setStep(0); run(t, 12, {}, (x) => { T += dt; if (Math.round(T / dt) % 10 === 0) log('startTone', x, T); });
    out.tone = { rpmStand: Math.round(r0), rpmMin: Math.round(rmin), uStand: Math.round(u0), uMin: Math.round(umin), semitones: +(12 * Math.log2(r0 / rmin)).toFixed(1), rpmAfter: Math.round(t.eq.mg.rpm) };
  }
  // the release magnets on the dynamo, on a stiff wire
  {
    const t = fresh(); t.eq.park(true); run(t, 30); const r0 = t.eq.mg.rpm, i0 = t.eq.aux.dynamoA;
    t.eq.park(false); t.eq.setStep(1); run(t, 12); out.magnets = { rpm0: Math.round(r0), rpm1: Math.round(t.eq.mg.rpm), dynamoA0: Math.round(i0), dynamoA1: Math.round(t.eq.aux.dynamoA) };
  }
  // no wire
  {
    const t = fresh(); t.supply = { u0: 0, r: 0 }; run(t, 40); t.eq.setStep(2); run(t, 2);
    out.dead = { rpm: Math.round(t.eq.mg.rpm), sn: t.eq.sn, ls: t.eq.ls, aux: +t.eq.aux.U.toFixed(1), v: +t.v.toFixed(2) };
  }
  // step 1's setting on the 24 V side
  { const t = fresh(); const q = (u) => { t.eq.aux.U = u; return Math.round(t.eq._setting(S.driveCurrent, 1) - S.driveCurrent[0]); }; out.rc = [26, 25, 24, 23].map(q); }
  // the pilot motor at the regulated 26 V: the fastest stretch of a step 5 start (the current still far off)
  {
    const t = fresh(); t.eq.setStep(5); let last = t.eq.p, top = 0;
    run(t, 2, {}, (x) => { top = Math.max(top, (x.eq.p - last) / dt); last = x.eq.p; });
    out.pilot = +top.toFixed(1);
  }
  // the track brakes on the 24 V side
  {
    const t = fresh(); t.eq.park(true); run(t, 2); t.eq.park(false); const a0 = t.eq.aux.U;
    t.eq.pedal.brake = S.pedalMax; t.eq.goal = null; run(t, 1); out.track = { before: +a0.toFixed(1), during: +t.eq.aux.U.toFixed(1), battery: Math.round(t.eq.aux.batteryA) };
  }
  // the wire, on a made-up straight line: substations at km 1 and km 5
  {
    const route = { nearest: (x, y) => ({ s: x, d: Math.abs(y) }) };
    const f = new Feeding(route, [{ ref: 'a', e: 1000, n: 0 }, { ref: 'b', e: 5000, n: 200 }, { ref: 'far', e: 2000, n: 9000 }], [0, 0]);
    const at = (s, o) => { const q = f.supply(s, o); return { ref: q.ref, r: +q.r.toFixed(3), u0: Math.round(q.u0) }; };
    out.feed = { n: f.feeds.length, at1000: at(1000), at1500: at(1500), at2500: at(2500), at4800: at(4800),
      sameSide: at(1500, [{ s: 1400, i: 500 }]), otherSide: at(1500, [{ s: 600, i: 500 }]), otherFeed: at(1500, [{ s: 4900, i: 500 }]) };
    const none = new Feeding(route, [], [0, 0]);
    out.feed.none = none.supply(100).u0;
    out.ai = { stand: Math.round(aiLineCurrent(2, 0, 0)), start: Math.round(aiLineCurrent(2, 2, 1)), cruise: Math.round(aiLineCurrent(2, 10, 0)) };
  }
  return { out, series };
}"""


def checks(o):
    fails = []

    def want(ok, msg):
        if not ok:
            fails.append(msg)

    c = o["coast"]
    want(c["maxRate"] <= 23, f"the accelerator moved at {c['maxRate']} positions/s, the pilot motor's most is ≈21.7 at 26 V")
    want(c["perKmh"] <= 9, f"coast-down: {c['perKmh']} positions per km/h after the first seconds: a sweep at nearly constant speed")
    want(c["standP"] <= 3.1, f"standing after coasting at position {c['standP']}, want the bottom (ZR8 at 3)")
    for kmh, lo, hi in ((10, 4, 25), (20, 18, 42), (30, 35, 62), (40, 52, 80)):
        p = c["at"].get(str(kmh))
        want(p is not None and lo <= p <= hi, f"coasting at {kmh} km/h at position {p}, want {lo}–{hi}")
    d = o["downhill"]
    want(d["v1"] > d["v0"] + 5 and d["p1"] > d["p0"] + 5, f"downhill the position should rise with the speed: {d}")
    want(d["maxA"] < 250, f"downhill coasting current {d['maxA']} A")
    for t in o["takeUp"]:
        want(not t["mr"] and t["peak"] < 400, f"take-up at {t['kmh']} km/h: peak {t['peak']} A, maximum relay {t['mr']}")
        want(t["inBand"] is not None and t["inBand"] < 1.5, f"take-up at {t['kmh']} km/h: at the setting after {t['inBand']} s")
    for kmh, rows in o["brakeSteps"].items():
        for r, set_a in zip(rows, (160, 211, 262, 306, 350)):
            want(abs(r["A"] - set_a) <= 0.1 * set_a, f"brake step {r['step']} at {kmh} km/h: {r['A']} A, want {set_a} ±10 %")
        want(all(rows[i]["p"] >= rows[i + 1]["p"] - 0.5 for i in range(4)) and rows[0]["p"] > rows[4]["p"] + 3,
             f"brake steps at {kmh} km/h should stand lower the higher the step: {[r['p'] for r in rows]}")
    b = o["coastThenBrake"]
    want(1.0 <= b["decel"] <= 1.6 and b["shoeAt"] is not None and b["shoeAt"] < 6, f"drive, coast 2.5 s, step 5: {b}")
    want(o["slam"]["shoeAt"] is not None and o["slam"]["shoeAt"] > 20, f"drive with the brake pedal slammed: shoes at {o['slam']['shoeAt']} km/h, want at speed")
    s = {r["step"]: r for r in o["stops"]}
    want(s[1]["secs"] > 25 and s[1]["shoeMax"] == 0, f"brake step 1 should fade out and roll on, with no shoes: {s[1]}")
    want(s[2]["shoeMax"] == 0, f"brake step 2 should not bring the shoes in: {s[2]}")
    want(s[3]["stopped"] and s[3]["shoeMax"] >= 1, f"brake step 3 should stop on the shoes: {s[3]}")
    want(s[5]["stopped"] and s[5]["shoeMax"] == 2 and s[5]["shoeAt"] < 7, f"brake step 5 should stop on the shoes from ≈4 km/h: {s[5]}")
    w = {r["u"]: r for r in o["wire"]}
    want(abs(w[420]["f15"] - w[600]["f15"]) < 0.05 * w[600]["f15"], f"on the resistors the force should not depend on the wire: {w[420]['f15']} and {w[600]['f15']} N")
    want(w[420]["p20"] > w[600]["p20"] + 3, f"a weak wire should stand higher at the same speed: {w[420]['p20']} against {w[600]['p20']}")
    want(w[420]["top"] < w[600]["top"] - 8 < w[650]["top"], f"top speed against the wire: {[(u, w[u]['top']) for u in w]}")
    m = {r["u"]: r for r in o["mg"]}
    want(m[720]["rpm"] < 2500, f"the motor-generator at 720 V: {m[720]['rpm']} rpm, its most is 2,500")
    want(1500 < m[600]["rpm"] < 2000, f"the motor-generator at 600 V: {m[600]['rpm']} rpm, rated 1,750")
    want(9 < m[600]["A"] < 16, f"the motor-generator at 600 V draws {m[600]['A']} A, rated 13")
    ratio = m[450]["rpm"] / m[600]["rpm"]
    want(0.72 <= ratio <= 0.92, f"a series motor on a fan runs between √U and U: {ratio:.2f} at 450 V")
    want(all(abs(m[u]["aux"] - 26) <= 0.5 for u in (720, 650, 600, 550, 500)), f"26 V should hold down to 500 V: {[(u, m[u]['aux']) for u in m]}")
    t = o["tone"]
    want(t["uMin"] < t["uStand"] - 80 and 0.8 <= t["semitones"] <= 7, f"the tone on a start: {t}")
    want(t["rpmAfter"] > t["rpmMin"] * 1.04, f"the tone should come back when the current goes: {t}")
    g = o["magnets"]
    want(g["dynamoA1"] > g["dynamoA0"] + 20 and g["rpm1"] < g["rpm0"], f"the shoes' release magnets on the dynamo: {g}")
    n = o["dead"]
    want(not n["sn"] and not n["ls"] and n["v"] == 0 and 17 < n["aux"] < 23, f"no wire: {n}")
    want(o["rc"] == [0, 10, 20, 30], f"step 1's setting on the 24 V side: {o['rc']}, want +0, 10, 20, 30 A (T3SU-26 p. 4)")
    want(17 <= o["pilot"] <= 23, f"the pilot motor at 26 V: {o['pilot']} positions/s")
    want(o["track"]["during"] < o["track"]["before"] and o["track"]["during"] > 15 and o["track"]["battery"] < 0, f"track brakes on the 24 V side: {o['track']}")
    f = o["feed"]
    want(f["n"] == 2, f"the far substation should not feed this line: {f['n']} feeds")
    want(f["at1000"]["ref"] == "a" and f["at4800"]["ref"] == "b" and f["at1000"]["r"] < f["at1500"]["r"] < f["at2500"]["r"], f"the feeds and their resistance: {f}")
    want(f["sameSide"]["u0"] < f["otherSide"]["u0"] < f["otherFeed"]["u0"], f"another tram on the wire: {f}")
    want(f["none"] == 600, f"no substation: {f['none']} V")
    return fails


def main():
    faulthandler.dump_traceback_later(420, exit=True)
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
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(r["out"], ensure_ascii=False))
    if "--report" in sys.argv:
        with open(sys.argv[sys.argv.index("--report") + 1], "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False)
    fails = checks(r["out"])
    if errors:
        fails.append(f"page errors: {errors[:3]}")
    if fails:
        sys.exit("\n".join(fails))
    print("electric test drives: pass")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    main()
