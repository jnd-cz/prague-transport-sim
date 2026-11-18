# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network a shift's Start builds from the survey (#658): its time and its size as data.

A line loaded as a player loads it, a shift started from the menu, then the network built again and timed: the traffic's
roads, lanes, footways, links, doors and signal bindings (src/traffic.js `Traffic`), and the game's platforms
(src/game.js `_buildPlatforms`). The survey's reads are counted during it (`classAt`, `classUnder`, `covered`,
`ground.surface`). The network is written out as it stands, plain JSON with positions in cm: a road's path and its fitted
kerbs, a lane's path, a footway's path and its links, a door, a lane's signal; its size raw, gzip and brotli, per part.

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

# (a built network as plain data, positions in cm: a road's path, width, fitted kerbs and median, the tracks' lateral
# positions; a lane's road, direction, junctions and path; a footway's path and links; a door; a lane's signal)
SERIALIZE = """(T) => {
  const cm = (v) => Math.round(v * 100);
  const pts = (p) => p.p.flatMap(([x, y]) => [cm(x), cm(y)]);
  const lanes = T.laneList ?? [], walks = T.walks, roads = T.roads, li = new Map(lanes.map((l, i) => [l, i])), wi = new Map(walks.map((w, i) => [w, i]));
  return {
    roads: roads.map((r) => ({ p: pts(r.path), w: r.w, lo: r.fitLo?.map(cm), hi: r.fitHi?.map(cm), med: r.fitMed?.map(cm), trk: r.trk?.map((v) => v && cm(v)) })),
    lanes: lanes.map((l) => ({ road: roads.indexOf(l.road), dir: l.dir, from: l.from, to: l.to, p: pts(l.path) })),
    walks: walks.map((w) => ({ p: pts(w.path), link: w.link ? 1 : 0, links: w.links?.map((e) => e.map((x) => [wi.get(x.walk), cm(x.s)])) })),
    doors: (T.doors ?? []).map((d) => [wi.get(d.walk), cm(d.s), cm(d.x), cm(d.y)]),
    lights: lanes.filter((l) => l.light).map((l) => [li.get(l), l.light.kind, l.light.head, cm(l.light.back ?? 0)]),
  };
}"""

MEASURE = """async () => {
  const { startShift } = await import('/tools/bench/shift.js'), serialize = SERIALIZE;
  let t = performance.now();
  await startShift({ timeout: 300 });
  const start = performance.now() - t;
  const g = window.game, tr = window.traffic, ground = tr.ground, dtm = ground.dtm, reads = {};
  const count = (o, k) => { if (!o?.[k]) return; const f = o[k]; reads[k] = 0; o[k] = function (...a) { reads[k]++; return f.apply(this, a); }; return () => { o[k] = f; }; };
  const undo = [count(dtm, 'classAt'), count(dtm, 'classUnder'), count(dtm, 'covered'), count(ground, 'surface')];
  t = performance.now();
  const T = new tr.constructor(window.scene, g.data, g.route, ground, g, tr.rand);
  const traffic = performance.now() - t;
  const trafficReads = { ...reads };
  for (const k in reads) reads[k] = 0;
  t = performance.now();
  g._buildPlatforms();
  const platforms = performance.now() - t;
  for (const u of undo) u?.();
  const parts = serialize(T), lanes = T.laneList ?? [], walks = T.walks;
  const n = { roads: T.roads.length, lanes: lanes.length, walks: walks.length, links: walks.filter((w) => w.link).length,
    doors: (T.doors ?? []).length, lights: parts.lights.length, platforms: g.platforms.length,
    lanePoints: lanes.reduce((a, l) => a + l.path.p.length, 0), walkPoints: walks.reduce((a, w) => a + w.path.p.length, 0) };
  T.dispose();
  const json = Object.fromEntries(Object.entries(parts).map(([k, v]) => [k, JSON.stringify(v)]));
  return { ms: { start, traffic, platforms }, reads: { traffic: trafficReads, platforms: { ...reads } }, n, json };
}""".replace("SERIALIZE", SERIALIZE)


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
                    size = {}
                    for k, s in r.pop("json").items():
                        b = s.encode()
                        size[k] = {"raw kB": round(len(b) / 1e3), "gzip kB": round(len(gzip.compress(b, 9)) / 1e3),
                                   "brotli kB": round(len(brotli.compress(b, quality=11)) / 1e3)}
                    size["all"] = {u: sum(v[u] for v in size.values()) for u in ("raw kB", "gzip kB", "brotli kB")}
                    r["ms"] = {k: round(v) for k, v in r["ms"].items()}
                    out[ln] = {**r, "size": size}
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
