// SPDX-License-Identifier: AGPL-3.0-or-later
// Models from IPR catalogue UK.2, UK.4, UK.5, US.4 and Z.1–Z.14.
import * as T from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const steel = new T.MeshStandardMaterial({ name: 'black-grey metal', vertexColors: true, metalness: .2, roughness: .75 });
const binSteel = steel.clone();
binSteel.name = 'black-grey bin metal';
binSteel.side = T.DoubleSide;
const coating = new T.Color(0x35383a), liner = new T.Color(0x222526);
const DETAIL = {
  near: { ends: 10, bend: 9, section: 10 },
  middle: { ends: 8, bend: 6, section: 8 },
  far: { ends: 6, bend: 4, section: 6 },
};
let cladding;

function expandedMetal() {
  if (cladding) return cladding;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#464a4b';
  ctx.fillRect(0, 0, 64, 64);
  ctx.fillStyle = '#26292a';
  for (const y of [0, 16, 32, 48, 64]) {
    const shift = y % 32 ? 8 : 0;
    for (let x = shift; x <= 64; x += 16) {
      ctx.beginPath();
      ctx.moveTo(x - 5, y);
      ctx.lineTo(x, y - 3);
      ctx.lineTo(x + 5, y);
      ctx.lineTo(x, y + 3);
      ctx.fill();
    }
  }
  const map = new T.CanvasTexture(canvas);
  map.colorSpace = T.SRGBColorSpace;
  map.wrapS = map.wrapT = T.RepeatWrapping;
  cladding = new T.MeshStandardMaterial({ name: 'expanded metal', map, metalness: .15, roughness: .83 });
  return cladding;
}

function capsule(length, depth, steps, z = 0) {
  const radius = depth / 2, offset = (length - depth) / 2, loop = [];
  for (const side of [1, -1]) {
    const start = side === 1 ? -Math.PI / 2 : Math.PI / 2;
    // For the circular shell the semicircles meet at one vertex.
    for (let i = 0; i <= (offset ? steps : steps - 1); i++) {
      const a = start + i * Math.PI / steps;
      const x = Math.cos(a), n = Math.sin(a);
      loop.push({ x: side * offset + radius * x, z: z + radius * n, nx: x, nz: n });
    }
  }
  return loop;
}

function slab(outline, bottom, height, slope = 0, centre = 0) {
  const shape = new T.Shape(outline.map(p => new T.Vector2(p.x, -p.z)));
  const g = new T.ExtrudeGeometry(shape, { depth: height, bevelEnabled: false });
  g.rotateX(-Math.PI / 2).translate(0, bottom, 0);
  if (slope) {
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i++) p.setY(i, p.getY(i) + slope * (p.getZ(i) - centre));
    // The cap should light as one inclined sheet, with hard normals around the edge.
    g.computeVertexNormals();
  }
  const indexed = mergeVertices(g);
  g.dispose();
  return indexed;
}

function strip(outline, low, high, inward = false) {
  const positions = [], normals = [], uv = [], indices = [];
  let u = 0;
  for (let i = 0; i <= outline.length; i++) {
    const p = outline[i % outline.length], q = outline[i - 1];
    if (q) u += Math.hypot(p.x - q.x, p.z - q.z);
    for (const y of [low, high]) {
      positions.push(p.x, y, p.z);
      normals.push(inward ? -p.nx : p.nx, 0, inward ? -p.nz : p.nz);
      uv.push(u / .144, y / .144);
    }
    if (!i) continue;
    const n = 2 * i;
    if (inward) indices.push(n - 2, n, n - 1, n - 1, n, n + 1);
    else indices.push(n - 2, n - 1, n, n - 1, n + 1, n);
  }
  return geometry(positions, normals, uv, indices);
}

