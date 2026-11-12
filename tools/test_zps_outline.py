# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street outlines where survey and lidar disagree (#470): python -P -E tools/test_zps_outline.py"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zps_outline as zo  # noqa: E402

GRADE = 0.04  # a street rising 4 % along x


def plane(x, y):
    return 200.0 + GRADE * np.asarray(x, float)


def road(zs=None, cls="road", y0=0.0):
    """A road 6 m wide along x, its kerb edge y = y0 with a vertex every 5 m from 0 to 60 m (heights: the plane, or zs)."""
    xs = np.arange(0, 61, 5.0)
    zs = plane(xs, 0) if zs is None else np.asarray(zs, float)
    edge = [[float(x), y0, round(float(z), 2)] for x, z in zip(xs, zs)]
    far = [[60.0, y0 - 6, round(float(plane(60, 0)), 2)], [0.0, y0 - 6, round(float(plane(0, 0)), 2)]]
    return {"c": cls, "l": 0, "r": edge + far}


def heights(a):
    return [q[2] for q in a["r"][:13]]


class Outline(unittest.TestCase):
    def test_a_run_on_another_line_takes_the_lidar(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[5:8] += 1.2  # (three vertices on a wall's top line)
        a = road(zs)
        rep = zo.correct([a], plane)
        self.assertEqual(rep["places"], 3)
        np.testing.assert_allclose(heights(a), plane(np.arange(0, 61, 5.0), 0), atol=0.011)

    def test_a_lone_vertex_off_its_kerb_takes_the_lidar_and_the_rest_stay(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[6] -= 0.15
        a = road(zs)
        before = heights(a)
        zo.correct([a], plane)
        after = heights(a)
        self.assertAlmostEqual(after[6], float(plane(30, 0)), delta=0.011)
        self.assertEqual(before[:6] + before[7:], after[:6] + after[7:])

    def test_scatter_under_its_threshold_stays(self):
        zs = plane(np.arange(0, 61, 5.0), 0) + np.array([0.03, -0.02, 0.03, 0, -0.03, 0.02, 0.04, -0.02, 0, 0.03, -0.03, 0, 0.02])  # (within 7 cm of each other)
        a = road(zs)
        self.assertEqual(zo.correct([a], plane)["places"], 0)

    def test_a_shape_the_lidar_sees_too_stays(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[6] -= 0.15  # (a lowered kerb, a driveway: in both)

        def ground(x, y):
            x = np.asarray(x, float)
            return plane(x, y) - 0.15 * np.clip(1 - np.abs(x - 30) / 1.5, 0, 1)
        a = road(zs)
        self.assertEqual(zo.correct([a], ground)["places"], 0)

    def test_the_offset_comes_from_the_vertices_that_agree_with_the_lidar(self):
        # a sidewalk's foot line 8 cm under IPR inside it, with a long run 1.5 m up: the run comes down to the foot line,
        # not the others up to the run
        zs = plane(np.arange(0, 61, 5.0), 0) - 0.08
        zs[3:9] += 1.5
        a = road(zs, cls="sidewalk")
        zo.correct([a], plane)
        np.testing.assert_allclose(heights(a), plane(np.arange(0, 61, 5.0), 0) - 0.08, atol=0.011)

    def test_kept_under_a_cover_in_a_held_area_and_on_paved(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[6] += 0.5
        cover = shapely.box(28, -1, 32, 1)
        self.assertEqual(zo.correct([road(zs)], plane, covers=cover)["places"], 0)
        self.assertEqual(zo.correct([road(zs)], plane, held=[0])["places"], 0)
        self.assertEqual(zo.correct([road(zs, cls="paved")], plane)["places"], 0)
        self.assertEqual(zo.correct([road(zs, cls="platform")], plane)["places"], 0)
        self.assertEqual(zo.correct([road(zs)], plane)["places"], 1)

    def test_a_face_the_survey_drew_stays(self):
        a = road()
        x = 30.0
        k = 6
        a["r"].insert(k + 1, [x + 0.3, 0.0, round(float(plane(x, 0)) - 0.24, 2)])  # (a kerb corner: two heights at one place)
        before = [q[2] for q in a["r"]]
        zo.correct([a], plane)
        self.assertEqual(before, [q[2] for q in a["r"]])

    def test_a_shared_vertex_gets_one_height(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[6] += 0.4
        a = road(zs)
        walk = {"c": "paved", "l": 0, "r": [list(q) for q in a["r"][:13]][::-1] + [[0.0, 3.0, 200.1], [60.0, 3.0, 202.5]]}
        zo.correct([a, walk], plane)
        shared = [q[2] for q in walk["r"] if q[0] == 30.0 and q[1] == 0.0]
        self.assertEqual(shared, [a["r"][6][2]])
        self.assertAlmostEqual(shared[0], float(plane(30, 0)), delta=0.011)

    def test_a_larger_move_is_another_level(self):
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[6] += 2.5
        self.assertEqual(zo.correct([road(zs)], plane)["places"], 0)

    def test_a_run_moves_whole_or_not_at_all(self):
        # a stretch off IPR whose middle lies beyond MAX: moved in part it would become a sawtooth
        zs = plane(np.arange(0, 61, 5.0), 0)
        zs[4:9] -= np.array([1.0, 1.5, 2.5, 1.5, 1.0])
        a = road(zs)
        before = heights(a)
        self.assertEqual(zo.correct([a], plane)["places"], 0)
        self.assertEqual(before, heights(a))


if __name__ == "__main__":
    unittest.main()
