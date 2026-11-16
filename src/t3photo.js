// Original T3 geometry, metres, rail plane y=0, forward +z, doors on -x.
// Dimensioned drawing and photo references: assets/t3photo/README.md (#437).
import * as THREE from 'three';
import { mergeGeometries, mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

export const T3_PHOTO = Object.freeze({ length: 14, width: 2.5, roof: 3.06,
  bogieCentres: 6.4, axleSpacing: 1.9, wheelDiameter: .7, gauge: 1.435,
  overCouplers: 15.104, floor: .874, doors: [5.3, -.75, -5.3] });

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
    railPlane: 0, licence: 'GPL-3.0', dimensions: { ...T3_PHOTO }, reference: 'assets/t3photo/README.md' };
  const material = (name, color, roughness = .5, metalness = 0, extra = {}) => {
    const m = new THREE.MeshStandardMaterial({ color, roughness, metalness, side: THREE.DoubleSide, ...extra });
    m.name = name; return m;
  };
  const cream = material('Ivory_enamel', '#dfd6b9', .32), red = material('Prague_red_enamel', '#ac1e29', .3);
  const roofMat = material('Roof_grey', '#565653', .75), rubber = material('Rubber', '#171c1d', .84);
  const steel = material('Steel', '#525b60', .42, .75), chrome = material('Aluminium', '#b4b8b6', .28, .75);
  const dark = material('Underframe', '#303737', .77, .3), floorMat = material('Floor', '#53453c', .9);
  const glass = material('Window_glass', '#729293', .12, .28, { transparent: true, opacity: .57, depthWrite: false });
  const seatMat = material('Red_seat_shell', '#974139', .48), poleMat = material('Handrails', '#b5ae91', .32, .55);
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
        if (lo === .85) plate(cabin, 'Interior_wall', s, cream, sx - side * .035, 0, 0, ry);
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
    // Squarer than an ellipse: a wide face, tight corner radii, and a short tapered shoulder.
    const x = r * Math.sin(a), z = 5.99 + (1.01 - rake - inset) * Math.pow(Math.max(0, Math.cos(a)), .48);
    return [x, y, sign * z];
  };
  for (const sign of [-1, 1]) {
    for (const [lo, hi, mat] of [[.34, .85, cream], [.85, 1.66, red], [1.66, 1.77, cream], [2.65, 2.79, cream]]) {
      const rows = [lo, hi].map(y => Array.from({ length: 49 }, (_, i) => endPoint(-Math.PI / 2 + Math.PI * i / 48, y, sign)));
      if (lo < .5) { // open coupler pocket between the two cream cheek panels
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(0, 13)), mat);
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(36)), mat);
      } else surface(body, 'End_moulding', rows, mat);
    }
    const rows = [1.77, 2.65].map(y => Array.from({ length: 49 }, (_, i) => endPoint(-Math.PI / 2 + Math.PI * i / 48, y, sign, .012)));
    surface(body, sign > 0 ? 'Windscreen' : 'Rear_window', rows, glass);
    for (const y of [1.77, 2.65]) tube(detail, 'End_window_seal', Array.from({ length: 49 }, (_, i) => V(...endPoint(-Math.PI / 2 + Math.PI * i / 48, y, sign))), .018, rubber);
    for (const a of [-Math.PI / 2, -.83, .83, Math.PI / 2]) {
      rod(detail, 'End_window_mullion', V(...endPoint(a, 1.77, sign)), V(...endPoint(a, 2.65, sign)), .018, chrome);
    }
    for (const [y, radius, mat] of [[.86, .042, rubber], [.90, .026, chrome], [.83, .018, chrome]]) {
      tube(detail, 'Rubbing_strip', Array.from({ length: 49 }, (_, i) => V(...endPoint(-Math.PI / 2 + Math.PI * i / 48, y, sign, -.015))), radius, mat);
    }
    for (const x of [-.64, .64]) {
      const z = sign * (6.98 - .09 * Math.abs(x));
      if (sign > 0) {
        const g = group(detail, 'Headlamp', x, 1.13, z); g.rotation.x = Math.PI / 2;
        mesh(g, 'Lamp_housing', new THREE.CylinderGeometry(.139, .145, .095, 32), rubber);
        mesh(g, 'Lamp_bezel', new THREE.CylinderGeometry(.12, .13, .022, 32), chrome, 0, .058, 0);
        mesh(g, 'Lamp_lens', new THREE.SphereGeometry(.112, 24, 12), lamp, 0, .066, 0).scale.y = .25;
      } else {
        box(detail, 'Rear_lamp_surround', [.23, .105, .04], [x, 1.04, z], rubber);
        box(detail, 'Rear_red_lamp', [.195, .070, .045], [x, 1.04, z - .02], tail);
        const reflector = group(detail, 'Rear_reflector', Math.sign(x) * .88, .67, -6.87);
        reflector.rotation.x = -Math.PI / 2;
        mesh(reflector, 'Reflector_rim', new THREE.CylinderGeometry(.063, .063, .017, 24), chrome);
        mesh(reflector, 'Reflector_red', new THREE.CylinderGeometry(.048, .048, .022, 24), tail, 0, .012, 0);
      }
    }
    if (sign < 0) box(detail, 'Rear_white_marker', [.19, .08, .025], [0, 1.04, -7.016], cream);
    for (const x of [-1.08, 1.08]) {
      const z = sign * 6.73;
      box(detail, 'Indicator_surround', [.075, .24, .035], [x, 1.21, z], chrome);
      box(detail, 'Indicator', [.055, .092, .042], [x, 1.27, z + sign * .015], amber);
      box(detail, 'Marker_light', [.055, .085, .042], [x, 1.16, z + sign * .016], sign > 0 ? lamp : tail);
    }
    const hatch = rr(-.28, 1.47, .56, .16, .025);
    rim(detail, 'Access_hatch_seam', hatch, red, [0, 0, sign * 7.005], 0, .004);
  }
  // Roof cross-sections form the domed shoulders and smoothly rounded end caps.
  const roofRows = [];
  for (const [z, w, h] of [[-6.84, .02, 2.79], [-6.76, .70, 2.91], [-6.52, 1.12, 3.00], [-5.99, 1.25, 3.06],
    [-4.5, 1.25, 3.06], [0, 1.25, 3.06], [4.5, 1.25, 3.06], [5.99, 1.25, 3.04], [6.36, 1.10, 2.98], [6.52, .70, 2.87], [6.57, .02, 2.79]]) {
    roofRows.push(Array.from({ length: 33 }, (_, i) => { const a = Math.PI * i / 32; return [w * Math.cos(a), 2.74 + (h - 2.74) * Math.sin(a), z]; }));
  }
  surface(body, 'Roof_shell', roofRows, cream);
  surface(detail, 'Roof_equipment_deck', [-5.6, 5.6].map(z => Array.from({ length: 25 }, (_, i) => {
    const x = -.82 + 1.64 * i / 24; return [x, 2.748 + .32 * Math.sqrt(1 - (x / 1.25) ** 2), z];
  })), roofMat);
  for (const z of [-4.5, -.5, 4.45]) box(detail, 'Roof_vent', [.58, .075, .88], [0, 3.10, z], roofMat);
  box(detail, 'Electrical_box', [.35, .32, .55], [.56, 3.22, 1.8], steel);

  // Floor, steps and a modest full saloon, visible through the real windows.
  box(cabin, 'Saloon_floor', [1.70, .08, 11.75], [.305, .834, -.03], floorMat);
  let floorStart = -5.905;
  for (const [a, b] of [...T3_PHOTO.doors.map(z => [z - .70, z + .70]).sort((a, b) => a[0] - b[0]), [5.845, 5.845]]) {
    if (a > floorStart) box(cabin, 'Floor_at_side', [.61, .08, a - floorStart], [-.85, .834, (a + floorStart) / 2], floorMat);
    floorStart = b;
  }
  box(cabin, 'Underfloor_frame', [1.72, .25, 11.8], [0, .65, 0], dark);
  for (const sign of [-1, 1]) {
    box(cabin, 'End_underframe', [1.50, .26, 1.1], [0, .60, sign * 6.30], dark);
    box(detail, 'Life_guard', [1.47, .29, .10], [0, .20, sign * 6.55], rubber);
  }
  for (const z of [-1.7, 0, 1.6]) box(cabin, 'Underfloor_cabinet', [1.3, .28, 1], [0, .46, z], dark);
  for (const side of [-1, 1]) {
    if (side > 0) box(cabin, 'Interior_sill', [.055, .11, 11.8], [side * 1.19, 1.68, 0], cream);
    else for (const [a, b] of [[-4.60, -1.45], [-.05, 4.60]]) box(cabin, 'Interior_sill', [.055, .11, b - a], [-1.19, 1.68, (a + b) / 2], cream);
    rod(cabin, 'Overhead_handrail', V(side * .68, 2.40, -5.6), V(side * .68, 2.40, 4.7), .016, poleMat);
    for (const z of [-4.1, -2.7, -1.3, .1, 1.5, 2.9, 4.3]) {
      if (side < 0 && T3_PHOTO.doors.some(d => Math.abs(d - z) < .95)) continue;
      const seat = group(cabin, 'Seat', side * .84, 0, z);
      box(seat, 'Seat_pedestal', [.065, .4, .06], [0, 1.07, 0], chrome);
      const cushion = plate(seat, 'Seat_shell', rr(-.23, -.22, .46, .44, .075), seatMat, 0, 1.29, 0);
      cushion.rotation.x = -Math.PI / 2;
      const back = plate(seat, 'Seat_back', rr(-.23, 1.30, .46, .48, .10), seatMat, 0, 0, -.20);
      back.rotation.x = -.09;
      rod(seat, 'Seat_support', V(-.18, 1.15, -.22), V(-.18, 1.66, -.24), .013, chrome);
      rod(seat, 'Seat_support', V(.18, 1.15, -.22), V(.18, 1.66, -.24), .013, chrome);
    }
  }
  for (const z of T3_PHOTO.doors) {
    for (const dz of [-.77, .77]) rod(cabin, 'Door_stanchion', V(-.85, .9, z + dz), V(-.85, 2.55, z + dz), .018, poleMat);
    for (let i = 0; i < 3; i++) {
      box(cabin, 'Entry_step', [.25, .08, 1.36], [-1.13 + i * .22, .35 + i * .24, z], floorMat);
      box(cabin, 'Step_nosing', [.025, .025, 1.36], [-1.25 + i * .22, .397 + i * .24, z], chrome);
    }
  }
  box(cabin, 'Driver_console', [1.40, .15, .56], [.1, 1.63, 6.16], dark);
  box(cabin, 'Driver_seat', [.48, .12, .47], [.36, 1.30, 5.63], rubber);
  box(cabin, 'Driver_seat_back', [.48, .50, .1], [.36, 1.60, 5.37], rubber);
  plate(cabin, 'Cab_partition', rr(-1.13, .90, 1.55, 1.62, .03), glass, 0, 0, 4.89);
  rod(cabin, 'Cab_frame', V(-1.13, 2.52, 4.89), V(.42, 2.52, 4.89), .022, chrome);

  // Each opening has two bi-fold pairs, outer hinge then inner hinge (four leaves).
  for (const [i, z] of T3_PHOTO.doors.entries()) {
    const d = group(root, `Door_${i + 1}`, -1.257, .31, z), pairs = [];
    for (const sign of [-1, 1]) {
      const outer = group(d, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_outer`, 0, 0, sign * .69);
      const inner = group(outer, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_inner`, 0, 0, -sign * .345);
      for (const leaf of [outer, inner]) {
        const panel = rr(0, 0, .345, 2.34, .018);
        panel.holes.push(rr(.065, .25, .215, .91, .065), rr(.065, 1.29, .215, .96, .065));
        const shell = group(leaf, leaf.name + '_panel'); shell.rotation.y = sign > 0 ? Math.PI / 2 : -Math.PI / 2;
        plate(shell, 'Door_enamel', panel, cream, 0, 0, 0);
        for (const [y, h] of [[.25, .91], [1.29, .96]]) {
          const s = rr(.065, y, .215, h, .065);
          plate(shell, 'Door_glass', s, glass, 0, 0, .002);
          rim(shell, 'Door_window_gasket', s, rubber, [0, 0, .008], 0, .012);
        }
        rod(shell, 'Door_leaf_seal', V(0, .01, .003), V(0, 2.33, .003), .014, rubber);
        rod(shell, 'Door_handle', V(.31, .94, .04), V(.31, 1.36, .04), .012, chrome);
      }
      outer.userData.axis = 'Y'; outer.userData.range = [0, -sign * Math.PI / 2];
      inner.userData.axis = 'Y'; inner.userData.range = [0, sign * Math.PI];
      pairs.push({ outer, inner, sign });
    }
    rig.doors.push({ node: d, pairs });
  }

  for (const [i, z] of [3.2, -3.2].entries()) {
    const b = group(root, `Bogie_${i + 1}`, 0, .35, z); b.userData.axis = 'Y';
    const chassis = group(b, 'Bogie_frame');
    for (const x of [-.89, .89]) {
      box(chassis, 'Side_frame', [.16, .22, 2.35], [x, .08, 0], dark);
      for (const dz of [-.56, .56]) {
        for (let k = 0; k < 5; k++) mesh(chassis, 'Spring_coil', new THREE.TorusGeometry(.095, .014, 5, 12), steel, x, .05 + k * .035, dz).rotation.x = Math.PI / 2;
      }
      box(chassis, 'Magnetic_track_brake', [.14, .105, 1.10], [Math.sign(x) * .7175, -.285, 0], steel);
    }
    box(chassis, 'Bogie_crossmember', [1.9, .22, .32], [0, .12, 0], dark);
    for (const [j, dz] of [.95, -.95].entries()) {
      const axle = group(b, `Wheelset_${i + 1}_${j + 1}`, 0, 0, dz); axle.userData.axis = 'X';
      rod(axle, 'Axle', V(-.86, 0, 0), V(.86, 0, 0), .065, steel);
      for (const side of [-1, 1]) {
        const x = side * .7525;
        const wheel = mesh(axle, 'Wheel_tyre', new THREE.CylinderGeometry(.35, .35, .105, 48), steel, x, 0, 0); wheel.rotation.z = Math.PI / 2;
        const disc = mesh(axle, 'Wheel_disc', new THREE.CylinderGeometry(.285, .285, .113, 32), dark, x, 0, 0); disc.rotation.z = Math.PI / 2;
        const hub = mesh(axle, 'Wheel_hub', new THREE.CylinderGeometry(.115, .115, .15, 24), steel, x, 0, 0); hub.rotation.z = Math.PI / 2;
        for (let k = 0; k < 6; k++) {
          const a = k * Math.PI / 3;
          mesh(axle, 'Wheel_bolt', new THREE.SphereGeometry(.021, 6, 4), chrome, x + side * .065, .18 * Math.cos(a), .18 * Math.sin(a));
        }
      }
      rig.wheelsets.push(axle);
    }
    rig.bogies.push(b);
  }
  for (const sign of [-1, 1]) {
    const c = group(root, sign > 0 ? 'Coupler_front' : 'Coupler_rear', 0, .46, sign * 6.25);
    c.userData.axis = 'Y';
    box(c, 'Coupler_shank', [.13, .12, 1.12], [0, 0, sign * .56], steel);
    box(c, 'Coupler_head', [.25, .22, .182], [0, 0, sign * 1.211], dark);
    const hole = rr(-.067, -.055, .134, .11, .025);
    plate(c, 'Coupler_socket', hole, rubber, 0, 0, sign * 1.3023);
    rod(c, 'Coupler_pin', V(0, -.15, sign * 1.20), V(0, .17, sign * 1.20), .025, steel);
    tube(c, 'Coupler_cable', [V(.10, -.03, .1 * sign), V(.20, -.18, .7 * sign), V(.13, -.2, 1.15 * sign)], .014, rubber);
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
      rod(arm, 'Collector_crossbrace', V(-.53, .04, 0), V(.53, L - .04, 0), .009, steel);
      rod(arm, 'Collector_crossbrace', V(.53, .04, 0), V(-.53, L - .04, 0), .009, steel);
      rod(arm, 'Collector_hinge', V(-.60, 0, 0), V(.60, 0, 0), .038, steel);
    }
    arms.push({ lower, upper, sign });
  }
  const head = group(panto, 'Pantograph_contact_head');
  for (const z of [-.15, .15]) tube(head, 'Contact_strip', [V(-.96, -.12, z), V(-.80, 0, z), V(-.5, .03, z), V(.5, .03, z), V(.8, 0, z), V(.96, -.12, z)], .022, dark);
  rod(head, 'Head_crossmember', V(0, 0, -.19), V(0, 0, .19), .025, steel);
  rig.pantograph = { node: panto, arms, head, armLength: L };

  for (const x of [-.53, .53]) {
    const w = group(root, x < 0 ? 'Wiper_right' : 'Wiper_left', x, 1.79, 6.96);
    w.rotation.x = -.40;
    const pivot = group(w, w.name + '_pivot'); pivot.userData.axis = 'Z';
    rod(pivot, 'Wiper_arm', V(0, 0, .01), V(.18, .52, .01), .009, dark);
    rod(pivot, 'Wiper_blade', V(.18, .29, .025), V(.18, .77, .025), .016, rubber);
    rig.wipers.push(pivot);
  }
  const mirror = group(detail, 'Mirror_arm');
  tube(mirror, 'Mirror_support', [V(-1.12, 2.79, 6.1), V(-1.52, 2.81, 6.34), V(-1.64, 2.42, 6.37)], .022, steel);
  box(mirror, 'Mirror_back', [.18, .41, .085], [-1.64, 2.24, 6.37], rubber);
  box(mirror, 'Mirror_glass', [.151, .37, .008], [-1.64, 2.24, 6.32], chrome);

  // Text is a single generated atlas, never a photo projected onto the body.
  const cv = document.createElement('canvas'); cv.width = 1024; cv.height = 512;
  const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, 1024, 512);
  const writtenRows = new Set();
  function label(name, text, size, pos, ry, bg, fg, row) {
    const x = 0, y = row * 100, w = 1024, h = 96;
    if (!writtenRows.has(row)) {
      writtenRows.add(row);
      if (bg) { ctx.fillStyle = bg; ctx.fillRect(x, y, w, h); }
      ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const lines = String(text).split('\n'), virtualW = h * size[0] / size[1];
      ctx.font = `bold ${lines.length > 1 ? 39 : 80}px Arial`;
      ctx.save(); ctx.translate(w / 2, y); ctx.scale(w / virtualW, 1);
      lines.forEach((t, i) => ctx.fillText(t, 0, h * (i + .5) / lines.length, virtualW * .92)); ctx.restore();
    }
    const g = new THREE.PlaneGeometry(...size), uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i), 1 - (y + h * (1 - uv.getY(i))) / 512);
    const m = mesh(detail, name, g, atlasMat, ...pos); m.rotation.y = ry;
  }
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8; tex.minFilter = THREE.LinearFilter; tex.generateMipmaps = false;
  const atlasMat = material('Lettering', '#ffffff', .55, 0, { map: tex, transparent: true, alphaTest: .15 });
  label('Route_front', line, [.55, .33], [0, 2.83, 6.59], 0, '#145488', '#fff8df', 0);
  label('Fleet_front', fleet, [.53, .16], [0, 1.13, 7.012], 0, null, '#d3b665', 1);
  label('Destination', destination, [.62, .22], [0, 1.91, 6.82], 0, '#145488', '#fff8df', 2);
  label('Fleet_rear', fleet, [.53, .16], [0, 1.13, -7.012], Math.PI, null, '#d3b665', 1);
  label('Route_rear', line, [.29, .31], [0, 1.97, -6.95], Math.PI, '#e4ddc4', '#145488', 3);
  label('Route_mirror', line, [.22, .27], [-1.58, 2.53, 6.44], 0, '#145488', '#fff8df', 0);
  for (const side of [-1, 1]) label('Fleet_side', fleet, [.46, .16], [side * 1.257, 1.43, 1.8], side * Math.PI / 2, null, '#d3b665', 1);
  tex.needsUpdate = true;
  const assemblies = [body, cabin, detail, ...rig.doors.flatMap(d => [d.node, ...d.pairs.flatMap(p => [p.outer, p.inner])]),
    ...rig.bogies, ...rig.wheelsets, ...rig.couplers, ...rig.wipers.flatMap(w => [w.parent, w]),
    panto, head, ...arms.flatMap(a => [a.lower, a.upper])];
  assemblies.forEach(g => { g.userData.assembly = true; });
  batch(root);
  // The drawing's plan tapers toward both ends. Apply the same continuous taper to
  // shell, roof, glazing and fittings; yaw end-door jambs into that side plane.
  const taper = z => 1 - .06 * Math.max(0, Math.abs(z) - 4.8);
  body.traverse(o => {
    if (!o.isMesh) return;
    const p = o.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) p.setX(i, p.getX(i) * taper(p.getZ(i)));
    p.needsUpdate = true; o.geometry.computeVertexNormals();
  });
  for (const d of rig.doors) {
    const z = d.node.position.z;
    if (Math.abs(z) > 4.8) {
      d.node.position.x *= taper(z);
      d.node.rotation.y = Math.sign(z) * Math.atan(.075);
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
    const a = clamp(Array.isArray(doors) ? doors[i] ?? 0 : doors) * Math.PI / 2;
    outer.rotation.y = -sign * a; inner.rotation.y = sign * 2 * a;
  }));
  r.bogies.forEach((b, i) => { b.rotation.y = bogies[i] ?? 0; });
  r.wheelsets.forEach(w => { w.rotation.x = wheelAngle; });
  r.couplers.forEach((c, i) => { c.rotation.y = couplers[i] ?? 0; });
  r.wipers.forEach(w => { w.rotation.z = -.33 + clamp(wipers) * .85; });
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
    wipers: ['right', 'left'].map(s => need(`Wiper_${s}_pivot`)),
    pantograph: { node: need('Pantograph'), head: need('Pantograph_contact_head'), armLength: 1.55,
      arms: [-1, 1].map(sign => { const s = sign < 0 ? 'rear' : 'front';
        return { lower: need(`Pantograph_lower_${s}`), upper: need(`Pantograph_upper_${s}`), sign };
      }) },
  };
  return root;
}
