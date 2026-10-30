"""Browser regression tests for #111: python -P -E tools/test_headless_timeout.py."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import headless


HTML = """<!doctype html><title>9</title><div id="loading" class="hidden"></div>
<input id="selStop"><input id="selTrip"><input id="optWeather"><input id="optObst">
<button id="btnStart"></button><script>
const mode = location.pathname.split('/')[1];
if (mode === 'loading') document.getElementById('loading').className = '';
window.game = {
  clock: 0, tram: {s: 11221, v: 0}, route: {length: 20000, at: () => ({x: 0, y: 0})},
  profile: {height: () => 0}, penalties: {}, signals: [], nextStop: 0,
  stops: mode === 'scheduled' ? [{arrived: true, sched: 1800}] : [], _atStop: () => true,
  update(h) { this.clock += h; if (mode === 'finish') this.tram.s += 100; }
};
window.traffic = {oncoming: [], ahead: [], backStops: [], update() {}};
window.camera = {position: {set() {}}};
</script>"""


class Handler(BaseHTTPRequestHandler):
    started = Event()

    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/started':
            self.started.set()
        if path == '/tools/bench/redruns.js':
            body = (Path(__file__).parent / 'bench' / 'redruns.js').read_bytes()
            mime = 'text/javascript'
        elif path == '/src/autopilot.js':
            body = b'export class Autopilot { constructor() { this.input = {}; } step() {} }'
            mime = 'text/javascript'
        else:
            body, mime = HTML.encode(), 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', mime)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class TimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def run_bench(self, mode='', timeout=5):
        result, _ = headless.run_one(self.browser, self.url + '/' + mode, '9', 'redruns', 2, timeout)
        self.assertEqual(self.browser.contexts, [], 'each job must close its page/context')
        return result

    def test_timeout_then_next_job(self):
        Handler.started.clear()
        with patch.dict(headless.CALLS, redruns="await fetch('/started'); return await new Promise(() => {});"):
            start = time.monotonic()
            self.assertEqual(self.run_bench(timeout=0.5), {'error': 'timeout'})
            self.assertLess(time.monotonic() - start, 3)
            self.assertTrue(Handler.started.is_set(), 'the hanging bench must start before its timeout')
        result = self.run_bench('finish')
        self.assertIsNone(result['stuck'])
        self.assertTrue(headless.judge('redruns', result)[0])

    def test_loading_uses_same_deadline(self):
        start = time.monotonic()
        self.assertEqual(self.run_bench('loading', timeout=0.5), {'error': 'timeout'})
        self.assertLess(time.monotonic() - start, 3)

    def test_rejection_is_a_result(self):
        with patch.dict(headless.CALLS, redruns="await Promise.resolve(); throw new Error('bench failed');"):
            self.assertEqual(self.run_bench(), {'error': 'Error: bench failed'})

    def test_stuck_and_scheduled_wait(self):
        for mode, departure in [('', 0), ('scheduled', 1800)]:
            with self.subTest(mode=mode):
                # Include the fixture clock in the result to check scheduled waits, not only the position.
                js = headless.CALLS['redruns'].replace('return await run(SEED);',
                    'const r = await run(SEED); return {...r, clock: window.game.clock};')
                with patch.dict(headless.CALLS, redruns=js):
                    result = self.run_bench(mode)
                self.assertEqual(result['stuck'], 11221)
                self.assertGreater(result['clock'], departure + 600)
                self.assertLess(result['clock'], departure + 630)
                self.assertIn('stuck at 11221', headless.judge('redruns', result)[1])
                self.assertEqual(headless.counts('redruns', result)['stuck'], 11221)

    def test_stuck_at_zero_fails_both_judges(self):
        self.assertFalse(headless.judge('redruns', {'stuck': 0})[0])
        batch = (Path(__file__).parent / 'bench' / 'batch.html').read_text(encoding='utf-8')
        judge = batch[batch.index('function judge('):batch.index('function render()')]
        page = self.browser.new_page()
        try:
            result = page.evaluate('() => { ' + judge + ' return judge("redruns", {stuck: 0}); }')
            self.assertFalse(result['ok'])
            self.assertIn('stuck at 0', result['text'])
        finally:
            page.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
