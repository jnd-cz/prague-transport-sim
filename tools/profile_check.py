# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where a check's time goes (#205): one run of a headless.py check in headless Chromium under the CPU profiler.

    python -P -E tools/profile_check.py --line 17 --check u3 --seed 1 [--out reports/profile/17-u3-1.json]

Its own server on a free port (as headless.py), the same browser flags and the same call per check. Prints the
page load (to the hidden loading screen) and the check's run: wall time, the sampled CPU time by source file
(src/*.js, three.js, idle, garbage collection, the rest), the top functions by self time, the JS heap and how
many frames the page drew. --out keeps that summary as JSON and both raw profiles beside it (.cpuprofile, open in
Chrome DevTools' Performance panel). The renderer's GPU work (SwiftShader) runs in the GPU process: in this
profile it shows as idle time of the page's main thread, waiting for frames.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright  # noqa: E402
from headless import ARGS, CALLS, serve, stop_server  # noqa: E402

# (frames the page drew: every requestAnimationFrame callback that ran, counted before the game's own code)
COUNT_FRAMES = """
window.__frames = 0;
const raf = window.requestAnimationFrame.bind(window);
window.requestAnimationFrame = (cb) => raf((t) => { window.__frames++; cb(t); });
"""


def summary(profile, top=25):
    """Self time (ms) by file and by function from a CDP Profiler profile."""
    nodes = {n['id']: n for n in profile['nodes']}
    self_us = defaultdict(float)
    for nid, dt in zip(profile.get('samples', []), profile.get('timeDeltas', [])):
        self_us[nid] += dt
    by_file, by_fn = defaultdict(float), defaultdict(float)
    for nid, us in self_us.items():
        cf = nodes[nid]['callFrame']
        url, fn = cf.get('url') or '', cf.get('functionName') or '(anonymous)'
        if not url:
            f = fn if fn.startswith('(') else '(native)'
        else:
            path = url.split('://', 1)[-1].split('/', 1)[-1].split('?')[0]
            f = 'three.js' if 'three' in path else path
        by_file[f] += us / 1000
        by_fn[f'{fn} {f}:{cf.get("lineNumber", 0) + 1}'] += us / 1000
    total = sum(by_file.values()) or 1.0
    rows = lambda d, n: [[k, round(v), round(100 * v / total, 1)] for k, v in sorted(d.items(), key=lambda kv: -kv[1])[:n]]
    return {'sampled_ms': round(total), 'by_file': rows(by_file, 40), 'top_functions': rows(by_fn, top)}


def heap(cdp):
    h = cdp.send('Runtime.getHeapUsage')
    return round(h['usedSize'] / 2 ** 20), round(h['totalSize'] / 2 ** 20)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--line', default='17')
    ap.add_argument('--check', default='u3', choices=sorted(CALLS))
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--timeout', type=float, default=1800)
    ap.add_argument('--interval', type=int, default=1000, help='sampling interval, microseconds')
    ap.add_argument('--out')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    proc, url = serve(0)
    out = {'line': args.line, 'check': args.check, 'seed': args.seed}
    raw = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=ARGS)
            page = browser.new_page(viewport={'width': 960, 'height': 540})
            page.add_init_script(COUNT_FRAMES)
            cdp = page.context.new_cdp_session(page)
            cdp.send('Profiler.enable')
            cdp.send('Profiler.setSamplingInterval', {'interval': args.interval})
            cdp.send('Profiler.start')
            t0 = time.monotonic()
            page.goto(f'{url}/index.html?line={args.line}&keepgeo', timeout=120_000)
            page.wait_for_function(
                f"() => document.getElementById('loading')?.classList.contains('hidden') && document.title.includes('{args.line}')",
                timeout=600_000, polling=250)
            t1 = time.monotonic()
            raw['load'] = cdp.send('Profiler.stop')['profile']
            out['load'] = {'wall_s': round(t1 - t0, 1), 'heap_mb': heap(cdp),
                           'frames': page.evaluate('() => window.__frames'), **summary(raw['load'])}
            cdp.send('Profiler.start')
            f0 = page.evaluate('() => window.__frames')
            js = CALLS[args.check].replace('SEED', str(args.seed))
            page.evaluate(f"""() => {{
                window._job = {{ done: false }};
                (async () => {{ {js} }})().then(
                    result => {{ window._job.result = result; window._job.done = true; }},
                    error => {{ window._job.result = {{ error: String(error) }}; window._job.done = true; }});
            }}""")
            page.wait_for_function('() => window._job.done', timeout=args.timeout * 1000, polling=250)
            t2 = time.monotonic()
            raw['run'] = cdp.send('Profiler.stop')['profile']
            res = page.evaluate('() => window._job.result') or {}
            out['run'] = {'wall_s': round(t2 - t1, 1), 'heap_mb': heap(cdp),
                          'frames': page.evaluate('() => window.__frames') - f0,
                          'error': res.get('error') if isinstance(res, dict) else None, **summary(raw['run'])}
            browser.close()
    finally:
        stop_server(proc)
    for phase in ('load', 'run'):
        p = out[phase]
        print(f"{phase}: {p['wall_s']} s wall, {p['sampled_ms'] / 1000:.1f} s sampled, heap {p['heap_mb'][0]} of "
              f"{p['heap_mb'][1]} MB, {p['frames']} frames" + (f", error {p.get('error')}" if p.get('error') else ''))
        for k, ms, pct in p['by_file'][:14]:
            print(f'  {pct:5.1f} %  {ms / 1000:7.1f} s  {k}')
        print('  top functions:')
        for k, ms, pct in p['top_functions'][:12]:
            print(f'  {pct:5.1f} %  {ms / 1000:7.1f} s  {k}')
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(out, fh, indent=1)
        for phase, prof in raw.items():
            with open(args.out[:-5] + f'.{phase}.cpuprofile', 'w', encoding='utf-8') as fh:
                json.dump(prof, fh)


if __name__ == '__main__':
    main()
