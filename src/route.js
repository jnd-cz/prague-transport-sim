// Route geometry along the line: arc-length parameterised polyline in local metres
// (x = east, y = north). Three.js world uses (x, height, -y).

// Resample a polyline every `step` metres of its arc length and smooth it with a Gaussian
// window (the window shrinks symmetrically at the ends, so end points stay put). OSM draws
// curves as straight segments; this turns them into continuous curves. Returns the points
// and their arc-length positions along the ORIGINAL polyline.
export function smoothPolyline(pts, step = 1, radius = 6) {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
  const L = cum[cum.length - 1];
  const n = Math.max(2, Math.round(L / step) + 1);
  const xs = new Float64Array(n), ys = new Float64Array(n), ss = new Float64Array(n);
  let j = 0;
  for (let i = 0; i < n; i++) {
    const s = (L * i) / (n - 1);
    while (j < pts.length - 2 && cum[j + 1] < s) j++;
    const seg = cum[j + 1] - cum[j] || 1e-9, t = Math.max(0, Math.min(1, (s - cum[j]) / seg));
    xs[i] = pts[j][0] + (pts[j + 1][0] - pts[j][0]) * t;
    ys[i] = pts[j][1] + (pts[j + 1][1] - pts[j][1]) * t;
    ss[i] = s;
  }
  const k = Math.max(1, Math.round(radius / (L / (n - 1) || 1)));
  const sigma = k / 2;
  const w = [];
  for (let d = 0; d <= k; d++) w.push(Math.exp(-0.5 * (d / sigma) ** 2));
  const out = [];
  for (let i = 0; i < n; i++) {
    const r = Math.min(k, i, n - 1 - i);
    let sx = 0, sy = 0, sw = 0;
    for (let d = -r; d <= r; d++) { const ww = w[Math.abs(d)]; sx += xs[i + d] * ww; sy += ys[i + d] * ww; sw += ww; }
    out.push([sx / sw, sy / sw]);
  }
  return { pts: out, s: ss };
}

export class Route {
  constructor(pts) {
    // smooth curves but keep the original arc-length parameter (stops, switches and
    // signals were measured along the unsmoothed OSM path)
    const sm = smoothPolyline(pts, 1, 6);
    this.pts = sm.pts;
    this.s = sm.s;
    this.length = this.s[this.s.length - 1];
    this.coarse = this.pts.filter((_, i) => i % 8 === 0); // for the minimap
    this._buildSamples();
  }

  _index(s) {
    let lo = 0, hi = this.s.length - 1;
    if (s <= 0) return 0;
    if (s >= this.length) return hi - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.s[mid] <= s) lo = mid; else hi = mid;
    }
    return lo;
  }

  // Position and unit heading at arc length s.
  at(s, out = {}) {
    const i = this._index(s);
    const a = this.pts[i], b = this.pts[i + 1];
    const seg = this.s[i + 1] - this.s[i] || 1e-9;
    const t = Math.max(0, Math.min(1, (s - this.s[i]) / seg));
    out.x = a[0] + (b[0] - a[0]) * t;
    out.y = a[1] + (b[1] - a[1]) * t;
    const dl = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1e-9;
    out.hx = (b[0] - a[0]) / dl;
    out.hy = (b[1] - a[1]) / dl;
    return out;
  }

  // Smoothed heading: chord between two points around s (avoids kinks at OSM nodes).
  heading(s, span = 6) {
    const a = this.at(s - span), b = this.at(s + span);
    const dx = b.x - a.x, dy = b.y - a.y, l = Math.hypot(dx, dy) || 1;
    return { hx: dx / l, hy: dy / l };
  }

  // Point at s shifted sideways; lateral > 0 is to the left of the direction of travel.
  offset(s, lateral) {
    const p = this.at(s);
    const h = this.heading(s, 3);
    return { x: p.x - h.hy * lateral, y: p.y + h.hx * lateral, hx: h.hx, hy: h.hy };
  }

  // Samples every 4 m with a spatial hash, used for distance-to-track queries.
  _buildSamples() {
    this.cell = 40;
    this.grid = new Map();
    const p = {};
    for (let s = 0; s <= this.length; s += 4) {
      this.at(s, p);
      const k = this.key(p.x, p.y);
      if (!this.grid.has(k)) this.grid.set(k, []);
      this.grid.get(k).push([p.x, p.y, s]);
    }
  }

  key(x, y) {
    return Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell);
  }

  // Approximate nearest distance from (x, y) to the route (only accurate below ~40 m).
  distance(x, y) {
    const cx = Math.floor(x / this.cell), cy = Math.floor(y / this.cell);
    let best = Infinity;
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const arr = this.grid.get((cx + dx) * 100003 + (cy + dy));
      if (!arr) continue;
      for (const q of arr) best = Math.min(best, Math.hypot(q[0] - x, q[1] - y));
    }
    return best;
  }

  // Nearest route sample to (x, y) within ~40 m: { d, s } or null.
  nearest(x, y) {
    const cx = Math.floor(x / this.cell), cy = Math.floor(y / this.cell);
    let best = null;
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const arr = this.grid.get((cx + dx) * 100003 + (cy + dy));
      if (!arr) continue;
      for (const q of arr) {
        const d = Math.hypot(q[0] - x, q[1] - y);
        if (!best || d < best.d) best = { d, s: q[2] };
      }
    }
    return best;
  }

  // Curve radius (m) at s, from heading change over 16 m.
  radiusAt(s) {
    if (!this.radii) {
      const n = Math.ceil(this.length / 5) + 1;
      this.radii = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const a = this.heading(i * 5 - 8, 4), b = this.heading(i * 5 + 8, 4);
        const dTheta = Math.acos(Math.max(-1, Math.min(1, a.hx * b.hx + a.hy * b.hy)));
        this.radii[i] = dTheta > 1e-4 ? 16 / dTheta : 1e6;
      }
    }
    return this.radii[Math.max(0, Math.min(this.radii.length - 1, Math.round(s / 5)))];
  }

  // Curvature-based speed limits (km/h) sampled every 5 m, plus extra restrictions.
  speedLimits(extra = []) {
    const step = 5;
    const n = Math.ceil(this.length / step) + 1;
    const lim = new Float32Array(n).fill(50);
    for (let i = 0; i < n; i++) {
      const s = i * step;
      const r = this.radiusAt(s);
      let v = 50;
      if (r < 25) v = 10; else if (r < 45) v = 15; else if (r < 80) v = 20;
      else if (r < 140) v = 30; else if (r < 250) v = 40;
      lim[i] = v;
    }
    // a curve limit applies to the whole curve: take min over a short window
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let v = lim[i];
      for (let j = Math.max(0, i - 3); j <= Math.min(n - 1, i + 1); j++) v = Math.min(v, lim[j]);
      out[i] = v;
    }
    for (const e of extra) {
      for (let s = e.from; s <= e.to; s += step) {
        const i = Math.round(s / step);
        if (i >= 0 && i < n) out[i] = Math.min(out[i], e.v);
      }
    }
    return { step, values: out, at: (s) => out[Math.max(0, Math.min(n - 1, Math.floor(s / step)))] };
  }
}
