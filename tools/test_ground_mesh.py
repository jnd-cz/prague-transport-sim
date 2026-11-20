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
        # x = 4. A sidewalk corner on its top 0.10 m under it takes it; one 0.12 m under it does not: the wall stands over
        # it, a low wall (#776: the platform climbed the cheek walls at Krejcárek's ramp); one where the wall holds its
        # top and its foot, the nearer, down to it; one 2 m off any, or off the outline, keeps its own; a lawn corner is
        # not moved, nor one on another level's wall)
        wall = {"c": "wall", "l": 0, "r": [[0, 0, 229.6], [4, 0, 230.0], [4, 0, 228.5], [4, 0.3, 228.5], [0, 0.3, 228.5]]}
        upper = {"c": "wall", "l": 1, "r": [[0, 1, 300.0], [4, 1, 300.0], [4, 1.3, 300.0]]}
        D = {"areas": [wall, upper]}
        x = np.array([2.0, 0.0, 4.0, 2.0, 2.0, 2.0, 2.0])
        y = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 1.0])
        z = np.array([229.68, 229.50, 228.70, 227.60, 229.70, 229.75, 299.90])
        street = np.array([True, True, True, True, True, False, True])
        got = gm.snap_to_walls(D, x, y, z, street)
        self.assertEqual(np.round(got, 3).tolist(), [229.68, 229.6, 228.5, 227.6, 229.7, 229.75, 299.9])


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

    def test_a_lidar_corner_a_wall_holds_keeps_the_walls_level(self):
        # (#770: line 37 (3389.13, -10.60), the cutting's wall north of Ohrada: the paved ground's corner on the wall's
        # line, held at the foot's 244.59 m; its area's own outline there 248.44 (the area runs behind the wall's top
        # too); the top strip's corner 248.03. Not held it is one edge, welded, as above)
        cx, cy = np.array([0.0, 0.0, 1.0, 1.0]), np.zeros(4)
        p = 2.0 + (10 - 2) / 100
        zc = np.array([244.59, 248.03, 244.59, 248.03])
        prio = np.array([p + gm.YIELD, p, p + gm.YIELD, p])
        kind = np.array(["survey"] * 4, dtype=object)
        label = np.array(["lidar", "survey", "lidar", "survey"], dtype=object)
        zown = np.array([248.44, np.nan, 248.44, np.nan])
        held = np.array([True, False, False, False])
        zf, steps, _ = gm.weld(cx, cy, zc, prio, kind, label, zown, held)
        self.assertEqual(np.round(zf, 3).tolist(), [244.59, 248.03, 248.03, 248.03])
        self.assertEqual(steps["ties"]["lidar apart"], 1)
        # (#771: a lawn, of a lower rank than the paved strip it stands at the foot of: line 17 (-724.65, -2546.51))
        prio = np.array([2.0 + (10 - 0) / 100 + gm.YIELD, p, 2.0 + (10 - 0) / 100 + gm.YIELD, p])
        zf, steps, _ = gm.weld(cx, cy, np.array([193.68, 197.88, 193.68, 197.88]), prio, kind, label,
                               np.array([197.16, np.nan, 197.16, np.nan]), held)
        self.assertEqual(np.round(zf, 3).tolist(), [193.68, 197.88, 197.88, 197.88])

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

    def test_a_wall_area_whose_sides_part_stands_upright(self):
        # (#697: Chotkova's road wall, line 23 area 842: its foot's side at 205.3 m, its top's 1.7 m behind at 208.5)
        segs = gm.ring_segments({"r": [[0, 0, 205.3], [30, 0, 205.3], [30, 1.7, 208.5], [0, 1.7, 208.5]]})
        x = np.full(4, 15.0)
        y = np.array([0.0, 0.85, 1.7, 0.0])  # (on the foot's outline, inside, on the top's outline, on the foot's again)
        z, lifted = gm.wall_face(segs, x, y, x + 0.3, np.array([0.4, 0.9, 1.3, 0.4]))
        self.assertTrue(np.allclose(z, 208.5))  # (the top level right across, the foot's corners lifted to it)
        self.assertEqual(lifted.tolist(), [True, False, False, True])
        # (a low wall, its sides 0.5 m apart in height: between them as before, #653)
        low = gm.ring_segments({"r": [[0, 0, 205.3], [30, 0, 205.3], [30, 1.7, 205.8], [0, 1.7, 205.8]]})
        z, lifted = gm.wall_face(low, x, y, x + 0.3, np.array([0.4, 0.9, 1.3, 0.4]))
        self.assertTrue(np.allclose(z, [205.3, 205.55, 205.8, 205.3], atol=0.02))
        self.assertFalse(lifted.any())
        # (a bastion's battered face, 5 m across and 16.5 m up, line 23 area 860: between its sides too)
        wide = gm.ring_segments({"r": [[0, 0, 307.8], [60, 0, 307.8], [60, 5, 324.3], [0, 5, 324.3]]})
        z, lifted = gm.wall_face(wide, np.full(2, 30.0), np.array([0.0, 2.5]), np.full(2, 30.3), np.array([0.4, 2.8]))
        self.assertTrue(np.allclose(z, [307.8, 316.05], atol=0.1))
        self.assertFalse(lifted.any())

    def test_a_paved_strip_that_climbs_a_wall_is_a_wall(self):
        # (#697: a parapet along a path surveyed as paved, 0.4 m across, its foot's side 1.5 m under its top's)
        strip = [[0, 0, 186.0], [40, 0, 186.2], [40, 0.4, 187.7], [0, 0.4, 187.5]]
        self.assertTrue(gm.wall_like({"c": "wall", "r": strip}))
        self.assertTrue(gm.wall_like({"c": "paved", "r": strip}))
        self.assertFalse(gm.wall_like({"c": "paved", "g": 1, "r": strip}))  # (on the lidar: the city mesh's)
        self.assertFalse(gm.wall_like({"c": "paved", "r": [[0, 0, 186.0], [40, 0, 186.2], [40, 0.4, 186.3], [0, 0.4, 186.1]]}))
        yard = [[0, 0, 186.0], [40, 0, 186.2], [40, 0.4, 187.7], [40, 12, 187.7], [0, 12, 187.5]]  # (a yard: 12 m across)
        self.assertFalse(gm.wall_like({"c": "paved", "r": yard}))
        self.assertFalse(gm.wall_like({"c": "green", "r": strip}))

    def test_a_lifted_wall_corner_is_welded_apart_from_the_ground_at_its_foot(self):
        cx, cy = np.zeros(4), np.zeros(4)
        zc = np.array([208.5, 208.5, 205.3, 205.36])  # (two wall faces' corners at the top; the road and a lawn at the foot)
        prio = np.array([2.05, 2.05, 2.02, 2.09])
        kind = np.array(["survey"] * 4, dtype=object)
        zf, _, _ = gm.weld(cx, cy, zc, prio, kind)
        self.assertEqual(np.round(zf, 2).tolist(), [205.3, 205.3, 205.3, 205.3])
        zf, _, _ = gm.weld(cx, cy, zc, prio, kind, apart=np.array([True, True, False, False]))
        self.assertEqual(np.round(zf, 2).tolist(), [208.5, 208.5, 205.3, 205.3])

    def test_step_faces_on_a_wall_line(self):
        V = np.array([[0, 0, 0], [1000, 0, 0], [1000, 0, 3000], [0, 5000, 0], [1000, 5000, 0], [1000, 5000, 2000]])
        W = np.array([[0, 1, 2], [3, 4, 5]])
        self.assertEqual(gm.on_lines(V, W, [np.array([[-2.0, 0.0], [4.0, 0.0]])]).tolist(), [True, False])

    def test_an_outline_that_climbs_a_wall_is_on_two_levels(self):
        # (#761: the Modřany abutment's sidewalk, area 7214 of line 17: 198.48 -> 200.80 m in 0.49 m of its outline)
        street = {"r": [[0, 0, 198.0], [10, 0, 198.15], [10, 3, 198.3], [0, 3, 198.1]]}  # (a kerb's 15 cm is no wall)
        self.assertFalse(gm.climbs(street))
        two = {"r": [[0, 0, 198.15], [1.1, 0, 198.48], [1.15, 0.49, 200.8], [10, 0.5, 200.4], [10, 3, 204.0], [0, 3, 201.7]]}
        self.assertTrue(gm.climbs(two))
        self.assertTrue(gm.climbs({"r": street["r"], "h": [[[4, 1, 198.1], [4.3, 1, 199.4], [4.3, 2, 199.4]]]}))  # (a hole's outline too)
        self.assertFalse(gm.climbs({"r": [[0, 0, None], [0.5, 0, 203.0], [5, 4, 203.0]]}))  # (a point without a height)
        self.assertFalse(gm.climbs({"r": [[0, 0, 198.0], [6, 0, 201.0], [6, 5, 201.0]]}))  # (a ramp: 3 m in 6 m)

    def test_the_terrains_two_sides_of_a_held_wall_keep_their_levels(self):
        # (#697: two terrain corners at one point on a surveyed wall line, held at its sides' levels, took the middle;
        # unheld ones still do)
        cx, cy = np.array([0.0, 0.0, 1.0, 1.0]), np.zeros(4)
        zc = np.array([208.6, 211.6, 208.6, 211.6])
        prio, kind = np.full(4, 3.0), np.array(["terrain"] * 4, dtype=object)
        zf, _, _ = gm.weld(cx, cy, zc, prio, kind, held=np.array([True, True, False, False]))
        self.assertEqual(np.round(zf, 3).tolist(), [208.6, 211.6, 210.1, 210.1])


