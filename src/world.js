// SPDX-License-Identifier: AGPL-3.0-or-later
// The world built from the line's data, layer by layer (buildWorld): the ground file's tiles, the tracks' beds and
// rails, the streets, the structures, the buildings, the trees and the catenary, each layer in its own module.
import * as THREE from 'three';
import { DTM_LIFT } from './terrain.js';
import { RAIL_HEAD, BED_BELOW } from './heights.js';
import { preparePedestrianCrossings } from './pedestrianCrossings.js';
import { NearBatches } from './nearbatch.js';
import { weatherize, wetFactor, WEATHER_UNIFORMS, WEATHER_LOOK } from './weather.js';
import { bridgeWire, buildLod2, buildOsmBuildings } from './buildings.js';
import { buildCatenary } from './catenary.js';
import { STYLE_BED_HEX, attachGround, buildDtm, flushDtm } from './groundDraw.js';
import { buildRoads, buildZebras } from './streets.js';
import { buildBridges, buildRoadPortals, buildRockTunnels, buildTrackSupport, fitDtmToMouths,
  roadPortalMouths } from './structures.js';
import { buildTrees } from './trees.js';
import { ChunkedGeometry, GROUND_SNOW, SegmentIndex, W, addRibbon, addSide, densify, flatMat, polyLength } from './worldMesh.js';

const TRACK_REACH = 6; // m from a drawn track within which ground.trackAt is its own height (terrain.js trackAt's reach)

// A track's bed (#547): out to its width each side (`t.bed`, tools/track_beds.py: the survey's area of its style, the
// middle of the strip to a paired track), the rails' plane between them and beyond, except where it meets the paired
// track: there the edge lies at the mean of the two near rails, as the street between them (terrain.js heightAt).
// Without `t.bed` (data built before #547) the 2.7 m ribbon.
const GAUGE_HALF = 0.72;
// (the bed across at each drawn point: [x, y, nx, ny, offsets, heights] with the offsets (m, + left) and heights of its
// right edge, right rail, left rail and left edge; the edges 1.35 m out without `t.bed`)
function bedRows(t, step, zBed, tilt, otherRail) {
  const line = t.smooth, rows = [];
  const len = (L) => { let a = 0; for (let i = 1; i < L.length; i++) a += Math.hypot(L[i][0] - L[i - 1][0], L[i][1] - L[i - 1][1]); return a; };
  const k = len(t.p) / (len(line) || 1), n = t.bed?.l.length ?? 0;
  let acc = 0;
  for (let i = 0; i < line.length; i++) {
    const p = line[i];
    if (i) acc += Math.hypot(p[0] - line[i - 1][0], p[1] - line[i - 1][1]);
    const f = n ? Math.min(n - 1, (acc * k) / step) : 0, i0 = Math.min(Math.floor(f), Math.max(0, n - 1)), i1 = Math.min(i0 + 1, Math.max(0, n - 1)), u = f - i0;
    const near = u < 0.5 ? i0 : i1;
    const prev = line[Math.max(0, i - 1)], next = line[Math.min(line.length - 1, i + 1)];
    let dx = next[0] - prev[0], dy = next[1] - prev[1];
    const l = Math.hypot(dx, dy) || 1;
    dx /= l; dy /= l;
    let scale = 1;
    if (i > 0 && i < line.length - 1) {
      const ax = p[0] - prev[0], ay = p[1] - prev[1], al = Math.hypot(ax, ay) || 1;
      scale = Math.min(2, 1 / Math.max(0.5, (ax / al) * dx + (ay / al) * dy));
    }
    const nx = -dy * scale, ny = dx * scale, slope = tilt[i] / GAUGE_HALF;
    const off = [0, -GAUGE_HALF, GAUGE_HALF, 0], z = [0, zBed[i] - tilt[i], zBed[i] + tilt[i], 0];
    for (const [side, key, bit, j] of [[-1, 'r', 2, 0], [1, 'l', 1, 3]]) {
      const w = t.bed ? (t.bed[key][i0] * (1 - u) + t.bed[key][i1] * u) / 100 : 1.35;
      off[j] = side * w;
      z[j] = zBed[i] + slope * side * w;
      if (t.bed?.meet[near] & bit) {
        const o = otherRail(p[0] + nx * side * w, p[1] + ny * side * w);
        if (o !== null) z[j] = (zBed[i] + tilt[i] * side + o) / 2;
      }
    }
    rows.push([p[0], p[1], nx, ny, off, z]);
  }
  return rows;
}

