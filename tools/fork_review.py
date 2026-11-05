"""Where are the switches' tips? DI's forks against OSM's switches along each line's routes, for the review page (#237):
    python -P -E tools/fork_review.py [--lines 9,17,22,23,37] [--over 2]

For each facing switch of a line's route and opposite route (tools/di_network.py: DI's fork where the route leaves a
node by one of two passes) the nearest OSM switch of the corridor's tracks (railway=switch, or a node where three
OSM track ways meet; the build's cached answer raw/.../tracks.json) within di_tracks.FORK. A card goes to
reports/review/track-forks-N.json where the two lie more than --over metres apart, where DI draws a switch twice
(two legs to the same next node), or where only one has a switch
(an OSM switch within NEAR of the route with no DI fork within di_tracks.FORK: Anděl). The pin is DI's fork; the user
places it on the tip (where the blades begin): the answers become data/truth.json trackSources.switchTips, which the
network takes (di_network.Network.move_tips). Cards are keyed by place (the fork's position to 1e-5 degrees).
"""
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import di_network  # noqa: E402
import di_tracks  # noqa: E402
from atomic import replacing  # noqa: E402
from geo import Frame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OPTIONS = ["tip at the pin (DI's fork)", "tip at OSM's switch", "unsure"]
DI, OSM = "#ff3b30", "#3e9dff"
NEAR = 3.0   # m: an OSM switch this near the route is on it


def tracks_answer(line):
    """The build's cached corridor tracks of a line (tools/build_line.py RAW)."""
    for p in (ROOT / 'raw' / 'run9-10' if line == '9' else None, ROOT / 'raw' / f'line{line}', ROOT / 'raw'):
        if p is not None and (p / 'tracks.json').exists():
            return json.loads((p / 'tracks.json').read_text(encoding='utf-8'))
    raise SystemExit(f"line {line}: no cached tracks.json; build the line first (tools/build_line.py)")


def osm_switches(ans, frame):
    """[(x, y, node id, how)] of OSM's switches: railway=switch nodes and nodes where three or more track ways meet."""
    nodes = {e['id']: e for e in ans['elements'] if e['type'] == 'node'}
    deg = {}
    for e in ans['elements']:
        if e['type'] == 'way':
            ns = e['nodes']
            for i, n in enumerate(ns):
                deg[n] = deg.get(n, 0) + (1 if i in (0, len(ns) - 1) else 2)
    out = []
    for n, e in nodes.items():
        t = e.get('tags', {})
        if t.get('railway') in ('railway_crossing', 'crossing', 'tram_crossing'):
            continue
        if t.get('railway') == 'switch' or deg.get(n, 0) >= 3:
            x, y = frame.xy(e['lat'], e['lon'])
            out.append((float(x), float(y), n, 'railway=switch' if t.get('railway') == 'switch' else 'junction'))
    return out


def forks(net, data):
    """[(x, y, node, s, key)] of the facing switches on the line's routes (key: 'path' or 'pathBack')."""
    out = []
    for key in ('path', 'pathBack'):
        if not data.get(key):
            continue
        m = di_network.Match(net, [tuple(p[:2]) for p in data[key]])
        g = di_network.Drawn(net, m.edges, fit=False)
        pts, ends = g.route(m)
        line = di_network.LineString(pts)
        def at(s, line=line):
            q = line.interpolate(s)
            return (q.x, q.y)
        for sw in g.facing(m, ends, at):
            x, y = net.nodes[sw['node']]['xy']
            out.append((x, y, sw['node'], sw['s'], key))
    return out


def drawn_twice(net, node):
    """Two of a fork's ends lead to the same next node (past a midpoint split): DI's switch drawn twice."""
    far = []
    for e, end in net.at[node]:
        ed = net.edges[e]
        n = ed['b'] if end == 0 else ed['a']
        if net.nodes[n]['kind'] == 'mid' and len(net.at[n]) == 2:
            f, fend = next(x for x in net.at[n] if x[0] != e)
            n = net.edges[f]['b'] if fend == 0 else net.edges[f]['a']
        far.append(n)
    return len(far) != len(set(far))


