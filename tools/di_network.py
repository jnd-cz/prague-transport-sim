"""DI's track network as a graph, and routes matched over it (#237).

    python -P -E tools/di_network.py --line 17     # build the network, match the line's routes, print what was found

The current DTM transport layer (DI) is the drawn network: its chains (tools/di_tracks.py `Source`, records merged
end to end) split into edges at every place where tracks meet. Nothing of OSM's graph is moved onto it; OSM says
which of it a line uses (its route relations, the GTFS shapes as now) and what it is (bridges, tunnels, switches'
tags).

**Nodes** where DI's tracks meet:
- record ends that meet (within JOIN): a fork, a crossing drawn as four records, a track end;
- a chain's lone end on another chain's middle (within ATTACH): a branch the provider did not split the through
  track for (Palackého náměstí); where the branch first runs on the track as a copy, it joins where it leaves;
- an interlaced branch (`Source.interlaced`, Čechův most, Ohrada) joins the through track at its tip;
- two chains crossing inside both (a diamond crossing drawn through).

**Passing a node:** a train goes from one edge into another only where they continue each other: their directions
out of the node (over LOOK m) within TURN of opposite. So from a switch's toe into either leg and back, straight
across a crossing; never from one leg of a switch into the other, never round a crossing's corner.

**A route** (a sequence of positions: OSM's route nodes) is matched as one sequence over the graph (a hidden
Markov model, Viterbi): every STEP m of the route a state is an edge, a direction and a place along it near the
route; the next state follows the previous along the graph, through the passes above, about as far as the route
went. A state off the network (OSM's own line) is allowed at a cost where DI has no track.
"""
import heapq
import math
import sys
from collections import defaultdict
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point
from shapely.ops import substring

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_tracks  # noqa: E402

JOIN = di_tracks.JOIN    # m: record ends this near meet
ATTACH = 0.5             # m: a lone chain end this near another chain's middle joins it there
END_CLEAR = 0.5          # m: a split point this near a chain's end is that end
LOOK = 2.0               # m along an edge for its direction out of a node
TURN = 16.0              # degrees: two edges at a node continue each other when their directions out of it are within
                         # this of opposite (measured on DI 2026-10-31: of 913 switches' diverging legs against their
                         # toe 875 lie within 5°, 912 within 15°; of 1,492 corners of four-way nodes 95 lie within 20°,
                         # the shallow crossings from 15°: Nádraží Braník's at 21-29°)
PARALLEL = 5.0           # degrees: ends of one node this near one direction run parallel
GAUNTLET_LOOK = 5.0      # m out along parallel ends where their order across the track is read
GAUNTLET_RUN = 10.0      # m out along parallel ends where a gauntlet's tracks still lie within its width
GAP = 2.0                # m: two track ends facing each other this near are one track
CROSS_GAP = 8.0          # m: two track ends facing each other across a crossing this far apart are one track
CROSS_TURN = 30.0        # degrees: such ends face each other, and the gap runs along them, within this
ARCHIVE_NEAR = 1.0       # m: the archive's axis this near both ends of a gap fills it
SHORT = 2.0              # m: nodes where tracks meet, joined by a shorter edge, are one node
ZONE = 2.7               # m: another track this near makes a junction (plain double track: 2.75-3.5 m apart)
STUB = 3.0               # m: a shorter dead-end edge from a node where tracks meet is dropped
SECTION_TURN = 60.0      # degrees: the most a section's branch may leave its legs' line at the node they end at
TWICE = 0.5              # m: two short edges between the same nodes this near each other are one track drawn twice
SECTION_LEGS = 9.0       # m: a switch drawn as a section has legs this long or shorter (Dvorecký most 4.7 m,
                         # Palackého náměstí 6.8 m; the tongues DI draws: 8.4-9 m)
PHOTO_SHARE = 0.8        # of an edge's length a photo track covers for the edge to take it


def _unit(v):
    l = math.hypot(*v) or 1.0
    return (v[0] / l, v[1] / l)


