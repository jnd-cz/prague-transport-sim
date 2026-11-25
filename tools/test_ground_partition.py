# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_partition.py: the survey's overlaps, the bed union, the plot height and the terrain cut (#507).

    python -P -E tools/test_ground_partition.py
"""
import os
import sys
import unittest

import numpy as np
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_partition as gp  # noqa: E402


class Frame:
    E0 = N0 = 0.0


class Ipr:
    """IPR's ground as a function of x, y."""

    def __init__(self, f):
        self.f = f

    def sample(self, E, N):
        return self.f(np.asarray(E, float), np.asarray(N, float))


def sq(x0, y0, x1, y1, z=0.0):
    return [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]]


class Area(unittest.TestCase):
    def test_the_box_within_reach_of_the_route_and_the_tracks(self):
        L = {"terrain": {"x0": -5000, "y0": -5000, "dx": 10, "dy": 10, "nx": 1001, "ny": 1001},
             "path": [[0, 0], [1000, 0]], "tracks": [{"p": [[0, 3000], [0, 3100]]}]}
        a = gp.line_area(L, reach=1200)
        self.assertTrue(a.contains(shapely.Point(500, 1100)))
        self.assertFalse(a.contains(shapely.Point(500, 1300)))
        self.assertTrue(a.contains(shapely.Point(0, 4250)))  # (around the track)
        self.assertFalse(a.contains(shapely.Point(3000, 0)))
        self.assertTrue(gp.line_box(L).covers(a))


class Survey(unittest.TestCase):
    def test_higher_rank_holds_the_overlap(self):
        D = {"areas": [{"c": "green", "l": 0, "r": sq(0, 0, 10, 10)}, {"c": "road", "l": 0, "r": sq(5, 0, 15, 10)}]}
        p = gp.survey_pieces(D, shapely.box(-100, -100, 100, 100))
        by = {q["c"]: q["g"].area for q in p}
        self.assertAlmostEqual(by["road"], 100)
        self.assertAlmostEqual(by["green"], 50)

    def test_smaller_wins_between_equal_ranks_and_not_ground_left_out(self):
        D = {"areas": [{"c": "road", "l": 0, "r": sq(0, 0, 10, 10)}, {"c": "road", "l": 0, "r": sq(2, 2, 4, 4)},
                       {"c": "roof", "l": 0, "r": sq(0, 0, 1, 1)}, {"c": "road", "l": 1, "r": sq(0, 0, 3, 3)}]}
        p = gp.survey_pieces(D, shapely.box(-100, -100, 100, 100))
        self.assertEqual(sorted(round(q["g"].area) for q in p), [4, 96])
        self.assertEqual({q["area"] for q in p}, {0, 1})

    def test_a_wall_is_drawn_under_what_outranks_it(self):
        # (#653: a level-0 wall is a piece, drawn from its own outline as the page drew it before #509; a road over it
        # holds the overlap; another level's wall is not one)
        D = {"areas": [{"c": "road", "l": 0, "r": sq(0, 0, 10, 10)}, {"c": "wall", "l": 0, "r": sq(9, 0, 11, 10)},
                       {"c": "wall", "l": 1, "r": sq(20, 0, 21, 10)}]}
        p = gp.survey_pieces(D, shapely.box(-100, -100, 100, 100))
        by = {q["area"]: round(q["g"].area) for q in p}
        self.assertEqual(by, {0: 100, 1: 10})

    def test_clipped_to_the_box(self):
        D = {"areas": [{"c": "road", "l": 0, "r": sq(-5, 0, 5, 10)}]}
        self.assertAlmostEqual(gp.survey_pieces(D, shapely.box(0, 0, 100, 100))[0]["g"].area, 50)


def track(p, n, z=0.0, w=200):
    return {"p": p, "zs": [z] * n if np.isscalar(z) else list(z), "bed": {"l": [w] * n, "r": [w] * n, "meet": [0] * n}}


