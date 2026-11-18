// SPDX-License-Identifier: AGPL-3.0-or-later
// The cab's frame in the cab view (#246): the T3's windscreen posts, the pillars where the windscreen's wrap ends, the cab
// window on the left up to the cab's rear wall and the front door on the right, drawn where the driver's eye sees them.
// They turn with the head (Q / E), the zoom (G) and the cab's pitch and sway, so the view ends where the car's windows
// end (the user, 2026-11-17: "keep real pillars and end the view where real window ends. Right side can have door view
// there"). The geometry is the T3 model's (src/t3simple.js CAB); the ceiling band over it stays the screen's
// (index.html #cab .roof) and is the top of every opening. A 2D canvas under the panel: a few polygons, each clipped at
// the eye's near plane.
import * as THREE from 'three';
import { CAB } from './t3simple.js';

const NEAR = 0.05;
const LEAN = 0.25, LEAN_TO = 1.3; // the eye leans towards the window it looks out of: 0.25 m a radian, up to 1.3 rad
// The driver's eye, over the seat of the T3's general arrangement (drawingdatabase.com Tatra-T3-1.gif, its plan view at
// 20 mm a pixel): the seat 0.32 m left of the centre line, its backrest 1.4 m and its front edge 1.0 m behind the nose,
// the eye over its middle (the user, 2026-11-17: "does the camera sit as real driver would, somewhat left off center? The
// t3 drawing ... shows the driver's seat"). It was on the centre line 0.8 m behind the nose, about over the desk. Its
// height is the old one: the drawing's side view has no seat. x left of the centre line, h over the rail, back from the
// body's front; src/main.js places the camera there
export const EYE = { x: 0.32, h: 2.39, back: 1.2 };
// z from the body's front (negative), x left of the centre line, h over the rail
const dz = (z) => z - CAB.front;
const SIDE = { window: CAB.window.map(dz), door: CAB.door.map(dz), wrap: dz(CAB.wrap) };
const half = (d) => CAB.half(CAB.front + d);
// The cab's rear wall, 1.62 m behind the nose on the general arrangement's plan view (docs/knowledge.md): it crosses the
// cab window, so the cab has the window's front 0.57 m of 1.3 (the user, 2026-11-17: "start of the side window frame with
// portion of the window on driver's side, then the back wall of the cabin starts"). It runs from the left side to the
// middle, where the drawing's partition turns diagonally to the front door's front jamb; that one is left out: the
// door is in view from the seat ("door view").
const REAR = -1.62;
const WALL_SHOWN = 0.12; // rad of the rear wall in view past the window's cut, the head turned all the way left
const R = 0.08; // the openings' top corners: their radius (m)
const COL = { post: '#59605c', postEdge: '#2b2f2d', rubber: '#151616', wall: '#6c726e', partition: '#5f6562', door: '#b8b3a3', doorEdge: '#3a3a36' };

// A quad in a side's plane (sign +1 the left, -1 the right) from d0 to d1 along the car, h0 to h1 high
function side(sign, d0, d1, h0, h1) {
  return [[sign * half(d0), h0, d0], [sign * half(d1), h0, d1], [sign * half(d1), h1, d1], [sign * half(d0), h1, d0]];
}
// a quad standing between two points of the plan ([x, d]), h0 to h1 high
const upright = ([x0, d0], [x1, d1], h0, h1) => [[x0, h0, d0], [x1, h0, d1], [x1, h1, d1], [x0, h1, d0]];

