"""Tests of the top-of-rail assembly (tools/line_heights.py, #197) on synthetic chains:
python -P -E tools/test_line_heights.py"""
import contextlib
import io
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import line_heights as lh  # noqa: E402


def chain(xy, z, kind='paved', terrain=None):
    """A Chain along the polyline xy with a staged height z(s) (None: held) every 5 m bin."""
    c = lh.Chain(xy, [])
    for b in range(int(c.length // lh.BIN) + 1):
        s = min((b + .5) * lh.BIN, c.length)
        h = z(s)
        p = c.line.interpolate(s)
        c.bins.append({'s': s, 'z': h, 'w': 0.0 if h is None else 1.0, 'src': None if h is None else 'dtmp',
                       'kind': kind, 'terrain': terrain(s) if terrain else None, 'xy': (p.x, p.y), 'flags': []})
    return c


def arc(x0, y0, r, a0, a1, n=40):
    return [(x0 + r * math.cos(a0 + (a1 - a0) * k / n), y0 + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def quiet(f, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a)


class Assembly(unittest.TestCase):
    def test_fork_takes_the_through_tracks_height(self):
        # a turnout leaving a 1 % grade, its own data 0.2 m higher: its end takes the through track's height
        through = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        branch = chain([(100, 0)] + arc(100, 50, 50, -math.pi / 2, 0)[1:], lambda s: 101.2 + .01 * s)
        summary = quiet(lh.assemble, [through, branch])
        self.assertLess(abs(branch.z_at(0)[0] - through.z_at(100)[0]), .01)
        self.assertEqual(summary['over_1cm'], 0)

    def test_crossing_at_grade_shares_one_height(self):
        a = chain([(0, 0), (200, 0)], lambda s: 100.0)
        b = chain([(100, -100), (100, 100)], lambda s: 100.06)
        summary = quiet(lh.assemble, [a, b])
        self.assertLess(abs(a.z_at(100)[0] - b.z_at(100)[0]), .01)
        self.assertEqual(summary['crossings_apart'], [])

    def test_track_over_another_is_not_pinned(self):
        a = chain([(0, 0), (200, 0)], lambda s: 100.0)
        b = chain([(100, -100), (100, 100)], lambda s: 106.0)
        summary = quiet(lh.assemble, [a, b])
        self.assertGreater(abs(a.z_at(100)[0] - b.z_at(100)[0]), 5)
        self.assertEqual(len(summary['crossings_apart']), 1)

    def test_a_hold_over_60_m_cuts_the_profile(self):
        c = chain([(0, 0), (300, 0)], lambda s: None if 100 < s < 190 else 100 + .005 * s)
        quiet(lh.assemble, [c])
        self.assertEqual(len(c.runs), 2)
        self.assertEqual(len(c.held), 1)
        self.assertIsNone(c.z_at(145)[0])
        short = chain([(0, 0), (300, 0)], lambda s: None if 100 < s < 140 else 100 + .005 * s)
        quiet(lh.assemble, [short])
        self.assertEqual(len(short.runs), 1)
        self.assertAlmostEqual(short.z_at(120)[0], 100.6, delta=.02)  # (bridged by the curve)
        self.assertEqual(short.z_at(120)[1], 'curve')

    @staticmethod
    def sag(s):
        # -6 % into +6 % along a 100 m radius: no curve at the street's 500 m stays within 10 cm of it
        if s < 94:
            return 100 - .06 * s
        if s < 106:
            return 100 - .06 * s + (s - 94) ** 2 / 200
        return 100 - .06 * 106 + 144 / 200 + .06 * (s - 106)

    def test_a_sag_tighter_than_the_radius_stays_in_the_band_and_goes_to_review(self):
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        quiet(lh.assemble, [c])
        self.assertLess(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + lh.FIT)
        self.assertEqual([p['kind'] for p in c.review], ['band'])
        self.assertLess(c.review[0]['factor'], 1)
        self.assertTrue(c.review[0]['fits'])

    def test_a_curve_at_the_radius_within_the_band_is_solved(self):
        # (a 600 m sag with +-4 cm of noise: within 10 cm at 500 m, nothing for review, the noise not followed)
        noise = lambda s: .04 if int(s // 5) % 2 else -.04
        c = chain([(0, 0), (300, 0)], lambda s: 100 + (s - 150) ** 2 / 1200 + noise(s))
        quiet(lh.assemble, [c])
        self.assertEqual(c.review, [])
        self.assertLess(max(abs(c.z_at(s)[0] - (100 + (s - 150) ** 2 / 1200)) for s in range(10, 290, 5)), .03)

    def test_an_answer_to_hold_the_radius_keeps_it_and_the_place_is_reviewed(self):
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        lh.RADIUS_ANSWERS = [{'xy': (100.0, 0.0), 'answer': lh.HOLD}]
        try:
            quiet(lh.assemble, [c])
        finally:
            lh.RADIUS_ANSWERS = []
        self.assertGreater(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + .005)  # (the radius held)
        self.assertEqual([(p['kind'], p['factor']) for p in c.review], [('band', 1.0)])

    def test_a_lone_bump_is_dropped(self):
        c = chain([(0, 0), (200, 0)], lambda s: 100.5 if abs(s - 102.5) < 1 else 100.0)
        quiet(lh.assemble, [c])
        self.assertLess(abs(c.z_at(102.5)[0] - 100), .05)
        self.assertEqual(c.review, [])

    def test_the_archive_on_the_ground_under_a_deck_is_not_followed(self):
        # (a 5 m dive over 20 m and back, steeper than any track: a step, not a sag)
        c = chain([(0, 0), (300, 0)], lambda s: 195.0 if 140 < s < 160 else 200.0)
        quiet(lh.assemble, [c])
        self.assertLess(abs(c.z_at(150)[0] - 200), .05)
        self.assertEqual(c.review, [])
        self.assertTrue(c.steps)

class Lines(unittest.TestCase):
    def test_a_line_past_a_fork_has_no_step(self):
        through = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        branch = chain([(100, 0)] + arc(100, 50, 50, -math.pi / 2, 0)[1:], lambda s: 101.0 + .01 * s)
        quiet(lh.assemble, [through, branch])
        path = [(0, 0), (100, 0)] + arc(100, 50, 50, -math.pi / 2, 0)[1:]
        zs, srcs, _ = lh.Lookup([through, branch]).along(path)
        self.assertTrue(all(z is not None for z in zs))
        steps = [abs(b - a) for a, b in zip(zs, zs[1:])]
        self.assertLess(max(steps), .025)  # (2 m at grades of 1 %: no jump between the two tracks)

    def test_the_opposite_track_beside_ours(self):
        path = [(0, 0), (100, 0)]
        back = [(100, 3.5), (0, 3.5)]
        off, zs = lh.across(path, back, [200.0 + .01 * k for k in range(51)])
        self.assertTrue(all(abs(o - 3.5) < 1e-6 for o in off))
        self.assertAlmostEqual(zs[0], 200.5, places=3)  # (our s 0 is the opposite track's s 100)

    def test_a_track_ending_on_another_takes_its_height(self):
        through = {'p': [[0, 0], [40, 0]], 'zs': [100 + .02 * 2 * k for k in range(21)]}
        branch = {'p': [[20, .3], [40, 10]], 'zs': [100.43 + .01 * k for k in range(13)]}
        lh.join_ends([through, branch])
        self.assertAlmostEqual(branch['zs'][0], 100.4, places=3)  # (the through track's height at x 20)
        self.assertAlmostEqual(branch['zs'][-1], 100.43 + .12, places=3)  # (its far end, free, unchanged)

    def test_ends_meeting_only_each_other_take_their_mean(self):
        a = {'p': [[0, 0], [20, 0]], 'zs': [100.0] * 11}
        b = {'p': [[20, .2], [40, 5]], 'zs': [100.04] * 12}
        lh.join_ends([a, b])
        self.assertAlmostEqual(a['zs'][-1], 100.02, places=3)
        self.assertAlmostEqual(b['zs'][0], 100.02, places=3)

    def test_ranges(self):
        self.assertEqual(lh.ranges(['di', 'di', 'dtmp', 'dtmp', 'surface']),
                         [[0, 3.0, 'di'], [3.0, 7.0, 'dtmp'], [7.0, 8, 'surface']])


if __name__ == '__main__':
    unittest.main()
