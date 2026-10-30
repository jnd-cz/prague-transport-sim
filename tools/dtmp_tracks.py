"""Archived DTMP tram axes and height fallback assessment for the DI districts (#61).

    python -P -E tools/dtmp_tracks.py --fetch --acquire-only  # explicit upstream acquisition
    python -P -E tools/dtmp_tracks.py                       # offline report from raw snapshot

The small city-wide 55010 layer is acquired completely, then assessment is clipped to the same
16 DI export polygons. Never imports the archive into generated game data.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
from dtm_di import NS, sha, write_json
from geo import Frame, load_line

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'raw' / 'dtmp-tracks'
DI = ROOT / 'raw' / 'dtm-di'
SERVICE = 'https://gs-pub.praha.eu/arcgis/rest/services/dtmp/dtmp/MapServer'
LAYER = SERVICE + '/10'
WHERE = 'CTMTP_KOD=55010'
STEP = 5.0
RADIUS = 1.0
ANGLE = 15.0


def structure_mask():
    """A plan match cannot establish track Z on a structure (archive has ground Z on Trojsky most)."""
    from osm_local import ways
    tagged = ways(lambda t: t.get('railway') == 'tram' and (
        t.get('bridge', 'no') != 'no' or t.get('tunnel', 'no') != 'no'
        or t.get('covered') == 'yes' or t.get('layer', '0') != '0'))
    geoms = []
    for way in tagged:
        coords = way['geometry']
        x, y = Frame().xy([p['lat'] for p in coords], [p['lon'] for p in coords])
        geoms.append(LineString(zip(x, y)))
    return unary_union(geoms).buffer(5), [w['id'] for w in tagged]


def request(url, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={'User-Agent': 'prague-transport-sim/DTMP-research'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                result = json.load(r)
            if 'error' in result:
                raise ValueError(result['error'])
            return result
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2)


def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    metadata = request(LAYER, {'f': 'json'})
    write_json(RAW / 'layer10.json', metadata)
    if not metadata.get('hasZ'):
        raise ValueError('archive no longer advertises Z')
    params = {'f': 'json', 'where': WHERE, 'returnIdsOnly': 'true'}
    ids = request(LAYER + '/query', params)
    if 'objectIds' not in ids or len(ids['objectIds']) != len(set(ids['objectIds'])):
        raise ValueError('missing or duplicate archive object IDs')
    write_json(RAW / 'ids.json', ids)
    pages = []
    wanted = sorted(ids['objectIds'])
    for offset in range(0, len(wanted), 500):
        batch = wanted[offset:offset + 500]
        query = {'f': 'json', 'where': WHERE, 'objectIds': ','.join(map(str, batch)),
                 'outFields': '*', 'outSR': 5514, 'returnGeometry': 'true', 'returnZ': 'true'}
        page = request(LAYER + '/query', query)
        if page.get('exceededTransferLimit'):
            raise ValueError('archive truncated an explicit ID batch')
        got = [f['attributes']['OBJECTID'] for f in page.get('features', [])]
        if sorted(got) != batch:
            raise ValueError('archive did not return the requested ID batch exactly')
        if not page.get('hasZ') or page['spatialReference'].get('latestWkid',
                page['spatialReference'].get('wkid')) != 5514:
            raise ValueError('archive response lacks EPSG:5514 and Z')
        name = f'page-{offset // 500:03}.json'
        write_json(RAW / name, page)
        pages.append({'file': name, 'sha256': sha(RAW / name), 'query': query})
        print(f'archive: {offset + len(batch)}/{len(wanted)} features', flush=True)
    write_json(RAW / 'provenance.json', {
        'service': SERVICE, 'layer': LAYER, 'query_url': LAYER + '/query',
        'acquired': datetime.now(timezone.utc).isoformat(), 'where': WHERE,
        'licence': 'CC BY 4.0, datový podklad © IPR Praha; IPR download-service terms I.8',
        'terms': 'raw/dtm-di/terms.pdf', 'terms_sha256': sha(DI / 'terms.pdf'),
        'archive_period': 'DTMP operation ended 2024-06-30; record dates retained individually',
        'ids_query': params, 'ids_sha256': sha(RAW / 'ids.json'), 'pages': pages})


def xyz(values):
    """Native S-JTSK through the shared frame; preserve the source Bpv Z."""
    x, y = Frame().from_jtsk([v[0] for v in values], [v[1] for v in values])
    return [(float(a), float(b), v[2] if len(v) > 2 else None)
            for a, b, v in zip(x, y, values)]


def di_data():
    provenance = json.loads((DI / 'provenance.json').read_text(encoding='utf-8'))
    districts, paths, seen = [], [], set()
    for entry in provenance['packages']:
        file = DI / entry['file']
        if sha(file) != entry['sha256']:
            raise ValueError(f'{file}: source hash mismatch')
        with zipfile.ZipFile(file) as z:
            root = ET.fromstring(z.read(next(n for n in z.namelist() if n.endswith('.xml'))))
        rings = []
        polygon = root.find('.//di:ObvodDatoveSady/gml:Polygon', NS)
        for ring in polygon.findall('.//gml:posList', NS):
            vals = [float(v) for v in ring.text.split()]
            x, y = Frame().from_jtsk(vals[::2], vals[1::2])
            rings.append(list(zip(x, y)))
        districts.append(entry | {'polygon': Polygon(rings[0], rings[1:])})
        layer = root.find('.//obj:OsaKolejeTramvajoveDrahy', NS)
        if layer is None:
            continue
        for rec in layer.findall('.//{*}ZaznamObjektu'):
            identity = rec.findtext('.//atr:ID', namespaces=NS)
            attrs = {n.tag.split('}')[-1]: n.text for n in rec.iter()
                     if n.tag.startswith('{atr}') and len(n) == 0}
            for line in rec.findall('.//gml:LineString', NS):
                if line.get('srsDimension') != '3' or line.get('srsName') != 'EPSG:5514':
                    raise ValueError('unexpected DI coordinates')
                vals = [float(v) for v in line.find('gml:posList', NS).text.split()]
                coords = xyz([vals[i:i + 3] for i in range(0, len(vals), 3)])
                key = (identity, tuple(coords))
                if key not in seen:
                    paths.append({'id': identity, 'coords': coords, 'attrs': attrs})
                    seen.add(key)
    return districts, paths


def archive_data():
    provenance = json.loads((RAW / 'provenance.json').read_text(encoding='utf-8'))
    ids = json.loads((RAW / 'ids.json').read_text(encoding='utf-8'))
    if sha(RAW / 'ids.json') != provenance['ids_sha256']:
        raise ValueError('archive ID manifest hash mismatch')
    features, paths = {}, []
    for page in provenance['pages']:
        file = RAW / page['file']
        if sha(file) != page['sha256']:
            raise ValueError(f'{file}: source hash mismatch')
        for feature in json.loads(file.read_text(encoding='utf-8'))['features']:
            attrs = feature['attributes']
            identity = attrs['OBJECTID']
            if identity in features or attrs['CTMTP_KOD'] != 55010:
                raise ValueError('duplicate archive feature or wrong track classification')
            features[identity] = feature
            for coords in feature.get('geometry', {}).get('paths', []):
                paths.append({'id': identity, 'coords': xyz(coords), 'attrs': attrs})
    if sorted(features) != sorted(ids['objectIds']):
        raise ValueError('archive pages do not match the ID inventory')
    return provenance, features, paths


def good_z(z):
    # Deliberately broad sanity range for Prague Bpv. Numeric is not a quality certification.
    return z is not None and math.isfinite(z) and 100 < z < 500


class Segments:
    def __init__(self, paths):
        self.rows, geoms = [], []
        for path in paths:
            for a, b in zip(path['coords'], path['coords'][1:]):
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                if length < 1e-6:
                    continue
                row = {'a': a, 'b': b, 'length': length, 'id': path['id'], 'attrs': path['attrs']}
                self.rows.append(row)
                geoms.append(LineString([a[:2], b[:2]]))
        self.geoms = geoms
        self.tree = STRtree(geoms)

    def match(self, x, y, ux, uy, radius=RADIUS):
        candidates = []
        for index in self.tree.query(Point(x, y).buffer(radius)):
            row = self.rows[index]
            a, b, length = row['a'], row['b'], row['length']
            vx, vy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
            if abs(vx * ux + vy * uy) < math.cos(math.radians(ANGLE)):
                continue
            t = min(1.0, max(0.0, ((x - a[0]) * vx + (y - a[1]) * vy) / length))
            px, py = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
            distance = math.hypot(px - x, py - y)
            if distance > radius:
                continue
            z = a[2] + t * (b[2] - a[2]) if good_z(a[2]) and good_z(b[2]) else None
            candidates.append((distance, str(row['id']), z, row, px, py))
        if not candidates:
            return {'status': 'no_match'}
        candidates.sort(key=lambda c: (c[0], c[1]))
        best = candidates[0]
        # Crossing/overlapping levels with almost equal plan fit must not supply an arbitrary Z.
        if best[2] is not None and any(c[2] is not None and c[0] <= best[0] + 0.25
                                     and abs(c[2] - best[2]) > 0.3 for c in candidates[1:]):
            return {'status': 'ambiguous'}
        return {'status': 'numeric' if best[2] is not None else 'missing_z',
                'z': best[2], 'id': best[3]['id'], 'attrs': best[3]['attrs'],
                'distance': best[0], 'x': best[4], 'y': best[5]}


def samples(segments, area):
    """Clip first, then equal midpoint bins <= 5 m; each observation represents its exact bin length."""
    for row, geom in zip(segments.rows, segments.geoms):
        if area is not None and not area.intersects(geom):
            continue
        clipped = geom if area is None else geom.intersection(area)
        parts = list(clipped.geoms) if hasattr(clipped, 'geoms') else [clipped]
        a, b, length = row['a'], row['b'], row['length']
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        for part in parts:
            if part.geom_type != 'LineString' or part.length < 1e-6:
                continue
            n = math.ceil(part.length / STEP)
            weight = part.length / n
            for j in range(n):
                p = part.interpolate((j + 0.5) * weight)
                t = ((p.x - a[0]) * ux + (p.y - a[1]) * uy) / length
                z = a[2] + t * (b[2] - a[2]) if good_z(a[2]) and good_z(b[2]) else None
                yield {'x': p.x, 'y': p.y, 'ux': ux, 'uy': uy, 'z': z,
                       'weight': weight, 'id': row['id']}


def quantile(values, weights, q):
    if not values:
        return None
    order = np.argsort(values)
    v, w = np.asarray(values)[order], np.asarray(weights)[order]
    return float(v[min(len(v) - 1, np.searchsorted(np.cumsum(w), q * sum(w)))])


def summary(observations):
    counts, deltas, weights, horizontal = Counter(), [], [], []
    for obs in observations:
        weight = obs['weight']
        counts['total_m'] += weight
        current = obs['z'] is not None
        counts['current_z_m' if current else 'missing_z_m'] += weight
        match = obs['archive']
        if match['status'] != 'numeric':
            counts[match['status'] + '_m'] += weight
            continue
        counts['archive_matched_m'] += weight
        if current:
            deltas.append(match['z'] - obs['z'])
            horizontal.append(match['distance'])
            weights.append(weight)
        else:
            counts['fallback_candidate_m'] += weight
            if obs.get('structure'):
                counts['fallback_structure_review_m'] += weight
            elif obs.get('conflict'):
                counts['fallback_conflict_m'] += weight
            else:
                counts['fallback_eligible_m'] += weight
                counts['fallback_corroborated_m' if obs.get('corroborated') else 'fallback_unvalidated_m'] += weight
            if match['distance'] <= 0.5:
                counts['fallback_within_0_5m_m'] += weight
        if match['distance'] <= 0.5:
            counts['tight_match_m'] += weight
    missing = counts['missing_z_m']
    return {'lengths': {k: round(v, 3) for k, v in sorted(counts.items())},
            'fallback_percent_of_missing': round(100 * counts['fallback_candidate_m'] / missing, 2) if missing else None,
            'eligible_percent_of_missing': round(100 * counts['fallback_eligible_m'] / missing, 2) if missing else None,
            'height_comparison': {'matched_m': round(sum(weights), 3),
                                  'median_archive_minus_di_m': quantile(deltas, weights, 0.5),
                                  'p90_absolute_m': quantile([abs(v) for v in deltas], weights, 0.9),
                                  'p99_absolute_m': quantile([abs(v) for v in deltas], weights, 0.99),
                                  'within_0_1m_percent': 100 * sum(w for v, w in zip(deltas, weights) if abs(v) <= .1) / sum(weights) if weights else None,
                                  'within_0_3m_percent': 100 * sum(w for v, w in zip(deltas, weights) if abs(v) <= .3) / sum(weights) if weights else None,
                                  'over_1m_m': sum(w for v, w in zip(deltas, weights) if abs(v) > 1),
                                  'median_xy_m': quantile(horizontal, weights, 0.5)}}


def analyse():
    districts, current_paths = di_data()
    provenance, features, archive_paths = archive_data()
    area = unary_union([d['polygon'] for d in districts])
    current = Segments(current_paths)
    archived = Segments(archive_paths)
    structures, structure_ids = structure_mask()
    print(f"Assessing {len(current_paths)} DI paths ({len(current.rows)} segments) against "
          f"{len(archive_paths)} archived paths ({len(archived.rows)} segments)", flush=True)
    observations, by_archive = [], {}
    for obs in samples(current, area):
        obs['archive'] = archived.match(obs['x'], obs['y'], obs['ux'], obs['uy'])
        match = obs['archive']
        if obs['z'] is not None and match['status'] == 'numeric':
            by_archive.setdefault(match['id'], []).append((match['z'] - obs['z'], obs['weight']))
        observations.append(obs)
    print(f"Compared {len(observations)} length-weighted DI samples", flush=True)
    corroborated, conflicts = set(), set()
    for identity, pairs in by_archive.items():
        v, w = zip(*pairs)
        if sum(w) >= 10 and quantile([abs(x) for x in v], w, .9) <= .3:
            corroborated.add(identity)
        if sum(w) >= 10 and quantile([abs(x) for x in v], w, .9) > .3:
            conflicts.add(identity)
    for obs in observations:
        obs['corroborated'] = obs['archive'].get('id') in corroborated
        obs['conflict'] = obs['archive'].get('id') in conflicts
    district_rows = []
    points = shapely.points([(o['x'], o['y']) for o in observations])
    for obs, hit in zip(observations, shapely.intersects(structures, points)):
        obs['structure'] = bool(hit)
    for district in districts:
        mask = shapely.intersects(district['polygon'], points)
        selected = [o for o, hit in zip(observations, mask) if hit]
        row = {k: district[k] for k in ('code', 'name', 'lines')}
        row.update(summary(selected))
        district_rows.append(row)
        print(f"{row['name']:18} {json.dumps(row['lengths'])}", flush=True)
    routes = []
    for line in (9, 17, 22, 23, 37):
        data = load_line(line)
        route_paths = [{'id': key, 'coords': [(p[0], p[1], None) for p in data[key]], 'attrs': {}}
                       for key in ('path', 'pathBack') if data.get(key)]
        route_obs = []
        for obs in samples(Segments(route_paths), None):
            match = current.match(obs['x'], obs['y'], obs['ux'], obs['uy'], radius=2)
            if match['status'] in ('numeric', 'missing_z'):
                obs['z'] = match['z']
                obs['archive'] = archived.match(match['x'], match['y'], obs['ux'], obs['uy'])
            else:
                obs['archive'] = {'status': 'no_current_di'}
            obs['corroborated'] = obs['archive'].get('id') in corroborated
            obs['conflict'] = obs['archive'].get('id') in conflicts
            route_obs.append(obs)
        for obs, hit in zip(route_obs, shapely.intersects(structures,
                shapely.points([(o['x'], o['y']) for o in route_obs]))):
            obs['structure'] = bool(hit)
        routes.append({'line': line} | summary(route_obs))
        print(f"Line {line}: {len(route_obs)} route samples", flush=True)
    clipped_archive = [p for p in archive_paths if LineString([v[:2] for v in p['coords']]).intersects(area)]
    archived_ids = {p['id'] for p in clipped_archive}
    inventory = {field: dict(Counter(str(features[i]['attributes'].get(field)) for i in archived_ids))
                 for field in ('PUVOD', 'GTC_ID', 'ROK', 'STAV_ZMENA')}
    raw_z = [v[2] for p in clipped_archive for v in p['coords'] if good_z(v[2])]
    feature_z = {}
    for path in clipped_archive:
        feature_z.setdefault(path['id'], []).extend(v[2] for v in path['coords'])
    z_inventory = Counter('all_numeric' if all(good_z(z) for z in zs) else
                          'mixed_or_invalid' if any(good_z(z) for z in zs) else 'no_usable_z'
                          for zs in feature_z.values())
    dates = {}
    for field in ('DAT_VZNIK', 'DAT_ZMENA'):
        values = [features[i]['attributes'][field] for i in archived_ids
                  if features[i]['attributes'].get(field) is not None]
        dates[field] = {'present': len(values), 'min': min(values), 'max': max(values)} if values else {}
    examples = []
    for obs in observations:
        match = obs['archive']
        if obs['z'] is not None and match['status'] == 'numeric' and abs(match['z'] - obs['z']) > 1:
            examples.append({'di_id': obs['id'], 'archive_objectid': match['id'],
                             'xy': [obs['x'], obs['y']], 'delta_m': match['z'] - obs['z'],
                             'di_z': obs['z'], 'archive_z': match['z'],
                             'structure': obs['structure'],
                             'distance_m': match['distance']})
    examples.sort(key=lambda e: -abs(e['delta_m']))
    unique = {}
    for e in examples:
        unique.setdefault((e['di_id'], e['archive_objectid']), e)
    review = list(unique.values())[:20]
    surface_evidence(review)
    return {'method': {'step_m': STEP, 'max_distance_m': RADIUS, 'max_heading_degrees': ANGLE,
                       'usable_z_range_m': [100, 500], 'scope': 'DI export polygons for 16 districts',
                       'structure_review': 'OSM tram bridge/tunnel/covered/nonzero-layer ways, buffered 5m; excluded from eligible fallback',
                       'structure_osm_ways': structure_ids,
                       'corroboration': 'same archive feature: >=10m of numeric DI overlap, p90 |deltaZ| <=0.3m; not independent validation'},
            'archive': {'acquired': provenance['acquired'], 'city_features': len(features),
                        'area_features': len(archived_ids), 'area_attribute_counts': inventory,
                        'area_z_features': dict(z_inventory), 'area_record_dates': dates,
                        'area_numeric_z_min': min(raw_z), 'area_numeric_z_max': max(raw_z),
                        'features_corroborated': len(corroborated), 'features_conflicting': len(conflicts)},
            'overall': summary(observations), 'districts': district_rows, 'lines': routes,
            'comparison_off_structures': summary([o for o in observations if not o['structure']])['height_comparison'],
            'comparison_on_structures': summary([o for o in observations if o['structure']])['height_comparison'],
            'large_height_disagreements': review}


def surface_evidence(examples):
    """Diagnostic only: the existing compiled ZPS deck vertices can help interpret large mismatches."""
    surfaces, polygons = [], []
    for line in (17, 22):
        data = json.loads((ROOT / f'data/line{line}.dtm.json').read_text(encoding='utf-8'))
        for area in data['areas']:
            if area['c'] not in ('deck', 'tram', 'road') or area['l'] != 1:
                continue
            poly = Polygon([v[:2] for v in area['r']])
            if poly.is_valid:
                surfaces.append(area)
                polygons.append(poly)
    tree = STRtree(polygons)
    for example in examples:
        x, y = example['xy']
        point = Point(x, y)
        evidence = []
        for i in tree.query(point.buffer(2)):
            if polygons[i].distance(point) > 2:
                continue
            area = surfaces[i]
            near = sorted(area['r'], key=lambda v: (v[0] - x)**2 + (v[1] - y)**2)[:3]
            evidence.append({'class': area['c'], 'level': 1, 'nearest_vertex_z': [v[2] for v in near]})
        example['compiled_survey_deck_evidence'] = evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--acquire-only', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'reports' / 'dtmp-tracks.json')
    args = parser.parse_args()
    if args.fetch:
        acquire()
    if not args.acquire_only:
        report = analyse()
        write_json(args.output, report)
        print(json.dumps({'overall': report['overall'], 'lines': report['lines']}, indent=2))
        print(f'Report: {args.output}')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
