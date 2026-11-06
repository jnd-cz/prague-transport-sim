"""The validation report's limits and table (#23): python -I tools/test_validation.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebuild  # noqa: E402
import validation  # noqa: E402


def good(**kw):
    return {"fit": {"points": 100, "median": 0.1, "p90": 3.0},
            "stops": [{"stop": "A", "s": 1, "diff": 2.0}, {"stop": "B", "s": 2, "diff": -9.0}],
            "crossings": 10, "crossingsWithoutOsm": [1, 2], "signalsOnPlatforms": [], "crossingsInPlatforms": [],
            "platformOverlaps": [], **kw}


class Measures(unittest.TestCase):
    def test_a_good_line_is_within_every_limit(self):
        self.assertEqual(validation.over(validation.measures(good())), [])

    def test_shares(self):
        m = validation.measures(good(stops=[{"stop": "A", "s": 1, "osm": None}, {"stop": "B", "s": 2, "diff": 11.0},
                                            {"stop": "C", "s": 3, "diff": 1.0}, {"stop": "D", "s": 4, "diff": 1.0}]))
        self.assertEqual(m["stopsFar"], 50.0)
        self.assertEqual(m["crossingsLone"], 20.0)

    def test_each_limit_is_read(self):
        for kw, check in ((dict(fit={"median": 0.6, "p90": 3.0}), "fitMedian"), (dict(fit={"median": 0.1, "p90": 6.5}), "fitP90"),
                          (dict(crossingsWithoutOsm=list(range(6))), "crossingsLone"),
                          (dict(signalsOnPlatforms=[{}] * 11), "signalsOnPlatforms"),
                          (dict(crossingsInPlatforms=[{}] * 11), "crossingsInPlatforms"),
                          (dict(platformOverlaps=[{}]), "platformOverlaps")):
            self.assertEqual(validation.over(validation.measures(good(**kw))), [check], kw)

    def test_no_osm_track_near_ours_is_over(self):
        self.assertIn("fitMedian", validation.over(validation.measures(good(fit={"points": 0, "median": None, "p90": None}))))


class Report(unittest.TestCase):
    def test_table_and_missing_line(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data"))
            with open(os.path.join(d, "data", "line17.validate.json"), "w", encoding="utf-8") as f:
                json.dump(good(platformOverlaps=[{}]), f)
            rows, bad, missing = validation.report(["17", "9"], root=d)
        self.assertEqual(missing, ["9"])
        self.assertEqual(bad, {"17": ["platformOverlaps"]})
        self.assertIn("| platforms overlapping on the route | 0 | 1 **over** |", rows)


class Build(unittest.TestCase):
    def test_every_line_is_validated_and_has_its_furniture_and_the_signals_stay_line_17s(self):
        for line in ("9", "17", "22", "23", "37"):
            names = [w[0] for w in rebuild.writers(line)]
            self.assertIn("osm_validate.py", names)
            self.assertEqual(names[-1], "osm_validate.py")  # (after the steps that write what it reads)
            self.assertEqual("osm_signals.py" in names, line == "17")
            self.assertIn("dtm_points.py", names)


if __name__ == "__main__":
    unittest.main()
