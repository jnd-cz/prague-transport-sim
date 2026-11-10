"""The hybrid T3 model (src/t3h.js, #248) in headless Chromium.

Usage: python -P -E tools/test_t3h.py [--line 17] [--synthetic]

Part 1 (no world data needed; the asset is in git): the model loads; the saloon, the lighter level and the
draw calls; a set on a straight and on a 20 m curve: the second car hangs on the stiff coupling link (cars
15.04 m apart), the couplers turn about their pins, the bogies (6.4 m apart) turn to the track; the
track-brake shoes hang 12 mm over the rail and drop by bogie; the couplers' heads meet on a wave in the track; the doors, the collector at the wire, the
cards. Part 2 (with data/line<N>.json): the game draws our tram with it, credits it, and its doors follow
the game's; with the classic model picked in the menu it loads that one.
"""
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SYNTHETIC = r"""async () => {
  const THREE = await import('three');
  const t3h = await import('/src/t3h.js');
  const models = await import('/src/models.js');
  // (its files from its manifest; the registry gives the sets their fleet numbers)
  const vehicles = await import('/src/vehicles.js');
  await vehicles.loadRegistry();
  const man = vehicles.byId.get('t3h');
  const files = await Promise.all([man.model, man.rig].map(async (f) => {
    const r = await fetch('/' + vehicles.fileUrl(man, f));
    return { ok: r.ok, json: () => r.json(), arrayBuffer: () => r.arrayBuffer() };
  }));
  const proto = await t3h.loadHybridT3(files, 5.34);
  const tris = (root, pred = () => true) => { let n = 0; root.traverse((o) => { if (o.isMesh && pred(o)) { const g = o.geometry; n += (g.index ? g.index.count : g.attributes.position.count) / 3; } }); return n; };
  const shown = (o) => { for (let q = o; q; q = q.parent) if (!q.visible) return false; return true; };
  const drawn = (car) => { let n = 0; car.traverse((o) => { if (o.isMesh && shown(o)) n++; }); return n; };
  const out = { stats: proto.stats, fullTris: tris(proto.template), insideTris: tris(proto.template, (o) => o.name === 'T3H_in'),
    lightTris: tris(proto.light), lightInside: tris(proto.light, (o) => o.name === 'T3H_in') };
  const m = models.makeT3({ line: '17', cars: 2, dest: 'Vozovna Kobylisy', run: '801' });
  new THREE.Scene().add(m);
  const [a, b] = m.userData.cars;
  out.hybrid = !!m.userData.hybrid;
  out.drawnFull = drawn(a);
  const pin = (car, z) => car.localToWorld(new THREE.Vector3(0, 0, z));
  const link = (k) => pin(m.userData.cars[k], -6.25).distanceTo(pin(m.userData.cars[k + 1], 6.25));
  const deg = (r) => r * 180 / Math.PI;
  // a straight along map x
  models.placeConsist(m, 100, (s) => [s, 0, 0, 0]);
  m.updateMatrixWorld(true);
  out.straight = { c1: a.position.x, c2: b.position.x, link: link(0), rear: deg(a.userData.rig.couplers[1].rotation.y), front: deg(b.userData.rig.couplers[0].rotation.y) };
  // the shoes released: their lowest point over the rail (the car on the rail plane at height 0)
  const shoeLow = () => { let y = Infinity; a.traverse((o) => { if (o.name === 'T3H_shoe') y = Math.min(y, new THREE.Box3().setFromObject(o).min.y); }); return y; };
  m.updateMatrixWorld(true);
  out.shoeGap = shoeLow();
  const shoes = (car) => car.userData.rig.bogies.map((g) => g.shoes.map((s) => +s.position.y.toFixed(4)));
  t3h.poseHybrid(m, { track: 1 }); out.track1 = shoes(a);
  t3h.poseHybrid(m, { track: 2 }); out.track2 = shoes(a);
  m.updateMatrixWorld(true); out.shoeGapOn = shoeLow();
  t3h.poseHybrid(m, { track: 0 }); out.track0 = shoes(a);
  // a 20 m curve to the left
  const R = 20, along = (car) => R * Math.atan2(car.position.x, R + car.position.z);
  models.placeConsist(m, 60, (s) => [R * Math.sin(s / R), R * (1 - Math.cos(s / R)), 0, 0]);
  m.updateMatrixWorld(true);
  out.curve = { pitch: along(a) - along(b), link: link(0), rear: deg(a.userData.rig.couplers[1].rotation.y), front: deg(b.userData.rig.couplers[0].rotation.y),
    bogies: a.userData.rig.bogies.map((g) => deg(g.node.rotation.y)) };
  // a grade, then a wave of 30 m (the cars on opposite curves): the two bars' tips, the coupling plane on the link
  const tips = () => {
    m.updateMatrixWorld(true);
    const [r, f] = [a.userData.rig.couplers[1], b.userData.rig.couplers[0]];
    return { gap: r.localToWorld(new THREE.Vector3(-1.27, 0, 0)).distanceTo(f.localToWorld(new THREE.Vector3(1.27, 0, 0))), rear: deg(r.rotation.z), front: deg(f.rotation.z) };
  };
  models.placeConsist(m, 100, (s) => [s, 0, 0.06 * s, 0]);
  out.grade = tips();
  out.wave = { gap: 0, tilt: 0 };
  for (let s = 100; s < 130; s += 1.5) {
    models.placeConsist(m, s, (q) => [q, 0, 0.05 * Math.sin(2 * Math.PI * q / 30), 0]);
    const t = tips();
    out.wave.gap = Math.max(out.wave.gap, t.gap);
    out.wave.tilt = Math.max(out.wave.tilt, Math.abs(t.rear));
  }
  models.placeConsist(m, 60, (s) => [R * Math.sin(s / R), R * (1 - Math.cos(s / R)), 0, 0]);
  // the doors and the collector
  const leaf = a.userData.rig.full.getObjectByName('Door_Front_Left_Outer');
  const q0 = leaf.quaternion.clone();
  t3h.poseHybrid(m, { doors: 1 }); out.doorTurn = deg(q0.angleTo(leaf.quaternion));
  t3h.poseHybrid(m, { doors: 0 }); out.doorBack = deg(q0.angleTo(leaf.quaternion));
  models.placeConsist(m, 100, (s) => [s, 0, 0, 0]);
  m.updateMatrixWorld(true);
  const head = a.userData.rig.full.getObjectByName(proto.rig.pantograph.head);
  out.contact = head.getWorldPosition(new THREE.Vector3()).y + proto.rig.pantograph.contactHeadOffset;
  // #436: the indicators' glows by side on both cars (in the blink's lit half, then its dark half), the brake lamps on
  // every car, the high beams' glow on the leading car
  const glows = (car, side) => car.userData.rig.signals[side].map((g) => g.visible);
  models.poseT3(m, { braking: true, indicate: 'left', clock: 0.1 });
  out.lamps = { left: [a, b].map((c) => [glows(c, 'left'), glows(c, 'right')]), brakes: [a, b].map((c) => c.userData.rig.brakes.map((g) => g.visible)) };
  // where the glows draw in the car (they were stored at scale 0, and copied with a NaN rotation never drew)
  m.updateMatrixWorld(true);
  const inCar = (g) => { const box = new THREE.Box3().setFromObject(g).applyMatrix4(a.matrixWorld.clone().invert()), c = box.getCenter(new THREE.Vector3()); return [c.x, c.y, c.z].map((v) => +v.toFixed(2)); };
  out.lamps.glowAt = [...a.userData.rig.signals.left, ...a.userData.rig.brakes].map(inCar);
  models.poseT3(m, { indicate: 'left', clock: 0.5 });
  out.lamps.dark = [a, b].map((c) => glows(c, 'left'));
  models.poseT3(m, { braking: false, indicate: null, highBeam: true });
  out.lamps.beams = [a, b].map((c) => !!c.userData.beams?.visible);
  out.lamps.beamAt = a.userData.beams ? (a.userData.beams.geometry.computeBoundingBox(), [a.userData.beams.geometry.boundingBox.min.toArray(), a.userData.beams.geometry.boundingBox.max.toArray()]) : null;
  models.poseT3(m, { highBeam: false });
  // the tail lamps added at load (the asset has none): on the rear panel, lit on every car
  const tail = (c) => c.children.find((o) => o.name === 'T3H_tail');
  out.lamps.tails = [a, b].map((c) => tail(c) && +tail(c).material.color.r.toFixed(3));
  if (tail(a)) { const tb = new THREE.Box3().setFromBufferAttribute(tail(a).geometry.attributes.position); out.lamps.tailAt = [tb.min.toArray(), tb.max.toArray()].map((v) => v.map((x) => +x.toFixed(3))); }
  // the cards
  models.setConsistLine(m, '9', 'Sídliště Řepy', '816');
  out.dest = [a, b].map((c) => c.userData.rig.plates.destAll.map((o) => o.visible));
  out.destCanvas = a.userData.rig.plates.dest.material.map?.image?.width ?? null;
  out.fleetOwn = a.userData.rig.full.getObjectByName(proto.rig.numberPlates[0]).material !== b.userData.rig.full.getObjectByName(proto.rig.numberPlates[0]).material;
  // the fleet numbers' digits: each quad's height (the four merged, four corners each) times the digits' share of
  // the texture's rows
  const fn = a.userData.rig.full.getObjectByName(proto.rig.numberPlates[0]), FP = fn.geometry.attributes.position, fh = [];
  for (let q = 0; q + 3 < FP.count; q += 4) { const ys = [0, 1, 2, 3].map((i) => FP.getY(q + i)); fh.push(Math.max(...ys) - Math.min(...ys)); }
  const fim = fn.material.map.image, fd = fim.getContext('2d').getImageData(0, 0, fim.width, fim.height).data;
  let fr0 = Infinity, fr1 = -1;
  for (let y = 0; y < fim.height; y++) for (let x = 0; x < fim.width; x++) if (fd[4 * (y * fim.width + x) + 3] > 127) { fr0 = Math.min(fr0, y); fr1 = Math.max(fr1, y); }
  out.fleetDigits = fh.map((h) => h * (fr1 - fr0 + 1) / fim.height);
  // faded in as an AI tram: the fleet numbers' clear canvas stays clear, the body opaque
  const { setOpacity } = await import('/src/traffic.js');
  setOpacity(m, 0); setOpacity(m, 0.5); setOpacity(m, 1);
  const fleetMat = a.userData.rig.full.getObjectByName(proto.rig.numberPlates[0]).material;
  out.fadedFleet = { transparent: fleetMat.transparent, depthWrite: fleetMat.depthWrite, opacity: fleetMat.opacity };
  out.fadedOpaque = []; a.userData.rig.full.traverse((o) => { if (o.isMesh && o.material.transparent && !o.material.userData.glass && !proto.rig.numberPlates.includes(o.name) && !/^Route_Number/.test(o.name)) out.fadedOpaque.push(o.name); });
  // the lighter level
  t3h.setHybridLevel(m, 'light');
  out.drawnLight = drawn(a);
  out.levels = [a.userData.rig.full.visible, a.userData.rig.light.visible];
  out.glass = proto.template.getObjectByName('T3H_glass').material.userData.opacity;
  return out;
}"""

