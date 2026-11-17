// SPDX-License-Identifier: AGPL-3.0-or-later
// The prebuilt ground (data/lineN.ground.bin + .json, tools/ground_mesh.py, #508): fetched with the line's files, in
// tiles of the S-JTSK grid (`layout.tile` m, tools/geo.py TILE, #30), each decoded on its own in a pool of workers
// (src/groundWorker.js). At load every tile's height lookup is decoded: the world is placed on it. Then only the tiles
// in the window keep their lookup, and only they are drawn: within the fog's end of the camera, and of the route ahead
// of the tram (WINDOW_AHEAD). `?keepgeo` and `?bot` keep every tile, lookup and meshes: the checks read the whole line.
// The lookup (GroundTiles.lookup) is one index of the drawn triangles that cars, walkers, stops, kerbs, the camera and
// the lints read (#509); where no tile is held it answers null, and the 10 m grid answers (src/main.js useGroundLookup).

export const LOOKUP_CELL = 16; // m: a tile's lookup grid
export const WINDOW_AHEAD = 1000; // m of route ahead of the tram held, as round the camera (the user, 2026-11-17: "The
// window in front of the planned route can be loaded larger than around but I wouldn't be too greedy")
export const WINDOW_STEP = 100; // m: the route ahead read this often
export const WINDOW_KEEP = 250; // m past the window a tile is dropped (so a tile at its edge is not loaded and dropped in turn)
export const WINDOW_EVERY = 250; // ms: the window looked at this often

