# SPDX-License-Identifier: AGPL-3.0-or-later
"""The project's overview (#826): the heavy queue's estimated times (baseline_store.schedule) worked out by hand for
alone, shared and mixed queues; the snapshot from a temp LOCKS with tickets and history and fake session logs of both
agents, with no text of a log in it; the upload only on change against a fake FTP; a deploy keeps overview.json.
python -P -E tools/test_overview.py"""
import ftplib
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import baseline_store  # noqa: E402
import board  # noqa: E402
import deploy  # noqa: E402
import overview  # noqa: E402
from test_deploy import FakeFtp  # noqa: E402

NOW = 1_800_000_000.0
MARKER = "SECRET-PROMPT-TEXT-8c1f"


def job(pid, state, since=None, share=None, expect=None, kind="x.py", gb=None, t=None):
    return {"what": f"job{pid}", "root": f"/w/transport-game-{pid}", "pid": pid, "t": NOW - 1000 + pid if t is None else t,
            "state": state, "since": since if since is not None else NOW - 1000 + pid, "share": share, "kind": kind,
            "expect": expect, "gb": gb, "queue": baseline_store.QUEUE}


def times(jobs, **kw):
    out = baseline_store.schedule(jobs, NOW, kw.pop("records", []), **{"free": None, "cores": 8, "keep": 8.0, **kw})
    return {j["pid"]: (j["start"] and j["start"] - NOW, j["finish"] and j["finish"] - NOW, j["late"]) for j in out}


