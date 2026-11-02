"""Rendered crossing check and triangle filtering: python -P -E tools/test_crossing_check.py."""
from pathlib import Path
import re
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent))
from headless import serve,stop_server

ROOT=Path(__file__).resolve().parent.parent


class CrossingCheck(unittest.TestCase):
    def test_filtered_check_matches_drawn_pedestrian_geometry(self):
        server,url=serve(0)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                html=(ROOT/'index.html').read_text(encoding='utf-8')
                importmap=re.search(r'<script type="importmap">.*?</script>',html,re.S)[0]
                page.route('**/crossing-check-test*',lambda route:route.fulfill(body=importmap))
                page.goto(url+'/crossing-check-test?keepgeo')
                result=page.evaluate('''async () => {
                  const THREE=await import('three');
                  const {run}=await import('/tools/bench/crossingSlab.js');
                  const material=new THREE.MeshBasicMaterial({side:THREE.DoubleSide});
                  const quad=(x0,x1,y0,y1,z)=>[x0,z,-y0, x1,z,-y0, x1,z,-y1,
                                                x0,z,-y0, x1,z,-y1, x0,z,-y1];
                  const mesh=(p,surface,extra={})=>{
                    const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(p,3));
                    const m=new THREE.Mesh(g,material);m.userData={surface,...extra};return m;
                  };
                  const rails=mesh([...quad(0,20,-0.77,-0.67,200.012),...quad(0,20,0.67,0.77,200.012)],'rail');
                  const surface=mesh([...quad(9,11,-2,2,200.1),...quad(0,20,-4,4,200.2)],'dtm',
                    {surfaceRanges:[[0,2,'sidewalk',0,0],[2,4,'road',0,1]]});
                  const world=new THREE.Group();world.add(rails,surface);world.updateMatrixWorld(true);
                  const route={length:20,ground:{profile:{height:()=>200,onBridge:()=>false}},
                    nearest:(x,y)=>x>=0&&x<=20?{s:x,d:Math.abs(y)}:null,offset:(s,l)=>({x:s,y:l})};
                  window.game={route,data:{roads:[]}};window.world=world;
                  const a=run().checks.crossingSlab,b=run({unfiltered:true}).checks.crossingSlab;
                  return {a,b};
                }''')
                self.assertEqual(result['a']['count'],1)
                self.assertEqual(result['a']['missing'],0)
                self.assertAlmostEqual(result['a']['places'][0]['mag'],0.088,places=3)
                self.assertEqual(result['a'],result['b'])
                browser.close()
        finally:
            stop_server(server)


if __name__=='__main__':
    unittest.main(verbosity=2)
