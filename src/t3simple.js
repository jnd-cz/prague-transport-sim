// The built-in Tatra T3 (#427): our own shapes after the T3's general-arrangement drawing (side and plan
// views, dimensioned) and a colour elevation of both sides and both ends, both on drawingdatabase.com
// (`Tatra-T3-1.gif`, `trams_t3_01.png`; measured in #427), with the T3's numbers from src/tram.js.
// The body is one lofted surface: a plan outline per height (straight sides; the ends tapering in plan from
// the doors to rounded corners and a bulged face) stacked along the side view's end profiles (the
// windscreen leaning back under the roof cap's visor), painted from one canvas shared by every car. The
// running gear, pantograph and fittings are one mesh in vertex colours, the lamps another, the car's fleet
// numbers a third: four draw calls a car, and its plates. Two variants: the T3SUCS, and the T3M with the
// resistors' box on the roof and its green dot-matrix displays (src/models.js). One car: origin on the rail plane
// midway between the bogie pivots, facing +Z, the right side (the doors) at -X.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { T3 } from './tram.js';

// --- the drawings' numbers: metres above the rail top and from the car's centre
const HW = 1.25;                                    // half width (2 500 mm)
const BOTTOM = 0.35, EAVE = 2.62, ROOF = 3.02;      // the skirt's lower edge; the roof's shoulder from-to
const SHOULDER = ROOF - EAVE;                       // its radius (the front view)
const PIVOT = T3.bogies / 2;                // 6 400 mm apart, 3 800 mm from each end
const WHEELBASE = 1.9, WHEEL_R = 0.35;              // 1 900 mm; wheels 700 mm
const COUPLER_H = 0.552;                            // 552 mm above the rail
const COUPLER_FACE = T3.length / 2 - T3.couplerOverlap / 2; // where two coupled heads meet (src/tram.js)
// The ends in plan (the plan view): straight sides between SIDE.r and SIDE.f, then tapering to the end's
// corners (CORNER: half width, its z with the nose at 7.0 m); the face bulges FACE m from the corners to
// the nose. Up to SPLIT the taper is the same at every height (the front and rear doors stand on it);
// beyond it, it follows the end's profile to the corner.
const SIDE = { f: 4.51, r: -4.84 }, SPLIT = { f: 6.05, r: -6.10 };
const CORNER = { f: [0.727, 6.81], r: [0.775, -6.79] };
const FACE = 0.19, FILLET = 0.15;
// the nose (on the centreline) by height (the side view): the lower end, the windscreen leaning back from
// 1.65 m, the roof cap's visor over it at 2.56 m, the cap curving down into the roof
const NOSE = {
  f: [[0.35, 6.70], [0.47, 6.79], [0.70, 6.85], [0.80, 6.90], [1.04, 6.95], [1.54, 6.96], [1.65, 7.00], [2.53, 6.56], [2.56, 6.68],
    [2.72, 6.63], [2.83, 6.58], [2.91, 6.56], [2.94, 6.51], [2.98, 6.43], [3.02, 6.15]],
  r: [[0.35, 6.71], [0.47, 6.81], [0.70, 6.86], [0.80, 6.91], [1.04, 6.94], [1.50, 6.98], [1.69, 7.00], [2.53, 6.77], [2.56, 6.82],
    [2.72, 6.79], [2.83, 6.75], [2.94, 6.70], [2.98, 6.65], [3.02, 6.37]],
};
const BODY_FRONT = 7.0;
// the heights of the outlines; a height given twice is a crease (the normals do not blend across it)
const RINGS = [0.35, 0.47, 0.70, 0.80, 1.04, 1.30, 1.54, 1.65, 1.65, 1.69, 2.10, 2.53, 2.53, 2.56, 2.56, 2.62, 2.70, 2.78, 2.85, 2.91, 2.96, 2.99, 3.01, 3.02];
const REF_H = 1.2;                                  // the outline the texture is laid out on

// the sides' windows and doors, z from-to (the colour elevation; the doors on the right side)
const WIN_R = [[-4.48, -3.16], [-2.98, -1.66], [0.13, 1.44], [1.63, 2.95], [3.14, 4.46]];
const WIN_L = [[4.65, 5.95], [3.15, 4.46], [1.63, 2.95], [0.13, 1.44], [-1.37, -0.05], [-2.87, -1.56], [-4.38, -3.08], [-5.87, -4.57]];
const DOORS = [[-6.04, -4.71], [-1.41, -0.10], [4.71, 6.03]];
// the livery's heights: the bumper, the red panel, the window band (glass, transom), the roof's eave and
// gutter; the cream caps reach 3.05 m from the centre on the roof's shoulders and 6.08 m on its top. Round the
// cab the red starts lower, under the cream band with the flap (the front view: 1.47 m on the face, 1.51 m on the
// cab's sides), and steps up to the sill line behind it with a rounded corner: by the front door's edge on the
// right (the red's corner rounded), behind the cab window on the left (the cream's corner rounded); the colour
// elevation, the user, 2026-11-09: "the shape is closer to the 2d picture"
const LIV = { bumper: [0.70, 0.80], red: [0.78, 1.62], redCab: 1.48, glass: [1.71, 2.52], transom: [2.10, 2.135], eave: 2.56, gutter: 2.85, capSide: 3.05, capTop: 6.08 };
const CAB_STEP = { r: 6.03, l: 6.11, radius: 0.09 };
// the skirt cut out over each bogie up to 0.62 m (the colour elevation, conflig's model, the photos)
const CUTOUT = { half: 1.2, top: 0.62, r: 0.15 };
const COL = {
  red: '#b3201a', cream: '#e6d8b8', roof: '#6e7276', glass: '#25303a', sky: '#56697a', rubber: '#1c1c1c', bumper: '#1e1e1e', step: '#3e2416',
  louvre: '#6d1611', lamp: '#f2ecd6', panto: '#c49a3a', // (the pantograph's ochre as on conflig's model: the user, 2026-11-09, "Pantograph color is good")
  // the bogies dusty brown (the user's photo of a T3 bogie over the pit, 2026-11-09)
  wheel: '#51483f', tyre: '#6e665d', hub: '#625a50', frame: '#5d5146', spring: '#6e604f', shoe: '#40392f',
};

