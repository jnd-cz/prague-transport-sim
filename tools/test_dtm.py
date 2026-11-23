# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/dtm.py's build on a small survey package (#703): python -P -E tools/test_dtm.py

A district's two packages (the areas, OPL; the 3D lines, KR) written as GeoPackages in a temporary root with a line along
them; the build run in this process with the sources it reads from raw/ stood in for (IPR's terrain flat at 200 m, no
OSM extract, no surveyed tracks, no bridge models), as a checkout without them builds."""
import array
import base64
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dtm  # noqa: E402
from geo import ORIGIN  # noqa: E402
import mosty3d  # noqa: E402
# (the modules build() imports, imported before a test takes the output: one of them reconfigures sys.stdout)
import dmr5g, kerbs, zps_decks, zps_ground, zps_inside, zps_medians, zps_outline, zps_shelters  # noqa: E402,F401,E401

DISTRICT, DATE = "500089", "20260930"
ROAD = "Dopravni#010000000503_Test"
ROAD_LINES = "Hranice_dopravní_stavby_nebo_plochy#010000000503_Test"


class FlatIpr:
    """IPR's 1 m terrain as a level ground at 200 m (the real one is a 2 GB raster)."""
    def sample(self, E, N):
        return np.full(np.shape(E), 200.0)


def square(x0, size=5.0):
    e, n = ORIGIN
    return [(e + x0 + x, n + y) for x, y in [(0, 0), (size, 0), (size, size), (0, size), (0, 0)]]


def gpkg(path, layers):
    """A GeoPackage with `layers`: {name: (geometry type, [(points, z or None), ...])}, polygons (one ring) or lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""create table gpkg_contents(table_name text,data_type text);
            create table gpkg_geometry_columns(table_name text,column_name text,geometry_type_name text,z integer);""")
        for name, (kind, feats) in layers.items():
            db.execute("insert into gpkg_contents values(?,?)", (name, "features"))
            db.execute("insert into gpkg_geometry_columns values(?,?,?,?)", (name, "shape", kind, int(kind == "LINESTRING")))
            db.execute(f'create table "{name}" (id integer, shape blob, UrovenUmisteniObjektuZPS integer)')
            for i, (pts, z) in enumerate(feats):
                if kind == "POLYGON":
                    wkb = struct.pack("<BIII", 1, 3, 1, len(pts)) + b"".join(struct.pack("<dd", *p) for p in pts)
                else:
                    wkb = struct.pack("<BII", 1, 1002, len(pts)) + b"".join(struct.pack("<ddd", *p, z) for p in pts)
                db.execute(f'insert into "{name}" values(?,?,0)', (i, b"GP\x00\x01" + struct.pack("<i", 5514) + wkb))
        db.commit()


class Build(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "data").mkdir()
        line = {"path": [[0, 0], [20, 0]], "terrain": {"data": base64.b64encode(array.array("h", [0] * 4)).decode(),
                "base": 200, "scale": 1, "x0": -10, "y0": -10, "dx": 40, "dy": 40, "nx": 2, "ny": 2}}
        (self.root / "data/line17.json").write_text(json.dumps(line), encoding="utf-8")
        snaps = self.root / "snapshots"
        snaps.mkdir()
        (snaps / "CURRENT").write_text("test\n", encoding="utf-8")
        files = [{"path": f"raw/dtm/VS_CZ010_MOMC_{DISTRICT}_{DATE}_ZPS_{k}.gpkg.zip"} for k in ("OPL", "KR")]
        (snaps / "test.json").write_text(json.dumps({"groups": [{"name": "dtm", "files": files}]}), encoding="utf-8")
        # (the sources a checkout may lack: the build says so and goes on, as it does there)
        bridges = mosty3d.Bridges
        for p in (patch("ipr_dtm.IprDtm", FlatIpr), patch.dict(sys.modules, {"osm_local": None, "dtmp_tracks": None}),
                  patch.object(mosty3d, "Bridges", lambda: bridges(raw=str(self.root / "raw/geoportal/mosty3d")))):
            p.start()
            self.addCleanup(p.stop)

    def package(self, areas, lines):
        folder = self.root / "raw/dtm"
        for kind, layers in (("OPL", areas), ("KR", lines)):
            gpkg(folder / f"VS_CZ010_MOMC_{DISTRICT}_{DATE}_ZPS_{kind}.gpkg" / f"ZPS_{kind}.gpkg", layers)
        return [str(p) for p in folder.iterdir()]

    def build(self, sources):
        log = io.StringIO()
        with redirect_stdout(log):
            out = dtm.build("17", sources, root=str(self.root))
        return out, log.getvalue()

    def test_a_road_takes_its_lines_heights_and_is_counted(self):
        src = self.package({ROAD: ("POLYGON", [(square(0), None)])}, {ROAD_LINES: ("LINESTRING", [(square(0), 200.4)])})
        out, log = self.build(src)
        self.assertEqual([(a["c"], a["l"]) for a in out["areas"]], [("road", 0)])
        self.assertEqual({q[2] for q in out["areas"][0]["r"]}, {200.4})
        self.assertEqual(out["provenance"]["lists"]["areas"]["checks"]["classes"], {"road": {"areas": 1, "m2": 25.0}})
        written = json.loads((self.root / "data/line17.dtm.json").read_text(encoding="utf-8"))
        self.assertEqual(written["areas"], out["areas"])
        self.assertIn(f"district: {DISTRICT}, month {DATE}", log)

    def test_a_layer_it_does_not_know_stops_the_build_and_names_it(self):
        src = self.package({ROAD: ("POLYGON", [(square(0), None)]), "Neznama#019999999903_Test": ("POLYGON", [(square(10), None)])},
                           {ROAD_LINES: ("LINESTRING", [(square(0), 200.4)])})
        with self.assertRaises(SystemExit) as e, redirect_stdout(io.StringIO()):
            dtm.build("17", src, root=str(self.root))
        self.assertIn(DISTRICT, str(e.exception.code))
        self.assertIn("019999999903", str(e.exception.code))
        self.assertFalse((self.root / "data/line17.dtm.json").exists())

    def test_a_layer_left_out_on_purpose_is_skipped(self):
        # (Budova: buildings come from IPR's LOD2, tools/zps_layers.py LEFT_OUT)
        src = self.package({ROAD: ("POLYGON", [(square(0), None)]), "Budova#010000000103_Test": ("POLYGON", [(square(10), None)])},
                           {ROAD_LINES: ("LINESTRING", [(square(0), 200.4)])})
        out, _ = self.build(src)
        self.assertEqual([a["c"] for a in out["areas"]], ["road"])

    def test_an_area_without_surveyed_heights_is_dropped(self):
        # (its lines 3 m off: no outline point within 2.5 m of one; a flat sheet at a guessed level would be worse)
        src = self.package({ROAD: ("POLYGON", [(square(0), None)])}, {ROAD_LINES: ("LINESTRING", [(square(8), 200.4)])})
        out, log = self.build(src)
        self.assertEqual(out["areas"], [])
        self.assertIn("dropped 1 areas", log)

    def test_importing_it_builds_nothing(self):
        # (#703: its work in build() and main(); the rebuild runs it as a script)
        self.assertTrue(callable(dtm.build) and callable(dtm.main))
        self.assertFalse(os.path.exists(self.root / "data/line17.dtm.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
