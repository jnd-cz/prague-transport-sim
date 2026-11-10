// The hybrid Tatra T3 (#248; assets/t3h/, CC BY-NC 4.0, see its LICENSE.txt): SimonStrikesBack's body,
// interior and cab (CC BY 4.0) with conflig's collector, mirror and lamps (CC BY-NC 4.0), rigged in the
// project's asset lab (street-life-boarding v14). Loaded once into a car template:
// - the parts that never move merged by kind into vertex-coloured meshes: outside the shell, the saloon
//   (left out on the lighter level) and the glass;
// - the moving parts kept as the asset's nodes: door leaves, bogies and wheels, the collector, the lamps
//   (the asset's clips scrub the doors and the collector); the track-brake shoes and the couplers get
//   their own pivots;
// - the textured parts (lamps, collector, mirror, the cards) as they are.
// Each set owns its materials (traffic fades AI trams one by one) and its cards. The asset's axes: +X
// forward, +Y up, +Z right, origin on the rail plane midway between the bogies; the game's cars face +Z.
import * as THREE from 'three';
import { T3, CAR_PITCH } from './tram.js';
import { beamsMesh } from './lamps.js';

export const T3H_FILES = ['assets/t3h/tatra-t3-hybrid-nc.glb', 'assets/t3h/rig.json'];
export const T3H_CREDIT = 'Tatra T3 3D model: hybrid of "Tatra T3" by SimonStrikesBack (sketchfab.com, CC BY 4.0) '
  + 'and "Tatra T3" by Jakub Vaja (conflig) (sketchfab.com, CC BY-NC 4.0), modified; CC BY-NC 4.0.';

const PLANE = CAR_PITCH / 2;    // the plane two coupled heads meet in, from the car centre
// saloon materials: the seats, their frames and the grab rails, the ceiling and its lamps, the cab desk
const INSIDE = new Set(['Handles', 'Control_Panel', 'Red_Seat', 'Blue_Seat', 'Leather', 'Material',
  'Inner_Plastic_Glass', 'Interior_Walls', 'White_Ceiling']);
const GLASS_FAR = 0.85;         // the glass's opacity on the lighter level (no saloon behind it)

let proto = null;
export const hybridReady = () => !!proto;

const box = (g, m) => { const b = new THREE.Box3().setFromBufferAttribute(g.attributes.position); return m ? b.applyMatrix4(m) : b; };

// one geometry of position, normal and colour (the material's colour, linear) for merging
function painted(src, m, color) {
  const g = new THREE.BufferGeometry();
  const P = src.attributes.position;
  g.setAttribute('position', P.clone());
  if (src.attributes.normal) g.setAttribute('normal', src.attributes.normal.clone());
  const c = new Float32Array(P.count * 3), C = src.attributes.color;
  for (let i = 0; i < P.count; i++) {
    const k = C ? [C.getX(i), C.getY(i), C.getZ(i)] : [1, 1, 1];
    c[i * 3] = color.r * k[0]; c[i * 3 + 1] = color.g * k[1]; c[i * 3 + 2] = color.b * k[2];
  }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  if (src.index) g.setIndex(src.index.clone());
  else g.setIndex([...Array(P.count).keys()]);
  g.applyMatrix4(m);
  if (!g.attributes.normal) g.computeVertexNormals();
  return g;
}

