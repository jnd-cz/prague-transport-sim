# SPDX-License-Identifier: AGPL-3.0-or-later
"""On-screen controls and the viewport-sized mirror (#79): python -P -E tools/test_touch.py [--line 17]
(its own server on a free port). On a phone (390 x 844, touch) a shift is driven by the buttons only:
doors closed, ▲ touched a step while the finger is down, ▲ held steps the lever on and the tram moves, let go the lever is
on 0 (#837), S held the same, the emergency brake held and let go, and let go with S held (brake step 5); the outside view turns by a
drag. On desktops the buttons stay hidden and the mirror frame grows with the viewport, its aspect fixed.
Full screen (#485): a phone asks once; "Not now" keeps a start in the page, "Full screen" enters it and so does each later
start after leaving it; a desktop isn't asked. In landscape (844 x 390, 740 x 360) the controller is a column at the right
(top to bottom: power, 0, brake, STOP), the other buttons at the left, the dashboard between them, no button over another
or off the screen; in portrait the controller stays a row. Safari on an iPhone (no Fullscreen API, played here by a page
script) is told once how to add the game to the home screen; started from there (display-mode standalone, also played)
it asks nothing and counts as full screen; the web manifest and the icons it names are served. A phone whose controls
were switched off keeps 🎮 in the shift, which brings them back; ⛶ stands apart from 🎮; a note's machine facts say
whether the controls were on. Paused in a shift (#691), the pause panel has ⛶, which enters full screen and leaves it, its
buttons on the screen and clear of the on-screen buttons, in portrait and in landscape."""
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
# (a desktop browser that reports a coarse pointer without a touch screen, as the Firefox of #675's note)
COARSE = """const mm = window.matchMedia.bind(window);
window.matchMedia = (q) => /pointer: coarse/.test(q) ? { matches: true, media: q, addEventListener() {}, removeEventListener() {} } : mm(q);"""
# (switched on with 🎮 once, on a desktop)
STORED = "localStorage.setItem('tram-touch', '1');"
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


def paused(page):
    """Paused by II: what's wrong with the pause panel's place, [] when nothing."""
    page.tap("#touch button[data-k='p']")
    page.wait_for_selector("#pausePanel.show", timeout=10000)
    return page.evaluate("""() => {
      const box = (e) => e.getBoundingClientRect(), bad = [];
      const touch = [...document.querySelectorAll('#touch button')].filter((e) => e.offsetParent);
      for (const b of document.querySelectorAll('#pausePanel button')) {
        const r = box(b);
        if (r.left < 0 || r.top < 0 || r.right > innerWidth + 0.5 || r.bottom > innerHeight + 0.5) bad.push(`${b.id} off the screen`);
        for (const o of touch.map(box)) if (r.left < o.right - 0.5 && o.left < r.right - 0.5 && r.top < o.bottom - 0.5 && o.top < r.bottom - 0.5) bad.push(`${b.id} under a button`);
      }
      return bad;
    }""")


