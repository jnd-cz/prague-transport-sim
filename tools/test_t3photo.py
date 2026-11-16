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
  const { bindPhotoT3 } = await import('/src/t3photo.js');
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
  const before = pos(r.doors[0].pairs[0].inner);
  s.pose(m, { doors: [1, .5, 0], bogies: [.2, -.2], wheelAngle: 1.2, wipers: 1, couplers: [.15, -.15], pantograph: 1 });
  checks.doorsFoldInward = pos(r.doors[0].pairs[0].inner).x > before.x + .3;
  checks.independentDoors = near(r.doors[2].pairs[0].outer.rotation.y, 0) && near(Math.abs(r.doors[1].pairs[0].outer.rotation.y), Math.PI / 4);
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
  checks.importedRigMoves = near(Math.abs(gltf.scene.rig.doors[0].pairs[0].outer.rotation.y), Math.PI / 2)
    && near(gltf.scene.rig.wipers[0].rotation.z, .52);
  s.pose(gltf.scene); s.roundTrip = gltf.scene;
  const originalBounds = new THREE.Box3().setFromObject(m), importedBounds = new THREE.Box3().setFromObject(gltf.scene);
  checks.glbBounds = originalBounds.min.distanceTo(importedBounds.min) < .001 && originalBounds.max.distanceTo(importedBounds.max) < .001;
  let materials = new Set(), textures = new Set();
  gltf.scene.traverse(o => { if (o.isMesh) { materials.add(o.material.name); if (o.material.map) textures.add(o.material.map.uuid); } });
  checks.glbMaterials = materials.has('Prague_red_enamel') && materials.has('Ivory_enamel') && textures.size === 1;
  checks.meshBudget = s.stats.meshes < 150;
  checks.triangleBudget = s.stats.triangles < 100000;
  s.renderer.render(s.scene, s.camera);
  const nodes = []; m.traverse(o => { if (o.userData.assembly) nodes.push({ name: o.name,
    parent: o.parent.name, translation: o.position.toArray(), rotation: o.quaternion.toArray(),
    ...(o.userData.axis ? { axis: o.userData.axis } : {}), ...(o.userData.range ? { range: o.userData.range } : {}) }); });
  return { checks, stats: s.stats, body: size.toArray(), roof: bounds.max.y, nodes,
    glbBytes: bytes.byteLength, exportedNodes: names.length, materials: materials.size,
    drawCalls: s.renderer.info.render.calls, failed: Object.keys(checks).filter(k => !checks[k]) };
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
            assert page.evaluate('Math.abs(t3studio.model.rig.doors[0].pairs[0].outer.rotation.y) > 1.5')
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
                for view in ['hero', 'front', 'side', 'rear', 'left']:
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
