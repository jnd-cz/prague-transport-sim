// SPDX-License-Identifier: AGPL-3.0-or-later
// The trees and their fallen leaves.
import * as THREE from 'three';
import { rng } from './random.js';
import { weatherize, crownColor, crownThinning, leafTexture } from './weather.js';
import { roofIndex } from './buildings.js';
import { CELL, GROUND_SNOW, SegmentIndex, pointInRing, signedArea } from './worldMesh.js';

// Vegetation from the city register (data.geo.trees: [x, y, kind], tools/geoportal.py): 0 deciduous
// tree, 1 conifer, 2 bush or hedge, 3 plants in a container, 4 a sample along a registered tree row
// (a position on the row's line, not a surveyed tree). Without the register, parks and woods are filled
// at random. What the rules below decide is kept per class with its places (group.userData.treeLog, the
// lint's tree checks), #649:
// - a tree inside a building is dropped (courtyard trees are not under a roof);
// - a tree under TRACK_MIN from a track centre is dropped (the tram's body and its swing); further out a
//   crown that reaches over the tram's band starts above the wire on a bare trunk and grows taller and wider
//   than the others, an oval that arches over the track as the limes and chestnuts on Mariánské hradby do (the
//   user, 2026-11-17: "make them taller over track"; their photos of 2026-11-18: trunks bare to the wire,
//   crowns half as tall again as wide, meeting over the track);
// - a crown next to a facade is narrowed, not shrunk, and the tree dropped only when a crown CROWN_MIN wide
//   does not clear it (the user: "narrower next to buildings");
// - a row sample near a register tree is that tree again; a sample on a carriageway or a parking lot moves
//   off it to the nearest other ground within ROW_SNAP (the row lines lie up to 5 m off their trees: the
//   castle's row south of Mariánské hradby runs 2.5 m into the carriageway, its trunks 2.5 m behind the
//   kerb), else it is dropped.
const CROWN = 2.6; // icosahedron radius of a tree crown at scale 1 (x 1.1 wide, x 1.4 tall)
const TRACK_MIN = 2.2; // m from a track centre: the T3's half-width 1.25 m plus about 1 m
const TRAM_BAND = 1.6; // m from a track centre that a crown under the wire stays out of (body 1.25 m, its swing)
const WIRE_CLEAR = 6.5; // m over the rail: a crown reaching into the tram's band keeps its underside above this
const LIFT_TALL = 1.6; // a lifted crown's height over an unlifted one's (k = 1: 7.3 m -> 11.6 m, its top ~18 m over the rail)
const LIFT_WIDE = 1.2; // and its width (k = 1: 6.3 m -> 7.6 m across, over the track above the wire)
const CROWN_MIN = 0.8; // m: the narrowest crown radius next to a facade
const ROW_DUP = 4; // m: a row sample this near a register tree is that tree (the register's spacing ~8 m)
const ROW_SNAP = 5; // m: how far a row sample on a carriageway may move off it
export function buildTrees(group, data, ground, trackDist) {
  const r = rng(99);
  const trees = [], bushes = [], pots = [];
  const log = { building: [], track: [], facade: [], rowDuplicate: [], rowOnRoad: [], rowMoved: [], lifted: [], narrowed: [] };
  group.userData.treeLog = log;
  const roof = roofIndex(group); // buildings are already in the group
  const under = (x, y, z) => { const h = roof(x, y); return h !== null && h > z; };
  // carriageway: the surveyed streets where they exist, else near an OSM road's centre line (a tram strip
  // is not one: trees there answer to the track rule)
  const roads = new SegmentIndex(10);
  for (const rd of data.roads) if (!rd.f && rd.c) roads.addLine(rd.p);
  const onRoad = (x, y) => {
    const t = ground.dtm?.surfaceAt(x, y);
    if (t) return t.c === 'road' || t.c === 'parking';
    return roads.dist(x, y) < 2.5;
  };
  // the crown's width that clears the facades: narrowed until neither its rim nor its half-rim is under a
  // roof higher than its bottom; 0 when even a crown CROWN_MIN wide does not fit
  const fit = (x, y, bottom, R) => {
    for (let w = 1; R * w >= CROWN_MIN; w *= 0.85) {
      let clear = true;
      for (const f of [1, 0.5]) for (let a = 0; a < 8 && clear; a++) {
        const rad = R * w * f;
        clear = !under(x + Math.cos(a * Math.PI / 4) * rad, y + Math.sin(a * Math.PI / 4) * rad, bottom);
      }
      if (clear) return w;
    }
    return 0;
  };
  // a tree of size k: [x, y, k, z, its crown's bottom and top over z, its radius] (m: the shape any tree model
  // can take), or null
  const plant = (x, y, z, k) => {
    let R = CROWN * 1.1 * k, half = CROWN * 1.4 * k, b = 5.4 * k - half;
    let w = fit(x, y, z + b, R);
    if (w && trackDist(x, y) - R * w < TRAM_BAND) {
      const rail = ground.trackOwn?.heightAt(x, y, 10) ?? z;
      if (rail + WIRE_CLEAR - z > b) {
        b = rail + WIRE_CLEAR - z; half *= LIFT_TALL; R *= LIFT_WIDE;
        w = fit(x, y, z + b, R);
        if (w) log.lifted.push([x, y]);
      }
    }
    if (!w) { log.facade.push([x, y]); return null; }
    if (w < 1) log.narrowed.push([x, y]);
    return [x, y, k, z, b, b + 2 * half, R * w];
  };
  const real = data.geo?.trees;
  if (real) {
    // the register's trees, for the row samples that repeat them
    const reg = new Map(), cellOf = (i, j) => i * 65536 + j;
    for (const [x, y, kind = 0] of real) {
      if (kind > 1) continue;
      const k = cellOf(Math.floor(x / ROW_DUP), Math.floor(y / ROW_DUP));
      if (reg.has(k)) reg.get(k).push(x, y); else reg.set(k, [x, y]);
    }
    const nearReg = (x, y) => {
      const i0 = Math.floor(x / ROW_DUP), j0 = Math.floor(y / ROW_DUP);
      for (let i = i0 - 1; i <= i0 + 1; i++) for (let j = j0 - 1; j <= j0 + 1; j++) {
        const a = reg.get(cellOf(i, j));
        if (a) for (let n = 0; n < a.length; n += 2) if (Math.hypot(a[n] - x, a[n + 1] - y) < ROW_DUP) return true;
      }
      return false;
    };
    // the nearest ground off the carriageway within ROW_SNAP, 1 m past its edge where that is off it too
    const offRoad = (x, y) => {
      for (let rad = 0.5; rad <= ROW_SNAP; rad += 0.5) for (let a = 0; a < 16; a++) {
        const cx = Math.cos(a * Math.PI / 8), cy = Math.sin(a * Math.PI / 8);
        if (onRoad(x + cx * rad, y + cy * rad)) continue;
        const f = onRoad(x + cx * (rad + 1), y + cy * (rad + 1)) ? rad : rad + 1;
        return [x + cx * f, y + cy * f];
      }
      return null;
    };
    const seen = new Set(); // one plant per ~1.5 m cell
    for (let [x, y, kind = 0] of real) {
      if (kind === 4) {
        if (nearReg(x, y)) { log.rowDuplicate.push([x, y]); continue; }
        if (onRoad(x, y)) {
          const o = offRoad(x, y);
          if (!o) { log.rowOnRoad.push([x, y]); continue; }
          log.rowMoved.push([x, y, o[0], o[1]]);
          [x, y] = o;
          if (nearReg(x, y)) { log.rowDuplicate.push([x, y]); continue; }
        }
      }
      const cell = `${Math.round(x / 1.5)},${Math.round(y / 1.5)}`;
      if (seen.has(cell)) continue;
      seen.add(cell);
      const z = ground.at(x, y);
      if (under(x, y, z + 1)) { log.building.push([x, y]); continue; }
      if (kind === 2 || kind === 3) {
        if (trackDist(x, y) < 2.2) continue;
        (kind === 2 ? bushes : pots).push([x, y, 0.8 + r() * 0.6, z]);
        continue;
      }
      if (trackDist(x, y) < TRACK_MIN) { log.track.push([x, y]); continue; }
      // (each tree's size from its place: a rule that keeps or drops another tree does not resize this one)
      const t = plant(x, y, z, 0.75 + rng(Math.round(x * 10) * 73856093 ^ Math.round(y * 10) * 19349663)() * 0.6);
      if (t) trees.push(t);
    }
  }
  for (const g of data.green) {
    if (real && g.t !== 'wood') continue; // the city tree register covers streets and parks
    const ring = g.p;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of ring) { minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]); minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); }
    const area = Math.abs(signedArea(ring));
    const n = Math.min(400, Math.floor(area / (g.t === 'wood' ? 90 : 500)));
    for (let i = 0; i < n * 2 && trees.length < 9000; i++) {
      const x = minX + r() * (maxX - minX), y = minY + r() * (maxY - minY);
      if (!pointInRing(x, y, ring)) continue;
      if (trackDist(x, y) < 6) continue;
      const z = ground.terrain.height(x, y);
      if (under(x, y, z + 1)) continue;
      const k = 0.7 + r() * 0.7, half = CROWN * 1.4 * k, w = fit(x, y, z + 5.4 * k - half, CROWN * 1.1 * k);
      if (w) trees.push([x, y, k, z, 5.4 * k - half, 5.4 * k + half, CROWN * 1.1 * k * w]);
    }
  }
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
  // each plant's own summer green (drawn in the same order as always, so the dry look is unchanged);
  // the weather recolours them (src/weather.js: species, autumn stage, bare in winter)
  const summer = () => new THREE.Color().setHSL(0.24 + r() * 0.06, 0.35 + r() * 0.15, 0.25 + r() * 0.1);
  // (a little snow settles on the tops of the crowns: bare twigs hold little)
  const leafMat = () => weatherize(new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), { snow: 0.15 });
  const sets = []; // [mesh, plants, summer colours, first colour index, place(i, thinning)]
  const nearList = []; // [mesh, name, height at scale 1 (m)]
  if (trees.length) {
    const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(CROWN, 0), leafMat(), trees.length);
    const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.18, 0.25, 3, 5), new THREE.MeshLambertMaterial({ color: 0x5b4632 }), trees.length);
    crown.userData.trees = true; // read by the lints
    const place = (i, f) => {
      const [x, y, , z, b, t, R] = trees[i], half = (t - b) / 2;
      s.set(R * f / CROWN, half * f / CROWN, R * f / CROWN);
      p.set(x, z + b + half + half * (f - 1) * 0.5, -y); // (a thinner crown keeps its top lower, not its bottom)
      m.compose(p, q, s);
      crown.setMatrixAt(i, m);
    };
    // the trunk reaches 0.17 of the crown's height into it (3 k long under a crown at 5.4 k); a lifted crown's
    // tree is taller and its trunk thicker, by its height over 15 m (an unlifted one is 12.2 m at most)
    trees.forEach(([x, y, , z, b, t], i) => {
      const h = b + (t - b) * 0.17, th = Math.max(1, t / 15);
      s.set(th, h / 3, th);
      p.set(x, z + h / 2, -y);
      m.compose(p, q, s);
      trunk.setMatrixAt(i, m);
    });
    sets.push([crown, trees, trees.map(summer), 0, place]);
    nearList.push([crown, 'crowns', CROWN * 2.8], [trunk, 'trunks', 3]);
    group.add(crown, trunk);
  }
  // bushes and hedges: a low shrub on the ground
  if (bushes.length) {
    const bush = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 0), leafMat(), bushes.length);
    bushes.forEach(([x, y, k, z], i) => {
      s.set(k, k * 0.8, k);
      p.set(x, z + 0.55 * k, -y);
      m.compose(p, q, s);
      bush.setMatrixAt(i, m);
    });
    sets.push([bush, bushes, bushes.map(summer), 100000, null]);
    nearList.push([bush, 'bushes', 1.6]);
    group.add(bush);
  }
  // plants in containers: a concrete planter with a small shrub
  if (pots.length) {
    const pot = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.6, 1), weatherize(new THREE.MeshLambertMaterial({ color: 0x9a968c }), { snow: GROUND_SNOW }), pots.length);
    const shrub = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.55, 0), leafMat(), pots.length);
    pots.forEach(([x, y, , z], i) => {
      p.set(x, z + 0.3, -y); s.set(1, 1, 1);
      m.compose(p, q, s);
      pot.setMatrixAt(i, m);
      p.set(x, z + 0.95, -y);
      m.compose(p, q, s);
      shrub.setMatrixAt(i, m);
    });
    sets.push([shrub, pots, pots.map(summer), 200000, null]);
    nearList.push([pot, 'planters', 0.6], [shrub, 'planter shrubs', 1.1]);
    group.add(pot, shrub);
  }
  const litter = buildLeafLitter(group, trees, ground, trackDist, onRoad);
  const col = new THREE.Color();
  const setWeather = (w) => {
    for (const [mesh, plants, greens, i0, place] of sets) {
      for (let i = 0; i < plants.length; i++) {
        mesh.setColorAt(i, crownColor(i0 + i, w, greens[i], col));
        if (place) place(i, crownThinning(i0 + i, w));
      }
      mesh.instanceColor.needsUpdate = true;
      mesh.instanceMatrix.needsUpdate = true;
    }
    for (const l of litter) l.visible = w === 'leaves';
  };
  setWeather('dry');
  // drawn near the camera only, by their height at a crown of scale 1 (src/nearbatch.js, #610); after the first
  // colouring, so the kept instances carry it
  const near = group.userData.near;
  if (near) for (const [o, name, size] of nearList) near.add(o, name, size);
  return { setWeather };
}

