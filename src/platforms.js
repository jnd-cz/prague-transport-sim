// SPDX-License-Identifier: AGPL-3.0-or-later
// Tram platforms and stop furniture (#419): the OSM platforms of both directions where the build placed them
// (tools/placement.py `place_platform`: the path, s0, s1, side, far and `ours`), our stops' signs, shelters and stand-in
// platforms, the opposite direction's signs and shelters. World furniture: the game's rules read `game.platforms`.
import * as THREE from 'three';
import { makeStopSign } from './models.js';

// Place an object at route position s with lateral offset, facing direction of travel
// (or facing the tram when `faceBack`). Within 9 m of the track (or on a bridge) it stands at the track's profile; past
// it on the ground there, read once its tile holds its lookup (ground.later: what Start places reads no lookup past the
// window, #658), at the track's level until then.
export function place(obj, route, s, lateral, h = 0, faceBack = false) {
  const o = route.offset(s, lateral), g = route.ground;
  if (Math.abs(lateral) < 9 || g.profile.onBridge(s) || !g.later) obj.position.set(o.x, h + g.atRoute(s, lateral), -o.y);
  else {
    obj.position.set(o.x, h + g.profile.heightAt(s, 0), -o.y);
    g.later(o.x, o.y, () => { obj.position.y = h + g.at(obj.position.x, -obj.position.z); });
  }
  const fx = faceBack ? -o.hx : o.hx, fy = faceBack ? -o.hy : o.hy;
  obj.rotation.y = Math.atan2(fx, -fy);
}

// a glass stop shelter (back panel on its local -x side)
function makeShelter() {
  const shelter = new THREE.Group();
  const roof = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.1, 5), new THREE.MeshLambertMaterial({ color: 0x3d4a52 }));
  roof.position.y = 2.5;
  const back = new THREE.Mesh(new THREE.BoxGeometry(0.05, 2.1, 5), new THREE.MeshLambertMaterial({ color: 0x9fb8c4, transparent: true, opacity: 0.45 }));
  back.position.set(-0.75, 1.3, 0);
  shelter.add(roof, back);
  return shelter;
}

// A platform strip along rt from s0 to s1 (`side` +1 left), from `inner` to `outer` m off the axis, its top 0.18 m over
// the top of rail (src/heights.js), kerb faces where it starts, ends and breaks: triangles into pos/col. A cross-section
// within STRIP_CLEAR m of a drawn track's axis is left out with the segments beside it (#581: at Bílá Hora's loop the
// first stop's own platform ran as one straight box across the loop's tracks, at Spojovací OSM's platform A crossed
// one). Returns the metres left out. `zo`: the street's surface at the outer kerb of each cross-section, read at the load
// (settlePlatforms: Start reads no lookup past the window, #658).
const STRIP_CLEAR = 0.8;
// the strip's cross-sections along its track, about every 2 m
const sections = (s0, s1) => { const n = Math.max(2, Math.ceil((s1 - s0) / 2)), out = []; for (let k = 0; k <= n; k++) out.push(s0 + ((s1 - s0) * k) / n); return out; };
export function platformStrip(rt, s0, s1, side, inner, outer, ground, pos, col, cTop, cKerb, zo = null) {
  const V = (o, z) => [o.x, z, -o.y];
  const tri = (a, b, c, k) => { pos.push(...a, ...b, ...c); for (let i = 0; i < 3; i++) col.push(k.r, k.g, k.b); };
  const quad = (a, b, c, d, k) => { tri(a, b, c, k); tri(a, c, d, k); };
  const clear = (s) => {
    if (!ground?.trackWithin) return true;
    for (let o = inner + STRIP_CLEAR; o <= outer + 1e-6; o += 0.5) {
      const p = rt.offset(s, side * o);
      if (ground.trackWithin(p.x, p.y, STRIP_CLEAR)) return false;
    }
    return true;
  };
  const end = (c) => quad(V(c.I, c.zt - 0.06), V(c.O, c.zg), V(c.O, c.top), V(c.I, c.top), cKerb);
  let prev = null, left = 0;
  const S = sections(s0, s1), n = S.length - 1;
  for (let k = 0; k <= n; k++) {
    const s = S[k];
    if (!clear(s)) {
      if (prev) end(prev);
      if (k) left += (s1 - s0) / n;
      prev = null;
      continue;
    }
    const c = rt.at(s), I = rt.offset(s, side * inner), O = rt.offset(s, side * outer);
    const zt = ground.trackAt(c.x, c.y), top = zt + 0.18, zg = Math.min(top - 0.05, (zo ? zo[k] : ground.surface(O.x, O.y)) - 0.05);
    const cur = { I, O, zt, top, zg };
    if (prev) {
      quad(V(prev.I, prev.top), V(I, top), V(O, top), V(prev.O, prev.top), cTop);
      quad(V(prev.I, prev.zt - 0.06), V(I, zt - 0.06), V(I, top), V(prev.I, prev.top), cKerb);
      quad(V(prev.O, prev.zg), V(O, zg), V(O, top), V(prev.O, prev.top), cKerb);
    } else end(cur);
    prev = cur;
  }
  if (prev) end(prev);
  return left;
}