const lerpProfile = (P, h) => {
  if (h <= P[0][0]) return P[0][1];
  for (let i = 1; i < P.length; i++) if (h <= P[i][0]) { const [h0, z0] = P[i - 1], [h1, z1] = P[i]; return z0 + (z1 - z0) * (h - h0) / (h1 - h0 || 1); }
  return P[P.length - 1][1];
};
// the cross-section: vertical sides, the roof's shoulders a quarter circle into the flat top
const halfWidth = (h) => (h <= EAVE ? HW : HW - SHOULDER + Math.sqrt(Math.max(0, SHOULDER ** 2 - (h - EAVE) ** 2)));
// the half width on the taper that every height shares (between SIDE and the corner at the waist)
function taperHW(k, z) {
  const [cw, cz] = CORNER[k], t = (z - SIDE[k]) / (cz - SIDE[k]);
  return HW - Math.min(1, Math.max(0, t)) * (HW - cw);
}

// The right half of the plan outline at height h (x <= 0, the plan's y is the car's z), from the rear nose
// to the front nose: 21 points.
function half(h) {
  const s = halfWidth(h) / HW;
  const end = (k) => { // from the nose to the split point: 9 points
    const sign = k === 'f' ? 1 : -1, nose = sign * lerpProfile(NOSE[k], h), cw = CORNER[k][0] * s;
    const C = new THREE.Vector2(-cw, nose - sign * FACE);
    // the taper's direction from the corner back to where the sides run straight
    const d = new THREE.Vector2(-HW * s, SIDE[k]).sub(new THREE.Vector2(-CORNER[k][0] * s, CORNER[k][1])).normalize();
    const faceAt = (x) => new THREE.Vector2(x, nose - sign * FACE * (x / cw) ** 2);
    const P1 = faceAt(-(cw - FILLET)), P2 = C.clone().addScaledVector(d, FILLET);
    const pts = [faceAt(0), faceAt(-(cw - FILLET) * 0.4), faceAt(-(cw - FILLET) * 0.75), P1];
    for (const t of [0.25, 0.5, 0.75]) pts.push(new THREE.Vector2().addScaledVector(P1, (1 - t) ** 2).addScaledVector(C, 2 * t * (1 - t)).addScaledVector(P2, t * t));
    pts.push(P2);
    const zs = sign > 0 ? Math.min(SPLIT[k], P2.y - 0.05) : Math.max(SPLIT[k], P2.y + 0.05);
    pts.push(new THREE.Vector2(-taperHW(k, zs) * s, zs));
    return pts;
  };
  return [...end('r'), new THREE.Vector2(-HW * s, SIDE.r), new THREE.Vector2(-HW * s, 0), new THREE.Vector2(-HW * s, SIDE.f), ...end('f').reverse()];
}
const SEAM = 10; // the index of the right side's point at z = 0 in half(): the outline starts and ends there

// The whole outline at h: from the right side's middle forward, round the front, back along the left side,
// round the rear and forward again to the start (the seam's point twice, for its texture coordinates).
// Seen from above it runs clockwise: a quad from one point to the next and up faces outwards.
function ring(h) {
  const r = half(h), n = r.length, left = [];
  for (let i = n - 2; i >= 1; i--) left.push(new THREE.Vector2(-r[i].x, r[i].y));
  return [...r.slice(SEAM), ...left, ...r.slice(0, SEAM + 1)];
}

// the texture's layout: the sides in the top 512 rows (u along the outline at REF_H, v by height), the
// roof's top in the 128 below (u along the car, v across)
const TW = 4096, TH = 640, SIDE_ROWS = 512, TOP_H = 3.06, BOT_H = 0.30, ROOF_HALF = 0.9, ROOF_LEN = 7.05;
const rowOf = (h) => (TOP_H - h) / (TOP_H - BOT_H) * SIDE_ROWS;
const vOf = (h) => 1 - rowOf(h) / TH;
let REF = null; // the reference outline: its points with their u, and its length
function reference() {
  if (REF) return REF;
  const pts = ring(REF_H), d = [0];
  for (let i = 1; i < pts.length; i++) d.push(d[i - 1] + pts[i].distanceTo(pts[i - 1]));
  const L = d[d.length - 1];
  REF = { L, pts: pts.map((p, i) => ({ x: p.x, z: p.y, u: d[i] / L })) };
  return REF;
}
// u of the nearest point of the reference outline to (x, z)
function uAt(x, z) {
  const R = reference().pts;
  let best = Infinity, bu = 0;
  for (let i = 1; i < R.length; i++) {
    const a = R[i - 1], b = R[i], dx = b.x - a.x, dz = b.z - a.z, l2 = dx * dx + dz * dz || 1e-9;
    const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (z - a.z) * dz) / l2));
    const dd = (a.x + t * dx - x) ** 2 + (a.z + t * dz - z) ** 2;
    if (dd < best) { best = dd; bu = a.u + t * (b.u - a.u); }
  }
  return bu;
}
// the reference outline's x at z on a side (sign -1 right, 1 left), behind the end's corner
function sideX(sign, z) {
  const R = reference().pts.filter((p) => Math.sign(p.x) === sign && Math.abs(p.x) > 0.6).sort((a, b) => a.z - b.z);
  for (let i = 1; i < R.length; i++) {
    const a = R[i - 1], b = R[i];
    if (z >= a.z && z <= b.z) return a.x + (b.x - a.x) * (z - a.z) / (b.z - a.z || 1);
  }
  return sign * HW;
}
// the point of the reference outline at u
function atU(u) {
  const R = reference().pts;
  for (let i = 1; i < R.length; i++) if (u <= R[i].u) {
    const a = R[i - 1], b = R[i], t = (u - a.u) / (b.u - a.u || 1);
    return { x: a.x + t * (b.x - a.x), z: a.z + t * (b.z - a.z) };
  }
  return R[R.length - 1];
}

