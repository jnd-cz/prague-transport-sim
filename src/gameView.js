// SPDX-License-Identifier: AGPL-3.0-or-later
// The game as drawn (#228): the world furniture of src/game.js's rules and what moves in them, built and posed from its
// state. At the start: the platforms and stops (src/platforms.js), the tram signals (where they stand: _mount), the
// distant signals, the switches' indicators, contact markers and signs, the speed switches' elements, the obstacles,
// the leaf mash and the track signs (signBoards: each where the rule wants it and where it stands). After a step the page
// draws from (src/run.js stepTraffic): the aspects, the indicators, the obstacles, the late passengers, the cross
// streets' cars and the driver with the switch iron; the people waiting at the stops once a drawn frame (syncCrowd,
// src/main.js). The rules read nothing of it.
import * as THREE from 'three';
import {
  makeCar, makePerson, makeCrowd, makeTramSignal, makeSwitchIndicator, makeContactMarker,
  makeSpeedSign, makeContactSign, makeRadioSwitchSign, makeSpeedBoard, disposeModel,
  makeSpeedSwitchSignal, makeSwitchNumberPlate, makeCallSignal, makeEntrySignal,
} from './models.js';
import { tramClearance } from './tram.js';
import { FROG } from './speedRules.js';
import { buildPlatforms, buildStop, place } from './platforms.js';
import { leafTexture } from './weather.js';
import { rng } from './random.js';

// the signs that release a limit (an end, a Rychlostník): moved past a platform, not before it (_mount)
const RELEASE = new Set(['end', 'higher', 'climbEnd', 'descentEnd', 'zoneEnd']);

