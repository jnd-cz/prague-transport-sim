# SPDX-License-Identifier: AGPL-3.0-or-later
"""IPR Mosty 3D (3D bridges) for the whole city: the layer's every mesh node, for the track-height import (#192).

Usage:  python -I tools/mosty3d.py fetch      # downloads into raw/geoportal/mosty3d/ (then snapshot publish)
        python -P -E tools/mosty3d.py stats   # features, triangles, footprint area

The I3S geometry layout is the one tools/geoportal.py reads (non-Draco buffer). `load()` gives per feature its
triangles in the city frame (tools/geo.py) and its footprint; `Bridges.top(x, y)` the model's highest surface there.
"""
import gzip
import json
import math
import os
import struct
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -I / -P leave it out)
from atomic import replacing  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'raw', 'geoportal', 'mosty3d')
SERVICE = 'https://services5.arcgis.com/SBTXIEUGWbqzUecw/arcgis/rest/services/Mosty_3D_WSL1/SceneServer/layers/0'
R_EARTH = 6378137.0


def get(url):
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'tram-game-prototype/0.1'})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            return gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data
        except OSError as e:
            print('  retry', attempt, e)
            time.sleep(3 * (attempt + 1))
    raise SystemExit('download failed: ' + url)


def fetch():
    os.makedirs(RAW, exist_ok=True)
    layer = get(SERVICE + '?f=json')
    with replacing(os.path.join(RAW, 'layer.json'), 'wb') as f:
        f.write(layer)
    nodes, page = [], 0
    while True:
        data = json.loads(get(f'{SERVICE}/nodepages/{page}?f=json'))
        if 'nodes' not in data:
            break
        with replacing(os.path.join(RAW, f'np{page}.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f)
        nodes += data['nodes']
        if len(data['nodes']) < json.loads(layer)['nodePages']['nodesPerPage']:
            break
        page += 1
    meshes = [n for n in nodes if n.get('mesh') and not n.get('children')]
    for k, n in enumerate(meshes):
        res = n['mesh']['geometry']['resource']
        with replacing(os.path.join(RAW, f'g{res}.bin'), 'wb') as f:
            f.write(get(f'{SERVICE}/nodes/{res}/geometries/0'))
        print(f'  {k + 1}/{len(meshes)} g{res}.bin')
    print(f'{len(nodes)} nodes, {len(meshes)} leaf meshes in {RAW}')


def merc_to_latlon(mx, my):
    return math.degrees(2 * math.atan(math.exp(my / R_EARTH)) - math.pi / 2), math.degrees(mx / R_EARTH)


def load(raw=RAW):
    """{feature id: list of triangles ((x, y, z) * 3) in the city frame}. A feature split over several nodes
    keeps its first node's copy (the nodes hold the same feature at one level of detail)."""
    import numpy as np
    from geo import Frame
    frame = Frame()
    nodes, page = [], 0
    while os.path.exists(os.path.join(raw, f'np{page}.json')):
        with open(os.path.join(raw, f'np{page}.json'), encoding='utf-8') as f:
            nodes += json.load(f)['nodes']
        page += 1
    out = {}
    for n in nodes:
        if not n.get('mesh') or n.get('children'):
            continue
        with open(os.path.join(raw, f"g{n['mesh']['geometry']['resource']}.bin"), 'rb') as f:
            data = f.read()
        vc, fc = struct.unpack_from('<II', data, 0)
        off = 8
        pos = np.frombuffer(data, '<f4', vc * 3, off).reshape(-1, 3).astype(float); off += vc * 12
        off += vc * 12 + vc * 8 + vc * 4            # normals, uv0, colour
        fids = struct.unpack_from(f'<{fc}Q', data, off); off += fc * 8
        ranges = struct.unpack_from(f'<{fc * 2}I', data, off)
        cx, cy, cz = n['obb']['center']
        my = cy + pos[:, 1]
        lat = np.degrees(2 * np.arctan(np.exp(my / R_EARTH)) - math.pi / 2)
        lon = np.degrees((cx + pos[:, 0]) / R_EARTH)
        x, y = frame.xy(lat, lon)
        xyz = np.column_stack([x, y, cz + pos[:, 2]])
        for i, fid in enumerate(fids):
            if fid in out:
                continue
            t0, t1 = ranges[2 * i], ranges[2 * i + 1]
            out[fid] = xyz[t0 * 3:(t1 + 1) * 3].reshape(-1, 3, 3)
    return out


class Bridges:
    """Footprints and top surface of every Mosty 3D feature; `top(x, y)` is the highest model surface over a
    point (the model is blocks from the highest surface seen from the air down: deck or parapet)."""

    def __init__(self, raw=RAW):
        import numpy as np
        import shapely
        from shapely.ops import unary_union
        self.np, self.shapely = np, shapely
        feats = load(raw) if os.path.exists(os.path.join(raw, 'np0.json')) else {}
        self.ids, self.footprints, tris, owner = [], [], [], []
        for fid, t in feats.items():
            polys = shapely.polygons(t[:, :, :2])
            ok = shapely.area(polys) > 1e-3
            if not ok.any():
                continue
            self.ids.append(int(fid))
            self.footprints.append(unary_union(polys[ok]).buffer(0.05).buffer(-0.05))
            tris.append(t[ok])
            owner += [len(self.ids) - 1] * int(ok.sum())
        self.tris = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
        self.owner = np.array(owner, int)
        self.tree = shapely.STRtree(shapely.polygons(self.tris[:, :, :2]) if len(self.tris) else [])
        self.foot_tree = shapely.STRtree(self.footprints)

    def top_of(self, x, y, k):
        """The highest surface of feature k over (x, y), or None."""
        return self.top(x, y, k)[0]

    def top(self, x, y, k=None):
        """(z, feature index) of the highest triangle over (x, y) (of feature k only, when given), or (None, None)."""
        hits = self.tree.query(self.shapely.Point(x, y), predicate='intersects')
        if k is not None:
            hits = [h for h in hits if self.owner[h] == k]
        if not len(hits):
            return None, None
        best, who = None, None
        for h in hits:
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = self.tris[h]
            d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(d) < 1e-9:
                z = max(z0, z1, z2)
            else:
                a = ((y1 - y2) * (x - x2) + (x2 - x1) * (y - y2)) / d
                b = ((y2 - y0) * (x - x2) + (x0 - x2) * (y - y2)) / d
                z = a * z0 + b * z1 + (1 - a - b) * z2
            if best is None or z > best:
                best, who = float(z), int(self.owner[h])
        return best, who


def stats():
    b = Bridges()
    area = sum(f.area for f in b.footprints)
    print(f'{len(b.ids)} features, {len(b.tris)} triangles, footprints {area / 1e4:.1f} ha')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'fetch':
        fetch()
    elif cmd == 'stats':
        stats()
    else:
        print(__doc__)