class Beds(unittest.TestCase):
    def line(self, tracks):
        return {"path": [[0, -50], [0, 50]], "tracks": tracks, "lift": {"step": 2, "unit": 0.001, "v": [0] * 60}}

    def test_overlapping_beds_merge_into_one(self):
        L = self.line([track([[0, 0], [20, 0]], 11), track([[10, -1], [30, 1]], 11)])
        B, outs = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: x * 0), Frame())
        self.assertEqual(len(outs), 2)
        self.assertEqual(len(shapely.get_parts(B)), 1)
        self.assertGreater(B.area, 4 * 30 - 1)

    def test_a_gap_of_mm_between_two_beds_is_closed_a_wide_one_stays(self):
        L = self.line([track([[0, 0], [20, 0]], 11), track([[0, 4.005], [20, 4.005]], 11),
                       track([[0, 8.5], [20, 8.5]], 11)])
        B, _ = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: x * 0), Frame())
        self.assertEqual(len(shapely.get_parts(B)), 2)  # (the 5 mm gap closed, the 0.5 m one kept)
        self.assertAlmostEqual(B.area, 3 * 80 + 0.1, places=2)

    def test_samples_on_a_structure_left_out(self):
        # (a bridge: the rails 6 m over IPR's ground in the middle of the track)
        z = [0.0] * 4 + [6.0] * 3 + [0.0] * 4
        log = {}
        L = self.line([track([[0, 0], [20, 0]], 11, z)])
        B, _ = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: x * 0), Frame(), log)
        self.assertEqual(len(shapely.get_parts(B)), 2)
        self.assertAlmostEqual(B.area, 4 * 12, places=3)  # (three 2 m stretches on each side kept, four left out)
        self.assertEqual(log["samples on structures, left out"], 3)

    def test_the_bed_ends_at_the_decks_end(self):
        # (#594: a span s 60-100 with a ramp s 60-64, the deck from s 64 (x 14); the lidar falls 6 m from x 11, so its
        # test left out the ramp's sample at x 12 and the bed ended at x 10. The route's deck decides: the bed to x 14)
        L = {"path": [[-50, 0], [50, 0]], "tracks": [track([[0, 0], [20, 0]], 11)], "spans": [[60, 100]],
             "ramps": [[60, 64]], "heights": {"step": 2, "path": [0.0] * 51}, "lift": {"step": 2, "unit": 0.001, "v": [0] * 51}}
        log = {}
        B, _ = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: np.where(x > 11, -6.0, 0.0)), Frame(), log)
        self.assertAlmostEqual(B.bounds[2], 14, places=3)
        self.assertAlmostEqual(B.area, 14 * 4, places=2)
        self.assertEqual(log["samples near a span's end the route's decks decided against the lidar"], 1)
        # (a track crossing under the deck, 6 m below the route, keeps the lidar's test)
        L["tracks"].append(track([[30, -10], [30, 10]], 11, -6.0))
        B, outs = gp.bed_pieces(L, shapely.box(-100, -100, 100, 100), Ipr(lambda x, y: np.where(x > 11, -6.0, 0.0)), Frame())
        self.assertAlmostEqual(dict(outs)[1].area, 20 * 4, places=2)

    def test_route_decks_are_the_spans_less_their_ramps(self):
        self.assertEqual(gp.route_decks({"spans": [[0, 100], [200, 210]], "ramps": [[0, 10], [90, 100], [205, 210]]}),
                         [(10, 90), (200, 205)])

    def test_outline_keep_mask(self):
        import track_beds
        tr = track([[0, 0], [10, 0]], 6)
        full = track_beds.outline(tr, tr["bed"])
        part = track_beds.outline(tr, tr["bed"], keep=[True, True, True, False, False, False])
        self.assertAlmostEqual(full.area, 40, places=3)
        self.assertAlmostEqual(part.area, 16, places=3)


