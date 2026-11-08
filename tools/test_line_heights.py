"""Tests of the top-of-rail assembly (tools/line_heights.py, #197) on synthetic chains:
python -P -E tools/test_line_heights.py"""
import contextlib
import io
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
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

    @staticmethod
    def tightest(c):
        return min(min(lh.implied_radii(run['s'], run['z']), default=math.inf) for run in c.runs)

    def test_a_sag_tighter_than_the_floor_holds_the_floor_and_goes_to_review(self):
        # (the user, 2026-11-07: "hold minimum radius at 500m everywhere and get back with review cases which can't fit")
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        quiet(lh.assemble, [c])
        self.assertGreater(self.tightest(c), lh.radii()['min'] * .97)
        self.assertGreater(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + .005)  # (the band gave way)
        self.assertEqual([(p['kind'], p['factor'], p['fits']) for p in c.review], [('band', 1.0, False)])
        self.assertGreater(c.review[0]['excess'], .005)
        follow = c.review[0]['final']  # (the card's 'follow the data': within the band, below the floor)
        self.assertLess(min(lh.implied_radii([a for a, _ in follow], [b for _, b in follow]), default=math.inf), lh.radii()['min'])

    def test_a_follow_answer_given_before_the_floor_gives_way_only_to_it(self):
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        lh.RADIUS_ANSWERS, lh.FLOOR_SINCE = [{'xy': (100.0, 0.0), 'answer': lh.FOLLOW, 'date': '2026-11-03'}], '2026-11-07'
        try:
            quiet(lh.assemble, [c])
        finally:
            lh.RADIUS_ANSWERS, lh.FLOOR_SINCE = [], None
        self.assertGreater(self.tightest(c), lh.radii()['min'] * .97)
        self.assertFalse(c.review[0]['fits'])

    def test_a_follow_answer_given_since_the_floor_follows_the_data_below_it(self):
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        lh.RADIUS_ANSWERS, lh.FLOOR_SINCE = [{'xy': (100.0, 0.0), 'answer': lh.FOLLOW, 'date': '2026-11-08'}], '2026-11-07'
        try:
            quiet(lh.assemble, [c])
        finally:
            lh.RADIUS_ANSWERS, lh.FLOOR_SINCE = [], None
        self.assertLess(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + lh.FIT)
        self.assertLess(self.tightest(c), lh.radii()['min'])

    def test_pins_that_need_a_tighter_curve_get_it_and_go_to_review(self):
        # (two meeting points 4 m apart, 20 cm apart in height, on a level track: the rails join, below the floor)
        c = chain([(0, 0), (200, 0)], lambda s: 100.0)
        quiet(lh.solve, c, {100.0: 100.0, 104.0: 100.2}, lh.radii())
        self.assertLess(abs(c.z_at(104.0)[0] - 100.2), .01)
        tight = [p for p in c.review if p['below']]
        self.assertEqual(len(tight), 1)
        self.assertLess(tight[0]['radius'], lh.radii()['min'])

    def test_a_hold_answer_at_a_junction_holds_the_floor_and_the_tracks_meet_half_way(self):
        # (a track crossing two others 4 m apart whose heights differ by 20 cm: alone it meets them on a 320 m curve; held,
        # the two give way towards it. The user, 2026-11-07: "best fit to 500m limit even at the price of larger height
        # difference from source")
        a = chain([(100, -150), (100, 150)], lambda s: 100.0)
        b = chain([(104, -150), (104, 150)], lambda s: 100.2)
        c = chain([(0, 0), (200, 0)], lambda s: 100.1)
        lh.RADIUS_ANSWERS = [{'xy': (102.0, 0.0), 'answer': lh.HOLD, 'date': '2026-11-07'}]
        try:
            quiet(lh.assemble, [a, b, c])
        finally:
            lh.RADIUS_ANSWERS = []
        self.assertGreater(self.tightest(c), lh.radii()['min'] * .97)
        self.assertLess(abs(c.z_at(100)[0] - a.z_at(150)[0]), .01)
        self.assertLess(abs(c.z_at(104)[0] - b.z_at(150)[0]), .01)
        self.assertFalse([p for p in c.review if p['below']])

    def test_on_open_track_the_radius_gives_way_to_the_floor_and_no_review(self):
        # (a 700 m sag: under the open track's 1000 m, over the floor, within the band at it)
        c = chain([(0, 0), (300, 0)], lambda s: 100 + (s - 150) ** 2 / 1400 * (1 if abs(s - 150) < 60 else 0)
                  + (0 if abs(s - 150) < 60 else (60 ** 2 / 1400 + 120 / 1400 * (abs(s - 150) - 60))), kind='open')
        quiet(lh.assemble, [c])
        self.assertEqual(c.review, [])
        self.assertGreater(self.tightest(c), lh.radii()['min'] * .97)
        self.assertLess(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + lh.FIT)

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

    def test_an_answer_that_discards_the_outliers_fits_the_radius_to_the_rest(self):
        # (a 1 m hump over 30 m, 50 m radius at its top: without the answer the radius gives way to follow it, held
        # alone the curve misses the top by 16 cm)
        hump = lambda s: 100 + math.exp(-((s - 100) / 10) ** 2)
        c = chain([(0, 0), (200, 0)], hump, terrain=hump)
        lh.RADIUS_ANSWERS = [{'xy': (100.0, 0.0), 'answer': lh.HOLD, 'outliers': 'drop'}]
        try:
            quiet(lh.assemble, [c])
        finally:
            lh.RADIUS_ANSWERS = []
        # (the four top bins dropped; the curve at the radius within the band of the rest)
        self.assertEqual(len(c.dropped), 4)
        self.assertEqual([(p['kind'], p['factor']) for p in c.review], [('band', 1.0)])
        self.assertLess(c.z_at(100)[0], hump(100) - .5)
        top = lambda si: any(abs(x - si) < .01 for x, _ in c.dropped)
        self.assertTrue(all(abs(c.z_at(b['s'])[0] - b['z']) <= lh.BAND + lh.FIT for b in c.bins if not top(b['s'])))

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

    def test_past_the_opposite_routes_end_there_is_no_opposite_track(self):
        # (#344, line 23 near Těšnov: 52 m past the opposite route's end, its end 3 m to the side was taken as beside ours)
        path = [(0, 0), (100, 0)]
        back = [(60, 3.0), (0, 3.0)]
        off, zs = lh.across(path, back, [200.0 + .01 * k for k in range(31)])
        self.assertTrue(all(o is not None for o in off[:30]))
        self.assertTrue(all(o is None and z is None for o, z in zip(off[33:], zs[33:])))

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


