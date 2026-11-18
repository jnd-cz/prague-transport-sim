# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network the build makes (tools/network.py) is the page's: line 37's roads built here against the roads its Start
builds (src/traffic.js), every point, kerb, median and track position the same to the cm. The page's code goes once the
page reads the layer (#658); until then this holds the port to it. Every line: python -P -E tools/network.py --parity.

    python -P -E tools/test_network_parity.py
A browser test (about 30 s). Skipped without line 37's data (python -I tools/snapshot.py data-fetch).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402
import network as nw  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINE = "37"


class PageParity(unittest.TestCase):
    def test_roads_are_the_pages(self):
        if not os.path.exists(os.path.join(ROOT, "data", f"line{LINE}.ground.json")):
            self.skipTest(f"no line {LINE} data: python -I tools/snapshot.py data-fetch")
        from playwright.sync_api import sync_playwright
        built = nw.build(LINE, log=lambda m: None)["roads"]
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            try:
                page = nw.page_roads([LINE], browser)[LINE]
            finally:
                browser.close()
        rep = nw.compare(page, built)
        self.assertEqual((rep["page"], rep["exact"]), (len(built), len(built)), rep)


if __name__ == "__main__":
    unittest.main()
