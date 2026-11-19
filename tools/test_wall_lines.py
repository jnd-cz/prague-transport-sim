# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/wall_lines.py: the survey's wall lines as stretches with a level on either side, and tools/ground_mesh.py
hold_at_walls: the corners beside a stretch at their side's level (#697).

    python -P -E tools/test_wall_lines.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_mesh as gm  # noqa: E402
import wall_lines as wl  # noqa: E402


def quay(x, y, top=196.9, foot=188.6, at=0.0, smear=1.0):
    """A raster like IPR's across a wall along the y axis at x = `at`: the top to its left (x < at), the foot to its
    right, the step spread over `smear` m either side."""
    t = np.clip((np.asarray(x, float) - at + smear) / (2 * smear), 0, 1)
    return top + (foot - top) * t


class Stretches(unittest.TestCase):
    def test_a_wall_line_across_a_step_is_one_stretch_with_its_two_levels(self):
        # (the line runs north: its left is west, the top)
        line = np.array([[0.0, 0.0, 188.58], [0.0, 30.0, 188.58]])
        st = wl.of_lines([line], quay)
        self.assertEqual(len(st), 1)
        s = st[0]
        self.assertAlmostEqual(float(np.hypot(*(s["p"][-1] - s["p"][0]))), 30.0)
        self.assertTrue(np.allclose(s["zl"], 196.9))
        self.assertTrue(np.allclose(s["zr"], 188.58))  # (the line's own height: the survey's reading of the foot)

    def test_the_sides_follow_the_lines_direction(self):
        st = wl.of_lines([np.array([[0.0, 30.0, np.nan], [0.0, 0.0, np.nan]])], quay)  # (running south: its left is east)
        self.assertTrue(np.allclose(st[0]["zl"], 188.6) and np.allclose(st[0]["zr"], 196.9))

    def test_a_wall_on_level_ground_is_no_stretch(self):
        flat = lambda x, y: np.full(np.shape(x), 200.0)  # noqa: E731
        self.assertEqual(wl.of_lines([np.array([[0.0, 0.0, 201.5], [0.0, 30.0, 201.5]])], flat), [])
        kerb = lambda x, y: np.where(np.asarray(x) < 0, 200.15, 200.0)  # noqa: E731
        self.assertEqual(wl.of_lines([np.array([[0.0, 0.0, 200.0], [0.0, 30.0, 200.0]])], kerb), [])

    def test_a_wall_stepped_along_part_of_it_is_cut_to_that_part(self):
        def half(x, y):  # (a step south of y = 20 only)
            return np.where(np.asarray(y) < 20, quay(x, y), 196.9)
        st = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 40.0, np.nan]])], half)
        self.assertEqual(len(st), 1)
        self.assertAlmostEqual(float(st[0]["p"][-1][1]), 19.0, delta=1.01)

    def test_the_high_side_reads_past_the_smear(self):
        """IPR spreads the step over 2 m and more: SIDE alone read the quay's top 0.5-2.7 m low in places."""
        wide = lambda x, y: quay(x, y, smear=2.2)  # noqa: E731
        s = wl.of_lines([np.array([[0.0, 0.0, np.nan], [0.0, 30.0, np.nan]])], wide)[0]
        self.assertTrue(np.allclose(s["zl"], 196.9) and np.allclose(s["zr"], 188.6))

    def test_runs_close_small_gaps_and_drop_short_ones(self):
        d = np.arange(12.0)
        on = np.array([1, 1, 1, 0, 1, 1, 0, 0, 0, 0, 1, 0], bool)
        self.assertEqual(wl.runs(on, d), [(0, 5)])


class Hold(unittest.TestCase):
    WALL = [{"p": np.array([[0.0, 0.0], [0.0, 30.0]]), "zl": np.array([196.9, 196.9]), "zr": np.array([188.6, 188.6])}]

    def test_corners_on_and_beside_the_line_take_their_sides_level(self):
        #          on the line, twice     1 m west    1 m east    3 m west (past the hold)
        cx = np.array([0.0, 0.0, -1.0, 1.0, -3.0])
        cy = np.full(5, 10.0)
        tx = np.array([-0.5, 0.5, -1.2, 1.2, -3.2])  # (their triangles' centres)
        z = np.array([192.0, 192.0, 195.0, 190.0, 196.8])
        got, held = gm.hold_at_walls(cx, cy, tx, cy, z, np.ones(5, bool), self.WALL)
        self.assertEqual(got.tolist(), [196.9, 188.6, 196.9, 188.6, 196.8])
        self.assertEqual(held.tolist(), [True, True, True, True, False])

    def test_only_eligible_corners_move(self):
        cx, cy = np.array([0.0, 0.0]), np.array([10.0, 10.0])
        got, held = gm.hold_at_walls(cx, cy, np.array([-0.5, -0.5]), cy, np.array([192.0, 192.0]), np.array([True, False]), self.WALL)
        self.assertEqual(got.tolist(), [196.9, 192.0])
        self.assertEqual(gm.hold_at_walls(cx, cy, cx, cy, np.array([1.0, 2.0]), np.ones(2, bool), [])[0].tolist(), [1.0, 2.0])

    def test_the_level_runs_along_a_sloping_wall(self):
        wall = [{"p": np.array([[0.0, 0.0], [0.0, 10.0]]), "zl": np.array([200.0, 202.0]), "zr": np.array([195.0, 195.0])}]
        got, _ = gm.hold_at_walls(np.array([-0.5]), np.array([2.5]), np.array([-0.6]), np.array([2.5]), np.array([0.0]), np.ones(1, bool), wall)
        self.assertAlmostEqual(float(got[0]), 200.5)


if __name__ == "__main__":
    unittest.main(verbosity=1)
