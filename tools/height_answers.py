# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user's answers on the track heights and the rules that apply them before the solve (tools/line_heights.py, #418).

The answers (data/truth.json trackHeights radiusAnswers and stepAnswers, `load`) are this module's globals, read here by
the rules and by line_heights' solver: whatever sets them (line_heights `main`, tools/track_steps.py, the tests in
tools/test_line_heights.py) sets them on this module. `apply` runs the rules on the chains' 5 m bins before the smoother;
`answer_at`, `ground_at` and `below_floor` answer the solver at a place; `staged_heights` stages the heights with the
user's reviewed spans as evidence.
"""
import bisect
import json
import math
from pathlib import Path
import sys

import shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_profile import BIN, ROOT, whittaker  # noqa: E402
from track_curve import geometry_fact  # noqa: E402

MIN_RADIUS = float(geometry_fact('min-radius-passenger'))  # m, 20: an area's radius limit where its answer names none
                                                           # (the same fact as line_heights' MIN_RADIUS)
FLOOR_SINCE = None  # the date of the floor (data/truth.json trackGeometry vertical-radius-min): a later 'follow the data'
                    # answer at a place lets the radius go below it there
MAX_GRADE = 0.09  # the steepest tram track (the game's grade limiter, src/terrain.js; Hercovka - Kobylisy 8-8.8 %)
SMOOTH_WAVELENGTH = 70.0  # m: the waves the smoother halves. What the two tracks of a street do not share ends about here
                         # (#358: at 32-64 m they share 0.67 cm rms and differ by 0.84; at 128-256 m they agree). 100 m
                         # gains 0.7 grade swings per km, and costs distance from the data and coupler travel
NEIGHBOUR_GAP = (2.0, 7.0)  # m: another track this far off, running parallel, is this track's neighbour
NEIGHBOUR_STEP = 0.20  # m: a height this far from its own smooth line is a step or a dip ...
NEIGHBOUR_CALM = 0.05  # m: ... if the neighbour's height there lies this near its own line
DROP_NOISE = 0.05     # m: where an answer discards outliers, a height this far from its smooth line goes
BLEND_NOISE = 0.02    # m: where an answer weights towards the survey, a height this far from its line, or tighter than 500 m
BLEND_REACH = 20.0    # m: the survey's pull fades in and out over this (per point it stepped: 7 -> 19 cm of coupling step)
TOWARD_AGREE, TOWARD_OTHER = 0.08, 0.5  # m: survey and lidar this near agree (else the lidar alone); a lidar this far from the
                                        # archive is another level (a deck, a wall), no evidence for the rail
NEIGHBOUR_LOG = []    # (xy, height) of the heights the last snap_to_neighbour moved: reports/line-heights.json
STEP_ANSWERS = []     # the user's answers on the step review: data/truth.json trackHeights.stepAnswers
STEP_REACH = 70.0     # m: the stretch a step card showed either side of its place
IGNORE_ANSWERS = []  # the user's answers that drop heights: data/truth.json radiusAnswers with `ignore` (load_ignore_answers)
STRETCH_NEAR = 1.0   # m: a height this near an `ignore` answer's stretch is on it
RADIUS_ANSWERS = []  # the user's answers on the radius review: [{'xy': city frame, 'answer': ...}] (data/truth.json)
HOLD, FOLLOW, GROUND = 'hold the radius', 'follow the data', 'follow the ground'
GROUND_ANSWERS = []  # the user's areas where the tracks take the lidar ground: radiusAnswers with `area` (load_ground_answers)
GROUND_OTHER = 1.5   # m: a lidar this far from the track's height there is another level (a wall, a roof), no evidence
ANSWER_REACH = 15.0  # m: an answer applies to the place where the radius would give way this near it


def load_radius_answers(truth):
    """data/truth.json trackHeights.radiusAnswers: a place (lat, lon) and the user's choice there."""
    from geo import Frame
    F = Frame()
    out = [{'xy': tuple(float(v) for v in F.xy(*a['place'])), 'answer': a['answer'], 'outliers': a.get('outliers'), 'date': a.get('date')}
           for a in (truth.get('trackHeights') or {}).get('radiusAnswers', []) if not a.get('area')]
    # (a step answer is the later word at its place: the radius answers within its reach give way to it)
    for a in load_step_answers(truth):
        if a['radius']:
            out = [o for o in out if math.dist(o['xy'], a['xy']) > a['reach']]
            out.append({'xy': a['xy'], 'answer': a['radius'], 'outliers': 'drop' if a['drop'] else None, 'reach': a['reach'], 'date': a['date']})
    return out


