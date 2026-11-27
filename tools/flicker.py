# SPDX-License-Identifier: AGPL-3.0-or-later
"""Flicker in motion: the same drive drawn two ways, the pixels that flick counted in each (#705).

    python -P -E tools/flicker.py --line 17 --s 5064 --b gfx=log            # as the page draws against ?gfx=log
    python -P -E tools/flicker.py --line 22 --s 6330 --view chase --b gfx=log --frames 40 --step 0.1
    python -P -E tools/flicker.py --line 17 --s 5064 --b gfx=log --near 0.001   # the calibration: a near plane
                                                    # 300 times nearer, so that depths at a distance must fight

A still picture cannot show depth fighting: two faces nearly at one depth swap from frame to frame as the camera
moves. So the tram is put --frames times --step metres further on (paused, no traffic, as tools/shot.py draws),
each frame is taken with the address's --a and with its --b, and per way the tool counts the flicks: a pixel that
differs from the frame before and from the frame after by more than FLICK of 255 in brightness while those two
differ by less than half of it (it changed and came back). An edge passing a pixel flicks too, in both ways alike,
so the two counts are read against each other; "only" is a way's flicks further than 1 px from any of the other's
in the same frame. Writes <out>/flicker-<line>-<s>-<view>.png: way a's frame in the middle of the drive, a's only
flicks of every frame red, b's only cyan.
"""
import argparse
import io
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu  # noqa: E402
from shot import HIDE, require, site  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FLICK = 24  # of 255 in brightness


def drive(browser, root, line, s, view, frames, step, params="", near=None, timeout=300):
    """[frames] of brightness (H x W, int16) and the middle frame's picture, the tram put step metres on per frame."""
    context = browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    context.add_init_script("""window.headless = true;
      let state = 158; Math.random = () => ((state = (Math.imul(state, 1664525) + 1013904223) >>> 0) / 4294967296);""")
    page, errors, deadline = context.new_page(), [], time.monotonic() + timeout
    page.on("pageerror", lambda e: errors.append(str(e)))
    left = lambda: max(1, (deadline - time.monotonic()) * 1000)  # noqa: E731
    try:
        with site(root) as url:
            more = "".join(f"&{q}" for q in params.split("&") if q)
            page.goto(f"{url}/?line={line}&seed=158&keepgeo{more}", timeout=left())
            page.wait_for_function("document.getElementById('loading')?.classList.contains('hidden') && "
                                   "!document.getElementById('menu')?.classList.contains('hidden')", timeout=left())
            page.select_option("#optWeather", "dry")
            page.select_option("#optObst", "off")
            if page.locator("#selStop").count():
                page.select_option("#selStop", index=0)
                page.select_option("#selTrip", index=0)
            page.click("#btnStart", timeout=left())
            page.wait_for_function("window.game && window.camera", timeout=left())
            require(page, "game")
            page.evaluate("""([s, last]) => {
              const g = window.game;
              if (s < 0 || last > g.route.length) throw new Error(`s ${s}..${last} outside route 0..${g.route.length}`);
              g.tram.s = s; g.tram.v = 0; g.tram.a = 0; g.paused = true;
              window.run.trafficView.dispose(); window.traffic.update = () => {};
            }""", [s, s + frames * step])
            if view == "chase":  # (as tools/shot.py: V before the pause, a zero wheel event snaps the orbit)
                page.evaluate("window.game.paused = false")
                page.keyboard.press("v")
                page.evaluate("window.game.paused = true; document.getElementById('gl').dispatchEvent(new WheelEvent('wheel', {deltaY:0}));")
            page.add_style_tag(content=HIDE)
            out, shown = [], None
            for i in range(frames):
                n = page.evaluate("""([s, near]) => {
                  window.game.tram.s = s;
                  if (near) { window.camera.near = near; window.camera.updateProjectionMatrix(); }
                  window.headless = false; return window.drawCount; }""", [s + i * step, near])
                page.wait_for_function("n => window.drawCount >= n + 2", arg=n, timeout=left())
                page.evaluate("window.headless = true")
                img = Image.open(io.BytesIO(page.screenshot(timeout=left()))).convert("RGB")
                if i == frames // 2:
                    shown = img
                out.append(np.asarray(img.convert("L"), dtype=np.int16))
            if errors:
                raise RuntimeError("; ".join(errors))
            return out, shown
    finally:
        context.close()


