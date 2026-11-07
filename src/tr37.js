// The T3SUCS's traction equipment ČKD TR 37 as the driver works it (#221): the pedals, the accelerator
// (zrychlovač), the motors and the brakes. Sources, numbers and the derivation:
// docs/research/prazsketramvaje/t3-accelerator.md (§ 2 pedals, § 3 accelerator, § 5 numbers, § 6 the
// model, § 8 the wiring diagram).
//
// Two pedals without detents (HG 14). A drive step sets a CURRENT, which the limiting relay holds by
// turning the 99-position accelerator at up to 20 positions/s: resistance out up to 75, then the bridging
// contactor M2 and four field-weakening stages at 80/85/90/95, rest at 99 ("on the trolley"). The car
// starts through two damping resistors. Pedal off, the motors stay in two cross-connected brake loops through the
// accelerator, and the same relay turns it the other way to hold a small "preparation" current (T3SU-24 § 4.2): the
// rollers go back towards the start as the speed falls, and up again when it rises downhill. A brake step sets a
// larger current in the same loops and the same relay holds it (§ 4.3), so the position comes from the motor chart
// and the loop's resistance, not from a table: nothing but the pilot motor moves it, at up to 20 positions/s. Below
// ≈4 km/h the loops no longer excite; from brake step 5 on (and parked) the relay LO hands over to the
// spring-applied shoe brakes once the brake current falls below 120 A; the end of the stroke adds the track brakes.
// The brake pedal off zero, an open door, the maximum relay or a stopped motor-generator keep the line contactor out.
// Units: m, s, N, V, Ω; currents are a car's (two motor groups of two motors in series, in parallel).
//
// The interface every vehicle's equipment gives src/tram.js (a T3M's chopper or a T3R.P's IGBT drive
// would be another class with the same): update(dt, ctx) → forces and the current, notch, lamps,
// autoDrive(want) for the autopilot, and its controls (here the pedals, the ratchet and the arcade lever).

import { MotorGenerator, AuxBus } from './electric.js';

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
  footRate: 45,              // °/s a pedal goes to the step asked for: a firm press, ≈0.5 s to brake step 5 [assumed]
  // currents (A, car)
  driveCurrent: [220, 290, 360, 420, 480],   // [ckd03] p. 4
  brakeCurrent: [160, 211, 262, 306, 350],   // step 5 [ckd26] p. 4; steps 1–4 from the wiring diagram (§ 8.2)
  prepCurrent: 50,           // coasting (25 per group – 90 on the ammeter by source, § 3.5)
  relayBand: [1.0, 1.06],    // the limiting relay turns the pilot motor below the setting and back above it (±5 % held, [ckd03] p. 4) [assumed]
  relayPulse: 0.08,          // … in pulses (coil PC, T3SU-19 p. 3): at full speed only this share of the setting away from it [assumed]
  // (the setting falls with coil RC's current, so it rises as the 24 V side sags: step 1 240 A at 26 V, 270 A at 23 V,
  // T3SU-26 p. 4; the other steps by their RC current, 57 / 38 / 28 / 19 / 0 mA, § 8.2)
  rcShift: [10, 6.7, 4.9, 3.3, 0], // A per volt below 26
  maxRelay: 750,             // A: MR opens the line contactor until the drive pedal is back at 0 ([ckd24] p. 9)
  loCurrent: 120,            // A: LO drops below it ([ckd24] p. 16) …
  loDelay: 0.1,              // s … after the relay's drop time [assumed]
  // the accelerator and the circuit
  accRate: 20,               // positions/s at 24 V, both ways ([ckd17] p. 5: 5 ± 0.5 s a sweep)
  accDrive: 2.835,           // Ω over positions 1–77 in drive (§ 8.1)
  accBrake: 3.614,           // Ω over positions 1–99 in the brake loops, out as the position falls (§ 8.1, T3SU-24 § 1.4)
  pMin: 2.5,                 // pedal off, the pilot motor's return path ends at position 3 (ZR8, T3SU-17 p. 7) and the cross coasts on
  damping: [1.05, 0.7],      // Ω: R1 bridges 0.35, then R2 0.7 (§ 8.1) …
  dampStep: 0.1,             // s each [assumed]
  fieldStages: [[95, 0.55], [90, 0.66], [85, 0.78], [80, 0.89]], // position, field (55 % at the last, [ckd04] p. 2)
  // a group's field with its shunts: F4 or F1 alone 78 %, with F2 or F3 55 % (the car's stages above, by group); F2
  // alone 65 %, from the same shunts in parallel [calc]
  shunt: { first: 0.78, second: 0.55, f2: 0.65 },
  weakScale: 1,              // how much of the chart's weakened-field curve the stages reach (calibrated below)
  rMotor: 0.11,              // Ω per motor [assumed from 91 % efficiency]
  rLoop: 0.17,               // Ω per group's share of a brake loop outside the motors (cables, contactors, OR): 120 A at ≈4 km/h at the bottom of the
                             // accelerator ([ckd24] p. 16, [ckd03] p. 7), which also starts step 5's fade at ≈6 km/h [calibrated]
  remanence: 0.0047,         // V/rpm: what the loops excite from, 3 % of the flux at 150 A [assumed]
  loopLag: 0.2,              // s for the brake current to follow (the fields' inductance) [assumed]
  loopDelay: 0.25,           // s from the line contactor out to B1 and B2 in, which the loops and the pilot motor's way back go through [assumed]
  gear: 7.43,                // the sheet's gear ratio ([ckd-schema])
  wheelR: 0.35,              // m, 700 mm new
  gearEff: 0.97,
  // braking
  coastSettle: 2.5,          // s the autopilot coasts between drive and brake: the accelerator's way back (ČKD: 2–3 s, [ckd03] p. 11)
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

