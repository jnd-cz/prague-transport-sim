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

    def test_a_step_brought_down_to_one_height_is_one_vertex(self):
        """fit_mouths can bring both vertices of a step to one height: weld_coincident makes them one and drops the wall
        between them, so the file decodes to what was built."""
        V = mm([0, 0, 200000], [1000, 0, 200000], [1000, 0, 200000], [0, -1000, 200000], [1000, -1000, 200000])
        F = np.array([[0, 3, 1], [3, 4, 2], [1, 3, 2]])  # (the last: the wall between the two vertices at (1000, 0))
        built = {"V": V, "F": F, "cls": np.array([1, 1, 4]), "draw": np.array(["a", "b", "w"], dtype=object),
                 "area": np.array(["road", "road", ""], dtype=object)}
        self.assertEqual(gm.weld_coincident(built), 1)
        self.assertEqual(len(built["V"]), 4)
        self.assertEqual(built["cls"].tolist(), [1, 1])
        self.assertEqual(built["draw"].tolist(), ["a", "b"])
        W = built["V"][built["F"]]
        self.assertEqual(sorted(map(tuple, W[1].tolist())), [(0, -1000, 200000), (1000, -1000, 200000), (1000, 0, 200000)])
        self.assertEqual(gm.weld_coincident(built), 0)

    def test_tiles_round_trip_and_weld_on_their_border(self):
        # (x 306 m is the border between tiles e-1486 and e-1485, #30: two triangles either side share its two vertices)
        V = mm([300000, 0, 200000], [306000, 0, 200100], [306000, -1000, 199900], [300000, -1000, 200000],
               [312000, 0, 200300], [312000, -1000, 200200])
        F = np.array([[0, 1, 2], [0, 2, 3], [1, 4, 5], [1, 5, 2]])
        cls = np.array([0, 1, 1, 0])
        draw = np.array(["grass", "road", "sidewalk", ""], dtype=object)
        blob, layout = gm.encode_tiles(V, F, cls, draw)
        self.assertEqual([t["name"] for t in layout["tiles"]], ["e-1486_n-2087", "e-1485_n-2087"])
        self.assertEqual(layout["vertices"], 8)  # (the border's two in both tiles)
        self.assertEqual(layout["draw"], {"survey": ["road", "sidewalk"], "terrain": ["grass"]})  # ("": unnamed)
        W, by, names = gm.decode(blob, layout, draw=True)
        self.assertEqual(len(W), 6)  # (welded)
        got = {tuple(sorted(map(tuple, (W[t] * Q).round().astype(int).tolist()))): n
               for c in by for t, n in zip(by[c], names.get(c, [""] * len(by[c])))}
        want = {tuple(sorted(map(tuple, V[F[i]].tolist()))): draw[i] for i in range(4)}
        self.assertEqual(got, want)

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
    def test_lines_on_the_tiles_grid_clipped_to_the_area(self):
        # (two pieces side by side get lines at the same x: their faces' corners meet on the shared edge; the grid is
        # S-JTSK's, as the tiles' (#30): x = 1 is E -742,805, y = 4 is N -1,043,020)
        g = shapely.box(2, 0, 14, 8)
        L = gm.lattice(g, 5.0)
        xs = sorted({round(c[0], 6) for part in shapely.get_parts(L) for c in shapely.get_coordinates(part) if
                     abs(c[1] - 0) < 1e-9 or abs(c[1] - 8) < 1e-9})
        self.assertEqual(xs, [6.0, 11.0])
        self.assertAlmostEqual(shapely.length(L), 2 * 8 + 1 * 12)  # (x = 6, 11 across 8 m; y = 4 across 12 m)
        self.assertTrue(g.buffer(1e-9).contains(L))
        self.assertIsNone(gm.lattice(shapely.box(7, 5, 10, 8), 5.0))

    def test_a_cell_the_surface_bends_in_is_cut_finer_and_no_other(self):
        """#697: three 5 m cells in a row (x 1-6, 6-11, 11-16), a wall of 8 m in the middle one."""
        g = shapely.box(1, 4, 16, 9)
        got = gm.bends(g, lambda px, py: np.where(px < 8.5, 8.0, 0.0), 5.0)
        xy = shapely.get_coordinates(got)
        self.assertGreaterEqual(xy[:, 0].min(), 6.0)
        self.assertLessEqual(xy[:, 0].max(), 11.0)
        fine = int(round(5.0 / gm.LATTICE_FINE)) - 1
        self.assertAlmostEqual(shapely.length(got), 2 * fine * 5.0)  # (lines along and across the cell, on the grid)
        self.assertEqual(sorted({round(v, 6) for v in xy[:, 0]} - {6.0, 11.0}), [6.0 + gm.LATTICE_FINE * k for k in range(1, fine + 1)])

    def test_a_plane_and_a_roads_crown_cut_nothing(self):
        g = shapely.box(1, 4, 16, 9)
        self.assertIsNone(gm.bends(g, lambda px, py: 200 + 0.03 * px + 0.01 * py, 5.0))
        self.assertIsNone(gm.bends(g, lambda px, py: 200 - 0.025 * np.abs(px - 8.5), 5.0))  # (a crown: 2.5 % each way)
        self.assertIsNone(gm.bends(shapely.box(7, 5, 10, 8), lambda px, py: np.full(len(px), np.nan), 5.0))  # (no surface)