class TruePlaces(unittest.TestCase):
    def bins(self, grade=0.05):
        # a straight 5 % grade, each bin's sample up to 2.4 m off its centre and its height true to where it lies
        line = lh.LineString([(0, 0), (200, 0)])
        out = []
        for b in range(40):
            s = (b + .5) * lh.BIN
            t = s + 2.4 * math.sin(b * 1.7)
            out.append({'s': s, 'z': 100 + grade * t, 'xy': (t, 0.0)})
        return line, out

    def test_a_grade_stays_a_grade(self):
        line, series = self.bins()
        before = max(abs(x['z'] - (100 + .05 * x['s'])) for x in series)
        lh.at_true_places(series, line)
        after = max(abs(x['z'] - (100 + .05 * x['s'])) for x in series[1:-1])
        self.assertGreater(before, .1)
        self.assertLess(after, .001)

    def test_a_held_bin_stays_held(self):
        line, series = self.bins()
        series[7]['z'] = None
        series[7]['xy'] = None
        lh.at_true_places(series, line)
        self.assertIsNone(series[7]['z'])

    def test_a_bin_with_no_sample_near_keeps_its_height(self):
        line = lh.LineString([(0, 0), (200, 0)])
        series = [{'s': 2.5, 'z': 100.0, 'xy': (2.5, 0.0)}, {'s': 102.5, 'z': 104.0, 'xy': (102.5, 0.0)}]
        lh.at_true_places(series, line)
        self.assertEqual([x['z'] for x in series], [100.0, 104.0])

    def test_a_chain_passing_a_sample_twice_leaves_it_in_its_bin(self):
        # (project finds the chain's other pass, far from this bin's centre)
        line = lh.LineString([(0, 0), (200, 0)])
        series = [{'s': 2.5, 'z': 100.0, 'xy': (2.5, 0.0)}, {'s': 7.5, 'z': 100.0, 'xy': (150.0, 0.0)}, {'s': 12.5, 'z': 100.0, 'xy': (12.5, 0.0)}]
        lh.at_true_places(series, line)
        self.assertEqual([x['z'] for x in series], [100.0, 100.0, 100.0])


