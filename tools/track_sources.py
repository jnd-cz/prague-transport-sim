# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a line's track did not come from DI (#20, #237).

    python -P -E tools/track_sources.py --line 17            # print the findings
    python -P -E tools/track_sources.py --line 17 --write    # also reports/review/track-sources-17.json (?review)
    python -P -E tools/track_sources.py --line 17 --from-reviews reports/reviews/line17.json   # answers as truth entries

Open the file with ?line=17&review=reports/review/track-sources-17.json. An answer "matches reality" recorded in
data/truth.json trackSources.reviewAnswers (kind and place, with the user's quote) takes the finding off the list;
anything else goes in a note and stays held: the build does not change tracks from answers (#35, M4).

Reads data/lineN.json (its trackSource ranges, track chains with `src`). Finding: a stretch of the route or of a drawn
track within CORRIDOR of it longer than FILL metres taken from the archived DTMP axes or OSM instead of DI. (The
user's orthophoto tracks are facts, not questions. A switch needs no finding since #237: the line's switches are
DI's forks, tools/di_network.py; tools/fork_review.py lists where the drawn track has trouble.)
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from track_moves import Route

ROOT = Path(__file__).resolve().parent.parent
OWN = ('di', 'ortho')   # DI, and the tracks the user measured on the orthophoto (data/truth.json photoTracks)
FILL = 10.0       # m: a fill stretch worth a finding (#20)
CORRIDOR = 60.0   # m: drawn tracks the build takes (tools/build_line.py Q_TRACKS: around.w:60)
GROUP = 30.0      # m: drawn fill tracks this near each other are one place


def findings(data):
    import shapely
    from shapely.geometry import LineString
    out = []
    routes = {k: Route(data[k]) for k in ('path', 'pathBack') if len(data.get(k) or []) > 1}
    lines = {k: LineString(r.pts) for k, r in routes.items()}
    # fill along the route
    for key, ranges in (data.get('trackSource') or {}).items():
        if key not in routes:
            continue
        for a, b, src in ranges:
            if src not in OWN and b - a > FILL:
                x, y = routes[key].at((a + b) / 2)
                out.append({'kind': 'track fill', 'src_track': src, 'where': key, 's': round(a, 1),
                            'length_m': round(b - a, 1), 'x': round(x, 1), 'y': round(y, 1)})
    # fill on drawn tracks near the route (not already on the route), one finding per place (GROUP)
    near = shapely.unary_union([l.buffer(CORRIDOR) for l in lines.values()])
    on_route = shapely.unary_union([l.buffer(1.0) for l in lines.values()])
    pieces = []
    for t in data.get('tracks', []):
        if t.get('src', 'di') in OWN or len(t['p']) < 2:
            continue
        g = LineString(t['p']).intersection(near).difference(on_route)
        if g.length > 0.5:
            pieces.append((t['src'], g))
    groups = []
    for src, g in pieces:
        hit = next((grp for grp in groups if grp[0] == src and any(g.distance(h) <= GROUP for h in grp[1])), None)
        if hit:
            hit[1].append(g)
        else:
            groups.append((src, [g]))
    for src, gs in groups:
        length = sum(g.length for g in gs)
        if length > FILL:
            longest = max(gs, key=lambda g: g.length)
            c = longest.interpolate(0.5, normalized=True)
            out.append({'kind': 'track fill', 'src_track': src, 'where': 'drawn track', 'length_m': round(length, 1),
                        'x': round(c.x, 1), 'y': round(c.y, 1)})
    return out


OPTIONS = ['matches reality', 'unsure']
INFO = {
    'track fill': 'This track is drawn from {src} here: DI (the current DTM, 2026-09-30) has no track within 2 m of it '
                  'over {length} m. Does the track run like this in the imagery? If not, say how in a note: the build '
                  'does not move tracks from answers yet.',
}
CONFIRM = 3.0   # m: a recorded answer covers the finding of its kind this near


def review_items(found, line, confirmed=()):
    """The findings as a ?review file's items, without those the user confirmed (kind and place)."""
    items = []
    for f in found:
        if any(c['kind'] == f['kind'] and math.dist((c['x'], c['y']), (f['x'], f['y'])) <= CONFIRM for c in confirmed):
            continue
        src = {'osm': 'OpenStreetMap', 'dtmp': 'the archived technical map (DTMP, 2008-2024 records)'}.get(f.get('src_track'))
        items.append({'kind': f['kind'], 'id': f"{f['kind']}|{f['x']:.1f},{f['y']:.1f}", 'line': line,
                      'x': f['x'], 'y': f['y'], 's': f.get('s'), 'mag': f.get('length_m', 5), 'status': 'review',
                      'info': INFO[f['kind']].format(src=src, length=f.get('length_m')), 'lat': f.get('lat'), 'lon': f.get('lon')})
    return items


def confirmed_answers(root=ROOT):
    path = root / 'data/truth.json'
    truth = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    return truth.get('trackSources', {}).get('reviewAnswers', [])


def main():
    line = sys.argv[sys.argv.index('--line') + 1] if '--line' in sys.argv else '17'
    data = json.loads((ROOT / f'data/line{line}.json').read_text(encoding='utf-8'))
    found = findings(data)
    from geo import Frame
    frame = Frame()
    for f in found:
        lat, lon = frame.ll(f['x'], f['y'])
        f['lat'], f['lon'] = round(float(lat), 6), round(float(lon), 6)
    by = Counter(f['kind'] for f in found)
    print(f'line {line}: {dict(by)}')
    for f in sorted(found, key=lambda f: (f['kind'], -f.get('length_m', 0))):
        print(f"  {f['kind']}: {f.get('src_track', '')} {f.get('where', '')} {f.get('length_m', '')} m, s {f.get('s')}, "
              f"{f['lat']:.5f} N {f['lon']:.5f} E")
    if '--from-reviews' in sys.argv:
        answers = json.loads(Path(sys.argv[sys.argv.index('--from-reviews') + 1]).read_text(encoding='utf-8'))['items']
        for key, a in answers.items():
            if a.get('kind') in INFO and a.get('v') == OPTIONS[0] and not a.get('note'):
                print(json.dumps({'kind': a['kind'], 'x': a['x'], 'y': a['y'], 'line': int(line), 'answer': a['v'],
                                  'quote': '', 'source': 'review page answer', 'date': ''}, ensure_ascii=False))
    if '--write' in sys.argv:
        out = ROOT / f'reports/review/track-sources-{line}.json'
        items = review_items(found, line, confirmed_answers())
        if not items:   # (nothing to ask: no set)
            out.unlink(missing_ok=True)
            print(f'line {line}: no findings')
            return
        with open(out, 'w', encoding='utf-8', newline='') as f:
            json.dump({'schema': 1, 'issue': 237, 'line': line, 'options': OPTIONS, 'findings': items}, f,
                      ensure_ascii=False, indent=1)
        print(f'wrote {out}: {len(items)} findings')


if __name__ == '__main__':
    main()