class Weirs(unittest.TestCase):
    def test_a_corner_on_a_cut_is_seen_square_off_it_on_its_triangles_side(self):
        cut = shapely.MultiLineString([[(0, 0), (10, 0)], [(20, -5), (20, 5)]])
        x, y = gm.off_cuts(np.array([5.0, 5.0, 20.0]), np.array([0.0, 0.0, 1.0]), np.array([4.0, 9.0, 25.0]),
                           np.array([3.0, -0.5, 0.0]), cut, 3.0)
        self.assertEqual(np.round(x, 6).tolist(), [5.0, 5.0, 23.0])
        self.assertEqual(np.round(y, 6).tolist(), [3.0, -3.0, 1.0])


class LoweredKerbs(unittest.TestCase):
    """#630: a kerb corner at a crossing's lowered stretch (tools/kerbs.py, #303) stands its height over the road."""

    def test_the_stretch_its_ramps_and_the_plain_kerb_beyond(self):
        low = np.array([[0.0, 0.0, 0.02]])
        x = np.array([0.0, 1.9, 2.4, 3.0, 10.0])
        y = np.zeros(5)
        z = gm.lowered_heights(x, y, np.full(5, 100.12), np.full(5, 100.0), low, 4.0, 0.125)
        # (within 2 m the stretch's 2 cm; then 1:8 along the kerb: 0.4 m past it 7 cm, 1 m past it the plain 12 cm)
        self.assertEqual(np.round(z - 100.0, 3).tolist(), [0.02, 0.02, 0.07, 0.12, 0.12])

    def test_a_flush_kerb_and_the_lowest_of_two(self):
        low = np.array([[0.0, 0.0, 0.0], [3.0, 0.0, 0.02]])
        z = gm.lowered_heights(np.array([2.2]), np.array([0.0]), np.array([100.12]), np.array([100.0]), low, 4.0, 0.125)
        self.assertAlmostEqual(float(z[0]) - 100.0, 0.02, places=6)

    def test_the_rule_read_from_the_survey(self):
        D = {"provenance": {"lists": {"areas": {"checks": {"kerbs": {"lowered": {
            "rule": {"kerb": 0.02, "width": 4.0, "ramp": 0.125},
            "stretches": [{"x": 1, "y": 2, "c": "sidewalk", "h": 0.02}, {"x": 3, "y": 4, "c": "sidewalk", "h": None},
                          {"x": 5, "y": 6, "c": "platform", "h": 0.02}]}}}}}}}
        low, w, r = gm.lowered_kerbs(D)
        self.assertEqual(low.tolist(), [[1.0, 2.0, 0.02]])
        self.assertEqual((w, r), (4.0, 0.125))
        self.assertEqual(len(gm.lowered_kerbs({})[0]), 0)


