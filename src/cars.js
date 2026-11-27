// SPDX-License-Identifier: AGPL-3.0-or-later
// The street vehicles as drawn (#250, #723): the five types' models (src/carTypes.js, assets/cars/) where the box cars
// stand. As with the walkers' figures (src/people.js), the rules and the checks keep the box cars (src/models.js makeCar,
// sized to their type by fitCar), posed by the steps and between them (src/between.js); before a draw this moves them
// to a camera layer no camera draws and draws each type's models instanced at their poses. Every car in the camera's view
// within NEAR_IN m of it (until NEAR_OUT) is the near model: its wheels rolling by the distance and the front ones steering by the
// curve driven, its lamps lit by its state (the headlamps as daytime lights, the brake lamps while it slows or stands,
// its indicators), its plates; the rest the far model, one primitive. A car's paint is its box car's colour, on the far
// model too (its baked paint, the near model's colour, takes it); its fade is one value, a dissolve (no sorting).
// Draw calls: per type the near body, lamps and plates and the far model, and the wheels of all types: 21 however many
// cars (a box car drew 7: up to about 150, #723). ?boxcars keeps the box cars.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { CAR_TYPES, carFiles } from './carTypes.js';

export const CAR_FILES = CAR_TYPES.flatMap((t) => { const f = carFiles(t); return [f.near, f.far]; });
const HIDDEN = 1; // (src/people.js: the camera layer of the box figures, which no camera draws)
// the plates' atlas: COLS × ROWS plates of PW × PH px; a car keeps its plate's cell while it is about (a cell is taken
// back from one no longer near, the longest gone first, when none is free)
const COLS = 4, ROWS = 16, PW = 256, PH = 64;
// near: within 65 m of the camera (out beyond 73 m; the asset lab's handoff's distances, docs/assets-inventory.md) and in
// its view (a sphere of the car's half length and VIEW_IN m, kept to VIEW_OUT m: wider than the car, so it changes
// models off the picture): cars behind it or beside it take no place. NEAR_MAX, the atlas's cells, is only a bound: a near car costs no draw call, about 2,000 triangles more than
// the far model (the handoff's 8 were for near cars drawn each as its own copy, about 14 draw calls a car). FAR_MAX far
// ones of a type
export const NEAR_MAX = COLS * ROWS, NEAR_IN = 65, NEAR_OUT = 73, VIEW_IN = 3, VIEW_OUT = 4;
// and in the right mirror's view within MIRROR_IN m of its camera (kept to MIRROR_OUT), while it is shown: the cars beside
// and behind the tram with their indicators (one turning across the tracks, to warn with the bell) and brake lamps
// (maintainer, 2026-11-24). The mirror's
// picture is about 300 px tall for 30 degrees: a car at 50 m there is as tall as one at about 85 m on a 1080 px screen
export const MIRROR_IN = 50, MIRROR_OUT = 55;
const FAR_MAX = 64;
const BODY = new Set(['paint', 'glass', 'trim', 'alloy', 'cargo_door']);
const LAMPS = ['headlamp', 'brake', 'indicator_left', 'indicator_right'];
const TURN = new THREE.Matrix4().makeRotationY(-Math.PI / 2); // the models face +X (right +Z), the game's cars +Z (right -X)
// the lamps as lit (linear): headlamps warm white, brake lamps red, indicators amber; the headlamps by day as daytime
// running lamps
const LIT = { head: 0.45 };
const STEER_MAX = 0.55; // rad (the lab's "±30° visual steering")

// responses: the loader's bodies of CAR_FILES, in that order -> { [type id]: { near, far } } (glTF scenes)
export async function loadCars(responses) {
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const loader = new GLTFLoader();
  const scenes = await Promise.all(responses.map(async (r, i) => {
    if (!r?.ok) throw new Error(`${CAR_FILES[i]} missing`);
    return (await loader.parseAsync(await r.arrayBuffer(), '')).scene;
  }));
  return Object.fromEntries(CAR_TYPES.map((t, i) => [t.id, { near: scenes[2 * i], far: scenes[2 * i + 1] }]));
}

