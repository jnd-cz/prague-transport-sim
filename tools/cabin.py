# SPDX-License-Identifier: AGPL-3.0-or-later
"""The T3's cabin for the passengers (#249): python -P -E tools/cabin.py [--model GLB] [--out DIR] [--packing JSON ...]

Runs the passenger lab's preparation (tools/cabin/, from street-life-boarding v14) in a page on a T3 model's GLB: the
layout (the 24 seats from their meshes, the three doors and their entry steps from the floor, the cab's exclusion),
then the floor (a 2 cm grid of the passenger deck, cab, fixtures, legroom, edge margin, circulation and standing
pockets; the navigation grid) and the standing packings (aligned, staggered and dense rows; the adaptive body
outlines). Writes the lab's files into DIR (default reports/249/cabin): t3-cabin-layout.json, t3-cabin-navigation.json,
t3-floor-space.json, floor-space.svg, capacity-layout.svg, packing-<id>.svg, and summary.json.
--timing LAYOUT runs the lab's timing scenarios (tools/cabin/passenger-timing.js) on a layout instead: each packing
filled and emptied, and 10 out / 10 in, both exit policies, with the lab's checks; writes DIR/passenger-timing.json.
--expect FILE compares the timings with a recorded result (the lab's tests/passenger-timing.json).
--alight LAYOUT fills every packing of a layout and empties it again with the game's alighting pace
(src/passengers/exit-flow.js GAME_PACE; --pace JSON for another): the times in through the doors and out.
--model defaults to the game's assets/t3h/tatra-t3-hybrid-nc.glb; the lab's own GLB reproduces its files. --packing adds
an adaptive packing with those options (adaptivePacking's: id, padding, trials and the search's own, tools/cabin/).
"""
import argparse
import functools
import hashlib
import http.server
import json
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL = os.path.join(ROOT, "assets", "t3h", "tatra-t3-hybrid-nc.glb")
PERSON = os.path.join(ROOT, "assets", "people", "person-near.glb")

RUN = """async ([model, person, assetId, opts]) => {
  const bytes = async (u) => (await fetch(u)).arrayBuffer();
  const hex = async (b) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', b))].map((x) => x.toString(16).padStart(2, '0')).join('');
  const { input } = await import('/tools/cabin/body-footprint.js');
  const { prepareLayout } = await import('/tools/cabin/prepare-layout.js');
  const { prepareFloor } = await import('/tools/cabin/prepare-floor.js');
  const m = await bytes(model), p = await bytes(person), sha = await hex(m);
  input.person = p; input.personSha = await hex(p);
  const { layout, summary } = await prepareLayout(m, sha, assetId);
  const floor = await prepareFloor(layout, m, sha, opts);
  return { sha, layoutSummary: summary, ...floor };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def importmap():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    return re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)


def prepare(model, opts):
    """The lab's files for this model, as {name: object or text}, and the summary."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    glb = open(model, "rb").read()
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__cabin.html", lambda r: r.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.route(base + "/__model.glb", lambda r: r.fulfill(content_type="model/gltf-binary", body=glb))
            page.goto(base + "/__cabin.html")
            page.set_default_timeout(1800000)
            asset = os.path.splitext(os.path.basename(model))[0] + "-" + hashlib.sha256(glb).hexdigest()[:8]
            out = page.evaluate(RUN, [base + "/__model.glb", base + "/assets/people/person-near.glb", asset, opts])
            browser.close()
            if errors:
                sys.exit(f"page errors: {errors[:3]}")
            return out
    finally:
        server.shutdown()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


TIMING = """async ([layout, v7]) => {
  const { passengerTiming } = await import('/tools/cabin/passenger-timing.js');
  const t0 = performance.now(), out = passengerTiming(layout, v7);
  return { ...out, cpuSeconds: (performance.now() - t0) / 1000 };
}"""


def timing(layout, v7):
    """The lab's timing scenarios on this layout (its result, the flow frames, the CPU seconds they took)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__cabin.html", lambda r: r.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__cabin.html")
            page.set_default_timeout(3600000)
            out = page.evaluate(TIMING, [layout, v7])
            browser.close()
            if errors:
                sys.exit(f"page errors: {errors[:3]}")
            return out
    finally:
        server.shutdown()


ALIGHT = """async ([layout, pace]) => {
  const flow = await import('/src/passengers/exit-flow.js');
  const { createBoardingController } = await import('/src/passengers/boarding-state.js');
  const { createPassengerTests } = await import('/tools/cabin/passenger-tests.js');
  const { selectCabinPacking } = await import('/src/passengers/cabin-space.js');
  const out = {};
  for (const config of layout.standing.configurations) {
    const c = createBoardingController(selectCabinPacking(layout, config.id), { exitPace: pace ?? flow.GAME_PACE }), t = createPassengerTests(c);
    t.startFull();
    let n = 0;
    while (t.report().status === 'running' && n++ < 40000) { c.update(0.025); t.update(); }
    out[config.id] = { people: 24 + config.places.length, status: t.report().status, ...t.report().timings };
  }
  return out;
}"""


def alight(layout, pace):
    """Each packing filled and emptied with the game's alighting pace (or this one): {packing: timings}"""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            page.route(base + "/__cabin.html", lambda r: r.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__cabin.html")
            page.set_default_timeout(3600000)
            out = page.evaluate(ALIGHT, [layout, pace])
            browser.close()
            return out
    finally:
        server.shutdown()


