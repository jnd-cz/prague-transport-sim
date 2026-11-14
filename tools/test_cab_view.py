# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cab view is fixed to the tram body (#597): python -P -E tools/test_cab_view.py [--line 17] [--shots DIR] [--root DIR]
(its own server on a free port). The tram stands in the line's tightest curve, its front past the curve's middle. The
camera must be the lead car's point 0.8 m behind the body's front, 2.39 m over the rail, on the centre line, and
look along the body. It prints how far the track 4 m ahead of the tram (the old view's heading) turns from the body
there. --shots saves the cab view; --root serves another checkout (main's, to compare its view)."""
import argparse
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the tightest curve: the heading's turn over 10 m, every 2 m; the tram's front 8 m past it
PLACE = """() => {
  const r = window.game.route, yaw = (h) => Math.atan2(h.hx, h.hy);
  let best = null;
  for (let s = 60; s < r.length - 60; s += 2) {
    let d = yaw(r.heading(s + 5, 5)) - yaw(r.heading(s - 5, 5));
    d = Math.atan2(Math.sin(d), Math.cos(d));
    if (!best || Math.abs(d) > best.d) best = { s, d: Math.abs(d) };
  }
  const g = window.game;
  g.tram.s = best.s + 8; g.tram.v = 0; g.tram.a = 0; g.paused = true;
  return { s: best.s, R: Math.round(10 / best.d) };
}"""
MEASURE = """() => {
  const lead = window.tramModel.userData.cars[0], cam = window.camera, r = window.game.route, s = window.game.tram.s;
  lead.updateWorldMatrix(true, false);
  const deg = (a) => Math.round(Math.atan2(Math.sin(a), Math.cos(a)) * 1800 / Math.PI) / 10;
  const f = new cam.position.constructor(0, 0, 1).transformDirection(lead.matrixWorld), body = Math.atan2(f.x, -f.z);
  const d = new cam.position.constructor(); cam.getWorldDirection(d);
  const h = r.heading(s + 4, 8), ahead = Math.atan2(h.hx, h.hy);
  const p = lead.worldToLocal(cam.position.clone());
  return { viewVsBody: deg(Math.atan2(d.x, -d.z) - body), oldHeadingVsBody: deg(ahead - body),
           eye: [p.x, p.y, p.z].map((v) => Math.round(v * 100) / 100) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--shots")
    ap.add_argument("--root", default=ROOT)
    args = ap.parse_args()
    root = os.path.abspath(args.root)
    if not os.path.exists(os.path.join(root, "data", f"line{args.line}.json")):
        print(f"skip: data/line{args.line}.json missing (python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(600, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=root))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            r = page.evaluate(PLACE)
            page.wait_for_timeout(3000)  # (the old view eased towards its heading)
            r.update(page.evaluate(MEASURE))
            if args.shots:
                os.makedirs(args.shots, exist_ok=True)
                page.screenshot(path=os.path.join(args.shots, f"cab-line{args.line}.png"))
            r["errors"] = errors[:3]
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    fails = []
    if abs(r["viewVsBody"]) > 0.5:
        fails.append(f"the cab view looks {r['viewVsBody']} degrees off the body (the track ahead turns {r['oldHeadingVsBody']})")
    x, y, z = r["eye"]
    if abs(x) > 0.02 or abs(y - 2.39) > 0.02 or not 5.5 < z < 7:
        fails.append(f"the eye at {r['eye']} in the lead car (want 0, 2.39, 0.8 m behind the body's front)")
    if r["errors"]:
        fails.append(f"page errors: {r['errors']}")
    if fails:
        sys.exit("; ".join(fails))
    print(f"cab view: on the body in a {r['R']} m curve (the track 4 m ahead turns {r['oldHeadingVsBody']} degrees from it), "
          f"the eye at {r['eye']}: pass")


if __name__ == "__main__":
    main()
