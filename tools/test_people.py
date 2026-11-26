# SPDX-License-Identifier: AGPL-3.0-or-later
"""The pedestrians' figures (#251): python -P -E tools/test_people.py [--line 17] [--synthetic]
(its own server on a free port). Part 1, without world data: the figures (src/people.js, assets/people/)
load with their skeleton and clips, and on a synthetic crowd of 100 walkers in a row the nearest ones
become animated figures (at most 64, in within 80 m, out beyond 88 m; the full figure within 40 m, the
simplified one further out, which must be the far figure's body unbaked), walk or run by their speed and
keep the crowd's shirt colours, with hair colours and styles of their own; the rest go to the far batch and
the box crowd is hidden. Each animated figure is one draw call, and only people in view are animated: with
the camera turned away from the row, none; with the right mirror's camera looking along it, those within 50 m of
the mirror, as the simplified figure, one draw call each in its picture. Part 2, in the game (needs data/lineN.json; skipped without): after a short autopilot drive the
walkers and the stop crowd are drawn by figures, the box meshes are on the hidden layer, and ?boxpeople
leaves the box figures. Our set's passengers (#249 step 3, src/passengerView.js): every one the passenger core has
drawn (the counted ones only on the steps and outside), those on a car as its node's children (the animated ones) or
in its own batches (the distant ones, standing and seated); and the same seeded drive, drawn once a second, ends the
same with the figures and with ?boxpeople (nothing drawn feeds back into the run). The run, from the line's first stop,
starts with nobody aboard and nobody to alight there, and nobody waits for other lines at a stop of our line only (#249).
At the next stop two walking in from the platform's ends and one running for the tram are each one figure from the platform
into the car (the same key, look and shirt in every drawn step, none missing, no jump); at the departure time the doors close
for one still walking in, who is left without a penalty (#249)."""
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNTHETIC = """async () => {
  const THREE = await import('three');
  const { People, PEOPLE_FILES, loadPeople } = await import('/src/people.js');
  const res = await Promise.all(PEOPLE_FILES.map(async (f) => { const r = await fetch('/' + f); return { ok: r.ok, arrayBuffer: () => r.arrayBuffer() }; }));
  const assets = await loadPeople(res);
  let bones = 0, tris = 0, farTris = 0;
  assets.near.scene.traverse((o) => { if (o.isSkinnedMesh) bones = Math.max(bones, o.skeleton.bones.length); if (o.isMesh) tris += o.geometry.index.count / 3; });
  assets.far.scene.traverse((o) => { if (o.isMesh) farTris += o.geometry.index.count / 3; });
  const scene = new THREE.Scene(), people = new People(scene, assets);
  const N = 100, crowd = new THREE.InstancedMesh(new THREE.BoxGeometry(0.4, 1.7, 0.3), new THREE.MeshBasicMaterial(), N);
  const slots = [], m = new THREE.Matrix4(), red = new THREE.Color(0xc03020);
  const row = (x0, gap, dx = 0) => { for (let i = 0; i < N; i++) { m.makeTranslation(x0 + gap * i + dx, 0, 0); crowd.setMatrixAt(i, m); } };
  for (let i = 0; i < N; i++) { crowd.setColorAt(i, red); slots.push({ i }); }
  const game = { clock: 0, runners: [], obstacles: [], action: null }, gameView = { game, crowd: null, driver: null, meshOf: () => null };
  // (the game's field, looking along +X at the row: only people in view are animated)
  const cam = new THREE.PerspectiveCamera(62, 16 / 9, 0.1, 2000);
  cam.rotation.set(0, -Math.PI / 2, 0);
  const look = (x, clock) => { cam.position.set(x, 1.6, 0); cam.updateMatrixWorld(); game.clock = clock; people.sync(cam, { crowd, traffic: { slots } }, gameView); };
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
  out.shirt = f.u.shirt.value.getHex() === red.getHex();
  row(1, 0.5); look(0, 3.0); out.cap = { ...people.stats }; // all 100 within 51 m: the cap
  out.hairColours = new Set([...people.near.values()].map((f) => f.u.hair.value.getHex())).size;
  // one draw call a figure, one for the far batch (three a figure before: the shirt, the trousers, the rest)
  const ren = new THREE.WebGLRenderer(); ren.setSize(320, 180);
  ren.info.reset(); ren.render(scene, cam); out.capCalls = ren.info.render.calls;
  ren.dispose();
  // turned away from the row: none animated but within the margin behind the camera; and back
  cam.rotation.set(0, Math.PI / 2, 0); look(0, 3.5); out.away = { ...people.stats };
  cam.rotation.set(0, -Math.PI / 2, 0); look(0, 4.0); out.back = { ...people.stats };
  const count = (a) => a.array.reduce((s, v) => s + v, 0);
  let nearHair = 0;
  assets.near.scene.traverse((o) => { if (o.isMesh && o.geometry.attributes.hairMask) nearHair = count(o.geometry.attributes.hairMask); });
  out.hairVertices = [nearHair, count(people.far.geometry.attributes.hairMask)];
  out.styles = new Set([...people.near.values()].map((f) => f.style)).size;
  // each person's own height (the figure's y axis), within 0.88-1.05
  const hs = [...people.near.values()].map((f) => { const e = f.root.matrix.elements; return Math.hypot(e[4], e[5], e[6]); });
  out.heights = [Math.min(...hs), Math.max(...hs), new Set(hs.map((h) => h.toFixed(3))).size];
  // the middle level is the far figure's body unbaked: the same triangles, the same bounds standing
  const mid = people.levels.middle, parts = [mid.shirt, mid.trousers, mid.citizen_detail.short];
  out.middleTris = parts.reduce((s, g) => s + g.index.count / 3, 0);
  const box = new THREE.Box3();
  for (const g of parts) { g.computeBoundingBox(); box.union(g.boundingBox); }
  people.far.geometry.computeBoundingBox();
  out.middleBoxGap = Math.max(box.min.distanceTo(people.far.geometry.boundingBox.min), box.max.distanceTo(people.far.geometry.boundingBox.max));
  // the mirror (src/mirror.js's camera: 30 deg, 150:190) at the camera's place looking along the row, the camera turned
  // away: the row every 2 m from x = 1; first without the mirror (only the camera's margin: x 1, 3, 5), then with it
  const mirror = new THREE.PerspectiveCamera(30, 150 / 190, 0.3, 300);
  mirror.position.set(0, 2.1, 0); mirror.rotation.set(0, -Math.PI / 2, 0);
  row(1, 2); cam.rotation.set(0, Math.PI / 2, 0); cam.position.set(0, 1.6, 0); cam.updateMatrixWorld();
  const sync = (m) => { game.clock += 0.5; people.sync(cam, { crowd, traffic: { slots } }, gameView, m); };
  sync(null); sync(null); out.noMirror = { ...people.stats };
  sync(mirror); sync(mirror); out.mirror = { ...people.stats };
  const ren2 = new THREE.WebGLRenderer(); ren2.setSize(150, 190);
  ren2.info.reset(); ren2.render(scene, mirror); out.mirrorCalls = ren2.info.render.calls;
  ren2.dispose();
  return out;
}"""