// a vertex attribute of n floats a vertex, every vertex `v`
const filled = (count, n, v) => new THREE.BufferAttribute(new Float32Array(count * n).fill(v), n);
// a geometry's vertex colours as rgb (the GLBs' COLOR_0 is rgba): or every vertex `c`
function rgb(g, c) {
  const n = g.attributes.position.count, a = new Float32Array(n * 3), col = g.attributes.color;
  for (let i = 0; i < n; i++) {
    a[3 * i] = col ? col.getX(i) : c.r; a[3 * i + 1] = col ? col.getY(i) : c.g; a[3 * i + 2] = col ? col.getZ(i) : c.b;
  }
  return new THREE.BufferAttribute(a, 3);
}
// a mesh's geometry in its model's frame with only the attributes named (and its colours as rgb)
function baked(mesh, keep) {
  mesh.updateWorldMatrix(true, false);
  const g = mesh.geometry.clone().applyMatrix4(mesh.matrixWorld);
  g.setAttribute('color', rgb(g, mesh.material.color));
  for (const k of Object.keys(g.attributes)) if (!keep.includes(k)) g.deleteAttribute(k);
  return g;
}
const meshesOf = (root) => { const out = []; root.traverse((o) => { if (o.isMesh) out.push(o); }); return out; };

// the shaders' changes: a dissolve by the instance's fade (a fragment drawn where a fixed per-pixel threshold is under the
// fade), and `decl` / `vert` in the vertex shader (attributes; the colour, replacing three's color_vertex)
function patch(mat, name, decl, vert, uv = '') {
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', `#include <common>\nattribute float instanceFade;\nvarying float vFade;\n${decl}`)
      .replace('#include <begin_vertex>', '#include <begin_vertex>\n  vFade = instanceFade;')
      .replace('#include <color_vertex>', vert || '#include <color_vertex>')
      .replace('#include <uv_vertex>', `#include <uv_vertex>\n${uv}`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vFade;')
      .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\n'
        + '  if (vFade < 0.999 && fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))) >= vFade) discard;');
  };
  mat.customProgramCacheKey = () => `cars-${name}`;
  return mat;
}
// the paint: vertices marked `paint` take the instance's colour
const PAINT_VERT = 'vColor = vec3(1.0);\n#ifdef USE_COLOR\n  vColor *= color;\n#endif\n#ifdef USE_INSTANCING_COLOR\n  vColor = mix(vColor, instanceColor, paint);\n#endif';
const bodyMaterial = (name) => patch(new THREE.MeshLambertMaterial({ vertexColors: true }), name, 'attribute float paint;', PAINT_VERT);

function instanced(geo, mat, n, colours = false) {
  geo.setAttribute('instanceFade', new THREE.InstancedBufferAttribute(new Float32Array(n).fill(1), 1));
  const m = new THREE.InstancedMesh(geo, mat, n);
  m.count = 0;
  m.frustumCulled = false; // (its instances are anywhere: the geometry's bounds at the origin say nothing)
  if (colours) m.setColorAt(0, new THREE.Color()); // (creates the instance colours, which the shader needs from the start)
  return m;
}

