// SPDX-License-Identifier: AGPL-3.0-or-later
// Original T3 geometry, metres, rail plane y=0, forward +z, doors on -x.
// Dimensioned drawing and photo references: assets/t3photo/README.md (#437).
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

export const T3_PHOTO = Object.freeze({ length: 14, width: 2.5, roof: 3.06,
  bogieCentres: 6.4, axleSpacing: 1.9, wheelDiameter: .7, gauge: 1.435,
  overCouplers: 15.104, floor: .874, entryFloor: .39, doorMaxAngle: 84 * Math.PI / 180,
  seats: 24, doors: [5.3, -.75, -5.3] });

const V = (x, y, z) => new THREE.Vector3(x, y, z);
const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
function group(parent, name, x = 0, y = 0, z = 0) {
  const g = new THREE.Group(); g.name = name; g.position.set(x, y, z); parent.add(g); return g;
}
function mesh(parent, name, geometry, material, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(geometry, material); m.name = name; m.position.set(x, y, z);
  m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
}
function box(p, name, size, pos, mat) { return mesh(p, name, new THREE.BoxGeometry(...size), mat, ...pos); }
function rod(p, name, a, b, r, mat, sides = 10) {
  const d = b.clone().sub(a), m = mesh(p, name, new THREE.CylinderGeometry(r, r, d.length(), sides), mat);
  m.position.copy(a).add(b).multiplyScalar(.5); m.quaternion.setFromUnitVectors(V(0, 1, 0), d.normalize()); return m;
}
function rr(x, y, w, h, r) {
  const s = new THREE.Shape(); r = Math.min(r, w / 2, h / 2);
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y); return s;
}
function plate(p, name, shape, mat, x, y, z, ry = 0) {
  const m = mesh(p, name, new THREE.ShapeGeometry(shape, 10), mat, x, y, z); m.rotation.y = ry; return m;
}
function tube(p, name, points, radius, mat, closed = false) {
  const path = new THREE.CatmullRomCurve3(points, closed, 'centripetal');
  return mesh(p, name, new THREE.TubeGeometry(path, Math.min(128, Math.max(16, Math.ceil(points.length * 1.5))), radius, 6, closed), mat);
}
function rim(p, name, shape, mat, position, ry = 0, radius = .013) {
  const g = group(p, name, ...position); g.rotation.y = ry;
  tube(g, name + '_seal', shape.getPoints(8).map(q => V(q.x, q.y, 0)), radius, mat, true); return g;
}
function surface(p, name, rows, mat) {
  const pos = [], idx = [], uv = [], n = rows[0].length;
  rows.forEach((row, j) => row.forEach((v, i) => { pos.push(...v); uv.push(i / (n - 1), j / (rows.length - 1)); }));
  for (let j = 0; j < rows.length - 1; j++) for (let i = 0; i < n - 1; i++) {
    const a = j * n + i, b = a + n; idx.push(a, b, a + 1, b, b + 1, a + 1);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2)); g.setIndex(idx); g.computeVertexNormals();
  return mesh(p, name, g, mat);
}
// Batch only within a rigid assembly. Named articulation groups keep their local pivots.
function batch(root) {
  for (const c of [...root.children]) if (c.isGroup) batch(c);
  for (const c of [...root.children]) if (c.isGroup && !c.userData.assembly) {
    c.updateMatrix();
    for (const o of [...c.children]) {
      o.updateMatrix(); o.matrix.premultiply(c.matrix);
      o.matrix.decompose(o.position, o.quaternion, o.scale); root.add(o);
    }
    root.remove(c);
  }
  const byMat = new Map();
  for (const o of [...root.children]) if (o.isMesh && !o.userData.keep) {
    o.updateMatrix(); const g = o.geometry.clone().applyMatrix4(o.matrix);
    const flat = g.index ? g.toNonIndexed() : g;
    for (const a of Object.keys(flat.attributes)) if (!['position', 'normal', 'uv'].includes(a)) flat.deleteAttribute(a);
    if (!flat.attributes.uv) flat.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(flat.attributes.position.count * 2), 2));
    if (!byMat.has(o.material)) byMat.set(o.material, []); byMat.get(o.material).push(flat);
    root.remove(o); o.geometry.dispose(); if (g !== flat) g.dispose();
  }
  for (const [mat, parts] of byMat) {
    const g = mergeGeometries(parts, false), indexed = mergeVertices(g, 1e-5);
    parts.forEach(x => x.dispose()); g.dispose();
    mesh(root, root.name + '_' + mat.name, indexed, mat);
  }
}

