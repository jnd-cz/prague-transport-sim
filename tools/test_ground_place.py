# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_place.py: a place's tiles, the comparison with the written file, the measures (#757), and the city mesh's
key (tools/city_terrain.py code_hash): what it hashes of the code.

    python -P -E tools/test_ground_place.py
"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_mesh as gm  # noqa: E402
import ground_place as gpl  # noqa: E402
from geo import tile_box, tile_index  # noqa: E402

T, S, W = gm.CLASS_IDS["terrain"], gm.CLASS_IDS["survey"], gm.CLASS_IDS["wall"]


def mm(*rows):
    return np.asarray(rows, np.int64)


class Tiles(unittest.TestCase):
    def test_a_place_inside_a_tile_takes_it_and_its_ring(self):
        e, n = (int(v) for v in tile_index(3925.0, 330.0))
        mid, box = gpl.tiles_of((3925.0, 330.0), 40)
        self.assertEqual(mid, [(e, n)])
        a, b = tile_box(e - 1, n - 1), tile_box(e + 1, n + 1)
        self.assertEqual(box, (a[0], a[1], b[2], b[3]))
        self.assertEqual(gpl.tiles_of((3925.0, 330.0), 40, ring=0)[1], tile_box(e, n))

    def test_a_reach_over_a_border_takes_both_tiles(self):
        x0 = tile_box(*(int(v) for v in tile_index(3925.0, 330.0)))[0]
        mid, _ = gpl.tiles_of((x0 + 10.0, 330.0), 40)
        self.assertEqual(len(mid), 2)
        self.assertTrue(gpl.in_tiles(np.array([x0 - 5.0, x0 + 5.0]), np.array([330.0, 330.0]), mid).all())
        self.assertFalse(gpl.in_tiles(np.array([x0 + 5.0]), np.array([330.0 + 600.0]), mid).any())


class Locality(unittest.TestCase):
    # a square of four corners and a middle point, cut into four triangles
    V = mm([0, 0, 1000], [5000, 0, 1000], [5000, 5000, 1000], [0, 5000, 1000], [2500, 2500, 1000])
    F = np.array([[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]])
    C = np.full(4, S)

    def test_the_same_mesh_in_another_order_is_the_same(self):
        order = np.array([4, 2, 0, 3, 1])
        back = np.argsort(order)
        rep = gpl.locality((self.V, self.F, self.C), (self.V[order], back[self.F][::-1, ::-1], self.C))
        self.assertEqual(rep["same %"], 100.0)
        self.assertEqual(rep["vertices"]["only built"] + rep["vertices"]["only written"], 0)
        self.assertEqual(rep["triangles"]["only built"] + rep["triangles"]["only written"], 0)

    def test_a_point_at_another_height_is_named_by_what_gave_it(self):
        V2 = self.V.copy()
        V2[4, 2] += 250
        corners = {"x": V2[:, 0] / 1000, "y": V2[:, 1] / 1000, "z": V2[:, 2] / 1000,
                   "label": np.array(["terrain", "terrain", "street", "street", "lidar"], dtype=object)}
        rep = gpl.locality((V2, self.F, self.C), (self.V, self.F, self.C), corners)
        p = rep["points at another height"]
        self.assertEqual((p["points"], p["max cm"], p["over 1 / 5 / 20 cm"]), (1, 25.0, [1, 1, 1]))
        self.assertEqual(p["by what gave the height"], {"lidar": {"points": 1, "max cm": 25.0}})
        self.assertEqual(p["the farthest"][0]["at"], [2.5, 2.5])
        self.assertEqual(rep["triangles"]["only built"], 4)
        self.assertEqual(rep["same %"], 80.0)

    def test_a_quad_cut_along_its_other_diagonal_moves_no_vertex(self):
        """#738: the same four corners, the other diagonal."""
        V = self.V[:4]
        a, b = np.array([[0, 1, 2], [0, 2, 3]]), np.array([[0, 1, 3], [1, 2, 3]])
        rep = gpl.locality((V, a, self.C[:2]), (V, b, self.C[:2]))
        self.assertEqual(rep["same %"], 100.0)
        self.assertEqual((rep["triangles"]["only built"], rep["triangles"]["only written"]), (2, 2))

    def test_a_point_in_one_only(self):
        rep = gpl.locality((self.V, self.F, self.C), (self.V[:4], np.array([[0, 1, 2], [0, 2, 3]]), self.C[:2]))
        self.assertEqual(rep["points in one only"], {"built": 1, "written": 0})
        self.assertEqual(rep["points at another height"]["points"], 0)


class Measures(unittest.TestCase):
    def wall(self, flip=False):
        """A level floor at 0 and one at 0.4 m (0.5 m at one end), 5 m long, a wall between them at x = 5 m."""
        V = mm([0, 0, 0], [5000, 0, 0], [5000, 5000, 0], [0, 5000, 0],
               [5000, 0, 400], [10000, 0, 400], [10000, 5000, 500], [5000, 5000, 500])
        floor = [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]]
        w = [[1, 4, 7], [1, 7, 2]] if not flip else [[1, 4, 2], [4, 7, 2]]
        return V, np.array(floor + w), np.array([S, S, S, S, W, W])

    def test_a_wall_counts_once_at_its_taller_end_however_it_is_cut(self):
        for flip in (False, True):
            m = gpl.measures(*self.wall(flip), (0, 0, 10, 5))
            self.assertEqual(m["walls"], {"m": 5.0, "tallest m": 0.5, "m over 0.1 m": 5.0, "m over 0.3 m": 5.0, "m over 1.0 m": 0.0})
            self.assertEqual(m["m2 by class"], {"survey": 50.0})

    def test_a_steep_face_that_is_no_wall(self):
        V = mm([0, 0, 0], [1000, 0, 2000], [1000, 1000, 2000], [0, 1000, 0])
        m = gpl.measures(V, np.array([[0, 1, 2], [0, 2, 3]]), np.array([T, T]), (0, 0, 1, 1))
        self.assertEqual(m["steep faces that are no wall"], {"m2 in plan": 1.0, "triangles": 2, "by class": {"terrain": 1.0}})
        self.assertEqual(m["walls"]["m"], 0.0)

    def test_only_what_lies_in_the_box(self):
        self.assertEqual(gpl.measures(*self.wall(), (0, 0, 4, 5))["m2 by class"], {"survey": 25.0})


