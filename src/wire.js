// SPDX-License-Identifier: AGPL-3.0-or-later
// The contact wire's height over the rail heads: its normal height (src/models.js CONTACT_WIRE), and lower under a
// structure (#71). No imports: tools/test_wire.py loads it alone.
//
// Under a bridge lower than the wire's normal height the wire drops to just under the structure and rises back on a
// gentle slope, and every wire near it comes down with it (the maintainer, #71: under Výtoň's railway bridge "the
// whole overhead network gets noticeably low and affects the nearby junction"). The collectors follow it; the T3's
// goes low enough for Výtoň's bridge (the maintainer, #13, 2026-11-28). Until this the wire was 5.34 m everywhere and
// the bridge models were cut where it passed: on line 17 Výtoň's railway bridge (4.32 m over the rails at its lowest)
// and the two bridges before Nádraží Holešovice (4.12 and 4.52 m).
export const COLLECTOR = 1.0;      // m a side of a track's axis that the collector takes (the lint's mounted-clear-of-tram)
export const WIRE_FROM = 3.6;      // m over the rails: what stands from here up is over the collector, lower is beside the car body
export const WIRE_UNDER = 0.15;    // m: the wire under the lowest point of a structure over the collector
export const WIRE_MIN = 3.9;       // m: the wire is never lower over the rails: the T3's collector reaches down to 3.89 m (assets/t3h/rig.json minContactHeight)
// The wire's slope: at most 1 in (5 x the speed in km/h) is the desired figure of Yarra Trams' CE-019-ST-0032 (4.11.4, #71),
// 1 in 250 at the network's 50 km/h, the gentlest it asks for at any speed driven here; 1 in 75 is its absolute limit.
export const WIRE_GRADE = 1 / 250;
// A model's slab over a track (the Divadelní rule of the survey's decks, tools/zps_decks.py, for the bridge models;
// the maintainer, #71): a model that leaves less than the clearance OSM posts for the way under it, CLEAR_MARGIN m and
// the wire's gap, has its underside lifted to that, as far as SLAB_LEFT m of slab stay under its top. The models are
// photogrammetry of 2001-2008 with a nominal depth; the streets under them were rebuilt since. Where OSM posts nothing
// the legal height without a sign holds, for a track as for a road (the maintainer, #71). The wire is over the sign's
// height, not the slab alone: a sign under tram wires shows noticeably less than the wires' height, so that no vehicle
// comes near them (the maintainer, #71); how much less is not known here, CLEAR_MARGIN is the least. A sign lower
// than a collector reaches (3.1 m under Výtoň's bridge, 3.2 m in U Výstaviště) so asks for the lowest wire and its gap.
export const CLEARANCE = 4.2;      // m: the clearance where no sign says less (tools/clearances.py's default for car roads)
export const CLEAR_MARGIN = 0.1, SLAB_LEFT = 0.3; // m (tools/zps_decks.py MARGIN, MIN_SLAB)
export const LIFT_REACH = 12;      // m in plan from a lifted point over a track: the model's underside comes up this far aside, the street under it
const TOP_NEAR = 0.45;             // m in plan: a point's top is the highest point of the model this near (the models are sampled every 0.4 m)
// m: a posted clearance holds for a structure's points this near its way. The street's axis lies up to 8 m from a track
// on its own lane, and a tagged way may end before the bridge: 13.2 m from the first point under the bridge in
// Dukelských hrdinů (line 17).
const HEADROOM_REACH = 20;
const SAME_LEVEL = 3;              // m: a low point lowers the wires of tracks within this of its own rail height
const LOW_STEP = 0.5, BESIDE = 6;  // m: the tracks are read for structures this often; within BESIDE m of a low point the wire keeps its height, not its height over the rails
const CELL = 0.5, FAR = 512;

