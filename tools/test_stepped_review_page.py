# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/stepped_review.py stepped_places (the rule di_network.Network.state_steps states the stepped-curve answers by,
#672) against tools/lint.js steppedCurves itself: on DI's own lines through every answered place in data/truth.json
trackSources.steppedAnswers (Network.line_through), the same places flagged with the same radii.

    python -P -E tools/test_stepped_review_page.py
A browser test (it loads lint.js, not the game). Skipped without DI's snapshot (python -I tools/snapshot.py fetch).
"""
import faulthandler
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402
import stepped_review as sr  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = """<!doctype html><script type="importmap">
{ "imports": { "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/" } }
</script><script type="module">
import { steppedCurves } from '/tools/lint.js';
window.steppedCurves = steppedCurves;
</script>"""


def js_round(v):
    """Math.round: halves up (s lies on halves: 12.5 + 2k)."""
    return math.floor(v + 0.5)


def buckets(found):
    """lint.js's places from stepped_places: per 10 m of s the one of the largest R25 / R5."""
    out = {}
    for q in found:
        k = js_round(q['s'] / 10)
        mag = q['r25'] / q['r5']
        if not (k in out and out[k]['mag'] >= mag):
            out[k] = {'s': js_round(q['s']), 'mag': mag, 'r5': q['r5'], 'r25': q['r25']}
    return out


def polylines():
    """DI's lines through each answered place: [(answer's decision, polyline)]."""
    import di_network
    import di_tracks
    net = di_network.load_network()
    out = []
    for xy, _, reach, key in [(xy, a, r, i) for i, (xy, a, r) in enumerate(di_tracks.stepped_answers())]:
        pt = di_network.Point(xy)
        for i in net.tree.query(pt.buffer(reach)):
            e = net.eids[i]
            if net.edges[e]['line'].distance(pt) <= reach:
                out.append((key, net.line_through(e)))
    return out


class Agreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(600, exit=True)

    @classmethod
    def tearDownClass(cls):
        faulthandler.cancel_dump_traceback_later()

    def test_the_rule_flags_what_lint_flags(self):
        from dtmp_tracks import DI
        if not (DI / 'provenance.json').exists():
            self.skipTest("no DI snapshot: python -I tools/snapshot.py fetch")
        lines = polylines()
        self.assertTrue(lines)
        from playwright.sync_api import sync_playwright
        server, url = serve(0)
        pw = sync_playwright().start()
        browser = gpu.launch(pw)[0]
        try:
            page = browser.new_page()
            page.goto(f"{url}/README.md")
            page.set_content(PAGE)
            page.wait_for_function("!!window.steppedCurves", timeout=60_000)
            flagged = 0
            for key, p in lines:
                js = page.evaluate("(p) => window.steppedCurves({ data: { path: p } })", [list(q[:2]) for q in p])
                ours = buckets(sr.stepped_places(p))
                # (lint.js lists its TOP places of the most R25 / R5: each one ours too, at the same s and radii)
                self.assertEqual(len(ours), js['count'], f"answer {key}")
                by_s = {q['s']: q for q in ours.values()}
                for q in js['places']:
                    self.assertIn(q['s'], by_s, f"answer {key}")
                    self.assertTrue(math.isclose(by_s[q['s']]['mag'], q['mag'], rel_tol=1e-9), f"answer {key}")
                flagged += len(ours)
            print(f"{len(lines)} DI lines through {len({k for k, _ in lines})} answered places: {flagged} places "
                  "flagged, the same as lint.js")
        finally:
            browser.close()
            pw.stop()
            stop_server(server)


if __name__ == '__main__':
    unittest.main()