class Network:
    """nodes: {id: {'xy', 'kind'}}; edges: {id: {'a', 'b', 'line', 'src', 'records'}}, `line` from a to b;
    at[node]: [(edge, end)] the edge ends at the node (end 0: the edge starts there)."""

    def __init__(self, source, tips=(), photo=None, archive=None):
        self.source = source
        self.archive = archive
        self.nodes, self.edges = {}, {}
        self.at = defaultdict(list)
        self.report = defaultdict(int)
        self._reach = {}
        self._zones = {}
        self._build(source)
        if tips or photo is not None:
            self.move_tips(tips)
            self.take_photo(photo)
            self.index()
        self.unique_pairs()
        self.index()

    # ------------------------------------------------------------------ construction
    def _node(self, xy, kind):
        n = len(self.nodes)
        self.nodes[n] = {'xy': (float(xy[0]), float(xy[1])), 'kind': kind}
        return n

    def _build(self, src):
        chains = [c['line'] for c in src.chains]
        recs = [c['records'] for c in src.chains]
        # 1. split points per chain: {chain: [(s, node)]}; ends first
        cuts = defaultdict(list)
        tips = [(c, 0) for c in range(len(chains))] + [(c, 1) for c in range(len(chains))]
        txy = [chains[c].coords[0] if e == 0 else chains[c].coords[-1] for c, e in tips]
        ttree = shapely.STRtree(shapely.points(txy))
        group = list(range(len(tips)))

        def root(i):
            while group[i] != i:
                group[i] = group[group[i]]
                i = group[i]
            return i
        for i, xy in enumerate(txy):
            for j in ttree.query(Point(xy).buffer(JOIN)):
                if math.dist(xy, txy[int(j)]) <= JOIN:
                    group[root(int(j))] = root(i)
        members = defaultdict(list)
        for i in range(len(tips)):
            members[root(i)].append(i)
        end_node = {}
        for g, ms in members.items():
            xs = [txy[m] for m in ms]
            n = self._node((sum(x for x, _ in xs) / len(xs), sum(y for _, y in xs) / len(xs)),
                           'end' if len(ms) == 1 else 'joint' if len(ms) == 2 else 'meet')
            for m in ms:
                end_node[m] = n
        for i, (c, e) in enumerate(tips):
            cuts[c].append((0.0 if e == 0 else chains[c].length, end_node[i], None))
        # 2. lone ends on another chain's middle, interlaced branches at their tips
        ctree = shapely.STRtree(chains)
        inter = [(it['tip'], it) for it in getattr(src, 'interlaced', [])]
        joined = set()
        for i, (c, e) in enumerate(tips):
            if len(members[root(i)]) != 1:
                continue
            xy = txy[i]
            best = None
            for j in ctree.query(Point(xy).buffer(ATTACH)):
                j = int(j)
                if j == c:
                    continue
                d = chains[j].distance(Point(xy))
                s = chains[j].project(Point(xy))
                if d <= ATTACH and END_CLEAR < s < chains[j].length - END_CLEAR and (best is None or d < best[0]):
                    best = (d, j, s)
            if best is None:
                continue
            _, j, s = best
            line = chains[c] if e == 0 else LineString(chains[c].coords[::-1])
            # (a branch leaves its track within TURN: an end meeting a track's middle steeper is a crossing track the
            # provider broke there, Ohrada; _crossing_gaps joins it to its continuation)
            q = line.interpolate(min(1.0, line.length))
            vb, vt = _unit((q.x - xy[0], q.y - xy[1])), _unit(self._dir(chains[j], s))
            if abs(vb[0] * vt[0] + vb[1] * vt[1]) < math.cos(math.radians(TURN)):
                self.report['steep ends not joined as branches'] += 1
                continue
            # an interlaced branch: joins at its tip on the through track (TONGUE back where DI starts it beside)
            tip = next((t for t, it in inter if chains[j].distance(Point(t)) <= JOIN and math.dist(t, xy) <= di_tracks.TONGUE + 2.0), None)
            if tip is not None:
                s = chains[j].project(Point(tip))
                kind = 'interlaced'
            else:
                # a copy running on the track first: the branch leaves where it parts (OVERLAP)
                d0, run = chains[j].distance(Point(xy)), 0.0
                while run + 0.5 <= line.length and chains[j].distance(line.interpolate(run + 0.5)) <= d0 + di_tracks.OVERLAP:
                    run += 0.5
                if run >= di_tracks.OVERLAP_MIN:
                    p = line.interpolate(run)
                    s = chains[j].project(p)
                    # (the copy part is dropped: the branch starts where it leaves)
                    cuts[c].append((run if e == 0 else chains[c].length - run, None, 'trim'))
                    self.report['copies trimmed'] += 1
                kind = 'branch'
            if not END_CLEAR < s < chains[j].length - END_CLEAR:
                continue
            n = self._node(chains[j].interpolate(s).coords[0], kind)
            cuts[j].append((s, n, None))
            joined.add(i)
            self.report[f'{kind} joins'] += 1
            # the branch's end goes to the node
            cuts[c] = [(s0, n if (s0 == (0.0 if e == 0 else chains[c].length) and nd == end_node[i]) else nd, f)
                       for s0, nd, f in cuts[c]]
        # 3. crossings inside both chains
        for a in range(len(chains)):
            for b in ctree.query(chains[a]):
                b = int(b)
                if b <= a:
                    continue
                x = chains[a].intersection(chains[b])
                for g in getattr(x, 'geoms', [x]):
                    if g.is_empty or g.geom_type != 'Point':
                        continue
                    sa, sb = chains[a].project(g), chains[b].project(g)
                    if not (END_CLEAR < sa < chains[a].length - END_CLEAR and END_CLEAR < sb < chains[b].length - END_CLEAR):
                        continue
                    # (a touch at a fork the provider drew through is not a crossing: the angle tells)
                    da = _unit(self._dir(chains[a], sa)); db = _unit(self._dir(chains[b], sb))
                    ang = math.degrees(math.acos(min(1.0, abs(da[0] * db[0] + da[1] * db[1]))))
                    if ang < 2 * TURN / 3:
                        self.report['shallow touches'] += 1
                        continue
                    n = self._node((g.x, g.y), 'crossing')
                    cuts[a].append((sa, n, None))
                    cuts[b].append((sb, n, None))
                    self.report['crossings'] += 1
        # 4. edges between consecutive cuts
        for c, cs in cuts.items():
            cs = sorted(cs, key=lambda t: t[0])
            trim = [s for s, _, f in cs if f == 'trim']
            pts = [(s, n) for s, n, f in cs if f != 'trim']
            if trim:   # (a copy dropped: the end node moves to where the branch leaves)
                t = trim[0]
                if t < chains[c].length / 2:
                    pts = [(t, pts[0][1])] + [p for p in pts[1:] if p[0] > t]
                else:
                    pts = [p for p in pts[:-1] if p[0] < t] + [(t, pts[-1][1])]
            for (s0, a), (s1, b) in zip(pts, pts[1:]):
                if s1 - s0 < 1e-3 or a == b:
                    continue
                self.add_edge(a, b, substring(chains[c], s0, s1).coords, self.source.name, recs[c], c)
        for n, ends in self.at.items():
            k = self.nodes[n]['kind']
            if k == 'meet':
                self.nodes[n]['kind'] = 'fork' if len(ends) == 3 else 'meet'
        self._interlaced_tips(getattr(src, 'interlaced', []))
        self._gaps()
        self._stubs()
        self._crossing_gaps(self.archive)
        self._contract()
        self._sections()
        self._sections_into_junctions()
        self._twice()
        self.index()

    def _stubs(self):
        """A dead-end edge under STUB from a node where tracks meet is a scrap of a record, not a track (Kobylisy:
        0.6 m beside the track read as a switch's leg)."""
        while True:
            hit = next((e for e, ed in self.edges.items() if ed['line'].length < STUB and
                        sorted((len(self.at[ed['a']]), len(self.at[ed['b']]))) [0] == 1 and
                        max(len(self.at[ed['a']]), len(self.at[ed['b']])) >= 3), None)
            if hit is None:
                return
            ed = self.remove_edge(hit)
            for n in (ed['a'], ed['b']):
                if not self.at[n]:
                    self.nodes[n]['kind'] = 'gone'
            self.report['stubs dropped'] += 1

    def _contract(self):
        """Nodes where tracks meet, joined by an edge under SHORT, are one node: a junction DI draws in pieces
        (Nádraží Braník, line 17: a shallow crossing as two four-way nodes 0.7 m apart, its middle drawn twice as 1 m
        records; read apart, a train could turn from the route into the crossing track)."""
        while True:
            # (never a crossing point of two DI chains: it lies exactly on both; three chains crossing within 2 m at
            # Strossmayerovo náměstí, merged at their midpoint, bent all three 0.3 m towards it)
            hit = next((e for e, ed in self.edges.items() if ed['line'].length < SHORT and ed['a'] != ed['b']
                        and len(self.at[ed['a']]) >= 3 and len(self.at[ed['b']]) >= 3
                        and 'crossing' not in (self.nodes[ed['a']]['kind'], self.nodes[ed['b']]['kind'])), None)
            if hit is None:
                return
            a, b = self.edges[hit]['a'], self.edges[hit]['b']
            for e in [e for e, ed in self.edges.items() if {ed['a'], ed['b']} == {a, b} and ed['line'].length < SHORT]:
                self.remove_edge(e)
            xa, xb = self.nodes[a]['xy'], self.nodes[b]['xy']
            mid = ((xa[0] + xb[0]) / 2, (xa[1] + xb[1]) / 2)
            self.nodes[a]['xy'] = mid
            for e, end in list(self.at[b]):
                ed = self.edges[e]
                ed['a' if end == 0 else 'b'] = a
                self.at[a].append((e, end))
            self.at[b] = []
            self.nodes[b]['kind'] = 'gone'
            for e, end in self.at[a]:
                ed = self.edges[e]
                c = list(ed['line'].coords)
                c[0 if end == 0 else -1] = mid
                ed['line'] = LineString(c)
            if self.nodes[a]['kind'] in ('end', 'joint'):
                self.nodes[a]['kind'] = 'meet'
            self.report['short edges contracted'] += 1

    def _sections(self):
        """A switch drawn as a section (Podolská vodárna, Dvorecký most): from its tip X two legs as records of
        SECTION_LEGS m or less end together at Y, where the two tracks go on. The switch is at the tip: the two
        legs go, the tracks leaving Y start at X (each with one leg's points before its own)."""
        for X in list(self.at):
            ends = self.at[X]
            if len(ends) != 3:
                continue
            far = defaultdict(list)
            for e, end in ends:
                ed = self.edges[e]
                if ed['line'].length <= SECTION_LEGS:
                    far[ed['b'] if end == 0 else ed['a']].append((e, end))
            Y, legs = next(((y, ls) for y, ls in far.items() if len(ls) == 2 and y != X), (None, None))
            if Y is None or len(self.at[Y]) != 4:
                continue
            leg_ids = {e for e, _ in legs}
            onward = [x for x in self.at[Y] if x[0] not in leg_ids]
            if len(onward) != 2:
                continue
            pieces = []
            for e, end in legs:
                ed = self.remove_edge(e)
                c = list(ed['line'].coords)
                pieces.append(c if end == 0 else c[::-1])   # from X to Y
            for (e, end), piece in zip(onward, pieces):
                ed = self.remove_edge(e)
                c = list(ed['line'].coords)
                if end == 0:
                    self.add_edge(X, ed['b'], piece[:-1] + c, ed['src'], ed['records'])
                else:
                    self.add_edge(ed['a'], X, c + piece[::-1][1:], ed['src'], ed['records'])
            self.nodes[X]['kind'] = 'fork'
            self.nodes[Y]['kind'] = 'gone'
            self.report['sections to their tips'] += 1

    def _sections_into_junctions(self):
        """A switch drawn as a section whose two legs end at a node where other tracks meet too (Strossmayerovo náměstí:
        from the fork both legs run side by side 8 m into a crossing, where the diverging curve leaves 35° off; the user,
        2026-11-05, "the both di forks are fine"): the straight leg stays; the other leg goes and the diverging track
        starts at the fork, DI's points from where it leaves on (the fit joins it to the fork tangent). Tracks crossing
        through the node (two ends of one chain) are not the branch."""
        cos_t = math.cos(math.radians(TURN))
        cos_max = math.cos(math.radians(SECTION_TURN))
        for X in list(self.at):
            ends = self.at[X]
            if len(ends) != 3:
                continue
            far = defaultdict(list)
            for e, end in ends:
                ed = self.edges[e]
                if ed['line'].length <= SECTION_LEGS:
                    far[ed['b'] if end == 0 else ed['a']].append((e, end))
            Y, legs = next(((y, ls) for y, ls in far.items() if len(ls) == 2 and y != X), (None, None))
            if Y is None or len(self.at[Y]) <= 4:
                continue
            leg_ids = {e for e, _ in legs}
            at_y = [x for x in self.at[Y] if x[0] not in leg_ids]
            chain_n = defaultdict(int)
            for e, _ in at_y:
                chain_n[self.edges[e].get('chain')] += 1
            free = [x for x in at_y if chain_n[self.edges[x[0]].get('chain')] < 2]
            # the legs arrive at Y in direction u (into Y): the straight continuation leaves along u, the branch off it
            l0 = legs[0]
            arrive = self.out_dir(l0[0], 1 - l0[1])
            u = (-arrive[0], -arrive[1])
            dev = lambda x, u=u: u[0] * self.out_dir(*x)[0] + u[1] * self.out_dir(*x)[1]
            straight = [x for x in free if dev(x) >= cos_t]
            branch = [x for x in free if cos_max <= dev(x) < cos_t]
            if len(straight) != 1 or len(branch) != 1:
                continue
            # (the leg off the straight track's line goes: both run within centimetres, the kept one must continue the
            # straight track without an angle; Strossmayerovo náměstí kept the branch's and bent it 0.21 m)
            yx, yy = self.nodes[Y]['xy']
            off = lambda leg, u=u, yx=yx, yy=yy: max(abs(u[0] * (q[1] - yy) - u[1] * (q[0] - yx))
                                                    for q in self.edges[leg[0]]['line'].coords)
            gone = max(legs, key=off)
            self.remove_edge(gone[0])
            b, bend = branch[0]
            ed = self.remove_edge(b)
            c = list(ed['line'].coords)
            xy = self.nodes[X]['xy']
            if bend == 0:
                self.add_edge(X, ed['b'], [xy] + c[1:], ed['src'], ed['records'], ed.get('chain'))
            else:
                self.add_edge(ed['a'], X, c[:-1] + [xy], ed['src'], ed['records'], ed.get('chain'))
            self.report['sections into junctions'] += 1

    def _twice(self):
        """Two short edges (SECTION_LEGS or less) between the same two nodes, within TWICE of each other, are one track
        drawn twice: one goes (Strossmayerovo náměstí: two 8 m records from a fork into the crossing; the user,
        2026-11-05: the DI forks there are right, the bend came from the double). A gauntlet's tracks are longer."""
        by = defaultdict(list)
        for e, ed in self.edges.items():
            if ed['a'] != ed['b'] and ed['line'].length <= SECTION_LEGS:
                by[frozenset((ed['a'], ed['b']))].append(e)
        for es in by.values():
            keep = es[0]
            for e in es[1:]:
                if e in self.edges and self.edges[e]['line'].hausdorff_distance(self.edges[keep]['line']) <= TWICE:
                    self.remove_edge(e)
                    self.report['tracks drawn twice'] += 1

    def split_at(self, e, s, n):
        """Edge e split s m along it at the existing node n (moved nowhere: the pieces end at n's place)."""
        ed = self.remove_edge(e)
        line = ed['line']
        self.add_edge(ed['a'], n, substring(line, 0, s).coords, ed['src'], ed['records'], ed.get('chain'))
        self.add_edge(n, ed['b'], substring(line, s, line.length).coords, ed['src'], ed['records'], ed.get('chain'))

    def _crossing_gaps(self, archive):
        """Two track ends facing each other across a gap of up to CROSS_GAP are one track the provider broke where
        it crosses another (Ohrada: the track from the east ends on the through track, its continuation starts 5 m on;
        the user, 2026-11-05: "sadly missing piece of data ... fill it here with a nice curve fit"). They are joined
        along the archive's axis where it runs within ARCHIVE_NEAR of both ends, else straight (the curve fit smooths
        it as fill); where the joint crosses another track the two meet in a crossing, each going on as itself."""
        # (an end left without a continuation at a node where tracks meet: none of the node's other ends lies within
        # TURN of opposite it, Ohrada; it leaves the node for its own, to be joined across the gap)
        cos_t = math.cos(math.radians(180 - TURN))
        for n0 in [n for n in list(self.at) if len(self.at[n]) >= 3]:
            for x in list(self.at[n0]):
                d = self.out_dir(*x)
                if any(d[0] * self.out_dir(*y)[0] + d[1] * self.out_dir(*y)[1] <= cos_t for y in self.at[n0] if y != x):
                    continue
                e, end = x
                n1 = self._node(self.nodes[n0]['xy'], 'end')
                self.at[n0].remove(x)
                self.at[n1].append(x)
                self.edges[e]['a' if end == 0 else 'b'] = n1
                self.report['dead ends detached from a junction'] += 1
        ends = [n for n, v in self.nodes.items() if len(self.at[n]) == 1]
        if not ends:
            return
        tree = shapely.STRtree(shapely.points([self.nodes[n]['xy'] for n in ends]))
        arch = [c['line'] for c in archive.chains] if archive is not None else []
        atree = shapely.STRtree(arch) if arch else None
        cos_face = math.cos(math.radians(180 - CROSS_TURN))
        done = set()
        for n in ends:
            if n in done or len(self.at[n]) != 1:
                continue
            p = self.nodes[n]['xy']
            u = self.out_dir(*self.at[n][0])      # into the track: the gap lies the other way
            best = None
            for j in tree.query(Point(p).buffer(CROSS_GAP)):
                m = ends[int(j)]
                if m == n or m in done or len(self.at[m]) != 1:
                    continue
                q = self.nodes[m]['xy']
                v = self.out_dir(*self.at[m][0])
                g = math.dist(p, q)
                w = _unit((q[0] - p[0], q[1] - p[1]))
                if GAP < g <= CROSS_GAP and u[0] * v[0] + u[1] * v[1] <= cos_face \
                        and -(u[0] * w[0] + u[1] * w[1]) >= math.cos(math.radians(CROSS_TURN)) and (best is None or g < best[0]):
                    best = (g, m)
            if best is None:
                continue
            m = best[1]
            q = self.nodes[m]['xy']
            coords, src = [p, q], 'gap'
            if atree is not None:
                for k in atree.query(LineString([p, q]).buffer(ARCHIVE_NEAR)):
                    a = arch[int(k)]
                    if a.distance(Point(p)) <= ARCHIVE_NEAR and a.distance(Point(q)) <= ARCHIVE_NEAR:
                        s0, s1 = a.project(Point(p)), a.project(Point(q))
                        piece = substring(a, min(s0, s1), max(s0, s1))
                        c = list(piece.coords) if s0 <= s1 else list(piece.coords)[::-1]
                        coords, src = [p] + c[1:-1] + [q], 'dtmp'
                        break
            chain = f'gap-{n}-{m}'
            e = self.add_edge(n, m, coords, src, [], chain)
            done.update((n, m))
            self.nodes[n]['kind'] = self.nodes[m]['kind'] = 'gap'
            self.report['crossing gaps filled'] += 1
            # where the joint crosses another track: a crossing node on both
            for f in [f for f, fd in self.edges.items() if f != e and fd['line'].crosses(self.edges[e]['line'])]:
                x = self.edges[f]['line'].intersection(self.edges[e]['line'])
                if x.geom_type != 'Point':
                    continue
                le, lf = self.edges[e]['line'], self.edges[f]['line']
                se, sf = le.project(x), lf.project(x)
                if not (END_CLEAR < sf < lf.length - END_CLEAR and END_CLEAR < se < le.length - END_CLEAR):
                    continue
                c = self._node((x.x, x.y), 'crossing')
                self.split_at(f, sf, c)
                self.split_at(e, se, c)
                e = next(g for g, gd in self.edges.items() if gd.get('chain') == chain and c in (gd['a'], gd['b']) and m in (gd['a'], gd['b']))
                self.report['crossings on filled gaps'] += 1

    def _gaps(self):
        """Two track ends facing each other within GAP join with a straight edge: a record the provider ended short
        (Kobyliské náměstí, line 17: 1.1 m between two ends of one track)."""
        ends = [n for n, v in self.nodes.items() if len(self.at[n]) == 1]
        tree = shapely.STRtree(shapely.points([self.nodes[n]['xy'] for n in ends]))
        cos = math.cos(math.radians(180 - TURN))
        done = set()
        for n in ends:
            if n in done:
                continue
            p = self.nodes[n]['xy']
            u = self.out_dir(*self.at[n][0])
            best = None
            for j in tree.query(Point(p).buffer(GAP)):
                m = ends[int(j)]
                if m == n or m in done:
                    continue
                q = self.nodes[m]['xy']
                v = self.out_dir(*self.at[m][0])
                g = math.dist(p, q)
                w = _unit((q[0] - p[0], q[1] - p[1]))
                # (facing each other, the gap along their direction: n's track leaves away from m)
                if g <= GAP and u[0] * v[0] + u[1] * v[1] <= cos and -(u[0] * w[0] + u[1] * w[1]) >= math.cos(math.radians(TURN)) \
                        and (best is None or g < best[0]):
                    best = (g, m)
            if best:
                g, m = best
                e = self.at[n][0][0]
                self.add_edge(n, m, [self.nodes[n]['xy'], self.nodes[m]['xy']], self.edges[e]['src'], [])
                self.nodes[n]['kind'] = self.nodes[m]['kind'] = 'gap'
                done.update((n, m))
                self.report['gaps joined'] += 1

    def unique_pairs(self):
        """Every edge between two different nodes and no two edges between the same pair (the curve fit keys its
        edges by their nodes): a loop or a second edge splits at its middle (the gauntlet's two tracks between the
        same two nodes)."""
        seen = set()
        for e in list(self.edges):
            ed = self.edges[e]
            key = frozenset((ed['a'], ed['b']))
            if ed['a'] == ed['b'] or key in seen:
                self.split(e, ed['line'].length / 2, 'mid')
                self.report['edges split for a unique pair'] += 1
            else:
                seen.add(key)

    def through(self, n):
        """A switch node's ends: (toe, through leg, diverging leg) by the passes and directions, or None."""
        ends = self.at[n]
        if len(ends) != 3:
            return None
        dirs = {x: self.out_dir(*x) for x in ends}
        toe = next((x for x in ends if len(self.passes.get(x, ())) == 2), None)
        if toe is None:
            return None
        legs = self.passes[toe]
        d0 = dirs[toe]
        a, b = sorted(legs, key=lambda y: d0[0] * dirs[y][0] + d0[1] * dirs[y][1])   # most opposite first
        return toe, a, b

    def move_tips(self, tips):
        """A switch whose tip the user placed (data/truth.json trackSources.switchTips: [(near, tip)] in city metres)
        forks at the point of its through track nearest the tip: the through edge splits there and the diverging
        leg starts at it (Podolská vodárna: 3.3 m east of DI's fork, at the manhole)."""
        for near, tip in tips:
            forks = [(math.dist(v['xy'], near), n) for n, v in self.nodes.items()
                     if math.dist(v['xy'], near) <= di_tracks.FORK and self.through(n)]
            if not forks:
                self.report['switch tips without a fork'] += 1
                continue
            F = min(forks)[1]
            toe, thr, div = self.through(F)
            best = None
            for x in (toe, thr):
                line = self.edges[x[0]]['line']
                s = line.project(Point(tip))
                d = line.distance(Point(tip))
                if END_CLEAR < s < line.length - END_CLEAR and (best is None or d < best[0]):
                    best = (d, x, s)
            if best is None or math.dist(self.nodes[F]['xy'], tip) <= END_CLEAR:
                self.report['switch tips at their fork already'] += 1
                continue
            _, x, s = best
            fx, fy = self.nodes[F]['xy']
            Q = self.split(x[0], s, 'tip')
            # (a tip behind the fork: the branch runs along the through track from the tip to the fork first, a long
            # thin switch, Ohrada; ahead of it, the branch starts at the tip)
            lead = [self.nodes[Q]['xy']]
            if x == toe:
                toe_e = next(e for e, end in self.at[Q] if e != div[0] and
                             {self.edges[e]['a'], self.edges[e]['b']} == {Q, F})
                c = list(self.edges[toe_e]['line'].coords)
                lead = c if self.edges[toe_e]['a'] == Q else c[::-1]
                lead = lead[:-1]
            ed = self.remove_edge(div[0])
            coords = list(ed['line'].coords)
            if div[1] == 0:
                self.add_edge(Q, ed['b'], lead + ([(fx, fy)] if x == toe else []) + coords[1:], ed['src'], ed['records'])
            else:
                self.add_edge(ed['a'], Q, coords[:-1] + ([(fx, fy)] if x == toe else []) + lead[::-1], ed['src'], ed['records'])
            self.nodes[F]['kind'] = 'joint'
            self.report['switch tips placed'] += 1

    def take_photo(self, photo):
        """Tracks measured on the orthophoto the user took over DI's (data/truth.json photoTracks): an edge the photo
        track covers along PHOTO_SHARE of its length within di_tracks.PHOTO_COVER takes the photo's line between its
        nodes."""
        if photo is None:
            return
        for ch in photo.chains:
            pl = ch['line']
            for e in list(self.edges):
                line = self.edges[e]['line']
                if line.distance(pl) > di_tracks.PHOTO_COVER:
                    continue
                n = max(2, int(line.length))
                near = sum(pl.distance(line.interpolate(line.length * i / n)) <= di_tracks.PHOTO_COVER for i in range(n + 1))
                if near < PHOTO_SHARE * (n + 1):
                    continue
                s0, s1 = pl.project(Point(line.coords[0])), pl.project(Point(line.coords[-1]))
                piece = substring(pl, min(s0, s1), max(s0, s1))
                coords = list(piece.coords) if s0 <= s1 else list(piece.coords)[::-1]
                ed = self.edges[e]
                coords[0], coords[-1] = self.nodes[ed['a']]['xy'], self.nodes[ed['b']]['xy']
                ed['line'] = LineString(coords)
                ed['src'], ed['records'] = 'ortho', ch['records']
                self.report['edges from the orthophoto'] += 1

    def index(self):
        """The search tree and the passes, after the edges changed."""
        self._zones, self._reach = {}, {}
        self.eids = list(self.edges)
        self.tree = shapely.STRtree([self.edges[e]['line'] for e in self.eids])
        self._passes()

    # ------------------------------------------------------------------ editing
    def add_edge(self, a, b, coords, src, records, chain=None):
        # (the line gets points every END_STEP before its ends go to its nodes' places: a node sits where record ends
        # meet, at a crossing point or between merged nodes, up to decimetres off this record's end, and DI draws
        # straight track with vertices tens of metres apart; moved alone, the end point turned the whole first
        # segment: Strossmayerovo náměstí, 12 m of straight 0.1-0.4 m off its record)
        coords = dense(list(coords), END_STEP) if len(coords) > 1 else list(coords)
        coords[0], coords[-1] = self.nodes[a]['xy'], self.nodes[b]['xy']
        e = max(self.edges, default=-1) + 1
        self.edges[e] = {'a': a, 'b': b, 'line': LineString(coords), 'src': src, 'records': records, 'chain': chain}
        self.at[a].append((e, 0))
        self.at[b].append((e, 1))
        return e

    def remove_edge(self, e):
        ed = self.edges.pop(e)
        self.at[ed['a']].remove((e, 0))
        self.at[ed['b']].remove((e, 1))
        return ed

    def split(self, e, s, kind):
        """A new node at s m along edge e, the edge split there; the node."""
        ed = self.edges[e]
        line = ed['line']
        n = self._node(line.interpolate(s).coords[0], kind)
        self.remove_edge(e)
        self.add_edge(ed['a'], n, substring(line, 0, s).coords, ed['src'], ed['records'], ed.get('chain'))
        self.add_edge(n, ed['b'], substring(line, s, line.length).coords, ed['src'], ed['records'], ed.get('chain'))
        return n

    def _interlaced_tips(self, interlaced):
        """An interlaced branch DI starts beside the track at a record joint (the fork there) is joined at its tip
        (`Source.interlaced`, a tongue back along the track): the through edge splits at the tip and the branch's
        end moves there, the piece from the tip to where DI starts it drawn straight (Čechův most: 13 cm beside the
        track for 8.5 m)."""
        for it in interlaced:
            tip, u, side = it['tip'], it['dir'], it['side']
            near = [(math.dist(v['xy'], tip), n) for n, v in self.nodes.items()
                    if math.dist(v['xy'], tip) <= di_tracks.TONGUE + 8.0]
            if not near or min(near)[0] <= 1.0:
                continue
            # the node ahead of the tip where branch and track part (three or more ends)
            ahead = [(d, n) for d, n in near if len(self.at[n]) >= 3 and
                     (self.nodes[n]['xy'][0] - tip[0]) * u[0] + (self.nodes[n]['xy'][1] - tip[1]) * u[1] > 0]
            if not ahead:
                self.report['interlaced tips without a node ahead'] += 1
                continue
            J = min(ahead)[1]
            jx, jy = self.nodes[J]['xy']
            outs = [(e, end) for e, end in self.at[J] if self.out_dir(e, end)[0] * u[0] + self.out_dir(e, end)[1] * u[1] > 0.5]
            ins = [(e, end) for e, end in self.at[J] if (e, end) not in outs]
            if len(outs) != 2 or len(ins) != 1:
                self.report['interlaced tips without a switch (gauntlet)'] += 1
                continue

            def far(x):
                line = self.edges[x[0]]['line']
                q = line.interpolate(min(5.0, line.length) if x[1] == 0 else max(0.0, line.length - 5.0))
                return (q.x, q.y)
            # the branch: the out edge on the branch's side of the other one
            a, b = outs
            pa, pb = far(a), far(b)
            cross = u[0] * (pa[1] - pb[1]) - u[1] * (pa[0] - pb[0])
            branch = a if (cross > 0) == (side > 0) else b
            e_in, end_in = ins[0]
            line = self.edges[e_in]['line']
            s = line.project(Point(tip))
            if not END_CLEAR < s < line.length - END_CLEAR:
                self.report['interlaced tips off the track edge'] += 1
                continue
            T = self.split(e_in, s, 'interlaced')
            ed = self.remove_edge(branch[0])
            coords = list(ed['line'].coords)
            if branch[1] == 0:
                self.add_edge(T, ed['b'], [self.nodes[T]['xy']] + coords, ed['src'], ed['records'])
            else:
                self.add_edge(ed['a'], T, coords + [self.nodes[T]['xy']], ed['src'], ed['records'])
            self.nodes[J]['kind'] = 'joint'
            self.report['interlaced joins'] += 1

    @staticmethod
    def _dir(line, s):
        p, q = line.interpolate(max(0.0, s - 0.5)), line.interpolate(min(line.length, s + 0.5))
        return (q.x - p.x, q.y - p.y)

    def out_dir(self, e, end):
        """The unit direction out of edge e's end `end` (0: its start) into the edge, over LOOK m."""
        line = self.edges[e]['line']
        p0 = line.coords[0] if end == 0 else line.coords[-1]
        q = line.interpolate(min(LOOK, line.length) if end == 0 else max(0.0, line.length - LOOK))
        return _unit((q.x - p0[0], q.y - p0[1]))

    def _passes(self):
        """self.passes[(edge, end)]: the (edge, end) pairs a train may leave the node by, arriving by this end."""
        cos = math.cos(math.radians(180 - TURN))
        par = math.cos(math.radians(PARALLEL))
        self.passes = {}
        paired = 0
        for n, ends in self.at.items():
            if not ends:
                continue
            dirs = {x: self.out_dir(*x) for x in ends}
            for x in ends:
                self.passes[x] = [y for y in ends if y != x and dirs[x][0] * dirs[y][0] + dirs[x][1] * dirs[y][1] <= cos]
            # parallel tracks meeting at one node, two or more each way (a gauntlet, Malostranské náměstí: two tracks
            # 9 cm apart, their records ending together): each continues the one on its own side
            d = dirs[ends[0]]
            one = [x for x in ends if dirs[x][0] * d[0] + dirs[x][1] * d[1] >= par]
            two = [x for x in ends if dirs[x][0] * d[0] + dirs[x][1] * d[1] <= -par]
            # (only where the tracks on each side still run within a gauntlet's width 10 m out: two switches meeting at
            # one node, Královka, spread apart there)
            def close(xs):
                for i, a in enumerate(xs):
                    for b in xs[:i]:
                        d = min(GAUNTLET_RUN, self.edges[a[0]]['line'].length, self.edges[b[0]]['line'].length)
                        if self.edges[b[0]]['line'].distance(self._ahead(a, d)) > di_tracks.INTERLACE[1]:
                            return False
                return True
            if len(one) >= 2 and len(one) == len(two) and len(one) + len(two) == len(ends) and close(one) and close(two):
                nx, ny = self.nodes[n]['xy']
                side = lambda x, d=d, nx=nx, ny=ny: (lambda q: d[0] * (q.y - ny) - d[1] * (q.x - nx))(self._ahead(x, GAUNTLET_LOOK))
                one.sort(key=side)
                two.sort(key=side)
                for a, b in zip(one, two):
                    self.passes[a], self.passes[b] = [b], [a]
                paired += 1
        # two DI chains crossing through each other (a node of kind 'crossing'): each goes on only as itself, however
        # shallow (Vozovna Kobylisy: 14-15°, within TURN)
        for n, ends in self.at.items():
            if self.nodes[n]['kind'] != 'crossing':
                continue
            by = defaultdict(list)
            for x in ends:
                by[self.edges[x[0]].get('chain')].append(x)
            # (each chain running through: its two ends pass only each other; the other ends not into them)
            through = {k: v for k, v in by.items() if k is not None and len(v) == 2}
            paired = {x for v in through.values() for x in v}
            for a, b in through.values():
                self.passes[a], self.passes[b] = [b], [a]
            for x in ends:
                if x not in paired:
                    self.passes[x] = [y for y in self.passes[x] if y not in paired]
        # (two track ends joined across a gap: a train passes, whatever the bend; the fit smooths it)
        for n, ends in self.at.items():
            if self.nodes[n]['kind'] == 'gap' and len(ends) == 2:
                self.passes[ends[0]], self.passes[ends[1]] = [ends[1]], [ends[0]]
        dead = sum(1 for n, ends in self.at.items() if len(ends) >= 2 and all(not self.passes[x] for x in ends))
        self.report['nodes nobody passes'] = dead
        self.report['parallel meets paired'] = paired

    def _ahead(self, x, dist):
        line = self.edges[x[0]]['line']
        return line.interpolate(min(dist, line.length) if x[1] == 0 else max(0.0, line.length - dist))

    def summary(self):
        kinds = defaultdict(int)
        for v in self.nodes.values():
            kinds[v['kind']] += 1
        return {'nodes': len(self.nodes), 'edges': len(self.edges), 'kinds': dict(kinds), **self.report}

    def in_zone(self, e, t):
        """Whether t m along edge e lies in a junction: another track within ZONE m, not one this edge continues into
        at its ends (DI 2026-10-31: plain double track lies 2.75-3.5 m apart, 205 km of it; junctions below)."""
        z = self._zones.get(e)
        if z is None:
            ed = self.edges[e]
            skip = {e} | {f for end in (0, 1) for f, _ in self.passes.get((e, end), ())}
            line = ed['line']
            n = max(1, int(line.length))
            inside = []
            for i in range(n + 1):
                p = line.interpolate(line.length * i / n)
                near = [self.eids[int(j)] for j in self.tree.query(p.buffer(ZONE))]
                inside.append(any(f not in skip and self.edges[f]['line'].distance(p) < ZONE for f in near))
            z = []
            for i, v in enumerate(inside):
                if v:
                    a, b = line.length * max(0, i - 1) / n, line.length * min(n, i + 1) / n
                    if z and a <= z[-1][1]:
                        z[-1] = (z[-1][0], b)
                    else:
                        z.append((a, b))
            self._zones[e] = z
        return any(a <= t <= b for a, b in z)

    # ------------------------------------------------------------------ travel
    def reach(self, e, end, bound):
        """{(edge, end entered by): distance} from leaving edge e by its end `end` (at that node), over the passes, up
        to `bound` m (the distance counts the edges passed whole, not the one entered)."""
        key = (e, end, bound)
        hit = self._reach.get(key)
        if hit is not None:
            return hit
        out, heap = {}, [(0.0, e, end)]
        seen = set()
        while heap:
            d, x, xe = heapq.heappop(heap)
            if (x, xe) in seen:
                continue
            seen.add((x, xe))
            for y, ye in self.passes.get((x, xe), ()):
                if (y, ye) not in out or d < out[(y, ye)]:
                    out[(y, ye)] = d
                nd = d + self.edges[y]['line'].length
                if nd <= bound:
                    heapq.heappush(heap, (nd, y, 1 - ye))
        self._reach[key] = out
        return out


