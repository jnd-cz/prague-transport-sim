# Traffic-signal data along a line from OpenStreetMap, for the game's traffic lights (docs/history/REMOTE-CHANGES.md §17).
# Belongs into build_line.py later (docs/history/BUILD-TOOLS-HANDOFF.md §2.1).
#   python -P -E tools/osm_signals.py 17      -> data/line17.signals.json
# Reads the snapshot's OSM extract (tools/osm_local.py; pyosmium, hence -P -E). Writes, in the line's
# local metres (tools/geo.py):
#   stop:  highway=traffic_signals nodes on roads (mappers put them at each approach's stop line), with
#          the travel direction they serve (traffic_signals:direction forward/backward along the way;
#          none: both ways): [{ x, y, hx, hy, both }]
#   peds:  signalled pedestrian crossings (crossing=traffic_signals, not on the tram track): [{ x, y }]
#   tram:  crossings over the tram track (railway=tram_crossing, or a crossing node on a tram way):
#          [{ x, y, sig }], sig = signalled (crossing=traffic_signals)
# The corridor: boxes of ~1.5 km of route, 120 m around it.
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves it out)
import osm_local  # noqa: E402
from geo import ROOT, Frame  # noqa: E402

line = sys.argv[1] if len(sys.argv) > 1 else '17'
data = json.load(open(os.path.join(ROOT, 'data', f'line{line}.json'), encoding='utf-8'))
frame = Frame()
to_xy = frame.xy
if not osm_local.available():
    raise SystemExit('no raw/osm/praha.osm.pbf: run python -I tools/snapshot.py fetch')

# boxes of ~1.5 km of route each, 120 m around it
path = data['path']
boxes, cur, acc = [], [path[0]], 0.0
for a, b in zip(path, path[1:]):
    acc += math.hypot(b[0] - a[0], b[1] - a[1])
    cur.append(b)
    if acc > 1500:
        boxes.append(cur); cur, acc = [b], 0.0
if len(cur) > 1:
    boxes.append(cur)
bbs = [frame.bbox(pts, 120) for pts in boxes]
inbox = lambda lat, lon: any(s <= lat <= n and w <= lon <= e for s, w, n, e in bbs)  # noqa: E731

nodes = {el['id']: el for el in osm_local.nodes(lambda t: t.get('highway') == 'traffic_signals' or t.get('crossing') == 'traffic_signals'
                                                   or t.get('railway') == 'tram_crossing') if inbox(el['lat'], el['lon'])}
ways = {w['id']: w for w in osm_local.ways(lambda t: 'highway' in t or 'railway' in t, bbox=(min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)))
        if any(n in nodes for n in w['nodes'])}
print(f'{len(nodes)} signal / crossing nodes, {len(ways)} ways through them', file=sys.stderr)

# the ways each node lies on, with its neighbours there (for the direction)
on_ways = {}
for wy in ways.values():
    for k, nid in enumerate(wy.get('nodes', [])):
        if nid in nodes:
            on_ways.setdefault(nid, []).append((wy, k))

out = {'source': f'OpenStreetMap contributors (ODbL), extract {osm_local.base_id()}', 'stop': [], 'peds': [], 'tram': []}
for nid, el in nodes.items():
    t = el.get('tags', {})
    x, y = to_xy(el['lat'], el['lon'])
    ws = on_ways.get(nid, [])
    tramway = any(w.get('tags', {}).get('railway') == 'tram' for w, _ in ws)
    if t.get('railway') == 'tram_crossing' or (t.get('crossing') == 'traffic_signals' and tramway):
        out['tram'].append({'x': round(x, 2), 'y': round(y, 2), 'sig': t.get('crossing') == 'traffic_signals'})
        continue
    if t.get('highway') == 'traffic_signals' and t.get('traffic_signals') not in ('crossing',):
        road = next(((w, k) for w, k in ws if 'highway' in w.get('tags', {})), None)
        if not road:
            continue
        w, k = road
        g = w['geometry']
        a, b = g[max(0, k - 1)], g[min(len(g) - 1, k + 1)]
        (ax, ay), (bx, by) = to_xy(a['lat'], a['lon']), to_xy(b['lat'], b['lon'])
        L = math.hypot(bx - ax, by - ay) or 1
        hx, hy = (bx - ax) / L, (by - ay) / L
        d = t.get('traffic_signals:direction', t.get('direction', ''))
        if d == 'backward':
            hx, hy = -hx, -hy
        out['stop'].append({'x': round(x, 2), 'y': round(y, 2), 'hx': round(hx, 3), 'hy': round(hy, 3), 'both': d not in ('forward', 'backward')})
        continue
    if t.get('crossing') == 'traffic_signals' or t.get('highway') == 'traffic_signals':
        out['peds'].append({'x': round(x, 2), 'y': round(y, 2)})

json.dump(out, open(os.path.join(ROOT, 'data', f'line{line}.signals.json'), 'w', encoding='utf-8'), separators=(',', ':'))
print(f"line {line}: {len(out['stop'])} car stop lines, {len(out['peds'])} signalled pedestrian crossings, {len(out['tram'])} tram crossings ({sum(1 for c in out['tram'] if c['sig'])} signalled)")
