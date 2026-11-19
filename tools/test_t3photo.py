# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check and export the original photo-based T3 using its own ephemeral server.

Usage: python -P -E tools/test_t3photo.py [--export] [--screenshots]
No world data, Blender or Node required. Reports go to reports/t3photo/.
"""
import argparse
import base64
import faulthandler
import functools
import http.server
import json
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

CHECK = """async () => {
  const THREE = await import('three');
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { bindPhotoT3, T3_PHOTO } = await import('/src/t3photo.js');
  const s = window.t3studio, m = s.model, r = m.rig;
  const checks = {}, near = (a, b) => Math.abs(a - b) < .002;
  const pos = n => n.getWorldPosition(new THREE.Vector3());
  s.reset();
  const shell = m.getObjectByName('Body_Ivory_enamel');
  const bounds = new THREE.Box3().setFromObject(shell);
  bounds.union(new THREE.Box3().setFromObject(m.getObjectByName('Body_Prague_red_enamel')));
  const size = bounds.getSize(new THREE.Vector3());
  checks.bodyLength14 = near(size.z, 14);
  checks.bodyWidth2_5 = near(size.x, 2.5);
  checks.roof3_06 = near(bounds.max.y, 3.06);
  checks.bogies6_4 = near(pos(r.bogies[0]).distanceTo(pos(r.bogies[1])), 6.4);
  checks.axles1_9 = [0, 2].every(i => near(pos(r.wheelsets[i]).distanceTo(pos(r.wheelsets[i + 1])), 1.9));
  const wheels = new THREE.Box3().setFromObject(r.wheelsets[0]);
  checks.wheels0_7 = near(wheels.max.y - wheels.min.y, .7) && near(wheels.min.y, 0);
  const coupling = new THREE.Box3().setFromObject(r.couplers[0]);
  coupling.union(new THREE.Box3().setFromObject(r.couplers[1]));
  checks.overCouplers15_104 = near(coupling.max.z - coupling.min.z, 15.104);
  checks.twelveDoorLeaves = r.doors.flatMap(d => d.pairs.flatMap(p => [p.outer, p.inner])).length === 12;
  checks.doorBottomAtFirstStep = r.doors.every(d => {
    const b = new THREE.Box3().setFromObject(d.node);
    return b.min.y >= T3_PHOTO.entryFloor && b.min.y < T3_PHOTO.entryFloor + .025 && near(b.max.y, 2.65);
  });
  const interior = m.getObjectByName('Interior');
  const seats = interior.userData.passengerSeats;
  checks.twentyFourSeats = seats.length === 24;
  checks.seatsClearDoorways = seats.filter(p => p.x < -.6).every(p => T3_PHOTO.doors.every(z => Math.abs(z - p.z) > 1));
  const ray = new THREE.Raycaster();
  const hit = (origin, direction, objects) => {
    ray.set(new THREE.Vector3(...origin), new THREE.Vector3(...direction));
    return ray.intersectObjects(objects, true)[0];
  };
  const redShell = m.getObjectByName('Body_Prague_red_enamel');
  checks.sideWallsKeepFullWidthBetweenShoulders = [-1, 1].every(side =>
    [-5.8, -4.4, -3, -1.8, 0, 1.8, 3, 4.4, 5.8].filter(z => side > 0 || T3_PHOTO.doors.every(d => Math.abs(d - z) > .71)).every(z => {
      const h = hit([side * 2, 1.495, z], [-side, 0, 0], [redShell]);
      return h && near(Math.abs(h.point.x), 1.25 * (1 - .10 * Math.max(0, Math.abs(z) - 4.65)));
    }));
  // Check the actual frame vertices against the panel surface, not just the overall body bounds.
  const frames = m.getObjectByName('Interior_Aluminium').geometry.attributes.position;
  let frameClearance = Infinity;
  for (let i = 0; i < frames.count; i++) {
    const x = frames.getX(i), y = frames.getY(i), z = frames.getZ(i);
    if (y < 1.15 || y > 1.64 || Math.abs(x) < .4) continue;
    const side = Math.sign(x), h = hit([side * 2, y, z], [-side, 0, 0], [redShell]);
    if (h) frameClearance = Math.min(frameClearance, Math.abs(h.point.x) - Math.abs(x));
  }
  checks.seatFramesClearActualPanels = frameClearance > .04 && frameClearance < .3;
  const cushions = []; interior.traverse(o => { if (o.isMesh && o.material.name === 'Red_seat_cushion') cushions.push(o); });
  checks.seatsHaveSolidCushions = seats.every(p => {
    const h = hit([p.x, 1.5, p.z + .08], [0, -1, 0], cushions);
    return h && h.point.y > 1.30 && h.point.y < 1.34;
  });
  const supports = []; interior.traverse(o => { if (o.isMesh && o.material.name === 'Handrails') supports.push(o); });
  checks.seatsHavePedestals = seats.every(p => {
    const x = p.x * (1 - .10 * Math.max(0, Math.abs(p.z) - 4.65));
    const h = hit([x, 1.245, p.z], [0, -1, 0], supports);
    return h && h.point.y > 1.22 && h.point.y < 1.245;
  });
  checks.silverInsideCreamOutsideDoors = T3_PHOTO.doors.every((z, i) => [-.5175, -.1725, .1725, .5175].every(dz => {
    const inside = hit([0, 1.53, z + dz], [-1, 0, 0], [r.doors[i].node]);
    const outside = hit([-2, 1.53, z + dz], [1, 0, 0], [r.doors[i].node]);
    return inside?.object.material.name === 'Handrails' && outside?.object.material.name === 'Ivory_enamel';
  }));
  const floors = []; interior.traverse(o => { if (o.isMesh && o.material.name === 'Floor') floors.push(o); });
  checks.closedStairRisers = T3_PHOTO.doors.every(z => [.48, .72].every((y, i) => {
    const h = hit([-2, y, z], [1, 0, 0], floors), expected = (-1.035 + i * .22) * (1 - .10 * Math.max(0, Math.abs(z) - 4.65));
    return h && Math.abs(h.point.x - expected) < .025;
  }));
  checks.solidWheelFaces = r.wheelsets.every(w => [-1, 1].every(side => [0, .08, .17, .26, .33].every(radius => {
    const p = pos(w), h = hit([side * 1.4, p.y + radius, p.z], [-side, 0, 0], [w]);
    return h && h.object.material.name === 'Wheel_brown_dust';
  })));
  const brakes = []; m.traverse(o => { if (o.isGroup && o.name.startsWith('Magnetic_brake_')) brakes.push(o); });
  checks.fourSuspendedMagneticBrakes = brakes.length === 4 && brakes.every(b => {
    const box = new THREE.Box3().setFromObject(b), size = box.getSize(new THREE.Vector3());
    return box.min.y > .015 && box.min.y < .03 && size.y > .4 && size.z > 1;
  });
  checks.twoSideIndicators = ['left', 'right'].every(side => m.getObjectByName('Side_indicator_' + side));
  checks.singleCollectorDiagonal = r.pantograph.arms.every(a => a.lower.userData.diagonalRods === 1 && a.upper.userData.diagonalRods === 1);
  const endVertices = m.getObjectByName('Body_Prague_red_enamel').geometry.attributes.position;
  let shoulderWidth = 0;
  for (let i = 0; i < endVertices.count; i++) if (Math.abs(endVertices.getZ(i)) > 6.5) shoulderWidth = Math.max(shoulderWidth, Math.abs(endVertices.getX(i)));
  checks.taperedEndShoulders = shoulderWidth > .6 && shoulderWidth < 1.05;
  const browHit = hit([0, 2.68, 8], [0, 0, -1], [shell]);
  const glassHit = hit([0, 2.64, 8], [0, 0, -1], [m.getObjectByName('Body_Window_glass')]);
  checks.browOverhangsGlass = browHit && glassHit && browHit.point.z > glassHit.point.z + .025;
  const routePlate = m.getObjectByName('Route_plate'), routeBounds = new THREE.Box3().setFromObject(routePlate);
  checks.routePlateFollowsBrow = routeBounds.min.y > 2.65 && routeBounds.max.y < 3.02 && routePlate.rotation.x < -.08 && routePlate.rotation.x > -.25;
  const frontCoupler = m.getObjectByName('Coupler_front');
  const forkCentre = hit([0, .46, 8], [0, 0, -1], [frontCoupler]);
  const forkCheek = hit([-.11, .46, 8], [0, 0, -1], [frontCoupler]);
  checks.couplerHasOpenFork = forkCentre && forkCheek && forkCheek.point.z - forkCentre.point.z > .10;
  checks.couplerHasBoredEye = !hit([-.112, 1, 7.45], [0, -1, 0], [frontCoupler]) && !!hit([-.16, 1, 7.45], [0, -1, 0], [frontCoupler]);
  checks.rearWiperRig = r.wipers.length === 3 && !!m.getObjectByName('Wiper_rear_pivot');
  const before = pos(r.doors[0].pairs[0].inner);
  s.pose(m, { doors: [1, .5, 0], bogies: [.2, -.2], wheelAngle: 1.2, wipers: 1, couplers: [.15, -.15], pantograph: 1 });
  checks.doorsFoldInward = pos(r.doors[0].pairs[0].inner).x > before.x + .3;
  checks.independentDoors = near(r.doors[2].pairs[0].outer.rotation.y, 0) && near(Math.abs(r.doors[1].pairs[0].outer.rotation.y), T3_PHOTO.doorMaxAngle / 2);
  checks.doorsStopShortOf90 = near(Math.abs(r.doors[0].pairs[0].outer.rotation.y), 84 * Math.PI / 180);
  checks.bogiePose = near(r.bogies[0].rotation.y, .2) && near(r.bogies[1].rotation.y, -.2);
  checks.wheelPose = r.wheelsets.every(w => near(w.rotation.x, 1.2));
  checks.couplerPose = near(r.couplers[0].rotation.y, .15);
  const headHigh = pos(r.pantograph.head).y;
  const armTip = arm => arm.upper.localToWorld(new THREE.Vector3(0, r.pantograph.armLength, 0));
  checks.collectorLinkage = r.pantograph.arms.every(a => armTip(a).distanceTo(pos(r.pantograph.head)) < .0001);
  s.pose(m, { pantograph: 0 });
  checks.collectorLowers = headHigh - pos(r.pantograph.head).y > 2;
  checks.collectorFoldedLinkage = r.pantograph.arms.every(a => armTip(a).distanceTo(pos(r.pantograph.head)) < .0001);
  s.reset();
  checks.poseResets = before.distanceTo(pos(r.doors[0].pairs[0].inner)) < 1e-6;
  let invalid = 0; m.traverse(o => { if (o.isMesh) for (const v of o.geometry.attributes.position.array) if (!Number.isFinite(v)) invalid++; });
  checks.finiteGeometry = invalid === 0;
  const bytes = await s.exportGLB(), gltf = await new GLTFLoader().parseAsync(bytes, '');
  const names = []; gltf.scene.traverse(o => { if (o.name) names.push(o.name); });
  const expected = [...r.doors.flatMap(d => d.pairs.flatMap(p => [p.outer.name, p.inner.name])),
    ...r.bogies.map(b => b.name), ...r.wheelsets.map(w => w.name), ...r.wipers.map(w => w.name),
    'Pantograph_contact_head', 'Coupler_front', 'Coupler_rear'];
  checks.glbHierarchy = expected.every(n => names.includes(n));
  bindPhotoT3(gltf.scene);
  s.pose(gltf.scene, { doors: [1, .5, 0], pantograph: .3, wipers: 1 });
  checks.importedRigMoves = near(Math.abs(gltf.scene.rig.doors[0].pairs[0].outer.rotation.y), T3_PHOTO.doorMaxAngle)
    && near(gltf.scene.rig.wipers[0].rotation.z, -.52) && near(gltf.scene.rig.wipers[1].rotation.z, .52);
  s.pose(gltf.scene); s.roundTrip = gltf.scene;
  const originalBounds = new THREE.Box3().setFromObject(m), importedBounds = new THREE.Box3().setFromObject(gltf.scene);
  checks.glbBounds = originalBounds.min.distanceTo(importedBounds.min) < .001 && originalBounds.max.distanceTo(importedBounds.max) < .001;
  let materials = new Set(), textures = new Set(), floorTexture;
  gltf.scene.traverse(o => { if (o.isMesh) {
    materials.add(o.material.name); if (o.material.map) textures.add(o.material.map.uuid);
    if (o.material.name === 'Floor') floorTexture = o.material.map;
  } });
  checks.glbMaterials = materials.has('Prague_red_enamel') && materials.has('Ivory_enamel') && textures.size === 2;
  checks.glbRibbedFloor = floorTexture?.image.width === 64 && floorTexture.wrapS === THREE.RepeatWrapping;
  checks.meshBudget = s.stats.meshes < 150;
  checks.triangleBudget = s.stats.triangles < 100000;
  s.renderer.render(s.scene, s.camera);
  const nodes = []; m.traverse(o => { if (o.userData.assembly) nodes.push({ name: o.name,
    parent: o.parent.name, translation: o.position.toArray(), rotation: o.quaternion.toArray(),
    ...(o.userData.axis ? { axis: o.userData.axis } : {}), ...(o.userData.range ? { range: o.userData.range } : {}) }); });
  return { checks, stats: s.stats, body: size.toArray(), roof: bounds.max.y, nodes,
    glbBytes: bytes.byteLength, exportedNodes: names.length, materials: materials.size,
    drawCalls: s.renderer.info.render.calls, seatFrameClearance: frameClearance,
    failed: Object.keys(checks).filter(k => !checks[k]) };
}"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--screenshots', action='store_true')
    args = parser.parse_args()
    faulthandler.dump_traceback_later(180, exit=True)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = ROOT / 'reports' / 't3photo'
    out.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1600, 'height': 1000}, device_scale_factor=1)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}/tools/t3-model/', timeout=60000)
            page.wait_for_function('window.t3studio', timeout=60000)
            page.get_by_role('slider', name='Front doors', exact=True).focus()
            page.keyboard.press('End')
            assert page.evaluate('Math.abs(t3studio.model.rig.doors[0].pairs[0].outer.rotation.y) > 1.4')
            page.keyboard.press('Home')
            result = page.evaluate(CHECK)
            result['pageErrors'] = errors
            if args.export:
                encoded = page.evaluate("""async () => {
                  const b = new Uint8Array(await t3studio.exportGLB());
                  let str = ''; for (let i=0;i<b.length;i+=8192) str += String.fromCharCode(...b.subarray(i,i+8192));
                  return btoa(str);
                }""")
                target = ROOT / 'assets' / 't3photo' / 'tatra-t3-6892.glb'
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(encoded))
                rig = {'schema': 't3photo-rig-v1', 'units': 'metres', 'up': '+Y', 'forward': '+Z',
                       'doorSide': '-X', 'railPlane': 0, 'dimensions': result['stats']['dimensions'],
                       'poseSource': '../../src/t3photo.js#posePhotoT3', 'nodes': result.pop('nodes')}
                (target.parent / 'rig.json').write_text(json.dumps(rig, indent=2) + '\n', encoding='utf-8')
            else:
                result.pop('nodes')
            if args.screenshots:
                for view in ['hero', 'front', 'side', 'rear', 'quarter', 'coupler', 'entry', 'bogie', 'interior', 'collector']:
                    page.evaluate('(v) => t3studio.view(v)', view)
                    page.wait_for_timeout(350)
                    page.screenshot(path=str(out / f'{view}.png'))
                page.evaluate("t3studio.view('hero'); t3studio.pose(t3studio.model, {doors: 1, pantograph: .68})")
                page.wait_for_timeout(350)
                page.screenshot(path=str(out / 'doors-open.png'))
                page.evaluate('t3studio.model.visible = false; t3studio.scene.add(t3studio.roundTrip)')
                page.wait_for_timeout(350)
                page.screenshot(path=str(out / 'glb-roundtrip.png'))
                page.evaluate('t3studio.scene.remove(t3studio.roundTrip); t3studio.model.visible = true')
                page.set_viewport_size({'width': 390, 'height': 844})
                page.wait_for_timeout(350)
                page.screenshot(path=str(out / 'mobile.png'))
                page.get_by_role('button', name='Interior', exact=True).click()
                page.wait_for_timeout(350)
                assert page.evaluate('Math.abs(t3studio.camera.position.z) < 6.5')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(out / 'mobile-interior.png'))
            browser.close()
        (out / 'checks.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
        if result['failed'] or errors:
            raise SystemExit(1)
    finally:
        server.shutdown()
        faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