def load_ignore_answers(truth):
    """data/truth.json radiusAnswers with `ignore`: 'switches' drops the heights between a junction's switches within `reach`
    (solve), 'stretch' those of `sources` along `stretch` (answered_ignore). Read apart from the radius answers, which a step
    answer's radius overrides within its reach."""
    from geo import Frame
    F = Frame()
    xy = lambda p: tuple(float(v) for v in F.xy(*p))
    return [{'xy': xy(a['place']), 'ignore': a['ignore'], 'reach': a.get('reach', ANSWER_REACH),
             'stretch': [xy(p) for p in a.get('stretch', [])], 'sources': a.get('sources', ['di', 'dtmp'])}
            for a in (truth.get('trackHeights') or {}).get('radiusAnswers', []) if a.get('ignore')]


def answered_ignore(chs):
    """Where an answer drops a source's heights along a stretch, they go and the curve bridges them (the user, line 9 at
    Olšanské hřbitovy, 2026-11-07: "if you discard di on the left half, left of the white marker")."""
    n = 0
    for a in IGNORE_ANSWERS:
        if a['ignore'] != 'stretch' or len(a['stretch']) < 2:
            continue
        line = LineString(a['stretch'])
        for c in chs:
            if c.line.distance(line) > STRETCH_NEAR:
                continue
            for x in c.bins:
                if x['xy'] and x.get('z') is not None and x.get('src') in a['sources'] and line.distance(Point(x['xy'])) <= STRETCH_NEAR:
                    x['z'], x['w'] = None, 0.0
                    n += 1
    return n


def load_ground_answers(truth):
    """data/truth.json radiusAnswers with an `area` (lat, lon corners): 'follow the ground' there, the radius no tighter
    than `radius_min` (the user, 2026-11-08: 250 m; the 131 m curve at Malovanka was a 2.4 cm bump in the lidar over 5 m)."""
    from geo import Frame
    F = Frame()
    return [{'area': Polygon([tuple(float(v) for v in F.xy(*p)) for p in a['area']]), 'answer': FOLLOW, 'date': a.get('date'),
             'radius_min': a.get('radius_min', MIN_RADIUS)}
            for a in (truth.get('trackHeights') or {}).get('radiusAnswers', []) if a.get('area')]


def ground_at(xy, reach=0.0):
    """The ground answer whose area holds this point (or lies within `reach` of it), or None."""
    return next((g for g in GROUND_ANSWERS if xy is not None and g['area'].distance(Point(xy)) <= reach), None)


def answered_ground(chs):
    """Where an answer has the tracks follow the ground in an area, each height there takes the lidar ground and is marked,
    so that no rule drops it as a step steeper than any track; around the area the heights move part way, fading out over
    BLEND_REACH, so the edge makes no step, and are marked too (Královka: the ground climbs 61 cm in 5 m just past where
    the arms meet, at the area's edge; dropped there, the track lay 49 cm under it) (the user, Královka and Malovanka, 2026-11-08: "Can you try fitting the tracks to
    ground in the highlighted areas ... With smooth transition to the rest of tracks"). A lidar over GROUND_OTHER off is
    another level and stays out."""
    n = 0
    for g in GROUND_ANSWERS:
        near = g['area'].buffer(BLEND_REACH)
        for c in chs:
            if not c.line.intersects(near):
                continue
            for x in c.bins:
                lid = x.get('terrain')
                if not x['xy'] or lid is None or x.get('pin') or not near.covers(Point(x['xy'])):
                    continue
                if x.get('z') is not None and abs(lid - x['z']) > GROUND_OTHER:
                    continue
                d = g['area'].distance(Point(x['xy']))
                if d == 0:
                    x['z'], x['w'], x['ground'] = lid, 1.0, True
                    x['src'] = x.get('src') or 'dtmp'
                elif x.get('z') is not None:
                    x['z'] += (1 - d / BLEND_REACH) * (lid - x['z'])
                    x['ground'] = x.get('ground') or 'near'
                else:
                    continue
                n += 1
    return n


