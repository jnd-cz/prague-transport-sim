// SPDX-License-Identifier: AGPL-3.0-or-later
// Low-poly models built from primitives: cars, pedestrians, signals and signs; the T3 sets (the built-in car
// in src/t3simple.js, the hybrid in src/t3h.js, conflig's classic loaded here).
import * as THREE from 'three';
import { hybridReady, makeHybridSet, setHybridLine, poseHybrid } from './t3h.js';
import { makeSimpleSet, poseSimple, t3Variant, fleetNumbers, ROUTE_BOX } from './t3simple.js';
import { hangConsist } from './consist.js';
import { signalsAt } from './lamps.js';
import { CAR_PITCH } from './tram.js';
import { drawCallSignal, drawSwitchSignal } from './ledPanels.js';
import { drawSign, drawLedPanel, drawNumberPlate, shownSize, SIGN_SCALE } from './speedSigns.js';

const lambert = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, ...extra });

// Resources that outlive one object carry userData.shared: the detailed T3's geometry and textures
// (every set shares them), the cached sign and leaf textures. disposeModel leaves them alone.
const shared = (x) => !!x.userData?.shared;
const texturesOf = (m) => Object.values(m).filter((v) => v?.isTexture);

// Frees the GPU memory of an object that leaves for good (an AI tram, a cross-street car, the last
// shift's objects): its geometries, materials and their textures. It skips the shared ones and the
// world's geometry, whose arrays are dropped after upload (main.js uploadWorld), so it could not be
// uploaded again. (Without it, every AI tram left 5 canvas textures and a material on the GPU.)
export function disposeModel(root) {
  root.traverse((o) => {
    const g = o.geometry;
    if (g && !g.userData.release && !shared(g)) g.dispose();
    if (o.isInstancedMesh) o.dispose();
    for (const m of [o.material].flat()) {
      if (!m || shared(m)) continue;
      for (const tex of texturesOf(m)) if (!shared(tex)) tex.dispose();
      m.dispose();
    }
  });
}

