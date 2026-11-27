// SPDX-License-Identifier: AGPL-3.0-or-later
// Prague IPR shelters, catalogue pp. 6–9 (#252). See ASSETS.md for the design and source credits.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const HEIGHT = 2.455;
const STANDARD_DEPTH = 1.858;
const POST_BASE = -.18;  // The anchor plate is below the ±0.000 paving datum (IPR catalogue, pp. 10–11).
const GLASS_BOTTOM = .23, GLASS_TOP = 2.245;
const FASCIA_Y = 2.13, FASCIA_HEIGHT = .36, FASCIA_DEPTH = .15;
const STANDARD_POSTS = [-1.83, 1.83], PASSAGE_POSTS = [-1.83, -.61, 1.83];
const LAYOUTS = {
  'P.1': { length: 4.040, supports: STANDARD_POSTS, bays: [[0, 1]], side: 1.08, citylight: true },
  'P.2': { length: 4.040, supports: PASSAGE_POSTS, bays: [[1, 2]], side: 1.08, citylight: true, passage: true },
  'P.3': { length: 4.040, supports: STANDARD_POSTS, bays: [[0, 1]], side: .58 },
  'P.4': { length: 4.040, supports: PASSAGE_POSTS, bays: [[1, 2]], side: .58, passage: true },
  'P.5': { length: 7.080, supports: [-3.35, -.28, .82, 3.35], bays: [[0, 1], [2, 3]], side: 1.08, citylight: true, passage: true },
  'P.6': { length: 7.080, supports: [-3.35, 0, 3.35], bays: [[0, 1], [1, 2]], side: 1.08, citylight: true },
  'P.7': { length: 7.080, supports: [-3.35, 0, 3.35], bays: [[0, 1], [1, 2]], side: .58, citylight: false },
  'P.11': { length: 4.040, supports: STANDARD_POSTS },
  'P.12': { length: 4.040, depth: 1.438, supports: STANDARD_POSTS, bays: [[0, 1]], bench: false },
};

const metal = new THREE.MeshStandardMaterial({ name: 'frame', color: 0x35383a, metalness: .23, roughness: .72 });
const wood = new THREE.MeshStandardMaterial({ name: 'seats', color: 0x584434, roughness: .87 });
const poster = new THREE.MeshBasicMaterial({ name: 'citylight', color: 0xd9d9d2 });
const glassSurface = { transparent: true, depthWrite: false, side: THREE.DoubleSide, forceSinglePass: true };
const glass = new THREE.MeshBasicMaterial({ name: 'glass', color: 0xa2bfc3, opacity: .24, ...glassSurface });
const roofGlass = new THREE.MeshBasicMaterial({ name: 'roof-glass', color: 0x82999d, opacity: .42, ...glassSurface });

