# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the paved track against IPR measure (tools/bench/paved_ipr.py, #539): python -P -E tools/test_paved_ipr.py"""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'bench'))
import paved_ipr as pi  # noqa: E402


class Flat:
    """IPR as a level ground at 100 m."""
    def sample(self, E, N):
        return np.full(np.shape(E), 100.0)


def line(dips, staged, areas=()):
    """A straight 300 m route along x; the rails 0.2 m under the ground over each (s0, s1) of `dips`; staged heights as
    given ([s, z]); the archive named as the source throughout."""
    s = np.arange(151) * 2.0
    z = np.full(len(s), 100.0)
    for a, b in dips:
        z[(s >= a) & (s <= b)] = 99.8
    d = {'path': [[0, 0], [300, 0]], 'heights': {'step': 2.0, 'path': z.tolist(), 'staged': {'path': staged}},
         'heightSource': {'path': [[0, 300, 'dtmp']]}}
    return pi.measure_data('t', d, list(areas), Flat())


def tram(x0, x1, z):
    """A survey area along the track at height z."""
    return {'c': 'tram', 'l': 0, 'r': [[x0, -3, z], [x1, -3, z], [x1, 3, z], [x0, 3, z]]}


class Measure(unittest.TestCase):
    def test_a_source_under_ipr_holds_the_track_there(self):
        r = line([(50, 100)], [[s, 99.8] for s in range(50, 101, 5)])
        (run,) = r['runs']
        self.assertEqual((run['s0'], run['s1'], run['cause']), (50, 100, 'held, no survey'))
        self.assertAlmostEqual(run['worst'], -0.2)
        self.assertEqual(r['under_m'], 52)

    def test_the_survey_says_which_of_the_two_is_apart(self):
        held = [[s, 99.8] for s in range(50, 101, 5)]
        self.assertEqual(line([(50, 100)], held, [tram(40, 110, 99.82)])['runs'][0]['cause'], 'held, survey with the source')
        self.assertEqual(line([(50, 100)], held, [tram(40, 110, 99.98)])['runs'][0]['cause'], 'held, survey with IPR')

    def test_a_curve_under_its_staged_heights_did_not_follow_them(self):
        (run,) = line([(150, 200)], [[s, 100.0] for s in range(150, 201, 5)])['runs']
        self.assertEqual(run['cause'], 'radius')

    def test_short_or_shallow_stretches_are_not_runs(self):
        self.assertEqual(line([(250, 252)], [])['runs'], [])     # (4 m)
        r = line([], [])
        self.assertEqual((r['runs'], r['under_m']), ([], 0))

    def test_along_samples_the_route_every_step(self):
        s, xy, d = pi.along([[0, 0], [10, 0], [10, 10]], 2.0, 11)
        self.assertEqual(xy[5].tolist(), [10.0, 0.0])
        self.assertEqual(xy[8].tolist(), [10.0, 6.0])
        self.assertEqual(d[8].tolist(), [0.0, 1.0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
