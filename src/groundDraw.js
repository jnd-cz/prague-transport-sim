// SPDX-License-Identifier: AGPL-3.0-or-later
// The ground drawn: the ground file's tiles in the materials of the layers they replace (src/groundFile.js brings
// them), and the survey's decks and roofs over it, the decks of our bridges laid to the track.
import * as THREE from 'three';
import { DTM_LIFT } from './terrain.js';
import { STREET_BELOW } from './heights.js';
import { weatherize, wetFactor } from './weather.js';
import { GFX } from './gfx.js';
import { ChunkedGeometry, FOOT_SNOW, GROUND_SNOW, STREET_SNOW, W } from './worldMesh.js';

// The DTM areas as meshes: ground-level surfaces draped on their surveyed heights (sidewalks,
// islands and platforms with a kerb face down to the road), level 1 (bridge decks, railway on
// the bridge, canopies) as slabs with sides and an underside.
const DTM_COLORS = {
  road: '#55565a', parking: '#5e5f63', cycle: '#7d5a52', tram: '#6c675d', sidewalk: '#a39d90', island: '#9b968a', median: '#9b968a',
  platform: '#b3ad9f', paved: '#9b968b', stairs: '#aaa59a', green: '#6f8a4e', water: '#5d7f95', deck: '#8f897e',
  rail: '#6a6258', roof: '#5f6266', wall: '#8a8172',
};
// with the ground file (#509) the streets are its own: the decks of our bridges alone
export function flushDtm(ground) {
  const dtm = ground.dtm;
  if (dtm.flushed) return; // kept across weather rebuilds
  dtm.flushed = true;
  const done = new Set();
  const { route, profile } = ground;
  // The surveyed decks of our own bridges carry the tracks: laid to the track profile the same way
  // (each area's offset at the route, full within 8 m, fading out by 15 m; crossfall kept), so the
  // cars beside the tram drive on the deck at the rails' level. Measured first, then moved. (One offset
  // for every area, from the deck nearest the rails, left the bridge's outline (class deck) 0.2-0.47 m over
  // the carriageway it overlaps on Čechův most and Trojský most once the rails followed DI, #197: each area
  // takes its own, the outline 2 cm under the street.)
  const deckMoves = [], own = new Map();
  const ownAt = (a, ai, s, x, y, zt) => {
    const key = `${ai}:${Math.round(s)}`;
    if (own.has(key)) return own.get(key);
    let z = null;
    for (const [A, B, C] of a.mesh) {
      const d = (B[0] - A[0]) * (C[1] - A[1]) - (B[1] - A[1]) * (C[0] - A[0]);
      if (Math.abs(d) < 1e-9) continue;
      const u = ((B[0] - x) * (C[1] - y) - (B[1] - y) * (C[0] - x)) / d, v = ((C[0] - x) * (A[1] - y) - (C[1] - y) * (A[0] - x)) / d;
      if (u < -1e-6 || v < -1e-6 || u + v > 1 + 1e-6) continue;
      const zz = u * A[2] + v * B[2] + (1 - u - v) * C[2];
      if (Math.abs(zz - zt) <= 2.5 && (z === null || Math.abs(zz - zt) < Math.abs(z - zt))) z = zz;
    }
    own.set(key, z);
    return z;
  };
  dtm.areas.forEach((a, ai) => {
    if (a.l < 1) return;
    for (const p of [...a.ring, ...a.holes.flat(), ...a.mesh.flat()]) {
      if (done.has(p)) continue;
      done.add(p);
      const n = route.nearest(p[0], p[1]);
      if (!n || n.d >= 15 || !profile.onBridge(n.s)) continue;
      const q = route.at(n.s), zt = profile.height(n.s) - profile.lift(n.s) - STREET_BELOW - (a.c === 'deck' ? 0.02 : 0);
      // (a walkway with no deck under the route's axis, own or another's, within 2.5 m of the deck takes no offset but is
      // still laid below (WALK): on Krejcárek's north end, s 3458-3496, the survey has no deck under our track, and its
      // tram strip 1.5-4.3 m left of it, from the deck up to the parapet's top, stood 0.37 m over the rails, #594)
      const walk = a.c === 'tram' || a.c === 'paved' || a.c === 'sidewalk';
      const zr = ownAt(a, ai, n.s, q.x, q.y, zt) ?? dtm.deckAt(q.x, q.y, zt, 2.5) ?? (walk && Math.abs(p[2] - zt) <= 2.5 ? zt : null);
      if (zr === null) continue;
      const k = Math.max(0, Math.min(1, (n.d - 8) / 7));
      deckMoves.push([p, (zt - zr) * (1 - k * k * (3 - 2 * k)), n, a.c]);
    }
  });
  // A tram area of the deck lies at the rails' level: a vertex of one within 8 m that still stands more than DECK_OVER m
  // over the rail heads at its place is the parapet's or the railing's top taken as the surface, laid to the deck's
  // surface there. (On line 37's Krejcárek viaduct the survey's tram areas along the deck's edge, 1.5-4.4 m right of our
  // track, stepped up to 0.9-1.3 m over the rails half a metre out from it: their triangles stood over the deck as grey
  // slabs, #549.) The same holds for the walkways on the deck: on line 17's track-only bridge at Modřanská škola the
  // survey's paved strip 0.61 m over the rails is the parapet wall (maintainer, #549). On a deck with a carriageway a sidewalk standing more than DECK_OVER m over the rails is laid to an
  // ordinary kerb, KERB m over the deck: Čechův most's, 0.66-0.73 m in the survey, is an ordinary sidewalk a little
  // over the road and rails, with a railing at its edge (maintainer, #549).
  // A deck that carries only track (no level-1 carriageway of the survey within 8 m of the route on that span) is flat at
  // the track's level: every vertex of its tram areas within 8 m is laid there, the walkways beside the bed with them (the
  // user, 2026-11-14, #549, on the Krejcárek viaduct: "There is open ballast track in the middle, walkway a bit lower and
  // a parapet on the side. We can simplify it to flat deck at track's level and model the parapet by what's left on top").
  const DECK_OVER = 0.3, PARAPET_MIN = 0.5, PARAPET_H = [0.6, 1.3], KERB = 0.15;
  const WALK = new Set(['tram', 'paved', 'sidewalk']); // (the deck's own areas a flat deck lays and takes its parapets from)
  const spanOf = (s) => (profile.bridges || []).findIndex(([a, b]) => s >= a && s <= b);
  const roaded = new Set();
  for (const [, , n, c] of deckMoves) if (c === 'road' && n.d <= 8) roaded.add(spanOf(n.s));
  // (read by the bridge models: nothing of one stands over a flat deck)
  dtm.flatDeck = (s) => { const sp = spanOf(s); return sp >= 0 && !roaded.has(sp); };
  dtm.deckLaid = [];
  const over = new Map(), laid = new Set(); // (a laid vertex: how far its survey height stood over the deck)
  for (const [p, dz, n, c] of deckMoves) {
    p[2] += dz;
    if (!WALK.has(c) || n.d > 8) continue;
    const q = route.at(n.s), l = (p[1] - q.y) * q.hx - (p[0] - q.x) * q.hy, zr = profile.heightAt(n.s, l);
    const sp = spanOf(n.s), flat = sp >= 0 && !roaded.has(sp);
    if (!flat && (c === 'paved' || p[2] - zr <= DECK_OVER)) continue;
    const z = zr - profile.lift(n.s, l) - STREET_BELOW + (!flat && c === 'sidewalk' ? KERB : 0);
    if (p[2] - zr > DECK_OVER) {
      dtm.deckLaid.push({ x: p[0], y: p[1], s: Math.round(n.s), c, dz: Math.round((z - p[2]) * 100) / 100 });
      over.set(p, p[2] - z);
    }
    laid.add(p);
    p[2] = z;
  }
  // The parapet is what the survey had on top: a ring edge of a tram area along the route, both its ends laid from
  // PARAPET_MIN m or more over the deck and 2.5 m or more from our track, is the deck's edge under the parapet's top. It is
  // drawn as a wall that high (PARAPET_H), 0.3 m thick towards the track (the photos: a concrete parapet with a railing).
  // A deck has a parapet on both edges (the photos): where the survey kept no top on one side (Krejcárek's left, its
  // walkway flat out to the edge), that side's outermost ring edges of the laid areas get one as high as the span's
  // parapets from the survey (their median). (Edges: along the route, within 0.6 m of the outermost laid vertex in their
  // 4 m stretch and side.)
  dtm.parapets = [];
  const edges = [], outer = new Map();
  const latOf = (p) => { const n = route.nearest(p[0], p[1]); if (!n) return null; const q = route.at(n.s); return { n, l: (p[1] - q.y) * q.hx - (p[0] - q.x) * q.hy }; };
  for (const a of dtm.areas) {
    if (a.l < 1 || !WALK.has(a.c)) continue;
    for (const ring of [a.ring, ...a.holes]) for (let i = 0; i < ring.length; i++) {
      const p = ring[i], q2 = ring[(i + 1) % ring.length];
      if (!laid.has(p) || !laid.has(q2)) continue;
      const mx = (p[0] + q2[0]) / 2, my = (p[1] + q2[1]) / 2, n = route.nearest(mx, my);
      if (!n || n.d < 2.5 || !dtm.flatDeck(n.s)) continue;
      const r = route.at(n.s), ex = q2[0] - p[0], ey = q2[1] - p[1], el = Math.hypot(ex, ey) || 1e-9;
      if (Math.abs(ex * r.hx + ey * r.hy) / el < 0.9) continue; // (across the deck: an area's end, not its edge)
      const lp = latOf(p), lq = latOf(q2), side = lp.l + lq.l > 0 ? 1 : -1;
      for (const L of [lp, lq]) {
        const k = `${side}:${Math.floor(L.n.s / 4)}`;
        outer.set(k, Math.max(outer.get(k) ?? 0, Math.abs(L.l)));
      }
      edges.push({ p, q: q2, n, side, lp, lq, ix: (r.x - mx) / n.d, iy: (r.y - my) / n.d });
    }
  }
  const surveyed = [];
  for (const e of edges) if (over.get(e.p) >= PARAPET_MIN && over.get(e.q) >= PARAPET_MIN) surveyed.push(Math.min(over.get(e.p), over.get(e.q)));
  surveyed.sort((x, y) => x - y);
  const usual = surveyed.length ? surveyed[surveyed.length >> 1] : null;
  for (const e of edges) {
    const own = over.get(e.p) >= PARAPET_MIN && over.get(e.q) >= PARAPET_MIN;
    const edge = [e.lp, e.lq].every((L) => Math.abs(L.l) >= (outer.get(`${e.side}:${Math.floor(L.n.s / 4)}`) ?? 0) - 0.6);
    if (!own && !(edge && usual !== null)) continue;
    const h = Math.max(PARAPET_H[0], Math.min(PARAPET_H[1], own ? Math.min(over.get(e.p), over.get(e.q)) : usual));
    dtm.parapets.push({ p: e.p, q: e.q, h, ix: e.ix, iy: e.iy, s: Math.round(e.n.s), from: own ? 'survey' : 'other side' });
  }
}

