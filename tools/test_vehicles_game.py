# SPDX-License-Identifier: AGPL-3.0-or-later
"""The vehicle registry in the game (#455), in headless Chromium: every model from its manifest, and a sample added
as a folder alone.

Usage: python -P -E tools/test_vehicles_game.py [--line 17]

Needs the line's data (python -I tools/snapshot.py data-fetch); skips without it. A sample tier-1 vehicle is made
in the page (a 14 m box in the T3's dimensions with a red block on its nose, a GLB facing +X) and served beside the
repository's vehicles with its vehicle.json and a line in assets/vehicles.json, as a folder in assets/ would be;
so is tools/test_rigged.py's rigged sample (#467), and a broken manifest (no names). Checks: the menu lists the index's vehicles in order with their names
in both languages and leaves the broken one out; picking each starts a shift with it (the right model, its cars, no
page errors), AI trams use it, it credits itself; the sample stands facing +Z with its nose forward and its wheels'
plane on the rails. The manifests themselves: tools/test_vehicles.py.
"""
import argparse
import base64
import faulthandler
import functools
import http.server
import json
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402
from test_rigged import sample_rig  # noqa: E402

# the sample: a body 14.0 x 2.5 m from 0.35 to 3.1 m over the rail, a red block on its nose, the length along +X
MAKE = r"""async () => {
  const THREE = await import('three');
  const { GLTFExporter } = await import('three/addons/exporters/GLTFExporter.js');
  const scene = new THREE.Scene();
  const body = new THREE.Mesh(new THREE.BoxGeometry(14, 2.75, 2.5).translate(0, 0.35 + 1.375, 0), new THREE.MeshStandardMaterial({ color: 0xd8c08a }));
  body.name = 'body';
  const nose = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.5, 1).translate(7.15, 1.5, 0), new THREE.MeshStandardMaterial({ color: 0xff0000 }));
  nose.name = 'nose';
  scene.add(body, nose);
  const glb = await new GLTFExporter().parseAsync(scene, { binary: true });
  let s = ''; const b = new Uint8Array(glb);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}"""

PICK = r"""async (id) => {
  const $ = (x) => document.getElementById(x);
  $('optAuto').checked = false;
  const sel = $('optModel');
  sel.value = id; sel.dispatchEvent(new Event('change'));
  $('btnStart').click();
  const t0 = performance.now();
  while (!(window.game && window.tramModel?.userData.vehicle === id)) {
    if (performance.now() - t0 > 120000) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  const m = window.tramModel, u = m?.userData || {};
  const out = { vehicle: u.vehicle, kind: u.kind, cars: u.cars?.length, attrib: $('attrib').textContent };
  if (u.kind === 'gltf') {
    // in the car's own axes: the nose forward (+Z), the body's floor of the box on the rail plane's side
    const car = u.cars[0], THREE = await import('three'), box = (name) => {
      const b = new THREE.Box3();
      car.traverse((o) => { if (o.isMesh && o.name === name) { o.geometry.computeBoundingBox(); b.union(o.geometry.boundingBox); } });
      return [b.min.toArray().map((x) => +x.toFixed(3)), b.max.toArray().map((x) => +x.toFixed(3))];
    };
    out.nose = box('nose'); out.body = box('body'); out.bogie = u.bogie; out.bodyFront = +u.bodyFront.toFixed(3);
  }
  // the AI trams that came out meanwhile: the vehicles they were built as
  await new Promise((r) => setTimeout(r, 3000));
  const ai = new Set();
  window.traffic?.group?.traverse((o) => { if (o.userData?.vehicle !== undefined && o !== m) ai.add(o.userData.vehicle); });
  out.ai = [...ai];
  return out;
}"""


