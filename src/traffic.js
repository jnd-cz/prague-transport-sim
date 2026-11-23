// SPDX-License-Identifier: AGPL-3.0-or-later
// Ambient life: cars on the road network (a lane graph: one smooth lane per road and direction,
// connector curves through the junctions), pedestrians on footways and sidewalks, and other trams
// (ahead of us on our track, and oncoming on the opposite track). Everything fades in and out
// instead of popping.
import * as THREE from 'three';
import { makeCar, makeCrowd, makeT3, placeConsist, poseT3, setNextStop, makeTrafficLights, makePedLights, disposeModel } from './models.js';
import { T3, COUPLING_GAP, CAR_PITCH } from './tram.js';
import { setRiggedLevel, FULL_IN, FULL_OUT } from './rigged.js';
import { junctionTurns, indicating } from './indicators.js';
import { t as tx } from './i18n.js'; // (t is the trams' loop variable here)
import { aiLineCurrent } from './electric.js';

const OTHER_LINES = ['9', '15', '23', '2', '18', '13', '7', '4'];
const MAX_CARS = 30, MAX_WALKERS = 90, FADE = 1.2;
const TRACK_CLEAR = 2.8; // pedestrians and cars keep this far from a track centre line
// a walker that turns back twice within TURN_ROOM m of walking, or keeps within STILL_R m of a place for STILL_T s
// while not waiting at a kerb, has nowhere to go and leaves (_turnBack, _leave; #366, #269, #393)
const TURN_ROOM = 3, STILL_R = 2, STILL_T = 10;

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

// Seconds an AI tram at v takes to bring its front `d` m on, braking on its curve (0.7 m/s², as limitSpeed) to vEnd there, and no
// faster than now (one that would still speed up gets there sooner: the count errs towards stopping)
function timeTo(d, v, vEnd) {
  let t = 0;
  for (let x = 0.5; x < d; x += 1) t += 1 / Math.max(0.5, Math.min(Math.max(v, 0.5), Math.sqrt(vEnd * vEnd + 2 * 0.7 * (d - x))));
  return t;
}

// The speed (m/s) an AI tram may run at s: the limit under the whole set, and every lower limit ahead
// reached on a braking curve (0.7 m/s2, as our tram's nextLimitChange). With only the limit where it
// stood it ran into a slow section at full speed, braked inside it and crawled on a held blinking GO
// until it turned red (line 17 s 10826).
// AI trams run AI_UNDER m/s under it, as our autopilot catching up (#242; the user, 2026-11-10: "keep them simply driving swiftly up
// under the given speed limit"); the oncoming trams ran at 0.85 of it.
const AI_UNDER = 0.2;
function limitSpeed(lim, s, len) {
  let v = Math.min(lim.at(s), lim.at(s - len)) / 3.6;
  for (let d = 5; d < 300; d += 5) v = Math.min(v, Math.sqrt((lim.at(s + d) / 3.6) ** 2 + 2 * 0.7 * Math.max(0, d - 5)));
  return v;
}

