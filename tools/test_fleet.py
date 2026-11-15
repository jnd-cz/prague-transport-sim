# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fleet numbers dealt from the vehicle's fleet (#527), in headless Chromium.

Usage: python -P -E tools/test_fleet.py [--line 17] [--seed 3] [--secs 900]

The dealer alone (src/vehicles.js FleetDealer on the built-in car's and the hybrid's manifests): each type dealt as
often as it has numbers, the listed sets only together or one car alone, no number twice on a street of
sets coming and going, the player's preferred set never dealt to anybody else, the same stream deals the same.
Then the game (line --line, seed --seed, the built-in car, the preferred set 6892+6921 remembered in the menu),
driven by the autopilot for --secs simulated seconds with the traffic on, twice: our tram runs as the preferred set,
no number twice among the sets on the street at any moment, none of them ours, and the second run deals the same
sets in the same order. Needs the line's data (python -I tools/snapshot.py data-fetch); skips without it.
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

PREFER = "6892+6921"
HISTORIC = [[6892, 6921], [7269, 7290], [8080, 8074]]

DEALER = r"""async () => {
  const V = await import('/src/vehicles.js'), { rng } = await import('/src/random.js');
  await V.loadRegistry();
  const v3 = V.byId.get('t3simple'), vh = V.byId.get('t3h'), f = V.fleetOf(v3), out = {};
  // shares: 20000 two-car and single-car sets, each given back at once
  const d = new V.FleetDealer(v3, rng(1)), n = {};
  for (let i = 0; i < 20000; i++) { const s = d.deal(i % 4 ? 2 : 1); n[s.type] = (n[s.type] || 0) + 1; d.give(s.numbers); }
  const all = f.types.reduce((s, t) => s + t.numbers.length, 0);
  out.shares = Object.fromEntries(f.types.map((t) => [t.type, [(n[t.type] || 0) / 20000, t.numbers.length / all]]));
  // a street: up to 40 sets on it, one leaving or arriving per step; the preferred set held for the whole run
  const r = rng(7), e = new V.FleetDealer(v3, rng(2)), street = [];
  const ours = e.ours(2, V.preferredSet(v3, '8080'));
  out.ours = ours;
  let twice = 0, oursDealt = 0, setSplit = 0, singleSet = 0, typeMix = 0;
  const historic = new Set();
  for (let i = 0; i < 30000; i++) {
    if (street.length && (street.length >= 40 || r() < 0.5)) e.give(street.splice(Math.floor(r() * street.length), 1)[0].numbers);
    else {
      const cars = r() < 0.2 ? 1 : 2, s = e.deal(cars);
      street.push(s);
      const set = f.setOf.get(s.numbers[0]);
      if (set && cars > 1) { if (String(set) !== String(s.numbers)) setSplit++; else historic.add(String(set)); }
      if (cars === 1 && set) singleSet++;
      if (s.numbers.some((x) => ours.numbers.includes(x))) oursDealt++;
      if (s.numbers.some((x) => f.typeOf.get(x) !== s.type)) typeMix++;
      if (cars > 1 && s.numbers.some((x) => f.setOf.has(x) && String(f.setOf.get(x)) !== String(s.numbers))) setSplit++;
      const on = street.flatMap((x) => x.numbers);
      if (new Set(on).size !== on.length) twice++;
    }
  }
  Object.assign(out, { twice, oursDealt, setSplit, singleSet, typeMix, historic: [...historic].sort() });
  // (the type and numbers: the livery a set is dealt is tools/test_liveries.py's)
  const tn = (x) => x && { type: x.type, numbers: x.numbers };
  out.ours = tn(out.ours);
  // our single car from a pair (line 23): its partner runs alone on AI single cars, the pair is never dealt whole
  const o = new V.FleetDealer(v3, rng(5)), one = o.ours(1, V.preferredSet(v3, '6892+6921'));
  let partner = 0, oursSingle = 0, pairWhole = 0;
  for (let i = 0; i < 4000; i++) {
    const s = o.deal(i % 2 ? 2 : 1);
    if (s.numbers.includes(6921) && s.numbers.length === 1) partner++;
    if (s.numbers.includes(6892)) oursSingle++;
    if (s.numbers.length === 2 && s.numbers.includes(6921)) pairWhole++;
    o.give(s.numbers);
  }
  out.single = { one: tn(one), partner, oursSingle, pairWhole };
  // the preferred set's forms; the hybrid's own fleet
  out.prefer = { lone: V.preferredSet(v3, '7269'), setText: V.preferredSet(v3, '6892+6921'), mixed: V.preferredSet(v3, '6892+7001'), none: V.preferredSet(v3, '1') };
  const lone = new V.FleetDealer(v3, rng(3)).ours(2, V.preferredSet(v3, '7005'));
  out.prefer.loneFree = tn(lone);
  out.prefer.dealtNoPrefer = new V.FleetDealer(v3, rng(3)).ours(2).type;
  out.hybrid = [...new Set(Array.from({ length: 500 }, () => new V.FleetDealer(vh, rng(4)).deal(2).type))];
  // replay: the same stream deals the same
  const deal = (seed) => { const x = new V.FleetDealer(v3, rng(seed)); return Array.from({ length: 50 }, (_, i) => x.deal(1 + (i % 2)).numbers.join('+')).join(','); };
  out.replay = deal(11) === deal(11) && deal(11) !== deal(12);
  return out;
}"""

