"""Where signals and stop points stand, decided in the build (tools/placement.py, #22): python -P -E tools/test_placement.py.

The rules on made-up streets, and on each line's data the build's placement against the game's own rules
(src/game.js placementDiffs) in headless Chromium; the latter skips for data built before the placement step."""
import faulthandler
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import placement as pl  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = Path(__file__).resolve().parent.parent


def street(x, w=8, car=True):
    """A street crossing the route (the x axis) at right angles at x."""
    return {'p': [[x, -40], [x, 40]], 'w': w, 'c': 1 if car else 0}


class Rules(unittest.TestCase):
    R = pl.Route([[0, 0], [1000, 0]])

    def placed(self, signals, roads=(), crossings=(), stops=()):
        stops = list(stops)
        targets = pl.stop_points(stops, self.R.length)
        C = pl.route_conflicts(self.R, list(roads), list(crossings), None, stops, targets)
        placed, _ = pl.place_signals(signals, C, stops, targets)
        return pl.platform_rule(placed, stops, list(targets))

    def test_a_signal_goes_to_its_junction_s_stop_line(self):
        (d,), _ = self.placed([{'s': 480, 'cross': 500}], [street(500)])
        self.assertEqual(d['rule'], 'junctionEdge')
        self.assertAlmostEqual(d['s'], 500 - 4 - 4, places=1)    # (the street's near edge 4 m before its centre)

    def test_no_conflict_near_it_runs_on_demand(self):
        (d,), _ = self.placed([{'s': 480, 'cross': 500}])
        self.assertTrue(d['demand'])
        self.assertEqual(d['rule'], 'onDemand')

    def test_along_a_platform_it_moves_to_the_head(self):
        # (on demand mid-platform, its crossing well past the platform: just past where the front stops)
        stop = {'name': 'A', 's': 400, 'sign': 420, 'p0': 360, 'p1': 420}
        (d,), targets = self.placed([{'s': 400, 'cross': 440}], stops=[stop])
        self.assertEqual((d['rule'], d['demand']), ('platformHead', True))
        self.assertAlmostEqual(d['s'], 422)
        self.assertEqual(targets, [420])

    def test_a_crossing_right_after_the_platform_hangs_it(self):
        stop = {'name': 'A', 's': 400, 'sign': 420, 'p0': 360, 'p1': 420}
        (d,), targets = self.placed([{'s': 410, 'cross': 422}], [street(422, w=4)], stops=[stop])
        self.assertEqual((d['rule'], d['hang'], d['head']), ('platformHang', True, 0))
        self.assertAlmostEqual(d['s'], 423, places=1)    # (3 m past the stop point, the crossing's edge after it)
        self.assertEqual(targets, [420])

    def test_a_crossing_inside_the_platform_moves_the_stop_point_back_before_it(self):
        stop = {'name': 'A', 's': 400, 'sign': 420, 'p0': 360, 'p1': 420}
        (d,), targets = self.placed([{'s': 405, 'cross': 419}], [street(419, w=4)], stops=[stop])
        self.assertEqual(d['rule'], 'platformHang')
        self.assertAlmostEqual(d['s'], 420, places=1)    # (the crossing's edge 417 + 3)
        self.assertAlmostEqual(targets[0], 417, places=1)

    def test_two_at_one_stop_line_are_one(self):
        out, _ = self.placed([{'s': 480, 'cross': 500}, {'s': 484, 'cross': 505}], [street(500)])
        self.assertEqual([d.get('rule') for d in out], ['junctionEdge', 'sameStopLine'])
        self.assertTrue(out[1]['drop'])

    def test_a_stop_beside_the_car_lane_is_vienna_type_an_island_is_not(self):
        # the road along the right of the route (y -1.6 to -8), the sidewalk beyond it; an island over the road at x 300-360
        road = {'c': 'road', 'l': 0, 'r': [[0, -1.6], [1000, -1.6], [1000, -8], [0, -8]]}
        walk = {'c': 'sidewalk', 'l': 0, 'r': [[0, -8], [1000, -8], [1000, -12], [0, -12]]}
        island = {'c': 'island', 'l': 0, 'r': [[300, -1.6], [360, -1.6], [360, -4.6], [300, -4.6]]}
        survey = pl.Survey([road, walk, island])
        self.assertEqual(survey.class_at(330, -3), 'island')     # (the smaller area, drawn over the road)
        self.assertAlmostEqual(pl.vienna(self.R, survey, 100, 130), 8.2, delta=0.41)
        self.assertIsNone(pl.vienna(self.R, survey, 310, 350))

    def test_an_area_keeps_its_holes_and_a_crossed_ring(self):
        # a road with a hole (`h`) at x 100-200, and its ring crossing itself at x 600 (a bow tie, as Seifertova's
        # carriageway at Lipanská on line 9): the game triangulates both, the hole empty and the road on both sides
        road = {'c': 'road', 'l': 0, 'r': [[0, -1], [500, -1], [700, -8], [1000, -8], [1000, -1], [700, -1], [500, -8], [0, -8]],
                'h': [[[100, -2], [200, -2], [200, -6], [100, -6]]]}
        survey = pl.Survey([road])
        self.assertIsNone(survey.class_at(150, -4))
        self.assertEqual(survey.class_at(300, -4), 'road')
        self.assertEqual(survey.class_at(800, -4), 'road')

    def test_a_platform_on_the_doors_side_is_ours_whichever_path_took_it(self):
        # line 9's round trip: the back path over the same track the same way, a hair nearer the platform, draws it;
        # the route passes it on its doors' side, so it is our stop's platform
        RB = pl.Route([[0, -0.01], [1000, -0.01]])
        right = {'p': [[100, -3], [160, -3]]}
        self.assertIs(pl.assign(right, self.R, RB)[0], RB)
        self.assertEqual(pl.ours(right, self.R), (100, 160))
        # the opposite track's platform (left of the route) is not ours
        self.assertIsNone(pl.ours({'p': [[100, 9], [160, 9]]}, self.R))

    def test_a_platform_reaching_behind_the_route_s_start_is_judged_by_its_part_along_it(self):
        # line 37 starts at the head of Spojovací's platform, 29 m of it behind the start
        self.assertEqual(pl.ours({'p': [[-29, -3], [1.5, -3]]}, self.R), (1.5, 1.5))

    def test_the_route_is_the_game_s_metre_by_metre_chords(self):
        R = pl.Route([[0, 0], [10, 0], [10, 10]])
        s, d = R.nearest(10.5, 5)
        self.assertAlmostEqual(s, 15, delta=0.6)
        self.assertLess(d, 1.0)
        self.assertEqual(R.at(3)[:2], (3.0, 0.0))


