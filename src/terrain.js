// Terrain heights (ČÚZK DMR 5G grid) and the smoothed vertical profile of the route.

export class Terrain {
  constructor(t) {
    const bin = atob(t.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const raw = new Int16Array(bytes.buffer);
    this.h = new Float32Array(raw.length);
    for (let i = 0; i < raw.length; i++) this.h[i] = t.base + raw[i] * t.scale;
    Object.assign(this, { x0: t.x0, y0: t.y0, dx: t.dx, dy: t.dy, nx: t.nx, ny: t.ny });
    let min = Infinity;
    for (const v of this.h) min = Math.min(min, v);
    this.min = min;
  }

  // grid value with clamping at the edges
  cell(ix, iy) {
    ix = Math.max(0, Math.min(this.nx - 1, ix));
    iy = Math.max(0, Math.min(this.ny - 1, iy));
    return this.h[iy * this.nx + ix];
  }

  // height at local metres (x east, y north), interpolated on the same two triangles per cell
  // as the rendered terrain mesh (split along b-c), so anything draped on it sits exactly on
  // the visible surface (bilinear interpolation differs by up to a few dm on curved ground)
  height(x, y) {
    const fx = (x - this.x0) / this.dx, fy = (y - this.y0) / this.dy;
    const ix = Math.floor(fx), iy = Math.floor(fy);
    const tx = fx - ix, ty = fy - iy;
    const a = this.cell(ix, iy), b = this.cell(ix + 1, iy), c = this.cell(ix, iy + 1), d = this.cell(ix + 1, iy + 1);
    if (tx + ty <= 1) return a + (b - a) * tx + (c - a) * ty;
    return d + (c - d) * (1 - tx) + (b - d) * (1 - ty);
  }
}

// Route elevation z(s): terrain sampled along the track, smoothed like real vertical
// alignment, with bridge decks bridged linearly between their abutments.
// Surfaces of the IPR "Mosty 3D" bridges right above/below the track centre, every 2 m along
// the route: Map 2 m bin -> list of z where a bridge triangle is crossed by the vertical line.
export function bridgeDecks(geo, route, terrain) {
  const out = new Map();
  if (!geo?.buildings?.arr) return out;
  const { arr, q, chunks } = geo.buildings;
  const cell = 20, grid = new Map();
  for (const ch of chunks) {
    if (!ch.k) continue;
    const [ox, oy, oz] = ch.o;
    let v = ch.v;
    for (const [bi, count] of ch.b.entries()) {
      if (ch.k[bi] !== 1) { v += count; continue; }
      for (let t = 0; t < count; t += 3, v += 3) {
        const P = [0, 1, 2].map((k) => [ox + arr[(v + k) * 3] * q, oy + arr[(v + k) * 3 + 1] * q, oz + arr[(v + k) * 3 + 2] * q]);
        const x0 = Math.min(P[0][0], P[1][0], P[2][0]), x1 = Math.max(P[0][0], P[1][0], P[2][0]);
        const y0 = Math.min(P[0][1], P[1][1], P[2][1]), y1 = Math.max(P[0][1], P[1][1], P[2][1]);
        for (let i = Math.floor(x0 / cell); i <= Math.floor(x1 / cell); i++) for (let j = Math.floor(y0 / cell); j <= Math.floor(y1 / cell); j++) {
          const key = `${i},${j}`;
          if (!grid.has(key)) grid.set(key, []);
          grid.get(key).push(P);
        }
      }
    }
  }
  if (!grid.size) return out;
  const p = {};
  for (let s = 0; s <= route.length; s += 2) {
    route.at(s, p);
    const tris = grid.get(`${Math.floor(p.x / cell)},${Math.floor(p.y / cell)}`);
    if (!tris) continue;
    const hits = [];
    for (const [a, b, c] of tris) {
      const d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((b[1] - c[1]) * (p.x - c[0]) + (c[0] - b[0]) * (p.y - c[1])) / d;
      const w2 = ((c[1] - a[1]) * (p.x - c[0]) + (a[0] - c[0]) * (p.y - c[1])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      hits.push(w1 * a[2] + w2 * b[2] + w3 * c[2]);
    }
    if (hits.length) out.set(Math.round(s / 2), hits);
  }
  return out;
}

export class Profile {
  constructor(route, terrain, bridges = [], tunnels = [], decks = new Map(), dtm = null) {
    const step = (this.step = 2);
    const n = (this.n = Math.ceil(route.length / step) + 1);
    let z = new Float32Array(n);
    const p = {};
    this.surveyed = 0;
    for (let i = 0; i < n; i++) {
      route.at(i * step, p);
      // the surveyed street surface (DTM) where there is one, else the lidar terrain: a bridge
      // deck (level 1) over the route carries the tram, unless OSM says the track runs under a
      // structure there (covered / underpass), then the ground level under it
      const under = tunnels.some(([a, b]) => i * step > a - 10 && i * step < b + 10);
      const deck = dtm && !under ? dtm.deckAt(p.x, p.y) : null;
      const zd = deck ?? (dtm ? dtm.heightAt(p.x, p.y) : null);
      if (zd !== null) this.surveyed++;
      z[i] = zd ?? terrain.height(p.x, p.y);
    }
    // box filter via prefix sums (window shrinks at the ends)
    const smooth = (arr, radius) => {
      const pre = new Float64Array(arr.length + 1);
      for (let i = 0; i < arr.length; i++) pre[i + 1] = pre[i] + arr[i];
      const out = new Float32Array(arr.length);
      for (let i = 0; i < arr.length; i++) {
        const a = Math.max(0, i - radius), b = Math.min(arr.length - 1, i + radius);
        out[i] = (pre[b + 1] - pre[a]) / (b - a + 1);
      }
      return out;
    };
    // Bridges first, on the raw samples: the deck spans between the street levels measured
    // just outside the bridge, so the river below never leaks into the smoothed profile.
    this.bridges = bridges;
    const rawMean = (a, b) => {
      let acc = 0, cnt = 0;
      for (let i = Math.max(0, a); i <= Math.min(n - 1, b); i++) { acc += z[i]; cnt++; }
      return acc / Math.max(1, cnt);
    };
    for (const [s0, s1] of bridges) {
      const i0 = Math.max(0, Math.floor(s0 / step) - 5), i1 = Math.min(n - 1, Math.ceil(s1 / step) + 5);
      const z0 = rawMean(i0 - 6, i0), z1 = rawMean(i1, i1 + 6);
      for (let i = i0; i <= i1; i++) {
        const t = (i - i0) / (i1 - i0);
        // linear deck with a gentle hog (crest) like a real arch bridge
        z[i] = z0 + (z1 - z0) * t + 1.2 * Math.sin(Math.PI * t);
      }
    }
    // real bridges (Mosty 3D): on an OSM-tagged bridge of our route the rails lie on the deck
    // of the 3D model. In OSM-tagged underpasses / covered stretches any structure at or above
    // the lidar height is a roof or bridge over the tram (the "bare-earth" model even samples
    // station canopies there); elsewhere only structures clearly above the track count. The
    // track keeps CLEAR m below their underside, with ramps of at most 6 %.
    const CLEAR = 5.3;
    this.realDecks = [];
    const soffit = new Float32Array(n).fill(Infinity);
    if (decks.size) {
      const tagged = (i) => bridges.some(([a, b]) => i * step > a && i * step < b);
      const covered = (i) => tunnels.some(([a, b]) => i * step > a - 20 && i * step < b + 20);
      for (const [k, hits] of decks) {
        if (k >= n) continue;
        if (tagged(k)) {
          const top = Math.max(...hits.filter((h) => Math.abs(h - z[k]) < 3));
          if (Number.isFinite(top)) z[k] = top;
        } else {
          const above = hits.filter((h) => h > z[k] + (covered(k) ? -1.5 : 2.5));
          if (above.length) soffit[k] = Math.min(...above);
        }
      }
      for (const [s0, s1] of bridges) {
        let cnt = 0;
        for (let k = Math.ceil(s0 / step); k <= s1 / step; k++) if (decks.has(k)) cnt++;
        if (cnt * step > (s1 - s0) * 0.3) this.realDecks.push([s0, s1]);
      }
    }
    // highest allowed track level: under each structure, spreading out as 6 % ramps
    const limit = soffit.map((v) => v - CLEAR);
    for (let i = 1; i < n; i++) limit[i] = Math.min(limit[i], limit[i - 1] + 0.06 * step);
    for (let i = n - 2; i >= 0; i--) limit[i] = Math.min(limit[i], limit[i + 1] + 0.06 * step);
    const clear = () => { for (let i = 0; i < n; i++) if (z[i] > limit[i]) z[i] = limit[i]; };
    clear();
    // underpasses: the bare-earth model includes the embankment above, so span them straight
    for (const [s0, s1] of tunnels) {
      const i0 = Math.max(0, Math.floor(s0 / step) - 5), i1 = Math.min(n - 1, Math.ceil(s1 / step) + 5);
      const z0 = rawMean(i0 - 6, i0), z1 = rawMean(i1, i1 + 6);
      for (let i = i0; i <= i1; i++) z[i] = z0 + ((z1 - z0) * (i - i0)) / (i1 - i0);
    }
    // grade limiter: tram track never exceeds ~9 %, so steeper stretches are structures the DEM
    // does not see through (viaducts, untagged underpasses): bridge them with a straight line
    for (let pass = 0; pass < 6; pass++) {
      let changed = false;
      for (let i = 1; i < n; i++) {
        if (Math.abs(z[i] - z[i - 1]) / step <= 0.09) continue;
        let a = Math.max(0, i - 20), b = Math.min(n - 1, i + 20);
        while (b < n - 1 && Math.abs(z[b + 1] - z[b]) / step > 0.09) b++;
        b = Math.min(n - 1, b + 10);
        for (let k = a; k <= b; k++) z[k] = z[a] + ((z[b] - z[a]) * (k - a)) / (b - a);
        changed = true;
        i = b;
      }
      if (!changed) break;
    }
    for (let k = 0; k < 3; k++) z = smooth(z, 9); // ~±25 m Gaussian-ish: removes DEM spikes at ramps/abutments
    // smoothing may lift the track back into an overpass: enforce the clearance, ease it in
    for (let k = 0; k < 3; k++) { clear(); z = smooth(z, 4); }
    clear();
    this.z = z;
    this.grades = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = Math.max(0, i - 3), b = Math.min(n - 1, i + 3);
      this.grades[i] = (z[b] - z[a]) / ((b - a) * step || 1);
    }
  }

  _interp(arr, s) {
    const f = Math.max(0, Math.min(this.n - 1.001, s / this.step));
    const i = Math.floor(f), t = f - i;
    return arr[i] * (1 - t) + arr[i + 1] * t;
  }

  height(s) { return this._interp(this.z, s); }
  grade(s) { return this._interp(this.grades, s); }

  onBridge(s) {
    return this.bridges.some(([a, b]) => s > a - 4 && s < b + 4);
  }
}

// Carve the track corridor into the terrain grid. Within BENCH m of the track the ground is
// the track level. Where the hillside rises more than WALL_MIN m above the track, a retaining
// wall stands at BENCH m with a flat cap behind it; the grid vertices behind the wall are
// lowered so no coarse terrain triangle can cut through the track. Elsewhere the ground
// blends back to the natural terrain (embankment / cutting slopes). Returns wall runs.
const BENCH = 7, BLEND = 8, WALL_MIN = 1.5, WALL_REACH = 22;
export function carveCorridor(T, route, profile) {
  const { nx, ny } = T;
  const orig = T.h.slice();
  const N = nx * ny;
  const bestD = new Float32Array(N).fill(Infinity), bestS = new Float32Array(N), bestSide = new Int8Array(N);
  const R = WALL_REACH + 3;
  const p = {};
  for (let s = 0; s <= route.length; s += 2) {
    route.at(s, p);
    const h = route.heading(s, 3);
    const i0 = Math.max(0, Math.floor((p.x - R - T.x0) / T.dx)), i1 = Math.min(nx - 1, Math.ceil((p.x + R - T.x0) / T.dx));
    const j0 = Math.max(0, Math.floor((p.y + R - T.y0) / T.dy)), j1 = Math.min(ny - 1, Math.ceil((p.y - R - T.y0) / T.dy));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const x = T.x0 + i * T.dx, y = T.y0 + j * T.dy;
      const d = Math.hypot(x - p.x, y - p.y);
      const k = j * nx + i;
      if (d < bestD[k]) {
        bestD[k] = d;
        bestS[k] = s;
        bestSide[k] = h.hx * (y - p.y) - h.hy * (x - p.x) > 0 ? 1 : -1; // +1 = left
      }
    }
  }
  const origAt = (x, y) => {
    const fx = (x - T.x0) / T.dx, fy = (y - T.y0) / T.dy;
    const i = Math.max(0, Math.min(nx - 2, Math.floor(fx))), j = Math.max(0, Math.min(ny - 2, Math.floor(fy)));
    const tx = Math.min(1, Math.max(0, fx - i)), ty = Math.min(1, Math.max(0, fy - j));
    const a = orig[j * nx + i], b = orig[j * nx + i + 1], c = orig[(j + 1) * nx + i], d = orig[(j + 1) * nx + i + 1];
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty;
  };
  // where along each side the hillside needs a retaining wall, and how tall
  const WSTEP = 3, nw = Math.ceil(route.length / WSTEP) + 1;
  const wallTop = { 1: new Float32Array(nw).fill(NaN), '-1': new Float32Array(nw).fill(NaN) };
  for (let i = 0; i < nw; i++) {
    const s = i * WSTEP;
    if (profile.onBridge(s)) continue;
    const zp = profile.height(s);
    for (const side of [1, -1]) {
      let top = -Infinity;
      for (const lat of [BENCH + 1, BENCH + 4, BENCH + 8]) {
        const o = route.offset(s, side * lat);
        top = Math.max(top, origAt(o.x, o.y));
      }
      if (top - zp > WALL_MIN) wallTop[side][i] = top;
    }
  }
  // drop isolated wall samples, so walls come in runs of at least ~12 m
  for (const side of [1, -1]) {
    const w = wallTop[side];
    for (let i = 0; i < nw; i++) {
      if (isNaN(w[i])) continue;
      let run = 0;
      for (let k = i - 2; k <= i + 2; k++) if (k >= 0 && k < nw && !isNaN(w[k])) run++;
      if (run < 3) w[i] = NaN;
    }
  }
  for (let k = 0; k < N; k++) {
    const d = bestD[k];
    if (d > R) continue;
    const s = bestS[k];
    if (profile.onBridge(s)) continue;
    const zp = profile.height(s);
    const wall = !isNaN(wallTop[bestSide[k]][Math.round(s / WSTEP)]);
    if (d <= BENCH || (wall && d <= WALL_REACH)) T.h[k] = zp - 0.05;
    else if (d <= BENCH + BLEND) T.h[k] = zp + (orig[k] - zp) * ((d - BENCH) / BLEND);
  }
  // collect wall runs per side
  const runs = [];
  for (const side of [1, -1]) {
    let cur = null;
    for (let i = 0; i < nw; i++) {
      const top = wallTop[side][i];
      if (!isNaN(top)) {
        if (!cur) { cur = { side, pts: [] }; runs.push(cur); }
        cur.pts.push({ s: i * WSTEP, top });
      } else cur = null;
    }
  }
  for (const r of runs) {
    // smooth the wall crest a little
    const t = r.pts.map((q) => q.top);
    r.pts.forEach((q, i) => { q.top = (t[Math.max(0, i - 1)] + t[i] + t[Math.min(t.length - 1, i + 1)]) / 3; });
  }
  T.orig = orig;
  return { runs, bench: BENCH, reach: WALL_REACH };
}