// A track's bed (#547): out to its width each side (`t.bed`, tools/track_beds.py: the survey's area of its style, the
// middle of the strip to a paired track), the rails' plane between them and beyond, except where it meets the paired
// track: there the edge lies at the mean of the two near rails, as the street between them (terrain.js heightAt).
// (skip(i): leave the piece between rows i and i + 1 out)
function addBed(cg, rows, col, skip = null) {
  if (rows.length < 2) return;
  const V = rows.map(([x, y, nx, ny, off, z]) => off.map((o, j) => W(x + nx * o, y + ny * o, z[j])));
  const c = cg._chunk(rows[0][0], rows[0][1]);
  for (let i = 0; i < V.length - 1; i++) {
    if (skip?.(i)) continue;
    const A = V[i], B = V[i + 1], cc = typeof col === 'function' ? col(i) : col;
    for (let j = 0; j < 3; j++) cg.quad(c, A[j], B[j], B[j + 1], A[j + 1], cc);
  }
}

// The bed's surface at offset o (m, + left) of one of its rows (the rows of bedRows); null past its edges
function bedZ(row, o) {
  const off = row[4], z = row[5];
  if (o < off[0] || o > off[3]) return null;
  for (let j = 0; j < 3; j++) if (o <= off[j + 1]) return z[j] + ((z[j + 1] - z[j]) * (o - off[j])) / ((off[j + 1] - off[j]) || 1);
  return z[3];
}

// A track's assembled top of rail (`zs` every `step` m along t.p, tools/line_heights.py) at its drawn points t.smooth.
function ownHeights(t, step) {
  const len = (L) => { let a = 0; for (let i = 1; i < L.length; i++) a += Math.hypot(L[i][0] - L[i - 1][0], L[i][1] - L[i - 1][1]); return a; };
  const sm = t.smooth, k = len(t.p) / (len(sm) || 1), d = new Float32Array(sm.length);
  let acc = 0;
  for (let i = 0; i < sm.length; i++) {
    if (i) acc += Math.hypot(sm[i][0] - sm[i - 1][0], sm[i][1] - sm[i - 1][1]);
    const f = (acc * k) / step, i0 = Math.min(Math.floor(f), t.zs.length - 1), a = t.zs[i0], b = t.zs[Math.min(i0 + 1, t.zs.length - 1)];
    d[i] = a == null || b == null ? NaN : a + (b - a) * (f - i0);
  }
  if (d.some(Number.isNaN)) throw new Error('a track without a height: data built before #480, rebuild it (tools/rebuild.py)');
  return Array.from(d);
}

// The parts of buildWorld in order, with their usual share of its time (line 17, ms) and the loading
// screen's label for them. (A line without the surveyed streets skips the two DTM parts.)
export const WORLD_PARTS = [
  ['tracks + tunnel roads', 1600, 'tracks'], ['terrain mesh', 1100, 'terrain'],
  ['DTM streets', 3800, 'streets'], ['OSM roads', 300, 'roads'], ['track bed + rails', 100, 'roads'], ['track support', 1200, 'roads'],
  ['zebras', 50, 'roads'], ['bridges + tunnels', 20, 'roads'], ['buildings', 3300, 'buildings'],
  ['trees', 200, 'wires'], ['catenary', 200, 'wires'],
];

// onPart(name): called (and awaited) after each part, so a loading screen can show the progress.
// The world is the same in every weather: group.userData.setWeather(w) sets it (src/weather.js).
// (x, y)'s offset across from our track, left > 0, at its nearest route point n (Profile.heightAt's `lateral`)
function lateralOf(route, n, x, y) { const q = route.at(n.s); return q.hx * (y - q.y) - q.hy * (x - q.x); }
// the track style at (x, y) beside the route: the other direction's track takes its own (`stylesBack`, #584)
function styleOn(route, ground, n, x, y) {
  if (!ground.styles) return undefined;
  return ground.profile.onBack(n.s, lateralOf(route, n, x, y)) ? ground.styles.atBack(n.s) : ground.styles.at(n.s);
}

