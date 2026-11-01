// Mirror rendering cost, at a fixed line position, on a foreground page (#79).
//   const { run } = await import('/tools/bench/mirror.js'); await run({ s: 5064, seconds: 10 });
// Keeps the real renderer and native frame loop: no background/throttled-page FPS claims. Each pair
// alternates mirror off/on and returns frame times, mirror texture updates and submitted geometry.
export async function run({ s = 5064, seconds = 10, rounds = 3 } = {}) {
  const g = window.game, renderer = window.renderer;
  if (!g || !renderer) throw new Error('start a shift first');
  if (!(seconds > 0) || !Number.isInteger(rounds) || rounds < 1) throw new Error('positive seconds and integer rounds required');
  const saved = { paused: g.paused, s: g.tram.s, v: g.tram.v, a: g.tram.a, update: g.update, traffic: window.traffic.update,
                  headless:window.headless, chase:document.body.classList.contains('chase'),
                  mirror:!document.body.classList.contains('nomirror') };
  const original = renderer.render;
  const gl = renderer.getContext(), ext = gl.getExtension('WEBGL_debug_renderer_info');
  const result = { line: g.line, s, seconds, rounds, viewport: [innerWidth, innerHeight, devicePixelRatio],
                   gpu: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER), samples: [] };
  let active = null;
  renderer.render = function (scene, camera) {
    const texture = this.getRenderTarget() !== null, start = performance.now();
    original.call(this, scene, camera);
    if (!active) return;
    const elapsed = performance.now() - start;
    active.render_ms += elapsed;
    if (texture) {
      active.mirror_updates++;
      active.mirror_ms += elapsed;
      active.mirror_calls += this.info.render.calls;
      active.mirror_triangles += this.info.render.triangles;
    }
  };
  const key = () => dispatchEvent(new KeyboardEvent('keydown', { key: 'z' }));
  const wait = ms => new Promise(ok => setTimeout(ok, ms));
  const measure = async (mirror) => {
    active = { mirror, frames: 0, mirror_updates: 0, render_ms: 0, mirror_ms: 0,
               mirror_calls: 0, mirror_triangles: 0, focused: true, visible: true, dt_ms: [] };
    const sample = active, start = performance.now();
    let last = start, stop = false;
    const frame = now => {
      if (stop) return;
      sample.frames++;
      sample.dt_ms.push(now - last); last = now;
      sample.focused &&= document.hasFocus();
      sample.visible &&= document.visibilityState === 'visible';
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
    await wait(seconds * 1000);
    stop = true; active = null;
    const elapsed = (performance.now() - start) / 1000;
    sample.fps = sample.frames / elapsed;
    sample.mirror_hz = sample.mirror_updates / elapsed;
    sample.elapsed_s = elapsed;
    sample.dt_ms.sort((a, b) => a - b);
    sample.p50_ms = sample.dt_ms[Math.floor(sample.dt_ms.length * .5)] ?? null;
    sample.p95_ms = sample.dt_ms[Math.floor(sample.dt_ms.length * .95)] ?? null;
    delete sample.dt_ms;
    result.samples.push(sample);
  };
  try {
    window.headless = false;
    // Freeze simulation, while keeping the driving render cadence and the actual camera/mirror path.
    g.tram.s = s; g.tram.v = 0; g.tram.a = 0; g.paused = false;
    g.update = () => {}; window.traffic.update = () => {};
    if (document.body.classList.contains('chase')) dispatchEvent(new KeyboardEvent('keydown', { key: 'v' }));
    if (document.body.classList.contains('nomirror')) key();
    await wait(2000);
    for (let i = 0; i < rounds; i++) {
      // Reversing the order helps expose warm-up or temperature drift.
      for (const on of i % 2 ? [true, false] : [false, true]) {
        const enabled = !document.body.classList.contains('nomirror');
        if (enabled !== on) key();
        await wait(500);
        await measure(on);
      }
    }
    result.foreground = result.samples.every(s => s.focused && s.visible);
    return result;
  } finally {
    active = null;
    renderer.render = original;
    g.update = saved.update; window.traffic.update = saved.traffic;
    g.paused = false;
    if (document.body.classList.contains('chase') !== saved.chase) dispatchEvent(new KeyboardEvent('keydown', {key:'v'}));
    if (!document.body.classList.contains('nomirror') !== saved.mirror) key();
    g.paused = saved.paused; g.tram.s = saved.s; g.tram.v = saved.v; g.tram.a = saved.a;
    window.headless = saved.headless;
  }
}
