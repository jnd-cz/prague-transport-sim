// Static 3D scenery built from the preprocessed OSM data, draped on the DMR 5G terrain.
import * as THREE from 'three';
import { smoothPolyline } from './route.js';

const CELL = 350; // spatial chunk size (m) for merged meshes, so frustum culling can skip far chunks
const TERRAIN_CHUNK = 20; // terrain cells per chunk side

// deterministic pseudo random
export function rng(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

const W = (x, y, h = 0) => [x, h, -y];

function signedArea(ring) {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) a += (ring[j][0] - ring[i][0]) * (ring[j][1] + ring[i][1]);
  return a / 2; // > 0 for counter-clockwise (x east, y north)
}

function pointInRing(x, y, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// split long segments so draped geometry follows the terrain
function densify(line, maxLen = 4) {
  const out = [line[0]];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1], b = line[i];
    const n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / maxLen);
    for (let k = 1; k <= n; k++) out.push([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n]);
  }
  return out;
}

// Accumulates triangles per chunk, then emits one mesh per chunk.
class ChunkedGeometry {
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
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2];
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.hypot(nx, ny, nz) || 1;
    nx /= l; ny /= l; nz /= l;
    c.pos.push(...a, ...b, ...d);
    c.nor.push(nx, ny, nz, nx, ny, nz, nx, ny, nz);
    if (this.useUv) c.uv.push(...(uvs || [0, 0, 0, 0, 0, 0]));
    if (this.useColor) c.col.push(...col, ...col, ...col);
  }
  quad(c, a, b, d, e, col) { this.tri(c, a, b, d, null, col); this.tri(c, a, d, e, null, col); }
  build(group) {
    for (const c of this.chunks.values()) {
      if (!c.pos.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(c.pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(c.nor, 3));
      if (this.useUv) g.setAttribute('uv', new THREE.Float32BufferAttribute(c.uv, 2));
      if (this.useColor) g.setAttribute('color', new THREE.Float32BufferAttribute(c.col, 3));
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, this.material);
      m.matrixAutoUpdate = false;
      group.add(m);
    }
  }
}

// Flat polygon at constant height h (roofs); triangles forced to face up.
function addFlatPolygon(cg, ring, h, col) {
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
function addRibbon(cg, line, width, hfn, lift, col, offset = 0) {
  if (line.length < 2) return;
  const fixed = Array.isArray(hfn);
  if (!fixed) line = densify(line);
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
    L.push(W(lx, ly, (fixed ? hfn[i] : hfn(lx, ly)) + lift));
    R.push(W(rx, ry, (fixed ? hfn[i] : hfn(rx, ry)) + lift));
  }
  const c = cg._chunk(line[0][0], line[0][1]);
  for (let i = 0; i < line.length - 1; i++) cg.quad(c, R[i], R[i + 1], L[i + 1], L[i], col);
}

// Heights along a track chain, smoothed along its length (Gaussian, ±9 m) so rails never
// step even where the ground function changes regime (route profile / terrain / bridge).
function trackHeights(line, hf) {
  const raw = line.map((p) => hf(p[0], p[1]));
  const n = raw.length, k = 6, out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const r = Math.min(k, i, n - 1 - i);
    let acc = 0, wsum = 0;
    for (let d = -r; d <= r; d++) { const w = Math.exp(-0.5 * (d / 3) ** 2); acc += raw[i + d] * w; wsum += w; }
    out[i] = acc / wsum;
  }
  return Array.from(out);
}

// Height function for an OSM way: bridges not on our route span linearly between their ends.
function wayHeight(line, isBridge, ground) {
  if (!isBridge) return (x, y) => ground.at(x, y);
  const a = line[0], b = line[line.length - 1];
  const ha = ground.terrain.height(a[0], a[1]), hb = ground.terrain.height(b[0], b[1]);
  const lx = b[0] - a[0], ly = b[1] - a[1], l2 = lx * lx + ly * ly || 1;
  return (x, y) => {
    // decks that share our route's bridge take its profile; otherwise a straight span
    const deck = ground.deckAt(x, y);
    if (deck !== null) return deck;
    const t = Math.max(0, Math.min(1, ((x - a[0]) * lx + (y - a[1]) * ly) / l2));
    return ha + (hb - ha) * t;
  };
}

