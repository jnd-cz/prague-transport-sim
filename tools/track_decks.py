"""ZPS deck heights for the track-height stage; rail offsets come only from truth facts."""
import json
import math
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, substring, triangulate
from shapely.strtree import STRtree

from dtm_di import sha


class Decks:
    def __init__(self, records, facts=(), style_regions=()):
        self.records, self.polygons, self.triangles = [], [], {}
        for record in records:
            poly = Polygon([v[:2] for v in record['ring']], record.get('holes', []))
            if poly.is_valid and not poly.is_empty:
                self.records.append(record)
                self.polygons.append(poly)
        self.tree = STRtree(self.polygons)
        self.facts = list(facts)
        self.style_regions = list(style_regions)
        ids = set()
        for fact in self.facts:
            if (not fact.get('id') or fact['id'] in ids or not fact.get('source') or not fact.get('date') or
                    not isinstance(fact.get('metres'), (int,float)) or not math.isfinite(fact['metres']) or fact['metres'] < 0):
                raise ValueError('railAboveDeck facts need unique id, finite nonnegative metres, source and date')
            scopes = [fact.get('scope') == 'all', bool(fact.get('di_ids')), bool(fact.get('bounds'))]
            if sum(scopes) != 1:
                raise ValueError('railAboveDeck fact needs exactly one scope: all, di_ids or city-frame bounds')
            if fact.get('styles') and (not isinstance(fact['styles'], list) or
                                      any(s not in ('embedded','panels','grass','ballast') for s in fact['styles'])):
                raise ValueError('unknown railAboveDeck track style')
            if fact.get('bounds'):
                b = fact['bounds']
                if len(b) != 4 or not all(math.isfinite(v) for v in b) or b[0] > b[2] or b[1] > b[3]:
                    raise ValueError('invalid railAboveDeck bounds')
            ids.add(fact['id'])

    def _height(self, index, point):
        if index not in self.triangles:
            record, poly = self.records[index], self.polygons[index]
            zs = {}
            for v in record['ring']:
                if len(v) > 2 and v[2] is not None and math.isfinite(v[2]):
                    zs.setdefault(tuple(v[:2]), set()).add(v[2])
            triangles = []
            for t in triangulate(poly):
                vertices = list(t.exterior.coords)[:3]
                if poly.covers(t) and all(len(zs.get(v, ())) == 1 for v in vertices):
                    triangles.append((t, [(*v, next(iter(zs[v]))) for v in vertices]))
            self.triangles[index] = triangles
        heights = []
        for triangle, v in self.triangles[index]:
            if not triangle.covers(point):
                continue
            (x0,y0,z0),(x1,y1,z1),(x2,y2,z2) = v
            det = (y1-y2)*(x0-x2) + (x2-x1)*(y0-y2)
            if abs(det) < 1e-9:
                continue
            a = ((y1-y2)*(point.x-x2) + (x2-x1)*(point.y-y2))/det
            b = ((y2-y0)*(point.x-x2) + (x0-x2)*(point.y-y2))/det
            heights.append(a*z0 + b*z1 + (1-a-b)*z2)
        return heights[0] if heights and max(heights)-min(heights) <= .3 else None

    def candidates(self, x, y, di_id):
        point, out = Point(x,y), []
        regions = [r for r in self.style_regions if r['polygon'].covers(point)]
        styles = {r['style'] for r in regions}
        defaulted = not styles
        styles = styles or {'panels'}
        facts = [f for f in self.facts if (not f.get('styles') or styles.intersection(f['styles'])) and (f.get('scope') == 'all' or
                 str(di_id) in {str(i) for i in f.get('di_ids', [])} or
                 (f.get('bounds') and f['bounds'][0] <= x <= f['bounds'][2] and f['bounds'][1] <= y <= f['bounds'][3]))]
        for index in sorted(self.tree.query(point.buffer(2))):
            poly, record = self.polygons[index], self.records[index]
            distance = poly.distance(point)
            if distance > 2:
                continue
            inside = poly.covers(point)
            q = point if inside else nearest_points(poly,point)[0]
            z = self._height(index,q)
            candidate = {'id':record['id'], 'level':record['level'], 'surface_z':z, 'z':None,
                         'inside':inside, 'distance':distance, 'offset_fact_ids':[f['id'] for f in facts],
                         'track_styles':sorted(styles), 'style_defaulted':defaulted,
                         'style_sources':[r.get('source',{}) for r in regions],
                         'provenance':record['source']}
            if z is None:
                candidate['excluded'] = 'deck_surface_height_unavailable'
            elif not facts:
                candidate['excluded'] = 'deck_rail_offset_missing'
            elif max(f['metres'] for f in facts) - min(f['metres'] for f in facts) > 1e-9:
                candidate['excluded'] = 'ambiguous_rail_offset_facts'
            else:
                candidate['z'] = z + facts[0]['metres']
                candidate['rail_above_deck_m'] = facts[0]['metres']
            out.append(candidate)
        return out


def load_decks(root):
    root = Path(root)
    manifest = json.loads((root / 'data/MANIFEST.json').read_text(encoding='utf-8'))
    snap = json.loads((root / 'snapshots' / (manifest['snapshot'] + '.json')).read_text(encoding='utf-8'))
    dates = sorted({Path(f['path']).name.split('_')[4] for g in snap['groups'] if g['name']=='dtm' for f in g['files']})
    records = []
    for line in (17,22):
        name = f'line{line}.dtm.json'
        path = root / 'data' / name
        if not path.exists():
            continue
        digest = sha(path)
        published = manifest['files'].get(name,{}).get('sha256') == digest
        data = json.loads(path.read_text(encoding='utf-8'))
        for i, area in enumerate(data['areas']):
            if area['c'] != 'deck':
                continue
            identity = f'{name}#areas/{i}'
            records.append({'id':identity, 'ring':area['r'], 'holes':[[v[:2] for v in h] for h in area.get('h',[])],
                            'level':area['l'], 'source':{'record':identity, 'file':f'data/{name}', 'sha256':digest,
                            'source_snapshot':manifest['snapshot'] if published else None,
                            'date':dates[0] if published and len(dates)==1 else None,
                            'date_kind':'source_package_state' if published else 'unpublished_build'}})
    truth = json.loads((root / 'data/truth.json').read_text(encoding='utf-8'))
    facts = truth.get('trackHeights',{}).get('railAboveDeck',[])
    styles, lines = [], {}
    for mark_index, mark in enumerate(truth.get('trackStyles',[])):
        line = str(mark['line'])
        if line not in lines:
            lines[line] = json.loads((root / f'data/line{line}.json').read_text(encoding='utf-8'))
        data = lines[line]
        a = next((i for i,st in enumerate(data['stops']) if st['name']==mark['from']), None)
        b = next((i for i,st in enumerate(data['stops']) if a is not None and i>a and st['name']==mark['to']), None)
        if a is None or b is None:
            continue
        section = substring(LineString([p[:2] for p in data['path']]), data['stops'][a]['s'], data['stops'][b]['s'])
        styles.append({'style':mark['style'], 'polygon':section.buffer(5,cap_style=2),
                       'source':{'record':f'data/truth.json#trackStyles/{mark_index}', **mark}})
    return Decks(records,facts,styles)
