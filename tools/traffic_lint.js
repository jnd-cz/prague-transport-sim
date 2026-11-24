// SPDX-License-Identifier: AGPL-3.0-or-later
// Dev tool: watch what the player would see while the autopilot drives the whole line headless with the real traffic
// (a watcher on the u3 drive, tools/bench/u3.js, fixed time step; #722). Every `sample` seconds the pose of each
// visible car, walker, AI tram and our tram is recorded:
//   slide  - a car or walker moving sideways against its heading (wrong path, lane jump)
//   jump   - a visible car or walker that teleports between two samples
//   overlap- two vehicles intersecting (car/car, car/tram, tram/tram), once per episode
//   walker - a walker inside a vehicle
//   walkerStuck - a walker that keeps within STILL_R of one place for STILL_T while not waiting at a kerb or in a door,
//            once per episode: 'turning' (its way flips), 'loop' (its walks change), 'still' (neither) (#366, #269, #393)
// Used by tools/lint.js ({ traffic: true }); returns checks in the same shape.
import { CAR_PITCH } from '../src/tram.js';

const CAR = [4.3, 1.8], TRAM = [14.0, 2.5];
const TOP = 12;
// a walker walks 1.1-1.6 m/s: one that stays within 2 m of a place for 30 s without a reason is caught (#393's measure)
const STILL_R = 2, STILL_T = 30;
const AT_MAX = 2000; // every place as [x, y, s] up to this many (headless.py keeps them in the baseline, #157)
export const placesAt = (items) => (items.length <= AT_MAX ? { at: items.map((i) => [i.x == null ? null : Math.round(i.x), i.y == null ? null : Math.round(i.y), i.s == null ? null : Math.round(i.s)]) } : {});

// rectangle as centre, unit heading, half length / width -> its 4 corners
function corners(b) {
  const { x, y, hx, hy, l, w } = b, nx = -hy, ny = hx;
  return [[x + hx * l + nx * w, y + hy * l + ny * w], [x + hx * l - nx * w, y + hy * l - ny * w],
    [x - hx * l - nx * w, y - hy * l - ny * w], [x - hx * l + nx * w, y - hy * l + ny * w]];
}
// separating axis test for two rectangles; returns the penetration depth (> 0 = overlap)
function overlap(a, b) {
  if (Math.hypot(a.x - b.x, a.y - b.y) > a.l + a.w + b.l + b.w) return 0;
  const ca = corners(a), cb = corners(b);
  let depth = Infinity;
  for (const [ax, ay] of [[a.hx, a.hy], [-a.hy, a.hx], [b.hx, b.hy], [-b.hy, b.hx]]) {
    const pa = ca.map(([x, y]) => x * ax + y * ay), pb = cb.map(([x, y]) => x * ax + y * ay);
    const d = Math.min(Math.max(...pa), Math.max(...pb)) - Math.max(Math.min(...pa), Math.min(...pb));
    if (d <= 0) return 0;
    depth = Math.min(depth, d);
  }
  return depth;
}
const inBox = (b, x, y) => {
  const dx = x - b.x, dy = y - b.y;
  return Math.abs(dx * b.hx + dy * b.hy) < b.l && Math.abs(-dx * b.hy + dy * b.hx) < b.w;
};
// heading of an object whose rotation.y = atan2(hx, -hy) (cars, tram cars, walkers)
const head = (ry) => [Math.sin(ry), -Math.cos(ry)];

