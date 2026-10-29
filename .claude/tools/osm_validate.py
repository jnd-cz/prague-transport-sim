# Checks a line's data against OpenStreetMap (BUILD-TOOLS-HANDOFF.md §3). Not part of the game.
#   python -I .claude/tools/osm_validate.py 17            (fetches OSM once, then uses the cache)
#   python -I .claude/tools/osm_validate.py 17 --refresh  (fetches again)
# Prints: the coordinate fit (OSM tram ways vs our tracks), stops vs OSM stop positions, the line's
# crossings without an OSM tram crossing, tram signals standing along platforms, and crossings inside
# platforms. Writes the same as JSON to data/lineN.validate.json. The OSM answer is cached in
# .claude/tools/cache/lineN.osm.json (raw Overpass JSON).
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')  # (Czech names on a Windows console; -I ignores PYTHONIOENCODING)
SERVERS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
line = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '17'
refresh = '--refresh' in sys.argv
data = json.load(open(f'data/line{line}.json', encoding='utf-8'))
lat0, lon0 = data['origin']
KY, KX = 110574, 111320 * math.cos(math.radians(lat0))  # the line data's conversion (handoff §1.1)
to_xy = lambda lat, lon: ((lon - lon0) * KX, (lat - lat0) * KY)
to_ll = lambda x, y: (lat0 + y / KY, lon0 + x / KX)


