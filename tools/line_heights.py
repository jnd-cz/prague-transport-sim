"""Top-of-rail heights for the game (#197): one vertical profile per track of the network, written into the lines.

    python -P -E tools/line_heights.py 17 22       # stage the heights, assemble, write data/line17.json, line22.json
    python -P -E tools/line_heights.py 17 --staged reports/track-heights.json   # reuse an import of this checkout

The staged heights (tools/import_track_heights.py: numeric DI, the archive, the user's reviewed spans from
data/truth.json, survey plus the style fact) are binned every 5 m along each chain of DI paths
(tools/track_profile.py `chains`: through a fork the straightest pair continues; copies are dropped as in
tools/di_tracks.py) and smoothed once with `vertical_profile` at each point's design radius: 500 m on paved
street and where the construction is unknown, 1000 m on open track, in a turnout and across a diamond crossing
(docs/decisions/2026-11-02-vertical-profile.md). A held stretch up to 60 m is bridged by the curve; a longer one
cuts the profile and is listed. The chains are solved longest first; where a track meets one already solved (a
junction, tracks that cross at grade) it is pinned to that track's height, so no junction has two heights.

A line's path, opposite path and drawn tracks take the heights of the chains they lie on every 2 m (`heights`,
`heightSource`, a track's `zs`; `backOff` / `backZ` the opposite track beside the path); where none does (OSM or archive fill, a long hold) the value is null and the
game keeps its surface-plus-style profile there (src/terrain.js Profile).
"""
import argparse
import bisect
from collections import Counter, defaultdict
import json
import math
import time
from pathlib import Path
import sys

import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_profile import BIN, HELD_GAP, ROOT, STEP as MISS, STRUCTURE, BIG, banded_profile, cause, chains, implied_radii, radii, vertical_profile  # noqa: E402

OUT_STEP = 2.0  # m between heights along a line's path and tracks (the game's profile step, src/terrain.js)
MATCH = 1.0     # m from a line's point to the chain it lies on (both are DI where the line is, #20)
ANGLE = 30      # degrees between them
JOIN = 0.5      # m: a chain's end this near another chain meets it
SWITCH, BEHIND, DIAMOND = 15.0, 3.0, 5.0  # m: the switch radius from a fork into the turnout (and this far behind it)
                                          # on both tracks, and either side of a crossing (a 20 m zone around every pin
                                          # held a 430 m sag at Nádraží Holešovice to 1000 m, the curve 3 m under it)
NEAR_PIN = 1.5  # m: a bin this near a pinned point gives way to it
BAND = 0.10     # m: the curve stays within this of the staged heights (the user, 2026-11-03: "If the curve >=500m fits
                # within 10cm then it's solved, otherwise let's keep it for review again so we can find the root cause")
JUNCTION_BAND = 0.15  # m within a turnout or a diamond: the play the user allowed there for input errors and noise
                      # ("there can be little play within the junction if we account for input data errors, noise")
FIT, PIN_FIT = 0.01, 0.002  # m outside the band that still fits (the solver's convergence); at a pin, where rails join
PIN_TOL = 0.005  # m: a junction's pinned height, within this
LONE = 2        # bins: a group of misses this small is a lone bad point, not held to the band
RELAX_STEP, RELAX_STEPS, RELAX_REACH = 0.8, 12, 50.0  # where the band is missed: the radius x0.8 within 50 m, at most
MIN_RADIUS = 20.0  # m: 12 times, never under the tightest horizontal radius (data/truth.json min-radius-passenger)
NEAR_MEET = 2.0  # m: two tracks meeting a third this near each other along it meet each other too (Ke Stírce: two
                 # track ends 0.65 m apart on a third track, 9 cm apart in height, pinned it to both)
MAX_GRADE = 0.09  # the steepest tram track (the game's grade limiter, src/terrain.js; Hercovka - Kobylisy 8-8.8 %)
HOLD_WEIGHT = 1e-3  # a held bin's pull towards the straight line across its hold
PIN_MERGE = 0.5  # m: pinned points this near each other along a track are one (their mean)
PIN_WEIGHT = 1e3  # a pinned point's weight against a staged height's 1 (1e6 left the solver short of the radius
                  # after 3000 steps on 30 chains, up to 55 s each)
CROSS = 1.0     # m: tracks crossing within this height of each other cross at grade (else one passes over)
END_FADE = 10.0  # m over which a track's end taking the height of the track it joins fades out
ACROSS_MIN, ACROSS_MAX = 2.0, 6.0  # m: the opposite track beside ours (the game's corridor is 6 m, src/terrain.js)
EXTEND = BIN    # m: a chain's height reaches this far past its first and last bin (its ends, junctions)
CODE = {'di': 'di', 'archive': 'dtmp', 'reviewed': 'review', 'deck': 'zps', 'survey': 'zps'}  # staged dataset -> code
LEVELS = ('di', 'dtmp', 'review', 'zps', 'curve', 'surface')  # codes in the order of sources.LAYERS['heights']


RADIUS_ANSWERS = []  # the user's answers on the radius review: [{'xy': city frame, 'answer': ...}] (data/truth.json)
HOLD, FOLLOW = 'hold the radius', 'follow the data'
ANSWER_REACH = 15.0  # m: an answer applies to the place where the radius would give way this near it
DROP_MAX = 12     # rounds: where an answer holds the radius and discards the outliers, one point dropped per round


def load_radius_answers(truth):
    """data/truth.json trackHeights.radiusAnswers: a place (lat, lon) and the user's choice there."""
    from geo import Frame
    F = Frame()
    return [{'xy': tuple(float(v) for v in F.xy(*a['place'])), 'answer': a['answer'], 'outliers': a.get('outliers')}
            for a in (truth.get('trackHeights') or {}).get('radiusAnswers', [])]


def answer_at(xys, kinds=(HOLD,)):
    """The user's answer (of `kinds`) at a place: the nearest within ANSWER_REACH of any of its points, else None."""
    near = [(math.dist(a['xy'], xy), k, a) for k, a in enumerate(RADIUS_ANSWERS) if a['answer'] in kinds
            for xy in xys if xy is not None]
    near = [x for x in near if x[0] <= ANSWER_REACH]
    return min(near)[2] if near else None