function canvasTexture(w, h, draw) {
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  draw(cv.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// a texture cached for the whole page (signs, plates): marked shared, so disposeModel keeps it
const keptTexture = (w, h, draw) => { const tex = canvasTexture(w, h, draw); tex.userData.shared = true; return tex; };

// The T3's number plates and cards (user photos, 2026-10-23): the route number on the roof box at
// the front and on the mirror arm (white digits on DPP blue, no border; the mirror one smaller and
// taller than wide), on the rear at the bottom of the rear window inverted (blue digits on white),
// and behind the windscreen the destination card (blue capitals on white with a blue frame, two
// lines, centred) and the run number card (white on black, on the side pane left of the frame support
// as seen from the front).
const DPP_BLUE = '#1f57a8';
// (fill: the font size as a share of the plate height; digits are ~0.72 of it)
function numberTexture(line, w, h, fg, bg, fill = 0.85) {
  return canvasTexture(w, h, (g) => {
    g.fillStyle = bg;
    g.fillRect(0, 0, w, h);
    g.fillStyle = fg;
    const text = String(line);
    let size = h * fill;
    g.font = `bold ${size}px "Arial Narrow", Arial, sans-serif`;
    while (g.measureText(text).width > w * 0.86 && size > 10) { size -= 2; g.font = `bold ${size}px "Arial Narrow", Arial, sans-serif`; }
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(text, w / 2, h / 2 + h * 0.04);
  });
}
// A T3M's displays are green dot-matrix LEDs (the user's photos of 8015 and 8080, 2026-11-09: "green top number plate",
// "Green dot led panel with destination and next stop"): the text drawn in white on black, then sampled into round
// diodes on a pitch, lit where the text covers their centre, dim where not.
function ledDots(g, w, h, pitch, draw) {
  const src = document.createElement('canvas');
  src.width = w; src.height = h;
  const s = src.getContext('2d');
  s.fillStyle = '#000'; s.fillRect(0, 0, w, h);
  s.fillStyle = '#fff'; s.textBaseline = 'middle';
  draw(s, w, h);
  const px = s.getImageData(0, 0, w, h).data;
  g.fillStyle = '#0a0f0a'; g.fillRect(0, 0, w, h);
  for (let y = pitch / 2; y < h; y += pitch) for (let x = pitch / 2; x < w; x += pitch) {
    g.fillStyle = px[(Math.floor(y) * w + Math.floor(x)) * 4] > 110 ? '#a8f06e' : '#172414';
    g.beginPath(); g.arc(x, y, pitch * 0.38, 0, 2 * Math.PI); g.fill();
  }
}
const ledFace = (w, h, pitch, draw) => canvasTexture(w, h, (g) => ledDots(g, w, h, pitch, draw));
// The route box on the built-in car's front cap (src/t3simple.js ROUTE_BOX): in a dark rim, white digits on DPP
// blue, or a T3M's green display; the corners square on a T3, rounded on a T3SUCS and a T3M (the user,
// 2026-11-10: "T3SUCS have the top line plate behind window with rounded corners, the same shape as T3M which has
// digital display there instead"), clear outside them (the plate's material tests the alpha). The digits 0.8 of
// the box's height, bold and wide as on 6892 and 7290. No variant: conflig's classic, over the box in its texture.
function routeBoxTexture(line, variant) {
  if (!variant) return numberTexture(line, 160, 128, '#ffffff', DPP_BLUE, 0.9);
  const H = 128, W = Math.round((H * ROUTE_BOX.w) / ROUTE_BOX.h), rim = 5, r = variant === 'T3' ? 0 : (H * ROUTE_BOX.r) / ROUTE_BOX.h;
  return canvasTexture(W, H, (g) => {
    g.fillStyle = '#1b1c1d';
    g.beginPath(); g.roundRect(0, 0, W, H, r); g.fill();
    const w = W - 2 * rim, h = H - 2 * rim, text = String(line);
    g.save();
    g.beginPath(); g.roundRect(rim, rim, w, h, Math.max(0, r - rim)); g.clip();
    g.translate(rim, rim);
    if (variant === 'T3M') {
      ledDots(g, w, h, 5, (s) => { s.font = `bold ${h * 0.8}px "Arial Narrow", Arial, sans-serif`; s.textAlign = 'center'; s.fillText(text, w / 2, h / 2 + 4); });
    } else {
      g.fillStyle = DPP_BLUE; g.fillRect(0, 0, w, h);
      g.fillStyle = '#ffffff';
      g.font = 'bold 100px Arial, sans-serif';
      // (the digits' own box scaled to 0.8 of the box, squeezed only past 0.88 of its width)
      const m = g.measureText(text), L = m.actualBoundingBoxLeft, R = m.actualBoundingBoxRight, A = m.actualBoundingBoxAscent, D = m.actualBoundingBoxDescent;
      const k = (0.8 * H) / (A + D), kx = Math.min(k, (0.88 * w) / (L + R));
      g.setTransform(kx, 0, 0, k, W / 2 - (kx * (R - L)) / 2, H / 2 - (k * (D - A)) / 2);
      g.fillText(text, 0, 0);
    }
    g.restore();
  });
}
// the T3M's side panel: the route number large on the left, the destination over the next stop beside it (each only
// when the set has it)
function ledPanelTexture(line, dest, next) {
  return ledFace(512, 160, 4, (s, w, h) => {
    const fit = (text, x, y, size, max, weight = 'bold') => {
      let px = size;
      do { s.font = `${weight} ${px}px "Arial Narrow", Arial, sans-serif`; px -= 2; } while (s.measureText(text).width > max && px > 12);
      s.fillText(text, x, y);
    };
    s.textAlign = 'center';
    fit(String(line), 76, h / 2 + 6, 134, 140);
    s.textAlign = 'left';
    if (dest) fit(dest.toUpperCase(), 168, next ? 48 : h / 2 + 4, 60, w - 180);
    if (next) fit(next, 168, 118, 44, w - 180, 'normal');
  });
}
const mirrorPlateTexture = (line) => numberTexture(line, 104, 128, '#ffffff', DPP_BLUE, 0.85);
const rearPlateTexture = (line) => numberTexture(line, 144, 128, '#1d3f86', '#f4f4f0', 1.0);
const runCardTexture = (run) => numberTexture(run, 112, 72, '#f4f4f0', '#151515', 0.8);
// the destination in capitals on two lines when it is more than one word (split nearest the middle)
function destinationTexture(name) {
  return canvasTexture(320, 128, (g, w, h) => {
    g.fillStyle = '#f4f4f0';
    g.fillRect(0, 0, w, h);
    g.strokeStyle = DPP_BLUE;
    g.lineWidth = 6;
    g.strokeRect(5, 5, w - 10, h - 10);
    if (!name) return;
    const words = name.toUpperCase().split(/\s+/);
    let lines = [words.join(' ')];
    if (words.length > 1) {
      let best = null;
      for (let k = 1; k < words.length; k++) {
        const a = words.slice(0, k).join(' '), b = words.slice(k).join(' ');
        if (!best || Math.abs(a.length - b.length) < Math.abs(best[0].length - best[1].length)) best = [a, b];
      }
      lines = best;
    }
    g.fillStyle = DPP_BLUE;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    let size = lines.length > 1 ? 46 : 56;
    const fit = () => lines.every((l) => g.measureText(l).width < w - 28);
    g.font = `bold ${size}px "Arial Narrow", Arial, sans-serif`;
    while (!fit() && size > 14) { size -= 2; g.font = `bold ${size}px "Arial Narrow", Arial, sans-serif`; }
    lines.forEach((l, i) => g.fillText(l, w / 2, h / 2 + (i - (lines.length - 1) / 2) * size * 1.05 + 2));
  });
}

// A T3 set of one or two cars (Prague ran most T3s as two-car multiple units). The cars are
// separate children so each can follow the track on its own bogies: see placeConsist().
// Each set owns its materials (traffic fades them individually).
// dest: the destination card's text (none: no card); run: the run number card
// detailed: 'hybrid' (or true: the animated hybrid, src/t3h.js), 'classic' (conflig's model, loaded on the
// player's choice), false (the built-in car, src/t3simple.js); a model not loaded falls back to the next simpler one.
// variant (the built-in car): 'T3', 'T3SUCS' or 'T3M'; none: one from the run number (src/t3simple.js T3_TYPES)
export function makeT3({ line = '22', cars = 1, detailed = true, dest = null, run = '', variant = null } = {}) {
  const root = new THREE.Group();
  root.userData.line = line;
  if (detailed === 'classic' && detailedProto) { makeDetailedSet(root, line, cars, dest, run); root.userData.kind = 'classic'; return root; }
  if (detailed && hybridReady()) { makeHybridSet(root, line, cars, dest, run, CONTACT_WIRE - RAIL_TOP); root.userData.kind = 'hybrid'; return root; }
  if (detailed && detailedProto) { makeDetailedSet(root, line, cars, dest, run); root.userData.kind = 'classic'; return root; }
  const v = variant ?? t3Variant(run);
  makeSimpleSet(root, cars, dest, plateMats(line, dest, run, v), CONTACT_WIRE - RAIL_TOP, { variant: v, fleet: fleetNumbers(v, run, cars) });
  Object.assign(root.userData, { kind: 'simple', dest, run });
  return root;
}

// the plates' and cards' materials of a set: route box and mirror plate glowing, the cards on the glass lit like the body
function plateMats(line, dest, run, variant) {
  const plate = (map, extra) => new THREE.MeshBasicMaterial({ map, polygonOffset: true, polygonOffsetFactor: -2, ...extra });
  const card = (map) => new THREE.MeshLambertMaterial({ map, polygonOffset: true, polygonOffsetFactor: -2 });
  return {
    rbMat: plate(routeBoxTexture(line, variant), { alphaTest: 0.5 }), mirMat: plate(mirrorPlateTexture(line)), rearMat: card(rearPlateTexture(line)),
    destMat: card(destinationTexture(dest)), runMat: card(runCardTexture(run)),
    ...(variant === 'T3M' ? { ledMat: plate(ledPanelTexture(line, dest, null)) } : {}),
  };
}

// The classic detailed T3 (Sketchfab "Tatra T3" low-poly model, CC BY-NC 4.0; see assets/t3/LICENSE.txt), the
// player's choice beside the hybrid (src/t3h.js): simpler, no saloon and no moving parts.
// reduced to a single 2048 px colour texture with the ambient occlusion baked in. Its axes were
// found by principal component analysis of the body: length e1 (front = wipers), width e2
// (doors on +e2 = right), height e3 (wheels on +e3 = down); units are metres (body 14.0 m).
let detailedProto = null;
export const classicReady = () => !!detailedProto;
export const CONTACT_WIRE = 5.34;  // contact wire over top of rail (the track profile; src/heights.js)
export const RAIL_TOP = 0;         // the wheels stand on the profile: it is the top of rail (src/heights.js)

// files: { url: blob URL } of parts already downloaded (the loading screen counts their bytes)
export async function loadDetailedT3(url = 'assets/t3/t3.gltf', files = {}) {
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const manager = new THREE.LoadingManager();
  manager.setURLModifier((u) => files[u] || u);
  const gl = await new GLTFLoader(manager).loadAsync(url);
  const src = gl.scene;
  src.updateMatrixWorld(true);
  // The car's axes come from its 8 wheels (the body is too box-like for a reliable principal
  // axis analysis): forward from the rear to the front axle midpoints, left from the right to the
  // left wheels, up square to both. A rough length axis only sorts the wheels into groups.
  const rough = new THREE.Vector3(0.678, -0.157, 0.718).normalize();
  const wheelPts = [];
  const v = new THREE.Vector3();
  src.traverse((o) => {
    if (!o.isMesh || !o.name.startsWith('wheels')) return;
    const p = o.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) wheelPts.push(v.fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld).clone());
  });
  const mid = wheelPts.reduce((a, b) => a.add(b), new THREE.Vector3()).divideScalar(wheelPts.length);
  const bodyMid = new THREE.Vector3(); let nb = 0;
  src.traverse((o) => {
    if (!o.isMesh || !o.name.startsWith('body')) return;
    const p = o.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) { bodyMid.add(v.fromBufferAttribute(p, i).applyMatrix4(o.matrixWorld)); nb++; }
  });
  bodyMid.divideScalar(nb);
  const roughUp = bodyMid.clone().sub(mid);
  roughUp.addScaledVector(rough, -roughUp.dot(rough)).normalize();
  const roughLeft = new THREE.Vector3().crossVectors(roughUp, rough); // up x forward = left
  const groups = new Map(); // "front/rear" + "left/right" -> mean point
  for (const p of wheelPts) {
    const d = p.clone().sub(mid);
    const k = (d.dot(rough) > 0 ? 'F' : 'B') + (d.dot(roughLeft) > 0 ? 'L' : 'R');
    if (!groups.has(k)) groups.set(k, { c: new THREE.Vector3(), n: 0 });
    const g = groups.get(k); g.c.add(p); g.n++;
  }
  const G = (k) => groups.get(k).c.clone().divideScalar(groups.get(k).n);
  const fwd = G('FL').add(G('FR')).sub(G('BL')).sub(G('BR')).normalize();
  const left = G('FL').add(G('BL')).sub(G('FR')).sub(G('BR'));
  left.addScaledVector(fwd, -left.dot(fwd)).normalize();
  const up = new THREE.Vector3().crossVectors(fwd, left); // forward x left = up
  // local car axes: x = left, y = up, z = forward
  const rot = new THREE.Matrix4().set(left.x, left.y, left.z, 0, up.x, up.y, up.z, 0, fwd.x, fwd.y, fwd.z, 0, 0, 0, 0, 1);
  const proto = new THREE.Group();
  src.traverse((o) => {
    if (!o.isMesh) return;
    const g = o.geometry.clone().applyMatrix4(new THREE.Matrix4().multiplyMatrices(rot, o.matrixWorld));
    const m = new THREE.Mesh(g, o.material);
    m.name = o.name;
    proto.add(m);
  });
  // origin: on the rails (bottom of the wheels), centred between the wheels across and along
  const wb = new THREE.Box3();
  for (const m of proto.children) if (m.name.startsWith('wheels')) { m.geometry.computeBoundingBox(); wb.union(m.geometry.boundingBox); }
  const shift = new THREE.Matrix4().makeTranslation(-(wb.min.x + wb.max.x) / 2, -wb.min.y, -(wb.min.z + wb.max.z) / 2);
  for (const m of proto.children) m.geometry.applyMatrix4(shift);
  // bogie pivots (between each bogie's two axles) and the pantograph
  const wheelZ = [];
  for (const m of proto.children) if (m.name.startsWith('wheels')) {
    const p = m.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) wheelZ.push(p.getZ(i));
  }
  const front = wheelZ.filter((z) => z > 0), rear = wheelZ.filter((z) => z < 0);
  const bogie = ((front.reduce((a, b) => a + b, 0) / front.length) - (rear.reduce((a, b) => a + b, 0) / rear.length)) / 2;
  // raise the pantograph head to the contact wire: stretch the frame up from its base
  const pan = proto.children.filter((m) => m.name.startsWith('power'));
  const pb = new THREE.Box3();
  for (const m of pan) { m.geometry.computeBoundingBox(); pb.union(m.geometry.boundingBox); }
  const base = pb.min.y, k = (CONTACT_WIRE - RAIL_TOP - 0.01 - base) / (pb.max.y - base);
  for (const m of pan) {
    const p = m.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) p.setY(i, base + (p.getY(i) - base) * k);
    p.needsUpdate = true;
  }
  for (const m of proto.children) { m.geometry.computeBoundingBox(); m.geometry.computeBoundingSphere(); }
  const body = new THREE.Box3();
  for (const m of proto.children) if (m.name.startsWith('body')) body.union(m.geometry.boundingBox);
  proto.userData = { bogie, panto: (pb.min.z + pb.max.z) / 2, bodyFront: body.max.z, boxes: paintedBoxes(proto), cards: glassCards(proto) };
  const mat = proto.children[0].material;
  mat.metalness = 0; mat.roughness = 0.75;
  // (not the material: each set clones it, and a clone copies userData)
  for (const m of proto.children) for (const x of [m.geometry, ...texturesOf(m.material)]) x.userData.shared = true;
  detailedProto = proto;
  return proto;
}