GAME = r"""async ({ secs, seed }) => {
  const $ = (id) => document.getElementById(id);
  const { Autopilot } = await import('/src/autopilot.js'), { startShift } = await import('/tools/bench/shift.js');
  window.runSeed = seed;
  $('optModel').value = 't3simple'; $('optModel').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optTemp').value = 'autumn'; $('optWeather').value = 'dry';
  $('optCars').value = 'auto'; $('optObst').value = 'off'; $('optAuto').checked = false;
  const out = { menu: $('optFleet').value, menuRow: !$('fleetRow').hidden };
  window.headless = true;
  const g = await startShift(), tr = window.traffic, ap = new Autopilot(), dt = 1 / 30;
  g.audio.setMuted(true);
  out.ours = window.tramModel.userData.fleet;
  const order = [], seen = new Set(), twice = [];
  let oursOut = 0, T = 0, maxOn = 0;
  const camera = { position: { x: 0, z: 0 } };
  while (T < secs && !g.finished) {
    ap.step(g, dt); g.update(dt, ap.input);
    const p = g.route.at(g.tram.s); camera.position.x = p.x; camera.position.z = -p.y;
    tr.update(dt, camera); T += dt;
    const sets = [...tr.ahead, ...tr.oncoming].map((t) => t.mesh.userData.fleet);
    for (const s of sets) { const k = s.join('+'); if (!seen.has(s)) { seen.add(s); order.push(k); } }
    const on = sets.flat();
    maxOn = Math.max(maxOn, sets.length);
    if (new Set(on).size !== on.length && twice.length < 5) twice.push([Math.round(T), on]);
    if (on.some((x) => out.ours.includes(x))) oursOut++;
  }
  window.headless = false; delete window.runSeed;
  return { ...out, order, twice, oursOut, maxOn, T: Math.round(T), s: Math.round(g.tram.s) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--secs", type=float, default=900)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(1200, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    r, fails = {"games": []}, []

    def need(ok, why):
        if not ok:
            fails.append(why)

    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            for k in range(2):
                ctx = browser.new_context(viewport={"width": 960, "height": 540})
                ctx.add_init_script(f"try {{ localStorage.setItem('tram.fleet', JSON.stringify({{ t3simple: '{PREFER}' }})); }} catch {{}}")
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                if k == 0:
                    r["dealer"] = page.evaluate(DEALER)
                g = page.evaluate(GAME, {"secs": args.secs, "seed": args.seed})
                g["errors"] = errors
                r["games"].append(g)
                ctx.close()
            browser.close()
    finally:
        server.shutdown()

    d = r["dealer"]
    print("dealer:", json.dumps({k: v for k, v in d.items() if k != "prefer"}, ensure_ascii=False))
    print("prefer:", json.dumps(d["prefer"]))
    for t, (got, want) in d["shares"].items():
        need(abs(got - want) < 0.02, f"type {t} dealt {got:.3f} of the sets, its numbers are {want:.3f} of the fleet")
    need(d["twice"] == 0, f"a number twice on the street {d['twice']} times")
    need(d["oursDealt"] == 0, f"the preferred set dealt to another tram {d['oursDealt']} times")
    need(d["setSplit"] == 0, f"listed sets split or mixed with another car {d['setSplit']} times")
    need(d["singleSet"] > 0, "a single car is never dealt a listed set's car")
    sg = d["single"]
    need(sg["one"] == {"type": "T3", "numbers": [6892]} and sg["partner"] > 0 and sg["oursSingle"] == 0 and sg["pairWhole"] == 0,
         f"our single car from 6892+6921: {sg}; wants 6892 ours, 6921 dealt alone, the pair never whole")
    need(d["typeMix"] == 0, f"sets of mixed types {d['typeMix']} times")
    others = [s for s in HISTORIC if s != [8080, 8074]]   # (8080+8074 is the street's preferred set: never dealt)
    need(d["historic"] == sorted(",".join(map(str, s)) for s in others), f"historic sets dealt: {d['historic']}, wants all of {others}")
    need(d["ours"] == {"type": "T3M", "numbers": [8080, 8074]}, f"preferred '8080' gives {d['ours']}, wants T3M 8080+8074 (its set)")
    pr = d["prefer"]
    need(pr["lone"] == {"type": "T3SUCS", "numbers": [7269, 7290]} and pr["setText"] == {"type": "T3", "numbers": [6892, 6921]},
         f"preferred sets read as {pr['lone']} and {pr['setText']}")
    need(pr["mixed"] is None and pr["none"] is None, "a mixed or unknown preferred set is not refused")
    lf = pr["loneFree"]
    need(lf["type"] == "T3SUCS" and lf["numbers"][0] == 7005 and 7001 <= lf["numbers"][1] <= 7292 and lf["numbers"][1] not in (7005, 7269, 7290),
         f"a lone preferred 7005 gives {lf}, wants a second T3SUCS outside the sets")
    need(pr["dealtNoPrefer"] == "T3SUCS", f"our tram without a preference is a {pr['dealtNoPrefer']}, wants the T3SUCS the simulation drives")
    need(d["hybrid"] == ["T3SUCS"], f"the hybrid dealt types {d['hybrid']}")
    need(d["replay"], "the same stream does not deal the same, or another deals the same")
    for k, g in enumerate(r["games"]):
        print(f"game {k + 1}: ours {g['ours']}, {len(g['order'])} sets dealt, up to {g['maxOn']} at once, {g['T']} s to s {g['s']}; first {g['order'][:6]}")
        need(g["menuRow"] and g["menu"] == PREFER, f"game {k + 1}: the menu shows {g['menu']!r}, wants the remembered {PREFER}")
        need(g["ours"] == [6892, 6921], f"game {k + 1}: our tram is {g['ours']}, wants {PREFER}")
        need(not g["twice"], f"game {k + 1}: a number twice on the street: {g['twice']}")
        need(g["oursOut"] == 0, f"game {k + 1}: our numbers on an AI tram {g['oursOut']} frames")
        need(len(g["order"]) >= 5, f"game {k + 1}: only {len(g['order'])} AI sets came out")
        need(not g["errors"], f"game {k + 1}: page errors {g['errors']}")
    a, b = r["games"]
    need(a["order"] == b["order"], "the second run with the same seed dealt other sets")
    for f in fails:
        print("FAIL", f)
    print("fleet numbers: dealt by type, sets kept, none twice, the preferred set ours: " + ("pass" if not fails else f"{len(fails)} failures"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
