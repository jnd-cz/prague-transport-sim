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


class Lowered(unittest.TestCase):
    """#303: OSM's crossings and kerb nodes lower the kerb over the norm's width, with ramps; the survey shows none."""
    CROSS = LineString([(20.0, -6.0), (20.0, 3.0)])

    def run_it(self, crossings=(), nodes=(), inside=0.10, road=0.0):
        road_a, walk = street()
        r = kerbs.apply([road_a, walk], terrain(inside, road), crossings=crossings, kerb_nodes=nodes)
        return r, {round(p[0], 2): p[2] for p in walk["r"] if p[1] == 0.0}, {round(p[0], 2): p[2] for p in road_a["r"] if p[1] == 0.0}

    def ramp(self, h=kerbs.LOW_H):
        return kerbs.LOW_W / 2 + (kerbs.KERB - h) / kerbs.LOW_RAMP

    def test_a_crossing_lowers_its_width_and_ramps_up_beyond(self):
        r, walk, road = self.run_it([self.CROSS])
        half, end = kerbs.LOW_W / 2, self.ramp()
        self.assertAlmostEqual(walk[20.0], Z + kerbs.LOW_H)
        self.assertAlmostEqual(walk[20.0 + half], Z + kerbs.LOW_H)
        self.assertAlmostEqual(walk[round(20.0 - end, 2)], Z + kerbs.KERB)
        self.assertAlmostEqual(walk[16.0], Z + kerbs.KERB)
        self.assertEqual(r["lowered"]["bySource"], {"crossing": 1})
        # (the road's ring has the same points, at its own height)
        self.assertEqual(sorted(walk), sorted(road))
        self.assertTrue(all(z == Z for z in road.values()))

    def test_the_points_keep_the_kerb_faces(self):
        road_a, walk = street()
        kerbs.apply([road_a, walk], terrain(0.10, 0.0), crossings=[self.CROSS])
        self.assertEqual(sum(walk["k"][0]), 10 + 4)

    def test_a_crossing_ending_short_of_the_kerb_meets_it(self):
        _, walk, _ = self.run_it([LineString([(20.0, -6.0), (20.0, -2.0)])])
        self.assertAlmostEqual(walk[20.0], Z + kerbs.LOW_H)

    def test_a_raised_tag_at_the_crossing_keeps_the_kerb(self):
        r, walk, _ = self.run_it([self.CROSS], [(20.3, 0.2, "raised")])
        self.assertAlmostEqual(walk[20.0], Z + kerbs.KERB)
        self.assertEqual(r["lowered"]["bySource"], {"osm kerb=raised": 1})

    def test_a_flush_tag_takes_the_road_level(self):
        r, walk, _ = self.run_it([self.CROSS], [(20.0, 0.0, "flush")])
        self.assertAlmostEqual(walk[20.0], Z)
        self.assertIn(round(20.0 + self.ramp(0.0), 2), walk)
        self.assertEqual(r["lowered"]["bySource"], {"osm kerb=flush": 1})

    def test_a_lowered_node_away_from_crossings(self):
        r, walk, _ = self.run_it(nodes=[(8.0, 0.5, "lowered")])
        self.assertAlmostEqual(walk[8.0], Z + kerbs.LOW_H)
        self.assertEqual(r["lowered"]["bySource"], {"osm kerb=lowered": 1})
        _, walk, _ = self.run_it(nodes=[(8.0, 1.5, "lowered")])
        self.assertAlmostEqual(walk[8.0], Z + kerbs.KERB)

    def test_a_top_line_lowers_the_road_less(self):
        _, walk, road = self.run_it([self.CROSS], inside=0.0, road=-0.10)
        self.assertAlmostEqual(walk[20.0], Z)
        self.assertAlmostEqual(road[20.0], Z - kerbs.LOW_H)
        self.assertAlmostEqual(road[0.0], Z - kerbs.KERB)

    def test_none_given_changes_nothing(self):
        plain, given = list(street()), list(street())
        kerbs.apply(plain, terrain(0.10, 0.0))
        r = kerbs.apply(given, terrain(0.10, 0.0), crossings=[], kerb_nodes=[(20.0, 9.0, "lowered")])
        self.assertEqual(plain, given)
        self.assertEqual(r["lowered"]["stretches"], [])

    def test_the_check_reads_plain_kerb(self):
        # (terrain level with a plain kerb along the street: the lowered stretch is not judged by it)
        a, _, _ = self.run_it([self.CROSS], inside=0.10)
        self.assertEqual(a["review"], [])

    def test_crossing_tags(self):
        self.assertTrue(kerbs.is_crossing({"highway": "footway", "footway": "crossing"}))
        self.assertTrue(kerbs.is_crossing({"highway": "path", "crossing": "uncontrolled"}))
        self.assertFalse(kerbs.is_crossing({"highway": "footway", "footway": "sidewalk"}))
        self.assertFalse(kerbs.is_crossing({"highway": "footway", "crossing": "no"}))


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