class Plots(unittest.TestCase):
    def test_height_is_the_median_around_the_footprint(self):
        g = shapely.box(0, 0, 10, 10)
        z = gp.plot_height(g, Ipr(lambda x, y: x), Frame())
        self.assertAlmostEqual(z, 5.0, delta=0.3)

    def test_cut_by_the_classes_above_and_earlier_footprints(self):
        L = {"buildings": [{"p": [[0, 0], [10, 0], [10, 10], [0, 10]], "h": 9, "k": "yes"},
                           {"p": [[5, 0], [15, 0], [15, 10], [5, 10]], "h": 9, "k": "yes"}]}
        above = shapely.box(0, 0, 2, 10)
        p = gp.plot_pieces(L, shapely.box(-100, -100, 100, 100), [above], Ipr(lambda x, y: x * 0 + 200), Frame())
        self.assertEqual([round(q["g"].area) for q in p], [80, 50])
        self.assertEqual([q["z"] for q in p], [200.0, 200.0])


class Strips(unittest.TestCase):
    def test_a_thin_strip_by_a_plot_joins_it_a_wide_one_stays(self):
        box = shapely.box(0, 0, 30, 10)
        plots = [{"building": 0, "z": 0, "g": shapely.box(10, 0, 20, 10)}]
        survey = shapely.box(0, 0, 9.6, 10)  # (0.4 m short of the footprint: a strip)
        terrain = box.difference(survey.union(plots[0]["g"]))  # (and 10 m of open ground east of it)
        r = gp.thin_strips(terrain, plots)
        self.assertEqual(r["pieces"], 1)
        self.assertAlmostEqual(r["area"], 4.0, places=3)
        self.assertAlmostEqual(plots[0]["g"].area, 104.0, places=3)

    def test_a_plot_that_took_a_strip_has_no_grid_of_its_own(self):
        # (the strip is on the grid, but GEOS's grid stays with a geometry: a union over the plot snap-rounded every
        # piece in it, a survey vertex 0.3 mm off the grid moved to it, #812)
        plots = [{"building": 0, "z": 0, "g": shapely.box(10, 0, 20, 10)}]
        gp.thin_strips(shapely.box(0, 0, 30, 10).difference(shapely.box(0, 0, 9.6, 10).union(plots[0]["g"])), plots)
        self.assertEqual(float(shapely.get_precision(plots[0]["g"])), 0.0)
        survey = shapely.Polygon([(20.0003, 5), (20.0003, 15), (25, 15), (25, 5)])
        U = shapely.union_all([plots[0]["g"], survey])
        self.assertIn(20.0003, shapely.get_coordinates(U)[:, 0].tolist())

    def test_strips_do_not_go_by_where_the_terrains_rings_start(self):
        # (stairs-beside-a-building's terrain by a plot, on the grid: opened with the grid, a needle 6 m long and 0.5 mm
        # wide along the plot's edge (-2726.399, -1336.031) to (-2725.6, -1344.2) for three of its ring's starts and none
        # for the fourth, and float noise 300 m off chose which, #812)
        ring = [(-2725.024, -1351.031), (-2725.64, -1351.031), (-2725.0, -1350.9), (-2725.6, -1344.2), (-2726.399, -1336.031),
                (-2720.85, -1334.77), (-2719.02, -1342.41), (-2718.42, -1342.33), (-2717.75, -1342.83), (-2716.48, -1348.89)]
        edge = shapely.box(-2727.4, -1345.0, -2724.9, -1335.5)
        got = []
        for k in range(4):
            r = ring[k:] + ring[:k]
            th = gp.thin_parts(shapely.Polygon(r + r[:1]))
            self.assertLess(th.intersection(edge).area, 1e-6)
            got.append(shapely.normalize(th))
        self.assertTrue(all(g.equals_exact(got[0], 0.0) for g in got))

    def test_strips_read_their_tile_and_its_margin_alone(self):
        # (a footprint and a survey area 0.4 m apart across a tile's edge: the strip between them as the opening of the
        # whole terrain gives it, one piece across the edge; and the same strip whatever terrain lies beyond the margin,
        # #812: GEOS's buffer of the whole box's terrain moved its vertices with the box)
        from geo import tile_box, tile_index
        (e, _), (n, _) = tile_index([0.0, 0.0], [0.0, 0.0])
        X = tile_box(int(e), int(n))[2]  # (the tile's east edge)
        plot = shapely.box(X - 20, 0, X + 20, 10)
        survey = shapely.box(X - 20, 10.4, X + 20, 30)
        box = shapely.box(X - 40, -20, X + 40, 50)
        terrain = box.difference(plot.union(survey))
        thin = gp.thin_parts(terrain)
        whole = terrain.difference(terrain.buffer(-0.5).buffer(0.5, join_style="mitre"))
        self.assertEqual(len(shapely.get_parts(thin)), 1)
        self.assertAlmostEqual(thin.area, whole.area, places=2)
        self.assertAlmostEqual(thin.area, 16.0, delta=0.1)  # (40 m by 0.4 m, its ends rounded where they open)
        far = shapely.box(X + 900, 2000, X + 1400, 2600).difference(shapely.box(X + 1000, 2100, X + 1000.3, 2400))
        thin2 = gp.thin_parts(terrain.union(far))
        near = shapely.box(X - 40, -20, X + 40, 50)
        self.assertTrue(thin2.intersection(near).equals_exact(thin.intersection(near), 0.0))


