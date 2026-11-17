// SPDX-License-Identifier: AGPL-3.0-or-later
// The ground file's tiles decoded (tools/ground_mesh.py encode_tiles, #508, #509, #30), in workers so the page's thread
// keeps drawing (the tile container's decision: docs/decisions/2026-11-06-tile-container.md). A tile is decoded on its
// own; its neighbours' blobs come with it when its meshes are asked, for the normals of the vertices on its border.
//
// In: first { init: { styles, names, cell, unit, tile } } — `styles[class][draw name]` = [group, r, g, b] (src/world.js
// groundStyles), `names[class]` the file's draw names ('' first, src/groundFile.js); then per tile { id, bytes, layout,
// box: [x0, y0], ring: [{ bytes, layout }], lookup, meshes, coarse } (bytes: the tile's blob, layout: its own; coarse:
// the far ground's step in m, with `lookup`).
// Out: { id, lookup, meshes, coarse, times }:
// - lookup: { x0, y0, cell, nx, ny, start, tris, vx, vy, vz, tv, tk, kinds, ta, areas, cover }, the tile's height lookup:
//   its flat triangles (the steps' walls left out) in a grid of `cell` m from its corner, each with its class (tk: an
//   index into `kinds`, the file's classes) and the survey's class under it (ta: an index into `areas`, 0 for none),
//   and the survey's 10 m cells (cover, as src/terrain.js TriIndex keys them);
// - meshes: [{ group, pos, nor, col, idx }], one indexed geometry per material group, positions from the tile's corner
//   as three.js takes them (x, z, -y), each draw class with its own vertices so colours do not blend across a class's
//   edge, the normals averaged over its triangles, the neighbours' too on the tile's border;
// - coarse: { pos, nor, col, idx }, the far ground (#30): the lookup's heights and colours on a `coarse` m grid from the
//   tile's corner, a cell drawn where all four corners lie on the ground, and a skirt COARSE_SKIRT m down its border
//   (a detailed tile beside it meets it at its own vertices, not at the grid's: the skirt covers what is between).

function varints(bytes, n, off, out) {
  for (let i = 0; i < n; i++) {
    let v = 0, mul = 1, b;
    do { b = bytes[off++]; v += (b & 0x7f) * mul; mul *= 128; } while (b >= 0x80);
    out[i] = v;
  }
  return off;
}
const unzig = (u) => (u % 2 ? -(u + 1) / 2 : u / 2);

// One encode() blob from `off`: a tile (#30) or a whole file before tiles. `areas`/`areaId`: the survey's class names,
// shared by the tiles; `names[class]`: the draw names the file uses (['', …]), the blob's own draw indexes mapped into
// them; `edge`: the tile's side in the file's units (its vertices on its border are flagged, for the weld), or 0.
function decodeOne(bytes, off, layout, areas, areaId, names, edge) {
  const n = layout.vertices, q = layout.unit;
  const raw = new Float64Array(3 * n);
  off = varints(bytes, 3 * n, off, raw);
  const vx = new Float64Array(n), vy = new Float64Array(n), vz = new Float64Array(n), border = edge ? new Uint8Array(n) : null;
  let a = 0, b = 0, c = 0;
  for (let i = 0; i < n; i++) {
    a += unzig(raw[3 * i]); b += unzig(raw[3 * i + 1]); c += unzig(raw[3 * i + 2]);
    vx[i] = layout.x0 + a * q; vy[i] = layout.y1 - b * q; vz[i] = layout.base + c * q;
    if (edge && (a === 0 || a === edge || b === 0 || b === edge)) border[i] = 1;
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
    const own = layout.draw[name], to = own.map((d) => names[name].indexOf(d));
    const draw = classes[name].draw;
    let k = 0;
    for (let i = 0; i < runs; i++) draw.fill(to[r[2 * i]], k, (k += r[2 * i + 1]));
  }
  // the survey's class under each triangle (tools/ground_mesh.py LAYERS: after the draw classes), as one list of names
  for (const [name, runs] of Object.entries(layout.areaRuns || {})) {
    const r = new Float64Array(2 * runs);
    off = varints(bytes, 2 * runs, off, r);
    const ids = layout.area[name].map((a) => { if (!areaId.has(a)) { areaId.set(a, areas.length); areas.push(a); } return areaId.get(a); });
    const area = (classes[name].area = new Uint8Array(classes[name].tris.length / 3));
    let k = 0;
    for (let i = 0; i < runs; i++) area.fill(ids[r[2 * i]], k, (k += r[2 * i + 1]));
  }
  return { vx, vy, vz, border, classes };
}

