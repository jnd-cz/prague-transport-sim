# SPDX-License-Identifier: AGPL-3.0-or-later
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
import build_id  # noqa: E402
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
        for f in ("atomic.py", "stepcache.py", "step_inputs.py"):
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

    def test_a_shared_cache_holds_in_another_checkout(self):
        # (#797: the cache beside the machine's data cache. A second checkout of the same files, with no data yet,
        # skips every step and gets the outputs; a change there runs there and leaves the first checkout's records)
        shared = tempfile.mkdtemp(prefix="test_rebuild_cache_")
        self.addCleanup(shutil.rmtree, shared, True)
        self.addCleanup(os.environ.pop, stepcache.DIR_ENV, None)
        one = self.root
        rebuild.CACHE = stepcache.Cache(one, shared)
        self.assertEqual(self.build(), [0, 0])
        first = self.data()
        self.assertFalse(os.path.exists(os.path.join(one, "reports", "rebuild", "cache")))
        two = tempfile.mkdtemp(prefix="test_rebuild_two_")
        self.addCleanup(shutil.rmtree, two, True)
        for d in ("tools", "raw"):
            shutil.copytree(os.path.join(one, d), os.path.join(two, d), ignore=shutil.ignore_patterns("__pycache__"))
        for d in ("data", "reports/rebuild"):
            os.makedirs(os.path.join(two, d))
        self.root = rebuild.ROOT = two
        rebuild.CACHE = stepcache.Cache(two, shared)
        self.assertEqual(self.build(), ["skip", "skip"])
        self.assertEqual(self.data(), first)
        self.write("raw/in.txt", "two")
        self.assertEqual(self.build(), [0, 0])
        self.assertEqual(self.data()["src"], "two")
        self.root = rebuild.ROOT = one
        rebuild.CACHE = stepcache.Cache(one, shared)
        self.assertEqual(self.build(), ["skip", "skip"])
        self.assertEqual(self.data(), first)
        # (without a folder given the cache is the checkout's own again, and knows nothing of these runs)
        rebuild.CACHE = stepcache.Cache(one)
        self.assertNotIn(stepcache.DIR_ENV, os.environ)
        self.assertEqual(self.build(), [0, 0])

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

    def test_a_declared_input_in_the_key(self):
        """A file outside the checkout (the city mesh the ground reads, #702) is not traced: the step declares it by a
        value that changes with it, and another value runs it again."""
        log = os.path.join(self.root, "reports", "rebuild", "line9.a.log")
        run = lambda k: rebuild.run_step("line9", ["a.py", "--line", "9"], log, declared={"city mesh": k})[2]  # noqa: E731
        self.assertEqual(run("k1"), 0)
        self.assertEqual(run("k1"), "skip")
        name = rebuild.CACHE.name("line9", "a.py", ["--line", "9"])
        self.assertEqual(rebuild.CACHE.records(name)[0]["declared"], {"city mesh": "k1"})
        self.assertEqual(rebuild.CACHE.match(name, env=rebuild.step_env("line"), declared={"city mesh": "k2"}),
                         (None, "city mesh k1 → k2"))
        self.assertEqual(run("k2"), 0)
        self.assertEqual(run("k1"), "skip")  # (the earlier record is kept beside it)
        self.assertEqual(rebuild.run_step("line9", ["a.py", "--line", "9"], log)[2], 0)  # (none declared: another key)

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
            res = rebuild.side_by_side("9", [[["b.py", "--line", "9"]], [["c.py", "--line", "9"]]], times)
            return [t[2] for _, ts in res for t in ts]
        self.assertEqual(phase(), [0, 0])
        name = rebuild.CACHE.name("line9", "c.py", ["--line", "9"])
        self.assertEqual(rebuild.CACHE.records(name)[0]["phase"], ["data/x.json"])
        self.assertEqual(phase(), ["skip", "skip"])
        self.write("tools/b.py", B.replace("B_ADD", "10"))
        self.assertEqual(phase(), [0, "skip"])  # (b's new output is not what c read)

    def test_reader_after_the_steps_before_reads_and_keys_their_output(self):
        """d after a and b, beside nothing that writes x.json (as dtm after build_line and platforms, #617): it reads
        b's output every time, and a change to b runs d again."""
        self.write("tools/d.py", C.replace('d["src"]', 'd["b"]').replace("c.json", "d.json"))

        def phase():
            fail, times = rebuild.run_steps("9", [["a.py", "--line", "9"], ["b.py", "--line", "9"]])
            res = rebuild.side_by_side("9", [[["d.py", "--line", "9"]]], times)
            with open(os.path.join(self.root, "data", "d.json"), encoding="utf-8") as f:
                return [t[2] for t in times] + [t[2] for _, ts in res for t in ts], json.load(f)
        self.assertEqual(phase(), ([0, 0, 0], 1))
        self.assertEqual(phase(), (["skip", "skip", "skip"], 1))
        self.write("tools/b.py", B.replace("B_ADD", "10"))
        self.assertEqual(phase(), (["skip", 0, 0], 10))

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

    def test_a_needed_input_missing_stops_the_build(self):
        """#701: placement read the survey only where it was there, and beside dtm.py it was not yet (or half): under
        rebuild a step that needs a missing input stops and names it; run without needing it, it goes on."""
        self.write("tools/n.py", "import os, sys\nROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))\n"
                                 "sys.path.insert(0, os.path.join(ROOT, 'tools'))\nimport step_inputs\n"
                                 "print('survey', step_inputs.there(os.path.join(ROOT, 'data', 's.json'), ROOT))\n")
        log = os.path.join(self.root, "reports", "rebuild", "line9.n.log")
        fail, _ = rebuild.run_steps("9", [["n.py"]], needs=("data/s.json",))
        self.assertEqual(fail, "n.py")
        self.assertIn("data/s.json: missing", open(log, encoding="utf-8").read())
        fail, times = rebuild.run_steps("9", [["n.py"]])
        self.assertIsNone(fail)
        self.assertIn("survey False", open(log, encoding="utf-8").read())
        self.write("data/s.json", "{}")
        fail, _ = rebuild.run_steps("9", [["n.py"]], needs=("data/s.json",))
        self.assertIsNone(fail)
        self.assertIn("survey True", open(log, encoding="utf-8").read())

    def test_prune(self):
        with mock.patch.object(stepcache, "KEEP", 2):
            self.build()
            self.write("raw/in.txt", "two")
            self.build()
            self.write("raw/in.txt", "three")
            self.build()  # (KEEP records per step: the first run's outputs are named by none)
        n, _ = rebuild.CACHE.prune()
        self.assertGreater(n, 0)
        self.assertEqual(self.build(), ["skip", "skip"])