const TOP = 0xa7a197, KERB = 0x8e8a82;
function platformMesh(pos, col) {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.computeVertexNormals();
  const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
  m.userData.surface = 'platform'; // (the checks find it: tools/lint.js)
  return m;
}

// An OSM platform's strip across its track: from 1.5 m off its centre out to its width (an OSM line usually runs along
// its middle, 2-3.5 m wide unless tagged: it reached over the car lane at Trojská, 5.1 m; an area gives its outer edge)
function across(pl) {
  const inner = 1.5, far = pl.far;
  return { inner, outer: pl.area ? Math.min(inner + 6, Math.max(inner + 2, far)) : inner + (pl.w || Math.max(2.4, Math.min(3.5, pl.gtfs ? far + 1 - inner : 2 * far - 2 * inner))) };
}

// What the platforms stand on, read at the end of the load while every tile's lookup is held (src/main.js; the window
// drops those past it from there, #658): the street's surface at each strip's outer kerb (a platform the survey does not
// draw), under a Vienna-type platform's sign on the opposite path and under an opposite platform's shelter, onto its
// network record (zo, zs, zh).
export function settlePlatforms(data, route, backRoute) {
  const ground = route.ground, net = new Map((data.network?.platforms || []).map((r) => [r.i, r]));
  for (const [i, pl] of (data.platforms || []).entries()) {
    const N = net.get(i), rt = pl.path === 'back' ? backRoute : pl.path ? route : null;
    if (!N || !rt) continue;
    const kerb = pl.side < 0 ? pl.vienna ?? null : null;
    if (kerb === null && !N.surveyed) {
      const { outer } = across(pl);
      N.zo = sections(pl.s0, pl.s1).map((s) => { const O = rt.offset(s, pl.side * outer); return ground.surface(O.x, O.y); });
    }
    if (kerb !== null && rt === backRoute && !pl.ours && !pl.twin) {
      const at = pl.stop ? rt.nearest(pl.stop[0], pl.stop[1]).s : pl.s1 - 0.5, o = rt.offset(at, pl.side * (kerb + 0.8));
      N.zs = ground.surface(o.x, o.y);
    }
    if (pl.shelter && rt === backRoute && !pl.ours) {
      const m = rt.offset((pl.s0 + pl.s1) / 2, pl.side * ((kerb !== null ? kerb + 2 : across(pl).outer) - 0.6));
      N.zh = ground.trackAt(m.x, m.y);
    }
  }
}

