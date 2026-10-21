// Autopilot driver: plans a target speed from limits, stops, signals, obstacles and the tram
// ahead, then picks the controller notch from the forces needed (incl. gradient). It also works
// the doors, departs on time, rings the bell, sands on slippery rail, sets IRC switches and
// passes overhead contacts with or without current. Used for "watch the ride" and for the
// headless rule tests (tools/autopilot.js).
import { T3 } from './tram.js';

const DECEL = 0.65; // planned braking (m/s2), below B2 so there is margin

export class Autopilot {
  constructor() {
    this.hold = 0;       // s until the notch may change again (smooth, fewer clicks)
    this.bellCooldown = 0;
    this.input = { deadman: true, sand: false };
  }

  step(g, dt) {
    const tr = g.tram;
    const st = g.stops[g.nextStop];
    this.bellCooldown -= dt;
    this.hold -= dt;

    // doors: open at the platform, close once everyone is aboard and it is departure time
    if (st) {
      const atStop = tr.v < 0.05 && tr.s > st.target - 4 && tr.s < st.target + 12;
      if (atStop && !st.served && g.doorState === 'closed') g.toggleDoors();
      if (atStop && st.served && st.waiting === 0 && st.alight === 0 && g.doorState === 'open' && g.clock >= st.sched) g.toggleDoors();
    }

    // target speed: line speed, upcoming restrictions, then everything we must stop for
    let vt = g.currentLimit / 3.6 - 0.6;
    const nl = g.nextLimitChange();
    if (nl) vt = Math.min(vt, Math.sqrt((nl.v / 3.6) ** 2 + 2 * DECEL * Math.max(0, nl.d - 12)) - 0.3);
    let stopAt = null;
    const consider = (s) => { if (stopAt === null || s < stopAt) stopAt = s; };
    if (st) {
      const needStop = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if ((!st.served && needStop) || g.doorState !== 'closed') consider(st.target);
    }
    const sig = g.signals.find((x) => x.s > tr.s + 0.2);
    if (sig && sig.state !== 'go') consider(sig.s - 3);
    let hazard = false;
    for (const ob of g.obstacles) {
      if (ob.state !== 'gone' && Math.abs(ob.lat) < 2.5 && ob.s > tr.s) {
        consider(ob.s - 8);
        if (ob.s - tr.s < 80) hazard = true;
      }
    }
    const gap = g.tramAheadGap();
    if (gap !== null) consider(tr.s + gap - 8);
    if (stopAt !== null) {
      const d = stopAt - tr.s;
      vt = Math.min(vt, Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, d - 1.5))));
      if (d < 1.5) vt = 0;
    }
    if (hazard && this.bellCooldown <= 0) { g.ringBell(); this.bellCooldown = 6; }

    // IRC: select the route direction for radio switches in range
    if (!g.opts.autoIrc) {
      for (const w of g.switches) {
        if (w.auto && !w.passed && !w.ircSet && w.s - tr.s > 2 && w.s - tr.s < 70) { g.irc(w.required === 'straight' ? 'straight' : w.divSide); break; }
      }
    }
    // overhead contact: pass under it drawing current for the turn, coasting for straight
    let wantPower = null;
    const ct = g.nextContact();
    if (ct && ct.contact - tr.s < 25) wantPower = ct.required === 'diverging';

    // force-based notch choice: wanted acceleration plus gravity on the gradient
    const grade = g.profile.grade(tr.s - 7);
    const aWant = Math.max(-1.1, Math.min(1.0, (vt - tr.v) * 0.9));
    const need = tr.mass * (aWant + 9.81 * grade) + 650 + 4.2 * tr.v * tr.v;
    const pick = (forces, f) => { for (let k = 1; k <= 4; k++) if (forces[k] >= f) return k; return 4; };
    let notch;
    if (g.doorState !== 'closed') notch = -2;
    else if (vt <= 0.05) notch = tr.v > 1.5 || Math.abs(grade) > 0.03 ? -4 : -2;
    else if (Math.abs(vt - tr.v) < 0.25 && Math.abs(need) < 3000) notch = 0;
    else if (need > 0) notch = pick(T3.driveForce, need);
    else notch = -pick(T3.brakeForce, -need);
    if (wantPower === true) notch = Math.max(1, notch);
    if (wantPower === false) notch = Math.min(0, notch);
    // slippery rail: ease off one notch and sand
    this.input.sand = tr.slip || tr.slide;
    if (tr.slip && notch > 1) notch--;
    if (tr.slide && notch < -1) notch++;

    // change notches calmly unless braking harder is needed right now
    const urgent = notch < tr.notch && notch < 0 || wantPower !== null || vt <= 0.05;
    if (notch !== tr.notch && (this.hold <= 0 || urgent)) {
      tr.notch = notch;
      this.hold = 0.6;
    }
    return { vt, stopAt, notch: tr.notch };
  }
}
