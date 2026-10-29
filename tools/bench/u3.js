// Dev check (not part of the game): cars turning across our track in front of the tram (PLAN U3).
// Drives a whole line headless with the autopilot; in the page (after loading):
//   const { run } = await import('/tools/bench/u3.js'); await run(seed)
// Counts (distinct cars): yielded = waited at the track for our tram (within 150 m of it);
// crossedAhead = crossed in front of the moving tram within 100 m; closeCuts = on the track inside the
// tram's stopping distance (v²/2 + 10 m at 1 m/s2) while it moved faster than 2 m/s (of them bold);
// bells = the autopilot's bell; hits = collisions with crossing cars.
const CAR_FRONT = 2.2; // a car's front bumper ahead of its position (its middle), as traffic.js CAR_HALF

export async function run(seed = 1, opts = {}) {
  const { trip = 40, chunk = 400 } = opts;
  window.runSeed = seed >>> 0; // the run's seeded stream (src/random.js)
  const $ = (id) => document.getElementById(id);
  $('selStop').value = '0'; $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = String(trip); $('optWeather').value = 'dry'; $('optObst').value = 'normal';
  $('btnStart').click();
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const game = window.game, traffic = window.traffic, camera = window.camera;
  const pilot = new Autopilot();
  game.autopilot = true; game.paused = false;
  const R = window._u3 = { seed, steps: 0, done: false, bells: 0, hits: [], cuts: [] };
  const yielded = new Set(), crossed = new Set(), cut = new Set();
  const ring = game.ringBell.bind(game);
  game.ringBell = () => { R.bells++; ring(); };
  // our own signal penalties, with the signal's state (what led to it)
  const pen = game.penalty.bind(game);
  game.penalty = (kind, pts, msg) => {
    if (kind === 'signal') {
      const sig = game.signals.filter((x) => Math.abs(x.s - game.tram.s) < 5)[0];
      (R.sig ||= []).push({ s: Math.round(game.tram.s), v: +game.tram.v.toFixed(1), sigS: sig && Math.round(sig.s), t: sig?.t !== undefined ? +sig.t.toFixed(1) : null, ext: sig?.ext !== undefined ? +sig.ext.toFixed(1) : null, cycle: sig && sig.cycle, goDir: sig?.goDir,
        sinceStop: sig && +(game.clock - sig.stopSince).toFixed(1), trail: (R.trail || []).slice(-12).join(' | ') });
    }
    pen(kind, pts, msg);
  };
  const coll = game._collision.bind(game);
  game._collision = (what, pts) => {
    // (the scene: the crossing cars at the tram's front)
    const tr = game.tram;
    const cars = (game.carsCrossing || []).filter((x) => Math.abs(x.s - tr.s) < 6).map((x) => ({ d: +(x.s - tr.s).toFixed(1), onTrack: x.onTrack, v: +(x.car.vNow ?? 0).toFixed(1), front: x.car.xing && +(x.car.xing.dC - 2.2).toFixed(1), bold: !!x.car.bold, light: x.car.lane?.light ? traffic.lightAspect(x.car.lane.light) : null, conn: !!x.car.conn, lightGo: !!x.car.lightGo }));
    R.hits.push({ what, s: Math.round(tr.s), v: +(tr.v * 3.6).toFixed(0), notch: tr.notch, cars, trail: (R.ctrail || []).slice(-10).join(' | ') });
    coll(what, pts);
  };
  const h = 1 / 30;
  await new Promise((resolve) => {
    const tick = () => {
      for (let k = 0; k < chunk; k++) {
        if (game.finished || game.tram.s > game.route.length - 5) { R.done = true; break; }
        // (headless nothing moves the camera, and the cars spawn around it: keep it at the cab)
        const tr = game.tram, q = game.route.at(tr.s);
        camera.position.set(q.x, game.profile.height(tr.s) + 2.6, -q.y);
        // (D2: cars entering a junction from a lane with a light: on red / red-amber without having
        // committed on amber = a red run; on amber = a pass. Judged where the car's front crossed its stop
        // line (lane.light.back before the lane end, up to 40 m), else at the junction's entry)
        const lit = new Map(traffic.cars.filter((c) => c.active && !c.conn && c.lane?.light).map((c) => [c, { lane: c.lane, a: traffic.lightAspect(c.lane.light), go: c.lightGo === c.lane, v: c.vNow, age: c._age = (c._lane === c.lane ? (c._age || 0) + 1 : 0), spawnedOn: c._spawnLane === c.lane, front: c.toEnd - c.lane.light.back - 3.2 }]));
        for (const c of traffic.cars) { if (c.active && c._lane !== c.lane) { if (c._lane === undefined || c.id !== c._id) { c._spawnLane = c.lane; c._spawnS = c.s; } c._lane = c.lane; c._id = c.id; } }
        pilot.step(game, h); game.update(h, pilot.input); traffic.update(h, camera); R.steps++;
        for (const [c, b] of lit) {
          if (!c.conn && c.lane === b.lane && b.front > -0.5 && c.toEnd - b.lane.light.back - 3.2 <= -0.5) c._atLine = { lane: b.lane, a: traffic.lightAspect(b.lane.light), go: c.lightGo === b.lane };
        }
        for (const [c, b0] of lit) {
          if (!c.conn || c.lane !== b0.lane) continue;
          const b = c._atLine?.lane === b0.lane ? { ...b0, a: c._atLine.a, go: c._atLine.go } : b0;
          if ((b.a === 'red' || b.a === 'redamber') && !b.go) { R.carRed = (R.carRed || 0) + 1; (R.carRedWhy ||= []).push({ v: +(b.v ?? 0).toFixed(1), stepsOnLane: b.age, spawnedOnThisLane: b.spawnedOn, aspect: b.a, bold: !!c.bold, yielding: !!c.yielding, lane: b.lane.id, src: b.lane.light.src, back: +b.lane.light.back.toFixed(1), len: Math.round(b.lane.path.length), spawnS: c._spawnS != null ? +c._spawnS.toFixed(1) : null, sig: Math.round(b.lane.light.sig.cross), kind: b.lane.light.kind }); }
          else if (b.a === 'amber') R.carAmber = (R.carAmber || 0) + 1;
          else R.carGreen = (R.carGreen || 0) + 1;
        }
        // (optional watch: every step, the cars within 40 m of route position opts.watch while the tram is
        // within 150 m before it: their lane, plan, crossings seen, decision)
        if (opts.watch && tr.s > opts.watch - 150 && tr.s < opts.watch + 5) {
          const W = game.route.at(opts.watch);
          for (const c of traffic.cars) {
            if (!c.active) continue;
            const p = c.path.at(c.s);
            if (Math.hypot(p.x - W.x, p.y - W.y) > 40) continue;
            (R.watch ||= []).push(`${(game.clock % 1000).toFixed(1)} tram${Math.round(opts.watch - tr.s)} #${c.id} ${c.conn ? 'conn' : 'lane' + c.lane.id} toEnd${(c.toEnd ?? 0).toFixed(1)} next${c.next ? c.next.id : '-'} v${(c.vNow ?? 0).toFixed(1)} xing${c.xing ? `${Math.round(c.xing.sx)}@${(c.xing.dC - 2.2).toFixed(1)}` : '-'}${c.yielding ? ' Y' : ''}`);
          }
        }
        // (a trail of crossing cars ahead of the tram, every 0.5 s: for the collision scene)
        if (R.steps % 15 === 0) {
          const cc = traffic.cars.filter((c) => c.active && c.xing && c.xing.sx > tr.s - 2 && c.xing.sx - tr.s < 40)
            .map((c) => `#${c.id} x${Math.round(c.xing.sx - tr.s)}m front${(c.xing.dC - 2.2).toFixed(1)} v${(c.vNow ?? 0).toFixed(1)}${c.yielding ? ' YIELD' : ''}${c.bold ? ' bold' : ''}${c.conn ? ' conn' : ''}`);
          (R.ctrail ||= []).push(`${Math.round(game.clock)} tram ${(tr.v * 3.6).toFixed(0)}km/h n${tr.notch} [${cc.join(', ')}]`);
          if (R.ctrail.length > 30) R.ctrail.shift();
        }
        // (a trail of our tram near signals: s, v, the next signal's state, t, ext; every 0.5 s)
        if (R.steps % 15 === 0) {
          const nx = game.signals.find((x) => x.s > tr.s - 1);
          if (nx && nx.s - tr.s < 120) { (R.trail ||= []).push(`${Math.round(game.clock)} s${Math.round(tr.s)} v${tr.v.toFixed(1)} ${Math.round(nx.s)}:${nx.state} t${nx.t?.toFixed(1) ?? (nx.gauntlet ? "gauntlet" : "-")} x${nx.ext?.toFixed(1) ?? "-"}${nx.backCommitted ? ' B' : ''}${nx.aheadCommitted ? ' A' : ''}`); if (R.trail.length > 40) R.trail.shift(); }
        }
        for (const c of traffic.cars) if (c.active && c.yielding && c.xing && Math.abs(c.xing.sx - tr.s) < 150) {
          yielded.add(c.id);
          // where a yielding car stands: its front bumper's distance from the track centre line
          if ((c.vNow ?? 1) < 0.05 && !(R.bumper ||= new Map()).has(c.id)) {
            const seq = traffic._seq(c); let fp = null;
            for (const [path, off] of seq) { const s = CAR_FRONT - off; if (s <= path.length) { fp = path.at(s); break; } }
            const n = fp && game.route.nearest(fp.x, fp.y);
            if (n) R.bumper.set(c.id, n.d);
          }
        }
        for (const xc of game.carsCrossing || []) {
          const d = xc.s - tr.s;
          if (d > 0 && d < 100 && tr.v > 0.5) crossed.add(xc.car.id);
          if (xc.onTrack && d > 0 && tr.v > 2 && d < (tr.v * tr.v) / 2 + 10 && !cut.has(xc.car.id)) {
            cut.add(xc.car.id);
            R.cuts.push({ s: Math.round(tr.s), d: Math.round(d), v: +(tr.v * 3.6).toFixed(0), bold: !!xc.car.bold });
          }
        }
      }
      R.tramS = Math.round(game.tram.s);
      // (stuck: the tram has not moved for 10 game minutes, a deadlock; give up and report)
      if (R.lastS === undefined || Math.abs(game.tram.s - R.lastS) > 1) { R.lastS = game.tram.s; R.lastMove = game.clock; }
      if (game.clock - R.lastMove > 600) {
        R.done = true; R.stuck = Math.round(game.tram.s);
        // what holds the tram: the autopilot's plan and what lies ahead of it
        const tr = game.tram, plan = pilot.step(game, 0);
        R.stuckScene = { s: Math.round(tr.s), v: tr.v, plan: { vt: plan.vt, stopAt: plan.stopAt && Math.round(plan.stopAt - tr.s) }, doors: game.doorState, action: !!game.action, hold: game.holdTimer,
          nextStop: game.stops[game.nextStop] && { name: game.stops[game.nextStop].name, d: Math.round(game.stops[game.nextStop].target - tr.s), served: game.stops[game.nextStop].served, waiting: game.stops[game.nextStop].waiting, runners: game.runners.length },
          signal: (() => { const x = game.signals.find((q) => q.s > tr.s); return x && { d: Math.round(x.s - tr.s), state: x.state, demand: !!x.demand, t: x.t }; })(),
          carsOnTrack: (game.carsOnTrack || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => Math.round(c.s - tr.s)),
          carsCrossing: (game.carsCrossing || []).filter((c) => c.s > tr.s && c.s - tr.s < 120).map((c) => ({ d: Math.round(c.s - tr.s), onTrack: c.onTrack, v: c.car.vNow, light: c.car.lane?.light ? traffic.lightAspect(c.car.lane.light) : null, seen: c.car.seen && { gap: c.car.seen.gap, v: c.car.seen.v } })),
          tramAhead: game.tramAheadGap(), obstacles: game.obstacles.filter((o) => o.state !== 'gone' && o.s > tr.s && o.s - tr.s < 100).map((o) => ({ d: Math.round(o.s - tr.s), lat: o.lat, type: o.type, state: o.state })) };
      }
      if (!R.done) setTimeout(tick, 0);
      else resolve();
    };
    tick();
  });
  const bump = [...(R.bumper || new Map()).values()].sort((a, b) => a - b);
  const q = (p) => (bump.length ? +bump[Math.min(bump.length - 1, Math.floor(p * bump.length))].toFixed(1) : null);
  return { seed, watch: R.watch || [], stuck: R.stuck ?? null, carsIntoJunctions: { green: R.carGreen || 0, amber: R.carAmber || 0, red: R.carRed || 0 }, carRedWhy: R.carRedWhy || [], stuckScene: R.stuckScene || null, bumperToTrackCentre: { n: bump.length, min: q(0), median: q(0.5), max: q(0.999) }, yielded: yielded.size, crossedAhead: crossed.size, closeCuts: R.cuts.length, closeCutsBold: R.cuts.filter((c) => c.bold).length,
    bells: R.bells, hits: R.hits.length, collisions: R.hits, cuts: R.cuts, signalPenalty: game.penalties.signal || 0, signalEvents: R.sig || [], collisionPenalty: Math.round(game.penalties.collision || 0) };
}
