# SPDX-License-Identifier: AGPL-3.0-or-later
"""The HUD's distances: python -P -E tools/test_hud.py [--line 17] (its own server on a free port).

The limit ahead in the chip ("Limit 30 km/h in 87 m") and on the info screen (I) is shown in whole metres, also
when it is a stop's point limit, whose distance runs to the centimetre (#403); the game's own value stays exact,
for the autopilot (#486).
"""
import argparse
import faulthandler
import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
AHEAD = 87.34  # m before the point: a distance with decimals


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    a = ap.parse_args()
    faulthandler.dump_traceback_later(600, exit=True)  # (page.evaluate has no timeout of its own)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    fails = []
    try:
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{srv.server_port}/?line={a.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            page.click("#btnStart", no_wait_after=True)
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=120000)
            page.keyboard.press("p")
            page.wait_for_function("game.paused")
            # (a point where it is the next limit the game names: lower than the limit before it, nothing nearer)
            nl = page.evaluate(f"""() => {{
              const g = game; g.opts.assist = true;
              for (const p of g.points) {{
                g.tram.s = p.s - {AHEAD}; g.tram.v = 0;
                const nl = g.nextLimitChange();
                if (nl && nl.point) return nl;
              }}
              return null;
            }}""")
            if not nl:
                fails.append(f"line {a.line}: no stop's point limit ahead of any position tried")
            else:
                page.keyboard.press("i")  # (the info screen)
                page.wait_for_function("document.getElementById('assist').textContent.length > 0")
                page.wait_for_timeout(200)  # (the HUD redraws 30 times a second)
                chip = [c for c in page.eval_on_selector_all("#assist .chip", "cs => cs.map(c => c.textContent)")
                        if f"{nl['v']} km/h" in c]
                info = page.text_content("#info") or ""
                want = str(round(nl["d"]))
                print(f"line {a.line}: next limit {nl['v']} km/h at {nl['d']:.2f} m; chip {chip}; "
                      f"info {re.findall(r'[^·]*' + str(nl['v']) + r' \S+ \S+ m', info)}")
                if abs(nl["d"] - AHEAD) > 1e-6:
                    fails.append(f"the game's distance {nl['d']} is not the exact {AHEAD}")
                if not chip or f" {want} m" not in chip[0] or re.search(r"\d\.\d", chip[0]):
                    fails.append(f"chip {chip}: wants {want} m, whole")
                if f" {want} m" not in info or re.search(rf"{nl['v']} \S+ \d+\.\d+ m", info):
                    fails.append(f"info line: wants {want} m, whole")
            if errors:
                fails.append(f"page errors: {errors[:3]}")
            browser.close()
    finally:
        srv.shutdown()
    print("FAIL:\n  " + "\n  ".join(fails) if fails else "OK")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
