"""Smoke test of review mode (?review, src/review.js) on a phone-sized page with touch:
python -P -E tools/test_review.py [--line 17]
(tools/serve.py's handler on a free port, its review answers in a temp folder; the findings file is
served by the test, not written). An answer with a note goes to the server and comes back after a
reload with the browser's storage cleared (#136)."""
import argparse
import faulthandler
import hashlib
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import zlib

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402

FILE = {"options": ["right", "wrong"],
        "checks": {"demo": {"places": [{"x": 0.0, "y": 0.0, "kind": "here", "mag": 5, "info": "the city origin"},
                                       {"x": 30.0, "y": 0.0, "kind": "here", "mag": 4, "info": "30 m east"}]}}}
HEIGHT = {'findings':[{'kind':'trackheight','id':'bridge-test','x':0,'y':0,'mag':10,'status':'review',
    'info':'test bridge','decision':{'span_ids':['span-test'],'structure':{'kind':'bridge'}},
    'options':['archive profile ok','follows survey surface','other level (deck / under)','unsure'],
    'answer_explanations':{'archive profile ok':'structure level is not identified',
                           'follows survey surface':None},
    'answer_previews':{'follows survey surface':{'span-test':[[0,200.5],[10,201.5]]}},
    'spans':[{'id':'span-test','line':17,'direction':'path','length_m':10,'start_s':0,
              'structure':{'kind':'bridge'},'status':'review','review_flags':['known_archive_disagreement'],'proposal':{'rule':'independent_height_required'},
              'profile':[{'s':0,'xy':[0,0],'archive':[{'z':200}],'surfaces':[],'ipr_terrain_z':199,'di_z':200},
                         {'s':10,'xy':[10,0],'archive':[{'z':201}],'surfaces':[],'ipr_terrain_z':200,'di_z':201}]}]}]}
# Two independent decisions may occupy the same coordinates.
HEIGHT['findings'].append({**HEIGHT['findings'][0], 'id':'other-bridge',
                           'decision':{'span_ids':['other-span'],'structure':{'kind':'bridge'}}})
HEIGHT_QUEUE = {'snapshot':'test','spans':[HEIGHT['findings'][0]['spans'][0],
                {**HEIGHT['findings'][0]['spans'][0], 'id':'other-span'}]}
HEIGHT_BYTES = json.dumps(HEIGHT_QUEUE).encode('utf-8')
HEIGHT_COMPACT = {'snapshot':'test','span_file':'test-spans.json',
                  'span_sha256':hashlib.sha256(HEIGHT_BYTES).hexdigest(),
                  'findings':[{k:v for k,v in f.items() if k!='spans'} for f in HEIGHT['findings']]}


