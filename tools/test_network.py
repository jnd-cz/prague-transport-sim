# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/network.py: the page's arithmetic and survey reads, the roads' rules on a made-up survey, the comparison, and
the parity with the page (tools/test_network_parity.py).

    python -P -E tools/test_network.py
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import network as nw  # noqa: E402


class Arithmetic(unittest.TestCase):
    def test_hypot(self):
        for a, b in ((3, 4), (0, 0), (-1e-3, 2.5), (1e6, 1e-6), (0.1, 0.2)):
            self.assertEqual(nw.hyp(a, b), float(nw.js_hypot(a, b)))
            self.assertAlmostEqual(nw.hyp(a, b), math.hypot(a, b), delta=1e-12 * max(1, abs(a), abs(b)))

    def test_round_halves_up(self):
        self.assertEqual([nw.js_round(v) for v in (2.5, -2.5, -0.4, 0.49)], [3, -2, 0, 0])
        self.assertEqual(nw.cm(-0.125), -12)

    def test_varints(self):
        import ground_mesh as gm
        v = np.random.default_rng(1).integers(-2**40, 2**40, 5000)
        blob = b"xy" + gm.varints(gm.zigzag(v))
        u, off = nw.read_varints(blob, len(v), 2)
        self.assertEqual(off, len(blob))
        self.assertTrue((nw.unzigzag(u) == v).all())


class Geometry(unittest.TestCase):
    def test_smooth_keeps_the_ends(self):
        pts = [[0, 0], [30, 0], [30, 30]]
        out = nw.smooth_polyline(pts, 3, 6)
        self.assertEqual(len(out), 21)
        self.assertEqual(out[0].tolist(), [0, 0])
        self.assertAlmostEqual(out[-1][0], 30, places=9)
        self.assertAlmostEqual(out[-1][1], 30, places=9)
        self.assertGreater(min(math.hypot(x - 30, y) for x, y in out), 1)  # (the corner rounded)

    def test_path_at(self):
        p = nw.Path([[0, 0], [10, 0], [10, 10]])
        x, y, hx, hy = p.at(np.array([-5, 5, 15, 99]))
        self.assertEqual(p.length, 20)
        self.assertEqual(list(zip(x, y)), [(0, 0), (5, 0), (10, 5), (10, 10)])
        self.assertEqual(list(zip(hx, hy)), [(1, 0), (1, 0), (0, 1), (0, 1)])

    def test_route_nearest(self):
        r = nw.Route([[0, 0], [100, 0]], {"before": [[-20, 0]], "after": [[120, 0]]})
        self.assertEqual(r.length, 100)
        self.assertEqual(r.at(50)[:2], (50, 0))
        d, s = r.nearest(33, 3)
        self.assertAlmostEqual(d, 3)
        self.assertAlmostEqual(s, 33)
        self.assertIsNone(r.nearest(500, 500))


class FakeSurvey:
    """A survey of straight bands across y: [(y0, y1, class)], first match; or of boxes [(x0, x1, y0, y1, class)]."""

    def __init__(self, bands):
        self.bands = bands

    def class_at(self, x, y):
        out = np.full(len(y), None, dtype=object)
        for b in reversed(self.bands):
            x0, x1, y0, y1, c = b if len(b) == 5 else (-np.inf, np.inf, *b)
            out[(x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)] = c
        return out

    def covered(self, x, y):
        return np.ones(len(x), bool)

    def class_under(self, x, y):
        return np.full(len(x), None, dtype=object)


def roads(survey, *ways):
    data = {"roads": [{"p": p, "w": w, "f": 0, "c": 1, **kw} for p, w, kw in ways]}
    return nw.Network(data, survey, None, None).roads