// --- the livery: one canvas for every car
let LIVERY = null;
function livery() {
  if (LIVERY) return LIVERY;
  const { L } = reference(), du = (m) => m / L;
  const cv = document.createElement('canvas');
  cv.width = TW; cv.height = TH;
  const g = cv.getContext('2d');
  const X = (u) => u * TW, Y = rowOf;
  const span = (u0, u1, h0, h1, color) => { g.fillStyle = color; g.fillRect(X(u0), Y(h1), X(u1) - X(u0), Y(h0) - Y(h1)); };
  const rrect = (u0, u1, h0, h1, r, fill, stroke = null, lw = 3) => {
    g.beginPath();
    g.roundRect(X(u0), Y(h1), X(u1) - X(u0), Y(h0) - Y(h1), r);
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.stroke(); }
  };
  // glass: the sky's reflection at the top fading into the dark inside
  const glass = (h0, h1) => { const gr = g.createLinearGradient(0, Y(h1), 0, Y(h0)); gr.addColorStop(0, COL.sky); gr.addColorStop(0.45, COL.glass); gr.addColorStop(1, COL.glass); return gr; };
  g.fillStyle = COL.cream;
  g.fillRect(0, 0, TW, TH);
  // the bands, column by column: where the outline is at that u decides the red's top and the caps
  const redTop = (x, z) => {
    if (z < 0) return LIV.red[1];
    const right = x < 0, zs = right ? CAB_STEP.r : CAB_STEP.l, R = CAB_STEP.radius;
    if (z < zs) return LIV.red[1];
    if (z >= zs + R) return LIV.redCab;
    const t = zs + R - z, arc = Math.sqrt(R * R - t * t);
    return right ? LIV.redCab - R + arc : LIV.redCab + R - arc;
  };
  for (let c = 0; c < TW; c++) {
    const u = (c + 0.5) / TW, { x, z } = atU(u), az = Math.abs(z), end = z > SPLIT.f || z < SPLIT.r;
    const col = (h0, h1, color) => { g.fillStyle = color; g.fillRect(c, Y(h1), 1, Y(h0) - Y(h1)); };
    const top = redTop(x, z);
    col(LIV.red[0], top, COL.red);
    col(LIV.red[0] - 0.008, LIV.red[0], '#6a1a14'); // the red's lower edge
    col(top, top + 0.008, '#5a1410');
    // the roof grey over the middle; the ends' caps cream
    if (!end) {
      col(LIV.gutter, TOP_H, az < LIV.capTop ? COL.roof : COL.cream);
      col(LIV.eave, LIV.gutter, az < LIV.capSide ? COL.roof : COL.cream);
      if (az > 3.3 && az < 5.9) col(LIV.gutter - 0.012, LIV.gutter + 0.004, '#3a3c3e');
    }
  }
  const sideU = (sign, z) => uAt(sideX(sign, z), z);
  const along = (sign, z0, z1) => { const a = sideU(sign, z0), b = sideU(sign, z1); return [Math.min(a, b), Math.max(a, b)]; };
  // windows: a thin rubber edge, glass, the transom and the upper pair of hoppers
  for (const [sign, list] of [[-1, WIN_R], [1, WIN_L]]) for (const [z0, z1] of list) {
    const [a, b] = along(sign, z0, z1), m = (a + b) / 2;
    rrect(a, b, LIV.glass[0], LIV.glass[1], 8, glass(...LIV.glass), COL.rubber, 2);
    span(a, b, LIV.transom[0], LIV.transom[1], '#c9c3b2');
    span(m - du(0.009), m + du(0.009), LIV.transom[1], LIV.glass[1], '#c9c3b2');
  }
  // the doors (right side): four cream leaves, each with a tall pane over a lower one, a dark gap in the middle
  for (const [z0, z1] of DOORS) {
    const [a, b] = along(-1, z0, z1), w = (b - a) / 4;
    span(a, b, BOT_H, 2.6, COL.cream);
    for (let k = 0; k < 4; k++) {
      const l0 = a + k * w, l1 = l0 + w, m = w * 0.12;
      rrect(l0 + m, l1 - m, 1.68, 2.50, 10, glass(1.68, 2.50), COL.rubber, 2);
      rrect(l0 + m, l1 - m, 0.73, 1.59, 10, glass(0.73, 1.59), COL.rubber, 2);
      if (k) span(l0 - du(0.004), l0 + du(0.004), BOT_H, 2.6, COL.rubber);
    }
    span(a + 2 * w - du(0.02), a + 2 * w + du(0.02), BOT_H, 2.6, '#2a2a2a');
    span(a, b, 2.585, 2.6, COL.rubber);
    span(a - du(0.008), a, BOT_H, 2.6, COL.rubber);
    span(b, b + du(0.008), BOT_H, 2.6, COL.rubber);
  }
  // the ends' glazing: the panoramic windscreen wrapping round the corners onto the sides, two thin posts in
  // it; the rear window likewise, with posts at the corners as well
  const [fr, fl] = [sideU(-1, 6.22), sideU(1, 6.22)];
  rrect(fr, fl, 1.66, LIV.glass[1], 14, glass(1.66, LIV.glass[1]), COL.rubber, 2);
  for (const x of [-0.61, 0.61]) { const u = uAt(x, 7); span(u - du(0.014), u + du(0.014), 1.66, LIV.glass[1], '#c9c3b2'); }
  g.strokeStyle = '#151515'; g.lineWidth = 3;
  for (const [x0, x1] of [[-0.40, -0.55], [0.06, -0.09]]) { // the wipers
    g.beginPath(); g.moveTo(X(uAt(x0, 7)), Y(1.70)); g.lineTo(X(uAt(x1, 7)), Y(2.24)); g.stroke();
  }
  // the flaps: under the windscreen, across the red's top edge; on the rear, in the red under the window
  const flap = (sign, h0, h1, color) => {
    const a = uAt(-sign * 0.25, sign * 7), b = uAt(sign * 0.25, sign * 7), [u0, u1] = [Math.min(a, b), Math.max(a, b)];
    g.strokeStyle = color; g.lineWidth = 2;
    g.beginPath(); g.roundRect(X(u0), Y(h1), X(u1) - X(u0), Y(h0) - Y(h1), 5); g.stroke();
  };
  flap(1, 1.40, 1.555, '#7c3a2c');
  flap(-1, 1.36, 1.50, '#7a1812');
  const [rl, rr] = [sideU(1, -6.09), sideU(-1, -6.29)];
  rrect(rl, rr, 1.70, 2.53, 14, glass(1.70, 2.53), COL.rubber, 2);
  for (const x of [-0.6, 0.6]) { const u = uAt(x, -7); span(u - du(0.014), u + du(0.014), 1.70, 2.53, '#c9c3b2'); }
  for (const sign of [-1, 1]) { const u = uAt(sign * CORNER.r[0], CORNER.r[1]); span(u - du(0.012), u + du(0.012), 1.70, 2.53, '#c9c3b2'); }
  // the skirt cut out over the bogies (transparent: the material tests the alpha)
  g.save();
  g.globalCompositeOperation = 'destination-out';
  for (const sign of [-1, 1]) for (const zc of [-PIVOT, PIVOT]) {
    const [a, b] = along(sign, zc - CUTOUT.half, zc + CUTOUT.half);
    g.beginPath();
    // (down to 0.33 m: under the body's edge at 0.35, and 6 rows clear of the roof's part of the texture)
    g.roundRect(X(a), Y(CUTOUT.top), X(b) - X(a), Y(0.33) - Y(CUTOUT.top), [X(du(CUTOUT.r)), X(du(CUTOUT.r)), 0, 0]);
    g.fill();
  }
  g.restore();
  // the louvres of the motor-generator's air intake, left side
  for (let k = 0; k < 3; k++) {
    const [a, b] = along(1, -1.37 + k * 0.41, -1.37 + k * 0.41 + 0.38);
    for (let h = 0.87; h < 1.29; h += 0.035) span(a, b, h, h + 0.016, COL.louvre);
  }
  // the roof's top: grey, the caps cream at the ends
  const rz = (z) => (z + ROOF_LEN) / (2 * ROOF_LEN) * TW;
  g.fillStyle = COL.roof; g.fillRect(0, SIDE_ROWS, TW, TH - SIDE_ROWS);
  g.fillStyle = COL.cream;
  g.fillRect(0, SIDE_ROWS, rz(-LIV.capTop), TH - SIDE_ROWS);
  g.fillRect(rz(LIV.capTop), SIDE_ROWS, TW - rz(LIV.capTop), TH - SIDE_ROWS);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  tex.userData.shared = true;
  LIVERY = tex;
  return tex;
}

