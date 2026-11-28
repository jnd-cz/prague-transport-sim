// SPDX-License-Identifier: AGPL-3.0-or-later
// The streets the survey does not draw: OSM's carriageways and footways as ribbons, the zebras, and the street
// detail near the track (the tram streets widened to hold their tracks first).
import * as THREE from 'three';
import { yaw } from './features.js';
import { weatherize, wetFactor } from './weather.js';
import { ChunkedGeometry, FOOT_SNOW, STREET_SNOW, SegmentIndex, W, addRibbon, densify, flatMat } from './worldMesh.js';

// OSM `lanes` (and so our width estimate) counts only the car lanes, but in Prague the tram
// tracks usually run down the middle of the same street. Widen such roads by the track zone
// (3.2 m per track) and flag them, so asphalt, kerbs (poles) and car lanes sit beside the tracks.
export function widenTramStreets(data) {
  const idx = new SegmentIndex(10);
  for (const t of data.tracks) idx.addLine(t.p);
  for (const r of data.roads) {
    if (r.f || r.w < 5 || r.p.length < 2) continue;
    let n = 0, near = 0, both = 0;
    const pts = densify(r.p, 5);
    pts.forEach(([x, y], i) => {
      n++;
      if (idx.dist(x, y) < 2.6) near++;
      // tracks on both sides of the centre line = double track
      const a = pts[Math.max(0, i - 1)], c = pts[Math.min(pts.length - 1, i + 1)];
      const hx = c[0] - a[0], hy = c[1] - a[1], hl = Math.hypot(hx, hy) || 1, ox = (-hy / hl) * 1.6, oy = (hx / hl) * 1.6;
      if (idx.dist(x + ox, y + oy) < 0.8 && idx.dist(x - ox, y - oy) < 0.8) both++;
    });
    if (near / n < 0.6) continue;
    r.tram = both / n > 0.3 ? 2 : 1;
    r.w += 3.2 * r.tram;
  }
}

// Height function for an OSM way: bridges not on our route span linearly between their ends.
// (the same function the cars and walkers on a bridge stand on: ground.way)
export function wayHeight(line, isBridge, ground) {
  return ground.way(line, isBridge);
}

// Pieces of a polyline outside the DTM-surveyed streets (densified at 3 m); for a way on a bridge
// (height function hf) outside the surveyed decks at its height.
export function uncoveredRuns(line, dtm, hf = null) {
  const pts = densify(line, 3), runs = [];
  let cur = [];
  for (const p of pts) {
    if ((hf ? dtm.deckAt(p[0], p[1], hf(p[0], p[1]) + 0.1, 1) : dtm.heightAt(p[0], p[1])) === null) cur.push(p);
    else { if (cur.length > 1) runs.push(cur); cur = []; }
  }
  if (cur.length > 1) runs.push(cur);
  return runs;
}

