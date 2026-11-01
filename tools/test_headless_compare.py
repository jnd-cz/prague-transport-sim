"""Seed-spread comparison of headless runs (#156): python -P -E tools/test_headless_compare.py"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import headless  # noqa: E402


def base(line, check, per_seed):
    return {f"line{line}-{check}-seed{s}": {"counts": c} for s, c in per_seed.items()}


def row(rows):
    assert len(rows) == 1, rows
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


class Spread(unittest.TestCase):
    def setUp(self):
        self.base = base(22, "traffic", {s: {"walkerHit": w, "slide": 6000, "finished": 1}
                                          for s, w in zip(range(1, 6), (80, 97, 65, 70, 90))})

    def test_same_runs_are_same(self):
        runs = {(22, "traffic", s): dict(v["counts"]) for s, v in zip(range(1, 6), self.base.values())}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual(cells[3:], ["same", "", ""])

    def test_reshuffled_seeds_inside_the_spread_are_noise(self):
        # #151: +54 % on one seed, -33 % on another, the mean inside main's 65-97
        runs = {(22, "traffic", s): {"walkerHit": w, "slide": 6000, "finished": 1}
                for s, w in zip(range(1, 6), (95, 65, 88, 72, 81))}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual(cells[3], "–")
        self.assertEqual(cells[4], "walkerHit")

    def test_a_mean_outside_the_spread_is_marked(self):
        runs = {(22, "traffic", s): {"walkerHit": 120, "slide": 4000, "finished": 1} for s in range(1, 6)}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertIn("walkerHit 80 [65–97] → 120 **worse**", cells[3])
        self.assertIn("slide 6000 → 4000 better", cells[3])

    def test_hard_failures_stay_per_seed(self):
        runs = {(22, "traffic", s): {"walkerHit": 80, "slide": 6000, "finished": int(s != 3)} for s in range(1, 6)}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual(cells[5], "seed 3: finished 1 → 0 **worse**")

    def test_context_counts_are_not_marked(self):
        b = base(17, "u3", {s: {"yielded": y, "stuck": None, "hits": 0} for s, y in zip(range(1, 4), (40, 44, 50))})
        runs = {(17, "u3", s): {"yielded": 70, "stuck": None, "hits": 0} for s in range(1, 4)}
        cells = row(headless.compare_rows(b, runs))
        self.assertEqual(cells[3], "yielded 45 [40–50] → 70")
        b["line17-u3-seed2"]["counts"]["stuck"] = None
        runs[(17, "u3", 2)]["stuck"] = 11969
        self.assertIn("seed 2: stuck None → 11969 **worse**", row(headless.compare_rows(b, runs))[5])

    def test_seedless_checks_show_every_move(self):
        b = {"line17-surfaces": {"counts": {"spikes": 10, "steps": 3}}}
        cells = row(headless.compare_rows(b, {(17, "surfaces", 0): {"spikes": 4, "steps": 3}}))
        self.assertEqual(cells[3], "spikes 10 → 4")

    def test_one_seed_against_the_stored_spread(self):
        runs = {(22, "traffic", 1): {"walkerHit": 96, "slide": 6000, "finished": 1}}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual((cells[2], cells[3], cells[4]), ("1 (main: 5)", "–", "walkerHit"))


if __name__ == "__main__":
    unittest.main(verbosity=1)
