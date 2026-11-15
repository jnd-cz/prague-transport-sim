// SPDX-License-Identifier: AGPL-3.0-or-later
// A tram's longitudinal dynamics: the body (mass, length, capacity) and the forces on it (gravity,
// running and curve resistance, adhesion, sand), with the traction equipment as its own part (#221):
// `tram.eq` turns the driver's controls into tractive and brake forces and the line current. The T3SUCS
// has the ČKD TR 37 (src/tr37.js); another model would bring its body table and its equipment class.

import { TR37 } from './tr37.js';

const G = 9.81;

// the Tatra T3's body (per car); a vehicle's manifest names its type (assets/*/vehicle.json `type`, VEHICLE_TYPES)
export const T3 = {
  length: 15.2,              // over couplers (body 14.0 m), DPP training manual: the head's face to the other's
  width: 2.5,                // the body (tramClearance's 1.25 m a side); a package's car is measured against it (#530)
  // (#248, the sources in the issue's research comment of 2026-11-04)
  bogies: 6.4,               // bogie pivots apart (J. Dynybyl, ČVUT FS bachelor thesis 2018, Table 3: 3.8 m from each frame end)
  trackBrakeGap: 0.012,      // the released magnet's pole pieces over the rail, new wheels (ČKD T-50496 p. 1: 8-12 mm)
  couplerPivot: 6.25,        // the coupler yoke's pin from the car centre [estimated on the frame figure of Ivanov et al. 1977]
  // two coupled Prague heads overlap: each reaches 80 mm past the plane they couple in (its pins 45 mm
  // either side of it; M. Barnet, ČVUT FS diploma thesis 2019, drawing DP-2018-01, the head in plan)
  couplerOverlap: 0.16,
  emptyMass: 16000,          // kg
  rotMass: 2400,             // kg: motors, gears and wheels turning, ≈15 % of the empty car (t3-accelerator.md § 5.3)
  paxMass: 72,               // kg / passenger
  capacity: 110,             // 24 seated + 86 standing (crush load 160)
  crushCapacity: 160,
  vMax: 65 / 3.6,            // empty, on the level ([ckd03] p. 4)
  // s of sanding in the box, full from the depot and refilled at each terminus (src/game.js, the user, 2026-11-04, #265): "on the level of
  // minutes if not more" (the user, 2026-11-07, PR #363). A tram's
  // box holds at least 17 dm³ (ČSN 28 1300), 25-27 kg, and a sander gives 400-500 g per 30 s (TSI; tram dosers 410-590 g measured):
  // 25-33 min of sanding (Matečka 2015, VUT Brno, pp. 14, 16, 66-69: raw/reference/adhesion/, #266). The T3's own box is not known.
  // 90 s ran dry on every line 9 run in autumn
  sandSecs: 1500,
  lineVoltage: 600,
};
export const VEHICLE_TYPES = { T3 };

// Wheel/rail adhesion (peak, at a standstill) by weather: the game's values, which the checks were set on. The research
// (docs/research/rail-adhesion.md, #266) has rain 0.18, autumn rail between the leaf patches 0.22 (an estimate) and light
// snow 0.10; the user, 2026-11-11, kept these ("Keep the main values"). game.js: leaf patches and the icy pedestrian crossings.
export const ADHESION = { dry: 0.30, rain: 0.17, leaves: 0.15, snow: 0.12 };

// Adhesion falls with speed: Curtius–Kniffler, μ = 0.161 + 7.5 / (v + 44) with v in km/h, as a factor of
// its standstill value: 1.00 at 0, 0.75 at 40, 0.70 at 60 km/h (#266)
export const muSpeed = (v) => (0.161 + 7.5 / (Math.abs(v) * 3.6 + 44)) / 0.3315;

// Sand by the rail's state (#266): no gain on dry rail (the lab even measured a loss), about +0.045 on wet
// rail and snow (Moore), and on a leaf patch two to three times its grip (field braking 1.5 → 4.5 %g).
// The patch is told by its value (game.js: 0.06; nothing else is that low)
export const sandedMu = (mu) => (mu < 0.07 ? mu * 2.5 : mu < 0.27 ? Math.min(0.27, mu + 0.045) : mu);

// The creep curve, lumped over the axles: the force rises to its peak at CREEP_PEAK and falls towards
// SPIN_LEFT of it when the wheels spin or lock (dry ≈ 40–50 % of peak, wet nearly flat: #266, Polach);
// creep is the wheels' speed against the tram's over the tram's speed (at least 1.5 m/s: from a stand)
const CREEP_PEAK = 0.03, CREEP_FALL = 0.15, SPIN_LEFT = { dry: 0.5, rain: 0.85, leaves: 0.5, snow: 0.6 };