// The route number boxes painted in the model's texture (pixel rectangles in t3_color.jpg, found
// by colour): map each rectangle's corners onto the model through the triangle whose texture
// coordinates contain its centre (glTF texture v runs downwards), then make an upright quad over
// it, a little proud of the surface and a little larger. The rear box mirrors the front one.
const PAINTED = [[513, 46, 550, 92], [1873, 1078, 1909, 1124]]; // front dome, front right corner
function paintedBoxes(proto, W = 2048, H = 2048) {
  const boxes = [];
  for (const [x0, y0, x1, y1] of PAINTED) {
    const uc = (x0 + x1) / 2 / W, vc = (y0 + y1) / 2 / H;
    let tri = null;
    for (const m of proto.children) {
      const g = m.geometry, P = g.attributes.position, U = g.attributes.uv;
      if (!U || tri) continue;
      const cnt = g.index ? g.index.count : P.count;
      for (let t = 0; t < cnt && !tri; t += 3) {
        const ii = [0, 1, 2].map((q) => (g.index ? g.index.getX(t + q) : t + q));
        const a = ii.map((i) => [U.getX(i), U.getY(i)]);
        const w = bary(a, uc, vc);
        if (w && w.every((x) => x > -1e-4)) tri = { a, p: ii.map((i) => new THREE.Vector3().fromBufferAttribute(P, i)) };
      }
    }
    if (!tri) continue;
    const at = (u, v) => { const w = bary(tri.a, u, v); return tri.p[0].clone().multiplyScalar(w[0]).addScaledVector(tri.p[1], w[1]).addScaledVector(tri.p[2], w[2]); };
    const corners = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map(([x, y]) => at(x / W, y / H));
    const n = new THREE.Vector3().crossVectors(tri.p[1].clone().sub(tri.p[0]), tri.p[2].clone().sub(tri.p[0])).normalize();
    const c = corners.reduce((s, v) => s.add(v), new THREE.Vector3()).divideScalar(4);
    if (n.dot(c.clone().setY(0)) < 0) n.negate(); // outwards
    const up = new THREE.Vector3(0, 1, 0).addScaledVector(n, -n.y).normalize();
    const right = new THREE.Vector3().crossVectors(up, n).normalize();
    let r0 = Infinity, r1 = -Infinity, u0 = Infinity, u1 = -Infinity;
    for (const v of corners) { const d = v.clone().sub(c); r0 = Math.min(r0, d.dot(right)); r1 = Math.max(r1, d.dot(right)); u0 = Math.min(u0, d.dot(up)); u1 = Math.max(u1, d.dot(up)); }
    boxes.push({ c: c.addScaledVector(n, 0.012), n, up, right, w: (r1 - r0) * 1.12, h: (u1 - u0) * 1.12 });
  }
  return boxes;
}

