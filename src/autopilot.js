// Autopilot driver: plans a target speed from limits, stops, signals, obstacles and the tram
// ahead, then asks the vehicle's equipment for the force needed (incl. gradient); the T3's works its
// pedals as a careful driver (the advanced model, #221: src/tr37.js autoDrive). It also works
// the doors, departs on time, rings the bell, sands on slippery rail, sets IRC switches and
// passes overhead contacts (with the pantograph) drawing current or coasting. Used for "watch the ride" and for the
// headless rule tests (tools/autopilot.js).

import { muSpeed, sandedMu } from './tram.js';

const TRAM_GAP = 2; // m behind the tram ahead when stopping (D 1/2 § 27.6: at least 1 m)
const DECEL = 0.65; // planned braking (m/s2), below B2 so there is margin
const STOP_SHORT = 3; // m: the planned stop curve ends this far before the stop point
const SAG = 1.1, OVER = 0.6; // m/s: under the plan before pressing on, over it before braking (4 and 2 km/h)
// On slippery rail (#265): the driver knows the weather's grip (game.muBase), not where a leaf patch lies.
// Planned braking and the force asked for stay within GRIP_USE of the rail's grip at the speed (margin for
// the patches and the second car); a spin is noticed after REACT s, the drive eased off until the wheels
// grip, then tried one step lower (the user, 2026-11-04: "They ease of the drive and try again with less
// power"); sand at once braking harder than the rail allows ("he needs to apply sand quickly"), starting only
// on a grade or after spinning twice ("Only at grades where it would be difficult to get moving")
const GRIP_USE = 0.5, REACT = 0.5, LOW_MU = 0.25;

export class Autopilot {
  constructor() {
    this.bellCooldown = 0;
    this.input = { deadman: true, sand: false, switchBtn: false };
  }

