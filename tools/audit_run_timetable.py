"""Independently audit a rebuilt two-line timetable against its pinned GTFS and build log.

    python -I tools/audit_run_timetable.py --line 9 --log reports/issue96-pairs.log

Checks emitted rows, logged pairs and omitted eligible pairs, including the full vehicle block,
the stop sequence and the source snapshot's hash. It does not import the builder or its helper.
"""
import argparse
from collections import Counter, defaultdict
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PAIR = re.compile(r'^paired (\S+) (\S+) -> (\S+) (\S+) block (\S+), gap (\d+)s$')


def seconds(value):
    hours, minutes, secs = map(int, value.split(':'))
    return hours * 3600 + minutes * 60 + secs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--line', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('--data', help='built line JSON (defaults to data/lineN.json)')
    parser.add_argument('--date', help='service date (defaults to the one the build log names)')
    args = parser.parse_args()
    data_path = Path(args.data) if args.data else ROOT / 'data' / f'line{args.line}.json'
    data = json.loads(data_path.read_text(encoding='utf-8'))
    segments = data['segments']
    if len(segments) != 2 or segments[0]['from'] != 0:
        raise SystemExit('expected a two-line run starting at the first stop')
    change = segments[1]['from']
    if not 0 < change < len(data['stops']) - 1:
        raise SystemExit('invalid line-change stop index')
    source = ROOT / 'raw' / 'PID_GTFS.zip'
    snapshot_id = (ROOT / 'snapshots' / 'CURRENT').read_text(encoding='utf-8').strip()
    manifest = json.loads((ROOT / 'snapshots' / f'{snapshot_id}.json').read_text(encoding='utf-8'))
    expected = next(f['sha256'] for group in manifest['groups'] for f in group['files'] if f['path'] == 'raw/PID_GTFS.zip')
    with source.open('rb') as f:
        actual = hashlib.file_digest(f, 'sha256').hexdigest()
    if actual != expected:
        raise SystemExit('GTFS does not match the pinned source snapshot')

    pairs, logged_date = [], None
    for line in Path(args.log).read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('service date '):
            logged_date = line.split()[-1]
        elif line.startswith('paired '):
            match = PAIR.fullmatch(line)
            if not match:
                raise SystemExit(f'unrecognised pair log: {line}')
            pairs.append(match.groups())
    if not pairs:
        raise SystemExit('no pairs in build log')
    # The build's own date, not a copy of it here: a new GTFS snapshot moves SERVICE_DATE.
    if not (args.date or logged_date):
        raise SystemExit('the build log names no service date: pass --date')
    if args.date and logged_date and args.date != logged_date:
        raise SystemExit(f'--date {args.date} differs from the build log ({logged_date})')
    date = dt.date.fromisoformat(args.date or logged_date)
    ymd, weekday = date.strftime('%Y%m%d'), date.strftime('%A').lower()
    with zipfile.ZipFile(source) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name), encoding='utf-8-sig', newline=''))
        active = {r['service_id'] for r in rows('calendar.txt')
                  if r['start_date'] <= ymd <= r['end_date'] and r[weekday] == '1'}
        for r in rows('calendar_dates.txt'):
            if r['date'] == ymd:
                (active.add if r['exception_type'] == '1' else active.discard)(r['service_id'])
        trips = {r['trip_id']: r for r in rows('trips.txt') if r['service_id'] in active}
        first_route, second_route = ('L' + segment['line'] for segment in segments)
        blocks = {trip.get('block_id') for trip in trips.values()
                  if trip['route_id'] == first_route and trip.get('block_id')}
        relevant = {tid for tid, trip in trips.items()
                    if trip['route_id'] in (first_route, second_route) or trip.get('block_id') in blocks}
        times = defaultdict(list)
        for row in rows('stop_times.txt'):
            if row['trip_id'] in relevant:
                times[row['trip_id']].append(row)
        names = {r['stop_id']: r['stop_name'] for r in rows('stops.txt')}
    for t in times.values():
        t.sort(key=lambda row: int(row['stop_sequence']))
    block_trips = defaultdict(list)
    for tid in relevant:
        block = trips[tid].get('block_id')
        if block in blocks:
            block_trips[block].append(tid)

    expected_rows = []
    seen_a, seen_b = set(), set()
    for a, arr, b, dep, block, gap in pairs:
        if a in seen_a or b in seen_b:
            raise SystemExit(f'duplicate trip in pair {a} -> {b}')
        seen_a.add(a)
        seen_b.add(b)
        if a not in trips or b not in trips or a not in times or b not in times:
            raise SystemExit(f'pair {a} -> {b} is not active or has no times')
        first, second = trips[a], trips[b]
        if (first.get('block_id') != block or second.get('block_id') != block or
                first['route_id'] != 'L' + segments[0]['line'] or second['route_id'] != 'L' + segments[1]['line']):
            raise SystemExit(f'incorrect route or block: {a} -> {b}')
        aa, bb = times[a], times[b]
        if (aa[-1]['stop_id'] != bb[0]['stop_id'] or aa[-1]['arrival_time'] != arr or
                bb[0]['departure_time'] != dep or seconds(dep) - seconds(arr) != int(gap) or int(gap) < 0):
            raise SystemExit(f'inconsistent terminal or times: {a} -> {b}')
        if ([names[r['stop_id']] for r in aa] + [names[r['stop_id']] for r in bb[1:]] !=
                [st['name'] for st in data['stops']] or len(aa) - 1 != change):
            raise SystemExit(f'stop sequence differs: {a} -> {b}')
        arrival, departure = seconds(arr), seconds(dep)
        for other in block_trips[block]:
            if other in (a, b):
                continue
            if not times[other]:
                raise SystemExit(f'block trip {other} has no stop times')
            start, end = seconds(times[other][0]['departure_time']), seconds(times[other][-1]['arrival_time'])
            if (start < arrival < end) or arrival <= start <= departure:
                raise SystemExit(f'overlapping or intervening block trip {other}: {a} -> {b}')
        expected_rows.append(tuple(seconds(r['departure_time']) for r in aa[:-1] + bb))
    if Counter(expected_rows) != Counter(map(tuple, data['timetable'])):
        raise SystemExit('built timetable does not contain exactly the logged GTFS pairs')
    # Derive the two selected stop patterns independently from a logged pair, then scan all
    # active first-route blocks. This catches a pair omitted from both the log and the output.
    pattern_a = tuple(r['stop_id'] for r in times[pairs[0][0]])
    pattern_b = tuple(r['stop_id'] for r in times[pairs[0][2]])
    first_ids = [tid for tid in relevant if trips[tid]['route_id'] == first_route and
                 tuple(r['stop_id'] for r in times[tid]) == pattern_a]
    second_ids = {tid for tid in relevant if trips[tid]['route_id'] == second_route and
                  tuple(r['stop_id'] for r in times[tid]) == pattern_b}
    candidates = []
    for a in first_ids:
        block = trips[a].get('block_id')
        group = block_trips.get(block, [])
        if not block or any(not times[tid] for tid in group):
            continue
        try:
            spans = [(seconds(times[tid][0]['departure_time']), seconds(times[tid][-1]['arrival_time']), tid)
                     for tid in group]
            if any(end < start for start, end, _ in spans):
                continue
            arrival = seconds(times[a][-1]['arrival_time'])
        except (ValueError, KeyError, TypeError):
            continue
        others = [(start, end, tid) for start, end, tid in spans if tid != a]
        if any(start < arrival < end for start, end, _ in others):
            continue
        starts = sorted((start, tid) for start, _, tid in others if start >= arrival)
        if not starts or (len(starts) > 1 and starts[0][0] == starts[1][0]):
            continue
        b = starts[0][1]
        if b in second_ids and times[a][-1]['stop_id'] == times[b][0]['stop_id']:
            candidates.append((a, b))
    claims = Counter(b for _, b in candidates)
    eligible = {(a, b) for a, b in candidates if claims[b] == 1}
    emitted = {(a, b) for a, _, b, _, _, _ in pairs}
    if eligible != emitted:
        raise SystemExit(f'eligible GTFS pairs differ: omitted {sorted(eligible - emitted)}, unexpected {sorted(emitted - eligible)}')
    gaps = Counter(int(pair[-1]) for pair in pairs)
    print(f'{len(pairs)} pairs verified against {snapshot_id} GTFS for {date}; gaps in seconds: {dict(sorted(gaps.items()))}')


if __name__ == '__main__':
    main()
