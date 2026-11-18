# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network a shift's Start builds (#658, tools/bench/network_layer.py) is a function of the data alone: line 37
loaded as a player loads it, a shift started, then the traffic's network built twice more. Both builds come out the same
(roads, lanes, footways and their links, doors, signals, as tools/bench/network_layer.py writes them out), and neither
calls the run's random numbers or Math.random (but for Three.js's object ids). That is what lets the build make the
network once (#658's design note).

    python -P -E tools/test_network_layer.py
A browser test (it loads the game, about a minute). Skipped without line 37's data (python -I tools/snapshot.py
data-fetch).
"""
import faulthandler
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench"))
from headless import load_page, serve, stop_server  # noqa: E402
import gpu  # noqa: E402
from network_layer import SERIALIZE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = "37"

TWICE = """async () => {
  const { startShift } = await import('/tools/bench/shift.js'), serialize = SERIALIZE;
  await startShift({ timeout: 300 });
  const g = window.game, tr = window.traffic, out = [];
  let rand = 0, random = 0, ids = 0;
  const own = () => { rand++; return tr.rand(); }, mathRandom = Math.random;
  // (Three.js draws each object's uuid with Math.random: the build's meshes, 120 calls on line 37; not the network)
  Math.random = () => { if ((new Error().stack || '').includes('generateUUID')) ids++; else random++; return mathRandom(); };
  try {
    for (let k = 0; k < 2; k++) {
      const T = new tr.constructor(window.scene, g.data, g.route, tr.ground, g, own);
      out.push(JSON.stringify(serialize(T)));
      T.dispose();
    }
  } finally {
    Math.random = mathRandom;
  }
  const n = JSON.parse(out[0]);
  return { same: out[0] === out[1], bytes: out[0].length, rand, random, ids,
           n: Object.fromEntries(Object.entries(n).map(([k, v]) => [k, v.length])) };
}""".replace("SERIALIZE", SERIALIZE)


class NetworkLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(ROOT, "data", f"line{LINE}.ground.json")):
            raise unittest.SkipTest(f"no line {LINE} data: python -I tools/snapshot.py data-fetch")
        from playwright.sync_api import sync_playwright
        # (page.evaluate has no time limit: a promise that never settles would hang the run without a word)
        faulthandler.dump_traceback_later(900, exit=True)
        cls.server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                try:
                    page, errors, load = load_page(browser, url, LINE, 600, {"keepgeo": False})
                    if isinstance(load, dict):
                        raise RuntimeError(f"line {LINE}: the load failed: {load} {errors[:3]}")
                    cls.r = page.evaluate(TWICE)
                    cls.errors = list(errors)
                finally:
                    browser.close()
        finally:
            stop_server(cls.server)
            faulthandler.cancel_dump_traceback_later()

    def test_built_twice_the_same(self):
        self.assertTrue(self.r["same"], self.r)
        for k in ("roads", "lanes", "walks", "doors", "lights"):
            self.assertGreater(self.r["n"][k], 0, (k, self.r["n"]))

    def test_no_randomness(self):
        self.assertEqual((self.r["rand"], self.r["random"]), (0, 0), self.r)

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
