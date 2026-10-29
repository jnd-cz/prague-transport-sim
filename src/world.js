// Static 3D scenery built from the preprocessed OSM data, draped on the DMR 5G terrain.
import * as THREE from 'three';
import { smoothPolyline } from './route.js';
import { rng } from './random.js';
import { DTM_LIFT, FLUSH } from './terrain.js';
import { CONTACT_WIRE } from './models.js';
import { RAIL_HEAD, BED_BELOW, STREET_BELOW } from './heights.js';
import { weatherize, wetFactor, WEATHER_UNIFORMS, WEATHER_LOOK, crownColor, crownThinning, leafTexture } from './weather.js';

const CELL = 350; // spatial chunk size (m) for merged meshes, so frustum culling can skip far chunks
const TERRAIN_CHUNK = 20; // terrain cells per chunk side
// how much of the snow stays on a surface (src/weather.js): carriageways are driven and ploughed,
// footways trodden; ground, roofs, ballast take it all
const STREET_SNOW = 0.35, FOOT_SNOW = 0.7, GROUND_SNOW = 1;

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
const polyLength = (line) => line.reduce((s, p, i) => (i ? s + Math.hypot(p[0] - line[i - 1][0], p[1] - line[i - 1][1]) : 0), 0);

// Grid of line segments for fast "distance to the nearest X" queries (tracks, roads).
class SegmentIndex {
  constructor(cell = 10) { this.cell = cell; this.map = new Map(); }
  add(a, b, w = 0) {
    const c = this.cell, seg = [a[0], a[1], b[0], b[1], w / 2];
    const i0 = Math.floor((Math.min(a[0], b[0]) - seg[4]) / c), i1 = Math.floor((Math.max(a[0], b[0]) + seg[4]) / c);
    const j0 = Math.floor((Math.min(a[1], b[1]) - seg[4]) / c), j1 = Math.floor((Math.max(a[1], b[1]) + seg[4]) / c);
    for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) {
      const k = `${i},${j}`;
      if (!this.map.has(k)) this.map.set(k, []);
      this.map.get(k).push(seg);
    }
  }
  addLine(line, w = 0) { for (let i = 1; i < line.length; i++) this.add(line[i - 1], line[i], w); }
  // distance from (x, y) to the nearest segment's edge (centre line minus half width), up to ~cell
  dist(x, y) {
    const c = this.cell, ci = Math.floor(x / c), cj = Math.floor(y / c);
    let best = Infinity;
    for (let i = ci - 1; i <= ci + 1; i++) for (let j = cj - 1; j <= cj + 1; j++) {
      const arr = this.map.get(`${i},${j}`);
      if (!arr) continue;
      for (const [ax, ay, bx, by, hw] of arr) {
        const dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2));
        best = Math.min(best, Math.hypot(ax + dx * t - x, ay + dy * t - y) - hw);
      }
    }
    return best;
  }
}

