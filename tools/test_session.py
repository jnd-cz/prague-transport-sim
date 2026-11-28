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

    def __init__(self, issue=None, branches="", prs=None, dirty="", stacked=None, worktrees=""):
        self.issue = issue or {"title": "Checks: the stops check rides with the drive", "state": "OPEN",
                               "labels": [{"name": "lane:tooling"}, {"name": "agent:claude"}]}
        self.branches, self.prs, self.dirty, self.seen, self.stacked = branches, prs or [], dirty, [], stacked or []
        self.worktrees = worktrees  # (git worktree list --porcelain)

    def __call__(self, *cmd, cwd=session.ROOT, check=True):
        self.seen.append(cmd)
        if cmd[:3] == ("gh", "issue", "view"):
            return json.dumps(self.issue), 0
        if cmd[:3] == ("git", "branch", "--list"):
            return self.branches, 0
        if cmd[:3] == ("git", "worktree", "list"):
            return self.worktrees, 0
        if cmd[:3] == ("gh", "pr", "merge"):
            for p in self.prs:
                p["state"] = "MERGED"
        if cmd[:3] == ("gh", "pr", "list"):
            return json.dumps(self.stacked if "--base" in cmd else self.prs), 0
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


class Merge(unittest.TestCase):
    """merge N: everything checked before anything changes, then the squash, the finish, the remote branch."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(session, "folder", return_value=self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def pr(self, **more):
        return {"number": 744, "title": "Checks: stops with the drive (#708)", "state": "OPEN", "isDraft": True,
                "mergeable": "MERGEABLE", "statusCheckRollup": [{"name": "tools", "conclusion": "SUCCESS"},
                                                                {"context": "legacy", "state": "SUCCESS"}], **more}

    def test_a_draft_with_passed_checks_is_merged_under_its_title_and_finished(self):
        r, said = Fake(branches="708-stops-with-drive", prs=[self.pr()]), []
        session.merge(708, run=r, out=said.append)
        self.assertEqual(r.ran("gh", "pr", "ready")[0][-1], "744")
        m = r.ran("gh", "pr", "merge")[0]
        self.assertEqual(m[m.index("--subject") + 1], "Checks: stops with the drive (#708) (#744)")
        self.assertIn("--squash", m)
        self.assertNotIn("--delete-branch", m)  # (gh would remove the worktree with its untracked files)
        heads = [c[:3] for c in r.seen]
        self.assertLess(heads.index(("gh", "pr", "merge")), heads.index(("git", "worktree", "remove")))
        self.assertEqual(r.ran("git", "branch", "-D")[0][-1], "708-stops-with-drive")
        self.assertEqual(r.ran("git", "push")[0][-2:], ("--delete", "708-stops-with-drive"))
        self.assertEqual(r.ran("gh", "issue", "edit")[0][-2:], ("--remove-label", "agent:claude"))
        self.assertIn("merged as", said[0])

    def test_nothing_changes_while_something_is_in_the_way(self):
        cases = {"a PR standing on it": dict(prs=[self.pr()], stacked=[{"number": 745}]),
                 "a conflict": dict(prs=[self.pr(mergeable="CONFLICTING")]),
                 "a check running": dict(prs=[self.pr(statusCheckRollup=[{"name": "tools", "conclusion": ""}])]),
                 "a check failed": dict(prs=[self.pr(statusCheckRollup=[{"name": "tools", "conclusion": "FAILURE"}])]),
                 "untracked files": dict(prs=[self.pr()], dirty="?? reports/708/"),
                 "no open PR": dict(prs=[]),
                 "two open PRs": dict(prs=[self.pr(), self.pr(number=746)])}
        for what, kw in cases.items():
            r = Fake(branches="708-stops-with-drive", **kw)
            with self.assertRaises(SystemExit, msg=what):
                session.merge(708, run=r)
            self.assertFalse(r.ran("gh", "pr", "ready") or r.ran("gh", "pr", "merge") or r.ran("git", "worktree", "remove"), what)
        with self.assertRaises(SystemExit):
            session.merge(708, run=Fake(branches=""))

    def test_an_issue_with_two_branches_merges_the_one_named(self):
        """#228 had two PRs on two branches; merge 228 took the first and stopped on its conflict (#891)."""
        two = "708-stops-with-drive\n708-game-view"
        other = os.path.join(self.tmp.name, "other")
        os.mkdir(other)
        trees = (f"worktree {session.ROOT}\nHEAD 1\nbranch refs/heads/main\n\n"
                 f"worktree {self.tmp.name}\nHEAD 2\nbranch refs/heads/708-stops-with-drive\n\n"
                 f"worktree {other}\nHEAD 3\nbranch refs/heads/708-game-view\n")
        r = Fake(branches=two, prs=[self.pr()], worktrees=trees)
        with self.assertRaises(SystemExit) as e:
            session.merge(708, run=r)
        self.assertIn("708-stops-with-drive, 708-game-view: name one with --branch", str(e.exception))
        self.assertFalse(r.ran("gh", "pr", "list") or r.ran("gh", "pr", "merge"))
        with self.assertRaises(SystemExit):
            session.merge(708, run=r, named="709-other")
        self.assertFalse(r.ran("gh", "pr", "merge"))
        said = []
        session.merge(708, run=r, out=said.append, named="708-game-view")
        self.assertEqual(r.ran("gh", "pr", "list", "--head")[0][4], "708-game-view")
        self.assertEqual(r.ran("git", "worktree", "remove")[0][-1], os.path.normpath(other))  # (its own, not the issue's folder)
        self.assertEqual([c[-1] for c in r.ran("git", "branch", "-D")], ["708-game-view"])
        self.assertEqual(r.ran("git", "push")[0][-1], "708-game-view")
        self.assertFalse(r.ran("gh", "issue", "edit"), "the other branch's session keeps the label")
        self.assertIn("label stays for 708-stops-with-drive", said[-1])

    def test_a_named_branch_in_no_worktree_leaves_the_issues_folder(self):
        # (the issue's folder holds the other branch: a finish of the named one must not remove it)
        r = Fake(branches="708-stops-with-drive\n708-game-view", prs=[{"number": 744, "state": "MERGED"}],
                 worktrees=f"worktree {self.tmp.name}\nHEAD 2\nbranch refs/heads/708-stops-with-drive\n")
        session.finish(708, run=r, out=lambda s: None, named="708-game-view")
        self.assertFalse(r.ran("git", "worktree", "remove"))
        self.assertEqual(r.ran("git", "branch", "-D")[0][-1], "708-game-view")
        with self.assertRaises(SystemExit):
            session.finish(708, run=r)  # (two branches, none named)

    def test_the_files_listed_are_named_and_discard_goes_on(self):
        r = Fake(branches="708-stops-with-drive", prs=[self.pr(isDraft=False)], dirty="?? reports/708/")
        with self.assertRaises(SystemExit) as e:
            session.merge(708, run=r)
        self.assertIn("reports/708/", str(e.exception))
        session.merge(708, discard=True, run=r, out=lambda s: None)
        self.assertFalse(r.ran("gh", "pr", "ready"))  # (it was no draft)
        self.assertTrue(r.ran("gh", "pr", "merge") and r.ran("git", "worktree", "remove"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
