# SPDX-License-Identifier: AGPL-3.0-or-later
"""A run is the same at any frame rate and in any view (#722): python -P -E tools/test_frame_rate.py [--line 37]
(its own server on a free port; needs data/). The real page and its own frame loop (src/main.js frame()), driven by a
made-up clock once the shift has started: one seed and the autopilot, at 20 and at 60 frames a second, in the cab and
in the chase view. After the same number of game steps, our tram, the clock, every car, walker and AI tram stand
exactly where they stand in the others. Before #722 the game cut each frame's time into its own steps (16.7 ms at
60 fps) and the traffic lived round the camera, so neither held."""
import argparse
import faulthandler
import os
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE, SEED, STEPS = "37", 7, 900  # 900 steps of 1/30 s: 30 s of game time

# Before the page's scripts: requestAnimationFrame and performance.now as they are until __manual(), then a made-up
# clock that moves only by __frame(ms), which runs the frame callbacks waiting for it.
CLOCK = """(() => {
  const realNow = performance.now.bind(performance), realRaf = window.requestAnimationFrame.bind(window), q = [];
  let manual = false, now = 0;
  performance.now = () => (manual ? now : realNow());
  window.requestAnimationFrame = (cb) => { if (!manual) return realRaf(cb); q.push(cb); return q.length; };
  window.__manual = () => { now = realNow(); manual = true; };
  window.__frame = (ms) => { now += ms; for (const cb of q.splice(0)) cb(now); };
})();"""

RUN = """async ({ seed, fps, chase, steps }) => {
  const $ = (id) => document.getElementById(id);
  window.runSeed = seed;
  window.headless = true; // (the frame loop only draws until the made-up clock takes over)
  $('menu').classList.remove('hidden');
  $('selStop').value = '0'; $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optWeather').value = 'dry'; $('optTemp').value = 'autumn'; $('optObst').value = 'normal';
  $('optAuto').checked = true;
  const { startShift } = await import('/tools/bench/shift.js');
  const g = await startShift(), tr = window.traffic;
  g.audio.setMuted?.(true);
  if (chase) window.dispatchEvent(new KeyboardEvent('keydown', { key: 'v' }));
  // the state after the game step `steps` (its traffic step follows it)
  let n = 0, snap = null;
  const update = g.update.bind(g), r = (v, k = 4) => +(+v).toFixed(k);
  g.update = (h, input) => {
    update(h, input);
    if (++n === steps) snap = {
      h, s: r(g.tram.s, 6), v: r(g.tram.v, 6), clock: r(g.clock, 6), next: g.nextStop,
      cars: tr.cars.filter((c) => c.active).map((c) => [c.id, r(c.s), r(c.vNow ?? 0)]),
      walkers: (tr.slots || []).map((w) => (w ? [r(w.x ?? NaN, 3), r(w.y ?? NaN, 3)] : null)),
      ahead: tr.ahead.map((t) => r(t.s)), oncoming: tr.oncoming.map((t) => r(t.s)),
    };
  };
  window.__manual();
  await new Promise((res) => setTimeout(res, 100)); // (a frame the real clock asked for runs, and asks the made-up one)
  window.__frame(0);
  window.headless = false;
  const ms = 1000 / fps;
  for (let k = 0; k < 100000 && !snap; k++) window.__frame(ms);
  return { snap, steps: n, chase: document.body.classList.contains('chase') };
}"""


class FrameRate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(900, exit=True)
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def run_at(self, fps, chase):
        page = self.browser.new_page()
        try:
            page.add_init_script(CLOCK)
            page.goto(f"{self.url}/index.html?line={LINE}")
            page.wait_for_selector("#btnStart:visible", timeout=240000)
            return page.evaluate(RUN, {"seed": SEED, "fps": fps, "chase": chase, "steps": STEPS})
        finally:
            page.close()

    def test_the_same_run_at_20_and_60_fps_in_the_cab_and_the_chase_view(self):
        runs = {(fps, chase): self.run_at(fps, chase) for fps, chase in ((60, False), (20, False), (60, True), (20, True))}
        ref = runs[(60, False)]["snap"]
        self.assertIsNotNone(ref, "the run did not reach its steps")
        self.assertAlmostEqual(ref["h"], 1 / 30, places=9)
        self.assertGreater(len(ref["cars"]) + sum(1 for w in ref["walkers"] if w), 5, "too little traffic to compare")
        for (fps, chase), out in runs.items():
            with self.subTest(fps=fps, chase=chase):
                self.assertEqual(out["chase"], chase)
                self.assertIsNotNone(out["snap"])
                for k in ("h", "s", "v", "clock", "next", "ahead", "oncoming", "cars", "walkers"):
                    self.assertEqual(out["snap"][k], ref[k], f"{fps} fps, {'chase' if chase else 'cab'}: {k}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--line", default=LINE)
    args, rest = ap.parse_known_args()
    LINE = args.line
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
