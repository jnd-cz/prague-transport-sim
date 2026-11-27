# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/street_profile.py: street profiles, crossfall, the junctions' fill and the drive-line measures (#512).

    python -P -E tools/test_street_profile.py
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import street_profile as sp  # noqa: E402


def way(i, name, nodes, xy, highway="residential", oneway="no"):
    return {"id": i, "name": name, "highway": highway, "oneway": oneway, "nodes": nodes, "xy": np.asarray(xy, float)}


class Profiles(unittest.TestCase):
    def test_ways_of_one_name_join_end_to_end(self):
        ws = [way(1, "A", [1, 2], [(0, 0), (10, 0)]), way(2, "A", [3, 2], [(20, 0), (10, 0)]),
              way(3, "B", [2, 4], [(10, 0), (10, 10)])]
        cs = sp.chains(ws)
        a = next(c for c in cs if c["name"] == "A")
        self.assertEqual(a["nodes"], [1, 2, 3])
        self.assertEqual(len(cs), 2)

    def test_a_dual_carriageway_is_not_joined_round_its_end(self):
        # (Hartigova: the two one-way carriageways share their west end node)
        ws = [way(1, "H", [1, 2], [(100, 0), (0, 0)], oneway="yes"), way(2, "H", [2, 3], [(0, 0), (100, 40)], oneway="yes"),
              way(3, "H", [3, 4], [(100, 40), (200, 40)], oneway="yes")]
        cs = sp.chains(ws)
        self.assertEqual(sorted(len(c["ids"]) for c in cs), [1, 2])

    def test_resample_every_metre(self):
        s, p, t = sp.resample(np.array([(0, 0), (10, 0), (10, 5)], float))
        self.assertEqual(len(s), 15)
        self.assertTrue(np.allclose(p[12], (10, 2)))
        self.assertTrue(np.allclose(t[12], (0, 1)))

    def test_profile_smooths_noise_and_keeps_the_radius(self):
        s = np.arange(0, 200.0)
        true = 200 + 0.03 * s - 0.03 * np.maximum(s - 100, 0) ** 2 / 200  # a grade into a crest of R 3333 m
        rng = np.random.default_rng(3)
        z = sp.profile(s, true + rng.normal(0, 0.02, len(s)), rmin=500)
        self.assertLess(np.abs(z - true).max(), 0.03)
        k = np.abs(np.diff(z, 2))
        self.assertLessEqual(k.max(), 1 / 500 * 1.05)

    def test_a_pinned_street_meets_its_governing_one(self):
        s = np.arange(0, 60.0)
        z = sp.profile(s, 300 + 0.02 * s, rmin=150, pins=[0, 1, 2], pin_z=np.array([299.8, 299.82, 299.84]))
        self.assertAlmostEqual(z[0], 299.8, places=2)
        self.assertLess(abs(z[-1] - (300 + 0.02 * 59)), 0.05)


