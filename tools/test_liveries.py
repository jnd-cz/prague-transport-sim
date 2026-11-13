# SPDX-License-Identifier: AGPL-3.0-or-later
"""Liveries (#529) in headless Chromium: the sample liveries on our tram and on AI trams.

Usage: python -P -E tools/test_liveries.py [--line 17] [--seed 3] [--secs 600]

The looks (src/models.js makeT3 with a livery, src/rigged.js wear, src/t3simple.js livery): the hybrid's sample
gives its body slot a texture and its band a colour, every other material as the vehicle's own; the built-in car's
sample paints its body, band and roof; both draw the fleet numbers in their colour; without a livery both are as
before. A livery naming a slot its vehicle lacks is refused with the slot's name (src/vehicles.js liveryProblems).
The dealer (FleetDealer) gives each sample to about its `share` of the AI sets of the types it fits, and a number's
wrap (the fleet's `liveries`) to that number. Then the game (line --line, seed --seed, the built-in car, the green
sample remembered in the menu), driven by the autopilot for --secs simulated seconds with the traffic on: our tram
wears it, and the AI trams that are dealt it wear it. Needs the line's data (python -I tools/snapshot.py
data-fetch); skips without it.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402

BLUE, GREEN = "sample.t3h-blue", "sample.t3simple-green"

LOOKS = r"""async () => {
  const THREE = await import('three');
  const V = await import('/src/vehicles.js'), M = await import('/src/models.js'), R = await import('/src/rigged.js');
  const { rng } = await import('/src/random.js'), { T3 } = await import('/src/tram.js');
  await V.loadRegistry();
  const out = { liveries: [...V.liveries.keys()].sort() };
  const vh = V.byId.get('t3h'), v3 = V.byId.get('t3simple');
  if (!R.riggedReady('t3h')) {
    const files = await Promise.all([vh.model, vh.rig].map(async (f) => {
      const r = await fetch('/' + V.fileUrl(vh, f));
      return { ok: r.ok, json: () => r.json(), arrayBuffer: () => r.arrayBuffer() };
    }));
    await R.loadRigged(vh, files[0], files[1], T3, 5.34);
  }
  // every material of a set by name: its map's source and its colour
  const mats = (root) => {
    const m = {};
    root.traverse((o) => { if (o.isMesh && o.material?.name && !(o.material.name in m)) m[o.material.name] = { map: o.material.map?.image?.src ?? (o.material.map ? 'canvas' : null), colour: o.material.color?.getHexString() }; });
    return m;
  };
  // the fleet number's colour: the most common opaque pixel of the first car's number texture
  const ink = (root) => {
    let tex = null;
    root.traverse((o) => { if (!tex && o.isMesh && (o.name === 'fleet' || o.material?.name === 'Fleet_Number_Decal') && o.material.map?.image?.getContext) tex = o.material.map; });
    if (!tex) return null;
    const d = tex.image.getContext('2d').getImageData(0, 0, tex.image.width, tex.image.height).data, n = new Map();
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] === 255) { const k = ((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]).toString(16).padStart(6, '0'); n.set(k, (n.get(k) || 0) + 1); }
    return [...n].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  };
  const own = M.makeT3({ vehicle: 't3h', cars: 2, line: '17', run: '801', variant: 'T3SUCS' });
  const blue = M.makeT3({ vehicle: 't3h', cars: 2, line: '17', run: '801', variant: 'T3SUCS', livery: 'sample.t3h-blue' });
  await new Promise((ok) => { const t = setInterval(() => { let img = null; blue.traverse((o) => { if (o.material?.name === 'Red_Hull') img = o.material.map?.image; }); if (img?.complete && img.naturalWidth) { clearInterval(t); ok(); } }, 50); setTimeout(ok, 10000); });
  const a = mats(own), b = mats(blue);
  out.hybrid = { own: { Red_Hull: a.Red_Hull, Beige: a.Beige }, blue: { Red_Hull: b.Red_Hull, Beige: b.Beige, Beige_wbackface: b.Beige_wbackface },
    others: Object.keys(a).filter((k) => !['Red_Hull', 'Beige', 'Beige_wbackface'].includes(k) && JSON.stringify(a[k]) !== JSON.stringify(b[k]) && a[k].map !== 'canvas'),
    livery: [own.userData.livery, blue.userData.livery], ink: [ink(own), ink(blue)],
    draws: [own, blue].map((x) => { let n = 0; x.userData.cars[0].userData.rig.full.traverse((o) => { if (o.isMesh) n++; }); return n; }) };
  // the built-in car: the livery canvas's pixels of the red and the green
  const s0 = M.makeT3({ vehicle: 't3simple', cars: 1, line: '17', run: '801', variant: 'T3' });
  const s1 = M.makeT3({ vehicle: 't3simple', cars: 1, line: '17', run: '801', variant: 'T3', livery: 'sample.t3simple-green' });
  const s2 = M.makeT3({ vehicle: 't3simple', cars: 1, line: '17', run: '802', variant: 'T3' });
  const body = (root) => { let m = null; root.traverse((o) => { if (o.name === 'body') m = o.material; }); return m; };
  const count = (tex, hex) => {
    const c = tex.image, d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
    let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === r && d[i + 1] === g && d[i + 2] === bl) n++; return n;
  };
  out.simple = { sameOwn: body(s0).map === body(s2).map, red: [count(body(s0).map, '#b3201a'), count(body(s1).map, '#b3201a')],
    green: [count(body(s0).map, '#2f6b3a'), count(body(s1).map, '#2f6b3a')], roof: count(body(s1).map, '#5d6266'),
    livery: [s0.userData.livery, s1.userData.livery], ink: [ink(s0), ink(s1)] };
  // refused: a slot its vehicle lacks, by its name
  const l = (x) => ({ schema: 1, kind: 'livery', id: 'x', requires: { t3h: '>=1' }, names: { cs: 'x', en: 'x' }, files: [{ path: 'a.png' }], ...x });
  out.refused = { roof: V.liveryProblems(l({ textures: { roof: 'a.png' } }), vh), wheels: V.liveryProblems(l({ colours: { wheels: '#000000' } }), vh),
    type: V.liveryProblems(l({ types: ['T3M'] }), vh), good: V.liveryProblems(l({ textures: { body: 'a.png' }, colours: { band: '#ffffff' } }), vh),
    simpleSlot: V.liveryProblems({ ...l({ colours: { body: '#000000', skirt: '#000000' } }), requires: { t3simple: '>=1' } }, v3) };
  // dealing: each sample on about its share of the sets of the types it fits; a wrap on its number
  const deal = (v, n, seed) => { const d = new V.FleetDealer(v, rng(seed)), c = {}; for (let i = 0; i < n; i++) { const s = d.deal(2); const k = `${s.type}|${s.livery}`; c[k] = (c[k] || 0) + 1; d.give(s.numbers); } return c; };
  out.dealt = { t3h: deal(vh, 4000, 1), t3simple: deal(v3, 4000, 2) };
  v3.fleet.liveries = { 6500: 'sample.t3simple-green' };
  out.wrap = [V.liveryOf(v3, 'T3', [6500, 6501], 0.99), V.liveryOf(v3, 'T3', [6502, 6501], 0.99)];
  delete v3.fleet.liveries;
  // an AI set dealt the green sample is built wearing it
  const d = new V.FleetDealer(v3, rng(5));
  let s = null; for (let i = 0; i < 500 && !s; i++) { const x = d.deal(2); if (x.livery) s = x; }
  const ai = M.makeT3({ vehicle: 't3simple', cars: 2, line: '17', run: '803', dealt: s });
  out.ai = { dealt: s, livery: ai.userData.livery, green: count(body(ai).map, '#2f6b3a') };
  return out;
}"""

GAME = r"""async ({ secs, seed }) => {
  const $ = (id) => document.getElementById(id);
  const { Autopilot } = await import('/src/autopilot.js'), { startShift } = await import('/tools/bench/shift.js');
  window.runSeed = seed;
  $('optModel').value = 't3simple'; $('optModel').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optTemp').value = 'autumn'; $('optWeather').value = 'dry';
  $('optCars').value = 'auto'; $('optObst').value = 'off'; $('optAuto').checked = false;
  const out = { menu: $('optLivery').value, menuRow: !$('liveryRow').hidden, options: [...$('optLivery').options].map((o) => o.value) };
  window.headless = true;
  const g = await startShift(), tr = window.traffic, ap = new Autopilot(), dt = 1 / 30;
  g.audio.setMuted(true);
  out.ours = window.tramModel.userData.livery;
  const seen = new Map();
  let T = 0;
  const camera = { position: { x: 0, z: 0 } };
  while (T < secs && !g.finished) {
    ap.step(g, dt); g.update(dt, ap.input);
    const p = g.route.at(g.tram.s); camera.position.x = p.x; camera.position.z = -p.y;
    tr.update(dt, camera); T += dt;
    for (const t of [...tr.ahead, ...tr.oncoming]) if (!seen.has(t.mesh)) {
      let map = null; t.mesh.traverse((o) => { if (!map && o.name === 'body') map = o.material.map; });
      seen.set(t.mesh, { livery: t.mesh.userData.livery, map });
    }
  }
  window.headless = false; delete window.runSeed;
  const own = [...seen.values()].find((x) => !x.livery)?.map, worn = [...seen.values()].filter((x) => x.livery);
  return { ...out, sets: seen.size, worn: worn.map((x) => x.livery), wornOwnMap: worn.filter((x) => x.map === own).length, T: Math.round(T) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--secs", type=float, default=600)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(1200, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    fails = []

    def need(ok, why):
        if not ok:
            fails.append(why)

    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            ctx = browser.new_context(viewport={"width": 960, "height": 540})
            ctx.add_init_script(f"try {{ localStorage.setItem('tram.livery', JSON.stringify({{ t3simple: '{GREEN}' }})); }} catch {{}}")
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}/?line={args.line}", timeout=300000)
            page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
            d = page.evaluate(LOOKS)
            g = page.evaluate(GAME, {"secs": args.secs, "seed": args.seed})
            ctx.close()
            browser.close()
    finally:
        server.shutdown()

    print("looks:", json.dumps({k: d[k] for k in ("liveries", "hybrid", "simple", "wrap", "ai")}, ensure_ascii=False))
    print("refused:", json.dumps(d["refused"], ensure_ascii=False))
    print("dealt:", json.dumps(d["dealt"]))
    print("game:", json.dumps(g, ensure_ascii=False))
    need(d["liveries"] == sorted([BLUE, GREEN]), f"liveries loaded {d['liveries']}")
    h = d["hybrid"]
    need(h["blue"]["Red_Hull"]["map"] and h["blue"]["Red_Hull"]["map"].endswith(f"/assets/{BLUE}/body.png") and h["blue"]["Red_Hull"]["colour"] == "ffffff",
         f"the hybrid's body slot with the sample: {h['blue']['Red_Hull']}, wants its texture on white")
    need(h["blue"]["Beige"]["colour"] == h["blue"]["Beige_wbackface"]["colour"] == "e4e9ee" and h["blue"]["Beige"]["map"] is None,
         f"the hybrid's band slot with the sample: {h['blue']['Beige']}")
    # (the own look keeps the slots' parts merged into the painted meshes, as before #529: no draws added)
    need(h["own"]["Red_Hull"] is None and h["own"]["Beige"] is None and h["draws"][0] < h["draws"][1],
         f"the hybrid's own look: {h['own']}, its meshes a car {h['draws']} (own, the sample)")
    need(not h["others"], f"materials outside the sample's slots changed: {h['others']}")
    need(h["livery"] == [None, BLUE], f"the sets' liveries {h['livery']}")
    need(h["ink"][1] == "ffffff" and h["ink"][0] != "ffffff", f"the hybrid's fleet numbers {h['ink']}, wants white with the sample only")
    s = d["simple"]
    need(s["sameOwn"], "the built-in car's own livery is not one texture shared by every set")
    need(s["red"][0] > 0 and s["red"][1] == 0 and s["green"][0] == 0 and s["green"][1] > 0 and s["roof"] > 0,
         f"the built-in car's red pixels {s['red']}, green {s['green']}, the sample's roof {s['roof']} (own, sample)")
    need(s["livery"] == [None, GREEN] and s["ink"][1] == "f2f2f2" and s["ink"][0] != "f2f2f2", f"the built-in car's liveries {s['livery']}, numbers {s['ink']}")
    r = d["refused"]
    need(any("texture slot roof" in x for x in r["roof"]), f"a texture for a slot the hybrid lacks: {r['roof']}")
    need(any("colour slot wheels" in x for x in r["wheels"]), f"a colour for a slot the hybrid lacks: {r['wheels']}")
    need(any("type T3M" in x for x in r["type"]), f"a type the hybrid's fleet lacks: {r['type']}")
    need(any("colour slot skirt" in x for x in r["simpleSlot"]) and not any("body" in x for x in r["simpleSlot"]), f"the built-in car's slots: {r['simpleSlot']}")
    need(not r["good"], f"a good livery refused: {r['good']}")
    for vid, lid in (("t3h", BLUE), ("t3simple", GREEN)):
        c = d["dealt"][vid]
        for t in {k.split("|")[0] for k in c}:
            n = sum(v for k, v in c.items() if k.startswith(t + "|"))
            share = c.get(f"{t}|{lid}", 0) / n
            need(abs(share - 0.15) < 0.04, f"{vid} {t}: the sample on {share:.3f} of the sets, its share 0.15")
    need(d["wrap"] == [GREEN, None], f"a number's wrap {d['wrap']}")
    need(d["ai"]["livery"] == GREEN and d["ai"]["green"] > 0, f"an AI set dealt the sample: {d['ai']}")
    need(g["menuRow"] and g["menu"] == GREEN and g["options"] == ["", "*", GREEN], f"the menu: {g['menuRow']}, {g['menu']}, {g['options']}")
    need(g["ours"] == GREEN, f"our tram wears {g['ours']}, wants the remembered {GREEN}")
    need(g["sets"] >= 5 and g["worn"] and set(g["worn"]) == {GREEN} and g["wornOwnMap"] == 0,
         f"AI sets {g['sets']}, wearing {g['worn']}, {g['wornOwnMap']} of them with the own texture")
    need(not errors, f"page errors {errors}")
    for f in fails:
        print("FAIL", f)
    print("liveries: slots, refusals, dealing, ours and AI trams': " + ("pass" if not fails else f"{len(fails)} failures"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
