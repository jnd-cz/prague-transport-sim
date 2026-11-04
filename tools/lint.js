// Dev tool: lints for the loaded line (docs/history/PLAN.md §2). Each check counts one kind of problem over the
// whole line and lists the worst places, so a fix is judged by the count, not by one spot.
// In the browser console on a running shift (load the page with ?keepgeo, start a shift first):
//   const { lint } = await import('/tools/lint.js?v=' + Date.now());
//   await lint();                 // quick checks (a few seconds)
//   await lint({ bot: true });    // + the street bot (DTM lines, about a minute)
//   await lint({ traffic: true }); // + the whole line driven headless, traffic watched (a minute or two)
// The report is saved to reports/lineN.json by tools/serve.py; compare with the committed baseline:
//   python tools/lint_report.py            (--accept makes the current reports the baseline)
import { makeT3, placeConsist, CONTACT_WIRE } from '../src/models.js';
import { roofIndex } from '../src/world.js';
import { tramClearance } from '../src/tram.js';
import * as THREE from 'three';
import { runStreetBot } from '../src/streetbot.js';
import { trafficRun, placesAt } from './traffic_lint.js';

const TOP = 12; // places listed per check

// one check's result: how many, out of how many, and the worst places
function check(rule, of, items, key = (p) => p.mag) {
  const places = [...items].sort((a, b) => key(b) - key(a)).slice(0, TOP);
  return { rule, count: items.length, of, places, ...placesAt(items) };
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

// Signal heads standing along a platform (an island-tip pole or a head on the wire is fine).
function signalsInPlatforms(g) {
  const bad = [];
  for (const sg of g.signals) {
    const p = sg.mesh.position, n = g.route.nearest(p.x, -p.z);
    if (!n) continue;
    for (const st of g.stops) {
      if (st.p0 == null || n.s <= st.p0 || n.s >= st.p1 || sg.mesh.userData.hung || sg.mesh.userData.tip) continue;
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
    const z0 = g.route.ground.profile.height(n.s); // rail top (the profile, src/heights.js)
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
// rails and the wire above them; the Modřany corridor had up to 6 m). The profile is read across the
// street (heightAt): with the build's heights the opposite track has its own (#197). Every 1.5 m of track,
// counted per 10 m.
function trackLevels(g) {
  const r = g.route, pr = r.ground.profile, bad = new Map();
  let n = 0;
  for (const t of g.data.tracks) {
    if (!t.z) continue;
    for (let i = 0; i < t.smooth.length; i++) {
      const [x, y] = t.smooth[i], q = r.nearest(x, y);
      if (!q || q.d > 5) continue;
      n++;
      const p = r.at(q.s), l = (y - p.y) * p.hx - (x - p.x) * p.hy; // (left > 0, as src/terrain.js near)
      const dev = t.z[i] - pr.heightAt(q.s, l), k = Math.round(q.s / 10);
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
    const p = r.at(s), zb = pr.height(s) - pr.lift(s); // bed top (src/heights.js)
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

// Compare the drawn rail heads with actual bed and street triangles on each canted curve.
// A separate missing-ray count makes registration gaps visible instead of calling them clear.
export function cantedRailVisibility(g, world) {
  const r = g.route, prof = r.ground.profile, rails = [], surfaces = [];
  world.traverse((m) => {
    if (!m.isMesh) return;
    if (m.userData.surface === 'rail') rails.push(m);
    else if (['bed', 'terrain', 'dtm', 'road', 'support'].includes(m.userData.surface)) surfaces.push(m);
  });
  const ray = new THREE.Raycaster(), down = new THREE.Vector3(0, -1, 0), o = new THREE.Vector3();
  ray.far = 4;
  // The meshes combine many tracks. Compare each rail with its own bed; an overlapping track's
  // ribbon is a separate obstruction, not a cant error on this one.
  const owner = (hit) => {
    const ranges = hit.object.userData.trackRanges || [];
    let lo = 0, hi = ranges.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (ranges[mid][0] <= hit.faceIndex) lo = mid + 1; else hi = mid; }
    const range = ranges[lo - 1];
    return range && hit.faceIndex < range[1] ? range[2] : null;
  };
  let samples = 0, missing = 0, missingBed = 0, curve = -1, inCurve = false;
  const bad = new Map(), other = new Map(), covered = new Map();
  for (let s = 0; s < r.length; s += 2) {
    const canted = r.cantAt(s) > 0.005;
    if (!canted) { inCurve = false; continue; }
    if (!inCurve) { curve++; inCurve = true; }
    for (const side of [-1, 1]) {
      const p = r.offset(s, side * 0.72);
      o.set(p.x, prof.height(s) + 1, -p.y); ray.set(o, down);
      let head = ray.intersectObjects(rails, false)[0];
      // The route and the smoothed track axis can differ slightly at switches.
      for (const shift of [-0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.4, 0.4]) {
        if (head) break;
        const q = r.offset(s, side * 0.72 + shift);
        o.set(q.x, prof.height(s) + 1, -q.y); ray.set(o, down);
        head = ray.intersectObjects(rails, false)[0];
      }
      if (!head) { missing++; continue; }
      const trackId = owner(head);
      if (trackId === null) throw new Error('canted rail check needs per-track geometry ranges');
      samples++;
      const hits = ray.intersectObjects(surfaces, false).filter((h) => h.point.y <= head.point.y + 0.4);
      const ownBed = hits.find((h) => h.object.userData.surface === 'bed' && owner(h) === trackId);
      if (!ownBed) missingBed++;
      else covered.set(curve, (covered.get(curve) || 0) | (side < 0 ? 1 : 2));
      for (const [map, hit] of [[bad, ownBed],
                                [other, hits.find((h) => h.object.userData.surface !== 'bed' || owner(h) !== trackId)]]) {
        const delta = hit ? hit.point.y - head.point.y : -Infinity;
        if (delta > 0.001 && !(map.get(curve)?.mag >= delta))
          map.set(curve, { s: Math.round(s), x: head.point.x, y: -head.point.z, side, mag: delta,
                           info: `${hit.object.userData.surface} ${(delta * 1000).toFixed(0)} mm above rail head` });
      }
    }
  }
  return { ...check('canted-bed-below-rail', samples, [...bad.values()]), curves: curve + 1, missing, missingBed,
           unmeasuredCurves: curve + 1 - [...covered.values()].filter((sides) => sides === 3).length,
           otherSurfaces: check('other-surfaces-above-rail', samples, [...other.values()]) };
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

// Points at arc lengths along a polyline (linear between its points), with its length.
function along(p) {
  const cum = [0];
  for (let i = 1; i < p.length; i++) cum.push(cum[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
  const L = cum[cum.length - 1];
  let j = 0;
  const at = (s) => {
    s = Math.max(0, Math.min(L, s));
    if (s < cum[j]) j = 0;
    while (j < p.length - 2 && cum[j + 1] < s) j++;
    const t = (s - cum[j]) / (cum[j + 1] - cum[j] || 1e-9);
    return [p[j][0] + (p[j + 1][0] - p[j][0]) * t, p[j][1] + (p[j + 1][1] - p[j][1]) * t];
  };
  return { L, at };
}

// The track in plan (#204): the radius over 5 m, the circle through a point and the farthest points within 2.5 m
// either side, at every point of the line's path, its opposite path and every track as the build drew them (its
// points lie on the fitted curves; a circle through points interpolated on the game's 1.5 m resample read a 19 m
// curve as 17.4 m: a 1 m chord sags 7 mm inside it). Flagged under 18 m (data/truth.json trackGeometry
// `min-radius-network`, the user: "under 18m there shouldn't be anything like that"); 18-20 m are exceptions
// (`min-radius-passenger`), listed in `exceptions`. tools/track_curve.py holds 20 m within the points' accuracy
// class and 18 m past it. Places per 10 m of each line, counted per class (our, opposite, the track's source).
const MIN_RADIUS = 18, EXCEPTION_RADIUS = 20, SLACK = 0.995, HALF = 2.5;
function circleRadius(a, b, c) {
  const ab = Math.hypot(b[0] - a[0], b[1] - a[1]), bc = Math.hypot(c[0] - b[0], c[1] - b[1]), ca = Math.hypot(a[0] - c[0], a[1] - c[1]);
  const area2 = Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]));
  return area2 > 1e-9 ? Math.min(1e6, (ab * bc * ca) / (2 * area2)) : 1e6;
}
function trackRadius(g) {
  const d = g.data, lines = [['our', d.path], ['opposite', d.pathBack], ...(d.tracks || []).map((t) => [t.src || 'osm', t.p])];
  const bad = new Map(), near = new Map(), kinds = {}, nearKinds = {};
  let n = 0, minR = Infinity;
  lines.forEach(([kind, p], li) => {
    if (!p || p.length < 3) return;
    const cum = [0];
    for (let i = 1; i < p.length; i++) cum.push(cum[i - 1] + Math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]));
    const L = cum[cum.length - 1];
    let j0 = 0, j1 = 0;
    for (let i = 0; i < p.length; i++) {
      if (cum[i] < HALF || cum[i] > L - HALF) continue;
      while (cum[i] - cum[j0] > HALF + 1e-9) j0++;
      j1 = Math.max(j1, i);
      while (j1 < p.length - 1 && cum[j1 + 1] - cum[i] <= HALF + 1e-9) j1++;
      if (cum[i] - cum[j0] < 0.6 * HALF || cum[j1] - cum[i] < 0.6 * HALF) continue; // (points far apart: a straight)
      const R = circleRadius(p[j0], p[i], p[j1]);
      n++;
      minR = Math.min(minR, R);
      const k = `${li}:${Math.round(cum[i] / 10)}`, map = R < MIN_RADIUS * SLACK ? bad : R < EXCEPTION_RADIUS * SLACK ? near : null;
      if (map && !(map.get(k)?.mag >= MIN_RADIUS / R))
        map.set(k, { kind, x: p[i][0], y: p[i][1], ...(kind === 'our' || kind === 'opposite' ? { s: Math.round(cum[i]) } : {}), mag: MIN_RADIUS / R, info: `${kind} track radius ${R.toFixed(1)} m over 5 m` });
    }
  });
  for (const k of near.keys()) if (bad.has(k)) near.delete(k);
  for (const b of bad.values()) kinds[b.kind] = (kinds[b.kind] || 0) + 1;
  for (const b of near.values()) nearKinds[b.kind] = (nearKinds[b.kind] || 0) + 1;
  const c = check('track-radius', n, [...bad.values()]);
  c.kinds = kinds;
  c.minRadius = Math.round(minR * 10) / 10;
  const e = check('track-radius-exceptions', n, [...near.values()]);
  c.exceptions = { count: e.count, kinds: nearKinds, places: e.places };
  return c;
}

// Where drawn tracks meet (#204): at every node where track chains end (a record or source joint, a switch, a
// crossing), the chains that continue each other (directions within 30°) are paired straightest first; a pair
// whose directions break by more than 1° is flagged, per class (joint: two ends, switch: three, crossing: four
// or more). The leg left over at a switch is the diverging track: its start angle against the through track is
// listed, not flagged (data/truth.json `switch-start`: most switches start tangentially, some abruptly). The
// direction at an end is the tangent of the parabola through the drawn track's first three points (a chord, or
// points between them, read a smooth 20 m curve as a 2-4° break). The bar stays 1° (the user, 2026-11-03: "Keep
// 1°, fix the nodes"): 71 breaks on line 17 were the game's drawing (a three-point average and a 1.5 m resample
// at short pieces' ends). Where at least two drawn points lie within JOIN_REACH of the end, the tangent is the
// least-squares parabola's through them: three points whose first step was 0.17 m read a smooth 21 m curve's
// joint at a crossing as a 1.2° break (0.2° fitted over 2-3 m).
const JOIN_REACH = 2.0;
function trackJoins(g) {
  const ends = [];
  for (const t of g.data.tracks || []) {
    const p = t.smooth || t.p;
    if (!p || p.length < 2) continue;
    const { L } = along(p);
    if (L < 0.5) continue;
    for (const fwd of [true, false]) {
      const q = fwd ? p : [...p].reverse(), p0 = q[0];
      let dx = q[1][0] - p0[0], dy = q[1][1] - p0[1];
      const near = [];
      for (let k = 1, c = 0; k < q.length; k++) {
        c += Math.hypot(q[k][0] - q[k - 1][0], q[k][1] - q[k - 1][1]);
        if (c > JOIN_REACH) break;
        near.push(q[k]);
      }
      if (near.length >= 2) {
        // y = a x + b x² through the end, least squares, in the frame of the chord to the farthest point
        const f = near[near.length - 1], cl = Math.hypot(f[0] - p0[0], f[1] - p0[1]), ux = (f[0] - p0[0]) / cl, uy = (f[1] - p0[1]) / cl;
        let x2 = 0, x3 = 0, x4 = 0, xy = 0, x2y = 0;
        for (const [qx, qy] of near) {
          const x = (qx - p0[0]) * ux + (qy - p0[1]) * uy, y = -(qx - p0[0]) * uy + (qy - p0[1]) * ux;
          x2 += x * x; x3 += x * x * x; x4 += x * x * x * x; xy += x * y; x2y += x * x * y;
        }
        const a = (xy * x4 - x2y * x3) / (x2 * x4 - x3 * x3 || 1e-12);
        dx = ux - a * uy;
        dy = uy + a * ux;
      } else if (q.length > 2) {
        const h1 = Math.hypot(dx, dy), h2 = Math.hypot(q[2][0] - q[1][0], q[2][1] - q[1][1]);
        if (h1 > 1e-6 && h2 > 1e-6) {
          const a = -(2 * h1 + h2) / (h1 * (h1 + h2)), b = (h1 + h2) / (h1 * h2), c = -h1 / (h2 * (h1 + h2));
          dx = a * p0[0] + b * q[1][0] + c * q[2][0];
          dy = a * p0[1] + b * q[1][1] + c * q[2][1];
        }
      }
      const l = Math.hypot(dx, dy) || 1;
      ends.push({ x: p0[0], y: p0[1], dx: dx / l, dy: dy / l, src: t.src || 'osm' });
    }
  }
  // ends at one node: within 5 cm (each chain ends at the node's position)
  const cell = new Map(), key = (x, y) => `${Math.round(x / 0.1)},${Math.round(y / 0.1)}`;
  ends.forEach((e, i) => { const k = key(e.x, e.y); if (!cell.has(k)) cell.set(k, []); cell.get(k).push(i); });
  const group = new Array(ends.length).fill(-1), groups = [];
  ends.forEach((e, i) => {
    if (group[i] >= 0) return;
    const gi = groups.length, members = [i];
    group[i] = gi;
    for (let m = 0; m < members.length; m++) {
      const a = ends[members[m]], kx = Math.round(a.x / 0.1), ky = Math.round(a.y / 0.1);
      for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++)
        for (const j of cell.get(`${kx + ox},${ky + oy}`) || [])
          if (group[j] < 0 && Math.hypot(ends[j].x - a.x, ends[j].y - a.y) <= 0.05) { group[j] = gi; members.push(j); }
    }
    groups.push(members);
  });
  const deg = (u, v) => (Math.acos(Math.max(-1, Math.min(1, u.dx * v.dx + u.dy * v.dy))) * 180) / Math.PI;
  const bad = [], diverging = [], kinds = {};
  let n = 0;
  for (const ms of groups) {
    if (ms.length < 2) continue;
    const pairs = [];
    for (let a = 0; a < ms.length; a++) for (let b = a + 1; b < ms.length; b++) {
      const u = ends[ms[a]], v = ends[ms[b]];
      const brk = deg(u, { dx: -v.dx, dy: -v.dy });
      if (brk < 30) pairs.push([brk, ms[a], ms[b]]);
    }
    pairs.sort((p, q) => p[0] - q[0]);
    const used = new Set(), through = [];
    for (const [brk, a, b] of pairs) if (!used.has(a) && !used.has(b)) { used.add(a); used.add(b); through.push([brk, a, b]); }
    const kind = ms.length === 2 ? 'joint' : ms.length === 3 ? 'switch' : 'crossing';
    for (const [brk, a, b] of through) {
      n++;
      if (brk > 1) {
        kinds[kind] = (kinds[kind] || 0) + 1;
        bad.push({ kind, x: ends[a].x, y: ends[a].y, mag: brk, info: `${kind}: the through track breaks ${brk.toFixed(1)}° (${ends[a].src}/${ends[b].src})` });
      }
    }
    if (through.length)
      for (const d of ms.filter((m) => !used.has(m))) {
        const e = ends[d], ang = Math.min(...through.flatMap(([, a, b]) => [deg(e, ends[a]), deg(e, ends[b])]));
        diverging.push({ x: Math.round(e.x), y: Math.round(e.y), deg: Math.round(ang * 10) / 10, src: e.src });
      }
  }
  const c = check('track-joins', n, bad);
  c.kinds = kinds;
  const angles = diverging.map((d) => d.deg).sort((a, b) => a - b), q = (f) => angles[Math.min(angles.length - 1, Math.floor(f * angles.length))];
  c.diverging = { n: angles.length, p50: q(0.5), p90: q(0.9), max: angles[angles.length - 1], places: diverging.sort((a, b) => b.deg - a.deg).slice(0, TOP) };
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
    const wire = c.z + CONTACT_WIRE, low = Math.min(...c.attach), tilt = Math.max(...c.attach) - low;
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

// Our track (both directions, as the game drives them) against the building footprints (OSM, data.buildings):
// a centre nearer than half a T3's width puts the car into the wall. The game lifts a building the route passes
// under (src/world.js), so the meshes hide it; main's OSM track came within 0.71 m of a wall at Karlovy lázně (#20).
// Footprints with a passage (building:min_level) are not in the data. Places per 20 m.
function trackInBuildings(g) {
  const HALF = 1.25, CELL = 20, cells = new Map();
  for (const b of g.data.buildings || []) {
    const p = b.p;
    if (!p || p.length < 3) continue;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of p) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    for (let x = Math.floor((x0 - HALF) / CELL); x <= Math.floor((x1 + HALF) / CELL); x++)
      for (let y = Math.floor((y0 - HALF) / CELL); y <= Math.floor((y1 + HALF) / CELL); y++) {
        const k = `${x},${y}`;
        if (!cells.has(k)) cells.set(k, []);
        cells.get(k).push(p);
      }
  }
  const clearance = (x, y) => {   // distance to the nearest footprint edge, negative inside one
    let best = Infinity;
    for (const p of cells.get(`${Math.floor(x / CELL)},${Math.floor(y / CELL)}`) || []) {
      let inside = false, d = Infinity;
      for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
        const [ax, ay] = p[j], [bx, by] = p[i], dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
        d = Math.min(d, Math.hypot(x - ax - t * dx, y - ay - t * dy));
        if ((ay > y) !== (by > y) && x < ax + ((y - ay) * dx) / (dy || 1e-9)) inside = !inside;
      }
      best = Math.min(best, inside ? -d : d);
    }
    return best;
  };
  const bad = new Map();
  let n = 0;
  for (const [name, r] of [['our', g.route], ['opposite', g.backRoute]]) {
    if (!r) continue;
    for (let s = 0; s < r.length; s += 2) {
      const p = r.at(s), d = clearance(p.x, p.y);
      n++;
      const k = `${name}${Math.round(s / 20)}`;
      if (d < HALF && !(bad.get(k)?.mag >= HALF - d))
        bad.set(k, { s: Math.round(s), x: p.x, y: p.y, mag: HALF - d, info: `${name} track ${d < 0 ? 'inside a building' : `${d.toFixed(2)} m from a building`}` });
    }
  }
  return check('track-clear-of-buildings', n, [...bad.values()]);
}

// Car lanes and footways against the survey (DTM lines), the tracks and the platforms. Every lane
// and every junction connector a car may take, every 2 m (ground level only):
//   off       the lane centre on a sidewalk, island, platform, lawn, steps (not carriageway, parking,
//             tram bed or paving at road level)
//   trambed   on a separate tram bed (survey class "tram" within 1.6 m of a track): cars drive on the
//             tracks only where the track lies in the carriageway
//   stop      through a tram platform (ours or the opposite one, game.platforms, or a surveyed one)
//   kink      the lane turns more than 12° within 4 m where its road runs straight (< 4°)
//   doubled   another road's lane the same way within 2.2 m alongside (two lanes where one is)
// and every footway (walker path) 2 m step: on the carriageway for more than 6 m in a row (crossing a
// street is fine), as "walkroad". Places per 30 m; counts per kind in samples.
function laneQuality(g) {
  const tr = window.traffic, dtm = g.route.ground?.dtm, r = g.route, bk = g.backRoute;
  if (!tr) return check('lanes-realistic', 0, []);
  const CARR = new Set(['road', 'parking', 'tram']), OK_WALK = new Set(['sidewalk', 'island', 'platform', 'paved', 'cycle', 'stairs', 'green']);
  const trackD = (x, y) => Math.min(r.distance(x, y), bk ? bk.distance(x, y) : Infinity);
  const plats = (g.platforms || []).map((p) => ({ p, rt: p.rt }));
  const onPlatform = (x, y) => plats.some(({ p, rt }) => {
    const n = rt.nearest(x, y);
    if (!n || n.s < p.s0 || n.s > p.s1) return false;
    const q = rt.at(n.s), lat = q.hx * (y - q.y) - q.hy * (x - q.x);
    return lat * p.side > p.inner - 0.2 && lat * p.side < p.outer;
  });
  const kinds = {}, bad = new Map();
  let n = 0;
  const flag = (kind, x, y, info) => {
    kinds[kind] = (kinds[kind] || 0) + 1;
    const q = r.nearest(x, y), k = `${kind}${Math.round(x / 30)},${Math.round(y / 30)}`;
    if (!bad.has(k)) bad.set(k, { s: q ? Math.round(q.s) : null, x, y, mag: 1, kind, info: `${kind}: ${info}` });
    else bad.get(k).mag++;
  };
  // lane points in a grid for the doubled test
  const grid = new Map();
  for (const L of tr.laneList) {
    if (L.road.b || L.road.t) continue;
    for (let s = 0; s <= L.path.length; s += 2) {
      const p = L.path.at(s), k = Math.floor(p.x / 4) * 100003 + Math.floor(p.y / 4);
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push([p.x, p.y, p.hx, p.hy, L]);
    }
  }
  const paths = [];
  for (const L of tr.laneList) {
    if (L.road.b || L.road.t) continue;
    paths.push({ path: L.path, lane: L, road: L.road });
    for (const b of tr.nextLanes(L)) { const c = tr.connector(L, b); if (c && !b.road.b && !b.road.t) paths.push({ path: c.path, conn: true }); }
  }
  for (const { path, lane, road, conn } of paths) {
    for (let s = 0; s <= path.length; s += 2) {
      const p = path.at(s);
      n++;
      const c = dtm ? dtm.classAt(p.x, p.y) : 'road';
      if (c && !CARR.has(c) && !(c === 'paved' || c === 'cycle')) flag('off', p.x, p.y, `lane on ${c}`);
      if (c === 'tram' && trackD(p.x, p.y) < 1.6) flag('trambed', p.x, p.y, 'lane on a separate tram bed');
      if (onPlatform(p.x, p.y) || c === 'platform') flag('stop', p.x, p.y, 'lane through a tram platform');
      // kinks along a lane (not connectors) where the road itself runs straight
      if (!conn && s >= 4 && s <= path.length - 4) {
        const a = path.at(s - 2), b = path.at(s + 2);
        const turn = Math.abs(Math.atan2(a.hx * b.hy - a.hy * b.hx, a.hx * b.hx + a.hy * b.hy));
        if (turn > 0.21) {
          // the road's own turn at the same place (its centre line, nearest point)
          let best = 0, bd = Infinity;
          for (let u = 0; u <= road.path.length; u += 2) { const o = road.path.at(u), d = Math.hypot(o.x - p.x, o.y - p.y); if (d < bd) { bd = d; best = u; } }
          const ra = road.path.at(Math.max(0, best - 2)), rb = road.path.at(Math.min(road.path.length, best + 2));
          const rt = Math.abs(Math.atan2(ra.hx * rb.hy - ra.hy * rb.hx, ra.hx * rb.hx + ra.hy * rb.hy));
          if (rt < 0.07) flag('kink', p.x, p.y, `lane turns ${(turn * 57.3).toFixed(0)}° in 4 m on a straight road`);
        }
      }
      if (lane) {
        const k0x = Math.floor(p.x / 4), k0y = Math.floor(p.y / 4);
        let dbl = false;
        for (let i = k0x - 1; i <= k0x + 1 && !dbl; i++) for (let j = k0y - 1; j <= k0y + 1 && !dbl; j++) {
          for (const [x, y, hx, hy, L2] of grid.get(i * 100003 + j) || []) {
            if (L2.road === road || hx * p.hx + hy * p.hy < 0.9) continue;
            if (Math.hypot(x - p.x, y - p.y) < 2.2) { dbl = true; break; }
          }
        }
        if (dbl) flag('doubled', p.x, p.y, 'another road\'s lane alongside, the same way');
      }
    }
  }
  // walkers on the carriageway
  if (dtm) for (const w of tr.walks) {
    if (w.deck) continue;
    let run = 0;
    for (let s = 0; s <= w.path.length; s += 2) {
      const p = w.path.at(s), c = dtm.classAt(p.x + p.hy * w.off, p.y - p.hx * w.off);
      run = c && CARR.has(c) ? run + 2 : 0;
      if (run === 8) flag('walkroad', p.x, p.y, `footway on the ${c} for over 6 m`);
    }
  }
  const out = check('lanes-realistic', n, [...bad.values()]);
  out.count = Object.values(kinds).reduce((a, b) => a + b, 0);
  out.samples = kinds;
  // per 500 m of the route and kind (where to look first)
  out.byArea = {};
  for (const b of bad.values()) { const k = Math.round((b.s ?? -500) / 500) * 500; (out.byArea[k] ||= {})[b.kind] = ((out.byArea[k] ||= {})[b.kind] || 0) + b.mag; }
  return out;
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

// traffic counts swing 20-30 % whenever trajectories change: the traffic run is repeated with these
// seeds and the counts averaged (each run's counts kept in "runs")
const SEEDS = [22, 7, 1234];

// Bridge models (Mosty 3D) cutting through what drives on them: an up-facing model surface 0.15-2.5 m
// over the track (every 2 m of our route) or over a road on a bridge (every vertex of the bridge
// ways cars use): the slab or parapet clips the tram or the car (A2: Nádraží Modřany overpass, both
// ends of Čechův most, Trojský most, Štefánikův most). Places per 20 m.
function deckClip(g, world) {
  const r = g.route, G = r.ground, prof = G?.profile;
  if (!G?.model?.size || !prof) return check('bridge-model-clear-of-deck', 0, []);
  // (what is drawn: a ray down from 2.5 m over the surface to 0.15 m over it, against the building
  // meshes, Mosty 3D bridges among them, after the tram's envelope is cut out of them)
  const meshes = [];
  world.traverse((o) => { if (o.isMesh && o.userData.building) meshes.push(o); });
  const ray = new THREE.Raycaster(), down = new THREE.Vector3(0, -1, 0), from = new THREE.Vector3();
  const bad = new Map();
  let n = 0;
  const test = (x, y, z, s, what) => {
    n++;
    ray.set(from.set(x, z + 2.5, -y), down);
    ray.far = 2.35;
    const hit = ray.intersectObjects(meshes, false)[0];
    if (!hit) return;
    const mag = hit.point.y - z, k = `${what}${Math.round(x / 20)},${Math.round(y / 20)}`;
    if (!(bad.get(k)?.mag >= mag)) bad.set(k, { s: Math.round(s), x, y, mag, info: `${what}: model ${mag.toFixed(2)} m over it` });
  };
  for (let s = 0; s < r.length; s += 2) { const p = r.at(s); test(p.x, p.y, prof.height(s), s, 'track'); }
  for (const rd of g.data.roads) {
    if (!rd.b || !rd.c) continue;
    const hf = G.way(rd.way || rd.p, true);
    for (const [x, y] of rd.p) { const q = r.nearest(x, y); test(x, y, hf(x, y), q ? q.s : -1, 'road'); }
  }
  return check('bridge-model-clear-of-deck', n, [...bad.values()]);
}

// Roads passing under our route (OSM maxheight, tools/clearances.py; the profile keeps them as floors):
// the track at least the clearance + 0.8 m over the road surface. Short by more than 0.1 m is listed.
function underpassClearance(g) {
  const prof = g.route.ground?.profile, cs = prof?.clearances || [];
  const bad = [];
  for (const c of cs) {
    const z = prof.height(c.s), short = c.need - z;
    if (short > 0.1) bad.push({ s: Math.round(c.s), x: c.x, y: c.y, mag: short, info: `${c.name || c.kind} ${c.mh} m (${c.src}): track ${(z - c.zr).toFixed(1)} m over the road, ${short.toFixed(1)} m short` });
  }
  return check('underpass-clearance', cs.length, bad);
}

// The user's stop facts (data/truth.json `stops`) against the game's stop type: boarding across a car
// lane, a Vienna-type or street stop (`stop.vienna`, src/game.js _vienna), or at a kerb or island. A
// fact names a stop and a direction: towards a stop further on, from one behind, or "*" both; facts for
// other lines, unknown directions ("?", "centrum") and multi-platform stops are not counted. vienna-cycle
// (only the cycle strip raised, a classic kerb for cars) is listed but not counted: the detector's
// car-lane test does not decide it (#224).
async function stopFacts(g) {
  let facts = [];
  try { facts = (await (await fetch('/data/truth.json', { cache: 'no-store' })).json()).stops || []; } catch { /* no truth file */ }
  const index = new Map(g.stops.map((st, i) => [st.name, i]));
  const ACROSS = new Set(['vienna', 'street']), KERB = new Set(['island', 'kerb']);
  const bad = [], listed = [];
  let of = 0;
  for (const f of facts) {
    const i = index.get(f.name);
    if (i === undefined) continue;
    const ahead = index.get(f.towards), behind = index.get(f.from);
    const ours = f.towards === '*' || (ahead !== undefined && ahead > i) || (behind !== undefined && behind < i);
    if (!ours) continue;
    const st = g.stops[i], p = g.route.at(st.target);
    const where = { stop: st.name, s: Math.round(st.target), x: p.x, y: p.y };
    if (f.type === 'vienna-cycle') { listed.push({ ...where, info: `vienna-cycle; game: ${st.vienna ? 'across a lane' : 'at a kerb'}` }); continue; }
    if (!ACROSS.has(f.type) && !KERB.has(f.type)) continue;
    of++;
    if (ACROSS.has(f.type) !== !!st.vienna) bad.push({ ...where, mag: 1, info: `fact ${f.type} (${f.source}); game: ${st.vienna ? 'across a lane' : 'at a kerb'}` });
  }
  return { ...check('stop-facts', of, bad), listed };
}

export async function lint({ bot = false, traffic = false, save = true, seeds = SEEDS } = {}) {
  const g = window.game, world = window.world;
  if (!g || !world) throw new Error('start a shift first');
  // (the game frees the meshes' CPU copies after the GPU upload; the mesh checks need them: ?keepgeo)
  if (!/[?&](keepgeo|bot)\b/.test(location.search)) throw new Error('load the page with ?keepgeo (e.g. /?line=17&keepgeo)');
  const t0 = performance.now();
  const trees = treesInBuildings(world);
  const checks = {
    consist: consistAtStops(g),
    stopFacts: await stopFacts(g),
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
    cantedRailVisibility: cantedRailVisibility(g, world),
    verticalCurves: verticalCurves(g),
    catenary: catenarySpans(g),
    trackSpacing: trackSpacing(g),
    trackRadius: trackRadius(g),
    trackJoins: trackJoins(g),
    trackInBuildings: trackInBuildings(g),
    lanes: laneQuality(g),
    deckClip: deckClip(g, world),
    underpassClearance: underpassClearance(g),
  };
  if (bot && g.route.ground?.dtm) {
    const r = await runStreetBot({ world, traffic: window.traffic, ground: g.route.ground, route: g.route });
    checks.streetBot = { rule: 'street-bot', count: r.findings.length, of: Math.round((r.stats.carKm + r.stats.walkKm) * 1000), samples: r.stats.samples, places: r.findings.slice(0, TOP).map((P) => ({ kind: P.kind, x: P.x, y: P.y, mag: P.mag, n: P.n, info: P.info })) };
  }
  let trafficStats;
  if (traffic) {
    // last: it starts a new shift from the first stop
    const runs = [];
    for (const seed of seeds) runs.push(await trafficRun({ seed }));
    for (const [k, c] of Object.entries(runs[0].checks)) {
      const counts = runs.map((r) => r.checks[k]?.count ?? 0);
      checks[k] = { ...c, count: Math.round(counts.reduce((x, y) => x + y, 0) / counts.length), runs: counts };
    }
    trafficStats = { ...runs[0].stats, seeds, finished: runs.every((r) => r.stats.finished) };
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
