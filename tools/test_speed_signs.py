"""The speed signs' placement rule and faces (src/speedSigns.js) and the speeds over trackwork (src/speedRules.js, #211), in headless Chromium:

    python -P -E tools/test_speed_signs.py
    python -P -E tools/test_speed_signs.py --sheet reports/speed_signs.png   # also a sheet of every face, to compare with D 1/2 p. 45-47, 52-56
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
sys.stdout.reconfigure(encoding="utf-8")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


RULES = r"""
async () => {
  const { planSigns: plan, brakingDistance, signSize } = await import('/src/speedSigns.js');
  const fill = (...parts) => parts.flatMap(([v, m]) => Array(m / 5).fill(v));
  const kinds = (r) => r.map((g) => `${g.kind}${g.v ?? g.digit ?? ''}@${g.s}`);
  return {
    plainStreet: kinds(plan({ posted: fill([0, 500]) })),
    tagged50: kinds(plan({ posted: fill([0, 200], [50, 300]) })),
    rychlostnik: kinds(plan({ posted: fill([50, 300], [60, 300], [50, 300]) })),
    rychlostnikToRestriction: kinds(plan({ posted: fill([50, 300], [60, 300], [30, 100], [50, 300]) })),
    t3On70: kinds(plan({ posted: fill([60, 300], [70, 300], [60, 300]) })),
    restriction: kinds(plan({ posted: fill([50, 300], [40, 100], [50, 300]) })),
    bigDrop: kinds(plan({ posted: fill([50, 300], [20, 100], [50, 300]) })),
    shortDrop: kinds(plan({ posted: fill([50, 300], [30, 10], [50, 300]) })),
    switchPiece: kinds(plan({ posted: fill([50, 300], [15, 40], [50, 300]), trackwork: [310] })),
    plain15: kinds(plan({ posted: fill([50, 300], [15, 40], [50, 300]) })),
    curve: kinds(plan({ posted: fill([0, 500]), smallRadius: [{ from: 100, to: 130, side: 'left' }] })),
    curveOnSwitch: kinds(plan({ posted: fill([0, 500]), smallRadius: [{ from: 100, to: 130 }], trackwork: [120] })),
    zone: kinds(plan({ posted: fill([0, 500]), zones: [{ from: 100, to: 300, v: 40 }] })),
    descent: kinds(plan({ posted: fill([0, 900]), gradients: [{ from: 100, to: 570, permille: 80 }] })),
    braking50: brakingDistance(50), braking60: brakingDistance(60),
    plateSize: signSize({ kind: 'restriction', v: 30 }),
    arrowSize: signSize({ kind: 'restriction', v: 10, arrow: 'left' }),
    backed: signSize({ kind: 'restriction', v: 30, backing: true }),
  };
}
"""

SPEED_RULES = r"""
async () => {
  const { speedFacts, trackworkStretches, withoutOwnPieces, placeStretches, FROG } = await import('/src/speedRules.js');
  const { Route } = await import('/src/route.js');
  const truth = await (await fetch('/data/truth.json')).json();
  const facts = speedFacts(truth);
  let missing = null;
  try { speedFacts({ operation: { facts: [] } }); } catch (e) { missing = String(e.message); }
  const work = { trailing: [{ s: 200, fromDiverging: true }, { s: 300, fromDiverging: false, frog: 12 }], crossings: [400] };
  const own = (posted, trackwork) => withoutOwnPieces(posted, 5, [{ s: 100 }], trackwork, facts);
  const fill = (...parts) => parts.flatMap(([v, n]) => Array(n).fill(v));
  const stops = [{ name: 'A', s: 0 }, { name: 'Hercovka', s: 100 }, { name: 'Nad Trojou', s: 200 }];
  // a straight, an arc of radius 30 m with no transition from x = 200, a quarter turn, and a straight
  const arc = [];
  for (let x = 0; x <= 200; x += 1) arc.push([x, 0]);
  const R = 30, turn = Math.PI / 2, curveLen = R * turn;
  for (let t = 1 / R; t < turn; t += 1 / R) arc.push([200 + R * Math.sin(t), R - R * Math.cos(t)]);
  for (let y = 0; y <= 200; y += 1) arc.push([200 + R, R + y]);
  const route = new Route(arc);
  const end = 200 + curveLen;
  const window = (past) => {
    const lim = route.speedLimits([], past);
    let lowest = 99, last = 0, top = 0;
    for (let m = 150; m < 330; m++) lowest = Math.min(lowest, lim.at(m));
    for (let m = 150; m < 330; m++) { if (lim.at(m) === lowest) last = m; if (lim.at(m) < 50) top = m; }
    return { lowest, last, top };
  };
  const ladder = route.speedLimits([{ from: 100, to: 110, v: 15 }], 2);
  return {
    limits: { end, none: window(0), two: window(2), fifteen: window(15) },
    extra: { at105: ladder.at(105), at110: ladder.at(110.5), at111: ladder.at(111), bin: ladder.values[21], bin2: ladder.values[23], restriction: ladder.restriction(105), free: ladder.restriction(120) },
    places: {
      read: facts.places,
      untagged: placeStretches(facts.places, stops, Array(60).fill(0), 5),
      tagged: placeStretches(facts.places, stops, Array(60).fill(25), 5),
      noData: placeStretches(facts.places, stops, undefined, 5),
      partly: placeStretches(facts.places, stops, fill([0, 30], [25, 10], [0, 20]), 5),
      uphill: placeStretches(facts.places, [{ name: 'Nad Trojou', s: 100 }, { name: 'Hercovka', s: 200 }], Array(60).fill(0), 5),
    },
    facts, missing, FROG,
    stretches: trackworkStretches([{ s: 100 }, { s: 150, frog: 13 }], work, facts),
    noData: trackworkStretches([{ s: 100 }], undefined, facts),
    ownDropped: own(fill([50, 19], [15, 4], [50, 5]), work),
    farKept: own(fill([50, 40], [15, 2], [50, 5]), { trailing: [], crossings: [] }),
    withoutWork: own(fill([50, 19], [15, 4], [50, 5]), null),
  };
}
"""

PIXELS = r"""
async () => {
  const { drawSign, drawLedPanel, signSize, KINDS } = await import('/src/speedSigns.js');
  const colour = (spec, fx, fy) => {
    const s = signSize(spec), W = 200, H = Math.round(W * s.h / s.w), c = document.createElement('canvas');
    c.width = W; c.height = H;
    const g = c.getContext('2d', { willReadFrequently: true });
    drawSign(g, spec, W, H);
    const d = g.getImageData(Math.floor(fx * W), Math.floor(fy * H), 1, 1).data;
    return [d[0], d[1], d[2]];
  };
  const led = (spec, fx, fy) => {
    const c = document.createElement('canvas'); c.width = 200; c.height = 140;
    const g = c.getContext('2d', { willReadFrequently: true });
    drawLedPanel(g, spec, 200, 140);
    return [...g.getImageData(fx * 200, fy * 140, 1, 1).data].slice(0, 3);
  };
  const all = [];
  for (const kind of KINDS) {
    const c = document.createElement('canvas'); c.width = 100; c.height = 200;
    drawSign(c.getContext('2d'), { kind, v: 30, digit: 3, permille: 80 }, 100, 200);
    all.push(kind);
  }
  return {
    drawn: all.length,
    restrictionFrame: colour({ kind: 'restriction', v: 30 }, 0.05, 0.5),
    restrictionPanel: colour({ kind: 'restriction', v: 30 }, 0.25, 0.14),
    higherPanel: colour({ kind: 'higher', v: 60 }, 0.25, 0.14),
    slowPanel: colour({ kind: 'slow' }, 0.5, 0.5),
    backingEdge: colour({ kind: 'restriction', v: 30, backing: true }, 0.03, 0.5),
    triangleMiddle: colour({ kind: 'warning' }, 0.5, 0.3),
    entryGoCentre: led({ kind: 'entry', state: 'go' }, 0.5, 0.5),
    entryStopSide: led({ kind: 'entry', state: 'stop' }, 0.3, 0.5),
    entryGoSide: led({ kind: 'entry', state: 'go' }, 0.3, 0.5),
    darkChevron: led({ kind: 'chevron', dir: 'straight', dark: true }, 0.5, 0.14),
  };
}
"""

SHEET = r"""
async () => {
  const { drawSign, drawLedPanel, signSize } = await import('/src/speedSigns.js');
  document.body.style.cssText = 'margin:0;background:#8fa0ad;font:13px Arial,sans-serif;color:#111;width:1180px';
  const signs = [
    ['SIG-V1 restriction', { kind: 'restriction', v: 30 }], ['V1 over a fork', { kind: 'restriction', v: 10, arrow: 'left' }],
    ['V1 on a backing board', { kind: 'restriction', v: 30, backing: true }], ['SIG-V2 Pomalu', { kind: 'slow' }], ['SIG-V3 end', { kind: 'end' }],
    ['SIG-V4 warning 3', { kind: 'warning', digit: 3 }], ['V4 before Pomalu', { kind: 'warning' }], ['SIG-V5 point', { kind: 'point', v: 20 }],
    ['SIG-V6 Rychlostník', { kind: 'higher', v: 60 }], ['V6 65', { kind: 'higher', v: 65 }], ['V6 by car type (no source)', { kind: 'higher', v: 70, carType: '14T' }],
    ['SIG-V7 end', { kind: 'higherEnd' }], ['SIG-V8 small radius', { kind: 'smallRadius', curve: 'right' }], ['SIG-V9 switch V', { kind: 'switchV' }],
    ['SIG-V10 zone', { kind: 'zone', v: 40 }], ['SIG-V11 end of zone', { kind: 'zoneEnd', v: 40 }],
    ['SIG-G1 climb', { kind: 'climb', permille: 80 }], ['SIG-G2 end', { kind: 'climbEnd', permille: 80 }], ['SIG-G3 descent', { kind: 'descent', permille: 80 }], ['SIG-G4 end', { kind: 'descentEnd', permille: 80 }],
  ];
  const panels = [
    ['SW-R3 entry, go', { kind: 'entry', state: 'go' }, 90, 90], ['entry, stop', { kind: 'entry', state: 'stop' }, 90, 90],
    ['SW-R4 set straight', { kind: 'chevron', dir: 'straight' }, 130, 90], ['set right', { kind: 'chevron', dir: 'right' }, 130, 90], ['set left', { kind: 'chevron', dir: 'left' }, 130, 90],
    ['undetermined', { kind: 'undetermined' }, 130, 90], ['number 50', { kind: 'number', v: 50 }, 130, 90], ['number 40', { kind: 'number', v: 40 }, 130, 90], ['no number', { kind: 'number', dark: true }, 130, 90],
  ];
  const cell = (label, draw, w, h) => {
    const d = document.createElement('div');
    d.style.cssText = 'display:inline-block;vertical-align:bottom;margin:10px;text-align:center;width:' + Math.max(w, 96) + 'px';
    const c = document.createElement('canvas'); c.width = w * 2; c.height = h * 2; c.style.cssText = `width:${w}px;height:${h}px`;
    draw(c.getContext('2d'), w * 2, h * 2);
    const t = document.createElement('div'); t.textContent = label; t.style.marginTop = '4px';
    d.append(c, t); document.body.append(d);
  };
  for (const [label, sign] of signs) {
    const s = signSize(sign), u = 500;
    cell(label, (g, W, H) => drawSign(g, sign, W, H), Math.round(s.w * u), Math.round(s.h * u));
  }
  const br = document.createElement('div'); document.body.append(br);
  for (const [label, panel, w, h] of panels) cell(label, (g, W, H) => drawLedPanel(g, panel, W, H), w, h);
  return document.body.scrollHeight;
}
"""


def check(r, p):
    f = []
    def want(name, got, expected):
        if got != expected:
            f.append(f"{name}: {got} != {expected}")
    want("a street with no tag has no sign", r["plainStreet"], [])
    want("a tagged 50 after untagged track has no sign", r["tagged50"], [])
    want("Rychlostník and its end", r["rychlostnik"], ["higher60@300", "higherEnd@600"])
    want("a restriction ends a Rychlostník, no end sign of its own", r["rychlostnikToRestriction"], ["higher60@300", "warning3@400", "restriction30@600", "end@700"])
    want("a T3 on the 70 stretch has 65", r["t3On70"], ["higher65@300", "higher60@600"])
    want("a restriction of 10 km/h less has no warning", r["restriction"], ["restriction40@300", "end@400"])
    want("a drop of 30 has its warning at braking distance", r["bigDrop"], ["warning2@160", "restriction20@300", "end@400"])
    want("a stretch under 25 m has no sign", r["shortDrop"], [])
    want("a switch's own 15 has no sign", r["switchPiece"], [])
    want("a 15 away from any switch has one", r["plain15"], ["warning1@160", "restriction15@300", "end@340"])
    want("a small-radius curve", r["curve"], ["smallRadius15@100"])
    want("the curve at a switch has no sign (§ 49.19)", r["curveOnSwitch"], [])
    want("a zone and its end", r["zone"], ["zone40@100", "zoneEnd40@300"])
    want("a dangerous descent and its end", r["descent"], ["descent@100", "descentEnd@570"])
    want("braking distance from 50", r["braking50"], 140)
    want("braking distance from 60", r["braking60"], 200)
    want("the plate", r["plateSize"], {"w": 0.2, "h": 0.3})
    want("the plate with an arrow", r["arrowSize"], {"w": 0.2, "h": 0.35})
    want("the backing board", r["backed"], {"w": 0.28, "h": 0.38})
    white, yellow, black = lambda c: min(c) > 200, lambda c: c[0] > 220 and c[1] > 170 and c[2] < 60, lambda c: max(c) < 40
    want("15 kinds drawn", p["drawn"], 15)
    for name, test, c in (("the white frame", white, p["restrictionFrame"]), ("the yellow panel", yellow, p["restrictionPanel"]),
                          ("the Rychlostník's black panel", black, p["higherPanel"]), ("Pomalu's bare panel", yellow, p["slowPanel"]),
                          ("the yellow backing", yellow, p["backingEdge"]), ("the triangle's yellow", yellow, p["triangleMiddle"]),
                          ("entry go: the bar", white, p["entryGoCentre"]), ("entry stop: the bar", white, p["entryStopSide"]),
                          ("entry go: dark beside the bar", black, p["entryGoSide"]), ("a dark panel", black, p["darkChevron"])):
        if not test(c):
            f.append(f"{name}: {c}")
    return f


def check_rules(r):
    f = []
    def want(name, got, expected):
        if got != expected:
            f.append(f"{name}: {got} != {expected}")
    want("the facts by id", r["facts"], {"facing": 15, "trailingDiverging": 15, "trailingStraight": 30, "crossing": 15, "general": 50, "smallRadius": 15,
                                         "past": 2, "places": [{"from": "Hercovka", "to": "Nad Trojou", "v": 25}]})
    if "no value" not in (r["missing"] or ""):
        f.append(f"a missing fact must stop the game: {r['missing']}")
    want("switches from the blades to 2 m past the frog, 15 km/h, whichever way they are set", r["noData"], [{"from": 96, "to": 100 + r["FROG"] + 2, "v": 15}])
    want("every kind of trackwork, each 2 m past its end", r["stretches"], [
        {"from": 96, "to": 100 + r["FROG"] + 2, "v": 15}, {"from": 146, "to": 165, "v": 15},
        {"from": 200 - r["FROG"], "to": 206, "v": 15}, {"from": 288, "to": 306, "v": 30}, {"from": 397, "to": 405, "v": 15}])
    p = r["places"]
    want("Trojská's fact where OSM tags nothing", p["untagged"], [{"from": 100, "to": 200, "v": 25}])
    want("OSM comes first", p["tagged"], [])
    want("without speeds in the data the fact holds", p["noData"], [{"from": 100, "to": 200, "v": 25}])
    want("only the untagged part", p["partly"], [{"from": 100, "to": 150, "v": 25}])
    want("not uphill", p["uphill"], [])
    # the curve's end, 2 m past, against the 16 m estimate's own smear of it (R 30, no transition: the worst case)
    lim = r["limits"]
    if lim["two"]["last"] >= lim["fifteen"]["last"]:
        f.append(f"a narrower margin must lift the lowest speed sooner: {lim}")
    if lim["two"]["last"] != lim["none"]["last"] + 2:
        f.append(f"the margin moves the limit's end by itself: {lim}")
    if not lim["end"] - 10 <= lim["two"]["last"] <= lim["end"] + 2:
        f.append(f"the lowest speed must end by 2 m past the curve: {lim}")
    x = r["extra"]
    want("a restriction is exact to the metre", [x["at105"], x["at110"], x["at111"]], [15, 15, 50])
    want("the 5 m table holds each bin's lowest", [x["bin"], x["bin2"]], [15, 50])
    want("restriction() reads the restrictions alone", [x["restriction"], x["free"]], [15, 99])
    want("OSM's 15 at a switch is the switch's own", r["ownDropped"], [50] * 19 + [0] * 4 + [50] * 5)
    want("a 15 elsewhere stays", r["farKept"], [50] * 40 + [15] * 2 + [50] * 5)
    want("without the line's trackwork OSM's 15 stays", r["withoutWork"], [50] * 19 + [15] * 4 + [50] * 5)
    return f


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sheet")
    a = ap.parse_args()
    faulthandler.dump_traceback_later(120, exit=True)  # the whole test: page.evaluate has no time limit
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1180, "height": 800}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(base + "/__signs.html", lambda route: route.fulfill(content_type="text/html", body="<!doctype html><html><body></body></html>"))
        page.goto(base + "/__signs.html")
        rules = page.evaluate(RULES)
        pixels = page.evaluate(PIXELS)
        speed_rules = page.evaluate(SPEED_RULES) if os.path.exists(os.path.join(ROOT, "data", "truth.json")) else None
        if a.sheet:
            page.evaluate(SHEET)
            page.screenshot(path=a.sheet, full_page=True)
        browser.close()
    server.shutdown()
    fails = check(rules, pixels) + (check_rules(speed_rules) if speed_rules else []) + [f"page error: {e}" for e in errors]
    if fails:
        print(json.dumps(rules, ensure_ascii=False, indent=0))
        print("FAILED\n  " + "\n  ".join(fails))
        sys.exit(1)
    print("speed signs: every rule and face as expected")


if __name__ == "__main__":
    main()