class Answers(unittest.TestCase):
    def setUp(self):
        self.old = lh.STEP_ANSWERS
        self.addCleanup(lambda: setattr(lh, 'STEP_ANSWERS', self.old))

    def test_an_answer_drops_a_sources_heights_along_a_stretch(self):
        # (line 9 at Olšanské hřbitovy: DI's 65 cm dip left of the card's marker goes, the curve bridges it)
        dip = lambda s: 100.0 - (0.6 if 30 <= s <= 60 else 0.0)
        c = chain([(0, 0), (200, 0)], dip)
        for x in c.bins:
            x['src'] = 'di'
        lh.IGNORE_ANSWERS = [{'ignore': 'stretch', 'stretch': [(25.0, 0.0), (65.0, 0.0)], 'sources': ['di'], 'xy': (45.0, 0.0), 'reach': 15}]
        try:
            self.assertEqual(lh.answered_ignore([c]), sum(1 for x in c.bins if 25 <= x['s'] <= 65))
            quiet(lh.assemble, [c])
        finally:
            lh.IGNORE_ANSWERS = []
        self.assertAlmostEqual(c.z_at(45)[0], 100.0, delta=.02)

    def test_an_answer_drops_the_heights_between_a_junctions_switches(self):
        # (Malovanka: a 30 cm hump between the switches; within the junction's 15 cm band the curve rose half of it)
        c = chain([(0, 0), (200, 0)], lambda s: 100.0 + (0.3 if 90 <= s <= 110 else 0.0))
        c.switch = [(85.0, 95.0), (105.0, 115.0)]
        lh.IGNORE_ANSWERS = [{'ignore': 'switches', 'xy': (100.0, 0.0), 'reach': 40, 'stretch': [], 'sources': []}]
        try:
            quiet(lh.solve, c, {}, lh.radii())
        finally:
            lh.IGNORE_ANSWERS = []
        self.assertAlmostEqual(c.z_at(100)[0], 100.0, delta=.03)

    def test_an_answer_has_the_tracks_follow_the_ground_in_an_area(self):
        # (Královka's west arm: the data level, the ground stepping 60 cm down at 12 % over 5 m; the step was dropped as
        # steeper than any track and the arm stayed 15-78 cm above the ground)
        ground = lambda s: 100.0 if s <= 95 else 99.4 if s >= 100 else 100.0 - .12 * (s - 95)
        c = chain([(0, 0), (260, 0)], lambda s: 100.0, terrain=ground)
        lh.GROUND_ANSWERS = [{'area': lh.Polygon([(70, -5), (150, -5), (150, 5), (70, 5)]), 'answer': lh.FOLLOW, 'date': None,
                              'radius_min': 250.0}]
        try:
            self.assertGreater(lh.answered_ground([c]), 0)
            for x in c.bins:
                x['staged'] = x['z']
            quiet(lh.assemble, [c])
        finally:
            lh.GROUND_ANSWERS = []
        self.assertAlmostEqual(c.z_at(125)[0], 99.4, delta=lh.GROUND_BAND + .01)
        self.assertAlmostEqual(c.z_at(80)[0], 100.0, delta=lh.GROUND_BAND + .01)
        self.assertAlmostEqual(c.z_at(240)[0], 100.0, delta=lh.BAND)
        # (the edge makes no step: no grade steeper than any track's beyond the ground's own step)
        s = [5.0 * k for k in range(52)]
        z = [c.z_at(t)[0] for t in s]
        self.assertLess(max(abs(b - a) / 5 for t, a, b in zip(s, z, z[1:]) if not 85 <= t <= 105), lh.MAX_GRADE)
        # (no tighter than the area's limit, within the solver's tolerance: the step itself needs 42 m)
        self.assertGreater(min(lh.implied_radii(c.runs[0]['s'], c.runs[0]['z'])), 250.0 * lh.TIGHT)

    def test_an_archive_answer_takes_the_archive_and_holds_where_it_has_none(self):
        lh.STEP_ANSWERS = [{'xy': (0.0, 0.0), 'use': 'archive', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0}]
        series = [{'xy': (10.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}, {'xy': (20.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': None},
                  {'xy': (90.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}]
        lh.answered_source(series)
        self.assertEqual([(x['z'], x['w'], x['src']) for x in series], [(191.5, 1.0, 'dtmp'), (None, 0.0, None), (190.0, 1.0, 'di')])

    def test_a_di_answer_leaves_the_height(self):
        lh.STEP_ANSWERS = [{'xy': (0.0, 0.0), 'use': 'di', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0}]
        series = [{'xy': (10.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}]
        lh.answered_source(series)
        self.assertEqual(series[0]['z'], 190.0)

    def test_outliers_go_only_within_the_reach(self):
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for x in c.bins:
            x['survey'] = None
        c.bins[10]['z'] += .3
        c.bins[50]['z'] += .3
        lh.STEP_ANSWERS = [{'xy': (52.5, 0.0), 'use': 'di', 'drop': True, 'blend': False, 'radius': None, 'reach': 70.0}]
        self.assertEqual(lh.answered_noise([c])[0], 1)
        self.assertIsNone(c.bins[10]['z'])
        self.assertIsNotNone(c.bins[50]['z'])

    def test_a_noisy_height_takes_the_mean_with_the_survey(self):
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for x in c.bins:
            x['survey'] = 100.0 + .01 * x['s']
        c.bins[10]['z'] += .1
        lh.STEP_ANSWERS = [{'xy': (52.5, 0.0), 'use': 'di', 'drop': False, 'blend': True, 'radius': None, 'reach': 70.0}]
        before = c.bins[10]['z']
        self.assertGreaterEqual(lh.answered_noise([c])[1], 1)
        self.assertLess(c.bins[10]['z'], before)

    def test_the_surveys_pull_makes_no_step_between_bins(self):
        # the survey 20 cm under a noisy stretch: the heights fade towards it, no two neighbours over 5 cm further apart than the grade
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for k, x in enumerate(c.bins):
            x['survey'] = 99.8 + .01 * x['s']
            if k % 2:
                x['z'] += .06
        lh.STEP_ANSWERS = [{'xy': (150.0, 0.0), 'use': 'di', 'drop': False, 'blend': True, 'radius': None, 'reach': 70.0}]
        lh.answered_noise([c])
        steps = [abs(b['z'] - a['z'] - .05) for a, b in zip(c.bins, c.bins[1:])]
        self.assertLess(max(steps), .09)
        self.assertLess(c.bins[30]['z'], 100 + .01 * c.bins[30]['s'] - .02)

    def test_a_toward_answer_moves_the_archive_half_way_and_fades_at_its_edge(self):
        # (Malovanka, 2026-11-07: "Let's pick the half option"; the survey and lidar 20 cm over the archive)
        c = chain([(0, 0), (300, 0)], lambda s: 100.0)
        for x in c.bins:
            x['archive'], x['survey'], x['terrain'] = 100.0, 100.2, 100.2
        c.bins[0]['terrain'] = 101.0  # (another level: stays)
        lh.STEP_ANSWERS = [{'xy': (60.0, 0.0), 'use': 'archive', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0,
                            'toward': {'heights': 'survey+lidar', 'share': 0.5}}]
        lh.answered_toward([c])
        # (s 2.5 on another level, s 62.5 at the answer, s 7.5 and 112.5 in the fade 52.5 m off, s 132.5 past the reach)
        for k, want in ((0, 100.0), (12, 100.1), (1, 100.0875), (22, 100.0875), (26, 100.0)):
            self.assertAlmostEqual(c.bins[k]['z'], want, places=6)
        steps = [abs(b['z'] - a['z']) for a, b in zip(c.bins[1:], c.bins[2:])]
        self.assertLess(max(steps), .03)

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_a_step_answer_replaces_the_radius_answers_in_its_reach(self):
        truth = {'trackHeights': {'radiusAnswers': [{'place': [50.08862, 14.40603], 'answer': lh.HOLD}, {'place': [50.05, 14.4], 'answer': lh.HOLD}],
                                  'stepAnswers': [{'place': [50.08862, 14.40603], 'use': 'archive', 'radius': 'follow'}]}}
        out = lh.load_radius_answers(truth)
        self.assertEqual(sorted(a['answer'] for a in out), [lh.FOLLOW, lh.HOLD])
        self.assertEqual(lh.answer_at([out[-1]['xy']]), None)


class Neighbour(unittest.TestCase):
    def tracks(self, f=lambda s: 100 + .02 * s, g=lambda s: 100.3 + .02 * s):
        return chain([(0, 0), (400, 0)], f), chain([(0, 3.5), (400, 3.5)], g)

    def test_a_dip_on_one_track_takes_the_other_tracks_height_and_their_offset(self):
        a, b = self.tracks()
        for k in (40, 41, 42):
            a.bins[k]['z'] -= 1.0
        self.assertEqual(lh.snap_to_neighbour([a, b]), 3)
        for k in (40, 41, 42):
            self.assertAlmostEqual(a.bins[k]['z'], 100 + .02 * a.bins[k]['s'], delta=.01)

    def test_tracks_that_really_differ_stay_apart(self):
        a, b = self.tracks()
        self.assertEqual(lh.snap_to_neighbour([a, b]), 0)
        self.assertAlmostEqual(b.bins[40]['z'] - a.bins[40]['z'], .3, delta=1e-6)

    def test_a_dip_on_both_stays(self):
        a, b = self.tracks()
        for k in (40, 41, 42):
            a.bins[k]['z'] -= 1.0
            b.bins[k]['z'] -= 1.0
        self.assertEqual(lh.snap_to_neighbour([a, b]), 0)

    def test_a_lone_track_stays(self):
        a, _ = self.tracks()
        a.bins[40]['z'] -= 1.0
        self.assertEqual(lh.snap_to_neighbour([a]), 0)


class Sources(unittest.TestCase):
    def hump(self, both=False, flags=()):
        # (#344, line 9 at Sídliště Řepy: one track's DI humped up to 0.97 m over the lidar for 90 m, the archive and the
        # track beside it on the lidar)
        ground = lambda s: 100 + .02 * s
        bump = lambda s: max(0.0, 0.9 * (1 - abs(s - 200) / 50))
        a = chain([(0, 0), (400, 0)], lambda s: ground(s) + 0.15 + bump(s), terrain=ground)
        b = chain([(0, 3), (400, 3)], lambda s: ground(s) + 0.15 + (bump(s) if both else 0.0), terrain=ground)
        for c in (a, b):
            for x in c.bins:
                x['src'], x['archive'], x['flags'] = 'di', ground(x['s']) + 0.15, list(flags)
        return a, b, ground

    def test_dis_hump_on_one_track_takes_the_archive(self):
        a, b, ground = self.hump()
        self.assertGreater(lh.archive_over_di([a, b]), 0)
        self.assertLess(max(abs(x['z'] - ground(x['s']) - 0.15) for x in a.bins), lh.SOURCES_EDGE + 1e-9)
        self.assertTrue(all(x['src'] == 'di' for x in b.bins))

    def test_a_hump_on_both_tracks_stays(self):
        # (a rebuild may have raised both tracks since the archive)
        a, b, _ = self.hump(both=True)
        self.assertEqual(lh.archive_over_di([a, b]), 0)

    def test_on_a_structure_dis_height_stays(self):
        a, b, _ = self.hump(flags=['structure_hint'])
        self.assertEqual(lh.archive_over_di([a, b]), 0)


class Smoothed(unittest.TestCase):
    def test_it_hardly_moves_a_height_near_a_junction(self):
        through = chain([(0, 0), (400, 0)], lambda s: 100 + .15 * math.sin(s / 6))
        branch = chain([(200, 0), (200, 100)], lambda s: 100.0)
        z0 = {round(x['s']): x['z'] for x in through.bins}
        lh.smooth_heights([through, branch])
        reach, small = lh.SMOOTH_JUNCTION
        at = [x for x in through.bins if abs(x['s'] - 200) <= reach]
        self.assertTrue(at)
        self.assertLessEqual(max(abs(x['z'] - z0[round(x['s'])]) for x in at), small + 1e-9)

    def test_a_short_run_stays(self):
        c = chain([(0, 0), (90, 0)], lambda s: 100 + .1 * math.sin(s / 6))
        z0 = [x['z'] for x in c.bins]
        lh.smooth_heights([c])
        self.assertEqual([x['z'] for x in c.bins], z0)

    def test_it_moves_a_height_at_most_the_clamp(self):
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .15 * math.sin(s / 6))
        z0 = [x['z'] for x in c.bins]
        lh.smooth_heights([c])
        self.assertLessEqual(max(abs(x['z'] - z) for x, z in zip(c.bins, z0)), lh.SMOOTH_CLAMP + 1e-9)


if __name__ == '__main__':
    unittest.main()
