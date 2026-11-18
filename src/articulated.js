// SPDX-License-Identifier: AGPL-3.0-or-later
// A vehicle's running gear as data, and its pose on the track from it (#579): rigid sections in a row, each on its own
// bogies or carried by its neighbours through joints. A type (src/tram.js VEHICLE_TYPES, later a package's manifest) has
//   sections  [{ from, to, bogies: [{ at, turn, maxAngle, wheelbase }] }], front to rear: the body's extent, its bogies
//   joints    [{ at, yaw, pitch, bogie }]: joint k joins sections k and k + 1 at one pin; yaw and pitch are its freedom
//             (a largest angle in rad, or null: free); bogie is a bogie carrying the joint ({ turn, maxAngle, wheelbase }:
//             a Jacobs bogie), or none
// Positions are along the vehicle in m from its front coupler face, on straight track. A bogie turns 'free' (a pivot),
// 'limited' (springs or stops: to maxAngle against its section) or 'fixed' (not at all: a section on it alone takes the
// track's heading there). The user, 2026-11-13 (PR #577): "The sections are usually coupled freely but it can be pivoted
// at different places, and some bogies can have smaller freedom of movement or be completely fixed relative to the
// chassis."
//
// placeUnit() puts a unit on the track from the front, each section from what is placed ahead of it:
// - the first section stands on its two supports (bogies, or a bogie and the one under its rear joint), or on one
//   fixed bogie with the track's heading there;
// - a section behind a pin hangs on it: the line from the pin (or the bogie under it) to its one support behind;
// - a section with no support behind its pin is carried by its two joints: placed with the section behind it, which
//   stands on its own supports, solved so that the two joints are the carried section's length apart.
// Each support stands on the track at its own s, found from the point ahead of it by their distance in a straight line
// (the chord of a curve, shorter than the arc). A joint past its yaw or pitch freedom holds the section behind it at the
// limit, turned about the pin; that section's bogies then stand off the track, by `off` m: the flanges' work. A bogie
// past its own freedom (limited, fixed) keeps its section's line and logs its angle of attack beyond it (`attack`, rad).

const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const len = (d) => Math.hypot(d[0], d[1], d[2]);
const unit = (d) => { const l = len(d) || 1e-9; return [d[0] / l, d[1] / l, d[2] / l]; };
// the heading (as src/consist.js: atan2(east, -north) of the forward axis) and the climb of a forward axis
const yawOf = (u) => Math.atan2(u[0], -u[1]);
const pitchOf = (u) => Math.atan2(u[2], Math.hypot(u[0], u[1]));
const axis = (yaw, pitch) => [Math.sin(yaw) * Math.cos(pitch), -Math.cos(yaw) * Math.cos(pitch), Math.sin(pitch)];
const clamp = (x, m) => (m == null ? x : Math.max(-m, Math.min(m, x)));

// every bogie of a type, front to rear: a section's own ({ sec }) and those under joints ({ joint, sec: the one ahead })
export function bogiesOf(type) {
  const out = [];
  type.sections.forEach((S, k) => { for (const b of S.bogies || []) out.push({ ...b, sec: k }); });
  (type.joints || []).forEach((j, k) => { if (j.bogie) out.push({ ...j.bogie, at: j.at, joint: k, sec: k }); });
  return out.sort((a, b) => a.at - b.at);
}
// what a section stands on behind its front pin: its own bogies and the bogie under its rear joint
const behindPin = (all, k) => all.filter((b) => (b.joint === undefined && b.sec === k) || b.joint === k);
// a section that stands on its own supports: two, or one fixed bogie
const standsAlone = (own) => own.length === 2 || (own.length === 1 && own[0].turn === 'fixed');

// what is wrong with a type's running gear: [] when nothing
export function gearProblems(type) {
  const S = type.sections, J = type.joints || [], bad = [];
  if (!Array.isArray(S) || !S.length) return ['no sections'];
  if (J.length !== S.length - 1) return [`${S.length} sections need ${S.length - 1} joints, it has ${J.length}`];
  S.forEach((s, k) => {
    if (!(s.from < s.to)) bad.push(`section ${k}: from ${s.from} is not ahead of to ${s.to}`);
    for (const b of s.bogies || []) if (!(b.at >= s.from && b.at <= s.to)) bad.push(`section ${k}: a bogie at ${b.at} is off it`);
  });
  J.forEach((j, k) => { if (!(j.at > S[k].from && j.at < S[k + 1].to)) bad.push(`joint ${k}: at ${j.at} is not between sections ${k} and ${k + 1}`); });
  const all = bogiesOf(type);
  for (const b of all) {
    if (!['free', 'limited', 'fixed'].includes(b.turn)) bad.push(`a bogie at ${b.at}: turn ${b.turn} is none of free, limited, fixed`);
    if (b.turn === 'limited' && !(b.maxAngle > 0)) bad.push(`a bogie at ${b.at}: limited without maxAngle`);
    if (!(b.wheelbase > 0)) bad.push(`a bogie at ${b.at}: no wheelbase`);
  }
  if (bad.length) return bad;
  // placed from the front, each section needs its line from what is ahead of it, and no more than that
  let alone = true; // (the first section, and one behind a carried section, stand on their own)
  S.forEach((s, k) => {
    const own = behindPin(all, k);
    if (alone) {
      if (!standsAlone(own)) bad.push(`section ${k}: stands on ${own.length} supports${own.length === 1 ? ', turning' : ''}: it needs two, or one fixed bogie`);
      alone = false;
    } else if (!own.length) {
      if (k === S.length - 1) bad.push(`section ${k}: the last, with no support behind its pin`);
      alone = true; // (carried by its joints: the next one stands on its own)
    } else if (own.length > 1) bad.push(`section ${k}: its pin and ${own.length} supports behind it over-constrain it (a rigid section stands on two)`);
  });
  return bad;
}

