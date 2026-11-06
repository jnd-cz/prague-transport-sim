"""DI's network graph against OSM's track graph, junction by junction (#237):
    python -P -E tools/bench/track_topology.py [--lines 9,17,22,23,37] [--json out.json] [--latest]

Distance to DI cannot see a wrong connection or a missing one, so this reads which movements each graph allows. A
movement is a way through a junction: from a point LEG m before it to a point LEG m after it, turning at most TURN
degrees at every node. Both ways round, on the tracks a line draws (data/lineN.json) and OSM's whole tram network (the
build's cached network_tracks.json, else the line's corridor, where a track the corridor lacks reads as a difference):
  osm-only: OSM allows it, the network has no such path (a connection the build lost, or one OSM has wrong);
  di-only:  the network allows it, OSM's graph has no such path (a connection the build invented, or OSM lacks it);
  no-osm:   the network's movement where OSM has no track within NEAR (a track OSM lacks: no reading of the connection);
  no-di:    OSM's movement where the network has no track within NEAR (a track DI lacks or the network dropped).
OSM's movements are looked for on the whole network, so a track a line leaves out is no difference.
A point stands on any track within NEAR (OSM lies up to metres off, and a fork up to 48 m from DI's, Ohrada): a wrong
connection between tracks closer than that goes unseen, and nothing here says which graph is right. Differences are a
list to review, one per place, so the exit code stays 0. A di-only place can be OSM out of date (rebuilt track, 50.07847 N
14.43178 E, the user 2026-11-06): each run says the extract's date, --latest asks Geofabrik whether a newer one exists.
"""
import heapq
import json
import math
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import shapely  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402
import di_network  # noqa: E402
import fork_review  # noqa: E402
from geo import Frame  # noqa: E402
from track_fit import line_edges  # noqa: E402

LEG = 15.0      # m before and after a junction: past the switch, whichever graph's fork lies nearer
NEAR = 2.5      # m: a point stands on a track this near (the user: the closest tracks in OSM lie 2.5 m apart)
TURN = 60.0     # degrees at one node of a path; a tram does not turn more within a junction
THROUGH = 30.0  # degrees at a junction's own node: more is two tracks crossing at a node OSM has not tagged
SLACK = 1.25    # a path may be this much longer than the movement, plus SLACK_M: a graph's detour is another movement
SLACK_M = 5.0
LATEST = 'https://download.geofabrik.de/europe/czech-republic-latest.osm.pbf'
GROUP = 10.0    # m: differences this near are one place
CROSSINGS = ('railway_crossing', 'crossing', 'tram_crossing')


def unit(a, b):
    d = math.dist(a, b) or 1.0
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


