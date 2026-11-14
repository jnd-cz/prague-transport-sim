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

    def test_agents_md_names_every_tool_that_takes_its_turn(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        rule = re.search(r"\*\*Heavy jobs take turns:\*\*(.*?)\n- \*\*", text, re.S).group(1)
        tools = [p.name for p in sorted(TOOLS.glob("*.py")) if not p.name.startswith("test_")
                 and p.name not in ("baseline_store.py", "heavy.py") and queuing(p)]
        self.assertIn("rebuild.py", tools)
        for name in tools:
            self.assertIn(f"`{name}`", rule, f"{name} takes its turn: AGENTS.md's heavy jobs rule names it")


if __name__ == "__main__":
    unittest.main()