export function setOpacity(obj, a) {
  obj.visible = a > 0.01;
  obj.traverse((o) => {
    const m = o.material;
    if (!m) return;
    // (glass keeps its own opacity: userData.opacity, src/rigged.js. A material blended from the start
    // stays blended: the hybrid's fleet numbers are a decal on a clear canvas, whose clear pixels drew
    // black once the faded-in tram went opaque)
    const base = m.userData.opacity ?? 1;
    m.userData.blend ??= m.transparent;
    m.userData.fade = a;
    m.transparent = a < 0.999 || base < 1 || m.userData.blend;
    m.opacity = a * base;
    m.depthWrite = a > 0.5 && base === 1 && !m.userData.blend;
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
    // The network the build made (tools/network.py, data/lineN.network.json, #658): the roads (OSM's ways split at their
    // junctions, smoothed, fitted to the survey's kerbs and medians, the tracks on them), their lanes, the footways (OSM's
    // and the sidewalks the survey shows beside the roads, linked across the streets), the doors, the signals bound to
    // the lanes and their heads. Start builds none of it and reads no survey. (Positions in cm, a path's points in mm.)
    const N = data.network, ways = data.allRoads || data.roads;
    if (!N?.lanes) throw new Error(`line ${data.line}: no network (data/line${data.line}.network.json): python -P -E tools/network.py --lines ${data.line}`);
    // (a path's points in mm: in cm a straight lane zigzagged enough for curveSpeeds to slow the cars on it)
    const pts = (a) => { const out = []; for (let i = 0; i < a.length; i += 2) out.push([a[i] / 1000, a[i + 1] / 1000]); return out; };
    const m = (a) => a.map((v) => v / 100);
    this.roads = [];
    this.walks = [];
    // what a road's cars and walkers stand on: the street surface, or on a bridge (OSM bridge tag) the deck it lies on,
    // exactly as the road is drawn (ground.way: the span of the whole chain of its ways, its ends the build's,
    // tools/network.py heights, #682); in a road tunnel its floor between the portals
    this.surfaceFn = (r) => {
      if (!r.b && !r.t) return (x, y) => ground.surface(x, y);
      const src = ways[r.way], w = ground.way(src.way || src.p, !r.t, !!r.t);
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
    for (const R of N.roads) {
      const road = { path: new Path(pts(R.p)), w: R.w, o: R.o || 0, tram: R.tram, b: R.b || 0, t: R.t || 0, ln: R.ln, lf: R.lf, lb: R.lb,
        ends: R.ends, way: R.way, fitLo: R.lo ? m(R.lo) : null, fitHi: R.hi ? m(R.hi) : null, fitMed: R.med ? R.med.map(m) : null,
        trk: R.trk ? R.trk.map(m) : null };
      road.hf = this.surfaceFn(road);
      this.roads.push(road);
      if (road.path.length >= 15) addIndex('r', this.roads.length - 1, road.path); // spawn only on real streets
    }
    // (a link walk, a crossing or a join, stands on the street's surface: its hf null)
    for (const W of N.walks) {
      const walk = { path: new Path(pts(W.p)), off: 0, hf: W.link ? null : W.deck ? this.surfaceFn({ b: 1, way: W.way }) : (x, y) => ground.surface(x, y), deck: !!W.deck };
      if (W.link) walk.link = true;
      else addIndex('w', this.walks.length, walk.path);
      this.walks.push(walk);
    }
    N.walks.forEach((W, i) => { this.walks[i].links = W.links.map((e) => e.map(([k, s]) => ({ walk: this.walks[k], s: s / 100 }))); });
    this._loadLanes(N, pts);
    this._loadDoors(N);
    this._loadSignals(N);

    this.cars = [];
    this.walkers = [];
    this.walkLoops = new Map(); // place "x,y" -> times a walker turned back there rather than round a loop (#496)
    this.walkLeaves = new Map(); // "why x,y" -> times a walker with nowhere to go left there (_leave, #366)
    this.crowd = makeCrowd(MAX_WALKERS);
    this.group.add(this.crowd);

    // where oncoming trams stop: the front at the far end of their own platform (game.platforms of the
    // back route: OSM shapes, GTFS positions). Mapped from our stop point they stopped 8 m into theirs:
    // our platform's far end is near the start of theirs (user: "they stop just before the stop instead
    // of running to its end"). Only there: our stop mapped across, the fallback where they had no platform within
    // 30 m, stopped them opposite our stop sign with doors open, a second stop where theirs is staggered 27-141 m
    // away (42 of the 49 such points on the five lines) and one where PID has none for them (the user, 2026-11-09:
    // "ai trams from other direction still seem to stop and open door at our direction's stops but a bit past the
    // stop sign"). Our stops with no platform of the same name for them: noOppositeStop (lint).
    // (on their right: the T3's doors; not at a platform no tram stops at, `unused`, #407)
    // (overlapping platforms of one stop, OSM and GTFS, are one stretch: two stop points in one platform
    // stopped the tram twice, Kobylisy 951 and 1012)
    const backPl = (game.platforms || []).filter((p) => p.back && p.rt === this.back && p.side < 0 && !p.unused).map((p) => [p.s0, p.s1]).sort((a, b) => a[0] - b[0]);
    const runs = [];
    for (const [a, b] of backPl) if (runs.length && a < runs[runs.length - 1][1] + 10) runs[runs.length - 1][1] = Math.max(runs[runs.length - 1][1], b); else runs.push([a, b]);
    const ends = runs.map(([, b]) => b - 1);
    this.backStops = this.back ? ends : [];
    // what AI trams show (#436, drawing only): the junction turns along our route, where they indicate; the stops
    // where passengers cross a car lane (ours: Vienna-type, theirs: a platform with a kerb), where they indicate
    // right; the stops' names in order, for a T3M's side display
    this.lampWays = {
      ahead: { turns: junctionTurns(route, game.data.switches), kerb: game.stops.filter((st) => st.vienna).map((st) => st.target),
        stops: game.stops.map((st) => ({ s: st.target, name: st.name })) },
      back: { turns: [], kerb: [], stops: [] },
    };
    if (this.back) {
      const pl = (game.platforms || []).filter((q) => q.back && q.rt === this.back && q.side < 0 && !q.unused).sort((a, b) => a.s1 - b.s1);
      Object.assign(this.lampWays.back, { kerb: pl.filter((q) => q.kerb != null).map((q) => q.s1 - 1), stops: pl.map((q) => ({ s: q.s1 - 1, name: q.name })) });
    }
    const backNames = new Set((game.platforms || []).filter((p) => p.back && p.rt === this.back && p.side < 0 && !p.unused).map((p) => p.name));
    this.noOppositeStop = this.back ? game.stops.filter((st) => !backNames.has(st.name)).map((st) => ({ stop: st.name, s: st.target })) : [];
    // a junction's stop line for oncoming trams (backCross − 6, in update) inside a platform: the point lay up to 1.7 m past
    // the line, and a tram pulling in as the signal turned red rolled over it to reach the point (line 37 s 4688, line 9
    // s 5409, #385). A line up to 10 m before the point moves it to 3 m before the line, where a red stops it anyway, if
    // the front is still 10 m into the platform there (a door at it); otherwise it stays and is listed as kept. Each one in
    // platformCaps (lint). (A line further back, inside a long platform, is left to the red and dilemma rules below: one
    // 41-52 m before the end of an 83 m platform at Přístaviště and Nádraží Modřany on line 17, where the tram passes it
    // at speed, the phase held for it.)
    this.platformCaps = [];
    const lines = (game.signals || []).filter((g) => g.backCross !== undefined).map((g) => ({ sig: Math.round(g.s), line: g.backCross - 6 }));
    this.backStops = this.backStops.map((p) => {
      const piece = backPl.filter(([a, b]) => p >= a && p <= b).sort((x, y) => y[0] - x[0])[0];
      const from = piece ? piece[0] : p - 10;
      const L = lines.filter((x) => x.line > Math.max(from, p - 10) && x.line - 3 < p).sort((a, b) => a.line - b.line)[0];
      if (!L) return p;
      const to = L.line - 3, moved = to >= from + 10;
      this.platformCaps.push({ s: p, to: moved ? to : null, line: L.line, sig: L.sig, platform: !!piece });
      return moved ? to : p;
    }).sort((a, b) => a - b);
    // other lines that really serve this route's stops (from GTFS)
    const other = new Set();
    const mine = new Set((game.segments || []).map((g) => g.line));
    for (const st of data.stops) for (const l of st.lines || []) if (!mine.has(l)) other.add(l);
    this.otherLines = other.size ? [...other] : OTHER_LINES;
    this.ahead = [];
    this.oncoming = [];
    this.spawnTimer = 3;
  }

  // ------------------------------------------------------------------ lane graph
  // Every road has one lane per driving direction (and per OSM lane), as the build laid it (tools/network.py
  // build_lanes: beside the surveyed kerbs, a median or the tracks' middle, trimmed back from both junctions, smoothed).
  // A car follows its lane's own tangent, so it never moves sideways; through a junction a connector curve leads from
  // the end of one lane to the start of the next.
  _loadLanes(N, pts) {
    this.laneList = [];
    this.lanesFrom = new Map(); // junction key -> lanes starting there
    this.lanesTo = new Map();   // junction key -> lanes ending there
    this.connectors = new Map();
    this.conflicts = new Map();
    this.laneGrid = new Map(); // lane points in 4 m cells (is a point in a lane?)
    const push = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
    for (const r of this.roads) r.lanes = [];
    for (const L of N.lanes) {
      const r = this.roads[L.road], k = L.road, dir = L.dir, path = new Path(pts(L.p)), trim = Math.min(5, r.path.length * 0.2);
      const lane = { id: this.laneList.length, road: r, k, dir, sel: L.sel, trim, path, from: r.ends[dir > 0 ? 0 : 1], to: r.ends[dir > 0 ? 1 : 0] };
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

  dispose() { this.scene.remove(this.group); disposeModel(this.group); }

  // The point the traffic lives round (#722): our tram's front, whatever the camera shows. Cars and walkers appear in a
  // ring round it and go to sleep by their distance from it. Before, the camera's place: the cab and the chase view, or
  // a free camera, gave different runs of one seed, and the benches put the camera at the cab to get this point.
  focus() {
    const p = this.route.at(this.game.tram.s);
    return [p.x, p.y];
  }

  // draw: false for a step whose result is not shown (inspect mode runs several steps per frame):
  // cars and walkers move but are not posed (their height and matrices wait for the drawn step). `view`: the camera,
  // for what only the drawing reads (an AI tram's detailed model near it); nothing the run does depends on it.
  // `focus`: the focus where the step began, taken before the game's step (the page and the benches do: they set the
  // camera at the cab before it, and a focus after it, 0.3 m on at 10 m/s, gave another run of the seed).
  update(dt, view, draw = true, focus = this.focus()) {
    const tram = this.game.tram;
    const [cx, cy] = focus;
    this.cam = view ? [view.position.x, -view.position.z] : [cx, cy];
    this._carsOnTracks();
    this._updateRoadCars(dt, cx, cy, draw);
    this._updateWalkers(dt, cx, cy, draw);
    this._updateAhead(dt, tram);
    this._updateOncoming(dt, tram);
    this._wireLoads(dt);
    this._clearAiTramCycles(dt);
  }

  // what the steps move, for the page to draw between the last two (src/between.js): the cars in sight (posed on a
  // drawn step: update's draw) and the other trams' cars (placed every step). The walkers (1.1-1.6 m/s, 5 cm a step)
  // stay where the step left them.
  movers() {
    const out = [];
    for (const c of this.cars) if (c.alpha > 0) out.push(c.mesh);
    for (const t of this.ahead) out.push(...t.mesh.userData.cars);
    for (const t of this.oncoming) out.push(...t.mesh.userData.cars);
    return out;
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
          // (and at least 50 m from the focus itself, the tram's front: the ring's point picks an index cell, and a
          // cell can reach it; a car came in at 8 m/s 6 m before the track with the tram 4 m off, line 17 s 19919)
          const sp = lane.path.at(s), close = Math.hypot(sp.x - cx, sp.y - cy) < 50;
          const c = redNear || close || cars.some((o) => o.active && o.path === lane.path && Math.abs(o.s - s) < 12) ? null : this._carSlot();
          if (c) Object.assign(c, { id: undefined, active: true, kind: 'road', lane, road: r, dir: lane.dir, conn: null, next: undefined, next2: undefined, next2From: null, lightGo: null, lightHold: null, lead: null, path: lane.path, s, v: 7 + this.rand() * 6, vNow: null, coast: null, hitTram: false, cycleT: 0, z: undefined, seen: null, why: null });
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
        // (#602, the user, 2026-11-14: "they dont stop in front of the opposite direction's track when yielding to oncoming
        // trams": both tracks, each with its trams, ours and the AI trams ahead of it on ours, the oncoming ones on the other;
        // and a car waits before the first track it reaches: tracks with no room for a car between them are crossed as one)
        let xGap = null, keepClear = false, yieldAi = null;
        const xs = [];
        seq.forEach(([path, off], k) => {
          for (const x of this._trackCrossings(path)) {
            const dC = off + x.sIn; // the car's middle to where the track's band begins
            if (dC > -CAR_HALF - TRACK_ZONE - CAR_HALF && dC < 45) xs.push({ dC, dOut: off + x.sOut, sx: x.sx, rt: x.rt, sOurs: x.sOurs, k });
          }
        });
        xs.sort((a, b) => a.dC - b.dC);
        // (one crossing seen twice, the next path starting inside the track's band, counts once: a car
        // turning into a lane along the track stood with its nose on it, giving way at the second copy
        // past the first's edge, and the tram hit it; line 17 s 9903, seed 1)
        for (let i = xs.length - 1; i > 0; i--) if (xs.slice(0, i).some((o) => o.rt === xs[i].rt && Math.abs(o.sx - xs[i].sx) < 4)) xs.splice(i, 1);
        for (let i = 0; i < xs.length; i++) {
          const g = i > 0 && xs[i].dC - xs[i - 1].g.dOut < 2 * CAR_HALF + 2 * YIELD_GAP ? xs[i - 1].g : { dC: xs[i].dC, dOut: xs[i].dOut, k: xs[i].k };
          g.dOut = Math.max(g.dOut, xs[i].dOut);
          xs[i].g = g;
        }
        // a car turning onto the track (its way still on it 12 m past the band's edge: a lane along
        // the rails) does not clear it in a few seconds: it goes only when the tram could stop behind
        // it (s 9903: a bold driver turned in 36 m ahead of the tram at 45 km/h, crawled on along the
        // track and was hit)
        const wayAt = (d) => { for (let i = seq.length - 1; i >= 0; i--) if (d >= seq[i][1]) return seq[i][0].at(d - seq[i][1]); return null; };
        for (const x of xs) { const q = wayAt(x.dC + 12), n = q && x.rt.nearest(q.x, q.y); x.along = !!n && n.d < 2.6; }
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
        let gapFor = lead;
        if (ob && (gap === null || ob.gap < gap)) { gap = ob.gap; vLead = ob.v; gapFor = ob.car || ob.tram || (ob.what === 'our tram' ? tram : null); }
        c.xing = xs.find((x) => x.rt === this.route) || null; // (our track's: the checks read it)
        for (const x of xs) {
          if (c.z !== undefined && x.sOurs !== null && Math.abs(c.z - this.ground.profile.height(x.sOurs)) > LEVEL_APART) continue;
          const ours = x.rt === this.route, { dC, sx } = x, v = c.vNow ?? 0, front = dC - CAR_HALF;
          // where it waits: its front YIELD_GAP before the first track of the group, or before this one when already past that
          const gFront = x.g.dC - CAR_HALF, wait = gFront > 0 ? gFront : front;
          // (a car already across the group's first track goes on over the rest: waiting before the next one it stood on the
          // one behind it, and a tram there waited for it; line 37 s 4714, seed 5: our tram, a car on our track waiting for an
          // oncoming tram, which waited for a car on its track, which waited for ours. It stops only for a tram's body there)
          const across = gFront <= 0 && x.g.dC < x.dC;
          // (braking up to 5 m/s2; a car standing or crawling stays where it is: one held by the queue
          // 0.9 m from the band, inside YIELD_GAP, counted as committed and pulled out in front of the
          // tram when the queue moved on, line 17 s 9903)
          const canStop = v < 1 || wait - YIELD_GAP > (v * v) / 10 - 0.5;
          let holds = null;
          for (const t of ours ? [tram, ...this.ahead] : this.oncoming) {
            if (!t || (t !== tram && (t.alpha ?? 0) < 0.3)) continue;
            const onBody = sx > t.s - t.length - 2 && sx < t.s + 2;
            const tA = (sx - t.s - 2) / Math.max(t.v, 0.1), tC = (Math.max(0, front) + TRACK_ZONE + 2 * CAR_HALF) / Math.max(v, 2.5);
            const coming = t.v > 0.5 && sx >= t.s && (sx - t.s < 16 || tA < tC + (c.bold ? 0.5 : 2.5) || (x.along && sx - t.s < (t.v * t.v) / 2 + t.v * 2 + 20));
            if (onBody || (coming && !across)) { holds = t; break; }
          }
          if (holds && canStop && front > 0) {
            xGap = wait - YIELD_GAP + 8; // (following() stops 8 m short)
            // a crossing past a junction: wait before the junction, not in it, unless the car stands
            // wholly on the lane beyond. One waiting in the junction's mouth blocked a car leaving the
            // track the other way; the tram stopped for that one with its body on this car's crossing
            // (line 37 s 1475, seed 2). Where the tracks run through the junction, cars wait in it.
            const k = gFront > 0 ? x.g.k : x.k, J = seq[k - 1];
            if (J && J[2] && J[1] > 0 && wait + CAR_HALF - YIELD_GAP - 2 * CAR_HALF < seq[k][1]) {
              const toJ = J[1] - CAR_HALF - 1; // its front 1 m before the junction
              if (v < 1 || toJ > (v * v) / 10 - 0.5) xGap = toJ + 8;
            }
            if (holds === tram) c.xing = x; else yieldAi = holds;
            break;
          }
          // nor onto the tracks without room to leave them: the car ahead standing or crawling closer than
          // the way across (the group's bands and a car's length). A car stood on the track behind a queue that
          // waited, round the junction, for a car giving way to our tram, which waited for the first
          // (line 9 s 11221, seed 2)
          if (!across && gap !== null && vLead < 1 && gap < Math.max(0, wait) + (x.g.dOut - x.g.dC) + 2 * CAR_HALF && canStop && wait > 0) {
            xGap = wait - YIELD_GAP + 8; if (ours) c.xing = x; keepClear = true; break;
          }
          // nor while the junction after them holds it and the car could not wait clear of the tracks before it: one held at a
          // junction halts where it is within 9 m of it (look, below), so that is the room it needs past the tracks; else it
          // would wait on the rails (#602: line 37 s 4713, a car through two short lanes and two junctions found the second
          // held only on the lane past the track, standing on it; 33 cars on our track, 37 on the other, held so in 25 runs)
          if (!across && canStop && wait > 0) {
            const Jn = seq.find(([, off, isJ, cn]) => isJ && cn && off >= x.g.dC && off < x.g.dOut + CAR_HALF + 10);
            const held = Jn && this._junctionHeld(c, Jn[3], Jn[1], Jn[1] + 0.1, live);
            if (held && (held.exitFull || held.blocker)) { xGap = wait - YIELD_GAP + 8; if (ours) c.xing = x; keepClear = true; c.jBlock = held.exitFull ? 'exit full' : held.blocker.id; break; }
          }
          // crossing: on our track, or moving onto it (a car standing before it, held by a queue, is not:
          // the tram waited for two such cars for good, line 17 s 11629)
          if (ours && ((front <= 0 && front > -TRACK_ZONE - 2 * CAR_HALF) || (front > 0 && front < 8 && v > 1))) crossing.push({ s: sx, onTrack: front <= 0, car: c });
        }
        c.yielding = xGap !== null && !keepClear && !yieldAi; // (to our tram: what u3 counts)
        c.yieldAi = yieldAi; // (to an AI tram)
        c.keepClear = keepClear;
        // junctions, from braking distance on: wait while a car is on a crossing connector, nearer
        // to its own crossing one, or standing at the mouth of a lane the connector passes close to
        let jStop = null, jFor = null;
        c.jBlock = null;
        const look = Math.max(9, ((c.vNow ?? 0) ** 2) / 8 + 3);
        if (c.plan && c.toEnd < look) {
          const { exitFull, blocker } = this._junctionHeld(c, c.plan, c.toEnd, look, live);
          c.jBlock = exitFull ? 'exit full' : blocker ? blocker.id : null; // (for the stuck scene, tools/bench/stuck.js)
          if ((exitFull || blocker) && c.toEnd > 1.5) {
            jStop = c.toEnd - 2; jFor = exitFull || blocker;
          }
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
        const terms = { lead: following(gap, vLead), junction: jStop === null ? Infinity : following(jStop, 0), tram: following(xGap, 0), light: following(lGap, 0), curve: vCurve };
        const vt = Math.min(c.v, ...Object.values(terms));
        // (what holds the car, for the stuck scene)
        c.why = vt < 0.3 ? Object.keys(terms).find((k) => terms[k] === vt) || 'speed' : null;
        c.waitFor = c.why === 'lead' ? gapFor : c.why === 'junction' ? jFor : c.why === 'tram' ? (keepClear ? gapFor : yieldAi || tram) : null;
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
    // A car standing on our track in front of our standing tram, whose queue ends at a car that waits for
    // a standing tram (ours, its body across that car's way, or an oncoming one: it gave way while the tram came, the tram then stopped
    // for the car on the track behind it): none of the three can move, and the car on the track cannot
    // back off in this model. After 30 s it leaves (fades out, as at the edge of the traffic area).
    // Rules that kept the tram short of such crossings, or cars off the track, moved the cycle elsewhere
    // (line 22 s 12619 seed 3; 10 new stuck runs over 5 lines x 5 seeds; #154)
    // The same with an AI tram ahead of ours in the tram's place: it stopped for the car on the track,
    // which waited for that tram (line 9 seed 4 s 7581, line 23 seed 5 s 7693: 7200 s jams, #259).
    const fronts = [tram, ...this.ahead].filter((t) => t.v < 0.3).map((t) => t.s);
    for (const x of crossing) {
      const a = x.car;
      let ends = false;
      if (x.onTrack && fronts.some((f) => x.s > f && x.s - f < 15) && (a.vNow ?? 0) < 0.3) {
        for (let o = a, n = 0; o && n < 6; n++) {
          const sn = o.seen;
          if (!sn || (o.vNow ?? 0) > 0.3) break;
          if (!sn.car) { ends = (sn.what === 'our tram' || sn.what === 'tram') && sn.v < 0.3; break; } // (or an oncoming one, stopped for a car on its track)
          o = sn.car;
        }
      }
      a.cycleT = ends ? (a.cycleT || 0) + dt : 0;
      if (a.cycleT > 30) { a.active = false; a.cycleT = 0; this.cyclesBroken = (this.cyclesBroken || 0) + 1; }
    }
    for (const x of crossing) {
      if (!x.onTrack || x.car.hitTram || x.s < tram.s - 1 || x.s > tram.s + 0.5 || tram.v < 0.3) continue;
      x.car.hitTram = true;
      this.game._collision(tx('obj.crossingCar'));
    }
  }

  // Cars on our track and on the opposite one (within 1.6 m of a track centre: the car body then
  // overlaps a tram), as route positions: trams stop behind them (shared lanes, a car queuing on
  // the tracks). this.game.carsOnTrack: [{s, v, car}] along our route, carsOnBack along the opposite one.
  _carsOnTracks() {
    const ours = [], back = [];
    for (const c of this.cars) {
      if (!c.active || c.alpha < 0.5 || !c.path) continue;
      const p = c.path.at(c.s);
      // only cars going the tram's way hold it up (one facing it waits for the tram instead)
      const n = this.route.nearestOnHeading(p.x, p.y, p.hx, p.hy, CAR_ALIGN);
      // (a car on the road under our bridge, or on a bridge over the track, is not on it)
      if (n && c.z !== undefined && Math.abs(c.z - this.ground.profile.height(n.s)) > LEVEL_APART) continue;
      if (n && n.d < 1.6) ours.push({ s: n.s, v: c.vNow ?? 0, car: c });
      if (this.back) {
        const b = this.back.nearestOnHeading(p.x, p.y, p.hx, p.hy, CAR_ALIGN);
        if (b && b.d < 1.6) back.push({ s: b.s, v: c.vNow ?? 0, car: c });
      }
    }
    this.game.carsOnTrack = ours;
    this.carsOnBack = back;
  }

  // What holds car c at the junction of connector `plan`, its middle `dist` from the junction's entry, seeing the cars that
  // come to it from `look` m: { exitFull, blocker } (each a car or undefined)
  // (a car that is itself waiting for this one does not block it: in the junction, or standing in the
  // mouth of a lane leaving it - a car just out of the junction onto the track waited for the one
  // behind its tail, which waited for it, line 9 s 18390, #152; not a car before the junction: let
  // through, cars drove in behind one waiting for the tram and blocked the track, line 22 s 11969;
  // and a car only enters when its exit lane has room: it never stops inside the junction)
  // (nor does one in the exit's mouth that waits for this one: car 1299 stood on the track there
  // waiting for 1290, which waited for the exit to clear, line 9 s 18394 seed 1, #259)
  // (nor one whose chain of waits comes back to c through other cars, any length: car 875 stood on a connector waiting
  // for 851, held at the junction by 882, held by 875; line 17 seed 5 s 17693, #607. Of such a circle the car held at a
  // junction with the lowest id goes, the others keep waiting: all of them going drove them into each other)
  _junctionHeld(c, plan, dist, look, live) {
    const J = plan.at;
    const exitFull = live.find((o) => o !== c && o.path === plan.to.path && o.s < 7 && o.seen?.car !== c && o.lead !== c && !this._circleGoes(c, o));
    const blocker = live.find((o) => o !== c && (
      (o.conn && o.conn.at === J && this._conflict(o.conn, plan) && o.seen?.car !== c)
      || (!o.conn && o.plan && o.plan.at === J && o.toEnd < look && this._conflict(o.plan, plan)
        // (a car whose own path is blocked does not hold its turn: one close behind an obstacle, or
        // stopped behind a stopped one; line 9 s 8679, three cars waited for each other that way)
        && !(o.seen && (o.seen.gap < 4 || ((o.vNow ?? 0) < 0.3 && o.seen.v < 0.3)))
        && (o.toEnd < dist - 0.05 || (Math.abs(o.toEnd - dist) <= 0.05 && o.id < c.id)))
      || (!o.conn && o.lane !== plan.from && o.lane.to === J && o.toEnd < 5 && !(o.plan && o.plan.at === J) && this._nearLaneEnd(plan, o.lane, true))
      || (!o.conn && o.lane !== plan.to && o.lane.from === J && o.s < 5 && o.seen?.car !== c && this._nearLaneEnd(plan, o.lane, false))) && !this._circleGoes(c, o));
    return { exitFull, blocker };
  }

  // does o wait for c through a chain of waitFor (as the last step left them), and is c the one of that circle to go: the
  // lowest id among its cars held at a junction (#607)
  _circleGoes(c, o) {
    const ring = [c, o];
    for (let x = o.waitFor; x; x = x.waitFor) {
      if (x !== c) { if (ring.includes(x) || ring.length > 12) return false; ring.push(x); continue; }
      if (!ring.every((y) => y === c || y.why !== 'junction' || y.id > c.id)) return false;
      // (counted once a hold: the traffic check's junctionCircles)
      if (!(this.game.clock - (c.circleAt ?? -Infinity) < 5)) this.junctionCircles = (this.junctionCircles || 0) + 1;
      c.circleAt = this.game.clock;
      return true;
    }
    return false;
  }

  // Where a car path crosses a track, ours or the opposite one (cached per path): [{ sIn, sOut, sx, rt, sOurs }], sIn along
  // the path where it comes within 2.6 m of the track centre (the tram's swept edge and a margin), sOut where it leaves that
  // band, sx the track's route position there, rt that route, sOurs our route's position (for the heights; null where the
  // opposite track runs apart from ours). Only where the path crosses (|cos| < 0.7: not driving along the track, a car there
  // follows the tram instead) and not where our track passes over it on a bridge.
  _trackCrossings(path) {
    if (path._xings) return path._xings;
    const out = [];
    for (const rt of [this.route, this.back]) {
      if (!rt) continue;
      let cur = null;
      for (let s = 0; s <= path.length; s += 1) {
        const p = path.at(s), n = rt.nearest(p.x, p.y), near = !!n && n.d < 2.6;
        if (near && !cur) {
          const h = rt.at(n.s), o = rt === this.route ? n : this.route.nearest(p.x, p.y), sOurs = o && o.d < 10 ? o.s : null;
          const x = { sIn: s, sOut: path.length, sx: n.s, rt, sOurs };
          cur = Math.abs(p.hx * h.hx + p.hy * h.hy) < 0.7 && !(sOurs !== null && this.ground.profile.overBridge(sOurs)) ? x : 'skip';
          if (cur !== 'skip') out.push(cur);
        } else if (!near && cur) {
          if (cur !== 'skip') cur.sOut = s;
          cur = null;
        }
      }
    }
    return (path._xings = out);
  }

  // The paths a car drives next, each with the distance from the car to its start. Past a short next
  // lane (under 45 m) it also chooses the one after it (c.next2, kept when it gets there): a track
  // crossing two lanes ahead, beyond a 4 m piece in a junction's mouth, was seen only 5 m before the
  // track, too late to give way to the tram (line 17 s 16855).
  _seq(c) {
    const seq = [[c.path, -c.s, !!c.conn, c.conn]]; // [path, offset, a junction's connector, that connector]
    let lane = null, off = 0;
    if (c.conn) { lane = c.conn.to; off = c.conn.path.length - c.s; seq.push([lane.path, off]); }
    else if (c.next) {
      off = c.path.length - c.s;
      if (c.plan) { seq.push([c.plan.path, off, true, c.plan]); off += c.plan.path.length; }
      lane = c.next;
      seq.push([lane.path, off]);
    }
    if (lane && lane.path.length < 45) {
      if (c.next2 === undefined || c.next2From !== lane) { c.next2 = this._chooseNext(lane); c.next2From = lane; }
      if (c.next2) {
        const cn = this.connector(lane, c.next2);
        off += lane.path.length;
        if (cn) { seq.push([cn.path, off, true, cn]); off += cn.path.length; }
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
      const s = tram.s - 0.6 - 7.6 - k * CAR_PITCH, p = this.route.at(s), h = this.route.heading(s, 3);
      out.push({ x: p.x, y: p.y, z: this.ground.profile.height(s), hx: h.hx, hy: h.hy, l: 7.2, w: 1.3, vx: h.hx * tram.v, vy: h.hy * tram.v, what: 'our tram' });
    }
    for (const t of [...this.ahead, ...this.oncoming]) {
      if ((t.alpha ?? 0) < 0.3) continue;
      for (const m of t.mesh.userData.cars) {
        const hx = Math.sin(m.rotation.y), hy = -Math.cos(m.rotation.y);
        out.push({ x: m.position.x, y: -m.position.z, z: m.position.y, hx, hy, l: 7.2, w: 1.3, vx: hx * t.v, vy: hy * t.v, what: 'tram', tram: t });
      }
    }
    for (const w of this.slots || []) {
      if (w && w.alpha > 0.5 && w.x !== undefined) out.push({ x: w.x, y: w.y, z: w.z, hx: 1, hy: 0, l: 0.4, w: 0.4, vx: 0, vy: 0, walker: w, what: 'walker' });
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
          return { gap: d - 2.6, v: Math.max(0, o.vx * q.hx + o.vy * q.hy), car: o.car, what: o.what, walker: o.walker, tram: o.tram };
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

  // The footway network, as the build linked it (tools/network.py link_walks): the walks are pieces (OSM footways, the
  // sidewalks of each street side, cut where the survey has no sidewalk) and every end links to the other walks passing
  // within 3 m of it, else to the nearest one within 15 m (across a side street), by a short straight link walk, never
  // across the tram's tracks. walk.links = [at its start, at its end], each a list of { walk, s }; a link walk
  // (walk.link) is a walk of its own, linked at both ends.
  // Doors: where a building meets the footway network (tools/network.py find_doors), for walkers to come out of and go
  // into. this.doors: { walk, s, x, y, ix, iy } (ix, iy: 1.5 m inside the building), by 50 m cell in this.doorIdx;
  // walk.doors: those on it, by s.
  _loadDoors(N) {
    for (const w of this.walks) if (!w.link) w.doors = [];
    this.doors = [];
    this.doorIdx = new Map();
    for (const [k, s, x, y, ix, iy] of N.doors) {
      const door = { walk: this.walks[k], s: s / 100, x: x / 100, y: y / 100, ix: ix / 100, iy: iy / 100 };
      this.doors.push(door);
      door.walk.doors.push(door);
      const kk = `${Math.floor(door.x / 50)},${Math.floor(door.y / 50)}`;
      if (!this.doorIdx.has(kk)) this.doorIdx.set(kk, []);
      this.doorIdx.get(kk).push(door);
    }
    for (const w of this.walks) w.doors?.sort((a, b) => a.s - b.s);
  }

  // D2, traffic lights. The junction controllers are the street signals' (game._runController); the build bound each
  // lane ending at a junction of such a signal to it (tools/network.py Signals: the game's signals, each lane's stop
  // line `back` m before its end, OSM's or the junction's edge, never on a zebra): 'along' the tram street (green with
  // the trams going straight, the opposite direction's GO; amber while it blinks) or 'cross' (green in the cross phase,
  // 3 s amber, 3 s all red). lane.light = { sig, kind, head, back, src }; a car signal head 4 m past each stop line,
  // 2.2 m right of the lane, on the street's surface (read at the load). (On-demand and single-track signals have no car
  // approaches.)
  // Pedestrian signal heads at OSM's signalled crossings (data/lineN.signals.json) of one of our signals: one on each
  // kerb of the street the node lies on, facing the people waiting across. Phases as _pedRed: walking across the tram
  // street (or a road along it) with the cross phase, across a side street with the trams going straight.
  // this.pedCross: [{ x, y, cx, cy, sig, along, heads }].
  _loadSignals(N) {
    // (a signal by its index in the line data: game.js keeps it on each of its signals)
    const sigOf = new Map(this.game.signals.filter((s) => s.i !== undefined).map((s) => [s.i, s]));
    const sig = (i) => {
      const s = sigOf.get(i);
      if (!s) throw new Error(`line ${this.game.data.line}: the network binds signal ${i}, the game has none such: the network is older than the data (python -P -E tools/network.py --lines ${this.game.data.line})`);
      return s;
    };
    // (each head on the street's surface, the build's: tools/network.py heights, #682)
    const head = (h) => ({ x: h.p[0] / 100, z: -h.p[1] / 100, h: h.z / 100, face: h.face / 1000 });
    this.lightLanes = [];
    this.lightSigs = [];
    for (const L of N.lights) {
      const lane = this.laneList[L.lane];
      lane.light = { sig: sig(L.sig), kind: L.kind, head: L.head, back: L.back / 100, src: L.src };
      this.lightLanes.push(lane);
    }
    for (const { sig: i } of N.lightSigs) {
      const s = sig(i), P = this.route.at(s.cross), h = this.route.heading(s.cross, 6);
      this.lightSigs.push({ sig: s, x: P.x, y: P.y, hx: h.hx, hy: h.hy });
    }
    this.lights = makeTrafficLights(N.heads.map(head));
    this.group.add(this.lights.group);
    this.pedCross = N.pedCross.map((c) => ({ x: c.p[0] / 100, y: c.p[1] / 100, cx: c.c[0] / 1e4, cy: c.c[1] / 1e4, sig: sig(c.sig), along: c.along, heads: c.heads }));
    this.pedLights = makePedLights(N.pedHeads.map(head));
    this.group.add(this.pedLights.group);
    const osm = this.lightLanes.filter((l) => l.light.src === 'osm').length;
    console.log(`traffic lights: ${N.heads.length} car heads at ${this.lightSigs.length} junctions (stop lines: ${osm} from OSM, ${this.lightLanes.length - osm} at the junction edge); pedestrian signals: ${N.pedHeads.length} heads at ${this.pedCross.length} crossings`);
  }

  // the light an approach shows: 'green' | 'amber' | 'red' | 'redamber' (the last 2 s before green)
  lightAspect(L) {
    const sig = L.sig, Y = sig.cycle, t = sig.t;
    if (L.kind === 'along') return sig.backState === 'go' ? 'green' : sig.backState === 'warn' ? 'amber' : Y.C - t < 2 ? 'redamber' : 'red';
    if (t >= Y.cross && t < Y.C - 6) return 'green';
    if (t >= Y.C - 6 && t < Y.C - 3) return 'amber';
    return t >= Y.cross - 2 && t < Y.cross ? 'redamber' : 'red';
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
  // there is another way), turning back only at a dead end; they turn back before the tracks. One with nowhere to go
  // (turned back twice within a few metres, or held in one place) leaves, fading where it stands.
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
          const [, k, s0] = near, s = s0 + this.rand() * 20, dir = this.rand() < 0.5 ? 1 : -1, q = this.walks[k].path.at(s);
          // (not by the tracks, where it would only turn back: three appeared on a crossing between the two tracks
          // and stood there turning, line 17 s 2918, #366)
          if (this.trackDist(q.x, q.y) >= TRACK_CLEAR || this.inLane(q.x, q.y)) this.slots[free] = { walk: this.walks[k], s, dir, v, side, alpha: 0, goal, walked: 0 };
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
        // turn back before the tracks: where its step ahead comes within TRACK_CLEAR of a track and nearer to it than
        // where it stands (one walking along a track keeps on: turning back there flipped it every frame and it stood
        // in a car's way for good, line 23 s 662, #366), but never while standing in a car lane (finish crossing first:
        // a walker turning back and forth there blocked the cars). One with nowhere to go leaves (_turnBack, below).
        const here = pos(w.s), end = w.s + w.dir < 0 || w.s + w.dir > w.walk.path.length;
        let dA;
        if (w.leave) { /* it stands while it fades */ } else if (end) {
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
          let pick = good.length ? good[Math.floor(this.rand() * good.length)][0] : best > -0.3 ? scored.find(([, sc]) => sc === best)[0] : null;
          // nor round a loop: onto a walk it entered less than 15 m ago it turns back instead, as at a dead end. (Four
          // short pieces joined 1 m from each other's ends made a 7 m ring across a driveway; each end's least bad way
          // on led round it, and six walkers circled there for good in front of a car, whose queue stood on our
          // track: line 23 s 3349, seed 1, #496.) Counted per place in walkLoops (window.traffic).
          if (pick && w.trail?.some((o) => o.walk === pick.walk && w.walked - o.at < 15)) {
            const k = `${Math.round(here.x)},${Math.round(here.y)}`;
            this.walkLoops.set(k, (this.walkLoops.get(k) || 0) + 1);
            pick = null;
          }
          if (pick) {
            w.trail = [...(w.trail || []).slice(-5), { walk: pick.walk, at: w.walked }];
            const nq = pick.walk.path.at(pick.s), len = pick.walk.path.length;
            w.prev = w.walk; w.walk = pick.walk; w.s = pick.s; w.travel = H;
            w.dir = pick.s < 0.5 ? 1 : pick.s > len - 0.5 ? -1 : nq.hx * H.x + nq.hy * H.y >= 0 ? 1 : -1;
            // (its sideways offset is along the way's drawing direction: onto a way drawn the other way it
            // flipped sides, a 1.2 m hop at the join; keep the side nearer to where it stands)
            const pa = pos(w.s);
            w.side = -w.side;
            const pb = pos(w.s);
            if (Math.hypot(pa.x - here.x, pa.y - here.y) < Math.hypot(pb.x - here.x, pb.y - here.y)) w.side = -w.side;
          } else this._turnBack(w, here); // a dead end: back
        } else if ((dA = this.trackDist(ahead.x, ahead.y)) < TRACK_CLEAR && dA < this.trackDist(here.x, here.y) - 0.05
          && !this.inLane(here.x, here.y)) this._turnBack(w, here);
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
        // the backstop: one that keeps within STILL_R of a place for STILL_T while not waiting at a kerb is held by
        // something (a loop of walks, a turn) and leaves: a car on its way would wait for it for good, and the car's
        // queue on our track held the tram (line 22 s 7656, #393; line 23 s 5059, #269)
        if (!w.leave && !w.door) {
          const a = w.still;
          if (!a || w.waitKerb || Math.hypot(here.x - a.x, here.y - a.y) > STILL_R) w.still = { x: here.x, y: here.y, t: 0 };
          else if ((a.t += dt) > STILL_T) this._leave(w, here, 'stuck');
        }
        const pp = pos(w.s);
        x = pp.x; y = pp.y; hx = pp.p.hx * w.dir; hy = pp.p.hy * w.dir;
      }
      w.x = x; w.y = y;
      const going = w.leave || Math.hypot(x - cx, y - cy) > 260; // (far off, or leaving)
      w.alpha = Math.max(0, Math.min(1, w.alpha + (going ? -dt : dt) / FADE));
      if (going && w.alpha <= 0) { this.slots[i] = null; m.makeScale(0, 0, 0); this.crowd.setMatrixAt(i, m); continue; }
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

  // A walker turns back (a dead end, a loop, the tracks ahead). One that turned back less than TURN_ROOM of walking ago
  // has nowhere to go (the tracks or a dead end both ways: between the two tracks of a crossing, a short piece by a
  // track; turning there flipped it every frame, line 17 s 2918, #366) and leaves.
  // A turn frees the way back it came (the walk it left, its trail): on a link onto a crossing over a reserved track, the
  // track ahead turned it back to the link's start, where only the walk it came from led on.
  _turnBack(w, here) {
    if (w.turnedAt !== undefined && w.walked - w.turnedAt < TURN_ROOM) { this._leave(w, here, 'turns'); return; }
    w.turnedAt = w.walked; w.dir = -w.dir; w.waitKerb = false;
    w.travel = null; w.prev = null; w.trail = null;
  }

  // a walker that leaves stands and sinks into the ground where it is, as one far off fades (cars see it until it is
  // half gone); counted per place and why in walkLeaves (window.traffic): 'turns' (_turnBack), 'stuck' (STILL_T)
  _leave(w, here, why) {
    w.leave = true; w.waitKerb = false;
    const k = `${why} ${Math.round(here.x)},${Math.round(here.y)}`;
    this.walkLeaves.set(k, (this.walkLeaves.get(k) || 0) + 1);
  }

  // --------------------------------------------------------------------- other trams
  _placeTram(t, route, s, profileZ, dt = 0) {
    placeConsist(t.mesh, s, (q) => { const p = route.at(q); return [p.x, p.y, profileZ(q, p), route.rollAt(q)]; });
    const u = t.mesh.userData;
    // the lamps (#436): the brake lamps while it slows or stands, the indicators at junction turns and stops where
    // passengers cross a car lane (blinking out of step with the others'); a T3M's side display its next stop
    const braking = t.v < 0.05 || t.v < (t.vWas ?? t.v) - 0.2 * dt;
    t.vWas = t.v;
    const way = this.lampWays[route === this.route ? 'ahead' : 'back'];
    const lamps = { braking, indicate: indicating(way.turns, way.kerb, s, t.v, braking), clock: this.game.clock + 0.17 * (t.id % 4) };
    if (u.kind === 'simple') {
      poseT3(t.mesh, lamps);
      if (u.variant === 'T3M') setNextStop(t.mesh, way.stops.find((st) => st.s > s - 2)?.name ?? null);
    }
    if (!u.rigged) return;
    // the detailed model: its full level near the camera; the doors open while it dwells at a stop (shut
    // 2 s before it leaves, 2 s to move); its lamps as above (posed on the full level only)
    const c = u.cars[0].position, d = this.cam ? Math.hypot(c.x - this.cam[0], -c.z - this.cam[1]) : 0;
    setRiggedLevel(t.mesh, d < (u.level === 'full' ? FULL_OUT : FULL_IN) ? 'full' : 'light');
    t.doorU = Math.max(0, Math.min(1, (t.doorU ?? 0) + ((t.dwell ?? 0) > 2 ? dt : -dt) / 2));
    if (u.level === 'full') poseT3(t.mesh, { doors: t.doorU, ...lamps });
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
    // (its type and fleet numbers dealt from the run's fleet, src/vehicles.js FleetDealer: none twice on the street)
    const mesh = makeT3({ line, cars, vehicle: this.game.opts.vehicle, run: `8${String(1 + ((this.tramCount * 17) % 40)).padStart(2, '0')}`,
      dealt: this.game.opts.dealer?.deal(cars) });
    setOpacity(mesh, 0);
    this.group.add(mesh);
    return { id: this.tramCount, mesh, length: T3.length * cars + COUPLING_GAP * (cars - 1) };
  }

  _tramGone(t) {
    this.game.opts.dealer?.give(t.mesh.userData.fleet);
    this.group.remove(t.mesh); disposeModel(t.mesh);
  }

  _tramFade(t, dt, leaving) {
    t.alpha = Math.max(0, Math.min(1, (t.alpha ?? 0) + (leaving ? -dt : dt) / FADE));
    setOpacity(t.mesh, t.alpha);
  }

  // The #154 recovery only sees a car immediately in front of our tram. At Balabenka (#168)
  // an oncoming tram -> car 307 -> 295 -> 297 -> that same tram locks up before we arrive.
  // Follow the actual stop reasons: a red light, dwell or a moving vehicle ends the chain.
  // As with #154, a car cannot back out in this model, so fade one only after a closed cycle
  // has stood for 30 s. Never let a car drive through the tram to break the tie.
  _clearAiTramCycles(dt) {
    for (const t of [...this.ahead, ...this.oncoming]) {
      const ring = [];
      let o = t;
      while (o && !ring.includes(o) && ring.length < this.cars.length + this.ahead.length + this.oncoming.length) {
        if ((o.kind === 'road' ? !o.active || (o.vNow ?? 0) >= 0.3 : o.v >= 0.3 || o.dwell > 0 || o.leaving)) break;
        ring.push(o); o = o.waitFor;
      }
      const car = o === t && ring.find((x) => x.kind === 'road');
      const key = car ? ring.map((x) => `${x.kind === 'road' ? 'car' : 'tram'}${x.id}`).join('>') : null;
      t.cycleT = key && key === t.cycleKey ? (t.cycleT || 0) + dt : 0;
      t.cycleKey = key;
      if (!car || t.cycleT <= 30) continue;
      car.active = false; t.cycleT = 0;
      this.cyclesBroken = (this.cyclesBroken || 0) + 1;
      const event = { clock: this.game.clock, car: car.id, cycle: key,
        reasons: ring.map((x) => x.kind === 'road' ? x.why : x.stop?.why) };
      this.game.trafficCycles ||= [];
      this.game.trafficCycles.push(event);
      if (this.game.trafficCycles.length > 20) this.game.trafficCycles.shift();
      console.debug('AI tram waiting cycle', event);
    }
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
      let vt = Math.max(0, limitSpeed(g.limits, t.s, t.length) - AI_UNDER);
      const close = t.s - t.length - tram.s < 300; // (our tram closing in)
      let stopAt = null;
      t.waitFor = null; t.stop = null;
      const stop = (s, why, who = null) => { if (s < (stopAt ?? Infinity)) { stopAt = s; t.stop = { s, why }; t.waitFor = who; } };
      const st = g.stops.find((x) => x.target > t.s + 0.5);
      if (st) stop(st.target, 'stop');
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
        // (too close to stop comfortably for a blinking GO, it goes on only if it is there while the GO lasts: the rest of the blinking
        // and what the controller can still hold for it. Slowing for a junction's 15 km/h past the signal, one took 12 s from 91 m out
        // at 44 km/h, past the 10 s hold, and ran the red 1.4 s late, line 17 seed 5; 11 s at line 22 s 4211, #394. Not there in
        // time and able to stop on full service braking, it stops)
        else if (sig.state === 'warn' && d > 0 && d > stopDistance(t.v, 'stop')) {
          const vSig = Math.min(limitSpeed(g.limits, sig.s, t.length) - AI_UNDER, stopAt !== null && stopAt > sig.s ? Math.sqrt(1.8 * Math.max(0, stopAt - 0.5 - sig.s)) : Infinity);
          if (timeTo(sig.s - t.s, t.v, Math.max(0, vSig)) + 1 > (sig.timer ?? 0) + (sig.aheadHoldLeft ?? 0)) t.redStops.add(sig);
        }
        if (t.redStops.has(sig)) stop(sig.s - 3, 'signal');
        else if (sig.state === 'warn' && d > -3) sig.aheadCommitted = true;
      }
      const other = this.ahead.find((o) => o !== t && o.s > t.s);
      // (2 m behind the tram ahead, D 1/2 § 27.6: at least 1 m; 6 m kept two 2-car sets off long platforms, #258)
      if (other) stop(other.s - other.length - 2, 'tram', other);
      const clear = other && g.keepClear(t.s, other.s - other.length);
      if (clear !== null && clear !== undefined) stop(clear, 'keep clear', other);
      // a car on the track ahead (along it, or crossing it: it gives way to our tram only)
      for (const c of g.carsOnTrack || []) if (c.s > t.s) stop(c.s - 2.5 - 4, 'car on track', c.car);
      for (const c of g.carsCrossing || []) if (c.s > t.s) stop(c.s - 6, 'crossing car', c.car);
      // (on its braking curve it brakes as hard as it takes to stop at the point, as _updateOncoming)
      let aStop = Infinity;
      if (close && t.dwell > 8) t.dwell = 6 + (t.dwell % 2); // (only boarding while we close in)
      if (t.dwell > 0) { t.stop = { s: t.s, why: 'dwell' }; t.waitFor = null; }
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
      t.a = a;
      t.v = Math.max(0, t.v + a * dt);
      t.s += t.v * dt;
      t.leaving = t.s - tram.s > 1000 || t.s > this.route.length - 20 || (t.endS !== null && t.s > t.endS);
      this._tramFade(t, dt, t.leaving);
      this._placeTram(t, this.route, t.s, (s) => profile.height(s), dt);
    }
    this.ahead = this.ahead.filter((t) => {
      if (t.leaving && t.alpha <= 0) { this._tramGone(t); return false; }
      return true;
    });
    g.aiTrams = this.ahead;
  }

  // What the other trams draw, for the voltage at our pantograph (src/electric.js), twice a second: a tram on either
  // track hangs on the same wire feed.
  _wireLoads(dt) {
    this._wireT = (this._wireT ?? 0) - dt;
    if (this._wireT > 0) return;
    this._wireT = 0.5;
    const out = [];
    for (const t of this.ahead) out.push({ s: t.s, i: aiLineCurrent(2, t.v, t.a ?? 0) });
    for (const t of this.oncoming) {
      const p = this.back.at(t.s), n = this.route.nearest(p.x, p.y);
      if (n) out.push({ s: n.s, i: aiLineCurrent(2, t.v, t.a ?? 0) });
    }
    this.game.otherTrams = out;
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
    if (!this.backLimits) this.backLimits = br.speedLimits([], this.game.opts.speedFacts.past);
    const ground = this.ground;
    const gauntlets = this.game.gauntlets || [];
    for (const G of gauntlets) G.theirs = { requested: false, occupied: false };
    for (const sig of this.game.signals) sig.backCommitted = false; // (set again below, read by the controller)
    for (const t of this.oncoming) {
      let vt = Math.max(0, limitSpeed(this.backLimits, t.s, t.length) - AI_UNDER);
      let stopAt = this.backStops.find((s) => s > t.s + 0.5 && !t.served.has(s)) ?? null;
      const isStop = stopAt !== null, platformAt = stopAt;
      t.waitFor = null; t.stop = stopAt === null ? null : { s: stopAt, why: 'stop' };
      const stop = (s, why, who = null) => { if (s < (stopAt ?? Infinity)) { stopAt = s; t.stop = { s, why }; t.waitFor = who; } };
      for (const c of this.carsOnBack || []) if (c.s > t.s) stop(c.s - 2.5 - 4, 'car on track', c.car);
      // keep a distance to the oncoming tram in front
      for (const o of this.oncoming) if (o !== t && o.s > t.s) stop(o.s - o.length - 2, 'tram', o);
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
        if (t.redStops.has(sig)) { if (d > -1) stop(line - 3, 'signal'); } // a little before the line
        // (not a tram that stops at its platform before the line anyway: the controller held the green up to 10 s for it, line 37
        // holds 1.6 → 4.6 a run once #385 put three platform points just before their lines. Behind a car it may still be committed:
        // the car can move on)
        else if (d > 0 && d < 150 && sig.backState === 'warn' && !(isStop && platformAt < line)) sig.backCommitted = true;
      }
      for (const G of gauntlets) {
        if (t.s > G.b0 && t.s - t.length < G.b1) G.theirs.occupied = true;
        if (t.s <= G.b0 && G.b0 - t.s < 150) {
          G.theirs.requested = true;
          const allowed = G.state === 'theirs' && !G.entered;
          if (!allowed) stop(G.b0 - 4, 'gauntlet');
        }
      }
      // (on its braking curve a tram brakes as hard as it takes to stop at the point, up to 1.3 m/s2:
      // following the curve's speed with a lag over-ran stop points by 3-4 m, onto red stop lines)
      let aStop = Infinity;
      if (t.dwell > 0) { t.stop = { s: t.s, why: 'dwell' }; t.waitFor = null; }
      if (t.dwell > 0) { t.dwell -= dt; vt = 0; }
      else if (stopAt !== null) {
        const d = stopAt - t.s;
        vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * 0.9 * Math.max(0, d - 0.5))));
        if (t.v > vt - 0.05 && t.v > 0.05) aStop = -(t.v * t.v) / (2 * Math.max(0.1, d - 0.5));
        if (d < 0.8 && t.v < 0.3 && isStop && this.backStops.includes(stopAt)) { t.served.add(stopAt); t.dwell = 10 + this.rand() * 10; }
      }
      const a = Math.max(-1.3, Math.min(1.0, (vt - t.v) * 0.8, aStop));
      t.a = a;
      t.v = Math.max(0, t.v + a * dt);
      t.s += t.v * dt;
      const p = br.at(t.s), me = this.route.at(tram.s);
      // past the last stop it shares with our line it turns off
      const ourS = t.endS !== null ? this.route.nearestOnHeading(p.x, p.y, -p.hx, -p.hy)?.s : null;
      t.leaving = (p.x - me.x) * me.hx + (p.y - me.y) * me.hy < -150 || t.s > br.length - 20 || (ourS != null && ourS < t.endS);
      this._tramFade(t, dt, t.leaving);
      this._placeTram(t, br, t.s, (s, q) => ground.trackAt(q.x, q.y), dt);
    }
    this.oncoming = this.oncoming.filter((t) => {
      if (t.leaving && t.alpha <= 0) { this._tramGone(t); return false; }
      return true;
    });
  }
}