// The cards on the windows: the model's windows are painted in its (opaque) texture, so the cards lie
// on the glass, 5 mm proud, following its slope: found by casting a ray at the window from outside.
// [name, x (left +), bottom height, width, height, end (+1 front, -1 rear)] in metres; the windscreen's
// flat middle pane runs from x −0.62 to +0.58 between the frame supports (measured by raycasting), from
// 1.71 m up; a wiper arm stands out at x −0.36; the side panes curve back beyond the supports. The
// destination card in the middle pane's middle, the run number on the right-hand side pane (left as
// seen from the front), just past the frame support.
const CARDS = [
  ['dest', -0.02, 1.75, 0.46, 0.19, 1],
  ['run', -0.75, 1.75, 0.15, 0.1, 1],
  ['rear', 0, 1.75, 0.34, 0.3, -1],
];
function glassCards(proto) {
  proto.updateMatrixWorld(true);
  const ray = new THREE.Raycaster(), out = {};
  for (const [name, x, y0, w, h, end] of CARDS) {
    const y = y0 + h / 2;
    ray.set(new THREE.Vector3(x, y, end * 20), new THREE.Vector3(0, 0, -end));
    const hit = ray.intersectObjects(proto.children, false)[0];
    if (!hit) continue;
    const n = hit.face.normal.clone();
    if (n.z * end < 0) n.negate(); // outwards
    const up = new THREE.Vector3(0, 1, 0).addScaledVector(n, -n.y).normalize();
    const right = new THREE.Vector3().crossVectors(up, n).normalize();
    out[name] = { c: hit.point.clone().addScaledVector(n, 0.005), n, up, right, w, h };
  }
  return out;
}
function bary(a, u, v) {
  const d = (a[1][1] - a[2][1]) * (a[0][0] - a[2][0]) + (a[2][0] - a[1][0]) * (a[0][1] - a[2][1]);
  if (Math.abs(d) < 1e-12) return null;
  const w1 = ((a[1][1] - a[2][1]) * (u - a[2][0]) + (a[2][0] - a[1][0]) * (v - a[2][1])) / d;
  const w2 = ((a[2][1] - a[0][1]) * (u - a[2][0]) + (a[0][0] - a[2][0]) * (v - a[2][1])) / d;
  return [w1, w2, 1 - w1 - w2];
}
function boxQuad(b) {
  // upright quad: x along `right`, y along `up`, facing `n`
  const g = new THREE.PlaneGeometry(b.w, b.h);
  g.applyMatrix4(new THREE.Matrix4().makeBasis(b.right, b.up, b.n).setPosition(b.c));
  return g;
}

function makeDetailedSet(root, line, cars, dest, run) {
  // own material per set (traffic fades sets individually), shared geometry
  const mat = detailedProto.children[0].material.clone();
  const mats = { ...plateMats(line, dest, run), body: mat };
  root.userData.mats = mats;
  root.userData.dest = dest;
  root.userData.run = run;
  root.userData.bogie = detailedProto.userData.bogie;
  root.userData.bodyFront = detailedProto.userData.bodyFront;
  root.userData.cars = [];
  const { boxes, cards } = detailedProto.userData;
  for (let k = 0; k < cars; k++) {
    const car = new THREE.Group();
    car.rotation.order = 'YXZ';
    for (const m of detailedProto.children) car.add(new THREE.Mesh(m.geometry, mat));
    // the leading car: the roof and mirror plates over the boxes painted in the texture, the cards
    // behind the windscreen (no destination card on a tram whose destination we do not know); the
    // last car: the inverted plate in the rear window
    if (k === 0) {
      if (boxes[0]) car.add(new THREE.Mesh(boxQuad(boxes[0]), mats.rbMat));
      // (the mirror plate is smaller than the box painted there, and taller than wide)
      if (boxes[1]) car.add(new THREE.Mesh(boxQuad({ ...boxes[1], w: 0.22, h: 0.28 }), mats.mirMat));
      if (cards.dest && dest) car.add(new THREE.Mesh(boxQuad(cards.dest), mats.destMat));
      if (cards.run) car.add(new THREE.Mesh(boxQuad(cards.run), mats.runMat));
    }
    if (k === cars - 1 && cards.rear) car.add(new THREE.Mesh(boxQuad(cards.rear), mats.rearMat));
    root.add(car);
    root.userData.cars.push(car);
  }
  return root;
}

// Change the route number on the plates, the destination card and the run number (a new shift, a run
// continuing as another line). (A set made without a destination has no card to change.)
export function setConsistLine(model, line, dest = model.userData.dest, run = model.userData.run) {
  if (model.userData.hybrid) { setHybridLine(model, line, dest, run); return; }
  const u = model.userData, { mats } = u;
  const swap = (m, tex) => { if (!m) return; const old = m.map; m.map = tex; m.needsUpdate = true; old?.dispose(); };
  if (u.line !== line) {
    swap(mats.rbMat, routeBoxTexture(line, u.variant));
    swap(mats.mirMat, mirrorPlateTexture(line));
    swap(mats.rearMat, rearPlateTexture(line));
  }
  if (u.dest !== dest) swap(mats.destMat, destinationTexture(dest));
  if (u.run !== run) swap(mats.runMat, runCardTexture(run));
  if (u.line !== line || u.dest !== dest) swap(mats.ledMat, ledPanelTexture(line, dest, u.next));
  Object.assign(u, { line, dest, run });
}

// The next stop on a T3M's side panel (the built-in car; other sets have none to show)
export function setNextStop(model, next) {
  const u = model.userData;
  if (!u.mats?.ledMat || u.next === next) return;
  const old = u.mats.ledMat.map;
  u.mats.ledMat.map = ledPanelTexture(u.line, u.dest, next);
  u.mats.ledMat.needsUpdate = true;
  old?.dispose();
  u.next = next;
}

// Put each car of a set on the track (`at(s)` -> [x, y, track bed height, roll]): each car rests on its two bogie
// pivots, so it yaws, pitches and leans with them, wheels on the rail heads. The hybrid and the built-in car hang
// each next car on the coupling and pose their bogies, wheels and couplers (src/consist.js); the classic model
// stands its cars CAR_PITCH apart, its body 0.6 m behind the coupler face, on its own pivots' spacing.
export function placeConsist(model, sFront, at) {
  const u = model.userData;
  if (u.kind !== 'classic') { hangConsist(model, sFront, at); return; }
  const { bogie, bodyFront } = u;
  u.cars.forEach((car, k) => {
    const c = sFront - k * CAR_PITCH - 0.6 - bodyFront; // car origin (midway between the bogies)
    const [ax, ay, za, ra = 0] = at(c + bogie), [bx, by, zb, rb = 0] = at(c - bogie);
    car.position.set((ax + bx) / 2, (za + zb) / 2 + RAIL_TOP, -(ay + by) / 2);
    car.rotation.order = 'YXZ'; // heading, then pitch, then the lean into a canted curve
    car.rotation.y = Math.atan2(ax - bx, -(ay - by));
    car.rotation.x = -Math.atan2(za - zb, 2 * bogie);
    car.rotation.z = -(ra + rb) / 2;
  });
}

// A set's mechanisms from the game's state, whichever model (each acts only on what changes): the doors (0..1),
// the collector's contact height, the track brakes' magnets (the hybrid's: src/t3h.js poseHybrid); the brake lamps
// (`braking`), the indicators (`indicate`: 'left', 'right', 'hazard' or none, blinking by `clock` in s), the high
// beams (`highBeam`) on both it and the built-in car (src/t3simple.js poseSimple); the classic model has none.
export function poseT3(model, state) {
  const k = model.userData.kind;
  if (k !== 'hybrid' && k !== 'simple') return;
  const s = 'indicate' in state ? { ...state, signals: signalsAt(state.indicate, state.clock ?? 0) } : state;
  if (k === 'hybrid') poseHybrid(model, s);
  else poseSimple(model, s);
}

