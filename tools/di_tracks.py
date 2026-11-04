"""Track centrelines from the current DTM transport layer (DI), the archived DTMP axes and OSM as fill (#20).

    python -P -E tools/di_tracks.py --line 17     # match the line's cached OSM track ways, print what moved

The OSM track graph the build uses keeps its topology (nodes, ways, switches); its geometry is replaced
edge by edge where a source matches: every sample along the OSM edge lies within TOL of one source
chain, at most ANGLE off its direction, the chains following each other end to end. DI first, then the
archived DTMP axes (docs/decisions/2026-10-27-track-source.md); an edge no source matches keeps OSM and
takes up its neighbours' shift over BLEND metres. A source track with no OSM edge is never added (#35
for depots). The build (tools/build_line.py) calls `TrackGeometry`; every route position is computed
from the moved geometry afterwards.
"""
import math
import sys
from collections import defaultdict
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point

sys.path.insert(0, str(Path(__file__).resolve().parent))

TOL = 2.0      # m from an OSM edge sample to the source line
ANGLE = 30     # degrees between the OSM edge and the source line
STEP = 2.0     # m between samples along an OSM edge
JOIN = 0.5     # m: source record ends closer than this continue each other (DI: 19,227 of 20,742 ends meet
               # exactly, 1,168 more within 0.5 m)
FORK = 15.0    # m: an OSM switch takes the position of a source fork on its own tracks, diverging to the same side,
               # this near (the user's answers of 2026-11-03, #204: forks 5.3-7.4 m from OSM's switch are the same
               # switch, "Switch is there, likely a bit further than 5m")
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
BLEND = 20.0   # m along an OSM fill stretch over which it takes up the shift of its matched neighbours
CHANGE = 1.0   # m-equivalent cost of continuing on another chain along one OSM edge
JOINT = 4.0    # m: the chain may change only this near the joint of the two chains (STEP + TOL)
CONTEXT = 10.0  # m of the straightest continuation on either side a stretch is matched with: the 4.75 m between two
                # switches at Strossmayerovo náměstí, alone, lay nearer the branch DI draws 0.19 m beside the straight
                # (the straight was drawn bent onto it, 8 cm); the branch's chain does not reach the straight beyond
CONTINUE = 30.0  # degrees: an edge continues another within this
MIN_RECORD = 0.05  # m: shorter source records are dropped
DUPLICATE = 0.2    # m: a record joining the same two places as another, never farther from it, is a copy
SUPERSEDED = 0.95, 0.09  # share of an older record's length within DUPLICATE of newer records, and their median
                         # distance at most (m), for the older one to be an earlier copy: DI 2026-10-31's re-entries
                         # differ from the old records by up to 8.8 cm; interlaced track runs 9-17 cm beside its
                         # partner (Malostranské náměstí 9-10 cm, Čechův most 13 cm)
FORK_MIN, FORK_OUT, FORK_APART = 3.0, 8.0, 0.3  # m: a fork's branches (records this long) are this far apart
                                                # this far out
CONTEXT = 4.0  # m: an unmatched stretch between two matched nodes takes the chain its ends lie on within this
               # (Křižovnická: OSM draws a 60 m chord of the curve between both tracks, 1-2 m from each;
               # its neighbours fix which track it is)


def _unit(v):
    l = math.hypot(*v) or 1.0
    return (v[0] / l, v[1] / l)


def switch_legs(dirs):
    """A switch among three unit directions out of a node: (toe, (through leg, diverging leg)) as indices. The
    through track is the most nearly opposite pair; the diverging leg leaves within 90° of the through leg it runs
    beside, the toe the other way. None for another number of legs or a crossing."""
    if len(dirs) != 3:
        return None
    dot = lambda a, b: dirs[a][0] * dirs[b][0] + dirs[a][1] * dirs[b][1]
    i, j = min(((0, 1), (0, 2), (1, 2)), key=lambda p: dot(*p))
    d = 3 - i - j
    t = i if dot(i, d) > dot(j, d) else j
    if dot(t, d) <= 0:
        return None
    return (j if t == i else i), (t, d)


def branch_side(dirs, legs=None):
    """Which side of its through leg a switch's diverging leg leaves to: 1 left, -1 right, 0 not clear (within 1°)."""
    legs = legs or switch_legs(dirs)
    if not legs:
        return 0
    t, d = dirs[legs[1][0]], dirs[legs[1][1]]
    c = t[0] * d[1] - t[1] * d[0]
    return 0 if abs(c) < math.sin(math.radians(1)) else (1 if c > 0 else -1)