export class GameView {
  constructor(scene, game) {
    this.scene = scene;
    this.game = game;
    const g = game, route = g.route;
    this.objects = new THREE.Group();
    scene.add(this.objects);
    // the platforms of both directions and the opposite stops' furniture; our stops' (platformGaps: the strips left out
    // over a track)
    this.platformGaps = [];
    buildPlatforms({ data: g.data, route, platforms: g.platforms, group: this.objects, log: this });
    this.stopSigns = new Map(); // our stop -> its sign
    for (const st of g.stops) this.stopSigns.set(st, buildStop({ stop: st, data: g.data, route, group: this.objects, log: this }));
    this.crowd = makeCrowd(120); // (the people waiting at the stop ahead and the one just passed: syncCrowd)
    this.objects.add(this.crowd);
    // the tram signals' heads (sig -> head); a gauntlet's two (G.sig's, and theirs facing oncoming trams: G -> head)
    this.heads = new Map();
    this.theirs = new Map();
    for (const sig of g.signals) {
      if (sig.gauntlet) continue;
      const mesh = makeTramSignal();
      // (at a platform end: on its own pole at the island's tip, a few metres past the post and further from
      // the track, so the post does not hide it from the driver; the same pole carries the crossing's
      // pedestrian heads; user's street view, Palackého náměstí. Hung from a span it hung 20 m back)
      if (sig.head && !sig.head.vienna) {
        const s = Math.min(sig.s, (sig.head.p1 ?? sig.s) - 0.5);
        place(mesh, route, s, -3.5, 0.18, true);
        mesh.userData.tip = s === sig.head.p1 - 0.5;
      } else this._mount(mesh, sig.s, { hang: sig.hang });
      this.objects.add(mesh);
      this.heads.set(sig, mesh);
    }
    for (const G of g.gauntlets) {
      const mesh = makeTramSignal();
      place(mesh, route, G.sig.s, -2.4, 0, true);
      this.objects.add(mesh);
      this.heads.set(G.sig, mesh);
      const their = makeTramSignal(), o = g.backRoute.offset(G.b0 - 4, -2.4);
      their.position.set(o.x, route.ground.trackAt(o.x, o.y), -o.y);
      their.rotation.y = Math.atan2(-o.hx, o.hy);
      this.objects.add(their);
      this.theirs.set(G, their);
    }
    this.distants = new Map(); // distant signal (předvěst) -> its head
    for (const d of g.distants) {
      const mesh = makeTramSignal({ distant: true });
      this._mount(mesh, d.s);
      this.objects.add(mesh);
      this.distants.set(d, mesh);
    }
    // the facing switches: a sign at the contact (or 40 m before a radio switch), the indicator over the track (a speed
    // switch's at its frog, with its elements), the contact's marker on the wire
    this.signBoards = []; // { kind, s, at, ... }: each track sign, where the rule wants it (s) and where it stands (at)
    this.switches = new Map(); // switch -> { indicator, marker }
    for (const sw of g.switches) {
      const indicator = sw.speedSwitch ? makeSpeedSwitchSignal() : makeSwitchIndicator(), marker = makeContactMarker();
      marker.visible = !sw.auto;
      const sign = sw.auto ? makeRadioSwitchSign() : makeContactSign();
      this._mount(sign, sw.auto ? sw.s - 40 : sw.contact);
      this.objects.add(sign);
      if (sw.speedSwitch) this._speedSwitch(sw, indicator);
      else place(indicator, route, sw.s - 8, -0.4, -0.26, true); // hangs from the span wire over the track
      const c = route.at(sw.contact);
      marker.position.x = c.x;
      marker.position.y += g.profile.height(sw.contact);
      marker.position.z = -c.y;
      this.objects.add(indicator, marker);
      this.switches.set(sw, { indicator, marker });
    }
    this.obstacles = new Map(); // obstacle -> its car or person
    for (const ob of g.obstacles) {
      const mesh = ob.type === 'parked' ? makeCar(ob.model) : makePerson(ob.model);
      this.objects.add(mesh);
      this.obstacles.set(ob, mesh);
    }
    // the leaf mash on and between the rails (autumn: src/game.js _initAdhesion's patches)
    if (g.leafSmears.length) {
      const mat = new THREE.MeshLambertMaterial({ map: leafTexture(true), alphaTest: 0.35, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
      const geo = new THREE.PlaneGeometry(1, 1);
      for (const L of g.leafSmears) {
        const smear = new THREE.Mesh(geo, mat);
        smear.rotation.set(-Math.PI / 2, 0, L.turn);
        smear.scale.set(L.size, L.size, 1);
        const holder = new THREE.Group();
        holder.add(smear);
        place(holder, route, L.s, L.lat, 0.27, false);
        this.objects.add(holder);
      }
    }
    this._signs();
    this.runners = new Map();  // late passenger -> person
    this.crossCars = new Map(); // a cross street's car -> its model
    this.driver = null; // the driver out with the switch iron
    this.sync();
  }

  // Track signs (#364) where src/game.js's rules want them (signPlan), each mounted by _mount and listed in signBoards
  // with where it stands; the diagnostic boards (diagSigns) in their own group, shown with the debug overlay only (F8,
  // src/debugOverlay.js), none within 20 m of a real sign, which stands there.
  _signs() {
    const g = this.game;
    for (const sign of g.signPlan) {
      const board = makeSpeedBoard(sign);
      this._mount(board, sign.s, { movable: RELEASE.has(sign.kind) ? 'after' : true });
      this.objects.add(board);
      // where the rule wants it, and where it stands (moved off a platform, or to its span)
      this.signBoards.push({ ...sign, s: Math.round(sign.s), at: Math.round(board.userData.mountedS ?? sign.s) });
    }
    const diag = (this.diagBoards = new THREE.Group());
    diag.visible = false;
    this.objects.add(diag);
    const real = this.signBoards.map((b) => b.at ?? b.s);
    for (const { s, v, movable } of g.diagSigns) {
      const board = makeSpeedSign(v);
      board.userData.diagnostic = true;
      this._mount(board, s, { movable });
      const at = board.userData.mountedS ?? s;
      if (real.some((r) => Math.abs(r - at) < 20)) continue;
      diag.add(board);
      this.signBoards.push({ kind: 'diagnostic', v, s: Math.round(s), at: Math.round(at) });
    }
  }

  // A speed switch's elements at R01's distances (D 1/2 § 46; docs/decisions/2026-11-07-speed-switch-signals.md): the
  // number plate 190 m before it, the call signal 160 m (dark: no registration yet), the entry sleeper signal 27 m (may
  // enter), and the switch signal at the frog, in place of the red indicator. They and their limit stay as for any
  // facing switch until registration is built (the later issue).
  _speedSwitch(sw, indicator) {
    const route = this.game.route, frog = sw.frog ?? FROG, add = (obj, s, how) => { if (s < 5) return; how(obj, s); this.objects.add(obj); };
    add(makeSwitchNumberPlate(sw.speedSwitch.number), sw.s - 190, (o, s) => this._mount(o, s, { movable: true }));
    add(makeCallSignal(), sw.s - 160, (o, s) => this._mount(o, s, { movable: true }));
    add(makeEntrySignal('go'), sw.s - 27, (o, s) => place(o, route, s, -1.1, 0, true));
    this._mount(indicator, sw.s + frog);
    this.signBoards.push({ kind: 'speedSwitch', number: sw.speedSwitch.number, s: Math.round(sw.s) });
  }

  // Put a signal or sign beside the track at route position s: at the kerb on the right when it
  // is close to the track (within 6.5 m), otherwise hung from the nearest span wire over the
  // track, where the driver sees it best. Never on a platform or against a facade; speed and
  // gradient signs that would stand on a platform move to just before it. (userData.mountedS: where it stands;
  // userData.hung: from a span)
  _mount(obj, s, { movable = false, hang = false } = {}) {
    const g = this.game, route = g.route, C = route.catenary || [], ud = obj.userData;
    const platformAt = (x) => g.stops.find((st) => x > (st.p0 ?? st.target - 30) - 4 && x < (st.p1 ?? st.target + 2) + 2);
    // movable: true moves a sign on a platform to just before it; 'after', for a sign that releases a limit (an end, a
    // Rychlostník), to just past it, so that no sign tells the driver to speed up before the limit lifts
    const after = movable === 'after';
    let onPlatform = platformAt(s);
    if (onPlatform && movable) { s = after ? (onPlatform.p1 ?? onPlatform.target + 2) + 6 : (onPlatform.p0 ?? onPlatform.target - 30) - 6; onPlatform = platformAt(s); }
    ud.mountedS = s;
    const hidePole = () => { if (ud.pole) ud.pole.visible = false; };
    const kerb = route.kerbAt ? route.kerbAt(s, -1) : null;
    if (kerb && !kerb.wall && kerb.lat <= 6.5 && !onPlatform && !hang) {
      place(obj, route, s, -kerb.lat, 0, true);
      return;
    }
    // a signal that must hang (its place is on a platform) takes a span up to 30 m away
    const reach = hang ? 30 : 16;
    // (a cross-span; one that must hang may also use a pole's bracket arm over the track. Not one
    // after s: the nearest span was often over the junction, the signal hung in its middle (user,
    // 2026-10-24); one that must hang takes such a span only when there is none before s)
    const spans = C.filter((c) => (hang ? c.L || c.R : c.L && c.R) && Math.abs(c.s - s) <= reach).sort((a, b) => Math.abs(a.s - s) - Math.abs(b.s - s));
    const span = spans.find((c) => (after ? c.s >= s - 2 : c.s <= s + 2)) || (hang ? spans[0] : null);
    if (span && ud.boardTop !== undefined) {
      ud.mountedS = span.s;
      // right of the tram: its half width, the overhang of the car ends in a curve, a margin and
      // the board's own half width (it used to hang 1.15 m out, over the tram's roof edge)
      hidePole();
      const box = new THREE.Box3().setFromObject(obj);
      const half = Math.max(0.2, (box.max.x - box.min.x) / 2);
      place(obj, route, span.s, -(tramClearance(route, span.s) + half), 0, true);
      ud.hung = true;
      obj.position.y = g.profile.height(span.s) + 5.04 - ud.boardTop;
      const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 1.25, 4), new THREE.MeshLambertMaterial({ color: 0x333333 }));
      rod.position.y = ud.boardTop + 0.62;
      obj.add(rod);
      return;
    }
    if (kerb && !kerb.wall && kerb.lat <= 12) { place(obj, route, s, -kerb.lat, 0, true); return; }
    place(obj, route, s, -2.6, 0, true);
  }