class Terraces(unittest.TestCase):
    """#663: a raised courtyard, line 37 (7590, 743): beds 2.1-3.7 m over the lidar inside walls as high."""

    @staticmethod
    def box(x0, y0, x1, y1, z):
        return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]

    def setUp(self):
        b = self.box
        self.D = {"areas": [
            {"c": "green", "g": 1, "r": b(0, 0, 10, 10, 210.0)},        # 0 a bed, 4 m over the lidar, by wall 1
            {"c": "wall", "r": b(0, -0.3, 10, 0, 210.0)},               # 1 its wall, as high
            {"c": "green", "g": 1, "r": b(30, 0, 40, 10, 210.0)},       # 2 as high, no wall: a deck, a roof
            {"c": "green", "g": 1, "r": b(60, 0, 70, 10, 206.2)},       # 3 a lawn on the ground by wall 4
            {"c": "wall", "r": b(60, -0.3, 70, 0, 207.5)},              # 4 a garden wall on the ground
            {"c": "green", "r": b(0, 20, 10, 30, 210.0)},               # 5 off the lidar: its own outline already
            {"c": "green", "g": 1, "l": 1, "r": b(0, 40, 10, 50, 210.0)},  # 6 on a structure's level
            # 7 a footpath from the street up onto the bed's terrace: 3 of its 6 points at the bed's height
            {"c": "sidewalk", "r": [[10, 0, 210.0], [12, 0, 210.0], [12, 10, 210.0], [12, 20, 206.1], [10, 20, 206.0], [10, 10, 208.0]]},
            # 8 the street's sidewalk along the terrace's foot: it touches the bed, none of its points over the lidar
            {"c": "sidewalk", "r": b(-3, 0, 0, 10, 206.05)},
        ]}
        self.lidar = lambda x, y: np.full(np.shape(x), 206.0)

    def test_a_lidar_area_over_the_lidar_by_a_wall_as_high_is_a_terrace(self):
        self.assertEqual(gm.terraces(self.D, list(range(9)), self.lidar), {0})

    def test_a_footpath_onto_a_terrace_stands_on_it_and_a_streets_sidewalk_at_its_foot_does_not(self):
        self.assertEqual(gm.beside(self.D, [7, 8], {0}, self.lidar), {7})
        self.assertEqual(gm.beside(self.D, [7, 8], set(), self.lidar), set())


