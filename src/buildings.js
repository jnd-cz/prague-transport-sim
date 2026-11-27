// SPDX-License-Identifier: AGPL-3.0-or-later
// The buildings: the 3D city model's (LOD2) with their façade and roof textures and the landmarks drawn past the
// fog, else OSM's footprints extruded; the roofs' index for what stands on them.
import * as THREE from 'three';
import { rng } from './random.js';
import { STREET_BELOW } from './heights.js';
import { LANDMARK_TALL, LANDMARK_HIGH, LANDMARK_RISE, landmarkHaze, textureMean } from './landmarks.js';
import { weatherize } from './weather.js';
import { GFX } from './gfx.js';
import { ChunkedGeometry, FootprintIndex, GROUND_SNOW, W, addFlatPolygon, pointInRing, signedArea } from './worldMesh.js';

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

// Facade textures by building type: prefab panel blocks (paneláky), churches, industrial halls
// and glass office fronts. Each tile is white-ish and tinted per building by vertex colour.
function panelTexture() {
  // tile 3.6 m x 2.8 m: concrete panel with joints, a window, every other column a loggia
  const cv = document.createElement('canvas');
  cv.width = 256; cv.height = 200;
  const g = cv.getContext('2d');
  g.fillStyle = '#f2f0ea'; g.fillRect(0, 0, 256, 200);
  g.fillStyle = '#d8d4cb'; g.fillRect(0, 0, 256, 3); g.fillRect(0, 0, 3, 200);
  g.fillStyle = '#e4e1da'; g.fillRect(16, 150, 224, 18); // parapet band
  g.fillStyle = '#9aa3a8'; g.fillRect(40, 40, 96, 100);   // window
  g.fillStyle = '#2d3a44'; g.fillRect(46, 46, 84, 88);
  g.fillStyle = '#9aa3a8'; g.fillRect(86, 46, 4, 88);
  g.fillStyle = '#4a4f52'; g.fillRect(160, 30, 80, 120);  // loggia recess
  g.fillStyle = '#d6d2c8'; g.fillRect(156, 108, 88, 42);  // loggia parapet
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
function churchTexture() {
  // tile 5 m x 9 m: ashlar stone and one tall arched window
  const cv = document.createElement('canvas');
  cv.width = 128; cv.height = 230;
  const g = cv.getContext('2d');
  g.fillStyle = '#ffffff'; g.fillRect(0, 0, 128, 230);
  g.strokeStyle = 'rgba(0,0,0,.10)'; g.lineWidth = 1;
  for (let y = 0; y < 230; y += 12) { g.beginPath(); g.moveTo(0, y); g.lineTo(128, y); g.stroke();
    for (let x = (y / 12) % 2 ? 0 : 16; x < 128; x += 32) { g.beginPath(); g.moveTo(x, y); g.lineTo(x, y + 12); g.stroke(); } }
  g.fillStyle = '#2b2f36';
  g.beginPath(); g.moveTo(44, 190); g.lineTo(44, 70); g.arc(64, 70, 20, Math.PI, 0); g.lineTo(84, 190); g.closePath(); g.fill();
  g.strokeStyle = '#8a8f96'; g.lineWidth = 2;
  g.beginPath(); g.moveTo(64, 52); g.lineTo(64, 190); g.moveTo(44, 120); g.lineTo(84, 120); g.stroke();
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
function industrialTexture() {
  // tile 6 m x 4 m: vertical cladding ribs and a ribbon window
  const cv = document.createElement('canvas');
  cv.width = 192; cv.height = 128;
  const g = cv.getContext('2d');
  g.fillStyle = '#f4f4f4'; g.fillRect(0, 0, 192, 128);
  g.fillStyle = 'rgba(0,0,0,.07)';
  for (let x = 0; x < 192; x += 8) g.fillRect(x, 0, 3, 128);
  g.fillStyle = '#3a4650'; g.fillRect(0, 34, 192, 22);
  g.fillStyle = '#9aa0a4'; for (let x = 0; x < 192; x += 48) g.fillRect(x, 34, 3, 22);
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}
function glassTexture() {
  // tile 1.5 m x 3.6 m: curtain wall with mullions and a spandrel band
  const cv = document.createElement('canvas');
  cv.width = 64; cv.height = 154;
  const g = cv.getContext('2d');
  const gr = g.createLinearGradient(0, 0, 64, 154);
  gr.addColorStop(0, '#9fb6c6'); gr.addColorStop(1, '#55697a');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 154);
  g.fillStyle = '#d9dcdf'; g.fillRect(0, 0, 3, 154); g.fillRect(0, 124, 64, 30);
  const t = new THREE.CanvasTexture(cv);
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  return t;
}

const FACADE_COLORS = ['#e8d9b5', '#d9c7a0', '#efe3c8', '#c9b79a', '#e3c9b0', '#d6d0c2', '#e6d2a8', '#cfc3ad',
  '#e0b9a0', '#b9c4c9', '#d8cfb8', '#f0e6d2'].map((c) => new THREE.Color(c));
const MODEL_UNDER = 0.05; // m: a bridge model's top lies this far under the bed top inside the trams' sweep (#742) ...
const MODEL_REACH = 0.5;  // m: ... its corners from there up to this far over the rail heads
const ROOF_COLORS = ['#8c4a32', '#7a3f2c', '#5f5a55', '#6d6862', '#9a5638', '#4f4b47'].map((c) => new THREE.Color(c));

// Fallback: OSM footprints extruded to their tagged height, sitting on the terrain.
export function buildOsmBuildings(group, data, route, ground) {
  // (snow on the roofs: the faces that point up)
  const facadeMat = weatherize(new THREE.MeshLambertMaterial({ map: facadeTexture(), vertexColors: true }), { snow: GROUND_SNOW });
  const roofMat = weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { snow: GROUND_SNOW });
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
      for (const p of ring) ht = Math.max(ht, ground.at(p[0], p[1], true));
      base = Math.max(ht, ground.at(cx, cy, true)) + 6.4;
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
  walls.build(group, 'building');
  roofs.build(group, 'building');
  console.log(`buildings: ${data.buildings.length} (${skipped} spanning the track)`);
}

