// The built-in Tatra T3 (#427): our own shapes after the T3's general-arrangement drawing (side and plan
// views, dimensioned) and a colour elevation of both sides and both ends, both on drawingdatabase.com
// (`Tatra-T3-1.gif`, `trams_t3_01.png`; measured in #427), with the T3's numbers from src/tram.js.
// The body is one lofted surface: a plan outline per height (straight sides; the ends tapering in plan from
// the doors to rounded corners and a bulged face) stacked along the side view's end profiles (the
// windscreen leaning back under the roof cap's visor), painted from one canvas shared by every car. The
// fittings are one mesh in vertex colours, the lamps another, the car's fleet numbers a third; the moving parts
// (#454) are instanced in the same colours: the two bogies' frames, the four wheelsets, the two couplers, the
// pantograph's bars. Eight draw calls a car, and its plates. Three types: the T3 (a silver bumper, the route box
// square), the T3SUCS (a brown bumper, the route box rounded) and the T3M (as the T3SUCS, with the resistors' box
// on the roof and its green dot-matrix displays; src/models.js draws the plates). One car: origin on the rail plane
// midway between the bogie pivots, facing +Z, the right side (the doors) at -X.
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { T3 } from './tram.js';
import { beamsMesh } from './lamps.js';

// --- the drawings' numbers: metres above the rail top and from the car's centre
const HW = 1.25;                                    // half width (2 500 mm)
const BOTTOM = 0.35, EAVE = 2.62, ROOF = 3.02;      // the skirt's lower edge; the roof's shoulder from-to
const SHOULDER = ROOF - EAVE;                       // its radius (the front view)
const PIVOT = T3.bogies / 2;                // 6 400 mm apart, 3 800 mm from each end
const WHEELBASE = 1.9, WHEEL_R = 0.35;              // 1 900 mm; wheels 700 mm
// the coupler's bar 0.59 m over the rail, as the two other models have it (conflig's classic 0.594 m, the hybrid's 0.584 m;
// the user, 2026-11-10: "I don't know proper figures so you might as well take it from the others")
const COUPLER_H = 0.59;
const COUPLER_FACE = T3.length / 2 - T3.couplerOverlap / 2; // where two coupled heads meet (src/tram.js)
// The ends in plan: straight sides between SIDE.r and SIDE.f (the plan view), then tapering to the end's
// corners (CORNER: half width, its z with the nose at 7.0 m), rounded by FILLET; the face bulges FACE m from
// the corners to the nose. Up to SPLIT the taper is the same at every height (the front and rear doors stand on
// it); beyond it, it follows the end's profile to the corner. The corners are wider than the plan view's (0.73 and
// 0.78 m): the user's head-on photos of 6892 put the corner lamp units at ±0.93-0.99 m on the front and ±0.96 m on
// the rear, and the windscreen's posts at ±0.71 m (the user, 2026-11-10: "Let's try widening and we'll see how it
// looks")
const SIDE = { f: 4.51, r: -4.84 }, SPLIT = { f: 6.05, r: -6.10 };
const CORNER = { f: [1.0, 6.79], r: [1.0, -6.79] };
const FACE = 0.21, FILLET = 0.32;
// the nose (on the centreline) by height (the side view): the lower end, the windscreen leaning back from
// 1.65 m, the roof cap's visor over it at 2.56 m; the brow over it upright to 2.86 m, then rolling into the roof
// over 0.5 m (a quarter ellipse, 0.16 m high), the rear's likewise (the user, 2026-11-10, beside the photo of 7290:
// "make the front brow less slanted, perhaps even perpendicular? The back should be similar", then "make the brow on
// both sides a bit thinner, like running a bit down towards the front and back"; the side view had it leaning back)
const BROW = { top: 2.86, run: 0.5 };
const brow = (z) => [0, 20, 40, 55, 70, 80, 90].map((d) => {
  const a = (d * Math.PI) / 180;
  return [BROW.top + (ROOF - BROW.top) * Math.sin(a), z - BROW.run + BROW.run * Math.cos(a)];
});
const NOSE = {
  f: [[0.35, 6.70], [0.47, 6.79], [0.70, 6.85], [0.80, 6.90], [1.04, 6.95], [1.54, 6.96], [1.65, 7.00], [2.53, 6.56], [2.56, 6.68],
    ...brow(6.68)],
  r: [[0.35, 6.71], [0.47, 6.81], [0.70, 6.86], [0.80, 6.91], [1.04, 6.94], [1.50, 6.98], [1.69, 7.00], [2.53, 6.77], [2.56, 6.82],
    ...brow(6.82)],
};
const BODY_FRONT = 7.0;
// the heights of the outlines; a height given twice is a crease (the normals do not blend across it)
// (every 0.1 m through the windows' band, where the end leans; close together where the brow rolls into the roof)
const RINGS = [0.35, 0.47, 0.70, 0.80, 1.04, 1.30, 1.54, 1.65, 1.65, 1.69, 1.80, 1.90, 2.00, 2.10, 2.20, 2.30, 2.40, 2.53, 2.53,
  2.56, 2.56, 2.62, 2.70, 2.78, 2.86, 2.91, 2.94, 2.965, 2.985, 3.0, 3.01, 3.017, 3.02];
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
// elevation, the user, 2026-11-09: "the shape is closer to the 2d picture". The bumper 0.76-0.86 m: the user's
// head-on photo of 6892 (2026-11-10), scaled by the skirt's foot (0.35 m), the red's top (1.48 m) and the roof
// (3.02 m), which agree to 3 %; the colour elevation has it 6 cm lower.
const LIV = { bumper: [0.76, 0.86], red: [0.84, 1.62], redCab: 1.48, glass: [1.71, 2.52], transom: [2.10, 2.135], eave: 2.56, gutter: 2.85, capSide: 3.05, capTop: 6.08 };
const CAB_STEP = { r: 6.03, l: 6.11, radius: 0.09 };
// the skirt cut out over each bogie in arches round the wheels, 2 cm clear of their treads, level over their tops
// between them (the user's photo of a T3's bogie from the side, 2026-11-10; the colour elevation and conflig's
// model have a lower, square cutout to 0.62 m)
const CUTOUT = { arch: WHEEL_R + 0.02, top: 2 * WHEEL_R + 0.02, half: WHEELBASE / 2 + WHEEL_R + 0.02 };
// the ends open under the bumper between the skirt's corners, which reach in to where the headlights start
// (the user, 2026-11-10: "the skirt stays only on sides up until where the headlights start, front and back is
// open under the bumper"; 6892's front and rear: ±0.65 m)
const OPEN = 0.65;
const COL = {
  red: '#b3201a', cream: '#e6d8b8', roof: '#6e7276', glass: '#25303a', sky: '#56697a', rubber: '#1c1c1c', step: '#3e2416',
  // the bumper brown on a T3SUCS or T3M (the photo of 7290), silver with two thin red stripes on a T3 (6892)
  bumper: '#55332f', silver: '#c3c5c4',
  louvre: '#6d1611', lamp: '#f2ecd6', panto: '#c49a3a', // (the pantograph's ochre as on conflig's model: the user, 2026-11-09, "Pantograph color is good")
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
// the point of the reference outline round an end's corner (end 1 the front, -1 the rear) on a side (sign -1 the
// right) where it is ax off the centreline: its x and z, the outward normal in plan (x, z), the yaw that turns +z
// along the outline
function atCorner(end, sign, ax) {
  const R = reference().pts.filter((p) => sign * p.x > 0 && end * p.z > 5.5);
  for (let i = 1; i < R.length; i++) {
    const a = R[i - 1], b = R[i];
    if ((Math.abs(a.x) - ax) * (Math.abs(b.x) - ax) > 0 || a.x === b.x) continue;
    const t = (ax - Math.abs(a.x)) / (Math.abs(b.x) - Math.abs(a.x)), tx = b.x - a.x, tz = b.z - a.z, l = Math.hypot(tx, tz);
    let n = [tz / l, -tx / l];
    if (n[0] * sign + n[1] * end < 0) n = [-n[0], -n[1]]; // (outwards: away from the centreline and the car's middle)
    return { x: sign * ax, z: a.z + t * tz, n, yaw: Math.atan2(tx, tz) };
  }
  return null;
}
// the texture's u where the outline at height h reaches z on a side (sign -1 the right): the body's own texture
// coordinates there, which follow the outline's points (they move with the end's lean, the reference's do not)
function ringU(h, sign, z) {
  const P = ring(h), R = reference().pts;
  for (let j = 1; j < P.length; j++) {
    const a = P[j - 1], b = P[j];
    if (sign * a.x < 0.5 || sign * b.x < 0.5 || (a.y - z) * (b.y - z) > 0 || a.y === b.y) continue;
    const t = (z - a.y) / (b.y - a.y);
    return R[j - 1].u + t * (R[j].u - R[j - 1].u);
  }
  return sideU(sign, z);
}
// u of a side's point at z on the reference outline
const sideU = (sign, z) => uAt(sideX(sign, z), z);
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
  const along =(sign, z0, z1) => { const a = sideU(sign, z0), b = sideU(sign, z1); return [Math.min(a, b), Math.max(a, b)]; };
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
  // it (±0.71 m: 6892 head on); the rear window likewise, with posts at the corners as well
  // (A window's upright edges on the sides are drawn through the body's own coordinates at each height: the
  // outline's points round an end move back with the leaning windscreen, so an edge straight in the texture
  // came out kinked on the body; the user, 2026-11-10: "clean, rounded vertical cut on the side where it meets
  // the doors, currently there's kind of zig zag pattern".)
  const wrapped = (e, zr, zl, h0, h1, r) => { // e 1 the front; zr, zl: its edges' z on the right and the left
    const pts = [], N = 6, steps = Math.ceil((h1 - h0 - 2 * r) / 0.04);
    const arc = (sign, zc, hc, a0, a1) => { for (let i = 0; i <= N; i++) { const a = a0 + (a1 - a0) * i / N; pts.push([sign, zc + e * r * Math.cos(a), hc + r * Math.sin(a)]); } };
    // the right edge from its foot up, the top across, the left edge down, the foot across
    arc(-1, zr + e * r, h0 + r, -Math.PI / 2, -Math.PI);
    for (let i = 1; i < steps; i++) pts.push([-1, zr, h0 + r + (h1 - h0 - 2 * r) * i / steps]);
    arc(-1, zr + e * r, h1 - r, Math.PI, Math.PI / 2);
    arc(1, zl + e * r, h1 - r, Math.PI / 2, Math.PI);
    for (let i = steps - 1; i > 0; i--) pts.push([1, zl, h0 + r + (h1 - h0 - 2 * r) * i / steps]);
    arc(1, zl + e * r, h0 + r, -Math.PI, -Math.PI / 2);
    g.beginPath();
    pts.forEach(([sign, z, h], i) => (i ? g.lineTo : g.moveTo).call(g, X(ringU(h, sign, z)), Y(h)));
    g.closePath();
    g.fillStyle = glass(h0, h1); g.fill();
    g.strokeStyle = COL.rubber; g.lineWidth = 2; g.stroke();
  };
  wrapped(1, 6.22, 6.22, 1.66, LIV.glass[1], 0.07);
  for (const x of [-0.71, 0.71]) { const u = uAt(x, onFace(1, x, REF_H).z); span(u - du(0.014), u + du(0.014), 1.66, LIV.glass[1], '#c9c3b2'); }
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
  wrapped(-1, -6.29, -6.09, 1.70, 2.53, 0.07);
  for (const x of [-0.6, 0.6]) { const u = uAt(x, onFace(-1, x, REF_H).z); span(u - du(0.014), u + du(0.014), 1.70, 2.53, '#c9c3b2'); }
  for (const sign of [-1, 1]) { const c = atCorner(-1, sign, CORNER.r[0] - 0.06), u = uAt(c.x, c.z); span(u - du(0.012), u + du(0.012), 1.70, 2.53, '#c9c3b2'); }
  // the skirt cut out over the bogies (transparent: the material tests the alpha)
  g.save();
  g.globalCompositeOperation = 'destination-out';
  for (const sign of [-1, 1]) for (const zc of [-PIVOT, PIVOT]) {
    // (down to 0.33 m: under the body's edge at 0.35, and 6 rows clear of the roof's part of the texture)
    const w = WHEELBASE / 2, A = CUTOUT.arch, pts = [[zc - w - A, 0.33]];
    for (let i = 0; i <= 12; i++) { const a = Math.PI * (1 - i / 24); pts.push([zc - w + A * Math.cos(a), WHEEL_R + A * Math.sin(a)]); }
    for (let i = 0; i <= 12; i++) { const a = Math.PI * (0.5 - i / 24); pts.push([zc + w + A * Math.cos(a), WHEEL_R + A * Math.sin(a)]); }
    pts.push([zc + w + A, 0.33]);
    g.beginPath();
    pts.forEach(([z, h], i) => (i ? g.lineTo : g.moveTo).call(g, X(sideU(sign, z)), Y(h)));
    g.closePath();
    g.fill();
  }
  // and the ends under the bumper (its underside hides the cut's top; the edges' u from points on the face, as a
  // point ahead of the curved face is nearest to one nearer the middle)
  for (const sign of [1, -1]) {
    const a = uAt(-OPEN, onFace(sign, -OPEN, REF_H).z), b = uAt(OPEN, onFace(sign, OPEN, REF_H).z);
    g.fillRect(X(Math.min(a, b)), Y(LIV.bumper[0] + 0.01), X(Math.abs(b - a)), Y(0.33) - Y(LIV.bumper[0] + 0.01));
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
// front, -1 the rear): its outer face, top and underside, wound like the outline (outwards); the outline is the
// one at height hr (bands of one bumper share it)
function strip(sign, z0, h0, h1, out, color, hr = (h0 + h1) / 2) {
  const pts = ring(hr).filter((p) => sign * p.y >= z0);
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
// Its frame is posed (poseSimple): the bars below, one instance each of a unit bar; the base stays put.
const PANTO = { z: 3.1, x: 0.55, lower: 1.70, upper: 1.75, head: 0.025, base: ROOF + 0.09 };
// the head's rise over the base: lowered, the knees level with the base (the arms' lengths allow no lower);
// raised at most with the arms 0.1 m short of straight
const RISE = { down: Math.sqrt(PANTO.upper ** 2 - PANTO.lower ** 2), up: PANTO.lower + PANTO.upper - 0.1 };
// the collector's top for a contact height over the rail (5 mm under the wire), lowered below its range
export const collectorTop = (h) => PANTO.base + PANTO.head + THREE.MathUtils.clamp(h - 0.005 - PANTO.head - PANTO.base, RISE.down, RISE.up);
// the frame's bars for a contact height h: [from, to, radius, radius upwards, colour]
function pantoBars(h) {
  const rise = collectorTop(h) - PANTO.head - PANTO.base, out = [], c = COL.panto, dark = '#2b2b2b';
  // the knee's height a over the base: lower^2 - a^2 = upper^2 - (rise - a)^2
  const a = (PANTO.lower ** 2 - PANTO.upper ** 2 + rise ** 2) / (2 * rise), dz = Math.sqrt(Math.max(0, PANTO.lower ** 2 - a * a));
  const P = (x, y, z) => [x, PANTO.base + y, PANTO.z + z];
  for (const x of [-PANTO.x, PANTO.x]) {
    for (const s of [-1, 1]) out.push([P(x, 0, 0), P(x, a, s * dz), 0.028, 0.028, c], [P(x, a, s * dz), P(x, rise, 0), 0.022, 0.022, c]);
  }
  for (const s of [-1, 1]) out.push([P(-PANTO.x, a, s * dz), P(PANTO.x, a, s * dz), 0.02, 0.02, c]); // the knees' shafts
  // the collector: its bar across the top (0.1 m deep, 0.05 m high) with the horns turned down, on the frames' tops
  out.push([P(-0.65, rise, 0), P(0.65, rise, 0), 0.05, PANTO.head, dark]);
  for (const s of [-1, 1]) out.push([P(s * 0.65, rise, 0), P(s * 0.92, rise - 0.12, 0), 0.02, 0.02, dark]);
  return out;
}
const PANTO_BARS = pantoBars(5).length;
// the base frame on its insulators
function pantoBase() {
  const out = [part(box(1.3, 0.06, 1.2), '#2e2f30', { at: [0, ROOF + 0.06, PANTO.z] })];
  for (const x of [-0.5, 0.5]) for (const z of [-0.45, 0.45]) out.push(part(new THREE.CylinderGeometry(0.04, 0.05, 0.06, 6), '#8a6a3a', { at: [x, ROOF + 0.03, PANTO.z + z] }));
  return out;
}

// a point of an end's face (sign 1 the front) at (x, h): its z, and the yaw that turns +z to its normal
function onFace(sign, x, h) {
  const k = sign > 0 ? 'f' : 'r', cw = CORNER[k][0];
  return { z: sign * (lerpProfile(NOSE[k], h) - FACE * (x / cw) ** 2), yaw: Math.atan2(2 * FACE * x / cw ** 2, sign) };
}

// The bogie as the user's photos show it (one over the pit, 2026-11-09; one from the side, 2026-11-10): the wheels
// outermost, grey discs with the hub's big hex nut and a boss inside rust-brown tyres, a curved guard inside each
// wheel; between them, over the rail, the track-brake shoe 12 mm up, its upper bar with a row of nuts, hung from the
// side beam at 0.40 m; the ribbed rubber spring in the middle up to the skirt, the gearbox's housing beside it, coil
// springs by the wheels, a brake rod and a lever; all of it a dusty warm grey
const BOGIE_COL = { disc: '#7f7866', hub: '#6d675a', boss: '#78725f', tyre: '#6a4c33', frame: '#77705e', guard: '#5f5a4e', shoe: '#7e7764', rubber: '#4f4a41', rib: '#68625a' };
const sideways = { rot: [0, 0, Math.PI / 2] };
// a wheelset about its axle's middle: the two wheels (the hub's nut, flats on top at rest, shows them turn)
function wheelset() {
  const P = [], C = BOGIE_COL;
  for (const sx of [-1, 1]) {
    P.push(part(new THREE.CylinderGeometry(WHEEL_R, WHEEL_R, 0.1, 28), C.tyre, { at: [sx * 0.75, 0, 0], ...sideways }));
    P.push(part(new THREE.CylinderGeometry(WHEEL_R - 0.06, WHEEL_R - 0.06, 0.104, 28), C.disc, { at: [sx * 0.75, 0, 0], ...sideways }));
    P.push(part(new THREE.CylinderGeometry(0.135, 0.135, 0.03, 6), C.hub, { at: [sx * 0.817, 0, 0], ...sideways }));
    P.push(part(new THREE.CylinderGeometry(0.06, 0.06, 0.03, 14), C.boss, { at: [sx * 0.84, 0, 0], ...sideways }));
    P.push(part(new THREE.CylinderGeometry(0.02, 0.02, 0.02, 6), C.hub, { at: [sx * 0.86, 0, 0], ...sideways }));
  }
  return mergeGeometries(P);
}
// a bogie's frame about its pivot (zc 0), everything but the wheelsets
function bogie(zc = 0) {
  const P = [], C = BOGIE_COL, gap = T3.trackBrakeGap;
  for (const sx of [-1, 1]) {
    for (const dz of [-WHEELBASE / 2, WHEELBASE / 2]) {
      const z = zc + dz, inward = -Math.sign(dz);
      P.push(part(box(0.14, 0.2, 0.22), C.frame, { at: [sx * 0.62, WHEEL_R, z] })); // the axle box, behind the disc
      // the guard: an arc 0.37-0.42 m round the wheel's side towards the middle, from 5 cm over the rail to near its top
      for (let k = 0; k < 6; k++) {
        const step = 125 / 6, a = (-45 + (k + 0.5) * step) * Math.PI / 180, r = WHEEL_R + 0.045;
        P.push(part(box(0.03, 0.05, r * step * Math.PI / 180 + 0.01), C.guard, { at: [sx * 0.69, WHEEL_R + r * Math.sin(a), z + inward * r * Math.cos(a)], rot: [Math.PI / 2 - inward * a, 0, 0] }));
      }
      // a coil spring by the wheel: its rod and coils
      const zs = z + inward * 0.47;
      P.push(part(new THREE.CylinderGeometry(0.022, 0.022, 0.24, 6), C.frame, { at: [sx * 0.64, 0.5, zs] }));
      for (let k = 0; k < 6; k++) P.push(part(new THREE.CylinderGeometry(0.045, 0.045, 0.014, 6), C.guard, { at: [sx * 0.64, 0.41 + k * 0.036, zs] }));
    }
    // the track brake: the shoe 12 mm over the rail, its upper bar with seven nuts, the bracket in its middle and
    // the hangers up to the side beam
    P.push(part(box(0.1, 0.09, 1.1), C.shoe, { at: [sx * 0.75, gap + 0.045, zc] }));
    P.push(part(box(0.07, 0.075, 1.04), C.shoe, { at: [sx * 0.75, gap + 0.1275, zc] }));
    for (let k = -3; k <= 3; k++) P.push(part(new THREE.CylinderGeometry(0.02, 0.02, 0.02, 6), C.hub, { at: [sx * 0.795, gap + 0.1275, zc + k * 0.14], ...sideways }));
    P.push(part(box(0.06, 0.12, 0.16), C.frame, { at: [sx * 0.74, gap + 0.2, zc] }));
    for (const dz of [-0.42, 0.42]) P.push(part(box(0.04, 0.2, 0.05), C.frame, { at: [sx * 0.74, 0.3, zc + dz] }));
    // the side beam, the bracket at its end, the lever and the brake rod
    P.push(part(box(0.14, 0.035, 1.1), C.frame, { at: [sx * 0.66, 0.40, zc - 0.1] }));
    P.push(part(box(0.1, 0.24, 0.08), C.frame, { at: [sx * 0.66, 0.53, zc - 0.68] }));
    P.push(bar([sx * 0.72, 0.36, zc - 0.6], [sx * 0.72, 0.43, zc - 0.05], 0.018, C.frame));
    P.push(bar([sx * 0.73, 0.3, zc + 0.06], [sx * 0.73, 0.68, zc + 0.06], 0.011, C.guard));
    // the rubber spring with its ribs and top plate; the gearbox's housing beside it with its round cover
    P.push(part(new THREE.CylinderGeometry(0.2, 0.2, 0.26, 18), C.rubber, { at: [sx * 0.6, 0.56, zc] }));
    for (const y of [0.47, 0.54, 0.61]) P.push(part(new THREE.CylinderGeometry(0.212, 0.212, 0.02, 18), C.rib, { at: [sx * 0.6, y, zc] }));
    P.push(part(new THREE.CylinderGeometry(0.215, 0.215, 0.025, 18), C.frame, { at: [sx * 0.6, 0.7, zc] }));
    P.push(part(box(0.22, 0.4, 0.26), C.frame, { at: [sx * 0.62, 0.5, zc + 0.36] }));
    P.push(part(new THREE.CylinderGeometry(0.11, 0.11, 0.05, 14), C.shoe, { at: [sx * 0.74, 0.54, zc + 0.36], ...sideways }));
  }
  P.push(part(box(1.4, 0.14, 0.5), C.frame, { at: [0, 0.48, zc] }));
  return mergeGeometries(P);
}

// The mirror (the user's photos of 6921 and 7122): its arm rises from the cap's side over the front door, runs out
// and drops; the route plate hangs on the drop facing forward (src/models.js puts the plate on it), the mirror
// below it, its back to the front. A small mirror on a bracket at the left corner.
const SIDE_INDICATOR = { z: 3.05, h: 1.81 };
// The headlights' centres and the corner units' housings and lenses, from the user's head-on photo of 6892
// (2026-11-10: "check headlight position from this head on shot"), on the scale of the bumper's note (LIV): the
// headlights 1.11 m up (the colour elevation: 1.03 m), 1.08 m apart (the photo 1.11 m; the user: "a tad to far
// apart"), pointing straight ahead in a dark surround with a chrome rim ("they should both point straight", "dark
// accent around them"); the corner units 0.98-1.30 m with the clear (rear: red) lamp just under the headlights'
// line, the indicator over it, round the corners 0.93 m off the centreline (the photo, both ends)
const HEADLIGHT = { x: 0.54, h: 1.11 };
const CORNER_LAMP = { housing: [0.98, 1.30], low: [0.99, 1.14], high: [1.17, 1.29], x: 0.93 };
// the T3M's side display: in the upper part of the right side's second window from the front (the user's photo of 8015)
const SIDE_DISPLAY = { z: 2.29, h: 2.31, w: 1.05, hh: 0.33 };
// the route box on the front cap: its corners square on a T3, rounded on a T3SUCS and round the T3M's display (the
// user, 2026-11-10; 6892 and 7290: 0.49 x 0.30 m, the corners' radius 0.05 m); src/models.js draws it
export const ROUTE_BOX = { w: 0.49, h: 0.30, r: 0.05 };
const ARM = [[-0.86, 2.82, 6.05], [-1.2, 3.02, 6.22], [-1.54, 3.02, 6.28], [-1.62, 2.94, 6.28], [-1.62, 2.3, 6.28]];
const MIRROR_PLATE = [-1.62, 2.52, 6.31];

// the parts that never move (the running gear and the pantograph's frame are posed: gearShapes)
function partsGeometry(variant) {
  const P = [], dark = '#2c2d2e';
  // under the body: the equipment's lower edge between the bogies, the floor's underside, the door steps
  P.push(part(box(2.0, 0.07, 3.6), dark, { at: [0, BOTTOM - 0.035, 0] }));
  P.push(part(cap(ring(BOTTOM), BOTTOM, -1), dark));
  for (const [z0, z1] of DOORS) {
    const xa = sideX(-1, z0), xb = sideX(-1, z1);
    P.push(part(box(0.24, 0.05, Math.hypot(xb - xa, z1 - z0) - 0.06), COL.step, { at: [(xa + xb) / 2 + 0.1, BOTTOM - 0.03, (z0 + z1) / 2], rot: [0, Math.atan2(xb - xa, z1 - z0), 0] }));
  }
  // the ends: the bumper round the end back to the doors (a T3's silver with two thin red stripes, 12 mm a
  // quarter of the bumper in from its edges as on 6892, the others' brown), the underframe's end dark behind
  // the opening under it, the coupler's gear
  const [b0, b1] = LIV.bumper, bh = b1 - b0;
  const bands = variant === 'T3'
    ? [[0, 0.115, COL.silver], [0.115, 0.23, COL.red], [0.23, 0.77, COL.silver], [0.77, 0.885, COL.red], [0.885, 1, COL.silver]]
    : [[0, 1, COL.bumper]];
  for (const sign of [1, -1]) {
    for (const [t0, t1, c] of bands) P.push(strip(sign, 6.05, b0 + t0 * bh, b0 + t1 * bh, 0.05, c, b0 + bh / 2));
    const zf = sign * lerpProfile(NOSE[sign > 0 ? 'f' : 'r'], 0.4);
    // (behind the opening, wider than it: the skirt's corners from inside are not drawn; 3 cm inside the face at
    // its foot, where it is furthest back, so its corners do not come through the skirt)
    P.push(part(box(2 * OPEN + 0.1, b0 + 0.04 - BOTTOM, 0.04), '#262422', { at: [0, (BOTTOM + b0 + 0.04) / 2, sign * (Math.abs(onFace(sign, OPEN + 0.05, BOTTOM).z) - 0.05)] }));
    P.push(part(box(0.8, 0.12, 0.25), '#2a2a2a', { at: [0, 0.26, zf - sign * 0.5] }));
  }
  // behind each bogie's cutouts, a dark panel down the middle (the cutouts do not show through the car)
  for (const zc of [-PIVOT, PIVOT]) P.push(part(box(0.02, CUTOUT.top - BOTTOM + 0.06, 2 * CUTOUT.half), '#2e2a26', { at: [0, (CUTOUT.top + BOTTOM) / 2, zc] }));
  // the headlights' surrounds, dark, pointing straight ahead (reaching back into the curved face), a chrome rim
  for (const x of [-HEADLIGHT.x, HEADLIGHT.x]) {
    const front = onFace(1, x, HEADLIGHT.h).z + 0.035, ahead = { rot: [Math.PI / 2, 0, 0] };
    P.push(part(new THREE.CylinderGeometry(0.125, 0.13, 0.11, 20), '#1b1b1b', { at: [x, HEADLIGHT.h, front - 0.055], ...ahead }));
    P.push(part(new THREE.CircleGeometry(0.098, 20), '#aeb1b3', { at: [x, HEADLIGHT.h, front + 0.001] }));
  }
  // the lamp units' housings round the corners, the side indicators' on the pillar amidships
  for (const end of [1, -1]) for (const sign of [-1, 1]) {
    const c = atCorner(end, sign, CORNER_LAMP.x), [h0, h1] = CORNER_LAMP.housing;
    P.push(part(box(0.02, h1 - h0, 0.095), '#262626', { at: [c.x + c.n[0] * 0.008, (h0 + h1) / 2, c.z + c.n[1] * 0.008], rot: [0, c.yaw, 0] }));
  }
  for (const sign of [-1, 1]) P.push(part(box(0.016, 0.135, 0.08), '#262626', { at: [sign * (HW + 0.006), SIDE_INDICATOR.h, SIDE_INDICATOR.z] }));
  // the roof (the colour elevation): three hatches, a low cover behind the pantograph, a box amidships, the
  // aerial on the front cap, the pantograph's base; on a T3M the resistors' box towards the rear (the user's photos
  // of 8080 and 8088: "Box on top with resistors towards back only for t3m")
  for (const z of [-5.2, -0.78, 4.69]) P.push(part(box(0.62, 0.06, 1.05), '#7c8084', { at: [0, ROOF + 0.03, z] }));
  P.push(part(box(0.9, 0.05, 1.45), '#5c6064', { at: [0, ROOF + 0.025, 1.7] }));
  P.push(part(box(0.5, 0.12, 0.5), '#5c6064', { at: [0, ROOF + 0.06, 0.18] }));
  if (variant === 'T3M') { // (short but wide, its top a grille: the user, 2026-11-09, and a model of an 8xxx)
    P.push(part(box(1.4, 0.2, 0.85), '#45484b', { at: [0, ROOF + 0.1, -3.0] }));
    for (let k = 0; k < 8; k++) P.push(part(box(1.32, 0.02, 0.05), '#5d6164', { at: [0, ROOF + 0.205, -3.35 + 0.1 * k] }));
  }
  P.push(bar([0, ROOF - 0.05, 5.68], [0, ROOF + 0.24, 5.68], 0.015, '#8a8d90'), bar([0, ROOF + 0.24, 5.55], [0, ROOF + 0.24, 5.81], 0.012, '#8a8d90'));
  P.push(...pantoBase());
  for (let i = 1; i < ARM.length; i++) P.push(bar(ARM[i - 1], ARM[i], 0.02, '#8a8d90'));
  P.push(part(box(0.22, 0.38, 0.05), '#1c1c1c', { at: [-1.66, 2.2, 6.24] })); // (its top behind the plate)
  const lm = atCorner(1, 1, 0.98); // (the small mirror's bracket from the corner, just behind the windscreen's wrap)
  P.push(bar([lm.x - 0.02, 1.72, lm.z], [lm.x + 0.18, 1.8, lm.z - 0.06], 0.012, '#8a8d90'), part(box(0.05, 0.18, 0.11), '#1c1c1c', { at: [lm.x + 0.2, 1.9, lm.z - 0.08] }));
  return mergeGeometries(P);
}

// The coupler (the user's picture of a T3's, 2026-11-10: "something like the attached image, only dark"): a round
// bar from the yoke's pin under the body end (T3.couplerPivot) to a clamp, the head cast in one with a neck, its
// mouth two jaws with the coupling pin down through them and its handle on top; the jaws' faces at the plane
// where two coupled heads meet. Built as the front one about its pin (the yoke's): posed on either end (gear)
function coupler() {
  const C = [], sign = 1, z = (d) => COUPLER_FACE - T3.couplerPivot - d, y = 0, bar0 = '#2f3133', cast = '#28292b', along = { rot: [Math.PI / 2, 0, 0] };
  C.push(bar([0, y, 0], [0, y, z(0.52)], 0.034, bar0));
  C.push(part(new THREE.CylinderGeometry(0.056, 0.056, 0.11, 12), '#36383a', { at: [0, y, z(0.47)], ...along })); // the clamp
  for (const s of [-1, 1]) C.push(part(box(0.03, 0.035, 0.09), '#36383a', { at: [s * 0.07, y + 0.035, z(0.47)] })); // its bolts' lugs
  // the neck widening from the clamp into the head: a square frustum, flattened to the head's height
  C.push(part(new THREE.CylinderGeometry(0.165 / Math.SQRT2, 0.075 / Math.SQRT2, 0.16, 4).rotateY(Math.PI / 4), cast, { at: [0, y, z(0.34)], rot: [sign * Math.PI / 2, 0, 0], scale: [1, 1, 0.76] }));
  C.push(part(box(0.165, 0.125, 0.2), cast, { at: [0, y, z(0.2)] })); // the head
  for (const s of [-1, 1]) C.push(part(box(0.05, 0.125, 0.1), cast, { at: [s * 0.0575, y, z(0.05)] })); // the jaws
  C.push(part(box(0.065, 0.03, 0.1), cast, { at: [0, y - 0.0475, z(0.05)] })); // the mouth's floor
  C.push(part(new THREE.CylinderGeometry(0.017, 0.017, 0.2, 8), '#3a3c3e', { at: [0, y + 0.02, z(0.06)] })); // the pin
  C.push(bar([-0.045, y + 0.12, z(0.06)], [0.045, y + 0.12, z(0.06)], 0.009, '#3a3c3e'));
  for (const s of [-1, 1]) C.push(bar([s * 0.045, y + 0.12, z(0.06)], [s * 0.03, y + 0.07, z(0.06)], 0.009, '#3a3c3e')); // the handle
  for (const s of [-1, 1]) C.push(part(new THREE.CylinderGeometry(0.03, 0.03, 0.015, 10), '#3a3c3e', { at: [s * 0.0835, y, z(0.2)], rot: [0, 0, Math.PI / 2] })); // the side bosses
  return mergeGeometries(C);
}

// The lamps: the round headlights; rectangular units by the corners, an orange indicator over a clear
// lamp at the front and over a red one at the rear (the user, 2026-11-09: "round or rectangle, I would choose
// the latter"); on the rear face two red lamps and the white one between them, the round red reflectors under
// the bumper (the photos of 6892 and 6921). By function (the user, 2026-11-10, #436): the front corners' clear
// lamps are the position lamps, the rear corners' red ones the brake lamps ("as on the hybrid"), the rear face's
// red pair the tail lamps, the white one between them the reversing lamp. Each part is tagged with its function
// (geometry.userData.lamps: vertex ranges in merge order); a car lights them by its colours (setLamps).
function lampsGeometry() {
  const L = [], fns = [];
  const add = (fn, g) => { L.push(g); fns.push(fn); };
  const side = (sign) => (sign > 0 ? 'indL' : 'indR'); // (x left)
  for (const x of [-HEADLIGHT.x, HEADLIGHT.x]) {
    add('head', part(new THREE.CircleGeometry(0.085, 18), COL.lamp, { at: [x, HEADLIGHT.h, onFace(1, x, HEADLIGHT.h).z + 0.038] }));
  }
  for (const [end, low, fn] of [[1, '#f2efe4', 'pos'], [-1, '#d8261a', 'brake']]) for (const sign of [-1, 1]) {
    const c = atCorner(end, sign, CORNER_LAMP.x), at = (h) => [c.x + c.n[0] * 0.02, h, c.z + c.n[1] * 0.02], { high: [a0, a1], low: [c0, c1] } = CORNER_LAMP;
    add(side(sign), part(box(0.012, a1 - a0, 0.075), '#ff9a22', { at: at((a0 + a1) / 2), rot: [0, c.yaw, 0] }));
    add(fn, part(box(0.012, c1 - c0, 0.075), low, { at: at((c0 + c1) / 2), rot: [0, c.yaw, 0] }));
  }
  const onRear = (fn, x, h, w, hh, color) => {
    const f = onFace(-1, x, h);
    add(fn, part(box(w, hh, 0.02), color, { at: [x + 0.012 * Math.sin(f.yaw), h, f.z + 0.012 * Math.cos(f.yaw)], rot: [0, f.yaw, 0] }));
  };
  // the side indicators: on the pillar between the first and second windows on the right, the second and third on
  // the left (both 3.05 m ahead of the centre), at the window band's foot (the user's photos of 8015 and 8080)
  for (const sign of [-1, 1]) add(side(sign), part(box(0.012, 0.11, 0.06), '#ff9a22', { at: [sign * (HW + 0.016), SIDE_INDICATOR.h, SIDE_INDICATOR.z] }));
  for (const x of [-0.47, 0.47]) onRear('tail', x, 0.95, 0.2, 0.07, '#d8261a');
  onRear('rev', 0, 0.95, 0.16, 0.055, '#f4f4ee');
  for (const x of [-0.66, 0.66]) {
    const f = onFace(-1, x, 0.6);
    add('refl', part(new THREE.CircleGeometry(0.045, 14), '#c41e14', { at: [x + 0.008 * Math.sin(f.yaw), 0.6, f.z + 0.008 * Math.cos(f.yaw)], rot: [0, f.yaw, 0] }));
  }
  const g = mergeGeometries(L);
  let at = 0;
  g.userData.lamps = L.map((p, i) => { const n = p.attributes.position.count, r = { fn: fns[i], start: at, count: n }; at += n; return r; });
  return g;
}

// A car's lamps: its own copy of the lamps' colours, each function lit or dimmed to LAMP_DIM of its colour when
// its state changes. A lamp off shows its lens, darker; the reflectors are not lamps and stay as they are.
const LAMP_DIM = 0.2;
// a lamp lit at twice its colour, not tone mapped: as bright as the hybrid's glows (the user, 2026-11-10: "The hybrid
// model's light are brighter")
const LAMP_LIT = 2;
function carLamps(shared) {
  const geo = shared.clone(), lit = shared.attributes.color.array, byFn = {};
  geo.userData = {}; // (its own: disposeModel frees it; clone shares the userData)
  for (const r of shared.userData.lamps) (byFn[r.fn] ||= []).push(r);
  delete byFn.refl;
  return { geo, lit, byFn, on: {} };
}
function setLamps(lp, want) {
  const C = lp.geo.attributes.color;
  let dirty = false;
  for (const [fn, ranges] of Object.entries(lp.byFn)) {
    const on = !!want[fn];
    if (lp.on[fn] === on) continue;
    lp.on[fn] = on;
    dirty = true;
    const k = on ? LAMP_LIT : LAMP_DIM;
    for (const { start, count } of ranges) for (let i = start * 3; i < (start + count) * 3; i++) C.array[i] = lp.lit[i] * k;
  }
  if (dirty) C.needsUpdate = true;
}
// the lamps of car k wanted for the set's state: the front end lit on the leading car only, the rear end's red lamps
// on every car (the user, 2026-11-10, with a photo of 8088 coupled behind another: "in between cars only the rear red
// lights light up"), the indicators on every car
function lampsWanted(k, { braking = false, signals = {} } = {}) {
  const lead = k === 0;
  return { head: lead, pos: lead, tail: true, brake: braking, rev: false, indL: !!signals.left, indR: !!signals.right };
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
// logos"), its digits 0.14 m tall on every side (the user, 2026-11-10: "same size in all sides"). Measured on the
// photos (the red band's heights as the scale): 0.13-0.15 m on the fronts of 8080, 0.14 m on the sides of 8015
// and 8080; conflig's model 0.146 m on its ends, 0.13 m on its sides. Placed as on the photos:
// - front: between the headlights, centred on them;
// - rear: centred over the white lamp, its foot 5 cm over the lamps' tops (8088, 6921);
// - sides: the top 0.12 m under the red's top; on the right under the first window behind the front door,
//   ending 0.35 m before it (8015, 8080), on the left under the first window's front behind the cab window
//   (8080), both 4.17 m ahead of the centre (conflig's: 4.15 and 4.17 m, its digits 1.35-1.50 m).
const FLEET = { h: 0.14, front: HEADLIGHT.h, rear: 1.105, side: { z: 4.17, h: 1.43 } };
// the canvas: the digits FLEET_PX.h px tall in a 512 x 160 px texture, so the quads are FLEET.h * 160 / 120 tall
const FLEET_PX = { w: 480, h: 120 }, FLEET_QH = (FLEET.h * 160) / FLEET_PX.h, FLEET_QW = (FLEET_QH * 512) / 160;
function fleetTexture(n) {
  const cv = document.createElement('canvas');
  cv.width = 512; cv.height = 160;
  const g = cv.getContext('2d'), s = n == null ? '' : String(n);
  if (!s) return new THREE.CanvasTexture(cv); // (a vehicle without fleet numbers for this type)
  // (the hybrid's font and colour, src/t3h.js fleetTexture: the user, 2026-11-10, "the new model uses different font
  // from the hybrid model and my photos")
  g.fillStyle = '#e3b625';
  g.font = 'bold 100px Arial, sans-serif';
  // the digits' own box scaled to FLEET_PX.h, whichever font the system has (squeezed only past FLEET_PX.w)
  const m = g.measureText(s), L = m.actualBoundingBoxLeft, R = m.actualBoundingBoxRight, A = m.actualBoundingBoxAscent, D = m.actualBoundingBoxDescent;
  const k = FLEET_PX.h / (A + D), kx = Math.min(k, FLEET_PX.w / (L + R));
  g.setTransform(kx, 0, 0, k, 256 - (kx * (R - L)) / 2, 80 - (k * (D - A)) / 2);
  g.fillText(s, 0, 0);
  const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

let SHAPES = null;
const PARTS = new Map();
function shapes(variant) {
  if (!SHAPES) {
    const body = bodyGeometry(), lamps = lampsGeometry();
    const probe = new THREE.Mesh(body);
    probe.updateMatrixWorld(true);
    // Prague's plates and cards (src/models.js): the route number in the box on the front's brow (0.49 x 0.30 m,
    // 6892 and 7290; its foot 3 cm over the brow's lower edge, the user, 2026-11-10: "adjust the line plate to sit
    // lower, near the edge") and on the mirror arm (smaller, taller than wide), the
    // destination and the run number resting on the windscreen's lower edge (the user, 2026-11-09: "closer to
    // the bottom glass border"), the run number on the pane right of the post (left as seen from the front), the
    // route inverted in the rear window
    const plates = {
      rb: onBody(probe, 0, 2.59 + ROUTE_BOX.h / 2, 1, ROUTE_BOX.w, ROUTE_BOX.h), mir: new THREE.PlaneGeometry(0.22, 0.28).translate(...MIRROR_PLATE),
      dest: onBody(probe, -0.02, 1.77, 1, 0.46, 0.19), run: onBody(probe, -0.8, 1.725, 1, 0.12, 0.09), rear: onBody(probe, 0, 1.90, -1, 0.34, 0.3),
      led: onFlank(-1, SIDE_DISPLAY.z, SIDE_DISPLAY.h, SIDE_DISPLAY.w, SIDE_DISPLAY.hh),
    };
    const fleet = mergeGeometries([onFaceStrip(1, FLEET.front, FLEET_QW, FLEET_QH), onFaceStrip(-1, FLEET.rear, FLEET_QW, FLEET_QH),
      ...[-1, 1].map((sign) => onFlank(sign, FLEET.side.z, FLEET.side.h, FLEET_QW, FLEET_QH))]);
    // the posed parts, one instance each: a bogie's frame, a wheelset, a coupler, a unit bar of the pantograph's
    // frame (white: its instances' colours)
    const gear = { bogie: bogie(), wheels: wheelset(), coupler: coupler(), bar: part(new THREE.CylinderGeometry(1, 1, 1, 6), '#ffffff') };
    for (const g of [body, lamps, fleet, ...Object.values(plates), ...Object.values(gear)]) if (g) g.userData.shared = true;
    SHAPES = { body, lamps, plates, fleet, gear, livery: livery() };
  }
  if (!PARTS.has(variant)) { const g = partsGeometry(variant); g.userData.shared = true; PARTS.set(variant, g); }
  return { ...SHAPES, parts: PARTS.get(variant) };
}

// ------------------------------------------------------------------------------------- the running gear
// A car's moving parts are instances in its frame (src/consist.js poses them through car.userData.gear): the two
// bogies' frames, turned about their pivots; the four wheelsets in them, rolled; the two couplers, swung about
// their pins; the pantograph's bars (poseSimple). A car draws 8 meshes besides its plates.
const _m = new THREE.Matrix4(), _w = new THREE.Matrix4(), _e = new THREE.Euler(0, 0, 0, 'YXZ');
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _x = new THREE.Vector3(), _y = new THREE.Vector3(), _z = new THREE.Vector3(), _up = new THREE.Vector3(0, 1, 0);
// (the instances move within the car: a sphere round all of it, so three culls them with the car)
const CAR_SPHERE = new THREE.Sphere(new THREE.Vector3(0, 2.0, 0), 8.2);

function instanced(geo, mat, n, name) {
  const o = new THREE.InstancedMesh(geo, mat, n);
  o.name = name;
  o.boundingSphere = CAR_SPHERE.clone();
  o.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  return o;
}

// a car's gear: its state, written into the instances in done() when it changed
function carGear(meshes) {
  const st = { yaw: [0, 0], s: 0, dir: [[0, 0], [0, 0]] }, eps = 1e-5;
  let dirty = true;
  const set = (v, k, x) => { if (Math.abs(v[k] - x) > eps) { v[k] = x; dirty = true; } };
  return {
    axle: WHEELBASE / 2, pinY: COUPLER_H, live: () => true, state: st,
    turn(i, d) { set(st.yaw, i, d); },
    roll(s) { if (Math.abs(s - st.s) > 1e-4) { st.s = s; dirty = true; } },
    // a coupler's yaw (+ to the left of its own end's straight ahead) and pitch (+ up) from its outward direction
    swing(i, q) {
      const out = i === 0 ? 1 : -1;
      set(st.dir[i], 0, q ? Math.atan2(out * q.x, out * q.z) : 0);
      set(st.dir[i], 1, q ? Math.atan2(q.y, Math.hypot(q.x, q.z)) : 0);
    },
    done() {
      if (!dirty) return;
      dirty = false;
      const turn = st.s / WHEEL_R; // (rolling forwards: the wheel's top to +z, about +x)
      for (let i = 0; i < 2; i++) {
        const out = i === 0 ? 1 : -1;
        _m.makeRotationY(st.yaw[i]).setPosition(0, 0, out * PIVOT);
        meshes.bogies.setMatrixAt(i, _m);
        for (let j = 0; j < 2; j++) {
          _w.makeRotationX(turn).setPosition(0, WHEEL_R, (j === 0 ? 1 : -1) * WHEELBASE / 2);
          meshes.wheels.setMatrixAt(2 * i + j, _w.premultiply(_m));
        }
        // the coupler is built as the front one: the rear one turned round
        _e.set(-st.dir[i][1], st.dir[i][0] + (out > 0 ? 0 : Math.PI), 0);
        _m.makeRotationFromEuler(_e).setPosition(0, COUPLER_H, out * T3.couplerPivot);
        meshes.couplers.setMatrixAt(i, _m);
      }
      for (const o of [meshes.bogies, meshes.wheels, meshes.couplers]) o.instanceMatrix.needsUpdate = true;
    },
  };
}

// the pantograph's bars for a contact height h over the rail: each a unit bar from a to b, r its radius across
// (horizontal), ru upwards (the hexagon's corner up: the collector's top ru over its middle)
function posePanto(mesh, h) {
  pantoBars(h).forEach(([a, b, r, ru], i) => {
    _a.set(...a); _b.set(...b);
    _y.subVectors(_b, _a);
    const len = _y.length();
    _y.divideScalar(len);
    _z.copy(_up).addScaledVector(_y, -_up.dot(_y));
    if (_z.lengthSq() < 1e-8) _z.set(1, 0, 0); else _z.normalize();
    _x.crossVectors(_y, _z);
    _m.makeBasis(_x.multiplyScalar(r), _y.multiplyScalar(len), _z.multiplyScalar(ru)).setPosition(_a.add(_b).multiplyScalar(0.5));
    mesh.setMatrixAt(i, _m);
  });
  mesh.instanceMatrix.needsUpdate = true;
}

// The built-in car's state (src/models.js poseT3), each only when it changes: the collector's contact height
// over the rail (below its working range it lies lowered); the lamps: the brake lamps while braking, the
// indicators' sides lit now (`signals`: { left, right }), the high beams' glow on the leading car
export function poseSimple(model, { collector, braking, signals, highBeam } = {}) {
  const { cars } = model.userData, st = model.userData.lampState;
  if (braking !== undefined) st.braking = braking;
  if (signals !== undefined) st.signals = signals;
  cars.forEach((car, k) => {
    const p = car.userData.panto;
    if (collector !== undefined && Math.abs(collector - p.h) > 1e-3) { p.h = collector; posePanto(p.mesh, collector); }
    setLamps(car.userData.lamps, lampsWanted(k, st));
    if (highBeam !== undefined && car.userData.beams) car.userData.beams.visible = !!highBeam;
  });
}

// A set of `cars` built-in T3s in `root` (src/models.js makeT3): `mats` holds the plates' materials
// (route box, mirror plate, rear plate, destination and run cards), which setConsistLine swaps; `variant`
// 'T3', 'T3SUCS' or 'T3M' (its manifest's variants, assets/t3simple/vehicle.json), `fleet` the cars' numbers; the
// collector on the wire `wire` m over the rail.
export function makeSimpleSet(root, cars, dest, mats, wire, { variant = 'T3SUCS', fleet = Array(cars).fill(null) } = {}) {
  const P = shapes(variant);
  // each set owns its materials (traffic fades them one set at a time); the shapes and the livery are shared
  Object.assign(mats, {
    body: new THREE.MeshLambertMaterial({ map: P.livery, alphaTest: 0.5 }), // (the alpha: the skirt's cutouts)
    parts: new THREE.MeshLambertMaterial({ vertexColors: true }),
    lamps: new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false }),
  });
  Object.assign(root.userData, { mats, bogie: PIVOT, bodyFront: BODY_FRONT, cars: [], variant, fleet, lampState: { braking: false, signals: {} } });
  const colours = pantoBars(wire).map((b) => new THREE.Color(b[4]));
  for (let k = 0; k < cars; k++) {
    const car = new THREE.Group();
    car.rotation.order = 'YXZ';
    const mesh = (g, m, name) => { if (g) { const o = new THREE.Mesh(g, m); o.name = name; car.add(o); } };
    mesh(P.body, mats.body, 'body');
    mesh(P.parts, mats.parts, 'parts');
    const lamps = carLamps(P.lamps);
    mesh(lamps.geo, mats.lamps, 'lamps');
    setLamps(lamps, lampsWanted(k, root.userData.lampState)); // (in service: the ends' lamps lit)
    car.userData.lamps = lamps;
    // the high beams' glow over the leading car's headlights (drawn only while they are on)
    if (k === 0) {
      car.userData.beams = beamsMesh([-HEADLIGHT.x, HEADLIGHT.x].map((x) => [x, HEADLIGHT.h, onFace(1, x, HEADLIGHT.h).z + 0.05]));
      car.add(car.userData.beams);
    }
    // (a decal blended at its edges: traffic's fade keeps a blended material blended)
    const fm = new THREE.MeshLambertMaterial({ map: fleetTexture(fleet[k]), transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
    mesh(P.fleet, fm, 'fleet');
    const gm = { bogies: instanced(P.gear.bogie, mats.parts, 2, 'bogies'), wheels: instanced(P.gear.wheels, mats.parts, 4, 'wheels'),
      couplers: instanced(P.gear.coupler, mats.parts, 2, 'couplers'), panto: instanced(P.gear.bar, mats.parts, PANTO_BARS, 'pantograph') };
    for (const o of Object.values(gm)) car.add(o);
    colours.forEach((c, i) => gm.panto.setColorAt(i, c));
    car.userData.gear = carGear(gm);
    car.userData.gear.done(); // (square, at rest)
    car.userData.panto = { mesh: gm.panto, h: wire };
    posePanto(gm.panto, wire);
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
