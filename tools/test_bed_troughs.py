# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bed trough review set (tools/bed_troughs.py, #548): python -P -E tools/test_bed_troughs.py."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bed_troughs as T  # noqa: E402


class Frame:
    def ll(self, x, y):
        return 50 + y / 1e5, 14 + x / 1e5

    def xy(self, lat, lon):
        return (lon - 14) * 1e5, (lat - 50) * 1e5


DATA = {"path": [[0.0, 0.0], [1000.0, 0.0]], "stops": [{"name": "A", "s": 0.0}, {"name": "B", "s": 600.0}]}


class Places(unittest.TestCase):
    def test_the_deepest_of_each_place_and_none_too_shallow(self):
        t = [[0, 0, 0.45, 1, 0.3], [20, 0, 0.9, 1, 0.5], [200, 0, 0.5, 2, -0.1], [400, 0, 0.3, 3, 0.2]]
        self.assertEqual(T.places(t, card_cm=40, same=50), [[20, 0, 0.9, 1, 0.5], [200, 0, 0.5, 2, -0.1]])

    def test_a_card_says_where_and_offers_the_answers_an_importer_reads(self):
        c = T.card("37", [550.0, 3.0, 0.62, 24, 0.4], Frame(), T.near_stop(DATA, 550.0, 3.0))
        self.assertEqual((c["kind"], c["mag"], c["line"]), ("bed trough", 62, "37"))
        self.assertIn("near B (route s 550, 3 m off the route)", c["info"])
        self.assertIn("40 cm over the bed's edge", c["info"])
        self.assertEqual([o for o in c["options"] if o in T.ANSWER], [T.REAL, T.WALL, T.OURS])


class Import(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "reports" / "review").mkdir(parents=True)
        (self.root / "reports" / "reviews").mkdir(parents=True)
        (self.root / "data").mkdir()
        (self.root / "data" / "truth.json").write_text('{\n "note": "x",\n "readers": {\n  "note": "y"\n }\n}\n', encoding="utf-8")
        c = T.card("37", [550.0, 3.0, 0.62, 24, 0.4], Frame(), "near B")
        (self.root / "reports" / "review" / "bed-troughs-37.json").write_text(json.dumps({"findings": [c]}), encoding="utf-8")
        (self.root / "reports" / "reviews" / "line37.json").write_text(json.dumps(
            {"items": {c["id"]: {"id": c["id"], "kind": "bed trough", "v": T.WALL, "t": 1794592958642, "note": "a wall"}}}),
            encoding="utf-8")
        self.old, T.ROOT = T.ROOT, self.root

    def tearDown(self):
        T.ROOT = self.old
        shutil.rmtree(self.root)

    def test_an_answer_becomes_a_fact_with_its_reader(self):
        T.do_import(["37"], "reports/reviews")
        truth = json.loads((self.root / "data" / "truth.json").read_text(encoding="utf-8"))
        (a,) = truth["bedTroughReview"]["answers"]
        self.assertEqual((a["answer"], a["note"], a["line"]), ("wall", "a wall", "37"))
        self.assertIn("2026-11-13", a["source"])
        self.assertEqual(truth["readers"]["bedTroughReview"], T.READER)


if __name__ == "__main__":
    unittest.main()
