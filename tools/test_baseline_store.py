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

    def test_measure_at_runs_seeded_checks_with_their_seeds(self):
        """#709: the seeds go to the pinned worktree's run, and the runs are read by their seeded names."""
        want = {"src": "s"}
        seen = []

        def run(cmd, cwd=None, **kw):
            seen.append(cmd)
            if cmd[:3] == ["git", "worktree", "add"]:
                os.makedirs(os.path.join(cmd[5], "reports", "baseline"))
            if "tools/headless.py" in cmd:
                with open(os.path.join(cwd, "reports", "baseline", "headless.json"), "w", encoding="utf-8") as f:
                    json.dump({"line9-u3-seed1": {"counts": {"n": 1}, "measured_on": want},
                               "line9-u3-seed2": {"counts": {"n": 2}, "measured_on": want},
                               "line9-u3-seed3": {"counts": {"n": 3}, "measured_on": want},
                               "line9-lint": {"counts": {"n": 4}, "measured_on": want}}, f)
            return mock.Mock(returncode=0)
        counts, _ = baseline_store.measure_at("abcdef0123", ["9"], ["u3"], want, run=run, out=io.StringIO(), seeds=[1, 2])
        self.assertEqual(sorted(counts), ["line9-u3-seed1", "line9-u3-seed2"])  # (the seeds asked, no seedless run)
        cmd = next(c for c in seen if "tools/headless.py" in c)
        self.assertEqual(cmd[cmd.index("--seeds") + 1], "1,2")


TOOLS = os.path.dirname(os.path.abspath(__file__))
# (a job that holds its turn until a file appears. argv[4]: the test's settings, run first: `share` for a shared job,
# `spin` for what it does meanwhile, the queue's constants)
JOB = ("import os, sys, time; sys.path.insert(0, sys.argv[1]); import baseline_store as b\n"
       "b.HeavyJob.POLL = 0.1\n"
       "share, expect, spin = None, None, lambda: time.sleep(0.05)\n"
       "exec(sys.argv[4])\n"
       "with b.HeavyJob(sys.argv[2], share=share, expect=expect):\n"
       "    print('in', flush=True)\n"
       "    while not os.path.exists(sys.argv[3]): spin()\n")
# (a machine of the test's own: 8 cores, 40 GB free, 2 kept)
MACHINE = "b.HeavyJob.FREE = staticmethod(lambda: 40.0); b.HeavyJob.CORES = 8; b.HeavyJob.KEEP = 2.0; "


