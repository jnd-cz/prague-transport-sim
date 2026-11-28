# SPDX-License-Identifier: AGPL-3.0-or-later
"""The feature layer (#14): every placed object of a line as one record, data/lineN.features.json.

    python -P -E tools/features.py --line 17                 # the line's file, from the snapshot and the built survey
    python -P -E tools/features.py --line 17 --geojson OUT   # the records as GeoJSON (EPSG:5514), for a review; no game input

A record: `id` (the source's own, the same on every line that sees the object), `kind`, `x`, `y` (the city frame, m),
`heading` (compass degrees, clockwise from north, the way the object's front, its model's +Z, faces) with `headingFrom`
(what decided it), `mount` (ground, wall), `source` (a level of tools/sources.py's furniture chain), and what the
kind's source knows beside (a shelter's footprint and stop). A height only where the source has one: the game stands
the rest on its ground. The model is the kind's (src/features.js); a record names a `variant` only where it differs.

The file holds the records in groups, one per kind, source and mount, column by column (`records()` gives them
back): a line has some 20,000 of them. Sources now: the archive survey's points (raw/dtmpoints, fetched by
tools/dtm_points.py) and the surveyed shelter footprints (data/lineN.dtm.json, tools/zps_shelters.py). The design:
docs/decisions/2026-11-28-feature-layer.md.
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I leaves it out)
import sources  # noqa: E402
from atomic import replacing  # noqa: E402
from geo import ORIGIN, ROOT  # noqa: E402

VERSION = 1

# the archive survey's point codes (DTMP ctmtp_kod) we keep, and the kind each is
DTMP = {
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
WALL = {'signal_on_building', 'stop_sign_on_building', 'light_on_building'}  # (the survey's "on a building" codes)
# one shaft is often recorded twice, under two networks' codes: one cover per MERGE m (each way) of a kind
MERGED = {'manhole', 'gutter_inlet', 'hydrant_cap', 'hydrant', 'valve_cap'}
MERGE = 0.3
STREET = {'gutter_inlet'}  # (kinds that lie along the nearest street)
CELL = 20.0  # m: the street segments are looked up by their middle's cell, the cell around a point and its eight neighbours
COLUMNS = ('heading', 'z', 'length', 'width', 'stop', 'variant')  # (a group's columns beside id and xy, where any record has one)


def survey_points(raw, to_xy):
    """The archive survey's points as records. raw: raw/dtmpoints/lineN.json; to_xy(lat, lon) -> the city frame."""
    out = []
    for f in raw['features']:
        kind = DTMP.get(f['attributes']['ctmtp_kod'])
        if not kind or 'geometry' not in f:
            continue
        x, y = to_xy(f['geometry']['y'], f['geometry']['x'])
        out.append({'id': f"dtmp:{f['attributes']['objectid']}", 'kind': kind, 'x': round(x, 2), 'y': round(y, 2),
                    'mount': 'wall' if kind in WALL else 'ground', 'source': 'dtmpoints'})
    return out


def merge(recs, kinds=MERGED, r=MERGE):
    """(kept, dropped count): of a kind in `kinds`, one record per r m each way, the first by (x, y)."""
    kept, cells, dropped = [], {}, 0
    for o in sorted(recs, key=lambda o: (o['kind'], o['x'], o['y'], o['id'])):
        if o['kind'] not in kinds:
            kept.append(o)
            continue
        i, j = math.floor(o['x'] / r), math.floor(o['y'] / r)
        near = (p for di in (-1, 0, 1) for dj in (-1, 0, 1) for p in cells.get((o['kind'], i + di, j + dj), ()))
        if any(abs(p['x'] - o['x']) < r and abs(p['y'] - o['y']) < r for p in near):
            dropped += 1
            continue
        cells.setdefault((o['kind'], i, j), []).append(o)
        kept.append(o)
    return kept, dropped


def street_bearing(roads):
    """A function (x, y) -> the compass bearing (degrees) of the nearest carriageway segment, None where none is near.
    roads: line.json's (`p` polyline, `c` a carriageway, `f` a footway)."""
    grid = {}
    for r in roads:
        if not r.get('c') or r.get('f'):
            continue
        for a, b in zip(r['p'], r['p'][1:]):
            grid.setdefault((math.floor((a[0] + b[0]) / 2 / CELL), math.floor((a[1] + b[1]) / 2 / CELL)), []).append((a, b))

    def bearing(x, y):
        best = None
        for gx in (-1, 0, 1):
            for gy in (-1, 0, 1):
                for a, b in grid.get((math.floor(x / CELL) + gx, math.floor(y / CELL) + gy), ()):
                    dx, dy = b[0] - a[0], b[1] - a[1]
                    t = max(0.0, min(1.0, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy or 1e-9)))
                    d = math.hypot(a[0] + dx * t - x, a[1] + dy * t - y)
                    if best is None or d < best[0]:
                        best = (d, math.degrees(math.atan2(dx, dy)) % 360)
        return None if best is None else round(best[1], 1)
    return bearing


def along_streets(recs, roads, kinds=STREET):
    """The heading of the kinds that lie along a street: the nearest carriageway segment's (in place)."""
    bearing = street_bearing(roads)
    for o in recs:
        if o['kind'] in kinds and (b := bearing(o['x'], o['y'])) is not None:
            o['heading'], o['headingFrom'] = b, 'street'
    return recs


