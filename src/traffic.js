// Ambient life: cars on the road network (a lane graph: one smooth lane per road and direction,
// connector curves through the junctions), pedestrians on footways and sidewalks, and other trams
// (ahead of us on our track, and oncoming on the opposite track). Everything fades in and out
// instead of popping.
import * as THREE from 'three';
import { smoothPolyline } from './route.js';
import { makeCar, makeCrowd, makeT3, placeConsist, makeTrafficLights, makePedLights } from './models.js';
import { T3, COUPLING_GAP } from './tram.js';
import { t as tx } from './i18n.js'; // (t is the trams' loop variable here)

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
// How far an AI tram needs to stop before a signal that is no longer GO. When the GO starts blinking
// a driver stops if it is comfortable (0.9 m/s2 after ~2 s), else goes on (the dilemma zone: the
// controller holds the phase); facing a red a driver stops whenever full service braking allows it
// (1.3 m/s2 after ~1 s): one passing a blinking GO with the next signal 68 m on at red drove
// through it by the comfortable rule (line 17 s 10251).
function stopDistance(v, state) {
  return state === 'warn' ? (v * v) / 1.8 + v * 2 + 1 : (v * v) / 2.6 + v + 0.5;
}

// The speed (m/s) an AI tram may run at s: the limit under the whole set, and every lower limit ahead
// reached on a braking curve (0.7 m/s2, as our tram's nextLimitChange). With only the limit where it
// stood it ran into a slow section at full speed, braked inside it and crawled on a held blinking GO
// until it turned red (line 17 s 10826).
function limitSpeed(lim, s, len) {
  let v = Math.min(lim.at(s), lim.at(s - len)) / 3.6;
  for (let d = 5; d < 300; d += 5) v = Math.min(v, Math.sqrt((lim.at(s + d) / 3.6) ** 2 + 2 * 0.7 * Math.max(0, d - 5)));
  return v;
}

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

// which way a junction connector turns: 'left' / 'right' (more than ~30°), else null (cached)
function turnOf(conn) {
  if (conn._turn !== undefined) return conn._turn;
  const a = conn.path.at(0), b = conn.path.at(conn.path.length);
  const ang = Math.atan2(a.hx * b.hy - a.hy * b.hx, a.hx * b.hx + a.hy * b.hy);
  return (conn._turn = ang > 0.5 ? 'left' : ang < -0.5 ? 'right' : null);
}

// U3, cars across the tram's track: CAR_HALF = half a car's length (its position is its middle);
// TRACK_ZONE = how far into the crossing a car is on the tram's way (the 2.6 m band each side of the
// track centre, ~5.2 m across); a car's front stops YIELD_GAP m before it
const CAR_HALF = 2.2, TRACK_ZONE = 5.2, YIELD_GAP = 1.5;
// a car on the track holds up the tram when its heading is within 72° of the track's (cos 0.3): one
// still turning onto it counts (#100; at 60°, cos 0.5, it did not until it had straightened out)
const CAR_ALIGN = 0.3;

