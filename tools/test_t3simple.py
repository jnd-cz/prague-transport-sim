"""The built-in T3 (src/t3simple.js, #427) against the T3's general-arrangement drawing, in headless Chromium.

Usage: python -P -E tools/test_t3simple.py [--shots DIR] [--models simple,classic,hybrid]

Needs no world data. Checks: the body is 14.0 x 2.5 m with its roof at 3.02 m; the ends in plan taper
from the doors and in the side view lean back above the windscreen's foot (the drawing's numbers); the
bogie pivots 6.4 m apart with wheels of 700 mm at 1.9 m; the couplers' heads meet in a two-car set; the
pantograph's head at the wire; the plates and cards on the right cars and swapped with the line; at most
four draw calls a car besides its plates; the T3M variant with its roof box and green display, fleet numbers by
type, AI sets of both types. With --shots: the same views of each model (side, three-quarter
front and rear, the front, a two-car set, an orthographic side elevation at the colour drawing's scale)
as DIR/<model>-<view>.png and one picture per view with the models side by side (DIR/compare-<view>.png).
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

MEASURE = r"""async () => {
  const THREE = await import('three');
  const models = await import('/src/models.js');
  const { CAR_PITCH } = await import('/src/tram.js');
  const m = models.makeT3({ line: '17', cars: 2, detailed: false, dest: 'Vozovna Kobylisy', run: '801', variant: 'T3SUCS' });
  new THREE.Scene().add(m);
  const [a, b] = m.userData.cars, out = { kind: m.userData.kind, bogie: m.userData.bogie };
  const meshes = (car) => car.children.filter((o) => o.isMesh);
  const named = (car, name) => car.children.find((o) => o.name === name);
  out.drawn = [meshes(a).length, meshes(b).length];
  const body = named(a, 'body'), parts = named(a, 'parts');
  // the variants: the T3M's resistor box towards the rear of the roof, its route display; the fleet numbers
  const roofBox = (geo) => { const P = geo.attributes.position; let top = 0; for (let i = 0; i < P.count; i++) if (P.getZ(i) < -1.2 && P.getZ(i) > -4.1 && Math.abs(P.getX(i)) < 0.7) top = Math.max(top, P.getY(i)); return top; };
  const px = (mat) => Array.from(mat.map.image.getContext('2d').getImageData(3, 3, 1, 1).data.slice(0, 3));
  const t3m = models.makeT3({ line: '17', cars: 2, detailed: false, run: '801', variant: 'T3M' });
  out.variants = { suc: m.userData.variant, m: t3m.userData.variant, sucRoof: roofBox(parts.geometry), mRoof: roofBox(named(t3m.userData.cars[0], 'parts').geometry),
    sucDisplay: px(m.userData.mats.rbMat), mDisplay: px(t3m.userData.mats.rbMat) };
  out.fleet = { suc: m.userData.fleet, m: t3m.userData.fleet, meshes: [a, b].map((c) => c.children.filter((o) => o.name === 'fleet').length) };
  // the T3M's side display on every car, none on the T3SUCS; the next stop redraws it; the side indicators on both sides
  const displays = (set) => set.userData.cars.map((c) => c.children.filter((o) => o.name === 'display').length);
  const led0 = t3m.userData.mats.ledMat.map;
  models.setNextStop(t3m, 'Palmovka');
  const L = named(a, 'lamps').geometry.attributes.position;
  const ind = [-1, 1].map((s) => { for (let i = 0; i < L.count; i++) if (s * L.getX(i) > 1.255 && Math.abs(L.getZ(i) - 3.05) < 0.05 && Math.abs(L.getY(i) - 1.81) < 0.07) return true; return false; });
  out.displays = { suc: displays(m), m: displays(t3m), next: t3m.userData.mats.ledMat.map !== led0 && t3m.userData.next === 'Palmovka', indicators: ind };
  const auto = new Set();
  for (let r = 801; r < 849; r++) auto.add(models.makeT3({ line: '17', detailed: false, run: String(r) }).userData.variant);
  out.fleet.auto = [...auto].sort();
  // faded in as an AI tram: the fleet numbers stay a blended decal, the body opaque
  const { setOpacity } = await import('/src/traffic.js');
  setOpacity(t3m, 0); setOpacity(t3m, 0.5); setOpacity(t3m, 1);
  const tc = t3m.userData.cars[0], fm = named(tc, 'fleet').material, bm = named(tc, 'body').material;
  out.fleet.faded = { transparent: fm.transparent, depthWrite: fm.depthWrite, opacity: fm.opacity, body: bm.transparent };
  body.geometry.computeBoundingBox();
  const bb = body.geometry.boundingBox;
  out.body = { x: [bb.min.x, bb.max.x], y: [bb.min.y, bb.max.y], z: [bb.min.z, bb.max.z] };
  // the parts: the wheels (the points on the rail), the couplers' faces, the pantograph's head
  const P = parts.geometry.attributes.position, low = [];
  let top = -Infinity, zMin = Infinity, zMax = -Infinity;
  for (let i = 0; i < P.count; i++) {
    const y = P.getY(i), z = P.getZ(i);
    if (y < 0.01) low.push(z); // the wheels' lowest points (the track-brake shoes hang 12 mm up)
    top = Math.max(top, y); zMin = Math.min(zMin, z); zMax = Math.max(zMax, z);
  }
  // the points on the rail in groups (a wheel's are within its 0.7 m), each group's middle
  low.sort((p, q) => p - q);
  const groups = [];
  for (const z of low) { const g = groups[groups.length - 1]; if (g && z - g[g.length - 1] < 0.3) g.push(z); else groups.push([z]); }
  out.wheelZ = groups.map((g) => +((g[0] + g[g.length - 1]) / 2).toFixed(3));
  out.top = top; out.couplers = [zMin, zMax]; out.wire = models.CONTACT_WIRE - models.RAIL_TOP;
  // the outline, by rays: the half width at the waist along the car, the nose's z by height
  a.updateMatrixWorld(true);
  const hit = (o, d) => new THREE.Raycaster(new THREE.Vector3(...o), new THREE.Vector3(...d)).intersectObject(body, false)[0]?.point;
  out.halfWidth = Object.fromEntries([0, 3.0, 5.5, -5.8].map((z) => [z, -hit([-5, 1.2, z], [1, 0, 0]).x]));
  out.noseF = Object.fromEntries([1.0, 1.65, 2.3, 2.53, 2.65].map((h) => [h, hit([0, h, 20], [0, 0, -1]).z]));
  out.noseR = Object.fromEntries([1.0, 1.69, 2.53].map((h) => [h, hit([0, h, -20], [0, 0, 1]).z]));
  // a set on a straight: the cars' centres, the couplers' heads
  models.placeConsist(m, 100, (s) => [s, 0, 0, 0]);
  out.pitch = Math.abs(a.position.x - b.position.x); out.CAR_PITCH = CAR_PITCH;
  m.updateMatrixWorld(true);
  out.couplerGap = a.localToWorld(new THREE.Vector3(0, 0, zMin)).distanceTo(b.localToWorld(new THREE.Vector3(0, 0, zMax)));
  // the plates: route box, mirror, destination and run on the first car, the rear plate on the last
  out.plates = [a, b].map((c) => c.children.filter((o) => o.name === 'plate').length);
  const rb = m.userData.mats.rbMat, map0 = rb.map;
  models.setConsistLine(m, '22', 'Bílá Hora', '802');
  out.swapped = rb.map !== map0 && m.userData.dest === 'Bílá Hora';
  return out;
}"""

# the same views of each model: a car facing +z on a strip of track, lit as the game lights it (src/main.js)
SHOTS = r"""async ({ kinds }) => {
  const THREE = await import('three');
  const models = await import('/src/models.js');
  const t3h = await import('/src/t3h.js');
  if (kinds.includes('hybrid')) {
    const files = await Promise.all(t3h.T3H_FILES.map(async (f) => { const r = await fetch('/' + f); return { ok: r.ok, json: () => r.json(), arrayBuffer: () => r.arrayBuffer() }; }));
    await t3h.loadHybridT3(files, models.CONTACT_WIRE - models.RAIL_TOP);
  }
  if (kinds.includes('classic')) await models.loadDetailedT3('assets/t3/t3.gltf');
  const W = 1280, H = 720;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(W, H);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#b9cfe0');
  scene.add(new THREE.HemisphereLight(0xdfe9f5, 0x6b6a5c, 1.6));
  const sun = new THREE.DirectionalLight(0xfff1dc, 1.6);
  sun.position.set(-300, 500, 200);
  scene.add(sun);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.MeshLambertMaterial({ color: 0x8c8a82 }));
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.01;
  scene.add(ground);
  for (const x of [-0.7175, 0.7175]) {
    const rail = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.02, 60), new THREE.MeshLambertMaterial({ color: 0x9a9a9a }));
    rail.position.set(x, 0, -10);
    scene.add(rail);
  }
  const persp = (pos, look, fov = 32) => { const c = new THREE.PerspectiveCamera(fov, W / H, 0.1, 500); c.position.set(...pos); c.lookAt(...look); return c; };
  // the side elevation at the colour drawing's scale (12.66 mm a pixel, 79 px/m), the right side
  const elev = new THREE.OrthographicCamera(-W / 2 / 79, W / 2 / 79, H / 2 / 79, -H / 2 / 79, 0.1, 100);
  elev.position.set(-40, 2.3, 0); elev.lookAt(0, 2.3, 0);
  const views = {
    side: persp([-24, 2.2, 0.5], [0, 1.6, 0.5], 36), front34: persp([-7.5, 2.3, 15], [0, 1.5, 5]), rear34: persp([7, 2.4, -15], [0, 1.5, -5]),
    front: persp([0, 1.8, 22], [0, 1.7, 0], 14), set: persp([-14, 4, 24], [0, 1.4, -4], 40), elevation: elev,
    bogie: persp([-5, 0.9, 3.4], [0, 0.45, 3.2], 32), display: persp([-6.5, 2.0, 1.2], [-1.25, 2.0, 3.2], 34),
  };
  const out = {};
  for (const kind of kinds) {
    for (const [view, cam] of Object.entries(views)) {
      const simple = kind === 'simple' || kind === 't3m';
      const m = models.makeT3({ line: '17', cars: view === 'set' ? 2 : 1, detailed: simple ? false : kind, dest: 'Sídliště Ďáblice', run: '801', variant: kind === 't3m' ? 'T3M' : 'T3SUCS' });
      models.placeConsist(m, 7.6, (s) => [0, -s, 0, 0]);
      if (m.userData.hybrid) t3h.poseHybrid(m, { doors: 0, braking: false, track: 0 });
      models.setNextStop(m, 'Palmovka');
      scene.add(m);
      renderer.render(scene, cam);
      out[`${kind}-${view}`] = renderer.domElement.toDataURL('image/png');
      scene.remove(m);
      models.disposeModel(m);
    }
    out[`${kind}-kind`] = kind;
  }
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def importmap():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    return re.search(r'<script type="importmap">.*?</script>', html, re.S).group(0)


