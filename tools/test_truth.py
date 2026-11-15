# SPDX-License-Identifier: AGPL-3.0-or-later
"""data/truth.json: every section names its reader, and the facts the code reads are there (#224):
python -I tools/test_truth.py"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import track_curve  # noqa: E402

TRUTH = json.load(open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8"))


class Truth(unittest.TestCase):
    def test_every_section_names_its_reader_or_that_it_is_reference(self):
        sections = set(TRUTH) - {"note", "readers"}
        self.assertEqual(sorted(sections - set(TRUTH["readers"])), [], "a section without a reader in `readers`")
        self.assertEqual(sorted(set(TRUTH["readers"]) - sections), [], "a reader of a section that is gone")

    def test_the_files_a_reader_names_exist(self):
        for section, text in TRUTH["readers"].items():
            for path in re.findall(r"\b((?:tools|src)/[\w./]+?\.(?:py|js))\b", text):
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), f"{section}: {path}")

    def test_the_radii_the_code_reads_are_facts(self):
        # (tools/track_curve.py, line_heights.py and lint.js read them instead of copying them)
        for fact, value in (("min-radius-network", 18), ("min-radius-passenger", 20), ("vertical-radius-street", 500)):
            self.assertEqual(track_curve.geometry_fact(fact), value, fact)
        self.assertEqual(track_curve.MIN_RADIUS, 18.0)
        lint = open(os.path.join(ROOT, "tools", "lint.js"), encoding="utf-8").read()
        for fact in ("min-radius-network", "min-radius-passenger", "vertical-radius-street"):
            self.assertIn(f"geometryFact(truth, '{fact}')", lint)

    def test_no_tool_counts_among_the_facts(self):
        # (counts a tool made go stale with the next snapshot: they belong in its output or in docs/knowledge.md)
        for s in TRUTH["sourceAccuracy"]["sources"]:
            self.assertFalse({"horizontalClasses", "heightClasses", "counted"} & set(s), s["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
