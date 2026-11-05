"""The frame time and the draw calls with each tram model (tools/bench/frametime.js), in a headed Chromium.

Usage: python -P -E tools/frametime.py [--line 17] [--models detailed,classic,simple] [--frames 600] [--headless]

Its own server on a free port; for each model a fresh page at 1280 x 720 loads the line, starts the first
trip with that model, adds three more sets ahead and measures `--frames` frames with vsync off (so the
interval is what a frame costs, not the display's 60 Hz). Headed by default: headless Chromium draws in
software, so its times say nothing about a GPU (#205); `--headless` only checks that the bench runs. Run it
on a quiet machine, the window in front: it waits its turn among the heavy jobs (tools/baseline_store.py).
Prints a table and writes reports/frametime.json.
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


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def measure(line, models, frames, headless, warm=120):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    out = []
    try:
        with sync_playwright() as p:
            args = [] if headless else ["--disable-gpu-vsync", "--disable-frame-rate-limit"]
            browser = p.chromium.launch(headless=headless, args=args)
            for model in models:
                page = browser.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(f"{base}/?line={line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                r = page.evaluate("async (o) => { const { run } = await import('/tools/bench/frametime.js'); return await run(o); }",
                                  {"model": model, "frames": frames, "warm": warm})
                r["errors"] = errors[:3]
                out.append(r)
                page.close()
            browser.close()
    finally:
        server.shutdown()
    return out


def table(rows):
    lines = ["| model | frame median / p95 (ms) | fps | render CPU median / p95 (ms) | of it matrices (ms) | draw calls | triangles | nodes (scene / our set) | AI sets (m: level) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        sets = ", ".join(f"{s['far']}: {s['level']}" for s in r["sets"])
        lines.append(f"| {r['model']} ({r['kind']}) | {r['frameMedian']} / {r['frameP95']} | {r['fps']} | {r['renderMedian']} / {r['renderP95']} | "
                     f"{r.get('matrixMedian')} | {r.get('calls')} | {r.get('triangles'):,} | {r.get('nodes'):,} / {r.get('tramNodes')} | {sets} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--models", default="detailed,classic,simple")
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--headless", action="store_true", help="software drawing: checks the bench runs, no timing")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        sys.exit(f"no data/line{args.line}.json: python -I tools/snapshot.py data-fetch")
    sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
    from baseline_store import HeavyJob
    with HeavyJob("frametime"):  # (frame times need the machine to itself: it waits for the heavy jobs, #280)
        faulthandler.dump_traceback_later(1800, exit=True)  # page.evaluate has no time limit
        rows = measure(args.line, args.models.split(","), args.frames, args.headless)
        faulthandler.cancel_dump_traceback_later()
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "frametime.json"), "w", encoding="utf-8", newline="") as f:
        json.dump({"line": args.line, "headless": args.headless, "runs": rows}, f, indent=1)
    print(table(rows))
    for r in rows:
        if r["errors"]:
            print(f"{r['model']}: page errors {r['errors']}")


if __name__ == "__main__":
    main()
