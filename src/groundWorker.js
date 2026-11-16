// SPDX-License-Identifier: AGPL-3.0-or-later
// The ground file's decoder (tools/ground_mesh.py encode, #508, #509), in a worker so the page's thread keeps drawing
// the loading screen (the tile container's decision: docs/decisions/2026-11-06-tile-container.md).
//
// In: { buffer, layout, styles, chunk, cell } — `styles[class][draw name]` = [group, r, g, b] (src/groundFile.js).
// Out: { meshes: [{ group, pos, nor, col, idx }], lookup: { x0, y0, cell, nx, ny, start, tris, vx, vy, vz, tv } }:
// per CHUNK m square and material group an indexed geometry (positions as three.js takes them: x, z, -y), each
// draw class with its own vertices so colours do not blend across a class's edge, the normals averaged over its
// triangles; and the height lookup: the flat triangles (the steps' walls left out) in a grid of `cell` m.

function varints(bytes, n, off, out) {
  for (let i = 0; i < n; i++) {
    let v = 0, mul = 1, b;
    do { b = bytes[off++]; v += (b & 0x7f) * mul; mul *= 128; } while (b >= 0x80);
    out[i] = v;
  }
  return off;
}
const unzig = (u) => (u % 2 ? -(u + 1) / 2 : u / 2);

function decode(buffer, layout) {
  const bytes = new Uint8Array(buffer), n = layout.vertices, q = layout.unit;
  const raw = new Float64Array(3 * n);
  let off = varints(bytes, 3 * n, 0, raw);
  const vx = new Float64Array(n), vy = new Float64Array(n), vz = new Float64Array(n);
  let a = 0, b = 0, c = 0;
  for (let i = 0; i < n; i++) {
    a += unzig(raw[3 * i]); b += unzig(raw[3 * i + 1]); c += unzig(raw[3 * i + 2]);
    vx[i] = layout.x0 + a * q; vy[i] = layout.y1 - b * q; vz[i] = layout.base + c * q;
  }
  const classes = {};
  for (const [name, m] of Object.entries(layout.classes)) {
    const d = new Float64Array(3 * m);
    off = varints(bytes, 3 * m, off, d);
    const t = new Uint32Array(3 * m);
    let first = 0;
    for (let i = 0; i < m; i++) {
      first += unzig(d[3 * i]);
      t[3 * i] = first; t[3 * i + 1] = first + unzig(d[3 * i + 1]); t[3 * i + 2] = first + unzig(d[3 * i + 2]);
    }
    classes[name] = { tris: t, draw: new Uint16Array(m) };
  }
  for (const [name, runs] of Object.entries(layout.drawRuns || {})) {
    const r = new Float64Array(2 * runs);
    off = varints(bytes, 2 * runs, off, r);
    const draw = classes[name].draw;
    let k = 0;
    for (let i = 0; i < runs; i++) draw.fill(r[2 * i], k, (k += r[2 * i + 1]));
  }
  return { vx, vy, vz, classes };
}

// (a wall stands upright: two of its corners share x and y)
const upright = (vx, vy, a, b, c) => (vx[a] === vx[b] && vy[a] === vy[b]) || (vx[b] === vx[c] && vy[b] === vy[c]) || (vx[a] === vx[c] && vy[a] === vy[c]);