class InARockTunnel(unittest.TestCase):
    """#771: the Vyšehrad tunnel's south mouth, line 17 s 11385.8: the survey's road 4.3 m over the track."""

    L = {"path": [[0.0, 0.0], [300.0, 0.0]], "tunnels": [[100.0, 140.0], [200.0, 210.0]],
         "heights": {"step": 2.0, "path": [193.0] * 151}}

    @staticmethod
    def hill(x, y):  # (20 m of rock over the first tunnel, a road's bridge 6 m over the second)
        x = np.asarray(x, float)
        return np.where((x > 98) & (x < 142), 213.0, np.where((x > 199) & (x < 211), 199.0, 193.0))

    def test_a_tunnel_under_rock_is_one_and_a_road_over_the_track_is_not(self):
        self.assertEqual(gm.rock_tunnels(self.L, self.hill), [(100.0, 140.0)])

    def test_the_corridor_and_the_rails_level(self):
        x = np.array([99.0, 99.8, 120.0, 120.0, 140.4, 141.0, 205.0])
        y = np.array([0.0, 2.0, 8.0, 9.0, -3.0, 0.0, 0.0])
        inside, rail = gm.in_the_rock(self.L, [(100.0, 140.0)], x, y)
        self.assertEqual(inside.tolist(), [False, True, True, False, True, False, False])
        self.assertEqual(rail[inside].tolist(), [193.0, 193.0, 193.0])

    def test_a_portals_masonry_comes_down_with_the_corridor(self):
        # (the north gate, line 17 area 1237: a wall-like strip with a corner on the hill inside the corridor and its
        # wing wall's line running 12 m on past the tunnel's end; a road with a corner on the hill is no masonry, and a
        # wall 40 m on is another wall)
        x = np.array([139.0, 144.0, 152.0, 139.0, 150.0, 190.0])
        y = np.array([3.0, 4.0, 5.0, -3.0, -5.0, 4.0])
        z = np.array([197.2, 196.0, 193.2, 197.0, 196.0, 196.0])
        area = np.array([7, 7, 7, 8, 8, 7])
        inside, rail = gm.in_the_rock(self.L, [(100.0, 140.0)], x, y)
        self.assertEqual(inside.tolist(), [True, False, False, True, False, False])
        inside, rail = gm.portal_masonry(self.L, [(100.0, 140.0)], inside, rail, x, y, z, area, lambda a: a == 7)
        self.assertEqual(inside.tolist(), [True, True, True, True, False, False])
        self.assertEqual(gm.off_the_hill(z, np.where(inside, rail, np.nan))[0].tolist(), [193.0, 193.0, 193.2, 193.0, 196.0, 196.0])

    def test_a_corner_on_the_hill_comes_down_to_the_rails(self):
        z, high = gm.off_the_hill([197.3, 193.4, 205.0], [193.0, 193.0, np.nan])
        self.assertEqual(z.tolist(), [193.0, 193.4, 205.0])
        self.assertEqual(high.tolist(), [True, False, False])


