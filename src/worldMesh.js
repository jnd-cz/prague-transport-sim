// SPDX-License-Identifier: AGPL-3.0-or-later
// What the world's layers build with: meshes merged in chunks, spatial indexes of lines and footprints, ribbons along
// a line, and how much snow each kind of surface keeps.
import * as THREE from 'three';
import { weatherize, wetFactor } from './weather.js';

export const CELL = 350; // spatial chunk size (m) for merged meshes, so frustum culling can skip far chunks
// how much of the snow stays on a surface (src/weather.js): carriageways are driven and ploughed,
// footways trodden; ground, roofs, ballast take it all
export const STREET_SNOW = 0.35, FOOT_SNOW = 0.7, GROUND_SNOW = 1;

// (the weather is the materials' state, src/weather.js: everything is built in its dry colours, each
// material with how much darker it gets wet (the old wet colours as factors) and how snow lies on it)
export const flatMat = (dry, wetHex, snow = STREET_SNOW) => weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { wet: wetFactor(dry, wetHex), snow, slush: true });

export const W = (x, y, h = 0) => [x, h, -y];

export function signedArea(ring) {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1]);
  return a / 2; // > 0 for counter-clockwise (x east, y north)
}

export function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// split long segments so draped geometry follows the terrain
export function densify(line, maxLen = 4) {
  const out = [line[0]];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1], b = line[i];
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / maxLen);
    for (let k = 1; k <= n; k++) out.push([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n]);
  }
  return out;
}
export const polyLength = (line) => line.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - line[i - 1][0], p[1] - line[i - 1][1]) : 0), 0);

// Grid of line segments for fast "distance to the nearest X" queries (tracks, roads).
export class SegmentIndex {
  constructor(cell = 10) { this.cell = cell; this.map = new Map(); }
  // (za, zb: the ends' heights, for heightAt)
  add(a, b, w = 0, za = 0, zb = 0) {
    const c = this.cell, seg = [a[0], a[1], b[0], b[1], w / 2, za, zb];
    const i0 = Math.floor((Math.min(a[0], b[0]) - seg[4]) / c), i1 = Math.floor((Math.max(a[0], b[0]) + seg[4]) / c);
    const j0 = Math.floor((Math.min(a[1], b[1]) - seg[4]) / c), j1 = Math.floor((Math.max(a[1], b[1]) + seg[4]) / c);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = i * 65536 + j; // (a number, not "i,j": #205)
      const arr = this.map.get(k);
      if (arr) arr.push(seg); else this.map.set(k, [seg]);
    }
  }
  addLine(line, w = 0) { for (let i = 1; i < line.length; i++) this.add(line[i - 1], line[i], w); }
  // distance from (x, y) to the nearest segment's edge (centre line minus half width), up to ~cell
  dist(x, y) {
    const c = this.cell, ci = Math.floor(x / c), cj = Math.floor(y / c);
    let best = Infinity;
    for (let i = ci - 1; i <= ci + 1; i++) for (let j = cj - 1; j <= cj + 1; j++) {
      const arr = this.map.get(i * 65536 + j);
      if (!arr) continue;
      for (const [ax, ay, bx, by, hw] of arr) {
        const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
        best = Math.min(best, Math.hypot(ax + dx * t - x, ay + dy * t - y) - hw);
      }
    }
    return best;
  }
  // whether dist(x, y) < r: the same terms, done at the first segment that is (#244: the street flush asks this
  // of every road-bed vertex, and needed no minimum)
  within(x, y, r) {
    const c = this.cell, ci = Math.floor(x / c), cj = Math.floor(y / c);
    for (let i = ci - 1; i <= ci + 1; i++) for (let j = cj - 1; j <= cj + 1; j++) {
      const arr = this.map.get(i * 65536 + j);
      if (!arr) continue;
      for (const [ax, ay, bx, by, hw] of arr) {
        const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
        if (Math.hypot(ax + dx * t - x, ay + dy * t - y) - hw < r) return true;
      }
    }
    return false;
  }
  // the nearest segment's height at its point nearest (x, y), between its ends' (add's za, zb), if within r (<= cell) of
  // its centre line; else null
  heightAt(x, y, r) {
    const c = this.cell, ci = Math.floor(x / c), cj = Math.floor(y / c);
    let best = r * r, z = null;
    for (let i = ci - 1; i <= ci + 1; i++) for (let j = cj - 1; j <= cj + 1; j++) {
      const arr = this.map.get(i * 65536 + j);
      if (!arr) continue;
      for (const [ax, ay, bx, by, , za, zb] of arr) {
        const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
        const d = (ax + dx * t - x) ** 2 + (ay + dy * t - y) ** 2;
        if (d < best) { best = d; z = za + (zb - za) * t; }
      }
    }
    return z;
  }
}