// [rpm at 300 V, torque] of one motor at current Im and field phi (1 full … 0.55); below 60 A the flux follows
// the current from the iron's remanence (a self-excited loop's flux never quite starts from nothing)
export function motor(Im, phi = 1) {
  const w = Math.min(1, ((1 - phi) / 0.5) * C.weakScale);
  if (Im < MI[0]) {
    const f60 = (300 - MI[0] * C.rMotor) / (N_FULL[0] * (1 - w) + N_WEAK[0] * w);
    const f = C.remanence + ((f60 - C.remanence) * Im) / MI[0];
    return [(300 - Im * C.rMotor) / f, (T_FULL[0] * (1 - w) + T_WEAK[0] * w) * (f / f60) * (Im / MI[0])];
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
const braking = (Ib, phi = 1) => (4 * motor(Ib / 2, phi)[1] * C.gear) / C.gearEff / C.wheelR;

export const accR = (p) => (p >= 75 ? 0 : (C.accDrive * (77 - p)) / 76); // M2 bridges it from 75 (§ 8.4)
// (a stage's contactor closes over one position: the relay holds the current there, where the real one hunts; a
// step would make the bar flicker)
const stage = (p, at) => Math.max(0, Math.min(1, p - at));
export function field(p) {
  let phi = 1, was = 1;
  for (let i = C.fieldStages.length - 1; i >= 0; i--) { const [q, f] = C.fieldStages[i]; phi += (f - was) * stage(p, q); was = f; }
  return phi;
}

// The field of the brake loops at position p. F1 and F3 hang on the accelerator's contacts alone (ZR6, ZR5: T3SU-24 p. 8),
// so they shunt 4M+3M in the loops too, from 85 and 90; F4 and the drive's F2 need M2, which is out. In coasting F2 shunts
// 1M+2M so that "the accelerator's resistance is enough" at speed (p. 9); the brake pedal opens it. The loops are
// crossed, each group's armature feeding the other's field through the one accelerator, so in the excitation they count
// as the harmonic mean of the two fields [calc].
export function loopField(p, coasting) {
  const a = coasting ? C.shunt.f2 : 1;
  const b = 1 + (C.shunt.first - 1) * stage(p, 85) + (C.shunt.second - C.shunt.first) * stage(p, 90);
  return (2 * a * b) / (a + b);
}
export const brakeR = (p) => (C.accBrake * (p - 1)) / 98;

// the car's current in the brake loops at position p: a group's EMF drives its own and the shared resistance (the
// accelerator carries both groups, as in drive), E = Im·(Rm + Rloop + R(p)). E grows with Im less and less, so one root; it
// collapses towards the remanence's trickle below the speed where the flux per ampere no longer reaches that resistance.
export function loopCurrent(v, p, phi) {
  const n = Math.abs(v) * RPM;
  if (n < 1) return 0;
  const R = C.rMotor + C.rLoop + brakeR(p);
  let lo = 0, hi = 390;
  for (let i = 0; i < 20; i++) {
    const Im = (lo + hi) / 2;
    if (emf(Im, n, phi) - Im * R > 0) lo = Im; else hi = Im;
  }
  return lo + hi; // (2 · the mid-point: two groups)
}

// the step a pedal angle is on (0 below the first)
export function stepOf(angle, angles) { let s = 0; for (let i = 0; i < angles.length; i++) if (angle >= angles[i]) s = i + 1; return s; }

export class TR37 {
  constructor(cars = 1) {
    this.cars = cars;
    this.kind = 'pedals';  // which controls and HUD (src/hud.js pedal bar)
    this.mode = 'arcade';  // 'arcade': the lever and the helper; 'advanced': the pedals as they are
    this.lever = 0;        // arcade: −5…+5 steps, −6 the emergency stop
    this.pedal = { drive: 0, brake: 0 }; // degrees
    this.goal = null;      // { drive, brake }: where setStep sends the pedals, reached at footRate
    this.parked = true;    // the brake pedal in its ratchet (the car starts at a stop)
    this.p = C.pMin;       // accelerator position 1…99
    this.mg = new MotorGenerator();
    this.aux = new AuxBus();
    this.mg.settle(C.lineVoltage, 26 * 25);
    this.sn = true;        // SN: the motor-generator's current holds it (T3SU-24 § 2.1): no fans, no traction
    this.Iset = 0;         // A: what the relay holds now
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
  // ZR1: the accelerator's positions 1–80, fed through BK9 (brake pedal 0–2) or ZR10 (positions 3–99) (§ 8.2)
  get lamps() { return { acc: this.p < 80 && (this.brakeAngle < C.br1Angle || this.p >= 3), shoe: this.shoe > 0 }; }
  get drawing() { return this.ls; } // traction current through the pantograph
  // the switch button: drive off and the accelerator at 1–30 (M1's rest contact and ZR9, § 8.2)
  get buttonLive() { return !this.ls && this.p <= 30; }
  // a step's force standing to the end of the resistors (N), for the autopilot's choice
  driveForce(step) { return tractive(C.driveCurrent[step - 1] / 2, 1) * this.cars; }
  // … and a brake step's at this speed: what the relay can hold between the two ends of the accelerator (N)
  brakeForce(step, v = 10) {
    const low = loopCurrent(v, C.pMin, 1), high = loopCurrent(v, 99, loopField(99, false));
    return braking(Math.max(high, Math.min(low, C.brakeCurrent[step - 1]))) * this.cars;
  }
  // a setting on coil RC's 24 V (T3SU-26 p. 4)
  _setting(table, step) { return table[step - 1] + (26 - this.aux.U) * C.rcShift[step - 1]; }
  // the pilot motor's turn in dt for current I against setting: dir +1 where a low current wants a higher position (drive),
  // −1 where it wants a lower one (the brake loops). The rate follows the 24 V side (T3SU-17 p. 5 sets 5 s at 24 V).
  _relay(I, set, dir, dt) {
    const [lo, hi] = C.relayBand, e = I < set * lo ? (set * lo - I) / set : I > set * hi ? -(I - set * hi) / set : 0;
    if (!e) return 0;
    return Math.sign(e) * dir * C.accRate * (this.aux.U / 24) * Math.min(1, Math.abs(e) / C.relayPulse) * dt;
  }

  // ------------------------------------------------------------------ the driver's controls
  // advanced: a tap moves to the next step's angle along one axis from full brake (−) to full drive (+);
  // the brake stops at step 5 (parking and the track brakes take their own action)
  tap(dir) {
    const P = this.pedal, B5 = C.brakeAngles[4];
    this.goal = null;
    if (dir > 0) {
      if (P.brake > 0) P.brake = [0, ...C.brakeAngles].filter((a) => a < P.brake - 0.01).pop() ?? 0;
      else if (!this.parked) P.drive = C.driveAngles.find((a) => a > P.drive + 0.01) ?? C.pedalMax;
    } else if (P.drive > 0) P.drive = [0, ...C.driveAngles].filter((a) => a < P.drive - 0.01).pop() ?? 0;
    else P.brake = Math.max(P.brake, C.brakeAngles.find((a) => a > P.brake + 0.01) ?? B5);
  }
  // … and held: the pedal moves on at 20°/s; the brake stops at step 5 unless it is already deeper
  hold(dir, dt) {
    const P = this.pedal, d = C.pedalRate * dt, B5 = C.brakeAngles[4];
    this.goal = null;
    if (dir > 0) { if (P.brake > 0) P.brake = Math.max(0, P.brake - d); else if (!this.parked) P.drive = Math.min(C.pedalMax, P.drive + d); }
    else if (P.drive > 0) P.drive = Math.max(0, P.drive - d);
    else if (P.brake < B5) P.brake = Math.min(B5, P.brake + d);
  }
  // a number key: drive step n (n > 0), brake step −n, or both pedals released (0); −6 the emergency stop
  // (a foot takes its time: going for brake step 5 the loops have ≈0.5 s to build their current past LO's 120 A; off one
  // pedal before the other; the pedal to the floor at once)
  setStep(n) {
    const P = this.pedal;
    if (n > 0) { if (this.parked) return; this.goal = { drive: C.driveAngles[n - 1] + 1, brake: 0 }; }
    else if (n <= -6) { P.drive = 0; P.brake = C.pedalMax; this.goal = null; }
    else if (n < 0) this.goal = { drive: 0, brake: C.brakeAngles[-n - 1] + 0.5 };
    else this.goal = { drive: 0, brake: 0 };
  }
  _foot(dt) {
    const g = this.goal, P = this.pedal;
    if (!g) return;
    const d = C.footRate * dt;
    if (P.brake > g.brake || g.brake === 0) P.brake += Math.max(-d * 2, g.brake - P.brake);
    if (P.drive > g.drive || g.drive === 0) P.drive += Math.max(-d * 2, g.drive - P.drive);
    if (g.brake > P.brake && P.drive === 0) P.brake = Math.min(g.brake, P.brake + d);
    if (g.drive > P.drive && P.brake === 0) P.drive = Math.min(g.drive, P.drive + d);
    if (P.brake === g.brake && P.drive === g.drive) this.goal = null;
  }
  // the ratchet: press to the station position and tip the plate; tipped back, the springs return it to 0
  park(on = !this.parked) {
    this.parked = on;
    this.goal = null;
    if (on) this.pedal.drive = 0;
    else this.pedal.brake = 0;
  }

  // arcade: the lever's step on the pedals, with what a driver does without thinking: off one pedal before
  // the other, parked whenever the car stands without drive, unparked to drive
  _arcade(doorsOpen, v) {
    const L = this.lever;
    if (L !== this.leverWas) { this.leverWas = L; if (L <= 0 || !doorsOpen) { if (L > 0 && this.parked) this.parked = false; this.setStep(L > 0 ? L : L <= -6 ? -6 : L); } }
    if (L > 0 && !doorsOpen) {
      if (this.parked) { this.parked = false; this.setStep(L); }
      if (this.pedal.drive === 0 && !this.goal) this.setStep(L);
    } else if (L <= 0) {
      if (Math.abs(v) < 0.1) this.parked = true;
    } else { this.pedal.drive = 0; if (this.goal?.drive) this.goal = null; if (Math.abs(v) < 0.1) this.parked = true; }
  }

  // the autopilot's wish on the pedals, as a careful driver: want = { force (N, + drive / − brake), stand (stop and
  // stay), coast, power (true: current through the pantograph, false: none), urgent, v, dt, slip, slide, stopDist (m to
  // the stop point, or null), noDrive (braking for a stop: the drive pedal stays off), fixed (that point stays where it
  // is), aNeed (m/s² still needed to end there), aCoast (m/s² it slows by itself), inertia (kg), grade, speedErr (m/s over
  // the speed to hold, null when not holding one) }.
  // Stands parked; one step at a time unless urgent; drives as T3SU-03 p. 4 asks ("zpravidla" steps 1–3 on the level, more only
  // at speed or uphill, a step back before letting go), coasts 2.5 s between drive and brake unless urgent ([ckd03] p. 11).
  autoDrive(w) {
    this.mode = 'advanced';
    const A = this.auto, v = Math.abs(w.v), now = A.step;
    A.hold -= w.dt;
    if (w.stand && v < 0.05) { if (!this.parked) this.park(true); A.step = -5; return; }
    if (!w.stand && this.parked) this.park(false);
    const pick = (f, force) => { for (let k = 1; k <= 5; k++) if (force(k) >= f) return k; return 5; };
    const F = (k) => this.brakeForce(k, v);
    let s;
    if (w.stand) s = Math.min(-3, -pick(-w.force, F));
    else if (w.coast) s = 0;
    else if (w.force > 0) s = pick(w.force, (k) => this.driveForce(k));
    else {
      // a brake step stays while it is about right: on the way in it would otherwise come and go, the force asked for
      // falling as soon as a step gives more than it (main let go and pressed again ≈5 times per stop)
      const f = -w.force, on = now < 0 ? -now : 0;
      if (on === 0) s = f >= 0.7 * F(1) ? -pick(f, F) : 0;
      else if (f > F(on) * 1.08) s = -pick(f, F);
      else if (on > 1 && f < F(on - 1) * 0.92) s = -(on - 1);
      else if (on === 1 && f < 0.4 * F(1)) s = 0;
      else s = now;
    }
    // holding a speed a step stays until the speed has moved, and so does nothing: the relay holds the force, and between
    // two steps' forces (a gradient) it let go and pressed every 2 s (main: 130–200 pedal changes a km). The plan's speed is
    // 0.6 m/s under the limit, so these bands stay under it.
    if (w.speedErr != null && !w.urgent && s !== now) {
      const e = w.speedErr;
      if (now < 0 && s > now && e > -0.7) s = now;
      else if (now < 0 && s < now && e < 0.3) s = now;
      else if (now > 0 && s >= 0 && e < 0.2 && e > -0.7) s = now;
      else if (now === 0 && s > 0 && e > -0.6 && v > 1) s = 0;
      else if (now === 0 && s < 0 && e < 0.25) s = 0;
    }
    if (w.power === true) s = Math.max(1, s);
    if (w.power === false) s = Math.min(0, s);
    if (w.noDrive) s = Math.min(0, s);
    if (w.slip && s > 1) s--;
    if (w.slide && s < -1) s++;
    // right after drive the brake loops are not excited yet: steps 1–4 only build more slowly, step 5 would
    // drop LO and bring the shoes in at speed, so step 4 at most until they settle; after braking, coast
    // before driving again ([ckd03] p. 11). (From a stand the loops are not the question.)
    if (!w.urgent && v > 2) {
      if (s < -4 && (this.ls || this.coastT < C.coastSettle)) s = -4;
      if (s > 0 && this.brakeT < C.coastSettle) s = 0;
    }
    if (w.fixed && w.aNeed != null && s < 0 && v < 1.6 && !w.stand && !w.urgent) {
      // the last metres to a stop or a signal. The electric brake is out below ≈6 km/h; from step 3 on it hands over to the
      // shoes, partly (BR1 at position 3) or fully on step 5 (LO), and partly is as far as they let go again without the
      // drive pedal: so not before that alone is what it takes, until then rolling.
      const a1 = (C.shoeForce[1] * this.cars) / w.inertia + Math.max(0, w.aCoast);
      if (w.aNeed > a1 * 1.3) s = -5;
      else if (w.aNeed >= a1 * 0.9 || this.shoe > 0) s = -3;
      else s = 0;
    } else if (s < 0 && v < 2.5 && !w.fixed) {
      // behind something that moves: at a crawl (below ≈9 km/h) steps 1–2 fade out to nothing and steps 3–4 leave only the
      // shoes partly applied (≈0.5 m/s², less than a downhill grade takes): a stop point within 8 m or needing more than
      // 0.15 m/s² gets step 5, so LO hands over to the full shoes, as a driver does (it overran stops by 1–4 m
      // and red signals at 0.8 km/h on step 3–4: #241's checks)
      const need = w.stopDist == null ? 0 : (w.v * w.v) / (2 * Math.max(0.3, w.stopDist));
      s = need > 0.15 || (w.stopDist != null && w.stopDist < 8) ? -5 : Math.min(s, -3);
    }
    // a stop the service brake (≈1.3 m/s² on step 5) cannot make: the pedal to the floor, the track brakes
    // with it, as a driver does for a signal turning red too close (line 17 seed 3: red 36 m ahead at
    // 38 km/h, 1.6 m/s² needed; the old force model braked 1.8 m/s²); let go once it is in hand
    if (w.stopDist != null && v > 2) {
      const need = (w.v * w.v) / (2 * Math.max(0.5, w.stopDist));
      if (need > 1.15 || (now === -6 && need > 0.6)) s = -6;
    }
    const contact = w.power != null;
    if (!w.urgent && !contact && s !== -6) {
      // from the lever's "nothing" a careful foot: brake and drive one step at a time; off a high drive step through a lower one
      if (s < 0 && now <= 0 && s < now - 1) s = now - 1;
      if (s > 0 && now >= 0 && s > now + 1) s = now + 1;
      // (T3SU-03 p. 4: on the level steps 1–3, more only at speed or uphill)
      if (s > 3 && v < 25 / 3.6 && Math.abs(w.grade || 0) < 0.02) s = 3;
      if (now >= 3 && s <= 0) s = 1;
    }
    if (s !== now && (A.hold <= 0 || w.urgent || contact)) {
      A.step = s;
      // (a brake step comes on after 0.3 s, comes off after 0.8 s; drive 0.6 s)
      A.hold = s < now && s < 0 ? 0.3 : s < 0 ? 0.8 : 0.6;
      this.setStep(s);
    }
  }

  // ------------------------------------------------------------------ one step
  // ctx: { v, voltage, doorsOpen, rescue, forcedStop } → { drive, brake (wheel: electric + shoes), track
  // (magnet pairs), current (A, the ammeter, negative braking), line (A drawn from the line, all cars),
  // dissipated (W in the resistors) }
  update(dt, { v = 0, voltage = C.lineVoltage, doorsOpen = false, rescue = false, forcedStop = false } = {}) {
    if (this.mode === 'arcade') this._arcade(doorsOpen, v);
    this._foot(dt);
    const k = this.cars, speed = Math.abs(v);
    const b = this.brakeAngle, d = this.pedal.drive;
    this.brakeT = b >= C.brakeOff ? 0 : this.brakeT + dt;

    // the line contactor LS: brake pedal at 0 (BK2), drive ≥ step 1 (JK1, then R2 holds it down to the
    // pre-step), doors closed (DBR), the maximum relay not tripped, the safety relay RB up
    if (this.mr && d < C.driveHold) this.mr = false;
    this.sn = this.mg.i > 2;
    const allowed = b < C.brakeOff && !doorsOpen && !this.mr && !rescue && !forcedStop && this.sn;
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
      const set = this.Iset = this._setting(C.driveCurrent, Math.max(1, this.driveStep));
      // the limiting relay turns the accelerator on below the setting, back above it; the pilot motor
      // stops at 97 and the cross coasts on to 99, where the pedal no longer matters until it is back at 0
      if (this.p < 97 && this.relT < 0) {
        this.p = Math.max(1, Math.min(99, this.p + this._relay(I, set, 1, dt)));
        if (this.p >= 97) this.p = 99;
      }
      if (I > C.maxRelay) { this.mr = true; this.ls = false; }
      fDrive = tractive(Im, phi) * k;
    } else {
      // the brake loops: the relay holds the preparation current coasting (its coil CP; T3SU-24 § 4.2) and the step's
      // current braking (§ 4.3) by turning the accelerator, down for more current, up for less. After drive it stands
      // far above what the loops need, and they do not excite until it is back: the 2–3 s of coasting ČKD asks for,
      // and with the pedal already at step 5 LO drops meanwhile and the shoes come in at speed ([ckd03] p. 11).
      const bs = this.brakeStep, on = b >= C.brakeOff;
      const set = this.Iset = on && bs ? this._setting(C.brakeCurrent, bs) : C.prepCurrent;
      const phi = loopField(this.p, !on), closed = this.coastT >= C.loopDelay, Ieq = closed ? loopCurrent(speed, this.p, phi) : 0;
      if (closed) this.p = Math.max(C.pMin, Math.min(99, this.p + this._relay(Ieq, set, -1, dt)));
      this.Ib += (Ieq - this.Ib) * Math.min(1, dt / C.loopLag);
      I = -this.Ib;
      fElec = braking(this.Ib, phi) * k;
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
    if (!this.ls && b >= C.br1Angle && this.p < 3) this.shoe = Math.max(this.shoe, 1); // (ZR10, closed at 3–99: T3SU-24 p. 14)
    const shoeT = C.shoeForce[this.shoe] * k;
    // (the springs apply in ≈0.3 s, the magnets release in ≈0.5 s [assumed]: slower, the fade left 1–2 m of
    // weak braking at 3.5–5 km/h and the autopilot overran stops, #241's check)
    // (the same 0.3 s partly or fully: stage 1 came in at 5 m/s³ otherwise)
    this.shoeF += Math.max(-60000 * k * dt, Math.min(((C.shoeForce[this.shoe] * k) / 0.3) * dt, shoeT - this.shoeF));

    // the tractive force builds with the motors' inductance (≈0.15 s)
    this.drive += (fDrive - this.drive) * Math.min(1, dt / 0.15);
    const track = rescue || b >= C.trackAngles[1] ? 2 : b >= C.trackAngles[0] ? 1 : 0;

    // the 24 V side: control 20 A with the lamps, 8 A more with the power contactors in [assumed]; the shoe brakes' four
    // release magnets, 2.7 Ω each, in full through BR1 and through RČ partly (T3SU-05 p. 3); the track brakes' magnets, 0.632 Ω
    const U = this.aux.U;
    const magnets = this.shoe === 0 ? (4 * U) / 2.7 : this.shoe === 1 ? (4 * U) / (2.7 * 3.3) : 0;
    const demand = 20 + (this.ls ? 8 : 0) + magnets + (track * 2 * U) / 0.632;
    this.aux.update(dt, this.mg.rpm, demand);
    this.mg.update(dt, voltage, this.aux.U * this.aux.dynamoA);

    return {
      drive: this.drive, brake: fElec + this.shoeF, track: track * C.trackForce * k, trackOn: track > 0, trackPairs: track,
      current: I, line: this.ls ? I * k : 0, dissipated: fElec * speed, auxLine: this.mg.i * k,
    };
  }
}