class Pits(unittest.TestCase):
    def test_a_small_green_area_inside_a_sidewalk_is_a_pit(self):
        # (#696: a tree pit of 2 m2 and a bed of 30 m2 in a sidewalk; a lawn of 100 m2 in it; a pit with one side on the
        # road; a green area on another level)
        def rect(x0, y0, x1, y1, c, l=0):
            return {"c": c, "l": l, "r": [[x0, y0, 190.0], [x1, y0, 190.0], [x1, y1, 190.0], [x0, y1, 190.0]]}
        D = {"areas": [rect(0, 0, 60, 12, "sidewalk"), rect(2, 2, 3, 4, "green"), rect(10, 2, 16, 7, "green"),
                       rect(20, 1, 40, 6, "green"), rect(50, -1, 52, 1, "green"), rect(2, 6, 3, 8, "green", 1),
                       rect(0, -8, 60, 0, "road")]}
        self.assertEqual(gm.pits(D, list(range(7))), {1, 2})
        self.assertEqual(gm.pits(D, [3, 6]), set())


class LowWalls(unittest.TestCase):
    def test_a_walls_corner_over_the_ground_at_its_point_stands_apart(self):
        # (#696, #776: a low wall's top 0.5 m over the sidewalk it shares a point with; one level with it; one over
        # nothing; the sidewalk's own corner; one 1.5 m over a lawn's corner on the lidar, which the weld joins to it)
        cx, cy = np.array([0.0, 0.0, 1.0, 1.0, 2.0, 0.0, 3.0, 3.0]), np.zeros(8)
        z = np.array([192.6, 192.1, 192.15, 192.1, 192.6, 192.1, 195.6, 194.1])
        wall = np.array([True, False, True, False, True, False, True, False])
        street = np.array([False, True, False, True, False, True, False, False])
        self.assertEqual(gm.standing(cx, cy, z, wall, street).tolist(), [True] + [False] * 7)


class Platforms(unittest.TestCase):
    """#776: a platform 40 m long on the right of a straight track that climbs 1 %, its edge 1.35 m from the axis."""

    L = {"path": [[0.0, 0.0], [100.0, 0.0]], "heights": {"step": 2.0, "path": [200.0 + 0.02 * i for i in range(51)]},
         "platforms": [{"path": "route", "s0": 30.0, "s1": 70.0, "side": -1, "vienna": None, "name": "Test"}]}

    def corners(self):
        xs, ys = np.meshgrid(np.arange(20.0, 81.0, 1.0), -np.arange(1.5, 7.1, 0.5))
        return xs.ravel(), ys.ravel()

    def test_a_platform_is_a_plane_over_the_rail_top(self):
        x, y = self.corners()
        rng = np.random.default_rng(1)
        z = 200.0 + 0.01 * x + 0.20 + 0.01 * -y + rng.normal(0, 0.05, len(x))  # (0.20 m at the axis, 1 % crossfall, bumps)
        z[(np.abs(x - 50) < 1.5) & (y < -5.6)] += 1.2  # (a wall's top behind the band)
        got, moved = gm.platform_planes(self.L, x, y, z, np.ones(len(x), bool))
        band = (x >= 32) & (x <= 68) & (y >= -4.0)
        plane = 200.0 + 0.01 * x + 0.20 + 0.01 * -y + 1.28 * 0.05  # (at the top of the bumps: their 90th percentile)
        self.assertLess(np.abs(got[band] - plane[band]).max(), 0.025)
        self.assertTrue(moved[band].all())
        out = (x < 30) | (x > 70) | (y < -5.5)
        self.assertTrue(np.allclose(got[out], z[out]) and not moved[out].any())

    def test_a_platform_keeps_its_high_kerb(self):
        # (an island between the bed and a road 0.12 m higher: the street surface runs straight from one kerb's top to
        # the other's, 5 % across. The plane takes 2 % and keeps the high side within 1.5 cm; at the corners' middle it
        # lay 3.7 cm under it. A road climbing 8 cm against the rails along the stop: the plane keeps its high end)
        x, y = self.corners()
        z = 200.0 + 0.01 * x + 0.05 * -y
        got, _ = gm.platform_planes(self.L, x, y, z, np.ones(len(x), bool))
        high = (x >= 32) & (x <= 68) & (y == -4.0)
        self.assertGreater((got[high] - z[high]).min(), -0.015)
        z = 200.0 + 0.01 * x + 0.20 + 0.002 * (x - 30)
        got, _ = gm.platform_planes(self.L, x, y, z, np.ones(len(x), bool))
        end = (x >= 60) & (x <= 68) & (y >= -4.0)
        self.assertGreater((got[end] - z[end]).min(), -0.02)

    def test_other_platforms_and_other_corners_are_left(self):
        x, y = self.corners()
        z = 200.0 + 0.01 * x + 0.20 + 0.03 * np.sin(x)
        self.assertTrue(np.allclose(gm.platform_planes(dict(self.L, platforms=[dict(self.L["platforms"][0], vienna=3.2)]), x, y, z,
                                                       np.ones(len(x), bool))[0], z))  # (a Vienna-type stop)
        self.assertTrue(np.allclose(gm.platform_planes(self.L, x, -y, z, np.ones(len(x), bool))[0], z))  # (the other side)
        self.assertTrue(np.allclose(gm.platform_planes(self.L, x, y, z, np.zeros(len(x), bool))[0], z))  # (no raised corner)

    def test_a_bare_hole_in_a_sidewalk_is_its_own_ground(self):
        def ring(x0, y0, x1, y1):
            return [[x0, y0, 190.0], [x1, y0, 190.0], [x1, y1, 190.0], [x0, y1, 190.0]]
        walk = {"c": "sidewalk", "l": 0, "r": ring(0, 0, 60, 12), "h": [ring(5, 4, 9, 5.5), ring(20, 3, 26, 7), ring(40, 2, 55, 10)]}
        D = {"areas": [walk, {"c": "green", "l": 0, "r": ring(20, 3, 26, 7)}]}
        got = gm.bare_holes(D, [0, 1])  # (a shelter's footprint; a hole a bed fills; a hole of 120 m2)
        self.assertEqual([round(g.area, 1) for g in got], [6.0])