def near(v, want, tol):
    return abs(v - want) <= tol


def judge(r):
    """The checks against the drawing's numbers: a list of failures."""
    fails = []
    want = {
        "the built-in model": r["kind"] == "simple",
        "body 14.0 m long (z -7.00..7.00)": near(r["body"]["z"][0], -7.0, 0.01) and near(r["body"]["z"][1], 7.0, 0.01),
        "body 2.5 m wide": near(r["body"]["x"][0], -1.25, 0.005) and near(r["body"]["x"][1], 1.25, 0.005),
        "skirt at 0.35 m, roof at 3.02 m": near(r["body"]["y"][0], 0.35, 0.005) and near(r["body"]["y"][1], 3.02, 0.005),
        "bogie pivots 3.2 m from the centre": near(r["bogie"], 3.2, 1e-6),
        "the wheels on the rail at the pivots +-0.95 m": len(r["wheelZ"]) == 4
        and all(near(z, w, 0.01) for z, w in zip(r["wheelZ"], (-4.15, -2.25, 2.25, 4.15))),
        "the couplers' heads at +-7.52 m": near(r["couplers"][0], -7.52, 0.01) and near(r["couplers"][1], 7.52, 0.01),
        "the collector's head just under the wire": near(r["top"], r["wire"] - 0.005, 0.01),
        # the plan view: straight sides, the ends tapering from 4.51 m ahead / 4.84 m behind the centre
        "the plan: 1.25 m half width amidships": near(r["halfWidth"]["0"], 1.25, 0.01) and near(r["halfWidth"]["3"], 1.25, 0.01),
        "the plan: the front tapered to 1.03 m at 5.5 m": near(r["halfWidth"]["5.5"], 1.025, 0.03),
        "the plan: the rear tapered to 1.02 m at -5.8 m": near(r["halfWidth"]["-5.8"], 1.016, 0.03),
        # the side view: the nose at 7.0 m at the windscreen's foot, the windscreen leaning back 0.44 m, the visor
        "the side: the windscreen's foot at 7.0 m": near(r["noseF"]["1.65"], 7.0, 0.02),
        "the side: the windscreen's top 0.44 m back": near(r["noseF"]["2.53"], 6.56, 0.03),
        "the side: the visor over it": r["noseF"]["2.65"] > r["noseF"]["2.53"] + 0.05,
        "the side: the rear window's foot at -7.0 m": near(r["noseR"]["1.69"], -7.0, 0.02),
        "two cars CAR_PITCH apart": near(r["pitch"], r["CAR_PITCH"], 0.005),
        "the coupled heads meet": r["couplerGap"] < 0.01,
        "plates: 4 on the first car, the rear plate on the last": r["plates"] == [4, 1],
        "the plates follow the line": r["swapped"],
        "four draw calls a car besides the plates": r["drawn"][0] - r["plates"][0] <= 4 and r["drawn"][1] - r["plates"][1] <= 4,
        # the variants: only a T3M has the resistors' box on the roof (3.02 m) and the green-on-black display
        "variants as asked": r["variants"]["suc"] == "T3SUCS" and r["variants"]["m"] == "T3M",
        "the T3M's roof box, none on the T3SUCS": r["variants"]["mRoof"] > 3.18 and r["variants"]["sucRoof"] < 3.12,
        "the T3M's side display on each car, none on the T3SUCS; the next stop shown": r["displays"]["m"] == [1, 1] and r["displays"]["suc"] == [0, 0] and r["displays"]["next"],
        "the side indicators on both sides": r["displays"]["indicators"] == [True, True],
        "the T3M's display dark, the T3SUCS's plate blue": sum(r["variants"]["mDisplay"]) < 90 and r["variants"]["sucDisplay"][2] > 120,
        "fleet numbers by type, each car its own": all(7001 <= n <= 7292 for n in r["fleet"]["suc"]) and all(8001 <= n <= 8090 for n in r["fleet"]["m"])
        and len(set(r["fleet"]["suc"])) == 2 and r["fleet"]["meshes"] == [1, 1],
        "AI sets of both types by run number": r["fleet"]["auto"] == ["T3M", "T3SUCS"],
        "faded in: the fleet numbers stay blended, the body opaque": r["fleet"]["faded"] == {"transparent": True, "depthWrite": False, "opacity": 1, "body": False},
    }
    fails += [k for k, ok in want.items() if not ok]
    return fails


