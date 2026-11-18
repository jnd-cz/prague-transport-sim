# SPDX-License-Identifier: AGPL-3.0-or-later
"""The driver's panel and the cab's frame (#246): python -P -E tools/test_panel.py [--line 17] (its own server on a free
port, 1600 x 900). Checks:
- the lamp strip's V (výstup): dark before a passenger's stop request, lit from it until the doors open, dark at a
  request stop nobody gets off at (src/panel.js requested);
- the heaters' knobs point at their position labels in every position (src/panel.js POS), the control switch's
  handle at its mark 1 (CAM);
- the cab frame leaves the mirror's picture out while it is shown, and covers it when the mirror is off (src/cabframe.js);
- with the head turned all the way left, the cab's rear wall stands at the screen's left edge (src/cabframe.js REAR)."""
import argparse
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the V lamp at a request stop somebody gets off at: before the press, after it, once the doors opened; and with nobody
# getting off
REQUEST = """async () => {
  const g = window.game, wait = () => new Promise((r) => setTimeout(r, 150));
  const lamp = () => document.querySelector('#dash .full [data-l="V"]').getAttribute('class');
  const st = g.stops.find((s) => s.request && s.i > 0);
  if (!st) return { skip: 'no request stop' };
  const prev = g.stops[st.i - 1], frac = st.alightFrac, out = {}, was = [g.nextStop, g.tram.s];
  g.paused = true; g.tram.v = 0; g.tram.a = 0; g.nextStop = st.i; st.alightFrac = 0.2;
  g.tram.s = prev.target + 5; await wait(); out.before = lamp();
  g.tram.s = st.target - 3; await wait(); out.after = lamp();
  st.served = true; await wait(); out.served = lamp();
  st.served = false; st.alightFrac = 0; await wait(); out.nobody = lamp();
  st.alightFrac = frac;
  // (back at the shift's start, running: the head turns only while the game runs)
  [g.nextStop, g.tram.s] = was; g.paused = false;
  return out;
}"""
# each heater position: the knob's angle against the direction from its middle to the position's label; the control
# switch: its handle against its mark 1
KNOBS = """async () => {
  const g = window.game, wait = () => new Promise((r) => setTimeout(r, 400)), out = [];
  const mid = (el) => { const b = el.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; };
  for (const [id, key, n] of [['kalor', 'cab', 4], ['salon', 'saloon', 3]]) {
    const ctl = document.querySelector(`#dash .full [data-c="${id}"]`), knob = ctl.querySelector('.knob');
    const labels = [...ctl.querySelectorAll('.pos')], was = g.climate[key];
    for (let k = 0; k < n; k++) {
      g.climate[key] = k; await wait();
      const m = new DOMMatrix(getComputedStyle(knob).transform), a = Math.atan2(m.b, m.a) * 180 / Math.PI;
      const [cx, cy] = mid(knob.parentElement), [lx, ly] = mid(labels[k]);
      out.push({ id, k, label: labels[k].textContent, knob: Math.round(a), toLabel: Math.round(Math.atan2(ly - cy, lx - cx) * 180 / Math.PI) });
    }
    g.climate[key] = was;
  }
  const cam = document.querySelector('#dash .full [data-c="vypinac"] .cam'), h = cam.querySelector('.handle');
  const m = new DOMMatrix(getComputedStyle(h).transform), [cx, cy] = mid(cam), [lx, ly] = mid(cam.querySelectorAll('.marks b')[1]);
  out.push({ id: 'vypinac', k: 1, label: '1', knob: Math.round(Math.atan2(m.b, m.a) * 180 / Math.PI), toLabel: Math.round(Math.atan2(ly - cy, lx - cx) * 180 / Math.PI) });
  return out;
}"""
# the cab frame's canvas at the middle of the mirror's picture and at the screen's left edge
PIXELS = """(rect) => {
  const cv = document.getElementById('cabFrame'), g = cv.getContext('2d'), k = cv.width / innerWidth;
  const at = (x, y) => [...g.getImageData(Math.round(x * k), Math.round(y * k), 1, 1).data];
  const b = document.getElementById('mirror').getBoundingClientRect(), m = rect || b;
  return { shown: b.width > 0, rect: { left: m.left, top: m.top, width: m.width, height: m.height },
           mirror: at(m.left + m.width / 2, m.top + m.height / 2), edge: at(4, innerHeight * 0.35),
           z: getComputedStyle(document.getElementById('mirror')).zIndex };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skip: data/line{args.line}.json missing (python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(600, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails, r = [], {}
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            ctx = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
            ctx.add_init_script("try { localStorage.setItem('tram-fullscreen', '0'); localStorage.removeItem('tram-panel-fold'); } catch {}")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            page.mouse.move(8, 200)
            r["request"] = page.evaluate(REQUEST)
            r["knobs"] = page.evaluate(KNOBS)
            page.keyboard.down("q")
            page.wait_for_timeout(2500)
            r["left"] = page.evaluate(PIXELS)
            page.keyboard.press("z")
            page.wait_for_timeout(300)
            r["noMirror"] = page.evaluate(PIXELS, r["left"]["rect"])
            page.keyboard.up("q")
            r["errors"] = errors[:3]
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    q = r["request"]
    if "skip" not in q:
        if "on" in q["before"]:
            fails.append(f"V lit before the stop request: {q}")
        if q["after"] != "on g":
            fails.append(f"V dark after the stop request: {q}")
        if "on" in q["served"] or "on" in q["nobody"]:
            fails.append(f"V lit once the doors opened or with nobody getting off: {q}")
    for k in r["knobs"]:
        d = (k["knob"] - k["toLabel"] + 180) % 360 - 180
        if abs(d) > 6:
            fails.append(f"{k['id']} at {k['label']}: the knob points {d}° off its label")
    m, n = r["left"], r["noMirror"]
    if r["left"]["z"] != "6":
        fails.append(f"the mirror's frame is not over the HUD (z-index {m['z']})")
    if not m["shown"] or m["mirror"][3] != 0:
        fails.append(f"the cab frame covers the mirror's picture: {m['mirror']}")
    if n["shown"] or n["mirror"][3] == 0:
        fails.append(f"with the mirror off (Z), the cab frame leaves its place out: {n['mirror']}")
    if m["edge"][3] < 255 or abs(m["edge"][0] - 0x5f) > 3:
        fails.append(f"no rear wall at the left edge with the head turned all the way left: {m['edge']}")
    if r["errors"]:
        fails.append(f"page errors: {r['errors']}")
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
