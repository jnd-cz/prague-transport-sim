# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the cell lattice: python -I tools/test_geo_cells.py"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo_cells as gc  # noqa: E402


class Cells(unittest.TestCase):
    ROUTE = [(0.0, 10.0), (3000.0, 40.0), (3100.0, 2000.0)]

    def test_every_point_of_the_corridor_is_in_a_cell(self):
        have = set(gc.cells(self.ROUTE, 220.0))
        for x, y in ((0, 230), (0, -210), (1500, 245), (2999, -190), (3320, 1000), (2885, 1000), (3100, 2220)):
            self.assertIn((x // gc.SIZE, y // gc.SIZE), {(float(a), float(b)) for a, b in have}, (x, y))

    def test_a_cell_is_the_same_place_whatever_the_route(self):
        self.assertEqual(gc.bounds(-2, 3), (-1000.0, 1500.0, -500.0, 2000.0))

    def test_a_small_route_change_asks_for_few_new_cells(self):
        # (with boxes numbered along the route, 2 m less at its start renamed every later answer, #320)
        moved = [(x + 2.0, y + 2.0) for x, y in self.ROUTE]
        old, new = set(gc.cells(self.ROUTE, 220.0)), set(gc.cells(moved, 220.0))
        self.assertLessEqual(len(new - old), 2)
        shorter = [(x, y) for x, y in self.ROUTE[:2]] + [(3100.0, 1990.0)]
        self.assertEqual(set(gc.cells(shorter, 220.0)) - old, set())

    def test_a_long_segment_passes_over_no_cell(self):
        got = gc.cells([(0.0, 0.0), (5000.0, 0.0)], 10.0)
        self.assertEqual({ix for ix, _ in got}, set(range(-1, 11)))

    def test_cells_are_sorted_and_unique(self):
        got = gc.cells(self.ROUTE, 220.0)
        self.assertEqual(got, sorted(set(got)))


if __name__ == "__main__":
    unittest.main()
