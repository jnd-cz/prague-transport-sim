# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/ground_at.py: the page's ground reads in the build.

    python -P -E tools/test_ground_at.py                 # the rules on made-up data
    python -P -E tools/test_ground_at.py --browser       # also against the page on every line in data/ (a game a line)

The browser test reads the page's ground.at (on the ground and on a deck), ground.surface and ground.trackAt at points
along every line (every 25 m, up to 30 m across), at the bridges' and road tunnels' ends and round their mouths, and
holds the build's answers within LIMIT of them. Lines without data are skipped (python -I tools/snapshot.py data-fetch).
"""
import faulthandler
import json
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ground_at as ga  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 0.001  # m
BROWSER = "--browser" in sys.argv
if BROWSER:
    sys.argv.remove("--browser")


class Chains(unittest.TestCase):
    def test_ways_join_end_to_end(self):
        roads = [{"p": [[0, 0], [10, 0]], "t": 1}, {"p": [[20, 0], [10, 0]], "t": 1}, {"p": [[-3, 0], [-50, 0]]},
                 {"p": [[30, 0], [20, 0]], "t": 1}, {"p": [[25, 5], [25, 30]], "t": 1}]
        out = ga.chain_ways(roads, "t")
        self.assertEqual(len(out), 2)
        line, opened, members = out[0]
        self.assertEqual([tuple(p) for p in line], [(0, 0), (10, 0), (20, 0), (30, 0)])
        self.assertEqual(opened, (True, False))  # (an ordinary road 3 m from its start; none at its end)
        self.assertEqual(sorted(members), [0, 1, 3])

    def test_a_fork_ends_a_chain(self):
        roads = [{"p": [[0, 0], [10, 0]], "b": 1}, {"p": [[10, 0], [20, 0]], "b": 1}, {"p": [[10, 0], [10, 10]], "b": 1}]
        out = ga.chain_ways(roads, "b")
        self.assertEqual(out[0][2], [0])  # (two ways go on from its end: it stops there, and the other two join)
        self.assertEqual(sorted(out[1][2]), [1, 2])


class ProfileAcross(unittest.TestCase):
    def profile(self, back=4.0, cross=None):
        class R:
            class rt:
                length = 100.0

            @staticmethod
            def lift(s, lateral=0.0):
                return 0.05
        L = {"heights": {"step": 2, "path": [200 + 0.01 * s for s in range(0, 102, 2)],
                         "backOff": [back] * 51, "backZ": [201 + 0.01 * s for s in range(0, 102, 2)]}}
        if cross:
            L["crossLevel"] = {"step": 2, "unit": 0.001, "path": [cross] * 51}
        return ga.Profile(L, R)

    def test_linear_to_the_other_track_level_past_it(self):
        p = self.profile()
        z = p.height(50)
        self.assertAlmostEqual(p.height_at(50, 0), z, places=4)
        self.assertAlmostEqual(p.height_at(50, 2), z + 0.5, places=4)
        self.assertAlmostEqual(p.height_at(50, 4), z + 1, places=4)
        self.assertAlmostEqual(p.height_at(50, 7), z + 1, places=4)
        self.assertAlmostEqual(p.height_at(50, -3), z, places=4)

    def test_faded_in_at_the_ends(self):
        p = self.profile()
        self.assertAlmostEqual(p.height_at(0, 4), p.height(0), places=4)
        self.assertAlmostEqual(p.height_at(4, 4), p.height(4) + 0.4, places=4)

    def test_tilt_carries_past_the_outer_track(self):
        p = self.profile(cross=15)  # (15 mm over 1.5 m: the left lower by 1 %)
        z = p.height(50)
        self.assertAlmostEqual(p.height_at(50, -1), z + 0.01, places=4)
        self.assertAlmostEqual(p.height_at(50, -3), z + 0.014, places=4)
        self.assertAlmostEqual(p.height_at(50, 6), z + 1 - 0.014, places=4)


def lines():
    if os.environ.get("TEST_LINES"):  # (some lines only: TEST_LINES=37,17)
        return os.environ["TEST_LINES"].split(",")
    try:
        with open(os.path.join(ROOT, "data", "lines.json"), encoding="utf-8") as f:
            return [str(e["line"]) for e in json.load(f)
                    if os.path.exists(os.path.join(ROOT, "data", f"line{e['line']}.ground.json"))]
    except OSError:
        return []


def probes(g):
    """The points the browser test reads: along the route, round the ways' ends and the mouths."""
    pts = []
    s = 0.0
    while s <= g.rt.length:
        x, y, hx, hy = g.rt.at(s)
        for o in np.arange(-29.63, 30, 3):  # (off the rules' round distances: a point 6 m out reads 5.999999 on the page)
            pts.append((x - hy * o, y + hx * o))
        s += 25
    for line, _, _, _ in g.chains():
        for p, q in ((line[0], line[1]), (line[-1], line[-2])):
            dx, dy = p[0] - q[0], p[1] - q[1]
            ln = math.hypot(dx, dy) or 1
            pts += [(p[0] + dx / ln * d, p[1] + dy / ln * d) for d in range(-6, 13, 3)]
    for m in g.mouths():
        for d in range(-4, int(m["D"]) + 1, 2):
            for lat in np.arange(-m["w"] - 2, m["w"] + 2.01, 1.5):
                pts.append((m["p"][0] + m["hx"] * d + m["nx"] * lat, m["p"][1] + m["hy"] * d + m["ny"] * lat))
    return pts


READ = """async (pts) => {
  if (!window.game) { const { startShift } = await import('/tools/bench/shift.js'); await startShift({ timeout: 300 }); }
  const G = window.game.route.ground;
  return pts.map(([x, y]) => [G.at(x, y), G.at(x, y, true), G.surface(x, y), G.trackAt(x, y)]);
}"""


@unittest.skipUnless(BROWSER, "a browser test: --browser")
class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(3600, exit=True)
        from playwright.sync_api import sync_playwright
        from headless import serve
        import gpu
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]

    @classmethod
    def tearDownClass(cls):
        from headless import stop_server
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def test_reads_as_the_page(self):
        from headless import load_page
        names = lines()
        if not names:
            self.skipTest("no line data: python -I tools/snapshot.py data-fetch")
        for ln in names:
            with self.subTest(line=ln):
                g = ga.Ground(ln)
                pts = probes(g)
                page, errors, load = load_page(self.browser, self.url, ln, 600, {"keepgeo": True})
                self.assertNotIsInstance(load, dict, f"line {ln}: {load} {errors[:3]}")
                got = np.asarray(page.evaluate(READ, [list(p) for p in pts]), float)
                page.close()
                xs, ys = [p[0] for p in pts], [p[1] for p in pts]
                ours = np.column_stack([g.at_many(xs, ys), g.at_many(xs, ys, True), g.surface_many(xs, ys),
                                        [g.track_at(x, y) for x, y in pts]])
                d = np.abs(got - ours)
                names_ = ("at", "at deck", "surface", "trackAt")
                for c, name in enumerate(names_):
                    k = int(np.argmax(d[:, c]))
                    print(f"line {ln} {name}: {len(pts)} points, {(d[:, c] > LIMIT).sum()} over {LIMIT * 1000:.0f} mm, "
                          f"the farthest {d[k, c] * 100:.2f} cm at ({pts[k][0]:.1f}, {pts[k][1]:.1f}): page "
                          f"{got[k, c]:.3f}, here {ours[k, c]:.3f}", flush=True)
                self.assertLessEqual(float(d.max()), LIMIT)


if __name__ == "__main__":
    unittest.main()