def review(line, net, data, switches, over, frame):
    found, seen, cards = forks(net, data), set(), []
    route = [di_network.LineString([p[:2] for p in data[k]]) for k in ('path', 'pathBack') if data.get(k)]
    used = set()
    for x, y, node, s, key in found:
        if node in seen:
            continue
        seen.add(node)
        near = min(switches, key=lambda o: math.dist(o[:2], (x, y)), default=None)
        d = math.dist(near[:2], (x, y)) if near else math.inf
        if near and d <= di_tracks.FORK:
            used.add(near[2])
        twice = drawn_twice(net, node)
        if d <= over and not twice:
            continue
        lat, lon = frame.ll(x, y)
        marks = [{"x": round(x, 2), "y": round(y, 2), "label": "DI's fork", "color": DI}]
        if near and d <= di_tracks.FORK:
            marks.append({"x": round(near[0], 2), "y": round(near[1], 2), "label": f"OSM's switch ({near[3]})", "color": OSM})
            why = f"DI's fork lies {d:.1f} m from OSM's switch."
        else:
            why = "OSM has no switch within 15 m of DI's fork."
        if twice:
            why += " DI draws two tracks from this fork to the next node (Strossmayerovo náměstí): the switch drawn twice?"
        cards.append({"kind": "switch tip", "id": f"fork-{float(lat):.5f}-{float(lon):.5f}", "line": line, "route": key,
                      "x": round(x, 2), "y": round(y, 2), "s": s, "mag": round(min(d, 20.0), 1), "status": "review", "pick": True,
                      "marks": marks, "di_fork": [round(x, 2), round(y, 2)], "osm_node": near[2] if near and d <= di_tracks.FORK else None,
                      "info": f"{why} The pin is DI's fork. Where does the switch begin (the tip of its blades)? "
                              f"Not at the pin: place it on the map."})
    # OSM's switches on the route with no DI fork near (Anděl: OSM's junction node where DI's tracks do not meet)
    for ox, oy, n, how in switches:
        if n in used or min(r.distance(di_network.Point(ox, oy)) for r in route) > NEAR:
            continue
        # (any place DI's tracks meet, trailing switches and crossings included)
        if any(math.dist((ox, oy), v['xy']) <= di_tracks.FORK for n2, v in net.nodes.items() if len(net.at[n2]) >= 3):
            continue
        lat, lon = frame.ll(ox, oy)
        cards.append({"kind": "switch tip", "id": f"osm-switch-{n}", "line": line, "x": round(ox, 2), "y": round(oy, 2),
                      "mag": 20.0, "status": "review", "pick": True, "osm_node": n,
                      "marks": [{"x": round(ox, 2), "y": round(oy, 2), "label": f"OSM's switch ({how})", "color": OSM}],
                      "info": "OSM has a switch on the route here; DI has no fork within 15 m. Is there a switch? "
                              "Place the pin on its tip, or answer at the pin if OSM's place is right."})
    return cards


def main():
    args = sys.argv[1:]
    lines = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    over = float(args[args.index('--over') + 1]) if '--over' in args else 2.0
    frame = Frame()
    net = di_network.load_network()
    for line in lines:
        data = json.loads((ROOT / 'data' / f'line{line}.json').read_text(encoding='utf-8'))
        cards = review(line, net, data, osm_switches(tracks_answer(line), frame), over, frame)
        out = {"schema": 1, "issue": 237, "line": line, "options": OPTIONS, "over_m": over, "findings": cards}
        with replacing(os.path.join(ROOT, 'reports', 'review', f'track-forks-{line}.json'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
        print(f"line {line}: {len(cards)} cards ({sum('di_fork' in c for c in cards)} DI forks off OSM's switch, "
              f"{sum('di_fork' not in c for c in cards)} OSM switches without a DI fork)")


if __name__ == '__main__':
    main()