// Building footprints on a grid, for point-in-building tests.
class FootprintIndex {
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

// OSM `lanes` (and so our width estimate) counts only the car lanes, but in Prague the tram
// tracks usually run down the middle of the same street. Widen such roads by the track zone
// (3.2 m per track) and flag them, so asphalt, kerbs (poles) and car lanes sit beside the tracks.
export function widenTramStreets(data) {
  const idx = new SegmentIndex(10);
  for (const t of data.tracks) idx.addLine(t.p);
  for (const r of data.roads) {
    if (r.f || r.w < 5 || r.p.length < 2) continue;
    let n = 0, near = 0, both = 0;
    const pts = densify(r.p, 5);
    pts.forEach(([x, y], i) => {
      n++;
      if (idx.dist(x, y) < 2.6) near++;
      // tracks on both sides of the centre line = double track
      const a = pts[Math.max(0, i - 1)], c = pts[Math.min(pts.length - 1, i + 1)];
      const hx = c[0] - a[0], hy = c[1] - a[1], hl = Math.hypot(hx, hy) || 1, ox = (-hy / hl) * 1.6, oy = (hx / hl) * 1.6;
      if (idx.dist(x + ox, y + oy) < 0.8 && idx.dist(x - ox, y - oy) < 0.8) both++;
    });
    if (near / n < 0.6) continue;
    r.tram = both / n > 0.3 ? 2 : 1;
    r.w += 3.2 * r.tram;
  }
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
  // `surface` tags meshes cars and walkers stand on (read by the street bot); 'building' marks
  // building meshes instead (read by the lints)
  build(group, surface = null) {
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
      if (surface === 'building') m.userData.building = true;
      else if (surface) m.userData.surface = surface;
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
// (`strips` > 1: that many strips across, each edge at its own height: a street with tracks in it
// follows the track level in its middle instead of a straight line from kerb to kerb)
function addRibbon(cg, line, width, hfn, lift, col, offset = 0, strips = 1) {
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
    L.push(W(lx, ly, (fixed ? hfn[i] : hfn(lx, ly)) + lift));
    R.push(W(rx, ry, (fixed ? hfn[i] : hfn(rx, ry)) + lift));
  }
  const c = cg._chunk(line[0][0], line[0][1]);
  for (let i = 0; i < line.length - 1; i++) cg.quad(c, R[i], R[i + 1], L[i + 1], L[i], col);
}

// A vertical strip along `line` at `offset` m to its left, from zBot up to zTop (arrays per point):
// the sides of the rails where the bed lies well under the heads (grass, ballast)
function addSide(cg, line, offset, zTop, zBot) {
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
// (the same function the cars and walkers on a bridge stand on: ground.way)
function wayHeight(line, isBridge, ground) {
  return ground.way(line, isBridge);
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
const ROOF_COLORS = ['#8c4a32', '#7a3f2c', '#5f5a55', '#6d6862', '#9a5638', '#4f4b47'].map((c) => new THREE.Color(c));

// The parts of buildWorld in order, with their usual share of its time (line 17, ms) and the loading
// screen's label for them. (A line without the surveyed streets skips the two DTM parts.)
export const WORLD_PARTS = [
  ['tracks + tunnel roads', 1600, 'tracks'], ['terrain under tracks', 100, 'terrain'], ['terrain under DTM', 4700, 'terrain'],
  ['fine under DTM', 750, 'terrain'], ['fine to tunnel mouths', 100, 'terrain'], ['terrain mesh', 1100, 'terrain'],
  ['DTM streets', 3800, 'streets'], ['OSM roads', 300, 'roads'], ['track bed + rails', 100, 'roads'], ['track support', 1200, 'roads'],
  ['zebras', 50, 'roads'], ['walls', 20, 'roads'], ['bridges + tunnels', 20, 'roads'], ['buildings', 3300, 'buildings'],
  ['trees', 200, 'wires'], ['catenary', 200, 'wires'],
];

// onPart(name): called (and awaited) after each part, so a loading screen can show the progress.
// The world is the same in every weather: group.userData.setWeather(w) sets it (src/weather.js).
export async function buildWorld(scene, data, route, ground, onPart = null) {
  const group = new THREE.Group();
  group.matrixAutoUpdate = false;
  scene.add(group);
  // time of each part (window.worldTimes, logged at the end: what to optimize)
  const times = {};
  let lap = performance.now();
  const mark = async (k) => {
    times[k] = Math.round(performance.now() - lap);
    if (onPart) await onPart(k);
    lap = performance.now();
  };

  // far fallback ground below the terrain
  const far = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), weatherize(new THREE.MeshLambertMaterial({ color: 0x8a897d }), { wet: wetFactor('#8d8c80', '#77766c'), snow: GROUND_SNOW }));
  far.rotation.x = -Math.PI / 2;
  far.position.y = ground.terrain.min - 3;
  scene.add(far);

  // track geometry first: smoothed curves and heights (once; kept across weather rebuilds),
  // then the terrain is lowered under every track so it can't poke through the bed
  // OSM draws curves as straight segments: render tracks as smoothed curves
  for (const t of data.tracks) if (!t.smooth) t.smooth = smoothPolyline(t.p, 1.5, t.p.length > 2 ? 6 : 0.1).pts;
  // every track centre line, for keeping trees, zebra paint and poles off the tracks and for the
  // street surfaces laid flush with the track bed
  const tracks = new SegmentIndex(10);
  for (const t of data.tracks) tracks.addLine(t.smooth);
  const trackDist = (x, y) => tracks.dist(x, y);
  ground.trackDist = trackDist;
  if (ground.dtm) flushDtm(ground);
  // track heights after the streets are laid to the track profile, so other lines' tracks sit in them
  // (another line's track in a street: its top of rail is the street surface, as on our own route)
  const embedded = (hf) => hf;
  // (every track within 6 m of the route, ours and the opposite one (4.5 m apart on the Modřany
  // corridor), lies on the track profile, on a
  // bridge tagged in OSM or not: the opposite track 4.2 m off took the raw survey, 3 m off ours)
  const onDeck = (hf) => (x, y) => {
    const n = route.nearest(x, y);
    return n && n.d < 6 ? ground.trackAt(x, y) : hf(x, y);
  };
  for (const t of data.tracks) if (!t.z) t.z = trackHeights(t.smooth, onDeck(t.b ? wayHeight(t.p, t.b, ground) : embedded(wayHeight(t.p, t.b, ground))));
  // our tunnels through rock (terrain.js carveCorridor): the hill stays whole above the track; its
  // terrain is not drawn in the tunnel's corridor, the vault, the rock over it and the portals are
  const rock = ground.walls?.rock || [];
  const TUN_W = 8.5; // half width of the vault: both tracks and the road beside them (Vyšehrad tunnel)
  const inTunnel = (x, y, pad = 0) => {
    if (!rock.length) return false;
    const n = route.nearest(x, y);
    return !!n && n.d < TUN_W + pad && rock.some(([a, b]) => n.s > a - 0.5 && n.s < b + 0.5);
  };
  // road tunnels: drawn inside where they share our tunnel without an underground survey (else the
  // survey's floor is drawn there); a short one (a building passage, an underpass: under SHORT_TUNNEL m
  // in all) as an open road at its graded height, the building or bridge over it is its roof; a long
  // one below ground, with a mouth at each open end
  const SHORT_TUNNEL = 60, tunnelRoads = [], tunnelPortals = [];
  for (const r of data.roads) {
    if (!r.t || r.z) continue;
    const tf = ground.way(r.way || r.p, false, true), L = polyLength(r.way || r.p);
    const inside = densify(r.p, 3).filter((p) => inTunnel(p[0], p[1], 2));
    if (inside.length > 1) { if (!ground.dtm?.under?.length) tunnelRoads.push({ r, inside, tf }); }
    else if (L < SHORT_TUNNEL) tunnelRoads.push({ r, inside: densify(r.p, 3), tf });
    else if (r.c) tunnelPortals.push({ r, tf, L });
  }
  const mouths = roadPortalMouths(tunnelPortals);
  await mark('tracks + tunnel roads');
  // (how far a track's bed lies under its top of rail, by the route's track styles: src/heights.js)
  const liftAt = (x, y) => { const n = route.nearest(x, y); return n && n.d < 6 ? ground.profile.lift(n.s) : 0; };
  lowerTerrainUnderTracks(data, ground.terrain, inTunnel, liftAt);
  await mark('terrain under tracks');
  if (ground.dtm) { lowerTerrainUnderDtm(ground.dtm, ground.terrain); await mark('terrain under DTM'); lowerFineUnderDtm(ground.dtm, ground.terrain); await mark('fine under DTM'); }
  const cellPad = Math.hypot(ground.terrain.dx, ground.terrain.dy) / 2;
  const inMouth = (x, y) => mouths.some((m) => m.has(x, y, cellPad));
  fitFineToMouths(ground.terrain, mouths);
  await mark('fine to tunnel mouths');
  buildTerrain(group, data, route, ground.terrain, (x, y) => inTunnel(x, y, 3) || inMouth(x, y), (x, y) => inTunnel(x, y, 3));
  await mark('terrain mesh');
  if (ground.dtm) fitDtmToMouths(ground.dtm, mouths);
  if (ground.dtm) buildDtm(group, ground);
  await mark('DTM streets');

  // (the weather is the materials' state, src/weather.js: everything is built in its dry colours, each
  // material with how much darker it gets wet (the old wet colours as factors) and how snow lies on it)
  const flatMat = (dry, wetHex, snow = STREET_SNOW) => weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { wet: wetFactor(dry, wetHex), snow, slush: true });

  // roads (wider first so footways draw on top)
  const roadsCg = new ChunkedGeometry(flatMat('#55565a', '#3e3f43'), { color: true });
  const footCg = new ChunkedGeometry(flatMat('#a39d90', '#86817a', FOOT_SNOW), { color: true });
  const asphalt = new THREE.Color('#55565a').toArray(), paving = new THREE.Color('#a39d90').toArray();
  for (const r of [...data.roads].sort((a, b) => b.w - a.w)) {
    if (r.z) continue; // painted crossings: zebra stripes below, the asphalt shows through
    if (r.t) continue; // (road tunnels: above)
    // where the surveyed DTM streets exist, they replace the OSM ribbons (on a bridge: its deck)
    const runs = ground.dtm ? uncoveredRuns(r.p, ground.dtm, r.b ? wayHeight(r.way || r.p, true, ground) : null) : [r.p];
    // (a bridge spans between the ends of the whole way, not of the piece drawn)
    const hf = r.b ? wayHeight(r.way || r.p, true, ground) : null;
    // (a street with tracks in it, or crossing them: strips across, so the middle follows the track level)
    for (const run of runs) {
      const across = r.tram || (r.w > 3 && run.some(([x, y]) => trackDist(x, y) < 8));
      addRibbon(r.f ? footCg : roadsCg, run, r.w, hf || wayHeight(run, false, ground), r.f ? 0.16 : 0.12, r.f ? paving : asphalt, 0, across ? Math.ceil(r.w / 2) : 1);
    }
  }
  // (road tunnels: no snow inside)
  const tunnelCg = new ChunkedGeometry(flatMat('#55565a', '#3e3f43', 0), { color: true });
  for (const { r, inside, tf } of tunnelRoads) addRibbon(tunnelCg, inside, r.w, tf, 0.12, asphalt);
  roadsCg.build(group, 'road');
  footCg.build(group, 'road');
  tunnelCg.build(group, 'road');
  await mark('OSM roads');

  // track bed + rails for every tram track around the route
  const bedCg = new ChunkedGeometry(flatMat('#77736a', '#5f5c56'), { color: true });
  const bed = new THREE.Color('#77736a').toArray();
  // (rails: glossy when wet, roughness set by the weather; trams keep them clear of snow)
  const railMat = new THREE.MeshStandardMaterial({ color: 0xc4c7cc, metalness: 0.6, roughness: 0.4 });
  const railCg = new ChunkedGeometry(railMat);
  // (src/heights.js: t.z is the top of rail; the bed lies the track style's offset under it, the
  // rail heads stand just over it, and where the bed is well below, the rails get their sides)
  for (const t of data.tracks) {
    const lift = t.smooth.map(([x, y]) => liftAt(x, y));
    const zBed = t.z.map((z, i) => z - lift[i] - BED_BELOW);
    addRibbon(bedCg, t.smooth, 2.7, zBed, 0, bed);
    // on a canted curve of our route the outer rail is higher, the inner one lower
    const tilt = t.smooth.map(([x, y], i) => {
      const n = route.nearest(x, y);
      if (!n || n.d > 5) return 0;
      const roll = route.rollAt(n.s);
      if (!roll) return 0;
      const L = t.smooth, a = L[Math.max(0, i - 1)], b = L[Math.min(L.length - 1, i + 1)];
      const h = route.at(n.s), same = (b[0] - a[0]) * h.hx + (b[1] - a[1]) * h.hy >= 0 ? 1 : -1;
      return -0.72 * Math.tan(roll) * same; // left rail (+0.72 along the track) goes up by this (down when leaning left)
    });
    for (const side of [1, -1]) {
      const zr = t.z.map((z, i) => z + side * tilt[i]);
      addRibbon(railCg, t.smooth, 0.1, zr, RAIL_HEAD, null, side * 0.72);
      if (lift.some((v) => v > 0.03)) for (const face of [-0.05, 0.05]) addSide(railCg, t.smooth, side * 0.72 + face, zr.map((z) => z + RAIL_HEAD), zBed);
    }
  }
  bedCg.build(group, 'bed');
  railCg.build(group);
  await mark('track bed + rails');
  buildTrackSupport(group, route, ground, trackDist);
  await mark('track support');

  buildZebras(group, data, ground, trackDist);
  await mark('zebras');

  buildWalls(group, data, route, ground);
  await mark('walls');

  buildBridges(group, data, route, ground);
  buildRockTunnels(group, route, ground, rock, TUN_W);
  buildRoadPortals(group, mouths, ground.terrain);
  await mark('bridges + tunnels');

  if (data.geo?.buildings?.arr) buildLod2(group, data, route, ground);
  else buildOsmBuildings(group, data, route, ground);
  await mark('buildings');

  const trees = buildTrees(group, data, ground, trackDist);
  await mark('trees');
  buildCatenary(group, data, route, ground, trackDist);
  await mark('catenary');
  window.worldTimes = times;
  console.log('world build (ms)', times);
  // the weather: shader uniforms shared by all patched materials, the rails' gloss, the trees' crowns
  // and the fallen leaves (instant: nothing is rebuilt)
  group.userData.setWeather = (w) => {
    const look = WEATHER_LOOK[w] || WEATHER_LOOK.dry;
    WEATHER_UNIFORMS.uWet.value = look.wet;
    WEATHER_UNIFORMS.uSnow.value = look.snow;
    WEATHER_UNIFORMS.uAutumn.value = look.autumn;
    railMat.roughness = look.wet ? 0.2 : 0.4;
    trees.setWeather(w);
  };
  return group;
}

// Fallback: OSM footprints extruded to their tagged height, sitting on the terrain.
function buildOsmBuildings(group, data, route, ground) {
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

function buildLod2(group, data, route, ground) {
  const geo = data.geo.buildings, arr = geo.arr, q = geo.q;
  const side = THREE.DoubleSide;
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
  const roofMat = weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { snow: GROUND_SNOW });
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
  for (const ch of geo.chunks) {
    const [ox, oy, oz] = ch.o;
    const walls = {};
    for (const k in CLASSES) walls[k] = { pos: [], nor: [], uv: [], col: [] };
    const rPos = [], rNor = [], rCol = [];
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
      const C = CLASSES[cls], W = walls[cls], pal = CLASS_COLORS[cls];
      const facade = pal ? new THREE.Color(pal[Math.floor(r() * pal.length)]) : FACADE_COLORS[Math.floor(r() * FACADE_COLORS.length)];
      const roofTile = ROOF_COLORS[Math.floor(r() * 3)], roofFlat = new THREE.Color('#77736d');
      for (let t = 0; t < n3; t += 3) {
        const ax = xs[t], ay = ys[t], az = zs[t], bx = xs[t + 1], by = ys[t + 1], bz = zs[t + 1], cx = xs[t + 2], cy = ys[t + 2], cz = zs[t + 2];
        // nothing of a bridge model inside the space our tram sweeps (±3 m, from just over the rail heads
        // to 5.8 m above them): at the north end of Čechův most a slab 3.7 m above the deck cut through
        // the tram, and the model's top 0-0.5 m over the real deck would cover the rails (src/heights.js)
        if (isBridge) {
          const mx = (ax + bx + cx) / 3, my = (ay + by + cy) / 3, n = route.nearest(mx, my);
          if (n && n.d < 3) {
            const zr = ground.profile.height(n.s), mz = (az + bz + cz) / 3; // (top of rail)
            if (mz > zr + 0.02 && mz < zr + 5.8) continue;
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
          for (const [x, y, z] of tri) { rPos.push(x, z, -y); rNor.push(nx, nz, -ny); rCol.push(col.r, col.g, col.b); }
        } else {
          const hl = Math.hypot(nx, ny) || 1, tx = -ny / hl, ty = nx / hl;
          for (const [x, y, z] of tri) {
            W.pos.push(x, z, -y); W.nor.push(nx, nz, -ny); W.col.push(facade.r, facade.g, facade.b);
            W.uv.push((x * tx + y * ty) / C.w, (z - zmin - 0.4) / C.h);
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
      m.userData.building = true; // read by the lints (trees in buildings)
      group.add(m);
    };
    for (const k in walls) mk(walls[k].pos, walls[k].nor, walls[k].col, walls[k].uv, CLASSES[k].mat);
    mk(rPos, rNor, rCol, null, roofMat);
  }
  console.log(`LOD2 buildings: ${total} (${lifted} spanning the track)`, counts);
}

// Pieces of a polyline outside the DTM-surveyed streets (densified at 3 m); for a way on a bridge
// (height function hf) outside the surveyed decks at its height.
function uncoveredRuns(line, dtm, hf = null) {
  const pts = densify(line, 3), runs = [];
  let cur = [];
  for (const p of pts) {
    if ((hf ? dtm.deckAt(p[0], p[1], hf(p[0], p[1]) + 0.1, 1) : dtm.heightAt(p[0], p[1])) === null) cur.push(p);
    else { if (cur.length > 1) runs.push(cur); cur = []; }
  }
  if (cur.length > 1) runs.push(cur);
  return runs;
}

// Terrain under the surveyed streets goes 0.25 m below them, so the lidar ground (10 m grid)
// never shows through: at every drawn DTM vertex and edge midpoint the terrain triangle under it
// (same split as Terrain.height) is lowered by the excess.
function lowerTerrainUnderDtm(dtm, T) {
  for (const a of dtm.areas) {
    if (a.l !== 0 || a.c === 'roof' || a.c === 'deck' || a.c === 'rail') continue;
    for (const [p, q, r] of a.mesh) {
      for (const [x, y, z] of [p, q, r, mid(p, q), mid(q, r), mid(r, p)]) lowerTerrainAt(T, x, y, z - 0.25);
    }
  }
}
const mid = (p, q) => [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2];
// The fine blocks under the surveyed streets, vertex by vertex (the survey's own vertices are too far
// apart for a 2 m grid: a river area of a few large triangles left the quay's lidar 8 m over the water
// between them): every fine vertex under a ground-level surveyed area goes 0.25 m below it (up to 15 m).
function lowerFineUnderDtm(dtm, T) {
  for (const g of T.fine?.values() || []) {
    for (let j = 0; j < g.ny; j++) for (let i = 0; i < g.nx; i++) {
      const x = g.x0 + i * g.dx, y = g.y0 + j * g.dy, t = dtm.surfaceAt(x, y);
      if (!t) continue;
      const k = j * g.nx + i, excess = g.h[k] - (t.z - 0.25);
      if (excess > 0 && excess <= 15) g.h[k] -= excess;
    }
  }
}
// (> 6 m: a surface below the street (or bad data), not ours to dig; every grid, fine blocks too)
function lowerTerrainAt(T, x, y, zmax) {
  T.lowerAt(x, y, zmax, 6);
}

// The DTM areas as meshes: ground-level surfaces draped on their surveyed heights (sidewalks,
// islands and platforms with a kerb face down to the road), level 1 (bridge decks, railway on
// the bridge, canopies) as slabs with sides and an underside.
const DTM_COLORS = {
  road: '#55565a', parking: '#5e5f63', cycle: '#7d5a52', tram: '#6c675d', sidewalk: '#a39d90', island: '#9b968a',
  platform: '#b3ad9f', paved: '#9b968b', stairs: '#aaa59a', green: '#6f8a4e', water: '#5d7f95', deck: '#8f897e',
  rail: '#6a6258', roof: '#5f6266', wall: '#8a8172',
};
// Carriageway and tram areas next to the tracks are laid flush with the track bed (ground.flush):
// applied once to the vertices themselves, so the height lookup and the drawing agree.
function flushDtm(ground) {
  const dtm = ground.dtm;
  if (dtm.flushed) return; // kept across weather rebuilds
  dtm.flushed = true;
  const done = new Set();
  // Street model areas (tools/streets.py) are laid to the track profile: the carriageway's offset
  // from the track's surface level (top of rail less its style's offset), measured on the unshifted model along the route
  // (every 2 m) and across it (every 1 m, gaps filled from the nearest carriageway), is applied
  // fully within 5 m of the route (our track and the opposite one) and fades out by 15 m; other
  // lines' tracks crossing it take their heights from the street afterwards. Road and sidewalk at the same spot get the
  // same correction, so kerbs keep their height; a street sloping across gets level at the tracks.
  const { route, profile } = ground;
  const rows = new Map();
  const row = (i) => {
    if (rows.has(i)) return rows.get(i);
    const s = i * 2, zt = profile.height(s) - profile.lift(s) - STREET_BELOW, e = [];
    // under our bridge the street below keeps its own level
    if (profile.onBridge(s)) { rows.set(i, new Array(31).fill(null)); return rows.get(i); }
    // (the street at the rails' level: a road below or above it in plan is another level, never
    // measured; at the north end of Čechův most the embankment road 5.6 m below lifted the street)
    for (let l = -15; l <= 15; l++) {
      const o = route.offset(s, l), t = dtm.surfaceAt(o.x, o.y, zt);
      e.push(t && FLUSH.has(t.c) && Math.abs(zt - t.z) < 1.5 ? zt - t.z : null);
    }
    for (let k = 0; k < e.length; k++) if (e[k] === null) {
      for (let j = 1; j < e.length; j++) {
        const v = e[k - j] ?? e[k + j];
        if (v != null) { e[k] = v; break; }
      }
    }
    rows.set(i, e);
    return e;
  };
  // The correction is a smooth field: each row measures the survey's own noise too (±10-30 cm from
  // metre to metre), and applied row by row it stamped that noise back as waves across the streets
  // (line 17 s 15700-15800). Averaged over ±10 m along the route and ±2 m across.
  const smoothRows = new Map();
  const srow = (i) => {
    if (smoothRows.has(i)) return smoothRows.get(i);
    if (row(i)[0] === null) { smoothRows.set(i, null); return null; }
    const out = new Array(31).fill(0), w = new Array(31).fill(0);
    for (let j = i - 5; j <= i + 5; j++) {
      const e = row(j);
      if (e[0] === null) continue;
      const wj = 1 - Math.abs(j - i) / 6;
      for (let k = 0; k < 31; k++) for (let d = -2; d <= 2; d++) {
        const kk = k + d;
        if (kk < 0 || kk > 30) continue;
        const wk = wj * (1 - Math.abs(d) / 3);
        out[k] += e[kk] * wk; w[k] += wk;
      }
    }
    const res = out.map((v, k) => v / w[k]);
    smoothRows.set(i, res);
    return res;
  };
  const corr = (s, lat) => {
    const e = srow(Math.round(s / 2));
    if (e === null) return null;
    const f = Math.max(0, Math.min(30, lat + 15)), k = Math.min(29, Math.floor(f)), u = f - k;
    return e[k] * (1 - u) + e[k + 1] * u;
  };
  const shift = (p) => {
    if (done.has(p)) return;
    done.add(p);
    const n = route.nearest(p[0], p[1]);
    if (!n || n.d >= 15) return;
    const q = route.at(n.s), lat = q.hx * (p[1] - q.y) - q.hy * (p[0] - q.x);
    // in the track corridor (3 m from our tracks) a carriageway or tram bed is the bed, whatever
    // the survey says there (a 2 m bump at s 2420 stood 3.6 m over the rails); a structure well above
    // the track (over 4.5 m) is another level
    if (bed.has(p) && (!green.has(p) || ground.styles?.at(n.s) === 'grass') && ground.trackDist(p[0], p[1]) < 3 && !profile.onBridge(n.s) && p[2] - profile.height(n.s) < 4.5) { p[2] = profile.height(n.s) - profile.lift(n.s) - STREET_BELOW; return; }
    const dz = corr(n.s, lat);
    if (dz === null || Math.abs(p[2] - profile.height(n.s)) > 2.5 + Math.abs(dz)) return; // (another level)
    const k = Math.max(0, Math.min(1, (n.d - 5) / 10));
    p[2] += dz * (1 - k * k * (3 - 2 * k));
  };
  // measure everything first, then move
  // (bed: vertices of carriageway and tram areas, laid flush with the tracks; green ones too where the
  // track is grass track: src/heights.js)
  const pts = [], bed = new Set(), green = new Set();
  const inBed = (a, p) => { if (FLUSH.has(a.c)) bed.add(p); else if (a.c === 'green') { bed.add(p); green.add(p); } };
  for (const a of dtm.areas) if (a.model) {
    for (const tri of a.mesh) for (const p of tri) { pts.push(p); inBed(a, p); }
    for (const r of [a.ring, ...a.holes]) for (const p of r) { pts.push(p); inBed(a, p); }
  }
  for (const p of pts) { const n = route.nearest(p[0], p[1]); if (n && n.d < 15) srow(Math.round(n.s / 2)); } // (rows and their neighbours, before anything moves)
  for (const p of pts) shift(p);
  for (const a of dtm.areas) {
    if (a.model || a.l !== 0 || !(FLUSH.has(a.c) || a.c === 'green')) continue;
    for (const tri of a.mesh) for (const p of tri) {
      if (done.has(p)) continue;
      if (a.c === 'green') { const n = route.nearest(p[0], p[1]); if (!n || n.d > 8 || ground.styles?.at(n.s) !== 'grass') continue; }
      done.add(p);
      p[2] = ground.flush(p[0], p[1], p[2]);
    }
  }
  // The surveyed decks of our own bridges carry the tracks: laid to the track profile the same way
  // (the deck's offset at the route, full within 8 m, fading out by 15 m; crossfall kept), so the
  // cars beside the tram drive on the deck at the rails' level. Measured first, then moved.
  const deckMoves = [];
  for (const a of dtm.areas) {
    if (a.l < 1) continue;
    for (const p of [...a.ring, ...a.holes.flat(), ...a.mesh.flat()]) {
      if (done.has(p)) continue;
      done.add(p);
      const n = route.nearest(p[0], p[1]);
      if (!n || n.d >= 15 || !profile.onBridge(n.s)) continue;
      const q = route.at(n.s), zt = profile.height(n.s) - profile.lift(n.s) - STREET_BELOW, zr = dtm.deckAt(q.x, q.y, zt, 2.5);
      if (zr === null) continue;
      const k = Math.max(0, Math.min(1, (n.d - 8) / 7));
      deckMoves.push([p, (zt - zr) * (1 - k * k * (3 - 2 * k))]);
    }
  }
  for (const [p, dz] of deckMoves) p[2] += dz;
}

// (by weather: carriageways get slush, footways and the rest trodden snow, lawns all of it; all but
// lawns and water 0.8 darker when wet)
const DTM_KIND = { road: 'street', parking: 'street', tram: 'street', cycle: 'street', green: 'green', water: 'water' };
function buildDtm(group, ground) {
  const dtm = ground.dtm;
  const mat = (opts) => weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), opts);
  const cgs = {
    street: new ChunkedGeometry(mat({ wet: 0.8, snow: STREET_SNOW, slush: true }), { color: true }),
    other: new ChunkedGeometry(mat({ wet: 0.8, snow: FOOT_SNOW }), { color: true }),
    green: new ChunkedGeometry(mat({ snow: GROUND_SNOW }), { color: true }),
    water: new ChunkedGeometry(mat({}), { color: true }),
  };
  const color = {};
  for (const [k, v] of Object.entries(DTM_COLORS)) color[k] = new THREE.Color(v).toArray();
  for (const a of dtm.areas) {
    // (surveyed walls are drawn as surveyed: a quay wall's area runs from its foot line to its top
    // line, a battered face; a wall top is flat, and its sides come from the steps below)
    const col = color[a.c] || color.paved;
    const cg = cgs[DTM_KIND[a.c] || 'other'];
    const c = cg._chunk(a.ring[0][0], a.ring[0][1]);
    const slab = a.l > 0 ? (a.c === 'roof' ? 0.3 : 1.0) : 0;
    const lift = a.l > 0 ? 0.02 : DTM_LIFT[a.c] ?? 0.03;
    const fz = (v) => v[2];
    for (const [p, q, r] of a.mesh) {
      // a structure over our track (a railway bridge) keeps its underside above the catenary (5 m
      // over the rails: the slab gets thinner there); anything lower inside the space the tram
      // sweeps (±3 m, 0.4 m up) is not drawn, as for the bridge models
      let under = slab;
      if (slab) {
        const mx = (p[0] + q[0] + r[0]) / 3, my = (p[1] + q[1] + r[1]) / 3, n = ground.route.nearest(mx, my);
        if (n && n.d < 3) {
          const zr = ground.profile.height(n.s), mz = (p[2] + q[2] + r[2]) / 3; // (top of rail)
          if (mz > zr + 0.4 && mz < zr + 5.3) { dtm.inEnvelope = (dtm.inEnvelope || 0) + 1; continue; }
          if (mz > zr + 0.4) under = Math.max(0.3, Math.min(slab, mz - zr - 5.0));
        }
      }
      cg.tri(c, W(p[0], p[1], fz(p) + lift), W(q[0], q[1], fz(q) + lift), W(r[0], r[1], fz(r) + lift), null, col);
      if (slab) cg.tri(c, W(p[0], p[1], p[2] - under), W(r[0], r[1], r[2] - under), W(q[0], q[1], q[2] - under), null, col);
    }
    // kerbs (ground level) or slab sides (level 1) along every ring
    const drop = slab || (a.c === 'sidewalk' || a.c === 'island' || a.c === 'platform' ? 0.18 : 0);
    if (!drop) continue;
    const side = a.l > 0 ? col : new THREE.Color('#8e8a82').toArray();
    [a.ring, ...a.holes].forEach((ring, ri) => {
      for (let i = 0; i < ring.length; i++) {
        if (a.kerbs && !a.kerbs[ri]?.[i]) continue; // street model: kerbs only where the carriageway is
        const p = ring[i], q = ring[(i + 1) % ring.length];
        cg.quad(c, W(p[0], p[1], p[2] + lift - drop), W(q[0], q[1], q[2] + lift - drop), W(q[0], q[1], q[2] + lift), W(p[0], p[1], p[2] + lift), side);
      }
    });
  }
  buildDtmSteps(cgs.other, ground, color.wall);
  for (const cg of Object.values(cgs)) cg.build(group, 'dtm');
}

// Our tunnels through rock: a vault over both tracks and the road (walls to 4.8 m, an arch to 7.2 m
// over the rails), the rock above it at the lidar ground (wider than the hole cut in the terrain, a
// little above it, so the coarse terrain edge never shows a gap) and the two portal faces between the
// vault and the rock top. Every 2 m along the span.
function buildRockTunnels(group, route, ground, rock, HW) {
  if (!rock.length) return;
  const T = ground.terrain, pr = ground.profile;
  // outside (the portals and the rock top) wet and snowy in the weather; the vault and the floor inside dry
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#8b8475', '#6b6559'), snow: GROUND_SNOW }), { color: true });
  const inner = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { color: true });
  const stone = new THREE.Color('#8b8475').toArray(), vault = new THREE.Color('#5d5a52').toArray();
  const top = new THREE.Color('#6f7a55').toArray();
  const P = (s, lat, z) => { const o = route.offset(s, lat); return W(o.x, o.y, z); };
  const rockTop = (s, l) => { const o = route.offset(s, l); return Math.max(T.height(o.x, o.y) + 0.05, pr.height(s) + 9); };
  for (const [a, b] of rock) {
    // the walls where the surveyed tunnel floor ends (underground DTM areas: the Vyšehrad tunnel is
    // 1.5 m right of our track to 8 m left of it), else ±HW
    let lo = Infinity, hi = -Infinity;
    for (const u of ground.dtm?.under || []) for (const [x, y] of u.ring) {
      const n = route.nearest(x, y);
      if (!n || n.s < a - 5 || n.s > b + 5 || n.d > 20) continue;
      const q = route.at(n.s), lat = q.hx * (y - q.y) - q.hy * (x - q.x);
      lo = Math.min(lo, lat); hi = Math.max(hi, lat);
    }
    if (!(hi - lo > 4)) { lo = -HW; hi = HW; } else { lo -= 0.3; hi += 0.3; }
    // (the Vyšehrad tunnel: a stone semicircle springing low over the whole width, user photo)
    const c0 = (lo + hi) / 2, half = (hi - lo) / 2, rise = Math.min(half, 5), spring = 2.5;
    // the vault's cross-section: lateral offset and height over the rails
    const prof = [[lo, -0.3], [lo, spring]];
    for (let k = 1; k < 12; k++) { const t = Math.PI - (k / 12) * Math.PI; prof.push([c0 + half * Math.cos(t), spring + rise * Math.sin(t)]); }
    prof.push([hi, spring], [hi, -0.3]);
    const R0 = lo - 10, R1 = hi + 10; // the rock top reaches past the hole in the terrain
    const n = Math.max(2, Math.ceil((b - a) / 2));
    for (let k = 0; k < n; k++) {
      const s0 = a + ((b - a) * k) / n, s1 = a + ((b - a) * (k + 1)) / n, z0 = pr.height(s0), z1 = pr.height(s1);
      const c = cg._chunk(route.at(s0).x, route.at(s0).y), ci = inner._chunk(route.at(s0).x, route.at(s0).y);
      for (let i = 0; i < prof.length - 1; i++) {
        const [l0, h0] = prof[i], [l1, h1] = prof[i + 1];
        inner.quad(ci, P(s0, l0, z0 + h0), P(s1, l0, z1 + h0), P(s1, l1, z1 + h1), P(s0, l1, z0 + h1), vault);
      }
      for (let lat = R0; lat < R1; lat += 2) {
        cg.quad(c, P(s0, lat, rockTop(s0, lat)), P(s0, lat + 2, rockTop(s0, lat + 2)), P(s1, lat + 2, rockTop(s1, lat + 2)), P(s1, lat, rockTop(s1, lat)), top);
      }
    }
    // portals: from each vault point up to the rock top above it, and the rock face beside them
    for (const s of [a, b]) {
      const z = pr.height(s), c = cg._chunk(route.at(s).x, route.at(s).y);
      for (let i = 0; i < prof.length - 1; i++) {
        const [l0, h0] = prof[i], [l1, h1] = prof[i + 1];
        cg.quad(c, P(s, l0, z + h0), P(s, l1, z + h1), P(s, l1, rockTop(s, l1)), P(s, l0, rockTop(s, l0)), stone);
      }
      for (const [from, to] of [[R0, lo], [hi, R1]]) {
        for (let l = from; l < to; l += 2) {
          const l1 = Math.min(to, l + 2);
          cg.quad(c, P(s, l, z - 0.3), P(s, l1, z - 0.3), P(s, l1, rockTop(s, l1)), P(s, l, rockTop(s, l)), stone);
        }
      }
    }
  }
  // the tunnel's floor as surveyed (underground road and footway areas), at the track's height
  const floorCol = { road: new THREE.Color('#55565a').toArray(), sidewalk: new THREE.Color('#a39d90').toArray() };
  for (const u of ground.dtm?.under || []) {
    const n0 = route.nearest(u.ring[0][0], u.ring[0][1]);
    if (!n0 || n0.d > 20 || !rock.some(([a, b]) => n0.s > a - 10 && n0.s < b + 10)) continue;
    const ring = u.ring.map((p) => new THREE.Vector2(p[0], p[1]));
    let tris;
    try { tris = THREE.ShapeUtils.triangulateShape(ring, []); } catch { continue; }
    const lift = u.c === 'sidewalk' || u.c === 'island' ? 0.3 : 0.12, col = floorCol[u.c === 'road' ? 'road' : 'sidewalk'];
    const z = (p) => { const n = route.nearest(p.x, p.y); return (n ? pr.height(n.s) : pr.height(n0.s)) + lift; };
    for (const [i, j, k] of tris) {
      const A = ring[i], B = ring[j], C = ring[k];
      inner.tri(inner._chunk(A.x, A.y), W(A.x, A.y, z(A)), W(B.x, B.y, z(B)), W(C.x, C.y, z(C)), null, col);
    }
  }
  cg.build(group, 'support');
  inner.build(group, 'support');
  console.log(`rock tunnels: ${rock.map(([a, b]) => `${Math.round(a)}-${Math.round(b)}`).join(', ')}`);
}

// Road tunnels away from our track (Letenský tunel): the cars run below ground. At each end that is
// not another tunnel way, a mouth: a portal frame and a THROAT_D m deep dark tube into the hill
// (floor, walls, flat roof, darker inward, a black end far in), so cars drive out of darkness (a flat
// dark quad at the mouth read as an opaque wall). The terrain cells over a mouth are cut out
// (buildTerrain's hole) and covered again at 2-3 m: over the throat at least 0.6 m above its roof,
// in front of it down to the road; a headwall above the lintel reaches up to the hill.
const THROAT_D = 24, THROAT_H = 5.2;
function roadPortalMouths(list) {
  const key = (p) => `${p[0]},${p[1]}`, ends = new Map(), out = [];
  for (const { r } of list) for (const p of [r.p[0], r.p[r.p.length - 1]]) ends.set(key(p), (ends.get(key(p)) || 0) + 1);
  for (const { r, tf, L } of list) {
    const D = Math.min(THROAT_D, L / 2);
    for (const end of [0, 1]) {
      const i = end ? r.p.length - 1 : 0, j = end ? r.p.length - 2 : 1, p = r.p[i];
      if (ends.get(key(p)) > 1) continue; // the tunnel goes on as the next way
      const w0 = r.way || r.p, at0 = key(w0[0]) === key(p) ? 0 : key(w0[w0.length - 1]) === key(p) ? 1 : -1;
      if (at0 < 0 || (w0.open && !w0.open[at0])) continue; // (past the edge of the imported roads: no portal)
      const dx = r.p[j][0] - p[0], dy = r.p[j][1] - p[1], l = Math.hypot(dx, dy) || 1;
      const hx = dx / l, hy = dy / l, nx = -hy, ny = hx, w = r.w / 2 + 0.8;
      // local frame: d inward along the tunnel, lat across
      const loc = (x, y) => [(x - p[0]) * hx + (y - p[1]) * hy, (x - p[0]) * nx + (y - p[1]) * ny];
      const zAt = (d) => tf(p[0] + hx * Math.max(0, d), p[1] + hy * Math.max(0, d));
      out.push({
        p, hx, hy, nx, ny, w, zAt, loc, D,
        // within the mouth's cut (pad: m around it)
        has(x, y, pad = 0) { const [d, lat] = loc(x, y); return d > -4 - pad && d < D + 2 + pad && Math.abs(lat) < w + 2 + pad; },
      });
    }
  }
  return out;
}
// The survey's street areas around a mouth often take the portal's crown into their outline (a road
// area at the Letenský tunel ran 191-206 m: a grey ramp across the opening). Inside a mouth's
// footprint, street vertices above the tunnel road come down onto it (in place: the height lookup
// holds the same points). Lawns and the hill over the throat are left alone.
const MOUTH_FIT = new Set(['road', 'parking', 'paved', 'sidewalk', 'cycle', 'island', 'tram']);
function fitDtmToMouths(dtm, mouths) {
  if (!mouths.length || dtm.mouthsFitted) return;
  dtm.mouthsFitted = true;
  const seen = new Set();
  let n = 0;
  for (const a of dtm.areas) {
    if (a.l !== 0 || !MOUTH_FIT.has(a.c)) continue;
    for (const p of [...a.ring, ...a.holes.flat(), ...a.mesh.flat()]) {
      if (seen.has(p)) continue;
      seen.add(p);
      for (const m of mouths) {
        const [d, lat] = m.loc(p[0], p[1]);
        if (d < -3 || d > m.D || Math.abs(lat) > m.w + 1.5) continue;
        const z = m.zAt(d) + 0.05;
        if (p[2] > z + 0.3) { p[2] = z; n++; }
      }
    }
  }
  if (n) console.log(`survey points brought down into tunnel mouths: ${n}`);
}
function buildRoadPortals(group, mouths, T) {
  if (!mouths.length) return;
  // (the frame wet in the weather, no snow in the throat; the floor inside stays dry)
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#9a958a', '#77736b') }), { color: true });
  const floorCg = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true }), { color: true });
  const frame = new THREE.Color('#9a958a').toArray(), lining = new THREE.Color('#6d6a64');
  const asphalt = new THREE.Color('#55565a'), black = new THREE.Color('#050506');
  const earth = new THREE.Color('#6f8a4e').toArray();
  const fade = (c, d, D) => c.clone().lerp(black, Math.min(1, Math.pow(d / D, 0.6))).toArray();
  for (const m of mouths) {
    const { p, hx, hy, nx, ny, w, D } = m;
    const at = (lat, d, h) => W(p[0] + nx * lat + hx * d, p[1] + ny * lat + hy * d, m.zAt(d) + h);
    const c = cg._chunk(p[0], p[1]), fc = floorCg._chunk(p[0], p[1]);
    // the throat, 2 m rings
    for (let d = 0; d < D; d += 2) {
      const e = Math.min(D, d + 2), col = fade(lining, d + 1, D);
      floorCg.quad(fc, at(-w, d, 0.12), at(-w, e, 0.12), at(w, e, 0.12), at(w, d, 0.12), fade(asphalt, d + 1, D));
      cg.quad(c, at(-w, d, 0), at(-w, e, 0), at(-w, e, THROAT_H), at(-w, d, THROAT_H), col);
      cg.quad(c, at(w, d, 0), at(w, e, 0), at(w, e, THROAT_H), at(w, d, THROAT_H), col);
      cg.quad(c, at(-w, d, THROAT_H), at(w, d, THROAT_H), at(w, e, THROAT_H), at(-w, e, THROAT_H), col);
    }
    cg.quad(c, at(-w, D, 0), at(w, D, 0), at(w, D, THROAT_H), at(-w, D, THROAT_H), black.toArray());
    // the frame: lintel and jambs, the headwall above the lintel up to the hill over the mouth
    const W2 = w + 1.5;
    let top = 6.6;
    for (const lat of [-W2, 0, W2]) {
      const x = p[0] + nx * lat + hx, y = p[1] + ny * lat + hy;
      top = Math.max(top, Math.max(T.height(x, y), m.zAt(1) + THROAT_H + 0.6) - m.zAt(0) + 0.3);
    }
    cg.quad(c, at(-W2, 0, THROAT_H), at(W2, 0, THROAT_H), at(W2, 0, top), at(-W2, 0, top), frame);
    for (const sd of [-1, 1]) cg.quad(c, at(sd * w, 0, -0.2), at(sd * W2, 0, -0.2), at(sd * W2, 0, top), at(sd * w, 0, top), frame);
  }
  cg.build(group, 'support');
  floorCg.build(group, 'road');
  // the cover over the terrain cells buildTerrain left out
  const cov = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#6f8a4e', '#5e7346'), snow: GROUND_SNOW }), { color: true });
  const pad = Math.hypot(T.dx, T.dy) / 2, seen = new Set();
  const coverZ = (x, y) => {
    let z = T.height(x, y);
    for (const m of mouths) {
      const [d, lat] = m.loc(x, y);
      if (Math.abs(lat) > m.w + 2) continue;
      if (d >= 0 && d < m.D + 2) z = Math.max(z, m.zAt(d) + THROAT_H + 0.6);
      else if (d < 0 && d > -4) z = Math.min(z, m.zAt(0) - 0.3);
    }
    return z;
  };
  for (const m of mouths) {
    for (let d = -4 - pad; d < m.D + 2 + pad; d += 2) for (let lat = -m.w - 2 - pad; lat < m.w + 2 + pad; lat += 2) {
      const x = m.p[0] + m.hx * d + m.nx * lat, y = m.p[1] + m.hy * d + m.ny * lat;
      const i = Math.floor((x - T.x0) / T.dx), j = Math.floor((y - T.y0) / T.dy);
      if (i < 0 || j < 0 || i >= T.nx - 1 || j >= T.ny - 1 || seen.has(j * T.nx + i)) continue;
      const cx = T.x0 + (i + 0.5) * T.dx, cy = T.y0 + (j + 0.5) * T.dy;
      if (!mouths.some((q) => q.has(cx, cy, pad)) || T.fineAt?.(cx, cy)) continue; // (exactly the cells buildTerrain left out; under a fine block the ground itself is shaped)
      seen.add(j * T.nx + i);
      const n = 5, x0 = T.x0 + i * T.dx, y0 = T.y0 + j * T.dy, sx = T.dx / n, sy = T.dy / n, ch = cov._chunk(cx, cy);
      const P = (u, v) => { const X = x0 + u * sx, Y = y0 + v * sy; return W(X, Y, coverZ(X, Y)); };
      for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) cov.quad(ch, P(a, b), P(a, b + 1), P(a + 1, b + 1), P(a + 1, b), earth);
    }
  }
  cov.build(group);
  console.log(`road tunnel mouths: ${mouths.length}, terrain cells re-covered: ${seen.size}`);
}

