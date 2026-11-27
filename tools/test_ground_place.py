# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_place.py: a place's tiles, the comparison with the written file, the measures (#757), and the city mesh's
key (tools/city_terrain.py code_hash): what it hashes of the code.

    python -P -E tools/test_ground_place.py
"""
import json
import os
import sys
import tempfile
import time
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


class Overlay(unittest.TestCase):
    def test_the_places_tile_is_the_builds_and_its_neighbour_the_written_files(self):
        """x 306 m is the border between tiles e-1486 and e-1485 (tools/test_ground_mesh.py): a triangle either side."""
        def mesh(z):
            V = mm([300000, 0, z], [305000, 0, z], [305000, -1000, z], [307000, 0, z], [312000, 0, z], [312000, -1000, z])
            return {"V": V, "F": np.array([[0, 1, 2], [3, 4, 5]]), "cls": np.array([S, S]),
                    "draw": np.array(["road", "road"], dtype=object), "area": np.array(["road", "road"], dtype=object)}
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "data"))
            w = mesh(200000)
            blob, layout = gm.encode_tiles(w["V"], w["F"], w["cls"], w["draw"], w["area"])
            with open(os.path.join(root, "data", "line99.ground.bin"), "wb") as f:
                f.write(blob)
            with open(os.path.join(root, "data", "line99.ground.json"), "w", encoding="utf-8") as f:
                json.dump(layout, f)
            left = tuple(int(v) for v in tile_index(302.0, -0.5))
            done, lacking = gpl.overlay("99", mesh(205000), [left, (left[0], left[1] + 50)], os.path.join(root, "over"), root)
            self.assertEqual((len(done), len(lacking)), (1, 1))
            with open(os.path.join(root, "over", "data", "line99.ground.json"), encoding="utf-8") as f:
                lay = json.load(f)
            with open(os.path.join(root, "over", "data", "line99.ground.bin"), "rb") as f:
                V, by = gm.decode(f.read(), lay)
            z = {round(float(x)): float(h) for x, _, h in V.tolist()}
            self.assertEqual((z[300], z[305], z[307], z[312]), (205.0, 205.0, 200.0, 200.0))
            self.assertEqual((lay["triangles"], len(by["survey"])), (2, 2))


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


def fake_place(job):
    """A worker's place for Many: it sleeps its `sleep` s, then answers like ground_place.one."""
    name, pl, kw = job
    time.sleep(pl["sleep"])
    return name, not pl.get("fail"), f"{name}: {'Traceback (a test)' if pl.get('fail') else 'holds'}\n"


