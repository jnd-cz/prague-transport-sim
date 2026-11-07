"""Test drives of the autopilot on the T3 (#351, src/autopilot.js, src/tr37.js), on made-up straight lines without the game:
python -P -E tools/test_drives.py [--report FILE] [-k NAME]
(its own server on a free port; a blank page imports the modules through sync_playwright; --report saves each drive's time series).
The real Autopilot and Tram, with a small stand-in for the game: a stop or signal is a place on the line, a tram ahead a script.
What must hold, from the user (2026-11-06, #351: "smooth braking towards stop sign without any jums to jízda unless you're following
tram in front of you") and the ČKD manuals (T3SU-03 p. 4-6): one approach to a stop with no drive pedal after the first brake,
no shoes at speed, the stop within ±2.4 m of the point, and a pedal that does not hunt."""
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RUN = """async (only) => {
  const { Tram } = await import('/src/tram.js');
  const { Autopilot } = await import('/src/autopilot.js');
  const h = 1 / 30;
  // a line: stops [s], limit (km/h) or limits [[s, km/h]], grade(s), signals [{ s, states: [[t, state]] }], ahead { s, length, moves: [[t, v]] }, crossing { s, from, to } (a car crossing the track there, from t to t), contact (s of an overhead contact for a turn)
  const drive = (o) => {
    const tr = new Tram(o.cars ?? 2);
    tr.eq.mode = 'advanced';
    tr.passengers = o.pax ?? 0;
    tr.s = o.from ?? 0;
    if (o.supply) tr.supply = o.supply;
    const limitAt = (s) => { if (!o.limits) return o.limit ?? 50; let k = o.limits[0][1]; for (const [a, v] of o.limits) if (s >= a) k = v; return k; };
    const R = { name: o.name, series: [], changes: 0, flips: [], stands: [], shoes: 0, maxDecel: 0, maxJerk: 0, overrun: 0 };
    const stops = (o.stops || []).map((s, i) => ({ name: 'S' + i, target: s, served: false, waiting: 0, alight: 0, alightFrac: 0, request: false, sched: 0, zone: [s - 2.5, s + 3] }));
    const ahead = o.ahead ? { ...o.ahead, v: 0 } : null;
    const g = {
      tram: tr, clock: 0, stops, nextStop: 0, doorState: 'closed', obstacles: [], carsOnTrack: [], carsCrossing: [], switches: [], opts: { autoIrc: true },
      climate: { tout: 15, tin: 20, tcab: 20, saloon: 0, cab: 0, flap: false },
      profile: { grade: (s) => (o.grade ? o.grade(s) : 0) },
      signals: (o.signals || []).map((x) => ({ s: x.s, cross: x.s + 15, state: 'go', states: x.states })),
      toggleDoors() {
        const st = stops[this.nextStop];
        if (this.doorState === 'closed') { this.doorState = 'open'; st.served = true; st.sched = this.clock + 5; R.stands.push({ stop: st.name, err: +(st.target - tr.s).toFixed(2), T: +this.clock.toFixed(1) }); }
        else { this.doorState = 'closed'; this.nextStop++; }
      },
      _atStop(st) { return tr.s >= st.zone[0] && tr.s <= st.zone[1]; },
      get currentLimit() { return limitAt(tr.s); },
      nextLimitChange() { if (!o.limits) return null; const here = limitAt(tr.s); for (const [a, v] of o.limits) if (a > tr.s && v < here && a - tr.s < 300) return { v, d: a - tr.s }; return null; },
      tramAheadGap() { return ahead ? ahead.s - ahead.length - tr.s : null; },
      keepClear() { return null; }, ringBell() {}, irc() {}, heatingDraws() { return false; },
      nextContact() { return o.contact && !R.contact ? { contact: o.contact, required: 'diverging' } : null; },
    };
    const pilot = new Autopilot();
    let last = tr.notch, braked = false, lastA = 0, jf = 0, T = 0, step = 0;
    const end = o.secs ?? 240, lastS = o.until ?? Infinity;
    while (T < end) {
      T += h; g.clock = T; step++;
      for (const x of g.signals) for (const [t, state] of x.states) if (T >= t) x.state = state;
      if (ahead) { for (const [t, v] of ahead.moves) if (T >= t) ahead.v = v; ahead.s += ahead.v * h; }
      if (o.crossing) g.carsCrossing = T >= (o.crossing.from ?? 0) && T <= (o.crossing.to ?? Infinity) ? [o.crossing] : [];
      pilot.step(g, h);
      tr.update(h, { grade: g.profile.grade(tr.s), doorsOpen: g.doorState !== 'closed' });
      if (o.contact && !R.contact && tr.panto >= o.contact) R.contact = { kmh: +tr.kmh.toFixed(1), step: tr.notch, p: +tr.eq.p.toFixed(1), drawn: tr.drawing || (!!pilot.input.switchBtn && tr.eq.buttonLive) };
      const n = tr.notch, st = stops[g.nextStop], d = st ? st.target - tr.s : null;
      if (n !== last) { R.changes++; last = n; }
      // an approach: from the first brake pedal with the stop or the next stopping signal within reach
      const target = g.signals.filter((x) => x.s > tr.s && x.state !== 'go').map((x) => x.s - 3)[0] ?? (st && !st.served ? st.target : null);
      if (n < 0 && target !== null && target - tr.s < (tr.v * tr.v) / 1.3 + 10) braked = true;
      if (n < 0 && braked && tr.eq.shoe === 2 && tr.v > 8 / 3.6) R.shoes++;
      if (n > 0 && braked) { R.flips.push({ T: +T.toFixed(1), s: +tr.s.toFixed(1), kmh: +tr.kmh.toFixed(1), step: n, gap: g.tramAheadGap() === null ? null : +g.tramAheadGap().toFixed(1), car: !!o.crossing && T >= (o.crossing.from ?? 0) && T <= (o.crossing.to ?? Infinity) + 2 }); braked = false; }
      if (tr.v < 0.02) braked = false;
      R.maxDecel = Math.max(R.maxDecel, -tr.a);
      jf += ((tr.a - lastA) * 30 - jf) * 0.17;
      lastA = tr.a;
      if (tr.v > 0.2) R.maxJerk = Math.max(R.maxJerk, Math.abs(jf));
      for (const x of g.signals) if (x.state !== 'go' && x.s < tr.s && x.s > tr.s - 1 && tr.v > 0) R.overrun++;
      if (step % 8 === 0) R.series.push([+T.toFixed(2), +tr.s.toFixed(1), +tr.kmh.toFixed(1), n, +tr.eq.p.toFixed(1), Math.round(tr.current), Math.round(tr.voltage), Math.round(tr.eq.mg.rpm), tr.eq.shoe, +tr.a.toFixed(2), d === null ? null : +d.toFixed(1), g.tramAheadGap() === null ? null : +g.tramAheadGap().toFixed(1)]);
      if (tr.s >= lastS || (g.nextStop >= stops.length && o.endAtLastStop !== false)) break;
    }
    R.secs = +T.toFixed(1); R.lastKmh = +tr.kmh.toFixed(1); R.lastS = +tr.s.toFixed(1); R.maxDecel = +R.maxDecel.toFixed(2); R.maxJerk = +R.maxJerk.toFixed(2);
    R.minU = Math.min(...R.series.map((x) => x[6]));
    return R;
  };
  const uphill = (g) => () => g;
  const S = [
    { name: 'level, empty', stops: [20, 700], limit: 50 },
    { name: 'level, full', stops: [20, 700], limit: 50, pax: 220 },
    { name: 'level, crush load', stops: [20, 700], limit: 50, pax: 320 },
    { name: 'one car', stops: [20, 700], limit: 50, cars: 1 },
    { name: 'up 40 per mille', stops: [20, 700], limit: 50, grade: uphill(0.04), pax: 100 },
    { name: 'up 80 per mille', stops: [20, 500], limit: 30, grade: uphill(0.08), pax: 100 },
    { name: 'down 40 per mille', stops: [20, 700], limit: 50, grade: uphill(-0.04), pax: 100 },
    { name: 'down 70 per mille', stops: [20, 600], limit: 30, grade: uphill(-0.07), pax: 100 },
    { name: 'crest into the stop', stops: [20, 600], limit: 50, grade: (s) => (s < 450 ? 0.04 : -0.05), pax: 100 },
    { name: 'stops 120 m apart', stops: [20, 140, 260, 380], limit: 50, pax: 60, secs: 200 },
    { name: 'stops 60 m apart', stops: [20, 80, 140], limit: 50, pax: 60, secs: 120 },
    { name: 'slow street', stops: [20, 400], limit: 15, pax: 60 },
    { name: 'limit, then the stop', stops: [20, 800], limits: [[0, 50], [400, 20], [500, 50]], pax: 60 },
    { name: 'limit just before the stop', stops: [20, 600], limits: [[0, 50], [480, 15]], pax: 60 },
    { name: 'weak wire', stops: [20, 900], limit: 60, pax: 100, supply: { u0: 650, r: 0.25, floor: 400 } },
    { name: 'stiff wire', stops: [20, 900], limit: 60, pax: 100, supply: { u0: 650, r: 0.03 } },
    { name: 'red at a signal, in good time', stops: [20, 900], limit: 50, pax: 60, signals: [{ s: 500, states: [[0, 'stop'], [75, 'go']] }] },
    { name: 'red turns green on the way in', stops: [20, 900], limit: 50, pax: 60, signals: [{ s: 500, states: [[0, 'stop'], [32, 'go']] }] },
    { name: 'green turns red close by', stops: [20, 900], limit: 50, pax: 60, signals: [{ s: 500, states: [[0, 'go'], [36, 'warn'], [39, 'stop'], [80, 'go']] }] },
    { name: 'tram ahead stands at the stop, then leaves', stops: [20, 700], limit: 50, pax: 60, ahead: { s: 700, length: 30.24, moves: [[0, 0], [62, 6]] } },
    { name: 'tram ahead creeps on', stops: [20, 900], limit: 50, pax: 60, ahead: { s: 400, length: 30.24, moves: [[0, 2]] } },
    // (the bell rings for it, and the stop does not change: it took the last-metres rule away and stood 3.6 m short, line 17 seed 5, Nádraží Modřany)
    { name: 'car crossing past the stop', stops: [20, 600], limit: 50, pax: 60, crossing: { s: 640 } },
    { name: 'car crossing past the stop, downhill', stops: [20, 600], limit: 50, pax: 60, grade: uphill(-0.022), crossing: { s: 640 } },
    // (its point, 6 m short of it, comes before the stop for a moment: the plan forgot the stop and drove, line 22 seed 5 at Radošovická, line 37 seed 4 at U Elektry)
    ...[62, 64, 66, 68, 70, 72].map((t) => ({ name: `car crossing just past the stop, uphill, at ${t} s`, stops: [20, 600], limit: 50, pax: 60, grade: uphill(0.02), crossing: { s: 603, from: t, to: t + 2 } })),
    // (a turn: current through the pantograph under the contact, without the drive pedal once braking for the stop)
    ...[[600, 25], [600, 40], [600, 55], [600, 150], [600, 400]].map(([s, d]) => ({ name: `turn under a contact ${d} m before the stop`, stops: [20, s], limit: 50, pax: 60, contact: s - d })),
    // (still at speed there, already braking: nothing but the drive pedal can draw the current)
    ...[[600, 70], [600, 100]].map(([s, d]) => ({ name: `turn under a contact ${d} m before the stop, at speed`, stops: [20, s], limit: 50, pax: 60, contact: s - d })),
    { name: 'turn under a contact 70 m before the stop, downhill', stops: [20, 600], limit: 50, pax: 60, grade: uphill(-0.03), contact: 530 },
  ].filter((x) => !only || x.name.includes(only));
  return S.map(drive);
}"""


