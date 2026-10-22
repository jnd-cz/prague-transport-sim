// Tatra T3 longitudinal dynamics.
//
// Calibrated to the ČKD T3 pamphlet: 16 t empty, 4 x 40 kW, max 65 km/h, max acceleration
// and max service deceleration 1.8 m/s2 (empty car), max deceleration ~5 m/s2 with track brakes.
// Forces (not accelerations) are fixed, so a full car accelerates and brakes more slowly.
//
// Controller notch: +1..+4 drive, 0 neutral, -1..-4 electrodynamic brake (mechanical below
// ~9 km/h), -5 emergency: full wheel brake + magnetic track brakes + sand.

const G = 9.81;

export const T3 = {
  length: 15.2,              // over couplers (body 14.0 m), DPP training manual
  emptyMass: 16000,          // kg
  paxMass: 72,               // kg / passenger
  capacity: 110,             // 24 seated + 86 standing (crush load 160)
  crushCapacity: 160,
  maxPower: 172000,          // W at the wheel, short-term (4 x 40 kW continuous)
  driveForce: [0, 8500, 16000, 23000, 28800],   // N per notch -> 1.8 m/s2 empty at J4
  brakeForce: [0, 7500, 14500, 21500, 28800],   // N per notch -> 1.8 m/s2 empty at B4
  trackBrakeForce: 44000,    // N, 4 magnetic shoes, independent of wheel/rail adhesion
  edBrakeMinV: 2.5,          // m/s; below this the ED brake fades and the drum brake takes over
  vMax: 65 / 3.6,
  lineVoltage: 600,
};

// wheel/rail adhesion coefficient by weather (sand adds ~0.1)
export const ADHESION = { dry: 0.30, rain: 0.17, leaves: 0.15 };

// Prague ran the T3 mostly as two-car multiple-unit sets (both cars motored, one driver).
// Everything that scales with the cars lives here.
export const COUPLING_GAP = 0;     // cars are 15.2 m over couplers, coupled buffer to buffer
export const PANTO_FROM_FRONT = 4.5; // the (first car's) pantograph, which works the overhead contacts
                                     // (coupler 0.6 m + half body 7.0 m - 3.1 m ahead of the centre)