// Axles from the front of each car (bogie centres 6.36 m apart, axle base 1.9 m, coupler 0.6 m); the T3SUCS
// sands in front of the first axle, both wheels (DPP 2009 training textbook, #266). Sand on the rail helps the
// axles that follow, ours and the second car's; how long it lasts is not measured: SAND_LIFE s [assumed]
const AXLES = [3.47, 5.37, 9.83, 11.73];
const SAND_LIFE = 60;

// Prague ran the T3 mostly as two-car multiple-unit sets (both cars motored, one driver).
// Everything that scales with the cars lives here.
// coupled cars stand 15.04 m apart: 15.2 m over couplers less the heads' overlap (the user, 2026-11-04: "length
// over couplers minus body length minus shortening because how the couplers fit together"), the bodies 1.04 m
export const COUPLING_GAP = -T3.couplerOverlap;
export const CAR_PITCH = T3.length + COUPLING_GAP;
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
    this.supply = { u0: T3.lineVoltage, r: 0 }; // what the wire gives here (src/electric.js Feeding, from the game)
    this.loadW = 0;        // W of heating on the line; button: A through the switch button's resistor, both from the game
    this.buttonA = 0;
    this.trackBrake = false;
    this.trackMagnets = 0;
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
        const s = this.s - c * CAR_PITCH - AXLES[i];
        let mu = muAt(s);
        const sanded = (c === 0 && i === 0 && this.sanding) || this.sandTrail.some(([a, b, t]) => s >= a && s <= b && now - t < SAND_LIFE);
        if (sanded) mu = sandedMu(mu);
        sum += mu; n++;
      }
    }
    this.spinLeft = SPIN_LEFT[weather] ?? 0.5;
    return (sum / n) * muSpeed(this.v);
  }

  // mu: a number, or the rail's grip along the route (s → μ); weather: the creep curve's fall
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
      this.sand = Math.max(0, this.sand - dt / T3.sandSecs);
      const s1 = this.s - AXLES[0] + 0.5, last = this.sandTrail[this.sandTrail.length - 1];
      if (last && this.time - last[2] < 0.5 && Math.abs(s1 - last[1]) < 2 + speed * dt) { last[1] = Math.max(last[1], s1); last[0] = Math.min(last[0], s1); last[2] = this.time; }
      else this.sandTrail.push([s1, s1, this.time]);
    }
    if (this.sandTrail.length && this.time - this.sandTrail[0][2] >= SAND_LIFE) this.sandTrail = this.sandTrail.filter((x) => this.time - x[2] < SAND_LIFE);
    const muAt = typeof mu === 'function' ? mu : () => mu;
    this.mu = this.peakMu(muAt, weather);
    const N = m * G; // all axles are motored and braked

    this.drive = out.drive; this.brake = out.brake;
    const fD = this.drive, fB = this.brake;
    this.trackBrake = out.trackOn && speed > 0.3;
    this.trackMagnets = out.trackPairs; // (0 off, 1 the rear bogies', 2 all: the shoes on the rail)
    const fTrack = this.trackBrake ? out.track : 0; // (the magnets: no adhesion limit)

    this.electric = out.line > 0 ? this.voltage * out.line : -out.dissipated;
    // the wire: everything this set draws, through the resistance to its substation (a fast filter for the needle
    // and the step's order: the equipment read the last step's voltage)
    this.lineA = out.line + out.auxLine + this.buttonA + this.loadW / Math.max(100, this.voltage);
    const u = Math.max(this.supply.floor ?? 0, this.supply.u0 - this.supply.r * this.lineA);
    this.voltage += (u - this.voltage) * Math.min(1, dt / 0.05);
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
    for (let i = 0; i < n; i++) {
      const dv = vw - v, xi = Math.abs(dv) / Math.max(Math.abs(v), 1.5);
      const mu = xi <= CREEP_PEAK ? (muP * xi) / CREEP_PEAK : muP * (left + (1 - left) * Math.exp(-(xi - CREEP_PEAK) / CREEP_FALL));
      const F = Math.sign(dv) * mu * N; // forward on the body
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
    // the wheels still driving forward); sliding: slower than it moves
    this.slip = this.slipping && (vw - v) * (Math.sign(vw) || 1) > 0 && Math.abs(vw) > Math.abs(v);
    this.slide = this.slipping && Math.abs(vw) < Math.abs(v) && Math.abs(v) > 0.3;
    this.slideTime = this.slide && Math.abs(vw) < 0.3 * Math.abs(v) ? this.slideTime + dt : 0;
  }
}

// Half width of the space a T3 sweeps at s, measured from the track centre: 1.25 m body, the ends
// of a 14 m car with its bogies T3.bogies apart swing out by (7² − 3.2²) / 2R in a curve, 0.25 m margin.
const SWING = (7 ** 2 - (T3.bogies / 2) ** 2) / 2;
export function tramClearance(route, s) {
  return 1.25 + SWING / Math.max(15, route.radiusAt(s)) + 0.25;
}
