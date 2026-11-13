# SPDX-License-Identifier: AGPL-3.0-or-later
"""The kerb review list: what is not a kerb leaves it (#142): python -P -E tools/test_kerbs.py"""
import os
import sys
import unittest

from shapely.geometry import LineString

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kerbs  # noqa: E402

Z = 200.0


def street(y0=0.0, length=40.0, n=11):
    """A road and a sidewalk 3 m wide along it, sharing the kerb line y = y0 at height Z."""
    xs = [length * i / (n - 1) for i in range(n)]
    road = {"c": "road", "l": 0, "r": [[x, y0, Z] for x in xs] + [[length, y0 - 6, Z], [0.0, y0 - 6, Z]]}
    walk = {"c": "sidewalk", "l": 0, "r": [[x, y0, Z] for x in xs] + [[length, y0 + 3, Z + 0.1], [0.0, y0 + 3, Z + 0.1]]}
    return road, walk


def terrain(inside, road, y0=0.0):
    return lambda x, y: Z + (inside if y > y0 else road)


class Lists(unittest.TestCase):
    def run_it(self, inside, road=0.0, why=None, facts=()):
        return kerbs.apply(list(street()), terrain(inside, road), why, facts)

    def test_an_ordinary_disagreement_stays_on_the_list(self):
        r = self.run_it(0.30)
        self.assertEqual(len(r["review"]), 1)
        self.assertEqual({k: len(v) for k, v in r["notKerb"].items()}, {"level": 0, "wall": 0, "terrain": 0})

    def test_a_good_kerb_is_not_listed(self):
        r = self.run_it(0.10)
        self.assertEqual(r["review"], [])

    def test_terrain_far_off_is_not_a_kerb(self):
        r = self.run_it(-1.17)
        self.assertEqual(r["review"], [])
        self.assertEqual(len(r["notKerb"]["terrain"]), 1)

    def test_the_reason_from_the_surroundings_comes_first(self):
        r = self.run_it(-3.0, why=lambda pts: "level")
        self.assertEqual(len(r["notKerb"]["level"]), 1)
        self.assertEqual(len(r["notKerb"]["terrain"]), 0)

    def test_the_users_ramp_stays_whatever_stands_near(self):
        r = self.run_it(-0.85, why=lambda pts: "level", facts=[{"x": 20.0, "y": 1.0, "kind": "ramp"}])
        self.assertEqual(r["notKerb"]["level"], [])
        self.assertEqual([i["fact"] for i in r["review"]], ["ramp"])

    def test_the_same_area_twice_is_listed_once(self):
        a = list(street()) + list(street())
        r = kerbs.apply(a, terrain(0.30, 0.0))
        self.assertEqual(len(r["review"]), 1)


class OsmNote(unittest.TestCase):
    def report(self, nodes):
        return kerbs.apply(list(street()), terrain(0.30, 0.0), low_kerbs=nodes)

    def test_nodes_along_the_kerb_are_named(self):
        r = self.report([(20.0, 1.0, "lowered"), (10.0, -2.9, "lowered"), (30.0, 0.0, "flush")])
        self.assertEqual(r["review"][0]["osmKerb"], {"flush": 1, "lowered": 2})

    def test_a_node_further_off_is_not(self):
        self.assertNotIn("osmKerb", self.report([(20.0, 3.5, "lowered")])["review"][0])

    def test_it_changes_no_height_and_no_list(self):
        plain, tagged = list(street()), list(street())
        a = kerbs.apply(plain, terrain(0.30, 0.0))
        b = kerbs.apply(tagged, terrain(0.30, 0.0), low_kerbs=[(20.0, 0.0, "lowered")])
        self.assertEqual(plain, tagged)
        del b["review"][0]["osmKerb"]
        self.assertEqual(a, b)


class Decision(unittest.TestCase):
    def side(self, inside, road):
        road_a, walk = street()
        r = kerbs.apply([road_a, walk], terrain(inside, road))
        return r["areas"], walk["r"][0][2]

    def test_terrain_level_with_the_road_says_foot(self):
        areas, z = self.side(0.10, 0.0)
        self.assertEqual(areas, {"sidewalk/foot/terrain": 1})
        self.assertAlmostEqual(z, Z + kerbs.KERB)

    def test_terrain_level_with_the_sidewalk_says_top(self):
        areas, z = self.side(0.0, -0.10)
        self.assertEqual(areas, {"sidewalk/top/terrain": 1})
        self.assertAlmostEqual(z, Z)

    def test_terrain_off_on_both_sides_decides_nothing(self):
        areas, _ = self.side(-3.0, -3.1)  # (an underpass floor under the street)
        self.assertEqual(list(areas), ["sidewalk/foot/survey"])  # (the far edges, 0.1 m over the line)


class Surroundings(unittest.TestCase):
    PTS = [[float(x), 0.0] for x in range(0, 40, 4)]

    def test_nothing_near(self):
        self.assertIsNone(kerbs.surroundings([])(self.PTS))

    def test_an_osm_structure_along_it_is_another_level(self):
        why = kerbs.surroundings([], structures=[LineString([(0, 5), (40, 5)])])
        self.assertEqual(why(self.PTS), "level")

    def test_a_structure_at_one_end_is_not_enough(self):
        why = kerbs.surroundings([], structures=[LineString([(0, 5), (2, 5)])])
        self.assertEqual(why(self.PTS), "level" if 3 / 10 >= kerbs.SHARE else None)
        far = kerbs.surroundings([], structures=[LineString([(-30, 0), (-20, 0)])])
        self.assertIsNone(far(self.PTS))

    def test_an_area_off_level_along_it(self):
        deck = {"c": "deck", "l": 1, "r": [[0, 2, Z], [40, 2, Z], [40, 8, Z], [0, 8, Z]]}
        self.assertEqual(kerbs.surroundings([deck])(self.PTS), "level")

    def test_a_ground_level_area_is_no_level_change(self):
        ground = {"c": "road", "l": 0, "r": [[0, 2, Z], [40, 2, Z], [40, 8, Z], [0, 8, Z]]}
        self.assertIsNone(kerbs.surroundings([ground])(self.PTS))

    def test_a_wall_along_it(self):
        why = kerbs.surroundings([], walls=kerbs.lines([[(0, 2), (40, 2)], [(5, 5), (5, 5)]]))
        self.assertEqual(why(self.PTS), "wall")


if __name__ == "__main__":
    unittest.main()