// Building footprints on a grid, for point-in-building tests.
export class FootprintIndex {
  constructor(rings, cell = 25) {
    this.cell = cell; this.map = new Map(); this.entries = [];
    rings.forEach((ring) => {
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (const p of ring) { minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]); minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); }
      const e = { ring, minX, minY, maxX, maxY };
      this.entries.push(e);
      for (let i = Math.floor(minX / cell); i <= Math.floor(maxX / cell); i++) for (let j = Math.floor(minY / cell); j <= Math.floor(maxY / cell); j++) {
        const k = `${i},${j}`;
        if (!this.map.has(k)) this.map.set(k, []);
        this.map.get(k).push(e);
      }
    });
  }
  inside(x, y) {
    const arr = this.map.get(`${Math.floor(x / this.cell)},${Math.floor(y / this.cell)}`);
    if (!arr) return false;
    for (const e of arr) if (x >= e.minX && x <= e.maxX && y >= e.minY && y <= e.maxY && pointInRing(x, y, e.ring)) return true;
    return false;
  }
}

// Accumulates triangles per chunk, then emits one mesh per chunk.
export class ChunkedGeometry {
  constructor(material, { uv = false, color = false } = {}) {
    this.material = material;
    this.useUv = uv;
    this.useColor = color;
    this.chunks = new Map();
  }
  _chunk(x, y) {
    const k = `${Math.floor(x / CELL)},${Math.floor(y / CELL)}`;
    let c = this.chunks.get(k);
    if (!c) { c = { pos: [], nor: [], uv: [], col: [] }; this.chunks.set(k, c); }
    return c;
  }
  tri(c, a, b, d, uvs, col) {
    if (this.sourceId !== undefined) {
      const start = c.pos.length / 9, ranges = (c.footwayRanges ||= []), last = ranges[ranges.length - 1];
      if (last && last[2] === this.sourceId && last[1] === start) last[1]++;
      else ranges.push([start, start + 1, this.sourceId]);
    }
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    nx /= l; ny /= l; nz /= l;
    // (the values written out, not spread: millions of triangles at load, #244)
    c.pos.push(a[0], a[1], a[2], b[0], b[1], b[2], d[0], d[1], d[2]);
    c.nor.push(nx, ny, nz, nx, ny, nz, nx, ny, nz);
    if (this.useUv) { if (uvs) c.uv.push(uvs[0], uvs[1], uvs[2], uvs[3], uvs[4], uvs[5]); else c.uv.push(0, 0, 0, 0, 0, 0); }
    if (this.useColor) c.col.push(col[0], col[1], col[2], col[0], col[1], col[2], col[0], col[1], col[2]);
  }
  quad(c, a, b, d, e, col) { this.tri(c, a, b, d, null, col); this.tri(c, a, d, e, null, col); }
  // `surface` tags meshes cars and walkers stand on (read by the street bot); 'building' marks
  // building meshes instead (read by the lints)
  build(group, surface = null, surfaceKind = null) {
    for (const c of this.chunks.values()) {
      if (!c.pos.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(c.pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(c.nor, 3));
      if (this.useUv) g.setAttribute('uv', new THREE.Float32BufferAttribute(c.uv, 2));
      if (this.useColor) g.setAttribute('color', new THREE.Float32BufferAttribute(c.col, 3));
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, this.material);
      if (c.surfaceRanges) m.userData.surfaceRanges = c.surfaceRanges;
      if (c.footwayRanges) m.userData.footwayRanges = c.footwayRanges;
      m.matrixAutoUpdate = false;
      if (surface === 'building') m.userData.building = true;
      else if (surface) m.userData.surface = surface;
      if (c.trackRanges) m.userData.trackRanges = c.trackRanges;
      if (surfaceKind) m.userData.surfaceKind = surfaceKind;
      group.add(m);
    }
  }
}

