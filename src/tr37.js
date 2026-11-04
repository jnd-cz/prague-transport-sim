// The T3SUCS's traction equipment ČKD TR 37 as the driver works it (#221): the pedals, the accelerator
// (zrychlovač), the motors and the brakes. Sources, numbers and the derivation:
// docs/research/prazsketramvaje/t3-accelerator.md (§ 2 pedals, § 3 accelerator, § 5 numbers, § 6 the
// model, § 8 the wiring diagram).
//
// Two pedals without detents (HG 14). A drive step sets a CURRENT, which the limiting relay holds by
// turning the 99-position accelerator at up to 20 positions/s: resistance out up to 75, then the bridging
// contactor M2 and four field-weakening stages at 80/85/90/95, rest at 99 ("on the trolley"). The car
// starts through two damping resistors. In coasting the brake loops carry a small "preparation" current
// and the accelerator follows the speed. A brake step sets a brake current; the electric brake fades
// below ≈6 km/h; from brake step 5 on (and parked) the relay LO hands over to the spring-applied shoe
// brakes once the brake current falls below 120 A; the end of the stroke adds the track brakes. The
// brake pedal off zero, an open door or the maximum relay keep the line contactor out (no traction).
// Units: m, s, N, V, Ω; currents are a car's (two motor groups of two motors in series, in parallel).
//
// The interface every vehicle's equipment gives src/tram.js (a T3M's chopper or a T3R.P's IGBT drive
// would be another class with the same): update(dt, ctx) → forces and the current, notch, lamps,
// autoDrive(want) for the autopilot, and its controls (here the pedals, the ratchet and the arcade lever).

export const TR37_SPEC = {
  lineVoltage: 600,
  // the pedal controller HG 14, degrees of the 40° stroke ([ckd16] p. 6, § 2)
  pedalMax: 40,
  driveAngles: [5, 12, 20, 27, 35],
  brakeAngles: [3, 7, 12, 18, 23],
  parkAngle: 27,
  trackAngles: [37, 39.5],   // the rear bogie's magnets, then both bogies' at the stop
  driveHold: 1.5,            // JK2 / R2 hold the line contactor down to here (the pre-step, [ckd24] p. 8)
  brakeOff: 2,               // BK2 opens: no drive
  loAngle: 20.5,             // BK8 opens between brake steps 4 and 5: LO held by the brake current alone
  br1Angle: 9.5,             // BK9 opens between brake steps 2 and 3
  pedalRate: 20,             // °/s a held key moves a pedal (0 to the stop in 2 s)
  // currents (A, car)
  driveCurrent: [220, 290, 360, 420, 480],   // [ckd03] p. 4
  brakeCurrent: [160, 211, 262, 306, 350],   // step 5 [ckd26] p. 4; steps 1–4 from the wiring diagram (§ 8.2)
  prepCurrent: 50,           // coasting (25 per group – 90 on the ammeter by source, § 3.5)
  relayBand: [1.0, 1.1],     // the limiting relay steps on below the setting, back above +10 % (±5 % held, [ckd03] p. 4) [assumed]
  maxRelay: 750,             // A: MR opens the line contactor until the drive pedal is back at 0 ([ckd24] p. 9)
  loCurrent: 120,            // A: LO drops below it ([ckd24] p. 16) …
  loDelay: 0.3,              // s … after the relay's drop time [assumed]
  // the accelerator and the circuit
  accRate: 20,               // positions/s ([ckd17] p. 5: 1 → 99 in 5 s)
  accDrive: 2.835,           // Ω over positions 1–77 in drive (§ 8.1)
  damping: [1.05, 0.7],      // Ω: R1 bridges 0.35, then R2 0.7 (§ 8.1) …
  dampStep: 0.1,             // s each [assumed]
  fieldStages: [[95, 0.55], [90, 0.66], [85, 0.78], [80, 0.89]], // position, field (55 % at the last, [ckd04] p. 2)
  weakScale: 1,              // how much of the chart's weakened-field curve the stages reach (calibrated below)
  rMotor: 0.11,              // Ω per motor [assumed from 91 % efficiency]
  gear: 7.43,                // the sheet's gear ratio ([ckd-schema])
  wheelR: 0.35,              // m, 700 mm new
  gearEff: 0.97,
  // braking
  fade: [3 / 3.6, 6 / 3.6],  // m/s: the electric brake fades between these (step 5 gives 120 A at ≈4 km/h, § 3.6)
  brakeBuild: [0.3, 2.0],    // s for the brake current to build: from coasting, and within coastSettle of
  coastSettle: 2.5,          // driving (the loops not yet excited; ČKD: coast 2–3 s, [ckd03] p. 11) [assumed]
  shoeForce: [0, 9200, 27600], // N per car: shoe brakes released / partly / fully [assumed ≈0.5 / 1.5 m/s² empty]
  trackForce: 12000,         // N per car per magnet pair: 2 × 60 kN attraction × μ 0.1 [μ assumed]
};
const C = TR37_SPEC;

