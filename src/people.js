// SPDX-License-Identifier: AGPL-3.0-or-later
// Pedestrians drawn with the asset lab's figures (#251) at three levels: the full figure near the camera,
// the simplified one (no nose, ears or eyes) still animated further out, and one instanced batch of the
// static far figure beyond; each person with a hair colour and style of their own. Drawing only: it reads where the game and the
// traffic put their people (the two box crowds' instance matrices, the runners', the obstacle
// pedestrians' and the driver's box figures) and writes nothing back, so a seeded run counts the same
// with or without it. The box figures stay in the scene on a camera layer nothing draws: their
// `visible` is the game's (an obstacle pedestrian appears by it) and they come back with ?boxpeople.
import * as THREE from 'three';
import { bindPose, middleBody, withStyle, styleOf, STYLES, SKIN_COLOR, HAT_COLOR } from './figures.js';

export const PEOPLE_FILES = ['assets/people/person-near.glb', 'assets/people/person-far.glb'];

// at most 64 animated figures, in within 80 m, out beyond 88 m; an animated one keeps its place against
// a newcomer up to 5 m closer (the handoff's values, which the user tried on line 17); of them the full
// figure within 40 m, out beyond 46 m. (The lab switched at 21 m, where 13 % of the figure's 1,222 pixels
// change visibly at 1080 px and the game's 62 deg: the face and the head's shading. At 40 m it is 48 pixels
// of a 42 px tall figure; #251.)
const NEAR_MAX = 64, NEAR_IN = 80, NEAR_OUT = 88, KEEP = 5, FULL_IN = 40, FULL_OUT = 46;
// one Walk cycle covers 16/15 m, one Run cycle 2.15 m (the lab's catalog.json); faster than RUN: running
const STRIDE = { Walk: 16 / 15, Run: 2.15 }, RUN = 2.4, STILL = 0.25;
const FAR_MAX = 320;
const HIDDEN = 1; // the camera layer of the box figures: no camera draws it
const TURN = new THREE.Matrix4().makeRotationY(-Math.PI / 2); // the figures face +X, the game's models +Z
const TROUSERS = [0x303e50, 0x393532, 0x48515b, 0x2b2b2b, 0x4a4036, 0x1f2a3a].map((c) => new THREE.Color(c));
// the far figure's baked shirt and trouser colours (person-far.glb), replaced per instance
const FAR_SHIRT = new THREE.Color(0x416c79), FAR_TROUSERS = new THREE.Color(0x2b3446);
// both figures' baked hair colour (the near one's hair: 86 vertices on the Head bone), and the hair
// colours given instead, with rough shares in 100 (dark brown and brown the most; grey for the older)
const BAKED_HAIR = new THREE.Color(0x342a23);
const HAIRS = [[0x342a23, 30], [0x1e1a18, 14], [0x4e3627, 20], [0x6e5038, 10], [0x9a7a52, 7], [0xc2a26e, 4],
  [0x6f3820, 4], [0x8a8782, 7], [0xc4c2bc, 4]].flatMap(([c, w]) => Array(w).fill(new THREE.Color(c)));
const hairOf = (n) => HAIRS[(Math.imul(n + 1, 2654435761) >>> 0) % HAIRS.length];
// the colour where the hair is: a bald head's cap is skin, a cap's wearer shows the cap at a distance
const hairFor = (n, style, far) => style === 'bald' ? SKIN_COLOR : far && style === 'cap' ? HAT_COLOR : hairOf(n);
// each person's build: height 0.88-1.05 of the figure's 1.845 m (1.62-1.94 m), width 0.92-1.08; it
// replaces the stop crowd's own height scale (0.85-1.15 of the box figure)
const unit = (n, k) => (Math.imul(n + k, 0x85ebca6b) >>> 0) / 4294967296;
const buildOf = (n) => [0.92 + 0.16 * unit(n, 11), 0.88 + 0.17 * unit(n, 3)];
function rescale(m, w, h) { // (keeps the rotation and the position)
  const e = m.elements;
  for (const [c, k] of [[0, w], [4, h], [8, w]]) {
    const f = k / (Math.hypot(e[c], e[c + 1], e[c + 2]) || 1);
    e[c] *= f; e[c + 1] *= f; e[c + 2] *= f;
  }
}

