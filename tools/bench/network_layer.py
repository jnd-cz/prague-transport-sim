# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a shift's Start does with the network the build made (#658, data/lineN.network.json, tools/network.py): its time,
the ground's lookups it reads (and those of tiles the window does not hold: none), the lookups held, and the file's size.

A line loaded as a player loads it (the window drops the lookups past it once the load is done), a shift started from
the menu and timed; the lookups' reads during it counted by kind (src/groundFile.js GroundLookup: height, survey, kind,
bedOffSurvey, covered) and by whether the tile was held; the lookups held after it (count and MB,
GroundTiles.held()). The file's size raw, gzip and brotli, per part.

Usage: python -P -E tools/bench/network_layer.py [--lines 17,37] [--out reports/658/network.json]

Headless Chromium on the GPU (tools/gpu.py), its own server on a free port; waits its turn among the heavy jobs.
"""
import argparse
import faulthandler
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

MEASURE = """async () => {
  const g = window.groundTiles, lk = g.lookup, reads = {}, missed = {};
  const undo = ['height', 'survey', 'kind', 'bedOffSurvey', 'covered'].map((k) => {
    const f = lk[k];
    lk[k] = function (x, y, ...a) { reads[k] = (reads[k] || 0) + 1; if (!lk._at(x, y)) missed[k] = (missed[k] || 0) + 1; return f.call(this, x, y, ...a); };
    return () => { delete lk[k]; };
  });
  const { startShift } = await import('/tools/bench/shift.js');
  const t = performance.now();
  try { await startShift({ timeout: 300 }); } finally { for (const u of undo) u(); }
  const h = g.held();
  return { startMs: Math.round(performance.now() - t), reads, missed, lookups: h.lookups, tiles: h.tiles, lookupMB: Math.round(h.lookupMB * 10) / 10 };
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    ap.add_argument("--out", help="write the measurements here (JSON)")
    a = ap.parse_args()
    lines = [s.strip() for s in a.lines.split(",") if s.strip()]
    # (page.evaluate has no time limit: a promise that never settles would hang the run without a word)
    faulthandler.dump_traceback_later(900 * len(lines) + 600, exit=True)
    import brotli
    from baseline_store import HeavyJob
    from playwright.sync_api import sync_playwright

    import gpu
    from headless import load_page, serve, stop_server
    out = {}
    with HeavyJob("network layer"):
        server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                for ln in lines:
                    page, errors, load = load_page(browser, url, ln, 600, {"keepgeo": False})
                    if isinstance(load, dict):
                        raise SystemExit(f"line {ln}: the load failed: {load} {errors[:3]}")
                    r = page.evaluate(MEASURE)
                    page.close()
                    with open(os.path.join(ROOT, "data", f"line{ln}.network.json"), encoding="utf-8") as f:
                        net = json.load(f)
                    size = {}
                    for k, v in net.items():
                        if not isinstance(v, (list, dict)) or k in ("provenance",):
                            continue
                        b = json.dumps(v, separators=(",", ":")).encode()
                        size[k] = {"raw kB": round(len(b) / 1e3), "gzip kB": round(len(gzip.compress(b, 9)) / 1e3),
                                   "brotli kB": round(len(brotli.compress(b, quality=11)) / 1e3)}
                    size["all"] = {u: sum(v[u] for v in size.values()) for u in ("raw kB", "gzip kB", "brotli kB")}
                    out[ln] = {**r, "errors": errors[:3], "size": size}
                    print(f"line {ln}: {json.dumps(out[ln])}", flush=True)
                browser.close()
        finally:
            stop_server(server)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
        print(a.out)


if __name__ == "__main__":
    main()