// OSM's roads and footways as ribbons where the survey has no street (on a bridge: where it has no deck at the way's
// height), and the road tunnels buildWorld draws inside (`tunnelRoads`)
export function buildRoads(group, data, ground, trackDist, pedestrianCrossings, tunnelRoads) {
  // roads (wider first so footways draw on top)
  const roadsCg = new ChunkedGeometry(flatMat('#55565a', '#3e3f43'), { color: true });
  const footCg = new ChunkedGeometry(flatMat('#a39d90', '#86817a', FOOT_SNOW), { color: true });
  const asphalt = new THREE.Color('#55565a').toArray(), paving = new THREE.Color('#a39d90').toArray();
  const roadIds = new Map(data.roads.map((r, i) => [r, i]));
  const keepRoadRanges = /[?&](keepgeo|bot)\b/.test(location.search);
  for (const r of [...data.roads].sort((a, b) => b.w - a.w)) {
    if (keepRoadRanges) footCg.sourceId = roadIds.get(r);
    if (r.z) continue; // painted crossings: zebra stripes below, the asphalt shows through
    if (r.t) continue; // (road tunnels: above)
    // where the surveyed DTM streets exist, they replace the OSM ribbons (on a bridge: its deck)
    const runs = ground.dtm ? uncoveredRuns(r.p, ground.dtm, r.b ? wayHeight(r.way || r.p, true, ground) : null) : [r.p];
    // (a bridge spans between the ends of the whole way, not of the piece drawn)
    const hf = r.b ? wayHeight(r.way || r.p, true, ground) : null;
    // (a street with tracks in it, or crossing them: strips across, so the middle follows the track level)
    for (const run of runs) {
      const across = r.tram || (r.w > 3 && run.some(([x, y]) => trackDist(x, y) < 8));
      const height = hf || wayHeight(run, false, ground), lift = r.f ? 0.16 : 0.12;
      const crossing = r.f ? pedestrianCrossings.footway(run, r.w, height, lift, r.n || null) : null;
      addRibbon(r.f ? footCg : roadsCg, crossing ? densify(run, 0.2) : run, r.w, crossing || height, lift, r.f ? paving : asphalt, 0,
        crossing ? Math.ceil(r.w / 0.2) : across ? Math.ceil(r.w / 2) : 1);
    }
  }
  footCg.sourceId = undefined;
  // (road tunnels: no snow inside)
  const tunnelCg = new ChunkedGeometry(flatMat('#55565a', '#3e3f43', 0), { color: true });
  for (const { r, inside, tf } of tunnelRoads) addRibbon(tunnelCg, inside, r.w, tf, 0.12, asphalt);
  roadsCg.build(group, 'road');
  footCg.build(group, 'road', 'footway');
  tunnelCg.build(group, 'road');
}

// Pedestrian crossings with zebra paint: 0.5 m bars every metre along the crossing, each
// 3 m long across the walking direction. No paint on the tram tracks (as in Prague).
export function buildZebras(group, data, ground, trackDist) {
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { wet: wetFactor('#e9e9e4', '#c9cbcc'), snow: STREET_SNOW, slush: true }), { color: true });
  const white = new THREE.Color('#e9e9e4').toArray();
  // and the OSM signalled crossings (data.osmSignals.peds) without a zebra way of their own: across the
  // nearest car road, kerb to kerb (Palackého náměstí: the two crossings from the island over the road
  // had no paint, the maintainer's orthophoto reading 2026-10-24)
  const ways = data.roads.filter((r) => r.z).map((r) => ({ p: r.p }));
  const segDist = (P, x, y) => { let m = Infinity; for (let i = 1; i < P.length; i++) { const a = P[i - 1], b = P[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9, t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)); m = Math.min(m, Math.hypot(a[0] + dx * t - x, a[1] + dy * t - y)); } return m; };
  for (const o of data.osmSignals?.peds || []) {
    if (ways.some((w) => segDist(w.p, o.x, o.y) < 4)) continue;
    let best = null;
    for (const r of data.roads) {
      if (!r.c || r.f || r.t || !(r.w >= 5)) continue;
      const P = r.p;
      for (let i = 1; i < P.length; i++) {
        const a = P[i - 1], b = P[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((o.x - a[0]) * dx + (o.y - a[1]) * dy) / l2)), d = Math.hypot(a[0] + dx * t - o.x, a[1] + dy * t - o.y);
        if (d < 6 && (!best || d < best.d)) { const l = Math.sqrt(l2); best = { d, hx: dx / l, hy: dy / l, half: r.w / 2 }; }
      }
    }
    if (!best) continue;
    const cx = -best.hy, cy = best.hx;
    ways.push({ p: [[o.x - cx * best.half, o.y - cy * best.half], [o.x + cx * best.half, o.y + cy * best.half]], osm: true });
  }
  for (const r of ways) {
    const path = densify(r.p, 0.5);
    let acc = 0;
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1], b = path[i];
      const l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
      acc += l;
      if (acc % 1.0 > 0.5 || acc < 0.4) continue; // stripe on the first half of each metre
      const hx = (b[0] - a[0]) / l, hy = (b[1] - a[1]) / l, nx = -hy * 1.5, ny = hx * 1.5;
      const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
      if (trackDist(cx, cy) < 1.75 || trackDist(cx + nx, cy + ny) < 1.6 || trackDist(cx - nx, cy - ny) < 1.6) continue;
      const q = [[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]]
        .map(([x, y]) => W(x, y, ground.at(x, y) + 0.135));
      cg.quad(cg._chunk(cx, cy), q[3], q[2], q[1], q[0], white);
    }
  }
  cg.build(group);
}

