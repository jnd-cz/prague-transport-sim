"""Render a paused view and the same camera in a reference checkout (#158).

    python -P -E tools/shot.py --line 17 --s 5064 --view cab --ref origin/main
    python -P -E tools/shot.py --line 17 --s 5064 --view review --ref ../other-checkout

Writes individual PNGs, a labelled side-by-side PNG, and camera/data hashes to reports/shots/.
Git references are exported temporarily and use verified published files from TRAMDATA_CACHE.
Directories use their working data. Both sites use their own free localhost port, sequential pages,
the same seed, no moving traffic and no HUD. The reference camera is locked to the current camera.
"""
import argparse
from contextlib import contextmanager
import functools
import http.server
import json
import math
from pathlib import Path
import sys
import shutil
import threading
import time
import tempfile

from PIL import Image, ImageDraw
from playwright.sync_api import Error as PlaywrightError, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
from data_reference import ROOT, checkout, digest, git


class Quiet(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *args):
        pass


@contextmanager
def site(root):
    # The kernel reserves this ephemeral socket before any browser is started.
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


HIDE = 'body > :not(#view):not(#gl):not(#cab) { display:none !important }'


def capture(browser, root, line, s, view, output, timeout, pose=None, target=None):
    context = browser.new_context(viewport={'width': 1280, 'height': 720}, device_scale_factor=1)
    context.add_init_script('''window.headless = true;
      let state = 158; Math.random = () => ((state = (Math.imul(state, 1664525) + 1013904223) >>> 0) / 4294967296);''')
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    deadline = time.monotonic() + timeout

    def remaining():
        return max(1, (deadline - time.monotonic()) * 1000)

    try:
        with site(root) as url:
            print(f'Loading line {line}, {view}: {root}', flush=True)
            page.goto(f'{url}/?line={line}&seed=158&keepgeo', timeout=remaining())
            page.wait_for_function("document.getElementById('loading')?.classList.contains('hidden') && "
                                   "!document.getElementById('menu')?.classList.contains('hidden')", timeout=remaining())
            page.select_option('#optWeather', 'dry')
            page.select_option('#optObst', 'off')
            if page.locator('#selStop').count():
                page.select_option('#selStop', index=0)
                page.select_option('#selTrip', index=0)
            if page.locator('#optTemp').count():
                page.select_option('#optTemp', 'autumn')
            page.click('#btnStart', timeout=remaining())
            page.wait_for_function('window.game && window.camera', timeout=remaining())
            point = page.evaluate('''s => {
              const g = window.game;
              if (s < 0 || s > g.route.length) throw new Error(`s ${s} outside route 0..${g.route.length}`);
              g.tram.s = s; g.tram.v = 0; g.tram.a = 0; g.paused = true;
              window.traffic.dispose(); window.traffic.update = () => {};
              const p = g.route.at(s), h = g.route.heading(s);
              return {x: p.x, y: p.y, yaw: Math.atan2(h.hx, h.hy) * 180 / Math.PI};
            }''', s)
            target = target or point
            if view == 'review':
                at = f"{target['x']},{target['y']},{target['yaw']},45,60"
                page.goto(f'{url}/?line={line}&seed=158&keepgeo&review&at={at}', timeout=remaining())
                page.wait_for_function('window.review', timeout=remaining())
                page.evaluate('''() => { window._shotReady = false;
                  window.review.ready.then(() => { window._shotReady = true; }); }''')
                page.wait_for_function('window._shotReady', timeout=remaining())
                page.add_style_tag(content=HIDE)
                page.evaluate('window.review._render()')
            else:
                if view == 'chase':
                    # V is handled before pause. The zero wheel event makes the native orbit snap
                    # to its target, rather than easing from the menu preview camera.
                    page.evaluate('window.game.paused = false')
                    page.keyboard.press('v')
                    page.evaluate("window.game.paused = true; document.getElementById('gl').dispatchEvent(new WheelEvent('wheel', {deltaY:0}));")
                page.add_style_tag(content=HIDE)
                count = page.evaluate('window.drawCount')
                page.evaluate('window.headless = false')
                page.wait_for_function('n => window.drawCount >= n + 2', arg=count, timeout=remaining())
                page.evaluate('window.headless = true')
            info = page.evaluate('''pose => {
              const R = window.review, cam = R ? R.camera : window.camera;
              cam.clearViewOffset(); cam.updateProjectionMatrix();
              const native = {position: cam.position.toArray(), quaternion: cam.quaternion.toArray(),
                              up: cam.up.toArray(), fov: cam.fov, near: cam.near, far: cam.far,
                              zoom: cam.zoom, aspect: cam.aspect};
              if (pose) {
                cam.position.fromArray(pose.position); cam.quaternion.fromArray(pose.quaternion);
                cam.up.fromArray(pose.up); Object.assign(cam, {fov:pose.fov, near:pose.near, far:pose.far,
                                                             zoom:pose.zoom, aspect:pose.aspect});
                cam.clearViewOffset(); cam.updateProjectionMatrix(); cam.updateMatrixWorld();
              }
              if (R) R._render = () => {}; // the captured camera stays fixed through the next draw
              const g = window.game;
              return {camera: pose || native, native_camera: native, target: R ? R.T : null,
                      tram_s: g ? g.tram.s : null, paused: g ? g.paused : true, view_offset_enabled:!!cam.view?.enabled,
                      canvas_visible: document.getElementById('gl').getBoundingClientRect().width > 0,
                      hud_visible: [...document.body.children].some(e => !['view','gl','cab'].includes(e.id) &&
                        getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().height > 0)};
            }''', pose)
            if not info['canvas_visible']:
                raise RuntimeError('the scene canvas is hidden; refusing a blank screenshot')
            count = page.evaluate('window.drawCount')
            page.wait_for_function('n => window.drawCount > n', arg=count, timeout=remaining())
            page.screenshot(path=str(output), timeout=remaining())
            if errors:
                raise RuntimeError('; '.join(errors))
            inputs = [*sorted((root / 'data').glob(f'line{line}.*')), root/'data/truth.json', root/'data/MANIFEST.json']
            info.update(target_xy=target, page_errors=errors, image_sha256=digest(output),
                        settings={'viewport':[1280,720], 'seed':158, 'trip_index':0, 'weather':'dry'},
                        data_sha256={p.name: digest(p) for p in inputs if p.is_file()})
            return info
    finally:
        context.close()


