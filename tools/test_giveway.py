# SPDX-License-Identifier: AGPL-3.0-or-later
"""The give-way check's geometry (tools/bench/giveway.js, #602) on made-up tracks and car ways:
python -P -E tools/test_giveway.py."""
import faulthandler
from pathlib import Path
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server, judge  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

# a straight track along x; one with a 20 m curve; car ways meeting them each its own way
SCENE = r"""async () => {
  const { Route } = await import('/src/route.js');
  const { wayStretches, reach } = await import('/tools/bench/giveway.js');
  const straight = new Route(Array.from({ length: 201 }, (_, i) => [i, 0]));
  const arc = (r, a0, a1, n = 60) => Array.from({ length: n + 1 }, (_, i) => { const a = (a0 + (a1 - a0) * i / n) * Math.PI / 180; return [r * Math.cos(a), r * Math.sin(a)]; });
  // east along y = -20, round a 20 m curve about (0, 0), west along y = 20
  const curve = new Route([[-40, -20], [-20, -20], ...arc(20, -90, 90).slice(0, -1), [0, 20], [-20, 20], [-40, 20]]);
  const way = (pts) => [{ path: new Route(pts), off: 0, conn: false, hf: null }];
  const ways = {
    across: [straight, way([[50, -20], [50, 20]])],
    shallowAcross: [straight, way([[20, -10], [20 + 40 * Math.cos(Math.PI / 6), -10 + 40 * Math.sin(Math.PI / 6)]])],
    alongsideNear: [straight, way([[60, 3], [95, 1.7], [140, 1.7], [175, 3]])],
    alongsideClear: [straight, way([[60, -3], [95, -2.4], [140, -2.4], [175, -3]])],
    ontoRails: [straight, way([[160, 8], [170, 0.3], [199, 0.3]])],
    cornerNear: [straight, way([[100, 12], [120, 2.65], [140, 12]])],
    curveOutside: [curve, way([...arc(27, -80, -62, 6), ...arc(22.4, -60, 60), ...arc(27, 62, 80, 6)])],
  };
  const out = {};
  for (const [name, [track, seq]] of Object.entries(ways)) {
    const ws = wayStretches(seq, [track]);
    out[name] = ws.map((w) => { const r = w.kind ? null : reach(seq, w); return { kind: w.kind || (r.least < 0 ? 'reach' : 'clear'), least: r && Math.round(r.least * 100) / 100, minD: Math.round(w.minD * 100) / 100 }; });
  }
  return out;
}"""


class GiveWay(unittest.TestCase):
    def test_kinds_of_entries_and_the_body_reach(self):
        faulthandler.dump_traceback_later(300, exit=True)
        server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                page = browser.new_page()
                page.route('**/giveway-test', lambda route: route.fulfill(body='<!doctype html><title>t</title>', content_type='text/html'))
                page.goto(url + '/giveway-test')
                r = page.evaluate(SCENE)
                browser.close()
        finally:
            stop_server(server)
            faulthandler.cancel_dump_traceback_later()
        kinds = {k: [w['kind'] for w in v] for k, v in r.items()}
        self.assertEqual(kinds['across'], ['cross'])
        # (30° to the track: the give-way loop took it for driving along before #602, |cos| 0.87; it crosses all the same)
        self.assertEqual(kinds['shallowAcross'], ['cross'])
        # (a car's middle 1.7 m from the centre: its side 0.8 m, inside the body's 1.25 m by 0.45 m; at the bend into it,
        # turned 2°, its corner 0.08 m deeper)
        self.assertEqual(kinds['alongsideNear'], ['reach'])
        self.assertAlmostEqual(r['alongsideNear'][0]['least'], -0.5, delta=0.06)
        # (2.4 m: 0.25 m clear on a straight, 0.17 m at the bend)
        self.assertEqual(kinds['alongsideClear'], ['clear'])
        self.assertAlmostEqual(r['alongsideClear'][0]['least'], 0.2, delta=0.06)
        self.assertEqual(kinds['ontoRails'], ['rails'])
        # (never in the band, its middle 2.65 m from the centre at the nearest, but turned 25° there: its corner 0.9 m from it)
        self.assertEqual(kinds['cornerNear'], ['reach'])
        self.assertGreater(r['cornerNear'][0]['minD'], 2.6)
        self.assertLess(r['cornerNear'][0]['least'], -0.05)
        # (the same 2.4 m outside a 20 m curve: the body's ends swing out about 0.9 m over it)
        self.assertEqual(kinds['curveOutside'], ['reach'])
        self.assertLess(r['curveOutside'][0]['least'], -0.4)

    def test_measured_not_judged(self):
        ok, line = judge('giveway', {'checks': {'waits': 3, 'waitInBody': {'count': 2, 'at': [], 'byRule': {'band': 2}},
                                                'letGoInBody': {'count': 0, 'at': []}, 'skippedCross': {'count': 1, 'at': []},
                                                'skippedReach': {'count': 0, 'at': []}}})
        self.assertTrue(ok)
        self.assertIn('in a passing body 2', line)


if __name__ == '__main__':
    unittest.main()