def shelters(footprints, tracks):
    """The surveyed shelter footprints (dtm.json `shelters`) as records. The front faces the nearer track: of the two
    ways across the footprint's long side, the one towards the nearest point of `tracks` (polylines of [x, y])."""
    pts = [p for t in tracks for p in t]
    out = []
    for s in footprints:
        along = math.radians(s['bearing'])  # (the long side, from the x axis)
        nx, ny = -math.sin(along), math.cos(along)
        if pts:
            px, py = min(pts, key=lambda p: (p[0] - s['x']) ** 2 + (p[1] - s['y']) ** 2)[:2]
            if (px - s['x']) * nx + (py - s['y']) * ny < 0:
                nx, ny = -nx, -ny
        e, n = round((s['x'] + ORIGIN[0]) / 2) * 2, round((s['y'] + ORIGIN[1]) / 2) * 2  # (S-JTSK, to 2 m: no source ID)
        out.append({'id': f'shelter:zps:{e},{n}', 'kind': 'shelter', 'x': s['x'], 'y': s['y'],
                    'heading': round(math.degrees(math.atan2(nx, ny)) % 360, 1), 'headingFrom': 'footprint',
                    'mount': 'ground', 'source': 'zps', 'z': s['z'], 'length': s['length'], 'width': s['width'],
                    'stop': (s.get('stop') or {}).get('id')})
    return out


def pack(recs):
    """The records as groups (kind, source, mount), each column by column, sorted: the file's `groups`."""
    groups = {}
    for o in sorted(recs, key=lambda o: (o['kind'], o['source'], o['mount'], o['x'], o['y'], o['id'])):
        groups.setdefault((o['kind'], o['source'], o['mount']), []).append(o)
    out = []
    for (kind, source, mount), rs in groups.items():
        g = {'kind': kind, 'source': source, 'mount': mount, 'id': [o['id'] for o in rs],
             'xy': [v for o in rs for v in (o['x'], o['y'])]}
        froms = {o['headingFrom'] for o in rs if o.get('heading') is not None}
        if len(froms) > 1:
            raise ValueError(f'{kind} from {source}: headings from {sorted(froms)} in one group')
        if froms:
            g['headingFrom'] = froms.pop()
        for c in COLUMNS:
            if any(o.get(c) is not None for o in rs):
                g[c] = [o.get(c) for o in rs]
        out.append(g)
    return out


def records(groups):
    """The file's groups back as records."""
    out = []
    for g in groups:
        for i, fid in enumerate(g['id']):
            o = {'id': fid, 'kind': g['kind'], 'x': g['xy'][2 * i], 'y': g['xy'][2 * i + 1], 'mount': g['mount'], 'source': g['source']}
            for c in COLUMNS:
                if c in g and g[c][i] is not None:
                    o[c] = g[c][i]
            if 'heading' in o:
                o['headingFrom'] = g['headingFrom']
            out.append(o)
    return out


def compile_line(raw, line, dtm=None, to_xy=None):
    """A line's file (without its provenance): raw/dtmpoints' answer, data/lineN.json, data/lineN.dtm.json or None."""
    pts, dropped = merge(survey_points(raw, to_xy))
    along_streets(pts, line['roads'])
    shel = shelters((dtm or {}).get('shelters', ()), [line['path'], line.get('pathBack') or []])
    ids = [o['id'] for o in pts + shel]
    if len(set(ids)) != len(ids):
        raise ValueError('two features with one id')
    return {'version': VERSION, 'groups': pack(pts + shel), 'merged': dropped}, len(pts), len(shel)


def geojson(recs, line):
    """The records as a GeoJSON collection in S-JTSK (EPSG:5514), as data/lineN.built.geojson is."""
    return {'type': 'FeatureCollection', 'crs': {'type': 'name', 'properties': {'name': 'urn:ogc:def:crs:EPSG::5514'}},
            'properties': {'line': str(line), 'origin': list(ORIGIN)},
            'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [round(o['x'] + ORIGIN[0], 2), round(o['y'] + ORIGIN[1], 2)]},
                          'properties': {k: v for k, v in o.items() if k not in ('x', 'y')} | {'type': o['kind']}} for o in recs]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--line', default='17')
    ap.add_argument('--geojson', help='write the records as GeoJSON here instead of the line\'s file')
    ap.add_argument('--root', default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    from geo import Frame
    data = lambda name: os.path.join(a.root, 'data', f'line{a.line}.{name}')  # noqa: E731
    line = json.load(open(data('json'), encoding='utf-8'))
    raw = json.load(open(os.path.join(a.root, 'raw', 'dtmpoints', f'line{a.line}.json'), encoding='utf-8'))
    dtm = json.load(open(data('dtm.json'), encoding='utf-8')) if os.path.exists(data('dtm.json')) else None
    out, n_pts, n_shel = compile_line(raw, line, dtm, Frame().xy)
    if a.geojson:
        with replacing(a.geojson, 'w', encoding='utf-8') as fh:
            json.dump(geojson(records(out['groups']), a.line), fh, ensure_ascii=False, separators=(',', ':'))
        print(f"line {a.line}: {n_pts + n_shel} features -> {a.geojson}")
        return
    out['fetched'] = raw['fetched']
    out['provenance'] = sources.stamp('features.py', {'groups': sources.entry('furniture', [n_pts, n_shel, 0, 0], checks={'merged': out['merged']})})
    out['attribution'] = sources.attribution(out['provenance'])
    with replacing(data('features.json'), 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(',', ':'))
    counts = {}
    for g in out['groups']:
        counts[g['kind']] = counts.get(g['kind'], 0) + len(g['id'])
    print(f"line {a.line}: " + ', '.join(f'{v} {k}' for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
          + f"; {out['merged']} merged -> data/line{a.line}.features.json")


if __name__ == '__main__':
    main()
