// SPDX-License-Identifier: AGPL-3.0-or-later
// Dev check (not part of the game): cars turning across our track in front of the tram (PLAN U3).
// Drives a whole line headless with the autopilot; in the page (after loading):
//   const { run } = await import('/tools/bench/u3.js'); await run(seed)
// Counts (distinct cars): yielded = waited at the track for our tram (within 150 m of it);
// crossedAhead = crossed in front of the moving tram within 100 m; closeCuts = on the track inside the
// tram's stopping distance (v²/2 + 10 m at 1 m/s2) while it moved faster than 2 m/s (of them bold);
// bells = the autopilot's bell; hits = collisions with crossing cars.
import { stuckWatch, stuckScene } from './stuck.js';

// #602: a car's body (its type's half length and half width over the tyres, src/carTypes.js) against both tracks. FOUL: a
// tram's half width (1.25 m) with its swing in a tight curve's overhang (about 0.45 m) and 0.3 m; a body corner nearer a
// track's centre fouls the tram passing there
const FOUL = 2.0;
// the car's corners' least distance to a route's centre line, and the route position there: { d, s } or null
function bodyTo(route, p, c) {
  let best = null;
  const nx = -p.hy, ny = p.hx, hl = c.half, hw = c.halfW;
  for (const [a, b] of [[hl, hw], [hl, -hw], [-hl, hw], [-hl, -hw]]) {
    const n = route.nearest(p.x + p.hx * a + nx * b, p.y + p.hy * a + ny * b);
    if (n && (!best || n.d < best.d)) best = { d: n.d, s: n.s };
  }
  return best;
}

