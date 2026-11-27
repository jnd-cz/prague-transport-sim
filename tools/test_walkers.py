# SPDX-License-Identifier: AGPL-3.0-or-later
"""Walkers with nowhere to go (#366, #269, #393): python -P -E tools/test_walkers.py (own free-port server, a page with
no game in it). src/traffic.js `_updateWalkers` stepped on made-up walks and tracks:
- between the two tracks of a crossing (the tracks near both ways) a walker leaves: it does not stand there turning
  (line 17 s 2918, three walkers twitching in the maintainer's report of 2026-11-18);
- along a track inside TRACK_CLEAR it keeps walking (turning there every frame froze it in a car's way, line 23 s 662);
- towards a track it turns back before it and walks away, and pacing between a dead end and the tracks is no reason to
  leave; on a crossing over a reserved track it turns back onto the sidewalk it came from;
- one held in one place for no reason leaves after STILL_T; one waiting at the kerb for its red stays;
- none appears between the tracks."""
import faulthandler
from pathlib import Path
import re
import sys
import unittest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

FIXTURE = '''async () => {
  const {Traffic} = await import('/src/traffic.js');
  // a straight walk from (x0, y0) along (hx, hy), L long
  window.walk = (x0, y0, hx, hy, L) => ({ off: 0, links: [[], []], doors: [], path: { length: L,
    at: (s) => { s = Math.max(0, Math.min(L, s)); return { x: x0 + hx * s, y: y0 + hy * s, hx, hy }; } } });
  // tracks: the y of each track's centre line (along x); lane(x, y): in a car lane; red: the walkers' light at a kerb
  window.fixture = ({ tracks = [], lane = () => false, red = false, walk, w = {} } = {}) => {
    const tr = Object.create(Traffic.prototype);
    tr.trackDist = (x, y) => Math.min(100, ...tracks.map((ty) => Math.abs(y - ty)));
    tr.inLane = lane; tr.rand = () => 0.99; tr.ground = { surface: () => 0 };
    tr.walkLoops = new Map(); tr.walkLeaves = new Map();
    tr._pedRed = () => red; tr._carComing = () => false; tr._ringDoor = () => null; tr._ringIndex = () => null;
    tr.walks = walk ? [walk] : [];
    tr.slots = new Array(90).fill(null);
    if (walk) tr.slots[0] = { walk, s: 0, dir: 1, v: 1.4, side: 0, alpha: 1, goal: 1e9, walked: 0, ...w };
    return tr;
  };
  // step the walkers for secs at 30 Hz; the walker in slot 0 (null once gone) and the range of its y
  window.run = (tr, secs) => {
    let lo = Infinity, hi = -Infinity;
    for (let k = 0; k < secs * 30; k++) {
      tr._updateWalkers(1 / 30, 0, 0);
      const o = tr.slots[0];
      if (o?.y !== undefined) { lo = Math.min(lo, o.y); hi = Math.max(hi, o.y); }
    }
    const o = tr.slots[0];
    return { gone: !o, leave: !!o?.leave, x: o?.x, y: o?.y, dir: o?.dir, lo, hi, leaves: [...tr.walkLeaves.keys()] };
  };
}'''


