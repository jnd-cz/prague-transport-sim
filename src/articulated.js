// SPDX-License-Identifier: AGPL-3.0-or-later
// A vehicle's running gear as data, and its pose on the track from it (#579): rigid sections in a row, each on its own
// bogies or carried by its neighbours through joints. A type (src/tram.js VEHICLE_TYPES, later a package's manifest) has
//   sections  [{ from, to, bogies: [{ at, centre, turn, maxAngle, wheelbase }] }], front to rear: the body's extent and
//             its bogies; `at` is where the section rests on the bogie (its pivot), `centre` the bogie's middle between
//             its axles when the pivot is off it (the 15T's end bogies: w/6 toward the car's middle, Škoda's patent
//             CZ297213B6 and its product sheet's drawing, docs/research/articulated-trams.md)
//   joints    [{ at, yaw, pitch, bogie, steer }]: joint k joins sections k and k + 1. yaw and pitch are its freedom (a
//             largest angle in rad, or null: free). bogie, when the joint stands on one ({ turn, maxAngle, wheelbase,
//             pivots }): on one pin shared by both sections (the KT8D5, the K2), or with pivots: 'axles' one pivot over
//             each axle, the section ahead on the front one and the one behind on the rear one, and no pin between
//             them (the 15T). steer: a joint with no bogie whose angle rods from the two sections' bogies set (the
//             KT4): the rear section's yaw against the front's is steer × the rear bogie's turn against the front one's,
//             once that turn is past steerFrom (rad, default 0): the rods' spring links hold the joint straight below it
//             (a KT4 driver's account: the mechanism takes hold late, only at a larger turn of the bogies, so the car
//             runs straight and calm on straight track; k-report.net, 2023-10-11, docs/research/articulated-trams.md)
// Positions are along the vehicle in m from its front coupler face, on straight track. A bogie turns 'free' (a pivot),
// 'limited' (springs or stops: to maxAngle against its section) or 'fixed' (not at all). The sections are usually
// coupled freely, pivoted at different places, and some bogies turn less or not at all against the chassis (PR #577).
//
// placeUnit() puts a unit on the track. It starts at the first section that stands on its own:
// - on two supports on the track (its bogies' pivots, a joint's bogie, an axle of a bogie with a pivot over each), the
//   first at the s its position along the vehicle gives, the second by their distance in a straight line (the chord
//   of a curve, shorter than the arc);
// - on one fixed or limited bogie, with the track's heading there (a limited bogie's springs centre it: the 14T, the
//   52T's inner sections);
// - or the first two sections on a steered joint, solved together (the KT4).
// From there each section behind it is placed from the one ahead, and each ahead of it from the one behind:
// - a section on a pin hangs on it: the line from the pin to its one support on the far side;
// - a section on a bogie with a pivot over each axle stands on that bogie's other axle (the bogie's wheelbase from the
//   neighbour's) and on its own support;
// - a section with no support beside its pins is carried by them: placed with the section behind it, which stands on
//   its own, solved so that the two pins are its length apart (the 14T's and the 52T's middle sections).
// A unit placed from a section behind its front is then moved until its first support stands at the s it should.
// A joint past its yaw or pitch freedom holds a hanging section at the limit, turned about the pin; its bogies then
// stand off the track, by `off` m: the flanges' work. A bogie past its own freedom (limited, fixed) keeps its section's
// line and logs its angle of attack beyond it (`attack`, rad). A pivot off its bogie's middle is taken on the track at
// its s: on an 18 m curve that is 2 cm outside the chord between the axles, where it really is.

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const len = (d) => Math.hypot(d[0], d[1], d[2]);
const unit = (d) => { const l = len(d) || 1e-9; return [d[0] / l, d[1] / l, d[2] / l]; };
// the heading (as src/consist.js: atan2(east, -north) of the forward axis) and the climb of a forward axis
const yawOf = (u) => Math.atan2(u[0], -u[1]);
const pitchOf = (u) => Math.atan2(u[2], Math.hypot(u[0], u[1]));
const axis = (yaw, pitch) => [Math.sin(yaw) * Math.cos(pitch), -Math.cos(yaw) * Math.cos(pitch), Math.sin(pitch)];
const clamp = (x, m) => (m == null ? x : Math.max(-m, Math.min(m, x)));
const TURNS = ['free', 'limited', 'fixed'];