// Tram platforms of both directions from OSM (tools/platforms.py), each along the path the build put it on, built as a
// strip curved along it from 1.5 m off the track centre out to its width, 0.18 m over top of rail (src/heights.js), kerb
// faces on both sides. Where the surveyed streets (DTM) have a platform, island or sidewalk there, the survey draws it.
// The opposite direction's platforms get a stop sign at their head and a shelter where OSM has one. The stop type
// (Vienna: the kerb's offset) is the build's (tools/placement.py vienna), and whether the survey draws a platform too
// (data/lineN.network.json, tools/network.py Stops); the heights its strip and a Vienna-type one's sign stand on were
// read at the load (settlePlatforms): Start reads no survey (#658). Returns game.platforms ({ rt, back, s0, s1, side, inner, outer, ours, kerb, surveyed,
// ... }: src/traffic.js reads it); `log` collects the strips left out over tracks (platformGaps).
export function buildPlatforms({ data, route, backRoute, group, log }) {
  const ground = route.ground, net = new Map((data.network?.platforms || []).map((r) => [r.i, r]));
  const pos = [], col = [];
  const cTop = new THREE.Color(TOP), cKerb = new THREE.Color(KERB);
  const platforms = [], also = [];
  for (const [i, pl] of (data.platforms || []).entries()) {
    if (!('path' in pl)) throw new Error(`line ${data.line} data has platforms without their placement: built before #419, rebuild it (tools/rebuild.py)`);
    if (!pl.path) continue;
    const rt = pl.path === 'back' ? backRoute : route;
    if (!rt) continue;
    const { s0, s1, side } = pl, { inner, outer } = across(pl);
    const ours = pl.ours ? { s0: pl.ours[0], s1: pl.ours[1] } : null;
    const N = net.get(i);
    if (!N) throw new Error(`line ${data.line}: platform ${pl.name} is not in the network (python -P -E tools/network.py --lines ${data.line})`);
    const plat = { rt, back: rt !== route, s0, s1, side, inner, outer, name: pl.name, code: pl.code, lines: pl.lines, stop: pl.stop, shelter: pl.shelter, ours, twin: !!pl.twin, unused: !!pl.unused, zs: N.zs, zh: N.zh };
    platforms.push(plat);
    if (pl.also) also.push([plat, pl.also]);
    // (a Vienna-type stop on the doors' side: no platform on the road, the sidewalk is the platform)
    plat.kerb = side < 0 ? pl.vienna ?? null : null;
    if (plat.kerb !== null) { plat.inner = plat.kerb; plat.outer = plat.kerb + 2; plat.surveyed = true; continue; }
    plat.surveyed = N.surveyed; // (its middle a platform, island or sidewalk of the survey)
    if (plat.surveyed) continue;
    const left = platformStrip(rt, s0, s1, side, inner, outer, ground, pos, col, cTop, cKerb, N.zo);
    if (left) log.platformGaps.push(`${pl.name} ${pl.code ?? ''}: ${left.toFixed(0)} m over a track left out`);
  }
  // A platform both paths tie on (they run over its track the same way: line 9 from Řepy to Motol) serves both: the
  // other path gets it along its own s, not drawn again and without a sign of its own, its kerb and survey the drawn
  // one's (the user, 2026-11-14, #419: platforms belong to the track, docs/architecture.md)
  for (const [plat, list] of also) for (const a of list) {
    const art = a.path === 'back' ? backRoute : route;
    if (art) platforms.push({ ...plat, rt: art, back: art !== route, s0: a.s0, s1: a.s1, side: a.side, ours: null, twin: true, shared: true });
  }
  if (pos.length) group.add(platformMesh(pos, col));
  // the opposite direction's stops: sign where PID has the stop (GTFS position, name and lines;
  // their driving direction is along the back route), shelter where OSM has one. Not on our own platforms (`ours`:
  // our stop's sign and shelter stand there). One sign per platform: where OSM draws a platform as several ways, the
  // others (`twin`, tools/platforms.py) got a blank sign beside its own (Flora, Malostranská). A platform no tram stops
  // at (`unused`) has its sign without the lines' plate (the user, 2026-11-09, #407)
  for (const p of platforms) {
    if (!p.back || p.ours || p.shared) continue;
    if (!p.twin) {
      const at = p.stop ? p.rt.nearest(p.stop[0], p.stop[1]).s : p.s1 - 0.5;
      const o = p.rt.offset(at, p.side * (p.inner + 0.8)), h = p.rt.at(at);
      const zt = p.kerb !== null ? p.zs - 0.18 : ground.trackAt(o.x, o.y);
      const sign = makeStopSign(p.name || '', false, p.unused ? [] : p.lines || [String(data.line)]);
      sign.position.set(o.x, zt + 0.18, -o.y);
      sign.rotation.y = Math.atan2(-h.hx, h.hy);
      group.add(sign);
    }
    if (p.shelter) {
      const sh = makeShelter(), m = p.rt.offset((p.s0 + p.s1) / 2, p.side * (p.outer - 0.6));
      sh.position.set(m.x, p.zh + 0.18, -m.y);
      sh.rotation.y = Math.atan2(m.hx, -m.hy) + (p.side > 0 ? Math.PI : 0);
      group.add(sh);
    }
  }
  return platforms;
}

