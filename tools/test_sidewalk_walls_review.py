# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sidewalks at a wall measured and picked for review (tools/sidewalk_walls_review.py, #653):
python -P -E tools/test_sidewalk_walls_review.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import sidewalk_walls_review as R  # noqa: E402

# a parapet 0.5 m thick along a terrace's edge, its outline at the top's 106 m alone; the walkway below runs 4 m out
# from it at 100 m, and its outline carries the top's level along the wall (as Vyšehrad's path, #899)
WALL = {"c": "wall", "l": 0, "r": [[0, 0, 106], [20, 0, 106], [20, 0.5, 106], [0, 0.5, 106]]}
BELOW = {"c": "sidewalk", "l": 0, "r": [[0, -4, 100], [20, -4, 100], [20, 0, 106], [0, 0, 106]]}
# the walkway on the terrace beside the parapet, its outline at its own level: the lidar's
ABOVE = {"c": "sidewalk", "l": 0, "r": [[0, 0.5, 106], [20, 0.5, 106], [20, 4.5, 106], [0, 4.5, 106]]}


def survey(*areas, dx=0.0):
    return {"areas": [{**a, "r": [[q[0] + dx, q[1], q[2]] for q in a["r"]]} for a in areas]}


def walk(D):
    return shapely.union_all([shapely.Polygon([q[:2] for q in a["r"]]) for a in D["areas"] if a["c"] == "sidewalk"])


def lidar(x, y):   # (the walkway below at 100 m, the terrace at 106 m)
    return np.where(np.asarray(y) < 0.25, 100.0, 106.0)


def measured(dx=0.0, *extra):
    D = survey(WALL, BELOW, ABOVE, *extra, dx=dx)
    return R.measure(D, walk(D), lidar)


class Measure(unittest.TestCase):
    def test_an_edge_carrying_the_walls_top_is_over_and_its_own_level_is_not(self):
        m, read = measured()
        self.assertAlmostEqual(read, 40.0)   # (both edges along the wall, 20 m each)
        bad = m["off"] > R.OFF
        self.assertEqual(bad.sum() * R.SAMPLE, 20.0)
        self.assertTrue(np.all(m["p"][bad][:, 1] < 0.25))   # (the walkway below)
        self.assertEqual(set(m["side"][bad]), {"over"})
        self.assertEqual(set(m["cls"][bad]), {"wall"})
        self.assertEqual(R.held(m, int(np.flatnonzero(bad)[0])), 106.0)
        n = R.count(m, read)
        self.assertEqual((n["off"], n["over"], n["under"], n["wall"], n["stretches"], n["long"]), (20.0, 20.0, 0, 20.0, 1, 1))
        self.assertIn("| 9 | 40 | 20 | 20 | 0 | 0 | 20 / 0 / 0 | 1 (1) |", R.table({"9": n}))

    def test_a_narrow_sidewalk_is_not_read(self):
        # (IPR 1.5 m in from an edge of a sidewalk 1 m wide is another area's: street_profile.runs_in)
        D = survey(WALL, {**BELOW, "r": [[0, -1, 100], [20, -1, 100], [20, 0, 106], [0, 0, 106]]})
        m, read = R.measure(D, walk(D), lidar)
        self.assertEqual(read, 0)

    def test_a_stretch_on_two_lines_is_one_and_far_ones_are_two(self):
        a, _ = measured()
        b, _ = measured(0.0, *survey(WALL, BELOW, dx=100.0)["areas"])
        S, at = R.stretches({"17": b, "9": a})
        S = sorted(S, key=lambda s: at["p"][s["worst"]][0])
        self.assertEqual([(s["lines"], s["length"], s["side"], R.group(s)) for s in S],
                         [(["9", "17"], 20.0, "over", "over, wall"), (["17"], 20.0, "over", "over, wall")])

    def test_the_longest_of_a_group_get_a_card_short_or_near_ones_not(self):
        m, _ = measured(0.0, *survey(WALL, BELOW, dx=100.0)["areas"], *survey(WALL, BELOW, dx=110.0)["areas"])
        S, at = R.stretches({"9": m})
        self.assertEqual(len(S), 2)   # (the walls from 100 and 110 m overlap: one stretch of 30 m)
        old = R.PER_GROUP, R.SHORT
        try:
            R.PER_GROUP = 5
            got = R.choose(S, at, np.zeros((0, 2)))
            self.assertEqual([s["length"] for s in got], [30.0, 20.0])
            got = R.choose(S, at, np.array([[105.0, 0.0]]))   # (an answered place on the longer one)
            self.assertEqual([s["length"] for s in got], [20.0])
            R.SHORT = 25.0
            self.assertEqual([s["length"] for s in R.choose(S, at, np.zeros((0, 2)))], [30.0])
        finally:
            R.PER_GROUP, R.SHORT = old

    def test_the_answers_are_keys(self):
        keys = [k for _, k in R.ANSWERS]
        self.assertEqual(len(set(keys)), len(keys))
        self.assertEqual(R.ANSWER[R.UNSURE], R.UNSURE)
        self.assertEqual(set(R.GROUPS), {"over, wall", "over, strip", "under, wall", "under, strip", "stairs"})

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_an_answer_goes_into_truth_and_the_place_off_the_review(self):
        m, _ = measured()
        S, at = R.stretches({"9": m})
        c = R.card(S[0], at)
        self.assertEqual((c["kind"], c["lines"], len(c["marks"]), c["options"][-1], c["side"]),
                         (R.KIND, ["9"], 4, R.UNSURE, "over"))
        self.assertEqual((c["survey"], c["lidar"]), (106.0, 100.0))
        self.assertTrue(c["id"].startswith("sidewalk-wall-"))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "review").mkdir()
            (d / "reviews").mkdir()
            (d / "review" / "sidewalk-walls-9.json").write_text(json.dumps({"findings": [c]}), encoding="utf-8")
            key = f"file|{R.KIND}|{c['x']:.1f},{c['y']:.1f}"   # (review mode's key: src/reviewFindings.js fid)
            (d / "reviews" / "line9.json").write_text(json.dumps({"items": {key: {
                "v": R.ANSWERS[0][0], "kind": R.KIND, "id": c["id"], "t": 1764288000000, "note": "a path at the foot"}}}),
                encoding="utf-8")
            p = d / "truth.json"
            p.write_text('{\n "note": "x",\n "other": [1]\n}\n', encoding="utf-8")
            R.do_import(["9"], d / "reviews", p, d / "review")
            truth = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(truth["other"], [1])
            (a,) = truth["sidewalkWallsReview"]["answers"]
            self.assertEqual((a["id"], a["level"], a["note"], a["survey"], a["lidar"]),
                             (c["id"], "lidar", "a path at the foot", 106.0, 100.0))
            (ax, ay), = R.answered(truth)
            self.assertLess(abs(ax - c["x"]) + abs(ay - c["y"]), 0.1)
            self.assertEqual(R.choose(S, at, R.answered(truth)), [])   # (answered: no card again)


if __name__ == "__main__":
    unittest.main()
