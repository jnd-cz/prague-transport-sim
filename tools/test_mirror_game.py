"""Real mirror integration and viewport screenshots (#79).

    python -P -E tools/test_mirror_game.py --line 17

Own free-port server; no FPS claims from headless rendering. Captures 1280x720, 3840x2160 and
390x844, checks the same camera direction/FOV, texture resize, cached idle picture and disable paths.
"""
import argparse
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0,str(Path(__file__).resolve().parent))
from atomic import replacing
from shot import site

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--line',type=int,default=17)
    ap.add_argument('--out',type=Path,default=ROOT/'reports/shots/mirror79')
    a = ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    results = {'views':[]}
    with site(ROOT) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=1)
            errors = []
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.add_init_script('window.headless = true')
            page.goto(f'{url}/?line={a.line}&seed=79',timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')",timeout=180000)
            page.select_option('#optTemp','autumn')
            page.select_option('#selTrip',index=0)
            page.click('#btnStart')
            page.wait_for_function('window.game && window.mirror',timeout=60000)
            page.evaluate('''() => {
              game.tram.s = Math.min(5064,game.route.length); game.tram.v=0; game.tram.a=0; game.paused=true;
              traffic.dispose(); traffic.update=()=>{}; window.headless=false;
            }''')
            page.add_style_tag(content='#pausePanel,#msgs {display:none !important}')
            for width,height in ((1280,720),(3840,2160),(390,844)):
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate('phone => document.body.classList.toggle("touch",phone)',width==390)
                page.wait_for_function('''() => {
                  const b=document.getElementById('mirror').getBoundingClientRect();
                  return mirror.stats.updates>0 && mirror.target.height===Math.round(Math.max(120,Math.min(640,(b.height-12)*renderer.getPixelRatio())));
                }''',timeout=30000)
                row = page.evaluate('''() => {
                  const m=mirror,c=m.camera,b=document.getElementById('mirror').getBoundingClientRect();
                  return {viewport:[innerWidth,innerHeight],frame:[b.width,b.height],target:[m.target.width,m.target.height],
                          fov:c.fov,aspect:c.aspect,far:c.far,rotation:c.rotation.toArray(),stats:{...m.stats},
                          excluded:m.hidden.map(o=>({part:o.userData.part,flat:!!o.userData.mirrorDetail,type:o.type,visible:o.visible}))};
                }''')
                assert row['far']==300 and row['fov']==30
                assert abs(row['aspect']-150/190)<1e-10
                assert abs(row['target'][0]-row['target'][1]*150/190)<=1
                assert row['target'][1]<=640
                if results['views']:
                    assert row['rotation']==results['views'][0]['rotation']
                assert all(o['flat'] or o['part']=='catenary' and o['type']=='LineSegments' for o in row['excluded'])
                results['views'].append(row)
                page.screenshot(path=str(a.out/f'line{a.line}-{width}x{height}.png'))
            idle = page.evaluate('''() => ({...mirror.stats})''')
            page.wait_for_timeout(1500)
            after = page.evaluate('''() => ({...mirror.stats})''')
            assert after['updates']==idle['updates'], (idle,after)
            assert after['presents']>idle['presents'], (idle,after)
            results['idle'] = {'before':idle,'after':after}
            for mode,key in (('off','z'),('chase','v'),('headless',None)):
                page.evaluate('window.headless=true; game.paused=false')
                if key:
                    page.keyboard.press(key)
                    page.evaluate('game.paused=true; window.headless=false')
                before = page.evaluate('mirror.stats.presents')
                page.wait_for_timeout(750)
                assert page.evaluate('mirror.stats.presents')==before, mode
                results[mode] = True
                if key:
                    page.evaluate('window.headless=true; game.paused=false')
                    page.keyboard.press(key)
                    page.evaluate('game.paused=true; window.headless=false')
            assert not errors,errors
            results['page_errors'] = errors
        finally:
            browser.close()
    with replacing(a.out/'results.json','w',encoding='utf-8') as f:
        json.dump(results,f,indent=2)
    print(json.dumps(results,indent=2))
    print('mirror integration: viewport, camera, cached idle picture, off/chase/headless: pass')


if __name__=='__main__':
    main()
