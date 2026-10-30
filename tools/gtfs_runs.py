"""Pair GTFS trips only when their vehicle block proves the continuation."""
from collections import Counter, defaultdict


def seconds(hms):
    h, m, s = map(int, hms.split(':'))
    return h * 3600 + m * 60 + s


def pair_continuations(trips, stop_times, first_ids, next_ids):
    """Return (pairs, rejected arrivals, unused departures).

    All active trips in the first trips' blocks must be supplied, including other routes. A
    selected departure is a continuation only if it is the unique next trip in the block,
    starts at the same stop, and no other trip overlaps the arrival. Never infer a vehicle
    from proximity in time. Values in stop_times are sorted by stop_sequence.
    """
    selected = set(next_ids)
    blocks = defaultdict(list)
    unusable = set()
    for tid, trip in trips.items():
        block = trip.get('block_id', '')
        if not block:
            continue
        rows = stop_times.get(tid, [])
        try:
            if not rows:
                raise ValueError('missing stop times')
            start = seconds(rows[0]['departure_time'])
            end = seconds(rows[-1]['arrival_time'])
            if end < start:
                raise ValueError('trip ends before it starts')
        except (ValueError, KeyError, TypeError):
            unusable.add(block)
            continue
        blocks[block].append((start, end, tid))

    proposals, rejected = [], []
    for a in first_ids:
        block = trips[a].get('block_id', '')
        if not block:
            rejected.append((a, 'missing block_id'))
            continue
        if block in unusable:
            rejected.append((a, 'block has missing or invalid trip times'))
            continue
        rows = stop_times[a]
        arrival = seconds(rows[-1]['arrival_time'])
        others = [entry for entry in blocks[block] if entry[2] != a]
        if any(start < arrival < end for start, end, _ in others):
            rejected.append((a, 'another trip overlaps the arrival in its block'))
            continue
        future = [entry for entry in others if entry[0] >= arrival]
        if not future:
            rejected.append((a, 'no subsequent trip in block'))
            continue
        earliest = min(x[0] for x in future)
        candidates = [x for x in future if x[0] == earliest]
        if len(candidates) != 1:
            rejected.append((a, 'ambiguous simultaneous next trips in block'))
            continue
        start, _, b = candidates[0]
        if b not in selected:
            rejected.append((a, f'next block trip {b} is not on the selected pattern'))
        elif rows[-1]['stop_id'] != stop_times[b][0]['stop_id']:
            rejected.append((a, f'next block trip {b} starts at another stop'))
        else:
            proposals.append((a, b, start - arrival))

    counts = Counter(b for _, b, _ in proposals)
    pairs = []
    for a, b, gap in proposals:
        if counts[b] > 1:
            rejected.append((a, f'next block trip {b} claimed by multiple arrivals'))
        else:
            pairs.append((a, b, gap))
    used = {b for _, b, _ in pairs}
    return pairs, rejected, [b for b in next_ids if b not in used]
