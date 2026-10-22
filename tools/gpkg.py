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
        vals = struct.unpack_from(bo + "d" * (n * dim), buf, off)
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


def features(path, table, where="", params=()):
    """Yield dicts of attributes with the decoded geometry under 'geom'."""
    c = sqlite3.connect(path)
    gcol = c.execute("select column_name from gpkg_geometry_columns where table_name=?", (table,)).fetchone()[0]
    cols = [r[1] for r in c.execute(f'pragma table_info("{table}")')]
    for row in c.execute(f'select * from "{table}" {where}', params):
        d = dict(zip(cols, row))
        d["geom"] = geometry(d.pop(gcol))
        yield d
    c.close()