export class Tram {
  constructor(cars = 1) {
    this.cars = cars;
    this.s = 0;            // front position along route (m)
    this.v = 0;            // m/s, negative when rolling back
    this.a = 0;            // m/s2
    this.notch = -2;
    this.drive = 0;        // applied tractive force (N), slewed
    this.brake = 0;        // applied wheel brake force (N), slewed
    this.passengers = 0;
    this.current = 0;
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
  get length() { return T3.length * this.cars + COUPLING_GAP * (this.cars - 1); }
  get capacity() { return T3.capacity * this.cars; }
  get crushCapacity() { return T3.crushCapacity * this.cars; }
  get panto() { return this.s - PANTO_FROM_FRONT; }
  driveForce(notch) { return T3.driveForce[notch] * this.cars; }
  brakeForce(notch) { return T3.brakeForce[notch] * this.cars; }
  get kmh() { return this.v * 3.6; }
  // net applied force for gauges, sounds and the overhead contact (+ drawing current)
  get force() { return this.drive - this.brake; }
  set force(f) { this.drive = Math.max(0, f); this.brake = Math.max(0, -f); }

  update(dt, { deadmanTrip = false, grade = 0, radius = 1e6, mu = ADHESION.dry, sandKey = false, autoHold = false } = {}) {
    const m = this.mass;
    let notch = deadmanTrip ? -5 : this.notch;
    const emergency = notch === -5;
    this.grade = grade;

    // sand: driver key, or automatically with the emergency brake
    this.sanding = (sandKey || (emergency && Math.abs(this.v) > 0.3)) && this.sand > 0;
    if (this.sanding) this.sand = Math.max(0, this.sand - dt / 90);
    this.mu = Math.min(0.33, mu + (this.sanding ? 0.1 : 0));
    const adhesion = this.mu * m * G; // all axles are motored and braked
    const k = this.cars;

    // targets
    let targetDrive = 0, targetBrake = 0;
    if (notch > 0) {
      const pNotch = T3.maxPower * k * (0.4 + 0.15 * notch);
      let f = Math.min(this.driveForce(notch), pNotch / Math.max(Math.abs(this.v), 0.5));
      if (this.v > 16.5) f *= Math.max(0, 1 - (this.v - 16.5) / (T3.vMax - 16.5 + 0.3));
      targetDrive = f;
    } else if (notch < 0) {
      targetBrake = this.brakeForce(Math.min(4, -notch));
    }
    // doors open: the T3's door interlock holds the car on the brakes
    if (autoHold) targetBrake = Math.max(targetBrake, this.brakeForce(2));

    // jerk-limited response (contactors, brake cylinders)
    this.drive += Math.max(-30000 * k * dt, Math.min(24000 * k * dt, targetDrive - this.drive));
    this.brake += Math.max(-30000 * k * dt, Math.min((emergency ? 90000 : 28000) * k * dt, targetBrake - this.brake));

    // adhesion limit: exceeding it spins (traction) or locks (braking) the wheels
    let fDrive = this.drive, fBrake = this.brake;
    this.slip = fDrive > adhesion && Math.abs(this.v) < T3.vMax;
    if (this.slip) fDrive = 0.7 * adhesion;
    this.slide = fBrake > adhesion && Math.abs(this.v) > 0.3;
    if (this.slide) fBrake = 0.75 * adhesion;
    this.slideTime = this.slide ? this.slideTime + dt : 0;
    this.trackBrake = emergency && Math.abs(this.v) > 0.3;
    const fTrack = this.trackBrake ? T3.trackBrakeForce * k : 0;

    if (this.forcedStop) {
      // held (collision, crowbar...): brakes stay applied so it can't roll away when released
      this.v = 0; this.a = 0; this.drive = 0;
      this.brake = Math.max(this.brake, this.brakeForce(3));
      this._electrics(dt, 0);
      return;
    }

    // external forces
    const fGrav = (-m * G * grade) / Math.sqrt(1 + grade * grade);
    const curve = Math.min(0.015, 0.3 / Math.max(radius, 10)); // N/N, ~1.5 % equivalent at R = 20 m
    const speed = Math.abs(this.v);
    const fResist = 650 * k + 28 * k * speed + 4.2 * (0.7 + 0.3 * k) * speed * speed + m * G * curve;
    const fStopping = fBrake + fTrack + fResist; // always opposes motion
    const fPush = fDrive + fGrav;

    const prevA = this.a;
    let acc;
    if (speed < 0.05) {
      // static: brakes and friction hold unless the push exceeds them
      const hold = fBrake + fResist;
      acc = Math.abs(fPush) <= hold ? 0 : (fPush - Math.sign(fPush) * hold) / m;
      if (acc === 0) this.v = 0;
    } else {
      acc = (fPush - Math.sign(this.v) * fStopping) / m;
    }
    const v0 = this.v;
    this.v += acc * dt;
    // braking/friction cannot reverse the direction of travel by itself
    if (v0 !== 0 && Math.sign(this.v) !== Math.sign(v0) && Math.abs(fPush) <= fBrake + fResist) this.v = 0;
    this.v = Math.max(-3, this.v);
    this.s = Math.max(0, this.s + this.v * dt);
    this.a = acc;
    this.jerk = dt > 0 ? (acc - prevA) / dt : 0;
    this._electrics(dt, notch, fDrive);
  }

  _electrics(dt, notch, fDrive = 0) {
    let electric = 0; // W drawn (+) or dissipated in the braking resistors (-)
    if (fDrive > 0) electric = (fDrive * Math.max(Math.abs(this.v), 0.6)) / 0.86 + 9000 * Math.min(1, fDrive / 8000);
    else if (this.brake > 0 && this.v > T3.edBrakeMinV && notch !== -5) electric = -this.brake * this.v * 0.9;
    else if (notch === -5 && Math.abs(this.v) > 0.3) electric = -60000; // track brake coils
    const drop = electric > 0 ? (electric / 600) * 0.045 : 0;
    // simulation time, not the wall clock: the current decides the contacts (switches), so the
    // same drive must give the same result (headless tests)
    this.time = (this.time || 0) + dt;
    this.voltage = T3.lineVoltage + 18 * Math.sin(this.time * 1000 / 2300) - drop;
    this.electric = electric;
    const targetI = electric / Math.max(this.voltage, 300);
    // wheelspin: motor current collapses and flickers
    const slipI = this.slip ? 0.55 + 0.2 * Math.sin(this.time * 1000 / 40) : 1;
    this.current += (targetI * slipI - this.current) * Math.min(1, dt * 6);
  }
}
