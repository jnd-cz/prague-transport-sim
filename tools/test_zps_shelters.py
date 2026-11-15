# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/zps_shelters.py: the shelter holes in the survey's platforms filled, their footprints kept (#523).

    python -P -E tools/test_zps_shelters.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zps_shelters as zs  # noqa: E402


def ring(x0, y0, x1, y1, z):
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


def platform(holes, z=200.2, level=0):
    return {"c": "platform", "l": level, "r": ring(0, 0, 60, 3, z), "h": holes}


SINGLE = ring(10, 0.6, 14, 2.4, 200.2)  # 4.0 x 1.8 m, along x
DOUBLE = ring(30, 0.8, 37.8, 2.3, 200.2)  # 7.8 x 1.5 m
STOPS = [{"p": [[0, 0], [60, 0], [60, 3], [0, 3]], "name": "Palmovka", "code": "A", "id": "U529Z1P"}]


class Shelters(unittest.TestCase):
    def test_empty_holes_are_filled_and_their_footprints_kept(self):
        areas = [platform([SINGLE, DOUBLE])]
        rep = zs.fill(areas, STOPS)
        self.assertNotIn("h", areas[0])
        self.assertEqual((rep["filled"], rep["kept"], rep["byKind"]), (2, 0, {"double": 1, "single": 1}))
        s = rep["shelters"][0]
        self.assertEqual((s["x"], s["y"], s["length"], s["width"], s["z"]), (12.0, 1.5, 4.0, 1.8, 200.2))
        self.assertIn(s["bearing"], (0.0, 180.0))
        self.assertEqual(s["stop"], {"name": "Palmovka", "code": "A", "id": "U529Z1P"})
        self.assertEqual(len(s["ring"]), 4)

    def test_a_stair_in_the_hole_keeps_it(self):
        stair = {"c": "stairs", "l": 0, "r": ring(10, 0.6, 14, 2.4, 199.0)}
        areas = [platform([SINGLE, DOUBLE]), stair]
        rep = zs.fill(areas)
        self.assertEqual(areas[0]["h"], [SINGLE])
        self.assertEqual((rep["filled"], rep["kept"]), (1, 1))

    def test_a_road_or_tunnel_under_the_whole_platform_is_not_the_holes(self):
        # an island platform on a road whose polygon spans it (Pohořelec), a tunnel under it (Brusnice over Blanka)
        road = {"c": "road", "l": 0, "r": ring(-5, -5, 65, 8, 199.9)}
        tunnel = {"c": "tunnel", "l": -1, "r": ring(8, -10, 20, 10, 190.0)}
        areas = [platform([SINGLE]), road, tunnel]
        rep = zs.fill(areas)
        self.assertNotIn("h", areas[0])
        self.assertEqual(rep["filled"], 1)

    def test_kerb_flags_follow_the_holes(self):
        stair = {"c": "stairs", "l": 0, "r": ring(10, 0.6, 14, 2.4, 199.0)}
        a = platform([SINGLE, DOUBLE])
        a["k"] = [[1, 0, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]]
        zs.fill([a, stair])
        self.assertEqual(a["k"], [[1, 0, 0, 0], [0, 0, 0, 1]])

    def test_only_level_0_platforms(self):
        areas = [platform([SINGLE], level=1), {"c": "sidewalk", "l": 0, "r": ring(0, 0, 60, 3, 200), "h": [SINGLE]}]
        rep = zs.fill(areas)
        self.assertEqual(rep["filled"], 0)
        self.assertEqual(areas[0]["h"], [SINGLE])
        self.assertEqual(areas[1]["h"], [SINGLE])

    def test_a_far_stop_is_not_named(self):
        far = [dict(STOPS[0], p=[[500, 0], [560, 0], [560, 3], [500, 3]])]
        rep = zs.fill([platform([SINGLE])], far)
        self.assertNotIn("stop", rep["shelters"][0])


if __name__ == "__main__":
    unittest.main()
