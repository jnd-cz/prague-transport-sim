# SPDX-License-Identifier: AGPL-3.0-or-later
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
import time
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
                                  "with b.HeavyJob('rebuild test', wait=False): print('in', flush=True); time.sleep(30)",
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
        with baseline_store.HeavyJob("headless", wait=False):  # (wait=False: not behind this machine's real jobs)
            self.assertFalse(any(str(os.getpid()) in b for b in baseline_store.busy()))


class Ticket(unittest.TestCase):
    def test_a_ticket_being_read_elsewhere_is_replaced_on_a_later_try(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d):
            real, tries = os.replace, []

            def busy(a, b):
                tries.append(a)
                if len(tries) < 3:
                    raise PermissionError(5, "Access is denied")
                real(a, b)
            job = baseline_store.HeavyJob("test", wait=False)
            job.path = os.path.join(d, "1.lock")
            with mock.patch.object(baseline_store.os, "replace", busy), mock.patch.object(baseline_store.time, "sleep"):
                job._write("running")
            self.assertEqual(len(tries), 3)
            self.assertTrue(os.path.exists(job.path))

    def test_it_gives_up_in_the_end(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d):
            job = baseline_store.HeavyJob("test", wait=False)
            job.path = os.path.join(d, "1.lock")
            with mock.patch.object(baseline_store.os, "replace", side_effect=PermissionError(5, "x")), \
                    mock.patch.object(baseline_store.time, "sleep"), self.assertRaises(PermissionError):
                job._write("running")


class Checkpoints(unittest.TestCase):
    """Names, the index and what this machine keeps by key (#282); the store's files in a dict."""
    def test_latest_is_the_highest_world_checkpoint_never_a_test(self):
        self.assertEqual(baseline_store.latest_checkpoint({"W2": {}, "W10": {}, "TEST-282": {}, "W1": {}}), "W10")
        self.assertIsNone(baseline_store.latest_checkpoint({"TEST-282": {}}))
        self.assertIsNone(baseline_store.latest_checkpoint({}))

    def test_publish_lists_it_and_keeps_the_others(self):
        files = {"checkpoints.json": {"W1": {"key": "a", "commit": "1", "time": "t"}}}
        with mock.patch.object(baseline_store, "_put", files.update), \
                mock.patch.object(baseline_store, "fetch", lambda n: (files.get(f"{n}.json"), files.get(f"{n}.places.json"))):
            baseline_store.publish_checkpoint("W2", "b", {"r": 1}, {"r": 2}, "abc")
            self.assertEqual(sorted(baseline_store.checkpoints()), ["W1", "W2"])
            self.assertEqual(baseline_store.checkpoints()["W2"]["key"], "b")
            self.assertEqual(baseline_store.fetch_checkpoint("W2"), ({"r": 1}, {"r": 2}))

    def test_a_bad_name_is_refused(self):
        with self.assertRaises(ValueError):
            baseline_store.publish_checkpoint("../W1", "k", {}, {}, "c")

    def test_kept_accumulates_by_key_on_this_machine(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"TRAMDATA_CACHE": d}):
            self.assertEqual(baseline_store.kept("k"), ({}, {}))
            baseline_store.keep("k", {"a": 1}, {"a": 2})
            baseline_store.keep("k", {"b": 3}, {})
            self.assertEqual(baseline_store.kept("k"), ({"a": 1, "b": 3}, {"a": 2}))
            self.assertEqual(baseline_store.kept("other"), ({}, {}))

    def test_measure_at_reads_the_pinned_worktree_and_removes_it(self):
        want = {"src": "s"}
        seen = []

        def run(cmd, cwd=None, **kw):
            seen.append(cmd)
            if cmd[:3] == ["git", "worktree", "add"]:
                self.wt = cmd[5]
                os.makedirs(os.path.join(self.wt, "reports", "baseline"))
            if "tools/headless.py" in cmd:
                with open(os.path.join(cwd, "reports", "baseline", "headless.json"), "w", encoding="utf-8") as f:
                    json.dump({"line9-lint": {"counts": {"n": 1}, "measured_on": want},
                               "line9-surfaces": {"counts": {"n": 2}, "measured_on": {"src": "older"}},
                               "line17-lint": {"counts": {"n": 3}, "measured_on": want}}, f)
                with open(os.path.join(cwd, "reports", "baseline", "headless-places.json"), "w", encoding="utf-8") as f:
                    json.dump({"line9-lint": {"x": []}, "line17-lint": {"y": []}}, f)
            return mock.Mock(returncode=0)
        counts, places = baseline_store.measure_at("abcdef0123", ["9"], ["lint", "surfaces"], want, run=run, out=io.StringIO())
        self.assertEqual(list(counts), ["line9-lint"])  # (not another line's, nor one measured on older trees)
        self.assertEqual(places, {"line9-lint": {"x": []}})
        self.assertIn(["git", "worktree", "remove", "--force", self.wt], seen)
        self.assertFalse(os.path.exists(self.wt))


TOOLS = os.path.dirname(os.path.abspath(__file__))
JOB = ("import os, sys, time; sys.path.insert(0, sys.argv[1]); import baseline_store as b\n"
       "b.HeavyJob.POLL = 0.1\n"
       "with b.HeavyJob(sys.argv[2]):\n"
       "    print('in', flush=True)\n"
       "    while not os.path.exists(sys.argv[3]): time.sleep(0.05)\n")


