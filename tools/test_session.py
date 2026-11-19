# SPDX-License-Identifier: AGPL-3.0-or-later
"""An issue's session started and finished (#727): python -I tools/test_session.py

The commands tools/session.py gives git and gh, on a fake runner: nothing is created or removed for real."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session  # noqa: E402


class Fake:
    """A runner that records the commands and answers the reads."""

    def __init__(self, issue=None, branches="", prs=None, dirty=""):
        self.issue = issue or {"title": "Checks: the stops check rides with the drive", "state": "OPEN",
                               "labels": [{"name": "lane:tooling"}, {"name": "agent:claude"}]}
        self.branches, self.prs, self.dirty, self.seen = branches, prs or [], dirty, []

    def __call__(self, *cmd, cwd=session.ROOT, check=True):
        self.seen.append(cmd)
        if cmd[:3] == ("gh", "issue", "view"):
            return json.dumps(self.issue), 0
        if cmd[:3] == ("git", "branch", "--list"):
            return self.branches, 0
        if cmd[:3] == ("gh", "pr", "list"):
            return json.dumps(self.prs), 0
        if cmd[:3] == ("git", "status", "--short"):
            return self.dirty, 0
        return "", 0

    def ran(self, *head):
        return [c for c in self.seen if c[:len(head)] == head]


class Slug(unittest.TestCase):
    def test_the_first_words_that_say_something(self):
        self.assertEqual(session.slug("Checks: the stops check rides with the drive"), "checks-stops-check")
        self.assertEqual(session.slug("The ground and the network as rebuild steps; one build ID"), "ground-network-rebuild")
        self.assertEqual(session.slug("dtm.py: a survey layer it does not know stops the build"), "dtm-py")
        self.assertEqual(session.slug("AGENTS.md to about 100 lines"), "agents-md-about")
        self.assertEqual(session.slug("…"), "work")


class Start(unittest.TestCase):
    def test_worktree_email_data_and_label_in_order(self):
        r, said = Fake(), []
        with mock.patch.object(session.os.path, "exists", return_value=False):
            wt, branch = session.start(708, name="stops-with-drive", run=r, out=said.append)
        self.assertEqual(branch, "708-stops-with-drive")
        self.assertTrue(wt.endswith("-708"))
        kinds = [c[:3] for c in r.seen]
        order = [("git", "worktree", "add"), ("git", "config", "user.email"), ("gh", "issue", "edit")]
        self.assertEqual([k for k in kinds if k in order], order)
        self.assertEqual(r.ran("git", "worktree", "add")[0][3:], ("-q", wt, "-b", branch, "origin/main"))
        self.assertTrue(any("data-fetch" in c for c in r.seen) and not any(c[-1] == "fetch" for c in r.seen))
        self.assertEqual(r.ran("gh", "issue", "edit")[0][-1], "agent:claude")
        self.assertIn("lane:tooling", said[0])

    def test_a_build_also_fetches_raw(self):
        r = Fake()
        with mock.patch.object(session.os.path, "exists", return_value=False):
            session.start(708, agent="codex", raw=True, run=r, out=lambda s: None)
        self.assertTrue(any(c[-1] == "fetch" for c in r.seen))
        self.assertEqual(r.ran("gh", "issue", "edit")[0][-1], "agent:codex")

    def test_refuses_a_closed_issue_an_existing_folder_or_branch(self):
        closed = Fake(issue={"title": "x", "state": "CLOSED", "labels": []})
        with self.assertRaises(SystemExit):
            session.start(1, run=closed)
        with mock.patch.object(session.os.path, "exists", return_value=True), self.assertRaises(SystemExit):
            session.start(708, run=Fake())
        r = Fake(branches="708-older-name")
        with mock.patch.object(session.os.path, "exists", return_value=False), self.assertRaises(SystemExit):
            session.start(708, run=r)
        self.assertFalse(r.ran("git", "worktree", "add"))


class Finish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(session, "folder", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def test_a_merged_clean_one_goes_with_its_label(self):
        r = Fake(branches="708-stops-with-drive", prs=[{"number": 744, "state": "MERGED"}])
        session.finish(708, run=r, out=lambda s: None)
        self.assertEqual(r.ran("git", "worktree", "remove")[0][-1], self.tmp.name)
        self.assertEqual(r.ran("git", "branch", "-D")[0][-1], "708-stops-with-drive")
        self.assertEqual(r.ran("gh", "issue", "edit")[0][-2:], ("--remove-label", "agent:claude"))

    def test_nothing_goes_while_the_pr_is_open_or_absent(self):
        for prs in ([], [{"number": 744, "state": "OPEN"}], [{"number": 1, "state": "MERGED"}, {"number": 2, "state": "OPEN"}],
                    [{"number": 3, "state": "CLOSED"}]):
            r = Fake(branches="708-stops-with-drive", prs=prs)
            with self.assertRaises(SystemExit):
                session.finish(708, run=r)
            self.assertFalse(r.ran("git", "worktree", "remove") or r.ran("git", "branch", "-D"), prs)

    def test_untracked_files_stop_it_until_discard(self):
        r = Fake(branches="708-stops-with-drive", prs=[{"number": 744, "state": "MERGED"}], dirty="?? reports/708/")
        with self.assertRaises(SystemExit) as e:
            session.finish(708, run=r)
        self.assertIn("reports/708/", str(e.exception))
        self.assertFalse(r.ran("git", "worktree", "remove"))
        session.finish(708, discard=True, run=r, out=lambda s: None)
        self.assertTrue(r.ran("git", "worktree", "remove"))

    def test_no_branch_and_no_merged_pr_no_work(self):
        with self.assertRaises(SystemExit):
            session.finish(708, run=Fake(branches=""))
        r = Fake(branches="", prs=[{"number": 9, "state": "MERGED", "headRefName": "7080-other"}])  # (another issue's)
        with self.assertRaises(SystemExit):
            session.finish(708, run=r)
        self.assertFalse(r.ran("gh", "issue", "edit"))

    def test_a_merge_that_took_the_branch_leaves_the_label_to_finish(self):
        """#748, #749: the worktree and the branch were gone when finish ran; it stopped and the label stayed."""
        prs = [{"number": 744, "state": "MERGED", "headRefName": "708-stops-with-drive"},
               {"number": 9, "state": "OPEN", "headRefName": "709-other"}]
        with mock.patch.object(session, "folder", return_value=os.path.join(self.tmp.name, "gone")):
            r, said = Fake(branches="", prs=prs), []
            session.finish(708, run=r, out=said.append)
        self.assertFalse(r.ran("git", "worktree", "remove") or r.ran("git", "branch", "-D"))
        self.assertEqual(r.ran("gh", "issue", "edit")[0][-2:], ("--remove-label", "agent:claude"))
        self.assertIn("gone already", said[0])
        # (the branch gone, the folder still there: its files are looked at as ever)
        r = Fake(branches="", prs=prs, dirty="?? reports/708/")
        with self.assertRaises(SystemExit):
            session.finish(708, run=r)
        self.assertFalse(r.ran("git", "worktree", "remove"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
