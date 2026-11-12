# SPDX-License-Identifier: AGPL-3.0-or-later
"""The route's structures built offline (tools/line_structures.py, #480): python -P -E tools/test_line_structures.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import line_structures as S  # noqa: E402


def rect(x0, x1, y0, y1, c, l=0, z=200.0):
    return {"c": c, "l": l, "r": [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]}


def data(**extra):
    return {"line": "x", "path": [[0.0, 0.0], [1000.0, 0.0]], "bridges": [], "tunnels": [],
            "heights": {"step": 2, "path": [210.0] * 501}, **extra}


def run(d, dtm=None, tris=(), road=None, lidar=200.0):
    return S.structures(d, dtm, list(tris), lambda x, y: road, lambda x, y: lidar)


class Spans(unittest.TestCase):
    def test_osm_bridges_and_runs_of_surveyed_bed_on_a_structure_are_spans(self):
        dtm = {"areas": [rect(300, 330, -3, 3, "tram", 1), rect(500, 506, -3, 3, "tram", 1), rect(600, 700, -3, 3, "road", 1)]}
        spans, real, _ = run(data(bridges=[[100.0, 150.0], [152.0, 180.0]]), dtm)
        # (OSM's two bridges 2 m apart: one span; the 6 m bed run is too short; a road deck is not our bed)
        self.assertEqual(spans, [[100.0, 180.0], [300.0, 330.0]])
        self.assertEqual(real, [[300.0, 330.0]])   # (the surveyed bed is its own deck; the OSM bridge has none)

    def test_a_bridge_with_its_model_under_the_track_or_beside_it_has_a_deck(self):
        under = [[(90, -5), (200, -5), (200, 5)], [(90, -5), (200, 5), (90, 5)]]
        beside = [[(390, 1), (500, 1), (500, 8)], [(390, 1), (500, 8), (390, 8)]]   # (the other track's half)
        far = [[(690, 10), (800, 10), (800, 20)], [(690, 10), (800, 20), (690, 20)]]
        _, real, _ = run(data(bridges=[[100.0, 180.0], [400.0, 480.0], [700.0, 780.0]]), None, under + beside + far)
        self.assertEqual(real, [[100.0, 180.0], [400.0, 480.0]])

    def test_no_bed_near_a_tunnel(self):
        dtm = {"areas": [rect(300, 340, -3, 3, "tram", 1), rect(500, 540, -3, 3, "tram", 1)]}
        spans, _, _ = run(data(tunnels=[[335.0, 400.0], [505.0, 600.0]]), dtm)
        # (the bed stops 10 m before a tunnel: 300-324 m stays a span, 500-494 m none)
        self.assertEqual(spans, [[300, 324]])


class Underpasses(unittest.TestCase):
    def test_a_road_under_the_track_has_its_clearance_and_one_at_grade_none(self):
        cs = [{"s": 200.0, "x": 200.0, "y": 0.0, "mh": 4.2, "kind": "car"}, {"s": 400.0, "x": 400.0, "y": 0.0, "mh": 4.2},
              {"s": 600.0, "x": 600.0, "y": 0.0, "mh": None}]
        _, _, under = run(data(clearances=cs), road=205.0)
        self.assertEqual([(c["s"], c["zr"], c["need"]) for c in under], [(200.0, 205.0, 210.0), (400.0, 205.0, 210.0)])
        _, _, at_grade = run(data(clearances=cs), road=208.5)
        self.assertEqual(at_grade, [])   # (the track 1.5 m over the road: the road meets it at grade)
        _, _, lidar = run(data(clearances=cs[:1]), road=None, lidar=204.0)
        self.assertEqual(lidar[0]["zr"], 204.0)   # (no survey there: the lidar)


class SurveySurface(unittest.TestCase):
    def test_the_highest_ranked_area_linear_between_its_outline_points(self):
        ramp = {"c": "road", "l": 0, "r": [[0, 0, 200.0], [40, 0, 204.0], [40, 10, 204.0], [0, 10, 200.0]]}
        green = rect(-10, 60, -10, 30, "green", 0, 190.0)
        surf = S.Surface({"areas": [green, ramp]})
        self.assertAlmostEqual(surf.at(20, 5), 202.0, places=6)
        self.assertAlmostEqual(surf.at(50, 20), 190.0, places=6)
        self.assertIsNone(surf.at(100, 100))


if __name__ == "__main__":
    unittest.main()
