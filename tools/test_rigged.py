# SPDX-License-Identifier: AGPL-3.0-or-later
"""The rigged loader (src/rigged.js, #467) on a sample vehicle made in the page, in headless Chromium.

Usage: python -P -E tools/test_rigged.py

Needs no world data. The sample is a box tram facing +Z (the hybrid faces +X): a body with a red nose, two bogies
placed 3.25 m from the centre (the T3's pivots are 3.2 m) with two wheels each, coupler bars, a door of two leaves
with its opening clip, a collector whose head a clip lowers, the indicators and a brake lamp, all named in its rig.
It is served as a folder (assets/sample-rig/: vehicle.json, the GLB, rig.json) beside the repository's vehicles and
loaded through the registry. Checks: it loads as a rigged vehicle; its bogies stand at the type's pivots; on a
25 m curve its bogies turn against the body to the track (opposite ways, about 0.13 rad), its wheels roll by the
distance over their radius, the couplers between its cars swing along the link; its doors open by their clip; the
collector's head follows the contact height; the indicators and the brake lamp light by state. A copy whose rig
names a part the model lacks is refused with that name in the reason. The hybrid on the same loader:
tools/test_t3h.py; the sample in the game: tools/test_vehicles_game.py.
"""
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

# the sample's model (a GLB, base64) and its rig: +Z forward, +Y up, the origin on the rail plane between the pivots
MAKE_RIG = r"""async () => {
  const THREE = await import('three');
  const { GLTFExporter } = await import('three/addons/exporters/GLTFExporter.js');
  const std = (c, e) => new THREE.MeshStandardMaterial({ color: c, ...(e ? { emissive: e } : {}) });
  const mesh = (name, g, m) => { const o = new THREE.Mesh(g, m); o.name = name; return o; };
  const rig = new THREE.Group(); rig.name = 'Rig';
  rig.add(mesh('Body', new THREE.BoxGeometry(2.5, 2.75, 14).translate(0, 0.35 + 1.375, 0), std(0xd8c08a)));
  rig.add(mesh('Nose', new THREE.BoxGeometry(1, 0.5, 0.3).translate(0, 1.5, 7.15), std(0xff0000)));
  const wheels = [];
  for (const [b, z] of [['F', 3.25], ['R', -3.25]]) {
    const bogie = new THREE.Group(); bogie.name = `Bogie_${b}`; bogie.position.set(0, 0.5, z);
    bogie.add(mesh(`Frame_${b}`, new THREE.BoxGeometry(2, 0.2, 2.4), std(0x333333)));
    for (const [k, dz] of [[1, 0.9], [2, -0.9]]) {
      const w = mesh(`Wheel_${b}${k}`, new THREE.CylinderGeometry(0.4, 0.4, 1.5, 16).rotateZ(Math.PI / 2), std(0x222222));
      w.position.set(0, -0.1, dz); bogie.add(w); wheels.push(w.name);
    }
    rig.add(bogie);
  }
  rig.add(mesh('Coupler_F', new THREE.BoxGeometry(0.12, 0.12, 1.3).translate(0, 0.59, 6.75), std(0x111111)));
  rig.add(mesh('Coupler_R', new THREE.BoxGeometry(0.12, 0.12, 1.3).translate(0, 0.59, -6.75), std(0x111111)));
  // the door: two leaves on the right side (-X), hinged at their outer edges
  const leaves = [];
  for (const [n, z] of [['D1_Out', 1.0], ['D1_In', 0.3]]) {
    const leaf = new THREE.Group(); leaf.name = n; leaf.position.set(-1.26, 0.4, z);
    leaf.add(mesh(`${n}_Panel`, new THREE.BoxGeometry(0.04, 2, 0.7).translate(0, 1, -0.35), std(0x996633)));
    rig.add(leaf); leaves.push(leaf);
  }
  const doorTrack = (n, sign) => new THREE.QuaternionKeyframeTrack(`${n}.quaternion`, [0, 1],
    [...new THREE.Quaternion().toArray(), ...new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), sign * 1.4).toArray()]);
  const doorClip = new THREE.AnimationClip('Door_D1_Open', 1, [doorTrack('D1_Out', 1), doorTrack('D1_In', -1)]);
  // the collector: its head raised 2.6 m over the roof's 3.1 m at the clip's start (contact 6.0 m), lowered to 0.9 m
  const panto = new THREE.Group(); panto.name = 'Panto'; panto.position.set(0, 3.1, 1);
  const head = mesh('Panto_Head', new THREE.BoxGeometry(1.6, 0.05, 0.1), std(0x444444)); head.position.y = 2.9;
  panto.add(head); rig.add(panto);
  const pantoClip = new THREE.AnimationClip('Panto_Lower', 1, [new THREE.VectorKeyframeTrack('Panto_Head.position', [0, 1], [0, 2.9, 0, 0, 0.9, 0])]);
  for (const [n, x, z, c] of [['Ind_L', 1.26, 6.5, 0xffa000], ['Ind_R', -1.26, 6.5, 0xffa000], ['Brake_G', 0, 1.0, 0xff0000]]) {
    const g = mesh(n, new THREE.BoxGeometry(0.05, 0.1, 0.15), std(c, c)); g.position.set(x, 1.2, n === 'Brake_G' ? -7.01 : z); rig.add(g);
  }
  const scene = new THREE.Scene(); scene.add(rig);
  const glb = await new GLTFExporter().parseAsync(scene, { binary: true, animations: [doorClip, pantoClip] });
  let s = ''; const b = new Uint8Array(glb);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return {
    glb: btoa(s),
    rig: {
      root: 'Rig', forward: '+Z',
      bogies: [{ name: 'Bogie_F', pivot: [0, 0.5, 3.25] }, { name: 'Bogie_R', pivot: [0, 0.5, -3.25] }],
      wheels: wheels.map((name) => ({ name, radius: 0.4 })),
      couplers: { front: ['Coupler_F'], rear: ['Coupler_R'] },
      doors: [{ name: 'D1', clip: 'Door_D1_Open', leaves: [{ outer: 'D1_Out', inner: 'D1_In' }] }],
      pantograph: { root: 'Panto', head: 'Panto_Head', clip: 'Panto_Lower', linkages: [], minContactHeight: 4.0, maxContactHeight: 6.0 },
      signals: { left: ['Ind_L'], right: ['Ind_R'] }, brakes: ['Brake_G'],
    },
  };
}"""


