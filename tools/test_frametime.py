# SPDX-License-Identifier: AGPL-3.0-or-later
"""tools/frametime.py: the bench runs for a model and reports what it measured (headless, a few frames), also at the
zoom key's narrower field (#382), at a pixel ratio of its own and with the page's drawing switches (#705).

Usage: python -P -E tools/test_frametime.py [--line 17]

Needs data/line<N>.json (python -I tools/snapshot.py data-fetch); skips without it. Headless draws in
software, so this checks the bench, not the times. (A browser test: frametime.measure launches Chromium
through sync_playwright.)
"""
import argparse
import faulthandler
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frametime import ROOT, fill, measure  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"(skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    # (the models by their registry names: "detailed" and "simple" are their names before #455, which the menu no longer
    # offers, and the bench waited for a model never picked)
    rows = measure(args.line, ["t3h", "t3simple"], frames=10, headless=True, warm=5)
    # (the zoomed run at the bench's own pixel ratio too, #705)
    zoomed = measure(args.line, ["t3simple"], frames=10, headless=True, warm=5, fovs=[22.75], ratios=[2])[0]
    # (every drawing switch of src/gfx.js at once: the page draws at its cap of the pixel ratio, with no page error)
    switched = measure(args.line, ["t3simple"], frames=10, headless=True, warm=5, params="gfx=nolog,snowif,front,noaa,pr0.5")[0]
    faulthandler.cancel_dump_traceback_later()
    fails = []
    hy, simple = rows
    if simple["pixelRatio"] != 1 or simple["drawn"] != [1280, 720]:
        fails.append(f"the page's own pixel ratio: {simple['pixelRatio']}, {simple['drawn']} drawn")
    if zoomed["pixelRatio"] != 2 or zoomed["drawn"] != [2560, 1440] or zoomed["canvas"] != zoomed["drawn"]:
        fails.append(f"--ratio 2: {zoomed['pixelRatio']}, {zoomed['drawn']} drawn, the canvas {zoomed['canvas']}")
    if switched["pixelRatio"] != 0.5 or switched["drawn"] != [640, 360] or switched["frames"] != 10 or switched["errors"]:
        fails.append(f"the switches with pr0.5: {switched['pixelRatio']}, {switched['drawn']} drawn, {switched['errors']}")
    # the fill cost: between the lowest ratio and the highest, of the GPU's time; a run whose buffer was cut is left out
    row = {"model": "m", "fov": 62, "frameMedian": 3}
    cost = fill([{**row, "pixelRatio": 1, "drawn": [1000, 1000], "canvas": [1000, 1000], "gpuMs": 2},
                 {**row, "pixelRatio": 2, "drawn": [2000, 2000], "canvas": [2000, 2000], "gpuMs": 5},
                 {**row, "pixelRatio": 4, "drawn": [3000, 3000], "canvas": [4000, 4000], "gpuMs": 50}])
    if cost != [("m", 62, 1, 2, 1.0, "GPU")]:
        fails.append(f"the fill cost of 3 ms over 3 megapixels: {cost}")
    if simple["fov"] != 62 or zoomed["fov"] != 22.75:
        fails.append(f"the fields measured: {simple['fov']}, {zoomed['fov']}")
    if not zoomed.get("calls") or zoomed["calls"] > simple["calls"]:
        fails.append(f"a narrower field draws no more: {zoomed.get('calls')} calls zoomed, {simple['calls']} not")
    if hy["kind"] != "rigged" or simple["kind"] != "simple":  # (the hybrid is a rigged glTF since #467)
        fails.append(f"the models drawn: {hy['kind']}, {simple['kind']}")
    if [s["level"] for s in hy["sets"]] != ["full", "light", "light"]:
        fails.append(f"the hybrid sets' levels by distance: {hy['sets']}")
    for r in rows:
        if r["frames"] != 10 or not r.get("calls") or not r.get("triangles") or r["errors"]:
            fails.append(f"{r['model']}: {r}")
    if fails:
        sys.exit("; ".join(fails))
    print(f"frame-time bench: runs per model, the sets' levels, draw calls and triangles reported; zoomed {zoomed['calls']} calls"
          f" against {simple['calls']}: pass")


if __name__ == "__main__":
    main()