GAME = """async () => {
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const g = window.game, traffic = window.traffic, view = window.run.trafficView, ap = new Autopilot(), dt = 1 / 30;
  const gv = window.run.gameView, people = window.people;
  // (drawn once a simulated second, as a page draws; with ?boxpeople nothing to draw)
  const draw = () => { gv.sync(); gv.syncCrowd(); if (people) people.sync(window.camera, view, gv, null, window.paxView.sync(g, window.tramModel, gv)); };
  g.audio.setMuted?.(true);
  // (#249: the run from the line's first stop has nobody aboard and nobody to alight there; those waiting for other lines are
  // only where other lines stop, by the platforms' lines)
  const start = { first: g.opts.startStop === 0, aboard: g.pax.aboard, alightFrac: g.stops[g.nextStop].alightFrac,
    lone: g.stops.filter((st, i) => g.data.stops[i].lines?.every((l) => g.segments.some((s) => s.line === l))).map((st) => st.ambient) };
  let k = 0;
  for (let t = 0; t < 90; t += dt) { ap.step(g, dt); g.update(dt, ap.input); traffic.update(dt); view.sync(window.camera); if (++k % 30 === 0) draw(); }
  // (the run's state: equal with and without the figures)
  const state = { s: +g.tram.s.toFixed(4), clock: +g.clock.toFixed(3), score: +g.score.toFixed(3), passengers: g.tram.passengers,
    stops: g.stops.map((st) => [st.waiting, st.alight, !!st.served]).join(';'),
    actors: g.pax.cars.map((c) => [...c.c.actors.values()].map((a) => `${a.id}@${a.x.toFixed(3)},${a.z.toFixed(3)}`).join('|')).join('/') };
  if (!people) return { state };
  draw();
  const walkers = (traffic.slots || []).filter(Boolean).length;
  let skinned = 0;
  people.group.traverse((o) => { if (o.isSkinnedMesh && o.parent?.visible !== false && o.parent?.parent?.visible !== false) skinned++; });
  const stats = { ...people.stats };
  // (then the tram shown and the camera 7 m beside the first car's middle door, looking at it: its passengers near)
  const model = window.tramModel, node = model.userData.cars[0].userData.rig.full, cam = window.camera, V = cam.position.constructor;
  model.visible = true; node.updateMatrixWorld(true);
  cam.position.copy(new V(-0.8, 1.7, 7).applyMatrix4(node.matrixWorld)); cam.lookAt(new V(-0.8, 1.3, 0).applyMatrix4(node.matrixWorld));
  const pax = window.paxView.sync(g, model, gv);
  people.sync(cam, view, gv, null, pax);
  // the passengers drawn: every one the core has (the counted ones on the steps and outside only), those on a car on it
  const drawable = g.pax.cars.reduce((n, c) => n + [...c.c.actors.values()].filter((a) => !(a.counted && a.aboard && !a.legPose)).length, 0);
  const cars = new Set(pax.cars), onCar = pax.recs.filter((r) => r.parent).length;
  let nearOnCar = 0, carSkinned = 0;
  for (const f of people.near.values()) if (cars.has(f.root.parent)) nearOnCar++;
  for (const c of pax.cars) c.traverse((o) => { if (o.isSkinnedMesh) carSkinned++; });
  const farOnCar = pax.cars.reduce((n, c) => n + (c.userData.paxFar ? c.userData.paxFar.standing.count + c.userData.paxFar.seated.count : 0), 0);
  const seated = pax.recs.filter((r) => r.pax.seated).length;
  const farSeated = pax.cars.reduce((n, c) => n + (c.userData.paxFar?.seated.count ?? 0), 0);
  return { ...stats, walkers, skinned, stopCrowd: gv.crowd.count, hidden: [view.crowd.layers.mask, gv.crowd.layers.mask], state, start,
    paxRecs: pax.recs.length, drawable, onCar, nearOnCar, farOnCar, carSkinned, seated, farSeated, paxCars: pax.cars.length, cars: g.pax.cars.length };
}"""