# (steps that read data/truth.json as the build steps do, each writing what it read to data/<name>.out, #816)
READER = '''import json, os, sys
from pathlib import Path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRUTH = os.path.join(ROOT, "data", "truth.json")
{body}
open(os.path.join(ROOT, "data", os.path.basename(__file__)[:-3] + ".out"), "w", encoding="utf-8").write(json.dumps(out))
'''
READERS = {
    # (build_line: one section through json.load and .get)
    "signs": 'out = json.load(open(TRUTH, encoding="utf-8")).get("stopSigns", {}).get("signs", [])',
    # (track_styles, line_heights: Path.read_text, json.loads and [])
    "kerbs": 'out = json.loads(Path(TRUTH).read_text(encoding="utf-8"))["kerbFacts"]',
    # (a section the file does not hold: its absence is the key)
    "none": 'out = json.load(open(TRUTH, encoding="utf-8")).get("noSuchSection")',
    # (the whole file read: its items)
    "every": 'out = sorted(k for k, v in json.load(open(TRUTH, encoding="utf-8")).items())',
    # (the text read without a parse)
    "raw": 'out = len(open(TRUTH, encoding="utf-8").read())',
    # (parsed, no section read)
    "nothing": 'out = bool(json.load(open(TRUTH, encoding="utf-8")))',
    # (copied whole, then one section read from the copy)
    "copied": 'out = dict(json.load(open(TRUTH, encoding="utf-8")))["stopSigns"]',
}
# (a step whose multiprocessing children read the file when they import it, as street_profile's workers do)
POOL = '''import json, os
from concurrent.futures import ProcessPoolExecutor
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "data", "truth.json"), encoding="utf-8") as fh:
    GEOMETRY = json.load(fh)["streetGeometry"]


def work(n):
    return GEOMETRY["radius"] * n


if __name__ == "__main__":
    with ProcessPoolExecutor(2) as ex:
        out = list(ex.map(work, [1, 2]))
    open(os.path.join(ROOT, "data", "pool.out"), "w", encoding="utf-8").write(json.dumps(out))
'''
TRUTH = {"readers": {"stopSigns": "signs"}, "stopSigns": {"signs": [1]}, "kerbFacts": {"places": [2]},
         "streetGeometry": {"radius": 3}, "groundPlaces": {"places": [{"name": "a"}]}}


