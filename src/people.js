// SPDX-License-Identifier: AGPL-3.0-or-later
// Pedestrians drawn with the asset lab's figures (#251) at three levels: the full figure near the camera,
// the simplified one (no nose, ears or eyes) still animated further out, and one instanced batch of the
// static far figure beyond; each person with a hair colour and style of their own. Drawing only: it reads where the game and the
// traffic put their people (the two box crowds' instance matrices, the runners', the obstacle
// pedestrians' and the driver's box figures) and writes nothing back, so a seeded run counts the same
// with or without it. The box figures stay in the scene on a camera layer nothing draws: their
// `visible` is the game's (an obstacle pedestrian appears by it) and they come back with ?boxpeople.
// An animated figure is one primitive, one draw call (its shirt, trousers and the rest were three before), and only
// people in view are animated (the slots went by distance alone, to people behind the camera too): in the camera's view,
// or in the right mirror's near the tram (people boarding, running for the doors; the user, 2026-11-24: "The main use
// of mirrors in player's vehicle is to check is people finished boarding").
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { bindPose, middleBody, withStyle, styleOf, STYLES, SKIN_COLOR, HAT_COLOR } from './figures.js';

// (#249 step 3: our set's passengers too, src/passengerView.js: on the car they are its node's children, the animated ones
// with the lab's clips (Sit, TramStepUp, TramStepDown), the sitting down blended, the leg poses on the entry steps; the
// distant ones in two batches a car, standing and seated, person-seated-far.glb)
export const PEOPLE_FILES = ['assets/people/person-near.glb', 'assets/people/person-far.glb', 'assets/people/person-seated-far.glb'];
const CAR_FAR = 140; // a car's distant passengers at most, of each posture (105 places, those walking in and out)

// at most 64 animated figures, in within 80 m, out beyond 88 m; an animated one keeps its place against
// a newcomer up to 5 m closer (the handoff's values, which the user tried on line 17); of them the full
// figure within 40 m, out beyond 46 m. (The lab switched at 21 m, where 13 % of the figure's 1,222 pixels
// change visibly at 1080 px and the game's 62 deg: the face and the head's shading. At 40 m it is 48 pixels
// of a 42 px tall figure; #251.)
const NEAR_MAX = 64, NEAR_IN = 80, NEAR_OUT = 88, KEEP = 5, FULL_IN = 40, FULL_OUT = 46;
// in view: the camera's frustum against a sphere round the figure (its bounds, BODY_R), VIEW_IN m larger to come in and
// VIEW_OUT m to stay (as src/cars.js: the change happens off the screen's edge)
const BODY_R = 1.45, VIEW_IN = 3, VIEW_OUT = 4;
// in the mirror's view (src/mirror.js: 30 degrees, a picture about 300 px tall, 30 times a second) within MIRROR_IN m of
// its camera, kept to MIRROR_OUT: a figure at 50 m is about 20 px tall there, as one at 80 m on a 1080 px screen. Those
// seen only there are the middle figure (the full one's face is a pixel or two in it)
const MIRROR_IN = 50, MIRROR_OUT = 55;
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

// a figure's three parts as one primitive: the shirt and the trousers marked to take the person's colours (the detail
// part's hair region is marked already, maskOf)
function oneBody(shirt, trousers, detail) {
  const mark = (g, s, t) => {
    g = g.clone();
    const n = g.attributes.position.count;
    g.setAttribute('shirtMask', new THREE.BufferAttribute(new Float32Array(n).fill(s), 1));
    g.setAttribute('trousersMask', new THREE.BufferAttribute(new Float32Array(n).fill(t), 1));
    if (!g.attributes.hairMask) g.setAttribute('hairMask', new THREE.BufferAttribute(new Float32Array(n), 1));
    return g;
  };
  return mergeGeometries([mark(shirt, 1, 0), mark(trousers, 0, 1), mark(detail, 0, 0)]);
}

