# SPDX-License-Identifier: AGPL-3.0-or-later
"""The game's route is the build's (#276 step 2, #477): python -P -E tools/test_built_route.py.

On every line in data/: the page's route, from the path and the run the build wrote (`pathExt`), passes within 1 cm
of every built point at its arc length: the page reads the build's points as they are (resampled every metre, the
chords cut curves by up to 1.9 cm). Data built without the run, the curves, the radius or the cant does not load. Lines without data are skipped (python -I tools/snapshot.py data-fetch)."""
import faulthandler
import functools
import http.server
import json
import os
import threading
import unittest

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 0.01  # m: the decision's bound (docs/decisions/2026-11-05-ground-built-offline.md §3)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def lines():
    try:
        with open(os.path.join(ROOT, 'data', 'lines.json'), encoding='utf-8') as f:
            return [str(entry['line']) for entry in json.load(f)]
    except OSError:
        return []


class BuiltRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(300, exit=True)
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        cls.page.goto(f'http://127.0.0.1:{cls.server.server_port}/README.md')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        faulthandler.cancel_dump_traceback_later()

    def test_data_without_the_run_does_not_load(self):
        result = self.page.evaluate('''async () => {
          const {checkBuiltRoute}=await import('/src/route.js');
          const fails=(d)=>{try{checkBuiltRoute(d);return null;}catch(e){return String(e.message);}};
          return {none:fails({line:'x'}), curves:fails({line:'x',trackCurve:{}}), all:fails({line:'x',trackCurve:{},pathExt:{before:[],after:[]},curvature:{},cant:{},styles:[],lift:{},heights:{},spans:[],realDecks:[],underpasses:[],crossLevel:{}})};
        }''')
        self.assertIn('trackCurve, pathExt, curvature, cant, styles, lift, heights, spans, realDecks, underpasses, crossLevel', result['none'])
        self.assertIn('pathExt, curvature, cant, styles, lift', result['curves'])
        self.assertIsNone(result['all'])

    def test_the_route_passes_every_built_point(self):
        names = [n for n in lines() if os.path.exists(os.path.join(ROOT, 'data', f'line{n}.json'))]
        if not names:
            self.skipTest('no line data: python -I tools/snapshot.py data-fetch')
        for line in names:
            with self.subTest(line=line):
                r = self.page.evaluate('''async (line) => {
                  const {Route}=await import('/src/route.js');
                  const d=await (await fetch(`/data/line${line}.json`)).json();
                  if (!d.pathExt) return {missing: true};
                  const route=new Route(d.path, d.pathExt);
                  const all=[...d.pathExt.before, ...d.path, ...d.pathExt.after];
                  let c=0, s0=0, worst=0;
                  for (let i=1;i<=d.pathExt.before.length;i++) s0+=Math.hypot(all[i][0]-all[i-1][0], all[i][1]-all[i-1][1]);
                  const p={};
                  for (let i=0;i<all.length;i++) {
                    if (i) c+=Math.hypot(all[i][0]-all[i-1][0], all[i][1]-all[i-1][1]);
                    route.at(c-s0, p);
                    worst=Math.max(worst, Math.hypot(p.x-all[i][0], p.y-all[i][1]));
                  }
                  return {worst, points: all.length, from: route.s[0], to: route.s[route.s.length-1], length: route.length};
                }''', line)
                self.assertFalse(r.get('missing'), f'line {line}: no pathExt (built before #477)')
                self.assertLessEqual(r['worst'], LIMIT, f"line {line}: a built point {r['worst'] * 100:.2f} cm off the route")
                self.assertLess(r['from'], -59)
                self.assertGreater(r['to'], r['length'] + 59)
                print(f"line {line}: {r['points']} built points, the farthest {r['worst'] * 1000:.1f} mm off the game's route")


if __name__ == '__main__':
    unittest.main()