// What carries our tracks where they stand above the ground drawn beside them (approach ramps of
// the bridges whose survey or model stops short, an embankment over a lower street): off the bridges,
// walls from the bed down to the ground at the outer bed edges and a top between the two tracks; on
// our bridges, a 0.8 m deck under the beds where the ground is far below. Every 2 m along the route.
function buildTrackSupport(group, route, ground, trackDist) {
  const { profile, dtm, terrain } = ground;
  const below = (x, y) => { const t = dtm?.surfaceAt(x, y); return t ? t.z : terrain.height(x, y); };
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#8a8376', '#6d675d'), snow: GROUND_SNOW }), { color: true });
  const stone = new THREE.Color('#8a8376').toArray(), ballast = new THREE.Color('#77736a').toArray();
  const edges = (s) => {
    let lo = 0, hi = 0;
    for (let lat = -6; lat <= 6; lat += 0.25) { const o = route.offset(s, lat); if (trackDist(o.x, o.y) < 0.2) { lo = Math.min(lo, lat); hi = Math.max(hi, lat); } }
    return [lo - 1.4, hi + 1.4];
  };
  let prev = null, walls = 0;
  for (let s = 0; s <= route.length; s += 2) {
    const zb = profile.height(s) - profile.lift(s), [lo, hi] = edges(s), bridge = profile.onBridge(s);
    const L = route.offset(s, hi), R = route.offset(s, lo);
    const gL = below(L.x, L.y), gR = below(R.x, R.y), C = route.at(s), gC = below(C.x, C.y);
    const cur = { s, zb, L, R, gL, gR, bridge, need: bridge ? zb - Math.min(gL, gR, gC) > 1 : Math.max(zb - gL, zb - gR) > 0.6 };
    if (prev && prev.need && cur.need) {
      const c = cg._chunk(L.x, L.y);
      const P = (o, z) => W(o.x, o.y, z);
      // top (ballast) between the outer bed edges, just under the beds
      cg.quad(c, P(prev.R, prev.zb - 0.03), P(R, zb - 0.03), P(L, zb - 0.03), P(prev.L, prev.zb - 0.03), ballast);
      const footL = bridge ? zb - 0.8 : Math.min(zb, gL) - 0.1, footLp = prev.bridge ? prev.zb - 0.8 : Math.min(prev.zb, prev.gL) - 0.1;
      const footR = bridge ? zb - 0.8 : Math.min(zb, gR) - 0.1, footRp = prev.bridge ? prev.zb - 0.8 : Math.min(prev.zb, prev.gR) - 0.1;
      cg.quad(c, P(prev.L, footLp), P(L, footL), P(L, zb), P(prev.L, prev.zb), stone);
      cg.quad(c, P(prev.R, footRp), P(R, footR), P(R, zb), P(prev.R, prev.zb), stone);
      if (bridge) cg.quad(c, P(prev.L, footLp), P(prev.R, footRp), P(R, footR), P(L, footL), stone);
      walls++;
    }
    prev = cur;
  }
  cg.build(group, 'support');
  console.log(`track support: ${walls * 2} m`);
}

