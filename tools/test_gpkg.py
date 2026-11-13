# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/gpkg.py: features read only where their boxes reach the cells asked (#517), the rest decoded as before.

    python -P -E tools/test_gpkg.py
"""
import json
import os
import random
import sqlite3
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import shapely  # noqa: E402

import gpkg  # noqa: E402


def blob(geom, env=False):
    """A GPKG geometry blob: the header (srs 5514, an envelope if asked) and the WKB with Z."""
    wkb = shapely.to_wkb(geom, output_dimension=3, flavor="iso")
    if env:
        x0, y0, x1, y1 = geom.bounds
        return b"GP\x00" + bytes([1 | (1 << 1)]) + struct.pack("<i4d", 5514, x0, x1, y0, y1) + wkb
    return b"GP\x00\x01" + struct.pack("<i", 5514) + wkb


def package(path, geoms):
    c = sqlite3.connect(path)
    c.execute("create table gpkg_geometry_columns (table_name, column_name, geometry_type_name, z)")
    c.execute("create table gpkg_contents (table_name, data_type)")
    c.execute("insert into gpkg_geometry_columns values ('t', 'geom', 'LINESTRING', 1)")
    c.execute("insert into gpkg_contents values ('t', 'features')")
    c.execute('create table t (fid integer primary key, ID text, geom blob)')
    c.executemany("insert into t (ID, geom) values (?, ?)", [(f"f{i}", g) for i, g in enumerate(geoms)])
    c.commit()
    c.close()


def in_cells(geom, cells, size, shift):
    """The callers' own test: a vertex in one of the cells."""
    xy = shapely.get_coordinates(geom)
    return any((int((x - shift[0]) // size), int((y - shift[1]) // size)) in cells for x, y in xy)


class Near(unittest.TestCase):
    def test_kept_features_are_those_the_vertices_reach(self):
        """Every feature with a vertex in a cell is kept, in order and decoded as without keep; one GEOS cannot read
        (a line of one point) or an empty one passes to the decoder as before."""
        rng = random.Random(4)
        shift, size = (-742806.0, -1043024.0), 40
        cells = {(rng.randrange(-30, 30), rng.randrange(-30, 30)) for _ in range(150)}
        geoms = []
        for _ in range(1500):
            x, y = shift[0] + rng.uniform(-1300, 1300), shift[1] + rng.uniform(-1300, 1300)
            pts = [(x + rng.uniform(-60, 60) * k, y + rng.uniform(-60, 60) * k, 200 + k) for k in range(rng.randrange(2, 6))]
            geoms.append(shapely.LineString(pts))
        blobs = [blob(g, env=i % 3 == 0) for i, g in enumerate(geoms)]
        # (a line of one point, far from the cells: GEOS refuses it, the decoder reads it; and an empty geometry)
        bad = b"\x01" + struct.pack("<II", 1002, 1) + struct.pack("<3d", shift[0] + 5000, shift[1] + 5000, 1)
        blobs += [b"GP\x00\x01" + struct.pack("<i", 5514) + bad, b"GP\x00" + bytes([0x11]) + struct.pack("<i", 5514)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.gpkg")
            package(p, blobs)
            every = list(gpkg.features(p, "t"))
            kept = list(gpkg.features(p, "t", keep=gpkg.near(cells, size, shift)))
            boxes = list(gpkg.features(p, "t", keep=gpkg.near_boxes(
                [(shift[0] + i * size, shift[1] + j * size, shift[0] + (i + 1) * size - 1e-6, shift[1] + (j + 1) * size - 1e-6)
                 for i, j in cells], size, shift)))
        want = [f for f, g in zip(every, geoms) if in_cells(g, cells, size, shift)]
        self.assertGreater(len(want), 50)
        self.assertLess(len(kept), len(every) * .8)
        ids = [f["ID"] for f in kept]
        self.assertEqual(ids, sorted(ids, key=lambda i: int(i[1:])))  # (in the table's order)
        for f in want:
            self.assertIn(f, kept)
        self.assertEqual({f["ID"] for f in want} - {f["ID"] for f in boxes}, set())
        self.assertIn(every[-2], kept)  # (GEOS could not read it: decoded as before)
        self.assertIn(every[-1], kept)
        self.assertIsNone(every[-1]["geom"])
        self.assertEqual(every[-2]["geom"][0], "LineString")

    def test_no_cells(self):
        self.assertEqual(gpkg.near(set(), 5)(np.zeros((3, 4))).tolist(), [False] * 3)
        self.assertEqual(gpkg.near_boxes([], 5)(np.zeros((2, 4))).tolist(), [False] * 2)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "line17.json")) and
                     os.path.isdir(os.path.join(ROOT, "raw", "dtm")), "needs data/ and raw/dtm: python -I tools/snapshot.py fetch")
class Survey(unittest.TestCase):
    def test_a_lines_survey_read_as_before(self):
        """Line 17's corridor (dtm.py's and zps_source.py's 40 m cells) in one district's 3D lines: the same lines, in
        order, with or without keep."""
        from dtm_packages import DTM, select_packages
        from geo import Frame
        F = Frame()
        line = json.load(open(os.path.join(ROOT, "data", "line17.json"), encoding="utf-8"))
        cells = {(int(p[0] // 40) + dx, int(p[1] // 40) + dy) for p in line["path"] + line.get("pathBack", [])
                 for dx in range(-2, 3) for dy in range(-2, 3)}
        package = select_packages(ROOT, districts=DTM["17"])[0]
        tables = [t for t, i in gpkg.layers(package.kr).items() if i["type"] in ("LINESTRING", "MULTILINESTRING")
                  and "Hranice" in t]
        corridor = lambda f: f["geom"] and any(  # noqa: E731
            (int((x - F.E0) // 40), int((y - F.N0) // 40)) in cells
            for pts in ([f["geom"][1]] if f["geom"][0] == "LineString" else [q[1] for q in f["geom"][1]]) for x, y, *_ in pts)
        keep = gpkg.near(cells, 40, (F.E0, F.N0))
        before = [f for t in tables for f in gpkg.features(package.kr, t) if corridor(f)]
        after = [f for t in tables for f in gpkg.features(package.kr, t, keep=keep) if corridor(f)]
        self.assertGreater(len(before), 100)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
