// A tram's longitudinal dynamics: the body (mass, length, capacity) and the forces on it (gravity,
// running and curve resistance, adhesion, sand), with the traction equipment as its own part (#221):
// `tram.eq` turns the driver's controls into tractive and brake forces and the line current. The T3SUCS
// has the ČKD TR 37 (src/tr37.js); another model would bring its body table and its equipment class.

import { TR37 } from './tr37.js';

const G = 9.81;

// the Tatra T3's body (per car)
export const T3 = {
  length: 15.2,              // over couplers (body 14.0 m), DPP training manual
  emptyMass: 16000,          // kg
  rotMass: 2400,             // kg: motors, gears and wheels turning, ≈15 % of the empty car (t3-accelerator.md § 5.3)
  paxMass: 72,               // kg / passenger
  capacity: 110,             // 24 seated + 86 standing (crush load 160)
  crushCapacity: 160,
  vMax: 65 / 3.6,            // empty, on the level ([ckd03] p. 4)
  lineVoltage: 600,
};

// Wheel/rail adhesion (peak, at a standstill) by weather, from docs/research/rail-adhesion.md (#266):
// dry 0.30 (Moore 0.25–0.30; tram rig 0.4), steady rain on rinsed rail 0.18 (BR 0.2, Moore 0.18–0.20),
// autumn rail between the leaf patches 0.22 (estimate: leaves act through the patches, game.js 0.06),
// light snow 0.10 (Moore). game.js: leaf patches and the icy pedestrian crossings.
export const ADHESION = { dry: 0.30, rain: 0.18, leaves: 0.22, snow: 0.10 };

// Adhesion falls with speed: Curtius–Kniffler, μ = 0.161 + 7.5 / (v + 44) with v in km/h, as a factor of
// its standstill value: 1.00 at 0, 0.75 at 40, 0.70 at 60 km/h (#266)
export const muSpeed = (v) => (0.161 + 7.5 / (Math.abs(v) * 3.6 + 44)) / 0.3315;

// Sand by the rail's state (#266): no gain on dry rail (the lab even measured a loss), about +0.04 on wet
// rail and +0.05 on snow (Moore), and on a leaf patch two to three times its grip (field braking 1.5 → 4.5 %g).
// The patch is told by its value (game.js: 0.06; nothing else is that low)
export const sandedMu = (mu) => (mu < 0.07 ? mu * 2.5 : mu < 0.27 ? Math.min(0.27, mu + 0.045) : mu);

// The creep curve, lumped over the axles: the force rises to its peak at CREEP_PEAK and falls towards
// SPIN_LEFT of it when the wheels spin or lock (dry ≈ 40–50 % of peak, wet nearly flat: #266, Polach);
// creep is the wheels' speed against the tram's over the tram's speed (at least 1.5 m/s: from a stand)
const CREEP_PEAK = 0.03, CREEP_FALL = 0.15, SPIN_LEFT = { dry: 0.5, rain: 0.85, leaves: 0.5, snow: 0.6 };

// Axles from the front of each car (bogie centres 6.36 m apart, axle base 1.9 m, coupler 0.6 m); the T3SUCS
// sands in front of the first axle, both wheels (DPP 2009 training textbook, #266)
const AXLES = [3.47, 5.37, 9.83, 11.73];
// sand on the rail helps the axles that follow, ours and the second car's; how far is not measured: the
// sand laid stays for SAND_LIFE s. The boxes: ≈ 5 min of sanding per filling (2 × 17–24 kg at 3–6 kg/min
// per bogie, the user's figures, #266), filled at the terminus: a run starts full
const SAND_LIFE = 60, SAND_TIME = 300;

// Prague ran the T3 mostly as two-car multiple-unit sets (both cars motored, one driver).
// Everything that scales with the cars lives here.
export const COUPLING_GAP = 0;     // cars are 15.2 m over couplers, coupled buffer to buffer
export const PANTO_FROM_FRONT = 4.5; // the (first car's) pantograph, which works the overhead contacts
                                     // (coupler 0.6 m + half body 7.0 m - 3.1 m ahead of the centre)