// Steps between surveyed surfaces: embankment and quay walls, terraces, retaining walls the survey
// only outlines. Wherever the surface just outside a ground-level area's edge lies more than 0.5 m
// below the edge, a stone face closes the gap from the edge down to it. The outside surface is
// extrapolated back to the edge from 0.5 and 1.5 m out, so a slope down from the edge is not a step.
function buildDtmSteps(cg, ground, col) {
  const dtm = ground.dtm, T = ground.terrain;
  const out = (x, y) => {
    const t = dtm.surfaceAt(x, y);
    return t ? t.z + (DTM_LIFT[t.c] ?? 0.03) : T.height(x, y);
  };
  let faces = 0;
  for (const a of dtm.areas) {
    if (a.l !== 0 || a.c === 'water') continue;
    const lift = DTM_LIFT[a.c] ?? 0.03;
    [a.ring, ...a.holes].forEach((ring, ri) => {
      const sgn = (signedArea(ring) > 0 ? 1 : -1) * (ri ? -1 : 1); // outside = right of the edge on a CCW outline
      for (let i = 0; i < ring.length; i++) {
        const p = ring[i], q = ring[(i + 1) % ring.length];
        const dx = q[0] - p[0], dy = q[1] - p[1], l = Math.hypot(dx, dy);
        if (l < 0.05) continue;
        const nx = (sgn * dy) / l, ny = (-sgn * dx) / l;
        const n = Math.max(1, Math.ceil(l / 4));
        let prev = null;
        for (let k = 0; k <= n; k++) {
          const u = k / n, x = p[0] + dx * u, y = p[1] + dy * u, top = p[2] + (q[2] - p[2]) * u + lift;
          const z1 = out(x + nx * 0.5, y + ny * 0.5), z2 = out(x + nx * 1.5, y + ny * 1.5);
          const edge = z1 + (z1 - z2) * 0.5, foot = Math.min(top, z1, edge) - 0.05;
          const cur = { x, y, top, foot, step: top - edge };
          if (prev && Math.max(prev.step, cur.step) > 0.5 && Math.min(prev.step, cur.step) > 0.2) {
            cg.quad(cg._chunk(x, y), W(prev.x, prev.y, prev.foot), W(x, y, cur.foot), W(x, y, top), W(prev.x, prev.y, prev.top), col);
            faces++;
          }
          prev = cur;
        }
      }
    });
  }
  console.log(`DTM steps: ${faces} wall faces`);
}