function facadeTexture() {
  const cv = document.createElement('canvas');
  cv.width = 128; cv.height = 128;
  const g = cv.getContext('2d');
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, 128, 128);
  const r = rng(7);
  for (let i = 0; i < 900; i++) {
    const v = 225 + Math.floor(r() * 30);
    g.fillStyle = `rgb(${v},${v},${v})`;
    g.fillRect(r() * 128, r() * 128, 2, 2);
  }
  // window: tile = 3.5 m wide x 3.2 m high
  g.fillStyle = '#d9d4c8';
  g.fillRect(30, 26, 68, 80);
  g.fillStyle = '#2b3440';
  g.fillRect(36, 32, 56, 68);
  g.fillStyle = '#56687a';
  g.fillRect(36, 32, 56, 24);
  g.fillStyle = '#d9d4c8';
  g.fillRect(62, 32, 4, 68);
  g.fillRect(36, 60, 56, 4);
  g.fillStyle = '#c9c3b6';
  g.fillRect(0, 120, 128, 8);
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

const FACADE_COLORS = ['#e8d9b5', '#d9c7a0', '#efe3c8', '#c9b79a', '#e3c9b0', '#d6d0c2', '#e6d2a8', '#cfc3ad',
  '#e0b9a0', '#b9c4c9', '#d8cfb8', '#f0e6d2'].map((c) => new THREE.Color(c));
const ROOF_COLORS = ['#8c4a32', '#7a3f2c', '#5f5a55', '#6d6862', '#9a5638', '#4f4b47'].map((c) => new THREE.Color(c));

export function buildWorld(scene, data, route, ground, weather) {
  const group = new THREE.Group();
  group.matrixAutoUpdate = false;
  scene.add(group);

  // far fallback ground below the terrain
  const far = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), new THREE.MeshLambertMaterial({ color: 0x8a897d }));
  far.rotation.x = -Math.PI / 2;
  far.position.y = ground.terrain.min - 3;
  scene.add(far);

  buildTerrain(group, data, route, ground.terrain, weather);

  const flatMat = new THREE.MeshLambertMaterial({ vertexColors: true });
  const wet = weather !== 'dry';

  // roads (wider first so footways draw on top)
  const roadsCg = new ChunkedGeometry(flatMat, { color: true });
  const asphalt = new THREE.Color(wet ? '#3e3f43' : '#55565a').toArray(), paving = new THREE.Color(wet ? '#86817a' : '#a39d90').toArray();
  for (const r of [...data.roads].sort((a, b) => b.w - a.w)) {
    addRibbon(roadsCg, r.p, r.w, wayHeight(r.p, r.b, ground), r.f ? 0.16 : 0.12, r.f ? paving : asphalt);
  }
  roadsCg.build(group);

  // track bed + rails for every tram track around the route
  const bedCg = new ChunkedGeometry(flatMat, { color: true });
  const bed = new THREE.Color(wet ? '#5f5c56' : '#77736a').toArray();
  const railMat = new THREE.MeshStandardMaterial({ color: 0xc4c7cc, metalness: 0.6, roughness: wet ? 0.2 : 0.4 });
  const railCg = new ChunkedGeometry(railMat);
  for (const t of data.tracks) {
    // OSM draws curves as straight segments: render tracks as smoothed curves
    if (!t.smooth) t.smooth = smoothPolyline(t.p, 1.5, t.p.length > 2 ? 6 : 0.1).pts;
    t.z = trackHeights(t.smooth, wayHeight(t.p, t.b, ground));
    addRibbon(bedCg, t.smooth, 2.7, t.z, 0.2, bed);
    addRibbon(railCg, t.smooth, 0.1, t.z, 0.26, null, 0.72);
    addRibbon(railCg, t.smooth, 0.1, t.z, 0.26, null, -0.72);
  }
  bedCg.build(group);
  railCg.build(group);

  buildWalls(group, data, route, ground);

  buildBridges(group, data, route, ground);

  if (data.geo?.buildings?.arr) buildLod2(group, data, route, ground);
  else buildOsmBuildings(group, data, route, ground);

  buildTrees(group, data, route, ground, weather);
  buildCatenary(group, data, route, ground);
  return group;
}

