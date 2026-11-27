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


def line(dips, staged, areas=(), humps=(), styles=(), track='paved'):
    """A straight 300 m route along x; the rails 0.2 m under the ground over each (s0, s1) of `dips` and 0.5 m over it
    over each of `humps`; staged heights as given ([s, z]); the archive named as the source throughout."""
    s = np.arange(151) * 2.0
    z = np.full(len(s), 100.0)
    for a, b in dips:
        z[(s >= a) & (s <= b)] = 99.8
    for a, b in humps:
        z[(s >= a) & (s <= b)] = 100.5
    d = {'path': [[0, 0], [300, 0]], 'heights': {'step': 2.0, 'path': z.tolist(), 'staged': {'path': staged}},
         'heightSource': {'path': [[0, 300, 'dtmp']]}, 'styles': [{'s0': a, 's1': b, 'style': st} for a, b, st in styles]}
    return pi.measure_data('t', d, list(areas), Flat(), track)


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

    def test_a_track_over_ipr_is_a_run_with_its_source_and_the_street_beside(self):
        # (#539, line 9 at Bertramka: the archive up to 0.9 m over the lidar for 200 m, the street level across)
        r = line([], [], [tram(40, 110, 100.3)], humps=[(50, 100)])
        (run,) = r['over_runs']
        self.assertEqual((run['s0'], run['s1'], run['sources'], run['sides_minus_centre']), (50, 100, ['dtmp'], 0.0))
        self.assertAlmostEqual(run['survey_minus_ipr'], 0.3)
        self.assertAlmostEqual(run['worst'], 0.5)
        self.assertEqual((r['over_m'], r['over_by_source'], r['runs']), (52, {'dtmp': 52}, []))

    def test_a_short_stretch_over_ipr_is_no_run(self):
        self.assertEqual(line([], [], humps=[(50, 56)])['over_runs'], [])   # (8 m)

    def test_grass_track_is_measured_apart(self):
        # (#876, Bělohorská: the archive's records 0.2-0.45 m under the lidar on grass track, which the paved measure
        # leaves out; the lidar reads the lawn at the rail heads)
        held, styles = [[s, 99.8] for s in range(50, 101, 5)], [(40, 120, 'grass'), (200, 260, 'ballast')]
        r = line([(50, 100), (210, 250)], held, styles=styles)
        self.assertEqual((r['runs'], r['paved_km']), ([], 0.2))
        r = line([(50, 100), (210, 250)], held, styles=styles, track='grass')
        (run,) = r['runs']
        self.assertEqual((run['s0'], run['s1'], run['cause'], r['paved_km']), (50, 100, 'held, no survey', 0.1))
        self.assertEqual(line([], [], track='grass')['runs'], [])   # (a line with no grass track)

    def test_along_samples_the_route_every_step(self):
        s, xy, d = pi.along([[0, 0], [10, 0], [10, 10]], 2.0, 11)
        self.assertEqual(xy[5].tolist(), [10.0, 0.0])
        self.assertEqual(xy[8].tolist(), [10.0, 6.0])
        self.assertEqual(d[8].tolist(), [0.0, 1.0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
