# SPDX-License-Identifier: AGPL-3.0-or-later
"""The city terrain's mesh on a synthetic raster (#428): python -P -E tools/test_city_terrain.py (needs pydelatin)."""
import faulthandler
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import city_terrain as ct  # noqa: E402

try:
    import pydelatin  # noqa: F401
except ImportError:
    pydelatin = None

H, W = 150, 220
ORIGIN = (1000.0, 2000.0)  # city frame of cell (0, 0): x = 1000 + column, y = 2000 - row
CITY_COLS = 150  # the city: columns 0..149
RIM = 12  # cells: the most a kept triangle reaches past the ground's edge
TOLF = lambda d: ct.tol(d, 0.05, 20.0, 0.6)  # noqa: E731 (grows within the raster: 5 cm up to 20 m, 0.6 m from 240 m)


class Frame:
    E0 = N0 = 0.0  # (S-JTSK is the city frame here)


def terrain(rows, cols):
    """Hills on a slope with a 3 m terrace edge at column 120."""
    r, c = np.asarray(rows, np.float64), np.asarray(cols, np.float64)
    return (250 + 6 * np.sin(c / 19) * np.cos(r / 13) + 0.05 * c + 3 * (c >= 120)).astype(np.float32)


class Dem:
    """DMR 5G stand-in: the terrain 2 cm higher, everywhere."""

    def __init__(self):
        self.asked = 0

    def have(self, ix, iy):
        return True

    def sample(self, E, N):
        self.asked += len(E)
        return terrain(ORIGIN[1] - N, E - ORIGIN[0]) + 0.02


class NoGrids:
    def sample(self, E, N):
        return np.full(E.shape, np.nan, np.float32)


def raw():
    """IPR's file over the box: a strip of 0.00 m along the bottom, declared no-data top right (outside the city) and in a
    hole inside it, one cell under the floor inside, a cell of 169.99 m outside."""
    a = terrain(*np.mgrid[0:H, 0:W])
    a[-6:, :] = 0.0
    a[:40, 170:] = -3.4028235e38
    a[60:80, 30:60] = -3.4028235e38
    a[100, 100] = 120.0
    a[100, 200] = 169.99
    return a


def cells():
    Z, lev = ct.classify(raw())
    lev[:, :CITY_COLS] |= ct.INSIDE
    return Z, lev


def tracks():
    """One track along row 75, from column 0 to 160 (city frame segments)."""
    x = ORIGIN[0] + np.arange(0, 161, 20, dtype=float)
    y = np.full(len(x), ORIGIN[1] - 75)
    return np.column_stack([x[:-1], y[:-1], x[1:], y[1:]])


def covered(V, T, Z):
    """Independent of the tool: per cell the most any triangle covering it is off Z (m; NaN where none covers it or Z
    has no ground) and how many triangles cover it."""
    shape = Z.shape
    err = np.full(shape, np.nan)
    n = np.zeros(shape, int)
    z = Z.astype(np.float64)
    for t in T:
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = V[t].astype(np.float64)
        x0, x1 = int(min(ax, bx, cx)), int(max(ax, bx, cx))
        y0, y1 = int(min(ay, by, cy)), int(max(ay, by, cy))
        gy, gx = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-9) & (l2 >= -1e-9) & (l3 >= -1e-9)
        m = (l1 * az + l2 * bz + l3 * cz) / 100
        e = np.abs(m - z[gy, gx])
        cur = err[gy[inside], gx[inside]]
        err[gy[inside], gx[inside]] = np.fmax(cur, e[inside])
        n[gy[inside], gx[inside]] += 1
    return err, n


