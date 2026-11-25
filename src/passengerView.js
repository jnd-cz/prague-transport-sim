// SPDX-License-Identifier: AGPL-3.0-or-later
// Our set's passengers drawn (#249 step 3): the people of the passenger core (src/passengers/consist.js) as records for
// the figures (src/people.js), drawing only: it reads the core and writes nothing back, so a seeded run counts the same
// with or without it. The detailed model only (the rigged hybrid T3, whose cabin the core's is: assets/passengers/).
//
// The frames (the user's rules for #249, 2026-11-25): a passenger on the car (its floor or its entry steps) is drawn in the
// car's own frame, a child of its model's node, so they sway, pitch and lean with the body and are hidden with it (the cab
// view) and shown with it (the mirror, the outside views); one on the platform is drawn in the world, on the car's frame
// without its lean (the platform does not lean with the body). The switch is at the platform's edge. The counted passengers
// (above the 105 places) are drawn only on the steps and outside. A boarder first seen at the queue walks there from one of
// the stop crowd's places (src/gameView.js crowdSpots), which then stays empty; one who alighted walks on off the platform
// a little longer and goes.
import * as THREE from 'three';

const EASE = 1.3; // m/s: from the crowd's place to the queue (only drawn: the core has them queued already)
const LEAVE = 3; // s an alighter walks on after the core lets them go
const SHIRTS = [0x8b2f2f, 0x2f4f8b, 0x3c6b3c, 0x666666, 0xc29a3a, 0x222222, 0x8a5a9a, 0xd0d0d0, 0x2a5c63, 0xa8523a]; // (the stop crowd's, src/models.js)
const TURN_BACK = new THREE.Matrix4().makeRotationY(Math.PI / 2); // (src/people.js multiplies a record's matrix by its TURN)
const UP = new THREE.Vector3(0, 1, 0);

export class PassengerView {
  constructor() {
    this.game = null;
    this.seen = new Map(); // actor id -> { spot, off: Vector3 (world), walked, last world position, heading }
    this.ghosts = new Map(); // actor id -> an alighter walking off: { p, dir, n, shirt, t, walked }
    this.used = new Map(); // stop -> Set of the crowd places taken by boarders
    this.recs = [];
    this._m = new THREE.Matrix4(); this._q = new THREE.Quaternion(); this._p = new THREE.Vector3(); this._s = new THREE.Vector3();
    this._ex = new THREE.Vector3(); this._ey = new THREE.Vector3(); this._ez = new THREE.Vector3(); this._o = new THREE.Vector3();
  }

  // the crowd places taken at a stop (src/gameView.js hides them)
  usedAt(stop) { return this.used.get(stop) || null; }