GAME = """() => {
  const u = window.tramModel.userData, r = u.cars[0].userData.rig;
  return { hybrid: !!u.hybrid, cars: u.cars.length, doors: r.doors, open: window.game.doorOpenness,
    credit: /SimonStrikesBack/.test(document.body.innerHTML + (window.game.data?.attribution || '')) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
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
            page.route(base + "/__t3h.html", lambda route: route.fulfill(
                content_type="text/html", body=f"<!doctype html><html><head>{importmap()}</head><body></body></html>"))
            page.goto(base + "/__t3h.html")
            r["synthetic"] = s = page.evaluate(SYNTHETIC)
            st, cv = s["straight"], s["curve"]
            # On R 20, both cars on the circle: the bogie pivots stand 3.2 m along the arc from the car's centre,
            # so a bogie turns 3.2 / 20 rad to the body and the body's chord is rc from the circle's centre; its
            # pins (6.25 m from the car's centre) are rp from it; the 2.54 m link (15.04 - 2 x 6.25) spans dt at
            # rp; the car centres are R (2 a + dt) apart along the track, and each coupler stands at a + dt / 2
            # to its car.
            bogie = math.degrees(3.2 / 20)
            rc = 20 * math.cos(3.2 / 20)
            rp, a = math.hypot(rc, 6.25), math.atan2(6.25, rc)
            dt = 2 * math.asin(1.27 / rp)
            pitch, angle = 20 * (2 * a + dt), math.degrees(a + dt / 2)
            want = {
                "the model loads, 43,668 triangles (the asset's 43,792 less a hidden helper)": s["fullTris"] == 43668,
                "the saloon is its own part (>= 25,000 triangles)": s["insideTris"] >= 25000,
                "the lighter level: no saloon": s["lightInside"] == 0 and s["lightTris"] < s["fullTris"] - s["insideTris"] + 200,
                "a hybrid set": s["hybrid"],
                "draw calls per car: full <= 70, lighter <= 16": s["drawnFull"] <= 70 and s["drawnLight"] <= 16,
                "the levels swap": s["levels"] == [False, True],
                "straight: the first car's centre 7.6 m behind the front": abs(st["c1"] - 92.4) < 1e-3,
                "straight: the second car 15.04 m behind": abs(st["c1"] - st["c2"] - 15.04) < 1e-3,
                "straight: the link 2.54 m, the couplers straight": abs(st["link"] - 2.54) < 1e-3 and abs(st["rear"]) < 0.01 and abs(st["front"]) < 0.01,
                "R 20: the link keeps its length (1 mm)": abs(cv["link"] - 2.54) < 1e-3,
                f"R 20: the second car {pitch:.3f} m along the track (1 mm)": abs(cv["pitch"] - pitch) < 1e-3,
                f"R 20: each coupler {angle:.1f} degrees to its car, the two alike": abs(abs(cv["rear"]) - angle) < 0.05 and abs(abs(cv["front"]) - angle) < 0.05,
                "R 20: the bogies turn to the track": all(abs(abs(x) - bogie) < 0.01 for x in cv["bogies"]) and cv["bogies"][0] * cv["bogies"][1] < 0,
                "a grade: the couplers in line with their cars": abs(s["grade"]["rear"]) < 0.01 and abs(s["grade"]["front"]) < 0.01,
                f"a wave: the heads meet (gap {s['wave']['gap'] * 1000:.1f} mm)": s["wave"]["gap"] < 0.005,
                f"a wave: the couplers tilt ({s['wave']['tilt']:.2f} degrees)": s["wave"]["tilt"] > 0.2,
                "the shoes hang 12 mm over the rail": abs(s["shoeGap"] - 0.012) < 0.002,
                "the shoes on the rail with the magnets on": abs(s["shoeGapOn"]) < 0.002,
                "the rear bogie's shoes first": s["track1"] == [[-0.012, -0.012], [0, 0]] or s["track1"] == [[0, 0], [-0.012, -0.012]],
                "both bogies' at the stop, none when off": s["track2"] == [[-0.012, -0.012], [-0.012, -0.012]] and s["track0"] == [[0, 0], [0, 0]],
                "the doors open and shut": s["doorTurn"] > 30 and s["doorBack"] < 0.01,
                "the collector at the 5.34 m wire (3 cm)": abs(s["contact"] - 5.34) < 0.03,
                "the destination card in the leading car only": s["dest"][0] and all(s["dest"][0]) and not any(s["dest"][1]),
                "the cards drawn (canvas)": s["destCanvas"] == 1024,
                "each car its own fleet number": s["fleetOwn"],
                # the user, 2026-11-10: "fix the hybrid's fleet number size" (0.14 m as on the photos; were 0.106 m on
                # the ends, 0.13 m on the sides)
                f"the fleet numbers' digits 0.14 m on all four quads ({[round(d, 3) for d in s['fleetDigits']]})": len(s["fleetDigits"]) == 4
                and all(abs(d - 0.14) < 0.004 for d in s["fleetDigits"]),
                "faded in: the fleet numbers stay blended (their clear canvas drew black)": s["fadedFleet"] == {"transparent": True, "depthWrite": False, "opacity": 1},
                f"faded in: the rest opaque ({s['fadedOpaque'][:3]})": not s["fadedOpaque"],
                "the glass see-through (0.18)": s["glass"] == 0.18,
                # #436: the indicators by side on every car, blinking; the brake lamps at the set's rear (the coupled
                # ends dark, as the built-in car's); the high beams' glow over the leading car's headlights
                "the left indicators on both cars, the right ones off, then the blink's dark half": s["lamps"]["left"] == [[[True] * 3, [False] * 3]] * 2
                and s["lamps"]["dark"] == [[False] * 3] * 2,
                # the left front, repeater and rear indicators, the left and right brake lamps in the rear corner units
                f"the glows where the lamps are ({s['lamps']['glowAt']})": all(all(v == v for v in p) for p in s["lamps"]["glowAt"])
                and [round(p[2]) for p in s["lamps"]["glowAt"]] == [7, 3, -7, -7, -7] and all(abs(abs(p[0]) - 0.95) < 0.05 for p in s["lamps"]["glowAt"][:1] + s["lamps"]["glowAt"][2:]),
                f"the tail lamps on the rear panel ({s['lamps'].get('tailAt')}), lit on every car": s["lamps"]["tails"][0] == s["lamps"]["tails"][1] > 1
                and s["lamps"]["tailAt"][0][2] < -6.9 and 0.85 < s["lamps"]["tailAt"][0][1] < 1.1
                and abs(s["lamps"]["tailAt"][0][0] + 0.57) < 0.01,
                # the user, 2026-11-10: "in between cars only the rear red lights light up"
                "the brake lamps on every car": s["lamps"]["brakes"] == [[True, True], [True, True]],
                "the high beams' glow on the leading car, at its headlights (7.0 m ahead, 1.2 m up)": s["lamps"]["beams"] == [True, False]
                and s["lamps"]["beamAt"] and 6.9 < s["lamps"]["beamAt"][0][2] < 7.2 and 0.8 < s["lamps"]["beamAt"][0][1] < 1.3,
            }
            fails += [f"synthetic: {k}" for k, ok in want.items() if not ok]
            if data and not args.synthetic:
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                page.evaluate("document.getElementById('optAuto').checked = false")
                page.evaluate("document.getElementById('btnStart').click()")
                page.wait_for_function("window.game && window.tramModel && window.camera", timeout=60000)
                page.wait_for_timeout(2000)
                r["game"] = g = page.evaluate(GAME)
                if not g["hybrid"]:
                    fails.append("game: our tram is not the hybrid model")
                if abs(g["doors"] - g["open"]) > 1e-3:
                    fails.append(f"game: the drawn doors {g['doors']} do not follow the game's {g['open']}")
                if not g["credit"]:
                    fails.append("game: the hybrid's credit is missing")
                # the classic model, downloaded when picked
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                page.evaluate("document.getElementById('optAuto').checked = false; const o = document.getElementById('optModel'); o.value = 't3'; o.dispatchEvent(new Event('change'))")
                page.evaluate("document.getElementById('btnStart').click()")
                page.wait_for_function("window.game && window.tramModel && window.camera", timeout=120000)
                r["classic"] = c = page.evaluate("({ kind: window.tramModel.userData.kind, cars: window.tramModel.userData.cars.length, credit: /conflig/.test(document.getElementById('attrib').textContent) })")
                if c["kind"] != "classic" or not c["credit"]:
                    fails.append(f"game: the classic model picked, got {c}")
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
    print("hybrid T3: levels, coupling, bogies, track-brake shoes, doors, collector, cards: pass")


if __name__ == "__main__":
    main()
