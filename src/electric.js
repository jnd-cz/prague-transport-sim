// The T3's electric system outside the motors (#351, #355): the wire it runs under, and the motor-generator with
// its fans, dynamo, regulator and battery. Sources: raw/reference/ckd-t3su/ (T3SU-15 motor-generator, T3SU-23
// regulator, T3SU-13 battery, T3SU-05 shoe brakes, T3SU-24 § 2.1, T3SU-26), notes in
// docs/research/prazsketramvaje/t3-accelerator.md § 9. What no source gives is marked [assumed].
//
// The wire: every traction substation feeds the track nearest to it, and a tram's voltage falls with its own
// current and the other trams' on the same feed. The motor-generator is a series motor on the line, so its speed,
// and with it the fans' tone, follows the wire; the dynamo on its shaft is regulated to 26 V, so the 24 V side hardly
// does. Units: V, A, Ω, rad/s, W; everything here is one car's unless named otherwise.

export const WIRE = {
  u0: 650,        // V: a substation at no load [assumed; nominal 600 V, the T3 is built for 720 V, T3SU-15 p. 1]
  rSource: 0.03,  // Ω: the rectifier and its transformer [assumed, ≈6 % drop at 1,200 A]
  rWire: 0.10,    // Ω per km of track: contact wire 100 mm² Cu (0.18) with its neighbour track's and the rails [assumed]
  rFeeder: 0.06,  // Ω per km of underground feeder cable, from the substation to a section's feed point [assumed]
  wireKm: 0.8,    // km of wire at most from a feed point: sections of 1–2 km are fed about their middle [assumed]
  reach: 4,       // km: a substation further from this line's track does not feed it [assumed]
};

// Where each substation meets this line, and which feed a point of the track hangs on: the one with the least
// resistance to it (the real section ends are not known yet, #277: a tram crossing one sees the voltage step). The
// path is wire near the place and feeder cable beyond it: a section's feed point is not known either, only that the
// cable runs out to it.
const along = (m) => { const km = m / 1000; return WIRE.rWire * Math.min(km, WIRE.wireKm) + WIRE.rFeeder * Math.max(0, km - WIRE.wireKm); };

export class Feeding {
  constructor(route, substations, frameOrigin) {
    this.feeds = [];
    if (!substations?.length || !frameOrigin) return;
    const [e0, n0] = frameOrigin;
    for (const sub of substations) {
      const n = route.nearest(sub.e - e0, sub.n - n0);
      if (!n || n.d > WIRE.reach * 1000) continue;
      this.feeds.push({ s: n.s, ref: sub.ref, r0: WIRE.rSource + (WIRE.rFeeder * n.d) / 1000 });
    }
    this.feeds.sort((a, b) => a.s - b.s);
  }

  // the feed of route position s: { i, r (Ω to it) }; a line no substation reaches: null
  at(s) {
    let best = -1, r = Infinity;
    for (let i = 0; i < this.feeds.length; i++) {
      const f = this.feeds[i], q = f.r0 + along(Math.abs(s - f.s));
      if (q < r) { r = q; best = i; }
    }
    return best < 0 ? null : { i: best, r };
  }

  // what a tram at s sees: no-load voltage less what the others on its feed draw through the shared part, and its
  // own resistance. others: [{ s, i (A) }]. With no feed: the nominal wire.
  supply(s, others = []) {
    const me = this.at(s);
    if (!me) return { u0: 600, r: 0, ref: null };
    const f = this.feeds[me.i];
    let drop = 0, load = 0;
    for (const o of others) {
      const q = this.at(o.s);
      if (!q || q.i !== me.i) continue;
      load += o.i;
      // (the wire is shared only on the same side of the feed, as far as the nearer of the two)
      const same = (s - f.s) * (o.s - f.s) > 0;
      drop += o.i * (f.r0 + (same ? along(Math.min(Math.abs(s - f.s), Math.abs(o.s - f.s))) : 0));
    }
    return { u0: WIRE.u0 - drop, r: me.r, ref: f.ref, km: Math.abs(s - f.s) / 1000, others: load };
  }
}

// An AI tram's line current from what it does, for the wire [assumed: no equipment of its own]: on the resistors the
// step's current per car from its acceleration, on the motor curve its power, plus its motor-generator's.
export function aiLineCurrent(cars, v, a) {
  const k = cars || 2, base = 14 * k;
  if (a <= 0.05 && v > 1) return base + (k * 700 * v) / 500; // (holding speed: running resistance)
  if (a <= 0.05) return base;
  const onResistors = (220 + 150 * Math.min(1.8, a)) * k;
  const onCurve = (k * 18400 * a * v) / 500;
  return base + Math.min(onResistors, Math.max(onCurve, 120 * k));
}