// One of our stops: its platform, sign and shelter, into `group`. Sets stop.vienna, stop.sign and stop.signPlace (the
// game moves the sign with the stop point: _initSignals may pull it back to a signal's stop point). What it reads of the
// survey, at the stop point the set (`cars`) gives, is the build's (data/lineN.network.json `stops`, tools/network.py
// Stops: whether the survey draws the stand-in platform, how far out the shelter stands): Start reads no survey (#658).
// A Vienna-type stop's sign and shelter, and a stand-in platform, stand on the street's surface, read once its tile holds
// its lookup (ground.later).
export function buildStop({ stop, data, route, platforms, group, log, cars = 2 }) {
  const g = new THREE.Group(), ground = route.ground, N = data.network.stops[stop.i], c = cars - 1;
  // our platform: the OSM one (built with both directions' platforms) where it covers the stop zone, also one the
  // back path took that the route passes on its doors' side (`ours`), else a 30 m box on the right (T3 doors are on
  // the right side only)
  const osm = platforms.find((p) => !p.back && p.side < 0 && p.s0 < stop.target - 8 && p.s1 > stop.target - 20)
    || platforms.find((p) => p.back && p.ours && p.ours.s0 < stop.target - 8 && p.ours.s1 > stop.target - 20);
  const len = 30;
  // (a Vienna-type stop: boarding from the sidewalk; sign and shelter stand at the kerb)
  const kerb = osm ? osm.kerb : data.stops[stop.i].vienna ?? null;
  stop.vienna = kerb !== null;
  // (a strip along the route as the OSM platforms, 1.5-4.1 m to the right, 0.18 m over the top of rail; before #581 a
  // straight box along the chord, its top 0.44 m over the rails, which at a first stop in a loop (Bílá Hora) ran
  // across the loop's tracks; not where the survey draws a platform, an island or a sidewalk there, as the OSM ones)
  stop.standIn = N.stand[c];
  if (stop.standIn) {
    // (on the street's surface, read once its tile holds its lookup; none on today's lines)
    const s0 = stop.target - len - 1, s1 = stop.target - 1, at = route.offset((s0 + s1) / 2, -2.8);
    ground.later(at.x, at.y, () => {
      const pos = [], col = [];
      const left = platformStrip(route, s0, s1, -1, 1.5, 4.1, ground, pos, col, new THREE.Color(TOP), new THREE.Color(KERB));
      if (left) log.platformGaps.push(`stop ${stop.name}: ${left.toFixed(0)} m over a track left out`);
      if (pos.length) g.add(platformMesh(pos, col));
    });
  }
  // the classic red Prague stop sign (zastávkový označník) where the tram front stops
  const sign = makeStopSign(stop.name, stop.request, data.stops[stop.i].lines || [String(data.line)]);
  // (on the sidewalk's height, not the track's)
  const onWalk = (m) => ground.later(m.position.x, -m.position.z, () => { m.position.y = ground.surface(m.position.x, -m.position.z); });
  stop.signPlace = (s) => { place(sign, route, s + 0.5, stop.vienna ? -(kerb + 0.6) : -2.3, 0.18, true); if (stop.vienna) onWalk(sign); };
  stop.signPlace(stop.target);
  g.add(sign);
  stop.sign = sign;
  // the shelter's outer edge: the OSM platform's, but no further than the surveyed one where the DTM
  // draws the platform (OSM's island at Palackého náměstí is 6.2 m out, the survey's 4.5 m: the
  // shelter stood on the road)
  const outer = osm ? N.outer[c] / 100 : null;
  stop.shelterOuter = outer;
  // shelter (at the back of the OSM platform where there is one)
  const shelter = makeShelter();
  place(shelter, route, stop.target - 12, stop.vienna ? -(kerb + 2.4) : osm ? -(outer - 0.6) : -3.4, 0.18);
  if (stop.vienna) onWalk(shelter);
  g.add(shelter);
  group.add(g);
}
