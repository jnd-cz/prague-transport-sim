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

  // bilinear height at local metres (x east, y north)
  height(x, y) {
    const fx = (x - this.x0) / this.dx, fy = (y - this.y0) / this.dy;
    const ix = Math.floor(fx), iy = Math.floor(fy);
    const tx = fx - ix, ty = fy - iy;
    const a = this.cell(ix, iy), b = this.cell(ix + 1, iy), c = this.cell(ix, iy + 1), d = this.cell(ix + 1, iy + 1);
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty;
  }
}

// Route elevation z(s): terrain sampled along the track, smoothed like real vertical
// alignment, with bridge decks bridged linearly between their abutments.
export class Profile {
  constructor(route, terrain, bridges = [], tunnels = []) {
    const step = (this.step = 2);
    const n = (this.n = Math.ceil(route.length / step) + 1);
    let z = new Float32Array(n);
    const p = {};
    for (let i = 0; i < n; i++) {
      route.at(i * step, p);
      z[i] = terrain.height(p.x, p.y);
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
export function makeGround(route, terrain, profile) {
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
    // ground height at an arbitrary point; `deck` marks things that are part of a bridge
    at(x, y, deck = false) {
      const n = near(x, y);
      if (n && profile.onBridge(n.s)) {
        if (n.d < 4 || (deck && n.d < 22)) return profile.height(n.s);
        return terrain.height(x, y);
      }
      if (n && n.d < 9) {
        const zt = profile.height(n.s);
        if (n.d < 4) return zt;
        // blend from track level to terrain over 4..9 m
        const k = (n.d - 4) / 5;
        return zt * (1 - k) + terrain.height(x, y) * k;
      }
      return terrain.height(x, y);
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