// --- the shapes, built once for every set
function bodyGeometry() {
  const R = reference().pts, n = R.length, pos = [], uv = [], idx = [];
  RINGS.forEach((h) => ring(h).forEach((p, j) => { pos.push(p.x, h, p.y); uv.push(R[j].u, vOf(h)); }));
  for (let r = 0; r + 1 < RINGS.length; r++) for (let j = 0; j + 1 < n; j++) {
    const a = r * n + j, b = a + 1, d = a + n, c = d + 1;
    idx.push(a, b, d, b, c, d);
  }
  const side = new THREE.BufferGeometry();
  side.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  side.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  side.setIndex(idx);
  side.computeVertexNormals(); // (the creases' zero-area bands add nothing to either side's normals)
  const top = cap(ring(ROOF), ROOF, 1), tp = top.attributes.position, tuv = [];
  for (let i = 0; i < tp.count; i++) tuv.push((tp.getZ(i) + ROOF_LEN) / (2 * ROOF_LEN), 1 - (SIDE_ROWS + (tp.getX(i) + ROOF_HALF) / (2 * ROOF_HALF) * (TH - SIDE_ROWS)) / TH);
  top.setAttribute('uv', new THREE.Float32BufferAttribute(tuv, 2));
  return mergeGeometries([side, top]);
}
// a flat cap over an outline at height y, facing up (dir 1) or down (-1)
function cap(pts, y, dir) {
  const contour = pts.slice(0, -1);
  const pos = [], nor = [], idx = [];
  for (const p of contour) { pos.push(p.x, y, p.y); nor.push(0, dir, 0); }
  for (const [a, b, c] of THREE.ShapeUtils.triangulateShape(contour, [])) {
    // a triangle (a, b, c) faces up when (c - a) x (b - a) in the plan, x by z, is positive
    const A = contour[a], B = contour[b], Cc = contour[c];
    const up = (Cc.x - A.x) * (B.y - A.y) - (B.x - A.x) * (Cc.y - A.y);
    if (Math.sign(up) === dir) idx.push(a, b, c); else idx.push(a, c, b);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setIndex(idx);
  return geo;
}

// one part in vertex colours: its geometry moved into place (Euler order YXZ: the yaw last), the uv dropped
function part(geo, color, { at = [0, 0, 0], rot = [0, 0, 0], scale = [1, 1, 1] } = {}) {
  const m = new THREE.Matrix4().compose(new THREE.Vector3(...at), new THREE.Quaternion().setFromEuler(new THREE.Euler(...rot, 'YXZ')), new THREE.Vector3(...scale));
  const g = geo.clone().applyMatrix4(m);
  if (g.attributes.uv) g.deleteAttribute('uv');
  if (!g.index) g.setIndex([...Array(g.attributes.position.count).keys()]); // mergeGeometries: all indexed
  const c = new THREE.Color(color), col = new Float32Array(g.attributes.position.count * 3); // (Color reads sRGB into linear)
  for (let i = 0; i < col.length; i += 3) { col[i] = c.r; col[i + 1] = c.g; col[i + 2] = c.b; }
  g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  return g;
}
const box = (w, h, d) => new THREE.BoxGeometry(w, h, d);
// a bar from a to b, radius r
function bar(a, b, r, color) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b);
  const g = new THREE.CylinderGeometry(r, r, A.distanceTo(B), 6);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), B.clone().sub(A).normalize()));
  g.translate((A.x + B.x) / 2, (A.y + B.y) / 2, (A.z + B.z) / 2);
  return part(g, color);
}
// a strip `out` m proud of the outline between heights h0 and h1, round an end from |z| = z0 (sign 1 the
// front, -1 the rear): its outer face, top and underside, wound like the outline (outwards)
function strip(sign, z0, h0, h1, out, color) {
  const pts = ring((h0 + h1) / 2).filter((p) => sign * p.y >= z0);
  const off = pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    const t = new THREE.Vector2(b.x - a.x, b.y - a.y).normalize();
    return p.clone().add(new THREE.Vector2(-t.y, t.x).multiplyScalar(out)); // outwards: the tangent turned left
  });
  const pos = [], idx = [];
  const quad = (a, b, c, d) => { const i = pos.length / 3; pos.push(...a, ...b, ...c, ...d); idx.push(i, i + 1, i + 2, i, i + 2, i + 3); };
  for (let i = 1; i < pts.length; i++) {
    const [o0, o1, p0, p1] = [off[i - 1], off[i], pts[i - 1], pts[i]];
    quad([o0.x, h0, o0.y], [o1.x, h0, o1.y], [o1.x, h1, o1.y], [o0.x, h1, o0.y]);
    quad([o0.x, h1, o0.y], [o1.x, h1, o1.y], [p1.x, h1, p1.y], [p0.x, h1, p0.y]);
    quad([p0.x, h0, p0.y], [p1.x, h0, p1.y], [o1.x, h0, o1.y], [o0.x, h0, o0.y]);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return part(g, color);
}

