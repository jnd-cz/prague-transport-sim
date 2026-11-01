"""Measure the real mirror on a focused browser page (#79).

    python -P -E tools/mirror_bench.py --line 17 --s 5064 --headed --output reports/mirror-before.json

Own free-port server. --headed uses the machine's normal graphics backend; without it the browser is
headless. The JSON records the GPU and focus/visibility; FPS from an unfocused page is rejected.
"""
import argparse
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
from shot import site

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--line', type=int, default=17)
    ap.add_argument('--s', type=float, default=5064)
    ap.add_argument('--seconds', type=float, default=10)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--headed', action='store_true')
    ap.add_argument('--output', type=Path, default=ROOT/'reports/mirror-bench.json')
    a = ap.parse_args()
    if a.seconds <= 0 or a.rounds < 1:
        ap.error('seconds and rounds must be positive')
    with site(ROOT) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        try:
            page = browser.new_page(viewport={'width':1280,'height':720}, device_scale_factor=1)
            page.add_init_script('window.headless = true')
            page.goto(f'{url}/?line={a.line}&seed=79', timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.select_option('#selTrip', index=0)
            page.select_option('#optTemp', 'autumn')
            page.select_option('#optWeather', 'dry')
            page.select_option('#optObst', 'off')
            page.click('#btnStart')
            page.wait_for_function('window.game', timeout=60000)
            page.bring_to_front()
            page.evaluate('''args => {
              window._mirrorBench = {done:false};
              import('/tools/bench/mirror.js').then(m => m.run(args)).then(
                value => {window._mirrorBench = {done:true,value}},
                e => {window._mirrorBench = {done:true,error:String(e)}});
            }''', {'s':a.s,'seconds':a.seconds,'rounds':a.rounds})
            page.wait_for_function('window._mirrorBench.done', timeout=(a.seconds*a.rounds*2+60)*1000, polling=500)
            result = page.evaluate('window._mirrorBench')
            if result.get('error'):
                raise RuntimeError(result['error'])
            report = result['value']
            a.output.parent.mkdir(parents=True, exist_ok=True)
            with replacing(a.output, 'w', encoding='utf-8') as f:
                json.dump(report,f,indent=2)
            print(json.dumps(report,indent=2), flush=True)
            if not report['foreground']:
                raise SystemExit('Page lost focus or visibility; frame rates are not a foreground measurement')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