class BesideAThinWall(unittest.TestCase):
    def test_a_road_beside_a_thin_wall_keeps_its_surface_from_past_the_smear(self):
        # (#779: a wall 0.3 m across along y = 0..0.3, a ramp at 258 m south of it and a road at 261 m north; the
        # raster spreads the step over 1.5 m either side, and so does the road's own surface. Corners 0.5 m and on the
        # wall, either side, take the surface 1.5 m out; one 2 m off is left; so are all on a surface level out there)
        D = {"areas": [{"c": "wall", "l": 0, "r": [[0, 0, 260.4], [10, 0, 260.4], [10, 0.3, 260.4], [0, 0.3, 260.4]]},
                       {"c": "wall", "l": 0, "r": [[0, 20, 260.4], [10, 20, 260.4], [10, 23, 260.4], [0, 23, 260.4]]},
                       {"c": "wall", "l": 1, "r": [[0, 40, 260.4], [10, 40, 260.4], [10, 40.3, 260.4], [0, 40.3, 260.4]]}]}
        walls = gm.thin_walls(D)
        self.assertEqual(len(walls), 4)

        def smeared(px, py):
            return 258.0 + 3.0 * np.clip((np.asarray(py, float) + 1.5) / 3.3, 0, 1)
        x = np.full(5, 5.0)
        y = np.array([-0.5, 0.0, 0.3, 0.8, -2.0])
        ty = np.array([-0.7, -0.2, 0.5, 1.0, -2.2])
        z, held = gm.off_the_smear(walls, x, y, x, ty, smeared(x, y), smeared)
        self.assertEqual(held.tolist(), [True, True, True, True, False])
        np.testing.assert_allclose(z, [258.0, 258.0, 261.0, 261.0, smeared(5.0, -2.0)], atol=1e-9)
        flat = lambda px, py: np.full(len(np.atleast_1d(px)), 258.0)  # noqa: E731
        self.assertFalse(gm.off_the_smear(walls, x, y, x, ty, flat(x, y) + 0.04, flat)[1].any())
        self.assertFalse(gm.off_the_smear(walls, x, y, x, ty, smeared(x, y), lambda px, py: np.full(len(px), np.nan))[1].any())
        # (the surface out there 5 m over the lidar, a deck's level: left; on the lidar: taken)
        self.assertFalse(gm.off_the_smear(walls, x, y, x, ty, smeared(x, y), lambda px, py: smeared(px, py) + 5.0, smeared)[1].any())
        self.assertEqual(gm.off_the_smear(walls, x, y, x, ty, smeared(x, y), smeared, smeared)[1].sum(), 4)

    def test_a_sidewalks_edge_over_a_sunk_road_is_such_a_wall(self):
        # (a sidewalk north of y = 0 surveyed at 200.4 m, its kerb edge along a ramp falling east from 200.3 m: the
        # edge from where it stands 0.3 m over a kerb on the ramp, 20 m of 0.25 m pieces less the first 3 m; beside a
        # level road, none)
        D = {"areas": [{"c": "sidewalk", "l": 0, "k": [[1, 0, 0, 0]],
                        "r": [[0, 0, 200.4], [20, 0, 200.4], [20, 4, 200.4], [0, 4, 200.4]]}]}
        ground = lambda px, py: np.full(len(px), 200.4)  # noqa: E731
        e = gm.kerb_walls(D, lambda px, py: 200.3 - 0.1 * np.asarray(px, float), ground)
        self.assertEqual(e.shape, (68, 2, 2))
        self.assertAlmostEqual(float(e[:, :, 0].min()), 3.0)
        self.assertEqual(gm.kerb_walls(D, lambda px, py: np.full(len(px), 200.3), ground).shape, (0, 2, 2))
        # (the outline carries a parapet's top, 1.1 m over the walkway, the road a kerb under that: no wall; the
        # road 1.5 m over the walkway: a wall, by the lidar's level, #770)
        low = lambda px, py: np.full(len(px), 199.3)  # noqa: E731
        self.assertEqual(gm.kerb_walls(D, lambda px, py: np.full(len(px), 199.2), low).shape, (0, 2, 2))
        self.assertEqual(gm.kerb_walls(D, lambda px, py: np.full(len(px), 200.8), low).shape, (80, 2, 2))

    def test_in_a_corner_of_two_walls_the_surface_is_read_clear_of_both(self):
        # (walls along y = 0 and along x = 0, a pit at 258 m in their corner whose surface is smeared within 1.5 m of
        # either: a corner on the first wall 0.2 m from the second takes the surface 1.5 m from both)
        D = {"areas": [{"c": "wall", "l": 0, "r": [[0, 0, 261], [10, 0, 261], [10, 0.3, 261], [0, 0.3, 261]]},
                       {"c": "wall", "l": 0, "r": [[-0.3, -10, 261], [0, -10, 261], [0, 0.3, 261], [-0.3, 0.3, 261]]}]}

        def pit(px, py):
            px, py = np.asarray(px, float), np.asarray(py, float)
            return np.where((px > 0) & (py < 0), 258.0 + 3.0 * np.clip(1 - np.minimum(px, -py) / 1.5, 0, 1), 261.0)
        x, y = np.array([0.2]), np.array([0.0])
        z, held = gm.off_the_smear(gm.thin_walls(D), x, y, np.array([0.4]), np.array([-0.3]), pit(x, y), pit)
        self.assertTrue(held[0])
        self.assertAlmostEqual(float(z[0]), 258.0, places=6)

    def test_at_a_walls_end_the_point_out_is_not_through_the_wall(self):
        # (a road's corner at the wall's end, its triangle north of the wall: the short edge across the wall's end
        # points along the wall into the pit south of it; the corner takes the road's own side)
        D = {"areas": [{"c": "wall", "l": 0, "r": [[0, 0, 261], [10, 0, 261], [10, 0.3, 261], [0, 0.3, 261]]}]}

        def ground(px, py):
            return np.where(np.asarray(py, float) < 0.15, 258.0, 261.0)
        x, y = np.array([0.0]), np.array([0.3])
        z, held = gm.off_the_smear(gm.thin_walls(D), x, y, np.array([0.3]), np.array([0.6]), np.array([259.5]), ground)
        self.assertEqual((held.tolist(), z.tolist()), ([True], [261.0]))

    def test_a_ramp_runs_on_to_the_wall_at_its_own_grade(self):
        # (a ramp falling 15 % towards the wall's foot: the corner at the wall lies on the ramp's line, not level with
        # the surface 1.5 m out; a surface 40 % steeper there is another wall's smear: level)
        D = {"areas": [{"c": "wall", "l": 0, "r": [[0, 0, 260.4], [10, 0, 260.4], [10, 0.3, 260.4], [0, 0.3, 260.4]]}]}
        walls = gm.thin_walls(D)

        x, y, ty = np.full(2, 5.0), np.array([0.0, -1.0]), np.array([-0.2, -1.2])
        for grade, at_wall in ((0.15, 258.0), (0.4, 258.6)):
            ramp = lambda px, py, grade=grade: 258.0 - grade * np.asarray(py, float)  # noqa: E731
            z, held = gm.off_the_smear(walls, x, y, x, ty, np.full(2, 259.0), ramp)
            self.assertTrue(held.all())
            np.testing.assert_allclose(z, [at_wall, 258.0 + grade * (1.0 if grade < 0.2 else 1.5)], atol=1e-9)


