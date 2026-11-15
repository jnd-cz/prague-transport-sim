// SPDX-License-Identifier: AGPL-3.0-or-later
// Dev check (not part of the game): how the autopilot brings the tram to its stops (#351). A watcher on the
// u3 drive (tools/bench/u3.js, opts.also); in the page after loading:
//   const { run } = await import('/tools/bench/stops.js'); await run(seed)
// An approach runs from the first brake pedal with the stop within its braking distance at the autopilot's 0.65 m/s²
// (and 10 m) until the tram stands there; a brake for a curve further out is not one, and driving on after it is fine.
// flips: the drive pedal after the brake pedal inside an approach, by what allowed it: ahead (a tram ahead short of the stop
// point: the user, #351, "unless you're following tram in front of you"), signal (a signal short of the stop point
// showed stop), car (a car on or crossing our track that it would stop for short of it), contact (a turn under a contact too fast for the
// switch button, only the drive pedal can draw it), free (nothing: the plan changed its mind, which
// is what must stay at 0). shoesAtSpeed: approaches where the shoe brakes came fully in above 8 km/h (LO dropped).
// pulses: the brake pedal let off to zero and pressed again inside an approach. restarts: the tram stood short of
// the stop point and drove on. err: the stop point less the front at the stand (+ short, − over; behindTram, behindCar: stands behind a tram
// or a car ahead at the stop, not judged by it). The timetable: late (the game's
// penalty for it), devMean (s after the schedule at the departures), lateStops (departures over 3 min after it); smooth driving must not
// cost it: 4 % slower on the same line took line 22's penalty from 17 to 509.
// The drive pedal's use, on the whole run: presses (from 0 to a drive step, "našlápnutí"), pressesRolling (of them while already moving
// faster than 1 m/s, the rest are the starts), brakeApplies (from coasting or drive to a brake step), the shares of the distance on drive,
// coasting and brake, coastStretches (coasting 20 m or more). In the wet: slipSecs, slideSecs, sandSecs, emergencies (the pedal to the floor),
// slips and slides as episodes, slidesAtStops (a slide begun within 30 m before the stop point, #265).
// Per stretch, the way to each stop (stretches: drive presses, brake applications, seconds from moving off the stop before it to standing
// served at this one), as the user counted them on a ride, "drive + braking" (#396); held, the seconds of it standing or under 1.5 m/s
// by what the autopilot stopped for (signal, gauntlet for a single track's signal, car, tram, walker, junction, obstacle, none), the
// last 30 m into the stop left out, and tt, the timetable's time there (departure to departure, so with this stop's dwell; #431).
// Energy a km (kWh/km, the traction only): lineKWh drawn from the wire, wasteKWh of it not turned into the motors' work (the starting
// resistors above all: a press held at a low step keeps them in the circuit), brakeKWh burnt in the brake resistors.