// Fallback: OSM footprints extruded to their tagged height, sitting on the terrain.
function buildOsmBuildings(group, data, route, ground) {
  const facadeMat = new THREE.MeshLambertMaterial({ map: facadeTexture(), vertexColors: true });
  const roofMat = new THREE.MeshLambertMaterial({ vertexColors: true });
  const walls = new ChunkedGeometry(facadeMat, { uv: true, color: true });
  const roofs = new ChunkedGeometry(roofMat, { color: true });
  let skipped = 0;
  data.buildings.forEach((b, idx) => {
    let ring = b.p;
    let blocked = false;
    for (const p of ring) if (route.distance(p[0], p[1]) < 2.5) { blocked = true; break; }
    let cx = 0, cy = 0;
    for (const p of ring) { cx += p[0]; cy += p[1]; }
    cx /= ring.length; cy /= ring.length;
    if (!blocked && route.distance(cx, cy) < 3) blocked = true;
    if (signedArea(ring) < 0) ring = [...ring].reverse();
    let hmin = Infinity, hsum = 0;
    for (const p of ring) { const h = ground.terrain.height(p[0], p[1]); hmin = Math.min(hmin, h); hsum += h; }
    let base = hmin - 1, top = hsum / ring.length + b.h;
    if (blocked) {
      // the tracks pass under this building (e.g. Letenska): raise it over the tram and wire
      skipped++;
      let ht = -Infinity;
      for (const p of ring) ht = Math.max(ht, ground.at(p[0], p[1]));
      base = Math.max(ht, ground.at(cx, cy)) + 6.4;
      top = Math.max(base + 4, top);
    }
    const r = rng(idx * 7919 + 13);
    const col = FACADE_COLORS[Math.floor(r() * FACADE_COLORS.length)].toArray();
    const small = b.h < 4;
    const c = walls._chunk(ring[0][0], ring[0][1]);
    let u = 0;
    for (let i = 0; i < ring.length; i++) {
      const a = ring[i], d = ring[(i + 1) % ring.length];
      const len = Math.hypot(d[0] - a[0], d[1] - a[1]);
      const u0 = small ? 0 : u / 3.5, u1 = small ? 0 : (u + len) / 3.5;
      const v0 = small ? 0 : (base - top) / 3.2;
      const a0 = W(a[0], a[1], base), b0 = W(d[0], d[1], base), b1 = W(d[0], d[1], top), a1 = W(a[0], a[1], top);
      walls.tri(c, a0, b0, b1, [u0, v0, u1, v0, u1, 0], col);
      walls.tri(c, a0, b1, a1, [u0, v0, u1, 0, u0, 0], col);
      u += len;
    }
    addFlatPolygon(roofs, ring, top, ROOF_COLORS[Math.floor(r() * ROOF_COLORS.length)].toArray());
  });
  walls.build(group);
  roofs.build(group);
  console.log(`buildings: ${data.buildings.length} (${skipped} spanning the track)`);
}

