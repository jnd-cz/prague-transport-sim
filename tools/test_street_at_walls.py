# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/bench/street_at_walls.py: the street's corners at walls and stairs against their own street (#653).

    python -P -E tools/test_street_at_walls.py
"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "bench"))
import street_at_walls as saw  # noqa: E402


def rect(c, x0, y0, x1, y1, z, extra=()):
    """A level-0 area's outline, anticlockwise, with points `extra` [(x, y, z)] on its south edge (y0)."""
    south = sorted([(x0, y0, z), *extra, (x1, y0, z)])
    return {"c": c, "l": 0, "r": [list(p) for p in south] + [[x1, y1, z], [x0, y1, z]]}


def street(z=200.0, low=None):
    """The sidewalk's ground over y 1..5 as a grid (V in mm, F) and its corners P (m): every vertex at z, the one at
    (5, 1) at `low` where given."""
    xs, ys = [0.0, 4.0, 5.0, 6.0, 10.0], [1.0, 1.2, 3.0, 5.0]
    P = np.array([[x, y, z] for y in ys for x in xs], float)
    if low is not None:
        P[2, 2] = low
    F = []
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            a, b, c, d = j * len(xs) + i, j * len(xs) + i + 1, (j + 1) * len(xs) + i + 1, (j + 1) * len(xs) + i
            F += [[a, b, c], [a, c, d]]
    return np.round(P * 1000).astype(np.int64), np.array(F), P


class AtWalls(unittest.TestCase):
    # (a wall along y 0..1 and a sidewalk north of it, sharing the line y = 1)
    def test_a_corner_off_its_street_is_counted_and_one_on_it_is_not(self):
        D = {"areas": [rect("wall", 0, 0, 10, 1, 200.0), rect("sidewalk", 0, 1, 10, 5, 200.0)]}
        V, F, P = street(low=196.0)
        rows, n = saw.measure(D, V, F, P)
        self.assertEqual(n, 5)  # (the corners on the wall's outline: x 0, 4, 5, 6, 10 at y = 1)
        bad = [r for r in rows if r["off"] > saw.OFF]
        self.assertEqual([(r["at"], r["off"]) for r in bad], [([5.0, 1.0], 4.0)])
        V, F, P = street()
        self.assertEqual([r for r in saw.measure(D, V, F, P)[0] if r["off"] > saw.OFF], [])

    def test_a_corner_at_its_own_outline_height_is_none(self):
        # (a ramp from the wall's end: the survey has the corner at 196 m in both outlines, Krejcárek's sidewalk 284)
        D = {"areas": [rect("wall", 0, 0, 10, 1, 200.0), rect("sidewalk", 0, 1, 10, 5, 200.0, [(5.0, 1.0, 196.0)])]}
        V, F, P = street(low=196.0)
        self.assertEqual([r for r in saw.measure(D, V, F, P)[0] if r["off"] > saw.OFF], [])

    def test_an_area_on_both_sides_of_a_wall_is_read_on_the_corners_side(self):
        # (Modřany's wall 7821, line 17 (-2455, -8516): one sidewalk on both sides of a low wall 0.3 m thick standing in
        # it, its south part at 196 m, its north part at 200 m; each side's corners at their side's level. 0.5 m in from
        # the south edge lies past the wall, on the north part)
        xs = [0.0, 4.0, 5.0, 6.0, 10.0]
        rows_ = [(-5.0, 196.0), (-3.0, 196.0), (-0.2, 196.0), (0.0, 196.0), (0.3, 200.0), (1.2, 200.0), (3.0, 200.0), (5.0, 200.0)]
        P = np.array([[x, y, z] for y, z in rows_ for x in xs], float)
        F = []
        for j in (0, 1, 2, 4, 5, 6):  # (the two parts' rows, nothing over the wall)
            for i in range(len(xs) - 1):
                a, b, c, d = j * len(xs) + i, j * len(xs) + i + 1, (j + 1) * len(xs) + i + 1, (j + 1) * len(xs) + i
                F += [[a, b, c], [a, c, d]]
        wall = {"c": "wall", "l": 0, "r": [[0, 0, 196.0], [10, 0, 196.0], [10, 0.3, 200.0], [0, 0.3, 200.0]]}
        walk = {"c": "sidewalk", "l": 0, "r": [[-1, -5, 196.0], [11, -5, 196.0], [11, 5, 200.0], [-1, 5, 200.0]],
                "h": [[[0, 0, 200.0], [0, 0.3, 200.0], [10, 0.3, 200.0], [10, 0, 200.0]]]}  # (the hole at the top's height, as shared lines are)
        rows, n = saw.measure({"areas": [wall, walk]}, np.round(P * 1000).astype(np.int64), np.array(F), P)
        self.assertEqual(n, 10)
        self.assertEqual([r for r in rows if r["off"] > saw.OFF], [])

    def test_a_street_at_the_foot_whose_outline_has_the_top_is_none(self):
        # (Hořejší nábřeží: the street at the wall's foot, its outline and the wall's at the top's height)
        D = {"areas": [rect("wall", 0, 0, 10, 1, 193.8), rect("sidewalk", 0, 1, 10, 5, 193.8)]}
        V, F, P = street(z=187.5)
        rows, _ = saw.measure(D, V, F, P)
        self.assertTrue(rows)
        self.assertEqual([r for r in rows if r["off"] > saw.OFF], [])


if __name__ == "__main__":
    unittest.main()