export async function run(seed = 1, opts = {}) {
  // (opts.stopAt: end where our tram reaches this route s, a replay of the moment, ?seed=N&at=S; opts.progress: a line per chunk)
  const { trip = 40, chunk = 400, weather = 'dry', stopAt = Infinity, progress = () => {} } = opts;
  window.headless = true;
  // the run (src/run.js, #226): its seeded stream, the first stop, the autopilot driving; nothing from the real weather:
  // the menu's default temperature is today's Prague forecast, which sets the autopilot's heaters and flap (#205)
  const run = await window.startRun({ seed: seed >>> 0, startStop: 0, trip, weather, obstacles: 'normal', temp: 'autumn', autopilot: true });
  const { game, traffic, pilot } = run, camera = window.camera;
  game.pilot = pilot; // (for the watchers: what it stops for, tools/bench/stops.js)
  const stuck = stuckWatch(game);
  // (other checks' watchers along on the same drive, opts.also: [(game, traffic, { view }) => watcher], #205; view: the
  // traffic as drawn, src/trafficView.js)
  const also = (opts.also || []).map((make) => make(game, traffic, { view: run.trafficView }));
  game.paused = false;
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
    const cars = (game.carsCrossing || []).filter((x) => Math.abs(x.s - tr.s) < 6).map((x) => ({ d: +(x.s - tr.s).toFixed(1), onTrack: x.onTrack, v: +(x.car.vNow ?? 0).toFixed(1), front: x.car.xing && +(x.car.xing.dC - x.car.half).toFixed(1), bold: !!x.car.bold, light: x.car.lane?.light ? traffic.lightAspect(x.car.lane.light) : null, conn: !!x.car.conn, lightGo: !!x.car.lightGo }));
    R.hits.push({ what, s: Math.round(tr.s), v: +(tr.v * 3.6).toFixed(0), notch: tr.notch, cars, trail: (R.ctrail || []).slice(-10).join(' | ') });
    coll(what, pts);
  };
  const h = 1 / 30;
  await new Promise((resolve) => {
    const tick = () => {
      for (let k = 0; k < chunk; k++) {
        if (game.finished || game.tram.s > game.route.length - 5 || game.tram.s >= stopAt) { R.done = true; break; }
        const alsoBefore = also.map((w) => w.before());
        // (headless nothing moves the camera: keep it at the cab for the once-a-second draw; the cars spawn round the
        // tram's front whatever it shows, traffic.focus, #722)
        const tr = game.tram, q = game.route.at(tr.s);
        camera.position.set(q.x, game.profile.height(tr.s) + 2.6, -q.y);
        // (D2: cars entering a junction from a lane with a light: on red / red-amber without having
        // committed on amber = a red run; on amber = a pass. Judged where the car's front crossed its stop
        // line (lane.light.back before the lane end, up to 40 m), else at the junction's entry)
        const lit = new Map(traffic.cars.filter((c) => c.active && !c.conn && c.lane?.light).map((c) => [c, { lane: c.lane, a: traffic.lightAspect(c.lane.light), go: c.lightGo === c.lane, v: c.vNow, age: c._age = (c._lane === c.lane ? (c._age || 0) + 1 : 0), spawnedOn: c._spawnLane === c.lane, front: c.toEnd - c.lane.light.back - 3.2 }]));
        for (const c of traffic.cars) { if (c.active && c._lane !== c.lane) { if (c._lane === undefined || c.id !== c._id) { c._spawnLane = c.lane; c._spawnS = c.s; } c._lane = c.lane; c._id = c.id; } }
        run.step(h, null, camera); R.steps++;
        also.forEach((w, i) => w.after(alsoBefore[i]));
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
            (R.watch ||= []).push(`${(game.clock % 1000).toFixed(1)} tram${Math.round(opts.watch - tr.s)} #${c.id} ${c.conn ? 'conn' : 'lane' + c.lane.id} toEnd${(c.toEnd ?? 0).toFixed(1)} next${c.next ? c.next.id : '-'} v${(c.vNow ?? 0).toFixed(1)} xing${c.xing ? `${Math.round(c.xing.sx)}@${(c.xing.dC - c.half).toFixed(1)}` : '-'}${c.yielding ? ' Y' : ''} why${c.why ?? '-'}${c.jBlock != null ? ' jb' + c.jBlock : ''} lead${c.lead?.id ?? '-'}`);
          }
        }
        // (a trail of crossing cars ahead of the tram, every 0.5 s: for the collision scene)
        if (R.steps % 15 === 0) {
          const cc = traffic.cars.filter((c) => c.active && c.xing && c.xing.sx > tr.s - 2 && c.xing.sx - tr.s < 40)
            .map((c) => `#${c.id} x${Math.round(c.xing.sx - tr.s)}m front${(c.xing.dC - c.half).toFixed(1)} v${(c.vNow ?? 0).toFixed(1)}${c.yielding ? ' YIELD' : ''}${c.bold ? ' bold' : ''}${c.conn ? ' conn' : ''}`);
          (R.ctrail ||= []).push(`${Math.round(game.clock)} tram ${(tr.v * 3.6).toFixed(0)}km/h n${tr.notch} [${cc.join(', ')}]`);
          if (R.ctrail.length > 30) R.ctrail.shift();
        }
        // (a trail of our tram near signals: s, v, the next signal's state, t, ext; every 0.5 s)
        if (R.steps % 15 === 0) {
          const nx = game.signals.find((x) => x.s > tr.s - 1);
          if (nx && nx.s - tr.s < 120) { (R.trail ||= []).push(`${Math.round(game.clock)} s${Math.round(tr.s)} v${tr.v.toFixed(1)} ${Math.round(nx.s)}:${nx.state} t${nx.t?.toFixed(1) ?? (nx.gauntlet ? "gauntlet" : "-")} x${nx.ext?.toFixed(1) ?? "-"}${nx.backCommitted ? ' B' : ''} P${game.pilot?.goThrough === nx ? 'go' : game.pilot?.stopFor === nx ? 'stop' : '-'}:${game.pilot?.stopWhy ?? '-'}@${game.pilot?.stopAtS == null ? '-' : Math.round(game.pilot.stopAtS)} n${tr.notch} a${tr.a.toFixed(2)}${nx.aheadCommitted ? ' A' : ''}`); if (R.trail.length > 40) R.trail.shift(); }
        }
        // #602: every 0.5 s, the standing cars across a track (not along it, as a car in a lane on the rails) whose body
        // fouls it with a tram there or coming (its front within 40 m before, or its body over the place); and where each
        // yielding car stands against both tracks (its body's nearest corner)
        if (R.steps % 15 === 0) {
          const tracks = [[game.route, [tr, ...traffic.ahead], 'ours'], [traffic.back, traffic.oncoming, 'back']];
          for (const c of traffic.cars) {
            if (!c.active || (c.vNow ?? 1) > 0.3 || (c.alpha ?? 1) < 0.5 || !c.path) continue;
            const p = c.path.at(c.s);
            for (const [route, trams, k] of tracks) {
              if (!route) continue;
              const b = bodyTo(route, p, c);
              if (!b || b.d > 8) continue;
              const h = route.at(b.s);
              if (Math.abs(p.hx * h.hx + p.hy * h.hy) > 0.7) continue;
              if (c.yielding && !(R.stance ||= new Map()).has(`${k}${c.id}`)) R.stance.set(`${k}${c.id}`, +b.d.toFixed(2));
              const tram = trams.find((t) => t && b.s - t.s < 40 && b.s > t.s - (t.length ?? 0) - 1);
              if (b.d < FOUL && tram && !(R.foul ||= new Map()).has(`${k}${c.id}`)) {
                R.foul.set(`${k}${c.id}`, { track: k, s: Math.round(b.s), d: +b.d.toFixed(2), tram: tram === tr ? 'ours' : 'ai', ahead: Math.round(b.s - tram.s), yielding: !!c.yielding, why: c.why ?? null, conn: !!c.conn });
              }
            }
          }
        }
        for (const c of traffic.cars) if (c.active && c.yielding && c.xing && Math.abs(c.xing.sx - tr.s) < 150) {
          yielded.add(c.id);
          // where a yielding car stands: its front bumper's (half its length ahead of its middle) distance from the track centre line
          if ((c.vNow ?? 1) < 0.05 && !(R.bumper ||= new Map()).has(c.id)) {
            const seq = traffic._seq(c); let fp = null;
            for (const [path, off] of seq) { const s = c.half - off; if (s <= path.length) { fp = path.at(s); break; } }
            const n = fp && game.route.nearest(fp.x, fp.y);
            if (n) R.bumper.set(c.id, n.d);
          }
        }
        for (const xc of game.carsCrossing || []) {
          const d = xc.s - tr.s;
          if (d > 0 && d < 100 && tr.v > 0.5) crossed.add(xc.car.id);
          if (xc.onTrack && d > 0 && tr.v > 2 && d < (tr.v * tr.v) / 2 + 10 && !cut.has(xc.car.id)) {
            cut.add(xc.car.id);
            R.cuts.push({ s: Math.round(tr.s), d: Math.round(d), v: +(tr.v * 3.6).toFixed(0), bold: !!xc.car.bold,
              // (#560: seconds since a circle of cars let it go, if within a minute)
              letGo: game.clock - (xc.car.letGoAt ?? -Infinity) < 60 ? Math.round(game.clock - xc.car.letGoAt) : null });
          }
        }
      }
      R.tramS = Math.round(game.tram.s);
      progress(`drive: ${Math.round(game.clock)} s, s ${R.tramS}, stop ${game.nextStop}`);
      if ((R.stuck = stuck()) !== null) { R.done = true; R.stuckScene = stuckScene(game, traffic, pilot); }
      if (!R.done) setTimeout(tick, 0);
      else resolve();
    };
    tick();
  });
  const bump = [...(R.bumper || new Map()).values()].sort((a, b) => a - b);
  const q = (p) => (bump.length ? +bump[Math.min(bump.length - 1, Math.floor(p * bump.length))].toFixed(1) : null);
  return { seed, watch: R.watch || [], stuck: R.stuck ?? null, carsIntoJunctions: { green: R.carGreen || 0, amber: R.carAmber || 0, red: R.carRed || 0 }, carRedWhy: R.carRedWhy || [], stuckScene: R.stuckScene || null, bumperToTrackCentre: { n: bump.length, min: q(0), median: q(0.5), max: q(0.999) },
    // #602: yielding cars' nearest body corner to each track (stood within FOUL of it: on it); the fouls by track and tram
    stance: (() => { const out = {}; for (const k of ['ours', 'back']) { const v = [...(R.stance || new Map())].filter(([key]) => key.startsWith(k)).map(([, d]) => d).sort((a, b) => a - b); out[k] = { n: v.length, min: v[0] ?? null, median: v[Math.floor(v.length / 2)] ?? null, within: v.filter((d) => d < FOUL).length }; } return out; })(),
    fouls: { ours: [...(R.foul || new Map()).values()].filter((f) => f.track === 'ours').length, back: [...(R.foul || new Map()).values()].filter((f) => f.track === 'back').length,
      places: [...(R.foul || new Map()).values()].slice(0, 30) }, yielded: yielded.size, crossedAhead: crossed.size, closeCuts: R.cuts.length, closeCutsBold: R.cuts.filter((c) => c.bold).length,
    bells: R.bells, hits: R.hits.length, collisions: R.hits, cuts: R.cuts, signalPenalty: game.penalties.signal || 0, signalEvents: R.sig || [], collisionPenalty: Math.round(game.penalties.collision || 0),
    also: also.map((w) => w.result(seed, R.stuck ?? null, R.stuckScene || null)) };
}