// IPR Praha LOD2 buildings (real roof shapes, absolute heights). Walls get the facade texture
// (u along the wall, v up from the building's base), roofs a colour by slope. Buildings the
// track passes under are lifted clear of the tram; foundations are sunk to hide terrain gaps.
function buildLod2(group, data, route, ground) {
  const geo = data.geo.buildings, arr = geo.arr, q = geo.q;
  const facadeMat = new THREE.MeshLambertMaterial({ map: facadeTexture(), vertexColors: true, side: THREE.DoubleSide });
  const roofMat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide });
  let bIndex = 0, lifted = 0, total = 0;
  for (const ch of geo.chunks) {
    const [ox, oy, oz] = ch.o;
    const wPos = [], wNor = [], wUv = [], wCol = [], rPos = [], rNor = [], rCol = [];
    let v = ch.v;
    for (const count of ch.b) {
      // decode this building
      const xs = new Float32Array(count), ys = new Float32Array(count), zs = new Float32Array(count);
      let zmin = Infinity;
      for (let i = 0; i < count; i++, v++) {
        xs[i] = ox + arr[v * 3] * q;
        ys[i] = oy + arr[v * 3 + 1] * q;
        zs[i] = oz + arr[v * 3 + 2] * q;
        zmin = Math.min(zmin, zs[i]);
      }
      // the tram passes under it (a passage): lift everything below the wire clear of the track
      let clear = -Infinity;
      for (let i = 0; i < count; i += 3) {
        if (route.distance(xs[i], ys[i]) < 2.5) clear = Math.max(clear, ground.at(xs[i], ys[i]) + 6.3);
      }
      if (clear > zmin + 0.5) {
        lifted++;
        for (let i = 0; i < count; i++) zs[i] = Math.max(zs[i], clear);
        zmin = clear;
      } else {
        for (let i = 0; i < count; i++) if (zs[i] < zmin + 0.3) zs[i] -= 2.5; // sink the foundation
      }
      const r = rng(bIndex * 7919 + 13);
      const facade = FACADE_COLORS[Math.floor(r() * FACADE_COLORS.length)];
      const roofTile = ROOF_COLORS[Math.floor(r() * 3)], roofFlat = new THREE.Color('#77736d');
      for (let t = 0; t < count; t += 3) {
        const ax = xs[t], ay = ys[t], az = zs[t], bx = xs[t + 1], by = ys[t + 1], bz = zs[t + 1], cx = xs[t + 2], cy = ys[t + 2], cz = zs[t + 2];
        let nx = (by - ay) * (cz - az) - (bz - az) * (cy - ay);
        let ny = (bz - az) * (cx - ax) - (bx - ax) * (cz - az);
        let nz = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
        const l = Math.hypot(nx, ny, nz);
        if (l < 1e-6) continue;
        nx /= l; ny /= l; nz /= l;
        const tri = [[ax, ay, az], [bx, by, bz], [cx, cy, cz]];
        if (Math.abs(nz) > 0.3) {
          const col = Math.abs(nz) > 0.97 ? roofFlat : roofTile;
          for (const [x, y, z] of tri) { rPos.push(x, z, -y); rNor.push(nx, nz, -ny); rCol.push(col.r, col.g, col.b); }
        } else {
          const hl = Math.hypot(nx, ny) || 1, tx = -ny / hl, ty = nx / hl;
          for (const [x, y, z] of tri) {
            wPos.push(x, z, -y); wNor.push(nx, nz, -ny); wCol.push(facade.r, facade.g, facade.b);
            wUv.push((x * tx + y * ty) / 3.5, (z - zmin - 0.4) / 3.2);
          }
        }
      }
      bIndex++;
      total++;
    }
    const mk = (pos, nor, col, uv, mat) => {
      if (!pos.length) return;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
      g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      if (uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, mat);
      m.matrixAutoUpdate = false;
      group.add(m);
    };
    mk(wPos, wNor, wCol, wUv, facadeMat);
    mk(rPos, rNor, rCol, null, roofMat);
  }
  console.log(`LOD2 buildings: ${total} (${lifted} spanning the track)`);
}

