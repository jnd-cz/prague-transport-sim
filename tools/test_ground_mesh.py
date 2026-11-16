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

    def test_draw_classes_round_trip_with_their_triangles(self):
        V = mm([0, 0, 200000], [1000, 0, 200100], [1000, -1000, 199900], [0, -1000, 200000], [500, -500, 201234])
        F = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        cls = np.array([1, 1, 1, 0])
        draw = np.array(["road", "sidewalk", "road", ""], dtype=object)
        blob, layout = gm.encode(V, F, cls, shapely.box(0, -1, 1, 0), draw)
        W, by, names = gm.decode(blob, layout, draw=True)
        self.assertEqual(sorted(layout["draw"]), ["survey"])
        got = {tuple(sorted(map(tuple, (W[t] * Q).round().astype(int).tolist()))): n for t, n in zip(by["survey"], names["survey"])}
        want = {tuple(sorted(map(tuple, V[F[i]].tolist()))): draw[i] for i in range(3)}
        self.assertEqual(got, want)
        V2, by2 = gm.decode(blob, layout)  # (without asking, as before)
        self.assertEqual(len(by2["survey"]), 3)

    def test_survey_classes_round_trip_beside_the_draw_classes(self):
        # (a bed on the survey: drawn as the bed, its survey class the area's under it)
        V = mm([0, 0, 200000], [1000, 0, 200100], [1000, -1000, 199900], [0, -1000, 200000], [500, -500, 201234])
        F = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
        cls = np.array([1, 2, 1, 0])
        draw = np.array(["green", "embedded", "road", ""], dtype=object)
        area = np.array(["median", "tram", "road", ""], dtype=object)
        blob, layout = gm.encode(V, F, cls, shapely.box(0, -1, 1, 0), draw, area)
        W, by, names, areas = gm.decode(blob, layout, draw=True, area=True)
        self.assertEqual(sorted(layout["area"]), ["bed", "survey"])
        for c in ("survey", "bed"):
            got = {tuple(sorted(map(tuple, (W[t] * Q).round().astype(int).tolist()))): (n, a)
                   for t, n, a in zip(by[c], names[c], areas[c])}
            want = {tuple(sorted(map(tuple, V[F[i]].tolist()))): (draw[i], area[i]) for i in range(3) if cls[i] == gm.CLASS_IDS[c]}
            self.assertEqual(got, want)
        W2, by2, names2 = gm.decode(blob, layout, draw=True)  # (the draw classes alone, as before)
        self.assertEqual(sorted(names2), ["bed", "survey"])


class Lattice(unittest.TestCase):
    def test_lines_on_the_city_grid_clipped_to_the_area(self):
        # (two pieces side by side get lines at the same x: their faces' corners meet on the shared edge)
        g = shapely.box(1, 2, 13, 9)
        L = gm.lattice(g, 5.0)
        xs = sorted({round(c[0], 6) for part in shapely.get_parts(L) for c in shapely.get_coordinates(part) if
                     abs(c[1] - 2) < 1e-9 or abs(c[1] - 9) < 1e-9})
        self.assertEqual(xs, [5.0, 10.0])
        self.assertAlmostEqual(shapely.length(L), 2 * 7 + 1 * 12)  # (x = 5, 10 across 7 m; y = 5 across 12 m)
        self.assertTrue(shapely.box(1, 2, 13, 9).buffer(1e-9).contains(L))
        self.assertIsNone(gm.lattice(shapely.box(1, 1, 4, 4), 5.0))


class Lidar(unittest.TestCase):
    def test_the_city_mesh_under_the_survey_answers_on_its_triangles_planes_only(self):
        # (a lawn on the lidar ground takes the city mesh's height: its triangles under the classes above, "under")
        x, y, z = np.array([0., 10, 10, 0]), np.array([0., 0, 10, 10]), np.array([100., 110, 120, 110])  # z = 100 + x + y
        T = np.array([[0, 1, 2], [0, 2, 3]])
        got = gm.city_at({"x": x, "y": y, "z": z, "T": T, "under": np.array([0, 1])}, np.array([5., 2, 20]), np.array([2., 5, 20]))
        self.assertAlmostEqual(got[0], 107)
        self.assertAlmostEqual(got[1], 107)
        self.assertTrue(np.isnan(got[2]))  # (off the mesh)
        got = gm.city_at({"x": x, "y": y, "z": z, "T": T, "under": np.array([0])}, np.array([2.]), np.array([5.]))
        self.assertTrue(np.isnan(got[0]))  # (a triangle no class lies over is not asked)


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


class Border(unittest.TestCase):
    def test_edges_on_a_polygon_border_are_not_cracks(self):
        # (a diamond of two triangles: its four sides on the border of a diamond-shaped ground, none a crack)
        V = mm([0, -1000, 0], [1000, 0, 0], [0, 1000, 0], [-1000, 0, 0])
        F = np.array([[0, 1, 2], [0, 2, 3]])
        area = shapely.Polygon([(0, -1), (1, 0), (0, 1), (-1, 0)])
        self.assertEqual(gm.edge_check(V, F, area)["used once inside the box"], 0)
        self.assertEqual(gm.edge_check(V, F[:1], area)["used once inside the box"], 1)  # (the diagonal, inside)


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


def level_line(tracks):
    """A line of straight level tracks at 200 m (top of rail), no lift: bed_surface.Beds' input."""
    n = 60
    return {"path": [[0, -10], [0, 110]], "pathExt": {"before": [], "after": []}, "heights": {"step": 2.0},
            "lift": {"step": 2, "unit": 0.001, "v": [0] * n},
            "tracks": [{"p": p, "zs": [200.0] * 62, "bed": {"l": [200] * 62, "r": [200] * 62, "meet": [0] * 62}, **extra}
                       for p, extra in tracks]}


