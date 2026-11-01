// Gameplay: timetable, stops & passengers, doors, signals, switches, obstacles, scoring.
import * as THREE from 'three';
import { ADHESION, PANTO_FROM_FRONT, tramClearance } from './tram.js';
import { Route } from './route.js';
import { t } from './i18n.js';
import { leafTexture } from './weather.js';
import {
  makeCar, makePerson, makeCrowd, makeTramSignal, makeSwitchIndicator, makeContactMarker,
  makeStopSign, makeSpeedSign, makeContactSign, makeRadioSwitchSign, makeGradientSign,
} from './models.js';

const DOOR_OPEN_TIME = 2.0, DOOR_CLOSE_TIME = 3.0;
const STOP_AHEAD = 6;          // tram front stops this far past the projected platform point
// The platform is 30 m long: any front position that puts the 14 m car alongside it counts.
// Stopping within 3 m of the sign earns a bonus; overshooting > 4 m is served but penalised.
const STOP_TOL_BEHIND = 20, STOP_TOL_AHEAD = 12;

import { rng } from './random.js';

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
// a glass stop shelter (back panel on its local -x side)
function makeShelter() {
  const shelter = new THREE.Group();
  const roof = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.1, 5), new THREE.MeshLambertMaterial({ color: 0x3d4a52 }));
  roof.position.y = 2.5;
  const back = new THREE.Mesh(new THREE.BoxGeometry(0.05, 2.1, 5), new THREE.MeshLambertMaterial({ color: 0x9fb8c4, transparent: true, opacity: 0.45 }));
  back.position.set(-0.75, 1.3, 0);
  shelter.add(roof, back);
  return shelter;
}

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
    // climate (T3SUCS, DPP training manual): saloon seat heaters 0/1/2, cab fan heater (kalorifer)
    // 0 off / 1 fan / 2 half / 3 full, flap for the accelerator resistors' waste heat; the outdoor
    // temperature comes from the menu (real Prague weather, or a fixed season)
    const tout = opts.toutAt ? opts.toutAt(this.clock) : 12;
    const preheated = tout < 12;
    this.climate = { saloon: preheated ? 2 : 0, cab: preheated ? 3 : 0, flap: preheated, tout,
      tin: preheated ? 15 : tout + 1, tcab: preheated ? 17 : tout + 1, warned: 0 };
    this.deadmanHeld = false;
    this.deadmanTimer = 0;
    this.action = null; // { label, t, done }
    this.runners = []; // late passengers running for the tram (C14)
    this.holdTimer = 0;
    this.objects = new THREE.Group();
    scene.add(this.objects);

    this.profile = route.ground.profile;
    this.weather = opts.weather || 'dry';
    this.flatFlag = false;
    this.rollFlag = false;

    // a vehicle run may change its line number at a terminus (e.g. 9 continuing as 10)
    this.segments = data.segments || [{ line: String(data.line), from: 0 }];
    this.line = this.segments.filter((g) => g.from <= opts.startStop).pop().line; // starting at the change stop = new line
    this.onLineChange = null;
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
    // switches whose contact is already behind the pantograph were set for us on arrival
    for (const w of this.switches) {
      if (w.contact < tram.panto && w.s > tram.s - 1) { w.passedContact = true; w.pos = w.required; this._showSwitch(w); }
    }
    tram.passengers = Math.min(tram.crushCapacity, Math.floor((10 + this.rand() * 25) * demandAt(this.clock)));
    this.nextStop = opts.startStop;
    st.arrived = true;
    st.arriveClock = this.clock;
  }

  // ------------------------------------------------------------------ setup
  _initStops() {
    const r = this.rand;
    const n = this.data.stops.length;
    this._buildPlatforms();
    this.stops = this.data.stops.map((s, i) => {
      const central = i > n * 0.25 && i < n * 0.7 ? 1 : 0;
      const request = !!s.request;
      const demand = demandAt(this.trip[i]); // peak hours bring crowds
      let waiting = Math.floor(r() * (8 + central * 14) * demand);
      if (request && r() < 0.55) waiting = 0;
      const stop = {
        i, name: s.name, request,
        target: Math.min(s.s + STOP_AHEAD, this.route.length - 2),
        p0: s.p0, p1: s.p1,
        sched: this.trip[i],
        waiting, alightFrac: 0.08 + r() * 0.25 + central * 0.05,
        alight: 0, runners: r() < 0.35 ? 1 + Math.floor(r() * 3) : 0, runnerDelay: 4 + r() * 9,
        arrived: false, served: false, done: false, departClock: null,
      };
      if (request && r() < 0.5) stop.alightFrac = 0;
      this._stopZone(stop);
      stop.ambient = request ? Math.floor(r() * 2) : 2 + Math.floor(r() * (5 + central * 6)); // waiting for other lines
      if (i === n - 1) { stop.waiting = 0; stop.alightFrac = 1; stop.runners = 0; }
      // end of one line of the run: everybody leaves, the tram continues as the next line
      const change = this.segments.find((g) => g.from === i && g.from > 0);
      if (change) { stop.alightFrac = 1; stop.lineChange = change.line; }
      this._buildStop(stop);
      return stop;
    });
    this.crowd = makeCrowd(120);
    this.objects.add(this.crowd);
  }

  // Tram platforms of both directions from OSM (tools/platforms.py): each belongs to the nearer of our
  // track and the opposite one and is built as a strip curved along it, from 1.5 m off the track centre
  // out to its width, 0.18 m over top of rail (src/heights.js), kerb faces on both sides. Where the surveyed streets
  // (DTM) have a platform, island or sidewalk there, the survey draws it. The opposite direction's
  // platforms get a stop sign at their head and a shelter where OSM has one.
  // A Vienna-type stop (boarding from the sidewalk across the car lane; cars stop behind the open
  // doors): right of the track along the stop (2.2-3.4 m, doors on the right) the survey has mostly
  // carriageway, not an island or a raised edge (Čechův most, Ke Stírce from Kobylisy got a platform
  // on the road). Returns the kerb's offset (m right of the track: the first sidewalk out to 12 m), or
  // null for an ordinary stop / no survey.
  _vienna(rt, s0, s1) {
    const dtm = this.route.ground.dtm;
    if (!dtm) return null;
    // (car lanes only, not the tram bed: Hodkovičky on its own corridor read as a Vienna-type stop)
    const LANE = new Set(['road', 'parking']), RAISED = new Set(['island', 'platform', 'sidewalk', 'paved']);
    let lane = 0, raised = 0, kerb = 0, nk = 0;
    for (let s = s0 + 3; s < s1 - 2; s += 4) {
      for (const off of [2.2, 2.8, 3.4]) {
        const o = rt.offset(s, -off), c = dtm.classAt(o.x, o.y);
        if (LANE.has(c)) lane++;
        else if (RAISED.has(c)) raised++;
      }
      for (let off = 3.4; off <= 12; off += 0.4) {
        const o = rt.offset(s, -off), c = dtm.classAt(o.x, o.y);
        if (c === 'sidewalk' || c === 'paved' || c === 'platform' || c === 'island') { kerb += off; nk++; break; }
      }
    }
    if (lane + raised < 3 || lane / (lane + raised) <= 0.5) return null;
    return nk ? kerb / nk : 6;
  }

  _buildPlatforms() {
    const routes = [this.route, this.backRoute].filter(Boolean), ground = this.route.ground, dtm = ground.dtm;
    const pos = [], col = [];
    const cTop = new THREE.Color(0xa7a197), cKerb = new THREE.Color(0x8e8a82);
    const V = (o, z) => [o.x, z, -o.y];
    const tri = (a, b, c, k) => { pos.push(...a, ...b, ...c); for (let i = 0; i < 3; i++) col.push(k.r, k.g, k.b); };
    const quad = (a, b, c, d, k) => { tri(a, b, c, k); tri(a, c, d, k); };
    this.platforms = [];
    for (const pl of this.data.platforms || []) {
      let best = null;
      for (const rt of routes) {
        const proj = pl.p.map(([x, y]) => rt.nearest(x, y));
        if (proj.some((q) => !q)) continue;
        const d = proj.reduce((a, q) => a + q.d, 0) / proj.length;
        if (!best || d < best.d) best = { rt, proj, d };
      }
      if (!best || best.d > 12) continue;
      const { rt, proj } = best;
      // (a platform known only from GTFS: its stop position is where the tram front stops; the
      // platform runs 31 m back from there, room for a two-car set)
      let s0 = Math.min(...proj.map((q) => q.s)), s1 = Math.max(...proj.map((q) => q.s));
      if (pl.gtfs) { s1 = proj[0].s + 1; s0 = s1 - 32; }
      if (s1 - s0 < 8 || s1 - s0 > 120) continue;
      const lats = pl.p.map(([x, y], i) => { const q = rt.at(proj[i].s); return q.hx * (y - q.y) - q.hy * (x - q.x); }); // + = left
      const side = Math.sign(lats.reduce((a, b) => a + b, 0)) || -1, far = Math.max(...lats.map((l) => l * side));
      // (an OSM platform line usually runs along its middle, an area gives its outer edge)
      // (an OSM line: 2-3.5 m wide unless tagged; it reached over the car lane at Trojská, 5.1 m)
      const inner = 1.5, outer = pl.area ? Math.min(inner + 6, Math.max(inner + 2, far)) : inner + (pl.w || Math.max(2.4, Math.min(3.5, pl.gtfs ? far + 1 - inner : 2 * far - 2 * inner)));
      const plat = { rt, back: rt !== this.route, s0, s1, side, inner, outer, name: pl.name, code: pl.code, lines: pl.lines, stop: pl.stop, shelter: pl.shelter };
      this.platforms.push(plat);
      // (a Vienna-type stop on the doors' side: no platform on the road, the sidewalk is the platform)
      plat.kerb = side < 0 ? this._vienna(rt, s0, s1) : null;
      if (plat.kerb !== null) { plat.inner = plat.kerb; plat.outer = plat.kerb + 2; plat.surveyed = true; continue; }
      const mid = rt.offset((s0 + s1) / 2, side * (inner + outer) / 2), cls = dtm?.classAt(mid.x, mid.y);
      plat.surveyed = cls === 'platform' || cls === 'island' || cls === 'sidewalk';
      if (plat.surveyed) continue;
      let prev = null;
      const n = Math.max(2, Math.ceil((s1 - s0) / 2));
      for (let k = 0; k <= n; k++) {
        const s = s0 + ((s1 - s0) * k) / n, c = rt.at(s);
        const I = rt.offset(s, side * inner), O = rt.offset(s, side * outer);
        const zt = ground.trackAt(c.x, c.y), top = zt + 0.18, zg = Math.min(top - 0.05, ground.surface(O.x, O.y) - 0.05);
        const cur = { I, O, zt, top, zg };
        if (prev) {
          quad(V(prev.I, prev.top), V(I, top), V(O, top), V(prev.O, prev.top), cTop);
          quad(V(prev.I, prev.zt - 0.06), V(I, zt - 0.06), V(I, top), V(prev.I, prev.top), cKerb);
          quad(V(prev.O, prev.zg), V(O, zg), V(O, top), V(prev.O, prev.top), cKerb);
        } else quad(V(I, zt - 0.06), V(O, zg), V(O, top), V(I, top), cKerb);
        prev = cur;
      }
      quad(V(prev.I, prev.zt + 0.2), V(prev.O, prev.zg), V(prev.O, prev.top), V(prev.I, prev.top), cKerb);
    }
    if (pos.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      g.computeVertexNormals();
      this.objects.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide })));
    }
    // the opposite direction's stops: sign where PID has the stop (GTFS position, name and lines;
    // their driving direction is along the back route), shelter where OSM has one
    for (const p of this.platforms) {
      if (!p.back) continue;
      const at = p.stop ? p.rt.nearest(p.stop[0], p.stop[1]).s : p.s1 - 0.5;
      const o = p.rt.offset(at, p.side * (p.inner + 0.8)), h = p.rt.at(at);
      const zt = p.kerb !== null ? ground.surface(o.x, o.y) - 0.18 : ground.trackAt(o.x, o.y);
      const sign = makeStopSign(p.name || '', false, p.lines || [String(this.data.line)]);
      sign.position.set(o.x, zt + 0.18, -o.y);
      sign.rotation.y = Math.atan2(-h.hx, h.hy);
      this.objects.add(sign);
      if (p.shelter) {
        const sh = makeShelter(), m = p.rt.offset((p.s0 + p.s1) / 2, p.side * (p.outer - 0.6));
        sh.position.set(m.x, ground.trackAt(m.x, m.y) + 0.18, -m.y);
        sh.rotation.y = Math.atan2(m.hx, -m.hy) + (p.side > 0 ? Math.PI : 0);
        this.objects.add(sh);
      }
    }
  }

  _buildStop(stop) {
    const route = this.route;
    const g = new THREE.Group();
    // our platform: the OSM one (built with both directions' platforms) where it covers the stop zone,
    // else a 30 m box on the right (T3 doors are on the right side only)
    const osm = (this.platforms || []).find((p) => !p.back && p.side < 0 && p.s0 < stop.target - 8 && p.s1 > stop.target - 20);
    const len = 30, mid = stop.target - len / 2 - 1;
    // (a Vienna-type stop: boarding from the sidewalk; sign and shelter stand at the kerb)
    const kerb = osm ? osm.kerb : this._vienna(route, stop.target - len - 1, stop.target - 1);
    stop.vienna = kerb !== null;
    const plat = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.22, len), new THREE.MeshLambertMaterial({ color: 0xa7a197 }));
    plat.visible = !osm && !stop.vienna;
    place(plat, route, mid, -3.0, -0.15); // (0.26 under the old street-level reference: top of rail now)
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
    // (on the sidewalk's height, not the track's)
    const onWalk = (m) => { m.position.y = route.ground.surface(m.position.x, -m.position.z); };
    place(sign, route, stop.target + 0.5, stop.vienna ? -(kerb + 0.6) : -2.3, 0.18, true);
    if (stop.vienna) onWalk(sign);
    g.add(sign);
    // (kept to move with the stop point: _initSignals may pull it back to a signal's stop point)
    stop.sign = sign;
    stop.signPlace = (s) => { place(sign, route, s + 0.5, stop.vienna ? -(kerb + 0.6) : -2.3, 0.18, true); if (stop.vienna) onWalk(sign); };
    // the shelter's outer edge: the OSM platform's, but no further than the surveyed one where the DTM
    // draws the platform (OSM's island at Palackého náměstí is 6.2 m out, the survey's 4.5 m: the
    // shelter stood on the road)
    let outer = osm ? osm.outer : null;
    const dtm = route.ground.dtm;
    if (osm && dtm?.classAt) {
      let lat = osm.inner + 0.5, last = null;
      for (; lat <= osm.outer + 0.01; lat += 0.25) { const o = route.offset(stop.target - 12, -lat); if (dtm.classAt(o.x, o.y) === 'platform') last = lat; else if (last !== null) break; }
      if (last !== null) outer = Math.min(outer, last + 0.25);
    }
    // shelter (at the back of the OSM platform where there is one)
    const shelter = makeShelter();
    place(shelter, route, stop.target - 12, stop.vienna ? -(kerb + 2.4) : osm ? -(outer - 0.6) : -3.4, 0.18);
    if (stop.vienna) onWalk(shelter);
    g.add(shelter);
    this.objects.add(g);
  }

  _initSignals() {
    // grade separation: where our track is on a bridge, the junctions and their traffic lights
    // belong to the road underneath (e.g. the Modřany estakáda), not to the tram
    const placed = this._placeSignals(this.data.signals);
    this.signals = placed.filter((d) => !d.drop && !this.profile.overBridge(d.cross)).map((d, i) => {
      d = { ...d };
      // a signal never stands along a platform: it moves to the platform head, just past where the
      // tram front stops; if the crossing follows too closely for that, it hangs from the wire
      for (const st of this.stops) {
        const a = (st.p0 ?? st.target - 30) - 1, b = st.target + 2;
        if (d.s > a && d.s < b) {
          // (only while the platform head is still before the junction's near edge)
          if (b < (d.edge ?? d.cross) - 1) d.s = b;
          else {
            // (the crossing right after the platform: its stop point, 3 m before the signal, is where the
            // front stops for the passengers, or the crossing's edge if that comes first; hung 12-15 m
            // back over the platform it made trams stop short of the platform end at red, Kublov)
            d.hang = true; d.head = st;
            d.s = Math.max(d.s, Math.min(st.target, d.farEdge ?? d.edge ?? d.cross) + 3); // (farEdge: kept short of it, Nádraží Modřany)
            // (and the front stops for the passengers no further than that: the crossing began 4 m before
            // the platform's end at Staroměstská, the tram served the stop 3 m past its red stop point)
            if (d.s - 3 < st.target) { st.target = d.s - 3; st.zone[1] = Math.min(st.zone[1], st.target + 0.5); st.zone[0] = Math.min(st.zone[0], st.target - 6); st.signPlace?.(st.target); }
          }
        }
      }
      const mesh = makeTramSignal();
      // (at a platform end: on its own pole at the island's tip, a few metres past the post and further from
      // the track, so the post does not hide it from the driver; the same pole carries the crossing's
      // pedestrian heads; user's street view, Palackého náměstí. Hung from a span it hung 20 m back)
      if (d.head && !d.head.vienna) {
        const s = Math.min(d.s, (d.head.p1 ?? d.s) - 0.5);
        place(mesh, this.route, s, -3.5, 0.18, true);
        mesh.userData.tip = s === d.head.p1 - 0.5;
      }
      else this._mount(mesh, d.s, { hang: d.hang });
      this.objects.add(mesh);
      // the GO aspect shows the direction the route takes through the junction
      const h0 = this.route.heading(d.cross - 5, 5), h1 = this.route.heading(d.cross + 30, 8);
      const turn = Math.atan2(h0.hx * h1.hy - h0.hy * h1.hx, h0.hx * h1.hx + h0.hy * h1.hy);
      const goDir = turn > 0.45 ? 'left' : turn < -0.45 ? 'right' : 'straight';
      const sig = { ...d, goDir, state: 'stop', timer: 0, preferred: false, mesh, cars: [], spawn: 0, seed: i * 31 };
      // the junction's controller: one fixed cycle (60-90 s): trams going straight in both
      // directions together, then a short turning phase if our route turns here, then the cross
      // street; our GO is the straight phase or the turning phase
      const C = 60 + this.rand() * 30, gS = 20 + this.rand() * 10, gT = goDir === 'straight' ? 0 : 10;
      sig.cycle = { C, gS, gT, ours: goDir === 'straight' ? [0, gS] : [gS, gS + gT], cross: gS + gT };
      sig.t = this.rand() * C;
      sig.ext = 0;
      // where the opposite track passes the junction: oncoming trams stop there on red
      if (this.backRoute) {
        const x = this.route.at(d.cross), n = this.backRoute.nearestOnHeading(x.x, x.y, -x.hx, -x.hy);
        if (n && n.d < 15) sig.backCross = n.s;
      }
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
      const n = back.nearestOnHeading(p.x, p.y, -p.hx, -p.hy);
      if (n && n.d < 1.8) {
        // Consecutive 3 m samples must follow the same reverse traversal; a jump at a
        // crossing or between legs of a loop must not join two conflict sections.
        if (!cur || n.s > cur[2] || cur[2] - n.s > 15) { cur = [s, s, n.s]; segs.push(cur); }
        else { cur[1] = s; cur[2] = n.s; }
      } else cur = null;
    }
    for (const [a, b] of segs) {
      if (b - a < 25) continue;
      const s0 = a - 6, s1 = b + 6; // conflict zone incl. car body overhang
      const pa = this.route.at(s0), pb = this.route.at(s1);
      const enter = back.nearestOnHeading(pb.x, pb.y, -pb.hx, -pb.hy);
      const exit = back.nearestOnHeading(pa.x, pa.y, -pa.hx, -pa.hy);
      if (!enter || !exit || enter.s >= exit.s) continue;
      const G = {
        s0, s1,
        b0: enter.s, // oncoming trams enter at our far end
        b1: exit.s,
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
      G.theirMesh.position.set(o.x, this.route.ground.trackAt(o.x, o.y), -o.y);
      G.theirMesh.rotation.y = Math.atan2(-o.hx, o.hy);
      this.objects.add(G.theirMesh);
      this.gauntlets.push(G);
    }
    this.signals.sort((a, b) => a.s - b.s);
    for (const sig of this.signals) sig.xroad = sig.gauntlet ? null : this._crossRoad(sig.cross);
  }

  // Where streets, footways and pedestrian crossings cross our route: { s, start, car } sorted by s
  // (the conflict points a signal protects): s where the centre line crosses, start where its near
  // edge does (half its width, longer at a slant). Not ways on a bridge or in a tunnel (other levels).
  _routeConflicts() {
    const R = this.route, out = [];
    for (const r of this.data.roads) {
      if (r.t) continue;
      // (a bridge way counts where it meets the track at its end, at street level: the road off
      // Palackého most enters the junction there; it was left out and the signal moved into the junction)
      const chain = r.b ? (r.way || r.p) : null, ends = chain && [chain[0], chain[chain.length - 1]];
      const P = r.p;
      for (let i = 1; i < P.length; i++) {
        const a = P[i - 1], b = P[i], L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
        const m = R.nearest((a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
        if (!m || m.d > L / 2 + 3) continue;
        for (let t = 0; t <= L; t += 1) {
          const x = a[0] + ((b[0] - a[0]) * t) / L, y = a[1] + ((b[1] - a[1]) * t) / L, n = R.nearest(x, y);
          if (!n || n.d > 1.2) continue;
          if (ends && Math.min(...ends.map((e) => Math.hypot(e[0] - x, e[1] - y))) > 25) break;
          const h = R.at(n.s);
          // (crossing at more than ~18°: streets meet the track at a slant where it curves through a
          // junction, Kobylisy; "more than 37°" missed most of that junction)
          const cos = Math.abs(((b[0] - a[0]) * h.hx + (b[1] - a[1]) * h.hy) / L);
          if (cos < 0.95) out.push({ s: n.s, start: n.s - (r.w || 3) / 2 / Math.max(0.3, Math.sqrt(1 - cos * cos)), car: !r.f && !!r.c });
          break;
        }
      }
    }
    // (not a crossing that starts inside our platform with no OSM crossing over the tracks there: a zebra
    // from the island platform across the road beside it, which the line data projected onto the track;
    // the signal at Palackého náměstí stopped the tram 15 m short of the platform end for one, user's
    // orthophoto 2026-10-24; also Jiráskovo nám., Strossmayerovo nám., Veletržní palác)
    const osmTram = (this.data.osmSignals?.tram || []).map((c) => R.nearest(c.x, c.y)).filter((n) => n && n.d < 4).map((n) => n.s);
    const inPlatform = (s) => this.data.osmSignals && this.stops?.some((st) => st.p0 !== undefined && s > st.p0 + 2 && s < st.p1 - 0.5) && !osmTram.some((t) => Math.abs(t - s) < 5);
    for (const s of this.data.crossings) if (!inPlatform(s)) out.push({ s, start: s - 2, car: false });
    // signalled crossings over the tram track from OSM (data/lineN.signals.json, .claude/tools/osm_signals.py)
    for (const c of this.data.osmSignals?.tram || []) { const n = R.nearest(c.x, c.y); if (n && n.d < 4) out.push({ s: n.s, start: n.s - 2.5, car: false }); }
    return out.sort((a, b) => a.s - b.s);
  }

  // Where each signal stands (user, 2026-10-24: one after the junction at Kobylisy, some in the
  // middle of nowhere, some far before their junction). The conflicts come in clusters (gaps under
  // 20 m: a wide junction has 18 m between its streets' centre lines): a junction. A signal standing after a street junction (car crossings within 45 m before
  // it) that has no signal of its own belongs to it; if the junction has one, it is the junction's
  // far-side pedestrian crossing and is dropped (Kobylisy s 20819 stood after the junction, matched to
  // the zebra beyond it); else to the cluster around its crossing point. It stands 4 m before the
  // cluster's first conflict's near edge (the stop line), forward or back (the platform rule in _initSignals may
  // still move or hang it). No conflict within 30 m (a cycle path or footway we do not have): an
  // on-demand crossing (d.demand), resting on GO for the tram.
  _placeSignals(list) {
    const C = this._routeConflicts(), GAP = 20;
    const edge = (lo, hi) => Math.min(...C.slice(lo, hi + 1).map((c) => c.start)); // the cluster's near edge
    const clusterOf = (k) => { let lo = k, hi = k; while (lo > 0 && C[lo].s - C[lo - 1].s < GAP) lo--; while (hi < C.length - 1 && C[hi + 1].s - C[hi].s < GAP) hi++; return [lo, hi]; };
    const out = list.map((d) => ({ ...d }));
    const moved = [];
    for (const d of out) {
      const s0 = d.s;
      d.s0 = s0; // (its input position: a stable id for the annotations, docs/architecture.md §10.4)
      // (the first conflict ahead of the signal, within 40 m: the crossing point can lie between two
      // clusters, Palackého náměstí s 12435 is 15 m after one and 12 m before the next, and the nearest
      // one was the far side of the junction)
      // (from the platform end for a signal standing along a platform: Přístaviště's stood 72 m before
      // the crossing that follows the platform, matched to nothing and ran on demand mid-platform)
      const plat = this.stops?.find((st) => d.s > (st.p0 ?? st.target - 30) - 1 && d.s < st.target + 2);
      const from = plat ? Math.max(d.s, plat.target) : d.s;
      let k = C.findIndex((c) => c.s > from - 3), best = k < 0 ? Infinity : C[k].s - from;
      if (best > 40) {
        k = -1; best = Infinity;
        C.forEach((c, i) => { const e = Math.abs(c.s - d.cross); if (e < best) { best = e; k = i; } });
        if (best > 30) k = -1;
      }
      if (k < 0) { d.demand = true; moved.push(`${Math.round(s0)} on demand`); continue; }
      const [lo, hi] = clusterOf(k);
      // matched to a pedestrian crossing (no street in its cluster) right after a street junction (its
      // last street crossing within 25 m before the signal) that has no signal of its own: the junction's
      const ownStreet = C.slice(lo, hi + 1).some((c) => c.car);
      const behind = C.filter((c) => c.car && c.s < d.s && c.s > d.s - 25);
      if (!ownStreet && behind.length) {
        const [blo, bhi] = clusterOf(C.indexOf(behind[behind.length - 1]));
        const first = edge(blo, bhi);
        if (!list.some((o) => o !== d && o.s > first - 30 && o.s < first)) {
          d.s = first - 4; d.edge = first; d.cross = C.slice(blo).find((c) => c.car).s;
          moved.push(`${Math.round(s0)}→${Math.round(d.s)} (it stood after its junction)`);
          continue;
        }
        // the junction has its signal: this one is for the junction's far-side pedestrian crossing, which
        // belongs to the same controller; no tram signal of its own after the junction (Kobylisy s 20819)
        d.drop = true;
        moved.push(`${Math.round(s0)} dropped (a far-side crossing of the junction before it)`);
        continue;
      }
      d.edge = edge(lo, hi);
      // (never past the crossing it was made for: there the conflicts missed its own junction and the
      // next one took it; line 23 s 283 went to 307, 18 m past its junction at 288, onto the stop point
      // of the next signal, which stayed red: a red pass on a GO). Not for a signal along a platform:
      // there the data's crossing is often a road-only one inside the platform and the platform end
      // decides (Palackého náměstí, Přístaviště above).
      if (!plat && d.cross !== undefined && d.edge > d.cross + 5 && d.cross > d.s) {
        moved.push(`${Math.round(s0)} kept (the first conflict at ${Math.round(d.edge)} lies past its own crossing ${Math.round(d.cross)})`);
        d.edge = d.cross; continue;
      }
      const want = d.edge - 4;
      // (forward by 25 m at most: the OSM signal is usually near its stop line; a conflict missing in our
      // data must not move it far into a junction)
      if (want > d.s + 25) { moved.push(`${Math.round(s0)} kept (its junction edge ${Math.round(want - d.s)} m on)`); d.farEdge = d.edge; d.edge = d.s + 4; continue; }
      if (Math.abs(want - d.s) > 1) { d.s = want; moved.push(`${Math.round(s0)}→${Math.round(d.s)}`); }
    }
    // two signals at one stop line are one: a tram cannot obey two heads there (one GO, one red); the
    // one whose crossing comes first stays
    const live = out.filter((d) => !d.drop).sort((a, b) => a.s - b.s);
    for (let i = 1; i < live.length; i++) {
      const a = live[i - 1], b = live[i];
      if (b.s - a.s >= 8 || a.drop) continue;
      const later = (b.cross ?? b.s) >= (a.cross ?? a.s) ? b : a;
      later.drop = true;
      moved.push(`${Math.round(later.s0)} dropped (at the stop line of ${Math.round((later === b ? a : b).s0)})`);
    }
    console.log(`signals placed: ${moved.join(', ')}`);
    this.signalMoves = moved;
    return out;
  }

  // The street crossing the route at a signalled junction (for cross traffic), as a polyline
  // through the crossing point, or null where the signal only protects a pedestrian crossing.
  _crossRoad(sCross) {
    const P = this.route.at(sCross), h = this.route.heading(sCross, 6);
    const side = (p) => h.hx * (p[1] - P.y) - h.hy * (p[0] - P.x);
    let best = null;
    for (const r of this.data.roads) {
      if (!r.c || r.w < 5 || r.b || r.f) continue;
      for (let i = 1; i < r.p.length; i++) {
        const a = r.p[i - 1], b = r.p[i];
        if (Math.min(Math.hypot(a[0] - P.x, a[1] - P.y), Math.hypot(b[0] - P.x, b[1] - P.y)) > 80) continue;
        const fa = side(a), fb = side(b);
        if (fa * fb >= 0) continue;
        const t = fa / (fa - fb), x = a[0] + (b[0] - a[0]) * t, y = a[1] + (b[1] - a[1]) * t;
        const along = Math.abs((x - P.x) * h.hx + (y - P.y) * h.hy);
        const l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
        const cos = Math.abs(((b[0] - a[0]) * h.hx + (b[1] - a[1]) * h.hy) / l);
        if (along > 15 || cos > 0.8) continue;
        if (!best || along < best.along) best = { r, i, x, y, along };
      }
    }
    if (!best) return null;
    // polyline 45 m either side of the crossing point; OSM often splits the street right at
    // the junction, so it continues into the connecting way that carries straight on
    const { r, i } = best, X0 = [best.x, best.y];
    const walk = (pts) => {
      const out = [];
      let acc = 0, prev = X0, used = new Set([r]);
      while (acc < 45) {
        for (const q of pts) { acc += Math.hypot(q[0] - prev[0], q[1] - prev[1]); out.push(q); prev = q; if (acc >= 45) break; }
        if (acc >= 45 || out.length < 1) break;
        const end = out[out.length - 1], before = out.length > 1 ? out[out.length - 2] : X0;
        const dx = end[0] - before[0], dy = end[1] - before[1], dl = Math.hypot(dx, dy) || 1;
        let next = null;
        for (const o of this.data.roads) {
          if (used.has(o) || o.f || o.p.length < 2) continue;
          for (const [first, rest] of [[o.p[0], o.p.slice(1)], [o.p[o.p.length - 1], o.p.slice(0, -1).reverse()]]) {
            if (Math.hypot(first[0] - end[0], first[1] - end[1]) > 1 || !rest.length) continue;
            const ex = rest[0][0] - end[0], ey = rest[0][1] - end[1], el = Math.hypot(ex, ey) || 1;
            if ((dx * ex + dy * ey) / (dl * el) > 0.7) { next = { o, rest }; break; }
          }
          if (next) break;
        }
        if (!next) break;
        used.add(next.o);
        pts = next.rest;
      }
      return out;
    };
    const back = walk(r.p.slice(0, i).reverse()), fwd = walk(r.p.slice(i));
    if (back.length < 1 || fwd.length < 1) return null;
    const line = [...back.reverse(), X0, ...fwd];
    const cum = [0];
    for (let k = 1; k < line.length; k++) cum.push(cum[k - 1] + Math.hypot(line[k][0] - line[k - 1][0], line[k][1] - line[k - 1][1]));
    const at = (s) => {
      s = Math.max(0, Math.min(cum[cum.length - 1], s));
      let k = 1;
      while (k < cum.length - 1 && cum[k] < s) k++;
      const a = line[k - 1], b = line[k], seg = cum[k] - cum[k - 1] || 1e-9, u = (s - cum[k - 1]) / seg;
      return { x: a[0] + (b[0] - a[0]) * u, y: a[1] + (b[1] - a[1]) * u, hx: (b[0] - a[0]) / seg, hy: (b[1] - a[1]) / seg };
    };
    const sX = cum[back.length], length = cum[cum.length - 1];
    if (sX < 15 || length - sX < 15) return null; // too short to show traffic queueing
    return { at, length, sX, w: r.w, oneway: r.o || 0 };
  }

  _updateGauntlets(dt) {
    const tram = this.tram;
    for (const G of this.gauntlets) {
      const overlaps = (front, len = tram.length) => front > G.s0 && front - len < G.s1;
      const approaching = (front) => front <= G.s0 && G.s0 - front < 150;
      const occOurs = overlaps(tram.s) || this.aiTrams.some((t) => overlaps(t.s, t.length));
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
      this._mount(mesh, ds);
      this.objects.add(mesh);
      this.distants.push({ s: ds, main: sig, mesh });
      lastS = sig.s;
    }
  }

  _initSwitches() {
    // contacts of closely following switches keep their order and at least 4 m between them
    const contacts = [];
    this.data.switches.forEach((d, k) => {
      let c = this._contactPos(d.s);
      const prev = contacts[k - 1];
      if (k > 0 && c < prev + 4 && d.s - this.data.switches[k - 1].s < 40) c = Math.min(prev + 4, d.s - PANTO_FROM_FRONT - 1);
      contacts.push(c);
    });
    this.switches = this.data.switches.map((d, k) => {
      const required = d.routeDiverging ? 'diverging' : 'straight';
      const divSide = d.routeDiverging ? d.routeSide : (d.routeSide === 'left' ? 'right' : 'left');
      const sw = {
        ...d, required, divSide,
        pos: this.rand() < 0.5 ? 'straight' : 'diverging',
        contact: contacts[k], passedContact: false, passed: false,
        indicator: makeSwitchIndicator(), marker: makeContactMarker(),
      };
      // Every facing switch is worked by an overhead contact: the driver passes under it with
      // current (turn) or coasting (straight), also right after a stop, at a signal or on a
      // gradient. Radio (IRC) control is only used where the data marks a switch as such.
      // Trailing switches are not in the data at all: the tram simply trails through them.
      sw.auto = !!d.irc || !!this.opts.autoSwitch;
      sw.marker.visible = !sw.auto;
      if (sw.auto && this.opts.autoIrc) sw.pos = required;
      const sign = sw.auto ? makeRadioSwitchSign() : makeContactSign();
      this._mount(sign, sw.auto ? d.s - 40 : sw.contact);
      this.objects.add(sign);
      place(sw.indicator, this.route, d.s - 8, -0.4, -0.26, true); // hangs from the span wire over the track
      const c = this.route.at(sw.contact);
      sw.marker.position.x = c.x;
      sw.marker.position.y += this.profile.height(sw.contact);
      sw.marker.position.z = -c.y;
      this.objects.add(sw.indicator, sw.marker);
      this._showSwitch(sw);
      return sw;
    });
  }

  // Overhead contact position: ~22 m before the switch, but never where a tram stands with
  // its pantograph at a stop or a signal (it could not pass under it coasting from rest);
  // there it is moved back before the standing area, as on the real network.
  _contactPos(sSwitch) {
    const P = PANTO_FROM_FRONT, zones = [];
    for (const st of this.stops) zones.push([st.target - 20 - P - 3, st.target + 12 - P + 2]);
    for (const g of this.signals) zones.push([g.s - 3 - 18 - P, g.s - P + 1]);
    let c = sSwitch - 22;
    for (let k = 0; k < 3; k++) {
      const z = zones.find(([a, b]) => c > a && c < b);
      if (!z) break;
      if (sSwitch - (z[1] + 4) >= 10) c = z[1] + 4;          // room after the standing area
      else if (sSwitch - (z[0] - 2) <= 75) c = z[0] - 2;     // otherwise just before it
      else break;
    }
    return c;
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
      this._mount(sign, s, { movable: true });
      this.objects.add(sign);
    }
    let inSteep = false;
    for (let s = 0; s < this.route.length; s += 10) {
      const g = this.profile.grade(s + 30);
      if (!inSteep && g < -0.055) {
        inSteep = true;
        const sign = makeGradientSign(Math.round(-this.profile.grade(s + 60) * 100) || 6);
        this._mount(sign, s, { movable: true });
        this.objects.add(sign);
      } else if (inSteep && g > -0.03) inSteep = false;
    }
  }

  // Put a signal or sign beside the track at route position s: at the kerb on the right when it
  // is close to the track (within 6.5 m), otherwise hung from the nearest span wire over the
  // track, where the driver sees it best. Never on a platform or against a facade; speed and
  // gradient signs that would stand on a platform move to just before it.
  _mount(obj, s, { movable = false, hang = false } = {}) {
    const route = this.route, C = route.catenary || [], ud = obj.userData;
    const platformAt = (x) => this.stops.find((st) => x > (st.p0 ?? st.target - 30) - 4 && x < (st.p1 ?? st.target + 2) + 2);
    let onPlatform = platformAt(s);
    if (onPlatform && movable) { s = (onPlatform.p0 ?? onPlatform.target - 30) - 6; onPlatform = platformAt(s); }
    const hidePole = () => { if (ud.pole) ud.pole.visible = false; };
    const kerb = route.kerbAt ? route.kerbAt(s, -1) : null;
    if (kerb && !kerb.wall && kerb.lat <= 6.5 && !onPlatform && !hang) {
      place(obj, route, s, -kerb.lat, 0, true);
      return;
    }
    // a signal that must hang (its place is on a platform) takes a span up to 30 m away
    const reach = hang ? 30 : 16;
    // (a cross-span; one that must hang may also use a pole's bracket arm over the track. Not one
    // after s: the nearest span was often over the junction, the signal hung in its middle (user,
    // 2026-10-24); one that must hang takes such a span only when there is none before s)
    const spans = C.filter((c) => (hang ? c.L || c.R : c.L && c.R) && Math.abs(c.s - s) <= reach).sort((a, b) => Math.abs(a.s - s) - Math.abs(b.s - s));
    const span = spans.find((c) => c.s <= s + 2) || (hang ? spans[0] : null);
    if (span && ud.boardTop !== undefined) {
      // right of the tram: its half width, the overhang of the car ends in a curve, a margin and
      // the board's own half width (it used to hang 1.15 m out, over the tram's roof edge)
      hidePole();
      const box = new THREE.Box3().setFromObject(obj);
      const half = Math.max(0.2, (box.max.x - box.min.x) / 2);
      place(obj, route, span.s, -(tramClearance(route, span.s) + half), 0, true);
      ud.hung = true;
      obj.position.y = this.profile.height(span.s) + 5.04 - ud.boardTop;
      const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.25, 4), new THREE.MeshLambertMaterial({ color: 0x333333 }));
      rod.position.y = ud.boardTop + 0.62;
      obj.add(rod);
      return;
    }
    if (kerb && !kerb.wall && kerb.lat <= 12) { place(obj, route, s, -kerb.lat, 0, true); return; }
    place(obj, route, s, -2.6, 0, true);
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
      if (this.profile.overBridge(s)) continue; // the crossing is on the road under the bridge
      const mesh = makePerson(Math.floor(this.rand() * 8));
      mesh.visible = false;
      this.objects.add(mesh);
      this.obstacles.push({ type: 'pedestrian', s, lat: this.rand() < 0.5 ? -6 : 6, mesh, state: 'idle', timer: 0, rung: false, speed: 1.3 });
    }
  }

  // Wheel/rail adhesion along the line. Rain lowers it everywhere; in autumn, crushed wet
  // leaves form short, very slippery patches (drawn as a dark leaf mash on and between the rails);
  // in snow, feet (and cars) pack snow and ice into the rails where they cross the track (the
  // pedestrian crossings, ±4 m: ~5 % of line 17; road junctions would be the next to add).
  _initAdhesion() {
    this.muBase = ADHESION[this.weather] ?? ADHESION.dry;
    this.patches = [];
    this.icy = this.weather === 'snow' ? this.data.crossings.map((s) => [s - 4, s + 4]) : [];
    if (this.weather !== 'leaves') return;
    const mat = new THREE.MeshLambertMaterial({ map: leafTexture(true), alphaTest: 0.35, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    const geo = new THREE.PlaneGeometry(1, 1);
    for (let s = 150 + this.rand() * 200; s < this.route.length - 50; s += 180 + this.rand() * 420) {
      const len = 15 + this.rand() * 45;
      this.patches.push([s, s + len]);
      // overlapping irregular smears, thickest in the middle of the patch
      for (let k = s; k < s + len; k += 1.6 + this.rand() * 1.4) {
        const smear = new THREE.Mesh(geo, mat);
        smear.rotation.set(-Math.PI / 2, 0, this.rand() * Math.PI * 2);
        const size = (1.4 + this.rand() * 1.4) * (0.6 + 0.4 * Math.sin(Math.PI * (k - s) / len));
        smear.scale.set(size, size, 1);
        const holder = new THREE.Group();
        holder.add(smear);
        place(holder, this.route, k, (this.rand() - 0.5) * 1.2, 0.27, false);
        this.objects.add(holder);
      }
    }
  }

  muAt(s) {
    let mu = this.muBase;
    if (this.weather === 'rain') mu += 0.02 * Math.sin(s / 37);
    for (const [a, b] of this.patches) if (s > a && s < b) return 0.06;
    for (const [a, b] of this.icy) if (s > a && s < b) return 0.08;
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
    for (let s = this.tram.s - this.tram.length; s <= this.tram.s + 0.1; s += 5) v = Math.min(v, this.limits.at(s));
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
        if (d > 0 && d < 200) this.msg(t('msg.notAtPlatform', { go: Math.round(st.zone[0] - this.tram.s), d: Math.round(d) }), 'warn', 5);
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

  // The driver gets out with the switch iron (stavědlo; C14; the code keeps the name crowbar): walks
  // from the cab door along the tram's right side to
  // the switch (1.6 m/s), throws it (2 s crouched over the points) and walks back; at least 9 s.
  crowbar() {
    if (this.action) return;
    const sw = this.switches.find((w) => !w.passed && w.s - this.tram.s > 0 && w.s - this.tram.s < 40);
    if (!sw) { this.msg(t('msg.noSwitch'), 'warn'); return; }
    if (this.tram.v > 0.05) { this.msg(t('msg.stopFirst'), 'warn'); return; }
    const door = this.tram.s - 1.5, walk = (sw.s - 0.6 - door) / 1.6, total = Math.max(9, 2 * walk + 2);
    const driver = makePerson(4);
    driver.children[1].material.color.set(0xff7a1a); // (the torso: a high-visibility vest)
    this.objects.add(driver);
    this.action = {
      label: t('msg.crowbar'), t: total, total, walk, door, at: sw.s - 0.6, driver,
      done: () => {
        this.objects.remove(driver);
        sw.pos = sw.pos === 'straight' ? 'diverging' : 'straight';
        this._showSwitch(sw);
        this.audio.click(0.3, 400);
        this.msg(t('msg.switchManual', { dir: t(`dirShort.${sw.pos === 'straight' ? 'straight' : sw.divSide}`) }), 'info');
      },
    };
    this._poseDriver();
  }

  // the driver out with the switch iron: out along the side of the tram, at the points, back
  _poseDriver() {
    const a = this.action;
    if (!a?.driver) return;
    const el = a.total - a.t, back = a.total - a.walk;
    let along, lat = -1.7, crouch = 1;
    if (el < a.walk) along = a.door + (a.at - a.door) * (el / a.walk);
    else if (el < back) { along = a.at; lat = -0.6; crouch = 0.7 + 0.08 * Math.sin(el * 5); }
    else along = a.at - (a.at - a.door) * Math.min(1, (el - back) / a.walk);
    const o = this.route.offset(along, lat);
    a.driver.position.set(o.x, this.profile.height(along) + 0.05, -o.y);
    a.driver.scale.y = crouch;
  }

  // Late passengers (C14): when the tram arrives they come running along the platform side from behind
  // (3.4-4 m/s, timed to arrive about runnerDelay later) to the rear door. With the doors open they
  // join the waiting passengers and board; at closed doors they wait (the driver may open again); left
  // behind when the tram goes: a penalty.
  _spawnRunners(st) {
    const tr = this.tram;
    for (let k = 0; k < st.runners; k++) {
      const mesh = makePerson(11 + st.i + k);
      this.objects.add(mesh);
      const target = tr.s - tr.length + 2.2 + k * 0.6;
      this.runners.push({ mesh, st, s: target - 6 - k * 2.5 - 3.4 * st.runnerDelay, lat: -3.4 + (k % 2) * 0.5, v: 3.4 + this.rand() * 0.6, target, state: 'run' });
    }
    this.msg(t('msg.runners', { n: st.runners }), 'info');
    st.runners = 0;
  }

  // is anybody still running for the tram at this stop (the autopilot keeps its doors open)
  runnersFor(st) { return this.runners.some((r) => r.st === st && r.state !== 'left'); }

  _updateRunners(dt) {
    const tr = this.tram;
    for (const r of this.runners) {
      if (r.state === 'run') {
        r.s = Math.min(r.target, r.s + r.v * dt);
        r.lat += (-1.9 - r.lat) * Math.min(1, dt * 0.8); // towards the platform edge by the door
        if (r.s >= r.target) r.state = 'door';
      }
      if (r.state !== 'left') {
        const open = this.doorState === 'open' || this.doorState === 'opening';
        if (r.state === 'door' && open && this._atStop(r.st) && tr.v < 0.05) { r.st.waiting++; r.state = 'aboard'; }
        else if (tr.s > r.st.zone[1] + 2 || (tr.v > 0.5 && this.doorState === 'closed')) { // (the tram leaves)
          r.state = 'left';
          this.penalty('leftBehind', 15, t('msg.runnerLeft'));
        }
      }
      const o = this.route.offset(r.s, r.lat), bob = r.state === 'run' ? Math.abs(Math.sin(r.s * 2.2)) * 0.08 : 0;
      r.mesh.position.set(o.x, this.profile.height(r.s) + 0.18 + bob, -o.y);
    }
    // aboard, or left far behind: gone
    for (const r of this.runners) if (r.state === 'aboard' || (r.state === 'left' && tr.s - r.s > 150)) this.objects.remove(r.mesh);
    this.runners = this.runners.filter((r) => !(r.state === 'aboard' || (r.state === 'left' && tr.s - r.s > 150)));
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
      this._poseDriver();
      if (this.action.t <= 0) { const a = this.action; this.action = null; a.done(); }
    } else if (this.holdTimer > 0) {
      this.holdTimer -= dt;
      tram.forcedStop = true;
    } else tram.forcedStop = false;

    const mid = tram.s - tram.length / 2;
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
    this._updateRunners(dt);
    this.input = input;
    this._updateClimate(dt);
    this._updateSwitches(prevS);
    this._updateSignals(dt, prevS);
    this._updateObstacles(dt);
    this._updateRules(dt);

    for (const m of this.messages) m.t += dt;
    this.messages = this.messages.filter((m) => m.t < m.ttl);
  }

  _atStop(st) {
    return this.tram.s >= st.zone[0] && this.tram.s <= st.zone[1];
  }

  // Where the tram front may stand to serve a stop. With the OSM platform known, the whole set
  // must stand alongside it (rear at most 3 m short of its start, front at most 4 m past its end),
  // so on a long platform a second tram can stop behind the first one; a platform shorter than
  // the set only needs the first doors at it. Otherwise 20 m behind to 12 m past the stop sign.
  _stopZone(st) {
    const L = this.tram.length;
    if (st.p0 !== undefined && st.p1 - st.p0 >= 15) {
      const hi = st.p1 + 4;
      const lo = Math.min(hi - 8, st.p1 - st.p0 + 3 >= L ? st.p0 + L - 3 : st.p1 - 8); // at least 8 m to aim at
      st.zone = [lo, hi];
      st.target = Math.max(lo + 2.5, Math.min(st.target, hi - 3));
    } else st.zone = [st.target - STOP_TOL_BEHIND, st.target + STOP_TOL_AHEAD];
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
      if (st.runners > 0) this._spawnRunners(st);
    }
    if (st.arrived && !st.alightSet) {
      st.alightSet = true;
      st.alight = Math.round(tram.passengers * st.alightFrac);
    }
    // passenger exchange through open doors
    if (at && this.doorState === 'open') {
      st.served = true;
      // three doors per car; a packed car boards slowly
      const crowd = tram.passengers > tram.capacity ? 0.45 : tram.passengers > tram.capacity * 0.75 ? 0.75 : 1;
      st.flow = (st.flow || 0) + 3 * tram.cars * 1.1 * crowd * dt;
      while (st.flow >= 1) {
        st.flow -= 1;
        if (st.alight > 0) { st.alight--; tram.passengers--; this.score += 1; }
        else if (st.waiting > 0 && tram.passengers < tram.crushCapacity) { st.waiting--; tram.passengers++; this.score += 1; }
        else break;
      }
      if (st.alight === 0 && st.waiting > 0 && tram.passengers >= tram.crushCapacity) {
        this.msg(t('msg.full', { n: st.waiting }), 'warn', 5);
        st.leftFull = st.waiting;
        st.waiting = 0;
      }
    }
    // last passengers of the old line are out: the route boxes and the HUD show the new line
    if (st.lineChange && st.arrived && st.alightSet && st.alight === 0 && this.line !== st.lineChange) this._changeLine(st.lineChange);
    // departure detection
    if (st.served && st.departClock === null && tram.v > 0.3) st.departClock = this.clock;

    const passed = tram.s > st.zone[1] + 1;
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
        sw.locked = (sw.auto ? tram.s > sw.s - 8 : tram.panto > sw.contact) && tram.s - tram.length < sw.s + 2;
        sw.indicator.userData.set(sw.pos === 'straight' ? 'straight' : sw.divSide, sw.locked && blinkOff);
      }
      if (sw.passed) continue;
      if (!sw.passedContact && prevS - PANTO_FROM_FRONT < sw.contact && tram.panto >= sw.contact) {
        sw.passedContact = true;
        if (!sw.auto) {
          sw.pos = this.contactCurrent() ? 'diverging' : 'straight';
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

  // Does current flow through the pantograph as it passes an overhead contact? Traction power
  // (the classic way), the "Výhybka" button, or the heating (seat heaters / cab heater) unless
  // the driver holds the heating cut-out button, as the T3 manual tells drivers in winter.
  heatingDraws() { const c = this.climate; return c.saloon > 0 || c.cab >= 2; }
  contactCurrent() {
    const inp = this.input || {};
    return this.tram.force > 500 || !!inp.switchBtn || (this.heatingDraws() && !inp.cutout);
  }

  setHeating(which) {
    const c = this.climate;
    if (which === 'saloon') c.saloon = (c.saloon + 1) % 3;
    if (which === 'cab') c.cab = (c.cab + 1) % 4;
    if (which === 'flap') c.flap = !c.flap;
    this.audio.click(0.15, 900);
    const key = { saloon: `msg.heatSaloon${c.saloon}`, cab: `msg.heatCab${c.cab}`, flap: c.flap ? 'msg.flapOpen' : 'msg.flapClosed' }[which];
    this.msg(t(key), 'info', 2.5);
  }

  // Indoor temperature of the saloon (per car; the set is heated alike from the first car) and
  // of the cab: heaters, waste heat of the resistors through the flap, passengers' body heat,
  // losses through the body and much larger ones while the doors are open.
  _updateClimate(dt) {
    const c = this.climate, tram = this.tram, cars = tram.cars;
    if (this.opts.toutAt) c.tout = this.opts.toutAt(this.clock);
    const seat = [0, 3000, 10000][c.saloon] * cars;
    const el = tram.electric || 0, v = Math.abs(tram.v);
    const waste = c.flap ? 0.35 * Math.max(0, -el) + 0.5 * Math.max(0, el) * Math.max(0, 1 - v / 9) : 0;
    const people = tram.passengers * 90;
    const open = this.doorState !== 'closed' ? 2500 * cars : 0;
    const windows = c.tin > 21 ? 1200 * cars : 0; // passengers open the sliding windows
    const loss = (450 * cars + windows + open) * (c.tin - c.tout);
    c.tin += ((seat + waste + people - loss) / (2.0e6 * cars)) * dt;
    const kal = [0, 0, 2000, 4000][c.cab];
    const mix = c.cab >= 1 ? 120 : 30; // the fan also stirs in saloon air
    c.tcab += ((kal - 60 * (c.tcab - c.tout) - mix * (c.tcab - c.tin)) / 1.5e5) * dt;
    // passengers mind the cold below ~12 °C, and heat the driver caused (heating or the flap
    // on a warm day): above 27 °C and more than 4 K over the outside temperature
    if (tram.passengers > 0) {
      const bad = Math.max(0, 12 - c.tin) + Math.max(0, c.tin - Math.max(27, c.tout + 4));
      if (bad > 0) {
        const pts = bad * 0.04 * dt * (0.5 + tram.passengers / 60);
        this.score -= pts;
        this.penalties.climate = (this.penalties.climate || 0) + pts;
        c.warned -= dt;
        if (c.warned <= 0) { c.warned = 90; this.msg(t(c.tin < 12 ? 'msg.cold' : 'msg.hot', { t: Math.round(c.tin) }), 'warn', 5); }
      }
    }
  }

  // the next overhead contact ahead (a contact can lie before the previous switch)
  nextContact() {
    return this.switches.find((w) => !w.auto && !w.passedContact && w.contact > this.tram.panto - 1);
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
      this._runController(sig, dt);
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

  // Junction controller (fixed cycle, see _initSignals) with tram priority: a tram detected 140 m
  // before the signal cuts the cross street's green short (after at least 8 s of it) and jumps to
  // our tram phase; a tram committed to the junction (dilemma zone: too close to stop when the GO
  // starts blinking) holds the phase up to 10 s more: ours, an AI tram ahead of us (sig.aheadCommitted)
  // or an oncoming one (sig.backCommitted; both set by traffic.js). Sets sig.state (our head: go / warn = last 3 s / stop), sig.timer (s to the
  // next change of our head) and sig.backState (the opposite direction, whose GO is the straight
  // phase but ends 3 s before it for clearance: go / warn = its last 3 s, blinking / stop).
  _runController(sig, dt) {
    const tram = this.tram, Y = sig.cycle, dist = sig.s - tram.s;
    const [a, b] = Y.ours;
    const inOurs = () => sig.t >= a && sig.t < b;
    const ourCall = dist > 0 && dist < 140;
    if ((ourCall || sig.aiRequest) && !inOurs()) {
      if (ourCall && !sig.preferred) sig.preferred = true; // (the call lamp: our tram's request)
      // cut the cross street's green short once it had its minimum: on to the tram phases (the
      // straight one first, so the opposite direction is never starved when our route turns:
      // that deadlocked the Letenská single track) through the cross street's amber and all-red
      // (D2: its cars see the lights now; the jump straight to 0 turned them from green to red)
      if (sig.t >= Y.cross + 8 && sig.t < Y.C - 6) sig.t = Y.C - 6;
    }
    if (dist < -tram.length) sig.preferred = false;
    // dilemma zone: hold GO for a tram committed to the junction
    // (committed: moving, and too close to stop comfortably before the stop point 3 m before the
    // signal, the autopilot's own test; "within 15 m + v²/1.6" held the phase 10 s for a slow tram still
    // 50 m out, and the hold was spent before it arrived, line 17 s 10251; standing: it can wait)
    const committed = dist > 0 && tram.v > 1 && dist - 3 < (tram.v * tram.v) / 1.8 + tram.v;
    // (each its own 10 s: our tram, an AI tram ahead of it, an oncoming one; holding for another tram
    // used a shared budget up, and ours then got a red it could not stop for, line 17 s 3158, 10251)
    const backWarn = sig.t >= Y.gS - 6 && sig.t < Y.gS - 3, endOurs = inOurs() && b - sig.t < 3.2;
    const holds = [['ext', endOurs && committed], ['extAhead', endOurs && sig.aheadCommitted], ['extBack', backWarn && sig.backCommitted]];
    const h = holds.find(([k, want]) => want && (sig[k] ?? 0) < 10);
    // an on-demand crossing (sig.demand: no street or footway we know there) rests on GO for the trams
    // (before both directions' blinking) until someone asks to cross, about every two minutes; then
    // one cycle runs
    const rest = sig.demand && Y.gT === 0 && !sig.request && inOurs() && sig.t >= a + 1 && b - sig.t > 6.5;
    if (rest && this.rand() < dt / 120) sig.request = true;
    if (h) sig[h[0]] = (sig[h[0]] ?? 0) + dt;
    else if (!rest) sig.t += dt;
    if (sig.t >= Y.C) { sig.t -= Y.C; sig.ext = 0; sig.extAhead = 0; sig.extBack = 0; sig.request = false; }
    const prev = sig.state;
    sig.state = inOurs() ? (b - sig.t > 3 ? 'go' : 'warn') : 'stop';
    if (sig.state === 'stop' && prev !== 'stop') sig.stopSince = this.clock;
    sig.timer = sig.state === 'go' ? b - 3 - sig.t : sig.state === 'warn' ? b - sig.t : (a - sig.t + Y.C) % Y.C;
    const back = sig.t < Y.gS - 6 ? 'go' : sig.t < Y.gS - 3 ? 'warn' : 'stop';
    if (back === 'stop' && sig.backState !== 'stop') sig.backStopSince = this.clock;
    sig.backState = back;
  }

  _crossTraffic(sig, dt) {
    const tram = this.tram;
    const X = sig.xroad;
    if (!X) return; // pedestrian signal: no crossing street
    const near = Math.abs(sig.cross - tram.s) < 400;
    const tramOnCrossing = sig.cross > tram.s - tram.length - 1 && sig.cross < tram.s + 4;
    // drivers also see a tram about to enter (e.g. one that stopped past its signal)
    const tramComing = tramOnCrossing || (sig.cross > tram.s && sig.cross < tram.s + 6 + tram.v * 2.5 && tram.v > 0.1);
    if (near && sig.state === 'stop' && sig.timer > 5) {
      sig.spawn -= dt;
      if (sig.spawn <= 0 && sig.cars.length < 4) {
        sig.spawn = 3 + this.rand() * 4;
        const dir = X.oneway || (this.rand() < 0.5 ? 1 : -1);
        const start = dir > 0 ? 0 : X.length;
        if (!sig.cars.some((c) => c.dir === dir && Math.abs(c.s - start) < 9)) {
          const mesh = makeCar(sig.seed++);
          mesh.rotation.order = 'YXZ';
          this.objects.add(mesh);
          sig.cars.push({ s: start, dir, mesh, v: 0 });
        }
      }
    }
    const ground = this.route.ground;
    for (const car of sig.cars) {
      // distance to the crossing point along the car's way (+ = still before it)
      const toX = (X.sX - car.s) * car.dir;
      // the cross street has red while the tram has GO (and 3 s of clearance before it);
      // cars wait at their stop line, and always give way to a tram on the crossing
      // (the cross street has green only in its own phase of the cycle)
      const red = sig.t < sig.cycle.cross || sig.t > sig.cycle.C - 3;
      const waiting = toX > 3.5 && toX < 12 && (red || tramComing);
      // queue behind the car in front
      let gap = Infinity;
      for (const o of sig.cars) if (o !== car && o.dir === car.dir && (o.s - car.s) * car.dir > 0) gap = Math.min(gap, (o.s - car.s) * car.dir - 4.4);
      const vt = waiting ? 0 : Math.min(9, Math.max(0, (gap - 3) * 0.9));
      car.v = vt > car.v ? Math.min(vt, car.v + dt * 2.5) : Math.max(vt, car.v - dt * 6);
      car.s += car.dir * car.v * dt;
      const p = X.at(car.s), hx = p.hx * car.dir, hy = p.hy * car.dir;
      const lane = X.oneway ? 0 : Math.max(1.5, X.w / 4); // right-hand traffic
      const x = p.x + hy * lane, y = p.y - hx * lane;
      const zf = ground.at(x + hx * 1.6, y + hy * 1.6), zb = ground.at(x - hx * 1.6, y - hy * 1.6);
      car.mesh.position.set(x, (zf + zb) / 2 + 0.1, -y);
      car.mesh.rotation.y = Math.atan2(hx, -hy);
      car.mesh.rotation.x = -Math.atan2(zf - zb, 3.2);
      if (Math.abs(toX) < 2.3 && tramOnCrossing && tram.v > 0.2 && !car.hit) {
        car.hit = true;
        this._collision(t('obj.crossingCar'));
      }
    }
    sig.cars = sig.cars.filter((c) => {
      if (c.s < -1 || c.s > X.length + 1) { this.objects.remove(c.mesh); return false; }
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
          // drives off forwards and steers out of the track to the right (no sideways sliding)
          ob.v = Math.min(8, (ob.v || 0) + 2 * dt);
          const ds = ob.v * dt, dl = Math.min(ds * 0.2, ob.lat + 4.5);
          ob.s += ds;
          ob.lat -= dl;
          ob.driven = (ob.driven || 0) + ds;
          place(ob.mesh, this.route, ob.s, ob.lat, 0, false);
          ob.mesh.rotation.y -= ds > 0 ? Math.atan2(dl, ds) : 0;
          if (ob.driven > 45) { ob.state = 'gone'; ob.mesh.visible = false; }
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
      if (ob.state !== 'gone' && Math.abs(ob.lat) < 1.55 && ob.s <= tram.s + 0.2 && ob.s >= tram.s - tram.length) {
        if (tram.v > 0.15 || ob.type === 'pedestrian') {
          ob.state = 'gone';
          ob.mesh.visible = false;
          this._collision(t(ob.type === 'parked' ? 'obj.parkedCar' : 'obj.pedestrian'), ob.type === 'pedestrian' ? 500 : 300);
        }
      }
    }
    // running into the rear of the tram ahead
    for (const ai of this.aiTrams) {
      const rear = ai.s - ai.length;
      if (!ai.hit && tram.s > rear - 0.3 && tram.s < ai.s) {
        ai.hit = true;
        tram.s = rear - 0.4;
        this._collision(t('obj.tramAhead', { line: ai.mesh.userData.line ?? '?' }), 400);
      }
      if (tram.s < rear - 5) ai.hit = false;
    }
  }

  // where the current line goes (the destination card): the stop where the run changes its number,
  // else the last stop
  get destination() {
    const i = this.segments.findIndex((g) => g.line === this.line), next = this.segments[i + 1];
    return this.data.stops[next ? next.from : this.data.stops.length - 1].name;
  }

  _changeLine(line) {
    const old = this.line;
    this.line = line;
    this.msg(t('msg.lineChange', { a: old, b: line }), 'info', 8);
    this.onLineChange?.(line, old);
  }

  // gap from our front to the rear of the next tram ahead (m), or null
  tramAheadGap() {
    let gap = null;
    for (const ai of this.aiTrams) {
      const d = ai.s - ai.length - this.tram.s;
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
        p.set(o.x, this.profile.height(along) + 0.18, -o.y);
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
