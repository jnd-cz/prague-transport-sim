# SPDX-License-Identifier: AGPL-3.0-or-later
"""Open track from the lidar (tools/open_track.py, #591): python -P -E tools/test_open_track.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import open_track as O  # noqa: E402


class FlatRails:
    """Rails at 200 m along the whole route, from DI."""
    def at(self, x, y, ux, uy):
        return 200.0, "di"


def ground(profile):
    """A lidar whose ground under the route at x is profile(x) (the route runs along y = 0)."""
    import numpy as np
    return lambda xs, ys: np.array([profile(x) for x in xs])


DATA = {"path": [[0.0, 0.0], [600.0, 0.0]]}


class Runs(unittest.TestCase):
    def found(self, profile, data=DATA):
        return O.runs(O.medians(O.gaps(data, FlatRails(), ground(profile))), O.skip_of(data))

    def test_ballast_reads_as_rails_over_the_ground_paved_does_not(self):
        # (the rails 0.16 m over the ground at 100-300 m: ballast; level with it elsewhere: paved)
        rs = self.found(lambda x: 199.84 if 100 <= x <= 300 else 200.0)
        self.assertEqual([(round(r["s0"]), round(r["s1"]), r["sure"]) for r in rs], [(100, 300, True)])
        self.assertAlmostEqual(rs[0]["median"], 0.16, places=2)

    def test_short_runs_go_near_ones_join_and_a_deep_one_is_not_sure(self):
        rs = self.found(lambda x: 199.84 if 100 <= x <= 130 else 199.6 if 300 <= x <= 400 else 200.0)
        # (30 m with a 20 m median: shorter than MIN_RUN; 0.4 m deep: a card, not ballast)
        self.assertEqual([(round(r["s0"]), round(r["s1"]), r["sure"]) for r in rs], [(300, 400, False)])
        rs = self.found(lambda x: 199.84 if 100 <= x <= 200 or 215 <= x <= 300 else 200.0)
        self.assertEqual(len(rs), 1)   # (a 15 m gap: one run)

    def test_bridges_and_tunnels_are_left_out(self):
        data = {**DATA, "bridges": [[150.0, 250.0]]}
        rs = self.found(lambda x: 199.84 if 100 <= x <= 300 else 200.0, data)
        # (10 m past each end left out: 38 m left on either side, shorter than MIN_RUN)
        self.assertEqual(rs, [])


if __name__ == "__main__":
    unittest.main()
