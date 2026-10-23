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

// Streets that wave: the drawn survey surface along lines parallel to the route (6-20 m either side,
// every 1 m), each sample against its 21 m running mean within the same surface class; a sample more
// than 8 cm off is a bump. Places: where samples deviate more than 15 cm, per 50 m.
const STREETS = new Set(['road', 'tram', 'parking', 'sidewalk', 'island', 'cycle', 'paved', 'platform']);
function streetWaviness(g) {
  const r = g.route, dtm = r.ground.dtm;
  if (!dtm) return check('streets-smooth', 0, []);
  let n = 0;
  const bad = new Map(), byClass = {};
  for (const lat of [-20, -14, -9, -6, 6, 9, 14, 20]) {
    const zs = [], cs = [];
    for (let s = 0; s < r.length; s += 1) { const o = r.offset(s, lat), t = dtm.surfaceAt(o.x, o.y); zs.push(t ? t.z : null); cs.push(t ? t.c : null); }
    for (let i = 10; i < zs.length - 10; i++) {
      if (zs[i] === null || !STREETS.has(cs[i])) continue; // (lawns follow the lidar ground; water is level)
      let sum = 0, ok = true;
      for (let k = -10; k <= 10 && ok; k++) { if (zs[i + k] === null || cs[i + k] !== cs[i]) ok = false; else sum += zs[i + k]; }
      if (!ok) continue;
      n++;
      const res = Math.abs(zs[i] - sum / 21);
      if (res <= 0.08) continue;
      byClass[cs[i]] = (byClass[cs[i]] || 0) + 1;
      const k = Math.round(i / 50);
      if (res > 0.15 && !(bad.get(k)?.mag >= res)) { const o = r.offset(i, lat); bad.set(k, { s: i, x: o.x, y: o.y, mag: res, info: `${cs[i]} ${res.toFixed(2)} m off its 21 m mean, ${lat} m from the route` }); }
    }
  }
  const c = check('streets-smooth', n, [...bad.values()]);
  c.count = Object.values(byClass).reduce((a, b) => a + b, 0);
  c.samples = byClass;
  return c;
}

// The coarse lidar terrain (10 x 15 m) showing through a surveyed surface: within 25 m of the route,
// every 2 m along and 1.5 m across, terrain more than 5 cm above the drawn survey.
function terrainOverSurvey(g) {
  const r = g.route, ground = r.ground, dtm = ground.dtm, T = ground.terrain;
  if (!dtm) return check('terrain-under-survey', 0, []);
  let n = 0;
  const bad = new Map();
  for (let s = 0; s < r.length; s += 2) for (let lat = -25; lat <= 25; lat += 1.5) {
    const o = r.offset(s, lat), t = dtm.surfaceAt(o.x, o.y);
    if (!t) continue;
    n++;
    const dz = T.height(o.x, o.y) - t.z;
    const k = Math.round(s / 20);
    if (dz > 0.05 && !(bad.get(k)?.mag >= dz)) bad.set(k, { s: Math.round(s), x: o.x, y: o.y, mag: dz, info: `terrain ${dz.toFixed(2)} m above the ${t.c}, ${lat} m from the route` });
  }
  return check('terrain-under-survey', n, [...bad.values()]);
}

// What carries the rails: every 2 m, a ray down from 2.5 m above the track bed onto the drawn
// ground, street, bridge deck or bridge model (not the bed itself). Something above the bed top
// covers the rails; nothing within 0.6 m under the bed is a gap (on a bridge: the deck lies below
// the tracks).
function railSupport(g, world) {
  const r = g.route, pr = r.ground.profile;
  const targets = [];
  world.traverse((m) => { if (m.isMesh && (m.userData.building || ['terrain', 'dtm', 'road', 'support'].includes(m.userData.surface))) targets.push(m); });
  const ray = new THREE.Raycaster(), down = new THREE.Vector3(0, -1, 0), o = new THREE.Vector3();
  ray.far = 9;
  let n = 0;
  const bad = new Map();
  for (let s = 0; s < r.length; s += 2) {
    const p = r.at(s), zb = pr.height(s) + 0.2; // bed top
    o.set(p.x, zb + 2.5, -p.y);
    ray.set(o, down);
    const hit = ray.intersectObjects(targets, false)[0];
    n++;
    const top = hit ? hit.point.y : -Infinity, bridge = pr.onBridge(s);
    let info = null, mag = 0;
    if (top > zb + 0.05) { info = `${bridge ? 'bridge' : 'ground'} ${(top - zb).toFixed(2)} m above the bed top`; mag = top - zb; }
    else if (top < zb - 0.8) { info = hit ? `${bridge ? 'deck' : 'ground'} ${(zb - top).toFixed(2)} m below the bed top` : 'nothing under the bed within 6.5 m'; mag = hit ? zb - top : 6.5; }
    const k = Math.round(s / 20);
    if (info && !(bad.get(k)?.mag >= mag)) bad.set(k, { s: Math.round(s), x: p.x, y: p.y, mag, info });
  }
  return check('rails-supported', n, [...bad.values()]);
}