class Junctions(unittest.TestCase):
    def test_the_fill_follows_a_tilted_junction_through_the_noise(self):
        # a junction tilted 2 % one way and 1 % the other (Palmovka's, by the tracks), lidar noise 3 cm, held at its
        # two streets' edges
        n = 60
        Y, X = np.mgrid[0:n, 0:n].astype(float)
        plane = 190 + 0.02 * X - 0.01 * Y
        data = plane + np.random.default_rng(1).normal(0, 0.03, plane.shape)
        known = np.full(plane.shape, np.nan)
        known[:, :3], known[:, -3:] = plane[:, :3], plane[:, -3:]
        g = sp.fill_2d(known, np.isnan(known), data, (sp.JUNCTION_WAVE / (2 * math.pi)) ** 4)
        self.assertLess(np.sqrt(((g - plane) ** 2).mean()), 0.01)
        self.assertLess(np.abs(g - plane).max(), 0.03)

    def test_a_raised_bed_keeps_its_kerb(self):
        # a bed 0.15 m over a flat road beside it (Hartigova's raised belt): held, but the road is not drawn up to it
        n = 40
        Y, X = np.mgrid[0:n, 0:n].astype(float)
        data = np.full((n, n), 200.0)
        known = np.full((n, n), np.nan)
        known[:, 18:22] = 200.15
        kerb = np.isfinite(known)
        lam = (sp.JUNCTION_WAVE / (2 * math.pi)) ** 4
        free = np.isnan(known)
        drawn = sp.fill_2d(known, free, data, lam)
        kept = sp.fill_2d(known, free, data, lam, kerb=kerb)
        self.assertGreater(drawn[:, 17].mean() - 200, 0.05)  # (without the kerb the road climbs to the bed)
        self.assertLess(np.abs(kept[:, :18] - 200).max(), 0.005)

    def test_raised_reads_ipr_not_the_track_heights(self):
        # a 3 m corridor 0.2 m over the road in IPR, the tracks' heights 0.13 m under its top (Hartigova): raised; a
        # level corridor, the tracks' heights 0.25 m over it (Olšanské hřbitovy, #606): not
        from types import SimpleNamespace
        from shapely.geometry import box
        s = np.arange(0, 40.0)
        c = {"s": s, "p": np.column_stack([s, np.zeros(len(s))]), "t": np.tile([1.0, 0.0], (len(s), 1)),
             "half": np.full(len(s), 0.8), "width": np.full((len(s), 2), 1.5)}
        road = box(-5, -10, 45, 10)
        F = SimpleNamespace(E0=0.0, N0=0.0)
        raised = SimpleNamespace(sample=lambda x, y: np.where(np.abs(np.asarray(y, float)) <= 1.5, 200.2, 200.0))
        level = SimpleNamespace(sample=lambda x, y: np.full(len(np.atleast_1d(x)), 200.0))
        self.assertTrue(sp.raised_bed(dict(c, z=np.full(len(s), 200.07)), F, raised, road).all())
        self.assertFalse(sp.raised_bed(dict(c, z=np.full(len(s), 200.25)), F, level, road).any())
        # (#606: on a corridor the maintainer confirmed, IPR level across it, the tracks' own surface decides: raised there,
        # not where the tracks stand within RAISED_BED of IPR beside)
        on = s < 25
        got = sp.raised_bed(dict(c, z=np.full(len(s), 200.25)), F, level, road, on)
        self.assertTrue(got[on].all())
        self.assertFalse(got[~on].any())
        self.assertFalse(sp.raised_bed(dict(c, z=np.full(len(s), 200.05)), F, level, road, on).any())
        # (a road 8 m wide across the confirmed corridor, s 10-18: the survey's own tram area has a gap there, a level
        # crossing. No sample of it is raised; the corridor either side stays so. IPR's own reading keeps a crossing
        # the old way, by its ramp)
        own = box(-5, -3, 10, 3).union(box(18, -3, 45, 3))
        got = sp.raised_bed(dict(c, z=np.full(len(s), 200.25)), F, level, road, on, own)
        cross = (s > 10) & (s < 18)
        self.assertFalse(got[cross].any())
        self.assertTrue(got[on & ((s < 10) | (s > 18))].all())
        self.assertTrue(sp.raised_bed(dict(c, z=np.full(len(s), 200.07)), F, raised, road, on, own).all())

    @unittest.skipUnless(__import__("geo").have_grid(), __import__("geo").NO_GRID)
    def test_a_confirmed_corridor_lies_between_its_ends(self):
        from geo import Frame
        F = Frame()
        a, b = (50.078425, 14.47248), (50.077978, 14.463804)
        ax, ay = (float(np.ravel(v)[0]) for v in F.xy([a[0]], [a[1]]))
        bx, by = (float(np.ravel(v)[0]) for v in F.xy([b[0]], [b[1]]))
        places = [{"line": 9, "from": list(a), "to": list(b)}, {"line": 37, "lat": a[0], "lon": a[1]}]
        mid = ((ax + bx) / 2, (ay + by) / 2)
        p = np.array([mid, (mid[0], mid[1] + 5), (mid[0], mid[1] + 20), (ax + (ax - bx) * 0.05, ay + (ay - by) * 0.05)])
        self.assertEqual(sp.confirmed_corridor(9, p, places).tolist(), [True, True, False, False])
        self.assertFalse(sp.confirmed_corridor(37, p, places).any())

    def test_street_geometry_from_truth(self):
        r, other, belt, fall, walk = sp.street_geometry()
        self.assertEqual((r["primary"], r["living_street"], other, belt, fall, walk),
                         (500.0, 100.0, 150.0, 0.07, 0.06, (0.005, 0.02)))

    def test_bilinear_reads_the_edge(self):
        g = np.array([[1.0, 2.0], [np.nan, 4.0]])
        z = sp.bilinear((0.0, 1.0, 1.0, g), np.array([0.5]), np.array([0.5]))
        self.assertTrue(np.isfinite(z[0]))