def same_way(dirs, branches):
    """An OSM switch (unit directions to its neighbours) and a source fork (its branches) face the same way: the
    two legs of each leave within 45° of the other's (the opposite of the toe). Which leg is the through one is not
    compared: OSM's legs near a switch are a few metres long, and in a curved switch the straighter one differs
    (Křižovnická, 50.0884 N 14.4155 E: OSM's diverging leg left, DI's right). Either not a switch: not decided."""
    a, b = switch_legs(dirs), switch_legs(branches)
    if not a or not b:
        return True
    u, v = dirs[a[0]], branches[b[0]]
    return u[0] * v[0] + u[1] * v[1] > math.cos(math.radians(45))


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
                    used.add(nr)
                    nxt = recs[nr][1] if nk == 0 else recs[nr][1][::-1]
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
        # segments for matching
        self.seg_chain, segs = [], []
        for c, ch in enumerate(self.chains):
            xy = list(ch['line'].coords)
            for a, b in zip(xy, xy[1:]):
                if a != b:
                    segs.append(LineString([a, b]))
                    self.seg_chain.append(c)
        self.segs = segs
        self.tree = shapely.STRtree(segs)
        self.fork_tree = shapely.STRtree(shapely.points(self.forks)) if self.forks else None

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
                        elif not lone and math.dist(e, (behind[1].x, behind[1].y)) < 0.01 and da[min(2, len(da) - 1)] >= INTERLACE[0]:
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

    def candidates(self, x, y, ux, uy, tol=TOL, only=None):
        """{chain: distance} of the source chains within tol whose direction there is within ANGLE."""
        out = {}
        for i in self.tree.query(Point(x, y).buffer(tol)):
            if only is not None and self.seg_chain[i] not in only:
                continue
            seg = self.segs[i]
            (ax, ay), (bx, by) = seg.coords
            l = math.hypot(bx - ax, by - ay)
            if abs(((bx - ax) * ux + (by - ay) * uy) / l) < math.cos(math.radians(ANGLE)):
                continue
            d = seg.distance(Point(x, y))
            c = self.seg_chain[i]
            if d <= tol and d < out.get(c, math.inf):
                out[c] = d
        return out

    def fork_near(self, x, y, reach=FORK):
        if self.fork_tree is None:
            return None
        hits = [self.forks[i] for i in self.fork_tree.query(Point(x, y).buffer(reach))]
        return min(hits, key=lambda f: math.dist(f, (x, y)), default=None)

    def connected(self, c1, c2):
        """The point where chain c1 ends and c2 begins (within JOIN), else None."""
        l1, l2 = self.chains[c1]['line'].coords, self.chains[c2]['line'].coords
        for p in (l1[0], l1[-1]):
            for q in (l2[0], l2[-1]):
                if math.dist(p, q) <= JOIN:
                    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        return None

    def match(self, a, b, tol=TOL, only=None):
        """The source chains along OSM edge a-b: [(chain, first sample, last sample), ...] or None."""
        found = self.match_path([a, b], tol, only)
        return found[0] if found else None

    def match_path(self, pts, tol=TOL, only=None):
        """The source chains along the OSM edges of a node sequence, one runs list per edge, or None. Over the
        whole sequence the chain changes only where one chain continues another, within JOINT of their joint
        (near a switch both tracks lie within centimetres: an edge alone may lie nearer the other one)."""
        samples, edge_of = [], []
        for e, (a, b) in enumerate(zip(pts, pts[1:])):
            length = math.dist(a, b)
            if length < 1e-6:
                return None
            ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            n = max(1, math.ceil(length / STEP))
            for k in range(0 if e == 0 else 1, n + 1):
                samples.append(((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n), ux, uy))
                edge_of.append(e)
        cands = [self.candidates(*p, ux, uy, tol, only) for p, ux, uy in samples]
        if not all(cands):
            return None
        back = [{c: (d, None) for c, d in cands[0].items()}]
        for k in range(1, len(samples)):
            p = samples[k][0]
            nxt = {}
            for c, d in cands[k].items():
                best = None
                for q, (qc, _) in back[-1].items():
                    if q == c:
                        step = 0.0
                    else:
                        joint = self.connected(q, c)
                        step = CHANGE if joint is not None and math.dist(joint, p) <= JOINT else None
                    if step is not None and (best is None or qc + step < best[0]):
                        best = (qc + step, q)
                if best:
                    nxt[c] = (best[0] + d, best[1])
            if not nxt:
                return None
            back.append(nxt)
        c = min(back[-1], key=lambda k: back[-1][k][0])
        seq = []
        for k in range(len(samples) - 1, -1, -1):
            seq.append(c)
            c = back[k][c][1]
        seq.reverse()
        out = [[] for _ in range(len(pts) - 1)]
        # each edge's runs; an inner node's sample belongs to both edges that meet there
        for k, (c, (p, _, _)) in enumerate(zip(seq, samples)):
            for e in {edge_of[k]} | ({edge_of[k] + 1} if k + 1 < len(samples) and edge_of[k + 1] == edge_of[k] + 1 else set()):
                runs = out[e]
                if runs and runs[-1][0] == c:
                    runs[-1][2] = p
                else:
                    runs.append([c, p, p])
        return out


