// SPDX-License-Identifier: AGPL-3.0-or-later
// The structures: our tunnels through rock, the road tunnels' portals and the ground fitted to their mouths, the
// track's support, the bridges and the retaining walls.
import * as THREE from 'three';
import { weatherize, wetFactor } from './weather.js';
import { ChunkedGeometry, GROUND_SNOW, STREET_SNOW, W, densify } from './worldMesh.js';

// Our tunnels through rock: a vault over both tracks and the road (walls to 4.8 m, an arch to 7.2 m
// over the rails), the rock above it at the lidar ground (wider than the hole cut in the terrain, a
// little above it, so the coarse terrain edge never shows a gap) and the two portal faces between the
// vault and the rock top. Every 2 m along the span.
export function buildRockTunnels(group, route, ground, rock, HW) {
  if (!rock.length) return;
  const T = ground.terrain, pr = ground.profile;
  // outside (the portals and the rock top) wet and snowy in the weather; the vault and the floor inside dry
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#8b8475', '#6b6559'), snow: GROUND_SNOW }), { color: true });
  const inner = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { color: true });
  const stone = new THREE.Color('#8b8475').toArray(), vault = new THREE.Color('#5d5a52').toArray();
  const top = new THREE.Color('#6f7a55').toArray();
  const P = (s, lat, z) => { const o = route.offset(s, lat); return W(o.x, o.y, z); };
  const rockTop = (s, l) => { const o = route.offset(s, l); return Math.max(T.height(o.x, o.y) + 0.05, pr.height(s) + 9); };
  for (const [a, b] of rock) {
    // the walls where the surveyed tunnel floor ends (underground DTM areas: the Vyšehrad tunnel is
    // 1.5 m right of our track to 8 m left of it), else ±HW
    let lo = Infinity, hi = -Infinity;
    for (const u of ground.dtm?.under || []) for (const [x, y] of u.ring) {
      const n = route.nearest(x, y);
      if (!n || n.s < a - 5 || n.s > b + 5 || n.d > 20) continue;
      const q = route.at(n.s), lat = q.hx * (y - q.y) - q.hy * (x - q.x);
      lo = Math.min(lo, lat); hi = Math.max(hi, lat);
    }
    if (!(hi - lo > 4)) { lo = -HW; hi = HW; } else { lo -= 0.3; hi += 0.3; }
    // (the Vyšehrad tunnel: a stone semicircle springing low over the whole width, user photo)
    const c0 = (lo + hi) / 2, half = (hi - lo) / 2, rise = Math.min(half, 5), spring = 2.5;
    // the vault's cross-section: lateral offset and height over the rails
    const prof = [[lo, -0.3], [lo, spring]];
    for (let k = 1; k < 12; k++) { const t = Math.PI - (k / 12) * Math.PI; prof.push([c0 + half * Math.cos(t), spring + rise * Math.sin(t)]); }
    prof.push([hi, spring], [hi, -0.3]);
    const R0 = lo - 10, R1 = hi + 10; // the rock top reaches past the hole in the terrain
    const n = Math.max(2, Math.ceil((b - a) / 2));
    for (let k = 0; k < n; k++) {
      const s0 = a + ((b - a) * k) / n, s1 = a + ((b - a) * (k + 1)) / n, z0 = pr.height(s0), z1 = pr.height(s1);
      const c = cg._chunk(route.at(s0).x, route.at(s0).y), ci = inner._chunk(route.at(s0).x, route.at(s0).y);
      for (let i = 0; i < prof.length - 1; i++) {
        const [l0, h0] = prof[i], [l1, h1] = prof[i + 1];
        inner.quad(ci, P(s0, l0, z0 + h0), P(s1, l0, z1 + h0), P(s1, l1, z1 + h1), P(s0, l1, z0 + h1), vault);
      }
      for (let lat = R0; lat < R1; lat += 2) {
        cg.quad(c, P(s0, lat, rockTop(s0, lat)), P(s0, lat + 2, rockTop(s0, lat + 2)), P(s1, lat + 2, rockTop(s1, lat + 2)), P(s1, lat, rockTop(s1, lat)), top);
      }
    }
    // portals: from each vault point up to the rock top above it, and the rock face beside them
    for (const s of [a, b]) {
      const z = pr.height(s), c = cg._chunk(route.at(s).x, route.at(s).y);
      for (let i = 0; i < prof.length - 1; i++) {
        const [l0, h0] = prof[i], [l1, h1] = prof[i + 1];
        cg.quad(c, P(s, l0, z + h0), P(s, l1, z + h1), P(s, l1, rockTop(s, l1)), P(s, l0, rockTop(s, l0)), stone);
      }
      for (const [from, to] of [[R0, lo], [hi, R1]]) {
        for (let l = from; l < to; l += 2) {
          const l1 = Math.min(to, l + 2);
          cg.quad(c, P(s, l, z - 0.3), P(s, l1, z - 0.3), P(s, l1, rockTop(s, l1)), P(s, l, rockTop(s, l)), stone);
        }
      }
    }
  }
  // the tunnel's floor as surveyed (underground road and footway areas), at the track's height
  const floorCol = { road: new THREE.Color('#55565a').toArray(), sidewalk: new THREE.Color('#a39d90').toArray() };
  for (const u of ground.dtm?.under || []) {
    const n0 = route.nearest(u.ring[0][0], u.ring[0][1]);
    if (!n0 || n0.d > 20 || !rock.some(([a, b]) => n0.s > a - 10 && n0.s < b + 10)) continue;
    const ring = u.ring.map((p) => new THREE.Vector2(p[0], p[1]));
    let tris;
    try { tris = THREE.ShapeUtils.triangulateShape(ring, []); } catch { continue; }
    const lift = u.c === 'sidewalk' || u.c === 'island' ? 0.3 : 0.12, col = floorCol[u.c === 'road' ? 'road' : 'sidewalk'];
    const z = (p) => { const n = route.nearest(p.x, p.y); return (n ? pr.height(n.s) : pr.height(n0.s)) + lift; };
    for (const [i, j, k] of tris) {
      const A = ring[i], B = ring[j], C = ring[k];
      inner.tri(inner._chunk(A.x, A.y), W(A.x, A.y, z(A)), W(B.x, B.y, z(B)), W(C.x, C.y, z(C)), null, col);
    }
  }
  cg.build(group, 'support');
  inner.build(group, 'support');
  console.log(`rock tunnels: ${rock.map(([a, b]) => `${Math.round(a)}-${Math.round(b)}`).join(', ')}`);
}

