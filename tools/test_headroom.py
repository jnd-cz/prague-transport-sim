# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the posted clearances along the tracks (tools/headroom.py, #71): python -P -E tools/test_headroom.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import headroom  # noqa: E402


def xy(lats, lons):  # (the test's frame: a degree is a metre)
    return list(lons), list(lats)


def way(i, pts, **tags):
    return {"type": "way", "id": i, "tags": tags, "geometry": [{"lat": y, "lon": x} for x, y in pts]}


TRACK = [[x, 0.0] for x in range(0, 201, 10)]  # (a track along x, 200 m)


class Headroom(unittest.TestCase):
    def test_metres(self):
        self.assertEqual(headroom.metres("4.3"), 4.3)
        self.assertEqual(headroom.metres(" 4,3 m"), 4.3)
        self.assertEqual(headroom.metres("13'6\""), round(13 * 0.3048 + 6 * 0.0254, 2))
        for v in (None, "default", "none", "below_default", ""):
            self.assertIsNone(headroom.metres(v))

    def test_a_street_with_the_track_cut_to_the_tracks(self):
        # a road 5 m beside the track from x = -100 to 300: kept where it lies within NEAR m (25) of the track
        out = headroom.posted([way(7, [(-100, 5), (300, 5)], highway="secondary", maxheight="4.3", name="Dukelských hrdinů")], [TRACK], xy)
        self.assertEqual(len(out), 1)
        w = out[0]
        self.assertEqual((w["mh"], w["src"], w["kind"], w["name"], w["id"]), (4.3, "4.3", "car", "Dukelských hrdinů", 7))
        xs = sorted(p[0] for p in w["p"])
        self.assertAlmostEqual(xs[0], -24.5, delta=0.2)  # (25 m from the track's end, 5 m aside)
        self.assertAlmostEqual(xs[-1], 224.5, delta=0.2)

    def test_what_is_left_out(self):
        els = [
            way(1, [(0, 40), (200, 40)], highway="secondary", maxheight="4.3"),             # 40 m from the track
            way(2, [(0, 3), (200, 3)], highway="secondary", maxheight="default"),           # no number
            way(3, [(0, 3), (200, 3)], highway="secondary", maxheight="below_default"),
            way(4, [(0, 3), (200, 3)], highway="secondary"),                                # nothing posted
            way(5, [(0, 3), (200, 3)], highway="secondary", maxheight="4.0", bridge="yes"),  # passes over
            way(6, [(0, 3), (200, 3)], highway="footway", maxheight="2.5"),                 # not a road or a track
            way(10, [(0, 3), (200, 3)], highway="trunk", maxheight="4.6", tunnel="yes", layer="-2"),  # a road tunnel under the street
            way(11, [(0, 3), (200, 3)], highway="residential", maxheight="3.5", layer="-1"),          # a road under the ground
        ]
        self.assertEqual(headroom.posted(els, [TRACK], xy), [])
        self.assertEqual(headroom.posted([way(8, [(0, 3), (200, 3)], highway="secondary", maxheight="4.3")], [], xy), [])

    def test_a_passage_and_a_track_in_a_tunnel_stay(self):
        els = [way(12, [(0, 3), (50, 3)], highway="residential", maxheight="3.3", tunnel="building_passage"),
               way(13, [(60, 0), (90, 0)], railway="tram", maxheight="4.0", tunnel="yes", layer="-1")]
        self.assertEqual([(w["id"], w["kind"], w["mh"]) for w in headroom.posted(els, [TRACK], xy)], [(12, "car", 3.3), (13, "tram", 4.0)])

    def test_a_tram_way_by_its_nodes_and_the_physical_height_first(self):
        els = [{"type": "node", "id": 1, "lat": 0.0, "lon": 50.0}, {"type": "node", "id": 2, "lat": 0.0, "lon": 90.0},
               {"type": "way", "id": 9, "nodes": [1, 2], "tags": {"railway": "tram", "maxheight": "3.9", "maxheight:physical": "4.1"}},
               {"type": "way", "id": 9, "nodes": [1, 2], "tags": {"railway": "tram", "maxheight": "3.9"}}]  # (the same way twice: once)
        out = headroom.posted(els, [TRACK], xy)
        self.assertEqual([(w["id"], w["kind"], w["mh"], w["src"], w["p"]) for w in out], [(9, "tram", 4.1, "4.1", [[50.0, 0.0], [90.0, 0.0]])])

    def test_a_way_that_crosses_the_zone_twice_gives_two_parts(self):
        # (a road that leaves the tracks' 25 m and comes back)
        out = headroom.posted([way(3, [(20, 5), (60, 5), (60, 60), (140, 60), (140, 5), (180, 5)], highway="tertiary", maxheight="3.5")], [TRACK], xy)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(w["mh"] == 3.5 and max(abs(p[1]) for p in w["p"]) <= headroom.NEAR + 0.1 for w in out))


if __name__ == "__main__":
    unittest.main()