class CrownReach(unittest.TestCase):
    def test_a_streets_width_ends_where_its_crown_leaves_the_ground(self):
        # (#780: a street along y = 0 on ground level across but for a mouth 8 m long at x = 46..54, where the ground
        # falls 6.5 % to the south: the level crown is 0.15 m off the ground 2.5 m out, and the south half width ends
        # at the least a street keeps, a lane; so it does 3 m before and after the mouth, and not 6 m before; elsewhere
        # it is the road area's, and so is the north side's)
        from types import SimpleNamespace
        from shapely.geometry import box
        s = np.arange(0.0, 101.0, 1.0)
        p = np.column_stack([s, np.zeros(len(s))])
        t = np.tile([1.0, 0.0], (len(s), 1))

        def ground(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            return 200.0 + np.where((x > 46) & (x < 54) & (y < 0), 0.065 * y, 0.0)
        fall, width = sp.crossfall(SimpleNamespace(E0=0.0, N0=0.0), SimpleNamespace(sample=ground), p, t, box(-5, -8, 105, 8), s)
        south = 1 if width[50, 1] < width[50, 0] else 0
        self.assertAlmostEqual(float(width[50, south]), sp.FALL_MIN)
        self.assertAlmostEqual(float(width[44, south]), sp.FALL_MIN)
        self.assertGreater(float(width[40, south]), 7.0)
        self.assertGreater(float(width[50, 1 - south]), 7.0)
        self.assertGreater(float(width[20].min()), 7.0)


class Parking(unittest.TestCase):
    def test_a_parking_area_is_in_the_roads_fill_unless_under_a_deck(self):
        # three level-0 car parks: one in the open, one 40 % under a deck, one 20 % under it; and one on level 1:
        # the open one and the one 20 % under the deck join the road's fill (#800)
        import shapely
        from shapely.geometry import box

        def area(x0, c="parking", lv=0):
            return {"c": c, "l": lv, "r": [[x0, 0, 200], [x0 + 10, 0, 200], [x0 + 10, 10, 200], [x0, 10, 200]]}
        dtm = {"areas": [area(0), area(20), area(40), area(60, lv=1), area(80, c="road"),
                         area(26, c="deck", lv=1), area(48, c="deck", lv=1)]}
        _, cover = sp.street_areas(dtm)
        park = sp.parking_area(dtm, cover)
        inside = shapely.contains_xy(park, [5, 25, 45, 65, 85], [5] * 5).tolist()
        self.assertEqual(inside, [True, False, True, False, False])
        self.assertAlmostEqual(park.area, 200.0)
        self.assertTrue(sp.parking_area({"areas": [area(0)]}, None).equals(box(0, 0, 10, 10)))


class Sidewalks(unittest.TestCase):
    def test_a_kerb_round_a_corner_in_short_edges_is_a_kerb(self):
        # a sidewalk whose kerb turns a corner in edges of 0.77 m (a quarter circle of radius 4 m round (4, 4)), then
        # runs 10 m straight and 0.3 m on: one kerb, its normals turning with it into the sidewalk; a lone 0.3 m kerb
        # edge is a jog, none (#800: such edges were none under 3 m each, and the walkway had no plane there)
        import shapely
        ang = np.linspace(math.pi, 1.5 * math.pi, 7)
        arc = [(4 + 4 * math.cos(a), 4 + 4 * math.sin(a), 200.1) for a in ang]   # (0, 4) round to (4, 0)
        ring = arc + [(14.0, 0.0, 200.1), (14.3, 0.0, None), (14.3, 8.0, 200.2), (0.0, 8.0, 200.2)]
        k = [True] * 6 + [True, True, False, False, False]   # (the arc's six edges, the 10 m kerb, the 0.3 m edge)
        jog = [[20, 0, 200.1], [20.3, 0, 200.1], [20.3, 5, 200.1], [20, 5, 200.1]]
        dtm = {"areas": [{"c": "sidewalk", "l": 0, "r": [list(p) for p in ring], "k": [k]},
                         {"c": "sidewalk", "l": 0, "r": jog, "k": [[True, False, False, False]]}]}
        edges, walk = sp.kerb_edges(dtm)
        self.assertEqual(len(edges), 8)   # (one run, given edge by edge: wall_tops judges each edge on its own)
        self.assertEqual([len(e[0]) for e in edges][6], 40)   # (the 10 m edge, every 0.25 m)
        self.assertEqual([e[3] for e in edges], [False] * 6 + [True, False])   # (only the 10 m edge may be a wall's top)
        q, n, own = (np.concatenate([e[i] for e in edges]) for i in range(3))
        self.assertAlmostEqual(len(q) * 0.25, 2 * math.pi + 10.3, delta=0.3)  # (the arc 2 pi m, then 10.3 m)
        self.assertTrue(shapely.contains_xy(walk, *(q + n * 0.2).T).all())   # (every normal into the sidewalk)
        mid = np.argmin(np.hypot(*(q - (4 - 4 * math.sqrt(0.5), 4 - 4 * math.sqrt(0.5))).T))
        self.assertAlmostEqual(float(n[mid] @ np.array([math.sqrt(0.5), math.sqrt(0.5)])), 1.0, delta=0.01)
        self.assertAlmostEqual(float(own[mid]), 200.1)
        self.assertTrue(np.isnan(own[-1]))   # (the 0.3 m edge's far end has no height)
        # (and each point's normal of its own edge, into the sidewalk: the 10 m edge's straight across it to its ends)
        ne = np.concatenate([e[4] for e in edges])
        self.assertTrue(shapely.contains_xy(walk, *(q + ne * 0.2).T).all())
        self.assertTrue(np.allclose(edges[6][4], [0.0, 1.0]))

    def test_held_at_the_kerb_and_rising_with_the_ground(self):
        # a 20 m by 4 m sidewalk beside a flat road at 200 m, the ground rising 2 % away from the kerb: within the
        # sidewalks' range, the walkway takes it
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: 200.10 + 0.02 * np.asarray(y, float))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 4),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))]}
        f = sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.0), [(0, 0), (20, 4)])
        z = sp.bilinear(f, np.array([10.0, 10.0]), np.array([0.25, 3.0]))
        self.assertAlmostEqual(z[0], 200.105, delta=0.006)  # (the road, the measured kerb (kerbs.KERB) and 0.25 m at 2 %)
        self.assertAlmostEqual(z[1], 200.16, delta=0.015)  # (the ground's 2 %)

    def test_a_steep_ground_gives_a_walkway_at_the_norm(self):
        # the ground rising 6 % across a 4 m sidewalk: the walkway rises 2 % (data/truth.json sidewalk-crossfall)
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: 200.10 + 0.06 * np.asarray(y, float))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 4),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))]}
        f = sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.0), [(0, 0), (20, 4)])
        z = sp.bilinear(f, np.array([10.0]), np.array([3.0]))
        self.assertAlmostEqual(z[0], 200.16, delta=0.01)

    def test_a_walkway_ends_at_a_wall(self):
        # a 6 m sidewalk whose ground steps up 2 m at 3 m from the kerb (a wall inside the survey's area): the walkway
        # holds the kerb's plane up to the wall, and beyond it the ground, not the plane
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: np.where(np.asarray(y, float) > 3.0, 202.10, 200.10))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 6),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))]}
        f = sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.0), [(0, 0), (20, 6)])
        z = sp.bilinear(f, np.array([10.0, 10.0]), np.array([1.5, 5.0]))
        self.assertLess(abs(z[0] - 200.12), 0.03)
        self.assertGreater(z[1], 201.8)

    def test_no_walkers_line_on_a_wall(self):
        # the walker's line 1.5 m in runs along a wall's face (IPR rising 3 m across it): left out of the steps, for
        # every surface, and counted
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: 200.0 + 3.0 * np.clip(np.asarray(y, float) - 1.0, 0, 1))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 4),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))]}
        rough = sp.sidewalk_measures(ctx, lambda x, y: 200.0 + 0.5 * (np.floor(np.asarray(x, float)) % 2),
                                     lambda x, y: np.full(len(np.atleast_1d(x)), 199.9), [(0, 0), (20, 4)])
        self.assertEqual(rough["walker's steps"], 0)
        self.assertGreater(rough["walker's metres on a wall, left out"], 10)

    def test_wall_edges_are_the_sidewalks_own_edges_on_a_wall(self):
        # (a sidewalk whose far edge is a wall's top: that edge, at the sidewalk's own heights; not its kerb or its ends)
        sw = {"c": "sidewalk", "l": 0, "r": [[0, 0, 200.1], [20, 0, 200.1], [20, 6, 200.3], [0, 6, 200.2]]}
        wall = {"c": "wall", "l": 0, "r": [[0, 6, 200.2], [20, 6, 200.3], [20, 6.3, 198.0], [0, 6.3, 198.0]]}
        e = sp.wall_edges({"areas": [sw, wall]})
        self.assertEqual(e.tolist(), [[[20, 6, 200.3], [0, 6, 200.2]]])

    def test_a_wall_holds_the_walkway_at_its_top(self):
        # a 6 m sidewalk whose far edge is a wall's top at 200.2 m, the street 2 m below it; IPR's raster spreads the
        # wall's face from 4 to 7 m: the fill holds the sidewalk's own edge and takes no pull within 1.5 m of it (#653: the
        # walkway sank 0.5 m into the top of Krejcárek's ramp wall)
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: 200.2 - 2.0 * np.clip((np.asarray(y, float) - 4.0) / 3.0, 0, 1))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 6),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))],
               "wall_edges": np.array([[[20, 6, 200.2], [0, 6, 200.2]]])}  # (the sidewalk on its left)
        f = sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.1), [(0, 0), (20, 6)])
        z = sp.bilinear(f, np.array([10.0, 10.0]), np.array([5.0, 5.9]))
        self.assertAlmostEqual(z[1], 200.2, delta=0.03)  # (between the held row and a free one, 0.5 m in)
        self.assertGreater(z[0], 200.1)
        ctx.pop("wall_edges")
        z0 = sp.bilinear(sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.1), [(0, 0), (20, 6)]),
                         np.array([10.0]), np.array([5.9]))
        self.assertLess(z0[0], 199.8)  # (without it: IPR's smear)

    def test_a_kerb_edge_over_a_sunk_road_is_a_walls_top(self):
        # (#779: a 4 m sidewalk surveyed level at 200.4 m beside a ramp falling from 200.3 to 198.3 m along it; IPR's
        # raster spreads the step over the sidewalk's first 1.5 m. Its edge keeps its own height from where it stands
        # 0.3 m over a kerb on the ramp; at the ramp's head it is a kerb. Without its own heights: the ramp plus a kerb)
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)

        def ramp(x, y):
            return 200.3 - 0.1 * np.asarray(x, float)
        ipr = SimpleNamespace(sample=lambda x, y: ramp(x, y) + (200.4 - ramp(x, y)) * np.clip(np.asarray(y, float) / 1.5, 0, 1))
        edge = (np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 4),
               "kerb_edges": [edge + (np.full(len(u), 200.4),)]}
        z = sp.bilinear(sp.sidewalks(ctx, ramp, [(0, 0), (20, 4)]), np.array([15.0, 15.0, 1.0]), np.array([0.25, 3.0, 0.25]))
        self.assertAlmostEqual(z[0], 200.4, delta=0.03)
        self.assertAlmostEqual(z[1], 200.4, delta=0.03)
        self.assertAlmostEqual(z[2], 200.3, delta=0.05)  # (the head: the ramp at 200.2 m and a kerb)
        # (the same edge too short for a wall's, street_profile.WALL_EDGE_MIN: where it is no plain kerb it is held at
        # nothing, its walkway on the fill; at the head still a kerb's plane, #800)
        ctx["kerb_edges"] = [edge + (np.full(len(u), 200.4), False)]
        zs = sp.bilinear(sp.sidewalks(ctx, ramp, [(0, 0), (20, 4)]), np.array([15.0, 1.0]), np.array([0.25, 0.25]))
        self.assertLess(zs[0], 200.0)
        self.assertAlmostEqual(zs[1], 200.3, delta=0.05)
        top, segs = sp.wall_tops(edge[0], edge[1], np.full(len(u), 200.4), ramp(u, 0 * u))
        self.assertEqual((int(top.argmax()), segs.shape, segs[0, :, 2].tolist()), (12, (68, 2, 3), [200.4, 200.4]))
        self.assertFalse(sp.wall_tops(edge[0], edge[1], np.full(len(u), 200.4), np.full(len(u), 199.9))[0].any())
        # (the edge's height a parapet's, 1.1 m over the ground inside the sidewalk: none)
        self.assertFalse(sp.wall_tops(edge[0], edge[1], np.full(len(u), 200.4), ramp(u, 0 * u), np.full(len(u), 199.3))[0].any())
        # (#770: at the foot of a road's wall. The edge's own height the wall's top, 1.5 m over the ground inside a
        # sidewalk 4 m wide: the walkway is the ground's, 1.5 m under the road, a wall's edge; a sidewalk 1.6 m wide
        # cannot tell)
        high = np.full(len(u), 201.5)
        top, segs = sp.wall_tops(edge[0], edge[1], np.full(len(u), 201.4), high, np.full(len(u), 199.9), np.ones(len(u), bool))
        self.assertEqual((bool(top.all()), segs[0, :, 2].tolist()), (True, [199.9, 199.9]))
        self.assertFalse(sp.wall_tops(edge[0], edge[1], np.full(len(u), 201.4), high, np.full(len(u), 199.9), np.zeros(len(u), bool))[0].any())
        # (its own height the foot's: under the road by its own height)
        top, segs = sp.wall_tops(edge[0], edge[1], np.full(len(u), 199.9), high, np.full(len(u), 199.95), np.zeros(len(u), bool))
        self.assertEqual((bool(top.all()), segs[0, :, 2].tolist()), (True, [199.9, 199.9]))
        # (on a quay wall's top, the drop behind a walkway 1.2 m wide: the ground 1.5 m in lies on the wall's face, 1.7 m
        # under the edge, and IPR 0.5-1 m in at the edge's own height: an ordinary kerb. At a wall's foot IPR that near
        # is the walkway's already)
        level = np.full(len(u), 200.0)
        near = np.column_stack([level + 0.05, level + 0.08, level - 0.35])
        self.assertFalse(sp.wall_tops(edge[0], edge[1], level, level - 0.05, level - 1.7, np.ones(len(u), bool), near)[0].any())
        self.assertTrue(sp.wall_tops(edge[0], edge[1], level, level - 0.05, level - 1.7, np.ones(len(u), bool))[0].all())
        foot = np.column_stack([np.full(len(u), 200.3), np.full(len(u), 199.95), np.full(len(u), 199.9)])
        top, segs = sp.wall_tops(edge[0], edge[1], np.full(len(u), 201.4), high, np.full(len(u), 199.9), np.ones(len(u), bool), foot)
        self.assertEqual((bool(top.all()), segs[0, :, 2].tolist()), (True, [199.9, 199.9]))
        # (at a wall's foot with the edge's height between the two levels, 0.6 m over the walkway, and the raster's smear
        # of the wall at that height 0.5 m in: no plain kerb, the walkway is the ground's)
        smear = np.column_stack([np.full(len(u), 200.6), np.full(len(u), 200.1), np.full(len(u), 199.9)])
        top, segs = sp.wall_tops(edge[0], edge[1], np.full(len(u), 200.5), high, np.full(len(u), 199.9), np.ones(len(u), bool), smear)
        self.assertEqual((bool(top.all()), segs[0, :, 2].tolist()), (True, [199.9, 199.9]))
        # (#800: the verge by a car park on line 22 (3449, -2602). Its edge surveyed at 211.38 m, 0.41 m off IPR 1.5 m in,
        # the car park's surface 212.04 m beyond: a wall 0.66 m down by the heights, but IPR 1 m in lies 0.14 m under
        # the car park, the verge's slope. No wall; by the heights alone, one)
        n = len(u)
        verge = np.column_stack([np.full(n, 211.95), np.full(n, 211.90), np.full(n, 211.85)])
        args = (edge[0], edge[1], np.full(n, 211.38), np.full(n, 212.04), np.full(n, 211.79), np.ones(n, bool))
        self.assertTrue(sp.wall_tops(*args)[0].all())
        self.assertFalse(sp.wall_tops(*args, verge)[0].any())
        # (half of it borne, IPR 1 m in 0.33 m under the car park: a wall)
        self.assertTrue(sp.wall_tops(*args, verge - 0.2)[0].all())
        # (#834: a wall at the street with the walkway 1.8 m lower beside a building, line 17 (-360, 30). The walkway's
        # level is IPR's 1.5 m in, on a sidewalk 4 m wide; the wall some 0.7-1.2 m in, IPR 1 m in bears 0.40 of the step,
        # or 0.28 where it stands furthest in: a wall. The same IPR 1 m in bearing 0.2: none)
        run = (edge[0], edge[1], np.full(n, 190.26), np.full(n, 190.72), np.full(n, 188.92), np.ones(n, bool))
        lean = np.column_stack([np.full(n, 190.57), np.full(n, 190.30), np.full(n, 190.00)])
        self.assertTrue(sp.wall_tops(*run, lean)[0].all())
        self.assertTrue(sp.wall_tops(*run, lean + np.array([0.0, 0.0, 0.22]))[0].all())
        self.assertFalse(sp.wall_tops(*run, lean + np.array([0.0, 0.0, 0.36]))[0].any())
        # (#834: Bělohorská, line 22 (-4159, 149), a street the maintainer found plain. The walkway's level IPR's 1.5 m in,
        # 2.34 m over the road, IPR 1 m in bearing 0.38 of it, but 0.5 m in 2.68 m under the road: no wall's smear)
        up = (edge[0], edge[1], np.full(n, 320.87), np.full(n, 320.40), np.full(n, 322.74), np.ones(n, bool))
        dip = np.column_stack([np.full(n, 317.72), np.full(n, 318.40), np.full(n, 321.30)])
        self.assertFalse(sp.wall_tops(*up, dip)[0].any())
        self.assertTrue(sp.wall_tops(*up, dip + np.array([2.70, 2.00, 0.0]))[0].all())
        ctx["kerb_edges"] = [edge]
        z0 = sp.bilinear(sp.sidewalks(ctx, ramp, [(0, 0), (20, 4)]), np.array([15.0]), np.array([0.25]))
        self.assertLess(z0[0], 199.5)

    def test_wall_heights_take_the_nearest_edge(self):
        # (the sidewalk on the edge's left; a cell on its right, the wall's other level, does not take it)
        X, Y = np.meshgrid(np.arange(0, 4.1, 0.5), np.array([0.0, 1.0, 3.0, -0.5]))
        z, d, q, n = sp.wall_heights(np.array([[[0, 0, 10.0], [4, 0, 12.0]]]), X, Y, np.ones(X.shape, bool), 1.5)
        self.assertAlmostEqual(z[0, 4], 11.0)
        self.assertAlmostEqual(d[1, 4], 1.0)
        self.assertEqual(q[1, 4].tolist(), [2.0, 0.0])
        self.assertEqual(n[1, 4].tolist(), [0.0, 1.0])  # (into the sidewalk)
        self.assertTrue(np.isnan(z[2]).all() and np.isinf(d[2]).all())
        self.assertTrue(np.isnan(z[3]).all())

    def test_the_walls_level_nearest_the_reference(self):
        # (a wall 2 m tall: its top and its foot within a metre; the sidewalk's own outline said the foot, IPR beside the
        # wall the top: the top. Without a reference, its own)
        wall = {"c": "wall", "l": 0, "r": [[0, 0, 230.6], [10, 0, 230.6], [10, 0.3, 228.56], [0, 0.3, 228.56]]}
        lv = sp.WallLevels({"areas": [wall]})
        got = lv.pick(np.array([5.0, 0.2, 5.0]), np.array([0.0, 0.0, 0.0]), np.array([228.56, 228.56, 228.56]),
                      np.array([230.4, 228.7, np.nan]))
        self.assertEqual(got.tolist(), [228.56, 228.56, 228.56])  # (no wall vertex within 1 m of (5, 0): its own)
        got = lv.pick(np.array([0.2, 0.2]), np.array([0.1, 0.1]), np.array([228.56, 228.56]), np.array([230.4, 228.7]))
        self.assertEqual(got.tolist(), [230.6, 228.56])

    def test_a_wall_edge_runs_with_its_sidewalk_on_its_left(self):
        # (the same edge drawn the other way round its ring: turned)
        sw = {"c": "sidewalk", "l": 0, "r": [[0, 6, 200.2], [20, 6, 200.3], [20, 0, 200.1], [0, 0, 200.1]]}
        wall = {"c": "wall", "l": 0, "r": [[0, 6, 200.2], [20, 6, 200.3], [20, 6.3, 198.0], [0, 6.3, 198.0]]}
        self.assertEqual(sp.wall_edges({"areas": [sw, wall]}).tolist(), [[[20, 6, 200.3], [0, 6, 200.2]]])