// Combined ground function used by all scenery: near the route (and on its bridges)
// the track profile wins, so rails, platforms and poles sit exactly on the track.
// Surveyed street surfaces from the Prague DTM (tools/dtm.py): areas with a height on every
// vertex. Triangulated once; `heightAt(x, y)` returns the ground-level (level 0) surface height
// where an area covers the point (roads and tram areas win over the rest), else null.
// `covered(x, y)` tells whether the DTM describes the street there at all.
// drawn DTM surfaces stand this much above their surveyed height (no z-fighting between classes)
export const DTM_LIFT = { road: 0.03, parking: 0.03, cycle: 0.035, tram: 0.035, sidewalk: 0.05, island: 0.05, platform: 0.06, paved: 0.04, stairs: 0.05, green: 0.02, water: 0.01 };
export const FLUSH = new Set(['road', 'tram', 'parking', 'paved']); // surfaces the tracks are laid in
const STREET = new Set(['road', 'tram', 'parking', 'paved', 'sidewalk', 'island', 'platform', 'cycle']);
// wide surfaces whose interior heights come from the surveyed point cloud; narrow ones (sidewalks,
// islands) are planar between their own exact vertices, which keeps them smooth
const CLOUD = new Set(['road', 'tram', 'parking']);
const SURFACE_RANK = { tram: 9, road: 8, island: 7, platform: 7, sidewalk: 6, parking: 5, cycle: 5, paved: 4, stairs: 3, green: 2, water: 1 };
export class DtmSurface {
  constructor(dtm, terrain, THREE) {
    this.terrain = terrain;
    // surveyed ground heights (DTM 3D lines, densified): the height inside wide areas
    this.zc = 4;
    this.zgrid = new Map();
    const zf = dtm.z || [];
    for (let i = 0; i < zf.length; i += 3) {
      const key = Math.floor(zf[i] / this.zc) * 100003 + Math.floor(zf[i + 1] / this.zc);
      if (!this.zgrid.has(key)) this.zgrid.set(key, []);
      this.zgrid.get(key).push(zf[i], zf[i + 1], zf[i + 2]);
    }
    this.cell = 10;
    this.grid = new Map();
    this.deckGrid = new Map(); // level 1: bridge decks and the streets on them
    this.areas = [];
    for (const a of dtm.areas) {
      if (a.l < 0) continue; // metro and other underground levels
      const fill = (ring) => {
        // missing heights: neighbours on the ring, else the terrain
        for (let i = 0; i < ring.length; i++) {
          if (ring[i][2] !== null) continue;
          let z = null;
          for (let k = 1; k < ring.length && z === null; k++) z = ring[(i + k) % ring.length][2] ?? ring[(i - k + ring.length) % ring.length][2];
          ring[i][2] = z ?? terrain.height(ring[i][0], ring[i][1]);
        }
        return ring;
      };
      const outer = fill(a.r), holes = (a.h || []).map(fill);
      if (outer.length < 3) continue;
      // street model (tools/streets.py): smooth heights and a ready mesh
      if (a.v && a.t) {
        const area = { c: a.c, l: a.l, ring: outer, holes, mesh: [], kerbs: a.k || null, model: true };
        const rank = SURFACE_RANK[a.c] || 1;
        for (let i = 0; i < a.t.length; i += 3) {
          const tri = [a.v[a.t[i]], a.v[a.t[i + 1]], a.v[a.t[i + 2]]];
          area.mesh.push(tri);
          this._index(this.grid, [...tri, rank, a.c]);
        }
        this.areas.push(area);
        continue;
      }
      const v2 = (r) => r.map((p) => new THREE.Vector2(p[0], p[1]));
      let tri;
      try { tri = THREE.ShapeUtils.triangulateShape(v2(outer), holes.map(v2)); } catch { continue; }
      const all = [...outer, ...holes.flat()];
      const area = { c: a.c, l: a.l, ring: outer, holes, mesh: [] };
      const rank = SURFACE_RANK[a.c] || 1;
      const ground = a.l === 0 && a.c !== 'wall' && a.c !== 'roof' && a.c !== 'deck' && a.c !== 'rail';
      for (const [i, j, k] of tri) {
        const p = all[i], q = all[j], r = all[k];
        if (a.l >= 1 && (a.c === 'deck' || a.c === 'road' || a.c === 'tram' || a.c === 'paved' || a.c === 'sidewalk')) {
          this._index(this.deckGrid, [p[0], p[1], p[2], q[0], q[1], q[2], r[0], r[1], r[2]]);
        }
        // render mesh: split to <= 5 m edges, interior heights from the surveyed points
        const n0 = area.mesh.length;
        if (a.l === 0 && STREET.has(a.c)) this._split(p, q, r, CLOUD.has(a.c), area.mesh);
        else area.mesh.push([p, q, r]);
        // the height lookup uses exactly the drawn triangles, so cars stand on what is drawn
        if (ground) for (let m = n0; m < area.mesh.length; m++) this._index(this.grid, [...area.mesh[m], rank, a.c]);
      }
      this.areas.push(area);
    }
  }
  _hit(x, y) {
    const t = this._hitTri(x, y);
    return t ? t.z : null;
  }
  // DTM area class at (x, y) ('road', 'sidewalk', ...), or null
  classAt(x, y) {
    const t = this._hitTri(x, y);
    return t ? t.c : null;
  }
  _hitTri(x, y) {
    const arr = this.grid.get(Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell));
    if (!arr) return null;
    // overlapping ground-level areas: the one closest to the lidar ground, then by rank
    const g = this.terrain.height(x, y);
    let best = null, bestScore = Infinity;
    for (const [p, q, r, rank, c] of arr) {
      const d = (q[1] - r[1]) * (p[0] - r[0]) + (r[0] - q[0]) * (p[1] - r[1]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((q[1] - r[1]) * (x - r[0]) + (r[0] - q[0]) * (y - r[1])) / d;
      const w2 = ((r[1] - p[1]) * (x - r[0]) + (p[0] - r[0]) * (y - r[1])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * p[2] + w2 * q[2] + w3 * r[2];
      const score = Math.abs(z - g) - rank * 0.05;
      if (score < bestScore) { best = { z, c }; bestScore = score; }
    }
    return best;
  }
  // inverse distance weighted surveyed height within r m, or null; with `ref`, only points within
  // `tol` of it count (a street above or below, or a kerb top, must not pull the surface)
  cloudZ(x, y, r = 5, ref = null, tol = 0.6) {
    const c = this.zc, ci = Math.floor(x / c), cj = Math.floor(y / c), n = Math.ceil(r / c);
    let sw = 0, sz = 0;
    for (let i = ci - n; i <= ci + n; i++) for (let j = cj - n; j <= cj + n; j++) {
      const arr = this.zgrid.get(i * 100003 + j);
      if (!arr) continue;
      for (let k = 0; k < arr.length; k += 3) {
        const d2 = (arr[k] - x) ** 2 + (arr[k + 1] - y) ** 2;
        if (d2 > r * r || (ref !== null && Math.abs(arr[k + 2] - ref) > tol)) continue;
        const w = 1 / (d2 + 0.25);
        sw += w; sz += w * arr[k + 2];
      }
    }
    return sw ? sz / sw : null;
  }
  // longest-edge bisection down to 5 m edges (thin carriageway slivers stay cheap)
  _split(p, q, r, ground, out, depth = 0) {
    const l0 = Math.hypot(p[0] - q[0], p[1] - q[1]), l1 = Math.hypot(q[0] - r[0], q[1] - r[1]), l2 = Math.hypot(r[0] - p[0], r[1] - p[1]);
    const e = Math.max(l0, l1, l2);
    if (e <= 5 || depth >= 16) { out.push([p, q, r]); return; }
    if (l1 === e) [p, q, r] = [q, r, p];
    else if (l2 === e) [p, q, r] = [r, p, q];
    // now p-q is the longest edge
    const x = (p[0] + q[0]) / 2, y = (p[1] + q[1]) / 2;
    const zl = (p[2] + q[2]) / 2;
    const m = [x, y, (ground ? this.cloudZ(x, y, 5, zl, 0.6 + 0.02 * e) : null) ?? zl];
    this._split(p, m, r, ground, out, depth + 1);
    this._split(m, q, r, ground, out, depth + 1);
  }
  // ground-level surface height where a DTM area covers (x, y): the surveyed points around,
  // else the area's own triangles
  // (t: flat [ax, ay, az, bx, ...] or [p, q, r, rank, class] with p = [x, y, z])
  _index(grid, t) {
    const [ax, ay, bx, by, cx, cy] = Array.isArray(t[0]) ? [t[0][0], t[0][1], t[1][0], t[1][1], t[2][0], t[2][1]] : [t[0], t[1], t[3], t[4], t[6], t[7]];
    const x0 = Math.min(ax, bx, cx), x1 = Math.max(ax, bx, cx), y0 = Math.min(ay, by, cy), y1 = Math.max(ay, by, cy);
    for (let ix = Math.floor(x0 / this.cell); ix <= Math.floor(x1 / this.cell); ix++) for (let iy = Math.floor(y0 / this.cell); iy <= Math.floor(y1 / this.cell); iy++) {
      const key = ix * 100003 + iy;
      if (!grid.has(key)) grid.set(key, []);
      grid.get(key).push(t);
    }
  }
  // top of a level-1 surface (bridge deck) over (x, y), or null
  deckAt(x, y) {
    const arr = this.deckGrid.get(Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell));
    if (!arr) return null;
    let best = null;
    for (const t of arr) {
      const d = (t[4] - t[7]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[1] - t[7]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((t[4] - t[7]) * (x - t[6]) + (t[6] - t[3]) * (y - t[7])) / d;
      const w2 = ((t[7] - t[1]) * (x - t[6]) + (t[0] - t[6]) * (y - t[7])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * t[2] + w2 * t[5] + w3 * t[8];
      if (best === null || z > best) best = z;
    }
    return best;
  }
  heightAt(x, y) {
    const t = this._hitTri(x, y);
    return t ? t.z : null;
  }
  surfaceAt(x, y) { return this._hitTri(x, y); }
  covered(x, y) { return this.grid.has(Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell)); }
}

export function makeGround(route, terrain, profile, dtm = null) {
  // nearest route position, refined from the 4 m samples by projecting onto the tangent
  // (without this, heights read from the profile step by 4 m x gradient)
  const near = (x, y) => {
    const n = route.nearest(x, y);
    if (!n) return null;
    const p = route.at(n.s);
    const s = Math.max(0, Math.min(route.length, n.s + (x - p.x) * p.hx + (y - p.y) * p.hy));
    const q = route.at(s);
    return { s, d: Math.hypot(x - q.x, y - q.y) };
  };
  return {
    terrain,
    profile,
    route,
    dtm,
    // ground height at an arbitrary point; `deck` marks things that are part of a bridge
    at(x, y, deck = false) {
      const n = near(x, y);
      if (n && profile.onBridge(n.s)) {
        if (n.d < 4 || (deck && n.d < 22)) return profile.height(n.s);
        return terrain.height(x, y);
      }
      if (n && n.d < 4) return profile.height(n.s);
      // surveyed street surface (DTM) where it exists
      const zd = dtm ? dtm.heightAt(x, y) : null;
      if (zd !== null) return zd;
      if (n && n.d < 9) {
        const zt = profile.height(n.s);
        // blend from track level to terrain over 4..9 m
        const k = (n.d - 4) / 5;
        return zt * (1 - k) + terrain.height(x, y) * k;
      }
      return terrain.height(x, y);
    },
    // The smoothed track profile wins next to the tracks: carriageway and tram areas are flush with
    // the track bed within 3 m of a track centre and blend back to their surveyed height by 6 m.
    // (`trackDist` is set by buildWorld once the tracks are smoothed.)
    flush(x, y, z) {
      const d = this.trackDist ? this.trackDist(x, y) : Infinity;
      if (d > 6) return z;
      const n = route.nearest(x, y);
      if (!n || n.d > 12) return z;
      const zt = profile.height(n.s) + 0.14;
      const k = Math.max(0, Math.min(1, (d - 3) / 3));
      return zt + (z - zt) * k * k * (3 - 2 * k);
    },
    // top of the street surface as drawn, where cars and walkers stand: the DTM area (flush with
    // the tracks, lifted per class), else an OSM road ribbon (0.12 above the ground)
    surface(x, y) {
      if (dtm) {
        const n = near(x, y);
        const t = n && profile.onBridge(n.s) && n.d < 22 ? null : dtm.surfaceAt(x, y);
        if (t) return t.z + (DTM_LIFT[t.c] ?? 0.03); // flush with the tracks already (world.js flushDtm)
      }
      return this.at(x, y) + 0.12;
    },
    // deck height if (x, y) is on one of the route's bridges, else null
    deckAt(x, y) {
      const n = near(x, y);
      return n && n.d < 22 && profile.onBridge(n.s) ? profile.height(n.s) : null;
    },
    // ground at a route position with lateral offset (left > 0)
    atRoute(s, lateral) {
      if (Math.abs(lateral) < 9 || profile.onBridge(s)) return profile.height(s);
      const o = route.offset(s, lateral);
      return this.at(o.x, o.y);
    },
  };
}