export function stopsWatch(game) {
  const R = { stops: [], flips: [], stretches: [], changes: 0, driveSteps: 0, steps: 0, presses: 0, pressesRolling: 0, brakeApplies: 0, driveM: 0, coastM: 0, brakeM: 0, coastStretches: 0, slip: 0, slide: 0, sand: 0, slips: 0, slides: 0, slidesAtStops: 0, emergencies: 0, emergencyAt: [], lineJ: 0, mechJ: 0, brakeJ: 0 };
  let heldClock = null, a = null, cur = null, last = 0, lastA = 0, lastStep = 0, jf = 0, lastS = null, coastRun = 0, lastClock = null, curTo = null;
  const finish = (st, tr) => {
    a.err = +(st.target - tr.s).toFixed(2);
    // (served behind a tram standing at the front of a long platform, as src/game.js lets a second set stop: not short of the point;
    // it counted Přístaviště 34.6 m short on line 17's 74 m platform, autumn seed 2; so behind a car standing on the track inside the
    // platform's zone: Karlovy lázně 11.8 m short, 8 m behind a car that had turned onto the track in front of the tram, line 17 seed 5)
    const gap = game.tramAheadGap?.();
    const car = [...(game.carsOnTrack || []), ...(game.carsCrossing || [])].some((c) => c.s > tr.s && c.s - tr.s < 12);
    a.behind = gap != null && gap < 12 ? 'tram' : car ? 'car' : false;
    R.stops.push({ stop: st.name, s: Math.round(st.target), v0: +(a.v0 * 3.6).toFixed(0), d0: Math.round(a.d0), secs: +(game.clock - a.t0).toFixed(1), flips: a.flips.length,
      pulses: a.pulses, steps: a.changes, decel: +a.decel.toFixed(2), jerk: +a.jerk.toFixed(2), shoesAtSpeed: a.shoes, restarts: a.restarts, err: a.err, behind: a.behind, arr: Math.round(game.clock - st.sched) });
    a = null;
  };
  return {
    before: () => null,
    after: () => {
      const tr = game.tram, n = tr.notch, st = game.stops[game.nextStop];
      R.steps++;
      // (the pedal's use over the whole run, read before lastStep moves on)
      if (n > 0 && lastStep <= 0) { R.presses++; if (tr.v > 1) R.pressesRolling++; }
      if (n < 0 && lastStep >= 0 && tr.v > 0.3) R.brakeApplies++;
      // (the stretch to a stop begins once the stop before it is served, so the pull-away counts toward the next one)
      const to = st && st.served ? game.stops[game.nextStop + 1] : st;
      if (to) {
        if (to !== curTo) {
          curTo = to;
          const k = game.stops.indexOf(to), fr = game.stops[k - 1];
          R.stretches.push({ to: to.name, drive: 0, brake: 0, t0: game.clock, tMove: null, held: {}, tt: fr && fr.sched != null && to.sched != null ? to.sched - fr.sched : null });
        }
        const q = R.stretches[R.stretches.length - 1];
        // (and, moving off, the quickest run there at the line's limits and the time in hand the autopilot saw, #242)
        if (q.tMove === null && tr.v > 0.3) { q.tMove = game.clock; q.quick = game.pilot?._run ? game.pilot._run(to.target) - game.pilot._run(tr.s) : null; q.hand = game.pilot?.inHand ?? null; q.sched = to.sched - game.clock; }
        // (the time held on the way, standing or under 1.5 m/s, by what the autopilot stops for: a single track's signal apart
        // from the others, and not the last metres into the stop itself, #431)
        const dtc = heldClock === null ? 0 : game.clock - heldClock;
        heldClock = game.clock;
        if (q.tMove !== null && tr.v < 1.5 && dtc > 0 && dtc < 1) {
          const p = game.pilot;
          let why = p?.stopWhy ?? 'none';
          if (why === 'stop' && p?.stopAtS != null && Math.abs(p.stopAtS - to.target) < 1 && to.target - tr.s < 30) why = null;
          else if (why === 'signal') { const nx = game.signals.find((x) => x.s > tr.s); if (nx?.gauntlet) why = 'gauntlet'; }
          if (why) q.held[why] = (q.held[why] || 0) + dtc;
        }
        if (n > 0 && lastStep <= 0) q.drive++;
        if (n < 0 && lastStep >= 0 && tr.v > 0.3) q.brake++;
      }
      if (n === -6 && lastStep !== -6) {
        R.emergencies++;
        // (each use of the track brakes: where, how fast, for what, how far it had, on what rail)
        const p = game.pilot, why = p?.stopWhy ?? null;
        R.emergencyAt.push({ s: Math.round(tr.s), kmh: +(tr.v * 3.6).toFixed(1), why, d: p?.stopAtS == null ? null : +(p.stopAtS - tr.s).toFixed(1),
          stop: st?.name ?? null, mu: +(game.muBase ?? 0.3).toFixed(2), slide: !!tr.slide, sandLeft: +(tr.sand ?? 0).toFixed(2) });
      }
      const ds = lastS === null ? 0 : Math.max(0, tr.s - lastS), dt = lastClock === null ? 0 : game.clock - lastClock;
      lastS = tr.s; lastClock = game.clock;
      if (n > 0) R.driveM += ds; else if (n < 0) R.brakeM += ds; else R.coastM += ds;
      if (n === 0) coastRun += ds; else { if (coastRun >= 20) R.coastStretches++; coastRun = 0; }
      if (tr.slip) R.slip += dt;
      // (the traction's power: tr.electric is the wire's (+) or the brake resistors' (−); the motors' work is the drive force by the speed)
      if (tr.electric > 0) { R.lineJ += tr.electric * dt; R.mechJ += Math.max(0, tr.drive * tr.v) * dt; } else R.brakeJ -= tr.electric * dt;
      if (tr.slide) R.slide += dt;
      // (and as episodes, #265: a spin or a slide from its start; a slide at a stop, its start within 30 m before the stop point)
      if (tr.slip && !R.wasSlip) R.slips++;
      if (tr.slide && !R.wasSlide) { R.slides++; if (st && !st.served && st.target - tr.s < 30 && st.target - tr.s > -5) R.slidesAtStops++; }
      R.wasSlip = !!tr.slip; R.wasSlide = !!tr.slide;
      if (tr.sanding) R.sand += dt;
      if (n !== lastStep) { R.changes++; lastStep = n; }
      if (n > 0) R.driveSteps++;
      if (st !== cur) { cur = st; if (a) a = null; }
      if (st && !st.served && !a && !st._seen) {
        const d = st.target - tr.s, needs = !st.request || st.waiting > 0 || st.alightFrac > 0;
        if (needs && n < 0 && d > 0 && d < (tr.v * tr.v) / 1.3 + 10 && tr.v > 1) {
          a = { v0: tr.v, d0: d, t0: game.clock, flips: [], pulses: 0, changes: 0, decel: 0, jerk: 0, shoes: 0, restarts: 0, was: n, braked: true, stood: false, why: {} };
        }
      }
      if (a) {
        const d = st.target - tr.s;
        // what stood short of the stop point during this approach
        const gap = game.tramAheadGap?.();
        if (gap !== null && gap !== undefined && gap < d + 2) a.why.ahead = true;
        if (game.signals.some((x) => x.s > tr.s && x.s < st.target + 1 && x.state !== 'go')) a.why.signal = true;
        // (its stopping point, which the autopilot takes 6–8 m short of it, as src/autopilot.js)
        if ((game.carsOnTrack || []).some((c) => c.s > tr.s && c.s - 7.5 < st.target) || (game.carsCrossing || []).some((c) => c.s > tr.s && c.s - 6 < st.target)) a.why.car = true;
        if (game.obstacles.some((o) => o.state !== 'gone' && Math.abs(o.lat) < 2.5 && o.s > tr.s && o.s - 8 < st.target)) a.why.car = true;
        if (n !== a.was) {
          a.changes++;
          if (a.braked && n > 0) {
            // (standing short of the point and going on is a restart, counted apart; a real stand behind a signal or a car has its cause)
            const ct = game.nextContact?.(), under = ct && ct.required === 'diverging' && ct.contact - tr.panto < tr.v * 1.5 + 2;
            const cause = a.why.ahead ? 'ahead' : a.why.signal ? 'signal' : a.why.car ? 'car' : under ? 'contact' : a.stood ? 'short' : 'free';
            a.flips.push(cause);
            R.flips.push({ cause, stop: st.name, s: Math.round(tr.s), v: +(tr.v * 3.6).toFixed(1), d: +d.toFixed(1), step: n, stood: a.stood });
            a.braked = false;
            a.why = {};
          }
          if (n < 0) a.braked = true;
          if (a.was === 0 && n < 0 && a.released) a.pulses++;
          if (a.was < 0 && n === 0) a.released = true;
          a.was = n;
        }
        if (tr.v < 0.05) a.stood = true;
        else if (a.stood && n > 0) { a.restarts++; a.stood = false; }
        a.decel = Math.max(a.decel, -tr.a);
        // (jerk over about 0.2 s: one step's difference is the integration's, not what a passenger feels)
        jf += ((tr.a - lastA) * 30 - jf) * 0.17;
        a.jerk = Math.max(a.jerk, Math.abs(jf));
        if (tr.eq.shoe === 2 && tr.v > 8 / 3.6 && !a.shoeSeen) { a.shoes++; a.shoeSeen = true; }
        if (tr.v < 0.05 && game._atStop(st)) { st._seen = true; finish(st, tr); }
      }
      lastA = tr.a;
      last = n;
    },
    result: (seed, stuck) => {
      const S = R.stops, sum = (k) => S.reduce((t, x) => t + x[k], 0), max = (k) => S.reduce((t, x) => Math.max(t, x[k]), 0);
      const own = S.filter((x) => !x.behind);
      const by = (c) => R.flips.filter((f) => f.cause === c).length, errs = own.map((x) => Math.abs(x.err)).sort((p, q) => p - q);
      const devs = (game.log || []).map((x) => x.dev).filter((x) => x !== undefined && x !== null);
      return { seed, stuck: stuck ?? null, stops: S.length, flipsFree: by('free'), flipsShort: by('short'), flipsAhead: by('ahead'), flipsSignal: by('signal'), flipsCar: by('car'), flipsContact: by('contact'),
        restarts: sum('restarts'), pulses: sum('pulses'), shoesAtSpeed: sum('shoesAtSpeed'), maxDecel: +max('decel').toFixed(2), maxJerk: +max('jerk').toFixed(2),
        errP90: errs.length ? errs[Math.floor(errs.length * 0.9)] : null, errMax: errs.length ? errs[errs.length - 1] : null, short: own.filter((x) => x.err > 3).length, over: own.filter((x) => x.err < -3).length, behindTram: S.filter((x) => x.behind === 'tram').length, behindCar: S.filter((x) => x.behind === 'car').length,
        pedalChangesPerKm: +(R.changes / Math.max(1, game.tram.s / 1000)).toFixed(1), driveShare: +(R.driveSteps / Math.max(1, R.steps)).toFixed(3), simSeconds: Math.round(game.clock - (R.clock0 ?? 0)),
        presses: R.presses, pressesPerKm: +(R.presses / Math.max(1, game.tram.s / 1000)).toFixed(2), pressesPerStop: +(R.presses / Math.max(1, S.length)).toFixed(2), pressesRolling: R.pressesRolling,
        brakeApplies: R.brakeApplies, driveM: Math.round(R.driveM), coastM: Math.round(R.coastM), brakeM: Math.round(R.brakeM), coastStretches: R.coastStretches,
        lineKWh: +(R.lineJ / 3.6e6 / Math.max(0.1, game.tram.s / 1000)).toFixed(3), wasteKWh: +((R.lineJ - R.mechJ) / 3.6e6 / Math.max(0.1, game.tram.s / 1000)).toFixed(3), brakeKWh: +(R.brakeJ / 3.6e6 / Math.max(0.1, game.tram.s / 1000)).toFixed(3),
        slipSecs: +R.slip.toFixed(1), slideSecs: +R.slide.toFixed(1), slips: R.slips, slides: R.slides, slidesAtStops: R.slidesAtStops, sandSecs: +R.sand.toFixed(1), sandLeft: +(game.tram.sand ?? 0).toFixed(2), emergencies: R.emergencies, emergencyAt: R.emergencyAt,
        comfort: Math.round(game.penalties.comfort || 0), overspeed: Math.round(game.penalties.speed || 0), late: Math.round(game.penalties.late || 0),
        devMean: devs.length ? Math.round(devs.reduce((t, x) => t + x, 0) / devs.length) : 0, lateStops: devs.filter((x) => x > 180).length, flips: R.flips.slice(0, 40), worst: [...S].sort((p, q) => Math.abs(q.err) - Math.abs(p.err)).slice(0, 5),
        // (arrival against the timetable's time, which is the departure: arrOnTime the share within ±30 s of it, arrEarly the stops
        // reached more than 30 s before it, where the tram then stands, arrMean in s; #242. The terminus is left out)
        ...((A) => ({ arrOnTime: A.length ? +(A.filter((x) => Math.abs(x) <= 30).length / A.length).toFixed(2) : null, arrEarly: A.filter((x) => x < -30).length,
          arrMean: A.length ? Math.round(A.reduce((t, x) => t + x, 0) / A.length) : null, arrs: A }))(S.slice(0, -1).map((x) => x.arr)),
        stretches: R.stretches.map((q, i) => ({ to: q.to, drive: q.drive, brake: q.brake, secs: Math.round((R.stretches[i + 1]?.t0 ?? game.clock) - (q.tMove ?? q.t0)), quick: q.quick == null ? null : Math.round(q.quick), hand: q.hand == null ? null : Math.round(q.hand), sched: q.sched == null ? null : Math.round(q.sched), tt: q.tt == null ? null : Math.round(q.tt), held:Object.fromEntries(Object.entries(q.held).map(([k, v]) => [k, Math.round(v)])) })) };
    },
  };
}

// (opts.load: the passengers held at this share of the capacity all the way, before and after each step: how the timetable and the
// driving follow the load; boarding still slows in a full car, src/game.js)
const loadWatch = (share) => (game) => {
  const hold = () => { game.tram.passengers = Math.round(share * game.tram.capacity); };
  return { before: hold, after: hold, result: () => null };
};

export async function run(seed = 1, opts = {}) {
  const { run: drive } = await import('./u3.js');
  const r = await drive(seed, { ...opts, also: opts.load != null ? [stopsWatch, loadWatch(opts.load)] : [stopsWatch] });
  // (opts.full: with what the drive itself found, for the weather's stress test)
  return opts.full ? { ...r.also[0], hits: r.hits, collisions: r.collisions, signalPenalty: r.signalPenalty, signalEvents: r.signalEvents, collisionPenalty: r.collisionPenalty, stuckScene: r.stuckScene } : r.also[0];
}