// The pantograph (both drawings): seen from the side a rhombus, its lower arms from the base and its upper
// arms to the collector meeting at knees fore and aft; two such frames side by side, the knees on shafts
// across. The arms keep their lengths, so the knees spread as the head comes down to the wire.
const PANTO = { z: 3.1, x: 0.55, lower: 1.70, upper: 1.75, head: 0.025 };
function pantograph(wire) {
  const base = ROOF + 0.09, top = wire - 0.005 - PANTO.head, rise = top - base, out = [], c = COL.panto;
  // the knee's height a over the base: lower^2 - a^2 = upper^2 - (rise - a)^2
  const a = (PANTO.lower ** 2 - PANTO.upper ** 2 + rise ** 2) / (2 * rise), dz = Math.sqrt(Math.max(0, PANTO.lower ** 2 - a * a));
  const P = (x, y, z) => [x, base + y, PANTO.z + z];
  for (const x of [-PANTO.x, PANTO.x]) {
    for (const s of [-1, 1]) out.push(bar(P(x, 0, 0), P(x, a, s * dz), 0.028, c), bar(P(x, a, s * dz), P(x, rise, 0), 0.022, c));
  }
  for (const s of [-1, 1]) out.push(bar(P(-PANTO.x, a, s * dz), P(PANTO.x, a, s * dz), 0.02, c)); // the knees' shafts
  // the collector: its bar across the top with the horns turned down, on the frames' tops
  out.push(part(box(1.3, 2 * PANTO.head, 0.1), '#2b2b2b', { at: P(0, rise, 0) }));
  for (const s of [-1, 1]) out.push(bar(P(s * 0.65, rise, 0), P(s * 0.92, rise - 0.12, 0), 0.02, '#2b2b2b'));
  // the base frame on its insulators
  out.push(part(box(1.3, 0.06, 1.2), '#2e2f30', { at: [0, ROOF + 0.06, PANTO.z] }));
  for (const x of [-0.5, 0.5]) for (const z of [-0.45, 0.45]) out.push(part(new THREE.CylinderGeometry(0.04, 0.05, 0.06, 6), '#8a6a3a', { at: [x, ROOF + 0.03, PANTO.z + z] }));
  return out;
}

// a point of an end's face (sign 1 the front) at (x, h): its z, and the yaw that turns +z to its normal
function onFace(sign, x, h) {
  const k = sign > 0 ? 'f' : 'r', cw = CORNER[k][0];
  return { z: sign * (lerpProfile(NOSE[k], h) - FACE * (x / cw) ** 2), yaw: Math.atan2(2 * FACE * x / cw ** 2, sign) };
}

// a point of a side (sign -1 the right, 1 the left) at z on the reference outline: its x, the yaw that turns
// +z along the side, and the outward normal in plan (x, z)
function onSide(sign, z) {
  const x = sideX(sign, z), tx = sideX(sign, z + 0.05) - x, l = Math.hypot(tx, 0.05);
  return { x, yaw: Math.atan2(tx, 0.05), n: [sign * 0.05 / l, -sign * tx / l] };
}

// The bogie (the user's photo of one over the pit): the wheels outermost, their discs inside the tyres with the
// hub's hex; inside them the frame (a bridge bogie): the side beam low between the wheels, the axle boxes, coil
// springs by the wheels and the ribbed rubber spring between them, the track-brake shoes 12 mm over the rail on
// their hangers; all of it dusty brown
function bogie(zc) {
  const P = [];
  for (const sx of [-1, 1]) {
    for (const dz of [-WHEELBASE / 2, WHEELBASE / 2]) {
      const z = zc + dz, side = { rot: [0, 0, Math.PI / 2] };
      P.push(part(new THREE.CylinderGeometry(WHEEL_R, WHEEL_R, 0.1, 24), COL.tyre, { at: [sx * 0.75, WHEEL_R, z], ...side }));
      P.push(part(new THREE.CylinderGeometry(WHEEL_R - 0.055, WHEEL_R - 0.055, 0.106, 24), COL.wheel, { at: [sx * 0.75, WHEEL_R, z], ...side }));
      P.push(part(new THREE.CylinderGeometry(0.085, 0.085, 0.03, 6), COL.hub, { at: [sx * 0.815, WHEEL_R, z], ...side }));
      P.push(part(box(0.14, 0.2, 0.22), COL.frame, { at: [sx * 0.62, WHEEL_R, z] }));
      P.push(part(new THREE.CylinderGeometry(0.05, 0.05, 0.17, 8), COL.spring, { at: [sx * 0.62, 0.55, z - Math.sign(dz) * 0.36] }));
    }
    P.push(part(box(0.12, 0.17, WHEELBASE + 0.2), COL.frame, { at: [sx * 0.62, 0.3, zc] }));
    P.push(part(new THREE.CylinderGeometry(0.19, 0.19, 0.26, 16), COL.spring, { at: [sx * 0.6, 0.55, zc] }));
    for (const y of [0.49, 0.57]) P.push(part(new THREE.CylinderGeometry(0.205, 0.205, 0.025, 16), COL.frame, { at: [sx * 0.6, y, zc] }));
    P.push(part(box(0.1, 0.11, 1.05), COL.shoe, { at: [sx * 0.75, T3.trackBrakeGap + 0.055, zc] }));
    for (const dz of [-0.42, 0.42]) P.push(part(box(0.04, 0.2, 0.04), COL.frame, { at: [sx * 0.75, 0.2, zc + dz] }));
  }
  P.push(part(box(1.4, 0.14, 0.5), COL.frame, { at: [0, 0.48, zc] }));
  return P;
}

