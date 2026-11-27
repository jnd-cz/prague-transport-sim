// SPDX-License-Identifier: AGPL-3.0-or-later
// The prebuilt ground (data/lineN.ground.bin + .json, tools/ground_mesh.py, #508): fetched with the line's files, in
// tiles of the S-JTSK grid (`layout.tile` m, tools/geo.py TILE, #30), each decoded on its own in a pool of workers
// (src/groundWorker.js). At load every tile's height lookup is decoded: the world is placed on it. Then only the tiles
// in the window keep their lookup, and only they are drawn in detail: within WINDOW_NEAR of the camera, and of the route
// ahead of the tram (WINDOW_AHEAD). Past them to the fog's end the far ground: each tile's own on a coarse grid. Start
// reads no lookup past the window: the network and the heights of what it places come from the build
// (data/lineN.network.json, tools/network.py, #658), and what stands off the track settles when its tile's lookup comes
// (later).
// `?keepgeo` and `?bot` keep every tile, lookup and meshes: the checks read the whole line.
// The lookup (GroundTiles.lookup) is one index of the drawn triangles that cars, walkers, stops, kerbs, the camera and
// the lints read (#509); where no tile is held it answers null, and the 10 m grid answers (src/main.js useGroundLookup).

export const LOOKUP_CELL = 16; // m: a tile's lookup grid
export const WINDOW_NEAR = 400; // m: the detail round the camera and the route ahead; past it the far ground (#30)
export const COARSE_STEP = 20; // m: the far ground's grid (it divides the tile: its border points are the neighbour's)
export const WINDOW_AHEAD = 1000; // m of route ahead of the tram held, as round the camera (larger, not too greedy:
// maintainer, 2026-11-17)
export const WINDOW_STEP = 100; // m: the route ahead read this often
export const WINDOW_KEEP = 250; // m past the window a tile is dropped (so a tile at its edge is not loaded and dropped in turn)
export const WINDOW_EVERY = 250; // ms: the window looked at this often
export const RETRY_FIRST = 1000; // ms: a tile that failed is asked for again after this, doubling up to RETRY_MAX (#711)
export const RETRY_MAX = 60000;

// The file: every line has it, the page builds no ground of its own (#510). Missing, the line does not load.
export async function fetchGround(load, lineId) {
  const [jr, br] = await Promise.all([load.get(`data/line${lineId}.ground.json`), load.get(`data/line${lineId}.ground.bin`)]);
  if (!jr.ok || !br.ok) throw new Error(`line ${lineId}: no ground file (data/line${lineId}.ground.*, tools/ground_mesh.py): ${jr.status} / ${br.status}`);
  const layout = await jr.json();
  if (!layout.tiles) throw new Error(`line ${lineId}: the ground file has no tiles (built before #30): python -P -E tools/ground_mesh.py --line ${lineId}`);
  return { layout, buffer: await br.arrayBuffer() };
}

// the window's points: where the camera is (x, y), then the route ahead of s every WINDOW_STEP to WINDOW_AHEAD
export function windowPoints(at, route, s) {
  const pts = [at];
  if (route) for (let d = 0; d <= WINDOW_AHEAD; d += WINDOW_STEP) { const p = route.at(Math.min(route.length, s + d)); pts.push([p.x, p.y]); }
  return pts;
}

// A few workers, each job to the least busy (src/groundWorker.js)
class Pool {
  constructor(n, init) {
    this.wait = new Map();
    this.id = 0;
    this.ws = Array.from({ length: n }, () => {
      const w = new Worker(new URL('./groundWorker.js', import.meta.url), { type: 'module' });
      w.busy = 0;
      w.onmessage = ({ data }) => { const j = this.wait.get(data.id); this.wait.delete(data.id); w.busy--; j.res(data); };
      w.onerror = (e) => { for (const [id, j] of this.wait) if (j.w === w) { this.wait.delete(id); j.rej(e); } };
      w.postMessage({ init });
      return w;
    });
  }
  run(msg, transfer) {
    const w = this.ws.reduce((a, b) => (b.busy < a.busy ? b : a));
    w.busy++;
    msg.id = ++this.id;
    return new Promise((res, rej) => { this.wait.set(msg.id, { res, rej, w }); w.postMessage(msg, transfer); });
  }
}

// The draw names per class: '' first (a tile that names none of a class's triangles draws them as '', its index 0)
function drawNames(layout) {
  const out = {};
  for (const name of Object.keys(layout.classes)) out[name] = ['', ...(layout.draw?.[name] || []).filter((d) => d !== '')];
  return out;
}

