# SPDX-License-Identifier: AGPL-3.0-or-later
"""Start reads no survey (#658): line 17 loaded as a player loads it (the window drops the lookups past it once the load
is done), a shift started. Start reads no lookup of a tile the window does not hold (the survey's classes, the ground's
heights: every one goes through the lookup), and fewer lookups are held than the file has tiles. The traffic's network
is the file's (data/lineN.network.json, tools/network.py): its roads, lanes, walks, doors, bound lanes, heads and
crossings, each lane where the file starts it, the heads on the file's heights and the bridges' and road tunnels' ways
between the file's ends (#682). Line 17 has every part: OSM's stop lines and signalled crossings, medians, crossings on
the road under a bridge (the file's, #823; Start's seed draws one).

    python -P -E tools/test_network_layer.py
A browser test (about 30 s). Skipped without line 17's network (python -I tools/snapshot.py data-fetch).
"""
import faulthandler
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from headless import load_page, serve, stop_server  # noqa: E402
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = "17"
# Start's seed: its jaywalker draw picks Čechův most's crossing (s 14900), inside the bridge's span. Before #823 Start
# asked Profile.overBridge there and read the ground under the span, past the window: with a fresh seed the test failed
# on about one Start in six (line 17 has four crossings inside a span)
SEED = 12

START = """async (seed) => {
  const lk = window.groundTiles.lookup, reads = {}, missed = {};
  const undo = ['height', 'survey', 'kind', 'bedOffSurvey', 'covered'].map((k) => {
    const f = lk[k];
    lk[k] = function (x, y, ...a) { reads[k] = (reads[k] || 0) + 1; if (!lk._at(x, y)) missed[k] = (missed[k] || 0) + 1; return f.call(this, x, y, ...a); };
    return () => { delete lk[k]; };
  });
  // (Start asks for no ground once a tile comes for our stops' signs, shelters and stand-in platforms, #694)
  const gl = lk.g, later = gl.later, stopLater = [];
  gl.later = function (x, y, fn) { if (/buildStop/.test(new Error().stack)) stopLater.push([x, y]); return later.call(this, x, y, fn); };
  const { startShift } = await import('/tools/bench/shift.js');
  window.runSeed = seed;
  try { await startShift({ timeout: 300 }); } finally { for (const u of undo) u(); gl.later = later; delete window.runSeed; }
  const T = window.traffic, mm = (v) => Math.round(v * 1000), g = window.game;
  // (the crossings inside a span, past the window still: what Start's own overBridge answered there before #823)
  const spans = g.profile.bridges;
  const inSpan = g.data.crossings.map((s, k) => [k, s]).filter(([, s]) => spans.some(([a, b]) => s > a + 8 && s < b - 8))
    .map(([k, s]) => [k, g.profile.overBridge(s)]);
  return { reads, missed, held: window.groundTiles.lookups.size, tiles: window.groundTiles.tiles.size,
    n: { roads: T.roads.length, lanes: T.laneList.length, walks: T.walks.length, doors: T.doors.length, lights: T.lightLanes.length,
         pedCross: T.pedCross.length, heads: T.heads.length, pedHeads: T.pedHeads.length },
    lanes: T.laneList.map((l) => [l.k, l.dir, l.sel, mm(l.path.p[0][0]), mm(l.path.p[0][1]), l.path.p.length]),
    poles: [T.heads, T.pedHeads].map((H) => H.map((h) => h.h)), // (the heights the heads' poles stand at, #228: the traffic's)
    ways: window.game.route.ground.wayEnds.size, stopLater,
    stops: window.game.stops.map((st) => ({ target: st.target, vienna: st.vienna, sign: window.run.gameView.meshOf(st).position.y })), inSpan };
}"""


class StartReadsNoSurvey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        net = os.path.join(ROOT, "data", f"line{LINE}.network.json")
        if not os.path.exists(net):
            raise unittest.SkipTest(f"no line {LINE} network: python -I tools/snapshot.py data-fetch")
        with open(net, encoding="utf-8") as f:
            cls.net = json.load(f)
        from playwright.sync_api import sync_playwright
        # (page.evaluate has no time limit: a promise that never settles would hang the run without a word)
        faulthandler.dump_traceback_later(900, exit=True)
        server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                try:
                    page, cls.errors, load = load_page(browser, url, LINE, 600, {"keepgeo": False})
                    if isinstance(load, dict):
                        raise RuntimeError(f"line {LINE}: the load failed: {load} {cls.errors[:3]}")
                    cls.r = page.evaluate(START, SEED)
                finally:
                    browser.close()
        finally:
            stop_server(server)
            faulthandler.cancel_dump_traceback_later()

    def test_no_lookup_past_the_window(self):
        self.assertEqual(self.r["missed"], {}, self.r["reads"])
        self.assertLess(self.r["held"], self.r["tiles"])

    def test_the_network_is_the_files(self):
        N = self.net
        self.assertEqual(self.r["n"], {"roads": len(N["roads"]), "lanes": len(N["lanes"]), "walks": len(N["walks"]),
                                       "doors": len(N["doors"]), "lights": len(N["lights"]), "pedCross": len(N["pedCross"]),
                                       "heads": len(N["heads"]), "pedHeads": len(N["pedHeads"])})
        self.assertEqual(self.r["lanes"], [[L["road"], L["dir"], L["sel"], L["p"][0], L["p"][1], len(L["p"]) // 2] for L in N["lanes"]])
        self.assertGreater(len(N["pedCross"]), 0)

    def test_heights_are_the_files(self):
        """The heads stand on the heights the build stored (#682), and the bridges' and road tunnels' ways run between
        the build's ends."""
        for poles, key in zip(self.r["poles"], ("heads", "pedHeads")):
            self.assertEqual(len(poles), len(self.net[key]))
            worst = max((abs(y - h["z"] / 100) for y, h in zip(poles, self.net[key])), default=0)
            self.assertLess(worst, 0.001, key)
        self.assertEqual(self.r["ways"], len(self.net["ways"]))

    def test_our_stops_stand_on_the_files(self):
        """Our stops' signs and shelters stand where the build put them, on its heights: Start calls ground.later for
        none of them, and a Vienna-type stop's sign stands on the stored zs (#694)."""
        self.assertEqual(self.r["stopLater"], [])
        self.assertEqual(len(self.r["stops"]), len(self.net["stops"]))
        vienna = [(st, N) for st, N in zip(self.r["stops"], self.net["stops"]) if st["vienna"]]
        self.assertTrue(vienna)  # (line 17 has two)
        for st, N in vienna:
            self.assertLess(abs(st["sign"] - N["zs"] / 100), 0.001)

    def test_crossings_over_bridges_are_the_files(self):
        """No jaywalker waits at a crossing on the road under a bridge: the build's list (overBridgeCrossings) is what
        the page's Profile.overBridge answers at each crossing inside a span, so the draws stay as they were (#823)."""
        self.assertTrue(self.r["inSpan"])  # (line 17: Modřany, the culvert at s 5816, Čechův most)
        self.assertEqual([k for k, over in self.r["inSpan"] if over], self.net["overBridgeCrossings"])

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
