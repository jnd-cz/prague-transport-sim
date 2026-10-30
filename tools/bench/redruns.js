// Dev check (not part of the game): drive a whole line headless with the autopilot and count the
// oncoming AI trams that pass their stop line on red. In the page (after loading):
//   const { run } = await import('/tools/bench/redruns.js'); await run(seed);   then read window._res
// A red run is "avoidable" when, during that same red period, the tram was once far enough away to
// stop with full service braking (v²/2.6 + v + 0.5 m); else it was in the dilemma zone when the
// light changed.
// Also counted: passes while the GO blinks (warn: allowed), our own signal penalties, controller holds.
// It stops when our tram is stuck (tools/bench/stuck.js, as u3).
import { stuckWatch, stuckScene } from './stuck.js';

export async function run(seed = 1, { trip = 40, chunk = 400 } = {}) {
  window.runSeed = seed >>> 0; // the run's seeded stream (src/random.js)
  const $ = (id) => document.getElementById(id);
  $('selStop').value = '0'; $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = String(trip); $('optWeather').value = 'dry'; $('optObst').value = 'normal';
  $('btnStart').click();
  window.headless = true;
  const { Autopilot } = await import('/src/autopilot.js');
  const game = window.game, traffic = window.traffic, camera = window.camera;
  const pilot = new Autopilot();
  const stuck = stuckWatch(game);
  game.autopilot = true; game.paused = false;
  const R = window._res = { seed, steps: 0, red: [], warnPasses: 0, holds: 0, done: false, t0: performance.now() };
  const h = 1 / 30;
  const wasHeld = new Map();
  await new Promise((resolve) => {
    const tick = () => {
      for (let k = 0; k < chunk; k++) {
        if (game.finished || game.tram.s > game.route.length - 5) { R.done = true; break; }
        const prev = new Map(traffic.oncoming.map((t) => [t, t.s]));
        const prevAhead = new Map(traffic.ahead.map((t) => [t, t.s]));
        // (headless nothing moves the camera, and road cars spawn around it: keep it at the cab)
        const q = game.route.at(game.tram.s);
        camera.position.set(q.x, game.profile.height(game.tram.s) + 2.6, -q.y);
        pilot.step(game, h); game.update(h, pilot.input); traffic.update(h, camera); R.steps++;
        // the AI trams ahead of us, at our signals (their stop point is 3 m before the head)
        for (const t of traffic.ahead) {
          const p = prevAhead.get(t);
          t._hist ||= [];
          if (R.steps % 15 === 0) {
            const nx = game.signals.find((x) => x.s > t.s + 0.5);
            t._hist.push([Math.round(game.clock), +t.s.toFixed(1), +t.v.toFixed(2), +(t.dwell || 0).toFixed(1), nx ? `${Math.round(nx.s)}:${nx.state}` : '-', [...(t.redStops || [])].map((x) => Math.round(x.s)).join('+')]);
            if (t._hist.length > 40) t._hist.shift();
          }
          for (const sig of game.signals) {
            if (p === undefined || !(p < sig.s && t.s >= sig.s)) continue;
            if (sig.state === 'stop') (R.aheadRed ||= []).push({ sigS: Math.round(sig.s), v: +t.v.toFixed(1), sinceRed: +(game.clock - sig.stopSince).toFixed(1), stops: game.stops.filter((st) => Math.abs(st.target - sig.s) < 80).map((st) => Math.round(st.target)), hist: t._hist.slice(-24).map((q) => q.join(' ')).join(' | ') });
            else if (sig.state === 'warn') R.aheadWarnPasses = (R.aheadWarnPasses || 0) + 1;
          }
        }
        for (const sig of game.signals) { if (sig.backCommitted && !wasHeld.get(sig)) R.holds++; wasHeld.set(sig, sig.backCommitted); }
        for (const t of traffic.oncoming) {
          const p = prev.get(t);
          t._could ||= new Map(); // sig -> the red period (backStopSince) in which it could have stopped
          // (debug trail: every 0.5 s the last 20 s of s, v, dwell, the signals it stops for)
          t._hist ||= [];
          if (R.steps % 15 === 0) { t._hist.push([Math.round(game.clock), +t.s.toFixed(1), +t.v.toFixed(2), +(t.dwell || 0).toFixed(1), [...(t.redStops || [])].map((s) => Math.round(s.s)).join('+')]); if (t._hist.length > 40) t._hist.shift(); }
          for (const sig of game.signals) {
            if (sig.backCross === undefined) continue;
            const line = sig.backCross - 6, d = line - t.s;
            if (sig.backState === 'stop' && d > 0 && d > (t.v * t.v) / 2.6 + t.v + 0.5) t._could.set(sig, sig.backStopSince); // (full service braking: traffic.js stopDistance)
            if (p !== undefined && p < line && t.s >= line) {
              if (sig.backState === 'stop') R.red.push({ sigS: Math.round(sig.s), line: +line.toFixed(1), v: +t.v.toFixed(1), sinceRed: +(game.clock - sig.backStopSince).toFixed(1), avoidable: t._could.get(sig) === sig.backStopSince, tram: t.mesh.userData.line, inSet: !!t.redStops?.has(sig), platforms: traffic.backStops.filter((b) => Math.abs(b - line) < 30).map((b) => +b.toFixed(1)), hist: t._hist.slice(-16).map((q) => q.join(' ')).join(' | ') });
              else if (sig.backState === 'warn') R.warnPasses++;
            }
          }
        }
      }
      R.tramS = Math.round(game.tram.s);
      if ((R.stuck = stuck()) !== null) { R.done = true; R.stuckScene = stuckScene(game, traffic, pilot); }
      if (!R.done) setTimeout(tick, 0);
      else { R.ourSignalPenalty = game.penalties.signal || 0; R.minutes = Math.round(game.clock / 60); R.ms = Math.round(performance.now() - R.t0); resolve(); }
    };
    tick();
  });
  return { seed, stuck: R.stuck ?? null, stuckScene: R.stuckScene || null, redRuns: R.red.length, avoidable: R.red.filter((r) => r.avoidable).length, warnPasses: R.warnPasses, holds: R.holds,
    aheadRedRuns: (R.aheadRed || []).length, aheadWarnPasses: R.aheadWarnPasses || 0, ourSignalPenalty: R.ourSignalPenalty, red: R.red, aheadRed: R.aheadRed || [] };
}
