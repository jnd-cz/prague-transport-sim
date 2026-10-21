// Dev tool: drives a game headlessly (fixed time step) to exercise the gameplay rules.
// In the browser console:  const { autopilot } = await import('/tools/autopilot.js'); autopilot(0, 10)
import { Autopilot } from '../src/autopilot.js';

export function autopilot(startStop, untilStop, { obstacles = 'off', weather = 'dry', maxT = 3600, dt = 1 / 30, trace = null } = {}) {
  const $ = (id) => document.getElementById(id);
  $('menu').classList.remove('hidden');
  $('selStop').value = String(startStop);
  $('selStop').dispatchEvent(new Event('change'));
  $('optObst').value = obstacles;
  $('optWeather').value = weather;
  $('optAuto').checked = false;
  $('btnStart').click();
  const g = window.game, tr = g.tram;
  g.audio.setMuted(true);
  const ap = new Autopilot();
  let T = 0;
  const out = [], seen = new Set();
  while (T < maxT && g.nextStop < untilStop && !g.finished) {
    const { vt, stopAt, notch } = ap.step(g, dt);
    g.update(dt, ap.input);
    if (window.traffic) {
      const p = g.route.at(tr.s);
      window.traffic.update(dt, { position: { x: p.x, z: -p.y } });
    }
    T += dt;
    if (trace && Math.floor(T) !== Math.floor(T - dt)) trace.push([Math.floor(T), g.nextStop, Math.round(tr.s), +tr.kmh.toFixed(1), +(vt * 3.6).toFixed(1), notch, stopAt && Math.round(stopAt), g.doorState]);
    for (const m of g.messages) {
      if (!seen.has(m.text)) { seen.add(m.text); out.push(`${T.toFixed(0)}s s=${tr.s.toFixed(0)} ${m.kind}: ${m.text}`); }
    }
  }
  return { T: Math.round(T), next: g.nextStop, finished: g.finished, score: Math.round(g.score), pen: g.penalties, out };
}
