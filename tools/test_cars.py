# SPDX-License-Identifier: AGPL-3.0-or-later
"""The street vehicles as drawn (#250, #723): python -P -E tools/test_cars.py [--line 17] [--synthetic]
(its own server on a free port). Part 1, without world data: the five types' models (src/cars.js, assets/cars/) load;
on synthetic box cars (src/models.js makeCar, sized by fitCar) every one in the camera's view within 65 m (out beyond
73 m) is drawn as the near model, the nearest 64 at most, and the rest as the far one, in 21 draw calls however many; a
queue of 40 ahead all near, 6 behind the camera far; turned around the other way, and back with the same plate cells,
no plate drawn again; the box cars are on the hidden
layer; each car's paint is its box car's colour, near and far; its lamps by its state (the indicator it shows, the brake
lamps while it slows or stands, none on a parked car); its front wheels steered to the curve it drives (atan of the
wheelbase by the curvature, to its left in a left turn), the rear ones not, the wheels on the ground and rolled by the
distance; its fade one value on all its parts; a plate cell of its own while near. Part 2, in the game (needs
data/lineN.json; skipped without): after a short autopilot drive the traffic's cars are drawn as models and their boxes
hidden, and ?boxcars leaves the box cars."""
import argparse
import faulthandler
import functools
import http.server
import json
import math
import os
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNTHETIC = """async () => {
  const THREE = await import('three');
  const { Cars, CAR_FILES, loadCars, NEAR_MAX } = await import('/src/cars.js');
  const { CAR_TYPES } = await import('/src/carTypes.js');
  const { makeCar, fitCar } = await import('/src/models.js');
  const scene = new THREE.Scene();
  const cars = new Cars(scene, await loadCars(await Promise.all(CAR_FILES.map((f) => fetch('/' + f)))));
  const view = { cars: new Map() }, game = { clock: 0, obstacles: [], signals: [] };
  const group = new THREE.Group(); scene.add(group);
  const made = [];
  const box = (i, type, x, z, yaw = 0) => { const m = makeCar(i); fitCar(m, type); m.rotation.order = 'YXZ'; m.position.set(x, 0, z); m.rotation.y = yaw; group.add(m); return m; };
  const add = (i, type, x, z, yaw) => { const m = box(i, type, x, z, yaw); view.cars.set({ id: i + 1 }, m); made.push(m); return m; };
  const cam = new THREE.PerspectiveCamera(50, 16 / 9, 0.1, 1000);
  const look = (x, z) => { cam.position.set(x, 1.6, z); cam.updateMatrixWorld(); };
  const sync = (n = 1, fn) => { for (let i = 0; i < n; i++) { game.clock += 1 / 30; fn?.(i); cars.sync(cam, view, game); } };
  const out = { nearMax: NEAR_MAX };
  // one of each type in a row 3.4 m apart at z = 0, facing +Z; 20 more from z = -100 on
  CAR_TYPES.forEach((t, i) => add(i, t, (i - 2) * 3.4, 0));
  for (let k = 0; k < 20; k++) add(10 + k, CAR_TYPES[k % 5], (k % 10 - 5) * 4, -100 - Math.floor(k / 10) * 9);
  look(0, 10); sync();
  out.at0 = { ...cars.stats, hidden: made[0].layers.mask, hiddenPart: made[0].children[3].layers.mask };
  const r = new THREE.WebGLRenderer(); r.setSize(320, 180);
  r.info.reset(); r.render(scene, cam); out.calls = r.info.render.calls;
  out.typeTris = Object.fromEntries([...cars.types].map(([t, k]) => [t.id, [k.body, k.lamps, k.plates, k.far].map((m) => m.geometry.index.count / 3)]));
  out.wheelTris = cars.wheels.geometry.index.count / 3;
  // the paint: each type's one near car and its far ones in their box cars' colours
  const hex = (m, i) => { const c = new THREE.Color(); m.getColorAt(i, c); return c.getHexString(); };
  out.paint = [...cars.types].map(([t, k], i) => [hex(k.body, 0) === made[i].children[0].material.color.getHexString(),
    hex(k.far, 0) === made[5 + i].children[0].material.color.getHexString()]);
  out.farPaintVertices = [...cars.types.values()].map((k) => k.far.geometry.attributes.paint.array.reduce((s, v) => s + v, 0));
  out.cells = [cars.cell.size, new Set(cars.cell.values()).size];
  // near until 73 m, in again within 65 m (the hatchback at x -6.8, z 0)
  const near = () => cars.near.has('t1');
  look(0, 10); sync(); const a = near();
  look(0, 69); sync(); const b = near();
  look(0, 74); sync(); const c = near();
  look(0, 67); sync(); const d = near();
  look(0, 64); sync(); const e = near();
  out.hysteresis = [a, b, c, d, e];
  // lamps: the hatchback indicating left; the sedan braking to a stop, then driving on at 5 m/s; a parked car
  const parked = box(40, CAR_TYPES[0], 8, 4);
  game.obstacles.push({ type: 'parked', mesh: parked, state: 'idle' });
  look(0, 12);
  made[0].userData.blink('left', true);
  let v = 6;
  sync(30, () => { v = Math.max(0, v - 0.3); made[1].position.z += v / 30; });
  const lampsOf = (t) => { const k = cars.types.get(CAR_TYPES[t]); return Array.from(k.lamps.geometry.attributes.instanceLamps.array.slice(0, 4 * k.lamps.count)); };
  out.lampsIndicating = lampsOf(0);  // the hatchback's and the parked hatchback's, in their order of distance
  out.lampsBraking = lampsOf(1);
  sync(30, () => { made[1].position.z += 5 / 30; });
  out.lampsDriving = lampsOf(1);
  // steering: the hatchback (the nearest: wheels 0-3, FL FR RL RR) on a left arc, 0.012 rad a 0.2 m step, for 9 m
  game.obstacles.length = 0; parked.visible = false;
  const h = made[0];
  sync(45, () => { h.rotation.y += 0.012; h.position.x += Math.sin(h.rotation.y) * 0.2; h.position.z += Math.cos(h.rotation.y) * 0.2;
    cam.position.set(h.position.x + 3, 1.6, h.position.z + 3); cam.updateMatrixWorld(); });
  const m = new THREE.Matrix4(), p = new THREE.Vector3(), q = new THREE.Quaternion(), s = new THREE.Vector3();
  const yaw = h.rotation.y, fwd = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw)), left = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
  out.wheels = [0, 1, 2, 3].map((i) => {
    cars.wheels.getMatrixAt(i, m); m.decompose(p, q, s);
    const x = new THREE.Vector3(1, 0, 0).applyQuaternion(q); // (the wheel's +X: where it rolls; the roll turns it about its axle)
    const axle = new THREE.Vector3(0, 0, 1).applyQuaternion(q); // (its axle: the car's right, turned by the steering)
    // (the axle's turn from the car's right towards its front: a left steer turns the right-hand axle forwards)
    const ang = Math.atan2(axle.dot(fwd), -axle.dot(left));
    return { y: +p.y.toFixed(4), steer: +ang.toFixed(4), sx: +s.x.toFixed(4) };
  });
  out.steer = cars.track.get('t1').steer;
  out.dist = cars.track.get('t1').dist;
  // the fade: the sedan at 0.4 on its body, lamps, plates and wheels; at 0 not drawn
  made[1].userData.alpha = 0.4; look(0, 12); sync();
  const sedan = cars.types.get(CAR_TYPES[1]);
  out.fade = [sedan.body, sedan.lamps, sedan.plates].map((k) => +k.geometry.attributes.instanceFade.getX(0).toFixed(3));
  out.wheelFades = Array.from(cars.wheels.geometry.attributes.instanceFade.array.slice(0, cars.wheels.count)).filter((f) => Math.abs(f - 0.4) < 1e-6).length;
  const before = cars.stats.cars;
  made[1].userData.alpha = 0; sync(); out.gone = [sedan.body.count, before - cars.stats.cars];
  // a queue (another traffic: the cars above gone, their cells freed): 40 in four lanes 10 to 64 m ahead of the camera,
  // 6 behind it 8 and 14 m away
  const view2 = { cars: new Map() };
  const put = (i, x, z) => view2.cars.set({ id: 1000 + i }, box(100 + i, CAR_TYPES[i % 5], x, z));
  for (let k = 0; k < 40; k++) put(k, (k % 4 - 1.5) * 3.5, -10 - 6 * Math.floor(k / 4));
  for (let k = 0; k < 6; k++) put(40 + k, (k % 3 - 1) * 3.5, 8 + 6 * Math.floor(k / 3));
  const key = (i) => `t${1000 + i}`, ids = (a, b) => Array.from({ length: b - a }, (_, i) => a + i);
  let plates = 0;
  const draw = cars._plate.bind(cars);
  cars._plate = (c, t) => { plates++; draw(c, t); };
  const turn = (y) => { cam.position.set(0, 1.6, 0); cam.rotation.set(0, y, 0); cam.updateMatrixWorld(); game.clock += 1 / 30; cars.sync(cam, view2, game); };
  turn(0);
  out.queue = { ...cars.stats, cells: cars.cell.size, behindNear: ids(40, 46).filter((i) => cars.near.has(key(i))).length, plates };
  const cellsOf = () => ids(0, 40).map((i) => cars.cell.get(key(i)));
  const kept = cellsOf();
  let had = plates;
  turn(Math.PI);
  out.turned = { ...cars.stats, behindNear: ids(40, 46).filter((i) => cars.near.has(key(i))).length, plates: plates - had };
  had = plates;
  turn(0);
  out.back = { ...cars.stats, plates: plates - had, sameCells: cellsOf().every((c, i) => c === kept[i]) };
  // the bound: 30 more in two outer lanes 14 to 62 m ahead, 70 in view: the nearest 64 near, a cell each (the cells of
  // the 6 behind taken back), still 21 draw calls
  for (let k = 0; k < 30; k++) put(46 + k, (k % 2 ? 1 : -1) * 8.75, -14 - 3.4 * Math.floor(k / 2));
  turn(0);
  out.bound = { ...cars.stats, cells: cars.cell.size, distinct: new Set([...cars.near].map((k) => cars.cell.get(k))).size };
  r.info.reset(); r.render(scene, cam); out.bound.calls = r.info.render.calls; out.bound.triangles = r.info.render.triangles;
  return out;
}"""