# the matcher's weights
STEP = 2.0          # m between the route's samples
RADIUS = 8.0        # m: edges this near a sample are its candidates
SIGMA = 1.5         # m: the spread of the route's positions about the track (OSM's 2.2 m at Anděl costs 1.1)
HEADING = 45.0      # degrees: a candidate edge runs within this of the route's direction
TURN_COST = 2.0     # per unit of (1 - cos) between the route's direction and the edge's
BETA = 1.0          # m: a metre of difference between the route's step and the distance along the network costs 1
OFF_COST = 8.0      # per sample off the network (OSM's own line): a sample 4.9 m from a track costs as much
OFF_SWITCH = 20.0   # to leave the network or come back to it
ZONE_WEIGHT = 0.05  # of a sample's position and heading cost inside a junction: OSM's line there is not trusted (it
                    # snaps to the wrong track, Anděl); the network's connections between the anchors decide


class Match:
    """A route matched over the network. pts: the route's positions in order (OSM's route nodes).
    After construction: `pieces` [(edge, dir, t0, t1) | ('off', [points])] in order (dir 1: along the edge's line,
    t along it), `node_s` the route position of each input point along the matched line, `points` the line,
    `edges` the edges used, `report`."""

    def __init__(self, net, pts):
        self.net = net
        if not hasattr(net, '_reach'):
            net._reach = {}
        # samples: every input point, and points between them at most STEP apart
        samples, owner = [], []
        clean = [pts[0]] + [p for p, q in zip(pts[1:], pts) if math.dist(p, q) > 1e-6]
        for i, p in enumerate(clean):
            if i:
                q = clean[i - 1]
                n = math.ceil(math.dist(p, q) / STEP)
                for k in range(1, n):
                    samples.append((q[0] + (p[0] - q[0]) * k / n, q[1] + (p[1] - q[1]) * k / n))
                    owner.append(None)
            samples.append(tuple(p))
            owner.append(i)
        self.samples = samples
        heads = []
        for k in range(len(samples)):
            a, b = samples[max(0, k - 1)], samples[min(len(samples) - 1, k + 1)]
            heads.append(_unit((b[0] - a[0], b[1] - a[1])))
        steps = [0.0] + [math.dist(a, b) for a, b in zip(samples, samples[1:])]
        cands = [self._candidates(p, h) for p, h in zip(samples, heads)]
        # Viterbi: state = (edge, dir, t) or None (off the network)
        prev = {None: (OFF_COST + OFF_SWITCH, None)}
        for c, (e, dr, t, cost) in cands[0].items():
            prev[c] = (cost, None)
        back = [prev]
        for k in range(1, len(samples)):
            cur = {}
            states = list(cands[k].items()) + [(None, None)]
            for c, info in states:
                emit = info[3] if info else OFF_COST
                best = None
                for pc, (pcost, _) in prev.items():
                    tr = self._transition(pc, cands[k - 1].get(pc) if pc else None, c, info, steps[k])
                    if tr is None:
                        continue
                    v = pcost + tr
                    if best is None or v < best[0]:
                        best = (v, pc)
                if best is not None:
                    cur[c] = (best[0] + emit, best[1])
            back.append(cur)
            prev = cur
        # the best end, back to the start
        c = min(prev, key=lambda x: prev[x][0])
        self.cost = prev[c][0]
        seq = []
        for k in range(len(samples) - 1, -1, -1):
            seq.append(c)
            c = back[k][c][1]
        seq.reverse()
        self.states = [(cands[k][c][:3] if c is not None else None) for k, c in enumerate(seq)]
        self._pieces(owner, clean)

    def _candidates(self, p, h):
        """{key: (edge, dir, t, emission cost)} of the edges within RADIUS of p running within HEADING of h."""
        out = {}
        pt = Point(p)
        cos = math.cos(math.radians(HEADING))
        for i in self.net.tree.query(pt.buffer(RADIUS)):
            e = self.net.eids[int(i)]
            line = self.net.edges[e]['line']
            d = line.distance(pt)
            if d > RADIUS:
                continue
            t = line.project(pt)
            v = _unit(Network._dir(line, t))
            c = v[0] * h[0] + v[1] * h[1]
            if abs(c) < cos:
                continue
            dr = 1 if c > 0 else -1
            w = ZONE_WEIGHT if self.net.in_zone(e, t) else 1.0
            out[(e, dr)] = (e, dr, t, w * (0.5 * (d / SIGMA) ** 2 + TURN_COST * (1 - abs(c))))
        return out

    def _transition(self, pc, pinfo, c, info, step):
        """The cost from state pc to c over a route step, None where c cannot follow pc."""
        if pc is None and c is None:
            return 0.0
        if pc is None or c is None:
            return OFF_SWITCH
        e1, d1, t1 = pinfo[:3]
        e2, d2, t2 = info[:3]
        if (e1, d1) == (e2, d2):
            run = (t2 - t1) * d1
            if run < -0.5:
                return None
            return abs(run - step) / BETA
        len1 = self.net.edges[e1]['line'].length
        rem = (len1 - t1) if d1 > 0 else t1
        bound = step * 2 + 10.0
        if rem > bound:
            return None
        reach = self.net.reach(e1, 1 if d1 > 0 else 0, round(bound - rem + 0.5))
        entry = 0 if d2 > 0 else 1
        if (e2, entry) not in reach:
            return None
        len2 = self.net.edges[e2]['line'].length
        run = rem + reach[(e2, entry)] + (t2 if d2 > 0 else len2 - t2)
        return abs(run - step) / BETA

    def _pieces(self, owner, clean):
        """The matched line: pieces along edges and off the network, and where each input point lies on it."""
        net, pieces = self.net, []
        sample_s = []
        s = 0.0

        def add(e, dr, t0, t1):
            nonlocal s
            if pieces and pieces[-1][0] == e and pieces[-1][1] == dr:
                pieces[-1] = (e, dr, pieces[-1][2], t1)
            else:
                pieces.append((e, dr, t0, t1))
            s += abs(t1 - t0)
        prev = None
        for k, st in enumerate(self.states):
            if st is None:
                p = self.samples[k]
                if pieces and pieces[-1][0] == 'off':
                    s += math.dist(pieces[-1][1][-1], p)
                    pieces[-1][1].append(p)
                else:
                    if pieces and prev is not None:
                        q = net.edges[prev[0]]['line'].interpolate(prev[2])
                        s += math.dist((q.x, q.y), p)
                        pieces.append(('off', [(q.x, q.y), p]))
                    else:
                        pieces.append(('off', [p]))
                sample_s.append(s)
                prev = None
                continue
            e, dr, t = st
            if prev is None:
                if pieces and pieces[-1][0] == 'off':
                    q = net.edges[e]['line'].interpolate(t)
                    s += math.dist(pieces[-1][1][-1], (q.x, q.y))
                    pieces[-1][1].append((q.x, q.y))
                pieces.append((e, dr, t, t))
            elif (prev[0], prev[1]) == (e, dr):
                add(e, dr, prev[2], max(t, prev[2]) if dr > 0 else min(t, prev[2]))
            else:
                # through the network from prev to this state: the shortest way over the passes
                for (x, xd, a, b) in self._between(prev, st):
                    add(x, xd, a, b)
            sample_s.append(s)
            if pieces[-1][0] != 'off':
                last = pieces[-1]
                prev = (last[0], last[1], last[3])
            else:
                prev = st
        self.pieces = [p for p in pieces if p[0] == 'off' or abs(p[3] - p[2]) > 1e-6 or len(pieces) == 1]
        self.node_s = [sample_s[k] for k, o in enumerate(owner) if o is not None]
        self.length = s
        self.edges = {p[0] for p in self.pieces if p[0] != 'off'}
        pts = []
        for p in self.pieces:
            if p[0] == 'off':
                seg = p[1]
            else:
                line = net.edges[p[0]]['line']
                seg = [(q.x, q.y) for q in [line.interpolate(p[2])]] + \
                      [c for c, cs in zip(line.coords, _acc(line)) if min(p[2], p[3]) < cs < max(p[2], p[3])][::(1 if p[1] > 0 else -1)] + \
                      [(q.x, q.y) for q in [line.interpolate(p[3])]]
            for q in seg:
                if not pts or math.dist(pts[-1], q) > 0.01:
                    pts.append(q)
        self.points = pts
        off = sum(math.dist(a, b) for p in self.pieces if p[0] == 'off' for a, b in zip(p[1], p[1][1:]))
        self.report = {'samples': len(self.samples), 'pieces': len(self.pieces), 'edges': len(self.edges),
                       'off_m': round(off, 1), 'length_m': round(s, 1), 'cost': round(self.cost, 1)}
        # (where the route ran off the network: the first point and the length of each such piece)
        self.off = [(p[1][0], sum(math.dist(a, b) for a, b in zip(p[1], p[1][1:]))) for p in self.pieces if p[0] == 'off']

    def _between(self, a, b):
        """[(edge, dir, t0, t1)] from state a to state b over the passes, a's edge to its end first."""
        net = self.net
        e1, d1, t1 = a
        e2, d2, t2 = b
        len1 = net.edges[e1]['line'].length
        out = [(e1, d1, t1, len1 if d1 > 0 else 0.0)]
        # Dijkstra with parents from leaving e1
        start = (e1, 1 if d1 > 0 else 0)
        heap, par, seen = [(0.0, start)], {start: None}, set()
        goal = (e2, 0 if d2 > 0 else 1)
        found = None
        while heap:
            d, (x, xe) = heapq.heappop(heap)
            if (x, xe) in seen:
                continue
            seen.add((x, xe))
            for y, ye in net.passes.get((x, xe), ()):
                if (y, ye) == goal:
                    par.setdefault(('goal', 0), (x, xe))
                    found = True
                    break
                nxt = (y, 1 - ye)
                if nxt not in par:
                    par[nxt] = (x, xe)
                    heapq.heappush(heap, (d + net.edges[y]['line'].length, nxt))
            if found:
                break
        if not found:
            return out + [(e2, d2, (0.0 if d2 > 0 else net.edges[e2]['line'].length), t2)]
        chain, cur = [], par[('goal', 0)]
        while cur != start:
            chain.append(cur)
            cur = par[cur]
        for x, xe in reversed(chain):   # (x left by end xe: passed whole, entered at 1 - xe)
            l = net.edges[x]['line'].length
            out.append((x, 1 if xe == 1 else -1, 0.0 if xe == 1 else l, l if xe == 1 else 0.0))
        out.append((e2, d2, 0.0 if d2 > 0 else net.edges[e2]['line'].length, t2))
        return out


