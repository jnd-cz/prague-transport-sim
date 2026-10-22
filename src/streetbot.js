import * as THREE from 'three';
import { carPose } from './traffic.js';

// Street bot (debug, ?bot in the URL): drives every car lane and walks every footway of the
// traffic network where the surveyed DTM streets exist, the way the traffic places cars and
// walkers, and reports the places that look wrong:
//   car   - kerb: the drawn surface steps under the car (it drives over a kerb)
//           sidewalk: two or more wheels on a sidewalk, island, platform, greenery or steps
//           jump: the car's own height steps by more than 0.15 m within 1 m
//           tilt: rolled more than 7° (one side up a kerb)
//           float / sunk: the car hovers above / sinks into what is drawn under it
//           gap: no DTM area under the car inside the surveyed streets
//   walk  - bumpy: the drawn path surface is rough (second difference over 1 m)
//           kerb, float / sunk: as for cars
//           road: walking along the carriageway for more than 6 m
//           crossing: stepping over a normal kerb between carriageway and sidewalk (not a defect,
//           but a pedestrian crossing should have a dropped kerb)
// Findings of a kind within 15 m are merged into one place, ranked by size and count.

const CAR_BAD = new Set(['sidewalk', 'island', 'platform', 'green', 'stairs', 'water']);
const WALK_BAD = new Set(['road', 'tram', 'parking']);
export const BOT_COLORS = {
  kerb: '#ff3b30', sidewalk: '#ff9500', jump: '#af52de', tilt: '#ffcc00', float: '#34c759', sunk: '#007aff',
  gap: '#8e8e93', bumpy: '#ff2d55', crossing: '#c7c7cc', road: '#5ac8fa', 'walk-kerb': '#ff6b5e', 'walk-float': '#7be08f', 'walk-sunk': '#5fa8ff',
};

// Every triangle of the meshes cars and walkers stand on (tagged `userData.surface`), indexed
// in 2 m cells around the probe points: the height that is really drawn, not the ground function.
class Drawn {
  constructor(world, keep) {
    this.cell = 2;
    this.map = new Map();
    this.tris = [];
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
    world.traverse((m) => {
      if (!m.isMesh || !m.userData.surface) return;
      const pos = m.geometry.attributes.position, idx = m.geometry.index;
      const n = idx ? idx.count : pos.count;
      for (let i = 0; i < n; i += 3) {
        const ia = idx ? idx.getX(i) : i, ib = idx ? idx.getX(i + 1) : i + 1, ic = idx ? idx.getX(i + 2) : i + 2;
        a.fromBufferAttribute(pos, ia); b.fromBufferAttribute(pos, ib); c.fromBufferAttribute(pos, ic);
        // three.js space -> ours: x, y = -z, height = y
        const t = [a.x, -a.z, a.y, b.x, -b.z, b.y, c.x, -c.z, c.y, m.userData.surface];
        const area = (t[3] - t[0]) * (t[7] - t[1]) - (t[4] - t[1]) * (t[6] - t[0]);
        if (Math.abs(area) < 1e-4) continue; // vertical: kerb faces, walls
        const x0 = Math.floor(Math.min(t[0], t[3], t[6]) / this.cell), x1 = Math.floor(Math.max(t[0], t[3], t[6]) / this.cell);
        const y0 = Math.floor(Math.min(t[1], t[4], t[7]) / this.cell), y1 = Math.floor(Math.max(t[1], t[4], t[7]) / this.cell);
        let id = -1;
        for (let ix = x0; ix <= x1; ix++) for (let iy = y0; iy <= y1; iy++) {
          const k = ix * 100003 + iy;
          if (!keep.has(k)) continue;
          if (id < 0) { id = this.tris.length; this.tris.push(t); }
          if (!this.map.has(k)) this.map.set(k, []);
          this.map.get(k).push(id);
        }
      }
    });
  }
  // highest drawn surface between zRef - 4 and zRef + 1.2 (decks and roofs above don't count)
  at(x, y, zRef, what = false) {
    const arr = this.map.get(Math.floor(x / this.cell) * 100003 + Math.floor(y / this.cell));
    if (!arr) return null;
    let best = null;
    for (const id of arr) {
      const t = this.tris[id];
      const d = (t[4] - t[7]) * (t[0] - t[6]) + (t[6] - t[3]) * (t[1] - t[7]);
      const w1 = ((t[4] - t[7]) * (x - t[6]) + (t[6] - t[3]) * (y - t[7])) / d;
      const w2 = ((t[7] - t[1]) * (x - t[6]) + (t[0] - t[6]) * (y - t[7])) / d;
      const w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * t[2] + w2 * t[5] + w3 * t[8];
      if (z > zRef + 1.2 || z < zRef - 4) continue;
      if (best === null || z > best) { best = z; this.what = t[9]; }
    }
    return what ? [best, this.what] : best;
  }
}