class Polyline:
    """nearest(x, y) -> (s, d, lateral +right) on a polyline, through a 25 m grid of its segments"""
    def __init__(self, pts, cell=25.0):
        self.p, self.s, self.cell, self.grid = pts, [0.0], cell, {}
        for i in range(1, len(pts)):
            self.s.append(self.s[-1] + math.dist(pts[i - 1], pts[i]))
        for i in range(1, len(pts)):
            (ax, ay), (bx, by) = pts[i - 1], pts[i]
            for gx in range(int(min(ax, bx) // cell) - 1, int(max(ax, bx) // cell) + 2):
                for gy in range(int(min(ay, by) // cell) - 1, int(max(ay, by) // cell) + 2):
                    self.grid.setdefault((gx, gy), []).append(i)

    def nearest(self, x, y):
        best = None
        for i in self.grid.get((int(x // self.cell), int(y // self.cell)), ()):
            (ax, ay), (bx, by) = self.p[i - 1], self.p[i]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy or 1e-9
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
            px, py = ax + dx * t, ay + dy * t
            d = math.hypot(x - px, y - py)
            if best is None or d < best[1]:
                L = math.sqrt(l2)
                best = (self.s[i - 1] + t * L, d, ((x - px) * dy - (y - py) * dx) / L)
        return best  # None: farther than ~25 m


route = Polyline(data['path'])
back = Polyline(data['pathBack']) if data.get('pathBack') else None


def query(q):
    for k, url in enumerate(SERVERS * 2):
        try:
            req = urllib.request.Request(url, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': 'tatra-t3-prague-game/0.1 (data validation)'})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 (next server, backing off)
            print(f'  {url}: {e}; retrying', file=sys.stderr)
            time.sleep(5 * (k + 1))
    raise SystemExit('Overpass: no server answered')


cache = f'.claude/tools/cache/line{line}.osm.json'
if refresh or not os.path.exists(cache):
    path, boxes, cur, acc = data['path'], [], [data['path'][0]], 0.0
    for a, b in zip(path, path[1:]):
        acc += math.dist(a, b)
        cur.append(b)
        if acc > 1500:
            boxes.append(cur); cur, acc = [b], 0.0
    if len(cur) > 1:
        boxes.append(cur)
    els = {}
    for i, pts in enumerate(boxes):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        s, w = to_ll(min(xs) - 120, min(ys) - 120)
        n, e = to_ll(max(xs) + 120, max(ys) + 120)
        bb = f'{s:.6f},{w:.6f},{n:.6f},{e:.6f}'
        res = query(f'[out:json][timeout:90];(way({bb})[railway=tram];node({bb})[public_transport=stop_position][tram=yes];node({bb})[railway=tram_crossing];'
                    f'node({bb})[highway=crossing];way({bb})[public_transport=platform][tram=yes];way({bb})[railway=platform];);out geom tags;')
        for el in res['elements']:
            els[f"{el['type']}{el['id']}"] = el
        print(f'box {i + 1}/{len(boxes)}: {len(els)} elements', file=sys.stderr)
        time.sleep(5)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump({'fetched': time.strftime('%Y-%m-%d'), 'elements': list(els.values())}, open(cache, 'w', encoding='utf-8'))
osm = json.load(open(cache, encoding='utf-8'))
els = osm['elements']
tags = lambda el: el.get('tags', {})
geom = lambda el: [to_xy(g['lat'], g['lon']) for g in el.get('geometry', [])] if el['type'] == 'way' else [to_xy(el['lat'], el['lon'])]
out = {'line': line, 'osmFetched': osm.get('fetched')}

# 1. coordinate fit: OSM tram way points vs the nearer of our two tracks
ds = []
for el in els:
    if el['type'] == 'way' and tags(el).get('railway') == 'tram':
        for x, y in geom(el):
            n = [h for h in (route.nearest(x, y), back and back.nearest(x, y)) if h]
            if n and min(h[1] for h in n) < 12:
                ds.append(min(h[1] for h in n))
ds.sort()
out['fit'] = {'points': len(ds), 'median': round(ds[len(ds) // 2], 2) if ds else None, 'p90': round(ds[int(len(ds) * 0.9)], 2) if ds else None}
print(f"1. coordinate fit: {len(ds)} OSM tram points near our tracks, median {out['fit']['median']} m, 90th pct {out['fit']['p90']} m  ({'OK' if ds and ds[len(ds) // 2] < 0.5 else 'CHECK THE CONVERSION'})")

# 2. stops vs OSM stop positions (same name, on our track)
sp = [(tags(el).get('name', ''), *geom(el)[0]) for el in els if el['type'] == 'node' and tags(el).get('public_transport') == 'stop_position']
rows = []
for st in data['stops']:
    c = [route.nearest(x, y) for name, x, y in sp if name == st['name']]
    c = [h for h in c if h and h[1] < 3]
    if not c:
        rows.append({'stop': st['name'], 's': round(st['s']), 'osm': None}); continue
    h = min(c, key=lambda h: abs(h[0] - st['s']))
    rows.append({'stop': st['name'], 's': round(st['s']), 'diff': round(h[0] - st['s'], 1)})
out['stops'] = rows
far = [r for r in rows if r.get('osm', 1) is None or abs(r.get('diff', 0)) > 10]
print(f"2. stops: {len(rows) - len(far)} of {len(rows)} within 10 m of OSM's stop position on our track")
for r in far:
    print(f"   {r['stop']} (s {r['s']}): " + ('no OSM stop position on our track' if r.get('osm', 1) is None else f"OSM {r['diff']:+} m"))

# 3. the line's crossings without an OSM tram crossing within 5 m
tc = []
for el in els:
    t = tags(el)
    if el['type'] == 'node' and (t.get('railway') == 'tram_crossing' or t.get('highway') == 'crossing'):
        x, y = geom(el)[0]
        h = route.nearest(x, y)
        if h and h[1] < 4:
            tc.append(h[0])
lone = [round(s) for s in data.get('crossings', []) if not any(abs(s - t) < 5 for t in tc)]
out['crossingsWithoutOsm'] = lone
print(f"3. crossings: {len(lone)} of {len(data.get('crossings', []))} have no OSM tram / footway crossing node on our track within 5 m")
if lone:
    print('   s ' + ', '.join(map(str, lone)))

# 4. tram signals along platforms, 5. crossings inside platforms (before the platform's end)
plats = [(st['name'], st.get('p0'), st.get('p1')) for st in data['stops'] if st.get('p0') is not None]
on = [{'signal': round(g['s']), 'stop': n} for g in data.get('signals', []) for n, a, b in plats if a - 1 < g['s'] < b + 2]
inside = [{'crossing': round(c), 'stop': n, 'beforeEnd': round(b - c, 1)} for c in data.get('crossings', []) for n, a, b in plats if a + 2 < c < b - 0.5]
out['signalsOnPlatforms'], out['crossingsInPlatforms'] = on, inside
print(f"4. tram signals standing along a platform: {len(on)}" + (' (' + ', '.join(f"{o['signal']} {o['stop']}" for o in on) + ')' if on else ''))
print(f"5. crossings inside a platform: {len(inside)}" + (' (' + ', '.join(f"{o['crossing']} {o['stop']} {o['beforeEnd']} m before its end" for o in inside) + ')' if inside else ''))

json.dump(out, open(f'data/line{line}.validate.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'written data/line{line}.validate.json')
