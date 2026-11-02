"""The nightly baseline's key, inputs, lock and decision (#157, #126): python -I tools/test_baseline_store.py"""
import datetime
import glob
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autodeploy  # noqa: E402
import baseline_store  # noqa: E402


class Store(unittest.TestCase):
    def test_key_depends_on_every_tree_not_their_order(self):
        a = {"src": "1", "data/MANIFEST.json": "2"}
        self.assertEqual(baseline_store.key(a), baseline_store.key(dict(reversed(list(a.items())))))
        self.assertNotEqual(baseline_store.key(a), baseline_store.key({**a, "src": "3"}))

    def test_a_heavy_job_is_busy_while_its_process_lives(self):
        child = subprocess.Popen([sys.executable, "-I", "-c",
                                  "import sys, time; sys.path.insert(0, sys.argv[1]); import baseline_store as b\n"
                                  "with b.HeavyJob('rebuild test'): print('in', flush=True); time.sleep(30)",
                                  os.path.dirname(os.path.abspath(__file__))], stdout=subprocess.PIPE, text=True)
        try:
            child.stdout.readline()
            self.assertTrue(any(b.startswith("rebuild test") for b in baseline_store.busy()))
        finally:
            child.kill()
            child.wait()
            child.stdout.close()
        self.assertFalse(baseline_store.alive(child.pid))
        self.assertFalse(any(b.startswith("rebuild test") for b in baseline_store.busy()))  # (its stale lock is dropped)

    def test_own_lock_is_not_busy(self):
        with baseline_store.HeavyJob("headless"):
            self.assertFalse(any(str(os.getpid()) in b for b in baseline_store.busy()))


class Inputs(unittest.TestCase):
    """The user's facts are measured like the code: truth.json alone changes a baseline's key (#126)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        for p, text in (("src/main.js", "1"), ("data/MANIFEST.json", "{}"), ("data/truth.json", '{"a": 1}')):
            os.makedirs(os.path.join(self.root, os.path.dirname(p)), exist_ok=True)
            self.write(p, text)
        self.commit()

    def write(self, p, text):
        with open(os.path.join(self.root, p), "w", encoding="utf-8") as f:
            f.write(text)

    def commit(self):
        for cmd in (["init", "-q"], ["add", "-A"],
                    ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"]):
            subprocess.run(["git", *cmd], cwd=self.root, check=True, capture_output=True)

    def test_a_truth_edit_is_dirty_and_then_a_new_key(self):
        before = baseline_store.trees("HEAD", root=self.root)
        self.assertEqual(baseline_store.dirty(root=self.root), "")
        self.write("data/truth.json", '{"a": 2}')
        self.assertIn("data/truth.json", baseline_store.dirty(root=self.root))  # (--baseline stops before any job)
        self.commit()
        after = baseline_store.trees("HEAD", root=self.root)
        self.assertEqual(before["src"], after["src"])
        self.assertNotEqual(baseline_store.key(before), baseline_store.key(after))

    def test_a_baseline_from_before_truth_was_measured_is_stale(self):
        now = baseline_store.trees("HEAD", root=self.root)
        old = {k: v for k, v in now.items() if k != "data/truth.json"}  # (measured_on of a run stored before #126)
        self.assertNotEqual(old, now)

    def test_every_fixed_data_file_the_game_loads_is_measured(self):
        # (a per-line file is covered by the manifest; a fixed one must be in it or in MEASURED)
        root = baseline_store.ROOT
        loaded = {m for p in glob.glob(os.path.join(root, "src", "*.js"))
                  for m in re.findall(r"['`](data/[a-z_]+\.json)['`]", open(p, encoding="utf-8").read())}
        manifest = {f"data/{f}" for f in json.load(open(os.path.join(root, "data", "MANIFEST.json"), encoding="utf-8"))["files"]}
        self.assertIn("data/truth.json", loaded)
        self.assertEqual(sorted(loaded - manifest - set(baseline_store.MEASURED)), [])


class Nightly(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        self.ran = []
        patches = [mock.patch.object(baseline_store, "trees", lambda rev, root=None: {"src": "a"}),
                   mock.patch.object(autodeploy, "run", lambda log, *cmd: self.ran.append(cmd) or 0),
                   mock.patch.object(autodeploy, "git", lambda *a: "abc1234")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.key = baseline_store.key({"src": "a"})

    def night(self, st, hour=2, published=False, busy=(), free=4):
        with mock.patch.object(baseline_store, "published", lambda k: published), \
             mock.patch.object(baseline_store, "busy", lambda: list(busy)), \
             mock.patch("sysinfo.workers", lambda gb: free):
            return autodeploy.nightly(self.log, st, datetime.datetime(2026, 11, 2, hour, 10))

    def test_only_at_night(self):
        self.night({}, hour=14)
        self.assertFalse(self.ran)

    def test_already_published_is_remembered(self):
        st = {}
        self.night(st, published=True)
        self.assertEqual((st["baseline"], self.ran), (self.key, []))

    def test_waits_for_a_heavy_job_or_memory(self):
        self.night({}, busy=["rebuild C:/x"])
        self.night({}, free=1)
        self.assertFalse(self.ran)
        self.assertIn("waits", self.log.getvalue())

    def test_measures_with_two_pages_and_tries_once_a_night(self):
        st = {}
        self.assertEqual(self.night(st), 1)  # (the stub publishes nothing)
        cmd = self.ran[0]
        self.assertIn("--publish", cmd)
        self.assertEqual(cmd[cmd.index("--jobs") + 1], "2")
        self.night(st)
        self.assertEqual(len([c for c in self.ran if "tools/headless.py" in c]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
