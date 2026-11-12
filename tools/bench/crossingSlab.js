// SPDX-License-Identifier: AGPL-3.0-or-later
// Rendered pedestrian surfaces above rail heads, grouped in 20 m route sections (#146).
// On a running shift loaded with ?keepgeo: (await import('/tools/bench/crossingSlab.js')).run()
import * as THREE from 'three';
import { pedestrianShape } from '../../src/pedestrianCrossings.js';
import { DTM_LIFT } from '../../src/terrain.js';

// A downward ray misses a vertical kerb. Intersect its actual drawn top edge with the sampled
// rail-head chords instead; this also detects a narrow lip between the 2 m surface samples.
export function crossingEdgeHits(game, heads) {
  const cells = new Map(), last = new Map(), size = 12, hits = [];
  const visit = (p, q, fn) => {
    for (let x = Math.floor(Math.min(p.x, q.x) / size); x <= Math.floor(Math.max(p.x, q.x) / size); x++)
      for (let y = Math.floor(Math.min(p.y, q.y) / size); y <= Math.floor(Math.max(p.y, q.y) / size); y++) fn(`${x},${y}`);
  };
  for (const q of heads) {
    const p = last.get(q.side); last.set(q.side, q);
    if (!p || q.s - p.s > 2.01) continue;
    const seg = { p, q };
    visit(p, q, (key) => { if (!cells.has(key)) cells.set(key, []); cells.get(key).push(seg); });
  }
  let samples = 0;
  const ground = game.route.ground;
  for (const { area: id } of ground.pedestrianCrossings?.survey || []) {
    const area = ground.dtm.areas[id];
    if (!['sidewalk', 'island'].includes(area.c)) continue;
    [area.ring, ...area.holes].forEach((ring, ri) => {
      for (let i = 0; i < ring.length; i++) {
        if (area.kerbs && !area.kerbs[ri]?.[i]) continue;
        const a = ring[i], b = ring[(i + 1) % ring.length], dx = b[0] - a[0], dy = b[1] - a[1], nearby = new Set();
        visit({ x:a[0], y:a[1] }, { x:b[0], y:b[1] }, (key) => { for (const s of cells.get(key) || []) nearby.add(s); });
        for (const { p, q } of nearby) {
          const ex = q.x - p.x, ey = q.y - p.y, den = dx * ey - dy * ex;
          if (Math.abs(den) < 1e-9) continue;
          const ax = p.x - a[0], ay = p.y - a[1], u = (ax * ey - ay * ex) / den, v = (ax * dy - ay * dx) / den;
          if (u < 0 || u > 1 || v < 0 || v > 1) continue;
          const s = p.s + (q.s - p.s) * v;
          if (area.l !== 0 && !ground.profile.onBridge(s)) continue;
          samples++;
          const railZ = p.z + (q.z - p.z) * v;
          const surfaceZ = a[2] + (b[2] - a[2]) * u + (area.l > 0 ? 0.02 : DTM_LIFT[area.c] ?? 0.03);
          if (surfaceZ - railZ <= 0.001) continue;
          hits.push({ s, side:p.side, x:a[0]+dx*u, y:a[1]+dy*u, railZ, surfaceZ, excess:surfaceZ-railZ,
                      source:'dtm', part:'kerb', area:id, class:area.c, level:area.l, way:null });
        }
      }
    });
  }
  return { hits, samples };
}