// The point at chord distance d behind point K (its s estimate sK) on the track: its s
function behind(at, K, sK, d) {
  let s = sK - d;
  for (let i = 0; i < 8; i++) {
    const p = at(s), e = Math.hypot(p[0] - K[0], p[1] - K[1], p[2] - K[2]) - d;
    if (Math.abs(e) < 1e-6) break;
    s += e; // (the chord grows about as fast as the arc behind K)
  }
  return s;
}
// the track's forward axis at s over a bogie's wheelbase
const trackAxis = (at, s, wb) => unit(sub(at(s + wb / 2), at(s - wb / 2)));

// A unit of `type` on the track (at(s) -> [x, y, height, roll]) with its front coupler face at sFront. Returns
//   sections [{ p: [x, y, z] (the middle of from..to), yaw, pitch, roll }]
//   bogies   [{ s, yaw (against its section; a joint's: against the section ahead), attack, off }], front to rear
//   joints   [{ yaw, pitch, held, over }]: the rear section against the front one; held at a limit, or over it (rad)
export function placeUnit(type, sFront, at) {
  const S = type.sections, J = type.joints || [], all = bogiesOf(type), sOf = new Map(), joints = [];
  // per section { R: a point on its axis, aR: its position along the vehicle, sR: its s estimate, u: forward axis }
  const sec = [];
  const point = (q, a) => [q.R[0] + q.u[0] * (q.aR - a), q.R[1] + q.u[1] * (q.aR - a), q.R[2] + q.u[2] * (q.aR - a)];
  const sAt = (q, a) => q.sR - (a - q.aR);
  const standAlone = (own, s1) => {
    const p1 = at(s1);
    sOf.set(own[0], s1);
    if (own.length === 1) return { R: p1.slice(0, 3), aR: own[0].at, sR: s1, u: trackAxis(at, s1, own[0].wheelbase) };
    const s2 = behind(at, p1, s1, own[1].at - own[0].at);
    sOf.set(own[1], s2);
    return { R: p1.slice(0, 3), aR: own[0].at, sR: s1, u: unit(sub(p1, at(s2))) };
  };
  // joint k between placed sections: its angles, the rear one held at a limit when `hold` (turned about the pin)
  const joint = (k, hold) => {
    const f = sec[k], r = sec[k + 1], j = J[k];
    const dy = wrap(yawOf(r.u) - yawOf(f.u)), dp = pitchOf(r.u) - pitchOf(f.u), cy = clamp(dy, j.yaw), cp = clamp(dp, j.pitch);
    const past = cy !== dy || cp !== dp;
    if (past && hold) Object.assign(r, { R: point(f, j.at), aR: j.at, sR: sAt(f, j.at), u: axis(yawOf(f.u) + cy, pitchOf(f.u) + cp), held: true });
    joints[k] = past && hold ? { yaw: cy, pitch: cp, held: true, over: 0 } : { yaw: dy, pitch: dp, held: false, over: Math.max(Math.abs(dy - cy), Math.abs(dp - cp)) };
  };
  for (let k = 0; k < S.length; k++) {
    if (sec[k]) continue; // (placed with the carried section ahead of it)
    const own = behindPin(all, k);
    if (k === 0) { sec[0] = standAlone(own, sFront - own[0].at); continue; }
    const prev = sec[k - 1], a = J[k - 1].at, F = point(prev, a), sF = sAt(prev, a);
    if (J[k - 1].bogie) sOf.set(all.find((b) => b.joint === k - 1), sF);
    if (own.length) {
      const s2 = behind(at, F, sF, own[0].at - a);
      sOf.set(own[0], s2);
      sec[k] = { R: F, aR: a, sR: sF, u: unit(sub(F, at(s2))) };
      joint(k - 1, true);
      continue;
    }
    // carried: the section behind stands on its own, its first support's s such that its front pin is this one's
    // length from this one's front pin
    const next = behindPin(all, k + 1), a2 = J[k].at, L = a2 - a;
    let s1 = sF - (next[0].at - a), q;
    for (let i = 0; i < 12; i++) {
      q = standAlone(next, s1);
      const e = len(sub(F, point(q, a2))) - L;
      if (Math.abs(e) < 1e-6) break;
      s1 += e;
    }
    sec[k + 1] = q;
    sec[k] = { R: F, aR: a, sR: sF, u: unit(sub(F, point(q, a2))) };
    joint(k - 1, false);
    joint(k, false);
  }
  const bogies = all.map((b) => {
    const q = sec[b.sec], s = sOf.get(b) ?? sAt(q, b.at), rel = wrap(yawOf(trackAxis(at, s, b.wheelbase)) - yawOf(q.u));
    const yaw = b.turn === 'fixed' ? 0 : b.turn === 'limited' ? clamp(rel, b.maxAngle) : rel;
    // a held section's pivot against the track's point at its s
    const p = point(q, b.at), c = at(s), off = q.held ? Math.hypot(p[0] - c[0], p[1] - c[1]) : 0;
    return { s, yaw, attack: rel - yaw, off };
  });
  const sections = sec.map((q, k) => {
    const mid = (S[k].from + S[k].to) / 2, mine = all.filter((b) => b.sec === k);
    const roll = mine.length ? mine.reduce((x, b) => x + (at(sOf.get(b) ?? sAt(q, b.at))[3] || 0), 0) / mine.length : at(sAt(q, mid))[3] || 0;
    return { p: point(q, mid), yaw: yawOf(q.u), pitch: pitchOf(q.u), roll };
  });
  return { sections, bogies, joints };
}
