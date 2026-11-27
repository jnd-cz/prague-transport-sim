# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check and optionally render all nine IPR bench models without loading a line."""

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
  const { makeIprBench } = await import('/src/benches.js');
  const variants = ['backrest', 'armrests', 'backless'];
  const levels = ['near', 'middle', 'far'];
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  renderer.setSize(1020, 630);
  document.body.style.margin = '0';
  document.body.append(renderer.domElement);
  renderer.setScissorTest(true);
  const camera = new THREE.OrthographicCamera(-1.27, 1.27, .71, -.71, .1, 20);
  camera.position.set(1.35, 1.48, 2.6);
  camera.lookAt(0, .44, 0);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe9e9e5);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x93887d, 2.0));
  const sun = new THREE.DirectionalLight(0xfff5e6, 2.2);
  sun.position.set(1, 4, 2);
  scene.add(sun);

  return variants.map((variant, row) => levels.map((level, col) => {
    const model = makeIprBench(variant, level);
    const bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3()).toArray();
    const triangles = model.children.map(({ geometry: g }) => (g.index ?? g.attributes.position).count / 3);
    const positions = model.children.flatMap(m => Array.from(m.geometry.attributes.position.array));
    const materials = model.children.map(m => m.material.name);

    // Draw the two material groups as instances, as the feature layer will do.
    const batch = model.children.map(mesh => {
      const instances = new THREE.InstancedMesh(mesh.geometry, mesh.material, 1);
      instances.setMatrixAt(0, new THREE.Matrix4());
      scene.add(instances);
      return instances;
    });
    renderer.setViewport(340 * col, 210 * (2 - row), 340, 210);
    renderer.setScissor(340 * col + 2, 210 * (2 - row) + 2, 336, 206);
    renderer.render(scene, camera);
    const calls = renderer.info.render.calls;
    scene.remove(...batch);
    return { variant, level, size, floor: bounds.min.y, calls, triangles, materials,
      finite: positions.every(Number.isFinite) };
  }));
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, help="save a PNG, with variants down and detail levels across")
    args = parser.parse_args()
    faulthandler.dump_traceback_later(60, exit=True)
    handler = functools.partial(Quiet, directory=ROOT)
    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server, sync_playwright() as p:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_port}/__benches.html"
        browser, _ = gpu.launch(p)
        page = browser.new_page(viewport={"width": 1020, "height": 630})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        importmap = re.search(r'<script type="importmap">.*?</script>',
                              (ROOT / "index.html").read_text(encoding="utf-8"), re.S)[0]
        page.route(url, lambda route: route.fulfill(content_type="text/html", body=f"<!doctype html>{importmap}"))
        page.goto(url)
        variants = page.evaluate(CHECK)
        if args.preview:
            page.screenshot(path=args.preview)
        browser.close()
        server.shutdown()
    assert not errors, errors

    for row in variants:
        counts = [sum(model["triangles"]) for model in row]
        assert counts[0] > counts[1] > counts[2] > 0, row
        assert counts[0] < 1_000 and counts[2] < 450, row
        for model in row:
            expected = (1.80, .453, .548) if model["variant"] == "backless" else (1.80, .873, .656)
            assert all(abs(a - b) < .015 for a, b in zip(model["size"], expected)), model
            assert abs(model["floor"]) < .001, model
            assert model["finite"] and model["calls"] == 2 and model["materials"] == ["metal", "wood"], model
        print(f'{row[0]["variant"]}: {counts} triangles, two instanced draw calls per level')
    for back, arms in zip(*variants[:2]):
        assert back["triangles"][0] < arms["triangles"][0], (back, arms)
        assert back["triangles"][1] == arms["triangles"][1], (back, arms)


if __name__ == "__main__":
    main()
