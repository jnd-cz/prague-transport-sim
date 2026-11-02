// Dev check helpers (not part of the game) for the benches that drive a whole line (u3, redruns): when
// our tram counts as stuck, and what stood in front of it then.

// A function to call once per chunk: our tram's position once it has not moved for 10 minutes, else
// null. A scheduled wait at a stop is not a deadlock: the clock starts at departure.
export function stuckWatch(game) {
  let lastS, lastMove = 0;
  return () => {
    if (lastS === undefined || Math.abs(game.tram.s - lastS) > 1) { lastS = game.tram.s; lastMove = game.clock; }
    const st = game.stops[game.nextStop];
    if (st?.arrived && game._atStop(st) && Math.abs(game.tram.v) < 0.05) lastMove = Math.max(lastMove, Math.min(game.clock, st.sched));
    return game.clock - lastMove > 600 ? Math.round(game.tram.s) : null;
  };
}

// What holds the tram: the autopilot's plan and what lies ahead of it. Each crossing car carries the
// chain of what it waits for (a car's id, 'our tram', 'tram', or a walker with what it does): the
// line 9 s 11221 gridlock ran car -> car -> car -> our tram (#92).
export function stuckScene(game, traffic, pilot) {
  const tr = game.tram, plan = pilot.step(game, 0) || {}, st = game.stops[game.nextStop];
  // (a walker: where it stands and why: waiting at the kerb for a car, crossing, on the pavement)
  const walker = (w) => ({ walker: true, state: w.waitKerb ? 'waits at the kerb' : w.door ? 'at a door' : 'walking', v: +(w.v ?? 0).toFixed(1), dir: w.dir });
  const waits = (car) => {
    const out = [];
    for (let c = car, n = 0; c && n < 8; n++) {
      const o = c.seen;
      // (the last car of the chain sees no car: why it stands - the tram, a light, a give-way)
      if (!o) {
        if (n) out.push({ id: c.id, v: +(c.vNow ?? 0).toFixed(1), conn: !!c.conn, yielding: !!c.yielding, keepClear: !!c.keepClear,
          light: c.lane?.light ? traffic.lightAspect(c.lane.light) : null, why: c.why ?? null, junction: c.jBlock ?? null, for: null });
        break;
      }
      out.push({ id: c.id, gap: +o.gap.toFixed(1), v: +(c.vNow ?? 0).toFixed(1), conn: !!c.conn, yielding: !!c.yielding, keepClear: !!c.keepClear, for: o.car ? o.car.id : o.walker ? walker(o.walker) : o.what });
      if (!o.car || out.some((x) => x.id === o.car.id)) break;
      c = o.car;
    }
    return out;
  };
  const sig = game.signals.find((q) => q.s > tr.s);
  return { s: Math.round(tr.s), v: tr.v, plan: { vt: plan.vt, stopAt: plan.stopAt && Math.round(plan.stopAt - tr.s) }, doors: game.doorState, action: !!game.action, hold: game.holdTimer,
    nextStop: st && { name: st.name, d: Math.round(st.target - tr.s), served: st.served, waiting: st.waiting, runners: (game.runners || []).length },
    signal: sig && { d: Math.round(sig.s - tr.s), state: sig.state, demand: !!sig.demand, t: sig.t },
    carsOnTrack: (game.carsOnTrack || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => Math.round(c.s - tr.s)),
    carsCrossing: (game.carsCrossing || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => ({ d: Math.round(c.s - tr.s), onTrack: c.onTrack, v: c.car.vNow, light: c.car.lane?.light ? traffic.lightAspect(c.car.lane.light) : null, waits: waits(c.car) })),
    tramAhead: game.tramAheadGap ? game.tramAheadGap() : null,
    obstacles: (game.obstacles || []).filter((o) => o.state !== 'gone' && o.s > tr.s && o.s - tr.s < 100).map((o) => ({ d: Math.round(o.s - tr.s), lat: o.lat, type: o.type, state: o.state })) };
}
