# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/flicker.py's counting: python -P -E tools/test_flicker.py

Made-up frames: a pixel that changes and comes back is a flick, one that changes and stays is not; a way's flicks
within a pixel of the other's are not "only" its own; the two ways' pictures are compared frame by frame. (The
drive itself needs a page and the GPU: `tools/flicker.py --near 0.001` is its calibration, DEVELOPING.md.)
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flicker  # noqa: E402


def frames(n, spots):
    """n grey frames of 8 x 8; spots: {(frame, y, x): brightness}."""
    out = [np.full((8, 8), 100, dtype=np.int16) for _ in range(n)]
    for (i, y, x), v in spots.items():
        out[i][y, x] = v
    return out


class FlickerTest(unittest.TestCase):
    def test_flicks(self):
        # (2, 2) is dark in frame 2 only: a flick there. (5, 5) turns dark in frame 2 and stays: an edge that passed.
        f = frames(5, {(2, 2, 2): 20, (2, 5, 5): 20, (3, 5, 5): 20, (4, 5, 5): 20})
        got = flicker.flicks(f)
        self.assertEqual(len(got), 3)
        self.assertEqual([int(g.sum()) for g in got], [0, 1, 0])
        self.assertTrue(got[1][2, 2])
        # a change under the threshold is no flick
        self.assertEqual(sum(int(g.sum()) for g in flicker.flicks(frames(5, {(2, 2, 2): 100 - flicker.FLICK}))), 0)

    def test_compare(self):
        a = frames(5, {(2, 2, 2): 20, (2, 6, 6): 20})    # a flicks at (2, 2) and at (6, 6)
        b = frames(5, {(2, 2, 3): 20})                   # b flicks beside a's first: the same edge, a pixel off
        r = flicker.compare(a, b)
        self.assertEqual(r["flicks"], [2 / 3, 1 / 3])
        self.assertEqual(r["only"], [1 / 3, 0])          # only (6, 6) is a's own
        self.assertTrue(r["marks"][0][6, 6] and not r["marks"][0][2, 2])
        self.assertFalse(r["marks"][1].any())
        # the pictures differ in frame 2 only, in three of its 64 pixels
        self.assertAlmostEqual(r["differ"][1], 300 / 64)
        self.assertAlmostEqual(r["differ"][0], 300 / 64 / 5)

    def test_grown(self):
        m = np.zeros((5, 5), dtype=bool)
        m[0, 0] = m[3, 3] = True
        g = flicker.grown(m)
        self.assertEqual(int(g.sum()), 4 + 9)
        self.assertEqual(g.shape, m.shape)


if __name__ == "__main__":
    unittest.main()
