# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/street_profile.py: street profiles, crossfall, the junctions' fill and the drive-line measures (#512).

    python -P -E tools/test_street_profile.py
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import street_profile as sp  # noqa: E402


def way(i, name, nodes, xy, highway="residential", oneway="no"):
    return {"id": i, "name": name, "highway": highway, "oneway": oneway, "nodes": nodes, "xy": np.asarray(xy, float)}


class Profiles(unittest.TestCase):
    def test_ways_of_one_name_join_end_to_end(self):
        ws = [way(1, "A", [1, 2], [(0, 0), (10, 0)]), way(2, "A", [3, 2], [(20, 0), (10, 0)]),
              way(3, "B", [2, 4], [(10, 0), (10, 10)])]
        cs = sp.chains(ws)
        a = next(c for c in cs if c["name"] == "A")
        self.assertEqual(a["nodes"], [1, 2, 3])
        self.assertEqual(len(cs), 2)

    def test_a_dual_carriageway_is_not_joined_round_its_end(self):
        # (Hartigova: the two one-way carriageways share their west end node)
        ws = [way(1, "H", [1, 2], [(100, 0), (0, 0)], oneway="yes"), way(2, "H", [2, 3], [(0, 0), (100, 40)], oneway="yes"),
              way(3, "H", [3, 4], [(100, 40), (200, 40)], oneway="yes")]
        cs = sp.chains(ws)
        self.assertEqual(sorted(len(c["ids"]) for c in cs), [1, 2])

    def test_resample_every_metre(self):
        s, p, t = sp.resample(np.array([(0, 0), (10, 0), (10, 5)], float))
        self.assertEqual(len(s), 15)
        self.assertTrue(np.allclose(p[12], (10, 2)))
        self.assertTrue(np.allclose(t[12], (0, 1)))

    def test_profile_smooths_noise_and_keeps_the_radius(self):
        s = np.arange(0, 200.0)
        true = 200 + 0.03 * s - 0.03 * np.maximum(s - 100, 0) ** 2 / 200  # a grade into a crest of R 3333 m
        rng = np.random.default_rng(3)
        z = sp.profile(s, true + rng.normal(0, 0.02, len(s)), rmin=500)
        self.assertLess(np.abs(z - true).max(), 0.03)
        k = np.abs(np.diff(z, 2))
        self.assertLessEqual(k.max(), 1 / 500 * 1.05)

    def test_a_pinned_street_meets_its_governing_one(self):
        s = np.arange(0, 60.0)
        z = sp.profile(s, 300 + 0.02 * s, rmin=150, pins=[0, 1, 2], pin_z=np.array([299.8, 299.82, 299.84]))
        self.assertAlmostEqual(z[0], 299.8, places=2)
        self.assertLess(abs(z[-1] - (300 + 0.02 * 59)), 0.05)


class Junctions(unittest.TestCase):
    def test_the_fill_follows_a_tilted_junction_through_the_noise(self):
        # a junction tilted 2 % one way and 1 % the other (Palmovka's, by the tracks), lidar noise 3 cm, held at its
        # two streets' edges
        n = 60
        Y, X = np.mgrid[0:n, 0:n].astype(float)
        plane = 190 + 0.02 * X - 0.01 * Y
        data = plane + np.random.default_rng(1).normal(0, 0.03, plane.shape)
        known = np.full(plane.shape, np.nan)
        known[:, :3], known[:, -3:] = plane[:, :3], plane[:, -3:]
        g = sp.fill_2d(known, np.isnan(known), data, (sp.JUNCTION_WAVE / (2 * math.pi)) ** 4)
        self.assertLess(np.sqrt(((g - plane) ** 2).mean()), 0.01)
        self.assertLess(np.abs(g - plane).max(), 0.03)

    def test_a_raised_bed_keeps_its_kerb(self):
        # a bed 0.15 m over a flat road beside it (Hartigova's raised belt): held, but the road is not drawn up to it
        n = 40
        Y, X = np.mgrid[0:n, 0:n].astype(float)
        data = np.full((n, n), 200.0)
        known = np.full((n, n), np.nan)
        known[:, 18:22] = 200.15
        kerb = np.isfinite(known)
        lam = (sp.JUNCTION_WAVE / (2 * math.pi)) ** 4
        free = np.isnan(known)
        drawn = sp.fill_2d(known, free, data, lam)
        kept = sp.fill_2d(known, free, data, lam, kerb=kerb)
        self.assertGreater(drawn[:, 17].mean() - 200, 0.05)  # (without the kerb the road climbs to the bed)
        self.assertLess(np.abs(kept[:, :18] - 200).max(), 0.005)

    def test_street_geometry_from_truth(self):
        r, other, belt, fall = sp.street_geometry()
        self.assertEqual((r["primary"], r["living_street"], other, belt, fall), (500.0, 100.0, 150.0, 0.07, 0.06))

    def test_bilinear_reads_the_edge(self):
        g = np.array([[1.0, 2.0], [np.nan, 4.0]])
        z = sp.bilinear((0.0, 1.0, 1.0, g), np.array([0.5]), np.array([0.5]))
        self.assertTrue(np.isfinite(z[0]))


class Measures(unittest.TestCase):
    def street(self, n=40):
        s = np.arange(0, float(n))
        return {"name": "test", "highway": "residential", "s": s, "p": np.column_stack([s, np.zeros(n)]),
                "t": np.tile([1.0, 0.0], (n, 1))}

    def test_a_step_is_a_jump_and_a_side_slope_a_roll(self):
        c = self.street()
        flat = sp.drive_measures(lambda x, y: np.where(np.asarray(x) > 20, 200.2, 200.0), [c])
        self.assertEqual(flat["jumps"], 2)  # (both drive lines)
        side = sp.drive_measures(lambda x, y: 200 + 0.2 * np.asarray(y), [c])
        self.assertEqual(side["rolls over 7 deg"], 2 * 40)
        self.assertEqual(side["jumps"], 0)
        steep = sp.drive_measures(lambda x, y: 200 + 0.16 * np.asarray(x), [c])  # (a 16 % street: a slope, not a step)
        self.assertEqual(steep["jumps"], 0)

    def test_drive_lines_off_the_road_are_not_measured(self):
        # (an island beside a carriageway, 0.3 m up, under one drive line: no car drives it)
        from shapely.geometry import box
        c = self.street()
        z = lambda x, y: np.where((np.asarray(x) > 20) & (np.asarray(y) > 1), 200.3, 200.0)  # noqa: E731
        self.assertEqual(sp.drive_measures(z, [c])["jumps"], 1)  # (the left drive line)
        road = box(-1, -3, 41, 1).union(box(-1, 1, 20, 3))
        self.assertEqual(sp.drive_measures(z, [c], road=road)["jumps"], 0)


if __name__ == "__main__":
    unittest.main()