  // the head of a tram signal (or a gauntlet's: G.sig), an obstacle's, a runner's or a cross street's car's model, our
  // stop's sign: for the checks, the debug overlay and the people; null if none
  meshOf(o) {
    return this.heads.get(o) || this.obstacles.get(o) || this.runners.get(o) || this.crossCars.get(o) || this.stopSigns.get(o) || null;
  }

  // after a step the page draws from
  sync() {
    const g = this.game;
    for (const [sig, mesh] of this.heads) mesh.userData.set(sig.show.aspect, sig.show);
    for (const [G, mesh] of this.theirs) mesh.userData.set(G.their.aspect, G.their);
    for (const [d, mesh] of this.distants) mesh.userData.set(d.main.state === 'go' ? 'go' : 'stop', { goDir: 'straight' });
    for (const [sw, { indicator }] of this.switches) indicator.userData.set(sw.shown.dir, sw.shown.off);
    for (const [ob, mesh] of this.obstacles) this._obstacle(ob, mesh);
    this._runners();
    this._crossCars();
    this._driver();
  }

  // what the steps move, for the page to draw between the last two (src/between.js): the cross streets' cars at the
  // signalled crossings, the late passengers running for the doors, the obstacles, the driver with the switch iron
  movers() {
    const out = [...this.crossCars.values(), ...this.runners.values()];
    for (const [ob, mesh] of this.obstacles) if (ob.state !== 'gone') out.push(mesh);
    if (this.driver) out.push(this.driver);
    return out;
  }