// (a wall stands upright: two of its corners share x and y)
const upright = (vx, vy, a, b, c) => (vx[a] === vx[b] && vy[a] === vy[b]) || (vx[b] === vx[c] && vy[b] === vy[c]) || (vx[a] === vx[c] && vy[a] === vy[c]);

// The neighbours' triangles at the tile's border: per style and point (mm) the sum of their area-weighted normals
// (three.js frame), to add to the tile's own there
function ringNormals(ring, box, cfg) {
  const out = new Map(), q = cfg.unit, edge = Math.round(cfg.tile / q);
  const X0 = Math.round(box[0] / q), Y0 = Math.round(box[1] / q), X1 = X0 + edge, Y1 = Y0 + edge;
  for (const r of ring) {
    const g = decodeOne(new Uint8Array(r.bytes), 0, r.layout, [''], new Map([['', 0]]), cfg.names, 0);
    const { vx, vy, vz } = g, mx = new Float64Array(vx.length), my = new Float64Array(vx.length), on = new Uint8Array(vx.length);
    let any = false;
    for (let i = 0; i < vx.length; i++) {
      const x = (mx[i] = Math.round(vx[i] / q)), y = (my[i] = Math.round(vy[i] / q));
      if (((x === X0 || x === X1) && y >= Y0 && y <= Y1) || ((y === Y0 || y === Y1) && x >= X0 && x <= X1)) { on[i] = 1; any = true; }
    }
    if (!any) continue;
    for (const [name, { tris, draw }] of Object.entries(g.classes)) {
      const names = cfg.names[name];
      for (let i = 0; i < draw.length; i++) {
        const a = tris[3 * i], b = tris[3 * i + 1], c = tris[3 * i + 2];
        if (!on[a] && !on[b] && !on[c]) continue;
        const s = cfg.styles[name]?.[names[draw[i]]] ?? cfg.styles[name]?.[''] ?? null;
        if (!s) continue;
        const ux = vx[b] - vx[a], uy = vz[b] - vz[a], uz = vy[a] - vy[b], wx = vx[c] - vx[a], wy = vz[c] - vz[a], wz = vy[a] - vy[c];
        const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
        for (const v of [a, b, c]) {
          if (!on[v]) continue;
          const k = `${cfg.sid.get(s)}|${mx[v]},${my[v]},${Math.round(vz[v] / q)}`, n = out.get(k);
          if (n) { n[0] += nx; n[1] += ny; n[2] += nz; } else out.set(k, [nx, ny, nz]);
        }
      }
    }
  }
  return out;
}

