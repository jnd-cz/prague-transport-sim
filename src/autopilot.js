// Autopilot driver: plans a target speed from limits, stops, signals, obstacles and the tram
// ahead, then asks the vehicle's equipment for the force needed (incl. gradient); the T3's works its
// pedals as a careful driver (the advanced model, #221: src/tr37.js autoDrive). It also works
// the doors, departs on time, rings the bell, sands on slippery rail, sets IRC switches and
// passes overhead contacts (with the pantograph) drawing current or coasting. Used for "watch the ride" and for the
// headless rule tests (tools/autopilot.js).

const TRAM_GAP = 2; // m behind the tram ahead when stopping (D 1/2 § 27.6: at least 1 m)
const DECEL = 0.65; // planned braking (m/s2) behind something that moves, below B2 so there is margin
const PLAN_DECEL = 0.9; // … to a stop, a signal or a lower limit: step 3 on the level, as the drive's steps 1–3. A real ride on line 23 braked at about 0.9 at the end, on a heritage line whose drivers
// go milder (the user, 2026-11-07: "our autopilot can lean a bit on the faster side where it makes sense"); 0.65 lost 2–3 s a stop against main, which ran 0.7 m/s over its curve
const STOP_SHORT = 3; // m: behind something that moves (a tram, a car), the planned curve ends this far before it
const STOP_MARGIN = 0.8; // m: at a stop or a signal, the tram stands this far short of the point
const STAND_SHORT = 2.4; // m: standing this close is arrived (a stop zone may start only 2.5 m before the point)
const V_BUTTON = 4.2; // m/s: slow enough for the switch button: the accelerator stands at 30 or less coasting (ZR9, T3SU-24 § 8.2; tools/test_electric.py: 31 at 20 km/h), with the 1–2 km/h it comes in over the plan

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
    // (1.4 km/h under the limit, the penalty starting 3 km/h over it: at 15 km/h the old 2.2 km/h was a seventh of the speed, the user, 2026-11-07:
    // "our autopilot can lean a bit on the faster side where it makes sense")
    let vt = g.currentLimit / 3.6 - 0.4;
    let nl = g.nextLimitChange();
    // the deceleration to plan on: less on a steep downhill, where the electric brake has to hold the tram's weight too (70 ‰ takes
    // ≈0.7 of step 5's ≈1 m/s²: braking at 0.65 there ended on the track brakes)
    const gradeHere = g.profile.grade(tr.s - 7);
    // (and less on a slippery rail, as a driver knows it: half of what wet leaves hold)
    const planMax = Math.min(PLAN_DECEL, 0.5 * 9.81 * (g.muBase ?? 0.3));
    const planAt = (grade) => Math.max(0.2, Math.min(planMax, 0.7 * ((tr.eq.brakeForce(5, Math.max(tr.v, 2.5)) + 650 * tr.cars) / tr.inertia + (tr.mass * 9.81 * grade) / tr.inertia)));
    const limitDecel = planAt(gradeHere);
    const vLine = vt;
    const curveTo = (limit) => Math.sqrt((limit.v / 3.6) ** 2 + 2 * limitDecel * Math.max(0, limit.d - 12)) - 0.3;
    if (nl) vt = Math.min(vt, curveTo(nl));
    let vLimit = vt;
    let stopAt = null, fixed = false, fixedAt = null;
    // (fixed: a stop or a signal, which stays where it is; else something that can move off. Something nearer does not take
    // the fixed point away: a car crossing just past a stop, its point 6 m short of it, had the plan forget the stop for
    // a second and drive on the way in, line 22 seed 5 at Radošovická, line 37 seed 4 at U Elektry)
    const consider = (s, still = false) => { if (still && (fixedAt === null || s < fixedAt)) fixedAt = s; if (stopAt === null || s < stopAt) { stopAt = s; fixed = still; } };
    if (st) {
      const needStop = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if ((!st.served && needStop) || g.doorState !== 'closed') consider(st.target, true);
    }
    // a signal: when its GO starts blinking, stop if that is comfortable (~0.9 m/s2), else clear the
    // junction on it and keep going (the controller holds the phase for a committed tram); braking
    // for a blinking GO it could not stop for took it over the line on red (line 17 s 3158)
    const sig = g.signals.find((x) => x.s > tr.s + 0.2);
    if (this.stopFor && (this.stopFor !== sig || sig.state === 'go')) this.stopFor = null;
    if (sig && sig.state !== 'go') {
      const d = sig.s - 3 - tr.s;
      // (only a moving tram: one standing at the stop point stays; it went on red from there, s 14178.) Decided once, at the
      // first sight of the blinking, and a stop stays a stop while service braking (1.15 m/s²) still makes it: the test, met
      // again on the way down, turned a tram braking for it into one going through 82 m out at 41 km/h, which then slowed for
      // the junction's 15 km/h, spent the controller's 10 s and met red 7 m before the signal (line 23 towards Královka, seed 5)
      if (sig.state === 'warn' && this.goThrough !== sig && tr.v > 1) {
        if (this.stopFor !== sig && d < (tr.v * tr.v) / 1.8 + tr.v) this.goThrough = sig;
        else if (this.stopFor === sig && d < (tr.v * tr.v) / 2.3 + 0.3 * tr.v) { this.goThrough = sig; this.stopFor = null; }
        else this.stopFor = sig;
      }
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
    const dLeft = fixedAt === null ? null : fixedAt - tr.s - STOP_MARGIN;
    // (the steepest downhill between here and the point counts: a crest just before it took the brake's margin away)
    const stopDecel = dLeft === null || dLeft > 400 ? limitDecel : planAt(Math.min(gradeHere, g.profile.grade(tr.s + dLeft / 2 - 7), g.profile.grade(tr.s + dLeft - 7)));
    let vFixed = Infinity, vMoving = Infinity, stood = false;
    if (fixedAt !== null) {
      vFixed = Math.sqrt(2 * stopDecel * Math.max(0, dLeft));
      stood = tr.v < 0.1 && fixedAt - tr.s < STAND_SHORT;
      if (stood || dLeft <= 0) vFixed = 0;
      vt = Math.min(vt, vFixed);
    }
    // a turn under a contact where it will be braking anyway, for a stop just past it or for the switch's own limit: slow enough
    // there for the switch button, as a limit of its own, or it would take the drive pedal between the brake. (Where it
    // is still at speed there, the drive pedal is the way: nothing else draws the current.)
    const ct = g.nextContact();
    if (ct && ct.required === 'diverging' && tr.v > V_BUTTON) {
      const dc = ct.contact - tr.panto;
      const toLimit = nl && nl.d - 12 > dc ? curveTo({ v: nl.v, d: nl.d - dc }) : Infinity;
      const toPoint = fixedAt !== null && ct.contact + 4.5 < fixedAt ? Math.sqrt(2 * stopDecel * Math.max(0, fixedAt - STOP_MARGIN - ct.contact - 4.5)) : Infinity;
      const there = Math.min(toLimit, toPoint);
      if (dc > 0 && there > V_BUTTON && there < 0.75 * vLine) {
        nl = { v: V_BUTTON * 3.6, d: dc + 12 };
        vLimit = Math.min(vLimit, curveTo(nl));
        vt = Math.min(vt, vLimit);
      }
    }
    if (stopAt !== null && !fixed) {
      const d = stopAt - tr.s;
      // (the curve ends 3 m short: below ≈6 km/h the T3's electric brake fades and the shoes take ≈0.5 s to
      // come in, so a crawl up to the last 1.5 m overran stops and signals by 1–3 m, #241's checks; a driver
      // comes in slowly and lets the shoes stop it. The precise-stop bonus allows ±3 m.)
      vMoving = Math.max(Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, d - STOP_SHORT))), d > 1 ? 0.8 : 0);
      if (d < 1) vMoving = 0;
      vt = Math.min(vt, vMoving);
    }
    // how hard it slows by itself, rolling on the gradient with the preparation current (m/s²)
    const resist = 650 * tr.cars + 28 * tr.cars * tr.v + 4.2 * tr.v * tr.v;
    const aCoast = (resist + 700 * tr.cars) / tr.inertia + (tr.mass * 9.81 * gradeHere) / tr.inertia;
    // the approach: from the first brake pedal for this point until the tram stands, the point goes away, or something nearer
    // has taken it well under the curve (that may move off again, and the tram with it)
    if (fixedAt !== null && tr.notch < 0 && tr.v > 0.3 && tr.v >= vFixed - 0.5) this.approach = this.approach ?? fixedAt;
    if (this.approach != null && (fixedAt === null || Math.abs(this.approach - fixedAt) > 3 || tr.v < 0.05 || (!fixed && tr.v < vFixed - 1.5))) this.approach = null;
    const inApproach = this.approach != null;
    // drive only if still under the plan 2.5 s on: a careful driver coasts into a braking curve (on the T3
    // the brake builds slowly within ≈2.5 s of driving; it drove up to 16.5 km/h 11 m before Ruská and
    // overran, line 22 seed 4, #241's check)
    const look = Math.max(0, tr.v) * 2.5;
    let vtDrive = vt;
    if (nl) vtDrive = Math.min(vtDrive, Math.sqrt((nl.v / 3.6) ** 2 + 2 * limitDecel * Math.max(0, nl.d - 12 - look)) - 0.3);
    if (fixedAt !== null) {
      vtDrive = Math.min(vtDrive, Math.sqrt(Math.max(0, 2 * stopDecel * Math.max(0, dLeft - look))));
      // (it rolls there by itself: ČKD, T3SU-03 p. 5, "fully use coasting, above all when coming into stops")
      if (stood || (dLeft < 40 && aCoast > 0 && (tr.v * tr.v) / (2 * aCoast) >= dLeft)) vtDrive = 0;
      // (stopped short of the point: on, slowly)
      else if (tr.v < 0.1) vtDrive = Math.max(vtDrive, Math.min(vLimit, 1.2));
    }
    if (stopAt !== null && !fixed) {
      const d = stopAt - tr.s;
      vtDrive = Math.min(vtDrive, Math.max(Math.sqrt(Math.max(0, 2 * DECEL * Math.max(0, d - look - STOP_SHORT))), d > 1 ? 0.8 : 0));
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
    // (once on the curve to it, not from the moment a lower limit is in sight: that had it stop accelerating 300 m before every curve)
    const aToLimit = nl && nl.v / 3.6 < tr.v && tr.v >= curveTo(nl) - 0.3 ? (tr.v * tr.v - (nl.v / 3.6 - 0.3) ** 2) / (2 * Math.max(3, nl.d - 12)) : 0;
    // near a speed it holds, gently: a hard gain took it from one brake step's force to the next and from 14 to 10 km/h and
    // back down a gradient, and it asked for drive there; into a lower limit ahead, the deceleration that ends there, not
    // a lag behind it
    if (vt === vLimit) {
      const off = (tr.v > vt ? vt : vtDrive) - tr.v, gentle = Math.sign(off) * (0.35 * Math.min(Math.abs(off), 1) + 0.9 * Math.max(0, Math.abs(off) - 1));
      aPlan = Math.max(-1.1, Math.min(1.0, gentle));
      if (aToLimit > 0) aPlan = Math.max(-1.1, Math.min(aPlan, -aToLimit));
    }
    // on the curve to a fixed point: the deceleration that still ends there, whatever the brake's steps gave so far; too
    // fast for a speed limit or for something nearer as well, the harder of the two
    // (half a second ahead, the brake's own lag: a whole second left the deceleration below step 3 and 12 m of rolling at the end)
    const onCurve = dLeft !== null && (inApproach || tr.v >= Math.sqrt(2 * stopDecel * Math.max(0, dLeft - tr.v * 0.5)) - 0.02) && tr.v > 0.05;
    const aNeed = onCurve ? (tr.v * tr.v) / (2 * Math.max(0.3, dLeft)) : 0;
    const vOver = Math.min(vLimit, vMoving);
    const aWant = onCurve ? Math.max(-1.3, Math.min(-aNeed, -aToLimit, tr.v > vOver ? (vOver - tr.v) * 0.9 : 0)) : aPlan;
    const need = tr.inertia * aWant + tr.mass * 9.81 * grade + resist;
    const stand = g.doorState !== 'closed' || vt <= 0.05;
    const coast = (!onCurve && between) || (onCurve && need > -300) || (!onCurve && Math.abs(vt - tr.v) < 0.25 && Math.abs(need) < 3000);
    // urgent: harder braking than planned is needed now (a stop closer than the plan's distance)
    const urgent = stopAt !== null && tr.v > 1 && (tr.v * tr.v) / (2 * Math.max(0.5, stopAt - tr.s - 1.5)) > DECEL * 1.3;
    // a turn under a contact while braking or coasting in: the switch button draws the current, the drive pedal stays off;
    // too fast for the button (the accelerator over 30), only the drive pedal can: the wrong way otherwise
    // (the position still falls as it brakes: the pedal only at the last moment, the foot's 0.3 s before the contact, if that was not enough)
    const needPedal = wantPower === true && !tr.eq.buttonLive && (tr.eq.ls || tr.eq.p > 36 || ct.contact - tr.panto < tr.v * 0.3 + 1);
    const button = wantPower === true && !needPedal && (need < 0 || inApproach || coast);
    this.input.switchBtn = button;
    // slippery rail: sand where it decides something, pulling away or braking for a point (the equipment eases off a step): on every slip
    // and slide the box, 90 s for a shift, was dry half way along, and then a leaf patch on 50 ‰ could not be left at all
    // (a moment longer than the slip it stops: sand flickering on and off is no use). Pulling away, only where slipping wheels
    // (0.7 of the grip) do not climb with 0.15 m/s² to spare: a leaf patch over 26 ‰; on the level they still pull away, and the
    // box was still dry on lines 9, 17 and 22, with patches up 35–40 ‰ ahead (0.41 m/s² slipping: 38 ‰ at most). There, once it
    // slipped, until 3 m/s: sand for 1.5 s at a time slipped again after each
    const slipClimbs = 0.7 * 9.81 * g.muAt(tr.s) > 9.81 * Math.max(0, gradeHere) + 0.15;
    this.startSand = tr.v < 3 && !slipClimbs && need > 0 && (tr.slip || !!this.startSand);
    this.sandT = this.startSand || (tr.slide && (onCurve || urgent || hazard)) ? 1.5 : (this.sandT || 0) - dt;
    this.input.sand = this.sandT > 0;
    // (a hazard past the point it stops at anyway rings the bell and changes nothing else: it took the last metres' rule away,
    // step 5 at 4 km/h and 3.6 m short at Nádraží Modřany, line 17 seed 5)
    tr.eq.autoDrive({ force: need, stand, coast, power: button ? null : wantPower, urgent: urgent || (hazard && !(fixed && onCurve)), v: tr.v, dt, slip: tr.slip, slide: tr.slide,
      stopDist: stopAt === null ? null : stopAt - tr.s, noDrive: (inApproach || (onCurve && tr.v > 0.1)) && !needPedal, fixed, aNeed,
      aSoon: onCurve ? (tr.v * tr.v) / (2 * Math.max(0.3, dLeft - tr.v * 0.5)) : 0, aCoast, inertia: tr.inertia, grade, sandLeft: tr.sand > 0,
      speedErr: onCurve ? null : tr.v - vt });
    return { vt, stopAt, notch: tr.notch, fixed, aNeed, inApproach };
  }
}