def load_step_answers(truth):
    """data/truth.json trackHeights.stepAnswers: at a place, whose heights (`use`: the archive, or DI as it is), and whether
    outliers go (`drop`), the survey is weighed in where the heights are noisy or the curve exceeded (`blend`), and how
    the radius answers there change (`radius`)."""
    from geo import Frame
    F = Frame()
    return [{'xy': tuple(float(v) for v in F.xy(*a['place'])), 'use': a['use'], 'drop': bool(a.get('drop')), 'blend': bool(a.get('blend')),
             'radius': {'follow': FOLLOW, 'hold': HOLD}.get(a.get('radius')), 'reach': a.get('reach', STEP_REACH),
             'toward': a.get('toward'), 'date': a.get('radius_date', a.get('date'))}
            for a in (truth.get('trackHeights') or {}).get('stepAnswers', [])]


def step_answer_at(xy):
    """The nearest step answer whose reach holds this point, or None."""
    near = [(math.dist(a['xy'], xy), k) for k, a in enumerate(STEP_ANSWERS) if math.dist(a['xy'], xy) <= a['reach']]
    return STEP_ANSWERS[min(near)[1]] if near else None


def answer_at(xys, kinds=(HOLD,)):
    """The user's answer (of `kinds`) at a place: the nearest within ANSWER_REACH of any of its points, else None. In an area
    where the tracks follow the ground, and the BLEND_REACH around it, that answer is the later word: it follows the data there."""
    g = next((g for xy in xys if (g := ground_at(xy, BLEND_REACH))), None)
    if g:
        return g if FOLLOW in kinds else None
    near = [(math.dist(a['xy'], xy), k, a) for k, a in enumerate(RADIUS_ANSWERS) if a['answer'] in kinds
            for xy in xys if xy is not None]
    near = [x for x in near if x[0] <= x[2].get('reach', ANSWER_REACH)]
    return min(near)[2] if near else None


def below_floor(xys):
    """A 'follow the data' answer given since the floor (FLOOR_SINCE) at this place: the user's later word lets the radius give
    way below the floor here. One given before it lets the radius give way only down to it (the user, 2026-11-07: "hold
    minimum radius at 500m everywhere and get back with review cases which can't fit the rule")."""
    a = answer_at(xys, (FOLLOW,))
    return bool(a and FLOOR_SINCE and (a.get('date') or '') >= FLOOR_SINCE)


def load(truth):
    """The answers and the date of the floor from data/truth.json, into this module's globals where the rules read them."""
    global RADIUS_ANSWERS, STEP_ANSWERS, FLOOR_SINCE, IGNORE_ANSWERS, GROUND_ANSWERS
    RADIUS_ANSWERS, STEP_ANSWERS = load_radius_answers(truth), load_step_answers(truth)
    IGNORE_ANSWERS, GROUND_ANSWERS = load_ignore_answers(truth), load_ground_answers(truth)
    FLOOR_SINCE = next((f.get('date') for f in truth['trackGeometry']['facts'] if f['id'] == 'vertical-radius-min'), None)


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


def answered_source(series):
    """Where the user's step answer takes the archive: its height in each bin, and where it has none the bin is held, so the
    curve bridges it (the user, Malostranské náměstí, 2026-11-06: "archive, bridge the gap")."""
    for x in series:
        a = step_answer_at(x['xy']) if x['xy'] and STEP_ANSWERS else None
        if not a or a['use'] != 'archive':
            continue
        if x['archive'] is None:
            x['z'], x['w'], x['src'] = None, 0.0, None
        else:
            x['z'], x['w'], x['src'] = x['archive'], 1.0, 'dtmp'


def height_runs(c):
    """The chain's stretches of bins with a height, no more than 2 BIN apart, as index lists."""
    out, run = [], []
    for i, x in enumerate(c.bins):
        if x['z'] is None:
            continue
        if run and x['s'] - c.bins[run[-1]]['s'] > 2 * BIN + .01:
            out.append(run)
            run = []
        run.append(i)
    if run:
        out.append(run)
    return [r for r in out if len(r) >= 5]


def smooth_line(c, run):
    """A run's own smooth line, for what lies off it."""
    return whittaker([c.bins[i]['s'] for i in run], [c.bins[i]['z'] for i in run], SMOOTH_WAVELENGTH)


