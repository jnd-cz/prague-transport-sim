"""Audio lifecycle: python -P -E tools/test_audio_pause.py (own free-port server)."""
from pathlib import Path
import sys
import unittest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server


class AudioPause(unittest.TestCase):
    def test_shift_lifecycle(self):
        server, url = serve(0)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 960, 'height': 600})
                page.goto(url + '/?line=23', timeout=180000)
                page.wait_for_selector('#btnStart', state='visible', timeout=180000)
                page.click('#btnStart')
                page.wait_for_function('window.game && game.audio.master && game.audio.active', timeout=120000)
                def gain(value):
                    page.wait_for_function('(n) => Math.abs(game.audio.master.gain.value - n) < 0.001', arg=value, timeout=30000)
                page.evaluate('game.tram.v = 5')
                gain(0.6)
                page.keyboard.press('p')
                gain(0)
                self.assertEqual(page.evaluate('''() => {
                  const a=game.audio, f=a.ctx.createBufferSource.bind(a.ctx); let n=0;
                  a.ctx.createBufferSource=()=>{n++; return f();}; a.click();
                  a.ctx.createBufferSource=f; return n;
                }'''), 0)
                page.keyboard.press('m')  # paused controls do not change the saved mute preference
                page.keyboard.press('p')
                gain(0.6)
                page.keyboard.press('m')
                gain(0)
                page.keyboard.press('p')
                page.keyboard.press('p')
                gain(0)
                page.keyboard.press('m')
                gain(0.6)
                page.keyboard.press('F9')
                page.wait_for_selector('#rpBox.show')
                gain(0)
                page.click('#rpCancel')
                gain(0.6)
                page.keyboard.press('i')
                page.keyboard.press('Space')
                gain(0)
                page.keyboard.press('Space')
                gain(0.6)
                page.keyboard.press('i')
                page.keyboard.press('p')
                gain(0)
                page.click('#btnToMenu')
                gain(0)
                page.click('#btnStart')
                gain(0.6)
                page.evaluate('game.finished = true')
                gain(0)
                browser.close()
        finally:
            stop_server(server)


if __name__ == '__main__':
    unittest.main(verbosity=2)