// a type's models as instanced meshes: the near body (paint, glass, trim, alloy, cargo door), its lamps, its plates;
// the far model; where its wheels are (their centres in the model's frame, the front ones steered)
function typeOf(t, { near, far }) {
  const parts = meshesOf(near), bodyGeos = [], lampGeos = [], plateGeos = [];
  let paint = null;
  for (const m of parts) {
    const name = m.material.name;
    if (BODY.has(name)) {
      const g = baked(m, ['position', 'normal', 'color']);
      g.setAttribute('paint', filled(g.attributes.position.count, 1, name === 'paint' ? 1 : 0));
      bodyGeos.push(g);
      if (name === 'paint') paint = m.material.color;
    } else if (LAMPS.includes(name)) {
      const g = baked(m, ['position', 'normal', 'color']);
      g.setAttribute('lamp', filled(g.attributes.position.count, 1, LAMPS.indexOf(name)));
      lampGeos.push(g);
    } else if (name === 'plate_text') plateGeos.push(baked(m, ['position', 'normal', 'uv']));
  }
  const wheels = ['FL', 'FR', 'RL', 'RR'].map((w) => {
    const p = near.getObjectByName(`wheel_${w}`).getWorldPosition(new THREE.Vector3());
    return { p, front: w[0] === 'F' };
  });
  const farMesh = meshesOf(far)[0], fg = baked(farMesh, ['position', 'normal', 'color']), fc = fg.attributes.color;
  // (the far model's baked paint is the near model's paint colour: its vertices take the instance's colour)
  const fp = new Float32Array(fc.count);
  for (let i = 0; i < fc.count; i++) fp[i] = Math.abs(fc.getX(i) - paint.r) + Math.abs(fc.getY(i) - paint.g) + Math.abs(fc.getZ(i) - paint.b) < 6e-3 ? 1 : 0;
  fg.setAttribute('paint', new THREE.BufferAttribute(fp, 1));
  const lamps = instanced(mergeGeometries(lampGeos), patch(new THREE.MeshBasicMaterial({ vertexColors: true }), 'lamps',
    'attribute float lamp;\nattribute vec4 instanceLamps;',
    'vColor = color;\n  float lv = lamp < 0.5 ? instanceLamps.x : lamp < 1.5 ? instanceLamps.y : lamp < 2.5 ? instanceLamps.z : instanceLamps.w;\n'
    + '  vec3 lit = lamp < 0.5 ? vec3(1.0, 0.95, 0.8) : lamp < 1.5 ? vec3(1.0, 0.04, 0.02) : vec3(1.0, 0.45, 0.02);\n'
    + '  vColor = mix(vColor * 0.6, lit, lv);'), NEAR_MAX);
  lamps.geometry.setAttribute('instanceLamps', new THREE.InstancedBufferAttribute(new Float32Array(NEAR_MAX * 4), 4));
  return {
    t, wheels,
    body: instanced(mergeGeometries(bodyGeos), bodyMaterial('body'), NEAR_MAX, true),
    lamps,
    plateGeo: mergeGeometries(plateGeos),
    far: instanced(fg, bodyMaterial('far'), FAR_MAX, true),
  };
}

// a fictional registration (the lab's: "fictional generated plates tied to the canonical internal entity id"): a Prague
// one's shape, a digit, A, a digit or letter, then four digits, from the car's number
function registration(n) {
  let h = Math.imul((n | 0) ^ 0x2545f491, 0x9e3779b1);
  const next = (k) => { h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d); return ((h >>> 0) % k); };
  const mid = '0123456789ABCDEFHJKLMNPRSTUVXYZ';
  return `${1 + next(9)}A${mid[next(mid.length)]} ${String(next(10000)).padStart(4, '0')}`;
}