export function crossingReason(game, hit, source, way) {
  const r = game.route;
  if (!r.at) return null;
  const p = r.at(hit.s);
  if (source) {
    const a = r.ground.dtm?.areas[source[4]];
    if (!a) return null;
    const shape = pedestrianShape(p.x, p.y, p.hx, p.hy, a);
    if (!shape || shape.across[0] > -0.72 || shape.across[1] < 0.72) return 'survey-edge-does-not-cross-gauge';
    if (shape.along[1] - shape.along[0] > shape.across[1] - shape.across[0] + 1) return 'survey-surface-runs-along-track';
    return null;
  }
  const road = game.data.roads[way];
  if (!road) return null;
  let distance = Infinity, alignment = 0;
  for (let i = 1; i < road.p.length; i++) {
    const a = road.p[i - 1], b = road.p[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    if (!l2) continue;
    const t = Math.max(0, Math.min(1, ((hit.x - a[0]) * dx + (hit.y - a[1]) * dy) / l2));
    const d = Math.hypot(hit.x - a[0] - t * dx, hit.y - a[1] - t * dy);
    if (d < distance) { distance = d; alignment = Math.abs(dx * p.hx + dy * p.hy) / Math.sqrt(l2); }
  }
  return alignment >= 0.75 ? 'mapped-footway-runs-along-track' : null;
}

// Compare the survey-based crossing decisions with independently mapped OSM pedestrian ways.
function calibration(game) {
  const decisions = game.route.ground.pedestrianCrossings;
  if (!decisions) return null;
  const cells = new Map(), size = 25, reach = 5;
  for (const way of game.data.roads) {
    if (!way.z && !way.f) continue;
    for (let i = 1; i < way.p.length; i++) {
      const a = way.p[i - 1], b = way.p[i], segment = { a, b, zebra: !!way.z };
      for (let x = Math.floor((Math.min(a[0], b[0]) - reach) / size); x <= Math.floor((Math.max(a[0], b[0]) + reach) / size); x++)
        for (let y = Math.floor((Math.min(a[1], b[1]) - reach) / size); y <= Math.floor((Math.max(a[1], b[1]) + reach) / size); y++) {
          const key = `${x},${y}`; if (!cells.has(key)) cells.set(key, []); cells.get(key).push(segment);
        }
    }
  }
  let zebra = 0, footway = 0, unmatched = 0, mappedSpansTrack = 0;
  const widths = [], examples = [];
  for (const area of decisions.survey) for (const site of area.sites) {
    widths.push(site.width);
    let z = false, f = false;
    for (const seg of cells.get(`${Math.floor(site.x / size)},${Math.floor(site.y / size)}`) || []) {
      const dx = seg.b[0] - seg.a[0], dy = seg.b[1] - seg.a[1], l2 = dx * dx + dy * dy || 1e-9;
      const t = Math.max(0, Math.min(1, ((site.x - seg.a[0]) * dx + (site.y - seg.a[1]) * dy) / l2));
      if (Math.hypot(site.x - seg.a[0] - t * dx, site.y - seg.a[1] - t * dy) > reach) continue;
      if (Math.abs((dx * site.ux + dy * site.uy) / Math.sqrt(l2)) >= 0.75) continue;
      if (seg.zebra) z = true; else f = true;
    }
    if ((z || f) && site.spansTrack) mappedSpansTrack++;
    if (z) zebra++; else if (f) footway++; else { unmatched++; if (examples.length < 20) examples.push(site); }
  }
  return { surveyAreas: decisions.survey.length, surveySites: widths.length, zebra, footway, unmatched, mappedSpansTrack,
           minWidth: widths.length ? Math.min(...widths) : null, maxWidth: widths.length ? Math.max(...widths) : null,
           unmatchedExamples: examples, reviewSites: decisions.review?.length || 0, adjustedFootways: decisions.footways.length };
}

export async function run({ unfiltered = false } = {}) {
  const game = window.game, world = window.world;
  if (!game || !world || !/[?&](keepgeo|bot)\b/.test(location.search)) throw new Error('start a shift with ?keepgeo');
  const rails = [], footways = [];
  world.traverse((m) => {
    if (!m.isMesh) return;
    if (m.userData.surface === 'rail') rails.push(m);
    else if ((m.userData.surface === 'road' && m.userData.surfaceKind === 'footway') ||
             m.userData.surface === 'dtm') footways.push(m);
  });
  const route = game.route, profile = route.ground.profile, ray = new THREE.Raycaster();
  const origin = new THREE.Vector3(), down = new THREE.Vector3(0, -1, 0), bad = new Map();
  ray.far = 4;
  const walkway = new Set(['sidewalk', 'island', 'paved', 'cycle']);
  const area = (mesh, face) => {
    if (mesh.userData.walkAreas) return mesh.userData.walkAreas[face] || null;
    const ranges = mesh.userData.surfaceRanges || [];
    let lo = 0, hi = ranges.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (ranges[mid][0] <= face) lo = mid + 1; else hi = mid; }
    const r = ranges[lo - 1];
    return r && face < r[1] && walkway.has(r[2]) ? r : null;
  };
  // DTM street meshes also contain millions of road triangles. Keep only pedestrian triangles
  // for ray casting; their vertices, materials, transforms and source-area identities stay exact.
  const targets = [];
  for (const mesh of footways) {
    if (mesh.userData.surface !== 'dtm' || unfiltered) { targets.push(mesh); continue; }
    const pos = mesh.geometry.getAttribute('position'), vertices = [], areas = [];
    for (let i = 0; i < pos.count; i += 3) {
      const a = area(mesh, i / 3);
      if (!a) continue;
      for (let j = 0; j < 3; j++) vertices.push(pos.getX(i + j), pos.getY(i + j), pos.getZ(i + j));
      areas.push(a);
    }
    if (!areas.length) continue;
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    geometry.computeBoundingSphere();
    const filtered = new THREE.Mesh(geometry, mesh.material);
    filtered.matrixAutoUpdate = false; filtered.matrixWorld.copy(mesh.matrixWorld);
    filtered.userData = { ...mesh.userData, walkAreas: areas };
    targets.push(filtered);
  }
  // A 5 m survey triangle crossing a rail has its centroid within 6 m of the route. Its projected
  // position and neighbours bound the samples to inspect, including long diagonal crossings.
  const bins = new Set();
  for (const mesh of targets) {
    const pos = mesh.geometry.getAttribute('position');
    for (let i = 0; i < pos.count; i += 3) {
      if (mesh.userData.surface === 'dtm' && !area(mesh, i / 3)) continue;
      const x = (pos.getX(i) + pos.getX(i + 1) + pos.getX(i + 2)) / 3;
      const y = -(pos.getZ(i) + pos.getZ(i + 1) + pos.getZ(i + 2)) / 3;
      const n = route.nearest(x, y);
      if (!n || n.d > 6) continue;
      for (let k = -3; k <= 3; k++) { const b = Math.round(n.s / 2) + k; if (b >= 0 && b * 2 < route.length) bins.add(b); }
    }
  }
  let samples = 0, missing = 0;
  const hits = [], heads = [], missingHeads = [], unresolved = new Map(), explained = new Map();
  for (const bin of [...bins].sort((a, b) => a - b)) for (const side of [-1, 1]) {
    const s = bin * 2;
    let head = null;
    for (const shift of [0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.4, 0.4]) {
      const p = route.offset(s, side * 0.72 + shift);
      origin.set(p.x, profile.height(s) + 1, -p.y); ray.set(origin, down);
      head = ray.intersectObjects(rails, false)[0];
      if (head) break;
    }
    if (!head) { missing++; missingHeads.push({ s, side }); continue; }
    heads.push({ s, side, x:head.point.x, y:-head.point.z, z:head.point.y });
    samples++;
    const surface = ray.intersectObjects(targets, false).find((h) => {
      if (h.point.y > head.point.y + 0.4) return false;
      if (h.object.userData.surface !== 'dtm') return true;
      const a = area(h.object, h.faceIndex);
      return a && (a[3] === 0 || profile.onBridge(s));
    });
    const excess = surface ? surface.point.y - head.point.y : -Infinity, key = Math.round(s / 20);
    if (excess > 0.001) {
      const source = surface.object.userData.surface === 'dtm' ? area(surface.object, surface.faceIndex) : null;
      const way = source ? null : surface.object.userData.footwayRanges?.find((r) => r[0] <= surface.faceIndex && surface.faceIndex < r[1])?.[2];
      const hit = { s, side, x: head.point.x, y: -head.point.z, railZ: head.point.y, surfaceZ: surface.point.y, way: way ?? null,
                  source: source ? 'dtm' : 'osm-footway', area: source?.[4] ?? null,
                  class: source?.[2] ?? 'footway', level: source?.[3] ?? null, excess };
      hit.geometryReason = crossingReason(game, hit, source, way);
      hit.reason = hit.geometryReason;
      const target = hit.reason ? explained : unresolved;
      if (!target.has(key) || target.get(key).excess < excess) target.set(key, hit);
      hits.push(hit);
    }
    if (excess > 0.001 && !(bad.get(key)?.mag >= excess)) bad.set(key, {
      s: Math.round(s), x: head.point.x, y: -head.point.z, side, mag: excess,
      info: `${surface.object.userData.surface === 'dtm' ? `dtm/${area(surface.object, surface.faceIndex)[2]}` : 'OSM footway'} ${(excess * 1000).toFixed(0)} mm above rail`,
    });
  }
  const edges = crossingEdgeHits(game, heads);
  for (const hit of edges.hits) {
    hit.geometryReason = crossingReason(game, hit, [0,0,hit.class,hit.level,hit.area], null);
    hit.reason = hit.geometryReason;
    const key = Math.round(hit.s / 20), target = hit.reason ? explained : unresolved;
    if (!target.has(key) || target.get(key).excess < hit.excess) target.set(key, hit);
    if (!(bad.get(key)?.mag >= hit.excess)) bad.set(key, { ...hit, mag:hit.excess });
    hits.push(hit);
  }
  const places = [...bad.values()].sort((a, b) => b.mag - a.mag);
  const areaIds = new Set([...hits.filter((h) => h.area !== null).map((h) => h.area),
                           ...(route.ground.pedestrianCrossings?.review || []).map((s) => s.area)]);
  const sourceAreas = [...areaIds].filter((id) => route.ground.dtm?.areas[id]).map((id) => {
    const a = route.ground.dtm.areas[id];
    return { id, sourceId: a.sourceId, class: a.c, level: a.l, ring: a.ring, holes: a.holes };
  });
  const reviewCandidates = (route.ground.pedestrianCrossings?.review || []).map((s) => ({ ...s,
    s: route.nearest(s.x, s.y)?.s, sourceId: route.ground.dtm?.areas[s.area]?.sourceId }));
  // Each geometric class has its own count and places, so rebuilds reveal new/moved cases in
  // --compare without a list of generated array indexes masquerading as truth facts.
  const classified = {};
  for (const [reason, name] of Object.entries({
    'mapped-footway-runs-along-track':'crossingAlongFootway',
    'survey-edge-does-not-cross-gauge':'crossingSurveyEdge',
    'survey-surface-runs-along-track':'crossingAlongSurvey',
  })) {
    const sections = new Map();
    for (const h of hits.filter((h) => h.reason === reason)) {
      const k = Math.round(h.s / 20);
      if (!sections.has(k) || sections.get(k).excess < h.excess) sections.set(k, h);
    }
    classified[name] = { rule:reason, count:sections.size, at:[...sections.values()].map((h) => [h.x,h.y,h.s]) };
  }
  const reviewPlaces = new Map(reviewCandidates.map((s) => [`${s.x.toFixed(1)},${s.y.toFixed(1)}`,s]));
  classified.crossingSurveyReview = { rule:'survey-patch-needs-review', count:reviewPlaces.size,
    at:[...reviewPlaces.values()].map((s) => [s.x,s.y,s.s]) };
  return { calibration: calibration(game), hits, missingHeads, sourceAreas, reviewCandidates,
           checks: { crossingSlab: { rule: 'pedestrian-surface-below-rail', count: unresolved.size, rawCount: places.length,
                                  reviewCandidates: reviewCandidates.length,
                                  kerbOf: edges.samples, kerbHits: edges.hits.length,
                                  of: samples, missing, sections: [...unresolved.values()].sort((a, b) => a.s - b.s),
                                  explainedSections: [...explained.values()].sort((a, b) => a.s - b.s),
                                  rawSections: places.sort((a, b) => a.s - b.s),
                                  at: [...unresolved.values()].map((h) => [h.x,h.y,h.s]),
                                  places: [...unresolved.values()].sort((a, b) => b.excess - a.excess).slice(0, 12).map((h) => ({...h, mag:h.excess})) }, ...classified } };
}
