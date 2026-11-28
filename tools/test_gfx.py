# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the page draws (src/gfx.js, src/autoscale.js, #705): python -P -E tools/test_gfx.py [--line 17]

The automatic render scale's rule on made-up frames (no data needed):
- frames that keep the display's rate, and a few long ones among them, leave the scale alone;
- frames slow at the full scale and quick at 0.75 step once and stay;
- frames held to 30 a second whatever is drawn step once, come back and stay (the pixels were not the limit);
- frames slow at every scale step to the last one and stay;
- a pause between two slow windows starts the count anew.
The page (needs data/line<N>.json; skipped without it, and says so):
- draws without the logarithmic depth buffer, antialiased, at the full scale, the snow's code out of the materials'
  shaders until it snows;
- the menu's render scale halves the drawing buffer at once and is kept over a reload;
- the menu's antialiasing loads the page again without it;
- ?gfx=log,snowall,noaa,pr0.5 draws as asked, whatever the menu's settings;
- on a shift whose frames are held to 40 ms the automatic scale steps down, finds the frames no shorter, and
  comes back.
"""
import argparse
import faulthandler
import os
import sys

from playwright.sync_api import Error as PlaywrightError, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402
from shot import site  # noqa: E402
from test_perf import BLACK  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# frames fed to an AutoScale: per case, seconds of frames whose interval is a function of the scale and the frame's
# number (a pause: one interval of that many ms); what it chose and logged
RULE = """async () => {
  const { AutoScale } = await import('/src/autoscale.js');
  const feed = (a, t, seconds, dt) => {
    for (let end = t + seconds * 1000, i = 0; t < end; i++) { t += dt(a.scale, i); a.frame(t); }
    return t;
  };
  const one = (seconds, dt) => { const a = new AutoScale(); feed(a, 0, seconds, dt); return { scale: a.scale, held: a.held, log: a.log }; };
  const out = {};
  out.quick = one(60, () => 16.7);
  out.hitches = one(60, (s, i) => (i % 20 === 0 ? 100 : 16.7));           // 5 % of the frames long
  // (two display intervals for over a third of the frames, as the tester's GPU: 43.5 frames a second)
  out.helped = one(60, (s, i) => (s === 1 ? (i % 3 === 0 ? 33.3 : 16.7) : 16.7));
  out.capped = one(60, () => 33.3);
  out.slow = one(90, (s) => ({ 1: 60, 0.75: 40, 0.5: 25 })[s]);
  const a = new AutoScale();                                               // one slow window, a pause, one slow window
  let t = feed(a, 0, 5.5, () => 33.3);
  t += 5000; a.frame(t);
  feed(a, t, 5.5, () => 33.3);
  out.paused = { scale: a.scale, log: a.log };
  return out;
}"""

# every frame held to 40 ms, whatever is drawn (as tools/test_perf.py's)
SLOW = """(() => {
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => raf(() => { const end = performance.now() + 40; while (performance.now() < end); cb(performance.now()); });
})()"""

STATE = """() => {
  const gl = window.renderer.getContext(), mats = new Set();
  window.world.traverse((o) => { for (const m of [].concat(o.material || [])) if (m.userData?.weather) mats.add(m); });
  const keys = [...mats].map((m) => m.customProgramCacheKey());
  return { logDepth: window.renderer.capabilities.logarithmicDepthBuffer, aa: gl.getContextAttributes().antialias,
           buffer: [gl.drawingBufferWidth, gl.drawingBufferHeight], ratio: window.renderer.getPixelRatio(),
           scale: window.gfx.scale, fixed: window.gfx.fixed, select: document.getElementById('optScale').value,
           check: document.getElementById('optAA').checked, weathered: keys.length,
           snowless: keys.filter((k) => k.split('|')[0].endsWith('n')).length }; // (a landmark's key goes on: src/landmarks.js)
}"""


def rule(page, fails):
    r = page.evaluate(RULE)
    for name in ("quick", "hitches"):
        if r[name]["scale"] != 1 or r[name]["log"]:
            fails.append(f"{name} frames: {r[name]}")
    if r["helped"]["scale"] != 0.75 or [e["why"] for e in r["helped"]["log"]] != ["slow"]:
        fails.append(f"a step that helped: {r['helped']}")
    if r["capped"]["scale"] != 1 or not r["capped"]["held"] or [e["why"] for e in r["capped"]["log"]] != ["slow", "no faster: back"]:
        fails.append(f"frames held to 30 a second: {r['capped']}")
    if r["slow"]["scale"] != 0.5 or not r["slow"]["held"] or \
            [[e["from"], e["to"]] for e in r["slow"]["log"]] != [[1, 0.75], [0.75, 0.5], [0.5, 0.5]]:
        fails.append(f"slow at every scale: {r['slow']}")
    if r["paused"]["scale"] != 1 or r["paused"]["log"]:
        fails.append(f"a pause between two slow windows: {r['paused']}")


def menu(page, url, more=""):
    page.goto(f"{url}{more}", timeout=180000)
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden') && window.renderer && window.world",
                           timeout=180000)


def pages(context, url, line, fails):
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    at = f"{url}/?line={line}"
    menu(page, at)
    s = page.evaluate(STATE)
    if s["logDepth"] or not s["aa"] or s["buffer"] != [1280, 720] or s["scale"] != 1 or s["select"] != "auto" or not s["check"]:
        fails.append(f"the page as it loads: {s}")
    if not s["weathered"] or s["snowless"] != s["weathered"]:
        fails.append(f"dry: the snow's code in {s['weathered'] - s['snowless']} of {s['weathered']} weathered materials")
    # snow: every weathered material's key changes (it is compiled with the snow's code), and back
    # (the weather's uniform itself: the menu's choice is applied at a shift's start)
    page.evaluate("import('/src/weather.js').then((w) => { w.WEATHER_UNIFORMS.uSnow.value = 1; })")
    s = page.evaluate(STATE)
    if s["snowless"]:
        fails.append(f"snow: {s['snowless']} of {s['weathered']} weathered materials without the snow's code")
    page.evaluate("import('/src/weather.js').then((w) => { w.WEATHER_UNIFORMS.uSnow.value = 0; })")
    s = page.evaluate(STATE)
    if s["snowless"] != s["weathered"]:
        fails.append(f"dry again: the snow's code in {s['weathered'] - s['snowless']} of {s['weathered']} weathered materials")
    # the render scale: at once, and kept
    page.select_option("#optScale", "0.5")
    s = page.evaluate(STATE)
    if s["buffer"] != [640, 360] or s["scale"] != 0.5:
        fails.append(f"the menu's scale 50 %: {s}")
    menu(page, at)
    s = page.evaluate(STATE)
    if s["buffer"] != [640, 360] or s["select"] != "0.5":
        fails.append(f"the scale after a reload: {s}")
    # the address's switches over the menu's settings
    menu(page, at + "&gfx=log,snowall,noaa,pr0.5")
    s = page.evaluate(STATE)
    if not s["logDepth"] or s["aa"] or s["buffer"] != [640, 360] or s["ratio"] != 0.5 or not s["fixed"] or s["snowless"]:
        fails.append(f"?gfx=log,snowall,noaa,pr0.5: {s}")
    menu(page, at + "&gfx=pr1")
    s = page.evaluate(STATE)
    if s["buffer"] != [1280, 720] or s["scale"] != 1:
        fails.append(f"?gfx=pr1 with the menu's scale at 50 %: {s}")
    # the antialiasing: the page loads again without it
    menu(page, at)
    page.select_option("#optScale", "auto")
    with page.expect_navigation(timeout=180000):
        page.uncheck("#optAA")
    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden') && window.renderer && window.world",
                           timeout=180000)
    s = page.evaluate(STATE)
    if s["aa"] or s["check"] or s["buffer"] != [1280, 720]:
        fails.append(f"the menu's antialiasing off: {s}")
    # the automatic scale on a shift whose every frame is held to 40 ms: a step down draws 960 x 540, the frames are
    # no shorter for it, so the step is taken back and the scale stays
    page.evaluate(BLACK)  # (under SLOW's wait, so that it reads back right after the page's frame)
    page.evaluate(SLOW)
    page.check("#optAuto")
    page.click("#btnStart")
    try:
        page.wait_for_function("window.renderer.getContext().drawingBufferWidth === 960", timeout=60000)
        page.wait_for_function("window.gfx.auto.length === 2 && window.renderer.getContext().drawingBufferWidth === 1280", timeout=60000)
    except PlaywrightError:
        pass
    page.wait_for_timeout(300)  # (the frames after the step back)
    auto = page.evaluate("({ log: window.gfx.auto, scale: window.gfx.scale, black: window.blackFrames, drawn: window.drawnFrames })")
    if [e["why"] for e in auto["log"]] != ["slow", "no faster: back"] or auto["scale"] != 1:
        fails.append(f"the automatic scale on 40 ms frames: {auto}")
    # (a step resizes the canvas, which clears it: before the frame's draw, so that no frame is left black)
    if auto["black"] or not auto["drawn"] > 50:
        fails.append(f"the automatic scale's steps left {auto['black']} of {auto['drawn']} drawn frames black")
    if errors:
        fails.append(f"page errors: {errors}")
    page.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test
    fails, skipped = [], ""
    with sync_playwright() as pw, site(ROOT) as url:
        browser, _ = gpu.launch(pw, quiet=True)
        try:
            context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
            page = context.new_page()
            page.goto(f"{url}/src/autoscale.js")
            rule(page, fails)
            page.close()
            if os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
                pages(context, url, args.line, fails)
            else:
                skipped = f" (the page part skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)"
        finally:
            browser.close()
    faulthandler.cancel_dump_traceback_later()
    if fails:
        sys.exit("; ".join(fails))
    print(f"drawing settings: the automatic scale's rule, the menu's scale and antialiasing, the address's switches: pass{skipped}")


if __name__ == "__main__":
    main()