  dispose() {
    this.scene.remove(this.objects);
    disposeModel(this.objects);
  }

  // an obstacle where it is (a parked car driving off out of the track, a pedestrian crossing it: ob.turn its heading
  // against the track's); a pedestrian shows once it walks, none once gone
  _obstacle(ob, mesh) {
    mesh.visible = ob.state !== 'gone' && !(ob.type === 'pedestrian' && ob.state === 'idle');
    if (!mesh.visible) return;
    const at = mesh.userData.at;
    if (at && at[0] === ob.s && at[1] === ob.lat && at[2] === ob.turn) return;
    mesh.userData.at = [ob.s, ob.lat, ob.turn];
    place(mesh, this.game.route, ob.s, ob.lat, 0, false);
    mesh.rotation.y += ob.turn;
  }

  // the late passengers running along the platform to the rear door (bobbing while they run); gone once aboard or
  // left far behind
  _runners() {
    const g = this.game, live = new Set();
    for (const r of g.runners) {
      live.add(r);
      let mesh = this.runners.get(r);
      if (!mesh) { mesh = makePerson(r.model); this.objects.add(mesh); this.runners.set(r, mesh); }
      const o = g.route.offset(r.s, r.lat), bob = r.state === 'run' ? Math.abs(Math.sin(r.s * 2.2)) * 0.08 : 0;
      mesh.position.set(o.x, g.profile.height(r.s) + 0.18 + bob, -o.y);
    }
    for (const [r, mesh] of this.runners) if (!live.has(r)) { this.objects.remove(mesh); this.runners.delete(r); }
  }