def serve(body):
    """A route handler answering with this JSON (Playwright calls it with the route and the request)."""
    return lambda route, request: route.fulfill(content_type="application/json", body=body)


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    index = json.load(open(os.path.join(ROOT, "assets", "vehicles.json"), encoding="utf-8"))
    ids = index["vehicles"]
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    imap = re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)
    names = {i: json.load(open(os.path.join(ROOT, "assets", i, "vehicle.json"), encoding="utf-8"))["names"] for i in ids}
    r, fails = {}, []
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]  # (WebGL on the machine's GPU where it has one)
            page = browser.new_page()
            page.route(base + "/__make.html", lambda route: route.fulfill(content_type="text/html", body=f"<!doctype html><html><head>{imap}</head><body></body></html>"))
            page.goto(base + "/__make.html")
            glb = base64.b64decode(page.evaluate(MAKE))
            rig_glb, rig_json, rig_man = sample_rig(page, base, imap)
            page.close()
            sample = {
                "schema": 1, "id": "sample", "names": {"cs": "Vzorek (test)", "en": "Sample (test)"}, "type": "T3",
                "loader": "gltf", "model": "sample.glb", "forward": "+X", "files": [{"path": "sample.glb", "bytes": len(glb)}],
                "preload": False, "tier": 1, "moves": [], "levels": 1,
                "licence": {"spdx": "CC0-1.0", "commercial": True, "file": "LICENSE.txt", "authors": ["the test"],
                            "sources": ["tools/test_vehicles_game.py"], "credit": "Sample tram: a box from the vehicle test."},
            }
            served = {
                "/assets/vehicles.json": json.dumps({**index, "vehicles": ids + ["sample", "sample-rig", "broken"]}),
                "/assets/sample/vehicle.json": json.dumps(sample),
                "/assets/sample-rig/vehicle.json": json.dumps(rig_man),
                "/assets/sample-rig/rig.json": rig_json.decode(),
                "/assets/broken/vehicle.json": json.dumps({**sample, "id": "broken", "names": {}}),
            }
            order = ids + ["sample", "sample-rig"]
            for vid in order:
                ctx = browser.new_context(viewport={"width": 960, "height": 540})
                for path, body in served.items():
                    ctx.route(base + path, serve(body))
                ctx.route(base + "/assets/sample/sample.glb", lambda route: route.fulfill(content_type="model/gltf-binary", body=glb))
                ctx.route(base + "/assets/sample-rig/model.glb", lambda route: route.fulfill(content_type="model/gltf-binary", body=rig_glb))
                page = ctx.new_page()
                errors, warns = [], []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.on("console", lambda m, warns=warns: warns.append(m.text) if m.type in ("warning", "error") else None)
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                if vid == order[0]:
                    menu = lambda page=page: page.evaluate("[...document.getElementById('optModel').options].map((o) => [o.value, o.text])")  # noqa: E731
                    r["menu"] = {"en": menu()}
                    page.evaluate("import('/src/i18n.js').then((m) => m.setLang('cs'))")
                    r["menu"]["cs"] = menu()
                    page.evaluate("import('/src/i18n.js').then((m) => m.setLang('en'))")
                    r["brokenWarned"] = any("vehicle broken left out" in w for w in warns)
                g = r[vid] = page.evaluate(PICK, vid)
                g["errors"] = errors
                ctx.close()
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False, indent=1))
    all_names = {**names, "sample": sample["names"], "sample-rig": rig_man["names"]}
    for lang in ("en", "cs"):
        want = [[i, all_names[i][lang]] for i in order]
        if r["menu"][lang] != want:
            fails.append(f"the menu in {lang} is {r['menu'][lang]}, wants {want}")
    if not r["brokenWarned"]:
        fails.append("the broken manifest was not refused with a warning")
    kinds = {"builtin": "simple", "gltf": "gltf", "gltf-classic": "classic", "gltf-rigged": "rigged"}
    for vid in order:
        g = r[vid]
        man = sample if vid == "sample" else rig_man if vid == "sample-rig" else json.load(open(os.path.join(ROOT, "assets", vid, "vehicle.json"), encoding="utf-8"))
        if g["vehicle"] != vid or g["kind"] != kinds[man["loader"]] or g["cars"] != 2:
            fails.append(f"{vid}: built as {g['vehicle']} ({g['kind']}, {g['cars']} cars), wants {vid} ({kinds[man['loader']]}, 2 cars on line 17)")
        if g["errors"]:
            fails.append(f"{vid}: page errors {g['errors']}")
        credit = man["licence"]["credit"]
        if credit and credit not in g["attrib"]:
            fails.append(f"{vid}: its credit is not in the credits")
        if g["ai"] and set(g["ai"]) != {vid}:
            fails.append(f"{vid}: AI trams built as {g['ai']}")
    s = r["sample"]
    if s.get("kind") == "gltf":
        (n0, n1), (b0, b1) = s["nose"], s["body"]
        if not (n0[2] > 6.9 and abs(n0[0] + n1[0]) < 0.01):
            fails.append(f"sample: its nose at z {n0[2]}..{n1[2]}, wants it forward (+Z, past 6.9 m) and centred")
        if not (abs(b0[1] - 0.35) < 0.01 and abs(b1[2] - 7) < 0.01 and abs(s["bodyFront"] - 7.3) < 0.01):
            fails.append(f"sample: its body {b0}..{b1}, front {s['bodyFront']}: wants its floor at 0.35 m and its nose's front at 7.3 m")
        if abs(s["bogie"] - 3.2) > 1e-9:
            fails.append(f"sample: its pivots {s['bogie']} m from the centre, wants the T3's 3.2 m (src/tram.js)")
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failures")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