// Keep the terrain at or below every track's bed: for samples along each track (centre and
// both bed edges) find the mesh triangle underneath (same split as Terrain.height) and lower
// its three vertices by the excess. Bridges are skipped. (t.z is top of rail; the bed lies
// `liftAt` under it, and the terrain 0.06 m under that: src/heights.js)
function lowerTerrainUnderTracks(data, T, inTunnel = () => false, liftAt = () => 0) {
  for (let pass = 0; pass < 2; pass++) for (const t of data.tracks) {
    if (t.b) continue;
    const L = t.smooth, Z = t.z;
    for (let i = 0; i < L.length; i++) {
      const a = L[Math.max(0, i - 1)], b = L[Math.min(L.length - 1, i + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
      if (inTunnel(L[i][0], L[i][1])) continue; // (in a rock tunnel the hill stays above)
      for (const off of [0, 1.4, -1.4]) {
        const x = L[i][0] - (dy / l) * off, y = L[i][1] + (dx / l) * off;
        T.lowerAt(x, y, Z[i] - liftAt(x, y) - 0.06);
      }
    }
  }
}

// Terrain mesh in chunks near the route, coloured by land cover (parks, woods, water).
// (hole: coarse cells left out; fineHole: fine cells left out (a tunnel's corridor); the coarse cells
// under the fine blocks are left out too, the fine mesh is drawn instead)
// (dry colours; the weather by the land class on every vertex (landCls), src/weather.js)
function buildTerrain(group, data, route, T, hole = () => false, fineHole = hole) {
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

  const palette = [new THREE.Color('#8d8c80'), new THREE.Color('#6f8a4e'), new THREE.Color('#566f3c'), new THREE.Color('#5d7f95')];
  // which chunks are close enough to the route to matter
  const samples = [];
  for (let s = 0; s <= route.length; s += 60) { const p = route.at(s); samples.push([p.x, p.y]); }
  const veg = { wet: wetFactor('#8d8c80', '#77766c'), snow: GROUND_SNOW, veg: true };
  const mat = weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), veg);
  const C = TERRAIN_CHUNK;
  for (let cj = 0; cj < ny - 1; cj += C) {
    for (let ci = 0; ci < nx - 1; ci += C) {
      const cx = T.x0 + (ci + C / 2) * T.dx, cy = T.y0 + (cj + C / 2) * T.dy;
      if (!samples.some((p) => Math.abs(p[0] - cx) < 1000 && Math.abs(p[1] - cy) < 1000 && Math.hypot(p[0] - cx, p[1] - cy) < 1000)) continue;
      const w = Math.min(C, nx - 1 - ci) + 1, h = Math.min(C, ny - 1 - cj) + 1;
      const pos = new Float32Array(w * h * 3), nor = new Float32Array(w * h * 3), col = new Float32Array(w * h * 3), lc = new Uint8Array(w * h);
      for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
        const gi = ci + i, gj = cj + j, k = (j * w + i) * 3;
        const x = T.x0 + gi * T.dx, y = T.y0 + gj * T.dy;
        pos[k] = x; pos[k + 1] = T.cell(gi, gj); pos[k + 2] = -y;
        // normal from central differences
        const hx = (T.cell(gi + 1, gj) - T.cell(gi - 1, gj)) / (2 * T.dx);
        const hy = (T.cell(gi, gj + 1) - T.cell(gi, gj - 1)) / (2 * T.dy);
        const l = Math.hypot(hx, 1, hy);
        nor[k] = -hx / l; nor[k + 1] = 1 / l; nor[k + 2] = hy / l;
        lc[j * w + i] = cls[gj * nx + gi];
        const c = palette[lc[j * w + i]];
        col[k] = c.r; col[k + 1] = c.g; col[k + 2] = c.b;
      }
      const idx = [];
      for (let j = 0; j < h - 1; j++) for (let i = 0; i < w - 1; i++) {
        const a = j * w + i, b = a + 1, c = a + w, d = c + 1;
        const mx = T.x0 + (ci + i + 0.5) * T.dx, my = T.y0 + (cj + j + 0.5) * T.dy;
        if (hole(mx, my) || T.fineAt?.(mx, my)) continue; // (a tunnel's corridor; a fine block's area)
        // grid rows go south (dy < 0), so this winding faces up
        idx.push(a, c, b, b, c, d);
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
      g.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
      g.setAttribute('color', new THREE.BufferAttribute(col, 3));
      g.setAttribute('landCls', new THREE.BufferAttribute(lc, 1));
      g.setIndex(idx);
      g.computeBoundingSphere();
      const m = new THREE.Mesh(g, mat);
      m.matrixAutoUpdate = false;
      m.userData.surface = 'terrain';
      group.add(m);
    }
  }
  // the fine blocks (2 m, tools/fine_terrain.py): one mesh each, land cover from the coarse classes,
  // and a 3 m skirt down along every edge without a neighbouring block (no crack to the coarse grid)
  const fineMat = weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), veg);
  for (const g of T.fine?.values() || []) {
    const n = g.nx, pos = [], nor = [], col = [], lc = [], idx = [];
    const clsAt = (x, y) => {
      const gi = Math.max(0, Math.min(nx - 1, Math.round((x - T.x0) / T.dx))), gj = Math.max(0, Math.min(ny - 1, Math.round((y - T.y0) / T.dy)));
      return cls[gj * nx + gi];
    };
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
      const x = g.x0 + i * g.dx, y = g.y0 + j * g.dy;
      pos.push(x, g.cell(i, j), -y);
      const hx = (g.cell(i + 1, j) - g.cell(i - 1, j)) / ((Math.min(n - 1, i + 1) - Math.max(0, i - 1)) * g.dx);
      const hy = (g.cell(i, j + 1) - g.cell(i, j - 1)) / ((Math.min(n - 1, j + 1) - Math.max(0, j - 1)) * g.dy);
      const l = Math.hypot(hx, 1, hy);
      nor.push(-hx / l, 1 / l, hy / l);
      const k = clsAt(x, y), c = palette[k];
      lc.push(k);
      col.push(c.r, c.g, c.b);
    }
    for (let j = 0; j < n - 1; j++) for (let i = 0; i < n - 1; i++) {
      if (fineHole(g.x0 + (i + 0.5) * g.dx, g.y0 + (j + 0.5) * g.dy)) continue;
      const a = j * n + i, b = a + 1, c = a + n, d = c + 1;
      idx.push(a, c, b, b, c, d);
    }
    // skirts: (edge vertices, then the same 3 m lower)
    const edges = [
      [[g.bi, g.bj - 1], (k) => k],
      [[g.bi, g.bj + 1], (k) => (n - 1) * n + k],
      [[g.bi - 1, g.bj], (k) => k * n],
      [[g.bi + 1, g.bj], (k) => k * n + n - 1],
    ];
    for (const [[bi, bj], at] of edges) {
      if (T.fine.has(`${bi},${bj}`)) continue;
      const base = pos.length / 3;
      for (let k = 0; k < n; k++) {
        const v = at(k);
        pos.push(pos[v * 3], pos[v * 3 + 1] - 3, pos[v * 3 + 2]);
        nor.push(nor[v * 3], nor[v * 3 + 1], nor[v * 3 + 2]);
        col.push(col[v * 3], col[v * 3 + 1], col[v * 3 + 2]);
        lc.push(lc[v]);
      }
      for (let k = 0; k < n - 1; k++) idx.push(at(k), base + k, at(k + 1), at(k + 1), base + k, base + k + 1);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    geo.setAttribute('landCls', new THREE.BufferAttribute(Uint8Array.from(lc), 1));
    geo.setIndex(idx);
    geo.computeBoundingSphere();
    const m = new THREE.Mesh(geo, fineMat);
    m.matrixAutoUpdate = false;
    m.userData.surface = 'terrain';
    group.add(m);
  }
}