function meshes(g, layout, styles, chunk) {
  const { vx, vy, vz, classes } = g;
  // every triangle as one number, sorted: its (group, chunk, style) key over 2^24, then its index, so that each mesh
  // is one run and each draw class one run in it (millions of triangles: typed arrays, not objects)
  const style = [], sid = new Map(), chunks = new Map();
  let total = 0;
  for (const { draw } of Object.values(classes)) total += draw.length;
  const all = new Uint32Array(3 * total), key = new Float64Array(total);
  let n = 0;
  for (const [name, { tris, draw }] of Object.entries(classes)) {
    const names = layout.draw?.[name] || [''];
    const st = names.map((d) => {
      const s = styles[name]?.[d] ?? styles[name]?.[''] ?? null;
      if (s && !sid.has(s)) { sid.set(s, style.length); style.push(s); }
      return s;
    });
    for (let i = 0; i < draw.length; i++) {
      const s = st[draw[i]];
      if (!s) continue;
      const a = tris[3 * i], b = tris[3 * i + 1], c = tris[3 * i + 2];
      const ck = `${Math.floor((vx[a] + vx[b] + vx[c]) / 3 / chunk)},${Math.floor((vy[a] + vy[b] + vy[c]) / 3 / chunk)}`;
      if (!chunks.has(ck)) chunks.set(ck, chunks.size);
      all[3 * n] = a; all[3 * n + 1] = b; all[3 * n + 2] = c;
      key[n] = ((s[0] * 65536 + chunks.get(ck)) * 256 + sid.get(s)) * 16777216 + n;
      n++;
    }
  }
  if (n >= 16777216) throw new Error(`${n} triangles: more than the sort key holds (2^24)`);
  const order = key.subarray(0, n).sort();
  const groupOf = (k) => Math.floor(k / 16777216 / 256);
  const local = new Int32Array(vx.length), stamp = new Int32Array(vx.length).fill(-1);
  const out = [];
  let i = 0, gen = 0;
  while (i < n) {
    const mesh = groupOf(order[i]);
    let j = i;
    while (j < n && groupOf(order[j]) === mesh) j++;
    // one mesh: its vertices, each draw class's own
    const pos = [], col = [], idx = new Uint32Array(3 * (j - i));
    let nv = 0, last = -1;
    for (let k = i; k < j; k++) {
      const t = order[k] % 16777216, s = style[Math.floor(order[k] / 16777216) % 256];
      if (s !== last) { gen++; last = s; }
      for (let e = 0; e < 3; e++) {
        const v = all[3 * t + e];
        if (stamp[v] !== gen) {
          stamp[v] = gen; local[v] = nv++;
          pos.push(vx[v], vz[v], -vy[v]);
          col.push(s[1], s[2], s[3]);
        }
        idx[3 * (k - i) + e] = local[v];
      }
    }
    const P = new Float32Array(pos), N = new Float32Array(P.length);
    for (let t = 0; t < idx.length; t += 3) {
      const a = 3 * idx[t], b = 3 * idx[t + 1], c = 3 * idx[t + 2];
      const ux = P[b] - P[a], uy = P[b + 1] - P[a + 1], uz = P[b + 2] - P[a + 2];
      const wx = P[c] - P[a], wy = P[c + 1] - P[a + 1], wz = P[c + 2] - P[a + 2];
      const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx; // (area-weighted)
      for (const v of [a, b, c]) { N[v] += nx; N[v + 1] += ny; N[v + 2] += nz; }
    }
    for (let v = 0; v < N.length; v += 3) {
      const l = Math.hypot(N[v], N[v + 1], N[v + 2]) || 1;
      N[v] /= l; N[v + 1] /= l; N[v + 2] /= l;
    }
    out.push({ group: style[Math.floor(order[i] / 16777216) % 256][0], pos: P, nor: N, col: new Float32Array(col), idx });
    i = j;
  }
  return out;
}

function lookup(g, cell) {
  const { vx, vy, vz, classes } = g;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < vx.length; i++) { if (vx[i] < x0) x0 = vx[i]; if (vx[i] > x1) x1 = vx[i]; if (vy[i] < y0) y0 = vy[i]; if (vy[i] > y1) y1 = vy[i]; }
  const nx = Math.ceil((x1 - x0) / cell) + 1, ny = Math.ceil((y1 - y0) / cell) + 1;
  let m = 0;
  for (const [name, { tris }] of Object.entries(classes)) if (name !== 'wall') m += tris.length;
  const tv = new Uint32Array(m);
  m = 0;
  for (const [name, { tris }] of Object.entries(classes)) {
    if (name === 'wall') continue;
    for (let i = 0; i < tris.length; i += 3) {
      if (upright(vx, vy, tris[i], tris[i + 1], tris[i + 2])) continue;
      tv[m++] = tris[i]; tv[m++] = tris[i + 1]; tv[m++] = tris[i + 2];
    }
  }
  const rect = (t) => {
    const a = tv[t], b = tv[t + 1], c = tv[t + 2];
    return [Math.floor((Math.min(vx[a], vx[b], vx[c]) - x0) / cell), Math.floor((Math.min(vy[a], vy[b], vy[c]) - y0) / cell),
      Math.floor((Math.max(vx[a], vx[b], vx[c]) - x0) / cell), Math.floor((Math.max(vy[a], vy[b], vy[c]) - y0) / cell)];
  };
  const count = new Uint32Array(nx * ny + 1);
  for (let t = 0; t < m; t += 3) {
    const [i0, j0, i1, j1] = rect(t);
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) count[j * nx + i + 1]++;
  }
  for (let k = 1; k < count.length; k++) count[k] += count[k - 1];
  const start = count.slice(), tris = new Uint32Array(count[count.length - 1]), fill = count.slice(0, -1);
  for (let t = 0; t < m; t += 3) {
    const [i0, j0, i1, j1] = rect(t);
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) tris[fill[j * nx + i]++] = t / 3;
  }
  // (heights kept relative to the lowest vertex: a 32-bit float holds them to well under a mm)
  return { x0, y0, cell, nx, ny, start, tris, tv: tv.slice(0, m), vx: Float32Array.from(vx, (v) => v - x0), vy: Float32Array.from(vy, (v) => v - y0), vz: Float32Array.from(vz) };
}

onmessage = ({ data }) => {
  const t0 = performance.now();
  const g = decode(data.buffer, data.layout);
  const t1 = performance.now();
  const ms = meshes(g, data.layout, data.styles, data.chunk);
  const t2 = performance.now();
  const lk = lookup(g, data.cell);
  const t3 = performance.now();
  const transfer = [];
  for (const m of ms) transfer.push(m.pos.buffer, m.nor.buffer, m.col.buffer, m.idx.buffer);
  transfer.push(lk.start.buffer, lk.tris.buffer, lk.tv.buffer, lk.vx.buffer, lk.vy.buffer, lk.vz.buffer);
  postMessage({ meshes: ms, lookup: lk, times: { decode: t1 - t0, meshes: t2 - t1, lookup: t3 - t2 } }, transfer);
};
