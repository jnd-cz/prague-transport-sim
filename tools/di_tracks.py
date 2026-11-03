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
FORK = 5.0     # m: an OSM switch takes the position of a source fork this near
BLEND = 20.0   # m along an OSM fill stretch over which it takes up the shift of its matched neighbours
CHANGE = 1.0   # m-equivalent cost of continuing on another chain along one OSM edge
JOINT = 4.0    # m: the chain may change only this near the joint of the two chains (STEP + TOL)
MIN_RECORD = 0.05  # m: shorter source records are dropped
DUPLICATE = 0.2    # m: a record joining the same two places as another, never farther from it, is a copy
FORK_MIN, FORK_OUT, FORK_APART = 3.0, 8.0, 0.3  # m: a fork's branches (records this long) are this far apart
                                                # this far out
CONTEXT = 4.0  # m: an unmatched stretch between two matched nodes takes the chain its ends lie on within this
               # (Křižovnická: OSM draws a 60 m chord of the curve between both tracks, 1-2 m from each;
               # its neighbours fix which track it is)


class Source:
    """A source's track records merged into chains that end only at forks, crossings and track ends."""

    def __init__(self, name, paths):
        self.name = name
        # (DI has zero-length records and the same piece twice under two IDs, Čechův most: either would make a
        # straight track look like a fork)
        recs = [(p, [tuple(c[:2]) for c in p['coords']]) for p in paths if len(p['coords']) > 1]
        recs = [r for r in recs if LineString(r[1]).length >= MIN_RECORD]
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
        self.duplicates = len(paths) - len(recs)
        members = defaultdict(list)
        for i in range(len(ends)):
            members[root(i)].append(i)
        # forks: places where two records leave in the same direction and move apart (two copies of one track
        # leave together and stay within centimetres: Vozovna Kobylisy, 10 m each at 98-99 degrees)
        self.forks = []
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
        # 2. node positions: a matched node moves onto its chain (a switch onto the source's fork when one is
        # within FORK), a node with only unmatched edges keeps OSM's position and takes up its neighbours' shift
        self.pos = {}
        # each source fork goes to the nearest OSM switch within FORK, one node per fork (Palackého náměstí: two
        # switches 4-5 m apart would both take one fork and the edge between them would vanish)
        claims = []
        for n in adj:
            if len(adj[n]) < 3:
                continue
            hits = [(m, self.edges[(n, m) if str(n) < str(m) else (m, n)]) for m in adj[n]]
            src = next((h[0] for _, h in hits if h), None)
            if src is None or src.fork_tree is None:
                continue
            # the chains this node's edges run on at it: a fork must lie on all of them (a crossover has a fork on
            # each track; the other track's one 4 m sideways may be the nearer, Holešovice)
            mine = {(h[1][0][0] if str(n) < str(m) else h[1][-1][0]) for m, h in hits if h and h[0] is src}
            for i in src.fork_tree.query(Point(pos[n]).buffer(FORK)):
                f = src.forks[i]
                d = math.dist(f, pos[n])
                # never past a neighbour (Holešovice: a fork 3.7 m behind the previous node turned the route back)
                keeps = all(math.dist(f, pos[m]) > 0.5 and (f[0] - pos[m][0]) * (pos[n][0] - pos[m][0])
                            + (f[1] - pos[m][1]) * (pos[n][1] - pos[m][1]) > 0 for m in adj[n])
                on = all(src.chains[c]['line'].distance(Point(f)) <= JOIN for c in mine)
                if d <= FORK and keeps and on:
                    claims.append((d, n, (src.name, int(i)), f))
        fork_of, taken = {}, set()
        for d, n, key, f in sorted(claims, key=lambda c: c[0]):
            if n not in fork_of and key not in taken:
                fork_of[n] = f
                taken.add(key)
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
        matched = set(self.pos)
        shift = {n: (self.pos[n][0] - pos[n][0], self.pos[n][1] - pos[n][1]) for n in matched}
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