END_STEP = 1.0      # m: an edge's line has points this far apart before its ends go to its nodes' places
DENSE = 2.0         # m: at most this between a surveyed line's points given to the curve fit
MIN_SPAN = 2.0      # m: a shorter stretch of an edge the corridor's track ways run on is not drawn
FULL = 1.0          # m: a drawn stretch this near both ends of its edge is the whole edge
EXTEND = 40.0       # m: a corridor way is matched lengthened this far along OSM's track at both ends
CONTINUE = 30.0     # degrees: OSM's track continues a way within this
ALT_LOOK = 14.0     # m along a switch's other leg for the point the game shows it by (`alt`)
SWITCH_GAP = 3.0    # m: a facing switch this near the one before is the same place (two forks of one crossover)


def load_network():
    """DI's network with the user's switch tips and orthophoto tracks (data/truth.json trackSources)."""
    di, archive = di_tracks.load_sources()
    return Network(di, di_tracks.switch_tips(), di_tracks.photo_source(), archive)


def dense(coords, step=DENSE):
    """A surveyed line with points at most `step` m apart along its own segments: DI draws a straight track with
    vertices tens of metres apart, and the fit, with no data between them, sagged 0.41 m in a 462 m straight leaning
    into curves at both ends (line 37 east of Ohrada). The user, 2026-11-06: "Straight tracks should ... be stiffer"."""
    out = [coords[0]]
    for a, b in zip(coords, coords[1:]):
        n = int(math.dist(a, b) / step)
        out += [(a[0] + (b[0] - a[0]) * i / (n + 1), a[1] + (b[1] - a[1]) * i / (n + 1)) for i in range(1, n + 1)]
        out.append(b)
    return out