const CAR_COLORS = [0x2f4f7f, 0xa0a4a8, 0x1c1c1c, 0xe8e8e8, 0x7a1f1f, 0x3d5c3a, 0xc8b47a, 0x5a6f80, 0xd8d2c0, 0x324a63];
export function makeCar(seed = 0) {
  const g = new THREE.Group();
  const body = lambert(CAR_COLORS[seed % CAR_COLORS.length]);
  const lower = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.75, 4.3), body);
  lower.position.y = 0.6;
  const upper = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.55, 2.3), lambert(0x22303a));
  upper.position.set(0, 1.25, -0.2);
  const roof = new THREE.Mesh(new THREE.BoxGeometry(1.62, 0.06, 2.0), body);
  roof.position.set(0, 1.55, -0.2);
  g.add(lower, upper, roof);
  for (const [x, z] of [[-0.8, 1.4], [0.8, 1.4], [-0.8, -1.4], [0.8, -1.4]]) {
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.2, 10), lambert(0x111111));
    w.rotation.z = Math.PI / 2;
    w.position.set(x, 0.32, z);
    g.add(w);
  }
  // turn indicators at the four corners (+X is the car's left), lit by userData.blink(side, on)
  const amber = new THREE.MeshBasicMaterial({ color: 0xffa31a });
  const lamps = { left: [], right: [] };
  for (const [side, x] of [['left', 0.78], ['right', -0.78]]) {
    for (const z of [2.16, -2.16]) {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.1, 0.04), amber);
      l.position.set(x, 0.82, z);
      l.visible = false;
      lamps[side].push(l);
      g.add(l);
    }
  }
  g.userData.blink = (side, on) => {
    for (const s of ['left', 'right']) for (const l of lamps[s]) l.visible = s === side && on;
  };
  return g; // facing +Z
}

const SHIRTS = [0x8b2f2f, 0x2f4f8b, 0x3c6b3c, 0x666666, 0xc29a3a, 0x222222, 0x8a5a9a, 0xd0d0d0, 0x2a5c63, 0xa8523a];
export function makePerson(seed = 0) {
  const g = new THREE.Group();
  const legs = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.85, 0.22), lambert(0x2a2f3a));
  legs.position.y = 0.43;
  const torso = new THREE.Mesh(new THREE.BoxGeometry(0.46, 0.66, 0.26), lambert(SHIRTS[seed % SHIRTS.length]));
  torso.position.y = 1.18;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.13, 8, 6), lambert(0xd9b38c));
  head.position.y = 1.65;
  g.add(legs, torso, head);
  return g;
}

// Traffic lights for cars (D2), all heads of the line in a few instanced meshes: a grey pole, a black
// housing with a black backplate, and three lamps (red, amber, green from the top) whose colour is set
// per instance, bright when lit, dark when not. heads: [{ x, z, h, face }] in world coordinates (h:
// the ground height; face: the turn about Y that points the lamps, local +Z, towards the drivers).
// Returns { group, set(i, aspect) } with aspect 'red' | 'redamber' | 'amber' | 'green' | 'dark'.
export function makeTrafficLights(heads) {
  const n = Math.max(1, heads.length);
  const group = new THREE.Group();
  const pole = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.06, 0.07, 3.3, 6).translate(0, 1.65, 0), lambert(0x6f7377), n);
  const box = new THREE.InstancedMesh(new THREE.BoxGeometry(0.34, 0.95, 0.24).translate(0, 2.85, -0.02), lambert(0x161616), n);
  const plate = new THREE.InstancedMesh(new THREE.BoxGeometry(0.56, 1.18, 0.02).translate(0, 2.85, -0.15), lambert(0x101010), n);
  const lamp = new THREE.InstancedMesh(new THREE.CircleGeometry(0.11, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }), n * 3);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  heads.forEach((h, i) => {
    q.setFromAxisAngle(up, h.face);
    p.set(h.x, h.h, h.z);
    m.compose(p, q, s);
    pole.setMatrixAt(i, m); box.setMatrixAt(i, m); plate.setMatrixAt(i, m);
    for (let k = 0; k < 3; k++) {
      const off = new THREE.Vector3(0, 3.15 - k * 0.3, 0.105).applyQuaternion(q);
      m.compose(p.clone().add(off), q, s);
      lamp.setMatrixAt(i * 3 + k, m);
    }
  });
  group.add(pole, box, plate, lamp);
  const LIT = [new THREE.Color(0xff2a1a), new THREE.Color(0xffb000), new THREE.Color(0x2bff6a)];
  const OFF = [new THREE.Color(0x2a0806), new THREE.Color(0x2a1f04), new THREE.Color(0x05220e)];
  const ON = { red: [1, 0, 0], redamber: [1, 1, 0], amber: [0, 1, 0], green: [0, 0, 1], dark: [0, 0, 0] };
  const state = new Array(n).fill(null);
  const set = (i, aspect) => {
    if (state[i] === aspect) return;
    state[i] = aspect;
    ON[aspect].forEach((on, k) => lamp.setColorAt(i * 3 + k, on ? LIT[k] : OFF[k]));
    lamp.instanceColor.needsUpdate = true;
  };
  heads.forEach((_, i) => set(i, 'red'));
  return { group, set, count: heads.length };
}

// Pedestrian signal heads, instanced like the car heads: a pole, a narrow black housing and two square
// lamps (red standing figure above, green walking figure below; plain squares here). heads: [{ x, z, h,
// face }] as for makeTrafficLights (face turns local +Z towards the people waiting across the street).
// Returns { group, set(i, 'red' | 'green' | 'dark'), count }.
export function makePedLights(heads) {
  const n = Math.max(1, heads.length);
  const group = new THREE.Group();
  const pole = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.05, 0.06, 2.6, 6).translate(0, 1.3, 0), lambert(0x6f7377), n);
  const box = new THREE.InstancedMesh(new THREE.BoxGeometry(0.28, 0.62, 0.2).translate(0, 2.3, 0.02), lambert(0x161616), n);
  const lamp = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.2, 0.2), new THREE.MeshBasicMaterial({ color: 0xffffff }), n * 2);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), s = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3(), up = new THREE.Vector3(0, 1, 0);
  heads.forEach((h, i) => {
    q.setFromAxisAngle(up, h.face);
    p.set(h.x, h.h, h.z);
    m.compose(p, q, s);
    pole.setMatrixAt(i, m); box.setMatrixAt(i, m);
    for (let k = 0; k < 2; k++) {
      const off = new THREE.Vector3(0, 2.45 - k * 0.29, 0.125).applyQuaternion(q);
      m.compose(p.clone().add(off), q, s);
      lamp.setMatrixAt(i * 2 + k, m);
    }
  });
  group.add(pole, box, lamp);
  const LIT = [new THREE.Color(0xff2a1a), new THREE.Color(0x2bff6a)];
  const OFF = [new THREE.Color(0x2a0806), new THREE.Color(0x05220e)];
  const ON = { red: [1, 0], green: [0, 1], dark: [0, 0] };
  const state = new Array(n).fill(null);
  const set = (i, aspect) => {
    if (state[i] === aspect) return;
    state[i] = aspect;
    ON[aspect].forEach((on, k) => lamp.setColorAt(i * 2 + k, on ? LIT[k] : OFF[k]));
    lamp.instanceColor.needsUpdate = true;
  };
  heads.forEach((_, i) => set(i, 'red'));
  return { group, set, count: heads.length };
}

// Instanced people (one simple figure per instance, per-instance shirt colour).
export function makeCrowd(max) {
  const legs = new THREE.BoxGeometry(0.36, 0.85, 0.24).translate(0, 0.43, 0);
  const torso = new THREE.BoxGeometry(0.46, 0.66, 0.28).translate(0, 1.18, 0);
  const head = new THREE.BoxGeometry(0.22, 0.24, 0.22).translate(0, 1.64, 0);
  const geo = mergeBoxes([legs, torso, head], [0.25, 1, 0.85]);
  const mesh = new THREE.InstancedMesh(geo, lambert(0xffffff, { vertexColors: true }), max);
  const c = new THREE.Color();
  for (let i = 0; i < max; i++) {
    c.setHex(SHIRTS[(i * 7) % SHIRTS.length]);
    mesh.setColorAt(i, c);
  }
  mesh.count = 0;
  mesh.frustumCulled = false; // instances move around the whole map
  return mesh;
}

