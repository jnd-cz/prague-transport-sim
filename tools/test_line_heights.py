# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the top-of-rail assembly (tools/line_heights.py, #197) and of the answers' rules in front of it
(tools/height_answers.py, #418) on synthetic chains:
python -P -E tools/test_line_heights.py"""
import contextlib
import io
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import height_answers as ha  # noqa: E402
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
        ha.RADIUS_ANSWERS, ha.FLOOR_SINCE = [{'xy': (100.0, 0.0), 'answer': ha.FOLLOW, 'date': '2026-11-03'}], '2026-11-07'
        try:
            quiet(lh.assemble, [c])
            # (the build is the one without the answer: that the solver met it, and did not take it, is asserted here, #418)
            self.assertIs(ha.answer_at([(100.0, 0.0)], (ha.FOLLOW,)), ha.RADIUS_ANSWERS[0])
            self.assertFalse(ha.below_floor([(100.0, 0.0)]))
        finally:
            ha.RADIUS_ANSWERS, ha.FLOOR_SINCE = [], None
        self.assertGreater(self.tightest(c), lh.radii()['min'] * .97)
        self.assertFalse(c.review[0]['fits'])

    def test_a_follow_answer_given_since_the_floor_follows_the_data_below_it(self):
        c = chain([(0, 0), (200, 0)], self.sag, terrain=self.sag)
        ha.RADIUS_ANSWERS, ha.FLOOR_SINCE = [{'xy': (100.0, 0.0), 'answer': ha.FOLLOW, 'date': '2026-11-08'}], '2026-11-07'
        try:
            quiet(lh.assemble, [c])
        finally:
            ha.RADIUS_ANSWERS, ha.FLOOR_SINCE = [], None
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
        ha.RADIUS_ANSWERS = [{'xy': (102.0, 0.0), 'answer': ha.HOLD, 'date': '2026-11-07'}]
        try:
            quiet(lh.assemble, [a, b, c])
        finally:
            ha.RADIUS_ANSWERS = []
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
        ha.RADIUS_ANSWERS = [{'xy': (100.0, 0.0), 'answer': ha.HOLD}]
        try:
            quiet(lh.assemble, [c])
            # (the floor holds this sag without the answer too: that the solver met it is asserted here, #418)
            self.assertIs(ha.answer_at([(100.0, 0.0)]), ha.RADIUS_ANSWERS[0])
        finally:
            ha.RADIUS_ANSWERS = []
        self.assertGreater(max(abs(c.z_at(b['s'])[0] - b['z']) for b in c.bins), lh.BAND + .005)  # (the radius held)
        self.assertEqual([(p['kind'], p['factor']) for p in c.review], [('band', 1.0)])

    def test_an_answer_that_discards_the_outliers_fits_the_radius_to_the_rest(self):
        # (a 1 m hump over 30 m, 50 m radius at its top: without the answer the radius gives way to follow it, held
        # alone the curve misses the top by 16 cm)
        hump = lambda s: 100 + math.exp(-((s - 100) / 10) ** 2)
        c = chain([(0, 0), (200, 0)], hump, terrain=hump)
        ha.RADIUS_ANSWERS = [{'xy': (100.0, 0.0), 'answer': ha.HOLD, 'outliers': 'drop'}]
        try:
            quiet(lh.assemble, [c])
        finally:
            ha.RADIUS_ANSWERS = []
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


class AtOnce(unittest.TestCase):
    """Lookup.along, across and staged_along ask GEOS for every point at once (#516): the same output, to its last bit,
    as asking one point at a time (the code before, here)."""

    def setUp(self):
        import random
        rng = random.Random(7)
        self.chs = []
        for k in range(14):  # (tracks side by side, crossing and forking, with runs of heights and steps)
            y0, bend = 3.5 * (k % 5), rng.uniform(-.004, .004)
            xy = [(x, y0 + bend * (x - 150) ** 2 / 10 + (k // 5) * x * .2) for x in range(0, 301, 7)]
            self.chs.append(chain(xy, lambda s, k=k: 200 + .01 * s + k * .1))
        quiet(lh.assemble, self.chs)
        for c in self.chs[::3]:
            for run in c.runs:
                run['step'] = [False] * len(run['s'])
        self.path = [(x, y + .05 + ((x % 13) - 6) * .02) for x, y in self.chs[0].xy]  # (along one track, wavering)
        self.back = [(x, y - .05) for x, y in reversed(self.chs[1].xy)]  # (the track beside it, the other way)

    def along_one_by_one(self, lookup, pts, step=lh.OUT_STEP):
        from shapely.geometry import LineString
        line = LineString(pts)
        L = line.length
        n = max(1, math.ceil(L / step - 1e-9))
        zs, srcs = [], []
        for k in range(n + 1):
            s = min(L, k * step)
            over = k * step - s
            p, a, b = line.interpolate(s), line.interpolate(max(0.0, s - 1)), line.interpolate(min(L, s + 1))
            d = math.hypot(b.x - a.x, b.y - a.y) or 1
            ux, uy = (b.x - a.x) / d, (b.y - a.y) / d
            cands = []
            for j in lookup.tree.query(p.buffer(lh.MATCH)):
                c = lookup.chs[int(j)]
                dist = c.line.distance(p)
                if dist > lh.MATCH:
                    continue
                t = c.line.project(p)
                vx, vy = c.direction(t)
                cos = ux * vx + uy * vy
                if abs(cos) >= math.cos(math.radians(lh.ANGLE)):
                    cands.append((dist, int(j), t + (over if cos > 0 else -over)))
            acc = wsum = 0.0
            src = None
            for dist, j, t in sorted(cands):
                z, sj = lookup.chs[j].z_at(t)
                if z is None:
                    continue
                w = (1 - dist / lh.MATCH) / (dist + .02) ** 2
                acc, wsum, src = acc + w * z, wsum + w, src or sj
            zs.append(round(acc / wsum, 3) if wsum else None)
            srcs.append(src if wsum else 'surface')
        return zs, srcs, L

    def across_one_by_one(self, path, back, back_z, step=lh.OUT_STEP):
        from shapely.geometry import LineString
        a, b = LineString(path), LineString(back)
        n = max(1, math.ceil(a.length / step - 1e-9))
        off, zs = [], []
        for k in range(n + 1):
            s = min(a.length, k * step)
            p, u0, u1 = a.interpolate(s), a.interpolate(max(0.0, s - 1)), a.interpolate(min(a.length, s + 1))
            d = math.hypot(u1.x - u0.x, u1.y - u0.y) or 1
            ux, uy = (u1.x - u0.x) / d, (u1.y - u0.y) / d
            t = b.project(p)
            q, v0, v1 = b.interpolate(t), b.interpolate(max(0.0, t - 1)), b.interpolate(min(b.length, t + 1))
            e = math.hypot(v1.x - v0.x, v1.y - v0.y) or 1
            lat = (q.y - p.y) * ux - (q.x - p.x) * uy
            i = min(int(t / step), len(back_z) - 2)
            z0, z1 = back_z[i], back_z[i + 1]
            if (not lh.ACROSS_MIN <= abs(lat) <= lh.ACROSS_MAX or p.distance(q) > lh.ACROSS_MAX or z0 is None or z1 is None
                    or abs(ux * (v1.x - v0.x) + uy * (v1.y - v0.y)) / e < math.cos(math.radians(lh.ANGLE))):
                off.append(None)
                zs.append(None)
                continue
            off.append(round(lat, 2))
            zs.append(round(z0 + (z1 - z0) * (t / step - i), 3))
        return off, zs

    def staged_one_by_one(self, pts, lookup):
        from shapely.geometry import LineString
        line_, out = LineString(pts), []
        for j in lookup.tree.query(line_, predicate='dwithin', distance=lh.MATCH):
            c = lookup.chs[int(j)]
            for run in c.runs:
                if any(run['step']):
                    continue
                for s, raw in zip(run['s'], run['raw']):
                    if raw is None:
                        continue
                    p = c.line.interpolate(s)
                    if line_.distance(p) <= .3:
                        out.append([round(line_.project(p), 1), round(raw, 3)])
        return sorted(out)

    def test_as_one_point_at_a_time(self):
        lookup = lh.Lookup(self.chs)
        got = lookup.along(self.path)
        self.assertEqual(got, self.along_one_by_one(lookup, self.path))
        self.assertGreater(sum(z is not None for z in got[0]), 50)
        back_z = lookup.along(self.back)[0]
        self.assertEqual(lh.across(self.path, self.back, back_z), self.across_one_by_one(self.path, self.back, back_z))
        self.assertGreater(sum(o is not None for o in lh.across(self.path, self.back, back_z)[0]), 5)
        got = lh.staged_along(self.path, lookup)
        self.assertEqual(got, self.staged_one_by_one(self.path, lookup))
        self.assertGreater(len(got), 10)


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
        self.old = ha.STEP_ANSWERS
        self.addCleanup(lambda: setattr(ha, 'STEP_ANSWERS', self.old))

    def test_an_answer_drops_a_sources_heights_along_a_stretch(self):
        # (line 9 at Olšanské hřbitovy: DI's 65 cm dip left of the card's marker goes, the curve bridges it)
        dip = lambda s: 100.0 - (0.6 if 30 <= s <= 60 else 0.0)
        c = chain([(0, 0), (200, 0)], dip)
        for x in c.bins:
            x['src'] = 'di'
        ha.IGNORE_ANSWERS = [{'ignore': 'stretch', 'stretch': [(25.0, 0.0), (65.0, 0.0)], 'sources': ['di'], 'xy': (45.0, 0.0), 'reach': 15}]
        try:
            self.assertEqual(ha.answered_ignore([c]), sum(1 for x in c.bins if 25 <= x['s'] <= 65))
            quiet(lh.assemble, [c])
        finally:
            ha.IGNORE_ANSWERS = []
        self.assertAlmostEqual(c.z_at(45)[0], 100.0, delta=.02)

    def test_an_answer_drops_the_heights_between_a_junctions_switches(self):
        # (Malovanka: a 30 cm hump between the switches; within the junction's 15 cm band the curve rose half of it)
        c = chain([(0, 0), (200, 0)], lambda s: 100.0 + (0.3 if 90 <= s <= 110 else 0.0))
        c.switch = [(85.0, 95.0), (105.0, 115.0)]
        ha.IGNORE_ANSWERS = [{'ignore': 'switches', 'xy': (100.0, 0.0), 'reach': 40, 'stretch': [], 'sources': []}]
        try:
            quiet(lh.solve, c, {}, lh.radii())
        finally:
            ha.IGNORE_ANSWERS = []
        self.assertAlmostEqual(c.z_at(100)[0], 100.0, delta=.03)

    def test_an_answer_has_the_tracks_follow_the_ground_in_an_area(self):
        # (Královka's west arm: the data level, the ground stepping 60 cm down at 12 % over 5 m; the step was dropped as
        # steeper than any track and the arm stayed 15-78 cm above the ground)
        ground = lambda s: 100.0 if s <= 95 else 99.4 if s >= 100 else 100.0 - .12 * (s - 95)
        c = chain([(0, 0), (260, 0)], lambda s: 100.0, terrain=ground)
        ha.GROUND_ANSWERS = [{'area': ha.Polygon([(70, -5), (150, -5), (150, 5), (70, 5)]), 'answer': ha.FOLLOW, 'date': None,
                              'radius_min': 250.0}]
        try:
            self.assertGreater(ha.answered_ground([c]), 0)
            for x in c.bins:
                x['staged'] = x['z']
            quiet(lh.assemble, [c])
        finally:
            ha.GROUND_ANSWERS = []
        self.assertAlmostEqual(c.z_at(125)[0], 99.4, delta=lh.GROUND_BAND + .01)
        self.assertAlmostEqual(c.z_at(80)[0], 100.0, delta=lh.GROUND_BAND + .01)
        self.assertAlmostEqual(c.z_at(240)[0], 100.0, delta=lh.BAND)
        # (the edge makes no step: no grade steeper than any track's beyond the ground's own step)
        s = [5.0 * k for k in range(52)]
        z = [c.z_at(t)[0] for t in s]
        self.assertLess(max(abs(b - a) / 5 for t, a, b in zip(s, z, z[1:]) if not 85 <= t <= 105), ha.MAX_GRADE)
        # (no tighter than the area's limit, within the solver's tolerance: the step itself needs 42 m)
        self.assertGreater(min(lh.implied_radii(c.runs[0]['s'], c.runs[0]['z'])), 250.0 * lh.TIGHT)

    def test_an_archive_answer_takes_the_archive_and_holds_where_it_has_none(self):
        ha.STEP_ANSWERS = [{'xy': (0.0, 0.0), 'use': 'archive', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0}]
        series = [{'xy': (10.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}, {'xy': (20.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': None},
                  {'xy': (90.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}]
        ha.answered_source(series)
        self.assertEqual([(x['z'], x['w'], x['src']) for x in series], [(191.5, 1.0, 'dtmp'), (None, 0.0, None), (190.0, 1.0, 'di')])

    def test_a_di_answer_leaves_the_height(self):
        ha.STEP_ANSWERS = [{'xy': (0.0, 0.0), 'use': 'di', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0}]
        series = [{'xy': (10.0, 0.0), 'z': 190.0, 'w': 1.0, 'src': 'di', 'archive': 191.5}]
        ha.answered_source(series)
        self.assertEqual(series[0]['z'], 190.0)
        self.assertIs(ha.step_answer_at((10.0, 0.0)), ha.STEP_ANSWERS[0])  # (met there, and the height left: #418)

    def test_outliers_go_only_within_the_reach(self):
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for x in c.bins:
            x['survey'] = None
        c.bins[10]['z'] += .3
        c.bins[50]['z'] += .3
        ha.STEP_ANSWERS = [{'xy': (52.5, 0.0), 'use': 'di', 'drop': True, 'blend': False, 'radius': None, 'reach': 70.0}]
        self.assertEqual(ha.answered_noise([c])[0], 1)
        self.assertIsNone(c.bins[10]['z'])
        self.assertIsNotNone(c.bins[50]['z'])

    def test_a_noisy_height_takes_the_mean_with_the_survey(self):
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for x in c.bins:
            x['survey'] = 100.0 + .01 * x['s']
        c.bins[10]['z'] += .1
        ha.STEP_ANSWERS = [{'xy': (52.5, 0.0), 'use': 'di', 'drop': False, 'blend': True, 'radius': None, 'reach': 70.0}]
        before = c.bins[10]['z']
        self.assertGreaterEqual(ha.answered_noise([c])[1], 1)
        self.assertLess(c.bins[10]['z'], before)

    def test_the_surveys_pull_makes_no_step_between_bins(self):
        # the survey 20 cm under a noisy stretch: the heights fade towards it, no two neighbours over 5 cm further apart than the grade
        c = chain([(0, 0), (300, 0)], lambda s: 100 + .01 * s)
        for k, x in enumerate(c.bins):
            x['survey'] = 99.8 + .01 * x['s']
            if k % 2:
                x['z'] += .06
        ha.STEP_ANSWERS = [{'xy': (150.0, 0.0), 'use': 'di', 'drop': False, 'blend': True, 'radius': None, 'reach': 70.0}]
        ha.answered_noise([c])
        steps = [abs(b['z'] - a['z'] - .05) for a, b in zip(c.bins, c.bins[1:])]
        self.assertLess(max(steps), .09)
        self.assertLess(c.bins[30]['z'], 100 + .01 * c.bins[30]['s'] - .02)

    def test_a_toward_answer_moves_the_archive_half_way_and_fades_at_its_edge(self):
        # (Malovanka, 2026-11-07: "Let's pick the half option"; the survey and lidar 20 cm over the archive)
        c = chain([(0, 0), (300, 0)], lambda s: 100.0)
        for x in c.bins:
            x['archive'], x['survey'], x['terrain'] = 100.0, 100.2, 100.2
        c.bins[0]['terrain'] = 101.0  # (another level: stays)
        ha.STEP_ANSWERS = [{'xy': (60.0, 0.0), 'use': 'archive', 'drop': False, 'blend': False, 'radius': None, 'reach': 70.0,
                            'toward': {'heights': 'survey+lidar', 'share': 0.5}}]
        ha.answered_toward([c])
        # (s 2.5 on another level, s 62.5 at the answer, s 7.5 and 112.5 in the fade 52.5 m off, s 132.5 past the reach)
        for k, want in ((0, 100.0), (12, 100.1), (1, 100.0875), (22, 100.0875), (26, 100.0)):
            self.assertAlmostEqual(c.bins[k]['z'], want, places=6)
        steps = [abs(b['z'] - a['z']) for a, b in zip(c.bins[1:], c.bins[2:])]
        self.assertLess(max(steps), .03)

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_a_step_answer_replaces_the_radius_answers_in_its_reach(self):
        truth = {'trackHeights': {'radiusAnswers': [{'place': [50.08862, 14.40603], 'answer': ha.HOLD}, {'place': [50.05, 14.4], 'answer': ha.HOLD}],
                                  'stepAnswers': [{'place': [50.08862, 14.40603], 'use': 'archive', 'radius': 'follow'}]}}
        out = ha.load_radius_answers(truth)
        self.assertEqual(sorted(a['answer'] for a in out), [ha.FOLLOW, ha.HOLD])
        self.assertEqual(ha.answer_at([out[-1]['xy']]), None)

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_load_sets_the_answers_where_the_rules_read_them(self):
        names = ('RADIUS_ANSWERS', 'STEP_ANSWERS', 'IGNORE_ANSWERS', 'GROUND_ANSWERS', 'FLOOR_SINCE')
        old = {n: getattr(ha, n) for n in names}
        self.addCleanup(lambda: [setattr(ha, n, v) for n, v in old.items()])
        place = [50.08862, 14.40603]
        ha.load({'trackHeights': {'radiusAnswers': [{'place': place, 'answer': ha.HOLD},
                                                    {'place': place, 'answer': ha.HOLD, 'ignore': 'switches'},
                                                    {'area': [place, [50.0887, 14.4061], [50.0886, 14.4062]], 'answer': ha.FOLLOW}],
                                  'stepAnswers': [{'place': place, 'use': 'archive'}]},
                 'trackGeometry': {'facts': [{'id': 'vertical-radius-min', 'date': '2026-11-07'}]}})
        self.assertEqual([len(ha.RADIUS_ANSWERS), len(ha.STEP_ANSWERS), len(ha.IGNORE_ANSWERS), len(ha.GROUND_ANSWERS)], [2, 1, 1, 1])
        self.assertEqual(ha.FLOOR_SINCE, '2026-11-07')
        self.assertIs(ha.step_answer_at(ha.STEP_ANSWERS[0]['xy']), ha.STEP_ANSWERS[0])

    def test_the_answers_live_in_height_answers_alone(self):
        # (#418: set on line_heights, an answer would sit on a copy that no rule reads, and the tests pass on nothing)
        for n in ('RADIUS_ANSWERS', 'STEP_ANSWERS', 'IGNORE_ANSWERS', 'GROUND_ANSWERS', 'FLOOR_SINCE', 'NEIGHBOUR_LOG', 'LIDAR_LOG'):
            self.assertTrue(hasattr(ha, n), n)
            self.assertFalse(hasattr(lh, n), n)


class Neighbour(unittest.TestCase):
    def tracks(self, f=lambda s: 100 + .02 * s, g=lambda s: 100.3 + .02 * s):
        return chain([(0, 0), (400, 0)], f), chain([(0, 3.5), (400, 3.5)], g)

    def test_a_dip_on_one_track_takes_the_other_tracks_height_and_their_offset(self):
        a, b = self.tracks()
        for k in (40, 41, 42):
            a.bins[k]['z'] -= 1.0
        self.assertEqual(ha.snap_to_neighbour([a, b]), 3)
        for k in (40, 41, 42):
            self.assertAlmostEqual(a.bins[k]['z'], 100 + .02 * a.bins[k]['s'], delta=.01)

    def test_tracks_that_really_differ_stay_apart(self):
        a, b = self.tracks()
        self.assertEqual(ha.snap_to_neighbour([a, b]), 0)
        self.assertAlmostEqual(b.bins[40]['z'] - a.bins[40]['z'], .3, delta=1e-6)

    def test_a_dip_on_both_stays(self):
        a, b = self.tracks()
        for k in (40, 41, 42):
            a.bins[k]['z'] -= 1.0
            b.bins[k]['z'] -= 1.0
        self.assertEqual(ha.snap_to_neighbour([a, b]), 0)

    def test_a_lone_track_stays(self):
        a, _ = self.tracks()
        a.bins[40]['z'] -= 1.0
        self.assertEqual(ha.snap_to_neighbour([a]), 0)


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
        self.assertGreater(ha.archive_over_di([a, b]), 0)
        self.assertLess(max(abs(x['z'] - ground(x['s']) - 0.15) for x in a.bins), ha.SOURCES_EDGE + 1e-9)
        self.assertTrue(all(x['src'] == 'di' for x in b.bins))

    def test_a_hump_on_both_tracks_stays(self):
        # (a rebuild may have raised both tracks since the archive)
        a, b, _ = self.hump(both=True)
        self.assertEqual(ha.archive_over_di([a, b]), 0)

    def test_on_a_structure_dis_height_stays(self):
        a, b, _ = self.hump(flags=['structure_hint'])
        self.assertEqual(ha.archive_over_di([a, b]), 0)


class Held(unittest.TestCase):
    def track(self, archive, survey, held=range(20, 40), flags=()):
        # (#202: a held stretch, the archive and the survey 0.35 m apart, as on line 17 between Čechův most and
        # Strossmayerovo náměstí; around it DI 5 cm over the lidar)
        ground = lambda s: 100 + .01 * s
        c = chain([(0, 0), (300, 0)], lambda s: ground(s) + .05, terrain=ground)
        for k, x in enumerate(c.bins):
            x['src'], x['flags'] = 'di', list(flags)
            x['archive'] = x['survey'] = None
            if k in held:
                x['z'], x['w'], x['src'] = None, 0.0, None
                x['archive'] = None if archive is None else ground(x['s']) + archive
                x['survey'] = None if survey is None else ground(x['s']) + survey
        return c, ground

    def test_the_lidar_picks_the_archive(self):
        c, ground = self.track(.02, -.33)
        self.assertEqual(ha.held_settled([c]), (20, 0, 0))
        self.assertTrue(all(x['src'] == 'dtmp' and abs(x['z'] - ground(x['s']) - .02) < 1e-9 for x in c.bins[20:40]))

    def test_the_lidar_picks_the_survey(self):
        c, _ = self.track(.4, -.03)
        self.assertEqual(ha.held_settled([c]), (20, 0, 0))
        self.assertTrue(all(x['src'] == 'zps' for x in c.bins[20:40]))

    def test_neither_near_the_lidar_stays_held(self):
        c, _ = self.track(.3, -.3)
        self.assertEqual(ha.held_settled([c]), (0, 0, 0))
        self.assertTrue(all(x['z'] is None for x in c.bins[20:40]))

    def test_only_the_lidar_gives_it_with_the_rails_offset_around(self):
        c, ground = self.track(None, None)
        self.assertEqual(ha.held_settled([c]), (0, 20, 0))
        self.assertTrue(all(x['src'] == 'lidar' and abs(x['z'] - ground(x['s']) - .05) < 1e-9 for x in c.bins[20:40]))

    def test_the_lidar_confirms_a_lone_source(self):
        # (#480: line 37 at Palmovka, only the archive, 1-2 cm off the lidar)
        c, ground = self.track(.02, None)
        self.assertEqual(ha.held_settled([c]), (0, 0, 20))
        self.assertTrue(all(x['src'] == 'dtmp' and abs(x['z'] - ground(x['s']) - .02) < 1e-9 for x in c.bins[20:40]))
        c, _ = self.track(None, -.04)
        self.assertEqual(ha.held_settled([c]), (0, 0, 20))
        self.assertTrue(all(x['src'] == 'zps' for x in c.bins[20:40]))
        c, _ = self.track(.3, None)   # (the lidar does not confirm it: held)
        self.assertEqual(ha.held_settled([c]), (0, 0, 0))

    def test_a_lidar_steeper_than_any_track_stays_held(self):
        # (Petřín's funicular: held its whole length, the hill's bare earth stepped 2-6 m)
        c, ground = self.track(None, None)
        for x in c.bins:
            x['terrain'] += .3 * max(0.0, x['s'] - 100)   # (30 % from s 100)
        self.assertEqual(ha.held_settled([c]), (0, 0, 0))

    def test_a_lidar_that_does_not_meet_the_heights_beside_stays_held(self):
        c, _ = self.track(None, None)
        for x in c.bins[20:40]:
            x['terrain'] += 0.6
        self.assertEqual(ha.held_settled([c]), (0, 0, 0))

    def test_on_a_structure_it_stays_held(self):
        # (the bare-earth lidar lies under a deck and over a tunnel)
        c, _ = self.track(None, None, flags=['structure_hint'])
        self.assertEqual(ha.held_settled([c]), (0, 0, 0))


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



class NoLift:
    def at(self, xy):
        return 0.04 if xy and xy[0] > 150 else 0.0


class Surface(unittest.TestCase):
    """Where no source has a height (#480): the surface plus the style's lift, no sample left without one."""

    def test_a_long_hold_takes_the_surface_and_a_short_one_stays_for_the_curve(self):
        held = lambda a, b: (lambda s: None if a <= s <= b else 100.0)  # noqa: E731
        long_, short = chain([(0, 0), (300, 0)], held(50, 200), terrain=lambda s: 100.5), chain([(0, 0), (300, 0)], held(100, 140), terrain=lambda s: 100.5)
        filled, left = lh.surface_fill([long_, short], NoLift())
        got = [(x['s'], x['z'], x['src']) for x in long_.bins if x['src'] == 'surface']
        self.assertEqual(got[0][:2], (52.5, 100.5))
        self.assertEqual(got[-1][:2], (197.5, 100.54))   # (past s 150 the grass lift)
        self.assertTrue(all(x['z'] is None for x in short.bins if 100 <= x['s'] <= 140))
        self.assertEqual((filled, left), (150.0, 0.0))

    def test_not_on_a_steep_hill_and_on_a_structure_the_deck(self):
        steep = chain([(0, 0), (300, 0)], lambda s: None if 50 <= s <= 200 else 100.0, terrain=lambda s: 100 + 0.2 * s)
        deck = chain([(0, 0), (300, 0)], lambda s: None if 50 <= s <= 200 else 100.0, terrain=lambda s: 90.0)
        for x in deck.bins:
            if x['z'] is None:
                x['flags'], x['survey'] = ['structure_hint'], 101.0
        lh.surface_fill([steep, deck], NoLift())
        self.assertTrue(all(x['z'] is None for x in steep.bins if 50 <= x['s'] <= 200))   # (Petřín's funicular)
        self.assertEqual({x['z'] for x in deck.bins if 50 <= x['s'] <= 200}, {101.0})   # (not the lidar under it)

    def test_a_tracks_end_past_its_chain_meets_its_own_height(self):
        zs = [None, None, 101.0, 101.2, None, None, None, 101.4]
        filled = lh.fill_gaps([(0, 0), (14, 0)], zs, srcs := ['x'] * 8, lambda xy: 100.0 + xy[0] * 0.01)
        self.assertEqual(filled, 10.0)
        # (an end: the shift at the one side, the surface's slope kept; between: the shifts at both sides, linear)
        self.assertEqual(zs[:2], [100.96, 100.98])
        self.assertEqual(zs[4:7], [101.25, 101.3, 101.35])
        self.assertEqual(srcs, ['surface', 'surface', 'x', 'x', 'surface', 'surface', 'surface', 'x'])


class Workers(unittest.TestCase):
    def test_first_solves_in_workers_as_in_one_process(self):
        """#511: the chains' first solves side by side in worker processes give what one process gives, with the answers
        this process holds (a 'hold' answer at a crossing), and the pinned pass after them the same pins."""
        def network():
            out = [chain([(0, 40 * k), (400, 40 * k)], lambda s, k=k: 101 + .001 * k * (s - 200) + (.3 if 150 < s < 160 else 0))
                   for k in range(18)]  # (each at 101 m where the long track crosses it: pinned there)
            return out + [chain([(200, -50), (200, 18 * 40)], lambda s: 101.0)]  # (crossing them all)
        saved = ha.RADIUS_ANSWERS
        self.addCleanup(setattr, ha, 'RADIUS_ANSWERS', saved)
        ha.RADIUS_ANSWERS = [{'xy': (200.0, 80.0), 'answer': ha.HOLD}]
        one, many = network(), network()
        with mock.patch.object(lh, 'POOL', 10 ** 6):
            a = quiet(lh.assemble, one)
        with mock.patch.object(lh, 'POOL', 2):
            b = quiet(lh.assemble, many)
        self.assertEqual(a['pinned'], 18)
        self.assertEqual(a['pinned'], b['pinned'])
        for x, y in zip(one, many):
            self.assertEqual(len(x.runs), len(y.runs))
            for p, q in zip(x.runs, y.runs):
                self.assertEqual(p['s'], q['s'])
                for u, v in zip(p['z'], q['z']):  # (one BLAS thread in the workers: equal to its last bits, or nearly)
                    self.assertAlmostEqual(u, v, places=9)
            self.assertEqual((len(x.review), len(x.dropped), len(x.apart), x.held), (len(y.review), len(y.dropped), len(y.apart), y.held))


class Kept(unittest.TestCase):
    def test_runs_kept_as_solved_again(self):
        """#516: a run whose points are as at an earlier solve of its chain keeps what it found then: the network's
        heights to their last bit as when every run is solved again (one process), and some runs were kept."""
        def network():
            out = [chain([(0, 40 * k), (1000, 40 * k)], lambda s, k=k: 101 + .001 * k * (s - 200) + (.3 if 150 < s < 160 else 0))
                   for k in range(6)]  # (solved first: the longest)
            # (a track crossing them, its runs cut by a held stretch: the far one has no pins)
            far = lambda s: None if 300 < s < 420 else 101.0 + .002 * (s - 300) * (s > 420)  # noqa: E731
            return out + [chain([(200, -50), (200, 6 * 40 + 400)], far)]
        saved = ha.RADIUS_ANSWERS
        self.addCleanup(setattr, ha, 'RADIUS_ANSWERS', saved)
        ha.RADIUS_ANSWERS = [{'xy': (200.0, 80.0), 'answer': ha.HOLD}]
        solved = [0]
        run = lh.solve_run

        def counted(*a):
            solved[0] += 1
            return run(*a)
        with mock.patch.object(lh, 'POOL', 10 ** 6), mock.patch.object(lh, 'solve_run', counted):
            kept_net = network()
            a = quiet(lh.assemble, kept_net)
            n_kept = solved[0]
            fresh_net, keys = network(), iter(range(10 ** 9))
            with mock.patch.object(lh, '_key', lambda run: next(keys)):
                b = quiet(lh.assemble, fresh_net)
            n_fresh = solved[0] - n_kept
        self.assertEqual(a, b)
        self.assertLess(n_kept, n_fresh)
        for x, y in zip(kept_net, fresh_net):
            self.assertEqual((x.runs, x.held, x.steps, x.review, x.dropped, x.apart),
                             (y.runs, y.held, y.steps, y.review, y.dropped, y.apart))


if __name__ == '__main__':
    unittest.main()
