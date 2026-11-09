"""Chromium's WebGL on the machine's GPU where it has one, else in software (#411).

    from gpu import launch
    browser, renderer = launch(pw)                 # headless, on the GPU when WebGL names a real adapter
    browser, renderer = launch(pw, gpu=False)      # SwiftShader, the software path

What draws pictures takes the GPU: tools/shot.py, the mirror's screenshots, tools/frametime.py's headless test. A
headless Chromium can use the GPU (ANGLE on Direct3D 11): 60 frames of a heavy full-screen draw took 0.28 s on the
dev PC's Intel Arc A770 and 47.5 s on SwiftShader, which Playwright's headless Chromium uses unless told otherwise.
The checks (tools/headless.py) draw nothing at all. Where the GPU path gives no real adapter (another system, no
GPU, a session without one), it falls back to SwiftShader and says so: pictures from either are compared only with
pictures taken the same way.
"""
import sys

SOFTWARE = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
HARDWARE = ["--use-angle=d3d11", "--ignore-gpu-blocklist", "--enable-gpu-rasterization"]

RENDERER = """() => {
  const gl = document.createElement('canvas').getContext('webgl2') || document.createElement('canvas').getContext('webgl');
  if (!gl) return null;
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
}"""


def renderer(browser):
    """The WebGL renderer a page of this browser reports (None without WebGL)."""
    page = browser.new_page()
    try:
        return page.evaluate(RENDERER)
    finally:
        page.close()


def software(name):
    return name is None or "SwiftShader" in name


def launch(pw, headless=True, gpu=True, args=(), quiet=False):
    """(browser, its WebGL renderer): on the GPU when asked and WebGL names a real adapter there, else SwiftShader."""
    if gpu and sys.platform == "win32":
        browser = pw.chromium.launch(headless=headless, args=[*HARDWARE, *args])
        name = renderer(browser)
        if not software(name):
            return browser, name
        browser.close()
        if not quiet:
            print(f"note: no GPU for WebGL ({name or 'no WebGL'}): drawing in software (SwiftShader)", flush=True)
    browser = pw.chromium.launch(headless=headless, args=[*SOFTWARE, *args])
    return browser, renderer(browser)
