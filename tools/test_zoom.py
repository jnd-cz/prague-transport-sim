"""The cab view's zoom key (#382): python -P -E tools/test_zoom.py [--line 17] (its own server on a free port).

At 1920 x 1080: holding G narrows the cab camera to ZOOM's field and letting go brings back 62 degrees; from 75 m before a
restriction board its figures (0.113 of 0.3 of the plate) are at least 8 px high zoomed; the outside view (V) keeps its
field; the window losing focus lets the zoom go. On a phone (390 x 844, touch) the held 🔍 button does the same.
"""
import argparse
import faulthandler
import functools
import http.server
import json
import math
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
CAB_FOV, ZOOM = 62, 3
ZOOMED = 2 * math.degrees(math.atan(math.tan(math.radians(CAB_FOV / 2)) / ZOOM))   # 22.75


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def shift(browser, port, line, vp, mobile):
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mobile, has_touch=mobile, device_scale_factor=1)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/?line={line}", timeout=300000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
    page.click("#btnStart", no_wait_after=True)
    page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=120000)
    return ctx, page, errors


FOV = "Math.round(window.camera.fov * 100) / 100"
# the figures' height on the screen of the restriction board standing nearest to `at`, at that moment's camera
FIGURES = r"""async () => {
  const THREE = await import('three');
  const g = window.game, cam = window.camera;
  let board = null;
  g.objects.traverse((o) => { if (o.userData?.sign?.kind === 'restriction' && Math.abs((o.userData.mountedS ?? -1e9) - g._zoomTestAt) < 1) board = o; });
  if (!board) return null;
  const face = board.children[1], bb = (face.geometry.computeBoundingBox(), face.geometry.boundingBox);
  face.updateMatrixWorld(true);
  const y = (v) => (1 - face.localToWorld(new THREE.Vector3(0, v, 0)).project(cam).y) / 2 * innerHeight;
  const plate = Math.abs(y(bb.min.y) - y(bb.max.y));
  return Math.round(plate * 0.113 / 0.3 * 10) / 10;
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port, r, fails = server.server_port, {}, []
    near = lambda v: f"Math.abs(window.camera.fov - {v}) < 0.3"  # noqa: E731
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            ctx, page, errors = shift(browser, port, args.line, (1920, 1080), False)
            r["start"] = page.evaluate(FOV)
            # 75 m before the first restriction board past 300 m, paused there
            at = page.evaluate("(window.game.signBoards || []).filter((b) => b.kind === 'restriction' && b.at > 300).map((b) => b.at)[0] ?? null")
            r["board"] = at
            if at is not None:
                page.evaluate(f"window.game._zoomTestAt = {at}; window.game.tram.s = {at - 75}; window.game.tram.v = 0; window.game.paused = true")
                page.wait_for_timeout(1500)
                r["figuresPlain"] = page.evaluate(FIGURES)
            page.keyboard.down("g")
            page.wait_for_function(near(ZOOMED), timeout=60000)
            r["zoomed"] = page.evaluate(FOV)
            page.wait_for_timeout(500)
            if at is not None:
                r["figuresZoomed"] = page.evaluate(FIGURES)
            page.keyboard.up("g")
            page.wait_for_function(near(CAB_FOV), timeout=60000)
            r["released"] = page.evaluate(FOV)
            # the outside view keeps its field
            page.evaluate("window.game.paused = false")
            page.keyboard.press("v")
            page.keyboard.down("g")
            page.wait_for_timeout(1500)
            r["outside"] = page.evaluate(FOV)
            page.keyboard.up("g")
            page.keyboard.press("v")
            # a lost focus lets go
            page.keyboard.down("g")
            page.wait_for_function(near(ZOOMED), timeout=60000)
            page.evaluate("window.dispatchEvent(new Event('blur'))")
            page.wait_for_function(near(CAB_FOV), timeout=60000)
            r["afterBlur"] = page.evaluate(FOV)
            page.keyboard.up("g")
            r["errors"] = errors[:3]
            ctx.close()
            # the phone: the held 🔍 button
            ctx, page, errors = shift(browser, port, args.line, (390, 844), True)
            r["button"] = page.is_visible("#touch button[data-k='g']")
            box = page.locator("#touch button[data-k='g']").bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.wait_for_function(near(ZOOMED), timeout=60000)
            r["touchZoomed"] = page.evaluate(FOV)
            page.mouse.up()
            page.wait_for_function(near(CAB_FOV), timeout=60000)
            r["touchReleased"] = page.evaluate(FOV)
            r["phoneErrors"] = errors[:3]
            ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False))
    ok = lambda v, want: v is not None and abs(v - want) < 0.3  # noqa: E731
    if not ok(r.get("start"), CAB_FOV): fails.append(f"the cab view starts at {CAB_FOV}°: {r.get('start')}")
    if not ok(r.get("zoomed"), ZOOMED): fails.append(f"G held narrows it to {ZOOMED:.2f}°: {r.get('zoomed')}")
    if not ok(r.get("released"), CAB_FOV): fails.append(f"letting go brings back {CAB_FOV}°: {r.get('released')}")
    if not ok(r.get("outside"), CAB_FOV): fails.append(f"the outside view keeps {CAB_FOV}°: {r.get('outside')}")
    if not ok(r.get("afterBlur"), CAB_FOV): fails.append(f"a lost focus lets the zoom go: {r.get('afterBlur')}")
    if r.get("board") is None: fails.append("no restriction board past 300 m to measure on this line")
    elif not (r.get("figuresZoomed") or 0) >= 8: fails.append(f"zoomed, the figures 75 m ahead are 8 px or more: {r.get('figuresZoomed')} (plain {r.get('figuresPlain')})")
    if not r.get("button"): fails.append("the phone shows the 🔍 button")
    if not ok(r.get("touchZoomed"), ZOOMED) or not ok(r.get("touchReleased"), CAB_FOV): fails.append(f"the held button zooms and lets go: {r.get('touchZoomed')}, {r.get('touchReleased')}")
    fails += [f"page error: {e}" for e in r.get("errors", []) + r.get("phoneErrors", [])]
    if fails:
        print("FAILED\n  " + "\n  ".join(fails))
        sys.exit(1)
    print(f"zoom: {CAB_FOV}° -> {ZOOMED:.1f}° held; figures 75 m ahead {r['figuresPlain']} px -> {r['figuresZoomed']} px")


if __name__ == "__main__":
    main()