let markedGlass;
function markings() {
  if (markedGlass) return markedGlass;
  // One metre horizontally. The window has two denser bands at 0.8–1.0 and 1.4–1.6 m above grade.
  const canvas = document.createElement('canvas');
  canvas.width = 200;
  canvas.height = 400;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(162,191,195,.24)';
  ctx.fillRect(0, 0, 200, 400);
  for (let row = 0; row < 26; row++) {
    const y = row * 15 + 4, height = GLASS_TOP - y / 400 * (GLASS_TOP - GLASS_BOTTOM);
    const band = (height >= .8 && height <= 1) || (height >= 1.4 && height <= 1.6);
    ctx.fillStyle = band ? 'rgba(67,71,75,.66)' : 'rgba(67,71,75,.38)';
    for (let x = row % 2 ? 10 : 0; x <= 200; x += 20) {
      ctx.beginPath();
      ctx.arc(x, y, band ? 4.4 : 2.2, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  map.wrapS = THREE.RepeatWrapping;
  markedGlass = new THREE.MeshBasicMaterial({ name: 'marked-glass', map, ...glassSurface });
  return markedGlass;
}

function box(parts, w, h, d, x, y, z) {
  parts.push(new THREE.BoxGeometry(w, h, d).translate(x, y, z));
}

function batch(parts, material) {
  const mesh = new THREE.Mesh(mergeGeometries(parts), material);
  for (const part of parts) part.dispose();
  mesh.name = material.name;
  mesh.castShadow = material === metal || material === wood;
  mesh.receiveShadow = mesh.castShadow;
  return mesh;
}

function pane(group, name, width, x, z, side, near) {
  const geometry = new THREE.PlaneGeometry(width, GLASS_TOP - GLASS_BOTTOM);
  if (near) {
    const uv = geometry.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setX(i, uv.getX(i) * width);
  }
  // Separate planes keep their own sort centres when seen through another pane.
  const mesh = new THREE.Mesh(geometry, near ? markings() : glass);
  mesh.name = name;
  mesh.position.set(x, (GLASS_TOP + GLASS_BOTTOM) / 2, z);
  if (side) mesh.rotation.y = Math.PI / 2;
  group.add(mesh);
}

function canopy(group, frame, length, wall, back, level) {
  const half = length / 2, front = -wall, radius = .13;
  const outline = new THREE.Shape();
  outline.moveTo(-half, -wall);
  outline.lineTo(half, -wall);
  outline.lineTo(half, -front + radius);
  outline.quadraticCurveTo(half, -front, half - radius, -front);
  outline.lineTo(-half + radius, -front);
  outline.quadraticCurveTo(-half, -front, -half, -front + radius);
  outline.closePath();
  const curves = level === 'near' ? 4 : 1;
  const roof = new THREE.Mesh(new THREE.ShapeGeometry(outline, curves).rotateX(-Math.PI / 2), roofGlass);
  roof.name = 'canopy';
  roof.position.y = HEIGHT;
  group.add(roof);

  box(frame, length - .08, .139, .125, 0, 2.321, back);
  box(frame, length - .23, .042, .05, 0, HEIGHT - .021, front - .044);
  box(frame, length, .033, .048, 0, HEIGHT - .0165, wall + .024);
  const ribs = level === 'near' ? (length > 5 ? 7 : 4) : level === 'middle' ? 3 : 2;
  for (let i = 0; i < ribs; i++) {
    const x = (length - .24) * (i / (ribs - 1) - .5);
    // Same end setback for the 1.710 m and 1.290 m roof consoles.
    box(frame, .048, .069, 2 * front - .148, x, HEIGHT - .048, .014);
  }
}

function addCompactBench(frame, seats, back, level) {
  // The waterfront platform has a shallow seat on two brackets fixed to the lower rail (#252).
  const centre = .36, depth = .26, slats = level === 'far' ? 1 : 3;
  for (let i = 0; i < slats; i++) {
    box(seats, 1.60, .032, depth / slats - (slats > 1 ? .003 : 0), centre, .477,
      back + .063 + (i + .5) * depth / slats);
  }
  for (const x of [centre - .56, centre + .56]) {
    frame.push(new THREE.BoxGeometry(.043, Math.hypot(.218, .185), .042)
      .rotateX(Math.atan2(.185, .218)).translate(x, .343, back + .1325));
  }
}

function freestanding(group, frame, layout, back, level, compactBench) {
  const { supports, bays, side, citylight, bench = true } = layout, near = level === 'near', far = level === 'far';
  const seats = [];
  for (const x of supports) {
    box(frame, .105, 2.32 - POST_BASE, .135, x, (2.32 + POST_BASE) / 2, back);
    if (near) box(frame, .216, .02, .212, x, POST_BASE - .01, back);
  }
  for (const [first, last] of bays) {
    const lo = supports[first] + .055, hi = supports[last] - .055;
    box(frame, hi - lo, .07, .085, (lo + hi) / 2, .233, back);
    const panes = far ? 1 : Math.round((hi - lo) / 1.06);
    const span = (hi - lo) / panes;
    for (let i = 0; i < panes; i++) {
      const x = lo + span * (i + .5);
      pane(group, 'rear-glass', span - .009, x, back + .012, false, near);
      if (near && i) {
        box(frame, .048, .028, .05, x - span / 2, 1.26, back + .012);
      }
    }
    if (!bench) continue;
    const seat = hi - 1.05;
    const slats = near ? 8 : far ? 1 : 4;
    for (let i = 0; i < slats; i++) {
      box(seats, 1.800, .035, .31 / slats - (slats > 1 ? .004 : 0), seat, .485,
        back + .072 + (i + .5) * .31 / slats);
    }
    for (const x of [seat - .64, seat + .64]) {
      box(frame, .049, .043, .36, x, .447, back + .186);
      if (!far) box(frame, .046, .23, .045, x, .335, back + .038);
    }
  }
  if (compactBench) addCompactBench(frame, seats, back, level);
  if (seats.length) group.add(batch(seats, wood));
  if (!side) return;

  for (const x of [supports[0], supports.at(-1)]) {
    if (citylight && x < 0) continue;
    const z = back + side / 2;
    pane(group, 'end-glass', side, x, z, true, near);
    for (const y of [GLASS_BOTTOM, GLASS_TOP]) box(frame, .06, .045, side, x, y, z);
    if (near) box(frame, .036, GLASS_TOP - GLASS_BOTTOM, .028, x, (GLASS_BOTTOM + GLASS_TOP) / 2, back + side);
  }
  if (citylight) {
    const x = supports[0], z = back + 1.35 / 2;
    box(frame, .123, GLASS_TOP - GLASS_BOTTOM + .06, 1.35, x, (GLASS_TOP + GLASS_BOTTOM) / 2, z);
    const faces = [];
    for (const sign of [-1, 1]) box(faces, .002, 1.76, 1.18, x + sign * .062, 1.27, z);
    group.add(batch(faces, poster));
  }
}

function wallMounts(frame, positions, wall, near) {
  for (const x of positions) {
    box(frame, .14, .700, .068, x, 2.105, wall + .034);
    box(frame, .112, .657, .120, x, 2.089, wall + .100);
    if (near) {
      for (const y of [1.84, 2.19]) box(frame, .165, .045, .058, x, y, wall + .036);
    }
  }
}

function namePlate(name, width, x, back, twoSided) {
  const height = FASCIA_HEIGHT - .02;
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width * 512);
  canvas.height = Math.round(height * 512);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#f3f5f0';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const lines = String(name).trim().split(/\s*[\r\n]+\s*/);
  const step = canvas.height / Math.max(2.15, lines.length + .35);
  let font = Math.round(lines.length === 1 ? canvas.height * .55 : step * .88);
  ctx.font = `600 ${font}px sans-serif`;
  const longest = Math.max(1, ...lines.map(line => ctx.measureText(line).width));
  font = Math.max(1, Math.floor(font * Math.min(1, (canvas.width - 48) / longest)));
  ctx.font = `600 ${font}px sans-serif`;
  for (const [i, line] of lines.entries()) {
    ctx.fillText(line, canvas.width / 2, canvas.height / 2 + (i - (lines.length - 1) / 2) * step);
  }
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  const offset = FASCIA_DEPTH / 2 + .002;
  const faces = [new THREE.PlaneGeometry(width, height).translate(x, FASCIA_Y, back + offset)];
  // Rotate the rear face so the street-facing name reads left to right as well.
  if (twoSided) faces.push(new THREE.PlaneGeometry(width, height)
    .rotateY(Math.PI).translate(x, FASCIA_Y, back - offset));
  const mesh = batch(faces, new THREE.MeshBasicMaterial({ map, transparent: true, depthWrite: false }));
  mesh.name = 'stop-name';
  return mesh;
}

function fascia(group, frame, { supports, bays, passage }, back, stopName) {
  // Put panels above the glazed bays to keep each rear passage clear up to the header.
  const spans = passage ? bays : [[0, supports.length - 1]];
  for (const [i, [a, b]] of spans.entries()) {
    const x = (supports[a] + supports[b]) / 2, width = supports[b] - supports[a] - .034;
    box(frame, width, FASCIA_HEIGHT, FASCIA_DEPTH, x, FASCIA_Y, back);
    if (i === 0 && stopName) group.add(namePlate(stopName, Math.min(3.25, width - .14), x, back, Boolean(bays)));
  }
}

// Length is on X, front is +Z and Y = 0 is the finished paving at the shelter midpoint. The back wall plane
// for P.11 is Z = -0.929. A newline in the stop label separates the name and its qualifier.
// Enable compactBench for P.12 placements with a documented seat.
export function makeIprShelter(variant, level = 'near', stopName = '', { compactBench = false } = {}) {
  if (!Object.hasOwn(LAYOUTS, variant)) throw new RangeError(`Unknown shelter variant: ${variant}`);
  if (!['near', 'middle', 'far'].includes(level)) throw new RangeError(`Unknown shelter detail: ${level}`);
  const layout = LAYOUTS[variant], wall = -(layout.depth ?? STANDARD_DEPTH) / 2, back = wall + .14;
  const group = new THREE.Group(), frame = [];
  group.name = variant;
  canopy(group, frame, layout.length, wall, back, level);
  if (layout.bays) freestanding(group, frame, layout, back, level, variant === 'P.12' && compactBench);
  else wallMounts(frame, layout.supports, wall, level === 'near');
  fascia(group, frame, layout, back, stopName);
  group.add(batch(frame, metal));
  return group;
}