class DayAndNight(unittest.TestCase):
    """#851: by day a long job, or one of unknown time, waits for the night and stands ahead of none meanwhile; a short
    one goes before longer ones queued earlier, but not before one that has waited PASS_MAX."""
    def setUp(self):  # (a lock folder of the test's own: no early night of this machine's, heavy.py --night)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        locks = mock.patch.object(baseline_store, "LOCKS", self.tmp.name)
        locks.start()
        self.addCleanup(locks.stop)

    def at(self, h, m=0):
        lt = time.localtime()
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))

    def job(self, **kw):
        with mock.patch.dict(os.environ):
            os.environ.pop(baseline_store.DAY, None)
            return baseline_store.HeavyJob("j", wait=False, kind="a kind never run", **kw)

    def ticket(self, what, pid, t, **kw):
        return {"what": what, "root": "C:/x/transport-game-1", "pid": pid, "t": t, "state": "waiting", "since": t,
                "share": None, "queue": baseline_store.QUEUE, **kw}

    def test_the_night_hours(self):
        self.assertEqual([baseline_store.night(self.at(h)) for h in (6, 7, 12, 22, 23, 2)],
                         [True, False, False, False, True, True])
        self.assertEqual(baseline_store.night_starts(self.at(14)), self.at(23))
        self.assertEqual(baseline_store.night_starts(self.at(23, 30)), self.at(23, 30))

    def test_by_day_a_long_job_or_one_of_unknown_time_waits_for_the_night(self):
        noon, late = self.at(12), self.at(23, 30)
        self.assertIn("expected 40 min, over 30 by day", self.job(expect=2400).night_hold(noon, []))
        self.assertIn("its time is not known", self.job().night_hold(noon, []))
        self.assertEqual(self.job(expect=1500).night_hold(noon, []), "")  # (the suite with the page tests: 24 min)
        self.assertEqual(self.job(expect=2400).night_hold(late, []), "")
        self.assertEqual(self.job(expect=2400, day=True).night_hold(noon, []), "")
        with mock.patch.dict(os.environ, {baseline_store.DAY: "1"}):
            self.assertTrue(baseline_store.HeavyJob("j", wait=False).day)  # (TRAM_HEAVY_DAY=1: the user's word)

    def test_the_short_ones_first_but_not_before_one_waiting_two_hours(self):
        now = self.at(12)
        long = self.ticket("long", 1, now - 600, expect=3600)
        short = self.ticket("short", 2, now - 60, expect=300)
        unknown = self.ticket("unknown", 3, now - 900)
        rank = lambda j: baseline_store.rank(j, now, [])  # noqa: E731
        self.assertLess(rank(short), rank(long))
        self.assertLess(rank(short), rank(unknown))
        self.assertLess(rank(unknown), rank(long))  # (first come first among the longer ones)
        self.assertLess(rank(dict(long, t=now - 7300)), rank(short))

    def test_a_held_job_stands_ahead_of_none_and_the_board_shows_it(self):
        now = time.time()
        held = self.ticket("long", 1, now - 600, expect=3600, held=True)
        me = self.job(expect=60)
        me.t = now
        with mock.patch.object(baseline_store, "queued_turns", lambda: [held]), \
                mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual(me.ahead(), [])
        with mock.patch.object(baseline_store, "queued_turns", lambda: [dict(held, held=False, expect=60)]), \
                mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual([j["what"] for j in me.ahead()], ["long"])  # (not held, as short and first: ahead)
        self.assertTrue(baseline_store.describe(held, now).endswith(", held for the night"))
        noon = self.at(12)
        got = baseline_store.schedule([dict(held, t=noon - 600, since=noon - 600), self.ticket("b", 2, noon - 60, expect=300)],
                                      noon, records=[])
        self.assertEqual({j["what"]: j["start"] for j in got}, {"long": self.at(23), "b": noon})

    def test_a_held_jobs_ticket_is_queued_at_the_night_so_an_older_checkout_passes_it(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d):
            j = self.job(expect=2400)
            j.t, j.parked = time.time(), "expected 40 min"
            j._write("waiting")
            got, = baseline_store.queue()
            j.parked = ""
            j._write("waiting")
            back, = baseline_store.queue()
            os.remove(j.path)
        self.assertTrue(got["held"])
        self.assertAlmostEqual(got["t"], baseline_store.night_starts(), delta=5)  # (at night "now": read twice, #854)
        self.assertEqual((back["held"], back["t"]), (False, j.t))

    def test_the_night_started_early_on_the_users_word(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d):
            noon = self.at(12)
            self.assertFalse(baseline_store.night(noon))
            e = baseline_store.start_night(noon)
            lt = time.localtime(noon + 86400)
            self.assertEqual(e["until"], time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 7, 0, 0, 0, 0, -1)))
            self.assertTrue(baseline_store.night(noon + 60))
            self.assertEqual(baseline_store.night_starts(noon + 60), noon + 60)
            self.assertEqual(self.job(expect=2400).night_hold(noon + 60, []), "")
            self.assertFalse(baseline_store.night(noon - 60))  # (not before it was started)
            self.assertTrue(baseline_store.end_night())
            self.assertFalse(baseline_store.night(noon + 60))
            self.assertFalse(baseline_store.end_night())
        self.assertEqual(baseline_store.morning(self.at(3)), self.at(7))

    def test_versions_that_order_otherwise_wait_for_each_other_only_until_the_queue_stands_still(self):
        """#854, as on 2026-11-25: this version puts a long job that has waited 2 h before a short one; a checkout of an
        older version (a ticket without "held") waits for the short one, queued first. With nothing running, after
        STALL s the short one takes its turn by queue time."""
        now = time.time()
        old = {"what": "#548", "root": "C:/x/transport-game-548", "pid": 2, "t": now - 4 * 3600, "state": "waiting",
               "since": now - 4 * 3600, "share": {"gb": 22.0, "cores": 12}, "expect": 7200, "held": False}
        me, out = self.job(expect=360), io.StringIO()
        me.t, me.out = now - 6 * 3600, out
        old["t"] = now - 3 * 3600  # (queued after me, waited past PASS_MAX: before me by rank)
        with mock.patch.object(baseline_store, "queued_turns", lambda: [old]),                 mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual([j["what"] for j in me.ahead()], ["#548"])  # (the stall starts)
            with mock.patch.object(baseline_store.HeavyJob, "STALL", 0.0):
                self.assertEqual(me.ahead(), [])  # (first come first served: mine is the older ticket)
        self.assertIn("first come first served until one runs (#854)", out.getvalue())
        running = dict(old, state="running", pid=3, t=now - 60)
        with mock.patch.object(baseline_store, "queued_turns", lambda: [running, old]),                 mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual([j["what"] for j in me.ahead()], ["#548", "#548"])  # (something runs: the rule as before)
            self.assertIsNone(me.still)

    def test_the_queue_version_of_a_ticket(self):
        v = baseline_store.queue_version
        self.assertEqual([v({}), v({"held": False}), v({"held": False, "queue": 2}), v({"queue": 7})], [0, 1, 2, 7])
        self.assertEqual(self.ticket("x", 1, 0)["queue"], baseline_store.QUEUE)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d):
            j = self.job(expect=60)
            j.t = time.time()
            j._write("waiting")
            got, = baseline_store.queue()
            os.remove(j.path)
        self.assertEqual(got["queue"], baseline_store.QUEUE)
        self.assertNotIn("merge main", baseline_store.describe(got))
        self.assertTrue(baseline_store.describe({**got, "queue": 1}).endswith(", its queue code is older (merge main)"))

    def test_with_a_first_come_ticket_waiting_first_come_first_served_at_once(self):
        """#856, as on 2026-11-25 06:24: #812's jobs (#851's code) put #250's short job first; #250's checkout (first come
        first served, no "queue" nor "held" on its ticket) waits for #812's, queued before it. Now #812's take their
        turn by queue time too, at once."""
        now = time.time()
        old = {"what": "#250 perf M", "root": "C:/x/transport-game-250-main", "pid": 2, "t": now - 1300,
               "state": "waiting", "since": now - 1300, "share": None, "expect": 360}
        me = self.job(expect=1500, share={"gb": 5, "cores": 4})
        me.t = now - 2600
        with mock.patch.object(baseline_store, "queued_turns", lambda: [old]), \
                mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual(me.ahead(), [])
            later = self.job(expect=60)
            later.t = now
            self.assertEqual([j["what"] for j in later.ahead()], ["#250 perf M"])  # (short, but queued after it)
        new = dict(old, queue=baseline_store.QUEUE)  # (the same ticket of this version: short ones first)
        with mock.patch.object(baseline_store, "queued_turns", lambda: [new]), \
                mock.patch.object(baseline_store, "history", lambda: []):
            self.assertEqual([j["what"] for j in me.ahead()], ["#250 perf M"])
        got = baseline_store.schedule([dict(old, pid=2), {**old, "what": "#812", "pid": 3, "t": now - 2600,
                                                          "since": now - 2600, "expect": 1500, "queue": 2}], now, records=[])
        self.assertLess(next(j["start"] for j in got if j["what"] == "#812"),
                        next(j["start"] for j in got if j["what"] == "#250 perf M"))

    def test_a_held_job_starts_when_the_night_comes(self):
        out, nights = io.StringIO(), iter([False, False, True])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d), \
                mock.patch.object(baseline_store, "night", lambda t=None: next(nights, True)), \
                mock.patch.multiple(baseline_store.HeavyJob, POLL=0.01, WATCH=False), mock.patch.dict(os.environ):
            for k in (baseline_store.DAY, baseline_store.HELD, "TRAM_HEAVY_NOWAIT"):
                os.environ.pop(k, None)
            with baseline_store.HeavyJob("long", out=out, expect=2400) as j:
                self.assertEqual((j.parked, j.state), ("", "running"))
        self.assertIn("long waits for the night (23:00): expected 40 min", out.getvalue())


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
        # (the order of the turns, not the hour: a job of unknown time is not held for the night here, #851)
        self.env[baseline_store.DAY] = "1"
        day = mock.patch.dict(os.environ, {baseline_store.DAY: "1"})
        day.start()
        self.addCleanup(day.stop)
        self.kids = []

    def job(self, name, setup=""):
        release = os.path.join(self.tmp.name, f"release-{name}")
        p = subprocess.Popen([sys.executable, "-I", "-c", JOB, TOOLS, name, release, setup], env=self.env,
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

    def shared(self, name, gb=4, cores=2):
        """A count run or a build on the test's machine (MACHINE), with its peak memory and its cores."""
        return self.job(name, MACHINE + f"share = {{'gb': {gb}, 'cores': {cores}}}")

    def test_shared_jobs_run_side_by_side_while_memory_and_cores_fit(self):
        a, release_a = self.shared("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, release_b = self.shared("b")
        self.assertEqual(b.stdout.readline().strip(), "in")  # (beside a: 8 of 38 GB, 4 of 8 cores)
        self.assertEqual(sorted(self.states()), [("a", "running"), ("b", "running")])
        for r in (release_a, release_b):
            open(r, "w").close()
        self.assertEqual((a.wait(10), b.wait(10)), (0, 0))

    def test_a_shared_job_waits_for_the_memory_another_declared(self):
        a, release_a = self.shared("a", gb=30)  # (it holds a few MB yet: its 30 GB are kept for it)
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, release_b = self.shared("b", gb=10)  # (40 free - 2 kept - 30 declared: 8)
        self.wait_for(lambda: self.states() == [("a", "running"), ("b", "waiting")])
        c, release_c = self.shared("c", gb=4)  # (it would fit, but b came first: a big job is not passed for good)
        self.wait_for(lambda: self.states() == [("a", "running"), ("b", "waiting"), ("c", "waiting")])
        open(release_a, "w").close()
        self.assertEqual(b.stdout.readline().strip(), "in")
        self.assertEqual(c.stdout.readline().strip(), "in")  # (beside b: 14 of 38 GB)
        for r in (release_b, release_c):
            open(r, "w").close()
        self.assertEqual((b.wait(10), c.wait(10)), (0, 0))
        self.assertRegex(b.stderr.read(), r"b waits for memory \(8 GB free to share, 10 needed\) beside a in ")

    def test_a_shared_job_waits_for_cores(self):
        a, release_a = self.shared("a", cores=6)
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, release_b = self.shared("b", cores=4)
        self.wait_for(lambda: self.states() == [("a", "running"), ("b", "waiting")])
        open(release_a, "w").close()
        self.assertEqual(b.stdout.readline().strip(), "in")
        open(release_b, "w").close()
        self.assertEqual(b.wait(10), 0)
        self.assertIn("b waits for cores (2 of 8 free, 4 needed) beside a in ", b.stderr.read())

    def test_a_timing_waits_for_the_shared_jobs_and_holds_those_after_it(self):
        a, release_a = self.shared("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        x, release_x = self.job("timing")
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting")])
        c, release_c = self.shared("c")  # (it would fit beside a: the timing queued before it goes first)
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting"), ("c", "waiting")])
        open(release_a, "w").close()
        self.assertEqual(x.stdout.readline().strip(), "in")
        self.assertEqual(a.wait(10), 0)
        time.sleep(0.5)
        self.assertEqual(self.states(), [("timing", "running"), ("c", "waiting")])  # (alone)
        open(release_x, "w").close()
        self.assertEqual(c.stdout.readline().strip(), "in")
        open(release_c, "w").close()
        self.assertEqual((x.wait(10), c.wait(10)), (0, 0))

    def test_a_short_shared_job_goes_before_a_timing_that_waits_for_a_long_one(self):
        """Backfilling (#829): the timing cannot start before a's expected end, so c, ending sooner, runs beside a;
        d, whose 1.5× its time would end after a's, keeps its turn behind the timing."""
        a, release_a = self.job("a", MACHINE + "share = {'gb': 4, 'cores': 2}; expect = 3600")
        self.assertEqual(a.stdout.readline().strip(), "in")
        x, release_x = self.job("timing")
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting")])
        c, release_c = self.job("c", MACHINE + "share = {'gb': 4, 'cores': 2}; expect = 600")
        self.assertEqual(c.stdout.readline().strip(), "in")  # (now + 900 s before a's end at 3600)
        d, release_d = self.job("d", MACHINE + "share = {'gb': 4, 'cores': 2}; expect = 3000")
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting"), ("c", "running"),
                                                ("d", "waiting")])
        time.sleep(0.5)
        self.assertEqual(self.states()[-1], ("d", "waiting"))
        e, release_e = self.job("e", MACHINE + "share = {'gb': 4, 'cores': 2}; expect = 300")
        self.assertEqual(e.stdout.readline().strip(), "in")  # (past d too: d waits behind the timing all the same)
        for r in (release_c, release_e, release_a):
            open(r, "w").close()
        self.assertEqual(x.stdout.readline().strip(), "in")  # (alone, once a, c and e ended)
        open(release_x, "w").close()
        self.assertEqual(d.stdout.readline().strip(), "in")
        open(release_d, "w").close()
        self.assertEqual([k.wait(10) for k in (a, x, c, d, e)], [0, 0, 0, 0, 0])

    def test_no_backfill_without_known_times(self):
        """A running job with no expected time: the timing's start is not known, so no shared job goes before it."""
        a, release_a = self.shared("a")
        self.assertEqual(a.stdout.readline().strip(), "in")
        x, release_x = self.job("timing")
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting")])
        # (900 s: longer than SHORT, which would go before the timing as the short ones do, #851)
        c, release_c = self.job("c", MACHINE + "share = {'gb': 4, 'cores': 2}; expect = 900")
        self.wait_for(lambda: self.states() == [("a", "running"), ("timing", "waiting"), ("c", "waiting")])
        time.sleep(0.5)
        self.assertEqual(self.states()[-1], ("c", "waiting"))
        for r in (release_a, release_x, release_c):
            open(r, "w").close()
        self.assertEqual([k.wait(10) for k in (a, x, c)], [0, 0, 0])

    def test_backfills(self):
        run = [{"since": 1000.0, "expect": 3600.0, "kind": "a.py"}]
        self.assertTrue(baseline_store.backfills(600, run, 1.5, now=2000.0, records=[]))  # (2900 <= 4600)
        self.assertFalse(baseline_store.backfills(1800, run, 1.5, now=2000.0, records=[]))  # (4700 > 4600)
        self.assertFalse(baseline_store.backfills(None, run, 1.5, now=2000.0, records=[]))
        self.assertFalse(baseline_store.backfills(60, [], 1.5, now=2000.0, records=[]))
        self.assertFalse(baseline_store.backfills(60, run + [{"since": 1500.0, "kind": "new.py"}], 1.5, now=2000.0,
                                                  records=[]))
        self.assertFalse(baseline_store.backfills(60, run, 1.5, now=4600.0, records=[]))  # (a past its time)
        self.assertTrue(baseline_store.backfills(60, [{"since": 1000.0, "kind": "b.py"}], 1.5, now=1100.0,
                                                 records=[{"kind": "b.py", "wall": 900.0, "rc": 0}]))

    def test_a_shared_job_waits_for_an_older_tools_job(self):
        # (a ticket with no share, as a checkout from before #728 writes it: a job alone)
        # (its process: not this one, which starts b: a job never waits for a process that started it)
        other = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (other.kill(), other.wait()))
        os.makedirs(baseline_store.LOCKS)
        old = os.path.join(baseline_store.LOCKS, f"{other.pid}.lock")
        with open(old, "w", encoding="utf-8") as f:
            json.dump({"what": "old", "root": "C:/x/transport-game-1", "pid": other.pid, "t": time.time(),
                       "state": "running", "since": time.time()}, f)
        b, release_b = self.shared("b")
        self.wait_for(lambda: self.states() == [("old", "running"), ("b", "waiting")])
        time.sleep(0.5)
        self.assertEqual(self.states(), [("old", "running"), ("b", "waiting")])
        os.remove(old)
        self.assertEqual(b.stdout.readline().strip(), "in")
        open(release_b, "w").close()
        self.assertEqual(b.wait(10), 0)

    def chain(self, name, step_setup=""):
        """A shared chain (4 GB, 2 cores) that starts a step once its turn comes: a job of its own tool, run in the
        chain's turn (HELD), released by `<its release>-step`."""
        setup = (MACHINE + "share = {'gb': 4, 'cores': 2}\nimport subprocess\nkid = []\n"
                 "def spin():\n"
                 f"    if not kid: kid.append(subprocess.Popen([sys.executable, '-I', '-c', {JOB!r}, sys.argv[1], "
                 f"'step', sys.argv[3] + '-step', {MACHINE + step_setup!r}]))\n"
                 "    time.sleep(0.05)\n")
        p, release = self.job(name, setup)
        self.addCleanup(lambda: open(release + "-step", "w").close())  # (the step is the chain's child, not the test's)
        return p, release, release + "-step"

    def test_a_shared_job_runs_beside_a_shared_chain_whose_step_declares_no_share(self):
        """#844: the step's ticket names the chain ("in"), and the queue counts it as the chain's. Before, it was a job
        alone running, and b waited for it (2026-11-24: 22 min beside #800's chain)."""
        a, release_a, release_step = self.chain("chain")
        self.assertEqual(a.stdout.readline().strip(), "in")
        self.assertEqual(a.stdout.readline().strip(), "in")  # (the step, in the chain's turn: its output is the chain's)
        step = next(j for j in baseline_store.queue() if j["what"] == "step")
        self.assertEqual((step["in"], step["share"], step["state"]), (a.pid, None, "running"))
        b, release_b = self.shared("b")
        self.assertEqual(b.stdout.readline().strip(), "in")  # (beside the chain: 8 of 38 GB, 4 of 8 cores)
        x, release_x = self.job("timing")
        self.wait_for(lambda: ("timing", "waiting") in self.states())
        open(release_step, "w").close()
        time.sleep(0.5)
        self.assertEqual(self.states()[-1], ("timing", "waiting"))  # (alone: it waits for the chain and b)
        for r in (release_a, release_b):
            open(r, "w").close()
        self.assertEqual(x.stdout.readline().strip(), "in")
        open(release_x, "w").close()
        self.assertEqual([k.wait(10) for k in (a, b, x)], [0, 0, 0])

    def test_an_older_checkouts_step_is_found_in_the_process_table(self):
        """A step whose ticket names no job (a checkout from before #844) is its chain's all the same: the chain's
        process started it."""
        old = ("_d = b.json.dump\n"  # (its tickets as an older checkout writes them: no "in")
               "def _dump(o, f, *a, **k):\n"
               "    return _d({x: y for x, y in o.items() if x != 'in'} if isinstance(o, dict) else o, f, *a, **k)\n"
               "b.json.dump = _dump\n")
        a, release_a, release_step = self.chain("chain", old)
        self.assertEqual(a.stdout.readline().strip(), "in")
        self.assertEqual(a.stdout.readline().strip(), "in")
        jobs = baseline_store.queue()
        step = next(j for j in jobs if j["what"] == "step")
        self.assertNotIn("in", step)
        self.assertEqual(baseline_store.ticket_parents(jobs), {step["pid"]: a.pid})
        b, release_b = self.shared("b")
        self.assertEqual(b.stdout.readline().strip(), "in")
        for r in (release_step, release_a, release_b):
            open(r, "w").close()
        self.assertEqual([k.wait(10) for k in (a, b)], [0, 0])

    def test_ticket_parents_take_an_ancestor_that_started_first(self):
        t = time.time()
        jobs = [{"pid": p, "state": s} for p, s in [(10, "running"), (13, "running"), (20, "running"), (30, "running"),
                                                     (40, "waiting")]]  # (an older checkout's tickets: no "in")
        jobs += [{"pid": 50, "state": "running", "in": None}, {"pid": 60, "state": "running", "in": 10}]
        table = {13: 12, 12: 10, 10: 1, 20: 99, 99: 1, 30: 40, 40: 1, 50: 10, 60: 10}  # (13 under a shell under 10)
        made = {10: t, 12: t + 1, 13: t + 2, 20: t, 30: t, 40: t + 5, 50: t + 1, 60: t + 1}.get
        # (30's parent pid 40 holds a ticket but started after 30: a pid Windows reused, not 30's parent; 50 and 60 say
        # themselves, 50 that it holds a turn of its own though 10 started it; 20's ancestors hold none)
        self.assertEqual(baseline_store.ticket_parents(jobs, table, made), {13: 10})

    def test_turns_fold_a_jobs_steps_into_it(self):
        t = time.time()

        def tk(pid, what, share=None, inside=None, state="running"):
            return {"what": what, "root": "C:/x/transport-game-800", "pid": pid, "t": t + pid / 1000, "state": state,
                    "since": t, "share": share, "in": inside}
        jobs = [tk(1, "chain", {"gb": 6.0, "cores": 12}), tk(2, "street_profile", None, 1),
                tk(3, "ground_mesh", {"gb": 21.0, "cores": 8}, 2),  # (a step of a step: the chain's)
                tk(4, "alone chain"), tk(5, "places", {"gb": 3.5, "cores": 1}, 4),
                tk(6, "orphan step", None, 99),  # (its parent's ticket is gone: a job of its own)
                tk(7, "b", {"gb": 3.5, "cores": 1}, state="waiting")]
        got = baseline_store.turns(jobs)
        self.assertEqual([j["what"] for j in got], ["chain", "alone chain", "orphan step", "b"])
        self.assertEqual(got[0]["share"], {"gb": 21.0, "cores": 12})  # (the larger of its own and its steps')
        self.assertEqual([s["what"] for s in got[0]["steps"]], ["street_profile", "ground_mesh"])
        self.assertIsNone(got[1]["share"])  # (a shared step in a job alone: still alone)
        self.assertEqual(got[2]["steps"], [])
        self.assertEqual(jobs[0]["share"], {"gb": 6.0, "cores": 12})  # (the tickets themselves are kept)
        self.assertIn(", its steps street_profile, ground_mesh running", baseline_store.describe(got[0], t))
        self.assertEqual([j["what"] for j in baseline_store.schedule(jobs, t, records=[], free=40.0)],
                         ["chain", "alone chain", "orphan step", "b"])
        with mock.patch.object(baseline_store.os, "getpid", lambda: 3):  # (a step's own turn is its chain's)
            self.assertTrue(baseline_store.own_turn(got[0]))
            self.assertFalse(baseline_store.own_turn(got[1]))

    def test_room_is_what_the_running_shared_jobs_leave_and_a_claim_is_kept(self):
        a, release_a = self.shared("a", gb=30, cores=3)
        self.assertEqual(a.stdout.readline().strip(), "in")
        with mock.patch.multiple(baseline_store.HeavyJob, FREE=staticmethod(lambda: 40.0), CORES=8, KEEP=2.0):
            with baseline_store.HeavyJob("me", wait=False, share={"gb": 4, "cores": 2}) as me:
                room = me.room()
                self.assertEqual(room["cores"], 5)
                self.assertTrue(8.0 <= room["gb"] < 8.5, room)  # (40 - 2 - 30, and the few MB a holds already)
                mine = next(j for j in baseline_store.queue() if j["what"] == "me")
                me.claim(gb=16, cores=5)
                now = next(j for j in baseline_store.queue() if j["what"] == "me")
                self.assertEqual((now["share"], now["since"], now["state"]), ({"gb": 16.0, "cores": 5}, mine["since"], "running"))
                self.assertTrue(baseline_store.describe(now).endswith(" (shared: 16 GB, 5 cores)"))
        open(release_a, "w").close()
        self.assertEqual(a.wait(10), 0)

    def test_a_wait_behind_a_job_doing_nothing_ends_with_an_error(self):
        a, release_a = self.job("a")  # (it sleeps until released)
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, _ = self.job("b", "b.HeavyJob.IDLE, b.HeavyJob.IDLE_CPU, b.HeavyJob.LOOK = 1.0, 2.0, 0.2")
        self.assertEqual(b.wait(30), 1)
        err = b.stderr.read()
        self.assertRegex(err, r"b ends its wait after \d+ min: a in .*running \d+ min \(pid %d\)" % a.pid)
        self.assertIn("It does nothing", err)
        self.assertEqual(self.states(), [("a", "running")])  # (b's ticket went with it)
        open(release_a, "w").close()
        self.assertEqual(a.wait(10), 0)

    def test_a_job_at_work_is_waited_for(self):
        a, release_a = self.job("a", "spin = lambda: sum(range(200000))")  # (a core kept busy)
        self.assertEqual(a.stdout.readline().strip(), "in")
        b, release_b = self.job("b", "b.HeavyJob.IDLE, b.HeavyJob.IDLE_CPU, b.HeavyJob.LOOK = 1.0, 0.3, 0.2")
        self.wait_for(lambda: self.states() == [("a", "running"), ("b", "waiting")])
        time.sleep(4)
        self.assertIsNone(b.poll())
        open(release_a, "w").close()
        self.assertEqual(b.stdout.readline().strip(), "in")
        open(release_b, "w").close()
        self.assertEqual(b.wait(10), 0)

    def test_usage_is_a_process_with_what_it_started(self):
        own = baseline_store.usage(os.getpid())
        self.assertGreater(own[0], 0)
        self.assertGreater(own[1], 0.005)
        kid = subprocess.Popen([sys.executable, "-I", "-c", "import time; x = b'x' * 200_000_000; print('held', flush=True); time.sleep(60)"],
                               stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (kid.kill(), kid.wait(), kid.stdout.close()))
        self.assertEqual(kid.stdout.readline().strip(), "held")
        with_kid = baseline_store.usage(os.getpid())
        self.assertGreater(with_kid[1], own[1] + 0.15)
        self.assertLess(baseline_store.usage(os.getpid(), skip=(kid.pid,))[1], with_kid[1] - 0.15)

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
        old = ", its queue code is older (merge main)"  # (#856)
        self.assertEqual(baseline_store.describe(j, j["since"] + 600), "headless in transport-game-268, running 10 min" + old)
        # (a ticket written just after the board read the clock)
        self.assertEqual(baseline_store.describe(j, j["since"] - 1), "headless in transport-game-268, running 0 min" + old)

    def test_a_job_that_watches_itself_is_given_twice_the_idle_time(self):
        other = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (other.kill(), other.wait()))
        time.sleep(0.5)  # (its start's CPU spent)
        me = baseline_store.HeavyJob("me", wait=False)
        for watch, ends in ((False, 600.0), (True, 1200.0)):
            ahead, marks = [{"pid": other.pid, "state": "running", "watch": watch, "what": "x", "root": "r", "since": 0}], {}
            self.assertIsNone(me._idle(ahead, marks, 0.0))
            self.assertIsNone(me._idle(ahead, marks, ends - 1))
            self.assertEqual(me._idle(ahead, marks, ends)[0]["pid"], other.pid)