class Terrain(unittest.TestCase):
    def setUp(self):
        self.x = np.array([0, 10, 10, 0], float)
        self.y = np.array([0, 0, 10, 10], float)
        self.T = np.array([[0, 1, 2], [0, 2, 3]])
        self.box = shapely.box(0, 0, 10, 10)

    def test_cut_kept_and_areas(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.box(6, 1, 8, 3), self.box, threads=1)
        self.assertEqual((r["cut"], r["kept"], r["dropped"]), (1, 1, 0))
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 96, places=6)

    def test_dropped_under_the_cover(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.box(-1, -1, 11, 5).union(shapely.box(5, -1, 11, 11)),
                           self.box, threads=1)
        self.assertEqual(r["dropped"], 1)
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 100 - 50 - 25, places=6)

    def test_cut_by_the_box(self):
        r = gp.cut_terrain(self.x, self.y, self.T, shapely.Polygon(), shapely.box(0, 0, 5, 10), threads=1)
        self.assertEqual(r["cut"], 2)
        self.assertAlmostEqual(r["kept_area"] + r["new_area"], 50, places=6)

    def test_a_needle_thinner_than_the_grid_is_no_remain(self):
        # (#812, modranska-skola-ramp: needles 0.2-0.3 mm wide along a building's edge, kept in one box and not in
        # another. A cover leaving a strip 0.3 mm wide and 10 m long (3e-3 m2, over SLIVER) leaves no remain; 2 mm wide
        # it does)
        for w, n in ((0.0003, 0), (0.002, 1)):
            r = gp.cut_terrain(self.x, self.y, self.T, shapely.box(-1, -1, 10 - w, 11), self.box, threads=1, geometry=True)
            self.assertEqual(len(r["remains"]), n, w)

    def test_the_cover_from_its_pieces_per_tile(self):
        # (#812, yard-at-a-sidewalk: the cover united for the whole box kept a crossing's node as a vertex by what else
        # the box held; from the pieces each tile unites its own, in an order by place, and cuts as the united cover)
        pieces = [shapely.box(6, 1, 8, 3), shapely.box(7, 2, 9, 4), shapely.box(-50, -50, -40, -40)]
        a = gp.cut_terrain(self.x, self.y, self.T, shapely.union_all(pieces), self.box, threads=1, geometry=True)
        for order in (pieces, pieces[::-1]):
            b = gp.cut_terrain(self.x, self.y, self.T, order, self.box, threads=1, geometry=True)
            self.assertEqual((b["cut"], b["kept"], b["dropped"]), (a["cut"], a["kept"], a["dropped"]))
            self.assertAlmostEqual(b["new_area"], a["new_area"], places=6)
            self.assertEqual([round(g.area, 9) for _, g in b["remains"]], [round(g.area, 9) for _, g in a["remains"]])