function meshes(g, cfg, box, ring) {
  const { vx, vy, vz, classes, border } = g, styles = cfg.styles, q = cfg.unit, [x0, y0] = box;
  // every triangle as one number, sorted: its (group, style) key over 2^24, then its index, so that each mesh is one
  // run and each draw class one run in it (typed arrays, not objects)
  const style = [], sid = new Map();
  let total = 0;
  for (const { draw } of Object.values(classes)) total += draw.length;
  const all = new Uint32Array(3 * total), key = new Float64Array(total);
  let n = 0;
  for (const [name, { tris, draw }] of Object.entries(classes)) {
    const names = cfg.names[name];
    const st = names.map((d) => {
      const s = styles[name]?.[d] ?? styles[name]?.[''] ?? null;
      if (s && !sid.has(s)) { sid.set(s, style.length); style.push(s); }
      return s;
    });
    for (let i = 0; i < draw.length; i++) {
      const s = st[draw[i]];
      if (!s) continue;
      all[3 * n] = tris[3 * i]; all[3 * n + 1] = tris[3 * i + 1]; all[3 * n + 2] = tris[3 * i + 2];
      key[n] = (s[0] * 256 + sid.get(s)) * 16777216 + n;
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
    // one mesh: its vertices, each draw class's own (the tile's border ones remembered: the neighbours' normals)
    const pos = [], col = [], idx = new Uint32Array(3 * (j - i)), edge = [];
    let nv = 0, last = -1;
    for (let k = i; k < j; k++) {
      const t = order[k] % 16777216, s = style[Math.floor(order[k] / 16777216) % 256];
      if (s !== last) { gen++; last = s; }
      for (let e = 0; e < 3; e++) {
        const v = all[3 * t + e];
        if (stamp[v] !== gen) {
          stamp[v] = gen; local[v] = nv++;
          pos.push(vx[v] - x0, vz[v], y0 - vy[v]);
          col.push(s[1], s[2], s[3]);
          if (border[v]) edge.push(local[v], v, cfg.sid.get(s));
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
    if (ring) {
      for (let e = 0; e < edge.length; e += 3) {
        const v = edge[e + 1], r = ring.get(`${edge[e + 2]}|${Math.round(vx[v] / q)},${Math.round(vy[v] / q)},${Math.round(vz[v] / q)}`);
        if (r) { const o = 3 * edge[e]; N[o] += r[0]; N[o + 1] += r[1]; N[o + 2] += r[2]; }
      }
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

const COVER_CELL = 10; // m: src/terrain.js TriIndex's cover
// (the grid from the tile's corner, `side` m across: a vertex on its far border in the last cell)
function lookup(g, cell, box, side) {
  const { vx, vy, vz, classes } = g, [x0, y0] = box, col = [];
  const nx = Math.floor(side / cell) + 1, ny = nx;
  let m = 0;
  for (const [name, { tris }] of Object.entries(classes)) if (name !== 'wall') m += tris.length;
  const tv = new Uint32Array(m), ta = new Uint8Array(m / 3), tk = new Uint8Array(m / 3), kinds = Object.keys(classes), cover = new Set();
  m = 0;
  for (const [name, { tris, area, draw }] of Object.entries(classes)) {
    const kind = kinds.indexOf(name), names = cfg.names[name];
    if (name === 'wall') continue;
    for (let i = 0; i < tris.length; i += 3) {
      const a = tris[i], b = tris[i + 1], c = tris[i + 2];
      if (upright(vx, vy, a, b, c)) continue;
      const id = area ? area[i / 3] : 0;
      if (id) {
        const i0 = Math.floor(Math.min(vx[a], vx[b], vx[c]) / COVER_CELL), i1 = Math.floor(Math.max(vx[a], vx[b], vx[c]) / COVER_CELL);
        const j0 = Math.floor(Math.min(vy[a], vy[b], vy[c]) / COVER_CELL), j1 = Math.floor(Math.max(vy[a], vy[b], vy[c]) / COVER_CELL);
        for (let ix = i0; ix <= i1; ix++) for (let iy = j0; iy <= j1; iy++) cover.add(ix * 100003 + iy);
      }
      ta[m / 3] = id; tk[m / 3] = kind;
      const st = cfg.styles[name]?.[names[draw[i / 3]]] ?? cfg.styles[name]?.[''];
      col.push(st ? st[1] : 0.5, st ? st[2] : 0.5, st ? st[3] : 0.5);
      tv[m++] = a; tv[m++] = b; tv[m++] = c;
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
  return { x0, y0, cell, nx, ny, start, tris, tv: tv.slice(0, m), ta: ta.slice(0, m / 3), areas: g.areas, tk: tk.slice(0, m / 3), kinds, cover: Float64Array.from(cover), col,
    vx: Float32Array.from(vx, (v) => v - x0), vy: Float32Array.from(vy, (v) => v - y0), vz: Float32Array.from(vz) };
}

// The lookup's triangle at (px, py) from its corner: [index, height], [-1] off the ground (src/groundFile.js GroundLookup)
function find(lk, px, py) {
  const i = Math.floor(px / lk.cell), j = Math.floor(py / lk.cell);
  if (i < 0 || j < 0 || i >= lk.nx || j >= lk.ny) return [-1, 0];
  const { vx, vy, vz, tv, tris } = lk, k = j * lk.nx + i;
  let best = -1, bz = 0;
  for (let s = lk.start[k], e = lk.start[k + 1]; s < e; s++) {
    const t = 3 * tris[s], a = tv[t], b = tv[t + 1], c = tv[t + 2];
    const d = (vy[b] - vy[c]) * (vx[a] - vx[c]) + (vx[c] - vx[b]) * (vy[a] - vy[c]);
    if (!d) continue;
    const w0 = ((vy[b] - vy[c]) * (px - vx[c]) + (vx[c] - vx[b]) * (py - vy[c])) / d, w1 = ((vy[c] - vy[a]) * (px - vx[c]) + (vx[a] - vx[c]) * (py - vy[c])) / d;
    const w2 = 1 - w0 - w1;
    if (w0 < -1e-7 || w1 < -1e-7 || w2 < -1e-7) continue;
    const z = w0 * vz[a] + w1 * vz[b] + w2 * vz[c];
    if (best < 0 || z > bz) { best = tris[s]; bz = z; }
  }
  return [best, bz];
}

const COARSE_SKIRT = 5; // m: the far ground's skirt down its border
function coarse(lk, col, side, step) {
  const n = Math.round(side / step) + 1, z = new Float64Array(n * n).fill(NaN), C = new Float32Array(3 * n * n);
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const [t, h] = find(lk, i * step, j * step);
    if (t < 0) continue;
    z[j * n + i] = h;
    C[3 * (j * n + i)] = col[3 * t]; C[3 * (j * n + i) + 1] = col[3 * t + 1]; C[3 * (j * n + i) + 2] = col[3 * t + 2];
  }
  const ok = (i, j) => i >= 0 && j >= 0 && i < n && j < n && !Number.isNaN(z[j * n + i]);
  const pos = [], nor = [], cols = [], idx = [], at = new Int32Array(n * n).fill(-1);
  const add = (i, j, dz) => {
    const k = j * n + i;
    // (the normal from the grid's differences, as three.js takes it: x, up, -y)
    const l = ok(i - 1, j) ? i - 1 : i, r = ok(i + 1, j) ? i + 1 : i, b = ok(i, j - 1) ? j - 1 : j, f = ok(i, j + 1) ? j + 1 : j;
    const dx = r > l ? (z[j * n + r] - z[j * n + l]) / ((r - l) * step) : 0, dy = f > b ? (z[f * n + i] - z[b * n + i]) / ((f - b) * step) : 0;
    const len = Math.hypot(dx, 1, dy);
    pos.push(i * step, z[k] - dz, -j * step);
    nor.push(-dx / len, 1 / len, dy / len);
    cols.push(C[3 * k], C[3 * k + 1], C[3 * k + 2]);
    return pos.length / 3 - 1;
  };
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) if (ok(i, j)) at[j * n + i] = add(i, j, 0);
  for (let j = 0; j + 1 < n; j++) for (let i = 0; i + 1 < n; i++) {
    const a = at[j * n + i], b = at[j * n + i + 1], c = at[(j + 1) * n + i + 1], d = at[(j + 1) * n + i];
    if (a < 0 || b < 0 || c < 0 || d < 0) continue;
    idx.push(a, b, c, a, c, d); // (counter-clockwise from above, as the ground file's)
  }
  // the skirt: each border edge with both ends on the ground, down COARSE_SKIRT m
  const edge = (i0, j0, i1, j1) => {
    if (!ok(i0, j0) || !ok(i1, j1)) return;
    const a = at[j0 * n + i0], b = at[j1 * n + i1], a2 = add(i0, j0, COARSE_SKIRT), b2 = add(i1, j1, COARSE_SKIRT);
    idx.push(a, a2, b2, a, b2, b);
  };
  for (let k = 0; k + 1 < n; k++) { edge(k, 0, k + 1, 0); edge(k + 1, n - 1, k, n - 1); edge(0, k + 1, 0, k); edge(n - 1, k, n - 1, k + 1); }
  return { pos: new Float32Array(pos), nor: new Float32Array(nor), col: new Float32Array(cols), idx: new Uint32Array(idx) };
}

let cfg = null;
onmessage = ({ data }) => {
  if (data.init) {
    cfg = data.init;
    cfg.sid = new Map(); // (each style an id: the neighbours' normals are matched by it)
    for (const byDraw of Object.values(cfg.styles)) for (const s of Object.values(byDraw)) if (!cfg.sid.has(s)) cfg.sid.set(s, cfg.sid.size);
    return;
  }
  const t0 = performance.now(), areas = [''];
  const g = decodeOne(new Uint8Array(data.bytes), 0, data.layout, areas, new Map([['', 0]]), cfg.names, Math.round(cfg.tile / cfg.unit));
  g.areas = areas;
  const t1 = performance.now();
  const out = { id: data.id }, transfer = [];
  if (data.lookup) {
    const lk = (out.lookup = lookup(g, cfg.cell, data.box, cfg.tile));
    if (data.coarse) {
      const c = (out.coarse = coarse(lk, lk.col, cfg.tile, data.coarse));
      transfer.push(c.pos.buffer, c.nor.buffer, c.col.buffer, c.idx.buffer);
    }
    delete lk.col;
    transfer.push(lk.start.buffer, lk.tris.buffer, lk.tv.buffer, lk.ta.buffer, lk.tk.buffer, lk.cover.buffer, lk.vx.buffer, lk.vy.buffer, lk.vz.buffer);
  }
  const t2 = performance.now();
  if (data.meshes) {
    out.meshes = meshes(g, cfg, data.box, data.ring?.length ? ringNormals(data.ring, data.box, cfg) : null);
    for (const m of out.meshes) transfer.push(m.pos.buffer, m.nor.buffer, m.col.buffer, m.idx.buffer);
  }
  out.times = { decode: t1 - t0, lookup: t2 - t1, meshes: performance.now() - t2 };
  postMessage(out, transfer);
};