const tick = () => new Promise((r) => setTimeout(r, 0));

export async function runStreetBot({ world, traffic, ground, route, progress = () => {} }) {
  const dtm = ground.dtm;
  if (!dtm) return { findings: [], stats: { note: 'no DTM for this line' } };
  const covered = (x, y) => dtm.covered(x, y);

  // 1. probe paths, 1 m steps, only inside the surveyed streets
  const paths = []; // {kind: 'car'|'walk', pts: [{x, y, hx, hy}]}
  // src: what the probe follows ('road 12', 'lane', 'walk 3'), s: position along it
  const runsOf = (kind, src, sample, length) => {
    let cur = [];
    for (let s = 0; s <= length; s += 1) {
      const p = sample(s);
      if (p && covered(p.x, p.y)) { p.src = src; p.s = s; p.L = length; cur.push(p); }
      else { if (cur.length > 3) paths.push({ kind, pts: cur }); cur = []; }
    }
    if (cur.length > 3) paths.push({ kind, pts: cur });
  };
  for (const [k, r] of traffic.roads.entries()) {
    const dirs = r.o ? [r.o] : [1, -1];
    const sels = r.o && r.w >= 7 ? [-1, 1] : [1];
    for (const dir of dirs) for (const sel of sels) {
      runsOf('car', `road ${k}`, (s0) => {
        const s = dir > 0 ? s0 : r.path.length - s0;
        const p = r.path.at(s);
        const hx = p.hx * dir, hy = p.hy * dir, lane = traffic.laneOffset(r, s, dir, sel);
        return { x: p.x + hy * lane, y: p.y - hx * lane, hx, hy };
      }, r.path.length);
    }
  }
  // cars in the lanes beside the tram (Traffic._updateStreetCars, lateral offset eased in)
  for (const dir of [1, -1]) {
    let lat = null;
    runsOf('car', 'lane', (s0) => {
      const s = dir > 0 ? s0 : route.length - s0;
      const lane = traffic.laneAt(s, dir, lat);
      if (!lane) { lat = null; return null; }
      lat = lat === null ? lane.lat : lat + (lane.lat - lat) * 0.2;
      const o = route.offset(s, lat);
      return { x: o.x, y: o.y, hx: o.hx * dir, hy: o.hy * dir };
    }, route.length);
  }
  for (const [k, w] of traffic.walks.entries()) {
    runsOf('walk', `walk ${k}`, (s) => {
      const p = w.path.at(s);
      return { x: p.x + p.hy * w.off, y: p.y - p.hx * w.off, hx: p.hx, hy: p.hy };
    }, w.path.length);
  }
  progress(`${paths.length} paths`);
  await tick();

  // 2. drawn surfaces around every probe point (car wheels reach 1.6 m)
  const keep = new Set();
  for (const P of paths) for (const p of P.pts) {
    for (let dx = -2; dx <= 2; dx += 2) for (let dy = -2; dy <= 2; dy += 2) keep.add(Math.floor((p.x + dx) / 2) * 100003 + Math.floor((p.y + dy) / 2));
  }
  const drawn = new Drawn(world, keep);
  progress(`indexed ${drawn.tris.length} drawn triangles`);
  await tick();

  // 3. drive and walk
  const raw = [];
  const flag = (kind, p, z, mag, info) => raw.push({ kind, x: p.x, y: p.y, z, mag, info, src: p.src, s: p.s, L: p.L });
  let carM = 0, walkM = 0;
  for (let pi = 0; pi < paths.length; pi++) {
    const { kind, pts } = paths[pi];
    let prev = null, prevD = null, prev2D = null, roadRun = 0, prevC = null, prev2C = null;
    for (const p of pts) {
      const { x, y, hx, hy } = p;
      if (kind === 'car') {
        carM++;
        const { z, roll } = carPose(ground, x, y, hx, hy);
        const zd = drawn.at(x, y, z);
        const cls = dtm.classAt(x, y);
        let bad = 0;
        const on = [];
        for (const [f, l] of [[1.3, 0.8], [1.3, -0.8], [-1.3, 0.8], [-1.3, -0.8]]) {
          const c = dtm.classAt(x + hx * f - hy * l, y + hy * f + hx * l);
          if (CAR_BAD.has(c)) { bad++; on.push(c); }
        }
        if (bad >= 2) flag('sidewalk', p, z, bad / 4, on.join(','));
        if (Math.abs(roll) > 0.12) flag('tilt', p, z, Math.abs(roll) * 57.3, `${(roll * 57.3).toFixed(0)}°`);
        if (cls === null) flag('gap', p, z, 1, 'no DTM area');
        if (zd === null) flag('gap', p, z, 1, 'nothing drawn');
        else {
          const gap = z - zd;
          if (gap > 0.15) flag('float', p, z, gap, `${gap.toFixed(2)} m above`);
          if (gap < -0.1) flag('sunk', p, z, -gap, `${(-gap).toFixed(2)} m below`);
        }
        if (prev !== null && Math.abs(z - prev) > 0.15) flag('jump', p, z, Math.abs(z - prev), `${(z - prev).toFixed(2)} m in 1 m`);
        // a step is a sudden change against the slope so far (steep streets are not steps)
        const slope = prevD !== null && prev2D !== null ? prevD - prev2D : 0;
        if (zd !== null && prevD !== null && Math.abs(zd - prevD - slope) > 0.12) flag('kerb', p, z, Math.abs(zd - prevD - slope), `${(zd - prevD).toFixed(2)} m drawn step`);
        prev = z; prev2D = prevD; prevD = zd;
      } else {
        walkM++;
        const z = ground.surface(x, y);
        const zd = drawn.at(x, y, z);
        const cls = dtm.classAt(x, y);
        roadRun = WALK_BAD.has(cls) ? roadRun + 1 : 0;
        if (roadRun === 6) flag('road', p, z, 1, `on ${cls}`);
        if (zd !== null) {
          const gap = z - zd;
          if (gap > 0.15) flag('walk-float', p, z, gap, `${gap.toFixed(2)} m above`);
          if (gap < -0.1) flag('walk-sunk', p, z, -gap, `${(-gap).toFixed(2)} m below`);
          const step = prevD === null ? 0 : zd - prevD;
          const jolt = step - (prevD !== null && prev2D !== null ? prevD - prev2D : 0); // against the slope so far
          // stepping between the carriageway and a raised surface over a normal kerb: real, but a
          // crossing should have a dropped kerb (listed apart, not counted as a defect)
          const kerbCross = prevC !== cls && (WALK_BAD.has(prevC) !== WALK_BAD.has(cls)) && Math.abs(step) > 0.06 && Math.abs(step) <= 0.22;
          if (kerbCross) flag('crossing', p, z, Math.abs(step), `${step.toFixed(2)} m kerb, ${prevC} → ${cls}`);
          else if (Math.abs(jolt) > 0.12) flag('walk-kerb', p, z, Math.abs(jolt), `${step.toFixed(2)} m drawn step`);
          else if (prevD !== null && prev2D !== null && prevC === cls && prev2C === cls) {
            const dd = Math.abs(zd - 2 * prevD + prev2D);
            if (dd > 0.06) flag('bumpy', p, z, dd, `${dd.toFixed(2)} m bend in 1 m`);
          }
        }
        prev2D = prevD; prevD = zd; prev2C = prevC; prevC = cls;
      }
    }
    if (pi % 50 === 0) { progress(`driving ${pi}/${paths.length}`); await tick(); }
  }

  // 4. merge each kind within 15 m into places
  const places = [];
  const grid = new Map();
  for (const f of raw.sort((a, b) => b.mag - a.mag)) {
    const gx = Math.floor(f.x / 15), gy = Math.floor(f.y / 15);
    let hit = null;
    for (let i = gx - 1; i <= gx + 1 && !hit; i++) for (let j = gy - 1; j <= gy + 1 && !hit; j++) {
      for (const P of grid.get(`${f.kind}|${i}|${j}`) || []) if (Math.hypot(P.x - f.x, P.y - f.y) < 15) { hit = P; break; }
    }
    if (hit) { hit.n++; continue; }
    const P = { ...f, n: 1 };
    places.push(P);
    const k = `${f.kind}|${gx}|${gy}`;
    if (!grid.has(k)) grid.set(k, []);
    grid.get(k).push(P);
  }
  for (const P of places) P.score = P.mag * Math.sqrt(P.n);
  places.sort((a, b) => b.score - a.score);
  const byKind = {};
  for (const f of raw) byKind[f.kind] = (byKind[f.kind] || 0) + 1;
  const placesByKind = {};
  for (const P of places) placesByKind[P.kind] = (placesByKind[P.kind] || 0) + 1;
  return { drawn, raw, findings: places, stats: { carKm: carM / 1000, walkKm: walkM / 1000, paths: paths.length, samples: byKind, places: placesByKind } };
}

