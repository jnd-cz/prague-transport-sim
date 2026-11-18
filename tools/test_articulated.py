# SPDX-License-Identifier: AGPL-3.0-or-later
"""Articulated vehicles on the track (#579, src/articulated.js): python -P -E tools/test_articulated.py [--lines 9,17,22,23,37]
(its own server on a free port, a page with no game in it). Checks:
- the T3 (one section, two free bogies): on the straight as before; on a 20 m curve both pivots on it 6.4 m apart in a
  straight line, each bogie turned by asin(3.2 / R) against the body; on a 200 m crest both pivots on the profile;
- the Prague types the user named (2026-11-18: KT8D5, 14T, 15T, 52T, K2, KT4), their running gear from
  docs/research/articulated-trams.md (the 14T's and the 52T's positions estimated until a source gives them): on a
  25 m curve every support of every section on the curve, neighbouring sections' pins in one place, a carried
  section its length between its pins, a section on one fixed or limited bogie on the track's heading there, the
  15T's sections each on two axles of their bogies a wheelbase apart, the KT4's joint on the track (its rods split
  the bogies' turning evenly), the 52T's front support where its front puts it (it is placed from its second section);
  the KT4 with its rods' springs holding the joint straight below a turn of 0.05 rad: straight on a 300 m curve;
- a joint limit below a curve's angle holds its section there, its bogie off the track;
- the running gear's checks: every type passes, gear that cannot be placed is refused;
- on every line's route (in plan), each metre, every type: its joints' largest angle, none past a limit, the pins in
  one place; the T3's car centre against its old placement (pivots 6.4 m apart along the track): how far it moved."""
import argparse
import faulthandler
import functools
import http.server
import json
import os
import sys
import threading

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # (python -P leaves tools/ out)
import gpu  # noqa: E402  (Chromium on the GPU where it has one, #463)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The types, positions in m from the front coupler face (the body's front plus the coupler, from the lengths over and
# without couplers), from docs/research/articulated-trams.md. [E] marks an estimate. Joint limits are not known for
# any type: 0.6 rad here, which a 18 m curve stays under (the scans below measure it).
SHARED = """
const A = await import('/src/articulated.js'), { T3 } = await import('/src/tram.js');
const YAW = 0.6, wb = 1.9;
const free = (at, centre) => ({ at, centre, turn: 'free', wheelbase: wb }), fixed = (at) => ({ at, turn: 'fixed', wheelbase: wb });
const limited = (at) => ({ at, turn: 'limited', maxAngle: 0.1, wheelbase: wb }); // [E] the 52T's angle is not known
const pin = (at, bogie) => ({ at, yaw: YAW, pitch: null, ...(bogie ? { bogie: { turn: 'free', wheelbase: wb } } : {}) });
const sec = (from, to, ...bogies) => ({ from, to, bogies });
const TYPES = {
  T3,
  // KT8D5: pivots every 7.50 m from 3.90 m behind the body's front, the inner two under the joints' pins; couplers 0.47 m
  KT8D5: { sections: [sec(0.47, 11.87, free(4.37)), sec(11.87, 19.37), sec(19.37, 30.77, free(26.87))], joints: [pin(11.87, true), pin(19.37, true)] },
  // K2 [E]: the T3's 3.80 m end overhang, the middle bogie under the joint; couplers 0.55 m
  K2: { sections: [sec(0.55, 10.75, free(4.35)), sec(10.75, 20.95, free(17.15))], joints: [pin(10.75, true)] },
  // KT4: pivots 8.90 m apart, the joint midway on no bogie, steered by rods from the bogies [E: evenly], stiff in pitch
  KT4: { sections: [sec(0.47, 9.53, free(5.08)), sec(9.53, 18.58, free(13.98))], joints: [{ at: 9.53, yaw: YAW, pitch: 0, steer: 0.5 }] },
  // 15T, measured on Škoda's drawing: the end bogies' pivots w/6 off their middles toward the car's middle; between
  // the sections a bogie with a pivot over each axle and no pin; no coupler (an emergency one fitted by hand)
  '15T': { sections: [sec(0, 10.90, free(2.16, 1.85)), sec(10.90, 20.51), sec(20.51, 31.40, free(29.22, 29.57))],
    joints: [10.90, 20.51].map((at) => ({ at, yaw: YAW, pitch: null, bogie: { turn: 'free', wheelbase: wb, pivots: 'axles' } })) },
  // 14T [E positions]: fixed bogies under sections 1, 3 and 5, sections 2 and 4 hung between them; 30.25 m
  '14T': { sections: [sec(0, 8.4, fixed(4.0)), sec(8.2, 12.6), sec(12.4, 17.85, fixed(15.12)), sec(17.65, 22.05), sec(21.85, 30.25, fixed(26.25))],
    joints: [8.3, 12.5, 17.75, 21.95].map((at) => pin(at)) },
  // 52T [E positions]: free bogies under the end sections at their outer ends, the end sections resting on the next
  // one's pin; limited bogies under sections 2 and 4; section 3 hung between them; 31.99 m over the bumpers
  '52T': { sections: [sec(0, 8.6, free(2.6)), sec(8.4, 14.2, limited(11.3)), sec(14.0, 18.0), sec(17.8, 23.6, limited(20.7)), sec(23.4, 31.99, free(29.4))],
    joints: [8.5, 14.1, 17.9, 23.5].map((at) => pin(at)) },
};
// a point of section k of a pose at position a along the vehicle
const pt = (type, P, k, a) => { const S = type.sections[k], q = P.sections[k], m = (S.from + S.to) / 2, d = a - m, cp = Math.cos(q.pitch);
  return [q.p[0] - Math.sin(q.yaw) * cp * d, q.p[1] + Math.cos(q.yaw) * cp * d, q.p[2] - Math.sin(q.pitch) * d]; };
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
// the pins' mismatch: each pinned joint's point on the section ahead against the same on the section behind
const pins = (type, P) => Math.max(0, ...(type.joints || []).map((j, k) => (j.bogie?.pivots === 'axles' ? 0 : dist(pt(type, P, k, j.at), pt(type, P, k + 1, j.at)))));
const rests = (type, P) => A.restPoints(type, P).flat();
"""

