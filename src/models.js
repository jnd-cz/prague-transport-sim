// Low-poly models built from primitives: T3 tram, cars, pedestrians, signals and signs.
import * as THREE from 'three';

const lambert = (color, extra = {}) => new THREE.MeshLambertMaterial({ color, ...extra });

function canvasTexture(w, h, draw) {
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  draw(cv.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// Plan outline of the car body: straight sides with elliptical ends.
function planShape(halfW, halfL, endDepth) {
  const straight = halfL - endDepth, n = 18, s = new THREE.Shape();
  for (let i = 0; i <= n; i++) { // front end, from the right side through the nose
    const a = (Math.PI * i) / n;
    const x = halfW * Math.cos(a), z = straight + endDepth * Math.sin(a);
    i === 0 ? s.moveTo(x, z) : s.lineTo(x, z);
  }
  for (let i = 0; i <= n; i++) { // rear end
    const a = Math.PI + (Math.PI * i) / n;
    s.lineTo(halfW * Math.cos(a), -straight + endDepth * Math.sin(a));
  }
  return s;
}

// One horizontal livery band of the body, from y0 to y1, inset by `inset` metres.
function band(y0, y1, inset, mat) {
  const geo = new THREE.ExtrudeGeometry(planShape(1.25 - inset, 7 - inset, 1.05 - inset * 0.6), { depth: y1 - y0, bevelEnabled: false, curveSegments: 1 });
  geo.rotateX(-Math.PI / 2); // extrusion becomes height
  geo.translate(0, y0, 0);
  return new THREE.Mesh(geo, mat);
}

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
const routeBoxTexture = (line) => numberTexture(line, 160, 128, '#ffffff', DPP_BLUE, 0.9);
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

// Tatra T3 in the Prague livery: red lower body, cream window band and upper body, dark grey
// roof, cream four-leaf folding doors, blue route number boxes, orange diamond pantograph.
// One car: origin = centre of the body at rail level, facing +Z (local), 14 m x 2.5 m.
function makeT3Car(line, mats) {
  const g = new THREE.Group();
  g.rotation.order = 'YXZ';
  const { red, cream, glass, dark, roof, chrome, orange, grey, rubber, rbMat } = mats;
  g.add(band(0.40, 0.52, 0.04, dark));          // underframe skirt
  g.add(band(0.52, 0.60, -0.006, chrome));      // bumper / rubbing strip
  g.add(band(0.60, 1.30, 0, red));              // lower body
  g.add(band(1.30, 1.42, -0.008, cream));       // window sill
  g.add(band(1.42, 2.34, 0.03, glass));         // window band (recessed glass)
  g.add(band(2.34, 2.62, 0.004, cream));        // upper body, slight tumblehome
  g.add(band(2.62, 2.80, 0.02, cream));
  // rounded roof edge built from narrowing bands
  [[2.80, 2.86, 0.06], [2.86, 2.92, 0.13], [2.92, 2.98, 0.24], [2.98, 3.03, 0.40], [3.03, 3.07, 0.62]]
    .forEach(([a, b, i]) => g.add(band(a, b, i, roof)));
  const box = (w, h, d, mat, x, y, z, parent = g) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    parent.add(m);
    return m;
  };
  const DOORS = [4.85, -0.25, -5.0]; // door centres on the right side (-X)
  const inDoor = (z) => DOORS.some((d) => Math.abs(z - d) < 0.7);
  // window pillars, and the transom between the big panes and the top hopper windows
  for (let z = -5.4; z <= 5.5; z += 1.36) for (const x of [-1.235, 1.235]) {
    if (x < 0 && inDoor(z)) continue;
    box(0.04, 0.93, 0.13, cream, x, 1.88, z);
  }
  for (const x of [-1.232, 1.232]) {
    let z0 = -5.9;
    const stops = x < 0 ? [...DOORS].sort((a, b) => a - b).flatMap((d) => [d - 0.66, d + 0.66]) : [];
    const cuts = [z0, ...stops, 5.9];
    for (let k = 0; k < cuts.length; k += 2) {
      const a = cuts[k], b = cuts[k + 1];
      if (b - a > 0.2) box(0.03, 0.045, b - a, cream, x, 2.06, (a + b) / 2);
    }
  }
  // windscreen corner pillars at both ends
  for (const sz of [1, -1]) for (const sx of [1, -1]) box(0.09, 0.93, 0.09, cream, sx * 0.84, 1.88, sz * 6.5);
  // four-leaf folding doors: cream leaves, tall glazing, dark seams, step and door lamp
  for (const z of DOORS) {
    box(0.03, 2.0, 1.28, cream, -1.262, 1.42, z);
    for (const dz of [-0.465, -0.155, 0.155, 0.465]) {
      box(0.035, 0.95, 0.22, glass, -1.268, 1.82, z + dz);
      box(0.03, 0.36, 0.2, glass, -1.268, 0.98, z + dz);
    }
    for (const dz of [-0.31, 0, 0.31]) box(0.04, 2.0, 0.018, rubber, -1.27, 1.42, z + dz);
    box(0.18, 0.12, 1.2, dark, -1.15, 0.36, z); // step
    box(0.05, 0.06, 0.16, orange, -1.27, 2.5, z); // door indicator lamp
  }
  // front: headlights with chrome rings, indicators, coupler cover, wipers, mirror
  const lamp = (x, y, z, r, color, facing) => {
    const l = new THREE.Mesh(new THREE.CircleGeometry(r, 16), new THREE.MeshBasicMaterial({ color }));
    l.position.set(x, y, z);
    l.rotation.y = facing;
    g.add(l);
    const ring = new THREE.Mesh(new THREE.RingGeometry(r, r * 1.3, 16), chrome);
    ring.position.set(x, y, z - Math.cos(facing) * 0.002);
    ring.rotation.y = facing;
    g.add(ring);
  };
  const endZ = (x, sz, inset = 0) => {
    // surface of the elliptical end at lateral x
    const hw = 1.25 - inset, straight = 7 - inset - (1.05 - inset * 0.6), d = 1.05 - inset * 0.6;
    return sz * (straight + d * Math.sqrt(Math.max(0, 1 - (x / hw) ** 2)));
  };
  for (const sz of [1, -1]) {
    for (const x of [-0.72, 0.72]) {
      const face = sz > 0 ? Math.atan2(x * 0.9, 1) : Math.PI + Math.atan2(-x * 0.9, 1);
      lamp(x, 0.92, endZ(x, sz) + sz * 0.012, 0.1, sz > 0 ? 0xfff3c0 : 0x9a1010, face);
      const xi = x * 1.32;
      const fi = sz > 0 ? Math.atan2(xi * 0.9, 1) : Math.PI + Math.atan2(-xi * 0.9, 1);
      lamp(xi, 0.92, endZ(xi, sz) + sz * 0.012, 0.055, 0xe08a1a, fi);
    }
    box(0.55, 0.16, 0.34, dark, 0, 0.48, sz * 6.95); // coupler under its cover
  }
  for (const x of [-0.38, 0.38]) {
    const w = box(0.025, 0.75, 0.02, rubber, x, 1.78, endZ(x, 1, 0.03) + 0.02);
    w.rotation.z = x > 0 ? 0.32 : -0.32;
  }
  const mirrorArm = box(0.3, 0.03, 0.03, grey, -1.37, 2.2, 6.15);
  mirrorArm.rotation.y = -0.4;
  box(0.05, 0.32, 0.14, dark, -1.5, 2.12, 6.22);
  // route number boxes: front dome, rear, and beside the front door
  const rb = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.31), rbMat);
  rb.position.set(0, 2.58, 7.0);
  g.add(rb);
  const rbRear = rb.clone();
  rbRear.position.set(0, 2.58, -7.0);
  rbRear.rotation.y = Math.PI;
  g.add(rbRear);
  const rbSide = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.3), rbMat);
  rbSide.position.set(-1.27, 1.95, 5.65);
  rbSide.rotation.y = -Math.PI / 2;
  g.add(rbSide);
  // bogies: side frames, wheels, springs and the magnetic track brake shoes
  const wheelGeo = new THREE.CylinderGeometry(0.35, 0.35, 0.12, 14), wheelMat = lambert(0x161616);
  for (const z of [-3.8, 3.8]) {
    for (const x of [-0.93, 0.93]) {
      box(0.16, 0.3, 2.5, dark, x, 0.44, z);
      for (const dz of [-0.45, 0.45]) {
        const sp = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.22, 8), grey);
        sp.position.set(x, 0.68, z + dz);
        g.add(sp);
      }
    }
    box(1.7, 0.18, 0.5, dark, 0, 0.5, z); // bolster
    for (const dz of [-0.95, 0.95]) for (const x of [-0.72, 0.72]) {
      const w = new THREE.Mesh(wheelGeo, wheelMat);
      w.rotation.z = Math.PI / 2;
      w.position.set(x, 0.35, z + dz);
      g.add(w);
    }
    for (const x of [-0.72, 0.72]) box(0.1, 0.09, 1.0, grey, x, 0.1, z);
  }
  // underfloor equipment between the bogies
  for (const [x, z, l] of [[0.55, 0.6, 2.2], [-0.55, -0.9, 1.6], [0.45, -2.0, 0.9]]) box(0.9, 0.3, l, dark, x, 0.48, z);
  // roof: resistor box, ventilation hatches and the orange diamond pantograph
  box(1.3, 0.26, 2.6, lambert(0x48494a), 0, 3.19, -2.4);
  for (const z of [4.4, -0.2, -5.3]) box(0.7, 0.07, 0.85, grey, 0, 3.1, z);
  box(1.1, 0.12, 1.4, dark, 0, 3.12, 3.1); // pantograph base frame
  const pan = new THREE.Group();
  const bar = (x0, y0, z0, x1, y1, z1, mat = orange) => {
    const a = new THREE.Vector3(x0, y0, z0), b = new THREE.Vector3(x1, y1, z1);
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, a.distanceTo(b), 5), mat);
    m.position.copy(a).add(b).multiplyScalar(0.5);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    pan.add(m);
  };
  // diamond (rhombus) frames on both sides, seen from the side as < >
  for (const x of [-0.5, 0.5]) {
    bar(x, 3.2, -0.65, x * 0.6, 4.05, 0); bar(x, 3.2, 0.65, x * 0.6, 4.05, 0);
    bar(x * 0.6, 4.05, 0, x * 0.25, 4.85, -0.25); bar(x * 0.6, 4.05, 0, x * 0.25, 4.85, 0.25);
  }
  bar(-0.3, 4.05, 0, 0.3, 4.05, 0);
  // collector head with horns
  const head = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.05, 0.12), dark);
  head.position.set(0, 4.88, 0);
  pan.add(head);
  bar(-0.62, 4.88, 0, -0.85, 4.74, 0, dark); bar(0.62, 4.88, 0, 0.85, 4.74, 0, dark);
  // same place as on the detailed model (3.1 m ahead of the car centre), raised to the wire:
  // the frame is stretched up from its base at 3.2 m so the head (4.88 m) meets the wire
  const k = (CONTACT_WIRE - RAIL_TOP - 0.01 - 3.2) / (4.88 - 3.2);
  pan.scale.y = k;
  pan.position.set(0, 3.2 - 3.2 * k, 3.1);
  g.add(pan);
  return g;
}