def combine(current, reference, output, labels):
    with Image.open(current) as a, Image.open(reference) as b:
        image = Image.new('RGB', (a.width + b.width, max(a.height, b.height) + 30), '#20242b')
        image.paste(a, (0, 30))
        image.paste(b, (a.width, 30))
        draw = ImageDraw.Draw(image)
        draw.text((10, 8), labels[0], fill='white')
        draw.text((a.width + 10, 8), labels[1], fill='white')
        image.save(output)


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--line', type=int, required=True)
    ap.add_argument('--s', type=float, required=True)
    ap.add_argument('--view', choices=('cab', 'chase', 'review'), default='cab')
    ap.add_argument('--ref', default='origin/main', help='reference directory or git revision (default origin/main)')
    ap.add_argument('--cache', help='read-only machine cache (default TRAMDATA_CACHE)')
    ap.add_argument('--timeout', type=float, default=240, help='seconds per capture, including loading')
    ap.add_argument('--out', type=Path, default=root / 'reports/shots')
    a = ap.parse_args(argv)
    if a.line <= 0 or not math.isfinite(a.s) or a.s < 0 or not math.isfinite(a.timeout) or a.timeout <= 0:
        ap.error('s must be finite and nonnegative; timeout must be finite and positive')
    a.out.mkdir(parents=True, exist_ok=True)
    stem = f'line{a.line}-s{a.s:g}-{a.view}'
    try:
        reference_rev = (git(root, 'rev-parse', '--verify', a.ref + '^{commit}')
                         if a.ref and not Path(a.ref).is_dir() else None)
        with tempfile.TemporaryDirectory(prefix='.shot-', dir=a.out) as tmp, sync_playwright() as pw:
            work = Path(tmp)
            current = work / f'{stem}-current.png'
            browser = pw.chromium.launch(headless=True, args=['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
            try:
                now = capture(browser, root, a.line, a.s, a.view, current, a.timeout)
                report = {'line': a.line, 's': a.s, 'view': a.view, 'current': now,
                          'current_commit': git(root, 'rev-parse', 'HEAD'),
                          'working_changes': git(root, 'status', '--porcelain', '--', 'src', 'index.html', 'data/truth.json', 'data/MANIFEST.json')}
                if a.ref:
                    reference = work / f'{stem}-reference.png'
                    with checkout(root, reference_rev or a.ref, a.cache) as other:
                        report['reference'] = capture(browser, other, a.line, a.s, a.view, reference, a.timeout,
                                                      pose=now['camera'], target=now['target_xy'])
                        if reference_rev is None:
                            try:
                                report['reference_commit'] = git(other, 'rev-parse', 'HEAD')
                                report['reference_working_changes'] = git(other, 'status', '--porcelain', '--',
                                                                         'src', 'index.html', 'data/truth.json', 'data/MANIFEST.json')
                            except (OSError, ValueError):
                                report['reference_commit'] = None  # an unpacked distribution need not be a git checkout
                    report['reference_spec'] = a.ref
                    if not Path(a.ref).is_dir():
                        report['reference_commit'] = reference_rev
                    pair = work / f'{stem}-pair.png'
                    combine(current, reference, pair, ['Current checkout', f'Reference: {a.ref}'])
                    print(f'Pair: {a.out / pair.name}')
                for image in work.glob('*.png'):
                    # Temp directories are private on Windows. Copy to an atomic sibling in the
                    # report directory so images inherit its access rights and the user can open them.
                    with image.open('rb') as src, replacing(a.out / image.name, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                with replacing(a.out / f'{stem}.json', 'w', encoding='utf-8') as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                print(f'Shot: {a.out / current.name}')
                return report
            finally:
                browser.close()
    except (OSError, ValueError, RuntimeError, PlaywrightError) as e:
        ap.exit(1, f'shot: {e}\n')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