class Strips(unittest.TestCase):
    """(#786) a paved strip is a wall for the sidewalk beside it: a wall's face in plan, or one the ground steps across"""

    def test_a_paved_strip_that_is_a_walls_face_is_a_wall_for_the_sidewalk(self):
        # (a sidewalk whose far edge is the top's side of a paved strip 0.2 m across, the strip's other side 2.3 m lower:
        # its edge is a wall edge, as on a wall area. A paved yard 6 m across, and a strip on the lidar's ground: none)
        sw = {"c": "sidewalk", "l": 0, "r": [[0, 0, 200.1], [20, 0, 200.1], [20, 6, 200.3], [0, 6, 200.2]]}
        face = {"c": "paved", "l": 0, "r": [[0, 6, 200.2], [20, 6, 200.3], [20, 6.2, 198.0], [0, 6.2, 198.0]]}
        yard = {"c": "paved", "l": 0, "r": [[0, 6, 200.2], [20, 6, 200.3], [20, 12, 198.0], [0, 12, 198.0]]}
        self.assertEqual(sp.wall_edges({"areas": [sw, face]}).tolist(), [[[20, 6, 200.3], [0, 6, 200.2]]])
        self.assertEqual(len(sp.wall_areas({"areas": [sw, face, yard, dict(face, g=1), dict(face, l=1)]})), 1)
        self.assertEqual(len(sp.wall_edges({"areas": [sw, yard]})), 0)

    def test_a_strip_the_ground_steps_across_holds_the_walkway_on_its_side(self):
        # a 6 m sidewalk whose far edge lies on a strip with the ground 2 m lower beyond it; IPR's raster spreads the
        # step from 4 to 7 m. The cells along the strip are held at the ground's level on the sidewalk's side, with no
        # pull from IPR within 1.5 m of it
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: 200.2 - 2.0 * np.clip((np.asarray(y, float) - 4.0) / 3.0, 0, 1))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 6),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))],
               "strip_edges": lambda b: (np.array([[[20, 6, 200.2], [0, 6, 200.2]]]), np.array([3.0]))}
        road = lambda x, y: np.full(len(np.atleast_1d(x)), 200.1)  # noqa: E731
        z = sp.bilinear(sp.sidewalks(ctx, road, [(0, 0), (20, 6)]), np.array([10.0, 10.0]), np.array([5.0, 5.9]))
        self.assertAlmostEqual(z[1], 200.2, delta=0.03)
        self.assertGreater(z[0], 200.1)
        ctx.pop("strip_edges")
        self.assertLess(sp.bilinear(sp.sidewalks(ctx, road, [(0, 0), (20, 6)]), np.array([10.0]), np.array([5.9]))[0], 199.8)
        # (a walkway 0.6 m wide between the strip and a road: IPR has no reading of it, and it stands a kerb over the
        # road past it, not at the smear its strip's edge was given)
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 0.6), "kerb_edges": [],
               "strip_edges": lambda b: (np.array([[[0, 0, 201.0], [20, 0, 201.0]]]), np.array([0.6]))}
        z = sp.bilinear(sp.sidewalks(ctx, road, [(0, 0), (20, 1)]), np.array([10.0]), np.array([0.25]))
        self.assertAlmostEqual(z[0], 200.1 + 0.1, delta=0.02)

    def test_strip_edges_are_a_strips_sides_the_ground_steps_across(self):
        # (a strip 0.2 m across along y = 6..6.2, a sidewalk south of it at 200.2 m and the ground north of it at
        # 196.4 m: its south side's edges, the sidewalk on their left, at IPR 1.5 m in. The ground level across it: none)
        from shapely.geometry import box
        strip = np.array([[0, 6, 198.5], [20, 6, 198.5], [20, 6.2, 198.5], [0, 6.2, 198.5], [0, 6, 198.5]], float)
        e, w = sp.strip_edges("0", box(0, 0, 20, 6), [(0, 0), (20, 6)],
                              lambda x, y: np.where(np.asarray(y, float) > 6.1, 196.4, 200.2), [strip])
        self.assertEqual((e.shape, w.tolist()), ((20, 2, 3), [3.0] * 20))
        np.testing.assert_allclose(e[0], [[1.0, 6.0, 200.2], [0.0, 6.0, 200.2]], atol=1e-9)
        self.assertEqual(len(sp.strip_edges("0", box(0, 0, 20, 6), [(0, 0), (20, 6)], lambda x, y: 200.2 + 0 * np.asarray(y, float), [strip])[0]), 0)
        # (a ramp 2 m wide between that strip and another, rising 5 % along them, the ground 1.5 m higher behind one
        # and 1.5 m lower behind the other, IPR smearing both across the ramp: both strips' edges on the ramp, at IPR
        # halfway across it)
        other = strip + [0, -2.2, 0]

        def ramp(x, y):
            x, y = np.asarray(x, float), np.asarray(y, float)
            return 198.0 + 0.05 * x + 1.5 * np.clip((y - 5.0) / 1.0, -1, 1)
        e, w = sp.strip_edges("0", box(0, 4, 20, 6), [(0, 0), (20, 6)], ramp, [strip, other])
        self.assertEqual(e.shape, (40, 2, 3))
        np.testing.assert_allclose(w, 2.0, atol=0.03)
        np.testing.assert_allclose(e[:, 0, 2], 198.0 + 0.05 * e[:, :, 0].mean(1), atol=0.07)  # (an end's mean is over fewer)

    def test_a_strips_sides_keep_their_own_levels_round_its_corners(self):
        # (a strip 1 m across with a sidewalk all round it, at 200.2 m south of its middle and 196.4 m north: each long
        # side's edges at its own walkway's level right up to the corners, its two ends no edges; a block 2 m long none)
        from shapely.geometry import box

        def lidar(x, y):
            return np.where(np.asarray(y, float) > 6.5, 196.4, 200.2) + 0 * np.asarray(x, float)
        strip = np.array([[0, 6, 198.5], [20, 6, 198.5], [20, 7, 198.5], [0, 7, 198.5], [0, 6, 198.5]], float)
        e, w = sp.strip_edges("0", box(-10, -4, 30, 17), [(-10, -4), (30, 17)], lidar, [strip])
        self.assertEqual(len(e), 40)
        self.assertEqual(sorted(set(np.round(e[:, :, 1].mean(1), 3).tolist())), [6.0, 7.0])
        np.testing.assert_allclose(e[:, 0, 2], np.where(e[:, 0, 1] < 6.5, 200.2, 196.4), atol=1e-9)
        block = np.array([[9, 6, 198.5], [11, 6, 198.5], [11, 7, 198.5], [9, 7, 198.5], [9, 6, 198.5]], float)
        self.assertEqual(len(sp.strip_edges("0", box(-10, -4, 30, 17), [(-10, -4), (30, 17)], lidar, [block])[0]), 0)

    def test_a_sidewalk_runs_in_unbroken(self):
        # (a sidewalk 0.6 m wide and another behind a strip 0.2 m across: 2 m in from the first one's kerb is a
        # sidewalk, but not the same one)
        from shapely.geometry import box
        q, n = np.array([[5.0, 0.0], [15.0, 0.0]]), np.tile([0.0, 1.0], (2, 1))
        self.assertEqual(sp.runs_in(box(0, 0, 20, 0.6).union(box(0, 0.8, 20, 4)), q, n, 2.0).tolist(), [False, False])
        self.assertEqual(sp.runs_in(box(0, 0, 20, 4), q, n, 2.0).tolist(), [True, True])
        self.assertEqual(sp.runs_in(None, q, n, 2.0).tolist(), [False, False])
        self.assertEqual(sp.runs_in(box(0, 0, 20, 4), q, n, np.array([2.0, 5.0])).tolist(), [True, False])

    def test_a_kerbs_walkway_ends_at_a_strip_between_two_sidewalks(self):
        # (a sidewalk 0.9 m wide at a road's kerb, a parapet 0.2 m across behind it, between the plane's samples at
        # 0.75 and 1.0 m... and a ramp 1.5 m over the road behind the parapet: the kerb's plane stays before the
        # parapet, and the ramp's cells follow the ground)
        from types import SimpleNamespace
        from shapely.geometry import box
        u = np.arange(0.125, 20, 0.25)
        ipr = SimpleNamespace(sample=lambda x, y: np.where(np.asarray(y, float) > 1.3, 201.6, 200.1))
        ctx = {"F": SimpleNamespace(E0=0.0, N0=0.0), "ipr": ipr, "walk": box(0, 0, 20, 0.9).union(box(0, 1.1, 20, 4)),
               "kerb_edges": [(np.column_stack([u, np.zeros(len(u))]), np.tile([0.0, 1.0], (len(u), 1)))]}
        f = sp.sidewalks(ctx, lambda x, y: np.full(len(np.atleast_1d(x)), 200.0), [(0, 0), (20, 4)])
        z = sp.bilinear(f, np.array([10.0, 10.0, 10.0]), np.array([0.5, 1.5, 3.0]))
        self.assertAlmostEqual(z[0], 200.11, delta=0.02)
        self.assertGreater(z[1], 201.4)
        self.assertGreater(z[2], 201.5)