# (#249) after GAME's drive, on to the next stop: two walking in from the platform's ends and one running for the tram, each
# one figure from the platform into the car (the same key, number and shirt in every drawn step, no step missing, no jump);
# then the departure time come, one walking in from the back end is not waited for and leaves no penalty
SCENE = """async () => {
  const { Autopilot } = await import('/src/autopilot.js');
  const g = window.game, traffic = window.traffic, view = window.run.trafficView, ap = new Autopilot(), dt = 1 / 30;
  const gv = window.run.gameView, people = window.people, model = window.tramModel, { placeConsist } = await import('/src/models.js');
  model.visible = true;
  const step = () => { ap.step(g, dt); g.update(dt, ap.input); traffic.update(dt); view.sync(window.camera); };
  // (the model where the tram is, as the page places it each frame, src/main.js placeTram: the passengers on its cars go with it)
  const place = () => placeConsist(model, g.tram.s, (q) => { const p = g.route.at(q); return [p.x, p.y, g.profile.height(q), g.route.rollAt(q)]; });
  const draw = () => { place(); gv.sync(); gv.syncCrowd(); people.sync(window.camera, view, gv, null, window.paxView.sync(g, model, gv)); };
  for (let t = 0; t < 900 && !(g.stops[g.nextStop].arrived && g.doorState === 'open'); t += dt) step();
  const st = g.stops[g.nextStop], [lo, hi] = g.platformEnds(st);
  st.nextCome = Infinity; // (the stream off: the test's three only)
  st.sched = g.clock + 90; // (and time for them)
  g._spawnWalker(st, 'front'); g._spawnWalker(st, 'back'); st.runners = 1; g._spawnRunners(st);
  const who = g.runners.slice(-3), out = { stop: st.name, ends: [lo, hi].map((x) => +x.toFixed(1)), tram: +g.tram.s.toFixed(1), who: [] };
  const start = who.map((r) => ({ s: +r.s.toFixed(1), walk: !!r.walk, car: r.car, door: r.door }));
  const tracks = who.map(() => []);
  const actorOf = (r) => { for (const c of g.pax.cars) for (const a of c.c.actors.values()) if (a.who === r) return a; return null; };
  const aboard = who.map(() => null);
  for (let t = 0; t < 80 && aboard.some((x) => x === null || g.clock - x < 3); t += dt) {
    step(); draw();
    who.forEach((r, i) => {
      const rec = people.recs.find((x) => x.key === r), a = actorOf(r);
      if (a?.aboard && aboard[i] === null) aboard[i] = g.clock;
      tracks[i].push(rec ? { x: rec.x, y: rec.y, z: rec.z, n: rec.n, shirt: rec.shirt.getHex(), pax: !!rec.pax } : null);
    });
  }
  who.forEach((r, i) => {
    const tr = tracks[i], first = tr.findIndex(Boolean);
    let gaps = 0, jump = 0, box = false, pax = false;
    const looks = new Set();
    for (let k = first; k >= 0 && k < tr.length; k++) {
      const p = tr[k];
      if (!p) { gaps++; continue; }
      looks.add(`${p.n}/${p.shirt}`);
      if (p.pax) pax = true; else if (!pax) box = true;
      const q = tr[k - 1];
      if (q && k > first) jump = Math.max(jump, Math.hypot(p.x - q.x, p.y - q.y, p.z - q.z));
    }
    out.who.push({ ...start[i], seen: first >= 0, gaps, looks: [...looks], jump: +jump.toFixed(3), boxThenPax: box && pax, aboard: aboard[i] !== null });
  });
  // the departure time come: one walking in from the back end, not waited for
  g._spawnWalker(st, 'back');
  const late = g.runners[g.runners.length - 1], pen = g.penalties.leftBehind || 0, sched = (st.sched = g.clock);
  let closing = null;
  for (let t = 0; t < 60 && st.departClock === null; t += dt) { step(); if (closing === null && g.doorState !== 'open') closing = g.clock; }
  for (let t = 0; t < 8; t += dt) step(); // (on its way: those left behind are left)
  out.late = { s: +late.s.toFixed(1), state: late.state, closingAfter: closing === null ? null : +(closing - sched).toFixed(2),
    penalty: (g.penalties.leftBehind || 0) - pen, boarded: !!actorOf(late) };
  return out;
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
            page.route(base + "/__people.html", lambda route: route.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__people.html")
            r["synthetic"] = s = page.evaluate(SYNTHETIC)
            want = {
                "17 bones": s["bones"] == 17,
                "the 8 clips": s["clips"] == sorted(["Walk", "Idle", "Run", "StairUp", "StairDown", "TramStepUp", "TramStepDown", "Sit"]),
                "4228 / 840 triangles": (s["tris"], s["farTris"]) == (4228, 840),
                "40 near within 80 m, 60 far": (s["at0"]["near"], s["at0"]["far"]) == (40, 60),
                "of them 20 full within 40 m, 20 middle": (s["at0"]["full"], s["at0"]["middle"]) == (20, 20),
                "full kept up to 46 m": (s["back6"]["full"], s["back10"]["full"]) == (20, 18),
                "the middle level: the far figure's 840 triangles": s["middleTris"] == 840,
                "the middle level: the far figure's bounds (2 mm)": s["middleBoxGap"] < 0.002,
                "hair styles vary": s["styles"] >= 4,
                "heights 0.88-1.05, varied": s["heights"][0] >= 0.879 and s["heights"][1] <= 1.051 and s["heights"][2] >= 20,
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
                "one draw call a figure (64 near + the far batch: 65)": s["capCalls"] == 65,
                # (the figure's sphere, 1.45 m, and the 4 m kept: those within 5.45 m behind the camera stay, 9 of the row)
                "none animated out of view (beyond the 5.45 m margin)": (s["away"]["near"], s["away"]["far"]) == (9, 91),
                "animated again in view": s["back"]["near"] == 64,
                "turned away, no mirror: the camera's margin only (3)": (s["noMirror"]["near"], s["noMirror"]["mirror"]) == (3, 0),
                "the mirror: those within 50 m of it animated (3 + 22), the simplified figure":
                    (s["mirror"]["near"], s["mirror"]["mirror"]) == (25, 22) and s["mirror"]["full"] <= 3,
                "the mirror's picture: one draw call a figure (25 + the far batch)": s["mirrorCalls"] == 26,
            }
            fails += [f"synthetic: {k}" for k, ok in want.items() if not ok]
            if data and not args.synthetic:
                for mode in ("", "&boxpeople"):
                    # (one seed for both, so the two drives are the same run)
                    page.goto(f"{base}/?line={args.line}&seed=7{mode}", timeout=300000)
                    page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                    # (the page steps no game of its own: both drives are the test's steps only)
                    page.evaluate("document.getElementById('optAuto').checked = false; window.headless = true")
                    if mode:
                        r["boxpeople"] = b = page.evaluate("({ people: window.people })")
                        if b["people"] is not None:
                            fails.append("?boxpeople: the figures loaded anyway")
                        page.click("#btnStart")
                        page.wait_for_function("window.game && window.traffic && window.camera", timeout=60000)
                        box = page.evaluate(GAME)["state"]
                        if box != r["game"]["state"]:
                            diff = [k for k in box if box[k] != r["game"]["state"].get(k)]
                            fails.append(f"game: the run differs with the figures and without them ({diff})")
                        continue
                    page.click("#btnStart")
                    page.wait_for_function("window.game && window.traffic && window.camera", timeout=60000)
                    r["game"] = gm = page.evaluate(GAME)
                    want = {
                        f"passengers: {gm['paxRecs']} drawn of {gm['drawable']}": gm["paxRecs"] >= gm["drawable"] > 0,
                        f"passengers: our {gm['paxCars']} cars": gm["paxCars"] == gm["cars"] > 0,
                        f"passengers on a car: {gm['nearOnCar']} animated + {gm['farOnCar']} distant of {gm['onCar']}":
                            gm["nearOnCar"] > 0 and gm["nearOnCar"] + gm["farOnCar"] == gm["onCar"] and gm["carSkinned"] == gm["nearOnCar"],
                        f"passengers seated: {gm['seated']}, of them distant on the seated figure {gm['farSeated']}": gm["seated"] > 0 and gm["farSeated"] <= gm["seated"],
                        f"from the line's first stop: {gm['start']['aboard']} aboard at the start, alighting share {gm['start']['alightFrac']}":
                            gm["start"]["first"] and gm["start"]["aboard"] == 0 and gm["start"]["alightFrac"] == 0,
                        f"waiting for other lines at the {len(gm['start']['lone'])} stops of our line only: {gm['start']['lone']}":
                            len(gm["start"]["lone"]) > 0 and not any(gm["start"]["lone"]),
                    }
                    fails += [f"game: {k}" for k, ok in want.items() if not ok]
                    # (#249: those walking in and the runner, one figure each into the car; the late one not waited for)
                    r["scene"] = sc = page.evaluate(SCENE)
                    lo, hi = sc["ends"]
                    for i, w in enumerate(sc["who"]):
                        name = f"{'walker' if w['walk'] else 'runner'} {i + 1} at {sc['stop']}"
                        want = {
                            f"{name}: boarded": w["aboard"],
                            f"{name}: one figure, no drawn step without it ({w['gaps']})": w["seen"] and w["gaps"] == 0,
                            f"{name}: one look, number and shirt ({w['looks']})": len(w["looks"]) == 1,
                            f"{name}: from their own figure on into the core's boarder": w["boxThenPax"],
                            f"{name}: no jump between drawn steps ({w['jump']} m)": w["jump"] < 0.6,
                        }
                        if w["walk"]:
                            want[f"{name}: in from a platform end ({w['s']}; ends {lo}, {hi})"] = min(abs(w["s"] - (lo - 1)), abs(w["s"] - (hi + 1))) < 0.15
                        fails += [f"scene: {k}" for k, ok in want.items() if not ok]
                    late = sc["late"]
                    want = {
                        f"the departure time come, the doors close for one still walking in ({late['closingAfter']} s)":
                            late["closingAfter"] is not None and late["closingAfter"] < 1,
                        f"the one walking in is left ({late['state']}), not aboard": late["state"] == "left" and not late["boarded"],
                        f"no penalty for them ({late['penalty']})": late["penalty"] == 0,
                    }
                    fails += [f"scene: {k}" for k, ok in want.items() if not ok]
                    if gm["people"] < gm["walkers"] or gm["walkers"] == 0:
                        fails.append(f"game: {gm['walkers']} walkers, {gm['people']} drawn as figures")
                    if gm["near"] == 0 or gm["near"] > 64:
                        fails.append(f"game: {gm['near']} near figures")
                    if gm["skinned"] != gm["near"]:
                        fails.append(f"game: {gm['skinned']} skinned meshes shown for {gm['near']} near figures (one each)")
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
    print("pedestrian figures: load, near/far by distance (64, 80 / 88 m) and view, one draw call a figure, walk and run by "
          "speed, box figures hidden: pass")


if __name__ == "__main__":
    main()
