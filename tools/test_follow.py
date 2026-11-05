"""A tram stopping dead in front of our autopilot (#221, #260): python -P -E tools/test_follow.py [--line 22]
(its own server on a free port). The autopilot drives the line until it runs at 30 km/h or more on open
track; an AI tram is put 60 m ahead of it at the same speed, keeps that distance for 2 s, then stands where it is
(as if it had hit something); then again 35 m ahead, closer than the service brake can stop in (the
emergency position, track brakes). Our tram must stop without touching it: at least 1 m behind its rear, no
collision. The autopilot plans to stop behind the leader's current rear (a "brick wall"), so a leader
stopping at once is the worst case it has to meet."""
import argparse
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
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const g = window.game, tr = g.tram, traffic = window.traffic, ap = new Autopilot(), dt = 1 / 30;
  g.audio.setMuted?.(true);
  const step = () => { ap.step(g, dt); g.update(dt, ap.input); traffic.update(dt, { position: { x: 0, z: 0 } }); };
  const out = [];
  let T = 0;
  for (const ahead of [60, 35]) {
    // to speed on open track: 30 km/h or more and no stop within 200 m
    while (T < 1800 && !(tr.v > 8.3 && (g.stops[g.nextStop]?.target ?? 1e9) - tr.s > 200 && !traffic.ahead.some((o) => o.s > tr.s && o.s - tr.s < 300))) { step(); T += dt; }
    if (tr.v <= 8.3) return { err: 'never reached 30 km/h', T, kmh: tr.kmh, out };
    // (the leader appears 2 s before it stops: its rear `ahead` m in front of ours then, both at our speed)
    const v0 = tr.kmh, ai = { ...traffic._newTram(), v: tr.v, dwell: 0, lastStop: g.nextStop, endS: null };
    ai.s = tr.s + ahead + ai.length;
    traffic.ahead.push(ai);
    let minGap = 1e9, t = 0, frozen = null, stoppedAt = null, deepest = 0;
    const hits0 = g.penalties.collision || 0;
    while (t < 60) {
      if (frozen === null && t >= 2) frozen = ai.s;
      if (frozen === null) { ai.v = tr.v; ai.s += tr.v * dt; } // (keeps its distance until it stops)
      step(); t += dt; T += dt;
      if (frozen !== null) { ai.s = frozen; ai.v = 0; ai.dwell = 1e9; }
      minGap = Math.min(minGap, ai.s - ai.length - tr.s);
      deepest = Math.max(deepest, tr.eq.brakeAngle);
      if (stoppedAt === null && frozen !== null && tr.v < 0.01) stoppedAt = +t.toFixed(1);
    }
    out.push({ ahead, v0: +v0.toFixed(1), minGap: +minGap.toFixed(2), stoppedAt, collisions: (g.penalties.collision || 0) - hits0, deepestBrake: deepest });
    traffic.ahead.splice(traffic.ahead.indexOf(ai), 1);
  }
  return { out };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="22")
    args = ap.parse_args()
    faulthandler.dump_traceback_later(600, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 540})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            page.evaluate("document.getElementById('optObst').value = 'off'; document.getElementById('optAuto').checked = false")
            page.click("#btnStart")
            page.wait_for_function("window.game && window.traffic", timeout=60000)
            r = page.evaluate(RUN)
            browser.close()
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    print(json.dumps(r))
    fails = []
    if r.get("err"):
        fails.append(f"{r['err']}: {r}")
    for c in r.get("out", []):
        if c["collisions"] or c["minGap"] < 1 or c["stoppedAt"] is None:
            fails.append(f"our tram did not stop at least 1 m behind a tram stopping dead {c['ahead']} m ahead at {c['v0']} km/h: {c}")
    if errors:
        fails.append(f"page errors: {errors[:3]}")
    if fails:
        sys.exit("; ".join(fails))
    print("; ".join(f"a tram stopping dead {c['ahead']} m ahead at {c['v0']} km/h: ours stopped {c['minGap']} m behind it after {c['stoppedAt']} s"
                    for c in r["out"]) + ": pass")


if __name__ == "__main__":
    main()
