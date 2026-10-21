// Ambient life: cars in the street lanes alongside the tram, cars on the surrounding road
// network, pedestrians on footways and sidewalks, and other trams (ahead of us on our track,
// and oncoming on the opposite track). Everything fades in and out instead of popping.
import * as THREE from 'three';
import { smoothPolyline } from './route.js';
import { makeCar, makeCrowd, makeT3, placeConsist } from './models.js';
import { T3, COUPLING_GAP } from './tram.js';

const OTHER_LINES = ['9', '15', '23', '2', '18', '13', '7', '4'];
const MAX_CARS = 30, MAX_WALKERS = 90, FADE = 1.2;
const TRACK_CLEAR = 2.8; // pedestrians and cars keep this far from a track centre line

// A polyline with arc length lookups (for roads and footways).
class Path {
  constructor(pts) {
    this.p = pts;
    this.s = [0];
    for (let i = 1; i < pts.length; i++) this.s.push(this.s[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    this.length = this.s[this.s.length - 1];
  }
  at(s) {
    s = Math.max(0, Math.min(this.length, s));
    let lo = 0, hi = this.s.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (this.s[m] <= s) lo = m; else hi = m; }
    const a = this.p[lo], b = this.p[hi], seg = this.s[hi] - this.s[lo] || 1e-9, t = (s - this.s[lo]) / seg;
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
    return { x: a[0] + dx * t, y: a[1] + dy * t, hx: dx / l, hy: dy / l };
  }
}

// Fade a model in/out by its materials' opacity (each model owns its materials).
function setOpacity(obj, a) {
  obj.visible = a > 0.01;
  obj.traverse((o) => {
    if (!o.material) return;
    o.material.transparent = a < 0.999;
    o.material.opacity = a;
    o.material.depthWrite = a > 0.5;
  });
}

const key = (p) => `${Math.round(p[0])},${Math.round(p[1])}`;

// speed a car may drive at behind a leader `gap` m ahead (bumper to bumper) going `vLead`
function following(gap, vLead) {
  if (gap === null) return Infinity;
  return Math.max(0, Math.min(vLead + (gap - 8) * 0.4, (gap - 3.5) * 0.9));
}

export class Traffic {
  constructor(scene, data, route, ground, game, rand) {
    this.scene = scene;
    this.route = route;
    this.ground = ground;
    this.game = game;
    this.rand = rand;
    this.back = game.backRoute;
    this.group = new THREE.Group();
    scene.add(this.group);

    // distance to the nearest tram track centre (ours or the opposite direction)
    this.trackDist = (x, y) => {
      let d = route.distance(x, y);
      if (this.back) d = Math.min(d, this.back.distance(x, y));
      return d;
    };
    const nearTrackShare = (path, off = 0) => {
      let near = 0, n = 0;
      for (let s = 0; s <= path.length; s += 5) {
        const p = path.at(s);
        n++;
        if (this.trackDist(p.x + p.hy * off, p.y - p.hx * off) < 4) near++;
      }
      return near / Math.max(1, n);
    };

    this.roads = [];
    this.walks = [];
    this.lanes = new Map(); // street lanes beside the tram: 10 m cell -> [{lat, w, dirs}]
    this.cell = 60;
    this.index = new Map();
    const addIndex = (kind, k, path) => {
      for (let s = 0; s < path.length; s += 20) {
        const p = path.at(s);
        const kk = `${Math.floor(p.x / this.cell)},${Math.floor(p.y / this.cell)}`;
        if (!this.index.has(kk)) this.index.set(kk, []);
        this.index.get(kk).push([kind, k, s]);
      }
    };
    for (const r of data.roads) {
      if (r.p.length < 2) continue;
      const path = new Path(r.p.length > 2 ? smoothPolyline(r.p, 3, 6).pts : r.p);
      if (path.length < 15) continue;
      if (r.f) {
        // footways running along the tracks are platforms/verges: nobody strolls there
        if (path.length > 30 && nearTrackShare(path) < 0.2) { this.walks.push({ path, off: 0 }); addIndex('w', this.walks.length - 1, path); }
        continue;
      }
      // cars only on public vehicle roads: no driveways, service yards or courtyards
      if (!r.c || r.w < 5 || r.b) continue;
      let near = 0, n = 0;
      for (let s = 0; s < path.length; s += 10) { const p = path.at(s); n++; if (route.distance(p.x, p.y) < 7) near++; }
      if (near / n > 0.4) { this._addLanes(path, r); continue; }
      const road = { path, w: r.w, o: r.o || 0, ends: [key(r.p[0]), key(r.p[r.p.length - 1])] };
      this.roads.push(road);
      addIndex('r', this.roads.length - 1, path);
      if (r.w >= 6) for (const side of [1, -1]) {
        const off = side * (r.w / 2 + 1.3);
        if (nearTrackShare(path, off) < 0.2) { this.walks.push({ path, off }); addIndex('w', this.walks.length - 1, path); }
      }
    }
    // road network: which roads meet at each end point
    this.junctions = new Map();
    this.roads.forEach((r, k) => r.ends.forEach((e, end) => {
      if (!this.junctions.has(e)) this.junctions.set(e, []);
      this.junctions.get(e).push({ k, end });
    }));

    this.cars = [];
    this.walkers = [];
    this.crowd = makeCrowd(MAX_WALKERS);
    this.group.add(this.crowd);

    this.backStops = this.back ? game.stops.map((st) => {
      const o = route.offset(st.target, 3.2);
      const n = this.back.nearest(o.x, o.y);
      return n && n.d < 30 ? n.s + 8 : null;
    }).filter((s) => s !== null).sort((a, b) => a - b) : [];
    // other lines that really serve this route's stops (from GTFS)
    const other = new Set();
    const mine = new Set((game.segments || []).map((g) => g.line));
    for (const st of data.stops) for (const l of st.lines || []) if (!mine.has(l)) other.add(l);
    this.otherLines = other.size ? [...other] : OTHER_LINES;
    this.ahead = [];
    this.oncoming = [];
    this.spawnTimer = 3;
  }

