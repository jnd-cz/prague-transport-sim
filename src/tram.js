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

// wheel/rail adhesion coefficient by weather (sand adds ~0.1); snow: the rail head under fresh snow
// (game.js: compacted snow and ice at the pedestrian crossings is worse)
export const ADHESION = { dry: 0.30, rain: 0.17, leaves: 0.15, snow: 0.12 };

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

  update(dt, { deadmanTrip = false, grade = 0, radius = 1e6, mu = ADHESION.dry, sandKey = false, doorsOpen = false } = {}) {
    const m = this.mass, k = this.cars, speed = Math.abs(this.v);
    this.grade = grade;
    const out = this.eq.update(dt, { v: this.v, voltage: this.voltage, doorsOpen, rescue: deadmanTrip, forcedStop: this.forcedStop });

    // sand: driver key, or automatically with the track brakes
    this.sanding = (sandKey || (out.trackOn && speed > 0.3)) && this.sand > 0;
    if (this.sanding) this.sand = Math.max(0, this.sand - dt / 90);
    this.mu = Math.min(0.33, mu + (this.sanding ? 0.1 : 0));
    const adhesion = this.mu * m * G; // all axles are motored and braked

    // adhesion limit: exceeding it spins (traction) or locks (braking) the wheels
    this.drive = out.drive; this.brake = out.brake;
    let fD = this.drive, fB = this.brake;
    this.slip = fD > adhesion && speed < T3.vMax;
    if (this.slip) fD = 0.7 * adhesion;
    this.slide = fB > adhesion && speed > 0.3;
    if (this.slide) fB = 0.75 * adhesion;
    this.slideTime = this.slide ? this.slideTime + dt : 0;
    this.trackBrake = out.trackOn && speed > 0.3;
    const fTrack = this.trackBrake ? out.track : 0; // (the magnets: no adhesion limit)

    this.time = (this.time || 0) + dt; // (simulation time: the same drive gives the same result)
    this.electric = out.line > 0 ? this.voltage * out.line : -out.dissipated;
    this.voltage = T3.lineVoltage + 18 * Math.sin((this.time * 1000) / 2300) - out.line * 0.045;
    // wheelspin: motor current collapses and flickers
    this.current = this.forcedStop ? 0 : out.current * (this.slip ? 0.55 + 0.2 * Math.sin((this.time * 1000) / 40) : 1);

    if (this.forcedStop) {
      // held (collision, crowbar...): it can't roll away when released
      this.v = 0; this.a = 0; this.drive = 0;
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
    this.s = Math.max(0, this.s + this.v * dt);
    this.a = acc;
    this.jerk = dt > 0 ? (acc - prevA) / dt : 0;
  }
}

// Half width of the space a T3 sweeps at s, measured from the track centre: 1.25 m body, the ends
// of a 14 m car with bogies 6.36 m apart swing out by (7² − 3.18²) / 2R in a curve, 0.25 m margin.
export function tramClearance(route, s) {
  return 1.25 + 19.5 / Math.max(15, route.radiusAt(s)) + 0.25;
}
