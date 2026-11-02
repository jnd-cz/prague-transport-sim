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

    def test_missing_required_truth_is_an_explicit_loading_error_that_cannot_be_overwritten(self):
        result = self.page.evaluate('''async () => {
          const {loadHeightFacts} = await import('/src/heights.js');
          const {Loader} = await import('/src/loading.js');
          for (const id of ['loading','loadPct','loadStep']) {
            if (!document.getElementById(id)) { const e=document.createElement('div'); e.id=id; document.body.append(e); }
          }
          document.getElementById('loading').classList.add('hidden');
          const loader=new Loader();
          try {await loadHeightFacts(async()=>({ok:false,status:404}));}
          catch(e) {loader.fail(e);}
          loader.render(true);
          return {visible:!document.getElementById('loading').classList.contains('hidden'),
                  title:document.getElementById('loadPct').textContent,
                  message:document.getElementById('loadStep').textContent};
        }''')
        self.assertTrue(result['visible'])
        self.assertEqual(result['title'],'Cannot start')
        self.assertIn('data/truth.json',result['message'])
        self.assertIn('404',result['message'])

    def test_fact_download_uses_the_same_conflict_validation(self):
        result = self.page.evaluate('''async truth => {
          const {loadHeightFacts} = await import('/src/heights.js');
          truth.trackHeights.railAboveDeck.push({...truth.trackHeights.railAboveDeck[0],metres:1});
          try {await loadHeightFacts(async()=>({ok:true,json:async()=>truth})); return null;}
          catch(e) {return e.message;}
        }''',self.truth)
        self.assertIn('Missing or conflicting',result)

    def test_actual_startup_shows_a_missing_truth_file(self):
        page = self.browser.new_page()
        try:
            page.route('**/data/truth.json',lambda route:route.fulfill(status=404,body='missing'))
            page.goto(self.url+'/?line=37')
            page.wait_for_function("document.getElementById('loadPct')?.textContent==='Cannot start'",timeout=30000)
            self.assertTrue(page.locator('#loading').is_visible())
            self.assertIn('data/truth.json',page.locator('#loadStep').inner_text())
            self.assertIn('404',page.locator('#loadStep').inner_text())
        finally:
            page.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
