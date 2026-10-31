"""src/geo.js's lat/lon against tools/geo.py on points across Prague: python -P -E tools/test_geo_js.py
(serves the checkout itself on a free port; fails over 2 m)."""
import functools
import http.server
import json
import math
import os
import random
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geo import Frame, ORIGIN  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIMIT = 2.0  # m (#129: enough to open street-level imagery at a place)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


rnd = random.Random(129)
# the city frame from Zličín to Černý Most and Ďáblice to Modřany (about 30 x 20 km)
pts = [(rnd.uniform(-14000, 16000), rnd.uniform(-11000, 9000)) for _ in range(200)]
lat, lon = Frame().ll([p[0] for p in pts], [p[1] for p in pts])
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f'http://127.0.0.1:{server.server_port}/README.md')
        got = page.evaluate('''async ([pts, origin]) => {
          const { toLatLon } = await import('/src/geo.js');
          return pts.map(([x, y]) => toLatLon(x, y, origin));
        }''', [pts, list(ORIGIN)])
        browser.close()
finally:
    server.shutdown()
err = []
for (la, lo), a, b in zip(got, lat, lon):
    err.append(math.hypot((la - a) * 111200, (lo - b) * 111200 * math.cos(math.radians(a))))
err.sort()
print(json.dumps({"points": len(err), "medianM": round(err[len(err) // 2], 2), "maxM": round(err[-1], 2)}))
if err[-1] > LIMIT:
    raise SystemExit(f"max error {err[-1]:.2f} m over {LIMIT} m")