class Water(unittest.TestCase):
    """WaterLevels (#632): a point's level from the banks of its own water it sees over the water, past no cut."""

    def test_the_level_steps_at_a_weir(self):
        W = shapely.box(0, 0, 600, 40)
        weir = shapely.LineString([(300, -5), (300, 45)])
        lv = gp.WaterLevels(W, [weir], Ipr(lambda x, y: np.where(x < 300, 12.0, 10.0)), Frame())
        z = lv.at(np.array([150.0, 290.0, 310.0, 450.0]), np.array([20.0, 20.0, 20.0, 20.0]))
        self.assertEqual(z.tolist(), [12.0, 12.0, 10.0, 10.0])
        # (a corner on the weir: its own side's level, seen from inside its triangle)
        z = lv.at(np.array([300.0, 300.0]), np.array([20.0, 20.0]), np.array([298.0, 302.0]), np.array([20.0, 20.0]))
        self.assertEqual(z.tolist(), [12.0, 10.0])

    def test_no_bank_across_an_island(self):
        W = shapely.box(0, 0, 600, 100).difference(shapely.box(100, 30, 500, 70))
        lv = gp.WaterLevels(W, [], Ipr(lambda x, y: np.where(y > 50, 20.0, 10.0)), Frame())
        z = lv.at(np.array([300.0, 300.0]), np.array([85.0, 15.0]))
        self.assertEqual(z.tolist(), [20.0, 10.0])

    def test_a_pond_by_the_river_its_own_level(self):
        W = shapely.union_all([shapely.box(0, 0, 600, 40), shapely.box(200, 60, 230, 80)])
        lv = gp.WaterLevels(W, [], Ipr(lambda x, y: np.where(y > 50, 30.0, 10.0)), Frame())
        z = lv.at(np.array([215.0, 215.0]), np.array([70.0, 20.0]))
        self.assertEqual(z.tolist(), [30.0, 10.0])


def keyed(P):
    return sorted(map(tuple, np.round(P, 6).tolist()))


class Grid(unittest.TestCase):
    def test_a_needle_of_float_noise_is_gone_on_the_grid(self):
        # (building 1174's plot in lattice-cell's tile, #812: a needle 9.4 m long, its base a few 1e-13 m wide)
        base = (-1009.7171, 518.4534)
        ring = [(-1030.0, 491.1), (-975.4, 500.0), (-997.44, 529.25), (-1004.8, 526.53), base, (-1004.9, 526.6),
                (base[0] + 3e-13, base[1] - 2e-13), (-1014.27, 509.35)]
        plain = [(-1030.0, 491.1), (-975.4, 500.0), (-997.44, 529.25), (-1004.8, 526.53), base, (-1014.27, 509.35)]
        a, b = [{"g": shapely.Polygon(ring)}], [{"g": shapely.Polygon(plain)}]
        gp.on_the_grid(a)
        gp.on_the_grid(b)
        self.assertTrue(shapely.equals_exact(shapely.normalize(a[0]["g"]), shapely.normalize(b[0]["g"]), 0))
        self.assertFalse(np.isclose(shapely.get_coordinates(a[0]["g"]), (-1004.9, 526.6)).all(1).any())
        # (and a piece left under SLIVER goes)
        c = [{"g": shapely.box(0, 0, 0.005, 0.01)}, {"g": shapely.box(0, 0, 1, 1)}]
        self.assertEqual(len(gp.on_the_grid(c)), 1)


