"""The DMR 5G tiles and the passages rule: python -P -E tools/test_dmr5g.py (no download, no raw/ needed)."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dmr5g  # noqa: E402


class Passage(unittest.TestCase):
    def test_what_counts_as_a_passage(self):
        yes = [{"tunnel": "yes"}, {"tunnel": "building_passage"}, {"tunnel": "culvert"}, {"covered": "yes"},
               {"culvert": "yes"}, {"layer": "-1"}]
        no = [{}, {"tunnel": "no"}, {"layer": "1"}, {"layer": "x"}, {"tunnel": "yes", "location": "underground"},
              {"railway": "subway", "tunnel": "yes"}]
        self.assertTrue(all(dmr5g.passage(t) for t in yes))
        self.assertFalse(any(dmr5g.passage(t) for t in no))


class Tiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, ix, iy, a):
        Image.fromarray(a.astype(np.float32), "F").save(os.path.join(self.tmp.name, dmr5g.name(ix, iy)))

    def test_bilinear_on_pixel_centres_and_a_missing_tile(self):
        j, i = np.mgrid[0:500, 0:500]
        self.write(-1, -2, 200 + 0.1 * i + 0.01 * j)  # (rows go south)
        t = dmr5g.Tiles(directory=self.tmp.name)
        E = np.array([-500 + 10.5, -500 + 10.0])
        N = np.array([-1000 + 500 - 20.5, -1000 + 500 - 20.5])
        np.testing.assert_allclose(t.sample(E, N), [200 + 1.0 + 0.2, 200 + 0.95 + 0.2], atol=1e-4)
        self.assertTrue(t.have(-1, -2))
        self.assertFalse(t.have(0, 0))
        with self.assertRaises(SystemExit):  # (not in raw/dem/ and no fetch: an error, #223)
            t.tile(0, 0)

    def test_fetch_all_skips_what_is_there_and_downloads_the_rest(self):
        self.write(1, 1, np.zeros((500, 500)))
        got = []

        def fake(ix, iy, path, out=print):
            got.append((ix, iy))
            Image.fromarray(np.ones((500, 500), np.float32), "F").save(path)
        old_dir, old_dl = dmr5g.DIR, dmr5g.download
        dmr5g.DIR, dmr5g.download = self.tmp.name, fake
        try:
            n, size = dmr5g.fetch_all([(1, 1), (2, 1), (3, 1)], pause=0, out=lambda *a, **k: None)
        finally:
            dmr5g.DIR, dmr5g.download = old_dir, old_dl
        self.assertEqual(got, [(2, 1), (3, 1)])
        self.assertEqual(n, 2)
        self.assertGreater(size, 0)


class UnderIpr(unittest.TestCase):
    def test_the_tiles_under_ground_cells(self):
        class Ipr:  # (a raster of 600 x 300 cells of 1 m, tiles of 128; ground in its left half only)
            w, h, tw, th = 600, 300, 128, 128
            ntx = 5
            e0, n0 = 0.5, 999.5

            def decode(self, tx, ty):
                a = np.full((128, 128), -3.4e38, np.float32)
                cols = tx * 128 + np.arange(128)
                a[:, cols < 300] = 250.0
                return a
        tiles = dmr5g.under_ipr(Ipr())
        # E 0.5..299.5 lies in ix 0; N 999.5 down to 700.5 lies in iy 1
        self.assertEqual(tiles, [(0, 1)])


if __name__ == "__main__":
    unittest.main()
