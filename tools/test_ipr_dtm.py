"""The terrain raster's reader: python -P -E tools/test_ipr_dtm.py (no download needed)."""
import io
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ipr_dtm import IprDtm, lzw  # noqa: E402


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