function recyclingInlets(outer, y, segments) {
  const cutouts = [-.318, 0, .318].map(x =>
    capsule(.229, .229, segments / 2).map(p => ({ ...p, x: p.x + x })));
  const path = loop => loop.map(p => new T.Vector2(p.x, -p.z));
  const shape = new T.Shape(path(outer));
  shape.holes = cutouts.map(loop => new T.Path(path(loop)));
  return {
    top: new T.ShapeGeometry(shape).rotateX(-Math.PI / 2).translate(0, y, 0),
    shafts: cutouts.map(loop => strip(loop, y - .115, y, true)),
  };
}

function binNeck(outline, bottom, underside, centre, bands) {
  const half = outline.length / 2;
  const rear = outline.slice(half).concat(outline.slice(0, half)).filter(p => p.z <= centre + 1e-6);
  const positions = [], uv = [], indices = [], width = rear.length;
  // One sheet flares to the rim and to the sloped cover perimeter. Its open ends curve
  // back in side view to leave a rounded mouth.
  for (let band = 0; band <= bands; band++) {
    const t = band / bands, waist = Math.sin(Math.PI * t);
    for (const [i, p] of rear.entries()) {
      positions.push(
        p.x - p.nx * .033 * waist,
        T.MathUtils.lerp(bottom, underside(p.z), t),
        p.z - (1 + p.nz) * .052 * waist,
      );
      uv.push(i / (width - 1), t);
      if (!band || !i) continue;
      const upper = band * width + i, lower = upper - width;
      indices.push(lower - 1, upper - 1, lower, upper - 1, upper, lower);
    }
  }
  const neck = new T.BufferGeometry();
  neck.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  neck.setAttribute('uv', new T.Float32BufferAttribute(uv, 2));
  neck.setIndex(indices);
  neck.computeVertexNormals();
  return neck;
}

function rim(outer, inner, height) {
  const positions = [], normals = [], uv = [], indices = [];
  for (const [i, p] of outer.entries()) {
    for (const q of [p, inner[i]]) {
      positions.push(q.x, height, q.z);
      normals.push(0, 1, 0);
      uv.push(q.x, q.z);
    }
    const n = 2 * i, next = 2 * ((i + 1) % outer.length);
    indices.push(n, n + 1, next, n + 1, next + 1, next);
  }
  return geometry(positions, normals, uv, indices);
}

function geometry(positions, normals, uv, indices) {
  const g = new T.BufferGeometry();
  g.setAttribute('position', new T.Float32BufferAttribute(positions, 3));
  g.setAttribute('normal', new T.Float32BufferAttribute(normals, 3));
  g.setAttribute('uv', new T.Float32BufferAttribute(uv, 2));
  g.setIndex(indices);
  return g;
}

function mesh(material, parts) {
  const result = new T.Mesh(mergeGeometries(parts), material);
  result.name = material.name;
  for (const part of parts) part.dispose();
  return result;
}

function tint(parts, color) {
  for (const part of parts) {
    const rgb = new Uint8Array(3 * part.attributes.position.count);
    for (let i = 0; i < rgb.length; i += 3) {
      rgb[i] = Math.round(color.r * 255);
      rgb[i + 1] = Math.round(color.g * 255);
      rgb[i + 2] = Math.round(color.b * 255);
    }
    part.setAttribute('color', new T.BufferAttribute(rgb, 3, true));
  }
  return parts;
}

const BINS = {
  'bin-large': { catalogue: 'UK.2', length: .675, depth: .375, rimY: .803, high: 1.015, base: .060 },
  'bin-recycling': { catalogue: 'UK.4', length: 1.015, depth: .375, rimY: .809, high: 1.020, base: .060 },
  'bin-small-canopied': { catalogue: 'UK.5', length: .375, depth: .375, rimY: 1.003, high: 1.186, base: .231 },
};

