# SPDX-License-Identifier: AGPL-3.0-or-later
# Street furniture points from Prague's technical map (archived DTMP, state as of 30 June 2024, CC BY,
# "datový podklad © IPR Praha") along a line: traffic signals, public transport stop signs, poles and
# masts, street lights, traffic sign carriers, ground covers. This tool fetches the raw answers; the line's
# features are built from them by tools/features.py (#14), which also names the codes kept.
#   python -P -E tools/dtm_points.py 17 --refresh   (asks the service again: a new raw answer for a new snapshot)
#   python -P -E tools/dtm_points.py 17             (asks only when the raw answer is not there)
#   python -P -E tools/dtm_points.py 17 --signs     -> raw/dtmpoints/lineN.signs.json: the stop signs of both
#                                                   archive layers, for tools/build_line.py's stop points (#258)
# Source: https://mp.iprpraha.cz/arcgis/rest/services/Hosted/DTMP_CUR_TMISZNAK_B/FeatureServer/0
# (open data hub item d4418172a31b46b7b875668eaa354f22). Points have no heights. The raw answer is a
# snapshot input: raw/dtmpoints/lineN.json (tools/snapshot.py).
# Checked at Palackého náměstí: the stop sign ~3 m from the OSM stop position / the maintainer's photo, a
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
line = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else '17'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I leaves it out)
from atomic import replacing  # noqa: E402
from features import DTMP as KINDS  # noqa: E402
from geo import ROOT, Frame  # noqa: E402

data = json.load(open(os.path.join(ROOT, 'data', f'line{line}.json'), encoding='utf-8'))
to_ll = Frame().ll


def get(params, url=URL):
    q = url + '?' + urllib.parse.urlencode(params)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(q, headers={'User-Agent': 'tatra-t3-prague-game/0.1 (dtm points)'}), timeout=120) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 (back off and retry)
            print(f'  {e}; retrying', file=sys.stderr)
            time.sleep(5 * (k + 1))
    raise SystemExit('the map server did not answer')


def path_boxes(path):
    """the line in pieces of ~800 m, each queried as its bounding box"""
    boxes, cur, acc = [], [path[0]], 0.0
    for a, b in zip(path, path[1:]):
        acc += math.dist(a[:2], b[:2])
        cur.append(b)
        if acc > 800:
            boxes.append(cur); cur, acc = [b], 0.0
    if len(cur) > 1:
        boxes.append(cur)
    return boxes


# The stop signs (zastávka MHD, 605240/605241) are in two layers of the archive: the second (_ADS_B) has as many
# again as the first, and the two together put a sign beside 275 of the 295 stops (both directions) of lines 9,
# 17, 22, 23 and 37, the first alone 154 (#258). The layers are stored in Web Mercator: asked for S-JTSK the
# server leaves out the datum shift (9.9 m off), so WGS 84 out and tools/geo.py, as for the points below.
SIGN_LAYERS = ('DTMP_CUR_TMISZNAK_B', 'DTMP_CUR_TMISZNAK_ADS_B')
if '--signs' in sys.argv:
    feats = {}
    for layer in SIGN_LAYERS:
        url = URL.replace('DTMP_CUR_TMISZNAK_B', layer)
        for i, pts in enumerate(path_boxes(data['path'])):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            s, w = to_ll(min(xs) - 60, min(ys) - 60)
            n, e = to_ll(max(xs) + 60, max(ys) + 60)
            res = get({'where': 'ctmtp_kod IN (605240,605241)', 'geometry': f'{w},{s},{e},{n}', 'geometryType': 'esriGeometryEnvelope',
                       'inSR': 4326, 'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'objectid,ctmtp_kod', 'returnGeometry': 'true',
                       'outSR': 4326, 'resultRecordCount': 2000, 'f': 'json'}, url)
            for f in res.get('features', []):
                if 'geometry' in f:
                    feats[(layer, f['attributes']['objectid'])] = {'layer': layer, 'id': f['attributes']['objectid'],
                                                                   'kod': f['attributes']['ctmtp_kod'],
                                                                   'lat': f['geometry']['y'], 'lon': f['geometry']['x']}
            time.sleep(1)
        print(f'{layer}: {sum(k[0] == layer for k in feats)} stop signs', file=sys.stderr)
    dst = os.path.join(ROOT, 'raw', 'dtmpoints', f'line{line}.signs.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with replacing(dst, 'w', encoding='utf-8') as fh:
        json.dump({'fetched': time.strftime('%Y-%m-%d'), 'source': 'Archivní DTM Prahy (stav k 30. 6. 2024), datový podklad © IPR Praha (CC BY 4.0)',
                   'layers': list(SIGN_LAYERS), 'signs': sorted(feats.values(), key=lambda f: (f['layer'], f['id']))}, fh, ensure_ascii=False)
    print(f'line {line}: {len(feats)} stop signs -> {os.path.relpath(dst, ROOT)}')
    sys.exit(0)

cache = os.path.join(ROOT, 'raw', 'dtmpoints', f'line{line}.json')
if '--refresh' in sys.argv or not os.path.exists(cache):
    boxes = path_boxes(data['path'])
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
    with replacing(cache, 'w', encoding='utf-8') as fh:
        json.dump({'fetched': time.strftime('%Y-%m-%d'), 'features': list(feats.values())}, fh)

raw = json.load(open(cache, encoding='utf-8'))
print(f"line {line}: {len(raw['features'])} points fetched {raw['fetched']} in raw/dtmpoints/line{line}.json "
      f"(tools/features.py builds data/line{line}.features.json from them)")
