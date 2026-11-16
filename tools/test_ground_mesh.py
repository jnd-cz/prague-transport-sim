# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_mesh.py: the file's round trip, the steps' walls, the edge check, the faces of neighbouring squares, and
on every line with data/lineN.ground.*: no T-junction and no crack (every edge used by two triangles or on the box's
border) (#508).

    python -P -E tools/test_ground_mesh.py
"""
import json
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_mesh as gm  # noqa: E402

ROOT = gm.ROOT
Q = gm.Q


def mm(*rows):
    return np.asarray(rows, np.int64)


class File(unittest.TestCase):
    def test_round_trip(self):
        V = mm([0, 0, 200000], [1000, 0, 200100], [1000, -1000, 199900], [0, -1000, 200000], [500, -500, 201234])
        F = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        cls = np.array([0, 1, 1, 3])
        blob, layout = gm.encode(V, F, cls, shapely.box(0, -1, 1, 0))
        W, by = gm.decode(blob, layout)
        self.assertTrue(np.allclose(np.sort(W * Q, axis=0), np.sort(V, axis=0)))
        got = {tuple(sorted(map(tuple, (W[t] * Q).round().astype(int).tolist()))) for c in by for t in by[c]}
        want = {tuple(sorted(map(tuple, V[t].tolist()))) for t in F}
        self.assertEqual(got, want)
        self.assertEqual({c: len(t) for c, t in by.items()}, {"terrain": 1, "survey": 2, "bed": 0, "plot": 1, "wall": 0})


class Steps(unittest.TestCase):
    def square_with_a_step(self):
        # two triangles meeting along x = 1000, the right one 0.1 m higher: its own vertices on the edge
        V = mm([0, 0, 0], [1000, 0, 0], [1000, 1000, 0], [1000, 0, 100], [1000, 1000, 100], [2000, 0, 100])
        F = np.array([[0, 1, 2], [3, 5, 4]])
        return V, F

    def test_a_step_gets_its_wall(self):
        V, F = self.square_with_a_step()
        w = gm.step_walls(V, F)
        self.assertEqual(len(w), 2)
        self.assertTrue(gm.is_wall(V, w).all())

    def test_edges_used_once_found_and_closed_by_the_walls(self):
        V, F = self.square_with_a_step()
        box = shapely.box(0, 0, 2, 1)
        self.assertEqual(gm.edge_check(V, F, box)["used once inside the box"], 2)  # (the open sides, not the step)
        # (a T-junction: a vertex on an edge that the triangle across it does not have)
        V2 = mm([0, 0, 0], [2000, 0, 0], [1000, 1000, 0], [1000, -1000, 0], [500, -500, 0], [500, 0, 0])
        F2 = np.array([[0, 1, 2], [0, 4, 5], [5, 4, 3], [5, 3, 1]])
        r = gm.edge_check(V2, F2, shapely.box(-10, -10, 10, 10))
        self.assertGreaterEqual(r["used once inside the box"], 3)


class Faces(unittest.TestCase):
    def test_neighbouring_squares_share_the_border_vertices(self):
        lines = np.asarray([shapely.box(0.3, 0.3, 1.7, 0.9).boundary, shapely.LineString([(0.1, 0.5), (1.9, 0.45)])], dtype=object)
        tree = shapely.STRtree(lines)
        a = gm.tile_faces((0, 0, 1, 1), tree, lines, None, None)
        b = gm.tile_faces((1, 0, 2, 1), tree, lines, None, None)
        on = lambda fs: {tuple(np.round(p, 9)) for f in fs for p in shapely.get_coordinates(f) if abs(p[0] - 1) < 1e-12}  # noqa: E731
        self.assertEqual(on(a), on(b))
        self.assertAlmostEqual(float(shapely.area(a).sum() + shapely.area(b).sum()), 2.0)

    def test_plane(self):
        tri = np.array([[[0, 0, 1], [1, 0, 2], [0, 1, 3]]], float)
        self.assertAlmostEqual(float(gm.plane(tri, np.array([0.5]), np.array([0.5]))[0]), 2.5)


class Built(unittest.TestCase):
    def test_every_built_line_has_no_t_junction_and_no_crack(self):
        names = [f[4:-len(".ground.bin")] for f in sorted(os.listdir(os.path.join(ROOT, "data"))) if f.endswith(".ground.bin")]
        if not names:
            self.skipTest("no data/lineN.ground.bin: python -P -E tools/ground_mesh.py --line N")
        for ln in names:
            with self.subTest(line=ln):
                layout = json.load(open(os.path.join(ROOT, "data", f"line{ln}.ground.json"), encoding="utf-8"))
                blob = open(os.path.join(ROOT, "data", f"line{ln}.ground.bin"), "rb").read()
                V, by = gm.decode(blob, layout)
                Vq = np.round(V * Q).astype(np.int64)
                F = np.vstack([t for t in by.values() if len(t)])
                L = json.load(open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8"))
                import ground_partition
                r = gm.edge_check(Vq, F, ground_partition.line_box(L))
                self.assertEqual(r["used once inside the box"], 0, f"line {ln}: {r}")
                self.assertEqual(r["used more than twice"], 0, f"line {ln}: {r}")


if __name__ == "__main__":
    unittest.main()