class Stairs(unittest.TestCase):
    # (Krejcárek's stairs, line 37 survey area 1339: the foot at 228.56-228.82, the top at 229.75-229.82)
    KREJCAREK = {"c": "stairs", "l": 0, "r": [[3925.7, 328.8, 228.82], [3926.8, 327.2, 228.56], [3928.7, 328.4, 229.82],
                                               [3928.8, 328.5, 229.76], [3927.8, 330.1, 229.75]]}

    def test_one_flight_is_its_plane_foot_to_top(self):
        """#447: the outline's heights triangulated strayed 0.39 m from the straight line between foot and top."""
        s = gm.SurveySurface({"areas": [self.KREJCAREK]}, [0])
        self.assertIn(0, s.flights)
        t = np.linspace(0, 1, 9)
        z = s.at(0, 3926.25 + 2.0 * t, 328.0 + 1.25 * t)
        self.assertLess(float(np.abs(z - (z[0] + (z[-1] - z[0]) * t)).max()), 1e-9)
        self.assertAlmostEqual(float(z[-1] - z[0]), 1.09, delta=0.1)

    def test_stairs_with_a_turn_keep_their_outline(self):
        turn = {"c": "stairs", "l": 0, "r": [[0, 0, 200.0], [2, 0, 200.0], [2, 3, 201.5], [5, 3, 203.0], [5, 5, 203.0], [0, 5, 201.5]]}
        self.assertIsNone(gm.flight(turn))
        s = gm.SurveySurface({"areas": [turn, {"c": "paved", "l": 0, "r": [[0, 0, 1.0], [1, 0, 1.0], [0, 1, 2.0]]}]}, [0, 1])
        self.assertEqual(s.flights, {})
        self.assertAlmostEqual(float(s.at(0, np.array([1.0]), np.array([0.0]))[0]), 200.0)


