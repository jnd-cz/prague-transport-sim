// Dev bench (not part of the game): the frame time and the draw calls with a tram model (#248, #250).
// In a page with the menu up (tools/frametime.py drives it in a headed browser; headless draws in software):
//   const { run } = await import('/tools/bench/frametime.js'); await run({ model: 'detailed' })
// The scene: the first stop of the line's first trip, our set standing with its doors open, three more
// sets of the same model on the track ahead (fronts AI m ahead of ours: the nearest at its full level, the
// two others at the lighter one, as traffic sets them), the camera fixed 14 m off the platform side. The
// game runs (a paused one draws 4 frames a second, #149) with the run's seeded traffic.
// Returns the frame interval (median, p95; vsync off in the runner), the CPU time of renderer.render,
// the draw calls and triangles of a frame, and each set's level.
const AI = [45, 110, 180];

const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
const pct = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const until = async (ok, ms = 120000) => {
  for (const t0 = performance.now(); !ok(); ) {
    if (performance.now() - t0 > ms) throw new Error('frametime: timed out waiting for the game');
    await new Promise((r) => setTimeout(r, 100));
  }
};
const frame = () => new Promise((r) => requestAnimationFrame(r));

export async function run({ model = 'detailed', frames = 600, warm = 120, ai = AI } = {}) {
  const $ = (id) => document.getElementById(id);
  window.runSeed = 1; // (the run's seeded stream: the same traffic for every model)
  $('selStop').value = '0'; $('selStop').dispatchEvent(new Event('change'));
  $('selTrip').value = '0'; $('optWeather').value = 'dry'; $('optTemp').value = 'autumn'; $('optObst').value = 'off';
  $('optAuto').checked = false;
  const sel = $('optModel');
  sel.value = model; sel.dispatchEvent(new Event('change'));
  const kind = model === 'simple' ? 'simple' : model === 'classic' ? 'classic' : 'hybrid';
  $('btnStart').click();
  await until(() => window.game && window.tramModel?.userData.kind === kind && window.camera);
  const { makeT3, placeConsist } = await import('/src/models.js');
  const { setHybridLevel, FULL_OUT } = await import('/src/t3h.js');
  const g = window.game, route = g.route, s0 = g.tram.s;
  const at = (q) => { const p = route.at(q); return [p.x, p.y, g.profile.height(q), route.rollAt(q)]; };
  // the camera: 14 m off the platform (right) side of our set's middle, 3 m up, looking 40 m ahead
  window.freeCam = true;
  const c = route.offset(s0 - 15, -14), l = route.at(s0 + 40);
  window.camera.position.set(c.x, g.profile.height(s0 - 15) + 3, -c.y);
  window.camera.lookAt(l.x, g.profile.height(s0 + 40) + 1.5, -l.y);
  window.camera.updateMatrixWorld();
  const sets = ai.map((d) => {
    const m = makeT3({ line: g.line, cars: 2, detailed: model === 'simple' ? false : kind, run: '899' });
    placeConsist(m, s0 + d, at);
    window.scene.add(m);
    const p = m.userData.cars[0].position, far = Math.hypot(p.x - window.camera.position.x, p.z - window.camera.position.z);
    setHybridLevel(m, far < FULL_OUT ? 'full' : 'light');
    return { m, far: Math.round(far) };
  });
  // the CPU time of each render (the GPU's work shows in the frame interval)
  const r = window.renderer, orig = r.render;
  const cpu = [];
  let info = null;
  r.render = function (scene, cam) {
    const t = performance.now();
    orig.call(this, scene, cam);
    cpu.push(performance.now() - t);
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
    for (const { m } of sets) { window.scene.remove(m); }
  }
  const c2 = cpu.slice(warm);
  const ms = (x) => +x.toFixed(2);
  return {
    model, kind: window.tramModel.userData.kind, frames: gaps.length,
    frameMedian: ms(median(gaps)), frameP95: ms(pct(gaps, 0.95)), fps: +(1000 / median(gaps)).toFixed(1),
    renderMedian: ms(median(c2)), renderP95: ms(pct(c2, 0.95)), ...info,
    sets: sets.map(({ m, far }) => ({ far, level: m.userData.level ?? m.userData.kind })),
    viewport: [innerWidth, innerHeight, devicePixelRatio],
  };
}