class Fit(unittest.TestCase):
    def test_kerbs(self):
        r = roads(FakeSurvey([(-4, 4, "road"), (-9, 9, "sidewalk")]), ([[0, 0], [100, 0]], 8, {}))[0]
        self.assertEqual(set(r["fitLo"]), {-4.25})
        self.assertEqual(set(r["fitHi"]), {4.25})
        self.assertIsNone(r["fitMed"])

    def test_tram_area_at_the_side_trimmed(self):
        # (y = -l: the right side of a road heading east is south)
        r = roads(FakeSurvey([(-4, 4, "road"), (-8, -4, "tram")]), ([[0, 0], [100, 0]], 8, {}))[0]
        self.assertEqual(set(r["fitHi"]), {4.25})

    def test_median_on_a_two_way_road(self):
        sv = FakeSurvey([(-0.5, 0.5, "median"), (-6, 6, "road")])
        two = roads(sv, ([[0, 0], [100, 0]], 12, {}))[0]
        self.assertEqual([set(a) for a in two["fitMed"]], [{-0.75}, {0.75}])
        one = roads(sv, ([[0, 0], [100, 0]], 12, {"o": 1}))[0]
        self.assertIsNone(one["fitMed"])  # (a one-way road's carriageway ends at it: here at the centre)

    def test_parallel_ways_split_the_carriageway(self):
        sv = FakeSurvey([(-4, 7, "road")])
        a, b = roads(sv, ([[0, 0], [100, 0]], 8, {}), ([[0, 3], [100, 3]], 8, {}))
        self.assertEqual(set(a["fitLo"]), {-1.5})  # (the way 3 m to its left takes that side)
        self.assertEqual(set(b["fitHi"]), {1.5})

    def test_plaza_not_fitted(self):
        r = roads(FakeSurvey([(-15, 15, "road")]), ([[0, 0], [100, 0]], 8, {}))[0]
        self.assertIsNone(r["fitLo"])


