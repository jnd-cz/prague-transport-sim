# SPDX-License-Identifier: AGPL-3.0-or-later
"""A pull request names its issue in its title and its text (tools/pr_text.py, #727), and every source file starts with
the licence's line (AGENTS.md, Code and docs). python -I tools/test_pr_text.py"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import pr_text  # noqa: E402


class Text(unittest.TestCase):
    def test_a_title_with_its_issue_and_a_text_with_the_keyword_pass(self):
        self.assertEqual(pr_text.problems("Seeded compares measured at the merge base (#709)", "Closes #709.\n\n**Verdict:** …"), [])
        self.assertEqual(pr_text.problems("Paved yards meet the sidewalks (#638)", "Stands on #743: merge it first. Part of #638. More"), [])

    def test_what_is_missing_is_said(self):
        self.assertEqual(len(pr_text.problems("Fix things", "No issue here")), 2)
        self.assertIn("title", pr_text.problems("Fix things", "Closes #5.")[0])
        self.assertIn("neither", pr_text.problems("Fix things (#5)", "It closes the gap of #5")[0])
        self.assertEqual(pr_text.problems(None, None).__len__(), 2)

    def test_the_title_and_the_text_name_the_same_issue(self):
        bad = pr_text.problems("Fix things (#5)", "Part of #6.")
        self.assertEqual(bad, ["the title names #5, the text Part of #6"])
        self.assertEqual(pr_text.problems("Fix things (#5)", "Part of #6. Closes #5."), [])

    def test_the_events_pull_request_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "event.json")
            for pr, code in (({"title": "A (#1)", "body": "Closes #1."}, 0), ({"title": "A", "body": None}, 1)):
                with open(p, "w", encoding="utf-8") as f:
                    json.dump({"pull_request": pr}, f)
                with mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": p}), mock.patch("builtins.print"):
                    self.assertEqual(pr_text.main([]), code)


class LicenceLine(unittest.TestCase):
    def test_every_source_file_starts_with_it(self):
        """In its first three lines (a shebang or a doctype may stand before it)."""
        missing = []
        for pattern in ("src/*.js", "tools/*.py", "tools/*.js", "tools/*.php", "tools/bench/*.py", "tools/bench/*.js"):
            for p in sorted(ROOT.glob(pattern)):
                with open(p, encoding="utf-8", errors="replace") as f:
                    head = [f.readline() for _ in range(3)]
                if not any("SPDX-License-Identifier: AGPL-3.0-or-later" in line for line in head):
                    missing.append(p.relative_to(ROOT).as_posix())
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
