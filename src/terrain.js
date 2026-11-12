// Terrain heights (ČÚZK DMR 5G grid) and the smoothed vertical profile of the route.

// A regular height grid (rows go south: dy < 0): the coarse terrain of a line, or one block of the
// fine terrain (tools/fine_terrain.py).
export class Grid {
  constructor(x0, y0, dx, dy, nx, ny, h) {
    Object.assign(this, { x0, y0, dx, dy, nx, ny, h });
  }

  // grid value with clamping at the edges
  cell(ix, iy) {
    ix = Math.max(0, Math.min(this.nx - 1, ix));
    iy = Math.max(0, Math.min(this.ny - 1, iy));
    return this.h[iy * this.nx + ix];
  }

  contains(x, y) {
    const fx = (x - this.x0) / this.dx, fy = (y - this.y0) / this.dy;
    return fx >= 0 && fy >= 0 && fx <= this.nx - 1 && fy <= this.ny - 1;
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

  // lower the mesh triangle under (x, y) so its surface there is at most zmax (by at most `cap` m)
  lowerAt(x, y, zmax, cap = Infinity) {
    const fx = (x - this.x0) / this.dx, fy = (y - this.y0) / this.dy;
    const ix = Math.floor(fx), iy = Math.floor(fy);
    if (ix < 0 || iy < 0 || ix >= this.nx - 1 || iy >= this.ny - 1) return;
    const excess = this.height(x, y) - zmax;
    if (excess <= 0 || excess > cap) return;
    const tx = fx - ix, ty = fy - iy;
    const A = iy * this.nx + ix, B = A + 1, C = A + this.nx;
    if (tx + ty <= 1) this.h[A] -= excess;
    else this.h[C + 1] -= excess;
    this.h[B] -= excess;
    this.h[C] -= excess;
  }
}

// The terrain of a line: the coarse grid over everything (10 x 15 m, build_line.py), and where
// tools/fine_terrain.py made it, a 2 m grid near the tracks in blocks (addFine). `height` asks the fine
// block first; the edits (carving, lowering under tracks and streets) go to every grid (`grids()`).
// The coarse grid's fields stay on the Terrain itself (x0, y0, dx, dy, nx, ny, h, cell).
export class Terrain extends Grid {
  constructor(t) {
    const bin = atob(t.data);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const raw = new Int16Array(bytes.buffer);
    const h = new Float32Array(raw.length);
    for (let i = 0; i < raw.length; i++) h[i] = t.base + raw[i] * t.scale;
    super(t.x0, t.y0, t.dx, t.dy, t.nx, t.ny, h);
    let min = Infinity;
    for (const v of this.h) min = Math.min(min, v);
    this.min = min;
    this.fine = new Map(); // "bi,bj" -> Grid
    this.fineIdx = new Map(); // bi * 65536 + bj -> the same Grid
    this.fineMeta = null;
  }

  // the fine blocks (meta: lineN.fine.json, q: its Int16 samples)
  addFine(meta, q) {
    const B = meta.B, n = B + 1, bs = B * meta.step;
    meta.blocks.forEach(([bi, bj], k) => {
      const h = new Float32Array(n * n);
      for (let i = 0; i < n * n; i++) h[i] = meta.base + q[k * n * n + i] * meta.scale;
      const g = Object.assign(new Grid(meta.x0 + bi * bs, meta.y0 - bj * bs, meta.step, -meta.step, n, n, h), { bi, bj });
      this.fine.set(`${bi},${bj}`, g);
      this.fineIdx.set(bi * 65536 + bj, g);
    });
    this.fineMeta = { ...meta, bs };
  }

  fineAt(x, y) {
    const m = this.fineMeta;
    if (!m) return null;
    return this.fineIdx.get(Math.floor((x - m.x0) / m.bs) * 65536 + Math.floor((m.y0 - y) / m.bs)) || null;
  }

  height(x, y) {
    const f = this.fineAt(x, y);
    return f ? f.height(x, y) : super.height(x, y);
  }

  coarseHeight(x, y) { return super.height(x, y); }

  // every grid the edits apply to: the coarse one (as a plain Grid view) and the fine blocks
  grids() {
    return [this.coarse(), ...this.fine.values()];
  }

  // the coarse grid as a plain Grid (its height ignores the fine blocks)
  coarse() {
    if (!this._coarse) this._coarse = new Grid(this.x0, this.y0, this.dx, this.dy, this.nx, this.ny, this.h);
    return this._coarse;
  }

  // lower the surface at (x, y) to at most zmax in every grid (cap: deeper is not ours to dig; on a
  // fine block at least 15 m: a 2 m cell lowered stays local, where a coarse 10 x 15 m triangle
  // dragged its surroundings down; quay walls stood 8-9 m over the surveyed river)
  lowerAt(x, y, zmax, cap = Infinity) {
    const c = this.coarse();
    if (c.contains(x, y)) c.lowerAt(x, y, zmax, cap);
    const m = this.fineMeta;
    if (!m) return;
    // (as finesAt, inline: millions of calls under the streets at load, #205)
    const bi = Math.floor((x - m.x0) / m.bs), bj = Math.floor((m.y0 - y) / m.bs), fcap = Math.max(cap, 15);
    for (let i = bi - 1; i <= bi; i++) for (let j = bj - 1; j <= bj; j++) {
      const g = this.fineIdx.get(i * 65536 + j);
      if (g && g.contains(x, y)) g.lowerAt(x, y, zmax, fcap);
    }
  }