// Road tunnels away from our track (Letenský tunel): the cars run below ground. At each end that is
// not another tunnel way, a mouth: a portal frame and a THROAT_D m deep dark tube into the hill
// (floor, walls, flat roof, darker inward, a black end far in), so cars drive out of darkness (a flat
// dark quad at the mouth read as an opaque wall). The terrain cells over a mouth are cut out
// (buildTerrain's hole) and covered again at 2-3 m: over the throat at least 0.6 m above its roof,
// in front of it down to the road; a headwall above the lintel reaches up to the hill.
const THROAT_D = 24, THROAT_H = 5.2;
export function roadPortalMouths(list) {
  const key = (p) => `${p[0]},${p[1]}`, ends = new Map(), out = [];
  for (const { r } of list) for (const p of [r.p[0], r.p[r.p.length - 1]]) ends.set(key(p), (ends.get(key(p)) || 0) + 1);
  for (const { r, tf, L } of list) {
    const D = Math.min(THROAT_D, L / 2);
    for (const end of [0, 1]) {
      const i = end ? r.p.length - 1 : 0, j = end ? r.p.length - 2 : 1, p = r.p[i];
      if (ends.get(key(p)) > 1) continue; // the tunnel goes on as the next way
      const w0 = r.way || r.p, at0 = key(w0[0]) === key(p) ? 0 : key(w0[w0.length - 1]) === key(p) ? 1 : -1;
      if (at0 < 0 || (w0.open && !w0.open[at0])) continue; // (past the edge of the imported roads: no portal)
      const dx = r.p[j][0] - p[0], dy = r.p[j][1] - p[1], l = Math.hypot(dx, dy) || 1;
      const hx = dx / l, hy = dy / l, nx = -hy, ny = hx, w = r.w / 2 + 0.8;
      // local frame: d inward along the tunnel, lat across
      const loc = (x, y) => [(x - p[0]) * hx + (y - p[1]) * hy, (x - p[0]) * nx + (y - p[1]) * ny];
      const zAt = (d) => tf(p[0] + hx * Math.max(0, d), p[1] + hy * Math.max(0, d));
      out.push({
        p, hx, hy, nx, ny, w, zAt, loc, D,
        // within the mouth's cut (pad: m around it)
        has(x, y, pad = 0) { const [d, lat] = loc(x, y); return d > -4 - pad && d < D + 2 + pad && Math.abs(lat) < w + 2 + pad; },
      });
    }
  }
  return out;
}
// The survey's street areas around a mouth often take the portal's crown into their outline (a road
// area at the Letenský tunel ran 191-206 m: a grey ramp across the opening). Inside a mouth's
// footprint, street vertices above the tunnel road come down onto it (in place: the height lookup
// holds the same points). Lawns and the hill over the throat are left alone.
const MOUTH_FIT = new Set(['road', 'parking', 'paved', 'sidewalk', 'cycle', 'island', 'median', 'tram']);
// The same for the ground file (#509): its street vertices inside a mouth's footprint over the tunnel road come down onto
// it, in the lookup (its survey street triangles' vertices) and then every drawn vertex at one of those points, whatever
// its group, tile by tile as they come (#30): the file is one welded surface, a lawn, a bed or a step's wall shares a street's vertex there, and drawn on
// its own it kept that corner up, a crack, cars and walkers standing 2.5-17.7 m off what was drawn (#632: groundDrawn
// at the Strahov tunnel's mouths, lines 9, 17, 22, 23). Only the squares and cells near a mouth are read.
const MOUTH_NEAR = 0.005; // m: a drawn vertex (32-bit) this near a moved one in plan and height is it
export function mouthFix(mouths) {
  if (!mouths.length) return null;
  const into = (x, y, z) => {
    for (const m of mouths) {
      const [d, lat] = m.loc(x, y);
      if (d < -3 || d > m.D || Math.abs(lat) > m.w + 1.5) continue;
      const zt = m.zAt(d) + 0.05;
      if (z > zt + 0.3) return zt;
    }
    return null;
  };
  const boxes = mouths.map((m) => { const r = m.D + m.w + 5; return [m.p[0] - r, m.p[1] - r, m.p[0] + r, m.p[1] + r]; });
  // the points moved: 2 cm cells -> [x, y, z before, z after]
  const moved = new Map(), C = 0.02, key = (i, j) => i * 1048576 + j;
  const fix = { points: 0, drawn: 0 };
  // a tile's lookup: its street points in a mouth come down (each point once, whichever tile held it first)
  fix.lookup = (lk) => {
    const done = new Set();
    for (const [bx0, by0, bx1, by1] of boxes) {
      const i0 = Math.max(0, Math.floor((bx0 - lk.x0) / lk.cell)), i1 = Math.min(lk.nx - 1, Math.floor((bx1 - lk.x0) / lk.cell));
      const j0 = Math.max(0, Math.floor((by0 - lk.y0) / lk.cell)), j1 = Math.min(lk.ny - 1, Math.floor((by1 - lk.y0) / lk.cell));
      for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) {
        const k = j * lk.nx + i;
        for (let s = lk.start[k], e = lk.start[k + 1]; s < e; s++) {
          const t = lk.tris[s];
          if (!MOUTH_FIT.has(lk.areas[lk.ta[t]])) continue;
          for (let c = 0; c < 3; c++) {
            const v = lk.tv[3 * t + c];
            if (done.has(v)) continue;
            done.add(v);
            const x = lk.vx[v] + lk.x0, y = lk.vy[v] + lk.y0, z = into(x, y, lk.vz[v]);
            if (z === null) continue;
            const kk = key(Math.round(x / C), Math.round(y / C)), at = moved.get(kk) || [];
            if (!at.some((q) => Math.abs(q[0] - x) <= MOUTH_NEAR && Math.abs(q[1] - y) <= MOUTH_NEAR && Math.abs(q[2] - lk.vz[v]) <= MOUTH_NEAR)) {
              at.push([x, y, lk.vz[v], z]);
              moved.set(kk, at);
              fix.points++;
            }
            lk.vz[v] = z;
          }
        }
      }
    }
  };
  // a tile's mesh arrays (positions from its corner [bx, by]): every drawn vertex at a moved point follows it
  fix.meshes = (ms, [bx, by]) => {
    if (!moved.size) return;
    for (const mesh of ms) {
      const P = mesh.pos;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (let v = 0; v < P.length; v += 3) { const x = P[v] + bx, y = by - P[v + 2]; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      if (!boxes.some((q) => q[0] <= x1 && q[2] >= x0 && q[1] <= y1 && q[3] >= y0)) continue;
      for (let v = 0; v < P.length; v += 3) {
        const x = P[v] + bx, y = by - P[v + 2], z = P[v + 1], ci = Math.round(x / C), cj = Math.round(y / C);
        let to = null;
        for (let a = -1; a <= 1 && to === null; a++) for (let b = -1; b <= 1 && to === null; b++) {
          for (const q of moved.get(key(ci + a, cj + b)) || []) {
            if (Math.abs(q[0] - x) <= MOUTH_NEAR && Math.abs(q[1] - y) <= MOUTH_NEAR && Math.abs(q[2] - z) <= MOUTH_NEAR) { to = q[3]; break; }
          }
        }
        if (to !== null) { P[v + 1] = to; fix.drawn++; }
      }
    }
  };
  return fix;
}
export function fitDtmToMouths(dtm, mouths) {
  if (!mouths.length || dtm.mouthsFitted) return;
  dtm.mouthsFitted = true;
  const seen = new Set();
  let n = 0;
  // (each mouth's reach as a box in plan; an area whose outline lies outside every box has no vertex to bring
  // down: the millions of others were tested against every mouth, #244)
  const boxes = mouths.map((m) => {
    const xs = [], ys = [], l = m.w + 1.5;
    for (const d of [-3, m.D]) for (const t of [-l, l]) { xs.push(m.p[0] + d * m.hx + t * m.nx); ys.push(m.p[1] + d * m.hy + t * m.ny); }
    return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
  });
  for (const a of dtm.areas) {
    if (a.l !== 0 || !MOUTH_FIT.has(a.c)) continue;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of a.ring) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    if (!boxes.some((b) => x0 <= b[2] + 1e-6 && x1 >= b[0] - 1e-6 && y0 <= b[3] + 1e-6 && y1 >= b[1] - 1e-6)) continue;
    for (const p of [...a.ring, ...a.holes.flat(), ...a.mesh.flat()]) {
      if (seen.has(p)) continue;
      seen.add(p);
      for (const m of mouths) {
        const [d, lat] = m.loc(p[0], p[1]);
        if (d < -3 || d > m.D || Math.abs(lat) > m.w + 1.5) continue;
        const z = m.zAt(d) + 0.05;
        if (p[2] > z + 0.3) { p[2] = z; n++; }
      }
    }
  }
  if (n) console.log(`survey points brought down into tunnel mouths: ${n}`);
}
export function buildRoadPortals(group, mouths, T) {
  if (!mouths.length) return;
  // (the frame wet in the weather, no snow in the throat; the floor inside stays dry)
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#9a958a', '#77736b') }), { color: true });
  const floorCg = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true }), { color: true });
  const frame = new THREE.Color('#9a958a').toArray(), lining = new THREE.Color('#6d6a64');
  const asphalt = new THREE.Color('#55565a'), black = new THREE.Color('#050506');
  const earth = new THREE.Color('#6f8a4e').toArray();
  const fade = (c, d, D) => c.clone().lerp(black, Math.min(1, Math.pow(d / D, 0.6))).toArray();
  for (const m of mouths) {
    const { p, hx, hy, nx, ny, w, D } = m;
    const at = (lat, d, h) => W(p[0] + nx * lat + hx * d, p[1] + ny * lat + hy * d, m.zAt(d) + h);
    const c = cg._chunk(p[0], p[1]), fc = floorCg._chunk(p[0], p[1]);
    // the throat, 2 m rings
    for (let d = 0; d < D; d += 2) {
      const e = Math.min(D, d + 2), col = fade(lining, d + 1, D);
      floorCg.quad(fc, at(-w, d, 0.12), at(-w, e, 0.12), at(w, e, 0.12), at(w, d, 0.12), fade(asphalt, d + 1, D));
      cg.quad(c, at(-w, d, 0), at(-w, e, 0), at(-w, e, THROAT_H), at(-w, d, THROAT_H), col);
      cg.quad(c, at(w, d, 0), at(w, e, 0), at(w, e, THROAT_H), at(w, d, THROAT_H), col);
      cg.quad(c, at(-w, d, THROAT_H), at(w, d, THROAT_H), at(w, e, THROAT_H), at(-w, e, THROAT_H), col);
    }
    cg.quad(c, at(-w, D, 0), at(w, D, 0), at(w, D, THROAT_H), at(-w, D, THROAT_H), black.toArray());
    // the frame: lintel and jambs, the headwall above the lintel up to the hill over the mouth
    const W2 = w + 1.5;
    let top = 6.6;
    for (const lat of [-W2, 0, W2]) {
      const x = p[0] + nx * lat + hx, y = p[1] + ny * lat + hy;
      top = Math.max(top, Math.max(T.height(x, y), m.zAt(1) + THROAT_H + 0.6) - m.zAt(0) + 0.3);
    }
    cg.quad(c, at(-W2, 0, THROAT_H), at(W2, 0, THROAT_H), at(W2, 0, top), at(-W2, 0, top), frame);
    for (const sd of [-1, 1]) cg.quad(c, at(sd * w, 0, -0.2), at(sd * W2, 0, -0.2), at(sd * W2, 0, top), at(sd * w, 0, top), frame);
  }
  cg.build(group, 'support');
  floorCg.build(group, 'road');
  // the cover over the terrain cells buildTerrain left out
  const cov = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#6f8a4e', '#5e7346'), snow: GROUND_SNOW }), { color: true });
  const pad = Math.hypot(T.dx, T.dy) / 2, seen = new Set();
  const coverZ = (x, y) => {
    let z = T.height(x, y);
    for (const m of mouths) {
      const [d, lat] = m.loc(x, y);
      if (Math.abs(lat) > m.w + 2) continue;
      if (d >= 0 && d < m.D + 2) z = Math.max(z, m.zAt(d) + THROAT_H + 0.6);
      else if (d < 0 && d > -4) z = Math.min(z, m.zAt(0) - 0.3);
    }
    return z;
  };
  for (const m of mouths) {
    for (let d = -4 - pad; d < m.D + 2 + pad; d += 2) for (let lat = -m.w - 2 - pad; lat < m.w + 2 + pad; lat += 2) {
      const x = m.p[0] + m.hx * d + m.nx * lat, y = m.p[1] + m.hy * d + m.ny * lat;
      const i = Math.floor((x - T.x0) / T.dx), j = Math.floor((y - T.y0) / T.dy);
      if (i < 0 || j < 0 || i >= T.nx - 1 || j >= T.ny - 1 || seen.has(j * T.nx + i)) continue;
      const cx = T.x0 + (i + 0.5) * T.dx, cy = T.y0 + (j + 0.5) * T.dy;
      if (!mouths.some((q) => q.has(cx, cy, pad))) continue;
      seen.add(j * T.nx + i);
      const n = 5, x0 = T.x0 + i * T.dx, y0 = T.y0 + j * T.dy, sx = T.dx / n, sy = T.dy / n, ch = cov._chunk(cx, cy);
      const P = (u, v) => { const X = x0 + u * sx, Y = y0 + v * sy; return W(X, Y, coverZ(X, Y)); };
      for (let a = 0; a < n; a++) for (let b = 0; b < n; b++) cov.quad(ch, P(a, b), P(a, b + 1), P(a + 1, b + 1), P(a + 1, b), earth);
    }
  }
  cov.build(group);
  console.log(`road tunnel mouths: ${mouths.length}, terrain cells re-covered: ${seen.size}`);
}