export class Tram {
  constructor(cars = 1) {
    this.cars = cars;
    this.eq = new TR37(cars);
    this.s = 0;            // front position along route (m)
    this.v = 0;            // m/s, negative when rolling back
    this.a = 0;            // m/s2
    this.drive = 0;        // tractive force at the rail (N)
    this.brake = 0;        // wheel brake force (N)
    this.passengers = 0;
    this.current = 0;      // A, the ammeter (a car's; negative braking)
    this.electric = 0;     // W drawn from the line (+) or burnt in the brake resistors (−)
    this.voltage = T3.lineVoltage;
    this.trackBrake = false;
    this.sanding = false;
    this.sand = 1;         // sand box level 0..1
    this.slip = false;     // wheels spinning under traction
    this.slide = false;    // wheels locked under braking
    this.slideTime = 0;
    this.vw = 0;           // the wheels' rim speed (m/s): the tram's own while they grip
    this.slipping = false; // the wheels turn on their own (spinning or sliding)
    this.sandTrail = [];   // [from, to, time laid]: sand on the rail, route s
    this.jerk = 0;
    this.forcedStop = false;
    this.grade = 0;
    this.mu = ADHESION.dry;
  }

  get mass() { return T3.emptyMass * this.cars + this.passengers * T3.paxMass; }
  get inertia() { return this.mass + T3.rotMass * this.cars; } // what the forces accelerate
  get length() { return T3.length * this.cars + COUPLING_GAP * (this.cars - 1); }
  get capacity() { return T3.capacity * this.cars; }
  get crushCapacity() { return T3.crushCapacity * this.cars; }
  get panto() { return this.s - PANTO_FROM_FRONT; }
  get kmh() { return this.v * 3.6; }
  get notch() { return this.eq.notch; }
  // net applied force for gauges and sounds; drawing: traction current through the pantograph
  get force() { return this.drive - this.brake; }
  set force(f) { this.drive = Math.max(0, f); this.brake = Math.max(0, -f); this.eq.drive = this.drive; }
  get drawing() { return this.eq.drawing && this.drive > 500; }

  // the peak adhesion coefficient over the axles: each axle's rail (muAt: leaf patches, ice), sand under
  // the first axle while sanding and under the following ones where sand was laid, then the speed's fall
  peakMu(muAt, weather) {
    const now = this.time || 0;
    let sum = 0, n = 0;
    for (let c = 0; c < this.cars; c++) {
      for (let i = 0; i < AXLES.length; i++) {
        const s = this.s - c * (T3.length + COUPLING_GAP) - AXLES[i];
        let mu = muAt(s);
        const sanded = (c === 0 && i === 0 && this.sanding) || this.sandTrail.some(([a, b, t]) => s >= a && s <= b && now - t < SAND_LIFE);
        if (sanded) mu = sandedMu(mu);
        sum += mu; n++;
      }
    }
    this.spinLeft = SPIN_LEFT[weather] ?? 0.5;
    return (sum / n) * muSpeed(this.v);
  }