  // the fine blocks whose area (edges included) holds (x, y): at most the four around a block corner,
  // looked up by index (scanning every block made the lowering under the streets take a minute)
  finesAt(x, y) {
    const m = this.fineMeta, out = [];
    if (!m) return out;
    const fx = (x - m.x0) / m.bs, fy = (m.y0 - y) / m.bs, bi = Math.floor(fx), bj = Math.floor(fy);
    for (let i = bi - 1; i <= bi; i++) for (let j = bj - 1; j <= bj; j++) {
      const g = this.fine.get(`${i},${j}`);
      if (g && g.contains(x, y)) out.push(g);
    }
    return out;
  }
}

// Route elevation z(s): terrain sampled along the track, smoothed like real vertical
// alignment, with bridge decks bridged linearly between their abutments.
// Surfaces of the IPR "Mosty 3D" bridges right above/below the track centre, every 2 m along
// the route: Map 2 m bin -> list of z where a bridge triangle is crossed by the vertical line.
// The Mosty 3D bridge models as a surface lookup anywhere (not only along the route): topAt(x, y, ref,
// tol) is the highest up-facing model surface at (x, y) within ref ± tol, or null.
export function bridgeModel(geo) {
  const grid = new Map(), cell = 10;
  if (geo?.buildings?.arr) {
    const { arr, q, chunks } = geo.buildings;
    for (const ch of chunks) {
      if (!ch.k) continue;
      const [ox, oy, oz] = ch.o;
      let v = ch.v;
      for (const [bi, count] of ch.b.entries()) {
        if (ch.k[bi] !== 1) { v += count; continue; }
        for (let t = 0; t < count; t += 3, v += 3) {
          const P = [0, 1, 2].map((k) => [ox + arr[(v + k) * 3] * q, oy + arr[(v + k) * 3 + 1] * q, oz + arr[(v + k) * 3 + 2] * q]);
          // (up-facing only: a deck's top, not its soffit or sides)
          const ux = P[1][0] - P[0][0], uy = P[1][1] - P[0][1], uz = P[1][2] - P[0][2], wx = P[2][0] - P[0][0], wy = P[2][1] - P[0][1], wz = P[2][2] - P[0][2];
          const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
          if (Math.abs(nz) < 0.8 * Math.hypot(nx, ny, nz)) continue;
          const x0 = Math.min(P[0][0], P[1][0], P[2][0]), x1 = Math.max(P[0][0], P[1][0], P[2][0]);
          const y0 = Math.min(P[0][1], P[1][1], P[2][1]), y1 = Math.max(P[0][1], P[1][1], P[2][1]);
          for (let i = Math.floor(x0 / cell); i <= Math.floor(x1 / cell); i++) for (let j = Math.floor(y0 / cell); j <= Math.floor(y1 / cell); j++) {
            const k = i * 100003 + j;
            if (!grid.has(k)) grid.set(k, []);
            grid.get(k).push(P);
          }
        }
      }
    }
  }
  return {
    size: grid.size,
    topAt(x, y, ref, tol = 4) {
      const zs = this.surfaces(x, y).filter((z) => Math.abs(z - ref) <= tol);
      return zs.length ? Math.max(...zs) : null;
    },
    // the deck over a way spanning at `span`: the lowest model surface from 3 m under it to 15 m over
    // it and above `floor` (a high bridge's deck stood 14 m over the span between the ground at its
    // OSM ends; railings and arches over the deck are higher, piers' tops near the water lower)
    deckAt(x, y, span, floor = -Infinity) {
      const zs = this.surfaces(x, y).filter((z) => z > Math.max(span - 3, floor) && z < span + 15);
      return zs.length ? Math.min(...zs) : null;
    },
    surfaces(x, y) {
      const tris = grid.get(Math.floor(x / cell) * 100003 + Math.floor(y / cell));
      if (!tris) return [];
      const out = [];
      for (const [a, b, c] of tris) {
        const d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
        if (Math.abs(d) < 1e-9) continue;
        const w1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d;
        const w2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d;
        const w3 = 1 - w1 - w2;
        if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
        out.push(w1 * a[2] + w2 * b[2] + w3 * c[2]);
      }
      return out;
    },
  };
}

// Road tunnels and bridges drawn in OSM as several ways (a tube split at its lane changes, a bridge
// at every change of tags): each such way gets `way`, the whole chain it belongs to (joined end to end
// through ways of the same kind and level only, oriented), so its height runs between the real portals
// or abutments (makeGround().way). Per way, the inner ends took the ground there: the hill top over
// the Letenský tunel, the river under a footway on a bridge.
export function chainTunnels(roads) {
  return chainWays(roads, 't') + chainWays(roads, 'b');
}
function chainWays(roads, flag) {
  const tun = roads.filter((r) => r[flag] && r.p?.length > 1), key = (p) => `${p[0]},${p[1]}`, at = new Map();
  for (const r of tun) for (const p of [r.p[0], r.p[r.p.length - 1]]) { const k = key(p); if (!at.has(k)) at.set(k, []); at.get(k).push(r); }
  const done = new Set();
  let n = 0;
  for (const r0 of tun) {
    if (done.has(r0)) continue;
    let line = r0.p.slice();
    const members = [r0];
    done.add(r0);
    // grow at both ends while exactly one other unused tunnel way continues there
    for (let grew = true; grew;) {
      grew = false;
      for (const front of [false, true]) {
        const p = front ? line[0] : line[line.length - 1], next = (at.get(key(p)) || []).filter((r) => !done.has(r));
        if (next.length !== 1) continue;
        const r = next[0], pts = key(r.p[0]) === key(p) ? r.p : r.p.slice().reverse();
        line = front ? [...pts.slice().reverse(), ...line.slice(1)] : [...line, ...pts.slice(1)];
        members.push(r); done.add(r); grew = true;
      }
    }
    // an end is a portal where an ordinary road goes on from it; else the tunnel runs on past the
    // edge of the imported roads (the Letenský tunel's Letná end) and that end is no portal
    // (an ordinary road within 4.5 m: the importer does not always keep the shared node)
    const roadEnd = (p) => roads.some((r) => !r[flag] && r.p?.length > 1 && r.p.some((q) => Math.abs(q[0] - p[0]) < 4.5 && Math.abs(q[1] - p[1]) < 4.5 && Math.hypot(q[0] - p[0], q[1] - p[1]) < 4.5));
    line.open = [roadEnd(line[0]), roadEnd(line[line.length - 1])];
    for (const r of members) r.way = line;
    n++;
  }
  return n;
}

export class Profile {
  // The track profile is the top of rail (src/heights.js), built offline (#480, #276 step 2): the line data's
  // `heights` every 2 m (tools/line_heights.py: every sample has one, the surface plus the style's lift where no
  // source does), the spans the route runs on a bridge, those with a deck (`spans`, `realDecks`) and the roads under it
  // (`underpasses`, tools/line_structures.py). `lift(s)`: the rails' height over the bed (`lift`, tools/track_styles.py).
  // Until #480 the page computed a surface profile here at every load (166-505 ms) and threw it away wherever the build
  // had a height, over 99 % of the route.
  constructor(route, data, lift = () => 0, dtm = null, terrain = null) {
    const step = (this.step = 2);
    this.lift = lift;
    const n = (this.n = Math.ceil(route.length / step) + 1);
    Object.assign(this, { route, terrain, dtm, tunnels: data.tunnels || [] });
    const h = data.heights;
    const z = resampleHeights(h.path, h.step, n, step);
    if (z.some(Number.isNaN)) throw new Error(`line ${data.line} data has samples without a height: built before #480, rebuild it (tools/rebuild.py)`);
    const ranges = data.heightSource?.path || [];
    this.source = Array.from(z, (_, i) => ranges.find((r) => i * step >= r[0] && i * step <= r[1])?.[2] ?? 'data');
    this.bridges = data.spans;
    this.realDecks = data.realDecks;
    this.clearances = data.underpasses;
    this.backOff = null;
    // the opposite track across the street (its offset, left > 0, and height at each sample, from the build): the
    // cross-section between the two tracks is linear, level beyond them (heightAt). Where either track has no
    // height the cross-section is level, and it fades in and out over FADE m.
    if (h.backOff) {
      const off = resampleHeights(h.backOff, h.step, n, step), zb = resampleHeights(h.backZ, h.step, n, step);
      const ok = (i) => !Number.isNaN(off[i]) && !Number.isNaN(zb[i]);
      const FADE = 10, dz = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        if (!ok(i)) continue;
        let j = i;
        while (j + 1 < n && ok(j + 1)) j++;
        for (let k = i; k <= j; k++) dz[k] = (zb[k] - z[k]) * Math.min(1, (k - i) * step / FADE, (j - k) * step / FADE);
        i = j;
      }
      this.backOff = off;
      this.backDz = dz;
    }
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
  // top of rail `lateral` m across from our track (left > 0): ours, the opposite track's where the build gave its
  // cross-section, linear between the two and level beyond (#197)
  heightAt(s, lateral = 0) {
    const z = this._interp(this.z, s);
    if (!this.backOff || !lateral) return z;
    const o = this.backOff[Math.max(0, Math.min(this.n - 1, Math.round(s / this.step)))];
    if (!(Math.abs(o) > 0.5)) return z;
    return z + this._interp(this.backDz, s) * Math.max(0, Math.min(1, lateral / o));
  }
  grade(s) { return this._interp(this.grades, s); }

