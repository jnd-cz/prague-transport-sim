# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check and render the nine IPR shelter models without loading a line."""

import argparse
import faulthandler
import functools
import http.server
from pathlib import Path
import re
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

CHECK = """async () => {
  const THREE = await import('three');
  const { makeIprShelter } = await import('/src/shelters.js');
  const variants = ['P.1', 'P.2', 'P.3', 'P.4', 'P.12', 'P.5', 'P.6', 'P.7', 'P.11'];
  const levels = ['near', 'middle', 'far'];
  const name = 'Palackého náměstí\\n(nábřeží)';
  const width = 376, height = 180;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(width * 3, height * (variants.length + 1));
  renderer.setScissorTest(true);
  const sheet = document.createElement('main');
  sheet.append(renderer.domElement);
  document.body.append(sheet);
  for (const [i, text] of Object.entries(levels)) label(text, width * (Number(i) + .5), -18);
  for (const [i, text] of Object.entries(variants)) label(text, -31, height * (Number(i) + .5));
  function label(text, x, y) {
    const element = document.createElement('span');
    element.textContent = text;
    element.style.left = x + 'px';
    element.style.top = y + 'px';
    sheet.append(element);
  }

  const camera = new THREE.OrthographicCamera(-4.4, 4.4, 2.11, -2.11, .1, 30);
  camera.position.set(2.9, 4.3, 9.8);
  camera.lookAt(0, 1.25, 0);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe8ebeb);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xb7aba0, 2.2));
  const sun = new THREE.DirectionalLight(0xfff5e8, 2);
  sun.position.set(2, 4, 4);
  scene.add(sun);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(24, 16),
    new THREE.MeshStandardMaterial({ color: 0xcbcbc4, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -.005;
  const wall = new THREE.Mesh(new THREE.BoxGeometry(5.45, 3.04, .15),
    new THREE.MeshStandardMaterial({ color: 0xbec2c0, roughness: 1 }));
  wall.position.set(0, 1.52, -.929 - .075);
  const rearRay = (x, y) => new THREE.Raycaster(new THREE.Vector3(x, y, 0), new THREE.Vector3(0, 0, -1));

  const results = variants.map((variant, row) => levels.map((level, col) => {
    const model = makeIprShelter(variant, level, name);
    model.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3()).toArray();
    const triangles = model.children.reduce((n, { geometry: g }) => n + (g.index ?? g.attributes.position).count / 3, 0);
    const types = model.children.map(mesh => mesh.name);
    const endPanes = model.children.filter(mesh => mesh.name === 'end-glass').map(mesh => mesh.geometry.parameters.width);
    const standardPassage = variant === 'P.2' || variant === 'P.4';
    const gap = standardPassage ? -1.20 : .25;
    const rearWall = rearRay(gap, 1.35).intersectObject(model, true).some(hit => hit.object.name === 'rear-glass');
    const openingUnderFascia = rearRay(gap, 2.13).intersectObject(model, true).length === 0;
    const passagePost = rearRay(-.61, 1.35).intersectObject(model.getObjectByName('frame')).length > 0;
    const seat = model.getObjectByName('seats');
    const seatXs = seat ? Array.from(seat.geometry.attributes.position.array).filter((x, i) => i % 3 === 0) : [];
    const twoBays = seatXs.some(x => x < -.65) && seatXs.some(x => x > .65) && seatXs.every(x => Math.abs(x) > .1);
    const seatClear = seatXs.every(x => x > -.55);
    const sign = model.getObjectByName('stop-name');
    const signBounds = new THREE.Box3().setFromObject(sign);
    const centre = signBounds.getCenter(new THREE.Vector3());
    const faces = [1, -1].map(side => new THREE.Raycaster(
      centre.clone().add(new THREE.Vector3(0, 0, side * .5)), new THREE.Vector3(0, 0, -side))
      .intersectObject(sign).length > 0);
    const { width: w, height: h } = sign.material.map.image;
    const ctx = sign.material.map.image.getContext('2d');
    const inkRows = [];
    for (let y = 0; y < h; y++) {
      if (ctx.getImageData(0, y, w, 1).data.some((v, i) => i % 4 === 3 && v > 80)) inkRows.push(y);
    }
    const twoLinesFit = inkRows[0] > 6 && inkRows[0] < h / 2 - 12
      && inkRows.at(-1) > h / 2 + 12 && inkRows.at(-1) < h - 6
      && !inkRows.some(y => Math.abs(y - h / 2) < 3);
    const plain = makeIprShelter(variant, level);
    const labelOptional = !plain.getObjectByName('stop-name');

    scene.add(model);
    const backing = variant === 'P.11' ? wall : floor;
    scene.add(backing);
    renderer.setViewport(width * col, height * (variants.length - row), width, height);
    renderer.setScissor(width * col + 2, height * (variants.length - row) + 2, width - 4, height - 4);
    renderer.render(scene, camera);
    const calls = renderer.info.render.calls - 1;  // one backing surface
    scene.remove(model, backing);
    return { variant, level, size, min: bounds.min.toArray(), max: bounds.max.toArray(),
      triangles, calls, types, rearWall, endPanes, twoBays, twoLinesFit, faces, labelOptional, openingUnderFascia,
      passagePost, seatClear };
  }));

  const detail = new THREE.OrthographicCamera(-1.25, 1.25, .59, -.59, .1, 20);
  for (const [col, [variant, side, caption]] of [
    ['P.1', 1, 'P.1 · front'], ['P.1', -1, 'P.1 · street side'], ['P.11', 1, 'P.11 · outward face'],
  ].entries()) {
    const model = makeIprShelter(variant, 'near', name);
    const sign = new THREE.Box3().setFromObject(model.getObjectByName('stop-name')).getCenter(new THREE.Vector3());
    detail.position.set(sign.x, sign.y + .03, side * 5);
    detail.lookAt(sign);
    scene.add(model);
    if (variant === 'P.11') scene.add(wall);
    renderer.setViewport(width * col, 18, width, height - 18);
    renderer.setScissor(width * col + 2, 18, width - 4, height - 20);
    renderer.render(scene, detail);
    scene.remove(model, wall);
    label(caption, width * (col + .5), height * (variants.length + 1) - 8);
  }

  // Test the rendering contract for the feature layer with two independently named stops.
  // Keep their alpha-blended surfaces sorted as separate objects.
  const pair = ['Palackého náměstí', 'Kobylisy'].map(stop => makeIprShelter('P.1', 'near', stop));
  pair[0].position.x = -2.15;
  pair[1].position.x = 2.15;
  const target = new THREE.WebGLRenderTarget(220, 96);
  renderer.setScissorTest(false);
  renderer.setRenderTarget(target);
  scene.add(...pair);
  renderer.render(scene, camera);
  const separate = renderer.info.render.calls;
  const trianglesBefore = renderer.info.render.triangles;
  const opaque = pair[0].children.filter(mesh => !mesh.material.transparent);
  for (const mesh of opaque) {
    const instances = new THREE.InstancedMesh(mesh.geometry, mesh.material, pair.length);
    pair.forEach((model, i) => {
      instances.setMatrixAt(i, model.matrix);
      model.remove(model.getObjectByName(mesh.name));
    });
    scene.add(instances);
  }
  renderer.render(scene, camera);
  const instanced = renderer.info.render.calls;
  const sameTriangleCount = renderer.info.render.triangles === trianglesBefore;
  const differentNames = pair[0].getObjectByName('stop-name').material.map !== pair[1].getObjectByName('stop-name').material.map;
  renderer.setRenderTarget(null);
  target.dispose();
  return { results, pair: { separate, instanced, differentNames, sameTriangleCount } };
}"""

