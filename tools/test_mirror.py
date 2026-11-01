"""Mirror texture cadence, composition and renderer state: python -P -E tools/test_mirror.py.

Uses the real Three.js camera/target/geometry and a recording renderer, on its own free-port server.
No whole city is needed to test timestamps or exception-safe visibility restoration.
"""
import json
from pathlib import Path
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shot import site

ROOT = Path(__file__).resolve().parent.parent
SETUP = '''async () => {
  const THREE = await import('three');
  const {Mirror} = await import('/src/mirror.js');
  window.fixture = () => {
    const source = new THREE.Scene(), model = new THREE.Group(), detail = new THREE.Group(), hidden = new THREE.Group();
    model.visible = false; hidden.visible = false;
    let box = {left:100, bottom:300, width:150, height:190};
    const r = {target:null, viewport:new THREE.Vector4(1,2,3,4), scissor:new THREE.Vector4(5,6,7,8),
      clipping:false, autoClear:true, calls:[], fail:false, getPixelRatio:()=>1,
      getRenderTarget() {return this.target}, setRenderTarget(t) {this.target=t},
      getViewport(v) {return v.copy(this.viewport)}, setViewport(...v) {this.viewport = v.length===1 ? v[0].clone() : new THREE.Vector4(...v)},
      getScissor(v) {return v.copy(this.scissor)}, setScissor(...v) {this.scissor = v.length===1 ? v[0].clone() : new THREE.Vector4(...v)},
      getScissorTest() {return this.clipping}, setScissorTest(v) {this.clipping=v},
      render(scene,camera) {
        this.calls.push({texture:!!this.target, model:model.visible, detail:detail.visible, hidden:hidden.visible});
        if (this.fail === true || this.fail === 'overlay' && !this.target) throw new Error('draw failed');
      }};
    const mirror = new Mirror(r,source,{getBoundingClientRect:()=>box},[detail,hidden]);
    let poses=0;
    return {mirror,r,model,detail,hidden, setBox:v=>box=v, draw:(t,active=true)=>mirror.draw(t,active,()=>poses++,model), poses:()=>poses};
  };
}'''


class MirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = site(ROOT)
        url = cls.host.__enter__()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        importmap = (ROOT/'index.html').read_text(encoding='utf-8').split('<script type="importmap">')[1].split('</script>')[0]
        cls.page.route('**/mirror-test', lambda route: route.fulfill(body=f'<script type="importmap">{importmap}</script>'))
        cls.page.goto(url+'/mirror-test')
        cls.page.evaluate(SETUP)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.host.__exit__(None,None,None)

    def test_60_120_and_144_hz_capture_at_30_hz_but_present_every_frame(self):
        r = self.page.evaluate('''() => [60,120,144].map(hz => {
          const f=fixture(); for(let i=0;i<hz*3;i++) f.draw(i*1000/hz);
          return {hz,...f.mirror.stats,poses:f.poses()};
        })''')
        for row in r:
            self.assertEqual(row['updates'],90,row)
            self.assertEqual(row['poses'],90)
            self.assertEqual(row['presents'],row['hz']*3)

    def test_slow_or_resumed_frames_do_not_burst_and_idle_presents_cached_texture(self):
        r = self.page.evaluate('''() => {
          const f=fixture(); f.draw(0); f.draw(250); const slow=f.mirror.stats.updates;
          for(let i=1;i<=4;i++) f.draw(250+i*250,false);
          const idle=f.mirror.stats.updates; f.draw(10000); f.draw(10001);
          return {slow,idle,...f.mirror.stats};
        }''')
        self.assertEqual(r['slow'],2)
        self.assertEqual(r['idle'],2)
        self.assertEqual(r['updates'],3)
        self.assertEqual(r['presents'],8)

    def test_hidden_frame_is_not_drawn_and_resizing_fills_new_target_before_presenting(self):
        r = self.page.evaluate('''() => {
          const f=fixture(); f.setBox({width:0,height:0}); f.draw(0);
          const hidden={...f.mirror.stats}; f.setBox({left:0,bottom:300,width:300,height:380});
          f.draw(1,false); return {hidden,...f.mirror.stats,width:f.mirror.target.width,height:f.mirror.target.height};
        }''')
        self.assertEqual(r['hidden']['updates'],0)
        self.assertEqual(r['updates'],1)
        self.assertEqual(r['presents'],1)
        self.assertEqual(r['height'],368)
        self.assertEqual(r['width'],round(368*150/190))

    def test_camera_fov_aspect_far_plane_and_horizontal_uv_flip(self):
        r = self.page.evaluate('''() => {
          const f=fixture(),m=f.mirror,uv=m.scene.children[0].geometry.attributes.uv;
          return {fov:m.camera.fov,aspect:m.camera.aspect,far:m.camera.far,near:m.camera.near,
                  uv:[uv.getX(0),uv.getX(1),uv.getX(2),uv.getX(3)]};
        }''')
        self.assertEqual(r['fov'],30)
        self.assertEqual(r['far'],300)
        self.assertEqual(r['near'],.3)
        self.assertAlmostEqual(r['aspect'],150/190)
        self.assertEqual(r['uv'],[1,0,1,0])

    def test_model_details_and_render_state_are_restored_after_both_draws(self):
        r = self.page.evaluate('''() => {
          const f=fixture(); f.draw(0);
          return {calls:f.r.calls, model:f.model.visible,detail:f.detail.visible,hidden:f.hidden.visible,
            viewport:f.r.viewport.toArray(),scissor:f.r.scissor.toArray(),clip:f.r.clipping,clear:f.r.autoClear,target:f.r.target};
        }''')
        self.assertEqual(r['calls'][0],{'texture':True,'model':True,'detail':False,'hidden':False})
        self.assertEqual(r['calls'][1]['detail'],True)
        self.assertFalse(r['model'])
        self.assertTrue(r['detail'])
        self.assertFalse(r['hidden'])
        self.assertEqual(r['viewport'],[1,2,3,4])
        self.assertEqual(r['scissor'],[5,6,7,8])
        self.assertFalse(r['clip'])
        self.assertTrue(r['clear'])
        self.assertIsNone(r['target'])

    def test_texture_draw_failure_restores_visibility_and_target(self):
        r = self.page.evaluate('''() => {
          const f=fixture(); f.r.fail=true; try {f.draw(0)} catch(e) {}
          return {model:f.model.visible,detail:f.detail.visible,hidden:f.hidden.visible,target:f.r.target};
        }''')
        self.assertEqual(r,{'model':False,'detail':True,'hidden':False,'target':None})

    def test_overlay_failure_restores_viewport_scissor_and_clear_mode(self):
        r = self.page.evaluate('''() => {
          const f=fixture(); f.r.fail='overlay'; try {f.draw(0)} catch(e) {}
          return {v:f.r.viewport.toArray(),s:f.r.scissor.toArray(),clip:f.r.clipping,clear:f.r.autoClear};
        }''')
        self.assertEqual(r,{'v':[1,2,3,4],'s':[5,6,7,8],'clip':False,'clear':True})


if __name__ == '__main__':
    unittest.main(verbosity=2)
