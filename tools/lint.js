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
import { roofIndex } from '../src/world.js';
import { tramClearance } from '../src/tram.js';
import * as THREE from 'three';
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
      if (st.p0 == null || n.s <= st.p0 || n.s >= st.p1 || sg.mesh.userData.hung) continue; // hung over the track is fine
      bad.push({ stop: st.name, s: Math.round(n.s), x: p.x, y: -p.z, mag: Math.min(n.s - st.p0, st.p1 - n.s), info: `${(st.p1 - n.s).toFixed(1)} m before the platform end` });
    }
  }
  return check('signal-not-in-platform', g.signals.length, bad);
}

// Trees whose trunk stands inside a building, or whose crown reaches into one (the crown circle,
// sampled at 8 points, passes under a roof that is higher than the crown's bottom).
function treesInBuildings(world) {
  const roof = roofIndex(world);
  const crown = [];
  world.traverse((m) => { if (m.isInstancedMesh && m.userData.trees) crown.push(m); });
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

// Signals and signs inside the space the tram sweeps: up to the roof (3.6 m above the rails) the
// body width plus the overhang in curves (tramClearance), above it the pantograph (±1 m, to 5.8 m).
function mountedInEnvelope(g) {
  const objs = [...g.signals.map((x) => x.mesh)];
  g.objects.traverse((o) => { if (o.userData.boardTop !== undefined && !objs.includes(o)) objs.push(o); });
  const bad = [], box = new THREE.Box3(), c = new THREE.Vector3();
  for (const o of objs) {
    box.setFromObject(o);
    if (box.isEmpty()) continue;
    box.getCenter(c);
    const n = g.route.nearest(c.x, -c.z);
    if (!n || n.d > 8) continue;
    const z0 = g.route.ground.profile.height(n.s) + 0.26; // rail top
    let worst = 0;
    // the box corners in plan, as lateral offsets from the track centre
    for (const [x, y] of [[box.min.x, box.min.z], [box.max.x, box.min.z], [box.min.x, box.max.z], [box.max.x, box.max.z], [c.x, c.z]]) {
      const q = g.route.at(n.s), lat = Math.abs(q.hx * (-y - q.y) - q.hy * (x - q.x));
      const body = tramClearance(g.route, n.s) - 0.25;
      if (box.min.y - z0 < 3.6) worst = Math.max(worst, body - lat);
      else if (box.min.y - z0 < 5.8) worst = Math.max(worst, 1.0 - lat);
    }
    if (worst > 0.05) bad.push({ s: Math.round(n.s), x: c.x, y: -c.z, mag: worst, info: `${o.userData.hung ? 'hung ' : ''}${o.userData.boardTop !== undefined && !g.signals.some((x) => x.mesh === o) ? 'sign' : 'signal'} ${worst.toFixed(2)} m inside the tram's envelope` });
  }
  return check('mounted-clear-of-tram', objs.length, bad);
}

// Grade separation: no signal, signalled crossing or pedestrian crossing of ours on a bridge span of
// the route (they belong to the road underneath; PLAN 9b).
function crossingsOnBridges(g) {
  const pr = g.route.ground.profile, bad = [];
  for (const sg of g.signals) if (pr.overBridge(sg.cross)) bad.push({ s: Math.round(sg.s), mag: 1, info: 'signal on a bridge span' });
  for (const s of g.data.crossings) if (pr.overBridge(s)) bad.push({ s: Math.round(s), mag: 0.5, info: 'pedestrian crossing in the data on a bridge span (no jaywalkers there)' });
  return check('grade-separated', g.signals.length, bad.filter((b) => b.info.startsWith('signal')));
}

// Two levels where our track is on a bridge: a car lane passing under the span stands on the road
// below (at least 2.5 m under the rails), a lane on the bridge itself on the deck (at the rails'
// level, ±0.5 m). Every car lane within 3 m of the route on a span, one sample per lane and span.
function levelsAtBridges(g) {
  const tr = window.traffic, r = g.route, pr = r.ground.profile, bad = [];
  let n = 0;
  for (const lane of tr?.laneList || []) {
    const seen = new Set();
    for (let s = 0; s <= lane.path.length; s += 2) {
      const p = lane.path.at(s), q = r.nearest(p.x, p.y);
      if (!q || q.d > 3 || !pr.onBridge(q.s)) continue;
      const span = pr.bridges.findIndex(([a, b]) => q.s > a - 4 && q.s < b + 4);
      if (seen.has(span)) continue;
      const dz = pr.height(q.s) - lane.road.hf(p.x, p.y), under = pr.overBridge(q.s) && !lane.road.b;
      if (!lane.road.b && !pr.overBridge(q.s)) continue; // at a bridge end or a low culvert: at grade
      seen.add(span);
      n++;
      if (under ? dz < 2.5 : Math.abs(dz + 0.12) > 0.5) bad.push({ s: Math.round(q.s), x: p.x, y: p.y, mag: Math.abs(dz), info: `${under ? 'road under the bridge' : 'road on the bridge'}: ${dz.toFixed(1)} m below the rails` });
    }
  }
  return check('two-levels-at-bridges', n, bad);
}

// Our track and the opposite one as drawn: within 6 m of the route every track lies on the track
// profile (a step between the two tracks, or a drawn track off the profile, is a vertical jump in the
// rails and the wire above them; the Modřany corridor had up to 6 m). Every 1.5 m of track, counted per 10 m.
function trackLevels(g) {
  const r = g.route, pr = r.ground.profile, bad = new Map();
  let n = 0;
  for (const t of g.data.tracks) {
    if (!t.z) continue;
    for (let i = 0; i < t.smooth.length; i++) {
      const [x, y] = t.smooth[i], q = r.nearest(x, y);
      if (!q || q.d > 5) continue;
      n++;
      const dev = t.z[i] - pr.height(q.s), k = Math.round(q.s / 10);
      if (Math.abs(dev) > 0.3 && !(bad.get(k)?.mag >= Math.abs(dev))) bad.set(k, { s: Math.round(q.s), x, y, mag: Math.abs(dev), info: `track ${dev.toFixed(2)} m off the profile, ${q.d.toFixed(1)} m from the route` });
    }
  }
  return check('tracks-on-profile', n, [...bad.values()]);
}

// Synthetic retaining walls (corridor carve) standing on a surveyed street surface.
function syntheticWallsOnStreets(g) {
  const ground = g.route.ground, dtm = ground?.dtm, walls = ground?.walls;
  if (!walls) return check('no-invented-walls-on-streets', 0, []);
  const bad = [];
  let n = 0;
  for (const run of walls.runs) for (let i = 0; i < run.pts.length - 1; i++) {
    n++;
    const s = (run.pts[i].s + run.pts[i + 1].s) / 2, f = g.route.offset(s, run.side * walls.bench);
    const t = dtm?.surfaceAt(f.x, f.y);
    if (t) bad.push({ s: Math.round(s), x: f.x, y: f.y, mag: run.pts[i].top - ground.profile.height(s), info: `wall on ${t.c}` });
  }
  return check('no-invented-walls-on-streets', n, bad);
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
    inventedWalls: syntheticWallsOnStreets(g),
    tramEnvelope: mountedInEnvelope(g),
    gradeSeparated: crossingsOnBridges(g),
    bridgeLevels: levelsAtBridges(g),
    trackLevels: trackLevels(g),
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