def shift(browser, port, line, vp, mobile, before=None, script=None):
    ctx = browser.new_context(viewport={"width": vp[0], "height": vp[1]}, is_mobile=mobile, has_touch=mobile)
    if script:
        ctx.add_init_script(script)
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
            lever = "window.game.tram.eq.lever"  # (arcade: the lever; the pedals follow on the next step)
            # ▲ touched: a step while the finger is down, 0 once it lifts; held: on a step each 0.5 s; let go, 0 as after N (#837)
            drive = page.locator("#touch button[data-k='w']").bounding_box()
            page.mouse.move(drive["x"] + 20, drive["y"] + 20)
            page.mouse.down()
            r["tap"] = [page.evaluate(lever)]
            page.mouse.up()
            r["tap"].append(page.evaluate(lever))
            page.mouse.down()
            step(1.2)
            r["notch"] = page.evaluate(lever)
            step(2)
            page.mouse.up()
            r["back"] = page.evaluate(lever)
            step(3)
            r["kmh"] = round(page.evaluate("window.game.tram.v") * 3.6, 1)
            # the keyboard's S the same: a step at once, the key's repeat no step of its own, held on, let go 0
            page.keyboard.down("s")
            page.keyboard.down("s")  # (held: Playwright sends it as a repeat)
            r["key"] = [page.evaluate(lever)]
            step(1.2)
            r["key"].append(page.evaluate(lever))
            page.keyboard.up("s")
            r["key"].append(page.evaluate(lever))
            # the emergency brake: held, then let go (0, as any let go of the lever in the Simple controls)
            stop = page.locator("#touch button[data-k='space']").bounding_box()
            page.mouse.move(stop["x"] + 20, stop["y"] + 20)
            page.mouse.down()
            r["held"] = page.evaluate("window.game.tram.eq.lever")
            page.mouse.up()
            r["released"] = page.evaluate("window.game.tram.eq.lever")
            # brake held while the emergency stop is let go: brake step 5, until brake is let go too (the user, 2026-11-23)
            page.keyboard.down("Space")
            page.keyboard.down("s")
            r["stopBrake"] = [page.evaluate(lever)]
            page.keyboard.up("Space")
            r["stopBrake"].append(page.evaluate(lever))
            page.keyboard.up("s")
            r["stopBrake"].append(page.evaluate(lever))
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
            # ⛶ on the pause panel (#691): in, then out
            r["pause"] = {"390x844": paused(page)}
            fs = {"label": page.text_content("#btnFs")}
            page.tap("#btnFs")
            page.wait_for_function(FULL, timeout=5000)
            fs["in"], fs["leave"] = page.evaluate(FULL), page.text_content("#btnFs")
            page.tap("#btnFs")
            page.wait_for_function("!" + FULL, timeout=5000)
            fs["out"] = not page.evaluate(FULL)
            r["pauseFs"] = fs
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
            r["pause"]["740x360"] = paused(page)
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
            # a desktop reporting a coarse pointer without touch (#675): hidden at load, ⛶ in the menu changes nothing;
            # one switched on with 🎮 once: shown, and the menu's 🎮 says so
            seen = {}
            def full(page):
                seen["menu"] = [page.evaluate("document.body.classList.contains('touch')"), page.evaluate("document.querySelector('.tbToggle:not(.fs)').classList.contains('on')")]
                page.click(".tbToggle.fs")
                page.wait_for_timeout(300)
                seen["afterFull"] = page.evaluate("document.body.classList.contains('touch')")
            ctx, page, errors = shift(browser, port, args.line, (1699, 1016), False, full, COARSE)
            r["deskCoarse"] = {**seen, "shift": page.is_visible("#touch button[data-k='w']"), "errors": errors[:3]}
            ctx.close()
            def menu_on(page):
                seen["stored"] = page.evaluate("document.querySelector('.tbToggle:not(.fs)').classList.contains('on')")
            ctx, page, errors = shift(browser, port, args.line, (1280, 720), False, menu_on, STORED)
            r["deskStored"] = {"marked": seen["stored"], "shift": page.is_visible("#touch button[data-k='w']"), "errors": errors[:3]}
            ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    if not r["buttons"]:
        fails.append("no on-screen controls on a phone")
    if r["doors"] != "closed" or r["notch"] < 3 or r["kmh"] <= 1:
        fails.append(f"the buttons did not drive the tram (doors {r['doors']}, ▲ held 1.2 s: lever {r['notch']}, {r['kmh']} km/h)")
    if r["tap"] != [1, 0] or r["back"] != 0:
        fails.append(f"the sprung lever: touched and lifted {r['tap']} (want [1, 0]), let go {r['back']} (want 0)")
    if r["key"][0] != -1 or not -5 <= r["key"][1] <= -3 or r["key"][2] != 0:
        fails.append(f"S held, its repeat, 1.2 s on, let go: lever {r['key']} (want -1, -3 to -5, 0)")
    if r["held"] != -6 or r["released"] != 0:
        fails.append(f"emergency brake held {r['held']}, released {r['released']} (want -6, 0)")
    if r["stopBrake"] != [-6, -5, 0]:
        fails.append(f"Space and S held, Space let go, S let go: lever {r['stopBrake']} (want [-6, -5, 0])")
    if r["orbit"] < 5:
        fails.append("a drag does not turn the outside view")
    if r["phoneErrors"]:
        fails.append(f"page errors: {r['phoneErrors']}")
    if any(r["deskButtons"]):
        fails.append("on-screen controls shown on a desktop")
    if r["deskCoarse"] != {"menu": [False, False], "afterFull": False, "shift": False, "errors": []}:
        fails.append(f"a desktop reporting a coarse pointer without touch: controls shown, or changed by ⛶ (#675): {r['deskCoarse']}")
    if r["deskStored"] != {"marked": True, "shift": True, "errors": []}:
        fails.append(f"a desktop with the controls switched on: not shown, or the menu's 🎮 does not say so: {r['deskStored']}")
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
    for size, bad in r["pause"].items():
        if bad:
            fails.append(f"pause panel at {size}: {'; '.join(bad)}")
    pf = r["pauseFs"]
    if not (pf["label"].startswith("⛶") and pf["in"] and pf["out"] and pf["leave"] != pf["label"]):
        fails.append(f"⛶ on the pause panel did not enter and leave full screen, or its label stays: {pf}")
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
