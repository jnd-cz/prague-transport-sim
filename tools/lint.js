// Dev tool: lints for the loaded line (PLAN.md §2). Each check counts one kind of problem over the
// whole line and lists the worst places, so a fix is judged by the count, not by one spot.
// In the browser console on a running shift (start one from the menu first):
//   const { lint } = await import('/tools/lint.js?v=' + Date.now());
//   await lint();                 // quick checks (a few seconds)
//   await lint({ bot: true });    // + the street bot (DTM lines, about a minute)
//   await lint({ traffic: true }); // + the whole line driven headless, traffic watched (a minute or two)
// The report is saved to reports/lineN.json by tools/serve.py; compare with the committed baseline:
//   python tools/lint_report.py            (--accept makes the current reports the baseline)
import { makeT3, placeConsist } from '../src/models.js';
import { runStreetBot } from '../src/streetbot.js';
import { trafficRun } from './traffic_lint.js';

const TOP = 12; // places listed per check

// one check's result: how many, out of how many, and the worst places
function check(rule, of, items, key = (p) => p.mag) {
  const places = [...items].sort((a, b) => key(b) - key(a)).slice(0, TOP);
  return { rule, count: items.length, of, places };
}

// A two-car set standing at every stop: both cars on the track, coupled (centres 15.2 m apart
// along the track, a little less as a chord on curves). Catches routes that end at a terminus stop
// with no track behind it (the second car was drawn inside the first at Sídliště Řepy).
function consistAtStops(g) {
  const route = g.route, prof = g.route.ground?.profile;
  const model = window.tramModel?.userData.cars.length >= 2 ? window.tramModel : makeT3({ line: g.data.line, cars: 2, detailed: false });
  const keep = model === window.tramModel ? model.userData.cars.map((c) => [c.position.clone(), c.rotation.clone()]) : null;
  const at = (q) => { const p = route.at(q); return [p.x, p.y, prof ? prof.height(q) : 0]; };
  // distance from a point to the route curve near s (the route includes the run-in / run-out)
  const offTrack = (x, y, s) => {
    let best = Infinity;
    for (let q = s - 25; q <= s + 25; q += 0.5) { const p = route.at(q); best = Math.min(best, Math.hypot(p.x - x, p.y - y)); }
    return best;
  };
  const bad = [];
  for (const st of g.stops) {
    placeConsist(model, st.target, at);
    const c = model.userData.cars.map((m) => m.position);
    const gap = Math.hypot(c[0].x - c[1].x, c[0].z - c[1].z);
    const off = Math.max(...c.map((p, k) => offTrack(p.x, -p.z, st.target - 7.6 - k * 15.2)));
    if (gap < 14 || gap > 15.5 || off > 0.5) bad.push({ stop: st.name, s: Math.round(st.target), mag: Math.max(Math.abs(15.2 - gap), off), info: `gap ${gap.toFixed(2)} m, ${off.toFixed(2)} m off the track` });
  }
  if (keep) model.userData.cars.forEach((m, k) => { m.position.copy(keep[k][0]); m.rotation.copy(keep[k][1]); });
  return check('consist-coupled', g.stops.length, bad);
}

// Signal heads standing along a platform (they belong at its head, past the end, or on the wire).
function signalsInPlatforms(g) {
  const bad = [];
  for (const sg of g.signals) {
    const p = sg.mesh.position, n = g.route.nearest(p.x, -p.z);
    if (!n) continue;
    for (const st of g.stops) {
      if (st.p0 == null || n.s <= st.p0 || n.s >= st.p1) continue;
      bad.push({ stop: st.name, s: Math.round(n.s), x: p.x, y: -p.z, mag: Math.min(n.s - st.p0, st.p1 - n.s), info: `${(st.p1 - n.s).toFixed(1)} m before the platform end` });
    }
  }
  return check('signal-not-in-platform', g.signals.length, bad);
}