  onBridge(s) {
    return this.bridges.some(([a, b]) => s > a - 4 && s < b + 4);
  }
  // well inside a bridge span (more than 8 m from its ends) and at least 3 m above the ground under
  // it: what lies here in 2D is on the road underneath (a junction at a bridge end is a real one for
  // the tram, and so is a road crossing a culvert "bridge" 1.2 m below the rails, s 5816 on line 17)
  overBridge(s) {
    if (!this.bridges.some(([a, b]) => s > a + 8 && s < b - 8)) return false;
    const p = this.route.at(s), zg = (this.dtm ? this.dtm.heightAt(p.x, p.y) : null) ?? this.terrain.height(p.x, p.y);
    return this.height(s) - zg > 3;
  }
}

// Carve the track corridor into the terrain grid. Within BENCH m of the track the ground is
// the track level. Where the hillside rises more than WALL_MIN m above the track, a retaining
// wall stands at BENCH m with a flat cap behind it; the grid vertices behind the wall are
// lowered so no coarse terrain triangle can cut through the track. Elsewhere the ground
// blends back to the natural terrain (embankment / cutting slopes). Returns wall runs.
const BENCH = 7, BLEND = 8, WALL_MIN = 1.5, WALL_REACH = 22;
// `dtm`: where the surveyed streets describe the ground beside the track, the survey decides and no
// retaining wall is invented (the 10 m lidar grid rising beside a street is not a wall)
export function carveCorridor(T, route, profile, dtm = null) {
  // the ground before carving, every grid (the fine blocks where there are some: walls and rock
  // tunnels are judged on the 2 m lidar there)
  const grids = T.grids ? T.grids() : [T];
  const origs = grids.map((g) => new Grid(g.x0, g.y0, g.dx, g.dy, g.nx, g.ny, g.h.slice()));
  const origAt = (x, y) => {
    for (let k = 1; k < origs.length; k++) if (origs[k].contains(x, y)) return origs[k].height(x, y);
    return origs[0].height(x, y);
  };
  // Tunnels of our route through rock (OSM tunnel, the lidar ground more than 8 m over the track on
  // average: the Vyšehrad tunnel; not a covered stretch under a station or a bridge): nothing is
  // carved there, the hill stays whole over the track and world.js draws the vault and the portals
  const rock = (profile.tunnels || []).filter(([a, b]) => {
    let acc = 0, n = 0;
    for (let s = a; s <= b; s += 4) { const q = route.at(s); acc += origAt(q.x, q.y) - profile.height(s); n++; }
    return n && acc / n > 8;
  });
  const inRock = (s) => rock.some(([a, b]) => s > a - 1 && s < b + 1);
  // where along each side the hillside needs a retaining wall, and how tall
  const WSTEP = 3, nw = Math.ceil(route.length / WSTEP) + 1;
  const wallTop = { 1: new Float32Array(nw).fill(NaN), '-1': new Float32Array(nw).fill(NaN) };
  for (let i = 0; i < nw; i++) {
    const s = i * WSTEP;
    if (profile.onBridge(s) || inRock(s)) continue;
    const zp = profile.height(s) - profile.lift(s); // (the bed: src/heights.js)
    for (const side of [1, -1]) {
      let top = -Infinity;
      for (const lat of [BENCH + 1, BENCH + 4, BENCH + 8]) {
        const o = route.offset(s, side * lat);
        top = Math.max(top, origAt(o.x, o.y));
      }
      const foot = route.offset(s, side * (BENCH + 0.5)), at = route.offset(s, side * BENCH);
      if (dtm && (dtm.surfaceAt(foot.x, foot.y) || dtm.surfaceAt(at.x, at.y))) continue;
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
  // carve each grid: every vertex within reach takes its nearest route sample's bench / wall / blend
  const R = WALL_REACH + 3;
  const samples = [];
  for (let s = 0; s <= route.length; s += 2) { const q = route.at(s), h = route.heading(s, 3); samples.push({ s, x: q.x, y: q.y, hx: h.hx, hy: h.hy }); }
  grids.forEach((g, gk) => {
    const { nx, ny } = g, N = nx * ny, orig = origs[gk].h;
    const bestD = new Float32Array(N).fill(Infinity), bestS = new Float32Array(N), bestSide = new Int8Array(N);
    const gx0 = Math.min(g.x0, g.x0 + (nx - 1) * g.dx), gx1 = Math.max(g.x0, g.x0 + (nx - 1) * g.dx);
    const gy0 = Math.min(g.y0, g.y0 + (ny - 1) * g.dy), gy1 = Math.max(g.y0, g.y0 + (ny - 1) * g.dy);
    for (const p of samples) {
      if (p.x < gx0 - R || p.x > gx1 + R || p.y < gy0 - R || p.y > gy1 + R) continue;
      const s = p.s, h = p;
      const i0 = Math.max(0, Math.floor((p.x - R - g.x0) / g.dx)), i1 = Math.min(nx - 1, Math.ceil((p.x + R - g.x0) / g.dx));
      const j0 = Math.max(0, Math.floor((p.y + R - g.y0) / g.dy)), j1 = Math.min(ny - 1, Math.ceil((p.y - R - g.y0) / g.dy));
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
        const x = g.x0 + i * g.dx, y = g.y0 + j * g.dy;
        const d = Math.hypot(x - p.x, y - p.y);
        const k = j * nx + i;
        if (d < bestD[k]) {
          bestD[k] = d;
          bestS[k] = s;
          bestSide[k] = h.hx * (y - p.y) - h.hy * (x - p.x) > 0 ? 1 : -1; // +1 = left
        }
      }
    }
    for (let k = 0; k < N; k++) {
      const d = bestD[k];
      if (d > R) continue;
      const s = bestS[k];
      if (profile.onBridge(s) || inRock(s)) continue;
      const zp = profile.height(s) - profile.lift(s); // (the bed)
      const wall = !isNaN(wallTop[bestSide[k]][Math.round(s / WSTEP)]);
      if (d <= BENCH || (wall && d <= WALL_REACH)) g.h[k] = zp - 0.05;
      else if (d <= BENCH + BLEND) g.h[k] = zp + (orig[k] - zp) * ((d - BENCH) / BLEND);
    }
  });
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
  return { runs, bench: BENCH, reach: WALL_REACH, rock };
}

// Combined ground function used by all scenery: near the route (and on its bridges)
// the track profile wins, so rails, platforms and poles sit exactly on the track.
// Surveyed street surfaces from the Prague DTM (tools/dtm.py): areas with a height on every
// vertex. Triangulated once; `heightAt(x, y)` returns the ground-level (level 0) surface height
// where an area covers the point (roads and tram areas win over the rest), else null.
// `covered(x, y)` tells whether the DTM describes the street there at all.
// drawn DTM surfaces stand this much above their surveyed height (no z-fighting between classes)
import { STREET_BELOW, ROAD_BELOW, resampleHeights } from './heights.js';

export const DTM_LIFT = { road: 0.03, parking: 0.03, cycle: 0.035, tram: 0.035, sidewalk: 0.05, island: 0.05, platform: 0.06, paved: 0.04, stairs: 0.05, green: 0.02, rail: 0.02, water: 0.01 };
export const FLUSH = new Set(['road', 'tram', 'parking', 'paved']); // surfaces the tracks are laid in
export const STREET = new Set(['road', 'tram', 'parking', 'paved', 'sidewalk', 'island', 'platform', 'cycle']);
// level 1+ surfaces that carry traffic: what cars and walkers on a bridge stand on
const DECK = new Set(['deck', 'road', 'tram', 'paved', 'sidewalk', 'cycle', 'island', 'parking']);
const DRAPE_EDGE = 5; // m: the longest edge of a draped area's triangles (its inside on the lidar: green p95 0.14-0.18 m against 0.38-0.44 at 10 m, #444)
const SURFACE_RANK = { tram: 9, road: 8, island: 7, platform: 7, sidewalk: 6, parking: 5, cycle: 5, paved: 4, stairs: 3, green: 2, water: 1 };
// (a railway yard on the lidar ground, `g`, is ground; one standing off it keeps its sheet and stays out)
const groundArea = (a) => a.l === 0 && a.c !== 'wall' && a.c !== 'roof' && a.c !== 'deck' && (a.c !== 'rail' || a.g);
// Lawson's edge flips on a triangulation of a polygon (earcut's, from THREE.ShapeUtils): each inner edge whose
// opposite corner lies in the other triangle's circumcircle is flipped until none does, which is the constrained
// Delaunay triangulation of the same points (#276's T2), the polygon's own edges kept (an edge of one triangle only is
// never flipped). Earcut clips its ears along a strip's sides and joins points far apart: an 800 m tram area on
// Krejcárek's ramp (line 37) had triangles along its length whose linear heights stood up to 6 m over the rails between
// outline points within 0.3 m of them (#444). pts: [[x, y, ...]]; tris: [[i, j, k]], changed in place and returned.
export function delaunayFlips(pts, tris) {
  const n = pts.length, key = (a, b) => (a < b ? a * n + b : b * n + a);
  const edges = new Map(); // edge key -> the triangles that have it
  const add = (t, a, b) => { const k = key(a, b), e = edges.get(k); if (e) e.push(t); else edges.set(k, [t]); };
  tris.forEach((t, i) => { add(i, t[0], t[1]); add(i, t[1], t[2]); add(i, t[2], t[0]); });
  const orient = (a, b, c) => (pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0]);
  // d strictly inside the circumcircle of (a, b, c), whichever way round (a, b, c) is
  const inCircle = (a, b, c, d) => {
    const ax = pts[a][0] - pts[d][0], ay = pts[a][1] - pts[d][1], bx = pts[b][0] - pts[d][0], by = pts[b][1] - pts[d][1];
    const cx = pts[c][0] - pts[d][0], cy = pts[c][1] - pts[d][1];
    const det = (ax * ax + ay * ay) * (bx * cy - cx * by) - (bx * bx + by * by) * (ax * cy - cx * ay) + (cx * cx + cy * cy) * (ax * by - bx * ay);
    const o = orient(a, b, c);
    return o > 0 ? det > 1e-9 : o < 0 ? det < -1e-9 : true; // (a sliver of no area: any d beside it)
  };
  const stack = [];
  for (const [k, e] of edges) if (e.length === 2) stack.push(k);
  const swap = (k, from, to) => { const e = edges.get(k); e[e.indexOf(from)] = to; };
  let flips = 0;
  const cap = 30 * tris.length + 100; // (Lawson's flips end; the cap guards against rounding)
  while (stack.length && flips < cap) {
    const k = stack.pop(), e = edges.get(k);
    if (!e || e.length !== 2) continue;
    const a = Math.floor(k / n), b = k % n, [t1, t2] = e;
    const c = tris[t1].find((v) => v !== a && v !== b), d = tris[t2].find((v) => v !== a && v !== b);
    if (c === undefined || d === undefined || c === d) continue;
    if (!inCircle(a, b, c, d)) continue;
    // (only across a convex pair: a and b on either side of c-d)
    if (orient(c, d, a) * orient(c, d, b) >= 0) continue;
    const sign = Math.sign(orient(...tris[t1])) || Math.sign(orient(...tris[t2])) || 1;
    const make = (p, q, r) => (Math.sign(orient(p, q, r)) === sign ? [p, q, r] : [p, r, q]);
    tris[t1] = make(c, a, d);
    tris[t2] = make(d, b, c);
    edges.delete(k);
    swap(key(b, c), t1, t2);
    swap(key(a, d), t2, t1);
    edges.set(key(c, d), [t1, t2]);
    for (const kk of [key(a, c), key(b, c), key(a, d), key(b, d)]) if (edges.get(kk)?.length === 2) stack.push(kk);
    flips++;
  }
  return tris;
}
export class DtmSurface {
  constructor(dtm, terrain, THREE) {
    this.terrain = terrain;
    this.grid = new TriIndex();
    this.deckGrid = new TriIndex(); // level 1: bridge decks and the streets on them
    this.areas = [];
    // underground areas (a road tunnel's floor: the Vyšehrad tunnel) are not drawn, but their outlines
    // tell the tunnel's width and where its road and footway are
    this.under = dtm.areas.filter((a) => a.l < 0 && a.r?.length > 2).map((a) => ({ c: a.c, ring: a.r }));
    for (const [sourceId, a] of dtm.areas.entries()) {
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
      // ground-level outlines cut into equal pieces of at most 4 m: neighbours share an edge's ends, so
      // they get the same points on it, and the 5 m split below never adds a point on one side only
      // (one area's midpoint, moved to the track profile by flushDtm, opened a seam to the other:
      // line 17's street seams over 3 cm 415 with the street model's shared 4 m grid, 675 without, #21)
      // (each piece keeps its edge's kerb flag, tools/kerbs.py)
      const cut = (ring, k) => {
        if (a.l !== 0) return [ring, k];
        const out = [], ko = [];
        ring.forEach((p, i) => {
          const q = ring[(i + 1) % ring.length], n = Math.ceil(Math.hypot(q[0] - p[0], q[1] - p[1]) / 4);
          for (let j = 0; j < Math.max(1, n); j++) { out.push(j ? [p[0] + (q[0] - p[0]) * j / n, p[1] + (q[1] - p[1]) * j / n, p[2] + (q[2] - p[2]) * j / n] : p); ko.push(k?.[i] ?? 0); }
        });
        return [out, k ? ko : null];
      };
      const [outer, k0] = cut(fill(a.r), a.k?.[0]), hk = (a.h || []).map((h, j) => cut(fill(h), a.k?.[j + 1]));
      const holes = hk.map((h) => h[0]), kerbs = a.k ? [k0, ...hk.map((h) => h[1])] : null;
      if (outer.length < 3) continue;
      // a river or pond is level: its outline takes the heights of both banks (the embankment's top)
      if (a.c === 'water') {
        const zs = outer.map((p) => p[2]).sort((u, v) => u - v), zw = zs[Math.floor(zs.length * 0.1)];
        for (const p of [...outer, ...holes.flat()]) p[2] = zw;
      }
      const v2 = (r) => r.map((p) => new THREE.Vector2(p[0], p[1]));
      let tri;
      try { tri = THREE.ShapeUtils.triangulateShape(v2(outer), holes.map(v2)); } catch { continue; }
      const all = [...outer, ...holes.flat()];
      // on the ground, the constrained Delaunay triangles over the same points (#276's T2): earcut's slivers along a
      // long strip joined points far apart, and their linear heights left a ridge up to 6 m over the rails on
      // Krejcárek's ramp (line 37 s 2566-2746: the tram area's outline within 0.3 m of the rails, #444)
      if (a.l === 0) delaunayFlips(all, tri);
      const area = { c: a.c, l: a.l, ring: outer, holes, mesh: [], kerbs, sourceId, t: a.t, g: a.g };
      // on a structure: a long deck outline (the Modřany estakáda's track bed runs from the foot of
      // one ramp to the other) must not be spanned by long triangles; inner points take the height
      // of the outline's own corners nearby
      const ringZ = a.l >= 1 ? (x, y) => {
        let sw = 0, sz = 0;
        for (const v of all) { const d2 = (v[0] - x) ** 2 + (v[1] - y) ** 2, w = 1 / (d2 * d2 + 1e-3); sw += w; sz += w * v[2]; }
        return sz / sw;
      } : null;
      const rank = SURFACE_RANK[a.c] || 1;
      const ground = groundArea(a); // (nobody stands on a wall)
      for (const [i, j, k] of tri) {
        const p = all[i], q = all[j], r = all[k];
        // render mesh: split to <= 5 m edges, linear between the surveyed vertices (the survey's own
        // meaning; averaging the surveyed points inside roads doubled their bumps, #21)
        const n0 = area.mesh.length;
        // a railway yard, a lawn or a paved yard has surveyed heights only on its outline: lying on the lidar
        // ground (`g`, tools/zps_inside.py), it takes the lidar inside (a flat sheet between the edges ran up
        // to 8.7 m under the Letná slope; Krejcárek's yard crossed the terrain in wedges, #444); the outline,
        // cut to 4 m above, is never split and keeps the survey's heights
        if (a.l === 0 && a.g) this._split(p, q, r, (x, y) => terrain.height(x, y), area.mesh, 0, DRAPE_EDGE);
        else if (a.l === 0 && STREET.has(a.c)) this._split(p, q, r, false, area.mesh);
        else if (a.l >= 1 && a.c !== 'roof') this._split(p, q, r, ringZ, area.mesh);
        else area.mesh.push([p, q, r]);
        // the height lookup uses exactly the drawn triangles, so cars stand on what is drawn
        if (ground) for (let m = n0; m < area.mesh.length; m++) this.grid.add(area.mesh[m], rank, a.c);
        // (decks by reference: world.js lays the decks of our bridges to the track profile afterwards)
        if (a.l >= 1 && DECK.has(a.c)) for (let m = n0; m < area.mesh.length; m++) this.deckGrid.add(area.mesh[m], a.l, a.c);
      }
      this.areas.push(area);
    }
    this.grid.freeze();
    this.deckGrid.freeze();
  }
  // Crossings may gain vertices after track heights are known; lookups must use the drawn mesh.
  reindexGround() {
    const grid = new TriIndex(), decks = new TriIndex();
    for (const a of this.areas) for (const tri of a.mesh) {
      if (groundArea(a)) grid.add(tri, SURFACE_RANK[a.c] || 1, a.c);
      if (a.l >= 1 && DECK.has(a.c)) decks.add(tri, a.l, a.c);
    }
    grid.freeze(); decks.freeze();
    if (this.sealed) { grid.seal(); decks.seal(); }
    this.grid = grid; this.deckGrid = decks;
  }

