// Autopilot driver: plans a target speed from limits, stops, signals, obstacles and the tram
// ahead, then asks the vehicle's equipment for the force needed (incl. gradient); the T3's works its
// pedals as a careful driver (the advanced model, #221: src/tr37.js autoDrive). It also works
// the doors, departs on time, rings the bell, sands on slippery rail, sets IRC switches and
// passes overhead contacts (with the pantograph) drawing current or coasting. Used for "watch the ride" and for the
// headless rule tests (tools/autopilot.js).

const TRAM_GAP = 2; // m behind the tram ahead when stopping (D 1/2 § 27.6: at least 1 m)
const DECEL = 0.65; // planned braking (m/s2), below B2 so there is margin
const STOP_SHORT = 3; // m: behind something that moves (a tram, a car), the planned curve ends this far before it
const STOP_MARGIN = 0.8; // m: at a stop or a signal, the tram stands this far short of the point
const STAND_SHORT = 2.4; // m: standing this close is arrived (a stop zone may start only 2.5 m before the point)

export class Autopilot {
  constructor() {
    this.bellCooldown = 0;
    this.input = { deadman: true, sand: false, switchBtn: false };
  }

  step(g, dt) {
    const tr = g.tram;
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
    if (nl) vt = Math.min(vt, Math.sqrt((nl.v / 3.6) ** 2 + 2 * DECEL * Math.max(0, nl.d - 12)) - 0.3);
    const vLimit = vt;
    let stopAt = null, fixed = false;
    // (fixed: a stop or a signal, which stays where it is; else something that can move off)
    const consider = (s, still = false) => { if (stopAt === null || s < stopAt) { stopAt = s; fixed = still; } };
    if (st) {
      const needStop = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if ((!st.served && needStop) || g.doorState !== 'closed') consider(st.target, true);
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
      if (this.goThrough !== sig) consider(sig.s - 3, true);
    }
    // past a signal, its crossing still ahead (stopped in the junction behind something): the driver no
    // longer sees the signal, and the cross street gives way to a tram in the junction; cars already on
    // the crossing drive off it first (the user, #268: "tram driver should wait until the tracks clear")
    const past = g.signals.find((x) => x.xroad && x.s <= tr.s && x.cross > tr.s + 1);
    if (past && past.cars.some((c) => Math.abs((past.xroad.sX - c.s) * c.dir) < 4 && c.v > 0.1)) consider(past.cross - 3);
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
    // Towards a stop or a signal the plan is one curve to the point, without a crawl at its end: the pedal changes then
    // come only from the deceleration still needed (aNeed), and once braking for it the drive pedal stays off (the
    // user, #351: "smooth braking towards stop sign without any jums to jízda unless you're following tram in front of
    // you"; on main the crawl's 3 km/h was held by drive pulses 1–2 m short). Behind something that moves it keeps
    // the curve ending 3 m short and the crawl up to it, so it closes up as a driver does.
    const dLeft = stopAt === null ? null : stopAt - tr.s - (fixed ? STOP_MARGIN : 0);
    let vStop = Infinity, stood = false;
    if (stopAt !== null) {
      const d = stopAt - tr.s;
      if (fixed) {
        vStop = Math.sqrt(2 * DECEL * Math.max(0, dLeft));
        stood = tr.v < 0.1 && d < STAND_SHORT;
        if (stood || dLeft <= 0) vStop = 0;
      } else {
        // (the curve ends 3 m short: below ≈6 km/h the T3's electric brake fades and the shoes take ≈0.5 s to
        // come in, so a crawl up to the last 1.5 m overran stops and signals by 1–3 m, #241's checks; a driver
        // comes in slowly and lets the shoes stop it. The precise-stop bonus allows ±3 m.)
        vStop = Math.max(Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, d - STOP_SHORT))), d > 1 ? 0.8 : 0);
        if (d < 1) vStop = 0;
      }
      vt = Math.min(vt, vStop);
    }
    // how hard it slows by itself, rolling on the gradient with the preparation current (m/s²)
    const gradeHere = g.profile.grade(tr.s - 7);
    const resist = 650 * tr.cars + 28 * tr.cars * tr.v + 4.2 * tr.v * tr.v;
    const aCoast = (resist + 700 * tr.cars) / tr.inertia + (tr.mass * 9.81 * gradeHere) / tr.inertia;
    // the approach: from the first brake pedal for this point until the tram stands (or the point goes away)
    if (fixed && tr.notch < 0 && tr.v > 0.3 && tr.v >= vStop - 0.5) { if (this.approach === undefined || this.approach === null) this.approach = stopAt; }
    if (this.approach !== null && this.approach !== undefined && (!fixed || Math.abs(this.approach - stopAt) > 3 || tr.v < 0.05)) this.approach = null;
    const inApproach = this.approach !== null && this.approach !== undefined;
    // drive only if still under the plan 2.5 s on: a careful driver coasts into a braking curve (on the T3
    // the brake builds slowly within ≈2.5 s of driving; it drove up to 16.5 km/h 11 m before Ruská and
    // overran, line 22 seed 4, #241's check)
    const look = Math.max(0, tr.v) * 2.5;
    let vtDrive = vt;
    if (nl) vtDrive = Math.min(vtDrive, Math.sqrt((nl.v / 3.6) ** 2 + 2 * DECEL * Math.max(0, nl.d - 12 - look)) - 0.3);
    if (stopAt !== null) {
      const d = stopAt - tr.s;
      if (fixed) {
        vtDrive = Math.min(vtDrive, Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, dLeft - look))));
        // (it rolls there by itself: ČKD, T3SU-03 p. 5, "fully use coasting, above all when coming into stops")
        if (stood || (dLeft < 40 && aCoast > 0 && (tr.v * tr.v) / (2 * aCoast) >= dLeft)) vtDrive = 0;
        // (stopped short of the point: on, slowly)
        else if (tr.v < 0.1) vtDrive = Math.max(vtDrive, Math.min(vLimit, 1.2));
      } else vtDrive = Math.min(vtDrive, Math.max(Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, d - look - STOP_SHORT))), d > 1 ? 0.8 : 0));
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
    const grade = gradeHere;
    // (between the drive plan and the brake plan: coast)
    const between = tr.v <= vt && tr.v >= vtDrive - 0.25 && vtDrive < vt - 0.25;
    let aPlan = Math.max(-1.1, Math.min(1.0, ((tr.v > vt ? vt : vtDrive) - tr.v) * 0.9));
    // near a speed it holds, gently: a hard gain took it from one brake step's force to the next and from 14 to 10 km/h and
    // back down a gradient, and it asked for drive there; into a lower limit ahead, the deceleration that ends there, not
    // a lag behind it
    if (vt === vLimit) {
      const off = (tr.v > vt ? vt : vtDrive) - tr.v, gentle = Math.sign(off) * (0.35 * Math.min(Math.abs(off), 1) + 0.9 * Math.max(0, Math.abs(off) - 1));
      aPlan = Math.max(-1.1, Math.min(1.0, gentle));
      if (nl && nl.v / 3.6 < tr.v) aPlan = Math.max(-1.1, Math.min(aPlan, -(tr.v * tr.v - (nl.v / 3.6 - 0.3) ** 2) / (2 * Math.max(3, nl.d - 12))));
    }
    // on the curve to a fixed point: the deceleration that still ends there, whatever the brake's steps gave so far; too
    // fast for a speed limit as well, the harder of the two
    // (the brake takes ≈1 s to come in: from the point where that second still leaves the curve's deceleration)
    const onCurve = fixed && dLeft !== null && (inApproach || tr.v >= Math.sqrt(2 * DECEL * Math.max(0, dLeft - tr.v)) - 0.02) && tr.v > 0.05;
    const aNeed = onCurve ? (tr.v * tr.v) / (2 * Math.max(0.3, dLeft)) : 0;
    const aWant = onCurve ? Math.max(-1.3, Math.min(-aNeed, tr.v > vLimit ? (vLimit - tr.v) * 0.9 : 0)) : aPlan;
    const need = tr.inertia * aWant + tr.mass * 9.81 * grade + resist;
    const stand = g.doorState !== 'closed' || vt <= 0.05;
    const coast = (!onCurve && between) || (onCurve && need > -300) || (!onCurve && Math.abs(vt - tr.v) < 0.25 && Math.abs(need) < 3000);
    // urgent: harder braking than planned is needed now (a stop closer than the plan's distance)
    const urgent = stopAt !== null && tr.v > 1 && (tr.v * tr.v) / (2 * Math.max(0.5, stopAt - tr.s - 1.5)) > DECEL * 1.3;
    // a turn under a contact while braking or coasting in: the switch button draws the current, the drive pedal stays off
    const button = wantPower === true && (need < 0 || inApproach || coast);
    this.input.switchBtn = button;
    this.input.sand = tr.slip || tr.slide; // slippery rail: sand (the equipment eases off a step)
    tr.eq.autoDrive({ force: need, stand, coast, power: button ? null : wantPower, urgent: urgent || hazard, v: tr.v, dt, slip: tr.slip, slide: tr.slide,
      stopDist: stopAt === null ? null : stopAt - tr.s, noDrive: inApproach || (onCurve && tr.v > 0.1), fixed, aNeed, aCoast, inertia: tr.inertia, grade,
      speedErr: onCurve ? null : tr.v - vt });
    return { vt, stopAt, notch: tr.notch, fixed, aNeed, inApproach };
  }
}