class OsmGraph:
    """OSM's track ways as {node: [next nodes]} with positions, and the movements through its junctions."""

    def __init__(self, ans, frame):
        el = {e['id']: e for e in ans['elements'] if e['type'] == 'node'}
        self.xy = {n: tuple(float(v) for v in frame.xy(e['lat'], e['lon'])) for n, e in el.items()}
        self.tags = {n: e.get('tags', {}) for n, e in el.items()}
        self.adj, self.segs = {}, []
        for w in ans['elements']:
            if w['type'] != 'way':
                continue
            ns = [n for n in w['nodes'] if n in el]
            for a, b in zip(ns, ns[1:]):
                if a != b and self.xy[a] != self.xy[b]:
                    self.adj.setdefault(a, set()).add(b)
                    self.adj.setdefault(b, set()).add(a)
                    self.segs.append((a, b))
        self.tree = shapely.STRtree([LineString([self.xy[a], self.xy[b]]) for a, b in self.segs]) if self.segs else None

    def walk(self, prev, n, length):
        """The point `length` m on from prev through n, straightest at every node."""
        p, cur, left = prev, n, length
        while True:
            d = math.dist(self.xy[p], self.xy[cur])
            if d >= left:
                f = left / d
                return (self.xy[p][0] + (self.xy[cur][0] - self.xy[p][0]) * f, self.xy[p][1] + (self.xy[cur][1] - self.xy[p][1]) * f)
            left -= d
            u = unit(self.xy[p], self.xy[cur])
            on = [(u[0] * v[0] + u[1] * v[1], m) for m in self.adj[cur] if m != p for v in [unit(self.xy[cur], self.xy[m])]]
            if not on or max(on)[0] < math.cos(math.radians(TURN)):
                return self.xy[cur]
            p, cur = cur, max(on)[1]

    def straightest(self, n, nb):
        """The legs of a crossing paired into its two straightest lines: {frozenset((a, b))}."""
        dirs = {m: unit(self.xy[n], self.xy[m]) for m in nb}
        turn = lambda a, b: dirs[a][0] * dirs[b][0] + dirs[a][1] * dirs[b][1]
        best, a = None, nb[0]
        for b in nb[1:]:
            rest = [m for m in nb[1:] if m != b]
            score = turn(a, b) + (turn(*rest) if len(rest) == 2 else 0.0)
            if best is None or score < best[0]:
                best = (score, {frozenset((a, b))} | ({frozenset(rest)} if len(rest) == 2 else set()))
        return best[1]

    def movements(self, keep):
        """[(place, a, b)]: through each junction `keep` accepts, from the point LEG before to the point LEG after."""
        out = []
        for n, nb in self.adj.items():
            if len(nb) < 3 or not keep(self.xy[n]):
                continue
            nb = sorted(nb)
            # (four legs are two tracks crossing unless tagged a switch, however shallow: the extract of the whole network has
            # no tags, and a curve crossing a straight at 20° is no way from one to the other. A double slip reads as a
            # difference)
            crossing = self.tags[n].get('railway') in CROSSINGS or (self.tags[n].get('railway') != 'switch' and len(nb) == 4)
            pairs = self.straightest(n, nb) if crossing else None
            for i, x in enumerate(nb):
                for y in nb[:i]:
                    u, v = unit(self.xy[x], self.xy[n]), unit(self.xy[n], self.xy[y])
                    if (frozenset((x, y)) in pairs) if crossing else (u[0] * v[0] + u[1] * v[1] >= math.cos(math.radians(THROUGH))):
                        out.append((self.xy[n], self.walk(n, x, LEG), self.walk(n, y, LEG)))
        return out

    def on(self, p):
        """[(a, b, distance from a along a-b)]: the segments within NEAR of p."""
        if self.tree is None:
            return []
        out = []
        for i in self.tree.query(Point(p), predicate='dwithin', distance=NEAR):
            a, b = self.segs[int(i)]
            out.append((a, b, LineString([self.xy[a], self.xy[b]]).project(Point(p))))
        return out

    def path(self, a, b, limit):
        """The shortest path from point a to point b under `limit` m that turns at most TURN at every node, or None."""
        ends = {}
        for x, y, s in self.on(b):
            ends[(x, y)] = s
            ends[(y, x)] = math.dist(self.xy[x], self.xy[y]) - s
        best, heap, seen, k = None, [], set(), 0
        for x, y, s in self.on(a):
            d = math.dist(self.xy[x], self.xy[y])
            for u, v, run in ((x, y, d - s), (y, x, s)):
                if (u, v) in ends:   # (both on one segment, going the right way)
                    g = ends[(u, v)] - (d - run)
                    if g >= -1e-6:
                        best = g if best is None else min(best, g)
                k += 1
                heapq.heappush(heap, (run, k, u, v))
        while heap:
            run, _, u, v = heapq.heappop(heap)
            if run > limit or (best is not None and run >= best) or (u, v) in seen:
                continue
            seen.add((u, v))
            h = unit(self.xy[u], self.xy[v])
            for m in self.adj[v]:
                if m == u:
                    continue
                w = unit(self.xy[v], self.xy[m])
                if h[0] * w[0] + h[1] * w[1] < math.cos(math.radians(TURN)):
                    continue
                if (v, m) in ends:
                    g = run + ends[(v, m)]
                    best = g if best is None else min(best, g)
                k += 1
                heapq.heappush(heap, (run + math.dist(self.xy[v], self.xy[m]), k, v, m))
        return best


class DiGraph:
    """The network's edges a line draws: movements through its nodes, paths along net.passes (only what a tram can)."""

    def __init__(self, net, edges):
        self.net, self.edges = net, sorted(edges)
        self.tree = shapely.STRtree([net.edges[e]['line'] for e in self.edges]) if self.edges else None

    def on(self, p):
        if self.tree is None:
            return []
        return [(self.edges[int(i)], self.net.edges[self.edges[int(i)]]['line'].project(Point(p)))
                for i in self.tree.query(Point(p), predicate='dwithin', distance=NEAR)]

    def path(self, a, b, limit):
        """The shortest path from point a to point b under `limit` m along the passes, or None."""
        net = self.net
        ends = {e: s for e, s in self.on(b)}
        best, heap, seen, k = None, [], set(), 0
        for e, s in self.on(a):
            length = net.edges[e]['line'].length
            if e in ends:
                g = abs(ends[e] - s)
                best = g if best is None else min(best, g)
            for out, run in ((1, length - s), (0, s)):
                k += 1
                heapq.heappush(heap, (run, k, e, out))
        while heap:
            run, _, e, out = heapq.heappop(heap)
            if run > limit or (best is not None and run >= best) or (e, out) in seen:
                continue
            seen.add((e, out))
            for f, fend in net.passes.get((e, out), ()):
                if f in ends:
                    g = run + (ends[f] if fend == 0 else net.edges[f]['line'].length - ends[f])
                    best = g if best is None else min(best, g)
                k += 1
                heapq.heappush(heap, (run + net.edges[f]['line'].length, k, f, 1 - fend))
        return best

    def walk(self, e, end, length):
        """The point `length` m along edge e from its end `end`, on along the straightest pass past its far end."""
        net, left = self.net, length
        for _ in range(50):
            line = net.edges[e]['line']
            if left <= line.length:
                q = line.interpolate(left if end == 0 else line.length - left)
                return (q.x, q.y)
            left -= line.length
            far = 1 - end
            on = [x for x in net.passes.get((e, far), ()) if x[0] in self.edges]
            if not on:
                q = line.coords[-1] if far == 1 else line.coords[0]
                return (q[0], q[1])
            d = net.out_dir(e, far)
            e, end = min(on, key=lambda x: d[0] * net.out_dir(*x)[0] + d[1] * net.out_dir(*x)[1])
        return (0.0, 0.0)

    def movements(self):
        """[(place, a, b)]: through each node where three or more drawn ends meet."""
        net, out, drawn = self.net, [], set(self.edges)
        for n, at in net.at.items():
            ends = [x for x in at if x[0] in drawn]
            if len(ends) < 3:
                continue
            done = set()
            for x in ends:
                for y in net.passes.get(x, ()):
                    if y in ends and frozenset((x, y)) not in done:
                        done.add(frozenset((x, y)))
                        out.append((net.nodes[n]['xy'], self.walk(x[0], x[1], LEG), self.walk(y[0], y[1], LEG)))
        return out