class GameAgrees(unittest.TestCase):
    """The game's own rules on each line agree with the build's placement (src/game.js placementDiffs)."""

    def test_no_line_differs(self):
        built = [p.stem[4:] for p in sorted((ROOT / 'data').glob('line*.json'))
                 if p.stem[4:].isdigit() and json.loads(p.read_text(encoding='utf-8')).get('signalsRaw')]
        if not built:
            self.skipTest('no line data with the placement step (tools/rebuild.py; python -I tools/snapshot.py data-fetch)')
        faulthandler.dump_traceback_later(900, exit=True)
        import headless
        from playwright.sync_api import sync_playwright
        server, url = headless.serve(0)
        try:
            with sync_playwright() as pw:
                b = gpu.launch(pw)[0]
                for line in built:
                    page = b.new_page()
                    page.goto(f"{url}/?line={line}", wait_until='load')
                    page.wait_for_function("() => document.getElementById('loading')?.classList.contains('hidden')", timeout=180000)
                    diffs = page.evaluate("""async () => { window.headless = true;
                        const { startShift } = await import('/tools/bench/shift.js'); const g = await startShift();
                        return g.placementDiffs; }""")
                    page.close()
                    with self.subTest(line=line):
                        self.assertEqual(diffs, [])
                b.close()
        finally:
            headless.stop_server(server)
            faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    unittest.main(verbosity=2)
