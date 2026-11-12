# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/autodeploy.py on a temp origin and deploy clone: python -I tools/test_autodeploy.py

The deploy cycle runs with nightly() replaced by a recorder, so the hour the test runs at does not matter (#323:
between 01:00 and 05:00 the real night step ran and every run failed); NightlyTest gives nightly() its own clock
(now=) and stand-ins for the baseline store."""
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autodeploy  # noqa: E402

# stand-ins for the clone's snapshot.py and deploy.py: append their name to calls.txt ("pull" for
# deploy.py --pull); a deploy fails when fail.txt exists, a pull when pullfail.txt does
STUB = """import os, sys
pull = "--pull" in sys.argv
open("calls.txt", "a").write(("pull" if pull else os.path.basename(__file__)) + "\\n")
sys.exit(1 if os.path.exists("pullfail.txt" if pull else "fail.txt") and __file__.endswith("deploy.py") else 0)
"""


def sh(cwd, *cmd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class AutodeployTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.work, self.dep = os.path.join(self.tmp, "work"), os.path.join(self.tmp, "deploy")
        sh(self.tmp, "git", "init", "-q", "--bare", "-b", "main", "origin.git")
        sh(self.tmp, "git", "clone", "-q", "origin.git", "work")
        for k, v in (("user.email", "t@example"), ("user.name", "t")):
            sh(self.work, "git", "config", k, v)
        os.mkdir(os.path.join(self.work, "tools"))
        for f in ("snapshot.py", "deploy.py"):
            open(os.path.join(self.work, "tools", f), "w").write(STUB)
        open(os.path.join(self.work, ".gitignore"), "w").write("calls.txt\nfail.txt\nreports/\ndeploy.local.json\n")
        self.commit("first")
        sh(self.tmp, "git", "clone", "-q", "origin.git", "deploy")
        open(os.path.join(self.dep, "deploy.local.json"), "w").write("{}")
        os.mkdir(os.path.join(self.dep, "reports"))
        p = {"ROOT": self.dep, "CONFIG": os.path.join(self.dep, "deploy.local.json"),
             "LOG": os.path.join(self.dep, "reports", "autodeploy.log"),
             "STATE": os.path.join(self.dep, "reports", "autodeploy.json")}
        self.patches = [mock.patch.object(autodeploy, k, v) for k, v in p.items()]
        # (the night step stands apart, NightlyTest: here it only records that a deployed main reached it)
        self.nights = []
        self.patches.append(mock.patch.object(autodeploy, "nightly", lambda log, st, now=None: self.nights.append(st.get("deployed")) or 0))
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def commit(self, msg):
        open(os.path.join(self.work, "f.txt"), "a").write(msg)
        sh(self.work, "git", "add", "-A")
        sh(self.work, "git", "commit", "-q", "-m", msg)
        sh(self.work, "git", "push", "-q", "origin", "main")
        return sh(self.work, "git", "rev-parse", "HEAD")

    def calls(self):
        p = os.path.join(self.dep, "calls.txt")
        out = open(p).read().split() if os.path.exists(p) else []
        if os.path.exists(p):
            os.remove(p)
        return out

    def test_cycle(self):
        self.assertEqual(autodeploy.main([]), 2, "a branch checked out: left alone")
        self.assertEqual(self.calls(), [])
        sh(self.dep, "git", "checkout", "-q", "--detach")
        c2 = self.commit("second")
        self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py", "pull"])
        self.assertEqual(sh(self.dep, "git", "rev-parse", "HEAD"), c2)
        self.assertEqual(self.nights, [c2], "the night step after the deploy")
        self.assertEqual(autodeploy.main([]), 0, "nothing new")
        self.assertEqual(self.calls(), ["pull"], "nothing new: only the reviews")
        # a failing deploy: recorded, not retried at once, retried after RETRY
        open(os.path.join(self.dep, "fail.txt"), "w").write("")
        c3 = self.commit("third")
        self.assertEqual(autodeploy.main([]), 1)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py", "pull"])
        self.assertEqual(json.load(open(autodeploy.STATE))["failed"], c3)
        self.assertEqual(self.nights[-1], c2, "not after a failed deploy")
        nights = len(self.nights)
        self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), ["pull"], "the failed deploy waits, the pull does not")
        os.remove(os.path.join(self.dep, "fail.txt"))
        with mock.patch.object(autodeploy, "RETRY", 0):
            self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py", "pull"])
        st = json.load(open(autodeploy.STATE))
        self.assertEqual((st["deployed"], "failed" in st), (c3, False))
        # (while c3 fails, the checkout is at c3 and the deployed main still c2: no night run on a checkout that is
        # not what the site serves)
        self.assertEqual(self.nights[nights:], [c3], "the night step again only once c3 is up")
        self.assertIn("third", open(autodeploy.LOG).read())

    def test_pull_failure_waits(self):
        sh(self.dep, "git", "checkout", "-q", "--detach")
        open(os.path.join(self.dep, "pullfail.txt"), "w").write("")
        self.assertEqual(autodeploy.main([]), 1)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py", "pull"])
        self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), [], "no FTP login for an hour after a failed one")
        with mock.patch.object(autodeploy, "RETRY", 0):
            self.assertEqual(autodeploy.main([]), 1)
        self.assertEqual(self.calls(), ["pull"])

    def test_not_a_deploy_checkout(self):
        os.remove(autodeploy.CONFIG)
        self.assertEqual(autodeploy.main([]), 2)


class NightlyTest(unittest.TestCase):
    """nightly() at a given hour (its now= argument), the baseline store and the measuring run stood in for."""

    def setUp(self):
        import baseline_store
        import sysinfo
        self.runs, self.store = [], {"published": False, "busy": []}
        self.patches = [
            mock.patch.object(autodeploy, "run", lambda log, *cmd: self.runs.append(cmd) or 0),
            mock.patch.object(autodeploy, "git", lambda *a: "abc1234"),
            mock.patch.object(baseline_store, "trees", lambda rev, root=None: {}),
            mock.patch.object(baseline_store, "key", lambda t: "k1"),
            mock.patch.object(baseline_store, "published", lambda k: self.store["published"]),
            mock.patch.object(baseline_store, "busy", lambda: self.store["busy"]),
            mock.patch.object(sysinfo, "workers", lambda gb, most=4: 4),
        ]
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()

    def at(self, hour, st, day=11):
        return autodeploy.nightly(io.StringIO(), st, now=datetime.datetime(2026, 11, day, hour))

    def test_only_at_night_and_once_a_night(self):
        # (the hours from NIGHT itself, whatever it is set to)
        night, day = list(autodeploy.NIGHT), [h for h in range(24) if h not in autodeploy.NIGHT]
        st = {}
        for hour in day:
            self.assertEqual(self.at(hour, st), 0)
        self.assertEqual(self.runs, [], "outside NIGHT nothing runs")
        self.assertEqual(self.at(night[0], st), 1, "measured, not published")
        self.assertEqual(len(self.runs), 1)
        self.assertIn("--baseline", self.runs[0])
        self.assertEqual(st["baseline_tried"], ["k1", "2026-11-11"])
        self.assertEqual(self.at(night[-1], st), 0)
        self.assertEqual(len(self.runs), 1, "not again the same night")
        self.store["published"] = True
        self.assertEqual(self.at(night[0], st, day=12), 0)
        self.assertEqual((len(self.runs), st["baseline"]), (1, "k1"), "published meanwhile: recorded, not measured")

    def test_waits_for_a_heavy_job(self):
        self.store["busy"] = ["headless.py (pid 1)"]
        self.assertEqual(self.at(autodeploy.NIGHT[0], {}), 0)
        self.assertEqual(self.runs, [])


if __name__ == "__main__":
    unittest.main()
