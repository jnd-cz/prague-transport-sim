// Gameplay: timetable, stops & passengers, doors, signals, switches, obstacles, scoring.
import * as THREE from 'three';
import { T3, ADHESION } from './tram.js';
import { Route } from './route.js';
import { t } from './i18n.js';
import {
  makeCar, makePerson, makeCrowd, makeTramSignal, makeSwitchIndicator, makeContactMarker,
  makeStopSign, makeSpeedSign, makeContactSign, makeRadioSwitchSign, makeGradientSign,
} from './models.js';

const DOOR_OPEN_TIME = 2.0, DOOR_CLOSE_TIME = 3.0;
const STOP_AHEAD = 6;          // tram front stops this far past the projected platform point
// The platform is 30 m long: any front position that puts the 14 m car alongside it counts.
// Stopping within 3 m of the sign earns a bonus; overshooting > 4 m is served but penalised.
const STOP_TOL_BEHIND = 20, STOP_TOL_AHEAD = 12;

function rng(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

// Passenger demand by time of day (weekday): morning and afternoon peaks, quiet nights.
const DEMAND = [[0, 0.3], [5, 0.35], [6, 1.0], [7, 2.2], [8.5, 2.3], [9.5, 1.3], [11, 1.0], [14, 1.3],
  [15.5, 2.0], [17.5, 2.0], [19, 1.1], [21, 0.7], [23, 0.4], [24, 0.3]];
export function demandAt(sec) {
  const h = ((sec / 3600) % 24 + 24) % 24;
  for (let i = 1; i < DEMAND.length; i++) {
    const [h1, v1] = DEMAND[i], [h0, v0] = DEMAND[i - 1];
    if (h <= h1) return v0 + ((v1 - v0) * (h - h0)) / (h1 - h0);
  }
  return 0.3;
}

export const fmtTime = (sec) => {
  sec = ((Math.floor(sec) % 86400) + 86400) % 86400;
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};
export const fmtDev = (d) => {
  const sign = d < 0 ? '−' : '+';
  d = Math.abs(Math.round(d));
  return `${sign}${Math.floor(d / 60)}:${String(d % 60).padStart(2, '0')}`;
};

// Place an object at route position s with lateral offset, facing direction of travel
// (or facing the tram when `faceBack`).
function place(obj, route, s, lateral, h = 0, faceBack = false) {
  const o = route.offset(s, lateral);
  obj.position.set(o.x, h + route.ground.atRoute(s, lateral), -o.y);
  const fx = faceBack ? -o.hx : o.hx, fy = faceBack ? -o.hy : o.hy;
  obj.rotation.y = Math.atan2(fx, -fy);
}

export class Game {
  constructor(scene, data, route, tram, audio, opts) {
    this.scene = scene;
    this.data = data;
    this.route = route;
    this.tram = tram;
    this.audio = audio;
    this.opts = opts;
    this.rand = rng(opts.seed ?? 12345);
    this.messages = [];
    this.score = 0;
    this.penalties = {};
    this.log = [];
    this.finished = false;
    this.paused = false;

    this.trip = data.timetable[opts.tripIndex];
    this.clock = this.trip[opts.startStop] - 40;
    this.doorState = 'open';
    this.doorTimer = 0;
    this.doorsMovingFlag = false;
    this.overspeedAcc = 0;
    this.comfortAcc = 0;
    this.deadmanHeld = false;
    this.deadmanTimer = 0;
    this.action = null; // { label, t, done }
    this.holdTimer = 0;
    this.objects = new THREE.Group();
    scene.add(this.objects);

    this.profile = route.ground.profile;
    this.weather = opts.weather || 'dry';
    this.flatFlag = false;
    this.rollFlag = false;

    this.backRoute = data.pathBack?.length > 1 ? new Route(data.pathBack) : null;
    this.backRoute && (this.backRoute.ground = route.ground);
    this._initStops();
    this._initSignals();
    this._initSwitches();
    this._initObstacles();
    this._initAdhesion();
    // restrictions: switches, and steep descents (Prague limits trams on long steep gradients)
    const extra = this.switches.map((w) => ({ from: w.s - 4, to: w.s + 14, v: w.routeDiverging ? 15 : 30 }));
    for (let s = 0; s < route.length; s += 10) {
      const g = this.profile.grade(s);
      if (g < -0.06) extra.push({ from: s - 10, to: s + 10, v: 25 });
      else if (g < -0.045) extra.push({ from: s - 10, to: s + 10, v: 35 });
    }
    this.limits = route.speedLimits(extra);
    this._initSigns();
    this.aiTrams = []; // same-direction trams ahead, kept up to date by the traffic module

    const st = this.stops[opts.startStop];
    tram.s = st.target;
    tram.passengers = Math.min(T3.crushCapacity, Math.floor((10 + this.rand() * 25) * demandAt(this.clock)));
    this.nextStop = opts.startStop;
    st.arrived = true;
    st.arriveClock = this.clock;
  }

  // ------------------------------------------------------------------ setup
  _initStops() {
    const r = this.rand;
    const n = this.data.stops.length;
    this.stops = this.data.stops.map((s, i) => {
      const central = i > n * 0.25 && i < n * 0.7 ? 1 : 0;
      const request = !!s.request;
      const demand = demandAt(this.trip[i]); // peak hours bring crowds
      let waiting = Math.floor(r() * (8 + central * 14) * demand);
      if (request && r() < 0.55) waiting = 0;
      const stop = {
        i, name: s.name, request,
        target: Math.min(s.s + STOP_AHEAD, this.route.length - 2),
        sched: this.trip[i],
        waiting, alightFrac: 0.08 + r() * 0.25 + central * 0.05,
        alight: 0, runners: r() < 0.35 ? 1 + Math.floor(r() * 3) : 0, runnerDelay: 4 + r() * 9,
        arrived: false, served: false, done: false, departClock: null,
      };
      if (request && r() < 0.5) stop.alightFrac = 0;
      stop.ambient = request ? Math.floor(r() * 2) : 2 + Math.floor(r() * (5 + central * 6)); // waiting for other lines
      if (i === n - 1) { stop.waiting = 0; stop.alightFrac = 1; stop.runners = 0; }
      this._buildStop(stop);
      return stop;
    });
    this.crowd = makeCrowd(120);
    this.objects.add(this.crowd);
  }

  _buildStop(stop) {
    const route = this.route;
    const g = new THREE.Group();
    // platform on the right (T3 doors are on the right side only)
    const len = 30, mid = stop.target - len / 2 - 1;
    const plat = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.22, len), new THREE.MeshLambertMaterial({ color: 0xa7a197 }));
    place(plat, route, mid, -3.0, 0.11);
    // curved platforms: approximate with a straight box oriented along the chord
    const a = route.offset(stop.target - len - 1, -3.0), b = route.offset(stop.target - 1, -3.0);
    const za = this.profile.height(stop.target - len - 1), zb = this.profile.height(stop.target - 1);
    const chord = Math.hypot(b.x - a.x, b.y - a.y);
    plat.position.set((a.x + b.x) / 2, (za + zb) / 2 + 0.33, -(a.y + b.y) / 2);
    plat.rotation.order = 'YXZ';
    plat.rotation.y = Math.atan2(b.x - a.x, -(b.y - a.y));
    plat.rotation.x = -Math.atan2(zb - za, chord);
    plat.scale.z = chord / len;
    g.add(plat);
    // the classic red Prague stop sign (zastávkový označník) where the tram front stops
    const sign = makeStopSign(stop.name, stop.request, this.data.stops[stop.i].lines || [String(this.data.line)]);
    place(sign, route, stop.target + 0.5, -2.3, 0.44, true);
    g.add(sign);
    // shelter
    const shelter = new THREE.Group();
    const roof = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.1, 5), new THREE.MeshLambertMaterial({ color: 0x3d4a52 }));
    roof.position.y = 2.5;
    const back = new THREE.Mesh(new THREE.BoxGeometry(0.05, 2.1, 5), new THREE.MeshLambertMaterial({ color: 0x9fb8c4, transparent: true, opacity: 0.45 }));
    back.position.set(-0.75, 1.3, 0);
    shelter.add(roof, back);
    place(shelter, route, stop.target - 12, -3.4, 0.44);
    g.add(shelter);
    this.objects.add(g);
  }

  _initSignals() {
    this.signals = this.data.signals.map((d, i) => {
      d = { ...d };
      // a signal just before a stop sign would block the platform: move it past the tram front
      for (const st of this.stops) {
        if (d.s > st.target - 25 && d.s < st.target + 2 && st.target + 2 < d.cross - 2) d.s = st.target + 2;
      }
      const mesh = makeTramSignal();
      place(mesh, this.route, d.s, -2.4, 0, true);
      this.objects.add(mesh);
      // the GO aspect shows the direction the route takes through the junction
      const h0 = this.route.heading(d.cross - 5, 5), h1 = this.route.heading(d.cross + 30, 8);
      const turn = Math.atan2(h0.hx * h1.hy - h0.hy * h1.hx, h0.hx * h1.hx + h0.hy * h1.hy);
      const goDir = turn > 0.45 ? 'left' : turn < -0.45 ? 'right' : 'straight';
      const sig = { ...d, goDir, state: 'stop', timer: 5 + this.rand() * 30, preferred: false, mesh, cars: [], spawn: 0, seed: i * 31 };
      if (this.rand() < 0.4) { sig.state = 'go'; sig.timer = 5 + this.rand() * 15; }
      mesh.userData.set(sig.state, { goDir });
      return sig;
    }).sort((a, b) => a.s - b.s);
    this._initGauntlets();
    this._initDistantSignals();
  }

  // Interlaced track (gauntlet), e.g. Letenska under the building near Malostranske namesti:
  // both directions share ~65 m of track, so only one tram may be inside at a time. Signals at
  // both ends; the block is granted to one direction, returns to STOP behind the entering
  // tram, and the other direction only gets GO after the section is clear plus clearance time.
  _initGauntlets() {
    this.gauntlets = [];
    const back = this.backRoute;
    if (!back) return;
    const segs = [];
    let cur = null;
    for (let s = 0; s < this.route.length; s += 3) {
      const p = this.route.at(s);
      const n = back.nearest(p.x, p.y);
      if (n && n.d < 1.8) { if (!cur) { cur = [s, s]; segs.push(cur); } else cur[1] = s; } else cur = null;
    }
    for (const [a, b] of segs) {
      if (b - a < 25) continue;
      const s0 = a - 6, s1 = b + 6; // conflict zone incl. car body overhang
      const pa = this.route.at(s0), pb = this.route.at(s1);
      const G = {
        s0, s1,
        b0: back.nearest(pb.x, pb.y).s, // oncoming trams enter at our far end
        b1: back.nearest(pa.x, pa.y).s,
        state: 'idle', timer: 0, entered: false, lastServed: 'theirs', grantedAt: 0,
        theirs: { requested: false, occupied: false },
      };
      // drop ordinary traffic-light signals that fall inside or just before the block
      this.signals = this.signals.filter((x) => {
        const drop = x.s > s0 - 30 && x.s < s1;
        if (drop) this.objects.remove(x.mesh);
        return !drop;
      });
      const mesh = makeTramSignal();
      place(mesh, this.route, s0 - 4, -2.4, 0, true);
      this.objects.add(mesh);
      G.sig = { s: s0 - 4, cross: s0, goDir: 'straight', gauntlet: G, state: 'stop', timer: Infinity, preferred: false, mesh, cars: [], spawn: 0 };
      this.signals.push(G.sig);
      // the opposite direction's signal, facing oncoming trams
      G.theirMesh = makeTramSignal();
      const o = back.offset(G.b0 - 4, -2.4);
      G.theirMesh.position.set(o.x, this.route.ground.at(o.x, o.y), -o.y);
      G.theirMesh.rotation.y = Math.atan2(-o.hx, o.hy);
      this.objects.add(G.theirMesh);
      this.gauntlets.push(G);
    }
    this.signals.sort((a, b) => a.s - b.s);
  }

  _updateGauntlets(dt) {
    const tram = this.tram;
    for (const G of this.gauntlets) {
      const overlaps = (front) => front > G.s0 && front - T3.length < G.s1;
      const approaching = (front) => front <= G.s0 && G.s0 - front < 150;
      const occOurs = overlaps(tram.s) || this.aiTrams.some((t) => overlaps(t.s));
      const reqOurs = approaching(tram.s) || this.aiTrams.some((t) => approaching(t.s));
      const { requested: reqTheirs, occupied: occTheirs } = G.theirs;
      G.reqOurs = reqOurs;
      if (G.state === 'idle') {
        if (occTheirs) G.state = 'theirs';
        else if (occOurs) G.state = 'ours';
        else if (reqOurs && (!reqTheirs || G.lastServed === 'theirs')) G.state = 'ours';
        else if (reqTheirs) G.state = 'theirs';
        G.entered = false;
        G.grantedAt = this.clock;
      } else if (G.state === 'ours') {
        if (occOurs) G.entered = true;
        const done = G.entered && !occOurs;
        const timeout = !G.entered && reqTheirs && this.clock - G.grantedAt > 45;
        if (done || timeout || (!reqOurs && !occOurs)) { G.state = 'clearing'; G.timer = 6; G.lastServed = 'ours'; }
      } else if (G.state === 'theirs') {
        if (occTheirs) G.entered = true;
        if ((G.entered && !occTheirs) || (!reqTheirs && !occTheirs)) { G.state = 'clearing'; G.timer = 6; G.lastServed = 'theirs'; }
      } else if (G.state === 'clearing') {
        G.timer -= dt;
        if (G.timer <= 0) G.state = 'idle';
      }
      // our signal shows GO only until our tram enters; then it returns to STOP behind it
      G.sig.state = G.state === 'ours' && !G.entered ? 'go' : 'stop';
      if (G.sig.state === 'stop' && G.sig.lastState !== 'stop') G.sig.stopSince = this.clock;
      G.sig.lastState = G.sig.state;
      const theirGo = G.state === 'theirs' && !G.entered;
      G.theirMesh.userData.set(theirGo ? 'go' : 'stop', { goDir: 'straight', call: G.theirs.requested && !theirGo ? 'on' : 'off' });
      // head-on: we are inside while an oncoming tram is too
      if (overlaps(tram.s) && occTheirs && !G.crashed) {
        G.crashed = true;
        this._collision(t('msg.headOn'), 600);
      }
      if (!overlaps(tram.s)) G.crashed = false;
    }
  }

  // Distant signals (předvěst, yellow P plate) before main signals hidden behind a curve.
  _initDistantSignals() {
    this.distants = [];
    let lastS = -1e9;
    for (const sig of this.signals) {
      let minR = Infinity;
      for (let s = sig.s - 140; s < sig.s - 20; s += 10) minR = Math.min(minR, this.route.radiusAt(s));
      const ds = sig.s - 120;
      if (minR > 110 || ds < 30 || ds - lastS < 60) continue;
      if (this.signals.some((o) => o !== sig && o.s > ds - 20 && o.s < sig.s)) continue;
      const mesh = makeTramSignal({ distant: true });
      place(mesh, this.route, ds, -2.4, 0, true);
      this.objects.add(mesh);
      this.distants.push({ s: ds, main: sig, mesh });
      lastS = sig.s;
    }
  }

  _initSwitches() {
    this.switches = this.data.switches.map((d) => {
      const required = d.routeDiverging ? 'diverging' : 'straight';
      const divSide = d.routeDiverging ? d.routeSide : (d.routeSide === 'left' ? 'right' : 'left');
      const sw = {
        ...d, required, divSide,
        pos: this.rand() < 0.5 ? 'straight' : 'diverging',
        contact: d.s - 22, passedContact: false, passed: false,
        indicator: makeSwitchIndicator(), marker: makeContactMarker(),
      };
      // a contact inside a stop zone can't be driven sensibly: such switches are set
      // automatically by the tram's route transmitter (IRC), like most Prague switches today
      // A contact just after a stop cannot be driven sensibly: these switches are radio (IRC)
      // controlled, as most Prague switches are today. The driver selects the direction with
      // the IRC buttons (Q left, R straight, E right), or it is automatic if the option is on.
      // (the same applies after a signal, where trams also stand and must start up again)
      sw.auto = this.stops.some((st) => st.target > sw.contact - 60 && st.target < d.s + 2)
        || this.signals.some((g) => g.s > sw.contact - 60 && g.s < d.s + 2);
      sw.marker.visible = !sw.auto;
      if (sw.auto && this.opts.autoIrc) sw.pos = required;
      const sign = sw.auto ? makeRadioSwitchSign() : makeContactSign();
      place(sign, this.route, sw.auto ? d.s - 40 : sw.contact, -2.6, 0, true);
      this.objects.add(sign);
      place(sw.indicator, this.route, d.s - 8, -0.4, 0, true); // hangs from the span wire over the track
      const c = this.route.at(sw.contact);
      sw.marker.position.x = c.x;
      sw.marker.position.y += this.profile.height(sw.contact);
      sw.marker.position.z = -c.y;
      this.objects.add(sw.indicator, sw.marker);
      this._showSwitch(sw);
      return sw;
    });
  }

  // IRC direction buttons: set the next radio-controlled switch within 80 m
  irc(dir) {
    // each press goes to the next radio switch ahead that the driver has not set yet
    const inRange = this.switches.filter((w) => w.auto && !w.passed && !w.locked && w.s - this.tram.s > 2 && w.s - this.tram.s < 80);
    const sw = inRange.find((w) => !w.ircSet) || inRange[inRange.length - 1];
    if (!sw) {
      const locked = this.switches.some((w) => w.auto && !w.passed && w.locked);
      this.audio.warning();
      this.msg(t(locked ? 'msg.ircLocked' : 'msg.ircNone'), 'warn', 2.5);
      return;
    }
    sw.ircSet = true;
    let pos = null;
    if (dir === 'straight') pos = 'straight';
    else if (dir === sw.divSide) pos = 'diverging';
    if (!pos) { this.audio.warning(); this.msg(t('msg.ircNoBranch', { dir: t(`dirShort.${dir}`) }), 'warn'); return; }
    sw.pos = pos;
    this._showSwitch(sw);
    this.audio.click(0.2, 2600);
    this.ircLast = dir;
  }

  // Track signs: speed limits (rychlostník) where a restriction starts or ends, and
  // dangerous gradient boards at the top of steep descents.
  _initSigns() {
    const lim = this.limits, step = lim.step, vals = lim.values;
    let last = -1e9, cur = vals[0];
    for (let i = 1; i < vals.length; i++) {
      const v = vals[i];
      if (v === cur) continue;
      // only changes that last at least 25 m
      let k = i;
      while (k < vals.length && vals[k] === v && (k - i) * step < 25) k++;
      if ((k - i) * step < 25 && k < vals.length) continue;
      const s = i * step - (v < cur ? 12 : 0);
      cur = v;
      if (s - last < 35 || s < 20) continue;
      last = s;
      const sign = makeSpeedSign(v);
      place(sign, this.route, s, -2.7, 0, true);
      this.objects.add(sign);
    }
    let inSteep = false;
    for (let s = 0; s < this.route.length; s += 10) {
      const g = this.profile.grade(s + 30);
      if (!inSteep && g < -0.055) {
        inSteep = true;
        const sign = makeGradientSign(Math.round(-this.profile.grade(s + 60) * 100) || 6);
        place(sign, this.route, s, -2.9, 0, true);
        this.objects.add(sign);
      } else if (inSteep && g > -0.03) inSteep = false;
    }
  }

  _showSwitch(sw) {
    sw.indicator.userData.set(sw.pos === 'straight' ? 'straight' : sw.divSide);
  }

  _initObstacles() {
    this.obstacles = [];
    const p = { off: 0, normal: 0.28, many: 0.6 }[this.opts.obstacles] ?? 0.28;
    if (!p) return;
    for (let i = this.opts.startStop; i < this.stops.length - 1; i++) {
      const a = this.stops[i].target + 40, b = this.stops[i + 1].target - 60;
      if (b - a < 80 || this.rand() > p) continue;
      const s = a + this.rand() * (b - a);
      if (this.switches.some((w) => Math.abs(w.s - s) < 30) || this.signals.some((g) => Math.abs(g.cross - s) < 40)) continue;
      const type = this.rand() < 0.5 ? 'parked' : 'pedestrian';
      const mesh = type === 'parked' ? makeCar(Math.floor(this.rand() * 8)) : makePerson(Math.floor(this.rand() * 8));
      const ob = { type, s, lat: type === 'parked' ? -1.5 : -6, mesh, state: 'idle', timer: 0, rung: false, speed: 1.3 };
      place(mesh, this.route, s, ob.lat, 0, false);
      if (type === 'pedestrian') mesh.visible = false;
      this.objects.add(mesh);
      this.obstacles.push(ob);
    }
    // jaywalkers at some unsignalised pedestrian crossings
    for (const s of this.data.crossings) {
      if (s < this.stops[this.opts.startStop].target + 50 || this.rand() > p * 0.15) continue;
      const mesh = makePerson(Math.floor(this.rand() * 8));
      mesh.visible = false;
      this.objects.add(mesh);
      this.obstacles.push({ type: 'pedestrian', s, lat: this.rand() < 0.5 ? -6 : 6, mesh, state: 'idle', timer: 0, rung: false, speed: 1.3 });
    }
  }

  // Wheel/rail adhesion along the line. Rain lowers it everywhere; in autumn, crushed wet
  // leaves form short, very slippery patches (drawn as brown smears on the rails).
  _initAdhesion() {
    this.muBase = ADHESION[this.weather] ?? ADHESION.dry;
    this.patches = [];
    if (this.weather !== 'leaves') return;
    const mat = new THREE.MeshLambertMaterial({ color: 0x6b4a22, transparent: true, opacity: 0.85 });
    for (let s = 150 + this.rand() * 200; s < this.route.length - 50; s += 180 + this.rand() * 420) {
      const len = 15 + this.rand() * 45;
      this.patches.push([s, s + len]);
      for (let k = s; k < s + len; k += 4) {
        const smear = new THREE.Mesh(new THREE.PlaneGeometry(1.9, 4.2), mat);
        smear.rotation.x = -Math.PI / 2;
        const holder = new THREE.Group();
        holder.add(smear);
        place(holder, this.route, k + 2, (this.rand() - 0.5) * 0.3, 0.28, false);
        this.objects.add(holder);
      }
    }
  }

  muAt(s) {
    let mu = this.muBase;
    if (this.weather === 'rain') mu += 0.02 * Math.sin(s / 37);
    for (const [a, b] of this.patches) if (s > a && s < b) return 0.06;
    return mu;
  }

  get atPlatform() {
    const st = this.stops[this.nextStop];
    return !!st && this._atStop(st);
  }

  // ------------------------------------------------------------------ helpers
  msg(text, kind = 'info', ttl = 4) {
    this.messages.push({ text, kind, ttl, t: 0 });
    if (this.messages.length > 5) this.messages.shift();
  }

  penalty(key, pts, text) {
    this.score -= pts;
    this.penalties[key] = (this.penalties[key] || 0) + pts;
    if (text) this.msg(`${text} (−${Math.round(pts)})`, 'bad', 5);
  }

  bonus(pts, text) {
    this.score += pts;
    if (text) this.msg(`${text} (+${pts})`, 'good', 3);
  }

  get currentLimit() {
    // the whole tram length must respect a restriction
    let v = 99;
    for (let s = this.tram.s - T3.length; s <= this.tram.s + 0.1; s += 5) v = Math.min(v, this.limits.at(s));
    return v;
  }

  // The most restrictive lower limit ahead: the one that needs braking soonest (a 10 km/h
  // curve shortly after a 40 km/h section matters more than the 40).
  nextLimitChange() {
    const cur = this.currentLimit;
    let best = null, bestNeed = Infinity;
    for (let d = 5; d < 300; d += 5) {
      const v = this.limits.at(this.tram.s + d);
      if (v >= cur) continue;
      const need = Math.sqrt((v / 3.6) ** 2 + 2 * 0.7 * d); // speed allowed now to make it
      if (need < bestNeed) { bestNeed = need; best = { v, d }; }
    }
    return best;
  }

  get doorsClosed() { return this.doorState === 'closed'; }

  // ------------------------------------------------------------------ input
  toggleDoors() {
    if (this.finished) return;
    if (this.doorState === 'closed' || this.doorState === 'closing') {
      if (Math.abs(this.tram.v) > 0.3) { this.audio.warning(); this.msg(t('msg.noOpenMoving'), 'warn'); return; }
      // tell the driver why nothing happens when the doors open away from the platform
      const st = this.stops[this.nextStop];
      if (st && !this._atStop(st)) {
        const d = st.target - this.tram.s;
        if (d > 0 && d < 200) this.msg(t('msg.notAtPlatform', { go: Math.round(d - STOP_TOL_BEHIND), d: Math.round(d) }), 'warn', 5);
        else if (d >= 200) this.msg(t('msg.noPlatform'), 'warn');
      }
      this.doorState = 'opening';
      this.doorTimer = DOOR_OPEN_TIME;
      this.audio.doors(false);
    } else {
      this.doorState = 'closing';
      this.doorTimer = DOOR_CLOSE_TIME;
      this.audio.doors(true);
      const st = this.stops[this.nextStop];
      if (st && st.arrived && st.waiting > 0 && this._atStop(st)) {
        this.penalty('leftBehind', st.waiting * 15, t('msg.closedOn', { n: st.waiting }));
        st.waiting = 0;
      }
    }
  }

  ringBell() {
    this.audio.bell();
    for (const ob of this.obstacles) {
      const d = ob.s - this.tram.s;
      if (d > 0 && d < 120) ob.rung = true;
    }
  }

  crowbar() {
    if (this.action) return;
    const sw = this.switches.find((w) => !w.passed && w.s - this.tram.s > 0 && w.s - this.tram.s < 40);
    if (!sw) { this.msg(t('msg.noSwitch'), 'warn'); return; }
    if (this.tram.v > 0.05) { this.msg(t('msg.stopFirst'), 'warn'); return; }
    this.action = {
      label: t('msg.crowbar'), t: 9,
      done: () => {
        sw.pos = sw.pos === 'straight' ? 'diverging' : 'straight';
        this._showSwitch(sw);
        this.audio.click(0.3, 400);
        this.msg(t('msg.switchManual', { dir: t(`dirShort.${sw.pos === 'straight' ? 'straight' : sw.divSide}`) }), 'info');
      },
    };
  }

  // ------------------------------------------------------------------ update
  update(dt, input) {
    if (this.paused || this.finished) return;
    const tram = this.tram;
    const prevS = tram.s;
    this.clock += dt;

    // dead-man pedal
    let deadmanTrip = false;
    if (this.opts.deadman) {
      const needs = tram.v > 0.5 || tram.notch > 0;
      if (input.deadman || !needs) this.deadmanTimer = 0;
      else {
        this.deadmanTimer += dt;
        if (this.deadmanTimer > 0.2 && Math.floor(this.deadmanTimer * 4) !== Math.floor((this.deadmanTimer - dt) * 4)) this.audio.warning();
        if (this.deadmanTimer > 2.0) deadmanTrip = true;
      }
      if (deadmanTrip && !this.deadmanTripped) { this.deadmanTripped = true; this.penalty('deadman', 50, t('msg.deadman')); }
      if (!deadmanTrip) this.deadmanTripped = false;
    }
    this.deadmanWarn = this.deadmanTimer > 0.2;

    // actions outside the cab and collisions hold the tram
    if (this.action) {
      this.action.t -= dt;
      tram.forcedStop = true;
      if (this.action.t <= 0) { const a = this.action; this.action = null; a.done(); }
    } else if (this.holdTimer > 0) {
      this.holdTimer -= dt;
      tram.forcedStop = true;
    } else tram.forcedStop = false;

    const mid = tram.s - T3.length / 2;
    tram.update(dt, {
      deadmanTrip,
      grade: this.profile.grade(mid),
      radius: this.route.radiusAt(tram.s - 4),
      mu: this.muAt(tram.s),
      sandKey: !!input.sand,
      autoHold: this.doorState !== 'closed',
    });

    this._updateDoors(dt);
    this._updateStops(dt);
    this._updateSwitches(prevS);
    this._updateSignals(dt, prevS);
    this._updateObstacles(dt);
    this._updateRules(dt);

    for (const m of this.messages) m.t += dt;
    this.messages = this.messages.filter((m) => m.t < m.ttl);
  }

  _atStop(st) {
    return this.tram.s >= st.target - STOP_TOL_BEHIND && this.tram.s <= st.target + STOP_TOL_AHEAD;
  }

  _updateDoors(dt) {
    if (this.doorState === 'opening' || this.doorState === 'closing') {
      this.doorTimer -= dt;
      if (this.doorTimer <= 0) this.doorState = this.doorState === 'opening' ? 'open' : 'closed';
    }
    if (this.doorState !== 'closed' && Math.abs(this.tram.v) > 0.4) {
      if (!this.doorsMovingFlag) { this.doorsMovingFlag = true; this.penalty('doors', 100, t('msg.doorsMoving')); }
    } else if (Math.abs(this.tram.v) < 0.1) this.doorsMovingFlag = false;
  }

  _updateStops(dt) {
    const tram = this.tram;
    const st = this.stops[this.nextStop];
    if (!st) return;
    const at = this._atStop(st) && Math.abs(tram.v) < 0.05;

    if (at && !st.arrived) {
      st.arrived = true;
      st.arriveClock = this.clock;
      const err = tram.s - st.target;
      if (Math.abs(err) < 3) this.bonus(15, t('msg.precise'));
      else if (err > 4) this.penalty('precision', 20, t('msg.overshot', { d: Math.round(err) }));
    }
    if (st.arrived && !st.alightSet) {
      st.alightSet = true;
      st.alight = Math.round(tram.passengers * st.alightFrac);
    }
    // passenger exchange through open doors
    if (at && this.doorState === 'open') {
      st.served = true;
      // three doors; a packed car boards slowly
      const crowd = tram.passengers > T3.capacity ? 0.45 : tram.passengers > T3.capacity * 0.75 ? 0.75 : 1;
      st.flow = (st.flow || 0) + 3 * 1.1 * crowd * dt;
      while (st.flow >= 1) {
        st.flow -= 1;
        if (st.alight > 0) { st.alight--; tram.passengers--; this.score += 1; }
        else if (st.waiting > 0 && tram.passengers < T3.crushCapacity) { st.waiting--; tram.passengers++; this.score += 1; }
        else break;
      }
      if (st.alight === 0 && st.waiting > 0 && tram.passengers >= T3.crushCapacity) {
        this.msg(t('msg.full', { n: st.waiting }), 'warn', 5);
        st.leftFull = st.waiting;
        st.waiting = 0;
      }
      // late runners
      if (st.runners > 0 && this.clock - st.arriveClock > st.runnerDelay) {
        st.waiting += st.runners;
        this.msg(t('msg.runners', { n: st.runners }), 'info');
        st.runners = 0;
      }
    }
    // departure detection
    if (st.served && st.departClock === null && tram.v > 0.3) st.departClock = this.clock;

    const passed = tram.s > st.target + STOP_TOL_AHEAD + 1;
    const last = this.nextStop === this.stops.length - 1;
    if (last && st.served && st.alight === 0 && this.doorState === 'open') {
      this._finishStop(st);
      this._end();
      return;
    }
    if (passed && !last) {
      this._finishStop(st);
      this.nextStop++;
    }
  }

  _finishStop(st) {
    st.done = true;
    if (!st.served) {
      const needed = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if (!needed) {
        this.log.push({ name: st.name, skipped: true });
        return;
      }
      this.penalty('missed', 150, t('msg.missed', { stop: st.name }));
      this.log.push({ name: st.name, missed: true });
      return;
    }
    if (st.alight > 0) this.penalty('leftBehind', st.alight * 10, t('msg.cantAlight', { n: st.alight }));
    const dep = st.departClock ?? this.clock;
    const dev = dep - st.sched;
    st.dev = dev;
    this.log.push({ name: st.name, dev });
    const last = st.i === this.stops.length - 1;
    if (last) return;
    if (dev < -5) this.penalty('early', 20 + Math.min(200, -dev * 1.5), t('msg.early', { t: fmtDev(dev) }));
    else if (dev <= 60) this.bonus(40, t('msg.onTime', { t: fmtDev(dev) }));
    else if (dev <= 180) this.bonus(10, t('msg.departed', { t: fmtDev(dev) }));
    else this.penalty('late', Math.min(80, (dev - 180) / 6), t('msg.lateDep', { t: fmtDev(dev) }));
  }

  _updateSwitches(prevS) {
    const tram = this.tram;
    const blinkOff = Math.floor(this.clock * 2.5) % 2 === 1;
    for (const sw of this.switches) {
      // the indicator blinks while the switch is locked under/for the approaching tram
      if (Math.abs(sw.s - tram.s) < 250) {
        sw.locked = tram.s > (sw.auto ? sw.s - 8 : sw.contact) && tram.s - T3.length < sw.s + 2;
        sw.indicator.userData.set(sw.pos === 'straight' ? 'straight' : sw.divSide, sw.locked && blinkOff);
      }
      if (sw.passed) continue;
      if (!sw.passedContact && prevS < sw.contact && tram.s >= sw.contact) {
        sw.passedContact = true;
        if (!sw.auto) {
          sw.pos = tram.force > 500 ? 'diverging' : 'straight';
          this._showSwitch(sw);
          this.audio.click(0.25, 2000);
        }
      }
      if (prevS < sw.s && tram.s >= sw.s) {
        sw.passed = true;
        if (sw.pos !== sw.required) {
          tram.s = sw.s - 0.3;
          tram.v = 0;
          tram.force = 0;
          this.holdTimer = 6;
          this.clock += 30;
          sw.pos = sw.required;
          this._showSwitch(sw);
          this.audio.crash();
          this.penalty('switch', 150, t('msg.wrongSwitch'));
        }
      }
    }
  }

  // the next overhead contact ahead (a contact can lie before the previous switch)
  nextContact() {
    return this.switches.find((w) => !w.auto && !w.passedContact && w.contact > this.tram.s - 1);
  }

  nextSwitch() {
    return this.switches.find((w) => !w.passed && w.s > this.tram.s - 1);
  }

  _updateSignals(dt, prevS) {
    const tram = this.tram;
    this._updateGauntlets(dt);
    for (const sig of this.signals) {
      if (sig.gauntlet) {
        let call = 'off';
        if (sig.gauntlet.reqOurs && sig.state === 'stop') call = sig.gauntlet.state === 'clearing' && Math.floor(this.clock * 3) % 2 ? 'off' : 'on';
        sig.mesh.userData.set(sig.state, { goDir: 'straight', call });
        if (prevS < sig.s && tram.s >= sig.s && sig.state === 'stop' && this.clock - (sig.stopSince ?? -1e9) > 1.0) {
          this.penalty('signal', 300, t('msg.passedGauntlet'));
        }
        continue;
      }
      sig.timer -= dt;
      const dist = sig.s - tram.s;
      // tram priority: detectors shorten the red phase when a tram approaches
      if (sig.state === 'stop' && dist > 0 && dist < 140 && !sig.preferred) {
        sig.preferred = true;
        sig.timer = Math.min(sig.timer, 5 + this.rand() * 12);
      }
      if (dist < -T3.length) sig.preferred = false;
      // the detector also holds GO for a tram that is committed to the junction
      if (sig.state === 'go' && dist > 0 && dist < 15 + (tram.v * tram.v) / 1.6) sig.timer = Math.max(sig.timer, 1.5); // dilemma zone
      if (sig.timer <= 0) {
        if (sig.state === 'stop') { sig.state = 'go'; sig.timer = 14 + this.rand() * 14; }
        else if (sig.state === 'go') { sig.state = 'warn'; sig.timer = 3; }
        else { sig.state = 'stop'; sig.timer = 20 + this.rand() * 30; sig.stopSince = this.clock; }
      }
      const blink = sig.state === 'warn' && Math.floor(this.clock * 2) % 2 === 0;
      // call lamp: lit once the tram request is registered, blinking in the last 3 s before GO
      let call = 'off';
      if (sig.preferred && sig.state === 'stop') call = sig.timer < 3 && Math.floor(this.clock * 3) % 2 ? 'off' : 'on';
      sig.mesh.userData.set(sig.state, { goDir: sig.goDir, blink, call });

      if (prevS < sig.s && tram.s >= sig.s && sig.state === 'stop' && this.clock - (sig.stopSince ?? -1e9) > 1.5) {
        this.penalty('signal', 200, t('msg.passedSignal'));
      }
      this._crossTraffic(sig, dt);
    }
    for (const d of this.distants) d.mesh.userData.set(d.main.state === 'go' ? 'go' : 'stop', { goDir: 'straight' });
  }

  _crossTraffic(sig, dt) {
    const tram = this.tram;
    const near = Math.abs(sig.cross - tram.s) < 400;
    const tramOnCrossing = sig.cross > tram.s - T3.length - 1 && sig.cross < tram.s + 4;
    if (near && sig.state === 'stop' && sig.timer > 5) {
      sig.spawn -= dt;
      if (sig.spawn <= 0 && sig.cars.length < 4) {
        sig.spawn = 3 + this.rand() * 4;
        const dir = this.rand() < 0.5 ? 1 : -1;
        const mesh = makeCar(sig.seed++);
        this.objects.add(mesh);
        sig.cars.push({ lat: -dir * 45, dir, mesh, v: 9 });
      }
    }
    for (const car of sig.cars) {
      const ahead = car.lat * car.dir < -3.5 && car.lat * car.dir > -8;
      car.v = tramOnCrossing && ahead ? 0 : Math.min(9, car.v + dt * 3);
      car.lat += car.dir * car.v * dt;
      const o = this.route.offset(sig.cross, car.lat);
      car.mesh.position.set(o.x, this.route.ground.atRoute(sig.cross, car.lat) + 0.1, -o.y);
      // drive perpendicular to the track
      car.mesh.rotation.y = Math.atan2(-o.hy * car.dir, -o.hx * car.dir);
      if (Math.abs(car.lat) < 2.3 && tramOnCrossing && tram.v > 0.2 && !car.hit) {
        car.hit = true;
        this._collision(t('obj.crossingCar'));
      }
    }
    sig.cars = sig.cars.filter((c) => {
      if (Math.abs(c.lat) > 46) { this.objects.remove(c.mesh); return false; }
      return true;
    });
  }

  _updateObstacles(dt) {
    const tram = this.tram;
    for (const ob of this.obstacles) {
      if (ob.state === 'gone') continue;
      const d = ob.s - tram.s;
      if (ob.type === 'parked') {
        if (ob.state === 'idle' && d > 0 && d < 70 && tram.v < 0.1) { ob.state = 'waiting'; ob.timer = 10 + this.rand() * 14; }
        if (ob.state === 'waiting') {
          if (ob.rung && !ob.rungHandled) { ob.rungHandled = true; ob.timer = Math.min(ob.timer, 4); this.msg(t('msg.bellHeard'), 'info'); }
          ob.timer -= dt;
          if (ob.timer <= 0) ob.state = 'leaving';
        }
        if (ob.state === 'leaving') {
          ob.lat -= dt * 1.6;
          if (ob.lat < -5) ob.state = 'gone';
          place(ob.mesh, this.route, ob.s, ob.lat, 0, false);
        }
      } else {
        if (ob.state === 'idle' && d > 0 && d < 55 + tram.v * 2) {
          ob.state = 'walking';
          ob.mesh.visible = true;
          ob.dir = ob.lat < 0 ? 1 : -1;
        }
        if (ob.state === 'walking') {
          const sp = ob.rung ? 3.2 : ob.speed;
          // pedestrians pause in the middle when the tram is very close and slow
          ob.lat += ob.dir * sp * dt;
          place(ob.mesh, this.route, ob.s, ob.lat, 0, false);
          ob.mesh.rotation.y += ob.dir > 0 ? Math.PI / 2 : -Math.PI / 2;
          if (Math.abs(ob.lat) > 7) { ob.state = 'gone'; ob.mesh.visible = false; }
        }
      }
      // collision with tram body
      if (ob.state !== 'gone' && Math.abs(ob.lat) < 1.55 && ob.s <= tram.s + 0.2 && ob.s >= tram.s - T3.length) {
        if (tram.v > 0.15 || ob.type === 'pedestrian') {
          ob.state = 'gone';
          ob.mesh.visible = false;
          this._collision(t(ob.type === 'parked' ? 'obj.parkedCar' : 'obj.pedestrian'), ob.type === 'pedestrian' ? 500 : 300);
        }
      }
    }
    // running into the rear of the tram ahead
    for (const ai of this.aiTrams) {
      const rear = ai.s - T3.length;
      if (!ai.hit && tram.s > rear - 0.3 && tram.s < ai.s) {
        ai.hit = true;
        tram.s = rear - 0.4;
        this._collision(t('obj.tramAhead', { line: ai.mesh.userData.line ?? '?' }), 400);
      }
      if (tram.s < rear - 5) ai.hit = false;
    }
  }

  // gap from our front to the rear of the next tram ahead (m), or null
  tramAheadGap() {
    let gap = null;
    for (const ai of this.aiTrams) {
      const d = ai.s - T3.length - this.tram.s;
      if (d > -1 && (gap === null || d < gap)) gap = d;
    }
    return gap;
  }

  _collision(what, pts = 300) {
    const tram = this.tram;
    this.audio.crash();
    this.penalty('collision', pts, t('msg.collision', { what }));
    tram.v = 0;
    tram.force = 0;
    this.holdTimer = 8;
    this.clock += 60;
  }

  _updateRules(dt) {
    const tram = this.tram;
    const lim = this.currentLimit;
    this.overspeed = tram.kmh > lim + 3;
    if (this.overspeed) {
      const pts = (tram.kmh - lim) * 0.6 * dt;
      this.overspeedAcc += pts;
      this.score -= pts;
      this.penalties.speed = (this.penalties.speed || 0) + pts;
      if (!this.overspeedWarned) { this.overspeedWarned = true; this.msg(t('msg.speeding', { v: lim }), 'bad'); }
      if (tram.kmh > lim + 22 && lim <= 20) {
        this.audio.crash();
        this.penalty('derail', 1000, t('msg.derailed'));
        this._end(true);
      }
    } else if (tram.kmh < lim) this.overspeedWarned = false;

    // passenger comfort: harsh longitudinal acceleration, jerk and sideways (curve) acceleration
    this.latAcc = (tram.v * tram.v) / this.route.radiusAt(tram.s - 4);
    if (tram.passengers > 0) {
      const harsh = Math.max(0, Math.abs(tram.a) - 1.5) * 4 + Math.max(0, Math.abs(tram.jerk) - 2.2) * 0.6
        + Math.max(0, this.latAcc - 1.0) * 5;
      if (harsh > 0) {
        const pts = harsh * dt * (0.5 + tram.passengers / 60);
        this.comfortAcc += pts;
        this.score -= pts;
        this.penalties.comfort = (this.penalties.comfort || 0) + pts;
      }
      if (this.latAcc > 1.4 && !this.latWarned) { this.latWarned = true; this.msg(t('msg.lateral'), 'warn'); }
      if (this.latAcc < 0.8) this.latWarned = false;
    }
    if (tram.notch === -5 && tram.v > 4 && !this.emergencyFlag) {
      this.emergencyFlag = true;
      if (tram.passengers > 20) this.msg(t('msg.emergencyPax'), 'warn');
    }
    if (Math.abs(tram.v) < 0.1) this.emergencyFlag = false;

    // rolling back on a gradient (released the brake before applying power)
    if (tram.v < -0.4 && !this.rollFlag) { this.rollFlag = true; this.penalty('rollback', 30, t('msg.rollback')); }
    if (tram.v >= 0) this.rollFlag = false;

    // locked wheels slide and grind flats into the tyres
    if (tram.slideTime > 1.2 && tram.v > 3 && !this.flatFlag) { this.flatFlag = true; this.penalty('flats', 40, t('msg.flats')); }
    if (!tram.slide) this.flatFlag = false;
    if (tram.slip && !this.slipWarned) { this.slipWarned = true; this.msg(t('msg.wheelspin'), 'warn'); }
    if (!tram.slip && !tram.slide) this.slipWarned = false;
  }

  _end(failed = false) {
    this.finished = true;
    this.failed = failed;
  }

  // ------------------------------------------------------------------ visuals
  updateVisuals() {
    // crowd at the next stop platform
    const st = this.stops[this.nextStop];
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
    let n = 0;
    // people on the platforms of the stop ahead and the one just passed
    for (const stop of [this.stops[this.nextStop - 1], st]) {
      if (!stop || Math.abs(stop.target - this.tram.s) > 450) continue;
      const r = rng(stop.i * 977);
      const count = Math.min(stop === st ? st.waiting + st.ambient : stop.ambient, 55);
      for (let k = 0; k < count && n < 120; k++) {
        const along = stop.target - 2 - r() * 24, lat = -2.4 - r() * 1.6;
        const o = this.route.offset(along, lat);
        p.set(o.x, this.profile.height(along) + 0.44, -o.y);
        sc.set(1, 0.85 + r() * 0.3, 1);
        q.setFromEuler(new THREE.Euler(0, r() * 6.28, 0));
        m.compose(p, q, sc);
        this.crowd.setMatrixAt(n++, m);
      }
    }
    this.crowd.count = n;
    this.crowd.instanceMatrix.needsUpdate = true;
  }
}
