# SPDX-License-Identifier: AGPL-3.0-or-later
"""The surfaces check's seams and a raised tram belt's kerb (#770): python -P -E tools/test_surfaces_check.py.

A strip of ground across a made-up route, in a page: road, the tram's surface H over it, road again, then the tram's
surface 0.12 m under the road. `run()` of tools/bench/surfaces.js counts the two edges of the raised belt as bedKerbs
where H is a kerb's (over data/truth.json `raised-belt`, up to 0.25 m) and as seams otherwise; a road over the tram's
surface is a seam at any height."""
from pathlib import Path
import re
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = Path(__file__).resolve().parent.parent
ROWS = 3  # the check reads a row every 4 m: a route of 9 m has s 0, 4, 8

RUN = '''async (H) => {
  const at = (lat) => lat < -10 ? null : lat < 0 ? {c: 'road', z: 200} : lat < 3 ? {c: 'tram', z: 200 + H}
    : lat < 6 ? {c: 'road', z: 200} : lat < 9 ? {c: 'tram', z: 199.88} : null;
  window.game = {data: {}, route: {length: 9, offset: (s, lat) => ({x: s, y: lat}),
    ground: {dtm: {surfaceAt: () => null}, lookup: {survey: (x, y) => at(y)}}}};
  const {run} = await import('/tools/bench/surfaces.js');
  const c = (await run()).checks;
  return {seams3: c.seams3.count, seams10: c.seams10.count, bedKerbs: c.bedKerbs.count, over10cm: c.bedKerbs.over10cm,
    medianCm: c.bedKerbs.medianCm};
}'''


class SurfacesCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]
        cls.page = cls.browser.new_page()
        cls.page.set_default_timeout(60000)
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        importmap = re.search(r'<script type="importmap">.*?</script>', html, re.S)[0]
        cls.page.route('**/surfaces-test', lambda route: route.fulfill(body=importmap))
        cls.page.goto(cls.url + '/surfaces-test')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)

    def run_strip(self, h):
        return self.page.evaluate(RUN, h)

    def test_a_raised_belts_kerb_is_counted_apart_from_the_seams(self):
        r = self.run_strip(0.12)
        # (both edges of the belt in every row; the road over the lower tram surface stays a seam)
        self.assertEqual((r['bedKerbs'], r['over10cm'], r['medianCm']), (2 * ROWS, 2 * ROWS, 12))
        self.assertEqual((r['seams3'], r['seams10']), (ROWS, ROWS))

    def test_a_kerb_of_under_10_cm_is_one_the_10_cm_seams_never_counted(self):
        r = self.run_strip(0.09)
        self.assertEqual((r['bedKerbs'], r['over10cm']), (2 * ROWS, 0))
        self.assertEqual((r['seams3'], r['seams10']), (ROWS, ROWS))

    def test_a_belt_no_higher_than_an_unraised_one_is_a_seam(self):
        r = self.run_strip(0.05)  # (data/truth.json raised-belt: 0.07 m)
        self.assertEqual(r['bedKerbs'], 0)
        self.assertEqual((r['seams3'], r['seams10']), (3 * ROWS, ROWS))

    def test_a_step_higher_than_a_kerb_is_a_seam(self):
        r = self.run_strip(0.30)
        self.assertEqual(r['bedKerbs'], 0)
        self.assertEqual((r['seams3'], r['seams10']), (3 * ROWS, 3 * ROWS))


if __name__ == '__main__':
    unittest.main()