// The clearance posted near a place: `list` is the line's `headroom` (tools/clearances.py: [{p: [[x, y], ...], mh}],
// OSM's ways with a posted maxheight near the tracks), the answer the highest of the ways within HEADROOM_REACH m, or
// 0 where there is none. (The highest: a sign says the structures on its way are no lower, and a way tagged for a
// low bridge farther on passes other structures too.)
export function headroomAt(list) {
  const ways = (list || []).filter((w) => w.mh > 0 && w.p?.length > 1).map((w) => ({ w, x0: Math.min(...w.p.map((q) => q[0])) - HEADROOM_REACH, x1: Math.max(...w.p.map((q) => q[0])) + HEADROOM_REACH,
    y0: Math.min(...w.p.map((q) => q[1])) - HEADROOM_REACH, y1: Math.max(...w.p.map((q) => q[1])) + HEADROOM_REACH }));
  return (x, y) => {
    let mh = 0;
    for (const b of ways) {
      if (b.w.mh <= mh || x < b.x0 || x > b.x1 || y < b.y0 || y > b.y1) continue;
      const p = b.w.p;
      for (let i = 0; i + 1 < p.length; i++) {
        const ex = p[i + 1][0] - p[i][0], ey = p[i + 1][1] - p[i][1];
        const u = Math.max(0, Math.min(1, ((x - p[i][0]) * ex + (y - p[i][1]) * ey) / Math.max(ex * ex + ey * ey, 1e-9)));
        const d = Math.hypot(p[i][0] + u * ex - x, p[i][1] + u * ey - y);
        if (d <= HEADROOM_REACH) { mh = b.w.mh; break; }
      }
    }
    return mh;
  };
}

// The structures' points over the tracks, by 0.5 m cell (each point once to 0.1 m in plan and 5 cm in height): what a
// wire must pass under. A point is x, y, its height (as lifted, below), the rail under it and its height in the model.
export class Ceilings {
  constructor() { this.cells = new Map(); this.seen = new Set(); this.count = 0; this.lifted = []; }

  add(x, y, z, zr = NaN) {
    const id = `${Math.round(x * 10)},${Math.round(y * 10)},${Math.round(z * 20)}`;
    if (this.seen.has(id)) return;
    this.seen.add(id);
    const k = Math.floor(x / CELL) * 2000003 + Math.floor(y / CELL);
    let c = this.cells.get(k);
    if (!c) this.cells.set(k, (c = []));
    c.push(x, y, z, zr, z);
    this.count++;
  }

  // the highest point of the models within r m of (x, y) in plan, or null
  highest(x, y, r) {
    let top = null;
    for (let ix = Math.floor((x - r) / CELL); ix <= Math.floor((x + r) / CELL); ix++) {
      for (let iy = Math.floor((y - r) / CELL); iy <= Math.floor((y + r) / CELL); iy++) {
        const c = this.cells.get(ix * 2000003 + iy);
        if (!c) continue;
        for (let n = 0; n < c.length; n += 5) if ((top === null || c[n + 4] > top) && Math.hypot(c[n] - x, c[n + 1] - y) <= r) top = c[n + 4];
      }
    }
    return top;
  }