// The frame's fixed members, back to front; [polygon, fill, edge]. Above the openings the screen's ceiling band stands
// for the cab's roof, as it does over the windscreen (the eye is 0.13 m under the windows' top: their wall over them
// filled the upper half of a side view), so the members reach up under it.
function members() {
  const L = [], d = SIDE.door, back = -7;
  // the left: the cab's rear wall, which hides the window and the side behind it
  L.push([[[half(REAR) + 0.05, 0.5, REAR], [0, 0.5, REAR], [0, 3.4, REAR], [half(REAR) + 0.05, 3.4, REAR]], COL.partition, COL.postEdge]);
  // the right: the wall behind the front door
  L.push([side(-1, back, d[0], 0.5, 3.4), COL.wall]);
  return L;
}
// The pillars in front of the door: where the windscreen's wrap ends, between it and the cab window (left) or the door
// (right), the glass's rubber along their edges; and the windscreen's two posts, leaning back with the face. Those two
// join its panes: 3 cm, the rubber gasket's black stripe down their middle (the user, 2026-11-17: "the window divider
// frame I would make thinner with rubber gasket stripe in middle"; they were 6 cm, plain)
function posts() {
  const L = [], w = SIDE.window, d = SIDE.door, wrap = SIDE.wrap, g = 0.012;
  L.push([side(1, w[1], wrap, 0.5, 3.4), COL.post, COL.postEdge]);
  L.push([side(-1, d[1], wrap, 0.5, 3.4), COL.post, COL.postEdge]);
  for (const [sign, d0, d1] of [[1, wrap - g, wrap], [1, w[1], w[1] + g], [-1, wrap - g, wrap]]) L.push([side(sign, d0, d1, 0.5, 3.4), COL.rubber]);
  // a strip of the face, x ± w
  const strip = (x, w) => [1.3, 1.9, 2.5, 3.1].map((h) => [x - w, h, dz(CAB.face(x - w, h))])
    .concat([3.1, 2.5, 1.9, 1.3].map((h) => [x + w, h, dz(CAB.face(x + w, h))]));
  for (const x of [-CAB.post, CAB.post]) {
    L.push([strip(x, 0.015), COL.post, COL.postEdge]);
    L.push([strip(x, 0.006), COL.rubber]);
  }
  return L;
}
// The rounded top corners of the openings by the pillars: the windscreen's ends, the cab window's front and the door's
// (the user, 2026-11-17: "end of main window with rounded corners"): [side, d of the pillar's edge, the opening's way
// along the car (+1 forward)]
const CORNERS = [[1, SIDE.wrap, 1], [1, SIDE.window[1], -1], [-1, SIDE.wrap, 1], [-1, SIDE.door[1], -1]];
// The front door's four leaves (a tall pane over a lower one: src/t3simple.js draws them so from outside), two folding
// to each jamb as it opens: open (0..1) folds each pair into a V standing into the cab, 80° at its most. They reach up
// under the ceiling band, so the door's top is the windscreen's (the user, 2026-11-17: "door view where doors top end is
// aligned with the front window top frame").
function door(open) {
  const L = [], [d0, d1] = SIDE.door, lw = (d1 - d0) / 4, th = open * 1.4, x0 = -half((d0 + d1) / 2);
  for (const [jamb, dir] of [[d0, 1], [d1, -1]]) {
    const p0 = [x0, jamb], p1 = [x0 + lw * Math.sin(th), jamb + dir * lw * Math.cos(th)], p2 = [x0, jamb + dir * 2 * lw * Math.cos(th)];
    for (const [a, b] of [[p0, p1], [p1, p2]]) {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1, ux = (b[0] - a[0]) / len, ud = (b[1] - a[1]) / len, st = 0.05;
      const at = (k) => [a[0] + ux * k, a[1] + ud * k];
      L.push([upright(a, at(st), 0.5, 3.4), COL.door, COL.doorEdge]);
      L.push([upright(at(len - st), b, 0.5, 3.4), COL.door, COL.doorEdge]);
      L.push([upright(a, b, 1.40, 1.50), COL.door, COL.doorEdge]);
    }
  }
  return L;
}

// How far the head turns each way: until the screen's edge shows a little of the cab's rear wall past the cab window
// (left) or reaches the front door's rear jamb (right), with the eye leant towards it (src/main.js); fov: the camera's
// vertical one (degrees), aspect: width / height
export function lookLimits(fov, aspect) {
  const halfH = Math.atan(Math.tan((fov / 2) * Math.PI / 180) * aspect), lean = LEAN * LEAN_TO;
  // the angle from ahead to a point x off the centre line towards a side (sign: +1 the left, -1 the right), d along the car
  const at = (x, d, sign) => Math.PI - Math.atan2(x - sign * EYE.x - lean, -EYE.back - d);
  return { left: at(half(REAR), REAR, 1) + WALL_SHOWN - halfH, right: at(half(SIDE.door[0]), SIDE.door[0], -1) - halfH };
}
// the eye's lean towards a side window for a head turned by look (rad)
export const leanFor = (look) => Math.sign(look) * Math.min(Math.abs(look), LEAN_TO) * LEAN;

export class CabFrame {
  constructor(canvas) {
    this.cv = canvas;
    this.g = canvas.getContext('2d');
    this.roof = canvas.parentElement?.querySelector('.roof');
    this.fixed = members();
    this.posts = posts();
    this.doorAt = null;
    this.m = new THREE.Matrix4();
    this.v = new THREE.Vector3();
    this.w = this.h = 0;
  }