// A T3 set of one or two cars (Prague ran most T3s as two-car multiple units). The cars are
// separate children so each can follow the track on its own bogies: see placeConsist().
// Each set owns its materials (traffic fades them individually).
// dest: the destination card's text (none: no card); run: the run number card
export function makeT3({ line = '22', cars = 1, detailed = true, dest = null, run = '' } = {}) {
  const root = new THREE.Group();
  root.userData.line = line;
  if (detailed && detailedProto) return makeDetailedSet(root, line, cars, dest, run);
  root.userData.bogie = 3.8;     // bogie pivots of the built-in model
  root.userData.bodyFront = 7.0;
  const mats = {
    red: lambert(0xb81a1f), cream: lambert(0xefe4c4), glass: lambert(0x1c262d), dark: lambert(0x2a2a2a),
    roof: lambert(0x5d6164), chrome: lambert(0xb9bcbf), orange: lambert(0xd8541c), grey: lambert(0x6a6d70),
    rubber: lambert(0x111111), rbMat: new THREE.MeshBasicMaterial({ map: routeBoxTexture(line) }),
  };
  root.userData.mats = mats;
  root.userData.cars = [];
  for (let k = 0; k < cars; k++) {
    const car = makeT3Car(line, mats);
    root.add(car);
    root.userData.cars.push(car);
  }
  return root;
}