  step(g, dt) {
    const tr = g.tram;
    // (in autumn it plans for a leaf patch with sand, not the rail between them: braking for the rail's 0.22 it
    // hit a patch 7 m before a stop and slid past it, line 17 leaves trace 2026-11-04)
    const muK = Math.min(g.muBase ?? 0.3, g.patches?.length ? sandedMu(0.06) : 1), lowMu = muK < LOW_MU, gripN = (v) => GRIP_USE * muK * muSpeed(v) * tr.mass * 9.81;
    const D = Math.min(DECEL, (gripN(11) / tr.inertia) * 0.9); // (planned at 40 km/h's grip)
    const st = g.stops[g.nextStop];
    this.bellCooldown -= dt;

    // doors: open at the platform, close once everyone is aboard and it is departure time
    if (st) {
      const atStop = tr.v < 0.05 && g._atStop(st);
      if (atStop && !st.served && g.doorState === 'closed') g.toggleDoors();
      // (and nobody is still running for it)
      if (atStop && st.served && st.waiting === 0 && st.alight === 0 && !g.runnersFor?.(st) && g.doorState === 'open' && g.clock >= st.sched) g.toggleDoors();
    }

    // target speed: line speed, upcoming restrictions, then everything we must stop for
    let vt = g.currentLimit / 3.6 - 0.6;
    const nl = g.nextLimitChange();
    if (nl) vt = Math.min(vt, Math.sqrt((nl.v / 3.6) ** 2 + 2 * D * Math.max(0, nl.d - 12)) - 0.3);
    let stopAt = null, stopTarget = null, creep = false;
    const consider = (s) => { if (stopAt === null || s < stopAt) stopAt = s; };
    if (st) {
      const needStop = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if ((!st.served && needStop) || g.doorState !== 'closed') { consider(st.target); stopTarget = st.target; }
    }
    // a signal: when its GO starts blinking, stop if that is comfortable (~0.9 m/s2), else clear the
    // junction on it and keep going (the controller holds the phase for a committed tram); braking
    // for a blinking GO it could not stop for took it over the line on red (line 17 s 3158)
    const sig = g.signals.find((x) => x.s > tr.s + 0.2);
    if (sig && sig.state !== 'go') {
      const d = sig.s - 3 - tr.s;
      // (only a moving tram: one standing at the stop point stays; it went on red from there, s 14178)
      if (sig.state === 'warn' && this.goThrough !== sig && tr.v > 1 && d < (tr.v * tr.v) / 1.8 + tr.v) this.goThrough = sig;
      // (red after all, the hold having run out while it crawled up behind something: stop if service
      // braking still can, line 17 s 10251)
      if (sig.state === 'stop' && this.goThrough === sig && d > (tr.v * tr.v) / 2.2 + 0.5) this.goThrough = null;
      // (a tram that stopped anyway, for the passengers at a stop whose stop point is the signal's, has
      // nothing to clear: it drove off on red after the doors closed, Čechův most s 14907, seed 4)
      if (this.goThrough === sig && tr.v < 0.3) this.goThrough = null;
      if (this.goThrough !== sig) consider(sig.s - 3);
    }
    let hazard = false;
    for (const ob of g.obstacles) {
      if (ob.state !== 'gone' && Math.abs(ob.lat) < 2.5 && ob.s > tr.s) {
        consider(ob.s - 8);
        if (ob.s - tr.s < 80) hazard = true;
      }
    }
    const gap = g.tramAheadGap();
    // (2 m behind the tram ahead, D 1/2 § 27.6: at least 1 m; 8 m since the prototype kept two 2-car sets off
    // long platforms, the user, #258)
    if (gap !== null) {
      consider(tr.s + gap - TRAM_GAP);
      const clear = g.keepClear(tr.s, tr.s + gap); // (not into a junction the tram ahead has not cleared)
      if (clear !== null) consider(clear);
    }
    // a car on our track ahead (shared lane, queuing on the tracks): stop behind it
    for (const c of g.carsOnTrack || []) if (c.s > tr.s && c.s - tr.s < 120) consider(c.s - 2.5 - 5);
    // a car crossing our track ahead (turning across, U3), or committed to it (too close to stop): stop
    // short of it until it is across, and ring the bell within 60 m (a car that went while we stood at a
    // stop before the junction was hit as we pulled away, line 17 s 16851)
    for (const c of g.carsCrossing || []) {
      if (c.s <= tr.s) continue;
      consider(c.s - 6);
      if (c.s - tr.s < 60 && tr.v > 1) hazard = true;
    }
    if (stopAt !== null) {
      const d = stopAt - tr.s;
      // (the curve ends 3 m short: below ≈6 km/h the T3's electric brake fades and the shoes take ≈0.5 s to
      // come in, so a crawl up to the last 1.5 m overran stops and signals by 1–3 m, #241's checks; a driver
      // comes in slowly and lets the shoes stop it. The precise-stop bonus allows ±3 m.)
      // (and from there it creeps at ≤ 3 km/h to 1 m short: a stop zone may start only 2.5 m before the point)
      // (the creep only towards a stop and more than 2.2 m short of it: within that it has stopped well,
      // and a stop zone may start 2.5 m before the point; short of a signal or a tram ahead it just stays)
      creep = stopAt === stopTarget && d > 2.2;
      vt = Math.min(vt, Math.max(Math.sqrt(Math.max(0, 2 * D * Math.max(0, d - STOP_SHORT))), creep ? 0.8 : 0));
      if (d < (stopAt === stopTarget ? 1 : STOP_SHORT)) vt = 0;
    }
    // drive only if still under the plan 2.5 s on: a careful driver coasts into a braking curve (on the T3
    // the brake builds slowly within ≈2.5 s of driving; it drove up to 16.5 km/h 11 m before Ruská and
    // overran, line 22 seed 4, #241's check)
    const look = Math.max(0, tr.v) * 2.5;
    let vtDrive = vt;
    if (nl) vtDrive = Math.min(vtDrive, Math.sqrt((nl.v / 3.6) ** 2 + 2 * D * Math.max(0, nl.d - 12 - look)) - 0.3);
    if (stopAt !== null) {
      const d = stopAt - tr.s;
      vtDrive = Math.min(vtDrive, Math.max(Math.sqrt(Math.max(0, 2 * D * Math.max(0, d - look - STOP_SHORT))), creep ? 0.8 : 0));
    }
    if (hazard && this.bellCooldown <= 0) { g.ringBell(); this.bellCooldown = 6; }

    // IRC: select the route direction for radio switches in range
    if (!g.opts.autoIrc) {
      for (const w of g.switches) {
        if (w.auto && !w.passed && !w.ircSet && w.s - tr.s > 2 && w.s - tr.s < 70) { g.irc(w.required === 'straight' ? 'straight' : w.divSide); break; }
      }
    }
    // overhead contact: the pantograph passes under it drawing current for the turn, coasting
    // for straight. Decide only for the last second or so, allowing for the controller's
    // ramp, so the tram can still start from a stop shortly before a contact.
    let wantPower = null;
    const ct = g.nextContact();
    if (ct) {
      const d = ct.contact - tr.panto, v = Math.max(0, tr.v);
      // a short pulse of J1 is enough for the turn (also while braking into a stop); for
      // straight the current must have died away (the controller ramps down in ~1 s)
      if (ct.required === 'diverging' && d < v * 0.5 + 1 && (v > 0.3 || vt > 0.5)) wantPower = true;
      if (ct.required === 'straight' && d < v * 1.3 + 1.5 && v > 0.4) wantPower = false;
    }

    // heating like a careful driver: seat heaters and cab heater by temperature, the waste-heat
    // flap open in the cold; and the heating cut-out held while coasting under a contact.
    // A driver turns one knob at a time and then lets the temperature settle: hysteresis bands
    // and at least 20 s between changes (it used to flick the cab heater every frame at 21 °C)
    const c = g.climate;
    this.heatHold = (this.heatHold ?? 0) - dt;
    if (this.heatHold <= 0) {
      const cold = c.tout < 14;
      const saloon = !cold ? 0 : c.tin < 15 ? 2 : c.tin < 18 ? Math.max(1, c.saloon) : c.tin > 21 ? 0 : c.tin > 19.5 ? Math.min(1, c.saloon) : c.saloon;
      const cab = !cold ? (c.tcab > 24 ? 1 : c.tcab < 22 ? 0 : c.cab) : c.tcab < 17 ? 3 : c.tcab < 20 ? Math.max(2, c.cab) : c.tcab > 22 ? Math.max(1, c.cab - 1) : c.cab;
      const flap = c.flap ? !(c.tin > 22 || c.tout > 12) : c.tout < 10 && c.tin < 20;
      if (saloon !== c.saloon) { c.saloon = saloon; this.heatHold = 20; }
      else if (cab !== c.cab) { c.cab = cab; this.heatHold = 20; }
      else if (flap !== c.flap) { c.flap = flap; this.heatHold = 20; }
    }
    this.input.cutout = wantPower === false && g.heatingDraws();

    // the force wanted: acceleration plus gravity on the gradient and the running resistance; the vehicle's
    // equipment works its own controls for it (the T3's pedals: src/tr37.js autoDrive)
    const grade = g.profile.grade(tr.s - 7);
    // (between the drive plan and the brake plan: coast)
    // drive, coast or brake, with bands as a driver holds a speed: press on once it has sagged SAG under
    // the plan and let go at it; brake once OVER above it (a little over the curve into a stop) and let go
    // at it; coast in between. Without the bands it pressed drive and brake every 5 s at 48 km/h and
    // pressed power at 1.6 km/h rolling into a stop (line 22 trace, 2026-11-04). The creep only starts a
    // tram standing short of its stop.
    const stopping = stopAt !== null && stopAt - tr.s < (tr.v * tr.v) / (2 * 0.5) + 15;
    if (this.mode === 'drive' && (tr.v >= vtDrive - 0.1 || (stopping && tr.v > 0.3))) this.mode = null;
    if (this.mode === 'brake' && tr.v <= vt - (stopping ? 0.15 : 0)) this.mode = null;
    if (!this.mode) {
      if (tr.v > vt + (stopping ? 0.15 : OVER)) this.mode = 'brake';
      // (standing well short of a signal or the tram ahead it closes up: coasting uphill in snow it stopped
      // 10 m short of a signal and never moved again, 2026-11-04)
      else if (stopping ? tr.v < 0.05 && (creep || (stopAt - tr.s > STOP_SHORT + 3 && vtDrive > 0.3)) : tr.v < vtDrive - SAG) this.mode = 'drive';
    }
    const aWant = this.mode === 'drive' ? Math.min(1.0, Math.max(0.3, (vtDrive - tr.v) * 0.9))
      : this.mode === 'brake' ? Math.max(-1.1, Math.min(-0.15, (vt - tr.v) * 0.9)) : 0;
    let need = tr.inertia * aWant + tr.mass * 9.81 * grade + 650 * tr.cars + 4.2 * tr.v * tr.v;
    // within the rail's grip on slippery rail (a steep start still gets what it takes to move, with sand)
    if (lowMu && need > 0) need = Math.min(need, Math.max(gripN(tr.v), tr.mass * 9.81 * grade + 650 * tr.cars + 0.15 * tr.inertia));
    // (rolling back: brake to a stand, then start again; it rolled back 20 m spinning in snow)
    const stand = g.doorState !== 'closed' || vt <= 0.05 || tr.v < -0.3;
    const coast = !this.mode;
    // urgent: harder braking than planned is needed now (a stop closer than the plan's distance)
    const urgent = stopAt !== null && tr.v > 1 && (tr.v * tr.v) / (2 * Math.max(0.5, stopAt - tr.s - 1.5)) > D * 1.3;
    // a turn under a contact while braking: the switch button draws the current, the drive pedal stays off
    const button = wantPower === true && need < 0;
    this.input.switchBtn = button;
    // a spin: noticed after REACT s, drive off until the wheels grip, then one step lower for a while
    this.spinT = tr.slip ? (this.spinT || 0) + dt : 0;
    if (this.spinT > REACT && !this.easing) {
      this.easing = true; this.spins = (this.spins || 0) + 1;
      this.cap = Math.max(1, (tr.notch > 0 ? tr.notch : 1) - 1);
    }
    if (this.easing && !tr.slipping) this.easing = false;
    this.capT = tr.slip ? 0 : (this.capT || 0) + dt;
    if (this.cap && (this.capT > 8 || tr.v > 8)) { this.cap = null; this.spins = 0; }
    // a slide: noticed after REACT s, the brake let off until the wheels roll, then braking a step lighter
    // with sand (the shoes held locked wheels locked for up to 10 s on leaves; easing a step at a time did
    // not free them). Not for an urgent stop: the track brakes do not depend on the rail's grip
    // (only a stop needing the track brakes keeps the pedal down: "urgent" at the gentle autumn plan, 0.57 m/s²,
    // held locked wheels at 17 → 5 km/h for 5.7 s)
    const hard = stopAt !== null && tr.v > 1 && (tr.v * tr.v) / (2 * Math.max(0.5, stopAt - tr.s - 1.5)) > 1.0;
    this.slideT = tr.slide ? (this.slideT || 0) + dt : 0;
    if (this.slideT > REACT && !this.freeing && !hard) {
      this.freeing = true;
      this.bCap = Math.min(-1, (tr.notch < 0 ? tr.notch : -1) + 1);
    }
    if (this.freeing && !tr.slipping) this.freeing = false;
    this.bCapT = tr.slide ? 0 : (this.bCapT || 0) + dt;
    if (this.bCap && (this.bCapT > 6 || tr.v < 1)) this.bCap = null;
    // sand: braking harder than the rail allows, or sliding; starting up a grade, or after two spins
    const braking = need < 0 && !stand;
    // (braking: near the rail's limit, 0.8 of its grip; at half of it the box was empty by stop 14 in snow)
    this.input.sand = tr.slide || (braking && lowMu && (urgent || -need > 1.6 * gripN(tr.v)))
      || (need > 0 && tr.v < 3 && ((grade > 0.02 && need > gripN(tr.v)) || this.spins >= 2) && tr.slip);
    tr.eq.autoDrive({ force: need, stand, coast, power: button ? null : wantPower, urgent: urgent || hazard, v: tr.v, dt, slip: tr.slip, slide: tr.slide,
      stopDist: stopAt === null ? null : stopAt - tr.s, maxStep: this.easing ? 0 : this.cap, minStep: hard ? null : this.freeing ? 0 : this.bCap, lowMu });
    return { vt, stopAt, notch: tr.notch };
  }
}
