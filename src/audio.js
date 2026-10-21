// Synthesised tram sounds (Web Audio): traction motor whine, rolling noise, rail joints,
// flange squeal, the T3 bell, door buzzer and controller clicks.

export class TramAudio {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this.lastJoint = 0;
  }

  start() {
    if (this.ctx) return;
    const ctx = (this.ctx = new (window.AudioContext || window.webkitAudioContext)());
    this.master = ctx.createGain();
    this.master.gain.value = 0.6;
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
    this.muted = m;
    if (this.master) this.master.gain.value = m ? 0 : 0.6;
  }

  update(tram, curvatureLimit, dt) {
    if (!this.ctx) return;
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

    // rail joints every 18 m: a bogie "ta-dum"
    const joint = Math.floor(tram.s / 18);
    if (joint !== this.lastJoint && v > 1 && !tram.slide) {
      this.lastJoint = joint;
      this.click(0.06 + Math.min(v / 18, 1) * 0.1, 140);
      setTimeout(() => this.click(0.05 + Math.min(v / 18, 1) * 0.08, 120), (2.0 / Math.max(v, 1)) * 1000);
    }
  }

  click(gain = 0.1, freq = 900) {
    if (!this.ctx) return;
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
    if (!this.ctx) return;
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
    if (!this.ctx) return;
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
    if (!this.ctx) return;
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
    if (!this.ctx) return;
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
