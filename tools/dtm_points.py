# Street furniture points from Prague's technical map (archived DTMP, state as of 30 June 2024, CC BY,
# "datový podklad © IPR Praha") along a line: traffic signals, public transport stop signs, poles and
# masts, street lights, traffic sign carriers, ground covers (REMOTE-CHANGES §20, §22).
#   python -I tools/dtm_points.py 17             -> data/lineN.dtmpoints.json (from the snapshot's raw answer)
#   python -I tools/dtm_points.py 17 --refresh   (asks the service again: a new raw answer for a new snapshot)
# Source: https://mp.iprpraha.cz/arcgis/rest/services/Hosted/DTMP_CUR_TMISZNAK_B/FeatureServer/0
# (open data hub item d4418172a31b46b7b875668eaa354f22). Points have no heights. The raw answer is a
# snapshot input: raw/dtmpoints/lineN.json (tools/snapshot.py).
# Checked at Palackého náměstí: the stop sign ~3 m from the OSM stop position / the user's photo, a
# "semafor" ~1 m from the tram signal pole at the island's tip (tram signals are coded "semafor" too).
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
URL = 'https://mp.iprpraha.cz/arcgis/rest/services/Hosted/DTMP_CUR_TMISZNAK_B/FeatureServer/0/query'
KINDS = {
    605250: 'signal', 605251: 'signal_on_building', 605161: 'light_signal',
    605240: 'stop_sign', 605241: 'stop_sign_on_building',
    606010: 'pole', 706010: 'pole_low_voltage', 606021: 'lattice_mast',
    606560: 'light_on_pole', 606570: 'decorative_light_on_pole', 606561: 'light_on_building',
    605270: 'traffic_sign', 605280: 'warning_beacon', 606780: 'clock',
    # street detail (ground covers and small furniture)
    106200: 'manhole', 406081: 'manhole', 306081: 'manhole', 506081: 'manhole', 606081: 'manhole', 706081: 'manhole', 206081: 'manhole', 106081: 'manhole',
    106300: 'gutter_inlet', 406130: 'hydrant_cap', 406120: 'hydrant', 406140: 'valve_cap', 306140: 'valve_cap',
    736750: 'phone_booth', 606650: 'transformer', 408170: 'fountain',
}
line = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '17'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I leaves it out)
from geo import ROOT, Frame  # noqa: E402

data = json.load(open(os.path.join(ROOT, 'data', f'line{line}.json'), encoding='utf-8'))
frame = Frame(*data['origin'])
to_xy, to_ll = frame.xy, frame.ll


def get(params):
    q = URL + '?' + urllib.parse.urlencode(params)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(q, headers={'User-Agent': 'tatra-t3-prague-game/0.1 (dtm points)'}), timeout=120) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 (back off and retry)
            print(f'  {e}; retrying', file=sys.stderr)
            time.sleep(5 * (k + 1))
    raise SystemExit('the map server did not answer')


cache = os.path.join(ROOT, 'raw', 'dtmpoints', f'line{line}.json')
if '--refresh' in sys.argv or not os.path.exists(cache):
    path, boxes, cur, acc = data['path'], [], [data['path'][0]], 0.0
    for a, b in zip(path, path[1:]):
        acc += math.dist(a, b)
        cur.append(b)
        if acc > 800:
            boxes.append(cur); cur, acc = [b], 0.0
    if len(cur) > 1:
        boxes.append(cur)
    feats = {}
    where = 'ctmtp_kod IN (' + ','.join(map(str, KINDS)) + ')'
    for i, pts in enumerate(boxes):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        s, w = to_ll(min(xs) - 60, min(ys) - 60)
        n, e = to_ll(max(xs) + 60, max(ys) + 60)
        offset = 0
        while True:
            res = get({'where': where, 'geometry': f'{w},{s},{e},{n}', 'geometryType': 'esriGeometryEnvelope', 'inSR': 4326,
                       'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'objectid,ctmtp_kod', 'returnGeometry': 'true',
                       'outSR': 4326, 'resultOffset': offset, 'resultRecordCount': 2000, 'f': 'json'})
            for f in res.get('features', []):
                feats[f['attributes']['objectid']] = f
            if not res.get('exceededTransferLimit'):
                break
            offset += 2000
        print(f'box {i + 1}/{len(boxes)}: {len(feats)} points', file=sys.stderr)
        time.sleep(1)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    json.dump({'fetched': time.strftime('%Y-%m-%d'), 'features': list(feats.values())}, open(cache, 'w', encoding='utf-8'))

raw = json.load(open(cache, encoding='utf-8'))
out = {'source': 'Archivní DTM Prahy (stav k 30. 6. 2024), datový podklad © IPR Praha (CC BY 4.0)', 'fetched': raw['fetched'], 'points': []}
counts = {}
for f in raw['features']:
    k = KINDS.get(f['attributes']['ctmtp_kod'])
    if not k or 'geometry' not in f:
        continue
    x, y = to_xy(f['geometry']['y'], f['geometry']['x'])
    out['points'].append({'k': k, 'x': round(x, 2), 'y': round(y, 2)})
    counts[k] = counts.get(k, 0) + 1
out['points'].sort(key=lambda p: (p['k'], p['x'], p['y']))
json.dump(out, open(os.path.join(ROOT, 'data', f'line{line}.dtmpoints.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'line {line}: ' + ', '.join(f'{v} {k}' for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) + f' -> data/line{line}.dtmpoints.json')
