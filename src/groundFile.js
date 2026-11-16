// SPDX-License-Identifier: AGPL-3.0-or-later
// The prebuilt ground (data/lineN.ground.bin + .json, tools/ground_mesh.py, #508): fetched with the line's files,
// decoded in a worker (src/groundWorker.js), drawn by src/world.js buildGroundFile, and its height lookup: one index
// of the drawn triangles that cars, walkers, stops, kerbs, the camera and the lints read (#509).

export const GROUND_CHUNK = 350; // m: the meshes' squares, as world.js CELL (frustum culling skips far ones)
export const LOOKUP_CELL = 16; // m: the lookup's grid

// The file, or null where the line has none (or ?oldground: the layers the page built before #509, for comparing).
export async function fetchGround(load, lineId, params) {
  if (params?.has('oldground')) return null;
  try {
    const [jr, br] = await Promise.all([load.get(`data/line${lineId}.ground.json`), load.get(`data/line${lineId}.ground.bin`)]);
    if (!jr.ok || !br.ok) return null;
    return { layout: await jr.json(), buffer: await br.arrayBuffer() };
  } catch {
    return null;
  }
}

// The decoded ground: { lookup: a promise of the GroundLookup, meshes: a promise of { meshes, times } }; the lookup
// comes first (src/groundWorker.js). `styles[class][draw name]` = [group, r, g, b].
export function decodeGround(file, styles) {
  const w = new Worker(new URL('./groundWorker.js', import.meta.url), { type: 'module' });
  let got, fail, done, failMeshes;
  const lookup = new Promise((res, rej) => { got = res; fail = rej; });
  const meshes = new Promise((res, rej) => { done = res; failMeshes = rej; });
  w.onmessage = ({ data }) => {
    if (data.lookup) { got(new GroundLookup(data.lookup)); return; }
    w.terminate();
    done({ meshes: data.meshes, times: data.times });
  };
  w.onerror = (e) => { w.terminate(); fail(e); failMeshes(e); };
  w.postMessage({ buffer: file.buffer, layout: file.layout, styles, chunk: GROUND_CHUNK, cell: LOOKUP_CELL }, [file.buffer]);
  meshes.catch(() => {}); // (one failure, reported through the lookup's promise)
  return { lookup, meshes };
}

// The drawn ground at (x, y): the triangle holding the point (the highest where several do: a kerb's top at its edge),
// its plane's height there and the survey's class under it (src/terrain.js DtmSurface asks it for its ground level).
export class GroundLookup {
  constructor(lk) {
    Object.assign(this, lk);
    this.coverSet = new Set(lk.cover);
    this.hitZ = 0;
  }
  // (the triangle, its height in this.hitZ; -1 off the ground)
  _find(x, y) {
    const px = x - this.x0, py = y - this.y0, i = Math.floor(px / this.cell), j = Math.floor(py / this.cell);
    if (i < 0 || j < 0 || i >= this.nx || j >= this.ny) return -1;
    const { vx, vy, vz, tv, tris } = this, k = j * this.nx + i;
    let best = -1, bz = 0;
    for (let s = this.start[k], e = this.start[k + 1]; s < e; s++) {
      const t = 3 * tris[s], a = tv[t], b = tv[t + 1], c = tv[t + 2];
      const ax = vx[a], ay = vy[a], bx = vx[b], by = vy[b], cx = vx[c], cy = vy[c];
      const d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (!d) continue;
      const w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d, w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d;
      const w2 = 1 - w0 - w1, eps = -1e-7;
      if (w0 < eps || w1 < eps || w2 < eps) continue;
      const z = w0 * vz[a] + w1 * vz[b] + w2 * vz[c];
      if (best < 0 || z > bz) { best = tris[s]; bz = z; }
    }
    this.hitZ = bz;
    return best;
  }
  height(x, y) { return this._find(x, y) < 0 ? null : this.hitZ; }
  // the survey at (x, y): { z, c } (its class: 'road', 'sidewalk', …), null where the ground is not the survey's
  survey(x, y) {
    const t = this._find(x, y);
    return t < 0 || !this.ta[t] ? null : { z: this.hitZ, c: this.areas[this.ta[t]] };
  }
  // whether the survey describes the street in (x, y)'s 10 m cell at all (src/terrain.js TriIndex.covered)
  covered(x, y) { return this.coverSet.has(Math.floor(x / 10) * 100003 + Math.floor(y / 10)); }
}
