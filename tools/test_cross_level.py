# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/cross_level.py: the cross level of paved track from the road's tilt across both tracks (#538).

    python -P -E tools/test_cross_level.py
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cross_level as cl  # noqa: E402


def street(n=101, off=3.7):
    """A straight line along x, every STEP m, its opposite track `off` m to the left."""
    s = np.arange(n) * cl.STEP
    xy = np.column_stack([s, np.zeros(n)])
    h = np.tile([1.0, 0.0], (n, 1))
    return s, xy, h, np.full(n, off)


class Planes(unittest.TestCase):
    def test_a_tilted_junction_reads_its_fall(self):
        # Sokolovská: the road falls 5 % to the left across both tracks
        s, xy, h, off = street()
        fall, res = cl.planes(lambda x, y: 200 - 0.05 * np.asarray(y) + 0.01 * np.asarray(x), xy, h, off)
        self.assertTrue(np.allclose(fall, -0.05, atol=1e-6))
        self.assertLess(res.max(), 1e-6)

    def test_a_crown_between_the_tracks_is_no_plane(self):
        # a crowned street, 2.5 % either way from between the tracks: the plane's fall is about 0, its residual large
        s, xy, h, off = street()
        fall, res = cl.planes(lambda x, y: 200 - 0.025 * np.abs(np.asarray(y) - 1.85), xy, h, off)
        self.assertLess(np.abs(fall).max(), 0.002)
        self.assertGreater(res.min(), cl.RESID / 2)


class Level(unittest.TestCase):
    def run_rule(self, fall, res=None, street_=None):
        n = len(fall)
        res = np.zeros(n) if res is None else res
        street_ = np.ones(n, bool) if street_ is None else street_
        c, _ = cl.cross_level(np.asarray(fall, float), res, street_, np.ones(n, bool))
        return c

    def test_the_fall_becomes_cross_level_with_its_flanks(self):
        fall = np.zeros(80)
        fall[20:60] = -np.r_[np.linspace(0.006, 0.05, 15), np.full(10, 0.05), np.linspace(0.05, 0.006, 15)]
        c = self.run_rule(fall)
        self.assertAlmostEqual(c.max(), 0.05 * cl.GAUGE, delta=0.004)   # + = the left rail lower: the road falls left
        self.assertGreater(c[22], 0)                                     # its flank (under LEVEL) is kept
        self.assertEqual(c[:15].any(), False)

    def test_a_crossfall_under_level_stays_level(self):
        self.assertFalse(self.run_rule(np.full(60, 0.015)).any())

    def test_ramps_and_the_cap(self):
        fall = np.zeros(60)
        fall[30:] = 0.12  # a step to a fall past the cap
        c = self.run_rule(fall)
        self.assertGreaterEqual(c.min(), -cl.CANT_MAX - 1e-9)
        self.assertLessEqual(np.abs(np.diff(c)).max(), cl.CANT_MAX / 30 * cl.STEP + 1e-9)

    def test_a_road_tilting_faster_than_the_ramp_starts_it_earlier(self):
        # the road goes from level to 5 % in 10 m (Sokolovská's is 20 m): the full tilt where the road has it, the
        # ramp before it
        fall = np.zeros(80)
        fall[40:45] = -np.linspace(0.01, 0.05, 5)
        fall[45:] = -0.05
        c = self.run_rule(fall, street_=np.r_[np.zeros(40, bool), np.ones(40, bool)])
        self.assertAlmostEqual(c[50], 0.05 * cl.GAUGE, delta=0.002)
        self.assertGreater(c[38], 0)  # (begun before the road tilts)
        self.assertLessEqual(np.abs(np.diff(c)).max(), cl.CANT_MAX / 30 * cl.STEP + 1e-9)

    def test_no_plane_and_open_bed_stay_level(self):
        fall = np.full(60, 0.05)
        self.assertFalse(self.run_rule(fall, res=np.full(60, 0.05)).any())
        self.assertFalse(self.run_rule(fall, street_=np.zeros(60, bool)).any())

    def test_grass_and_ballast_are_open_bed(self):
        s = np.arange(0, 100.0, cl.STEP)
        m = cl.masks({"styles": [{"s0": 20, "s1": 40, "style": "grass"}, {"s0": 60, "s1": 80, "style": "embedded"}],
                      "spans": [[90, 95]]}, s)
        self.assertFalse(m[(s >= 20) & (s <= 40)].any())
        self.assertTrue(m[(s > 40) & (s < 80)].all())
        self.assertFalse(m[s > 80].any())  # within NEAR_SPAN of the span


class Fuse(unittest.TestCase):
    def test_the_median_outvotes_one_source(self):
        # Sokolovská: tracks 2.7 %, survey 2.7 %, IPR 5.2 %
        f = cl.fuse({"IPR": [-0.052], "survey": [-0.027], "tracks": [-0.027]}, "median")
        self.assertAlmostEqual(f[0], -0.027)

    def test_two_sources_make_their_mean_and_one_none(self):
        f = cl.fuse({"IPR": [0.02, 0.02], "survey": [np.nan, np.nan], "tracks": [0.04, np.nan]}, "median")
        self.assertAlmostEqual(f[0], 0.03)
        self.assertTrue(np.isnan(f[1]))

    def test_the_hat_finds_each_sources_spread_and_weights_by_it(self):
        rng = np.random.default_rng(1)
        truth = rng.normal(0, 0.03, 4000)
        falls = {"IPR": truth + rng.normal(0, 0.005, 4000), "survey": truth + rng.normal(0, 0.01, 4000),
                 "tracks": truth + rng.normal(0, 0.02, 4000)}
        sig = cl.hat(falls, np.ones(4000, bool))
        self.assertAlmostEqual(sig["IPR"], 0.005, delta=0.0015)
        self.assertAlmostEqual(sig["survey"], 0.01, delta=0.0015)
        self.assertAlmostEqual(sig["tracks"], 0.02, delta=0.002)
        w = cl.fuse(falls, "weighted", sig)
        self.assertLess(np.std(w - truth), 0.005)


class Opposite(unittest.TestCase):
    def test_the_opposite_route_reads_it_from_its_own_side(self):
        s, xy, h, _ = street(20)
        c = np.full(20, 0.06)
        xyb = xy[::-1] + [0, 3.7]
        hb = -h
        cb = cl.opposite(c, xy, h, xyb, hb)
        self.assertTrue(np.allclose(cb, -0.06))
        far = cl.opposite(c, xy, h, xy + [0, 9.0], h)
        self.assertFalse(far.any())

    def test_a_level_answer_levels_between_its_pins(self):
        from geo import Frame
        F = Frame()
        s, xy, _, _ = street(50)
        c = np.full(50, 0.05)
        a = {"answer": "level", "between": [list(F.ll(20.0, 0.0)), list(F.ll(40.0, 0.0))]}
        out = cl.answered(c, xy, {"crossLevelReview": {"answers": [a, {**a, "answer": "tilts", "between": [
            list(F.ll(60.0, 0.0)), list(F.ll(80.0, 0.0))]}]}})
        self.assertFalse(out[(s >= 21) & (s <= 39)].any())
        self.assertTrue(out[(s > 50)].all())

    def test_places_list_the_stretches(self):
        s, xy, _, _ = street(10)
        c = np.array([0, 0.01, 0.03, 0.02, 0, 0, -0.01, -0.04, 0, 0])
        p = cl.places(s, xy, c)
        self.assertEqual([q["mm"] for q in p], [30.0, -40.0])
        self.assertEqual(p[0]["length"], 6)


if __name__ == "__main__":
    unittest.main()
