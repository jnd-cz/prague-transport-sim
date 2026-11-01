"""On-screen controls and the viewport-sized mirror (#79): python -P -E tools/test_touch.py [--line 17]
(its own server on a free port). On a phone (390 x 844, touch) a shift is driven by the buttons only:
doors closed, two notches of power, the tram moves, the emergency brake; the outside view turns by a
drag. On desktops the buttons stay hidden and the mirror frame grows with the viewport, its aspect fixed."""
import argparse
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def shift(browser, port, line, vp, mobile):
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/?line={line}", timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
    page.click("#btnStart")
    page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
    return ctx, page, errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port, r, fails = server.server_port, {}, []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx, page, errors = shift(browser, port, args.line, (390, 844), True)
            r["buttons"] = page.is_visible("#touch button[data-k='w']")
            tap = lambda k: page.tap(f"#touch button[data-k='{k}']")  # noqa: E731
            # (headless software WebGL draws line 17 at ~2.5 fps, so game time crawls: the test steps it)
            step = lambda sec: page.evaluate(f"for (let i = 0; i < {int(sec / 0.05)}; i++) window.game.update(0.05, {{}})")  # noqa: E731
            tap("d")
            step(6)
            r["doors"] = page.evaluate("window.game.doorState")
            tap("n")
            tap("w")
            tap("w")
            r["notch"] = page.evaluate("window.game.tram.notch")
            step(4)
            r["kmh"] = round(page.evaluate("window.game.tram.v") * 3.6, 1)
            # the emergency brake: held, then let go (back to B4)
            stop = page.locator("#touch button[data-k='space']").bounding_box()
            page.mouse.move(stop["x"] + 20, stop["y"] + 20)
            page.mouse.down()
            r["held"] = page.evaluate("window.game.tram.notch")
            page.mouse.up()
            r["released"] = page.evaluate("window.game.tram.notch")
            tap("v")
            page.wait_for_timeout(600)
            a = page.evaluate("[camera.position.x, camera.position.z]")
            page.mouse.move(195, 300)
            page.mouse.down()
            page.mouse.move(345, 300, steps=8)
            page.mouse.up()
            page.wait_for_timeout(300)
            b = page.evaluate("[camera.position.x, camera.position.z]")
            r["orbit"] = round(((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5, 1)
            r["phoneErrors"] = errors[:3]
            ctx.close()
            r["mirror"] = {}
            for vp in ((1280, 720), (2560, 1440)):
                ctx, page, errors = shift(browser, port, args.line, vp, False)
                box = page.locator("#mirror").bounding_box()
                r["mirror"][f"{vp[0]}x{vp[1]}"] = [round(box["width"]), round(box["height"])]
                r.setdefault("deskButtons", []).append(page.is_visible("#touch button[data-k='w']"))
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    if not r["buttons"]:
        fails.append("no on-screen controls on a phone")
    if r["doors"] != "closed" or r["notch"] != 2 or r["kmh"] <= 1:
        fails.append(f"the buttons did not drive the tram (doors {r['doors']}, notch {r['notch']}, {r['kmh']} km/h)")
    if r["held"] != -5 or r["released"] != -4:
        fails.append(f"emergency brake held {r['held']}, released {r['released']} (want -5, -4)")
    if r["orbit"] < 5:
        fails.append("a drag does not turn the outside view")
    if r["phoneErrors"]:
        fails.append(f"page errors: {r['phoneErrors']}")
    if any(r["deskButtons"]):
        fails.append("on-screen controls shown on a desktop")
    (w0, h0), (w1, h1) = r["mirror"].values()
    if not h1 > h0 * 1.5 or abs(w0 / h0 - 150 / 190) > 0.03 or abs(w1 / h1 - 150 / 190) > 0.03:
        fails.append(f"the mirror does not grow with the viewport at a fixed aspect: {r['mirror']}")
    if fails:
        sys.exit("; ".join(fails))
    print("touch: buttons drive the tram, emergency brake held and let go, outside view turns, mirror sized by the viewport: pass")


if __name__ == "__main__":
    main()
