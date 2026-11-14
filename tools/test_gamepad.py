# SPDX-License-Identifier: AGPL-3.0-or-later
"""A gamepad drives a shift (#592): python -P -E tools/test_gamepad.py [--line 17]
(its own server on a free port). A standard-layout pad, played by a page script in place of navigator.getGamepads():
it is announced when it connects. A closes the doors. The right trigger half pressed sets drive step 3 and the tram
moves. Held just over a step's edge and eased back a little, the trigger keeps its step. The left trigger over it
brakes at step 5, and both released free the pedals. LB held is the emergency brake, and let go it is brake step 5. A
held D-pad ↑ repeats. A key pressed beside a pad at rest stays. Start pauses and resumes, and Y and
the D-pad's sides send their keys. The right stick turns the head in proportion, nothing in its dead zone. In advanced controls a trigger puts the pedal straight on its step's angle,
for drive once Y has released the parking brake (before it, a warning says so); the dead-man pedal counts as held while the pad is connected."""
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

# a pad the test sets through window.pad({ buttons: {i: value}, axes: [..] }); every key event is logged
PAD = """(() => {
  const state = { buttons: {}, axes: [0, 0, 0, 0] };
  const pad = () => ({ id: 'Test pad (STANDARD GAMEPAD)', index: 0, connected: true, mapping: 'standard', timestamp: performance.now(),
    axes: state.axes.slice(), buttons: Array.from({ length: 17 }, (_, i) => ({ value: state.buttons[i] || 0, pressed: (state.buttons[i] || 0) > 0.5, touched: !!state.buttons[i] })) });
  let on = false;
  navigator.getGamepads = () => [on ? pad() : null, null, null, null];
  window.pad = (s) => { Object.assign(state, s); if (!on) { on = true; const e = new Event('gamepadconnected'); e.gamepad = pad(); window.dispatchEvent(e); } };
  window.keys = [];
  window.addEventListener('keydown', (e) => window.keys.push('+' + e.key + (e.shiftKey && e.key !== 'Shift' ? '^' : '') + (e.repeat ? '*' : '')), true);
  window.addEventListener('keyup', (e) => window.keys.push('-' + e.key), true);
})();"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skip: data/line{args.line}.json missing (python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(600, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port, r = server.server_port, {}
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            ctx = browser.new_context(viewport={"width": 1280, "height": 720})
            ctx.add_init_script(PAD)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/?line={args.line}", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            ev = lambda js: page.evaluate(js)  # noqa: E731
            # (the pad is read once a frame: wait for a few)
            frames = lambda: ev("new Promise((ok) => { let n = 0; const f = () => (++n >= 4 ? ok() : requestAnimationFrame(f)); requestAnimationFrame(f); })")  # noqa: E731
            pad = lambda **s: (ev(f"window.pad({json.dumps(s)})"), frames())  # noqa: E731
            lever = lambda: ev("window.game.tram.eq.lever")  # noqa: E731
            step = lambda sec: ev(f"for (let i = 0; i < {int(sec / 0.05)}; i++) window.game.update(0.05, {{}})")  # noqa: E731
            pad(buttons={})
            r["announced"] = ev("document.body.textContent.includes('Test pad')")
            pad(buttons={0: 1})
            pad(buttons={})
            step(6)
            r["doors"] = ev("window.game.doorState")
            pad(buttons={7: 0.5})
            r["drive"] = lever()
            step(4)
            r["kmh"] = round(ev("window.game.tram.v") * 3.6, 1)
            pad(buttons={7: 0.27})
            r["edge"] = [lever()]
            pad(buttons={7: 0.23})
            r["edge"].append(lever())
            pad(buttons={7: 0.5, 6: 1})
            r["brake"] = lever()
            pad(buttons={})
            r["free"] = lever()
            pad(buttons={4: 1})
            r["emergency"] = [lever()]
            pad(buttons={})
            r["emergency"].append(lever())
            page.keyboard.press("Digit2")
            frames()
            r["keyBeside"] = lever()
            ev("window.keys.length = 0")
            pad(buttons={12: 1})
            page.wait_for_timeout(900)
            pad(buttons={})
            r["repeats"] = ev("window.keys.filter((k) => k === '+w*').length")
            ev("window.keys.length = 0")
            pad(buttons={9: 1})
            pad(buttons={})
            r["paused"] = [ev("window.game.paused")]
            pad(buttons={9: 1})
            pad(buttons={})
            r["paused"].append(ev("window.game.paused"))
            # the right stick: the head turned in proportion (0.575 is half way past the dead zone of 0.15)
            # (the head eases there: read once it holds still, 0.4 s apart)
            yaw = lambda: ev("new Promise((ok) => { let a = camera.rotation.y; const f = () => { const b = camera.rotation.y; if (Math.abs(b - a) < 0.001) ok(b); else { a = b; setTimeout(f, 400); } }; setTimeout(f, 400); })")  # noqa: E731
            page.keyboard.press("Shift+Digit5")  # (stopped: a moving tram turns the view itself)
            step(20)
            ev("window.keys.length = 0")
            r["lookStill"] = round(ev("window.game.tram.v"), 3)
            y0 = yaw()
            pad(axes=[0, 0, -0.575, 0])
            y1 = yaw()
            pad(axes=[0, 0, -1, 0])
            y2 = yaw()
            pad(axes=[0, 0, 0.1, 0])
            y3 = yaw()
            r["look"] = [round(y1 - y0, 2), round(y2 - y0, 2), round(y3 - y0, 2)]
            pad(buttons={3: 1})
            pad(buttons={})
            pad(buttons={14: 1})
            pad(buttons={})
            r["keys"] = ev("window.keys")
            pad(buttons={7: 0.1})  # (drive step 1: the dead-man pedal is needed)
            r["deadman"] = ev("window.game.opts.deadman = true, window.game.deadmanTimer = 0, new Promise((ok) => setTimeout(() => ok(window.game.deadmanTimer), 1500))")
            r["deadmanNotch"] = ev("window.game.tram.notch")
            pad(buttons={})
            r["errors"] = errors[:3]
            ctx.close()
            # advanced controls: the trigger puts the pedal on the step at once, drive once the ratchet is released (Y)
            ctx = browser.new_context(viewport={"width": 1280, "height": 720})
            ctx.add_init_script(PAD)
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{port}/?line={args.line}", timeout=180000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=180000)
            page.select_option("#optControls", "advanced")
            page.click("#btnStart")
            page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=60000)
            pedals = lambda: ev("[window.game.tram.eq.pedal.drive, window.game.tram.eq.pedal.brake]")  # noqa: E731
            a = r["advanced"] = {"mode": ev("window.game.tram.eq.mode")}
            pad(buttons={0: 1})
            pad(buttons={})
            step(6)
            pad(buttons={7: 0.5})
            a["parked"] = pedals()
            a["warned"] = ev("window.game.messages.some((m) => m.kind === 'warn' && m.text.includes('Y)'))")
            pad(buttons={})
            pad(buttons={3: 1})
            pad(buttons={})
            # (no game step between a trigger and the reading: the pedal is there at once)
            pad(buttons={7: 0.5})
            a["drive3"] = pedals()
            pad(buttons={7: 1})
            a["drive5"] = pedals()
            pad(buttons={})
            a["free"] = pedals()
            pad(buttons={6: 1})
            a["brake5"] = pedals()
            pad(buttons={6: 0.1})
            a["brake1"] = pedals()
            pad(buttons={})
            a["errors"] = errors[:3]
            ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False))
    fails = []
    if not r["announced"]:
        fails.append("the pad was not announced")
    if r["doors"] != "closed" or r["drive"] != 3 or r["kmh"] <= 1:
        fails.append(f"the pad did not drive the tram (doors {r['doors']}, step {r['drive']}, {r['kmh']} km/h)")
    if r["edge"] != [2, 2]:
        fails.append(f"a trigger eased back at a step's edge flickers: {r['edge']} (want [2, 2])")
    if r["brake"] != -5 or r["free"] != 0:
        fails.append(f"left trigger over the right: {r['brake']} (want -5); both released: {r['free']} (want 0)")
    if r["emergency"] != [-6, -5]:
        fails.append(f"emergency brake held, let go: {r['emergency']} (want [-6, -5])")
    if r["keyBeside"] != 2:
        fails.append(f"a key pressed beside the pad at rest gave {r['keyBeside']} (want 2)")
    if r["repeats"] < 2:
        fails.append(f"a held D-pad ↑ repeated {r['repeats']} times in 0.9 s")
    if r["paused"] != [True, False]:
        fails.append(f"Start did not pause and resume: {r['paused']}")
    want = ["+r", "-r", "+,", "-,"]
    if not (0.6 <= r["look"][0] <= 0.7 and 1.25 <= r["look"][1] <= 1.35 and abs(r["look"][2]) < 0.02):
        fails.append(f"the right stick at half, full and in its dead zone turned the head {r['look']} (want 0.65, 1.3, 0)")
    if r["keys"] != want:
        fails.append(f"Y, D-pad ←: {r['keys']} (want {want})")
    if r["deadman"] != 0 or r["deadmanNotch"] <= 0:
        fails.append(f"the dead-man pedal not held with a pad connected: its timer {r['deadman']} s on step {r['deadmanNotch']}")
    a = r["advanced"]
    want = {"mode": "advanced", "parked": [0, 0], "drive3": [21, 0], "drive5": [36, 0], "free": [0, 0], "brake5": [0, 23.5], "brake1": [0, 3.5]}
    if {k: a[k] for k in want} != want or not a["warned"] or a["errors"]:
        fails.append(f"advanced controls: the pedals {a} (want {want})")
    if r["errors"]:
        fails.append(f"page errors: {r['errors']}")
    if fails:
        sys.exit("; ".join(fails))
    print("gamepad: announced, doors, trigger steps with a margin, brake over drive, emergency brake, repeats, a key beside it, "
          "pause, parking brake, look, indicators, the dead-man held, advanced controls' pedals at once: pass")


if __name__ == "__main__":
    main()