class TruthSectionsTest(unittest.TestCase):
    """#816: a step is keyed by the sections of data/truth.json it read, not by the whole file."""
    write, restore = StepCacheTest.write, StepCacheTest.restore

    def setUp(self):
        StepCacheTest.setUp(self)
        for n, body in READERS.items():
            self.write(f"tools/{n}.py", READER.format(body=body))
        self.write("tools/pool.py", POOL)
        self.truth(TRUTH)

    def truth(self, t):
        self.write("data/truth.json", json.dumps(t, indent=2))

    def run_all(self, names=(*READERS, "pool")):
        fail, times = rebuild.run_steps("9", [[f"{n}.py"] for n in names])
        self.assertIsNone(fail, open(os.path.join(self.root, "reports", "rebuild", f"line9.{fail[:-3]}.log")).read() if fail else "")
        return {t[0][:-3]: t[2] for t in times}, {t[0][:-3]: t[3] for t in times}

    def changed(self, section, value):
        t = json.loads(open(os.path.join(self.root, "data", "truth.json"), encoding="utf-8").read())
        t[section] = value
        self.truth(t)

    def test_a_section_the_step_did_not_read_leaves_it_skipped(self):
        self.assertEqual(set(self.run_all()[0].values()), {0})
        self.assertEqual(set(self.run_all()[0].values()), {"skip"})
        self.changed("groundPlaces", {"places": [{"name": "a"}, {"name": "b"}]})  # (a ground PR's new place)
        codes, why = self.run_all()
        self.assertEqual(codes, {"signs": "skip", "kerbs": "skip", "none": "skip", "pool": "skip",
                                 "every": 0, "raw": 0, "nothing": 0, "copied": 0})
        self.assertEqual(why["every"], "data/truth.json changed")
        self.changed("stopSigns", {"signs": [1, 5]})
        codes, why = self.run_all()
        self.assertEqual((codes["signs"], codes["kerbs"], codes["copied"]), (0, "skip", 0))
        self.assertEqual(why["signs"], "data/truth.json: stopSigns changed")
        self.assertEqual(json.load(open(os.path.join(self.root, "data", "signs.out"), encoding="utf-8")), [1, 5])
        self.changed("noSuchSection", {"now": "there"})
        codes, why = self.run_all(["none", "signs"])
        self.assertEqual((codes, why["none"]), ({"none": 0, "signs": "skip"}, "data/truth.json: noSuchSection there"))

    def test_the_record_holds_the_sections_read(self):
        _, times = rebuild.run_steps("9", [["kerbs.py"], ["every.py"], ["pool.py"]])
        kerbs, every, pool = (t[5] for t in times)
        self.assertTrue(kerbs["inputs"]["data/truth.json"].startswith(stepcache.SECTIONS))
        self.assertEqual(kerbs["sections"], {"data/truth.json": {"kerbFacts": stepcache.section_hash(TRUTH["kerbFacts"])}})
        self.assertEqual(every["inputs"]["data/truth.json"], rebuild.CACHE.hashes.state("data/truth.json"))
        self.assertNotIn("sections", every)
        self.assertEqual(set(pool["sections"]["data/truth.json"]), {"streetGeometry"})  # (read by the step and its children)
        self.changed("streetGeometry", {"radius": 4})
        self.assertEqual(self.run_all(["pool"])[0], {"pool": 0})
        self.assertEqual(json.load(open(os.path.join(self.root, "data", "pool.out"), encoding="utf-8")), [4, 8])

    def test_a_truth_gone_runs_the_step_and_an_old_checkout_does_not_take_the_record(self):
        self.run_all(["signs"])
        os.remove(os.path.join(self.root, "data", "truth.json"))
        name = rebuild.CACHE.name("line9", "signs.py", [])
        self.assertEqual(rebuild.CACHE.match(name, env=rebuild.step_env("line"))[1], "data/truth.json not there")
        self.truth(TRUTH)
        rec = rebuild.CACHE.records(rebuild.CACHE.name("line9", "signs.py", []))[0]
        # (a checkout from before #816 compares the value with the file's hash: never equal, so it runs the step)
        self.assertNotEqual(rec["inputs"]["data/truth.json"], rebuild.CACHE.hashes.state("data/truth.json"))

    def test_the_noting_dict_reads_as_the_dict(self):
        seen = []
        s = stepcache.Sections({"a": 1, "b": {"c": 2}}, seen.append)
        self.assertEqual((s["a"], s.get("b"), "x" in s, s.get("x", 9)), (1, {"c": 2}, False, 9))
        self.assertTrue(s)
        self.assertEqual(seen, ["a", "b", "x", "x"])
        for whole in (lambda: list(s), lambda: dict(s), lambda: {**s}, lambda: json.dumps(s), len, lambda: s == {},
                      lambda: s.items(), lambda: __import__("copy").deepcopy(s), lambda: __import__("pickle").dumps(s)):
            seen.clear()
            whole() if whole is not len else len(s)
            self.assertIn(None, seen, whole)
        self.assertEqual(type(__import__("pickle").loads(__import__("pickle").dumps(s))), dict)