// IPR Praha LOD2 buildings (real roof shapes, absolute heights). Walls get the facade texture
// (u along the wall, v up from the building's base), roofs a colour by slope. Buildings the
// track passes under are lifted clear of the tram; foundations are sunk to hide terrain gaps.
// building type from the OSM footprint under it, the roof shape and the size
const CHURCH = new Set(['church', 'cathedral', 'chapel', 'religious', 'synagogue', 'mosque', 'temple', 'monastery']);
const INDUSTRIAL = new Set(['industrial', 'warehouse', 'garage', 'garages', 'service', 'hangar', 'factory', 'manufacture',
  'storage_tank', 'transportation', 'train_station', 'shed', 'depot', 'parking']);
const OFFICE = new Set(['office', 'commercial', 'retail', 'hotel', 'supermarket', 'hospital', 'university', 'public']);
const RESID = new Set(['apartments', 'residential', 'yes', 'dormitory', 'flats']);
function buildingClass(kind, flatShare, height, area) {
  if (CHURCH.has(kind)) return 'church';
  if (INDUSTRIAL.has(kind)) return 'industrial';
  if (OFFICE.has(kind) && flatShare > 0.8 && height > 12) return 'glass';
  if (RESID.has(kind) && flatShare > 0.85 && height >= 15 && area >= 250) return 'panel';
  if (flatShare > 0.9 && height < 9 && area > 600) return 'industrial';
  return 'old';
}
const CLASS_COLORS = {
  panel: ['#e9e6dc', '#d9dde0', '#efe2c4', '#dfe8d6', '#f0d9c8', '#d7dbe6'],
  church: ['#d8cfb8', '#cbc0a6', '#e2dccb', '#bfb59d'],
  industrial: ['#c9cbcc', '#b8bcbf', '#d6d2c4', '#a9b1b6'],
  glass: ['#ffffff', '#e6eef4', '#dfe6e0'],
};