@unittest.skipIf(pydelatin is None, "needs pydelatin (python -m pip install --user pydelatin==0.4.0)")
class Mesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(300, exit=True)
        cls.Z, cls.lev = cells()
        cls.dem = Dem()
        cls.fb = ct.fallbacks(cls.Z, cls.lev, ORIGIN, Frame(), cls.dem, NoGrids())
        cls.dl = ct.distances(tracks(), (H, W), ORIGIN, lat=ct.LAT, threads=2)
        cls.V, cls.T, cls.rep = ct.build(cls.Z, cls.lev, cls.dl, (H, W), None, log=lambda s: None, threads=2, tolf=TOLF)
        cls.err, cls.n = covered(cls.V, cls.T, cls.Z)
        cls.ground = (cls.lev & ct.LEVEL) != ct.NO
        j, i = np.mgrid[0:H, 0:W]
        cls.tol = TOLF(ct.at_lattice(cls.dl, j, i))

    @classmethod
    def tearDownClass(cls):
        faulthandler.cancel_dump_traceback_later()

    def test_every_ground_cell_is_covered_and_within_its_tolerance(self):
        g = self.ground
        self.assertTrue((self.n[g] >= 1).all(), "a ground cell no triangle covers")
        over = self.err[g] > self.tol[g] + 1e-6  # (the vertices' cm as stored)
        self.assertEqual(int(over.sum()), 0)
        self.assertEqual(sum(b["cells"] for b in self.rep["bands"].values()), int(g.sum()))
        self.assertTrue(all(b["max_cm"] <= 100 * TOLF(1e9) for b in self.rep["bands"].values()))

    def test_the_tolerance_grows_away_from_the_track(self):
        bands = self.rep["bands"]  # (the raster reaches 96 m from the track: tol 5 cm up to 20 m, 24 cm at 96 m)
        self.assertGreater(bands["0-10"]["cells"], 0)
        self.assertLessEqual(bands["0-10"]["max_cm"], 5.0)
        self.assertGreater(bands["10-120"]["max_cm"], 5.0)
        self.assertGreater(bands["0-10"]["triangles"] / bands["0-10"]["cells"], bands["10-120"]["triangles"] / bands["10-120"]["cells"])

    def test_no_ground_makes_no_triangles(self):
        # outside the city: the 0.00 m strip, the declared no-data and the cell under the floor stay no ground
        self.assertEqual(int(self.ground[-6:, CITY_COLS:].sum()), 0)
        self.assertEqual(int(self.ground[:40, 170:].sum()), 0)
        self.assertFalse(self.ground[100, 200])
        # every triangle covers a ground cell, and none reaches far into no ground: a rim along the ground's edge
        T = self.T.astype(np.int64)
        k, px, py, _, _ = ct.rasterise(self.V[:, :2].astype(np.int64), self.V[:, 2].astype(np.int64), T, np.arange(len(T)), (H, W))
        self.assertTrue((np.bincount(k[self.ground[py, px]], minlength=len(T)) > 0).all())
        self.assertGreater(self.rep["dropped"], 0)
        steps = ct.ground_steps(self.ground, 40)
        self.assertLessEqual(int(steps[(self.n > 0) & ~self.ground].max()), RIM)
        self.assertEqual(int((self.n[:40 - RIM - 1, 170 + RIM + 1:] > 0).sum()), 0)  # (the no-data block's inside)

    def test_a_fallback_fills_gaps_inside_the_city_only(self):
        lv = self.lev & ct.LEVEL
        self.assertTrue((lv[60:80, 30:60] == 1).all())  # the hole inside the city: DMR 5G
        self.assertTrue((lv[-6:, :CITY_COLS] == 1).all())  # the 0.00 m strip inside the city
        self.assertEqual(lv[100, 100], 1)  # under the floor inside
        self.assertTrue((lv[-6:, CITY_COLS:] == ct.NO).all())
        self.assertTrue((lv[:40, 170:] == ct.NO).all())
        self.assertEqual(self.fb["dmr5g"], 20 * 30 + 6 * CITY_COLS + 1)
        np.testing.assert_allclose(self.Z[70, 40], terrain(70, 40) + 0.02, atol=1e-4)
        self.assertTrue((self.n[60:80, 30:60] > 0).all())  # (meshed)

    def test_the_kept_triangles_tile_the_ground_once(self):
        # the tool's own rasteriser gives every ground cell to exactly one triangle
        P = self.V[:, :2].astype(np.int64)
        T = self.T.astype(np.int64)
        own = np.full(len(P), np.iinfo(np.int64).max)
        np.minimum.at(own, T.ravel(), np.repeat(np.arange(len(T)), 3))
        k, px, py, m, mine = ct.rasterise(P, self.V[:, 2].astype(np.int64), T, np.arange(len(T)), (H, W), own)
        px, py = px[mine], py[mine]
        once = np.bincount(py * W + px, minlength=H * W).reshape(H, W)
        self.assertTrue((once[self.ground] == 1).all())
        self.assertLessEqual(int(once.max()), 1)