// The mirror (the user's photos of 6921 and 7122): its arm rises from the cap's side over the front door, runs out
// and drops; the route plate hangs on the drop facing forward (src/models.js puts the plate on it), the mirror
// below it, its back to the front. A small mirror on a bracket at the left corner.
const SIDE_INDICATOR = { z: 3.05, h: 1.81 };
// the T3M's side display: in the upper part of the right side's second window from the front (the user's photo of 8015)
const SIDE_DISPLAY = { z: 2.29, h: 2.31, w: 1.05, hh: 0.33 };
const ARM = [[-0.86, 2.82, 6.05], [-1.2, 3.02, 6.22], [-1.54, 3.02, 6.28], [-1.62, 2.94, 6.28], [-1.62, 2.3, 6.28]];
const MIRROR_PLATE = [-1.62, 2.52, 6.31];

function partsGeometry(wire, variant) {
  const P = [], dark = '#2c2d2e', steel = '#3a3b3c';
  for (const zc of [-PIVOT, PIVOT]) P.push(...bogie(zc));
  // under the body: the equipment's lower edge between the bogies, the floor's underside, the door steps
  P.push(part(box(2.0, 0.07, 3.6), dark, { at: [0, BOTTOM - 0.035, 0] }));
  P.push(part(cap(ring(BOTTOM), BOTTOM, -1), dark));
  for (const [z0, z1] of DOORS) {
    const xa = sideX(-1, z0), xb = sideX(-1, z1);
    P.push(part(box(0.24, 0.05, Math.hypot(xb - xa, z1 - z0) - 0.06), COL.step, { at: [(xa + xb) / 2 + 0.1, BOTTOM - 0.03, (z0 + z1) / 2], rot: [0, Math.atan2(xb - xa, z1 - z0), 0] }));
  }
  // the ends: the black bumper round the end back to the doors, the coupler's gear under the cream panel, the
  // coupler's bar and head
  for (const sign of [1, -1]) {
    P.push(strip(sign, 6.05, LIV.bumper[0], LIV.bumper[1], 0.05, COL.bumper));
    const zf = sign * lerpProfile(NOSE[sign > 0 ? 'f' : 'r'], 0.4);
    P.push(part(box(1.0, 0.18, 0.3), '#2e2e2e', { at: [0, 0.21, zf - sign * 0.42] }));
    P.push(bar([0, COUPLER_H, zf - sign * 0.3], [0, COUPLER_H, sign * (COUPLER_FACE - 0.16)], 0.045, steel));
    P.push(part(box(0.24, 0.17, 0.16), steel, { at: [0, COUPLER_H, sign * (COUPLER_FACE - 0.08)] }));
  }
  // behind each bogie's cutouts, a dark panel down the middle (the cutouts do not show through the car)
  for (const zc of [-PIVOT, PIVOT]) P.push(part(box(0.02, CUTOUT.top - BOTTOM + 0.04, 2 * CUTOUT.half), '#2e2a26', { at: [0, (CUTOUT.top + BOTTOM) / 2, zc] }));
  for (const x of [-0.53, 0.53]) { // the headlights' housings, in the body's red
    const f = onFace(1, x, 1.03);
    P.push(part(new THREE.CylinderGeometry(0.115, 0.12, 0.05, 18), COL.red, { at: [x + 0.012 * Math.sin(f.yaw), 1.03, f.z + 0.012 * Math.cos(f.yaw)], rot: [Math.PI / 2, f.yaw, 0] }));
  }
  // the lamp units' housings by the corners, the side indicators' on the pillar amidships
  for (const [sign, z] of [[-1, 6.42], [1, 6.42], [-1, -6.45], [1, -6.45]]) {
    const s = onSide(sign, z);
    P.push(part(box(0.02, 0.24, 0.095), '#262626', { at: [s.x + s.n[0] * 0.008, 1.235, z + s.n[1] * 0.008], rot: [0, s.yaw, 0] }));
  }
  for (const sign of [-1, 1]) P.push(part(box(0.016, 0.135, 0.08), '#262626', { at: [sign * (HW + 0.006), SIDE_INDICATOR.h, SIDE_INDICATOR.z] }));
  // the roof (the colour elevation): three hatches, a low cover behind the pantograph, a box amidships, the
  // aerial on the front cap, the pantograph; on a T3M the resistors' box towards the rear (the user's photos
  // of 8080 and 8088: "Box on top with resistors towards back only for t3m")
  for (const z of [-5.2, -0.78, 4.69]) P.push(part(box(0.62, 0.06, 1.05), '#7c8084', { at: [0, ROOF + 0.03, z] }));
  P.push(part(box(0.9, 0.05, 1.45), '#5c6064', { at: [0, ROOF + 0.025, 1.7] }));
  P.push(part(box(0.5, 0.12, 0.5), '#5c6064', { at: [0, ROOF + 0.06, 0.18] }));
  if (variant === 'T3M') { // (short but wide, its top a grille: the user, 2026-11-09, and a model of an 8xxx)
    P.push(part(box(1.4, 0.2, 0.85), '#45484b', { at: [0, ROOF + 0.1, -3.0] }));
    for (let k = 0; k < 8; k++) P.push(part(box(1.32, 0.02, 0.05), '#5d6164', { at: [0, ROOF + 0.205, -3.35 + 0.1 * k] }));
  }
  P.push(bar([0, ROOF - 0.05, 5.68], [0, ROOF + 0.24, 5.68], 0.015, '#8a8d90'), bar([0, ROOF + 0.24, 5.55], [0, ROOF + 0.24, 5.81], 0.012, '#8a8d90'));
  P.push(...pantograph(wire));
  for (let i = 1; i < ARM.length; i++) P.push(bar(ARM[i - 1], ARM[i], 0.02, '#8a8d90'));
  P.push(part(box(0.22, 0.38, 0.05), '#1c1c1c', { at: [-1.66, 2.2, 6.24] })); // (its top behind the plate)
  P.push(bar([0.78, 1.72, 6.58], [0.98, 1.8, 6.52], 0.012, '#8a8d90'), part(box(0.05, 0.18, 0.11), '#1c1c1c', { at: [1.0, 1.9, 6.5] }));
  return mergeGeometries(P);
}

