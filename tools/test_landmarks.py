# SPDX-License-Identifier: AGPL-3.0-or-later
"""Landmarks past the fog (src/landmarks.js, #610): python -P -E tools/test_landmarks.py [--line 17]

Its own server on a free port; the line loaded in Chromium on the GPU (tools/gpu.py). Checks:
- the rule picked buildings, each LANDMARK_TALL m high or LANDMARK_HIGH m on high ground, and they are drawn in meshes of
  their own (userData.landmark, part 'buildings', still read by the lints as buildings);
- the camera's far plane and the landmarks' haze follow the weather's fog (dry 950 m, snow 480 m);
- the pass past the far plane draws: a frame from the start stop has more than the sky where the copy lies.
Needs data/line<N>.json (python -I tools/snapshot.py data-fetch); skips without it.
"""
import argparse
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


PROBE = r"""async () => {
  const lm = await import('/src/landmarks.js');
  const L = window.landmarks, meshes = [];
  window.world.traverse((o) => { if (o.isMesh && o.userData.landmark) meshes.push({ part: o.userData.part, building: !!o.userData.building }); });
  const out = { n: L?.list.length ?? 0, triangles: L?.triangles ?? 0, list: L?.list.slice(0, 400) ?? [], meshes: meshes.length,
    parts: [...new Set(meshes.map((m) => m.part))], buildings: meshes.every((m) => m.building),
    rule: [lm.LANDMARK_TALL, lm.LANDMARK_HIGH, lm.LANDMARK_RISE], stretch: lm.LANDMARK_STRETCH, base: window.world.userData.landmarks?.baseMed };
  out.dry = { far: Math.round(window.camera.far), fog: window.scene.fog.far, haze: lm.LANDMARK_UNIFORMS.uLandmarkFar.value };
  // the copy alone, drawn by the pass: pixels other than the sky's colour
  const r = window.renderer, cam = window.camera;
  window.landmarks.render(r, window.scene, cam);
  const gl = r.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
  gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
  let other = 0;
  for (let i = 0; i < px.length; i += 4) if (Math.abs(px[i] - px[0]) + Math.abs(px[i + 1] - px[1]) + Math.abs(px[i + 2] - px[2]) > 6) other++;
  out.passPixels = other;
  out.camera = [Math.round(cam.position.x), Math.round(-cam.position.z)];
  return out;
}"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    args = ap.parse_args()
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"(skipped: no data/line{args.line}.json; python -I tools/snapshot.py data-fetch)")
        return
    faulthandler.dump_traceback_later(600, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            # (preserveDrawingBuffer for the read of the pass's pixels)
            page.add_init_script("""{ const gc = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function (t, o) { return gc.call(this, t, (t === 'webgl2' || t === 'webgl') ? { ...(o || {}), preserveDrawingBuffer: true } : o); }; }""")
            page.goto(f"http://127.0.0.1:{server.server_port}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            def shift(weather):
                page.evaluate(f"""(() => {{ const s = document.getElementById('selStop'); s.value = '16'; s.dispatchEvent(new Event('change'));
                  document.getElementById('optWeather').value = '{weather}'; }})()""")
                page.click("#btnStart")
                page.wait_for_function("window.game && document.body.classList.contains('shift')", timeout=180000)
                page.evaluate("window.game.paused = true")
                page.wait_for_timeout(1000)
            # (the weather is set when a shift starts)
            shift("snow")
            snow = page.evaluate("""async () => { const lm = await import('/src/landmarks.js');
              return { far: Math.round(window.camera.far), fog: window.scene.fog.far, haze: lm.LANDMARK_UNIFORMS.uLandmarkFar.value }; }""")
            page.evaluate("document.getElementById('btnToMenu').click()")
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=30000)
            shift("dry")
            r = page.evaluate(PROBE)
            r["snow"] = snow
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps({k: v for k, v in r.items() if k != "list"}))
    tall, high, rise = r["rule"]
    fails = []
    if not r["n"] or not r["meshes"]:
        fails.append(f"no landmarks: {r['n']} buildings, {r['meshes']} meshes")
    bad = [b for b in r["list"] if not (b[2] >= tall or (b[2] >= high and b[3] >= r["base"] + rise))]
    if bad:
        fails.append(f"buildings outside the rule: {bad[:5]}")
    if r["parts"] != ["buildings"] or not r["buildings"]:
        fails.append(f"landmark meshes: parts {r['parts']}, read as buildings {r['buildings']}")
    for w, fog in (("dry", 950), ("snow", 480)):
        x = r[w]
        if x["fog"] != fog or not (fog < x["far"] <= fog * 1.05) or x["haze"] != fog * r["stretch"]:
            fails.append(f"{w}: far plane {x['far']}, fog {x['fog']}, haze {x['haze']}")
    if r["passPixels"] < 50:
        fails.append(f"the pass past the far plane drew {r['passPixels']} pixels besides the sky at {r['camera']}")
    if fails:
        sys.exit("; ".join(fails))
    print(f"landmarks on line {args.line}: {r['n']} by the rule in meshes of their own, far plane and haze by the weather, "
          f"the far pass draws ({r['passPixels']} pixels): pass")


if __name__ == "__main__":
    main()
