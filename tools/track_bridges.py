# SPDX-License-Identifier: AGPL-3.0-or-later
"""Track on a Mosty 3D bridge: the structures OSM does not tag, for the track-height structure mask (#192).

    python -P -E tools/track_bridges.py               # calibration: OSM tram bridges (on) vs bridges over trams (under)

A footprint alone also covers track under a road bridge. A piece of track inside a footprint is on the bridge when
the track's height where it enters or leaves meets the model's top there; under a bridge the gap is the clearance.
The model never supplies a height (+-0.5 m, photogrammetry 2001-2008).
"""
import json
import sys
from collections import Counter
from pathlib import Path

import shapely
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, substring, unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo import Frame  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MIN_PIECE = 4.0   # m of track inside a footprint: shorter is a corner or a parapet overhang
INSETS = (1.5, 3, 4.5, 6)   # m inside the footprint where the model's top is read: their median, past a statue
                            # or a pylon at a bridge's end (Mánesův most: 5.9 m above the rail at one inset)
OUTSET = 2.0      # m outside where the track's height is read


def pieces(lines, bridges):
    """(line, piece, feature index) for every stretch of merged track inside a bridge footprint."""
    for line in lines:
        for k in bridges.foot_tree.query(line, predicate='intersects'):
            inside = line.intersection(bridges.footprints[k])
            for p in getattr(inside, 'geoms', [inside]):
                if p.geom_type == 'LineString' and p.length >= MIN_PIECE:
                    yield line, p, int(k)