class Queue(unittest.TestCase):
    """Heavy jobs take turns, first come first served (#280), in a lock folder of the test's own."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        locks = os.path.join(self.tmp.name, "tram-heavy")
        patch = mock.patch.object(baseline_store, "LOCKS", locks)
        patch.start()
        self.addCleanup(patch.stop)
        # (the children's tempfile.gettempdir() is the test's folder, so their LOCKS is the same)
        self.env = {**os.environ, "TMP": self.tmp.name, "TEMP": self.tmp.name, "TMPDIR": self.tmp.name}
        self.env.pop(baseline_store.HELD, None)
        self.env.pop("TRAM_HEAVY_NOWAIT", None)
        self.kids = []

    def job(self, name):
        release = os.path.join(self.tmp.name, f"release-{name}")
        p = subprocess.Popen([sys.executable, "-I", "-c", JOB, TOOLS, name, release], env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.kids.append(p)
        self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close(), p.stderr.close()))
        return p, release

    def wait_for(self, cond, secs=20):
        t = datetime.datetime.now()
        while not cond():
            if (datetime.datetime.now() - t).total_seconds() > secs:
                self.fail("timed out")
            time.sleep(0.05)

    def states(self):
        return [(j["what"], j["state"]) for j in baseline_store.queue()]

    def test_the_second_job_waits_for_the_first_then_runs(self):
        a, release_a = self.job("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, release_b = self.job("b")
        self.wait_for(lambda: self.states() == [("a", "running"), ("b", "waiting")])
        open(release_a, "w").close()
        self.assertEqual(b.stdout.readline().strip(), "in")  # (b runs once a has ended)
        self.assertEqual(a.wait(10), 0)
        self.assertEqual(self.states(), [("b", "running")])
        open(release_b, "w").close()
        self.assertEqual(b.wait(10), 0)
        err = b.stderr.read()
        self.assertIn("b waits for a in ", err)
        self.assertIn("b starts after", err)

    def test_a_dead_jobs_ticket_is_dropped(self):
        a, _ = self.job("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        a.kill()
        a.wait()
        self.assertEqual(self.states(), [])

    def test_nowait_runs_beside_and_a_step_runs_in_its_parents_turn(self):
        a, release_a = self.job("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        before = os.environ.get(baseline_store.HELD)  # (test_all.py's turn when the suite runs: #585 puts it back)
        with baseline_store.HeavyJob("now", wait=False):
            self.assertEqual(sorted(self.states()), [("a", "running"), ("now", "running")])
            step = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                                   "import baseline_store as b; print(b.HeavyJob('step').wait)", TOOLS],
                                  env={**self.env, baseline_store.HELD: os.environ[baseline_store.HELD]},
                                  capture_output=True, text=True)
            self.assertEqual(step.stdout.strip(), "False")
        self.assertEqual(os.environ.get(baseline_store.HELD), before)
        open(release_a, "w").close()

    def test_a_nested_jobs_end_keeps_its_parents_turn(self):
        # (#585: headless.py ends its turn before measuring main's baseline; inside heavy.py its end deleted HELD, and
        # the measuring child queued behind its own grandparent for 8 h)
        old = os.environ.get(baseline_store.HELD)
        self.addCleanup(lambda: os.environ.pop(baseline_store.HELD, None) if old is None
                        else os.environ.__setitem__(baseline_store.HELD, old))
        os.environ[baseline_store.HELD] = str(os.getppid())  # (a live process's turn: the one that started the test)
        with baseline_store.HeavyJob("inner") as j:
            self.assertFalse(j.wait)
            self.assertEqual(os.environ[baseline_store.HELD], str(os.getpid()))
        self.assertEqual(os.environ[baseline_store.HELD], str(os.getppid()))

    def test_a_job_never_waits_for_a_process_that_started_it(self):
        self.assertIn(os.getppid(), baseline_store.ancestors())
        with baseline_store.HeavyJob("outer", wait=False):
            # (the child's environment has lost HELD, as a tool starting it with a clean one would)
            inner, release = self.job("inner")
            self.wait_for(lambda: sorted(self.states()) == [("inner", "running"), ("outer", "running")])
            self.assertEqual(inner.stdout.readline().strip(), "in")
            open(release, "w").close()
            self.assertEqual(inner.wait(10), 0)
        self.assertIn("inner runs in the turn of outer", inner.stderr.read())

    def test_an_older_tools_lock_counts_as_running(self):
        os.makedirs(baseline_store.LOCKS)
        with open(os.path.join(baseline_store.LOCKS, f"{os.getpid()}.lock"), "w", encoding="utf-8") as f:
            f.write("headless C:/x/transport-game-268\n")
        j, = baseline_store.queue()
        self.assertEqual((j["what"], j["state"], j["root"]), ("headless", "running", "C:/x/transport-game-268"))
        self.assertEqual(baseline_store.describe(j, j["since"] + 600), "headless in transport-game-268, running 10 min")
        # (a ticket written just after the board read the clock)
        self.assertEqual(baseline_store.describe(j, j["since"] - 1), "headless in transport-game-268, running 0 min")


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
