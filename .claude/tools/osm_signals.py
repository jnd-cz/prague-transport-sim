# Traffic-signal data along a line from OpenStreetMap (Overpass), for the game's traffic lights.
# Not part of the game; belongs into the project's build tools (build_line.py) later.
#   python -I .claude/tools/osm_signals.py 17      -> data/line17.signals.json
# Writes, in the line's local metres (x east, y north from data/lineN.json "origin", the same
# conversion the game data uses):
#   stop:  highway=traffic_signals nodes on roads (mappers put them at each approach's stop line), with
#          the travel direction they serve (traffic_signals:direction forward/backward along the way;
#          none: both ways): [{ x, y, hx, hy, both }]
#   peds:  signalled pedestrian crossings (crossing=traffic_signals, not on the tram track): [{ x, y }]
#   tram:  crossings over the tram track (railway=tram_crossing, or a crossing node on a tram way):
#          [{ x, y, sig }], sig = signalled (crossing=traffic_signals)
# Queries the corridor in boxes along the route, 5 s apart (be kind to the public servers).
import json
import math
import sys
import time
import urllib.parse
import urllib.request

SERVERS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
line = sys.argv[1] if len(sys.argv) > 1 else '17'
data = json.load(open(f'data/line{line}.json', encoding='utf-8'))
lat0, lon0 = data['origin']
# (the line data's own conversion: 110574 m per degree of latitude, 111320 cos(lat0) of longitude;
# 111320 for both put the nodes up to 45 m off at the line's ends, fitted against the OSM tram tracks)
ky = 110574
kx = 111320 * math.cos(math.radians(lat0))
to_xy = lambda lat, lon: ((lon - lon0) * kx, (lat - lat0) * ky)
to_ll = lambda x, y: (lat0 + y / ky, lon0 + x / kx)

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


def query(q):
    for k, url in enumerate(SERVERS * 2):
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'tatra-t3-prague-game/0.1 (signal import)'})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 (retry on the next server, backing off)
            print(f'  {url}: {e}; retrying', file=sys.stderr)
            time.sleep(5 * (k + 1))
    raise SystemExit('Overpass: no server answered')


nodes, ways = {}, {}
for i, pts in enumerate(boxes):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    s, w = to_ll(min(xs) - 120, min(ys) - 120)
    n, e = to_ll(max(xs) + 120, max(ys) + 120)
    bb = f'{s:.6f},{w:.6f},{n:.6f},{e:.6f}'
    q = f'[out:json][timeout:60];(node({bb})[highway=traffic_signals];node({bb})[crossing=traffic_signals];node({bb})[railway=tram_crossing];)->.sig;.sig out body;way(bn.sig)[~"^(highway|railway)$"~"."];out geom;'
    res = query(q)
    for el in res['elements']:
        (nodes if el['type'] == 'node' else ways)[el['id']] = el
    print(f'box {i + 1}/{len(boxes)}: {len(nodes)} nodes, {len(ways)} ways so far', file=sys.stderr)
    time.sleep(5)

# the ways each node lies on, with its neighbours there (for the direction)
on_ways = {}
for wy in ways.values():
    for k, nid in enumerate(wy.get('nodes', [])):
        if nid in nodes:
            on_ways.setdefault(nid, []).append((wy, k))

out = {'source': 'OpenStreetMap contributors (ODbL), via Overpass', 'stop': [], 'peds': [], 'tram': []}
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

json.dump(out, open(f'data/line{line}.signals.json', 'w', encoding='utf-8'), separators=(',', ':'))
print(f"line {line}: {len(out['stop'])} car stop lines, {len(out['peds'])} signalled pedestrian crossings, {len(out['tram'])} tram crossings ({sum(1 for c in out['tram'] if c['sig'])} signalled)")
