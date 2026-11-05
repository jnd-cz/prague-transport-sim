"""The review directory's index (#288): which files are sets, their issue and lines: python -I tools/test_review_sets.py"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review_sets  # noqa: E402

LINES = ["9", "17", "22", "23", "37"]


class Index(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(self.tmp.name, "reports", "review")
        os.makedirs(self.folder)

    def write(self, name, doc):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def sets(self):
        return {os.path.basename(s["file"]): s for s in review_sets.sets(self.folder, LINES)}

    def test_issue_and_lines_from_the_file_then_findings_then_the_name(self):
        self.write("stop-signs-17.json", {"issue": 258, "findings": [{"x": 1.0, "y": 2.0}]})
        self.write("crossings.json", {"issue": 146, "title": "Crossings", "findings": [{"x": 1, "y": 2, "line": 17}]})
        self.write("radius.json", {"issue": 197, "findings": [{"x": 1, "y": 2, "lines_near": [23, 9]}, {"x": 3, "y": 4, "lines_near": [23]}]})
        self.write("sources.json", {"issue": 20, "line": "17", "about": "Track sources", "findings": [{"x": 0, "y": 0}]})
        s = self.sets()
        self.assertEqual(s["stop-signs-17.json"]["lines"], ["17"])
        self.assertEqual((s["crossings.json"]["lines"], s["crossings.json"]["title"]), (["17"], "Crossings"))
        self.assertEqual(s["radius.json"]["lines"], ["9", "23"])
        self.assertEqual((s["sources.json"]["title"], s["sources.json"]["waitsFor"]), ("Track sources", 237))  # (#20 closed into #237)
        self.assertTrue(all(not x["unknown"] for x in s.values()))

    def test_a_span_queue_and_a_file_without_findings_are_not_sets(self):
        self.write("heights.json", {"span_file": "reports/review/spans.json", "findings": [{"x": 1, "y": 2, "kind": "trackheight", "id": "a"}]})
        self.write("spans.json", {"spans": [{"x": 1, "y": 2}]})
        self.write("calibration.json", {"groups": {"a": 1}})
        self.write("index.json", {"sets": [{"x": 1, "y": 2}]})
        self.assertEqual(sorted(self.sets()), ["heights.json"])

    def test_known_fills_what_a_tool_does_not_write_and_the_rest_is_listed_unknown(self):
        self.write("track-z.json", {"about": "Archived heights", "findings": [{"x": 1, "y": 2}]})
        self.write("mystery.json", {"findings": [{"x": 1, "y": 2}]})
        with mock.patch.dict(review_sets.KNOWN, {"track-z.json": {"issue": 106, "lines": ["17"]}}, clear=True):
            s = self.sets()
        self.assertEqual((s["track-z.json"]["issue"], s["track-z.json"]["lines"], s["track-z.json"]["title"]), (106, ["17"], "Archived heights"))
        self.assertEqual(s["mystery.json"]["unknown"], ["issue", "lines"])

    def test_build_without_github(self):
        self.write("a-9.json", {"issue": 1, "findings": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]})
        with mock.patch.object(review_sets, "lines_of", return_value=LINES):
            index = review_sets.build(self.tmp.name, github=False)
        self.assertEqual([(s["file"], s["findings"], s["lines"]) for s in index["sets"]], [("reports/review/a-9.json", 2, ["9"])])
        self.assertEqual((index["lines"], index["questions"]), (LINES, []))


class Committed(unittest.TestCase):
    def test_every_committed_set_names_its_issue_and_lines(self):
        unknown = [s["file"] for s in review_sets.sets() if s["unknown"]]
        self.assertEqual(unknown, [], "give the set's tool an issue and lines to write, or a KNOWN entry")

    def test_every_known_entry_is_a_set(self):
        names = {os.path.basename(s["file"]) for s in review_sets.sets()}
        self.assertEqual(sorted(set(review_sets.KNOWN) - names), [])


if __name__ == "__main__":
    unittest.main()