# (a made-up step of a line's chain by the real step's name: it reads its files (a CRC of each, so it sees a stamped file
# as another) and writes its own, or adds to the line file as the writers after build_line do)
FAKE = '''import json, os, sys, zlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from atomic import replacing
NAME, READS, WRITES, FRESH = {name!r}, {reads!r}, {writes!r}, {fresh!r}
seen = {{}}
for r in READS:
    p = os.path.join(ROOT, r)
    seen[r] = zlib.crc32(open(p, "rb").read()) if os.path.exists(p) else None
out = os.path.join(ROOT, WRITES)
d = {{"provenance": {{"lists": {{}}}}}} if FRESH else json.load(open(out, encoding="utf-8"))
d[NAME] = seen
with replacing(out, "w", encoding="utf-8") as f:
    json.dump(d, f)
'''
L = "data/line9.json"
CHAIN = {  # name: (what it reads, what it writes, a file of its own)
    "build_line": (["raw/in.txt"], L, True), "platforms": ([], L, False), "osm_speeds": ([], L, False),
    "cant": ([], L, False), "clearances": ([], L, False), "dtm_points": ([L], "data/line9.dtmpoints.json", True),
    "osm_validate": ([L], "data/line9.validate.json", True), "geoportal": (["raw/in.txt"], "data/line9.geo.json", True),
    "dtm": (["raw/in.txt"], "data/line9.dtm.json", True), "zps_source": (["data/line9.dtm.json"], "data/line9.zps.json", True),
    "placement": (["data/line9.dtm.json"], L, False), "track_styles": (["data/line9.dtm.json"], L, False),
    "line_heights": (["data/line9.dtm.json"], L, False), "line_structures": ([], L, False), "cross_level": ([], L, False),
    "street_profile": ([L, "data/line9.dtm.json"], "data/line9.streets.json", True),
    "ground_mesh": ([L, "data/line9.dtm.json", "data/line9.streets.json"], "data/line9.ground.json", True),
    "network": ([L, "data/line9.ground.json", "data/line9.dtm.json", "data/line9.geo.json"], "data/line9.network.json", True)}


