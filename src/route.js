// Route geometry along the line: arc-length parameterised polyline in local metres
// (x = east, y = north). Three.js world uses (x, height, -y).
import { SMALL_RADIUS } from './speedSigns.js';

// Resample a polyline every `step` metres of its arc length and smooth it with a Gaussian
// window (the window shrinks symmetrically at the ends, so end points stay put). OSM draws
// streets as straight segments; this turns them into continuous curves (the cars' and walkers'
// paths). Returns the points and their arc-length positions along the ORIGINAL polyline. `radius`
// may be a function of that arc length. A radius of 0 resamples only (a window under one step
// still averaged three points). The track is not smoothed: the build draws it as curves (#204, #477).
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
  const kOf = (rad) => (rad > 0 ? Math.max(1, Math.round(rad / (L / (n - 1) || 1))) : 0);
  const weights = new Map(), win = (k) => {
    if (!weights.has(k)) { const w = []; for (let d = 0; d <= k; d++) w.push(Math.exp(-0.5 * (d / (k / 2)) ** 2)); weights.set(k, w); }
    return weights.get(k);
  };
  const out = [];
  for (let i = 0; i < n; i++) {
    const k = kOf(typeof radius === 'function' ? radius(ss[i]) : radius);
    if (!k) { out.push([xs[i], ys[i]]); continue; }
    const w = win(k), r = Math.min(k, i, n - 1 - i);
    let sx = 0, sy = 0, sw = 0;
    for (let d = -r; d <= r; d++) { const ww = w[Math.abs(d)]; sx += xs[i + d] * ww; sy += ys[i + d] * ww; sw += ww; }
    out.push([sx / sw, sy / sw]);
  }
  return { pts: out, s: ss };
}

// The line data is built with its track drawn as curves (`trackCurve`, tools/track_curve.py, #204) and the run past
// both termini (`pathExt`, tools/route.py, #477): the page smooths no track and walks none (#276 step 2). Data built
// before them cannot be drawn as the build meant it, so it does not load.
export function checkBuiltRoute(data) {
  const missing = ['trackCurve', 'pathExt'].filter((k) => !data[k]);
  if (missing.length) throw new Error(`line ${data.line} data lacks ${missing.join(' and ')}: built before #477, rebuild it (tools/rebuild.py)`);
}

// the cant's layout: the comfortable unbalanced lateral acceleration (m/s2) and the largest cant (m); the limit in a curve
// takes the route's `curveAccel` (_designSpeed)
const A_LAT = 0.8, CANT_MAX = 0.1;
// m a curve's limit starts before the radius asks for it: the 16 m estimate reads a curve's start late (its full radius
// about 12 m in, where the transition is short), and the limit is for the front going in
const CURVE_AHEAD = 5;

export class Route {
  // `ext` = {before, after}: the track past the ends (the line data's `pathExt`), at negative s / past length
  constructor(pts, ext = null) {
    // the build's points as they are, s along them (stops, switches and signals are measured along the path).
    // (Resampled every metre, the chords cut each point of a curve by about a quarter of its turn: 1.0-1.9 cm on
    // lines 9, 22 and 23, over the 1 cm the build is held to, #477)
    const before = ext?.before || [], after = ext?.after || [];
    const all = [...before, ...pts, ...after];
    const s = new Float64Array(all.length);
    for (let i = 1; i < all.length; i++) s[i] = s[i - 1] + Math.hypot(all[i][0] - all[i - 1][0], all[i][1] - all[i - 1][1]);
    const s0 = s[before.length]; // arc length of the run-in = where the path starts
    let L = 0;
    for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    this.pts = all.map((p) => [p[0], p[1]]);
    this.s = Array.from(s, (v) => v - s0);
    this.length = L; // the route itself ends here; the run-out continues past it
    this.coarse = this.pts.filter((_, i) => i % 8 === 0); // for the minimap
    this._buildSamples();
  }