// The TE 022 motor at 300 V ([ckd04] p. 14, read from the chart, § 5.2): current A → rpm and torque Nm at
// full field, and at the weakened field (drawn for 50 %; at 60 and 80 A the 100 A ratios)
const MI = [60, 80, 100, 125, 150, 175, 200, 250, 300, 350, 390];
const N_FULL = [3280, 2610, 2170, 1945, 1775, 1670, 1570, 1430, 1320, 1235, 1165];
const T_FULL = [45, 72, 125, 168, 216, 267, 330, 466, 574, 680, 750];
const N_WEAK = [6035, 4800, 4000, 3460, 3090, 2820, 2610, 2300, 2100, 1910, 1720];
const T_WEAK = [22, 36, 62, 95, 133, 175, 216, 307, 406, 511, 550];
const RPM = (C.gear * 60) / (2 * Math.PI * C.wheelR); // motor rpm per m/s (202.7)

function lin(x, xs, ys) {
  let i = 1;
  while (i < xs.length - 1 && x > xs[i]) i++;
  return ys[i - 1] + ((ys[i] - ys[i - 1]) * (x - xs[i - 1])) / (xs[i] - xs[i - 1]);
}

// [rpm at 300 V, torque] of one motor at current Im and field phi (1 full … 0.55); below 60 A the flux
// follows the current (rpm ∝ 1/I, torque ∝ I²)
export function motor(Im, phi = 1) {
  const w = Math.min(1, ((1 - phi) / 0.5) * C.weakScale);
  if (Im < MI[0]) {
    const k = Math.max(Im, 0.5) / MI[0];
    return [(N_FULL[0] * (1 - w) + N_WEAK[0] * w) / k, (T_FULL[0] * (1 - w) + T_WEAK[0] * w) * k * k];
  }
  return [lin(Im, MI, N_FULL) * (1 - w) + lin(Im, MI, N_WEAK) * w, lin(Im, MI, T_FULL) * (1 - w) + lin(Im, MI, T_WEAK) * w];
}

// back-EMF of one motor at current Im turning at n rpm: (300 V − I·R) × n / n300
const emf = (Im, n, phi) => ((300 - Im * C.rMotor) * n) / motor(Im, phi)[0];

// one motor group's current with resistance R in the car's common lead (it carries both groups, 2·Im):
// U = 2·Im·R + 2·(E + Im·Rm), solved by bisection (E grows with the current: one root)
export function groupCurrent(U, v, R, phi) {
  const n = Math.abs(v) * RPM;
  let lo = 0, hi = 600;
  for (let i = 0; i < 22; i++) {
    const Im = (lo + hi) / 2;
    if (U - 2 * Im * R - 2 * (emf(Im, n, phi) + Im * C.rMotor) > 0) lo = Im; else hi = Im;
  }
  return (lo + hi) / 2;
}

