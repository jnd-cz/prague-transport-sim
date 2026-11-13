# SPDX-License-Identifier: AGPL-3.0-or-later
"""Track on or under a Mosty 3D bridge (#192): python -P -E tools/test_track_bridges.py."""
from pathlib import Path
import sys
import unittest

import shapely
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dtmp_tracks import Segments
import track_bridges as tb


class FakeBridges:
    """Footprints with a flat top each; `holes` are boxes where the model has no surface."""

    def __init__(self, decks, holes=()):
        self.footprints = [d[0] for d in decks]
        self.tops = [d[1] for d in decks]
        self.ids = list(range(len(decks)))
        self.holes = holes
        self.foot_tree = shapely.STRtree(self.footprints)

    def top_of(self, x, y, k):
        p = shapely.Point(x, y)
        if any(h.contains(p) for h in self.holes) or not self.footprints[k].contains(p):
            return None
        return self.tops[k]


def track(zs, length=100):
    """A DI track along y = 0 with heights at evenly spaced vertices."""
    n = len(zs) - 1
    return [{'id': 'di-1', 'coords': [(length * i / n, 0, z) for i, z in enumerate(zs)], 'attrs': {}, 'sources': []}]


def run(paths, bridges, archive=(), terrain=None):
    terrain = terrain or (lambda xs, ys: [None] * len(xs))
    return tb.decide(paths, Segments(paths), Segments(list(archive)), terrain, bridges)


class TrackBridges(unittest.TestCase):
    def test_track_meeting_the_deck_is_on_and_a_clearance_is_under(self):
        on = run(track([205] * 11), FakeBridges([(box(40, -5, 60, 5), 205.4)]))
        self.assertEqual([f['verdict'] for f in on], ['on'])
        under = run(track([205] * 11), FakeBridges([(box(40, -5, 60, 5), 211.0)]))
        self.assertEqual([f['verdict'] for f in under], ['under'])
        between = run(track([205] * 11), FakeBridges([(box(40, -5, 60, 5), 207.2)]))
        self.assertEqual([f['verdict'] for f in between], ['unknown'])

    def test_one_end_meeting_the_deck_wins_over_the_archive_on_the_ground_at_the_other(self):
        # Libeň (#190): the archive dips onto the street under the deck at the river-bridge end
        heights = [192.4] * 4 + [186.0] + [190.2] * 6
        found = run(track(heights), FakeBridges([(box(41, -5, 95, 5), 190.4)]))
        self.assertEqual([f['verdict'] for f in found], ['on'])

    def test_the_terrain_at_an_abutment_counts_where_the_archive_dives(self):
        # Palackého most: the archive falls to the river's level, the terrain at the abutment is the deck
        nodi = track([None] * 11)
        archive = [{'id': 1, 'coords': [(0, 0, 192.7), (100, 0, 187.3)], 'attrs': {}, 'sources': []}]
        deck = FakeBridges([(box(40, -5, 60, 5), 197.4)])
        self.assertEqual([f['verdict'] for f in run(nodi, deck, archive)], ['under'])
        abutment = lambda xs, ys: [197.2] * len(xs)
        self.assertEqual([f['verdict'] for f in run(nodi, deck, archive, abutment)], ['on'])

    def test_a_piece_continuing_an_on_piece_of_the_same_bridge_is_on(self):
        decks = FakeBridges([(box(30, -5, 50, 5), 205.3), (box(50, -5, 70, 5), 205.3)], holes=[box(50, -5, 70, 5)])
        found = run(track([205] * 11), decks)
        self.assertEqual(sorted(f['verdict'] for f in found), ['on', 'on'])
        self.assertTrue(any(f.get('continues') for f in found))

    def test_an_abutment_on_land_stays_out_of_the_mask(self):
        # Palackého most's Smíchov end: the model's top meets the terrain, the track is at grade there
        ground = lambda xs, ys: [205.0 if x < 48 else 195.0 for x in xs]
        found = run(track([205] * 11), FakeBridges([(box(30, -5, 70, 5), 205.3)]), terrain=ground)
        geom, _, pieces = tb.mask(found)
        self.assertFalse(geom.intersects(shapely.Point(38, 0)))
        self.assertTrue(geom.contains(shapely.Point(60, 0)))
        self.assertAlmostEqual(pieces[0]['xy'][0][0], 48, delta=1)

    def test_only_on_pieces_enter_the_mask(self):
        found = run(track([205] * 11), FakeBridges([(box(20, -5, 30, 5), 205.2), (box(60, -5, 70, 5), 212.0)]))
        geom, ids, pieces = tb.mask(found)
        self.assertEqual(ids, ['mosty3d:0'])
        self.assertTrue(geom.contains(shapely.Point(25, 0)))
        self.assertFalse(geom.intersects(shapely.Point(65, 0)))


if __name__ == '__main__':
    unittest.main()