  _index(s) {
    let lo = 0, hi = this.s.length - 1;
    if (s <= this.s[0]) return 0;
    if (s >= this.s[hi]) return hi - 1;
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
    this.samples = [];
    const p = {};
    for (let s = 0; s <= this.length; s += 4) {
      this.at(s, p);
      const q = [p.x, p.y, s, this.samples.length];
      this.samples.push(q);
      const k = this.key(p.x, p.y);
      if (!this.grid.has(k)) this.grid.set(k, []);
      this.grid.get(k).push(q);
    }
  }

  key(x, y) {
    return Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell);
  }

  // Nearest distance from (x, y) to the route (only accurate below ~40 m).
  distance(x, y) {
    const n = this.nearest(x, y);
    return n ? n.d : Infinity;
  }

  // Nearest point of the route to (x, y) within ~40 m: { d, s } or null. The nearest 4 m sample,
  // refined onto the chords to its neighbours (the sample alone was up to 2 m off: two tracks 0.4 m
  // apart read 0.4-1.9 m, and the Letenská interlaced track fell apart into 3 m pieces).
  nearest(x, y) {
    const cx = Math.floor(x / this.cell), cy = Math.floor(y / this.cell);
    let best = null, bd = Infinity;
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      const arr = this.grid.get((cx + dx) * 100003 + (cy + dy));
      if (!arr) continue;
      for (const q of arr) {
        const d = (q[0] - x) ** 2 + (q[1] - y) ** 2;
        if (d < bd) { bd = d; best = q; }
      }
    }
    if (!best) return null;
    let out = { d: Math.sqrt(bd), s: best[2] };
    for (const o of [-1, 1]) {
      const r = this.samples[best[3] + o];
      if (!r) continue;
      const ex = r[0] - best[0], ey = r[1] - best[1], l2 = ex * ex + ey * ey;
      if (l2 < 1e-9) continue;
      const t = Math.max(0, Math.min(1, ((x - best[0]) * ex + (y - best[1]) * ey) / l2));
      const d = Math.hypot(best[0] + ex * t - x, best[1] + ey * t - y);
      if (d < out.d) out = { d, s: best[2] + (r[2] - best[2]) * t };
    }
    return out;
  }

  // A combined run may visit this street in both directions. Select a traversal, not just
  // the closest piece of track (9 -> 10 otherwise picked its own track as "oncoming").
  nearestOnHeading(x, y, hx, hy, minAlign = 0.5) {
    const near = this.nearest(x, y);
    if (near) {
      const h = this.heading(near.s, 3);
      if (h.hx * hx + h.hy * hy > minAlign) return near;
    }
    const cx = Math.floor(x / this.cell), cy = Math.floor(y / this.cell);
    let out = null;
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const q of this.grid.get((cx + dx) * 100003 + cy + dy) || []) {
        const r = this.samples[q[3] + 1];
        if (!r) continue;
        const ex = r[0] - q[0], ey = r[1] - q[1], l2 = ex * ex + ey * ey;
        if (l2 < 1e-9 || (ex * hx + ey * hy) / Math.sqrt(l2) <= minAlign) continue;
        const t = Math.max(0, Math.min(1, ((x - q[0]) * ex + (y - q[1]) * ey) / l2));
        const d = Math.hypot(q[0] + ex * t - x, q[1] + ey * t - y);
        if (!out || d < out.d) out = { d, s: q[2] + (r[2] - q[2]) * t };
      }
    }
    return out;
  }

  // Curve radius (m) at s itself, from heading change over 16 m.
  _radius(s) {
    const a = this.heading(s - 8, 4), b = this.heading(s + 8, 4);
    const dTheta = Math.acos(Math.max(-1, Math.min(1, a.hx * b.hx + a.hy * b.hy)));
    return dTheta > 1e-4 ? 16 / dTheta : 1e6;
  }

  // The same at the nearest 5 m, for what is read many times a frame.
  radiusAt(s) {
    if (!this.radii) {
      const n = Math.ceil(this.length / 5) + 1;
      this.radii = new Float32Array(n);
      for (let i = 0; i < n; i++) this.radii[i] = this._radius(i * 5);
    }
    return this.radii[Math.max(0, Math.min(this.radii.length - 1, Math.round(s / 5)))];
  }

  // Posted speed and dedicated track at s from `speedInfo` (data.speed, tools/osm_speeds.py: the
  // OSM maxspeed of the tram way, as OpenRailwayMap shows it, and "no vehicle road along it").
  _speedInfo(s) {
    const I = this.speedInfo;
    if (!I) return { osm: 0, dedicated: false };
    const k = Math.max(0, Math.min(I.osm.length - 1, Math.round(s / I.step)));
    return { osm: I.osm[k], dedicated: !!I.dedicated[k] };
  }

  // Cant (superelevation) profile along the route, every 2 m, signed (+ = the left rail lower, the
  // tram leans left). Only on dedicated track, which has no road surface to keep level, and not at
  // stops (a platform edge stays level with the doors) nor near the ends of the route (terminus
  // loops, depots). The cant a curve gets is 60 % of the balanced cant v² / (g R) · 1.5 m at the
  // speed the curve allows with full cant, at most 100 mm; it runs in and out linearly at most
  // 100 mm per 30 m (a transition curve), then is smoothed, so the tram and the view roll gently.
  // `stops`: [{p0, p1}] platform stretches along the route.
  prepareCant(stops = []) {
    const step = 2, n = Math.ceil(this.length / step) + 1;
    const c = new Float32Array(n);
    const level = (s) => s < 150 || s > this.length - 150 || stops.some((st) => s > st.p0 - 25 && s < st.p1 + 25);
    for (let i = 0; i < n; i++) {
      const s = i * step;
      if (!this._speedInfo(s).dedicated || level(s)) continue;
      const a = this.heading(s - 8, 4), b = this.heading(s + 8, 4);
      const turn = Math.atan2(a.hx * b.hy - a.hy * b.hx, a.hx * b.hx + a.hy * b.hy); // over 16 m
      const r = Math.abs(turn) > 1e-4 ? 16 / Math.abs(turn) : 1e6;
      if (r > 1500) continue;
      const v = this._designSpeed(s, r, true) / 3.6;
      c[i] = Math.sign(turn) * Math.min(CANT_MAX, 0.6 * 1.5 * v * v / (9.81 * r));
    }
    // run-in / run-out ramps: at most CANT_MAX per 30 m, both ways, towards zero first
    const d = (CANT_MAX / 30) * step;
    for (let pass = 0; pass < 2; pass++) {
      for (let i = 1; i < n; i++) c[i] = Math.sign(c[i]) * Math.min(Math.abs(c[i]), Math.abs(c[i - 1]) + d) * (Math.sign(c[i]) === Math.sign(c[i - 1]) || !c[i - 1] ? 1 : 0);
      for (let i = n - 2; i >= 0; i--) c[i] = Math.sign(c[i]) * Math.min(Math.abs(c[i]), Math.abs(c[i + 1]) + d) * (Math.sign(c[i]) === Math.sign(c[i + 1]) || !c[i + 1] ? 1 : 0);
    }
    // smooth over ±6 m (the ramp corners)
    const out = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      let sum = 0, w = 0;
      for (let k = -3; k <= 3; k++) { const j = i + k; if (j < 0 || j >= n) continue; const ww = 4 - Math.abs(k); sum += c[j] * ww; w += ww; }
      out[i] = sum / w;
    }
    this.cant = { step, c: out };
  }

  _cantSigned(s) {
    const C = this.cant;
    if (!C) return 0;
    const f = Math.max(0, Math.min(C.c.length - 1.001, s / C.step)), i = Math.floor(f), u = f - i;
    return C.c[i] * (1 - u) + C.c[i + 1] * u;
  }

  // cant (m) at s
  cantAt(s) { return Math.abs(this._cantSigned(s)); }

  // signed lean of a tram into the curve at s (rad, + = towards the left), from the cant
  rollAt(s) { return Math.atan2(this._cantSigned(s), 1.5); }

  // Speed a curve of radius r allows (km/h) with the given cant credit. With full cant, the speed the track was laid out
  // for (prepareCant: unbalanced A_LAT plus the cant), in 5 km/h: 50 in streets, 60 on dedicated track, however it is
  // signed. Otherwise the limit, in whole km/h, as no sign stands at such a curve: unbalanced `curveAccel`
  // (`curve-lateral-acceleration`) plus what the cant takes. The drivers of two line 23 rides took the unsigned curves of
  // R 30-60 m at 1.2-1.6 m/s², where 0.8 and the 5 km/h steps held the autopilot 6-14 km/h under them (#451). Never above
  // the posted speed, which stands for the sign, nor the car's top speed (`speedTop`), and 50 without a posted speed
  // (`max-speed`: more needs a Rychlostník, also off the road). A curve under SMALL_RADIUS has its sign: `curveFloor`,
  // 15 km/h over the whole of it (`small-radius-speed`).
  _designSpeed(s, r, fullCant, cant = 0, accel = this.curveAccel) {
    const { osm, dedicated } = this._speedInfo(s);
    if (fullCant) {
      const vd = Math.floor((Math.sqrt((A_LAT + (dedicated ? CANT_MAX : 0) * 9.81 / 1.5) * r) * 3.6) / 5) * 5;
      return Math.max(10, Math.min(Math.min(60, osm || (dedicated ? 60 : 50)), vd));
    }
    const floor = this.curveFloor ?? 10;
    const v = r < SMALL_RADIUS ? floor : Math.max(floor, Math.floor(Math.sqrt(((accel ?? A_LAT) + cant * 9.81 / 1.5) * r) * 3.6));
    const cap = osm ? Math.min(osm, this.speedTop ?? osm) : 50;
    return Math.min(cap, v);
  }

  // speed the curve at s allows (km/h), with the cant actually built there
  curveSpeed(s, accel = this.curveAccel) { return this._designSpeed(s, this._radius(s), false, this.cantAt(s), accel); }

  // Speed limits (km/h) to the metre: the curve and the posted speed (curveSpeed), `past` metres on from where they ask
  // for it (`restriction-past`: 15 m on until #211, from 5 m bins) and CURVE_AHEAD before, plus the extra restrictions,
  // which bring their own ends. `values` is the same every 5 m, each bin its lowest (the signs). `accel`: the curves' unbalanced
  // lateral acceleration, the route's own unless the autopilot asks for its milder curves (#242).
  speedLimits(extra = [], past = 0, accel = this.curveAccel) {
    const step = 5, metres = Math.ceil(this.length) + 1;
    const curve = new Float32Array(metres);
    for (let m = 0; m < metres; m++) curve[m] = this.curveSpeed(m, accel);
    const base = new Float32Array(metres);
    for (let m = 0; m < metres; m++) {
      let v = 99;
      for (let j = Math.max(0, m - past); j <= Math.min(metres - 1, m + CURVE_AHEAD); j++) v = Math.min(v, curve[j]);
      base[m] = v;
    }
    const fine = new Float32Array(metres).fill(99);
    for (const e of extra) {
      const last = Math.min(metres - 1, Math.floor(e.to));
      for (let m = Math.max(0, Math.floor(e.from)); m <= last; m++) fine[m] = Math.min(fine[m], e.v);
    }
    const values = new Float32Array(Math.ceil(this.length / step) + 1).fill(99);
    for (let m = 0; m < metres; m++) {
      const i = Math.floor(m / step);
      values[i] = Math.min(values[i], base[m], fine[m]);
    }
    if (values[values.length - 1] === 99) values[values.length - 1] = values[values.length - 2];
    const metre = (s) => Math.max(0, Math.min(metres - 1, Math.floor(s)));
    const restriction = (s) => fine[metre(s)];
    return { step, values, restriction, at: (s) => { const m = metre(s); return Math.min(base[m], fine[m]); } };
  }
}
