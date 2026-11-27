// SPDX-License-Identifier: AGPL-3.0-or-later
// What the game's steps move, drawn between the last two steps (#722). The page steps the game at a fixed 1/30 s
// (src/main.js fixedSteps) and draws our tram between its place before the last step and after it (drawnS); the
// cars, the other trams and the game's own movers are drawn the same way here, so that at 60 frames a second they
// glide beside our tram instead of standing still every other frame (maintainer, PR #809).
// After a step the page draws from, their poses are recorded; before a draw each is put between
// its last two; after the draw it is put back where the step left it, so a drawn pose never outlives its draw: the
// traffic's steps read none of these (src/traffic.js keeps its own poses, #228), and the game's movers are posed by
// its steps, which may read them back (src/game.js until #228's second half). A run stays the same at any frame rate
// (tools/test_frame_rate.py). openOMSI draws its
// traffic the same way (crates/omsi-sim/src/ai_traffic/fixed_step.rs, show_between / show_actual).
import * as THREE from 'three';

// further than this in one step, it was put there (appeared, a car reused, a tram recovered): drawn where it is, not
// swept there (our tram's drawnS: the same 5 m; a car at 50 km/h goes 0.46 m a step)
const JUMP = 5;
const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), ea = new THREE.Euler(), eb = new THREE.Euler();

// an object's pose: its position and its rotation's angles (the steps set the angles: src/consist.js poseSection,
// src/trafficView.js _car), so that putting them back gives the very quaternion the step left
function write(o, a) {
  a[0] = o.position.x; a[1] = o.position.y; a[2] = o.position.z;
  a[3] = o.rotation.x; a[4] = o.rotation.y; a[5] = o.rotation.z;
}
const same = (a, b) => a[0] === b[0] && a[1] === b[1] && a[2] === b[2] && a[3] === b[3] && a[4] === b[4] && a[5] === b[5];

export class Between {
  constructor() {
    this.poses = new Map(); // object -> { was, now: poses before and after the last step, at: the record it was in }
    this.n = 0; // records so far
    this.shown = []; // what show() moved, for back()
  }

  clear() {
    this.back();
    this.poses.clear();
    this.n = 0;
  }

  // after a step the page draws from: where each of `objs` stands now, and where it stood after the step before
  // (one not recorded then is drawn where it is); one not among `objs` is forgotten
  record(objs) {
    const n = ++this.n;
    for (const o of objs) {
      let e = this.poses.get(o);
      if (!e) { e = { was: new Float64Array(6), now: new Float64Array(6), at: 0, ok: false }; this.poses.set(o, e); }
      const t = e.was;
      e.was = e.now;
      e.now = t;
      write(o, e.now);
      const a = e.was, b = e.now;
      e.ok = e.at === n - 1 && Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) <= JUMP;
      e.at = n;
    }
    for (const [o, e] of this.poses) if (e.at !== n) this.poses.delete(o);
  }

  // a step that moved none of them (paused, the shift over): each stands where it stood
  hold() {
    const n = ++this.n;
    for (const e of this.poses.values()) { e.was.set(e.now); e.at = n; }
  }

  // draw them at u between the last two steps (0: where the last step found them, 1: where it left them)
  show(u) {
    this.back();
    if (!(u < 1)) return;
    for (const [o, e] of this.poses) {
      const a = e.was, b = e.now;
      if (!e.ok || same(a, b)) continue;
      o.position.set(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u);
      ea.set(a[3], a[4], a[5], o.rotation.order);
      eb.set(b[3], b[4], b[5], o.rotation.order);
      o.quaternion.slerpQuaternions(qa.setFromEuler(ea), qb.setFromEuler(eb), u);
      this.shown.push(o);
    }
  }

  // each back where the last step left it, before anything reads it or steps again
  back() {
    for (const o of this.shown) {
      const b = this.poses.get(o).now;
      o.position.set(b[0], b[1], b[2]);
      o.rotation.set(b[3], b[4], b[5]);
    }
    this.shown.length = 0;
  }
}