// The ground's tiles: which are held, their lookups and meshes. `make(meshes, box)` (src/groundDraw.js attachGround) turns a
// tile's mesh arrays into the scene's meshes and returns them, `drop(meshes)` takes them out; `makeCoarse(coarse, box)`
// makes a tile's far ground (#30), kept for every tile and hidden while its detail is drawn (the road tunnels' mouths are
// in the file, tools/ground_mesh.py fit_mouths, #682). A tile's meshes wait in `ready` and
// join the scene one a frame (flush), nearest first, so their uploads to the GPU fall in different frames.
export class GroundTiles {
  constructor(file, styles, keep = false) {
    const L = (this.layout = file.layout);
    this.bytes = new Uint8Array(file.buffer);
    this.keep = keep;
    this.T = L.tile;
    [this.E0, this.N0] = L.origin;
    this.tiles = new Map(L.tiles.map((t) => [`${t.e},${t.n}`, t]));
    this.lookups = new Map(); // key -> GroundLookup
    this.waiting = new Map(); // key -> what waits for that tile's lookup (later)
    this.drawn = new Map(); // key -> the scene's meshes
    this.coarse = new Map(); // key -> the far ground's mesh (or, before the world is built, its arrays)
    this.ready = []; // [key, mesh arrays]: made one a frame
    this.busy = new Map(); // key -> the job's promise
    this.failed = new Map(); // key -> { n, next, error }: a tile whose job failed, not asked for again before `next` (#711)
    this.onFail = null; // (key, failed): told of each failure (src/main.js: the performance log)
    this.pool = new Pool(Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 4) - 1)),
      { styles, names: drawNames(L), cell: LOOKUP_CELL, unit: L.unit, tile: L.tile });
    this.lookup = new TiledLookup(this);
    this.times = { decode: 0, lookup: 0, meshes: 0, jobs: 0, make: 0, makeMax: 0 }; // (ms: the workers', the page thread's)
    this.make = this.drop = this.makeCoarse = null;
    this.trim = false; // (set once the world is built and placed: from then on the window drops tiles)
    this.last = -Infinity;
  }
  keyAt(x, y) { return `${Math.floor((x + this.E0) / this.T)},${Math.floor((y + this.N0) / this.T)}`; }
  box(t) { return [t.e * this.T - this.E0, t.n * this.T - this.N0]; }
  blob(t) { return this.bytes.slice(t.offset, t.offset + t.bytes).buffer; }
  // the detail's reach: WINDOW_NEAR, or the fog's end when nearer (past it nothing is seen)
  reach(fog) { return Math.min(WINDOW_NEAR, fog); }
  // a tile's lookup (the first time with its far ground) and (`meshes`) its meshes, with its neighbours' blobs for the
  // normals on its border
  _job(key, meshes) {
    const t = this.tiles.get(key), lookup = !this.lookups.has(key), bytes = this.blob(t), ring = [], transfer = [bytes];
    if (meshes) {
      for (let de = -1; de <= 1; de++) for (let dn = -1; dn <= 1; dn++) {
        const r = (de || dn) && this.tiles.get(`${t.e + de},${t.n + dn}`);
        if (r) { const b = this.blob(r); ring.push({ bytes: b, layout: r.layout }); transfer.push(b); }
      }
    }
    const coarse = lookup && !this.keep && !this.coarse.has(key) ? COARSE_STEP : 0;
    return this.pool.run({ bytes, layout: t.layout, box: this.box(t), ring, lookup, meshes, coarse }, transfer).then((r) => {
      for (const k of ['decode', 'lookup', 'meshes']) this.times[k] += r.times[k];
      this.times.jobs++;
      if (r.lookup) {
        const lk = new GroundLookup(r.lookup);
        this.lookups.set(key, lk);
        const w = this.waiting.get(key);
        this.waiting.delete(key);
        for (const fn of w || []) fn();
      }
      if (r.coarse) this._coarse(key, r.coarse);
      if (r.meshes) this.ready.push([key, r.meshes]);
    });
  }
  _coarse(key, c) {
    if (!this.makeCoarse || !c.idx.length) { this.coarse.set(key, c); return; }
    const m = this.makeCoarse(c, this.box(this.tiles.get(key)));
    m.visible = !this.drawn.has(key);
    this.coarse.set(key, m);
  }
  // the far ground's arrays that came before the world was built (src/groundDraw.js attachGround)
  flushCoarse() { for (const [k, c] of this.coarse) if (c.idx) this._coarse(k, c); }
  _make(key, ms) {
    if (this.drawn.has(key) || !this.make) return;
    const t0 = performance.now(), box = this.box(this.tiles.get(key));
    this.drawn.set(key, this.make(ms, box));
    const c = this.coarse.get(key);
    if (c && c.isObject3D) c.visible = false;
    const dt = performance.now() - t0;
    this.times.make += dt;
    this.times.makeMax = Math.max(this.times.makeMax, dt);
  }
  // one tile's meshes into the scene (each frame); drain(): all that are ready (the load, the benches)
  flush() { if (this.ready.length) this._make(...this.ready.shift()); }
  drain() { while (this.ready.length) this._make(...this.ready.shift()); }
  // a tile's job; it resolves when the job fails too: the tile is noted in `failed`, its far ground stays drawn, and the
  // window asks for it again only after a pause that doubles with each failure (it was asked for every 250 ms, #711)
  _want(key, meshes) {
    if (this.busy.has(key)) return this.busy.get(key);
    const p = this._job(key, meshes).then(() => { this.failed.delete(key); }, (e) => this._fail(key, e))
      .finally(() => this.busy.delete(key));
    this.busy.set(key, p);
    return p;
  }
  _fail(key, e) {
    const f = this.failed.get(key) || { n: 0 };
    f.n++;
    f.next = performance.now() + Math.min(RETRY_MAX, RETRY_FIRST * 2 ** (f.n - 1));
    f.error = String(e?.message || e);
    this.failed.set(key, f);
    console.warn(`ground tile ${key} failed (${f.n}×), asked again in ${Math.round(f.next - performance.now())} ms:`, f.error);
    if (this.onFail) this.onFail(key, f);
  }
  // every tile's lookup (the world is placed on it) and its far ground; a tile that fails stops the load (the world
  // would stand on the 10 m grid there)
  async loadLookups() {
    await Promise.all([...this.tiles.keys()].map((k) => this._want(k, false)));
    if (this.failed.size) {
      const [k, f] = this.failed.entries().next().value;
      throw new Error(`ground tile ${k} (${this.failed.size} failed): ${f.error}`);
    }
  }
  // fn() now where (x, y)'s tile holds its lookup, else once it comes (the window reaches it); where the file has no tile
  // there, now (the 10 m grid answers). What Start places off the track settles on the drawn ground this way, without
  // reading a lookup past the window (#658)
  later(x, y, fn) {
    const k = this.keyAt(x, y);
    if (this.lookups.has(k) || !this.tiles.has(k)) { fn(); return; }
    if (!this.waiting.has(k)) this.waiting.set(k, []);
    this.waiting.get(k).push(fn);
  }
  // the tiles whose square comes within `r` of a point, nearest the first point first
  near(points, r) {
    const out = new Map(), [x0, y0] = points[0] || [0, 0];
    for (const [x, y] of points) {
      const e0 = Math.floor((x - r + this.E0) / this.T), e1 = Math.floor((x + r + this.E0) / this.T);
      const n0 = Math.floor((y - r + this.N0) / this.T), n1 = Math.floor((y + r + this.N0) / this.T);
      for (let e = e0; e <= e1; e++) for (let n = n0; n <= n1; n++) {
        const k = `${e},${n}`;
        if (out.has(k) || !this.tiles.has(k)) continue;
        const bx = e * this.T - this.E0, by = n * this.T - this.N0;
        const dx = Math.max(bx - x, 0, x - bx - this.T), dy = Math.max(by - y, 0, y - by - this.T);
        if (dx * dx + dy * dy <= r * r) out.set(k, Math.hypot(bx + this.T / 2 - x0, by + this.T / 2 - y0));
      }
    }
    return new Set([...out].sort((a, b) => a[1] - b[1]).map((e) => e[0]));
  }
  // The window: the tiles within `r` of the points held with their lookup and meshes; with `trim`, those past
  // r + WINDOW_KEEP dropped (their far ground shown again). Resolves when the window's tiles are ready (made by flush).
  // (#657 kept every lookup while Start read the survey along the whole line, 48-120 MB; it reads none since #658)
  // each(): after each tile's job (settle's progress)
  update(points, r, each = null) {
    const want = this.keep ? new Set(this.tiles.keys()) : this.near(points, r), jobs = [], queued = new Set(this.ready.map((e) => e[0]));
    const now = performance.now();
    for (const k of want) {
      if (this.drawn.has(k) || queued.has(k) || this.failed.get(k)?.next > now) continue;
      const p = this._want(k, true);
      jobs.push(each ? p.then(each) : p);
    }
    if (this.trim && !this.keep) {
      const hold = this.near(points, r + WINDOW_KEEP);
      this.ready = this.ready.filter((e) => hold.has(e[0]));
      for (const [k, ms] of this.drawn) {
        if (hold.has(k) || this.busy.has(k)) continue;
        this.drop(ms);
        this.drawn.delete(k);
        const c = this.coarse.get(k);
        if (c && c.isObject3D) c.visible = true;
      }
      for (const k of this.lookups.keys()) if (!hold.has(k) && !this.busy.has(k)) this.lookups.delete(k);
    }
    return Promise.all(jobs);
  }
  // each frame (src/main.js): a tile's meshes into the scene; every WINDOW_EVERY ms the window round the camera and the
  // route ahead of the tram, within the detail's reach
  tick(now, camera, route, s, fog) {
    this.flush();
    if (now - this.last < WINDOW_EVERY) return;
    this.last = now;
    this.update(windowPoints([camera.position.x, -camera.position.z], route, s), this.reach(fog)).catch((e) => console.error('ground tiles', e));
  }
  // the window's tiles in the scene: their jobs waited for and all their meshes made at once (the load, Start, #711);
  // progress(done, total) after each job. Returns the tiles asked for
  async settle(points, r, progress = null) {
    let done = 0, total = 0;
    const p = this.update(points, r, () => { done++; if (progress) progress(done, total); });
    total = this.busy.size;
    if (progress && total) progress(0, total);
    await p;
    this.drain();
    return total;
  }
  // what is held now (the window's measure, tools/bench/ground_tiles.py)
  held() {
    const size = (ms) => {
      let tris = 0, bytes = 0;
      for (const m of ms) {
        const g = m.geometry;
        tris += g.index.count / 3;
        for (const a of Object.values(g.attributes)) bytes += a.count * a.itemSize * 4;
        bytes += g.index.count * 4;
      }
      return [tris, bytes];
    };
    let tris = 0, bytes = 0, ctris = 0, cbytes = 0;
    for (const ms of this.drawn.values()) { const [t, b] = size(ms); tris += t; bytes += b; }
    const coarse = [...this.coarse.values()].filter((c) => c.isObject3D);
    [ctris, cbytes] = size(coarse);
    let lk = 0;
    for (const l of this.lookups.values()) for (const k of ['start', 'tris', 'tv', 'ta', 'tk', 'vx', 'vy', 'vz']) lk += l[k].byteLength;
    return { tiles: this.tiles.size, drawn: this.drawn.size, lookups: this.lookups.size, triangles: tris, meshMB: bytes / 1e6, lookupMB: lk / 1e6,
      coarse: coarse.length, coarseShown: coarse.filter((c) => c.visible).length, coarseTriangles: ctris, coarseMB: cbytes / 1e6 };
  }
}