class APairsEnd(unittest.TestCase):
    def test_the_strip_between_two_wall_lines_holds_nothing_past_their_end(self):
        # (#770: a wall's foot line along x = 0 from y = 0 north, its right side the strip to the top line at 271.18 m,
        # its left the ground at 272.5 m. A corner on the strip's side beside the line takes the strip's level; 0.4 m
        # past the end, within reach of the stretch's second segment, it is left; 1 m past it is out of reach)
        n = 6
        foot = {"p": np.column_stack([np.zeros(n), np.arange(n, dtype=float)]), "zl": np.full(n, 272.5), "zr": np.full(n, 271.18),
                "gl": np.zeros(n), "gr": np.zeros(n), "sr": np.ones(n, bool)}
        cx = np.array([0.3, 0.3, 0.3])
        cy = np.array([2.0, -0.4, -1.0])
        z, held = gm.hold_at_walls(cx, cy, cx, cy - 0.1, np.full(3, 272.6), np.ones(3, bool), [foot])
        self.assertEqual((held.tolist(), np.round(z, 2).tolist()), ([True, False, False], [271.18, 272.6, 272.6]))
        # (a side read from the raster holds on there, as before)
        plain = {k: v for k, v in foot.items() if k != "sr"}
        z0, _ = gm.hold_at_walls(cx, cy, cx, cy - 0.1, np.full(3, 272.6), np.ones(3, bool), [plain])
        self.assertEqual(np.round(z0, 2).tolist(), [271.18, 271.18, 272.6])
        # (the same line cut in two at y = 3: at the joint the strip runs on, and the corners beside it are held)
        a = {k: v[:4] for k, v in foot.items()}
        b = {k: v[3:] for k, v in foot.items()}
        z, held = gm.hold_at_walls(np.array([0.3, 0.3]), np.array([2.9, 3.1]), np.array([0.4, 0.4]), np.array([3.1, 2.9]),
                                   np.full(2, 272.6), np.ones(2, bool), [a, b])
        self.assertEqual(np.round(z, 2).tolist(), [271.18, 271.18])