// A type's running gear, front to rear: its bogies ({ centre, wheelbase, turn, maxAngle, sec: the section its turn is
// measured against, joint }) and what each section rests on ({ at, bogie: its index; pin: the joint, when the bogie is
// under one pin shared with the neighbour; axle: the joint, when the section rests on one axle of its bogie })
const GEAR = new WeakMap(), PLAN = new WeakMap();
export function gearOf(type) {
  if (GEAR.has(type)) return GEAR.get(type);
  const S = type.sections, J = type.joints || [], raw = [], rests = S.map(() => []);
  S.forEach((s, k) => { for (const b of s.bogies || []) rests[k].push({ at: b.at, b: raw.push({ ...b, centre: b.centre ?? b.at, sec: k }) - 1 }); });
  J.forEach((j, k) => {
    if (!j.bogie) return;
    const b = raw.push({ ...j.bogie, centre: j.at, sec: k, joint: k }) - 1;
    if (j.bogie.pivots === 'axles') {
      rests[k].push({ at: j.at - j.bogie.wheelbase / 2, b, axle: k });
      rests[k + 1].push({ at: j.at + j.bogie.wheelbase / 2, b, axle: k });
    } else for (const i of [k, k + 1]) rests[i].push({ at: j.at, b, pin: k });
  });
  const order = raw.map((_, i) => i).sort((a, b) => raw[a].centre - raw[b].centre), index = new Map(order.map((i, n) => [i, n]));
  const gear = { bogies: order.map((i) => raw[i]), rests: rests.map((r) => r.map((x) => ({ ...x, bogie: index.get(x.b) })).sort((a, b) => a.at - b.at)) };
  GEAR.set(type, gear);
  return gear;
}

const pinned = (j) => !(j.bogie && j.bogie.pivots === 'axles');
// a section that stands on its own: two supports, or one fixed or limited bogie (not a pin's: that is the neighbour's too)
const standsAlone = (g, r) => r.length === 2 || (r.length === 1 && r[0].pin === undefined && g.bogies[r[0].bogie].turn !== 'free');

// How each section is placed (placeUnit), or why it cannot be: { anchor, steps, problems }. A step is
// { k, how: 'alone' | 'steer' | 'hang' | 'axle' | 'carried' | 'back' }, in the order they run.
function plan(type) {
  if (PLAN.has(type)) return PLAN.get(type);
  const S = type.sections, J = type.joints || [], g = gearOf(type), R = g.rests, bad = [], steps = [];
  let anchor = -1;
  for (let k = 0; k < S.length && anchor < 0; k++) {
    if (standsAlone(g, R[k])) { anchor = k; steps.push({ k, how: 'alone' }); }
    else if (J[k]?.steer != null && !J[k].bogie && R[k].length === 1 && R[k + 1].length === 1) { anchor = k; steps.push({ k, how: 'steer' }); }
  }
  if (anchor < 0) {
    const p = { anchor, steps, problems: ['no section stands on its own: on two supports, on one fixed or limited bogie, or on a steered joint with its neighbour'] };
    PLAN.set(type, p);
    return p;
  }
  // behind the anchor, front to rear
  for (let k = anchor + (steps[0].how === 'steer' ? 2 : 1); k < S.length; k++) {
    const j = J[k - 1];
    if (j.steer != null) { bad.push(`joint ${k - 1}: steered, but not between the first sections that stand on it`); continue; }
    if (!pinned(j)) {
      const own = R[k].filter((x) => x.axle !== k - 1);
      if (own.length === 1) steps.push({ k, how: 'axle' });
      else bad.push(`section ${k}: on an axle of joint ${k - 1}'s bogie and ${own.length} more supports: it needs one more`);
      continue;
    }
    const far = R[k].filter((x) => x.at > j.at);
    if (far.length === 1) steps.push({ k, how: 'hang' });
    else if (far.length > 1) bad.push(`section ${k}: its pin and ${far.length} supports behind it over-constrain it (a rigid section stands on two)`);
    else if (k === S.length - 1) bad.push(`section ${k}: the last, with no support behind its pin`);
    else if (!pinned(J[k]) || J[k].steer != null) bad.push(`section ${k}: carried, but joint ${k} behind it is no plain pin`);
    else if (!standsAlone(g, R[k + 1].filter((x) => x.pin !== k))) bad.push(`section ${k}: carried, but section ${k + 1} behind it does not stand on its own supports`);
    else { steps.push({ k, how: 'carried' }); k++; }
  }
  // ahead of the anchor, rear to front: each hangs back on its pin (the 52T's end sections) or its bogie's other axle
  for (let k = anchor - 1; k >= 0; k--) {
    const j = J[k], near = R[k].filter((x) => (pinned(j) ? x.at < j.at : x.axle !== k));
    if (near.length === 1) steps.push({ k, how: 'back' });
    else bad.push(`section ${k}: ahead of the first section that stands on its own, with ${near.length} supports ahead of its ${pinned(j) ? 'pin' : 'bogie'}: it needs one`);
  }
  const p = { anchor, steps, problems: bad };
  PLAN.set(type, p);
  return p;
}

