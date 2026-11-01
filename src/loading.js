// Loading screen with a progress bar. All files of a line are requested at once (the browser
// streams them in parallel) and counted byte by byte; after the downloads come the build steps
// (terrain, track profile, city), which block the page, so each one yields a frame first to show
// its label. The bar is shared by expected time: the downloads by their speed so far, the build
// steps by their usual milliseconds (the weights).
import { t } from './i18n.js';

const DL_SHARE_MIN = 0.05;
const $ = (id) => document.getElementById(id);
const mb = (b) => (b / 1048576).toFixed(1);
// two frames (the label painted), or 100 ms where no frames come (a hidden tab draws none)
const nextFrame = () => new Promise((r) => {
  requestAnimationFrame(() => requestAnimationFrame(r));
  setTimeout(r, 100);
});

class Download {
  constructor(url, label, onChange) {
    this.url = url;
    this.label = label;
    this.loaded = 0;
    this.total = 0;      // Content-Length, 0 when unknown (a compressed response, no header)
    this.state = 'wait'; // wait, load, done, missing, error
    this.onChange = onChange;
    this.promise = this.run();
  }

  async run() {
    try {
      const res = await fetch(this.url);
      if (!res.ok) { this.state = 'missing'; this.onChange(); return null; }
      const len = +res.headers.get('Content-Length') || 0;
      // a compressed body counts decompressed bytes, so its length is no use as the total
      this.total = res.headers.get('Content-Encoding') ? 0 : len;
      this.state = 'load';
      this.onChange();
      if (!res.body) { const buf = new Uint8Array(await res.arrayBuffer()); this.loaded = buf.length; return this.finish(buf); }
      const reader = res.body.getReader();
      const chunks = [];
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        chunks.push(value);
        this.loaded += value.length;
        this.onChange();
      }
      const buf = new Uint8Array(this.loaded);
      let o = 0;
      for (const c of chunks) { buf.set(c, o); o += c.length; }
      return this.finish(buf);
    } catch (e) {
      console.warn('download failed', this.url, e);
      this.state = 'error';
      this.onChange();
      return null;
    }
  }

  finish(buf) {
    this.state = 'done';
    this.total = this.loaded;
    this.onChange();
    return buf;
  }
}

// the body of a finished download read as fetch's Response would, or null when it is not there
function body(buf, url) {
  if (!buf) return null;
  return {
    ok: true,
    url,
    bytes: buf,
    arrayBuffer: () => Promise.resolve(buf.buffer),
    json: () => Promise.resolve(JSON.parse(new TextDecoder().decode(buf))),
    blobUrl: (type) => URL.createObjectURL(new Blob([buf], { type })),
  };
}

export class Loader {
  constructor() {
    this.files = new Map();
    this.steps = [];      // build steps: { key, weight, done }
    this.step = null;
    this.t0 = performance.now();
    this.pending = false;
    this.el = $('loading');
  }

  fail(error) {
    this.failed = true;
    this.el?.classList.remove('hidden');
    $('loadPct').textContent = 'Cannot start';
    $('loadStep').textContent = `${error.message || error}. Reload the page; if it persists, report this message.`;
  }

  // start downloading now; get(url) later waits for it
  prefetch(url, label = url.split('/').pop()) {
    if (!this.files.has(url)) this.files.set(url, new Download(url, label, () => this.render()));
    return this;
  }

  // a fetch-like body ({ ok, json(), arrayBuffer() }) or { ok: false } when the file is missing
  async get(url) {
    this.prefetch(url);
    const d = this.files.get(url);
    return body(await d.promise, url) || { ok: false, url };
  }

  // the build steps that follow the downloads, with their share of the build part of the bar
  plan(steps) { this.steps = steps.map(([key, weight]) => ({ key, weight, done: false })); this.render(); }

  // mark the previous step done, show this one and let the page paint it
  async begin(key) {
    this.close();
    this.step = this.steps.find((s) => s.key === key) || { key, weight: 0, done: false };
    this.step.t0 = performance.now();
    this.step.parts = null;
    this.render(true);
    await nextFrame();
    this.painted = performance.now();
  }

  // the current step's parts, in order: [name, weight, label]; the bar moves through the step by them
  async parts(list) {
    this.step.parts = { list, total: list.reduce((a, p) => a + p[1], 0) || 1, done: 0, label: list[0]?.[2] };
    this.render(true);
    await nextFrame();
    this.painted = performance.now();
  }

  // part `name` of the current step is done: the bar on, the next part's label; the page is painted
  // when the label changes or the last paint is 150 ms old (each paint costs a frame or two)
  async partDone(name) {
    const P = this.step?.parts;
    if (!P) return;
    const i = P.list.findIndex((p) => p[0] === name);
    if (i < 0) return;
    P.done = P.list.slice(0, i + 1).reduce((a, p) => a + p[1], 0);
    const label = P.list[i + 1]?.[2];
    if (label === P.label && performance.now() - (this.painted || 0) < 150) return;
    P.label = label;
    this.render(true);
    await nextFrame();
    this.painted = performance.now();
  }