class Rails(unittest.TestCase):
    def test_a_raised_area_across_the_track_is_a_crossing_one_beside_it_is_not(self):
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {})]))
        survey = [{"c": "sidewalk", "g": shapely.box(-5, 40, 5, 45)},  # (across: the axis in it)
                  {"c": "sidewalk", "g": shapely.box(0.5, 60, 4, 70)},  # (beside, over the right rail only)
                  {"c": "road", "g": shapely.box(-5, 80, 5, 85)}]  # (not raised)
        self.assertEqual(gm.crossing_pieces(survey, beds).tolist(), [True, False, False])

    def test_corners_on_the_rails_inside_the_outline(self):
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {}), ([[10, 0], [10, 100]], {"b": 1})]))
        x = np.array([-0.72, 0.72, 0.7205, 0.0, -0.72, 9.28])
        y = np.array([50.0, 50.0, 30.0, 50.0, 95.0, 50.0])
        got, low = gm.on_rails(x, y, beds, shapely.box(-3, 0, 3, 90))
        # (on the left and right rails; 0.5 mm off; between the rails; past the outline; on a bridge's rail)
        self.assertEqual(np.isfinite(got).tolist(), [True, True, True, False, False, False])
        self.assertTrue(np.allclose(got[:3], 200.0 - bed_surface.BED_BELOW))
        self.assertTrue(np.allclose(low[:3], 200.0 - bed_surface.BED_BELOW))

    def test_a_point_off_the_rail_is_judged_at_the_rail(self):
        # (the outline's edge on the right rail: a point 0.5 mm past it lies outside, its foot on the rail on the edge;
        # it counts, at the rail's height)
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {})]))
        got, _ = gm.on_rails(np.array([0.7205]), np.array([50.0]), beds, shapely.box(-3, 0, 0.72, 90))
        self.assertTrue(np.allclose(got, 200.0 - bed_surface.BED_BELOW))

    def test_the_band_takes_what_reaches_a_rail(self):
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {})]))
        outline = shapely.box(-3, 0, 3, 90)
        island = shapely.box(0.5, 40, 4, 50)  # (beside the track, over its right rail)
        hall = shapely.box(-3, 90, 3, 95)  # (a plot where the tracks end: the outline's end)
        far = shapely.box(2, 60, 4, 70)
        band = gm.rail_band(beds, outline, [island, hall, far])
        self.assertAlmostEqual(band.intersection(island).area, 10 * 2 * gm.RAIL_CLEAR, places=4)
        self.assertGreater(band.intersection(hall).area, 0)  # (the rails' ends, rounded)
        self.assertEqual(band.intersection(far).area, 0)
        self.assertTrue(band.contains(shapely.Point(0.72, 45)))
        self.assertFalse(band.contains(shapely.Point(0.80, 45)))

    def test_land_cover_as_the_page_colours_its_terrain(self):
        L = {"green": [{"p": [[0, 0], [10, 0], [10, 10], [0, 10]]}, {"p": [[20, 0], [30, 0], [30, 10], [20, 10]], "t": "wood"}],
             "water": [[[5, 5], [25, 5], [25, 8], [5, 8]]]}
        got = gm.land_cover(L, np.array([2, 22, 15, 40, 8]), np.array([2, 2, 6, 40, 6]))
        self.assertEqual(got.tolist(), ["grass", "wood", "water", "", "water"])

    def test_no_crossing_on_a_bridge(self):
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {"b": 1})]))
        self.assertFalse(gm.crossing_pieces([{"c": "sidewalk", "g": shapely.box(-5, 40, 5, 45)}], beds).any())

    def test_ground_over_a_rail_head_is_found(self):
        import bed_surface
        beds = bed_surface.Beds(level_line([([[0, 0], [0, 100]], {})]))
        top = 200.0
        # (a plane 1 cm under the top of rail, and over y 40..45 a square 0.1 m over it)
        V = mm([-5000, 0, 199990], [5000, 0, 199990], [5000, 100000, 199990], [-5000, 100000, 199990],
               [-5000, 40000, int((top + 0.1) * Q)], [5000, 40000, int((top + 0.1) * Q)], [5000, 45000, int((top + 0.1) * Q)],
               [-5000, 45000, int((top + 0.1) * Q)])
        F = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
        cls = np.array([0, 0, 1, 1])
        r = gm.heads_check(V, F, cls, beds, shapely.box(-3, 0, 3, 100), [("on it", 0, 42), ("away", 0, 80)])
        self.assertGreater(r["under the ground"], 0)
        self.assertGreater(r["on it"]["under the ground"], 0)
        self.assertAlmostEqual(r["on it"]["highest over the top of rail, mm"], 100, delta=1)
        self.assertEqual(r["away"]["under the ground"], 0)
        self.assertEqual(set(r["by the class over them"]), {"survey"})
        self.assertTrue(all(39 <= p[1] <= 46 and abs(p[2] - 10) < 0.2 for p in r["worst places: x, y, cm over, class"]))


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
                r = gm.edge_check(Vq, F, ground_partition.line_area(L))
                self.assertEqual(r["used once inside the box"], 0, f"line {ln}: {r}")
                self.assertEqual(r["used more than twice"], 0, f"line {ln}: {r}")


if __name__ == "__main__":
    unittest.main()
