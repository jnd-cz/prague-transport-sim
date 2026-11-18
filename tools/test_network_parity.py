# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network the build makes (tools/network.py) is the page's: line 17's network built here against the one its Start
builds (src/traffic.js), every point, kerb, median and track position the same to the cm. The page's code goes once the
page reads the layer (#658); until then this holds the port to it. Every line: python -P -E tools/network.py --parity.

    python -P -E tools/test_network_parity.py
A browser test (about 40 s). Skipped without line 17's data (python -I tools/snapshot.py data-fetch).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402
import network as nw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = "17"  # (the line with every part: OSM stop lines, pedestrian heads, medians)


class PageParity(unittest.TestCase):
    def test_network_is_the_pages(self):
        if not os.path.exists(os.path.join(ROOT, "data", f"line{LINE}.ground.json")):
            self.skipTest(f"no line {LINE} data: python -I tools/snapshot.py data-fetch")
        from playwright.sync_api import sync_playwright
        built = nw.build(LINE, log=lambda m: None)
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            try:
                page = nw.page_roads([LINE], browser)[LINE]
            finally:
                browser.close()
        for part in nw.PARTS:
            with self.subTest(part):
                rep = nw.compare(page[part], built[part])
                self.assertGreater(len(built[part]), 0)
                # (the page keeps its pedestrian heads only in their poles' 32-bit matrices: within the rounding there)
                same = rep["equal"] if part == "pedHeads" else rep["exact"]
                self.assertEqual((rep["page"], same), (len(built[part]), len(built[part])), rep)


if __name__ == "__main__":
    unittest.main()
