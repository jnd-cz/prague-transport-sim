# SPDX-License-Identifier: AGPL-3.0-or-later
"""The trams' lamps in the game (#436), in headless Chromium: our driver's keys and the AI trams' own.

Usage: python -P -E tools/test_lamps.py [--line 17]

Needs the line's data (python -I tools/snapshot.py data-fetch); skips without it. Starts a shift with the built-in
model and checks: the line's junction turns and its stops where passengers cross a car lane are found; the
indicator keys (, . /) blink our tram's indicators on both cars and switch them off, L held shows the high beams'
glow and Shift+L latches it; an AI T3M placed by the traffic before such a stop brakes with its brake lamps lit at
the rear, indicates right and shows that stop on its side display, and before a junction turn indicates to its side.
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
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402

# a car's lamps lit by function (the colours as built, not dimmed: src/t3simple.js setLamps)
LIT = """(car) => {
  const lp = car.userData.lamps, C = lp.geo.attributes.color.array, on = [];
  for (const [fn, rs] of Object.entries(lp.byFn)) {
    let x = 0, y = 0;
    for (const r of rs) for (let i = r.start * 3; i < (r.start + r.count) * 3; i++) { x += C[i]; y += lp.lit[i]; }
    if (x / y > 0.9) on.push(fn);
  }
  return on.sort().join(' ');
}"""

# the lamps seen frame by frame over 1.5 s of the game's clock (by the clock, not the wall: on SwiftShader, where
# tools/gpu.py finds no GPU, a frame of the city takes about a second and moves the clock 0.1 s): every state the two
# cars showed
SEEN = """async () => {
  const lit = %s, seen = new Set(), t0 = performance.now(), c0 = window.game.clock;
  while (window.game.clock - c0 < 1.5 && performance.now() - t0 < 90000) {
    seen.add(window.tramModel.userData.cars.map(lit).join(' | '));
    await new Promise((r) => requestAnimationFrame(r));
  }
  return { indicate: window.game.lamps.indicate, seen: [...seen].sort(), clock: +(window.game.clock - c0).toFixed(2) };
}""" % LIT

AI = """async () => {
  const models = await import('/src/models.js');
  const { indicating } = await import('/src/indicators.js');
  const tr = window.traffic, g = window.game, way = tr.lampWays.ahead, lit = %s;
  const m = models.makeT3({ line: '9', cars: 2, detailed: false, variant: 'T3M', run: '801' });
  tr.group.add(m);
  const out = { turns: way.turns.length, kerb: way.kerb.length, stops: way.stops.length, ours: { turns: g.lamps.turns.length, kerb: g.lamps.kerb.length } };
  // braking 20 m before the first stop where passengers cross a car lane
  const k = way.kerb.find((x) => x > 200);
  if (k !== undefined) {
    const t = { mesh: m, s: k - 20, v: 3, vWas: 5, id: 1 };
    tr._placeTram(t, tr.route, t.s, () => 0, 0.1);
    out.kerbStop = { want: way.stops.find((st) => st.s > t.s - 2)?.name, next: m.userData.next,
      indicate: indicating(way.turns, way.kerb, t.s, t.v, true), lamps: m.userData.cars.map(lit), signals: m.userData.lampState.signals };
  }
  // running through a junction turn, 10 m before its switch
  const j = way.turns[0];
  if (j) {
    const t = { mesh: m, s: j.s0 + 40, v: 6, vWas: 6, id: 2 };
    tr._placeTram(t, tr.route, t.s, () => 0, 0.1);
    out.turn = { side: j.side, indicate: indicating(way.turns, way.kerb, t.s, t.v, false), braking: m.userData.lampState.braking };
  }
  tr.group.remove(m);
  models.disposeModel(m);
  return out;
}""" % LIT


# two frames drawn (the keys act on the next one)
FRAMES = "new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors, r = [], {}
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]  # (WebGL on the machine's GPU where it has one)
            page = browser.new_page(viewport={"width": 960, "height": 540})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            page.evaluate("document.getElementById('optAuto').checked = false")
            page.select_option("#optModel", "simple")
            page.evaluate("document.getElementById('btnStart').click()")
            page.wait_for_function("window.game && window.tramModel && window.traffic && window.game.lamps", timeout=60000)
            page.wait_for_timeout(1500)
            r["kind"] = page.evaluate("window.tramModel.userData.kind")
            r["rest"] = page.evaluate(SEEN)
            page.keyboard.press("Comma")
            r["left"] = page.evaluate(SEEN)
            page.keyboard.press("Comma")
            r["off"] = page.evaluate(SEEN)
            page.keyboard.press("Slash")
            r["hazard"] = page.evaluate(SEEN)
            page.keyboard.press("Slash")
            beams = "window.tramModel.userData.cars.map((c) => !!c.userData.beams?.visible)"
            page.keyboard.down("l")
            page.evaluate(FRAMES)
            r["flash"] = page.evaluate(beams)
            page.keyboard.up("l")
            page.evaluate(FRAMES)
            r["flashEnd"] = page.evaluate(beams)
            page.keyboard.press("Shift+L")
            page.evaluate(FRAMES)
            r["latched"] = page.evaluate(beams)
            r["ai"] = page.evaluate(AI)
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False))
    ai = r["ai"]
    # (standing at its first stop, held braked: the brake lamps lit; the rear red lamps on both cars)
    idle, on = "brake head pos tail | brake tail", "brake head indL pos tail | brake indL tail"
    want = {
        "our tram is the built-in model": r["kind"] == "simple",
        "in service: the front lamps on the leading car, the tail and brake lamps on both, nothing blinking": r["rest"]["seen"] == [idle],
        ", blinks the left indicators on both cars": r["left"]["indicate"] == "left" and r["left"]["seen"] == sorted([on, idle]),
        ", again switches them off": r["off"]["indicate"] is None and r["off"]["seen"] == [idle],
        "/ blinks all of them": r["hazard"]["indicate"] == "hazard" and "brake head indL indR pos tail | brake indL indR tail" in r["hazard"]["seen"],
        "L held: the high beams' glow on the leading car, gone when let go; Shift+L latches it":
        r["flash"] == [True, False] and r["flashEnd"] == [False, False] and r["latched"] == [True, False],
        f"the line's junction turns and kerb stops found ({ai['ours']})": ai["ours"]["turns"] > 0 and ai["ours"]["kerb"] > 0 and ai["turns"] == ai["ours"]["turns"],
        "an AI T3M braking into a kerb stop: the stop on its side display, the right indicators, the brake lamps on both cars":
        "kerbStop" in ai and ai["kerbStop"]["next"] == ai["kerbStop"]["want"] and ai["kerbStop"]["indicate"] == "right"
        and all("brake" in x for x in ai["kerbStop"]["lamps"]) and not ai["kerbStop"]["signals"].get("left"),
        "an AI tram before a junction turn indicates to its side": "turn" in ai and ai["turn"]["indicate"] == ai["turn"]["side"],
    }
    fails = [k for k, ok in want.items() if not ok] + [f"page error: {e}" for e in errors[:3]]
    if fails:
        print("FAILED\n  " + "\n  ".join(fails))
        sys.exit(1)
    print(f"lamps on line {args.line}: keys, high beams, AI trams' indicators, brake lamps and next stop: pass")


if __name__ == "__main__":
    main()