// responses: the loader's bodies of T3H_FILES; contact: the contact wire over the rail (the lighter level's
// collector)
export async function loadHybridT3(responses, contact) {
  const [glbR, rigR] = responses;
  if (!glbR?.ok || !rigR?.ok) throw new Error('hybrid T3 files missing');
  const [{ GLTFLoader }, { mergeGeometries }] = await Promise.all([
    import('three/addons/loaders/GLTFLoader.js'), import('three/addons/utils/BufferGeometryUtils.js')]);
  const rig = await rigR.json();
  const gl = await new GLTFLoader().parseAsync(await glbR.arrayBuffer(), '');
  const src = gl.scene;
  src.updateMatrixWorld(true);
  const p = rig.pantograph;
  const movers = new Set([
    ...rig.doors.flatMap((d) => d.leaves.flatMap((l) => [l.outer, l.inner])),
    ...rig.bogies.map((b) => b.name), ...rig.wheels.map((w) => w.name),
    p.root, p.head, ...p.linkages.flatMap((l) => [l.lower, l.upper]),
    ...rig.signals.left, ...rig.signals.right, ...(rig.brakes || [])]);
  const cards = new Set([...rig.numberPlates, ...rig.routePlates, rig.infoPlates.frontDestination,
    rig.infoPlates.runNumber, ...rig.infoPlates.sideBoards]);
  const bogieNames = new Set(rig.bogies.map((b) => b.name));

  // the template: every node that is not a plain mesh (keeping the asset's hierarchy and transforms, so
  // its clips drive the copies by name), the moving meshes as they are
  const top = src.getObjectByName(rig.root) || src;
  const copy = new Map();
  const template = new THREE.Group();
  copy.set(top, template);
  template.name = top.name;
  top.traverse((o) => {
    if (o === top) return;
    const mover = movers.has(o.name);
    if (o.isMesh && !mover && !o.children.length) return;
    const c = o.isMesh && mover ? new THREE.Mesh(o.geometry, o.material) : new THREE.Group();
    c.name = o.name;
    // (the node's own transform, not its matrix decomposed: the lamps' glows are stored off at scale 0, whose
    // matrix decomposes to a NaN rotation, and they never drew)
    c.position.copy(o.position); c.quaternion.copy(o.quaternion); c.scale.copy(o.scale);
    copy.get(o.parent).add(c);
    copy.set(o, c);
  });
  // the frame a plain mesh moves with: its nearest moving ancestor, or the car
  const frameOf = (o) => { for (let q = o.parent; q && q !== top; q = q.parent) if (movers.has(q.name)) return q; return top; };
  const inv = new Map();
  const rel = (o, f) => {
    if (!inv.has(f)) inv.set(f, f === top ? new THREE.Matrix4().copy(top.matrixWorld).invert() : f.matrixWorld.clone().invert());
    return new THREE.Matrix4().multiplyMatrices(inv.get(f), o.matrixWorld);
  };
  const shell = (b) => b.min.y > 0.84 && b.max.y < 3.1 && Math.max(-b.min.z, b.max.z) < 1.25 && Math.max(-b.min.x, b.max.x) < 6.95;
  const paint = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.75, metalness: 0, side: THREE.DoubleSide });
  // (one pass for both faces: three draws a double-sided transparent material twice, back then front, and
  // the 13 glass meshes of a car cost 0.9 ms a frame in tools/frametime.py's scene; dark glass at 18 % shows
  // no sorting between its faces)
  const glass = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.2, metalness: 0, side: THREE.DoubleSide, transparent: true, opacity: 0.18, depthWrite: false, forceSinglePass: true });
  glass.userData = { opacity: 0.18, glass: true }; // (traffic's fade multiplies it)
  const buckets = new Map(); // frame -> { out, in, glass, dest, run: [geometries] }
  const put = (f, kind, g) => {
    if (!buckets.has(f)) buckets.set(f, { out: [], in: [], glass: [], dest: [], run: [] });
    buckets.get(f)[kind].push(g);
  };
  const kept = new Map(); // the textured parts by frame and material (a plate keeps its name)
  const stats = { kept: 0, merged: 0, dropped: 0, shoes: 0, couplers: 0 };
  const shoes = [], couplers = [];
  const cardOf = (name) => name.startsWith(rig.infoPlates.frontDestination) ? 'dest' : name.startsWith(rig.infoPlates.runNumber) ? 'run' : null;
  top.traverse((o) => {
    if (!o.isMesh || movers.has(o.name)) return;
    const m = o.material, f = frameOf(o), M = rel(o, f);
    if (m.opacity === 0) { stats.dropped++; return; } // (an invisible helper)
    const textured = m.map || m.normalMap || m.emissiveMap || (m.emissive && m.emissive.getHex() !== 0);
    if (textured || cards.has(o.name)) {
      const key = `${f.uuid}|${m.uuid}`;
      if (!kept.has(key)) kept.set(key, { f, m, geos: [], name: o.name });
      const g = o.geometry.clone().applyMatrix4(M);
      if (rig.numberPlates.includes(o.name)) fleetSize(g);
      kept.get(key).geos.push(g);
      stats.kept++;
      return;
    }
    // (the destination and run cards' backs and clips: hidden with the card when the car shows none)
    const card = cardOf(o.name);
    if (card) { put(f, card, painted(o.geometry, M, m.color)); stats.merged++; return; }
    const b = box(o.geometry, M);
    // the track-brake shoes: a bogie's parts between its axles over a rail; the couplers: the bars under
    // the body ends
    if (bogieNames.has(f.name) && b.max.x - b.min.x < 1.3 && Math.abs(b.min.z + b.max.z) > 0.8 && !o.name.startsWith('Wheel')) {
      shoes.push({ f, g: painted(o.geometry, M, m.color), b }); stats.shoes++; return;
    }
    if (f === top && Math.min(Math.abs(b.min.x), Math.abs(b.max.x)) > 5 && b.max.y < 0.7 && Math.max(-b.min.z, b.max.z) < 0.2) {
      couplers.push({ g: painted(o.geometry, M, m.color), b }); stats.couplers++; return;
    }
    const kind = m.transparent ? 'glass' : f === top && (INSIDE.has(m.name) || shell(b)) ? 'in' : 'out';
    put(f, kind, painted(o.geometry, M, m.color));
    stats.merged++;
  });
  for (const [f, k] of buckets) {
    for (const [kind, mat] of [['out', paint], ['in', paint], ['glass', glass], ['dest', paint], ['run', paint]]) {
      if (!k[kind].length) continue;
      const mesh = new THREE.Mesh(mergeGeometries(k[kind]), mat);
      mesh.name = `T3H_${kind}`;
      copy.get(f).add(mesh);
    }
  }
  for (const { f, m, geos, name } of kept.values()) {
    const merged = geos.length > 1 ? mergeGeometries(geos) : geos[0];
    for (const g of merged ? [merged] : geos) { // (parts whose attributes differ stay apart)
      const mesh = new THREE.Mesh(g, m);
      mesh.name = name;
      copy.get(f).add(mesh);
    }
  }
  // the shoes hang SHOE_GAP over the rail (the asset has them 67 mm up): each on its own pivot under its
  // bogie, which drops it onto the rail when its magnets are on
  for (const s of shoes) {
    const piv = new THREE.Group();
    piv.name = 'T3H_shoe';
    const bogieY = s.f.matrixWorld.elements[13];
    s.g.translate(0, T3.trackBrakeGap - (s.b.min.y + bogieY), 0);
    piv.add(new THREE.Mesh(s.g, paint));
    piv.userData.drop = T3.trackBrakeGap;
    copy.get(s.f).add(piv);
  }
  // the couplers: each bar turns about the yoke's pin under the body end (T3.couplerPivot); the asset's
  // bar (5.28-7.41 m) is refitted to run from just behind the pin to the coupling plane (the heads' 80 mm
  // beyond it are not drawn: two bars would overlap there)
  for (const c of couplers) {
    const e = c.b.min.x > 0 ? 1 : -1, x0 = e > 0 ? c.b.min.x : -c.b.max.x, x1 = e > 0 ? c.b.max.x : -c.b.min.x;
    const pin = T3.couplerPivot, a = pin - 0.1, P = c.g.attributes.position, y = (c.b.min.y + c.b.max.y) / 2;
    for (let i = 0; i < P.count; i++) {
      const x = P.getX(i) * e;
      P.setX(i, e * (a + (x - x0) * (PLANE - a) / (x1 - x0)) - e * pin);
      P.setY(i, P.getY(i) - y);
    }
    P.needsUpdate = true;
    c.g.computeBoundingBox(); c.g.computeBoundingSphere();
    const piv = new THREE.Group();
    piv.name = e > 0 ? 'T3H_coupler_front' : 'T3H_coupler_rear';
    piv.position.set(e * pin, y, 0);
    piv.add(new THREE.Mesh(c.g, paint));
    template.add(piv);
  }
  template.traverse((o) => {
    if (!o.isMesh) return;
    // (no environment map in the game: metals would draw black)
    if (o.material.isMeshStandardMaterial) { o.material.metalness = 0; o.material.roughness = Math.max(o.material.roughness, 0.5); }
    o.geometry.computeBoundingSphere();
    o.geometry.userData.shared = true;
    for (const t of Object.values(o.material)) if (t?.isTexture) t.userData.shared = true;
  });
  // the bogies at the real T3's pivots (T3.bogies; the asset has them 6.485 m apart), their shoes with them
  for (const b of rig.bogies) { const n = template.getObjectByName(b.name); if (n) n.position.x = Math.sign(b.x) * T3.bogies / 2; }
  // the lamps' glow: off, bright when on
  for (const n of [...rig.signals.left, ...rig.signals.right, ...(rig.brakes || [])]) {
    const g = template.getObjectByName(n);
    if (!g) continue;
    g.scale.setScalar(1); g.visible = false;
    if (g.material) { g.material.emissiveIntensity = 4; g.material.toneMapped = false; }
  }
  // the lighter level (AI trams farther than FULL_OUT): the car posed with its doors shut and the collector
  // at the wire, all but the saloon and the lamps' glow merged in the car's frame by material; the cards
  // and their backs stay apart (their textures and visibility change), the glass is darker (no saloon)
  const glassFar = glass.clone();
  glassFar.opacity = GLASS_FAR; glassFar.userData = { opacity: GLASS_FAR, glass: true };
  const mixer = new THREE.AnimationMixer(template);
  for (const [name, u] of [['Door_Front_Open', 0], ['Door_Middle_Open', 0], ['Door_Rear_Open', 0], ['Pantograph_Lower', collectorU(rig, contact)]]) {
    const clip = THREE.AnimationClip.findByName(gl.animations, name);
    if (!clip) continue;
    const a = mixer.clipAction(clip); a.play(); a.paused = true; a.time = u * clip.duration;
  }
  mixer.update(0);
  template.updateMatrixWorld(true);
  const glows = new Set([...rig.signals.left, ...rig.signals.right, ...(rig.brakes || [])]);
  const apart = (name) => cards.has(name) || name === 'T3H_dest' || name === 'T3H_run';
  const light = new THREE.Group(), flat = new Map();
  light.name = 'T3H_light';
  template.traverse((o) => {
    if (!o.isMesh || o.name === 'T3H_in' || glows.has(o.name)) return;
    const g = o.geometry.clone().applyMatrix4(o.matrixWorld); // (the template has no parent)
    g.userData.shared = true;
    if (apart(o.name)) { const k = new THREE.Mesh(g, o.material); k.name = o.name; light.add(k); return; }
    const m = o.material === glass ? glassFar : o.material;
    if (!flat.has(m)) flat.set(m, []);
    flat.get(m).push(g);
  });
  for (const [m, geos] of flat) {
    const merged = geos.length > 1 ? mergeGeometries(geos) : geos[0];
    for (const g of merged ? [merged] : geos) {
      g.computeBoundingSphere(); g.userData.shared = true;
      light.add(new THREE.Mesh(g, m));
    }
  }
  mixer.stopAllAction(); mixer.uncacheRoot(template);
  const bogie = T3.bogies / 2;
  // the headlights (one emissive mesh across the front, lit always: the user, 2026-11-10, #436): their centres in the
  // car's frame for the high beams' glow (the asset's (x, y, z) is the car's (-z, y, x))
  let heads = [];
  template.traverse((o) => {
    if (heads.length || !o.isMesh || !o.name.startsWith('White_Emission')) return;
    const b = box(o.geometry), r = (b.max.y - b.min.y) / 2, y = (b.min.y + b.max.y) / 2;
    heads = [b.min.z + r, b.max.z - r].map((z) => [-z, y, b.max.x + 0.01]);
  });
  proto = { template, light, rig, clips: gl.animations, bogie, stats, heads };
  return proto;
}

