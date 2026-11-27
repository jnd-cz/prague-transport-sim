# SPDX-License-Identifier: AGPL-3.0-or-later
"""IPR's pits under the survey's streets (tools/ipr_pits.py, #867): python -P -E tools/test_ipr_pits.py (no raw/)."""
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipr_pits as ip  # noqa: E402

ROAD, SIDEWALK, PAVED = (1 + ip.STREET.index(c) for c in ("road", "sidewalk", "paved"))


def street(n=60, z=240.0):
    """A level street (n x n cells at z, tilted 1 % east) and its class codes: road west of column 30, sidewalk east."""
    jj, ii = np.mgrid[0:n, 0:n]
    a = z + 0.01 * ii.astype(np.float64)
    cls = np.where(ii < 30, ROAD, SIDEWALK).astype(np.uint8)
    return a, cls


def level(j, i):
    """DMR 5G with a level street: no pit in the 2009-2013 lidar."""
    return 240.1


def dig(a, j, i, h, w, depth):
    a[j:j + h, i:i + w] -= depth
    return a


def verdicts(a, cls, **kw):
    return {(p["j"] // 10, p["i"] // 10): p for p in ip.pits(a, cls, **kw)}


class Pits(unittest.TestCase):
    def test_a_pit_in_the_road_is_filled_from_its_rim(self):
        a, cls = street()
        dig(a, 10, 10, 4, 5, 4.0)  # (Táboritská: 5 x 4 cells, 4 m deep, a flat floor)
        (p,) = ip.pits(a, cls, survey_z=lambda j, i: 240.1, dmr=level)
        self.assertIsNone(p["kept"])
        self.assertEqual(p["class"], "road")
        self.assertAlmostEqual(p["depth"], 4.0, places=1)
        rr, cc, z = p["cells"]
        self.assertEqual(len(rr), 20)
        self.assertLess(np.abs(z - (240 + 0.01 * cc)).max(), 0.01)  # (the rim's plane: the street's own tilt)

    def test_beside_the_street_stair_well_and_trench_are_kept(self):
        a, cls = street()
        cls[:, 50:] = ip.NO  # (a yard east of the sidewalk, off the survey)
        cls[35:45, 10:20] = ip.KEPT  # (stairs down in the road's area)
        dig(a, 10, 52, 4, 4, 2.0)  # (off the street)
        dig(a, 37, 12, 4, 4, 2.0)  # (the stair's well)
        dig(a, 52, 5, 3, 20, 1.5)  # (a trench along the road: 20 m long)
        got = {p["j"] // 10 * 10 + p["i"] // 10: p["kept"] for p in ip.pits(a, cls, survey_z=lambda j, i: 240.2)}
        self.assertEqual(got.get(15), "off the street")
        self.assertEqual(got.get(31), "stairs or a wall")
        self.assertEqual(len(got), 2)  # (the trench is no pit)

    def test_another_level_and_a_rough_rim_are_kept(self):
        a, cls = street()
        cls[5:20, 5:20] = ip.OTHER  # (a deck over the road)
        dig(a, 10, 10, 3, 3, 2.0)
        dig(a, 40, 10, 3, 3, 2.0)
        a[36:47, 6:9] += 1.5  # (a wall's top beside the second one, on the road's class: no plane)
        got = {p["j"] // 10: p["kept"] for p in ip.pits(a, cls)}
        self.assertEqual(got[1], "under the ground's level")
        self.assertEqual(got[4], "rim not level")

    def test_a_pit_at_a_kerb_reads_its_own_side_of_the_rim(self):
        # (Bělohorská: a sidewalk pit beside the kerb, the road 0.15 m under the sidewalk)
        a, cls = street()
        a[:, :30] -= 0.15
        dig(a, 20, 30, 3, 3, 3.0)
        (p,) = ip.pits(a, cls, survey_z=lambda j, i: 240.3, dmr=level)
        self.assertIsNone(p["kept"])
        self.assertEqual(p["class"], "sidewalk")
        self.assertLess(p["rough"], 0.05)

    def test_off_the_survey_level_is_kept(self):
        a, cls = street()
        dig(a, 10, 10, 4, 4, 3.0)
        (p,) = ip.pits(a, cls, survey_z=lambda j, i: 238.9)
        self.assertEqual(p["kept"], "not at the survey's level")

    def test_a_pit_fills_only_where_dmr5g_is_level(self):
        a, cls = street()
        cls[:] = PAVED
        dig(a, 10, 10, 4, 4, 1.5)
        dig(a, 40, 40, 4, 4, 1.5)
        dmr = lambda j, i: 240.1 if j < 30 else 238.7  # noqa: E731  (the second in the 2009-2013 lidar too)
        got = {p["j"] // 30: p["kept"] for p in ip.pits(a, cls, dmr=dmr)}
        self.assertEqual(got, {0: None, 1: "in DMR 5G too"})
        (p,) = ip.pits(dig(street()[0], 10, 10, 4, 4, 1.5), np.full((60, 60), PAVED, np.uint8))
        self.assertEqual(p["kept"], "in DMR 5G too")  # (no DMR: kept)
        # (Na Vápence's garage ramp: a road's pit 3 m deep, in the 2009-2013 lidar 1.6 m under the rim: it stays)
        a, cls = street()
        dig(a, 10, 10, 5, 11, 3.0)
        (p,) = ip.pits(a, cls, survey_z=lambda j, i: 239.7, dmr=lambda j, i: 238.5)
        self.assertEqual((p["class"], p["kept"]), ("road", "in DMR 5G too"))
        (p,) = ip.pits(a, cls, survey_z=lambda j, i: 239.7, dmr=level)
        self.assertIsNone(p["kept"])

    def test_a_long_pit_fills_where_dmr5g_is_level(self):
        # (Škrétova: 5 x 13 cells in the road, level in DMR 5G)
        a, cls = street()
        dig(a, 10, 5, 13, 5, 4.0)
        dig(a, 30, 40, 18, 4, 4.0)  # (18 m: a trench, no pit)
        (p,) = ip.pits(a, cls, dmr=lambda j, i: 240.05)
        self.assertIsNone(p["kept"])
        (p,) = ip.pits(a, cls, dmr=lambda j, i: 236.1)
        self.assertEqual(p["kept"], "in DMR 5G too")

    def test_a_pit_half_off_the_survey_fills_its_street_cells(self):
        a, cls = street()
        cls[:, :12] = ip.NO  # (a yard west of the road)
        dig(a, 10, 10, 4, 5, 2.0)  # (2 of its 5 columns in the yard)
        (p,) = ip.pits(a, cls, dmr=level)
        self.assertIsNone(p["kept"])
        self.assertEqual(sorted(set(p["cells"][1].tolist())), [12, 13, 14])
        cls[:, :13] = ip.NO  # (and mostly off it: kept)
        (p,) = ip.pits(a, cls)
        self.assertEqual(p["kept"], "off the street")

    def test_shallow_pits_are_none(self):
        a, cls = street()
        dig(a, 10, 10, 4, 4, 0.8)
        self.assertEqual(ip.pits(a, cls), [])


class Fills(unittest.TestCase):
    def test_the_file_fills_the_tiles_a_reader_decodes(self):
        from ipr_dtm import IprDtm
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "fills.json")
            with open(f, "w", encoding="utf-8") as fh:
                json.dump({"filled": [{"cells": [[3, 4, 241.5], [130, 5, 242.0]]}]}, fh)
            by = ip.load(f)(128, 128)
            self.assertEqual(sorted(by), [(0, 0), (1, 0)])
            r = IprDtm.__new__(IprDtm)
            r._fills = by
            a = r.fill(1, 0, np.zeros((128, 128), np.float32))
            self.assertEqual(float(a[5, 2]), 242.0)
            self.assertEqual(float(a.sum()), 242.0)
            self.assertEqual(ip.load(os.path.join(d, "none.json"))(128, 128), {})

    def test_paint_holes_show_what_lay_under(self):
        cls = ip.paint((10, 10), (0.0, 9.0), [(ROAD, [[0, 0], [9, 0], [9, 9], [0, 9]], []),
                                              (SIDEWALK, [[2, 2], [7, 2], [7, 7], [2, 7]], [[[4, 4], [5, 4], [5, 5], [4, 5]]])])
        self.assertEqual(int(cls[9 - 3, 3]), SIDEWALK)
        self.assertEqual(int(cls[9 - 0, 0]), ROAD)
        self.assertEqual(int(cls[9 - 4, 4]), ROAD)  # (in the hole)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    unittest.main()
