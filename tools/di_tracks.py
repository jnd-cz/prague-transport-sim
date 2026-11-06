"""DI's track records as chains (#20, #237): the current DTM transport layer (DI) and the archived DTMP axes.

`Source` merges a source's track records end to end into chains that end only at forks, crossings and track ends,
drops re-entered and duplicate records, and finds the forks the provider did not split its records at (a branch
ending on a track's middle, interlaced track, a copy running on the track first). tools/di_network.py builds the
drawn network from DI's chains; tools/line_heights.py chains the records for heights.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))

ANGLE = 30     # degrees: two records leaving one place within this of each other may fork there
JOIN = 0.5     # m: source record ends closer than this continue each other (DI: 19,227 of 20,742 ends meet
               # exactly, 1,168 more within 0.5 m)
FORK = 15.0    # m: a switch tip the user placed (data/truth.json switchTips) belongs to a fork this near (the user's
               # answers of 2026-11-03, #204: forks 5.3-7.4 m from OSM's switch are the same switch, "Switch is there,
               # likely a bit further than 5m")
OVERLAP = 0.03  # m: a branch ending on a track's middle stays within this of its distance at the end while it runs
                # on it as a copy (Vozovna Kobylisy: two records 1-3 cm apart for 15 m, then they part)
OVERLAP_MIN = 3.0  # m: running on as a copy this far: the fork is where it leaves, else at the branch's end
INTERLACE = 0.05, 0.2, 10.0  # m: a branch running beside a track within 0.2 m for 10 m or more, at a median offset of
                # 5 cm or more, is interlaced track: the switch is at the branch's end, where it starts beside the
                # track (Čechův most 13 cm for 28 m, Ohrada 12-13 cm for 51 m; a switch's branch is 0.2 m off within
                # 4-9 m). The user, 2026-11-03: "the fork starts and ends well in front of/behind the road junction"
PHOTO_COVER = 0.6  # m: an orthophoto track covers a source chain within this (Podolská vodárna: DI up to 0.34 m off)
SECTION = 6.0   # m: a switch's two legs drawn as records this long or shorter from its tip (Dvorecký most: 4.7 m)
TONGUE = 8.5    # m: where DI starts an interlaced branch already beside the track at a record joint, the switch's tip
                # lies this far back (the tongues DI draws: Ohrada, Dejvice 8.4-8.5 m, Chotkova 9 m; OSM's switches
                # at Čechův most lie 8.0 and 8.8 m behind DI's record joints)
MIN_RECORD = 0.05  # m: shorter source records are dropped
FOLD_MIN = 0.1     # m: record ends' last segments this long say which way they go (DI joins records with 1 cm scraps)
DUPLICATE = 0.2    # m: a record joining the same two places as another, never farther from it, is a copy
SUPERSEDED = 0.95, 0.09  # share of an older record's length within DUPLICATE of newer records, and their median
                         # distance at most (m), for the older one to be an earlier copy: DI 2026-10-31's re-entries
                         # differ from the old records by up to 8.8 cm; interlaced track runs 9-17 cm beside its
                         # partner (Malostranské náměstí 9-10 cm, Čechův most 13 cm)
FORK_MIN, FORK_OUT, FORK_APART = 3.0, 8.0, 0.3  # m: a fork's branches (records this long) are this far apart
                                                # this far out


def _unit(v):
    l = math.hypot(*v) or 1.0
    return (v[0] / l, v[1] / l)


def _latest(recs):
    """Records without the earlier copies of re-entered ones. The provider enters a track again under a new ID and
    leaves the old record in the export: DI 2026-10-31 has 1,112 records of 2025-01-30 and 2026-05-27 (30 km) lying
    on records entered 2026-10-07, which carry the heights 967 of the old ones lacked, and the old records at
    Podolské nábřeží run on through the new Dvorecký most junction where the re-entries end at its switches."""
    lines = [LineString(xy) for _, xy in recs]
    date = [p['attrs'].get('DatumVkladu') or '' for p, _ in recs]
    tree = shapely.STRtree(lines)
    keep = []
    for i, line in enumerate(lines):
        newer = [lines[int(j)] for j in tree.query(line, predicate='dwithin', distance=DUPLICATE) if date[int(j)] > date[i]]
        if newer:
            n = max(2, int(line.length / 0.5) + 1)
            d = shapely.distance(shapely.line_interpolate_point(line, [line.length * k / (n - 1) for k in range(n)]),
                                 shapely.MultiLineString(newer))
            near = sorted(d[d <= DUPLICATE])
            if len(near) >= SUPERSEDED[0] * n and near[len(near) // 2] <= SUPERSEDED[1]:
                continue
        keep.append(recs[i])
    return keep


class Source:
    """A source's track records merged into chains that end only at forks, crossings and track ends."""

    def __init__(self, name, paths):
        self.name = name
        # (DI has zero-length records and the same piece twice under two IDs, Čechův most: either would make a
        # straight track look like a fork)
        recs = [(p, [tuple(c[:2]) for c in p['coords']]) for p in paths if len(p['coords']) > 1]
        recs = [r for r in recs if LineString(r[1]).length >= MIN_RECORD]
        n = len(recs)
        recs = _latest(recs)
        self.superseded = n - len(recs)
        while True:   # clusters, then again without the duplicates found
            ends = [(r, k, xy[0 if k == 0 else -1]) for r, (_, xy) in enumerate(recs) for k in (0, 1)]
            tree = shapely.STRtree(shapely.points([e[2] for e in ends]))
            cluster = list(range(len(ends)))
            def root(i):
                while cluster[i] != i:
                    cluster[i] = cluster[cluster[i]]
                    i = cluster[i]
                return i
            for i, (_, _, xy) in enumerate(ends):
                for j in tree.query(Point(xy).buffer(JOIN)):
                    if math.dist(xy, ends[j][2]) <= JOIN:
                        cluster[root(int(j))] = root(i)
            between = defaultdict(list)
            for r in range(len(recs)):
                between[tuple(sorted((root(2 * r), root(2 * r + 1))))].append(r)
            drop = set()
            for rs in between.values():
                for i, r in enumerate(rs):
                    if r not in drop and any(LineString(recs[r][1]).hausdorff_distance(LineString(recs[q][1])) < DUPLICATE
                                             for q in rs[:i] if q not in drop):
                        drop.add(r)
            if not drop:
                break
            recs = [r for i, r in enumerate(recs) if i not in drop]
        self.duplicates = len(paths) - self.superseded - len(recs)
        self.records = [p for p, _ in recs]  # (the paths kept: tools/line_heights.py chains them for heights)
        members = defaultdict(list)
        for i in range(len(ends)):
            members[root(i)].append(i)
        # forks: places where two records leave in the same direction and move apart (two copies of one track
        # leave together and stay within centimetres: Vozovna Kobylisy, 10 m each at 98-99 degrees); each with the
        # directions its branches leave in (`branches`, unit vectors out of the fork)
        self.forks, self.branches, self.far, self.sections = [], [], [], 0
        for c, ms in members.items():
            if len(ms) < 3:
                continue
            out = []
            for m in ms:
                r, k = divmod(m, 2)
                line = LineString(recs[r][1] if k == 0 else recs[r][1][::-1])
                if line.length >= FORK_MIN:
                    p0, p1 = line.interpolate(1.0), line.interpolate(min(FORK_OUT, line.length))
                    out.append(((p0.x - line.coords[0][0], p0.y - line.coords[0][1]), (p1.x, p1.y)))
            split = any(math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) /
                                                                 ((math.hypot(*u) * math.hypot(*v)) or 1))))) < ANGLE
                        and math.dist(pu, pv) >= FORK_APART
                        for i, (u, pu) in enumerate(out) for v, pv in out[:i])
            if split:
                # a switch drawn as a section: both legs as records from the tip to a joint SECTION or less on, where
                # the track and the branch go on (Dvorecký most, DI 2026-10-07: 4.7 m, the switch machine cover and
                # OSM's switch at the tip); the switch is at the tip
                far = defaultdict(list)
                for m in ms:
                    r, k = divmod(m, 2)
                    if LineString(recs[r][1]).length <= SECTION:
                        far[root(2 * r + 1 - k)].append(m)
                tip = next((c2 for c2, legs in far.items() if len(legs) >= 2 and c2 != c), None)
                if tip is not None:
                    c, ms, out = tip, members[tip], []
                    for m in ms:
                        r, k = divmod(m, 2)
                        line = LineString(recs[r][1] if k == 0 else recs[r][1][::-1])
                        p0 = line.interpolate(min(1.0, line.length))
                        out.append(((p0.x - line.coords[0][0], p0.y - line.coords[0][1]), None))
                    self.sections += 1
                xs = [ends[m][2] for m in ms]
                fx, fy = sum(x for x, _ in xs) / len(xs), sum(y for _, y in xs) / len(xs)
                self.forks.append((fx, fy))
                self.branches.append([_unit(u) for u, _ in out])
                # (and to FORK_OUT on: a tangential switch's branch is 1° off at 1 m, which side it leaves to only
                # shows further on)
                self.far.append([_unit((q[0] - fx, q[1] - fy)) if q else _unit(u) for u, q in out])
        # merge records through clusters of exactly two ends
        at = {i: members[root(i)] for i in range(len(ends))}
        used, self.chains = set(), []
        for r in range(len(recs)):
            if r in used:
                continue
            used.add(r)
            pts, ids = list(recs[r][1]), [recs[r][0]]
            for k, forward in ((1, True), (0, False)):
                cur, cur_end = r, k
                while True:
                    group = at[2 * cur + cur_end]
                    if len(group) != 2:
                        break
                    other = next(m for m in group if m != 2 * cur + cur_end)
                    nr, nk = divmod(other, 2)
                    if nr in used:
                        break
                    nxt = recs[nr][1] if nk == 0 else recs[nr][1][::-1]
                    # (two records leaving the same way from one point do not continue each other: a fork whose toe ends
                    # a little apart, Hloubětín: merged, the track went out along one and back along the other)
                    here = recs[cur][1] if cur_end == 1 else recs[cur][1][::-1]
                    u = (here[-1][0] - here[-2][0], here[-1][1] - here[-2][1])
                    v = (nxt[1][0] - nxt[0][0], nxt[1][1] - nxt[0][1])
                    if u[0] * v[0] + u[1] * v[1] < 0 and min(math.hypot(*u), math.hypot(*v)) > FOLD_MIN:
                        break
                    used.add(nr)
                    if forward:
                        pts += nxt[1:]
                        ids.append(recs[nr][0])
                    else:
                        pts = nxt[::-1][:-1] + pts
                        ids.insert(0, recs[nr][0])
                    cur, cur_end = nr, 1 - nk
            line = LineString(pts)
            if line.length > 0:
                self.chains.append({'line': line, 'records': ids})
        self._branch_ends()

    def _branch_ends(self):
        """Forks the source does not split its records at: a chain's lone end on another chain's middle, leaving it
        within ANGLE and moving apart (Palackého náměstí: the branch ends 19.8 m along the through track). Interlaced
        track (INTERLACE) forks where the branch starts beside the track, followed across record joints (Dejvice:
        both tracks split every few metres, their joints 12 cm apart): at the tip of its tongue where DI draws one
        (Ohrada: 0 to 12 cm over 9 m), else at the branch's end (Čechův most: 13 cm off at the through track's record
        joint). A copy running on the track first forks where it leaves."""
        lines = [c['line'] for c in self.chains]
        if not lines:
            return
        tree = shapely.STRtree(lines)
        tips = [p for l in lines for p in (l.coords[0], l.coords[-1])]
        tip_tree = shapely.STRtree(shapely.points(tips))
        known = list(self.forks)
        self.interlaced = []   # {'tip', 'dir' the branch leaves in, 'side' it lies on (1 left), 'run' m}
        cos = math.cos(math.radians(ANGLE))

        def onward(c, s, sign, length):
            """Points every 0.5 m along chain c from s on (sign 1: towards its end), then on through the nearest chain
            end within JOIN that continues it within ANGLE, up to length."""
            out, seen = [], {c}
            while True:
                l = lines[c]
                n = int((l.length - s if sign > 0 else s) / 0.5)
                out += [l.interpolate(s + sign * 0.5 * i) for i in range(n + 1)]
                if len(out) * 0.5 >= length:
                    return out[:int(length / 0.5) + 1]
                tip = l.coords[-1] if sign > 0 else l.coords[0]
                q = l.interpolate(l.length - 1.0 if sign > 0 else 1.0)
                d = _unit((tip[0] - q.x, tip[1] - q.y))
                best = None
                for i in tip_tree.query(Point(tip).buffer(JOIN)):
                    c2, e2 = divmod(int(i), 2)
                    g = math.dist(tips[int(i)], tip)
                    if c2 in seen or g > JOIN:
                        continue
                    l2 = lines[c2]
                    r = l2.interpolate(1.0 if e2 == 0 else l2.length - 1.0)
                    d2 = _unit((r.x - tips[int(i)][0], r.y - tips[int(i)][1]))
                    if d[0] * d2[0] + d[1] * d2[1] > cos and (best is None or g < best[0]):
                        best = (g, c2, e2)
                if best is None:
                    return out
                _, c, e2 = best
                seen.add(c)
                s, sign = (0.0, 1) if e2 == 0 else (lines[c].length, -1)

        def geom(pts):
            return LineString([(p.x, p.y) for p in pts]) if len(pts) > 1 else pts[0]

        for k, line in enumerate(lines):
            for first in (True, False):
                e = tips[2 * k + (0 if first else 1)]
                pe = Point(e)
                if any(math.dist(e, f) <= JOIN for f in known):
                    continue
                lone = not any(int(i) // 2 != k and math.dist(e, tips[int(i)]) <= JOIN for i in tip_tree.query(pe.buffer(JOIN)))
                walk = (lambda s: line.interpolate(s)) if first else (lambda s: line.interpolate(line.length - s))
                sign = 1 if first else -1
                for j in tree.query(pe.buffer(JOIN)):
                    j = int(j)
                    thr = lines[j]
                    if j == k or thr.distance(pe) > JOIN:
                        continue
                    tt = thr.project(pe)
                    # interlaced: the branch on from its end and back past it, against the track both ways (only
                    # where it is beside the track 3 m on and still within INTERLACE 10 m on, or its record ends first)
                    d3 = thr.distance(walk(min(3.0, line.length)))
                    maybe = 0.03 <= d3 <= INTERLACE[1] and (line.length < INTERLACE[2] or
                                                            thr.distance(walk(INTERLACE[2])) <= INTERLACE[1])
                    ahead = onward(k, 0.0 if first else line.length, sign, 120.0) if maybe else [pe]
                    track = shapely.MultiLineString([g for g in (geom(onward(j, tt, 1, 150.0)), geom(onward(j, tt, -1, 150.0)))
                                                     if g.geom_type == 'LineString'] if maybe else [thr])
                    da = shapely.distance(shapely.points([(p.x, p.y) for p in ahead]), track)
                    n_a = next((i for i, d in enumerate(da) if d > INTERLACE[1]), len(da))
                    behind = onward(k, 0.0 if first else line.length, -sign, 40.0)[1:] if maybe and not lone else []
                    if behind:   # (the extension behind starts with the jump onto the next record)
                        behind = [pe] + behind
                    db = shapely.distance(shapely.points([(p.x, p.y) for p in behind]), track) if behind else []
                    n_b = 0
                    while n_b + 1 < len(db) and 0.01 < db[n_b + 1] <= INTERLACE[1]:
                        n_b += 1
                    offs = sorted(list(da[:n_a]) + list(db[1:n_b + 1]))
                    run = (n_a - 1 + n_b) * 0.5
                    inter = (maybe and run >= INTERLACE[2] and offs[len(offs) // 2] >= INTERLACE[0] and len(ahead) - n_a >= FORK_MIN / 0.5
                             and da[min(len(da) - 1, n_a + int(FORK_OUT / 0.5))] >= FORK_APART)
                    if inter:
                        u = _unit((ahead[2].x - ahead[0].x, ahead[2].y - ahead[0].y))
                        mine = False   # (this record is the track, the other the branch)
                        if n_b:   # (the tongue DI draws)
                            f = track.interpolate(track.project(behind[n_b]))
                        elif da[0] >= INTERLACE[0]:   # (it starts beside the track at a record joint: the tip is a
                                                      # tongue back along the track)
                            back = max((onward(j, tt, sg, TONGUE + 1.0) for sg in (1, -1)),
                                       key=lambda q: -((q[min(2, len(q) - 1)].x - q[0].x) * u[0] + (q[min(2, len(q) - 1)].y - q[0].y) * u[1]))
                            f = geom(back).interpolate(TONGUE)
                        elif not lone and len(behind) > 1 and math.dist(e, (behind[1].x, behind[1].y)) < 0.01 and da[min(2, len(da) - 1)] >= INTERLACE[0]:
                            # (a record continuing another's end with the branch beside it from the joint: the same
                            # switch seen from the track, a tongue back along it)
                            f, mine = geom(behind).interpolate(TONGUE), True
                        else:   # (the branch starts on the track)
                            f = track.interpolate(track.project(pe))
                        q0, q1 = track.interpolate(max(0.0, track.project(f) - 0.5)), track.interpolate(track.project(f) + 0.5)
                        v = _unit((q1.x - q0.x, q1.y - q0.y))
                        if v[0] * u[0] + v[1] * u[1] < 0:
                            v = (-v[0], -v[1])
                        # the side the branch lies on, where it parts: 1 left of its direction, -1 right
                        q = ahead[max(0, n_a - 1)]
                        r = track.interpolate(track.project(q))
                        side = (1 if u[0] * (q.y - r.y) - u[1] * (q.x - r.x) > 0 else -1) * (-1 if mine else 1)
                    else:
                        d0, s = thr.distance(pe), 0.0
                        while s + 0.5 <= line.length and thr.distance(walk(s + 0.5)) <= d0 + OVERLAP:
                            s += 0.5
                        if s < OVERLAP_MIN:
                            s = 0.0
                        # (a branch ending on the middle of a track, or leaving it after running on it as a copy)
                        p0 = walk(s)
                        tt = thr.project(p0)
                        if not (s or lone) or not JOIN < tt < thr.length - JOIN:
                            continue
                        if line.length - s < FORK_MIN or thr.distance(walk(min(s + FORK_OUT, line.length))) < FORK_APART:
                            continue
                        p1 = walk(s + 1.0)
                        u = _unit((p1.x - p0.x, p1.y - p0.y))
                        q0, q1 = thr.interpolate(max(0.0, tt - 0.5)), thr.interpolate(min(thr.length, tt + 0.5))
                        v = _unit((q1.x - q0.x, q1.y - q0.y))
                        f = thr.interpolate(tt)
                    if math.degrees(math.acos(min(1.0, abs(u[0] * v[0] + u[1] * v[1])))) > ANGLE:
                        continue
                    if any(math.dist((f.x, f.y), q) <= JOIN for q in known):
                        break   # (found from the other track's end too)
                    self.forks.append((f.x, f.y))
                    self.branches.append([v, (-v[0], -v[1]), u])
                    self.far.append(list(self.branches[-1]))
                    known.append((f.x, f.y))
                    if inter:
                        self.interlaced.append({'tip': (f.x, f.y), 'dir': u, 'side': side, 'run': run})
                    break

def switch_tips(truth=None):
    """[(near, tip)] in city metres: switches whose tip the user placed (data/truth.json trackSources.switchTips)."""
    import json
    from geo import Frame
    path = truth or Path(__file__).resolve().parent.parent / 'data' / 'truth.json'
    facts = json.loads(Path(path).read_text(encoding='utf-8'))['trackSources'].get('switchTips', [])
    frame, out = Frame(), []
    for f in facts:
        (nx, tx), (ny, ty) = frame.xy([f['near'][0], f['tip'][0]], [f['near'][1], f['tip'][1]])
        out.append(((float(nx), float(ny)), (float(tx), float(ty))))
    return out


def photo_tracks(truth=None):
    """Tracks measured on the orthophoto that the user took over DI's (data/truth.json trackSources.photoTracks, each
    an exception), as source records in city metres."""
    import json
    from geo import Frame
    path = truth or Path(__file__).resolve().parent.parent / 'data' / 'truth.json'
    facts = json.loads(Path(path).read_text(encoding='utf-8'))['trackSources'].get('photoTracks', [])
    frame, out = Frame(), []
    for i, f in enumerate(facts):
        xs, ys = frame.xy([p[0] for p in f['points']], [p[1] for p in f['points']])
        out.append({'id': f'photo-{i}', 'coords': [(float(x), float(y), None) for x, y in zip(xs, ys)],
                    'attrs': {}, 'sources': [], 'place': f['place']})
    return out


def photo_source():
    """The orthophoto's tracks the user took over DI's as a source (TrackGeometry `photo`), or None."""
    photo = photo_tracks()
    return Source('ortho', photo) if photo else None


def load_sources():
    from dtmp_tracks import archive_data, di_data
    _, di = di_data()
    _, _, archived = archive_data()
    return [Source('di', di), Source('dtmp', archived)]
