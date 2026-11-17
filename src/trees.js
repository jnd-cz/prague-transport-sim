// SPDX-License-Identifier: AGPL-3.0-or-later
// The trees and their fallen leaves.
import * as THREE from 'three';
import { rng } from './random.js';
import { weatherize, crownColor, crownThinning, leafTexture } from './weather.js';
import { roofIndex } from './buildings.js';
import { CELL, GROUND_SNOW, SegmentIndex, pointInRing, signedArea } from './worldMesh.js';

// Vegetation from the city register (data.geo.trees: [x, y, kind], tools/geoportal.py): 0 deciduous
// tree, 1 conifer, 2 bush or hedge, 3 plants in a container, 4 a sample along a registered tree row
// (a position on the row's line, not a surveyed tree). Trees inside a building are dropped and
// crowns shrink until they clear the facades; row samples on a carriageway are dropped too.
// Without the register, parks and woods are filled at random.
const CROWN = 2.6; // icosahedron radius of a tree crown at scale 1 (x 1.1 wide, x 1.4 tall)
export function buildTrees(group, data, ground, trackDist) {
  const r = rng(99);
  const trees = [], bushes = [], pots = [];
  const roof = roofIndex(group); // buildings are already in the group
  const under = (x, y, z) => { const h = roof(x, y); return h !== null && h > z; };
  // carriageway: the surveyed streets where they exist, else near an OSM road's centre line
  const roads = new SegmentIndex(10);
  for (const rd of data.roads) if (!rd.f && rd.c) roads.addLine(rd.p);
  const onRoad = (x, y) => {
    const t = ground.dtm?.surfaceAt(x, y);
    if (t) return t.c === 'road' || t.c === 'tram' || t.c === 'parking';
    return roads.dist(x, y) < 2.5;
  };
  // crown scale that clears the facades: shrinks until neither its rim nor its half-rim is under
  // a roof; 0 when even a small crown does not fit
  const fit = (x, y, z, k) => {
    for (; k >= 0.45; k *= 0.85) {
      const bottom = z + 5.4 * k - CROWN * 1.4 * k;
      let clear = true;
      for (const f of [1, 0.5]) for (let a = 0; a < 8 && clear; a++) {
        const rad = CROWN * 1.1 * k * f;
        clear = !under(x + Math.cos(a * Math.PI / 4) * rad, y + Math.sin(a * Math.PI / 4) * rad, bottom);
      }
      if (clear) return k;
    }
    return 0;
  };
  const real = data.geo?.trees;
  if (real) {
    const seen = new Set(); // the register and the sampled tree rows overlap: one plant per ~1.5 m cell
    for (const [x, y, kind = 0] of real) {
      const cell = `${Math.round(x / 1.5)},${Math.round(y / 1.5)}`;
      if (seen.has(cell)) continue;
      seen.add(cell);
      const z = ground.at(x, y);
      if (under(x, y, z + 1)) continue; // inside a building (courtyard trees are not under a roof)
      if (kind === 2 || kind === 3) {
        if (trackDist(x, y) < 2.2) continue;
        (kind === 2 ? bushes : pots).push([x, y, 0.8 + r() * 0.6, z]);
        continue;
      }
      if (kind === 4 && onRoad(x, y)) continue;
      // street trees next to the tracks are pruned clear of the tram and the wires
      const d = trackDist(x, y);
      if (d < 3.2) continue;
      const k = fit(x, y, z, Math.min(0.75 + r() * 0.6, (d - 1.9) / 2.86));
      if (k) trees.push([x, y, k, z]);
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
      const k = fit(x, y, z, 0.7 + r() * 0.7);
      if (k) trees.push([x, y, k, z]);
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
      const [x, y, k, z] = trees[i];
      s.set(k * 1.1 * f, k * 1.4 * f, k * 1.1 * f);
      p.set(x, z + 5.4 * k + CROWN * 1.4 * k * (f - 1) * 0.5, -y); // (a thinner crown keeps its top lower, not its bottom)
      m.compose(p, q, s);
      crown.setMatrixAt(i, m);
    };
    trees.forEach(([x, y, k, z], i) => {
      s.set(1, k, 1);
      p.set(x, z + 1.5 * k, -y);
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
