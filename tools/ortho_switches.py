"""Where DI's forks lie on the real switch (#210): IPR's leaf-off orthophoto around a junction with DI's track axes and
forks, OSM's switch nodes and the ZPS survey's traffic-area lines (kerbs, markings: the orthophoto's registration).

    python -P -E tools/ortho_switches.py --place staromestska            # one of PLACES
    python -P -E tools/ortho_switches.py --at -385,200,40 --name mine     # x,y,half-size in city metres
    python -P -E tools/ortho_switches.py --place dvorce --sources         # + OSM tram ways, the archive, a GeoJSON

Writes reports/ortho_switches/<name>.png (north up, RES m per pixel, a 1 m grid) and <name>.json (the forks in view:
index, position, the directions their branches leave in), and a close view of each fork (<name>-fork<i>). Orthophoto: flight 7-8 April 2026, 7 cm/px, CC BY 4.0
(IPR Praha, ImageServer ort/mimovegetacni_letecke_snimkovani); the images are cached in reports/ortho_switches/cache.
"""
import argparse
import glob
import json
import math
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image, ImageDraw, ImageFont, ImageOps
from shapely.geometry import box

import di_tracks as dt
import gpkg
from dtmp_tracks import di_data
from geo import Frame

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'reports' / 'ortho_switches'
SERVICE = 'https://gs-pub.praha.eu/imgs/rest/services/ort/mimovegetacni_letecke_snimkovani/ImageServer/exportImage'
RES = 0.035   # m per pixel (the flight's 7 cm, drawn at twice that)
# junctions the user proposed (session 2026-11-03), city metres: centre and half-size
PLACES = {'staromestska': (-390, 200, 40), 'palackeho': (-738, -1506, 40), 'strossmayerovo': (1015, 1145, 45),
          'jiraskovo': (-650, -1055, 30), 'malostranska': (-745, 495, 45),
          # Dvorecký most's ends (#209): no DI there yet; the flight of April 2026 shows the new tracks
          'dvorce': (-965, -4042, 45), 'dvorce-smichov': (-1390, -3985, 50)}
ZPS_LINES = ('Hranice_dopravní_stavby_nebo_plochy', 'Vnitřní_členění_dopravní_plochy')
CLOSE = 7.0   # m either side of a fork in its close view


def ortho(x0, y0, x1, y1, res=RES):
    """The orthophoto over a city-metre box, cached."""
    F = Frame()
    w, h = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
    OUT.joinpath('cache').mkdir(parents=True, exist_ok=True)
    f = OUT / 'cache' / f'{x0:.1f}_{y0:.1f}_{x1:.1f}_{y1:.1f}_{res}.png'
    if not f.exists():
        url = (f'{SERVICE}?bbox={x0 + F.E0},{y0 + F.N0},{x1 + F.E0},{y1 + F.N0}&bboxSR=5514&imageSR=5514'
               f'&size={w},{h}&format=png&f=image')
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'tram-game-prototype/0.1'}),
                                    timeout=120) as r:
            f.write_bytes(r.read())
    return Image.open(f).convert('RGB')


def zps_lines(area):
    """ZPS traffic-area lines (city metres) crossing a shapely area, from every district's KR package."""
    F = Frame()
    out = []
    for kr in sorted(glob.glob(str(ROOT / 'raw' / 'dtm' / '*_ZPS_KR.gpkg' / 'ZPS_KR.gpkg'))):
        for t in gpkg.layers(kr):
            if not t.endswith(ZPS_LINES):
                continue
            for feat in gpkg.features(kr, t):
                g = feat['geom']
                if not g:
                    continue
                for pts in ([g[1]] if g[0] == 'LineString' else [p[1] for p in g[1]]):
                    xs, ys = F.from_jtsk([p[0] for p in pts], [p[1] for p in pts])
                    line = list(zip(map(float, xs), map(float, ys)))
                    if any(area.contains(box(x - 0.01, y - 0.01, x + 0.01, y + 0.01)) for x, y in line):
                        out.append(line)
    return out


def osm_switches(area):
    """OSM railway=switch nodes in an area (the local extract)."""
    import osmium
    F = Frame()
    lat0, lon0 = F.ll(area.bounds[0], area.bounds[1])
    lat1, lon1 = F.ll(area.bounds[2], area.bounds[3])
    found = []

    class H(osmium.SimpleHandler):
        def node(self, n):
            if n.tags.get('railway') == 'switch' and float(lat0) <= n.location.lat <= float(lat1) \
                    and float(lon0) <= n.location.lon <= float(lon1):
                x, y = F.xy(n.location.lat, n.location.lon)
                found.append({'id': n.id, 'xy': (float(x), float(y)), 'ref': n.tags.get('ref')})
    H().apply_file(str(ROOT / 'raw' / 'osm' / 'praha.osm.pbf'))
    return found


