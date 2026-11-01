"""Profile rendering: python -P -E tools/test_track_height_profile.py (free-port server)."""
from pathlib import Path
import sys
import unittest
from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent))
from headless import serve,stop_server


class HeightProfile(unittest.TestCase):
    def test_sources_directions_and_single_sample(self):
        server,url=serve(0)
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                page=browser.new_page()
                page.goto(url+'/tools/bench/batch.html')
                result=page.evaluate('''async () => {
                  const {heightProfile}=await import('/src/trackHeightProfile.js');
                  const point=(s,z)=>({s,xy:[s,0],archive:[{z}],surfaces:[{class:'road',level:0,z:z+1,rail_height_eligible:true}],di_z:z,ipr_terrain_z:z-2});
                  const span={line:17,direction:'path',length_m:10,start_s:0,structure:{kind:'bridge',tags:{a:{layer:'1'}}},
                    structure_extent:[0,10],profile:[point(0,200),point(10,201)],proposal:{rule:'linear_di_portals',ends:[200,201]}};
                  const back={...span,direction:'pathBack',profile:[point(0,202),point(10,203)]};
                  const route={nearest(x,y){return {s:x,d:0}}}, profile={height(s){return 200+s/10}};
                  const a=heightProfile({spans:[span,back]},route,profile);
                  const b=heightProfile({spans:[{...span,profile:[point(0,200)]}]},route,profile);
                  return {svg:a.html.includes('heightProfile'),di:a.html.includes('DI 200.00'),
                    surface:a.html.includes('road level 0'),conflict:a.html.includes('Directions differ'),
                    proposal:a.html.includes('#ff9e31'), layer:a.html.includes('layer 1'),single:!!b};
                }''')
                self.assertTrue(all(result.values()),result)
                browser.close()
        finally:
            stop_server(server)


if __name__=='__main__':
    unittest.main(verbosity=2)