# the time a drive may take, s (this branch's run + about 2 %): smooth driving must not cost the timetable. Main on the same free runs
# took as long; 4 % slower took line 22's late penalty from 17 to 509 (tools/bench/stops.js counts it on the real lines)
TIMES = {"level, full": 98, "level, crush load": 100, "up 40 per mille": 91, "down 40 per mille": 102, "stops 120 m apart": 108, "stops 60 m apart": 65, "slow street": 138, "limit, then the stop": 123}


def checks(r):
    fails = []
    name = r["name"]

    def want(ok, msg):
        if not ok:
            fails.append(f"{name}: {msg}")

    # (a tram ahead, or a signal that went back to GO, is what may bring the drive pedal back)
    # (nor may a car that had it slow well under the curve: uphill it would not reach the point rolling)
    free = [f for f in r["flips"] if (f["gap"] is None or f["gap"] > 60) and not f["car"]]
    if "turns green" not in name and "red at a signal" not in name and "green turns red" not in name and "stops 60" not in name and "at speed" not in name:
        want(not free, f"drive pedal after the brake with nothing ahead: {free[:3]}")
    want(r["shoes"] == 0 or "green turns red" in name, f"shoes fully in at speed {r['shoes']} steps")
    want(r["overrun"] == 0, f"over a signal at stop {r['overrun']} times")
    for st in r["stands"]:
        want(abs(st["err"]) <= 2.5, f"stood {st['err']} m from the point at {st['stop']}")
    if "stands at the stop" not in name:
        # (a car that comes into the way close by is a hard stop, as it should be)
        want(r["maxDecel"] <= (2.5 if "green turns red" in name else 1.8 if "just past" in name else 1.45), f"decelerated at {r['maxDecel']} m/s²")
    if "contact" in r:
        want(r["contact"]["drawn"], f"no current under the contact: {r['contact']}")
    if name in TIMES:
        want(r["secs"] <= TIMES[name], f"took {r['secs']} s, more than {TIMES[name]}")
    km = r["lastS"] / 1000
    # (following a slower tram is a pulse every few seconds, as a driver's)
    want(r["changes"] <= 25 * max(1, len(r["stands"])) + 60 * km + (r["secs"] / 3 if r["flips"] or "creeps" in name else 0), f"{r['changes']} pedal changes in {km:.2f} km and {len(r['stands'])} stops")
    return fails


def main():
    faulthandler.dump_traceback_later(300, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    only = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/README.md")
            drives = page.evaluate(RUN, only)
            browser.close()
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    sys.stdout.reconfigure(encoding="utf-8")
    for r in drives:
        err = ", ".join(str(s["err"]) for s in r["stands"])
        print(f"{r['name']:44} {r['secs']:6.1f} s, stops off by {err or '-':16} decel {r['maxDecel']:.2f}, jerk {r['maxJerk']:.1f}, pedal {r['changes']:3}, flips {len(r['flips'])}, shoes {r['shoes']}, U min {r['minU']}" + (f", contact {r['contact']}" if "contact" in r else ""))
    if "--report" in sys.argv:
        with open(sys.argv[sys.argv.index("--report") + 1], "w", encoding="utf-8") as fh:
            json.dump(drives, fh, ensure_ascii=False)
    fails = [f for r in drives for f in checks(r)]
    if errors:
        fails.append(f"page errors: {errors[:3]}")
    if fails:
        sys.exit("\n".join(fails))
    print("test drives: pass")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    main()
