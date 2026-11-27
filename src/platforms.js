// SPDX-License-Identifier: AGPL-3.0-or-later
// Tram platforms and stop furniture as drawn (#419, #228): the OSM platforms of both directions where the build placed
// them, our stops' signs, shelters and stand-in platforms, the opposite direction's signs and shelters. Where they are
// and what kind each stop is: src/platformRules.js (game.platforms, stop.vienna, standIn, shelterOuter); this draws it
// (src/gameView.js).
import * as THREE from 'three';
import { makeStopSign } from './models.js';

// Place an object at route position s with lateral offset, facing direction of travel
// (or facing the tram when `faceBack`). Within 9 m of the track (or on a bridge) it stands at the track's profile; past
// it on the ground there, read once its tile holds its lookup (ground.later: what Start places reads no lookup past the
// window, #658), at the track's level until then. `z`: the height the build stored for it (tools/network.py heights).
export function place(obj, route, s, lateral, h = 0, faceBack = false, z = null) {
  const o = route.offset(s, lateral), g = route.ground;
  if (z !== null) obj.position.set(o.x, z, -o.y);
  else if (Math.abs(lateral) < 9 || g.profile.onBridge(s) || !g.later) obj.position.set(o.x, h + g.atRoute(s, lateral), -o.y);
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
// one). Returns the metres left out. `zo`: the street's surface at the outer kerb of each cross-section, the build's
// (tools/network.py heights, #682: Start reads no lookup past the window, #658).
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


// Tram platforms of both directions (src/platformRules.js platformsOf), each along the path the build put it on, drawn
// as a strip curved along it from 1.5 m off the track centre out to its width, 0.18 m over top of rail (src/heights.js),
// kerb faces on both sides: not where the survey draws a platform, island or sidewalk there, nor a Vienna-type stop's (the
// sidewalk is its platform), nor one drawn for the other path already (`shared`). The opposite direction's platforms get
// a stop sign at their head and a shelter where OSM has one. The heights the strip's outer kerb, a Vienna-type one's sign
// and a shelter stand on are the build's (zo, zs, zh, tools/network.py heights, #682): Start reads no ground (#658).
// Into `group`; `log.platformGaps` collects the strips left out over tracks.
export function buildPlatforms({ data, route, platforms, group, log }) {
  const ground = route.ground, pos = [], col = [];
  const cTop = new THREE.Color(TOP), cKerb = new THREE.Color(KERB);
  for (const p of platforms) {
    if (p.shared || p.kerb !== null || p.surveyed) continue;
    const left = platformStrip(p.rt, p.s0, p.s1, p.side, p.inner, p.outer, ground, pos, col, cTop, cKerb, p.zo?.map((v) => v / 100));
    if (left) log.platformGaps.push(`${p.name} ${p.code ?? ''}: ${left.toFixed(0)} m over a track left out`);
  }
  if (pos.length) group.add(platformMesh(pos, col));
  // the opposite direction's stops: sign where PID has the stop (GTFS position, name and lines;
  // their driving direction is along the back route), shelter where OSM has one. Not on our own platforms (`ours`:
  // our stop's sign and shelter stand there). One sign per platform: where OSM draws a platform as several ways, the
  // others (`twin`, tools/platforms.py) got a blank sign beside its own (Flora, Malostranská). A platform no tram stops
  // at (`unused`) has its sign without the lines' plate (#407)
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
}

// One of our stops (src/platformRules.js stopOf): its stand-in platform, sign and shelter, into `group`, placed once from
// its stop point, the sign for every set (src/game.js _stopZone, #694). The heights a Vienna-type stop's sign and shelter
// and a stand-in platform stand on are the build's (data/lineN.network.json `stops`, tools/network.py Stops and heights):
// Start reads no ground (#658). Returns the sign.
export function buildStop({ stop, data, route, group, log }) {
  const g = new THREE.Group(), ground = route.ground, N = data.network.stops[stop.i], cm = (v) => (v === undefined ? null : v / 100);
  const len = 30;
  // (a strip along the route as the OSM platforms, 1.5-4.1 m to the right, 0.18 m over the top of rail; before #581 a
  // straight box along the chord, its top 0.44 m over the rails, which at a first stop in a loop (Bílá Hora) ran
  // across the loop's tracks; not where the survey draws a platform, an island or a sidewalk there, as the OSM ones)
  if (stop.standIn) {
    const pos = [], col = [];
    const left = platformStrip(route, stop.target - len - 1, stop.target - 1, -1, 1.5, 4.1, ground, pos, col, new THREE.Color(TOP), new THREE.Color(KERB), N.zo.map((v) => v / 100));
    if (left) log.platformGaps.push(`stop ${stop.name}: ${left.toFixed(0)} m over a track left out`);
    if (pos.length) g.add(platformMesh(pos, col));
  }
  // the classic red Prague stop sign (zastávkový označník) where the tram front stops: at its pole where the build
  // knows it on our side, the maintainer's placed sign or the DTM's (#685), else half a metre past the stop point (a
  // Vienna-type stop's at the kerb, on the sidewalk's height)
  const sign = makeStopSign(stop.name, stop.request, data.stops[stop.i].lines || [String(data.line)]);
  const { sign: at, signOff: off } = data.stops[stop.i];
  if (off !== undefined) place(sign, route, at, off, 0.18, true, cm(N.zs));
  else place(sign, route, stop.target + 0.5, stop.vienna ? -(stop.kerb + 0.6) : -2.3, 0.18, true, cm(N.zs));
  g.add(sign);
  // the shelter: at the back of the OSM platform where there is one (stop.shelterOuter)
  const shelter = makeShelter();
  place(shelter, route, stop.target - 12, stop.vienna ? -(stop.kerb + 2.4) : stop.shelterOuter !== null ? -(stop.shelterOuter - 0.6) : -3.4, 0.18, false, cm(N.zh));
  g.add(shelter);
  group.add(g);
  return sign;
}
