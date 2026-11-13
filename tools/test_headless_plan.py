# SPDX-License-Identifier: AGPL-3.0-or-later
"""Batch planning from this machine's run times (#413): python -P -E tools/test_headless_plan.py"""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import headless  # noqa: E402

os.environ["TRAM_HEAVY_NOWAIT"] = "1"  # (main() here runs a mocked worker: no turn among the real heavy jobs)


def timings(runs, loads):
    return {"runs": {f"{l}|{c}|{s}": v for (l, c, s), v in runs.items()}, "loads": loads}


class Estimate(unittest.TestCase):
    def test_fallbacks(self):
        t = timings({("9", "drive", 1): 100, ("9", "drive", 2): 120, ("17", "lint", 0): 16, ("22", "lint", 0): 14,
                     ("23", "lint", 0): 5}, {"9": 25, "17": 34})
        self.assertEqual(headless.estimate(("9", "drive", 1), t), 100)  # timed
        self.assertEqual(headless.estimate(("9", "drive", 3), t), 110)  # the line's other seeds
        self.assertEqual(headless.estimate(("9", "lint", 0), t), 14)  # the check's median elsewhere
        self.assertEqual(headless.estimate(("9", "heights", 0), t), headless.RUN)  # never timed
        self.assertEqual(headless.load_of("17", t), 34)
        self.assertEqual(headless.load_of("23", t), 29.5)  # the median of the loads measured
        self.assertEqual(headless.load_of("23", {"runs": {}, "loads": {}}), headless.LOAD)

    def test_finish_takes_the_free_page(self):
        self.assertEqual(headless.finish([5, 3, 3, 2], 2), 7)  # 5 | 3+3, then 2 to the first: 7
        self.assertEqual(headless.finish([4, 4], 8), 4)


class Plan(unittest.TestCase):
    # (the nightly times of 2026-11-11 in shape: line 9 long, 23 and 37 short)
    T = timings({**{("9", "drive", s): 95 for s in range(1, 6)}, **{("9", "traffic", s): 90 for s in range(1, 6)},
                 **{("23", "drive", s): 27 for s in range(1, 6)}, **{("23", "traffic", s): 28 for s in range(1, 6)},
                 ("9", "lint", 0): 16, ("23", "lint", 0): 5}, {"9": 25, "23": 15})
    JOBS = [(l, c, s) for l in ("9", "23") for c in ("drive", "traffic") for s in range(1, 6)] + [("9", "lint", 0), ("23", "lint", 0)]

    def dur(self, b):
        return headless.load_of(b[0][0], self.T) + sum(headless.estimate(j, self.T) for j in b)

    def test_every_run_once_one_line_a_batch_longest_first(self):
        for pages in (1, 2, 4, 8):
            bs = headless.plan(self.JOBS, pages, self.T)
            self.assertEqual(sorted(j for b in bs for j in b), sorted(self.JOBS))
            self.assertTrue(all(len({j[0] for j in b}) == 1 for b in bs))
            d = [self.dur(b) for b in bs]
            self.assertEqual(d, sorted(d, reverse=True))

    def test_one_page_loads_each_line_once(self):
        self.assertEqual(len(headless.plan(self.JOBS, 1, self.T)), 2)

    def test_beats_six_a_batch_in_line_order(self):
        old = [b for line in ("23", "9") for mine in [[j for j in self.JOBS if j[0] == line]]
               for b in (mine[k:k + 6] for k in range(0, len(mine), 6))]
        for pages in (2, 4, 8):
            new = headless.plan(self.JOBS, pages, self.T)
            self.assertLessEqual(headless.finish(map(self.dur, new), pages), headless.finish(map(self.dur, old), pages))
        # 8 pages: line 9 spread wide, not 2 batches of 6 while line 23's pages idle
        new = headless.plan(self.JOBS, 8, self.T)
        self.assertLess(headless.finish(map(self.dur, new), 8), 0.6 * headless.finish(map(self.dur, old), 8))
        self.assertGreater(sum(b[0][0] == "9" for b in new), 3)

    def test_batch_caps_the_size(self):
        bs = headless.plan(self.JOBS, 8, self.T, batch=1)
        self.assertEqual(len(bs), len(self.JOBS))
        self.assertEqual(bs[0][0][0], "9")

    def test_empty(self):
        self.assertEqual(headless.plan([], 4, self.T), [])


class Kept(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "baselines", "timings.json")

    def test_round_trip_merges(self):
        headless.save_timings({("17", "drive", 1): 51}, {"17": 34}, self.path)
        headless.save_timings({("17", "lint", 0): 16}, {}, self.path)
        self.assertEqual(headless.load_timings(self.path),
                         {"runs": {"17|drive|1": 51, "17|lint|0": 16}, "loads": {"17": 34}})
        self.assertEqual(headless.load_timings(os.path.join(self.tmp.name, "absent.json")), {"runs": {}, "loads": {}})

    def test_a_run_keeps_its_times_without_the_load(self):
        out = os.path.join(self.tmp.name, "results")
        calls = []

        def worker(batch, url, headed, timeout, done=None, page_opts=None):
            calls.append(batch)
            res = [(job, {"checks": {}}, 40, 0) for job in batch]
            res[0] = (res[0][0], res[0][1], 70, 30)  # (the first run in the page carried a 30 s load)
            return res

        argv = ["headless.py", "--lines", "23", "--checks", "lint,surfaces", "--jobs", "1", "--url", "http://x",
                "--out", out]
        with patch.object(sys, "argv", argv), patch.object(headless, "TIMINGS", self.path), \
                patch.object(headless, "BASELINE", os.path.join(self.tmp.name, "absent.json")), \
                patch.object(headless, "worker", side_effect=worker), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                headless.main()
        self.assertEqual(calls, [[("23", "lint", 0), ("23", "surfaces", 0)]])
        self.assertEqual(headless.load_timings(self.path),
                         {"runs": {"23|lint|0": 40, "23|surfaces|0": 40}, "loads": {"23": 30}})
        with open(os.path.join(out, "line23-lint.json"), encoding="utf-8") as f:
            o = json.load(f)
        self.assertEqual((o["seconds"], o["load"]), (70, 30))


if __name__ == "__main__":
    unittest.main(verbosity=2)