// everything visible now, as drawn (view: the traffic's models, src/trafficView.js): vehicles as rectangles, walkers as points
function snapshot(g, tr, view) {
  const out = { veh: [], walk: [] };
  for (const [i, c] of tr.cars.entries()) {
    const m = view.meshOf(c);
    if (c.alpha < 0.5 || !m) continue;
    const p = m.position, [hx, hy] = head(m.rotation.y);
    out.veh.push({ id: `car${i}`, kind: 'car', x: p.x, y: -p.z, z: p.y, hx, hy, l: CAR[0] / 2, w: CAR[1] / 2, src: c.kind, alpha: c.alpha,
      state: c.coast && !c.active ? 'coast' : c.conn ? 'junction' : 'lane', road: c.road, dir: c.dir });
  }
  for (const [list, kind] of [[tr.ahead, 'tram ahead'], [tr.oncoming, 'tram oncoming']]) {
    for (const t of list) {
      const set = view.meshOf(t);
      if ((t.alpha ?? 0) < 0.5 || !set) continue;
      set.userData.cars.forEach((m, k) => {
        const [hx, hy] = head(m.rotation.y);
        out.veh.push({ id: `${set.uuid}/${k}`, group: set.uuid, kind, x: m.position.x, y: -m.position.z, z: m.position.y, hx, hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
      });
    }
  }
  // our own set: car centres along the route behind the front
  const cars = g.tram.cars || 1;
  for (let k = 0; k < cars; k++) {
    const s = g.tram.s - 0.6 - 7.6 - k * CAR_PITCH, p = g.route.at(s), h = g.route.heading(s, 3);
    out.veh.push({ id: `us/${k}`, group: 'us', kind: 'our tram', x: p.x, y: p.y, z: g.route.ground.profile.height(s), hx: h.hx, hy: h.hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
  }
  const M = new view.crowd.matrix.constructor();
  for (const [i, w] of (tr.slots || []).entries()) {
    if (!w || w.alpha < 0.5) continue;
    view.crowd.getMatrixAt(i, M);
    const e = M.elements;
    out.walk.push({ id: `w${i}`, x: e[12], y: -e[14], z: e[13], hx: e[8], hy: -e[10], walk: w }); // w: the slot's walker (new object on respawn)
  }
  return out;
}

// The traffic check as a watcher on a whole-line drive (tools/bench/u3.js run, opts.also; #722, the user's "agree" on
// #708): it rides on the one drive of a line and seed that u3, redruns and stops share, so the tier drives each line
// and seed once. It only reads. Every `sample` s of game time it records what the player would see (snapshot).
// (view: the run's traffic as drawn, src/trafficView.js)
export function trafficWatch(g, tr, { sample = 0.2, dt = 1 / 30, view = window.run?.trafficView } = {}) {
  const slides = [], jumps = [], overlaps = [], hits = [], knobs = [], redRuns = [], stuckWalkers = [];
  const still = new Map(); // walker -> { x, y, t: since when within STILL_R of (x, y), flips, walks, dir, walk, rec }
  const lastS = new Map(); // oncoming tram -> its position at the previous step
  let heat = null; // last heating setting: saloon / cab / flap, to count the autopilot's knob changes
  const prev = new Map(), open = new Map(); // id -> last sample; pair -> open overlap episode
  let T = 0, nextSample = 0, samples = 0, seenVeh = 0, seenWalk = 0;
  const step = sample;
  return { before: () => null, after() {
      T += dt;
      // oncoming trams crossing a junction's stop line on red (B10: they share the straight phase)
      for (const t of tr.oncoming) {
        const s0 = lastS.get(t);
        if (s0 !== undefined) for (const sig of g.signals) {
          if (sig.backCross === undefined) continue;
          const line = sig.backCross - 6, d = line - t.s;
          // a tram counts only if, while the light was red, it was still far enough to stop (0.9 m/s2
          // and 2 s reaction): one that could no longer stop when it changed passes on amber
          t.couldStop = t.couldStop || new Set();
          if (sig.backState === 'go') t.couldStop.delete(sig);
          else if (d > (t.v * t.v) / 1.8 + t.v * 2 + 1) t.couldStop.add(sig);
          if (s0 < line && t.s >= line && sig.backState !== 'go' && t.couldStop.has(sig)) { const p = tr.back.at(t.s); redRuns.push({ kind: 'oncoming tram', x: p.x, y: p.y, mag: t.v, s: Math.round(sig.cross), info: `oncoming tram through red at ${(t.v * 3.6).toFixed(0)} km/h` }); }
        }
        lastS.set(t, t.s);
      }
      const c = g.climate, h = c && `${c.saloon}/${c.cab}/${c.flap}`;
      if (heat !== null && h !== heat) { const p = g.route.at(g.tram.s); knobs.push({ kind: 'heating', x: p.x, y: p.y, mag: 1, s: Math.round(g.tram.s), info: `${heat} → ${h} at ${Math.round(T)} s` }); }
      heat = h;
      window.trafficWatch?.(g, tr, T); // (a dev probe of one moment: the cars around a stuck scene)
      if (T < nextSample) return;
      nextSample = T + step;
      samples++;
      const snap = snapshot(g, tr, view);
      seenVeh += snap.veh.length; seenWalk += snap.walk.length;
      const now = new Map();
      // slide / jump: motion between two samples of the same visible object
      for (const o of [...snap.veh.filter((v) => v.kind === 'car'), ...snap.walk]) {
        now.set(o.id, o);
        const q = prev.get(o.id);
        if (!q || (o.walk && q.walk !== o.walk) || (q.src && q.src !== o.src)) continue; // respawned in the slot
        const dx = o.x - q.x, dy = o.y - q.y, d = Math.hypot(dx, dy);
        const isCar = !o.walk, vmax = isCar ? 20 : 3;
        // what changed between the samples (for cars: the state and the road) tells the cause
        const why = isCar ? (q.state !== o.state ? `${q.state}→${o.state}` : q.road !== o.road ? 'next road' : o.state === 'junction' ? 'junction' : 'same lane') : 'walk';
        if (d > vmax * step + 1) { jumps.push({ kind: isCar ? `car ${why}` : 'walker', x: o.x, y: o.y, mag: d, s: Math.round(g.tram.s), info: `${d.toFixed(1)} m in ${step} s (${why})` }); continue; }
        const hx = (o.hx + q.hx) / 2, hy = (o.hy + q.hy) / 2, hl = Math.hypot(hx, hy) || 1;
        const side = Math.abs((-dx * hy + dy * hx) / hl) / step; // m/s across the heading
        if (side > (isCar ? 0.8 : 0.6)) slides.push({ kind: isCar ? `car ${why}` : 'walker', x: o.x, y: o.y, mag: side, s: Math.round(g.tram.s), info: `${side.toFixed(1)} m/s sideways at ${(d / step).toFixed(1)} m/s` });
      }
      prev.clear();
      for (const [k, v] of now) prev.set(k, v);
      // overlaps between vehicles, one record per episode (the deepest moment)
      const V = snap.veh, live = new Set();
      for (let i = 0; i < V.length; i++) for (let j = i + 1; j < V.length; j++) {
        const a = V[i], b = V[j];
        if (a.group && a.group === b.group) continue; // cars of one set
        if (Math.abs(a.z - b.z) > 2.5) continue; // different levels: a bridge and the road under it
        const depth = overlap(a, b);
        if (depth <= 0.05) continue;
        const key = a.id < b.id ? `${a.id}|${b.id}` : `${b.id}|${a.id}`;
        live.add(key);
        const kinds = [a.kind, b.kind].sort().join(' / ');
        const ep = open.get(key);
        if (ep) { if (depth > ep.mag) Object.assign(ep, { mag: depth, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }); continue; }
        const states = [a.state || a.kind, b.state || b.kind].sort().join(' + ');
        const rec = { kind: kinds, states, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, mag: depth, s: Math.round(g.tram.s), info: `${kinds} (${states}), ${depth.toFixed(1)} m deep` };
        open.set(key, rec);
        overlaps.push(rec);
      }
      // walkers inside a vehicle, once per episode (a walker and a vehicle that stay together count once)
      for (const w of snap.walk) for (const v of V) if (Math.abs(v.z - w.z) < 2.5 && inBox(v, w.x, w.y)) {
        const key = `${w.id}|${v.id}`;
        live.add(key);
        if (!open.has(key)) {
          const rec = { kind: v.kind, x: w.x, y: w.y, mag: 1, s: Math.round(g.tram.s), info: `walker inside ${v.kind}` };
          open.set(key, rec);
          hits.push(rec);
        }
        break;
      }
      // walkers that stay in one place without a reason: a kerb wait or a door starts the watch again
      const seen = new Set();
      for (const o of snap.walk) {
        const w = o.walk;
        seen.add(w);
        let a = still.get(w);
        if (!a || w.waitKerb || w.door || Math.hypot(o.x - a.x, o.y - a.y) > STILL_R) {
          still.set(w, { x: o.x, y: o.y, t: T, flips: 0, walks: 0, dir: w.dir, walk: w.walk, rec: null });
          continue;
        }
        if (w.dir !== a.dir) a.flips++;
        if (w.walk !== a.walk) a.walks++;
        a.dir = w.dir; a.walk = w.walk;
        const long = T - a.t;
        if (long < STILL_T) continue;
        if (a.rec) { a.rec.mag = long; continue; }
        const kind = a.walks > 2 ? 'loop' : a.flips > 2 ? 'turning' : 'still';
        a.rec = { kind, x: o.x, y: o.y, mag: long, s: Math.round(g.tram.s), info: `walker ${kind} within ${STILL_R} m for ${STILL_T} s (${a.flips} turns, ${a.walks} walks)` };
        stuckWalkers.push(a.rec);
      }
      for (const w of [...still.keys()]) if (!seen.has(w)) still.delete(w);
      for (const k of [...open.keys()]) if (!live.has(k)) open.delete(k);
    },
    // stuck: where the drive's stuck watch stopped it (null: it got through), scene: what held the tram then
    result(seed, stuck, scene) {
      const pick = (rule, items, of) => {
        const byKind = {};
        for (const it of items) byKind[it.kind] = (byKind[it.kind] || 0) + 1;
        const byState = {};
        for (const it of items) if (it.states) byState[it.states] = (byState[it.states] || 0) + 1;
        return { rule, count: items.length, of, kinds: byKind, ...(Object.keys(byState).length ? { states: byState } : {}), places: [...items].sort((a, b) => b.mag - a.mag).slice(0, TOP), ...placesAt(items) };
      };
      const minutes = T / 60;
      // the walkers that had nowhere to go and left (src/traffic.js _leave, #366): how many, and the places most left at
      const leaves = [...(tr.walkLeaves || new Map())].sort((a, b) => b[1] - a[1]);
      return {
        stats: { simSeconds: Math.round(T), samples, finished: stuck === null, nextStop: g.nextStop, cyclesBroken: tr.cyclesBroken || 0, junctionCircles: tr.junctionCircles || 0, recoveredCycles: g.trafficCycles || [], carsVisible: +(seenVeh / Math.max(1, samples)).toFixed(1), walkersVisible: +(seenWalk / Math.max(1, samples)).toFixed(1),
          walkersLeft: leaves.reduce((n, [, c]) => n + c, 0), walkLeaves: Object.fromEntries(leaves.slice(0, TOP)),
          // (a run that did not get through: what held the tram at the end, as u3 and redruns report it)
          ...(stuck === null ? {} : { stuck, stuckScene: scene }) },
        checks: {
          slide: pick('traffic-no-sideways-motion', slides, samples),
          jump: pick('traffic-no-teleport', jumps, samples),
          overlap: pick('traffic-no-overlap', overlaps, Math.round(minutes)),
          walkerHit: pick('traffic-walkers-clear-of-vehicles', hits, Math.round(minutes)),
          walkerStuck: pick('traffic-walkers-keep-walking', stuckWalkers, Math.round(minutes)),
          heatingKnobs: pick('autopilot-calm-heating', knobs, Math.round(minutes)),
          redRuns: pick('trams-obey-junction-signals', redRuns, Math.round(minutes)),
        },
      };
    },
  };
}

// The traffic check alone: the u3 drive (trip 40, obstacles normal, autumn, dry) with this watcher only, so its counts
// are those it reports riding on the shared drive. Before #722 it drove its own run: trip 0, no obstacles.
// stopAt: end the drive when our tram reaches this route s (a replay of the moment, ?seed=N&at=S in src/main.js; it
// watches nothing then); progress: called once per chunk of steps with a line to show.
export async function trafficRun({ seed = 22, stopAt = Infinity, progress = () => {} } = {}) {
  const { run } = await import('./bench/u3.js');
  try {
    const r = await run(seed, { also: stopAt === Infinity ? [trafficWatch] : [], stopAt, progress });
    return r.also[0] ?? r;
  } finally { window.headless = false; delete window.runSeed; }
}