// Terrain mesh in chunks near the route, coloured by land cover (parks, woods, water).
function buildTerrain(group, data, route, T, weather) {
  const { nx, ny } = T;
  const cls = new Uint8Array(nx * ny); // 0 ground, 1 grass, 2 wood, 3 water
  const mark = (ring, v) => {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of ring) { minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]); minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); }
    const i0 = Math.max(0, Math.floor((minX - T.x0) / T.dx)), i1 = Math.min(nx - 1, Math.ceil((maxX - T.x0) / T.dx));
    const j0 = Math.max(0, Math.floor((maxY - T.y0) / T.dy)), j1 = Math.min(ny - 1, Math.ceil((minY - T.y0) / T.dy));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      if (pointInRing(T.x0 + i * T.dx, T.y0 + j * T.dy, ring)) cls[j * nx + i] = v;
    }
  };
  for (const g of data.green) mark(g.p, g.t === 'wood' ? 2 : 1);
  for (const w of data.water) mark(w, 3);

  const autumn = weather === 'leaves';
  const palette = [
    new THREE.Color(weather === 'dry' ? '#8d8c80' : '#77766c'),
    new THREE.Color(autumn ? '#8a8a4a' : '#6f8a4e'),
    new THREE.Color(autumn ? '#7a6a3a' : '#566f3c'),
    new THREE.Color('#5d7f95'),
  ];
  // which chunks are close enough to the route to matter
  const samples = [];
  for (let s = 0; s <= route.length; s += 60) { const p = route.at(s); samples.push([p.x, p.y]); }
  const mat = new THREE.MeshLambertMaterial({ vertexColors: true });
  const C = TERRAIN_CHUNK;
  for (let cj = 0; cj < ny - 1; cj += C) {
    for (let ci = 0; ci < nx - 1; ci += C) {
      const cx = T.x0 + (ci + C / 2) * T.dx, cy = T.y0 + (cj + C / 2) * T.dy;
      if (!samples.some((p) => Math.abs(p[0] - cx) < 1000 && Math.abs(p[1] - cy) < 1000 && Math.hypot(p[0] - cx, p[1] - cy) < 1000)) continue;
      const w = Math.min(C, nx - 1 - ci) + 1, h = Math.min(C, ny - 1 - cj) + 1;
      const pos = new Float32Array(w * h * 3), nor = new Float32Array(w * h * 3), col = new Float32Array(w * h * 3);
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
        const gi = ci + i, gj = cj + j, k = (j * w + i) * 3;
        const x = T.x0 + gi * T.dx, y = T.y0 + gj * T.dy;
        pos[k] = x; pos[k + 1] = T.cell(gi, gj); pos[k + 2] = -y;
        // normal from central differences
        const hx = (T.cell(gi + 1, gj) - T.cell(gi - 1, gj)) / (2 * T.dx);
        const hy = (T.cell(gi, gj + 1) - T.cell(gi, gj - 1)) / (2 * T.dy);
        const l = Math.hypot(hx, 1, hy);
        nor[k] = -hx / l; nor[k + 1] = 1 / l; nor[k + 2] = hy / l;
        const c = palette[cls[gj * nx + gi]];
        col[k] = c.r; col[k + 1] = c.g; col[k + 2] = c.b;
      }
      const idx = [];
      for (let j = 0; j < h - 1; j++) for (let i = 0; i < w - 1; i++) {
        const a = j * w + i, b = a + 1, c = a + w, d = c + 1;
        // grid rows go south (dy < 0), so this winding faces up
        idx.push(a, c, b, b, c, d);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
      g.setAttribute('color', new THREE.BufferAttribute(col, 3));
      g.setIndex(idx);
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, mat);
      m.matrixAutoUpdate = false;
      group.add(m);
    }
  }
}