class ChainTest(unittest.TestCase):
    """A line's whole chain (rebuild, heights, ground) with made-up steps and the real build_id.py: a second rebuild with
    nothing changed runs no step, though build_id rewrote the files the steps before it wrote (#702)."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="test_rebuild_chain_")
        self.addCleanup(shutil.rmtree, self.root, True)
        for d in ("tools", "data", "raw", "reports/rebuild"):
            os.makedirs(os.path.join(self.root, d))
        for f in ("atomic.py", "stepcache.py", "step_inputs.py", "build_id.py"):
            shutil.copy(os.path.join(TOOLS, f), os.path.join(self.root, "tools", f))
        for name, (reads, writes, fresh) in CHAIN.items():
            self.write(f"tools/{name}.py", FAKE.format(name=name, reads=reads, writes=writes, fresh=fresh))
        self.write("raw/in.txt", "one")
        self.saved = rebuild.ROOT, rebuild.CACHE, set(rebuild.FORCE)
        self.addCleanup(self.restore)
        rebuild.ROOT, rebuild.CACHE = self.root, stepcache.Cache(self.root)
        rebuild.FORCE.clear()
        self.mesh = "k1"
        for p in (mock.patch.dict(rebuild.DTM, {"9": ["x"]}), mock.patch.dict(rebuild.HOLD, {}, clear=True),
                  mock.patch.object(rebuild, "select_packages", lambda *a, **k: []),
                  mock.patch.object(rebuild, "city_mesh", lambda: self.mesh)):
            p.start()
            self.addCleanup(p.stop)

    restore = StepCacheTest.restore
    write = StepCacheTest.write

    def chain(self):
        """The line's three phases as rebuild.main runs them: their summaries."""
        with contextlib.redirect_stdout(io.StringIO()):
            return [rebuild.rebuild("9"), rebuild.heights(["9"]), rebuild.ground(["9"])]

    def files(self):
        d = os.path.join(self.root, "data")
        return {f: open(os.path.join(d, f), "rb").read() for f in sorted(os.listdir(d))}

    def test_a_second_rebuild_runs_no_step(self):
        first = self.chain()
        self.assertTrue(all("FAILED" not in r and "skipped" not in r for r in first), first)
        want, off = build_id.check("9", self.root)
        self.assertEqual(off, {})
        self.assertEqual(set(build_id.ids("9", self.root)), {"line9.geo.json", "line9.dtm.json", "line9.dtmpoints.json",
                                                            "line9.network.json", "line9.ground.json"})
        built = self.files()
        again = self.chain()
        self.assertEqual([r.rsplit(", ", 1)[1] for r in again], ["all 12 steps skipped", "all 4 steps skipped", "all 3 steps skipped"])
        self.assertEqual(self.files(), built)  # (each step's output put back, build_id's stamped files last)
        self.assertEqual(build_id.check("9", self.root), (want, {}))

    def test_the_ground_runs_on_another_city_mesh_and_the_network_after_it_only_if_it_changed(self):
        self.chain()
        self.mesh = "k2"
        r = self.chain()
        self.assertTrue(r[2].endswith("ran ground_mesh; 2 skipped"), r)  # (the same ground: the network and the ID stand)
        self.assertIn("city mesh k1 → k2", open(os.path.join(self.root, "reports", "rebuild", "ground.summary.log"), encoding="utf-8").read())
        self.write("tools/street_profile.py", FAKE.format(name="street_profile", reads=[L], writes="data/line9.streets.json", fresh=True))
        r = self.chain()
        self.assertTrue(r[1].endswith("ran street_profile; 3 skipped"), r)
        self.assertTrue(r[2].endswith("ran ground_mesh, network, build_id"), r)  # (a new ground, a new network on it)
        self.assertEqual(build_id.check("9", self.root)[1], {})

    def test_a_line_file_changed_stamps_every_file_again(self):
        self.chain()
        old = build_id.line_id("9", self.root)
        self.write("raw/in.txt", "two")
        self.assertTrue(all("FAILED" not in r for r in self.chain()))
        want, off = build_id.check("9", self.root)
        self.assertNotEqual(want, old)
        self.assertEqual(off, {})