class Measures(unittest.TestCase):
    def street(self, n=40):
        s = np.arange(0, float(n))
        return {"name": "test", "highway": "residential", "s": s, "p": np.column_stack([s, np.zeros(n)]),
                "t": np.tile([1.0, 0.0], (n, 1))}

    def test_a_step_is_a_jump_and_a_side_slope_a_roll(self):
        c = self.street()
        flat = sp.drive_measures(lambda x, y: np.where(np.asarray(x) > 20, 200.2, 200.0), [c])
        self.assertEqual(flat["jumps"], 2)  # (both drive lines)
        side = sp.drive_measures(lambda x, y: 200 + 0.2 * np.asarray(y), [c])
        self.assertEqual(side["rolls over 7 deg"], 2 * 40)
        self.assertEqual(side["jumps"], 0)
        steep = sp.drive_measures(lambda x, y: 200 + 0.16 * np.asarray(x), [c])  # (a 16 % street: a slope, not a step)
        self.assertEqual(steep["jumps"], 0)

    def test_drive_lines_off_the_road_are_not_measured(self):
        # (an island beside a carriageway, 0.3 m up, under one drive line: no car drives it)
        from shapely.geometry import box
        c = self.street()
        z = lambda x, y: np.where((np.asarray(x) > 20) & (np.asarray(y) > 1), 200.3, 200.0)  # noqa: E731
        self.assertEqual(sp.drive_measures(z, [c])["jumps"], 1)  # (the left drive line)
        road = box(-1, -3, 41, 1).union(box(-1, 1, 20, 3))
        self.assertEqual(sp.drive_measures(z, [c], road=road)["jumps"], 0)


