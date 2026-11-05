"""Switch tips where the drawn track has trouble, for the review page (#237):
    python -P -E tools/fork_review.py [--lines 9,17,22,23,37]

The build (tools/build_line.py) writes reports/track-problems-N.json: curves held to 18 m, surveyed points the
fitted curve misses by more than MISS, stretches off DI's network. Each place
(one per GROUP m, the worst) becomes a card in reports/review/track-forks-N.json with DI's forks within
di_tracks.FORK (red, the nearest is the pin; "drawn twice" where two legs lead to the same next node) and OSM's
switches (blue: railway=switch or a node where three track ways meet, from the build's cached tracks.json). The user
places the pin on the switch's tip; the answers become data/truth.json trackSources.switchTips, which the network
takes (di_network.Network.move_tips). The user, 2026-11-05: "focus only on the places which cause di track
deviation, kinks, forced radius or missing segments".
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
DI, OSM, PROBLEM = "#ff3b30", "#3e9dff", "#ffd60a"
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


MISS = 0.15    # m: a surveyed point the fitted curve misses by more than this is a problem (DI's class 3 states a
               # mean error of 0.14 m: the fit may move a point that far where a curve would bend under 20 m)
GROUP = 15.0   # m: problems this near each other are one place


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


def problems(line):
    """[(x, y, what, size)] where the line's drawn track has trouble (tools/build_line.py writes
    reports/track-problems-N.json), the worst of each GROUP m first."""
    f = ROOT / 'reports' / f'track-problems-{line}.json'
    if not f.exists():
        raise SystemExit(f"line {line}: no {f.name}; build the line first (tools/build_line.py)")
    pr = json.loads(f.read_text(encoding='utf-8'))
    items = [(h['xy'], f"curve held to 18 m: points moved {h['m']} m off DI", h['m'] + 1) for h in pr['held']]
    items += [(m['xy'], f"the fitted curve misses DI by {m['m']} m", m['m']) for m in pr['misses'] if m['m'] > MISS]
    # (curves left at 18-20 m are not listed: the network's minimum is 18 m, data/truth.json min-radius-network)
    items += [(o['xy'], f"{o['m']} m off DI's network (DI has no track the route can use)", 2.0) for o in pr['off']]
    out = []
    for xy, what, size in sorted(items, key=lambda i: -i[2]):
        if all(math.dist(xy, o[:2]) > GROUP for o in out):
            out.append((xy[0], xy[1], what, size))
    return out


def review(line, net, switches, frame):
    """A card per problem place: the pin on DI's nearest fork (else the place), DI's forks and OSM's switches near."""
    forks = [(v['xy'], n) for n, v in net.nodes.items() if len(net.at[n]) >= 3]
    cards = []
    for x, y, what, size in problems(line):
        near_f = sorted((f for f in forks if math.dist(f[0], (x, y)) <= di_tracks.FORK), key=lambda f: math.dist(f[0], (x, y)))
        near_o = [o for o in switches if math.dist(o[:2], (x, y)) <= di_tracks.FORK]
        px, py = near_f[0][0] if near_f else (x, y)
        lat, lon = frame.ll(px, py)
        marks = [{"x": round(x, 2), "y": round(y, 2), "label": what, "color": PROBLEM}]
        marks += [{"x": round(f[0][0], 2), "y": round(f[0][1], 2), "label": "DI's fork" + (" (drawn twice)" if drawn_twice(net, f[1]) else ""),
                   "color": DI} for f in near_f]
        marks += [{"x": round(o[0], 2), "y": round(o[1], 2), "label": f"OSM's switch ({o[3]})", "color": OSM} for o in near_o]
        cards.append({"kind": "switch tip", "id": f"track-{float(lat):.5f}-{float(lon):.5f}", "line": line,
                      "x": round(px, 2), "y": round(py, 2), "mag": round(size, 2), "status": "review", "pick": True,
                      "marks": marks, "problem": what,
                      "info": f"Here {what}. The pin is " + ("DI's nearest fork" if near_f else "the place") +
                              ". Where does the switch begin (the tip of its blades)? Place the pin there; if DI's track is "
                              "right and no switch is involved, answer unsure with a note."})
    return cards


def main():
    args = sys.argv[1:]
    lines = args[args.index('--lines') + 1].split(',') if '--lines' in args else ['9', '17', '22', '23', '37']
    frame = Frame()
    net = di_network.load_network()
    for line in lines:
        cards = review(line, net, osm_switches(tracks_answer(line), frame), frame)
        out = {"schema": 1, "issue": 237, "line": line, "options": OPTIONS, "findings": cards}
        dst = os.path.join(ROOT, 'reports', 'review', f'track-forks-{line}.json')
        if not cards:   # (no set for a line without trouble: an empty one would wait in the review directory)
            if os.path.exists(dst):
                os.remove(dst)
            print(f"line {line}: no places where the drawn track has trouble")
            continue
        with replacing(os.path.join(ROOT, 'reports', 'review', f'track-forks-{line}.json'), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(out, ensure_ascii=False, indent=1) + '\n')
        print(f"line {line}: {len(cards)} places where the drawn track has trouble")


if __name__ == '__main__':
    main()