@unittest.skipIf(pydelatin is None, "needs pydelatin")
class SecondPass(unittest.TestCase):
    def test_a_loose_mesh_is_refined_until_no_cell_is_over(self):
        rng = np.random.default_rng(5)
        h, w = 64, 96
        z = (250 + np.cumsum(rng.normal(0, 0.05, (h, w)), 1) + np.cumsum(rng.normal(0, 0.05, (h, w)), 0)).astype(np.float32)
        tri = ct.greedy(z / 0.5, (h, w))  # (a mesh to 50 cm against a tolerance of 2 cm: most triangles have cells over)
        tri.run()
        pts, T = tri.getPoints().reshape(-1, 3), tri.getTriangles().reshape(-1, 3).astype(np.int64)
        col, row = pts[:, 0].astype(np.int64), (h - 1 - pts[:, 1]).astype(np.int64)
        dl = np.zeros(((h - 1) // ct.LAT + 2, (w - 1) // ct.LAT + 2), np.float32)
        tolf = lambda d: np.full(np.shape(d), 0.02)  # noqa: E731
        mesh = ct.Mesh(np.column_stack([col, row]), np.round(z[row, col] * 100), T, z, lambda r, c: np.ones(np.shape(r), bool),
                       dl, (h, w), tolf, threads=2)
        first = mesh.check()
        self.assertGreater(len(first["over"][0]), 100)
        added, rounds = mesh.refine(first["over"], log=lambda s: None)
        final = mesh.check()
        self.assertEqual(len(final["over"][0]), 0)
        self.assertEqual(final["cells"], h * w)  # (conforming: each cell in exactly one triangle)
        self.assertGreater(added, 0)


class Key(unittest.TestCase):
    def test_the_key_follows_the_raster_tracks_floor_and_tolerance(self):
        segs = tracks()
        base = dict(raster="a" * 64, tiles={"1_2.tif": "b" * 64}, grids={}, tracks=segs, osm="c" * 16, code="d")
        k = ct.key(**base)
        self.assertEqual(k, ct.key(**base))
        moved = segs.copy()
        moved[0, 0] += 0.01
        for change in ({"raster": "e" * 64}, {"tracks": moved}, {"floor": 171.0},
                       {"tolerance": (0.2, ct.D0, ct.TOL_MAX, ct.LAT, ct.CAP)}, {"tiles": {"1_2.tif": "f" * 64}},
                       {"code": "g"}):
            self.assertNotEqual(ct.key(**(base | change)), k, change)


class Grids(unittest.TestCase):
    def test_pull_push_fills_gaps_smoothly(self):
        a = np.arange(64, dtype=float).reshape(8, 8)
        b = a.copy()
        b[2:6, 2:6] = np.nan
        f = ct.fill_gaps(b)
        self.assertFalse(np.isnan(f).any())
        self.assertLess(np.abs(f - a)[2:6, 2:6].max(), 12)
        self.assertTrue((ct.fill_gaps(np.full((3, 3), np.nan)) == 0).all())

    def test_steps_from_the_ground(self):
        g = np.zeros((9, 9), bool)
        g[4, 4] = True
        d = ct.ground_steps(g, 6)
        self.assertEqual(d[4, 4], 0)
        self.assertEqual(d[4, 6], 2)
        self.assertEqual(d[0, 0], 6)


if __name__ == "__main__":
    unittest.main()