// rail force of a car's four motors (N): traction at group current Im loses the gears' 3 %, the brake at
// loop current Ib (car) gains it
const tractive = (Im, phi) => (4 * motor(Im, phi)[1] * C.gear * C.gearEff) / C.wheelR;
const braking = (Ib) => (4 * motor(Ib / 2, 1)[1] * C.gear) / C.gearEff / C.wheelR;

export const accR = (p) => (p >= 75 ? 0 : (C.accDrive * (77 - p)) / 76); // M2 bridges it from 75 (§ 8.4)
export function field(p) { for (const [q, phi] of C.fieldStages) if (p >= q) return phi; return 1; }

// the accelerator's position in coasting: where drive step 1 would hold its current at this speed
// (≈7 standing, ≈30 at 12 km/h, § 8.2), so drive or brake take up at once
export function pMatch(v) {
  const Im = C.driveCurrent[0] / 2, R = (C.lineVoltage - 2 * (emf(Im, Math.abs(v) * RPM, 1) + Im * C.rMotor)) / (2 * Im);
  return R <= 0 ? 99 : Math.max(1, Math.min(99, 77 - (R * 76) / C.accDrive));
}
// … and braking: the self-excited loops need about 30 at 8–14 km/h (§ 8.2) and the whole 99 from ≈37 km/h;
// position 1 where the brake starts to fade (no resistance left to cut: the current then falls with the
// speed), so braking on step 3+ brings in the shoes partly there (BR1 at position 2, § 3.6)
const pBrake = (v) => Math.max(1, Math.min(99, 1 + (98 * (Math.abs(v) - C.fade[1])) / (37 / 3.6 - C.fade[1])));

// the step a pedal angle is on (0 below the first)
export function stepOf(angle, angles) { let s = 0; for (let i = 0; i < angles.length; i++) if (angle >= angles[i]) s = i + 1; return s; }

export class TR37 {
  constructor(cars = 1) {
    this.cars = cars;
    this.kind = 'pedals';  // which controls and HUD (src/hud.js pedal bar)
    this.mode = 'arcade';  // 'arcade': the lever and the helper; 'advanced': the pedals as they are
    this.lever = 0;        // arcade: −5…+5 steps, −6 the emergency stop
    this.pedal = { drive: 0, brake: 0 }; // degrees
    this.parked = true;    // the brake pedal in its ratchet (the car starts at a stop)
    this.p = 1;            // accelerator position 1…99
    this.ls = false;       // line contactor in (traction)
    this.lsT = 0;          // s since it closed (the damping resistors)
    this.relT = -1;        // s into a release (the dampers back in before it opens), −1: none
    this.mr = false;       // the maximum relay tripped
    this.coastT = 99;      // s since the line contactor opened
    this.brakeT = 99;      // s since the brake pedal was last off zero
    this.Ib = 0;           // brake-loop current (A, car)
    this.lo = false;       // relay LO (shoe brakes held off)
    this.loT = 0;
    this.shoe = 2;         // shoe brakes: 0 released (BR1), 1 partly (BR2), 2 fully applied
    this.shoeF = C.shoeForce[2] * cars;
    this.drive = 0;        // tractive force at the rail (N)
    this.auto = { hold: 0, step: 0 };
  }

  get brakeAngle() { return this.parked ? Math.max(this.pedal.brake, C.parkAngle) : this.pedal.brake; }
  get driveStep() { return stepOf(this.pedal.drive, C.driveAngles); }
  get brakeStep() { return stepOf(this.brakeAngle, C.brakeAngles); }
  // for logs and tests: the drive step, minus the brake step, −6 with the track brakes
  get notch() { const b = this.brakeAngle; return b >= C.trackAngles[0] ? -6 : this.brakeStep ? -this.brakeStep : this.driveStep; }
  get lamps() { return { acc: this.p < 80, shoe: this.shoe > 0 }; } // ZR1: the accelerator's positions 1–80 (§ 8.2)
  get drawing() { return this.ls; } // traction current through the pantograph
  // a step's force standing to the end of the resistors (N), for the autopilot's choice
  driveForce(step) { return tractive(C.driveCurrent[step - 1] / 2, 1) * this.cars; }
  brakeForce(step) { return braking(C.brakeCurrent[step - 1]) * this.cars; }

