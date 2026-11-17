// SPDX-License-Identifier: AGPL-3.0-or-later
// The overhead line: the contact wire over every track and its poles.
import * as THREE from 'three';
import { CONTACT_WIRE } from './models.js';
import { FootprintIndex, SegmentIndex } from './worldMesh.js';

// Overhead line: contact wire 5.34 m over top of rail of every track, hung from Prague-style cross-span wires.
// Each span is anchored on both sides of the street: on a pole at the kerb (between the
// carriageway and the sidewalk), or on a wall rosette where a building stands close to the
// track. Where one side has no place for an anchor (a square, a junction) a single pole with
// a bracket arm carries the wires. Poles are closer together on curves.
export function buildCatenary(group, data, route, ground, trackDist) {
  const wire = [];
  for (const t of data.tracks) {
    const line = t.smooth, z = t.z;
    for (let i = 0; i < line.length - 1; i += 2) {
      const j = Math.min(line.length - 1, i + 2);
      wire.push(new THREE.Vector3(line[i][0], z[i] + CONTACT_WIRE, -line[i][1]), new THREE.Vector3(line[j][0], z[j] + CONTACT_WIRE, -line[j][1]));
    }
  }
  // vehicle carriageways (poles stand outside them) and building footprints (rosettes)
  const roads = new SegmentIndex(12);
  for (const r of data.roads) if (!r.f && !r.b) roads.addLine(r.p, r.w - 0.6);
  const houses = new FootprintIndex(data.buildings.map((b) => b.p));
  // retaining walls: surveyed ones and the synthetic walls of the track cutting
  const walls = new SegmentIndex(10);
  for (const w of data.geo?.walls || []) walls.addLine(w.p, 0.8);
  const cut = { 1: [], '-1': [] };
  for (const run of ground.walls?.runs || []) if (run.pts.length > 1) cut[run.side].push([run.pts[0].s, run.pts[run.pts.length - 1].s]);
  const cutAt = (s, side) => cut[side].some(([a, b]) => s >= a - 3 && s <= b + 3);
  const B = ground.walls?.bench ?? 7;

  // find the anchor on one side (+1 left, -1 right) of route position s
  const pole = (s, side, lat) => { const p = route.offset(s, side * lat); return { wall: false, lat, sl: side * lat, x: p.x, y: p.y }; };
  const anchor = (s, side) => {
    if (ground.profile.onBridge(s)) return pole(s, side, 8.4); // on the bridge parapet
    for (let lat = 2.4; lat <= 22; lat += 0.4) {
      const o = route.offset(s, side * lat);
      if (houses.inside(o.x, o.y)) return lat <= 16 ? { wall: true, lat: lat - 0.1, sl: side * (lat - 0.1), x: o.x, y: o.y } : null;
      // a retaining wall: the pole stands at its foot, inside the cutting
      if (walls.dist(o.x, o.y) < 0 || (lat >= B - 0.4 && cutAt(s, side))) return trackDist(o.x, o.y) > 2.2 ? pole(s, side, lat - 0.5) : null;
      if (trackDist(o.x, o.y) < 2.3 || roads.dist(o.x, o.y) < 0) continue;
      // first free spot beyond the tracks and the carriageway: the kerb
      // a facade just behind the sidewalk carries the span wire on a rosette instead
      for (let k = lat + 0.8; k <= Math.min(lat + 5.5, 16); k += 0.4) {
        const w = route.offset(s, side * k);
        if (houses.inside(w.x, w.y)) return { wall: true, lat: k - 0.1, sl: side * (k - 0.1), x: w.x, y: w.y };
      }
      const p = route.offset(s, side * (lat + 0.45));
      return { wall: false, lat: lat + 0.45, sl: side * (lat + 0.45), x: p.x, y: p.y };
    }
    return null;
  };
  const stations = [];
  for (let s = 8; s <= route.length; ) {
    const R = route.radiusAt(s);
    stations.push(s);
    s += R < 50 ? 12 : R < 100 ? 18 : R < 200 ? 25 : 32;
  }
  const poles = [], rosettes = [];
  const m = new THREE.Matrix4();
  // for the game: span positions (signals and signs hang from them or sit on their poles) and a
  // kerb finder for anything else that must stand off the carriageway
  route.catenary = [];
  route.kerbAt = (s, side) => anchor(s, side);
  for (const s of stations) {
    const z = ground.profile.height(s);
    // tracks this span crosses: ours and any parallel one within 6 m (the opposite direction)
    const tracksLat = [0];
    for (let lat = -6; lat <= 6; lat += 0.25) {
      if (Math.abs(lat) < 2) continue;
      const o = route.offset(s, lat);
      if (trackDist(o.x, o.y) < 0.15 && !tracksLat.some((l) => Math.abs(l - lat) < 1.5)) tracksLat.push(lat);
    }
    let L = anchor(s, 1), Rt = anchor(s, -1);
    if (!L && !Rt) continue;
    // a far anchor across a wide street or square, with a close one on the other side: Prague
    // uses a bracket arm from the close pole instead of a long span
    const outer = (side) => (side > 0 ? Math.max(...tracksLat) : -Math.min(...tracksLat));
    if (L && Rt) {
      const fl = L.lat - outer(1), fr = Rt.lat - outer(-1);
      if (fl > 9 && fr < 5 && !Rt.wall) L = null;
      else if (fr > 9 && fl < 5 && !L.wall) Rt = null;
    }
    // The span always hangs 6.74 m over the rails (0.4 under the pole top: 1.4 m over the contact wire), so
    // both ends are level and it carries the wire from above; a pole reaches from its foot up to
    // there however low it stands (164 of 692 spans on line 17 hung from poles on a lower street and
    // held the wire from below, up to 6 m). (deck = true: on a bridge the pole stands on the deck.)
    const top = () => z + 6.74;
    const span = [];
    if (L && Rt) span.push([L, Rt]);
    else {
      // bracket arm from the one anchor to just past the farthest track
      const a = L || Rt, side = L ? 1 : -1;
      if (a.lat > 9) continue; // too far for an arm
      const far = side > 0 ? Math.min(...tracksLat) - 0.8 : Math.max(...tracksLat) + 0.8;
      const e = route.offset(s, far);
      span.push([a, { wall: true, sl: far, x: e.x, y: e.y, end: true }]);
    }
    const cat = { s, z, L, R: Rt, span: !!(L && Rt) || tracksLat.length > 0, tracksLat, attach: [] };
    route.catenary.push(cat);
    for (const a of [L, Rt]) {
      if (!a) continue;
      if (a.wall) rosettes.push([a.x, z + 6.74, a.y]);
      else {
        const zg = ground.at(a.x, a.y, true), h = Math.max(3, z + 7.14 - zg); // (the mesh is 7.4 m)
        m.makeScale(1, h / 7.4, 1).setPosition(a.x, zg + h / 2, -a.y);
        poles.push(m.clone());
      }
    }
    for (const [a, b] of span) {
      const za = top(a), zb = b.end ? za - 0.25 : top(b);
      cat.attach.push(za - 0.4, zb - 0.4); // (read by the lints: where the span hangs)
      wire.push(new THREE.Vector3(a.x, za - 0.4, -a.y), new THREE.Vector3(b.x, zb - 0.4, -b.y));
      // droppers down to each contact wire under the span
      for (const lat of tracksLat) {
        const c = route.offset(s, lat);
        const t = (lat - a.sl) / (b.sl - a.sl || 1);
        const zs = za - 0.4 + (zb - za) * Math.max(0, Math.min(1, t));
        wire.push(new THREE.Vector3(c.x, zs, -c.y), new THREE.Vector3(c.x, z + 5.6, -c.y));
      }
    }
  }
  const poleMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.17, 7.4, 6), new THREE.MeshLambertMaterial({ color: 0x4b5a4f }), Math.max(1, poles.length));
  poles.forEach((pm, i) => poleMesh.setMatrixAt(i, pm));
  poleMesh.count = poles.length;
  const roseMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.16, 0.16, 0.12, 8).rotateX(Math.PI / 2), new THREE.MeshLambertMaterial({ color: 0x3a3a3a }), Math.max(1, rosettes.length));
  rosettes.forEach(([x, h, y], i) => { m.makeTranslation(x, h - 0.4, -y); roseMesh.setMatrixAt(i, m); });
  roseMesh.count = rosettes.length;
  const wg = new THREE.BufferGeometry().setFromPoints(wire);
  group.add(new THREE.LineSegments(wg, new THREE.LineBasicMaterial({ color: 0x222222 })), poleMesh, roseMesh);
  console.log(`catenary: ${poles.length} poles, ${rosettes.length} wall rosettes`);
}