// The held tiles' lookups as one (GroundLookup's answers; null where no tile is held)
class TiledLookup {
  // (missed: the reads where the file has a tile but its lookup is not held, answered by the 10 m grid or the layers
  // instead: what a player's streamed page reads that the checks' ?keepgeo page does not, tools/headless.py --player, #710)
  constructor(g) { this.g = g; this.hitZ = 0; this.missed = { reads: 0, tiles: new Set(), at: [] }; }
  _at(x, y) {
    const k = this.g.keyAt(x, y), lk = this.g.lookups.get(k);
    if (lk) return lk;
    if (this.g.tiles.has(k)) {
      const m = this.missed;
      m.reads++;
      if (!m.tiles.has(k)) { m.tiles.add(k); if (m.at.length < 20) m.at.push([Math.round(x), Math.round(y)]); }
    }
    return null;
  }
  height(x, y) { const lk = this._at(x, y); if (!lk) return null; const z = lk.height(x, y); this.hitZ = lk.hitZ; return z; }
  survey(x, y) { const lk = this._at(x, y); if (!lk) return null; const v = lk.survey(x, y); this.hitZ = lk.hitZ; return v; }
  kind(x, y) { const lk = this._at(x, y); if (!lk) return null; const v = lk.kind(x, y); this.hitZ = lk.hitZ; return v; }
  bedOffSurvey(x, y) { const lk = this._at(x, y); return lk ? lk.bedOffSurvey(x, y) : null; }
  covered(x, y) { const lk = this._at(x, y); return lk ? lk.covered(x, y) : false; }
  surveyNear(x, y, r, fn) { for (const k of this.g.near([[x, y]], r)) this.g.lookups.get(k)?.surveyNear(x, y, r, fn); }
  // the held tiles' own lookups (the lints, the mouths)
  parts() { return [...this.g.lookups.values()]; }
}