def sample_rig(page, base, imap):
    """(the GLB's bytes, its rig, its manifest) made in a blank page of the server at `base`."""
    page.route(base + "/__make.html", lambda route: route.fulfill(content_type="text/html", body=f"<!doctype html><html><head>{imap}</head><body></body></html>"))
    page.goto(base + "/__make.html")
    made = page.evaluate(MAKE_RIG)
    glb, rig = base64.b64decode(made["glb"]), made["rig"]
    rig_bytes = json.dumps(rig).encode()
    manifest = {
        "schema": 1, "id": "sample-rig", "names": {"cs": "Vzorek s pohyby (test)", "en": "Rigged sample (test)"}, "type": "T3",
        "loader": "gltf-rigged", "model": "model.glb", "rig": "rig.json", "forward": "+Z",
        "files": [{"path": "model.glb", "bytes": len(glb)}, {"path": "rig.json", "bytes": len(rig_bytes)}],
        "preload": False, "tier": 3, "moves": ["bogies", "wheels", "couplers", "collector", "lamps", "doors"], "levels": 2,
        "fleet": {"types": {"T3SUCS": {"ranges": [[7001, 7010]]}}},
        "licence": {"spdx": "CC0-1.0", "commercial": True, "file": "LICENSE.txt", "authors": ["the test"],
                    "sources": ["tools/test_rigged.py"], "credit": "Rigged sample tram: boxes from the vehicle test."},
    }
    return glb, rig_bytes, manifest


def serve_sample(ctx, base, index, glb, rig_bytes, manifest, broken=None):
    """Routes in a browser context that serve the sample as assets/sample-rig/ (and `broken`, a copy whose rig is
    given, as assets/broken-rig/) and list them in assets/vehicles.json after the repository's vehicles."""
    extra = ["sample-rig"] + (["broken-rig"] if broken else [])
    files = {
        "/assets/vehicles.json": ("application/json", json.dumps({**index, "vehicles": index["vehicles"] + extra}).encode()),
        "/assets/sample-rig/vehicle.json": ("application/json", json.dumps(manifest).encode()),
        "/assets/sample-rig/model.glb": ("model/gltf-binary", glb),
        "/assets/sample-rig/rig.json": ("application/json", rig_bytes),
    }
    if broken:
        files["/assets/broken-rig/vehicle.json"] = ("application/json", json.dumps({**manifest, "id": "broken-rig", "files": [
            {"path": "model.glb", "bytes": len(glb)}, {"path": "rig.json", "bytes": len(broken)}]}).encode())
        files["/assets/broken-rig/model.glb"] = ("model/gltf-binary", glb)
        files["/assets/broken-rig/rig.json"] = ("application/json", broken)
    for path, (kind, body) in files.items():
        ctx.route(base + path, lambda route, request, kind=kind, body=body: route.fulfill(content_type=kind, body=body))