  // Lanes of a street that runs along the tram: lateral position relative to our track and
  // which directions may use them (right-hand traffic, one-way streets respected).
  _addLanes(path, r) {
    for (let s = 0; s < path.length; s += 5) {
      const p = path.at(s);
      const n = this.route.nearest(p.x, p.y);
      if (!n || n.d > 12) continue;
      const q = this.route.at(n.s);
      const lat = q.hx * (p.y - q.y) - q.hy * (p.x - q.x); // + = left of our direction
      const rel = p.hx * q.hx + p.hy * q.hy > 0 ? 1 : -1;   // road drawn along / against us
      const lanes = [];
      // streets with the tracks down the middle: one car lane on each side of the track zone
      const side = r.tram ? r.w / 2 - 1.7 : r.w / 4;
      if (r.o) {
        const dir = r.o * rel;
        const offs = r.w >= 7 ? [-side, side] : [0];
        for (const o of offs) lanes.push({ lat: lat + o, dir });
      } else {
        lanes.push({ lat: lat - side, dir: 1 }, { lat: lat + side, dir: -1 });
      }
      const ok = lanes.filter((l) => Math.abs(l.lat) > TRACK_CLEAR && Math.abs(l.lat - 3.2) > TRACK_CLEAR);
      if (!ok.length) continue;
      const c = Math.floor(n.s / 10);
      if (!this.lanes.has(c)) this.lanes.set(c, []);
      this.lanes.get(c).push(...ok);
    }
  }
  laneAt(s, dir, lat = null) {
    const arr = this.lanes.get(Math.floor(s / 10));
    if (!arr) return null;
    let best = null;
    for (const l of arr) if (l.dir === dir && (best === null || (lat !== null && Math.abs(l.lat - lat) < Math.abs(best.lat - lat)))) best = l;
    return best;
  }

  dispose() { this.scene.remove(this.group); }

  update(dt, camera) {
    const tram = this.game.tram;
    const cx = camera.position.x, cy = -camera.position.z;
    this._updateStreetCars(dt, tram);
    this._updateRoadCars(dt, cx, cy);
    this._updateWalkers(dt, cx, cy);
    this._updateAhead(dt, tram);
    this._updateOncoming(dt, tram);
  }

  _carSlot() {
    let c = this.cars.find((x) => !x.active && x.alpha <= 0);
    if (!c && this.cars.length < MAX_CARS) {
      c = { mesh: makeCar(Math.floor(this.rand() * 10)), active: false, alpha: 0 };
      setOpacity(c.mesh, 0);
      this.group.add(c.mesh);
      this.cars.push(c);
    }
    return c || null;
  }

