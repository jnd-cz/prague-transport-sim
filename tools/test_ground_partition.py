# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_partition.py: the survey's overlaps, the bed union, the plot height and the terrain cut (#507).

    python -P -E tools/test_ground_partition.py
"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_partition as gp  # noqa: E402


class Frame:
    E0 = N0 = 0.0


class Ipr:
    """IPR's ground as a function of x, y."""

    def __init__(self, f):
        self.f = f

    def sample(self, E, N):
        return self.f(np.asarray(E, float), np.asarray(N, float))


def sq(x0, y0, x1, y1, z=0.0):
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


class Survey(unittest.TestCase):
    def test_higher_rank_holds_the_overlap(self):
        D = {"areas": [{"c": "green", "l": 0, "r": sq(0, 0, 10, 10)}, {"c": "road", "l": 0, "r": sq(5, 0, 15, 10)}]}
        p = gp.survey_pieces(D, shapely.box(-100, -100, 100, 100))
        by = {q["c"]: q["g"].area for q in p}
        self.assertAlmostEqual(by["road"], 100)
        self.assertAlmostEqual(by["green"], 50)

    def test_smaller_wins_between_equal_ranks_and_not_ground_left_out(self):
        D = {"areas": [{"c": "road", "l": 0, "r": sq(0, 0, 10, 10)}, {"c": "road", "l": 0, "r": sq(2, 2, 4, 4)},
                       {"c": "wall", "l": 0, "r": sq(0, 0, 1, 1)}, {"c": "road", "l": 1, "r": sq(0, 0, 3, 3)}]}
        p = gp.survey_pieces(D, shapely.box(-100, -100, 100, 100))
        self.assertEqual(sorted(round(q["g"].area) for q in p), [4, 96])
        self.assertEqual({q["area"] for q in p}, {0, 1})

    def test_clipped_to_the_box(self):
        D = {"areas": [{"c": "road", "l": 0, "r": sq(-5, 0, 5, 10)}]}
        self.assertAlmostEqual(gp.survey_pieces(D, shapely.box(0, 0, 100, 100))[0]["g"].area, 50)


def track(p, n, z=0.0, w=200):
    return {"p": p, "zs": [z] * n if np.isscalar(z) else list(z), "bed": {"l": [w] * n, "r": [w] * n, "meet": [0] * n}}


class Beds(unittest.TestCase):
    def line(self, tracks):
        return {"path": [[0, -50], [0, 50]], "tracks": tracks, "lift": {"step": 2, "unit": 0.001, "v": [0] * 60}}

    def test_overlapping_beds_merge_into_one(self):
        L = self.line([track([[0, 0], [20, 0]], 11), track([[10, -1], [30, 1]], 11)])
        B, outs = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: x * 0), Frame())
        self.assertEqual(len(outs), 2)
        self.assertEqual(len(shapely.get_parts(B)), 1)
        self.assertGreater(B.area, 4 * 30 - 1)

    def test_samples_on_a_structure_left_out(self):
        # (a bridge: the rails 6 m over IPR's ground in the middle of the track)
        z = [0.0] * 4 + [6.0] * 3 + [0.0] * 4
        log = {}
        L = self.line([track([[0, 0], [20, 0]], 11, z)])
        B, _ = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: x * 0), Frame(), log)
        self.assertEqual(len(shapely.get_parts(B)), 2)
        self.assertAlmostEqual(B.area, 4 * 12, places=3)  # (three 2 m stretches on each side kept, four left out)
        self.assertEqual(log["samples on structures, left out"], 3)

    def test_outline_keep_mask(self):
        import track_beds
        tr = track([[0, 0], [10, 0]], 6)
        full = track_beds.outline(tr, tr["bed"])
        part = track_beds.outline(tr, tr["bed"], keep=[True, True, True, False, False, False])
        self.assertAlmostEqual(full.area, 40, places=3)
        self.assertAlmostEqual(part.area, 16, places=3)


class Plots(unittest.TestCase):
    def test_height_is_the_median_around_the_footprint(self):
        g = shapely.box(0, 0, 10, 10)
        z = gp.plot_height(g, Ipr(lambda x, y: x), Frame())
        self.assertAlmostEqual(z, 5.0, delta=0.3)

    def test_cut_by_the_classes_above_and_earlier_footprints(self):
        L = {"buildings": [{"p": [[0, 0], [10, 0], [10, 10], [0, 10]], "h": 9, "k": "yes"},
                           {"p": [[5, 0], [15, 0], [15, 10], [5, 10]], "h": 9, "k": "yes"}]}
        above = shapely.box(0, 0, 2, 10)
        p = gp.plot_pieces(L, shapely.box(-100, -100, 100, 100), above, Ipr(lambda x, y: x * 0 + 200), Frame())
        self.assertEqual([round(q["g"].area) for q in p], [80, 50])
        self.assertEqual([q["z"] for q in p], [200.0, 200.0])


class Terrain(unittest.TestCase):
    def setUp(self):
        self.x = np.array([0, 10, 10, 0], float)
        self.y = np.array([0, 0, 10, 10], float)
        self.T = np.array([[0, 1, 2], [0, 2, 3]])
        self.box = shapely.box(0, 0, 10, 10)

    def test_cut_kept_and_areas(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.box(6, 1, 8, 3), self.box, threads=1)
        self.assertEqual((r["cut"], r["kept"], r["dropped"]), (1, 1, 0))
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 96, places=6)

    def test_dropped_under_the_cover(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.box(-1, -1, 11, 5).union(shapely.box(5, -1, 11, 11)),
                           self.box, threads=1)
        self.assertEqual(r["dropped"], 1)
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 100 - 50 - 25, places=6)

    def test_cut_by_the_box(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.Polygon(), shapely.box(0, 0, 5, 10), threads=1)
        self.assertEqual(r["cut"], 2)
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 50, places=6)


if __name__ == "__main__":
    unittest.main()