// 1 where a vertex has colour c (a region of the baked vertex colours), else 0
function maskOf(geo, c) {
  const col = geo.attributes.color, m = new Float32Array(col.count);
  for (let i = 0; i < col.count; i++) m[i] = Math.abs(col.getX(i) - c.r) < 2e-3 && Math.abs(col.getY(i) - c.g) < 2e-3 && Math.abs(col.getZ(i) - c.b) < 2e-3 ? 1 : 0;
  return new THREE.BufferAttribute(m, 1);
}

// responses: the loader's bodies of PEOPLE_FILES, in that order
export async function loadPeople(responses) {
  const [{ GLTFLoader }, { clone }] = await Promise.all([
    import('three/addons/loaders/GLTFLoader.js'), import('three/addons/utils/SkeletonUtils.js')]);
  const loader = new GLTFLoader();
  const [near, far] = await Promise.all(responses.map(async (r, i) => {
    if (!r?.ok) throw new Error(`${PEOPLE_FILES[i]} missing`);
    return loader.parseAsync(await r.arrayBuffer(), '');
  }));
  return { near, far, clone };
}

// the far figure as one instanced mesh: the shirt, trousers and hair regions of its baked vertex colours
// take each instance's colours (the instance colour and two more per-instance colours)
function farBatch(gltf) {
  let src = null;
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((o) => { if (o.isMesh && !src) src = o; });
  const geo = src.geometry.clone().applyMatrix4(src.matrixWorld);
  geo.setAttribute('shirtMask', maskOf(geo, FAR_SHIRT));
  geo.setAttribute('trousersMask', maskOf(geo, FAR_TROUSERS));
  geo.setAttribute('hairMask', maskOf(geo, BAKED_HAIR));
  for (const k of ['instanceTrousers', 'instanceHair']) {
    const a = new THREE.InstancedBufferAttribute(new Float32Array(FAR_MAX * 3), 3);
    a.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute(k, a);
  }
  const mat = src.material.clone();
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float shirtMask;\nattribute float trousersMask;\nattribute float hairMask;\nattribute vec3 instanceTrousers;\nattribute vec3 instanceHair;')
      .replace('#include <color_vertex>', '#include <color_vertex>\n#ifdef USE_INSTANCING_COLOR\n  vColor.xyz = mix(color.xyz, instanceColor.xyz, shirtMask);\n  vColor.xyz = mix(vColor.xyz, instanceTrousers, trousersMask);\n  vColor.xyz = mix(vColor.xyz, instanceHair, hairMask);\n#endif');
  };
  mat.customProgramCacheKey = () => 'people-far';
  const mesh = new THREE.InstancedMesh(geo, mat, FAR_MAX);
  mesh.name = 'people-far';
  mesh.setColorAt(0, FAR_SHIRT); // (creates the instance colours, which the shader needs from the start)
  mesh.count = 0;
  mesh.frustumCulled = false; // instances anywhere on the map
  mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  return mesh;
}

export class People {
  constructor(scene, assets) {
    this.assets = assets;
    this.group = new THREE.Group();
    this.group.name = 'people';
    scene.add(this.group);
    this.far = farBatch(assets.far);
    this.group.add(this.far);
    // the levels' geometries, which the figures share: the full one from person-near.glb, the middle one
    // built from the lab's recipe on the same skeleton; the detail part (skin, eyes, shoes, hair) per style
    const part = {};
    assets.near.scene.traverse((o) => { if (o.isSkinnedMesh) part[o.material.name] = o; });
    const pose = bindPose(part.citizen_detail), mid = middleBody(pose);
    const styled = (detail, seg) => Object.fromEntries(STYLES.map((s) => [s, withStyle(detail, s, seg, pose)]));
    this.levels = {
      full: { shirt: part.shirt.geometry, trousers: part.trousers.geometry, citizen_detail: styled(part.citizen_detail.geometry, 12) },
      middle: { shirt: mid.shirt, trousers: mid.trousers, citizen_detail: styled(mid.citizen_detail, 6) },
    };
    for (const l of Object.values(this.levels)) for (const g of Object.values(l.citizen_detail)) g.setAttribute('hairMask', maskOf(g, BAKED_HAIR));
    this.clips = Object.fromEntries(assets.near.animations.map((c) => [c.name, c]));
    this.near = new Map(); // key -> figure
    this.pool = [];
    this.track = new Map(); // key -> { x, z, dist, speed, heading, t, seen }
    this.recs = [];
    this.mats = []; // reused matrices and colours, one per record
    this.colors = [];
    this.cam = new THREE.Vector3();
    this.sweep = 0;
    this.stats = { near: 0, far: 0, people: 0, figures: 0 };
  }