// merge simple geometries; `shade` darkens each part's vertex colour (legs dark, head pale)
function mergeBoxes(geos, shade) {
  const pos = [], nor = [], col = [], idx = [];
  let off = 0;
  geos.forEach((g, k) => {
    const p = g.attributes.position, n = g.attributes.normal;
    for (let i = 0; i < p.count; i++) {
      pos.push(p.getX(i), p.getY(i), p.getZ(i));
      nor.push(n.getX(i), n.getY(i), n.getZ(i));
      const v = shade[k];
      if (k === 2) col.push(1.0, 0.82, 0.68); else col.push(v, v, v);
    }
    for (let i = 0; i < g.index.count; i++) idx.push(g.index.getX(i) + off);
    off += p.count;
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  geo.setIndex(idx);
  return geo;
}

// Prague tram signal (SSZ TRAM): black housing with four round white lamps (three in the
// top row, one below the middle) mounted on a white backplate with a black edge. Aspects:
//   stop           = the two outer top lamps
//   go straight    = top middle + bottom
//   go left/right  = top left/right + bottom
// Below it hangs the call signal (výzvové návěstidlo): three LED strips \ | / (src/ledPanels.js) —
// the strip for the direction about to get GO lights once the tram's request is registered and
// blinks just before GO. A distant signal (předvěst) has a yellow "P" plate instead.
const ASPECT = {
  stop: ['L', 'R'],
  straight: ['M', 'B'],
  left: ['L', 'B'],
  right: ['R', 'B'],
};
let pPlateTex = null, backplateTex = null;
const callTex = {};
function callTexture(dir) {
  if (callTex[dir]) return callTex[dir];
  callTex[dir] = keptTexture(160, 160, (c, w, h) => drawCallSignal(c, dir === 'none' ? [] : [dir], w, h));
  return callTex[dir];
}

export function makeTramSignal({ distant = false } = {}) {
  const g = new THREE.Group();
  const top = distant ? 3.9 : 3.8;
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.08, top + 0.45, 8), lambert(0xa9adb0));
  pole.position.y = (top + 0.45) / 2;
  g.add(pole);
  g.userData.pole = pole;
  g.userData.boardTop = top + 0.43;
  if (!backplateTex) backplateTex = keptTexture(128, 128, (c, w, h) => {
    c.fillStyle = '#ffffff'; c.beginPath(); c.roundRect(0, 0, w, h, 10); c.fill();
    c.strokeStyle = '#111'; c.lineWidth = 5; c.beginPath(); c.roundRect(9, 9, w - 18, h - 18, 6); c.stroke();
  });
  const plate = new THREE.Mesh(new THREE.PlaneGeometry(0.86, 0.86), new THREE.MeshLambertMaterial({ map: backplateTex }));
  plate.position.set(0, top, 0.075);
  const plateBack = new THREE.Mesh(new THREE.PlaneGeometry(0.86, 0.86), lambert(0x8f9396));
  plateBack.position.set(0, top, 0.07);
  plateBack.rotation.y = Math.PI;
  const housing = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.56, 0.2), lambert(0x0e0e0e));
  housing.position.set(0, top, 0.12);
  g.add(plate, plateBack, housing);
  const on = new THREE.MeshBasicMaterial({ color: 0xfffdf0 });
  const off = new THREE.MeshBasicMaterial({ color: 0x2f3532 });
  const lensGeo = new THREE.CircleGeometry(0.07, 20);
  const pos = { L: [-0.17, 0.1], M: [0, 0.1], R: [0.17, 0.1], B: [0, -0.12] };
  const lamps = {};
  for (const [k, [x, y]] of Object.entries(pos)) {
    const m = new THREE.Mesh(lensGeo, off);
    m.position.set(x, top + y, 0.225);
    g.add(m);
    lamps[k] = m;
  }
  let callFace = null;
  if (distant) {
    if (!pPlateTex) pPlateTex = keptTexture(96, 128, (c, w, h) => {
      c.fillStyle = '#fff'; c.fillRect(0, 0, w, h);
      c.fillStyle = '#ffe600'; c.fillRect(8, 8, w - 16, h - 16);
      c.strokeStyle = '#111'; c.lineWidth = 4; c.strokeRect(12, 12, w - 24, h - 24);
      c.fillStyle = '#111'; c.font = 'bold 96px Arial, sans-serif'; c.textAlign = 'center'; c.textBaseline = 'middle';
      c.fillText('P', w / 2, h / 2 + 6);
    });
    const pp = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.4), new THREE.MeshLambertMaterial({ map: pPlateTex }));
    pp.position.set(0, top - 0.68, 0.1);
    g.add(pp);
  } else {
    const callBox = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.42, 0.18), lambert(0x0e0e0e));
    callBox.position.set(0, top - 0.72, 0.1);
    callFace = new THREE.Mesh(new THREE.PlaneGeometry(0.38, 0.38), new THREE.MeshBasicMaterial({ map: callTexture('none') }));
    callFace.position.set(0, top - 0.72, 0.195);
    g.add(callBox, callFace);
  }
  // state: 'stop' | 'go' | 'warn' (end of GO: the GO aspect blinks)
  // call: 'off' | 'on' (request registered) | 'blink-off' (blinking phase dark)
  g.userData.set = (state, { goDir = 'straight', blink = false, call: callState = 'off' } = {}) => {
    const aspect = state === 'stop' ? ASPECT.stop : state === 'go' || state === 'warn' ? ASPECT[goDir] : [];
    const lit = new Set(blink ? [] : aspect);
    for (const [k, m] of Object.entries(lamps)) m.material = lit.has(k) ? on : off;
    if (callFace) {
      const tex = callTexture(callState === 'on' ? goDir : 'none');
      if (callFace.material.map !== tex) { callFace.material.map = tex; callFace.material.needsUpdate = true; }
    }
  };
  return g;
}

// Switch position indicator (přestavníkové návěstidlo), newest DPP type: a black box hung from
// the span wire above the track, a matrix of red LEDs (src/ledPanels.js): a dart pointing left
// or right, a bar for straight. The symbol blinks while the switch is locked.
const arrowTextures = {};
function arrowTexture(dir) {
  if (arrowTextures[dir]) return arrowTextures[dir];
  arrowTextures[dir] = keptTexture(200, 160, (g, w, h) => drawSwitchSignal(g, dir, w, h));
  return arrowTextures[dir];
}

export function makeSwitchIndicator() {
  // hangs from the span wire: origin at track level, box at ~6.2 m
  const g = new THREE.Group();
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.48, 0.3), lambert(0x111111));
  box.position.y = 6.15;
  const mat = new THREE.MeshBasicMaterial({ map: arrowTexture('straight') });
  const face = new THREE.Mesh(new THREE.PlaneGeometry(0.56, 0.44), mat);
  face.position.set(0, 6.15, 0.155);
  const hanger = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.5, 0.04), lambert(0x333333));
  hanger.position.set(0, 6.6, 0);
  g.add(box, face, hanger);
  g.userData.set = (dir, blinkOff = false) => {
    const tex = arrowTexture(blinkOff ? 'off' : dir);
    if (mat.map !== tex) { mat.map = tex; mat.needsUpdate = true; }
  };
  return g;
}

// Little yellow plate marking the overhead switch contact.
export function makeContactMarker() {
  const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.25, 0.05), new THREE.MeshBasicMaterial({ color: 0xf2c300 }));
  m.position.y = 5.95;
  return m;
}

