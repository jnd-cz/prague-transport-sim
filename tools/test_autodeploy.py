"""tools/autodeploy.py on a temp origin and deploy clone: python -I tools/test_autodeploy.py"""
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

# stand-ins for the clone's snapshot.py and deploy.py: append their name to calls.txt, fail when fail.txt exists
STUB = """import os, sys
open("calls.txt", "a").write(os.path.basename(__file__) + "\\n")
sys.exit(1 if os.path.exists("fail.txt") and __file__.endswith("deploy.py") else 0)
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
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py"])
        self.assertEqual(sh(self.dep, "git", "rev-parse", "HEAD"), c2)
        self.assertEqual(autodeploy.main([]), 0, "nothing new")
        self.assertEqual(self.calls(), [])
        # a failing deploy: recorded, not retried at once, retried after RETRY
        open(os.path.join(self.dep, "fail.txt"), "w").write("")
        c3 = self.commit("third")
        self.assertEqual(autodeploy.main([]), 1)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py"])
        self.assertEqual(json.load(open(autodeploy.STATE))["failed"], c3)
        self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), [])
        os.remove(os.path.join(self.dep, "fail.txt"))
        with mock.patch.object(autodeploy, "RETRY", 0):
            self.assertEqual(autodeploy.main([]), 0)
        self.assertEqual(self.calls(), ["snapshot.py", "deploy.py"])
        st = json.load(open(autodeploy.STATE))
        self.assertEqual((st["deployed"], "failed" in st), (c3, False))
        self.assertIn("third", open(autodeploy.LOG).read())

    def test_not_a_deploy_checkout(self):
        os.remove(autodeploy.CONFIG)
        self.assertEqual(autodeploy.main([]), 2)


if __name__ == "__main__":
    unittest.main()
