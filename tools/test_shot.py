"""Screenshot controls and isolation: python -P -E tools/test_shot.py."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import capture, combine, site
import shot


HTML = '''<!doctype html><div id="view"><canvas id="gl" width="1280" height="720"></canvas></div>
<div id="loading" class="hidden"></div><div id="menu"><button id="btnStart">Start</button></div>
<select id="optWeather"><option value="dry">Dry</option></select>
<select id="optObst"><option value="off">Off</option></select>
<div id="top">HUD</div><div id="dash">Dashboard</div><div id="pausePanel">Pause</div><div id="msgs">Message</div>
<button id="touchToggle">Game controller</button>
<script>
const params = new URLSearchParams(location.search);
const vec = (values) => ({values, toArray() {return [...this.values]}, fromArray(a) {this.values = [...a]}});
window.camera = {position:vec([1,2,3]), quaternion:vec([0,0,0,1]), up:vec([0,1,0]), fov:60, near:.1, far:10000,
                zoom:1, aspect:1280/720, view:{enabled:true},
                clearViewOffset() {this.view.enabled=false}, updateProjectionMatrix() {}, updateMatrixWorld() {}};
window.drawCount = 0;
let chase = false;
document.addEventListener('keydown', e => {if (e.key === 'v') chase = true});
btnStart.onclick = () => {
  window.game = {paused:false, tram:{s:0,v:0,a:0}, route:{length:10000,
    at:s=>({x:s,y:s/2}), heading:()=>({hx:0,hy:1})}};
  window.traffic = {dispose() {}, update() {}};
  menu.classList.add('hidden');
};
if (params.has('review')) {
  const at = params.get('at').split(',').map(Number);
  window.review = {camera, T:{x:at[0],y:at[1],z:99}, ready:Promise.resolve(),
    _render() {camera.position.fromArray([this.T.x,this.T.z,this.T.y]);}};
  review._render();
  const box = document.createElement('div'); box.id='review'; document.body.append(box);
}
function frame() {
  if (window.game && !window.headless) {
    if (!game.paused) game.tram.s++;
    camera.position.fromArray([game.tram.s, chase ? 20 : 2, 3]);
  }
  const ctx = gl.getContext('2d'); ctx.fillStyle = '#344455'; ctx.fillRect(0,0,1280,720);
  ctx.fillStyle = '#778899'; ctx.fillRect(camera.position.values[0] % 400,20,50,50);
  drawCount++; requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>'''


class Shots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        (self.root / 'index.html').write_text(HTML, encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_cab_chase_and_review_are_paused_without_hud_and_reference_camera_is_locked(self):
        for view in ('cab', 'chase', 'review'):
            output = self.root / (view + '.png')
            before = (self.root / 'index.html').read_bytes()
            a = capture(self.browser, self.root, 17, 5064, view, output, 10)
            self.assertTrue(a['paused'])
            self.assertFalse(a['hud_visible'])
            self.assertTrue(a['canvas_visible'])
            self.assertFalse(a['view_offset_enabled'])
            if view != 'review':
                self.assertEqual(a['tram_s'], 5064)
            frozen = {**a['camera'], 'position': [11,22,33]}
            b = capture(self.browser, self.root, 17, 5064, view, self.root / ('ref-' + view + '.png'), 10,
                        pose=frozen, target=a['target_xy'])
            self.assertEqual(b['camera'], frozen)
            self.assertNotEqual(b['native_camera']['position'], frozen['position'])
            self.assertEqual((self.root / 'index.html').read_bytes(), before)
            with Image.open(output) as image:
                self.assertEqual(image.size, (1280,720))

    def test_load_timeout_closes_context_and_its_own_server(self):
        (self.root / 'index.html').write_text('<title>never ready</title>')
        count = len(self.browser.contexts)
        with self.assertRaises(TimeoutError):
            capture(self.browser, self.root, 17, 0, 'cab', self.root / 'no.png', .2)
        self.assertEqual(len(self.browser.contexts), count)
        self.assertFalse((self.root / 'no.png').exists())

    def test_servers_use_distinct_free_ports_and_pair_preserves_pixels(self):
        with site(self.root) as a, site(self.root) as b:
            self.assertNotEqual(a, b)
        for name, colour in [('a', 'red'), ('b', 'blue')]:
            Image.new('RGB', (20,10), colour).save(self.root / f'{name}.png')
        pair = self.root / 'pair.png'
        combine(self.root/'a.png', self.root/'b.png', pair, ['A','B'])
        with Image.open(pair) as image:
            self.assertEqual(image.size, (40,10 + shot.BAR))
            self.assertEqual(image.getpixel((0,shot.BAR)), (255,0,0))
            self.assertEqual(image.getpixel((20,shot.BAR)), (0,0,255))

    def test_a_missing_game_hook_is_named(self):
        (self.root / 'index.html').write_text(HTML.replace('dispose() {}, ', ''), encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'window.traffic.dispose'):
            capture(self.browser, self.root, 17, 5064, 'cab', self.root / 'x.png', 10)
        self.assertFalse((self.root / 'x.png').exists())

    def test_failed_reference_preserves_previous_images_and_removes_staging(self):
        output = self.root/'shots'
        output.mkdir()
        prior = output/'line17-s5064-cab-current.png'
        prior.write_bytes(b'previous successful image')
        def fake_capture(browser, root, line, s, view, dst, timeout, **kwargs):
            Image.new('RGB',(10,10),'red').save(dst)
            return {'camera':{},'target_xy':{}}
        with patch.object(shot,'git',return_value='reference'), patch.object(shot,'capture',fake_capture), \
             patch.object(shot,'checkout',side_effect=FileNotFoundError('cache blob absent')), self.assertRaises(SystemExit):
            shot.main(['--line','17','--s','5064','--out',str(output)], self.root)
        self.assertEqual(prior.read_bytes(), b'previous successful image')
        self.assertEqual(list(output.iterdir()), [prior])


if __name__ == '__main__':
    unittest.main(verbosity=2)
