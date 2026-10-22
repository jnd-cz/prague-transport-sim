// Dev tool: run the real game and traffic headless along the line (the autopilot drives, fixed
// time step, the camera follows the tram as in play) and watch what the player would see. Every
// `sample` seconds the pose of each visible car, walker, AI tram and our tram is recorded:
//   slide  - a car or walker moving sideways against its heading (wrong path, lane jump)
//   jump   - a visible car or walker that teleports between two samples
//   overlap- two vehicles intersecting (car/car, car/tram, tram/tram), once per episode
//   walker - a walker inside a vehicle
// Used by tools/lint.js ({ traffic: true }); returns checks in the same shape.
import { Autopilot } from '../src/autopilot.js';

const CAR = [4.3, 1.8], TRAM = [14.0, 2.5];
const TOP = 12;

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
    out.veh.push({ id: `car${i}`, kind: 'car', x: p.x, y: -p.z, hx, hy, l: CAR[0] / 2, w: CAR[1] / 2, src: c.kind === 'street' ? 'lane' : 'road', alpha: c.alpha,
      state: c.kind === 'street' ? 'lane' : c.coast && !c.active ? 'coast' : 'road', road: c.road, dir: c.dir });
  }
  for (const [list, kind] of [[tr.ahead, 'tram ahead'], [tr.oncoming, 'tram oncoming']]) {
    for (const t of list) {
      if ((t.alpha ?? 0) < 0.5) continue;
      t.mesh.userData.cars.forEach((m, k) => {
        const [hx, hy] = head(m.rotation.y);
        out.veh.push({ id: `${t.mesh.uuid}/${k}`, group: t.mesh.uuid, kind, x: m.position.x, y: -m.position.z, hx, hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
      });
    }
  }
  // our own set: car centres along the route behind the front
  const cars = g.tram.cars || 1;
  for (let k = 0; k < cars; k++) {
    const s = g.tram.s - 0.6 - 7.6 - k * 15.2, p = g.route.at(s), h = g.route.heading(s, 3);
    out.veh.push({ id: `us/${k}`, group: 'us', kind: 'our tram', x: p.x, y: p.y, hx: h.hx, hy: h.hy, l: TRAM[0] / 2, w: TRAM[1] / 2 });
  }
  const M = new tr.crowd.matrix.constructor();
  for (const [i, w] of (tr.slots || []).entries()) {
    if (!w || w.alpha < 0.5) continue;
    tr.crowd.getMatrixAt(i, M);
    const e = M.elements;
    out.walk.push({ id: `w${i}`, x: e[12], y: -e[14], hx: e[8], hy: -e[10], walk: w }); // w: the slot's walker (new object on respawn)
  }
  return out;
}

// seeded random numbers (mulberry32): the same run every time, so counts compare with the baseline
function seeded(seed) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export async function trafficRun({ from = 0, until = 999, sample = 0.2, dt = 1 / 30, maxT = 7200, seed = 22, progress = () => {} } = {}) {
  const $ = (id) => document.getElementById(id);
  const random = Math.random;
  Math.random = seeded(seed); // the game and the traffic draw from Math.random; restored below
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
  const slides = [], jumps = [], overlaps = [], hits = [];
  const prev = new Map(), open = new Map(); // id -> last sample; pair -> open overlap episode
  let T = 0, nextSample = 0, samples = 0, seenVeh = 0, seenWalk = 0;
  const camera = { position: { x: 0, z: 0 } };
  const step = sample;
  try {
  while (T < maxT && g.nextStop < until && !g.finished) {
    for (let k = 0; k < 600 && T < maxT && !g.finished; k++) {
      ap.step(g, dt);
      g.update(dt, ap.input);
      const p = g.route.at(g.tram.s);
      camera.position.x = p.x; camera.position.z = -p.y;
      tr.update(dt, camera);
      T += dt;
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
        const why = isCar ? (q.state !== o.state ? `${q.state}→${o.state}` : o.state === 'lane' ? 'lane beside the tram' : q.road !== o.road ? 'next road' : q.dir !== o.dir ? 'turned' : 'same road') : 'walk';
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
        const depth = overlap(a, b);
        if (depth <= 0.05) continue;
        const key = a.id < b.id ? `${a.id}|${b.id}` : `${b.id}|${a.id}`;
        live.add(key);
        const kinds = [a.kind, b.kind].sort().join(' / ');
        const ep = open.get(key);
        if (ep) { if (depth > ep.mag) Object.assign(ep, { mag: depth, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }); continue; }
        const rec = { kind: kinds, x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, mag: depth, s: Math.round(g.tram.s), info: `${kinds}, ${depth.toFixed(1)} m deep` };
        open.set(key, rec);
        overlaps.push(rec);
      }
      for (const k of [...open.keys()]) if (!live.has(k)) open.delete(k);
      // walkers inside a vehicle
      for (const w of snap.walk) for (const v of V) if (inBox(v, w.x, w.y)) {
        hits.push({ kind: v.kind, x: w.x, y: w.y, mag: 1, s: Math.round(g.tram.s), info: `walker inside ${v.kind}` });
        break;
      }
    }
    progress(`traffic run: ${Math.round(T)} s, stop ${g.nextStop}`);
    await new Promise((r) => setTimeout(r, 0));
  }
  } finally { window.headless = false; Math.random = random; }
  const pick = (rule, items, of) => {
    const byKind = {};
    for (const it of items) byKind[it.kind] = (byKind[it.kind] || 0) + 1;
    return { rule, count: items.length, of, kinds: byKind, places: [...items].sort((a, b) => b.mag - a.mag).slice(0, TOP) };
  };
  const minutes = T / 60;
  return {
    stats: { simSeconds: Math.round(T), samples, finished: g.finished, nextStop: g.nextStop, carsVisible: +(seenVeh / Math.max(1, samples)).toFixed(1), walkersVisible: +(seenWalk / Math.max(1, samples)).toFixed(1) },
    checks: {
      slide: pick('traffic-no-sideways-motion', slides, samples),
      jump: pick('traffic-no-teleport', jumps, samples),
      overlap: pick('traffic-no-overlap', overlaps, Math.round(minutes)),
      walkerHit: pick('traffic-walkers-clear-of-vehicles', hits, samples),
    },
  };
}
