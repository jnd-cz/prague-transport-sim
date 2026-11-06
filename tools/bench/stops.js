// Dev check (not part of the game): how the autopilot brings the tram to its stops (#351). A watcher on the
// u3 drive (tools/bench/u3.js, opts.also); in the page after loading:
//   const { run } = await import('/tools/bench/stops.js'); await run(seed)
// An approach runs from the first brake pedal with the stop within its braking distance at 0.4 m/s² (and 20 m) until
// the tram stands there.
// flips: the drive pedal after the brake pedal inside an approach, by what allowed it: ahead (a tram ahead short of the stop
// point: the user, #351, "unless you're following tram in front of you"), signal (a signal short of the stop point
// showed stop), car (a car on or crossing our track short of it), free (nothing: the plan changed its mind, which
// is what must stay at 0). shoesAtSpeed: approaches where the shoe brakes came fully in above 8 km/h (LO dropped).
// pulses: the brake pedal let off to zero and pressed again inside an approach. restarts: the tram stood short of
// the stop point and drove on. err: the stop point less the front at the stand (+ short, − over).

export function stopsWatch(game) {
  const R = { stops: [], flips: [], changes: 0, driveSteps: 0, steps: 0 };
  let a = null, cur = null, last = 0, lastA = 0, lastStep = 0, jf = 0;
  const finish = (st, tr) => {
    a.err = +(st.target - tr.s).toFixed(2);
    R.stops.push({ stop: st.name, s: Math.round(st.target), v0: +(a.v0 * 3.6).toFixed(0), d0: Math.round(a.d0), secs: +(game.clock - a.t0).toFixed(1), flips: a.flips.length,
      pulses: a.pulses, steps: a.changes, decel: +a.decel.toFixed(2), jerk: +a.jerk.toFixed(2), shoesAtSpeed: a.shoes, restarts: a.restarts, err: a.err });
    a = null;
  };
  return {
    before: () => null,
    after: () => {
      const tr = game.tram, n = tr.notch, st = game.stops[game.nextStop];
      R.steps++;
      if (n !== lastStep) { R.changes++; lastStep = n; }
      if (n > 0) R.driveSteps++;
      if (st !== cur) { cur = st; if (a) a = null; }
      if (st && !st.served && !a && !st._seen) {
        const d = st.target - tr.s, needs = !st.request || st.waiting > 0 || st.alightFrac > 0;
        if (needs && n < 0 && d > 0 && d < (tr.v * tr.v) / 0.8 + 20 && tr.v > 1) {
          a = { v0: tr.v, d0: d, t0: game.clock, flips: [], pulses: 0, changes: 0, decel: 0, jerk: 0, shoes: 0, restarts: 0, was: n, braked: true, stood: false, why: {} };
        }
      }
      if (a) {
        const d = st.target - tr.s;
        // what stood short of the stop point during this approach
        const gap = game.tramAheadGap?.();
        if (gap !== null && gap !== undefined && gap < d + 2) a.why.ahead = true;
        if (game.signals.some((x) => x.s > tr.s && x.s < st.target + 1 && x.state !== 'go')) a.why.signal = true;
        if ((game.carsOnTrack || []).some((c) => c.s > tr.s && c.s < st.target) || (game.carsCrossing || []).some((c) => c.s > tr.s && c.s < st.target)) a.why.car = true;
        if (game.obstacles.some((o) => o.state !== 'gone' && Math.abs(o.lat) < 2.5 && o.s > tr.s && o.s < st.target)) a.why.car = true;
        if (n !== a.was) {
          a.changes++;
          if (a.braked && n > 0) {
            // (standing short of the point and going on is a restart, counted apart; a real stand behind a signal or a car has its cause)
            const cause = a.why.ahead ? 'ahead' : a.why.signal ? 'signal' : a.why.car ? 'car' : a.stood ? 'short' : 'free';
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
      const by = (c) => R.flips.filter((f) => f.cause === c).length, errs = S.map((x) => Math.abs(x.err)).sort((p, q) => p - q);
      return { seed, stuck: stuck ?? null, stops: S.length, flipsFree: by('free'), flipsShort: by('short'), flipsAhead: by('ahead'), flipsSignal: by('signal'), flipsCar: by('car'),
        restarts: sum('restarts'), pulses: sum('pulses'), shoesAtSpeed: sum('shoesAtSpeed'), maxDecel: +max('decel').toFixed(2), maxJerk: +max('jerk').toFixed(2),
        errP90: errs.length ? errs[Math.floor(errs.length * 0.9)] : null, errMax: errs.length ? errs[errs.length - 1] : null, short: S.filter((x) => x.err > 3).length, over: S.filter((x) => x.err < -3).length,
        pedalChangesPerKm: +(R.changes / Math.max(1, game.tram.s / 1000)).toFixed(1), driveShare: +(R.driveSteps / Math.max(1, R.steps)).toFixed(3), simSeconds: Math.round(game.clock - (R.clock0 ?? 0)),
        comfort: Math.round(game.penalties.comfort || 0), flips: R.flips.slice(0, 40), worst: [...S].sort((p, q) => Math.abs(q.err) - Math.abs(p.err)).slice(0, 5) };
    },
  };
}

export async function run(seed = 1, opts = {}) {
  const { run: drive } = await import('./u3.js');
  const r = await drive(seed, { ...opts, also: [stopsWatch] });
  return r.also[0];
}