// lanes per direction: as OSM tags them (lanes:forward / lanes:backward, or lanes on a one-way road,
// or half of lanes from 4 on a two-way one), else one; turn lanes at junctions are not modelled
function lanesOf(src, dir) {
  if (src.o) return src.ln || 1;
  const own = dir > 0 ? src.lf : src.lb;
  if (own) return own;
  return src.ln >= 4 ? Math.floor(src.ln / 2) : 1;
}

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
        if (i < r.p.length - 1 && (uses.get(vkey(r.p[i])) || 0) > 1) { pieces.push({ ...r, p: cur, way: r.way || r.p }); cur = [r.p[i]]; }
      }
      pieces.push({ ...r, p: cur, way: r.way || r.p });
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
        // footways running along the tracks are platforms/verges: nobody strolls there; a footway lying
        // on the surveyed carriageway for more than 6 m is cut there (crossing a street is fine)
        const dtm = r.b ? null : this.ground.dtm, keepRuns = [];
        if (dtm) {
          const smp = [];
          for (let s = 0; s <= path.length; s += 2) { const q = path.at(s), c = dtm.classAt(q.x, q.y); smp.push({ q, on: c === 'road' || c === 'parking' || c === 'tram' }); }
          let cur = [];
          for (let i = 0; i < smp.length; i++) {
            let j = i;
            while (j < smp.length && smp[j].on) j++;
            if (j - i > 3) { if (cur.length > 1) keepRuns.push(cur); cur = []; i = j - 1; continue; }
            for (let k = i; k < Math.max(j, i + 1) && k < smp.length; k++) cur.push([smp[k].q.x, smp[k].q.y]);
            i = Math.max(j, i + 1) - 1;
          }
          if (cur.length > 1) keepRuns.push(cur);
        }
        for (const wp of dtm ? keepRuns.map((pts) => new Path(pts)) : [path]) {
          if (wp.length > 30 && nearTrackShare(wp) < 0.2) { this.walks.push({ path: wp, off: 0, hf: this.surfaceFn(r), deck: !!r.b }); addIndex('w', this.walks.length - 1, wp); }
        }
        continue;
      }
      // cars only on public vehicle roads: no driveways, service yards or courtyards
      if (!r.c || r.w < 5) continue;
      if (r.t) r.way = r.way || r.p; // (a tunnel: its whole chain of ways, chainTunnels)
      let near = 0, n = 0;
      for (let s = 0; s < path.length; s += 10) { const p = path.at(s); n++; if (route.distance(p.x, p.y) < 7) near++; }
      // the street the tram runs in: an ordinary part of the network (its cars drive alongside us),
      // its sidewalks get no extra walkers (the tram street's own footways cover them)
      const along = near / n > 0.4;
      const road = { src: r, path, w: r.w, o: r.o || 0, tram: r.tram, b: r.b || 0, t: r.t || 0, ln: r.ln, lf: r.lf, lb: r.lb, hf: this.surfaceFn(r), ends: [key(r.p[0]), key(r.p[r.p.length - 1])] };
      this._fitRoad(road);
      this._trackLats(road);
      this.jpos.set(road.ends[0], r.p[0]); this.jpos.set(road.ends[1], r.p[r.p.length - 1]);
      this.roads.push(road);
      if (path.length >= 15) addIndex('r', this.roads.length - 1, path); // spawn only on real streets
      if (along) continue;
      // sidewalks: 1.5 m beyond each kerb (the surveyed one where it exists, so walkers are not in
      // the lanes the cars drive)
      // (not along a bridge: only the carriageway is drawn there, its footways are OSM ways of their own;
      // not along a road tunnel: nobody walks under the hill beside the cars)
      if (r.w >= 6 && !r.b && !r.t) for (const side of [1, -1]) {
        // where the survey covers the street, on its sidewalk: the first sidewalk / paving within 8 m out
        // from the kerb, 1 m into it (else no path there: walkers used to stroll on parking strips and
        // carriageway where the kerb fit missed); elsewhere 1.5 m beyond the kerb
        const dtm = this.ground.dtm, runs = [];
        let cur = [];
        for (let s = 0; s <= path.length; s += 3) {
          const p = path.at(Math.min(s, path.length)), k = this.kerbs(road, s);
          const kerb = side > 0 ? k.hi : k.lo;
          let off = kerb + side * 1.5;
          if (dtm && dtm.covered(p.x, p.y)) {
            off = null;
            for (let d = 0.5; d <= 8; d += 0.5) {
              const o = kerb + side * d, c = dtm.classAt(p.x + p.hy * o, p.y - p.hx * o);
              if (c === 'sidewalk' || c === 'paved' || c === 'cycle') { off = o + side * 1.0; break; }
            }
          }
          if (off === null) { if (cur.length > 2) runs.push(cur); cur = []; continue; }
          cur.push([p.x + p.hy * off, p.y - p.hx * off]);
        }
        if (cur.length > 2) runs.push(cur);
        for (const pts of runs) {
          const walk = new Path(smoothPolyline(pts, 1, 4).pts);
          if (walk.length > 15 && nearTrackShare(walk) < 0.2) { this.walks.push({ path: walk, off: 0, hf: road.hf, deck: !!road.b }); addIndex('w', this.walks.length - 1, walk); }
        }
      }
    }
    this._buildLanes();
    this._linkWalks();
    this._findDoors(data.buildings || []);
    this._bindSignals();
    this._bindPedHeads();

    this.cars = [];
    this.walkers = [];
    this.crowd = makeCrowd(MAX_WALKERS);
    this.group.add(this.crowd);

    // where oncoming trams stop: the front at the far end of their own platform (game.platforms of the
    // back route: OSM shapes, GTFS positions). Mapped from our stop point they stopped 8 m into theirs:
    // our platform's far end is near the start of theirs (user: "they stop just before the stop instead
    // of running to its end"). Our stop mapped across stays the fallback where they have no platform.
    // (on their right: the T3's doors)
    // (overlapping platforms of one stop, OSM and GTFS, are one stretch: two stop points in one platform
    // stopped the tram twice, Kobylisy 951 and 1012)
    const backPl = (game.platforms || []).filter((p) => p.back && p.rt === this.back && p.side < 0).map((p) => [p.s0, p.s1]).sort((a, b) => a[0] - b[0]);
    const runs = [];
    for (const [a, b] of backPl) if (runs.length && a < runs[runs.length - 1][1] + 10) runs[runs.length - 1][1] = Math.max(runs[runs.length - 1][1], b); else runs.push([a, b]);
    const ends = runs.map(([, b]) => b - 1);
    this.backStops = this.back ? [...ends, ...game.stops.map((st) => {
      const o = route.offset(st.target, 3.2);
      const n = this.back.nearestOnHeading(o.x, o.y, -o.hx, -o.hy);
      return n && n.d < 30 && !runs.some(([a, b]) => n.s + 8 > a - 30 && n.s + 8 < b + 30) ? n.s + 8 : null;
    }).filter((s) => s !== null)].sort((a, b) => a - b) : [];
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
    if (!dtm || road.b) return; // (the survey's classes are those of the ground level)
    // (a road tunnel: the underground survey of its floor, where there is one)
    const classAt = road.t ? (x, y) => dtm.classUnder(x, y) : (x, y) => dtm.classAt(x, y);
    const L = road.path.length, n = Math.floor(L / 4) + 1;
    const lo = new Array(n).fill(null), hi = new Array(n).fill(null);
    let any = false;
    for (let i = 0; i < n; i++) {
      const p = road.path.at(Math.min(L, i * 4));
      if (!road.t && !dtm.covered(p.x, p.y)) continue;
      // (1 carriageway; 2 tram area, part of the street only between carriageway; 3 parking, part of it
      // but no lane: trimmed at the edges like a tram bed at the side)
      const on = [];
      for (let l = -16; l <= 16; l += 0.5) {
        const c = classAt(p.x + p.hy * l, p.y - p.hx * l);
        on.push(c === 'road' ? 1 : c === 'tram' ? 2 : c === 'parking' ? 3 : 0);
      }
      // the run around the centre (index 32), else the nearest within 8 m
      let k = 32;
      for (let d = 0; d <= 16 && !on[k]; d++) k = on[32 + d] ? 32 + d : on[32 - d] ? 32 - d : 32;
      if (!on[k]) continue;
      let a = k, b = k;
      // single 0.5 m holes (paint, a manhole cover area) don't end the carriageway
      while (a > 0 && (on[a - 1] || (a > 1 && on[a - 2]))) a--;
      while (b < on.length - 1 && (on[b + 1] || (b < on.length - 2 && on[b + 2]))) b++;
      while (a < b && on[a] !== 1) a++; // a track bed or parking at the side is not for cars
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
    // smoothed over ±20 m, and moving sideways at most 0.4 m per 4 m (a fitted kerb jumping at a bus
    // bay or a driveway made the lane kink on a straight road)
    const smooth = (arr) => arr.map((_, i) => { let s = 0, m = 0; for (let d = -5; d <= 5; d++) if (arr[i + d] !== undefined) { const w = 6 - Math.abs(d); s += arr[i + d] * w; m += w; } return s / m; });
    const limit = (arr) => {
      for (let i = 1; i < arr.length; i++) arr[i] = Math.max(arr[i - 1] - 0.4, Math.min(arr[i - 1] + 0.4, arr[i]));
      for (let i = arr.length - 2; i >= 0; i--) arr[i] = Math.max(arr[i + 1] - 0.4, Math.min(arr[i + 1] + 0.4, arr[i]));
      return arr;
    };
    road.fitLo = limit(smooth(fill(lo, -road.w / 2)));
    road.fitHi = limit(smooth(fill(hi, road.w / 2)));
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
  // Tram tracks running along a road (ours and the opposite one), every 4 m: their lateral offsets from
  // the road's centre line (+ = right). Where both lie in the carriageway, the line between them divides
  // the two directions; in a narrow street a car's lane then lies on the track of its own direction.
  _trackLats(road) {
    const L = road.path.length, n = Math.floor(L / 4) + 1, out = new Array(n);
    let any = false;
    for (let i = 0; i < n; i++) {
      const p = road.path.at(Math.min(L, i * 4)), lats = [];
      for (const rt of [this.route, this.back]) {
        if (!rt) continue;
        const q = rt.nearest(p.x, p.y);
        if (!q || q.d > road.w / 2 + 6) continue;
        const h = rt.at(q.s);
        if (Math.abs(h.hx * p.hx + h.hy * p.hy) < 0.85) continue; // crossing, not along
        lats.push((h.x - p.x) * p.hy - (h.y - p.y) * p.hx);
      }
      out[i] = lats;
      if (lats.length) any = true;
    }
    road.trk = any ? out : null;
  }
  tracksAt(r, s) {
    if (!r.trk) return [];
    return r.trk[Math.max(0, Math.min(r.trk.length - 1, Math.round(s / 4)))] || [];
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
  // Lane k (0 = the right one) of n: 1.7 m in from the right kerb, the others 3 m further each (less
  // where the band is narrower), never past the divider: the middle of a two-way road, or the line
  // between the two tracks where both lie in the carriageway (then in a narrow street the lane lies
  // on the track of its own direction: the Vyšehrad tunnel), or the left kerb of a one-way road.
  laneOffset(r, s, dir, k = 0) {
    let { lo, hi } = this.kerbs(r, s);
    let tk = this.tracksAt(r, s).filter((t) => t > lo - 0.5 && t < hi + 0.5);
    if (dir < 0) { [lo, hi] = [-hi, -lo]; tk = tk.map((t) => -t); } // the car's own right/left
    const n = lanesOf(r, dir);
    let div;
    if (r.o) div = lo;
    else if (tk.length >= 2) div = (Math.min(...tk) + Math.max(...tk)) / 2;
    else div = (lo + hi) / 2;
    const band = Math.max(0.1, hi - div), step = n > 1 ? Math.max(2.6, Math.min(3.25, (band - 1.7) / (n - 0.5))) : 0;
    // too narrow for a lane beside the track: on the track of its own direction (right of the divider)
    const own = tk.filter((t) => t > div);
    if (band < 3.2 && own.length) return Math.min(...own);
    const right = hi - Math.min(1.7, band / 2);
    return Math.max(right - k * step, div + Math.min(1.1, band / 2));
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
      for (const dir of dirs) for (let sel = 0; sel < lanesOf(r, dir); sel++) {
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

  // draw: false for a step whose result is not shown (inspect mode runs several steps per frame):
  // cars and walkers move but are not posed (their height and matrices wait for the drawn step)
  update(dt, camera, draw = true) {
    const tram = this.game.tram;
    const cx = camera.position.x, cy = -camera.position.z;
    this._carsOnTracks();
    this._updateRoadCars(dt, cx, cy, draw);
    this._updateWalkers(dt, cx, cy, draw);
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

  _poseCar(mesh, x, y, hx, hy, hf) {
    // a car standing still keeps its pose (the pose asks the ground height at several points)
    const last = mesh.userData.pose;
    if (last && last[0] === x && last[1] === y && last[2] === hx && last[3] === hy && last[4] === hf) return;
    mesh.userData.pose = [x, y, hx, hy, hf];
    const p = carPose(hf || ((u, v) => this.ground.surface(u, v)), x, y, hx, hy);
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
  _updateRoadCars(dt, cx, cy, draw = true) {
    const cars = this.cars.filter((c) => c.kind === 'road' && (c.active || c.alpha > 0));
    if (cars.filter((c) => c.active).length < 22 && this.rand() < dt * 4) {
      const near = this._ringIndex(cx, cy, 'r', 60, 360);
      if (near) {
        const [, k, s0] = near;
        const r = this.roads[k];
        const lane = r.lanes[Math.floor(this.rand() * r.lanes.length)];
        if (lane) {
          const s = Math.max(0, Math.min(lane.path.length, (lane.dir > 0 ? s0 : r.path.length - s0) - lane.trim));
          // (not within 50 m of a stop line that is not green: it came in at speed and ran the red)
          // (from the stop line, which can be up to 40 m before the lane's end: a car spawned 10 m before a
          // red line at 11.5 m/s, line 17 seed 5)
          // (nor within 50 m of one on a lane that follows: a short lane in a junction's mouth carries its
          // light at its start; a car spawned 16 m before such a red line at 11.2 m/s, line 9 s 15074, seed 3)
          const redAt = (l, d) => l.light && this.lightAspect(l.light) !== 'green' && d + l.path.length - l.light.back < 50;
          const redNear = redAt(lane, -s) || this.nextLanes(lane).some((b) => redAt(b, lane.path.length - s + (this.connector(lane, b)?.path.length || 0)));
          // (and at least 50 m from the camera itself: the ring's point picks an index cell, and a cell
          // can reach the camera; a car came in at 8 m/s 6 m before the track with the tram 4 m off,
          // line 17 s 19919)
          const sp = lane.path.at(s), close = Math.hypot(sp.x - cx, sp.y - cy) < 50;
          const c = redNear || close || cars.some((o) => o.active && o.path === lane.path && Math.abs(o.s - s) < 12) ? null : this._carSlot();
          if (c) Object.assign(c, { id: undefined, active: true, kind: 'road', lane, road: r, dir: lane.dir, conn: null, next: undefined, next2: undefined, next2From: null, lightGo: null, lightHold: null, lead: null, path: lane.path, s, v: 7 + this.rand() * 6, vNow: null, coast: null });
        }
      }
    }
    const tram = this.game.tram;
    const live = cars.filter((c) => c.active);
    const obstacles = this._pathObstacles();
    live.forEach((c) => {
      if (c.id === undefined) {
        c.id = this.nextCarId = (this.nextCarId || 0) + 1; // unique: the priority tie-breaks use it
        // one driver in eight crosses the tram's track with a small margin (from the id, not this.rand:
        // the seeded traffic runs stay comparable)
        c.bold = ((c.id * 2654435761) >>> 0) % 8 === 0;
      }
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
    const crossing = []; // cars on, or committed to, a crossing of our track (game.carsCrossing)
    for (const c of cars) {
      if (c.active) {
        const seq = this._seq(c);
        // Give way to the tram where the car's way crosses its track (U3: turning across in front of
        // it): the first crossing ahead within 45 m, on this path, through the junction or on the next
        // lane. The car waits with its front YIELD_GAP before the track while the tram's body stands on
        // the crossing, or while the tram is moving and would reach it before the car is across with a
        // margin (2.5 s; a bold driver, one in eight: 0.5 s). A tram standing clear of it (at a stop
        // before the junction) does not hold the cars: they go with their green (user, 2026-10-23).
        // A car too close to stop is committed and crosses: the tram's driver sees it
        // (game.carsCrossing: the bell, braking). Not where the car is on another level.
        // (every crossing within 45 m, nearest first, not only the first one: where the route loops
        // around, a car path crosses it twice; the car went by the first, the tram far off there, and
        // met the tram at the second already on the track, line 17 s 21530)
        let xGap = null, keepClear = false;
        const xs = [];
        seq.forEach(([path, off], k) => {
          for (const x of this._trackCrossings(path)) {
            const dC = off + x.sIn; // the car's middle to where the track's band begins
            if (dC > -CAR_HALF - TRACK_ZONE - CAR_HALF && dC < 45) xs.push({ dC, sx: x.sx, k });
          }
        });
        xs.sort((a, b) => a.dC - b.dC);
        // (one crossing seen twice, the next path starting inside the track's band, counts once: a car
        // turning into a lane along the track stood with its nose on it, giving way at the second copy
        // past the first's edge, and the tram hit it; line 17 s 9903, seed 1)
        for (let i = xs.length - 1; i > 0; i--) if (xs.slice(0, i).some((o) => Math.abs(o.sx - xs[i].sx) < 4)) xs.splice(i, 1);
        // a car turning onto the track (its way still on it 12 m past the band's edge: a lane along
        // the rails) does not clear it in a few seconds: it goes only when the tram could stop behind
        // it (s 9903: a bold driver turned in 36 m ahead of the tram at 45 km/h, crawled on along the
        // track and was hit)
        const wayAt = (d) => { for (let i = seq.length - 1; i >= 0; i--) if (d >= seq[i][1]) return seq[i][0].at(d - seq[i][1]); return null; };
        for (const x of xs) { const q = wayAt(x.dC + 12), n = q && this.route.nearest(q.x, q.y); x.along = !!n && n.d < 2.6; }
        // the car ahead: on this path, else across the junction on the connector and the next lane
        let gap = null, vLead = 0, lead = null;
        for (const o of live) {
          if (o === c) continue;
          for (const [path, off] of seq) {
            if (o.path !== path) continue;
            const d = off + o.s - 4.4;
            if (d > -2 && (path !== c.path || o.s > c.s) && (gap === null || d < gap)) { gap = d; vLead = o.vNow ?? 0; lead = o; }
          }
        }
        // a cycle of cars waiting for each other through this "car ahead on my way" as well as through
        // what they see (three cars at a junction: one on the connector ahead of the next, who waited
        // for the third, who overlapped the first; line 17 s 21178, the tram stuck behind): the lowest id
        // of the cycle goes (the leaders of the last step close the loop)
        const nextOf = (x) => x.seen?.car || x.lead;
        if (lead) {
          const ring = [c];
          for (let x = lead; x && ring.length < 6; x = nextOf(x)) {
            if (x === c) { if (ring.every((y) => y.id >= c.id)) { gap = null; lead = null; } break; }
            if (ring.includes(x)) break;
            ring.push(x);
          }
        }
        c.lead = lead;
        // trams and walkers on the path ahead (shared lanes on the tracks, a tram stopped at a
        // stop, someone crossing): stop or follow behind
        const ob = c.seen;
        if (ob && (gap === null || ob.gap < gap)) { gap = ob.gap; vLead = ob.v; }
        c.xing = xs[0] || null;
        for (const x of xs) {
          if (c.z !== undefined && Math.abs(c.z - this.ground.profile.height(x.sx)) > LEVEL_APART) continue;
          const { dC, sx } = x, v = c.vNow ?? 0, front = dC - CAR_HALF;
          const onBody = sx > tram.s - tram.length - 2 && sx < tram.s + 2;
          const tA = (sx - tram.s - 2) / Math.max(tram.v, 0.1), tC = (Math.max(0, front) + TRACK_ZONE + 2 * CAR_HALF) / Math.max(v, 2.5);
          const coming = tram.v > 0.5 && sx >= tram.s && (sx - tram.s < 16 || tA < tC + (c.bold ? 0.5 : 2.5) || (x.along && sx - tram.s < (tram.v * tram.v) / 2 + tram.v * 2 + 20));
          // (braking up to 5 m/s2; a car standing or crawling stays where it is: one held by the queue
          // 0.9 m from the band, inside YIELD_GAP, counted as committed and pulled out in front of the
          // tram when the queue moved on, line 17 s 9903)
          const canStop = v < 1 || front - YIELD_GAP > (v * v) / 10 - 0.5;
          if ((onBody || coming) && canStop && front > 0) {
            xGap = front - YIELD_GAP + 8; // (following() stops 8 m short)
            // a crossing past a junction: wait before the junction, not in it, unless the car stands
            // wholly on the lane beyond. One waiting in the junction's mouth blocked a car leaving the
            // track the other way; the tram stopped for that one with its body on this car's crossing
            // (line 37 s 1475, seed 2). Where the tracks run through the junction, cars wait in it.
            const J = seq[x.k - 1];
            if (J && J[2] && J[1] > 0 && dC - YIELD_GAP - 2 * CAR_HALF < seq[x.k][1]) {
              const toJ = J[1] - CAR_HALF - 1; // its front 1 m before the junction
              if (v < 1 || toJ > (v * v) / 10 - 0.5) xGap = toJ + 8;
            }
            c.xing = x; break;
          }
          // nor onto the track without room to leave it: the car ahead standing or crawling closer than
          // the way across (the band and a car's length). A car stood on the track behind a queue that
          // waited, round the junction, for a car giving way to our tram, which waited for the first
          // (line 9 s 11221, seed 2)
          if (gap !== null && vLead < 1 && gap < Math.max(0, front) + TRACK_ZONE + 2 * CAR_HALF && canStop && front > 0) { xGap = front - YIELD_GAP + 8; c.xing = x; keepClear = true; break; }
          // crossing: on the track, or moving onto it (a car standing before it, held by a queue, is not:
          // the tram waited for two such cars for good, line 17 s 11629)
          if ((front <= 0 && front > -TRACK_ZONE - 2 * CAR_HALF) || (front > 0 && front < 8 && v > 1)) crossing.push({ s: sx, onTrack: front <= 0, car: c });
        }
        c.yielding = xGap !== null && !keepClear; // (to the tram: what u3 counts)
        c.keepClear = keepClear;
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
        // D2: the light at the end of its lane: stop at the stop line (its front 1 m before it; L.back m before the lane end)
        // on red and red-amber, and on amber when it can (3 m/s2 after 1 s); a car that could not stop
        // on amber goes through and keeps to that (c.lightGo); past the line it goes on
        // (a lit lane shorter than a car, a piece in the junction's mouth: its light stands at the end of
        // the lane before it: cars crossed such lanes in one step, on red; a car that stopped for the
        // light keeps to it until green, also when it overran the line by a little: c.lightHold)
        let lGap = null;
        let L = !c.conn && c.lane.light, lane = c.lane, toLine = L ? c.toEnd - L.back : 0;
        // (the next lane's light when its stop line is near its start: OSM nodes and junction edges put it
        // 2-6 m into short lanes; looking only at lanes under 12 m, cars came onto such a lane at the line
        // at 4-11 m/s and crossed it on red, line 17 s 11785, 14839, 16161, 17244; a short lane's line is
        // at its start, back = its length)
        if (!L && !c.conn && c.next?.light) { const d = c.toEnd + (c.plan ? c.plan.path.length : 0) + c.next.path.length - c.next.light.back; if (d < 60) { L = c.next.light; lane = c.next; toLine = d; } }
        // (and from a junction connector onto such a lane)
        if (!L && c.conn && c.conn.to.light) { const d = c.conn.path.length - c.s + c.conn.to.path.length - c.conn.to.light.back; if (d < 60) { L = c.conn.to.light; lane = c.conn.to; toLine = d; } }
        if (L) {
          const a = this.lightAspect(L), v = c.vNow ?? 0, front = toLine - CAR_HALF - 1;
          if (a === 'green') { c.lightGo = null; c.lightHold = null; }
          else if (a === 'amber' && c.lightGo !== lane && c.lightHold !== lane && front < (v * v) / 6 + v) c.lightGo = lane;
          if (a !== 'green' && c.lightGo !== lane && (front > -0.5 || c.lightHold === lane)) { lGap = Math.max(0, front) + 8; c.lightHold = lane; } // (following() halts 8 m short)
        }
        const vt = Math.min(c.v, vCurve, following(gap, vLead), jStop === null ? Infinity : following(jStop, 0), following(xGap, 0), following(lGap, 0));
        c.vNow = this._approach(c.vNow ?? vt, vt, dt);
        c.s += c.vNow * dt;
        while (c.active && c.s > c.path.length) this._advance(c);
      }
      this._fade(c, dt);
      if (c.alpha <= 0) continue;
      if (!c.active && c.coast) {
        const k = c.coast;
        k.d += (c.vNow || 6) * dt;
        if (draw) this._poseCar(c.mesh, k.x + k.hx * k.d, k.y + k.hy * k.d, k.hx, k.hy, c.lane.road.hf);
        continue;
      }
      const p = c.path.at(c.s);
      if (Math.hypot(p.x - cx, p.y - cy) > 420) c.active = false;
      if (!draw) continue; // (c.z stays from the last drawn step: it only tells levels metres apart)
      this._poseCar(c.mesh, p.x, p.y, p.hx, p.hy, c.conn ? c.conn.hf : c.lane.road.hf);
      c.z = c.mesh.position.y;
      // the indicator: from 35 m before a junction where the car turns, and through it
      const J = c.conn || (c.plan && c.toEnd < 35 ? c.plan : null);
      c.mesh.userData.blink?.(J ? turnOf(J) : null, Math.floor(this.game.clock * 2.6) % 2 === 0);
    }
    if (draw) for (const lane of this.lightLanes) this.lights.set(lane.light.head, this.lightAspect(lane.light));
    if (draw) this.pedCross.forEach((x) => { const a = this._pedAspect(x); for (const i of x.heads) this.pedLights.set(i, a); });
    // the tram's driver sees these (autopilot: the bell, stopping short of one on the track); a car on
    // the crossing where the tram's front is: a collision (once per car)
    this.game.carsCrossing = crossing;
    for (const x of crossing) {
      if (!x.onTrack || x.car.hitTram || x.s < tram.s - 1 || x.s > tram.s + 0.5 || tram.v < 0.3) continue;
      x.car.hitTram = true;
      this.game._collision(tx('obj.crossingCar'));
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
      const n = this.route.nearestOnHeading(p.x, p.y, p.hx, p.hy, CAR_ALIGN);
      // (a car on the road under our bridge, or on a bridge over the track, is not on it)
      if (n && c.z !== undefined && Math.abs(c.z - this.ground.profile.height(n.s)) > LEVEL_APART) continue;
      if (n && n.d < 1.6) ours.push({ s: n.s, v: c.vNow ?? 0 });
      if (this.back) {
        const b = this.back.nearestOnHeading(p.x, p.y, p.hx, p.hy, CAR_ALIGN);
        if (b && b.d < 1.6) back.push({ s: b.s, v: c.vNow ?? 0 });
      }
    }
    this.game.carsOnTrack = ours;
    this.carsOnBack = back;
  }

  // Where a car path crosses our track (cached per path): [{ sIn, sx }], sIn along the path where it
  // comes within 2.6 m of the track centre (the tram's swept edge and a margin), sx the route position
  // there. Only where the path crosses (|cos| < 0.7: not driving along the track, a car there follows
  // the tram instead) and not where our track passes over it on a bridge.
  _trackCrossings(path) {
    if (path._xings) return path._xings;
    const out = [];
    let inside = false;
    for (let s = 0; s <= path.length; s += 1) {
      const p = path.at(s), n = this.route.nearest(p.x, p.y), near = !!n && n.d < 2.6;
      if (near && !inside) {
        const h = this.route.at(n.s);
        if (Math.abs(p.hx * h.hx + p.hy * h.hy) < 0.7 && !this.ground.profile.overBridge(n.s)) out.push({ sIn: s, sx: n.s });
      }
      inside = near;
    }
    return (path._xings = out);
  }

  // The paths a car drives next, each with the distance from the car to its start. Past a short next
  // lane (under 45 m) it also chooses the one after it (c.next2, kept when it gets there): a track
  // crossing two lanes ahead, beyond a 4 m piece in a junction's mouth, was seen only 5 m before the
  // track, too late to give way to the tram (line 17 s 16855).
  _seq(c) {
    const seq = [[c.path, -c.s, !!c.conn]]; // [path, offset, a junction's connector]
    let lane = null, off = 0;
    if (c.conn) { lane = c.conn.to; off = c.conn.path.length - c.s; seq.push([lane.path, off]); }
    else if (c.next) {
      off = c.path.length - c.s;
      if (c.plan) { seq.push([c.plan.path, off, true]); off += c.plan.path.length; }
      lane = c.next;
      seq.push([lane.path, off]);
    }
    if (lane && lane.path.length < 45) {
      if (c.next2 === undefined || c.next2From !== lane) { c.next2 = this._chooseNext(lane); c.next2From = lane; }
      if (c.next2) {
        const cn = this.connector(lane, c.next2);
        off += lane.path.length;
        if (cn) { seq.push([cn.path, off, true]); off += cn.path.length; }
        seq.push([c.next2.path, off]);
      }
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
    // (onto the next lane: the one after it, if already chosen in _seq, stays the plan)
    const keep = (lane) => (c.next2From === lane ? c.next2 : undefined);
    if (c.conn) {
      c.lane = c.conn.to; c.conn = null; c.next = keep(c.lane);
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
      else { c.lane = c.next; c.next = keep(c.lane); }
    }
    c.path = c.conn ? c.conn.path : c.lane.path;
    c.road = c.lane.road; c.dir = c.lane.dir;
    c.s = over;
  }

  // The footway network. The walks are pieces (OSM footways, the sidewalks of each street side, cut
  // where the survey has no sidewalk; line 17: 3 262, median 64 m) and a walker used to pace one piece
  // to and fro. Their ends lie close to other pieces (line 17: 69 % within 3 m, 92 % within 15 m), so
  // every end links to the other walks passing within 3 m of it, else to the nearest one within 15 m
  // (across a side street), by a short straight link walk, never across the tram's tracks.
  // walk.links = [at its start, at its end], each a list of { walk, s }; a link walk (walk.link) is a
  // walk of its own, linked at both ends. (Links leave from ends only: one passing the middle of a
  // walk is taken by walkers coming along that link, not by those walking past.)
  _linkWalks() {
    const C = 5, grid = new Map();
    const base = this.walks.slice();
    for (const w of base) {
      w.links = [[], []];
      for (let s = 0; s <= w.path.length; s += 1) {
        const p = w.path.at(s), kk = Math.floor(p.x / C) * 100003 + Math.floor(p.y / C);
        if (!grid.has(kk)) grid.set(kk, []);
        grid.get(kk).push([w, s, p.x, p.y]);
      }
    }
    // the nearest point of every other walk within R of (x, y), nearest first
    const around = (self, x, y, R) => {
      const best = new Map(), n = Math.ceil(R / C), ci = Math.floor(x / C), cj = Math.floor(y / C);
      for (let i = ci - n; i <= ci + n; i++) for (let j = cj - n; j <= cj + n; j++) {
        for (const [w, s, px, py] of grid.get(i * 100003 + j) || []) {
          if (w === self) continue;
          const d = Math.hypot(px - x, py - y);
          if (d <= R && (!best.has(w) || d < best.get(w).d)) best.set(w, { walk: w, s, d, x: px, y: py });
        }
      }
      return [...best.values()].sort((a, b) => a.d - b.d);
    };
    const clear = (x0, y0, x1, y1) => {
      const L = Math.hypot(x1 - x0, y1 - y0);
      for (let t = 0; t <= L; t += 1) if (this.trackDist(x0 + (x1 - x0) * (t / (L || 1)), y0 + (y1 - y0) * (t / (L || 1))) < TRACK_CLEAR) return false;
      return true;
    };
    let joined = 0, crossings = 0;
    for (const w of base) for (const e of [0, 1]) {
      const s0 = e ? w.path.length : 0, p = w.path.at(s0);
      let cands = around(w, p.x, p.y, 3).slice(0, 4);
      if (!cands.length) cands = around(w, p.x, p.y, 15).slice(0, 1);
      for (const c of cands) {
        if (c.d < 0.5) { w.links[e].push({ walk: c.walk, s: c.s }); joined++; continue; }
        if (!clear(p.x, p.y, c.x, c.y)) continue;
        const lw = { path: new Path([[p.x, p.y], [c.x, c.y]]), off: 0, hf: null, link: true, links: [[{ walk: w, s: s0 }], [{ walk: c.walk, s: c.s }]] };
        this.walks.push(lw);
        w.links[e].push({ walk: lw, s: 0 });
        if (c.d > 3) crossings++; else joined++;
      }
    }
    const open = base.reduce((a, w) => a + (w.links[0].length ? 0 : 1) + (w.links[1].length ? 0 : 1), 0);
    console.log(`footways: ${base.length} walks, ${joined} joins, ${crossings} street crossings, ${open} of ${base.length * 2} ends open`);
  }

  // Doors: where a building meets the footway network, the nearest walk point within 8 m of its
  // footprint (OSM footprints), for walkers to come out of and go into; later also metro exits and
  // stations from the detailed data (more entries of the same kind). this.doors: { walk, s, x, y, ix,
  // iy } (ix, iy: 1.5 m inside the building), by 50 m cell in this.doorIdx; walk.doors: those on it, by s.
  _findDoors(buildings) {
    const C = 5, grid = new Map();
    for (const w of this.walks) {
      if (w.link) continue;
      w.doors = [];
      for (let s = 0; s <= w.path.length; s += 2) {
        const p = w.path.at(s), kk = Math.floor(p.x / C) * 100003 + Math.floor(p.y / C);
        if (!grid.has(kk)) grid.set(kk, []);
        grid.get(kk).push([w, s, p.x, p.y]);
      }
    }
    this.doors = [];
    this.doorIdx = new Map();
    for (const b of buildings) {
      const ring = b.p;
      if (!ring || ring.length < 3) continue;
      let cx = 0, cy = 0;
      for (const q of ring) { cx += q[0]; cy += q[1]; }
      cx /= ring.length; cy /= ring.length;
      let best = null;
      for (let i = 0; i < ring.length; i++) {
        const a = ring[i], c = ring[(i + 1) % ring.length], L = Math.hypot(c[0] - a[0], c[1] - a[1]);
        for (let t = 0; t <= L; t += 3) {
          const fx = a[0] + (c[0] - a[0]) * (t / (L || 1)), fy = a[1] + (c[1] - a[1]) * (t / (L || 1));
          const ci = Math.floor(fx / C), cj = Math.floor(fy / C);
          for (let u = ci - 2; u <= ci + 2; u++) for (let v = cj - 2; v <= cj + 2; v++) {
            for (const [w, s, px, py] of grid.get(u * 100003 + v) || []) {
              const d = Math.hypot(px - fx, py - fy);
              if (d <= 8 && (!best || d < best.d)) best = { walk: w, s, x: px, y: py, d, fx, fy };
            }
          }
        }
      }
      if (!best) continue;
      const toC = Math.hypot(cx - best.fx, cy - best.fy) || 1;
      const door = { walk: best.walk, s: best.s, x: best.x, y: best.y, ix: best.fx + ((cx - best.fx) / toC) * 1.5, iy: best.fy + ((cy - best.fy) / toC) * 1.5 };
      this.doors.push(door);
      best.walk.doors.push(door);
      const kk = `${Math.floor(door.x / 50)},${Math.floor(door.y / 50)}`;
      if (!this.doorIdx.has(kk)) this.doorIdx.set(kk, []);
      this.doorIdx.get(kk).push(door);
    }
    for (const w of this.walks) w.doors?.sort((a, b) => a.s - b.s);
    console.log(`doors: ${this.doors.length} of ${buildings.length} buildings on the footway network`);
  }

  // D2, traffic lights. The junction controllers are the street signals' (game._runController); every
  // lane-graph junction within 25 m of such a signal's crossing point is that signal's, and each lane
  // ending there is an approach: 'along' the tram street (green with the trams going straight, the
  // opposite direction's GO; amber while it blinks) or 'cross' (green in the cross phase, 3 s amber,
  // 3 s all red). lane.light = { sig, kind, head }; a car signal head at each approach's stop line,
  // 2.2 m right of the lane. (On-demand and single-track signals have no car approaches.)
  _bindSignals() {
    const heads = [], osmStops = this.game.data.osmSignals?.stop || [];
    this.lightLanes = [];
    this.lightSigs = [];
    for (const sig of this.game.signals) {
      if (!sig.xroad || sig.gauntlet || sig.demand) continue;
      const P = this.route.at(sig.cross), h = this.route.heading(sig.cross, 6);
      let n = 0;
      for (const [key, pos] of this.jpos) {
        // (up to 50 m off where OSM has a stop line on the approach: the bridge end at Palackého
        // náměstí is 35 m from the crossing point)
        const far = Math.hypot(pos[0] - P.x, pos[1] - P.y);
        if (far > 50) continue;
        for (const lane of this.lanesTo.get(key) || []) {
          if (lane.light) continue;
          if (far > 25 && this._stopLine(lane, 'cross', P, osmStops).src !== 'osm') continue;
          // (a piece inside the junction, starting within it too, is no approach: its cars are in it;
          // OSM splits a junction into several nodes)
          const st = lane.path.at(0);
          if (Math.hypot(st.x - P.x, st.y - P.y) < 25) continue;
          const end = lane.path.at(lane.path.length);
          const kind = Math.abs(end.hx * h.hx + end.hy * h.hy) > 0.7 ? 'along' : 'cross';
          const { back, src } = this._stopLine(lane, kind, P, osmStops);
          // (the head 4 m past the stop line, never past the lane's end: the surveyed signal poles of the
          // technical map stand a median 4.2 m past the OSM stop line, 10-90 % −0.7 to +7.1 m, line 17,
          // .claude/bench/heads.js; on the line they were 5.5 m off)
          const e = lane.path.at(Math.min(lane.path.length, lane.path.length - back + 4));
          const x = e.x + e.hy * 2.2, y = e.y - e.hx * 2.2, face = Math.atan2(-e.hx, e.hy);
          // lanes side by side share a head (within 4 m, facing the same way)
          let head = heads.findIndex((o) => Math.hypot(o.x - x, o.z + y) < 4 && Math.cos(o.face - face) > 0.9);
          if (head < 0) { head = heads.length; heads.push({ x, z: -y, h: this.ground.surface(x, y), face }); }
          lane.light = { sig, kind, head, back, src };
          this.lightLanes.push(lane);
          n++;
        }
      }
      if (n) this.lightSigs.push({ sig, x: P.x, y: P.y, hx: h.hx, hy: h.hy });
    }
    this.lights = makeTrafficLights(heads);
    this.group.add(this.lights.group);
    const osm = this.lightLanes.filter((l) => l.light.src === 'osm').length;
    console.log(`traffic lights: ${heads.length} car heads at ${this.lightSigs.length} junctions (stop lines: ${osm} from OSM, ${this.lightLanes.length - osm} at the junction edge)`);
  }

  // Where an approach's stop line is, as `back` m before its lane's end (the lanes run on to 5 m short
  // of the OSM junction node, the middle of the junction: the heads stood in it, one on the tracks at
  // Palackého náměstí). An OSM traffic_signals node on the approach in its last 40 m (mappers put them
  // at the stop line, with the direction they serve): there (src 'osm'). Else the edge of the junction:
  // back from the end until the line is clear of the streets crossing it (half their width + 1.5 m) and,
  // crossing the tram street, 4.5 m clear of the tracks (src 'edge').
  // ...and never on a zebra: a crossing (OSM footway with zebra paint, 3 m wide) under the waiting car's
  // front or ahead of it, up to 4 m into the junction, pushes it back to 2 m before the crossing's middle (13 of 56
  // approaches with a zebra had the cars' front bumper on it; OSM stop nodes too, mapped on the
  // crossing node)
  _stopLine(lane, kind, P, osmStops) {
    const r = this._stopLineAt(lane, kind, P, osmStops), path = lane.path, L = path.length;
    if (r.src === 'short') return r;
    this.zebras ||= this.game.data.roads.filter((z) => z.z).map((z) => z.p);
    const e = path.at(L), pts = path.p.concat([[e.x + e.hx * 4, e.y + e.hy * 4]]);
    let stop = L - r.back, acc = 0;
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i], sl = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (acc + sl > stop - 6) {
        for (const z of this.zebras) for (let j = 1; j < z.length; j++) {
          const c = z[j - 1], d = z[j], rx = b[0] - a[0], ry = b[1] - a[1], sx = d[0] - c[0], sy = d[1] - c[1], den = rx * sy - ry * sx;
          if (Math.abs(den) < 1e-9) continue;
          const t = ((c[0] - a[0]) * sy - (c[1] - a[1]) * sx) / den, u = ((c[0] - a[0]) * ry - (c[1] - a[1]) * rx) / den;
          if (t >= 0 && t <= 1 && u >= 0 && u <= 1 && acc + t * sl > stop - 2.5) stop = Math.min(stop, acc + t * sl - 2);
        }
      }
      acc += sl;
    }
    return { ...r, back: Math.min(L - 1, Math.max(r.back, L - stop)) };
  }

  _stopLineAt(lane, kind, P, osmStops) {
    const path = lane.path, L = path.length, maxBack = Math.max(0, Math.min(40, L - 3));
    if (L < 12) return { back: L, src: 'short' }; // (cars stop at its start: see the car loop)
    let best = null;
    const J = this.jpos.get(lane.to);
    for (const o of osmStops) {
      // (a node on the junction node itself is the older one-per-junction tagging: no stop line)
      if (Math.hypot(o.x - P.x, o.y - P.y) > 70 || (J && Math.hypot(o.x - J[0], o.y - J[1]) < 6)) continue;
      for (let b = 0; b <= maxBack; b += 0.5) {
        const q = path.at(L - b), d = Math.hypot(o.x - q.x, o.y - q.y);
        if (d < 4.5 && (o.both || o.hx * q.hx + o.hy * q.hy > 0.7) && (!best || d < best.d)) best = { d, back: b };
      }
    }
    if (best) return { back: best.back, src: 'osm' };
    const end = path.at(L), cross = [];
    for (const r of this.roads) {
      if (r === lane.road || r.t || r.b) continue;
      const pts = r.path.p;
      let near = false;
      for (const p of pts) if (Math.hypot(p[0] - P.x, p[1] - P.y) < 35) { near = true; break; }
      if (!near) continue;
      cross.push(r);
    }
    const distTo = (r, x, y) => {
      const pts = r.path.p;
      let m = Infinity, cos = 1;
      for (let i = 1; i < pts.length; i++) {
        const a = pts[i - 1], b = pts[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)), d = Math.hypot(a[0] + dx * t - x, a[1] + dy * t - y);
        if (d < m) { m = d; cos = Math.abs((dx * end.hx + dy * end.hy) / Math.sqrt(l2)); }
      }
      return cos < 0.7 ? m : Infinity; // (only a street crossing ours: not its own continuation)
    };
    for (let b = 0; b <= maxBack; b += 0.5) {
      const q = path.at(L - b);
      // (not where the lane runs along the rails, a shared lane before it turns across: the line walked
      // back 38 m there, nearly to the lane's start, line 17 s 14839)
      const n = this.route.nearest(q.x, q.y), h = n && this.route.at(n.s), alongRails = h && Math.abs(q.hx * h.hx + q.hy * h.hy) > 0.8;
      if (kind === 'cross' && !alongRails && this.trackDist(q.x, q.y) < 4.5) continue;
      if (cross.some((r) => distTo(r, q.x, q.y) < r.w / 2 + 1.5)) continue;
      return { back: b, src: 'edge' };
    }
    return { back: maxBack, src: 'edge' };
  }

  // the light an approach shows: 'green' | 'amber' | 'red' | 'redamber' (the last 2 s before green)
  lightAspect(L) {
    const sig = L.sig, Y = sig.cycle, t = sig.t;
    if (L.kind === 'along') return sig.backState === 'go' ? 'green' : sig.backState === 'warn' ? 'amber' : Y.C - t < 2 ? 'redamber' : 'red';
    if (t >= Y.cross && t < Y.C - 6) return 'green';
    if (t >= Y.C - 6 && t < Y.C - 3) return 'amber';
    return t >= Y.cross - 2 && t < Y.cross ? 'redamber' : 'red';
  }

  // Pedestrian signal heads at the OSM signalled crossings (data.osmSignals.peds) belonging to one of our
  // tram signals (its crossing point or stop point within 45 m): one head on each kerb of the street the
  // node lies on, facing the people waiting across. The crossing runs across that street's nearest car
  // road (its half width + 0.6 m out from the node). Phases as _pedRed: walking across the tram street
  // (or a road along it, the zebras from Palackého náměstí's island) with the cross phase, across a side
  // street with the trams going straight. this.pedCross: [{ x, y, cx, cy, sig, along, heads }].
  _bindPedHeads() {
    const heads = [], nodes = this.game.data.osmSignals?.peds || [];
    this.pedCross = [];
    const sigs = this.game.signals.filter((s) => !s.gauntlet && s.cycle);
    for (const o of nodes) {
      if (this.pedCross.some((c) => Math.hypot(c.x - o.x, c.y - o.y) < 3)) continue;
      let sig = null, best = 45;
      for (const s of sigs) for (const sp of [s.cross, s.s]) { const q = this.route.at(sp), d = Math.hypot(q.x - o.x, q.y - o.y); if (d < best) { best = d; sig = s; } }
      if (!sig) continue;
      // the street it crosses: the nearest car road within 6 m
      let road = null, rd = 6, rh = null;
      for (const r of this.roads) {
        const P = r.path.p;
        for (let i = 1; i < P.length; i++) {
          const a = P[i - 1], b = P[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
          const t = Math.max(0, Math.min(1, ((o.x - a[0]) * dx + (o.y - a[1]) * dy) / l2)), d = Math.hypot(a[0] + dx * t - o.x, a[1] + dy * t - o.y);
          if (d < rd) { rd = d; road = r; const l = Math.sqrt(l2); rh = [dx / l, dy / l]; }
        }
      }
      if (!road) continue;
      const cx = -rh[1], cy = rh[0], half = road.w / 2 + 0.6; // walking direction: across the road
      const h = this.route.heading(sig.cross, 6), along = Math.abs(cx * h.hx + cy * h.hy) > 0.6;
      const ids = [];
      for (const side of [1, -1]) {
        const x = o.x + cx * half * side, y = o.y + cy * half * side;
        if (this.trackDist(x, y) < 1.8) continue; // (not on the rails)
        const fx = -cx * side, fy = -cy * side; // faces the opposite kerb
        ids.push(heads.length);
        heads.push({ x, z: -y, h: this.ground.surface(x, y), face: Math.atan2(fx, -fy) });
      }
      if (ids.length) this.pedCross.push({ x: o.x, y: o.y, cx, cy, sig, along, heads: ids });
    }
    this.pedLights = makePedLights(heads);
    this.group.add(this.pedLights.group);
    console.log(`pedestrian signals: ${heads.length} heads at ${this.pedCross.length} crossings`);
  }

  // a crossing's pedestrian aspect (green while its walkers may go)
  _pedAspect(x) {
    const sig = x.sig, Y = sig.cycle, t = sig.t;
    return (x.along ? sig.backState === 'go' : t >= Y.cross && t < Y.C - 6) ? 'green' : 'red';
  }

  // a walker at the kerb by a controlled junction, about to cross heading (hx, hy): red for it? Across
  // the tram street it walks with the cross phase, across the side street with the trams going straight.
  // (At a crossing with pedestrian heads, those decide: within 6 m of its node, walking along it.)
  _pedRed(x, y, hx, hy) {
    for (const c of this.pedCross || []) {
      if (Math.hypot(x - c.x, y - c.y) < 6 && Math.abs(hx * c.cx + hy * c.cy) > 0.7) return this._pedAspect(c) === 'red';
    }
    for (const L of this.lightSigs) {
      if (Math.hypot(x - L.x, y - L.y) > 30) continue;
      const sig = L.sig, Y = sig.cycle, t = sig.t;
      if (Math.abs(hx * L.hx + hy * L.hy) < 0.5) return !(t >= Y.cross && t < Y.C - 6); // across the tram street
      return sig.backState !== 'go'; // along it: across the side street
    }
    return false;
  }

  // a moving car that would reach (x, y) within 4 s (a walker at the kerb waits for it)
  _carComing(x, y) {
    for (const c of this.cars) {
      if (!c.active || (c.vNow ?? 0) < 1) continue;
      const p = c.path.at(c.s), dx = x - p.x, dy = y - p.y, d = Math.hypot(dx, dy);
      if (d > 40 || d < 0.5) continue;
      // coming towards the spot (within ~25° of its heading) and close in time
      if ((dx * p.hx + dy * p.hy) / d > 0.9 && d / c.vNow < 4) return true;
    }
    return false;
  }

  // a random door at a distance between rMin and rMax from (cx, cy), or null
  _ringDoor(cx, cy, rMin, rMax) {
    for (let tries = 0; tries < 8; tries++) {
      const a = this.rand() * Math.PI * 2, d = rMin + this.rand() * (rMax - rMin);
      const arr = this.doorIdx.get(`${Math.floor((cx + Math.cos(a) * d) / 50)},${Math.floor((cy + Math.sin(a) * d) / 50)}`);
      if (arr?.length) return arr[Math.floor(this.rand() * arr.length)];
    }
    return null;
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

  // Pedestrians: each keeps its own instance slot (stable colour). Most come out of a building's door
  // (it hides them until they are out) and, after a walk of 80-480 m on the footway network, go into
  // one they pass; the rest appear on a footway far enough away to fade in unseen (parks, squares).
  // At the end of a walk they go on along one of its links (not straight back where they came from if
  // there is another way), turning back only at a dead end; they turn back before the tracks.
  _updateWalkers(dt, cx, cy, draw = true) {
    if (!this.slots) this.slots = new Array(MAX_WALKERS).fill(null);
    const free = this.slots.indexOf(null);
    if (free >= 0 && this.rand() < dt * 8) {
      const v = 1.1 + this.rand() * 0.5, side = (this.rand() - 0.5) * 1.2, goal = 80 + this.rand() * 400;
      const door = this.rand() < 0.75 ? this._ringDoor(cx, cy, 30, 220) : null;
      if (door) this.slots[free] = { walk: door.walk, s: door.s, dir: this.rand() < 0.5 ? 1 : -1, v, side, alpha: 1, goal, walked: 0, door: { x: door.ix, y: door.iy, t: 0, out: true } };
      else {
        const near = this._ringIndex(cx, cy, 'w', 30, 220);
        if (near) {
          const [, k, s0] = near;
          this.slots[free] = { walk: this.walks[k], s: s0 + this.rand() * 20, dir: this.rand() < 0.5 ? 1 : -1, v, side, alpha: 0, goal, walked: 0 };
        }
      }
    }
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), p3 = new THREE.Vector3(), e = new THREE.Euler();
    for (let i = 0; i < MAX_WALKERS; i++) {
      const w = this.slots[i];
      if (!w) { if (draw) { m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); } continue; }
      const pos = (s) => {
        const p = w.walk.path.at(s), off = w.walk.off + w.side;
        return { x: p.x + p.hy * off, y: p.y - p.hx * off, p };
      };
      let x, y, hx, hy;
      if (w.door) {
        // stepping out of a building onto the footway (or back in), at walking pace
        const d = w.door, f = pos(w.s), L = Math.hypot(f.x - d.x, f.y - d.y) || 1;
        d.t = Math.min(1, d.t + (dt * w.v) / L);
        const u = d.out ? d.t : 1 - d.t;
        x = d.x + (f.x - d.x) * u; y = d.y + (f.y - d.y) * u;
        hx = ((f.x - d.x) / L) * (d.out ? 1 : -1); hy = ((f.y - d.y) / L) * (d.out ? 1 : -1);
        if (d.t >= 1) {
          if (!d.out) { this.slots[i] = null; m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
          w.door = null;
        }
      } else {
        const ahead = pos(w.s + w.dir * 1.5);
        // (it may have spawned past the end)
        if (w.s > w.walk.path.length) { w.s = w.walk.path.length; w.dir = -1; }
        if (w.s < 0) { w.s = 0; w.dir = 1; }
        // turn back before the tracks, but never while standing in a car lane (finish crossing first: a
        // walker turning back and forth there blocked the cars); after turning it commits to its way for
        // a few seconds (a path ending by the tracks had it flip every frame, line 17 s 13756)
        const here = pos(w.s), end = w.s + w.dir < 0 || w.s + w.dir > w.walk.path.length;
        w.commit = Math.max(0, (w.commit || 0) - dt);
        if (end) {
          // the way it is going (kept across link walks: a link's own direction is sideways)
          const H = w.walk.link && w.travel ? w.travel : { x: here.p.hx * w.dir, y: here.p.hy * w.dir };
          // how well each way on continues it: a link walk by its direction, a walk by its tangent there
          // (either way along it); not back where it came from if there is another way. (Taking any
          // link at random sent walkers onto the parallel sidewalk / footway and back: a U-turn every 7 m.)
          const links = w.walk.links?.[w.dir > 0 ? 1 : 0] || [];
          const score = (o) => {
            if (o.walk.link) { const a = o.walk.path.at(0), b = o.walk.path.at(o.walk.path.length); return o.s < 0.5 ? a.hx * H.x + a.hy * H.y : -(b.hx * H.x + b.hy * H.y); }
            const t = o.walk.path.at(o.s), len = o.walk.path.length, c = t.hx * H.x + t.hy * H.y;
            return o.s < 0.5 ? c : o.s > len - 0.5 ? -c : Math.abs(c);
          };
          const scored = links.filter((o) => o.walk !== w.prev).map((o) => [o, score(o)]);
          const best = scored.reduce((a, b) => Math.max(a, b[1]), -Infinity);
          const good = scored.filter(([, sc]) => sc > 0.3 && sc >= best - 0.4);
          const pick = good.length ? good[Math.floor(this.rand() * good.length)][0] : best > -0.3 ? scored.find(([, sc]) => sc === best)[0] : null;
          if (pick) {
            const nq = pick.walk.path.at(pick.s), len = pick.walk.path.length;
            w.prev = w.walk; w.walk = pick.walk; w.s = pick.s; w.travel = H;
            w.dir = pick.s < 0.5 ? 1 : pick.s > len - 0.5 ? -1 : nq.hx * H.x + nq.hy * H.y >= 0 ? 1 : -1;
            w.commit = 2;
            // (its sideways offset is along the way's drawing direction: onto a way drawn the other way it
            // flipped sides, a 1.2 m hop at the join; keep the side nearer to where it stands)
            const pa = pos(w.s);
            w.side = -w.side;
            const pb = pos(w.s);
            if (Math.hypot(pa.x - here.x, pa.y - here.y) < Math.hypot(pb.x - here.x, pb.y - here.y)) w.side = -w.side;
          } else { w.dir = -w.dir; w.commit = 4; w.travel = null; w.prev = null; } // a dead end: back
        } else if (!w.commit && this.trackDist(ahead.x, ahead.y) < TRACK_CLEAR && !this.inLane(here.x, here.y)) w.dir = -w.dir;
        // (B9) at the kerb, about to step into a car lane: wait while a car is coming (it would reach the
        // spot within 4 s); once in the lane, go on (cars stop for walkers on their path)
        else if (!this.inLane(here.x, here.y) && this.inLane(ahead.x, ahead.y)
          && (this._pedRed(ahead.x, ahead.y, here.p.hx * w.dir, here.p.hy * w.dir) || this._carComing(ahead.x, ahead.y))) w.waitKerb = true; // (D2: and for its red)
        else {
          w.waitKerb = false;
          const s0 = w.s;
          w.s += w.dir * w.v * dt;
          w.walked += w.v * dt;
          // its walk done: into the first door it passes
          if (w.walked > w.goal && w.walk.doors?.length) {
            const lo = Math.min(s0, w.s), hi = Math.max(s0, w.s), d = w.walk.doors.find((o) => o.s >= lo && o.s <= hi);
            if (d) { w.s = d.s; w.door = { x: d.ix, y: d.iy, t: 0, out: false }; }
          }
        }
        const pp = pos(w.s);
        x = pp.x; y = pp.y; hx = pp.p.hx * w.dir; hy = pp.p.hy * w.dir;
      }
      w.x = x; w.y = y;
      const far = Math.hypot(x - cx, y - cy) > 260;
      w.alpha = Math.max(0, Math.min(1, w.alpha + (far ? -dt : dt) / FADE));
      if (far && w.alpha <= 0) { this.slots[i] = null; m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
      if (!draw) continue;
      // fade by growing out of / sinking into the ground (instances share one material)
      const k = w.alpha;
      // the ground height again only after 0.3 m (a lookup costs ~7 us; walkers go 1.1-1.6 m/s, so
      // most frames reuse it: the step it makes is a few mm on a sloping footway)
      if (w.zx === undefined || Math.abs(x - w.zx) + Math.abs(y - w.zy) > 0.3) {
        w.z = w.walk.hf ? w.walk.hf(x, y) : this.ground.surface(x, y);
        w.zx = x; w.zy = y;
      }
      p3.set(x, w.z - (1 - k) * 1.8, -y);
      e.set(0, Math.atan2(hx, -hy), 0);
      q.setFromEuler(e);
      sc.set(1, 1, 1);
      m.compose(p3, q, sc);
      this.crowd.setMatrixAt(i, m);
    }
    if (!draw) return;
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
    // (a run number from a counter, not this.rand: the seeded traffic runs stay as they were; no
    // destination card: where another line's tram goes is not in our data)
    this.tramCount = (this.tramCount || 0) + 1;
    const mesh = makeT3({ line, cars, detailed: this.game.opts.detailed, run: `8${String(1 + ((this.tramCount * 17) % 40)).padStart(2, '0')}` });
    setOpacity(mesh, 0);
    this.group.add(mesh);
    return { mesh, length: T3.length * cars + COUPLING_GAP * (cars - 1) };
  }

  _tramFade(t, dt, leaving) {
    t.alpha = Math.max(0, Math.min(1, (t.alpha ?? 0) + (leaving ? -dt : dt) / FADE));
    setOpacity(t.mesh, t.alpha);
  }

  // Trams of other lines ahead of us: they stop at stops and at signals not showing GO. They keep their
  // head start as a dispatcher would have them: at the speed limit, and with our tram within 300 m they
  // only let people on and off (6-8 s) instead of a full dwell (user: catching up with them kept
  // delaying the tram; line 17: 173 s behind them over the line at 85 % of the limit, 12-24 s dwells,
  // spawned 450-900 m ahead).
  _updateAhead(dt, tram) {
    const g = this.game;
    for (const sig of g.signals) { sig.aheadCommitted = false; sig.aiRequest = false; } // (set again below, read by the controller)
    this.spawnTimer -= dt;
    if (this.spawnTimer <= 0 && this.ahead.length < 2) {
      this.spawnTimer = 40 + this.rand() * 80;
      const st = g.stops.find((x) => x.target > tram.s + 700 && x.target < tram.s + 1300 && x.i > g.nextStop);
      const other = st && this._otherLine(st.i, 1);
      if (other && !this.ahead.some((t) => Math.abs(t.s - st.target) < 60)) {
        this.ahead.push({ ...this._newTram(other.line), endS: other.endS, s: st.target, v: 0, dwell: 10 + this.rand() * 15, lastStop: st.i });
      }
    }
    const profile = this.ground.profile;
    for (const t of this.ahead) {
      let vt = limitSpeed(g.limits, t.s, t.length);
      const close = t.s - t.length - tram.s < 300; // (our tram closing in)
      let stopAt = null;
      const st = g.stops.find((x) => x.target > t.s + 0.5);
      if (st) stopAt = st.target;
      // our signals, as the oncoming trams do theirs (_updateOncoming): stop when still able to as the GO
      // starts blinking (or on red), keep stopping for it until GO; too close: go on, the controller holds
      // the phase (sig.aheadCommitted). Every signal within 150 m, not only the next one: a driver sees
      // the red one beyond the junction ahead (it saw it only after passing the first, line 17 s 10251).
      t.redStops ||= new Set();
      for (const x of t.redStops) if (x.state === 'go') t.redStops.delete(x);
      for (const sig of g.signals) {
        // (D2: an AI tram asks for priority like ours, from 140 m)
        if (sig.s > t.s && sig.s - t.s < 140 && !t.leaving) sig.aiRequest = true;
        if (sig.s <= t.s + 0.5 || sig.s - t.s > 150 || sig.state === 'go') continue;
        // (a tram standing at a platform whose signal stands at its head, 2 m past the stop point, is
        // already past "3 m before the signal": it stays as long as it is before the head itself)
        const d = sig.s - 3 - t.s;
        if ((d > 0 && d > stopDistance(t.v, sig.state)) || (t.v < 0.5 && t.s < sig.s - 0.3)) t.redStops.add(sig);
        if (t.redStops.has(sig)) { if (sig.s - 3 < (stopAt ?? Infinity)) stopAt = sig.s - 3; }
        else if (sig.state === 'warn' && d > -3) sig.aheadCommitted = true;
      }
      const other = this.ahead.find((o) => o !== t && o.s > t.s);
      if (other && other.s - other.length - 6 < (stopAt ?? Infinity)) stopAt = other.s - other.length - 6;
      // a car on the track ahead (along it, or crossing it: it gives way to our tram only)
      for (const c of g.carsOnTrack || []) if (c.s > t.s && c.s - 2.5 - 4 < (stopAt ?? Infinity)) stopAt = c.s - 2.5 - 4;
      for (const c of g.carsCrossing || []) if (c.s > t.s && c.s - 6 < (stopAt ?? Infinity)) stopAt = c.s - 6;
      // (on its braking curve it brakes as hard as it takes to stop at the point, as _updateOncoming)
      let aStop = Infinity;
      if (close && t.dwell > 8) t.dwell = 6 + (t.dwell % 2); // (only boarding while we close in)
      if (t.dwell > 0) { t.dwell -= dt; vt = 0; }
      else if (stopAt !== null) {
        const d = stopAt - t.s;
        vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * 0.9 * Math.max(0, d - 0.5))));
        if (t.v > vt - 0.05 && t.v > 0.05) aStop = -(t.v * t.v) / (2 * Math.max(0.1, d - 0.5));
        if (d < 0.8 && t.v < 0.3) {
          t.v = 0;
          if (st && stopAt === st.target && t.lastStop !== st.i) { t.lastStop = st.i; t.dwell = close ? 6 + this.rand() * 2 : 12 + this.rand() * 12; }
        }
      }
      const a = Math.max(-1.3, Math.min(1.0, (vt - t.v) * 0.8, aStop));
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
      const n = br.nearestOnHeading(o.x, o.y, -o.hx, -o.hy);
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
    for (const sig of this.game.signals) sig.backCommitted = false; // (set again below, read by the controller)
    for (const t of this.oncoming) {
      let vt = limitSpeed(this.backLimits, t.s, t.length) * 0.85;
      let stopAt = this.backStops.find((s) => s > t.s + 0.5 && !t.served.has(s)) ?? null;
      const isStop = stopAt !== null;
      for (const c of this.carsOnBack || []) if (c.s > t.s && c.s - 2.5 - 4 < (stopAt ?? Infinity)) stopAt = c.s - 2.5 - 4;
      // keep a distance to the oncoming tram in front
      for (const o of this.oncoming) if (o !== t && o.s > t.s && o.s - o.length - 6 < (stopAt ?? Infinity)) stopAt = o.s - o.length - 6;
      // junction signals: the opposite direction has GO together with our straight phase; a tram
      // that can still stop comfortably when its GO starts blinking (or is red) waits at its stop
      // line, and keeps waiting for that signal until it shows GO again. One that cannot is in the
      // dilemma zone: it goes on, and the controller holds the phase for it (sig.backCommitted).
      // (Every signal decided on is kept: with a single "red stop", two red signals close together
      // took it from each other and the tram drove through the nearer one, line 17 s 9791, 20819.)
      t.redStops ||= new Set();
      for (const sig of t.redStops) if (sig.backState === 'go') t.redStops.delete(sig);
      for (const sig of this.game.signals) {
        if (sig.backCross === undefined || sig.backState === 'go') continue;
        const line = sig.backCross - 6, d = line - t.s;
        // (stopDistance: comfortable for a blinking GO, full service braking for a red; a tram standing
        // or just starting can always stay)
        if (d > 0 && d < 150 && (d > stopDistance(t.v, sig.backState) || t.v < 0.5)) t.redStops.add(sig);
        if (t.redStops.has(sig)) { if (line - 3 < (stopAt ?? Infinity) && d > -1) stopAt = line - 3; } // a little before the line
        else if (d > 0 && d < 150 && sig.backState === 'warn') sig.backCommitted = true;
      }
      for (const G of gauntlets) {
        if (t.s > G.b0 && t.s - t.length < G.b1) G.theirs.occupied = true;
        if (t.s <= G.b0 && G.b0 - t.s < 150) {
          G.theirs.requested = true;
          const allowed = G.state === 'theirs' && !G.entered;
          if (!allowed && G.b0 - 4 < (stopAt ?? Infinity)) stopAt = G.b0 - 4;
        }
      }
      // (on its braking curve a tram brakes as hard as it takes to stop at the point, up to 1.3 m/s2:
      // following the curve's speed with a lag over-ran stop points by 3-4 m, onto red stop lines)
      let aStop = Infinity;
      if (t.dwell > 0) { t.dwell -= dt; vt = 0; }
      else if (stopAt !== null) {
        const d = stopAt - t.s;
        vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * 0.9 * Math.max(0, d - 0.5))));
        if (t.v > vt - 0.05 && t.v > 0.05) aStop = -(t.v * t.v) / (2 * Math.max(0.1, d - 0.5));
        if (d < 0.8 && t.v < 0.3 && isStop && this.backStops.includes(stopAt)) { t.served.add(stopAt); t.dwell = 10 + this.rand() * 10; }
      }
      const a = Math.max(-1.3, Math.min(1.0, (vt - t.v) * 0.8, aStop));
      t.v = Math.max(0, t.v + a * dt);
      t.s += t.v * dt;
      const p = br.at(t.s), me = this.route.at(tram.s);
      // past the last stop it shares with our line it turns off
      const ourS = t.endS !== null ? this.route.nearestOnHeading(p.x, p.y, -p.hx, -p.hy)?.s : null;
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