def answered_toward(chs):
    """Where a step answer moves the archive part way to survey + lidar (`toward`): each archive height within the answer's
    reach goes that share of the way to the mean of survey and lidar where they agree within TOWARD_AGREE, else to the
    lidar, fading out over the reach's last BLEND_REACH m so the edge makes no step; a height whose lidar lies on another
    level (over TOWARD_OTHER away) stays (the user, Malovanka, 2026-11-07: "Let's pick the half option for malovanka now").
    `from` names the sources it moves, the archive by default, and `other` how far the lidar may lie off for it to (Královka's
    loop: DI too, up to 1 m off, no structure there and the user's photos showing the whole loop flush with the grass)."""
    moved = 0
    # (by its own reach, not the nearest answer's: the next card 85 m on would cut it off half way, in a step)
    for a in [a for a in STEP_ANSWERS if a['toward']]:
        for c in chs:
            for x in c.bins:
                d = math.dist(x['xy'], a['xy']) if x['xy'] else math.inf
                if d > a['reach'] or x.get('z') is None or x.get('src') not in a['toward'].get('from', ['dtmp']) or x.get('pin'):
                    continue
                arch, surv, lid = (x.get('archive') if x.get('src') == 'dtmp' else x['z']), x.get('survey'), x.get('terrain')
                if arch is None or lid is None or abs(lid - arch) > a['toward'].get('other', TOWARD_OTHER):
                    continue
                ref = (surv + lid) / 2 if surv is not None and abs(surv - lid) <= TOWARD_AGREE else lid
                w = min(1.0, (a['reach'] - d) / BLEND_REACH)
                x['z'] += w * (arch + a['toward']['share'] * (ref - arch) - x['z'])
                moved += 1
    return moved


def answered_noise(chs):
    """Where a step answer discards outliers, the heights far from their smooth line go. Where it weighs in the survey, the
    stretch where heights are noisy or the curve exceeded moves half way to the survey's slow difference from them, the
    weight and the difference both spread over BLEND_REACH, so the survey's own steps and the stretch's ends make no kink."""
    if not any(a['drop'] or a['blend'] for a in STEP_ANSWERS):
        return 0, 0
    dropped = blended = 0
    for c in chs:
        for run in height_runs(c):
            answers = [step_answer_at(c.bins[i]['xy']) if c.bins[i]['xy'] else None for i in run]
            if not any(a and (a['drop'] or a['blend']) for a in answers):
                continue
            line = smooth_line(c, run)
            s = [c.bins[i]['s'] for i in run]
            z = [c.bins[i]['z'] for i in run]
            want = [0.0] * len(run)
            for k, a in enumerate(answers):
                if a and a['blend']:
                    tight = False
                    if 2 <= k < len(run) - 2:
                        tight = abs(2 * ((z[k + 2] - z[k]) / (s[k + 2] - s[k]) - (z[k] - z[k - 2]) / (s[k] - s[k - 2])) / (s[k + 2] - s[k - 2])) > 1 / 500
                    want[k] = 1.0 if tight or abs(z[k] - line[k]) > BLEND_NOISE else 0.0
            near = lambda k: [j for j in range(len(run)) if abs(s[j] - s[k]) <= BLEND_REACH]
            for k, a in enumerate(answers):
                x = c.bins[run[k]]
                if a and a['drop'] and abs(z[k] - line[k]) > DROP_NOISE:
                    x['z'], x['w'], x['src'] = None, 0.0, None
                    dropped += 1
                else:
                    # (past the answer's reach too: at its edge the pull stood at half and made a 5 cm step)
                    around = near(k)
                    gaps = [c.bins[run[j]]['survey'] - z[j] for j in around if c.bins[run[j]]['survey'] is not None]
                    weight = sum(want[j] for j in around) / len(around)
                    if gaps and weight:
                        x['z'] = z[k] + .5 * weight * sum(gaps) / len(around)  # (fades out where the survey ends)
                        blended += 1
    return dropped, blended


