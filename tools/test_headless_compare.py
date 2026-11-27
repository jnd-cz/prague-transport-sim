# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed-spread comparison of headless runs (#156): python -P -E tools/test_headless_compare.py"""
from contextlib import redirect_stdout
import io
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

    def test_a_jammed_run_is_reported_per_seed_and_left_out_of_the_spread(self):
        runs = {(22, "traffic", s): {"walkerHit": 80, "slide": 6000, "finished": 1} for s in range(1, 6)}
        runs[(22, "traffic", 4)] = {"walkerHit": 400, "slide": 90000, "finished": 0}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual(cells[3:], ["–", "walkerHit", "seed 4: finished 1 → 0 **worse**"])

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

    def test_a_count_kept_apart_is_not_marked_worse(self):
        b = {"line9-surfaces": {"counts": {"seams10": 800, "bedKerbs": 400, "loweredKerbs": 1300}}}
        cells = row(headless.compare_rows(b, {(9, "surfaces", 0): {"seams10": 810, "bedKerbs": 620, "loweredKerbs": 1310}}))
        self.assertEqual(cells[3], "bedKerbs 400 → 620; loweredKerbs 1300 → 1310; seams10 800 → 810 **worse**")

    def test_one_seed_against_the_stored_spread(self):
        runs = {(22, "traffic", 1): {"walkerHit": 96, "slide": 6000, "finished": 1}}
        cells = row(headless.compare_rows(self.base, runs))
        self.assertEqual((cells[2], cells[3], cells[4]), ("1 (main: 5)", "–", "walkerHit"))


class FakeStore:
    """What choose_baseline asks of tools/baseline_store.py (#282)."""
    latest_checkpoint = staticmethod(lambda index: max(index, default=None))

    def __init__(self, nightly=None, here=None, measured=None, checkpoint=None):
        self.nightly, self.here, self.measured, self.checkpoint = nightly, here or {}, measured, checkpoint
        self.asked, self.kept_now = [], None

    def key(self, want):
        return "k"

    def fetch(self, k):
        return (self.nightly, {}) if self.nightly else (None, None)

    def kept(self, k):
        return self.here, {}

    def keep(self, k, counts, places):
        self.kept_now = counts

    def measure_at(self, rev, lines, checks, want, seeds=None):
        self.asked.append((lines, checks, seeds) if seeds else (lines, checks))
        return self.measured or {}, {}

    def checkpoints(self):
        return {"W1": {}} if self.checkpoint else {}

    def fetch_checkpoint(self, name):
        return self.checkpoint, {}


class ChooseBaseline(unittest.TestCase):
    NOW, OLD = {"src": "now"}, {"src": "old"}

    def entry(self, on, n=1):
        return {"counts": {"n": n}, "measured_on": on, "commit": "c"}

    def choose(self, stored, results, store, measure=True):
        return headless.choose_baseline(stored, {}, results, "abcdef0", self.NOW, measure, store)

    def test_an_exact_committed_baseline_asks_nothing_else(self):
        s = FakeStore()
        base, _, stale = self.choose({"line9-lint": self.entry(self.NOW)}, {("9", "lint", 0): {}}, s)
        self.assertEqual((s.asked, stale), ([], []))
        self.assertEqual(base["line9-lint"]["measured_on"], self.NOW)

    def test_the_nightly_of_the_merge_base_comes_first(self):
        s = FakeStore(nightly={"line9-lint": self.entry(self.NOW, 7)})
        base, _, stale = self.choose({"line9-lint": self.entry(self.OLD)}, {("9", "lint", 0): {}}, s)
        self.assertEqual((base["line9-lint"]["counts"], s.asked, stale), ({"n": 7}, [], []))

    def test_a_seedless_run_without_one_is_measured_once_and_kept(self):
        s = FakeStore(measured={"line9-lint": self.entry(self.NOW, 5)})
        base, _, stale = self.choose({"line9-lint": self.entry(self.OLD)}, {("9", "lint", 0): {}}, s)
        self.assertEqual(s.asked, [(["9"], ["lint"])])
        self.assertEqual(base["line9-lint"]["counts"], {"n": 5})
        self.assertEqual(s.kept_now, {"line9-lint": self.entry(self.NOW, 5)})
        self.assertEqual(stale, [])

    def test_a_seeded_run_without_one_is_measured_at_the_merge_base_with_its_seeds(self):
        """#709: main's own runs of the seeds asked, not a checkpoint's (#582)."""
        measured = {f"line9-{c}-seed{s}": self.entry(self.NOW, 10 * s) for c in ("u3", "stops") for s in (1, 2)}
        s = FakeStore(measured=measured, checkpoint={"line9-u3-seed1": self.entry(self.OLD, 3)})
        results = {("9", c, k): {} for c in ("u3", "stops") for k in (1, 2)}
        base, _, stale = self.choose({"line9-u3-seed1": self.entry(self.OLD, 9)}, results, s)
        self.assertEqual(s.asked, [(["9"], ["stops", "u3"], [1, 2])])
        self.assertEqual([base[f"line9-u3-seed{k}"]["counts"] for k in (1, 2)], [{"n": 10}, {"n": 20}])
        self.assertEqual((s.kept_now, stale), (measured, []))

    def test_seeded_runs_this_machine_kept_are_not_measured_again(self):
        s = FakeStore(here={"line9-u3-seed1": self.entry(self.NOW, 5)})
        base, _, _ = self.choose({}, {("9", "u3", 1): {}}, s)
        self.assertEqual((base["line9-u3-seed1"]["counts"], s.asked), ({"n": 5}, []))

    def test_what_this_machine_kept_is_reused(self):
        s = FakeStore(here={"line9-lint": self.entry(self.NOW, 5)})
        base, _, _ = self.choose({}, {("9", "lint", 0): {}}, s)
        self.assertEqual((base["line9-lint"]["counts"], s.asked), ({"n": 5}, []))

    def test_no_measuring_when_told_not_to(self):
        s = FakeStore()
        _, _, stale = self.choose({"line9-lint": self.entry(self.OLD)}, {("9", "lint", 0): {}}, s, measure=False)
        self.assertEqual((s.asked, stale), ([], ["line9-lint"]))

    def test_without_measuring_a_seeded_run_takes_the_latest_checkpoint(self):
        s = FakeStore(checkpoint={"line9-u3-seed1": self.entry(self.OLD, 3)})
        out = io.StringIO()
        with redirect_stdout(out):
            base, _, stale = self.choose({"line9-u3-seed1": self.entry(self.OLD, 9)}, {("9", "u3", 1): {}}, s, measure=False)
        self.assertEqual((base["line9-u3-seed1"]["counts"], s.asked), ({"n": 3}, []))
        self.assertEqual(stale, [])  # (said by the note, not as a stale baseline)
        self.assertIn("not with main", out.getvalue())

    def test_a_measurement_that_gives_nothing_falls_back_to_the_checkpoint(self):
        s = FakeStore(measured={}, checkpoint={"line9-u3-seed1": self.entry(self.OLD, 3)})
        base, _, _ = self.choose({}, {("9", "u3", 1): {}}, s)
        self.assertEqual((base["line9-u3-seed1"]["counts"], s.asked), ({"n": 3}, [(["9"], ["u3"], [1])]))

    def test_no_checkpoint_and_no_measuring_leaves_a_seeded_run_stale(self):
        _, _, stale = self.choose({"line9-u3-seed1": self.entry(self.OLD)}, {("9", "u3", 1): {}}, FakeStore(), measure=False)
        self.assertEqual(stale, ["line9-u3-seed1"])