  _fade(c, dt) {
    const target = c.active ? 1 : 0;
    if (c.alpha === target) return;
    c.alpha = Math.max(0, Math.min(1, c.alpha + (target ? dt : -dt) / FADE));
    setOpacity(c.mesh, c.alpha);
  }

  // Cars in the lanes beside the tram.
  _updateStreetCars(dt, tram) {
    const street = this.cars.filter((c) => c.kind === 'street' && (c.active || c.alpha > 0));
    if (street.filter((c) => c.active).length < 8 && this.rand() < dt * 1.2) {
      const dir = this.rand() < 0.5 ? 1 : -1;
      const s = tram.s + (dir > 0 ? -60 + this.rand() * 320 : 150 + this.rand() * 280);
      const lane = this.laneAt(s, dir);
      if (lane && !street.some((c) => Math.abs(c.s - s) < 15 && c.dir === dir)) {
        const c = this._carSlot();
        if (c) Object.assign(c, { active: true, kind: 'street', s, dir, lat: lane.lat, v: 8 + this.rand() * 5, vNow: null });
      }
    }
    for (const c of street) {
      const front = street.filter((o) => o !== c && o.active && o.dir === c.dir && Math.abs(o.lat - c.lat) < 1.5 && (o.s - c.s) * c.dir > 0)
        .sort((a, b) => Math.abs(a.s - c.s) - Math.abs(b.s - c.s))[0];
      const vt = Math.min(c.v, front ? following(Math.abs(front.s - c.s) - 4.4, front.vNow ?? 0) : Infinity);
      c.vNow = this._approach(c.vNow ?? vt, vt, dt);
      c.s += c.dir * c.vNow * dt;
      const lane = this.laneAt(c.s, c.dir, c.lat);
      if (lane) c.lat += (lane.lat - c.lat) * Math.min(1, dt * 2);
      if (!lane || Math.abs(c.s - tram.s) > 480) c.active = false; // street ends: fade out
      this._fade(c, dt);
      const o = this.route.offset(c.s, c.lat);
      this._poseCar(c.mesh, o.x, o.y, o.hx * c.dir, o.hy * c.dir);
    }
  }

  // speed change with car-like acceleration (2 m/s2) and braking (up to 5 m/s2)
  _approach(v, vt, dt) {
    return vt > v ? Math.min(vt, v + 2 * dt) : Math.max(vt, v - 5 * dt);
  }

  // stand a car on the road surface: pitch with the slope, roll with the camber
  _poseCar(mesh, x, y, hx, hy) {
    const g = this.ground;
    const zf = g.at(x + hx * 1.6, y + hy * 1.6), zb = g.at(x - hx * 1.6, y - hy * 1.6);
    const zl = g.at(x - hy * 0.8, y + hx * 0.8), zr = g.at(x + hy * 0.8, y - hx * 0.8);
    mesh.rotation.order = 'YXZ';
    mesh.position.set(x, (zf + zb) / 2 + 0.12, -y);
    mesh.rotation.y = Math.atan2(hx, -hy);
    mesh.rotation.x = -Math.atan2(zf - zb, 3.2);
    mesh.rotation.z = Math.atan2(zl - zr, 1.6);
  }