// Vertical curves of the track profile: the radius of every crest and sag over 20 m (change of
// grade per metre), flagged under 500 m (tram track: 500 m minimum in streets, 1000 m preferred), and
// grades over 9 %.
function verticalCurves(g) {
  const pr = g.route.ground.profile, L = g.route.length, bad = new Map();
  let n = 0, minR = Infinity;
  for (let s = 10; s < L - 10; s += 2) {
    n++;
    const dg = pr.grade(s + 10) - pr.grade(s - 10), R = 20 / Math.max(1e-6, Math.abs(dg)), gr = Math.abs(pr.grade(s));
    minR = Math.min(minR, R);
    const k = Math.round(s / 50);
    if (R < 500 && !(bad.get(k)?.mag >= 500 / R)) bad.set(k, { s: Math.round(s), mag: 500 / R, info: `${dg > 0 ? 'sag' : 'crest'} radius ${Math.round(R)} m` });
    else if (gr > 0.09 && !bad.has(k)) bad.set(k, { s: Math.round(s), mag: gr * 10, info: `grade ${(gr * 100).toFixed(1)} %` }); // (Hercovka - Kobylisy really climbs 8-8.8 %)
  }
  const c = check('vertical-curves', n, [...bad.values()]);
  c.minRadius = Math.round(minR);
  return c;
}

// Overhead line: every span (or bracket arm) carries the contact wire from above, at least 0.6 m over
// it (wire 5.6 m above the rails), and the two ends of a span are level (within 0.5 m).
function catenarySpans(g) {
  const bad = [];
  let n = 0;
  for (const c of g.route.catenary || []) {
    if (!c.attach?.length) continue;
    n++;
    const wire = c.z + 5.6, low = Math.min(...c.attach), tilt = Math.max(...c.attach) - low;
    if (low < wire + 0.6) bad.push({ s: Math.round(c.s), mag: wire + 0.6 - low, info: `span ${(low - wire).toFixed(2)} m over the contact wire${low < wire ? ' (holds it from below)' : ''}` });
    else if (tilt > 0.5) bad.push({ s: Math.round(c.s), mag: tilt, info: `span ends ${tilt.toFixed(2)} m apart in height` });
  }
  return check('catenary-from-above', n, bad);
}

// Track axes of a double-track line at least 2.9 m apart (OSM sometimes draws them 2.1 m apart): every
// 2 m where the opposite track runs alongside ours the other way, 40 m or more from a switch.
function trackSpacing(g) {
  const r = g.route, b = g.backRoute, sw = (g.data.switches || []).map((w) => w.s ?? w), bad = new Map();
  let n = 0;
  if (!b) return check('tracks-apart', 0, []);
  // (interlaced track, under 1.8 m apart, and 40 m around it: as src/trackfix.js)
  const gaunt = [];
  for (let s = 0; s < r.length; s += 2) { const p = r.at(s), q = b.nearest(p.x, p.y); if (q && q.d < 1.8) gaunt.push([s - 40, s + 40]); }
  for (let s = 0; s < r.length; s += 2) {
    const p = r.at(s), q = b.nearest(p.x, p.y);
    if (!q || q.d > 6 || q.d < 1.8 || gaunt.some(([a, c]) => s > a && s < c)) continue;
    const h = b.at(q.s);
    if (p.hx * h.hx + p.hy * h.hy > -0.97 || sw.some((w) => Math.abs(w - s) < 40)) continue;
    n++;
    const k = Math.round(s / 20);
    if (q.d < 2.9 && !(bad.get(k)?.mag >= 2.9 - q.d)) bad.set(k, { s: Math.round(s), x: p.x, y: p.y, mag: 2.9 - q.d, info: `tracks ${q.d.toFixed(2)} m apart` });
  }
  return check('tracks-apart', n, [...bad.values()]);
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
    streetWaviness: streetWaviness(g),
    terrainOverSurvey: terrainOverSurvey(g),
    railSupport: railSupport(g, world),
    verticalCurves: verticalCurves(g),
    catenary: catenarySpans(g),
    trackSpacing: trackSpacing(g),
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
