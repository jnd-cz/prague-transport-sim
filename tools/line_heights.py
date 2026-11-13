# SPDX-License-Identifier: AGPL-3.0-or-later
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

Before the smoother, the user's answers (data/truth.json) and the rules that apply them set the bins' heights, and the
solver asks them where an answer holds or follows the radius: tools/height_answers.py.

A line's path, opposite path and drawn tracks take the heights of the chains they lie on every 2 m (`heights`,
`heightSource`, a track's `zs`; `backOff` / `backZ` the opposite track beside the path); where none does (OSM or archive fill, a long hold) the value is null and the
game keeps its surface-plus-style profile there (src/terrain.js Profile).
"""
import argparse
import bisect
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, wait
import heapq
import json
import math
import os
import time
from pathlib import Path
import sys

import numpy as np
import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_profile import BIN, HELD_GAP, ROOT, STEP as MISS, STRUCTURE, BIG, banded_profile, cause, chains, implied_radii, radii, vertical_profile  # noqa: E402
from track_curve import geometry_fact  # noqa: E402
# (the answers are height_answers' globals, read there: set them as ha.RADIUS_ANSWERS ..., never on this module)
import height_answers as ha  # noqa: E402
from height_answers import (BLEND_REACH, FOLLOW, HOLD, MAX_GRADE, SMOOTH_WAVELENGTH, STRUCTURE_FLAGS, answer_at, answered_source,  # noqa: E402
                            below_floor, ground_at, height_runs, smooth_line, staged_heights)

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
MIN_RADIUS = float(geometry_fact('min-radius-passenger'))  # m, 20: 12 times, never under the tightest horizontal radius
RELEASE, RELEASE_ROUNDS = 15.0, 3  # m, rounds: where the floor cannot meet the band, the band gives way this far around the
                                   # points it misses (as near a pin, below)
REVIEW_ISSUE = 276  # the issue the radius review waits for (reports/review/track-radius.json names it): W3's track
                    # profile work, since #358 closed at W2 (#416)
TIGHT = 0.95        # a solved curve under this share of the floor is a place for review: the solver's own tolerance is 2 %
                    # (track_profile.TOL), and 10 junctions read 478-490 m, no question for the user
NEAR_MEET = 2.0  # m: two tracks meeting a third this near each other along it meet each other too (Ke Stírce: two
                 # track ends 0.65 m apart on a third track, 9 cm apart in height, pinned it to both)
HOLD_WEIGHT = 1e-3  # a held bin's pull towards the straight line across its hold
PIN_MERGE = 0.5  # m: pinned points this near each other along a track are one (their mean)
MEET_GIVE = 0.03  # m a pin may give where an answer holds the floor and the tracks' meeting points need a tighter curve
MEET_ROUNDS = 8  # where an answer holds the floor at a junction, the rounds in which its tracks meet half way (assemble)
PIN_WEIGHT = 1e3  # a pinned point's weight against a staged height's 1 (1e6 left the solver short of the radius
                  # after 3000 steps on 30 chains, up to 55 s each)
CROSS = 1.0     # m: tracks crossing within this height of each other cross at grade (else one passes over)
END_FADE = 10.0  # m over which a track's end taking the height of the track it joins fades out
ACROSS_MIN, ACROSS_MAX = 2.0, 6.0  # m: the opposite track beside ours (the game's corridor is 6 m, src/terrain.js)
EXTEND = BIN    # m: a chain's height reaches this far past its first and last bin (its ends, junctions)
CODE = {'di': 'di', 'archive': 'dtmp', 'reviewed': 'review', 'deck': 'zps', 'survey': 'zps'}  # staged dataset -> code
LEVELS = ('di', 'dtmp', 'review', 'zps', 'lidar', 'curve', 'surface')  # codes in the order of sources.LAYERS['heights']
LIFT_REACH = 6.0  # m: a point takes the lift of the line route this near (src/world.js liftAt)


SMOOTH_CLAMP = 0.10   # m: the most the smoother may move a height; the band rule then applies around the smoothed height
SMOOTH_JUNCTION = (20.0, 0.01)  # m, m: this near a junction it may move a height only this far. Moved 10 cm, a through track left the
                                # track crossing it to meet that in a bend (19.4 cm of coupling step at Malostranské náměstí; 11.5 cm
                                # with this, for 0.6 degrees per km more coupler travel)
GROUND_BAND = 0.05   # m: the curve stays within this of the ground where an answer has the tracks follow it
DROP_MAX = 12     # rounds: where an answer holds the radius and discards the outliers, one point dropped per round


class LiftMap:
    """The rails' height over the bed at a point (the line data's `lift`, tools/track_styles.py): that of the nearest
    line route within LIFT_REACH m, else 0 (panels, the default style)."""

    def __init__(self, root=ROOT):
        self.items = []
        for p in sorted((root / 'data').glob('line*.json')):
            if not p.stem[4:].isdigit():
                continue
            d = json.loads(p.read_text(encoding='utf-8'))
            if d.get('lift') and len(d.get('path') or []) > 1:
                self.items.append((LineString([q[:2] for q in d['path']]), d['lift']))
        self.tree = shapely.STRtree([g for g, _ in self.items]) if self.items else None

    def at(self, xy):
        if self.tree is None or xy is None:
            return 0.0
        p, best = Point(xy), None
        for k in self.tree.query(p, predicate='dwithin', distance=LIFT_REACH):
            g, L = self.items[int(k)]
            d = g.distance(p)
            if best is None or d < best[0]:
                best = (d, g.project(p), L)
        if best is None:
            return 0.0
        _, s, L = best
        v, f = L['v'], max(0.0, min(len(L['v']) - 1.001, s / L['step']))
        i = int(f)
        return (v[i] + (v[i + 1] - v[i]) * (f - i)) * L['unit']


def surface_fill(chs, lifts):
    """Where a chain is held for longer than HELD_GAP (no source the staging could choose, the curve does not bridge
    it), the surface at the axis plus the style's lift (#480; the page's surface profile until then): the lidar ground
    off structures, the survey's deck on one (the lidar lies under it). Weighted as a height, so the solver curves into
    it; source 'surface'. Not where the lidar is steeper than any track (MAX_GRADE: Petřín's funicular, held its whole
    length, took 2-3 m steps on the hill). Returns the metres filled and those left without a surface (a structure
    without a deck)."""
    filled = left = 0.0
    for c in chs:
        bins = sorted((x for x in c.bins if x['xy']), key=lambda x: x['s'])
        run = []
        for x in bins + [None]:
            if x is not None and x.get('z') is None and (not run or x['s'] - run[-1]['s'] <= 2 * BIN + 1e-6):
                run.append(x)
                continue
            steep = any(a.get('terrain') is not None and b.get('terrain') is not None
                        and abs(b['terrain'] - a['terrain']) > MAX_GRADE * (b['s'] - a['s']) for a, b in zip(run, run[1:]))
            if run and run[-1]['s'] - run[0]['s'] > HELD_GAP and not steep:
                for h in run:
                    on_structure = bool(STRUCTURE_FLAGS & set(h.get('flags') or ()))
                    z = h.get('survey') if on_structure else (None if h.get('terrain') is None else h['terrain'] + lifts.at(h['xy']))
                    if z is None:
                        left += BIN
                        continue
                    h['z'], h['w'], h['src'] = round(z, 3), 1.0, 'surface'
                    filled += BIN
            run = [x] if x is not None and x.get('z') is None else []
    return filled, left


def follow_curve(s, z, rmin, tol, weight, fit, place):
    """The curve that follows the data at a place the floor cannot fit: the radius gives way within RELAX_REACH of the
    points still outside the band, below the floor, until the band is met (the review card's 'follow the data')."""
    lo, hi = s[place[0]] - RELAX_REACH, s[place[-1]] + RELAX_REACH
    rm = list(rmin)
    for _ in range(2 * RELAX_STEPS):
        res = banded_profile(s, z, rm, tol, weight)
        miss = [i for i, e in enumerate(res['excess']) if e > fit[i] and lo <= s[i] <= hi]
        if not miss:
            break
        rm = [max(v * RELAX_STEP, MIN_RADIUS) if any(abs(si - s[i]) <= RELAX_REACH for i in miss) else v for si, v in zip(s, rm)]
    return res


def review_place(c, kind, s0, s1, held, final, factor):
    """A place where the radius gave way (or an answer held it): the stretch, the curve held to the design radius,
    the final one and the staged heights, for the radius review (reports/review/track-radius.json)."""
    terrain = {round(b['s'], 1): b['terrain'] for b in c.bins}
    curve = lambda runs: [(si, zi) for run in runs for si, zi in zip(run['s'], run['z']) if s0 <= si <= s1]
    data = [(si, raw, src) for run in final for si, raw, src in zip(run['s'], run['raw'], run['src']) if s0 <= si <= s1]
    return {'kind': kind, 's0': s0, 's1': s1, 'factor': factor, 'held': curve(held), 'final': curve(final),
            'data': [(si, raw, src, terrain.get(round(si, 1)), tuple(c.line.interpolate(si).coords[0])) for si, raw, src in data]}


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


def at_true_places(series, line):
    """Each bin's height read at the bin's centre from the samples at their true places along the chain: a sample lies up
    to 2.4 m from its bin's centre (rms 1.2 m), which on a 4 % grade was a height error of up to 10 cm, and half of
    what the rails waved by (#358). A sample further from its centre than the bin is the chain passing it twice: it
    stays. A bin with no sample within 2 BIN either side keeps its own height."""
    pts = []
    for x in series:
        if x['z'] is not None and x['xy'] is not None:
            t = line.project(Point(x['xy']))
            pts.append((t if abs(t - x['s']) <= BIN else x['s'], x['z']))
    pts.sort()
    ts, zs = [], []
    for t, z in pts:
        if not ts or t - ts[-1] > 1e-6:
            ts.append(t)
            zs.append(z)
    if len(ts) < 2:
        return
    for x in series:
        if x['z'] is None:
            continue
        k = bisect.bisect_left(ts, x['s'])
        a, b = max(0, k - 1), min(len(ts) - 1, k)
        if a == b or x['s'] - ts[a] > 2 * BIN or ts[b] - x['s'] > 2 * BIN:
            continue
        x['z'] = zs[a] + (zs[b] - zs[a]) * (x['s'] - ts[a]) / (ts[b] - ts[a])


def other_heights(samples):
    """A bin's archive and survey heights, each the median of what its samples offer (None: none): what an answer can
    choose instead of the height staged (tools/import_track_heights.py keeps them as candidates)."""
    good = lambda v: isinstance(v, (int, float)) and v > 100
    arch, surv = [], []
    for h in samples:
        paved = (h.get('construction') or {}).get('kind') == 'paved'
        for c in h.get('candidates', ()):
            if c.get('excluded') or not good(c.get('z')):
                continue
            if c['dataset'] == 'archive':
                arch.append(c['z'])
            elif c['dataset'] in ('deck', 'survey') and c.get('inside') and paved and c.get('class') in ('deck', 'tram', 'road', 'paved', 'parking'):
                surv.append(c['z'])
    pick = lambda v: sorted(v)[len(v) // 2] if v else None
    return pick(arch), pick(surv)


def smooth_heights(chs):
    """The smoother in front of the band rule (#358): each run of heights, moved at most SMOOTH_CLAMP, nearly not at all near a
    junction, where the tracks must meet. A run shorter than two of its wavelengths stays: it has no waves to tell from its
    shape (a 91 m side track on line 17 fell 14 cm)."""
    diverge, clusters, crossings = junctions(chs)
    near = defaultdict(list)
    for d in diverge:
        for i, t in (d['end'], d['through']):
            near[i].append(t)
    for g in clusters + crossings:
        for i, t in g['members']:
            near[i].append(t)
    reach, small = SMOOTH_JUNCTION
    for k, c in enumerate(chs):
        for run in height_runs(c):
            if c.bins[run[-1]]['s'] - c.bins[run[0]]['s'] < 2 * SMOOTH_WAVELENGTH:
                continue
            for i, v in zip(run, smooth_line(c, run)):
                x = c.bins[i]
                most = small if any(abs(x['s'] - t) <= reach for t in near[k]) else SMOOTH_CLAMP
                x['z'] = max(x['z'] - most, min(x['z'] + most, float(v)))


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
            archive, survey = other_heights(v)
            series.append({'archive': archive, 'survey': survey, 's': min((b + .5) * BIN, cum), 'z': h['z'] if sel else None, 'w': 1.0 if sel else 0.0,
                           'src': CODE.get((h.get('height_source') or {}).get('dataset')) if sel else None,
                           'kind': kinds.most_common(1)[0][0], 'terrain': h.get('terrain_z'), 'xy': h['xy'],
                           'flags': sorted({f for x in v for f in x.get('review_flags', [])})})
        answered_source(series)
        track = Chain(xy, series)
        at_true_places(series, track.line)
        out.append(track)
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
    runs = runs_of(c, pins)
    c.runs, c.steps, c.review, c.dropped, c.apart = [], [], [], [], []
    for run in runs:
        add_run(c, solve_run(c, run, r))


def runs_of(c, pins):
    """The chain's series with its pins {t: z}, cut into the runs solve_run solves (c.held: the stretches held out)."""
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
    return runs


def add_run(c, got):
    """A run's results (solve_run) into its chain, in the order of its runs."""
    run, steps, review, dropped, apart = got
    c.runs.append(run)
    c.steps += steps
    c.review += review
    c.dropped += dropped
    c.apart += apart


def solve_run(c, run, r):
    """One run of a chain's series (solve): its heights and what it found, (run, steps, review places, points dropped, pins
    held apart). A run reads only its own points, the chain's bins, switches and line, and the answers: the runs of a
    chain are independent of each other (#516)."""
    found_steps, found_review, found_dropped, found_apart = [], [], [], []
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
    free_w = [0.0 if x.get('pin') else w for x, w in zip(run, weight)]
    # (a run of pins alone, the meeting points on a few metres of track, has nothing to find)
    rob = vertical_profile(s, zf, rmin0, weight=free_w)['z'] if sum(w > 0 for w in free_w) >= 2 else list(zf)
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
    # (where an answer has the tracks follow the ground, its heights are the ground: none of them goes)
    out = [g for g in groups if not any(run[i].get('ground') for i in g) and (len(g) <= LONE or steep(g))]
    dropped = {i for g in out for i in g}
    zone = lambda si: any(a <= si <= b for a, b in c.switch)
    tol = [PIN_TOL if x.get('pin') else None if (not x['w'] or i in dropped) else GROUND_BAND if x.get('ground') is True
           else JUNCTION_BAND if zone(x['s']) else BAND for i, x in enumerate(run)]
    weight = [0.0 if i in dropped else w for i, w in enumerate(weight)]
    # (where an answer drops the heights between a junction's switches, they go: the tracks meet on the curve around them;
    # the user, Malovanka, 2026-11-07: "if you ignore any height between the switches and fit the best vertical radius")
    for a in ha.IGNORE_ANSWERS:
        near = [(lo, hi) for lo, hi in c.switch if a['ignore'] == 'switches'
                and math.dist(c.line.interpolate((lo + hi) / 2).coords[0], a['xy']) <= a['reach']]
        if near:
            lo, hi = min(z[0] for z in near), max(z[1] for z in near)
            for i, x in enumerate(run):
                if lo <= x['s'] <= hi and not x.get('pin') and tol[i] is not None:
                    tol[i], weight[i] = None, HOLD_WEIGHT
    # the band rule: within BAND of the staged heights at the design radius, else the radius gives way where the
    # band is missed, down to the floor (an answer to hold the radius keeps the design radius), and where the floor
    # cannot meet the band either, the band gives way and the place goes to the user's review
    rmin = list(rmin0)
    fit = [PIN_FIT if x.get('pin') else FIT for x in run]
    over = lambda r_: [i for i, e in enumerate(r_['excess']) if e > fit[i]]
    xy_of = lambda j: run[j]['xy'] or tuple(c.line.interpolate(s[j]).coords[0])
    floor = r.get('min', MIN_RADIUS)
    # how far the radius may give way at each point: below the floor in an area that follows the ground, down to the area's
    # own limit (the user's word), and at most down to `least` anywhere
    grounds = [ground_at(xy_of(j), BLEND_REACH) for j in range(len(s))]
    least = [g['radius_min'] if g else MIN_RADIUS for g in grounds]
    lowest = [g['radius_min'] if g else floor for g in grounds]
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
                a = answer_at([xy_of(j) for j in group])
                free = [j for j in group if not run[j].get('pin')]
                if a is None:
                    bad += group
                    if below_floor([xy_of(j) for j in group]):
                        lowest = [lt if any(abs(si - s[j]) <= RELAX_REACH for j in group) else v for si, v, lt in zip(s, lowest, least)]
                elif a.get('outliers') == 'drop' and free:
                    worst.append(max(free, key=lambda j: res['excess'][j]))
            group = [i] if i is not None else []
        if not bad and not worst:
            break
        for j in worst:
            tol[j], weight[j] = None, 0.0
            found_dropped.append(xy_of(j))
        drops += bool(worst)
        if bad:
            near = lambda si: any(abs(si - s[i]) <= RELAX_REACH for i in bad)
            new = [max(v * RELAX_STEP, lo) if near(si) and v > lo else v for si, v, lo in zip(s, rmin, lowest)]
            if new == rmin and not worst:
                break  # (at the floor: nothing left to give way)
            relaxed += new != rmin
            rmin = new
        res = banded_profile(s, zf, rmin, tol, weight)
    # (the floor holds where the band cannot: the band gives way around the points it misses, and the curve at the
    # radius lies as near them as it can; how far it stays from them is the review's question)
    tol0, released = list(tol), set()
    for _ in range(RELEASE_ROUNDS):
        miss = [i for i in over(res) if not run[i].get('pin')]
        if not miss:
            break
        released |= set(miss)
        tol = [None if t is not None and not run[i].get('pin') and min(abs(s[i] - s[j]) for j in miss) <= RELEASE else t
               for i, t in enumerate(tol)]
        res = banded_profile(s, zf, rmin, tol, weight)
    # (where even that cannot meet a pin, the rails join first: the band gives way within 15 m of it, then the radius
    # gives way near it down to the floor, and below it only where nothing else joins the rails)
    apart = [i for i in over(res) if run[i].get('pin')]
    below, held_apart = set(), None
    if apart:
        tol = [None if t is not None and not run[i].get('pin') and min(abs(s[i] - s[j]) for j in apart) <= 15 else t
               for i, t in enumerate(tol)]
        res = banded_profile(s, zf, rmin, tol, weight)
        # (an answer holds the radius against the band, not against the rails joining: where they still miss, the
        # radius gives way near the pin as it would without the answer; 24 junctions 1-2.5 cm apart, 2026-11-04)
        for to_floor in (True, False):
            if not to_floor and apart and answer_at([xy_of(i) for i in apart], (HOLD,)):
                # (an answer holds the floor here: the radius stays, and the tracks meet half way, assemble; the user,
                # 2026-11-07: "best fit to 500m limit even at the price of larger height difference from source")
                found_apart += [(s[i], res['z'][i]) for i in apart]
                break
            for _ in range(RELAX_STEPS):
                apart = [i for i in over(res) if run[i].get('pin')]
                if not apart:
                    break
                near = lambda si: any(abs(si - s[i]) <= RELAX_REACH for i in apart)
                new = [max(v * RELAX_STEP, lo if to_floor else lt) if near(si) else v for si, v, lo, lt in zip(s, rmin, lowest, least)]
                if new == rmin:
                    break
                if not to_floor:
                    if held_apart is None:
                        held_apart = res
                    below |= set(apart)
                rmin = new
                res = banded_profile(s, zf, rmin, tol, weight)
    # (the solver meets its pins first: two pins metres apart that need a tighter curve get one without missing either, so
    # every curve under the floor where no answer allows it is a place for review too: 4 of the 5 places under 500 m on the
    # lines were such, at Malostranské náměstí, Trojská and Královka)
    tight = implied_radii(s, res['z'])
    tight_at = {i + 1 for i, v in enumerate(tight) if v < floor * TIGHT and lowest[i + 1] >= floor}
    pins_near = [j for j in range(len(s)) if run[j].get('pin') and tight_at and min(abs(s[j] - s[i]) for i in tight_at) <= RELAX_REACH]
    if pins_near and answer_at([xy_of(i) for i in tight_at], (HOLD,)):
        # (an answer holds the floor here too: solved at it with the pins near weighed like data, and the tracks they come
        # from meet that half way, assemble: Královka, Malovanka, Strossmayerovo náměstí, where several tracks' meeting
        # points metres apart needed 351-472 m)
        held = banded_profile(s, zf, [max(v, floor) for v in rmin], [MEET_GIVE if j in pins_near else t for j, t in enumerate(tol)],
                              weight)
        # (only where the pins giving MEET_GIVE let the floor hold: weighed like data, the pins went 26 cm and the tracks
        # pulled after them made 10 % grades at Malovanka)
        if min(implied_radii(s, held['z']), default=math.inf) >= floor * TIGHT:
            found_apart += [(s[j], held['z'][j]) for j in pins_near]
            tight_at = set()
    below |= tight_at
    raw = [None if x.get('pin') else x.get('staged', x['z']) for x in run]  # (before the smoother)
    # (for review: where the floor cannot meet the band, or the rails meet only below it; a place the band missed at
    # the design radius that an answer settled is kept too, so that the answers met can be counted)
    cand = sorted({i for i, e in enumerate(first['excess']) if e > FIT} | released | below)
    place = []
    for i in cand + [None]:
        if i is not None and (not place or s[i] - s[place[-1]] <= 50):
            place.append(i)
            continue
        if place:
            held_up = any(j in released or j in below for j in place)  # (the floor does not fit here)
            answered = answer_at([xy_of(j) for j in place], (HOLD, FOLLOW))
            if held_up or answered:
                gone = [abs(res['z'][j] - zf[j]) - tol0[j] for j in place if tol0[j] is not None]
                big = max(place, key=lambda j: abs(res['z'][j] - zf[j]))
                junction = bool(below & set(place)) or any(x.get('pin') and min(abs(x['s'] - s[j]) for j in place) <= 10 for x in run)
                tight_here = bool(below & set(place))
                follow = (held_apart or res) if tight_here else follow_curve(s, zf, rmin, tol0, weight, fit, place) if held_up else res
                shown = (follow, res) if tight_here else (res, follow)  # (held at the floor, followed below it)
                rec = review_place(c, 'junction' if junction else 'band', s[place[0]] - 60, s[place[-1]] + 60,
                                   [{'s': s, 'z': shown[0]['z']}], [{'s': s, 'z': shown[1]['z'], 'raw': raw,
                                   'src': [x['src'] for x in run]}],
                                   round(min(a / b for a, b in zip(rmin, rmin0)), 2))
                rec['at'] = tuple(xy_of(big))
                pins_here = [j for j in place if run[j].get('pin')] or [j for j in range(len(s)) if run[j].get('pin')
                                                                         and min(abs(s[j] - s[i]) for i in place) <= 15]
                if tight_here:  # (how far apart the rails stay at the floor; 0 where the solver bent below it to meet them)
                    rec['excess'] = max((abs(held_apart['z'][j] - zf[j]) for j in pins_here), default=0.0) if held_apart else 0.0
                else:
                    rec['excess'] = max(gone, default=0.0) if held_up else max(first['excess'][j] for j in place)
                rec['fits'] = not held_up  # (the floor meets the band here)
                rec['below'] = tight_here  # (the rails meet only below the floor)
                rec['radius'] = min(implied_radii(s, res['z'])[max(0, place[0] - 3):place[-1] + 2], default=math.inf)
                found_review.append(rec)
        place = [i] if i is not None else []
    # steps: what the band did not hold, and anything still outside it (the band given way included), by cause
    left = sorted(set(over(res)) | released)
    left = [left] if left else []
    for g in out + [g for g in left if g]:
        pts = [run[i] for i in g]
        held = [x for x in run if x['w'] == 0 and min(abs(x['s'] - p['s']) for p in pts) <= 20]
        big = max(g, key=lambda i: abs(res['z'][i] - run[i]['z']))
        if abs(res['z'][big] - run[big]['z']) <= MISS:
            continue
        found_steps.append({'cause': cause([{'src': {'dtmp': 'archive', 'zps': 'survey'}.get(p['src'], p['src']),
                                         'z': p['z'], 'terrain': p['terrain']} for p in pts],
                                       [run[i]['z'] - res['z'][i] for i in g],
                                       any(STRUCTURE & set(x['flags']) for x in held)),
                        'largest_m': round(run[big]['z'] - res['z'][big], 2), 'points': len(g),
                        'xy': run[big]['xy'], 'flags': sorted({f for p in pts for f in p['flags']})})
    step_s = {s[i] for g in out + left for i in g if abs(res['z'][i] - zf[i]) > MISS}  # (steps as #190 counts them)
    found_run = {'s': s, 'z': res['z'], 'raw': raw, 'src': [('curve' if x['w'] == 0 else x['src']) for x in run],
                   'step': [si in step_s for si in s], 'min_radius': res['min_radius']}
    # (a pin's source is that of its neighbours: the junction's height comes from the through track)
    src = found_run['src']
    for i, v in enumerate(src):
        if v is None:
            src[i] = next((src[j] for j in sorted(range(len(src)), key=lambda j: abs(j - i)) if src[j]), 'curve')
    return found_run, found_steps, found_review, found_dropped, found_apart


POOL = 16  # chains: fewer are solved in this process (a worker takes ~2 s to start: the network has ~600)


ANSWERS = ('RADIUS_ANSWERS', 'STEP_ANSWERS', 'IGNORE_ANSWERS', 'GROUND_ANSWERS', 'FLOOR_SINCE')  # (what ha.load sets)


def _worker(answers, chs=None):
    """A worker process: height_answers' globals as this process has them (solve reads the answers there), and for the
    lines' writing the chains and their lookup."""
    global _CHS, _LOOKUP
    for k, v in answers.items():
        setattr(ha, k, v)
    if chs is not None:
        _CHS, _LOOKUP = chs, Lookup(chs)


def _write(line):
    return write_line(line, _LOOKUP, _CHS)[2]


def _run(i, run, r):
    return solve_run(_CHS[i], run, r)


def _key(run):
    """A run's points as they are, for the results kept (in_turn)."""
    import hashlib
    import pickle
    return hashlib.sha1(pickle.dumps(run, protocol=pickle.HIGHEST_PROTOCOL)).digest()


BLAS = 4  # numpy's BLAS threads per worker: a long chain's solve on one thread took twice as long, and the longest set the pace


def _pool(n, chs=None):
    """Worker processes, n at most: a core per BLAS thread, 1 GB apiece of free memory (tools/sysinfo.py). Their numpy runs
    BLAS threads as this process's do, when rebuild.py gave it 4 (the environment is read at their start, #511)."""
    from concurrent.futures import ProcessPoolExecutor
    import sysinfo
    os.environ['OPENBLAS_NUM_THREADS'] = str(BLAS)
    return ProcessPoolExecutor(min(n, sysinfo.workers(1.0, most=max(1, (os.cpu_count() or 4) // BLAS))), initializer=_worker,
                               initargs=({k: getattr(ha, k) for k in ANSWERS}, chs))


def presolve(chs, order, r, pool=None, kept=None):
    """Every chain's first solve, without pins: each reads only its own chain, so they run side by side in the workers,
    the longest first (one process solved a line's chains in 192 s, these first solves about half of it, #511).
    {chain: (runs, held, steps, review, dropped, apart)}."""
    in_turn(chs, order, {i: () for i in order}, lambda i: {}, r, pool, kept)
    return {i: (chs[i].runs, chs[i].held, chs[i].steps, chs[i].review, chs[i].dropped, chs[i].apart) for i in order}


def in_turn(chs, order, waits, prepare, r, pool, kept=None):
    """Each chain of `order` once the chains it waits for (before it in the order) are done: prepare(i) gives its pins, or
    None where it is not solved (again). A chain's runs are solved in the pool when there is one, side by side with the
    others' whose waits are over (the longest chain's first solve set the pace of all the first solves, ~20 s of 26, #516);
    without one, here, strictly in the order. A run whose points are as at an earlier solve of its chain (`kept`: {chain:
    {run's key: what it found}}) keeps what it found then: the rounds of meeting half way move a few pins of a chain and
    solved all its runs again (#516)."""
    import copy
    kept = {} if kept is None else kept
    pos = {i: n for n, i in enumerate(order)}
    after, left = defaultdict(list), {}
    for i in order:
        left[i] = len(waits[i])
        for j in waits[i]:
            after[j].append(i)
    ready, running, found, keys = [pos[i] for i in order if not left[i]], {}, {}, {}
    heapq.heapify(ready)

    def finish(i):
        for k in after[i]:
            left[k] -= 1
            if not left[k]:
                heapq.heappush(ready, pos[k])

    def done(i):
        c, mine = chs[i], kept.setdefault(i, {})
        c.runs, c.steps, c.review, c.dropped, c.apart = [], [], [], [], []
        for k, got in zip(keys.pop(i), found.pop(i)):
            mine[k] = copy.deepcopy(got)
            add_run(c, got)
        finish(i)

    while ready or running:
        while ready:
            i = order[heapq.heappop(ready)]
            pins = prepare(i)
            if pins is None:
                finish(i)
                continue
            runs = runs_of(chs[i], pins)
            keys[i] = [_key(run) for run in runs]
            mine = kept.get(i, {})
            found[i] = [copy.deepcopy(mine[k]) if k in mine else None for k in keys[i]]
            todo = [n for n, got in enumerate(found[i]) if got is None]
            if pool is None:
                for n in todo:
                    found[i][n] = solve_run(chs[i], runs[n], r)
                done(i)
            elif not todo:
                done(i)
            else:
                for n in sorted(todo, key=lambda n: -len(runs[n])):
                    running[pool.submit(_run, i, runs[n], r)] = (i, n)
        if running:
            over, _ = wait(running, return_when=FIRST_COMPLETED)
            for f in over:
                i, n = running.pop(f)
                found[i][n] = f.result()
                if all(got is not None for got in found[i]):
                    done(i)


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
    pinned, used, apart, t0 = 0, [], {}, time.time()
    order = sorted(range(len(chs)), key=lambda i: -chs[i].length)
    pool = _pool(len(order), chs) if len(order) >= POOL else None
    kept = {}  # (each chain's runs and what they found: a run as it was at an earlier solve keeps it, in_turn)
    unpinned = presolve(chs, order, r, pool, kept)
    print(f'  every chain solved without pins, {time.time() - t0:.0f} s', flush=True)
    pos = {i: n for n, i in enumerate(order)}

    def pin(i):
        """Chain i's pins from the chains before it in the order that it meets, as they are final: (pins, its entries of
        `used`, the crossings it lists apart)."""
        c = chs[i]
        c.runs, c.held, c.steps, c.review, c.dropped, c.apart = unpinned[i]
        cands, gone = [], []
        for ti, j, tj, kind in meets[i]:
            if pos[j] > pos[i]:
                continue
            zj, zi = chs[j].z_at(tj)[0], c.z_at(ti)[0]
            if zj is None:
                continue
            if kind == 'cross' and (zi is None or abs(zi - zj) > CROSS):
                if zi is not None:  # (one track over the other, or one of them wrong there: listed)
                    gone.append(((min(i, j), max(i, j), round(ti), round(tj)), (abs(zi - zj), c.line.interpolate(ti))))
                continue
            cands.append((ti, kind in ('ends', 'near'), -chs[j].length, zj, j, tj))
        # (several at one spot: a fork's or crossing's own point first, then the longer track; at a fork on a 4 %
        # grade the end of a third track 0.5 m off gave 4 cm more)
        pins, mine = {}, []
        for x in sorted(cands, key=lambda x: (x[1], x[2])):
            if all(abs(x[0] - t) > PIN_MERGE for t in pins):
                pins[x[0]] = x[3]
                mine.append((i, x[0], x[4], x[5]))
        return pins, mine, gone

    got, done = {}, [0]

    def pinned_pass(i):
        got[i] = pin(i)
        done[0] += 1
        if done[0] % 200 == 0:
            print(f'  {done[0]} of {len(chs)} chains solved ({sum(bool(g[0]) for g in got.values())} pinned), '
                  f'{time.time() - t0:.0f} s', flush=True)
        return got[i][0] or None

    in_turn(chs, order, {i: {j for _, j, _, _ in meets[i] if pos[j] < pos[i]} for i in order}, pinned_pass, r, pool, kept)
    last = {}
    for i in order:
        pins, mine, gone = got[i]
        last[i] = pins
        used += mine
        pinned += bool(pins)
        apart.update(gone)
    # where an answer holds the floor at a junction whose rails meet only below it (solve: c.apart), the tracks meet half
    # way: the track the chain is pinned to there takes the middle of their heights as a pin of its own, and every chain
    # whose pins moved is solved again in the order above, until they meet (each round halves what is left)
    by_chain, extra, met = defaultdict(list), defaultdict(dict), [0]
    for u in used:
        by_chain[u[0]].append(u)

    def meet(i):
        p = {ti: chs[j].z_at(tj)[0] for _, ti, j, tj in by_chain[i]}
        p = {t: z for t, z in p.items() if z is not None} | extra[i]
        if p.keys() != last[i].keys() or any(abs(p[t] - last[i][t]) > 0.001 for t in p):
            last[i] = p
            met[0] += 1
            return p
        return None

    gaps = []
    for _ in range(MEET_ROUNDS):
        gap = 0.0
        for i in order:
            for t, z in chs[i].apart:
                for _, ti, j, tj in by_chain[i]:
                    zj = chs[j].z_at(tj)[0]
                    if abs(ti - t) <= PIN_MERGE and zj is not None and abs(zj - z) > PIN_TOL:
                        extra[j][tj], gap = (zj + z) / 2, max(gap, abs(zj - z))
        gaps.append(round(gap, 4))
        if not gap:
            break
        # (a chain's pins come from the chains it is pinned to, before it in the order: it waits for them this round)
        in_turn(chs, order, {i: {u[2] for u in by_chain[i]} for i in order}, meet, r, pool, kept)
    if pool is not None:
        pool.shutdown()
    met = met[0]
    if met:
        print(f'junctions held at the floor: the tracks met half way, {met} chains solved again; the widest gap by round, m: '
              f'{gaps}', flush=True)
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
        """(heights, sources) every `step` m along a polyline, and its length. GEOS answers for all the samples at once
        (the same operations; one call each was most of writing a line, #516), the arithmetic after it as it was."""
        line = LineString(pts)
        L = line.length
        n = max(1, math.ceil(L / step - 1e-9))
        ks = np.arange(n + 1) * step
        # (the last sample sits at n * step, past the line's end along its chain: the game reads every sample
        # at k * step, and the end read there stood 4 cm off on an 8 % grade)
        s = np.minimum(L, ks)
        p = shapely.line_interpolate_point(line, s)
        a, b = shapely.line_interpolate_point(line, np.maximum(0.0, s - 1)), shapely.line_interpolate_point(line, np.minimum(L, s + 1))
        ax, ay, bx, by = (shapely.get_x(a).tolist(), shapely.get_y(a).tolist(), shapely.get_x(b).tolist(),
                          shapely.get_y(b).tolist())
        k, j = self.tree.query(shapely.buffer(p, MATCH))
        lines = np.asarray([self.chs[int(x)].line for x in j], object)
        dist = shapely.distance(lines, p[k])
        ok = dist <= MATCH
        k, j, lines, dist = k[ok], j[ok], lines[ok], dist[ok]
        t = shapely.line_locate_point(lines, p[k])
        length = np.asarray([self.chs[int(x)].length for x in j], float)
        c0 = shapely.line_interpolate_point(lines, np.maximum(0.0, t - 1))  # (Chain.direction, at once)
        c1 = shapely.line_interpolate_point(lines, np.minimum(length, t + 1))
        cands = [[] for _ in range(n + 1)]
        for i, jj, dd, tt, x0, y0, x1, y1 in zip(k.tolist(), j.tolist(), dist.tolist(), t.tolist(),
                                                 shapely.get_x(c0).tolist(), shapely.get_y(c0).tolist(),
                                                 shapely.get_x(c1).tolist(), shapely.get_y(c1).tolist()):
            d = math.hypot(bx[i] - ax[i], by[i] - ay[i]) or 1
            ux, uy = (bx[i] - ax[i]) / d, (by[i] - ay[i]) / d
            e = math.hypot(x1 - x0, y1 - y0) or 1
            cos = ux * ((x1 - x0) / e) + uy * ((y1 - y0) / e)
            if abs(cos) >= math.cos(math.radians(ANGLE)):
                over = i * step - min(L, i * step)
                cands[i].append((dd, jj, tt + (over if cos > 0 else -over)))
        zs, srcs = [], []
        for c in cands:
            acc = wsum = 0.0
            src = None
            for dd, jj, tt in sorted(c):
                z, sj = self.chs[jj].z_at(tt)
                if z is None:
                    continue
                w = (1 - dd / MATCH) / (dd + .02) ** 2
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
    within ANGLE, ACROSS_MIN-ACROSS_MAX m off; the game's cross-section of the street between them (heightAt). Beside
    means its nearest point lies within ACROSS_MAX: past the opposite route's end the nearest point is its end, metres
    behind but 3 m to the side (#344: line 23 near Těšnov kept the end's height 52 m on, 0.45 m over the track beside
    ours, and trackLevels flagged that track)."""
    a, b = LineString(path), LineString(back)
    n = max(1, math.ceil(a.length / step - 1e-9))
    off, zs = [], []
    # (GEOS for every sample at once, the arithmetic after it as it was, #516)
    s = np.minimum(a.length, np.arange(n + 1) * step)
    P = shapely.line_interpolate_point(a, s)
    U0, U1 = shapely.line_interpolate_point(a, np.maximum(0.0, s - 1)), shapely.line_interpolate_point(a, np.minimum(a.length, s + 1))
    T = shapely.line_locate_point(b, P)
    Q = shapely.line_interpolate_point(b, T)
    V0, V1 = shapely.line_interpolate_point(b, np.maximum(0.0, T - 1)), shapely.line_interpolate_point(b, np.minimum(b.length, T + 1))
    xy = lambda g: zip(shapely.get_x(g).tolist(), shapely.get_y(g).tolist())  # noqa: E731
    for (px, py), (u0x, u0y), (u1x, u1y), t, (qx, qy), (v0x, v0y), (v1x, v1y), pq in zip(
            xy(P), xy(U0), xy(U1), T.tolist(), xy(Q), xy(V0), xy(V1), shapely.distance(P, Q).tolist()):
        d = math.hypot(u1x - u0x, u1y - u0y) or 1
        ux, uy = (u1x - u0x) / d, (u1y - u0y) / d
        e = math.hypot(v1x - v0x, v1y - v0y) or 1
        lat = (qy - py) * ux - (qx - px) * uy
        i = min(int(t / step), len(back_z) - 2)
        z0, z1 = back_z[i], back_z[i + 1]
        if (not ACROSS_MIN <= abs(lat) <= ACROSS_MAX or pq > ACROSS_MAX or z0 is None or z1 is None
                or abs(ux * (v1x - v0x) + uy * (v1y - v0y)) / e < math.cos(math.radians(ANGLE))):
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
        bins = [(s, raw) for run in c.runs if not any(run['step']) for s, raw in zip(run['s'], run['raw']) if raw is not None]
        if not bins:
            continue
        p = shapely.line_interpolate_point(c.line, np.asarray([s for s, _ in bins], float))  # (at once, #516)
        near = shapely.distance(line_, p) <= .3
        for (_, raw), at in zip([x for x, ok in zip(bins, near.tolist()) if ok], shapely.line_locate_point(line_, p[near]).tolist()):
            out.append([round(at, 1), round(raw, 3)])
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


class Surface:
    """The surface at the axis plus the style's lift, where no chain has a height (#480): the IPR lidar
    (tools/import_track_heights.py Terrain), read on first use."""

    def __init__(self, lifts):
        self.lifts, self.terrain = lifts, None

    def __call__(self, xy):
        if self.terrain is None:
            from import_track_heights import Terrain
            self.terrain = Terrain()
        z = self.terrain([xy[0]], [xy[1]])[0]
        return None if z is None or z != z else z + self.lifts.at(xy)


def fill_gaps(pts, zs, srcs, surface, step=OUT_STEP):
    """Every sample without a height along a polyline (`zs` from Lookup.along) takes the surface, shifted to meet the
    heights on both sides of its run (linearly between them; at an end, the one side's): a track's end past its chain
    (line 9's depot tracks, 2-4 m; line 22's at Depo Hostivař, 33 m). Source 'surface'. Returns the metres filled."""
    line_, n, filled = LineString(pts), len(zs), 0
    k = 0
    while k < n:
        if zs[k] is not None:
            k += 1
            continue
        j = k
        while j + 1 < n and zs[j + 1] is None:
            j += 1
        def surf(i):
            p = line_.interpolate(min(line_.length, i * step))
            return surface((p.x, p.y))
        sf = [surf(i) for i in range(k, j + 1)]
        # (the shift at each side: the height there against the surface there, as the page's meetHeights did)
        ea = surf(k - 1) if k > 0 else None
        eb = surf(j + 1) if j + 1 < n else None
        if any(v is None for v in sf) or (k > 0 and ea is None) or (j + 1 < n and eb is None):
            k = j + 1
            continue
        a = zs[k - 1] - ea if k > 0 else None
        b = zs[j + 1] - eb if j + 1 < n else None
        for i, v in enumerate(sf):
            u = (i + 1) / (len(sf) + 1)
            shift = (a if b is None else b if a is None else a + (b - a) * u) if (a is not None or b is not None) else 0.0
            zs[k + i] = round(v + shift, 3)
            if srcs is not None:
                srcs[k + i] = 'surface'
            filled += step
        k = j + 1
    return filled


def write_line(line, lookup, chs):
    """The line's heights: path and pathBack every 2 m, each drawn track's `zs`, with provenance."""
    import sources
    from atomic import replacing
    dst = ROOT / 'data' / f'line{line}.json'
    data = json.loads(dst.read_text(encoding='utf-8'))
    heights, src_ranges, metres = {'step': OUT_STEP}, {}, Counter()
    surface = Surface(LiftMap())
    for key in ('path', 'pathBack'):
        if not data.get(key) or len(data[key]) < 2:
            continue
        zs, srcs, L = lookup.along([tuple(p[:2]) for p in data[key]])
        fill_gaps([tuple(p[:2]) for p in data[key]], zs, srcs, surface)
        heights[key] = zs
        src_ranges[key] = ranges(srcs)
        for a, b, v in src_ranges[key]:
            metres[v] += b - a
    heights['staged'] = {key: staged_along([tuple(p[:2]) for p in data[key]], lookup) for key in ('path', 'pathBack')
                         if heights.get(key)}
    if heights.get('path') and heights.get('pathBack'):
        heights['backOff'], heights['backZ'] = across([tuple(p[:2]) for p in data['path']],
                                                      [tuple(p[:2]) for p in data['pathBack']], heights['pathBack'])
    covered, track_filled = 0, 0.0
    for t in data['tracks']:
        t.pop('zs', None)
        if len(t['p']) < 2:
            continue
        zs, _, _ = lookup.along([tuple(p[:2]) for p in t['p']])
        track_filled += fill_gaps([tuple(p[:2]) for p in t['p']], zs, None, surface)
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
    # (no height may be missing: the page keeps no profile of its own since #480)
    nulls = (sum(z is None for key in ('path', 'pathBack') for z in heights.get(key, []))
             + sum(1 for t in data['tracks'] if len(t['p']) > 1 for z in (t.get('zs') or [None]) if z is None))
    print(f'line {line}: path and pathBack {total:.0f} m: ' + ', '.join(f'{k} {metres[k]:.0f} m' for k in LEVELS if metres[k])
          + f'; {covered} of {len(data["tracks"])} tracks with heights, {track_filled:.0f} m of them the surface; '
          + f'{nulls} samples without a height; wrote {dst.name}', flush=True)
    data['_nulls'] = nulls
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
    floor = radii()['min']
    for c in chs:
        for p in c.review:
            # (a 'follow' given before the floor no longer settles a place the floor cannot fit: it comes back)
            # (and a 'hold the radius' settles a place only where the build could hold it: where the rails meet only below the
            # floor, the answer did not apply, and the place comes back)
            if len(p['data']) >= 2 and not p['fits'] and not below_floor([p['at']]) and (p['below'] or not answer_at([p['at']], (HOLD,))):
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
        if not lines:
            # (off the lines' routes: the floor holds there as built and nobody drives it; the user, 2026-11-07:
            # "Generally tracks far from the main line aren't important")
            continue
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
        if any(p['below'] for p in places):
            r_final = min(p['radius'] for p in places)
            info = (f"junction: no curve of {floor:.0f} m joins the rails here" + (f": held at it, they stay up to {mag * 100:.0f} cm apart"
                    if mag > .005 else " (the tracks' meeting points, metres apart, need a tighter one)") + f". As built they join, at {r_final:.0f} m.")
            why = {HOLD: f"The rails must meet, so the radius still gives way at the junction ({r_final:.0f} m); add 'Discard the "
                         "outliers' in the note to drop the points it misses first and fit the rest at the floor.",
                   FOLLOW: f"Keeps the rails joined at {r_final:.0f} m, as built."}
        else:
            where = 'near a junction' if main['kind'] == 'junction' else 'on plain track'
            info = (f"{main['kind']}: {where}, no curve of {floor:.0f} m (the floor) stays within {BAND * 100:.0f} cm of the "
                    f"staged heights: held at it, the curve leaves that band by up to {mag * 100:.0f} cm (tightest "
                    f"{radius(main['held']):.0f} m). Following the data within the band, the radius would be {r_final:.0f} m.")
            why = {HOLD: f"Keeps {floor:.0f} m, as built: the rail stays up to {mag * 100:.0f} cm from the data here.",
                   FOLLOW: f"Lets the radius go below {floor:.0f} m here, to {r_final:.0f} m, to stay within {BAND * 100:.0f} cm of the data."}
        out.append({'kind': 'trackheight', 'id': ident, 'x': at[0], 'y': at[1], 'mag': round(mag, 3),
                    'status': 'review', 'place': [round(lat, 5), round(lon, 5)], 'lines_near': lines, 'info': info,
                    'decision': {'span_ids': [sp['id'] for sp in spans], 'structure': {'kind': main['kind']}, 'status': 'review'},
                    'spans': spans, 'options': [HOLD, FOLLOW, 'unsure'], 'answer_explanations': why,
                    'answer_previews': previews})
    out.sort(key=lambda f: -f['mag'])
    dst = ROOT / 'reports' / 'review' / 'track-radius.json'
    with replacing(dst, 'w', encoding='utf-8', newline='') as fh:
        json.dump({'schema': 1, 'snapshot': snapshot, 'issue': REVIEW_ISSUE,
                   'title': f'Track radius: where no curve of {floor:.0f} m fits the data',
                   'lines': sorted({n for f in out for n in f['lines_near']}, key=int), 'findings': out}, fh, ensure_ascii=False, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('lines', nargs='+')
    ap.add_argument('--staged', help='an import of this checkout (tools/import_track_heights.py --evidence ...)')
    ap.add_argument('--smooth', choices=('wh3', 'none'), default='wh3', help='the smoother in front of the band rule (#358)')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    truth = json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8'))
    ha.load(truth)
    t0 = time.time()
    took = lambda what: print(f'({what}: {time.time() - t0:.0f} s from the start)', flush=True)  # noqa: E731
    staged = staged_heights(args.staged)
    took('staged')
    chs = build_chains(staged)
    del staged
    ha.apply(chs)
    took('chains and answers')
    filled, left = surface_fill(chs, LiftMap())
    print(f'surface where a hold is too long to bridge: {filled:.0f} m filled, {left:.0f} m on a structure without a deck', flush=True)
    for c in chs:
        for x in c.bins:
            x['staged'] = x['z']
    if args.smooth == 'wh3':
        smooth_heights(chs)
    took('smoothed')
    summary = assemble(chs)
    took('assembled')
    from geo import Frame
    F = Frame()
    steps = [dict(s, lat=round(float(F.ll(*s['xy'])[0]), 5), lon=round(float(F.ll(*s['xy'])[1]), 5))
             for c in chs for s in c.steps if s['xy']]
    by = Counter(s['cause'] for s in steps)
    # (an archive the terrain check already distrusts is explained: 50.1130 N 14.3937 E, off the game's lines, swings
    # over 1 m beside a 60 m hold, and true places took its bins out of the dips)
    bad = [s for s in steps if abs(s['largest_m']) > BIG and s['cause'] not in ('di', 'dip', 'structure')
           and 'archive_terrain_height_disagreement' not in s['flags']]
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
    print(f"radius answers: {len(answered)} of {len(ha.RADIUS_ANSWERS)} met a place; "
          f"{sum(len(c.dropped) for c in chs)} points dropped where an answer discards the outliers")
    review = radius_review(chs, (ROOT / 'snapshots/CURRENT').read_text().strip())
    print(f"radius review: {len(review)} places ({sum(f['decision']['structure']['kind'] == 'junction' for f in review)} "
          f"at junctions), reports/review/track-radius.json")
    took('the radius review')
    lookup, report = Lookup(chs), {'network': {**summary, 'steps_by_cause': dict(by), 'unexplained_steps': bad,
                                               'moved_m': {'p50': q(.5), 'p90': q(.9), 'p99': q(.99)},
                                               'held_over_60m': held,
                                               'neighbour_snaps': [[round(float(v), 5) for v in F.ll(*xy)] + [z] for xy, z in ha.NEIGHBOUR_LOG],
                                               'held_settled': [[round(float(v), 5) for v in F.ll(*xy)] + [rule, z] for xy, rule, z in ha.LIDAR_LOG],
                                               'dropped_by_answers': [[round(float(v), 5) for v in F.ll(*xy)]
                                                                      for c in chs for xy in c.dropped]}, 'lines': {}}
    nulls = 0
    if len(args.lines) > 1:  # (each line's writing reads only the chains: side by side, ~30 s a line, #511)
        with _pool(len(args.lines), chs) as ex:
            written = list(ex.map(_write, args.lines))
    else:
        written = [write_line(line, lookup, chs)[2] for line in args.lines]
    took('written')
    for line, data in zip(args.lines, written):
        nulls += data.pop('_nulls')
        report['lines'][line] = line_report(line, chs, lookup, data, summary)
    took('reported')
    out = ROOT / 'reports' / 'line-heights.json'
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding='utf-8')
    print(f'report: {out.relative_to(ROOT)}')
    if nulls:
        print(f'{nulls} samples without a height: the game has no profile of its own to fill them (#480)')
    sys.exit(1 if bad or summary['over_1cm'] or nulls else 0)


if __name__ == '__main__':
    main()