class Many(unittest.TestCase):
    """Several places at once in worker processes, in one shared turn (#843)."""

    def many(self, todo, jobs):
        import argparse
        import io
        from unittest import mock
        import baseline_store
        a = argparse.Namespace(jobs=jobs, rings=False, ring=1, mesh=None, threads=1, overlay=False)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as d, mock.patch.object(baseline_store, "LOCKS", d), \
                mock.patch.object(baseline_store.HeavyJob, "WATCH", False), \
                mock.patch.object(baseline_store.HeavyJob, "FREE", staticmethod(lambda: 64.0)), \
                mock.patch.object(baseline_store.HeavyJob, "CORES", 24):
            try:
                gpl.many(todo, a, work=fake_place, out=out)
                err = None
            except SystemExit as e:
                err = str(e)
        return out.getvalue().splitlines(), err

    def test_places_print_in_the_lists_order_whichever_ends_first(self):
        todo = {"first": {"sleep": 1.5}, "second": {"sleep": 0.0}, "third": {"sleep": 0.5}}
        lines, err = self.many(todo, 3)
        self.assertIsNone(err)
        self.assertEqual(lines, ["3 places, 3 at once, the longest first", "first: holds", "second: holds", "third: holds"])

    def test_a_failed_place_stops_the_run_with_its_name_and_its_lines(self):
        todo = {"done": {"sleep": 0.0}, "slow": {"sleep": 60.0}, "bad": {"sleep": 0.5, "fail": True}}
        t0 = time.time()
        lines, err = self.many(todo, 3)
        self.assertLess(time.time() - t0, 30.0, "the slow place was stopped, not waited for")
        self.assertIn("bad failed", err)
        self.assertEqual(lines[1:], ["done: holds", "bad: Traceback (a test)"])

    def test_a_worker_keeps_what_its_place_prints_though_a_tool_reconfigures_stdout(self):
        from unittest import mock

        def place(name, pl, **kw):  # (street_profile.py does this when the build first imports it)
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(f"{name}: Dobeška holds")
        with mock.patch.object(gpl, "run", place):
            self.assertEqual(gpl.one(("p", {}, {})), ("p", True, "p: Dobeška holds\n"))

        def broken(name, pl, **kw):
            print("built half")
            raise SystemExit("no raw/")
        with mock.patch.object(gpl, "run", broken):
            name, ok, text = gpl.one(("q", {}, {}))
        self.assertEqual((name, ok), ("q", False))
        self.assertTrue(text.startswith("built half\nTraceback") and "no raw/" in text, text)

    def test_the_turn_is_shared_and_takes_what_its_places_do(self):
        import baseline_store
        from unittest import mock
        seen = {}
        real = baseline_store.HeavyJob.claim

        def claim(job, gb=None, cores=None):
            seen.update(share=dict(job.share), gb=gb, cores=cores)
            return real(job, gb, cores)
        with mock.patch.object(baseline_store.HeavyJob, "claim", claim):
            self.many({"a": {"sleep": 0.0}, "b": {"sleep": 0.0}}, 4)
        # (queued for one place, so that it starts as soon as one fits; then it claims the two places it has, not the
        # four asked for: one core and PLACE_GB each)
        self.assertEqual(seen, {"share": {"gb": gpl.PLACE_GB[0], "cores": 1}, "gb": 2 * gpl.PLACE_GB[0], "cores": 2})

    def test_beside_other_jobs_it_takes_only_the_places_that_fit(self):
        import baseline_store
        from unittest import mock
        seen = {}
        real = baseline_store.HeavyJob.claim

        def claim(job, gb=None, cores=None):
            seen.update(gb=gb, cores=cores)
            return real(job, gb, cores)
        # (the queue leaves 8 GB beside the jobs running: two places of 3.5 GB)
        with mock.patch.object(baseline_store.HeavyJob, "claim", claim), \
                mock.patch.object(baseline_store.HeavyJob, "room", lambda job, jobs=None: {"gb": 8.0, "cores": 20}):
            lines, _ = self.many({k: {"sleep": 0.0} for k in "abcd"}, 4)
        self.assertEqual(seen, {"gb": 2 * gpl.PLACE_GB[0], "cores": 2})
        self.assertEqual(lines[0], "4 places, 2 at once, the longest first")


class Judge(unittest.TestCase):
    def report(self, root, name, rings):
        os.makedirs(os.path.join(root, "reports", "places", name))
        with open(os.path.join(root, "reports", "places", name, "place.json"), "w", encoding="utf-8") as f:
            json.dump({"place": name, "rings": rings} if rings else {"place": name}, f)

    def rings(self, n=0):
        return {"vertices": {"only built": n, "only written": n}, "triangles": {"only built": 2 * n, "only written": 0},
                "points at another height": {"points": n, "max cm": 3.5 if n else 0}}

    def test_the_set_holds_only_when_each_place_is_the_same_with_one_ring_more(self):
        with tempfile.TemporaryDirectory() as d:
            self.report(d, "a", self.rings())
            self.report(d, "b", self.rings())
            out = []
            self.assertEqual(gpl.judge(["a", "b"], root=d, log=out.append), 0)
            self.assertIn("2 of 2 the same", out[0])
            self.report(d, "c", self.rings(3))
            self.report(d, "d", None)  # (built without --rings)
            out = []
            self.assertEqual(gpl.judge(["a", "b", "c", "d", "e"], root=d, log=out.append), 1)
            self.assertIn("2 of 5 the same", out[0])
            self.assertIn("c: 6 / 0 triangles and 3 / 3 vertices in one build only, 3 points at another height (max 3.5 cm)", out[0])
            self.assertIn("d: no report with one ring more", out[0])
            self.assertIn("e: no report", out[0])

    def test_a_report_from_before_the_run_is_not_its(self):
        with tempfile.TemporaryDirectory() as d:
            self.report(d, "a", self.rings())
            self.assertEqual(gpl.judge(["a"], since=time.time() + 60, root=d, log=lambda s: None), 1)

    def test_a_rule_that_is_not_one_stops_before_anything_builds(self):
        with self.assertRaises(SystemExit) as e:
            gpl.main(["--rule", "walls,nope"])
        self.assertIn("no rule nope", str(e.exception))


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
        # (an expectation of the least: a kerb that must stand)
        self.assertEqual(gpl.held({"rise m": 0.08}, {"rise m at least": 0.05}), {})
        self.assertEqual(gpl.held({"rise m": 0.01}, {"rise m at least": 0.05}), {"rise m at least": (0.01, 0.05)})
        self.assertEqual(gpl.held({}, {"rise m at least": 0.05}), {"rise m at least": (None, 0.05)})

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
