// SPDX-License-Identifier: AGPL-3.0-or-later
// The cab's frame in the cab view (#246): the T3's windscreen posts, the posts where the windscreen's wrap ends, the cab
// window on the left and the front door on the right, and the walls past them, drawn where the driver's eye sees them.
// They turn with the head (Q / E), the zoom (G) and the cab's pitch and sway, so the view ends where the car's windows
// end (the user, 2026-11-17: "keep real pillars and end the view where real window ends. Right side can have door view
// there"). The geometry is the T3 model's (src/t3simple.js CAB); the ceiling band over it stays the screen's
// (index.html #cab .roof). A 2D canvas under the panel: a few polygons, each clipped at the eye's near plane.
import * as THREE from 'three';
import { CAB } from './t3simple.js';

const NEAR = 0.05;
const LEAN = 0.25, LEAN_TO = 1.3; // the eye leans towards the window it looks out of: 0.25 m a radian, up to 1.3 rad
const EYE_BACK = 0.8; // the eye behind the body's front (src/main.js)
// z from the body's front (negative), x left of the centre line, h over the rail
const dz = (z) => z - CAB.front;
const SIDE = { window: CAB.window.map(dz), door: CAB.door.map(dz), wrap: dz(CAB.wrap) };
const half = (d) => CAB.half(CAB.front + d);
const TOP = CAB.glass[1]; // the side windows' and the door's top
const COL = { post: '#59605c', postEdge: '#2b2f2d', wall: '#6c726e', partition: '#5f6562', door: '#b8b3a3', doorEdge: '#3a3a36' };

// A quad in a side's plane (sign +1 the left, -1 the right) from d0 to d1 along the car, h0 to h1 high
function side(sign, d0, d1, h0, h1) {
  return [[sign * half(d0), h0, d0], [sign * half(d1), h0, d1], [sign * half(d1), h1, d1], [sign * half(d0), h1, d0]];
}
// a quad standing between two points of the plan ([x, d]), h0 to h1 high
const upright = ([x0, d0], [x1, d1], h0, h1) => [[x0, h0, d0], [x1, h0, d1], [x1, h1, d1], [x0, h1, d0]];

// The frame's fixed members, back to front; [polygon, fill, edge]. Above the windows the screen's ceiling band stands
// for the cab's roof, as it does over the windscreen (the eye is 0.13 m under the windows' top: their wall over them
// filled the upper half of a side view).
function members() {
  const L = [], w = SIDE.window, d = SIDE.door, back = -7;
  // the left wall behind the cab window and the cab's rear partition across the car; the window's rear frame
  L.push([side(1, back, w[0], 0.5, 3.4), COL.wall]);
  L.push([[[1.25, 0.5, w[0] - 0.02], [-1.25, 0.5, w[0] - 0.02], [-1.25, 3.4, w[0] - 0.02], [1.25, 3.4, w[0] - 0.02]], COL.partition]);
  L.push([side(1, w[0] - 0.01, w[0] + 0.07, 0.5, 3.4), COL.post, COL.postEdge]);
  // the right: the wall behind the front door
  L.push([side(-1, back, d[0], 0.5, 3.4), COL.wall]);
  return L;
}
// The posts in front of the door: where the windscreen's wrap ends, between it and the cab window (left) or the door
// (right), and the windscreen's two, leaning back with the face
function posts() {
  const L = [];
  L.push([side(1, SIDE.window[1], SIDE.wrap, 0.5, 3.4), COL.post, COL.postEdge]);
  L.push([side(-1, SIDE.door[1], SIDE.wrap, 0.5, 3.4), COL.post, COL.postEdge]);
  for (const x of [-CAB.post, CAB.post]) {
    const p = [];
    for (const h of [1.3, 1.9, 2.5, 3.1]) p.push([x - 0.03, h, dz(CAB.face(x - 0.03, h))]);
    for (const h of [3.1, 2.5, 1.9, 1.3]) p.push([x + 0.03, h, dz(CAB.face(x + 0.03, h))]);
    L.push([p, COL.post, COL.postEdge]);
  }
  return L;
}
// The front door's four leaves (a tall pane over a lower one: src/t3simple.js draws them so from outside), two folding
// to each jamb as it opens: open (0..1) folds each pair into a V standing into the cab, 80° at its most
function door(open) {
  const L = [], [d0, d1] = SIDE.door, lw = (d1 - d0) / 4, th = open * 1.4, x0 = -half((d0 + d1) / 2);
  for (const [jamb, dir] of [[d0, 1], [d1, -1]]) {
    const p0 = [x0, jamb], p1 = [x0 + lw * Math.sin(th), jamb + dir * lw * Math.cos(th)], p2 = [x0, jamb + dir * 2 * lw * Math.cos(th)];
    for (const [a, b] of [[p0, p1], [p1, p2]]) {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, ux = (b[0] - a[0]) / len, ud = (b[1] - a[1]) / len, st = 0.05;
      const at = (k) => [a[0] + ux * k, a[1] + ud * k];
      L.push([upright(a, at(st), 0.5, TOP), COL.door, COL.doorEdge]);
      L.push([upright(at(len - st), b, 0.5, TOP), COL.door, COL.doorEdge]);
      L.push([upright(a, b, 1.40, 1.50), COL.door, COL.doorEdge]);
      L.push([upright(a, b, TOP - 0.08, TOP), COL.door, COL.doorEdge]);
    }
  }
  return L;
}

