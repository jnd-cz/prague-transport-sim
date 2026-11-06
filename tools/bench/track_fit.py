"""The curve fit alone, on a line's tracks or the whole network, without a build (#237):
    python -P -E tools/bench/track_fit.py --lines 9,17,22,23,37 [--top 15] [--min 0.05] [--json out.json]
    python -P -E tools/bench/track_fit.py --all

Builds DI's network (tools/di_network.py), takes the edges a line draws (those along the tracks of its last build,
data/lineN.json; --all: every edge), fits them and says, per line: how far the curves lie from DI's records where DI
has the track (COVER as in track_deviation.py), the kinks (the heading turning over KINK degrees within 2 m), the
places left under 20 m and held to 18 m, the worst places with what lies there: the nearest node, its kind and
number of ends, the source of the edge.
"""
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shapely  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402
import di_network  # noqa: E402
from geo import Frame  # noqa: E402

COVER = 1.0     # m: farther from every DI record, DI has no track there
GROUP = 20.0    # m: one worst place per this
KINK = 10.0     # degrees within 2 m: a radius under 11.5 m
ALONG = 0.8     # of an edge's samples within 1 m of a line's built tracks: the line draws it


def line_edges(net, tracks):
    lines = [LineString(t['p']) for t in tracks if len(t['p']) > 1]
    tree = shapely.STRtree(lines)
    out = set()
    for e, ed in net.edges.items():
        l = ed['line']
        n = max(2, int(l.length))
        pts = [l.interpolate(l.length * i / n) for i in range(n + 1)]
        near = sum(len(tree.query(p, predicate='dwithin', distance=1.0)) > 0 for p in pts)
        if near >= ALONG * len(pts):
            out.add(e)
    return out


def kinks(polys):
    out = []
    for p in polys:
        if len(p) < 2:
            continue
        l = LineString(p)
        if l.length < 4:
            continue
        n = int(l.length / 0.5)
        q = [l.interpolate(i * 0.5) for i in range(n + 1)]
        for i in range(2, len(q) - 2):
            a, b, c = q[i - 2], q[i], q[i + 2]
            u, v = (b.x - a.x, b.y - a.y), (c.x - b.x, c.y - b.y)
            lu, lv = math.hypot(*u), math.hypot(*v)
            if lu < 0.5 or lv < 0.5:
                continue
            ang = math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / (lu * lv)))))
            if ang > KINK:
                out.append((ang, b.x, b.y))
    return out


def worst_places(items):
    picked = []
    for it in sorted(items, reverse=True):
        if all(math.dist(it[1:3], w[1:3]) > GROUP for w in picked):
            picked.append(it)
    return picked


def main():
    args = sys.argv[1:]
    root = Path(__file__).resolve().parent.parent.parent
    top = int(args[args.index('--top') + 1]) if '--top' in args else 15
    low = float(args[args.index('--min') + 1]) if '--min' in args else 0.05
    names = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    if '--all' in args:
        names = ['all']
    t0 = time.time()
    net = di_network.load_network()
    print(f'network {time.time() - t0:.0f} s: {len(net.edges)} edges')
    records = [c['line'] for c in net.source.chains]
    rtree = shapely.STRtree(records)
    nids = [n for n in net.nodes if net.at.get(n)]
    ntree = shapely.STRtree(shapely.points([net.nodes[n]['xy'] for n in nids]))
    frame, report = Frame(), {}
    for name in names:
        t1 = time.time()
        if name == 'all':
            edges = set(net.edges)
        else:
            data = json.loads((root / 'data' / f'line{name}.json').read_text(encoding='utf-8'))
            edges = line_edges(net, data['tracks'])
        drawn = di_network.Drawn(net, edges)
        dev = []
        for e, p in drawn.pts.items():
            if len(p) < 2:
                continue
            l = LineString(p)
            n = max(1, int(l.length / 0.5))
            for q in shapely.line_interpolate_point(l, [l.length * i / n for i in range(n + 1)]):
                near = rtree.query(q, predicate='dwithin', distance=COVER)
                if len(near):
                    dev.append((min(records[int(j)].distance(q) for j in near), q.x, q.y, e))
        ds = sorted(d[0] for d in dev)
        share = lambda lim: sum(d <= lim for d in ds) / (len(ds) or 1)
        kk = worst_places(kinks(drawn.pts.values()))
        r = drawn.report
        rep = {'edges': len(edges), 'points': len(ds), 'within_2cm': round(share(0.02), 4), 'within_5cm': round(share(0.05), 4),
               'within_10cm': round(share(0.10), 4), 'over_10cm_m': round(sum(d > 0.10 for d in ds) * 0.5, 1),
               'max_m': round(ds[-1], 3) if ds else 0, 'kinks': len(kk), 'held': len(r.get('held_to_network_radius', ())),
               'tight': len(r.get('tighter_than_min_radius', ())), 'seconds': round(time.time() - t1)}
        report[name] = rep
        print(f"line {name}: {rep['edges']} edges, {rep['seconds']} s; within 2 cm {rep['within_2cm']:.1%}, 5 cm {rep['within_5cm']:.1%}, "
              f"10 cm {rep['within_10cm']:.1%}, over 10 cm {rep['over_10cm_m']} m, max {rep['max_m']} m; kinks {rep['kinks']}, held {rep['held']}, under 20 m {rep['tight']}")
        for d, x, y, e in [w for w in worst_places(dev) if w[0] >= low][:top]:
            j = ntree.query_nearest(Point(x, y))[0]
            m = nids[int(j)]
            ed = net.edges[e]
            lat, lon = frame.ll(x, y)
            print(f"   {d:.3f} m  {float(lat):.5f} N {float(lon):.5f} E  edge {e} {ed['src']} {ed['line'].length:.0f} m; node {m} {net.nodes[m]['kind']} "
                  f"{len(net.at[m])} ends, {math.dist((x, y), net.nodes[m]['xy']):.1f} m off")
        for a, x, y in kk[:top]:
            lat, lon = frame.ll(x, y)
            print(f"   kink {a:.0f}°  {float(lat):.5f} N {float(lon):.5f} E")
        for h in r.get('held_to_network_radius', ())[:top]:
            lat, lon = frame.ll(*h['xy'])
            print(f"   held {h['m']} m (R {h['radius_m']})  {float(lat):.5f} N {float(lon):.5f} E")
        for h in r.get('tighter_than_min_radius', ())[:top]:
            lat, lon = frame.ll(*h['xy'])
            print(f"   R {h['radius_m']} m  {float(lat):.5f} N {float(lon):.5f} E")
    if '--json' in args:
        Path(args[args.index('--json') + 1]).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
