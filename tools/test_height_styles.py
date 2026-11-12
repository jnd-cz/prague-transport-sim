# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared truth-fact offsets in the browser: python -P -E tools/test_height_styles.py."""

import json
from pathlib import Path
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = Path(__file__).resolve().parent.parent


class HeightStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]
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
          // (the sections are the build's, tools/track_styles.py: tools/test_track_styles.py)
          const styles = ['embedded', 'panels', 'grass', 'ballast'];
          const values = styles.map((style) => {
            const s = trackStyles(truth, {line: 'test', styles: [{s0: 100, s1: 200, style, source: 'user', mark: 0}]});
            return {style, d: s.sections[0].d, ids: s.sections[0].offsetFactIds};
          });
          // (the lift is the build's, data `lift` in mm every 2 m, tools/track_styles.py: the page interpolates it)
          const inferred = trackStyles(truth, {line: 'test', styles: [{s0: 0, s1: 100, style: 'grass', source: 'survey'}],
                                               lift: {step: 2, unit: 0.001, v: [0, 20, 40, 40]}});
          return {values, inferred: [inferred.lift(3), inferred.lift(6)], ids: inferred.sections[0].offsetFactIds};
        }""",
            self.truth,
        )
        for row in result['values']:
            fact = next(f for f in self.truth['trackHeights']['railAboveDeck'] if row['style'] in f['styles'])
            self.assertEqual(row['d'], fact['metres'])
            self.assertEqual(row['ids'], [fact['id']])
        self.assertAlmostEqual(result['inferred'][0], 0.03)
        self.assertAlmostEqual(result['inferred'][1], 0.04)
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
          for (const id of ['loading','loadPct','loadStep','loadBytes','loadFiles']) {
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