// Roofs of the drawn buildings in a 4 m grid: a point under a roof is inside a building.
function roofIndex(world) {
  const grid = new Map(), cell = 4;
  world.traverse((m) => {
    if (!m.isMesh || !m.userData.building) return;
    const a = m.geometry.attributes.position;
    for (let i = 0; i + 2 < a.count; i += 3) {
      const t = [];
      for (let k = 0; k < 3; k++) t.push(a.getX(i + k), -a.getZ(i + k), a.getY(i + k));
      const area = (t[3] - t[0]) * (t[7] - t[1]) - (t[4] - t[1]) * (t[6] - t[0]);
      if (Math.abs(area) < 0.5) continue; // walls (vertical) and slivers
      const x0 = Math.floor(Math.min(t[0], t[3], t[6]) / cell), x1 = Math.floor(Math.max(t[0], t[3], t[6]) / cell);
      const y0 = Math.floor(Math.min(t[1], t[4], t[7]) / cell), y1 = Math.floor(Math.max(t[1], t[4], t[7]) / cell);
      for (let ix = x0; ix <= x1; ix++) for (let iy = y0; iy <= y1; iy++) {
        const k = ix * 100003 + iy;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(t);
      }
    }
  });
  // height of the roof over (x, y), or null
  return (x, y) => {
    let best = null;
    for (const t of grid.get(Math.floor(x / cell) * 100003 + Math.floor(y / cell)) || []) {
      const d = (t[4] - t[7]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[1] - t[7]);
      const w1 = ((t[4] - t[7]) * (x - t[6]) + (t[6] - t[3]) * (y - t[7])) / d;
      const w2 = ((t[7] - t[1]) * (x - t[6]) + (t[0] - t[6]) * (y - t[7])) / d;
      if (w1 < 0 || w2 < 0 || w1 + w2 > 1) continue;
      const z = w1 * t[2] + w2 * t[5] + (1 - w1 - w2) * t[8];
      if (best === null || z > best) best = z;
    }
    return best;
  };
}

// Trees whose trunk stands inside a building, or whose crown reaches into one (the crown circle,
// sampled at 8 points, passes under a roof that is higher than the crown's bottom).
function treesInBuildings(world) {
  const roof = roofIndex(world);
  const crown = [];
  world.traverse((m) => { if (m.isInstancedMesh && m.geometry.type === 'IcosahedronGeometry') crown.push(m); });
  const trunkIn = [], crownIn = [];
  const M = new crown[0].matrix.constructor();
  let n = 0;
  for (const mesh of crown) for (let i = 0; i < mesh.count; i++) {
    mesh.getMatrixAt(i, M);
    const e = M.elements, x = e[12], y = -e[14], zc = e[13];
    const sx = Math.hypot(e[0], e[1], e[2]), r = 2.6 * sx, bottom = zc - 2.6 * Math.hypot(e[4], e[5], e[6]);
    n++;
    const over = roof(x, y);
    if (over !== null && over > bottom) { trunkIn.push({ x, y, mag: r, info: `trunk under a roof at ${over.toFixed(1)} m` }); continue; }
    let deep = 0;
    for (let k = 0; k < 8; k++) for (const f of [0.5, 1]) {
      const a = (k / 8) * 2 * Math.PI, z = roof(x + Math.cos(a) * r * f, y + Math.sin(a) * r * f);
      if (z !== null && z > bottom) deep = Math.max(deep, r * f);
    }
    if (deep) crownIn.push({ x, y, mag: deep, info: `crown ${deep.toFixed(1)} m into a building (radius ${r.toFixed(1)} m)` });
  }
  return { trunk: check('tree-trunk-outside-buildings', n, trunkIn), crown: check('tree-crown-clear-of-buildings', n, crownIn) };
}

// OSM bridge spans on the route without a surveyed deck (Mosty 3D) under the track.
function bridgesWithoutDeck(g) {
  const real = g.route.ground?.profile?.realDecks || [];
  const bad = g.data.bridges.filter(([a, b]) => !real.some(([x, y]) => y > a && x < b))
    .map(([a, b]) => ({ s: Math.round(a), mag: b - a, info: `${Math.round(b - a)} m span without a deck model` }));
  return check('bridge-has-deck', g.data.bridges.length, bad);
}

export async function lint({ bot = false, traffic = false, save = true } = {}) {
  const g = window.game, world = window.world;
  if (!g || !world) throw new Error('start a shift first');
  const t0 = performance.now();
  const trees = treesInBuildings(world);
  const checks = {
    consist: consistAtStops(g),
    signalsInPlatforms: signalsInPlatforms(g),
    treeTrunks: trees.trunk,
    treeCrowns: trees.crown,
    bridges: bridgesWithoutDeck(g),
  };
  if (bot && g.route.ground?.dtm) {
    const r = await runStreetBot({ world, traffic: window.traffic, ground: g.route.ground, route: g.route });
    checks.streetBot = { rule: 'street-bot', count: r.findings.length, of: Math.round((r.stats.carKm + r.stats.walkKm) * 1000), samples: r.stats.samples, places: r.findings.slice(0, TOP).map((P) => ({ kind: P.kind, x: P.x, y: P.y, mag: P.mag, n: P.n, info: P.info })) };
  }
  let trafficStats;
  if (traffic) {
    // last: it starts a new shift from the first stop
    const r = await trafficRun({});
    Object.assign(checks, r.checks);
    trafficStats = r.stats;
  }
  const report = { line: g.data.line, traffic: trafficStats, date: new Date().toISOString(), secs: Math.round((performance.now() - t0) / 100) / 10, checks };
  if (save) {
    try {
      const r = await fetch(`/report/line${g.data.line}.json`, { method: 'POST', body: JSON.stringify(report, null, 1) });
      report.saved = r.ok;
    } catch { report.saved = false; }
  }
  return report;
}
