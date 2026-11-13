// SPDX-License-Identifier: AGPL-3.0-or-later
// Dev bench (not part of the game): the frame time and the draw calls with a tram model (#248, #250).
// In a page with the menu up (tools/frametime.py drives it in a headed browser; headless draws in software):
//   const { run } = await import('/tools/bench/frametime.js'); await run({ model: 't3h' })
// The scene: the first stop of the line's first trip, our set standing with its doors open, three more
// sets of the same model on the track ahead (fronts AI m ahead of ours: the nearest at its full level, the
// two others at the lighter one, as traffic sets them), the camera fixed 14 m off the platform side. The
// game runs (a paused one draws 4 frames a second, #149) with the run's seeded traffic.
// Returns the frame interval (median, p95; vsync off in the runner), the CPU time of renderer.render,
// the draw calls and triangles of a frame, and each set's level. `fov`: the camera's vertical field in degrees
// (the cab's 62 unless given; the zoom key's 22.75, #382).
import { startShift } from './shift.js';

const AI = [45, 110, 180];

const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const until = async (ok, ms = 120000) => {
  for (const t0 = performance.now(); !ok(); ) {
    if (performance.now() - t0 > ms) throw new Error('frametime: timed out waiting for the game');
    await new Promise((r) => setTimeout(r, 100));
  }
};
const count = (o) => { let n = 0; o.traverse(() => n++); return n; };
const frame = () => new Promise((r) => requestAnimationFrame(r));

// livery: a livery id (#529) our set and the sets ahead wear; none, the vehicle's own
export async function run({ model = 't3h', frames = 600, warm = 120, ai = AI, fov = null, livery = null } = {}) {
  const $ = (id) => document.getElementById(id);
  window.runSeed = 1; // (the run's seeded stream: the same traffic for every model)
  $('selStop').value = '0'; $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optWeather').value = 'dry'; $('optTemp').value = 'autumn'; $('optObst').value = 'off';
  $('optAuto').checked = false;
  const sel = $('optModel');
  sel.value = model; sel.dispatchEvent(new Event('change'));
  if (livery && $('optLivery')) { $('optLivery').value = livery; $('optLivery').dispatchEvent(new Event('change')); }
  await startShift({ timeout: 120 });
  await until(() => window.tramModel?.userData.vehicle === model && window.camera);
  const { makeT3, placeConsist } = await import('/src/models.js');
  const { setRiggedLevel, FULL_OUT } = await import('/src/rigged.js');
  const g = window.game, route = g.route, s0 = g.tram.s;
  const at = (q) => { const p = route.at(q); return [p.x, p.y, g.profile.height(q), route.rollAt(q)]; };
  // the camera: 14 m off the platform (right) side of our set's middle, 3 m up, looking 40 m ahead
  window.freeCam = true;
  const c = route.offset(s0 - 15, -14), l = route.at(s0 + 40);
  window.camera.position.set(c.x, g.profile.height(s0 - 15) + 3, -c.y);
  window.camera.lookAt(l.x, g.profile.height(s0 + 40) + 1.5, -l.y);
  if (fov) { window.camera.fov = fov; window.camera.updateProjectionMatrix(); }
  window.camera.updateMatrixWorld();
  const sets = ai.map((d) => {
    const m = makeT3({ line: g.line, cars: 2, vehicle: model, run: '899', variant: livery ? 'T3SUCS' : null, livery });
    placeConsist(m, s0 + d, at);
    window.scene.add(m);
    const p = m.userData.cars[0].position, far = Math.hypot(p.x - window.camera.position.x, p.z - window.camera.position.z);
    setRiggedLevel(m, far < FULL_OUT ? 'full' : 'light');
    return { m, far: Math.round(far) };
  });
  // the CPU time of each render (the GPU's work shows in the frame interval)
  const r = window.renderer, orig = r.render;
  // (split: the scene's matrix update, which render does first, and the rest of render)
  const cpu = [], umw = [];
  let info = null;
  r.render = function (scene, cam) {
    const t = performance.now();
    scene.updateMatrixWorld();
    const t1 = performance.now(), auto = scene.matrixWorldAutoUpdate;
    scene.matrixWorldAutoUpdate = false;
    orig.call(this, scene, cam);
    scene.matrixWorldAutoUpdate = auto;
    cpu.push(performance.now() - t); umw.push(t1 - t);
    if (!info && cpu.length > warm) info = { calls: r.info.render.calls, triangles: r.info.render.triangles };
  };
  const gaps = [];
  try {
    let t = performance.now();
    for (let i = 0; i < warm + frames; i++) {
      await frame();
      const now = performance.now();
      if (i >= warm) gaps.push(now - t);
      t = now;
    }
  } finally {
    r.render = orig;
  }
  const c2 = cpu.slice(warm), setNodes = sets.length ? count(sets[0].m) : 0, nodes = count(window.scene);
  for (const { m } of sets) window.scene.remove(m);
  const ms = (x) => +x.toFixed(2);
  return {
    model, kind: window.tramModel.userData.kind, fov: +window.camera.fov.toFixed(2), frames: gaps.length,
    frameMedian: ms(median(gaps)), frameP95: ms(pct(gaps, 0.95)), fps: +(1000 / median(gaps)).toFixed(1),
    renderMedian: ms(median(c2)), renderP95: ms(pct(c2, 0.95)), matrixMedian: ms(median(umw.slice(warm))), ...info,
    nodes, tramNodes: count(window.tramModel), setNodes,
    sets: sets.map(({ m, far }) => ({ far, level: m.userData.level ?? m.userData.kind })),
    viewport: [innerWidth, innerHeight, devicePixelRatio],
  };
}