class UnderADeck(unittest.TestCase):
    def test_a_street_corner_at_the_decks_level_under_a_span_lies_on_the_lidar(self):
        # (#761: the road under the Modřany viaduct; the ramp's own strip, 0.3 m off the lidar, keeps the street surface)
        z, low = gm.off_the_deck([205.3, 204.7, 198.3, np.nan], [197.6, 204.4, 198.2, 197.0])
        self.assertEqual(low.tolist(), [True, False, False, False])
        self.assertEqual(z[:3].tolist(), [197.6, 204.7, 198.3])
        self.assertTrue(np.isnan(z[3]))


class TwoSided(unittest.TestCase):
    """#765: the wall under Letná, line 17 area 4166: a paved strip 0.44 m across, its foot's line along the road and
    its top's behind it, joining gradually at the ends."""

    @staticmethod
    def strip(top, n=16, step=2.0, width=0.44):
        foot = [[i * step, 0.0, 191.2] for i in range(n + 1)]
        back = [[i * step, width, 191.2 + top * min(1.0, i / 3, (n - i) / 3)] for i in range(n, -1, -1)]
        return {"c": "paved", "r": foot + back}

    def test_a_strip_with_its_foot_one_side_and_its_top_the_other_is_a_wall(self):
        a = self.strip(3.0)
        self.assertFalse(gm.climbs(a))
        self.assertTrue(gm.two_sided(a))
        self.assertTrue(gm.wall_like(a))

    def test_a_level_strip_and_a_low_edging_are_not(self):
        self.assertFalse(gm.two_sided(self.strip(0.0)))
        self.assertFalse(gm.wall_like(self.strip(0.4)))  # (under WALL_FACE)

    def test_a_strip_on_the_lidar_and_a_wide_area_are_not_walls(self):
        self.assertFalse(gm.wall_like(dict(self.strip(3.0), g=1)))
        self.assertFalse(gm.wall_like(self.strip(3.0, width=4.0)))


class Abutments(unittest.TestCase):
    """#763: the Modřany viaduct's abutment, line 17 (-2393, -9247): the bed's end 1.3 m over the face, the wing
    walls' lines turning at its corners and running on at the street's level."""

    outline = shapely.box(0, -3, 50, 3)  # (the bed on the ramp, its end at x = 0; the deck runs on to -x)
    tracks = [np.array([[60.0, 0.0], [-10.0, 0.0]])]

    @staticmethod
    def bed_at(x, y):
        return np.full(np.shape(x), 106.5)

    @staticmethod
    def lidar(x, y):  # (the street at 100 m, the ramp's top at 106 m, the face at x = 1.3 smeared over 1 m)
        return 100.0 + 6.0 * np.clip(np.asarray(x, float) - 0.8, 0, 1)

    wings = [np.array([[20, -4, 103.0], [1.3, -4, 103.0], [1.3, -4.5, 100.2], [-10, -4.5, 100.1]]),
             np.array([[20, 4, 103.0], [1.4, 4, 103.0]])]

    def ends(self, lines):
        self.assertEqual(len(lines), 1)
        return sorted(np.round(lines[0][:, :2], 2).tolist())

    def test_the_face_is_where_the_lidar_steps_under_the_beds_end_between_the_wing_walls_corners(self):
        got = gm.abutments(self.tracks, self.outline, self.bed_at, self.lidar, self.wings)
        self.assertEqual(self.ends(got), [[1.3, -4.0], [1.4, 4.0]])  # (not the low wall's points along the street)

    def test_without_wing_walls_it_runs_to_the_beds_edges(self):
        got = gm.abutments(self.tracks, self.outline, self.bed_at, self.lidar, [])
        self.assertEqual(self.ends(got), [[1.3, -3.0], [1.3, 3.0]])

    def test_over_a_slope_with_no_step_the_face_is_the_beds_end(self):
        # (an embankment's cone under the deck's end: Krejcárek, line 37 (3954, 380))
        got = gm.abutments(self.tracks, self.outline, self.bed_at, lambda x, y: 103.0 + 0.6 * np.clip(np.asarray(x, float), -9, 5), [])
        self.assertEqual(self.ends(got), [[0.0, -3.0], [0.0, 3.0]])

    def test_off_the_lines_bridges_a_beds_end_is_no_abutment(self):
        # (line 17 s 3088: the beds stop over an underpass the line has no span for)
        args = (self.tracks, self.outline, self.bed_at, self.lidar, self.wings)
        self.assertEqual(len(gm.abutments(*args, decks=shapely.box(-20, -12, 5, 12))), 1)
        self.assertEqual(gm.abutments(*args, decks=shapely.box(100, 100, 120, 120)), [])

    def test_a_bed_that_ends_on_the_ground_is_no_abutment(self):
        self.assertEqual(gm.abutments(self.tracks, self.outline, self.bed_at, lambda x, y: np.full(np.shape(x), 106.0), []), [])