class Drawn:
    """The edges a line draws, fitted as smooth curves (tools/track_curve.py `Network`, #204).
    pts[e]: the fitted points of edge e from its node a to b."""

    def __init__(self, net, edges, fit=True):
        import track_curve
        self.net, self.edges = net, set(edges)
        k = lambda a, b: (a, b) if str(a) < str(b) else (b, a)
        pos, pts, kind, limit = {}, {}, {}, {}
        errors = track_curve.class_errors()
        for e in self.edges:
            ed = net.edges[e]
            a, b = ed['a'], ed['b']
            pos[a], pos[b] = net.nodes[a]['xy'], net.nodes[b]['xy']
            c = list(ed['line'].coords)
            if ed['src'] in ('di', 'dtmp', 'ortho'):
                c = dense(c)
            key = k(a, b)
            pts[key] = c if key == (a, b) else c[::-1]
            kind[key] = ed['src']
            classes = {r['attrs'].get('TridaPresnostiPoloha') for r in ed['records'] if isinstance(r, dict)}
            known = [errors[c] for c in classes if c in errors]
            if known and None not in classes:
                limit[key] = max(known)
        self.report = {}
        # which drawn edges continue each other at each node: the passes (the fit joins only these into one curve)
        continues = defaultdict(set)
        for e in self.edges:
            ed = net.edges[e]
            for end, n in ((0, ed['a']), (1, ed['b'])):
                for f, fend in net.passes.get((e, end), ()):
                    if f in self.edges and f != e:
                        other = lambda x, xend: net.edges[x]['b'] if xend == 0 else net.edges[x]['a']
                        continues[n].add(frozenset((other(e, end), other(f, fend))))
        self.pos = dict(pos)
        if fit:
            tc = track_curve.Network(pos, pts, kind, {}, limit, continues)
            fitted, self.report = tc.pts, tc.report
            self.pos = dict(tc.pos)
        else:
            fitted = pts
        self.pts = {}
        for e in self.edges:
            ed = net.edges[e]
            key = k(ed['a'], ed['b'])
            p = fitted[key]
            self.pts[e] = list(p) if key == (ed['a'], ed['b']) else list(p)[::-1]

    def piece(self, e, dr, t0, t1):
        """The fitted points of edge e from t0 to t1 (m along DI's line), in the direction travelled."""
        p = self.pts.get(e) or list(self.net.edges[e]['line'].coords)
        raw = self.net.edges[e]['line'].length or 1.0
        line = LineString(p) if len(p) > 1 else None
        if line is None or line.length == 0:
            return [tuple(p[0])]
        f = line.length / raw
        a, b = sorted((t0 * f, t1 * f))
        seg = substring(line, a, b)
        c = [tuple(q) for q in (seg.coords if seg.geom_type == 'LineString' else [seg.coords[0]])]
        return c if dr > 0 else c[::-1]

    def route(self, match):
        """The route's points through the fitted edges, and the route position where each piece ends."""
        pts, idx = [], []
        for p in match.pieces:
            seg = p[1] if p[0] == 'off' else self.piece(*p)
            for q in seg:
                if not pts or math.dist(pts[-1], q) > 0.1:
                    pts.append(tuple(q))
            idx.append(len(pts) - 1)
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        ends = [cum[i] for i in idx]
        return pts, ends

    def facing(self, match, ends, at_s):
        """The facing switches along a matched route: where it leaves a node by one of two or more ends the end it
        arrived by passes to. [{'s', 'routeDiverging', 'routeSide', 'alt'}] as the game reads them; `at_s(s)` the
        route's point at route position s."""
        net, out = self.net, []
        pieces = match.pieces
        for i in range(len(pieces) - 1):
            p, q = pieces[i], pieces[i + 1]
            if p[0] == 'off' or q[0] == 'off':
                continue
            x = (p[0], 1 if p[1] > 0 else 0)
            y = (q[0], 0 if q[1] > 0 else 1)
            alts = [z for z in net.passes.get(x, ()) if z != y]
            if not alts:
                continue
            s = ends[i]
            if out and s - out[-1]['s'] < SWITCH_GAP:
                continue
            here = at_s(s)
            back = at_s(max(0.0, s - 2.0))
            d_in = _unit((here[0] - back[0], here[1] - back[1]))
            ahead = at_s(s + ALT_LOOK)
            v_route = (ahead[0] - here[0], ahead[1] - here[1])
            z = alts[0]
            line = LineString(self.pts.get(z[0]) or list(net.edges[z[0]]['line'].coords))
            tgt = line.interpolate(min(ALT_LOOK, line.length) if z[1] == 0 else max(0.0, line.length - ALT_LOOK))
            v_alt = (tgt.x - here[0], tgt.y - here[1])
            ang = lambda u, v: math.degrees(math.acos(max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) /
                                                                  ((math.hypot(*u) * math.hypot(*v)) or 1)))))
            cr = d_in[0] * v_route[1] - d_in[1] * v_route[0]
            ca = d_in[0] * v_alt[1] - d_in[1] * v_alt[0]
            out.append({'s': round(s, 1), 'routeDiverging': ang(d_in, v_route) > ang(d_in, v_alt),
                        'routeSide': 'left' if cr > ca else 'right', 'alt': [round(tgt.x, 1), round(tgt.y, 1)],
                        'node': net.edges[p[0]]['b'] if p[1] > 0 else net.edges[p[0]]['a']})
        return out

    def chains(self, flags, spans=None, xy=3):
        """The drawn edges merged into chains through nodes where exactly two drawn edges meet with the same
        source and flags ({edge: bridge}): [{'p', 'src', 'b'?}] as the game reads `tracks`. An edge drawn only along
        a stretch (`spans` {edge: (t0, t1)} m along it) is a chain of its own, that stretch."""
        net = self.net
        spans = spans or {}
        part = {e for e, (a, b) in spans.items() if e in self.edges and (a > FULL or b < net.edges[e]['line'].length - FULL)}
        out = []
        for e in sorted(part):
            a, b = spans[e]
            c = self.piece(e, 1, a, b)
            if len(c) > 1:
                t = {'p': [[round(x, xy), round(y, xy)] for x, y in c], 'src': net.edges[e]['src']}
                if flags.get(e):
                    t['b'] = 1
                out.append(t)
        at = defaultdict(list)
        for e in self.edges - part:
            at[net.edges[e]['a']].append(e)
            at[net.edges[e]['b']].append(e)
        key = lambda e: (net.edges[e]['src'], bool(flags.get(e)))
        used = set(part)

        def walk(e, n):
            """Edges on from edge e beyond its node n while the chain runs on."""
            seq = []
            while len(at[n]) == 2:
                f = at[n][0] if at[n][1] == e else at[n][1]
                if f in used or key(f) != key(e) or f == e:
                    break
                # (only into an edge a train passes to: two legs of a switch drawn without its toe are two chains)
                end_e, end_f = (0 if net.edges[e]['a'] == n else 1), (0 if net.edges[f]['a'] == n else 1)
                if (f, end_f) not in net.passes.get((e, end_e), ()):
                    break
                used.add(f)
                seq.append((f, n))
                e = f
                n = net.edges[f]['b'] if net.edges[f]['a'] == n else net.edges[f]['a']
            return seq
        for e in sorted(self.edges - part):
            if e in used:
                continue
            used.add(e)
            ed = net.edges[e]
            fwd = walk(e, ed['b'])
            bwd = walk(e, ed['a'])
            pts = []
            for f, n in reversed(bwd):   # (entered at n, from the far end towards n)
                p = self.pts[f]
                pts += p[::-1] if net.edges[f]['a'] == n else p
            for q in self.pts[e]:
                pts.append(q)
            for f, n in fwd:
                p = self.pts[f]
                pts += p if net.edges[f]['a'] == n else p[::-1]
            clean = []
            for q in pts:
                if not clean or math.dist(clean[-1], q) > 0.1:
                    clean.append(q)
            if len(clean) < 2:
                continue
            t = {'p': [[round(x, xy), round(y, xy)] for x, y in clean], 'src': ed['src']}
            if flags.get(e):
                t['b'] = 1
            out.append(t)
        return out

    def sources(self, match, ends):
        """[[s0, s1, source], ...] along a matched route."""
        out, s0 = [], 0.0
        for p, s1 in zip(match.pieces, ends):
            src = 'osm' if p[0] == 'off' else self.net.edges[p[0]]['src']
            if out and out[-1][2] == src:
                out[-1][1] = s1
            else:
                out.append([s0, s1, src])
            s0 = s1
        return [[round(a, 1), round(b, 1), c] for a, b, c in out if b - a > 0.05]


