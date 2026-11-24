// SPDX-License-Identifier: AGPL-3.0-or-later
// Traffic scenes (#566): small street networks built in code and driven on the traffic core (src/traffic.js) without the
// world: no line data, no ground, no meshes. A scene is roads (each a polyline, two-way or one-way), footway pieces with
// their links, our track and tram if it needs them, and the cars and walkers it places itself. It runs at the game's
// fixed step (1/30 s, src/main.js STEP) and reports what tools/test_traffic_scenes.py asserts.
//
// The network goes to Traffic in the build's own format (tools/network.py, data/lineN.network.json: points in mm,
// lengths in cm): a lane per direction 1.75 m right of a two-way road's line (on the line of a one-way road), trimmed
// back from both ends as the build trims them (5 m, or a fifth of a short road), every 2 m. Roads meet where their ends
// round to the same metre. The game is a stub with no stops and no opposite track, so no AI tram comes; the traffic's
// spawn index is emptied, so the only cars and walkers are the scene's. A car's type and size come from its id
// (Traffic._identify, src/carTypes.js, #250), as in the game. Ideas from openOMSI's traffic tests (AGPL-3.0-only),
// written anew.
import { Traffic, boxesApart, tramBoxes, MAX_WALKERS } from '../../src/traffic.js';
import { Route } from '../../src/route.js';
import { T3 } from '../../src/tram.js';
import { rng } from '../../src/random.js';

export const STEP = 1 / 30;

const key = ([x, y]) => `${Math.round(x)},${Math.round(y)}`;
const mm = (pts) => pts.flatMap(([x, y]) => [Math.round(x * 1000), Math.round(y * 1000)]);

// a polyline's points every `step` m (a Route for its arc length)
function dense(pts, step = 1) {
  const R = new Route(pts), out = [];
  const n = Math.max(1, Math.ceil(R.length / step));
  for (let i = 0; i <= n; i++) { const p = R.at((R.length * i) / n); out.push([p.x, p.y]); }
  return out;
}

// the network of a scene: roads [{ p, o, off }], walks [{ p, link, links: [[[k, s]...], [[k, s]...]] }] (s in m)
function network(roads, walks) {
  const N = { roads: [], lanes: [], walks: [], doors: [], lights: [], lightSigs: [], heads: [], pedCross: [], pedHeads: [] };
  roads.forEach((r, i) => {
    const o = r.o ? 1 : 0, off = r.off ?? (o ? 0 : 1.75), R = new Route(r.p), L = R.length;
    N.roads.push({ p: mm(dense(r.p, 2)), w: o ? 3.5 : 7, o, tram: 0, b: 0, t: 0, ln: o ? 1 : 2, ends: [key(r.p[0]), key(r.p[r.p.length - 1])], way: i });
    const trim = Math.min(5, L * 0.2);
    for (const d of o ? [1] : [1, -1]) {
      const pts = [], n = Math.max(2, Math.ceil((L - 2 * trim) / 2));
      for (let j = 0; j <= n; j++) {
        const u = trim + ((L - 2 * trim) * j) / n, p = R.at(d > 0 ? u : L - u), hx = p.hx * d, hy = p.hy * d;
        pts.push([p.x + hy * off, p.y - hx * off]);
      }
      N.lanes.push({ road: i, dir: d, sel: 0, p: mm(pts) });
    }
  });
  for (const w of walks) {
    N.walks.push({ p: mm(dense(w.p, 0.5)), link: !!w.link, links: (w.links || [[], []]).map((e) => e.map(([k, s]) => [k, Math.round(s * 100)])) });
  }
  return N;
}