  // ------------------------------------------------------------------ the driver's controls
  // advanced: a tap moves to the next step's angle along one axis from full brake (−) to full drive (+);
  // the brake stops at step 5 (parking and the track brakes take their own action)
  tap(dir) {
    const P = this.pedal, B5 = C.brakeAngles[4];
    if (dir > 0) {
      if (P.brake > 0) P.brake = [0, ...C.brakeAngles].filter((a) => a < P.brake - 0.01).pop() ?? 0;
      else if (!this.parked) P.drive = C.driveAngles.find((a) => a > P.drive + 0.01) ?? C.pedalMax;
    } else if (P.drive > 0) P.drive = [0, ...C.driveAngles].filter((a) => a < P.drive - 0.01).pop() ?? 0;
    else P.brake = Math.max(P.brake, C.brakeAngles.find((a) => a > P.brake + 0.01) ?? B5);
  }
  // … and held: the pedal moves on at 20°/s; the brake stops at step 5 unless it is already deeper
  hold(dir, dt) {
    const P = this.pedal, d = C.pedalRate * dt, B5 = C.brakeAngles[4];
    if (dir > 0) { if (P.brake > 0) P.brake = Math.max(0, P.brake - d); else if (!this.parked) P.drive = Math.min(C.pedalMax, P.drive + d); }
    else if (P.drive > 0) P.drive = Math.max(0, P.drive - d);
    else if (P.brake < B5) P.brake = Math.min(B5, P.brake + d);
  }
  // a number key: drive step n (n > 0), brake step −n, or both pedals released (0); −6 the emergency stop
  setStep(n) {
    const P = this.pedal;
    if (n > 0) { if (this.parked) return; P.brake = 0; P.drive = C.driveAngles[n - 1] + 1; }
    else if (n <= -6) { P.drive = 0; P.brake = C.pedalMax; }
    else if (n < 0) { P.drive = 0; P.brake = C.brakeAngles[-n - 1] + 0.5; }
    else { P.drive = 0; P.brake = 0; }
  }
  // the ratchet: press to the station position and tip the plate; tipped back, the springs return it to 0
  park(on = !this.parked) {
    this.parked = on;
    if (on) this.pedal.drive = 0;
    else this.pedal.brake = 0;
  }

  // arcade: the lever's step on the pedals, with what a driver does without thinking: off one pedal before
  // the other, parked whenever the car stands without drive, unparked to drive
  _arcade(doorsOpen, v) {
    const L = this.lever, P = this.pedal;
    if (L > 0 && !doorsOpen) {
      if (this.parked) this.parked = false;
      P.brake = 0;
      P.drive = C.driveAngles[L - 1] + 1;
    } else {
      P.drive = 0;
      P.brake = L >= 0 ? 0 : L <= -6 ? C.pedalMax : C.brakeAngles[-L - 1] + 0.5;
      if (Math.abs(v) < 0.1) this.parked = true;
    }
  }

