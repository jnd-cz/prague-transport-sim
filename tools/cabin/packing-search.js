// SPDX-License-Identifier: AGPL-3.0-or-later
// #249 step 1: a longer search for standing places than the lab's adaptive packing (tools/cabin/adaptive-packing.js, 24 scan
// orders and 40 local refills, kept only when they add a place), by the same rules: a body's padded outline (the Idle
// cycle's convex XZ projection, tools/cabin/body-footprint.js) wholly on free floor (the 2 cm grid's circulation and
// standing pockets, categories 5 and 6) and no two outlines overlapping (convexOverlap, exact). The search: the lab's best
// scan order as the start, then many local moves, each taking the places within a random radius of a random place away and
// filling the hole again, the candidates there swept from a random side (jitter: m of noise on the sweep); a move is kept when the count does not fall (a move
// that keeps it lets the search wander across equal packings). The randomness is a seeded stream: one seed, one packing.
import { inflate } from './body-footprint.js';
import { transformFootprint, convexOverlap, bounds, boundsOverlap } from '../../src/passengers/packing-geometry.js';

// a seeded stream in [0, 1) (mulberry32)
function stream(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const BUCKET = 0.6; // (the spatial hash's cell, m: wider than a body, so a body meets only the buckets it touches)

// layout and floor as for adaptivePacking (the layout; the coarse 2 cm floor survey); body: the measured outline.
// angles: headings tried (evenly over the turn, 8 = the lab's); step: candidate spacing in floor cells (2 = the lab's
// 4 cm); moves: local moves; radius: the hole's [least, most] m; start: the lab's scan orders first (true) or none
export function searchPacking(layout, floor, body, { id = 'search', label = null, padding = 0.008, angles = 8, step = 2,
  moves = 3000, radius = [0.45, 1.1], seed = 1, trials = 24, jitter = 0.06 } = {}) {
  const { cell, nx, nz, xMin, zMin, cat } = floor, polygon = inflate(body.polygon, padding);
  const headings = Array.from({ length: angles }, (_, i) => -Math.PI + (2 * Math.PI * i) / angles);
  // each heading's outline and the 2 cm cells it touches, relative to a cell centre (as the lab's forms)
  const forms = headings.map((heading) => {
    const points = transformFootprint(polygon, 0, 0, heading), b = bounds(points), mask = [];
    for (let iz = Math.floor(b.zMin / cell - 0.5); iz <= Math.ceil(b.zMax / cell + 0.5); iz++) {
      for (let ix = Math.floor(b.xMin / cell - 0.5); ix <= Math.ceil(b.xMax / cell + 0.5); ix++) {
        const a = ix * cell - cell / 2, z = iz * cell - cell / 2;
        if (convexOverlap(points, [[a, z], [a + cell, z], [a + cell, z + cell], [a, z + cell]], -1e-10)) mask.push([ix, iz]);
      }
    }
    return { heading, points, mask };
  });
  const free = (ix, iz) => ix >= 0 && ix < nx && iz >= 0 && iz < nz && cat[iz * nx + ix] >= 5;
  const cands = [];
  for (let iz = 0; iz < nz; iz += step) {
    for (let ix = 0; ix < nx; ix += step) {
      const x = xMin + (ix + 0.5) * cell, z = zMin + (iz + 0.5) * cell;
      for (const f of forms) {
        if (!f.mask.every(([dx, dz]) => free(ix + dx, iz + dz))) continue;
        const pts = f.points.map(([a, b]) => [a + x, b + z]);
        cands.push({ n: cands.length, x, z, heading: f.heading, polygon: pts, bounds: bounds(pts) });
      }
    }
  }
  const keys = (b) => {
    const out = [];
    for (let z = Math.floor(b.zMin / BUCKET); z <= Math.floor(b.zMax / BUCKET); z++) {
      for (let x = Math.floor(b.xMin / BUCKET); x <= Math.floor(b.xMax / BUCKET); x++) out.push(`${x}:${z}`);
    }
    return out;
  };
  // the candidates by bucket of their middle (for a hole's candidates)
  const near = new Map();
  for (const c of cands) {
    const k = `${Math.floor(c.x / BUCKET)}:${Math.floor(c.z / BUCKET)}`;
    if (!near.has(k)) near.set(k, []);
    near.get(k).push(c);
  }
  // a packing: the chosen candidates and their buckets
  const packing = (list = []) => {
    const P = { list: [], grid: new Map() };
    for (const c of list) add(P, c);
    return P;
  };
  const add = (P, c) => {
    P.list.push(c);
    for (const k of keys(c.bounds)) {
      if (!P.grid.has(k)) P.grid.set(k, new Set());
      P.grid.get(k).add(c);
    }
  };
  const remove = (P, c) => {
    P.list.splice(P.list.indexOf(c), 1);
    for (const k of keys(c.bounds)) P.grid.get(k)?.delete(c);
  };
  const fits = (P, c) => {
    for (const k of keys(c.bounds)) {
      for (const q of P.grid.get(k) ?? []) if (boundsOverlap(c.bounds, q.bounds) && convexOverlap(c.polygon, q.polygon)) return false;
    }
    return true;
  };
  const fill = (P, order) => { for (const c of order) if (fits(P, c)) add(P, c); };
  // the start: the lab's scan orders (its score, its hash), the best of them
  const hash = (n, s) => {
    let x = (n + 1) ^ Math.imul(s + 1, 0x9e3779b1);
    x = Math.imul(x ^ (x >>> 16), 0x85ebca6b);
    x = Math.imul(x ^ (x >>> 13), 0xc2b2ae35);
    return ((x ^ (x >>> 16)) >>> 0) / 4294967296;
  };
  let best = packing();
  for (let s = 0; s < trials; s++) {
    const score = (p) => (s < 8 ? (s % 2 ? p.x : -p.x) * 1.7 + (s % 4 < 2 ? p.z : -p.z) * 0.8 + hash(p.n, s) * 0.2 : hash(p.n, s) * 1.4 + Math.abs(p.z) * -0.12);
    const P = packing();
    fill(P, [...cands].sort((a, b) => score(a) - score(b)));
    if (P.list.length > best.list.length) best = P;
  }
  const startCount = best.list.length;
  // the local moves
  const rand = stream(seed);
  const cur = packing(best.list);
  let kept = 0, gained = 0;
  for (let m = 0; m < moves; m++) {
    const pivot = cur.list[Math.floor(rand() * cur.list.length)], r = radius[0] + rand() * (radius[1] - radius[0]);
    const gone = cur.list.filter((c) => Math.hypot(c.x - pivot.x, c.z - pivot.z) <= r);
    const before = cur.list.length;
    for (const c of gone) remove(cur, c);
    const hole = [];
    for (let z = Math.floor((pivot.z - r - BUCKET) / BUCKET); z <= Math.floor((pivot.z + r + BUCKET) / BUCKET); z++) {
      for (let x = Math.floor((pivot.x - r - BUCKET) / BUCKET); x <= Math.floor((pivot.x + r + BUCKET) / BUCKET); x++) {
        for (const c of near.get(`${x}:${z}`) ?? []) if (Math.hypot(c.x - pivot.x, c.z - pivot.z) <= r + 0.35) hole.push(c);
      }
    }
    // (a sweep across the hole from a random side, a little jittered: a random order filled holes looser than they were,
    // 46 of 1,000 moves kept and none gained)
    const dir = rand() * 2 * Math.PI, ux = Math.cos(dir), uz = Math.sin(dir);
    for (const c of hole) c.key = c.x * ux + c.z * uz + rand() * jitter;
    hole.sort((a, b) => a.key - b.key);
    const added = cur.list.length;
    fill(cur, hole);
    const now = cur.list.length;
    if (now < before) { // (back: the hole's new places out, the old ones in)
      for (const c of cur.list.slice(added)) remove(cur, c);
      for (const c of gone) add(cur, c);
      continue;
    }
    kept++;
    if (now > best.list.length) { best = packing(cur.list); gained++; }
  }
  // the result as the lab's configurations (its fields; footprintWorld, the place's outline; checked: no two overlap)
  let pairs = 0;
  const L = best.list;
  for (let i = 0; i < L.length; i++) for (let j = i + 1; j < L.length; j++) if (convexOverlap(L[i].polygon, L[j].polygon)) pairs++;
  const places = L.map((p, i) => ({ id: `stand-${id}-${String(i + 1).padStart(3, '0')}`, x: +p.x.toFixed(4), z: +p.z.toFixed(4), y: layout.floorY,
    heading: p.heading, footprintPolygon: polygon, footprintWorld: p.polygon,
    footprintHalfExtents: { x: Math.max(Math.abs(p.bounds.xMin - p.x), Math.abs(p.bounds.xMax - p.x)), z: Math.max(Math.abs(p.bounds.zMin - p.z), Math.abs(p.bounds.zMax - p.z)) } }));
  const name = label ?? `Search · ${angles} headings, ${(step * cell * 100).toFixed(0)} cm, ${moves} moves`;
  return { id, label: name, places, bodyFootprint: body, paddingMetres: padding,
    search: { candidates: cands.length, headings: angles, gridMetres: step * cell, trials, moves, radius, seed, jitter, startCount, movesKept: kept, gains: gained },
    placement: { kind: name, count: places.length, totalWithSeats: places.length + layout.seats.length, referenceAvatarWidth: body.width, referenceAvatarDepth: body.depth,
      overlappingBoundingEnvelopePairs: pairs, overlapMetric: 'Rotated inflated convex body outlines; zero intersection pairs',
      limits: 'As the adaptive packing: the complete Idle-phase body projection plus padding on the 2 cm net floor; a longer search, not an optimum.' } };
}