def extend(ids, adj, pos, length=EXTEND):
    """A way's nodes lengthened at both ends along OSM's straightest continuation (within CONTINUE degrees) up to
    `length` m: it enters and leaves a junction anchored on plain track. (nodes, index of the way's first node)."""
    def on(seq):
        out, run = [], 0.0
        prev, cur = seq[-2], seq[-1]
        seen = set(seq)
        while run < length:
            u = _unit((pos[cur][0] - pos[prev][0], pos[cur][1] - pos[prev][1]))
            nxt = [m for m in adj[cur] if m not in seen and pos[m] != pos[cur]]
            if not nxt:
                break
            m = max(nxt, key=lambda m: (lambda v: u[0] * v[0] + u[1] * v[1])(_unit((pos[m][0] - pos[cur][0], pos[m][1] - pos[cur][1]))))
            v = _unit((pos[m][0] - pos[cur][0], pos[m][1] - pos[cur][1]))
            if u[0] * v[0] + u[1] * v[1] < math.cos(math.radians(CONTINUE)):
                break
            out.append(m)
            seen.add(m)
            run += math.dist(pos[cur], pos[m])
            prev, cur = cur, m
        return out
    if len(ids) < 2:
        return ids, 0
    head = on(ids[::-1])[::-1]
    tail = on(ids)
    return head + ids + tail, len(head)