// what is wrong with a type's running gear: [] when nothing
export function gearProblems(type) {
  const S = type.sections, J = type.joints || [], bad = [];
  if (!Array.isArray(S) || !S.length) return ['no sections'];
  if (J.length !== S.length - 1) return [`${S.length} sections need ${S.length - 1} joints, it has ${J.length}`];
  S.forEach((s, k) => {
    if (!(s.from < s.to)) bad.push(`section ${k}: from ${s.from} is not ahead of to ${s.to}`);
    for (const b of s.bogies || []) if (!(b.at >= s.from && b.at <= s.to)) bad.push(`section ${k}: a bogie at ${b.at} is off it`);
  });
  J.forEach((j, k) => {
    if (!(j.at > S[k].from && j.at < S[k + 1].to)) bad.push(`joint ${k}: at ${j.at} is not between sections ${k} and ${k + 1}`);
    if (j.steer != null && (j.bogie || !(Math.abs(j.steer) <= 1))) bad.push(`joint ${k}: a steered joint needs no bogie under it and a steer between -1 and 1`);
    if (j.steerFrom !== undefined && !(j.steerFrom >= 0)) bad.push(`joint ${k}: steerFrom ${j.steerFrom} is no angle of 0 or more`);
    if (j.bogie?.pivots !== undefined && j.bogie.pivots !== 'axles') bad.push(`joint ${k}: pivots ${j.bogie.pivots} is not 'axles'`);
  });
  for (const b of gearOf(type).bogies) {
    if (!TURNS.includes(b.turn)) bad.push(`a bogie at ${b.centre}: turn ${b.turn} is none of ${TURNS.join(', ')}`);
    if (b.turn === 'limited' && !(b.maxAngle > 0)) bad.push(`a bogie at ${b.centre}: limited without maxAngle`);
    if (!(b.wheelbase > 0)) bad.push(`a bogie at ${b.centre}: no wheelbase`);
  }
  return bad.length ? bad : plan(type).problems;
}

// The s of the point at chord distance d from point K (its s estimate sK) on the track: behind it (dir -1) or ahead (+1)
function chord(at, K, sK, d, dir = -1) {
  let s = sK + dir * d;
  for (let i = 0; i < 8; i++) {
    const p = at(s), e = Math.hypot(p[0] - K[0], p[1] - K[1], p[2] - K[2]) - d;
    if (Math.abs(e) < 1e-6) break;
    s -= dir * e; // (the chord grows about as fast as the arc)
  }
  return s;
}
// the track's forward axis at s over a wheelbase
const trackAxis = (at, s, wb) => unit(sub(at(s + wb / 2), at(s - wb / 2)));

// A unit of `type` on the track (at(s) -> [x, y, height, roll]) with its front coupler face at sFront. Returns
//   sections [{ p: [x, y, z] (the middle of from..to), yaw, pitch, roll }]
//   bogies   [{ s (its middle's), yaw (against its section; a joint's: the one ahead), attack, off }], front to rear
//   joints   [{ yaw, pitch, held, over }]: the rear section against the front one; held at a limit, or over it (rad)
export function placeUnit(type, sFront, at) {
  const P = plan(type);
  if (P.problems.length) throw new Error(`running gear: ${P.problems.join('; ')}`);
  const first = gearOf(type).rests[0][0].at;
  let shift = 0, r = place(type, P, sFront, shift, at);
  // placed from a section behind its front (the 52T): moved until its first support stands where it should
  for (let i = 0; i < 3 && P.anchor > 0; i++) {
    const e = r.front - (sFront - first);
    if (Math.abs(e) < 1e-4) break;
    shift -= e;
    r = place(type, P, sFront, shift, at);
  }
  return r.pose;
}