class Places(unittest.TestCase):
    def test_every_place_names_its_line_point_issue_and_source(self):
        known = gpl.places()
        self.assertTrue(known)
        for name, p in known.items():
            self.assertIn(str(p["line"]), ("9", "17", "22", "23", "37"), name)
            self.assertEqual(len(p["at"]), 2, name)
            self.assertTrue(p.get("issue") and p.get("what") and p.get("source"), name)
            self.assertLessEqual(float(p.get("reach") or gpl.REACH), 250, name)
            for s in p.get("sections") or []:
                self.assertTrue(s.get("name") and len(s["from"]) == 2 and len(s["to"]) == 2 and s.get("expect"), name)
                self.assertLessEqual(max(abs(s[k][i] - p["at"][i]) for k in ("from", "to") for i in (0, 1)),
                                     float(p.get("reach") or gpl.REACH), f"{name}: a section inside the place's reach")
            if p.get("seen"):
                self.assertTrue(p["seen"].get("what") and p["seen"].get("from") and p["seen"].get("source"), name)


class Sections(unittest.TestCase):
    def profile(self, heights):
        d = np.arange(len(heights)) * gpl.SECTION_STEP
        return d, np.asarray(heights, float)

    def test_level_ground_a_wall_and_level_ground_does_not_slope(self):
        d, z = self.profile([8.0] * 20 + [0.0] * 20)
        m = gpl.section_measures(d, z, z)
        self.assertEqual((m["sloping m"], m["largest step m"], m["off the lidar m"]), (0.0, 8.0, 0.0))
        self.assertFalse(gpl.held(m, {"sloping m": 2.5, "off the lidar m": 2.5}))

    def test_the_same_drop_as_a_slope_slopes_and_leaves_the_lidar(self):
        d, wall = self.profile([8.0] * 20 + [0.0] * 20)
        _, z = self.profile([8.0] * 4 + list(np.linspace(8.0, 0.0, 33)) + [0.0] * 3)
        m = gpl.section_measures(d, z, wall)
        self.assertEqual(m["sloping m"], 8.0)
        self.assertGreater(m["off the lidar m"], 5.0)
        self.assertEqual(set(gpl.held(m, {"sloping m": 2.5, "off the lidar m": 2.5})), {"sloping m", "off the lidar m"})

    def test_an_even_flight_keeps_to_its_chord_a_warped_one_does_not(self):
        d, even = self.profile(np.linspace(0.0, 1.1, 10))
        self.assertEqual(gpl.section_measures(d, even)["off the chord m"], 0.0)
        _, warped = self.profile([0.0, 0.0, 0.0, 0.1, 0.9, 1.0, 1.1, 1.1, 1.1, 1.1])
        m = gpl.section_measures(d, warped)
        self.assertGreater(m["off the chord m"], 0.3)
        self.assertEqual(m["rise m"], 1.1)
        self.assertIn("off the chord m", gpl.held(m, {"off the chord m": 0.15}))

    def test_samples_off_the_mesh_are_counted_not_measured(self):
        d, z = self.profile([1.0, 1.0, np.nan, np.nan, 1.0, 1.0])
        m = gpl.section_measures(d, z)
        self.assertEqual((m["off the mesh m"], m["sloping m"], m["largest step m"]), (0.75, 0.0, 0.0))


class MeshKey(unittest.TestCase):
    def test_the_key_keeps_through_a_change_of_the_run_and_moves_with_the_mesh_code(self):
        import city_terrain as ct
        here = os.path.dirname(os.path.abspath(ct.__file__))
        with tempfile.TemporaryDirectory() as d:
            for f in ct.CODE:
                with open(os.path.join(here, f), "rb") as fh:
                    body = fh.read()
                with open(os.path.join(d, f), "wb") as fh:
                    fh.write(body)
            base = ct.code_hash(d)
            self.assertEqual(base, ct.code_hash())
            p = os.path.join(d, "city_terrain.py")
            with open(p, "rb") as fh:
                body = fh.read()
            self.assertEqual(body.count(ct.BOOKKEEPING), 1)
            with open(p, "wb") as fh:
                fh.write(body + b"\n# a line in the run section\n")
            self.assertEqual(ct.code_hash(d), base)
            with open(p, "wb") as fh:
                fh.write(body.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))  # (a checkout with other line ends)
            self.assertEqual(ct.code_hash(d), base)
            with open(p, "wb") as fh:
                fh.write(b"# a line in the mesh code\n" + body)
            self.assertNotEqual(ct.code_hash(d), base)


if __name__ == "__main__":
    unittest.main(verbosity=1)