class Walls(unittest.TestCase):
    def test_a_street_corner_on_a_wall_takes_its_height_there(self):
        # (#653: a wall's top rising 229.6 -> 230.0 m along x = 0..4, its foot at 228.5, top and foot at one place at
        # x = 4. A sidewalk corner on its top 0.12 m under it takes it, between its ends; one where the wall holds its top
        # and its foot, the nearer; one 2 m off any, or off the outline, keeps its own; a lawn corner is not moved, nor one
        # on another level's wall)
        wall = {"c": "wall", "l": 0, "r": [[0, 0, 229.6], [4, 0, 230.0], [4, 0, 228.5], [4, 0.3, 228.5], [0, 0.3, 228.5]]}
        upper = {"c": "wall", "l": 1, "r": [[0, 1, 300.0], [4, 1, 300.0], [4, 1.3, 300.0]]}
        D = {"areas": [wall, upper]}
        x = np.array([2.0, 0.0, 4.0, 2.0, 2.0, 2.0, 2.0])
        y = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 1.0])
        z = np.array([229.68, 229.50, 228.70, 227.60, 229.70, 229.75, 299.90])
        street = np.array([True, True, True, True, True, False, True])
        got = gm.snap_to_walls(D, x, y, z, street)
        self.assertEqual(np.round(got, 3).tolist(), [229.8, 229.6, 228.5, 227.6, 229.7, 229.75, 299.9])


    def test_a_walls_face_runs_straight_across_between_its_sides(self):
        # (#653: a battered wall 1 m across, its foot rising 228 -> 229 m along 10 m, its top at 230: across it between
        # the two, on its outline the outline's)
        a = {"c": "wall", "l": 0, "r": [[0, 0, 228.0], [10, 0, 229.0], [10, 1, 230.0], [0, 1, 230.0]]}
        got = gm.across_outline(gm.ring_segments(a), np.array([5.0, 5.0, 5.0, 2.0, 0.0]), np.array([0.0, 0.5, 1.0, 0.25, 0.5]))
        self.assertEqual(np.round(got, 3).tolist(), [228.5, 229.25, 230.0, 228.65, 229.0])

    def test_the_weld_ignores_the_corners_order(self):
        # (#664: two road areas of one rank meet at (0, 0) with their own surfaces, 193.49 and 193.32 m (line 22 by a
        # bridge's track, (-1114, -537)): the point takes the middle in either order; a terrain corner under them 0.6 m off
        # is a wall and keeps its own, one 0.2 m off takes the top's; a raised corner of the same rank beside a plain one
        # takes the middle too; the two sides of a weir keep their levels)
        cx = np.array([0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 2.0, 2.0])
        cy = np.zeros(9)
        zc = np.array([193.49, 193.32, 194.0, 193.6, 10.0, 10.2, 10.0, 5.0, 4.0])
        prio = np.array([2.02, 2.02, 3.0, 3.0, 2.03, 2.03, 3.0, 2.95, 2.95])
        kind = np.array(["survey", "survey", "terrain", "terrain", "survey", "raised", "terrain", "pool", "pool"], dtype=object)
        zf, steps, n = gm.weld(cx, cy, zc, prio, kind)
        self.assertEqual(n, 3)
        self.assertEqual(np.round(zf, 3).tolist(), [193.405, 193.405, 194.0, 193.405, 10.1, 10.1, 10.1, 5.0, 4.0])
        o = np.array([1, 0, 3, 2, 6, 5, 4, 8, 7])
        zf2, _, _ = gm.weld(cx[o], cy[o], zc[o], prio[o], kind[o])
        self.assertEqual(np.round(zf2, 3).tolist(), np.round(zf[o], 3).tolist())

    def test_a_corner_on_the_lidar_yields_to_a_surveyed_one_of_its_rank(self):
        # (#664: a paved yard on the lidar (`g`) and one on its own outline share (0, 0), 0.5 m apart (line 37's pairs, p50
        # 0.48 m): the surveyed edge holds, in either order, and the report counts the lidar's corner; a rank above still
        # wins over both)
        self.assertLess(gm.YIELD, 0.005)  # (under the ranks' 0.01 steps: a yielding corner never passes another rank)
        cx, cy = np.array([0.0, 0.0, 1.0, 1.0]), np.zeros(4)
        zc = np.array([250.5, 250.0, 250.5, 249.0])
        p = 2.0 + (10 - 2) / 100
        prio = np.array([p + gm.YIELD, p, p + gm.YIELD, p - 0.01])
        kind = np.array(["survey"] * 4, dtype=object)
        label = np.array(["lidar", "survey", "lidar", "survey"], dtype=object)
        zf, steps, _ = gm.weld(cx, cy, zc, prio, kind, label)
        self.assertEqual(np.round(zf, 3).tolist(), [250.0, 250.0, 249.0, 249.0])
        self.assertEqual(steps["ties"]["lidar corners yielded"], {"over 1 cm": 1, "over 5 cm": 1, "over 20 cm": 1})
        o = np.array([1, 0, 3, 2])
        zf2, _, _ = gm.weld(cx[o], cy[o], zc[o], prio[o], kind[o], label[o])
        self.assertEqual(np.round(zf2, 3).tolist(), np.round(zf[o], 3).tolist())

    def test_a_lidar_corner_whose_outline_stands_apart_keeps_its_height(self):
        # (#664: line 37 (3400, 9): the lidar 243.36 m, its area's own outline 248.28, the surveyed edge 248.16: one edge,
        # welded; (4430, 1469): the lidar 199.94, its outline 199.65, the edge 205.43: two levels, a step)
        cx, cy = np.array([0.0, 0.0, 1.0, 1.0]), np.zeros(4)
        p = 2.0 + (10 - 2) / 100
        zc = np.array([243.36, 248.16, 199.94, 205.43])
        prio = np.array([p + gm.YIELD, p, p + gm.YIELD, p])
        kind = np.array(["survey"] * 4, dtype=object)
        label = np.array(["lidar", "survey", "lidar", "survey"], dtype=object)
        zown = np.array([248.28, np.nan, 199.65, np.nan])
        zf, steps, _ = gm.weld(cx, cy, zc, prio, kind, label, zown)
        self.assertEqual(np.round(zf, 3).tolist(), [248.16, 248.16, 199.94, 205.43])
        self.assertEqual(steps["ties"]["lidar apart"], 1)

    def test_the_water_keeps_its_level_under_a_bank_of_its_rank(self):
        # (#664: survey water at OSM's level, 184.68 m, and its quay of one rank, 189.97 m, share a point (line 17's Vltava
        # by (-472, 324)): the quay keeps its top, the water its level, a step for the wall; the middle stood at 187.33)
        cx, cy = np.zeros(3), np.zeros(3)
        p = 2.0 + (10 - 2) / 100
        zc = np.array([184.68, 189.97, 189.5])
        prio = np.array([p + gm.YIELD, p, 3.0])
        kind = np.array(["pool", "survey", "terrain"], dtype=object)
        zf, steps, _ = gm.weld(cx, cy, zc, prio, kind)
        self.assertEqual(np.round(zf, 3).tolist(), [184.68, 189.97, 189.97])
        self.assertEqual(steps["ties"]["pool corners yielded"]["over 20 cm"], 1)

    def test_equal_rank_survey_heights_apart_are_a_step(self):
        # (#664: line 37's parking areas #3121 and #3130 share (6459.6, 827.4) at 203.19 and 202.06 m: each keeps its own,
        # and the corners under them take the nearer, a terrain one 0.44 m off welded, one 0.6 m off kept (STEP's wall);
        # two 0.15 m apart take the middle; a bed's two heights are not the survey's and take theirs as before)
        cx = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 2.0, 2.0])
        cy = np.zeros(9)
        p = 2.0 + (10 - 2) / 100
        zc = np.array([203.19, 202.06, 202.5, 202.1, 203.8, 10.0, 10.15, 5.0, 5.3])
        prio = np.array([p, p, 3.0, p + 0.01, 3.0, p, p, 1.0, 1.0])
        kind = np.array(["survey", "survey", "terrain", "survey", "terrain", "survey", "survey", "bed", "bed"], dtype=object)
        zf, steps, _ = gm.weld(cx, cy, zc, prio, kind)
        self.assertEqual(np.round(zf, 3).tolist(), [203.19, 202.06, 202.06, 202.06, 203.8, 10.075, 10.075, 5.15, 5.15])
        self.assertEqual(steps["ties"]["survey steps"], 1)
        o = np.array([1, 0, 4, 3, 2, 6, 5, 8, 7])
        zf2, _, _ = gm.weld(cx[o], cy[o], zc[o], prio[o], kind[o])
        self.assertEqual(np.round(zf2, 3).tolist(), np.round(zf[o], 3).tolist())


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


