"""Run with python -I tools/test_gtfs_runs.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gtfs_runs import pair_continuations  # noqa: E402


def trip(block, start, end, origin='A', destination='B'):
    return {'block_id': block}, [
        {'departure_time': start, 'arrival_time': start, 'stop_id': origin},
        {'departure_time': end, 'arrival_time': end, 'stop_id': destination},
    ]


class Continuations(unittest.TestCase):
    def pair(self, records, first=('a',), following=('b',)):
        trips, times = {}, {}
        for name, spec in records.items():
            trips[name], times[name] = trip(*spec)
        return pair_continuations(trips, times, first, following)

    def test_immediate_and_after_midnight(self):
        pairs, rejected, unused = self.pair({
            'a': ('block', '23:30:00', '24:10:00'),
            'b': ('block', '24:10:00', '24:40:00', 'B', 'C'),
        })
        self.assertEqual(pairs, [('a', 'b', 0)])
        self.assertEqual((rejected, unused), ([], []))

    def test_layover_is_preserved_and_other_blocks_are_ignored(self):
        pairs, rejected, unused = self.pair({
            'a': ('one', '09:00:00', '09:10:00'),
            'b': ('one', '09:15:00', '09:40:00', 'B', 'C'),
            'c': ('other', '09:10:00', '09:30:00', 'B', 'C'),
        }, following=('b', 'c'))
        self.assertEqual(pairs, [('a', 'b', 300)])
        self.assertEqual(rejected, [])
        self.assertEqual(unused, ['c'])

    def test_missing_block_and_missing_times_do_not_guess(self):
        pairs, rejected, unused = self.pair({
            'a': ('', '09:00:00', '09:10:00'),
            'b': ('', '09:10:00', '09:40:00', 'B', 'C'),
        })
        self.assertEqual((pairs, unused), ([], ['b']))
        self.assertIn('missing block_id', rejected[0][1])
        trips = {'a': {'block_id': 'one'}, 'b': {'block_id': 'one'}}
        times = {'a': trip('one', '09:00:00', '09:10:00')[1], 'b': []}
        self.assertIn('invalid', pair_continuations(trips, times, ['a'], ['b'])[1][0][1])

    def test_intervening_trip_and_simultaneous_departures_are_rejected(self):
        records = {'a': ('one', '09:00:00', '09:10:00'),
                   'b': ('one', '09:20:00', '09:40:00', 'B', 'C'),
                   'c': ('one', '09:10:00', '09:15:00', 'B', 'B')}
        self.assertIn('not on the selected pattern', self.pair(records)[1][0][1])
        records['c'] = ('one', '09:20:00', '09:30:00', 'B', 'C')
        self.assertIn('ambiguous', self.pair(records)[1][0][1])

    def test_overlap_and_wrong_stop_are_rejected(self):
        records = {'a': ('one', '09:00:00', '09:10:00'),
                   'b': ('one', '09:10:00', '09:40:00', 'X', 'C')}
        self.assertIn('another stop', self.pair(records)[1][0][1])
        records['c'] = ('one', '09:05:00', '09:11:00', 'X', 'Y')
        self.assertIn('overlaps', self.pair(records)[1][0][1])

    def test_a_block_can_contain_several_successive_runs(self):
        records = {'a': ('one', '08:00:00', '08:10:00'),
                   'b': ('one', '08:10:00', '08:30:00', 'B', 'A'),
                   'c': ('one', '08:35:00', '08:45:00', 'A', 'B'),
                   'd': ('one', '08:45:00', '09:05:00', 'B', 'C')}
        pairs, rejected, unused = self.pair(records, first=('a', 'c'), following=('b', 'd'))
        self.assertEqual(pairs, [('a', 'b', 0), ('c', 'd', 0)])
        self.assertEqual((rejected, unused), ([], []))

    def test_two_arrivals_cannot_claim_one_departure(self):
        records = {'a': ('one', '09:00:00', '09:10:00'),
                   'c': ('one', '09:00:00', '09:10:00'),
                   'b': ('one', '09:10:00', '09:40:00', 'B', 'C')}
        pairs, rejected, unused = self.pair(records, first=('a', 'c'))
        self.assertEqual(pairs, [])
        self.assertEqual(len(rejected), 2)
        self.assertEqual(unused, ['b'])


if __name__ == '__main__':
    unittest.main()
