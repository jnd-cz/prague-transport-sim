"""The game's free cameras take the same mouse and keys as review mode (#342): python -P -E tools/test_free_camera.py [--line 37]
Inspect mode's orbit and fly on a paused game, then the outside view. Its own server on a free port. Review mode's
side is in tools/test_review.py."""
import argparse
import faulthandler
import math
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve  # noqa: E402
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

STATE = """(() => { const I = window.inspect, p = window.camera.position;
  return { yaw: I.yaw, pitch: I.pitch, flyYaw: I.flyYaw, flyPitch: I.flyPitch, x: p.x, y: p.y, z: p.z }; })()"""


class Quiet(serve.NoCache):
    def log_message(self, *args):
        pass


def main():
    faulthandler.dump_traceback_later(600, exit=True)  # (page.evaluate has no time limit)
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="37")
    a = ap.parse_args()
    server = serve.Server(("127.0.0.1", 0), lambda *x, **k: Quiet(*x, directory=serve.ROOT, **k))
    server.identity, server.rate, server.lan = None, 0, False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []

    def check(what, ok, got=None):
        print(("ok   " if ok else "FAIL ") + what + ("" if ok else f": {got}"))
        if not ok:
            fails.append(what)

    with sync_playwright() as p:
        b = gpu.launch(p)[0]
        page = b.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.server_address[1]}/index.html?line={a.line}&inspect", timeout=300000)
        page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
        page.click("#btnStart")
        page.wait_for_function("window.inspect && window.inspect.active", timeout=120000)
        page.evaluate("""() => { window.inspect.paused = true;
          window.addEventListener('contextmenu', (e) => { window.menuPrevented = e.defaultPrevented; }); }""")

        def step():
            page.wait_for_timeout(120)  # (the frame that applies it)
            return page.evaluate(STATE)

        def diff(s0, s1):
            return {k: s1[k] - s0[k] for k in s0}

        def drag(button="left", shift=False):
            s0 = step()
            if shift:
                page.keyboard.down("Shift")
            page.mouse.move(640, 400)
            page.mouse.down(button=button)
            page.mouse.move(700, 420, steps=4)
            page.mouse.up(button=button)
            if shift:
                page.keyboard.up("Shift")
            return diff(s0, step())

        def hold(key):
            s0 = step()
            page.keyboard.down(key)
            page.wait_for_timeout(250)
            page.keyboard.up(key)
            return diff(s0, step())

        def moved(d):
            return math.hypot(d["x"], d["y"], d["z"])

        # orbit: tied to the tram, so every button turns
        left, right = drag(), drag("right")
        check("orbit: a left drag to the right and down looks right and further down", left["yaw"] < 0 and left["pitch"] < 0, left)
        check("orbit: a right drag turns too", right["yaw"] < 0 and right["pitch"] < 0, right)
        q, e = hold("q"), hold("e")
        check("orbit: Q looks left, E right", q["yaw"] > 0 > e["yaw"], (q, e))
        up, down = hold("ArrowUp"), hold("ArrowDown")
        check("orbit: the up arrow looks up, the down arrow down", up["pitch"] > 0 > down["pitch"], (up, down))
        page.mouse.click(640, 400, button="right")
        check("no context menu in inspect mode", page.evaluate("window.menuPrevented") is True)

        # fly: free, so the right button moves it
        page.keyboard.press("c")
        step()
        left, right, shift = drag(), drag("right"), drag(shift=True)
        check("fly: a left drag looks right and further down, staying put", left["flyYaw"] < 0 and left["flyPitch"] < 0 and moved(left) == 0, left)
        check("fly: a right drag moves, not turning", moved(right) > 0 and right["flyYaw"] == 0 and right["flyPitch"] == 0, right)
        check("fly: a Shift-drag moves", moved(shift) > 0 and shift["flyYaw"] == 0, shift)
        # (the ground follows the mouse: to the right and down takes the camera left and forward, against its heading)
        yaw = page.evaluate("window.inspect.flyYaw")
        side = right["x"] * math.cos(yaw) - right["z"] * math.sin(yaw)
        ahead = -right["x"] * math.sin(yaw) - right["z"] * math.cos(yaw)
        check("fly: the ground follows the mouse", side < 0 and ahead > 0, (side, ahead))
        q, e = hold("q"), hold("ArrowRight")
        check("fly: Q looks left, the right arrow right", q["flyYaw"] > 0 > e["flyYaw"], (q, e))
        up = hold("ArrowUp")
        check("fly: the up arrow looks up", up["flyPitch"] > 0, up)
        check("fly: R goes up, W moves", hold("r")["y"] > 0 and moved(hold("w")) > 0)

        # the outside view
        page.keyboard.press("i")
        page.keyboard.press("v")
        page.wait_for_timeout(800)
        page.evaluate("window.game.paused = true")
        page.wait_for_timeout(300)
        s0 = page.evaluate("[camera.position.x, camera.position.z]")
        page.mouse.move(640, 400)
        page.mouse.down(button="right")
        page.mouse.move(790, 400, steps=8)
        page.mouse.up(button="right")
        page.wait_for_timeout(300)
        s1 = page.evaluate("[camera.position.x, camera.position.z]")
        check("outside view: a right drag turns it", math.hypot(s1[0] - s0[0], s1[1] - s0[1]) > 5, (s0, s1))
        page.evaluate("window.menuPrevented = null")
        page.mouse.click(640, 400, button="right")
        check("no context menu in the outside view", page.evaluate("window.menuPrevented") is True)
        check("no page errors", not errors, errors[:3])
        b.close()
    server.shutdown()
    print(f"{len(fails)} failed" if fails else "all passed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