  // The models' undersides lifted to the clearance (the rule at CLEARANCE, above): `posted(x, y)` is the clearance
  // posted near a place (headroomAt), 0 for none. One clearance for a structure: the points that touch (cells within
  // 1 m of each other: the tracks under one bridge) take the highest posted near any of them, or CLEARANCE; OSM's
  // tagged way ends 5 m before the face of the bridge in Dukelských hrdinů (line 17), 25 m from its far side. A point
  // lower over its rail than the clearance, CLEAR_MARGIN and the wire's gap (at least the lowest wire and its gap) comes
  // up to that, or to SLAB_LEFT m under the model's top over it, whichever is lower; a point of the model's top stays. Returns the
  // lifted points ({x, y, zr, from, z, to: the height asked for, mh}), kept as `lifted`.
  lift(posted) {
    this.lifted = [];
    const done = new Set();
    for (const [k0, c0] of this.cells) {
      if (done.has(k0)) continue;
      done.add(k0);
      const cells = [], stack = [c0];
      let mh = 0;
      while (stack.length) {
        const c = stack.pop(), ix = Math.floor(c[0] / CELL), iy = Math.floor(c[1] / CELL);
        cells.push(c);
        mh = Math.max(mh, posted((ix + 0.5) * CELL, (iy + 0.5) * CELL));
        for (let dx = -2; dx <= 2; dx++) for (let dy = -2; dy <= 2; dy++) {
          const k = (ix + dx) * 2000003 + iy + dy, n = this.cells.get(k);
          if (n && !done.has(k)) { done.add(k); stack.push(n); }
        }
      }
      mh = mh || CLEARANCE;
      for (const c of cells) {
        for (let n = 0; n < c.length; n += 5) {
          const zr = c[n + 3], z0 = c[n + 4];
          if (!(zr === zr)) continue; // (a point with no rail given)
          const to = zr + Math.max(mh + CLEAR_MARGIN, WIRE_MIN) + WIRE_UNDER;
          if (z0 >= to) continue;
          const z = Math.min(to, this.highest(c[n], c[n + 1], TOP_NEAR) - SLAB_LEFT);
          if (z > z0 + 0.005) { c[n + 2] = z; this.lifted.push({ x: c[n], y: c[n + 1], zr, from: z0, z, to, mh }); }
        }
      }
    }
    return this.lifted;
  }

  // the lowest point within r m of (x, y) in plan between the heights z0 and z1, or null
  lowest(x, y, z0, z1, r = COLLECTOR) {
    let low = null;
    for (let ix = Math.floor((x - r) / CELL); ix <= Math.floor((x + r) / CELL); ix++) {
      for (let iy = Math.floor((y - r) / CELL); iy <= Math.floor((y + r) / CELL); iy++) {
        const c = this.cells.get(ix * 2000003 + iy);
        if (!c) continue;
        for (let n = 0; n < c.length; n += 5) {
          const z = c[n + 2];
          if (z >= z0 && z <= z1 && (low === null || z < low) && Math.hypot(c[n] - x, c[n + 1] - y) <= r) low = z;
        }
      }
    }
    return low;
  }
}

