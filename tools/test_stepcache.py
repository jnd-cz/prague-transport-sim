# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/stepcache.py's files written from several threads at once (#521): tools/rebuild.py --parallel keeps each
line's steps from its own thread, each keep saving hashes.json, while the steps' tracers read it.

    python -I tools/test_stepcache.py

(The steps' keys and records: tools/test_rebuild.py.)
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import stepcache  # noqa: E402

THREADS, SAVES = 8, 40


def run(fns):
    """fns in threads started together; the errors they raised."""
    errors, go = [], threading.Barrier(len(fns))

    def body(f):
        go.wait()
        try:
            f()
        except Exception as e:
            errors.append(e)
    ts = [threading.Thread(target=body, args=(f,)) for f in fns]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    return errors


class Threads(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.dir = os.path.join(self.root, "reports", "rebuild", "cache")

    def tearDown(self):
        self.tmp.cleanup()

    def parts(self):
        return [os.path.join(d, n) for d, _, ns in os.walk(self.root) for n in ns if n.endswith(".part")]

    def test_hashes_saved_from_threads_at_once(self):
        """Threads saving while others read the file: none fails, the file ends with every hash noted."""
        path = os.path.join(self.dir, "hashes.json")
        h, stop = stepcache.Hashes(self.root, path), threading.Event()

        def saver(i):
            def f():
                for k in range(SAVES):
                    h.merge({f"t{i}/{k}": [k, k, i, f"{i}.{k}"]})
                    h.save()
            return f

        def reader():  # (the steps' tracers, each loading the file at its start; held open a little longer here)
            while not stop.is_set():
                if os.path.exists(path):
                    stepcache.Hashes(self.root, path)
                    with open(path, encoding="utf-8"):
                        time.sleep(0.001)
                time.sleep(0.005)

        rs = [threading.Thread(target=reader) for _ in range(2)]
        for t in rs:
            t.start()
        try:
            errors = run([saver(i) for i in range(THREADS)])
        finally:
            stop.set()
            for t in rs:
                t.join()
        self.assertEqual(errors, [])
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
        self.assertEqual(len(got), THREADS * SAVES)
        self.assertEqual(got, h.known)
        self.assertEqual(self.parts(), [])

    def test_replace_waits_for_a_reader(self):
        """A file held open while it is replaced: the rename waits for it on Windows, and passes on POSIX."""
        path = os.path.join(self.root, "x.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("old")
        with open(path + ".part", "w", encoding="utf-8") as f:
            f.write("new")
        held, done = threading.Event(), threading.Event()

        def hold():
            with open(path, encoding="utf-8"):
                held.set()
                done.wait(0.3)
        t = threading.Thread(target=hold)
        t.start()
        held.wait()
        try:
            stepcache.replace(path + ".part", path)
        finally:
            done.set()
            t.join()
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "new")
        self.assertFalse(os.path.exists(path + ".part"))

    def test_replace_gives_up(self):
        """A file that stays refused: the error after WAIT, and no temporary file left."""
        path = os.path.join(self.root, "x.json")
        with open(path + ".part", "w", encoding="utf-8") as f:
            f.write("new")
        with mock.patch.object(stepcache, "WAIT", 0.05), \
                mock.patch.object(stepcache, "_replace", side_effect=PermissionError(13, "held")) as r:
            with self.assertRaises(PermissionError):
                stepcache.replace(path + ".part", path)
        self.assertGreater(r.call_count, 1)
        self.assertEqual(self.parts(), [])

    def test_steps_kept_from_threads_at_once(self):
        """Cache.keep and Cache.put as rebuild.py's line threads call them: each line's records kept, one blob for
        content the lines share, hashes.json holding every line's files."""
        cache = stepcache.Cache(self.root)
        os.makedirs(os.path.join(self.root, "data"))
        os.makedirs(os.path.join(self.dir, "steps"))  # (as rebuild.py's first step leaves it: Cache.tmp_record)
        for i in range(THREADS):
            for n in (f"line{i}.json", f"same{i}.json"):
                with open(os.path.join(self.root, "data", n), "w", encoding="utf-8") as f:
                    f.write(f"line {i}" if n.startswith("line") else "the same in every line")

        def line(i):
            def f():
                for k in range(SAVES // 4):
                    outs = {r: cache.hashes.state(r) for r in (f"data/line{i}.json", f"data/same{i}.json")}
                    for r, s in outs.items():
                        cache.put(r, s)
                    cache.keep(f"line{i}.step{k}", {"when": str(k), "outputs": outs, "modules": {}, "inputs": {},
                                                    "listings": {}, "packages": {}, "env": {}})
            return f
        self.assertEqual(run([line(i) for i in range(THREADS)]), [])
        for i in range(THREADS):
            self.assertEqual(len(cache.records(f"line{i}.step0")), 1)
        same = cache.hashes.state("data/same0.json")
        self.assertTrue(os.path.exists(cache.blob(same)))
        with open(os.path.join(self.dir, "hashes.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 2 * THREADS)
        self.assertEqual(self.parts(), [])


if __name__ == "__main__":
    unittest.main()
