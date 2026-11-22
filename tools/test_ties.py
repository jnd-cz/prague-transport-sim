# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ties.py: of candidates as near, the first by where they lie, whatever else the tree holds (#812).
    python -P -E tools/test_ties.py"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ties  # noqa: E402

# (two wall edges sharing the vertex (0, 0), a corner on it: 0 m from both)
EDGES = np.array([[[-3.0, -1.0], [0.0, 0.0]], [[0.0, 0.0], [-2.0, 3.0]]])


def clutter(n, seed):
    """n short edges within 30 m of the corner, none within 4 m: what else a larger box puts in the tree."""
    p = np.random.default_rng(seed).uniform(-30, 30, (3 * n + 10, 2))
    p = p[np.hypot(*p.T) > 4][:n]
    return np.stack([p, p + 0.5], 1)


class Ties(unittest.TestCase):
    def test_a_tie_goes_the_same_way_whatever_else_the_tree_holds(self):
        old, new = set(), set()
        for n in (0, 9, 30, 90):  # (9: query_nearest(all_matches=False) takes the other edge, shapely 2.2 / GEOS 3.14)
            segs = np.concatenate([EDGES, clutter(n, n + 1000)])
            tree = shapely.STRtree(shapely.linestrings(segs))
            P = shapely.points([[0.0, 0.0]])
            old.add(tuple(segs[tree.query_nearest(P, all_matches=False)[1][0]].ravel()))
            pi, ti = ties.nearest(tree, ties.segments(segs[:, 0], segs[:, 1]), P)
            new.add(tuple(segs[ti[0]].ravel()))
            # (and a stable sort by distance leaves the hits in the tree's order: the rank is the key that settles it)
            q, si = tree.query(P, predicate="dwithin", distance=0.5)
            d = shapely.distance(shapely.linestrings(segs[si]), P)
            k = ties.firsts(q, ties.segments(segs[:, 0], segs[:, 1])[si], d)
            self.assertEqual(tuple(segs[si[k[0]]].ravel()), tuple(EDGES[0].ravel()))
        self.assertGreater(len(old), 1, "the tree's order no longer moves the old pick: the case needs another layout")
        self.assertEqual(new, {tuple(EDGES[0].ravel())})  # (the first by its ends' coordinates: x -3 before 0)

    def test_a_segment_laid_the_other_way_is_told_apart(self):
        a = np.array([[0.0, 0.0], [5.0, 0.0]])
        b = np.array([[5.0, 0.0], [0.0, 0.0]])
        self.assertEqual(sorted(ties.segments(a, b).tolist()), [0, 1])
        g = shapely.linestrings(np.stack([a, b], 1))
        self.assertEqual(sorted(ties.by_place(g).tolist()), [0, 1])

    def test_keys_tell_apart_segments_over_one_another(self):
        a = np.zeros((2, 2))
        b = np.ones((2, 2))
        self.assertEqual(ties.segments(a, b, np.array([231.47, 231.31])).tolist(), [1, 0])

    def test_firsts_per_point(self):
        pi = np.array([2, 0, 2, 0, 1])
        key = np.array([5, 9, 1, 3, 7])
        k = ties.firsts(pi, key)
        self.assertEqual(pi[k].tolist(), [0, 1, 2])
        self.assertEqual(key[k].tolist(), [3, 7, 1])
        self.assertEqual(len(ties.firsts(np.zeros(0, int), np.zeros(0))), 0)

    def test_nearest_keeps_max_distance_and_the_distances(self):
        segs = np.array([[[0.0, 0.0], [1.0, 0.0]], [[0.0, 5.0], [1.0, 5.0]]])
        tree = shapely.STRtree(shapely.linestrings(segs))
        (pi, ti), d = ties.nearest(tree, ties.segments(segs[:, 0], segs[:, 1]), shapely.points([[0.5, 1.0], [0.5, 20.0]]),
                                   max_distance=2.0, return_distance=True)
        self.assertEqual(pi.tolist(), [0])
        self.assertEqual(ti.tolist(), [0])
        self.assertAlmostEqual(float(d[0]), 1.0)

    def test_empty(self):
        self.assertEqual(len(ties.rank(np.zeros(0))), 0)
        self.assertEqual(len(ties.by_place([])), 0)


if __name__ == "__main__":
    unittest.main()