// The lamps (lit): the round headlights; rectangular units by the corners, an orange indicator over a clear
// lamp at the front and over a red one at the rear (the user, 2026-11-09: "round or rectangle, I would choose
// the latter"); on the rear face two red lamps and the white one between them, the round red reflectors under
// the bumper (the photos of 6892 and 6921)
function lampsGeometry() {
  const L = [];
  for (const x of [-0.53, 0.53]) {
    const f = onFace(1, x, 1.03);
    L.push(part(new THREE.CircleGeometry(0.085, 18), COL.lamp, { at: [x + 0.042 * Math.sin(f.yaw), 1.03, f.z + 0.042 * Math.cos(f.yaw)], rot: [0, f.yaw, 0] }));
  }
  for (const [sign, z, low] of [[-1, 6.42, '#f2efe4'], [1, 6.42, '#f2efe4'], [-1, -6.45, '#d8261a'], [1, -6.45, '#d8261a']]) {
    const s = onSide(sign, z), at = (h) => [s.x + s.n[0] * 0.02, h, z + s.n[1] * 0.02];
    L.push(part(box(0.012, 0.1, 0.075), '#ff9a22', { at: at(1.29), rot: [0, s.yaw, 0] }));
    L.push(part(box(0.012, 0.1, 0.075), low, { at: at(1.175), rot: [0, s.yaw, 0] }));
  }
  const onRear = (x, h, w, hh, color) => {
    const f = onFace(-1, x, h);
    L.push(part(box(w, hh, 0.02), color, { at: [x + 0.012 * Math.sin(f.yaw), h, f.z + 0.012 * Math.cos(f.yaw)], rot: [0, f.yaw, 0] }));
  };
  // the side indicators: on the pillar between the first and second windows on the right, the second and third on
  // the left (both 3.05 m ahead of the centre), at the window band's foot (the user's photos of 8015 and 8080)
  for (const sign of [-1, 1]) L.push(part(box(0.012, 0.11, 0.06), '#ff9a22', { at: [sign * (HW + 0.016), SIDE_INDICATOR.h, SIDE_INDICATOR.z] }));
  for (const x of [-0.47, 0.47]) onRear(x, 0.95, 0.2, 0.07, '#d8261a');
  onRear(0, 0.95, 0.16, 0.055, '#f4f4ee');
  for (const x of [-0.66, 0.66]) {
    const f = onFace(-1, x, 0.6);
    L.push(part(new THREE.CircleGeometry(0.045, 14), '#c41e14', { at: [x + 0.008 * Math.sin(f.yaw), 0.6, f.z + 0.008 * Math.cos(f.yaw)], rot: [0, f.yaw, 0] }));
  }
  return mergeGeometries(L);
}

// A plate or card on the body: an upright quad 5 mm proud where a ray from outside the end meets it.
function onBody(mesh, x, y, end, w, h) {
  const hit = new THREE.Raycaster(new THREE.Vector3(x, y, end * 20), new THREE.Vector3(0, 0, -end)).intersectObject(mesh, false)[0];
  if (!hit) return null;
  const n = hit.face.normal.clone();
  if (n.z * end < 0) n.negate();
  const up = new THREE.Vector3(0, 1, 0).addScaledVector(n, -n.y).normalize();
  const right = new THREE.Vector3().crossVectors(up, n).normalize();
  return new THREE.PlaneGeometry(w, h).applyMatrix4(new THREE.Matrix4().makeBasis(right, up, n).setPosition(hit.point.clone().addScaledVector(n, 0.005)));
}
// a strip bent to an end's face (sign 1 the front), centred at height h, 15 mm proud (at 5 mm the face's facets,
// chords of the curve between the outline's points, cut into it): for a decal wider than the face is flat
function onFaceStrip(sign, h, w, hh, n = 10) {
  const pos = [], uv = [], idx = [];
  for (let i = 0; i <= n; i++) for (const [j, y] of [[0, h - hh / 2], [1, h + hh / 2]]) {
    const x = sign * (-w / 2 + (w * i) / n), f = onFace(sign, x, y);
    pos.push(x + 0.015 * Math.sin(f.yaw), y, f.z + 0.015 * Math.cos(f.yaw));
    uv.push(i / n, j);
  }
  for (let i = 0; i < n; i++) { const a = 2 * i; idx.push(a, a + 2, a + 1, a + 2, a + 3, a + 1); }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}
// a quad on a straight side (sign -1 the right), read from that side
function onFlank(sign, z, h, w, hh) {
  const right = new THREE.Vector3(0, 0, -sign), n = new THREE.Vector3(sign, 0, 0);
  return new THREE.PlaneGeometry(w, hh).applyMatrix4(new THREE.Matrix4().makeBasis(right, new THREE.Vector3(0, 1, 0), n).setPosition(sign * (HW + 0.004), h, z));
}