def beside(chs, tree, ci, x):
    """The track beside chain ci's bin x: NEIGHBOUR_GAP m off, parallel within 15 degrees, the nearest; (distance, its chain,
    the distance along it) or None."""
    if not x['xy']:
        return None
    p, best = Point(x['xy']), None
    ux, uy = chs[ci].direction(x['s'])
    for j in tree.query(p.buffer(NEIGHBOUR_GAP[1])):
        j = int(j)
        if j == ci:
            continue
        o = chs[j]
        d = o.line.distance(p)
        if not NEIGHBOUR_GAP[0] <= d <= NEIGHBOUR_GAP[1]:
            continue
        t = o.line.project(p)
        vx, vy = o.direction(t)
        if abs(ux * vx + uy * vy) >= math.cos(math.radians(15)) and (best is None or d < best[0]):
            best = (d, j, t)
    return best


SOURCES_OFF, SOURCES_ON, SOURCES_EDGE, SOURCES_RUN = 0.5, 0.3, 0.1, 3  # m, m, m, bins (archive_over_di)
STRUCTURE_FLAGS = {'structure_hint', 'structure_unverified', 'tunnel_unverified', 'known_archive_disagreement'}


HELD_NEAR = 0.10      # m: a held height's source the lidar lies this near, the other source further (held_settled, rule 1)
LIDAR_AROUND = 100.0  # m: the rail's offset over the lidar where only the lidar has a height: the median of the chain's
LIDAR_OFFSET = 0.01   # heights this near, else this (the network's median: p10 -0.067, p90 +0.182 m on 61,403 bins)
LIDAR_LOG = []        # (xy, rule, height) of the heights held_settled gave: reports/line-heights.json