// the collector clip's position (0..1) for a contact height over the rail
function collectorU(rig, h) {
  const p = rig.pantograph, c = THREE.MathUtils.clamp(h, p.minContactHeight, p.maxContactHeight);
  return (p.maxContactHeight - c) / (p.maxContactHeight - p.minContactHeight);
}

// ------------------------------------------------------------------------------------------- cards
// The plates and cards as the user described them (src/models.js, "The T3's number plates and cards"),
// drawn here over the asset's own plates, which have cream on navy and no frame.
function canvas(w, h, bg) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const x = c.getContext('2d');
  if (bg) { x.fillStyle = bg; x.fillRect(0, 0, w, h); }
  x.textAlign = 'center'; x.textBaseline = 'middle';
  return [c, x];
}
function texture(c, shared) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.flipY = false; t.anisotropy = 4;
  if (shared) t.userData.shared = true;
  return t;
}
const cache = new Map();
const cached = (key, make) => { if (!cache.has(key)) cache.set(key, texture(make(), true)); return cache.get(key); };
const up = (s) => String(s ?? '').normalize('NFC').trim().toLocaleUpperCase('cs-CZ');
const BLUE = '#1f57a8', WHITE = '#f4f4f0', IVORY = '#f5f1e5'; // (DPP blue as src/models.js; the side boards' ivory)