class Rules(unittest.TestCase):
    """What a running job's watch warns of and when it ends the job (#815), on fake clocks and usage."""
    def job(self, share=None, expect=None, limits=True):
        j = baseline_store.HeavyJob("v", wait=False, share=share, expect=expect, limits=limits)
        j.since, j.parent = 0.0, 4242
        return j

    def test_time_warns_past_twice_and_ends_only_once_calibrated(self):
        j = self.job(expect=300.0)
        self.assertEqual(j.verdict(500, 500, 1, 40, False), ([], None))  # (1.7×)
        self.assertEqual(j.verdict(700, 700, 1, 40, False), (["LATE ×2.3"], None))
        self.assertEqual(j.verdict(6000, 6000, 1, 40, False), (["LATE ×20"], None))  # (TIME_ENDS: not yet)
        with mock.patch.object(baseline_store.HeavyJob, "TIME_ENDS", True):
            self.assertIsNone(j.verdict(1300, 1300, 1, 40, False)[1])  # (×4.3 but 17 min over: not 30)
            self.assertEqual(j.verdict(2400, 2400, 1, 40, False)[1], "time: running 40 min, expected 5")
        self.assertEqual(self.job().verdict(1e6, 1e6, 1, 40, False), ([], None))  # (no expected time: no rule)

    def test_memory_against_the_share(self):
        j = self.job(share={"gb": 6, "cores": 4})
        self.assertEqual(j.verdict(60, 60, 7, 40, False), ([], None))  # (1.17×)
        self.assertEqual(j.verdict(120, 120, 8, 40, False), (["8 of 6 GB"], None))
        self.assertEqual(j.verdict(180, 180, 13, 40, False), (["13 of 6 GB"], None))  # (over 2×: once)
        self.assertEqual(j.verdict(240, 240, 13, 40, False)[1], "memory: 13.0 GB held, 6 declared")  # (twice)
        j = self.job(share={"gb": 6, "cores": 4})
        self.assertIsNone(j.verdict(60, 60, 7, 3, False)[1])  # (over 1× with 3 GB free, KEEP 8: once)
        self.assertEqual(j.verdict(120, 120, 7, 3, False)[1], "memory: 7.0 GB held, 6 declared, 3.0 GB left free on the machine")
        j = self.job(share={"gb": 6, "cores": 4})
        for t in (60, 120, 180):
            self.assertIsNone(j.verdict(t, t, 5, 3, False)[1])  # (within its share: the shortage is another's)

    def test_memory_of_a_job_alone_against_the_machine(self):
        j = self.job()
        self.assertEqual(j.verdict(60, 60, 30, 7, False), (["7 GB free"], None))
        self.assertIsNone(j.verdict(120, 120, 30, 3, False)[1])
        self.assertEqual(j.verdict(180, 180, 30, 3, False)[1],
                         "memory: 3.0 GB left free on the machine, 30.0 GB held by this job, which runs alone")
        self.assertEqual(j.verdict(240, 240, 30, None, False), ([], None))  # (free memory unknown)

    def test_idle_ends_after_its_time_and_work_moves_the_mark(self):
        j = self.job()
        self.assertIsNone(j.verdict(0, 10.0, 1, 40, False)[1])
        self.assertIsNone(j.verdict(590, 11.5, 1, 40, False)[1])
        self.assertIsNone(j.verdict(599, 13.0, 1, 40, False)[1])  # (3 s of CPU: the mark moves)
        self.assertIsNone(j.verdict(1100, 14.0, 1, 40, False)[1])
        self.assertEqual(j.verdict(1199, 14.9, 1, 40, False)[1], "idle: 1.9 s of CPU in 10 min")
        j = self.job()
        j.verdict(0, 50.0, 1, 40, False)
        self.assertIsNone(j.verdict(700, 20.0, 1, 40, False)[1])  # (the sum fell: a child ended; a new mark)

    def test_an_orphan_ends_and_without_limits_nothing_ends(self):
        self.assertEqual(self.job().verdict(60, 60, 1, 40, True)[1], "orphan: the process that started it (pid 4242) is gone")
        j = self.job(share={"gb": 1, "cores": 1}, limits=False)
        self.assertEqual(j.verdict(60, 60, 9, 40, True), (["9 of 1 GB"], None))
        self.assertEqual(j.verdict(120, 60, 9, 40, True), (["9 of 1 GB"], None))

    def test_the_expected_time_is_the_median_of_the_kinds_full_runs(self):
        rs = [{"kind": "k", "wall": w, "rc": rc, "ended": e} for w, rc, e in
              ((100, 0, None), (300, None, None), (200, 0, None), (5000, 0, "memory: …"), (900, 1, None), (30, 0, None))]
        self.assertEqual(baseline_store.expected("k", rs), 200)  # (not the ended, failed or short runs)
        self.assertIsNone(baseline_store.expected("k", rs[:2]))  # (two runs: too few)
        self.assertIsNone(baseline_store.expected("other", rs))
        more = rs + [{"kind": "k", "wall": w, "rc": 0, "ended": None} for w in (400, 500, 600)]
        self.assertEqual(baseline_store.expected("k", more, last=3), 500)  # (the last three)

    def test_kind_and_duration(self):
        self.assertEqual(baseline_store.kind_of(["python", "-P", "-E", "tools/ground_place.py", "--rings", "Karlovo",
                                                 "--all", "--threads=4"]), "ground_place.py --all --rings --threads")
        self.assertEqual(baseline_store.kind_of(["C:/Git/bin/bash.exe", "job.sh", "9"]), "job.sh")
        self.assertEqual(baseline_store.kind_of(["C:/x/node.exe", "--max-old-space-size", "8"]), "node --max-old-space-size")
        self.assertEqual([baseline_store.seconds(t) for t in ("90s", "20m", "1.5h", "20", "", "x", "0")],
                         [90, 1200, 5400, 1200, None, None, None])

    def test_the_board_sees_the_expected_time_the_warning_and_the_ends(self):
        j = {"what": "trace heights", "root": "C:/x/transport-game-812", "state": "running", "since": 0, "expect": 300,
             "share": {"gb": 6, "cores": 4}, "warn": "LATE ×20; 17 of 6 GB", "queue": baseline_store.QUEUE}
        self.assertEqual(baseline_store.describe(j, 6000), "trace heights in transport-game-812, running 100 min, "
                                                          "expected 5 (shared: 6 GB, 4 cores): LATE ×20; 17 of 6 GB")
        rs = [{"t": 0, "wall": 100, "ended": "idle: …"}, {"t": 0, "wall": 5000, "ended": None},
              {"t": 1000, "wall": 600, "ended": "orphan: …"}]
        self.assertEqual(baseline_store.recent_ends(1600 + 3600, records=rs), [rs[2]])