  // Cars on the surrounding road network: they continue across junctions.
  _updateRoadCars(dt, cx, cy) {
    const road = this.cars.filter((c) => c.kind === 'road' && (c.active || c.alpha > 0));
    if (road.filter((c) => c.active).length < 16 && this.rand() < dt * 3) {
      const near = this._ringIndex(cx, cy, 'r', 120, 360);
      if (near) {
        const [, k, s0] = near;
        const r = this.roads[k];
        const dir = r.o ? r.o : this.rand() < 0.5 ? 1 : -1;
        const c = road.some((o) => o.active && o.road === r && Math.abs(o.s - s0) < 12) ? null : this._carSlot();
        if (c) Object.assign(c, { active: true, kind: 'road', road: r, s: s0, dir, v: 7 + this.rand() * 6, vNow: null, laneSel: this.rand() < 0.5 ? -1 : 1 });
      }
    }
    const tram = this.game.tram;
    const tp = this.route.at(tram.s - 7);
    for (const c of road) {
      if (c.active) {
        // give way to the tram where the road crosses its track
        const p0 = c.road.path.at(c.s);
        const ax = p0.x + p0.hx * c.dir * 6, ay = p0.y + p0.hy * c.dir * 6;
        const waiting = Math.hypot(p0.x - tp.x, p0.y - tp.y) < 16 && this.route.distance(ax, ay) < 3;
        // keep a distance to the car ahead in the same lane
        let gap = null, vLead = 0;
        for (const o of road) {
          if (o === c || !o.active || o.road !== c.road || o.dir !== c.dir || (c.road.o && o.laneSel !== c.laneSel)) continue;
          const d = (o.s - c.s) * c.dir - 4.4;
          if (d > -2 && (gap === null || d < gap)) { gap = d; vLead = o.vNow ?? 0; }
        }
        const vt = waiting ? 0 : Math.min(c.v, following(gap, vLead));
        c.vNow = this._approach(c.vNow ?? vt, vt, dt);
        c.s += c.dir * c.vNow * dt;
        if (c.s < 0 || c.s > c.road.path.length) this._nextRoad(c);
      }
      this._fade(c, dt);
      if (c.alpha <= 0) continue;
      const r = c.road;
      const p = r.path.at(c.s);
      const hx = p.hx * c.dir, hy = p.hy * c.dir;
      // right-hand traffic; one-way roads use their full width
      const lane = r.tram ? r.w / 2 - 1.7 : r.o ? (r.w >= 7 ? c.laneSel * r.w / 4 : 0) : Math.max(1.5, r.w / 4);
      const x = p.x + hy * lane, y = p.y - hx * lane;
      if (Math.hypot(x - cx, y - cy) > 420) c.active = false;
      this._poseCar(c.mesh, x, y, hx, hy);
    }
  }

  _nextRoad(c) {
    const r = c.road;
    const endKey = c.dir > 0 ? r.ends[1] : r.ends[0];
    const here = r.path.at(c.dir > 0 ? r.path.length : 0);
    const hx = here.hx * c.dir, hy = here.hy * c.dir;
    const opts = (this.junctions.get(endKey) || []).filter((j) => this.roads[j.k] !== r).map((j) => {
      const nr = this.roads[j.k];
      const dir = j.end === 0 ? 1 : -1;
      if (nr.o && nr.o !== dir) return null; // no entry against a one-way street
      const q = nr.path.at(j.end === 0 ? 0 : nr.path.length);
      const turn = q.hx * dir * hx + q.hy * dir * hy; // 1 = straight on
      return { nr, dir, start: j.end === 0 ? 0 : nr.path.length, score: turn + this.rand() * 0.8 };
    }).filter(Boolean).sort((a, b) => b.score - a.score);
    if (!opts.length) { c.active = false; c.s = Math.max(0, Math.min(r.path.length, c.s)); return; }
    const o = opts[0];
    c.road = o.nr; c.dir = o.dir; c.s = o.start;
  }

  // random index entry at a distance between rMin and rMax from (cx, cy)
  _ringIndex(cx, cy, kind, rMin, rMax) {
    for (let tries = 0; tries < 8; tries++) {
      const a = this.rand() * Math.PI * 2, d = rMin + this.rand() * (rMax - rMin);
      const x = cx + Math.cos(a) * d, y = cy + Math.sin(a) * d;
      const arr = this.index.get(`${Math.floor(x / this.cell)},${Math.floor(y / this.cell)}`);
      if (!arr) continue;
      const cand = arr.filter((e) => e[0] === kind);
      if (cand.length) return cand[Math.floor(this.rand() * cand.length)];
    }
    return null;
  }