// the route number plates: on the roof (navy on cream), the inverted one in the rear window, the mirror's
function routeTexture(line, style) {
  return cached(`route:${style}:${line}`, () => {
    const mirror = style === 'mirror', inv = style === 'inverted', [c, x] = canvas(mirror ? 384 : 512, mirror ? 512 : 384, inv ? WHITE : BLUE);
    const w = c.width, h = c.height, t = String(line);
    x.fillStyle = inv ? '#1d3f86' : '#ffffff';
    x.font = `bold ${Math.min(h * 0.78, (w * 1.27) / t.length)}px Arial, sans-serif`;
    x.fillText(t, w / 2, h * 0.53, w * 0.94);
    return c;
  });
}
// the destination card behind the windscreen: blue capitals in a blue frame, two balanced lines when long
function destinationTexture(dest) {
  return cached(`dest:${dest ?? ''}`, () => {
    const [c, x] = canvas(1024, 384, WHITE);
    x.strokeStyle = BLUE; x.lineWidth = 18; x.strokeRect(15, 15, 994, 354);
    let lines = up(dest).split('\n');
    if (lines.length === 1 && lines[0].length > 13 && lines[0].includes(' ')) {
      const w = lines[0].split(/\s+/);
      let best = Infinity, at = 1;
      for (let i = 1; i < w.length; i++) {
        const d = Math.abs(w.slice(0, i).join(' ').length - w.slice(i).join(' ').length);
        if (d < best) { best = d; at = i; }
      }
      lines = [w.slice(0, at).join(' '), w.slice(at).join(' ')];
    }
    x.fillStyle = BLUE;
    lines.slice(0, 2).forEach((l, i, a) => { x.font = `bold ${a.length === 1 ? 200 : 140}px Arial, sans-serif`; x.fillText(l, 512, 30 + ((i + 0.5) * 324) / a.length, 920); });
    return c;
  });
}
// the side board in the second window: the route number and the destination
function sideTexture(line, dest) {
  return cached(`side:${line}:${dest ?? ''}`, () => {
    const [c, x] = canvas(1024, 600, IVORY);
    x.fillStyle = BLUE;
    x.font = 'bold 520px Arial, sans-serif'; x.fillText(String(line), 153, 318, 254);
    const lines = dest ? [up(dest)] : [''];
    lines.forEach((l, i) => { x.font = `bold ${Math.min(64, (510 / lines.length) * 0.77)}px Arial, sans-serif`; x.fillText(l, 656, 45 + ((i + 0.5) * 510) / lines.length, 672); });
    return c;
  });
}
function runTexture(run) {
  const [c, x] = canvas(384, 448, '#101418');
  x.fillStyle = '#fffdf4'; x.font = 'bold 390px Arial, sans-serif'; x.fillText(String(run ?? ''), 192, 234, 344);
  return texture(c);
}
// The fleet numbers' digits 0.14 m tall on every side (the user, 2026-11-10: "fix the hybrid's fleet number size";
// src/t3simple.js FLEET has the photos' measurements). The asset's quads, under one texture, are 0.19 m tall on the
// ends and 0.23 m on the sides, so its digits were 0.106 and 0.13 m: the texture's digits fill FLEET_FILL of its
// height whatever the font, and each quad is scaled about its centre to FLEET_H / FLEET_FILL.
const FLEET_H = 0.14, FLEET_FILL = 132 / 192;
function fleetSize(g) {
  g.computeBoundingBox();
  const b = g.boundingBox, c = b.getCenter(new THREE.Vector3()), k = FLEET_H / FLEET_FILL / (b.max.y - b.min.y);
  g.translate(-c.x, -c.y, -c.z).scale(k, k, k).translate(c.x, c.y, c.z);
}
function fleetTexture(n) {
  const [c, x] = canvas(512, 192);
  const t = String(n);
  x.fillStyle = '#e3b625'; x.font = 'bold 100px Arial, sans-serif';
  const m = x.measureText(t), L = m.actualBoundingBoxLeft, R = m.actualBoundingBoxRight, A = m.actualBoundingBoxAscent, D = m.actualBoundingBoxDescent;
  const k = (FLEET_FILL * 192) / (A + D), kx = Math.min(k, 480 / (L + R));
  x.setTransform(kx, 0, 0, k, 256 - (kx * (R - L)) / 2, 96 - (k * (D - A)) / 2);
  x.fillText(t, 0, 0);
  return texture(c);
}
const setMap = (m, tex) => { if (!m || m.map === tex) return; if (m.map && !m.map.userData.shared && m.userData.own) m.map.dispose(); m.map = tex; m.userData.own = !tex.userData.shared; m.needsUpdate = true; };