class StepsTest(unittest.TestCase):
    def test_ground_network_and_build_id_after_the_street_surfaces(self):
        """#702: the ground reads the street surfaces, the network the ground file, the build ID every file: each a step
        of the cache, --from names them."""
        self.assertEqual([st[0] for st in rebuild.ground_steps("17")], ["ground_mesh.py", "network.py", "build_id.py"])
        self.assertIn("--no-network", rebuild.ground_steps("17")[0])  # (the network a step of its own)
        self.assertTrue({"ground_mesh", "network", "build_id"} <= rebuild.names())
        self.assertEqual(rebuild.args(["9", "--from", "ground"])[2], {"ground_mesh"})

    def test_platforms_before_the_survey(self):
        """dtm reads the platforms platforms.py writes (the shelters' stops, #617): it runs before the groups, and no
        group beside dtm's writes them."""
        with mock.patch.dict(rebuild.DTM, {"17": ["x"]}), mock.patch.object(rebuild, "select_packages", lambda *a, **k: []):
            first, groups, then = rebuild.steps("17")
        self.assertEqual([st[0] for st in first], ["build_line.py", "platforms.py"])
        flat = [st[0] for g in groups for st in g]
        self.assertNotIn("platforms.py", flat)
        self.assertIn("dtm.py", flat)
        self.assertEqual({st[0] for st in first} | set(flat),
                         {"build_line.py", "geoportal.py", "dtm.py", "zps_source.py"}
                         | {w[0] for w in rebuild.writers("17")})

    def test_placement_after_the_survey(self):
        """placement reads the survey for the stop types (#701): it runs after the groups, dtm's among them, and before
        the track styles; the steps after dtm need the survey file of a line that has one, not of one that has none."""
        with mock.patch.dict(rebuild.DTM, {"17": ["x"]}), mock.patch.object(rebuild, "select_packages", lambda *a, **k: []), \
                mock.patch.dict(rebuild.HOLD, {}, clear=True):
            _, groups, then = rebuild.steps("17")
            self.assertEqual(rebuild.needs("17"), ("data/line17.dtm.json",))
        self.assertNotIn("placement.py", [st[0] for g in groups for st in g])
        self.assertEqual([st[0] for st in then], ["placement.py", "track_styles.py"])
        with mock.patch.dict(rebuild.DTM, {}, clear=True):
            self.assertEqual(rebuild.needs("17"), ())
        self.assertIn("placement", rebuild.names())
        self.assertIn("track_styles", rebuild.names())


class ArgsTest(unittest.TestCase):
    def test_args(self):
        self.assertEqual(rebuild.args(["9", "17"]), (["9", "17"], False, set()))
        self.assertEqual(rebuild.args(["--parallel"])[1:], (True, set()))
        self.assertEqual(rebuild.args(["9", "--from", "track"]), (["9"], False, {"build_line"}))
        self.assertEqual(rebuild.args(["--force"])[2], {"*"})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(rebuild.args(["--from", "nothing"]))
        self.assertIn("the steps: build_id, build_line", out.getvalue())
        self.assertIsNone(rebuild.args(["--help"]))


if __name__ == "__main__":
    unittest.main()