def montage(outdir, kinds, views):
    from PIL import Image, ImageDraw
    for v in views:
        ims = [Image.open(os.path.join(outdir, f"{k}-{v}.png")) for k in kinds]
        w, h = ims[0].size
        sheet = Image.new("RGB", (w, h * len(ims)), "white")
        for i, (k, im) in enumerate(zip(kinds, ims)):
            sheet.paste(im, (0, i * h))
            ImageDraw.Draw(sheet).text((12, i * h + 10), k, fill="black")
        sheet.save(os.path.join(outdir, f"compare-{v}.png"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--shots", help="also save the views of each model into this directory")
    ap.add_argument("--models", default="simple,t3m,classic,hybrid", help="the models for --shots (t3m: the built-in car as a T3M)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    faulthandler.dump_traceback_later(600, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__t3s.html", lambda route: route.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__t3s.html")
            r = page.evaluate(MEASURE)
            if args.shots:
                kinds = args.models.split(",")
                shots = page.evaluate(SHOTS, {"kinds": kinds})
                os.makedirs(args.shots, exist_ok=True)
                views = sorted({k.split("-", 1)[1] for k in shots if not k.endswith("-kind")})
                for k, v in shots.items():
                    if k.endswith("-kind"):
                        continue
                    open(os.path.join(args.shots, f"{k}.png"), "wb").write(base64.b64decode(v.split(",", 1)[1]))
                montage(args.shots, kinds, views)
                print(f"shots: {len(shots) - len(kinds)} pictures in {args.shots}")
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, ensure_ascii=False))
    fails = judge(r) + [f"page error: {e}" for e in errors[:3]]
    if fails:
        print("FAILED\n  " + "\n  ".join(fails))
        sys.exit(1)
    print(f"built-in T3: the drawing's outline and numbers, {r['drawn'][0]} + {r['drawn'][1]} draw calls in a two-car set: pass")


if __name__ == "__main__":
    main()