// Findings panel: a list (worst first) with a filter by kind; click, or n / b, flies the camera
// to the place; markers stand at every place. Arrow keys orbit, +/- zoom.
export function showBotPanel(result, { scene, camera, label }) {
  const markers = new THREE.Group();
  scene.add(markers);
  const geo = new THREE.CylinderGeometry(0.25, 0.25, 6, 6);
  const mats = {};
  for (const P of result.findings) {
    const m = new THREE.Mesh(geo, mats[P.kind] || (mats[P.kind] = new THREE.MeshBasicMaterial({ color: BOT_COLORS[P.kind] || '#fff' })));
    m.position.set(P.x, P.z + 3, -P.y);
    markers.add(m);
  }
  const box = document.createElement('div');
  box.id = 'botPanel';
  box.style.cssText = 'position:fixed;top:10px;right:10px;width:360px;max-height:calc(100vh - 20px);overflow:auto;z-index:50;'
    + 'background:rgba(20,22,26,.9);color:#eee;font:12px/1.35 system-ui,sans-serif;padding:10px;border-radius:8px';
  const st = result.stats;
  const kinds = Object.keys(st.places || {});
  box.innerHTML = `<b>Street bot</b> · cars ${st.carKm?.toFixed(1)} km, walkers ${st.walkKm?.toFixed(1)} km<br>
    <select id="botKind" style="margin:6px 0;width:100%"><option value="">all (${result.findings.length} places)</option>
    ${kinds.map((k) => `<option value="${k}">${k} (${st.places[k]})</option>`).join('')}</select>
    <div style="opacity:.7;margin-bottom:4px">click a row or n / b · arrows orbit · + / − zoom</div><div id="botList"></div>`;
  document.body.appendChild(box);
  let list = result.findings, cur = -1, ang = 0.6, dist = 22;
  const view = () => {
    const P = list[cur];
    if (!P) return;
    camera.position.set(P.x + Math.cos(ang) * dist, P.z + dist * 0.6, -(P.y + Math.sin(ang) * dist));
    camera.lookAt(P.x, P.z, -P.y);
    box.querySelectorAll('.botRow').forEach((r, i) => { r.style.background = i === cur ? '#3a4250' : ''; });
  };
  const render = () => {
    const kind = box.querySelector('#botKind').value;
    list = result.findings.filter((P) => !kind || P.kind === kind).slice(0, 400);
    markers.children.forEach((m, i) => { m.visible = !kind || result.findings[i].kind === kind; });
    box.querySelector('#botList').innerHTML = list.map((P, i) => `<div class="botRow" data-i="${i}" style="padding:3px 4px;cursor:pointer;border-top:1px solid #333">
      <span style="color:${BOT_COLORS[P.kind]}">■</span> <b>${P.kind}</b> ${P.info} ×${P.n}<br><span style="opacity:.7">${label(P)}</span></div>`).join('');
    cur = -1;
  };
  box.querySelector('#botKind').addEventListener('change', render);
  box.addEventListener('click', (e) => {
    const r = e.target.closest('.botRow');
    if (r) { cur = +r.dataset.i; view(); }
  });
  window.addEventListener('keydown', (e) => {
    if (e.key === 'n') { cur = Math.min(list.length - 1, cur + 1); view(); }
    else if (e.key === 'b') { cur = Math.max(0, cur - 1); view(); }
    else if (e.key === 'ArrowLeft') { ang += 0.3; view(); }
    else if (e.key === 'ArrowRight') { ang -= 0.3; view(); }
    else if (e.key === '+' || e.key === '=') { dist = Math.max(6, dist * 0.8); view(); }
    else if (e.key === '-') { dist = Math.min(120, dist * 1.25); view(); }
  });
  render();
  // jump to a place (index into result.findings), selecting its kind in the list
  const go = (i) => {
    const P = result.findings[i];
    const sel = box.querySelector('#botKind');
    if (!list.includes(P)) { sel.value = P.kind; render(); }
    cur = list.indexOf(P);
    if (cur < 0) { list = [P]; cur = 0; }
    view();
  };
  return { markers, box, go };
}