// What carries our tracks where they stand above the ground drawn beside them (approach ramps of
// the bridges whose survey or model stops short, an embankment over a lower street): off the bridges,
// walls from the bed down to the ground at the outer bed edges and a top between the two tracks; on
// our bridges, a 0.8 m deck under the beds where the ground is far below. Every 2 m along the route.
export function buildTrackSupport(group, route, ground) {
  const { profile, dtm, terrain } = ground;
  const below = (x, y) => { const t = dtm?.surfaceAt(x, y); return t ? t.z : terrain.height(x, y); };
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { wet: wetFactor('#8a8376', '#6d675d'), snow: GROUND_SNOW }), { color: true });
  const stone = new THREE.Color('#8a8376').toArray(), ballast = new THREE.Color('#77736a').toArray();
  const edges = (s) => {
    let lo = 0, hi = 0;
    for (let lat = -6; lat <= 6; lat += 0.25) { const o = route.offset(s, lat); if (ground.trackWithin(o.x, o.y, 0.2)) { lo = Math.min(lo, lat); hi = Math.max(hi, lat); } }
    return [lo - 1.4, hi + 1.4];
  };
  let prev = null, walls = 0;
  for (let s = 0; s <= route.length; s += 2) {
    const [lo, hi] = edges(s), bridge = profile.onBridge(s), zb = profile.height(s) - profile.lift(s);
    const zL = profile.heightAt(s, hi) - profile.lift(s, hi), zR = profile.heightAt(s, lo) - profile.lift(s, lo); // (each edge at its track's level, #197)
    const L = route.offset(s, hi), R = route.offset(s, lo);
    const gL = below(L.x, L.y), gR = below(R.x, R.y), C = route.at(s), gC = below(C.x, C.y);
    const cur = { s, zb, zL, zR, L, R, gL, gR, bridge, need: bridge ? Math.max(zL, zR) - Math.min(gL, gR, gC) > 1 : Math.max(zL - gL, zR - gR) > 0.6 };
    if (prev && prev.need && cur.need) {
      const c = cg._chunk(L.x, L.y);
      const P = (o, z) => W(o.x, o.y, z);
      // top (ballast) between the outer bed edges, just under the beds
      cg.quad(c, P(prev.R, prev.zR - 0.03), P(R, cur.zR - 0.03), P(L, cur.zL - 0.03), P(prev.L, prev.zL - 0.03), ballast);
      const footL = bridge ? cur.zL - 0.8 : Math.min(cur.zL, gL) - 0.1, footLp = prev.bridge ? prev.zL - 0.8 : Math.min(prev.zL, prev.gL) - 0.1;
      const footR = bridge ? cur.zR - 0.8 : Math.min(cur.zR, gR) - 0.1, footRp = prev.bridge ? prev.zR - 0.8 : Math.min(prev.zR, prev.gR) - 0.1;
      cg.quad(c, P(prev.L, footLp), P(L, footL), P(L, cur.zL), P(prev.L, prev.zL), stone);
      cg.quad(c, P(prev.R, footRp), P(R, footR), P(R, cur.zR), P(prev.R, prev.zR), stone);
      if (bridge) cg.quad(c, P(prev.L, footLp), P(prev.R, footRp), P(R, footR), P(L, footL), stone);
      walls++;
    }
    prev = cur;
  }
  cg.build(group, 'support');
  console.log(`track support: ${walls * 2} m`);
}

