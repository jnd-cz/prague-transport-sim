# SPDX-License-Identifier: AGPL-3.0-or-later
"""Holes in a line's drawn tracks (#237): python -P -E tools/bench/track_holes.py [--lines 9,17,22,23,37]

A network edge (tools/di_network.py) no drawn track runs along, while drawn tracks continue through it at both of its
ends, and it is short or one of them ends in the air without it: the rail stops at one side and goes on at the other.
Lists each with its place and length. Exit code 1 if any is left. (Strossmayerovo náměstí, line 17: two edges of 1.3 and 1.2 m between two crossings, under MIN_SPAN; Ohrada,
line 37: the 92 m branch of an interlaced switch, the way matched on the track beside it.)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import shapely  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
import di_network  # noqa: E402
from geo import Frame  # noqa: E402

ALONG = 0.1     # m: points of an edge this near a drawn track are drawn (the curve stays within 10 cm of DI)
MAX_EDGE = di_network.MIN_SPAN   # m: longer edges with both ends on going tracks are connections a line does not draw


def holes(net, tracks):
    """[(edge, length, middle)]: the edges missing between drawn tracks that continue through them."""
    lines = [LineString(t['p']) for t in tracks if len(t['p']) > 1]
    tree = shapely.STRtree(lines)
    drawn = {}

    def is_drawn(e):
        if e not in drawn:
            l = net.edges[e]['line']
            q = [l.interpolate(f, normalized=True) for f in (0.25, 0.5, 0.75)]
            drawn[e] = all(len(tree.query(p, predicate='dwithin', distance=ALONG)) for p in q)
        return drawn[e]
    out = []
    for e, ed in net.edges.items():
        l = ed['line']
        if is_drawn(e):
            continue
        ends = [[f for f, _ in net.passes.get((e, end), ()) if is_drawn(f)] for end in (0, 1)]
        nodes = (ed['a'], ed['b'])
        lone = [i for i, n in enumerate(nodes) if len(net.at[n]) == 2 and ends[i]
                and any(is_drawn(f) for f, _ in net.at[nodes[1 - i]] if f != e)]
        if lone or (all(ends) and l.length < MAX_EDGE):
            out.append((e, l.length, l.interpolate(0.5, normalized=True)))
    return out


def main():
    args = sys.argv[1:]
    names = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    root = Path(__file__).resolve().parent.parent.parent
    net, frame, total = di_network.load_network(), Frame(), 0
    for name in names:
        data = json.loads((root / 'data' / f'line{name}.json').read_text(encoding='utf-8'))
        found = holes(net, data['tracks'])
        total += len(found)
        print(f'line {name}: {len(found)} holes')
        for e, length, q in found:
            lat, lon = frame.ll(q.x, q.y)
            print(f'   edge {e}: {length:.1f} m at {float(lat):.5f} N {float(lon):.5f} E')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
