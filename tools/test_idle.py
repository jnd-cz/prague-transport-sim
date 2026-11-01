"""Idle drawing (#149): python -P -E tools/test_idle.py [--line 23]
(its own server on a free port). Counts the page's draws (window.drawCount) against the browser's frames
for 2 s in each state: the menu, driving, paused, and review mode at rest and moving. Idle
states draw at most ~4 a second; driving and a moving review camera draw every frame. (The draws are
no-ops while counted: headless software WebGL would otherwise make every frame one slow draw.)"""
import argparse
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEASURE = """async (move) => {
  // (the draw itself made a no-op: software WebGL takes ~300 ms a draw, which hid the rule)
  const R = window.renderer, render = R.render;
  R.render = () => {};
  const d0 = window.drawCount, t0 = performance.now();
  let frames = 0, run = true;
  const f = () => { frames++; if (move) { window.review._pan(3, 0); window.review._render(); } if (run) requestAnimationFrame(f); };
  requestAnimationFrame(f);
  await new Promise((ok) => setTimeout(ok, 2000));
  run = false;
  R.render = render;
  const s = (performance.now() - t0) / 1000;
  return { draws: +((window.drawCount - d0) / s).toFixed(1), frames: +(frames / s).toFixed(1) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="23")
    args = ap.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base, r = f"http://127.0.0.1:{server.server_port}/?line={args.line}", {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 600})
            page.goto(base, timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.wait_for_timeout(500)
            r["menu"] = page.evaluate(MEASURE, False)
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            r["driving"] = page.evaluate(MEASURE, False)
            page.keyboard.press("p")
            r["paused"] = page.evaluate(MEASURE, False)
            page.keyboard.press("p")
            r["resumed"] = page.evaluate(MEASURE, False)
            page.goto(base + "&review", timeout=180000)
            page.wait_for_function("window.review", timeout=180000)
            page.evaluate("window.review.ready")
            page.wait_for_timeout(1500)
            r["reviewRest"] = page.evaluate(MEASURE, False)
            r["reviewMove"] = page.evaluate(MEASURE, True)
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    fails = [f"{k} draws {v['draws']}/s, idle should be at most 5" for k, v in r.items()
             if k in ("menu", "paused", "reviewRest") and v["draws"] > 5]
    fails += [f"{k} draws {v['draws']} of {v['frames']} frames a second, should draw every frame" for k, v in r.items()
              if k in ("driving", "resumed", "reviewMove") and v["draws"] < 0.9 * v["frames"]]
    if fails:
        sys.exit("; ".join(fails))
    print("idle drawing: menu, pause and a resting review at most 5 a second; driving and a moving review every frame: pass")


if __name__ == "__main__":
    main()