  // the autopilot's wish on the pedals, as a careful driver: want = { force (N, + drive / − brake), stand
  // (stop and stay), coast, power (true: current through the pantograph, false: none), urgent, v, dt,
  // slip, slide, stopDist (m to the stop point, or null) }. Stands parked; brakes on step 3 or more into the
  // stop (BR1: the shoes partly), step 5 at a crawl when the stop needs it (LO: fully); coasts 2.5 s
  // between drive and brake unless urgent ([ckd03] p. 11); one step change per 0.6 s unless urgent.
  autoDrive(w) {
    this.mode = 'advanced';
    const A = this.auto;
    A.hold -= w.dt;
    if (w.stand && Math.abs(w.v) < 0.05) { if (!this.parked) this.park(true); A.step = -5; return; }
    if (!w.stand && this.parked) this.park(false);
    const pick = (f, force) => { for (let k = 1; k <= 5; k++) if (force(k) >= f) return k; return 5; };
    // (into a stop on step 3 or more: at the fade the shoes come in partly and the car stops gently)
    const brake = -pick(-w.force, (k) => this.brakeForce(k));
    let s = w.stand ? Math.min(-3, brake) : w.coast ? 0 : w.force > 0 ? pick(w.force, (k) => this.driveForce(k)) : brake;
    if (w.power === true) s = Math.max(1, s);
    if (w.power === false) s = Math.min(0, s);
    if (w.slip && s > 1) s--;
    if (w.slide && s < -1) s++;
    // right after drive the brake loops are not excited yet: steps 1–4 only build more slowly, step 5 would
    // drop LO and bring the shoes in at speed, so step 4 at most until they settle; after braking, coast
    // before driving again ([ckd03] p. 11). (From a stand the loops are not the question.)
    if (!w.urgent && Math.abs(w.v) > 2) {
      if (s < -4 && (this.ls || this.coastT < C.coastSettle)) s = -4;
      if (s > 0 && this.brakeT < C.coastSettle) s = 0;
    }
    // at a crawl (below ≈9 km/h) steps 1–2 fade out to nothing and steps 3–4 leave only the shoes partly
    // applied (≈0.5 m/s², less than a downhill grade takes): a stop point still needing more than 0.3 m/s²
    // gets step 5, so LO hands over to the full shoes, as a driver does (it overran stops by 1–4 m and a red
    // signal at 0.9 km/h on step 3–4: #241's first check)
    if (s < 0 && Math.abs(w.v) < 2.5) {
      const need = w.stopDist == null ? 0 : (w.v * w.v) / (2 * Math.max(0.3, w.stopDist));
      s = need > 0.3 ? -5 : Math.min(s, -3);
    }
    if (s !== A.step && (A.hold <= 0 || w.urgent || (s < A.step && s < 0) || w.power != null)) {
      A.step = s; A.hold = 0.6;
      this.setStep(s);
    }
  }

