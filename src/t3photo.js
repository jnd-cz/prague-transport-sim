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
function tube(p, name, points, radius, mat, closed = false, minSegments = 16) {
  const path = new THREE.CatmullRomCurve3(points, closed, 'centripetal');
  return mesh(p, name, new THREE.TubeGeometry(path, Math.min(128, Math.max(minSegments, Math.ceil(points.length * 1.5))), radius, 6, closed), mat);
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
// Long faces need vertices at each shoulder before tapering; moving only their
// end vertices would narrow the entire wall/floor, exposing the seat frames (#437).
function splitAtShoulders(geometry) {
  const cuts = [-4.65, 4.65], attributes = ['position', 'normal', 'uv'];
  const output = Object.fromEntries(attributes.map(k => [k, []]));
  const index = geometry.index, count = index ? index.count : geometry.attributes.position.count;
  const vertex = i => attributes.flatMap(k => {
    const a = geometry.attributes[k], offset = i * a.itemSize;
    return Array.from(a.array.subarray(offset, offset + a.itemSize));
  });
  for (let i = 0; i < count; i += 3) {
    let polygons = [[0, 1, 2].map(j => vertex(index ? index.getX(i + j) : i + j))];
    for (const z of cuts) polygons = polygons.flatMap(poly => {
      if (!poly.some(v => v[2] < z - 1e-6) || !poly.some(v => v[2] > z + 1e-6)) return [poly];
      const halves = [[], []];
      for (let j = 0; j < poly.length; j++) {
        const a = poly[j], b = poly[(j + 1) % poly.length];
        if (a[2] <= z) halves[0].push(a);
        if (a[2] >= z) halves[1].push(a);
        if ((a[2] < z && b[2] > z) || (a[2] > z && b[2] < z)) {
          const t = (z - a[2]) / (b[2] - a[2]), point = a.map((v, k) => THREE.MathUtils.lerp(v, b[k], t));
          halves.forEach(h => h.push(point));
        }
      }
      return halves.filter(h => h.length >= 3);
    });
    for (const poly of polygons) for (let j = 1; j < poly.length - 1; j++) {
      for (const v of [poly[0], poly[j], poly[j + 1]]) {
        output.position.push(...v.slice(0, 3)); output.normal.push(...v.slice(3, 6)); output.uv.push(...v.slice(6, 8));
      }
    }
  }
  const split = new THREE.BufferGeometry();
  for (const k of attributes) split.setAttribute(k, new THREE.Float32BufferAttribute(output[k], k === 'uv' ? 2 : 3));
  const welded = mergeVertices(split, 1e-5); split.dispose(); return welded;
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

export function makePhotoT3({ variant = '6892', fleet = variant, line = '23',
  destination = variant === '6312' ? 'NOVÉ MĚSTO\nBÍLÁ LABUŤ' : 'BŘEVNOV\nKRÁLOVKA' } = {}) {
  if (!['6892', '6312'].includes(variant)) throw new RangeError('Unknown T3 variant: ' + variant);
  const early = variant === '6312';
  const root = new THREE.Group(); root.name = 'Tatra_T3_' + variant;
  root.userData = { asset: 'Original photo-based Tatra T3', units: 'metres', forward: '+Z', up: '+Y',
    variant, fleet, railPlane: 0, licence: 'AGPL-3.0-or-later', dimensions: { ...T3_PHOTO }, reference: 'assets/t3photo/README.md' };
  const material = (name, color, roughness = .5, metalness = 0, extra = {}) => {
    const m = new THREE.MeshStandardMaterial({ color, roughness, metalness, side: THREE.DoubleSide, ...extra });
    m.name = name; return m;
  };
  const cream = material('Ivory_enamel', early ? '#eee0a7' : '#dfd6b9', .32);
  const red = material('Prague_red_enamel', early ? '#bd1925' : '#ac1e29', .3);
  const roofMat = material('Roof_grey', '#565653', .75), rubber = material('Rubber', '#171c1d', .84);
  const steel = material('Steel', '#525b60', .42, .75), chrome = material('Aluminium', '#b4b8b6', .28, .75);
  const dark = material('Underframe', '#303737', .77, .3), floorMat = material('Floor', '#ffffff', .92);
  const glass = material('Window_glass', '#729293', .12, .28, { transparent: true, opacity: early ? .35 : .57, depthWrite: false });
  const seatMat = material(early ? 'Red_seat_cushion' : 'Red_moulded_seat', early ? '#ae3436' : '#c32630', early ? .62 : .3);
  const greySeat = early ? null : material('Grey_moulded_seat', '#bab8bd', .28);
  const poleMat = material('Handrails', '#a3a7a5', .46, .45);
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
  const wheelMat = material('Wheel_brown_dust', '#827a66', .89, .18);
  const treadMat = material('Wheel_running_tread', '#9a8975', .53, .48);
  const casting = material('Coupler_cast_steel', '#4f5150', .79, .42);
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
            const l = c - 1.22, r = c + 1.22, top = .73;
            if (l < start || r > a) continue;
            s.lineTo(l, lo); s.quadraticCurveTo(l + .035, lo, l + .058, lo + .07);
            s.lineTo(l + .105, top - .07); s.quadraticCurveTo(l + .12, top, l + .20, top);
            s.lineTo(r - .20, top); s.quadraticCurveTo(r - .12, top, r - .105, top - .07);
            s.lineTo(r - .058, lo + .07); s.quadraticCurveTo(r - .035, lo, r, lo);
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
    if (early) {
      const spans = side < 0 ? [[-4.59, -1.46], [-.04, 4.59]] : [[-5.98, 5.98]];
      for (const [level, intervals] of [[.85, spans], [1.66, spans], [2.72, [[-5.95, 5.95]]]]) {
        for (const [a, b] of intervals) {
          const height = level === .85 ? .060 : .030;
          box(detail, 'Alloy_side_moulding', [.035, height, b-a], [sx + side*.014, level, (a+b)/2], chrome);
          box(detail, 'Side_moulding_insert', [.008, .009, b-a], [sx + side*.033, level, (a+b)/2], red);
        }
      }
    }
    if (side > 0) {
      box(detail, 'Vent_recess', [.018, .43, 1.16], [1.262, 1.20, -1.90], dark);
      for (let y = 1.01; y < 1.42; y += .043) box(detail, 'Vent_louvre', [.027, .023, 1.12], [1.279, y, -1.90], red);
    }
  }

  // Rounded front/rear mouldings. The front glazing rakes back; the rear is almost upright.
  const taper = z => 1 - .10 * Math.max(0, Math.abs(z) - 4.65);
  const rearRake = .04;
  const endPoint = (a, y, sign, inset = 0) => {
    const r = 1.25 - inset, rake = y > 1.64 ? (y - 1.64) * (sign > 0 ? .43 : rearRake) : 0;
    // Wide central pane, tight cheek returns. This form of sqrt(1 - sin(a)^8)
    // keeps regular samples and a finite tangent all the way to the side jamb.
    const s2 = Math.sin(a) ** 2, c = Math.max(0, Math.cos(a));
    const reach = c * Math.sqrt((1 + s2) * (1 + s2 * s2)) * (1 - .16 * s2);
    const belly = y >= .85 && y <= 1.66 ? .035 * ((y - 1.24) / .42) ** 2 : 0;
    const x = r * Math.sin(a), z = 5.99 + reach * (1.01 - rake - inset - belly);
    return [x, y, sign * z];
  };
  const angles = Array.from({ length: 49 }, (_, i) => -Math.PI / 2 + Math.PI * i / 48);
  const windowY = (a, top, sign = 1) => {
    const corner = clamp((Math.abs(a) - .73) / (Math.PI / 2 - .73));
    if (sign < 0) return top ? 2.65 - .035 * corner ** 2 : 1.73 + .02 * corner ** 2;
    return top ? 2.65 - .17 * corner ** 2 : 1.77 + .08 * corner ** 2;
  };
  const browPoint = (a, t, sign) => {
    const c = Math.cos(a), lower = endPoint(a, windowY(a, true, sign), sign);
    lower[1] += .012; lower[2] += sign * .018 * c;
    const rise = 2.74 + .19 * c - lower[1];
    return [lower[0], lower[1] + t * rise, lower[2] - sign * .14 * c * rise * t];
  };
  for (const sign of [-1, 1]) {
    // On 6312 the front cream sill extends below the alloy strip. The rear red
    // panel reaches the strip. Both paint lines meet the side waist at the jamb.
    const waist = a => {
      if (!early) return 1.66;
      const endHeight = sign > 0 ? 1.56 : windowY(a, false, sign) - .048;
      return THREE.MathUtils.lerp(endHeight, 1.66, clamp((Math.abs(a) - 1.35) / (Math.PI / 2 - 1.35)) ** 2);
    };
    for (const [lo, hi, mat] of [[.34, .85, cream], [.85, 1.66, red]]) {
      const rows = (lo < .5 ? [lo, .44, hi] : [lo, 1.04, 1.24, 1.45, hi]).map(y =>
        angles.map(a => endPoint(a, y === 1.66 ? waist(a) : y, sign)));
      if (lo < .5) { // open coupler pocket between the two cream cheek panels
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(0, 13)), mat);
        surface(body, 'End_skirt_cheek', rows.map(r => r.slice(36)), mat);
      } else surface(body, 'End_moulding', rows, mat);
    }
    surface(body, 'Cream_window_sill', [angles.map(a => endPoint(a, waist(a), sign)), angles.map(a => endPoint(a, windowY(a, false, sign), sign))], cream);
    {
      // Quarter ellipses meet the sill and jamb tangentially. 6892's rear
      // quarter-lights have tighter corners, especially at the sill.
      const shoulder = angles[sign > 0 ? 42 : 44], jamb = sign > 0 ? 1.50 : 1.52;
      const corner = Array.from({ length: 9 }, (_, i) => {
        const t = Math.PI * i / 16;
        return [shoulder + (jamb - shoulder) * Math.sin(t), 1 - Math.cos(t)];
      });
      const sections = [...corner.slice().reverse().map(([a, k]) => [-a, k]),
        ...angles.filter(a => Math.abs(a) < shoulder - 1e-9).map(a => [a, 0]), ...corner];
      const upperRadius = sign > 0 ? .235 : .093, lowerRadius = sign > 0 ? .125 : .045;
      const edge = (a, k, top) => windowY(a, top, sign) + k * (top ? -upperRadius : lowerRadius);
      const pane = (a, k, t, inset) => endPoint(a, THREE.MathUtils.lerp(edge(a, k, false), edge(a, k, true), t), sign,
        sign > 0 ? inset * t : inset);
      surface(body, 'Windscreen_with_quarter_lights', [0, .5, 1].map(t =>
        sections.map(([a, k]) => pane(a, k, t, .012))), glass);
      for (const side of [-1, 1]) {
        for (const top of [false, true]) surface(body, 'Quarter_light_corner', [false, true].map(cut =>
          corner.map(([a, k]) => endPoint(side * a, cut ? edge(a, k, top) : windowY(a, top, sign), sign))), cream);
        surface(body, 'Quarter_light_pillar', [false, true].map(top =>
          [jamb, Math.PI / 2].map(a => endPoint(side * a, windowY(a, top, sign), sign))), cream);
      }
      const across = t => sections.map(([a, k]) => V(...pane(a, k, t, 0)));
      const jambPoints = side => [.25, .5, .75].map(t => V(...pane(side * jamb, 1, t, 0)));
      const sidesAndTop = [...jambPoints(1), ...across(1).reverse(), ...jambPoints(-1).reverse()];
      if (sign > 0) {
        tube(detail, 'Front_upper_and_side_seal', [V(...pane(jamb, 1, 0, 0)), ...sidesAndTop,
          V(...pane(-jamb, 1, 0, 0))], .011, rubber);
      } else tube(detail, 'Rear_window_gasket', [...across(0), ...sidesAndTop], .017, rubber, true);
    }
    for (const a of [-.75, .75]) {
      rod(detail, 'End_window_mullion', V(...endPoint(a, windowY(a, false, sign), sign)), V(...endPoint(a, windowY(a, true, sign), sign)), .018, chrome);
    }
    surface(detail, 'Brow_underside', [angles.map(a => endPoint(a, windowY(a, true, sign), sign)), angles.map(a => browPoint(a, 0, sign))], rubber);
    if (early) {
      // Both sills carry an alloy moulding. Only the front has one on the brow.
      for (const atBrow of (sign > 0 ? [false, true] : [false])) {
        const edge = (a, dy, offset) => {
          const p = atBrow ? browPoint(a, .045, sign) : endPoint(a, windowY(a, false, sign) - .041, sign);
          return [p[0] + offset*Math.sin(a), p[1]+dy, p[2] + sign*offset*Math.cos(a)];
        };
        for (const [h, d, mat] of [[.015, .014, chrome], [.004, .017, red]]) {
          surface(detail, 'End_moulding_trim', [-h,h].map(dy => angles.map(a => edge(a, dy, d))), mat);
        }
      }
    }
    // Broad aluminium bumper with two fine red inserts, as the 7000 close-up shows.
    for (const [lo, hi, mat] of [[.79, .808, rubber], [.808, .827, chrome], [.827, .839, red],
      [.839, .91, chrome], [.91, .922, red], [.922, .941, chrome], [.941, .954, rubber]]) {
      surface(detail, 'Bumper_band', [lo, hi].map(y => angles.map(a => endPoint(a, y, sign, -.055))), mat);
    }
    for (const x of [-.64, .64]) {
      const z = endPoint(Math.asin(x / 1.25), 1.13, sign, -.025)[2];
      if (sign > 0) {
        const lampY = early ? 1.20 : 1.17, lampX = Math.sign(x) * (early ? .575 : .55);
        const face = endPoint(Math.asin(lampX / (1.25 * taper(7))), lampY, sign);
        const g = group(root, 'Headlamp', lampX, lampY, face[2] - .009); g.rotation.x = Math.PI / 2;
        mesh(g, 'Red_lamp_pod', new THREE.CylinderGeometry(.110, .124, .060, 32), red, 0, .025, 0);
        mesh(g, 'Lamp_rubber_ring', new THREE.CylinderGeometry(.107, .110, .018, 32), rubber, 0, .061, 0);
        mesh(g, 'Lamp_bezel', new THREE.CylinderGeometry(.092, .099, .009, 32), chrome, 0, .073, 0);
        mesh(g, 'Lamp_lens', new THREE.SphereGeometry(.089, 24, 12), lamp, 0, .078, 0).scale.y = .14;
      } else {
        if (early) {
          const pod = group(detail, 'Combined_rear_lamp', x * .85, 1.073, z + .012);
          pod.rotation.y = Math.PI;
          plate(pod, 'Oval_lamp_bezel', rr(-.127,-.054,.254,.108,.054), chrome, 0,0,.008);
          plate(pod, 'Amber_outer_lenses', rr(-.119,-.046,.238,.092,.046), amber, 0,0,.010);
          box(pod, 'Red_centre_lens', [.073,.09,.012], [0,0,.012], tail);
          for (const edge of [-.039,.039]) box(pod, 'Lens_divider', [.007,.091,.012], [edge,0,.014], chrome);
        } else {
          box(detail, 'Rear_lamp_surround', [.23, .105, .04], [x, 1.04, z], rubber);
          box(detail, 'Rear_red_lamp', [.195, .070, .045], [x, 1.04, z - .02], tail);
        }
        const reflector = group(detail, 'Rear_reflector', Math.sign(x) * .88, .67, endPoint(Math.asin(.88 / 1.25), .67, -1, -.025)[2]);
        reflector.rotation.x = -Math.PI / 2;
        mesh(reflector, 'Reflector_rim', new THREE.CylinderGeometry(.063, .063, .017, 24), chrome);
        mesh(reflector, 'Reflector_red', new THREE.CylinderGeometry(.048, .048, .022, 24), tail, 0, .012, 0);
      }
    }
    if (sign < 0 && !early) box(detail, 'Rear_white_marker', [.19, .08, .025], [0, 1.04, -7.016], cream);
    for (const x of [-1.08, 1.08]) {
      const z = endPoint(Math.asin(x / 1.25), 1.21, sign, -.025)[2];
      if (early) {
        if (sign > 0) {
          const g = group(detail, 'Front_cheek_marker', x, 1.49, z - .012);
          g.rotation.y = Math.sign(x) * .56;
          plate(g, 'Oval_marker_bezel', rr(-.046,-.09,.092,.18,.046), chrome, 0,0,.010);
          plate(g, 'Clear_marker_lens', rr(-.038,-.081,.076,.162,.038), glass, 0,0,.014);
        }
        continue;
      }
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
    roofRows.push(angles.map(a => [w * Math.sin(a), 2.74 + (h - 2.74) * Math.cos(a), z]));
  }
  if (early) {
    // The grey roof comes down to the drip rail in the middle, sweeping up at both ends.
    const boundary = a => 5.87 - 1.85 * Math.abs(Math.sin(a)) ** 6;
    const row = zAt => angles.map(a => [1.25*Math.sin(a), 2.74+.32*Math.cos(a), zAt(a)]);
    for (const sign of [-1, 1]) {
      surface(body, 'Cream_roof_return', [row(() => sign*5.99), row(a => sign*boundary(a))], cream);
    }
    surface(body, 'Grey_roof', [row(a => -boundary(a)), row(() => 0), row(boundary)], roofMat);
  } else surface(body, 'Roof_shell', roofRows, cream);
  for (const sign of [-1, 1]) {
    // One continuous surface from the glass to the crown. The cubic leaves
    // the brow on its tangent and arrives at the roof with zero vertical slope.
    const rows = [0, .5, 1].map(t => angles.map(a => browPoint(a, t, sign)));
    for (let j = 1; j <= 12; j++) rows.push(angles.map(a => {
      const t = j / 12, u = 1 - t, c = Math.cos(a), [x, y, z] = browPoint(a, 1, sign);
      const roofY = 2.74 + .32 * c, roofZ = sign * 5.99;
      return [x, u ** 3 * y + 3 * u * u * t * (y + .10 * c) + t * t * (3 - 2 * t) * roofY,
        u ** 3 * z + 3 * u * u * t * (z - sign * .014 * c * c)
        + 3 * u * t * t * THREE.MathUtils.lerp(z, roofZ, .49) + t ** 3 * roofZ];
    }));
    surface(body, 'Rounded_roof_cap', rows, cream);
  }
  if (!early) surface(detail, 'Roof_equipment_deck', [-5.6, 5.6].map(z => Array.from({ length: 25 }, (_, i) => {
    const x = -.82 + 1.64 * i / 24; return [x, 2.748 + .32 * Math.sqrt(1 - (x / 1.25) ** 2), z];
  })), roofMat);
  for (const z of [-4.5, -.5, 4.45]) box(detail, 'Roof_vent', [.58, .075, .88], [0, 3.10, z], roofMat);
  box(detail, 'Electrical_box', [.35, .32, .55], [.56, 3.22, 1.8], steel);

  // The single-seat layout was reconstructed from the 6312 saloon photos (#437).
  floorBox('Saloon_floor', [1.70, .08, 11.75], [.305, .834, -.03]);
  let floorStart = -5.905;
  for (const [a, b] of [...T3_PHOTO.doors.map(z => [z - .76, z + .76]).sort((a, b) => a[0] - b[0]), [5.845, 5.845]]) {
    if (a > floorStart) floorBox('Floor_at_side', [.61, .08, a - floorStart], [-.85, .834, (a + floorStart) / 2]);
    floorStart = b;
  }
  box(cabin, 'Underfloor_frame', [1.45, .25, 11.8], [.20, .65, 0], dark);
  floorBox('Rear_platform_floor', [1.68, .08, .90], [0, .834, -6.21]);
  for (const x of [-.40, .40]) box(cabin, 'Aisle_hatch_edge', [.015, .004, 9.5], [x, .876, -.25], chrome);
  for (const z of [-5, -3.2, -1.45, .25, 1.95, 3.6, 4.5]) {
    box(cabin, 'Aisle_hatch_end', [.80, .004, .014], [0, .876, z], chrome);
  }
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
  const seats = [];
  function addSeat(x, z, facing = 'forward', base = 'pedestal') {
    seats.push({ x, z, facing, base, style: early ? 'early upholstered T3' : 'moulded shell' });
  }
  for (let i = 0; i < 14; i++) addSeat(.84, -5.06 + i * .72, 'forward', i === 13 ? 'box' : 'pedestal');
  for (const z of [-4.18, -3.43, -2.68, -1.93]) addSeat(-.84, z);
  for (const z of [.30, 1.00, 1.70, 2.40, 3.10]) addSeat(-.84, z);
  addSeat(-.84, 4.18, 'rearward', 'box');
  cabin.userData.referenceCar = variant;
  cabin.userData.passengerSeats = seats;
  for (const [i, { x, z, facing, base }] of seats.entries()) {
    const seat = group(cabin, `Passenger_seat_${i + 1}`, x, 0, z);
    if (facing === 'rearward') seat.rotation.y = Math.PI;
    // Thick rounded pads on a tubular frame, rather than a single fibreglass shell.
    const pad = (name, w, h, depth, position) => {
      const g = new THREE.ExtrudeGeometry(rr(-w / 2, -h / 2, w, h, .061),
        { depth, bevelEnabled: true, bevelSegments: 1, steps: 1, bevelSize: .020, bevelThickness: .018, curveSegments: 4 });
      return mesh(seat, name, g, seatMat, ...position);
    };
    if (early) {
      pad('Seat_cushion', .46, .43, .065, [0, 1.25, 0]).rotation.x = -Math.PI / 2;
      pad('Seat_back_cushion', .425, .405, .048, [0, 1.59, -.24]).rotation.x = -.12;
      tube(seat, 'Seat_loop_frame', [V(-.235, 1.23, .15), V(-.235, 1.23, -.15), V(-.235, 1.39, -.26),
        V(-.235, 1.82, -.32), V(-.18, 1.90, -.33), V(.18, 1.90, -.33), V(.235, 1.82, -.32),
        V(.235, 1.39, -.26), V(.235, 1.23, -.15), V(.235, 1.23, .15)], .016, chrome, false, 28);
    } else {
      // One dished shell sweeps up into the backrest. Roll the exposed edges under.
      const finish = i % 2 ? seatMat : greySeat;
      const profile = [[.235,1.30,.205],[.20,1.32,.225],[.08,1.315,.23],[-.10,1.29,.225],
        [-.16,1.31,.222],[-.19,1.355,.217],[-.21,1.414,.21],[-.25,1.61,.198],[-.29,1.745,.178],[-.29,1.755,.158]];
      const rows = profile.map(([z,y,w]) => [-1.02,-1,-.65,0,.65,1,1.02].map(u =>
        [w*u, y + .032*u*u - (Math.abs(u)>1 ? .012 : 0), z + .035*u*u]));
      // The low back slot is open right through the coloured shell.
      surface(seat, 'Seat_pan', rows.slice(0,6), finish);
      for (const start of [0,4]) surface(seat, 'Slot_side', rows.slice(5,7).map(row => row.slice(start,start+3)), finish);
      surface(seat, 'Seat_back', rows.slice(6), finish);
      tube(seat, 'Shell_grab_rail', [V(-.19,1.26,.06), V(-.207,1.29,-.16), V(-.21,1.43,-.23),
        V(-.174,1.77,-.31), V(-.13,1.835,-.33), V(.13,1.835,-.33), V(.174,1.77,-.31),
        V(.21,1.43,-.23), V(.207,1.29,-.16), V(.19,1.26,.06)], .013, poleMat, false, 20);
      box(seat, 'Seat_mounting_plate', [.20,.055,.18], [0,1.254,-.045], poleMat);
    }
    if (base === 'box') {
      const housing = new THREE.ExtrudeGeometry(rr(-.205, -.18, .41, .36, .06),
        { depth: .35, bevelEnabled: false, steps: 1, curveSegments: 3 });
      mesh(seat, 'Seat_electrical_box', housing, poleMat, 0, .89, 0).rotation.x = -Math.PI / 2;
    } else {
      mesh(seat, 'Seat_pedestal', new THREE.CylinderGeometry(.10, .165, .35, 16), poleMat, 0, 1.065, 0);
      mesh(seat, 'Seat_foot_flange', new THREE.CylinderGeometry(.185, .185, .016, 16), chrome, 0, .885, 0);
    }
  }
  for (const [x, zs] of [[.59, [-4.85, -2.69, -.53, 1.63, 3.79]], [-.59, [-4.4, -2.17, .07, 2.17, 4.44]]]) {
    for (const z of zs) {
      rod(cabin, 'Aisle_stanchion', V(x, .877, z), V(x, 2.4, z), .014, poleMat);
      rod(cabin, 'Stanchion_rail_joint', V(x, 2.4, z), V(Math.sign(x) * .68, 2.4, z), .015, poleMat);
      if (x > 0 && (z === -2.69 || z === 1.63)) {
        box(cabin, 'Ticket_validator', [.095, .24, .12], [x - .050, 1.98, z], amber);
        box(cabin, 'Validator_face', [.008, .09, .08], [x - .099, 2.02, z], rubber);
      }
    }
  }
  for (const z of T3_PHOTO.doors) {
    for (const dz of [-.77, .77]) rod(cabin, 'Door_stanchion', V(-.85, .9, z + dz), V(-.85, 2.55, z + dz), .018, poleMat);
    // The raised tread projects into the centre of the opening. Its clipped
    // corners leave a deeper bottom landing where the pairs fold at each jamb.
    floorBox('Entry_landing', [.715,.11,1.52], [-.8975,.335,z]);
    for (const [a,b,outerA,outerB] of [[-.76,-.30,-.77,-.925],[-.30,.30,-.925,-.925],[.30,.76,-.925,-.77]]) {
      const step = floorBox('Middle_tread', [1,.242,b-a], [0,.511,z+(a+b)/2]);
      const p = step.geometry.attributes.position, uv = step.geometry.attributes.uv;
      for (let j=0; j<p.count; j++) {
        const x = p.getX(j)>0 ? -.54 : (p.getZ(j)>0 ? outerB : outerA);
        p.setX(j,x); uv.setX(j,x/.064);
      }
      step.geometry.computeVertexNormals();
      rod(cabin, 'Tread_edge', V(outerA,.633,z+a), V(outerB,.633,z+b), .007, steel, 6);
    }
    box(cabin, 'Landing_edge', [.016,.006,1.52], [-.551,.876,z], steel);
    floorBox('Landing_riser', [.02,.242,1.52], [-.55,.753,z]);
    for (const dz of [-.78,.78]) floorBox('Stair_well_cheek', [.69,.594,.035], [-.91,.577,z+dz]);
    box(cabin, 'Door_header', [.15,.085,1.46], [-1.16,2.691,z], cream);
    mesh(cabin, 'Door_warning_lamp', new THREE.SphereGeometry(.045,12,6), amber,-1.06,2.70,z).scale.y=.55;
  }
  box(cabin, 'Driver_console', [1.40, .15, .56], [.1, 1.63, 6.16], dark);
  box(cabin, 'Driver_seat', [.48, .12, .47], [.36, 1.30, 5.63], rubber);
  box(cabin, 'Driver_seat_back', [.48, .50, .1], [.36, 1.60, 5.37], rubber);
  // Looking forward in 18532, the driver is behind the window-side panel; the gate is beside the entry.
  for (const [a, b] of [[-.55, .05], [.05, 1.16]]) {
    box(cabin, 'Cab_partition_laminate', [b - a, .76, .035], [(a + b) / 2, 1.26, 4.89], wallMat);
    plate(cabin, 'Cab_partition_glazing', rr(a, 1.64, b - a, .88, .018), glass, 0, 0, 4.89);
    for (const y of [.89, 1.64, 2.52]) rod(cabin, 'Cab_frame', V(a, y, 4.89), V(b, y, 4.89), .016, chrome);
  }
  for (const x of [-.55, .05, 1.16]) rod(cabin, 'Cab_jamb', V(x, .89, 4.89), V(x, 2.52, 4.89), .018, chrome);

  // Each opening has two bi-fold pairs, outer hinge then inner hinge (four leaves).
  for (const [i, z] of T3_PHOTO.doors.entries()) {
    const d = group(root, `Door_${i + 1}`, -1.257, T3_PHOTO.entryFloor + .012, z), pairs = [];
    for (const sign of [-1, 1]) {
      const outer = group(d, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_outer`, 0, 0, sign * .69);
      const inner = group(outer, `Door_${i + 1}_${sign < 0 ? 'rear' : 'front'}_inner`, 0, 0, -sign * .345);
      for (const leaf of [outer, inner]) {
        const panel = rr(0, 0, .345, 2.228, .018);
        panel.holes.push(rr(.065, .18, .215, .89, .065), rr(.065, 1.20, .215, .96, .065));
        const shell = group(leaf, leaf.name + '_panel'); shell.rotation.y = sign > 0 ? Math.PI / 2 : -Math.PI / 2;
        plate(shell, 'Door_enamel', panel, cream, 0, 0, -sign * .006);
        plate(shell, 'Door_inner_aluminium', panel, poleMat, 0, 0, sign * .006);
        if (early) {
          const edge = leaf === outer ? .345 : 0, hand = leaf === outer ? -1 : 1;
          for (const y of [.075, 1.144, 2.168]) {
            box(shell, 'Enamel_hinge_strap', [.070,.032,.014], [edge + hand*.035,y,-sign*.015], cream);
            if (leaf === outer) rod(shell, 'Hinge_barrel', V(edge,y-.028,-sign*.022),
              V(edge,y+.028,-sign*.022), .013, cream, 8);
          }
        }
        for (const [y, h] of [[.18, .89], [1.20, .96]]) {
          const s = rr(.065, y, .215, h, .065);
          plate(shell, 'Door_glass', s, glass, 0, 0, .002);
          rim(shell, 'Door_window_gasket', s, rubber, [0, 0, .008], 0, .012);
        }
        rod(shell, 'Door_leaf_seal', V(0, .014, .003), V(0, 2.213, .003), .014, rubber);
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
    // The cast housings fill the space behind the suspended brake (18347/18348).
    // Separate solids leave recesses around the exposed pins and cable.
    box(chassis, 'Transverse_bolster', [1.39, .30, .58], [0, .18, 0], dark);
    for (const dz of [-.35, .35]) {
      mesh(chassis, 'Equipment_housing', new THREE.CylinderGeometry(.265, .265, 1.06, 16),
        dark, 0, .077, dz).rotation.z = Math.PI / 2;
    }
    for (const side of [-1, 1]) {
      const x = side * .68;
      box(chassis, 'Side_frame', [.18, .355, 1.42], [side * .53, .006, 0], dark);
      box(chassis, 'Frame_top_flange', [.22, .052, 1.64], [side * .54, .18, 0], wheelMat);
      box(chassis, 'End_casting', [.23, .24, .23], [x, .066, -.36], wheelMat);
      box(chassis, 'End_casting_flange', [.265, .043, .31], [x, -.007, -.36], wheelMat);
      for (const dz of [-.425, -.31]) {
        rod(chassis, 'Flange_bolt', V(x, .014, dz), V(x, .036, dz), .022, wheelMat, 6);
        rod(chassis, 'Bearing_bolt', V(x + side*.11, -.031, dz), V(x + side*.129, -.031, dz), .024, wheelMat, 6);
      }
      // A stack of broad, rounded layers and a flared cover are visible above the shoe.
      const pack = [[.126,-.122],[.158,-.106],[.159,-.084],[.145,-.073],[.168,-.064],
        [.168,-.035],[.155,-.027],[.172,-.018],[.172,.008],[.158,.016],[.169,.026],
        [.169,.052],[.153,.061],[.161,.071],[.16,.095],[.136,.108],[0,.108]];
      mesh(chassis, 'Suspension_pack', new THREE.LatheGeometry(pack.map(p => new THREE.Vector2(...p)), 24),
        wheelMat, x, .09, -.035);
      box(chassis, 'Cover_top', [.255, .15, .245], [x, .154, .325], wheelMat);
      mesh(chassis, 'Flared_cover', new THREE.CylinderGeometry(.139, .18, .177, 16),
        wheelMat, x, -.003, .325);
      box(chassis, 'Cover_mount', [.20, .075, .21], [x, -.101, .325], dark);
      // Brake coordinates are measured from the rail head, along its centreline.
      const brake = group(chassis, `Magnetic_brake_${i + 1}_${side < 0 ? 'right' : 'left'}`, side * .7175, -.35, 0);
      brake.userData.assembly = true;
      for (const dx of [-.048, .048]) box(brake, 'Pole_shoe', [.078, .043, 1.13], [dx, .044, 0], wheelMat);
      box(brake, 'Magnet_coil_casing', [.177, .113, 1.13], [0, .118, 0], wheelMat);
      box(brake, 'Magnet_top_flange', [.162, .033, 1.06], [0, .187, 0], wheelMat);
      for (const dz of [-.555, .555]) {
        box(brake, 'Magnet_end_lug', [.19, .145, .077], [0, .151, dz], wheelMat);
        rod(brake, 'Suspension_pin', V(0, .211, dz), V(0, .49, dz), .014, wheelMat);
        const spring = Array.from({length: 55}, (_, k) => {
          const a = k * Math.PI / 3;
          return V(.027 * Math.cos(a), .236 + k * .0035, dz + .027 * Math.sin(a));
        });
        mesh(brake, 'Hanger_spring', new THREE.TubeGeometry(new THREE.CatmullRomCurve3(spring),
          spring.length - 1, .0065, 4, false), wheelMat);
        box(brake, 'Hanger_bracket', [.175, .038, .093], [0, .478, dz], dark);
      }
      box(brake, 'Pivot_saddle', [.15, .105, .144], [0, .223, -.07], wheelMat);
      for (const dx of [-.073, .073]) {
        box(brake, 'Pivot_ear', [.03, .080, .125], [dx, .206, -.07], wheelMat);
        rod(brake, 'Rounded_pivot_ear', V(dx-.015, .246, -.07), V(dx+.015, .246, -.07), .061, wheelMat, 16);
      }
      rod(brake, 'Pivot_pin', V(-.103, .246, -.07), V(.103, .246, -.07), .028, wheelMat, 12);
      rod(brake, 'Suspension_link', V(side*.058, .246, -.07), V(side*.058, .56, -.034), .016, dark);
      for (const dz of [-.51, -.30, -.16, .07, .51]) {
        rod(brake, 'Casing_fastener', V(side * .085, .119, dz), V(side * .099, .119, dz), .016, wheelMat, 6);
      }
      tube(brake, 'Magnet_feed_cable', [V(0,.38,-.29), V(side*.102,.29,-.26),
        V(side*.11,.174,-.24), V(side*.113,.15,-.05), V(side*.113,.113,.21),
        V(side*.11,.142,.30), V(side*.073,.18,.31)], .011, dark);
      for (const [height, dz] of [[.157,-.10],[.123,.16]]) {
        box(brake, 'Cable_clip', [.048, .034, .017], [side*.101,height,dz], wheelMat);
      }
    }
    for (const [j, dz] of [.95, -.95].entries()) {
      const axle = group(b, `Wheelset_${i + 1}_${j + 1}`, 0, 0, dz); axle.userData.axis = 'X';
      rod(axle, 'Axle', V(-.75, 0, 0), V(.75, 0, 0), .065, wheelMat);
      for (const side of [-1, 1]) {
        const x = side * .7525;
        const section = [[0,-.061],[.318,-.061],[.321,.052],[.300,.055],[.297,.051],
          [.293,.051],[.290,.061],[.285,.064],[.109,.064],[.101,.069],[0,.069]];
        const rim = [[.317,-.061],[.347,-.061],[.350,-.057],[.350,.048],[.346,.053],[.317,.055]];
        for (const [name, profile, mat] of [['Solid_wheel',section,wheelMat],['Wheel_tyre',rim,treadMat]]) {
          mesh(axle, name, new THREE.LatheGeometry(profile.map(p => new THREE.Vector2(...p)), 36), mat,
            x, 0, 0).rotation.z = -side * Math.PI / 2;
        }
        // A bevel catches the light around the single hex on the plain wheel disc.
        const nut = [[.108,.066],[.118,.073],[.118,.091],[.107,.101],[0,.101]];
        mesh(axle, 'Hub_hex_nut', new THREE.LatheGeometry(nut.map(p => new THREE.Vector2(...p)), 6),
          wheelMat, x, 0, 0).rotation.z = -side * Math.PI / 2;
        rod(axle, 'Axle_tip', V(x + side*.101,0,0), V(x + side*.110,0,0), .025, wheelMat, 12);
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
      hp.setX(j, hp.getX(j) * (1 - .17 * clamp((z - 1.08) / .222)));
      hp.setY(j, z); hp.setZ(j, .075 + (hp.getZ(j) - .075) * (1 - .50 * clamp((z - 1.08) / .222)));
    }
    headGeo.computeVertexNormals(); headGeo.computeBoundingBox();
    const head = mesh(hardware, 'Bored_cast_coupler_head', headGeo, casting, 0, .075, 0); head.rotation.x = Math.PI / 2;
    for (const x of [-.174, .174]) {
      for (const y of [-.052, .052]) rod(hardware, 'Cast_side_rib', V(x, y, 1.06), V(x * .88, y * .70, 1.24), .010, casting, 6);
      rod(hardware, 'Side_pin', V(x - .01, .01, 1.065), V(x + .01, .01, 1.065), .026, steel, 10);
    }
    tube(hardware, 'Coupler_lifting_handle', [V(-.075, .09, 1.02), V(-.075, .185, 1.02), V(.075, .185, 1.02), V(.075, .09, 1.02)], .012, casting);
    for (let j = 0; j < 6; j++) {
      const link = mesh(hardware, 'Safety_chain_link', new THREE.TorusGeometry(.022, .005, 4, 10), steel, .105, -.12 - j * .034, .87 + .014 * Math.sin(j));
      link.rotation.y = j % 2 * Math.PI / 2;
    }
    tube(hardware, 'Coupler_cable', [V(.10, -.03, .1), V(.21, -.17, .65), V(.12, -.12, .95)], .014, rubber);
    box(detail, 'Recessed_end_bulkhead', [1.94, .54, .08], [0, .60, sign * 6.06], rubber);
    for (const side of [-1, 1]) box(detail, 'Pocket_return', [.065, .48, .64], [side * .96, .62, sign * 6.34], rubber);
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

  rig.frontWiperLinks = [];
  for (const side of [-1, 1]) {
    const x = side * .32, y = 1.744;
    const w = group(root, side < 0 ? 'Wiper_right' : 'Wiper_left', x, y, endPoint(Math.asin(x / (1.25 * taper(7))), y, 1, -.008)[2]);
    w.rotation.set(-Math.atan(.43), side * .13, 0, 'XYZ');
    box(detail, 'Wiper_mount', [.096, .022, .023],
      [(x + side * .017) / taper(w.position.z), y, w.position.z - .003], rubber).rotation.copy(w.rotation);
    const pivot = group(w, w.name + '_pivot'); pivot.userData.axis = 'Z';
    const link = group(w, w.name + '_link', side * .034, 0, 0);
    const carrier = group(pivot, w.name + '_carrier', 0, .515, 0);
    for (const node of [link, carrier]) { node.userData.assembly = true; node.userData.axis = 'Z'; }
    rod(pivot, 'Wiper_arm', V(0, 0, .012), V(0, .515, .008), .009, dark);
    rod(link, 'Wiper_link', V(0, 0, .012), V(0, .515, .008), .005, dark);
    rod(carrier, 'Wiper_bridge', V(side * .034, 0, .008), V(0, 0, 0), .007, dark);
    rod(carrier, 'Wiper_blade', V(0, -.26, -.003), V(0, .28, -.003), .010, rubber);
    rig.frontWiperLinks.push({ link, carrier });
    rig.wipers.push(pivot);
  }
  // C5R09032: the arm hangs from the brow on a small twin-spindle plate.
  if (!early) {
    const mount = browPoint(0, .40, -1);
    const rearWiper = group(root, 'Wiper_rear', 0, mount[1], mount[2] - .012);
    rearWiper.rotation.set(Math.atan(rearRake), Math.PI, 0);
    box(rearWiper, 'Rear_wiper_mount', [.105, .046, .026], [.025, 0, 0], cream);
    const rearPivot = group(rearWiper, 'Wiper_rear_pivot'); rearPivot.userData.axis = 'Z';
    const rearLink = group(rearWiper, 'Wiper_rear_link', .057, 0, 0);
    const rearCarrier = group(rearPivot, 'Wiper_rear_carrier', .012, -.56, 0);
    rig.rearLink = rearLink; rig.rearCarrier = rearCarrier;
    for (const node of [rearLink, rearCarrier]) { node.userData.axis = 'Z'; node.userData.assembly = true; }
    rod(rearPivot, 'Rear_wiper_arm', V(0, 0, .017), V(.012, -.56, .010), .011, dark);
    rod(rearLink, 'Rear_wiper_link', V(0, 0, .017), V(.012, -.56, .010), .005, dark);
    rod(rearCarrier, 'Rear_wiper_bridge', V(.057, 0, .010), V(0, 0, -.010), .008, dark);
    rod(rearCarrier, 'Rear_wiper_blade', V(0, .25, -.010), V(0, -.27, -.010), .011, rubber);
    rig.wipers.push(rearPivot);
  }
  const mirror = group(detail, 'Mirror_arm');
  if (early) {
    rod(mirror, 'Roof_mirror_stay', V(-1.11,2.80,6.40), V(-1.63,2.49,6.36), .012, cream);
    for (const side of [-1,1]) {
      tube(mirror, 'Sill_mirror_stay', [V(side*1.14,1.64,6.51), V(side*1.16,1.76,6.51),
        V(side*1.32,1.84,6.52), V(side*1.36,2.01,6.52)], .012, cream);
      box(mirror, 'Small_mirror_back', [.125,.205,.039], [side*1.36,2.05,6.52], rubber);
      box(mirror, 'Small_mirror_glass', [.107,.184,.008], [side*1.36,2.05,6.495], chrome);
    }
    rod(mirror, 'Mirror_board_stay', V(-1.16,1.71,6.51), V(-1.62,2.18,6.37), .013, cream);
    for (const x of [-.057,.057]) rod(detail, 'Roof_disc_stay', V(x,3.01,6.05), V(x,3.21,6.05), .012, cream);
    mesh(detail, 'Roof_disc', new THREE.CylinderGeometry(.129,.129,.012,24),cream,0,3.212,6.05);
  } else tube(mirror, 'Mirror_support', [V(-1.12, 2.79, 6.1), V(-1.52, 2.81, 6.34), V(-1.64, 2.42, 6.37)], .022, steel);
  box(mirror, 'Mirror_back', [.18, .41, .085], [-1.64, 2.24, 6.37], rubber);
  box(mirror, 'Mirror_glass', [.151, .37, .008], [-1.64, 2.24, 6.32], chrome);

  // Text is a single generated atlas, never a photo projected onto the body.
  const cv = document.createElement('canvas'); cv.width = 1024; cv.height = early ? 1024 : 512;
  const ctx = cv.getContext('2d');
  const writtenRows = new Set();
  function label(name, text, size, pos, ry, bg, fg, row, parent = detail) {
    const x = 0, y = row * 100, w = 1024, h = 96;
    if (!writtenRows.has(row)) {
      writtenRows.add(row);
      if (bg) { ctx.fillStyle = bg; ctx.fillRect(x, y, w, h); }
      ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const lines = String(text).split('\n'), virtualW = h * size[0] / size[1];
      ctx.font = `bold ${Math.min(80, Math.floor(80 / lines.length))}px ${early && row === 1 ? 'Georgia' : 'Arial'}`;
      ctx.save(); ctx.translate(w / 2, y); ctx.scale(w / virtualW, 1);
      lines.forEach((t, i) => {
        ctx.save();
        if (lines.length === 1) ctx.scale(virtualW * .86 / Math.max(1, ctx.measureText(t).width), 1);
        if (early && row === 1) {
          ctx.strokeStyle = '#251d17'; ctx.lineWidth = 4;
          ctx.strokeText(t, 0, h * .53, virtualW * .92);
        }
        ctx.fillText(t, 0, h * (i + .5) / lines.length, virtualW * .92); ctx.restore();
      }); ctx.restore();
    }
    const g = new THREE.PlaneGeometry(...size, name.startsWith('Fleet_') ? 24 : 1, 1), uv = g.attributes.uv;
    for (let i = 0; i < uv.count; i++) uv.setXY(i, uv.getX(i), 1 - (y + h * (1 - uv.getY(i))) / cv.height);
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
  const plateSlope = (browUpper[2] - browLower[2]) / (browUpper[1] - browLower[1]);
  const plateY = browLower[1] + .161;
  const routePlate = group(detail, 'Route_plate', 0, plateY, browLower[2] + .161 * plateSlope + .012);
  routePlate.rotation.x = Math.atan(plateSlope);
  routePlate.userData.assembly = true;
  const boardWidth = early ? .50 : .404;
  box(routePlate, 'Route_plate_frame', [boardWidth + .019, .298, .012], [0, 0, 0], cream);
  label('Route_front', line, [boardWidth, .288], [0, 0, .008], 0, '#145488', '#fff8df', 0, routePlate);
  label('Fleet_front', fleet, [.68, .23], [0, 1.17, 7.009], 0, null, '#d3b665', 1);
  label('Destination', destination, [.62, .22], [0, 1.91, 6.82], 0, '#145488', early ? '#f8d765' : '#fff8df', 2);
  label('Fleet_rear', fleet, [.68, .23], [0, 1.22, -7.009], Math.PI, null, '#d3b665', 1);
  label('Route_rear', line, [.29, .31], [0, early ? 1.91 : 1.97, -6.92], Math.PI, early ? '#253e83' : '#e4ddc4', early ? '#fff8df' : '#145488', 3);
  label('Route_mirror', line, [.22, .27], [-1.58, 2.53, 6.44], 0, '#145488', '#fff8df', 0);
  // The bogie cover warning uses the spare row of the lettering atlas.
  ctx.save(); ctx.translate(0, 400); ctx.scale(1024 / 72, 1);
  ctx.fillStyle = '#e7e1d1'; ctx.fillRect(0, 0, 72, 96);
  ctx.fillStyle = '#e3b839'; ctx.fillRect(4, 4, 64, 88);
  ctx.strokeStyle = '#332f27'; ctx.lineWidth = 3; ctx.beginPath();
  ctx.moveTo(36, 10); ctx.lineTo(60, 60); ctx.lineTo(12, 60); ctx.closePath(); ctx.stroke();
  ctx.fillStyle = '#332f27'; ctx.beginPath(); ctx.moveTo(38, 22); ctx.lineTo(29, 42);
  ctx.lineTo(36, 42); ctx.lineTo(31, 55); ctx.lineTo(45, 35); ctx.lineTo(38, 35); ctx.closePath(); ctx.fill();
  ctx.fillRect(14, 72, 44, 3); ctx.fillRect(21, 80, 30, 2); ctx.restore();
  writtenRows.add(4);
  for (const b of rig.bogies) for (const side of [-1, 1]) {
    label('Bogie_warning', '', [.064, .085], [side * .809, .155, .325], side * Math.PI / 2, null, null, 4, b);
  }
  for (const side of [-1, 1]) {
    label('Fleet_side', fleet, early ? [.42,.16] : [.68,.23], [side * 1.257, early ? 1.26 : 1.47, side < 0 && !early ? 3.80 : 1.80], side * Math.PI / 2, null, '#d3b665', 1);
    const indicator = group(detail, side < 0 ? 'Side_indicator_right' : 'Side_indicator_left', side * 1.269, early ? 2.25 : 1.49, early ? 2.96 : 4.35);
    indicator.userData.assembly = true;
    box(indicator, 'Side_indicator_base', [.025, .115, .10], [0, 0, 0], rubber);
    if (early) mesh(indicator, 'Amber_domed_repeater', new THREE.SphereGeometry(.081,12,8), amber,side*.012,0,0).scale.set(.55,1,.82);
    else box(indicator, 'Side_indicator_lens', [.045, .086, .075], [side * .012, 0, 0], amber);
  }
  if (early) {
    for (const z of [-4.03,3.72]) {
      label('Entry_lettering', 'VÝSTUP\nVSTUP', [.54,.33], [-1.257,1.40,z], -Math.PI/2, null, '#9b9389', 5);
      label('Window_route_card', line+'   BŘEVNOV, Královka\n        Pražský hrad · Újezd\n        NOVÉ MĚSTO, Bílá labuť',
        [.54,.29], [-1.237,2.43,z], -Math.PI/2, '#204c88','#f5d660',6);
    }
  }
  tex.needsUpdate = true;
  const assemblies = [body, cabin, detail, ...rig.doors.flatMap(d => [d.node, ...d.pairs.flatMap(p => [p.outer, p.inner])]),
    ...rig.bogies, ...rig.wheelsets, ...rig.couplers, ...rig.wipers.flatMap(w => [w.parent, w]),
    panto, head, ...arms.flatMap(a => [a.lower, a.upper])];
  assemblies.forEach(g => { g.userData.assembly = true; });
  batch(root);
  // The drawing's plan tapers toward both ends. Apply the same continuous taper to
  // shell, roof, glazing and fittings; yaw end-door jambs into that side plane.
  body.traverse(o => {
    if (!o.isMesh) return;
    const old = o.geometry; o.geometry = splitAtShoulders(old); old.dispose();
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
  pantograph = .68, wipers = 0, rearWiper = 0, couplers = [0, 0] } = {}) {
  const r = root.rig;
  r.doors.forEach((d, i) => d.pairs.forEach(({ outer, inner, sign }) => {
    const a = clamp(Array.isArray(doors) ? doors[i] ?? 0 : doors) * T3_PHOTO.doorMaxAngle;
    outer.rotation.y = -sign * a; inner.rotation.y = sign * 2 * a;
  }));
  r.bogies.forEach((b, i) => { b.rotation.y = bogies[i] ?? 0; });
  r.wheelsets.forEach(w => { w.rotation.x = wheelAngle; });
  r.couplers.forEach((c, i) => { c.rotation.y = couplers[i] ?? 0; });
  for (const [i, side] of [1, -1].entries()) {
    const linkage = r.frontWiperLinks?.[i];
    const angle = side * (linkage ? THREE.MathUtils.lerp(.70, -.63, clamp(wipers)) : .33 - .85 * clamp(wipers));
    r.wipers[i].rotation.z = angle;
    if (linkage) { linkage.link.rotation.z = angle; linkage.carrier.rotation.z = -angle; }
  }
  if (r.wipers[2]) r.wipers[2].rotation.z = .65 * clamp(rearWiper, -1, 1);
  if (r.rearLink && r.rearCarrier) {
    r.rearLink.rotation.z = r.wipers[2].rotation.z;
    r.rearCarrier.rotation.z = -r.rearLink.rotation.z;
  }
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
    wipers: [need('Wiper_right_pivot'), need('Wiper_left_pivot'), root.getObjectByName('Wiper_rear_pivot')].filter(Boolean),
    frontWiperLinks: ['right', 'left'].map(side => {
      const link = root.getObjectByName(`Wiper_${side}_link`);
      return link && { link, carrier: need(`Wiper_${side}_carrier`) };
    }),
    rearLink: root.getObjectByName('Wiper_rear_link'), rearCarrier: root.getObjectByName('Wiper_rear_carrier'),
    pantograph: { node: need('Pantograph'), head: need('Pantograph_contact_head'), armLength: 1.55,
      arms: [-1, 1].map(sign => { const s = sign < 0 ? 'rear' : 'front';
        return { lower: need(`Pantograph_lower_${s}`), upper: need(`Pantograph_upper_${s}`), sign };
      }) },
  };
  return root;
}
