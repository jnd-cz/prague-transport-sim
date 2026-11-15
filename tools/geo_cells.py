# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fixed lattice of cells over the city frame (#326): the feature services' answers are asked and named per cell, so
an answer always stands for the same place, a small change of a route asks for few new files, and lines share them.
"""
import math

SIZE = 500.0   # m, a cell's side
STEP = 50.0    # m: a route is read this often; well under the margin, so no cell within the margin is passed over


def cells(path, margin, size=SIZE):
    """Sorted [(ix, iy)]: the cells within `margin` m of a polyline [(x, y), ...], read as squares around its points."""
    out = set()

    def add(x, y):
        for ix in range(math.floor((x - margin) / size), math.floor((x + margin) / size) + 1):
            for iy in range(math.floor((y - margin) / size), math.floor((y + margin) / size) + 1):
                out.add((ix, iy))
    for a, b in zip(path, path[1:]):
        d = math.dist(a[:2], b[:2])
        n = max(1, math.ceil(d / STEP))
        for k in range(n + 1):
            add(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
    return sorted(out)


def bounds(ix, iy, size=SIZE):
    """(x0, y0, x1, y1) of a cell in city metres."""
    return ix * size, iy * size, (ix + 1) * size, (iy + 1) * size
