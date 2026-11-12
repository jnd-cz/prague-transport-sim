// SPDX-License-Identifier: AGPL-3.0-or-later
// Synthesised tram sounds (Web Audio): traction motor whine, rolling noise, rail joints,
// flange squeal, the T3 bell, door buzzer and controller clicks.

export class TramAudio {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this.active = false;
    this.finishing = false;
    this.epoch = 0;
    this.lastJoint = 0;
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
    lp.connect(this.motorGain).connect(this.master);

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
    src.connect(this.rollFilter).connect(this.rollGain).connect(this.master);
    src.start();

    // the motor-generator and its two fans (src/electric.js): always running, its speed following the wire, so its
    // tone falls when the tram draws current. A hum at twice the shaft speed, the blades' tone, the air.
    this.mgGain = ctx.createGain();
    this.mgGain.gain.value = 0.05;
    this.mgGain.connect(this.master);
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
    this.squealGain.connect(this.master);
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
      if (eq.ls !== this.lastLs) { if (this.lastLs !== undefined) this.click(0.12, 420); this.lastLs = eq.ls; }
      if (eq.ls) for (const q of [75, 80, 85, 90, 95]) if ((eq.p - q) * (eq.p - moved - q) < 0) this.click(0.05, 650);
      if (eq.shoe !== this.lastShoe) { if (this.lastShoe !== undefined) this.click(0.1, 260); this.lastShoe = eq.shoe; }
    }

    // rail joints every 18 m: a bogie "ta-dum"
    const joint = Math.floor(tram.s / 18);
    if (joint !== this.lastJoint && v > 1 && !tram.slide) {
      this.lastJoint = joint;
      this.click(0.06 + Math.min(v / 18, 1) * 0.1, 140);
      const epoch = this.epoch;
      setTimeout(() => { if (epoch === this.epoch) this.click(0.05 + Math.min(v / 18, 1) * 0.08, 120); }, (2.0 / Math.max(v, 1)) * 1000);
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
    if (!this.ctx || !this.active) return;
    const ctx = this.ctx, t = ctx.currentTime;
    if (closing) {
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
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = 'highpass';
    f.frequency.value = 2500;
    const g = ctx.createGain();
    const start = t + (closing ? 1.3 : 0);
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