def polyline(source, runs, a, b):
    """Points from a to b along the matched chains: the chain pieces between the projections of the ends and
    the joints between chains, a and b themselves at the ends."""
    pts = [a]
    for i, (c, _, _) in enumerate(runs):
        line = source.chains[c]['line']
        s0 = line.project(Point(a if i == 0 else source.connected(runs[i - 1][0], c)))
        s1 = line.project(Point(b if i == len(runs) - 1 else source.connected(c, runs[i + 1][0])))
        coords = list(line.coords)
        acc = [0.0]
        for p, q in zip(coords, coords[1:]):
            acc.append(acc[-1] + math.dist(p, q))
        inner = [coords[k] for k in range(len(coords)) if min(s0, s1) + 0.05 < acc[k] < max(s0, s1) - 0.05]
        if s1 < s0:
            inner.reverse()
        if i > 0:
            pts.append(source.connected(runs[i - 1][0], c))
        pts += inner
    pts.append(b)
    out = [pts[0]]
    for p in pts[1:-1]:
        if math.dist(p, out[-1]) > 0.01:
            out.append(p)
    return out + [pts[-1]]   # both ends always (two nodes may land a centimetre apart)


class TrackGeometry:
    """New node positions and edge geometry for an OSM track graph.

    pos: {node: (x, y)} as OSM gives them; edges: iterable of (a, b) node pairs (either direction).
    After construction: `at(node)` the node's position, `points(a, b)` the edge's points from a to b,
    `source(a, b)` {'src': 'di' | 'dtmp' | 'osm', 'records': [...]}, and `report` (counts and places)."""

    def __init__(self, pos, edges, sources, tips=(), photo=None):
        self.orig = dict(pos)
        self.edges = {}
        adj = defaultdict(set)
        for a, b in edges:
            if a == b or a not in pos or b not in pos:
                continue
            key = (a, b) if str(a) < str(b) else (b, a)
            self.edges[key] = None
            adj[a].add(b)
            adj[b].add(a)
        self.adj = adj
        # 1. per source in order (DI first): every edge it matches, then the unmatched stretches between matched
        # nodes; a later source takes only what is left
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        stretches = self._stretches()
        for src in sources:
            for nodes in stretches:
                keys = [k(a, b) for a, b in zip(nodes, nodes[1:])]
                if any(self.edges[e] is not None for e in keys):
                    continue
                before, after = self._context(nodes, pos)
                found = src.match_path([pos[n] for n in before + nodes + after]) if before or after else None
                found = found[len(before):len(before) + len(keys)] if found else src.match_path([pos[n] for n in nodes])
                if found:
                    for (a, b), e, runs in zip(zip(nodes, nodes[1:]), keys, found):
                        self.edges[e] = (src, runs if (a, b) == e else [[c, q, p] for c, p, q in runs[::-1]])
            for key in self.edges:
                if self.edges[key] is None:
                    runs = src.match(pos[key[0]], pos[key[1]])
                    if runs:
                        self.edges[key] = (src, runs)
            self._by_ends(src, pos)
            self._no_branch(src, pos)
        # 1b. a track measured on the orthophoto (data/truth.json photoTracks, `photo`) takes the edges matched to a
        # source chain it covers (along 80 % of its length within PHOTO_COVER); not the tracks it only passes near
        # at its ends (Podolská vodárna: its first 8 m run beside the straight track in Podolská)
        if photo is not None:
            lines = shapely.MultiLineString([c['line'] for c in photo.chains])
            covered = {}
            for key, hit in self.edges.items():
                if hit is None:
                    continue
                for c, _, _ in hit[1]:
                    if (id(hit[0]), c) not in covered:
                        line = hit[0].chains[c]['line']
                        n = max(2, int(line.length))
                        near = sum(lines.distance(line.interpolate(line.length * i / n)) <= PHOTO_COVER for i in range(n + 1))
                        covered[(id(hit[0]), c)] = near >= 0.8 * (n + 1)
            for key, hit in self.edges.items():
                if hit and all(covered[(id(hit[0]), c)] for c, _, _ in hit[1]):
                    runs = photo.match(pos[key[0]], pos[key[1]])
                    if runs:
                        self.edges[key] = (photo, runs)
        # 2. node positions: a matched node moves onto its chain (a switch onto the source's fork when one is
        # within FORK), a node with only unmatched edges keeps OSM's position and takes up its neighbours' shift
        self.pos = {}
        # each source fork goes to the nearest OSM switch within FORK on its tracks that leaves the same way, one
        # node per fork (Palackého náměstí: two switches 4-5 m apart would both take one fork and the edge between
        # them would vanish)
        claims, refused = [], []
        for n in adj:
            if len(adj[n]) < 3:
                continue
            hits = {m: self.edges[k(n, m)] for m in adj[n]}
            # (the source of its edges that has forks: a branch taken from the orthophoto has none)
            src = next((h[0] for h in hits.values() if h and h[0].fork_tree is not None), None)
            if src is None:
                continue
            ms = list(adj[n])
            dirs = [_unit((pos[m][0] - pos[n][0], pos[m][1] - pos[n][1])) for m in ms]
            legs = switch_legs(dirs)
            far_dirs = [self._far(n, m, pos) for m in ms] if legs else None
            if legs:
                # a switch: the fork lies on a chain its through track runs on (OSM's node may lie past the
                # source's fork and a record joint, Jiráskovo náměstí); not the diverging edge's, whose far end
                # may be the other track's fork of a crossover
                toe, (t, _) = legs
                on_chains = [{r[0] for r in hits[ms[x]][1]} for x in (toe, t) if hits[ms[x]] and hits[ms[x]][0] is src]
                on = lambda f: any(src.chains[c]['line'].distance(Point(f)) <= JOIN for cs in on_chains for c in cs)
            else:
                # (a crossing or more legs: on every chain the node's edges run on at it; a crossover has a fork on
                # each track, the other track's one 4 m sideways may be the nearer, Holešovice)
                mine = {(h[1][0][0] if str(n) < str(m) else h[1][-1][0]) for m, h in hits.items() if h and h[0] is src}
                on = lambda f: all(src.chains[c]['line'].distance(Point(f)) <= JOIN for c in mine)
            for i in src.fork_tree.query(Point(pos[n]).buffer(FORK)):
                f = src.forks[i]
                d = math.dist(f, pos[n])
                collapse = self._past(n, f, pos)
                if d <= FORK and on(f) and same_way(dirs, src.branches[i]):
                    # (a switch whose branch leaves to the other side, over CONTEXT m, takes it only if no switch
                    # nearby fits: Strossmayerovo náměstí's westward turn left its fork to OSM's switch 2.1 m on,
                    # whose branch leaves the other way, and started 3.8 m late at 12°)
                    c = (d + (FORK if legs and branch_side(far_dirs) * branch_side(src.far[i]) < 0 else 0.0),
                         n, (src.name, int(i)), f, collapse)
                    (claims if collapse is not None else refused).append(c)
            # a switch whose tip the user placed (data/truth.json trackSources.switchTips) takes the point of its
            # through track nearest that place, before any fork
            for i, (near, tip) in enumerate(tips):
                if legs and math.dist(near, pos[n]) <= FORK:
                    lines = [src.chains[c]['line'] for cs in on_chains for c in cs]
                    if lines:
                        line = min(lines, key=lambda l: l.distance(Point(tip)))
                        q = line.interpolate(line.project(Point(tip)))
                        collapse = self._past(n, (q.x, q.y), pos)
                        if collapse is not None:
                            claims.append((-1.0, n, ('tip', i), (q.x, q.y), collapse))
        fork_of, taken, collapsed = {}, set(), {}
        for d, n, key, f, collapse in sorted(claims, key=lambda c: c[0]):
            if n in fork_of or n in collapsed or key in taken or any(m in fork_of or m in collapsed for m in collapse):
                continue
            fork_of[n] = f
            taken.add(key)
            collapsed.update({m: f for m in collapse})
        # a fork past a neighbouring switch, once that switch is on its own fork further on: the order along the
        # track kept (Strossmayerovo náměstí, Milady Horákové: OSM's two switches 2.1 m apart, DI's forks 4.7 m apart
        # and 4-5 m further west; the eastern switch's branch ran on the track 3.8 m past DI's fork)
        placed = {**pos, **fork_of, **collapsed}
        for d, n, key, f, _ in sorted(refused, key=lambda c: c[0]):
            if n in fork_of or n in collapsed or key in taken:
                continue
            collapse = self._past(n, f, placed)
            if collapse is None or any(m in fork_of or m in collapsed for m in collapse):
                continue
            fork_of[n] = f
            taken.add(key)
            collapsed.update({m: f for m in collapse})
            placed.update({n: f, **{m: f for m in collapse}})
        for n in adj:
            ends = []
            for m in adj[n]:
                hit = self.edges[(n, m) if str(n) < str(m) else (m, n)]
                if hit:
                    src, runs = hit[:2]
                    run = runs[0] if (n, m) == ((n, m) if str(n) < str(m) else (m, n)) else runs[-1]
                    line = src.chains[run[0]]['line']
                    q = line.interpolate(line.project(Point(pos[n])))
                    ends.append((src, (q.x, q.y), line))
            if not ends:
                continue
            if n in fork_of:
                self.pos[n] = fork_of[n]
            else:
                # the point nearest to all the node's chains: a projection, or where two of them cross (a diamond
                # crossing at Dlouhá třída: the projection on the other track lay 0.5 m off ours)
                lines = list({id(e[2]): e[2] for e in ends}.values())
                cands = [e[1] for e in ends]
                for i, l1 in enumerate(lines):
                    for l2 in lines[:i]:
                        l = l1
                        x = l1.intersection(l2)
                        for g in getattr(x, 'geoms', [x]):
                            q = (g.x, g.y) if g.geom_type == 'Point' else None
                            # a crossing: inside both chains (two chains touching at a fork are a switch, not this),
                            # and never past a neighbour
                            if (q and math.dist(q, pos[n]) <= FORK
                                    and min(math.dist(q, l.coords[0]), math.dist(q, l.coords[-1]),
                                            math.dist(q, l2.coords[0]), math.dist(q, l2.coords[-1])) > JOIN
                                    and all(math.dist(q, pos[m]) > 0.5 and (q[0] - pos[m][0]) * (pos[n][0] - pos[m][0])
                                            + (q[1] - pos[m][1]) * (pos[n][1] - pos[m][1]) > 0 for m in adj[n])):
                                cands.append(q)
                self.pos[n] = min(cands, key=lambda q: (round(sum(l.distance(Point(q)) for l in lines), 3),
                                                        math.dist(q, pos[n])))
        self.pos.update(collapsed)
        self.forked, self.collapsed = fork_of, collapsed
        matched = set(self.pos)
        shift ={n: (self.pos[n][0] - pos[n][0], self.pos[n][1] - pos[n][1]) for n in matched}
        # fill nodes: the shift of the nearest matched node along the graph, fading to 0 over BLEND
        best = {}
        frontier = [(0.0, n, n) for n in matched]
        import heapq
        heapq.heapify(frontier)
        while frontier:
            d, n, origin = heapq.heappop(frontier)
            if n in best or d > BLEND:
                continue
            best[n] = (d, origin)
            for m in adj[n]:
                if m not in matched and m not in best:
                    heapq.heappush(frontier, (d + math.dist(pos[n], pos[m]), m, origin))
        for n in adj:
            if n in matched:
                continue
            if n in best:
                d, origin = best[n]
                f = 1 - d / BLEND
                self.pos[n] = (pos[n][0] + shift[origin][0] * f, pos[n][1] + shift[origin][1] * f)
            else:
                self.pos[n] = pos[n]
        # 3. edge points
        self.pts = {}
        for (a, b), hit in self.edges.items():
            if hit:
                src, runs = hit[:2]
                self.pts[(a, b)] = polyline(src, runs, self.pos[a], self.pos[b])
            else:
                self.pts[(a, b)] = [self.pos[a], self.pos[b]]
        self.report = self._report(sources)

    def _far(self, n, m, pos, length=CONTEXT):
        """The unit direction from node n to the point `length` m on along n-m and its straightest continuations."""
        prev, cur, d, seen = n, m, math.dist(pos[n], pos[m]), {n, m}
        while d < length:
            u = _unit((pos[cur][0] - pos[prev][0], pos[cur][1] - pos[prev][1]))
            nxt = [x for x in self.adj[cur] if x not in seen]
            if not nxt:
                break
            x = max(nxt, key=lambda x: (lambda v: u[0] * v[0] + u[1] * v[1])(_unit((pos[x][0] - pos[cur][0], pos[x][1] - pos[cur][1]))))
            d += math.dist(pos[cur], pos[x])
            prev, cur = cur, x
            seen.add(x)
        return _unit((pos[cur][0] - pos[n][0], pos[cur][1] - pos[n][1]))

    def _context(self, nodes, pos):
        """The nodes continuing a node sequence straight on at either end, up to CONTEXT m: through two-edge nodes,
        and through a switch only from its toe or through leg into the other (its legs by their directions over
        CONTEXT m: OSM's first metres made a crossover the through leg at Strossmayerovo náměstí). None from a
        diverging leg, at a crossing or past a turn over CONTINUE degrees."""
        out = []
        for seq in (nodes[::-1], nodes):
            prev, cur, ext, d = seq[-2], seq[-1], [], 0.0
            while d < CONTEXT:
                ms = [m for m in self.adj[cur]]
                if len(ms) == 2:
                    nxt = next(m for m in ms if m != prev)
                elif len(ms) == 3:
                    dirs = [self._far(cur, m, pos) for m in ms]
                    legs = switch_legs(dirs)
                    if legs is None or ms[legs[1][1]] == prev:
                        break
                    nxt = next(ms[i] for i in (legs[0], legs[1][0]) if ms[i] != prev)
                else:
                    break
                u = _unit((pos[cur][0] - pos[prev][0], pos[cur][1] - pos[prev][1]))
                v = _unit((pos[nxt][0] - pos[cur][0], pos[nxt][1] - pos[cur][1]))
                if nxt in nodes or nxt in ext or u[0] * v[0] + u[1] * v[1] < math.cos(math.radians(CONTINUE)):
                    break
                d += math.dist(pos[cur], pos[nxt])
                ext.append(nxt)
                prev, cur = cur, nxt
            out.append(ext)
        return out[0][::-1], out[1]

    def _stretches(self):
        """Node sequences through nodes with two edges, from a node with another count to the next (closed loops
        of two-edge nodes as one sequence)."""
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        seen, out = set(), []
        starts = [n for n in self.adj if len(self.adj[n]) != 2]
        for s in starts + list(self.adj):
            for m in self.adj[s]:
                if k(s, m) in seen:
                    continue
                seq = [s, m]
                seen.add(k(s, m))
                while len(self.adj[seq[-1]]) == 2 and seq[-1] != s:
                    nxt = next((x for x in self.adj[seq[-1]] if k(seq[-1], x) not in seen), None)
                    if nxt is None:
                        break
                    seen.add(k(seq[-1], nxt))
                    seq.append(nxt)
                out.append(seq)
        return out

    def _by_ends(self, src, pos):
        """An unmatched stretch (through nodes with two edges) between matched nodes takes this source's chains its
        ends lie on, within CONTEXT. An end matched by an earlier source gives this source's chain nearest to it."""
        for key in [k for k, v in self.edges.items() if v is None]:
            if self.edges[key] is not None:
                continue
            stretch, ends = self._stretch(key)
            if len(ends) < 2:
                continue
            only = set()
            for n, via in ends:
                hit = self.edges[via]
                if hit[0] is src:
                    only.add(hit[1][0][0] if n == via[0] else hit[1][-1][0])
                    continue
                m = via[1] if via[0] == n else via[0]
                l = math.dist(pos[n], pos[m]) or 1
                near = src.candidates(*pos[n], (pos[m][0] - pos[n][0]) / l, (pos[m][1] - pos[n][1]) / l, CONTEXT)
                if not near:
                    break
                only.add(min(near, key=near.get))
            else:
                found = {e: src.match(pos[e[0]], pos[e[1]], CONTEXT, only) for e in stretch}
                if all(found.values()):
                    for e, runs in found.items():
                        self.edges[e] = (src, runs, 'context')

    def _past(self, n, f, pos):
        """The nodes that move onto fork f with switch node n: none when f lies on n's side of every neighbour; a
        two-edge neighbour at f or behind it moves with n when the node after it lies beyond f (Křižovnická: OSM's
        node 0.5 m from the switch, the fork 5 m on). None when f lies past a junction or further (Holešovice: a
        fork 3.7 m behind the previous node turned the route back)."""
        beyond = lambda m, a: math.dist(f, pos[m]) > 0.5 and (f[0] - pos[m][0]) * (pos[a][0] - pos[m][0]) \
            + (f[1] - pos[m][1]) * (pos[a][1] - pos[m][1]) > 0
        out = []
        for m in self.adj[n]:
            if beyond(m, n):
                continue
            nxt = [x for x in self.adj[m] if x != n]
            if len(nxt) != 1 or not beyond(nxt[0], m):
                return None
            out.append(m)
        return out

    def _no_branch(self, src, pos):
        """A switch's diverging edge matched only to the one chain both its through edges run on at the switch: the
        source has no branch there (Dvorce: DI of 2026-09-30 has no track onto the new Dvorecký most), so the edge
        is left to the next source or OSM. (OSM's switch past the source's fork has its through edges on the two
        tracks leaving it, Jiráskovo náměstí: that is a branch.)"""
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        at = lambda n, m: (lambda h: h[1][0][0] if n == k(n, m)[0] else h[1][-1][0])(self.edges[k(n, m)])
        for n, ms in self.adj.items():
            if len(ms) != 3:
                continue
            ms = list(ms)
            legs = switch_legs([_unit((pos[m][0] - pos[n][0], pos[m][1] - pos[n][1])) for m in ms])
            if not legs:
                continue
            dv = ms[legs[1][1]]
            hit = self.edges[k(n, dv)]
            if not hit or hit[0] is not src or len({r[0] for r in hit[1]}) != 1:
                continue
            others = [m for m in ms if m != dv]
            if not all(self.edges[k(n, m)] and self.edges[k(n, m)][0] is src for m in others):
                continue
            if {at(n, m) for m in others} == {hit[1][0][0]}:
                self.edges[k(n, dv)] = None

    def _stretch(self, key):
        """The unmatched edges through two-edge nodes around `key`, and its ends: [(node, matched edge at it)]."""
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        stretch, ends, todo = {key}, [], [(key[0], key), (key[1], key)]
        while todo:
            n, came = todo.pop()
            others = [k(n, m) for m in self.adj[n] if k(n, m) != came]
            matched = [e for e in others if self.edges[e] is not None]
            if matched:
                ends.append((n, matched[0]))
            elif len(others) == 1 and others[0] not in stretch:
                stretch.add(others[0])
                e = others[0]
                todo.append((e[1] if e[0] == n else e[0], e))
        return stretch, ends

    def fit_curves(self):
        """The edges as smooth curves through their points, continuous in direction at every node
        (tools/track_curve.py, #204); `report['curve']` says what moved and what was left."""
        import track_curve
        kind = {key: (hit[0].name if hit else 'osm') for key, hit in self.edges.items()}
        # a node off the chain an edge runs on at it, and how far (the point nearest all of a node's chains; a fork
        # moved onto the through track, off the branch)
        loose = {}
        for (a, b), hit in self.edges.items():
            if hit:
                for n, run in ((a, hit[1][0]), (b, hit[1][-1])):
                    d = hit[0].chains[run[0]]['line'].distance(Point(self.pos[n]))
                    if d > 0.01:
                        loose[(n, (a, b))] = d
        # how far each surveyed edge may move where a curve would bend too tight: the mean coordinate error of the
        # worst accuracy class among its records (data/truth.json `sourceAccuracy`; the archive states none)
        errors, limit = track_curve.class_errors(), {}
        for key, hit in self.edges.items():
            if hit:
                classes = {r['attrs'].get('TridaPresnostiPoloha') for c, _, _ in hit[1] for r in hit[0].chains[c]['records']}
                known = [errors[c] for c in classes if c in errors]
                if known and None not in classes:
                    limit[key] = max(known)
        net = track_curve.Network(self.pos, self.pts, kind, loose, limit)
        self.pos.update(net.pos)
        self.pts = net.pts
        self.report['curve'] = net.report

    def at(self, n):
        return self.pos.get(n, self.orig.get(n))

    def points(self, a, b):
        key = (a, b) if str(a) < str(b) else (b, a)
        if key not in self.pts:
            return [self.at(a), self.at(b)]
        p = self.pts[key]
        return p if key == (a, b) else p[::-1]

    def source(self, a, b):
        hit = self.edges.get((a, b) if str(a) < str(b) else (b, a))
        if not hit:
            return {'src': 'osm', 'records': []}
        src, runs = hit[:2]
        recs = []
        for c, _, _ in runs:
            for r in src.chains[c]['records']:
                if r['id'] not in recs:
                    recs.append(r['id'])
        return {'src': src.name, 'records': recs}

    def _report(self, sources):
        length = defaultdict(float)
        fill = []
        for (a, b), hit in self.edges.items():
            l = math.dist(self.orig[a], self.orig[b])
            length[hit[0].name if hit else 'osm'] += l
            if not hit:
                fill.append(((a, b), l))
        moves = sorted(math.dist(self.orig[n], self.pos[n]) for n in self.pos)
        # an edge whose ends swapped order against OSM by 0.5 m or more: the track would run back on itself (two
        # nodes landing centimetres apart on one source track is no reversal)
        reversed_ = sum(1 for a, b in self.edges if math.dist(self.pos[a], self.pos[b]) >= 0.5 and
                        (self.pos[b][0] - self.pos[a][0]) * (self.orig[b][0] - self.orig[a][0])
                        + (self.pos[b][1] - self.pos[a][1]) * (self.orig[b][1] - self.orig[a][1]) < 0)
        q = lambda f: round(moves[min(len(moves) - 1, int(f * len(moves)))], 3) if moves else None
        return {'edges_m': {k: round(v, 1) for k, v in length.items()},
                'node_moves_m': {'n': len(moves), 'p50': q(.5), 'p90': q(.9), 'p99': q(.99), 'max': q(1)},
                'reversed_edges': reversed_,
                'switches_on_forks': len(self.forked), 'nodes_moved_with_a_switch': len(self.collapsed),
                'fill': fill}