  // the cross streets' cars at the signalled junctions, on the right-hand side of their street, pitched with its slope
  _crossCars() {
    const g = this.game, ground = g.route.ground, live = new Set();
    for (const sig of g.signals) {
      const X = sig.xroad;
      if (!X) continue;
      for (const car of sig.cars) {
        live.add(car);
        let mesh = this.crossCars.get(car);
        if (!mesh) { mesh = makeCar(car.model); mesh.rotation.order = 'YXZ'; this.objects.add(mesh); this.crossCars.set(car, mesh); }
        const p = X.at(car.s), hx = p.hx * car.dir, hy = p.hy * car.dir;
        const lane = X.oneway ? 0 : Math.max(1.5, X.w / 4); // right-hand traffic
        const x = p.x + hy * lane, y = p.y - hx * lane;
        const zf = ground.at(x + hx * 1.6, y + hy * 1.6), zb = ground.at(x - hx * 1.6, y - hy * 1.6);
        mesh.position.set(x, (zf + zb) / 2 + 0.1, -y);
        mesh.rotation.y = Math.atan2(hx, -hy);
        mesh.rotation.x = -Math.atan2(zf - zb, 3.2);
      }
    }
    for (const [car, mesh] of this.crossCars) if (!live.has(car)) { this.objects.remove(mesh); disposeModel(mesh); this.crossCars.delete(car); }
  }

  // the driver out with the switch iron (src/game.js crowbar): out along the side of the tram, at the points, back
  _driver() {
    const g = this.game, a = g.action;
    if (!a?.driver) {
      if (this.driver) { this.objects.remove(this.driver); this.driver = null; }
      return;
    }
    if (!this.driver) {
      this.driver = makePerson(4);
      this.driver.children[1].material.color.set(0xff7a1a); // (the torso: a high-visibility vest)
      this.objects.add(this.driver);
    }
    const el = a.total - a.t, back = a.total - a.walk;
    let along, lat = -1.7, crouch = 1;
    if (el < a.walk) along = a.door + (a.at - a.door) * (el / a.walk);
    else if (el < back) { along = a.at; lat = -0.6; crouch = 0.7 + 0.08 * Math.sin(el * 5); }
    else along = a.at - (a.at - a.door) * Math.min(1, (el - back) / a.walk);
    const o = g.route.offset(along, lat);
    this.driver.position.set(o.x, g.profile.height(along) + 0.05, -o.y);
    this.driver.scale.y = crouch;
  }

  // the people on the platforms of the stop ahead and the one just passed (each stop's own stream: they stand where
  // they stood); once a drawn frame (src/main.js), as before #228: none in the checks' steps
  syncCrowd() {
    const g = this.game, st = g.stops[g.nextStop];
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(1, 1, 1), p = new THREE.Vector3();
    let n = 0;
    for (const stop of [g.stops[g.nextStop - 1], st]) {
      if (!stop || Math.abs(stop.target - g.tram.s) > 450) continue;
      const r = rng(stop.i * 977);
      const count = Math.min(stop === st ? st.waiting + st.ambient : stop.ambient, 55);
      for (let k = 0; k < count && n < 120; k++) {
        const along = stop.target - 2 - r() * 24, lat = -2.4 - r() * 1.6;
        const o = g.route.offset(along, lat);
        p.set(o.x, g.profile.height(along) + 0.18, -o.y);
        sc.set(1, 0.85 + r() * 0.3, 1);
        // facing the track (within ±40°), 3 in 10 towards where the tram comes from (±25°); one draw of r()
        // as before, so everyone stands where they stood (#251)
        const h = g.route.heading(along), v = r();
        const yaw = v < 0.3 ? Math.atan2(-h.hx, h.hy) + (v / 0.3 - 0.5) * 0.9 : Math.atan2(-h.hy, -h.hx) + ((v - 0.3) / 0.7 - 0.5) * 1.4;
        q.setFromEuler(new THREE.Euler(0, yaw, 0));
        m.compose(p, q, sc);
        this.crowd.setMatrixAt(n++, m);
      }
    }
    this.crowd.count = n;
    this.crowd.instanceMatrix.needsUpdate = true;
  }
}