class Schedule(unittest.TestCase):
    def test_alone_one_after_another(self):
        got = times([job(1, "running", since=NOW - 600, expect=1200), job(2, "waiting", expect=300),
                     job(3, "waiting", kind="y.py --all")],
                    records=[{"kind": "y.py --all", "wall": 400.0, "rc": 0}, {"kind": "y.py --all", "wall": 500.0, "rc": 0},
                             {"kind": "y.py --all", "wall": 9000.0, "rc": 1}, {"kind": "y.py --all", "wall": 50.0, "rc": 0}])
        # (3's time: the median of its two full runs, 450 s; the failed run and the 50 s one left out)
        self.assertEqual(got, {1: (-600, 600, False), 2: (600, 900, False), 3: (900, 1350, False)})

    def test_shared_beside_each_other_while_cores_and_memory_fit(self):
        s = lambda gb, c: {"gb": gb, "cores": c}  # noqa: E731
        jobs = [job(1, "running", since=NOW - 60, share=s(6, 4), expect=660, gb=5.0),  # (ends +600)
                job(2, "waiting", share=s(6, 4), expect=300),  # (8 cores: fits now beside 1)
                job(3, "waiting", share=s(4, 2), expect=100),  # (cores full until 2 ends at +300)
                job(4, "waiting", share=s(10, 2), expect=100)]  # (memory: 20 free + 5 held - 8 kept = 17 GB)
        got = times(jobs, free=20.0)
        # 4 starts after 3 (queue order) at +300; beside 1 (6 GB) and 3 (4 GB) 10 more is 20 > 17: it waits for 3's end
        # at +400 (1 and 4: 16 GB, 6 cores)
        self.assertEqual(got, {1: (-60, 600, False), 2: (0, 300, False), 3: (300, 400, False), 4: (400, 500, False)})

    def test_mixed_alone_waits_for_all_and_shared_wait_for_it(self):
        s = {"gb": 2, "cores": 2}
        got = times([job(1, "running", since=NOW, share=s, expect=600), job(2, "waiting", expect=300),
                     job(3, "waiting", share=s, expect=500)])  # (1.5 × 500 ends after 1: in its turn)
        self.assertEqual(got, {1: (0, 600, False), 2: (600, 900, False), 3: (900, 1400, False)})

    def test_a_short_shared_job_goes_before_the_alone_ones(self):
        """Backfilling (#829), as on 2026-11-23: two alone jobs wait for a long shared one; the short shared jobs
        behind them run beside it, and the one too long for that keeps its turn."""
        s = {"gb": 4, "cores": 2}
        got = times([job(1, "running", since=NOW - 600, share=s, expect=4200), job(2, "waiting", expect=1380),
                     job(3, "waiting", expect=360), job(4, "waiting", share=s, expect=180),
                     job(5, "waiting", share=s, expect=360), job(6, "waiting", share=s, expect=3000)])
        # (3, alone and short, goes before 2, alone and longer: the short ones first, #851)
        self.assertEqual(got, {1: (-600, 3600, False), 2: (3960, 5340, False), 3: (3600, 3960, False),
                               4: (0, 180, False), 5: (0, 360, False), 6: (5340, 8340, False)})

    def test_a_short_shared_job_passes_one_of_no_known_time_behind_an_alone_one(self):
        """2 waits for 1 (alone); 3 (no known time) waits behind 2, so 4 passing it delays neither (#829)."""
        s = {"gb": 4, "cores": 2}
        got = times([job(1, "running", since=NOW, share=s, expect=3600), job(2, "waiting", expect=600),
                     job(3, "waiting", share=s, kind="new.py"), job(4, "waiting", share=s, expect=360)])
        self.assertEqual(got, {1: (0, 3600, False), 2: (3600, 4200, False), 3: (4200, None, False), 4: (0, 360, False)})

    def test_shared_with_nothing_running_starts_whatever_its_memory(self):
        got = times([job(1, "waiting", share={"gb": 64, "cores": 32}, expect=60)], free=4.0)
        self.assertEqual(got, {1: (0, 60, False)})

    def test_late_ends_now_and_unknown_leaves_the_rest_unknown(self):
        got = times([job(1, "running", since=NOW - 600, expect=60), job(2, "waiting", kind="new.py"),
                     job(3, "waiting", expect=60)])
        # (3, short, goes before 2, whose time is not known: #851; after 2 nothing would be known)
        self.assertEqual(got, {1: (-600, 0, True), 2: (60, None, False), 3: (0, 60, False)})

    def test_board_says_the_finish(self):
        j = baseline_store.schedule([job(1, "running", since=NOW - 60, expect=600), job(2, "waiting", expect=300)], NOW, [])
        self.assertEqual(board.eta(j[0], NOW), f", ends ~{board.clock(NOW + 540)}")
        self.assertEqual(board.eta(j[1], NOW), f", starts ~{board.clock(NOW + 540)}, ends ~{board.clock(NOW + 840)} (expected 5 min)")


