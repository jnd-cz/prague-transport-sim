# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/covers.py: the street over a passage keeps its own level where the raster has the passage's floor (#783).

    python -P -E tools/test_covers.py
"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import covers  # noqa: E402


def rect(c, x0, y0, x1, y1, z, level=0):
    z = z if callable(z) else (lambda x, y, z=z: z)
    return {"c": c, "l": level, "r": [[x, y, z(x, y)] for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]}


def slot(x0, x1, floor=196.0, top=200.0):
    """A raster level at `top` with the passage's floor between x0 and x1."""
    return lambda x, y: np.where((np.asarray(x, float) > x0) & (np.asarray(x, float) < x1), floor, top)


class Street(unittest.TestCase):
    # a road along x, 0..60 by 0..10 at 200 m, its verge north of it (10..14) on the lidar, an underpass under both
    # at x = 28..32 with stairs down into it south of the road
    D = {"areas": [rect("road", 0, 0, 60, 10, 200.0), dict(rect("green", 0, 10, 60, 14, 200.0), g=1),
                   rect("stairs", 28, -6, 32, 0, lambda x, y: 200.0 + y * 0.6),
                   rect("underpass", 28, -1, 32, 15, 196.0, level=-1)]}

    def test_the_street_over_the_passage_keeps_its_level(self):
        # (the raster's slot 1 m wider than the survey's passage either side: road and verge at 200 m in it and NEAR
        # round it; the stairs go down with the raster; far along the road there is no cover)
        lidar = slot(27, 33)
        C = covers.Covers(self.D, lidar)
        self.assertEqual(len(C.places), 1)
        x = np.array([30.0, 27.5, 30.0, 30.0, 10.0, 30.0])
        y = np.array([5.0, 5.0, 12.0, -3.0, 5.0, 20.0])
        z = C.at(x, y)
        np.testing.assert_allclose(z[:3], 200.0, atol=1e-9)
        self.assertTrue(np.isnan(z[3:]).all())
        np.testing.assert_allclose(C.over(lidar)(x, y), [200.0, 200.0, 200.0, 196.0, 200.0, 196.0], atol=1e-9)

    def test_osm_s_tunnel_way_is_a_passage_too(self):
        D = {"areas": self.D["areas"][:3]}
        self.assertEqual(len(covers.Covers(D, slot(27, 33)).places), 0)
        C = covers.Covers(D, slot(27, 33), ways=[shapely.LineString([(30, -1), (30, 15)])])
        self.assertEqual(len(C.places), 1)
        np.testing.assert_allclose(C.at(np.array([30.0]), np.array([5.0])), 200.0, atol=1e-9)

    def test_a_cut_that_runs_on_is_no_slot(self):
        # (the raster 4 m under the road from the passage on for 30 m: a structure left out whole, not a slot)
        self.assertEqual(len(covers.Covers(self.D, slot(27, 60)).places), 0)

    def test_the_open_ramp_before_the_passage_is_no_cover(self):
        # (OSM's tunnel way begins at the portal, x = 40; before it the ramp down to it lies open, drawn by the
        # survey as an area at its rim's level: the raster's floor there is the ground)
        D = {"areas": [rect("paved", 20, 0, 40, 4, 200.0), rect("road", 40, -10, 50, 14, 200.0)]}
        lidar = lambda x, y: np.where((np.asarray(x, float) > 28) & (np.asarray(x, float) < 40.5), 196.5, 200.0)  # noqa: E731
        self.assertEqual(len(covers.Covers(D, lidar, ways=[shapely.LineString([(40, 2), (50, 2)])]).places), 0)

    def test_nothing_where_the_raster_has_the_street(self):
        # (a tunnel deep under the street: the raster has the street's level over it)
        self.assertEqual(len(covers.Covers(self.D, slot(27, 33, floor=199.8)).places), 0)

    def test_a_steep_outline_is_no_cover(self):
        # (a sidewalk drawn as one area from the street down into a stair well, its outline 4 m down over 6 m: its
        # triangles are no surface, and it stays on the raster)
        D = {"areas": [rect("sidewalk", 26, 0, 34, 6, lambda x, y: 200.0 - 4.0 * y / 6.0),
                       rect("underpass", 28, -1, 32, 7, 196.0, level=-1)]}
        self.assertEqual(len(covers.Covers(D, slot(27, 33)).places), 0)
        # (but a kerb's top and foot close together are one: 0.6 m over 2 m, 30 %)
        t = covers._triangles({"c": "green", "l": 0, "r": [[0, 0, 200.0], [2, 0, 200.6], [2, 6, 200.6], [0, 6, 200.0]]})
        self.assertEqual(len(t), 2)

    def test_the_metro_is_no_passage(self):
        D = {"areas": self.D["areas"][:3] + [rect("tunnel", 28, -1, 32, 15, 180.0, level=-2)]}
        self.assertEqual(len(covers.Covers(D, slot(27, 33)).places), 0)
        self.assertFalse(covers.is_tunnel({"railway": "subway", "tunnel": "yes"}))
        self.assertFalse(covers.is_tunnel({"highway": "footway", "tunnel": "building_passage"}))
        self.assertFalse(covers.is_tunnel({"highway": "trunk", "tunnel": "yes", "layer": "-2"}))
        self.assertTrue(covers.is_tunnel({"highway": "cycleway", "tunnel": "yes", "layer": "-1"}))

    def test_two_passages_each_with_its_cover(self):
        D = {"areas": self.D["areas"] + [rect("underpass", 48, -1, 52, 15, 196.0, level=-1)]}
        lidar = lambda x, y: np.where(((np.asarray(x, float) > 27) & (np.asarray(x, float) < 33))  # noqa: E731
                                      | ((np.asarray(x, float) > 47) & (np.asarray(x, float) < 53)), 196.0, 200.0)
        C = covers.Covers(D, lidar)
        self.assertEqual(len(C.places), 2)
        np.testing.assert_allclose(C.at(np.array([30.0, 50.0]), np.array([5.0, 5.0])), 200.0, atol=1e-9)

    def test_iprs_reader_with_the_covers(self):
        from types import SimpleNamespace
        lidar = slot(27, 33)
        ipr = SimpleNamespace(sample=lambda E, N: lidar(np.asarray(E) - 1000.0, np.asarray(N) - 2000.0))
        c = covers.CoveredIpr(ipr, covers.Covers(self.D, lidar), SimpleNamespace(E0=1000.0, N0=2000.0))
        np.testing.assert_allclose(c.sample(np.array([1030.0, 1030.0]), np.array([2005.0, 1997.0])), [200.0, 196.0], atol=1e-9)


if __name__ == "__main__":
    unittest.main()