class Places(unittest.TestCase):
    def test_new_and_gone_places_across_seeds(self):
        stored = {"line22-traffic-seed1": {"walkerHit": [[0, 0, 10], [100, 100, 50]]},
                  "line22-traffic-seed2": {"walkerHit": [[5, 5, 12]]}}
        found = {(22, "traffic", 1): {"walkerHit": [[2, 2, 11], [500, 500, 300]]},
                 (22, "traffic", 2): {"walkerHit": [[501, 499, 301]]}}
        cells = row(headless.place_rows(stored, found))
        self.assertEqual(cells, ["22", "traffic", "walkerHit", "1: 500,500 (s 300) ×2", "1: 1 once"])

    def test_bench_places_match_by_route_position(self):
        stored = {"line17-u3-seed1": {"closeCuts": [[None, None, 14249]]}}
        found = {(17, "u3", 1): {"closeCuts": [[None, None, 14260], [None, None, 20525]]}}
        self.assertEqual(row(headless.place_rows(stored, found))[3:], ["1: 1 once", "0"])

    def test_same_places_give_no_row(self):
        stored = {"line17-lint": {"railSupport": [[1, 2, 3]]}}
        self.assertEqual(headless.place_rows(stored, {(17, "lint", 0): {"railSupport": [[1, 2, 3]]}}), [])


class Player(unittest.TestCase):
    """--player (#710): the checks' world beside a player's, run by run."""
    U3 = {"stuck": None, "hits": 0, "signalPenalty": 0, "yielded": 4, "closeCuts": 1,
          "carsIntoJunctions": {"red": 0, "green": 30, "amber": 2}}

    def table(self, streamed):
        kept = {("17", "u3", 1): headless.counts("u3", self.U3)}
        rows, bad = headless.player_rows(kept, {("17", "u3", 1): streamed})
        return [c.strip() for c in rows[2].strip("|").split("|")], bad

    FAR = {"reads": 0, "tiles": 0, "at": [], "held": 40, "of": 300, "streamed": True}

    def test_the_same_counts_pass(self):
        cells, bad = self.table(dict(self.U3, farGround=self.FAR))
        self.assertEqual((cells[3], cells[4], cells[5], cells[6], bad), ("same", "40 of 300", "none", "same", 0))

    def test_a_move_with_grid_reads_has_its_reason(self):
        far = dict(self.FAR, reads=120, tiles=2, at=[[10, 20]])
        cells, bad = self.table(dict(self.U3, yielded=5, farGround=far))
        self.assertEqual((cells[3], cells[5], cells[6], bad),
                         ("yielded 4 → 5", "120 reads on 2 tiles, first at [10, 20]", "moved: heights from the grid", 0))

    def test_a_move_without_a_grid_read_fails(self):
        cells, bad = self.table(dict(self.U3, hits=1))
        self.assertEqual((cells[3], cells[6], bad), ("hits 0 → 1", "moved without a grid read: FAIL", 1))

    def test_a_page_that_held_every_tile_proves_nothing(self):
        cells, bad = self.table(dict(self.U3, farGround=dict(self.FAR, held=300, streamed=False)))
        self.assertEqual((cells[4], cells[6], bad), ("300 of 300", "the page held every tile (not streamed): FAIL", 1))


if __name__ == "__main__":
    unittest.main(verbosity=1)
