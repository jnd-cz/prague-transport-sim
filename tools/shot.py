# SPDX-License-Identifier: AGPL-3.0-or-later
"""Render a paused view and the same camera in a reference checkout (#158).

    python -P -E tools/shot.py --line 17 --s 5064 --view cab --ref origin/main
    python -P -E tools/shot.py --line 17 --s 5064 --view review --ref ../other-checkout
    python -P -E tools/shot.py --line 17 --s 0 --view review --at 3185.9,3756.8 --dist 25   # a place off the route
    python -P -E tools/shot.py --line 17 --s 5064 --view chase --vehicle t3simple --livery sample.t3simple-green
    python -P -E tools/shot.py --line 22 --s 6330 --view cab --weather snow   # bare crowns, snow on the ground
    python -P -E tools/shot.py --line 37 --s 3420 --view cab --plain --ref .   # as a player sees it (the ground's
                                                                   # tiles, #30) against every tile in detail
    python -P -E tools/shot.py --line 17 --s 12568 --view review --at=-755,-1450 --ref . --overlay reports/places/rasinovo-quay/overlay
                                                                   # a place's ground (tools/ground_place.py --overlay,
                                                                   # #757) against the checkout's own
    python -P -E tools/shot.py --line 17 --s 5064 --view cab --ref . --params gfx=front   # what a drawing switch
                                                                   # changes (src/gfx.js, #705)

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
import re
import sys
import shutil
import threading
import time
import tempfile

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Error as PlaywrightError, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atomic import replacing
import gpu
import snapshot
from data_reference import ROOT, checkout, digest, git


class Quiet(http.server.SimpleHTTPRequestHandler):
    overlay = None  # a folder whose files stand in for the checkout's at the same paths (--overlay)

    def translate_path(self, path):
        p = super().translate_path(path)
        if self.overlay:
            try:
                q = Path(self.overlay) / Path(p).resolve().relative_to(Path(self.directory).resolve())
            except ValueError:
                return p
            if q.is_file():
                return str(q)
        return p

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, *args):
        pass


@contextmanager
def site(root, overlay=None):
    # The kernel reserves this ephemeral socket before any browser is started.
    handler = type('Overlaid', (Quiet,), {'overlay': str(overlay)}) if overlay else Quiet
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(handler, directory=str(root)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


HIDE = 'body > :not(#view):not(#gl):not(#cab) { display:none !important }'
# The game internals this tool drives (src/main.js, run.js, review.js); a renamed one fails here
# by name instead of as a timeout or a blank picture.
HOOKS = {'game': ['window.game.route.at', 'window.game.route.heading', 'window.game.tram',
                  'window.run.trafficView.dispose', 'window.drawCount'],
         'review': ['window.review.ready', 'window.review.T', 'window.review._render', 'window.review.camera']}
BAR = 36  # label strip above the pair


def require(page, part):
    missing = page.evaluate('''names => names.filter(n => {
      try { return (0, eval)(n) === undefined; } catch { return true; } })''', HOOKS[part])
    if missing:
        raise RuntimeError(f"the page lacks {', '.join(missing)}: shot.py drives these, update it with the game")


def font(size=20):
    for name in ('DejaVuSans.ttf', 'arial.ttf', 'Arial.ttf', 'LiberationSans-Regular.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def capture(browser, root, line, s, view, output, timeout, pose=None, target=None, dist=60, pitch=45, picks=(), plain=False, weather='dry',
            overlay=None, params=''):
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
        with site(root, overlay) as url:
            print(f'Loading line {line}, {view}: {root}' + (f' under {overlay}' if overlay else ''), flush=True)
            keep = '' if plain else '&keepgeo'  # (plain: the ground's tiles round the camera only, as a player loads, #30)
            keep += ''.join(f'&{q}' for q in params.split('&') if q)  # (--params: a drawing switch, src/gfx.js)
            page.goto(f'{url}/?line={line}&seed=158{keep}', timeout=remaining())
            page.wait_for_function("document.getElementById('loading')?.classList.contains('hidden') && "
                                   "!document.getElementById('menu')?.classList.contains('hidden')", timeout=remaining())
            page.select_option('#optWeather', weather)
            page.select_option('#optObst', 'off')
            if page.locator('#selStop').count():
                page.select_option('#selStop', index=0)
                page.select_option('#selTrip', index=0)
            if page.locator('#optTemp').count():
                page.select_option('#optTemp', 'autumn')
            # the menu's vehicle and livery, where this checkout offers them (a reference before #529 has no liveries)
            for sel, value in picks:
                if value and page.locator(f'{sel} option[value="{value}"]').count():
                    page.select_option(sel, value)
                    page.dispatch_event(sel, 'change')
            page.click('#btnStart', timeout=remaining())
            page.wait_for_function('window.game && window.camera', timeout=remaining())
            require(page, 'game')
            point = page.evaluate('''s => {
              const g = window.game;
              if (s < 0 || s > g.route.length) throw new Error(`s ${s} outside route 0..${g.route.length}`);
              g.tram.s = s; g.tram.v = 0; g.tram.a = 0; g.paused = true;
              window.run.trafficView.dispose(); window.traffic.update = () => {};
              const p = g.route.at(s), h = g.route.heading(s);
              return {x: p.x, y: p.y, yaw: Math.atan2(h.hx, h.hy) * 180 / Math.PI};
            }''', s)
            target = target or point
            if view == 'review':
                at = f"{target['x']},{target['y']},{target['yaw']},{pitch},{dist}"
                page.goto(f'{url}/?line={line}&seed=158{keep}&review&at={at}', timeout=remaining())
                page.wait_for_function('window.review', timeout=remaining())
                require(page, 'review')
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
            if plain:  # (the window round the captured camera and the route ahead, waited for: src/groundFile.js)
                page.evaluate('''async () => {
                  const g = window.groundTiles, cam = window.review ? window.review.camera : window.camera;
                  if (!g) return;
                  const pts = [[cam.position.x, -cam.position.z]], r = window.game?.route, s = window.game?.tram.s ?? 0;
                  if (r) for (let d = 0; d <= 1000; d += 100) { const p = r.at(Math.min(r.length, s + d)); pts.push([p.x, p.y]); }
                  g.last = Infinity;
                  await g.update(pts, g.reach(window.scene?.fog.far ?? 950));
                  g.drain();
                }''')
            # the small things drawn near the camera (src/nearbatch.js, #610) refill only once the camera has moved a
            # tenth of their range: refilled round the captured camera before the drawn frame, so the picture does not
            # hold where the camera was before it (#689)
            page.evaluate('() => { for (const s of window.nearBatches?.sets ?? []) s.dirty = true; }')
            count = page.evaluate('window.drawCount')
            page.wait_for_function('n => window.drawCount > n', arg=count, timeout=remaining())
            page.screenshot(path=str(output), timeout=remaining())
            # what of them the picture holds: per set its range, drawn and kept instances, and how far its fill is from
            # the camera (0: filled round it)
            info['near'] = page.evaluate('''() => {
              const nb = window.nearBatches, cam = window.review ? window.review.camera : window.camera;
              return nb ? Object.fromEntries(nb.sets.map((s) => [s.name, {range: Math.round(s.range), drawn: s.mesh.count,
                total: s.total, fill_from_camera: s.at ? Math.round(Math.hypot(s.at[0] - cam.position.x, s.at[1] - cam.position.z) * 10) / 10 : null}])) : null;
            }''')
            if errors:
                raise RuntimeError('; '.join(errors))
            inputs = [*sorted((root / 'data').glob(f'line{line}.*')), root/'data/truth.json', root/'data/MANIFEST.json']
            info.update(target_xy=target, page_errors=errors, image_sha256=digest(output),
                        settings={'viewport':[1280,720], 'seed':158, 'trip_index':0, 'weather':weather},
                        data_sha256={p.name: digest(p) for p in inputs if p.is_file()})
            return info
    finally:
        context.close()


def combine(current, reference, output, labels):
    with Image.open(current) as a, Image.open(reference) as b:
        image = Image.new('RGB', (a.width + b.width, max(a.height, b.height) + BAR), '#20242b')
        image.paste(a, (0, BAR))
        image.paste(b, (a.width, BAR))
        draw, f = ImageDraw.Draw(image), font()
        draw.text((12, BAR // 2), labels[0], fill='white', font=f, anchor='lm')
        draw.text((a.width + 12, BAR // 2), labels[1], fill='white', font=f, anchor='lm')
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
    ap.add_argument('--at', help='review: the place to look at, X,Y in the local frame (default the route at s)')
    ap.add_argument('--dist', type=float, default=60, help='review: the camera\'s distance in m (default 60)')
    ap.add_argument('--pitch', type=float, default=45, help='review: degrees down from level (default 45)')
    ap.add_argument('--yaw', type=float, default=0, help='review with --at: the heading looked along, degrees')
    ap.add_argument('--plain', action='store_true', help='the current checkout without ?keepgeo: the ground as a player sees it (#30)')
    ap.add_argument('--ref-plain', action='store_true', help='the reference without ?keepgeo')
    ap.add_argument('--vehicle', help='the tram model picked in the menu (assets/vehicles.json; default the first)')
    ap.add_argument('--weather', choices=('dry', 'rain', 'leaves', 'snow'), default='dry',
                    help="the menu's weather in both pictures (snow: winter, bare crowns; leaves: autumn)")
    ap.add_argument('--livery', help='the livery picked in the menu (#529; default the vehicle\'s own)')
    ap.add_argument('--overlay', type=Path, help='a folder whose files stand in for the current checkout\'s at the same paths '
                    '(a place\'s ground: tools/ground_place.py --overlay); the reference is drawn without it')
    ap.add_argument('--params', default='', help='added to the current checkout\'s page address, e.g. gfx=front (src/gfx.js); '
                    'the reference is drawn without it, so --ref . shows what a switch changes')
    a = ap.parse_args(argv)
    if a.overlay and not a.overlay.is_dir():
        ap.error(f'--overlay: no folder {a.overlay}')
    if a.view == 'review' and a.weather != 'dry':
        ap.error('--weather: the review view paints the surface classes and draws no weather; --view cab or chase shows it')
    snapshot.require_current_data(str(root))  # (#835; a reference revision's data is fetched from the store)
    if a.ref and Path(a.ref).is_dir():
        snapshot.require_current_data(str(Path(a.ref).resolve()))
    at = None
    if a.at:
        try:
            x, y = (float(v) for v in a.at.split(','))
        except ValueError:
            ap.error('--at takes X,Y')
        at = {'x': x, 'y': y, 'yaw': a.yaw}
    if a.line <= 0 or not math.isfinite(a.s) or a.s < 0 or not math.isfinite(a.timeout) or a.timeout <= 0:
        ap.error('s must be finite and nonnegative; timeout must be finite and positive')
    a.out.mkdir(parents=True, exist_ok=True)
    stem = f'line{a.line}-s{a.s:g}-{a.view}' + (f"-at{at['x']:g}_{at['y']:g}" if at else '') + ''.join(f'-{x}' for x in (a.vehicle, a.livery, a.weather if a.weather != 'dry' else None, re.sub(r'[^\w.,]+', '_', a.params)) if x)
    picks = (('#optModel', a.vehicle), ('#optLivery', a.livery or ''))
    try:
        reference_rev = (git(root, 'rev-parse', '--verify', a.ref + '^{commit}')
                         if a.ref and not Path(a.ref).is_dir() else None)
        with tempfile.TemporaryDirectory(prefix='.shot-', dir=a.out) as tmp, sync_playwright() as pw:
            work = Path(tmp)
            current = work / f'{stem}-current.png'
            # (both pictures drawn the same way, on the GPU where there is one, #411)
            browser, renderer = gpu.launch(pw)
            try:
                now = capture(browser, root, a.line, a.s, a.view, current, a.timeout, target=at, dist=a.dist, pitch=a.pitch, picks=picks,
                              plain=a.plain, weather=a.weather, overlay=a.overlay and a.overlay.resolve(), params=a.params)
                report = {'line': a.line, 's': a.s, 'view': a.view, 'renderer': renderer, 'current': now, 'params': a.params,
                          'current_commit': git(root, 'rev-parse', 'HEAD'),
                          'working_changes': git(root, 'status', '--porcelain', '--', 'src', 'index.html', 'data/truth.json', 'data/MANIFEST.json')}
                if a.ref:
                    reference = work / f'{stem}-reference.png'
                    with checkout(root, reference_rev or a.ref, a.cache, a.line) as other:
                        report['reference'] = capture(browser, other, a.line, a.s, a.view, reference, a.timeout,
                                                      pose=now['camera'], target=now['target_xy'], dist=a.dist, pitch=a.pitch, picks=picks,
                                                      plain=a.ref_plain, weather=a.weather)
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
                    combine(current, reference, pair, ['Current checkout' + (f' ?{a.params}' if a.params else ''), f'Reference: {a.ref}'])
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