export const MG = {
  // the series motor TMN 16 Ab: 600 V, 13 A, 5 kW, 1,750 rpm, 720 V and 2,500 rpm at most, its field 28 V at 13 A (T3SU-15 p. 2)
  r: 12,          // Ω in the circuit: RMG ≈4 (the sheet), field 2.15, armature ≈6 [assumed]
  k: 3.93,        // V·s/rad of flux at saturation, and …
  i0: 8,          // … the A at half of it: 2.43 at 13 A, so 444 V back-EMF at 1,750 rpm [from the rating]
  friction: 2,    // N·m [assumed]
  fan: 5.55e-4,   // N·m per (rad/s)²: the two fans, ≈3.4 kW at 1,750 rpm (the rest of the rated 5 kW) [assumed]
  inertia: 1.2,   // kg·m²: a 200 kg machine's rotor and two impellers [assumed]
  dynamoEff: 0.8, // [assumed]
};

// the dynamo TDN 16 Ab: 1.6 kW, 50 A, 70 A at 30 V at 1,500 rpm for 30 min (T3SU-15 p. 3); the regulator GC 11 holds
// 26 ± 0.5 V (T3SU-23 p. 1); the battery NKS 100: 17 NiCd cells of 1.2 V, 100 Ah, charged at 30 A (T3SU-13 p. 1)
export const AUX = {
  regulated: 26,
  emfAt1500: 32.1, // V at full field: 30 V + 70 A × rDynamo
  rDynamo: 0.03,   // Ω [assumed]
  iMax: 100,       // A: the regulator's fuse (T3SU-23 p. 1)
  cells: 17,
  cellV: [1.2, 1.3], // V, empty and full [assumed]
  rBattery: 0.03,  // Ω [assumed]
  ah: 100,
  charge: 30,      // A at most (T3SU-13 p. 1)
};

export class MotorGenerator {
  constructor() {
    this.w = 205;  // rad/s
    this.i = 12;   // A from the line
    this.dynW = 0;
  }

  get rpm() { return (this.w * 60) / (2 * Math.PI); }

  // the series motor's current at voltage U turning at w: U = I·R + K·I/(I + I0)·w, a quadratic in I
  current(U, w) {
    if (U < 1) return 0;
    const { r, k, i0 } = MG, b = U - r * i0 - k * w;
    return (b + Math.sqrt(b * b + 4 * r * U * i0)) / (2 * r);
  }

  update(dt, U, dynW) {
    const w = this.w, i = this.current(U, w);
    const T = (MG.k * i * i) / (i + MG.i0);
    const load = (w > 1 ? MG.friction : 0) + MG.fan * w * w + dynW / (MG.dynamoEff * Math.max(w, 30));
    this.w = Math.max(0, w + ((T - load) / MG.inertia) * dt);
    this.i = i;
    this.dynW = dynW;
  }

  // the steady state at voltage U, for a start with the machine already running
  settle(U, dynW) { for (let n = 0; n < 400; n++) this.update(0.1, U, dynW); }
}

// The 24 V side: dynamo through the regulator while it has the speed and the current, the battery otherwise.
export class AuxBus {
  constructor() {
    this.U = AUX.regulated;
    this.soc = 0.9;
    this.dynamoA = 0;
    this.batteryA = 0; // + charging
  }

  get ocv() { return AUX.cells * (AUX.cellV[0] + (AUX.cellV[1] - AUX.cellV[0]) * this.soc); }

  update(dt, rpm, demand) {
    const e = (AUX.emfAt1500 * rpm) / 1500, ocv = this.ocv;
    const charge = Math.min(AUX.charge, AUX.charge * (1 - this.soc) + 2);
    let U, id;
    const want = demand + charge;
    if (want <= AUX.iMax && e - want * AUX.rDynamo >= AUX.regulated) { U = AUX.regulated; id = want; }
    else {
      // the regulator at full field, or the dynamo at its limit: the battery shares the load through the diode
      const g = 1 / AUX.rDynamo + 1 / AUX.rBattery;
      U = Math.min(AUX.regulated, (e / AUX.rDynamo + ocv / AUX.rBattery - demand) / g);
      id = Math.max(0, (e - U) / AUX.rDynamo);
      if (id > AUX.iMax) { id = AUX.iMax; U = Math.min(AUX.regulated, ocv - (demand - id) * AUX.rBattery); }
      if (e <= U) { id = 0; U = Math.min(AUX.regulated, ocv - demand * AUX.rBattery); }
    }
    this.U = U;
    this.dynamoA = id;
    this.batteryA = id - demand;
    this.soc = Math.max(0, Math.min(1, this.soc + (this.batteryA * dt) / (AUX.ah * 3600)));
  }
}