// ---------------------------------------------------------------------------------------------- sets
let fleetCounter = 0;
// A set of `cars` cars on `root`. Fleet numbers are placeholders (as the run number until the data has
// them): Prague's T3SUCS were numbered from 7001.
export function makeHybridSet(root, line, cars, dest, run, collector) {
  const { template, rig, clips } = proto;
  const own = new Map();
  const mat = (m) => { let c = own.get(m); if (!c) { c = m.clone(); own.set(m, c); } return c; };
  Object.assign(root.userData, { hybrid: true, cars: [], bogie: proto.bogie, mats: { body: true }, line, dest, run, level: 'full' });
  const first = 7001 + 2 * (fleetCounter++ % 140);
  for (let k = 0; k < cars; k++) {
    const car = new THREE.Group();
    car.rotation.order = 'YXZ';
    // both levels, sharing the set's materials (the car's own for its fleet number)
    const r = template.clone(true), l = proto.light.clone(true);
    const fleetMat = new Map();
    for (const x of [r, l]) {
      x.rotation.y = -Math.PI / 2; // (the asset's +X forward onto the game's +Z)
      x.traverse((o) => {
        if (!o.material) return;
        if (rig.numberPlates.includes(o.name)) {
          if (!fleetMat.has(o.material)) { const c = o.material.clone(); c.map = fleetTexture(first + k); c.userData.own = true; fleetMat.set(o.material, c); }
          o.material = fleetMat.get(o.material);
        } else o.material = mat(o.material);
      });
      car.add(x);
    }
    l.visible = false;
    const n = (name) => r.getObjectByName(name);
    const both = (name) => [r.getObjectByName(name), l.getObjectByName(name)].filter(Boolean);
    const mixer = new THREE.AnimationMixer(r), act = {};
    for (const name of ['Door_Front_Open', 'Door_Middle_Open', 'Door_Rear_Open', 'Pantograph_Lower']) {
      const clip = THREE.AnimationClip.findByName(clips, name);
      if (!clip) continue;
      const a = mixer.clipAction(clip); a.play(); a.paused = true; act[name] = a;
    }
    car.userData.rig = {
      mixer, act, doors: -1, collector: -1, braking: null, track: -1,
      bogies: rig.bogies.map((b) => ({ node: n(b.name), front: b.x > 0, shoes: [] })),
      wheels: rig.wheels.map((w) => ({ node: n(w.name), r: w.radius })),
      couplers: [n('T3H_coupler_front'), n('T3H_coupler_rear')],
      brakes: (rig.brakes || []).map(n).filter(Boolean),
      signals: { left: rig.signals.left.map(n).filter(Boolean), right: rig.signals.right.map(n).filter(Boolean) }, lit: { left: false, right: false },
      full: r, light: l, plates: {},
    };
    const cr = car.userData.rig;
    for (const b of cr.bogies) b.node?.traverse((o) => { if (o.name === 'T3H_shoe') b.shoes.push(o); });
    car.userData.gear = gear(cr);
    // the high beams' glow over the leading car's headlights (src/lamps.js)
    if (k === 0 && proto.heads.length) { car.userData.beams = beamsMesh(proto.heads); car.add(car.userData.beams); }
    // the cards: the route plates on every car (the front one shows on the leading car, the rear one on the
    // last), the destination and run number in the leading car only
    cr.plates = {
      front: n('Route_Number_Front'), rear: n('Route_Number_Rear'), mirror: n('Route_Number_Mirror'),
      dest: n(rig.infoPlates.frontDestination), run: n(rig.infoPlates.runNumber), side: rig.infoPlates.sideBoards.map(n),
      destAll: [rig.infoPlates.frontDestination, 'T3H_dest'].flatMap(both), runAll: [rig.infoPlates.runNumber, 'T3H_run'].flatMap(both),
    };
    root.add(car);
    root.userData.cars.push(car);
  }
  setHybridLine(root, line, dest, run, true);
  poseHybrid(root, { doors: 0, collector });
  return root;
}

