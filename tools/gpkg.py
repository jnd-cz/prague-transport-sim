# SPDX-License-Identifier: AGPL-3.0-or-later
"""Minimal GeoPackage reader (no GDAL): layers, attributes and geometries decoded from the
GPKG binary header + WKB. Enough for the DTM Praha open data (points, lines, polygons, Z)."""
import sqlite3
import struct


def layers(path):
    c = sqlite3.connect(path)
    out = {}
    for t, in c.execute("select table_name from gpkg_contents where data_type='features'"):
        g = c.execute("select column_name, geometry_type_name, z from gpkg_geometry_columns where table_name=?", (t,)).fetchone()
        out[t] = {"geom": g[0], "type": g[1], "z": g[2]}
    c.close()
    return out


def _wkb(buf, off):
    """Return (geometry, new offset). Geometry: list of coordinate tuples (line/ring), nested lists."""
    bo = "<" if buf[off] == 1 else ">"
    (code,) = struct.unpack_from(bo + "I", buf, off + 1)
    off += 5
    # ISO WKB: 1000s = Z, 2000s = M, 3000s = ZM; EWKB flags in the high bits
    flags_z = bool(code & 0x80000000) or (code // 1000) in (1, 3)
    flags_m = bool(code & 0x40000000) or (code // 1000) in (2, 3)
    base = (code & 0xFFFF) % 1000
    dim = 2 + flags_z + flags_m

    def pts(n, off):
        vals = struct.unpack_from(f"{bo}{n * dim}d", buf, off)
        if not flags_m:  # (the points' tuples zipped from the values: a slice per point was most of a survey's read, #517)
            it = iter(vals)
            return list(zip(it, it, it) if flags_z else zip(it, it)), off + n * dim * 8
        return [tuple(vals[i * dim:i * dim + (3 if flags_z else 2)]) for i in range(n)], off + n * dim * 8

    if base == 1:
        p, off = pts(1, off)
        return ("Point", p[0]), off
    if base == 2:
        (n,) = struct.unpack_from(bo + "I", buf, off)
        p, off = pts(n, off + 4)
        return ("LineString", p), off
    if base == 3:
        (nr,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        rings = []
        for _ in range(nr):
            (n,) = struct.unpack_from(bo + "I", buf, off)
            r, off = pts(n, off + 4)
            rings.append(r)
        return ("Polygon", rings), off
    if base in (4, 5, 6, 7):
        (n,) = struct.unpack_from(bo + "I", buf, off)
        off += 4
        parts = []
        for _ in range(n):
            g, off = _wkb(buf, off)
            parts.append(g)
        return ({4: "MultiPoint", 5: "MultiLineString", 6: "MultiPolygon", 7: "GeometryCollection"}[base], parts), off
    raise ValueError(f"unsupported WKB type {code}")


def geometry(blob):
    """Decode a GPKG geometry blob -> (type, coords) or None."""
    if blob is None or blob[:2] != b"GP":
        return None
    flags = blob[3]
    env = (flags >> 1) & 7
    off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    if flags & 0x10:  # empty geometry
        return None
    g, _ = _wkb(blob, off)
    return g


def features(path, table, where="", params=(), keep=None):
    """Yield dicts of attributes with the decoded geometry under 'geom'. keep(boxes): which features to yield, from an
    (n, 4) array of their boxes (min x, min y, max x, max y) as GEOS reads them; one GEOS cannot read (NaN) is yielded
    (dtm.py and zps_source.py decode only what can reach the line, #517: decoding a district's 300 000 features in
    Python was most of their reading)."""
    c = sqlite3.connect(path)
    gcol = c.execute("select column_name from gpkg_geometry_columns where table_name=?", (table,)).fetchone()[0]
    cols = [r[1] for r in c.execute(f'pragma table_info("{table}")')]
    rows = c.execute(f'select * from "{table}" {where}', params)
    if keep is not None:
        import numpy as np
        import shapely
        rows = rows.fetchall()
        g = cols.index(gcol)
        boxes = shapely.bounds(shapely.from_wkb(np.array([_body(r[g]) for r in rows], dtype=object), on_invalid="ignore"))
        ok = keep(boxes) | ~np.isfinite(boxes).all(axis=1)
        rows = [r for r, k in zip(rows, ok.tolist()) if k]
    for row in rows:
        d = dict(zip(cols, row))
        d["geom"] = geometry(d.pop(gcol))
        yield d
    c.close()


def _body(blob):
    """A GPKG geometry blob's WKB, or None (none, empty)."""
    if blob is None or blob[:2] != b"GP" or blob[3] & 0x10:
        return None
    return blob[8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]:]


def near(cells, size, shift=(0.0, 0.0)):
    """keep() for features: whether a feature's box, widened by a cell, covers a cell of `cells` ((i, j) of a grid of
    `size` m: floor((x - shift) / size))."""
    import numpy as np
    ij = np.array(sorted(cells), dtype=np.int64).reshape(-1, 2)
    if not len(ij):
        return lambda boxes: np.zeros(len(boxes), bool)
    i0, j0 = ij.min(axis=0)
    grid = np.zeros(tuple(ij.max(axis=0) - (i0, j0) + 1), bool)
    grid[ij[:, 0] - i0, ij[:, 1] - j0] = True
    return _keep(grid, i0, j0, size, shift)


def near_boxes(boxes, size, shift=(0.0, 0.0)):
    """keep() for features: whether a feature's box, widened by a cell, covers a cell that one of `boxes` (min x, min y,
    max x, max y), widened by a cell, covers (a grid of `size` m: floor((x - shift) / size))."""
    import numpy as np
    b = np.asarray(boxes, float).reshape(-1, 4)
    if not len(b):
        return lambda boxes: np.zeros(len(boxes), bool)
    a0, a1 = (np.floor_divide(b[:, k] - shift[0], size).astype(np.int64) + d for k, d in ((0, -1), (2, 1)))
    c0, c1 = (np.floor_divide(b[:, k] - shift[1], size).astype(np.int64) + d for k, d in ((1, -1), (3, 1)))
    i0, j0 = a0.min(), c0.min()
    n, m = a1.max() - i0 + 1, c1.max() - j0 + 1
    edge = np.zeros((n + 1, m + 1), np.int64)  # (each box's corners: its cells are counted once the edges are summed)
    np.add.at(edge, (a0 - i0, c0 - j0), 1)
    np.add.at(edge, (a0 - i0, c1 - j0 + 1), -1)
    np.add.at(edge, (a1 - i0 + 1, c0 - j0), -1)
    np.add.at(edge, (a1 - i0 + 1, c1 - j0 + 1), 1)
    return _keep(edge.cumsum(axis=0).cumsum(axis=1)[:n, :m] > 0, i0, j0, size, shift)


def _keep(grid, i0, j0, size, shift):
    """keep(): whether a box, widened by a cell, covers a cell of the grid (whose first is (i0, j0)), summed at once from
    the cells' running counts."""
    import numpy as np
    n, m = grid.shape
    run = np.zeros((n + 1, m + 1), np.int64)
    run[1:, 1:] = grid.cumsum(axis=0).cumsum(axis=1)

    def keep(boxes):
        b = np.nan_to_num(np.asarray(boxes, float).reshape(-1, 4), nan=0.0, posinf=0.0, neginf=0.0)
        ri0 = np.floor_divide(b[:, 0] - shift[0], size) - 1 - i0
        ri1 = np.floor_divide(b[:, 2] - shift[0], size) + 1 - i0
        rj0 = np.floor_divide(b[:, 1] - shift[1], size) - 1 - j0
        rj1 = np.floor_divide(b[:, 3] - shift[1], size) + 1 - j0
        out = (ri1 >= 0) & (ri0 <= n - 1) & (rj1 >= 0) & (rj0 <= m - 1)
        lo_i, hi_i = (np.clip(v, 0, n - 1).astype(np.int64) for v in (ri0, ri1))
        lo_j, hi_j = (np.clip(v, 0, m - 1).astype(np.int64) for v in (rj0, rj1))
        total = run[hi_i + 1, hi_j + 1] - run[lo_i, hi_j + 1] - run[hi_i + 1, lo_j] + run[lo_i, lo_j]
        return out & (total > 0)
    return keep