// Detailed T3 (Sketchfab "Tatra T3" low-poly model, CC BY-NC 4.0; see assets/t3/LICENSE.txt),
// reduced to a single 2048 px colour texture with the ambient occlusion baked in. Its axes were
// found by principal component analysis of the body: length e1 (front = wipers), width e2
// (doors on +e2 = right), height e3 (wheels on +e3 = down); units are metres (body 14.0 m).
let detailedProto = null;
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
  const plate = (map) => new THREE.MeshBasicMaterial({ map, polygonOffset: true, polygonOffsetFactor: -2 });
  // (cards on the glass: lit like the body, not glowing)
  const card = (map) => new THREE.MeshLambertMaterial({ map, polygonOffset: true, polygonOffsetFactor: -2 });
  const mats = {
    rbMat: plate(routeBoxTexture(line)), mirMat: plate(mirrorPlateTexture(line)), rearMat: card(rearPlateTexture(line)),
    destMat: card(destinationTexture(dest)), runMat: card(runCardTexture(run)), body: mat,
  };
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
  const u = model.userData, { mats } = u;
  const swap = (m, tex) => { if (!m) return; const old = m.map; m.map = tex; m.needsUpdate = true; old?.dispose(); };
  if (u.line !== line) {
    swap(mats.rbMat, routeBoxTexture(line));
    swap(mats.mirMat, mirrorPlateTexture(line));
    swap(mats.rearMat, rearPlateTexture(line));
  }
  if (u.dest !== dest) swap(mats.destMat, destinationTexture(dest));
  if (u.run !== run) swap(mats.runMat, runCardTexture(run));
  Object.assign(u, { line, dest, run });
}