def edges(line, piece, bridges, k, height):
    """Per end of the piece: (gaps = model top - each track height candidate, top); None where either is unknown."""
    out = []
    a, b = line.project(Point(piece.coords[0])), line.project(Point(piece.coords[-1]))
    lo, hi = min(a, b), max(a, b)
    for s, inward in ((lo, 1), (hi, -1)):
        if (inward > 0 and s < 0.01) or (inward < 0 and s > line.length - 0.01):
            out.append(None)                # the track ends on the bridge: no outside to compare
            continue
        p_out = line.interpolate(min(line.length, max(0.0, s - inward * OUTSET)))
        tops = sorted(z for z in (bridges.top_of(p.x, p.y, k) for p in
                                  (line.interpolate(s + inward * min(d, (hi - lo) / 2)) for d in INSETS))
                      if z is not None)
        top = tops[len(tops) // 2] if tops else None
        hs = height(p_out.x, p_out.y, line, s - inward * OUTSET)
        out.append(None if top is None or not hs else ([top - h for h in hs], top))
    return out


# m: calibrated 2026-11-02 against OSM (python -P -E tools/track_bridges.py): the nearest end of a tram bridge's piece
# within 1.05 m of the top (68 pieces with heights), track under a bridge 3.30 m or more below it (114)
ON, UNDER = 1.5, 3.0
# m: where the model's top is no higher than this above the lidar terrain, the bridge stands on land (an abutment):
# the track is at grade there and the terrain check holds (Palackého most's Smíchov end: top 197.5, terrain 197.2-197.5)
ABUTMENT = 1.5
STEP = 2.0        # m between samples along a piece for the abutment trim


def verdict(ends):
    """'on' when a height at an end meets the top (the other end, or the archive, may be the ground under the
    deck: Libeň, Palackého most); 'under' when every known height at every end is a clearance; else 'unknown'."""
    gaps = [g for e in ends if e for g in e[0]]
    if any(abs(g) <= ON for g in gaps):
        return 'on'
    if gaps and all(g >= UNDER for g in gaps):
        return 'under'
    return 'unknown'


class Heights:
    """The track's height candidates at a point: numeric DI alone where it exists, else the matched archive and the
    lidar terrain (the archive dives to the river across Palackého most; the terrain at an abutment is the deck)."""

    def __init__(self, current, archive, terrain):
        self.current, self.archive, self.terrain = current, archive, terrain

    def __call__(self, x, y, line, s):
        q = line.interpolate(min(line.length, max(0.0, s + 0.5)))
        p = line.interpolate(min(line.length, max(0.0, s - 0.5)))
        dx, dy = q.x - p.x, q.y - p.y
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        m = self.current.match(x, y, dx / n, dy / n)
        if m['status'] == 'numeric':
            return [m['z']]
        m = self.archive.match(x, y, dx / n, dy / n)
        z = self.terrain([x], [y])[0]
        return ([m['z']] if m['status'] == 'numeric' else []) + ([z] if z is not None and z == z else [])


def track_lines(paths):
    merged = unary_union([LineString([c[:2] for c in p['coords']]) for p in paths if len(p['coords']) > 1])
    merged = merged if merged.geom_type == 'LineString' else linemerge(merged)
    return list(getattr(merged, 'geoms', [merged]))


def decide(paths, current, archive, terrain, bridges=None):
    """Every piece of track inside a footprint with its verdict: [{'feature', 'piece', 'ends', 'verdict'}]."""
    from mosty3d import Bridges
    bridges = bridges or Bridges()
    height = Heights(current, archive, terrain)
    out = []
    for line, piece, k in pieces(track_lines(paths), bridges):
        ends = edges(line, piece, bridges, k, height)
        out.append({'feature': bridges.ids[k], 'piece': piece, 'ends': ends, 'verdict': verdict(ends)})
    # A bridge split into features: an unknown piece continuing an 'on' piece is on it.
    changed = True
    while changed:
        changed = False
        ends_on = [Point(c) for f in out if f['verdict'] == 'on' for c in (f['piece'].coords[0], f['piece'].coords[-1])]
        tree = shapely.STRtree(ends_on) if ends_on else None
        for f in out:
            if f['verdict'] == 'unknown' and tree is not None and any(
                    len(tree.query(Point(c).buffer(1.0))) for c in (f['piece'].coords[0], f['piece'].coords[-1])):
                f['verdict'], f['continues'], changed = 'on', True, True
    for f in out:
        if f['verdict'] == 'on':
            f['decks'] = decks(f['piece'], bridges, bridges.ids.index(f['feature']), terrain)
    return out


def decks(piece, bridges, k, terrain):
    """The parts of an 'on' piece with room under the deck: the model's top more than ABUTMENT above the terrain
    (or no terrain or top to compare: kept)."""
    n = max(1, round(piece.length / STEP))
    ss = [piece.length * (i + 0.5) / n for i in range(n)]
    pts = [piece.interpolate(s) for s in ss]
    ground = terrain([p.x for p in pts], [p.y for p in pts])
    keep = []
    for p, z in zip(pts, ground):
        top = bridges.top_of(p.x, p.y, k)
        keep.append(top is None or z is None or z != z or top - z > ABUTMENT)
    out, start = [], None
    for i, kept in enumerate(keep + [False]):
        if kept and start is None:
            start = i
        elif not kept and start is not None:
            a, b = piece.length * start / n, piece.length * i / n
            if b - a >= MIN_PIECE:
                out.append(substring(piece, a, b))
            start = None
    return out


def mask(found, width=5):
    """The 'on' pieces as a structure corridor, their ids for the import's structure list, and the pieces for the
    review (tools/track_structure_review.py groups them as bridges)."""
    on = [(f, d) for f in found if f['verdict'] == 'on' for d in f.get('decks', [f['piece']])]
    geom = unary_union([d.buffer(width) for _, d in on]) if on else shapely.Polygon()
    pieces = [{'id': f'mosty3d:{f["feature"]}', 'xy': [[round(x, 2), round(y, 2)] for x, y in d.coords],
               'end_gaps_m': [[round(g, 2) for g in e[0]] if e else None for e in f['ends']],
               **({'continues': True} if f.get('continues') else {})} for f, d in on]
    return geom, sorted({p['id'] for p in pieces}), pieces


def osm_cases():
    """OSM's word per place: tram bridges (on) and other bridges crossing tram track (under)."""
    from osm_local import ways
    frame = Frame()
    tram = lambda t: 'tram' in (t.get('railway'), t.get('disused:railway'), t.get('construction:railway'),
                                t.get('construction'))
    def geom(w):
        x, y = frame.xy([p['lat'] for p in w['geometry']], [p['lon'] for p in w['geometry']])
        return LineString(zip(x, y))
    tracks = ways(lambda t: tram(t))
    on = unary_union([geom(w) for w in tracks if w['tags'].get('bridge', 'no') != 'no']).buffer(4)
    over = ways(lambda t: not tram(t) and t.get('bridge', 'no') != 'no'
                and ('highway' in t or 'railway' in t))
    all_track = unary_union([geom(w) for w in tracks])
    under = unary_union([geom(w).buffer(6) for w in over if geom(w).crosses(all_track)])
    return on, under


def calibrate():
    from dtmp_tracks import Segments, archive_data, di_data
    from import_track_heights import Terrain
    _, paths = di_data()
    _, _, archived = archive_data()
    found = decide(paths, Segments(paths), Segments(archived), Terrain())
    on, under = osm_cases()
    rows = []
    for f in found:
        mid = f['piece'].interpolate(0.5, normalized=True)
        case = 'osm_on' if on.contains(mid) else 'osm_under' if under.contains(mid) else 'untagged'
        gaps = [[round(g, 2) for g in e[0]] for e in f['ends'] if e]
        lat, lon = Frame().ll(mid.x, mid.y)
        rows.append({'case': case, 'verdict': f['verdict'], 'feature': f['feature'], 'length_m': round(f['piece'].length, 1),
                     'deck_m': round(sum(d.length for d in f.get('decks', [])), 1),
                     'gaps_m': gaps, 'at': [round(float(lat), 6), round(float(lon), 6)]})
    table = Counter((r['case'], r['verdict']) for r in rows)
    metres, deck = Counter(), Counter()
    for r in rows:
        metres[(r['case'], r['verdict'])] += r['length_m']
        deck[(r['case'], r['verdict'])] += r['deck_m']
    for (case, v), n in sorted(table.items()):
        print(f'{case:10} {v:8} {n:4} pieces {metres[(case, v)]:8.0f} m' + (f', {deck[(case, v)]:.0f} m over open space' if v == 'on' else ''))
    out = ROOT / 'reports/track-bridges.json'
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'wrote {out}')


if __name__ == '__main__':
    calibrate()
