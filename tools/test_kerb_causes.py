# SPDX-License-Identifier: AGPL-3.0-or-later
"""The flat kerbs' causes (tools/bench/kerb_causes.py, #800) on a made street: a route along x, the carriageway on its
right (y < 0), the raised area on its left, and a kerb of each kind in the sources.

    python -P -E tools/test_kerb_causes.py
Needs no data.
"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench"))
import kerb_causes as kc  # noqa: E402

LINE = shapely.LineString([(0, 0), (100, 0)])


def step(h, at=0.0, width=0.0):
    """A surface 0 on the carriageway and h on the raised side, rising from y = at over width m (0: a step)."""
    def z(x, y):
        y = np.asarray(y, float)
        return h * (np.clip((y - at) / width, 0, 1) if width else (y > at).astype(float))
    return z


def site(z, s=50.0, classes=("road", "sidewalk")):
    """The check's sample at s on the kerb's line (y = 0): its two heights 0.125 m either side, the first on the
    first class's side."""
    ys = np.array([-kc.HALF, kc.HALF] if classes[1] in kc.RAISED else [kc.HALF, -kc.HALF])
    h = z(np.full(2, s), ys)
    return {"x": s, "y": 0.0, "s": s, "classes": list(classes), "heights": [float(h[0]), float(h[1])], "step": float(abs(h[1] - h[0]))}


def street_of(z):
    return lambda kind, x, y: z(x, y)


class Causes(unittest.TestCase):
    def one(self, ground, lidar, street=None, **kw):
        rows = kc.sort_sites([site(ground, **kw)], LINE, ground, lidar, street_of(street or ground))
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_no_kerb_in_the_raster_either(self):
        r = self.one(step(0.0), step(0.02))
        self.assertEqual(r["cause"], "raster flat")
        self.assertAlmostEqual(r["ipr"], 0.02)

    def test_a_kerb_spread_wider_than_the_checks_row_is_a_ramp(self):
        # (0.12 m over 1 m: 0.03 m in the check's 0.25 m, 0.12 m over the 1.5 m read here)
        ground = step(0.12, at=-0.5, width=1.0)
        r = self.one(ground, step(0.14))
        self.assertLess(r["step"], kc.FLAT)
        self.assertEqual(r["cause"], "ramp")
        self.assertAlmostEqual(r["ground"], 0.12)

    def test_a_sidewalk_flat_on_the_street_surface(self):
        r = self.one(step(0.01), step(0.12), street=step(0.02))
        self.assertEqual(r["cause"], "street flat")
        self.assertAlmostEqual(r["street"], 0.02)

    def test_a_sidewalk_whose_street_surface_has_the_kerb(self):
        r = self.one(step(0.01), step(0.12), street=step(0.13))
        self.assertEqual(r["cause"], "other")

    def test_an_area_drawn_from_its_outline(self):
        for classes in (("road", "platform"), ("median", "tram"), ("parking", "sidewalk")):
            r = self.one(step(0.01), step(0.15), classes=classes)
            self.assertEqual(r["cause"], "outline flat", classes)
            self.assertTrue(np.isnan(r["street"]))

    def test_a_strip_at_a_walls_foot_reads_the_walls_kerb(self):
        # an island 1.8 m wide at the foot of a 2 m wall: IPR past its reading on the island rises with the wall, and
        # the kerb it reads is the wall's spread (line 17's islands at the retaining walls, #800); a kerb the ground
        # has spread over the row is still a ramp
        wall = lambda x, y: step(0.15)(x, y) + 2.0 * (np.asarray(y, float) > 1.8)  # noqa: E731
        r = self.one(step(0.01), wall, classes=("road", "island"))
        self.assertEqual(r["cause"], "beside a wall")
        self.assertAlmostEqual(r["beyond"], 2.0)
        self.assertEqual(self.one(step(0.12, at=-0.5, width=1.0), wall, classes=("road", "island"))["cause"], "ramp")
        self.assertEqual(self.one(step(0.01), step(0.15), classes=("road", "island"))["cause"], "outline flat")

    def test_the_raised_side_is_found_whichever_way_the_row_runs(self):
        # the raised area on the route's right, the pair recorded raised first: the kerbs keep their sign
        ground, lidar = (lambda x, y: step(0.03)(x, -np.asarray(y))), (lambda x, y: step(0.15)(x, -np.asarray(y)))
        st = {"x": 50.0, "y": 0.0, "s": 50.0, "classes": ["sidewalk", "road"], "heights": [0.03, 0.0], "step": 0.03}
        r = kc.sort_sites([st], LINE, ground, lidar, street_of(lidar))[0]
        self.assertAlmostEqual(r["ipr"], 0.15)
        self.assertAlmostEqual(r["ground"], 0.03)
        self.assertAlmostEqual(r["off"], 0.0)
        self.assertEqual(r["pair"], "sidewalk|road")

    def test_a_sample_at_a_platform_and_the_table(self):
        L = {"path": [[0, 0], [100, 0]], "platforms": [{"path": "route", "s0": 40.0, "s1": 60.0}]}
        plat = kc.platforms(L)
        ground, lidar = step(0.01), step(0.15)
        sites = [site(ground, s=50.0, classes=("road", "platform")), site(ground, s=90.0, classes=("road", "platform"))]
        rows = kc.sort_sites(sites, LINE, ground, lidar, street_of(ground), plat)
        self.assertEqual([r["platform"] for r in rows], [True, False])
        t = kc.table({"9": rows, "17": []})
        self.assertEqual(t[2], "| 9 | 2 | 0 | 0 | 2 | 0 | 0 | 0 |")
        self.assertEqual(t[-1], "| all | 2 | 0 | 0 | 2 | 0 | 0 | 0 |")

    def test_no_samples(self):
        self.assertEqual(kc.sort_sites([], LINE, step(0), step(0), street_of(step(0))), [])


if __name__ == "__main__":
    unittest.main()
