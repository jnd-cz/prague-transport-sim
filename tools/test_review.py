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
import review_sets  # noqa: E402
import serve  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

FILE = {"options": ["right", "wrong"],
        "checks": {"demo": {"places": [{"x": 0.0, "y": 0.0, "kind": "here", "mag": 5, "info": "the city origin"},
                                       {"x": 30.0, "y": 0.0, "kind": "here", "mag": 4, "info": "30 m east"},
                                       # (#258: other points drawn with it, and an answer placed on the map)
                                       {"x": 60.0, "y": 0.0, "kind": "here", "mag": 3, "info": "60 m east", "pick": True,
                                        "marks": [{"x": 62.0, "y": 2.0, "label": "the other source", "color": "#ff9e31"}]},
                                       # (#310: its own answers, one of them a point placed on the map)
                                       {"x": 90.0, "y": 0.0, "kind": "here", "mag": 2, "info": "90 m east", "pick": True,
                                        "options": ["the source", "my own mark: place it on the map", "unsure"],
                                        "place_option": "my own mark: place it on the map"}]}}}
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


def png(w, h, rgb, stripe=None):
    """A w×h PNG of one colour, with dark 3 px columns every `stripe` px (the orthophoto as the mocked
    service sends it: the columns stand for rails)."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    dark = bytes(c // 3 for c in rgb)
    row = b"".join(dark if stripe and x % stripe < 3 else bytes(rgb) for x in range(w))
    raw = b"".join(b"\0" + row for _ in range(h))
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
            browser = gpu.launch(p)[0]
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
              // (#334: the directory's link to a kerb list relies on these two)
              const { fid } = await import('./src/reviewFindings.js');
              const fileFilter = R.$('rvFilter').value, opened = R.file;
              R.file = null; R._filters(); // (the directory's link to a kerb list names no file)
              const firstFilter = R.$('rvFilter').value, kerbIds = R.findings.filter((f) => f.src === 'kerbs').map(fid);
              R.file = opened;
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
              return { by, fileFilter, firstFilter, kerbIds, look: Math.hypot(gx - f.x, gy - f.y), lat: L.lat, lon: L.lon, links, buttons,
                       panel: { top: panel.top, height: panel.height, width: panel.width },
                       heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null };
            }""")
            r["loadS"] = round(time.time() - t0)
            r["kerbIdsIndex"] = next((s["ids"] for s in review_sets.kerb_sets(serve.ROOT, [args.line])), [])
            # the orthophoto (#201), with IPR's service mocked: a 64 px image with the CORS header it sends,
            # then a service that refuses; and the track sources over it
            errors, ortho = [], []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("https://gs-pub.praha.eu/**", lambda q: (ortho.append(q.request.url), q.fulfill(
                status=200, content_type="image/png", headers={"Access-Control-Allow-Origin": "*"}, body=png(1500, 1500, (150, 150, 140), 100))))
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
              // the look: contrast, then lines (a stripe at x 100–102 of the 1500 px image, plain paving at x 150)
              const px = (x) => [...R.orthoMesh.material.map.image.getContext('2d').getImageData(x, 750, 1, 1).data].slice(0, 3);
              document.querySelector('[data-look="contrast"]').click();
              const contrast = { canvas: R.orthoMesh.material.map.isCanvasTexture === true, line: px(101), plain: px(150) };
              document.querySelector('[data-look="lines"]').click();
              const lines = { line: px(101), plain: px(150), maps: Object.keys(R.orthoMaps).sort().join() };
              document.querySelector('[data-look="contrast"]').click(); document.querySelector('[data-look="lines"]').click();
              const back = R.orthoMesh.material.map === R.orthoMaps['00'];
              R.dist = dist; R._render();
              return { loaded: !!loaded, w: first?.material.map.image.width, url, near, contrast, lines, back, credit, shown,
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
            # the same mouse and keys as the game's free cameras (#342; their side: tools/test_free_camera.py)
            spot = page.evaluate("""() => {
              const R = window.review, r = R.canvas.getBoundingClientRect();
              for (let y = r.top + 40; y < r.bottom - 120; y += 40) for (let x = r.left + 40; x < r.right - 120; x += 40)
                if (document.elementFromPoint(x, y) === R.canvas && document.elementFromPoint(x + 60, y + 20) === R.canvas) return { x, y };
            }""")
            cam = "(() => { const R = window.review; return { yaw: R.yaw, pitch: R.pitch, x: R.T.x, y: R.T.y, dist: R.dist }; })()"

            def moved(a, b):
                return {"yaw": b["yaw"] - a["yaw"], "pitch": b["pitch"] - a["pitch"], "move": abs(b["x"] - a["x"]) + abs(b["y"] - a["y"]), "dist": b["dist"] - a["dist"]}

            def drag(button="left", shift=False):
                a = page.evaluate(cam)
                if shift:
                    page.keyboard.down("Shift")
                page.mouse.move(spot["x"], spot["y"])
                page.mouse.down(button=button)
                page.mouse.move(spot["x"] + 60, spot["y"] + 20, steps=4)
                page.mouse.up(button=button)
                if shift:
                    page.keyboard.up("Shift")
                return moved(a, page.evaluate(cam))

            def hold(key):
                a = page.evaluate(cam)
                page.keyboard.down(key)
                page.wait_for_timeout(250)
                page.keyboard.up(key)
                return moved(a, page.evaluate(cam))

            r["cam"] = {"left": drag(), "right": drag("right"), "shift": drag(shift=True),
                        **{k: hold(k) for k in ("q", "e", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "r", "f", "w")}}
            r["cam"]["finger"] = page.evaluate("""() => {
              const R = window.review, a = { yaw: R.yaw, x: R.T.x, y: R.T.y };
              const send = (type, x, y) => R.canvas.dispatchEvent(new PointerEvent(type, { pointerId: 7, pointerType: 'touch', clientX: x, clientY: y, button: 0, bubbles: true }));
              send('pointerdown', 300, 300); send('pointermove', 360, 320); send('pointerup', 360, 320);
              return { yaw: R.yaw - a.yaw, move: Math.abs(R.T.x - a.x) + Math.abs(R.T.y - a.y) };
            }""")
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
            # a kerb on the list with an OSM lowered kerb along it: the card names it, one without does not (#142)
            r["kerbNote"] = page.evaluate("""async () => {
              const { kerbFindings } = await import('./src/review.js');
              const row = { c: 'sidewalk', x: 1, y: 2, kerb: 40, terrainOff: 0.2, line: 'foot', basis: 'terrain' };
              return kerbFindings({ provenance: { a: { platformSteps: [], review: [{ ...row, osmKerb: { flush: 1, lowered: 2 } }, row] } } }).map((f) => f.info);
            }""")
            # a finding with a mark and a placed answer (#258): the legend, the mark drawn, a click on the map 5 m east
            # of its pin saved as px, py
            place = page.evaluate("""() => {
              const R = window.review, i = R.list.findIndex((f) => f.info === '60 m east'), f = R.list[i];
              R.select(i);
              R.T.x = f.x; R.T.y = f.y; R.yaw = 0; R.pitch = 1.4; R.dist = 40; R._render(); R.camera.updateMatrixWorld();
              const r = R.canvas.getBoundingClientRect(), v = R.camera.position.clone().set(f.x + 5, f.z, -f.y).project(R.camera);
              return { legend: R.$('rvCard').textContent.includes('the other source'), button: !!R.$('rvCard').querySelector('button[data-place]'),
                       marks: R.hl.children.length, x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
            }""")
            page.click("#rvCard button[data-place]")
            page.mouse.click(place["x"], place["y"])
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length", timeout=20000)
            got = json.load(open(saved, encoding="utf-8"))
            rec = next((v for v in got.get("items", {}).values() if v.get("info") == "60 m east"), {})
            r["place"] = {**{k: place[k] for k in ("legend", "button", "marks")}, "v": rec.get("v"), "px": rec.get("px"), "py": rec.get("py")}
            # then an answer button: the placed point stays with it (it was dropped, line 22's stop signs, #258)
            page.click("#rvCard button[data-v='0']")
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length", timeout=20000)
            got = json.load(open(saved, encoding="utf-8"))
            rec = next((v for v in got.get("items", {}).values() if v.get("info") == "60 m east"), {})
            r["place"]["after"] = {"v": rec.get("v"), "px": rec.get("px")}
            # &todo (#310): a finding answered there, or given a point of one's own, stays in the list (placed: on the
            # card too; answered: the card moves on to the next without an answer, as before)
            todo = page.evaluate("""() => {
              const R = window.review;
              R.todo = true; R.kept.clear(); R._fill();
              const i = R.list.findIndex((f) => f.info === '90 m east'), f = R.list[i];
              R.select(i);
              R.T.x = f.x; R.T.y = f.y; R.yaw = 0; R.pitch = 1.4; R.dist = 40; R._render(); R.camera.updateMatrixWorld();
              const r = R.canvas.getBoundingClientRect(), v = R.camera.position.clone().set(f.x + 5, f.z, -f.y).project(R.camera);
              return { place: !!R.$('rvCard').querySelector('button[data-place]'), x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height };
            }""")
            page.click("#rvCard button[data-v='1']")
            page.mouse.click(todo["x"], todo["y"])
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length", timeout=20000)
            seen = "() => { const R = window.review; return { listed: R.list.some((f) => f.info === '90 m east'), card: R.$('rvCard').textContent.includes('90 m east') }; }"
            todo["placed"] = page.evaluate(seen)
            got = json.load(open(saved, encoding="utf-8"))
            rec = next((v for v in got.get("items", {}).values() if v.get("info") == "90 m east"), {})
            todo["placed"].update(v=rec.get("v"), px=rec.get("px"))
            page.click("#rvCard button[data-v='0']")
            page.wait_for_function("window.review.verdicts.state === 'saved' && !Object.keys(window.review.verdicts.pending).length", timeout=20000)
            todo["answered"] = page.evaluate(seen)
            page.evaluate("() => { const R = window.review; R.todo = false; R._fill(); }")
            r["todo"] = todo
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
            # (#379: an answer data/truth.json records shows on its card, without the page's remove button)
            r['recorded'] = page.evaluate('''() => {
              const R=window.review, f=R.findings.find(f=>f.id==='other-bridge');
              f.recorded={v:'follows survey surface',t:1,date:'2026-11-02',quote:'the quote',source:'data/truth.json'};
              R.otherAnswers={}; R._fill(); R.select(R.list.indexOf(f));
              const card=R.$('rvCard');
              return {on:[...card.querySelectorAll('button.on')].map(b=>b.textContent), text:card.textContent,
                      remove:!!card.querySelector('button[data-v=""]'), across:R.$('rvCount').textContent};
            }''')
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
    c, ln = o["contrast"], o["lines"]
    if not c["canvas"] or c["line"][0] >= 60:
        fails.append(f"orthophoto contrast: no processed image, or the dark stripe not kept dark: {c}")
    if not (ln["line"][2] > ln["line"][0] + 80 and abs(ln["plain"][2] - ln["plain"][0]) < 40) or ln["maps"] != "00,10,11" or not o["back"]:
        fails.append(f"orthophoto lines: the stripe not cyan, the paving tinted, or the looks not kept per image: {ln}, back {o['back']}")
    if not o["loaded"] or o["w"] != 1500:
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
    if sorted(r["kerbIds"]) != sorted(r["kerbIdsIndex"]):
        fails.append(f"the directory's kerb ids are not review mode's: {len(r['kerbIds'])} on the page, {len(r['kerbIdsIndex'])} in the index")
    if r["fileFilter"] != "file|":
        fails.append(f"review mode opened with a findings file starts on {r['fileFilter']!r}, not on that file")
    if r["kerbIds"] and r["firstFilter"] != "kerbs|":
        fails.append(f"review mode starts on {r['firstFilter']!r}, not on the kerbs the directory's link promises")
    if not (r["kerbNote"][0].endswith("· OSM: kerb=flush ×1, kerb=lowered ×2 along this kerb") and "OSM" not in r["kerbNote"][1]):
        fails.append(f"the kerb card's OSM note: {r['kerbNote']}")
    t = r["todo"]
    if t["place"] or not (t["placed"]["listed"] and t["placed"]["card"] and t["placed"]["v"] == "my own mark: place it on the map"
                          and abs((t["placed"]["px"] or 0) - 95) < 1.5 and t["answered"]["listed"]):
        fails.append(f"&todo: an answered or placed finding left the list or the card, or the own mark was not placed (want px ≈ 95): {t}")
    p = r["place"]
    if not (p["legend"] and p["button"] and p["marks"] >= 2 and p["v"] == "placed on the map"
            and p["px"] is not None and abs(p["px"] - 65) < 1.5 and abs(p["py"]) < 1.5):
        fails.append(f"a mark or the answer placed on the map (want px ≈ 65, py ≈ 0): {p}")
    if p["after"]["px"] != p["px"] or p["after"]["v"] in (None, "placed on the map"):
        fails.append(f"an answer after placing keeps the placed point: {p}")
    if (r["back"]["rec"] or {}).get("v") != "wrong" or not r["back"]["count"].startswith("1 / 4"):
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
    rec = r['recorded']
    if (rec['on'] != ['2 · follows survey surface'] or 'Answered in data/truth.json (2026-11-02): “the quote”' not in rec['text']
            or rec['remove'] or '2 / 2 answered across lines' not in rec['across']):
        fails.append(f"an answer recorded in data/truth.json is not shown on its card: {rec}")
    c = r["cam"]
    if not (c["left"]["yaw"] > 0 and c["left"]["pitch"] > 0 and c["left"]["move"] == 0):
        fails.append(f"a left drag does not turn and tilt, to the right and down, without moving: {c['left']}")
    for how in ("right", "shift"):
        if not (c[how]["move"] > 0 and c[how]["yaw"] == 0 and c[how]["pitch"] == 0):
            fails.append(f"a {how} drag does not move the camera alone: {c[how]}")
    if not (c["q"]["yaw"] < 0 < c["e"]["yaw"] and c["ArrowLeft"]["yaw"] < 0 < c["ArrowRight"]["yaw"] and c["ArrowUp"]["pitch"] < 0 < c["ArrowDown"]["pitch"]):
        fails.append(f"Q/E or the arrows do not turn left and right, or tilt up and down: {c}")
    if not (c["r"]["dist"] > 0 > c["f"]["dist"] and c["w"]["move"] > 0):
        fails.append(f"R/F do not go up and down, or W does not move: {c}")
    if not (c["finger"]["move"] > 0 and c["finger"]["yaw"] == 0):
        fails.append(f"one finger does not move the map: {c['finger']}")
    if fails:
        sys.exit("; ".join(fails))
    print("review mode: findings, camera, links, bottom sheet, a click on a pin; an answer saved, the next finding, read back: pass")


if __name__ == "__main__":
    main()
