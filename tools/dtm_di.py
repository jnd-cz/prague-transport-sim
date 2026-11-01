"""Acquire and report district DI set 7, without importing it into the world (#61).

    python -P -E tools/dtm_di.py --fetch     # deliberate upstream refresh; stage raw/dtm-di/
    python -P -E tools/dtm_di.py             # offline, from the snapshot; JSON -> reports/dtm-di.json

District selection uses both paths of the five built lines and administrative boundaries from the
pinned local OSM extract. The provider currently lists JVF ZIPs for DI, not the ZPS GPKG packages.
Publishing a source snapshot remains a separate, user-approved snapshot.py publish command.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
from geo import Frame, load_line

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'raw' / 'dtm-di'
LINES = (9, 17, 22, 23, 37)
CATALOGUE = 'https://geoportalpraha.cz/backend/selectmongo'
DATASET = '50DF58EE-2B3B-42B7-A414-3D2809159B8C'
DOWNLOADS = 'https://geoportalpraha.cz/api/get-dtm-download-metadata?code=07'
BASE = 'https://isdtmk.dtm-praha-sck.cz/api/istem/vydej/download/path/'
POLICY = 'https://geoportalpraha.cz/backend/getdokument/1'
NS = {'obj': 'objtyp', 'atr': 'atr', 'cmn': 'cmn', 'di': 'dopinf',
      'gml': 'http://www.opengis.net/gml/3.2'}
FLAGS = ('NeuplnaData', 'TridaPresnostiPoloha', 'TridaPresnostiVyska',
         'ZpusobPorizeniDI', 'UrovenUmisteniObjektuDI')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with replacing(path, 'w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def districts(lines=LINES, buffer=0.0):
    """Intersect complete line segments (including pathBack), not sampled points or bounding boxes;
    with a buffer, the corridor around them (the ZPS street survey's, dtm_packages.CORRIDOR)."""
    import osmium
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    from osm_local import PRAHA, relations

    frame = Frame()
    paths = {}
    for line in lines:
        data = load_line(line)
        if data.get('frame') != {'crs': 'EPSG:5514', 'origin': list(frame.to_jtsk(0, 0))}:
            raise ValueError(f'line {line}: rebuild in the city frame first')
        paths[line] = unary_union([LineString([p[:2] for p in data[key]])
                                   for key in ('path', 'pathBack') if data.get(key)])
    areas = {line: path.buffer(buffer) if buffer else path for line, path in paths.items()}
    rels = relations(lambda t: t.get('admin_level') == '9' and 'ref:cobe' in t
                     and t.get('name', '').startswith('Praha'))
    if len(rels) != 57:
        raise ValueError(f'expected all 57 Prague districts in the pinned extract, found {len(rels)}')
    ids = {m['ref'] for r in rels for m in r['members'] if m['type'] == 'way'}
    ways = {}
    for way in osmium.FileProcessor(PRAHA, osmium.osm.NODE | osmium.osm.WAY).with_locations():
        if way.is_way() and way.id in ids:
            x, y = frame.xy([n.location.lat for n in way.nodes], [n.location.lon for n in way.nodes])
            ways[way.id] = LineString(zip(x, y))
    if ids - ways.keys():
        raise ValueError('district boundary ways missing from the pinned extract')
    found = []
    polygons = []
    for rel in rels:
        members = rel['members']
        outer = [ways[m['ref']] for m in members if m['type'] == 'way' and m['role'] == 'outer']
        inner = [ways[m['ref']] for m in members if m['type'] == 'way' and m['role'] == 'inner']
        poly = unary_union(list(polygonize(outer))).difference(unary_union(list(polygonize(inner))))
        if poly.is_empty or not poly.is_valid:
            raise ValueError(f"invalid district boundary: {rel['tags']['name']}")
        polygons.append(poly)
        hits = [line for line, area in areas.items() if poly.intersects(area)]
        if hits:
            found.append({'code': rel['tags']['ref:cobe'], 'name': rel['tags']['name'],
                          'lines': hits, 'osm_relation': rel['id']})
    coverage = unary_union(polygons)
    for line, path in paths.items():
        missing = path.difference(coverage).length
        if missing > 0.01:
            raise ValueError(f'line {line}: {missing:.2f} m outside district coverage')
    return sorted(found, key=lambda d: d['code'])


def get(url, body=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                     headers={'Content-Type': 'application/json'} if body else {})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def acquire(selected):
    RAW.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(get(CATALOGUE, {'id': DATASET}))
    catalogue = json.loads(get(DOWNLOADS))
    write_json(RAW / 'catalogue.json', {'metadata_url': CATALOGUE, 'metadata_body': {'id': DATASET},
                                      'metadata': metadata, 'downloads_url': DOWNLOADS,
                                      'downloads': catalogue})
    # Capture the provider's terms alongside the ambiguous catalogue flag, not a guessed licence.
    for name, url in [('terms.pdf', POLICY), ('access.html',
            'https://portal.dtm-praha-sck.cz/poskytovani-dat/zpusoby-poskytovani-prazskych-dat-dtm')]:
        with replacing(RAW / name, 'wb') as f:
            f.write(get(url))
    packages = []
    for district in selected:
        entries = [f for row in catalogue for f in row['formats']
                   if f['obec_kod'] == district['code'] and f['format'] == 'JVF']
        if not entries:
            raise ValueError(f"no JVF package: {district['name']}")
        entry = max(entries, key=lambda e: e['platnost'])
        name = entry['soubor_nazev']
        if Path(name).name != name or not name.endswith('_DI.jvf.zip'):
            raise ValueError(f'unexpected package name: {name}')
        url = BASE + entry['kod_stazeni']
        content = get(url)
        if len(content) != int(entry['velikost']):
            raise ValueError(f'{name}: download size differs from catalogue')
        with replacing(RAW / name, 'wb') as f:
            f.write(content)
        with zipfile.ZipFile(RAW / name) as z:
            if z.testzip():
                raise ValueError(f'{name}: corrupt ZIP')
        packages.append(district | {'file': name, 'url': url, 'state': entry['platnost'],
                                    'sha256': sha(RAW / name)})
        print(f"downloaded {district['name']}: {len(content):,} bytes", flush=True)
    write_json(RAW / 'provenance.json', {'packages': packages, 'terms_url': POLICY,
                                       'licence_basis': 'IPR provision rules I.8: CC BY 4.0 for download services; '
                                       'catalogue openData=false retained in catalogue.json'})


def classify_z(values):
    import math
    if not values or any(not math.isfinite(v) for v in values):
        return 'missing_or_nonfinite'
    if all(v == 0 for v in values):
        return 'zero'
    return 'mixed' if any(v == 0 for v in values) else 'numeric'


def package_report(path):
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith('.xml')]
        if len(names) != 1:
            raise ValueError(f'{path}: expected one JVF XML')
        root = ET.fromstring(z.read(names[0]))
    if root.findtext('.//di:TypDatoveSady', namespaces=NS) != '7':
        raise ValueError(f'{path}: not DI set 7')
    layers = {}
    for kind in ('OsaKolejeTramvajoveDrahy', 'OsaTramvajoveDrahy'):
        layer = root.find(f'.//obj:{kind}', NS)
        records = [] if layer is None else layer.findall('.//{*}ZaznamObjektu')
        zcounts, flags, dates = Counter(), {f: Counter() for f in FLAGS}, {}
        for record in records:
            lists = record.findall('.//gml:posList', NS)
            values = []
            for line in record.findall('.//gml:LineString', NS):
                if line.get('srsName') != 'EPSG:5514' or line.get('srsDimension') != '3':
                    raise ValueError(f'{path}: expected EPSG:5514 3D track geometry')
            for pos in lists:
                coords = [float(v) for v in (pos.text or '').split()]
                if len(coords) % 3:
                    raise ValueError(f'{path}: invalid 3D position list')
                values.extend(coords[2::3])
            zcounts[classify_z(values)] += 1
            for field in FLAGS:
                flags[field][record.findtext('.//atr:' + field, default='missing', namespaces=NS)] += 1
            for field in ('DatumVkladu', 'DatumZmeny'):
                value = record.findtext('.//atr:' + field, namespaces=NS)
                if value:
                    dates.setdefault(field, []).append(value)
        layers[kind] = {'features': len(records), 'z': dict(sorted(zcounts.items())),
                        'flags': {k: dict(sorted(v.items())) for k, v in flags.items()},
                        'dates': {k: {'min': min(v), 'max': max(v)} for k, v in dates.items()}}
    if not any(v['features'] for v in layers.values()):
        raise ValueError(f'{path}: neither expected tram layer has records; check the JVF schema')
    return {'jvf': root.findtext('.//cmn:VerzeJVFDTM', namespaces=NS),
            'state': root.findtext('.//di:DatumPlatnosti', namespaces=NS), 'layers': layers}


def report(selected):
    provenance = json.loads((RAW / 'provenance.json').read_text(encoding='utf-8'))
    packages = {p['code']: p for p in provenance['packages']}
    rows = []
    for district in selected:
        entry = packages[district['code']]
        path = RAW / entry['file']
        if sha(path) != entry['sha256']:
            raise ValueError(f'{path}: hash differs from provenance')
        result = package_report(path)
        if datetime.fromisoformat(result['state']) != datetime.fromisoformat(entry['state']):
            raise ValueError(f'{path}: XML date differs from catalogue')
        rows.append(district | result | {'file': entry['file'], 'sha256': entry['sha256']})
        tracks = result['layers']['OsaKolejeTramvajoveDrahy']
        print(f"{district['name']:18} {district['code']} lines={district['lines']} "
              f"tracks={tracks['features']} Z={tracks['z']}")
    return {'lines': list(LINES), 'districts': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='refresh source files from the provider')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'dtm-di.json')
    args = parser.parse_args()
    selected = districts()
    if args.fetch:
        acquire(selected)
    write_json(args.output, report(selected))
    print(f'Report: {args.output}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