// The parapets flushDtm found on our flat decks: a wall from the deck up to the survey's top, 0.3 m thick towards the
// track, its outer face down to the slab's underside.
function buildParapets(cg, parapets, col) {
  const T = 0.3;
  for (const { p, q, h, ix, iy } of parapets) {
    const c = cg._chunk(p[0], p[1]);
    const P = (v, k, dz) => W(v[0] + ix * T * k, v[1] + iy * T * k, v[2] + dz);
    cg.quad(c, P(p, 0, -1), P(q, 0, -1), P(q, 0, h), P(p, 0, h), col);   // (outer face)
    cg.quad(c, P(q, 1, 0), P(p, 1, 0), P(p, 1, h), P(q, 1, h), col);     // (inner face)
    cg.quad(c, P(p, 0, h), P(q, 0, h), P(q, 1, h), P(p, 1, h), col);     // (top)
  }
}

// (by weather: carriageways get slush, footways and the rest trodden snow, lawns all of it; all but
// lawns and water 0.8 darker when wet)
const DTM_KIND = { road: 'street', parking: 'street', tram: 'street', cycle: 'street', green: 'green', water: 'water' };
// The ground file's draw classes as the page colours them (#509): the colours of the layers they replace (the terrain's
// land cover in buildTerrain, the survey's DTM_COLORS, the beds' styles, the kerbs' sides), and the material groups
const TERRAIN_HEX = { '': '#8d8c80', grass: '#6f8a4e', wood: '#566f3c', water: '#5d7f95' };
// (the terrain's land class, src/weather.js landCls: grass and woods turn in autumn and do not darken in the wet,
// water takes no snow; the worker hands it on per vertex, #707)
const TERRAIN_LAND = { '': 0, grass: 1, wood: 2, water: 3 };
export const STYLE_BED_HEX = { grass: '#5d7c3a', ballast: '#6e6457', panels: '#a3a097', embedded: '#55565a', setts: '#7a7268' };
const KERB_SIDE = '#8e8a82', BED_HEX = '#77736a';
export const GROUND_GROUPS = ['terrain', 'street', 'other', 'green', 'water', 'bed'];
const RAISED_DRAW = new Set(['sidewalk', 'island', 'median', 'platform']);
// styles[class][draw name] = [group, r, g, b] (src/groundWorker.js), the terrain's and the surveyed water's with the land
// class as a fifth (the far ground draws both with the terrain's material); a wall is drawn as the face above it, a
// kerb's side grey
export function groundStyles(layout) {
  const G = (name) => GROUND_GROUPS.indexOf(name), rgb = (hex) => new THREE.Color(hex).toArray();
  const out = { terrain: {}, survey: {}, bed: { '': [G('bed'), ...rgb(BED_HEX)] }, plot: {}, wall: {} };
  for (const [k, hex] of Object.entries(TERRAIN_HEX)) out.terrain[k] = [G('terrain'), ...rgb(hex), TERRAIN_LAND[k]];
  out.plot = out.terrain; // (a building's footprint is ground, drawn by its land cover: the 3D city model's buildings stand on it, #632)
  for (const [c, hex] of Object.entries(DTM_COLORS)) out.survey[c] = [G(DTM_KIND[c] || 'other'), ...rgb(hex), ...(DTM_KIND[c] === 'water' ? [TERRAIN_LAND.water] : [])];
  for (const [k, hex] of Object.entries(STYLE_BED_HEX)) out.bed[k] = [G('bed'), ...rgb(hex)];
  const kerb = () => [G('other'), ...rgb(KERB_SIDE)];
  for (const name of [...(layout.draw?.wall || []), '']) {
    const [cls, d = ''] = name.split(':');
    const above = out[cls]?.[d] ?? out[cls]?.[''];
    out.wall[name] = cls === 'survey' && RAISED_DRAW.has(d) ? kerb() : above ? [...above] : kerb();
  }
  return out;
}
// The prebuilt ground's meshes, tile by tile as src/groundFile.js GroundTiles brings them (#30), with the materials of
// the layers they replace; a tile's positions are from its corner (the mesh stands there: 32-bit positions within 500 m)
// hole(x, y): a terrain triangle whose centre it holds is not drawn (tested in the meshes that reach a box of `near`)
export function attachGround(group, tiles, hole = null, near = []) {
  // (GFX.side: both faces, or ?gfx=front the front ones only, to measure what the back ones cost: #705)
  const mat = (opts) => weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: GFX.side }), opts);
  const mats = {
    terrain: mat({ wet: wetFactor('#8d8c80', '#77766c'), snow: GROUND_SNOW, veg: true }),
    street: mat({ wet: 0.8, snow: STREET_SNOW, slush: true }),
    other: mat({ wet: 0.8, snow: FOOT_SNOW }),
    green: mat({ snow: GROUND_SNOW }),
    water: mat({}),
    bed: mat({ wet: wetFactor(BED_HEX, '#5f5c56'), snow: STREET_SNOW, slush: true }),
  };
  const sub = new THREE.Group();
  sub.matrixAutoUpdate = false;
  group.add(sub);
  // (a tile's arrays freed once on the GPU, as uploadWorld frees the world's: kept with ?keepgeo and ?bot)
  const free = function () { this.array = null; };
  tiles.make = (ms, [bx, by]) => {
    const out = [];
    let cut = 0;
    for (const m of ms) {
      let idx = m.idx;
      if (hole && near.length && GROUND_GROUPS[m.group] === 'terrain') { // (main cut its terrain only)
        const P = m.pos;
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (let v = 0; v < P.length; v += 3) { const x = P[v] + bx, y = by - P[v + 2]; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
        if (near.some((q) => q[0] <= x1 && q[2] >= x0 && q[1] <= y1 && q[3] >= y0)) {
          const keep = new Uint32Array(idx.length);
          let n = 0;
          for (let t = 0; t < idx.length; t += 3) {
            const a = 3 * idx[t], b = 3 * idx[t + 1], c = 3 * idx[t + 2];
            if (hole(bx + (P[a] + P[b] + P[c]) / 3, by - (P[a + 2] + P[b + 2] + P[c + 2]) / 3)) { cut++; continue; }
            keep[n++] = idx[t]; keep[n++] = idx[t + 1]; keep[n++] = idx[t + 2];
          }
          idx = keep.slice(0, n);
        }
      }
      if (!idx.length) continue;
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(m.pos, 3));
      g.setAttribute('normal', new THREE.BufferAttribute(m.nor, 3));
      g.setAttribute('color', new THREE.BufferAttribute(m.col, 3));
      const kind = GROUND_GROUPS[m.group];
      if (m.cls && mats[kind].userData.weather.veg) g.setAttribute('landCls', new THREE.BufferAttribute(m.cls, 1));
      g.setIndex(new THREE.BufferAttribute(idx, 1));
      g.computeBoundingSphere();
      if (!tiles.keep) { g.userData.release = true; for (const at of Object.values(g.attributes)) at.onUpload(free); g.index.onUpload(free); }
      const mesh = new THREE.Mesh(g, mats[kind]);
      mesh.position.set(bx, 0, -by);
      mesh.updateMatrix();
      mesh.matrixAutoUpdate = false;
      mesh.userData.surface = 'ground';
      mesh.userData.surfaceKind = kind;
      sub.add(mesh);
      out.push(mesh);
    }
    if (cut) tiles.cut = (tiles.cut || 0) + cut;
    return out;
  };
  tiles.drop = (ms) => { for (const m of ms) { sub.remove(m); m.geometry.dispose(); } };
  // the far ground (#30): a tile's coarse grid in its land cover's and streets' colours, not a surface anything stands on
  tiles.makeCoarse = (c, [bx, by]) => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(c.pos, 3));
    g.setAttribute('normal', new THREE.BufferAttribute(c.nor, 3));
    g.setAttribute('color', new THREE.BufferAttribute(c.col, 3));
    if (c.cls) g.setAttribute('landCls', new THREE.BufferAttribute(c.cls, 1));
    g.setIndex(new THREE.BufferAttribute(c.idx, 1));
    g.computeBoundingSphere();
    if (!tiles.keep) { g.userData.release = true; for (const at of Object.values(g.attributes)) at.onUpload(free); g.index.onUpload(free); }
    const mesh = new THREE.Mesh(g, mats.terrain);
    mesh.position.set(bx, 0, -by);
    mesh.updateMatrix();
    mesh.matrixAutoUpdate = false;
    mesh.userData.coarseGround = true;
    sub.add(mesh);
    return mesh;
  };
  tiles.flushCoarse();
}
// The decks and roofs (level 1+): the prebuilt ground holds level 0, its kerbs and its steps' walls (#509)
export function buildDtm(group, ground) {
  const dtm = ground.dtm;
  const mat = (opts) => weatherize(new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }), opts);
  const cgs = {
    street: new ChunkedGeometry(mat({ wet: 0.8, snow: STREET_SNOW, slush: true }), { color: true }),
    other: new ChunkedGeometry(mat({ wet: 0.8, snow: FOOT_SNOW }), { color: true }),
    green: new ChunkedGeometry(mat({ snow: GROUND_SNOW }), { color: true }),
    water: new ChunkedGeometry(mat({}), { color: true }),
  };
  const color = {};
  for (const [k, v] of Object.entries(DTM_COLORS)) color[k] = new THREE.Color(v).toArray();
  const keepSurfaceRanges = /[?&](keepgeo|bot)\b/.test(location.search);
  // (a level-1 street the ground holds as the cover over a passage is drawn by the ground: no slab of its own over it,
  // whose colour and ragged outline stood as blotches on Národní divadlo's bridgehead, tools/covers.py, #824)
  const covered = new Set(ground.tiles?.layout?.covered || []);
  for (const [areaId, a] of dtm.areas.entries()) {
    if (!(a.l > 0) || covered.has(a.sourceId)) continue;
    // (surveyed walls are drawn as surveyed: a quay wall's area runs from its foot line to its top
    // line, a battered face; a wall top is flat, and its sides come from the steps below)
    // (a median under OSM's grass is grass behind its kerbs: `s`, tools/zps_medians.py, #555)
    const col = (a.c === 'median' && a.s === 'green' ? color.green : color[a.c]) || color.paved;
    const cg = cgs[DTM_KIND[a.c] || 'other'];
    const c = cg._chunk(a.ring[0][0], a.ring[0][1]);
    const startFace = c.pos.length / 9;
    // (a deck over a way with maxheight is thinner where 1 m would leave less than it and 0.1 m: tools/zps_decks.py, #445)
    const slab = a.l > 0 ? (a.c === 'roof' ? 0.3 : a.t ?? 1.0) : 0;
    const lift = a.l > 0 ? 0.02 : DTM_LIFT[a.c] ?? 0.03;
    const fz = (v) => v[2];
    for (const [p, q, r] of a.mesh) {
      // a structure over our track (a railway bridge) keeps its underside above the catenary (5 m
      // over the rails: the slab gets thinner there); anything lower inside the space the tram
      // sweeps (±3 m, 0.4 m up) is not drawn, as for the bridge models
      let under = slab;
      if (slab) {
        const mx = (p[0] + q[0] + r[0]) / 3, my = (p[1] + q[1] + r[1]) / 3, n = ground.route.nearest(mx, my);
        if (n && n.d < 3) {
          const zr = ground.profile.height(n.s), mz = (p[2] + q[2] + r[2]) / 3; // (top of rail)
          if (mz > zr + 0.4 && mz < zr + 5.3) { dtm.inEnvelope = (dtm.inEnvelope || 0) + 1; continue; }
          if (mz > zr + 0.4) under = Math.max(0.3, Math.min(slab, mz - zr - 5.0));
        }
      }
      cg.tri(c, W(p[0], p[1], fz(p) + lift), W(q[0], q[1], fz(q) + lift), W(r[0], r[1], fz(r) + lift), null, col);
      if (slab) cg.tri(c, W(p[0], p[1], p[2] - under), W(r[0], r[1], r[2] - under), W(q[0], q[1], q[2] - under), null, col);
    }
    if (keepSurfaceRanges) (c.surfaceRanges ||= []).push([startFace, c.pos.length / 9, a.c, a.l, areaId]);
    // kerbs (ground level) or slab sides (level 1) along every ring
    const drop = slab || (a.c === 'sidewalk' || a.c === 'island' || a.c === 'median' || a.c === 'platform' ? 0.18 : 0);
    if (!drop) continue;
    const side = a.l > 0 ? col : new THREE.Color('#8e8a82').toArray();
    [a.ring, ...a.holes].forEach((ring, ri) => {
      for (let i = 0; i < ring.length; i++) {
        if (a.kerbs && !a.kerbs[ri]?.[i]) continue; // kerbs only where the carriageway is (tools/kerbs.py)
        const p = ring[i], q = ring[(i + 1) % ring.length];
        cg.quad(c, W(p[0], p[1], p[2] + lift - drop), W(q[0], q[1], q[2] + lift - drop), W(q[0], q[1], q[2] + lift), W(p[0], p[1], p[2] + lift), side);
      }
    });
  }
  buildParapets(cgs.other, dtm.parapets || [], color.wall);
  for (const [kind, cg] of Object.entries(cgs)) cg.build(group, 'dtm', kind);
}
