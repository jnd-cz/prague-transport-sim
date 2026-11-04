// The pedestrian figure's geometry built at load (#251): the middle level and the hair styles.
// The middle level is the asset lab's simplified body (no nose, ears or eyes; 6 x 4 spheres, 5-sided
// limbs), which the lab's recipe bakes into the static far figure (person-far.glb): here it stays
// skinned to the near figure's skeleton, so the same clips drive it. Ported from the recipe's person()
// (street-life-boarding v14, tools/prepare-traffic-assets.mjs; own work, GPL-3.0), with its bone
// weights; the bind pose is read from person-near.glb. Hair styles are extra pieces on the Head bone,
// in the baked hair colour so that each person's hair colour replaces them as it does the base cap.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const SKIN = 0xd5a67e, HAIR = 0x342a23, SHOE = 0x292b30, HAT = 0x2e3138;
export const SKIN_COLOR = new THREE.Color(SKIN), HAT_COLOR = new THREE.Color(HAT);

// in the Head bone's frame (+x the face, +y up, z the sides); the skull is an ellipsoid at (0, .02, 0)
// with radii (.104, .144, .103), the base hair cap one at (-.015, .107, 0) with (.105, .066, .105).
// [centre, radii, colour]; 'bald' recolours the cap (the hair colour is the skin's), 'cap' is a hat.
const STYLE_PIECES = {
  short: [],
  bald: [],
  collar: [[[-0.035, 0.005, 0], [0.095, 0.15, 0.118], HAIR]], // long at the back, down to the collar
  bob: [[[-0.02, 0.03, 0], [0.108, 0.115, 0.135], HAIR], [[0.082, 0.085, 0], [0.022, 0.028, 0.09], HAIR]], // to the jaw, wide, a flat fringe
  ponytail: [[[-0.125, 0.03, 0], [0.035, 0.09, 0.032], HAIR], [[-0.105, 0.09, 0], [0.022, 0.022, 0.022], HAIR]],
  bun: [[[-0.085, 0.135, 0], [0.048, 0.045, 0.048], HAIR]],
  cap: [[[-0.01, 0.115, 0], [0.112, 0.06, 0.11], HAT], [[0.1, 0.1, 0], [0.07, 0.012, 0.085], HAT]], // crown and peak
};
// rough shares in 100
const STYLE_SHARES = { short: 30, collar: 16, bob: 12, ponytail: 10, bun: 6, bald: 12, cap: 14 };
export const STYLES = Object.keys(STYLE_PIECES);
const STYLE_OF = Object.entries(STYLE_SHARES).flatMap(([s, w]) => Array(w).fill(s));
export const styleOf = (n) => STYLE_OF[(Math.imul(n + 7, 0x9e3779b1) >>> 0) % STYLE_OF.length];

// the bind pose of the near figure's skeleton: bone name -> { i, world, name }
export function bindPose(skinned) {
  const sk = skinned.skeleton, bones = {};
  sk.bones.forEach((b, i) => { bones[b.name] = { i, name: b.name, world: sk.boneInverses[i].clone().invert(), bone: b }; });
  return bones;
}

// the recipe's weights: a vertex at local y of bone `name` shared with the bone it bends into
function blend(name, y, pose) {
  const side = name.slice(-2), s = THREE.MathUtils.smoothstep;
  if (/^(LowerLeg|LowerArm)_/.test(name)) return [pose[name.startsWith('LowerLeg') ? 'UpperLeg' + side : 'UpperArm' + side], s(y, -0.055, 0.055)];
  if (/^(UpperLeg|UpperArm)_/.test(name)) {
    const length = name.startsWith('UpperLeg') ? 0.43 : 0.285;
    return [pose[name.startsWith('UpperLeg') ? 'LowerLeg' + side : 'LowerArm' + side], 0.5 * (1 - s(y, -length, -length + 0.07))];
  }
  if (name === 'Spine') {
    if (y > 0.15) return [pose.Chest, s(y, 0.15, 0.29)];
    if (y < 0) return [pose.Hips, 1 - s(y, -0.13, 0)];
  }
  return [null, 0];
}