// a figure's material: the vertex colours times the shirt's and the trousers' colours where their masks are, the hair
// colour on the hair region; the clothes' roughness 0.65 and the rest's 0.85, as the three materials had
function oneMaterial() {
  const u = { shirt: { value: new THREE.Color() }, trousers: { value: new THREE.Color() }, hair: { value: new THREE.Color() } };
  const m = new THREE.MeshStandardMaterial({ vertexColors: true, metalness: 0, roughness: 0.85 });
  m.onBeforeCompile = (sh) => {
    sh.uniforms.shirtColor = u.shirt; sh.uniforms.trousersColor = u.trousers; sh.uniforms.hairColor = u.hair;
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float shirtMask;\nattribute float trousersMask;\nattribute float hairMask;\nuniform vec3 shirtColor;\nuniform vec3 trousersColor;\nuniform vec3 hairColor;\nvarying float vCloth;')
      .replace('#include <color_vertex>', '#include <color_vertex>\n  vColor.xyz *= mix(vec3(1.0), shirtColor, shirtMask) * mix(vec3(1.0), trousersColor, trousersMask);\n  vColor.xyz = mix(vColor.xyz, hairColor, hairMask);\n  vCloth = shirtMask + trousersMask;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vCloth;')
      .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\n  roughnessFactor = mix(roughnessFactor, 0.65, vCloth);');
  };
  m.customProgramCacheKey = () => 'people-one';
  return { m, u };
}

// responses: the loader's bodies of PEOPLE_FILES, in that order
export async function loadPeople(responses) {
  const [{ GLTFLoader }, { clone }] = await Promise.all([
    import('three/addons/loaders/GLTFLoader.js'), import('three/addons/utils/SkeletonUtils.js')]);
  const loader = new GLTFLoader();
  const [near, far, seated] = await Promise.all(responses.map(async (r, i) => {
    if (!r?.ok) throw new Error(`${PEOPLE_FILES[i]} missing`);
    return loader.parseAsync(await r.arrayBuffer(), '');
  }));
  return { near, far, seated, clone };
}

