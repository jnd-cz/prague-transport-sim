# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit and export the remaining street furniture from prague-street-assets-lab.

Run with python -P -E. The optional traction pack is for local review while DPP
permission is pending. Each scene in a pack holds one named variant and level.
"""

import argparse
import base64
import faulthandler
import functools
import http.server
import json
from pathlib import Path
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STREET = ROOT / "assets/furniture/ipr-street.glb"
ATTRIBUTION = "studio Olgoj Chorchoj, spolupráce Aleš Boem. Datový podklad © IPR Praha."
MODULES = ("furniture-lod.js", "barrier-lod.js", "traction-assets.js")

PACK = """async ({ traction, attribution }) => {
  const T = await import('three');
  const { mergeVertices } = await import('three/addons/utils/BufferGeometryUtils.js');
  const { GLTFExporter } = await import('three/addons/exporters/GLTFExporter.js');
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { makeBinDetailed, makeBinLod, makeRecyclingBinLod, makeCycleStandLod } = await import('/furniture-lod.js');
  const { makeBin, makeCycleStand } = await import('/street_furniture_models.js');
  const { makeBollardLod, makeRailingLod } = await import('/barrier-lod.js');
  const { makeTractionPole, makeWallAnchor } = await import('/traction-assets.js');
  const levels = ['near', 'middle', 'far'];
  const bin = (level, small) => level === 'near' ? makeBinDetailed({ small })
    : makeBinLod({ level: level === 'middle' ? 'near' : 'mid', small });
  const labStreet = {
    'bin-large': level => bin(level, false),
    'bin-small-canopied': level => bin(level, true),
    'bin-recycling': makeRecyclingBinLod,
    'cycle-stand': makeCycleStandLod,
    'bollard': makeBollardLod,
    'railing-bars': level => makeRailingLod({ level }),
    'railing-glass': level => makeRailingLod({ level, fill: 'glass' })
  };
  const street = {
    ...labStreet,
    'bin-large': level => makeBin('bin-large', level),
    'bin-small-canopied': level => makeBin('bin-small-canopied', level),
    'bin-recycling': level => makeBin('bin-recycling', level),
    'cycle-stand': makeCycleStand,
  };
  const poles = {
    'pole-octagonal': level => makeTractionPole({ level }),
    'pole-three-stage': level => makeTractionPole({ level, type: 'three-stage' }),
    'pole-heb': level => makeTractionPole({ level, type: 'heb' }),
    'pole-three-stage-grey': level => makeTractionPole({ level, type: 'three-stage', finish: 'grey' }),
    'pole-heb-grey': level => makeTractionPole({ level, type: 'heb', finish: 'grey' }),
    'pole-octagonal-lit': level => makeTractionPole({ level, lighting: true }),
    'pole-heb-right': level => makeTractionPole({ level, type: 'heb', side: 'right' }),
    'pole-historic-study': level => makeTractionPole({ level, type: 'historic-study' }),
    'anchor-rosette-horizontal': level => makeWallAnchor({ level, style: 'rosette-horizontal' }),
    'anchor-rosette-vertical': level => makeWallAnchor({ level, style: 'rosette-vertical' }),
    'anchor-bracket': level => makeWallAnchor({ level, style: 'bracket' })
  };

  const renderer = new T.WebGLRenderer();
  renderer.setSize(96, 96);
  const renderScene = new T.Scene();
  renderScene.add(new T.HemisphereLight(0xffffff, 0x938077, 2));
  const camera = new T.OrthographicCamera(-1, 1, 1, -1, .01, 80);
  function measure(model) {
    const bounds = new T.Box3().setFromObject(model);
    const centre = bounds.getCenter(new T.Vector3());
    const radius = bounds.getSize(new T.Vector3()).length() * .55;
    camera.left = camera.bottom = -radius;
    camera.right = camera.top = radius;
    camera.updateProjectionMatrix();
    camera.position.copy(centre).addScaledVector(new T.Vector3(1, .8, 2).normalize(), 3 * radius);
    camera.lookAt(centre);
    const parent = model.parent;
    renderScene.add(model);
    renderer.render(renderScene, camera);
    const { calls, triangles } = renderer.info.render;
    renderScene.remove(model);
    parent?.add(model);
    return { calls, triangles, min: bounds.min.toArray(), max: bounds.max.toArray() };
  }
  const loader = new GLTFLoader();
  const reference = {};
  if (!traction) for (const id of ['bin-large', 'bin-large-near', 'bin-small', 'bin-small-near', 'bin-recycling', 'cycle-rack']) {
    reference[id] = measure((await loader.loadAsync('/models/' + id + '.glb')).scene);
  }

  const rows = [];
  const scenes = Object.entries(traction ? poles : street).flatMap(([kind, make]) => levels.map(level => {
    const model = make(level);
    const original = !traction && labStreet[kind] !== make ? labStreet[kind](level) : model;
    const before = measure(original);
    if (original !== model) original.traverse(mesh => mesh.geometry?.dispose());
    model.name = kind + '--' + level;
    const wall = kind.startsWith('anchor-');
    Object.assign(model.userData, { kind, level, placement: wall ? 'wall' : 'ground' });
    if (wall) model.userData.wallNormal = [0, 0, 1];
    else Object.assign(model.userData, { groundY: 0, up: [0, 1, 0] });
    if (kind === 'pole-historic-study') model.userData.unverifiedStudy = true;
    model.traverse(mesh => {
      if (!mesh.isMesh) return;
      if (!mesh.geometry.index) {
        const indexed = mergeVertices(mesh.geometry);
        mesh.geometry.dispose();
        mesh.geometry = indexed;
      }
      if (mesh.material.transparent) mesh.userData.singlePass = true;
    });
    const scene = new T.Scene();
    scene.name = model.name + '-scene';
    scene.userData = { units: 'metres', attribution: traction ? 'Prague street assets lab, traction studies' : attribution };
    scene.add(model);
    rows.push({ id: model.name, before });
    return scene;
  }));

  const bytes = await new GLTFExporter().parseAsync(scenes, { binary: true });
  const roundTrip = await loader.parseAsync(bytes, '');
  for (const [i, scene] of roundTrip.scenes.entries()) {
    const [model] = scene.children, row = rows[i];
    if (model.name !== row.id) throw new Error('Missing model: ' + row.id);
    row.raw = measure(model);
  }
  for (const [i, scene] of roundTrip.scenes.entries()) {
    const [model] = scene.children, row = rows[i];
    model.traverse(mesh => {
      if (mesh.userData.singlePass) mesh.material.forceSinglePass = true;
    });
    row.packed = measure(model);
    if (!row.packed.calls || !row.packed.triangles) throw new Error('Empty model: ' + row.id);
  }
  renderer.dispose();
  const view = new Uint8Array(bytes);
  let binary = '';
  for (let i = 0; i < view.length; i += 16384) binary += String.fromCharCode(...view.subarray(i, i + 16384));
  return { model: btoa(binary), rows, reference };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lab", type=Path, required=True, help="original prague-street-assets-lab directory")
    parser.add_argument("--street", type=Path, default=STREET, help="output asset path")
    parser.add_argument("--traction-review", type=Path, help="optional local review GLB, e.g. reports/traction.glb")
    parser.add_argument("--audit", type=Path, help="write the measured WebGL counts as JSON")
    args = parser.parse_args()
    faulthandler.dump_traceback_later(60, exit=True)
    source = {
        name: (args.lab / name).read_text(encoding="utf-8").replace(
            "three/addons/BufferGeometryUtils.js", "three/addons/utils/BufferGeometryUtils.js")
        for name in MODULES
    }
    source["street_furniture_models.js"] = Path(__file__).with_name("street_furniture_models.js").read_text(encoding="utf-8")
    importmap = re.search(r'<script type="importmap">.*?</script>',
                          (ROOT / "index.html").read_text(encoding="utf-8"), re.S)[0]
    server_handler = functools.partial(Quiet, directory=args.lab)
    audit = {}
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), server_handler) as server, sync_playwright() as p:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}"
        browser, graphics = gpu.launch(p)
        print(graphics)
        page = browser.new_page()
        page.route(url + "/__pack.html", lambda route: route.fulfill(content_type="text/html", body=importmap))

        def serve_module(route):
            name = route.request.url.rsplit("/", 1)[-1]
            route.fulfill(content_type="application/javascript", body=source[name])

        for name in source:
            page.route(url + "/" + name, serve_module)
        page.goto(url + "/__pack.html")
        for path, traction in [(args.street, False), (args.traction_review, True)]:
            if path is None:
                continue
            pack = page.evaluate(PACK, {"traction": traction, "attribution": ATTRIBUTION})
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(pack.pop("model")))
            audit[path.name] = pack
            print(f"{path}: {len(pack['rows'])} scenes, {path.stat().st_size:,} bytes")
        browser.close()
        server.shutdown()
    if args.audit:
        args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