// Street detail from the feature layer (data.features, src/features.js; the archive survey's points, CC BY,
// datový podklad © IPR Praha): manhole covers and valve caps as flat discs on the drawn ground, gutter
// inlets as grates turned by their heading (the nearest street's, tools/features.py), above-ground hydrants as
// small red posts. One instanced mesh per kind for the whole line (a few thousand instances: a few draw calls).
export function buildStreetDetail(data, ground, near = null) {
  const group = new THREE.Group();
  const feats = data.features;
  const flat = (geo) => geo.rotateX(-Math.PI / 2);
  const iron = (c) => weatherize(new THREE.MeshLambertMaterial({ color: c, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }), { wet: 0.6 });
  const kinds = {
    // (size: the width of a flat one, the height of the hydrant, for the distance it is drawn to, src/nearbatch.js)
    manhole: { geo: flat(new THREE.CircleGeometry(0.32, 14)), mat: iron(0x3a3a3c), turn: false, size: 0.64 },
    // (caps smaller than first drawn, maintainer, 2026-10-24; reference photos of all the covers to come)
    hydrant_cap: { geo: flat(new THREE.CircleGeometry(0.1, 10)), mat: iron(0x4a3a30), turn: false, size: 0.2 },
    valve_cap: { geo: flat(new THREE.CircleGeometry(0.06, 8)), mat: iron(0x3d3d3d), turn: false, size: 0.12 },
    gutter_inlet: { geo: flat(new THREE.PlaneGeometry(0.62, 0.36)), mat: iron(0x242424), turn: true, size: 0.5 },
    hydrant: { geo: new THREE.CylinderGeometry(0.11, 0.14, 0.85, 8).translate(0, 0.42, 0), mat: new THREE.MeshLambertMaterial({ color: 0x9c1d16 }), turn: false, size: 0.85, upright: true },
  };
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  for (const [k, def] of Object.entries(kinds)) {
    const list = feats.of(k);
    if (!list.length) continue;
    const mesh = new THREE.InstancedMesh(def.geo, def.mat, list.length);
    mesh.userData.mirrorDetail = k !== 'hydrant'; // flat covers/grates do not resolve in the small rear view
    list.forEach((o, i) => {
      // (a grate lies by its heading, flat where it has none; a round cover's turn is its place's, any will do)
      q.setFromAxisAngle(up, def.turn ? (o.heading === undefined ? 0 : yaw(o.heading)) : (o.x * 7.3 + o.y * 3.1) % (Math.PI * 2));
      // (between the rails on the paved track bed, which is drawn above the street's height: most covers
      // at Strossmayerovo náměstí lie in the track and were hidden under it)
      const onTrack = ground.trackDist && ground.trackDist(o.x, o.y) < 1.8 && ground.trackAt;
      p.set(o.x, Math.max(ground.surface(o.x, o.y), onTrack ? ground.trackAt(o.x, o.y) + 0.16 : -Infinity) + 0.015, -o.y);
      m.compose(p, q, s);
      mesh.setMatrixAt(i, m);
    });
    mesh.computeBoundingSphere();
    if (near) near.add(mesh, k, def.size, !def.upright);
    group.add(mesh);
  }
  group.userData.counts = Object.fromEntries(Object.keys(kinds).map((k) => [k, feats.count(k)]));
  return group;
}