def held_settled(chs):
    """Heights the staging held (no source it could choose), settled by the lidar (#202). Not on a structure (the bare-earth
    lidar lies under a deck, on a hill over a tunnel), nor under a step answer.
    1. Where the archive and the survey disagree, the one the lidar lies within HELD_NEAR m of while the other lies
       further: the lidar breaks the tie, two sources against one. Calibrated where DI has a height too: the lidar's pick
       matched DI within HELD_NEAR at 148 of 155 bins (the archive 137 of 141, the survey 11 of 14); where it picks
       neither (14), the height stays held. Line 17 between Čechův most and Strossmayerovo náměstí: the archive within
       1-3 cm of the lidar for 126 m, the survey 0.3-0.4 m under both.
    2. Where only the lidar has a height (no DI, archive or survey: `no_usable_height`), the lidar plus the rail's offset
       over it on the chain's heights within LIDAR_AROUND m, else LIDAR_OFFSET (line 22's west end: 74-80 m). Only a
       stretch the lidar draws no steeper than any track (MAX_GRADE) and that meets the heights either side of it within
       SOURCES_ON: Petřín's funicular, held its whole length, took the hill's bare earth, steps of 2.2-6.1 m.
    3. Where only one of the archive and the survey has a height and the lidar lies within HELD_NEAR m of it, that one: two
       sources agree (#480: line 37 at Palmovka, held 110 + 154 m, the archive within 1-2 cm of the lidar). Calibrated
       where DI has a height too: such a lone source matched DI within HELD_NEAR at 13,953 of 15,448 bins (90 %; median
       1.6 cm, 95th percentile 16 cm); of the 372 over 20 cm off DI, 267 had DI itself over 20 cm off the lidar.
    Returns the counts per rule; each height goes to LIDAR_LOG and its source code is the one taken ('lidar' for 2)."""
    n1 = n2 = n3 = 0
    LIDAR_LOG.clear()
    usable = lambda x: (x.get('z') is not None and x.get('terrain') is not None and x.get('src') in ('di', 'dtmp')
                        and not STRUCTURE_FLAGS & set(x.get('flags') or ()) and abs(x['z'] - x['terrain']) < 1.0)
    for c in chs:
        ref = sorted((x['s'], x['z'] - x['terrain']) for x in c.bins if usable(x))
        todo = []
        bins = sorted(c.bins, key=lambda x: x['s'])
        for x in c.bins:
            g = x.get('terrain')
            if (x.get('z') is not None or g is None or not x['xy'] or STRUCTURE_FLAGS & set(x.get('flags') or ())
                    or (STEP_ANSWERS and step_answer_at(x['xy']))):
                continue
            a, s = x.get('archive'), x.get('survey')
            if a is not None and s is not None:
                if abs(a - g) <= HELD_NEAR < abs(s - g):
                    todo.append((x, a, 'dtmp', 1))
                elif abs(s - g) <= HELD_NEAR < abs(a - g):
                    todo.append((x, s, 'zps', 1))
            elif (a is None) != (s is None) and abs((a if s is None else s) - g) <= HELD_NEAR:
                todo.append((x, a, 'dtmp', 3) if s is None else (x, s, 'zps', 3))
            elif a is None and s is None:
                near = sorted(o for t, o in ref if abs(t - x['s']) <= LIDAR_AROUND)
                todo.append((x, g + (near[len(near) // 2] if near else LIDAR_OFFSET), 'lidar', 2))
        # (rule 2 by stretch: no steeper than any track, meeting the heights either side)
        lid = [t for t in todo if t[3] == 2]
        todo = [t for t in todo if t[3] != 2]
        lid.sort(key=lambda t: t[0]['s'])
        runs = []
        for t in lid:
            if runs and t[0]['s'] - runs[-1][-1][0]['s'] <= 2 * BIN + .01:
                runs[-1].append(t)
            else:
                runs.append([t])
        for run in runs:
            if any(abs(b[1] - a[1]) > MAX_GRADE * (b[0]['s'] - a[0]['s']) for a, b in zip(run, run[1:])):
                continue
            ok = True
            for end, side in ((run[0], -1), (run[-1], 1)):
                nb = [x for x in bins if x.get('z') is not None and 0 < side * (x['s'] - end[0]['s']) <= 2 * BIN + .01]
                if nb and abs(min(nb, key=lambda x: abs(x['s'] - end[0]['s']))['z'] - end[1]) > SOURCES_ON:
                    ok = False
            if ok:
                todo += run
        for x, z, src, rule in todo:
            x['z'], x['w'], x['src'] = z, 1.0, src
            LIDAR_LOG.append((x['xy'], rule, round(z, 3)))
            if rule == 1:
                n1 += 1
            elif rule == 2:
                n2 += 1
            else:
                n3 += 1
    return n1, n2, n3


def archive_over_di(chs):
    """Where one track's DI lies over SOURCES_OFF m off the lidar for SOURCES_RUN bins and more, while the archive lies within
    SOURCES_ON m of it and the track beside it within SOURCES_ON m of its own lidar, three sources stand against one: the
    archive's heights replace DI's along the whole stretch where the two differ by over SOURCES_EDGE (#344: line 9 at
    Sídliště Řepy, DI's outbound track humped 0.97 m over the lidar for 90 m, 0.7-0.9 m over the return track 3 m beside it,
    the archive within 0.2 m of the lidar; the support drawn under it stood 0.9 m over the other track's bed). Not on a
    structure (the bare-earth lidar and the archive both lie under a bridge, DI on it: up to 14 m apart), nor where both
    tracks lie off the lidar (a rebuild may have raised them since the archive), nor where the user answered a step card."""
    tree = shapely.STRtree([c.line for c in chs])
    moved = 0
    for ci, c in enumerate(chs):
        bins = sorted((x for x in c.bins if x['xy']), key=lambda x: x['s'])

        def core(x):
            if (x.get('src') != 'di' or x.get('z') is None or x.get('archive') is None or x.get('terrain') is None
                    or STRUCTURE_FLAGS & set(x.get('flags') or ()) or (STEP_ANSWERS and step_answer_at(x['xy']))):
                return False
            if abs(x['z'] - x['terrain']) <= SOURCES_OFF or abs(x['archive'] - x['terrain']) > SOURCES_ON:
                return False
            best = beside(chs, tree, ci, x)
            if best is None:
                return False
            near = [b for b in chs[best[1]].bins if b.get('z') is not None and b.get('terrain') is not None and abs(b['s'] - best[2]) <= BIN]
            if not near:
                return False
            n = min(near, key=lambda b: abs(b['s'] - best[2]))
            return abs(n['z'] - n['terrain']) <= SOURCES_ON
        flags = [core(x) for x in bins]
        k = 0
        while k < len(bins):
            if not flags[k]:
                k += 1
                continue
            e = k
            while e + 1 < len(bins) and flags[e + 1] and bins[e + 1]['s'] - bins[e]['s'] <= 2 * BIN + .01:
                e += 1
            if e - k + 1 >= SOURCES_RUN:
                apart = lambda x: (x.get('src') == 'di' and x.get('z') is not None and x.get('archive') is not None
                                   and not STRUCTURE_FLAGS & set(x.get('flags') or ()) and abs(x['z'] - x['archive']) > SOURCES_EDGE)
                a, b = k, e
                while a > 0 and apart(bins[a - 1]) and bins[a]['s'] - bins[a - 1]['s'] <= 2 * BIN + .01:
                    a -= 1
                while b + 1 < len(bins) and apart(bins[b + 1]) and bins[b + 1]['s'] - bins[b]['s'] <= 2 * BIN + .01:
                    b += 1
                for x in bins[a:b + 1]:
                    if x.get('archive') is not None:
                        x['z'], x['src'] = x['archive'], 'dtmp'
                        moved += 1
            k = e + 1
    return moved


def snap_to_neighbour(chs):
    """A sudden step or dip on one track that the track beside it does not have takes the neighbour's height, their slow offset
    kept (the user, 2026-11-06: "snap to the other track on sudden jumps", "again use neighbor track when there are steps
    and dips"). The tracks' real differences are kept: the offset is the median over 50 m either side, and a height only
    moves if it left its own line by NEIGHBOUR_STEP while the neighbour stays near its line."""
    offs = {}
    for ci, c in enumerate(chs):
        offs[ci] = {}
        for run in height_runs(c):
            for i, v in zip(run, smooth_line(c, run)):
                offs[ci][i] = c.bins[i]['z'] - float(v)
    tree = shapely.STRtree([c.line for c in chs])
    moved = []
    for ci, c in enumerate(chs):
        steps = [i for i, r in offs[ci].items() if abs(r) > NEIGHBOUR_STEP and c.bins[i]['xy']]
        if not steps:
            continue
        pairs = {}
        for i in offs[ci]:
            x = c.bins[i]
            best = beside(chs, tree, ci, x)
            if best is None:
                continue
            o, t = chs[best[1]], best[2]
            near = [k for k in offs[best[1]] if abs(o.bins[k]['s'] - t) <= BIN]
            if len(near) < 2:
                continue
            near.sort(key=lambda k: o.bins[k]['s'])
            if max(abs(offs[best[1]][k]) for k in near) > NEIGHBOUR_CALM:
                continue
            ss, zz = [o.bins[k]['s'] for k in near], [o.bins[k]['z'] for k in near]
            a = max(0, bisect.bisect_right(ss, t) - 1)
            b = min(a + 1, len(ss) - 1)
            pairs[i] = zz[a] if a == b else zz[a] + (zz[b] - zz[a]) * (t - ss[a]) / (ss[b] - ss[a])
        for i in steps:
            if i not in pairs:
                continue
            x = c.bins[i]
            calm = sorted(pairs[k] - c.bins[k]['z'] for k in pairs if abs(c.bins[k]['s'] - x['s']) <= 50 and abs(offs[ci][k]) <= NEIGHBOUR_CALM)
            if len(calm) < 5:
                continue
            moved.append((i, c, pairs[i] - calm[len(calm) // 2]))
    for i, c, z in moved:
        c.bins[i]['z'] = z
    NEIGHBOUR_LOG[:] = [(c.bins[i]['xy'], round(z, 3)) for i, c, z in moved]
    return len(moved)


def apply(chs):
    """The rules in front of the smoother and the solve, in their order, each printing what it did (line_heights `main`)."""
    print(f'{answered_ignore(chs)} heights dropped along a stretch by an answer ({len(IGNORE_ANSWERS)} answers that drop heights)', flush=True)
    print(f'{answered_toward(chs)} heights moved part way to survey + lidar by a step answer', flush=True)
    dropped, blended = answered_noise(chs)
    print(f'step answers: {len(STEP_ANSWERS)}; {dropped} heights dropped, {blended} weighed with the survey', flush=True)
    print(f'{archive_over_di(chs)} heights took the archive where DI alone stood off the lidar and the track beside it', flush=True)
    n1, n2, n3 = held_settled(chs)
    print(f'held heights settled by the lidar: {n1} where it sided with the archive or the survey, {n2} where only it had one, '
          f'{n3} where it confirmed the only source', flush=True)
    print(f'{snap_to_neighbour(chs)} heights took the neighbouring track\'s at a step or dip', flush=True)
    print(f'{answered_ground(chs)} heights took the ground, or part way to it, in {len(GROUND_ANSWERS)} areas an answer has '
          f'follow the ground', flush=True)