export class Cars {
  constructor(scene, assets) {
    this.group = new THREE.Group();
    this.group.name = 'cars';
    scene.add(this.group);
    this.types = new Map();
    for (const t of CAR_TYPES) {
      const k = typeOf(t, assets[t.id]);
      this.types.set(t, k);
      this.group.add(k.body, k.lamps, k.far);
    }
    // the plates of all types, one mesh a type, from one atlas
    this.cv = document.createElement('canvas');
    this.cv.width = COLS * PW; this.cv.height = ROWS * PH;
    this.atlas = new THREE.CanvasTexture(this.cv);
    this.atlas.colorSpace = THREE.SRGBColorSpace;
    this.atlas.anisotropy = 4;
    const plateMat = patch(new THREE.MeshLambertMaterial({ map: this.atlas }), 'plates', 'attribute vec2 instancePlate;', '',
      `#ifdef USE_MAP\n  vMapUv = (vMapUv + instancePlate) * vec2(${1 / COLS}, ${1 / ROWS});\n#endif`);
    for (const k of this.types.values()) {
      k.plates = instanced(k.plateGeo, plateMat, NEAR_MAX);
      k.plates.geometry.setAttribute('instancePlate', new THREE.InstancedBufferAttribute(new Float32Array(NEAR_MAX * 2), 2));
      this.group.add(k.plates);
    }
    // the wheels of all types: the hatchback's wheel at a radius of 1 m, each scaled to its type's radius (the five
    // types' wheels are one mesh at their radii, 0.232 m wide)
    const w = meshesOf(assets[CAR_TYPES[0].id].near).find((m) => m.material.name === 'wheel_vertex');
    const wg = w.geometry.clone();
    wg.setAttribute('color', rgb(wg, w.material.color));
    for (const k of Object.keys(wg.attributes)) if (!['position', 'normal', 'color'].includes(k)) wg.deleteAttribute(k);
    wg.scale(1 / CAR_TYPES[0].wheelRadius, 1 / CAR_TYPES[0].wheelRadius, 1);
    this.wheels = instanced(wg, patch(new THREE.MeshLambertMaterial({ vertexColors: true }), 'wheels', '', ''), NEAR_MAX * 4);
    this.group.add(this.wheels);
    this.free = Array.from({ length: COLS * ROWS }, (_, i) => i); // the atlas's free cells
    this.cell = new Map();   // a near car's key -> its plate's cell
    this.track = new Map();  // key -> what it did: { x, z, yaw, t, speed, dist, steer, brake, seen }
    this.near = new Set();   // the keys drawn near
    this.recs = [];
    this.pool = [];
    this.sweep = 0;
    this.stats = { cars: 0, near: 0, far: 0 };
    this._m = new THREE.Matrix4(); this._w = new THREE.Matrix4(); this._q = new THREE.Quaternion();
    this._p = new THREE.Vector3(); this._s = new THREE.Vector3(); this._e = new THREE.Euler(0, 0, 0, 'YXZ');
    this._c = new THREE.Color(); this._cam = new THREE.Vector3();
    this._f = new THREE.Frustum(); this._pv = new THREE.Matrix4(); this._sp = new THREE.Sphere();
    this._mf = new THREE.Frustum(); this._mcam = new THREE.Vector3();
  }

  // a box car to draw: `key` its identity (a plate and a wheel's roll belong to it), `n` its number (its plate)
  _box(m, key, n, parked = false) {
    if (!m?.parent || !m.visible) return;
    const type = m.userData.type, alpha = m.userData.alpha ?? 1;
    if (!type || alpha <= 0) return;
    if (!m.userData.carsHidden) { m.traverse((o) => o.layers.set(HIDDEN)); m.userData.carsHidden = true; }
    m.updateWorldMatrix(true, false);
    const r = this.pool[this.recs.length] ||= { m: new THREE.Matrix4() }; // (the records are reused: no garbage a frame, #723)
    Object.assign(r, { key, n, type, alpha, parked, signal: m.userData.signal ?? null, paint: m.children[0]?.material?.color, s: null });
    m.matrixWorld.decompose(this._p, this._q, this._s);
    r.m.compose(this._p, this._q, this._s.set(1, 1, 1)).multiply(TURN);
    r.x = this._p.x; r.y = this._p.y; r.z = this._p.z;
    this._e.setFromQuaternion(this._q, 'YXZ');
    r.yaw = this._e.y;
    this.recs.push(r);
  }

