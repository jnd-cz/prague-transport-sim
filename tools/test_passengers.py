# SPDX-License-Identifier: AGPL-3.0-or-later
"""The passengers' cabin and boarding logic (#249 step 1): python -P -E tools/test_passengers.py (its own server on a free port).

On the game's hybrid T3 (assets/t3h/tatra-t3-hybrid-nc.glb), in a page: the passenger lab's preparation (tools/cabin/)
finds the 24 seats, the three doors with three entry levels each and the cab's exclusion, tied to the file's SHA-256; its
packings have no overlapping body outlines but the dense rows (the lab's nominal-110 stress, 53 pairs); the lab's timing
scenarios (tools/cabin/passenger-timing.js: every packing filled and emptied, 10 out / 10 in, both exit policies, with its
checks: no place taken twice, counts conserved, both streams of every door used together, doorway places last in and
first out) pass and give the lab's recorded times (tests/passenger-timing.json of street-life-boarding v14, revision 10),
so the modules brought into src/passengers/ work as they did there. A short search (tools/cabin/packing-search.js) gives
a packing with no overlaps and at least the lab's adaptive count, the same twice for one seed.
"""
import faulthandler
import functools
import http.server
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the lab's recorded times (simulation seconds), tests/passenger-timing.json, revision 10
LAB = {"aligned": {"full": {"boardingDoorClear": 35.325, "boardingSettled": 43.525, "alightingDoorClear": 45.075, "alightingRouteComplete": 50.125}, "mixed": {"tenOutDoorClear": 10.2, "exchangeComplete": 21.475, "lastIncomingDoorClear": 16.525, "lastOutgoingRouteComplete": 15.25}},
       "staggered": {"full": {"boardingDoorClear": 30.525, "boardingSettled": 37.825, "alightingDoorClear": 44.525, "alightingRouteComplete": 49.575}, "mixed": {"tenOutDoorClear": 10.2, "exchangeComplete": 21.475, "lastIncomingDoorClear": 16.525, "lastOutgoingRouteComplete": 15.25}},
       "dense": {"full": {"boardingDoorClear": 40.2, "boardingSettled": 48.125, "alightingDoorClear": 56.075, "alightingRouteComplete": 61.125}, "mixed": {"tenOutDoorClear": 10.75, "exchangeComplete": 21.675, "lastIncomingDoorClear": 17.075, "lastOutgoingRouteComplete": 15.8}},
       "adaptive": {"full": {"boardingDoorClear": 34.275, "boardingSettled": 45.55, "alightingDoorClear": 46.25, "alightingRouteComplete": 51.3}, "mixed": {"tenOutDoorClear": 10.65, "exchangeComplete": 21.25, "lastIncomingDoorClear": 16.975, "lastOutgoingRouteComplete": 15.7}},
       "loose": {"full": {"boardingDoorClear": 29.475, "boardingSettled": 41.425, "alightingDoorClear": 41.975, "alightingRouteComplete": 47.025}, "mixed": {"tenOutDoorClear": 10.75, "exchangeComplete": 21.4, "lastIncomingDoorClear": 17.075, "lastOutgoingRouteComplete": 15.8}}}

