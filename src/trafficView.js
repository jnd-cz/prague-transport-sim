// SPDX-License-Identifier: AGPL-3.0-or-later
// The traffic as drawn (#228): the models of src/traffic.js's cars, other trams, walkers and lights, built and posed
// from its state after a step the page draws from (src/run.js stepTraffic). The rules read nothing of it: a car's
// height and an AI tram's cars for the rules are their own (c.pose, t.boxes), and a step that is not drawn moves the
// traffic as a drawn one does. src/between.js draws the movers (movers()) between the last two steps.
import * as THREE from 'three';
import { makeCar, fitCar, makeCrowd, makeT3, placeConsist, poseT3, setNextStop, makeTrafficLights, makePedLights, disposeModel, setOpacity } from './models.js';
import { setRiggedLevel, FULL_IN, FULL_OUT } from './rigged.js';
import { indicating } from './indicators.js';
import { MAX_WALKERS } from './traffic.js';

const M = new THREE.Matrix4(), Q = new THREE.Quaternion(), ONE = new THREE.Vector3(1, 1, 1), P = new THREE.Vector3(), E = new THREE.Euler();
const NONE = new THREE.Matrix4().makeScale(0, 0, 0); // (an empty walker slot)

export class TrafficView {
  constructor(scene, traffic) {
    this.scene = scene;
    this.traffic = traffic;
    this.group = new THREE.Group();
    scene.add(this.group);
    this.cars = new Map();  // car slot -> its model (a slot keeps its model: makeCar by slot.model)
    this.trams = new Map(); // AI tram -> its model (dropped once the tram is in neither list)
    this.crowd = makeCrowd(MAX_WALKERS);
    this.group.add(this.crowd);
    this.lights = makeTrafficLights(traffic.heads);
    this.group.add(this.lights.group);
    this.pedLights = makePedLights(traffic.pedHeads);
    this.group.add(this.pedLights.group);
  }

  // the model drawn for a car slot or an AI tram (the checks and tests), or null
  meshOf(o) { return this.cars.get(o) || this.trams.get(o) || null; }

  // after a step the page draws from: every model where the traffic stands. `camera`: for what only the drawing reads
  // (an AI tram's detailed model near it); without one, the traffic's focus.
  sync(camera) {
    const T = this.traffic, f = T.focus(), cam = camera ? [camera.position.x, -camera.position.z] : f;
    for (const c of T.cars) this._car(c);
    const gone = new Set(this.trams.keys());
    for (const t of T.ahead) { gone.delete(t); this._tram(t, T.route, (s) => T.ground.profile.height(s), cam); }
    for (const t of T.oncoming) { gone.delete(t); this._tram(t, T.back, (s, q) => T.ground.trackAt(q.x, q.y), cam); }
    for (const t of gone) { const m = this.trams.get(t); this.group.remove(m); disposeModel(m); this.trams.delete(t); }
    for (const lane of T.lightLanes) this.lights.set(lane.light.head, T.lightAspect(lane.light));
    for (const x of T.pedCross) { const a = T.pedAspect(x); for (const i of x.heads) this.pedLights.set(i, a); }
    this._walkers();
  }

  // what the steps move, for the page to draw between the last two (src/between.js): the cars in sight and the other
  // trams' cars. The walkers (1.1-1.6 m/s, 5 cm a step) stay where the step left them.
  movers() {
    const out = [];
    for (const [c, m] of this.cars) if (c.alpha > 0) out.push(m);
    for (const m of this.trams.values()) out.push(...m.userData.cars);
    return out;
  }

  dispose() {
    this.scene.remove(this.group);
    disposeModel(this.group);
    this.cars.clear();
    this.trams.clear();
  }

  // a model's fade (each model owns its materials), set only when it changes
  _alpha(m, a) {
    if (m.userData.alpha === a) return;
    m.userData.alpha = a;
    setOpacity(m, a);
  }

  _car(c) {
    let m = this.cars.get(c);
    if (!m) { m = makeCar(c.model); this.group.add(m); this.cars.set(c, m); }
    if (m.userData.type !== c.type) { m.userData.type = c.type; fitCar(m, c.type); } // (a slot's car is of a new type each time)
    this._alpha(m, c.alpha);
    const p = c.pose;
    if (c.alpha <= 0 || !p) return;
    if (m.userData.pose !== p) { // (a car standing still keeps its pose object)
      m.userData.pose = p;
      m.rotation.order = 'YXZ';
      m.position.set(p.x, p.z, -p.y);
      m.rotation.y = Math.atan2(p.hx, -p.hy);
      m.rotation.x = -p.pitch;
      m.rotation.z = p.roll;
    }
    m.userData.blink?.(c.blink, Math.floor(this.traffic.game.clock * 2.6) % 2 === 0);
  }

  // An AI tram's set on `route` (`trackZ(s, p)`: the track bed's height), each car as its running gear and coupling put
  // it (src/models.js placeConsist). Its lamps (#436): the brake lamps while it slows or stands, the indicators at junction
  // turns and stops where passengers cross a car lane (blinking out of step with the others'); a T3M's side display its
  // next stop. The detailed model: its full level near the camera, its doors (t.doorU), its lamps posed on that level only.
  _tram(t, route, trackZ, cam) {
    const T = this.traffic;
    let m = this.trams.get(t);
    if (!m) {
      m = makeT3({ line: t.line, cars: t.cars, vehicle: T.game.opts.vehicle, run: t.run, dealt: t.dealt });
      this.group.add(m);
      this.trams.set(t, m);
    }
    this._alpha(m, t.alpha ?? 0);
    this.poseTram(t, m, route, trackZ, cam);
  }

  poseTram(t, m, route, trackZ, cam = null) {
    const T = this.traffic, u = m.userData;
    placeConsist(m, t.s, (q) => { const p = route.at(q); return [p.x, p.y, trackZ(q, p), route.rollAt(q)]; });
    const way = T.lampWays[route === T.route ? 'ahead' : 'back'], braking = !!t.braking;
    const lamps = { braking, indicate: indicating(way.turns, way.kerb, t.s, t.v, braking), clock: T.game.clock + 0.17 * (t.id % 4) };
    if (u.kind === 'simple') {
      poseT3(m, lamps);
      if (u.variant === 'T3M') setNextStop(m, way.stops.find((st) => st.s > t.s - 2)?.name ?? null);
    }
    if (!u.rigged) return;
    const c = u.cars[0].position, d = cam ? Math.hypot(c.x - cam[0], -c.z - cam[1]) : 0;
    setRiggedLevel(m, d < (u.level === 'full' ? FULL_OUT : FULL_IN) ? 'full' : 'light');
    if (u.level === 'full') poseT3(m, { doors: t.doorU ?? 0, ...lamps });
  }

  // the walkers, one instance each by its slot (a stable colour): fading by growing out of / sinking into the ground
  // (the instances share one material)
  _walkers() {
    const slots = this.traffic.slots || [];
    for (let i = 0; i < MAX_WALKERS; i++) {
      const w = slots[i];
      if (!w || w.z === undefined) { this.crowd.setMatrixAt(i, NONE); continue; }
      P.set(w.x, w.z - (1 - w.alpha) * 1.8, -w.y);
      E.set(0, Math.atan2(w.hx, -w.hy), 0);
      Q.setFromEuler(E);
      M.compose(P, Q, ONE);
      this.crowd.setMatrixAt(i, M);
    }
    this.crowd.count = MAX_WALKERS;
    this.crowd.instanceMatrix.needsUpdate = true;
  }
}