def review_place(c, kind, s0, s1, held, final, factor):
    """A place where the radius gave way (or an answer held it): the stretch, the curve held to the design radius,
    the final one and the staged heights, for the radius review (reports/review/track-radius.json)."""
    terrain = {round(b['s'], 1): b['terrain'] for b in c.bins}
    curve = lambda runs: [(si, zi) for run in runs for si, zi in zip(run['s'], run['z']) if s0 <= si <= s1]
    data = [(si, raw, src) for run in final for si, raw, src in zip(run['s'], run['raw'], run['src']) if s0 <= si <= s1]
    return {'kind': kind, 's0': s0, 's1': s1, 'factor': factor, 'held': curve(held), 'final': curve(final),
            'data': [(si, raw, src, terrain.get(round(si, 1)), tuple(c.line.interpolate(si).coords[0])) for si, raw, src in data]}


def staged_heights(path=None):
    """The staged heights with the user's answers as evidence: imported now, or read from `path` if that import
    has this checkout's snapshot and the same reviewed spans."""
    import track_span_evidence as ev
    truth = json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8'))
    queue = json.loads((ROOT / 'reports/review/track-heights.json').read_text(encoding='utf-8'))
    spans = ev.from_reviews(ev.truth_answers(truth), queue, 'data/truth.json')['span_reviews']
    if path:
        print(f'reading {path}', flush=True)
        staged = json.loads(Path(path).read_text(encoding='utf-8'))
        snap = (ROOT / 'snapshots/CURRENT').read_text().strip()
        have = (staged.get('evidence') or {}).get('span_reviews', [])
        if staged['snapshot'] != snap or json.dumps(have, sort_keys=True) != json.dumps(spans, sort_keys=True):
            raise SystemExit(f'{path}: snapshot {staged["snapshot"]} with {len(have)} reviewed spans, this checkout '
                             f'{snap} with {len(spans)}: run without --staged')
        return staged
    from import_track_heights import stage
    return stage({'span_reviews': spans})


class Chain:
    """One track: DI paths end to end, its 5 m bins of staged heights and, once solved, its runs of heights."""

    def __init__(self, xy, bins):
        self.xy, self.line, self.bins = xy, LineString(xy), bins
        self.length = self.line.length
        self.runs, self.held, self.steps, self.switch, self.review, self.dropped = [], [], [], [], [], []

    def z_at(self, t):
        """(height, source code) at distance t along the chain, or (None, None) outside its runs."""
        for r in self.runs:
            s, z = r['s'], r['z']
            if s[0] - EXTEND <= t <= s[-1] + EXTEND:
                if len(s) == 1:
                    return z[0], r['src'][0]
                i = min(max(1, bisect.bisect_left(s, t)), len(s) - 1)
                k = (t - s[i - 1]) / (s[i] - s[i - 1])
                return z[i - 1] + (z[i] - z[i - 1]) * k, r['src'][i - 1 if k < .5 else i]
        return None, None

    def direction(self, t):
        a, b = self.line.interpolate(max(0.0, t - 1)), self.line.interpolate(min(self.length, t + 1))
        d = math.hypot(b.x - a.x, b.y - a.y) or 1
        return (b.x - a.x) / d, (b.y - a.y) / d