  // Pedestrians: each keeps its own instance slot (stable colour); they turn back
  // instead of walking onto the tracks.
  _updateWalkers(dt, cx, cy) {
    if (!this.slots) this.slots = new Array(MAX_WALKERS).fill(null);
    const free = this.slots.indexOf(null);
    if (free >= 0 && this.rand() < dt * 8) {
      const near = this._ringIndex(cx, cy, 'w', 30, 220);
      if (near) {
        const [, k, s0] = near;
        this.slots[free] = { walk: this.walks[k], s: s0 + this.rand() * 20, dir: this.rand() < 0.5 ? 1 : -1, v: 1.1 + this.rand() * 0.5, side: (this.rand() - 0.5) * 1.2, alpha: 0 };
      }
    }
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), p3 = new THREE.Vector3(), e = new THREE.Euler();
    for (let i = 0; i < MAX_WALKERS; i++) {
      const w = this.slots[i];
      if (!w) { m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
      const pos = (s) => {
        const p = w.walk.path.at(s), off = w.walk.off + w.side;
        return { x: p.x + p.hy * off, y: p.y - p.hx * off, p };
      };
      const ahead = pos(w.s + w.dir * 1.5);
      if (this.trackDist(ahead.x, ahead.y) < TRACK_CLEAR || w.s + w.dir < 0 || w.s + w.dir > w.walk.path.length) w.dir = -w.dir;
      else w.s += w.dir * w.v * dt;
      const { x, y, p } = pos(w.s);
      const far = Math.hypot(x - cx, y - cy) > 260;
      w.alpha = Math.max(0, Math.min(1, w.alpha + (far ? -dt : dt) / FADE));
      if (far && w.alpha <= 0) { this.slots[i] = null; m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
      // fade by growing out of / sinking into the ground (instances share one material)
      const k = w.alpha;
      p3.set(x, this.ground.at(x, y) + 0.14 - (1 - k) * 1.8, -y);
      e.set(0, Math.atan2(p.hx * w.dir, -p.hy * w.dir), 0);
      q.setFromEuler(e);
      sc.set(1, 1, 1);
      m.compose(p3, q, sc);
      this.crowd.setMatrixAt(i, m);
    }
    this.crowd.count = MAX_WALKERS;
    this.crowd.instanceMatrix.needsUpdate = true;
  }

  // --------------------------------------------------------------------- other trams
  _placeTram(t, route, s, profileZ) {
    placeConsist(t.mesh, s, (q) => { const p = route.at(q); return [p.x, p.y, profileZ(q, p)]; });
  }

  // Another line serving our stop i (GTFS), and how far it shares our route: from stop i it
  // runs with us while the consecutive stops are served by it, then turns off (it fades out
  // there; it does not take its own branch). dir +1 = our direction, -1 = oncoming.
  _otherLine(i, dir) {
    const stops = this.game.data.stops, me = this.game.line;
    const cand = (stops[i]?.lines || []).filter((l) => l !== me);
    if (!cand.length) return null;
    const line = cand[Math.floor(this.rand() * cand.length)];
    let k = i;
    while (stops[k + dir] && (stops[k + dir].lines || []).includes(line)) k += dir;
    const end = this.game.stops[k].target;
    return { line, endS: k === (dir > 0 ? stops.length - 1 : 0) ? null : end + dir * 40 };
  }

  // a tram of one of the other lines serving these stops: two-car set, except heritage line 23
  _newTram(line = this.otherLines[Math.floor(this.rand() * this.otherLines.length)]) {
    const cars = line === '23' ? 1 : 2;
    const mesh = makeT3({ line, cars, detailed: this.game.opts.detailed });
    setOpacity(mesh, 0);
    this.group.add(mesh);
    return { mesh, length: T3.length * cars + COUPLING_GAP * (cars - 1) };
  }

  _tramFade(t, dt, leaving) {
    t.alpha = Math.max(0, Math.min(1, (t.alpha ?? 0) + (leaving ? -dt : dt) / FADE));
    setOpacity(t.mesh, t.alpha);
  }

  // Trams of other lines ahead of us: they stop at stops and at signals not showing GO.
  _updateAhead(dt, tram) {
    const g = this.game;
    this.spawnTimer -= dt;
    if (this.spawnTimer <= 0 && this.ahead.length < 2) {
      this.spawnTimer = 40 + this.rand() * 80;
      const st = g.stops.find((x) => x.target > tram.s + 450 && x.target < tram.s + 900 && x.i > g.nextStop);
      const other = st && this._otherLine(st.i, 1);
      if (other && !this.ahead.some((t) => Math.abs(t.s - st.target) < 60)) {
        this.ahead.push({ ...this._newTram(other.line), endS: other.endS, s: st.target, v: 0, dwell: 10 + this.rand() * 15, lastStop: st.i });
      }
    }
    const profile = this.ground.profile;
    for (const t of this.ahead) {
      let vt = Math.min(g.limits.at(t.s), g.limits.at(t.s - t.length)) / 3.6 * 0.85;
      let stopAt = null;
      const st = g.stops.find((x) => x.target > t.s + 0.5);
      if (st) stopAt = st.target;
      const sig = g.signals.find((x) => x.s > t.s + 0.5);
      if (sig && sig.state !== 'go' && sig.s - 3 < (stopAt ?? Infinity)) stopAt = sig.s - 3;
      const other = this.ahead.find((o) => o !== t && o.s > t.s);
      if (other && other.s - other.length - 6 < (stopAt ?? Infinity)) stopAt = other.s - other.length - 6;
      if (t.dwell > 0) { t.dwell -= dt; vt = 0; }
      else if (stopAt !== null) {
        const d = stopAt - t.s;
        vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * 0.9 * Math.max(0, d - 0.5))));
        if (d < 0.8 && t.v < 0.3) {
          t.v = 0;
          if (st && stopAt === st.target && t.lastStop !== st.i) { t.lastStop = st.i; t.dwell = 12 + this.rand() * 12; }
        }
      }
      const a = Math.max(-1.3, Math.min(1.0, (vt - t.v) * 0.8));
      t.v = Math.max(0, t.v + a * dt);
      t.s += t.v * dt;
      t.leaving = t.s - tram.s > 1000 || t.s > this.route.length - 20 || (t.endS !== null && t.s > t.endS);
      this._tramFade(t, dt, t.leaving);
      this._placeTram(t, this.route, t.s, (s) => profile.height(s));
    }
    this.ahead = this.ahead.filter((t) => {
      if (t.leaving && t.alpha <= 0) { this.group.remove(t.mesh); return false; }
      return true;
    });
    g.aiTrams = this.ahead;
  }

  // Oncoming trams on the opposite track; they obey the single-track (gauntlet) signals.
  _updateOncoming(dt, tram) {
    const br = this.back;
    if (!br) return;
    if (this.oncoming.length < 2 && this.rand() < dt / 25) {
      const s0 = Math.min(this.route.length - 5, tram.s + 550 + this.rand() * 400);
      const o = this.route.at(s0);
      const n = br.nearest(o.x, o.y);
      // a line that serves the stop just beyond, coming towards us
      const st = this.game.stops.find((x) => x.target > s0);
      const other = st && this._otherLine(st.i, -1);
      if (other && n && n.d < 25 && !this.oncoming.some((t) => Math.abs(t.s - n.s) < 120)) {
        this.oncoming.push({ ...this._newTram(other.line), endS: other.endS, s: n.s, v: 7, dwell: 0, served: new Set() });
      }
    }
    if (!this.backLimits) this.backLimits = br.speedLimits();
    const ground = this.ground;
    const gauntlets = this.game.gauntlets || [];
    for (const G of gauntlets) G.theirs = { requested: false, occupied: false };
    for (const t of this.oncoming) {
      let vt = Math.min(this.backLimits.at(t.s), this.backLimits.at(t.s - t.length)) / 3.6 * 0.85;
      let stopAt = this.backStops.find((s) => s > t.s + 0.5 && !t.served.has(s)) ?? null;
      const isStop = stopAt !== null;
      for (const G of gauntlets) {
        if (t.s > G.b0 && t.s - t.length < G.b1) G.theirs.occupied = true;
        if (t.s <= G.b0 && G.b0 - t.s < 150) {
          G.theirs.requested = true;
          const allowed = G.state === 'theirs' && !G.entered;
          if (!allowed && G.b0 - 4 < (stopAt ?? Infinity)) stopAt = G.b0 - 4;
        }
      }
      if (t.dwell > 0) { t.dwell -= dt; vt = 0; }
      else if (stopAt !== null) {
        const d = stopAt - t.s;
        vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * 0.9 * Math.max(0, d - 0.5))));
        if (d < 0.8 && t.v < 0.3 && isStop && this.backStops.includes(stopAt)) { t.served.add(stopAt); t.dwell = 10 + this.rand() * 10; }
      }
      const a = Math.max(-1.3, Math.min(1.0, (vt - t.v) * 0.8));
      t.v = Math.max(0, t.v + a * dt);
      t.s += t.v * dt;
      const p = br.at(t.s), me = this.route.at(tram.s);
      // past the last stop it shares with our line it turns off
      const ourS = t.endS !== null ? this.route.nearest(p.x, p.y)?.s : null;
      t.leaving = (p.x - me.x) * me.hx + (p.y - me.y) * me.hy < -150 || t.s > br.length - 20 || (ourS != null && ourS < t.endS);
      this._tramFade(t, dt, t.leaving);
      this._placeTram(t, br, t.s, (s, q) => ground.at(q.x, q.y));
    }
    this.oncoming = this.oncoming.filter((t) => {
      if (t.leaving && t.alpha <= 0) { this.group.remove(t.mesh); return false; }
      return true;
    });
  }
}
