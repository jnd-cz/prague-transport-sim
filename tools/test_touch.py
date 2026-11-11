"""On-screen controls and the viewport-sized mirror (#79): python -P -E tools/test_touch.py [--line 17]
(its own server on a free port). On a phone (390 x 844, touch) a shift is driven by the buttons only:
doors closed, two notches of power, the tram moves, the emergency brake; the outside view turns by a
drag. On desktops the buttons stay hidden and the mirror frame grows with the viewport, its aspect fixed.
Full screen (#485): a phone asks once; "Not now" keeps a start in the page, "Full screen" enters it and so does each later
start after leaving it; a desktop isn't asked. In landscape (844 x 390, 740 x 360) the controller is a column at the right
(top to bottom: power, 0, brake, STOP), the other buttons at the left, the dashboard between them, no button over another
or off the screen; in portrait the controller stays a row. Safari on an iPhone (no Fullscreen API, played here by a page
script) is told once how to add the game to the home screen; started from there (display-mode standalone, also played)
it asks nothing and counts as full screen; the web manifest and the icons it names are served. A phone whose controls
were switched off keeps 🎮 in the shift, which brings them back; ⛶ stands apart from 🎮; a note's machine facts say
whether the controls were on."""
import argparse
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


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


FULL = "!!(document.fullscreenElement || document.webkitFullscreenElement)"
# (Safari on an iPhone: a page has no Fullscreen API)
SAFARI = """for (const k of ['fullscreenEnabled', 'webkitFullscreenEnabled']) Object.defineProperty(Document.prototype, k, { get: () => false });
delete Element.prototype.requestFullscreen; delete Element.prototype.webkitRequestFullscreen;"""
# (started from the home screen)
HOME = """const mm = window.matchMedia.bind(window);
window.matchMedia = (q) => /display-mode: (fullscreen|standalone)/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {} } : mm(q);"""


def menu(browser, port, line, script):
    """A phone's menu with a page script run first: (context, page, errors)."""
    ctx = browser.new_context(viewport={"width": 844, "height": 390}, is_mobile=True, has_touch=True)
    ctx.add_init_script(script)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/?line={line}", timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
    return ctx, page, errors


def layout(page):
    """What's wrong with the landscape layout: [] when nothing."""
    return page.evaluate("""() => {
      const box = (e) => { const r = e.getBoundingClientRect(); return { k: e.dataset.k || e.dataset.more || e.id, l: r.left, t: r.top, r: r.right, b: r.bottom }; };
      const main = [...document.querySelectorAll('#touch .main button')].filter((e) => e.offsetParent).map(box);
      const side = [...document.querySelectorAll('#touch .side button')].map(box), dash = box(document.getElementById('dash'));
      const all = [...main, ...side], bad = [];
      for (const b of all) if (b.l < 0 || b.t < 0 || b.r > innerWidth + 0.5 || b.b > innerHeight + 0.5) bad.push(`${b.k} off the screen`);
      for (let i = 0; i < all.length; i++) for (let j = i + 1; j < all.length; j++) {
        const a = all[i], c = all[j];
        if (a.l < c.r - 0.5 && c.l < a.r - 0.5 && a.t < c.b - 0.5 && c.t < a.b - 0.5) bad.push(`${a.k} over ${c.k}`);
      }
      const order = [...main].sort((a, b) => a.t - b.t).map((b) => b.k).join(' ');
      if (order !== 'w n s space') bad.push(`controller top to bottom: ${order}`);
      if (main.some((b) => b.l < dash.r - 0.5 || b.b - b.t < 58)) bad.push('the controller is not a column right of the dashboard, 58 px a button');
      if (side.some((b) => b.r > dash.l + 0.5)) bad.push('a side button over the dashboard');
      return bad;
    }""")