export function makePhotoT3({ fleet = '6892', line = '23', destination = 'BŘEVNOV\nKRÁLOVKA' } = {}) {
  const root = new THREE.Group(); root.name = 'Tatra_T3_6892';
  root.userData = { asset: 'Original photo-based Tatra T3', units: 'metres', forward: '+Z', up: '+Y',
    railPlane: 0, licence: 'AGPL-3.0-or-later', dimensions: { ...T3_PHOTO }, reference: 'assets/t3photo/README.md' };
  const material = (name, color, roughness = .5, metalness = 0, extra = {}) => {
    const m = new THREE.MeshStandardMaterial({ color, roughness, metalness, side: THREE.DoubleSide, ...extra });
    m.name = name; return m;
  };
  const cream = material('Ivory_enamel', '#dfd6b9', .32), red = material('Prague_red_enamel', '#ac1e29', .3);
  const roofMat = material('Roof_grey', '#565653', .75), rubber = material('Rubber', '#171c1d', .84);
  const steel = material('Steel', '#525b60', .42, .75), chrome = material('Aluminium', '#b4b8b6', .28, .75);
  const dark = material('Underframe', '#303737', .77, .3), floorMat = material('Floor', '#ffffff', .92);
  const glass = material('Window_glass', '#729293', .12, .28, { transparent: true, opacity: .57, depthWrite: false });
  const seatMat = material('Red_seat_cushion', '#ae3436', .62), poleMat = material('Handrails', '#a3a7a5', .46, .45);
  const wallMat = material('Interior_laminate', '#bc9f94', .84);
  // Small repeatable rubber ribs, with metre-based UVs shared by the floor and stair blocks.
  const floorCanvas = document.createElement('canvas'); floorCanvas.width = floorCanvas.height = 64;
  const floorCtx = floorCanvas.getContext('2d');
  floorCtx.fillStyle = '#353833'; floorCtx.fillRect(0, 0, 64, 64);
  for (let x = 0; x < 64; x += 8) {
    floorCtx.fillStyle = '#202420'; floorCtx.fillRect(x, 0, 2, 64);
    floorCtx.fillStyle = '#50514a'; floorCtx.fillRect(x + 2, 0, 2, 64);
  }
  floorMat.map = new THREE.CanvasTexture(floorCanvas); floorMat.map.name = 'Ribbed_rubber';
  floorMat.map.colorSpace = THREE.SRGBColorSpace;
  floorMat.map.wrapS = floorMat.map.wrapT = THREE.RepeatWrapping;
  floorMat.map.anisotropy = 8;
  const floorBox = (name, size, pos) => {
    const m = box(cabin, name, size, pos, floorMat), a = m.geometry.attributes.position, uv = m.geometry.attributes.uv;
    for (let i = 0; i < a.count; i++) uv.setXY(i, (a.getX(i) + pos[0]) / .064, (a.getZ(i) + pos[2]) / .064);
    return m;
  };
  const wheelMat = material('Wheel_brown_dust', '#665044', .88, .2);
  const treadMat = material('Wheel_running_tread', '#817568', .54, .55);
  const casting = material('Coupler_cast_steel', '#737b7b', .66, .48);
  const orange = material('Collector_orange', '#cc522a', .44, .25);
  const lamp = material('Headlight_lens', '#eee6ce', .2, .12, { emissive: '#ffcb79', emissiveIntensity: .55 });
  const tail = material('Tail_lens', '#a91618', .3, 0, { emissive: '#b31111', emissiveIntensity: .2 });
  const amber = material('Indicator_lens', '#d47b20', .32);
  const body = group(root, 'Body'), cabin = group(body, 'Interior'), detail = group(body, 'Exterior_details');
  const rig = { doors: [], bogies: [], wheelsets: [], couplers: [], wipers: [], pantograph: null };

  // Side walls are actual openings, with wheel recesses cut out of the lower skirt.
  const leftWindows = [-5.18, -3.70, -2.22, -.74, .74, 2.22, 3.70, 5.18];
  const rightWindows = [-3.78, -2.29, .74, 2.22, 3.70];
  for (const side of [-1, 1]) {
    const ry = side * Math.PI / 2, sx = side * 1.25;
    // At -x, local horizontal coordinate is +z; at +x it is -z.
    const u = z => -side * z, windows = side < 0 ? rightWindows : leftWindows;
    for (const [lo, hi, mat] of [[.28, .85, cream], [.85, 1.66, red], [1.66, 2.74, cream]]) {
      const cuts = side < 0 ? T3_PHOTO.doors.map(z => [u(z) - .70, u(z) + .70]).sort((a, b) => a[0] - b[0]) : [];
      let start = -5.99;
      for (const [a, b] of [...cuts, [5.99, 5.99]]) {
        if (a <= start) { start = Math.max(start, b); continue; }
        let s = rr(start, lo, a - start, hi - lo, .002);
        if (lo < .8) {
          // A wheel recess is part of the perimeter, never a hole crossing its boundary.
          s = new THREE.Shape(); s.moveTo(start, lo);
          for (const c of [-3.2, 3.2]) {
            const l = c - 1.38, r = c + 1.38, top = .76;
            if (l < start || r > a) continue;
            s.lineTo(l, lo); s.lineTo(l, top - .12);
            s.quadraticCurveTo(l, top, l + .12, top); s.lineTo(r - .12, top);
            s.quadraticCurveTo(r, top, r, top - .12); s.lineTo(r, lo);
          }
          s.lineTo(a, lo); s.lineTo(a, hi); s.lineTo(start, hi); s.closePath();
        }
        if (lo > 1.6) for (const z of windows) {
          const c = u(z); if (c > start && c < a) s.holes.push(rr(c - .67, 1.75, 1.34, .88, .085));
        }
        plate(body, 'Side_wall', s, mat, sx, 0, 0, ry); start = b;
        if (lo === .85) plate(cabin, 'Interior_wall', s, wallMat, sx - side * .035, 0, 0, ry);
      }
    }
    for (const z of windows) {
      const c = u(z), s = rr(c - .67, 1.75, 1.34, .88, .085);
      plate(body, 'Side_glazing', s, glass, sx - side * .012, 0, 0, ry);
      rim(body, 'Window_gasket', s, rubber, [sx + side * .006, 0, 0], ry, .016);
      const frame = group(detail, 'Window_trim', sx + side * .023, 0, 0); frame.rotation.y = ry;
      rod(frame, 'Divider', V(c - .65, 2.21, 0), V(c + .65, 2.21, 0), .012, chrome);
      rod(frame, 'Sliding_pane', V(c, 2.22, 0), V(c, 2.61, 0), .009, chrome);
      box(frame, 'Window_latch', [.065, .025, .025], [c + .04, 2.25, .008], rubber);
    }
    rod(detail, 'Rain_gutter', V(sx, 2.72, -5.94), V(sx, 2.72, 5.94), .017, chrome);
    if (side > 0) {
      box(detail, 'Vent_recess', [.018, .43, 1.16], [1.262, 1.20, -1.90], dark);
      for (let y = 1.01; y < 1.42; y += .043) box(detail, 'Vent_louvre', [.027, .023, 1.12], [1.279, y, -1.90], red);
    }
  }

  // Rounded front/rear mouldings. The front glazing rakes back; the rear is almost upright.
  const endPoint = (a, y, sign, inset = 0) => {
    const r = 1.25 - inset, rake = y > 1.64 ? (y - 1.64) * (sign > 0 ? .43 : .13) : 0;
    // A shallow centre bow meets the much tighter quarter-light cheeks (6312 photos).
    const angle = Math.abs(a), reach = angle <= .82 ? 1.01 - .15 * (Math.sin(a) / Math.sin(.82)) ** 2
      : .86 * Math.pow(Math.max(0, Math.cos((angle - .82) / (Math.PI / 2 - .82) * Math.PI / 2)), .72);
    const belly = y >= .85 && y <= 1.66 ? .035 * ((y - 1.24) / .42) ** 2 : 0;
    const x = r * Math.sin(a), z = 5.99 + (reach / 1.01) * (1.01 - rake - inset - belly);
    return [x, y, sign * z];
  };
  const angles = Array.from({ length: 49 }, (_, i) => -Math.PI / 2 + Math.PI * i / 48);
  const windowY = (a, top, sign = 1) => {
    const corner = clamp((Math.abs(a) - .97) / (Math.PI / 2 - .97));
    return top ? 2.65 - (sign > 0 ? .19 : .09) * corner ** 3 : 1.77 + .09 * corner ** 3;
  };
  const browPoint = (a, t, sign) => {
    const lower = endPoint(a, windowY(a, true, sign), sign, sign > 0 ? -.045 : -.025);
    const upper = endPoint(a, 2.65, sign, sign > 0 ? -.035 : -.02);
    upper[0] *= .985; upper[1] = 2.74 + .25 * Math.cos(a) ** 2; upper[2] -= sign * .035 * Math.cos(a) ** 2;
    lower[1] += .025;
    return lower.map((v, i) => THREE.MathUtils.lerp(v, upper[i], t));
  };
  for (const sign of [-1, 1]) {
    for (const [lo, hi, mat] of [[.34, .85, cream], [.85, 1.66, red]]) {
      const rows = (lo < .5 ? [lo, .44, hi] : [lo, 1.04, 1.24, 1.45, hi]).map(y => angles.map(a => endPoint(a, y, sign)));
      if (lo < .5) { // open coupler pocket between the two cream cheek panels
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(0, 13)), mat);
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(36)), mat);
      } else surface(body, 'End_moulding', rows, mat);
    }
    surface(body, 'Cream_window_sill', [angles.map(a => endPoint(a, 1.66, sign)), angles.map(a => endPoint(a, windowY(a, false, sign), sign))], cream);
    const rows = [0, .5, 1].map(t => angles.map(a => endPoint(a, THREE.MathUtils.lerp(windowY(a, false, sign), windowY(a, true, sign), t), sign, .012)));
    surface(body, sign > 0 ? 'Windscreen_with_quarter_lights' : 'Rear_window', rows, glass);
    for (const top of [false, true]) tube(detail, 'End_window_seal', angles.map(a => V(...endPoint(a, windowY(a, top, sign), sign))), .018, rubber);
    for (const a of [-Math.PI / 2, -.83, .83, Math.PI / 2]) {
      rod(detail, 'End_window_mullion', V(...endPoint(a, windowY(a, false, sign), sign)), V(...endPoint(a, windowY(a, true, sign), sign)), .018, chrome);
    }
    surface(body, 'Overhanging_brow', [0, .12, .88, 1].map(t => angles.map(a => browPoint(a, t, sign))), cream);
    surface(detail, 'Brow_underside', [angles.map(a => endPoint(a, windowY(a, true, sign), sign)), angles.map(a => browPoint(a, 0, sign))], rubber);
    tube(detail, 'Brow_drip_edge', angles.map(a => V(...browPoint(a, 0, sign))), .012, chrome);
    for (const [dy, radius, mat] of [[.012, .013, chrome], [-.012, .008, red]]) {
      tube(detail, 'Windscreen_sill_trim', angles.map(a => V(...endPoint(a, windowY(a, false, sign) + dy, sign, -.016))), radius, mat);
    }
    // Broad aluminium bumper with two fine red inserts, as the 7000 close-up shows.
    for (const [lo, hi, mat] of [[.79, .808, rubber], [.808, .827, chrome], [.827, .839, red],
      [.839, .91, chrome], [.91, .922, red], [.922, .941, chrome], [.941, .954, rubber]]) {
      surface(detail, 'Bumper_band', [lo, hi].map(y => angles.map(a => endPoint(a, y, sign, -.055))), mat);
    }
    for (const x of [-.64, .64]) {
      const z = endPoint(Math.asin(x / 1.25), 1.13, sign, -.025)[2];
      if (sign > 0) {
        const g = group(detail, 'Headlamp', x, 1.13, z); g.rotation.x = Math.PI / 2;
        mesh(g, 'Red_lamp_pod', new THREE.CylinderGeometry(.143, .171, .11, 32), red, 0, .035, 0);
        mesh(g, 'Lamp_rubber_ring', new THREE.CylinderGeometry(.142, .145, .035, 32), rubber, 0, .105, 0);
        mesh(g, 'Lamp_bezel', new THREE.CylinderGeometry(.125, .134, .016, 32), chrome, 0, .13, 0);
        mesh(g, 'Lamp_lens', new THREE.SphereGeometry(.120, 24, 12), lamp, 0, .143, 0).scale.y = .20;
      } else {
        box(detail, 'Rear_lamp_surround', [.23, .105, .04], [x, 1.04, z], rubber);
        box(detail, 'Rear_red_lamp', [.195, .070, .045], [x, 1.04, z - .02], tail);
        const reflector = group(detail, 'Rear_reflector', Math.sign(x) * .88, .67, endPoint(Math.asin(.88 / 1.25), .67, -1, -.025)[2]);
        reflector.rotation.x = -Math.PI / 2;
        mesh(reflector, 'Reflector_rim', new THREE.CylinderGeometry(.063, .063, .017, 24), chrome);
        mesh(reflector, 'Reflector_red', new THREE.CylinderGeometry(.048, .048, .022, 24), tail, 0, .012, 0);
      }
    }
    if (sign < 0) box(detail, 'Rear_white_marker', [.19, .08, .025], [0, 1.04, -7.016], cream);
    for (const x of [-1.08, 1.08]) {
      const z = endPoint(Math.asin(x / 1.25), 1.21, sign, -.025)[2];
      box(detail, 'Indicator_surround', [.075, .24, .035], [x, 1.21, z], chrome);
      box(detail, 'Indicator', [.055, .092, .042], [x, 1.27, z + sign * .015], amber);
      box(detail, 'Marker_light', [.055, .085, .042], [x, 1.16, z + sign * .016], sign > 0 ? lamp : tail);
    }
    tube(detail, 'Access_hatch_seam', rr(-.28, 1.47, .56, .16, .025).getPoints(8).map(q =>
      V(...endPoint(Math.asin(q.x / 1.25), q.y, sign, -.005))), .004, dark, true);
  }
  // Roof cross-sections form the domed shoulders and smoothly rounded end caps.
  const roofRows = [];
  for (const [z, w, h] of [[-5.99, 1.25, 3.06], [-4.5, 1.25, 3.06], [0, 1.25, 3.06], [4.5, 1.25, 3.06], [5.99, 1.25, 3.06]]) {
    roofRows.push(Array.from({ length: 33 }, (_, i) => { const a = Math.PI * i / 32; return [w * Math.cos(a), 2.74 + (h - 2.74) * Math.sin(a), z]; }));
  }
  surface(body, 'Roof_shell', roofRows, cream);
  for (const sign of [-1, 1]) {
    const rows = Array.from({ length: 9 }, (_, j) => {
      const t = j / 8;
      return angles.map(a => {
        const front = browPoint(a, 1, sign), rear = [1.25 * Math.sin(a), 2.74 + .32 * Math.cos(a), sign * 5.99];
        const p = front.map((v, i) => THREE.MathUtils.lerp(v, rear[i], t));
        p[1] += .012 * Math.sin(Math.PI * t) * Math.cos(a); return p;
      });
    });
    surface(body, 'Rounded_roof_cap', rows, cream);
  }
  surface(detail, 'Roof_equipment_deck', [-5.6, 5.6].map(z => Array.from({ length: 25 }, (_, i) => {
    const x = -.82 + 1.64 * i / 24; return [x, 2.748 + .32 * Math.sqrt(1 - (x / 1.25) ** 2), z];
  })), roofMat);
  for (const z of [-4.5, -.5, 4.45]) box(detail, 'Roof_vent', [.58, .075, .88], [0, 3.10, z], roofMat);
  box(detail, 'Electrical_box', [.35, .32, .55], [.56, 3.22, 1.8], steel);

  // Closed stair wells and a 24-place saloon, with the user's early padded seat style.
  floorBox('Saloon_floor', [1.70, .08, 11.75], [.305, .834, -.03]);
  let floorStart = -5.905;
  for (const [a, b] of [...T3_PHOTO.doors.map(z => [z - .70, z + .70]).sort((a, b) => a[0] - b[0]), [5.845, 5.845]]) {
    if (a > floorStart) floorBox('Floor_at_side', [.61, .08, a - floorStart], [-.85, .834, (a + floorStart) / 2]);
    floorStart = b;
  }
  box(cabin, 'Underfloor_frame', [1.45, .25, 11.8], [.20, .65, 0], dark);
  floorBox('Rear_platform_floor', [1.68, .08, .90], [0, .834, -6.21]);
  for (const sign of [-1, 1]) {
    box(cabin, 'End_underframe_crossbeam', [1.50, .18, .14], [0, .65, sign * 6.08], dark);
    for (const x of [-.63, .63]) box(cabin, 'End_underframe_side_member', [.10, .16, .80], [x, .59, sign * 6.35], dark);
    box(detail, 'Life_guard', [1.47, .29, .10], [0, .20, sign * 6.55], rubber);
  }
  for (const z of [-1.7, 0, 1.6]) box(cabin, 'Underfloor_cabinet', [1.3, .28, 1], [0, .46, z], dark);
  for (const side of [-1, 1]) {
    const spans = side > 0 ? [[-5.90, 5.90]] : [[-4.60, -1.45], [-.05, 4.60]];
    for (const [a, b] of spans) {
      box(cabin, 'Interior_sill', [.055, .07, b - a], [side * 1.19, 1.68, (a + b) / 2], cream);
      box(cabin, 'Wall_kick_plate', [.012, .12, b - a], [side * 1.20, .95, (a + b) / 2], chrome);
      box(cabin, 'Sill_red_insert', [.016, .027, b - a], [side * 1.155, 1.68, (a + b) / 2], red);
      for (const y of [1.659, 1.701]) rod(cabin, 'Sill_trim', V(side * 1.145, y, a), V(side * 1.145, y, b), .006, chrome, 6);
    }
    rod(cabin, 'Overhead_handrail', V(side * .68, 2.40, -5.6), V(side * .68, 2.40, 4.7), .016, poleMat);
  }
  const seatPositions = [
    ...Array.from({ length: 13 }, (_, i) => [.84, -4.42 + i * .72]),
    ...[-4.14, -3.29, -2.44, .37, 1.11, 1.85, 2.59, 3.33, 4.07].map(z => [-.84, z]),
    [-.32, -6.15], [.32, -6.15],
  ];
  cabin.userData.passengerSeats = seatPositions.map(([x, z]) => ({ x, z, style: 'early upholstered T3' }));
  for (const [i, [x, z]] of seatPositions.entries()) {
    const seat = group(cabin, `Passenger_seat_${i + 1}`, x, 0, z);
    // Thick rounded pads on a tubular frame, rather than a single fibreglass shell.
    const pad = (name, w, h, depth, position) => {
      const g = new THREE.ExtrudeGeometry(rr(-w / 2, -h / 2, w, h, .045),
        { depth, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .012, bevelThickness: .012, curveSegments: 4 });
      return mesh(seat, name, g, seatMat, ...position);
    };
    pad('Seat_cushion', .46, .43, .065, [0, 1.25, 0]).rotation.x = -Math.PI / 2;
    pad('Seat_back_cushion', .43, .46, .075, [0, 1.59, -.24]).rotation.x = -.12;
    tube(seat, 'Seat_loop_frame', [V(-.235, 1.23, .15), V(-.235, 1.23, -.15), V(-.235, 1.39, -.26),
      V(-.235, 1.82, -.32), V(-.18, 1.90, -.33), V(.18, 1.90, -.33), V(.235, 1.82, -.32),
      V(.235, 1.39, -.26), V(.235, 1.23, -.15), V(.235, 1.23, .15)], .019, chrome);
    if ([13, 16, 21].includes(i)) {
      const base = new THREE.ExtrudeGeometry(rr(-.205, -.18, .41, .36, .06),
        { depth: .35, bevelEnabled: false, steps: 1, curveSegments: 3 });
      mesh(seat, 'Seat_electrical_box', base, poleMat, 0, .89, 0).rotation.x = -Math.PI / 2;
    } else {
      mesh(seat, 'Seat_pedestal', new THREE.CylinderGeometry(.115, .145, .35, 16), poleMat, 0, 1.065, 0);
      mesh(seat, 'Seat_foot_flange', new THREE.CylinderGeometry(.185, .185, .016, 16), chrome, 0, .885, 0);
    }
  }
  for (const z of T3_PHOTO.doors) {
    for (const dz of [-.77, .77]) rod(cabin, 'Door_stanchion', V(-.85, .9, z + dz), V(-.85, 2.55, z + dz), .018, poleMat);
    for (let i = 0; i < 3; i++) {
      const top = T3_PHOTO.entryFloor + i * (T3_PHOTO.floor - T3_PHOTO.entryFloor) / 2;
      floorBox('Closed_entry_step', [.25, top - .28, 1.39], [-1.13 + i * .22, (top + .28) / 2, z]);
      box(cabin, 'Step_nosing', [.025, .018, 1.39], [-1.24 + i * .22, top + .009, z], chrome);
    }
    for (const dz of [-.705, .705]) floorBox('Stair_well_cheek', [.69, .594, .035], [-.91, .577, z + dz]);
    box(cabin, 'Door_header', [.16, .18, 1.42], [-1.13, 2.70, z], cream);
    mesh(cabin, 'Door_warning_lamp', new THREE.SphereGeometry(.055, 12, 6), amber, -1.04, 2.60, z).scale.y = .55;
  }
  box(cabin, 'Driver_console', [1.40, .15, .56], [.1, 1.63, 6.16], dark);
  box(cabin, 'Driver_seat', [.48, .12, .47], [.36, 1.30, 5.63], rubber);
  box(cabin, 'Driver_seat_back', [.48, .50, .1], [.36, 1.60, 5.37], rubber);
  plate(cabin, 'Cab_partition', rr(-1.13, .90, 1.55, 1.62, .03), glass, 0, 0, 4.89);
  rod(cabin, 'Cab_frame', V(-1.13, 2.52, 4.89), V(.42, 2.52, 4.89), .022, chrome);

  // Each opening has two bi-fold pairs, outer hinge then inner hinge (four leaves).
  for (const [i, z] of T3_PHOTO.doors.entries()) {
    const d = group(root, `Door_${i + 1}`, -1.257, T3_PHOTO.entryFloor + .012, z), pairs = [];
    for (const sign of [-1, 1]) {
      const outer = group(d, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_outer`, 0, 0, sign * .69);
      const inner = group(outer, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_inner`, 0, 0, -sign * .345);
      for (const leaf of [outer, inner]) {
        const panel = rr(0, 0, .345, 2.248, .018);
        panel.holes.push(rr(.065, .18, .215, .89, .065), rr(.065, 1.20, .215, .96, .065));
        const shell = group(leaf, leaf.name + '_panel'); shell.rotation.y = sign > 0 ? Math.PI / 2 : -Math.PI / 2;
        plate(shell, 'Door_enamel', panel, cream, 0, 0, -sign * .006);
        plate(shell, 'Door_inner_aluminium', panel, poleMat, 0, 0, sign * .006);
        for (const [y, h] of [[.18, .89], [1.20, .96]]) {
          const s = rr(.065, y, .215, h, .065);
          plate(shell, 'Door_glass', s, glass, 0, 0, .002);
          rim(shell, 'Door_window_gasket', s, rubber, [0, 0, .008], 0, .012);
        }
        rod(shell, 'Door_leaf_seal', V(0, .014, .003), V(0, 2.234, .003), .014, rubber);
        if (leaf === inner) tube(shell, 'Door_inner_handle', [V(.29, .32, sign * .019),
          V(.26, .38, sign * .085), V(.10, 1.06, sign * .085), V(.08, 1.12, sign * .019)], .012, chrome);
      }
      outer.userData.axis = 'Y'; outer.userData.range = [0, -sign * T3_PHOTO.doorMaxAngle];
      inner.userData.axis = 'Y'; inner.userData.range = [0, sign * 2 * T3_PHOTO.doorMaxAngle];
      pairs.push({ outer, inner, sign });
    }
    rig.doors.push({ node: d, pairs });
  }

  for (const [i, z] of [3.2, -3.2].entries()) {
    const b = group(root, `Bogie_${i + 1}`, 0, .35, z); b.userData.axis = 'Y';
    const chassis = group(b, 'Bogie_frame');
    for (const x of [-.60, .60]) {
      box(chassis, 'Side_frame', [.16, .22, 2.35], [x, .08, 0], dark);
      for (const dz of [-.56, .56]) {
        for (let k = 0; k < 5; k++) mesh(chassis, 'Spring_coil', new THREE.TorusGeometry(.095, .014, 5, 12), steel, x, .05 + k * .035, dz).rotation.x = Math.PI / 2;
      }
      // FC33: enclosed coil between two pole shoes, spring hangers and a reaction link.
      const brake = group(chassis, `Magnetic_brake_${i + 1}_${x < 0 ? 'right' : 'left'}`, Math.sign(x) * .7175, -.35, 0);
      brake.userData.assembly = true;
      box(brake, 'Magnet_coil_casing', [.18, .12, .91], [0, .121, 0], wheelMat);
      for (const dx of [-.072, .072]) box(brake, 'Pole_shoe', [.047, .055, 1.10], [dx, .05, 0], wheelMat);
      for (const dz of [-.49, .49]) {
        box(brake, 'Magnet_end_plate', [.19, .15, .07], [0, .106, dz], wheelMat);
        rod(brake, 'Suspension_pin', V(0, .17, dz), V(0, .47, dz), .021, steel);
        for (let k = 0; k < 6; k++) mesh(brake, 'Hanger_spring', new THREE.TorusGeometry(.043, .009, 5, 12), wheelMat, 0, .23 + k * .025, dz).rotation.x = Math.PI / 2;
        box(brake, 'Hanger_bracket', [.26, .05, .11], [Math.sign(x) * .07, .46, dz], dark);
      }
      rod(brake, 'Brake_reaction_link', V(.10, .16, -.34), V(.16, .40, .17), .025, wheelMat);
      tube(brake, 'Magnet_feed_cable', [V(-.06, .20, .29), V(-.14, .36, .25), V(-.15, .42, -.20)], .017, rubber);
    }
    box(chassis, 'Bogie_crossmember', [1.9, .22, .32], [0, .12, 0], dark);
    for (const [j, dz] of [.95, -.95].entries()) {
      const axle = group(b, `Wheelset_${i + 1}_${j + 1}`, 0, 0, dz); axle.userData.axis = 'X';
      rod(axle, 'Axle', V(-.86, 0, 0), V(.86, 0, 0), .065, wheelMat);
      for (const side of [-1, 1]) {
        const x = side * .7525;
        const section = [[0, -.082], [.105, -.082], [.15, -.061], [.27, -.061], [.325, -.052], [.35, -.052],
          [.35, .052], [.325, .052], [.27, .061], [.15, .061], [.105, .082], [0, .082]];
        const wheel = mesh(axle, 'Solid_wheel', new THREE.LatheGeometry(section.map(p => new THREE.Vector2(...p)), 48), wheelMat, x, 0, 0);
        wheel.rotation.z = Math.PI / 2;
        const tread = mesh(axle, 'Running_tread', new THREE.CylinderGeometry(.3501, .3501, .102, 48, 1, true), treadMat, x, 0, 0);
        tread.rotation.z = Math.PI / 2;
        for (let k = 0; k < 6; k++) {
          const a = k * Math.PI / 3;
          mesh(axle, 'Wheel_bolt', new THREE.SphereGeometry(.018, 6, 4), wheelMat, x + side * .067, .18 * Math.cos(a), .18 * Math.sin(a));
        }
      }
      rig.wheelsets.push(axle);
    }
    rig.bogies.push(b);
  }
  for (const sign of [-1, 1]) {
    const c = group(root, sign > 0 ? 'Coupler_front' : 'Coupler_rear', 0, .46, sign * 6.25);
    c.userData.axis = 'Y';
    const hardware = group(c, 'Coupler_hardware'); hardware.rotation.y = sign < 0 ? Math.PI : 0;
    box(hardware, 'Drawbar', [.115, .12, .84], [0, 0, .47], steel);
    box(hardware, 'Drawbar_collar', [.18, .17, .105], [0, 0, .82], casting);
    rod(hardware, 'Drawbar_pivot', V(0, -.11, .11), V(0, .11, .11), .075, casting, 16);
    box(hardware, 'Head_neck', [.17, .145, .20], [0, 0, .95], casting);
    // Cast fork/guide head, with real bored eyes and an open mouth; not a black decal on a box.
    const outline = new THREE.Shape();
    [[-.09, .94], [-.17, 1.03], [-.18, 1.18], [-.14, 1.294], [-.06, 1.294], [-.026, 1.15],
      [.035, 1.15], [.075, 1.294], [.17, 1.27], [.18, 1.07], [.10, .94]].forEach(([x, z], i) => i ? outline.lineTo(x, z) : outline.moveTo(x, z));
    outline.closePath();
    for (const [x, z, radius] of [[-.112, 1.20, .028], [0, 1.025, .024]]) {
      const eye = new THREE.Path(); eye.absarc(x, z, radius, 0, Math.PI * 2, true); outline.holes.push(eye);
    }
    const headGeo = new THREE.ExtrudeGeometry(outline, { depth: .15, bevelEnabled: true, bevelThickness: .008,
      bevelSize: .008, bevelSegments: 1, steps: 1, curveSegments: 12 });
    // Bevel mitres extend beyond the profile; fit the finished casting to the drawing's coupling plane.
    headGeo.computeBoundingBox();
    const forwardScale = (1.302 - .94) / (headGeo.boundingBox.max.y - .94), hp = headGeo.attributes.position;
    for (let j = 0; j < hp.count; j++) {
      const z = .94 + (hp.getY(j) - .94) * forwardScale;
      hp.setY(j, z); hp.setZ(j, .075 + (hp.getZ(j) - .075) * (1 - .50 * clamp((z - 1.08) / .222)));
    }
    headGeo.computeVertexNormals(); headGeo.computeBoundingBox();
    const head = mesh(hardware, 'Bored_cast_coupler_head', headGeo, casting, 0, .075, 0); head.rotation.x = Math.PI / 2;
    for (const x of [-.174, .174]) {
      for (const y of [-.052, .052]) rod(hardware, 'Cast_side_rib', V(x, y, 1.06), V(x, y * .70, 1.24), .010, casting, 6);
      rod(hardware, 'Side_pin', V(x - .01, .01, 1.065), V(x + .01, .01, 1.065), .026, steel, 10);
    }
    tube(hardware, 'Coupler_lifting_handle', [V(-.075, .09, 1.02), V(-.075, .185, 1.02), V(.075, .185, 1.02), V(.075, .09, 1.02)], .012, casting);
    for (let j = 0; j < 6; j++) {
      const link = mesh(hardware, 'Safety_chain_link', new THREE.TorusGeometry(.022, .005, 4, 10), steel, .105, -.12 - j * .034, .87 + .014 * Math.sin(j));
      link.rotation.y = j % 2 * Math.PI / 2;
    }
    tube(hardware, 'Coupler_cable', [V(.10, -.03, .1), V(.21, -.17, .65), V(.12, -.12, .95)], .014, rubber);
    box(detail, 'Coupler_support_crossbar', [1.48, .065, .085], [0, .48, sign * 6.55], steel);
    for (const x of [-.65, .65]) rod(detail, 'Coupler_mount_brace', V(x, .54, sign * 6.12), V(0, .48, sign * 6.58), .033, steel);
    rig.couplers.push(c);
  }

  // True linkage hierarchy: paired lower/upper arms, their elbows, and level contact shoe.
  const panto = group(root, 'Pantograph', 0, 3.15, 3.1), arms = [];
  box(panto, 'Collector_base', [1.22, .12, .85], [0, .06, 0], dark);
  for (const x of [-.52, .52]) for (const z of [-.36, .36]) {
    for (let i = 0; i < 3; i++) mesh(panto, 'Insulator', new THREE.CylinderGeometry(.09, .09, .025, 14), cream, x, -.04 + .035 * i, z);
  }
  const L = 1.55;
  for (const sign of [-1, 1]) {
    const lower = group(panto, `Pantograph_lower_${sign > 0 ? 'front' : 'rear'}`, 0, .16, 0);
    const upper = group(lower, `Pantograph_upper_${sign > 0 ? 'front' : 'rear'}`, 0, L, 0);
    for (const arm of [lower, upper]) {
      for (const x of [-.53, .53]) rod(arm, 'Collector_arm', V(x, 0, 0), V(x, L, 0), .028, orange);
      const diagonal = sign * (arm === lower ? 1 : -1);
      rod(arm, 'Collector_diagonal', V(-diagonal * .53, .04, 0), V(diagonal * .53, L - .04, 0), .009, steel);
      arm.userData.diagonalRods = 1;
      rod(arm, 'Collector_hinge', V(-.60, 0, 0), V(.60, 0, 0), .038, steel);
    }
    arms.push({ lower, upper, sign });
  }
  const head = group(panto, 'Pantograph_contact_head');
  for (const z of [-.15, .15]) tube(head, 'Contact_strip', [V(-.96, -.12, z), V(-.80, 0, z), V(-.5, .03, z), V(.5, .03, z), V(.8, 0, z), V(.96, -.12, z)], .022, dark);
  rod(head, 'Head_crossmember', V(0, 0, -.19), V(0, 0, .19), .025, steel);
  rig.pantograph = { node: panto, arms, head, armLength: L };

  for (const x of [-.53, .53]) {
    const w = group(root, x < 0 ? 'Wiper_right' : 'Wiper_left', x * .80, 1.79, endPoint(Math.asin(x / 1.25), 1.79, 1, -.025)[2]);
    w.rotation.x = -.40;
    w.rotation.y = Math.sign(x) * .40;
    const pivot = group(w, w.name + '_pivot'); pivot.userData.axis = 'Z';
    rod(pivot, 'Wiper_arm', V(0, 0, .01), V(.18, .52, .01), .009, dark);
    rod(pivot, 'Wiper_blade', V(.18, .29, .025), V(.18, .77, .025), .016, rubber);
    rig.wipers.push(pivot);
  }
  const rearWiper = group(root, 'Wiper_rear', 0, 1.81, -6.995);
  rearWiper.rotation.set(-.13, Math.PI, 0);
  const rearPivot = group(rearWiper, 'Wiper_rear_pivot'); rearPivot.userData.axis = 'Z';
  rod(rearPivot, 'Rear_wiper_arm', V(0, 0, 0), V(0, .65, 0), .009, dark);
  rod(rearPivot, 'Rear_wiper_blade', V(.022, .28, .016), V(.022, .80, .016), .014, rubber);
  rig.wipers.push(rearPivot);
  const mirror = group(detail, 'Mirror_arm');
  tube(mirror, 'Mirror_support', [V(-1.12, 2.79, 6.1), V(-1.52, 2.81, 6.34), V(-1.64, 2.42, 6.37)], .022, steel);
  box(mirror, 'Mirror_back', [.18, .41, .085], [-1.64, 2.24, 6.37], rubber);
  box(mirror, 'Mirror_glass', [.151, .37, .008], [-1.64, 2.24, 6.32], chrome);

  // Text is a single generated atlas, never a photo projected onto the body.
  const cv = document.createElement('canvas'); cv.width = 1024; cv.height = 512;
  const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, 1024, 512);
  const writtenRows = new Set();
  function label(name, text, size, pos, ry, bg, fg, row, parent = detail) {
    const x = 0, y = row * 100, w = 1024, h = 96;
    if (!writtenRows.has(row)) {
      writtenRows.add(row);
      if (bg) { ctx.fillStyle = bg; ctx.fillRect(x, y, w, h); }
      ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const lines = String(text).split('\n'), virtualW = h * size[0] / size[1];
      ctx.font = `bold ${lines.length > 1 ? 39 : 80}px Arial`;
      ctx.save(); ctx.translate(w / 2, y); ctx.scale(w / virtualW, 1);
      lines.forEach((t, i) => {
        ctx.save();
        if (lines.length === 1) ctx.scale(virtualW * .86 / Math.max(1, ctx.measureText(t).width), 1);
        ctx.fillText(t, 0, h * (i + .5) / lines.length, virtualW * .92); ctx.restore();
      }); ctx.restore();
    }
    const g = new THREE.PlaneGeometry(...size, name.startsWith('Fleet_') ? 24 : 1, 1), uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i), 1 - (y + h * (1 - uv.getY(i))) / 512);
    if (name === 'Fleet_front' || name === 'Fleet_rear') {
      const p = g.attributes.position, sign = name === 'Fleet_front' ? 1 : -1;
      for (let i = 0; i < p.count; i++) p.setZ(i, Math.abs(endPoint(Math.asin(p.getX(i) / 1.25), pos[1] + p.getY(i), sign, -.009)[2]) - Math.abs(pos[2]));
      g.computeVertexNormals();
    }
    const m = mesh(parent, name, g, atlasMat, ...pos); m.rotation.y = ry; return m;
  }
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8; tex.minFilter = THREE.LinearFilter; tex.generateMipmaps = false;
  const atlasMat = material('Lettering', '#ffffff', .55, 0, { map: tex, transparent: true, alphaTest: .15 });
  const browLower = browPoint(0, 0, 1), browUpper = browPoint(0, 1, 1);
  const routePlate = group(detail, 'Route_plate', 0, (browLower[1] + browUpper[1]) / 2, (browLower[2] + browUpper[2]) / 2 + .014);
  routePlate.rotation.x = Math.atan2(browUpper[2] - browLower[2], browUpper[1] - browLower[1]);
  routePlate.userData.assembly = true;
  box(routePlate, 'Route_plate_frame', [.55, .322, .012], [0, 0, 0], cream);
  label('Route_front', line, [.52, .30], [0, 0, .008], 0, '#145488', '#fff8df', 0, routePlate);
  label('Fleet_front', fleet, [.68, .23], [0, 1.17, 7.009], 0, null, '#d3b665', 1);
  label('Destination', destination, [.62, .22], [0, 1.91, 6.82], 0, '#145488', '#fff8df', 2);
  label('Fleet_rear', fleet, [.68, .23], [0, 1.22, -7.009], Math.PI, null, '#d3b665', 1);
  label('Route_rear', line, [.29, .31], [0, 1.97, -6.92], Math.PI, '#e4ddc4', '#145488', 3);
  label('Route_mirror', line, [.22, .27], [-1.58, 2.53, 6.44], 0, '#145488', '#fff8df', 0);
  for (const side of [-1, 1]) {
    label('Fleet_side', fleet, [.68, .23], [side * 1.257, 1.47, side < 0 ? 3.80 : 1.80], side * Math.PI / 2, null, '#d3b665', 1);
    const indicator = group(detail, side < 0 ? 'Side_indicator_right' : 'Side_indicator_left', side * 1.269, 1.49, 4.35);
    indicator.userData.assembly = true;
    box(indicator, 'Side_indicator_base', [.025, .115, .10], [0, 0, 0], rubber);
    box(indicator, 'Side_indicator_lens', [.045, .086, .075], [side * .012, 0, 0], amber);
  }
  tex.needsUpdate = true;
  const assemblies = [body, cabin, detail, ...rig.doors.flatMap(d => [d.node, ...d.pairs.flatMap(p => [p.outer, p.inner])]),
    ...rig.bogies, ...rig.wheelsets, ...rig.couplers, ...rig.wipers.flatMap(w => [w.parent, w]),
    panto, head, ...arms.flatMap(a => [a.lower, a.upper])];
  assemblies.forEach(g => { g.userData.assembly = true; });
  batch(root);
  // The drawing's plan tapers toward both ends. Apply the same continuous taper to
  // shell, roof, glazing and fittings; yaw end-door jambs into that side plane.
  const taper = z => 1 - .10 * Math.max(0, Math.abs(z) - 4.65);
  body.traverse(o => {
    if (!o.isMesh) return;
    const p = o.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) p.setX(i, p.getX(i) * taper(p.getZ(i)));
    p.needsUpdate = true; o.geometry.computeVertexNormals();
  });
  for (const d of rig.doors) {
    const z = d.node.position.z;
    if (Math.abs(z) > 4.65) {
      d.node.position.x *= taper(z);
      d.node.rotation.y = Math.sign(z) * Math.atan(.125);
    }
  }
  // Keep live object references out of userData: GLTFExporter serializes that object.
  root.rig = rig;
  posePhotoT3(root);
  return root;
}

