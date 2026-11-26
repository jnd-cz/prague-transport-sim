# SPDX-License-Identifier: AGPL-3.0-or-later
"""Traffic scenes (#566): small street networks built in code and driven on the traffic core without the world
(tools/bench/scenes.js), each in milliseconds: python -P -E tools/test_traffic_scenes.py (own free-port server)."""
import faulthandler
from pathlib import Path
import re
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

# the scenes' results without their per-car end states (the asserts read what each scene reports)
PLAY = "async ([name, args]) => { const r = window.S.play(name, args); delete r.cars; delete r.trace; return r; }"

# a scene run twice, the traffic's car list in its own order and reversed: the steps whose cars' states differ
ORDER = """async (name) => {
  const S = window.S, A = S.SCENES[name](), B = S.SCENES[name]();
  B.T.cars.reverse();
  let differ = 0, first = null;
  for (let k = 0; k < Math.round(A.t / S.STEP); k++) {
    for (const sc of [A, B]) {
      const T = sc.T;
      T.game.clock += S.STEP;
      T.update(S.STEP, [0, 0]);
      if (sc.each) sc.each(T, T.game.clock);
    }
    const a = JSON.stringify(S.state(A.T)), b = JSON.stringify(S.state(B.T));
    if (a !== b) { differ++; first ??= k; }
  }
  return { differ, first, cars: A.T.cars.length };
}"""


class TrafficScenes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(120, exit=True)
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]
        cls.page = cls.browser.new_page()
        html = (Path(__file__).resolve().parent.parent / 'index.html').read_text(encoding='utf-8')
        importmap = re.search(r'<script type="importmap">.*?</script>', html, re.S)[0]
        cls.page.route('**/traffic-scenes-test', lambda r: r.fulfill(body=importmap, content_type='text/html'))
        cls.page.goto(cls.url + '/traffic-scenes-test')
        cls.page.evaluate("async () => { window.S = await import('/tools/bench/scenes.js'); }")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def play(self, name, **args):
        r = self.page.evaluate(PLAY, [name, args])
        return r

    def clean(self, r):
        self.assertEqual(r['hits'], [], 'a collision the rules reported')
        self.assertEqual(r['overlaps'], [], 'cars, walkers or the tram inside each other')

    def test_a_junction_without_signs_lets_every_car_through(self):
        r = self.play('junction')
        self.clean(r)
        self.assertEqual(sorted(r['through']), ['1', '2', '3', '4', '5', '6', '7', '8'])
        self.assertLess(max(r['through'].values()), 20)

    def test_the_order_the_cars_stand_in_decides_nothing(self):
        # (each step plans every car from the state at its start, and goes through them by id, #566)
        for name in ('junction', 'queueBeyond', 'sideRoad'):
            with self.subTest(name):
                r = self.page.evaluate(ORDER, name)
                self.assertGreaterEqual(r['cars'], 3)
                self.assertEqual(r['differ'], 0, f'states differ from step {r["first"]}')

    def test_a_car_does_not_enter_a_junction_it_cannot_leave(self):
        r = self.play('queueBeyond')
        self.clean(r)
        # (the queue beyond stands until 20 s: the car waits before the junction, the crossing car goes meanwhile)
        self.assertGreaterEqual(r['entered'], 20)
        self.assertLess(r['through']['2'], 20)
        self.assertIn('1', r['through'])

    def test_a_side_road_car_gets_into_a_busy_main_road(self):
        r = self.play('sideRoad')
        self.clean(r)
        self.assertGreater(r['fed'], 20)
        self.assertIsNotNone(r['in'])
        self.assertLess(r['in'], 30)

    def test_somebody_in_the_lane_holds_the_car(self):
        r = self.play('walkerInLane')
        self.clean(r)
        self.assertEqual(r['stood']['seen'], 'walker')
        self.assertIsNotNone(r['past'])

    def test_the_tram_waits_behind_cars_on_its_rails_and_all_go_on(self):
        r = self.play('carOnTrackBehindWaiting')
        self.clean(r)
        self.assertIsNotNone(r['stood'])
        self.assertLess(r['stood']['clock'], 25)  # (before the queue ahead moves)
        self.assertIsNotNone(r['past'])

    def test_a_car_turning_across_the_track_waits_for_the_tram(self):
        r = self.play('turnAcrossTrack')
        self.clean(r)
        self.assertTrue(r['yielded'])
        self.assertGreaterEqual(r['tramVMin'], 9.9)  # (the tram never braked for it)
        self.assertGreater(r['crossedAt'], r['tailPast'])

    def test_walkers_round_a_ring_of_walks_no_longer_hold_a_car(self):
        # (#496: before #608 the walkers circled the ring for good and the car stood behind them)
        jam = self.play('walkerRing', fixOff=True)
        self.assertIsNone(jam['past'])
        r = self.play('walkerRing')
        self.clean(r)
        self.assertIsNotNone(r['past'])
        self.assertLess(r['past'], 40)
        self.assertTrue(r['walkLoops'])

    def test_walkers_caught_on_one_spot_no_longer_hold_a_car(self):
        # (#393: walkers stepping round four short pieces on the spot held the car for good)
        jam = self.play('walkerSpot', fixOff=True)
        self.assertIsNone(jam['past'])
        r = self.play('walkerSpot')
        self.clean(r)
        self.assertIsNotNone(r['past'])
        self.assertLess(r['past'], 20)
        self.assertTrue(r['walkLeaves'])


if __name__ == '__main__':
    unittest.main()
