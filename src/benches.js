// SPDX-License-Identifier: AGPL-3.0-or-later
// Prague four-legged benches UL.1–UL.3 (#252). The outline and the slat centres were measured
// from the lab's bench-4-back, bench-4-arms and bench-4-flat GLBs. See ASSETS.md for the IPR credit.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const metal = new THREE.MeshStandardMaterial({ name: 'metal', color: 0x353b3c, metalness: .2, roughness: .75 });
const wood = new THREE.MeshStandardMaterial({ name: 'wood', color: 0x4f3a2d, roughness: .86 });

// End frame and its opening in [depth, height] mm. The first 22 mm of the backed frame
// below grade in the source are cropped at the pavement. Retain the opening at every distance.
const BACKED = [
  [[-328, 839], [-325, 856], [-310, 863], [-281, 730], [-220, 590], [-178, 455], [-144, 395],
    [-107, 365], [-51, 349], [-18, 349], [61, 359], [227, 392], [277, 393], [318, 386], [312, 370],
    [279, 349], [265, 308], [262, 0], [230, 0], [230, 34], [223, 42], [88, 45], [-234, 42],
    [-245, 33], [-250, 0], [-279, 0], [-269, 112], [-221, 365], [-219, 395], [-228, 499],
    [-237, 549], [-303, 724]],
  [[-238, 71], [-221, 66], [225, 67], [231, 80], [233, 279], [229, 313], [220, 337], [203, 352],
    [169, 358], [19, 326], [-35, 325], [-122, 332], [-168, 319], [-192, 298], [-209, 263], [-231, 151]],
];
const BACKED_SIMPLE = [
  [[-328, 839], [-310, 863], [-281, 730], [-178, 455], [-144, 395], [-107, 365], [-18, 349],
    [227, 392], [318, 386], [279, 349], [265, 308], [262, 0], [230, 0], [223, 42], [-234, 42],
    [-250, 0], [-279, 0], [-219, 395], [-237, 549], [-303, 724]],
  [[-238, 71], [225, 67], [233, 279], [220, 337], [169, 358], [19, 326], [-122, 332], [-168, 319], [-209, 263]],
];
const FLAT = [
  [[-257, 413], [-230, 420], [-184, 423], [-11, 415], [184, 423], [225, 421], [256, 414], [254, 399],
    [235, 387], [224, 372], [213, 329], [212, 0], [180, 0], [180, 52], [172, 64], [-6, 67],
    [-173, 64], [-180, 53], [-180, 0], [-212, 0], [-213, 324], [-221, 366], [-233, 385], [-253, 398]],
  [[24, 383], [-140, 387], [-156, 382], [-173, 361], [-181, 327], [-179, 95], [-167, 87],
    [150, 87], [176, 92], [181, 101], [181, 326], [177, 349], [165, 374], [152, 384], [136, 389]],
];
const FLAT_SIMPLE = [
  [[-257, 413], [-184, 423], [256, 414], [224, 372], [213, 329], [212, 0], [180, 0], [172, 64],
    [-6, 67], [-173, 64], [-180, 0], [-212, 0], [-213, 324], [-221, 366]],
  [[136, 389], [-140, 387], [-173, 361], [-179, 95], [176, 92], [181, 326], [165, 374]],
];
const ARM = [[-233, 619], [-211, 585], [-152, 606], [270, 640], [262, 423], [246, 400],
  [277, 393], [191, 387], [225, 398], [233, 527], [224, 580], [200, 602], [-156, 581], [-204, 564], [-204, 538]];
const ARM_SIMPLE = [[-224, 606], [270, 640], [260, 400], [225, 398], [233, 527],
  [224, 580], [200, 602], [-156, 581], [-210, 558]];
const BACKED_RIB = [[-315, 863], [-274, 707], [-226, 601], [-165, 422], [-135, 384], [-94, 360],
  [-41, 349], [12, 349], [212, 390], [272, 391], [317, 385], [316, 380], [214, 385], [8, 344],
  [-42, 344], [-85, 350], [-130, 373], [-170, 420], [-196, 485], [-223, 575], [-267, 673]];