export function makeBin(kind, level) {
  const { catalogue, length, depth, rimY, high, base } = BINS[kind];
  const small = kind === 'bin-small-canopied', recycling = kind === 'bin-recycling';
  const { ends } = DETAIL[level], z = small ? .035 : 0;
  const outline = (inset = 0) => capsule(length - 2 * inset, depth - 2 * inset, ends, z);
  const outer = outline(), inner = outline(.018);
  const drop = .104, coverTop = high - drop / 2, slope = drop / depth, skin = .011;
  const underside = depthAt => coverTop - skin + (depthAt - z) * slope;
  const frame = [
    slab(outer, base, .016),
    slab(outer, coverTop - skin, skin, slope, z),
    strip(outer, rimY - .018, rimY),
    binNeck(outer, rimY, underside, z, level === 'near' ? 7 : ends / 2),
  ];
  if (small) {
    const post = -.193;
    frame.push(new T.CylinderGeometry(.03175, .03175, 1.091, 2 * ends).translate(0, .4635, post));
    frame.push(new T.BoxGeometry(.15, .018, .135).translate(0, -.091, post));
    frame.push(new T.BoxGeometry(.048, .69, .055).translate(0, .616, -.173));
  } else {
    frame.push(slab(outline(.023), 0, base));
  }
  const inside = [slab(inner, rimY - .118, .005)];
  if (recycling) {
    const { top, shafts } = recyclingInlets(outer, rimY, ends + 2);
    frame.push(top);
    inside.push(...shafts);
  } else {
    frame.push(rim(outer, inner, rimY));
    inside.push(strip(inner, rimY - .115, rimY, true));
  }
  if (level === 'near' && !small) {
    frame.push(new T.BoxGeometry(.018, .065, .006).translate(recycling ? -.154 : 0, .55, depth / 2 + .001));
  }
  const model = new T.Group();
  model.userData.catalogue = catalogue;
  model.add(
    mesh(binSteel, [...tint(frame, coating), ...tint(inside, liner)]),
    mesh(expandedMetal(), [strip(outer, base + .014, rimY - .016)]),
  );
  return model;
}

function standPath(bend) {
  const leg = .2755, top = .892, radius = .137;
  const path = [[-leg, -.08, -1, 0]];
  for (const [centre, start] of [[-leg + radius, Math.PI], [leg - radius, Math.PI / 2]]) {
    for (let i = 0; i <= bend; i++) {
      const a = start - i * Math.PI / (2 * bend), nx = Math.cos(a), ny = Math.sin(a);
      path.push([centre + radius * nx, top - radius + radius * ny, nx, ny]);
    }
  }
  path.push([leg, -.08, 1, 0]);
  return path;
}

function sweep(path, half, depth, section) {
  const positions = [], normals = [], uv = [], indices = [];
  for (const [i, [x, y, nx, ny]] of path.entries()) {
    for (let j = 0; j < section; j++) {
      const angle = 2 * Math.PI * j / section, a = Math.cos(angle), b = Math.sin(angle);
      positions.push(x + nx * a * half, y + ny * a * half, b * depth);
      const n = Math.hypot(a / half, b / depth);
      normals.push(nx * a / (half * n), ny * a / (half * n), b / (depth * n));
      uv.push(i / path.length, j / section);
      if (!i) continue;
      const u = (i - 1) * section + j, v = (i - 1) * section + (j + 1) % section;
      indices.push(u, v, u + section, v, v + section, u + section);
    }
  }
  return geometry(positions, normals, uv, indices);
}

export function makeCycleStand(level) {
  const { bend, section } = DETAIL[level];
  const frame = [sweep(standPath(bend), .0195, .0315, section)];
  if (level === 'near') for (const x of [-.2755, .2755]) {
    const plate = slab(capsule(.15, .065, 4), -.098, .018);
    frame.push(plate.rotateY(Math.PI / 2).translate(x, 0, 0));
  }
  const model = new T.Group();
  model.add(mesh(steel, tint(frame, coating)));
  return model;
}

// The type 1 span is the outside frame width. The type 2 dimension is post-centre spacing.
export const RAILINGS = {
  'railing-bars-short': [1, 1, 'bars'],
  'railing-glass-short': [2, 1, 'glass'],
  'railing-glass-rounded-short': [3, 1, 'glass-rounded'],
  'railing-three-bars-short': [4, 1, 'three-bars'],
  'railing-bars': [5, 2, 'bars'],
  'railing-glass': [6, 2, 'glass'],
  'railing-glass-rounded': [7, 2, 'glass-rounded'],
  'railing-three-bars': [8, 2, 'three-bars'],
  'railing-tubular-three-bars-short': [9, 1, 'three-bars'],
  'railing-tubular-bars-short': [10, 1, 'bars'],
  'railing-tubular-glass-short': [11, 1, 'glass'],
  'railing-tubular-three-bars': [12, 2, 'three-bars'],
  'railing-tubular-bars': [13, 2, 'bars'],
  'railing-tubular-glass': [14, 2, 'glass'],
};