// Flat polygon at constant height h (roofs); triangles forced to face up.
export function addFlatPolygon(cg, ring, h, col) {
  if (ring.length < 3) return;
  const contour = ring.map((p) => new THREE.Vector2(p[0], p[1]));
  const tris = THREE.ShapeUtils.triangulateShape(contour, []);
  const c = cg._chunk(ring[0][0], ring[0][1]);
  for (const t of tris) {
    let a = ring[t[0]], b = ring[t[1]], d = ring[t[2]];
    const cross = (b[0] - a[0]) * (d[1] - a[1]) - (b[1] - a[1]) * (d[0] - a[0]);
    if (cross < 0) [b, d] = [d, b];
    cg.tri(c, W(a[0], a[1], h), W(b[0], b[1], h), W(d[0], d[1], h), null, col);
  }
}

// Ribbon along a polyline. `hfn` is either a height function (each edge vertex at
// hfn(x, y) + lift) or an array of centre-line heights (level across, e.g. track).
// (`strips` > 1: that many strips across, each edge at its own height: a street with tracks in it
// follows the track level in its middle instead of a straight line from kerb to kerb)
export function addRibbon(cg, line, width, hfn, lift, col, offset = 0, strips = 1, crossfall = null) {
  if (line.length < 2) return;
  const fixed = Array.isArray(hfn);
  if (!fixed) line = densify(line);
  if (strips > 1 && !fixed) {
    for (let k = 0; k < strips; k++) addRibbon(cg, line, width / strips, hfn, lift, col, offset + width * ((k + 0.5) / strips - 0.5));
    return;
  }
  const half = width / 2;
  const L = [], R = [];
  for (let i = 0; i < line.length; i++) {
    const p = line[i];
    const prev = line[Math.max(0, i - 1)], next = line[Math.min(line.length - 1, i + 1)];
    let dx = next[0] - prev[0], dy = next[1] - prev[1];
    const l = Math.hypot(dx, dy) || 1;
    dx /= l; dy /= l;
    let scale = 1;
    if (i > 0 && i < line.length - 1) {
      const ax = p[0] - prev[0], ay = p[1] - prev[1], al = Math.hypot(ax, ay) || 1;
      scale = Math.min(2, 1 / Math.max(0.5, (ax / al) * dx + (ay / al) * dy));
    }
    const nx = -dy, ny = dx;
    const lx = p[0] + nx * (offset + half * scale), ly = p[1] + ny * (offset + half * scale);
    const rx = p[0] + nx * (offset - half * scale), ry = p[1] + ny * (offset - half * scale);
    const dz = crossfall ? crossfall[i] * half * scale : 0;
    L.push(W(lx, ly, (fixed ? hfn[i] : hfn(lx, ly)) + lift + dz));
    R.push(W(rx, ry, (fixed ? hfn[i] : hfn(rx, ry)) + lift - dz));
  }
  const c = cg._chunk(line[0][0], line[0][1]);
  // (`col` a function: each segment's own colour, from its first point)
  for (let i = 0; i < line.length - 1; i++) cg.quad(c, R[i], R[i + 1], L[i + 1], L[i], typeof col === 'function' ? col(i) : col);
}

// A vertical strip along `line` at `offset` m to its left, from zBot up to zTop (arrays per point):
// the sides of the rails where the bed lies well under the heads (grass, ballast)
export function addSide(cg, line, offset, zTop, zBot) {
  const c = cg._chunk(line[0][0], line[0][1]), P = [];
  for (let i = 0; i < line.length; i++) {
    const a = line[Math.max(0, i - 1)], b = line[Math.min(line.length - 1, i + 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
    P.push([line[i][0] - (dy / l) * offset, line[i][1] + (dx / l) * offset]);
  }
  for (let i = 0; i < line.length - 1; i++) {
    cg.quad(c, W(P[i][0], P[i][1], zBot[i]), W(P[i + 1][0], P[i + 1][1], zBot[i + 1]),
      W(P[i + 1][0], P[i + 1][1], zTop[i + 1]), W(P[i][0], P[i][1], zTop[i]));
  }
}