// How far the head turns each way: until the screen's edge reaches the cab window's end (left) or the front door's
// (right), with the eye leant towards it (src/main.js); fov: the camera's vertical one (degrees), aspect: width / height
export function lookLimits(fov, aspect) {
  const halfH = Math.atan(Math.tan((fov / 2) * Math.PI / 180) * aspect), lean = LEAN * LEAN_TO;
  const end = (d) => Math.PI - Math.atan2(half(d) - lean, -EYE_BACK - d);
  return { left: end(SIDE.window[0]) - halfH, right: end(SIDE.door[0]) - halfH };
}
// the eye's lean towards a side window for a head turned by look (rad)
export const leanFor = (look) => Math.sign(look) * Math.min(Math.abs(look), LEAN_TO) * LEAN;

export class CabFrame {
  constructor(canvas) {
    this.cv = canvas;
    this.g = canvas.getContext('2d');
    this.fixed = members();
    this.posts = posts();
    this.doorAt = null;
    this.m = new THREE.Matrix4();
    this.v = new THREE.Vector3();
    this.w = this.h = 0;
  }

  // car: the lead car's object; front: its body's front in its frame (src/main.js leadFront); open: the doors (0..1)
  draw(camera, car, front, open = 0) {
    const cv = this.cv, dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = Math.round(innerWidth * dpr), H = Math.round(innerHeight * dpr);
    if (W !== this.w || H !== this.h) { cv.width = this.w = W; cv.height = this.h = H; }
    const g = this.g;
    g.clearRect(0, 0, W, H);
    camera.updateMatrixWorld();
    car.updateWorldMatrix(true, false);
    this.m.multiplyMatrices(camera.matrixWorldInverse, car.matrixWorld);
    const P = camera.projectionMatrix, v = this.v;
    const o = Math.round(open * 40) / 40;
    if (o !== this.doorAt) { this.doorAt = o; this.door = door(o); }
    for (const [poly, fill, edge] of [...this.fixed, ...this.door, ...this.posts]) {
      // into the camera's space, cut at the near plane (z < -NEAR is in front of the eye)
      let pts = poly.map(([x, h, d]) => v.set(x, h, front + d).applyMatrix4(this.m).toArray());
      pts = clipNear(pts);
      if (pts.length < 3) continue;
      g.beginPath();
      for (let i = 0; i < pts.length; i++) {
        v.fromArray(pts[i]).applyMatrix4(P);
        const sx = (v.x + 1) * W / 2, sy = (1 - v.y) * H / 2;
        if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy);
      }
      g.closePath();
      g.fillStyle = fill;
      g.fill();
      if (edge) { g.strokeStyle = edge; g.lineWidth = 1.5 * dpr; g.stroke(); }
    }
  }

  clear() { this.g.clearRect(0, 0, this.w, this.h); }
}

// Sutherland–Hodgman against the plane z = -NEAR
function clipNear(pts) {
  const out = [], n = pts.length, inside = (p) => p[2] < -NEAR;
  for (let i = 0; i < n; i++) {
    const a = pts[i], b = pts[(i + 1) % n], ia = inside(a), ib = inside(b);
    if (ia) out.push(a);
    if (ia !== ib) {
      const t = (-NEAR - a[2]) / (b[2] - a[2]);
      out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, -NEAR]);
    }
  }
  return out;
}