def timings(result):
    """{packing: {scenario: {timing: seconds}}} of a timing result"""
    return {k: {s: v[s]["timings"] for s in ("full", "mixed", "boardingDoorFull")} for k, v in result["configurations"].items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default=MODEL, help="the T3's GLB (default: the game's hybrid)")
    ap.add_argument("--out", default=os.path.join(ROOT, "reports", "249", "cabin"))
    ap.add_argument("--packing", action="append", default=[], help="an adaptive packing's options as JSON")
    ap.add_argument("--navigation-only", action="store_true")
    ap.add_argument("--timing", metavar="LAYOUT", help="run the timing scenarios on this layout instead")
    ap.add_argument("--expect", metavar="FILE", help="with --timing: a recorded result to compare with")
    ap.add_argument("--alight", metavar="LAYOUT", help="fill and empty every packing with the game's alighting pace")
    ap.add_argument("--pace", help="with --alight: another pace as JSON (src/passengers/exit-flow.js PACE's fields)")
    args = ap.parse_args()
    if args.alight:
        out = alight(json.load(open(args.alight, encoding="utf-8")), json.loads(args.pace) if args.pace else None)
        for k, t in out.items():
            print(f"{k:10} {t['people']:3} people: in through the doors {t['boardingDoorClear']:.1f} s, out {t.get('alightingDoorClear', float('nan')):.1f} s"
                  f" ({t['status']})")
        return
    if args.timing:
        layout = json.load(open(args.timing, encoding="utf-8"))
        out = timing(layout, None)
        os.makedirs(args.out, exist_ok=True)
        write(os.path.join(args.out, "passenger-timing.json"), json.dumps(out["result"], indent=1))
        got = timings(out["result"])
        for k, v in got.items():
            f, m = v["full"], v["mixed"]
            print(f"{k:10} full: board {f['boardingDoorClear']:.1f} / settled {f['boardingSettled']:.1f} s, alight {f['alightingDoorClear']:.1f} / "
                  f"route {f['alightingRouteComplete']:.1f} s; 10 out / 10 in {m.get('exchangeComplete', m.get('mixedComplete', float('nan'))):.1f} s")
        print(f"checks passed; {out['cpuSeconds']:.1f} s of CPU in the page")
        if args.expect:
            want = timings(json.load(open(args.expect, encoding="utf-8")))
            moved = [(k, s, t, want[k][s][t], got[k][s][t]) for k in want for s in want[k] for t in want[k][s]
                     if abs(want[k][s][t] - got.get(k, {}).get(s, {}).get(t, float("nan"))) > 1e-6]
            for m in moved:
                print("moved:", *m)
            if moved:
                sys.exit(f"{len(moved)} timings differ from {args.expect}")
            print(f"every timing as in {args.expect}")
        return
    opts = {"packings": [json.loads(o) for o in args.packing], "navigationOnly": args.navigation_only}
    out = prepare(args.model, opts)
    os.makedirs(args.out, exist_ok=True)
    for name, v in out["files"].items():
        text = v if isinstance(v, str) else json.dumps(v, indent=2 if name == "t3-cabin-layout.json" or name == "t3-floor-space.json" else None, ensure_ascii=False)
        write(os.path.join(args.out, name), text)
    summary = {"model": os.path.relpath(args.model, ROOT).replace("\\", "/"), "sha256": out["sha"], "layout": out["layoutSummary"], **out["summary"]}
    write(os.path.join(args.out, "summary.json"), json.dumps(summary, indent=1, ensure_ascii=False))
    for c in summary.get("placements", []):
        print(f"{c['id']:10} standing {c['count']:3} + seats = {c['totalWithSeats']:3}; overlapping pairs {c.get('overlappingBoundingEnvelopePairs')}; "
              f"window / circulation / doorway {c.get('windowPlaces')} / {c.get('circulationPlaces')} / {c.get('doorwayPlaces')}")
    print(f"written to {args.out} (model sha256 {out['sha'][:16]})")


if __name__ == "__main__":
    main()