// The tunnel mouths in the fine blocks: the cover is the ground itself at 2 m (no hole): over the
// throat at least 0.6 m above its roof, in front of it down to the road (as buildRoadPortals' cover).
function fitFineToMouths(T, mouths) {
  if (!T.fine?.size || !mouths.length) return;
  for (const g of T.fine.values()) {
    for (let j = 0; j < g.ny; j++) for (let i = 0; i < g.nx; i++) {
      const x = g.x0 + i * g.dx, y = g.y0 + j * g.dy, k = j * g.nx + i;
      for (const m of mouths) {
        const [d, lat] = m.loc(x, y);
        if (Math.abs(lat) > m.w + 2) continue;
        if (d >= 0 && d < m.D + 2) g.h[k] = Math.max(g.h[k], m.zAt(d) + THROAT_H + 0.6);
        else if (d < 0 && d > -4) g.h[k] = Math.min(g.h[k], m.zAt(0) - 0.3);
      }
    }
  }
}

// Deck, parapets and piers for bridges on the route (e.g. Most Legií).
function buildBridges(group, data, route, ground) {
  const sideMat = new THREE.MeshLambertMaterial({ color: 0x7f786c });
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { snow: STREET_SNOW, slush: true }), { color: true });
  const deckCol = new THREE.Color('#8f897e').toArray(), sideCol = new THREE.Color('#7a7366').toArray();
  for (const [s0, s1] of data.bridges) {
    // a real 3D model of this bridge (Mosty 3D) replaces the synthetic deck
    const real = (ground.profile.realDecks || []).reduce((acc, [a, b]) => acc + Math.max(0, Math.min(b, s1) - Math.max(a, s0)), 0);
    if (real > (s1 - s0) * 0.5) continue;
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

// Pedestrian crossings with zebra paint: 0.5 m bars every metre along the crossing, each
// 3 m long across the walking direction. No paint on the tram tracks (as in Prague).
function buildZebras(group, data, ground, trackDist) {
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { wet: wetFactor('#e9e9e4', '#c9cbcc'), snow: STREET_SNOW, slush: true }), { color: true });
  const white = new THREE.Color('#e9e9e4').toArray();
  // and the OSM signalled crossings (data.osmSignals.peds) without a zebra way of their own: across the
  // nearest car road, kerb to kerb (Palackého náměstí: the two crossings from the island over the road
  // had no paint, user's orthophoto 2026-10-24)
  const ways = data.roads.filter((r) => r.z).map((r) => ({ p: r.p }));
  const segDist = (P, x, y) => { let m = Infinity; for (let i = 1; i < P.length; i++) { const a = P[i - 1], b = P[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9, t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)); m = Math.min(m, Math.hypot(a[0] + dx * t - x, a[1] + dy * t - y)); } return m; };
  for (const o of data.osmSignals?.peds || []) {
    if (ways.some((w) => segDist(w.p, o.x, o.y) < 4)) continue;
    let best = null;
    for (const r of data.roads) {
      if (!r.c || r.f || r.t || !(r.w >= 5)) continue;
      const P = r.p;
      for (let i = 1; i < P.length; i++) {
        const a = P[i - 1], b = P[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((o.x - a[0]) * dx + (o.y - a[1]) * dy) / l2)), d = Math.hypot(a[0] + dx * t - o.x, a[1] + dy * t - o.y);
        if (d < 6 && (!best || d < best.d)) { const l = Math.sqrt(l2); best = { d, hx: dx / l, hy: dy / l, half: r.w / 2 }; }
      }
    }
    if (!best) continue;
    const cx = -best.hy, cy = best.hx;
    ways.push({ p: [[o.x - cx * best.half, o.y - cy * best.half], [o.x + cx * best.half, o.y + cy * best.half]], osm: true });
  }
  for (const r of ways) {
    const path = densify(r.p, 0.5);
    let acc = 0;
    for (let i = 1; i < path.length; i++) {
      const a = path[i - 1], b = path[i];
      const l = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
      acc += l;
      if (acc % 1.0 > 0.5 || acc < 0.4) continue; // stripe on the first half of each metre
      const hx = (b[0] - a[0]) / l, hy = (b[1] - a[1]) / l, nx = -hy * 1.5, ny = hx * 1.5;
      const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
      if (trackDist(cx, cy) < 1.75 || trackDist(cx + nx, cy + ny) < 1.6 || trackDist(cx - nx, cy - ny) < 1.6) continue;
      const q = [[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]]
        .map(([x, y]) => W(x, y, ground.at(x, y) + 0.135));
      cg.quad(cg._chunk(cx, cy), q[3], q[2], q[1], q[0], white);
    }
  }
  cg.build(group);
}