// Deck, parapets and piers for bridges on the route (e.g. Most Legií).
export function buildBridges(group, data, route, ground) {
  const sideMat = new THREE.MeshLambertMaterial({ color: 0x7f786c });
  const cg = new ChunkedGeometry(weatherize(new THREE.MeshLambertMaterial({ vertexColors: true }), { snow: STREET_SNOW, slush: true }), { color: true });
  const deckCol = new THREE.Color('#8f897e').toArray(), sideCol = new THREE.Color('#7a7366').toArray();
  for (const [s0, s1] of data.bridges) {
    // a real 3D model of this bridge (Mosty 3D) replaces the synthetic deck
    const real = (ground.profile.realDecks || []).reduce((acc, [a, b]) => acc + Math.max(0, Math.min(b, s1) - Math.max(a, s0)), 0);
    if (real > (s1 - s0) * 0.5) continue;
    const halfW = 9;
    const pts = [];
    for (let s = s0 - 2; s <= s1 + 2; s += 3) {
      const o = route.at(s), h = route.heading(s, 3), z = ground.profile.height(s);
      pts.push({ x: o.x, y: o.y, nx: -h.hy, ny: h.hx, z });
    }
    const c = cg._chunk(pts[0].x, pts[0].y);
    for (let i = 0; i < pts.length - 1; i++) {
      const p = pts[i], q = pts[i + 1];
      for (const side of [1, -1]) {
        const pa = [p.x + p.nx * halfW * side, p.y + p.ny * halfW * side], qa = [q.x + q.nx * halfW * side, q.y + q.ny * halfW * side];
        // fascia from deck down 1.6 m and parapet up 1.1 m
        cg.quad(c, W(pa[0], pa[1], p.z - 1.6), W(qa[0], qa[1], q.z - 1.6), W(qa[0], qa[1], q.z + 1.1), W(pa[0], pa[1], p.z + 1.1), sideCol);
        cg.quad(c, W(qa[0], qa[1], q.z - 1.6), W(pa[0], pa[1], p.z - 1.6), W(pa[0], pa[1], p.z + 1.1), W(qa[0], qa[1], q.z + 1.1), sideCol);
      }
      // deck underside
      const l0 = [p.x + p.nx * halfW, p.y + p.ny * halfW], r0 = [p.x - p.nx * halfW, p.y - p.ny * halfW];
      const l1 = [q.x + q.nx * halfW, q.y + q.ny * halfW], r1 = [q.x - q.nx * halfW, q.y - q.ny * halfW];
      cg.quad(c, W(l0[0], l0[1], p.z - 1.6), W(l1[0], l1[1], q.z - 1.6), W(r1[0], r1[1], q.z - 1.6), W(r0[0], r0[1], p.z - 1.6), deckCol);
      cg.quad(c, W(r0[0], r0[1], p.z + 0.1), W(r1[0], r1[1], q.z + 0.1), W(l1[0], l1[1], q.z + 0.1), W(l0[0], l0[1], p.z + 0.1), deckCol);
    }
    // piers every ~45 m
    for (let s = s0 + 30; s < s1 - 15; s += 45) {
      const o = route.at(s), z = ground.profile.height(s);
      const zg = ground.terrain.height(o.x, o.y) - 2;
      const pier = new THREE.Mesh(new THREE.BoxGeometry(4, Math.max(1, z - 1.6 - zg), 16), sideMat);
      const h = route.heading(s, 3);
      pier.position.set(o.x, (z - 1.6 + zg) / 2, -o.y);
      pier.rotation.y = Math.atan2(h.hx, -h.hy);
      group.add(pier);
    }
  }
  cg.build(group);
}

