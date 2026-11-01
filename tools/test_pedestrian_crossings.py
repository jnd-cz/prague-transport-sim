"""Crossing geometry and grade separation: python -P -E tools/test_pedestrian_crossings.py."""
from pathlib import Path
import json
import re
import sys
import unittest

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent))
from headless import serve,stop_server


class PedestrianCrossings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server,cls.url = serve(0)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True)
        cls.page = cls.browser.new_page()
        html=(Path(__file__).resolve().parent.parent/'index.html').read_text(encoding='utf-8')
        importmap=re.search(r'<script type="importmap">.*?</script>',html,re.S)[0]
        cls.page.route('**/pedestrian-crossing-test',lambda route:route.fulfill(body=importmap+'<title>crossing test</title>'))
        cls.page.goto(cls.url+'/pedestrian-crossing-test')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        stop_server(cls.server)

    def test_short_crossing_is_lowered_and_its_index_rebuilt(self):
        result = self.page.evaluate('''async () => {
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          const p=[[-2,-4,200.05],[2,-4,200.05],[2,4,200.05],[-2,4,200.05]];
          const area={c:'sidewalk',l:0,ring:p,holes:[],mesh:[[p[0],p[1],p[2]],[p[0],p[2],p[3]]]};
          const dtm={areas:[area],reindexed:0,reindexGround(){this.reindexed++;},
            _split(p,q,r,ground,out,depth,max){
              const lengths=[Math.hypot(p[0]-q[0],p[1]-q[1]),Math.hypot(q[0]-r[0],q[1]-r[1]),Math.hypot(r[0]-p[0],r[1]-p[1])];
              const e=Math.max(...lengths); if(e<=max || depth>=16){out.push([p,q,r]);return;}
              if(lengths[1]===e)[p,q,r]=[q,r,p]; else if(lengths[2]===e)[p,q,r]=[r,p,q];
              const m=[(p[0]+q[0])/2,(p[1]+q[1])/2,(p[2]+q[2])/2];
              this._split(p,m,r,false,out,depth+1,max); this._split(m,q,r,false,out,depth+1,max);
            }};
          const t={smooth:[[-10,0],[0,0],[10,0]],z:[200,200,200]};
          const ground={dtm};
          const data={tracks:[t],roads:[{z:1,p:[[0,-5],[0,5]]}]};
          const crossing=preparePedestrianCrossings(data,null,ground,()=>[0,0,0],()=>0.05);
          const firstTriangles=area.mesh.length;
          preparePedestrianCrossings(data,null,ground,()=>[0,0,0],()=>0.05);
          const vertices=area.mesh.flat();
          const near=vertices.filter(p=>Math.abs(p[0])<1 && Math.abs(p[1])<1);
          const foot=crossing.footway([[0,-5],[0,5]],2,()=>200,0.16);
          return {areas:ground.pedestrianCrossings.survey.length,reindexed:dtm.reindexed,triangles:area.mesh.length,firstTriangles,
                  near:near.map(p=>p[2]),foot:foot && foot(0,0.72)+0.16,
                  parallel:crossing.footway([[-5,1],[5,1]],2,()=>200,0.16),
                  overpass:crossing.footway([[0,-5],[0,5]],2,()=>210,0.16)};
        }''')
        self.assertEqual(result['areas'],1)
        self.assertEqual(result['reindexed'],1)
        self.assertEqual(result['triangles'],result['firstTriangles'])
        self.assertGreater(result['triangles'],2)
        self.assertTrue(result['near'])
        self.assertTrue(all(z <= 200.008-0.05+1e-6 for z in result['near']))
        self.assertLess(result['foot'],200.012)
        self.assertIsNone(result['parallel'])
        self.assertIsNone(result['overpass'])

    def test_parallel_sidewalk_does_not_become_a_crossing(self):
        result=self.page.evaluate('''async () => {
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          return [5,50].map(length => {
            const p=[[-length,-1,200], [length,-1,200], [length,1,200], [-length,1,200]];
            const a={c:'sidewalk',l:0,ring:p,holes:[],mesh:[[p[0],p[1],p[2]],[p[0],p[2],p[3]]]};
            const dtm={areas:[a],reindexGround(){throw new Error('parallel sidewalk changed');}};
            const t={smooth:[[-60,0],[0,0],[60,0]],z:[200,200,200]}, ground={dtm};
            preparePedestrianCrossings({tracks:[t]},null,ground,()=>[0,0,0],()=>0.05);
            return ground.pedestrianCrossings.survey.length;
          });
        }''')
        self.assertEqual(result,[0,0])

    def test_unmatched_survey_patch_is_held_for_review(self):
        result=self.page.evaluate('''async () => {
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          const p=[[-2,-4,200.05],[2,-4,200.05],[2,4,200.05],[-2,4,200.05]];
          const a={c:'sidewalk',l:0,ring:p,holes:[],mesh:[[p[0],p[1],p[2]],[p[0],p[2],p[3]]]};
          const dtm={areas:[a],reindexGround(){throw new Error('unmatched patch changed');}};
          const t={smooth:[[-10,0],[0,0],[10,0]],z:[200,200,200]}, ground={dtm};
          preparePedestrianCrossings({tracks:[t],roads:[{f:1,p:[[-5,1],[5,1]]}]},null,ground,()=>[0,0,0],()=>0.05);
          return {survey:ground.pedestrianCrossings.survey.length,review:ground.pedestrianCrossings.review.length,z:p[0][2]};
        }''')
        self.assertEqual(result['survey'],0)
        self.assertGreater(result['review'],0)
        self.assertEqual(result['z'],200.05)

    def test_crossing_follows_both_heights_on_canted_track(self):
        result=self.page.evaluate('''async () => {
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          const t={smooth:[[-10,0],[0,0],[10,0]],z:[200,200,200]}, ground={dtm:null};
          const crossing=preparePedestrianCrossings({tracks:[t]},null,ground,()=>[0.048,0.048,0.048],()=>0.05);
          const height=crossing.footway([[0,-5],[0,5]],2,()=>200,0.16);
          return [height(0,-0.72)+0.16,height(0,0.72)+0.16];
        }''')
        self.assertAlmostEqual(result[0],199.960,places=6)
        self.assertAlmostEqual(result[1],200.056,places=6)

    def test_survey_lookup_matches_the_refined_drawn_surface(self):
        result=self.page.evaluate('''async () => {
          const THREE=await import('three');
          const {DtmSurface,DTM_LIFT}=await import('/src/terrain.js');
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          const dtm=new DtmSurface({areas:[{c:'sidewalk',l:0,r:[[-2,-4,200.05],[2,-4,200.05],[2,4,200.05],[-2,4,200.05]]}]},
                                   {height:()=>200},THREE);
          const before=dtm.surfaceAt(0,0.72).z+DTM_LIFT.sidewalk;
          const track={smooth:[[-10,0],[0,0],[10,0]],z:[200,200,200]}, ground={dtm};
          preparePedestrianCrossings({tracks:[track],roads:[{z:1,p:[[0,-5],[0,5]]}]},null,ground,()=>[0,0,0],kind=>DTM_LIFT[kind] ?? 0.03);
          return {before,after:dtm.surfaceAt(0,0.72).z+DTM_LIFT.sidewalk,
                  areas:ground.pedestrianCrossings.survey.length};
        }''')
        self.assertEqual(result['areas'],1)
        self.assertGreater(result['before'],200.012)
        self.assertLess(result['after'],200.012)

    def test_reported_survey_polygon_matches_the_mapped_pedestrian_crossing(self):
        root=Path(__file__).resolve().parent.parent
        if not (root/'data/line17.dtm.json').exists():
            self.skipTest('fetch the pinned data snapshot for this source regression')
        from shapely.geometry import LineString,Point,Polygon
        from shapely.ops import triangulate

        data=json.loads((root/'data/line17.json').read_text(encoding='utf-8'))
        survey=json.loads((root/'data/line17.dtm.json').read_text(encoding='utf-8'))
        point=Point(-1584.3,-9165.2)
        candidates=[]
        for area in survey['areas']:
            if area['c']!='sidewalk' or area['l']!=0: continue
            poly=Polygon([p[:2] for p in area['r']],[[p[:2] for p in h] for h in area.get('h',[])])
            if poly.is_valid and poly.covers(point): candidates.append((poly.area,area,poly))
        self.assertTrue(candidates)
        _,area,poly=min(candidates,key=lambda x:x[0])
        tracks=[]
        for t in data['tracks']:
            if len(t['p'])<2: continue
            line=LineString([p[:2] for p in t['p']])
            if 1 < line.intersection(poly).length < 20:
                tracks.append({'smooth':[p[:2] for p in t['p']], 'z':[212.3]*len(t['p'])})
        self.assertGreaterEqual(len(tracks),2)
        zebras=[r for r in data['roads'] if r.get('z') and len(r['p'])>1 and LineString([p[:2] for p in r['p']]).distance(poly)<5]
        self.assertTrue(zebras)
        ring=[[p[0],p[1],212.3] for p in area['r']]
        mesh=[[[x,y,212.3] for x,y in list(t.exterior.coords)[:3]] for t in triangulate(poly) if poly.covers(t)]
        result=self.page.evaluate('''async ({ring,mesh,tracks,roads}) => {
          const {preparePedestrianCrossings}=await import('/src/pedestrianCrossings.js');
          const a={c:'sidewalk',l:0,ring,holes:[],mesh};
          const dtm={areas:[a],_split(p,q,r,g,out){out.push([p,q,r]);},reindexGround(){}};
          const ground={dtm};
          preparePedestrianCrossings({tracks,roads},null,ground,t=>t.z.map(()=>0),()=>0.05);
          return ground.pedestrianCrossings.survey;
        }''',{'ring':ring,'mesh':mesh,'tracks':tracks,'roads':zebras})
        self.assertEqual(len(result),1)
        self.assertTrue(any(5 < p['width'] < 8 for p in result[0]['sites']))


if __name__=='__main__':
    unittest.main(verbosity=2)