export function setHybridLine(model, line, dest = model.userData.dest, run = model.userData.run, force = false) {
  const u = model.userData;
  model.userData.cars.forEach((car, k) => {
    const p = car.userData.rig.plates;
    if (force || u.line !== line) {
      setMap(p.front?.material, routeTexture(line, 'normal'));
      setMap(p.rear?.material, routeTexture(line, 'inverted'));
      setMap(p.mirror?.material, routeTexture(line, 'mirror'));
    }
    if (force || u.line !== line || u.dest !== dest) for (const s of p.side) setMap(s?.material, sideTexture(line, dest));
    if (force || u.dest !== dest) setMap(p.dest?.material, destinationTexture(dest));
    if (force || u.run !== run) if (k === 0) setMap(p.run?.material, runTexture(run));
    // (no destination card on a tram whose destination we do not know; the cards only in the leading car)
    for (const o of p.destAll) o.visible = k === 0 && !!dest;
    for (const o of p.runAll) o.visible = k === 0;
  });
  Object.assign(u, { line, dest, run });
}

// The mechanisms from the game's state, each only when it changes: doors (0 closed .. 1 open), the
// collector's contact height over the rail, the brake lamps, the track-brake magnets (0 off, 1 the rear
// bogies', 2 all), the indicators' sides lit now (`signals`: { left, right }), the high beams.
export function poseHybrid(model, { doors, collector, braking, track, signals, highBeam } = {}) {
  const { cars } = model.userData;
  cars.forEach((car, k) => {
    const r = car.userData.rig;
    let scrub = false;
    if (doors !== undefined && Math.abs(doors - r.doors) > 1e-3) {
      r.doors = doors;
      for (const d of ['Door_Front_Open', 'Door_Middle_Open', 'Door_Rear_Open']) if (r.act[d]) r.act[d].time = THREE.MathUtils.clamp(doors, 0, 1) * r.act[d].getClip().duration;
      scrub = true;
    }
    if (collector !== undefined && Math.abs(collector - r.collector) > 1e-3 && r.act.Pantograph_Lower) {
      r.collector = collector;
      r.act.Pantograph_Lower.time = collectorU(proto.rig, collector) * r.act.Pantograph_Lower.getClip().duration;
      scrub = true;
    }
    if (scrub) r.mixer.update(0);
    // (the brake lamps at the set's rear: the coupled ends dark, as the built-in car's)
    const brakeLit = !!braking && k === cars.length - 1;
    if (braking !== undefined && brakeLit !== r.braking) { r.braking = brakeLit; for (const b of r.brakes) b.visible = brakeLit; }
    if (signals !== undefined) for (const s of ['left', 'right']) if (!!signals[s] !== r.lit[s]) { r.lit[s] = !!signals[s]; for (const g of r.signals[s]) g.visible = r.lit[s]; }
    if (highBeam !== undefined && car.userData.beams) car.userData.beams.visible = !!highBeam;
    if (track !== undefined && track !== r.track) {
      r.track = track;
      // (the rear bogie's magnets first, ČKD [ckd24] p. 16; src/tr37.js trackAngles)
      for (const b of r.bogies) for (const s of b.shoes) s.position.y = (track >= 2 || (track === 1 && !b.front)) ? -s.userData.drop : 0;
    }
  });
}