// Deck, parapets and piers for bridges on the route (e.g. Most Legií).
function buildBridges(group, data, route, ground) {
  const sideMat = new THREE.MeshLambertMaterial({ color: 0x7f786c });
  const cg = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true }), { color: true });
  const deckCol = new THREE.Color('#8f897e').toArray(), sideCol = new THREE.Color('#7a7366').toArray();
  for (const [s0, s1] of data.bridges) {
    const halfW = 9;
    const pts = [];
    for (let s = s0 - 2; s <= s1 + 2; s += 3) {
      const o = route.at(s), h = route.heading(s, 3), z = ground.profile.height(s);
      pts.push({ x: o.x, y: o.y, nx: -h.hy, ny: h.hx, z });
    }
    const c = cg._chunk(pts[0].x, pts[0].y);
    for (let i = 0; i < pts.length - 1; i++) {
      const p = pts[i], q = pts[i + 1];
      for (const side of [1, -1]) {
        const pa = [p.x + p.nx * halfW * side, p.y + p.ny * halfW * side], qa = [q.x + q.nx * halfW * side, q.y + q.ny * halfW * side];
        // fascia from deck down 1.6 m and parapet up 1.1 m
        cg.quad(c, W(pa[0], pa[1], p.z - 1.6), W(qa[0], qa[1], q.z - 1.6), W(qa[0], qa[1], q.z + 1.1), W(pa[0], pa[1], p.z + 1.1), sideCol);
        cg.quad(c, W(qa[0], qa[1], q.z - 1.6), W(pa[0], pa[1], p.z - 1.6), W(pa[0], pa[1], p.z + 1.1), W(qa[0], qa[1], q.z + 1.1), sideCol);
      }
      // deck underside
      const l0 = [p.x + p.nx * halfW, p.y + p.ny * halfW], r0 = [p.x - p.nx * halfW, p.y - p.ny * halfW];
      const l1 = [q.x + q.nx * halfW, q.y + q.ny * halfW], r1 = [q.x - q.nx * halfW, q.y - q.ny * halfW];
      cg.quad(c, W(l0[0], l0[1], p.z - 1.6), W(l1[0], l1[1], q.z - 1.6), W(r1[0], r1[1], q.z - 1.6), W(r0[0], r0[1], p.z - 1.6), deckCol);
      cg.quad(c, W(r0[0], r0[1], p.z + 0.1), W(r1[0], r1[1], q.z + 0.1), W(l1[0], l1[1], q.z + 0.1), W(l0[0], l0[1], p.z + 0.1), deckCol);
    }
    // piers every ~45 m
    for (let s = s0 + 30; s < s1 - 15; s += 45) {
      const o = route.at(s), z = ground.profile.height(s);
      const zg = ground.terrain.height(o.x, o.y) - 2;
      const pier = new THREE.Mesh(new THREE.BoxGeometry(4, Math.max(1, z - 1.6 - zg), 16), sideMat);
      const h = route.heading(s, 3);
      pier.position.set(o.x, (z - 1.6 + zg) / 2, -o.y);
      pier.rotation.y = Math.atan2(h.hx, -h.hy);
      group.add(pier);
    }
  }
  cg.build(group);
}

