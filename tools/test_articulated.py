# SPDX-License-Identifier: AGPL-3.0-or-later
"""Articulated vehicles on the track (#579, src/articulated.js): python -P -E tools/test_articulated.py [--lines 9,17,22,23,37]
(its own server on a free port, a page with no game in it). Checks:
- the T3 (one section, two free bogies): on the straight as before; on a 20 m curve both pivots on it 6.4 m apart in a
  straight line, each bogie turned by asin(3.2 / R) against the body; on a 200 m crest both pivots on the profile;
- two samples (made up until the user's types, #579 question 1): three sections with free end bogies and Jacobs
  bogies under the joints; three sections with the middle one carried by its joints and the end ones on fixed bogies.
  On a 25 m curve every pivot on it, the pins of neighbouring sections in one place, the carried section its length
  between its pins, a fixed bogie's section on the track's heading; a joint limit below the curve's angle holds its
  section there, its bogie off the track;
- the running gear's checks: the T3 and the samples pass, gear that cannot be placed from the front is refused;
- on every line's route (in plan), each metre: the samples' joints within their limits, their pins in one place; the
  T3's car centre against its old placement (pivots 6.4 m apart along the track): how far it moved, the largest at
  the line's tightest curve."""
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

# the samples (lengths and limits made up, #579 question 1) and the synthetic tracks, shared by both scripts
SHARED = """
const A = await import('/src/articulated.js'), { T3 } = await import('/src/tram.js');
const free = (at) => ({ at, turn: 'free', wheelbase: 1.8 }), fixed = (at) => ({ at, turn: 'fixed', wheelbase: 1.8 });
const YAW = 0.6, PITCH = 0.1;
const JACOBS = { sections: [{ from: 0.3, to: 10.9, bogies: [free(3.0)] }, { from: 10.3, to: 19.9, bogies: [] }, { from: 19.3, to: 29.9, bogies: [free(27.2)] }],
  joints: [{ at: 10.6, yaw: YAW, pitch: PITCH, bogie: { turn: 'free', wheelbase: 1.8 } }, { at: 19.6, yaw: YAW, pitch: PITCH, bogie: { turn: 'free', wheelbase: 1.8 } }] };
const CARRIED = { sections: [{ from: 0.3, to: 9.6, bogies: [fixed(5.0)] }, { from: 9.2, to: 14.6, bogies: [] }, { from: 14.2, to: 23.5, bogies: [fixed(18.8)] }],
  joints: [{ at: 9.4, yaw: YAW, pitch: PITCH }, { at: 14.4, yaw: YAW, pitch: PITCH }] };
// a point of section k of a pose at position a along the vehicle
const pt = (type, P, k, a) => { const S = type.sections[k], q = P.sections[k], m = (S.from + S.to) / 2, d = a - m, cp = Math.cos(q.pitch);
  return [q.p[0] - Math.sin(q.yaw) * cp * d, q.p[1] + Math.cos(q.yaw) * cp * d, q.p[2] - Math.sin(q.pitch) * d]; };
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
// the pins' mismatch: each joint's point on the section ahead against the same on the section behind
const pins = (type, P) => Math.max(0, ...(type.joints || []).map((j, k) => dist(pt(type, P, k, j.at), pt(type, P, k + 1, j.at))));
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
  // the samples on a 25 m curve
  { const R = 25, at = curve(R);
    const J = A.placeUnit(JACOBS, 60, at), C = A.placeUnit(CARRIED, 60, at);
    out.jacobs = { pins: pins(JACOBS, J),
      onTrack: Math.max(...A.bogiesOf(JACOBS).map((b) => onCircle(R, pt(JACOBS, J, b.sec, b.at)))), joints: J.joints, problems: A.gearProblems(JACOBS) };
    const fb = A.bogiesOf(CARRIED);
    out.carried = { onTrack: Math.max(...fb.map((b) => onCircle(R, pt(CARRIED, C, b.sec, b.at)))), pins: pins(CARRIED, C),
      length: dist(pt(CARRIED, C, 1, 9.4), pt(CARRIED, C, 1, 14.4)) - 5.0,
      heading: fb.map((b, i) => Math.abs(C.bogies[i].attack)), joints: C.joints, problems: A.gearProblems(CARRIED) };
    // a joint limit below the curve's angle
    const tight = { ...JACOBS, joints: JACOBS.joints.map((j) => ({ ...j, yaw: 0.05 })) }, H = A.placeUnit(tight, 60, at);
    out.held = { joints: H.joints, off: Math.max(...H.bogies.map((b) => b.off)), pins: pins(tight, H) };
  }
  // gear that cannot be placed from the front
  const bad = {
    frontTurning: { sections: [{ from: 0, to: 10, bogies: [free(5)] }], joints: [] },
    lastCarried: { sections: [{ from: 0, to: 10, bogies: [free(2), free(8)] }, { from: 9, to: 15, bogies: [] }], joints: [{ at: 9.5 }] },
    twoCarried: { sections: [{ from: 0, to: 10, bogies: [free(2), free(8)] }, { from: 9, to: 15, bogies: [] }, { from: 14, to: 20, bogies: [] }, { from: 19, to: 30, bogies: [free(22), free(28)] }],
      joints: [{ at: 9.5 }, { at: 14.5 }, { at: 19.5 }] },
    overPinned: { sections: [{ from: 0, to: 10, bogies: [free(2), free(8)] }, { from: 9, to: 20, bogies: [free(12), free(18)] }], joints: [{ at: 9.5 }] },
  };
  out.refused = Object.fromEntries(Object.entries(bad).map(([k, t]) => [k, A.gearProblems(t)]));
  out.t3problems = A.gearProblems(T3);
  return out;
}"""