/** Absolute poses, so repeated calls never accumulate drift. Angles are radians. */
export function posePhotoT3(root, { doors = [0, 0, 0], bogies = [0, 0], wheelAngle = 0,
  pantograph = .68, wipers = 0, couplers = [0, 0] } = {}) {
  const r = root.rig;
  r.doors.forEach((d, i) => d.pairs.forEach(({ outer, inner, sign }) => {
    const a = clamp(Array.isArray(doors) ? doors[i] ?? 0 : doors) * T3_PHOTO.doorMaxAngle;
    outer.rotation.y = -sign * a; inner.rotation.y = sign * 2 * a;
  }));
  r.bogies.forEach((b, i) => { b.rotation.y = bogies[i] ?? 0; });
  r.wheelsets.forEach(w => { w.rotation.x = wheelAngle; });
  r.couplers.forEach((c, i) => { c.rotation.y = couplers[i] ?? 0; });
  r.wipers.forEach(w => { w.rotation.z = w.name === 'Wiper_rear_pivot' ? clamp(wipers) * .65 : -.33 + clamp(wipers) * .85; });
  const p = r.pantograph, a = THREE.MathUtils.lerp(1.45, .28, clamp(pantograph));
  p.arms.forEach(({ lower, upper, sign }) => { lower.rotation.x = sign * a; upper.rotation.x = -sign * 2 * a; });
  p.head.position.y = .16 + 2 * p.armLength * Math.cos(a);
  root.updateMatrixWorld(true);
}

