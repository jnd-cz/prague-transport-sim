"""The speed survey's rules: python -P -E tools/test_speed_survey.py. Needs no data (pyosmium for its imports only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speed_survey as S  # noqa: E402


def way(pts, **tags):
    return {"id": 1, "tags": tags, "pts": pts}


class Tags(unittest.TestCase):
    def test_posted_reads_a_number_and_nothing_else(self):
        self.assertEqual(S.posted("50"), 50)
        self.assertEqual(S.posted("60;50"), 60)
        self.assertEqual(S.posted("CZ:pedestrian_zone"), 0)
        self.assertEqual(S.posted(None), 0)

    def test_conditional_keeps_every_period(self):
        self.assertEqual(S.conditional("50 @ (06:00-22:00); 40 @ (22:00-06:00)"), [(50, "06:00-22:00"), (40, "22:00-06:00")])
        self.assertEqual(S.conditional(None), [])

    def test_only_the_night_period_is_a_night_zone(self):
        self.assertEqual(S.night("40 @ (22:00-06:00)"), 40)
        self.assertEqual(S.night("50 @ (06:00-22:00); 40 @ (22:00-06:00)"), 40)
        self.assertEqual(S.night("30 @ (06:30-17:30)"), 0)  # Zlíchov: during the day

    def test_a_note_for_one_car_type(self):
        self.assertEqual(S.typed("max. 70 km/h pouze vozy 14T, ostatní max. 65 km/h"), (70, "14T", 65))
        self.assertIsNone(S.typed("jiná poznámka"))
        self.assertIsNone(S.typed(None))


class Along(unittest.TestCase):
    def test_stretches_leave_out_zeros_and_short_ones(self):
        self.assertEqual(S.stretches([0, 60, 60, 0, 65], step=5), [(5, 15, 60), (20, 25, 65)])
        self.assertEqual(S.stretches([60, 60, 0, 65], step=5, min_len=10), [(0, 10, 60)])

    def test_km_by_value(self):
        self.assertEqual(S.km_by_value([50] * 200 + [0] * 100, step=5), {0: 0.5, 50: 1.0})

    def test_the_way_under_the_track_is_near_and_in_line(self):
        ways = S.Ways([way([(0, 0), (100, 0)], maxspeed="60"), way([(50, -30), (50, 30)], maxspeed="15")])
        self.assertEqual(ways.under((20, 1), (1, 0))["tags"]["maxspeed"], "60")
        self.assertIsNone(ways.under((20, 3), (1, 0)))                  # beyond 2 m
        self.assertEqual(ways.under((50, 0.5), (1, 0))["tags"]["maxspeed"], "60")  # the crossing way is not in line

    def test_samples_every_step_with_the_heading(self):
        got = S.samples([(0, 0), (10, 0)], step=5)
        self.assertEqual([p for p, _ in got], [(0, 0), (5, 0), (10, 0)])
        self.assertEqual(got[0][1], (1, 0))

    def test_stop_between(self):
        stops = [{"name": "A", "s": 0}, {"name": "B", "s": 100}, {"name": "C", "s": 200}]
        self.assertEqual(S.stop_between(stops, 150), "B .. C")
        self.assertEqual(S.stop_between(stops, 500), "C .. C")


class Line(unittest.TestCase):
    def test_a_line_with_a_fast_stretch_a_note_and_a_night_zone(self):
        ways = S.Ways([
            way([(0, 0), (100, 0)], maxspeed="70", note="max. 70 km/h pouze vozy 14T, ostatní max. 65 km/h"),
            way([(100, 0), (200, 0)], maxspeed="50", **{"maxspeed:conditional": "40 @ (22:00-06:00)"}),
        ])
        data = {"path": [(0, 0), (200, 0)], "stops": [{"name": "A", "s": 0}, {"name": "B", "s": 200}],
                "speed": {"osm": [70] * 21 + [50] * 20}}  # (s 100 lies on both ways: the first one found)
        r = S.survey_line(17, data, ways)
        self.assertEqual(r["differsFromData"], 0)
        self.assertEqual([(f["v"], f["to"] - f["from"]) for f in r["fast"]], [(70, 105)])
        self.assertEqual(r["typedNotes"][0]["for"], "14T")
        self.assertEqual(r["typedNotes"][0]["others"], 65)
        self.assertEqual(r["night"][0]["v"], 40)

    def test_a_speed_switch_is_placed_on_the_lines_it_lies_on(self):
        lines = {17: {"path": [(0, 0), (100, 0)], "pathBack": [(100, 3), (0, 3)], "switches": [{"s": 40}]},
                 9: {"path": [(0, 500), (100, 500)]}}
        got = S.speed_switches(lines, [{"ref": "R04", "lat": 50, "lon": 14, "xy": (40, 0)}],
                               {"R04": {"place": "Nádraží Braník", "straight": 30, "diverging": 15}})
        self.assertEqual(got[0]["straight"], 30)
        self.assertEqual([(r["line"], r["dir"], r["facing"]) for r in got[0]["on"]], [(17, "out", True), (17, "back", None)])


if __name__ == "__main__":
    unittest.main()
