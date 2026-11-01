// Dev overlay (?debug, toggled with F8): markers for what the signal and traffic logic decided, drawn
// over everything (no depth test). Rebuilt on each toggle (the data does not move during a shift).
//   magenta ball / bar   tram signal head / where the tram stops for it (s − 3)
//   cyan / yellow bar    car stop line from an OSM node / at the computed junction edge (white: short lane)
//   yellow ball          car signal head
//   red dot              raw OSM stop-line node (data.osmSignals.stop)
//   white bar            conflict on the route (street, footway or crossing): its near edge
//   green bars / ball    platform start and end / where the tram front stops for passengers
import * as THREE from 'three';
import { buildHeightReview } from './heightReview.js';

// What the rules decided at run time, as the compiled-world GeoJSON of docs/architecture.md §10.4
// In S-JTSK (EPSG:5514): game metres plus the city origin (data.frame, docs/decisions/2026-10-29-city-frame-and-tiles.md).
// From the console during a shift: window.exportBuiltGeoJSON() saves data-lineN.built.geojson.
export function builtGeoJSON(game, traffic) {
  const [e0, n0] = game.data.frame.origin;
  const ll = (x, y) => [+(e0 + x).toFixed(2), +(n0 + y).toFixed(2)];
  const R = game.route, line = String(game.data.line), out = [];
  const feat = (geometry, p) => out.push({ type: 'Feature', geometry, properties: { line, ...p } });
  const pt = (x, y) => ({ type: 'Point', coordinates: ll(x, y) });
  const across = (s, half = 1.6) => { const q = R.at(s); return { type: 'LineString', coordinates: [ll(q.x + q.hy * half, q.y - q.hx * half), ll(q.x - q.hy * half, q.y + q.hx * half)] }; };
  const v = new THREE.Vector3(), worldPt = (o) => { o.getWorldPosition(v); return pt(v.x, -v.z); };
  const r1 = (s) => Math.round(s * 10) / 10;
  for (const st of game.stops) {
    const q = R.at(st.target);
    feat(pt(q.x, q.y), { id: `tram_stop_point:${line}:${st.name}`, type: 'tram_stop_point', stop: st.name, s: r1(st.target) });
    if (st.sign) feat(worldPt(st.sign), { id: `stop_post:${line}:${st.name}`, type: 'stop_post', stop: st.name, s: r1(st.target) });
  }
  for (const sg of game.signals) {
    const id = `tram_signal:${line}:sig@${Math.round(sg.s0 ?? sg.s)}`;
    feat(worldPt(sg.mesh), { id, type: 'tram_signal', s: r1(sg.s), stopAt: r1(sg.s - 3), mount: sg.head ? 'platform_head' : sg.mesh.userData.hung ? 'span' : 'kerb', rule: sg.demand ? 'onDemand' : sg.head ? 'platformEnd' : 'junctionEdge' });
    feat(across(sg.s - 3), { id: `tram_signal_stop:${line}:sig@${Math.round(sg.s0 ?? sg.s)}`, type: 'tram_signal_stop', signal: id, s: r1(sg.s - 3) });
  }
  for (const c of game._routeConflicts()) { const q = R.at(c.start); feat(pt(q.x, q.y), { id: `conflict:${line}:@${Math.round(c.start)}`, type: 'conflict', s: r1(c.start), car: c.car }); }
  if (traffic) {
    for (const l of traffic.lightLanes || []) {
      const q = l.path.at(l.path.length - l.light.back), a = ll(q.x + q.hy * 1.5, q.y - q.hx * 1.5), b = ll(q.x - q.hy * 1.5, q.y + q.hx * 1.5);
      feat({ type: 'LineString', coordinates: [a, b] }, { id: `car_stop_line:${line}:lane${l.id}`, type: 'car_stop_line', heading: Math.round((Math.atan2(q.hx, q.hy) * 180) / Math.PI + 360) % 360, junction: `sig@${Math.round(l.light.sig.cross)}`, source: l.light.src, rule: l.light.src === 'osm' ? 'osmNode' : l.light.src });
    }
    const heads = traffic.lights?.group.children[0], M = new THREE.Matrix4();
    for (let i = 0; heads && i < heads.count; i++) { heads.getMatrixAt(i, M); v.setFromMatrixPosition(M); feat(pt(v.x, -v.z), { id: `car_signal_head:${line}:${i}`, type: 'car_signal_head' }); }
  }
  return { type: 'FeatureCollection', crs: { type: 'name', properties: { name: 'urn:ogc:def:crs:EPSG::5514' } }, properties: { line, build: `runtime ${new Date().toISOString().slice(0, 10)}`, origin: [e0, n0] }, features: out };
}