// The drawn ground at (x, y): the triangle holding the point (the highest where several do: a kerb's top at its edge),
// its plane's height there and the survey's class under it (src/terrain.js DtmSurface asks it for its ground level).
export class GroundLookup {
  constructor(lk) {
    Object.assign(this, lk);
    this.coverSet = new Set(lk.cover);
    this.hitZ = 0;
  }
  // (the triangle, its height in this.hitZ; -1 off the ground)
  _find(x, y) {
    const px = x - this.x0, py = y - this.y0, i = Math.floor(px / this.cell), j = Math.floor(py / this.cell);
    if (i < 0 || j < 0 || i >= this.nx || j >= this.ny) return -1;
    const { vx, vy, vz, tv, tris } = this, k = j * this.nx + i;
    let best = -1, bz = 0;
    for (let s = this.start[k], e = this.start[k + 1]; s < e; s++) {
      const t = 3 * tris[s], a = tv[t], b = tv[t + 1], c = tv[t + 2];
      const ax = vx[a], ay = vy[a], bx = vx[b], by = vy[b], cx = vx[c], cy = vy[c];
      const d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
      if (!d) continue;
      const w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d, w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d;
      const w2 = 1 - w0 - w1, eps = -1e-7;
      if (w0 < eps || w1 < eps || w2 < eps) continue;
      const z = w0 * vz[a] + w1 * vz[b] + w2 * vz[c];
      if (best < 0 || z > bz) { best = tris[s]; bz = z; }
    }
    this.hitZ = bz;
    return best;
  }
  height(x, y) { return this._find(x, y) < 0 ? null : this.hitZ; }
  // the survey at (x, y): { z, c } (its class: 'road', 'sidewalk', …), null where the ground is not the survey's
  survey(x, y) {
    const t = this._find(x, y);
    return t < 0 || !this.ta[t] ? null : { z: this.hitZ, c: this.areas[this.ta[t]] };
  }
  // the file's class at (x, y) ('terrain', 'survey', 'bed', 'plot'), its height in this.hitZ; null off the ground
  kind(x, y) {
    const t = this._find(x, y);
    return t < 0 ? null : this.kinds[this.tk[t]];
  }
  // the height of a track's bed at (x, y) where the ground there is a bed off the survey, else null
  bedOffSurvey(x, y) {
    const t = this._find(x, y);
    return t >= 0 && !this.ta[t] && this.kinds[this.tk[t]] === 'bed' ? this.hitZ : null;
  }
  // each survey triangle with a corner within r of (x, y), once: fn(class, [x, y, z] × 3) (review's class layer)
  surveyNear(x, y, r, fn) {
    const { vx, vy, vz, tv, ta, tris, start } = this, px = x - this.x0, py = y - this.y0, r2 = r * r, seen = new Set();
    const i0 = Math.max(0, Math.floor((px - r) / this.cell)), i1 = Math.min(this.nx - 1, Math.floor((px + r) / this.cell));
    const j0 = Math.max(0, Math.floor((py - r) / this.cell)), j1 = Math.min(this.ny - 1, Math.floor((py + r) / this.cell));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
      const k = j * this.nx + i;
      for (let s = start[k], e = start[k + 1]; s < e; s++) {
        const t = tris[s];
        if (!ta[t] || seen.has(t)) continue;
        seen.add(t);
        const c = [tv[3 * t], tv[3 * t + 1], tv[3 * t + 2]];
        if (!c.some((v) => (vx[v] - px) ** 2 + (vy[v] - py) ** 2 <= r2)) continue;
        fn(this.areas[ta[t]], c.map((v) => [vx[v] + this.x0, vy[v] + this.y0, vz[v]]));
      }
    }
  }
  // whether the survey describes the street in (x, y)'s 10 m cell at all (src/terrain.js TriIndex.covered)
  covered(x, y) { return this.coverSet.has(Math.floor(x / 10) * 100003 + Math.floor(y / 10)); }
}
