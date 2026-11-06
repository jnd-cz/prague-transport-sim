"""The step review's rules (tools/track_steps.py): python -I tools/test_track_steps.py"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import track_steps as ts  # noqa: E402


def heights(f, length=400.0, step=2.0):
    return [f(i * step) for i in range(int(length / step) + 1)]


class CouplingSteps(unittest.TestCase):
    def largest(self, z):
        return max(abs(d) for _, d in ts.coupling_steps(z, 2.0))

    def test_a_constant_grade_has_none(self):
        self.assertLess(self.largest(heights(lambda s: 0.06 * s)), 1e-9)

    def test_a_constant_curve_has_none(self):
        self.assertLess(self.largest(heights(lambda s: s * s / 1000)), 1e-3)

    def test_a_wave_of_two_car_lengths_has_one(self):
        self.assertGreater(self.largest(heights(lambda s: 0.02 * math.sin(2 * math.pi * s / 30))), 0.03)

    def test_a_kink_is_listed_with_its_place(self):
        z = heights(lambda s: 200 + (1.0 if s > 200 else 0.0))
        found = ts.line_steps('22', {'heights': {'path': z, 'step': 2.0}, 'path': [[0, 0], [400, 0]]})
        self.assertEqual(len(found), 1)
        self.assertAlmostEqual(found[0]['x'], 200, delta=20)

    def test_nulls_split_the_runs(self):
        self.assertEqual(ts.runs_of([None, 1, 2, None, None, 3]), [(1, 3), (5, 6)])


class Jumps(unittest.TestCase):
    def test_a_segment_steeper_than_any_track_is_a_jump(self):
        g = {'dataset': 'di', 'id': 7, 'xy': [[0, 0], [4, 0], [24, 0]], 'raw_z': [190.0, 191.4, 191.6]}
        self.assertEqual(len(ts.di_jumps([g])), 1)

    def test_a_steep_track_short_or_without_heights_is_none(self):
        steep = {'dataset': 'di', 'id': 1, 'xy': [[0, 0], [20, 0]], 'raw_z': [190.0, 191.6]}          # 8 %
        short = {'dataset': 'di', 'id': 2, 'xy': [[0, 0], [1, 0]], 'raw_z': [190.0, 191.0]}            # 1 m
        empty = {'dataset': 'di', 'id': 3, 'xy': [[0, 0], [4, 0]], 'raw_z': [0, 191.4]}                # Z = 0
        self.assertEqual(ts.di_jumps([steep, short, empty]), [])


class Merging(unittest.TestCase):
    def test_places_near_the_largest_are_one_card(self):
        groups = ts.merged([{'x': 0, 'y': 0, 'cm': 5}, {'x': 30, 'y': 0, 'cm': 80}, {'x': 500, 'y': 0, 'cm': 12}])
        self.assertEqual([len(g) for g in groups], [2, 1])
        self.assertEqual(groups[0][0]['cm'], 80)


if __name__ == '__main__':
    unittest.main()