  update(dt, { deadmanTrip = false, grade = 0, radius = 1e6, mu = ADHESION.dry, weather = 'dry', sandKey = false, doorsOpen = false } = {}) {
    const m = this.mass, k = this.cars, speed = Math.abs(this.v);
    this.grade = grade;
    this.time = (this.time || 0) + dt; // (simulation time: the same drive gives the same result)
    // the motors turn with the wheels: spinning, their current falls (the ammeter dips); locked, the
    // electric brake fades
    const out = this.eq.update(dt, { v: this.slipping ? this.vw : this.v, voltage: this.voltage, doorsOpen, rescue: deadmanTrip, forcedStop: this.forcedStop });

    // sand: driver key, or automatically with the track brakes; laid in front of the first axle
    this.sanding = (sandKey || (out.trackOn && speed > 0.3)) && this.sand > 0;
    if (this.sanding) {
      this.sand = Math.max(0, this.sand - dt / SAND_TIME);
      const s1 = this.s - AXLES[0] + 0.5, last = this.sandTrail[this.sandTrail.length - 1];
      if (last && this.time - last[2] < 0.5 && Math.abs(s1 - last[1]) < 2 + speed * dt) { last[1] = Math.max(last[1], s1); last[0] = Math.min(last[0], s1); last[2] = this.time; }
      else this.sandTrail.push([s1, s1, this.time]);
    }
    this.sandTrail = this.sandTrail.filter((x) => this.time - x[2] < SAND_LIFE);
    const muAt = typeof mu === 'function' ? mu : () => mu;
    this.mu = this.peakMu(muAt, weather);
    const N = m * G; // all axles are motored and braked

    this.drive = out.drive; this.brake = out.brake;
    const fD = this.drive, fB = this.brake;
    this.trackBrake = out.trackOn && speed > 0.3;
    const fTrack = this.trackBrake ? out.track : 0; // (the magnets: no adhesion limit)

    this.electric = out.line > 0 ? this.voltage * out.line : -out.dissipated;
    this.voltage = T3.lineVoltage + 18 * Math.sin((this.time * 1000) / 2300) - out.line * 0.045;
    this.current = this.forcedStop ? 0 : out.current;

    if (this.forcedStop) {
      // held (collision, crowbar...): it can't roll away when released
      this.v = 0; this.vw = 0; this.a = 0; this.drive = 0; this.slipping = this.slip = this.slide = false;
      return;
    }

    // external forces
    const fGrav = (-m * G * grade) / Math.sqrt(1 + grade * grade);
    const curve = Math.min(0.015, 0.3 / Math.max(radius, 10)); // N/N, ~1.5 % equivalent at R = 20 m
    const fResist = 650 * k + 28 * k * speed + 4.2 * (0.7 + 0.3 * k) * speed * speed + m * G * curve;
    const fStopping = fB + fTrack + fResist; // always opposes motion
    const fPush = fD + fGrav;
    const M = this.inertia;

    const prevA = this.a;
    if (this.slipping) { this._slipStep(dt, { fD, fB, fTrack, fResist, fGrav, N }); this.a = (this.v - this._v0) / dt; this.jerk = dt > 0 ? (this.a - prevA) / dt : 0; return; }
    let acc;
    if (speed < 0.05) {
      // static: brakes and friction hold unless the push exceeds them
      const hold = fB + fResist;
      acc = Math.abs(fPush) <= hold ? 0 : (fPush - Math.sign(fPush) * hold) / M;
      if (acc === 0) this.v = 0;
    } else {
      acc = (fPush - Math.sign(this.v) * fStopping) / M;
    }
    const v0 = this.v;
    this.v += acc * dt;
    // braking/friction cannot reverse the direction of travel by itself
    if (v0 !== 0 && Math.sign(this.v) !== Math.sign(v0) && Math.abs(fPush) <= fB + fResist) this.v = 0;
    this.v = Math.max(-3, this.v);
    // gripping: the force the rail passes to the body (its share of the acceleration, against gravity and
    // resistance); more than the peak and the wheels break away (spinning under drive, sliding braked)
    const fRail = m * acc - fGrav + (this.v !== 0 ? Math.sign(this.v) * (fResist + fTrack) : 0);
    if (Math.abs(fRail) > this.mu * N && (fD > 0 || speed > 0.3)) {
      this.v = v0; this.vw = v0; this.slipping = true;
      this._slipStep(dt, { fD, fB, fTrack, fResist, fGrav, N });
      this.a = (this.v - v0) / dt;
      this.jerk = dt > 0 ? (this.a - prevA) / dt : 0;
      return;
    }
    this.vw = this.v;
    this.slip = this.slide = false; this.slideTime = 0;
    this.s = Math.max(0, this.s + this.v * dt);
    this.a = acc;
    this.jerk = dt > 0 ? (acc - prevA) / dt : 0;
  }