export function buildLod2(group, data, route, ground) {
  const geo = data.geo.buildings, arr = geo.arr, q = geo.q;
  const side = GFX.side; // (both faces, or ?gfx=front the front ones only, to measure what the back ones cost: #705)
  const CLASSES = {
    // (snow on whatever points up: roofs, ledges)
    old: { mat: weatherize(new THREE.MeshLambertMaterial({ map: facadeTexture(), vertexColors: true, side }), { snow: GROUND_SNOW }), w: 3.5, h: 3.2 },
    panel: { mat: weatherize(new THREE.MeshLambertMaterial({ map: panelTexture(), vertexColors: true, side }), { snow: GROUND_SNOW }), w: 3.6, h: 2.8 },
    church: { mat: weatherize(new THREE.MeshLambertMaterial({ map: churchTexture(), vertexColors: true, side }), { snow: GROUND_SNOW }), w: 5, h: 9 },
    industrial: { mat: weatherize(new THREE.MeshLambertMaterial({ map: industrialTexture(), vertexColors: true, side }), { snow: GROUND_SNOW }), w: 6, h: 4 },
    glass: { mat: weatherize(new THREE.MeshLambertMaterial({ map: glassTexture(), vertexColors: true, side }), { snow: GROUND_SNOW }), w: 1.5, h: 3.6 },
  };
  // OSM footprints say what a building is (church, apartments, warehouse ...)
  const osm = new FootprintIndex(data.buildings.map((b) => b.p));
  const kindAt = (x, y) => {
    const arr2 = osm.map.get(`${Math.floor(x / osm.cell)},${Math.floor(y / osm.cell)}`);
    if (!arr2) return 'yes';
    for (const e of arr2) if (x >= e.minX && x <= e.maxX && y >= e.minY && y <= e.maxY && pointInRing(x, y, e.ring)) return e.kind || 'yes';
    return 'yes';
  };
  data.buildings.forEach((b, i) => { osm.entries[i].kind = b.k; });
  const counts = {};
  const roofMat = weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side }), { snow: GROUND_SNOW });
  let bIndex = 0, lifted = 0, total = 0;
  // the car roads on bridges: a bridge model is cut out over them too (half their width, 0.4-4.5 m over
  // their surface; parapet blocks 1.2-1.7 m over the deck stood in the lanes, the lint deckClip)
  const bridgeRoads = new Map(), RC = 20;
  for (const r of data.roads) {
    if (!r.b || !r.c) continue;
    const hf = ground.way(r.way || r.p, true);
    for (let i = 1; i < r.p.length; i++) {
      const a = r.p[i - 1], b = r.p[i], seg = { a, b, hw: r.w / 2, hf };
      for (let gx = Math.floor((Math.min(a[0], b[0]) - 25) / RC); gx <= Math.floor((Math.max(a[0], b[0]) + 25) / RC); gx++) {
        for (let gy = Math.floor((Math.min(a[1], b[1]) - 25) / RC); gy <= Math.floor((Math.max(a[1], b[1]) + 25) / RC); gy++) {
          const k = gx * 100003 + gy;
          if (!bridgeRoads.has(k)) bridgeRoads.set(k, []);
          bridgeRoads.get(k).push(seg);
        }
      }
    }
  }
  // the bridge road under (x, y) within its half width (+ how far), or null
  const roadUnder = (x, y, pad = 0) => {
    for (const sg of bridgeRoads.get(Math.floor(x / RC) * 100003 + Math.floor(y / RC)) || []) {
      const { a, b } = sg, ex = b[0] - a[0], ey = b[1] - a[1], l2 = ex * ex + ey * ey || 1e-9;
      const t = Math.max(0, Math.min(1, ((x - a[0]) * ex + (y - a[1]) * ey) / l2));
      if (Math.hypot(a[0] + ex * t - x, a[1] + ey * t - y) < sg.hw + pad) return sg;
    }
    return null;
  };
  // (x, y) in the space the trams sweep in plan, ours and the opposite track's (3 m beyond each, the profile's
  // cross-section): the top of rail `zr` and the bed top `zb` there, else null (n: its nearest route point)
  const sweep = (x, y, n = route.nearest(x, y)) => {
    if (!n) return null;
    const o = ground.profile.backOffset(n.s);
    if (n.d > Math.abs(o) + 3.5) return null;
    const q = route.at(n.s), l = q.hx * (y - q.y) - q.hy * (x - q.x); // (left > 0, as src/world.js lateralOf)
    if (l < Math.min(0, o) - 3 || l > Math.max(0, o) + 3) return null;
    // (each track's own rails and bed to the line midway between them: the cross-section's line from one track to
    // the other left the model 0.22 m over our bed where the other track stands higher, line 22 s 18184)
    const lb = ground.profile.onBack(n.s, l) ? o : 0, zr = ground.profile.heightAt(n.s, lb);
    return { zr, zb: zr - ground.profile.lift(n.s, lb) };
  };
  // landmarks (src/landmarks.js): in meshes of their own with a lighter haze, and their triangles copied for the pass
  // past the far plane; "high ground" over the line's typical ground, the median along its route
  const along = [];
  for (let s = 0; s < route.length; s += 50) { const p = route.at(s); along.push(ground.at(p.x, p.y)); }
  along.sort((a, b) => a - b);
  const baseMed = along[along.length >> 1] ?? 0;
  const lmPos = [], lmNor = [], lmCol = [], lmMats = new Map();
  let lmCount = 0;
  const lmList = []; // [x, y, height, base]: which buildings the rule picked (window.landmarks.list)
  const lmMat = (m) => {
    if (!lmMats.has(m)) lmMats.set(m, landmarkHaze(weatherize(m.clone(), m.userData.weather)));
    return lmMats.get(m);
  };
  for (const ch of geo.chunks) {
    const [ox, oy, oz] = ch.o;
    const walls = {}, wallsL = {};
    for (const k in CLASSES) { walls[k] = { pos: [], nor: [], uv: [], col: [] }; wallsL[k] = { pos: [], nor: [], uv: [], col: [] }; }
    const rPos = [], rNor = [], rCol = [], lrPos = [], lrNor = [], lrCol = [];
    let v = ch.v;
    for (const [bi, count] of ch.b.entries()) {
      const isBridge = ch.k?.[bi] === 1; // Mosty 3D: concrete, never lifted or sunk
      // decode this building
      let xs = new Float32Array(count), ys = new Float32Array(count), zs = new Float32Array(count);
      let zmin = Infinity;
      for (let i = 0; i < count; i++, v++) {
        xs[i] = ox + arr[v * 3] * q;
        ys[i] = oy + arr[v * 3 + 1] * q;
        zs[i] = oz + arr[v * 3 + 2] * q;
        zmin = Math.min(zmin, zs[i]);
      }
      // a bridge model near our track: triangles split to <= 1.5 m, so the tram's envelope (below) cuts
      // just that space out of it (a coarse block's top, 1.6-1.9 m over the surveyed bed, spanned the
      // track with triangles whose centres lay outside the envelope: Modřany s 5070, 5824)
      let n3 = count;
      if (isBridge) {
        const near = (t) => [0, 1, 2].some((k) => route.distance(xs[t + k], ys[t + k]) < 25 || roadUnder(xs[t + k], ys[t + k], 25) || ground.dtm?.deckAt(xs[t + k], ys[t + k]) != null);
        const out = [];
        const split = (a, b, c, depth) => {
          const l = (p, q2) => Math.hypot(p[0] - q2[0], p[1] - q2[1], p[2] - q2[2]);
          const lab = l(a, b), lbc = l(b, c), lca = l(c, a), m = Math.max(lab, lbc, lca);
          if (m <= 1.5 || depth > 10) { out.push(a, b, c); return; }
          const mid = (p, q2) => [(p[0] + q2[0]) / 2, (p[1] + q2[1]) / 2, (p[2] + q2[2]) / 2];
          if (m === lab) { const d = mid(a, b); split(a, d, c, depth + 1); split(d, b, c, depth + 1); }
          else if (m === lbc) { const d = mid(b, c); split(a, b, d, depth + 1); split(a, d, c, depth + 1); }
          else { const d = mid(c, a); split(a, b, d, depth + 1); split(d, b, c, depth + 1); }
        };
        for (let t = 0; t < count; t += 3) {
          const P = [0, 1, 2].map((k) => [xs[t + k], ys[t + k], zs[t + k]]);
          if (near(t)) split(P[0], P[1], P[2], 0);
          else out.push(...P);
        }
        if (out.length !== count) {
          n3 = out.length;
          xs = Float32Array.from(out, (p) => p[0]); ys = Float32Array.from(out, (p) => p[1]); zs = Float32Array.from(out, (p) => p[2]);
        }
      }
      // the tram passes under it (a passage): lift everything below the wire clear of the track
      let clear = -Infinity;
      for (let i = 0; i < n3; i += 3) {
        if (route.distance(xs[i], ys[i]) < 2.5) clear = Math.max(clear, ground.at(xs[i], ys[i], true) + 6.3);
      }
      if (isBridge) clear = -Infinity;
      if (clear > zmin + 0.5) {
        lifted++;
        for (let i = 0; i < n3; i++) zs[i] = Math.max(zs[i], clear);
        zmin = clear;
      } else if (!isBridge) {
        for (let i = 0; i < n3; i++) if (zs[i] < zmin + 0.3) zs[i] -= 2.5; // sink the foundation
      }
      const r = rng(bIndex * 7919 + 13);
      // classify: roof flatness, height, footprint size, OSM tag under the centroid
      let flat = 0, roof = 0, zmax = -Infinity, minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, cxs = 0, cys = 0;
      for (let t = 0; t < n3; t += 3) {
        const ux = xs[t + 1] - xs[t], uy = ys[t + 1] - ys[t], uz = zs[t + 1] - zs[t], vx = xs[t + 2] - xs[t], vy = ys[t + 2] - ys[t], vz = zs[t + 2] - zs[t];
        const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, l = Math.hypot(nx, ny, nz);
        if (l > 1e-6 && Math.abs(nz) / l > 0.3) { roof += l; if (Math.abs(nz) / l > 0.97) flat += l; }
      }
      for (let i = 0; i < n3; i++) {
        zmax = Math.max(zmax, zs[i]); cxs += xs[i]; cys += ys[i];
        minX = Math.min(minX, xs[i]); maxX = Math.max(maxX, xs[i]); minY = Math.min(minY, ys[i]); maxY = Math.max(maxY, ys[i]);
      }
      const cls = buildingClass(kindAt(cxs / n3, cys / n3), roof ? flat / roof : 0, zmax - zmin, (maxX - minX) * (maxY - minY) * 0.6);
      counts[isBridge ? 'bridge' : cls] = (counts[isBridge ? 'bridge' : cls] || 0) + 1;
      const lm = !isBridge && (zmax - zmin >= LANDMARK_TALL || (zmax - zmin >= LANDMARK_HIGH && zmin >= baseMed + LANDMARK_RISE));
      if (lm) { lmCount++; lmList.push([Math.round(cxs / n3), Math.round(cys / n3), Math.round(zmax - zmin), Math.round(zmin)]); }
      const C = CLASSES[cls], W = (lm ? wallsL : walls)[cls], pal = CLASS_COLORS[cls];
      const RP = lm ? lrPos : rPos, RN = lm ? lrNor : rNor, RC2 = lm ? lrCol : rCol;
      const facade = pal ? new THREE.Color(pal[Math.floor(r() * pal.length)]) : FACADE_COLORS[Math.floor(r() * FACADE_COLORS.length)];
      const roofTile = ROOF_COLORS[Math.floor(r() * 3)], roofFlat = new THREE.Color('#77736d');
      for (let t = 0; t < n3; t += 3) {
        const ax = xs[t], ay = ys[t], bx = xs[t + 1], by = ys[t + 1], cx = xs[t + 2], cy = ys[t + 2];
        let az = zs[t], bz = zs[t + 1], cz = zs[t + 2];
        // nothing of a bridge model inside the space the trams sweep (±3 m of our track and of the opposite one, from
        // just over the rail heads to 5.8 m above them): at the north end of Čechův most a slab 3.7 m above the deck
        // cut through the tram, and the model's top 0-0.5 m over the real deck would cover the rails (src/heights.js)
        if (isBridge) {
          const mx = (ax + bx + cx) / 3, my = (ay + by + cy) / 3, n = route.nearest(mx, my);
          const sw = sweep(mx, my, n), mz0 = (az + bz + cz) / 3;
          if (sw && mz0 > sw.zr + 0.02 && mz0 < sw.zr + 5.8) continue;
          // (and under that space the model lies under the bed, not in the ballast up to the rail heads: its corners
          // within the sweep come down to MODEL_UNDER under the bed top, the opposite track's bed under its rails
          // (the profile's cross-section, #197: on main its rails ran on the model's top). Krejcárek, line 37: the track climbs
          // 6.2 % onto the viaduct's north end, numeric DI of 2023 and the archive alike, where the coarse model's top
          // falls 2 %: it stood 0.06-0.19 m over the bed top at s 3480-3488, and 0.04-0.06 m over it before the
          // south abutment, s 3030-3038, #742. A triangle's corners lie within 1.5 m of its centre: the split above)
          if (n && n.d < 14) {
            const under = (x, y, z) => {
              const w = sweep(x, y);
              // (to MODEL_REACH over the rail heads only: a road bridge's underside 5.6 m over the track came down
              // as spikes, line 22 s 18184)
              return w && z > w.zb - MODEL_UNDER && z < w.zr + MODEL_REACH ? w.zb - MODEL_UNDER : z;
            };
            az = under(ax, ay, az); bz = under(bx, by, bz); cz = under(cx, cy, cz);
          }
          // (over a flat deck, flushDtm, the deck and its parapets are the survey's: the model's top showed between the
          // survey's areas as grey bars across the ballast, and its edge beam as teeth along the deck's edge, #549)
          if (n && n.d < 8 && ground.dtm?.flatDeck?.(n.s)) {
            // (by its highest corner: by the centre, the corners of the split triangles poked through the ballast)
            const zd = ground.profile.height(n.s) - ground.profile.lift(n.s) - STREET_BELOW, hz = Math.max(az, bz, cz);
            // (and only wholly over the survey's deck: past its end the model is the deck, and cut it left a hole under
            // the track before the abutment, s 3032-3038)
            const onDeck = (x, y) => ground.dtm.deckAt(x, y, zd, 0.5) !== null;
            if (hz > zd - 0.1 && Math.min(az, bz, cz) < zd + 5.8 && onDeck(ax, ay) && onDeck(bx, by) && onDeck(cx, cy)) continue;
          }
          const rd = roadUnder(mx, my);
          if (rd) {
            const zr = rd.hf(mx, my), mz = (az + bz + cz) / 3;
            if (mz > zr + 0.14 && mz < zr + 4.5) continue; // (from just over the ribbon, drawn 0.12 over zr)
          }
          // trimmed to the surveyed deck where there is one (the survey is exact, the model coarse: at
          // Štefánikův most its top stood in the track and the roads): nothing over it (to 4.7 m)
          const mz = (az + bz + cz) / 3, zd = ground.dtm?.deckAt(mx, my, mz - 2.35, 2.35);
          if (zd !== null && zd !== undefined && mz > zd) continue;
        }
        let nx = (by - ay) * (cz - az) - (bz - az) * (cy - ay);
        let ny = (bz - az) * (cx - ax) - (bx - ax) * (cz - az);
        let nz = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
        const l = Math.hypot(nx, ny, nz);
        if (l < 1e-6) continue;
        nx /= l; ny /= l; nz /= l;
        const tri = [[ax, ay, az], [bx, by, bz], [cx, cy, cz]];
        if (isBridge) {
          const k = 0.75 + 0.25 * Math.abs(nz);
          for (const [x, y, z] of tri) { rPos.push(x, z, -y); rNor.push(nx, nz, -ny); rCol.push(0.62 * k, 0.61 * k, 0.58 * k); }
        } else if (Math.abs(nz) > 0.3) {
          const col = Math.abs(nz) > 0.97 ? roofFlat : roofTile;
          for (const [x, y, z] of tri) { RP.push(x, z, -y); RN.push(nx, nz, -ny); RC2.push(col.r, col.g, col.b); }
          if (lm) for (const [x, y, z] of tri) { lmPos.push(x, z, -y); lmNor.push(nx, nz, -ny); lmCol.push(col.r, col.g, col.b); }
        } else {
          const hl = Math.hypot(nx, ny) || 1, tx = -ny / hl, ty = nx / hl;
          for (const [x, y, z] of tri) {
            W.pos.push(x, z, -y); W.nor.push(nx, nz, -ny); W.col.push(facade.r, facade.g, facade.b);
            W.uv.push((x * tx + y * ty) / C.w, (z - zmin - 0.4) / C.h);
          }
          if (lm) {
            const t = textureMean(C.mat.map); // (the copy has no texture: its mean)
            for (const [x, y, z] of tri) { lmPos.push(x, z, -y); lmNor.push(nx, nz, -ny); lmCol.push(facade.r * t, facade.g * t, facade.b * t); }
          }
        }
      }
      bIndex++;
      total++;
    }
    const mk = (pos, nor, col, uv, mat, landmark = false) => {
      if (!pos.length) return;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
      g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
      if (uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, mat);
      m.matrixAutoUpdate = false;
      m.userData.building = true; // read by the lints (trees in buildings)
      if (landmark) m.userData.landmark = true;
      group.add(m);
    };
    for (const k in walls) mk(walls[k].pos, walls[k].nor, walls[k].col, walls[k].uv, CLASSES[k].mat);
    mk(rPos, rNor, rCol, null, roofMat);
    for (const k in wallsL) mk(wallsL[k].pos, wallsL[k].nor, wallsL[k].col, wallsL[k].uv, lmMat(CLASSES[k].mat), true);
    mk(lrPos, lrNor, lrCol, null, lmMat(roofMat), true);
  }
  if (lmPos.length) group.userData.landmarks = { pos: lmPos, nor: lmNor, col: lmCol, list: lmList, baseMed: Math.round(baseMed) };
  console.log(`landmarks: ${lmCount} buildings, ${lmPos.length / 9} triangles (line's ground ${Math.round(baseMed)} m)`);
  console.log(`LOD2 buildings: ${total} (${lifted} spanning the track)`, counts);
}