export function photoT3Stats(root) {
  let meshes = 0, triangles = 0;
  root.traverse(o => { if (o.isMesh) { meshes++; triangles += (o.geometry.index?.count ?? o.geometry.attributes.position.count) / 3; } });
  return { meshes, triangles, dimensions: T3_PHOTO };
}

/** Reconnect the same pose API after GLTFLoader loads the exported GLB. */
export function bindPhotoT3(root) {
  const need = name => { const o = root.getObjectByName(name); if (!o) throw new Error(`Missing T3 rig node: ${name}`); return o; };
  root.rig = {
    doors: [1, 2, 3].map(i => ({ node: need(`Door_${i}`), pairs: [-1, 1].map(sign => {
      const prefix = `Door_${i}_${sign < 0 ? 'rear' : 'front'}`;
      return { outer: need(prefix + '_outer'), inner: need(prefix + '_inner'), sign };
    }) })),
    bogies: [1, 2].map(i => need(`Bogie_${i}`)),
    wheelsets: [1, 2].flatMap(i => [1, 2].map(j => need(`Wheelset_${i}_${j}`))),
    couplers: ['front', 'rear'].map(s => need(`Coupler_${s}`)),
    wipers: ['right', 'left', 'rear'].map(s => need(`Wiper_${s}_pivot`)),
    pantograph: { node: need('Pantograph'), head: need('Pantograph_contact_head'), armLength: 1.55,
      arms: [-1, 1].map(sign => { const s = sign < 0 ? 'rear' : 'front';
        return { lower: need(`Pantograph_lower_${s}`), upper: need(`Pantograph_upper_${s}`), sign };
      }) },
  };
  return root;
}
