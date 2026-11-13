# SPDX-License-Identifier: AGPL-3.0-or-later
"""The track surface review set (tools/surface_review.py, #574): python -P -E tools/test_surface_review.py."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import surface_review as T  # noqa: E402


class Frame:
    def ll(self, x, y):
        return 50 + y / 1e5, 14 + x / 1e5


def along(spec):
    """[(length m, class)] as samples every 2 m."""
    out, s = [], 0.0
    for L, c in spec:
        for _ in range(int(L / 2)):
            out.append((s, c, c or "", 1))
            s += 2
    return out


class Runs(unittest.TestCase):
    def test_a_short_run_joins_its_longer_neighbour(self):
        rs = T.runs(along([(100, "asphalt"), (6, "setts"), (80, "setts"), (8, "asphalt"), (60, "setts")]))
        self.assertEqual([(r[2], round(r[0]), round(r[1])) for r in rs], [("asphalt", 0, 98), ("setts", 100, 252)])


class Cards(unittest.TestCase):
    def test_a_stretch_its_switches_and_the_junction_beside_it(self):
        data = {"path": [[0.0, 0.0], [400.0, 0.0]], "stops": [{"name": "A", "s": 0.0}],
                "styles": [{"s0": 230, "s1": 250, "style": "embedded", "source": "junction", "junction": ["switch"]},
                           {"s0": 350, "s1": 360, "style": "embedded", "source": "junction", "junction": ["road"]}]}
        rs = T.runs(along([(100, "asphalt"), (120, "setts"), (180, "asphalt")]))
        cs = T.cards_for("22", data, rs, Frame())
        self.assertEqual([(c["what"], c["s0"], c["s1"]) for c in cs],
                         [("stretch", 100, 218), ("switch", 88, 108), ("switch", 208, 228), ("junction", 230, 250)])
        self.assertIn(T.SETTS, cs[0]["options"])
        self.assertTrue(all(o in T.ANSWER or o in (T.UNSURE, T.TRACKS_DIFFER) for c in cs for o in c["options"]))


if __name__ == "__main__":
    unittest.main()
