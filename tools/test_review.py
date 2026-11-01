"""Smoke test of review mode (?review, src/review.js) on a phone-sized page with touch:
python -P -E tools/test_review.py [--line 17]
(tools/serve.py's handler on a free port, its review answers in a temp folder; the findings file is
served by the test, not written). An answer with a note goes to the server and comes back after a
reload with the browser's storage cleared (#136)."""
import argparse
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402

FILE = {"options": ["right", "wrong"],
        "checks": {"demo": {"places": [{"x": 0.0, "y": 0.0, "kind": "here", "mag": 5, "info": "the city origin"},
                                       {"x": 30.0, "y": 0.0, "kind": "here", "mag": 4, "info": "30 m east"}]}}}
HEIGHT = {'findings':[{'kind':'trackheight','id':'bridge-test','x':0,'y':0,'mag':10,'status':'review',
    'info':'test bridge','decision':{'span_ids':['span-test'],'structure':{'kind':'bridge'}},
    'spans':[{'id':'span-test','line':17,'direction':'path','length_m':10,'start_s':0,
              'structure':{'kind':'bridge'},'status':'review','proposal':{'rule':'independent_height_required'},
              'profile':[{'s':0,'xy':[0,0],'archive':[{'z':200}],'surfaces':[],'ipr_terrain_z':199,'di_z':200},
                         {'s':10,'xy':[10,0],'archive':[{'z':201}],'surfaces':[],'ipr_terrain_z':200,'di_z':201}]}]}]}


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    tmp = tempfile.mkdtemp()
    serve.REVIEWS = tmp
    server = serve.Server(('127.0.0.1', 0), lambda *a, **k: Quiet(*a, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails, saved = [], os.path.join(tmp, f"line{args.line}.json")

    def answers(route):
        p = os.path.join(tmp, route.request.url.rsplit("/", 1)[-1].split("?")[0])
        if os.path.exists(p):
            route.fulfill(status=200, content_type="application/json", body=open(p, encoding="utf-8").read())
        else:
            route.fulfill(status=404, body="")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            page = ctx.new_page()
            page.route("**/test-findings.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(FILE)))
            page.route("**/reports/reviews/*.json", answers)
            t0 = time.time()
            url = f"http://127.0.0.1:{server.server_port}/?line={args.line}&review=test-findings.json"
            page.goto(url, timeout=180000)
            page.wait_for_function("window.review", timeout=180000)
            r = page.evaluate("""async () => {
              const R = window.review;
              await R.ready;
              const by = {};
              for (const f of R.findings) by[f.src] = (by[f.src] || 0) + 1;
              R.$('rvFilter').value = 'file|';
              R._fill();
              const i = R.list.findIndex((f) => f.info === 'the city origin');
              R.select(i);
              const f = R.list[i], L = R.links(f.x, f.y);
              const t = R.camera.position.clone(), dir = new t.constructor();
              R.camera.getWorldDirection(dir);
              // where the camera looks at the finding's height: within 30 m of it
              const k = (f.z - t.y) / dir.y, gx = t.x + dir.x * k, gy = -(t.z + dir.z * k);
              const links = [...document.querySelectorAll('#rvCard a')].map((a) => a.href);
              const panel = document.querySelector('#review').getBoundingClientRect();
              const buttons = [...document.querySelectorAll('#rvCard button[data-v]')].map((b) => b.textContent);
              return { by, look: Math.hypot(gx - f.x, gy - f.y), lat: L.lat, lon: L.lon, links, buttons,
                       panel: { top: panel.top, height: panel.height, width: panel.width },
                       heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null };
            }""")
            r["loadS"] = round(time.time() - t0)
            # a click on the head of a neighbouring pin, close up (a pin is then ~100 px tall), selects it
            pin = page.evaluate("""() => {
              const R = window.review, r = R.canvas.getBoundingClientRect(), V = R.camera.position.constructor;
              R.T.x = 15; R.yaw = Math.PI / 2; R.pitch = 1.1; R.dist = 90; R._render(); R.camera.updateMatrixWorld();
              const i = R.list.findIndex((f) => f.info === '30 m east'), f = R.list[i];
              const v = new V(f.x, f.z + 6.8, -f.y).project(R.camera);
              return { i, x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
            }""")
            page.mouse.click(pin["x"], pin["y"])
            r["pinClick"] = page.evaluate("window.review.list[window.review.cur].info")
            page.evaluate("window.review.select(window.review.list.findIndex((f) => f.info === 'the city origin'))")
            # the answer as a reviewer gives it: a note, then the button
            page.fill("#rvNote", "kerb about 12 cm")
            page.click("#rvCard button[data-v='1']")
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length", timeout=20000)
            r["next"] = page.evaluate("window.review.list[window.review.cur].info")
            r["saved"] = json.load(open(saved, encoding="utf-8")) if os.path.exists(saved) else None
            # another device: no local storage, the answer comes from the server
            page.evaluate("localStorage.clear()")
            page.goto(url, timeout=180000)
            page.wait_for_function("window.review", timeout=180000)
            r["back"] = page.evaluate("""async () => {
              const R = window.review;
              await R.ready;
              await new Promise((ok) => { const t = setInterval(() => { if (R.verdicts.state !== 'loading') { clearInterval(t); ok(); } }, 100); });
              const rec = Object.values(R.verdicts.items).find((v) => v.info === 'the city origin');
              R.$('rvFilter').value = 'file|';
              R._fill();
              return { rec, count: R.$('rvCount').textContent };
            }""")
            page.route('**/height-findings.json',lambda q:q.fulfill(status=200,content_type='application/json',body=json.dumps(HEIGHT)))
            page.goto(f'http://127.0.0.1:{server.server_port}/?line={args.line}&review=height-findings.json',timeout=180000)
            page.wait_for_function('window.review',timeout=180000)
            r['height'] = page.evaluate('''async () => {
              const R=window.review; await R.ready;
              R.$('rvFilter').value='file|'; R._fill();
              const i=R.list.findIndex(f=>f.kind==='trackheight'); R.select(i);
              const svg=document.querySelector('#heightProfile');
              const button=[...document.querySelectorAll('#rvCard button[data-v]')].map(b=>b.textContent);
              if (svg) svg.dispatchEvent(new PointerEvent('pointermove',{clientX:svg.getBoundingClientRect().left+80}));
              return {count:R.list.filter(f=>f.kind==='trackheight').length, svg:!!svg, marker:!!R.heightMarker?.visible, button};
            }''')
            page.click("#rvCard button[data-v='0']")
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length",timeout=20000)
            r['heightSaved'] = json.load(open(saved,encoding='utf-8'))
            browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(r, ensure_ascii=False)[:1500])
    if not r["by"].get("file"):
        fails.append("no findings from the file")
    if not r["by"].get("seams"):
        fails.append("no seam findings from the survey")
    if r["look"] > 30:
        fails.append(f"camera looks {r['look']:.0f} m from the finding")
    la, lo = f"{r['lat']:.6f}", f"{r['lon']:.6f}"
    if len(r["links"]) < 4 or not all(la in h and lo in h for h in r["links"]):
        fails.append("the imagery links do not carry the finding's lat/lon")
    if not (math.isclose(r["panel"]["width"], 390, abs_tol=1) and r["panel"]["top"] > 844 / 3):
        fails.append(f"the panel is not a bottom sheet on a phone: {r['panel']}")
    if r["pinClick"] != "30 m east":
        fails.append(f"a click on a pin's head selected {r['pinClick']!r}")
    if [b.split(" · ", 1)[-1] for b in r["buttons"]] != FILE["options"]:
        fails.append(f"answer buttons {r['buttons']}, not the file's options")
    items = list((r["saved"] or {}).get("items", {}).values())
    if not any(v.get("v") == "wrong" and v.get("note") == "kerb about 12 cm" for v in items):
        fails.append(f"the answer did not reach the server: {r['saved']}")
    if r["next"] != "30 m east":
        fails.append(f"after the answer the card shows {r['next']!r}, not the next finding without one")
    if (r["back"]["rec"] or {}).get("v") != "wrong" or not r["back"]["count"].startswith("1 / 2"):
        fails.append(f"after a reload without local storage: {r['back']}")
    if r['height']['count'] != 1 or not r['height']['svg'] or not r['height']['marker']:
        fails.append(f"track height finding/profile/hover missing: {r['height']}")
    if not any(v.get('decision_id')=='bridge-test' and v.get('span_ids')==['span-test'] and v.get('v')=='archive profile ok'
               for v in r['heightSaved'].get('items',{}).values()):
        fails.append('track-height answer was not saved with its decision scope')
    if fails:
        sys.exit("; ".join(fails))
    print("review mode: findings, camera, links, bottom sheet, a click on a pin; an answer saved, the next finding, read back: pass")


if __name__ == "__main__":
    main()