const RAIL_DETAIL = {
  near: { sides: 12, bend: 6 },
  middle: { sides: 8, bend: 4 },
  far: { sides: 4, bend: 3 },
};
const glassSurface = { side: T.DoubleSide, transparent: true, depthWrite: false, forceSinglePass: true };
const clearPane = new T.MeshBasicMaterial({ ...glassSurface, name: 'clear railing glass', color: 0xb6cbcb, opacity: .22 });
const printPanes = new Map();

function printedPane(width, height, bottom, fullPrint) {
  const key = width + ':' + fullPrint;
  if (printPanes.has(key)) return printPanes.get(key);
  const scale = fullPrint ? 512 : 128;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(172,195,193,.22)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const dot = (x, y, radius) => {
    ctx.beginPath();
    ctx.arc(x * scale, (bottom + height - y) * scale, radius * scale, 0, Math.PI * 2);
    ctx.fill();
  };
  if (fullPrint) {
    ctx.fillStyle = 'rgba(72,78,78,.58)';
    for (let row = 0, y = bottom + .03; y < bottom + height; row++, y += .042) {
      for (let x = .036 + (row % 2) * .03125; x < width; x += .0625) dot(x, y, .006);
    }
  }
  // Z.S.1 and Z.S.2 use a single row at 916 mm above the paving.
  ctx.fillStyle = 'rgba(47,52,54,.88)';
  const n = Math.floor(width / .125);
  for (let i = 0; i < n; i++) dot(width / 2 + (i - (n - 1) / 2) * .125, .916, .025);
  const map = new T.CanvasTexture(canvas);
  map.colorSpace = T.SRGBColorSpace;
  const material = new T.MeshBasicMaterial({
    ...glassSurface, name: fullPrint ? 'printed railing glass' : 'railing glass marker row', map,
  });
  printPanes.set(key, material);
  return material;
}

function glassPanel(width, height, bottom, rounded, material, bend) {
  let g = new T.PlaneGeometry(width, height);
  if (rounded) {
    g.dispose();
    const x = width / 2, y = height / 2, r = .010;
    const shape = new T.Shape();
    shape.moveTo(-x + r, -y);
    shape.lineTo(x - r, -y);
    shape.quadraticCurveTo(x, -y, x, -y + r);
    shape.lineTo(x, y - r);
    shape.quadraticCurveTo(x, y, x - r, y);
    shape.lineTo(-x + r, y);
    shape.quadraticCurveTo(-x, y, -x, y - r);
    shape.lineTo(-x, -y + r);
    shape.quadraticCurveTo(-x, -y, -x + r, -y);
    g = new T.ShapeGeometry(shape, Math.max(1, Math.floor(bend / 2)));
    const p = g.attributes.position, uv = g.attributes.uv;
    for (let i = 0; i < p.count; i++) uv.setXY(i, p.getX(i) / width + .5, p.getY(i) / height + .5);
  }
  return new T.Mesh(g.translate(0, bottom + height / 2, 0), material);
}

function tubeX(radius, from, to, y, sides, cap = false) {
  return new T.CylinderGeometry(radius, radius, to - from, sides, 1, !cap, Math.PI / 2)
    .rotateZ(Math.PI / 2).translate((from + to) / 2, y, 0);
}

function tubeEnd(x, y, height, depth, sides) {
  return new T.CircleGeometry(1, sides).scale(depth, height, 1)
    .rotateY(Math.PI / 2).translate(x, y, 0);
}

