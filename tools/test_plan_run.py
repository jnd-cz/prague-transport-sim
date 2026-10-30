"""Test the complete GTFS run planner with a small feed: python -I tools/test_plan_run.py."""
import contextlib
import csv
import datetime
import io
import os
import sys
import tempfile
import types
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The planner does not use geometry or OSM. Avoid making it depend on their packages and data.
with patch.object(sys, 'argv', ['build_line.py', '--line', '9', '--then', '10']), \
        patch.dict(sys.modules, {'geo': types.SimpleNamespace(Frame=object), 'osm_local': types.ModuleType('osm_local')}), \
        patch('os.makedirs'):
    import build_line  # noqa: E402


def csv_text(fields, rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class PlanRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        archive = os.path.join(self.tmp.name, 'feed.zip')
        # a2's block contains an intervening trip on another route; a3 has no block.
        specs = [
            ('a1', 'L9', 'one', '08:00:00', '08:10:00', 'A', 'B'),
            ('a2', 'L9', 'two', '09:00:00', '09:10:00', 'A', 'B'),
            ('a3', 'L9', '', '10:00:00', '10:10:00', 'A', 'B'),
            ('b1', 'L10', 'one', '08:10:00', '08:25:00', 'B', 'C'),
            ('b2', 'L10', 'two', '09:15:00', '09:30:00', 'B', 'C'),
            ('b3', 'L10', 'three', '10:10:00', '10:25:00', 'B', 'C'),
            ('x', 'L99', 'two', '09:10:00', '09:14:00', 'B', 'B'),
            ('inactive', 'L99', 'one', '08:10:00', '08:14:00', 'B', 'B'),
        ]
        trips, times = [], []
        for tid, route, block, start, end, origin, destination in specs:
            trips.append({'trip_id': tid, 'route_id': route, 'service_id': 'off' if tid == 'inactive' else 'on',
                          'block_id': block, 'shape_id': route + 'shape'})
            for seq, stop, t in [(1, origin, start), (2, destination, end)]:
                times.append({'trip_id': tid, 'stop_id': stop, 'stop_sequence': seq, 'arrival_time': t,
                              'departure_time': t, 'pickup_type': '0', 'drop_off_type': '0'})
        files = {
            'calendar.txt': (['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'start_date', 'end_date'],
                             [dict(service_id=s, monday='1', tuesday='1', wednesday='1', thursday='1', friday='1',
                                   saturday='1', sunday='1', start_date='20261001', end_date='20261031') for s in ('on', 'off')]),
            'calendar_dates.txt': (['service_id', 'date', 'exception_type'],
                                   [{'service_id': 'off', 'date': '20261021', 'exception_type': '2'}]),
            'trips.txt': (['trip_id', 'route_id', 'service_id', 'block_id', 'shape_id'], trips),
            'stop_times.txt': (['trip_id', 'stop_id', 'stop_sequence', 'arrival_time', 'departure_time', 'pickup_type', 'drop_off_type'], times),
            'stops.txt': (['stop_id', 'stop_name'], [{'stop_id': x, 'stop_name': x} for x in ('A', 'B', 'C')]),
        }
        with zipfile.ZipFile(archive, 'w') as z:
            for name, (fields, rows) in files.items():
                z.writestr(name, csv_text(fields, rows))
        self.feed = patch.object(build_line, 'GTFS_ZIP', archive)
        self.date = patch.object(build_line, 'SERVICE_DATE', datetime.date(2026, 10, 21))
        self.feed.start()
        self.date.start()
        self.addCleanup(self.feed.stop)
        self.addCleanup(self.date.stop)

    def test_planner_preserves_only_verified_connection(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = build_line.plan_run('9', '10')
        self.assertEqual(result['stops'], ['A', 'B', 'C'])
        self.assertEqual(result['change'], 1)
        self.assertEqual(result['timetable'], [[28800, 29400, 30300]])
        self.assertEqual(result['shapes'], ['L9shape', 'L10shape'])
        self.assertIn('paired a1 08:10:00 -> b1 08:10:00 block one, gap 0s', output.getvalue())
        self.assertIn('unmatched arrival a2 09:10:00: next block trip x', output.getvalue())
        self.assertIn('unmatched arrival a3 10:10:00: missing block_id', output.getvalue())
        self.assertIn('unmatched departure b2 09:15:00', output.getvalue())
        self.assertIn('unmatched departure b3 10:10:00', output.getvalue())

    def test_planner_fails_closed_when_no_block_proves_a_pair(self):
        # An intervening trip also invalidates the only otherwise valid block.
        original_open = build_line.gtfs_open
        def feed():
            rd, active = original_open()
            def with_intervening(name):
                rows = list(rd(name))
                if name == 'trips.txt':
                    rows.append({'trip_id': 'y', 'route_id': 'L99', 'service_id': 'on',
                                 'block_id': 'one', 'shape_id': 'L99shape'})
                elif name == 'stop_times.txt':
                    rows.extend([{'trip_id': 'y', 'stop_id': 'B', 'stop_sequence': '1',
                                  'arrival_time': '08:10:00', 'departure_time': '08:10:00',
                                  'pickup_type': '0', 'drop_off_type': '0'},
                                 {'trip_id': 'y', 'stop_id': 'B', 'stop_sequence': '2',
                                  'arrival_time': '08:11:00', 'departure_time': '08:11:00',
                                  'pickup_type': '0', 'drop_off_type': '0'}])
                return iter(rows)
            return with_intervening, active
        with patch.object(build_line, 'gtfs_open', feed), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(SystemExit, 'no verified 9->10 continuations'):
                build_line.plan_run('9', '10')


if __name__ == '__main__':
    unittest.main()
