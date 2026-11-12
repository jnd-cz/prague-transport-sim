# SPDX-License-Identifier: AGPL-3.0-or-later
"""AI waiting cycles: python -P -E tools/test_tram_cycles.py (own free-port server)."""
import faulthandler
from pathlib import Path
import re
import sys
import unittest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from headless import serve, stop_server
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)


class TramCycles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        faulthandler.dump_traceback_later(120, exit=True)
        cls.server, cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = gpu.launch(cls.pw)[0]
        cls.page = cls.browser.new_page()
        html = (Path(__file__).resolve().parent.parent / 'index.html').read_text(encoding='utf-8')
        importmap = re.search(r'<script type="importmap">.*?</script>', html, re.S)[0]
        cls.page.route('**/tram-cycle-test', lambda r: r.fulfill(body=importmap))
        cls.page.goto(cls.url + '/tram-cycle-test')
        cls.page.evaluate('''async () => {
          const {Traffic} = await import('/src/traffic.js');
          window.fixture = () => {
            const tr = Object.create(Traffic.prototype);
            const t = {id:1,s:100,v:0,dwell:0,stop:{s:100,why:'car on track'}};
            const cars = [307,295,297].map(id=>({id,kind:'road',active:true,vNow:0,why:'lead'}));
            t.waitFor=cars[0]; cars[0].waitFor=cars[1]; cars[1].waitFor=cars[2]; cars[2].waitFor=t;
            tr.ahead=[]; tr.oncoming=[t]; tr.cars=cars; tr.game={clock:800};
            return {tr,t,cars};
          };
          window.tick = (tr,n) => { for(let i=0;i<n;i++) tr._clearAiTramCycles(1); };
        }''')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)
        faulthandler.cancel_dump_traceback_later()

    def test_closed_cycle_fades_one_car_after_30_seconds(self):
        r = self.page.evaluate('''() => {
          const {tr,cars}=fixture(); tick(tr,31);
          const before=cars.every(c=>c.active); tick(tr,1); tick(tr,40);
          return {before,active:cars.map(c=>c.active),n:tr.cyclesBroken,events:tr.game.trafficCycles};
        }''')
        self.assertTrue(r['before'])
        self.assertEqual(r['active'], [False, True, True])
        self.assertEqual(r['n'], 1)
        self.assertEqual(r['events'][0]['cycle'], 'tram1>car307>car295>car297')

    def test_open_or_moving_chains_do_not_recover(self):
        r = self.page.evaluate('''() => ['red','dwell','moving car','moving tram','inactive','other tram'].map(kind=>{
          const {tr,t,cars}=fixture();
          if(kind==='red') {t.waitFor=null; t.stop.why='signal';}
          if(kind==='dwell') t.dwell=10;
          if(kind==='moving car') cars[1].vNow=1;
          if(kind==='moving tram') t.v=1;
          if(kind==='inactive') cars[1].active=false;
          if(kind==='other tram') cars[2].waitFor={id:2,v:0};
          tick(tr,100); return tr.cyclesBroken||0;
        })''')
        self.assertEqual(r, [0]*6)

    def test_two_trams_in_one_cycle_recover_only_one_car(self):
        r = self.page.evaluate('''() => {
          const {tr,t,cars}=fixture();
          const ahead={id:2,s:90,v:0,dwell:0,stop:{s:90,why:'car on track'},waitFor:cars[2]};
          tr.ahead=[ahead]; cars[0].waitFor=ahead;
          tick(tr,100);
          return {removed:cars.filter(c=>!c.active).length,n:tr.cyclesBroken,events:tr.game.trafficCycles.length};
        }''')
        self.assertEqual(r, {'removed':1, 'n':1, 'events':1})

    def test_movement_resets_the_wait_and_scene_names_the_cycle(self):
        r = self.page.evaluate('''async () => {
          const {tr,t,cars}=fixture(); tick(tr,25); cars[1].vNow=1; tick(tr,1);
          cars[1].vNow=0; tick(tr,25);
          const {stuckScene}=await import('/tools/bench/stuck.js');
          const g={tram:{s:80,v:0},stops:[],signals:[{s:110,cross:112}],route:{at:()=>({x:0,y:0})}};
          tr.cars.forEach(c=>{c.path={at:()=>({x:10,y:0})}; c.s=0;});
          const scene=stuckScene(g,tr,{step:()=>({})});
          return {n:tr.cyclesBroken||0,waits:scene.aiTrams[0].waits,cars:scene.junction.cars.length};
        }''')
        self.assertEqual(r['n'], 0)
        self.assertEqual([w['id'] for w in r['waits']], ['oncoming1','car307','car295','car297'])
        self.assertEqual(r['waits'][-1]['for'], 'oncoming1')
        self.assertEqual(r['waits'][0]['why'], 'car on track')
        self.assertEqual(r['cars'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
