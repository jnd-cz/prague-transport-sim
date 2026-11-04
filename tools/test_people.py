"""The pedestrians' figures (#251): python -P -E tools/test_people.py [--line 17] [--synthetic]
(its own server on a free port). Part 1, without world data: the figures (src/people.js, assets/people/)
load with their skeleton and clips, and on a synthetic crowd of 100 walkers in a row the nearest ones
become animated figures (at most 64, in within 80 m, out beyond 88 m), walk or run by their speed and keep
the crowd's shirt colours, with hair colours of their own; the rest go to the far batch and the box crowd
is hidden. Part 2, in the game (needs data/lineN.json; skipped without): after a short autopilot drive the
walkers and the stop crowd are drawn by figures, the box meshes are on the hidden layer, and ?boxpeople
leaves the box figures."""
import argparse
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

SYNTHETIC = """async () => {
  const THREE = await import('three');
  const { People, PEOPLE_FILES, loadPeople } = await import('/src/people.js');
  const res = await Promise.all(PEOPLE_FILES.map(async (f) => { const r = await fetch('/' + f); return { ok: r.ok, arrayBuffer: () => r.arrayBuffer() }; }));
  const assets = await loadPeople(res);
  let bones = 0, tris = 0, farTris = 0;
  assets.near.scene.traverse((o) => { if (o.isSkinnedMesh) bones = Math.max(bones, o.skeleton.bones.length); if (o.isMesh) tris += o.geometry.index.count / 3; });
  assets.far.scene.traverse((o) => { if (o.isMesh) farTris += o.geometry.index.count / 3; });
  const people = new People(new THREE.Scene(), assets);
  const N = 100, crowd = new THREE.InstancedMesh(new THREE.BoxGeometry(0.4, 1.7, 0.3), new THREE.MeshBasicMaterial(), N);
  const slots = [], m = new THREE.Matrix4(), red = new THREE.Color(0xc03020);
  const row = (x0, gap, dx = 0) => { for (let i = 0; i < N; i++) { m.makeTranslation(x0 + gap * i + dx, 0, 0); crowd.setMatrixAt(i, m); } };
  for (let i = 0; i < N; i++) { crowd.setColorAt(i, red); slots.push({ i }); }
  const game = { clock: 0, crowd: null, runners: [], obstacles: [], action: null };
  const cam = new THREE.PerspectiveCamera();
  const look = (x, clock) => { cam.position.set(x, 1.6, 0); cam.updateMatrixWorld(); game.clock = clock; people.sync(cam, { crowd, slots }, game); };
  const motions = () => { const k = {}; for (const f of people.near.values()) k[f.motion] = (k[f.motion] || 0) + 1; return k; };
  const out = { bones, tris, farTris, clips: assets.near.animations.map((c) => c.name).sort() };
  row(1, 2);                 // walkers at x = 1, 3, ..., 199 m
  look(0, 0); out.at0 = { ...people.stats, hidden: crowd.layers.mask };
  look(-6, 0.5); out.back6 = { ...people.stats };     // the far ones near: still near up to 88 m
  look(-10, 1); out.back10 = { ...people.stats };     // the one at 79 m is now 89 m away: far
  look(0, 1.5); out.again = { ...people.stats };      // and near again within 80 m
  row(1, 2, 0.6); look(0, 2.0); out.walk = motions(); // 0.6 m in 0.5 s: walking
  row(1, 2, 2.1); look(0, 2.5); out.run = motions();  // 1.5 m in 0.5 s: running
  const f = people.near.values().next().value;
  out.shirt = f.mats.shirt.color.getHex() === red.getHex();
  row(1, 0.5); look(0, 3.0); out.cap = { ...people.stats }; // all 100 within 51 m: the cap
  out.hairColours = new Set([...people.near.values()].map((f) => f.mats.hair.value.getHex())).size;
  const count = (a) => a.array.reduce((s, v) => s + v, 0);
  let nearHair = 0;
  assets.near.scene.traverse((o) => { if (o.isMesh && o.geometry.attributes.hairMask) nearHair = count(o.geometry.attributes.hairMask); });
  out.hairVertices = [nearHair, count(people.far.geometry.attributes.hairMask)];
  return out;
}"""

