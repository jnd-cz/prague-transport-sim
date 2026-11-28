# SPDX-License-Identifier: AGPL-3.0-or-later
"""The frame time and the draw calls with each tram model (tools/bench/frametime.js), in a headed Chromium.

Usage: python -P -E tools/frametime.py [--line 17] [--models t3h,t3,t3simple] [--fov 62,22.75] [--frames 600] [--headless]
                                        [--traffic 60] [--stop 3] [--params boxcars] [--ratio 1,1.75,6]
       python -P -E tools/frametime.py --models t3h,t3h:sample.t3h-blue   # a model wearing a livery (#529)

Its own server on a free port; for each model a fresh page at 1280 x 720 loads the line, starts the first
trip with that model, adds three more sets ahead and measures `--frames` frames with vsync off (so the
interval is what a frame costs, not the display's 60 Hz; the GPU column is its own time for the frame's draws,
where the browser has a timer: on a fast GPU the interval is the CPU's); `--fov` measures each model at each of these vertical fields
(the cab's 62°, the zoom key's 22.75°: #382). Headed by default: headless Chromium draws in
software, so its times say nothing about a GPU (#205); `--headless` only checks that the bench runs. Run it
on a quiet machine, the window in front: it waits its turn among the heavy jobs (tools/baseline_store.py).
Prints a table and writes reports/frametime.json. `--traffic` steps the traffic that many seconds first (its cars in the
streets, #250), `--stop` measures at that stop of the trip, `--params` adds to the page's address (`boxcars`: the box
cars instead of the street vehicles' models, to measure the models against them; `gfx=log`: a drawing switch of
src/gfx.js). `--ratio` measures at each of these pixel ratios of the renderer, set by the bench: 1 is the triangles'
and the draw calls' cost, 1.75 the page's cap (2240 x 1260 drawn), 6 (7680 x 4320) 36 times the fragments; without
it the page's own ratio.
A weak GPU is short of fragments, not triangles (#705), and a fast one shows their cost only where they are the
limit: on the Arc A770 a frame at 1 and at 1.75 takes the same 3 ms, the CPU's (2026-11-27). With two or more
ratios the fill cost is printed too: the GPU's ms per megapixel drawn, between the lowest ratio and the highest
(the frame interval's where the browser has no GPU timer). A run whose drawing buffer the browser made smaller
than asked draws a part of the picture: it is marked and left out of the fill cost.
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


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


OLD = {"detailed": "t3h", "classic": "t3", "simple": "t3simple"}  # (the models' names before #455)


def measure(line, models, frames, headless, warm=120, fovs=(None,), traffic=0, stop=0, params="", ratios=(None,)):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    out = []
    try:
        with sync_playwright() as p:
            # (headless on the GPU where there is one, as headed: SwiftShader's frame times say nothing of a player's, #411)
            if headless:
                browser = gpu.launch(p)[0]
            else:
                browser = p.chromium.launch(headless=False, args=["--disable-gpu-vsync", "--disable-frame-rate-limit"])
            for spec, fov, ratio in [(m, f, r) for m in models for f in fovs for r in ratios]:
                model, _, livery = spec.partition(":")
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(f"{base}/?line={line}" + "".join(f"&{q}" for q in params.split("&") if q), timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                r = page.evaluate("async (o) => { const { run } = await import('/tools/bench/frametime.js'); return await run(o); }",
                                  {"model": model, "frames": frames, "warm": warm, "fov": fov, "livery": livery or None, "traffic": traffic, "stop": stop, "ratio": ratio})
                r["errors"] = errors[:3]
                if livery:
                    r["model"] = f"{model}:{livery}"
                if params:
                    r["model"] += f" ?{params}"
                out.append(r)
                page.close()
            browser.close()
    finally:
        server.shutdown()
    return out


def table(rows):
    lines = ["| model | field (°) | pixel ratio | frame median / p95 (ms) | fps | GPU (ms) | render CPU median / p95 (ms) | of it matrices (ms) | draw calls | triangles | nodes (scene / our set) | AI sets (m: level) | cars (drawn near / far) | people (animated: full + middle / far) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sets = ", ".join(f"{s['far']}: {s['level']}" for s in r["sets"])
        c = r.get("cars")
        cars = f"{r.get('trafficCars')} ({c['near']} / {c['far']})" if c else f"{r.get('trafficCars')} (boxes)"
        p = r.get("people")
        people = f"{p.get('people')} ({p.get('full', 0)} + {p.get('middle', 0)} / {p.get('far')})" if p else "boxes"
        cut = "" if r.get("drawn") == r.get("canvas") else f" (buffer cut to {r['drawn'][0]} x {r['drawn'][1]})"
        lines.append(f"| {r['model']} ({r['kind']}) | {r.get('fov')} | {r.get('pixelRatio')}{cut} | {r['frameMedian']} / {r['frameP95']} | {r['fps']} | {r.get('gpuMs')} | {r['renderMedian']} / {r['renderP95']} | "
                     f"{r.get('matrixMedian')} | {r.get('calls')} | {r.get('triangles'):,} | {r.get('nodes'):,} / {r.get('tramNodes')} | {sets} | {cars} | {people} |")
    return "\n".join(lines)


def fill(rows):
    """[(model, field, low ratio, high ratio, ms per megapixel, of what)]: what a megapixel more costs a frame, per
    model and field, between its run at the lowest pixel ratio and the one at the highest: of the GPU's time, or of
    the frame interval where a run has none."""
    groups = {}
    for r in rows:
        if r.get("drawn") and r["drawn"] == r.get("canvas"):
            groups.setdefault((r["model"], r.get("fov")), []).append(r)
    out = []
    for (model, fov), g in groups.items():
        g.sort(key=lambda r: r["drawn"][0] * r["drawn"][1])
        lo, hi = g[0], g[-1]
        mpx = (hi["drawn"][0] * hi["drawn"][1] - lo["drawn"][0] * lo["drawn"][1]) / 1e6
        if mpx > 0:
            key = "gpuMs" if lo.get("gpuMs") is not None and hi.get("gpuMs") is not None else "frameMedian"
            out.append((model, fov, lo["pixelRatio"], hi["pixelRatio"], round((hi[key] - lo[key]) / mpx, 3), "GPU" if key == "gpuMs" else "frame"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--models", default="t3h,t3,t3simple", help="vehicle ids (assets/vehicles.json), each with :<livery id> to wear one; the old names detailed, classic, simple still work")
    ap.add_argument("--fov", default="", help="vertical fields to measure each model at, e.g. 62,22.75 (default: the camera's)")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--headless", action="store_true", help="headless, on the GPU where there is one (else SwiftShader): checks the bench runs")
    ap.add_argument("--traffic", type=float, default=0, help="seconds the traffic steps before the measurement (its cars in the streets)")
    ap.add_argument("--stop", type=int, default=0, help="the stop of the trip to measure at (its index in the menu)")
    ap.add_argument("--params", default="", help="added to the page's address, e.g. boxcars or gfx=log")
    ap.add_argument("--ratio", default="", help="the renderer's pixel ratios to measure each model at, e.g. 1,1.75,6 (default: the page's own, the display's up to 1.75; 6 makes the fragments the limit on a fast GPU)")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        sys.exit(f"no data/line{args.line}.json: python -I tools/snapshot.py data-fetch")
    sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
    from baseline_store import HeavyJob
    with HeavyJob("frametime"):  # (frame times need the machine to itself: it waits for the heavy jobs, #280)
        faulthandler.dump_traceback_later(1800, exit=True)  # page.evaluate has no time limit
        fovs = [float(f) for f in args.fov.split(",") if f] or [None]
        rows = measure(args.line, [OLD.get(m, m) for m in args.models.split(",")], args.frames, args.headless, fovs=fovs,
                       traffic=args.traffic, stop=args.stop, params=args.params, ratios=[float(r) for r in args.ratio.split(",") if r] or [None])
        faulthandler.cancel_dump_traceback_later()
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "frametime.json"), "w", encoding="utf-8", newline="") as f:
        json.dump({"line": args.line, "headless": args.headless, "runs": rows}, f, indent=1)
    print(table(rows))
    for model, fov, lo, hi, cost, what in fill(rows):
        print(f"fill cost, {model}, field {fov}: {cost} ms of {what} time per megapixel (pixel ratio {lo:g} to {hi:g})")
    for r in rows:
        if r["errors"]:
            print(f"{r['model']}: page errors {r['errors']}")


if __name__ == "__main__":
    main()