  // the running step done, its time noted
  close() {
    if (!this.step) return;
    this.step.done = true;
    this.step.ms = performance.now() - this.step.t0;
    if (this.steps[0] === this.step) this.step.downloadMs = this.step.t0 - this.t0;
  }

  finish() {
    this.close();
    for (const s of this.steps) s.done = true;
    this.step = null;
    this.render(true);
    this.el.classList.add('hidden');
    // how long the start took (window.loadTimes, for performance checks)
    // (scripts: from opening the page until our code ran, Three.js from the CDN included)
    window.loadTimes = { scripts: Math.round(this.t0), download: Math.round(this.steps[0]?.downloadMs ?? 0) };
    for (const s of this.steps) window.loadTimes[s.key] = Math.round(s.ms ?? 0);
    window.loadTimes.total = Math.round(performance.now() - this.t0);
    console.log('load times (ms)', window.loadTimes);
  }

  fraction() {
    const files = [...this.files.values()].filter((d) => d.state !== 'missing' && d.state !== 'error');
    // a file whose size is not known yet counts as large as the average known one
    const known = files.filter((d) => d.total);
    const avg = known.length ? known.reduce((a, d) => a + d.total, 0) / known.length : 1;
    let have = 0, want = 0;
    for (const d of files) {
      const w = d.total || avg;
      want += w;
      have += d.state === 'done' ? w : d.total ? d.loaded : 0;
    }
    const dl = want ? have / want : 0;
    const sw = this.steps.reduce((a, s) => a + s.weight, 0) || 1;
    let built = this.steps.reduce((a, s) => a + (s.done ? s.weight : 0), 0);
    const P = this.step?.parts;
    if (P && !this.step.done) built += this.step.weight * (P.done / P.total);
    let f;
    if (!this.files.size) f = built / sw; // (nothing to download: the steps fill the whole bar)
    else {
      // the downloads' share of the bar: their expected time (at the speed so far) against the build
      // steps' usual time (the weights are milliseconds); fixed once the downloads are done
      const downloading = files.some((d) => d.state === 'wait' || d.state === 'load');
      if (downloading || this.dlShare === undefined) {
        const ms = performance.now() - this.t0, dlMs = dl > 0.02 ? ms / dl : Infinity;
        this.dlShare = Math.max(DL_SHARE_MIN, Math.min(1, dlMs / (dlMs + sw)));
      }
      f = downloading ? this.dlShare * dl : this.dlShare + (1 - this.dlShare) * built / sw;
    }
    // (the share estimate moves with the speed: the bar never goes back)
    this.maxF = Math.max(this.maxF || 0, Math.min(1, f));
    return this.maxF;
  }

  // redraw at most once a frame while bytes stream in; now = immediately (before a blocking step)
  render(now = false) {
    if (this.failed) return;
    if (!now) {
      if (this.pending) return;
      this.pending = true;
      const draw = () => { if (this.pending) { this.pending = false; this.render(true); } };
      requestAnimationFrame(draw);
      setTimeout(draw, 250);
      return;
    }
    if (!this.el) return;
    const f = this.fraction();
    $('loadBar').style.width = `${(f * 100).toFixed(1)}%`;
    $('loadPct').textContent = `${Math.floor(f * 100)} %`;
    const files = [...this.files.values()];
    const loaded = files.reduce((a, d) => a + d.loaded, 0);
    const total = files.reduce((a, d) => a + (d.state === 'missing' || d.state === 'error' ? 0 : d.total), 0);
    const secs = (performance.now() - this.t0) / 1000;
    const downloading = files.some((d) => d.state === 'wait' || d.state === 'load');
    let info = `${mb(loaded)}${total > loaded ? ` / ${mb(total)}` : ''} MB`;
    if (downloading && secs > 0.5) info += ` · ${mb(loaded / secs)} MB/s`;
    $('loadBytes').textContent = info;
    const part = this.step?.parts?.label;
    $('loadStep').textContent = this.step ? t(`load.${this.step.key}`) + (part ? ` · ${t(`load.w.${part}`)}` : '') : downloading ? t('load.download') : '';
    $('loadFiles').innerHTML = files.map((d) => {
      const pct = d.state === 'done' ? '✓' : d.state === 'missing' ? t('load.missing') : d.state === 'error' ? t('load.error')
        : d.total ? `${Math.floor((d.loaded / d.total) * 100)} %` : d.loaded ? `${mb(d.loaded)} MB` : '…';
      const size = d.total ? `${mb(d.total)} MB` : '';
      return `<tr class="${d.state}"><td>${d.label}</td><td>${size}</td><td>${pct}</td></tr>`;
    }).join('');
  }
}
