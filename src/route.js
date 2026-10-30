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

// The track beyond the ends of a route: the GTFS path starts and ends at the terminus stops, but a
// two-car set standing there reaches 30 m further back. Walk the OSM track chains from each end
// (continuing across chain joints in the most aligned direction) for `len` metres; where no track
// continues, go straight on. Returns {before, after} point lists (before runs towards the start).
export function extendAlongTracks(tracks, pts, len = 60) {
  const walk = (p, dx, dy) => {
    const out = [];
    let cur = [p[0], p[1]], hx = dx, hy = dy, left = len, guard = 0;
    while (left > 0 && guard++ < 20) {
      // the chain segment through cur that heads our way
      let best = null;
      for (const t of tracks) {
        const q = t.p;
        for (let i = 0; i < q.length - 1; i++) {
          const ax = q[i][0], ay = q[i][1], bx = q[i + 1][0], by = q[i + 1][1];
          const sx = bx - ax, sy = by - ay, l2 = sx * sx + sy * sy;
          if (!l2) continue;
          const u = Math.max(0, Math.min(1, ((cur[0] - ax) * sx + (cur[1] - ay) * sy) / l2));
          const d = Math.hypot(ax + sx * u - cur[0], ay + sy * u - cur[1]);
          if (d > 1.5) continue;
          const l = Math.sqrt(l2), dot = (sx * hx + sy * hy) / l;
          if (Math.abs(dot) < 0.6) continue;
          // forward along the chain = increasing index if the segment points our way
          const score = d - Math.abs(dot);
          if (!best || score < best.score) best = { score, q, i, u, fwd: dot > 0 };
        }
      }
      if (!best) break;
      const { q, fwd } = best;
      let i = best.i;
      const seq = [];
      if (fwd) for (let k = i + 1; k < q.length; k++) seq.push(q[k]);
      else for (let k = i; k >= 0; k--) seq.push(q[k]);
      let moved = false;
      for (const n of seq) {
        const l = Math.hypot(n[0] - cur[0], n[1] - cur[1]);
        if (l < 0.05) continue;
        if (l >= left) { cur = [cur[0] + (n[0] - cur[0]) * left / l, cur[1] + (n[1] - cur[1]) * left / l]; out.push(cur); left = 0; moved = true; break; }
        hx = (n[0] - cur[0]) / l; hy = (n[1] - cur[1]) / l;
        cur = [n[0], n[1]]; out.push(cur); left -= l; moved = true;
      }
      if (!moved) break;
    }
    if (left > 0) out.push([cur[0] + hx * left, cur[1] + hy * left]); // no track: straight on
    return out;
  };
  const n = pts.length;
  const h0 = [pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]], l0 = Math.hypot(...h0) || 1;
  const h1 = [pts[n - 1][0] - pts[n - 2][0], pts[n - 1][1] - pts[n - 2][1]], l1 = Math.hypot(...h1) || 1;
  return { before: walk(pts[0], h0[0] / l0, h0[1] / l0).reverse(), after: walk(pts[n - 1], h1[0] / l1, h1[1] / l1) };
}

// curve speeds: comfortable unbalanced lateral acceleration (m/s2) and the largest cant (m)
const A_LAT = 0.8, CANT_MAX = 0.1;

export class Route {
  // `ext` = {before, after}: track beyond the ends (extendAlongTracks), at negative s / past length
  constructor(pts, ext = null) {
    // smooth curves but keep the original arc-length parameter (stops, switches and
    // signals were measured along the unsmoothed OSM path)
    const before = ext?.before || [], after = ext?.after || [];
    const all = [...before, ...pts, ...after];
    let s0 = 0; // arc length of the run-in = where the original path starts
    for (let i = 1; i <= before.length; i++) s0 += Math.hypot(all[i][0] - all[i - 1][0], all[i][1] - all[i - 1][1]);
    let L = 0;
    for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    const sm = smoothPolyline(all, 1, 6);
    this.pts = sm.pts;
    this.s = Array.from(sm.s, (v) => v - s0);
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

  // speed a curve of radius r allows (km/h) with the given cant credit: unbalanced lateral
  // acceleration A_LAT plus what the cant takes, never above the posted OSM speed or the cap
  // (50 in streets, 60 on dedicated track; the 65-70 km/h pilot stretches are capped for now)
  _designSpeed(s, r, fullCant, cant = 0) {
    const { osm, dedicated } = this._speedInfo(s);
    const a = A_LAT + (fullCant ? (dedicated ? CANT_MAX : 0) : cant) * 9.81 / 1.5;
    const v = Math.floor((Math.sqrt(a * r) * 3.6) / 5) * 5;
    const cap = Math.min(60, osm || (dedicated ? 60 : 50));
    return Math.max(10, Math.min(cap, v));
  }

  // speed the curve at s allows (km/h), with the cant actually built there
  curveSpeed(s) { return this._designSpeed(s, this.radiusAt(s), false, this.cantAt(s)); }

  // Speed limits (km/h) sampled every 5 m: curves (curveSpeed) plus extra restrictions.
  speedLimits(extra = []) {
    const step = 5;
    const n = Math.ceil(this.length / step) + 1;
    const lim = new Float32Array(n).fill(50);
    for (let i = 0; i < n; i++) lim[i] = this.curveSpeed(i * step);
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