// ----------------------------------------------------------------------------- signs
// A board on a pole, facing +Z. `face` is a texture; size in metres.
function signOnPole(tex, w, h, y, poleH = y + h / 2) {
  const g = new THREE.Group();
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, poleH, 6), lambert(0x6a6a6a));
  pole.position.y = poleH / 2;
  const board = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshLambertMaterial({ map: tex }));
  board.position.set(0, y, 0.05);
  const back = new THREE.Mesh(new THREE.PlaneGeometry(w, h), lambert(0x8a8a8a));
  back.position.set(0, y, 0.045);
  back.rotation.y = Math.PI;
  g.add(pole, board, back);
  g.userData.pole = pole;
  g.userData.boardTop = y + h / 2;
  return g;
}

const signTex = new Map();
const cached = (key, make) => { if (!signTex.has(key)) { const tex = make(); tex.userData.shared = true; signTex.set(key, tex); } return signTex.get(key); };

// The old board, black number on white with a black border: now only a diagnostic, where a limit comes from a curve
// alone and no real sign stands (the user, 2026-11-08: "keep them for now for diagnostic purposes, we can drop them
// later with more stable release"), shown with the debug overlay (F8) only (#389).
export function makeSpeedSign(v) {
  const tex = cached(`v${v}`, () => canvasTexture(128, 160, (g, w, h) => {
    g.fillStyle = '#111'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#fff'; g.fillRect(10, 10, w - 20, h - 20);
    g.fillStyle = '#111';
    g.font = 'bold 84px "Arial Narrow", Arial, sans-serif';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(String(v), w / 2, h / 2 + 4);
  }));
  return signOnPole(tex, 0.36, 0.45, 3.0);
}

// Working trolley contact sign: white square, black triangle with an orange square inside.
export function makeContactSign() {
  const tex = cached('contact', () => canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = '#fff'; g.fillRect(0, 0, w, h);
    g.strokeStyle = '#222'; g.lineWidth = 3; g.strokeRect(2, 2, w - 4, h - 4);
    g.fillStyle = '#111';
    g.beginPath(); g.moveTo(w / 2, 14); g.lineTo(w - 14, h - 18); g.lineTo(14, h - 18); g.closePath(); g.fill();
    g.fillStyle = '#ff7a00'; g.fillRect(w / 2 - 17, h - 62, 34, 34);
  }));
  return signOnPole(tex, 0.36, 0.36, 4.4);
}

// Radio (IRC) operated switch: white square with a black border and a radio pictogram.
export function makeRadioSwitchSign() {
  const tex = cached('radio', () => canvasTexture(128, 128, (g, w, h) => {
    g.fillStyle = '#111'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#fff'; g.fillRect(10, 10, w - 20, h - 20);
    g.strokeStyle = '#111'; g.lineWidth = 6; g.lineCap = 'round';
    g.beginPath(); g.moveTo(w / 2, 98); g.lineTo(w / 2, 52); g.stroke();
    g.fillStyle = '#111'; g.beginPath(); g.arc(w / 2, 48, 7, 0, Math.PI * 2); g.fill();
    for (const r of [18, 30]) {
      g.beginPath(); g.arc(w / 2, 48, r, -Math.PI * 0.8, -Math.PI * 0.2); g.stroke();
    }
  }));
  return signOnPole(tex, 0.4, 0.4, 3.2);
}

// A D 1/2 speed or gradient sign (src/speedSigns.js: restriction, end, warning, Rychlostník, "r", zone, the gradient
// boards) on a pole, SIGN_SCALE times its real size, its bottom edge 2.6 m up (#364). Textures are kept per face, so
// they are drawn once: after loadFigureFont has settled (src/main.js), or a face keeps the font it was first drawn in.
export function makeSpeedBoard(sign) {
  const { s, ...face } = sign;
  const size = shownSize(face), H = 256, W = Math.round(H * size.w / size.h);
  const tex = cached('board' + JSON.stringify(face), () => canvasTexture(W, H, (g, w, h) => drawSign(g, face, w, h)));
  const g = signOnPole(tex, size.w, size.h, 2.6 + size.h / 2);
  // the warning triangle's corners are clear
  if (face.kind === 'warning') g.children[1].material.alphaTest = 0.5;
  g.userData.sign = face;
  return g;
}

// ------------------------------------------------------------------ the speed switch's elements (D 1/2 § 46, #365)
// Along the track at R01's distances (docs/decisions/2026-11-07-speed-switch-signals.md): the number plate (the radio
// receiver's place), the call signal, the entry sleeper signal, and at the frog the switch signal over its number box.

// "R 07": white on black, landscape as D 1/2 p. 45 draws it, 400 x 300 mm estimated, SIGN_SCALE times as the speed signs
export function makeSwitchNumberPlate(number) {
  const text = String(number).replace(/^R(\d)/, 'R $1');
  const w = 0.4 * SIGN_SCALE, h = 0.3 * SIGN_SCALE;
  const tex = cached('rplate' + text, () => canvasTexture(256, 192, (g, W, H) => drawNumberPlate(g, text, W, H)));
  return signOnPole(tex, w, h, 2.6 + h / 2);
}

// the call signal on its own pole: the junctions' box, dark until a request is registered (registration: the later issue)
export function makeCallSignal() {
  const g = new THREE.Group(), top = 3.6;
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.07, top + 0.25, 8), lambert(0xa9adb0));
  pole.position.y = (top + 0.25) / 2;
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.42, 0.18), lambert(0x0e0e0e));
  box.position.set(0, top, 0.1);
  const face = new THREE.Mesh(new THREE.PlaneGeometry(0.38, 0.38), new THREE.MeshBasicMaterial({ map: callTexture('none') }));
  face.position.set(0, top, 0.195);
  g.add(pole, box, face);
  g.userData.pole = pole;
  g.userData.boardTop = top + 0.21;
  return g;
}

// the entry sleeper signal: a round black disc low beside the rail, a white vertical bar (may enter) or horizontal one
const entryTex = {};
export function makeEntrySignal(state = 'go') {
  entryTex[state] ||= keptTexture(128, 128, (g, w, h) => drawLedPanel(g, { kind: 'entry', state }, w, h));
  const g = new THREE.Group();
  const post = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.35, 6), lambert(0x333333));
  post.position.y = 0.175;
  const disc = new THREE.Mesh(new THREE.CircleGeometry(0.15, 24), new THREE.MeshBasicMaterial({ map: entryTex[state], alphaTest: 0.5 }));
  disc.position.set(0, 0.5, 0.03);
  const back = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.05, 24), lambert(0x161616));
  back.rotation.x = Math.PI / 2; back.position.set(0, 0.5, 0);
  g.add(post, back, disc);
  return g;
}

