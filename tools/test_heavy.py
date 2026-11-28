# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/heavy.py: a command in its turn among the heavy jobs, a tool's turn held until it exits, and the tools that are
heavy jobs when run alone taking it (#536). python -I tools/test_heavy.py"""
import ast
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import baseline_store  # noqa: E402
import heavy  # noqa: E402

# (a job of its own that holds its turn until a file appears)
HOLD = ("import os, sys, time; sys.path.insert(0, sys.argv[1]); import baseline_store as b\n"
        "with b.HeavyJob(sys.argv[2], wait=False):\n"
        "    print('in', flush=True)\n"
        "    while not os.path.exists(sys.argv[3]):\n"
        "        time.sleep(0.05)\n")


class Queue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        # (a queue of the test's own: baseline_store.LOCKS lies in the temp directory)
        self.env = {**os.environ, "TMP": self.tmp.name, "TEMP": self.tmp.name, "TMPDIR": self.tmp.name}
        self.env.pop(heavy.HELD, None)
        self.env.pop("TRAM_HEAVY_NOWAIT", None)
        self.env["TRAM_HEAVY_DAY"] = "1"  # (the turns, not the hour: a job of unknown time is not held for the night, #851)
        self.locks = os.path.join(self.tmp.name, "tram-heavy")

    def tearDown(self):
        self.tmp.cleanup()

    def states(self):
        out = []
        for n in os.listdir(self.locks) if os.path.isdir(self.locks) else []:
            if n.endswith(".lock"):
                try:
                    with open(os.path.join(self.locks, n), encoding="utf-8") as f:
                        j = json.load(f)
                except (OSError, ValueError):
                    continue
                out.append((j["what"], j["state"]))
        return sorted(out)

    def heavy(self, *args, **kw):
        return [sys.executable, "-I", str(TOOLS / "heavy.py"), *args]

    def py(self, code, *args):
        return subprocess.run([sys.executable, "-I", "-c", code, str(TOOLS), *args], env=self.env, capture_output=True,
                              text=True, timeout=60)

    def test_the_command_runs_in_its_turn_and_its_exit_code_comes_back(self):
        code = "import os, sys; print(os.environ.get('TRAM_HEAVY_HELD') == str(os.getppid())); sys.exit(3)"
        r = subprocess.run(self.heavy("a job", "--", sys.executable, "-I", "-c", code), env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "True"), r.stderr)
        self.assertIn("heavy.py: a job done in", r.stderr)
        self.assertEqual(self.states(), [])

    def test_the_command_waits_for_the_job_running(self):
        release, marker = os.path.join(self.tmp.name, "release"), os.path.join(self.tmp.name, "ran")
        a = subprocess.Popen([sys.executable, "-I", "-c", HOLD, str(TOOLS), "a", release], env=self.env,
                             stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(a.stdout.readline().strip(), "in")
            b = subprocess.Popen(self.heavy("b", "--", sys.executable, "-I", "-c", f"open({marker!r}, 'w').close()"),
                                 env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            t = time.time()
            while ("b", "waiting") not in self.states() and time.time() - t < 30:
                time.sleep(0.1)
            self.assertEqual(self.states(), [("a", "running"), ("b", "waiting")])
            time.sleep(0.5)
            self.assertFalse(os.path.exists(marker))
        finally:
            open(release, "w").close()
            a.wait(timeout=30)
            a.stdout.close()
        out, err = b.communicate(timeout=60)
        self.assertEqual(b.returncode, 0, err)
        self.assertTrue(os.path.exists(marker))
        self.assertIn("heavy jobs: b waits for a in", err)

    def test_usage_without_a_command(self):
        r = subprocess.run(self.heavy("a job"), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("tools/heavy.py", r.stderr)

    def test_a_shared_command_runs_beside_a_shared_job_and_a_plain_one_waits(self):
        """#728: --shared GB,CORES for a count run or a build; the plain form is a timing, alone."""
        release = os.path.join(self.tmp.name, "release")
        hold = HOLD.replace("wait=False", "wait=False, share={'gb': 1, 'cores': 1}")
        a = subprocess.Popen([sys.executable, "-I", "-c", hold, str(TOOLS), "a", release], env=self.env,
                             stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(a.stdout.readline().strip(), "in")
            code = ("import json, os, sys; d = sys.argv[1]\n"
                    "print(sorted((j['what'], j['state'], j['share']) for j in (json.load(open(os.path.join(d, n), encoding='utf-8'))"
                    " for n in os.listdir(d) if n.endswith('.lock')))[1])")
            r = subprocess.run(self.heavy("--shared", "0.5,1", "b", "--", sys.executable, "-I", "-c", code, self.locks),
                               env=self.env, capture_output=True, text=True, timeout=60)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, "('b', 'running', {'gb': 0.5, 'cores': 1})"), r.stderr)
            b = subprocess.Popen(self.heavy("timing", "--", sys.executable, "-I", "-c", "pass"), env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            t = time.time()
            while ("timing", "waiting") not in self.states() and time.time() - t < 30:
                time.sleep(0.1)
            self.assertEqual(self.states(), [("a", "running"), ("timing", "waiting")])
        finally:
            open(release, "w").close()
            a.wait(timeout=30)
            a.stdout.close()
        _, err = b.communicate(timeout=60)
        self.assertEqual(b.returncode, 0, err)

    def test_shared_takes_two_numbers(self):
        self.assertEqual(heavy.shared("4,2"), {"gb": 4.0, "cores": 2})
        self.assertIsNone(heavy.shared("4"))
        r = subprocess.run(self.heavy("--shared", "lots", "a job", "--", sys.executable, "-I", "-c", "pass"), env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)

    def test_a_tools_turn_held_until_it_exits(self):
        r = self.py("import os, sys; sys.path.insert(0, sys.argv[1]); import heavy, baseline_store as b\n"
                    "heavy.turn('a tool')\n"
                    "print(os.environ['TRAM_HEAVY_HELD'] == str(os.getpid()), [(j['what'], j['state']) for j in b.queue()])")
        self.assertEqual(r.stdout.strip(), "True [('a tool', 'running')]", r.stderr)
        self.assertEqual(self.states(), [])

    def test_in_a_jobs_turn_a_tool_adds_nothing_and_imports_no_queue(self):
        self.env[heavy.HELD] = str(os.getpid())  # (this test is the job its step runs in)
        r = self.py("import sys; sys.path.insert(0, sys.argv[1]); import heavy\n"
                    "print(heavy.turn('a step'), 'baseline_store' in sys.modules)")
        self.assertEqual(r.stdout.strip(), "None False", r.stderr)
        self.assertEqual(self.states(), [])

    def test_the_same_variable_as_the_queue(self):
        self.assertEqual(heavy.HELD, baseline_store.HELD)

    def test_night_starts_early_and_ends(self):
        """#851: heavy.py --night on the maintainer's word, --night off."""
        on = subprocess.run([sys.executable, "-I", str(TOOLS / "heavy.py"), "--night"], env=self.env, capture_output=True,
                            text=True, timeout=60)
        self.assertEqual(on.returncode, 0, on.stderr)
        self.assertRegex(on.stderr, r"the night starts now, until 07:00 .*0 jobs held for it")
        self.assertTrue(os.path.exists(os.path.join(self.locks, "night.json")))
        off = subprocess.run([sys.executable, "-I", str(TOOLS / "heavy.py"), "--night", "off"], env=self.env,
                             capture_output=True, text=True, timeout=60)
        self.assertIn("the early night ended", off.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.locks, "night.json")))

    def test_options_before_the_name(self):
        """#815: --expect DURATION and --no-limit beside --shared, in any order."""
        self.assertEqual(heavy.options(["--expect", "20m", "--no-limit", "--shared", "4,2", "x", "--", "c"], baseline_store.seconds),
                         ({"share": {"gb": 4.0, "cores": 2}, "expect": 1200.0, "limits": False, "day": None}, ["x", "--", "c"]))
        self.assertEqual(heavy.options(["--day", "--expect", "2h", "x", "--", "c"], baseline_store.seconds),
                         ({"share": None, "expect": 7200.0, "limits": None, "day": True}, ["x", "--", "c"]))  # (#851)
        self.assertEqual(heavy.options(["x", "--", "c", "--no-limit"], baseline_store.seconds)[0],
                         {"share": None, "expect": None, "limits": None, "day": None})  # (the command's own options stay its own)
        for bad in (["--expect", "soon", "x"], ["--expect"], ["--fast", "x"]):
            self.assertIsNone(heavy.options(bad, baseline_store.seconds)[0], bad)

    def test_the_command_kind_and_expected_time_go_on_the_ticket_and_into_the_history(self):
        code = ("import json, os, sys; d = sys.argv[1]\n"
                "j, = (json.load(open(os.path.join(d, n), encoding='utf-8')) for n in os.listdir(d) if n.endswith('.lock'))\n"
                "print(j['kind'], j['expect'], j['watch'], j['stops'])")
        r = subprocess.run(self.heavy("--expect", "90s", "--no-limit", "k", "--", sys.executable, "-I", "-c", code, self.locks),
                           env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "python 90.0 False True"), r.stderr)  # (no limits: no ends)
        with open(os.path.join(self.locks, "history.jsonl"), "w", encoding="utf-8") as f:
            for w in (100, 200, 300):
                f.write(json.dumps({"kind": "python", "what": "k", "t": 0, "wall": w, "rc": 0, "ended": None, "gb": 1}) + "\n")
            f.write(json.dumps({"kind": "python", "what": "k", "t": 0, "wall": 99, "rc": None, "ended": "idle: …"}) + "\n")
        r = subprocess.run(self.heavy("k", "--", sys.executable, "-I", "-c", code, self.locks), env=self.env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "python 200 True True", r.stderr)  # (the median of the full runs)
        r = subprocess.run(self.heavy("--history"), env=self.env, capture_output=True, encoding="utf-8", timeout=60)
        self.assertIn("python | 3 | 3.3 | 1.5 | 1.0", r.stdout)
        self.assertRegex(r.stdout, r"ended: k \(python\) at .* after 2 min: idle: …")

    def test_stop_refuses_what_is_not_this_checkouts_job(self):
        r = subprocess.run(self.heavy("--stop", "4242424"), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no heavy job has pid 4242424", r.stderr)
        other = subprocess.Popen([sys.executable, "-I", "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (other.kill(), other.wait()))
        os.makedirs(self.locks)
        ticket = {"what": "theirs", "root": "C:/x/transport-game-1", "pid": other.pid, "t": 0, "state": "running",
                  "since": time.time(), "stops": True, "queue": baseline_store.QUEUE}
        with open(os.path.join(self.locks, f"{other.pid}.lock"), "w", encoding="utf-8") as f:
            json.dump(ticket, f)
        r = subprocess.run(self.heavy("--stop", str(other.pid)), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("theirs in transport-game-1, running 0 min is another checkout's job; --force", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.locks, f"{other.pid}.stop")))
        with open(os.path.join(self.locks, f"{other.pid}.lock"), "w", encoding="utf-8") as f:  # (an older checkout's)
            json.dump({k: v for k, v in ticket.items() if k != "stops"} | {"root": str(ROOT)}, f)
        r = subprocess.run(self.heavy("--stop", str(other.pid)), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not watch itself (its checkout is from before #815)", r.stderr)


def queuing(path):
    """Whether a tool takes a turn among the heavy jobs: it enters a HeavyJob or calls heavy.turn."""
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
            if name == "HeavyJob" or (name == "turn" and isinstance(f, ast.Attribute)
                                      and isinstance(f.value, ast.Name) and f.value.id == "heavy"):
                return True
    return False


class Tools(unittest.TestCase):
    def test_the_heavy_tools_take_their_turn(self):
        """#536: the steps over a minute or with workers, run alone, and the whole test suite."""
        for name in ("build_line.py", "dtm.py", "line_heights.py", "import_track_heights.py", "test_all.py"):
            self.assertTrue(queuing(TOOLS / name), name)

    def test_developing_md_names_every_tool_that_takes_its_turn(self):
        text = (ROOT / "DEVELOPING.md").read_text(encoding="utf-8")  # (moved from AGENTS.md, #727)
        rule = re.search(r"\*\*Heavy jobs\*\* \(.*?\n- (.*?)\n- ", text, re.S).group(1)
        tools = [p.name for p in sorted(TOOLS.glob("*.py")) if not p.name.startswith("test_")
                 and p.name not in ("baseline_store.py", "heavy.py") and queuing(p)]
        self.assertIn("rebuild.py", tools)
        for name in tools:
            self.assertIn(f"`{name}`", rule, f"{name} takes its turn: DEVELOPING.md's heavy jobs paragraph names it")


class Shell(unittest.TestCase):
    """#645: on Windows a plain `bash` or `sh` is Git Bash's, not WSL's (System32 comes before PATH)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, where, wrappers=True):
        """A Git for Windows layout of empty files: git.exe in `where` (under <Git>), bash.exe and sh.exe in usr/bin and
        (with `wrappers`) in bin."""
        g = Path(self.tmp.name, "Git")
        for f in [where + "/git.exe", "usr/bin/bash.exe", "usr/bin/sh.exe"] + (["bin/bash.exe", "bin/sh.exe"] if wrappers else []):
            (g / f).parent.mkdir(parents=True, exist_ok=True)
            (g / f).touch()
        return str(g / where / "git.exe"), str(g / ("bin" if wrappers else "usr/bin"))

    def test_a_plain_bash_or_sh_is_git_bash_wherever_git_lies(self):
        for where in ("cmd", "bin", "mingw64/bin", "ucrt64/bin"):
            git, shells = self.git(where)
            for name, exe in (("bash", "bash.exe"), ("BASH.EXE", "bash.exe"), ("sh", "sh.exe")):
                self.assertEqual(heavy.program([name, "job.sh", "a"], windows=True, git=git),
                                 [os.path.join(shells, exe), "job.sh", "a"], (where, name))

    def test_usr_bin_when_git_has_no_wrapper(self):
        git, shells = self.git("cmd", wrappers=False)
        self.assertEqual(heavy.program(["bash", "x.sh"], windows=True, git=git), [os.path.join(shells, "bash.exe"), "x.sh"])

    def test_other_commands_run_as_given(self):
        git, _ = self.git("cmd")
        for cmd in (["python", "-I", "x.py"], [r"C:\Windows\System32\bash.exe", "x.sh"], ["/usr/bin/bash", "x.sh"],
                    ["bashful"], []):
            self.assertEqual(heavy.program(cmd, windows=True, git=git), cmd)
        self.assertEqual(heavy.program(["bash", "x.sh"], windows=False, git=git), ["bash", "x.sh"])
        # (no Git for Windows next to git: as given)
        self.assertEqual(heavy.program(["bash", "x.sh"], windows=True, git=os.path.join(self.tmp.name, "git.exe")),
                         ["bash", "x.sh"])

    @unittest.skipUnless(os.name == "nt" and heavy.git_shell("bash"), "Windows with Git for Windows")
    def test_heavy_runs_a_bash_script_with_plain_bash(self):
        """As from PowerShell: only <Git>/cmd of Git's directories on PATH. The script finds Git's tools (uname)."""
        root = os.path.dirname(os.path.dirname(heavy.git_shell("bash")))
        path = [p for p in os.environ["PATH"].split(os.pathsep) if not os.path.normcase(p).startswith(os.path.normcase(root))]
        env = {**os.environ, "TMP": self.tmp.name, "TEMP": self.tmp.name, "TMPDIR": self.tmp.name,
               "PATH": os.pathsep.join([*path, os.path.join(root, "cmd")])}
        env.pop(heavy.HELD, None)
        env.pop("TRAM_HEAVY_NOWAIT", None)
        env["TRAM_HEAVY_DAY"] = "1"  # (not held for the night by day, #851)
        r = subprocess.run([sys.executable, "-I", str(TOOLS / "heavy.py"), "a script", "--", "bash", "-c",
                            'echo "$BASH_VERSION $(uname -s)"; exit 4'], env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertRegex(r.stdout.strip(), r"^\d+\.\d+\S* (MINGW|MSYS)")


if __name__ == "__main__":
    unittest.main()