def shift(browser, port, line, vp, mobile, before=None):
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mobile, has_touch=mobile)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/?line={line}", timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
    if before:
        before(page)
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
            browser = gpu.launch(p)[0]
            def no(page):
                r["asked"] = page.is_visible("#fsAsk")
                page.tap("#fsAsk button[data-a='0']")
            ctx, page, errors = shift(browser, port, args.line, (390, 844), True, no)
            r["noFull"] = [page.evaluate(FULL), page.evaluate("localStorage.getItem('tram-fullscreen')")]
            r["portraitRow"] = len({round(b["y"]) for b in (page.locator(f"#touch .main button[data-k='{k}']").bounding_box()
                                                           for k in ("s", "n", "w", "space"))})
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
            r["notch"] = page.evaluate("window.game.tram.eq.lever")  # (arcade: the lever; the pedals follow on the next step)
            step(4)
            r["kmh"] = round(page.evaluate("window.game.tram.v") * 3.6, 1)
            # the emergency brake: held, then let go (back to brake step 5)
            stop = page.locator("#touch button[data-k='space']").bounding_box()
            page.mouse.move(stop["x"] + 20, stop["y"] + 20)
            page.mouse.down()
            r["held"] = page.evaluate("window.game.tram.eq.lever")
            page.mouse.up()
            r["released"] = page.evaluate("window.game.tram.eq.lever")
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
            # landscape: the question's yes, full screen again on a start after leaving it, the layout at two sizes
            def yes(page):
                r["askedL"] = page.is_visible("#fsAsk")
                page.tap("#fsAsk button[data-a='1']")
                page.wait_for_function(FULL, timeout=5000)
                page.evaluate("document.exitFullscreen()")
                page.wait_for_function("!" + FULL, timeout=5000)
            ctx, page, errors = shift(browser, port, args.line, (844, 390), True, yes)
            page.wait_for_function(FULL, timeout=5000)
            r["fullAgain"] = page.evaluate(FULL)
            page.wait_for_timeout(300)
            r["layout"] = {"844x390": layout(page)}
            page.evaluate("document.exitFullscreen()")  # (a full-screen window can't be resized)
            page.wait_for_function("!" + FULL, timeout=5000)
            page.set_viewport_size({"width": 740, "height": 360})
            page.wait_for_timeout(300)
            r["layout"]["740x360"] = layout(page)
            r["landscapeErrors"] = errors[:3]
            ctx.close()
            # the controls switched off in the menu: 🎮 stays in the shift and brings them back; ⛶ apart from it
            def off(page):
                a, b = (page.locator(q).bounding_box() for q in (".tbToggle:not(.fs)", ".tbToggle.fs"))
                r["apart"] = round(abs(b["x"] - a["x"]))
                page.tap(".tbToggle:not(.fs)")
            ctx, page, errors = shift(browser, port, args.line, (844, 390), True, off)
            way = {"off": not page.evaluate("document.body.classList.contains('touch')"), "toggle": page.is_visible(".tbToggle:not(.fs)")}
            way["factsOff"] = page.evaluate("import('/src/perf.js').then((m) => m.machine({ getContext() { throw 0; } }).controls)")
            if way["toggle"]:
                page.tap(".tbToggle:not(.fs)")
            way["back"] = page.evaluate("document.body.classList.contains('touch')") and page.is_visible("#touch button[data-k='p']")
            way["factsOn"] = page.evaluate("import('/src/perf.js').then((m) => m.machine({ getContext() { throw 0; } }).controls)")
            way["errors"] = errors[:3]
            r["wayBack"] = way
            ctx.close()
            # Safari on an iPhone, then started from the home screen; the manifest and its icons
            ctx, page, errors = menu(browser, port, args.line, SAFARI)
            r["safari"] = {"hint": page.is_visible("#fsAsk.home"), "text": page.text_content("#fsAsk span"),
                           "toggle": page.is_visible(".tbToggle.fs")}
            page.tap("#fsAsk button")
            r["safari"]["after"] = [page.is_visible("#fsAsk"), page.evaluate("localStorage.getItem('tram-fullscreen')")]
            r["safari"]["errors"] = errors[:3]
            ctx.close()
            ctx, page, errors = menu(browser, port, args.line, HOME)
            r["home"] = {"asked": page.is_visible("#fsAsk"), "toggle": page.is_visible(".tbToggle.fs"),
                         "fs": page.evaluate("document.body.classList.contains('fs')"), "errors": errors[:3]}
            r["manifest"] = page.evaluate("""async () => {
              const href = document.querySelector('link[rel=manifest]').href, m = await (await fetch(href)).json();
              const urls = [...m.icons.map((i) => new URL(i.src, href).href), document.querySelector('link[rel=apple-touch-icon]').href];
              const got = await Promise.all(urls.map(async (u) => { const x = await fetch(u); return [x.status, x.headers.get('content-type')]; }));
              return { display: m.display, orientation: m.orientation, icons: got };
            }""")
            ctx.close()
            r["mirror"] = {}
            for vp in ((1280, 720), (2560, 1440)):
                ctx, page, errors = shift(browser, port, args.line, vp, False)
                box = page.locator("#mirror").bounding_box()
                r["mirror"][f"{vp[0]}x{vp[1]}"] = [round(box["width"]), round(box["height"])]
                r.setdefault("deskButtons", []).append(page.is_visible("#touch button[data-k='w']"))
                r.setdefault("deskAsked", []).append(page.evaluate("!!document.getElementById('fsAsk')?.classList.contains('show')"))
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    if not r["buttons"]:
        fails.append("no on-screen controls on a phone")
    if r["doors"] != "closed" or r["notch"] != 2 or r["kmh"] <= 1:
        fails.append(f"the buttons did not drive the tram (doors {r['doors']}, notch {r['notch']}, {r['kmh']} km/h)")
    if r["held"] != -6 or r["released"] != -5:
        fails.append(f"emergency brake held {r['held']}, released {r['released']} (want -6, -5)")
    if r["orbit"] < 5:
        fails.append("a drag does not turn the outside view")
    if r["phoneErrors"]:
        fails.append(f"page errors: {r['phoneErrors']}")
    if any(r["deskButtons"]):
        fails.append("on-screen controls shown on a desktop")
    if not r["asked"] or r["noFull"] != [False, "0"]:
        fails.append(f"full screen: a phone not asked, or 'Not now' still went full screen ({r['noFull']})")
    if not r["askedL"] or not r["fullAgain"]:
        fails.append("full screen: 'Full screen' or the next start after leaving it did not enter it")
    if any(r["deskAsked"]):
        fails.append("full screen asked on a desktop")
    if r["portraitRow"] != 1:
        fails.append("in portrait the controller is no longer one row")
    for size, bad in r["layout"].items():
        if bad:
            fails.append(f"landscape {size}: {'; '.join(bad)}")
    wb = r["wayBack"]
    if wb != {"off": True, "toggle": True, "factsOff": False, "back": True, "factsOn": True, "errors": []}:
        fails.append(f"controls switched off on a phone: no way back in the shift, or the note's facts miss it: {wb}")
    if r["apart"] < 300:
        fails.append(f"⛶ only {r['apart']} px from 🎮")
    sf = r["safari"]
    if not sf["hint"] or "Add to Home Screen" not in (sf["text"] or "") or sf["toggle"] or sf["after"] != [False, "0"] or sf["errors"]:
        fails.append(f"Safari on an iPhone: the home-screen hint not shown once, or ⛶ offered: {sf}")
    if r["home"]["asked"] or r["home"]["toggle"] or not r["home"]["fs"] or r["home"]["errors"]:
        fails.append(f"started from the home screen: asked, ⛶ offered or not counted as full screen: {r['home']}")
    m = r["manifest"]
    if m["display"] != "fullscreen" or m["orientation"] != "landscape" or any(st != 200 or "image/png" not in (ct or "") for st, ct in m["icons"]):
        fails.append(f"the web manifest or its icons: {m}")
    if r["landscapeErrors"]:
        fails.append(f"page errors in landscape: {r['landscapeErrors']}")
    (w0, h0), (w1, h1) = r["mirror"].values()
    if not h1 > h0 * 1.5 or abs(w0 / h0 - 150 / 190) > 0.03 or abs(w1 / h1 - 150 / 190) > 0.03:
        fails.append(f"the mirror does not grow with the viewport at a fixed aspect: {r['mirror']}")
    if fails:
        sys.exit("; ".join(fails))
    print("touch: buttons drive the tram, emergency brake held and let go, outside view turns, mirror sized by the viewport, "
          "full screen asked once and entered on a start, the landscape layout, Safari's home screen, the manifest, the way back to the controls: pass")


if __name__ == "__main__":
    main()