// Put each car of a set on the track: cars are 15.2 m over couplers, the body starts 0.6 m
// behind the coupler face; the car rests on its two bogie pivots (the model's own spacing), so
// it yaws and pitches with them, wheels on the rail heads. `at(s)` -> [x, y, track bed height].
export function placeConsist(model, sFront, at) {
  const { bogie, bodyFront } = model.userData;
  model.userData.cars.forEach((car, k) => {
    const c = sFront - k * 15.2 - 0.6 - bodyFront; // car origin (midway between the bogies)
    const [ax, ay, za, ra = 0] = at(c + bogie), [bx, by, zb, rb = 0] = at(c - bogie);
    car.position.set((ax + bx) / 2, (za + zb) / 2 + RAIL_TOP, -(ay + by) / 2);
    car.rotation.order = 'YXZ'; // heading, then pitch, then the lean into a canted curve
    car.rotation.y = Math.atan2(ax - bx, -(ay - by));
    car.rotation.x = -Math.atan2(za - zb, 2 * bogie);
    car.rotation.z = -(ra + rb) / 2;
  });
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
// Below it hangs the call signal (výzvové návěstidlo): three LED bars \ | / — the bar for the
// direction about to get GO lights orange once the tram's request is registered and blinks
// just before GO. A distant signal (předvěst) has a yellow "P" plate instead.
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
  callTex[dir] = canvasTexture(128, 128, (c, w, h) => {
    c.fillStyle = '#0a0a0a';
    c.fillRect(0, 0, w, h);
    const bars = { left: [[28, 30], [58, 98]], straight: [[64, 26], [64, 102]], right: [[100, 30], [70, 98]] };
    for (const [k, [[x0, y0], [x1, y1]]] of Object.entries(bars)) {
      // LED dots along the bar
      const n = 9;
      for (let i = 0; i < n; i++) {
        const x = x0 + ((x1 - x0) * i) / (n - 1), y = y0 + ((y1 - y0) * i) / (n - 1);
        for (const off of [-4, 4]) {
          c.fillStyle = k === dir ? '#ffa21a' : '#1d2a1d';
          c.beginPath();
          c.arc(x + off, y, 3.2, 0, Math.PI * 2);
          c.fill();
        }
      }
    }
  });
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
  if (!backplateTex) backplateTex = canvasTexture(128, 128, (c, w, h) => {
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
    if (!pPlateTex) pPlateTex = canvasTexture(96, 128, (c, w, h) => {
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
// the span wire above the track, a matrix of red LEDs forming a chevron: < left, > right,
// ^ straight. The symbol blinks while the switch is locked.
const arrowTextures = {};
function arrowTexture(dir) {
  if (arrowTextures[dir]) return arrowTextures[dir];
  arrowTextures[dir] = canvasTexture(160, 128, (g, w, h) => {
    g.fillStyle = '#0b0b0b';
    g.fillRect(0, 0, w, h);
    // chevron as two thick strokes meeting at a tip
    const tip = dir === 'left' ? [44, 64] : dir === 'right' ? [116, 64] : [80, 26];
    const ends = dir === 'left' ? [[96, 22], [96, 106]] : dir === 'right' ? [[64, 22], [64, 106]] : [[40, 88], [120, 88]];
    const dist = (px, py, [ax, ay], [bx, by]) => {
      const vx = bx - ax, vy = by - ay, t = Math.max(0, Math.min(1, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)));
      return Math.hypot(px - ax - vx * t, py - ay - vy * t);
    };
    for (let y = 5; y < h; y += 7) for (let x = 5; x < w; x += 7) {
      const lit = dir !== 'off' && (dist(x, y, tip, ends[0]) < 9 || dist(x, y, tip, ends[1]) < 9);
      g.fillStyle = lit ? '#ff2a12' : '#1a0b09';
      g.beginPath(); g.arc(x, y, 2.6, 0, Math.PI * 2); g.fill();
    }
  });
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
const cached = (key, make) => { if (!signTex.has(key)) signTex.set(key, make()); return signTex.get(key); };

// Tram speed sign (rychlostník): black number on a white board with a black border.
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

// Dangerous gradient: grey board, white field showing the slope with the red percentage.
export function makeGradientSign(pct) {
  const tex = cached(`grad${pct}`, () => canvasTexture(144, 160, (g, w, h) => {
    g.fillStyle = '#8b8d8f'; g.fillRect(0, 0, w, h);
    g.fillStyle = '#fff'; g.fillRect(12, 12, w - 24, h - 24);
    g.fillStyle = '#111';
    g.beginPath(); g.moveTo(20, 60); g.lineTo(w - 20, 120); g.lineTo(20, 120); g.closePath(); g.fill();
    g.fillStyle = '#d0141b';
    g.font = 'bold 40px Arial, sans-serif'; g.textAlign = 'center';
    g.fillText(`${pct} %`, w / 2 + 14, 50);
  }));
  return signOnPole(tex, 0.45, 0.5, 2.8);
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
  if (!stopTopTex) stopTopTex = canvasTexture(160, 160, (c, w, h) => {
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
  if (!timetableTex) timetableTex = canvasTexture(128, 160, (c, w, h) => {
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
  if (!baseTex) baseTex = canvasTexture(128, 128, (c, w, h) => {
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