  // the records of our set's passengers for this frame (src/people.js sync's): { recs, cars: the car nodes }; model: our
  // set's model, posed for this frame; gameView: its crowd's places
  sync(game, model, gameView) {
    const recs = this.recs;
    recs.length = 0;
    if (game !== this.game) { this.game = game; this.seen.clear(); this.ghosts.clear(); this.used.clear(); }
    const cars = model?.userData?.rigged ? model.userData.cars.map((c) => c.userData.rig.full) : [];
    if (!game?.pax || !cars.length || cars.length !== game.pax.cars.length) return { recs, cars: [] };
    model.updateMatrixWorld(true);
    const t = game.clock, shown = model.visible, st = game.stops[game.nextStop];
    const fit = game.pax.cars[0].c.layout.fitProfile.scale, edge = game.pax.cars[0].c.layout.doors[0].platformEdgeZ ?? 1.33;
    const alive = new Set();
    game.pax.cars.forEach((car, k) => {
      const node = cars[k], level = this._level(node);
      for (const a of car.c.actors.values()) {
        // (the counted ones are drawn on the steps and outside only)
        if (a.counted && a.aboard && !a.legPose) continue;
        alive.add(a.id);
        const on = a.z < edge || !!a.legPose;
        let s = this.seen.get(a.id);
        if (!s) { s = { spot: null, off: null, walked: 0, last: null, n: null, shirt: null }; this.seen.set(a.id, s); }
        const r = { key: a.id, parent: null, local: null, m: new THREE.Matrix4(), x: 0, y: 0, z: 0, shirt: null, n: 0, shown: true, pax: null };
        // the car-local pose (the figure faces +X, as the cabin's frame; scaled to the cabin's fit, as the lab drew them)
        this._q.setFromAxisAngle(UP, a.heading ?? 0);
        const local = new THREE.Matrix4().compose(this._p.set(a.x, a.y, a.z), this._q, this._s.set(fit.x, fit.y, fit.z));
        let motion = a.motion || 'Idle', heading = null, extra = 0;
        if (on) {
          r.parent = node; r.local = local; r.shown = shown;
          r.m.multiplyMatrices(node.matrixWorld, local).multiply(TURN_BACK);
          s.off = null;
        } else {
          // on the platform: the car's frame without its lean; a boarder new at the queue walks from a crowd place
          const p = this._onLevel(level, a.x, a.y, a.z, this._o);
          if (!s.last && a.tag === st?.i && !a.runner && !a.aboard) this._fromSpot(s, st, gameView, p);
          if (s.off) {
            const d = s.off.length(), step = Math.min(d, EASE * Math.max(0, t - (s.t ?? t)));
            if (d - step < 0.05) s.off = null;
            else {
              s.off.multiplyScalar((d - step) / d);
              extra = step;
              p.add(s.off);
              heading = Math.atan2(s.off.z, -s.off.x); // (walking towards the queue: against the offset)
              motion = 'Walk';
            }
          }
          const yaw = heading ?? level.yaw + (a.heading ?? 0); // (the world's, as an object's rotation about the up)
          this._q.setFromAxisAngle(UP, yaw);
          r.m.compose(p, this._q, this._s.set(fit.x, fit.y, fit.z)).multiply(TURN_BACK);
          s.lastOut = { p: p.clone(), yaw, egress: a.outsideAt != null };
        }
        s.walked += extra;
        s.t = t;
        s.last = true;
        if (a.aboard) s.boarded = true;
        if (s.n === null) {
          s.n = s.spot ? s.spot.n : (Math.imul(k + 1, 0x9e3779b1) ^ Math.imul(a.index, 0x85ebca6b)) >>> 0;
          s.shirt = s.spot ? s.spot.shirt : new THREE.Color(SHIRTS[s.n % SHIRTS.length]);
        }
        r.n = s.n; r.shirt = s.shirt;
        const e = r.m.elements;
        r.x = e[12]; r.y = e[13]; r.z = e[14];
        const phase = motion === 'Walk' ? ((a.distanceMetres ?? 0) + s.walked) / ((16 / 15) * fit.x) : motion === 'Idle' ? t * 0.25 + (s.n % 97) * 0.13
          : motion === 'Sit' ? 0 : a.animationPhase ?? 0;
        r.pax = { motion, phase, blend: a.poseBlend ?? null, legPose: on ? a.legPose ?? null : null, seated: motion === 'Sit' && !a.poseBlend, car: k };
        recs.push(r);
      }
    });
    // alighters the core let go: on a little further off the platform, then gone
    for (const [id, s] of this.seen) {
      if (alive.has(id)) continue;
      if (s.lastOut?.egress && !this.ghosts.has(id)) this.ghosts.set(id, { p: s.lastOut.p, yaw: s.lastOut.yaw, n: s.n, shirt: s.shirt, t0: t, t, walked: s.walked });
      // (a boarder the doors closed on, or for whom there was no room: back to their place in the crowd)
      else if (s.spot && !s.boarded) this.used.get(s.spot.stop)?.delete(s.spot.i);
      this.seen.delete(id);
    }
    for (const [id, g] of this.ghosts) {
      if (t - g.t0 > LEAVE || t < g.t0) { this.ghosts.delete(id); continue; }
      const step = 1.2 * Math.max(0, t - g.t);
      g.t = t; g.walked += step;
      g.p.x += Math.cos(g.yaw) * step; g.p.z -= Math.sin(g.yaw) * step;
      this._q.setFromAxisAngle(UP, g.yaw);
      const r = { key: id, parent: null, local: null, m: new THREE.Matrix4().compose(g.p, this._q, this._s.set(fit.x, fit.y, fit.z)).multiply(TURN_BACK),
        x: g.p.x, y: g.p.y, z: g.p.z, shirt: g.shirt, n: g.n, shown: true,
        pax: { motion: 'Walk', phase: g.walked / ((16 / 15) * fit.x), blend: null, legPose: null, seated: false, car: -1 } };
      recs.push(r);
    }
    return { recs, cars };
  }

  // a car's frame without its lean: its origin, its forward (+X) and right (+Z) level with the world's up, the up
  _level(node) {
    const e = node.matrixWorld.elements, L = node.userData.paxLevel || (node.userData.paxLevel = { o: new THREE.Vector3(), x: new THREE.Vector3(), y: new THREE.Vector3(), z: new THREE.Vector3(), yaw: 0 });
    L.o.set(e[12], e[13], e[14]);
    L.x.set(e[0], e[1], e[2]).normalize();
    L.z.crossVectors(L.x, UP).normalize(); // (forward x up: the right, level)
    if (L.z.dot(this._ez.set(e[8], e[9], e[10])) < 0) L.z.negate();
    L.y.crossVectors(L.z, L.x).normalize(); // (up along the car's pitch)
    L.yaw = Math.atan2(-L.x.z, L.x.x);
    return L;
  }

  _onLevel(L, x, y, z, out) {
    return out.copy(L.o).addScaledVector(L.x, x).addScaledVector(L.y, y).addScaledVector(L.z, z);
  }

  // the nearest crowd place of the stop not yet taken: the boarder walks from there (its offset from p, in the world)
  _fromSpot(s, st, gameView, p) {
    const spots = gameView?.crowdSpots?.(st);
    if (!spots?.length) return;
    let used = this.used.get(st);
    if (!used) { used = new Set(); this.used.set(st, used); }
    let best = -1, bd = Infinity;
    for (let i = 0; i < spots.length; i++) {
      if (used.has(i)) continue;
      const d = (spots[i].x - p.x) ** 2 + (spots[i].z - p.z) ** 2;
      if (d < bd) { bd = d; best = i; }
    }
    if (best < 0) return;
    used.add(best);
    const q = spots[best];
    s.spot = { ...q, stop: st, i: best };
    s.off = new THREE.Vector3(q.x - p.x, q.y - p.y, q.z - p.z);
    s.t = this.game.clock;
  }
}
