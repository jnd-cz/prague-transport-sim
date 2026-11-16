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

// The decoded ground: { meshes, lookup: GroundLookup, times }. `styles[class][draw name]` = [group, r, g, b].
export function decodeGround(file, styles) {
  return new Promise((resolve, reject) => {
    const w = new Worker(new URL('./groundWorker.js', import.meta.url), { type: 'module' });
    w.onmessage = ({ data }) => { w.terminate(); resolve({ meshes: data.meshes, lookup: new GroundLookup(data.lookup), times: data.times }); };
    w.onerror = (e) => { w.terminate(); reject(e); };
    w.postMessage({ buffer: file.buffer, layout: file.layout, styles, chunk: GROUND_CHUNK, cell: LOOKUP_CELL }, [file.buffer]);
  });
}

// The drawn ground's height at (x, y): the triangle holding the point (the highest where several do: a kerb's top at
// its edge), its plane there; null off the ground.
export class GroundLookup {
  constructor(lk) { Object.assign(this, lk); }
  height(x, y) {
    const px = x - this.x0, py = y - this.y0, i = Math.floor(px / this.cell), j = Math.floor(py / this.cell);
    if (i < 0 || j < 0 || i >= this.nx || j >= this.ny) return null;
    const { vx, vy, vz, tv, tris } = this, k = j * this.nx + i;
    let best = null;
    for (let s = this.start[k], e = this.start[k + 1]; s < e; s++) {
      const t = 3 * tris[s], a = tv[t], b = tv[t + 1], c = tv[t + 2];
      const ax = vx[a], ay = vy[a], bx = vx[b], by = vy[b], cx = vx[c], cy = vy[c];
      const d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (!d) continue;
      const w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d, w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d;
      const w2 = 1 - w0 - w1, eps = -1e-7;
      if (w0 < eps || w1 < eps || w2 < eps) continue;
      const z = w0 * vz[a] + w1 * vz[b] + w2 * vz[c];
      if (best === null || z > best) best = z;
    }
    return best;
  }
}
