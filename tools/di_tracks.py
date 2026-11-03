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
                # alongside (Čechův most: DI draws the branch 13 cm off the through track for 21 m before it leaves)
OVERLAP_MIN = 3.0  # m: running alongside this far is an overlap: the fork is where it ends, else at the branch's end
BLEND = 20.0   # m along an OSM fill stretch over which it takes up the shift of its matched neighbours
CHANGE = 1.0   # m-equivalent cost of continuing on another chain along one OSM edge
JOINT = 4.0    # m: the chain may change only this near the joint of the two chains (STEP + TOL)
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
        members = defaultdict(list)
        for i in range(len(ends)):
            members[root(i)].append(i)
        # forks: places where two records leave in the same direction and move apart (two copies of one track
        # leave together and stay within centimetres: Vozovna Kobylisy, 10 m each at 98-99 degrees); each with the
        # directions its branches leave in (`branches`, unit vectors out of the fork)
        self.forks, self.branches = [], []
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
                xs = [ends[m][2] for m in ms]
                self.forks.append((sum(x for x, _ in xs) / len(xs), sum(y for _, y in xs) / len(xs)))
                self.branches.append([_unit(u) for u, _ in out])
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
        within ANGLE and moving apart (Palackého náměstí: the branch ends 19.8 m along the through track). A branch
        that first runs alongside (within OVERLAP of its distance at the end, OVERLAP_MIN or more) forks where it
        leaves (Čechův most: 13 cm off for 21 m)."""
        lines = [c['line'] for c in self.chains]
        if not lines:
            return
        tree = shapely.STRtree(lines)
        tips = [p for l in lines for p in (l.coords[0], l.coords[-1])]
        tip_tree = shapely.STRtree(shapely.points(tips))
        known = list(self.forks)
        for k, line in enumerate(lines):
            for first in (True, False):
                e = tips[2 * k + (0 if first else 1)]
                pe = Point(e)
                if any(math.dist(e, f) <= JOIN for f in known):
                    continue
                lone = not any(int(i) // 2 != k and math.dist(e, tips[int(i)]) <= JOIN for i in tip_tree.query(pe.buffer(JOIN)))
                walk = (lambda s: line.interpolate(s)) if first else (lambda s: line.interpolate(line.length - s))
                for j in tree.query(pe.buffer(JOIN)):
                    j = int(j)
                    thr = lines[j]
                    if j == k or thr.distance(pe) > JOIN:
                        continue
                    d0, s = thr.distance(pe), 0.0
                    while s + 0.5 <= line.length and thr.distance(walk(s + 0.5)) <= d0 + OVERLAP:
                        s += 0.5
                    if s < OVERLAP_MIN:
                        s = 0.0
                    # (a branch ending on the middle of a track, or leaving it after running alongside: where
                    # other records end too, Čechův most's branch starts at the through track's record joint)
                    p0 = walk(s)
                    tt = thr.project(p0)
                    if not (s or lone) or not JOIN < tt < thr.length - JOIN:
                        continue
                    if line.length - s < FORK_MIN or thr.distance(walk(min(s + FORK_OUT, line.length))) < FORK_APART:
                        continue
                    p1 = walk(s + 1.0)
                    u = _unit((p1.x - p0.x, p1.y - p0.y))
                    a, b = thr.interpolate(max(0.0, tt - 0.5)), thr.interpolate(min(thr.length, tt + 0.5))
                    v = _unit((b.x - a.x, b.y - a.y))
                    if math.degrees(math.acos(min(1.0, abs(u[0] * v[0] + u[1] * v[1])))) > ANGLE:
                        continue
                    f = thr.interpolate(tt)
                    if any(math.dist((f.x, f.y), q) <= JOIN for q in known):
                        break   # (found from the other track's end too)
                    self.forks.append((f.x, f.y))
                    self.branches.append([v, (-v[0], -v[1]), u])
                    known.append((f.x, f.y))
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

    def __init__(self, pos, edges, sources):
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
                found = src.match_path([pos[n] for n in nodes])
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
        # 2. node positions: a matched node moves onto its chain (a switch onto the source's fork when one is
        # within FORK), a node with only unmatched edges keeps OSM's position and takes up its neighbours' shift
        self.pos = {}
        # each source fork goes to the nearest OSM switch within FORK on its tracks that leaves the same way, one
        # node per fork (Palackého náměstí: two switches 4-5 m apart would both take one fork and the edge between
        # them would vanish)
        claims = []
        for n in adj:
            if len(adj[n]) < 3:
                continue
            hits = {m: self.edges[k(n, m)] for m in adj[n]}
            src = next((h[0] for h in hits.values() if h), None)
            if src is None or src.fork_tree is None:
                continue
            ms = list(adj[n])
            dirs = [_unit((pos[m][0] - pos[n][0], pos[m][1] - pos[n][1])) for m in ms]
            legs = switch_legs(dirs)
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
                if d <= FORK and collapse is not None and on(f) and same_way(dirs, src.branches[i]):
                    claims.append((d, n, (src.name, int(i)), f, collapse))
        fork_of, taken, collapsed = {}, set(), {}
        for d, n, key, f, collapse in sorted(claims, key=lambda c: c[0]):
            if n in fork_of or n in collapsed or key in taken or any(m in fork_of or m in collapsed for m in collapse):
                continue
            fork_of[n] = f
            taken.add(key)
            collapsed.update({m: f for m in collapse})
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
