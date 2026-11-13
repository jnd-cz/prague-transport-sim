# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests of the switch-tip review: the forks an orthophoto track ends at. python -P -E tools/test_fork_review.py"""
from pathlib import Path
import sys
import types
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shapely.geometry import LineString  # noqa: E402
import fork_review as fr  # noqa: E402


class Frame:
    def ll(self, x, y):
        return (50.0 + y / 1e5, 14.0 + x / 1e5)


def network(src='ortho'):
    line = LineString([(0, 0), (12, 0), (20, 5)])
    return types.SimpleNamespace(nodes={'a': {'xy': (0.0, 0.0)}, 'b': {'xy': (20.0, 5.0)}},
                                 edges={1: {'a': 'a', 'b': 'b', 'src': src, 'line': line}})


class PhotoEnds(unittest.TestCase):
    def test_a_card_per_end_of_a_drawn_orthophoto_track(self):
        tracks = [{'p': [(0, 0), (12, 0), (20, 5)]}]
        cards = fr.photo_ends('17', tracks, network(), [(1.0, 0.0, 7, 'railway=switch')], Frame())
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]['mag'], 12.0)
        self.assertTrue(all(c['pick'] for c in cards))
        # (the OSM switch is marked on the card of the fork near it, and on the other only within FORK)
        self.assertIn("OSM's switch (railway=switch)", [m['label'] for m in cards[0]['marks']])
        self.assertNotEqual(cards[0]['id'], cards[1]['id'])

    def test_no_card_on_a_line_that_does_not_draw_it(self):
        self.assertEqual(fr.photo_ends('9', [{'p': [(500, 500), (600, 500)]}], network(), [], Frame()), [])

    def test_no_card_for_a_di_track(self):
        self.assertEqual(fr.photo_ends('17', [{'p': [(0, 0), (12, 0), (20, 5)]}], network('di'), [], Frame()), [])


if __name__ == '__main__':
    unittest.main()