const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2];
// Roofs of the drawn buildings (meshes tagged `building`) in a 4 m grid: `roof(x, y)` is the height
// of the highest roof over the point, or null; a point under a roof is inside a building.
export function roofIndex(group) {
  const grid = new Map(), cell = 4;
  group.traverse((m) => {
    if (!m.isMesh || !m.userData.building) return;
    const a = m.geometry.attributes.position;
    for (let i = 0; i + 2 < a.count; i += 3) {
      const t = [];
      for (let k = 0; k < 3; k++) t.push(a.getX(i + k), -a.getZ(i + k), a.getY(i + k));
      const area = (t[3] - t[0]) * (t[7] - t[1]) - (t[4] - t[1]) * (t[6] - t[0]);
      if (Math.abs(area) < 0.5) continue; // walls (vertical) and slivers
      const x0 = Math.floor(Math.min(t[0], t[3], t[6]) / cell), x1 = Math.floor(Math.max(t[0], t[3], t[6]) / cell);
      const y0 = Math.floor(Math.min(t[1], t[4], t[7]) / cell), y1 = Math.floor(Math.max(t[1], t[4], t[7]) / cell);
      for (let ix = x0; ix <= x1; ix++) for (let iy = y0; iy <= y1; iy++) {
        const k = ix * 100003 + iy;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(t);
      }
    }
  });
  return (x, y) => {
    let best = null;
    for (const t of grid.get(Math.floor(x / cell) * 100003 + Math.floor(y / cell)) || []) {
      const d = (t[4] - t[7]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[1] - t[7]);
      const w1 = ((t[4] - t[7]) * (x - t[6]) + (t[6] - t[3]) * (y - t[7])) / d;
      const w2 = ((t[7] - t[1]) * (x - t[6]) + (t[0] - t[6]) * (y - t[7])) / d;
      if (w1 < 0 || w2 < 0 || w1 + w2 > 1) continue;
      const z = w1 * t[2] + w2 * t[5] + (1 - w1 - w2) * t[8];
      if (best === null || z > best) best = z;
    }
    return best;
  };
}
