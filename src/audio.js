// SPDX-License-Identifier: AGPL-3.0-or-later
// The tram's sounds (Web Audio). The game raises named events and sets parameters; the loops follow the parameters.
// A sound pack (#528; docs/vehicles.md, Sound packs) gives an event a recording (or a list, one picked at random)
// and a loop a recording pitched by its parameter; every event and loop it leaves out keeps the built-in sound,
// synthesised here: traction motor whine, rolling noise, rail joints, the frogs, flange squeal, the T3 bell, door
// buzzer and the clicks of the controller, the contactors and the relays.
import { T3, CAR_PITCH } from './tram.js';

// The events the game raises (one entry a line: tools/sound_lists.py writes them into docs/vehicles.md).
export const EVENTS = {
  'door.open': 'the doors start opening (their clip starts)',
  'door.close': 'the doors start closing (their clip starts)',
  'door.buzzer': 'the door alert before the doors close',
  'bell': 'the main bell',
  'joint': 'a bogie over a rail joint (every 18 m)',
  'points': 'an axle over a switch\'s frog',
  'crossing': 'an axle over a rail of a diamond crossing',
  'notch.up': 'the controller moved to a higher command',
  'notch.down': 'the controller moved to a lower command',
  'lineContactor': 'the line contactor closes or opens',
  'contactor': 'a field-weakening stage of the accelerator',
  'trackBrake.on': 'the track brakes\' magnets drop',
  'trackBrake.off': 'the track brakes\' magnets lift',
  'indicator.tick': 'the indicators\' relay, lamps on',
  'indicator.tock': 'the indicators\' relay, lamps off',
  'switch.radio': 'a switch set by the radio control (IRC)',
  'switch.contact': 'a switch set by the overhead contact',
  'switch.iron': 'a switch set by hand with the switch iron',
  'heating': 'a heating switch',
  'warning': 'the cab\'s warning beep',
  'crash': 'a collision',
};
// The loops a pack may replace and the parameter that pitches each (its reference: `refSpeed` m/s or `refRpm`).
export const LOOPS = {
  'motor': 'traction motors and gears: pitched by speed, loud by the motor current',
  'rolling': 'rolling noise: pitched and loud by speed',
  'flange': 'flange squeal in curves under 20 m radius and on sliding wheels: not pitched',
  'mg': 'the motor-generator and its fans: pitched by mgRpm',
};
// The parameters the loops follow (TramAudio.params).
export const PARAMS = {
  'speed': 'm/s',
  'motorCurrent': 'A',
  'curveRadius': 'm (the curve\'s speed limit standing in for it: under 20 m radius squeals)',
  'mgRpm': 'rpm',
  'slide': '0/1: wheels locked and sliding',
  'trackBrake': '0/1: the track brakes on',
};
// a loop's built-in loudness at its loudest (the synthesis below): a pack's recording plays at its share of it
const LOOP_MAX = { motor: 0.145, rolling: 0.4, flange: 0.07, mg: 0.05 };
// a T3 set's axles behind its front, m (src/tram.js T3: the pivots 6.4 m apart, a bogie's wheelbase 1.9 m)
const WHEELBASE = 1.9;
export const axlesBehind = (cars) => Array.from({ length: cars }, (_, k) => k * CAR_PITCH + T3.length / 2)
  .flatMap((c) => [c - T3.bogies / 2, c + T3.bogies / 2]).flatMap((p) => [p - WHEELBASE / 2, p + WHEELBASE / 2]);
// a diamond crossing's two rails of the other track, either side of where the data puts it (the angle is not known)
const RAILS = [-0.7175, 0.7175];

