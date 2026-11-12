"""tools/rebuild.py with tools/stepcache.py: a step runs again only when what it read changed (#511).

    python -I tools/test_rebuild.py

Two made-up steps in a temporary checkout: a.py reads raw/in.txt, a module of its own, a file it may find and the
names in a folder, and writes data/x.json; b.py reads data/x.json and rewrites it (the steps after build_line do so).
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import rebuild  # noqa: E402
import stepcache  # noqa: E402

A = '''import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import helper
from atomic import replacing
src = open(os.path.join(ROOT, "raw", "in.txt"), encoding="utf-8").read()
extra = os.path.exists(os.path.join(ROOT, "raw", "extra.txt"))
cells = sorted(os.listdir(os.path.join(ROOT, "raw", "cells")))
with replacing(os.path.join(ROOT, "data", "x.json"), "w", encoding="utf-8") as f:
    json.dump({"src": src, "k": helper.K, "extra": extra, "cells": cells, "args": sys.argv[1:]}, f)
'''
B = '''import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from atomic import replacing
p = os.path.join(ROOT, "data", "x.json")
d = json.load(open(p, encoding="utf-8"))
d["b"] = d.get("b", 0) + B_ADD
with replacing(p, "w", encoding="utf-8") as f:
    json.dump(d, f)
'''
# (a reader beside the writers: c.py copies what it reads of data/x.json, as dtm.py reads build_line's output)
C = '''import json, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = json.load(open(os.path.join(ROOT, "data", "x.json"), encoding="utf-8"))
open(os.path.join(ROOT, "data", "c.json"), "w", encoding="utf-8").write(json.dumps(d["src"]))
'''

# (a step that hands its work to multiprocessing children: each reads raw/pN.txt and writes data/pN.out)
P = '''import os, sys
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def work(n):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import helper  # noqa: F401
    p = os.path.join(ROOT, "raw", f"p{n}.txt")
    text = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    open(os.path.join(ROOT, "data", f"p{n}.out"), "w", encoding="utf-8").write(text + "!")
    return n


if __name__ == "__main__":
    with ProcessPoolExecutor(2) as ex:
        print(list(ex.map(work, [1, 2])))
'''


class StepCacheTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="test_rebuild_")
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("tools", "data", "raw/cells", "reports/rebuild"):
            os.makedirs(os.path.join(self.root, d))
        for f in ("atomic.py", "stepcache.py"):
            shutil.copy(os.path.join(TOOLS, f), os.path.join(self.root, "tools", f))
        self.write("tools/helper.py", "K = 1\n")
        self.write("tools/a.py", A)
        self.write("tools/b.py", B.replace("B_ADD", "1"))
        self.write("tools/c.py", C)
        self.write("raw/in.txt", "one")
        self.write("raw/cells/1.bin", "1")
        self.saved = rebuild.ROOT, rebuild.CACHE, set(rebuild.FORCE)
        self.addCleanup(self.restore)
        rebuild.ROOT, rebuild.CACHE = self.root, stepcache.Cache(self.root)
        rebuild.FORCE.clear()

    def restore(self):
        rebuild.ROOT, rebuild.CACHE = self.saved[:2]
        rebuild.FORCE.clear()
        rebuild.FORCE.update(self.saved[2])

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        with open(p + ".part", "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(p + ".part", p)  # (a new file id, as the tools write: the hashes are keyed by it)

    def data(self):
        with open(os.path.join(self.root, "data", "x.json"), encoding="utf-8") as f:
            return json.load(f)

    def build(self):
        """a then b, as rebuild runs a line's chain; each step's exit code or "skip"."""
        fail, times = rebuild.run_steps("9", [["a.py", "--line", "9"], ["b.py", "--line", "9"]])
        self.assertIsNone(fail, open(os.path.join(self.root, "reports", "rebuild", f"line9.{fail[:-3]}.log")).read() if fail else "")
        return [t[2] for t in times]

    def test_unchanged_skips(self):
        self.assertEqual(self.build(), [0, 0])
        first = self.data()
        self.assertEqual(first["b"], 1)
        self.assertEqual(self.build(), ["skip", "skip"])
        self.assertEqual(self.data(), first)  # (b's output put back as it was, not b run twice)

    def test_changed_import_reruns(self):
        self.build()
        self.write("tools/helper.py", "K = 22\n")  # (another size: Python's bytecode cache goes by size and second)
        self.assertEqual(self.build(), [0, 0])
        self.assertEqual(self.data()["k"], 22)
        self.assertEqual(self.build(), ["skip", "skip"])

    def test_same_output_stops_there(self):
        self.build()
        self.write("tools/helper.py", "K = 1  # (a comment)\n")
        self.assertEqual(self.build(), [0, "skip"])  # (a's output is the same: b reads what it read)

    def test_changed_step_reads_what_it_read(self):
        self.build()
        self.write("tools/b.py", B.replace("B_ADD", "10"))
        self.assertEqual(self.build(), ["skip", 0])
        self.assertEqual(self.data()["b"], 10)  # (b read a's output, put back, not its own of the last run)

    def test_changed_input_reruns(self):
        self.build()
        self.write("raw/in.txt", "two")
        self.assertEqual(self.build(), [0, 0])
        self.assertEqual(self.data()["src"], "two")

    def test_new_probed_file_reruns(self):
        self.build()
        self.write("raw/extra.txt", "")
        self.assertEqual(self.build(), [0, 0])
        self.assertTrue(self.data()["extra"])

    def test_new_file_in_listed_folder_reruns(self):
        self.build()
        self.write("raw/cells/2.bin", "2")
        self.assertEqual(self.build(), [0, 0])
        self.assertEqual(self.data()["cells"], ["1.bin", "2.bin"])
        self.write("tools/other.py", "")  # (a new tool beside the steps: the import system's listing is no input)
        self.write("raw/cells/3.bin.4711.part", "")  # (another step's write in flight)
        self.assertEqual(self.build(), ["skip", "skip"])

    def test_lost_output_put_back(self):
        self.build()
        first = self.data()
        os.remove(os.path.join(self.root, "data", "x.json"))
        self.assertEqual(self.build(), ["skip", "skip"])
        self.assertEqual(self.data(), first)

    def test_from_and_force(self):
        self.build()
        rebuild.FORCE.add("b")
        self.assertEqual(self.build(), ["skip", 0])
        self.assertEqual(self.data()["b"], 1)
        rebuild.FORCE.clear()
        rebuild.FORCE.add("*")
        self.assertEqual(self.build(), [0, 0])

    def test_record_names_what_was_read(self):
        self.build()
        name = rebuild.CACHE.name("line9", "a.py", ["--line", "9"])
        rec = rebuild.CACHE.records(name)[0]
        self.assertEqual(set(rec["modules"]), {"tools/a.py", "tools/helper.py", "tools/atomic.py"})
        self.assertEqual(set(rec["inputs"]), {"raw/in.txt", "raw/extra.txt"})
        self.assertIsNone(rec["inputs"]["raw/extra.txt"])  # (probed, not there)
        self.assertEqual(set(rec["listings"]), {"raw/cells"})
        self.assertEqual(set(rec["outputs"]), {"data/x.json"})  # (not atomic's temporary file)
        self.assertEqual(rec["env"]["OPENBLAS_NUM_THREADS"], rebuild.BLAS["line"])
        self.write("raw/in.txt", "two")
        self.assertEqual(rebuild.CACHE.match(name, env=rebuild.step_env("line")), (None, "raw/in.txt changed"))

    def test_blas_threads_in_the_key(self):
        """numpy's BLAS threads change results in their last bits: another number runs the step again."""
        self.build()
        with mock.patch.dict(rebuild.BLAS, {"line": "3"}):
            self.assertEqual(self.build(), [0, 0])
        self.assertEqual(self.build(), ["skip", "skip"])  # (the record of each number kept)

    def test_reader_beside_writers_keyed_as_before_them(self):
        """c beside b (b rewrites data/x.json while c reads it): c's key holds x.json as a left it."""
        def phase():
            fail, times = rebuild.run_steps("9", [["a.py", "--line", "9"]])
            res = rebuild.side_by_side("9", [[["b.py", "--line", "9"]], [["c.py", "--line", "9"]]], times[0])
            return [t[2] for _, ts in res for t in ts]
        self.assertEqual(phase(), [0, 0])
        name = rebuild.CACHE.name("line9", "c.py", ["--line", "9"])
        self.assertEqual(rebuild.CACHE.records(name)[0]["phase"], ["data/x.json"])
        self.assertEqual(phase(), ["skip", "skip"])
        self.write("tools/b.py", B.replace("B_ADD", "10"))
        self.assertEqual(phase(), [0, "skip"])  # (b's new output is not what c read)

    def test_child_processes_traced(self):
        """A step whose work runs in multiprocessing children: what they read and write is in its record."""
        self.write("tools/p.py", P)
        self.write("raw/p1.txt", "1")
        fail, times = rebuild.run_steps("9", [["p.py", "--line", "9"]])
        self.assertIsNone(fail, open(os.path.join(self.root, "reports", "rebuild", "line9.p.log")).read() if fail else "")
        rec = times[0][5]
        self.assertEqual(set(rec["outputs"]), {"data/p1.out", "data/p2.out"})
        self.assertEqual(set(rec["inputs"]), {"raw/p1.txt", "raw/p2.txt"})
        self.assertIn("tools/helper.py", rec["modules"])  # (imported by the children only)
        self.assertNotIn("untraced", rec)
        self.assertEqual(rebuild.run_steps("9", [["p.py", "--line", "9"]])[1][0][2], "skip")
        self.write("raw/p1.txt", "one")  # (read by a child only)
        self.assertEqual(rebuild.run_steps("9", [["p.py", "--line", "9"]])[1][0][2], 0)
        self.assertEqual(open(os.path.join(self.root, "data", "p1.out"), encoding="utf-8").read(), "one!")

    def test_failed_step_keeps_no_record(self):
        self.write("tools/b.py", "raise SystemExit('no')\n")
        fail, times = rebuild.run_steps("9", [["a.py", "--line", "9"], ["b.py", "--line", "9"]])
        self.assertEqual(fail, "b.py")
        self.assertEqual(rebuild.CACHE.records(rebuild.CACHE.name("line9", "b.py", ["--line", "9"])), [])

    def test_prune(self):
        self.build()
        self.write("raw/in.txt", "two")
        self.build()
        self.write("raw/in.txt", "three")
        self.build()  # (KEEP records per step: the first run's outputs are named by none)
        n, _ = rebuild.CACHE.prune()
        self.assertGreater(n, 0)
        self.assertEqual(self.build(), ["skip", "skip"])


class ArgsTest(unittest.TestCase):
    def test_args(self):
        self.assertEqual(rebuild.args(["9", "17"]), (["9", "17"], False, set()))
        self.assertEqual(rebuild.args(["--parallel"])[1:], (True, set()))
        self.assertEqual(rebuild.args(["9", "--from", "track"]), (["9"], False, {"build_line"}))
        self.assertEqual(rebuild.args(["--force"])[2], {"*"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(rebuild.args(["--from", "nothing"]))
        self.assertIn("the steps: build_line", out.getvalue())
        self.assertIsNone(rebuild.args(["--help"]))


if __name__ == "__main__":
    unittest.main()