class WallsMeeting(unittest.TestCase):
    """#763: two stretches meeting at a corner (a wing wall and the abutment's line): the ramp's top north-east of
    it at 106 m, the street round it at 100 m."""

    @staticmethod
    def stretch(p, zl, zr):
        n = len(p)
        return {"p": np.array(p, float), "zl": np.full(n, zl), "gl": np.zeros(n), "zr": np.full(n, zr), "gr": np.zeros(n)}

    def hold(self, walls, corners):
        c = np.array(corners, float)  # (rows of the corner's x, y and its triangle's centre's x, y)
        z, held = gm.hold_at_walls(c[:, 0], c[:, 1], c[:, 2], c[:, 3], np.full(len(c), 103.0), np.ones(len(c), bool), walls)
        return z.tolist(), held.tolist()

    def setUp(self):
        self.wing = self.stretch([[10, 0], [5, 0], [0, 0]], 100.0, 106.0)  # (westwards: the street to its left, south)
        self.face = self.stretch([[0, 0], [0, 5], [0, 10]], 100.0, 106.0)  # (northwards: the street to its left, west)

    def test_the_corner_outside_two_meeting_walls_is_the_streets(self):
        z, held = self.hold([self.wing, self.face], [
            [-0.5, -0.5, -0.6, -0.3],  # (past both walls' ends)
            [-1.0, 0.2, -0.8, 0.1],    # (past the wing's end, north of its line run on: west of the face)
            [0.0, 0.0, -0.3, 0.5],     # (the meeting point itself, in a triangle west of the face)
            [0.0, 0.0, 0.5, 0.5],      # (and in one on the ramp)
            [0.0, 0.0, 0.4, -0.4],     # (and in one south of the wing)
        ])
        self.assertEqual(z, [100.0, 100.0, 100.0, 106.0, 100.0])
        self.assertTrue(all(held))

    def test_beside_a_strips_outline_every_corner_is_outside_the_strip(self):
        # (#771: the end of the wing wall by the Vyšehrad tunnel's north mouth, line 17 (-727.35, -2547.76): the strip's
        # north edge running west, the strip to its left, and its end's edge running south. The sidewalk's corner 1 m
        # past the end, in a triangle whose centre lies left of the north edge's line run on, took the strip's level)
        north = dict(self.stretch([[10, 0], [5, 0], [0, 0]], 106.0, 100.0), out="r")
        end = dict(self.stretch([[0, 0], [0.3, -0.6], [0.6, -1.2]], 106.0, 100.0), out="r")
        z, held = self.hold([north, end], [[-1.0, -0.1, -0.7, -2.2], [5.0, 0.5, 5.0, 0.8], [5.0, -0.8, 5.0, -1.1]])
        self.assertEqual(z, [100.0, 100.0, 106.0])  # (the last behind the strip: at its level, as at a wall line)
        plain = [self.stretch([[10, 0], [5, 0], [0, 0]], 106.0, 100.0)]
        self.assertEqual(self.hold(plain, [[5.0, 0.0, 5.0, -0.2]])[0], [106.0])  # (a wall line: by the triangle's side)
        # (a street's corner keeps its own surface beside a strip, #770; a wall line holds it)
        c = np.array([[5.0, 0.5, 5.0, 0.8], [5.0, 0.6, 5.0, 0.9]])
        args = (c[:, 0], c[:, 1], c[:, 2], c[:, 3], np.full(2, 103.0), np.ones(2, bool))
        self.assertEqual(gm.hold_at_walls(*args, [north], None, np.array([True, False]))[0].tolist(), [103.0, 100.0])
        self.assertEqual(gm.hold_at_walls(*args, plain, None, np.array([True, False]))[0].tolist(), [100.0, 100.0])

    def test_a_line_across_a_structure_leaves_the_decks_own_surface(self):
        face = dict(self.face, across=True)
        c = np.array([[-0.5, 5.0, -0.6, 5.0], [-0.5, 6.0, -0.6, 6.0]])
        z, held = gm.hold_at_walls(c[:, 0], c[:, 1], c[:, 2], c[:, 3], np.full(2, 106.3), np.ones(2, bool), [face], np.array([True, False]))
        self.assertEqual(z.tolist(), [106.3, 100.0])  # (the deck's own corner stays; the street's under it is held)
        self.assertEqual(held.tolist(), [False, True])

    def test_a_corner_past_a_walls_free_end_is_left(self):
        z, held = self.hold([self.wing], [[-0.5, 0.2, -0.6, 0.3], [2.0, 0.5, 2.0, 0.3]])
        self.assertEqual(z, [103.0, 106.0])
        self.assertEqual(held, [False, True])


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