class WaterLocality(unittest.TestCase):
    """#812: a level reads the water within WATER_FAR of its point, and nothing of where the box ends."""
    # (a pond with corners off the grid, and a river that runs out of either box)
    POND = shapely.Polygon([(13.3, 7.1), (61.7, 4.4), (78.2, 39.9), (40.6, 71.3), (9.8, 48.2)])
    RIVER = shapely.Polygon([(-2000.3, -40.2), (2000.7, -60.4), (2000.2, 30.6), (300.1, 45.3), (-2000.9, 20.1)])

    def test_a_banks_samples_do_not_follow_where_its_ring_starts(self):
        c = list(self.POND.exterior.coords)[:-1]
        turned = shapely.Polygon(c[2:] + c[:2])
        self.assertEqual(keyed(gp.bank_samples(self.POND.boundary)), keyed(gp.bank_samples(turned.boundary)))
        # (nor how far the water runs: another pond merged in at its far end leaves the near samples as they were)
        more = shapely.union_all([self.POND, shapely.box(75, 30, 140, 36)])
        near = lambda P: keyed(P[P[:, 0] < 60])  # noqa: E731
        self.assertEqual(near(gp.bank_samples(self.POND.boundary)), near(gp.bank_samples(more.boundary)))
        # (about one sample every WATER_STEP m)
        n = len(gp.bank_samples(self.POND.boundary))
        self.assertTrue(self.POND.length / gp.WATER_STEP <= n <= 1.5 * self.POND.length / gp.WATER_STEP, n)
        # (the old samples, spaced evenly from the ring's first point, moved with it)
        old = lambda g: shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length / 10))))  # noqa: E731
        self.assertNotEqual(keyed(old(self.POND.boundary)), keyed(old(turned.boundary)))

    def test_a_level_is_the_same_in_a_small_box_and_a_larger(self):
        from geo import ORIGIN
        ipr = Ipr(lambda x, y: 180.0 + 0.002 * x + 0.5 * np.sin(x / 37.0) + 0.3 * np.cos(y / 11.0))
        px, py = np.linspace(-300.5, 300.5, 41), np.linspace(-35.2, 20.3, 41)
        out = []
        for box in (shapely.box(-700.37, -400.81, 700.12, 400.55), shapely.box(-1203.9, -900.4, 1207.6, 903.2)):
            lv = gp.WaterLevels(self.RIVER, [], ipr, Frame(), extent=box.buffer(gp.WATER_FAR))
            self.assertEqual(((lv.x0 + ORIGIN[0]) % gp.WATER_RES, (lv.y1 + ORIGIN[1]) % gp.WATER_RES), (0.0, 0.0))
            out.append(lv.at(px, py))
        self.assertTrue(np.isfinite(out[0]).all())
        self.assertEqual(out[0].tolist(), out[1].tolist())

    def test_a_sight_line_along_a_cells_edge_reads_one_cell_in_any_box(self):
        # (#812, rasinovo-quay: a line of sight along x = -744, its sample's x -744 within 1e-13 m, read the wet cell
        # west of the edge with one ring of tiles and the dry one east of it with two. Here the line runs along the
        # lake's east edge in the raster, and a pond far west moves the raster's origin from -50 to -2000)
        lake, pond = shapely.box(-50, -50, 0, 50), shapely.box(-2000, -1000, -1990, -990)
        W = shapely.union_all([lake, pond])
        ipr = Ipr(lambda x, y: np.full(np.shape(x), 10.0))
        lvs = [gp.WaterLevels(W, [], ipr, Frame(), extent=e) for e in (shapely.box(-100, -100, 100, 100), shapely.box(-2100, -1100, 100, 100))]
        # (the first dry cell's west edge on the row of y = 0; past the raster's end a cell is dry)
        edges = [lv.x0 + np.flatnonzero(lv.grid[int(lv.y1), :])[-1] + 1 for lv in lvs]
        self.assertEqual(edges[0], edges[1])
        seen = []
        for lv in lvs:
            lv.P = np.array([[edges[0] - 1e-13, 20.0]])
            seen.append(lv._seen(np.array([edges[0] - 1e-13, -20.0]), np.array([0])).tolist())
        self.assertEqual(seen[0], seen[1])

    def test_no_bank_farther_than_water_far(self):
        # (a lake's middle, 600 m from every bank: no level, where the old fallback read banks at any distance; the
        # build gives such a corner the lidar's height. Prague's widest water, the Vltava, is under 400 m across)
        W = shapely.Point(0, 0).buffer(600, 64)
        lv = gp.WaterLevels(W, [], Ipr(lambda x, y: np.full(np.shape(x), 10.0)), Frame())
        z = lv.at(np.array([0.0, 450.0]), np.array([0.0, 0.0]))
        self.assertTrue(np.isnan(z[0]))
        self.assertEqual(z[1], 10.0)


if __name__ == "__main__":
    unittest.main()