// Street detail from Prague's technical map (data.dtmPoints, .claude/tools/dtm_points.py; CC BY,
// datový podklad © IPR Praha): manhole covers and valve caps as flat discs on the drawn ground, gutter
// inlets as grates turned along the nearest street, above-ground hydrants as small red posts. One
// instanced mesh per kind for the whole line (a few thousand instances: a few draw calls).
export function buildStreetDetail(data, ground) {
  const group = new THREE.Group();
  const pts = data.dtmPoints || [];
  // street directions for the grates: road segments in 20 m cells
  const cell = 20, grid = new Map();
  for (const r of data.roads) {
    if (!r.c || r.f) continue;
    for (let i = 1; i < r.p.length; i++) {
      const a = r.p[i - 1], b = r.p[i], k = `${Math.floor((a[0] + b[0]) / 2 / cell)},${Math.floor((a[1] + b[1]) / 2 / cell)}`;
      if (!grid.has(k)) grid.set(k, []);
      grid.get(k).push([a, b]);
    }
  }
  const streetAngle = (x, y) => {
    let best = null;
    for (let gx = -1; gx <= 1; gx++) for (let gy = -1; gy <= 1; gy++) for (const [a, b] of grid.get(`${Math.floor(x / cell) + gx},${Math.floor(y / cell) + gy}`) || []) {
      const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9, t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2));
      const d = Math.hypot(a[0] + dx * t - x, a[1] + dy * t - y);
      if (!best || d < best.d) best = { d, ang: Math.atan2(dx, -dy) };
    }
    return best ? best.ang : 0;
  };
  const flat = (geo) => geo.rotateX(-Math.PI / 2);
  const iron = (c) => weatherize(new THREE.MeshLambertMaterial({ color: c, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }), { wet: 0.6 });
  const kinds = {
    manhole: { geo: flat(new THREE.CircleGeometry(0.32, 14)), mat: iron(0x3a3a3c), turn: false },
    // (caps smaller than first drawn, user 2026-10-24; reference photos of all the covers to come)
    hydrant_cap: { geo: flat(new THREE.CircleGeometry(0.1, 10)), mat: iron(0x4a3a30), turn: false },
    valve_cap: { geo: flat(new THREE.CircleGeometry(0.06, 8)), mat: iron(0x3d3d3d), turn: false },
    gutter_inlet: { geo: flat(new THREE.PlaneGeometry(0.62, 0.36)), mat: iron(0x242424), turn: true },
    hydrant: { geo: new THREE.CylinderGeometry(0.11, 0.14, 0.85, 8).translate(0, 0.42, 0), mat: new THREE.MeshLambertMaterial({ color: 0x9c1d16 }), turn: false },
  };
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  for (const [k, def] of Object.entries(kinds)) {
    // (one shaft is often recorded twice, under two networks' codes: one cover per 0.3 m)
    const list = [];
    for (const o of pts) if (o.k === k && !list.some((l) => Math.abs(l.x - o.x) < 0.3 && Math.abs(l.y - o.y) < 0.3)) list.push(o);
    if (!list.length) continue;
    const mesh = new THREE.InstancedMesh(def.geo, def.mat, list.length);
    list.forEach((o, i) => {
      q.setFromAxisAngle(up, def.turn ? streetAngle(o.x, o.y) : (o.x * 7.3 + o.y * 3.1) % (Math.PI * 2));
      // (between the rails on the paved track bed, which is drawn above the street's height: most covers
      // at Strossmayerovo náměstí lie in the track and were hidden under it)
      const onTrack = ground.trackDist && ground.trackDist(o.x, o.y) < 1.8 && ground.trackAt;
      p.set(o.x, Math.max(ground.surface(o.x, o.y), onTrack ? ground.trackAt(o.x, o.y) + 0.16 : -Infinity) + 0.015, -o.y);
      m.compose(p, q, s);
      mesh.setMatrixAt(i, m);
    });
    mesh.computeBoundingSphere();
    group.add(mesh);
  }
  group.userData.counts = Object.fromEntries(Object.keys(kinds).map((k) => [k, pts.filter((o) => o.k === k).length]));
  return group;
}

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

