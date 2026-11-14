# SPDX-License-Identifier: AGPL-3.0-or-later
"""The survey's medians among its other areas (tools/zps_medians.py, #555): python -P -E tools/test_zps_medians.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zps_medians as M  # noqa: E402


def rect(x0, x1, y0, y1, c, l=0):
    return {"c": c, "l": l, "r": [[x0, y0, 200.0], [x1, y0, 200.0], [x1, y1, 200.0], [x0, y1, 200.0]]}


class Medians(unittest.TestCase):
    def test_a_tram_reservation_stays_tram_and_the_others_are_green_or_paved(self):
        areas = [rect(0, 100, 0, 7, "tram"), rect(0, 100, 0, 7, "median"),       # (the reservation, mapped twice)
                 rect(200, 300, 0, 3, "median"), rect(400, 500, 0, 3, "median"),
                 rect(0, 100, 10, 14, "road")]
        green = [{"p": [[190, -1], [310, -1], [310, 4], [190, 4]], "t": "grass"}]
        n = M.sort(areas, green)
        self.assertEqual(n, {"medians": 3, "tram": 1, "green": 1, "paved": 1})
        self.assertEqual([(a["c"], a["r"][0][0], a.get("s")) for a in areas],
                         [("tram", 0, None), ("median", 200, "green"), ("median", 400, None), ("road", 0, None)])

    def test_a_median_partly_beside_the_tram_area_stays(self):
        areas = [rect(0, 100, 0, 7, "tram"), rect(60, 160, 0, 3, "median")]   # (40 % under it)
        self.assertEqual(M.sort(areas, [])["tram"], 0)
        self.assertEqual([a["c"] for a in areas], ["tram", "median"])


if __name__ == "__main__":
    unittest.main()