  // The load is done and the survey's vertices final (flushDtm, the deck moves and fitDtmToMouths change
  // their heights after the index is built, and lookups read them live until then): the triangles' terms
  // copied into typed arrays for the lookups of the simulation (#245: _hitTri was ~22 % of a seeded run).
  seal() {
    if (this.sealed) return;
    this.grid.seal(); this.deckGrid.seal();
    this.sealed = true;
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
  _hitTri(x, y, ref = null) {
    const ix = this.grid, k = ix.at(x, y);
    if (k < 0) return null;
    // overlapping ground-level areas: the one closest to the lidar ground (or to `ref`), then by rank
    const g = ref ?? this.terrain.height(x, y);
    let best = -1, bestZ = 0, bestScore = Infinity;
    const f = ix.flat;
    if (f) {
      // (sealed: the same terms from typed arrays, the same arithmetic in the same order; #245)
      for (let n = ix.start[k], end = ix.start[k + 1]; n < end; n++) {
        const id = ix.ids[n], o = id * 10, d = f[o + 9];
        if (Math.abs(d) < 1e-9) continue;
        const dx = x - f[o + 4], dy = y - f[o + 5];
        const w1 = (f[o] * dx + f[o + 1] * dy) / d;
        const w2 = (f[o + 2] * dx + f[o + 3] * dy) / d;
        const w3 = 1 - w1 - w2;
        if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
        const z = w1 * f[o + 6] + w2 * f[o + 7] + w3 * f[o + 8];
        const score = Math.abs(z - g) - ix.val[id] * 0.05;
        if (score < bestScore) { best = id; bestZ = z; bestScore = score; }
      }
      return best < 0 ? null : { z: bestZ, c: ix.classOf(best) };
    }
    for (let n = ix.start[k], end = ix.start[k + 1]; n < end; n++) {
      const id = ix.ids[n], t = ix.tris[id], p = t[0], q = t[1], r = t[2];
      const d = (q[1] - r[1]) * (p[0] - r[0]) + (r[0] - q[0]) * (p[1] - r[1]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((q[1] - r[1]) * (x - r[0]) + (r[0] - q[0]) * (y - r[1])) / d;
      const w2 = ((r[1] - p[1]) * (x - r[0]) + (p[0] - r[0]) * (y - r[1])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * p[2] + w2 * q[2] + w3 * r[2];
      const score = Math.abs(z - g) - ix.val[id] * 0.05;
      if (score < bestScore) { best = id; bestZ = z; bestScore = score; }
    }
    return best < 0 ? null : { z: bestZ, c: ix.classOf(best) };
  }
  // longest-edge bisection down to 5 m edges (thin carriageway slivers stay cheap)
  _split(p, q, r, ground, out, depth = 0, maxEdge = 5) {
    const l0 = Math.hypot(p[0] - q[0], p[1] - q[1]), l1 = Math.hypot(q[0] - r[0], q[1] - r[1]), l2 = Math.hypot(r[0] - p[0], r[1] - p[1]);
    const e = Math.max(l0, l1, l2);
    if (e <= maxEdge || depth >= 16) { out.push([p, q, r]); return; }
    if (l1 === e) [p, q, r] = [q, r, p];
    else if (l2 === e) [p, q, r] = [r, p, q];
    // now p-q is the longest edge
    const x = (p[0] + q[0]) / 2, y = (p[1] + q[1]) / 2;
    const zl = (p[2] + q[2]) / 2;
    // (ground: a function = its height, false = linear)
    const m = [x, y, (typeof ground === 'function' ? ground(x, y) : null) ?? zl];
    this._split(p, m, r, ground, out, depth + 1, maxEdge);
    this._split(m, q, r, ground, out, depth + 1, maxEdge);
  }
  // top of a surveyed surface on a structure (bridge deck, level 1+) over (x, y), or null: the one
  // nearest to `ref` (within `tol`) when given, else the highest level-1 surface (then any level)
  deckAt(x, y, ref = null, tol = Infinity, cls = null) {
    const ix = this.deckGrid, k = ix.at(x, y);
    if (k < 0) return null;
    let best = null, score = Infinity;
    const f = ix.flat;
    if (f) {
      // (sealed: as in _hitTri)
      for (let n = ix.start[k], end = ix.start[k + 1]; n < end; n++) {
        const id = ix.ids[n], o = id * 10, l = ix.val[id];
        if (cls && ix.classOf(id) !== cls) continue;
        const d = f[o + 9];
        if (Math.abs(d) < 1e-9) continue;
        const dx = x - f[o + 4], dy = y - f[o + 5];
        const w1 = (f[o] * dx + f[o + 1] * dy) / d;
        const w2 = (f[o + 2] * dx + f[o + 3] * dy) / d;
        const w3 = 1 - w1 - w2;
        if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
        const z = w1 * f[o + 6] + w2 * f[o + 7] + w3 * f[o + 8];
        const sc = ref !== null ? Math.abs(z - ref) : (l === 1 ? 0 : 1e4) - z;
        if (sc < score && (ref === null || sc <= tol)) { best = z; score = sc; }
      }
      return best;
    }
    for (let n = ix.start[k], end = ix.start[k + 1]; n < end; n++) {
      const id = ix.ids[n], t = ix.tris[id], p = t[0], q = t[1], r = t[2], l = ix.val[id];
      if (cls && ix.classOf(id) !== cls) continue;
      const d = (q[1] - r[1]) * (p[0] - r[0]) + (r[0] - q[0]) * (p[1] - r[1]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((q[1] - r[1]) * (x - r[0]) + (r[0] - q[0]) * (y - r[1])) / d;
      const w2 = ((r[1] - p[1]) * (x - r[0]) + (p[0] - r[0]) * (y - r[1])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * p[2] + w2 * q[2] + w3 * r[2];
      const sc = ref !== null ? Math.abs(z - ref) : (l === 1 ? 0 : 1e4) - z;
      if (sc < score && (ref === null || sc <= tol)) { best = z; score = sc; }
    }
    return best;
  }
  heightAt(x, y) {
    const t = this._hitTri(x, y);
    return t ? t.z : null;
  }
  // (ref: the surface nearest this height, where streets of two heights overlap in plan)
  surfaceAt(x, y, ref = null) { return this._hitTri(x, y, ref); }
  // class of the underground (level < 0) area at (x, y), or null
  classUnder(x, y) {
    for (const a of this.under) {
      let inside = false;
      const r = a.ring;
      for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
        if ((r[i][1] > y) !== (r[j][1] > y) && x < ((r[j][0] - r[i][0]) * (y - r[i][1])) / (r[j][1] - r[i][1]) + r[i][0]) inside = !inside;
      }
      if (inside) return a.c;
    }
    return null;
  }
  covered(x, y) { return this.grid.covered(x, y); }
}

// Triangles of the surveyed areas by 3 m cell, for the height and deck lookups. The triangles are
// the areas' own mesh triangles by reference (world.js moves their heights afterwards: flush with
// the tracks, bridge decks, tunnel mouths; the lookups see that), numbered in one list, each with a
// value (rank or level) and a class. The cells' triangle numbers lie in one Int32Array (`ids`), cell
// k's from start[k] to start[k + 1]. (It was 10 m cells, each entry a new [p, q, r, value, class]
// array: 4.8 M of them on line 17, ~250 MB, and ~100 triangles tested per lookup; now ~20.)
// `covered` keeps the 10 m cells: callers ask whether the survey is about at all.
const TRI_CELL = 3, COVER_CELL = 10;
class TriIndex {
  constructor() {
    this.tris = [];
    this.vals = [];
    this.clsIds = [];
    this.classes = [];
    this.classId = new Map();
    this.box = []; // per triangle its cells' range ix0, ix1, iy0, iy1, while building
    this.cover = new Set(); // 10 m keys with a triangle
  }

  add(t, val, c) {
    const id = this.tris.length;
    this.tris.push(t);
    this.vals.push(val);
    if (!this.classId.has(c)) { this.classId.set(c, this.classes.length); this.classes.push(c); }
    this.clsIds.push(this.classId.get(c));
    const ax = t[0][0], ay = t[0][1], bx = t[1][0], by = t[1][1], cx = t[2][0], cy = t[2][1];
    const x0 = Math.min(ax, bx, cx), x1 = Math.max(ax, bx, cx), y0 = Math.min(ay, by, cy), y1 = Math.max(ay, by, cy);
    this.box.push(Math.floor(x0 / TRI_CELL), Math.floor(x1 / TRI_CELL), Math.floor(y0 / TRI_CELL), Math.floor(y1 / TRI_CELL));
    for (let ix = Math.floor(x0 / COVER_CELL); ix <= Math.floor(x1 / COVER_CELL); ix++) for (let iy = Math.floor(y0 / COVER_CELL); iy <= Math.floor(y1 / COVER_CELL); iy++) this.cover.add(ix * 100003 + iy);
  }

  // after the last add: the compact form. The cells' triangles are counted and placed on a grid over all
  // the triangles' cells (typed arrays, dropped after), each cell's in the order added, as a list per cell
  // did (a Map of growing lists: ~1 s per index on line 17, built twice at load, #244)
  freeze() {
    const b = this.box, nt = b.length / 4;
    let gx0 = Infinity, gx1 = -Infinity, gy0 = Infinity, gy1 = -Infinity;
    for (let i = 0; i < b.length; i += 4) {
      if (b[i] < gx0) gx0 = b[i]; if (b[i + 1] > gx1) gx1 = b[i + 1];
      if (b[i + 2] < gy0) gy0 = b[i + 2]; if (b[i + 3] > gy1) gy1 = b[i + 3];
    }
    const W = nt ? gx1 - gx0 + 1 : 0, H = nt ? gy1 - gy0 + 1 : 0, at = new Int32Array(W * H + 1);
    let n = 0;
    for (let i = 0; i < b.length; i += 4) {
      for (let ix = b[i]; ix <= b[i + 1]; ix++) for (let iy = b[i + 2]; iy <= b[i + 3]; iy++) at[(ix - gx0) * H + iy - gy0]++;
      n += (b[i + 1] - b[i] + 1) * (b[i + 3] - b[i + 2] + 1);
    }
    // (cell numbers by grid order; at[] becomes each cell's fill position)
    this.cells = new Map(); // key -> cell number
    const starts = [];
    let o = 0;
    for (let g = 0; g < W * H; g++) {
      const c = at[g];
      if (!c) continue;
      this.cells.set((Math.floor(g / H) + gx0) * 100003 + (g % H) + gy0, starts.length);
      starts.push(o);
      at[g] = o;
      o += c;
    }
    starts.push(o);
    this.start = Int32Array.from(starts);
    this.ids = new Int32Array(n);
    for (let i = 0, id = 0; id < nt; i += 4, id++) {
      for (let ix = b[i]; ix <= b[i + 1]; ix++) for (let iy = b[i + 2]; iy <= b[i + 3]; iy++) this.ids[at[(ix - gx0) * H + iy - gy0]++] = id;
    }
    this.val = Float32Array.from(this.vals);
    this.cls = Uint8Array.from(this.clsIds);
    this.box = this.vals = this.clsIds = null;
  }

  // per triangle: q1-r1, r0-q0, r1-p1, p0-r0, r0, r1, pz, qz, rz and the determinant, as the lookups compute them
  seal() {
    const n = this.tris.length, f = new Float64Array(n * 10);
    for (let i = 0; i < n; i++) {
      const [p, q, r] = this.tris[i], o = i * 10;
      f[o] = q[1] - r[1]; f[o + 1] = r[0] - q[0]; f[o + 2] = r[1] - p[1]; f[o + 3] = p[0] - r[0];
      f[o + 4] = r[0]; f[o + 5] = r[1]; f[o + 6] = p[2]; f[o + 7] = q[2]; f[o + 8] = r[2];
      f[o + 9] = (q[1] - r[1]) * (p[0] - r[0]) + (r[0] - q[0]) * (p[1] - r[1]);
    }
    this.flat = f;
  }

  // the cell number at (x, y), or -1
  at(x, y) { return this.cells.get(Math.floor(x / TRI_CELL) * 100003 + Math.floor(y / TRI_CELL)) ?? -1; }

  covered(x, y) { return this.cover.has(Math.floor(x / COVER_CELL) * 100003 + Math.floor(y / COVER_CELL)); }

  classOf(id) { return this.classes[this.cls[id]]; }
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
    return { s, d: Math.hypot(x - q.x, y - q.y), l: (y - q.y) * q.hx - (x - q.x) * q.hy }; // (l: left > 0)
  };
  return {
    terrain,
    profile,
    route,
    dtm,
    // ground height at an arbitrary point; `deck` marks things that are part of a bridge of our
    // route (on it: the deck; without the flag: the ground under the bridge, where the roads below are)
    // (next to the track: the ground under the OSM road ribbons, which are drawn 0.12 m over it, so the
    // road meets the rail heads at the track's surface level: src/heights.js)
    at(x, y, deck = false) {
      const n = near(x, y), under = (n) => profile.heightAt(n.s, n.l) - profile.lift(n.s) - ROAD_BELOW;
      if (n && profile.onBridge(n.s)) {
        if (deck && n.d < 22) return under(n);
        return (dtm ? dtm.heightAt(x, y) : null) ?? terrain.height(x, y);
      }
      if (n && n.d < 4) return under(n);
      // surveyed street surface (DTM) where it exists
      const zd = dtm ? dtm.heightAt(x, y) : null;
      if (zd !== null) return zd;
      if (n && n.d < 9) {
        const zt = under(n);
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
      if (!n || n.d > 12 || profile.onBridge(n.s)) return z; // (under our bridge: the road below)
      const q = route.at(n.s), l = (y - q.y) * q.hx - (x - q.x) * q.hy; // (left > 0: the opposite track's side, #197)
      const zt = profile.heightAt(n.s, l) - profile.lift(n.s) - STREET_BELOW; // the surface the track lies in
      if (d >= 3 ? Math.abs(z - zt) > 2.5 : z - zt > 4.5) return z; // a street above or below the tracks' level (in the track corridor: only a structure well above)
      const k = Math.max(0, Math.min(1, (d - 3) / 3));
      return zt + (z - zt) * k * k * (3 - 2 * k);
    },
    // top of the street surface as drawn at ground level, where cars and walkers stand: the DTM area
    // (flush with the tracks, lifted per class), else an OSM road ribbon (0.12 above the ground).
    // Under a bridge this is the road below it; on a bridge see deckSurface / way.
    surface(x, y) {
      if (dtm) {
        const t = dtm.surfaceAt(x, y);
        if (t) return t.z + (DTM_LIFT[t.c] ?? 0.03); // flush with the tracks already (world.js flushDtm)
      }
      return this.at(x, y) + 0.12;
    },
    // top of a bridge surface as drawn (a surveyed deck nearest to `ref`, else the deck of our
    // route's bridge), or null
    deckSurface(x, y, ref = null) {
      const z = dtm ? dtm.deckAt(x, y, ref, ref === null ? Infinity : 4) : null;
      if (z !== null) return z + 0.02;
      const n = near(x, y);
      return n && n.d < 22 && profile.onBridge(n.s) ? profile.heightAt(n.s, n.l) - profile.lift(n.s) - 0.012 : null;
    },
    // height function of an OSM way (its ribbon is drawn 0.12 above): ground level, or on a bridge
    // the deck it lies on, else a straight span between the ground at its two ends
    way(line, isBridge, isTunnel = false) {
      if (isTunnel) {
        // a road tunnel (line: the whole chain of its ways, chainTunnels): graded along its length
        // between its two portals (below the hill in between). A portal's height is the approach
        // road's: the lowest ground within 12 m out of the mouth (the lidar at the mouth itself is
        // often the hill face above it; per way, the inner ends took the hill top: Letenský tunel)
        const acc = [0];
        for (let i = 1; i < line.length; i++) acc.push(acc[i - 1] + Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]));
        const L = acc[acc.length - 1] || 1;
        const portal = (p, q) => {
          const dx = p[0] - q[0], dy = p[1] - q[1], l = Math.hypot(dx, dy) || 1;
          let z = Infinity;
          for (let d = 0; d <= 12; d += 3) z = Math.min(z, this.at(p[0] + (dx / l) * d, p[1] + (dy / l) * d));
          return z;
        };
        // (an end cut off by the edge of the imported roads (line.open false) is deep under the hill)
        const deep = (p) => this.at(p[0], p[1]) - 8;
        const [oa, ob] = line.open || [true, true];
        const ha = oa ? portal(line[0], line[1]) : deep(line[0]), hb = ob ? portal(line[line.length - 1], line[line.length - 2]) : deep(line[line.length - 1]);
        return (x, y) => {
          let best = Infinity, s = 0;
          for (let i = 1; i < line.length; i++) {
            const a = line[i - 1], b = line[i], ex = b[0] - a[0], ey = b[1] - a[1], l2 = ex * ex + ey * ey || 1e-9;
            const t = Math.max(0, Math.min(1, ((x - a[0]) * ex + (y - a[1]) * ey) / l2));
            const d = (a[0] + ex * t - x) ** 2 + (a[1] + ey * t - y) ** 2;
            if (d < best) { best = d; s = acc[i - 1] + (acc[i] - acc[i - 1]) * t; }
          }
          return ha + ((hb - ha) * s) / L;
        };
      }
      if (!isBridge) return (x, y) => this.at(x, y);
      // a bridge (line: the whole chain of its ways): a span along its length between the ground at
      // its abutments, and on it the surveyed deck near that height, else the Mosty 3D model's top
      // (footways on bridge pieces sagged towards the river: the span of the piece ended mid-river)
      const acc = [0];
      for (let i = 1; i < line.length; i++) acc.push(acc[i - 1] + Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]));
      const L = acc[acc.length - 1] || 1, a = line[0], b = line[line.length - 1];
      // (an end cut off by the edge of the imported roads (line.open false, mid-river) takes the other's)
      const [oa, ob] = line.open || [true, true];
      let ha = this.at(a[0], a[1]), hb = this.at(b[0], b[1]);
      if (!oa && ob) ha = hb;
      else if (oa && !ob) hb = ha;
      else if (!oa && !ob) ha = hb = Math.max(ha, hb); // (both: one of them is likely mid-river)
      const model = this.model;
      return (x, y) => {
        let best = Infinity, s = 0;
        for (let i = 1; i < line.length; i++) {
          const p = line[i - 1], q = line[i], ex = q[0] - p[0], ey = q[1] - p[1], l2 = ex * ex + ey * ey || 1e-9;
          const t = Math.max(0, Math.min(1, ((x - p[0]) * ex + (y - p[1]) * ey) / l2));
          const d = (p[0] + ex * t - x) ** 2 + (p[1] + ey * t - y) ** 2;
          if (d < best) { best = d; s = acc[i - 1] + (acc[i] - acc[i - 1]) * t; }
        }
        const span = ha + ((hb - ha) * s) / L, zg = this.at(x, y);
        const m = model?.deckAt(x, y, span, zg + 1.5) ?? null;
        const d = this.deckSurface(x, y, (m ?? span) + 0.12);
        if (d !== null) return d - 0.12;
        return m !== null ? m : Math.max(span, zg); // (never under the ground)
      };
    },
    // height of a track (its rails' foot) at (x, y): within 6 m of our route, ours and the opposite
    // one (4.5 m apart on the Modřany corridor), the track profile across the street (heightAt, #197: the
    // opposite track's own heights where the build gives them); elsewhere the ground or deck. The
    // drawn tracks and the trams on them both use it (the oncoming trams read the raw survey 4.2-4.8 m
    // off our track and jumped up to 3.4 m between Nádraží Braník and Čechova čtvrť)
    trackAt(x, y) {
      const n = near(x, y);
      return n && n.d < 6 ? profile.heightAt(n.s, n.l) : this.at(x, y, true);
    },
    // deck height if (x, y) is on one of the route's bridges, else null
    deckAt(x, y) {
      const n = near(x, y);
      return n && n.d < 22 && profile.onBridge(n.s) ? profile.heightAt(n.s, n.l) : null;
    },
    // ground at a route position with lateral offset (left > 0)
    atRoute(s, lateral) {
      if (Math.abs(lateral) < 9 || profile.onBridge(s)) return profile.heightAt(s, lateral);
      const o = route.offset(s, lateral);
      return this.at(o.x, o.y);
    },
  };
}
