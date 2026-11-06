"""The housekeeping report's parts (#290): dates issues wait for, the known-failures table, the sizes and
their change since the last pass: python -I tools/test_repo_health.py"""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_health as H  # noqa: E402

TODAY = datetime.date(2026, 11, 5)


class Dates(unittest.TestCase):
    def test_dates_an_issue_waits_for_within_a_week_or_past(self):
        text = ("**Time-bound:** part 1 before **10 Nov 2026, 22:00**; part 2 after **18 Nov 2026, 23:59**.\n"
                "Re-check after 2026-11-01. Built from 2026-10-30 data. Until 2027-01-01 nothing.")
        self.assertEqual(H.due(text, TODAY), [("after", "2026-11-01"), ("before", "2026-11-10")])

    def test_no_date_or_a_bad_one(self):
        self.assertEqual(H.due("before 31 Feb 2026, after the merge", TODAY), [])
        self.assertEqual(H.due(None, TODAY), [])


class KnownFailures(unittest.TestCase):
    def test_rows_with_an_issue(self):
        md = ("## Known failures (not caused by your change)\n\n| check | line | symptom | issue |\n|---|---|---|---|\n"
              "| page load | lines without them | 404s | (expected) |\n| crossing | 17 | 1 obstruction | #146 |\n\n## Code style\n| a | #9 |\n")
        self.assertEqual(H.known_failures(md), [("crossing / 17", 146)])


class Sizes(unittest.TestCase):
    def test_largest_files_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            for p, n in (("src/a.js", 30), ("src/b.js", 10), ("tools/x.py", 5), ("tools/test_x.py", 3), ("README.md", 7)):
                os.makedirs(os.path.join(d, os.path.dirname(p)), exist_ok=True)
                with open(os.path.join(d, p), "w", encoding="utf-8") as f:
                    f.write("x\n" * n)
            s = H.sizes(d, top=1)
        self.assertEqual((s["src"], s["srcTotal"], s["toolFiles"], s["testFiles"], s["docs"]),
                         ({"src/a.js": 30}, 40, 1, 1, {"README.md": 7}))

    def test_deltas_only_for_what_changed(self):
        before = {"src": {"src/a.js": 30, "src/b.js": 10}, "srcTotal": 40, "toolFiles": 1, "testFiles": 1}
        now = {"src": {"src/a.js": 35, "src/c.js": 4}, "srcTotal": 49, "toolFiles": 1, "testFiles": 2, "tools": {}, "docs": {}}
        self.assertEqual(H.deltas(now, before), {"src/a.js": 5, "srcTotal": 9, "testFiles": 1})


class Markdown(unittest.TestCase):
    def test_the_hidden_block_round_trips_and_changes_show(self):
        h = {"date": "2026-11-09", "commit": "abc", "sizes": {"src": {"src/a.js": 35}, "srcTotal": 35, "tools": {}, "toolFiles": 1,
                                                            "testFiles": 2, "docs": {}},
             "work": {"prs": [{"pr": 1, "title": "t", "draft": True, "idle_h": 60}], "issues": 3, "lanes": {"sim": 2, "none": 1},
                      "halfDone": [21], "parked": 0, "needsUser": 1, "rebuildLabel": []},
             "reviews": {"sets": 1, "findings": 2, "issueClosed": []}, "leftovers": {"worktreesDone": [], "worktreesStale": [], "branches": []},
             "knownFailuresClosed": [], "dated": [], "ci": {"runs": 1, "median_s": 30, "max_s": 30, "failed": 0}}
        before = {"date": "2026-11-02", "sizes": {"src": {"src/a.js": 30}, "srcTotal": 30, "testFiles": 1}}
        md = H.markdown(h, before)
        self.assertIn("`src/a.js` 35 (+5)", md)
        self.assertIn("against 2026-11-02", md)
        self.assertIn("idle 60 h: #1 t", md)
        self.assertIn("1 issues without a lane", md)
        block = md.rsplit("<!-- " + H.MARK + " ", 1)[1].rsplit(" -->", 1)[0]
        self.assertEqual(__import__("json").loads(block)["sizes"]["src"], {"src/a.js": 35})


class Branches(unittest.TestCase):
    def test_only_branches_on_the_remote_whose_pr_is_finished(self):
        ls = "aaa\trefs/heads/main\nbbb\trefs/heads/20-di-lines\nccc\trefs/heads/202-open\n"
        self.assertEqual(H.finished_on_remote(ls, {"20-di-lines", "gone-from-the-remote"}), ["20-di-lines"])

    def test_no_answer_from_the_remote_is_none(self):
        self.assertEqual(H.finished_on_remote(None, {"x"}), [])


if __name__ == "__main__":
    unittest.main()