export async function buildWorld(scene, data, route, ground, onPart = null) {
  const group = new THREE.Group();
  group.matrixAutoUpdate = false;
  group.userData.near = new NearBatches(); // the small things drawn near the camera only (src/nearbatch.js, #610)
  scene.add(group);
  // time of each part (window.worldTimes, logged at the end: what to optimize)
  const times = {};
  let lap = performance.now(), seen = 0;
  const mark = async (k) => {
    // (each mesh knows its part: review mode hides the buildings and the trees, src/review.js)
    for (const o of group.children.slice(seen)) o.userData.part ??= k;
    seen = group.children.length;
    times[k] = Math.round(performance.now() - lap);
    if (onPart) await onPart(k);
    lap = performance.now();
  };

  // far fallback ground below the terrain
  const far = new THREE.Mesh(new THREE.PlaneGeometry(60000, 60000), weatherize(new THREE.MeshLambertMaterial({ color: 0x8a897d }), { wet: wetFactor('#8d8c80', '#77766c'), snow: GROUND_SNOW }));
  far.rotation.x = -Math.PI / 2;
  far.position.y = ground.terrain.min - 3;
  scene.add(far);

  // track geometry first: the curves and heights (once; kept across weather rebuilds),
  // then the terrain is lowered under every track so it can't poke through the bed
  // the build draws every track as curves (data.trackCurve, #204): its points as they are, a point every 1.5 m at most
  // (resampled, a 4.6 m piece's end became a chord and its joint at Strossmayerovo náměstí broke 2.9°)
  for (const t of data.tracks) if (!t.smooth) t.smooth = densify(t.p, 1.5);
  // every track centre line, for keeping trees, zebra paint and poles off the tracks and for the
  // street surfaces laid flush with the track bed
  const tracks = new SegmentIndex(10);
  for (const t of data.tracks) tracks.addLine(t.smooth);
  const trackDist = (x, y) => tracks.dist(x, y);
  ground.trackDist = trackDist;
  // (whether a track is within r <= 4 m: the same answer from 4 m cells, a ninth of the area searched; the
  // street flush and the track support ask it millions of times at load, #244)
  const near = new SegmentIndex(4);
  for (const t of data.tracks) near.addLine(t.smooth);
  ground.trackWithin = (x, y, r) => near.within(x, y, r);
  // (the prebuilt ground, src/groundFile.js, #509: its survey, terrain and beds already meet the tracks)
  const pre = ground.tiles; // (the ground file's tiles, src/groundFile.js: lookups now, meshes as the window wants them)
  if (ground.dtm) flushDtm(ground);
  // every track's top of rail is the build's (#197: `zs` every 2 m along t.p, tools/line_heights.py), unsmoothed; since
  // #480 the build leaves no sample without one (the surface plus the style's lift where no source has a height)
  for (const t of data.tracks) if (!t.z) t.z = t.zs ? ownHeights(t, data.heights.step) : t.smooth.map(() => 0);
  // a track's height where something stands on it (the oncoming trams, platforms, the gauntlet): the nearest drawn track's
  // own, as its rails are drawn. (terrain.js trackAt took the route's profile across the street within 6 m of our route
  // and the street's surface past it: an oncoming tram stepped 0.27 m where the opposite track leaves ours at Ohrada, 0.1 m
  // at Palmovka, #655.) Past TRACK_REACH of every track, that answer still.
  if (!ground.trackOwn) {
    const own = new SegmentIndex(10);
    for (const t of data.tracks) for (let i = 1; i < t.smooth.length; i++) own.add(t.smooth[i - 1], t.smooth[i], 0, t.z[i - 1], t.z[i]);
    const trackAt = ground.trackAt.bind(ground);
    ground.trackOwn = own;
    ground.trackAt = (x, y) => own.heightAt(x, y, TRACK_REACH) ?? trackAt(x, y);
  }
  // Share the exact rail cant with pedestrian crossings; a crossing must meet each rail's height.
  const tiltCache = new WeakMap();
  const tiltOf = (t) => {
    if (tiltCache.has(t)) return tiltCache.get(t);
    const tilt = t.smooth.map(([x, y], i) => {
      const n = route.nearest(x, y);
      if (!n || n.d > 5) return 0;
      const roll = route.rollAt(n.s);
      if (!roll) return 0;
      const L = t.smooth, a = L[Math.max(0, i - 1)], b = L[Math.min(L.length - 1, i + 1)];
      const h = route.at(n.s), same = (b[0] - a[0]) * h.hx + (b[1] - a[1]) * h.hy >= 0 ? 1 : -1;
      return -0.72 * Math.tan(roll) * same;
    });
    tiltCache.set(t, tilt); return tilt;
  };
  // (how far a track's bed lies under its top of rail, by the route's track styles: src/heights.js)
  // (each track its own: the other direction's beside the route takes its `liftBack`, #584)
  // (off the route, the track's own `lift` at s along its p: its own styles' offsets, another line's open ballast,
  // tools/track_styles.py own_lifts, #548)
  const ownLift = (L, s) => {
    const n = L ? L.v.length : 0;
    if (!n) return 0;
    const f = Math.max(0, Math.min(n - 1.001, s / L.step)), i = Math.floor(f), u = f - i;
    return n < 2 ? L.v[0] * L.unit : (L.v[i] * (1 - u) + L.v[i + 1] * u) * L.unit;
  };
  const liftAt = (x, y, t, s) => {
    const n = route.nearest(x, y);
    return n && n.d < 6 ? ground.profile.lift(n.s, lateralOf(route, n, x, y)) : ownLift(t.lift, s);
  };
  // (each track's bed and tilt: a bed meeting its paired track's lays its edge at the mean of their near rails; the
  // survey and the terrain are laid under the same cross-section, #548)
  const lenOf = (L) => { let a = 0; for (let i = 1; i < L.length; i++) a += Math.hypot(L[i][0] - L[i - 1][0], L[i][1] - L[i - 1][1]); return a; };
  const beds = data.tracks.map((t) => {
    const k = lenOf(t.p) / (lenOf(t.smooth) || 1);
    let acc = 0;
    const lift = t.smooth.map(([x, y], i) => {
      if (i) acc += Math.hypot(x - t.smooth[i - 1][0], y - t.smooth[i - 1][1]);
      return liftAt(x, y, t, acc * k);
    });
    return { lift, zBed: t.z.map((z, i) => z - lift[i] - BED_BELOW), tilt: tiltOf(t) };
  });
  const bedGrid = new Map(), cell = (x, y) => `${Math.floor(x / 4)},${Math.floor(y / 4)}`;
  data.tracks.forEach((t, k) => t.smooth.forEach(([x, y], i) => {
    const key = cell(x, y);
    if (!bedGrid.has(key)) bedGrid.set(key, []);
    bedGrid.get(key).push([k, i]);
  }));
  // (each track's nearest drawn point to (x, y) within 4 m: [track, index, distance])
  const nearPoints = (x, y, skip = -1) => {
    const best = new Map(), cx = Math.floor(x / 4), cy = Math.floor(y / 4);
    for (let a = cx - 1; a <= cx + 1; a++) for (let b = cy - 1; b <= cy + 1; b++) for (const [k, i] of bedGrid.get(`${a},${b}`) || []) {
      if (k === skip) continue;
      const p = data.tracks[k].smooth[i], d = Math.hypot(p[0] - x, p[1] - y);
      if (d < 4 && !(best.get(k)?.[1] <= d)) best.set(k, [i, d]);
    }
    return [...best].map(([k, [i, d]]) => [k, i, d]);
  };
  // (the near rail of the nearest other track at (x, y): its height there)
  const otherRail = (own, x, y) => {
    let best = null;
    for (const h of nearPoints(x, y, own)) if (!best || h[2] < best[2]) best = h;
    if (!best) return null;
    const [k, i] = best, L = data.tracks[k].smooth, a = L[Math.max(0, i - 1)], b = L[Math.min(L.length - 1, i + 1)];
    const side = (b[0] - a[0]) * (y - L[i][1]) - (b[1] - a[1]) * (x - L[i][0]) >= 0 ? 1 : -1;
    return beds[k].zBed[i] + beds[k].tilt[i] * side;
  };
  data.tracks.forEach((t, k) => { beds[k].rows = bedRows(t, data.heights.step, beds[k].zBed, beds[k].tilt, (x, y) => otherRail(k, x, y)); });
  // (the rows of the beds near (x, y), each with the point's offset across it: [row, offset])
  const bedsNear = (x, y) => {
    const out = [];
    for (const [k, i] of nearPoints(x, y)) {
      if (data.tracks[k].b) continue;
      const rows = beds[k].rows;
      // (the nearer of the two segments around the point: the offset across and the share along)
      let best = null;
      for (const j of [i - 1, i]) {
        if (j < 0 || j + 1 >= rows.length) continue;
        const A = rows[j], B = rows[j + 1], ex = B[0] - A[0], ey = B[1] - A[1], el = ex * ex + ey * ey || 1;
        const u = ((x - A[0]) * ex + (y - A[1]) * ey) / el;
        if (u < -0.01 || u > 1.01) continue;
        const v = Math.max(0, Math.min(1, u)), px = A[0] + ex * v, py = A[1] + ey * v, d = Math.hypot(x - px, y - py);
        if (!best || d < best[0]) best = [d, A, B, v];
      }
      if (!best) continue;
      const [, A, B, v] = best, mix = (a, b) => a.map((q, j) => q * (1 - v) + b[j] * v);
      const row = [A[0] * (1 - v) + B[0] * v, A[1] * (1 - v) + B[1] * v, A[2] * (1 - v) + B[2] * v, A[3] * (1 - v) + B[3] * v, mix(A[4], B[4]), mix(A[5], B[5])];
      const nl = Math.hypot(row[2], row[3]) || 1, o = ((x - row[0]) * row[2] + (y - row[1]) * row[3]) / nl / nl;
      out.push([row, o, k]);
    }
    return out;
  };
  // (where beds overlap, a junction or a switch, a bed's edge no higher than the other bed under it: an edge over the
  // other track's rail heads buried them, #165, #548; another level, over 0.3 m apart, is left)
  const edges = data.tracks.map((t, k) => beds[k].rows.map(([x, y, nx, ny, off, z]) => [0, 3].map((j) => {
    let m = z[j];
    for (const [row, o, kk] of bedsNear(x + nx * off[j], y + ny * off[j])) {
      if (kk === k) continue;
      const zs = bedZ(row, o);
      if (zs !== null && m > zs && m - zs < 0.3) m = zs;
    }
    return m;
  })));
  data.tracks.forEach((t, k) => beds[k].rows.forEach((row, i) => { row[5][0] = edges[k][i][0]; row[5][3] = edges[k][i][1]; }));
  group.userData.bedRows = beds.map((b) => b.rows); // (read by tools/test_bed_surface_page.py: the build's copy of this rule, #508)
  const pedestrianCrossings = preparePedestrianCrossings(data, route, ground, tiltOf,
    (kind, level) => level > 0 ? 0.02 : DTM_LIFT[kind] ?? 0.03);
  // our tunnels through rock (terrain.js rockTunnels): the hill stays whole above the track; its
  // terrain is not drawn in the tunnel's corridor, the vault, the rock over it and the portals are
  const rock = ground.rock || [];
  const TUN_W = 8.5; // half width of the vault: both tracks and the road beside them (Vyšehrad tunnel)
  const inTunnel = (x, y, pad = 0) => {
    if (!rock.length) return false;
    const n = route.nearest(x, y);
    return !!n && n.d < TUN_W + pad && rock.some(([a, b]) => n.s > a - 0.5 && n.s < b + 0.5);
  };
  // road tunnels: drawn inside where they share our tunnel without an underground survey (else the
  // survey's floor is drawn there); a short one (a building passage, an underpass: under SHORT_TUNNEL m
  // in all) as an open road at its graded height, the building or bridge over it is its roof; a long
  // one below ground, with a mouth at each open end
  const SHORT_TUNNEL = 60, tunnelRoads = [], tunnelPortals = [];
  for (const r of data.roads) {
    if (!r.t || r.z) continue;
    const tf = ground.way(r.way || r.p, false, true), L = polyLength(r.way || r.p);
    const inside = densify(r.p, 3).filter((p) => inTunnel(p[0], p[1], 2));
    if (inside.length > 1) { if (!ground.dtm?.under?.length) tunnelRoads.push({ r, inside, tf }); }
    else if (L < SHORT_TUNNEL) tunnelRoads.push({ r, inside: densify(r.p, 3), tf });
    else if (r.c) tunnelPortals.push({ r, tf, L });
  }
  const mouths = roadPortalMouths(tunnelPortals);
  await mark('tracks + tunnel roads');
  const cellPad = Math.hypot(ground.terrain.dx, ground.terrain.dy) / 2;
  const inMouth = (x, y) => mouths.some((m) => m.has(x, y, cellPad));
  // (the file's ground is the hill over our rock tunnels and the road tunnels' mouths too: cut there, the vault, the
  // rock top and the portals drawn below; only the squares near them are tested. Its streets in a mouth come down onto
  // the tunnel road in the file, tools/ground_mesh.py fit_mouths, #682)
  const pad = TUN_W + 3 + cellPad, nearCut = [];
  for (const [a, b] of rock) for (let s = a - 1; s <= b + 1; s += 4) { const p = route.at(Math.max(0, Math.min(route.length, s))); nearCut.push([p.x - pad, p.y - pad, p.x + pad, p.y + pad]); }
  for (const m of mouths) { const r = m.D + m.w + 10; nearCut.push([m.p[0] - r, m.p[1] - r, m.p[0] + r, m.p[1] + r]); }
  attachGround(group, pre, (x, y) => inTunnel(x, y, 3) || inMouth(x, y), nearCut);
  await mark('terrain mesh');
  if (ground.dtm) fitDtmToMouths(ground.dtm, mouths);
  ground.dtm?.seal(); // (the survey's heights are final from here: its lookups from typed arrays, #244, #245)
  // (the contact wire's height under the bridge models first: the survey's slabs over a track hang no lower, #71)
  if (data.geo?.buildings?.arr) bridgeWire(data, ground);
  if (ground.dtm) buildDtm(group, ground);
  await mark('DTM streets');

  buildRoads(group, data, ground, trackDist, pedestrianCrossings, tunnelRoads);
  await mark('OSM roads');

  // track bed + rails for every tram track around the route
  const bedCg = new ChunkedGeometry(flatMat('#77736a', '#5f5c56'), { color: true });
  const bed = new THREE.Color('#77736a').toArray();
  // the bed by the route's track style (#52; colours until #308's textures): on our route's tracks (within 6 m of it)
  // the style at the nearest route point, elsewhere the track's own sections (`styles`, tools/track_styles.py
  // track_sections, #546: embedded at its junctions and road crossings), else panels
  // (setts, #574: a grey-brown stone until #308's texture)
  const STYLE_BED = Object.fromEntries(Object.entries(STYLE_BED_HEX)
    .map(([k, v]) => [k, new THREE.Color(v).toArray()]));
  const styleAt = (x, y) => { const n = route.nearest(x, y); return n && n.d < 6 && ground.styles ? styleOn(route, ground, n, x, y) : null; };
  // (a track's own style at each drawn point: its sections run along t.p, the drawn points along t.smooth, scaled as
  // ownHeights does)
  const ownStyles = (t) => {
    const len = (L) => { let a = 0; for (let i = 1; i < L.length; i++) a += Math.hypot(L[i][0] - L[i - 1][0], L[i][1] - L[i - 1][1]); return a; };
    const k = len(t.p) / (len(t.smooth) || 1);
    let acc = 0;
    return t.smooth.map((p, i) => {
      if (i) acc += Math.hypot(p[0] - t.smooth[i - 1][0], p[1] - t.smooth[i - 1][1]);
      const s = acc * k;
      return t.styles?.find(([a, b]) => s >= a && s <= b)?.[2] ?? 'panels';
    });
  };
  // (rails: glossy when wet, roughness set by the weather; trams keep them clear of snow)
  const railMat = new THREE.MeshStandardMaterial({ color: 0xc4c7cc, metalness: 0.6, roughness: 0.4 });
  const railCg = new ChunkedGeometry(railMat);
  // (src/heights.js: t.z is the top of rail; the bed lies the track style's offset under it, the
  // rail heads stand just over it, and where the bed is well below, the rails get their sides)
  const keepTrackRanges = /[?&](keepgeo|bot)\b/.test(location.search);
  const fileBed = (row) => ground.lookup?.kind(row[0], row[1]) === 'bed' && Math.abs(ground.lookup.hitZ - (bedZ(row, 0) ?? row[5][1])) < 0.1;
  for (const [trackId, t] of data.tracks.entries()) {
    const bc = keepTrackRanges && t.smooth.length > 1 ? bedCg._chunk(...t.smooth[0]) : null;
    const rc = keepTrackRanges && t.smooth.length > 1 ? railCg._chunk(...t.smooth[0]) : null;
    const bedStart = bc && bc.pos.length / 9, railStart = rc && rc.pos.length / 9;
    // on a canted curve of our route the outer rail is higher, the inner one lower
    const { lift, zBed, tilt } = beds[trackId];
    // The bed is the same canted plane as the rails, including its transition ramps.
    const own = ownStyles(t);
    const cols = t.smooth.map(([x, y], i) => STYLE_BED[styleAt(x, y) ?? own[i]] || bed);
    // (the ground file holds the beds on the ground: where it has this bed at both rows' centres, at the row's height; a
    // bed on a structure is not in it, the partition leaves it out (line 37's Krejcarek viaduct, its tracks without `b`))
    const rows = beds[trackId].rows;
    if (!pre || t.b) addBed(bedCg, rows, (i) => cols[i]);
    else addBed(bedCg, rows, (i) => cols[i], (i) => fileBed(rows[i]) && fileBed(rows[i + 1]));
    for (const side of [1, -1]) {
      const zr = t.z.map((z, i) => z + side * tilt[i]);
      addRibbon(railCg, t.smooth, 0.1, zr, RAIL_HEAD, null, side * 0.72);
      if (lift.some((v) => v > 0.03)) for (const face of [-0.05, 0.05]) addSide(railCg, t.smooth, side * 0.72 + face, zr.map((z) => z + RAIL_HEAD), zBed.map((z, i) => z + tilt[i] * (side + face / 0.72)));
    }
    if (bc) (bc.trackRanges ||= []).push([bedStart, bc.pos.length / 9, trackId]);
    if (rc) (rc.trackRanges ||= []).push([railStart, rc.pos.length / 9, trackId]);
  }
  bedCg.build(group, 'bed');
  railCg.build(group, 'rail');
  await mark('track bed + rails');
  buildTrackSupport(group, route, ground);
  await mark('track support');

  buildZebras(group, data, ground, trackDist);
  await mark('zebras');

  buildBridges(group, data, route, ground);
  buildRockTunnels(group, route, ground, rock, TUN_W);
  buildRoadPortals(group, mouths, ground.terrain);
  await mark('bridges + tunnels');

  if (data.geo?.buildings?.arr) buildLod2(group, data, route, ground);
  else buildOsmBuildings(group, data, route, ground);
  await mark('buildings');

  const trees = buildTrees(group, data, ground, trackDist);
  await mark('trees');
  buildCatenary(group, data, route, ground, trackDist);
  await mark('catenary');
  window.worldTimes = times;
  console.log('world build (ms)', times);
  // the weather: shader uniforms shared by all patched materials, the rails' gloss, the trees' crowns
  // and the fallen leaves (instant: nothing is rebuilt)
  group.userData.setWeather = (w) => {
    const look = WEATHER_LOOK[w] || WEATHER_LOOK.dry;
    WEATHER_UNIFORMS.uWet.value = look.wet;
    WEATHER_UNIFORMS.uSnow.value = look.snow;
    WEATHER_UNIFORMS.uAutumn.value = look.autumn;
    railMat.roughness = look.wet ? 0.2 : 0.4;
    trees.setWeather(w);
  };
  return group;
}