// The level a set is drawn at: 'full', or 'light' (no saloon, doors shut, everything merged; for AI trams
// beyond FULL_OUT). A set at its lighter level is posed as at its full one, which shows again at once.
export function setHybridLevel(model, level) {
  const u = model.userData;
  if (!u.hybrid || u.level === level) return;
  u.level = level;
  for (const car of u.cars) { car.userData.rig.full.visible = level === 'full'; car.userData.rig.light.visible = level !== 'full'; }
}
export const FULL_IN = 50, FULL_OUT = 60; // m from the camera: AI trams' full level (the saloon through the windows)

// ------------------------------------------------------------------------------------------ running
// A car's running gear for src/consist.js (hangConsist places the cars): its bogies' and wheels' nodes, the
// coupler bars' pivots. The rig's frame: +X the car's forward (z), +Z its right (-x).
function gear(r) {
  return {
    axle: 0.91, pinY: r.couplers[1]?.position.y ?? 0,
    live: () => r.full.visible, // (the lighter level has them merged)
    turn(i, d) { for (const b of r.bogies) if (b.node && b.front === (i === 0)) b.node.rotation.y = d; },
    roll(s) { for (const w of r.wheels) if (w.node) w.node.rotation.z = -s / w.r; },
    swing(i, q) {
      const bar = r.couplers[i];
      if (!bar) return;
      if (!q) { bar.rotation.set(0, 0, 0); return; }
      // the bar points along sign*X; up and down too (held along its car, each head rode on that car's pitch
      // and the two stepped against each other by cm where the track changes its grade between the cars, #356)
      const sign = i === 0 ? 1 : -1, fx = q.z, rz = -q.x;
      bar.rotation.y = sign > 0 ? Math.atan2(-rz, fx) : Math.atan2(rz, -fx);
      bar.rotation.z = sign * Math.atan2(q.y, Math.hypot(fx, rz));
    },
  };
}
