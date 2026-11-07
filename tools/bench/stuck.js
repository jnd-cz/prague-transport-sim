// Dev check helpers (not part of the game) for the benches that drive a whole line (u3, redruns): when
// our tram counts as stuck, and what stood in front of it then.

// A function to call once per chunk: our tram's position once it has not got on for 10 minutes, else
// null. A scheduled wait at a stop is not a deadlock: the clock starts at departure. Getting on is
// forward: rocking a metre back and forth on a leaf patch up a climb ran three autumn runs into the
// page's 30 min timeout instead (a jump back of 100 m is a new run, not a roll).
export function stuckWatch(game) {
  let lastS, lastMove = 0;
  return () => {
    if (lastS === undefined || game.tram.s - lastS > 1 || game.tram.s < lastS - 100) { lastS = game.tram.s; lastMove = game.clock; }
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
  const id = (o) => !o ? null : o === tr ? 'our tram' : o.kind === 'road' ? `car${o.id}` : `${traffic.ahead.includes(o) ? 'ahead' : 'oncoming'}${o.id}`;
  const seen = (o) => !o ? null : o.car ? id(o.car) : o.tram ? id(o.tram) : o.walker ? walker(o.walker) : o.what;
  const waits = (car) => {
    const out = [], visited = new Set();
    for (let c = car; c && !visited.has(c) && out.length < 40; c = c.waitFor) {
      visited.add(c);
      out.push({ id: id(c), v: +(c.kind === 'road' ? c.vNow ?? 0 : c.v).toFixed(1),
        why: c.kind === 'road' ? c.why ?? null : c.stop?.why ?? null, for: id(c.waitFor),
        ...(c.kind === 'road' ? { gap: c.seen && +c.seen.gap.toFixed(1), seen: seen(c.seen), conn: !!c.conn,
          yielding: !!c.yielding, keepClear: !!c.keepClear, light: c.lane?.light ? traffic.lightAspect(c.lane.light) : null, junction: c.jBlock ?? null }
          : { s: Math.round(c.s), stopAt: c.stop && Math.round(c.stop.s), dwell: Math.max(0, c.dwell || 0) }) });
    }
    return out;
  };
  const sig = game.signals.find((q) => q.s > tr.s);
  const junction = game.signals.reduce((a, q) => !a || Math.abs(q.cross - tr.s) < Math.abs(a.cross - tr.s) ? q : a, null);
  const centre = game.route.at(junction?.cross ?? tr.s);
  return { s: Math.round(tr.s), v: tr.v, plan: { vt: plan.vt, stopAt: plan.stopAt && Math.round(plan.stopAt - tr.s) }, doors: game.doorState, action: !!game.action, hold: game.holdTimer,
    nextStop: st && { name: st.name, d: Math.round(st.target - tr.s), served: st.served, waiting: st.waiting, runners: (game.runners || []).length },
    signal: sig && { d: Math.round(sig.s - tr.s), state: sig.state, demand: !!sig.demand, t: sig.t },
    carsOnTrack: (game.carsOnTrack || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => Math.round(c.s - tr.s)),
    carsCrossing: (game.carsCrossing || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => ({ d: Math.round(c.s - tr.s), onTrack: c.onTrack, v: c.car.vNow, light: c.car.lane?.light ? traffic.lightAspect(c.car.lane.light) : null, waits: waits(c.car) })),
    tramAhead: game.tramAheadGap ? game.tramAheadGap() : null,
    aiTrams: [...traffic.ahead, ...traffic.oncoming].map((t) => ({ id: id(t), waits: waits(t), cycleSeconds: t.cycleT || 0 })),
    junction: { s: Math.round(junction?.cross ?? tr.s), cars: traffic.cars.filter((c) => {
      if (!c.active || !c.path) return false;
      const p = c.path.at(c.s); return Math.hypot(p.x - centre.x, p.y - centre.y) < 100;
    }).map((c) => ({ id: id(c), lane: c.lane?.id, waits: waits(c) })) },
    recoveredCycles: game.trafficCycles || [],
    obstacles: (game.obstacles || []).filter((o) => o.state !== 'gone' && o.s > tr.s && o.s - tr.s < 100).map((o) => ({ d: Math.round(o.s - tr.s), lat: o.lat, type: o.type, state: o.state })) };
}