GAME = """async () => {
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const g = window.game, traffic = window.traffic, view = window.run.trafficView, ap = new Autopilot(), dt = 1 / 30;
  g.audio.setMuted?.(true);
  for (let t = 0; t < 90; t += dt) { ap.step(g, dt); g.update(dt, ap.input); traffic.update(dt); view.sync(window.camera); }
  window.cars.sync(window.camera, view, g);
  const shown = [...view.cars].filter(([c, m]) => c.type && (m.userData.alpha ?? 1) > 0 && m.visible);
  const hidden = shown.filter(([, m]) => m.layers.mask === 2 && m.children.every((o) => o.layers.mask === 2)).length;
  const types = new Set(shown.map(([c]) => c.type.id)).size;
  return { ...window.cars.stats, shown: shown.length, hidden, types };
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
            browser = gpu.launch(p)[0]
            page = browser.new_page(viewport={"width": 960, "height": 540})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route(base + "/__cars.html", lambda route: route.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__cars.html")
            r["synthetic"] = s = page.evaluate(SYNTHETIC)
            steer = math.atan(2.64 * 0.012 / 0.2)
            w = s["wheels"]
            want = {
                "5 near, 20 far": (s["at0"]["near"], s["at0"]["far"]) == (5, 20),
                "21 draw calls for 25 cars": s["calls"] == 21,
                "the box cars hidden (layer 1)": (s["at0"]["hidden"], s["at0"]["hiddenPart"]) == (2, 2),
                "the paint: the box cars' colours, near and far": all(a and b for a, b in s["paint"]),
                "the far models' paint found": all(n > 100 for n in s["farPaintVertices"]),
                "a plate cell each": s["cells"] == [5, 5],
                "a queue of 40 in view near, the 6 behind the camera far, a plate each": (s["queue"]["near"], s["queue"]["far"],
                    s["queue"]["behindNear"], s["queue"]["cells"], s["queue"]["plates"]) == (40, 6, 0, 40, 40),
                "turned around: the 6 near, the queue far": (s["turned"]["near"], s["turned"]["far"], s["turned"]["behindNear"],
                    s["turned"]["plates"]) == (6, 40, 6, 6),
                "turned back: the queue near with its plates' cells, none drawn again": (s["back"]["near"], s["back"]["plates"],
                    s["back"]["sameCells"]) == (40, 0, True),
                f"70 in view: the nearest {s['nearMax']} near, a cell each, 21 draw calls": s["nearMax"] == 64
                and (s["bound"]["near"], s["bound"]["far"], s["bound"]["cells"], s["bound"]["distinct"], s["bound"]["calls"])
                == (64, 12, 64, 64, 21),
                "near at 12 m, kept to 73 m, far beyond, near again within 65 m": s["hysteresis"] == [True, True, False, False, True],
                # (the hatchback's lamps, then the parked one's: [head, brake, left, right])
                "indicating left, daytime headlamps; a parked car unlit": sorted(round(x, 3) for x in s["lampsIndicating"])
                == sorted([0.45, 1, 1, 0, 0, 0, 0, 0]) and [0, 0, 0, 0] in (s["lampsIndicating"][:4], s["lampsIndicating"][4:])
                and any(q[2:] == [1, 0] and abs(q[0] - 0.45) < 1e-6 for q in (s["lampsIndicating"][:4], s["lampsIndicating"][4:])),
                "brake lamps while braking, off driving on": s["lampsBraking"][1] == 1 and s["lampsDriving"][1] == 0,
                f"steering {steer:.3f} rad to the left": abs(s["steer"] - steer) < 0.01,
                "the front wheels steered left by it, the rear not": abs(w[0]["steer"] - s["steer"]) < 1e-3 and abs(w[1]["steer"] - s["steer"]) < 1e-3
                and abs(w[2]["steer"]) < 1e-3 and abs(w[3]["steer"]) < 1e-3,
                "the wheels on the ground, at the type's radius": all(abs(x["y"] - 0.315) < 1e-3 and abs(x["sx"] - 0.315) < 1e-3 for x in w),
                "rolled 9 m": abs(s["dist"] - 9.0) < 0.05,
                "a fade of 0.4 on all its parts": s["fade"] == [0.4, 0.4, 0.4] and s["wheelFades"] == 4,
                "faded out: not drawn": s["gone"] == [0, 1],
            }
            fails += [f"synthetic: {k}" for k, ok in want.items() if not ok]
            if data and not args.synthetic:
                for mode in ("", "&boxcars"):
                    page.goto(f"{base}/?line={args.line}{mode}", timeout=300000)
                    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                    if mode:
                        r["boxcars"] = b = page.evaluate("({ cars: window.cars })")
                        if b["cars"] is not None:
                            fails.append("?boxcars: the models loaded anyway")
                        continue
                    page.evaluate("document.getElementById('optAuto').checked = false")
                    page.click("#btnStart")
                    page.wait_for_function("window.game && window.traffic && window.camera", timeout=60000)
                    r["game"] = gm = page.evaluate(GAME)
                    if gm["shown"] == 0 or gm["cars"] < gm["shown"]:
                        fails.append(f"game: {gm['shown']} cars in view, {gm['cars']} drawn as models")
                    if gm["hidden"] != gm["shown"]:
                        fails.append(f"game: {gm['shown'] - gm['hidden']} box cars not on the hidden layer")
                    if gm["near"] > 64:
                        fails.append(f"game: {gm['near']} near cars")
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
    print("street vehicles: five types near (in view within 65 / 73 m, 64 at most) and far in 21 draw calls, paint, "
          "lamps, steering, roll, fade, plates kept, box cars hidden: pass")


if __name__ == "__main__":
    main()
