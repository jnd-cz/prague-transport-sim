// Rendered pedestrian surfaces above rail heads, grouped in 20 m route sections (#146).
// On a running shift loaded with ?keepgeo: (await import('/tools/bench/crossingSlab.js')).run()
import * as THREE from 'three';

export function run() {
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
    const ranges = mesh.userData.surfaceRanges || [];
    let lo = 0, hi = ranges.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (ranges[mid][0] <= face) lo = mid + 1; else hi = mid; }
    const r = ranges[lo - 1];
    return r && face < r[1] && walkway.has(r[2]) ? r : null;
  };
  // A 5 m survey triangle crossing a rail has its centroid within 6 m of the route. Its projected
  // position and neighbours bound the samples to inspect, including long diagonal crossings.
  const bins = new Set();
  for (const mesh of footways) {
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
    const surface = ray.intersectObjects(footways, false).find((h) => {
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
  return { checks: { crossingSlab: { rule: 'pedestrian-surface-below-rail', count: places.length,
                                  of: samples, missing, sections: places.sort((a, b) => a.s - b.s),
                                  places: [...places].sort((a, b) => b.mag - a.mag).slice(0, 12) } } };
}