CHECK = r"""async () => {
  const THREE = await import('three');
  const models = await import('/src/models.js'), vehicles = await import('/src/vehicles.js');
  await vehicles.loadRegistry();
  const get = async (u) => { const r = await fetch('/' + u), buf = r.ok ? await r.arrayBuffer() : null;
    return { ok: r.ok, url: u, json: async () => JSON.parse(new TextDecoder().decode(buf)), arrayBuffer: async () => buf, blobUrl: (t) => URL.createObjectURL(new Blob([buf], { type: t })) }; };
  const out = {};
  try { await models.loadVehicle(vehicles.byId.get('broken-rig'), get); out.broken = 'loaded'; } catch (e) { out.broken = String(e.message || e); }
  await models.loadVehicle(vehicles.byId.get('sample-rig'), get);
  const m = models.makeT3({ line: '17', cars: 2, vehicle: 'sample-rig', dest: 'Test', run: '801' });
  new THREE.Scene().add(m);
  const u = m.userData, [a, b] = u.cars, node = (car, n) => car.userData.rig.full.getObjectByName(n);
  out.kind = u.kind; out.vehicle = u.vehicle; out.cars = u.cars.length;
  out.pivots = ['Bogie_F', 'Bogie_R'].map((n) => +node(a, n).position.z.toFixed(4));
  // on a 25 m curve to the left (the track's frame: x east, y north; the game's z is -y)
  const R = 25, arc = (s) => [R * Math.sin(s / R), R - R * Math.cos(s / R), 0, 0];
  models.placeConsist(m, 15.04, arc);
  m.updateMatrixWorld(true);
  out.yaw = ['Bogie_F', 'Bogie_R'].map((n) => +node(a, n).rotation.y.toFixed(4));
  out.roll = +node(a, 'Wheel_F1').rotation.x.toFixed(3);
  const bar = (car, n) => car.userData.rig.couplers[n].quaternion.angleTo(new THREE.Quaternion());
  out.couplers = { rearOfFirst: +bar(a, 1).toFixed(4), frontOfSecond: +bar(b, 0).toFixed(4), free: +bar(a, 0).toFixed(4) };
  const leaf = node(a, 'D1_Out'), q0 = leaf.quaternion.clone();
  models.poseT3(m, { doors: 1 }); out.door = +q0.angleTo(leaf.quaternion).toFixed(3);
  models.poseT3(m, { doors: 0 }); out.doorShut = +q0.angleTo(leaf.quaternion).toFixed(3);
  const headY = () => node(a, 'Panto_Head').position.y;
  models.poseT3(m, { collector: 5.34 }); const hWire = headY();
  models.poseT3(m, { collector: 0 }); const hDown = headY();
  out.collector = [+hWire.toFixed(3), +hDown.toFixed(3)];
  models.poseT3(m, { indicate: 'left', clock: 0.1, braking: true });
  out.lamps = { left: node(a, 'Ind_L').visible, right: node(a, 'Ind_R').visible, brake: node(b, 'Brake_G').visible };
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    faulthandler.dump_traceback_later(300, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    index = json.load(open(os.path.join(ROOT, "assets", "vehicles.json"), encoding="utf-8"))
    imap = re.search(r'<script type="importmap">.*?</script>', open(os.path.join(ROOT, "index.html"), encoding="utf-8").read(), re.S).group(0)
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            glb, rig_bytes, manifest = sample_rig(page, base, imap)
            page.close()
            broken = json.loads(rig_bytes)
            broken["pantograph"]["head"] = "No_Such_Head"
            ctx = browser.new_context()
            serve_sample(ctx, base, index, glb, rig_bytes, manifest, broken=json.dumps(broken).encode())
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__t.html", lambda route: route.fulfill(content_type="text/html", body=f"<!doctype html><html><head>{imap}</head><body></body></html>"))
            page.goto(base + "/__t.html")
            r = page.evaluate(CHECK)
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r))
    near = lambda x, y, tol: abs(x - y) <= tol  # noqa: E731
    yf, yr = r["yaw"]
    checks = {
        "the sample loads as a rigged vehicle, two cars": r["kind"] == "rigged" and r["vehicle"] == "sample-rig" and r["cars"] == 2,
        "its bogies at the T3's pivots (3.2 m; the model has them at 3.25 m)": near(r["pivots"][0], 3.2, 1e-3) and near(r["pivots"][1], -3.2, 1e-3),
        f"on a 25 m curve the bogies turn to the track, opposite ways ({yf}, {yr} rad)": 0.09 < abs(yf) < 0.17 and 0.09 < abs(yr) < 0.17 and yf * yr < 0,
        f"the wheels roll by the distance over their radius (15.04 / 0.4 = 37.6 rad: {r['roll']})": near(r["roll"], 15.04 / 0.4, 0.01),
        f"the couplers between the cars swing along the link, the free one straight ({r['couplers']})":
            r["couplers"]["rearOfFirst"] > 0.05 and r["couplers"]["frontOfSecond"] > 0.05 and r["couplers"]["free"] < 1e-6,
        f"the door opens by its clip (1.4 rad: {r['door']}) and shuts again": near(r["door"], 1.4, 0.01) and r["doorShut"] < 1e-3,
        f"the collector's head at the wire and lowered ({r['collector']})": near(r["collector"][0], 2.9 - (6.0 - 5.34) / 2 * 2.0, 0.01) and near(r["collector"][1], 0.9, 0.01),
        "the left indicators and the brake lamps light by state": r["lamps"] == {"left": True, "right": False, "brake": True},
        f"a rig naming a part the model lacks is refused with its name ({r['broken']})": "No_Such_Head" in r["broken"],
        "no page errors": not errors,
    }
    for k, ok in checks.items():
        print("ok  " if ok else "FAIL", k)
    fails = [k for k, ok in checks.items() if not ok]
    print("rigged loader on a sample vehicle: " + ("pass" if not fails else f"{len(fails)} failures"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
