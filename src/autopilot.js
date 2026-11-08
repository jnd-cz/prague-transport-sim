// Autopilot driver: plans a target speed from limits, stops, signals, obstacles and the tram
// ahead, then asks the vehicle's equipment for the force needed (incl. gradient); the T3's works its
// pedals as a careful driver (the advanced model, #221: src/tr37.js autoDrive). It also works
// the doors, departs on time, rings the bell, sands on slippery rail, sets IRC switches and
// passes overhead contacts (with the pantograph) drawing current or coasting. Used for "watch the ride" and for the
// headless rule tests (tools/autopilot.js).

const TRAM_GAP = 2; // m behind the tram ahead when stopping (D 1/2 § 27.6: at least 1 m)
const DECEL = 0.65; // planned braking (m/s2) behind something that moves, below B2 so there is margin
const PLAN_DECEL = 1.0; // … to a stop, a signal or a lower limit, the most on the level and empty (planAt: 0.85 of step 5 below that). Two real
// rides on line 23 (2026-10-31) braked late and firmly: from 23–25 km/h at 0.69 and 0.86 m/s² on average, 1.05–1.09 at p90, after ≈45 m of
// coasting; the user, 2026-11-07: "our autopilot can lean a bit on the faster side where it makes sense", "Later braking to match real
// driver". At 0.7 of step 5 a full set planned 0.63 and braked on step 3 from 140 m out
// s of coasting into the braking curve before a stop or a signal, at the speed the drive comes off: two real rides on line 23 (2026-10-31)
// took the drive pedal off 80–100 m out at ≈28–30 km/h and braked the last 25–30 m from ≈24 km/h. 8 s takes it off ≈90 m out at
// ≈28 km/h (as metres, 45 or 60, or half the way to a closer point, it drove up to 35 km/h 90 m out). Read from GPS the rides
// coasted 41–45 m, but the same reading takes a 32–37 m coast of the autopilot's for 7 m. ČKD, T3SU-03 p. 5: "fully use coasting,
// above all when coming into stops"; the user, 2026-11-07: "Later braking to match real driver"
const COAST_T = 8;
const STOP_SHORT = 3; // m: behind something that moves (a tram, a car), the planned curve ends this far before it
const STOP_MARGIN = 0.8; // m: at a stop or a signal, the tram stands this far short of the point
const STAND_SHORT = 2.4; // m: standing this close is arrived (a stop zone may start only 2.5 m before the point)
const V_BUTTON = 4.2; // m/s: slow enough for the switch button: the accelerator stands at 30 or less coasting (ZR9, T3SU-24 § 8.2; tools/test_electric.py: 31 at 20 km/h), with the 1–2 km/h it comes in over the plan
const V_BUTTON_COAST = 5.3; // m/s: the fastest the button still works coasting through (28 at 19 km/h coasting into Anděl, line 9 seed 1)

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
    // the deceleration to plan on: 0.85 of what step 5 gives, so less on a steep downhill, where the electric brake has to hold the tram's
    // weight too (70 ‰ takes ≈0.7 of step 5's ≈1 m/s²: braking at 0.65 there ended on the track brakes), and less with a full load
    const gradeHere = g.profile.grade(tr.s - 7);
    // (and less on a slippery rail, as a driver knows it: half of what wet leaves hold, less a downhill's pull; on dry rail step 5 binds
    // first. To a lower limit the whole pull, which is sure where the grip is not, to a point half of it: there the track brakes take a
    // slide, and nothing does for a limit. Down Chotkova's 55 ‰ half of 0.15's grip planned 0.74 m/s² where the grip held 0.56 after the
    // pull, and it came into the 20 km/h at 35, line 23 seed 2 in autumn; with the whole pull to the points too, the autumn runs' mean
    // delay rose by 100 s on lines 17 and 22)
    const mu = g.muBase ?? 0.3;
    // (0.85, the user, 2026-11-08: "a bit harder braking"; a phone on T3SUCS 7290 read 1.06 m/s² braking from 30-40 km/h, steps 4-5, and
    // whole stops from 20-40 km/h at 0.95-1.10, where 0.8 of step 5 planned 0.89)
    const planAt = (grade, pull = 0.5) => Math.max(0.2, Math.min(PLAN_DECEL, 9.81 * (0.5 * mu + pull * Math.min(0, grade)),
      0.85 * ((tr.eq.brakeForce(5, Math.max(tr.v, 2.5)) + 650 * tr.cars) / tr.inertia + (tr.mass * 9.81 * grade) / tr.inertia)));
    const limitDecel = planAt(gradeHere, 1);
    // (to a lower limit as to a point, the steepest downhill on the way counts: planned on the 23 ‰ where it began braking, it met 59 ‰,
    // where step 5 makes 0.67 m/s², and came into line 17's 15 km/h at s 17422 4.5 km/h over, seed 3)
    const limitPlan = (d) => (d > 400 ? limitDecel : planAt(Math.min(gradeHere, g.profile.grade(tr.s + d / 2 - 7), g.profile.grade(tr.s + d - 7)), 1));
    const vLine = vt;
    const curveTo = (limit) => Math.sqrt((limit.v / 3.6) ** 2 + 2 * limitPlan(limit.d) * Math.max(0, limit.d - 12)) - 0.3;
    if (nl) vt = Math.min(vt, curveTo(nl));
    let vLimit = vt;
    let stopAt = null, fixed = false, fixedAt = null, stopWhy = null;
    // (fixed: a stop or a signal, which stays where it is; else something that can move off. Something nearer does not take
    // the fixed point away: a car crossing just past a stop, its point 6 m short of it, had the plan forget the stop for
    // a second and drive on the way in, line 22 seed 5 at Radošovická, line 37 seed 4 at U Elektry)
    // (why: what it stops for, for the track brakes' rule and the logs: stop, signal, junction, walker, tram, car)
    const consider = (s, still = false, why = null) => { if (still && (fixedAt === null || s < fixedAt)) fixedAt = s; if (stopAt === null || s < stopAt) { stopAt = s; fixed = still; stopWhy = why; } };
    if (st) {
      const needStop = !st.request || st.waiting > 0 || st.alightFrac > 0;
      if ((!st.served && needStop) || g.doorState !== 'closed') consider(st.target, true, 'stop');
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
      if (this.goThrough !== sig) consider(sig.s - 3, true, 'signal');
    }
    // past a signal, its crossing still ahead (stopped in the junction behind something): the driver no
    // longer sees the signal, and the cross street gives way to a tram in the junction; cars already on
    // the crossing drive off it first (the user, #268: "tram driver should wait until the tracks clear")
    const past = g.signals.find((x) => x.xroad && x.s <= tr.s && x.cross > tr.s + 1);
    if (past && past.cars.some((c) => Math.abs((past.xroad.sX - c.s) * c.dir) < 4 && c.v > 0.1)) consider(past.cross - 3, false, 'junction');
    let hazard = false;
    for (const ob of g.obstacles) {
      if (ob.state !== 'gone' && Math.abs(ob.lat) < 2.5 && ob.s > tr.s) {
        consider(ob.s - 8, false, ob.type === 'pedestrian' ? 'walker' : 'obstacle');
        if (ob.s - tr.s < 80) hazard = true;
      }
    }
    const gap = g.tramAheadGap();
    // (2 m behind the tram ahead, D 1/2 § 27.6: at least 1 m; 8 m since the prototype kept two 2-car sets off
    // long platforms, the user, #258)
    if (gap !== null) {
      consider(tr.s + gap - TRAM_GAP, false, 'tram');
      const clear = g.keepClear(tr.s, tr.s + gap); // (not into a junction the tram ahead has not cleared)
      if (clear !== null) consider(clear, false, 'junction');
    }
    // a car on our track ahead (shared lane, queuing on the tracks): stop behind it
    for (const c of g.carsOnTrack || []) if (c.s > tr.s && c.s - tr.s < 120) consider(c.s - 2.5 - 5, false, 'car');
    // a car crossing our track ahead (turning across, U3), or committed to it (too close to stop): stop
    // short of it until it is across, and ring the bell within 60 m (a car that went while we stood at a
    // stop before the junction was hit as we pulled away, line 17 s 16851)
    for (const c of g.carsCrossing || []) {
      if (c.s <= tr.s) continue;
      consider(c.s - 6, false, 'car');
      if (c.s - tr.s < 60 && tr.v > 1) hazard = true;
    }
    // Towards a stop or a signal the plan is one curve to the point, without a crawl at its end: the pedal changes then
    // come only from the deceleration still needed (aNeed), and once braking for it the drive pedal stays off (the
    // user, #351: "smooth braking towards stop sign without any jums to jízda unless you're following tram in front of
    // you"; on main the crawl's 3 km/h was held by drive pulses 1–2 m short). Behind something that moves it keeps
    // the curve ending 3 m short and the crawl up to it, so it closes up as a driver does.
    const dLeft = fixedAt === null ? null : fixedAt - tr.s - STOP_MARGIN;
    // (the steepest downhill between here and the point counts: a crest just before it took the brake's margin away)
    const stopDecel = dLeft === null || dLeft > 400 ? planAt(gradeHere) : planAt(Math.min(gradeHere, g.profile.grade(tr.s + dLeft / 2 - 7), g.profile.grade(tr.s + dLeft - 7)));
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
    // (the next diverging contact, not only the next one: at Anděl one for a switch passed straight comes 4 m before it, and the turn
    // went on the drive pedal at 18 km/h, 7.1 m short on the track brakes, line 9 seed 4 in autumn)
    const cd = ct && ct.required === 'diverging' ? ct : (g.switches || []).find((w) => !w.auto && !w.passedContact && w.required === 'diverging' && w.contact > tr.panto - 1);
    if (cd && tr.v > V_BUTTON) {
      const dc = cd.contact - tr.panto;
      const toLimit = nl && nl.d - 12 > dc ? curveTo({ v: nl.v, d: nl.d - dc }) : Infinity;
      const toPoint = fixedAt !== null && cd.contact + 4.5 < fixedAt ? Math.sqrt(2 * stopDecel * Math.max(0, fixedAt - STOP_MARGIN - cd.contact - 4.5)) : Infinity;
      const there = Math.min(toLimit, toPoint);
      if (dc > 0 && there > V_BUTTON && there < 0.75 * vLine) {
        nl = { v: V_BUTTON * 3.6, d: dc + 12 };
        vLimit = Math.min(vLimit, curveTo(nl));
        vt = Math.min(vt, vLimit);
      } else if (dc > 0 && there > V_BUTTON && toPoint < Infinity && Math.min(there, nl && nl.d - 12 <= dc ? nl.v / 3.6 - 0.4 : vLine) > V_BUTTON_COAST) {
        // (at speed the drive pedal makes the turn, ≈1.5 s without the brake: slow enough there for the point to stay on its curve after
        // that. Braking at 0.85 of step 5 it was on the curve at the contact 70 m before the stop, then needed 1.16 m/s² and the track
        // brakes; test drive "turn under a contact 70 m before the stop, at speed". Not where the limit has it pass slow enough to coast
        // through on the button: 5 m before Anděl's contact, the 20 km/h street's limit, this took the target under the line's and so the
        // coasting for the button away, a brake step lifted the accelerator over 30, and the drive pedal turned at 19 km/h, 8 m short on
        // the track brakes, line 9 seed 1)
        const dC = Math.max(0, fixedAt - STOP_MARGIN - cd.contact - 4.5);
        const vC = (-3 * stopDecel + Math.sqrt(9 * stopDecel * stopDecel + 8 * stopDecel * dC)) / 2;
        if (vC < there && (!nl || curveTo({ v: vC * 3.6, d: dc + 12 }) < curveTo(nl))) {
          nl = { v: vC * 3.6, d: dc + 12 };
          vLimit = Math.min(vLimit, curveTo(nl));
          vt = Math.min(vt, vLimit);
        }
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
    const resist = 650 * tr.cars + 28 * tr.cars * tr.v + 4.2 * (0.7 + 0.3 * tr.cars) * tr.v * tr.v; // (as src/tram.js, without the curves)
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
    if (nl) vtDrive = Math.min(vtDrive, Math.sqrt((nl.v / 3.6) ** 2 + 2 * limitPlan(nl.d) * Math.max(0, nl.d - 12 - look)) - 0.3);
    if (fixedAt !== null) {
      // (and what it still gains while the accelerator comes off, ≈1 s: up 37 ‰ on step 4 at 1.1 m/s² it drove from 14 to 20 km/h
      // 19 m before Hlušičkova, then needed more than the brake builds after driving and stood 3.5–4.6 m short on the emergency
      // brake, line 9 seeds 1 and 3). It coasts COAST_T into the curve, with the gradient's own slowing: up a
      // climb the drive stays on longer, down one it comes off sooner
      // (the coast too with the steepest downhill on its way: over a crest from 40 ‰ up into 50 ‰ down it came to the curve at 47 km/h,
      // where step 5 makes only 0.65 m/s², and stood on the track brakes; test drive "crest into the stop")
      const gain = Math.max(0, tr.a);
      const coastIn = Math.min(dLeft, Math.max(look, COAST_T * tr.v));
      const gIn = Math.min(gradeHere, g.profile.grade(tr.s + coastIn / 2 - 7), g.profile.grade(tr.s + coastIn - 7));
      const aCoastIn = aCoast + (tr.mass * 9.81 * (gIn - gradeHere)) / tr.inertia;
      vtDrive = Math.min(vtDrive, Math.sqrt(Math.max(0, 2 * stopDecel * Math.max(0, dLeft - coastIn - gain * 3.5) + 2 * aCoastIn * coastIn)) - gain);
      // (it rolls there by itself: ČKD, T3SU-03 p. 5, "fully use coasting, above all when coming into stops"; just after braking up to
      // 90 m out when it is there within 15 s: after a switch's 15 km/h 53 m before the stop it drove up to 17 km/h between two
      // brakings. Not pulling away from the stop before: with stops 60 m apart that took 9 % longer)
      const rolls = aCoast > 0 && (tr.v * tr.v) / (2 * aCoast) >= dLeft && (dLeft < 40 || (tr.eq.brakeT < 5 && dLeft < 90 && dLeft < 15 * tr.v));
      if (stood || rolls) vtDrive = 0;
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
    // (up to 1.0 m/s² from a stand, 1.2 above 20 km/h: a phone on T3SUCS 7290 read 0.95-0.99 pulling away, step 3, and 1.21-1.29 from 20 to
    // 40 km/h, steps 4-5; the user, 2026-11-08, on pressing step 4 at speed: "I think we can check that now")
    const aUp = tr.v > 20 / 3.6 ? 1.2 : 1.0;
    let aPlan = Math.max(-1.1, Math.min(aUp, ((tr.v > vt ? vt : vtDrive) - tr.v) * 0.9));
    // (once on the curve to it, not from the moment a lower limit is in sight: that had it stop accelerating 300 m before every curve)
    const aToLimit = nl && nl.v / 3.6 < tr.v && tr.v >= curveTo(nl) - 0.3 ? (tr.v * tr.v - (nl.v / 3.6 - 0.3) ** 2) / (2 * Math.max(3, nl.d - 12)) : 0;
    // near a speed it holds, gently: a hard gain took it from one brake step's force to the next and from 14 to 10 km/h and
    // back down a gradient, and it asked for drive there; into a lower limit ahead, the deceleration that ends there, not
    // a lag behind it
    if (vt === vLimit) {
      const off = (tr.v > vt ? vt : vtDrive) - tr.v, gentle = Math.sign(off) * (0.35 * Math.min(Math.abs(off), 1) + 0.9 * Math.max(0, Math.abs(off) - 1));
      aPlan = Math.max(-1.1, Math.min(aUp, gentle));
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
    // urgent: harder braking than planned is needed now (a stop closer than the plan's distance)
    const urgent = stopAt !== null && tr.v > 1 && (tr.v * tr.v) / (2 * Math.max(0.5, stopAt - tr.s - 1.5)) > DECEL * 1.3;
    // (the switch button works with the accelerator at 30 or under, and a light brake step lifts it: one for 0.3 m/s over the limit
    // 5 m before a contact took it from 29 to 34, the drive pedal made the turn 22 m before Anděl and the brake after it needed the
    // track brakes, 7.8 m short, line 9 seeds 2 and 5 downhill. Holding the line's limit and less than 0.6 m/s over it, it coasts
    // through on the button and brakes after; not on the way down to a lower limit or a point, where coasting ran 3 km/h over the
    // switch's limit and the pedal made the turn after all, and braking on step 5 had the position at 21)
    // (a diverging contact, not only the next one: at Anděl one for a switch passed straight came 4 m before it)
    // (and over the first 0.6 m/s of a dip under the line's limit, whose curve keeps 12 m in hand: the switch's 15 km/h just past Anděl's stop
    // dipped it 2 m before the contact, a brake step lifted the accelerator over 30 and the drive pedal turned at 19 km/h, then the track
    // brakes, line 9 seeds 1 and 2)
    const btnSoon = tr.eq.buttonLive && !!cd && cd.contact > tr.panto && cd.contact - tr.panto < tr.v * 2.5 + 2;
    // (up a climb the approach drives again where coasting would stand it more than 3 m short, until it rolls to within 1 m: with the
    // drive pedal held off it stood 15.7 m short of Mezi Hřbitovy up 25 ‰, line 9 seed 2 in autumn; on the level it does not, where
    // main crawled on pulses. On the curve it asked to coast as well: after the track brakes for a slide let go 53 m out at 20 km/h it
    // coasted up 25 ‰ and stood 13 m short there, seed 3)
    const reach = aCoast > 0 ? (tr.v * tr.v) / (2 * aCoast) : Infinity;
    this.upDrive = inApproach && fixed && aCoast > 0.15 && (reach < dLeft - 3 || (!!this.upDrive && reach < dLeft - 1));
    const shortUphill = this.upDrive;
    const coast = (!onCurve && between) || (onCurve && need > -300 && !shortUphill) || (!onCurve && Math.abs(vt - tr.v) < 0.25 && Math.abs(need) < 3000) ||
      (btnSoon && vt > vLine - 0.6 && !onCurve && !urgent && !hazard && tr.v > vt - 0.25 && tr.v < vt + 0.6);
    // a turn under a contact while braking or coasting in: the switch button draws the current, the drive pedal stays off;
    // too fast for the button (the accelerator over 30), only the drive pedal can: the wrong way otherwise
    // (the position still falls as it brakes: the pedal only at the last moment, the foot's 0.3 s before the contact, if that was not enough)
    const needPedal = wantPower === true && !tr.eq.buttonLive && (tr.eq.ls || tr.eq.p > 36 || ct.contact - tr.panto < tr.v * 0.3 + 1);
    const button = wantPower === true && !needPedal && (need < 0 || inApproach || coast);
    // (coasting in to a point, over what the drive may reach: holding a limit it pressed step 1 against a slight climb 105 m before
    // Kubánské náměstí, between braking for the limit and braking for the stop, line 22 seeds 2 and 3)
    const coastingIn = fixedAt !== null && tr.v > vtDrive + 0.3;
    this.input.switchBtn = button;
    // slippery rail: sand pulling away where it decides something, and braking on a slide (the equipment eases off a step): on every slip
    // and slide the box, then 90 s for a shift, was dry half way along, and then a leaf patch on 50 ‰ could not be left at all
    // (a moment longer than the slip it stops: sand flickering on and off is no use). Pulling away, only where slipping wheels
    // (0.7 of the grip) do not climb with 0.15 m/s² to spare: a leaf patch over 26 ‰; on the level they still pull away, and the
    // box was still dry on lines 9, 17 and 22, with patches up 35–40 ‰ ahead (0.41 m/s² slipping: 38 ‰ at most). There, once it
    // slipped, until 3 m/s: sand for 1.5 s at a time slipped again after each
    const slipClimbs = 0.7 * 9.81 * g.muAt(tr.s) > 9.81 * Math.max(0, gradeHere) + 0.15;
    this.startSand = tr.v < 3 && !slipClimbs && need > 0 && (tr.slip || !!this.startSand);
    // (braking: on every slide. Rationed while the box held 90 s, to a point within what a sliding tram needs, it slid twice without sand
    // braking for a lower limit down Chotkova's 55 ‰, held step 1 for 3 s after each and came into the 20 km/h at 35, line 23 seed 2 in
    // autumn; the box holds 25 minutes)
    this.sandT = this.startSand || tr.slide ? 1.5 : (this.sandT || 0) - dt;
    this.input.sand = this.sandT > 0;
    // the track brakes only in danger (the DPP T3 textbook: "se používá jen v případě nebezpečí"; the user, 2026-11-08: "those should be
    // used only in emergency like walker or car appearing in front of tram or the non dry weather where it can't stop"): a walker, a car
    // or an obstacle in the way, or a rail that does not hold. A stop, a signal, a junction or a tram ahead on dry rail is service, step 5
    const dryRail = !tr.slide && Math.min(g.muAt(tr.s), g.muAt(stopAt === null ? tr.s : Math.min(stopAt, tr.s + 80))) >= 0.25;
    const trackOk = !dryRail || stopWhy === 'walker' || stopWhy === 'obstacle' || stopWhy === 'car';
    // (a hazard past the point it stops at anyway rings the bell and changes nothing else: it took the last metres' rule away,
    // step 5 at 4 km/h and 3.6 m short at Nádraží Modřany, line 17 seed 5)
    tr.eq.autoDrive({ trackOk, force: need, stand, coast, power: button ? null : wantPower, urgent: urgent || (hazard && !(fixed && onCurve)), v: tr.v, dt, slip: tr.slip, slide: tr.slide,
      stopDist: stopAt === null ? null : stopAt - tr.s, noDrive: (inApproach || (onCurve && tr.v > 0.1) || coastingIn) && !needPedal && !shortUphill, fixed, aNeed,
      aSoon: onCurve ? (tr.v * tr.v) / (2 * Math.max(0.3, dLeft - tr.v * 0.5)) : 0, aCoast, inertia: tr.inertia, grade, sandLeft: tr.sand > 0, slideA: 0.75 * 9.81 * g.muAt(tr.s) + 9.81 * gradeHere,
      aService: (tr.eq.brakeForce(5, Math.max(tr.v, 2.5)) + 650 * tr.cars) / tr.inertia + (tr.mass * 9.81 * gradeHere) / tr.inertia,
      // (on a climb the old 0.35: coasting loses the speed there in seconds, and each new press steps up through 1-4 again)
      speedErr: onCurve ? null : tr.v - vt, holdSag: gradeHere > 0.02 ? 0.35 : Math.min(1.0, Math.max(0.35, 0.12 * vt)) });
    this.stopWhy = stopAt === null ? null : stopWhy; this.stopAtS = stopAt;
    return { vt, vtDrive, stopAt, notch: tr.notch, fixed, aNeed, inApproach };
  }
}
