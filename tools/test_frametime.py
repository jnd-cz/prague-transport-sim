"""tools/frametime.py: the bench runs for a model and reports what it measured (headless, a few frames).

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
from frametime import ROOT, measure  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"(skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    rows = measure(args.line, ["detailed", "simple"], frames=10, headless=True, warm=5)
    faulthandler.cancel_dump_traceback_later()
    fails = []
    hy, simple = rows
    if hy["kind"] != "hybrid" or simple["kind"] != "simple":
        fails.append(f"the models drawn: {hy['kind']}, {simple['kind']}")
    if [s["level"] for s in hy["sets"]] != ["full", "light", "light"]:
        fails.append(f"the hybrid sets' levels by distance: {hy['sets']}")
    for r in rows:
        if r["frames"] != 10 or not r.get("calls") or not r.get("triangles") or r["errors"]:
            fails.append(f"{r['model']}: {r}")
    if fails:
        sys.exit("; ".join(fails))
    print("frame-time bench: runs per model, the sets' levels, draw calls and triangles reported: pass")


if __name__ == "__main__":
    main()
