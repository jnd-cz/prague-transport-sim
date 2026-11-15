// SPDX-License-Identifier: AGPL-3.0-or-later
// Small things drawn only near the camera (#610): an instanced mesh of the whole line (covers, grates, hydrants,
// trees) keeps every instance, and draws those within its range, refilled as the camera moves. One draw call
// as before, without the line's far instances: the trees were 294 k triangles in every view at Spojovací
// (line 37), most of them out of view or past the fog.
// The range comes from the thing's size on screen, the user's rule (2026-11-15): "hide the small things far away".
// Upright things (a hydrant, a crown) go when they would stand under UPRIGHT_PX pixels tall; flat ones on the
// ground (a manhole cover) are seen at a grazing angle from the cab's eye EYE m up, their height on screen
// size * EYE / d^2, and go under FLAT_PX. Nothing is drawn past the fog's end. The zoom key and a larger
// screen give finer pixels, so longer ranges.
import * as THREE from 'three';

const _s = new THREE.Sphere(), _m = new THREE.Matrix4();
const GRID = 50;        // m: the cells the instances are sorted into
const UPRIGHT_PX = 1.5, FLAT_PX = 0.25, EYE = 3;
const REFILL = 0.1;     // refill once the camera has moved this share of the range (the fill reaches 1 + REFILL of it)

export class NearBatches {
  constructor() {
    this.sets = [];
    this.log = {}; // name -> { range, drawn, total }: what each rule left out (window.nearBatches, the debug overlay)
  }

  // mesh: a built InstancedMesh with every instance set; size (m): the height of an upright thing, the width of a
  // flat one. Later setMatrixAt / setColorAt calls (the weather recolouring the crowns) change the kept instances.
  add(mesh, name, size, flat = false) {
    const total = mesh.count, M = new Float32Array(mesh.instanceMatrix.array);
    const set = { mesh, name, size, flat, total, M, C: mesh.instanceColor ? new Float32Array(mesh.instanceColor.array) : null,
      cells: new Map(), at: null, range: 0, dirty: true };
    for (let i = 0; i < total; i++) {
      const k = `${Math.floor(M[i * 16 + 12] / GRID)},${Math.floor(M[i * 16 + 14] / GRID)}`;
      if (!set.cells.has(k)) set.cells.set(k, []);
      set.cells.get(k).push(i);
    }
    mesh.setMatrixAt = (i, m) => { m.toArray(set.M, i * 16); set.dirty = true; };
    mesh.getMatrixAt = (i, m) => m.fromArray(set.M, i * 16);
    mesh.setColorAt = (i, c) => {
      if (!set.C) set.C = new Float32Array(total * 3).fill(1);
      c.toArray(set.C, i * 3); set.dirty = true;
    };
    mesh.userData.total = total; // (every instance, drawn or not: tools/lint.js reads them all)
    mesh.count = 0;
    this.sets.push(set);
    return mesh;
  }

  // before a draw: camera (its position, vertical field), the drawn picture's height (px), the fog's end (m);
  // true when a set was refilled (a cached picture, the mirror's, is out of date)
  update(camera, heightPx, fogFar) {
    let refilled = false;
    const px = (camera.fov * Math.PI) / 180 / camera.zoom / Math.max(1, heightPx); // rad per pixel
    const cx = camera.position.x, cz = camera.position.z;
    for (const s of this.sets) {
      const range = Math.min(fogFar, s.flat ? Math.sqrt((s.size * EYE) / (px * FLAT_PX)) : s.size / (px * UPRIGHT_PX));
      const moved = s.at ? Math.hypot(cx - s.at[0], cz - s.at[1]) : Infinity;
      if (!s.dirty && moved < range * REFILL && Math.abs(range - s.range) < range * REFILL) continue;
      this.fill(s, cx, cz, range);
      refilled = true;
    }
    return refilled;
  }

  fill(s, cx, cz, range) {
    const { mesh, M, C } = s, reach = range * (1 + REFILL), r2 = reach * reach;
    const dm = mesh.instanceMatrix.array;
    if (C && !mesh.instanceColor) mesh.instanceColor = new mesh.instanceMatrix.constructor(new Float32Array(s.total * 3), 3);
    const dc = mesh.instanceColor?.array;
    let n = 0;
    const g0 = Math.floor((cx - reach) / GRID), g1 = Math.floor((cx + reach) / GRID);
    const h0 = Math.floor((cz - reach) / GRID), h1 = Math.floor((cz + reach) / GRID);
    for (let gx = g0; gx <= g1; gx++) for (let gz = h0; gz <= h1; gz++) {
      const list = s.cells.get(`${gx},${gz}`);
      if (!list) continue;
      for (const i of list) {
        const dx = M[i * 16 + 12] - cx, dz = M[i * 16 + 14] - cz;
        if (dx * dx + dz * dz > r2) continue;
        dm.set(M.subarray(i * 16, i * 16 + 16), n * 16);
        if (C && dc) dc.set(C.subarray(i * 3, i * 3 + 3), n * 3);
        n++;
      }
    }
    mesh.count = n;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    // (none in range: an empty sphere, which the frustum test skips; visibility stays the other switches', review mode's
    // and the mirror's)
    // (three's computeBoundingSphere reads the instances through getMatrixAt, which reads the kept ones here: the
    // sphere of the drawn ones is made from the drawn buffer)
    const g = mesh.geometry;
    if (!g.boundingSphere) g.computeBoundingSphere();
    const bs = (mesh.boundingSphere ||= new THREE.Sphere()).makeEmpty();
    if (!n) bs.radius = -1;
    for (let i = 0; i < n; i++) bs.union(_s.copy(g.boundingSphere).applyMatrix4(_m.fromArray(dm, i * 16)));
    s.at = [cx, cz]; s.range = range; s.dirty = false;
    this.log[s.name] = { range: Math.round(range), drawn: n, total: s.total };
  }
}