class MeetRaised(unittest.TestCase):
    """A yard x 0-10 at 100 m; a sidewalk at x < 0 sharing its corners at x 0; a road at x > 10 sharing those at x 10."""
    def corners(self, side):
        # (sc, x, y, zs; sa: the areas, for the test of two yards)
        ys = np.arange(0, 11, 1.0)
        x = np.concatenate([np.zeros(11), np.full(11, 10.0), np.full(11, 1.0), np.full(11, 2.0), np.full(11, 5.0),
                            np.zeros(11), np.full(11, 10.0)])
        y = np.tile(ys, 7)
        sc = np.array(["paved"] * 55 + ["sidewalk"] * 11 + ["road"] * 11)
        sa = np.array([0] * 55 + [1] * 11 + [2] * 11)
        zs = np.concatenate([np.full(55, 100.0), np.full(11, 100.0 + side), np.full(11, 99.9)])
        return sc, sa, x, y, zs

    def test_the_yard_meets_the_sidewalk_and_fades_inward(self):
        sc, sa, x, y, zs = self.corners(0.2)
        z, s = gm.meet_raised(sc, x, y, zs)
        np.testing.assert_allclose(z[:11], 100.2)  # (on the edge: the sidewalk's)
        self.assertTrue(np.all(z[22:33] < 100.2) and np.all(z[22:33] > 100.0))  # (1 m in: part of it)
        np.testing.assert_allclose(z[44:55], 100.0)  # (5 m in: none)
        np.testing.assert_allclose(z[11:22], 100.0)  # (at the road: pinned)
        np.testing.assert_allclose(z[55:], zs[55:])  # (the others left)

    def test_a_larger_step_stands(self):
        sc, sa, x, y, zs = self.corners(0.5)
        z, s = gm.meet_raised(sc, x, y, zs)
        np.testing.assert_allclose(z, zs)

    def test_two_yards_on_a_shared_edge_shift_alike(self):
        # (the corners 1 m in shared by a second yard: each of the two corners at a place shifts alike)
        sc, sa, x, y, zs = self.corners(0.2)
        z, _ = gm.meet_raised(np.concatenate([sc, sc[22:33]]), np.concatenate([x, x[22:33]]), np.concatenate([y, y[22:33]]),
                              np.concatenate([zs, zs[22:33]]))
        np.testing.assert_allclose(z[-11:], z[22:33])


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

    def test_the_wall_faces_down_the_step(self):
        V, F = self.square_with_a_step()
        for w in gm.step_walls(V, F):
            P = V[w].astype(float)
            n = np.cross(P[1] - P[0], P[2] - P[0])
            self.assertLess(n[0], 0)  # (the lower triangle is at x < 1000)

    def test_every_triangle_faces_up(self):
        V, F = self.square_with_a_step()
        F = np.vstack([F, F[:, ::-1]])
        P = V[gm.face_up(V, F)].astype(float)
        self.assertTrue((np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])[:, 2] > 0).all())
        w = gm.step_walls(V, F[:2])
        self.assertTrue((gm.face_up(V, w) == w).all())  # (an upright one as it is)

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
                # (every triangle faces up: the page's normals average over its neighbours, gm.face_up)
                flat = F[~gm.is_wall(Vq, F)]
                P = Vq[flat].astype(float)
                down = int((np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])[:, 2] < 0).sum())
                self.assertEqual(down, 0, f"line {ln}: {down:,} triangles face down")


if __name__ == "__main__":
    unittest.main()
