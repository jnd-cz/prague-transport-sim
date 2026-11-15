# SPDX-License-Identifier: AGPL-3.0-or-later
"""DI's records as chains, their forks (#20, #237): python -P -E tools/test_di_tracks.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_tracks as dt


def rec(i, pts):
    return {'id': str(i), 'coords': [(x, y, None) for x, y in pts], 'attrs': {}, 'sources': []}


def turnout(x0, side=1, n=12):
    """A branch leaving the x axis at x0 on a 50 m radius to the left (side 1) or right (-1), 20 m long."""
    return [(x0 + 50 * math.sin(k / n * 0.4), side * 50 * (1 - math.cos(k / n * 0.4))) for k in range(n + 1)]


class Records(unittest.TestCase):
    def test_a_branch_ending_on_the_middle_of_a_track_is_a_fork(self):
        # Palackého náměstí: DI does not split the through record; the branch ends 19.8 m along it
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, turnout(50))])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (50, 0)), 1e-6)

    def test_an_interlaced_branch_forks_where_it_starts_beside_the_track(self):
        # Čechův most: DI draws the branch 13 cm off the through track for 21 m from a record joint, then it leaves;
        # the switch is a tongue before it ("the fork starts and ends well in front of/behind the road junction")
        branch = [(29, 0.13), (50, 0.13)] + [(x, y + 0.13) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (29, 0)]), rec(2, [(29, 0), (120, 0)]), rec(3, branch)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (29 - dt.TONGUE, 0)), 0.01)
        self.assertEqual(di.interlaced[0]['side'], 1)
        # Ohrada: the branch leaves the through track's middle, 12 cm off after 9 m, and runs on beside it
        ramp = [(20 + k, 0.012 * k) for k in range(10)] + [(50, 0.12)] + [(x, y + 0.12) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, ramp)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(math.dist(di.forks[0], (20, 0)), 0.01)

    def test_an_interlaced_branch_beside_a_joint_leaves_the_track_whole(self):
        # Ke Stírce: the branch starts 11.7 cm beside the through track's record joint; met there, the node lay on the
        # branch and line 17 stepped 12 cm through it. The user, 2026-11-07: "intarlaced switch here, same case as
        # Čechův most"
        branch = [(50, 0.117), (90, 0.117)] + [(x, y + 0.117) for x, y in turnout(90)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50, 0), (200, 0)]), rec(3, branch)])
        ids = lambda c: [r['id'] for r in c['records']]
        through = [c for c in di.chains if '1' in ids(c)]
        self.assertEqual(len(through), 1)
        self.assertEqual(ids(through[0]), ['1', '2'])
        self.assertLess(math.dist(di.forks[0], (50 - dt.TONGUE, 0)), 0.01)
        # Čechův most: the through track's joint 0.6 m apart, the branch ending 12 cm beside it with a scrap on
        b_in = [(0, 3.0), (20, 0.12), (49.4, 0.12)]
        di = dt.Source('di', [rec(1, [(-50, 0), (49.4, 0)]), rec(2, [(50, 0), (150, 0)]), rec(3, b_in),
                              rec(4, [(49.4, 0.12), (50, 0.11)])])
        through = next(c for c in di.chains if '1' in ids(c))
        self.assertEqual(ids(through), ['1', '2'])
        self.assertAlmostEqual(through['line'].length, 200, delta=0.01)

    def test_two_interlaced_tracks_split_at_the_same_places_stay_two(self):
        # Nádraží Libeň: both tracks split every 6-27 m, their joints 10.7 cm apart; met there, the through track's
        # records were dropped as copies of the branch's and line 37 ran the branch. The user, 2026-11-07: "there should
        # be two tracks running with a small shift that corresponds to the current jolts"
        cuts = [0, 6, 33, 39]
        a = [rec(10 + k, [(cuts[k], 0), (cuts[k + 1], 0)]) for k in range(3)]
        b = [rec(20 + k, [(cuts[k], 0.107), (cuts[k + 1], 0.107)]) for k in range(3)]
        # (where they part, both joints side by side: the branch goes on from its own, not from the through track's)
        part = [(39 + x, 0.107 + y) for x, y in turnout(0, n=20)]
        di = dt.Source('di', [rec(1, [(-60, 0), (0, 0)]), rec(2, [(39, 0), (150, 0)]), *a, *b, rec(4, part),
                              rec(3, [(-60, 3.4), (150, 3.4)])])
        self.assertEqual(di.duplicates, 0)
        ids = lambda c: [r['id'] for r in c['records']]
        self.assertTrue(any(ids(c) in (['20', '21', '22', '4'], ['4', '22', '21', '20']) for c in di.chains))
        self.assertTrue(any(ids(c) in (['1', '10', '11', '12', '2'], ['2', '12', '11', '10', '1']) for c in di.chains))

    def test_a_switch_drawn_as_a_section_forks_at_its_tip(self):
        # Dvorecký most (DI 2026-10-07): both legs drawn as 4.7 m records from the tip, where OSM's switch and the
        # switch machine cover are, to a joint where the track and the branch go on
        leg = [(50 + d, 0.0113 * d * d) for d in (0, 1, 2, 3, 4, 4.7)]   # (25 cm off at the joint)
        branch = [leg[-1]] + [(x, y) for x, y in turnout(50)[1:] if x > 54.7]
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50, 0), (54.7, 0)]), rec(3, leg),
                              rec(4, [(54.7, 0), (120, 0)]), rec(5, branch)])
        self.assertEqual(di.sections, 1)
        self.assertLess(min(math.dist(f, (50, 0)) for f in di.forks), 0.01)

    def test_a_copy_running_on_the_track_forks_where_it_leaves(self):
        # Vozovna Kobylisy: two records 1-3 cm apart for 15 m, then they part
        branch = [(30, 0.02), (50, 0.02)] + [(x, y + 0.02) for x, y in turnout(50)[1:]]
        di = dt.Source('di', [rec(1, [(0, 0), (120, 0)]), rec(2, branch)])
        self.assertEqual(len(di.forks), 1)
        self.assertLess(abs(di.forks[0][0] - 50), 2.0)

    def test_record_ends_within_join_continue_each_other(self):
        di = dt.Source('di', [rec(1, [(0, 0), (50, 0)]), rec(2, [(50.3, 0), (100, 0)])])
        self.assertEqual(len(di.chains), 1)
        self.assertEqual(di.chains[0]['line'].length > 99, True)

    def test_two_records_leaving_one_point_the_same_way_are_not_one_chain(self):
        # Hloubětín: merged, the track went 130 m out along one and back along the other, a 176° fold
        di = dt.Source('di', [rec(1, [(0, 0), (60, 0.5)]), rec(2, [(0, 0), (60, -0.5)])])
        self.assertEqual(len(di.chains), 2)

    def test_one_record_turning_back_on_itself_is_two(self):
        di = dt.Source('di', [rec(1, [(0, 60), (0.5, 30), (1, 0), (2, 30), (3, 60)])])
        self.assertEqual(len(di.chains), 2)

    def test_an_older_record_lying_on_newer_ones_is_dropped_but_interlaced_track_stays(self):
        def dated(i, pts, day):
            return rec(i, pts) | {'attrs': {'DatumVkladu': day}}
        old = dated(1, [(0, 0), (100, 0)], '2025-01-30')               # re-entered later in two pieces, 6 cm off
        new = [dated(2, [(0, 0.06), (60, 0.06)], '2026-10-07'), dated(3, [(60, 0.06), (100, 0.06)], '2026-10-07')]
        partner = dated(4, [(20, 0.19), (50, 0.19), (60, 3)], '2025-01-30')   # interlaced, 13 cm beside the newer
        di = dt.Source('di', [old, *new, partner])
        self.assertEqual(di.superseded, 1)
        self.assertEqual(sorted(r['id'] for c in di.chains for r in c['records']), ['2', '3', '4'])


if __name__ == '__main__':
    unittest.main()