def split_interlaced(ways, seqs, pos, interlaced, reach=20.0, snap=3.0):
    """OSM draws interlaced track as one way from the switch to where the tracks part: a railway=switch node at
    the tip, the split at a railway_crossing node ("rozjezdová splítka": Čechův most, Ke Stírce, Ohrada). For each
    interlaced switch of the source (`Source.interlaced`) whose tip lies on an OSM edge running its way, the stretch
    from the tip (an OSM node within `snap`, else a new one) to the next junction ahead within its run and `reach`
    is doubled; the copy carries the leg on the branch's side, so each track has its own edges and the switch is at
    the tip. Where OSM already splits at the tip nothing changes.

    ways: [{'nodes': [...], 'tags': {...}}], seqs: route node lists, pos: {node: (x, y)}; all changed in place.
    Returns {new node: ('copy', node) | ('between', a, b, t)} (t: from a towards b)."""
    new, next_id = {}, min([0] + [n for w in ways for n in w['nodes'] if isinstance(n, int)]) - 1
    for it in interlaced:
        tip, u = it['tip'], it['dir']
        adj = defaultdict(set)
        for ns in [w['nodes'] for w in ways] + list(seqs):
            for a, b in zip(ns, ns[1:]):
                if a != b:
                    adj[a].add(b)
                    adj[b].add(a)
        best = None
        for a in adj:
            for b in adj[a]:
                if str(a) >= str(b):
                    continue
                (ax, ay), (bx, by) = pos[a], pos[b]
                l2 = (bx - ax) ** 2 + (by - ay) ** 2
                if l2 < 1e-6:
                    continue
                s = max(0.0, min(1.0, ((tip[0] - ax) * (bx - ax) + (tip[1] - ay) * (by - ay)) / l2))
                d = math.dist(tip, (ax + s * (bx - ax), ay + s * (by - ay)))
                cos = abs((bx - ax) * u[0] + (by - ay) * u[1]) / math.sqrt(l2)
                if d <= TOL and cos > math.cos(math.radians(ANGLE)) and (best is None or d < best[0]):
                    best = (d, a, b, s)
        if best is None:
            continue
        _, a, b, s = best
        if (pos[b][0] - pos[a][0]) * u[0] + (pos[b][1] - pos[a][1]) * u[1] < 0:
            a, b, s = b, a, 1.0 - s
        q = (pos[a][0] + s * (pos[b][0] - pos[a][0]), pos[a][1] + s * (pos[b][1] - pos[a][1]))
        near = min((a, b), key=lambda n: math.dist(pos[n], q))
        if math.dist(pos[near], q) <= snap:
            if len(adj[near]) != 2:
                continue   # (OSM splits there already)
            S = near
            ahead = b if near == a else next(m for m in adj[b] if m != a) if len(adj[b]) == 2 else None
            if near == b and ahead is None:
                continue
            first = b if near == a else ahead
        else:
            S, first = next_id, b
            next_id -= 1
            new[S] = ('between', a, b, s)
            pos[S] = q
            for ns in [w['nodes'] for w in ways] + list(seqs):
                for i in range(len(ns) - 1, 0, -1):
                    if {ns[i - 1], ns[i]} == {a, b}:
                        ns.insert(i, S)
            adj[S] = {a, b}
            adj[a].discard(b); adj[b].discard(a); adj[a].add(S); adj[b].add(S)
        # the shared stretch ahead to the junction where the tracks part
        path, prev, cur, run = [S], S, first, math.dist(pos[S], pos[first])
        while len(adj[cur]) == 2 and run <= it['run'] + reach:
            path.append(cur)
            prev, cur = cur, next(m for m in adj[cur] if m != prev)
            run += math.dist(pos[prev], pos[cur])
        if len(adj[cur]) != 3 or run > it['run'] + reach:
            continue
        P = cur
        d_in = _unit((pos[P][0] - pos[prev][0], pos[P][1] - pos[prev][1]))
        legs = [m for m in adj[P] if m != prev]

        def out(m):
            """The leg's direction over its first metres."""
            p0, c, r = P, m, math.dist(pos[P], pos[m])
            while r < 5.0 and len(adj[c]) == 2:
                p0, c = c, next(x for x in adj[c] if x != p0)
                r += math.dist(pos[p0], pos[c])
            return _unit((pos[c][0] - pos[P][0], pos[c][1] - pos[P][1]))
        dirs = {m: out(m) for m in legs}
        if any(d_in[0] * w[0] + d_in[1] * w[1] <= 0 for w in dirs.values()):
            continue   # (not a split facing the tip)
        leg = max(legs, key=lambda m: it['side'] * (d_in[0] * dirs[m][1] - d_in[1] * dirs[m][0]))
        copy = {}
        for n in path[1:] + [P]:
            copy[n] = next_id
            new[next_id] = ('copy', n)
            pos[next_id] = pos[n]
            next_id -= 1
        # the leg leaves from P's copy; ways running on through P into it are cut there
        for w in list(ways):
            ns = w['nodes']
            for i in range(len(ns) - 1):
                if {ns[i], ns[i + 1]} == {P, leg}:
                    k = i if ns[i] == P else i + 1
                    head, tail = ns[:k + 1], ns[k:]
                    if ns[i] == P:
                        tail = [copy[P]] + tail[1:]
                        parts = [head, tail]
                    else:
                        head = head[:-1] + [copy[P]]
                        parts = [head, tail]
                    ways.remove(w)
                    ways.extend({**w, 'nodes': x} for x in parts if len(x) > 1)
                    break
        tags = next((w.get('tags', {}) for w in ways for i in range(len(w['nodes']) - 1)
                     if {w['nodes'][i], w['nodes'][i + 1]} == {S, path[1] if len(path) > 1 else P}), {})
        ways.append({'type': 'way', 'id': next_id, 'nodes': [S] + [copy[n] for n in path[1:] + [P]], 'tags': dict(tags)})
        next_id -= 1
        # routes on that leg take the copy
        shared = path + [P]
        for ns in seqs:
            for i in range(len(ns) - len(shared)):
                if ns[i:i + len(shared)] == shared and ns[i + len(shared)] == leg:
                    ns[i + 1:i + len(shared)] = [copy[n] for n in shared[1:]]
                elif ns[i + 1:i + 1 + len(shared)] == shared[::-1] and ns[i] == leg:
                    ns[i + 1:i + len(shared)] = [copy[n] for n in shared[::-1][:-1]]
    return new