def compare(osm, di, whole, near_drawn):
    """{'osm-only': [(place, a, b)], 'di-only': [...], 'no-osm': [...], 'no-di': [...]}: `di` the graph of the edges a
    line draws, `whole` of the network's; only OSM's junctions `near_drawn` accepts."""
    limit = lambda a, b: SLACK * 2 * LEG + SLACK_M
    found = {'osm-only': [], 'di-only': [], 'no-osm': [], 'no-di': []}
    counts = {'osm': 0, 'di': 0}
    for place, a, b in osm.movements(near_drawn):
        counts['osm'] += 1
        if not (whole.on(a) and whole.on(b)):
            found['no-di'].append((place, a, b))
        elif whole.path(a, b, limit(a, b)) is None:
            found['osm-only'].append((place, a, b))
    for place, a, b in di.movements():
        counts['di'] += 1
        if not (osm.on(a) and osm.on(b)):
            found['no-osm'].append((place, a, b))
        elif osm.path(a, b, limit(a, b)) is None:
            found['di-only'].append((place, a, b))
    return found, counts


def extract_date(root):
    """YYMMDD of the snapshot's OSM extract (raw/osm/czech-republic-YYMMDD.osm.pbf), or None."""
    return next((m.group(1) for m in (re.search(r'-(\d{6})\.osm\.pbf$', f.name) for f in (root / 'raw' / 'osm').glob('*.osm.pbf')) if m), None)


def latest_date():
    """YYMMDD of Geofabrik's latest extract, from where its -latest link redirects, or None."""
    class Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    req = urllib.request.Request(LATEST, method='HEAD')
    try:
        urllib.request.build_opener(Stop).open(req, timeout=20)
    except urllib.error.HTTPError as e:
        m = re.search(r'-(\d{6})\.osm\.pbf$', e.headers.get('Location') or '')
        return m.group(1) if m else None
    except OSError:
        return None
    return None


def osm_answer(root, name):
    """OSM's whole tram network from any line's build, else this line's corridor ways."""
    found = sorted((root / 'raw').glob('*/network_tracks.json'))
    if found:
        return json.loads(found[0].read_text(encoding='utf-8'))
    return fork_review.tracks_answer(name)


def places(items):
    out = []
    for it in items:
        if all(math.dist(it[0], o[0]) > GROUP for o in out):
            out.append(it)
    return out


def main():
    args = sys.argv[1:]
    names = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    root = Path(__file__).resolve().parent.parent.parent
    net, frame, report = di_network.load_network(), Frame(), {}
    whole = DiGraph(net, set(net.edges))
    ours = extract_date(root)
    print(f'OSM extract {ours}' + (f', Geofabrik has {latest_date()}' if '--latest' in args else ''))
    for name in names:
        data = json.loads((root / 'data' / f'line{name}.json').read_text(encoding='utf-8'))
        lines = [LineString(t['p']) for t in data['tracks'] if len(t['p']) > 1]
        tree = shapely.STRtree(lines)
        near = lambda p, tree=tree: len(tree.query(Point(p), predicate='dwithin', distance=NEAR)) > 0
        found, counts = compare(OsmGraph(osm_answer(root, name), frame), DiGraph(net, line_edges(net, data['tracks'])), whole, near)
        rep = {}
        print(f"line {name}: {counts['osm']} OSM movements, {counts['di']} network movements; "
              + ', '.join(f'{k} {len(places(v))}' for k, v in found.items()))
        for k, v in found.items():
            rep[k] = []
            for place, a, b in places(v):
                lat, lon = frame.ll(*place)
                rep[k].append({'at': [round(float(lat), 5), round(float(lon), 5)], 'from': [round(v, 2) for v in a], 'to': [round(v, 2) for v in b]})
                print(f'   {k}: {float(lat):.5f} N {float(lon):.5f} E')
        report[name] = rep
    if '--json' in args:
        Path(args[args.index('--json') + 1]).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
