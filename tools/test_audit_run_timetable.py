"""Run with python -I tools/test_audit_run_timetable.py; all inputs are temporary fixtures."""
import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_run_timetable as audit  # noqa: E402
from atomic import replacing  # noqa: E402
import test_plan_run as fixture  # noqa: E402


class AuditRun(unittest.TestCase):
    def setUp(self):
        fixture.PlanRun.setUp(self)
        self.root = Path(self.tmp.name) / 'checkout'
        for folder in ('raw', 'data', 'snapshots'):
            (self.root / folder).mkdir(parents=True)
        self.archive = self.root / 'raw' / 'PID_GTFS.zip'
        # Two verified pairs make it possible to omit one pair from both outputs while leaving
        # a plausible nonempty log and timetable.
        with zipfile.ZipFile(fixture.build_line.GTFS_ZIP) as src, replacing(self.archive, 'wb') as out:
            with zipfile.ZipFile(out, 'w') as dst:
                for name in src.namelist():
                    content = src.read(name).decode('utf-8-sig')
                    if name in ('trips.txt', 'stop_times.txt'):
                        reader = csv.DictReader(io.StringIO(content))
                        rows = list(reader)
                        if name == 'trips.txt':
                            rows.extend([{'trip_id': tid, 'route_id': route, 'service_id': 'on',
                                          'block_id': 'four', 'shape_id': route + 'shape'}
                                         for tid, route in [('a4', 'L9'), ('b4', 'L10')]])
                        else:
                            for tid, stops in [('a4', [('A', '11:00:00'), ('B', '11:10:00')]),
                                               ('b4', [('B', '11:10:00'), ('C', '11:25:00')])]:
                                rows.extend({'trip_id': tid, 'stop_id': stop, 'stop_sequence': i,
                                             'arrival_time': t, 'departure_time': t,
                                             'pickup_type': '0', 'drop_off_type': '0'}
                                            for i, (stop, t) in enumerate(stops, 1))
                        content = fixture.csv_text(reader.fieldnames, rows)
                    dst.writestr(name, content)
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        (self.root / 'snapshots' / 'CURRENT').write_text('test', encoding='utf-8')
        (self.root / 'snapshots' / 'test.json').write_text(json.dumps({'groups': [{'files': [
            {'path': 'raw/PID_GTFS.zip', 'sha256': digest}]}]}), encoding='utf-8')
        self.line = {'segments': [{'line': '9', 'from': 0}, {'line': '10', 'from': 1}],
                     'stops': [{'name': n} for n in ('A', 'B', 'C')],
                     'timetable': [[28800, 29400, 30300], [39600, 40200, 41100]]}
        self.log = ['paired a1 08:10:00 -> b1 08:10:00 block one, gap 0s',
                    'paired a4 11:10:00 -> b4 11:10:00 block four, gap 0s']
        self.date = 'service date 2026-10-21'
        self.write_fixture()

    def write_fixture(self):
        with replacing(self.root / 'data' / 'line9.json', 'w', encoding='utf-8') as f:
            json.dump(self.line, f)
        (self.root / 'log.txt').write_text('\n'.join(([self.date] if self.date else []) + self.log), encoding='utf-8')

    def run_audit(self):
        with patch.object(audit, 'ROOT', self.root), \
                patch.object(sys, 'argv', ['audit_run_timetable.py', '--line', '9', '--log', str(self.root / 'log.txt')]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            audit.main()
        return output.getvalue()

    def test_valid_pairs_and_calendar_exceptions(self):
        self.assertIn('2 pairs verified', self.run_audit())

    def test_pair_omitted_from_both_outputs_is_detected(self):
        self.line['timetable'].pop(0)
        self.log.pop(0)
        self.write_fixture()
        with self.assertRaisesRegex(SystemExit, "omitted .*a1.*b1"):
            self.run_audit()

    def test_service_date_comes_from_the_build_log(self):
        self.date = None
        self.write_fixture()
        with self.assertRaisesRegex(SystemExit, 'names no service date'):
            self.run_audit()

    def test_wrong_source_hash_is_rejected(self):
        (self.root / 'snapshots' / 'test.json').write_text(json.dumps({'groups': [{'files': [
            {'path': 'raw/PID_GTFS.zip', 'sha256': 'wrong'}]}]}), encoding='utf-8')
        with self.assertRaisesRegex(SystemExit, 'does not match the pinned source'):
            self.run_audit()


if __name__ == '__main__':
    unittest.main()