def png(w, h, rgb):
    """A plain w×h PNG of one colour (the orthophoto as the mocked service sends it)."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    raw = b"".join(b"\0" + bytes(rgb) * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    faulthandler.dump_traceback_later(600, exit=True)
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
            # the orthophoto (#201), with IPR's service mocked: a 64 px image with the CORS header it sends,
            # then a service that refuses; and the track sources over it
            errors, ortho = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("https://gs-pub.praha.eu/**", lambda q: (ortho.append(q.request.url), q.fulfill(
                status=200, content_type="image/png", headers={"Access-Control-Allow-Origin": "*"}, body=png(64, 64, (200, 40, 40)))))
            r["ortho"] = page.evaluate("""async () => {
              const R = window.review, wait = async (f) => { for (let i = 0; i < 100 && !f(); i++) await new Promise((ok) => setTimeout(ok, 100)); return f(); };
              R.T.x = 12; R.T.y = -40; R._render();
              document.querySelector('#rvLayers [data-layer="ortho"]').click();
              const loaded = await wait(() => R.orthoMesh);
              const credit = R.credit.textContent, shown = getComputedStyle(R.credit).display !== 'none';
              const c = R.credit.getBoundingClientRect(), panel = R.box.getBoundingClientRect();
              document.querySelector('#rvLayers [data-layer="sources"]').click();
              const url = R.orthoUrl, first = R.orthoMesh, dist = R.dist;
              // close up: half the box at the native 0.05 m, a whole number of draped cells
              R.dist = 20; R._render();
              await wait(() => R.orthoMesh !== first);
              const p = R.orthoMesh.geometry.attributes.position.array, b = R.orthoUrl.match(/bbox=([^&]+)/)[1].split(',').map(Number);
              let nan = 0; for (let i = 1; i < p.length; i += 3) if (!Number.isFinite(p[i])) nan++;
              const near = { box: b[2] - b[0], nan, classes: R.layers.classes };
              R.dist = dist; R._render();
              return { loaded: !!loaded, w: first?.material.map.image.width, url, near, credit, shown,
                       overPanel: c.bottom > panel.top && c.right > panel.left,
                       sources: R.sourceLines?.geometry.attributes.position.count || 0, tracks: (R.data.tracks || []).length };
            }""")
            page.unroute("https://gs-pub.praha.eu/**")
            page.route("https://gs-pub.praha.eu/**", lambda q: q.abort("connectionrefused"))
            r["orthoDown"] = page.evaluate("""async () => {
              const R = window.review, b = document.querySelector('#rvLayers [data-layer="ortho"]');
              // (off, another cell, on: a new request, now refused; the same box again comes from the image cache)
              b.click(); R.T.x = 312; R._render(); b.click();
              for (let i = 0; i < 100 && !R.credit.classList.contains('err'); i++) await new Promise((ok) => setTimeout(ok, 100));
              const err = R.credit.classList.contains('err'), text = R.credit.textContent;
              R.select(0); // (the page goes on without it)
              b.click();
              return { err, text, cur: R.cur, hidden: getComputedStyle(R.credit).display === 'none' };
            }""")
            r["orthoErrors"] = errors[:3]
            page.unroute("https://gs-pub.praha.eu/**")
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
            page.route('**/height-findings.json',lambda q:q.fulfill(status=200,content_type='application/json',body=json.dumps(HEIGHT_COMPACT)))
            page.route('**/test-spans.json',lambda q:q.fulfill(status=200,content_type='application/json',body=HEIGHT_BYTES))
            with open(os.path.join(tmp, 'line22.json'), 'w', encoding='utf-8') as out:
                json.dump({'items': {'file|trackheight|other-bridge': {'v': 'unsure', 't': 1}}}, out)
            page.goto(f'http://127.0.0.1:{server.server_port}/?line={args.line}&review=height-findings.json',timeout=180000)
            page.wait_for_function('window.review',timeout=180000)
            page.wait_for_function('window.review.otherAnswersReady',timeout=30000)
            r['height'] = page.evaluate('''async () => {
              const R=window.review; await R.ready;
              R.$('rvFilter').value='file|'; R._fill();
              const across=R.$('rvCount').textContent;
              const i=R.list.findIndex(f=>f.kind==='trackheight'); R.select(i);
              const svg=document.querySelector('#heightProfile');
              const held=R.$('rvCard').querySelector('button[data-v="0"]'); held.dispatchEvent(new Event('mouseenter'));
              const heldText=R.$('rvPreview').textContent;
              const survey=R.$('rvCard').querySelector('button[data-v="1"]'); survey.focus();
              const preview=svg.querySelector('[data-preview="follows survey surface"]');
              const previewShown=preview?.style.display!== 'none' && preview?.querySelector('path')?.getAttribute('d').includes('L');
              survey.blur();
              R.otherAnswers={};
              const toggle=R.$('rvHeight').querySelector('[data-height-series="path"]');
              toggle.click(); const hidden=svg.querySelector('[data-series="path"]').style.display==='none'; toggle.click();
              const {heightProfile}=await import('/src/trackHeightProfile.js');
              const point=(s,z,id)=>({s,xy:[s,0],archive:[{id,z}],surfaces:[],ipr_terrain_z:199,di_z:null});
              const main={id:'a',line:17,direction:'path',length_m:10,start_s:0,structure:{kind:'unmapped'},profile:[point(0,200,'a'),point(10,201,'b')]};
              const other={...main,id:'b',direction:'pathBack',profile:[point(0,200,'a'),point(20,202,'b')]};
              const chart=heightProfile({spans:[main,other]}, {nearest:()=>null}, {height:()=>null});
              const dom=new DOMParser().parseFromString(chart.html,'text/html');
              const archive=dom.querySelector('[data-series="path"] path').getAttribute('d');
              const projected=dom.querySelector('[data-series="pathBack"] path').getAttribute('d');
              const gapPoint={...point(5,200,'missing'),archive:[]};
              const gap=heightProfile({spans:[{...main,profile:[point(0,200,'a'),gapPoint,point(10,201,'b')]}]}, {nearest:()=>null}, {height:()=>null});
              const gapPath=new DOMParser().parseFromString(gap.html,'text/html').querySelector('[data-series="path"] path').getAttribute('d');
              // (two records at other levels: the line stays on the continuing one, the other is a hollow dot)
              const both={...point(5,190,'dive'),archive:[{id:'dive',z:190},{id:'a',z:200.5}]};
              const overlap=new DOMParser().parseFromString(heightProfile({spans:[{...main,profile:[point(0,200,'a'),both,point(10,201,'a')]}]}, {nearest:()=>null}, {height:()=>null}).html,'text/html');
              const overlapPath=overlap.querySelector('[data-series="path"] path').getAttribute('d').match(/[ML][0-9.]+,[0-9.]+/g).map(c=>+c.split(',')[1]);
              const overlapDots=overlap.querySelectorAll('[data-series="path"] circle').length;
              const button=[...document.querySelectorAll('#rvCard button[data-v]')].map(b=>b.textContent);
              if (svg) svg.dispatchEvent(new PointerEvent('pointermove',{clientX:svg.getBoundingClientRect().left+80}));
              const marker=!!R.heightMarker?.visible, cursor=R.$('heightCursor');
              // a click on the chart centres the camera on that point (#182): the right end is the span's end, x 10
              const rr=svg.getBoundingClientRect(); svg.dispatchEvent(new MouseEvent('click',{clientX:rr.right-2,clientY:rr.top+20}));
              const clickTo=[R.T.x,R.T.y];
              if (cursor) cursor.setAttribute('visibility','hidden');
              const p=R.heightChart.points[0], v=R.camera.position.clone().set(p.xy[0],p.game ?? R.ground.at(...p.xy),-p.xy[1]).project(R.camera);
              const rect=R.canvas.getBoundingClientRect();
              R._hover(rect.left+(v.x+1)*rect.width/2,rect.top+(1-v.y)*rect.height/2);
              return {count:R.list.filter(f=>f.kind==='trackheight').length, svg:!!svg, marker,
                reverse:cursor?.getAttribute('visibility')==='visible',
                conflict:R.hl.children.some(o=>o.material?.color?.getHex()===0xff3333), button,
                explanation:R.$('rvCard').textContent, clickTo, hidden, archive, gapPath, projected, across, heldText, previewShown,
                overlapSpread:Math.max(...overlapPath)-Math.min(...overlapPath), overlapDots};
            }''')
            page.click("#rvCard button[data-v='0']")
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length",timeout=20000)
            r['heightNext'] = page.evaluate('window.review.list[window.review.cur].id')
            r['heightSaved'] = json.load(open(saved,encoding='utf-8'))
            # a 1080p desktop window: the tall track-height card scrolls, the list keeps its rows (#178)
            page.set_viewport_size({'width': 1920, 'height': 800})
            r['desk'] = page.evaluate('''() => {
              const R=window.review, card=R.$('rvCard'), list=R.$('rvList');
              R.select(R.list.findIndex(f=>f.kind==='trackheight'));
              const b=card.querySelector('button[data-v="1"]'); b.focus();
              const preview=card.querySelector('[data-preview="follows survey surface"]');
              return {list:list.clientHeight, card:card.clientHeight, cardFull:card.scrollHeight,
                cardScrolls:getComputedStyle(card).overflowY==='auto', bottom:R.box.getBoundingClientRect().bottom, vh:innerHeight,
                preview:preview?.style.display !== 'none'};
            }''')
            browser.close()
    finally:
        server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
        faulthandler.cancel_dump_traceback_later()
    print(json.dumps(r, ensure_ascii=False)[:1500])
    if not r["by"].get("file"):
        fails.append("no findings from the file")
    d = r["desk"]
    if d["list"] < 150 or d["bottom"] > d["vh"] + 1 or (d["cardFull"] > d["card"] and not d["cardScrolls"]):
        fails.append(f"desktop panel: the list or the card is cut off: {d}")
    if not d['preview']:
        fails.append('answer preview is missing on desktop')
    o, od = r["ortho"], r["orthoDown"]
    origin = (-742806.0, -1043024.0)  # (data/line17.json frame; the request's box is centred on the 50 m cell of x 12, y -40)
    want = f"bbox={origin[0] + 0 - 75:.1f},{origin[1] - 50 - 75:.1f},{origin[0] + 0 + 75:.1f},{origin[1] - 50 + 75:.1f}&bboxSR=5514"
    if not o["loaded"] or o["w"] != 64:
        fails.append(f"orthophoto layer: no image draped from the service: {o}")
    if args.line == "17" and want not in (o["url"] or ""):
        fails.append(f"orthophoto request is not the 150 m box around the target's cell: {o['url']} (wanted {want})")
    if o["near"]["box"] != 75 or o["near"]["nan"] or o["near"]["classes"]:
        fails.append(f"orthophoto close up: not a 75 m box at 0.05 m, heights missing, or the classes left over it: {o['near']}")
    if not o["shown"] or "IPR Praha (CC BY 4.0)" not in o["credit"] or o["overPanel"]:
        fails.append(f"orthophoto credit missing or under the panel: {o}")
    if not o["sources"] or not o["tracks"]:
        fails.append(f"track sources layer drew nothing: {o}")
    if not od["err"] or "not available" not in od["text"] or od["cur"] != 0 or not od["hidden"]:
        fails.append(f"orthophoto with the service refusing: {od}")
    if r["orthoErrors"]:
        fails.append(f"page errors with the orthophoto layer: {r['orthoErrors']}")
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
    if r['height']['count'] != 2 or not all(r['height'][k] for k in ('svg','marker','reverse','conflict')):
        fails.append(f"track height finding/profile/hover missing: {r['height']}")
    if r['height'].get('clickTo') != [10, 0]:
        fails.append(f"a click on the chart's end did not move the camera to it: {r['height'].get('clickTo')}")
    if not r['height']['hidden'] or r['height']['archive'].count('M') != 1 or 'L' not in r['height']['archive'] or r['height']['gapPath'].count('M') != 2:
        fails.append('archive record transition or legend toggle failed')
    if r['height']['overlapDots'] != 1 or r['height']['overlapSpread'] > 20:
        fails.append(f"overlapping archive levels: the line jumped or the other record is hidden: {r['height']['overlapSpread']}, {r['height']['overlapDots']} dots")
    if r['height']['projected'].count('L'):
        fails.append('an out-of-range point was clamped at the edge')
    if r['heightNext'] != 'other-bridge':
        fails.append(f"same-location decision was not independent: {r['heightNext']}")
    if ('structure level is not identified' not in r['height']['heldText'] or not r['height']['previewShown']):
        fails.append('held-answer reason or focused answer preview is missing')
    if '1 / 2 answered across lines' not in r['height']['across']:
        fails.append(f"cross-line answer count: {r['height']['across']}")
    if not any(v.get('decision_id')=='bridge-test' and v.get('span_ids')==['span-test'] and v.get('v')=='archive profile ok'
               and v.get('span_sha256')==HEIGHT_COMPACT['span_sha256']
               for v in r['heightSaved'].get('items',{}).values()):
        fails.append('track-height answer was not saved with its decision scope')
    if fails:
        sys.exit("; ".join(fails))
    print("review mode: findings, camera, links, bottom sheet, a click on a pin; an answer saved, the next finding, read back: pass")


if __name__ == "__main__":
    main()
