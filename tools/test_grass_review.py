# SPDX-License-Identifier: AGPL-3.0-or-later
"""OSM's grass over our track for review (tools/grass_review.py, #503): python -P -E tools/test_grass_review.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geo  # noqa: E402
import grass_review as G  # noqa: E402

DATA = {"line": "x", "path": [[0.0, 0.0], [600.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}]}


class Review(unittest.TestCase):
    def test_runs_join_short_gaps(self):
        flags = [False] * 10 + [True] * 30 + [False] * 5 + [True] * 10 + [False] * 50 + [True] * 3
        self.assertEqual(G.runs_of(flags), [(10, 39), (45, 54), (105, 107)])
        self.assertEqual(G.runs_of(flags, 30), [(10, 54), (105, 107)])

    def test_a_candidate_is_grass_the_facts_do_not_cover(self):
        flags = [100 <= s <= 200 or 300 <= s <= 400 or 500 <= s <= 510 for s in range(601)]
        truth = {"trackStyles": [{"line": "x", "from": "A", "to": "B", "style": "embedded"}]}
        self.assertEqual(G.candidates(DATA, {}, None, flags), [(100, 200), (300, 400)])   # (10 m: too short)
        self.assertEqual(G.candidates(DATA, truth, None, flags), [])   # (an embedded mark is a fact too)

    def test_the_grass_under_a_bridge_is_not_ours(self):
        class Tree:
            def query(self, pt):
                return [0]
        from shapely.geometry import box
        _, flags = G.under_route({**DATA, "bridges": [[100.0, 200.0]], "tunnels": [[300.0, 310.0]]}, [box(-1, -1, 601, 1)], Tree())
        self.assertEqual(G.runs_of(flags), [(0, 99), (201, 299), (311, 600)])

    @unittest.skipUnless(geo.have_grid(), geo.NO_GRID)
    def test_an_answer_goes_into_truth_and_the_place_off_the_review(self):
        rt = G.Route(DATA["path"])
        c = G.card("x", DATA, rt, 100, 200)
        self.assertEqual((c["kind"], c["options"][0], len(c["between"])), ("grass track", G.GRASS, 2))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "truth.json"
            p.write_text('{\n "note": "x",\n "other": [1]\n}\n', encoding="utf-8")
            G.write_truth(p, {"note": "n", "answers": [{"id": c["id"], "lines": ["x"], "between": c["between"], "answer": "not grass"}]})
            truth = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(truth["other"], [1])
            flags = [100 <= s <= 200 for s in range(601)]
            self.assertEqual(G.candidates(DATA, truth, rt, flags), [])   # (answered: no card again)
            truth["grassReview"]["answers"][0]["answer"] = "grass"
            secs = G.T.sections(DATA, truth, None)
            self.assertEqual([(round(x["s0"]), round(x["s1"]), x["source"]) for x in secs], [(100, 200, "review")])


if __name__ == "__main__":
    unittest.main()
