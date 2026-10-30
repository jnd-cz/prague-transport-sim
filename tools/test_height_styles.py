"""Shared truth-fact offsets in the browser: python -P -E tools/test_height_styles.py."""

import json
from pathlib import Path
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server

ROOT = Path(__file__).resolve().parent.parent


class HeightStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        # An inert same-origin document avoids loading the whole game for module tests.
        cls.page.route(
            '**/height-style-test', lambda route: route.fulfill(body='<title>height styles</title>')
        )
        cls.page.goto(cls.url + '/height-style-test')
        cls.truth = json.loads((ROOT / 'data/truth.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)

    def test_all_styles_and_survey_grass_read_truth_facts_and_retain_ids(self):
        result = self.page.evaluate(
            """async (truth) => {
          const {trackStyles} = await import('/src/heights.js');
          const data = {line: 'test', stops: [{name: 'A', s: 100}, {name: 'B', s: 200}]};
          const styles = ['embedded', 'panels', 'grass', 'ballast'];
          const values = styles.map((style) => {
            const t = structuredClone(truth);
            t.trackStyles = [{line: 'test', from: 'A', to: 'B', style}];
            const s = trackStyles(t, data);
            return {style, d: s.sections[0].d, ids: s.sections[0].offsetFactIds};
          });
          truth.trackStyles = [];
          const fact = truth.trackHeights.railAboveDeck.find((f) => f.styles.includes('grass'));
          fact.metres = 0.09; // A changed fact must affect the runtime, including inferred grass.
          const inferred = trackStyles(truth, data, () => 'green', 100);
          return {values, inferred: inferred.lift(50), ids: inferred.sections[0].offsetFactIds};
        }""",
            self.truth,
        )
        for row in result['values']:
            fact = next(f for f in self.truth['trackHeights']['railAboveDeck'] if row['style'] in f['styles'])
            self.assertEqual(row['d'], fact['metres'])
            self.assertEqual(row['ids'], [fact['id']])
        self.assertAlmostEqual(result['inferred'], 0.09)
        self.assertEqual(result['ids'], ['rail-above-deck-grass'])

    def test_missing_and_conflicting_facts_fail_instead_of_guessing(self):
        errors = self.page.evaluate(
            """async (truth) => {
          const {trackStyleOffsets} = await import('/src/heights.js');
          const bad = structuredClone(truth.trackHeights.railAboveDeck[0]);
          bad.metres += 1;
          const conflicting = structuredClone(truth);
          conflicting.trackHeights.railAboveDeck.push(bad);
          return [null, conflicting].map((t) => {
            try {trackStyleOffsets(t); return null;} catch (e) {return e.message;}
          });
        }""",
            self.truth,
        )
        self.assertTrue(all('Missing or conflicting' in e for e in errors))


if __name__ == '__main__':
    unittest.main(verbosity=2)