function buildTrees(group, data, route, ground, weather) {
  const r = rng(99);
  const spots = [];
  const real = data.geo?.trees;
  if (real) {
    for (const [x, y] of real) {
      if (route.distance(x, y) < 3.5) continue;
      spots.push([x, y, 0.75 + r() * 0.6, ground.at(x, y)]);
    }
  }
  for (const g of data.green) {
    if (real && g.t !== 'wood') continue; // the city tree register covers streets and parks
    const ring = g.p;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of ring) { minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0]); minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1]); }
    const area = Math.abs(signedArea(ring));
    const n = Math.min(400, Math.floor(area / (g.t === 'wood' ? 90 : 500)));
    for (let i = 0; i < n * 2 && spots.length < 9000; i++) {
      const x = minX + r() * (maxX - minX), y = minY + r() * (maxY - minY);
      if (!pointInRing(x, y, ring)) continue;
      if (route.distance(x, y) < 6) continue;
      spots.push([x, y, 0.7 + r() * 0.7, ground.terrain.height(x, y)]);
    }
  }
  if (!spots.length) return;
  const crown = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(2.6, 0), new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), spots.length);
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.18, 0.25, 3, 5), new THREE.MeshLambertMaterial({ color: 0x5b4632 }), spots.length);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(), p = new THREE.Vector3();
  const col = new THREE.Color();
  spots.forEach(([x, y, k, z], i) => {
    s.set(k * 1.1, k * 1.4, k * 1.1);
    p.set(x, z + 5.4 * k, -y);
    m.compose(p, q, s);
    crown.setMatrixAt(i, m);
    if (weather === 'leaves') col.setHSL(0.05 + r() * 0.08, 0.55 + r() * 0.2, 0.32 + r() * 0.12);
    else col.setHSL(0.24 + r() * 0.06, 0.35 + r() * 0.15, 0.25 + r() * 0.1);
    crown.setColorAt(i, col);
    s.set(1, k, 1);
    p.set(x, z + 1.5 * k, -y);
    m.compose(p, q, s);
    trunk.setMatrixAt(i, m);
  });
  group.add(crown, trunk);
}

function buildCatenary(group, data, route, ground) {
  // contact wire 5.6 m above every track; Prague-style cross-span wires between poles on
  // both sides of the street every ~32 m
  const wire = [];
  for (const t of data.tracks) {
    const line = t.smooth, z = t.z;
    for (let i = 0; i < line.length - 1; i += 2) {
      const j = Math.min(line.length - 1, i + 2);
      wire.push(new THREE.Vector3(line[i][0], z[i] + 5.6, -line[i][1]), new THREE.Vector3(line[j][0], z[j] + 5.6, -line[j][1]));
    }
  }
  const poles = [];
  for (let s = 10; s <= route.length; s += 32) poles.push(s);
  const poleMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.17, 7.4, 6), new THREE.MeshLambertMaterial({ color: 0x4b5a4f }), poles.length * 2);
  const m = new THREE.Matrix4();
  let n = 0;
  poles.forEach((s) => {
    const z = ground.profile.height(s);
    const r = route.offset(s, -3.7), l = route.offset(s, 7.0);
    for (const o of [r, l]) {
      m.makeTranslation(o.x, z + 3.7, -o.y);
      poleMesh.setMatrixAt(n++, m);
    }
    // span wire across both tracks, droppers down to each contact wire
    wire.push(new THREE.Vector3(r.x, z + 6.6, -r.y), new THREE.Vector3(l.x, z + 6.6, -l.y));
    for (const lat of [0, 3.2]) {
      const c = route.offset(s, lat);
      wire.push(new THREE.Vector3(c.x, z + 6.6, -c.y), new THREE.Vector3(c.x, z + 5.6, -c.y));
    }
  });
  const wg = new THREE.BufferGeometry().setFromPoints(wire);
  group.add(new THREE.LineSegments(wg, new THREE.LineBasicMaterial({ color: 0x222222 })), poleMesh);
}

