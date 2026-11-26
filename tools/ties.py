# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ties broken by place (#812). An STRtree's hits come in the order of its traversal, not of its geometries, and
query_nearest(all_matches=False) gives the first of several equally near in that order. The traversal moves with every
geometry in the tree, so a rule that takes the first of equally near candidates as the tree hands them over picks by
what lies anywhere in the tree: a tile's ground came out another way when its box was larger. At lattice-cell (line 23,
the middle tile's ground built with one ring of tiles and with two) a sidewalk's corner on the vertex two wall edges
share, 0 m from both, read the surface on one side or the other, 230.21 or 230.37 m (own_side), and a corner on the lidar
0.343 m from two stretches over one wall, laid in opposite directions, took 228.78 or 228.81 m (hold_at_walls).
Here candidates are ranked by where they lie, and a tie goes to the first by that rank, whatever else the tree holds."""
import numpy as np
import shapely


def rank(*keys):
    """Each row's place in the order of keys (arrays of one length, the first the most significant): 0 to n-1, rows
    equal in every key in the order given."""
    n = len(keys[0]) if keys else 0
    if not n:
        return np.zeros(0, int)
    o = np.lexsort([np.asarray(k) for k in keys[::-1]])
    r = np.empty(n, int)
    r[o] = np.arange(n)
    return r


def segments(a, b, *keys):
    """rank of segments a -> b ((n, 2) or (n, 3) arrays) by their ends' coordinates, then by keys (what tells two
    segments over one another apart: their heights)."""
    a, b = np.asarray(a, float).reshape(len(a), -1), np.asarray(b, float).reshape(len(b), -1)
    return rank(a[:, 0], a[:, 1], b[:, 0], b[:, 1], *keys)


def by_place(geoms, *keys):
    """rank of geometries by their bounds, their first point (a segment laid the other way round), length and area, then
    by keys."""
    g = np.asarray(geoms, object).ravel()
    if not len(g):
        return np.zeros(0, int)
    b = shapely.bounds(g).reshape(-1, 4)
    xy, ix = shapely.get_coordinates(g, return_index=True)
    first = np.full((len(g), 2), np.nan)
    if len(ix):
        u, at = np.unique(ix, return_index=True)
        first[u] = xy[at]
    return rank(b[:, 0], b[:, 1], b[:, 2], b[:, 3], first[:, 0], first[:, 1], shapely.length(g), shapely.area(g), *keys)


def across(px, py, a, b):
    """The distance of points (px, py) from the lines through segments a -> b (unclamped: past a segment's end too).
    Of wall edges equally near a corner (both at the vertex they share), the one whose line runs nearest the corner's
    triangle is the edge the triangle lies along: the tie a rule settles by meaning before it falls back on place. Two
    stretches meeting at a stairwell's corner by street-over-an-underpass (line 17 (-1446.6, -9111.2)) are both 0.461 m
    from a corner, its triangle 0.195 m from one's line and 0.44 m from the other's, whose first level is a spike
    (216.76 m against 210.5 m along it); taken by place the corner stood 4.9 m over the stairwell floor (#812)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    e = b[:, :2] - a[:, :2]
    n = np.hypot(e[:, 0], e[:, 1])
    cr = np.abs(e[:, 0] * (np.asarray(py, float) - a[:, 1]) - e[:, 1] * (np.asarray(px, float) - a[:, 0]))
    return np.where(n > 1e-12, cr / np.maximum(n, 1e-12), np.hypot(np.asarray(px, float) - a[:, 0], np.asarray(py, float) - a[:, 1]))


def firsts(pi, *keys):
    """Of pairs (pi: the point of each), per point the first by keys (np.lexsort's order: the last key the most
    significant): the pairs' indices, one per point, in the order of the points."""
    pi = np.asarray(pi)
    if not len(pi):
        return np.zeros(0, int)
    o = np.lexsort((*keys, pi))
    return o[np.r_[True, pi[o][1:] != pi[o][:-1]]]


def nearest(tree, rk, pts, max_distance=None, return_distance=False):
    """query_nearest(all_matches=False) as it should be: per point the tree's nearest geometry, of several as near the
    first by rk (the rank of the tree's geometries, rank / segments / by_place). (point indices, tree indices), and the
    distances with return_distance."""
    kw = {} if max_distance is None else {"max_distance": max_distance}
    (pi, ti), d = tree.query_nearest(pts, all_matches=True, return_distance=True, **kw)
    k = firsts(pi, np.asarray(rk)[ti])
    return ((pi[k], ti[k]), d[k]) if return_distance else (pi[k], ti[k])