GAME = """async () => {
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const g = window.game, traffic = window.traffic, ap = new Autopilot(), dt = 1 / 30;
  g.audio.setMuted?.(true);
  for (let t = 0; t < 90; t += dt) { ap.step(g, dt); g.update(dt, ap.input); traffic.update(dt, window.camera); }
  g.updateVisuals();
  window.people.sync(window.camera, traffic, g);
  const walkers = (traffic.slots || []).filter(Boolean).length;
  return { ...window.people.stats, walkers, stopCrowd: g.crowd.count, hidden: [traffic.crowd.layers.mask, g.crowd.layers.mask] };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def importmap():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    return re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--synthetic", action="store_true", help="part 1 only (no world data needed)")
    args = ap.parse_args()
    faulthandler.dump_traceback_later(900, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    data = os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json"))
    fails, r = [], {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 960, "height": 540})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__people.html", lambda route: route.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__people.html")
            r["synthetic"] = s = page.evaluate(SYNTHETIC)
            want = {
                "17 bones": s["bones"] == 17,
                "the 8 clips": s["clips"] == sorted(["Walk", "Idle", "Run", "StairUp", "StairDown", "TramStepUp", "TramStepDown", "Sit"]),
                "4228 / 840 triangles": (s["tris"], s["farTris"]) == (4228, 840),
                "40 near within 80 m, 60 far": (s["at0"]["near"], s["at0"]["far"]) == (40, 60),
                "the box crowd hidden (layer 1)": s["at0"]["hidden"] == 2,
                "kept near up to 88 m": s["back6"]["near"] == 40,
                "far beyond 88 m": s["back10"]["near"] == 39,
                "near again within 80 m": s["again"]["near"] == 40,
                "walking at 1.2 m/s": s["walk"] == {"Walk": 40},
                "running at 3 m/s": s["run"] == {"Run": 40},
                "the crowd's shirt colour": s["shirt"],
                "at most 64 near": (s["cap"]["near"], s["cap"]["far"]) == (64, 36),
                "the hair regions (86 near, 20 far vertices)": s["hairVertices"] == [86, 20],
                "hair colours vary": s["hairColours"] >= 4,
            }
            fails += [f"synthetic: {k}" for k, ok in want.items() if not ok]
            if data and not args.synthetic:
                for mode in ("", "&boxpeople"):
                    page.goto(f"{base}/?line={args.line}{mode}", timeout=300000)
                    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                    if mode:
                        r["boxpeople"] = b = page.evaluate("({ people: window.people })")
                        if b["people"] is not None:
                            fails.append("?boxpeople: the figures loaded anyway")
                        continue
                    page.evaluate("document.getElementById('optAuto').checked = false")
                    page.click("#btnStart")
                    page.wait_for_function("window.game && window.traffic && window.camera", timeout=60000)
                    r["game"] = gm = page.evaluate(GAME)
                    if gm["people"] < gm["walkers"] or gm["walkers"] == 0:
                        fails.append(f"game: {gm['walkers']} walkers, {gm['people']} drawn as figures")
                    if gm["near"] == 0 or gm["near"] > 64:
                        fails.append(f"game: {gm['near']} near figures")
                    if gm["hidden"] != [2, 2]:
                        fails.append(f"game: the box crowds' layers {gm['hidden']}, should be the hidden one (2)")
            elif not args.synthetic:
                print(f"(part 2 skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)")
            if errors:
                fails.append(f"page errors: {errors[:3]}")
            browser.close()
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()
    print(json.dumps(r))
    if fails:
        sys.exit("; ".join(fails))
    print("pedestrian figures: load, near/far by distance (64, 80 / 88 m), walk and run by speed, box figures hidden: pass")


if __name__ == "__main__":
    main()