class Build(unittest.TestCase):
    """data/lineN.streets.*: what build_square packs, read back by read_streets (#507 and #508 read it)."""

    def test_written_and_read_back(self):
        import json
        import tempfile
        n = int(round(300.0 / sp.SW_CELL))
        rng = np.random.default_rng(1)
        zr = np.full((n, n), np.nan)
        zw = np.full((n, n), np.nan)
        zr[10:20, 30:200] = 210.0 + rng.random((10, 170))
        zw[20:24, 30:200] = 210.1 + rng.random((4, 170))

        def square(ln, cell, ij, ctx=None):
            on_r, on_w = np.isfinite(zr), np.isfinite(zw)
            base = float(np.floor(min(np.nanmin(zr), np.nanmin(zw))))
            q = np.round((np.concatenate([zr[on_r], zw[on_w]]) - base) / sp.STREETS_SCALE).astype(np.int16)
            return (ij, base, np.packbits(on_r.ravel()), np.packbits(on_w.ravel()), q, int(on_r.sum()), int(on_w.sum()),
                    sp.STREETS_SCALE)

        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            # (the squares reaching the line's ground, its 10 m grid's box within 1.2 km of the route: here that box)
            T = {"x0": 0.0, "y0": 899.0, "dx": 10.0, "dy": -10.0, "nx": 90, "ny": 30}
            json.dump({"path": [[10.0, 650.0], [320.0, 645.0], [620.0, 640.0]], "terrain": T}, open(os.path.join(root, "data", "line99.json"), "w"))
            keep = sp.build_square, sp._wide_init
            sp.build_square, sp._wide_init = square, lambda ln: None
            try:
                meta = sp.build(99, jobs=1, root=root)
            finally:
                sp.build_square, sp._wide_init = keep
            got, _ = sp.read_streets(99, root=root)
        self.assertEqual(sorted(got), [(0, 2), (1, 2), (2, 2)])
        self.assertEqual([q["road"] for q in meta["squares"]], [1700] * 3)
        x0, y1, r, w = got[(1, 2)]
        self.assertEqual((x0, y1), (300.0, 900.0))
        self.assertTrue(np.array_equal(np.isfinite(r), np.isfinite(zr)))
        self.assertLess(np.nanmax(np.abs(r - zr)), sp.STREETS_SCALE)
        self.assertLess(np.nanmax(np.abs(w - zw)), sp.STREETS_SCALE)


if __name__ == "__main__":
    unittest.main()
