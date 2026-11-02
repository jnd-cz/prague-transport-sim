"""Rendered crossing check and triangle filtering: python -P -E tools/test_crossing_check.py."""
from pathlib import Path
import re
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent))
from headless import serve,stop_server,judge

ROOT=Path(__file__).resolve().parent.parent


class CrossingCheck(unittest.TestCase):
    def test_vertical_lip_between_surface_samples_is_detected(self):
        server,url=serve(0)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                html=(ROOT/'index.html').read_text(encoding='utf-8')
                importmap=re.search(r'<script type="importmap">.*?</script>',html,re.S)[0]
                page.route('**/crossing-edge-test',lambda route:route.fulfill(body=importmap))
                page.goto(url+'/crossing-edge-test')
                result=page.evaluate('''async () => {
                  const {crossingEdgeHits}=await import('/tools/bench/crossingSlab.js');
                  const area={c:'sidewalk',l:0,ring:[[9.1,-2,200.05],[9.2,-2,200.05],[9.2,2,200.05],[9.1,2,200.05]],holes:[],kerbs:[[0,1,0,1]]};
                  const game={route:{ground:{dtm:{areas:[area]},pedestrianCrossings:{survey:[{area:0}]}}}};
                  const heads=[8,10].flatMap(s=>[-1,1].map(side=>({s,side,x:s,y:side*.72,z:200.012})));
                  const before=crossingEdgeHits(game,heads);
                  for(const p of area.ring)p[2]=200.008-.05;
                  return {before,after:crossingEdgeHits(game,heads)};
                }''')
                self.assertEqual(result['before']['samples'],4)
                self.assertEqual(len(result['before']['hits']),4)
                self.assertGreater(result['before']['hits'][0]['excess'],.08)
                self.assertEqual(result['after']['hits'],[])
                browser.close()
        finally:
            stop_server(server)

    def test_unresolved_crossings_fail_the_command(self):
        self.assertFalse(judge('crossing',{'checks':{'crossingSlab':{'count':1,'of':10}}})[0])
        self.assertFalse(judge('crossing',{'checks':{'crossingSlab':{'count':0,'of':0}}})[0])
        self.assertFalse(judge('crossing',{'checks':{'crossingSlab':{'count':0,'of':10,'unreviewedCandidates':1}}})[0])
        self.assertTrue(judge('crossing',{'checks':{'crossingSlab':{'count':0,'rawCount':4,'of':10}}})[0])

    def test_reasons_separate_transverse_crossings_from_side_surfaces(self):
        server,url=serve(0)
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(headless=True)
                page=browser.new_page()
                html=(ROOT/'index.html').read_text(encoding='utf-8')
                importmap=re.search(r'<script type="importmap">.*?</script>',html,re.S)[0]
                page.route('**/crossing-reason-test',lambda route:route.fulfill(body=importmap))
                page.goto(url+'/crossing-reason-test')
                reasons=page.evaluate('''async () => {
                  const {crossingReason,recordedReason}=await import('/tools/bench/crossingSlab.js');
                  const reviews={lines:{9:{files:{'line9.json':'a'},reasons:{parallel:{roads:[3]}}}}};
                  const manifest={files:{'line9.json':{sha256:'a'}}};
                  if(recordedReason(9,'roads',3,'parallel',reviews,manifest)!=='parallel')throw new Error('review lost');
                  for(const [line,id,reason] of [[9,4,'parallel'],[17,3,'parallel'],[9,3,'crossing']])
                    if(recordedReason(line,'roads',id,reason,reviews,manifest))throw new Error('unreviewed source accepted');
                  manifest.files['line9.json'].sha256='b';
                  if(recordedReason(9,'roads',3,'parallel',reviews,manifest))throw new Error('stale review accepted');
                  const rect=(x0,x1,y0,y1)=>({ring:[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],holes:[]});
                  const game={route:{at:()=>({x:0,y:0,hx:1,hy:0}),ground:{dtm:{areas:[
                    rect(-2,2,-4,4),rect(-20,20,-1,1),rect(-2,2,.5,2)]}}},
                    data:{roads:[{p:[[-10,1],[10,1]]},{p:[[0,-5],[0,5]]}]}};
                  const hit={s:0,x:0,y:.72};
                  return [0,1,2].map(id=>crossingReason(game,hit,[0,0,'sidewalk',0,id],null))
                    .concat([0,1].map(id=>crossingReason(game,hit,null,id)));
                }''')
                self.assertEqual(reasons,[None,'survey-surface-runs-along-track','survey-edge-does-not-cross-gauge',
                                          'mapped-footway-runs-along-track',None])
                browser.close()
        finally:
            stop_server(server)

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
                  const a=(await run()).checks.crossingSlab,b=(await run({unfiltered:true})).checks.crossingSlab;
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