def write_log(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for d in lines:
            f.write(json.dumps(d) + "\n")
    os.utime(path, (NOW - 120, NOW - 120))


class Fixture(unittest.TestCase):
    """A temp LOCKS with two tickets (this process and its parent: alive) and a history, a temp home with the logs
    of both agents, a worktree folder, and the board's rows and GitHub's answers made up."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        locks = os.path.join(self.tmp, "locks")
        os.makedirs(locks)
        me, parent = os.getpid(), os.getppid()
        for pid, d in ((parent, {"state": "running", "since": NOW - 300, "share": None, "kind": "rebuild.py --parallel",
                                 "expect": None, "gb": 3.0}),
                       (me, {"state": "waiting", "since": NOW - 100, "share": {"gb": 4, "cores": 2},
                             "kind": "headless.py --checks", "expect": 180.0})):
            with open(os.path.join(locks, f"{pid}.lock"), "w", encoding="utf-8") as f:
                json.dump({"what": f"w{pid}", "root": os.path.join(self.tmp, "transport-game-9"), "pid": pid,
                           "t": NOW - 400 + (pid == me), "warn": "", **d}, f)
        with open(os.path.join(locks, "history.jsonl"), "w", encoding="utf-8") as f:
            for w in (3000, 3600, 4200):
                f.write(json.dumps({"kind": "rebuild.py --parallel", "what": "rebuild", "root": "x", "t": NOW - 90000,
                                    "wall": w, "rc": 0, "ended": None}) + "\n")
            f.write(json.dumps({"kind": "ground_place.py --all", "what": "ground places", "root": "/w/transport-game-447",
                                "t": NOW - 7200, "wall": 1500, "rc": 86, "ended": "idle 10 min"}) + "\n")
        self.wt = os.path.join(self.tmp, "www", "Claude", "transport-game-801")
        self.main = os.path.join(self.tmp, "www", "Claude", "transport-game")
        for d in (self.wt, self.main):
            os.makedirs(d)
        self.home = os.path.join(self.tmp, "home")
        text = {"type": "user", "cwd": self.main, "message": {"content": MARKER}, "timestamp": "2026-11-23T08:00:00Z"}
        # a Claude Code session started in the main checkout working on #801 (its PR linked), one in the worktree
        # itself, a Codex session in the worktree, and a session of another project
        write_log(os.path.join(self.home, ".claude", "projects", "p", "a.jsonl"),
                  [text, {"type": "pr-link", "prNumber": 810, "prRepository": overview.REPO, "prUrl": MARKER},
                   {"type": "last-prompt", "lastPrompt": MARKER}, {"type": "custom-title", "customTitle": MARKER}])
        write_log(os.path.join(self.home, ".claude", "projects", "p", "b.jsonl"), [{**text, "cwd": self.wt}])
        write_log(os.path.join(self.home, ".codex", "sessions", "2026", "11", "23", "rollout-c.jsonl"),
                  [{"type": "session_meta", "payload": {"cwd": os.path.join(self.wt, "tools"), "base_instructions": MARKER}},
                   {"type": "response_item", "payload": {"content": [{"text": MARKER}]}}])
        write_log(os.path.join(self.home, ".claude", "projects", "q", "other.jsonl"), [{**text, "cwd": self.tmp}])
        old = os.path.join(self.home, ".claude", "projects", "p", "old.jsonl")
        write_log(old, [{**text, "cwd": self.wt}])
        os.utime(old, (NOW - 3 * 86400, NOW - 3 * 86400))
        self.rows = [
            {"worktree": self.main, "branch": "main", "head": "a" * 40, "missing": False, "issue": None, "issueTitle": None,
             "agents": [], "lane": None, "label": False, "pr": None, "asks": [], "behind": 0, "ahead": 0, "files": [],
             "rebuilds": [], "recheck": [], "dirty": [], "touched": NOW - 50, "main": True, "flags": []},
            {"worktree": self.wt, "branch": "801-thing", "head": "b" * 40, "missing": False, "issue": 801,
             "issueTitle": "A thing", "agents": ["claude"], "lane": "tooling", "label": False,
             "pr": {"number": 810, "state": "OPEN", "draft": False, "mergeable": "MERGEABLE", "title": "A thing (#801)", "updated": None},
             "asks": [("Questions for the user", ["Which way?"])], "behind": 1, "ahead": 2, "files": ["tools/a.py"],
             "rebuilds": [], "recheck": [], "dirty": ["x"], "touched": NOW - 30, "main": False, "flags": ["asks", "ready"]},
        ]
        self.github = ([], [{"number": 810, "headRefName": "801-thing", "state": "OPEN"}],
                       [{"number": 801, "title": "A thing", "labels": [{"name": "lane:tooling"}, {"name": "agent:claude"}]},
                        {"number": 802, "title": "Asks", "labels": [{"name": "needs-user"}, {"name": "lane:world"}]},
                        {"number": 803, "title": "Free", "labels": [{"name": "lane:sim"}], "blockedBy": {"nodes": []}}])
        self.patches = [mock.patch.object(baseline_store, "LOCKS", locks), mock.patch.object(board, "rows", lambda *a, **k: self.rows),
                        mock.patch.object(board, "ROOT", self.main)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def snap(self, **kw):
        return overview.snapshot(NOW, github=self.github, home=self.home, free=30.0, **kw)


class Snapshot(Fixture):
    def test_the_snapshot(self):
        s = self.snap()
        me, parent = os.getpid(), os.getppid()
        jobs = {j["pid"]: j for j in s["heavy"]["jobs"]}
        self.assertEqual(list(jobs), [parent, me])
        self.assertEqual((jobs[parent]["expect"], jobs[parent]["expectFrom"], jobs[parent]["finish"]), (3600, "history", NOW + 3300))
        self.assertEqual((jobs[me]["start"], jobs[me]["finish"]), (NOW + 3300, NOW + 3480))  # (shared, after the alone one)
        self.assertEqual(jobs[me]["root"], "transport-game-9")
        self.assertEqual([e["ended"] for e in s["heavy"]["ended"]], ["idle 10 min"])
        self.assertEqual(s["heavy"]["freeGb"], 30.0)
        ss = {(x["agent"], x["folder"]): x for x in s["sessions"]}
        self.assertEqual(set(ss), {("claude", "Claude/transport-game"), ("claude", "Claude/transport-game-801"),
                                   ("codex", "Claude/transport-game-801/tools")})  # (not another project's, not one 3 days old)
        self.assertEqual([(x["issue"], x["pr"] and x["pr"]["number"]) for x in s["sessions"]], [(801, 810)] * 3)
        self.assertEqual(s["waiting"]["questions"], [{"pr": 810, "title": "A thing (#801)", "issue": 801,
                                                     "sections": [{"title": "Questions for the user", "items": ["Which way?"]}]}])
        self.assertEqual(s["waiting"]["needsUser"], [{"number": 802, "title": "Asks"}])
        self.assertEqual(s["waiting"]["readyPrs"], [{"pr": 810, "title": "A thing (#801)", "issue": 801}])
        rows = {r["name"]: r for r in s["board"]["rows"]}
        self.assertEqual((rows["#801"]["worktree"], rows["#801"]["files"], rows["#801"]["dirty"]), ("transport-game-801", "tools 1", 1))
        self.assertEqual([i["number"] for i in s["board"]["ready"]["sim"]["issues"]], [803])
        self.assertEqual(json.loads(json.dumps(s)), s)

    def test_no_text_of_a_log_gets_in(self):
        text = json.dumps(self.snap())
        self.assertNotIn(MARKER, text)
        self.assertNotIn(self.tmp.replace("\\", "\\\\"), text)  # (no full path: the user's name stays off the page)

    def test_a_log_read_from_its_end_only(self):
        p = os.path.join(self.tmp, "big.jsonl")
        write_log(p, [{"cwd": "/first", "type": "user"}] + [{"type": "assistant", "x": "y" * 1000}] * 300
                  + [{"cwd": "/last", "type": "user"}, {"type": "pr-link", "prNumber": 5, "prRepository": overview.REPO}])
        reads = []
        real = open

        class Spy:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.f.close()

            def read(self, n=-1):
                reads.append(n)
                return self.f.read(n)

            def __getattr__(self, k):
                return getattr(self.f, k)
        with mock.patch("builtins.open", lambda *a, **k: Spy(real(*a, **k))):
            self.assertEqual(overview.read_log(p, chunk=4096), ("/last", 5))
        self.assertEqual(reads, [4096])
        # (another repository's PR is not this one's; a cwd only in the first line is found there)
        write_log(p, [{"type": "session_meta", "payload": {"cwd": "/w"}}] + [{"type": "x", "y": "z" * 1000}] * 30
                  + [{"type": "pr-link", "prNumber": 6, "prRepository": "someone/else"}])
        self.assertEqual(overview.read_log(p, chunk=4096, most=8192), ("/w", None))


class Upload(Fixture):
    def setUp(self):
        super().setUp()
        self.server = os.path.join(self.tmp, "httpdocs")
        os.makedirs(self.server)
        self.cfg = os.path.join(self.tmp, "deploy.local.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"host": "ftp.example", "user": "u", "dir": "/httpdocs",
                       "targets": {"alpha": {"public": True}}}, f)
        for p in (mock.patch.object(overview, "OUT", os.path.join(self.tmp, "overview.json")),
                  mock.patch.object(overview, "STATE", os.path.join(self.tmp, "state.json")),
                  mock.patch.object(overview, "CACHE", os.path.join(self.tmp, "cache.json")),
                  mock.patch.dict(os.environ, {"TRAM_DEPLOY_PASSWORD": "x"})):
            p.start()
            self.patches.append(p)
        self.log = open(os.path.join(self.tmp, "log.txt"), "w", encoding="utf-8")
        self.connects = 0
        self.refuse = False

    def tearDown(self):
        self.log.close()
        super().tearDown()

    def connect(self, cfg, pw):
        self.connects += 1
        if self.refuse:
            raise ftplib.error_perm("530 Login incorrect")
        self.assertEqual((cfg["name"], cfg.get("public")), ("test", None))
        self.ftp = FakeFtp(self.server)
        return self.ftp

    def run_once(self, t):
        code = overview.once(self.log, NOW + t, self.connect, self.cfg, github=self.github, home=self.home, free=30.0)
        self.assertEqual(code, 0)
        return self.connects

    def test_only_on_change_or_after_the_heartbeat(self):
        self.assertEqual(self.run_once(0), 1)
        with open(os.path.join(self.server, "overview.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["time"], NOW)
        self.assertEqual(self.run_once(60), 1)  # (the same snapshot a minute later: no upload)
        self.github[2].append({"number": 804, "title": "New", "labels": [{"name": "needs-user"}]})
        self.assertEqual(self.run_once(120), 2)  # (changed)
        self.assertEqual(self.run_once(120 + overview.HEARTBEAT - 1), 2)
        self.assertEqual(self.run_once(120 + overview.HEARTBEAT), 3)  # (unchanged, but the page must see the PC is on)
        with open(overview.OUT, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["time"], NOW + 120 + overview.HEARTBEAT)

    def test_a_refused_login_waits_an_hour(self):
        self.refuse = True
        self.assertEqual(self.run_once(0), 1)
        self.github[2].append({"number": 804, "title": "New", "labels": [{"name": "needs-user"}]})
        self.assertEqual(self.run_once(60), 1)  # (changed, but no second try within the hour)
        self.refuse = False
        self.assertEqual(self.run_once(overview.RETRY), 2)
        self.assertTrue(os.path.exists(os.path.join(self.server, "overview.json")))

    def test_never_a_public_target(self):
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"host": "ftp.example", "user": "u", "public": True}, f)
        with self.assertRaises(SystemExit):
            overview.once(self.log, NOW, self.connect, self.cfg, github=self.github, home=self.home, free=30.0)
        self.assertEqual(self.connects, 0)


class Deploy(unittest.TestCase):
    def test_a_deploy_keeps_the_overview(self):
        up, gone = deploy.plan({"index.html": "1"}, {"index.html": "0", "old.js": "2", "overview.json": "3"})
        self.assertEqual((up, gone), (["index.html"], ["old.js"]))

    def test_the_page_is_no_public_targets(self):
        for f in ("overview.html", "src/overview.js"):
            self.assertTrue(f.startswith(deploy.REVIEW_TOOLS), f)
        bad = deploy.public_ok("https://x/", get=lambda url, p: 200 if p in ("", "version.json", "overview.html") else
                               403 if p.endswith("/") else 404)
        self.assertEqual(bad, ["/overview.html answers 200, wants 404"])


if __name__ == "__main__":
    unittest.main()