// a piece in its bone's frame, placed in the bind pose, with skin weights and a vertex colour
function shaped(geo, bone, color, pose) {
  const b = pose[bone], p = geo.attributes.position, n = p.count, c = new THREE.Color(color);
  const si = new Uint16Array(n * 4), sw = new Float32Array(n * 4), col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const [alt, w] = blend(bone, p.getY(i), pose);
    si[i * 4] = b.i; si[i * 4 + 1] = alt ? alt.i : 0;
    sw[i * 4] = 1 - w; sw[i * 4 + 1] = w;
    col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
  }
  geo.deleteAttribute('uv');
  geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  geo.setAttribute('skinIndex', new THREE.BufferAttribute(si, 4));
  geo.setAttribute('skinWeight', new THREE.BufferAttribute(sw, 4));
  return geo.applyMatrix4(b.world);
}

const sphere = (p, s, seg) => new THREE.SphereGeometry(1, seg, seg === 6 ? 4 : 8).scale(...s).translate(...p);

// the middle level: { shirt, trousers, citizen_detail } geometries, the recipe's person('far') unbaked
export function middleBody(pose) {
  const parts = { shirt: [], trousers: [], citizen_detail: [] };
  const add = (g, bone, role, color = 0xffffff) => parts[role].push(shaped(g, bone, color, pose));
  const ell = (bone, p, s, role, color) => add(sphere(p, s, 6), bone, role, color);
  const limb = (bone, len, r1, r2, role, color) => {
    add(new THREE.CylinderGeometry(r1, r2, len, 5, 1).translate(0, -len / 2, 0), bone, role, color);
    ell(bone, [0, 0, 0], [r1, r1, r1], role, color);
  };
  const loft = (bone, rings, role) => { // (separate shoulders and waist: an adult silhouette)
    const pos = [], idx = [], N = 8;
    for (const [y, depth, width] of rings) for (let j = 0; j < N; j++) { const a = j / N * Math.PI * 2; pos.push(Math.cos(a) * depth, y, Math.sin(a) * width); }
    for (let i = 0; i < rings.length - 1; i++) for (let j = 0; j < N; j++) { const a = i * N + j, b = i * N + (j + 1) % N, c = (i + 1) * N + j, d = (i + 1) * N + (j + 1) % N; idx.push(a, c, b, b, c, d); }
    for (const [ring, reverse] of [[0, false], [rings.length - 1, true]]) for (let j = 1; j < N - 1; j++) idx.push(ring * N, ring * N + (reverse ? j + 1 : j), ring * N + (reverse ? j : j + 1));
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    g.computeVertexNormals();
    add(g, bone, role);
  };
  loft('Hips', [[-0.11, 0.115, 0.18], [0.025, 0.145, 0.205], [0.13, 0.135, 0.19]], 'trousers');
  loft('Spine', [[-0.13, 0.136, 0.19], [0.02, 0.147, 0.205], [0.2, 0.16, 0.245], [0.3, 0.135, 0.235], [0.345, 0.07, 0.1]], 'shirt');
  limb('Neck', 0.08, 0.064, 0.064, 'citizen_detail', SKIN);
  ell('Head', [0, 0.02, 0], [0.104, 0.144, 0.103], 'citizen_detail', SKIN);
  ell('Head', [-0.015, 0.107, 0], [0.105, 0.066, 0.105], 'citizen_detail', HAIR);
  for (const s of ['L', 'R']) {
    limb('UpperLeg_' + s, 0.43, 0.102, 0.082, 'trousers');
    limb('LowerLeg_' + s, 0.41, 0.083, 0.06, 'trousers');
    ell('Foot_' + s, [0.075, -0.025, 0], [0.17, 0.082, 0.088], 'citizen_detail', SHOE);
    limb('UpperArm_' + s, 0.285, 0.077, 0.061, 'shirt');
    limb('LowerArm_' + s, 0.25, 0.057, 0.04, 'citizen_detail', SKIN);
    ell('Hand_' + s, [0.012, -0.045, 0], [0.043, 0.075, 0.04], 'citizen_detail', SKIN);
  }
  return Object.fromEntries(Object.entries(parts).map(([k, gs]) => [k, mergeGeometries(gs)]));
}

// a detail geometry (skin, eyes, shoes, hair cap) with a hair style's pieces; seg: 12 near, 6 middle
export function withStyle(detail, style, seg, pose) {
  const pieces = STYLE_PIECES[style].map(([p, s, color]) => shaped(sphere(p, s, seg), 'Head', color, pose));
  return pieces.length ? mergeGeometries([detail, ...pieces]) : detail;
}
