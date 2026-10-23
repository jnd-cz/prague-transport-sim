// Ambient life: cars on the road network (a lane graph: one smooth lane per road and direction,
// connector curves through the junctions), pedestrians on footways and sidewalks, and other trams
// (ahead of us on our track, and oncoming on the opposite track). Everything fades in and out
// instead of popping.
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
  // speed (m/s) a car can take at each point: 2.5 m/s2 sideways on the curve through its
  // neighbours, at least 2.5 m/s (computed once)
  curveSpeeds() {
    if (this.vmax) return this.vmax;
    const P = this.p, n = P.length;
    this.vmax = new Float32Array(n).fill(30);
    for (let i = 1; i < n - 1; i++) {
      const a = P[i - 1], b = P[i], c = P[i + 1];
      const ab = Math.hypot(b[0] - a[0], b[1] - a[1]), bc = Math.hypot(c[0] - b[0], c[1] - b[1]), ca = Math.hypot(a[0] - c[0], a[1] - c[1]);
      const cross = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
      if (cross < 1e-6) continue;
      const R = (ab * bc * ca) / (2 * cross); // circumradius
      this.vmax[i] = Math.max(2.5, Math.sqrt(2.5 * R));
    }
    return this.vmax;
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

const CARRIAGEWAY = new Set(['road', 'parking']);

// stand a car on the drawn street surface hf(x, y) (ground level, or the deck of the bridge its road
// is on): pitch with the slope, roll with the camber
export function carPose(hf, x, y, hx, hy) {
  const zf = hf(x + hx * 1.6, y + hy * 1.6), zb = hf(x - hx * 1.6, y - hy * 1.6);
  const zl = hf(x - hy * 0.8, y + hx * 0.8), zr = hf(x + hy * 0.8, y - hx * 0.8);
  return { z: (zf + zb) / 2, pitch: Math.atan2(zf - zb, 3.2), roll: Math.atan2(zl - zr, 1.6) };
}

// things more than this apart in height are on different levels (a bridge and the road under it):
// they never meet
const LEVEL_APART = 2.5;

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
    // what a road's cars and walkers stand on: the street surface, or on a bridge (OSM bridge tag)
    // the deck it lies on, exactly as the road is drawn (ground.way)
    this.surfaceFn = (r) => {
      if (r.t) { const w = ground.way(r.way || r.p, false, true); return (x, y) => w(x, y) + 0.12; } // a road tunnel
      if (!r.b) return (x, y) => ground.surface(x, y);
      const w = ground.way(r.way || r.p, true); // (the span of the whole way, as drawn)
      return (x, y) => w(x, y) + 0.12;
    };
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
    // OSM roads meet at shared nodes, usually in the middle of a way, not only at its ends:
    // split every vehicle road at each point it shares with another road, so the network has
    // real junctions (cars used to vanish where a way simply continued past a junction)
    const vkey = (p) => `${p[0]},${p[1]}`;
    const uses = new Map();
    for (const r of data.roads) {
      if (r.f || r.p.length < 2) continue;
      for (const p of new Set(r.p.map(vkey))) uses.set(p, (uses.get(p) || 0) + 1);
    }
    const pieces = [];
    for (const r of data.roads) {
      if (r.p.length < 2) continue;
      if (r.f) { pieces.push(r); continue; }
      let cur = [r.p[0]];
      for (let i = 1; i < r.p.length; i++) {
        cur.push(r.p[i]);
        if (i < r.p.length - 1 && (uses.get(vkey(r.p[i])) || 0) > 1) { pieces.push({ ...r, p: cur, way: r.p }); cur = [r.p[i]]; }
      }
      pieces.push({ ...r, p: cur, way: r.p });
    }
    // centre lines of all vehicle ways (20 m cells), for splitting a carriageway two ways share
    this.wayIdx = new Map();
    for (const r of pieces) {
      if (r.f || !r.c || r.p.length < 2) continue;
      for (let i = 1; i < r.p.length; i++) {
        const sg = { a: r.p[i - 1], b: r.p[i], src: r };
        const x0 = Math.min(sg.a[0], sg.b[0]), x1 = Math.max(sg.a[0], sg.b[0]), y0 = Math.min(sg.a[1], sg.b[1]), y1 = Math.max(sg.a[1], sg.b[1]);
        for (let ix = Math.floor(x0 / 20); ix <= Math.floor(x1 / 20); ix++) for (let iy = Math.floor(y0 / 20); iy <= Math.floor(y1 / 20); iy++) {
          const k = ix * 100003 + iy;
          if (!this.wayIdx.has(k)) this.wayIdx.set(k, []);
          this.wayIdx.get(k).push(sg);
        }
      }
    }
    this.jpos = new Map(); // junction key -> [x, y]
    for (const r of pieces) {
      if (r.p.length < 2) continue;
      const path = new Path(r.p.length > 2 ? smoothPolyline(r.p, 3, 6).pts : r.p);
      if (path.length < (r.f ? 15 : 2)) continue;
      if (r.f) {
        if (r.t) continue; // (pedestrian underpasses: nobody walks under the ground here)
        // footways running along the tracks are platforms/verges: nobody strolls there
        if (path.length > 30 && nearTrackShare(path) < 0.2) { this.walks.push({ path, off: 0, hf: this.surfaceFn(r), deck: !!r.b }); addIndex('w', this.walks.length - 1, path); }
        continue;
      }
      // cars only on public vehicle roads: no driveways, service yards or courtyards
      if (!r.c || r.w < 5) continue;
      if (r.t) r.way = r.way || r.p; // (a tunnel spans between its own portals)
      let near = 0, n = 0;
      for (let s = 0; s < path.length; s += 10) { const p = path.at(s); n++; if (route.distance(p.x, p.y) < 7) near++; }
      // the street the tram runs in: an ordinary part of the network (its cars drive alongside us),
      // its sidewalks get no extra walkers (the tram street's own footways cover them)
      const along = near / n > 0.4;
      const road = { src: r, path, w: r.w, o: r.o || 0, tram: r.tram, b: r.b || 0, t: r.t || 0, hf: this.surfaceFn(r), ends: [key(r.p[0]), key(r.p[r.p.length - 1])] };
      this._fitRoad(road);
      this.jpos.set(road.ends[0], r.p[0]); this.jpos.set(road.ends[1], r.p[r.p.length - 1]);
      this.roads.push(road);
      if (path.length >= 15) addIndex('r', this.roads.length - 1, path); // spawn only on real streets
      if (along) continue;
      // sidewalks: 1.5 m beyond each kerb (the surveyed one where it exists, so walkers are not in
      // the lanes the cars drive)
      // (not along a bridge: only the carriageway is drawn there, its footways are OSM ways of their own;
      // not along a road tunnel: nobody walks under the hill beside the cars)
      if (r.w >= 6 && !r.b && !r.t) for (const side of [1, -1]) {
        const pts = [];
        for (let s = 0; s <= path.length; s += 3) {
          const p = path.at(Math.min(s, path.length)), k = this.kerbs(road, s);
          const off = side > 0 ? k.hi + 1.5 : k.lo - 1.5;
          pts.push([p.x + p.hy * off, p.y - p.hx * off]);
        }
        if (pts.length < 3) continue;
        const walk = new Path(smoothPolyline(pts, 1, 4).pts);
        if (nearTrackShare(walk) < 0.2) { this.walks.push({ path: walk, off: 0, hf: road.hf, deck: !!road.b }); addIndex('w', this.walks.length - 1, walk); }
      }
    }
    this._buildLanes();

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

  // Where the surveyed DTM carriageway is known, fit the road to it: every 4 m, scan across the
  // OSM centre line for the carriageway it lies in (a track bed in the middle of a divided street
  // counts, so both halves belong to it; else the nearest carriageway within 8 m) and keep its two
  // kerb lines, smoothed along the road. Junction squares and plazas (much wider than the street)
  // and places without DTM keep the OSM centre line and width.
  _fitRoad(road) {
    const dtm = this.ground.dtm;
    if (!dtm || road.b || road.t) return; // (the survey's classes are those of the ground level)
    const L = road.path.length, n = Math.floor(L / 4) + 1;
    const lo = new Array(n).fill(null), hi = new Array(n).fill(null);
    let any = false;
    for (let i = 0; i < n; i++) {
      const p = road.path.at(Math.min(L, i * 4));
      if (!dtm.covered(p.x, p.y)) continue;
      const on = [];
      for (let l = -16; l <= 16; l += 0.5) {
        const c = dtm.classAt(p.x + p.hy * l, p.y - p.hx * l);
        on.push(CARRIAGEWAY.has(c) ? 1 : c === 'tram' ? 2 : 0);
      }
      // the run around the centre (index 32), else the nearest within 8 m
      let k = 32;
      for (let d = 0; d <= 16 && !on[k]; d++) k = on[32 + d] ? 32 + d : on[32 - d] ? 32 - d : 32;
      if (!on[k]) continue;
      let a = k, b = k;
      // single 0.5 m holes (paint, a manhole cover area) don't end the carriageway
      while (a > 0 && (on[a - 1] || (a > 1 && on[a - 2]))) a--;
      while (b < on.length - 1 && (on[b + 1] || (b < on.length - 2 && on[b + 2]))) b++;
      while (a < b && on[a] !== 1) a++; // a track bed at the side is not for cars
      while (b > a && on[b] !== 1) b--;
      if (on[a] !== 1) continue;
      const width = (b - a) * 0.5 + 0.5;
      if (width > Math.max(road.w * 2.2, road.w + 9) || a === 0 || b === on.length - 1) continue; // junction, plaza
      lo[i] = a * 0.5 - 16.25;
      hi[i] = b * 0.5 - 15.75;
      // another way running alongside inside the same surveyed carriageway (a divided street mapped
      // as two ways, a slip lane): each takes its own side, split halfway between the centre lines
      for (const o of this._parallelWays(road, p)) {
        if (o > 1 && o < hi[i]) hi[i] = Math.max(o / 2, lo[i] + 2.5);
        if (o < -1 && o > lo[i]) lo[i] = Math.min(o / 2, hi[i] - 2.5);
      }
      any = true;
    }
    if (!any) return;
    // fill the gaps (blend back to the OSM line over 12 m), then smooth over ±8 m
    const fill = (arr, def) => arr.map((v, i) => {
      if (v !== null) return v;
      let best = def, bd = 4;
      for (let d = 1; d < 4; d++) {
        if (arr[i - d] != null && d < bd) { best = def + (arr[i - d] - def) * (1 - d / 4); bd = d; }
        if (arr[i + d] != null && d < bd) { best = def + (arr[i + d] - def) * (1 - d / 4); bd = d; }
      }
      return best;
    });
    const smooth = (arr) => arr.map((_, i) => { let s = 0, m = 0; for (let d = -2; d <= 2; d++) if (arr[i + d] !== undefined) { s += arr[i + d]; m++; } return s / m; });
    road.fitLo = smooth(fill(lo, -road.w / 2));
    road.fitHi = smooth(fill(hi, road.w / 2));
  }
  // lateral offsets (+ = right) of other vehicle ways running alongside `road` at point p (within 12 m,
  // heading within ~35°), from the centre-line index built in the constructor
  _parallelWays(road, p) {
    const out = [], cx = Math.floor(p.x / 20), cy = Math.floor(p.y / 20), seen = new Set();
    for (let i = cx - 1; i <= cx + 1; i++) for (let j = cy - 1; j <= cy + 1; j++) {
      for (const sg of this.wayIdx.get(i * 100003 + j) || []) {
        if (sg.src === road.src || !!sg.src.b !== !!road.b || !!sg.src.t !== !!road.t || seen.has(sg)) continue;
        seen.add(sg);
        const dx = sg.b[0] - sg.a[0], dy = sg.b[1] - sg.a[1], l = Math.hypot(dx, dy) || 1;
        if (Math.abs((dx * p.hx + dy * p.hy) / l) < 0.82) continue;
        // where the line through p across the road meets this segment
        const nx = p.hy, ny = -p.hx, den = dx * ny - dy * nx;
        if (Math.abs(den) < 1e-9) continue;
        const t = ((p.x - sg.a[0]) * ny - (p.y - sg.a[1]) * nx) / den;
        if (t < 0 || t > 1) continue;
        const qx = sg.a[0] + dx * t, qy = sg.a[1] + dy * t, off = (qx - p.x) * nx + (qy - p.y) * ny;
        if (Math.abs(off) < 12) out.push(off);
      }
    }
    return out;
  }
  // the two kerb lines of a road at s (m from its centre line, + = right of the road's direction):
  // fitted to the surveyed carriageway where it exists, else the OSM width
  kerbs(r, s) {
    if (!r.fitLo) return { lo: -r.w / 2, hi: r.w / 2 };
    const f = Math.max(0, Math.min(r.fitLo.length - 1, s / 4)), i = Math.floor(f), j = Math.min(r.fitLo.length - 1, i + 1), u = f - i;
    return { lo: r.fitLo[i] * (1 - u) + r.fitLo[j] * u, hi: r.fitHi[i] * (1 - u) + r.fitHi[j] * u };
  }

  // lateral position (+ = right of the driving direction) of a car on a road at s. Right-hand
  // traffic: 1.8 m in from the right kerb, but never closer than 1.2 m to the middle of a two-way
  // road; one-way roads from 7 m wide have two lanes.
  laneOffset(r, s, dir, sel = 1) {
    let { lo, hi } = this.kerbs(r, s);
    if (dir < 0) [lo, hi] = [-hi, -lo]; // the car's own right/left
    const w = hi - lo, mid = (lo + hi) / 2;
    if (r.o) return w < 7 ? mid : sel > 0 ? hi - 1.8 : lo + 1.8;
    return Math.max(hi - 1.8, mid + 1.2);
  }

  // ------------------------------------------------------------------ lane graph
  // Every road gets one lane per driving direction (two on one-way roads from 7 m wide): a smooth
  // curve of its own at the lane position (laneOffset: fitted to the surveyed kerbs where they
  // exist), trimmed back from both junctions. A car follows its lane's own tangent, so it never
  // moves sideways; through a junction a connector curve leads from the end of one lane to the
  // start of the next.
  _buildLanes() {
    this.laneList = [];
    this.lanesFrom = new Map(); // junction key -> lanes starting there
    this.lanesTo = new Map();   // junction key -> lanes ending there
    this.connectors = new Map();
    this.conflicts = new Map();
    this.laneGrid = new Map(); // lane points in 4 m cells (is a point in a lane?)
    const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
    this.roads.forEach((r, k) => {
      r.lanes = [];
      const L = r.path.length, trim = Math.min(5, L * 0.2);
      const dirs = r.o ? [r.o] : [1, -1];
      const sels = r.o && r.w >= 7 ? [-1, 1] : [1];
      for (const dir of dirs) for (const sel of sels) {
        const pts = [], n = Math.max(2, Math.ceil((L - 2 * trim) / 2));
        for (let i = 0; i <= n; i++) {
          const u = trim + ((L - 2 * trim) * i) / n, sr = dir > 0 ? u : L - u;
          const p = r.path.at(sr), hx = p.hx * dir, hy = p.hy * dir, off = this.laneOffset(r, sr, dir, sel);
          pts.push([p.x + hy * off, p.y - hx * off]);
        }
        const path = new Path(pts.length > 3 ? smoothPolyline(pts, 1, 6).pts : pts);
        const lane = { id: this.laneList.length, road: r, k, dir, sel, trim, path, from: r.ends[dir > 0 ? 0 : 1], to: r.ends[dir > 0 ? 1 : 0] };
        this.laneList.push(lane);
        r.lanes.push(lane);
        for (const q of path.p) {
          const key = Math.floor(q[0] / 4) * 100003 + Math.floor(q[1] / 4);
          if (!this.laneGrid.has(key)) this.laneGrid.set(key, []);
          this.laneGrid.get(key).push(q);
        }
        push(this.lanesFrom, lane.from, lane);
        push(this.lanesTo, lane.to, lane);
      }
    });
  }

  // whether a connector passes within a car's width of the last (end) or first 5 m of a lane, where a
  // car stands waiting at the junction or has just left it
  _nearLaneEnd(conn, lane, end) {
    const key = `${conn.id}|${lane.id}|${end ? 1 : 0}`;
    if (this.conflicts.has(key)) return this.conflicts.get(key);
    const L = lane.path.length, pts = [];
    for (let s = end ? Math.max(0, L - 5) : 0; s <= (end ? L : Math.min(L, 5)); s += 1) { const q = lane.path.at(s); pts.push([q.x, q.y]); }
    let hit = false;
    for (const a of conn.path.p) {
      for (const b of pts) if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 2.4) { hit = true; break; }
      if (hit) break;
    }
    this.conflicts.set(key, hit);
    return hit;
  }

  // whether (x, y) lies in a car lane (within 1.6 m of a lane's centre line)
  inLane(x, y) {
    const cx = Math.floor(x / 4), cy = Math.floor(y / 4);
    for (let i = cx - 1; i <= cx + 1; i++) for (let j = cy - 1; j <= cy + 1; j++) {
      for (const q of this.laneGrid.get(i * 100003 + j) || []) if (Math.abs(q[0] - x) < 1.6 && Math.abs(q[1] - y) < 1.6 && Math.hypot(q[0] - x, q[1] - y) < 1.6) return true;
    }
    return false;
  }

  // lanes a car on lane `a` may take at the junction it drives to: another road, no U-turn, not
  // against a one-way street (those have no lane in that direction)
  nextLanes(a) {
    const here = a.path.at(a.path.length);
    return (this.lanesFrom.get(a.to) || []).filter((b) => {
      if (b.road === a.road) return false;
      const q = b.path.at(0);
      return q.hx * here.hx + q.hy * here.hy > -0.6;
    });
  }

  _chooseNext(a) {
    const here = a.path.at(a.path.length);
    let best = null, bestScore = -Infinity;
    for (const b of this.nextLanes(a)) {
      const q = b.path.at(0);
      const score = q.hx * here.hx + q.hy * here.hy + this.rand() * 0.8 + (b.sel === a.sel ? 0.1 : 0); // 1 = straight on
      if (score > bestScore) { best = b; bestScore = score; }
    }
    return best;
  }

  // the connector from the end of lane a to the start of lane b (cubic Hermite with the lanes'
  // tangents), or null where they already touch
  connector(a, b) {
    const key = `${a.id}>${b.id}`;
    if (this.connectors.has(key)) return this.connectors.get(key);
    const p0 = a.path.at(a.path.length), p1 = b.path.at(0);
    const d = Math.hypot(p1.x - p0.x, p1.y - p0.y);
    let c = null;
    if (d >= 1) {
      const pts = [], n = Math.max(3, Math.ceil(d / 1.2));
      for (let i = 0; i <= n; i++) {
        const t = i / n, t2 = t * t, t3 = t2 * t;
        const h00 = 2 * t3 - 3 * t2 + 1, h10 = t3 - 2 * t2 + t, h01 = -2 * t3 + 3 * t2, h11 = t3 - t2;
        pts.push([h00 * p0.x + h10 * d * p0.hx + h01 * p1.x + h11 * d * p1.hx, h00 * p0.y + h10 * d * p0.hy + h01 * p1.y + h11 * d * p1.hy]);
      }
      c = { id: key, from: a, to: b, at: a.to, path: new Path(pts) };
      // its surface: the two lanes' surfaces, blended along it (they meet at a bridge end)
      const ha = a.road.hf, hb = b.road.hf;
      c.hf = ha === hb || !(a.road.b || b.road.b) ? ha : (x, y) => {
        const t = Math.max(0, Math.min(1, ((x - p0.x) * (p1.x - p0.x) + (y - p0.y) * (p1.y - p0.y)) / (d * d)));
        return ha(x, y) * (1 - t) + hb(x, y) * t;
      };
    }
    this.connectors.set(key, c);
    return c;
  }

  // two connectors through one junction that cross or come closer than a car is wide (cars from
  // the same lane follow each other instead)
  _conflict(c1, c2) {
    if (!c1 || !c2 || c1 === c2 || c1.from === c2.from) return false;
    const key = c1.id < c2.id ? `${c1.id}|${c2.id}` : `${c2.id}|${c1.id}`;
    if (this.conflicts.has(key)) return this.conflicts.get(key);
    let hit = c1.to === c2.to; // merging into the same lane
    for (const a of c1.path.p) {
      if (hit) break;
      for (const b of c2.path.p) if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 2.4) { hit = true; break; }
    }
    this.conflicts.set(key, hit);
    return hit;
  }

  dispose() { this.scene.remove(this.group); }

  update(dt, camera) {
    const tram = this.game.tram;
    const cx = camera.position.x, cy = -camera.position.z;
    this._carsOnTracks();
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

  // speed change with car-like acceleration (2 m/s2) and braking (up to 5 m/s2)
  _approach(v, vt, dt) {
    return vt > v ? Math.min(vt, v + 2 * dt) : Math.max(vt, v - 5 * dt);
  }

  _poseCar(mesh, x, y, hx, hy, hf = (u, v) => this.ground.surface(u, v)) {
    const p = carPose(hf, x, y, hx, hy);
    mesh.rotation.order = 'YXZ';
    mesh.position.set(x, p.z, -y);
    mesh.rotation.y = Math.atan2(hx, -hy);
    mesh.rotation.x = -p.pitch;
    mesh.rotation.z = p.roll;
  }

  // Cars on the lane graph: along a lane, through a junction on a connector, on along the next
  // lane. They keep their distance to the car ahead (also across the junction), give way at
  // junctions to cars on crossing connectors (the nearest first) and to the tram where the road
  // crosses its track, and roll on while fading out where the data ends.
  _updateRoadCars(dt, cx, cy) {
    const cars = this.cars.filter((c) => c.kind === 'road' && (c.active || c.alpha > 0));
    if (cars.filter((c) => c.active).length < 22 && this.rand() < dt * 4) {
      const near = this._ringIndex(cx, cy, 'r', 60, 360);
      if (near) {
        const [, k, s0] = near;
        const r = this.roads[k];
        const lane = r.lanes[Math.floor(this.rand() * r.lanes.length)];
        if (lane) {
          const s = Math.max(0, Math.min(lane.path.length, (lane.dir > 0 ? s0 : r.path.length - s0) - lane.trim));
          const c = cars.some((o) => o.active && o.path === lane.path && Math.abs(o.s - s) < 12) ? null : this._carSlot();
          if (c) Object.assign(c, { id: undefined, active: true, kind: 'road', lane, road: r, dir: lane.dir, conn: null, next: undefined, path: lane.path, s, v: 7 + this.rand() * 6, vNow: null, coast: null });
        }
      }
    }
    const tram = this.game.tram;
    const tp = this.route.at(tram.s - 7);
    const live = cars.filter((c) => c.active);
    const obstacles = this._pathObstacles();
    live.forEach((c) => {
      c.id = c.id ?? (this.nextCarId = (this.nextCarId || 0) + 1); // unique: the priority tie-breaks use it
      c.toEnd = c.conn ? 0 : c.path.length - c.s;
      // the next lane is chosen ahead of time, so the following distance can look across the junction
      if (!c.conn && c.next === undefined && c.toEnd < 40) c.next = this._chooseNext(c.lane);
      c.plan = !c.conn && c.next ? this.connector(c.lane, c.next) : null;
    });
    // the other cars as obstacles too (beyond following in one lane: turning across, waiting in
    // the mouth of a junction, lanes that touch)
    for (const o of live) {
      const p = o.path.at(o.s);
      obstacles.push({ car: o, x: p.x, y: p.y, z: o.z, hx: p.hx, hy: p.hy, l: 2.2, w: 0.9, vx: p.hx * (o.vNow ?? 0), vy: p.hy * (o.vNow ?? 0) });
    }
    // first pass: what each car sees ahead; when two cars see each other (crossing paths), the
    // one with the lower id goes first instead of both waiting
    for (const c of live) c.seen = this._obstacleAhead(c, this._seq(c), obstacles);
    // (and so for any cycle of cars waiting for each other: three cars in a junction each waited for
    // the next, line 9 s 13284; the lowest id of the cycle goes)
    for (const c of live) {
      const ring = [c];
      for (let o = c.seen?.car; o && ring.length < 8; o = o.seen?.car) {
        if (o === c) {
          const first = ring.reduce((u, v) => (v.id < u.id ? v : u));
          first.seen = null;
          break;
        }
        if (ring.includes(o)) break;
        ring.push(o);
      }
    }
    for (const c of cars) {
      if (c.active) {
        // give way to the tram where the road crosses its track
        const p0 = c.path.at(c.s);
        const ax = p0.x + p0.hx * 6, ay = p0.y + p0.hy * 6;
        // (only a car whose road crosses the track: one driving along it follows the tram instead;
        // not where our track passes over the road on a bridge)
        const across = Math.abs(p0.hx * tp.hx + p0.hy * tp.hy) < 0.7;
        const waiting = across && Math.hypot(p0.x - tp.x, p0.y - tp.y) < 16 && this.route.distance(ax, ay) < 3 && !this.ground.profile.overBridge(tram.s - 7)
          && !(c.z !== undefined && Math.abs(c.z - this.ground.profile.height(tram.s - 7)) > LEVEL_APART);
        // the car ahead: on this path, else across the junction on the connector and the next lane
        const seq = this._seq(c);
        let gap = null, vLead = 0;
        for (const o of live) {
          if (o === c) continue;
          for (const [path, off] of seq) {
            if (o.path !== path) continue;
            const d = off + o.s - 4.4;
            if (d > -2 && (path !== c.path || o.s > c.s) && (gap === null || d < gap)) { gap = d; vLead = o.vNow ?? 0; }
          }
        }
        // trams and walkers on the path ahead (shared lanes on the tracks, a tram stopped at a
        // stop, someone crossing): stop or follow behind
        const ob = c.seen;
        if (ob && (gap === null || ob.gap < gap)) { gap = ob.gap; vLead = ob.v; }
        // junctions, from braking distance on: wait while a car is on a crossing connector, nearer
        // to its own crossing one, or standing at the mouth of a lane the connector passes close to
        let jStop = null;
        const look = Math.max(9, ((c.vNow ?? 0) ** 2) / 8 + 3);
        if (c.plan && c.toEnd < look) {
          const J = c.plan.at;
          // (a car in the junction that is itself waiting for this one does not block it; and a car
          // only enters when its exit lane has room: it never stops inside the junction)
          const exitFull = live.some((o) => o !== c && o.path === c.next.path && o.s < 7);
          const blocked = exitFull || live.some((o) => o !== c && (
            (o.conn && o.conn.at === J && this._conflict(o.conn, c.plan) && o.seen?.car !== c)
            || (!o.conn && o.plan && o.plan.at === J && o.toEnd < look && this._conflict(o.plan, c.plan)
              // (a car whose own path is blocked does not hold its turn: one close behind an obstacle, or
              // stopped behind a stopped one; line 9 s 8679, three cars waited for each other that way)
              && !(o.seen && (o.seen.gap < 4 || ((o.vNow ?? 0) < 0.3 && o.seen.v < 0.3)))
              && (o.toEnd < c.toEnd - 0.05 || (Math.abs(o.toEnd - c.toEnd) <= 0.05 && o.id < c.id)))
            || (!o.conn && o.lane !== c.lane && o.lane.to === J && o.toEnd < 5 && !(o.plan && o.plan.at === J) && this._nearLaneEnd(c.plan, o.lane, true))
            || (!o.conn && o.lane !== c.next && o.lane.from === J && o.s < 5 && this._nearLaneEnd(c.plan, o.lane, false))));
          if (blocked && c.toEnd > 1.5) jStop = c.toEnd - 2;
        }
        // slow down for curves and turns ahead (braking at 3 m/s2), across the junction too
        let vCurve = Infinity;
        for (const [path, off] of seq) {
          const vm = path.curveSpeeds();
          for (let i = 0; i < path.p.length; i++) {
            const d = off + path.s[i];
            if (d < -1 || d > 30) continue;
            vCurve = Math.min(vCurve, Math.sqrt(vm[i] * vm[i] + 6 * Math.max(0, d)));
          }
        }
        const vt = waiting ? 0 : Math.min(c.v, vCurve, following(gap, vLead), jStop === null ? Infinity : following(jStop, 0));
        c.vNow = this._approach(c.vNow ?? vt, vt, dt);
        c.s += c.vNow * dt;
        while (c.active && c.s > c.path.length) this._advance(c);
      }
      this._fade(c, dt);
      if (c.alpha <= 0) continue;
      if (!c.active && c.coast) {
        const k = c.coast;
        k.d += (c.vNow || 6) * dt;
        this._poseCar(c.mesh, k.x + k.hx * k.d, k.y + k.hy * k.d, k.hx, k.hy, c.lane.road.hf);
        continue;
      }
      const p = c.path.at(c.s);
      if (Math.hypot(p.x - cx, p.y - cy) > 420) c.active = false;
      this._poseCar(c.mesh, p.x, p.y, p.hx, p.hy, c.conn ? c.conn.hf : c.lane.road.hf);
      c.z = c.mesh.position.y;
    }
  }

  // Cars on our track and on the opposite one (within 1.6 m of a track centre: the car body then
  // overlaps a tram), as route positions: trams stop behind them (shared lanes, a car queuing on
  // the tracks). this.game.carsOnTrack: [{s, v}] along our route, carsOnBack along the opposite one.
  _carsOnTracks() {
    const ours = [], back = [];
    for (const c of this.cars) {
      if (!c.active || c.alpha < 0.5 || !c.path) continue;
      const p = c.path.at(c.s);
      // only cars going the tram's way hold it up (one facing it waits for the tram instead)
      const n = this.route.nearest(p.x, p.y);
      // (a car on the road under our bridge, or on a bridge over the track, is not on it)
      if (n && c.z !== undefined && Math.abs(c.z - this.ground.profile.height(n.s)) > LEVEL_APART) continue;
      if (n && n.d < 1.6) { const h = this.route.at(n.s); if (h.hx * p.hx + h.hy * p.hy > 0.3) ours.push({ s: n.s, v: c.vNow ?? 0 }); }
      if (this.back) {
        const b = this.back.nearest(p.x, p.y);
        if (b && b.d < 1.6) { const h = this.back.at(b.s); if (h.hx * p.hx + h.hy * p.hy > 0.3) back.push({ s: b.s, v: c.vNow ?? 0 }); }
      }
    }
    this.game.carsOnTrack = ours;
    this.carsOnBack = back;
  }

  // the paths a car drives next, each with the distance from the car to its start
  _seq(c) {
    const seq = [[c.path, -c.s]];
    if (c.conn) seq.push([c.conn.to.path, c.conn.path.length - c.s]);
    else if (c.next) {
      const off = c.path.length - c.s;
      if (c.plan) seq.push([c.plan.path, off], [c.next.path, off + c.plan.path.length]);
      else seq.push([c.next.path, off]);
    }
    return seq;
  }

  // Everything a car must not drive into, as boxes with a velocity: the cars of our tram and of the
  // AI trams, and the walkers.
  _pathObstacles() {
    const out = [], g = this.game, tram = g.tram;
    for (let k = 0; k < (tram.cars || 1); k++) {
      const s = tram.s - 0.6 - 7.6 - k * 15.2, p = this.route.at(s), h = this.route.heading(s, 3);
      out.push({ x: p.x, y: p.y, z: this.ground.profile.height(s), hx: h.hx, hy: h.hy, l: 7.2, w: 1.3, vx: h.hx * tram.v, vy: h.hy * tram.v });
    }
    for (const t of [...this.ahead, ...this.oncoming]) {
      if ((t.alpha ?? 0) < 0.3) continue;
      for (const m of t.mesh.userData.cars) {
        const hx = Math.sin(m.rotation.y), hy = -Math.cos(m.rotation.y);
        out.push({ x: m.position.x, y: -m.position.z, z: m.position.y, hx, hy, l: 7.2, w: 1.3, vx: hx * t.v, vy: hy * t.v });
      }
    }
    for (const w of this.slots || []) {
      if (w && w.alpha > 0.5 && w.x !== undefined) out.push({ x: w.x, y: w.y, z: w.z, hx: 1, hy: 0, l: 0.4, w: 0.4, vx: 0, vy: 0 });
    }
    return out;
  }

  // the first obstacle on a car's path within 40 m: gap to it (bumper to bumper) and its speed
  // along the car's heading
  _obstacleAhead(c, seq, obstacles) {
    const p0 = c.path.at(c.s);
    // (something whose centre is behind the car can never be in its way: a car beside the front of
    // a tram waited for it while the tram waited for the car)
    // (nor something on another level: the bridge above, the road below)
    const near = obstacles.filter((o) => Math.abs(o.x - p0.x) < 50 && Math.abs(o.y - p0.y) < 50 && (o.x - p0.x) * p0.hx + (o.y - p0.y) * p0.hy > -1
      && !(o.z !== undefined && c.z !== undefined && Math.abs(o.z - c.z) > LEVEL_APART));
    if (!near.length) return null;
    for (let d = 2; d <= 40; d += 2) {
      let q = null;
      for (const [path, off] of seq) {
        const ls = d - off;
        if (ls >= 0 && ls <= path.length) { q = path.at(ls); break; }
      }
      if (!q) return null;
      for (const o of near) {
        if (o.car === c) continue;
        const dx = q.x - o.x, dy = q.y - o.y;
        if (Math.abs(dx * o.hx + dy * o.hy) < o.l + 2.2 && Math.abs(-dx * o.hy + dy * o.hx) < o.w + 1.0) {
          return { gap: d - 2.6, v: Math.max(0, o.vx * q.hx + o.vy * q.hy), car: o.car };
        }
      }
    }
    return null;
  }

  // past the end of the current path: lane -> connector -> next lane; at the edge of the data the
  // car rolls on straight while fading out
  _advance(c) {
    const over = c.s - c.path.length;
    if (c.conn) {
      c.lane = c.conn.to; c.conn = null; c.next = undefined;
    } else {
      if (c.next === undefined) c.next = this._chooseNext(c.lane);
      if (!c.next) {
        const end = c.path.at(c.path.length);
        c.active = false;
        c.s = c.path.length;
        c.coast = { x: end.x, y: end.y, hx: end.hx, hy: end.hy, d: over };
        return;
      }
      const conn = this.connector(c.lane, c.next);
      if (conn) c.conn = conn;
      else { c.lane = c.next; c.next = undefined; }
    }
    c.path = c.conn ? c.conn.path : c.lane.path;
    c.road = c.lane.road; c.dir = c.lane.dir;
    c.s = over;
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
      // turn back before the tracks or at the end of the path, but never while standing in a car
      // lane (finish crossing first: a walker turning back and forth there blocked the cars)
      // (at the end of its path a walker always turns back into it; it may have spawned past the end)
      if (w.s > w.walk.path.length) { w.s = w.walk.path.length; w.dir = -1; }
      if (w.s < 0) { w.s = 0; w.dir = 1; }
      // (after turning at the end of its path a walker commits to walking back into it for a few
      // seconds: a path ending by the tracks had it flip every frame between "end" and "tracks ahead",
      // standing in a lane on the track with a queue of cars and our tram behind, line 17 s 13756)
      const here = pos(w.s), end = w.s + w.dir < 0 || w.s + w.dir > w.walk.path.length;
      w.commit = Math.max(0, (w.commit || 0) - dt);
      if (end) { w.dir = -w.dir; w.commit = 4; }
      else if (!w.commit && this.trackDist(ahead.x, ahead.y) < TRACK_CLEAR && !this.inLane(here.x, here.y)) w.dir = -w.dir;
      else w.s += w.dir * w.v * dt;
      const { x, y, p } = pos(w.s);
      w.x = x; w.y = y;
      const far = Math.hypot(x - cx, y - cy) > 260;
      w.alpha = Math.max(0, Math.min(1, w.alpha + (far ? -dt : dt) / FADE));
      if (far && w.alpha <= 0) { this.slots[i] = null; m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
      // fade by growing out of / sinking into the ground (instances share one material)
      const k = w.alpha;
      w.z = w.walk.hf ? w.walk.hf(x, y) : this.ground.surface(x, y);
      p3.set(x, w.z - (1 - k) * 1.8, -y);
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
    placeConsist(t.mesh, s, (q) => { const p = route.at(q); return [p.x, p.y, profileZ(q, p), route.rollAt(q)]; });
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
      // a car on the track ahead
      for (const c of g.carsOnTrack || []) if (c.s > t.s && c.s - 2.5 - 4 < (stopAt ?? Infinity)) stopAt = c.s - 2.5 - 4;
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
      // (not within braking distance of a red stop line: it appears already moving)
      const redAhead = this.game.signals.some((sig) => sig.backCross !== undefined && sig.backState !== 'go' && sig.backCross - 6 - n?.s > -2 && sig.backCross - 6 - n?.s < 80);
      if (other && n && n.d < 25 && !redAhead && !this.oncoming.some((t) => Math.abs(t.s - n.s) < 120)) {
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
      for (const c of this.carsOnBack || []) if (c.s > t.s && c.s - 2.5 - 4 < (stopAt ?? Infinity)) stopAt = c.s - 2.5 - 4;
      // keep a distance to the oncoming tram in front
      for (const o of this.oncoming) if (o !== t && o.s > t.s && o.s - o.length - 6 < (stopAt ?? Infinity)) stopAt = o.s - o.length - 6;
      // junction signals: the opposite direction has GO together with our straight phase; a tram
      // that can still stop comfortably waits at its stop line on red
      if (t.redStop && t.redStop.backState === 'go') t.redStop = null;
      for (const sig of this.game.signals) {
        if (sig.backCross === undefined || sig.backState === 'go') continue;
        const line = sig.backCross - 6, d = line - t.s;
        // (they brake at 0.9 m/s2 and react with a lag: about 2 s of travel more)
        if (d > 0 && d < 150 && d > (t.v * t.v) / 1.8 + t.v * 2 + 1 && line < (stopAt ?? Infinity)) t.redStop = sig;
        if (t.redStop === sig && line - 3 < (stopAt ?? Infinity) && d > -1) stopAt = line - 3; // a little before the line
      }
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
      this._placeTram(t, br, t.s, (s, q) => ground.trackAt(q.x, q.y));
    }
    this.oncoming = this.oncoming.filter((t) => {
      if (t.leaving && t.alpha <= 0) { this.group.remove(t.mesh); return false; }
      return true;
    });
  }
}
