# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sound events and a sample sound pack (#528) in headless Chromium.

Usage: python -P -E tools/test_sounds.py [--line 17] [--stop 13] [--secs 240]

The game ships no sound pack yet (the built-in sounds); this test makes a sample basic pack for the built-in car,
short generated WAVs for the seven sounds the user named first (2026-11-11, PR #462: the door alert, the main bell,
accelerating under power, idle, switches and crossings, the curves' screech, the doors opening and closing), and
serves it to the page as a package listed in assets/vehicles.json. Then, once with the hybrid (no pack: the built-in
sounds) and once with the built-in car (the sample pack), on line --line: the bell rung and a door cycle raise their
events (door.open; door.buzzer and door.close together as the doors start closing), played by the built-in synthesis
or by the pack's recordings; the pack's loops mute the built-in voices and follow the drive (the motor's level under
power, the motor-generator's at idle). Driven by the autopilot from stop --stop (line 17's 13th: switches and
crossings within the next 1.5 km) for --secs simulated seconds, every axle of the set
sounds `points` or `crossing` once at each frog it passes, when its own place along the route is on the frog. A
pack naming an event the game lacks is left out with the name. Needs the line's data (python -I tools/snapshot.py
data-fetch); skips without it.
"""
import argparse
import faulthandler
import functools
import http.server
import io
import json
import math
import os
import sys
import threading
import wave

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))  # (python -P leaves it out)
import gpu  # noqa: E402

PACK = "sample.t3simple-sounds"
RATE = 22050


def tone(secs, parts, decay=0.0, noise=0.0):
    """A mono 16-bit WAV: sine partials [(Hz, level)], an exponential decay (1/s), a little noise."""
    n, x, out = int(secs * RATE), 12345, bytearray()
    for i in range(n):
        t = i / RATE
        v = sum(a * math.sin(2 * math.pi * f * t) for f, a in parts)
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        v = (v + noise * (x / 0x3FFFFFFF - 1)) * math.exp(-decay * t)
        out += int(max(-1, min(1, v)) * 32000).to_bytes(2, "little", signed=True)
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(out))
    return b.getvalue()


def sample_pack():
    files = {
        "buzzer.wav": tone(0.6, [(620, 0.4), (1240, 0.1)]),
        "bell1.wav": tone(0.8, [(1180, 0.4), (2650, 0.2)], decay=5), "bell2.wav": tone(0.8, [(1100, 0.4), (2500, 0.2)], decay=5),
        "door-open.wav": tone(0.5, [], decay=4, noise=0.4), "door-close.wav": tone(0.6, [], decay=3, noise=0.4),
        "points.wav": tone(0.15, [(180, 0.5)], decay=30, noise=0.3), "crossing.wav": tone(0.15, [(140, 0.5)], decay=30, noise=0.3),
        "motor-30kmh.wav": tone(1.0, [(240, 0.3), (361, 0.2), (965, 0.1)]), "mg.wav": tone(1.0, [(60, 0.3), (360, 0.1)]),
        "squeal.wav": tone(1.0, [(2900, 0.3), (3170, 0.15)]),
    }
    pack = {"schema": 1, "kind": "sounds", "id": PACK, "requires": {"t3simple": ">=1"},
            "names": {"cs": "Ukázkové zvuky (test)", "en": "Sample sounds (test)"},
            "licence": {"spdx": "CC0-1.0", "commercial": True, "authors": ["the test"], "sources": ["tools/test_sounds.py"], "credit": ""},
            "files": [{"path": k, "bytes": len(v)} for k, v in files.items()],
            "events": {"door.buzzer": "buzzer.wav", "bell": ["bell1.wav", "bell2.wav"], "door.open": "door-open.wav",
                       "door.close": "door-close.wav", "points": "points.wav", "crossing": "crossing.wav"},
            "loops": {"motor": {"file": "motor-30kmh.wav", "refSpeed": 8.3}, "mg": {"file": "mg.wav", "refRpm": 1800},
                      "flange": {"file": "squeal.wav"}}}
    return pack, files


GAME = r"""async ({ model, secs, stop }) => {
  const $ = (id) => document.getElementById(id);
  const { Autopilot } = await import('/src/autopilot.js'), { startShift } = await import('/tools/bench/shift.js');
  const { axlesBehind } = await import('/src/audio.js'), V = await import('/src/vehicles.js');
  window.runSeed = 3;
  $('optModel').value = model; $('optModel').dispatchEvent(new Event('change'));
  $('selStop').value = String(stop); $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optTemp').value = 'autumn'; $('optWeather').value = 'dry';
  $('optCars').value = 'auto'; $('optObst').value = 'off'; $('optAuto').checked = false;
  window.headless = true;
  const g = await startShift({ timeout: 120 }), a = g.audio, tr = window.traffic, ap = new Autopilot(), dt = 1 / 30;
  a.setMuted(true); a.setActive(true);
  const out = { pack: a.pack?.id ?? null, packs: [...V.soundPacks.keys()], loops: Object.keys(a.pack?.loops || {}),
    synth: { motor: a.motorOut.gain.value, mg: a.mgOut.gain.value, flange: a.squealOut.gain.value, rolling: a.rollOut.gain.value } };
  a.trace = [];
  g.ringBell();
  g.toggleDoors();   // (they stand open at the first stop: closing)
  g.toggleDoors();   // opening
  const step = () => { ap.step(g, dt); g.update(dt, ap.input); a.update(g.tram, g.currentLimit, dt); const p = g.route.at(g.tram.s); tr.update(dt, { position: { x: p.x, z: -p.y } }); };
  const doors = a.trace.map((x) => [x.e, x.by]);
  // the doors shut again, then the drive: the frogs and the loops
  g.toggleDoors();
  a.trace = [];
  const s0 = g.tram.s, levels = { motor: 0, mg: 0 };
  let T = 0;
  while (T < secs && !g.finished) {
    step(); T += dt;
    if (a.pack) for (const k of ['motor', 'mg']) levels[k] = Math.max(levels[k], a.pack.loops[k]?.level ?? 0);
  }
  const frogs = a.trace.filter((x) => x.e === 'points' || x.e === 'crossing');
  window.headless = false;
  return { ...out, doors, s0, s1: g.tram.s, cars: g.tram.cars, axles: axlesBehind(g.tram.cars), frogs: frogs.map((x) => [x.e, x.by, x.s, x.x]),
    frogList: a.frogs.map((f) => [f.e, f.s]), levels, T: Math.round(T) };
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--line", default="17")
    ap.add_argument("--stop", type=int, default=13)
    ap.add_argument("--secs", type=float, default=240)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.exists(os.path.join(ROOT, "data", f"line{args.line}.json")):
        print(f"skipped: no data/line{args.line}.json (python -I tools/snapshot.py data-fetch)")
        return 0
    faulthandler.dump_traceback_later(1200, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    pack, files = sample_pack()
    index = json.load(open(os.path.join(ROOT, "assets", "vehicles.json"), encoding="utf-8"))
    bad = {**pack, "id": "sample.bad", "events": {"gong": "buzzer.wav"}, "loops": {}}
    served = {"/assets/vehicles.json": ("application/json", json.dumps({**index, "sounds": [PACK, "sample.bad"]})),
              f"/assets/{PACK}/sounds.json": ("application/json", json.dumps(pack)),
              "/assets/sample.bad/sounds.json": ("application/json", json.dumps(bad)),
              **{f"/assets/{PACK}/{k}": ("audio/wav", v) for k, v in files.items()}}
    runs, fails, warns = {}, [], []

    def need(ok, why):
        if not ok:
            fails.append(why)

    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            for model in ("t3h", "t3simple"):
                ctx = browser.new_context(viewport={"width": 960, "height": 540})
                for path, (kind, body) in served.items():
                    ctx.route(base + path, lambda route, request, kind=kind, body=body: route.fulfill(content_type=kind, body=body))
                page = ctx.new_page()
                errors = []
                page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                page.on("console", lambda m: m.type == "warning" and "sound pack" in m.text and warns.append(m.text))
                page.goto(f"{base}/?line={args.line}", timeout=300000)
                page.wait_for_function("!document.getElementById('menu').classList.contains('hidden')", timeout=300000)
                runs[model] = page.evaluate(GAME, {"model": model, "secs": args.secs, "stop": args.stop})
                runs[model]["errors"] = errors
                ctx.close()
            browser.close()
    finally:
        server.shutdown()

    for model, r in runs.items():
        print(f"{model}: " + json.dumps({k: v for k, v in r.items() if k not in ("frogs", "frogList")}, ensure_ascii=False))
    print("warnings:", warns)
    h, s = runs["t3h"], runs["t3simple"]
    need(any("sample.bad" in w and "event gong: the game raises no such event" in w for w in warns), f"the bad pack is not refused by name: {warns}")
    need(s["packs"] == [PACK], f"packs loaded {s['packs']}")
    need(h["pack"] is None and s["pack"] == PACK, f"the hybrid sounds with {h['pack']}, the built-in car with {s['pack']}")
    want = [["bell"], ["door.buzzer", "door.close"], ["door.open"]]
    for model, by in (("t3h", "built-in"), ("t3simple", "pack")):
        d = runs[model]["doors"]
        need([e for e, _ in d] == [e for x in want for e in x] and all(b == by for _, b in d), f"{model}: bell and doors {d}, wants {want} by {by}")
    need(h["synth"] == {"motor": 1, "mg": 1, "flange": 1, "rolling": 1}, f"the hybrid's built-in loops {h['synth']}")
    need(s["synth"] == {"motor": 0, "mg": 0, "flange": 0, "rolling": 1} and sorted(s["loops"]) == ["flange", "mg", "motor"],
         f"the pack's loops {s['loops']}, the built-in voices {s['synth']} (the pack's muted, rolling kept)")
    need(s["levels"]["motor"] > 0.3 and s["levels"]["mg"] > 0.3, f"the pack's loops at most {s['levels']} on the drive")
    # every frog the whole set passed: each axle once, with the front where that axle is on the frog
    for model, r in runs.items():
        axles, by = sorted(r["axles"]), "pack" if model == "t3simple" else "built-in"
        passed = [(e, x) for e, x in r["frogList"] if x > r["s0"] + 0.5 and x + axles[-1] < r["s1"] - 0.5]
        need(len(passed) >= 3, f"{model}: only {len(passed)} frogs passed in {r['T']} s (s {r['s0']:.0f} → {r['s1']:.0f})")
        for e, x in passed:
            got = sorted(q[2] - x for q in r["frogs"] if q[3] == x and q[0] == e)
            ok = len(got) == len(axles) and all(abs(a - b) < 0.6 for a, b in zip(got, axles))
            need(ok and all(q[1] == by for q in r["frogs"] if q[3] == x), f"{model}: {e} at s {x:.1f}: the front at +{[round(g, 2) for g in got]}, wants the axles {axles} by {by}")
        kinds = {e for e, _ in passed}
        print(f"{model}: {len(passed)} frogs passed ({', '.join(sorted(kinds))}), {len(r['frogs'])} axle sounds, {r['cars']} cars")
        need(not r["errors"], f"{model}: page errors {r['errors']}")
    for f in fails:
        print("FAIL", f)
    print("sound events and packs: doors, bell, loops, frogs by axle, refusals: " + ("pass" if not fails else f"{len(fails)} failures"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
