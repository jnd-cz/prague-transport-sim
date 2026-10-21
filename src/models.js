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

function routeBoxTexture(line) {
  // DPP route number: white digits on a blue field with a thin white edge
  return canvasTexture(192, 96, (g, w, h) => {
    g.fillStyle = '#f2f2f2';
    g.fillRect(0, 0, w, h);
    g.fillStyle = '#1f4f9e';
    g.fillRect(6, 6, w - 12, h - 12);
    g.fillStyle = '#ffffff';
    g.font = 'bold 72px "Arial Narrow", Arial, sans-serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText(String(line), w / 2, h / 2 + 4);
  });
}

// Tatra T3 in the Prague livery: red lower body, cream window band and upper body, dark grey
// roof, cream folding doors, blue route number box in the front dome and the orange diamond
// pantograph. Origin = centre of the body at rail level, facing +Z (local). 14 m x 2.5 m.
export function makeT3({ line = '22' } = {}) {
  const g = new THREE.Group();
  g.userData.line = line;
  const red = lambert(0xb81a1f), cream = lambert(0xefe4c4), glass = lambert(0x1c262d), dark = lambert(0x2a2a2a);
  const roof = lambert(0x5d6164), chrome = lambert(0xb9bcbf), orange = lambert(0xd8541c);
  g.add(band(0.40, 0.52, 0.04, dark));          // underframe skirt
  g.add(band(0.52, 0.58, -0.005, chrome));      // bumper / rubbing strip
  g.add(band(0.58, 1.30, 0, red));              // lower body
  g.add(band(1.30, 1.42, -0.008, cream));       // window sill
  g.add(band(1.42, 2.34, 0.03, glass));         // window band (recessed glass)
  g.add(band(2.34, 2.80, 0, cream));            // upper body
  g.add(band(2.80, 2.93, 0.10, roof));          // roof edge
  g.add(band(2.93, 3.04, 0.32, roof));          // roof crown
  const box = (w, h, d, mat, x, y, z) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    g.add(m);
    return m;
  };
  // cream window pillars along the sides
  for (let z = -5.4; z <= 5.5; z += 1.36) for (const x of [-1.235, 1.235]) box(0.04, 0.93, 0.13, cream, x, 1.88, z);
  // windscreen corner pillars at both ends
  for (const sz of [1, -1]) for (const sx of [1, -1]) box(0.09, 0.93, 0.09, cream, sx * 0.84, 1.88, sz * 6.5);
  // headlights (front) / tail lights (rear) in the red apron
  for (const sz of [1, -1]) for (const x of [-0.72, 0.72]) {
    const l = new THREE.Mesh(new THREE.CircleGeometry(0.1, 14), new THREE.MeshBasicMaterial({ color: sz > 0 ? 0xfff3c0 : 0x9a1010 }));
    const zz = sz * 6.93 - sz * (Math.abs(x) / 1.25) ** 2 * 0.85;
    l.position.set(x, 0.92, zz + sz * 0.02);
    l.rotation.y = sz > 0 ? Math.atan2(x * 0.9, 1) : Math.PI + Math.atan2(-x * 0.9, 1);
    g.add(l);
  }
  // route number box in the front dome, and a smaller one by the front door
  const rbTex = routeBoxTexture(line);
  const rb = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.31), new THREE.MeshBasicMaterial({ map: rbTex }));
  rb.position.set(0, 2.58, 7.0);
  g.add(rb);
  const rbSide = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.3), new THREE.MeshBasicMaterial({ map: rbTex }));
  rbSide.position.set(-1.27, 1.95, 5.65);
  rbSide.rotation.y = -Math.PI / 2;
  g.add(rbSide);
  // three folding doors on the right side (-X when facing +Z): cream frames, tall glazing
  for (const z of [4.85, -0.25, -5.0]) {
    box(0.03, 2.0, 1.25, cream, -1.262, 1.42, z);
    for (const dz of [-0.45, -0.15, 0.15, 0.45]) box(0.035, 1.25, 0.22, glass, -1.266, 1.62, z + dz);
  }
  // bogies with wheels
  for (const z of [-3.6, 3.6]) {
    box(2.05, 0.38, 2.4, dark, 0, 0.34, z);
    for (const dz of [-0.95, 0.95]) for (const x of [-0.78, 0.78]) {
      const w = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.12, 12), lambert(0x161616));
      w.rotation.z = Math.PI / 2;
      w.position.set(x, 0.33, z + dz);
      g.add(w);
    }
  }
  // roof: resistor box and the orange diamond pantograph
  box(1.3, 0.26, 2.6, lambert(0x48494a), 0, 3.17, -2.4);
  box(1.1, 0.12, 1.4, dark, 0, 3.1, 1.6); // pantograph base frame
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
  pan.position.z = 1.6;
  g.add(pan);
  return g;
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