// Vegetation from the city register (data.geo.trees: [x, y, kind], tools/geoportal.py): 0 deciduous
// tree, 1 conifer, 2 bush or hedge, 3 plants in a container, 4 a sample along a registered tree row
// (a position on the row's line, not a surveyed tree). Trees inside a building are dropped and
// crowns shrink until they clear the facades; row samples on a carriageway are dropped too.
// Without the register, parks and woods are filled at random.
const CROWN = 2.6; // icosahedron radius of a tree crown at scale 1 (x 1.1 wide, x 1.4 tall)
function buildTrees(group, data, ground, trackDist) {
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
// Overhead line: contact wire 5.34 m over top of rail of every track, hung from Prague-style cross-span wires.
// Each span is anchored on both sides of the street: on a pole at the kerb (between the
// carriageway and the sidewalk), or on a wall rosette where a building stands close to the
// track. Where one side has no place for an anchor (a square, a junction) a single pole with
// a bracket arm carries the wires. Poles are closer together on curves.
function buildCatenary(group, data, route, ground, trackDist) {
  const wire = [];
  for (const t of data.tracks) {
    const line = t.smooth, z = t.z;
    for (let i = 0; i < line.length - 1; i += 2) {
      const j = Math.min(line.length - 1, i + 2);
      wire.push(new THREE.Vector3(line[i][0], z[i] + CONTACT_WIRE, -line[i][1]), new THREE.Vector3(line[j][0], z[j] + CONTACT_WIRE, -line[j][1]));
    }
  }
  // vehicle carriageways (poles stand outside them) and building footprints (rosettes)
  const roads = new SegmentIndex(12);
  for (const r of data.roads) if (!r.f && !r.b) roads.addLine(r.p, r.w - 0.6);
  const houses = new FootprintIndex(data.buildings.map((b) => b.p));
  // retaining walls: surveyed ones and the synthetic walls of the track cutting
  const walls = new SegmentIndex(10);
  for (const w of data.geo?.walls || []) walls.addLine(w.p, 0.8);
  const cut = { 1: [], '-1': [] };
  for (const run of ground.walls?.runs || []) if (run.pts.length > 1) cut[run.side].push([run.pts[0].s, run.pts[run.pts.length - 1].s]);
  const cutAt = (s, side) => cut[side].some(([a, b]) => s >= a - 3 && s <= b + 3);
  const B = ground.walls?.bench ?? 7;

  // find the anchor on one side (+1 left, -1 right) of route position s
  const pole = (s, side, lat) => { const p = route.offset(s, side * lat); return { wall: false, lat, sl: side * lat, x: p.x, y: p.y }; };
  const anchor = (s, side) => {
    if (ground.profile.onBridge(s)) return pole(s, side, 8.4); // on the bridge parapet
    for (let lat = 2.4; lat <= 22; lat += 0.4) {
      const o = route.offset(s, side * lat);
      if (houses.inside(o.x, o.y)) return lat <= 16 ? { wall: true, lat: lat - 0.1, sl: side * (lat - 0.1), x: o.x, y: o.y } : null;
      // a retaining wall: the pole stands at its foot, inside the cutting
      if (walls.dist(o.x, o.y) < 0 || (lat >= B - 0.4 && cutAt(s, side))) return trackDist(o.x, o.y) > 2.2 ? pole(s, side, lat - 0.5) : null;
      if (trackDist(o.x, o.y) < 2.3 || roads.dist(o.x, o.y) < 0) continue;
      // first free spot beyond the tracks and the carriageway: the kerb
      // a facade just behind the sidewalk carries the span wire on a rosette instead
      for (let k = lat + 0.8; k <= Math.min(lat + 5.5, 16); k += 0.4) {
        const w = route.offset(s, side * k);
        if (houses.inside(w.x, w.y)) return { wall: true, lat: k - 0.1, sl: side * (k - 0.1), x: w.x, y: w.y };
      }
      const p = route.offset(s, side * (lat + 0.45));
      return { wall: false, lat: lat + 0.45, sl: side * (lat + 0.45), x: p.x, y: p.y };
    }
    return null;
  };
  const stations = [];
  for (let s = 8; s <= route.length; ) {
    const R = route.radiusAt(s);
    stations.push(s);
    s += R < 50 ? 12 : R < 100 ? 18 : R < 200 ? 25 : 32;
  }
  const poles = [], rosettes = [];
  const m = new THREE.Matrix4();
  // for the game: span positions (signals and signs hang from them or sit on their poles) and a
  // kerb finder for anything else that must stand off the carriageway
  route.catenary = [];
  route.kerbAt = (s, side) => anchor(s, side);
  for (const s of stations) {
    const z = ground.profile.height(s);
    // tracks this span crosses: ours and any parallel one within 6 m (the opposite direction)
    const tracksLat = [0];
    for (let lat = -6; lat <= 6; lat += 0.25) {
      if (Math.abs(lat) < 2) continue;
      const o = route.offset(s, lat);
      if (trackDist(o.x, o.y) < 0.15 && !tracksLat.some((l) => Math.abs(l - lat) < 1.5)) tracksLat.push(lat);
    }
    let L = anchor(s, 1), Rt = anchor(s, -1);
    if (!L && !Rt) continue;
    // a far anchor across a wide street or square, with a close one on the other side: Prague
    // uses a bracket arm from the close pole instead of a long span
    const outer = (side) => (side > 0 ? Math.max(...tracksLat) : -Math.min(...tracksLat));
    if (L && Rt) {
      const fl = L.lat - outer(1), fr = Rt.lat - outer(-1);
      if (fl > 9 && fr < 5 && !Rt.wall) L = null;
      else if (fr > 9 && fl < 5 && !L.wall) Rt = null;
    }
    // The span always hangs 6.74 m over the rails (0.4 under the pole top: 1.4 m over the contact wire), so
    // both ends are level and it carries the wire from above; a pole reaches from its foot up to
    // there however low it stands (164 of 692 spans on line 17 hung from poles on a lower street and
    // held the wire from below, up to 6 m). (deck = true: on a bridge the pole stands on the deck.)
    const top = () => z + 6.74;
    const span = [];
    if (L && Rt) span.push([L, Rt]);
    else {
      // bracket arm from the one anchor to just past the farthest track
      const a = L || Rt, side = L ? 1 : -1;
      if (a.lat > 9) continue; // too far for an arm
      const far = side > 0 ? Math.min(...tracksLat) - 0.8 : Math.max(...tracksLat) + 0.8;
      const e = route.offset(s, far);
      span.push([a, { wall: true, sl: far, x: e.x, y: e.y, end: true }]);
    }
    const cat = { s, z, L, R: Rt, span: !!(L && Rt) || tracksLat.length > 0, tracksLat, attach: [] };
    route.catenary.push(cat);
    for (const a of [L, Rt]) {
      if (!a) continue;
      if (a.wall) rosettes.push([a.x, z + 6.74, a.y]);
      else {
        const zg = ground.at(a.x, a.y, true), h = Math.max(3, z + 7.14 - zg); // (the mesh is 7.4 m)
        m.makeScale(1, h / 7.4, 1).setPosition(a.x, zg + h / 2, -a.y);
        poles.push(m.clone());
      }
    }
    for (const [a, b] of span) {
      const za = top(a), zb = b.end ? za - 0.25 : top(b);
      cat.attach.push(za - 0.4, zb - 0.4); // (read by the lints: where the span hangs)
      wire.push(new THREE.Vector3(a.x, za - 0.4, -a.y), new THREE.Vector3(b.x, zb - 0.4, -b.y));
      // droppers down to each contact wire under the span
      for (const lat of tracksLat) {
        const c = route.offset(s, lat);
        const t = (lat - a.sl) / (b.sl - a.sl || 1);
        const zs = za - 0.4 + (zb - za) * Math.max(0, Math.min(1, t));
        wire.push(new THREE.Vector3(c.x, zs, -c.y), new THREE.Vector3(c.x, z + 5.6, -c.y));
      }
    }
  }
  const poleMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.17, 7.4, 6), new THREE.MeshLambertMaterial({ color: 0x4b5a4f }), Math.max(1, poles.length));
  poles.forEach((pm, i) => poleMesh.setMatrixAt(i, pm));
  poleMesh.count = poles.length;
  const roseMesh = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.16, 0.16, 0.12, 8).rotateX(Math.PI / 2), new THREE.MeshLambertMaterial({ color: 0x3a3a3a }), Math.max(1, rosettes.length));
  rosettes.forEach(([x, h, y], i) => { m.makeTranslation(x, h - 0.4, -y); roseMesh.setMatrixAt(i, m); });
  roseMesh.count = rosettes.length;
  const wg = new THREE.BufferGeometry().setFromPoints(wire);
  group.add(new THREE.LineSegments(wg, new THREE.LineBasicMaterial({ color: 0x222222 })), poleMesh, roseMesh);
  console.log(`catenary: ${poles.length} poles, ${rosettes.length} wall rosettes`);
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
