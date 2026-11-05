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