const FLAT_RIB = [[-256, 411], [-191, 423], [-3, 415], [191, 423], [256, 412], [254, 407],
  [191, 417], [-4, 409], [-190, 417], [-254, 407]];

// Start at the top of the back and follow the curved seat to the front edge.
const BACKED_SLATS = [[-293, 851], [-284, 800], [-271, 750], [-254, 700], [-233, 653], [-212, 607],
  [-196, 561], [-181, 512], [-165, 463], [-140, 415], [-98, 378], [-44, 364], [8, 366], [60, 374],
  [110, 384], [160, 395], [209, 404], [258, 407], [306, 403]];
const FLAT_SLATS = [[-251, 430], [-203, 437], [-153, 437], [-103, 435], [-52, 432], [0, 430],
  [52, 432], [103, 435], [153, 437], [203, 437], [251, 430]];

const vectors = (profile) => profile.map(([z, y]) => new THREE.Vector2(z / 1000, y / 1000));

function sideFrame(profile, x, thickness, opening) {
  const shape = new THREE.Shape(vectors(profile));
  if (opening) shape.holes.push(new THREE.Path(vectors(opening)));
  return new THREE.ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false })
    .rotateY(-Math.PI / 2).translate(x + thickness / 2, 0, 0);
}

function brace(side, flat) {
  const low = flat ? .080 : .058, high = flat ? .412 : .347;
  const outer = .815 * side, inner = (flat ? .24 : .31) * side;
  return new THREE.BoxGeometry(Math.hypot(inner - outer, high - low), .015, .015).toNonIndexed()
    .rotateZ(Math.atan2(high - low, inner - outer))
    .translate((outer + inner) / 2, (low + high) / 2, flat ? 0 : .01);
}

function slats(points, far) {
  const parts = [];
  for (let i = 0; i < points.length; i++) {
    const j = far ? Math.min(i + 1, points.length - 1) : i;
    const [z0, y0] = points[i], [z1, y1] = points[j];
    const [az, ay] = points[Math.max(0, i - 1)], [bz, by] = points[Math.min(points.length - 1, j + 1)];
    const angle = Math.atan2(ay - by, bz - az);
    const width = (40 + Math.hypot(z1 - z0, y1 - y0)) / 1000;
    parts.push(new THREE.BoxGeometry(1.8, .030, width).toNonIndexed().rotateX(angle)
      .translate(0, (y0 + y1) / 2000, (z0 + z1) / 2000));
    i = j;
  }
  return parts;
}

function mergeParts(parts, material) {
  const mesh = new THREE.Mesh(mergeGeometries(parts), material);
  for (const part of parts) part.dispose();
  mesh.castShadow = mesh.receiveShadow = true;
  return mesh;
}

// Y = 0 at grade, length along X, sitter faces +Z. Each material is one mesh so the feature
// layer can build one instanced mesh per material, variant and distance band.
export function makeIprBench(variant = 'backrest', level = 'near') {
  if (!['backrest', 'armrests', 'backless'].includes(variant)) throw new RangeError(`Unknown bench variant: ${variant}`);
  if (!['near', 'middle', 'far'].includes(level)) throw new RangeError(`Unknown bench detail: ${level}`);
  const flat = variant === 'backless', near = level === 'near', far = level === 'far';
  const [frame, opening] = flat ? (near ? FLAT : FLAT_SIMPLE) : (near ? BACKED : BACKED_SIMPLE);
  const frameParts = [];
  for (const side of [-1, 1]) {
    frameParts.push(sideFrame(frame, .815 * side, .052, opening), brace(side, flat));
    if (variant === 'armrests') frameParts.push(sideFrame(near ? ARM : ARM_SIMPLE, .830 * side, .050));
  }
  if (!far) frameParts.push(sideFrame(flat ? FLAT_RIB : BACKED_RIB, 0, .040));
  const bench = new THREE.Group();
  bench.add(mergeParts(frameParts, metal), mergeParts(slats(flat ? FLAT_SLATS : BACKED_SLATS, far), wood));
  return bench;
}