SYNTH = """async () => {
""" + SHARED + """
  const out = {};
  // a straight heading north, then a left curve of radius R from s = 0 (x east, y north)
  const curve = (R) => (s) => s <= 0 ? [0, s, 0, 0] : [-R + R * Math.cos(s / R), R * Math.sin(s / R), 0, 0];
  const onCircle = (R, p) => Math.abs(Math.hypot(p[0] + R, p[1]) - R);
  // straight: the old placement exactly
  { const at = (s) => [0, s, 0, 0], P = A.placeUnit(T3, -20, at);
    out.straight = { b0: P.bogies[0].s + 24.4, b1: P.bogies[1].s + 30.8, mid: P.sections[0].p[1] + 27.6, yaw: Math.sin(P.sections[0].yaw - Math.atan2(0, -1)) }; }
  // the T3 on a 20 m curve, all of it in the curve
  { const R = 20, at = curve(R), P = A.placeUnit(T3, 40, at), [b0, b1] = P.bogies, p0 = at(b0.s), p1 = at(b1.s);
    out.t3curve = { on: Math.max(onCircle(R, p0), onCircle(R, p1)), chord: dist(p0, p1) - 6.4,
      turn: [Math.abs(b0.yaw), Math.abs(b1.yaw)].map((y) => y - Math.asin(3.2 / R)) }; }
  // the T3 over a crest of 200 m radius
  { const Rv = 200, at = (s) => [0, s, -s * s / (2 * Rv), 0], P = A.placeUnit(T3, 5, at);
    const z = P.bogies.map((b) => at(b.s)), c = P.sections[0].p;
    out.crest = { mid: Math.abs(c[2] - (z[0][2] + z[1][2]) / 2), chord: dist(z[0], z[1]) - 6.4, pitch: P.sections[0].pitch - Math.atan2(z[0][2] - z[1][2], Math.abs(z[0][1] - z[1][1])) }; }
  // every type on a 25 m curve, all of it in the curve
  out.types = {};
  { const R = 25, at = curve(R);
    for (const [name, type] of Object.entries(TYPES)) {
      const problems = A.gearProblems(type);
      if (problems.length) { out.types[name] = { problems }; continue; }
      const sF = 60, P = A.placeUnit(type, sF, at), g = A.gearOf(type), r = rests(type, P);
      const q = { problems, onTrack: Math.max(...r.map((x) => onCircle(R, x.p))), pins: pins(type, P), joints: P.joints,
        attack: Math.max(0, ...P.bogies.map((b) => Math.abs(b.attack))),
        // the first support where the front puts it (sFront less its position along the vehicle)
        front: dist(r[0].p, at(sF - r[0].at)) };
      // a carried section: its length between its pins
      q.carried = Math.max(0, ...type.sections.map((s, k) => (g.rests[k].length || k === 0 || k === type.sections.length - 1 ? 0
        : Math.abs(dist(pt(type, P, k, type.joints[k - 1].at), pt(type, P, k, type.joints[k].at)) - (type.joints[k].at - type.joints[k - 1].at)))));
      // the 15T: each bogie under a joint has its two axles' points a wheelbase apart, both on the curve
      q.axles = Math.max(0, ...(type.joints || []).map((j, k) => (j.bogie?.pivots === 'axles'
        ? Math.abs(dist(pt(type, P, k, j.at - wb / 2), pt(type, P, k + 1, j.at + wb / 2)) - wb) : 0)));
      // the KT4: the steered joint's point on the curve
      q.steered = Math.max(0, ...(type.joints || []).map((j, k) => (j.steer != null ? onCircle(R, pt(type, P, k, j.at)) : 0)));
      out.types[name] = q;
    }
    // a joint limit below the curve's angle: the KT8D5 with 0.05 rad
    const tight = { ...TYPES.KT8D5, joints: TYPES.KT8D5.joints.map((j) => ({ ...j, yaw: 0.05 })) }, H = A.placeUnit(tight, 60, at);
    out.held = { joints: H.joints, off: Math.max(...H.bogies.map((b) => b.off)), pins: pins(tight, H) };
  }
  // the KT4's rods held straight by their springs until the bogies' turn passes steerFrom: straight on a 300 m curve
  // (the bogies 0.03 rad apart), steering on a 25 m one
  { const kt4 = { ...TYPES.KT4, joints: [{ ...TYPES.KT4.joints[0], steerFrom: 0.05 }] };
    out.steerFrom = { wide: A.placeUnit(kt4, 60, curve(300)).joints[0].yaw, tight: A.placeUnit(kt4, 60, curve(25)).joints[0].yaw,
      even: A.placeUnit(TYPES.KT4, 60, curve(25)).joints[0].yaw }; }
  // gear that cannot be placed
  const f = (at) => ({ at, turn: 'free', wheelbase: 1.8 });
  const bad = {
    frontTurning: { sections: [{ from: 0, to: 10, bogies: [f(5)] }], joints: [] },
    lastCarried: { sections: [{ from: 0, to: 10, bogies: [f(2), f(8)] }, { from: 9, to: 15, bogies: [] }], joints: [{ at: 9.5 }] },
    twoCarried: { sections: [{ from: 0, to: 10, bogies: [f(2), f(8)] }, { from: 9, to: 15, bogies: [] }, { from: 14, to: 20, bogies: [] }, { from: 19, to: 30, bogies: [f(22), f(28)] }],
      joints: [{ at: 9.5 }, { at: 14.5 }, { at: 19.5 }] },
    overPinned: { sections: [{ from: 0, to: 10, bogies: [f(2), f(8)] }, { from: 9, to: 20, bogies: [f(12), f(18)] }], joints: [{ at: 9.5 }] },
    onlyFree: { sections: [{ from: 0, to: 10, bogies: [f(3)] }, { from: 9, to: 20, bogies: [f(16)] }], joints: [{ at: 9.5 }] },
  };
  out.refused = Object.fromEntries(Object.entries(bad).map(([k, t]) => [k, A.gearProblems(t)]));
  return out;
}"""