  // car: the lead car's object; front: its body's front in its frame (src/main.js leadFront); open: the doors (0..1);
  // hole: the mirror's frame while it is shown (its picture is in the scene's canvas, under this one)
  draw(camera, car, front, open = 0, hole = null) {
    const cv = this.cv, dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = Math.round(innerWidth * dpr), H = Math.round(innerHeight * dpr);
    if (W !== this.w || H !== this.h) { cv.width = this.w = W; cv.height = this.h = H; }
    const g = this.g;
    g.clearRect(0, 0, W, H);
    camera.updateMatrixWorld();
    car.updateWorldMatrix(true, false);
    this.m.multiplyMatrices(camera.matrixWorldInverse, car.matrixWorld);
    this.P = camera.projectionMatrix;
    this.front = front;
    const o = Math.round(open * 40) / 40;
    if (o !== this.doorAt) { this.doorAt = o; this.door = door(o); }
    for (const [poly, fill, edge] of [...this.fixed, ...this.door, ...this.posts]) {
      // into the camera's space, cut at the near plane (z < -NEAR is in front of the eye)
      let pts = poly.map(([x, h, d]) => this.v.set(x, h, front + d).applyMatrix4(this.m).toArray());
      pts = clipNear(pts);
      if (pts.length < 3) continue;
      g.beginPath();
      for (let i = 0; i < pts.length; i++) {
        const [sx, sy] = this.screen(pts[i]);
        if (i) g.lineTo(sx, sy); else g.moveTo(sx, sy);
      }
      g.closePath();
      g.fillStyle = fill;
      g.fill();
      if (edge) { g.strokeStyle = edge; g.lineWidth = 1.5 * dpr; g.stroke(); }
    }
    const yb = this.roof ? this.roof.getBoundingClientRect().bottom * dpr : 0;
    if (yb > 0) for (const c of CORNERS) this.corner(...c, yb, dpr);
    // the mirror's picture stays on top of the frame (the user, 2026-11-17: "mirror view should stay on top of
    // everything, not be hidden by other surface ... only menu can draw over it"; index.html #mirror is over the rest)
    if (hole) {
      const b = hole.getBoundingClientRect();
      if (b.width > 12 && b.height > 12) g.clearRect((b.left + 6) * dpr, (b.top + 6) * dpr, (b.width - 12) * dpr, (b.height - 12) * dpr);
    }
  }

  // a point in the camera's space on the canvas
  screen(p) {
    const v = this.v.fromArray(p).applyMatrix4(this.P);
    return [(v.x + 1) * this.w / 2, (1 - v.y) * this.h / 2];
  }

  // One opening's top corner: where the pillar's edge (sign, d) crosses the ceiling band's bottom (yb, canvas px), the
  // frame's colour fills the corner round to R at the edge's distance. The band is the screen's, so the corner is found
  // on the screen: down the edge from under the band to where it comes out of it.
  corner(sign, d, way, yb, dpr) {
    const x = sign * half(d), cam = (h, dd = d, xx = x) => this.v.set(xx, h, this.front + dd).applyMatrix4(this.m).toArray();
    let prev = null;
    for (let h = 3.4; h >= 1.0; h -= 0.05) {
      const p = cam(h);
      if (p[2] > -NEAR) { prev = null; continue; }
      const s = this.screen(p);
      if (prev && prev.s[1] < yb && s[1] >= yb) {
        const t = (yb - prev.s[1]) / (s[1] - prev.s[1]), ex = prev.s[0] + (s[0] - prev.s[0]) * t;
        const depth = -(prev.p[2] + (p[2] - prev.p[2]) * t);
        const r = Math.min(0.15 * this.h, (R * this.P.elements[5] * this.h) / 2 / depth);
        if (ex < -r || ex > this.w + r) return;
        // down the edge, and the opening's side on the screen
        const ux = s[0] - prev.s[0], uy = s[1] - prev.s[1], ul = Math.hypot(ux, uy) || 1;
        const q = cam(h, d + way * 0.05, sign * half(d + way * 0.05));
        if (q[2] > -NEAR) return;
        const toward = Math.sign(this.screen(q)[0] - s[0]) || 1;
        const g = this.g, ax = ex + (ux / ul) * r, ay = yb + (uy / ul) * r, bx = ex + toward * r;
        g.beginPath();
        g.moveTo(ex, yb);
        g.lineTo(ax, ay);
        g.quadraticCurveTo(ex, yb, bx, yb);
        g.closePath();
        g.fillStyle = COL.post;
        g.fill();
        g.beginPath();
        g.moveTo(ax, ay);
        g.quadraticCurveTo(ex, yb, bx, yb);
        g.strokeStyle = COL.rubber;
        g.lineWidth = 1.5 * dpr;
        g.stroke();
        return;
      }
      prev = { p, s };
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