// A scene's traffic: { roads, walks, track (our tram's polyline), back (the opposite track's, its trams' way), tram: { s,
// v }, seed }. Returns the Traffic; its game stub is T.game (T.game.hits: the collisions the rules report).
export function build({ roads = [], walks = [], track = null, back = null, tram = null, seed = 1 } = {}) {
  const N = network(roads, walks);
  const route = new Route(dense(track || [[-500, 9000], [500, 9000]], 1));
  const hits = [];
  const game = {
    tram: { s: tram?.s ?? 0, v: tram?.v ?? 0, cars: 1, length: T3.length },
    backRoute: back ? new Route(dense(back, 1)) : null, platforms: [], stops: [], signals: [], segments: [], gauntlets: [], limits: [],
    data: { line: 'scene', stops: [], switches: [] }, opts: { speedFacts: { past: [] } }, clock: 0, nextStop: 0, hits,
    _collision(what) { hits.push({ clock: this.clock, what }); },
  };
  const ground = { surface: () => 0, way: () => () => 0, profile: { height: () => 0, overBridge: () => false } };
  const T = new Traffic({ line: 'scene', network: N, roads: N.roads, stops: [] }, route, ground, game, rng(seed));
  T.index = new Map(); // (no spawning: the scene's cars and walkers only)
  T.spawnTimer = Infinity;
  T.backLimits = []; // (no tram comes on the opposite track: its speed limits, from the line's data, are not needed)
  T.slots = new Array(MAX_WALKERS).fill(null);
  return T;
}

// the lane of road k going `dir` (+1 along its points)
export const laneOf = (T, k, dir = 1) => T.laneList.find((l) => l.k === k && l.dir === dir);

// a car on road k's lane `dir`, s m along it, wanting v m/s (moving at vNow, else as the game spawns: at v); `next`: the
// road it takes at the junction ahead (else the traffic chooses); `id`: its identity (type, size, boldness)
export function addCar(T, { road, dir = 1, s, v = 10, vNow = null, next = null, id }) {
  const lane = laneOf(T, road, dir);
  const c = { model: 0, active: true, alpha: 1, kind: 'road', lane, road: lane.road, dir: lane.dir, conn: null, next: undefined, next2: undefined,
    next2From: null, lightGo: null, lightHold: null, lead: null, path: lane.path, s, v, vNow, coast: null, hitTram: false, cycleT: 0,
    z: undefined, seen: null, why: null };
  if (next !== null) c.next = T.nextLanes(lane).find((b) => b.k === next) || null;
  T._identify(c, id);
  T.nextCarId = Math.max(T.nextCarId || 0, c.id);
  T.cars.push(c);
  return c;
}

// a walker on walk k, s m along it, going dir at v m/s (on the walk's line)
export function addWalker(T, { walk, s, dir = 1, v = 1.3 }) {
  const i = T.slots.indexOf(null);
  const w = { walk: T.walks[walk], s, dir, v, side: 0, alpha: 1, goal: 1e9, walked: 0 };
  T.slots[i] = w;
  return w;
}

// Our tram as a stand-in driver drives it: up to vMax, braking (1.3 m/s2, at most 3) to stand 4 m behind a car on the
// track or on a crossing of it, and only for those
function driveTram(T, dt, vMax) {
  const g = T.game, tram = g.tram;
  const ahead = [...(g.carsOnTrack || []), ...(g.carsCrossing || []).filter((x) => x.onTrack)].filter((o) => o.s > tram.s - 1).map((o) => o.s - tram.s);
  const gap = ahead.length ? Math.min(...ahead) : Infinity;
  const vt = Math.min(vMax, Math.sqrt(2 * 1.3 * Math.max(0, gap - 4)));
  tram.v = vt > tram.v ? Math.min(vt, tram.v + 1 * dt) : Math.max(vt, tram.v - 3 * dt);
  tram.s += tram.v * dt;
}