def drawn_tracks(path):
    """A line file's drawn tracks and both routes, resampled every 0.5 m, each point with the radius over 5 m."""
    from track_curve import radii
    d = json.load(open(path, encoding='utf-8'))
    out = []
    for p in [t['p'] for t in d['tracks']] + [d['path'], d.get('pathBack') or []]:
        c = [0.0]
        for a, b in zip(p, p[1:]):
            c.append(c[-1] + math.dist(a, b))
        if len(p) < 2 or c[-1] < 1:
            continue
        n, j, pts = max(2, int(c[-1] / 0.5)), 0, []
        for i in range(n + 1):
            s = c[-1] * i / n
            while j < len(p) - 2 and c[j + 1] < s:
                j += 1
            t = (s - c[j]) / ((c[j + 1] - c[j]) or 1e-9)
            pts.append((p[j][0] + (p[j + 1][0] - p[j][0]) * t, p[j][1] + (p[j + 1][1] - p[j][1]) * t))
        r = radii([q[0] for q in pts], [q[1] for q in pts], 2.5)
        out.append(list(zip(pts, r)))
    return out


def osm_ways(area):
    """OSM railway=tram ways near an area (the local extract), city metres."""
    import osmium
    F = Frame()
    lat0, lon0 = F.ll(area.bounds[0] - 20, area.bounds[1] - 20)
    lat1, lon1 = F.ll(area.bounds[2] + 20, area.bounds[3] + 20)
    found = []

    class H(osmium.SimpleHandler):
        def way(self, w):
            if w.tags.get('railway') != 'tram':
                return
            try:
                pts = [(n.lat, n.lon) for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            if any(float(lat0) <= a <= float(lat1) and float(lon0) <= b <= float(lon1) for a, b in pts):
                x, y = F.xy([p[0] for p in pts], [p[1] for p in pts])
                found.append(list(zip(map(float, x), map(float, y))))
    H().apply_file(str(ROOT / 'raw' / 'osm' / 'praha.osm.pbf'), locations=True)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--place', choices=sorted(PLACES))
    ap.add_argument('--at', help='x,y[,half] in city metres')
    ap.add_argument('--fork', type=int, help='centre on this DI fork (index printed in the place view)')
    ap.add_argument('--half', type=float, help='half-size in metres')
    ap.add_argument('--name')
    ap.add_argument('--sources', action='store_true', help='also OSM tram ways (green), the archive (orange)')
    ap.add_argument('--geojson', help='lines to draw in purple (city metres), e.g. DI planned works')
    ap.add_argument('--data', help="a line file whose drawn tracks and routes to draw: white, red under 20 m over 5 m")
    a = ap.parse_args()
    di = dt.Source('di', di_data()[1])
    if a.fork is not None:
        cx, cy = di.forks[a.fork]
        half = a.half or 8
    elif a.at:
        v = [float(t) for t in a.at.split(',')]
        cx, cy, half = v[0], v[1], v[2] if len(v) > 2 else (a.half or 40)
    else:
        cx, cy, half = PLACES[a.place or 'staromestska']
        half = a.half or half
    name = a.name or (f'{a.place}-fork{a.fork}' if a.fork is not None else a.place) or f'{cx:.0f}_{cy:.0f}'
    area = box(cx - half, cy - half, cx + half, cy + half)
    zps, osm = zps_lines(area.buffer(2)), osm_switches(area)
    extra = []
    if a.sources:
        from dtmp_tracks import archive_data
        extra.append(((255, 150, 30, 200), [[tuple(c[:2]) for c in p['coords']] for p in archive_data()[2]]))
        extra.append(((40, 200, 80, 200), osm_ways(area)))
    if a.geojson:
        g = json.load(open(a.geojson, encoding='utf-8'))
        extra.append(((200, 40, 200, 220), [f['geometry']['coordinates'] for f in g['features']]))
    if a.data:
        extra.append(('drawn', drawn_tracks(a.data)))
    forks = draw(name, cx, cy, half, di, zps, osm, extra)
    # a close view of every fork in the place (CLOSE m either side), and of every OSM switch DI has no fork near
    for f in forks:
        draw(f"{name}-fork{f['fork']}", *f['xy'], CLOSE, di, zps, osm, extra)
    for s in osm:
        if all(math.dist(s['xy'], f['xy']) > CLOSE for f in forks):
            draw(f"{name}-osm{s['id']}", *s['xy'], CLOSE, di, zps, osm, extra)
    print(f"wrote {OUT / name}.png and {len(forks)} close views: DI forks {[f['fork'] for f in forks]}, {len(osm)} OSM switches")


def draw(name, cx, cy, half, di, zps, osm, extra=()):
    """One picture: the orthophoto over the box with the overlays; returns the DI forks in view."""
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    area = box(x0, y0, x1, y1)
    raw = ImageOps.autocontrast(ortho(x0, y0, x1, y1), cutoff=1)
    img = raw.copy()
    W, H = img.size
    d = ImageDraw.Draw(img, 'RGBA')
    px = lambda p: ((p[0] - x0) / (x1 - x0) * W, (y1 - p[1]) / (y1 - y0) * H)
    lw = 1 if half <= CLOSE else 2
    for gx in range(math.ceil(x0), math.floor(x1) + 1):   # a 1 m grid, every 5 m stronger
        d.line([px((gx, y0)), px((gx, y1))], fill=(255, 255, 255, 60 if gx % 5 else 120), width=1)
    for gy in range(math.ceil(y0), math.floor(y1) + 1):
        d.line([px((x0, gy)), px((x1, gy))], fill=(255, 255, 255, 60 if gy % 5 else 120), width=1)
    for line in zps:
        d.line([px(p) for p in line], fill=(255, 220, 0, 230), width=lw)
    for colour, lines in extra:
        for line in lines:
            if colour == 'drawn':   # (points with their radius)
                for (p, r), (q, _) in zip(line, line[1:]):
                    if x0 - 5 <= p[0] <= x1 + 5 and y0 - 5 <= p[1] <= y1 + 5:
                        d.line([px(p), px(q)], fill=(255, 40, 40, 255) if r < 20 else (255, 255, 255, 170), width=lw + 1)
            elif len(line) > 1 and any(x0 - 5 <= x <= x1 + 5 and y0 - 5 <= y <= y1 + 5 for x, y in line):
                d.line([px(p) for p in line], fill=colour, width=lw)
    for ch in di.chains:
        if ch['line'].intersects(area):
            d.line([px(p) for p in ch['line'].coords], fill=(40, 120, 255, 150), width=lw)
    try:
        font = ImageFont.truetype('arial.ttf', max(14, int(0.5 / RES)))
    except OSError:
        font = ImageFont.load_default()
    forks = []
    for i, (f, br) in enumerate(zip(di.forks, di.branches)):
        if x0 <= f[0] <= x1 and y0 <= f[1] <= y1:
            r = 0.3 / RES
            q = px(f)
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], outline=(255, 40, 40, 255), width=lw)
            d.text((q[0] + r + 2, q[1] - r), str(i), fill=(255, 40, 40, 255), font=font)
            forks.append({'fork': i, 'xy': [round(f[0], 2), round(f[1], 2)], 'branches': [[round(v, 3) for v in b] for b in br]})
    for s in osm:
        q, r = px(s['xy']), 0.25 / RES
        d.rectangle([q[0] - r, q[1] - r, q[0] + r, q[1] + r], outline=(40, 220, 80, 255), width=lw)
    d.rectangle([8, 8, 8 + int(5 / RES), 14], fill=(255, 255, 255, 220))
    d.text((10, 16), f'5 m · {name} · DI axes blue, DI forks red, OSM switches green squares, ZPS lines yellow'
           + (' · OSM tram green, archive orange, planned purple, drawn track white (red under 20 m)' if extra else ''), fill=(255, 255, 255, 255), font=font)
    OUT.mkdir(parents=True, exist_ok=True)
    if half <= CLOSE:   # a close view: the bare photo beside the drawn one, twice the size
        pair = Image.new('RGB', (2 * W + 6, H), 'white')
        pair.paste(raw, (0, 0))
        pair.paste(img, (W + 6, 0))
        img = pair.resize((pair.width * 2, pair.height * 2), Image.LANCZOS)
    img.save(OUT / f'{name}.png')
    json.dump({'centre': [cx, cy], 'half': half, 'res': RES, 'forks': forks,
               'osm': [s for s in osm if x0 <= s['xy'][0] <= x1 and y0 <= s['xy'][1] <= y1]},
              open(OUT / f'{name}.json', 'w', encoding='utf-8'), indent=1)
    return forks


if __name__ == '__main__':
    main()
