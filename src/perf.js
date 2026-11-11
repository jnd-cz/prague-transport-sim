// How the game runs on the player's machine (#350): a frame-time log over a shift, the machine's facts, and
// the GPU's own time per frame where the browser offers a timer. A note carries them (src/report.js), a shift's
// end offers to send them, and the menu's performance test drives a fixed stretch to compare machines.
// A player's browser keeps vsync on, so the interval between frames stops at the display's rate: the shares of
// frames over 20 / 33 / 50 ms say whether the machine keeps up, not what a frame costs (tools/frametime.py
// measures that here, vsync off). The log is a counter per frame: no work in a frame beyond it.

const BINS = 201;          // 1 ms bins of the frame interval, the last one 200 ms and over
const GAP = 250;           // ms: a longer interval is a pause, a hidden tab or an idle redraw, not a frame
const STRETCH = 100;       // m of route per bin of the slow frames' places

export class PerfLog {
  constructor() { this.reset(); }

  // a new shift (or test): what it ran with
  reset(meta = {}) {
    this.meta = meta;
    this.hist = new Uint32Array(BINS);
    this.n = 0; this.sum = 0;
    this.slowAt = new Map(); // route bin -> frames over 33 ms
    this.calls = { sum: 0, max: 0 }; this.tris = { sum: 0, max: 0 };
    this.last = 0;
  }

  // one drawn frame while driving: now (ms), the tram's route position, the renderer's counts
  frame(now, s, info) {
    const dt = now - this.last;
    this.last = now;
    if (!(dt > 0 && dt < GAP) || document.hidden) return;
    this.hist[Math.min(BINS - 1, Math.round(dt))]++;
    this.n++; this.sum += dt;
    if (dt > 33.4 && Number.isFinite(s)) {
      const k = Math.floor(s / STRETCH);
      this.slowAt.set(k, (this.slowAt.get(k) || 0) + 1);
    }
    if (info) {
      this.calls.sum += info.calls; this.calls.max = Math.max(this.calls.max, info.calls);
      this.tris.sum += info.triangles; this.tris.max = Math.max(this.tris.max, info.triangles);
    }
  }

  // the interval below which a share p of the frames fall (ms)
  pct(p) {
    let need = p * this.n, acc = 0;
    for (let i = 0; i < BINS; i++) if ((acc += this.hist[i]) >= need) return i;
    return BINS - 1;
  }

  over(ms) {
    let c = 0;
    for (let i = Math.ceil(ms); i < BINS; i++) c += this.hist[i];
    return this.n ? Math.round((c / this.n) * 1000) / 10 : 0; // % of frames
  }

  // what a note or a test sends: small, no per-frame data
  summary() {
    if (!this.n) return null;
    const worst = [...this.slowAt].sort((a, b) => b[1] - a[1]).slice(0, 5)
      .map(([k, c]) => ({ s: k * STRETCH, slow: c }));
    const mem = performance.memory;
    return {
      ...this.meta, frames: this.n, seconds: Math.round(this.sum / 100) / 10, fps: Math.round((this.n * 10000) / this.sum) / 10,
      ms: { p50: this.pct(0.5), p90: this.pct(0.9), p99: this.pct(0.99) },
      over: { 20: this.over(20.5), 33: this.over(33.4), 50: this.over(50) },
      worst, calls: { mean: Math.round(this.calls.sum / this.n), max: this.calls.max },
      triangles: { mean: Math.round(this.tris.sum / this.n), max: this.tris.max },
      ...(mem ? { heapMB: Math.round(mem.usedJSHeapSize / 1e6) } : {}),
    };
  }
}

// the machine as the page sees it: no identifier, only what tells machines apart for performance
export function machine(renderer) {
  const out = { cores: navigator.hardwareConcurrency || null, memoryGB: navigator.deviceMemory || null,
    screen: `${screen.width}x${screen.height}`, viewport: `${innerWidth}x${innerHeight}`, dpr: devicePixelRatio,
    touch: navigator.maxTouchPoints > 0 };
  try {
    const gl = renderer.getContext();
    out.webgl2 = typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext;
    out.pixelRatio = renderer.getPixelRatio();
    out.maxTexture = gl.getParameter(gl.MAX_TEXTURE_SIZE);
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    // (some browsers hide it, or give only the vendor: then the GPU stays unknown)
    out.gpu = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null;
    out.gpuVendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null;
  } catch { /* (a lost context) */ }
  return out;
}

// The GPU's time per frame (EXT_disjoint_timer_query_webgl2): begin()/end() around the draw, poll() each frame
// collects the answers that are ready (a query answers a few frames later). null where the browser has no timer.
export function gpuTimer(gl) {
  const ext = gl.getExtension?.('EXT_disjoint_timer_query_webgl2');
  if (!ext || typeof gl.createQuery !== 'function') return null;
  const pending = [], times = [];
  let q = null;
  return {
    times,
    begin() { if (q) return; q = gl.createQuery(); gl.beginQuery(ext.TIME_ELAPSED_EXT, q); },
    end() { if (!q) return; gl.endQuery(ext.TIME_ELAPSED_EXT); pending.push(q); q = null; },
    poll() {
      const disjoint = gl.getParameter(ext.GPU_DISJOINT_EXT);
      while (pending.length && gl.getQueryParameter(pending[0], gl.QUERY_RESULT_AVAILABLE)) {
        const p = pending.shift();
        if (!disjoint) times.push(gl.getQueryParameter(p, gl.QUERY_RESULT) / 1e6);
        gl.deleteQuery(p);
      }
    },
    median() {
      if (!times.length) return null;
      const a = [...times].sort((x, y) => x - y);
      return Math.round(a[a.length >> 1] * 100) / 100;
    },
  };
}
