// Dev tool: run the real game and traffic headless along the line (the autopilot drives, fixed
// time step, the camera follows the tram as in play) and watch what the player would see. Every
// `sample` seconds the pose of each visible car, walker, AI tram and our tram is recorded:
//   slide  - a car or walker moving sideways against its heading (wrong path, lane jump)
//   jump   - a visible car or walker that teleports between two samples
//   overlap- two vehicles intersecting (car/car, car/tram, tram/tram), once per episode
//   walker - a walker inside a vehicle
// Used by tools/lint.js ({ traffic: true }); returns checks in the same shape.
import { Autopilot } from '../src/autopilot.js';
import { stuckScene } from './bench/stuck.js';

const CAR = [4.3, 1.8], TRAM = [14.0, 2.5];
const TOP = 12;
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

// everything visible now: vehicles as rectangles, walkers as points
function snapshot(g, tr) {
  const out = { veh: [], walk: [] };
  for (const [i, c] of tr.cars.entries()) {
    if (c.alpha < 0.5) continue;
    const p = c.mesh.position, [hx, hy] = head(c.mesh.rotation.y);
    out.veh.push({ id: `car${i}`, kind: 'car', x: p.x, y: -p.z, z: p.y, hx, hy, l: CAR[0] / 2, w: CAR[1] / 2, src: c.kind, alpha: c.alpha,
      state: c.coast && !c.active ? 'coast' : c.conn ? 'junction' : 'lane', road: c.road, dir: c.dir });
  }
  for (const [list, kind] of [[tr.ahead, 'tram ahead'], [tr.oncoming, 'tram oncoming']]) {
    for (const t of list) {
      if ((t.alpha ?? 0) < 0.5) continue;
      t.mesh.userData.cars.forEach((m, k) => {
        const [hx, hy] = head(m.rotation.y);
        out.veh.push({ id: `${t.mesh.uuid}/${k}`, group: t.mesh.uuid, kind, x: m.position.x, y: -m.position.z, z: m.position.y, hx, hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
      });
    }
  }
  // our own set: car centres along the route behind the front
  const cars = g.tram.cars || 1;
  for (let k = 0; k < cars; k++) {
    const s = g.tram.s - 0.6 - 7.6 - k * 15.2, p = g.route.at(s), h = g.route.heading(s, 3);
    out.veh.push({ id: `us/${k}`, group: 'us', kind: 'our tram', x: p.x, y: p.y, z: g.route.ground.profile.height(s), hx: h.hx, hy: h.hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
  }
  const M = new tr.crowd.matrix.constructor();
  for (const [i, w] of (tr.slots || []).entries()) {
    if (!w || w.alpha < 0.5) continue;
    tr.crowd.getMatrixAt(i, M);
    const e = M.elements;
    out.walk.push({ id: `w${i}`, x: e[12], y: -e[14], z: e[13], hx: e[8], hy: -e[10], walk: w }); // w: the slot's walker (new object on respawn)
  }
  return out;
}

export async function trafficRun({ from = 0, until = 999, sample = 0.2, dt = 1 / 30, maxT = 7200, seed = 22, progress = () => {} } = {}) {
  const $ = (id) => document.getElementById(id);
  window.runSeed = seed; // the run's seeded stream (src/random.js): the same run every time; cleared below
  $('menu').classList.remove('hidden');
  $('selStop').value = String(from);
  $('selStop').dispatchEvent(new Event('change'));
  // nothing from the real clock or weather: the first trip of the day, autumn, dry, default set
  $('selTrip').value = '0';
  $('optTemp').value = 'autumn';
  $('optWeather').value = 'dry';
  $('optCars').value = 'auto';
  $('optObst').value = 'off';
  $('optAuto').checked = false;
  $('btnStart').click();
  const g = window.game, tr = window.traffic;
  g.audio.setMuted(true);
  window.headless = true; // the page's frame loop must not step the game between our chunks
  const ap = new Autopilot();
  const slides = [], jumps = [], overlaps = [], hits = [], knobs = [], redRuns = [];
  const lastS = new Map(); // oncoming tram -> its position at the previous step
  let heat = null; // last heating setting: saloon / cab / flap, to count the autopilot's knob changes
  const prev = new Map(), open = new Map(); // id -> last sample; pair -> open overlap episode
  let T = 0, nextSample = 0, samples = 0, seenVeh = 0, seenWalk = 0;
  const camera = { position: { x: 0, z: 0 } };
  const step = sample;
  try {
  while (T < maxT && g.nextStop < until && !g.finished) {
    for (let k = 0; k < 600 && T < maxT && !g.finished; k++) {
      ap.step(g, dt);
      g.update(dt, ap.input);
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
      const p = g.route.at(g.tram.s);
      camera.position.x = p.x; camera.position.z = -p.y;
      tr.update(dt, camera);
      T += dt;
      window.trafficWatch?.(g, tr, T); // (a dev probe of one moment: the cars around a stuck scene)
      if (T < nextSample) continue;
      nextSample = T + step;
      samples++;
      const snap = snapshot(g, tr);
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
      for (const k of [...open.keys()]) if (!live.has(k)) open.delete(k);
    }
    progress(`traffic run: ${Math.round(T)} s, stop ${g.nextStop}`);
    await new Promise((r) => setTimeout(r, 0));
  }
  } finally { window.headless = false; delete window.runSeed; }
  const pick = (rule, items, of) => {
    const byKind = {};
    for (const it of items) byKind[it.kind] = (byKind[it.kind] || 0) + 1;
    const byState = {};
    for (const it of items) if (it.states) byState[it.states] = (byState[it.states] || 0) + 1;
    return { rule, count: items.length, of, kinds: byKind, ...(Object.keys(byState).length ? { states: byState } : {}), places: [...items].sort((a, b) => b.mag - a.mag).slice(0, TOP), ...placesAt(items) };
  };
  const minutes = T / 60;
  return {
    stats: { simSeconds: Math.round(T), samples, finished: g.finished, nextStop: g.nextStop, cyclesBroken: tr.cyclesBroken || 0, carsVisible: +(seenVeh / Math.max(1, samples)).toFixed(1), walkersVisible: +(seenWalk / Math.max(1, samples)).toFixed(1),
      // (a run that did not finish: what held the tram at the end, as u3 and redruns report it)
      ...(g.finished || g.nextStop >= until ? {} : { stuckScene: stuckScene(g, tr, ap) }) },
    checks: {
      slide: pick('traffic-no-sideways-motion', slides, samples),
      jump: pick('traffic-no-teleport', jumps, samples),
      overlap: pick('traffic-no-overlap', overlaps, Math.round(minutes)),
      walkerHit: pick('traffic-walkers-clear-of-vehicles', hits, Math.round(minutes)),
      heatingKnobs: pick('autopilot-calm-heating', knobs, Math.round(minutes)),
      redRuns: pick('trams-obey-junction-signals', redRuns, Math.round(minutes)),
    },
  };
}