  _figure() {
    const f = this.pool.pop();
    if (f) { f.root.visible = true; return f; }
    const root = this.assets.clone(this.assets.near.scene), mats = {}, meshes = {};
    root.matrixAutoUpdate = false;
    root.traverse((o) => {
      if (!o.isMesh) return;
      const name = o.material.name;
      meshes[name] = o;
      if (name === 'shirt' || name === 'trousers') o.material = mats[name] = o.material.clone();
      if (name === 'citizen_detail') { // (skin, eyes, shoes and hair in vertex colours: the hair is replaced)
        const m = o.material = o.material.clone(), hair = mats.hair = { value: new THREE.Color() };
        m.onBeforeCompile = (sh) => {
          sh.uniforms.hairColor = hair;
          sh.vertexShader = sh.vertexShader
            .replace('#include <common>', '#include <common>\nattribute float hairMask;\nuniform vec3 hairColor;')
            .replace('#include <color_vertex>', '#include <color_vertex>\n  vColor.xyz = mix(vColor.xyz, hairColor, hairMask);');
        };
        m.customProgramCacheKey = () => 'people-hair';
      }
      // (a skinned mesh's own bounds would be computed from its pose: one sphere round the body)
      if (o.isSkinnedMesh) o.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), 1.45);
    });
    const mixer = new THREE.AnimationMixer(root);
    const actions = Object.fromEntries(Object.entries(this.clips).map(([k, c]) => [k, mixer.clipAction(c)]));
    this.group.add(root);
    this.stats.figures++;
    return { root, mats, meshes, mixer, actions, motion: null, level: 'full', style: 'short' };
  }

  _matrix(n) { return this.mats[n] || (this.mats[n] = new THREE.Matrix4()); }
  _color(n) { return this.colors[n] || (this.colors[n] = new THREE.Color()); }

  // a box crowd (one InstancedMesh); slots: the walkers' records by instance (empty slots: null)
  _crowd(crowd, slots, tag) {
    if (!crowd) return;
    crowd.layers.set(HIDDEN);
    for (let i = 0; i < crowd.count; i++) {
      const slot = slots ? slots[i] : null;
      if (slots && !slot) continue;
      const m = this._matrix(this.recs.length);
      crowd.getMatrixAt(i, m);
      const e = m.elements;
      if (e[0] === 0 && e[5] === 0 && e[10] === 0) continue; // (an empty slot: scale 0)
      // (the stop crowd's people are drawn in order of their stops, so their index shifts when a stop
      // drops out of range: keyed, and their hair and trousers chosen, by where they stand)
      const gx = Math.round(e[12] * 10), gz = Math.round(e[14] * 10);
      const key = slot || `${tag}${gx},${gz}`, n = slot ? i : (Math.imul(gx, 73856093) ^ Math.imul(gz, 19349663)) >>> 0;
      const shirt = this._color(this.recs.length);
      if (crowd.instanceColor) crowd.getColorAt(i, shirt);
      this.recs.push({ key, m, x: e[12], y: e[13], z: e[14], shirt, n, box: null });
    }
  }

  // a box figure (makePerson: legs, torso, head), facing the way it moves
  _box(g, key, n) {
    if (!g?.parent || !g.visible) return;
    if (!g.userData.peopleHidden) { g.traverse((o) => o.layers.set(HIDDEN)); g.userData.peopleHidden = true; }
    const p = g.position;
    this.recs.push({ key, m: this._matrix(this.recs.length), x: p.x, y: p.y, z: p.z, shirt: g.children[1]?.material?.color || FAR_SHIRT, n, box: g });
  }

  // after the game's and the traffic's step, before drawing
  sync(camera, traffic, game) {
    this.recs.length = 0;
    if (traffic) this._crowd(traffic.crowd, traffic.slots || [], 'w');
    if (game) {
      this._crowd(game.crowd, null, 's');
      game.runners.forEach((r, k) => this._box(r.mesh, r, 1000 + k));
      game.obstacles.forEach((o, k) => { if (o.type === 'pedestrian') this._box(o.mesh, o, 2000 + k); });
      if (game.action?.driver) this._box(game.action.driver, game.action, 3000);
    }
    const t = game ? game.clock : 0, sweep = ++this.sweep;
    // how far each one moved since the last drawn frame: speed, walk phase, and the box figures' heading
    for (const r of this.recs) {
      let s = this.track.get(r.key);
      if (!s) {
        s = { x: r.x, z: r.z, dist: (r.n * 0.37) % 1, speed: 0, heading: r.box ? r.box.rotation.y : 0, t };
        this.track.set(r.key, s);
      }
      const dt = t - s.t, dx = r.x - s.x, dz = r.z - s.z, d = Math.hypot(dx, dz);
      if (dt > 0 && dt < 1 && d < 8) { // (else paused, or a jump: keep the pose)
        s.speed += (d / dt - s.speed) * Math.min(1, dt * 6);
        s.dist += d;
        if (r.box && d > 0.005) s.heading = Math.atan2(dx, dz);
      } else if (dt >= 1 || d >= 8) s.speed = 0;
      s.x = r.x; s.z = r.z; s.t = t; s.seen = sweep;
      r.s = s;
      if (r.box) r.m.makeRotationY(s.heading).setPosition(r.x, r.y, r.z);
      [r.w, r.h] = buildOf(r.n);
      rescale(r.m, r.w, r.h);
    }
    for (const [k, s] of this.track) if (s.seen !== sweep) this.track.delete(k);
    // the nearest ones (a near one keeps its place): animated figures; the rest: the far batch
    const c = camera.getWorldPosition(this.cam);
    for (const r of this.recs) { r.raw = Math.hypot(r.x - c.x, r.y - c.y, r.z - c.z); r.d = r.raw - (this.near.has(r.key) ? KEEP : 0); }
    const near = this.recs.filter((r) => r.d < (this.near.has(r.key) ? NEAR_OUT - KEEP : NEAR_IN)).sort((a, b) => a.d - b.d).slice(0, NEAR_MAX);
    const keep = new Set(near.map((r) => r.key));
    for (const [k, f] of this.near) if (!keep.has(k)) { f.root.visible = false; this.pool.push(f); this.near.delete(k); }
    let full = 0;
    for (const r of near) {
      let f = this.near.get(r.key);
      const level = r.raw < (f?.level === 'full' ? FULL_OUT : FULL_IN) ? 'full' : 'middle';
      if (!f) { f = this._figure(); this.near.set(r.key, f); }
      this._pose(f, r, t, level);
      if (level === 'full') full++;
    }
    let n = 0;
    const pants = this.far.geometry.attributes.instanceTrousers, hair = this.far.geometry.attributes.instanceHair;
    for (const r of this.recs) {
      if (keep.has(r.key) || n >= FAR_MAX) continue;
      this.far.setMatrixAt(n, r.m.multiply(TURN));
      this.far.setColorAt(n, r.shirt);
      const tr = TROUSERS[r.n % TROUSERS.length], h = hairFor(r.n, styleOf(r.n), true);
      pants.setXYZ(n, tr.r, tr.g, tr.b);
      hair.setXYZ(n, h.r, h.g, h.b);
      n++;
    }
    this.far.count = n;
    this.far.instanceMatrix.needsUpdate = true;
    this.far.instanceColor.needsUpdate = true;
    pants.needsUpdate = hair.needsUpdate = true;
    Object.assign(this.stats, { near: near.length, full, middle: near.length - full, far: n, people: this.recs.length });
  }

  _pose(f, r, t, level) {
    const style = styleOf(r.n);
    if (f.level !== level || f.style !== style) { // (the figures share the levels' geometries)
      const g = this.levels[level];
      f.meshes.shirt.geometry = g.shirt;
      f.meshes.trousers.geometry = g.trousers;
      f.meshes.citizen_detail.geometry = g.citizen_detail[style];
      f.level = level; f.style = style;
    }
    f.root.matrix.multiplyMatrices(r.m, TURN);
    f.root.matrixWorldNeedsUpdate = true;
    const motion = r.s.speed > RUN ? 'Run' : r.s.speed > STILL ? 'Walk' : 'Idle';
    if (f.motion !== motion) {
      if (f.motion) f.actions[f.motion].stop();
      f.actions[motion].play();
      f.motion = motion;
    }
    // (a stride is the clip's foot travel along the figure's forward axis, scaled with the person's build)
    const a = f.actions[motion], phase = STRIDE[motion] ? r.s.dist / (STRIDE[motion] * r.w) : t * 0.5 + r.n * 0.137;
    a.time = (phase - Math.floor(phase)) * a.getClip().duration;
    f.mixer.update(0);
    if (f.mats.shirt) f.mats.shirt.color.copy(r.shirt);
    if (f.mats.trousers) f.mats.trousers.color.copy(TROUSERS[r.n % TROUSERS.length]);
    if (f.mats.hair) f.mats.hair.value.copy(hairFor(r.n, style, false));
  }
}