export class TramAudio {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this.active = false;
    this.finishing = false;
    this.epoch = 0;
    this.lastJoint = 0;
    this.pack = null;      // the sound pack in use: { events: Map(event -> [AudioBuffer]), loops: { name: {...} } }
    this.frogs = [];       // [{ s, e: 'points' | 'crossing' }] by s: the route's frogs (setTrack)
    this.params = {};
    this.trace = null;     // an array to log each event into ({ e, by, s, x }: a test's)
  }

  start() {
    if (this.ctx) return;
    const ctx = (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
    this.master = ctx.createGain();
    this.master.gain.value = this.active && !this.muted ? 0.6 : 0;
    this.master.connect(ctx.destination);

    // noise buffer shared by several voices
    const len = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;

    // traction motors: two detuned saws + gear harmonic through a lowpass
    this.motorGain = ctx.createGain();
    this.motorGain.gain.value = 0;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 1400;
    lp.Q.value = 2;
    this.motorFilter = lp;
    this.motorOsc = [0, 1, 2].map((i) => {
      const o = ctx.createOscillator();
      o.type = i === 2 ? 'sine' : 'sawtooth';
      o.frequency.value = 50;
      const g = ctx.createGain();
      g.gain.value = i === 2 ? 0.6 : 0.35;
      o.connect(g).connect(lp);
      o.start();
      return o;
    });
    // (each loop's voices through an output a pack's recording mutes: _synth)
    [this.motorOut, this.rollOut, this.squealOut, this.mgOut] = [0, 1, 2, 3].map(() => { const g = ctx.createGain(); g.connect(this.master); return g; });
    lp.connect(this.motorGain).connect(this.motorOut);

    // rolling noise
    this.rollGain = ctx.createGain();
    this.rollGain.gain.value = 0;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    src.loop = true;
    this.rollFilter = ctx.createBiquadFilter();
    this.rollFilter.type = 'bandpass';
    this.rollFilter.frequency.value = 300;
    this.rollFilter.Q.value = 0.7;
    src.connect(this.rollFilter).connect(this.rollGain).connect(this.rollOut);
    src.start();

    // the motor-generator and its two fans (src/electric.js): always running, its speed following the wire, so its
    // tone falls when the tram draws current. A hum at twice the shaft speed, the blades' tone, the air.
    this.mgGain = ctx.createGain();
    this.mgGain.gain.value = 0.05;
    this.mgGain.connect(this.mgOut);
    this.mgOsc = [['triangle', 0.5], ['sawtooth', 0.12]].map(([type, level]) => {
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = type;
      o.frequency.value = 60;
      g.gain.value = level;
      o.connect(g).connect(this.mgGain);
      o.start();
      return o;
    });
    const air = ctx.createBufferSource();
    air.buffer = this.noise;
    air.loop = true;
    this.mgAir = ctx.createBiquadFilter();
    this.mgAir.type = 'bandpass';
    this.mgAir.frequency.value = 700;
    this.mgAir.Q.value = 1.2;
    const airGain = ctx.createGain();
    airGain.gain.value = 0.7;
    air.connect(this.mgAir).connect(airGain).connect(this.mgGain);
    air.start();
    // the accelerator's pilot motor and worm gear, whenever the cross turns
    this.pilotGain = ctx.createGain();
    this.pilotGain.gain.value = 0;
    this.pilotOsc = ctx.createOscillator();
    this.pilotOsc.type = 'sawtooth';
    this.pilotOsc.frequency.value = 300;
    const pilotLp = ctx.createBiquadFilter();
    pilotLp.type = 'lowpass';
    pilotLp.frequency.value = 1100;
    this.pilotOsc.connect(pilotLp).connect(this.pilotGain).connect(this.master);
    this.pilotOsc.start();

    // flange squeal in tight curves
    this.squealGain = ctx.createGain();
    this.squealGain.gain.value = 0;
    this.squeal = ctx.createOscillator();
    this.squeal.type = 'sine';
    this.squeal.frequency.value = 2900;
    const sq2 = ctx.createOscillator();
    sq2.frequency.value = 3170;
    const sqg = ctx.createGain();
    sqg.gain.value = 0.5;
    this.squeal.connect(this.squealGain);
    sq2.connect(sqg).connect(this.squealGain);
    this.squealGain.connect(this.squealOut);
    this.squeal.start();
    sq2.start();
  }

  setMuted(m) {
    if (this.muted === m) return;
    this.muted = m;
    this._fade(this.active && !m ? 0.6 : 0, 0.05);
  }

  // On finish, let an already-started crash play as the shift fades out. A pause or menu
  // transition mutes promptly; the separate preference remains unchanged.
  setActive(on, finishing = false) {
    if (this.active === on && this.finishing === finishing) return;
    if (this.active && !on) this.epoch++;
    this.active = on;
    this.finishing = finishing;
    this._fade(on && !this.muted ? 0.6 : 0, finishing && !this.muted ? 1.3 : 0.05);
  }

  _fade(target, seconds) {
    if (!this.master) return;
    const g = this.master.gain, t = this.ctx.currentTime;
    if (g.cancelAndHoldAtTime) g.cancelAndHoldAtTime(t);
    else { const value = g.value; g.cancelScheduledValues(t); g.setValueAtTime(value, t); }
    g.linearRampToValueAtTime(target, t + seconds);
  }

  update(tram, curvatureLimit, dt) {
    if (!this.ctx || !this.active) return;
    const t = this.ctx.currentTime;
    const v = Math.abs(tram.v);
    const load = Math.min(1, Math.abs(tram.current) / 450);
    // motor/gear frequency rises with wheel speed; spinning wheels race ahead of the tram
    const base = 38 + v * 24 + (tram.slip ? 90 + 40 * Math.sin(t * 9) : 0);
    this.motorOsc[0].frequency.setTargetAtTime(base, t, 0.05);
    this.motorOsc[1].frequency.setTargetAtTime(base * 1.505, t, 0.05);
    this.motorOsc[2].frequency.setTargetAtTime(base * 4.02, t, 0.05);
    this.motorFilter.frequency.setTargetAtTime(500 + v * 90 + load * 900, t, 0.1);
    const motor = v > 0.2 || tram.force > 100 ? 0.015 + load * 0.11 + Math.min(v / 18, 1) * 0.02 : 0;
    this.motorGain.gain.setTargetAtTime(motor, t, 0.08);
    this.rollFilter.frequency.setTargetAtTime(180 + v * 28, t, 0.1);
    this.rollGain.gain.setTargetAtTime(Math.min(0.32, v * 0.022), t, 0.1);
    let squeal = curvatureLimit <= 20 && v > 2.5 ? Math.min(0.03, (v - 2.5) * 0.008) : 0;
    if (tram.slide) squeal = 0.07; // locked wheels grinding on the rail
    this.squealGain.gain.setTargetAtTime(squeal, t, tram.slide ? 0.03 : 0.2);
    this.squeal.frequency.setTargetAtTime(tram.slide ? 1900 : 2900, t, 0.05);
    if (tram.trackBrake) this.rollGain.gain.setTargetAtTime(0.4, t, 0.05);

    const eq = tram.eq;
    if (eq.mg) {
      const f0 = eq.mg.rpm / 60; // (≈30 Hz)
      this.mgOsc[0].frequency.setTargetAtTime(Math.max(1, f0 * 2), t, 0.05);
      this.mgOsc[1].frequency.setTargetAtTime(Math.max(1, f0 * 12), t, 0.05); // (the impellers' blades)
      this.mgAir.frequency.setTargetAtTime(Math.max(50, f0 * 24), t, 0.05);
      this.mgGain.gain.setTargetAtTime(0.05 * Math.min(1, f0 / 25), t, 0.2);
      // the contactors: the line contactor's clunk, M2 and the four field stages as the cross passes them
      const moved = eq.p - (this.lastP ?? eq.p);
      this.lastP = eq.p;
      const rate = dt > 0 ? Math.abs(moved) / dt : 0;
      this.pilotGain.gain.setTargetAtTime(Math.min(0.012, rate * 0.0007), t, 0.04);
      this.pilotOsc.frequency.setTargetAtTime(150 + rate * 12, t, 0.05);
      if (eq.ls !== this.lastLs) { if (this.lastLs !== undefined) this.emit('lineContactor'); this.lastLs = eq.ls; }
      if (eq.ls) for (const q of [75, 80, 85, 90, 95]) if ((eq.p - q) * (eq.p - moved - q) < 0) this.emit('contactor');
      if (eq.shoe !== this.lastShoe) { if (this.lastShoe !== undefined) this.emit(eq.shoe ? 'trackBrake.on' : 'trackBrake.off'); this.lastShoe = eq.shoe; }
    }
    Object.assign(this.params, { speed: v, motorCurrent: Math.abs(tram.current), curveRadius: curvatureLimit, mgRpm: eq.mg?.rpm ?? 0,
      slide: tram.slide ? 1 : 0, trackBrake: tram.trackBrake ? 1 : 0 });
    this._loops(t, { motor, rolling: tram.trackBrake ? 0.4 : Math.min(0.32, v * 0.022), flange: squeal, mg: eq.mg ? 0.05 * Math.min(1, eq.mg.rpm / 60 / 25) : 0.05 });

    // rail joints every 18 m: a bogie "ta-dum"
    const joint = Math.floor(tram.s / 18);
    if (joint !== this.lastJoint && v > 1 && !tram.slide) {
      this.lastJoint = joint;
      const k = Math.min(v / 18, 1);
      this.emit('joint', { level: k, gain: 0.06 + k * 0.1, freq: 140 });
      const epoch = this.epoch;
      setTimeout(() => { if (epoch === this.epoch) this.emit('joint', { level: k, gain: 0.05 + k * 0.08, freq: 120 }); }, (2.0 / Math.max(v, 1)) * 1000);
    }
    // the frogs: each axle as it passes one, either way
    const last = this.lastS ?? tram.s;
    this.lastS = tram.s;
    if (tram.s !== last && v > 0.3 && this.frogs.length) {
      const lo = Math.min(last, tram.s), hi = Math.max(last, tram.s), k = Math.min(v / 12, 1);
      for (const a of axlesBehind(tram.cars || 1)) {
        for (const f of this.frogs) {
          const x = f.s + a;   // the front's s when this axle is on the frog
          if (x > lo && x <= hi) this.emit(f.e, { level: 0.4 + 0.6 * k, gain: 0.05 + k * 0.12, s: tram.s, x: f.s });
        }
      }
    }
  }

  // The route's frogs (src/game.js): a facing switch's `frog` m past its fork, a trailing one's before it, a diamond
  // crossing's two rails.
  setTrack({ switches = [], trailing = [], crossings = [] } = {}, frog = 11.5) {
    this.frogs = [...switches.map((w) => ({ s: w.s + (w.frog ?? frog), e: 'points' })),
      ...trailing.map((w) => ({ s: w.s - (w.frog ?? frog), e: 'points' })),
      ...crossings.flatMap((s) => RAILS.map((d) => ({ s: s + d, e: 'crossing' })))].sort((a, b) => a.s - b.s);
    this.lastS = undefined;
  }

  // An event: the pack's recording where it has one, else the built-in sound. o: { level 0..1 (a recording's
  // loudness), gain, freq (a click's), s, x (the trace's) }.
  emit(e, o = {}) {
    if (!this.ctx || !this.active) return;
    const files = this.pack?.events.get(e);
    if (files?.length) this._play(files[Math.floor(Math.random() * files.length)], o.level ?? 1);
    else BUILT_IN[e]?.(this, o);
    this.trace?.push({ e, by: files?.length ? 'pack' : 'built-in', s: o.s, x: o.x, t: this.ctx.currentTime });
  }

  _play(buffer, level) {
    const ctx = this.ctx, src = ctx.createBufferSource(), g = ctx.createGain();
    src.buffer = buffer;
    g.gain.value = level * (this.pack.gain ?? 1);
    src.connect(g).connect(this.master);
    src.start();
  }

  // A sound pack (src/vehicles.js soundsFor): its recordings fetched and decoded (url(path) their address); null, the
  // built-in sounds. Resolves when the pack plays.
  async usePack(pack, url = pack?.url ?? ((p) => p)) {
    if (!this.ctx) this.start();
    if ((this.pack?.id ?? null) === (pack?.id ?? null)) return;
    for (const l of Object.values(this.pack?.loops || {})) { l.src.stop(); l.out.disconnect(); }
    this.pack = null;
    for (const name of Object.keys(LOOPS)) this._synth(name, true);
    if (!pack) return;
    const ctx = this.ctx, cache = new Map();
    const decode = (p) => {
      if (!cache.has(p)) cache.set(p, fetch(url(p)).then((r) => r.arrayBuffer()).then((b) => ctx.decodeAudioData(b)));
      return cache.get(p);
    };
    const events = new Map();
    for (const [e, f] of Object.entries(pack.events || {})) events.set(e, await Promise.all([f].flat().map(decode)));
    const loops = {};
    for (const [name, l] of Object.entries(pack.loops || {})) {
      const src = ctx.createBufferSource(), out = ctx.createGain();
      src.buffer = await decode(l.file);
      src.loop = true;
      out.gain.value = 0;
      src.connect(out).connect(this.master);
      src.start();
      loops[name] = { ...l, src, out };
      this._synth(name, false);
    }
    this.pack = { id: pack.id, gain: pack.gain, events, loops };
  }

  // a built-in loop's voices on or off (a pack's recording plays in its place)
  _synth(name, on) {
    const node = { motor: this.motorOut, rolling: this.rollOut, flange: this.squealOut, mg: this.mgOut }[name];
    if (node) node.gain.value = on ? 1 : 0;
  }

  // the pack's loops: their loudness the built-in one's share of its loudest, their pitch their parameter over its
  // reference
  _loops(t, level) {
    const P = this.params;
    for (const [name, l] of Object.entries(this.pack?.loops || {})) {
      const rate = name === 'mg' ? P.mgRpm / (l.refRpm || 1800) : name === 'flange' ? 1 : P.speed / (l.refSpeed || 10);
      l.src.playbackRate.setTargetAtTime(Math.max(0.05, rate), t, 0.05);
      l.level = (level[name] / LOOP_MAX[name]) * (l.gain ?? 1);
      l.out.gain.setTargetAtTime(l.level, t, 0.08);
    }
  }

  click(gain = 0.1, freq = 900) {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = freq;
    const g = ctx.createGain();
    g.gain.setValueAtTime(gain, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.08);
    src.connect(f).connect(g).connect(this.master);
    src.start(t, Math.random());
    src.stop(t + 0.1);
  }

  // T3 mechanical bell: two quick metallic strikes
  bell() {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx;
    for (const delay of [0, 0.16]) {
      const t = ctx.currentTime + delay;
      for (const [f, a] of [[1180, 0.25], [2650, 0.14], [4120, 0.08], [5400, 0.04]]) {
        const o = ctx.createOscillator();
        o.frequency.value = f;
        const g = ctx.createGain();
        g.gain.setValueAtTime(a, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + 0.9);
        o.connect(g).connect(this.master);
        o.start(t);
        o.stop(t + 1);
      }
    }
  }

  // door closing buzzer + pneumatic hiss
  doors(closing) {
    if (closing) this.buzzer();
    this.doorHiss(closing ? 1.3 : 0);
  }
  buzzer() {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = 'square';
    o.frequency.value = 620;
    const g = ctx.createGain();
    g.gain.value = 0;
    for (let i = 0; i < 6; i++) {
      g.gain.setValueAtTime(0.05, t + i * 0.25);
      g.gain.setValueAtTime(0, t + i * 0.25 + 0.15);
    }
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + 1.6);
  }
  // the doors' pneumatic hiss, `after` s from now
  doorHiss(after = 0) {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = 'highpass';
    f.frequency.value = 2500;
    const g = ctx.createGain();
    const start = t + after;
    g.gain.setValueAtTime(0, t);
    g.gain.setValueAtTime(0.12, start);
    g.gain.exponentialRampToValueAtTime(0.0001, start + 0.7);
    src.connect(f).connect(g).connect(this.master);
    src.start(t);
    src.stop(start + 0.8);
  }

  warning() {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const o = ctx.createOscillator();
    o.type = 'square';
    o.frequency.value = 880;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.06, t);
    g.gain.setValueAtTime(0, t + 0.12);
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + 0.15);
  }

  crash() {
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = 900;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.7, t);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 1.2);
    src.connect(f).connect(g).connect(this.master);
    src.start(t);
    src.stop(t + 1.3);
  }
}

// The built-in sounds by event (each as the game sounded before #528).
const click = (gain, freq) => (a, o) => a.click(o.gain ?? gain, o.freq ?? freq);
const BUILT_IN = {
  'door.open': (a) => a.doors(false),
  'door.close': (a) => a.doorHiss(1.3),      // (the hiss as the buzzer ends)
  'door.buzzer': (a) => a.buzzer(),
  'bell': (a) => a.bell(),
  'joint': click(0.1, 140),
  'points': click(0.12, 220),
  'crossing': click(0.12, 180),
  'notch.up': click(0.12, 1600),
  'notch.down': click(0.12, 1600),
  'lineContactor': click(0.12, 420),
  'contactor': click(0.05, 650),
  'trackBrake.on': click(0.1, 260),
  'trackBrake.off': click(0.1, 260),
  'indicator.tick': click(0.05, 1250),
  'indicator.tock': click(0.05, 950),
  'switch.radio': click(0.2, 2600),
  'switch.contact': click(0.25, 2000),
  'switch.iron': click(0.3, 400),
  'heating': click(0.15, 900),
  'warning': (a) => a.warning(),
  'crash': (a) => a.crash(),
};