// The fleet number, yellow as on the T3Ms (the user's photos of 8080 and 8088: "in style of the t3m photos, no
// logos"): on the front between the headlights, on the rear over the lamps, on both sides at the red's top
// behind the front door
function fleetTexture(n) {
  const cv = document.createElement('canvas');
  cv.width = 512; cv.height = 160;
  const g = cv.getContext('2d');
  g.fillStyle = '#ffd21a';
  g.font = 'bold 148px "Bahnschrift", "D-DIN", "DIN Alternate", Arial, sans-serif';
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(String(n), 256, 86, 328);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// The variant and the fleet numbers of a set, from its run number when not given: a quarter of the sets T3Ms
// (8001-8090), the rest T3SUCS (7001-7292), each car its own number
const hashOf = (s) => { let h = 2166136261; for (const ch of String(s)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619) >>> 0; return h; };
export const t3Variant = (run) => (hashOf(run) % 4 === 1 ? 'T3M' : 'T3SUCS');
export function fleetNumbers(variant, run, cars) {
  const [lo, span] = variant === 'T3M' ? [8001, 90] : [7001, 292], h = hashOf(`${run}#`);
  return Array.from({ length: cars }, (_, k) => lo + ((h + k * 37) % span));
}

let SHAPES = null;
const PARTS = new Map();
function shapes(wire, variant) {
  if (!SHAPES || SHAPES.wire !== wire) {
    const body = bodyGeometry(), lamps = lampsGeometry();
    const probe = new THREE.Mesh(body);
    probe.updateMatrixWorld(true);
    // Prague's plates and cards (src/models.js): the route number in the box on the front cap and on the
    // mirror arm (smaller, taller than wide), the destination and the run number resting on the windscreen's
    // lower edge (the user, 2026-11-09: "closer to the bottom glass border"), the run number on the pane right
    // of the post (left as seen from the front), the route inverted in the rear window
    const plates = {
      rb: onBody(probe, 0, 2.74, 1, 0.56, 0.3), mir: new THREE.PlaneGeometry(0.22, 0.28).translate(...MIRROR_PLATE),
      dest: onBody(probe, -0.02, 1.77, 1, 0.46, 0.19), run: onBody(probe, -0.67, 1.725, 1, 0.12, 0.09), rear: onBody(probe, 0, 1.90, -1, 0.34, 0.3),
      led: onFlank(-1, SIDE_DISPLAY.z, SIDE_DISPLAY.h, SIDE_DISPLAY.w, SIDE_DISPLAY.hh),
    };
    // (the figures fill 0.64 of the texture's width and 0.66 of its height: 0.15 m tall on the front, between the
    // headlights, 0.14 m on the rear, 0.10 m on the sides, as on 6921, 6892 and 8080)
    const fleet = mergeGeometries([onFaceStrip(1, 1.03, 0.86, 0.23), onFaceStrip(-1, 1.15, 0.78, 0.21), onFlank(-1, 4.12, 1.5, 0.55, 0.15), onFlank(1, 4.12, 1.5, 0.55, 0.15)]);
    for (const g of [body, lamps, fleet, ...Object.values(plates)]) if (g) g.userData.shared = true;
    SHAPES = { wire, body, lamps, plates, fleet, livery: livery() };
    PARTS.clear();
  }
  if (!PARTS.has(variant)) { const g = partsGeometry(wire, variant); g.userData.shared = true; PARTS.set(variant, g); }
  return { ...SHAPES, parts: PARTS.get(variant) };
}

// A set of `cars` built-in T3s in `root` (src/models.js makeT3): `mats` holds the plates' materials
// (route box, mirror plate, rear plate, destination and run cards), which setConsistLine swaps; `variant`
// 'T3SUCS' or 'T3M', `fleet` the cars' numbers.
export function makeSimpleSet(root, cars, dest, mats, wire, { variant = 'T3SUCS', fleet = fleetNumbers(variant, '', cars) } = {}) {
  const P = shapes(wire, variant);
  // each set owns its materials (traffic fades them one set at a time); the shapes and the livery are shared
  Object.assign(mats, {
    body: new THREE.MeshLambertMaterial({ map: P.livery, alphaTest: 0.5 }), // (the alpha: the skirt's cutouts)
    parts: new THREE.MeshLambertMaterial({ vertexColors: true }),
    lamps: new THREE.MeshBasicMaterial({ vertexColors: true }),
  });
  Object.assign(root.userData, { mats, bogie: PIVOT, bodyFront: BODY_FRONT, cars: [], variant, fleet });
  for (let k = 0; k < cars; k++) {
    const car = new THREE.Group();
    car.rotation.order = 'YXZ';
    const mesh = (g, m, name) => { if (g) { const o = new THREE.Mesh(g, m); o.name = name; car.add(o); } };
    mesh(P.body, mats.body, 'body');
    mesh(P.parts, mats.parts, 'parts');
    mesh(P.lamps, mats.lamps, 'lamps');
    // (a decal blended at its edges: its userData.opacity under 1 keeps it transparent when traffic fades the set)
    const fm = new THREE.MeshLambertMaterial({ map: fleetTexture(fleet[k]), transparent: true, opacity: 0.999, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
    fm.userData.opacity = 0.999;
    mesh(P.fleet, fm, 'fleet');
    // the leading car carries the plates and the cards in the windscreen (no destination card when it is
    // not known), the last one the inverted plate in the rear window
    if (k === 0) {
      mesh(P.plates.rb, mats.rbMat, 'plate');
      mesh(P.plates.mir, mats.mirMat, 'plate');
      if (dest) mesh(P.plates.dest, mats.destMat, 'plate');
      mesh(P.plates.run, mats.runMat, 'plate');
    }
    if (k === cars - 1) mesh(P.plates.rear, mats.rearMat, 'plate');
    if (mats.ledMat) mesh(P.plates.led, mats.ledMat, 'display'); // (a T3M's side display, on every car)
    root.add(car);
    root.userData.cars.push(car);
  }
  return root;
}
