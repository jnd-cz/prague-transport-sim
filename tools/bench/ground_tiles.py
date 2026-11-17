# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ground's tiles along a drive (#30): a line loaded as a player loads it (no ?keepgeo), then the window moved along
its route every --step m (the camera over the route, the route ahead held: src/groundFile.js), each step waited for.
Per step: the tiles drawn in detail and the lookups held, their triangles and MB, the far ground's, the tiles loaded,
the workers' and the page thread's ms for them, a draw's ms after them (the new tiles' upload to the GPU happens there),
the tiles within the detail's reach of the camera not drawn in detail (`missing`) and those within the fog's end drawn
neither in detail nor far (`bare`): both must be 0. At the end every tile at once: what the page held before #30.

Usage: python -P -E tools/bench/ground_tiles.py [--lines 17,9] [--step 200] [--out reports/30/tiles.json]

Headless Chromium on the GPU (tools/gpu.py), its own server on a free port; waits its turn among the heavy jobs.
"""
import argparse
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

DRIVE = """async ({ step }) => {
  const { startShift } = await import('/tools/bench/shift.js');
  await startShift({ timeout: 120 }); // (the game, its camera and scene: a shift as the player starts it)
  const g = window.groundTiles, route = window.game.route, cam = window.camera, fog = window.scene.fog.far, R = g.reach(fog), out = [];
  g.last = Infinity; // (the frame loop's window off: the drive moves it)
  for (let s = 0; s <= route.length; s += step) {
    const p = route.at(s), pts = [[p.x, p.y]];
    cam.position.set(p.x, cam.position.y, -p.y);
    cam.updateMatrixWorld();
    for (let d = 0; d <= 1000; d += 100) { const q = route.at(Math.min(route.length, s + d)); pts.push([q.x, q.y]); }
    const was = { ...g.times }, t0 = performance.now();
    await g.update(pts, R);
    g.drain();
    const wait = performance.now() - t0, t1 = performance.now();
    window.renderer.render(window.scene, cam);
    const draw = performance.now() - t1, jobs = g.times.jobs - was.jobs;
    const missing = [...g.near([[p.x, p.y]], R)].filter((k) => !g.drawn.has(k)).length;
    const bare = [...g.near([[p.x, p.y]], fog)].filter((k) => !g.drawn.has(k) && !g.coarse.get(k)?.visible).length;
    out.push({ s, ...g.held(), jobs, bare, worker: (g.times.decode + g.times.lookup + g.times.meshes) - (was.decode + was.lookup + was.meshes),
      make: g.times.make - was.make, makeMax: g.times.makeMax, wait, draw: jobs ? draw : null, missing });
  }
  g.keep = true;
  await g.update([], 0);
  g.drain();
  return { steps: out, all: g.held(), times: g.times, km: route.length / 1000 };
}"""


def summary(r):
    st = r["steps"]
    q = lambda k: [x[k] for x in st if x[k] is not None]  # noqa: E731
    loads = sum(x["jobs"] for x in st[1:])
    per = [x["worker"] / x["jobs"] for x in st if x["jobs"]]
    make = [x["make"] / x["jobs"] for x in st if x["jobs"]]
    return {
        "tiles": r["all"]["tiles"], "km": round(r["km"], 1),
        "drawn": (round(statistics.mean(q("drawn")), 1), max(q("drawn"))),
        "lookups": (round(statistics.mean(q("lookups")), 1), max(q("lookups"))),
        "triangles M": (round(statistics.mean(q("triangles")) / 1e6, 2), round(max(q("triangles")) / 1e6, 2)),
        "mesh MB": (round(statistics.mean(q("meshMB"))), round(max(q("meshMB")))),
        "lookup MB": (round(statistics.mean(q("lookupMB"))), round(max(q("lookupMB")))),
        "far ground": {"tiles shown": (round(statistics.mean(q("coarseShown")), 1), max(q("coarseShown"))),
                       "triangles M": round(st[-1]["coarseTriangles"] / 1e6, 2), "MB": round(st[-1]["coarseMB"], 1)},
        "all tiles": {"triangles M": round(r["all"]["triangles"] / 1e6, 2), "mesh MB": round(r["all"]["meshMB"]),
                      "lookup MB": round(r["all"]["lookupMB"])},
        "loads per km": round(loads / r["km"], 1),
        "worker ms per tile": (round(statistics.median(per), 1), round(max(per), 1)) if per else None,
        "page ms per tile": (round(statistics.median(make), 1), round(r["times"]["makeMax"], 1)) if make else None,
        "draw ms after new tiles": (round(statistics.median(q("draw")), 1), round(max(q("draw")), 1)) if q("draw") else None,
        "missing": sum(x["missing"] for x in st), "bare": sum(x["bare"] for x in st),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lines", default="17")
    ap.add_argument("--step", type=float, default=200.0)
    ap.add_argument("--out", help="write the steps and the summary here (JSON)")
    a = ap.parse_args()
    from baseline_store import HeavyJob
    from playwright.sync_api import sync_playwright

    import gpu
    from headless import load_page, serve, stop_server
    out = {}
    with HeavyJob("ground tiles"):
        server, url = serve(0)
        try:
            with sync_playwright() as pw:
                browser = gpu.launch(pw)[0]
                for ln in [s.strip() for s in a.lines.split(",") if s.strip()]:
                    page, errors, load = load_page(browser, url, ln, 600, {"keepgeo": False})
                    if isinstance(load, dict):
                        raise SystemExit(f"line {ln}: the load failed: {load} {errors[:3]}")
                    r = page.evaluate(DRIVE, {"step": a.step})
                    page.close()
                    out[ln] = {"summary": summary(r), "steps": r["steps"]}
                    print(f"line {ln}: {json.dumps(out[ln]['summary'])}", flush=True)
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