HTML = """<!doctype html><style>
body { margin: 0; background: #fff; font: 600 15px system-ui; color: #2a3235; }
main { position: relative; margin: 36px 10px 10px 64px; width: max-content; }
main span { position: absolute; transform: translate(-50%,-50%); white-space: nowrap; }
canvas { display: block; }
</style>"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, help="save the contact sheet as a PNG or JPEG")
    args = parser.parse_args()
    faulthandler.dump_traceback_later(60, exit=True)
    handler = functools.partial(Quiet, directory=ROOT)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as p:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/__shelters.html"
        browser, _ = gpu.launch(p)
        page = browser.new_page(viewport={"width": 1202, "height": 1846})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        importmap = re.search(r'<script type="importmap">.*?</script>',
                              (ROOT / "index.html").read_text(encoding="utf-8"), re.S)[0]
        page.route(url, lambda route: route.fulfill(content_type="text/html", body=HTML + importmap))
        page.goto(url)
        measured = page.evaluate(CHECK)
        if args.preview:
            page.screenshot(path=args.preview)
        browser.close()
        server.shutdown()
    assert not errors, errors

    for row in measured["results"]:
        variant = row[0]["variant"]
        counts = [model["triangles"] for model in row]
        calls = [model["calls"] for model in row]
        assert counts[0] > counts[1] > counts[2] and counts[0] <= 800, row
        assert calls[0] >= calls[1] >= calls[2] and calls[0] <= 12, row
        for model in row:
            wall = variant == "P.11"
            island = variant == "P.12"
            extended = variant in {"P.5", "P.6", "P.7"}
            citylight = variant in {"P.1", "P.2", "P.5", "P.6"}
            standard_passage = variant in {"P.2", "P.4"}
            w, h, d = model["size"]
            assert abs(w - (7.080 if extended else 4.040)) < .001, model
            assert abs(d - (1.438 if island else 1.858)) < .001, model
            assert abs(model["max"][1] - 2.455) < .001, model
            assert (h < .72 and model["min"][1] >= 1.75) if wall else abs(model["min"][1]) < .001, model
            assert model["types"].count("frame") == 1 and model["types"].count("canopy") == 1, model
            assert model["twoBays"] == extended and ("seats" in model["types"]) == (not (wall or island)), model
            assert ("citylight" in model["types"]) == citylight, model
            assert model["rearWall"] == (variant in {"P.1", "P.3", "P.6", "P.7", "P.12"}), model
            assert model["endPanes"] == ([] if wall or island else [1.08] if citylight else [.58, .58]), model
            assert model["twoLinesFit"] and model["labelOptional"] and model["faces"] == [True, not wall], model
            if standard_passage or variant == "P.5":
                assert model["openingUnderFascia"], model
            if standard_passage:
                assert model["passagePost"] and model["seatClear"], model
        print(f"{variant}: {counts} triangles, {calls} draw calls with a stop label")
    pair = measured["pair"]
    assert pair == {"separate": 18, "instanced": 15, "differentNames": True, "sameTriangleCount": True}, pair
    print("Two differently named near P.1 shelters: 18 to 15 draw calls with opaque instancing")


if __name__ == "__main__":
    main()