LINES = """async (lines) => {
""" + SHARED + """
  const { Route } = await import('/src/route.js'), out = {};
  for (const line of lines) {
    const data = await (await fetch(`/data/line${line}.json`)).json(), route = new Route(data.path, data.pathExt);
    const at = (s) => { const p = route.at(s); return [p.x, p.y, 0, 0]; };
    const r = { t3: { shift: 0, at: 0, turn: 0, turnAt: 0 }, jacobs: { yaw: 0, held: 0, pins: 0, off: 0 }, carried: { yaw: 0, held: 0, pins: 0, attack: 0 } };
    for (let s = 40; s < route.length - 5; s += 1) {
      const T = A.placeUnit(T3, s, at), c = s - 7.6, a = at(c + 3.2), b = at(c - 3.2), old = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0];
      const d = dist(T.sections[0].p, old), turn = Math.max(...T.bogies.map((x) => Math.abs(x.yaw)));
      if (d > r.t3.shift) Object.assign(r.t3, { shift: d, at: s });
      if (turn > r.t3.turn) Object.assign(r.t3, { turn, turnAt: s });
      for (const [k, type] of [['jacobs', JACOBS], ['carried', CARRIED]]) {
        const P = A.placeUnit(type, s, at), q = r[k];
        q.yaw = Math.max(q.yaw, ...P.joints.map((j) => Math.abs(j.yaw) + (j.over || 0)));
        q.held += P.joints.filter((j) => j.held || j.over > 0).length;
        q.pins = Math.max(q.pins, pins(type, P));
        if ('off' in q) q.off = Math.max(q.off, ...P.bogies.map((x) => x.off));
        if ('attack' in q) q.attack = Math.max(q.attack, ...P.bogies.map((x) => Math.abs(x.attack)));
      }
    }
    r.length = Math.round(route.length);
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
    faulthandler.dump_traceback_later(600, exit=True)
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
    for name in ("jacobs", "carried"):
        q = r[name]
        if q["problems"]:
            fails.append(f"sample {name} refused: {q['problems']}")
        if q["onTrack"] > 1e-5 or q["pins"] > 1e-6 or any(j["held"] or j["over"] for j in q["joints"]):
            fails.append(f"sample {name} on a 25 m curve: a pivot off the curve, the pins apart, or a joint at its limit: {q}")
    q = r["carried"]
    if abs(q["length"]) > 1e-6 or max(q["heading"]) > 1e-6:
        fails.append(f"the carried section is not its length between its pins, or a fixed bogie's section is off the track's heading: {q}")
    h = r["held"]
    if not (h["joints"][0]["held"] and abs(abs(h["joints"][0]["yaw"]) - 0.05) < 1e-9 and h["off"] > 0.05 and h["pins"] < 1e-6):
        fails.append(f"a joint past its limit is not held there with its bogie off the track: {h}")
    for name, problems in r["refused"].items():
        if not problems:
            fails.append(f"gear {name} not refused")
    if r["t3problems"]:
        fails.append(f"the T3's gear refused: {r['t3problems']}")
    for line, q in r["lines"].items():
        for name in ("jacobs", "carried"):
            if q[name]["held"] or q[name]["pins"] > 1e-5:
                fails.append(f"line {line}, sample {name}: {q[name]['held']} joints at or past their limits, pins {q[name]['pins']:.2g} m apart: {q[name]}")
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