// The wire over every track of `tracks` ({smooth: [[x, y], ...], z: [...]}, the rails' heights) under `ceilings`; `normal`:
// its height where nothing is over it (src/models.js CONTACT_WIRE). `over(x, y, zr)`: the wire's height over the rail head
// zr at (x, y). `low`: the low points it comes from (each track vertex under a structure: x, y, the rail, the wire's height
// there). `drops`: the places, low points within 60 m of each other, for the log. A place whose structure stands lower
// than a collector reaches (under WIRE_MIN + WIRE_UNDER over the rails) is no evidence of a low wire, the model or the
// track's height is off there: `impossible` lists it, and its wire stays at its normal height. The heights are the
// ceilings' as lifted (Ceilings.lift): `lifts` lists those places (the underside over the rails from, to; the clearance),
// and `liftAt(x, y)` is the nearest lifted point within LIFT_REACH m in plan, for the models' corners (src/buildings.js).
export function makeWire(tracks, ceilings, normal) {
  let low = [];
  const far = new Map();
  if (ceilings.count) {
    // (every LOW_STEP m along each track, not at its vertices alone: a structure's edge is met within half a metre)
    for (const t of tracks) {
      for (let i = 0; i < t.smooth.length; i++) {
        const a = t.smooth[i], b = t.smooth[Math.min(i + 1, t.smooth.length - 1)], za = t.z[i], zb = t.z[Math.min(i + 1, t.smooth.length - 1)];
        const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / LOW_STEP));
        for (let k = 0; k < n; k++) {
          const u = k / n, x = a[0] + (b[0] - a[0]) * u, y = a[1] + (b[1] - a[1]) * u, zr = za + (zb - za) * u;
          const c = ceilings.lowest(x, y, zr + WIRE_FROM, zr + normal + WIRE_UNDER);
          if (c === null) continue;
          const h = Math.max(WIRE_MIN, c - zr - WIRE_UNDER);
          if (h < normal - 0.005) low.push({ x, y, zr, h, under: c - zr });
        }
      }
    }
  }
  const places = [];
  for (const p of low) {
    let d = places.find((q) => Math.hypot(q.x - p.x, q.y - p.y) < 60);
    if (!d) places.push((d = { x: p.x, y: p.y, wire: p.h, under: p.under, points: [] }));
    d.points.push(p);
    if (p.under < d.under) Object.assign(d, { x: p.x, y: p.y, wire: p.h, under: p.under });
  }
  const round = (d) => ({ x: Math.round(d.x), y: Math.round(d.y), wire: Math.round(d.wire * 100) / 100, under: Math.round(d.under * 100) / 100,
    points: d.points.length, reach: Math.round((normal - d.wire) / WIRE_GRADE) });
  const impossible = places.filter((d) => d.under < WIRE_MIN + WIRE_UNDER);
  for (const d of impossible) for (const p of d.points) p.out = true;
  low = low.filter((p) => !p.out);
  for (const p of low) {
    const k = Math.floor(p.x / FAR) * 2000003 + Math.floor(p.y / FAR);
    if (!far.has(k)) far.set(k, []);
    far.get(k).push(p);
  }
  const over = (x, y, zr) => {
    if (!low.length) return normal;
    let h = normal;
    const gx = Math.floor(x / FAR), gy = Math.floor(y / FAR);
    for (let ix = gx - 1; ix <= gx + 1; ix++) {
      for (let iy = gy - 1; iy <= gy + 1; iy++) {
        for (const p of far.get(ix * 2000003 + iy) || []) {
          if (Math.abs(p.zr - zr) > SAME_LEVEL + 0.08 * (Math.abs(p.x - x) + Math.abs(p.y - y))) continue;
          const d = Math.hypot(p.x - x, p.y - y);
          let v = p.h + d * WIRE_GRADE;
          // (beside the structure the wire is no higher than under it, whatever the rails do: on a street that comes
          // down to a bridge the rails before it stand higher, and a wire as high over them ran into the bridge's
          // face; the maintainer, #71)
          if (d < BESIDE) v = Math.max(WIRE_MIN, Math.min(v, p.zr + p.h - zr + d * WIRE_GRADE));
          if (v < h) h = v;
        }
      }
    }
    return h;
  };
  const lifts = [], near = new Map(), LC = 16;
  for (const p of ceilings.lifted) {
    let d = lifts.find((q) => Math.hypot(q.x - p.x, q.y - p.y) < 60);
    if (!d) lifts.push((d = { x: p.x, y: p.y, from: Infinity, to: Infinity, mh: p.mh, points: 0 }));
    d.points++;
    if (p.from - p.zr < d.from) Object.assign(d, { x: p.x, y: p.y, from: p.from - p.zr, mh: p.mh });
    d.to = Math.min(d.to, p.z - p.zr);
    const k = Math.floor(p.x / LC) * 2000003 + Math.floor(p.y / LC);
    if (!near.has(k)) near.set(k, []);
    near.get(k).push(p);
  }
  const liftAt = (x, y) => {
    if (!near.size) return null;
    let best = null, bd = LIFT_REACH;
    for (let ix = Math.floor((x - LIFT_REACH) / LC); ix <= Math.floor((x + LIFT_REACH) / LC); ix++) {
      for (let iy = Math.floor((y - LIFT_REACH) / LC); iy <= Math.floor((y + LIFT_REACH) / LC); iy++) {
        for (const p of near.get(ix * 2000003 + iy) || []) { const d = Math.hypot(p.x - x, p.y - y); if (d <= bd) { bd = d; best = p; } }
      }
    }
    return best;
  };
  const r2 = (v) => Math.round(v * 100) / 100;
  return { over, low, drops: places.filter((d) => !impossible.includes(d)).map(round), impossible: impossible.map(round), ceilings, normal,
    lifts: lifts.map((d) => ({ x: Math.round(d.x), y: Math.round(d.y), from: r2(d.from), to: r2(d.to), mh: d.mh, points: d.points })), liftAt };
}
