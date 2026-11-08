"""The diagnostic speed boards only with the debug overlay (#389): python -P -E tools/test_diagnostic_boards.py [--line 17]
(its own server on a free port).

On the line: the diagnostic boards (src/game.js _initSigns, a curve's own limit with no real sign) are hidden at the start
of a shift, shown after F8 and hidden after F8 again; none stands within 20 m of a real sign; the real D 1/2 signs stay
visible throughout.
"""
import argparse
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


# what is drawn: the diagnostic group's state and its boards, the real boards' visibility, and diagnostics beside real signs
STATE = r"""() => {
  const g = window.game, shown = (o) => { for (let p = o; p; p = p.parent) if (!p.visible) return false; return true; };
  const diag = g.diagBoards, boards = [], real = [];
  g.objects.traverse((o) => { if (o.userData.diagnostic) boards.push(o); else if (o.userData.sign) real.push(o); });
  const realAt = g.signBoards.filter((b) => b.kind !== 'diagnostic').map((b) => b.at ?? b.s);
  const beside = g.signBoards.filter((b) => b.kind === 'diagnostic' && realAt.some((r) => Math.abs(r - b.at) < 20));
  return {
    group: !!diag, diagnostic: boards.length, listed: g.signBoards.filter((b) => b.kind === 'diagnostic').length,
    inGroup: boards.every((o) => o.parent === diag), diagShown: boards.filter(shown).length,
    real: real.length, realShown: real.filter(shown).length, beside: beside.map((b) => [b.v, b.at]),
  };
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"(skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    r = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            page.click("#btnStart", no_wait_after=True)
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=120000)
            r["start"] = page.evaluate(STATE)
            page.keyboard.press("F8")
            r["f8"] = page.evaluate(STATE)
            page.keyboard.press("F8")
            r["f8again"] = page.evaluate(STATE)
            r["errors"] = errors[:3]
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False))
    s, on, off, fails = r["start"], r["f8"], r["f8again"], []
    if not s["group"] or not s["diagnostic"] or not s["inGroup"] or s["diagnostic"] != s["listed"]:
        fails.append(f"the diagnostic boards in their own group, as listed: {s}")
    if s["diagShown"]: fails.append(f"hidden at the start of a shift: {s['diagShown']} of {s['diagnostic']} shown")
    if on["diagShown"] != on["diagnostic"]: fails.append(f"shown after F8: {on['diagShown']} of {on['diagnostic']}")
    if off["diagShown"]: fails.append(f"hidden after F8 again: {off['diagShown']} shown")
    if s["beside"]: fails.append(f"none within 20 m of a real sign: {s['beside']}")
    for k, x in (("start", s), ("F8", on), ("F8 again", off)):
        if not x["real"] or x["realShown"] != x["real"]: fails.append(f"the real signs shown ({k}): {x['realShown']} of {x['real']}")
    fails += [f"page error: {e}" for e in r["errors"]]
    if fails:
        print("FAILED\n  " + "\n  ".join(fails))
        sys.exit(1)
    print(f"diagnostic boards: {s['diagnostic']} hidden, shown with F8, hidden again; none beside the {s['real']} real signs: pass")


if __name__ == "__main__":
    main()