# (a job that watches itself on the test's quick clock: argv[3] runs first and may set `share` and `body`, what it does
# in its turn)
WATCHED = ("import os, subprocess, sys, time; sys.path.insert(0, sys.argv[1]); import baseline_store as b\n"
           "H = b.HeavyJob; H.POLL, H.EVERY, H.TICK = 0.1, 0.2, 0.1\n"
           "H.FREE = staticmethod(lambda: 40.0); H.KEEP = 2.0\n"
           "share, body = None, lambda: time.sleep(30)\n"
           "exec(sys.argv[3])\n"
           "with b.HeavyJob(sys.argv[2], share=share):\n"
           "    print('in', flush=True)\n"
           "    body()\n")
KID = ("def body():\n"
       "    kid = subprocess.Popen([sys.executable, '-I', '-c', 'import time; time.sleep(60)'])\n"
       "    print(kid.pid, flush=True)\n"
       "    time.sleep(30)\n")
# (a process that starts a job and leaves it once it runs)
MIDDLE = ("import subprocess, sys\n"
          "p = subprocess.Popen(sys.argv[1:], stdout=subprocess.PIPE, text=True)\n"
          "assert p.stdout.readline().strip() == 'in'\n"
          "print(p.pid, flush=True)\n")


class Watch(unittest.TestCase):
    """A real job's watch ends it, and what it started, with the reason (#815); in a lock folder of the test's own."""
    setUp, wait_for, states = Queue.setUp, Queue.wait_for, Queue.states

    def watched(self, name, setup=""):
        p = subprocess.Popen([sys.executable, "-I", "-c", WATCHED, TOOLS, name, setup], env=self.env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close(), p.stderr.close()))
        self.assertEqual(p.stdout.readline().strip(), "in")
        return p

    def ended(self, p, why):
        self.assertEqual(p.wait(20), baseline_store.ENDED)
        err = p.stderr.read()
        self.assertRegex(err, rf"heavy jobs: \w+ ended by its watch after 0 min: {why}")
        self.assertEqual(self.states(), [])
        rec, = baseline_store.history()
        self.assertRegex(rec["ended"], f"^{why}")
        return err

    def test_an_idle_job_ends_with_what_it_started(self):
        p = self.watched("idle", "H.IDLE, H.IDLE_CPU = 1.5, 0.5\n" + KID)
        kid = int(p.stdout.readline())
        self.assertTrue(baseline_store.alive(kid))
        self.ended(p, "idle: ")
        self.wait_for(lambda: not baseline_store.alive(kid), 5)

    def test_a_job_over_twice_its_memory_ends(self):
        p = self.watched("big", "share = {'gb': 0.05, 'cores': 1}\n"
                                "def body():\n    x = b'x' * 300_000_000\n    time.sleep(30)\n")
        self.assertIn("warns: ", self.ended(p, "memory: 0.3 GB held, 0 declared"))

    def test_a_job_whose_starter_is_gone_ends(self):
        err = os.path.join(self.tmp.name, "orphan.err")
        with open(err, "w", encoding="utf-8") as f:
            mid = subprocess.Popen([sys.executable, "-I", "-c", MIDDLE, sys.executable, "-I", "-c", WATCHED, TOOLS,
                                    "orphan", ""], env=self.env, stdout=subprocess.PIPE, stderr=f, text=True)
            pid = int(mid.stdout.readline())
            self.assertEqual(mid.wait(10), 0)
            mid.stdout.close()
        self.wait_for(lambda: not baseline_store.alive(pid), 20)
        with open(err, encoding="utf-8") as f:
            self.assertRegex(f.read(), r"orphan ended by its watch after 0 min: orphan: the process that started it "
                                       rf"\(pid {mid.pid}\) is gone")

    def test_a_stop_request_ends_it(self):
        p = self.watched("asked", KID)
        kid = int(p.stdout.readline())
        r = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "heavy.py"), "--stop", str(p.pid)], env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("asked in ", r.stderr)
        self.assertIn("ended on request", r.stderr)
        self.ended(p, r"stopped on request \(heavy.py --stop\)")
        self.wait_for(lambda: not baseline_store.alive(kid), 5)

    def test_a_job_at_work_within_its_limits_runs_to_its_end_and_is_recorded(self):
        # (the work in a child, which the watch counts as the job's, and the main thread waiting: the watch's looks
        # never wait for the GIL. The idle limit at 5 % of a core, the real one 0.3 %: the job ended as idle at 10 %
        # with its work and pauses in one thread on a busy machine, 0 of 5 pass on two cores beside 4 busy, #829)
        p = self.watched("fine", "H.RECORD, H.IDLE, H.IDLE_CPU = 0.0, 2.0, 0.1\nshare = {'gb': 1, 'cores': 1}\n"
                                 "def body():\n    subprocess.run([sys.executable, '-I', '-c', "
                                 "'import time\\nt = time.time()\\nwhile time.time() - t < 3: pass'], check=True)\n")
        rc = p.wait(30)
        self.assertEqual(rc, 0, p.stderr.read())  # (the watch's reason when it ended the job)
        rec, = baseline_store.history()
        self.assertEqual((rec["what"], rec["kind"], rec["rc"], rec["ended"]), ("fine", "-c", 0, None))
        self.assertGreater(rec["wall"], 2.9)
        self.assertGreater(rec["gb"], 0)

    @unittest.skipUnless(os.name == "nt", "a Job Object: Windows")
    def test_a_stopped_wrapper_stops_its_command(self):
        w = subprocess.Popen([sys.executable, "-I", os.path.join(TOOLS, "heavy.py"), "wrapped", "--", sys.executable,
                              "-I", "-c", "import os, time; print(os.getpid(), flush=True); time.sleep(60)"],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: (w.kill(), w.wait(), w.stdout.close()))
        kid = int(w.stdout.readline())
        w.kill()  # (as a stopped task's shell would be: the wrapper alone)
        w.wait(10)
        self.wait_for(lambda: not baseline_store.alive(kid), 5)


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