  // after the game's and the traffic's step, before drawing (as People.sync); trafficView: src/trafficView.js, gameView:
  // src/gameView.js (the parked cars and the signalled crossings' cars, by their box cars there); mirror: the right
  // mirror's camera, posed for this frame, while the mirror is shown (else null)
  sync(camera, trafficView, gameView, mirror = null) {
    this.recs.length = 0;
    if (trafficView) for (const [c, m] of trafficView.cars) this._box(m, c.id === undefined ? c : `t${c.id}`, c.id ?? 0);
    const game = gameView?.game;
    if (game) {
      game.obstacles.forEach((o, k) => { if (o.type === 'parked') this._box(gameView.obstacles.get(o), o, 50000 + k, o.state === 'idle' || o.state === 'waiting'); });
      game.signals.forEach((sig, i) => (sig.cars || []).forEach((c) => this._box(gameView.crossCars.get(c), c, 60000 + i * 100 + c.model)));
    }
    const t = game ? game.clock : 0, sweep = ++this.sweep;
    // what each did since the last drawn frame: its distance (the wheels' roll), speed (the brake lamps), the curve
    // driven (the steering: the heading's change by the distance, the wheelbase's angle to it)
    for (const r of this.recs) {
      let s = this.track.get(r.key);
      if (!s) { s = { x: r.x, z: r.z, yaw: r.yaw, t, speed: 0, dist: 0, steer: 0, brake: 0 }; this.track.set(r.key, s); }
      const dt = t - s.t, d = Math.hypot(r.x - s.x, r.z - s.z);
      if (dt > 0 && dt < 1 && d < 8) {
        const v = d / dt, a = (v - s.speed) / dt;
        let dy = r.yaw - s.yaw;
        dy -= Math.round(dy / (2 * Math.PI)) * 2 * Math.PI;
        // (backwards: the heading's opposite to the way it moved)
        const fwd = d > 1e-4 ? Math.sign((r.x - s.x) * Math.sin(r.yaw) + (r.z - s.z) * Math.cos(r.yaw)) || 1 : 1;
        s.dist += fwd * d;
        if (d > 0.02) {
          const want = Math.max(-STEER_MAX, Math.min(STEER_MAX, Math.atan((r.type.wheelbase * dy) / (fwd * d))));
          s.steer += (want - s.steer) * Math.min(1, dt * 4);
        }
        s.brake = v < 0.3 || a < -0.6 ? 0.25 : Math.max(0, s.brake - dt); // (held 0.25 s past the braking: no flicker)
        s.speed += (v - s.speed) * Math.min(1, dt * 6);
      } else if (dt >= 1 || d >= 8) { s.speed = 0; s.brake = 0; }
      s.x = r.x; s.z = r.z; s.yaw = r.yaw; s.t = t; s.seen = sweep;
      r.s = s;
    }
    for (const [k, s] of this.track) {
      if (s.seen === sweep) continue;
      this.track.delete(k);
      const i = this.cell.get(k);
      if (i !== undefined) { this.free.push(i); this.cell.delete(k); }
    }
    // the ones in view within NEAR_IN (a near one keeps its place until NEAR_OUT and VIEW_OUT), or else in the mirror's
    // within MIRROR_IN (by their distance to its camera): the near model, the nearest NEAR_MAX; the rest: the far one
    const c = camera.getWorldPosition(this._cam);
    camera.updateMatrixWorld();
    this._f.setFromProjectionMatrix(this._pv.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
    const mc = mirror && mirror.getWorldPosition(this._mcam);
    if (mirror) { mirror.updateMatrixWorld(); this._mf.setFromProjectionMatrix(this._pv.multiplyMatrices(mirror.projectionMatrix, mirror.matrixWorldInverse)); }
    for (const r of this.recs) {
      const was = this.near.has(r.key);
      r.raw = Math.hypot(r.x - c.x, r.y - c.y, r.z - c.z);
      r.d = r.raw - (was ? NEAR_OUT - NEAR_IN : 0);
      this._sp.center.set(r.x, r.y, r.z);
      this._sp.radius = r.type.length / 2 + (was ? VIEW_OUT : VIEW_IN);
      r.view = r.d < NEAR_IN && this._f.intersectsSphere(this._sp);
      r.mirror = false;
      if (!r.view && mc) {
        const dm = Math.hypot(r.x - mc.x, r.y - mc.y, r.z - mc.z);
        if (dm < (was ? MIRROR_OUT : MIRROR_IN) && this._mf.intersectsSphere(this._sp)) { r.view = r.mirror = true; r.d = dm; }
      }
    }
    const near = this.recs.filter((r) => r.view).sort((a, b) => a.d - b.d).slice(0, NEAR_MAX);
    const keep = new Set(near.map((r) => r.key));
    // (one no longer near keeps its plate's cell, moved to the end of the order: the cells are taken back first-gone first)
    for (const k of this.near) {
      if (keep.has(k)) continue;
      this.near.delete(k);
      const i = this.cell.get(k);
      if (i !== undefined) { this.cell.delete(k); this.cell.set(k, i); }
    }
    for (const k of this.types.values()) { k.body.count = k.lamps.count = k.plates.count = k.far.count = 0; }
    let wheels = 0;
    const clock = t;
    for (const r of near) {
      this.near.add(r.key);
      const k = this.types.get(r.type), i = k.body.count++;
      k.lamps.count++; k.plates.count++;
      k.body.setMatrixAt(i, r.m); k.lamps.setMatrixAt(i, r.m); k.plates.setMatrixAt(i, r.m);
      k.body.setColorAt(i, r.paint || this._c.set(0x808080));
      for (const mesh of [k.body, k.lamps, k.plates]) mesh.geometry.attributes.instanceFade.setX(i, r.alpha);
      const on = r.signal !== null; // (the box car's indicator, blinking by the traffic's clock: src/trafficView.js)
      k.lamps.geometry.attributes.instanceLamps.setXYZW(i, r.parked ? 0 : LIT.head, r.parked ? 0 : r.s.brake > 0 ? 1 : 0,
        on && r.signal === 'left' ? 1 : 0, on && r.signal === 'right' ? 1 : 0);
      let cell = this.cell.get(r.key);
      if (cell === undefined) {
        cell = this.free.pop();
        if (cell === undefined) for (const [k, i] of this.cell) if (!keep.has(k)) { cell = i; this.cell.delete(k); break; }
        this.cell.set(r.key, cell ??= 0);
        this._plate(cell, registration(r.n));
      }
      k.plates.geometry.attributes.instancePlate.setXY(i, cell % COLS, ROWS - 1 - Math.floor(cell / COLS));
      for (const w of k.wheels) {
        const rad = r.type.wheelRadius;
        this._w.makeRotationZ(-r.s.dist / rad);
        // (steered about Y: a left turn, the yaw growing, turns the model's +X towards its left, -Z; the GLB's four wheels
        // are one mesh, unmirrored)
        if (w.front) this._w.premultiply(this._m.makeRotationY(r.s.steer));
        this._w.premultiply(this._m.makeTranslation(w.p.x, w.p.y, w.p.z)).multiply(this._m.makeScale(rad, rad, 1));
        this.wheels.setMatrixAt(wheels, this._w.premultiply(r.m));
        this.wheels.geometry.attributes.instanceFade.setX(wheels, r.alpha);
        wheels++;
      }
    }
    this.wheels.count = wheels;
    let far = 0;
    for (const r of this.recs) {
      if (keep.has(r.key)) continue;
      const k = this.types.get(r.type);
      if (k.far.count >= FAR_MAX) continue;
      const i = k.far.count++;
      k.far.setMatrixAt(i, r.m);
      k.far.setColorAt(i, r.paint || this._c.set(0x808080));
      k.far.geometry.attributes.instanceFade.setX(i, r.alpha);
      far++;
    }
    for (const k of [...this.types.values()]) {
      for (const mesh of [k.body, k.lamps, k.plates, k.far]) {
        mesh.instanceMatrix.needsUpdate = true;
        mesh.geometry.attributes.instanceFade.needsUpdate = true;
        if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      }
      k.lamps.geometry.attributes.instanceLamps.needsUpdate = true;
      k.plates.geometry.attributes.instancePlate.needsUpdate = true;
    }
    this.wheels.instanceMatrix.needsUpdate = true;
    this.wheels.geometry.attributes.instanceFade.needsUpdate = true;
    Object.assign(this.stats, { cars: this.recs.length, near: near.length, mirror: near.filter((r) => r.mirror).length, far, clock });
  }

  // a plate in the atlas's cell: white with the blue EU band, black characters
  _plate(cell, text) {
    const g = this.cv.getContext('2d'), x = (cell % COLS) * PW, y = Math.floor(cell / COLS) * PH;
    g.fillStyle = '#f4f4f0'; g.fillRect(x, y, PW, PH);
    g.fillStyle = '#1d3f9a'; g.fillRect(x, y, PW * 0.1, PH);
    g.fillStyle = '#f4f4f0'; g.font = `bold ${PH * 0.28}px Arial, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('CZ', x + PW * 0.05, y + PH * 0.75);
    g.fillStyle = '#151515'; g.font = `bold ${PH * 0.66}px "Arial Narrow", Arial, sans-serif`;
    g.fillText(text, x + PW * 0.55, y + PH * 0.54, PW * 0.86);
    g.strokeStyle = '#151515'; g.lineWidth = 3; g.strokeRect(x + 1.5, y + 1.5, PW - 3, PH - 3);
    this.atlas.needsUpdate = true;
  }
}