def flicks(frames):
    """[H x W bool] per inner frame: the pixel changed against the frame before and came back in the frame after."""
    out = []
    for a, b, c in zip(frames, frames[1:], frames[2:]):
        out.append((np.abs(b - a) > FLICK) & (np.abs(b - c) > FLICK) & (np.abs(c - a) < FLICK / 2))
    return out


def grown(m):
    """m with every set pixel's eight neighbours set."""
    p = np.pad(m, 1)
    h, w = m.shape
    return np.logical_or.reduce([p[y:y + h, x:x + w] for y in range(3) for x in range(3)])


def compare(a, b):
    """What two drives' frames say: per way the flicks a frame (mean), those only it has, and how the ways' pictures
    differ (the share of pixels over FLICK, mean and largest frame)."""
    fa, fb = flicks(a), flicks(b)
    only_a = [x & ~grown(y) for x, y in zip(fa, fb)]
    only_b = [y & ~grown(x) for x, y in zip(fa, fb)]
    differ = [float((np.abs(x - y) > FLICK).mean()) * 100 for x, y in zip(a, b)]
    n = max(1, len(fa))
    return {"flicks": [sum(int(x.sum()) for x in fa) / n, sum(int(x.sum()) for x in fb) / n],
            "only": [sum(int(x.sum()) for x in only_a) / n, sum(int(x.sum()) for x in only_b) / n],
            "differ": [sum(differ) / len(differ), max(differ)],
            "marks": [np.logical_or.reduce(only_a) if only_a else None, np.logical_or.reduce(only_b) if only_b else None]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", type=int, required=True)
    ap.add_argument("--s", type=float, required=True)
    ap.add_argument("--view", choices=("cab", "chase"), default="cab")
    ap.add_argument("--frames", type=int, default=30)
    ap.add_argument("--step", type=float, default=0.2, help="metres a frame (0.2: 43 km/h at 60 frames a second)")
    ap.add_argument("--a", default="", help="way a's address parameters (default none: as the page draws)")
    ap.add_argument("--b", default="gfx=log", help="way b's address parameters")
    ap.add_argument("--near", type=float, help="way a's near plane in m, to make depths fight (the calibration)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports/flicker")
    a = ap.parse_args(argv)
    with sync_playwright() as pw:
        browser, renderer = gpu.launch(pw)
        try:
            fa, shown = drive(browser, ROOT, a.line, a.s, a.view, a.frames, a.step, a.a, a.near)
            fb, shown_b = drive(browser, ROOT, a.line, a.s, a.view, a.frames, a.step, a.b)
        finally:
            browser.close()
    r = compare(fa, fb)
    a.out.mkdir(parents=True, exist_ok=True)
    pic = np.asarray(shown, dtype=np.uint8).copy()
    for marks, colour in zip(r["marks"], ((255, 0, 0), (0, 255, 255))):
        if marks is not None:
            pic[grown(marks)] = colour
    path = a.out / f"flicker-{a.line}-{a.s:g}-{a.view}{'-near' if a.near else ''}.png"
    Image.fromarray(pic).save(path)
    shown_b.save(path.with_name(path.stem + '-b.png'))  # (way b's middle frame, unmarked: what flicks there)
    name = lambda p, near=None: (p or "none") + (f", near {near:g} m" if near else "")  # noqa: E731
    print(f"line {a.line} s {a.s:g} {a.view}, {a.frames} frames of {a.step:g} m ({renderer})")
    print(f"  a ({name(a.a, a.near)}): {r['flicks'][0]:.1f} flicks a frame, {r['only'][0]:.1f} only here")
    print(f"  b ({name(a.b)}): {r['flicks'][1]:.1f} flicks a frame, {r['only'][1]:.1f} only here")
    print(f"  the two differ in {r['differ'][0]:.3f} % of pixels a frame (most {r['differ'][1]:.3f} %); {path}")
    return r


if __name__ == "__main__":
    main()