class Lanes(unittest.TestCase):
    """laneOffset on a road along x fitted to kerbs at ±4.25 m (+ right of the car's direction)."""

    def setUp(self):
        self.sv = FakeSurvey([(-4, 4, "road"), (-9, 9, "sidewalk")])

    def build(self, w=8, **kw):
        data = {"roads": [{"p": [[0, 0], [100, 0]], "w": w, "f": 0, "c": 1, **kw}]}
        return nw.Network(data, self.sv, None, None)

    def test_two_way(self):
        R = self.build()
        r = R.roads[0]
        self.assertEqual([round(R.lane_offset(r, 50, d), 6) for d in (1, -1)], [2.55, 2.55])  # (1.7 m in from the kerb)
        self.assertEqual([(x["dir"], x["from"], x["to"]) for x in R.lanes], [(1, "0,0", "100,0"), (-1, "100,0", "0,0")])
        a, b = R.lanes
        self.assertAlmostEqual(a["path"].p[len(a["path"].p) // 2][1], -2.55)  # (right of eastbound: south)
        self.assertAlmostEqual(b["path"].p[len(b["path"].p) // 2][1], 2.55)
        self.assertAlmostEqual(a["path"].p[0][0], 5)  # (trimmed 5 m back from the junction)

    def test_one_way_two_lanes(self):
        R = self.build(o=1, ln=2)
        r = R.roads[0]
        self.assertEqual(len(R.lanes), 2)
        self.assertEqual([round(R.lane_offset(r, 50, 1, k), 6) for k in (0, 1)], [2.55, -0.7])  # (3.25 m apart)

    def test_narrow_street_on_its_own_track(self):
        R = self.build()
        r = {**R.roads[0], "fitLo": [-2.0] * 26, "fitHi": [2.0] * 26, "trk": [[-0.8, 0.8]] * 26}
        self.assertEqual(R.lane_offset(r, 50, 1), 0.8)  # (the band right of the tracks' middle is under 3.2 m)
        self.assertEqual(R.lane_offset(r, 50, -1), 0.8)


class Walks(unittest.TestCase):
    @staticmethod
    def net(survey, ways, buildings=()):
        data = {"roads": [{"p": p, "w": w, "f": f, "c": int(not f), **kw} for p, w, f, kw in ways],
                "buildings": [{"p": b} for b in buildings]}
        return nw.Network(data, survey, None, None)

    def test_footway_cut_on_the_carriageway(self):
        n = self.net(FakeSurvey([(80, 120, -50, 50, "road")]), [([[0, 0], [200, 0]], 3, 1, {})])
        ends = sorted((round(w["path"].p[0][0]), round(w["path"].p[-1][0])) for w in n.walks if not w["link"])
        self.assertEqual(ends, [(0, 78), (122, 200)])  # (every 2 m: the last point off it on each side)

    def test_short_crossing_kept(self):
        n = self.net(FakeSurvey([(99, 103, -50, 50, "road")]), [([[0, 0], [200, 0]], 3, 1, {})])
        self.assertEqual(sum(1 for w in n.walks if not w["link"]), 1)

    def test_sidewalks_on_the_survey(self):
        sv = FakeSurvey([(-4, 4, "road"), (-7, 7, "sidewalk")])
        n = self.net(sv, [([[0, 0], [100, 0]], 8, 0, {})])
        ys = sorted(round(float(np.median(w["path"].p[:, 1])), 2) for w in n.walks if not w["link"])
        self.assertEqual(ys, [-5.75, 5.75])  # (the kerb at 4.25, the sidewalk from 4.75, 1 m into it)

    def test_ends_joined_and_linked(self):
        sv = FakeSurvey([(-100, 100, "sidewalk")])
        n = self.net(sv, [([[0, 0], [60, 0]], 3, 1, {}), ([[60.2, 0], [120, 0]], 3, 1, {}), ([[0, 2], [0, 60]], 3, 1, {})])
        a = n.walks[0]
        self.assertIn((1, 0), a["links"][1])  # (0.2 m apart: joined)
        links = [w for w in n.walks if w["link"]]
        self.assertTrue(any(w["links"] == [[(0, 0)], [(2, 0)]] for w in links), links)  # (2 m apart: a link walk)

    def test_door(self):
        sv = FakeSurvey([(-100, 100, "sidewalk")])
        n = self.net(sv, [([[0, 0], [60, 0]], 3, 1, {})], [[[20, 3], [30, 3], [30, 13], [20, 13]]])
        d = n.doors[0]
        self.assertEqual((d["walk"], d["s"], d["x"], d["y"]), (0, 20, 20, 0))
        self.assertAlmostEqual(math.hypot(d["ix"] - 20, d["iy"] - 3), 1.5)


class Signals(unittest.TestCase):
    def test_resample_heights(self):
        z = nw.resample_heights([10, 12, None], 2, 5, 1)
        self.assertEqual(z[:3].tolist(), [10, 11, 12])
        self.assertTrue(np.isnan(z[3:]).all())

    def sig(self, **kw):
        s = object.__new__(nw.Signals)
        s.zebras, s.osm_stops, s.jpos = [], [], {"100,0": [100, 0]}
        s.__dict__.update(kw)
        return s

    def test_stop_line_before_a_zebra(self):
        s = self.sig(zebras=[[[48, -3], [48, 3]]])
        s.stop_line_at = lambda *a: (0, "edge")
        lane = {"path": nw.Path([[0, 0], [50, 0]]), "to": "100,0"}
        self.assertEqual(s.stop_line(lane, "cross", 60, 0, []), (4, "edge"))  # (2 m before the zebra at 48 m)

    def test_osm_stop_line(self):
        s = self.sig(osm_stops=[{"x": 45, "y": 1, "hx": 1, "hy": 0}, {"x": 44, "y": 1, "hx": -1, "hy": 0}])
        lane = {"path": nw.Path([[0, 0], [50, 0]]), "to": "100,0"}
        self.assertEqual(s.osm_stop(lane, 60, 0), 5)  # (the node serving the other direction left out)
        s.jpos = {"100,0": [46, 0]}
        self.assertIsNone(s.osm_stop(lane, 60, 0))  # (on the junction's own node: no stop line)


class Stops(unittest.TestCase):
    def test_set_lengths_from_the_page(self):
        L = nw.set_lengths()
        self.assertEqual(L[1], 15.2)
        self.assertAlmostEqual(L[2], 30.24)  # (two cars, the couplers overlapping 0.16 m)

    def test_stops_by_set(self):
        recs = [{"stand": [True, False], "outer": [310, None]}]
        self.assertEqual(nw.as_page("stops", recs, 2), [{"stand": False, "outer": None}])


class Compare(unittest.TestCase):
    def test_finds_moves(self):
        a = [{"p": [0, 0, 100, 0], "w": 8, "ends": ["0,0", "1,0"], "hi": [425, 425]}]
        self.assertEqual(nw.compare(a, a)["exact"], 1)
        b = [{**a[0], "hi": [425, 427]}]
        rep = nw.compare(a, b)
        self.assertEqual((rep["exact"], rep["equal"], rep["fields"]["hi"]["max cm"]), (0, 0, 2))
        self.assertEqual(nw.compare(a, [{**a[0], "hi": [425, 426]}])["equal"], 1)
        self.assertIn("only page", nw.compare(a + a, b))


if __name__ == "__main__":
    unittest.main()