def corridor(net, ways, pos, bridges=()):
    """Where OSM's track ways of the corridor run on the network: each way lengthened along OSM's track (`extend`) and
    matched as a route; per edge the stretch the way itself covers ({edge: (t0, t1)}, m along it, from the first to
    the last metre covered), and whether it is on a bridge (`bridges`: the ids of the ways on one, by length)."""
    adj = defaultdict(set)
    for w in ways:
        ns = [n for n in w['nodes'] if n in pos]
        for a, b in zip(ns, ns[1:]):
            if a != b:
                adj[a].add(b)
                adj[b].add(a)
    spans, on_bridge, run_on = {}, defaultdict(float), defaultdict(float)
    for w in ways:
        ids = [n for n in w['nodes'] if n in pos]
        ids = [n for i, n in enumerate(ids) if i == 0 or pos[n] != pos[ids[i - 1]]]
        if len(ids) < 2:
            continue
        ext, first = extend(ids, adj, pos)
        m = Match(net, [pos[n] for n in ext])
        s0, s1 = m.node_s[first], m.node_s[first + len(ids) - 1]
        s = 0.0
        for p in m.pieces:
            if p[0] == 'off':
                s += sum(math.dist(a, b) for a, b in zip(p[1], p[1][1:]))
                continue
            run = abs(p[3] - p[2])
            lo, hi = max(s, s0), min(s + run, s1)
            if hi - lo > 1e-3:
                # (the part of this piece between the way's own ends, in t along the edge)
                ta = p[2] + (lo - s) * p[1]
                tb = p[2] + (hi - s) * p[1]
                a, b = sorted((ta, tb))
                old = spans.get(p[0])
                spans[p[0]] = (a, b) if old is None else (min(old[0], a), max(old[1], b))
                run_on[p[0]] += b - a
                if w.get('id') in bridges:
                    on_bridge[p[0]] += b - a
            s += run
    # (a stretch never ends inside a junction: from there it runs on to the edge's end, the network's connection)
    for e, (a, b) in list(spans.items()):
        length = net.edges[e]['line'].length
        spans[e] = (0.0 if net.in_zone(e, a) else a, length if net.in_zone(e, b) else b)
    spans = {e: sp for e, sp in spans.items() if sp[1] - sp[0] >= MIN_SPAN}
    flags = {e: on_bridge[e] >= 0.5 * run_on[e] for e in spans}
    return spans, flags

def _acc(line):
    out, s = [0.0], 0.0
    c = list(line.coords)
    for a, b in zip(c, c[1:]):
        s += math.dist(a, b)
        out.append(s)
    return out


def main():
    import json
    import time
    line = sys.argv[sys.argv.index('--line') + 1] if '--line' in sys.argv else '17'
    t = time.time()
    di, _ = di_tracks.load_sources()
    t1 = time.time()
    net = Network(di, di_tracks.switch_tips(), di_tracks.photo_source())
    print(f"sources {t1 - t:.1f} s, network {time.time() - t1:.1f} s: {net.summary()}")
    root = Path(__file__).resolve().parent.parent
    d = json.loads((root / 'data' / f'line{line}.json').read_text(encoding='utf-8'))
    for key in ('path', 'pathBack'):
        t2 = time.time()
        m = Match(net, [tuple(p[:2]) for p in d[key]])
        print(f"{key}: {time.time() - t2:.1f} s {m.report}")


if __name__ == '__main__':
    main()
