# SPDX-License-Identifier: AGPL-3.0-or-later
"""The terrain raster's reader: python -P -E tools/test_ipr_dtm.py (no download needed)."""
import io
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ipr_dtm import IprDtm, ground, lzw, tile_tiff  # noqa: E402


class Lzw(unittest.TestCase):
    def test_decodes_what_libtiff_encodes(self):
        rng = np.random.default_rng(7)
        # smooth heights (long runs: the code width grows to 12 bits and the table is cleared) and noise
        z = (200 + np.cumsum(rng.normal(0, 0.01, 300 * 300))).astype("<f4").reshape(300, 300)
        z[:40] = -3.4028235e38
        buf = io.BytesIO()
        Image.fromarray(z, "F").save(buf, "TIFF", compression="tiff_lzw", tiffinfo={278: 300})  # one strip
        im = Image.open(io.BytesIO(buf.getvalue()))
        off, n = im.tag_v2[273][0], im.tag_v2[279][0]
        self.assertEqual(lzw(buf.getvalue()[off:off + n]), z.tobytes())


    def test_a_tile_wrapped_as_its_own_tiff_decodes_the_same(self):
        # (#205: the reader hands each tile to Pillow's libtiff this way)
        rng = np.random.default_rng(3)
        z = (200 + np.cumsum(rng.normal(0, 0.01, 128 * 128))).astype("<f4").reshape(128, 128)
        buf = io.BytesIO()
        Image.fromarray(z, "F").save(buf, "TIFF", compression="tiff_lzw", tiffinfo={278: 128})
        im = Image.open(io.BytesIO(buf.getvalue()))
        off, n = im.tag_v2[273][0], im.tag_v2[279][0]
        data = buf.getvalue()[off:off + n]
        with Image.open(io.BytesIO(tile_tiff(data, 128, 128))) as t:
            self.assertEqual(np.array(t, dtype="<f4").tobytes(), lzw(data))


class Floor(unittest.TestCase):
    """A height under the floor (sources.TERRAIN_FLOOR) is no ground, as the declared no-data; the edge tiles' padding past
    the image (0.00 m, #325) is never read."""

    def test_a_decoded_tile_holds_no_ground_under_the_floor(self):
        z = np.full((128, 128), 250.0, "<f4")
        z[0, :5] = [0.0, -3.4028235e38, 169.99, 170.0, 170.73]  # zero, declared no-data, under, at and over the floor
        buf = io.BytesIO()
        Image.fromarray(z, "F").save(buf, "TIFF", compression="tiff_lzw", tiffinfo={278: 128})
        im = Image.open(io.BytesIO(buf.getvalue()))
        off, n = im.tag_v2[273][0], im.tag_v2[279][0]
        r = IprDtm.__new__(IprDtm)  # (one tile at offset 0 of a file of its own)
        r.f, r.offs, r.cnts = io.BytesIO(buf.getvalue()[off:off + n]), [0], [n]
        r.w = r.h = r.tw = r.th = 128
        r.ntx, r.tiles, r.e0, r.n0 = 1, {}, 0.5, 127.5
        a = r.tile(0, 0)
        self.assertEqual(np.isnan(a[0, :5]).tolist(), [True, True, True, False, False])
        self.assertEqual(int(np.isnan(a).sum()), 3)
        self.assertTrue(np.isnan(r.sample(np.array([0.5, 2.5]), np.array([127.5, 127.5]))).all())

    def test_an_edge_tiles_padding_is_never_read(self):
        # (the file's last tile column and row reach past its 35,001 x 26,001 cells, padded with 0.00 m: #325's zeros)
        cells = np.zeros((128, 128), np.float32)
        cells[:90, :100] = 250.0
        r = IprDtm.__new__(IprDtm)
        r.w, r.h, r.tw, r.th, r.e0, r.n0, r.tiles = 100, 90, 128, 128, 0.5, 89.5, {(0, 0): cells}
        i, j = np.meshgrid(np.arange(128), np.arange(128))
        got = r.cells(i, j)
        self.assertTrue((got[:90, :100] == 250).all())
        self.assertTrue(np.isnan(got[90:]).all() and np.isnan(got[:, 100:]).all())
        self.assertTrue(np.isnan(r.sample(np.array([99.8]), np.array([50.0])))[0])  # (bilinear across the edge)

    def test_the_floor_is_the_users(self):
        from sources import TERRAIN_FLOOR
        self.assertEqual(TERRAIN_FLOOR, 170.0)  # (the user, 2026-11-09, #428)
        self.assertTrue(np.isnan(ground(np.array([0.0, np.nan, -9999.0], np.float32))).all())


class Sample(unittest.TestCase):
    def raster(self, cells, e0, n0):
        r = IprDtm.__new__(IprDtm)  # (the file's tiles, without a file)
        r.w = r.h = r.tw = r.th = cells.shape[0]
        r.e0, r.n0, r.tiles = e0, n0, {(0, 0): cells}
        return r

    def test_bilinear_on_cell_centres_off_the_metre_grid(self):
        i, j = np.meshgrid(np.arange(8.0), np.arange(8.0))
        r = self.raster((10 * i + j).astype(np.float32), -100.2778, -50.3889)  # z = 10 * column + row
        e, n = np.array([-100.2778, -97.7778, -95.0]), np.array([-50.3889, -52.8889, -54.0])
        np.testing.assert_allclose(r.sample(e, n), [0, 27.5, 10 * 5.2778 + 3.6111], atol=1e-3)

    def test_no_data_and_outside_are_nan(self):
        cells = np.full((8, 8), 200, np.float32)
        cells[3, 3] = np.nan
        r = self.raster(cells, 0.5, 7.5)
        z = r.sample(np.array([3.2, 1.0, -5.0]), np.array([4.2, 6.0, 4.0]))
        self.assertTrue(np.isnan(z[0]))
        self.assertEqual(z[1], 200)
        self.assertTrue(np.isnan(z[2]))


if __name__ == "__main__":
    unittest.main()
