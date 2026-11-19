# SPDX-License-Identifier: AGPL-3.0-or-later
"""The HUD's cost on a slow CPU (#706): what one update writes into the page and how long it takes, in headless
Chromium on the GPU with the CPU throttled.

Usage: python -P -E tools/bench/hud.py [--line 17] [--throttle 4] [--seconds 20] [--out reports/hud/main.json]
       python -P -E tools/bench/hud.py --compare reports/hud/main.json reports/hud/706.json

The line loaded as a player loads it, a shift started with the autopilot on, then:
- `idle`: the HUD updated 200 times in a row with the game as it stands, a MutationObserver counting what changes in
  the page (child lists, text, attributes): the writes of an update when nothing changed. 0 is what is wanted.
- `drive`: the autopilot drives for --seconds, from when the tram is under way; the changes in the page per update of the HUD, the mean and the 95th
  percentile time of an update with the layout it leaves to do (a forced one, as the mirror and the cab frame read the
  page's boxes right after it), the same of the minimap's drawing alone, and the mean frame time.
A count is the same on every run; a time is this machine's, throttled: it waits its turn among the heavy jobs, alone.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

MEASURE = r"""async ({ seconds }) => {
  const { startShift } = await import('/tools/bench/shift.js');
  document.getElementById('optAuto').checked = true;
  const game = await startShift({ timeout: 120 }), hud = window.hud;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  await sleep(2000);
  let changes = 0;
  const mo = new MutationObserver((l) => { changes += l.length; });
  const watch = () => mo.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  const taken = () => { changes += mo.takeRecords().length; const n = changes; changes = 0; return n; };
  // nothing changed: the same game, updated again and again
  hud.update(game, game.opts);
  watch(); taken();
  const N = 200;
  for (let i = 0; i < N; i++) hud.update(game, game.opts);
  // (and where: the element each change was in, by its id or its nearest ancestor's)
  const where = {};
  const named = (n) => { for (let e = n.nodeType === 1 ? n : n.parentElement; e; e = e.parentElement) if (e.id) return `#${e.id}`; return 'body'; };
  const recs = mo.takeRecords();
  for (const r of recs) { const k = `${named(r.target)} ${r.type}${r.attributeName ? ' ' + r.attributeName : ''}`; where[k] = (where[k] || 0) + 1 / N; }
  const idle = (changes + recs.length) / N;
  changes = 0;
  mo.disconnect();
  // a drive: every update of the HUD timed with the layout it leaves, the minimap alone, the frames
  const pct = (a, q) => { const s = [...a].sort((x, y) => x - y); return s.length ? s[Math.min(s.length - 1, Math.floor(q * s.length))] : 0; };
  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const upd = [], mini = [], frames = [];
  const update = hud.update.bind(hud), draw = hud.drawMinimap.bind(hud);
  hud.drawMinimap = (g) => { const t = performance.now(); draw(g); mini.push(performance.now() - t); };
  hud.update = (g, o) => { const t = performance.now(); update(g, o); void document.body.offsetHeight; upd.push(performance.now() - t); };
  let on = true, last = performance.now();
  const tick = (now) => { frames.push(now - last); last = now; if (on) requestAnimationFrame(tick); };
  requestAnimationFrame((now) => { last = now; requestAnimationFrame(tick); });
  // (from when the tram is under way: it stands at its first stop until its departure)
  for (let i = 0; i < 1200 && Math.abs(game.tram.v) < 2; i++) await sleep(100);
  upd.length = mini.length = frames.length = 0;
  const s0 = game.tram.s;
  watch(); taken();
  await sleep(seconds * 1000);
  const moved = taken();
  on = false;
  mo.disconnect();
  hud.update = update; hud.drawMinimap = draw;
  const r2 = (x) => Math.round(x * 100) / 100;
  return { idle: { changesPerUpdate: r2(idle), where: Object.fromEntries(Object.entries(where).map(([k, v]) => [k, r2(v)])) },
    drive: { updates: upd.length, metres: Math.round(game.tram.s - s0), changesPerUpdate: r2(moved / Math.max(1, upd.length)),
      updateMs: r2(mean(upd)), updateMs95: r2(pct(upd, 0.95)), minimapMs: r2(mean(mini)), minimapMs95: r2(pct(mini, 0.95)),
      frameMs: r2(mean(frames)), frameMs95: r2(pct(frames, 0.95)) } };
}"""


def measure(line, throttle, seconds, timeout=600):
    from playwright.sync_api import sync_playwright

    import gpu
    from headless import load_page, serve, stop_server
    server, url = serve(0)
    try:
        with sync_playwright() as pw:
            browser = gpu.launch(pw)[0]
            page, errors, load = load_page(browser, url, line, timeout, {"keepgeo": False, "draw": True})
            if isinstance(load, dict):
                raise SystemExit(f"line {line}: the load failed: {load} {errors[:3]}")
            if throttle > 1:
                page.context.new_cdp_session(page).send("Emulation.setCPUThrottlingRate", {"rate": throttle})
            res = page.evaluate(MEASURE, {"seconds": seconds})
            page.close()
            browser.close()
    finally:
        stop_server(server)
    if errors:
        raise SystemExit(f"line {line}: page errors {errors[:3]}")
    return {"line": line, "throttle": throttle, **res}


def table(res, before=None):
    """Lines of text: each number (and the other run's, before -> after)."""
    rows = [f"line {res['line']}, CPU throttled {res['throttle']}x"]
    for part in ("idle", "drive"):
        for k, v in res[part].items():
            was = (before or {}).get(part, {}).get(k)
            rows.append(f"  {part:5} {k:18} {(f'{was} -> ' if was is not None else '')}{v}")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--throttle", type=float, default=4, help="Chromium's CPU throttle (4: a slow laptop; 1: none)")
    ap.add_argument("--seconds", type=float, default=20, help="the drive's length")
    ap.add_argument("--out", help="write the numbers here (JSON)")
    ap.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="print two saved runs side by side")
    a = ap.parse_args()
    if a.compare:
        before, after = (json.load(open(p, encoding="utf-8")) for p in a.compare)
        print("\n".join(table(after, before)))
        return
    from baseline_store import HeavyJob
    with HeavyJob("hud bench"):  # (a timing: alone)
        res = measure(a.line, a.throttle, a.seconds)
    print("\n".join(table(res)))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        print(a.out)


if __name__ == "__main__":
    main()