// Retaining walls where the track is cut into a hillside (e.g. Chotkova), with a flat cap
// covering the terrain lowered behind them.
export function buildWalls(group, data, route, ground) {
  const cg = new ChunkedGeometry(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), { color: true });
  const stone = new THREE.Color('#8a8172').toArray(), coping = new THREE.Color('#9c968a').toArray(), cap = new THREE.Color('#6f7d55').toArray();
  // real retaining walls (IPR Praha): line + height
  const realPts = new Map();
  const key = (x, y) => `${Math.floor(x / 8)},${Math.floor(y / 8)}`;
  for (const w of data.geo?.walls || []) {
    const line = densify(w.p, 2);
    const c = cg._chunk(line[0][0], line[0][1]);
    const half = 0.25;
    const edge = line.map((p, i) => {
      const a = line[Math.max(0, i - 1)], b = line[Math.min(line.length - 1, i + 1)];
      const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
      const nx = -dy / l, ny = dx / l;
      const g1 = ground.at(p[0] + nx * 1.5, p[1] + ny * 1.5), g2 = ground.at(p[0] - nx * 1.5, p[1] - ny * 1.5);
      const bottom = Math.min(g1, g2) - 0.4, top = Math.max(Math.max(g1, g2) + 0.3, bottom + 0.4 + w.h);
      realPts.set(key(p[0], p[1]), true);
      return { L: [p[0] + nx * half, p[1] + ny * half], R: [p[0] - nx * half, p[1] - ny * half], bottom, top };
    });
    for (let i = 0; i < edge.length - 1; i++) {
      const a = edge[i], b = edge[i + 1];
      for (const side of ['L', 'R']) {
        cg.quad(c, W(...a[side], a.bottom), W(...b[side], b.bottom), W(...b[side], b.top), W(...a[side], a.top), stone);
      }
      cg.quad(c, W(...a.L, a.top), W(...b.L, b.top), W(...b.R, b.top), W(...a.R, a.top), coping);
    }
  }
  const nearReal = (x, y) => {
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) if (realPts.has(`${Math.floor(x / 8) + i},${Math.floor(y / 8) + j}`)) return true;
    return false;
  };
  const runs = ground.walls?.runs || [];
  const B = ground.walls.bench, Rch = ground.walls.reach + 3;
  for (const run of runs) {
    if (run.pts.length < 2) continue;
    const c = cg._chunk(...(() => { const o = route.at(run.pts[0].s); return [o.x, o.y]; })());
    for (let i = 0; i < run.pts.length - 1; i++) {
      const a = run.pts[i], b = run.pts[i + 1];
      const za = ground.profile.height(a.s), zb = ground.profile.height(b.s);
      const fa = route.offset(a.s, run.side * B), fb = route.offset(b.s, run.side * B);
      const ka = route.offset(a.s, run.side * (B + 0.5)), kb = route.offset(b.s, run.side * (B + 0.5));
      const ca = route.offset(a.s, run.side * Rch), cb = route.offset(b.s, run.side * Rch);
      // wall face (unless a real surveyed wall stands here)
      if (!nearReal(fa.x, fa.y)) cg.quad(c, W(fa.x, fa.y, za - 0.3), W(fb.x, fb.y, zb - 0.3), W(fb.x, fb.y, b.top), W(fa.x, fa.y, a.top), stone);
      // coping stones and the cap of hillside behind the wall
      cg.quad(c, W(fa.x, fa.y, a.top + 0.15), W(fb.x, fb.y, b.top + 0.15), W(kb.x, kb.y, b.top + 0.15), W(ka.x, ka.y, a.top + 0.15), coping);
      cg.quad(c, W(fa.x, fa.y, a.top), W(fb.x, fb.y, b.top), W(fb.x, fb.y, b.top + 0.15), W(fa.x, fa.y, a.top + 0.15), coping);
      cg.quad(c, W(ka.x, ka.y, a.top + 0.05), W(kb.x, kb.y, b.top + 0.05), W(cb.x, cb.y, b.top + 0.05), W(ca.x, ca.y, a.top + 0.05), cap);
    }
  }
  cg.build(group);
}