// Retaining walls where the track is cut into a hillside (e.g. Chotkova), with a flat cap
// covering the terrain lowered behind them.
function buildWalls(group, data, route, ground) {
  const cg = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { color: true });
  const stone = new THREE.Color('#8a8172').toArray(), coping = new THREE.Color('#9c968a').toArray(), cap = new THREE.Color('#6f7d55').toArray();
  // real retaining walls (IPR Praha): line + height
  const realPts = new Map();
  const key = (x, y) => `${Math.floor(x / 8)},${Math.floor(y / 8)}`;
  for (const w of data.geo?.walls || []) {
    const line = densify(w.p, 2);
    const c = cg._chunk(line[0][0], line[0][1]);
    const half = 0.25;
    const edge = line.map((p, i) => {
      const a = line[Math.max(0, i - 1)], b = line[Math.min(line.length - 1, i + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
      const nx = -dy / l, ny = dx / l;
      const g1 = ground.at(p[0] + nx * 1.5, p[1] + ny * 1.5), g2 = ground.at(p[0] - nx * 1.5, p[1] - ny * 1.5);
      const bottom = Math.min(g1, g2) - 0.4, top = Math.max(Math.max(g1, g2) + 0.3, bottom + 0.4 + w.h);
      realPts.set(key(p[0], p[1]), true);
      return { L: [p[0] + nx * half, p[1] + ny * half], R: [p[0] - nx * half, p[1] - ny * half], bottom, top };
    });
    for (let i = 0; i < edge.length - 1; i++) {
      const a = edge[i], b = edge[i + 1];
      for (const side of ['L', 'R']) {
        cg.quad(c, W(...a[side], a.bottom), W(...b[side], b.bottom), W(...b[side], b.top), W(...a[side], a.top), stone);
      }
      cg.quad(c, W(...a.L, a.top), W(...b.L, b.top), W(...b.R, b.top), W(...a.R, a.top), coping);
    }
  }
  const nearReal = (x, y) => {
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) if (realPts.has(`${Math.floor(x / 8) + i},${Math.floor(y / 8) + j}`)) return true;
    return false;
  };
  const runs = ground.walls?.runs || [];
  const B = ground.walls.bench, Rch = ground.walls.reach + 3;
  for (const run of runs) {
    if (run.pts.length < 2) continue;
    const c = cg._chunk(...(() => { const o = route.at(run.pts[0].s); return [o.x, o.y]; })());
    for (let i = 0; i < run.pts.length - 1; i++) {
      const a = run.pts[i], b = run.pts[i + 1];
      const za = ground.profile.height(a.s), zb = ground.profile.height(b.s);
      const fa = route.offset(a.s, run.side * B), fb = route.offset(b.s, run.side * B);
      const ka = route.offset(a.s, run.side * (B + 0.5)), kb = route.offset(b.s, run.side * (B + 0.5));
      const ca = route.offset(a.s, run.side * Rch), cb = route.offset(b.s, run.side * Rch);
      // wall face (unless a real surveyed wall stands here)
      if (!nearReal(fa.x, fa.y)) cg.quad(c, W(fa.x, fa.y, za - 0.3), W(fb.x, fb.y, zb - 0.3), W(fb.x, fb.y, b.top), W(fa.x, fa.y, a.top), stone);
      // coping stones and the cap of hillside behind the wall
      cg.quad(c, W(fa.x, fa.y, a.top + 0.15), W(fb.x, fb.y, b.top + 0.15), W(kb.x, kb.y, b.top + 0.15), W(ka.x, ka.y, a.top + 0.15), coping);
      cg.quad(c, W(fa.x, fa.y, a.top), W(fb.x, fb.y, b.top), W(fb.x, fb.y, b.top + 0.15), W(fa.x, fa.y, a.top + 0.15), coping);
      cg.quad(c, W(ka.x, ka.y, a.top + 0.05), W(kb.x, kb.y, b.top + 0.05), W(cb.x, cb.y, b.top + 0.05), W(ca.x, ca.y, a.top + 0.05), cap);
    }
  }
  cg.build(group);
}

// Text label plane (for stop signs).
export function textPlane(text, { w = 2.2, h = 0.5, bg = '#ffffff', fg = '#111111', font = 'bold 38px sans-serif' } = {}) {
  const cv = document.createElement('canvas');
  cv.width = 512; cv.height = Math.round(512 * (h / w));
  const g = cv.getContext('2d');
  g.fillStyle = bg;
  g.fillRect(0, 0, cv.width, cv.height);
  g.fillStyle = fg;
  g.font = font;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  let size = parseInt(font.match(/(\d+)px/)[1], 10);
  while (g.measureText(text).width > cv.width - 20 && size > 12) {
    size -= 2;
    g.font = font.replace(/\d+px/, `${size}px`);
  }
  g.fillText(text, cv.width / 2, cv.height / 2);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  return new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: t, side: THREE.DoubleSide }));
}