// the cars' boxes overlapping each other or our tram's body, the deepest of each pair: [{ a, b, depth, clock }]
function overlaps(T) {
  const g = T.game, out = [];
  const boxes = T.cars.filter((c) => c.active && c.alpha > 0.5 && c.path).map((c) => {
    const p = c.path.at(c.s);
    return { x: p.x, y: p.y, hx: p.hx, hy: p.hy, l: c.half, w: c.halfW, who: `car${c.id}` };
  });
  for (const b of tramBoxes(g.tram.s, 1, (q) => { const p = T.route.at(q); return [p.x, p.y, 0, 0]; })) boxes.push({ x: b.x, y: b.y, hx: b.hx, hy: b.hy, l: 7.0, w: 1.25, who: 'tram' });
  for (const w of T.slots || []) if (w && w.alpha > 0.5 && w.x !== undefined) boxes.push({ x: w.x, y: w.y, hx: 1, hy: 0, l: 0.25, w: 0.25, who: 'walker' });
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      if (boxes[i].who === 'walker' && boxes[j].who === 'walker') continue; // (walkers pass through each other)
      const d = boxesApart(boxes[i], boxes[j]);
      if (d < -0.05) out.push({ a: boxes[i].who, b: boxes[j].who, depth: Math.round(-d * 100) / 100, clock: Math.round(g.clock * 10) / 10 });
    }
  }
  return out;
}

// Run a scene for `t` s at STEP: `tram` the tram's top speed (it stands without), `each(T, clock)` after every step.
// Returns { clock, hits, overlaps (the deepest per pair), cars: each car's end state, trace (every `traceEvery` s) }
export function run(T, { t = 60, tram = null, each = null, focus = [0, 0], traceEvery = 0 } = {}) {
  const g = T.game, worst = new Map(), trace = [];
  const n = Math.round(t / STEP);
  for (let k = 0; k < n; k++) {
    g.clock += STEP;
    if (tram !== null) driveTram(T, STEP, tram);
    T.update(STEP, focus);
    for (const o of overlaps(T)) { const kk = `${o.a}|${o.b}`; if (!worst.has(kk) || worst.get(kk).depth < o.depth) worst.set(kk, o); }
    if (each) each(T, g.clock);
    if (traceEvery && k % Math.round(traceEvery / STEP) === 0) trace.push(state(T));
  }
  return { clock: Math.round(g.clock * 10) / 10, hits: g.hits, overlaps: [...worst.values()], cars: state(T).cars, trace,
    walkLoops: [...T.walkLoops.entries()], walkLeaves: [...T.walkLeaves.entries()],
    // (the waits-for graph, #560: heads of chains standing a minute or more by kind, circles by class)
    heads: T.longChainCount || {}, circles: T.waitCircleCount || {}, longChains: T.longChains || [] };
}

// every car and walker, rounded: what the order test compares and the scenes report
export function state(T) {
  const r = (v) => (v === null || v === undefined ? v : Math.round(v * 1000) / 1000);
  return {
    clock: r(T.game.clock),
    tram: { s: r(T.game.tram.s), v: r(T.game.tram.v) },
    cars: T.cars.filter((c) => c.kind === 'road').map((c) => ({ id: c.id, type: c.type?.id, active: c.active, road: c.lane?.k, dir: c.lane?.dir,
      conn: !!c.conn, s: r(c.s), v: r(c.vNow), why: c.why, waitFor: c.waitFor ? (c.waitFor.kind === 'road' ? `car${c.waitFor.id}` : 'tram') : null,
      yielding: !!c.yielding })).sort((a, b) => a.id - b.id),
    walkers: (T.slots || []).filter(Boolean).map((w) => ({ x: r(w.x), y: r(w.y), s: r(w.s), leave: !!w.leave })),
  };
}

// ---------------------------------------------------------------------------------------------------------- the scenes
// Each returns { T, t, tram, each, report }: play(name, args) runs it and adds report() to run()'s result.
const r1 = (v) => Math.round(v * 10) / 10;
const cross = () => [{ p: [[-60, 0], [0, 0]] }, { p: [[0, 0], [60, 0]] }, { p: [[0, -60], [0, 0]] }, { p: [[0, 0], [0, 60]] }];
const seg = (a, b, links, link = false) => ({ p: [a, b], links, link });
const len = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

