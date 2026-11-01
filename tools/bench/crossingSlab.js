// Rendered pedestrian surfaces above rail heads, grouped in 20 m route sections (#146).
// On a running shift loaded with ?keepgeo: (await import('/tools/bench/crossingSlab.js')).run()
import * as THREE from 'three';

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
  let zebra = 0, footway = 0, unmatched = 0;
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
    if (z) zebra++; else if (f) footway++; else { unmatched++; if (examples.length < 20) examples.push(site); }
  }
  return { surveyAreas: decisions.survey.length, surveySites: widths.length, zebra, footway, unmatched,
           minWidth: widths.length ? Math.min(...widths) : null, maxWidth: widths.length ? Math.max(...widths) : null,
           unmatchedExamples: examples, reviewSites: decisions.review?.length || 0, adjustedFootways: decisions.footways.length };
}

export function run({ unfiltered = false } = {}) {
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
  for (const bin of [...bins].sort((a, b) => a - b)) for (const side of [-1, 1]) {
    const s = bin * 2;
    let head = null;
    for (const shift of [0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.4, 0.4]) {
      const p = route.offset(s, side * 0.72 + shift);
      origin.set(p.x, profile.height(s) + 1, -p.y); ray.set(origin, down);
      head = ray.intersectObjects(rails, false)[0];
      if (head) break;
    }
    if (!head) { missing++; continue; }
    samples++;
    const surface = ray.intersectObjects(targets, false).find((h) => {
      if (h.point.y > head.point.y + 0.4) return false;
      if (h.object.userData.surface !== 'dtm') return true;
      const a = area(h.object, h.faceIndex);
      return a && (a[3] === 0 || profile.onBridge(s));
    });
    const excess = surface ? surface.point.y - head.point.y : -Infinity, key = Math.round(s / 20);
    if (excess > 0.001 && !(bad.get(key)?.mag >= excess)) bad.set(key, {
      s: Math.round(s), x: head.point.x, y: -head.point.z, side, mag: excess,
      info: `${surface.object.userData.surface === 'dtm' ? `dtm/${area(surface.object, surface.faceIndex)[2]}` : 'OSM footway'} ${(excess * 1000).toFixed(0)} mm above rail`,
    });
  }
  const places = [...bad.values()].sort((a, b) => b.mag - a.mag);
  return { calibration: calibration(game), checks: { crossingSlab: { rule: 'pedestrian-surface-below-rail', count: places.length,
                                  of: samples, missing, sections: places.sort((a, b) => a.s - b.s),
                                  places: [...places].sort((a, b) => b.mag - a.mag).slice(0, 12) } } };
}
