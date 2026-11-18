# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground's tiles streamed round the camera (src/groundFile.js GroundTiles, #30): line 37 loaded as a player loads it
(no ?keepgeo) and the window moved along its route every STEP m (tools/bench/ground_tiles.py's drive): at every step
each tile within the detail's reach of the camera is drawn in detail and each within the fog's end at least far, fewer
tiles are drawn than the file has, fewer keep their lookup, and the height lookup answers on the route. A shift
started with the window at the line's far end judges as many platforms surveyed as the first (Start reads no survey: the
build's network says, #658; with the lookups gone past the window Start judged 30 of 40 unsurveyed, #654).

    python -P -E tools/test_ground_tiles.py
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
from ground_tiles import DRIVE  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE, STEP = "37", 1000.0


# a shift, then the window moved to the line's far end (the frame loop's off) and a shift started again: the platforms
# the survey draws, each time
SHIFTS = """async () => {
  const { startShift } = await import('/tools/bench/shift.js'), surveyed = () => window.game.platforms.filter((p) => p.surveyed).length;
  await startShift({ timeout: 120 });
  const first = surveyed(), g = window.groundTiles, r = window.game.route, p = r.at(r.length);
  g.last = Infinity;
  await g.update([[p.x, p.y]], g.reach(window.scene.fog.far));
  g.drain();
  await startShift({ timeout: 120 });
  return [first, surveyed()];
}"""


class Window(unittest.TestCase):
    def test_every_tile_in_view_drawn_and_the_far_ones_dropped(self):
        if not os.path.exists(os.path.join(ROOT, "data", f"line{LINE}.ground.json")):
            self.skipTest("no line data: python -I tools/snapshot.py data-fetch")
        faulthandler.dump_traceback_later(900, exit=True)
        from playwright.sync_api import sync_playwright
        server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                page, errors, load = load_page(browser, url, LINE, 600, {"keepgeo": False})
                self.assertNotIsInstance(load, dict, f"line {LINE}: {load} {errors[:3]}")
                first, again = page.evaluate(SHIFTS)
                r = page.evaluate(DRIVE, {"step": STEP})
                # (the lookup on the route where its tile is held: the route at the camera's step)
                on = page.evaluate("""() => { const g = window.groundTiles, p = window.game.route.at(0);
                  return [g.lookup.height(p.x, p.y), g.lookups.has(g.keyAt(p.x, p.y))]; }""")
                page.close()
                browser.close()
        finally:
            stop_server(server)
            faulthandler.cancel_dump_traceback_later()
        self.assertEqual(errors, [])
        steps = r["steps"]
        self.assertEqual([x["s"] for x in steps if x["missing"]], [])
        self.assertEqual([x["s"] for x in steps if x["bare"]], [])
        self.assertTrue(all(x["coarse"] > 0 for x in steps))
        self.assertTrue(all(x["drawn"] < x["tiles"] for x in steps), [(x["s"], x["drawn"], x["tiles"]) for x in steps])
        self.assertTrue(all(x["lookups"] < x["tiles"] for x in steps), [(x["s"], x["lookups"], x["tiles"]) for x in steps])
        self.assertGreater(first, 0)
        self.assertEqual(again, first)
        self.assertEqual(r["all"]["drawn"], r["all"]["tiles"])  # (every tile at the end: the drive's last step)
        z, held = on
        self.assertTrue(held)
        self.assertIsNotNone(z)


if __name__ == "__main__":
    unittest.main()
