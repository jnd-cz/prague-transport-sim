// SPDX-License-Identifier: AGPL-3.0-or-later
// Models from IPR catalogue UK.2, UK.4, UK.5 and US.4 and the corresponding lab CAD references.
import * as T from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const steel = new T.MeshStandardMaterial({ name: 'black-grey metal', vertexColors: true, metalness: .2, roughness: .75 });
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

function strip(outline, low, high, inward = false, close = true) {
  const positions = [], normals = [], uv = [], indices = [];
  let u = 0;
  const count = outline.length + Number(close);
  for (let i = 0; i < count; i++) {
    const p = outline[i % outline.length], q = outline[i - 1];
    if (q) u += Math.hypot(p.x - q.x, p.z - q.z);
    for (const y of [low, typeof high === 'function' ? high(p.z) : high]) {
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

function roofBack(crown, rimY, underside, centre) {
  const half = crown.length / 2;
  const rear = crown.slice(half).concat(crown.slice(0, half)).filter(p => p.z <= centre + 1e-6);
  // The rear skin wraps both corners. The front remains open for access.
  return [strip(rear, rimY, underside, false, false), strip(rear, rimY, underside, true, false)];
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

function cheek(x, z, bottom, underside, steps) {
  // Side elevation of the cast canopy support. The opening is on the high side.
  const t = new T.Shape();
  t.moveTo(z - .055, bottom);
  t.lineTo(z - .055, underside(z - .055));
  t.lineTo(z + .048, underside(z + .048));
  t.quadraticCurveTo(z - .042, bottom + .058, z + .012, bottom + .018);
  t.quadraticCurveTo(z + .027, bottom + .006, z + .062, bottom);
  t.closePath();
  const g = new T.ExtrudeGeometry(t, { depth: .014, bevelEnabled: false, curveSegments: steps });
  g.rotateY(-Math.PI / 2).translate(x + .007, 0, 0);
  const indexed = mergeVertices(g);
  g.dispose();
  return indexed;
}

const BINS = {
  'bin-large': { length: .675, depth: .375, rimY: .803, high: 1.015, base: .060 },
  'bin-recycling': { length: 1.015, depth: .375, rimY: .809, high: 1.020, base: .060 },
  'bin-small-canopied': { length: .375, depth: .375, rimY: 1.003, high: 1.186, base: .231 },
};

export function makeBin(kind, level) {
  const { length, depth, rimY, high, base } = BINS[kind];
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
    ...roofBack(outline(.009), rimY - .007, underside, z),
  ];
  if (small) {
    const post = -.193;
    frame.push(new T.CylinderGeometry(.03175, .03175, 1.091, 2 * ends).translate(0, .4635, post));
    frame.push(new T.BoxGeometry(.15, .018, .135).translate(0, -.091, post));
    frame.push(new T.BoxGeometry(.048, .69, .069).translate(0, .616, -.158));
    frame.push(cheek(0, z - .119, rimY - .008, underside, ends));
  } else {
    frame.push(slab(outline(.023), 0, base));
    for (const x of [-1, 1]) {
      frame.push(cheek(x * (length / 2 - .095), -.064, rimY - .008, underside, ends));
    }
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
  model.add(
    mesh(steel, [...tint(frame, coating), ...tint(inside, liner)]),
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

export function makeCycleStand(level) {
  const { bend, section } = DETAIL[level];
  const positions = [], normals = [], uv = [], indices = [];
  const path = standPath(bend), half = .0195, depth = .0315;
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
  const frame = [geometry(positions, normals, uv, indices)];
  if (level === 'near') for (const x of [-.2755, .2755]) {
    const plate = slab(capsule(.15, .065, 4), -.098, .018);
    frame.push(plate.rotateY(Math.PI / 2).translate(x, 0, 0));
  }
  const model = new T.Group();
  model.add(mesh(steel, tint(frame, coating)));
  return model;
}