function straightRailing(span, fill, level, sides, bend) {
  const glass = fill.startsWith('glass'), height = 1.1, bottom = -.15;
  const near = level === 'near', far = level === 'far';
  const post = span / 2 - .0165, topRail = height - .02415, lowRail = .2;
  const paneBottom = .238, paneHeight = .803;
  const frame = [tubeX(.02415, -post, post, topRail, sides), tubeX(.02415, -post, post, lowRail, sides)];
  if (fill === 'three-bars') frame.push(tubeX(.02415, -post, post, (topRail + lowRail) / 2, sides));
  for (const x of [-post, post]) {
    const upright = far
      ? new T.BoxGeometry(.033, height - bottom, .05).translate(0, (height + bottom) / 2, 0)
      : slab(capsule(.05, .033, near ? 4 : 2), bottom, height - bottom).rotateY(Math.PI / 2);
    frame.push(upright.translate(x, 0, 0));
    if (near) frame.push(new T.BoxGeometry(.110, .012, .154).translate(x, bottom + .006, 0));
  }
  if (glass && near) {
    for (const x of span === 1 ? [-.30, .30] : [-.80, 0, .80]) {
      for (const y of [paneBottom - .006, paneBottom + paneHeight + .006]) {
        frame.push(new T.BoxGeometry(.035, .025, .020).translate(x, y, 0));
      }
    }
  }
  const group = new T.Group();
  group.add(mesh(steel, tint(frame, coating)));
  if (glass) {
    const w = span - .096;
    group.add(glassPanel(w, paneHeight, paneBottom, fill === 'glass-rounded' && !far,
      printedPane(w, paneHeight, paneBottom, near), bend));
  }
  return group;
}

function bentRailing(span, fill, level, sides, bend) {
  const post = span / 2, base = -.2, long = span === 2;
  const near = level === 'near', far = level === 'far';
  const height = long ? 1.130 : 1.124, radius = long ? .030 : .025;
  const top = height - radius, low = .2, stub = long ? .104 : .080, elbow = long ? .078 : .063;
  const path = [[-post, base, -1, 0]];
  for (let i = 0; i <= bend; i++) {
    const a = Math.PI - i * Math.PI / (2 * bend), nx = Math.cos(a), ny = Math.sin(a);
    path.push([-post + elbow * (1 + nx), top - elbow * (1 - ny), nx, ny]);
  }
  const end = post + stub;
  path.push([far ? end : end - .02, top, 0, 1]);
  const frame = [
    sweep(path, radius, .025, sides),
    far ? tubeEnd(end, top, radius, .025, sides)
      : tubeX(radius, end - .021, end, top, sides, true),
    new T.CylinderGeometry(.025, .025, top - base, sides, 1, far, Math.PI / 2).translate(post, (top + base) / 2, 0),
  ];
  for (const y of fill === 'three-bars' ? [low, low + .45] : [low]) {
    frame.push(tubeX(.021, -post, end, y, sides, !far));
    if (far) frame.push(tubeEnd(end, y, .021, .021, sides));
  }
  if (near) for (const x of [-post, post]) {
    const foot = long ? .105 : .075;
    frame.push(new T.CylinderGeometry(foot, foot, .014, sides).translate(x, base + .007, 0));
  }
  const w = long ? 1.788 : .826, h = long ? .809 : .817, y = .232;
  if (fill === 'glass' && near) for (const railY of [(y + low + .021) / 2, (y + h + top - radius) / 2]) {
    frame.push(new T.BoxGeometry(w, .016, .016).translate(0, railY, 0));
  }
  const group = new T.Group();
  group.add(mesh(steel, tint(frame, coating)));
  if (fill === 'glass') group.add(glassPanel(w, h, y, false, clearPane, bend));
  return group;
}

export function makeRailing(kind, level) {
  const [number, span, fill] = RAILINGS[kind];
  const { sides, bend } = RAIL_DETAIL[level];
  const model = number < 9 ? straightRailing(span, fill, level, sides, bend)
    : bentRailing(span, fill, level, sides, bend);
  Object.assign(model.userData, { catalogue: 'Z.' + number, span });
  return model;
}
