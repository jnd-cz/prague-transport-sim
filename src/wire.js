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
const SAME_LEVEL = 3;              // m: a low point lowers the wires of tracks within this of its own rail height
const LOW_STEP = 0.5, BESIDE = 6;  // m: the tracks are read for structures this often; within BESIDE m of a low point the wire keeps its height, not its height over the rails
const CELL = 0.5, FAR = 512;

// The structures' points over the tracks, by 0.5 m cell (each point once to 0.1 m in plan and 5 cm in height): what a
// wire must pass under.
export class Ceilings {
  constructor() { this.cells = new Map(); this.seen = new Set(); this.count = 0; }

  add(x, y, z) {
    const id = `${Math.round(x * 10)},${Math.round(y * 10)},${Math.round(z * 20)}`;
    if (this.seen.has(id)) return;
    this.seen.add(id);
    const k = Math.floor(x / CELL) * 2000003 + Math.floor(y / CELL);
    let c = this.cells.get(k);
    if (!c) this.cells.set(k, (c = []));
    c.push(x, y, z);
    this.count++;
  }

  // the lowest point within r m of (x, y) in plan between the heights z0 and z1, or null
  lowest(x, y, z0, z1, r = COLLECTOR) {
    let low = null;
    for (let ix = Math.floor((x - r) / CELL); ix <= Math.floor((x + r) / CELL); ix++) {
      for (let iy = Math.floor((y - r) / CELL); iy <= Math.floor((y + r) / CELL); iy++) {
        const c = this.cells.get(ix * 2000003 + iy);
        if (!c) continue;
        for (let n = 0; n < c.length; n += 3) {
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
// track's height is off there: `impossible` lists it, and its wire stays at its normal height.
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
  return { over, low, drops: places.filter((d) => !impossible.includes(d)).map(round), impossible: impossible.map(round), ceilings, normal };
}