export function createDebugOverlay(scene) {
  let group = null;
  const mats = {};
  const mat = (c) => (mats[c] ||= new THREE.MeshBasicMaterial({ color: c, depthTest: false, transparent: true, opacity: 0.9 }));
  const geo = { ball: new THREE.SphereGeometry(0.9, 10, 8), dot: new THREE.SphereGeometry(0.6, 8, 6), bar: new THREE.BoxGeometry(3, 0.2, 0.6), wide: new THREE.BoxGeometry(5, 0.25, 0.6) };

  function build(game, traffic) {
    const g = new THREE.Group(), R = game.route, P = game.profile;
    const add = (shape, color, x, y, z, ry = 0) => { const m = new THREE.Mesh(geo[shape], mat(color)); m.position.set(x, y, z); m.rotation.y = ry; m.renderOrder = 999; g.add(m); };
    const across = (s, shape, color, lift = 0.3) => { const q = R.at(s); add(shape, color, q.x, P.height(s) + lift, -q.y, Math.atan2(-q.hx, q.hy)); };
    for (const s of game.signals) {
      const p = new THREE.Vector3();
      s.mesh.getWorldPosition(p);
      add('ball', 0xff00ff, p.x, p.y + 1.5, p.z);
      across(s.s - 3, 'wide', 0xff00ff);
    }
    for (const c of game._routeConflicts()) across(c.start, 'wide', 0xffffff, 0.15);
    for (const st of game.stops) {
      if (st.p0 !== undefined) { across(st.p0, 'wide', 0x22cc55, 0.5); across(st.p1, 'wide', 0x22cc55, 0.5); }
      const q = R.at(st.target);
      add('ball', 0x22cc55, q.x, P.height(st.target) + 2.5, -q.y);
    }
    if (traffic) {
      const surf = (x, y) => traffic.ground.surface(x, y);
      for (const l of traffic.lightLanes || []) {
        const q = l.path.at(l.path.length - l.light.back);
        add('bar', l.light.src === 'osm' ? 0x00ffff : l.light.src === 'short' ? 0xffffff : 0xffee00, q.x, surf(q.x, q.y) + 0.3, -q.y, Math.atan2(-q.hx, q.hy));
      }
      const heads = traffic.lights?.group.children[0], M = new THREE.Matrix4(), v = new THREE.Vector3();
      for (let i = 0; heads && i < heads.count; i++) { heads.getMatrixAt(i, M); v.setFromMatrixPosition(M); add('ball', 0xffee00, v.x, v.y + 3.2, v.z); }
      for (const o of game.data.osmSignals?.stop || []) add('dot', 0xff2020, o.x, surf(o.x, o.y) + 1, -o.y);
    }
    const heights = buildHeightReview(game);
    if (heights) g.add(heights);
    return g;
  }

  return {
    get on() { return !!group; },
    toggle(game, traffic) {
      if (group) { group.traverse((o) => o.userData.dispose?.()); scene.remove(group); group = null; return false; }
      if (!game) return false;
      group = build(game, traffic);
      scene.add(group);
      return true;
    },
    // a new shift (new game / traffic objects): drop the old markers
    reset() { if (group) { group.traverse((o) => o.userData.dispose?.()); scene.remove(group); group = null; } },
  };
}