// The file: every line has it, the page builds no ground of its own (#510). Missing, the line does not load.
export async function fetchGround(load, lineId) {
  const [jr, br] = await Promise.all([load.get(`data/line${lineId}.ground.json`), load.get(`data/line${lineId}.ground.bin`)]);
  if (!jr.ok || !br.ok) throw new Error(`line ${lineId}: no ground file (data/line${lineId}.ground.*, tools/ground_mesh.py): ${jr.status} / ${br.status}`);
  const layout = await jr.json();
  if (!layout.tiles) throw new Error(`line ${lineId}: the ground file has no tiles (built before #30): python -P -E tools/ground_mesh.py --line ${lineId}`);
  return { layout, buffer: await br.arrayBuffer() };
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

// The ground's tiles: which are held, their lookups and meshes. `make(meshes, box)` (src/world.js attachGround) turns a
// tile's mesh arrays into the scene's meshes and returns them, `drop(meshes)` takes them out; `fix` brings a tile's
// lookup and mesh arrays down into the road tunnels' mouths (world.js mouthFix).
export class GroundTiles {
  constructor(file, styles, keep = false) {
    const L = (this.layout = file.layout);
    this.bytes = new Uint8Array(file.buffer);
    this.keep = keep;
    this.T = L.tile;
    [this.E0, this.N0] = L.origin;
    this.tiles = new Map(L.tiles.map((t) => [`${t.e},${t.n}`, t]));
    this.lookups = new Map(); // key -> GroundLookup
    this.drawn = new Map(); // key -> the scene's meshes
    this.busy = new Map(); // key -> the job's promise
    this.pool = new Pool(Math.max(1, Math.min(4, (navigator.hardwareConcurrency || 4) - 1)),
      { styles, names: drawNames(L), cell: LOOKUP_CELL, unit: L.unit, tile: L.tile });
    this.lookup = new TiledLookup(this);
    this.times = { decode: 0, lookup: 0, meshes: 0, jobs: 0, make: 0, makeMax: 0 }; // (ms: the workers', the page thread's)
    this.make = this.drop = this.fix = null;
    this.trim = false; // (set once the world is built and placed: from then on the window drops tiles)
    this.last = -Infinity;
  }
  keyAt(x, y) { return `${Math.floor((x + this.E0) / this.T)},${Math.floor((y + this.N0) / this.T)}`; }
  box(t) { return [t.e * this.T - this.E0, t.n * this.T - this.N0]; }
  blob(t) { return this.bytes.slice(t.offset, t.offset + t.bytes).buffer; }
  // a tile's lookup and (`meshes`) its meshes, with its neighbours' blobs for the normals on its border
  _job(key, meshes) {
    const t = this.tiles.get(key), lookup = !this.lookups.has(key), bytes = this.blob(t), ring = [], transfer = [bytes];
    if (meshes) {
      for (let de = -1; de <= 1; de++) for (let dn = -1; dn <= 1; dn++) {
        const r = (de || dn) && this.tiles.get(`${t.e + de},${t.n + dn}`);
        if (r) { const b = this.blob(r); ring.push({ bytes: b, layout: r.layout }); transfer.push(b); }
      }
    }
    return this.pool.run({ bytes, layout: t.layout, box: this.box(t), ring, lookup, meshes }, transfer).then((r) => {
      for (const k of ['decode', 'lookup', 'meshes']) this.times[k] += r.times[k];
      this.times.jobs++;
      if (r.lookup) {
        const lk = new GroundLookup(r.lookup);
        this.fix?.lookup(lk);
        this.lookups.set(key, lk);
      }
      if (r.meshes && this.make) {
        const t0 = performance.now();
        this.fix?.meshes(r.meshes, this.box(t));
        this.drawn.set(key, this.make(r.meshes, this.box(t)));
        const ms = performance.now() - t0;
        this.times.make += ms;
        this.times.makeMax = Math.max(this.times.makeMax, ms);
      }
    });
  }
  _want(key, meshes) {
    if (this.busy.has(key)) return this.busy.get(key);
    const p = this._job(key, meshes).finally(() => this.busy.delete(key));
    this.busy.set(key, p);
    return p;
  }
  // every tile's lookup (the world is placed on it)
  loadLookups() { return Promise.all([...this.tiles.keys()].map((k) => this._want(k, false))); }
  // the tiles whose square comes within `r` of a point
  near(points, r) {
    const out = new Set();
    for (const [x, y] of points) {
      const e0 = Math.floor((x - r + this.E0) / this.T), e1 = Math.floor((x + r + this.E0) / this.T);
      const n0 = Math.floor((y - r + this.N0) / this.T), n1 = Math.floor((y + r + this.N0) / this.T);
      for (let e = e0; e <= e1; e++) for (let n = n0; n <= n1; n++) {
        const k = `${e},${n}`;
        if (out.has(k) || !this.tiles.has(k)) continue;
        const bx = e * this.T - this.E0, by = n * this.T - this.N0;
        const dx = Math.max(bx - x, 0, x - bx - this.T), dy = Math.max(by - y, 0, y - by - this.T);
        if (dx * dx + dy * dy <= r * r) out.add(k);
      }
    }
    return out;
  }
  // The window: the tiles within `r` of the points held with their lookup and meshes; with `trim`, those past
  // r + WINDOW_KEEP dropped. Resolves when the window's tiles are in.
  update(points, r) {
    const want = this.keep ? new Set(this.tiles.keys()) : this.near(points, r), jobs = [];
    for (const k of want) if (!this.drawn.has(k)) jobs.push(this._want(k, true));
    if (this.trim && !this.keep) {
      const hold = this.near(points, r + WINDOW_KEEP);
      for (const [k, ms] of this.drawn) if (!hold.has(k) && !this.busy.has(k)) { this.drop(ms); this.drawn.delete(k); }
      for (const k of this.lookups.keys()) if (!hold.has(k) && !this.busy.has(k)) this.lookups.delete(k);
    }
    return Promise.all(jobs);
  }
  // each frame (src/main.js): the window round the camera and the route ahead of the tram, every WINDOW_EVERY ms
  tick(now, camera, route, s, r) {
    if (now - this.last < WINDOW_EVERY) return;
    this.last = now;
    const pts = [[camera.position.x, -camera.position.z]];
    if (route) for (let d = 0; d <= WINDOW_AHEAD; d += WINDOW_STEP) { const p = route.at(Math.min(route.length, s + d)); pts.push([p.x, p.y]); }
    this.update(pts, r).catch((e) => console.error('ground tiles', e));
  }
  // what is held now (the window's measure, tools/bench/tiles.js)
  held() {
    let tris = 0, bytes = 0;
    for (const ms of this.drawn.values()) for (const m of ms) {
      const g = m.geometry;
      tris += g.index.count / 3;
      for (const a of Object.values(g.attributes)) bytes += a.count * a.itemSize * 4;
      bytes += g.index.count * 4;
    }
    let lk = 0;
    for (const l of this.lookups.values()) for (const k of ['start', 'tris', 'tv', 'ta', 'tk', 'vx', 'vy', 'vz']) lk += l[k].byteLength;
    return { tiles: this.tiles.size, drawn: this.drawn.size, lookups: this.lookups.size, triangles: tris, meshMB: bytes / 1e6, lookupMB: lk / 1e6 };
  }
}

// The held tiles' lookups as one (GroundLookup's answers; null where no tile is held)
class TiledLookup {
  constructor(g) { this.g = g; this.hitZ = 0; }
  _at(x, y) { return this.g.lookups.get(this.g.keyAt(x, y)) || null; }
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
