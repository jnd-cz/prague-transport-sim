# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stairs measured and picked for review (tools/stairs_review.py, #447): python -P -E tools/test_stairs_review.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import stairs_review as R  # noqa: E402

# one flight: 2 m wide, rising 3 m over 6 m (1:2)
FLIGHT = {"c": "stairs", "l": 0, "r": [[0, 0, 0], [2, 0, 0], [2, 6, 3], [0, 6, 3]]}
# a 4 m square whose outline goes up and down 3 m every 2 m: its triangles fold, steeper than 1:1
FOLD = {"c": "stairs", "l": 0, "r": [[10, 0, 0], [12, 0, 3], [14, 0, 0], [14, 4, 3], [12, 4, 0], [10, 4, 3]]}
OTHER = [{"c": "sidewalk", "l": 0, "r": [[20, 0, 1], [22, 0, 1], [22, 2, 1]]},
         {"c": "stairs", "l": 1, "r": [[30, 0, 0], [32, 0, 3], [32, 2, 0]]},       # (level 1)
         {"c": "stairs", "l": 0, "r": [[40, 0, 0], [42, 0, None], [42, 2, 0]]}]  # (a point without a height)


def survey(*areas):
    return {"areas": [dict(a) for a in areas]}


class Measure(unittest.TestCase):
    def test_a_flight_counts_as_one_and_a_fold_as_steep(self):
        n, rows = R.measure(survey(FLIGHT, FOLD, *OTHER))
        self.assertEqual((n["stairs"], n["flight"], n["rest"], n["odd"], n["tall"]), (2, 1, 1, 1, 0))
        self.assertAlmostEqual(n["m2"], 12 + 16)
        self.assertGreater(n["steep"], 4)
        (r,) = rows
        self.assertEqual((r["area"], r["foot"][2], r["top"][2]), (1, 0, 3))
        self.assertTrue(r["g"].contains(R.shapely.Point(r["x"], r["y"])))
        self.assertIn("| 9 | 2 | 28 | 1 | 1 | 16 |", R.table({"9": n}))

    def test_an_area_on_two_lines_is_one_place(self):
        _, a = R.measure(survey(FOLD))
        _, b = R.measure(survey(FLIGHT, FOLD, {**FOLD, "r": [[q[0] + 100, q[1], q[2]] for q in FOLD["r"]]}))
        P = R.places({"17": b, "9": a})
        self.assertEqual([(p["line"], p["lines"]) for p in P], [("9", ["9", "17"]), ("17", ["17"])])

    def test_the_worst_and_the_asked_get_a_card(self):
        _, rows = R.measure(survey(FOLD, {**FOLD, "r": [[q[0] + 100, q[1], q[2] / 3] for q in FOLD["r"]]},
                                   {**FOLD, "r": [[q[0] + 200, q[1], q[2] * 2] for q in FOLD["r"]]}))
        P = R.places({"9": rows})
        old = R.WORST, R.ASKED
        try:
            R.WORST, R.ASKED = 1, [(211.0, 2.0, "asked")]
            got = R.choose(P, {})
            self.assertEqual([(round(p["x"] // 100), why) for p, why in got], [(2, "asked")])  # (the steepest, asked too)
            R.ASKED = [(108.0, 2.0, "asked")]   # (2 m off its outline: within 5 m)
            got = R.choose(P, {})
            self.assertEqual([(round(p["x"] // 100), why) for p, why in got], [(2, None), (1, "asked")])
        finally:
            R.WORST, R.ASKED = old

    def test_the_kinds_are_answers_with_keys(self):
        keys = [k for _, k in R.KINDS]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(R.ANSWER[R.UNSURE], R.UNSURE)   # (recorded: no card again where the imagery shows nothing)

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_an_answer_goes_into_truth_and_the_place_off_the_review(self):
        _, rows = R.measure(survey(FOLD))
        P = R.places({"9": rows})
        c = R.card(P[0])
        self.assertEqual((c["kind"], c["lines"], len(c["marks"]), c["options"][-1]), ("stairs", ["9"], 2, R.UNSURE))
        self.assertTrue(c["id"].startswith("stairs-"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "truth.json"
            p.write_text('{\n "note": "x",\n "other": [1]\n}\n', encoding="utf-8")
            R.write_truth(p, {"note": "n", "answers": [{"id": c["id"], "lines": c["lines"], "place": c["place"], "kind": "sunk"}]})
            truth = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(truth["other"], [1])
            (ax, ay), = R.answered(truth)
            self.assertLess(abs(ax - P[0]["x"]) + abs(ay - P[0]["y"]), 0.05)
            old = R.ASKED
            try:
                R.ASKED = []
                self.assertEqual(R.choose(P, {}), [(P[0], None)])
                self.assertEqual(R.choose(P, truth), [])   # (answered: no card again)
            finally:
                R.ASKED = old


if __name__ == "__main__":
    unittest.main()
