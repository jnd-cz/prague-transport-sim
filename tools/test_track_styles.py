"""The track styles built offline (tools/track_styles.py, #479): python -P -E tools/test_track_styles.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_styles as T  # noqa: E402


def rect(x0, x1, y0, y1, c, l=0, z=200.0):
    return {"c": c, "l": l, "r": [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]}


STOPS = [{"name": "A", "s": 0.0}, {"name": "B", "s": 100.0}, {"name": "C", "s": 300.0}, {"name": "B", "s": 400.0}]
DATA = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": STOPS}


class Styles(unittest.TestCase):
    def test_the_users_mark_runs_from_its_stop_to_the_next_of_the_other_name(self):
        truth = {"trackStyles": [{"line": "y", "from": "A", "to": "B", "style": "ballast"},
                                 {"line": "x", "from": "C", "to": "B", "style": "ballast"}]}
        self.assertEqual(T.sections(DATA, truth, None), [{"s0": 300.0, "s1": 400.0, "style": "ballast", "source": "user", "mark": 1}])

    def test_green_under_the_axis_for_20_m_is_grass_track(self):
        sv = T.Survey({"areas": [rect(100, 160, -5, 5, "green"), rect(200, 212, -5, 5, "green"), rect(0, 600, -20, 20, "road", 1)]})
        secs = T.sections(DATA, {"trackStyles": []}, sv)
        self.assertEqual(secs, [{"s0": 100, "s1": 160, "style": "grass", "source": "survey"}])   # (the 12 m piece is too short)

    def test_short_gaps_are_one_section_and_the_users_marks_win(self):
        sv = T.Survey({"areas": [rect(100, 160, -5, 5, "green"), rect(180, 260, -5, 5, "green"), rect(360, 440, -5, 5, "green")]})
        truth = {"trackStyles": [{"line": "x", "from": "C", "to": "B", "style": "embedded"}]}
        secs = T.sections(DATA, truth, sv)
        self.assertEqual([(x["s0"], x["s1"], x["style"], x["source"]) for x in secs],
                         [(100, 260, "grass", "survey"), (300.0, 400.0, "embedded", "user")])

    def test_the_list_takes_every_pass_and_leaves_the_users_marks_their_track(self):
        stops = [{"name": "A", "s": 0.0}, {"name": "B", "s": 100.0}, {"name": "C", "s": 300.0}, {"name": "B", "s": 400.0},
                 {"name": "A", "s": 550.0}]
        data = {**DATA, "stops": stops}
        truth = {"trackStyles": [{"line": "x", "from": "C", "to": "B", "style": "embedded"}],
                 "grassTrack": {"stretches": [{"from": "A", "to": "B"}, {"from": "C", "to": "B"}, {"at": "C"},
                                              {"from": "B", "to": "C", "removed": 2009}]}}
        secs = T.sections(data, truth, None)
        self.assertEqual([(x["s0"], x["s1"], x["source"], x.get("stretch")) for x in secs],
                         [(0.0, 100.0, "list", 0), (100.0, 300.0, "list", 1), (300.0, 400.0, "user", None),
                          (400.0, 550.0, "list", 0)])   # (C - B both ways; the user's mark keeps the way back)

    def test_a_mark_between_two_points_runs_between_their_route_positions(self):
        ll = [list(map(float, T.Frame().ll(x, y))) for x, y in ((420.0, 3.0), (180.0, -2.0))]
        truth = {"trackStyles": [{"line": "x", "between": ll, "style": "grass"}],
                 "grassTrack": {"stretches": [{"from": "B", "to": "C"}]}}
        secs = T.sections(DATA, truth, None)
        self.assertEqual([(round(x["s0"], 3), round(x["s1"], 3), x["source"]) for x in secs],
                         [(100.0, 180.0, "list"), (180.0, 420.0, "user")])
        to_stop = {"trackStyles": [{"line": "x", "between": [ll[1], "B"], "style": "grass"}]}   # (B at 100 and 400: the nearer)
        self.assertEqual([(round(x["s0"], 2), round(x["s1"], 2)) for x in T.sections(DATA, to_stop, None)], [(100.0, 180.0)])
        far = [list(map(float, T.Frame().ll(x, y))) for x, y in ((420.0, 30.0), (180.0, 0.0))]
        self.assertEqual(T.sections(DATA, {"trackStyles": [{"line": "x", "between": far, "style": "grass"}]}, None), [])

    def test_an_area_of_higher_rank_over_the_green_decides(self):
        sv = T.Survey({"areas": [rect(100, 200, -5, 5, "green"), rect(140, 160, -5, 5, "road"), rect(0, 600, -9, 9, "wall")]})
        self.assertEqual(sv.class_at(150, 0), "road")
        self.assertEqual(sv.class_at(120, 0), "green")
        self.assertIsNone(sv.class_at(300, 0))   # (a wall is not ground)


if __name__ == "__main__":
    unittest.main()