def osm_graph(*answers):
    """Node positions (lat, lon) and edges of Overpass-format answers (ways with their nodes)."""
    nodes, edges = {}, set()
    for ans in answers:
        for e in ans['elements']:
            if e['type'] == 'node':
                nodes[e['id']] = (e['lat'], e['lon'])
        for e in ans['elements']:
            if e['type'] == 'way':
                for a, b in zip(e['nodes'], e['nodes'][1:]):
                    edges.add((a, b))
    return nodes, edges


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


def main():
    import glob
    import json
    from geo import Frame
    line = sys.argv[sys.argv.index('--line') + 1] if '--line' in sys.argv else '17'
    root = Path(__file__).resolve().parent.parent
    raw = root / 'raw' / f'line{line}'
    answers = [json.loads(Path(f).read_text(encoding='utf-8')) for f in [raw / 'tracks.json', *glob.glob(str(raw / 'route_*.json'))]]
    nodes, edges = osm_graph(*answers)
    frame = Frame()
    ids = list(nodes)
    x, y = frame.xy([nodes[i][0] for i in ids], [nodes[i][1] for i in ids])
    pos = {i: (float(a), float(b)) for i, a, b in zip(ids, x, y)}
    geo = TrackGeometry(pos, edges, load_sources())
    r = geo.report
    print(json.dumps({k: v for k, v in r.items() if k != 'fill'}))
    fill = sorted(r['fill'], key=lambda f: -f[1])
    print(f"OSM fill edges: {len(fill)}, {sum(f[1] for f in fill):.0f} m; longest:")
    for (a, b), l in fill[:15]:
        lat, lon = frame.ll(*geo.orig[a])
        print(f"  {l:6.1f} m  {float(lat):.5f} N {float(lon):.5f} E  ({a}-{b})")


if __name__ == '__main__':
    main()
