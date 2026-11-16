# SPDX-License-Identifier: AGPL-3.0-or-later
"""The beds' rows of tools/bed_surface.py against the page's own (src/world.js bedRows and the edges, #508): on every
line in data/, every row's point, offsets and heights within LIMIT.

    python -P -E tools/test_bed_surface_page.py
A browser test (it loads the game, about 30 s a line). Lines without data are skipped (python -I tools/snapshot.py
data-fetch). Removed with the page's copy of the rule (#509).
"""
import faulthandler
import json
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from headless import load_page, serve, stop_server  # noqa: E402
import gpu  # noqa: E402
import bed_surface as bs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 0.001  # m


def lines():
    try:
        with open(os.path.join(ROOT, "data", "lines.json"), encoding="utf-8") as f:
            return [str(e["line"]) for e in json.load(f) if os.path.exists(os.path.join(ROOT, "data", f"line{e['line']}.json"))]
    except OSError:
        return []


class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(2400, exit=True)
        from playwright.sync_api import sync_playwright
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def test_rows_as_the_page(self):
        names = lines()
        if not names:
            self.skipTest("no line data: python -I tools/snapshot.py data-fetch")
        for ln in names:
            with self.subTest(line=ln):
                page, errors, load = load_page(self.browser, self.url, ln, 300)
                self.assertNotIsInstance(load, dict, f"line {ln}: {load} {errors[:3]}")
                got = page.evaluate("window.world.userData.bedRows.map((rows) => rows.map((r) => "
                                    "[r[0], r[1], r[2], r[3], ...r[4], ...r[5]]))")
                page.close()
                with open(os.path.join(ROOT, "data", f"line{ln}.json"), encoding="utf-8") as f:
                    L = json.load(f)
                ours = bs.Beds(L).rows
                self.assertEqual(len(got), len(ours))
                worst, where = 0.0, None
                for k, (a, b) in enumerate(zip(got, ours)):
                    self.assertEqual(len(a), len(b), f"line {ln} track {k}: {len(a)} rows on the page, {len(b)} here")
                    if not a:
                        continue
                    A = np.asarray(a, float)
                    B = np.asarray([r[:4] + list(r[4]) + list(r[5]) for r in b], float)
                    d = np.abs(A - B).max(axis=1)
                    if d.max() > worst:
                        worst, where = float(d.max()), (k, int(d.argmax()), A[d.argmax()].round(3).tolist(),
                                                        B[d.argmax()].round(3).tolist())
                print(f"line {ln}: {sum(len(r) for r in ours)} rows, the farthest {worst * 1000:.2f} mm from the page's")
                self.assertLessEqual(worst, LIMIT, f"line {ln}: track {where[0]} row {where[1]}: page {where[2]}, "
                                                   f"here {where[3]}")


if __name__ == "__main__":
    unittest.main()