LINES = """async (lines) => {
""" + SHARED + """
  const { Route } = await import('/src/route.js'), out = {};
  for (const line of lines) {
    const data = await (await fetch(`/data/line${line}.json`)).json(), route = new Route(data.path, data.pathExt);
    const at = (s) => { const p = route.at(s); return [p.x, p.y, 0, 0]; };
    const r = { t3: { shift: 0, at: 0, turn: 0, turnAt: 0 }, length: Math.round(route.length) };
    for (const name of Object.keys(TYPES)) r[name] = { yaw: 0, yawAt: 0, held: 0, pins: 0, off: 0, attack: 0 };
    for (let s = 40; s < route.length - 5; s += 1) {
      const T = A.placeUnit(T3, s, at), c = s - 7.6, a = at(c + 3.2), b = at(c - 3.2), old = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0];
      const d = dist(T.sections[0].p, old), turn = Math.max(...T.bogies.map((x) => Math.abs(x.yaw)));
      if (d > r.t3.shift) Object.assign(r.t3, { shift: d, at: s });
      if (turn > r.t3.turn) Object.assign(r.t3, { turn, turnAt: s });
      for (const [name, type] of Object.entries(TYPES)) {
        const P = A.placeUnit(type, s, at), q = r[name], y = Math.max(0, ...P.joints.map((j) => Math.abs(j.yaw) + (j.over || 0)));
        if (y > q.yaw) Object.assign(q, { yaw: y, yawAt: s });
        q.held += P.joints.filter((j) => j.held || j.over > 0).length;
        q.pins = Math.max(q.pins, pins(type, P));
        q.off = Math.max(q.off, ...P.bogies.map((x) => x.off));
        q.attack = Math.max(q.attack, ...P.bogies.map((x) => Math.abs(x.attack)));
      }
    }
    out[line] = r;
  }
  return out;
}"""


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lines", default="9,17,22,23,37")
    args = ap.parse_args()
    lines = [x for x in args.lines.split(",") if x]
    missing = [x for x in lines if not os.path.exists(os.path.join(ROOT, "data", f"line{x}.json"))]
    if missing:
        print(f"lines {','.join(missing)}: no data/lineN.json (python -I tools/snapshot.py data-fetch); their routes are left out")
        lines = [x for x in lines if x not in missing]
    faulthandler.dump_traceback_later(900, exit=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fails = []
    try:
        with sync_playwright() as p:
            browser = gpu.launch(p)[0]
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/README.md")
            r = page.evaluate(SYNTH)
            r["lines"] = page.evaluate(LINES, lines) if lines else {}
            r["errors"] = errors[:3]
            browser.close()
    finally:
        server.shutdown()
    print(json.dumps(r, indent=1))
    st = r["straight"]
    if max(abs(st["b0"]), abs(st["b1"]), abs(st["mid"]), abs(st["yaw"])) > 1e-6:
        fails.append(f"the T3 on the straight is not where it stood: {st}")
    c = r["t3curve"]
    if c["on"] > 1e-6 or abs(c["chord"]) > 1e-5 or max(abs(x) for x in c["turn"]) > 1e-4:
        fails.append(f"the T3 on a 20 m curve: pivots off it, not 6.4 m apart, or bogies not at asin(3.2/R): {c}")
    k = r["crest"]
    if k["mid"] > 1e-6 or abs(k["chord"]) > 1e-5 or abs(k["pitch"]) > 1e-6:
        fails.append(f"the T3 over a 200 m crest: {k}")
    for name, q in r["types"].items():
        if q["problems"]:
            fails.append(f"{name}: its running gear refused: {q['problems']}")
            continue
        if q["onTrack"] > 1e-5 or q["pins"] > 1e-5 or any(j["held"] or j["over"] for j in q["joints"]):
            fails.append(f"{name} on a 25 m curve: a support off it ({q['onTrack']:.2g} m), the pins {q['pins']:.2g} m apart, or a joint at its limit")
        if q["attack"] > 1e-6 or q["carried"] > 1e-5 or q["axles"] > 1e-5 or q["steered"] > 1e-5 or q["front"] > 1e-3:
            fails.append(f"{name} on a 25 m curve: a fixed or limited bogie off the track's heading ({q['attack']:.2g} rad), a carried section "
                         f"off its length ({q['carried']:.2g}), a bogie's axles off its wheelbase ({q['axles']:.2g}), the steered joint off the track "
                         f"({q['steered']:.2g}) or the front support off its s ({q['front']:.2g} m)")
    h = r["held"]
    if not (h["joints"][0]["held"] and abs(abs(h["joints"][0]["yaw"]) - 0.05) < 1e-9 and h["off"] > 0.05 and h["pins"] < 1e-6):
        fails.append(f"a joint past its limit is not held there with its bogie off the track: {h}")
    sf = r["steerFrom"]
    if abs(sf["wide"]) > 1e-9 or not 0 < abs(sf["tight"]) < abs(sf["even"]):
        fails.append(f"the KT4's steered joint with steerFrom 0.05: not straight on a 300 m curve, or not steering less on a 25 m one: {sf}")
    for name, problems in r["refused"].items():
        if not problems:
            fails.append(f"gear {name} not refused")
    for line, q in r["lines"].items():
        for name in r["types"]:
            if name in q and (q[name]["held"] or q[name]["pins"] > 1e-5):
                fails.append(f"line {line}, {name}: {q[name]['held']} joints at or past their limits (the largest {q[name]['yaw']:.3f} rad at s {q[name]['yawAt']}), pins {q[name]['pins']:.2g} m apart")
        if q["t3"]["shift"] > 0.05:
            fails.append(f"line {line}: the T3's car moved {q['t3']['shift']:.3f} m from its old placement at s {q['t3']['at']}")
    if r["errors"]:
        fails.append(f"page errors: {r['errors']}")
    for f in fails:
        print("FAIL", f)
    print("ok" if not fails else f"{len(fails)} failed")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