// the far figure as one instanced mesh: the shirt, trousers and hair regions of its baked vertex colours
// take each instance's colours (the instance colour and two more per-instance colours)
function farBatch(gltf, max = FAR_MAX) {
  let src = null;
  gltf.scene.updateMatrixWorld(true);
  gltf.scene.traverse((o) => { if (o.isMesh && !src) src = o; });
  const geo = src.geometry.clone().applyMatrix4(src.matrixWorld);
  geo.setAttribute('shirtMask', maskOf(geo, FAR_SHIRT));
  geo.setAttribute('trousersMask', maskOf(geo, FAR_TROUSERS));
  geo.setAttribute('hairMask', maskOf(geo, BAKED_HAIR));
  for (const k of ['instanceTrousers', 'instanceHair']) {
    const a = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3);
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
  const mesh = new THREE.InstancedMesh(geo, mat, max);
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
    // each level and style as one primitive, which the figures share
    this.bodies = Object.fromEntries(Object.entries(this.levels).map(([k, l]) =>
      [k, Object.fromEntries(STYLES.map((st) => [st, oneBody(l.shirt, l.trousers, l.citizen_detail[st])]))]));
    this.clips = Object.fromEntries(assets.near.animations.map((c) => [c.name, c]));
    this.near = new Map(); // key -> figure
    this.pool = [];
    this.track = new Map(); // key -> { x, z, dist, speed, heading, t, seen }
    this.recs = [];
    this.mats = []; // reused matrices and colours, one per record
    this.colors = [];
    this.cam = new THREE.Vector3();
    this._f = new THREE.Frustum(); this._pv = new THREE.Matrix4(); this._sp = new THREE.Sphere();
    this._mf = new THREE.Frustum(); this.mcam = new THREE.Vector3();
    this.sweep = 0;
    this.stats = { near: 0, far: 0, people: 0, figures: 0 };
  }

  _figure() {
    const f = this.pool.pop();
    if (f) { f.root.visible = true; return f; }
    const root = this.assets.clone(this.assets.near.scene), parts = [];
    root.matrixAutoUpdate = false;
    // (the three parts have one skeleton, the same joints in the same order: the first part's mesh draws the one body,
    // the other two go; skin, eyes, shoes and hair in vertex colours, the hair's replaced)
    root.traverse((o) => { if (o.isSkinnedMesh) parts.push(o); });
    const body = parts[0];
    for (const o of parts.slice(1)) o.parent.remove(o);
    const { m, u } = oneMaterial();
    body.material = m;
    // (a skinned mesh's own bounds would be computed from its pose: one sphere round the body)
    body.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0.9, 0), BODY_R);
    const mixer = new THREE.AnimationMixer(root);
    const actions = Object.fromEntries(Object.entries(this.clips).map(([k, c]) => [k, mixer.clipAction(c)]));
    this.group.add(root);
    this.stats.figures++;
    // (the legs' bones for a passenger on the entry steps, with their rest poses: the lab's two-bone leg, its thigh 0.43 m and
    // shin 0.41 m)
    const bone = (name) => root.getObjectByName(name);
    const legs = ['L', 'R'].map((s) => [bone(`UpperLeg_${s}`), bone(`LowerLeg_${s}`), bone(`Foot_${s}`)]), hips = bone('Hips');
    const rest = [hips, ...legs.flat()].filter(Boolean).map((b) => [b, b.position.clone(), b.quaternion.clone()]);
    return { root, body, u, mixer, actions, motion: null, level: null, style: null, playing: [], hips, legs, rest, ik: false };
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

  // after the game's and the traffic's step, before drawing; the traffic and the game as drawn (src/trafficView.js,
  // src/gameView.js); mirror: the right mirror's camera, posed for this frame, while the mirror is shown (else null);
  // passengers: our set's, src/passengerView.js sync's { recs, cars }
  sync(camera, trafficView, gameView, mirror = null, passengers = null) {
    this.recs.length = 0;
    if (trafficView) this._crowd(trafficView.crowd, trafficView.traffic.slots || [], 'w');
    const game = gameView?.game;
    if (game) {
      this._crowd(gameView.crowd, null, 's');
      // (a runner or a walker by their own look, kept as their passenger's, src/passengerView.js)
      game.runners.forEach((r, k) => this._box(gameView.meshOf(r), r, r.look ?? 1000 + k));
      game.obstacles.forEach((o, k) => { if (o.type === 'pedestrian') this._box(gameView.meshOf(o), o, 2000 + k); });
      if (gameView.driver) this._box(gameView.driver, game.action, 3000);
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
    // (our set's passengers: their pose is the passenger core's, src/passengerView.js; those on a car hidden with it)
    if (passengers) for (const r of passengers.recs) this.recs.push(r);
    // the nearest ones in view (a near one keeps its place): animated figures; the rest: the far batch. In the camera's
    // view, or else in the mirror's (by their distance to its camera)
    const c = camera.getWorldPosition(this.cam);
    camera.updateMatrixWorld();
    this._f.setFromProjectionMatrix(this._pv.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
    const mc = mirror && mirror.getWorldPosition(this.mcam);
    if (mirror) { mirror.updateMatrixWorld(); this._mf.setFromProjectionMatrix(this._pv.multiplyMatrices(mirror.projectionMatrix, mirror.matrixWorldInverse)); }
    for (const r of this.recs) {
      const was = this.near.has(r.key);
      r.raw = Math.hypot(r.x - c.x, r.y - c.y, r.z - c.z); r.d = r.raw - (was ? KEEP : 0);
      this._sp.center.set(r.x, r.y + 0.9, r.z);
      this._sp.radius = BODY_R + (was ? VIEW_OUT : VIEW_IN);
      r.view = r.shown !== false && r.d < (was ? NEAR_OUT - KEEP : NEAR_IN) && this._f.intersectsSphere(this._sp);
      r.mirror = false;
      if (!r.view && mc) {
        const dm = Math.hypot(r.x - mc.x, r.y - mc.y, r.z - mc.z);
        if (dm < (was ? MIRROR_OUT : MIRROR_IN) && this._mf.intersectsSphere(this._sp)) { r.view = r.mirror = true; r.d = dm - (was ? KEEP : 0); }
      }
    }
    const near = this.recs.filter((r) => r.view).sort((a, b) => a.d - b.d).slice(0, NEAR_MAX);
    const keep = new Set(near.map((r) => r.key));
    for (const [k, f] of this.near) {
      if (keep.has(k)) continue;
      f.root.visible = false;
      if (f.root.parent !== this.group) this.group.add(f.root); // (off a car: its model may go)
      this.pool.push(f); this.near.delete(k);
    }
    let full = 0, mirrored = 0;
    for (const r of near) {
      let f = this.near.get(r.key);
      const level = !r.mirror && r.raw < (f?.level === 'full' ? FULL_OUT : FULL_IN) ? 'full' : 'middle';
      if (!f) { f = this._figure(); this.near.set(r.key, f); }
      this._pose(f, r, t, level);
      if (level === 'full') full++;
      if (r.mirror) mirrored++;
    }
    let n = 0;
    // (our set's distant passengers on a car: its own batches, standing and seated, in its frame)
    const carFar = (passengers?.cars || []).map((node) => this._carFar(node));
    let onCars = 0;
    for (const r of this.recs) {
      if (keep.has(r.key)) continue;
      if (r.pax?.car >= 0 && r.parent) {
        const b = carFar[r.pax.car]?.[r.pax.seated ? 'seated' : 'standing'];
        if (b && b.count < CAR_FAR) { this._farAt(b, b.count++, r.local, r); onCars++; }
        continue;
      }
      if (n >= FAR_MAX) continue;
      this._farAt(this.far, n++, r.m.multiply(TURN), r);
    }
    this.far.count = n;
    for (const b of [this.far, ...carFar.flatMap((x) => [x.standing, x.seated])]) {
      b.instanceMatrix.needsUpdate = true;
      b.instanceColor.needsUpdate = true;
      b.geometry.attributes.instanceTrousers.needsUpdate = b.geometry.attributes.instanceHair.needsUpdate = true;
    }
    Object.assign(this.stats, { near: near.length, full, middle: near.length - full, mirror: mirrored, far: n, onCars, people: this.recs.length });
  }

  // one distant figure of a batch: its matrix, its shirt, trousers and hair
  _farAt(b, i, m, r) {
    b.setMatrixAt(i, m);
    b.setColorAt(i, r.shirt);
    const tr = TROUSERS[r.n % TROUSERS.length], h = hairFor(r.n, styleOf(r.n), true);
    b.geometry.attributes.instanceTrousers.setXYZ(i, tr.r, tr.g, tr.b);
    b.geometry.attributes.instanceHair.setXYZ(i, h.r, h.g, h.b);
  }

  // a car's batches of distant passengers (its node's children, emptied each frame): standing and seated
  _carFar(node) {
    let b = node.userData.paxFar;
    if (!b) {
      b = node.userData.paxFar = { standing: farBatch(this.assets.far, CAR_FAR), seated: farBatch(this.assets.seated, CAR_FAR) };
      b.standing.name = 'passengers-far'; b.seated.name = 'passengers-far-seated';
      node.add(b.standing, b.seated);
    }
    b.standing.count = b.seated.count = 0;
    return b;
  }

  // the animated figures on a set's cars back to the people's group, before the set's model goes (src/main.js)
  detach(model) {
    for (const f of [...this.near.values(), ...this.pool]) {
      let on = false;
      for (let o = f.root.parent; o; o = o.parent) if (o === model) { on = true; break; }
      if (on) this.group.add(f.root);
    }
  }

  _pose(f, r, t, level) {
    const style = styleOf(r.n);
    if (f.level !== level || f.style !== style) { // (the figures share the levels' bodies)
      f.body.geometry = this.bodies[level][style];
      f.level = level; f.style = style;
    }
    // (a passenger on a car: its node's child in its frame; everyone else in the world)
    const parent = r.parent || this.group;
    if (f.root.parent !== parent) parent.add(f.root);
    if (r.parent) f.root.matrix.copy(r.local);
    else f.root.matrix.multiplyMatrices(r.m, TURN);
    f.root.matrixWorldNeedsUpdate = true;
    if (f.ik) { for (const [b, p, q] of f.rest) { b.position.copy(p); b.quaternion.copy(q); } f.ik = false; }
    if (r.pax) this._posePassenger(f, r.pax);
    else {
      const motion = r.s.speed > RUN ? 'Run' : r.s.speed > STILL ? 'Walk' : 'Idle';
      this._play(f, [motion], [1]);
      // (a stride is the clip's foot travel along the figure's forward axis, scaled with the person's build)
      const a = f.actions[motion], phase = STRIDE[motion] ? r.s.dist / (STRIDE[motion] * r.w) : t * 0.5 + r.n * 0.137;
      a.time = (phase - Math.floor(phase)) * a.getClip().duration;
      f.mixer.update(0);
    }
    f.u.shirt.value.copy(r.shirt);
    f.u.trousers.value.copy(TROUSERS[r.n % TROUSERS.length]);
    f.u.hair.value.copy(hairFor(r.n, style, false));
  }

  // the clips playing, with their weights (the others stopped)
  _play(f, names, weights) {
    const key = names.join('+');
    if (f.motion !== key) {
      for (const a of f.playing) if (!names.includes(a)) f.actions[a].stop();
      for (const a of names) f.actions[a].play();
      f.playing = names; f.motion = key;
    }
    names.forEach((a, i) => f.actions[a].setEffectiveWeight(weights[i]));
  }

  // a passenger's pose from the passenger core (src/passengers/boarding-state.js, exit-flow.js), as the lab drew it: the
  // clip at its phase (a clip is 1 s), sitting down and getting up blended, and on the entry steps the legs' two-bone pose
  // (the hips' height and each foot's target, forward and up in the figure's frame)
  _posePassenger(f, p) {
    const has = (m) => !!f.actions[m];
    if (p.blend && has(p.blend.from) && has(p.blend.to)) {
      const w = Math.min(1, Math.max(0, p.blend.weight));
      this._play(f, [p.blend.from, p.blend.to], [1 - w, w]);
      for (const m of [p.blend.from, p.blend.to]) f.actions[m].time = 0;
    } else {
      const motion = has(p.motion) ? p.motion : 'Idle';
      this._play(f, [motion], [1]);
      const a = f.actions[motion];
      a.time = (p.phase - Math.floor(p.phase)) * a.getClip().duration;
    }
    f.mixer.update(0);
    const L = p.legPose;
    if (!L || !f.hips || !Number.isFinite(L.hipsHeight) || L.feet?.length !== 2) return;
    f.hips.position.y = L.hipsHeight;
    L.feet.forEach(({ x, y }, i) => {
      const [up, low, foot] = f.legs[i];
      if (!up || !low || !foot) return;
      const dy = y - (L.hipsHeight - 0.015), A = 0.43, B = 0.41;
      const k = -Math.acos(Math.min(0.9999, Math.max(-0.9999, (x * x + dy * dy - A * A - B * B) / (2 * A * B))));
      const u = Math.atan2(x, -dy) - Math.atan2(B * Math.sin(k), A + B * Math.cos(k));
      up.rotation.set(0, 0, u); low.rotation.set(0, 0, k); foot.rotation.set(0, 0, -u - k);
    });
    f.ik = true;
  }
}
