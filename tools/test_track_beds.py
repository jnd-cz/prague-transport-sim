# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every drawn track's bed width (tools/track_beds.py, #547): python -P -E tools/test_track_beds.py."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import track_beds as B  # noqa: E402


def rect(x0, x1, y0, y1, c):
    return {"c": c, "l": 0, "r": [[x0, y0, 200], [x1, y0, 200], [x1, y1, 200], [x0, y1, 200]]}


def track(p):
    return {"p": p, "zs": [200.0] * (int(math.dist(p[0], p[-1]) / 2) + 2)}


def data(tracks, styles=()):
    return {"path": [[0.0, -100.0], [100.0, -100.0]], "styles": list(styles), "tracks": tracks, "heights": {"step": 2.0}}


class Widths(unittest.TestCase):
    def test_out_to_the_edge_of_the_surveys_tram_area(self):
        d = data([track([[0, 0], [100, 0]])])
        bs = B.beds(d, {"areas": [rect(-10, 110, -1.5, 2.6, "tram")]})
        mid = len(bs[0]["l"]) // 2
        self.assertAlmostEqual(bs[0]["l"][mid] / 100, 2.5, delta=0.11)    # (left of +x is +y)
        self.assertAlmostEqual(bs[0]["r"][mid] / 100, 1.4, delta=0.11)

    def test_without_the_styles_area_the_calibrated_width(self):
        d = data([track([[0, 0], [100, 0]])])
        bs = B.beds(d, {"areas": [rect(-10, 110, -5, 5, "road")]})
        self.assertEqual(set(bs[0]["l"]), {round(B.WIDTH["panels"] * 100)})
        self.assertEqual(B.beds(d, None)[0]["r"][3], round(B.WIDTH["panels"] * 100))

    def test_paired_tracks_meet_in_the_middle_of_their_strip(self):
        d = data([track([[0, 0], [100, 0]]), track([[100, 3.2], [0, 3.2]])])
        bs = B.beds(d, {"areas": [rect(-10, 110, -2, 5.2, "tram")]})
        mid = len(bs[0]["l"]) // 2
        self.assertEqual((bs[0]["l"][mid], bs[0]["meet"][mid]), (160, 1))
        self.assertEqual((bs[1]["l"][mid], bs[1]["meet"][mid]), (160, 1))   # (track 1 runs -x: its left, -y, faces track 0)
        self.assertEqual(bs[1]["r"][mid], 200)

    def test_a_crossing_track_stops_the_bed_where_its_axis_is_nearer(self):
        d = data([track([[0, 0], [100, 0]]), track([[50, -20], [50, 20]])])
        bs = B.beds(d, None)
        self.assertAlmostEqual(bs[0]["l"][24], 200, delta=B.STEP_OUT * 100)   # (s 48: the crossing axis 2 m along)
        self.assertEqual(bs[0]["l"][25], 80)        # (on it: never inside its own rails)
        self.assertEqual(bs[0]["meet"][24], 0)
        for side in "lr":   # (the crossing track 2 m before ours)
            self.assertAlmostEqual(bs[1][side][9], 200, delta=B.STEP_OUT * 100)
        self.assertEqual(bs[0]["l"][5], round(B.WIDTH["panels"] * 100))


class Report(unittest.TestCase):
    def test_the_strip_is_filled_and_less_street_shows(self):
        d = data([track([[0, 0], [100, 0]]), track([[100, 3.2], [0, 3.2]])])
        dtm = {"areas": [rect(-10, 110, -2, 5.2, "tram")]}
        r = B.report(d, dtm, B.beds(d, dtm))
        self.assertGreater(r["bed m2"][1], r["bed m2"][0])
        self.assertLess(r["street showing m2"][1], r["street showing m2"][0])


if __name__ == "__main__":
    unittest.main()