// Fallen leaves under the trees in autumn: flat patches of a leaf texture (alpha cut out) around each
// crown, more under bigger trees; few on carriageways (traffic blows them away), none on the tracks.
// One instanced mesh per CELL square, so far ones are culled. Hidden unless the weather is 'leaves'.
function buildLeafLitter(group, trees, ground, trackDist, onRoad) {
  const r = rng(4242);
  const cells = new Map();
  for (const [x, y, k] of trees) {
    const R = CROWN * 1.3 * k, n = Math.round(6 + k * 8);
    for (let j = 0; j < n; j++) {
      const a = r() * Math.PI * 2, d = Math.sqrt(r()) * R;
      const px = x + Math.cos(a) * d, py = y + Math.sin(a) * d;
      if (trackDist(px, py) < 2) continue;
      if (onRoad(px, py) && r() < 0.75) continue;
      const key = `${Math.floor(px / CELL)},${Math.floor(py / CELL)}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key).push([px, py, 2 + r() * 2.2, r() * Math.PI * 2, 0.85 + r() * 0.3]);
    }
  }
  const geo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const mat = new THREE.MeshLambertMaterial({ map: leafTexture(), alphaTest: 0.5, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0), col = new THREE.Color();
  const out = [];
  for (const list of cells.values()) {
    const mesh = new THREE.InstancedMesh(geo, mat, list.length);
    list.forEach(([x, y, size, rot, light], i) => {
      p.set(x, ground.at(x, y) + 0.03, -y);
      q.setFromAxisAngle(up, rot);
      s.set(size, 1, size);
      m.compose(p, q, s);
      mesh.setMatrixAt(i, m);
      mesh.setColorAt(i, col.setScalar(light));
    });
    mesh.computeBoundingSphere();
    mesh.visible = false;
    group.add(mesh);
    out.push(mesh);
  }
  return out;
}