PAGE = """async () => {
  const bytes = async (u) => (await fetch(u)).arrayBuffer();
  const hex = async (b) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map((x) => x.toString(16).padStart(2, '0')).join('');
  const { input } = await import('/tools/cabin/body-footprint.js');
  const { prepareLayout } = await import('/tools/cabin/prepare-layout.js');
  const { prepareFloor } = await import('/tools/cabin/prepare-floor.js');
  const { passengerTiming } = await import('/tools/cabin/passenger-timing.js');
  const { convexOverlap } = await import('/src/passengers/packing-geometry.js');
  const m = await bytes('/assets/t3h/tatra-t3-hybrid-nc.glb'), p = await bytes('/assets/people/person-near.glb'), sha = await hex(m);
  input.person = p; input.personSha = await hex(p);
  const { layout } = await prepareLayout(m, sha, 't3h');
  const out = { sha, layoutSha: layout.assetSha256, seats: layout.seats.length, doors: layout.doors.map((d) => [d.id, d.entryLevels.length]),
    cab: layout.exclusions.map((e) => e.id) };
  const opts = { packings: [{ search: { id: 'search', moves: 150, seed: 7 } }, { search: { id: 'again', moves: 150, seed: 7 } }] };
  const { files } = await prepareFloor(layout, m, sha, opts);
  const L = files['t3-cabin-layout.json'];
  out.packings = Object.fromEntries(L.standing.configurations.map((c) => {
    let pairs = 0;
    for (let i = 0; i < c.places.length; i++) for (let j = i + 1; j < c.places.length; j++) if (convexOverlap(c.places[i].footprintWorld, c.places[j].footprintWorld)) pairs++;
    return [c.id, { count: c.places.length, pairs, cells: c.places.map((q) => `${q.x},${q.z},${q.heading.toFixed(4)}`).join(';') }];
  }));
  // (the lab's scenarios on its own five packings: the two searches are left out, the lab recorded none for them)
  const lab = { ...L, standing: { ...L.standing, configurations: L.standing.configurations.filter((c) => !['search', 'again'].includes(c.id)) } };
  try {
    const { result } = passengerTiming(lab, null);
    out.timings = Object.fromEntries(Object.entries(result.configurations).map(([k, v]) => [k, { full: v.full.timings, mixed: v.mixed.timings }]));
  } catch (e) { out.failed = String(e); }
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def importmap():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    return re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)


def main():
    faulthandler.dump_traceback_later(900, exit=True)  # (page.evaluate has no time limit of its own)
    import hashlib
    sha = hashlib.sha256(open(os.path.join(ROOT, "assets", "t3h", "tatra-t3-hybrid-nc.glb"), "rb").read()).hexdigest()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    fails = []
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__passengers.html", lambda r: r.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__passengers.html")
            page.set_default_timeout(800000)
            r = page.evaluate(PAGE)
            browser.close()
            if errors:
                fails.append(f"page errors: {errors[:3]}")
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    want = {
        "the layout tied to the GLB's SHA-256": r["sha"] == sha and r["layoutSha"] == sha,
        "24 seats": r["seats"] == 24,
        "3 doors, 3 entry levels each": r["doors"] == [["Front", 3], ["Middle", 3], ["Rear", 3]],
        "the cab excluded": r["cab"] == ["driver-cab"],
        "the lab's packings: 60 / 59 / 86 / 70 / 58 standing": [r["packings"][k]["count"] for k in ("aligned", "staggered", "dense", "adaptive", "loose")] == [60, 59, 86, 70, 58],
        "no overlapping outlines but the dense rows' 53": all(v["pairs"] == 0 for k, v in r["packings"].items() if k != "dense") and r["packings"]["dense"]["pairs"] == 53,
        "the search: at least the adaptive count": r["packings"]["search"]["count"] >= r["packings"]["adaptive"]["count"],
        "the search: one seed, one packing": r["packings"]["search"]["cells"] == r["packings"]["again"]["cells"],
        "the lab's scenarios pass (its checks)": "failed" not in r,
    }
    fails += [k for k, ok in want.items() if not ok]
    if "failed" in r:
        fails.append(r["failed"][:300])
    else:
        moved = [(k, s, t, LAB[k][s][t], round(r["timings"][k][s][t], 4)) for k in LAB for s in LAB[k] for t in LAB[k][s]
                 if abs(LAB[k][s][t] - r["timings"][k][s][t]) > 1e-3]
        if moved:
            fails.append(f"times differ from the lab's: {moved[:4]}")
    print({k: v["count"] for k, v in r["packings"].items()})
    if fails:
        sys.exit("; ".join(fails))
    print("passenger cabin: the game's T3 gives the lab's layout, packings and times; the search packs at least as many: pass")


if __name__ == "__main__":
    main()