class Walkers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(120, exit=True)
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]
        cls.page = cls.browser.new_page()
        html = (Path(__file__).resolve().parent.parent / 'index.html').read_text(encoding='utf-8')
        importmap = re.search(r'<script type="importmap">.*?</script>', html, re.S)[0]
        cls.page.route('**/walkers-test', lambda r: r.fulfill(body=importmap))
        cls.page.goto(cls.url + '/walkers-test')
        cls.page.evaluate(FIXTURE)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def run_js(self, body):
        return self.page.evaluate(f'() => {{ {body} }}')

    def test_between_two_tracks_it_leaves(self):
        # a crossing over two tracks 3.2 m apart, the walker midway: each way leads onto a track
        r = self.run_js('''
          const tr = fixture({ tracks: [0, 3.2], walk: walk(0, -10, 0, 1, 23.2), w: { s: 11.6 } });
          return run(tr, 3);''')
        self.assertTrue(r['gone'], r)
        self.assertEqual([k.split(' ')[0] for k in r['leaves']], ['turns'])

    def test_along_a_track_it_keeps_walking(self):
        # a footway 2.5 m from a track centre, inside TRACK_CLEAR all along
        r = self.run_js('''
          const tr = fixture({ tracks: [0], walk: walk(0, 2.5, 1, 0, 100), w: { s: 10 } });
          return run(tr, 5);''')
        self.assertFalse(r['gone'] or r['leave'], r)
        self.assertEqual(r['dir'], 1)
        self.assertGreater(r['x'], 16)

    def test_towards_a_track_it_turns_back_and_paces_without_leaving(self):
        # a dead-end walk running down onto a track: it turns before the track, walks back to the dead end, turns
        # there and comes back: 5-6 m legs, never inside TRACK_CLEAR, never leaving
        r = self.run_js('''
          const tr = fixture({ tracks: [0], walk: walk(0, 10, 0, -1, 20), w: { s: 2 } });
          const a = run(tr, 4), b = run(tr, 26);
          return { a, b };''')
        self.assertEqual(r['a']['dir'], -1, r)
        self.assertFalse(r['b']['gone'] or r['b']['leave'], r)
        self.assertGreater(min(r['a']['lo'], r['b']['lo']), 2.8)
        self.assertEqual(r['b']['leaves'], [])

    def test_at_a_crossing_over_a_reserved_track_it_goes_back_the_way_it_came(self):
        # a sidewalk along y 5 ends at x 0 where a crossing runs down over two tracks (y 0 and -3.2): on the crossing the
        # tracks turn it back to its start, where only the sidewalk it came from leads on; it takes it (no dead end)
        r = self.run_js('''
          const A = walk(-60, 5, 1, 0, 60), L = walk(0, 5, 0, -1, 13);
          A.links[1] = [{ walk: L, s: 0 }]; L.links[0] = [{ walk: A, s: 60 }];
          const tr = fixture({ tracks: [0, -3.2], walk: A, w: { s: 50 } });
          const out = run(tr, 20);
          return { ...out, onA: tr.slots[0]?.walk === A };''')
        self.assertFalse(r['gone'] or r['leave'], r)
        self.assertEqual(r['leaves'], [])
        self.assertTrue(r['onA'], r)
        self.assertLess(r['x'], -10)
        self.assertGreater(r['lo'], 2.8)

    def test_held_for_no_reason_it_leaves_after_still_t(self):
        r = self.run_js('''
          const tr = fixture({ walk: walk(0, 50, 1, 0, 100), w: { s: 10, v: 0 } });
          const a = run(tr, 9), b = run(tr, 2), c = run(tr, 2);
          return { a, b, c };''')
        self.assertFalse(r['a']['leave'] or r['a']['gone'], r)
        self.assertTrue(r['b']['leave'] or r['b']['gone'], r)
        self.assertTrue(r['c']['gone'], r)
        self.assertEqual([k.split(' ')[0] for k in r['c']['leaves']], ['stuck'])

    def test_waiting_at_the_kerb_for_its_red_is_a_reason(self):
        # the lane starts at x 12; its red holds the walker at the kerb for 30 s
        r = self.run_js('''
          const tr = fixture({ lane: (x) => x > 12, red: true, walk: walk(0, 50, 1, 0, 100), w: { s: 10.6 } });
          return run(tr, 30);''')
        self.assertFalse(r['gone'] or r['leave'], r)
        self.assertEqual(r['leaves'], [])

    def test_none_appears_between_the_tracks(self):
        r = self.run_js('''
          const at = (y) => {
            const tr = fixture({ tracks: [0, 3.2] });
            tr.walks = [walk(-50, y, 1, 0, 100)]; tr.rand = () => 0.1; tr._ringIndex = () => ['w', 0, 40];
            tr._updateWalkers(1 / 30, 0, 0);
            return tr.slots.filter(Boolean).length;
          };
          return [at(1.6), at(8)];''')
        self.assertEqual(r, [0, 1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