// cars one behind another on road k's lane `dir`, the first's middle at s, 1.5 m between them: [{ id, v, vNow }]
function queue(T, road, dir, s, cars, next = null) {
  const out = [];
  let prev = null;
  for (const q of cars) {
    const c = addCar(T, { road, dir, s, next, v: q.v ?? 10, vNow: q.vNow ?? 0, id: q.id });
    if (prev) c.s = prev.s - prev.half - 1.5 - c.half;
    out.push(c);
    prev = c;
  }
  return out;
}

// when each car first stands on its goal road (off a junction's connector): { id: clock }
function arrivals(goal) {
  const at = {};
  return { at, each: (T, clock) => { for (const c of T.cars) if (at[c.id] === undefined && c.active && !c.conn && c.lane.k === goal.get(c.id)) at[c.id] = r1(clock); } };
}

export const SCENES = {
  // A junction with no signs and no priorities, two cars on each of its four approaches, each going straight on: all
  // eight get through, nobody overlaps (openOMSI: four_cars_at_a_junction_without_priorities_all_get_through). `reversed`:
  // the same cars with the traffic's list the other way round (the order test).
  junction({ reversed = false } = {}) {
    const T = build({ roads: cross() });
    const spec = [
      { road: 0, dir: 1, s: 30, next: 1, id: 1 }, { road: 0, dir: 1, s: 20, next: 1, id: 5 },
      { road: 1, dir: -1, s: 30, next: 0, id: 2 }, { road: 1, dir: -1, s: 21, next: 0, id: 6 },
      { road: 2, dir: 1, s: 31, next: 3, id: 3 }, { road: 2, dir: 1, s: 22, next: 3, id: 7 },
      { road: 3, dir: -1, s: 30.5, next: 2, id: 4 }, { road: 3, dir: -1, s: 19, next: 2, id: 8 },
    ];
    for (const c of spec) addCar(T, c);
    if (reversed) T.cars.reverse();
    const A = arrivals(new Map(spec.map((c) => [c.id, c.next])));
    return { T, t: 40, each: A.each, report: () => ({ through: A.at }) };
  },

  // A queue standing beyond a junction: a car coming to it stays before the junction while the exit lacks its length
  // (it never stops inside it), a car crossing the junction goes by meanwhile, and all go once the queue moves at 20 s
  // (openOMSI: a_car_does_not_drive_into_a_junction_it_cannot_leave)
  queueBeyond() {
    const T = build({ roads: cross() });
    const q = queue(T, 1, 1, 17, [{ id: 10, v: 0 }, { id: 11 }, { id: 12 }]);
    const car = addCar(T, { road: 0, dir: 1, s: 15, next: 1, id: 1 });
    addCar(T, { road: 2, dir: 1, s: 15, next: 3, id: 2 });
    const A = arrivals(new Map([[1, 1], [2, 3]]));
    let entered = null;
    return { T, t: 45, each: (T, clock) => {
      A.each(T, clock);
      if (car.conn && entered === null) entered = r1(clock);
      if (clock >= 20) q[0].v = 10;
    }, report: () => ({ through: A.at, entered }) };
  },

  // A side road's car turning left into a two-way main road whose both lanes carry a car every 2 s at 10 m/s: it gets in,
  // nobody overlaps (openOMSI: a_side_road_car_gets_into_a_main_road_that_never_leaves_a_gap)
  sideRoad() {
    const T = build({ roads: [{ p: [[-120, 0], [0, 0]] }, { p: [[0, 0], [120, 0]] }, { p: [[0, -60], [0, 0]] }] });
    const car = addCar(T, { road: 2, dir: 1, s: 35, next: 0, id: 1 });
    let id = 100, last = -Infinity, at = null;
    const feed = (road, dir, next) => {
      const lane = laneOf(T, road, dir);
      if (!T.cars.some((c) => c.active && c.path === lane.path && c.s < 14)) addCar(T, { road, dir, s: 2, vNow: 10, next, id: id++ });
    };
    return { T, t: 60, each: (T, clock) => {
      if (clock - last >= 2) { last = clock; feed(0, 1, 1); feed(1, -1, 0); }
      if (at === null && car.active && !car.conn && car.lane.k === 0) at = r1(clock);
    }, report: () => ({ in: at, fed: id - 100 }) };
  },

  // A walker crossing the road, already in the car's lane (at 1 m/s) as the car comes: the car stops short of it and
  // goes once it is across (openOMSI: somebody_on_the_crossing_holds_the_car). (One still on the kerb, or between the
  // lanes, waits for a car coming: B9.)
  walkerInLane() {
    const T = build({ roads: [{ p: [[-80, 0], [80, 0]] }], walks: [seg([0, 12], [0, -12])] });
    const car = addCar(T, { road: 0, dir: 1, s: 55, vNow: 10, id: 1 });
    addWalker(T, { walk: 0, s: 12.8, dir: 1, v: 1.0 });
    let stood = null, past = null;
    return { T, t: 30, each: (T, clock) => {
      if (stood === null && (car.vNow ?? 10) < 0.3) stood = { clock: r1(clock), seen: car.seen?.what ?? null, gap: car.seen ? r1(car.seen.gap) : null };
      if (past === null && car.path.at(car.s).x > 5) past = r1(clock);
    }, report: () => ({ stood, past }) };
  },

  // Our tram behind two cars on its rails, a one-way street along the track with a junction ahead: the first waits there,
  // its exit full (a queue standing on the rails beyond until 25 s), the second behind it; a car crosses the junction
  // and the track meanwhile; the tram stops behind them, and all go on (no collision, the tram past the junction)
  carOnTrackBehindWaiting() {
    const T = build({ roads: [{ p: [[-150, 0], [0, 0]], o: 1 }, { p: [[0, 0], [150, 0]], o: 1 }, { p: [[0, 60], [0, 0]] }, { p: [[0, 0], [0, -60]] }],
      track: [[-150, 0], [150, 0]], tram: { s: 0, v: 8 } });
    const exit = queue(T, 1, 1, 15, [{ id: 10, v: 0 }, { id: 11 }]);
    addCar(T, { road: 2, dir: 1, s: 40, vNow: 8, next: 3, id: 1 });
    queue(T, 0, 1, 125, [{ id: 2, vNow: 6 }, { id: 3, vNow: 6 }], 1);
    let stood = null, past = null;
    return { T, t: 70, tram: 8, each: (T, clock) => {
      const tr = T.game.tram;
      if (clock >= 25) exit[0].v = 10;
      if (stood === null && tr.v < 0.1) stood = { clock: r1(clock), s: r1(tr.s) };
      if (past === null && tr.s - tr.length > 150) past = r1(clock);
    }, report: () => ({ stood, past }) };
  },

  // A car on a street along the track turning left across it as our tram comes at 10 m/s: it waits before the track
  // until the tram has passed, and the tram never has to brake
  turnAcrossTrack() {
    const T = build({ roads: [{ p: [[200, 8], [60, 8]], o: 1 }, { p: [[60, 8], [60, -60]], o: 1 }],
      track: [[-100, 0], [300, 0]], tram: { s: 60, v: 10 } });
    const car = addCar(T, { road: 0, dir: 1, s: 50, vNow: 8, next: 1, id: 1 });
    let yielded = false, vMin = 10, crossedAt = null, tailPast = null;
    return { T, t: 25, tram: 10, each: (T, clock) => {
      const tr = T.game.tram;
      if (car.yielding) yielded = true;
      vMin = Math.min(vMin, tr.v);
      const p = car.active && car.path.at(car.s);
      if (crossedAt === null && p && car.lane.k === 1 && p.y + car.half < -1.5) crossedAt = r1(clock); // (its rear off the far rail)
      if (tailPast === null && tr.s - tr.length > 160 + 2.5) tailPast = r1(clock); // (route s 160: x 60)
    }, report: () => ({ yielded, tramVMin: r1(vMin), crossedAt, tailPast }) };
  },

  // #496 (line 23 s 3349, seed 1): walk A's end links 1 m back to a link crossing a car lane to walk B, 1 m before B's
  // end; B's end links through a second link to A, 1 m before A's end. At each end the least bad way on leads round that
  // 8 m ring, and walkers on it held a car for good. The walkers now turn back off a walk they entered less than 15 m ago
  // (#608); `fixOff` clears their record of the walks they entered every step, as before #608.
  walkerRing({ fixOff = false } = {}) {
    const a0 = [-20, 0], aE = [0, 0], p1 = [-1, 0], b0 = [-20, -3], bE = [1.5, -3], q1 = [0.5, -3], l2e = [0.75, 0];
    const lenA = len(a0, aE), lenB = len(b0, bE);
    const walks = [
      seg(a0, aE, [[], [[2, 0]]]), // A, its end -> L1
      seg(b0, bE, [[], [[3, 0]]]), // B, its end -> L2
      seg(p1, q1, [[[0, lenA - 1]], [[1, lenB - 1]]], true), // L1: from A 1 m before its end to B 1 m before its end
      seg(bE, l2e, [[[1, lenB]], [[0, lenA - 1]]], true), // L2: from B's end back to A 1 m before its end
    ];
    const T = build({ roads: [{ p: [[-60, 0], [60, 0]] }], walks });
    for (const [walk, s, dir] of [[2, 0.5, 1], [2, 2.2, 1], [3, 0.6, 1], [3, 2.0, 1], [0, lenA - 0.6, 1], [1, lenB - 0.5, 1]]) addWalker(T, { walk, s, dir, v: 1.3 });
    const car = addCar(T, { road: 0, dir: 1, s: 30, vNow: 8, id: 1 });
    let past = null;
    return { T, t: 60, each: (T, clock) => {
      if (fixOff) for (const w of T.slots) if (w) w.trail = null;
      if (past === null && car.path.at(car.s).x > 3) past = r1(clock);
    }, report: () => ({ past }) };
  },

  // #393 (line 22 s 7656, seed 4): four short pieces of footway, each under the metre a walker counts as an end, make a
  // square in a car lane; at each end the only way on but back is the next piece, so a walker steps round it on the spot.
  // Now one turning back twice within 3 m, or held within 2 m of one place for 10 s, leaves (#393, #366); `fixOff` clears
  // what those rules count every step.
  walkerSpot({ fixOff = false } = {}) {
    const c = [[-0.35, -1.4], [0.35, -1.4], [0.35, -2.1], [-0.35, -2.1]];
    const L = 0.7;
    const walks = c.map((a, i) => seg(a, c[(i + 1) % 4], [[[(i + 3) % 4, L]], [[(i + 1) % 4, 0]]]));
    const T = build({ roads: [{ p: [[-60, 0], [60, 0]] }], walks });
    for (let i = 0; i < 4; i++) addWalker(T, { walk: i, s: 0.2, dir: 1, v: 1.3 });
    const car = addCar(T, { road: 0, dir: 1, s: 30, vNow: 8, id: 1 });
    let past = null;
    return { T, t: 40, each: (T, clock) => {
      if (fixOff) for (const w of T.slots) if (w) { w.trail = null; w.still = null; w.turnedAt = undefined; }
      if (past === null && car.path.at(car.s).x > 3) past = r1(clock);
    }, report: () => ({ past }) };
  },
};

// run scene `name` (with its args; args.t: for so many seconds instead of the scene's own): run()'s result and the
// scene's own report
export function play(name, args = {}) {
  const sc = SCENES[name](args);
  const r = run(sc.T, { t: args.t ?? sc.t, tram: sc.tram ?? null, each: sc.each });
  return { ...r, ...sc.report() };
}