// The switch signal: two boxes with cut corners on a pole bracket about 5 m up, the white LED dart above (the set way;
// blinking while locked) and the number box below. The number stays dark here: without registration the switch is
// passed as a lockable one, 15 km/h (D 1/2 § 30.4; registration and the number are the later issue). Same API as
// makeSwitchIndicator: userData.set(dir, blinkOff).
const dartTex = {};
function dartTexture(dir) {
  return (dartTex[dir] ||= keptTexture(216, 150, (g, w, h) => drawLedPanel(g, dir === 'off' ? { kind: 'chevron', dark: true } : { kind: 'chevron', dir }, w, h)));
}
let numberDarkTex = null;
export function makeSpeedSwitchSignal() {
  const g = new THREE.Group(), y = 5.0;
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.07, y + 0.5, 8), lambert(0xa9adb0));
  pole.position.y = (y + 0.5) / 2;
  const mat = new THREE.MeshBasicMaterial({ map: dartTexture('straight'), alphaTest: 0.5 });
  numberDarkTex ||= keptTexture(216, 150, (c, w, h) => drawLedPanel(c, { kind: 'number', dark: true }, w, h));
  for (const [dy, m] of [[0.25, mat], [-0.25, new THREE.MeshBasicMaterial({ map: numberDarkTex, alphaTest: 0.5 })]]) {
    const box = new THREE.Mesh(new THREE.BoxGeometry(0.58, 0.4, 0.16), lambert(0x111111));
    box.position.set(0, y + dy, 0.12);
    const face = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.42), m);
    face.position.set(0, y + dy, 0.205);
    g.add(box, face);
  }
  g.add(pole);
  g.userData.pole = pole;
  g.userData.boardTop = y + 0.46;
  g.userData.set = (dir, blinkOff = false) => {
    const tex = dartTexture(blinkOff ? 'off' : dir);
    if (mat.map !== tex) { mat.map = tex; mat.needsUpdate = true; }
  };
  return g;
}

// Prague tram stop post (zastávkový označník): a red frame column. From the top: the tram
// stop sign (blue square with a white field and a black tram), the white name plate with the
// zone letter and the lines serving the stop, a red panel, the timetable case and the red base
// box with the electrical warning sticker. Faces +Z; origin at platform level.
let stopTopTex = null, timetableTex = null, baseTex = null;
export function makeStopSign(name, request = false, lines = ['22']) {
  const g = new THREE.Group();
  const red = lambert(0xd5161e);
  const W = 0.56;
  // the two side rails of the frame and cross pieces
  for (const x of [-W / 2, W / 2]) {
    const rail = new THREE.Mesh(new THREE.BoxGeometry(0.035, 3.45, 0.06), red);
    rail.position.set(x, 1.72, 0);
    g.add(rail);
  }
  const panel = (y, h, mat, depth = 0.08) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(W, h, depth), mat);
    m.position.set(0, y, 0);
    g.add(m);
    return m;
  };
  const face = (y, h, tex, w = W - 0.04) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshLambertMaterial({ map: tex }));
    m.position.set(0, y, 0.065); // in front of the deepest (12 cm) panel boxes
    g.add(m);
  };
  // tram stop sign
  if (!stopTopTex) stopTopTex = keptTexture(160, 160, (c, w, h) => {
    c.fillStyle = '#d5161e'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#ffffff'; c.fillRect(10, 10, w - 20, h - 20);
    c.fillStyle = '#1f5fb4'; c.fillRect(16, 16, w - 32, h - 32);
    c.fillStyle = '#ffffff'; c.fillRect(28, 28, w - 56, h - 56);
    // black tram (side view) with pantograph
    c.fillStyle = '#111';
    c.fillRect(42, 76, 76, 20);
    c.beginPath(); c.moveTo(42, 76); c.lineTo(36, 86); c.lineTo(42, 96); c.fill();
    c.beginPath(); c.moveTo(118, 76); c.lineTo(124, 86); c.lineTo(118, 96); c.fill();
    c.fillStyle = '#fff';
    for (let x = 48; x < 114; x += 11) c.fillRect(x, 79, 7, 7);
    c.strokeStyle = '#111'; c.lineWidth = 2.5;
    c.beginPath(); c.moveTo(74, 76); c.lineTo(80, 68); c.lineTo(86, 76); c.moveTo(80, 68); c.lineTo(80, 63); c.moveTo(72, 63); c.lineTo(88, 63); c.stroke();
    c.fillStyle = '#111';
    for (const x of [52, 64, 96, 108]) { c.beginPath(); c.arc(x, 97, 3.2, 0, Math.PI * 2); c.fill(); }
  });
  panel(3.17, 0.58, red, 0.12);
  face(3.17, 0.54, stopTopTex);
  // name plate with zone letter and lines
  const nameTex = canvasTexture(256, 220, (c, w, h) => {
    c.fillStyle = '#d5161e'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#f7f7f4'; c.fillRect(8, 8, w - 16, h - 16);
    c.fillStyle = '#222';
    let size = 34;
    const text = name + (request ? ' ✋' : '');
    c.font = `600 ${size}px Arial, sans-serif`;
    while (c.measureText(text).width > w - 70 && size > 14) { size -= 2; c.font = `600 ${size}px Arial, sans-serif`; }
    c.textBaseline = 'middle';
    c.fillText(text, 18, 42);
    c.strokeStyle = '#222'; c.lineWidth = 3;
    c.beginPath(); c.arc(w - 30, 42, 15, 0, Math.PI * 2); c.stroke();
    c.font = 'bold 20px Arial, sans-serif'; c.textAlign = 'center';
    c.fillText('A', w - 30, 43);
    c.fillStyle = '#ccc'; c.fillRect(16, 72, w - 32, 2);
    c.fillStyle = '#222'; c.font = '40px Arial, sans-serif'; c.textAlign = 'left';
    const row = (arr, y) => arr.forEach((l, i) => c.fillText(l, 22 + i * 72, y));
    row(lines.slice(0, 3), 112);
    row(lines.slice(3, 6), 168);
  });
  panel(2.6, 0.5, red);
  face(2.6, 0.46, nameTex);
  // empty red panel and the timetable case
  panel(2.12, 0.38, red);
  const redGlass = new THREE.Mesh(new THREE.PlaneGeometry(W - 0.08, 0.32), lambert(0xc41018));
  redGlass.position.set(0, 2.12, 0.045);
  g.add(redGlass);
  if (!timetableTex) timetableTex = keptTexture(128, 160, (c, w, h) => {
    c.fillStyle = '#b8b8b2'; c.fillRect(0, 0, w, h);
    for (const [x, y, ww, hh, col] of [[6, 6, 56, 46, '#fafafa'], [66, 6, 56, 46, '#fafafa'], [6, 56, 56, 46, '#fafafa'], [66, 56, 56, 46, '#fafafa'], [6, 106, 56, 48, '#f3d24a'], [66, 106, 56, 48, '#fafafa']]) {
      c.fillStyle = col; c.fillRect(x, y, ww, hh);
      c.fillStyle = '#9a9a9a';
      for (let ly = y + 6; ly < y + hh - 3; ly += 5) c.fillRect(x + 4, ly, ww - 8, 1);
    }
  });
  panel(1.55, 0.7, red);
  face(1.55, 0.66, timetableTex);
  // base box with the "danger: electrical equipment" sticker
  if (!baseTex) baseTex = keptTexture(128, 128, (c, w, h) => {
    c.fillStyle = '#d5161e'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#f5d000'; c.fillRect(44, 30, 40, 50);
    c.fillStyle = '#111';
    c.beginPath(); c.moveTo(64, 36); c.lineTo(80, 64); c.lineTo(48, 64); c.closePath(); c.fill();
    c.fillStyle = '#f5d000';
    c.beginPath(); c.moveTo(66, 44); c.lineTo(60, 55); c.lineTo(65, 55); c.lineTo(61, 62); c.lineTo(69, 51); c.lineTo(64, 51); c.closePath(); c.fill();
  });
  panel(0.42, 0.62, red, 0.12);
  face(0.42, 0.58, baseTex);
  // grey back of the panels
  const back = new THREE.Mesh(new THREE.PlaneGeometry(W, 3.2), lambert(0xb01218));
  back.position.set(0, 1.75, -0.05);
  back.rotation.y = Math.PI;
  g.add(back);
  return g;
}