  // The wheels turning on their own: the rotating mass between the motors' and brakes' force and the rail's,
  // the body between the rail's force and gravity, resistance and the track brakes. The rail's force follows
  // the creep curve, so a spin builds up within a second under too much drive and dies down once it is eased
  // (the T3 has no protection against it: the driver's job). Small steps: the curve is steep.
  _slipStep(dt, { fD, fB, fTrack, fResist, fGrav, N }) {
    const mb = this.mass, mr = T3.rotMass * this.cars, muP = this.mu, left = this.spinLeft ?? 0.5, n = 8, h = dt / n;
    this._v0 = this.v;
    let v = this.v, vw = this.vw;
    const along = (f, vel, stat) => {
      // a friction-like force on something moving at vel (or held, up to stat): what is left of f
      if (Math.abs(vel) > 0.01) return f - stat * Math.sign(vel);
      return Math.abs(f) <= stat ? 0 : f - stat * Math.sign(f);
    };
    let F = 0;
    for (let i = 0; i < n; i++) {
      const dv = vw - v, xi = Math.abs(dv) / Math.max(Math.abs(v), 1.5);
      const mu = xi <= CREEP_PEAK ? (muP * xi) / CREEP_PEAK : muP * (left + (1 - left) * Math.exp(-(xi - CREEP_PEAK) / CREEP_FALL));
      F = Math.sign(dv) * mu * N; // forward on the body
      const vw1 = vw + (along(fD - F, vw, fB) / mr) * h;
      const v1 = v + (along(F + fGrav, v, fResist + fTrack) / mb) * h;
      vw = vw !== 0 && Math.sign(vw1) !== Math.sign(vw) ? 0 : vw1; // (the brakes lock the wheels, not reverse them)
      v = v !== 0 && Math.sign(v1) !== Math.sign(v) && Math.abs(fD + fGrav) <= fB + fResist ? 0 : v1;
    }
    this.v = Math.max(-3, v); this.vw = vw;
    this.s = Math.max(0, this.s + this.v * dt);
    // gripping again: the creep back under the peak, and the force the wheels now need within it
    const dv = vw - v, xi = Math.abs(dv) / Math.max(Math.abs(v), 1.5);
    const need = (fD - (Math.abs(v) > 0.01 ? fB * Math.sign(v) : 0)) * (mb / (mb + mr)) - (fGrav * mr) / (mb + mr);
    if (xi <= CREEP_PEAK && Math.abs(need) <= muP * N) {
      this.v = (mb * v + mr * vw) / (mb + mr); this.vw = this.v; this.slipping = false;
    }
    // spinning: the wheels turn faster than the tram moves, in their own direction (also rolling back with
    // the wheels still driving forward, snow trace 2026-11-04); sliding: slower than it moves
    this.slip = this.slipping && (vw - v) * (Math.sign(vw) || 1) > 0 && Math.abs(vw) > Math.abs(v);
    this.slide = this.slipping && Math.abs(vw) < Math.abs(v) && Math.abs(v) > 0.3;
    this.slideTime = this.slide && Math.abs(vw) < 0.3 * Math.abs(v) ? this.slideTime + dt : 0;
  }
}

// Half width of the space a T3 sweeps at s, measured from the track centre: 1.25 m body, the ends
// of a 14 m car with bogies 6.36 m apart swing out by (7² − 3.18²) / 2R in a curve, 0.25 m margin.
export function tramClearance(route, s) {
  return 1.25 + 19.5 / Math.max(15, route.radiusAt(s)) + 0.25;
}
