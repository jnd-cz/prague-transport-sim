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
        for name in ('junction', 'queueBeyond', 'sideRoad', 'queuePastTrack', 'crossPastTrack'):
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

    def test_a_car_waits_before_the_track_for_room_past_it(self):
        # (#602: the car ahead moving, the queue it will stop behind standing past the track; before, the second car followed
        # the first and stood across the track, its nearer end 1.2 m past the centre)
        r = self.play('queuePastTrack')
        self.clean(r)
        self.assertGreater(r['clear'], 2.6)  # (outside the band, 2.6 m each side of the centre)
        self.assertIsNotNone(r['through'])

    def test_a_car_waits_before_the_track_for_one_crossing_its_way_past_it(self):
        # (#602, line 23 s 329, seed 31, the user's picture: before, the car went on and met the crossing one 8 m past the
        # track, the two 0.23 m inside each other)
        r = self.play('crossPastTrack')
        self.clean(r)
        self.assertGreater(r['atCross'], 2.6)
        self.assertGreater(r['clear'], 2.6)
        self.assertIsNotNone(r['through'])

    def test_a_car_on_the_opposite_track_waits_there_for_our_tram(self):
        # (#602: past the group's first band it went on over ours, stopping only for a tram's body there; our tram hit it,
        # 3 m deep)
        r = self.play('heldOnOpposite')
        self.clean(r)
        self.assertIsNotNone(r['crossedAt'])
        self.assertGreater(r['crossedAt'], r['tailPast'])

    def test_a_car_on_both_tracks_of_a_street_taken_out_and_back_holds_our_tram_on_either(self):
        # (#602, line 9 s 24330, seed 2 on 1e23f0b: the car was reported only on the part of the route nearest its middle,
        # the outbound one, 20 km behind our tram on the return part, which drove into it)
        r = self.play('outAndBack')
        self.clean(r)
        self.assertIsNotNone(r['short'])
        self.assertGreater(r['short'], 2)  # (stood short of x 0, its front clear of the car's nose)
        self.assertIsNotNone(r['tailPast'])  # (and went on once the car was across)

    def test_walkers_round_a_ring_of_walks_no_longer_hold_a_car(self):
        # (#496: before #608 the walkers circled the ring for good and the car stood behind them)
        jam = self.play('walkerRing', fixOff=True, t=90)
        self.assertIsNone(jam['past'])
        # (the waits-for graph names the jam's heads: the walkers taking turns in front of the car, #560)
        self.assertEqual(set(jam['heads']), {'walker'})
        r = self.play('walkerRing')
        self.clean(r)
        self.assertIsNotNone(r['past'])
        self.assertLess(r['past'], 40)
        self.assertTrue(r['walkLoops'])
        self.assertEqual(r['heads'], {})

    def test_of_a_circle_of_cars_the_one_with_nobody_on_its_right_goes(self):
        # (#560, the user, 2026-11-24: "the traffic rule that car on the right should go first"; a junction at 0,0, the
        # cars 6 m before it on their lanes, 1.75 m right of the roads' middles)
        r = self.page.evaluate('''async () => {
          const { Traffic } = await import('/src/traffic.js');
          const make = () => { const tr = Object.create(Traffic.prototype); tr.game = { clock: 100 }; tr._seq = (c) => [[c.path, 0]]; return tr; };
          const car = (id, x, y, hx, hy, stood) => ({ id, kind: 'road', active: true, why: 'junction', s: 0, stood,
            path: { at: () => ({ x, y, hx, hy }) } });
          const S = () => car(1, 1.75, -6, 0, 1, 30), E = () => car(2, 6, 1.75, -1, 0, 10);
          const N = () => car(3, -1.75, 6, 0, -1, 10), W = () => car(4, -6, -1.75, 1, 0, 20);
          const goes = (tr, cars) => [...tr._letGo(cars).keys()].map((c) => c.id);
          const out = {};
          // two cars from the south and the east, each held by the other: the east one has nobody on its right
          { const tr = make(), s = S(), e = E(); s.waitFor = e; e.waitFor = s; out.two = goes(tr, [s, e]); out.cls = tr.circlesLetGo; }
          // the same, the east one held off a track for want of room past it: not sent onto it, the south one goes (#602)
          { const tr = make(), s = S(), e = E(); s.waitFor = e; e.waitFor = s; e.keepClear = true; out.offTracks = goes(tr, [s, e]); }
          // every arm taken, each waiting for the one on its right: the one that has stood longest
          { const tr = make(), cs = [S(), E(), N(), W()]; cs.forEach((c, i) => { c.waitFor = cs[(i + 1) % 4]; }); cs[3].stood = 40; out.four = goes(tr, cs); }
          // the east car follows the south one on its way (not a rule's hold): the south one goes
          { const tr = make(), s = S(), e = E(); s.waitFor = e; e.why = 'lead'; e.seen = { car: s }; s.path = e.path; out.follower = goes(tr, [s, e]); }
          // the build's lanes are on the right of their roads as fromRight reads it: a car heading +x stands at y < 0
          const S2 = window.S, T = S2.build({ roads: [{ p: [[-60, 0], [0, 0]] }, { p: [[0, 0], [60, 0]] }] });
          const p = S2.laneOf(T, 0, 1).path.at(20);
          out.right = { hx: Math.round(p.hx), y: Math.round(p.y * 100) / 100 };
          return out;
        }''')
        self.assertEqual(r['two'], [2])
        self.assertEqual(r['cls'], {'rules': 1})
        self.assertEqual(r['offTracks'], [1])
        self.assertEqual(r['four'], [4])
        self.assertEqual(r['follower'], [1])
        self.assertEqual(r['right']['hx'], 1)
        self.assertLess(r['right']['y'], 0)

    def test_walkers_caught_on_one_spot_no_longer_hold_a_car(self):
        # (#393: walkers stepping round four short pieces on the spot held the car for good)
        jam = self.play('walkerSpot', fixOff=True, t=90)
        self.assertIsNone(jam['past'])
        self.assertEqual(set(jam['heads']), {'walker'})  # (#560)
        r = self.play('walkerSpot')
        self.clean(r)
        self.assertIsNotNone(r['past'])
        self.assertLess(r['past'], 20)
        self.assertTrue(r['walkLeaves'])


if __name__ == '__main__':
    unittest.main()
