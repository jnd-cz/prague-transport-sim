# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/bed_surface.py: the beds' rows and surface as the page lays them (#508).

    python -P -E tools/test_bed_surface.py
(the parity with the page on every line: tools/test_bed_surface_page.py, a browser test)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bed_surface as bs  # noqa: E402


def line(tracks, cant=None, lift=0.0):
    n = 60
    L = {"path": [[0, -10], [0, 110]], "pathExt": {"before": [], "after": []}, "heights": {"step": 2.0},
         "lift": {"step": 2, "unit": 0.001, "v": [lift * 1000] * n}, "tracks": tracks}
    if cant is not None:
        L["cant"] = {"step": 2, "unit": 1e-5, "c": [cant * 1e5] * n}
    return L


def track(p, z, w=200, meet=0, n=None):
    from bed_surface import poly_len
    n = n or int(poly_len(p) / 2) + 2
    return {"p": p, "zs": [z] * n if np.isscalar(z) else z, "bed": {"l": [w] * n, "r": [w] * n, "meet": [meet] * n}}


class Rows(unittest.TestCase):
    def test_densify_as_the_page(self):
        p = bs.densify([[0, 0], [3, 0], [3, 1]])
        self.assertEqual(len(p), 1 + 2 + 1)
        self.assertTrue(np.allclose(p[1], (1.5, 0)))

    def test_a_level_track_lies_at_top_of_rail_less_lift(self):
        b = bs.Beds(line([track([[0, 0], [0, 100]], 200.0)], lift=0.15))
        x, y, nx, ny, off, z = b.rows[0][10]
        self.assertEqual(off, [-2.0, -0.72, 0.72, 2.0])
        self.assertTrue(np.allclose(z, 200.0 - 0.15 - bs.BED_BELOW))
        self.assertAlmostEqual(b.surface(x + 0.5, y), 200.0 - 0.15 - bs.BED_BELOW)
        self.assertIsNone(b.surface(x + 2.5, y))

    def test_cant_tilts_the_rails_and_the_bed_on_their_plane(self):
        # (+ cant: the left rail lower; the track runs with the route)
        b = bs.Beds(line([track([[0, 0], [0, 100]], 200.0)], cant=0.06))
        _, _, _, _, off, z = b.rows[0][20]
        t = -0.72 * np.tan(np.arctan2(0.06, 1.5))
        self.assertAlmostEqual(z[2] - z[1], 2 * t)
        self.assertAlmostEqual((z[3] - z[0]) / (off[3] - off[0]), t / 0.72)

    def test_against_the_route_the_tilt_turns(self):
        a = bs.Beds(line([track([[0, 0], [0, 100]], 200.0)], cant=0.06)).tilt[0][20]
        b = bs.Beds(line([track([[0, 100], [0, 0]], 200.0)], cant=0.06)).tilt[0][20]
        self.assertAlmostEqual(a, -b)

    def test_an_edge_over_another_bed_is_lowered_to_it(self):
        # (two tracks 3 m apart, the second 0.1 m lower: the first bed's right edge lies over the second bed)
        b = bs.Beds(line([track([[0, 0], [0, 100]], 200.0), track([[3, 0], [3, 100]], 199.9)]))
        _, _, _, _, off, z = b.rows[0][30]
        self.assertAlmostEqual(z[0], 199.9 - bs.BED_BELOW, places=6)  # (its right edge at x = 2, on the other bed)
        self.assertAlmostEqual(z[3], 200.0 - bs.BED_BELOW, places=6)

    def test_meeting_a_paired_track_the_edge_takes_the_mean_of_the_near_rails(self):
        b = bs.Beds(line([track([[0, 0], [0, 100]], 200.0, w=150, meet=2), track([[3, 0], [3, 100]], 200.2, w=150, meet=1)]))
        _, _, _, _, off, z = b.rows[0][30]
        self.assertAlmostEqual(z[0], (200.0 + 200.2) / 2 - bs.BED_BELOW, places=6)

    def test_every_rail_point_of_a_bend_has_the_surface_of_its_row(self):
        # (on the outside of a bend a rail point lies past both segments' reach of bedsNear: line 37 track 4)
        p = [[0, 0], [0, 20], [3, 35], [10, 48], [22, 60]]
        b = bs.Beds(line([track(p, 200.0)]))
        pts, want = [], []
        for x, y, nx, ny, off, z in b.rows[0]:
            for j in (1, 2):
                pts.append((x + nx * off[j], y + ny * off[j]))
                want.append(z[j])
        got = b.surface_at(*np.asarray(pts).T)
        self.assertTrue(np.isfinite(got).all())
        self.assertLess(np.abs(got - want).max(), 1e-9)

    def test_a_cell_takes_its_first_rows_style(self):
        # (the route's styles change at s 50, y 40; a cell between two rows, across the bed, is one style: its first row's,
        # as the page coloured a quad between two rows. The nearest point split such a cell: a saw-tooth, #652)
        L = line([track([[0, 0], [0, 100]], 200.0)])
        L["styles"] = [{"s0": 0, "s1": 50, "style": "panels"}, {"s0": 50, "s1": 200, "style": "embedded"}]
        b = bs.Beds(L)
        rows, want = b.rows[0], b.row_styles()[0]
        i = next(i for i in range(1, len(want)) if want[i] != want[i - 1])  # (the first row of the new style)
        pts, exp = [], []
        for r in (i - 2, i - 1, i):
            (x0, y0), (x1, y1) = rows[r][:2], rows[r + 1][:2]
            for u in (0.1, 0.3, 0.7, 0.9):
                for side in (-1.2, -0.3, 0.4, 1.3):
                    pts.append((x0 + (x1 - x0) * u + side, y0 + (y1 - y0) * u))
                    exp.append(want[r])
        self.assertEqual(b.style_at(*np.asarray(pts).T), exp)
        self.assertEqual(set(exp), {"panels", "embedded"})

    def test_bed_z(self):
        row = [0, 0, 1, 0, [-2, -0.72, 0.72, 2], [1, 2, 3, 4]]
        self.assertEqual(bs.bed_z(row, -0.72), 2)
        self.assertAlmostEqual(bs.bed_z(row, 0), 2.5)
        self.assertIsNone(bs.bed_z(row, 2.1))


class Series(unittest.TestCase):
    def test_series_and_resample_as_the_page(self):
        f = bs.series({"step": 2, "unit": 0.001, "v": [0, 100, 200]})
        self.assertAlmostEqual(float(f(1.0)), 0.05)
        self.assertAlmostEqual(float(f(10.0)), 0.1999, places=6)  # (held at n - 1.001)
        r = bs.resample([1.0, None, 3.0], 2, 3, 1)
        self.assertEqual(r[0], 1.0)
        self.assertTrue(np.isnan(r[1]))


if __name__ == "__main__":
    unittest.main()