def build_chains(staged):
    """Chains of DI paths (copies dropped), each with its staged heights binned every BIN m."""
    import di_tracks
    geo = [g for g in staged['geometry'] if g['dataset'] == 'di']
    source = di_tracks.Source('di', [{'id': g['id'], 'coords': [(x, y, z) for (x, y), z in zip(g['xy'], g['raw_z'])],
                                      'attrs': g.get('attributes') or {}} for g in geo])  # (dates: re-entries, #209)
    paths = {p['id']: [tuple(c[:2]) for c in p['coords']] for p in source.records}
    lines = {pid: LineString(xy) for pid, xy in paths.items()}
    per = defaultdict(list)
    for h in staged['height_samples']:
        if h['di_id'] in lines:
            per[h['di_id']].append(h)
    out = []
    for chain in chains(paths):
        xy, cum, bins = [], 0.0, defaultdict(list)
        for pid, rev in chain:
            pts = paths[pid][::-1] if rev else paths[pid]
            if not xy:
                xy.append(pts[0])
            elif xy[-1] != pts[0]:  # (ends within the chain's 0.3 m, not always the same point)
                cum += math.dist(xy[-1], pts[0])
                xy.append(pts[0])
            L = lines[pid]
            for h in per.get(pid, ()):
                t = L.project(Point(h['xy']))
                bins[int((cum + (L.length - t if rev else t)) // BIN)].append(h)
            for a, b in zip(pts, pts[1:]):
                xy.append(b)
                cum += math.dist(a, b)
        if len(xy) < 2 or cum <= 0:
            continue
        series = []
        for b in sorted(bins):
            v = bins[b]
            sel = sorted((h for h in v if h['status'] == 'selected' and isinstance(h.get('z'), (int, float))),
                         key=lambda h: h['z'])
            h = (sel or v)[len(sel or v) // 2]
            kinds = Counter((x.get('construction') or {}).get('kind') or 'unknown' for x in v)
            series.append({'s': min((b + .5) * BIN, cum), 'z': h['z'] if sel else None, 'w': 1.0 if sel else 0.0,
                           'src': CODE.get((h.get('height_source') or {}).get('dataset')) if sel else None,
                           'kind': kinds.most_common(1)[0][0], 'terrain': h.get('terrain_z'), 'xy': h['xy'],
                           'flags': sorted({f for x in v for f in x.get('review_flags', [])})})
        out.append(Chain(xy, series))
    print(f'{len(out)} chains of {len(paths)} DI paths ({source.duplicates} copies dropped), '
          f'{sum(len(c.bins) for c in out)} bins', flush=True)
    return out


def junctions(chs):
    """Where a chain's end meets another chain: the diverging ends with the through chain they leave, groups of
    ends that meet only each other, and the points where two chains cross."""
    tree = shapely.STRtree([c.line for c in chs])
    diverge, clusters, seen = [], [], set()
    for i, c in enumerate(chs):
        for t_end, p in ((0.0, c.xy[0]), (c.length, c.xy[-1])):
            pt = Point(p)
            meets = [(int(j), chs[j].line.project(pt)) for j in tree.query(pt.buffer(JOIN))
                     if int(j) != i and chs[j].line.distance(pt) <= JOIN]
            through = [(j, t) for j, t in meets if JOIN < t < chs[j].length - JOIN]
            if through:
                j, t = min(through, key=lambda m: chs[m[0]].line.distance(pt))
                diverge.append({'end': (i, t_end), 'through': (j, t), 'xy': p})
            elif meets:
                key = frozenset([(i, round(t_end, 3))] + [(j, round(t, 3)) for j, t in meets])
                if key not in seen:
                    seen.add(key)
                    clusters.append({'members': [(i, t_end)] + meets, 'xy': p})
    crossings = []
    for i, c in enumerate(chs):
        for j in tree.query(c.line):
            j = int(j)
            if j <= i:
                continue
            x = c.line.intersection(chs[j].line)
            for g in getattr(x, 'geoms', [x]):
                if g.geom_type != 'Point':
                    continue  # (an overlap: one track twice, not a crossing)
                ti, tj = c.line.project(g), chs[j].line.project(g)
                if min(ti, c.length - ti, tj, chs[j].length - tj) > JOIN:
                    crossings.append({'members': [(i, ti), (j, tj)], 'xy': (g.x, g.y)})
    return diverge, clusters, crossings


def held_runs(series):
    """Runs of bins no more than 10 m apart that start and end with a height; a held stretch over HELD_GAP cuts
    the run (returned too), a shorter one stays in it at weight 0 (tools/track_profile.py `_held_runs`)."""
    runs, cut, run = [], [], []
    for x in series:
        if run and x['s'] - run[-1]['s'] > 2 * BIN + 1e-6:
            runs.append(run)
            run = []
        run.append(x)
        held = 0
        while held < len(run) and run[-1 - held]['w'] == 0:
            held += 1
        if held and run[-1]['s'] - run[-held]['s'] > HELD_GAP:
            cut.append(run[-held:])
            runs.append(run[:-held])
            run = []
    runs.append(run)
    for run in runs:
        while run and run[-1]['w'] == 0:
            run.pop()
        while run and run[0]['w'] == 0:
            run.pop(0)
    return [r for r in runs if len(r) >= 2], cut


def solve(c, pins, r, relax=None):
    """The chain's runs of heights with its pinned points {t: z}: radius by construction, switch radius near a
    junction, short holds bridged; `relax` {t: factor} scales the radius within RELAX_REACH of t."""
    # (pins nearer than PIN_MERGE are one: a fork's diverging end and its crossing with the through track lie
    # 0.003-1.6 m apart, and points that close make the solver's steps unequal by thousands)
    groups = []
    for t, z in sorted(pins.items()):
        if groups and t - groups[-1][-1][0] <= PIN_MERGE:
            groups[-1].append((t, z))
        else:
            groups.append([(t, z)])
    pins = {sum(t for t, _ in g) / len(g): sum(z for _, z in g) / len(g) for g in groups}
    series = [dict(x) for x in c.bins if all(abs(x['s'] - t) > NEAR_PIN for t in pins)]
    series += [{'s': t, 'z': z, 'w': 1.0, 'src': None, 'pin': True, 'kind': None, 'terrain': None, 'flags': [],
                'xy': None} for t, z in pins.items()]
    series.sort(key=lambda x: x['s'])
    runs, cut = held_runs(series)
    c.held = [{'s0': h[0]['s'], 's1': h[-1]['s'], 'flags': sorted({f for x in h for f in x['flags']}),
               'xy': h[len(h) // 2]['xy']} for h in cut]
    c.runs, c.steps, c.review, c.dropped = [], [], [], []
    for run in runs:
        # (a held bin starts on the straight line between its neighbours, at HOLD_WEIGHT: at weight 0 the curve was
        # free to sag anywhere the radius allows, 5 cm under a straight grade across 40 m)
        known = [(x['s'], x['z']) for x in run if x['z'] is not None]
        for x in run:
            if x['z'] is not None:
                x['zf'] = x['z']
                continue
            k = bisect.bisect_left(known, (x['s'],))
            (s0, z0), (s1, z1) = known[max(0, k - 1)], known[min(len(known) - 1, k)]
            x['zf'] = z0 if s1 == s0 else z0 + (z1 - z0) * (x['s'] - s0) / (s1 - s0)
        s, zf = [x['s'] for x in run], [x['zf'] for x in run]
        rmin0 = [r['switch'] if any(a <= si <= b for a, b in c.switch)
                 else r['open'] if x['kind'] == 'open' else r['street'] for si, x in zip(s, run)]
        weight = [PIN_WEIGHT if x.get('pin') else (x['w'] or HOLD_WEIGHT) for x in run]
        # (what the band does not hold: a lone bad point, one or two bins, and a stretch steeper than any track, the
        # archive on the ground under a deck; the robust fit at the design radius, without the pins, finds them)
        rob = vertical_profile(s, zf, rmin0, weight=[0.0 if x.get('pin') else w for x, w in zip(run, weight)])['z']
        groups = []
        for i, x in enumerate(run):
            if x['w'] and not x.get('pin') and abs(rob[i] - x['z']) > BAND:
                if groups and x['s'] - run[groups[-1][-1]]['s'] <= 20:
                    groups[-1].append(i)
                else:
                    groups.append([i])
        def steep(g):
            idx = [i for i in range(max(0, g[0] - 1), min(len(run), g[-1] + 2)) if run[i]['z'] is not None]
            return any(abs(run[b]['z'] - run[a]['z']) > MAX_GRADE * (run[b]['s'] - run[a]['s']) for a, b in zip(idx, idx[1:]))
        out = [g for g in groups if len(g) <= LONE or steep(g)]
        dropped = {i for g in out for i in g}
        zone = lambda si: any(a <= si <= b for a, b in c.switch)
        tol = [PIN_TOL if x.get('pin') else None if (not x['w'] or i in dropped) else JUNCTION_BAND if zone(x['s'])
               else BAND for i, x in enumerate(run)]
        weight = [0.0 if i in dropped else w for i, w in enumerate(weight)]
        # the band rule: within BAND of the staged heights at the design radius, else the radius gives way where the
        # band is missed (an answer to hold the radius keeps it) and the place goes to the user's review
        rmin = list(rmin0)
        fit = [PIN_FIT if x.get('pin') else FIT for x in run]
        over = lambda r_: [i for i, e in enumerate(r_['excess']) if e > fit[i]]
        res = first = banded_profile(s, zf, rmin, tol, weight)
        relaxed = drops = 0
        while relaxed < RELAX_STEPS and drops < DROP_MAX:
            # (an answer to hold the radius holds the whole place: the points outside the band within 50 m of each
            # other; one that discards the outliers drops the worst of them and fits the rest again, data/truth.json)
            bad, worst, group = [], [], []
            for i in over(res) + [None]:
                if i is not None and (not group or s[i] - s[group[-1]] <= 50):
                    group.append(i)
                    continue
                if group:
                    a = answer_at([run[j]['xy'] or tuple(c.line.interpolate(s[j]).coords[0]) for j in group])
                    free = [j for j in group if not run[j].get('pin')]
                    if a is None:
                        bad += group
                    elif a.get('outliers') == 'drop' and free:
                        worst.append(max(free, key=lambda j: res['excess'][j]))
                group = [i] if i is not None else []
            if not bad and not worst:
                break
            for j in worst:
                tol[j], weight[j] = None, 0.0
                c.dropped.append(run[j]['xy'] or tuple(c.line.interpolate(s[j]).coords[0]))
            drops += bool(worst)
            if bad:
                relaxed += 1
                near = lambda si: any(abs(si - s[i]) <= RELAX_REACH for i in bad)
                rmin = [max(v * RELAX_STEP, MIN_RADIUS) if near(si) else v for si, v in zip(s, rmin)]
            res = banded_profile(s, zf, rmin, tol, weight)
        # (where even that cannot meet a pin, the rails join first: the band gives way within 15 m of it)
        apart = [i for i in over(res) if run[i].get('pin')]
        if apart:
            tol = [None if t is not None and not run[i].get('pin') and min(abs(s[i] - s[j]) for j in apart) <= 15 else t
                   for i, t in enumerate(tol)]
            res = banded_profile(s, zf, rmin, tol, weight)
            # (an answer holds the radius against the band, not against the rails joining: where they still miss, the
            # radius gives way near the pin as it would without the answer; 24 junctions 1-2.5 cm apart, 2026-11-04)
            for _ in range(RELAX_STEPS):
                apart = [i for i in over(res) if run[i].get('pin')]
                if not apart:
                    break
                near = lambda si: any(abs(si - s[i]) <= RELAX_REACH for i in apart)
                rmin = [max(v * RELAX_STEP, MIN_RADIUS) if near(si) else v for si, v in zip(s, rmin)]
                res = banded_profile(s, zf, rmin, tol, weight)
        raw = [None if x.get('pin') else x['z'] for x in run]
        # (for review: the band missed by over FIT at the design radius, or rails over FIT apart; a few mm at a pin
        # only bend the radius, they are no question)
        review = [i for i, e in enumerate(first['excess']) if e > FIT]
        if review:
            worst, place = review, []
            for i in worst + [None]:
                if i is not None and (not place or s[i] - s[place[-1]] <= 50):
                    place.append(i)
                    continue
                if place:
                    big = max(place, key=lambda j: first['excess'][j])
                    junction = any(x.get('pin') and min(abs(x['s'] - s[j]) for j in place) <= 10 for x in run)
                    rec = review_place(c, 'junction' if junction else 'band', s[place[0]] - 60, s[place[-1]] + 60,
                                       [{'s': s, 'z': first['z']}], [{'s': s, 'z': res['z'], 'raw': raw,
                                       'src': [x['src'] for x in run]}],
                                       round(min(a / b for a, b in zip(rmin, rmin0)), 2))
                    rec['at'] = tuple(run[big]['xy'] or c.line.interpolate(s[big]).coords[0])
                    rec['excess'] = first['excess'][big]
                    rec['fits'] = not over(res) and not apart
                    c.review.append(rec)
                place = [i] if i is not None else []
        # steps: what the band did not hold, and anything still outside it, by cause
        left = [over(res)] if over(res) else []
        for g in out + [g for g in left if g]:
            pts = [run[i] for i in g]
            held = [x for x in run if x['w'] == 0 and min(abs(x['s'] - p['s']) for p in pts) <= 20]
            big = max(g, key=lambda i: abs(res['z'][i] - run[i]['z']))
            if abs(res['z'][big] - run[big]['z']) <= MISS:
                continue
            c.steps.append({'cause': cause([{'src': {'dtmp': 'archive', 'zps': 'survey'}.get(p['src'], p['src']),
                                             'z': p['z'], 'terrain': p['terrain']} for p in pts],
                                           [run[i]['z'] - res['z'][i] for i in g],
                                           any(STRUCTURE & set(x['flags']) for x in held)),
                            'largest_m': round(run[big]['z'] - res['z'][big], 2), 'points': len(g),
                            'xy': run[big]['xy'], 'flags': sorted({f for p in pts for f in p['flags']})})
        step_s = {s[i] for g in out + left for i in g if abs(res['z'][i] - zf[i]) > MISS}  # (steps as #190 counts them)
        c.runs.append({'s': s, 'z': res['z'], 'raw': raw, 'src': [('curve' if x['w'] == 0 else x['src']) for x in run],
                       'step': [si in step_s for si in s], 'min_radius': res['min_radius']})
    # (a pin's source is that of its neighbours: the junction's height comes from the through track)
    for run in c.runs:
        for i, v in enumerate(run['src']):
            if v is None:
                run['src'][i] = next((run['src'][j] for j in sorted(range(len(run['src'])), key=lambda j: abs(j - i))
                                      if run['src'][j]), 'curve')


def assemble(chs):
    """Solve every chain, longest first; a chain meeting one already solved (a junction, a group of ends, a crossing
    at grade) is pinned to its heights there. One pass: the pins come only from final curves (each crossing at the
    mean of its two tracks made pins a few metres apart and centimetres off along the tracks of a junction's
    diamonds, which no curve within the radius could meet: 172 s for 7 chains)."""
    r = radii()
    t0 = time.time()
    diverge, clusters, crossings = junctions(chs)
    print(f'junctions: {len(diverge)} diverging ends, {len(clusters)} groups of ends, {len(crossings)} crossings '
          f'({time.time() - t0:.0f} s)', flush=True)
    # chain -> (t on it, other chain, t on that, kind): a fork or a crossing is one point of both tracks; ends that
    # meet each other, or tracks meeting a third one near each other, are up to JOIN / NEAR_MEET apart
    meets = defaultdict(list)
    for d in diverge:
        (i, ti), (j, tj) = d['end'], d['through']
        meets[i].append((ti, j, tj, 'fork'))
        meets[j].append((tj, i, ti, 'fork'))
        # (the turnout: from the fork into the diverging track on both, the way the diverging track leaves)
        c, through = chs[i], chs[j]
        inward = 1 if ti == 0 else -1
        c.switch.append(tuple(sorted((ti - inward * BEHIND, ti + inward * SWITCH))))
        ahead = through.line.project(c.line.interpolate(ti + inward * min(10.0, c.length)))
        way = 1 if ahead >= tj else -1
        through.switch.append(tuple(sorted((tj - way * BEHIND, tj + way * SWITCH))))
    for g in clusters + crossings:
        for a, (i, ti) in enumerate(g['members']):
            if g in crossings:
                chs[i].switch.append((ti - DIAMOND, ti + DIAMOND))
            for j, tj in g['members'][a + 1:]:
                kind = 'cross' if g in crossings else 'ends'
                meets[i].append((ti, j, tj, kind))
                meets[j].append((tj, i, ti, kind))
    for i in range(len(chs)):
        near = sorted(m for m in meets[i] if m[3] != 'cross')
        for a, (t1, j1, u1, _) in enumerate(near):
            for t2, j2, u2, _ in near[a + 1:]:
                if t2 - t1 > NEAR_MEET:
                    break
                if j1 != j2 and not any(m[1] == j2 and abs(m[0] - u1) <= NEAR_MEET for m in meets[j1]):
                    meets[j1].append((u1, j2, u2, 'near'))
                    meets[j2].append((u2, j1, u1, 'near'))
    solved, pinned, used, apart, t0 = set(), 0, [], {}, time.time()
    for n, i in enumerate(sorted(range(len(chs)), key=lambda i: -chs[i].length)):
        c = chs[i]
        solve(c, {}, r)
        cands = []
        for ti, j, tj, kind in meets[i]:
            if j not in solved:
                continue
            zj, zi = chs[j].z_at(tj)[0], c.z_at(ti)[0]
            if zj is None:
                continue
            if kind == 'cross' and (zi is None or abs(zi - zj) > CROSS):
                if zi is not None:  # (one track over the other, or one of them wrong there: listed)
                    apart[(min(i, j), max(i, j), round(ti), round(tj))] = (abs(zi - zj), c.line.interpolate(ti))
                continue
            cands.append((ti, kind in ('ends', 'near'), -chs[j].length, zj, j, tj))
        # (several at one spot: a fork's or crossing's own point first, then the longer track; at a fork on a 4 %
        # grade the end of a third track 0.5 m off gave 4 cm more)
        pins = {}
        for x in sorted(cands, key=lambda x: (x[1], x[2])):
            if all(abs(x[0] - t) > PIN_MERGE for t in pins):
                pins[x[0]] = x[3]
                used.append((i, x[0], x[4], x[5]))
        if pins:
            solve(c, pins, r)
            pinned += 1
        solved.add(i)
        if n % 200 == 199:
            print(f'  {n + 1} of {len(chs)} chains solved ({pinned} pinned), {time.time() - t0:.0f} s', flush=True)
    # what is left where tracks were pinned to each other: the heights of both there
    worst = []
    for i, ti, j, tj in used:
        a, b = chs[i].z_at(ti)[0], chs[j].z_at(tj)[0]
        if a is not None and b is not None:
            worst.append((abs(a - b), chs[i].line.interpolate(ti)))
    worst.sort(key=lambda w: -w[0])
    xy = lambda p: [round(p.x, 1), round(p.y, 1)]
    return {'diverging': len(diverge), 'groups': len(clusters), 'crossings': len(crossings), 'pinned': len(used),
            'junction_heights_apart': [{'m': round(d, 4), 'xy': xy(p)} for d, p in worst[:10]],
            'over_1cm': sum(1 for d, _ in worst if d > .01),
            'crossings_apart': [{'m': round(d, 2), 'xy': xy(p)} for d, p in sorted(apart.values(), key=lambda v: -v[0])],
            'review_places': [{'kind': p['kind'], 'xy': [round(v, 1) for v in p['at']], 'factor': p['factor'],
                               'excess_m': round(p['excess'], 3), 'fits': p['fits']} for c in chs for p in c.review]}


class Lookup:
    """The height where a line's point lies: the chains within MATCH and ANGLE of its direction, weighted by how near
    each is (past a fork both tracks lie within centimetres and share the junction's height; picking one, the line
    jumped between them, and staying on one stepped where it let go)."""

    def __init__(self, chs):
        self.chs, self.tree = chs, shapely.STRtree([c.line for c in chs])

    def along(self, pts, step=OUT_STEP):
        """(heights, sources) every `step` m along a polyline, and its length."""
        line = LineString(pts)
        L = line.length
        n = max(1, math.ceil(L / step - 1e-9))
        zs, srcs = [], []
        for k in range(n + 1):
            # (the last sample sits at n * step, past the line's end along its chain: the game reads every sample
            # at k * step, and the end read there stood 4 cm off on an 8 % grade)
            s = min(L, k * step)
            over = k * step - s
            p, a, b = line.interpolate(s), line.interpolate(max(0.0, s - 1)), line.interpolate(min(L, s + 1))
            d = math.hypot(b.x - a.x, b.y - a.y) or 1
            ux, uy = (b.x - a.x) / d, (b.y - a.y) / d
            cands = []
            for j in self.tree.query(p.buffer(MATCH)):
                c = self.chs[int(j)]
                dist = c.line.distance(p)
                if dist > MATCH:
                    continue
                t = c.line.project(p)
                vx, vy = c.direction(t)
                cos = ux * vx + uy * vy
                if abs(cos) >= math.cos(math.radians(ANGLE)):
                    cands.append((dist, int(j), t + (over if cos > 0 else -over)))
            acc = wsum = 0.0
            src = None
            for dist, j, t in sorted(cands):
                z, sj = self.chs[j].z_at(t)
                if z is None:
                    continue
                w = (1 - dist / MATCH) / (dist + .02) ** 2
                acc, wsum, src = acc + w * z, wsum + w, src or sj
            zs.append(round(acc / wsum, 3) if wsum else None)
            srcs.append(src if wsum else 'surface')
        return zs, srcs, L


def ranges(srcs, step=OUT_STEP):
    """[[s0, s1, source], ...] of a run of per-sample sources."""
    out = []
    for k, v in enumerate(srcs):
        s = k * step
        if out and out[-1][2] == v:
            out[-1][1] = s
        else:
            if out:
                out[-1][1] = s - step / 2
            out.append([s if not out else s - step / 2, s, v])
    return [[round(a, 1), round(b, 1), c] for a, b, c in out]


def across(path, back, back_z, step=OUT_STEP):
    """At every path height: the opposite track's offset (left > 0) and height where it runs beside ours, parallel
    within ANGLE, ACROSS_MIN-ACROSS_MAX m off; the game's cross-section of the street between them (heightAt)."""
    a, b = LineString(path), LineString(back)
    n = max(1, math.ceil(a.length / step - 1e-9))
    off, zs = [], []
    for k in range(n + 1):
        s = min(a.length, k * step)
        p, u0, u1 = a.interpolate(s), a.interpolate(max(0.0, s - 1)), a.interpolate(min(a.length, s + 1))
        d = math.hypot(u1.x - u0.x, u1.y - u0.y) or 1
        ux, uy = (u1.x - u0.x) / d, (u1.y - u0.y) / d
        t = b.project(p)
        q, v0, v1 = b.interpolate(t), b.interpolate(max(0.0, t - 1)), b.interpolate(min(b.length, t + 1))
        e = math.hypot(v1.x - v0.x, v1.y - v0.y) or 1
        lat = (q.y - p.y) * ux - (q.x - p.x) * uy
        i = min(int(t / step), len(back_z) - 2)
        z0, z1 = back_z[i], back_z[i + 1]
        if (not ACROSS_MIN <= abs(lat) <= ACROSS_MAX or z0 is None or z1 is None
                or abs(ux * (v1.x - v0.x) + uy * (v1.y - v0.y)) / e < math.cos(math.radians(ANGLE))):
            off.append(None)
            zs.append(None)
            continue
        off.append(round(lat, 2))
        zs.append(round(z0 + (z1 - z0) * (t / step - i), 3))
    return off, zs


def staged_along(pts, lookup):
    """[[s, staged height], ...] along a polyline: every 5 m bin of the chains under it on runs without a step, where
    the bin lies within 0.3 m of the line (the issue's comparison: the game's track against the staged heights)."""
    line_, out = LineString(pts), []
    for j in lookup.tree.query(line_, predicate='dwithin', distance=MATCH):
        c = lookup.chs[int(j)]
        for run in c.runs:
            if any(run['step']):
                continue
            for s, raw in zip(run['s'], run['raw']):
                if raw is None:
                    continue
                p = c.line.interpolate(s)
                if line_.distance(p) <= .3:
                    out.append([round(line_.project(p), 1), round(raw, 3)])
    return sorted(out)


def join_ends(tracks, step=OUT_STEP):
    """Where a drawn track ends on another one (within JOIN of its line, away from its ends), its last metres take
    that track's height at the end, fading out over END_FADE m: the chains agree at their junctions within 1 cm, but
    a junction's short edges, ending up to 0.3 m off the track they join, were sampled 3 cm apart on a 2 % grade
    (Strossmayerovo náměstí). The track passing through is the reference, the longer one if there are several; ends
    that meet only each other take their mean."""
    lines = [LineString([tuple(p[:2]) for p in t['p']]) if t.get('zs') else None for t in tracks]
    tree = shapely.STRtree([g if g is not None else LineString([(0, 0), (0, 0)]) for g in lines])
    def z_on(t, g, s):
        k = s / step
        i = min(int(k), len(t['zs']) - 2)
        a, b = t['zs'][i], t['zs'][i + 1]
        return None if a is None or b is None else a + (b - a) * (k - i)
    moves, loose = [], []
    for t, g in zip(tracks, lines):
        if g is None:
            continue
        for end, at in ((0, 0.0), (1, g.length)):
            p = Point(g.coords[0 if end == 0 else -1])
            best = None
            for j in tree.query(p.buffer(JOIN)):
                o, go = tracks[int(j)], lines[int(j)]
                if go is None or o is t or go.distance(p) > JOIN:
                    continue
                so = go.project(p)
                if min(so, go.length - so) <= JOIN:
                    continue  # (another end there: not passing through)
                z = z_on(o, go, so)
                if z is not None and (best is None or go.length > best[0]):
                    best = (go.length, z)
            own = z_on(t, g, at)
            if own is None:
                continue
            if best:
                moves.append((t, at, best[1] - own))
            else:
                loose.append((t, at, own, p))
    # (ends meeting only other ends: their mean)
    seen = set()
    for a, (t, at, own, p) in enumerate(loose):
        if a in seen:
            continue
        group = [b for b, x in enumerate(loose) if b not in seen and x[3].distance(p) <= JOIN]
        seen.update(group)
        if len(group) > 1:
            mean = sum(loose[b][2] for b in group) / len(group)
            moves += [(loose[b][0], loose[b][1], mean - loose[b][2]) for b in group]
    per = defaultdict(dict)
    for t, at, dz in moves:
        per[id(t)][at] = (t, dz)
    for ends in per.values():
        t = next(iter(ends.values()))[0]
        L = max(ends) if len(ends) > 1 else None
        for k in range(len(t['zs'])):
            if t['zs'][k] is None:
                continue
            s, dz = k * step, 0.0
            for at, (_, d) in ends.items():
                if L is not None and L < 2 * END_FADE:  # (a short track joined at both ends: from one to the other)
                    w = max(0.0, min(1.0, 1 - s / L)) if at == 0 else max(0.0, min(1.0, s / L))
                else:
                    w = max(0.0, min(1.0, 1 - ((s if at == 0 else at - s) - 2.5) / END_FADE))
                dz += d * w
            t['zs'][k] = round(t['zs'][k] + dz, 3)
    return len(moves)


def write_line(line, lookup, chs):
    """The line's heights: path and pathBack every 2 m, each drawn track's `zs`, with provenance."""
    import sources
    from atomic import replacing
    dst = ROOT / 'data' / f'line{line}.json'
    data = json.loads(dst.read_text(encoding='utf-8'))
    heights, src_ranges, metres = {'step': OUT_STEP}, {}, Counter()
    for key in ('path', 'pathBack'):
        if not data.get(key) or len(data[key]) < 2:
            continue
        zs, srcs, L = lookup.along([tuple(p[:2]) for p in data[key]])
        heights[key] = zs
        src_ranges[key] = ranges(srcs)
        for a, b, v in src_ranges[key]:
            metres[v] += b - a
    heights['staged'] = {key: staged_along([tuple(p[:2]) for p in data[key]], lookup) for key in ('path', 'pathBack')
                         if heights.get(key)}
    if heights.get('path') and heights.get('pathBack'):
        heights['backOff'], heights['backZ'] = across([tuple(p[:2]) for p in data['path']],
                                                      [tuple(p[:2]) for p in data['pathBack']], heights['pathBack'])
    covered = 0
    for t in data['tracks']:
        t.pop('zs', None)
        if len(t['p']) < 2:
            continue
        zs, _, _ = lookup.along([tuple(p[:2]) for p in t['p']])
        if any(z is not None for z in zs):
            t['zs'] = zs
            covered += 1
    for _ in range(2):  # (a reference may move near its own end: once more settles it)
        join_ends(data['tracks'])
    data['heights'] = heights
    data['heightSource'] = src_ranges
    data['provenance'] = sources.stamp('line_heights.py', {
        'heights': sources.entry('heights', [round(metres[k]) for k in LEVELS], 'm (path and pathBack)')},
        prev=data.get('provenance'))
    data['attribution'] = sources.attribution(data['provenance'])
    with replacing(dst, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    total = sum(metres.values()) or 1
    print(f'line {line}: path and pathBack {total:.0f} m: ' + ', '.join(f'{k} {metres[k]:.0f} m' for k in LEVELS if metres[k])
          + f'; {covered} of {len(data["tracks"])} tracks with heights; wrote {dst.name}', flush=True)
    return heights, src_ranges, data


def line_report(line, chs, lookup, data, summary):
    """Per direction: the stretches without a height (over 10 m) and the heights against the staged ones on runs
    without a step (the issue's p90 <= 0.10 m)."""
    from geo import Frame
    F, out = Frame(), {}
    for key in ('path', 'pathBack'):
        if not data.get(key):
            continue
        line_ = LineString([tuple(p[:2]) for p in data[key]])
        zs = data['heights'].get(key, [])
        gaps, a = [], None
        for k, z in enumerate(zs + [0.0]):
            if z is None and a is None:
                a = k
            elif z is not None and a is not None:
                if (k - a) * OUT_STEP > 10:
                    p = line_.interpolate((a + k) / 2 * OUT_STEP)
                    lat, lon = F.ll(p.x, p.y)
                    near = [h for c in chs for h in c.held
                            if h['xy'] and math.dist(h['xy'], (p.x, p.y)) < (k - a) * OUT_STEP]
                    gaps.append({'s0': a * OUT_STEP, 's1': k * OUT_STEP, 'm': (k - a) * OUT_STEP,
                                 'lat': round(float(lat), 5), 'lon': round(float(lon), 5),
                                 'why': 'held' if near else 'no DI track',
                                 'flags': sorted({f for h in near for f in h['flags']} - {'track_style_defaulted_panels'})[:4]})
                a = None
        # (the staged heights along this direction, compared with the line's heights at their place)
        diffs = []
        for sp, raw in data['heights']['staged'].get(key, []):
            k = sp / OUT_STEP
            i = min(int(k), len(zs) - 2)
            if zs[i] is not None and zs[i + 1] is not None:
                diffs.append(abs(zs[i] + (zs[i + 1] - zs[i]) * (k - i) - raw))
        diffs.sort()
        q = lambda f: round(diffs[min(len(diffs) - 1, int(f * len(diffs)))], 3) if diffs else None
        near = lambda items: [dict(x, lat=round(float(F.ll(*x['xy'])[0]), 5), lon=round(float(F.ll(*x['xy'])[1]), 5),
                                   s=round(line_.project(Point(x['xy'])))) for x in items if line_.distance(Point(x['xy'])) < 10]
        out[key] = {'without_height': gaps, 'vs_staged': {'bins': len(diffs), 'p50': q(.5), 'p90': q(.9), 'p99': q(.99)},
                    'review_places': near(summary['review_places']), 'crossings_apart': near(summary['crossings_apart'])}
        print(f'  {key}: heights vs staged on runs without a step: {out[key]["vs_staged"]}; '
              f'{len(gaps)} stretches without a height over 10 m', flush=True)
        for g in gaps:
            print(f"    s {g['s0']:.0f}-{g['s1']:.0f} ({g['m']:.0f} m) at {g['lat']} N {g['lon']} E: {g['why']} {g['flags']}")
        for x in out[key]['review_places']:
            print(f"    for review ({x['kind']}): at the design radius {x['excess_m']} m outside the band at s {x['s']} "
                  f"({x['lat']} N {x['lon']} E); radius x{x['factor']}{'' if x['fits'] else ', still outside'}")
        for x in out[key]['crossings_apart']:
            print(f"    crossing {x['m']} m apart in the data at s {x['s']} ({x['lat']} N {x['lon']} E), not pinned")
    return out


def radius_review(chs, snapshot):
    """reports/review/track-radius.json: every place where the radius gave way (or an answer held it), the curve
    held to the design radius and the final one as answer previews over the staged heights and the terrain. A place
    the user answered (data/truth.json radiusAnswers) leaves the list."""
    from geo import Frame
    from atomic import replacing
    F = Frame()
    routes = {}
    for n in ('9', '17', '22', '23', '37'):
        f = ROOT / 'data' / f'line{n}.json'
        if f.exists():
            d = json.loads(f.read_text(encoding='utf-8'))
            routes[n] = [LineString([tuple(p[:2]) for p in d[k]]) for k in ('path', 'pathBack') if d.get(k)]
    by = {}
    for c in chs:
        for p in c.review:
            if len(p['data']) >= 2 and not answer_at([p['at']], (HOLD, FOLLOW)):
                lat, lon = (float(v) for v in F.ll(*p['at']))
                by.setdefault(f'radius-{lat:.4f}-{lon:.4f}', []).append(p)
    radius = lambda curve: min(implied_radii([a for a, _ in curve], [b for _, b in curve]), default=math.inf)
    out = []
    for ident, places in by.items():
        main = max(places, key=lambda p: len(p['data']))
        at = main['at']
        lat, lon = (float(v) for v in F.ll(*at))
        near = {n: min(g.distance(Point(at)) for g in gs) for n, gs in routes.items()}
        lines = sorted((n for n, dd in near.items() if dd < 10), key=int)
        spans, previews = [], {HOLD: {}, FOLLOW: {}}
        for k, p in enumerate(sorted(places, key=lambda p: -len(p['data']))):
            sid = f'{ident}:track{k + 1}'
            spans.append({'id': sid, 'line': int(lines[0] if lines else min(near, key=near.get)), 'direction': 'path',
                          'structure': {'kind': p['kind']},
                          'status': 'review', 'start_s': round(p['s0'], 1), 'length_m': round(p['s1'] - p['s0'], 1),
                          'profile': [{'s': round(si, 1), 'xy': [round(v, 2) for v in xy],
                                       'archive': [{'z': round(raw, 3)}] if raw is not None and src == 'dtmp' else [],
                                       'di_z': round(raw, 3) if raw is not None and src != 'dtmp' else None,
                                       'surfaces': [], 'ipr_terrain_z': terr}
                                      for si, raw, src, terr, xy in p['data']]})
            previews[HOLD][sid] = [[round(a, 1), round(b, 3)] for a, b in p['held']]
            previews[FOLLOW][sid] = [[round(a, 1), round(b, 3)] for a, b in p['final']]
        mag = max(p['excess'] for p in places)
        r_final = min(radius(p['final']) for p in places)
        where = 'at a junction (the rails meet there within 5 mm)' if main['kind'] == 'junction' else 'on plain track'
        info = (f"{main['kind']}: {where}, no curve at the design radius stays within {BAND * 100:.0f} cm of the staged "
                f"heights: held to it, the curve leaves that band by up to {mag * 100:.0f} cm (tightest "
                f"{radius(main['held']):.0f} m). Within the band the radius is {r_final:.0f} m"
                f"{'' if all(p['fits'] for p in places) else ', and the band is still missed'}.")
        out.append({'kind': 'trackheight', 'id': ident, 'x': at[0], 'y': at[1], 'mag': round(mag, 3),
                    'status': 'review', 'place': [round(lat, 5), round(lon, 5)], 'lines_near': lines, 'info': info,
                    'decision': {'span_ids': [sp['id'] for sp in spans], 'structure': {'kind': main['kind']}, 'status': 'review'},
                    'spans': spans, 'options': [HOLD, FOLLOW, 'unsure'], 'answer_explanations': {},
                    'answer_previews': previews})
    out.sort(key=lambda f: -f['mag'])
    dst = ROOT / 'reports' / 'review' / 'track-radius.json'
    with replacing(dst, 'w', encoding='utf-8', newline='') as fh:
        json.dump({'schema': 1, 'snapshot': snapshot, 'findings': out}, fh, ensure_ascii=False, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('lines', nargs='+')
    ap.add_argument('--staged', help='an import of this checkout (tools/import_track_heights.py --evidence ...)')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    global RADIUS_ANSWERS
    RADIUS_ANSWERS = load_radius_answers(json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8')))
    staged = staged_heights(args.staged)
    chs = build_chains(staged)
    del staged
    summary = assemble(chs)
    from geo import Frame
    F = Frame()
    steps = [dict(s, lat=round(float(F.ll(*s['xy'])[0]), 5), lon=round(float(F.ll(*s['xy'])[1]), 5))
             for c in chs for s in c.steps if s['xy']]
    by = Counter(s['cause'] for s in steps)
    bad = [s for s in steps if abs(s['largest_m']) > BIG and s['cause'] not in ('di', 'dip', 'structure')]
    held = [dict(h, m=round(h['s1'] - h['s0'], 1), lat=round(float(F.ll(*h['xy'])[0]), 5),
                 lon=round(float(F.ll(*h['xy'])[1]), 5)) for c in chs for h in c.held if h['xy']]
    moved = sorted(abs(z - raw) for c in chs for run in c.runs if not any(run['step'])
                   for z, raw in zip(run['z'], run['raw']) if raw is not None)
    q = lambda f: round(moved[min(len(moved) - 1, int(f * len(moved)))], 3) if moved else None
    print(f"network: {summary['diverging']} diverging ends, {summary['groups']} groups of ends, {summary['crossings']} "
          f"crossings; {summary['pinned']} pinned, with two heights over 1 cm: {summary['over_1cm']}; "
          f"{len(summary['crossings_apart'])} crossings over {CROSS:g} m apart in the data, not pinned")
    print(f'network: moved from the staged heights on runs without a step: p50 {q(.5)}, p90 {q(.9)}, p99 {q(.99)} m')
    print(f'network: steps by cause {dict(by)}; {len(bad)} over {BIG:g} m without a rule to explain them')
    kinds = Counter(p['kind'] for p in summary['review_places'])
    print(f'network: {len(held)} held stretches over {HELD_GAP} m, {sum(h["m"] for h in held):.0f} m; for review where no '
          f'curve at the design radius fits within {BAND:g} m: {kinds.get("band", 0)} places, {kinds.get("junction", 0)} at junctions')
    answered = {id(a) for c in chs for p in c.review if (a := answer_at([p['at']], (HOLD, FOLLOW)))}
    print(f"radius answers: {len(answered)} of {len(RADIUS_ANSWERS)} met a place; "
          f"{sum(len(c.dropped) for c in chs)} points dropped where an answer discards the outliers")
    review = radius_review(chs, (ROOT / 'snapshots/CURRENT').read_text().strip())
    print(f"radius review: {len(review)} places ({sum(f['decision']['structure']['kind'] == 'junction' for f in review)} "
          f"at junctions), reports/review/track-radius.json")
    lookup, report = Lookup(chs), {'network': {**summary, 'steps_by_cause': dict(by), 'unexplained_steps': bad,
                                               'moved_m': {'p50': q(.5), 'p90': q(.9), 'p99': q(.99)},
                                               'held_over_60m': held,
                                               'dropped_by_answers': [[round(float(v), 5) for v in F.ll(*xy)]
                                                                      for c in chs for xy in c.dropped]}, 'lines': {}}
    for line in args.lines:
        _, _, data = write_line(line, lookup, chs)
        report['lines'][line] = line_report(line, chs, lookup, data, summary)
    out = ROOT / 'reports' / 'line-heights.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'report: {out.relative_to(ROOT)}')
    sys.exit(1 if bad or summary['over_1cm'] else 0)


if __name__ == '__main__':
    main()
