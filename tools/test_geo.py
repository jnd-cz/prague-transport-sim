# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/geo.py's tile grid (#30): 500 m squares on the absolute S-JTSK grid, named by their index there.

    python -P -E tools/test_geo.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo  # noqa: E402


class Tiles(unittest.TestCase):
    def test_the_origins_tile(self):
        # (the Marian column, E -742,806, N -1,043,024: 24 m south of N -1,043,000)
        e, n = geo.tile_index(0.0, 0.0)
        self.assertEqual((int(e), int(n)), (-1486, -2087))
        self.assertEqual(geo.tile_name(e, n), "e-1486_n-2087")
        self.assertEqual(geo.tile_box(e, n), (-194.0, -476.0, 306.0, 24.0))

    def test_a_tile_holds_its_own_box_and_its_neighbour_starts_at_its_edge(self):
        x0, y0, x1, y1 = geo.tile_box(-1480, -2080)
        e, n = geo.tile_index([x0, x1 - 1e-6, x1], [y0, y1 - 1e-6, y0])
        self.assertEqual(e.tolist(), [-1480, -1480, -1479])
        self.assertEqual(n.tolist(), [-2080, -2080, -2080])

    def test_the_lattices_lie_on_the_tiles_grid(self):
        x0, y0, _, _ = geo.tile_box(-1486, -2087)
        for step in (5.0, 25.0, geo.TILE):
            self.assertEqual(geo.on_grid(x0 - 0.5, step, 0), x0)
            self.assertEqual(geo.on_grid(y0 - 0.5, step, 1), y0)
            self.assertEqual(geo.on_grid(x0, step, 0), x0)
        self.assertEqual(geo.on_grid(0.3, 5.0, 0), 1.0)  # (E -742,805)


if __name__ == "__main__":
    unittest.main()
