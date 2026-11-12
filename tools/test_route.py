# SPDX-License-Identifier: AGPL-3.0-or-later
"""The run past the termini (tools/route.py, #477): python -I tools/test_route.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route import RUN, extend, path_ext  # noqa: E402


def length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


class Run(unittest.TestCase):
    def test_no_track_goes_straight_on(self):
        ext = extend([], [[0, 0], [10, 0]])
        self.assertEqual(ext["before"], [(-RUN, 0.0)])
        self.assertEqual(ext["after"], [(10 + RUN, 0.0)])

    def test_follows_the_chain_and_runs_its_length(self):
        # a track curving left past the end: the run follows it for 60 m
        arc = [(10 + 20 * math.sin(a / 20), 20 - 20 * math.cos(a / 20)) for a in range(0, 41, 2)]
        ext = extend([arc], [[0, 0], [10, 0]])
        after = [(10, 0)] + ext["after"]
        self.assertAlmostEqual(length(after), RUN, places=6)
        self.assertAlmostEqual(ext["after"][0][0], arc[1][0], places=9)  # on the arc's points, not straight on
        # past the arc's end (40 m) it goes straight on along the arc's last direction
        self.assertGreater(ext["after"][-1][1], 10)

    def test_before_runs_towards_the_path(self):
        ext = extend([[(-50, 0), (0, 0)]], [[0, 0], [10, 0]])
        xs = [p[0] for p in ext["before"]]
        self.assertEqual(xs, sorted(xs))  # ordered towards the path's start
        self.assertAlmostEqual(xs[0], -RUN)

    def test_a_chain_drawn_the_other_way_is_walked_backwards(self):
        ext = extend([[(70, 0), (40, 0), (10, 0)]], [[0, 0], [10, 0]])
        self.assertEqual(ext["after"], [(40, 0), (70, 0)])

    def test_the_most_aligned_branch_wins_at_a_fork(self):
        straight = [(10, 0), (80, 0)]
        branch = [(10, 0), (60, 40)]  # 39° off
        ext = extend([branch, straight], [[0, 0], [10, 0]])
        self.assertTrue(all(abs(p[1]) < 1e-9 for p in ext["after"]))

    def test_a_track_across_the_end_is_not_taken(self):
        ext = extend([[(10, -30), (10, 30)]], [[0, 0], [10, 0]])
        self.assertEqual(ext["after"], [(10 + RUN, 0.0)])

    def test_path_ext_rounds_as_the_build(self):
        data = {"tracks": [{"p": [[10, 0], [33.33333, 0]]}], "path": [[0, 0], [10, 0]]}
        ext = path_ext(data, 3)
        self.assertEqual(ext["after"], [[33.333, 0.0], [70.0, 0.0]])
        self.assertEqual(ext["before"], [[-60.0, 0.0]])


if __name__ == "__main__":
    unittest.main()