function place(type, P, sFront, shift, at) {
  const S = type.sections, J = type.joints || [], g = gearOf(type), R = g.rests, sOf = new Map(), joints = [];
  // per section { R: a point on its axis, aR: its position along the vehicle, sR: its s estimate, u: forward axis }
  const sec = [];
  const point = (q, a) => [q.R[0] + q.u[0] * (q.aR - a), q.R[1] + q.u[1] * (q.aR - a), q.R[2] + q.u[2] * (q.aR - a)];
  const sAt = (q, a) => q.sR - (a - q.aR);
  const centreS = (x, s) => s - (g.bogies[x.bogie].centre - x.at); // (a support's bogie's middle, from the support's s)
  // a section from its first support at s1: on two, the second by its chord; on one fixed or limited bogie, the
  // track's heading at the bogie's middle
  const alone = (r, s1) => {
    const p1 = at(s1);
    sOf.set(r[0], s1);
    if (r.length === 1) return { R: p1.slice(0, 3), aR: r[0].at, sR: s1, u: trackAxis(at, centreS(r[0], s1), g.bogies[r[0].bogie].wheelbase) };
    const s2 = chord(at, p1, s1, r[1].at - r[0].at);
    sOf.set(r[1], s2);
    return { R: p1.slice(0, 3), aR: r[0].at, sR: s1, u: unit(sub(p1, at(s2))) };
  };
  // a section hanging on the point F (its s sF, at a along the vehicle) and its support x on the far side (dir)
  const hang = (F, sF, a, x, dir) => {
    const s = chord(at, F, sF, Math.abs(x.at - a), dir), p = at(s);
    sOf.set(x, s);
    return { R: F, aR: a, sR: sF, u: unit(dir < 0 ? sub(F, p) : sub(p, F)) };
  };
  // joint k's angles; the hanging section `hold` (k or k + 1) turned about the pin to the joint's limits
  const joint = (k, hold) => {
    const f = sec[k], r = sec[k + 1], j = J[k];
    const dy = wrap(yawOf(r.u) - yawOf(f.u)), dp = pitchOf(r.u) - pitchOf(f.u), cy = clamp(dy, j.yaw), cp = clamp(dp, j.pitch);
    if ((cy !== dy || cp !== dp) && hold !== undefined) {
      const other = hold === k ? r : f, sign = hold === k ? -1 : 1;
      Object.assign(sec[hold], { R: point(other, j.at), aR: j.at, sR: sAt(other, j.at), u: axis(yawOf(other.u) + sign * cy, pitchOf(other.u) + sign * cp), held: true });
      joints[k] = { yaw: cy, pitch: cp, held: true, over: 0 };
    } else joints[k] = { yaw: dy, pitch: dp, held: false, over: Math.max(Math.abs(dy - cy), Math.abs(dp - cp)) };
  };
  const s0 = (x) => sFront - x.at + shift;
  for (const { k, how } of P.steps) {
    const r = R[k];
    if (how === 'alone') { sec[k] = alone(r, s0(r[0])); continue; }
    if (how === 'steer') {
      // two sections on one bogie each, the joint's angle set by the bogies' turning; stiff in pitch, so both take the
      // pitch of the line between the pivots (the KT4: floor and roof hinges on one axis, docs/research)
      const x1 = r[0], x2 = R[k + 1][0], j = J[k], a = j.at - x1.at, b = x2.at - j.at, s1 = s0(x1), P1 = at(s1);
      const h1 = yawOf(trackAxis(at, centreS(x1, s1), g.bogies[x1.bogie].wheelbase)), wb2 = g.bogies[x2.bogie].wheelbase;
      let s2 = s1 - (a + b), th = 0, P2;
      const from = j.steerFrom || 0;
      for (let i = 0; i < 12; i++) {
        P2 = at(s2);
        const d = wrap(yawOf(trackAxis(at, centreS(x2, s2), wb2)) - h1);
        th = clamp(j.steer * Math.sign(d) * Math.max(0, Math.abs(d) - from), j.yaw);
        const e = len(sub(P1, P2)) - Math.sqrt(a * a + b * b + 2 * a * b * Math.cos(th));
        if (Math.abs(e) < 1e-6) break;
        s2 += e;
      }
      sOf.set(x1, s1);
      sOf.set(x2, s2);
      const D = sub(P1, P2), y0 = yawOf(D) - Math.atan2(b * Math.sin(th), a + b * Math.cos(th)), pt = pitchOf(D);
      sec[k] = { R: P1.slice(0, 3), aR: x1.at, sR: s1, u: axis(y0, pt) };
      sec[k + 1] = { R: point(sec[k], j.at), aR: j.at, sR: sAt(sec[k], j.at), u: axis(y0 + th, pt) };
      joint(k);
      continue;
    }
    if (how === 'hang') {
      const prev = sec[k - 1], a = J[k - 1].at, F = point(prev, a), sF = sAt(prev, a), pin = r.find((x) => x.pin === k - 1);
      if (pin) sOf.set(pin, sF);
      sec[k] = hang(F, sF, a, r.find((x) => x.at > a), -1);
      joint(k - 1, k);
      continue;
    }
    if (how === 'axle') {
      // the bogie's axles a wheelbase apart, the front one where the section ahead rests
      const front = R[k - 1].find((x) => x.axle === k - 1), rear = r.find((x) => x.axle === k - 1), sA = sOf.get(front);
      sec[k] = alone([rear, r.find((x) => x !== rear)], chord(at, at(sA), sA, rear.at - front.at));
      joint(k - 1);
      continue;
    }
    if (how === 'carried') {
      // the section behind stands on its own, its first support's s such that its front pin is this one's length from
      // this one's front pin
      const prev = sec[k - 1], a = J[k - 1].at, F = point(prev, a), sF = sAt(prev, a), a2 = J[k].at, L = a2 - a;
      const next = R[k + 1].filter((x) => x.pin !== k);
      let s1 = sF - (next[0].at - a), q;
      for (let i = 0; i < 12; i++) {
        q = alone(next, s1);
        const e = len(sub(F, point(q, a2))) - L;
        if (Math.abs(e) < 1e-6) break;
        s1 += e;
      }
      sec[k + 1] = q;
      sec[k] = { R: F, aR: a, sR: sF, u: unit(sub(F, point(q, a2))) };
      joint(k - 1);
      joint(k);
      continue;
    }
    // 'back': hanging on the section behind it, from its pin or its bogie's rear axle to its one support ahead
    const next = sec[k + 1], j = J[k];
    if (pinned(j)) {
      sec[k] = hang(point(next, j.at), sAt(next, j.at), j.at, r.filter((x) => x.at < j.at).pop(), 1);
      joint(k, k);
    } else {
      const rear = R[k + 1].find((x) => x.axle === k), front = r.find((x) => x.axle === k), sB = sOf.get(rear);
      const s1 = chord(at, at(sB), sB, rear.at - front.at, 1);
      sOf.set(front, s1);
      sec[k] = hang(at(s1).slice(0, 3), s1, front.at, r.find((x) => x !== front), 1);
      joint(k);
    }
  }
  const sOfRest = (x, k) => sOf.get(x) ?? sAt(sec[k], x.at);
  const bogies = g.bogies.map((b, i) => {
    const rs = [];
    R.forEach((r, k) => r.forEach((x) => { if (x.bogie === i) rs.push([x, k]); }));
    const s = b.joint !== undefined && !pinned(J[b.joint]) ? (sOfRest(...rs[0]) + sOfRest(...rs[1])) / 2 : centreS(rs[0][0], sOfRest(...rs[0]));
    const rel = wrap(yawOf(trackAxis(at, s, b.wheelbase)) - yawOf(sec[b.sec].u));
    const yaw = b.turn === 'fixed' ? 0 : b.turn === 'limited' ? clamp(rel, b.maxAngle) : rel;
    // a held section's pivot against the track's point at its s
    let off = 0;
    for (const [x, k] of rs) {
      if (!sec[k].held) continue;
      const p = point(sec[k], x.at), c = at(sOfRest(x, k));
      off = Math.max(off, Math.hypot(p[0] - c[0], p[1] - c[1]));
    }
    return { s, yaw, attack: rel - yaw, off };
  });
  const sections = sec.map((q, k) => {
    const mid = (S[k].from + S[k].to) / 2, rs = R[k];
    const roll = rs.length ? rs.reduce((t, x) => t + (at(sOfRest(x, k))[3] || 0), 0) / rs.length : at(sAt(q, mid))[3] || 0;
    return { p: point(q, mid), yaw: yawOf(q.u), pitch: pitchOf(q.u), roll };
  });
  return { front: sOfRest(R[0][0], 0), pose: { sections, bogies, joints } };
}

// where each section of a placed unit rests, in route coordinates (for the checks): [[{ at, p, s }]] per section
export function restPoints(type, pose) {
  const S = type.sections, R = gearOf(type).rests;
  return R.map((r, k) => {
    const q = pose.sections[k], m = (S[k].from + S[k].to) / 2, u = axis(q.yaw, q.pitch);
    return r.map((x) => ({ at: x.at, p: [q.p[0] + u[0] * (m - x.at), q.p[1] + u[1] * (m - x.at), q.p[2] + u[2] * (m - x.at)] }));
  });
}
