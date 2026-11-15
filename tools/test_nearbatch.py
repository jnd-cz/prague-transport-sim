# SPDX-License-Identifier: AGPL-3.0-or-later
"""src/nearbatch.js (#610): small things drawn near the camera only. python -P -E tools/test_nearbatch.py

Serves the checkout on a free port and loads the module in a page with the game's import map (three from its CDN).
Checks: an upright thing's range from its size and the picture's pixels; flat ones go nearer; nothing past the fog;
a refill only once the camera has moved; the drawn instances' bounding sphere around them (a sphere of the wrong
ones culled a whole batch in the rear view); getMatrixAt and setColorAt reach every instance, drawn or not.
"""
import faulthandler
import functools
import http.server
import json
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


TEST = r"""async () => {
  const THREE = await import('three');
  const { NearBatches } = await import('/src/nearbatch.js');
  const mk = (n, step) => {
    const m = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial(), n), M = new THREE.Matrix4();
    for (let i = 0; i < n; i++) m.setMatrixAt(i, M.makeTranslation(i * step, 0, 0));
    m.setColorAt(0, new THREE.Color(1, 1, 1));
    return m;
  };
  const nb = new NearBatches();
  const up = nb.add(mk(400, 10), 'posts', 1);          // 1 m tall, one every 10 m along x
  const flat = nb.add(mk(400, 10), 'covers', 0.6, true);
  const cam = new THREE.PerspectiveCamera(62, 1, 0.3, 950);
  const out = {};
  cam.position.set(0, 3, 0);
  out.first = nb.update(cam, 1000, 950);
  out.log1 = JSON.parse(JSON.stringify(nb.log));
  out.again = nb.update(cam, 1000, 950);
  cam.position.set(2000, 3, 0);
  out.moved = nb.update(cam, 1000, 950);
  out.log2 = JSON.parse(JSON.stringify(nb.log));
  const bs = up.boundingSphere;
  out.sphere = [bs.center.x, bs.radius];
  // every instance through getMatrixAt; a recolour reaches a drawn instance's copy
  const M = new THREE.Matrix4(), v = new THREE.Vector3();
  up.getMatrixAt(399, M); out.last = v.setFromMatrixPosition(M).x;
  out.total = up.userData.total;
  const i = 200; up.setColorAt(i, new THREE.Color(1, 0, 0)); nb.update(cam, 1000, 950);
  const a = up.instanceMatrix.array; let k = -1;
  for (let j = 0; j < up.count; j++) if (a[j * 16 + 12] === i * 10) k = j;
  out.recolour = k >= 0 ? Array.from(up.instanceColor.array.slice(k * 3, k * 3 + 3)) : null;
  // a taller picture (the zoom key, a larger screen): longer range; fog: none past its end
  nb.update(cam, 3000, 5000); out.tall = nb.log.posts.range;
  nb.update(cam, 3000, 300); out.fogged = nb.log.posts.range;
  return out;
}"""

faulthandler.dump_traceback_later(300, exit=True)
imap = re.search(r'<script type="importmap">.*?</script>', open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), re.S)[0]
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = gpu.launch(p)[0]
        page = browser.new_page()
        page.route("**/nearbatch-test.html", lambda route: route.fulfill(content_type="text/html", body=f"<!doctype html>{imap}"))
        page.goto(f"http://127.0.0.1:{server.server_port}/nearbatch-test.html")
        r = page.evaluate(TEST)
        browser.close()
finally:
    server.shutdown()
print(json.dumps(r))
fails = []
px = 62 * 3.14159265 / 180 / 1000
want = 1 / (px * 1.5)  # (src/nearbatch.js UPRIGHT_PX)
if not (r["first"] and abs(r["log1"]["posts"]["range"] - want) < 2):
    fails.append(f"upright range {r['log1']['posts']['range']}, want {want:.0f}")
if not r["log1"]["covers"]["range"] < r["log1"]["posts"]["range"] / 3:
    fails.append(f"flat covers not nearer: {r['log1']['covers']}")
if r["again"]:
    fails.append("refilled without the camera moving")
if not r["moved"]:
    fails.append("no refill after moving 2 km")
drawn = r["log2"]["posts"]["drawn"]
if not (drawn and abs(r["sphere"][0] - 2000) < 60 and r["sphere"][1] < r["log2"]["posts"]["range"] * 1.2):
    fails.append(f"the bounding sphere is not around the drawn instances: {r['sphere']}, drawn {drawn}")
if r["last"] != 3990 or r["total"] != 400:
    fails.append(f"getMatrixAt reads the kept instances: last at {r['last']}, total {r['total']}")
if r["recolour"] != [1, 0, 0]:
    fails.append(f"a recolour does not reach the drawn copy: {r['recolour']}")
if not (r["tall"] > r["log2"]["posts"]["range"] * 2.5 and r["fogged"] == 300):
    fails.append(f"range with a taller picture {r['tall']}, with the fog at 300 m {r['fogged']}")
if fails:
    sys.exit("; ".join(fails))
print("nearbatch: ranges by size, refills on movement, the sphere of the drawn, every instance kept: pass")
