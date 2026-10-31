"""Smoke test of review mode (?review, src/review.js) on a phone-sized page with touch:
python -P -E tools/test_review.py [--line 17]
(serves the checkout itself on a free port; a findings file is served by the test, not written)."""
import argparse
import functools
import http.server
import json
import math
import os
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = {"checks": {"demo": {"places": [{"x": 0.0, "y": 0.0, "kind": "here", "mag": 5, "info": "the city origin"}]}}}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            page = ctx.new_page()
            page.route("**/test-findings.json", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(FILE)))
            t0 = time.time()
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}&review=test-findings.json", timeout=180000)
            page.wait_for_function("window.review", timeout=180000)
            r = page.evaluate("""async () => {
              const R = window.review;
              await R.ready;
              const by = {};
              for (const f of R.findings) by[f.src] = (by[f.src] || 0) + 1;
              R.$('rvFilter').value = '';
              R._fill();
              const i = R.list.findIndex((f) => f.src === 'file');
              R.select(i);
              const f = R.list[i], L = R.links(f.x, f.y);
              const t = R.camera.position.clone(), dir = new t.constructor();
              R.camera.getWorldDirection(dir);
              // where the camera looks at the finding's height: within 30 m of it
              const k = (f.z - t.y) / dir.y, gx = t.x + dir.x * k, gy = -(t.z + dir.z * k);
              const links = [...document.querySelectorAll('#rvCard a')].map((a) => a.href);
              const panel = document.querySelector('#review').getBoundingClientRect();
              return { by, look: Math.hypot(gx - f.x, gy - f.y), lat: L.lat, lon: L.lon, links,
                       panel: { top: panel.top, height: panel.height, width: panel.width },
                       heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1e6) : null };
            }""")
            r["loadS"] = round(time.time() - t0)
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
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
    if fails:
        sys.exit("; ".join(fails))
    print("review mode: findings from the survey and a file, camera on the finding, links, bottom sheet: pass")


if __name__ == "__main__":
    main()