  // ------------------------------------------------------------------ one step
  // ctx: { v, voltage, doorsOpen, rescue, forcedStop } → { drive, brake (wheel: electric + shoes), track
  // (magnet pairs), current (A, the ammeter, negative braking), line (A drawn from the line, all cars),
  // dissipated (W in the resistors) }
  update(dt, { v = 0, voltage = C.lineVoltage, doorsOpen = false, rescue = false, forcedStop = false } = {}) {
    if (this.mode === 'arcade') this._arcade(doorsOpen, v);
    const k = this.cars, speed = Math.abs(v);
    const b = this.brakeAngle, d = this.pedal.drive;
    this.brakeT = b >= C.brakeOff ? 0 : this.brakeT + dt;

    // the line contactor LS: brake pedal at 0 (BK2), drive ≥ step 1 (JK1, then R2 holds it down to the
    // pre-step), doors closed (DBR), the maximum relay not tripped, the safety relay RB up
    if (this.mr && d < C.driveHold) this.mr = false;
    const allowed = b < C.brakeOff && !doorsOpen && !this.mr && !rescue && !forcedStop;
    if (!this.ls && allowed && this.driveStep >= 1) { this.ls = true; this.lsT = 0; this.relT = -1; this.Ib = 0; }
    else if (this.ls) {
      if (!allowed) this.ls = false;
      else if (d < C.driveHold) { if (this.relT < 0) this.relT = 0; } // R1, R2 drop: the dampers back in, then LS out
      else this.relT = -1;
    }
    if (this.relT >= 0) { this.relT += dt; if (this.relT >= 2 * C.dampStep) { this.ls = false; this.relT = -1; } }
    this.coastT = this.ls ? 0 : this.coastT + dt;

    let fDrive = 0, fElec = 0, I = 0;
    if (this.ls) {
      this.lsT += dt;
      const D = C.damping, Rd = this.relT >= 0 ? D[this.relT < C.dampStep ? 1 : 0] : this.lsT < C.dampStep ? D[0] : this.lsT < 2 * C.dampStep ? D[1] : 0;
      const phi = field(this.p), Im = groupCurrent(voltage, speed, accR(this.p) + Rd, phi);
      I = 2 * Im;
      const set = C.driveCurrent[Math.max(1, this.driveStep) - 1];
      // the limiting relay turns the accelerator on below the setting, back above it; the pilot motor
      // stops at 97 and the cross coasts on to 99, where the pedal no longer matters until it is back at 0
      if (this.p < 97 && this.relT < 0) {
        if (I < set * C.relayBand[0]) this.p = Math.min(99, this.p + C.accRate * dt);
        else if (I > set * C.relayBand[1]) this.p = Math.max(1, this.p - C.accRate * dt);
        if (this.p >= 97) this.p = 99;
      }
      if (I > C.maxRelay) { this.mr = true; this.ls = false; }
      fDrive = tractive(Im, phi) * k;
    } else {
      // the brake loops: preparation current coasting, the step's current braking, fading at a crawl;
      // the accelerator follows the speed
      const fade = Math.max(0, Math.min(1, (speed - C.fade[0]) / (C.fade[1] - C.fade[0])));
      const bs = this.brakeStep, on = b >= C.brakeOff;
      const want = (on && bs ? C.brakeCurrent[bs - 1] : C.prepCurrent) * fade;
      const settled = this.mode === 'arcade' || this.coastT >= C.coastSettle;
      const rate = Math.max(want, 100) / C.brakeBuild[settled ? 0 : 1];
      this.Ib += Math.max(-600 * dt, Math.min(rate * dt, want - this.Ib));
      const pt = on ? pBrake(speed) : pMatch(speed);
      this.p += Math.max(-C.accRate * dt, Math.min(C.accRate * dt, pt - this.p));
      I = -this.Ib;
      fElec = braking(this.Ib) * k;
    }

    // LO: its voltage coil (BK8) holds it up to brake step 4; from step 5 (and parked) only the brake
    // current does. Down, the shoe brakes apply fully; the pedal back at 0 lifts it (partly released),
    // the drive pedal (M1 → BR1) releases them. BR1 also falls when braking on step 3+ reaches position 2.
    if (b >= C.loAngle && !this.ls && this.Ib < C.loCurrent) this.loT += dt; else this.loT = 0;
    if (this.loT > C.loDelay) this.lo = false;
    if (b < C.brakeOff) this.lo = true;
    if (rescue || !this.lo) this.shoe = 2;
    else if (this.ls) this.shoe = 0;
    else if (this.shoe === 2) this.shoe = 1;
    if (!this.ls && b >= C.br1Angle && this.p < 2) this.shoe = Math.max(this.shoe, 1);
    const shoeT = C.shoeForce[this.shoe] * k;
    this.shoeF += Math.max(-60000 * k * dt, Math.min(40000 * k * dt, shoeT - this.shoeF)); // (springs, magnets)

    // the tractive force builds with the motors' inductance (≈0.15 s)
    this.drive += (fDrive - this.drive) * Math.min(1, dt / 0.15);
    const track = rescue || b >= C.trackAngles[1] ? 2 : b >= C.trackAngles[0] ? 1 : 0;
    return {
      drive: this.drive, brake: fElec + this.shoeF, track: track * C.trackForce * k, trackOn: track > 0,
      current: I, line: this.ls ? I * k : 0, dissipated: fElec * speed,
    };
  }
}
