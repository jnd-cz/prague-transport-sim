// Review mode (?review, #129): the findings of our checks on the map of the game, with layers that show
// the survey and links to street-level imagery at each place, on a desktop or a phone. No shift runs.
//   ?review                     findings from the data: the kerb review list (data/lineN.dtm.json
//                               provenance, tools/kerbs.py) and seams / flat kerbs between survey areas
//   ?review=reports/x.json      plus every {x, y} in that file (lint, headless results, a hand-made list)
//   &at=x,y,yaw,pitch,dist      the camera (the address follows it, so a place can be bookmarked or sent)
// Mouse: drag pans, right-drag (or Shift-drag) turns and tilts, wheel zooms, click a marker selects it.
// Touch: one finger pans, two fingers pinch, twist and tilt (move up / down together), tap a marker.
// Keys: W/A/S/D pan, Q/E turn, R/F tilt, + / − zoom, N / B next / previous finding, 1–4 an answer.
// Verdicts (#136): a button per answer and a note on the card, saved per line (src/verdicts.js) on the
// server; tools/deploy.py --pull-reviews (or reports/reviews/ locally) hands them to the agent.
import * as THREE from 'three';
import { toLatLon } from './geo.js';
import { Verdicts } from './verdicts.js';

const CARR = new Set(['road', 'tram', 'parking']), RAISED = new Set(['sidewalk', 'island', 'platform']);
const STREETS = new Set([...CARR, ...RAISED, 'paved', 'cycle']);
const CLASS_COLORS = {
  road: '#5b6cff', tram: '#b04bff', parking: '#4fb3ff', sidewalk: '#ffb02e', island: '#ff7a2e', platform: '#ff3e6c',
  paved: '#e6d84a', cycle: '#34d1a6', stairs: '#c9a27a', green: '#4caf50', water: '#2a8cff', deck: '#ffffff', rail: '#9e9e9e',
};
const SRC_COLORS = { kerbs: '#ff3e6c', seams: '#ffd400', file: '#3ee0ff' };
const SEAM = 0.03, FLAT = 0.05, CELL = 30; // m: a seam over 3 cm; a kerb under 5 cm; findings per 30 m
// (the class colours are drawn 0.2 m up: the OSM road ribbons lie 0.12 m over the survey)
const NEAR = 130; // m: the survey layers are drawn this far around the camera's target
const fmt = (v, d = 0) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d);
// the answers per kind of finding (a findings file can bring its own: "options": [...])
const OPTIONS = {
  kerb: ['kerb missing in game', 'ramp / level: OK', 'source wrong', 'unsure'],
  seam: ['visible step', 'not visible', 'unsure'],
  file: ['real problem', 'OK as is', 'source wrong', 'unsure'],
};
const options = (f) => f.options || (f.src === 'kerbs' || f.kind.startsWith('kerb') ? OPTIONS.kerb : f.src === 'seams' ? OPTIONS.seam : OPTIONS.file);
// (a finding's place and kind: the same after a rebuild that leaves it where it was)
const fid = (f) => `${f.src}|${f.kind}|${f.x.toFixed(1)},${f.y.toFixed(1)}`;
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// the kerb review list in the survey's provenance: wherever the stamp put it
function findKerbs(o) {
  if (!o || typeof o !== 'object') return null;
  if (Array.isArray(o.review) && 'platformSteps' in o) return o;
  for (const v of Object.values(o)) { const r = findKerbs(v); if (r) return r; }
  return null;
}

function kerbFindings(raw) {
  const k = findKerbs(raw?.provenance);
  return (k?.review || []).map((r) => ({
    src: 'kerbs', kind: `${r.c} ${r.line}`, x: r.x, y: r.y, mag: Math.abs(r.terrainOff) * 100, c: r.c,
    info: `terrain ${fmt(r.terrainOff * 100)} cm off the ${r.c} along ${r.kerb} m of kerb (the survey line taken as the kerb's ${r.line}, decided by the ${r.basis})`,
  }));
}

// Neighbouring survey areas at the same outline point: the same class (or road beside road) at another
// height is a seam, a road beside a sidewalk under 5 cm a flat kerb (sunk: the road higher). Points for
// the layer, findings grouped per 30 m.
function seamPoints(dtm) {
  const at = new Map();
  dtm.areas.forEach((a, i) => {
    if (a.l !== 0 || !STREETS.has(a.c)) return;
    for (const r of [a.ring, ...a.holes]) for (const p of r) {
      const k = `${Math.round(p[0] * 100)},${Math.round(p[1] * 100)}`;
      const l = at.get(k);
      if (!l) at.set(k, [{ i, p, c: a.c }]);
      else if (!l.some((e) => e.i === i)) l.push({ i, p, c: a.c });
    }
  });
  const pts = [];
  for (const l of at.values()) {
    if (l.length < 2) continue;
    let seam = 0, kerb = null, p = l[0].p;
    for (let u = 0; u < l.length; u++) for (let v = u + 1; v < l.length; v++) {
      const A = l[u], B = l[v], dz = B.p[2] - A.p[2];
      if (A.c === B.c || (CARR.has(A.c) && CARR.has(B.c))) { if (Math.abs(dz) > seam && Math.abs(dz) <= 1) { seam = Math.abs(dz); p = A.p; } }
      else if (Math.abs(dz) > 1) continue; // (another level: a street on a bridge over the sidewalk)
      else if (CARR.has(A.c) && RAISED.has(B.c)) kerb = kerb === null ? dz : Math.min(kerb, dz);
      else if (RAISED.has(A.c) && CARR.has(B.c)) kerb = kerb === null ? -dz : Math.min(kerb, -dz);
    }
    if (seam > SEAM) pts.push({ x: p[0], y: p[1], z: p[2], kind: 'seam', v: seam });
    if (kerb !== null && kerb < FLAT) pts.push({ x: l[0].p[0], y: l[0].p[1], z: l[0].p[2], kind: kerb < -0.02 ? 'kerb sunk' : 'kerb flat', v: kerb });
  }
  return pts;
}

function grouped(pts) {
  const cells = new Map();
  for (const q of pts) {
    const k = `${q.kind}|${Math.floor(q.x / CELL)},${Math.floor(q.y / CELL)}`;
    const g = cells.get(k);
    if (!g) cells.set(k, { q, n: 1, worst: q.v });
    else { g.n++; if (Math.abs(q.v) > Math.abs(g.worst)) { g.worst = q.v; g.q = q; } }
  }
  return [...cells.values()].map(({ q, n, worst }) => ({
    src: 'seams', kind: q.kind, x: q.x, y: q.y, z: q.z, mag: q.kind === 'seam' ? worst * 100 : n, // (kerbs: how many points, a long flat kerb first)
    info: q.kind === 'seam' ? `neighbouring areas up to ${(worst * 100).toFixed(0)} cm apart (${n} points within 30 m)`
      : `kerb step ${fmt(worst * 100)} cm (${n} points under 5 cm within 30 m)`,
  }));
}

// every object with numeric x and y in a findings file; its kind from the keys above it
function fileFindings(json, label) {
  const out = [], skip = new Set(['places', 'checks', 'result', 'review', 'findings', 'bad']);
  const opts = Array.isArray(json?.options) ? json.options.map(String) : undefined;
  const walk = (o, kind) => {
    if (Array.isArray(o)) { for (const v of o) walk(v, kind); return; }
    if (!o || typeof o !== 'object') return;
    if (typeof o.x === 'number' && typeof o.y === 'number') {
      const k = [kind, o.kind].filter(Boolean).join(': ') || label;
      out.push({ src: 'file', kind: k, x: o.x, y: o.y, mag: typeof o.mag === 'number' ? o.mag : 1, info: o.info || o.msg || '', options: opts });
      return;
    }
    for (const [k, v] of Object.entries(o)) walk(v, skip.has(k) ? kind : k);
  };
  walk(json, '');
  return out;
}

export class Review {
  constructor({ scene, camera, canvas, data, route, ground, world, url = '', at = null }) {
    Object.assign(this, { scene, camera, canvas, data, route, ground, world, dtm: ground.dtm });
    this.findings = [];
    this.list = [];
    this.cur = -1;
    this.T = { x: 0, y: 0, z: 0 };
    this.yaw = 0; this.pitch = 0.75; this.dist = 90;
    this.layers = { classes: true, wire: false, kerbs: true, seams: true, findings: true, track: true, buildings: true, trees: true };
    this.held = new Set();
    this.group = new THREE.Group();
    scene.add(this.group);
    this.near = new THREE.Group(); // the survey layers around the target, rebuilt as it moves
    this.group.add(this.near);
    this.nearAt = null;
    this.todo = false;
    this._names();
    this._ui();
    this.verdicts = new Verdicts(`line${data.line}`, { line: data.line, file: url || null }, () => this._sync());
    this._input();
    this._track();
    // findings: the data's own, then the file's
    let pts = [];
    if (this.dtm) {
      pts = seamPoints(this.dtm);
      this.seams = pts;
      this.findings.push(...kerbFindings(data.dtm), ...grouped(pts));
    }
    this.ready = (url ? fetch(url).then((r) => r.json()).then((j) => this.findings.push(...fileFindings(j, url.split('/').pop())))
      .catch((e) => this._note(`could not read ${url}: ${e.message}`)) : Promise.resolve()).then(() => {
      for (const f of this.findings) {
        f.z ??= ground.at(f.x, f.y);
        const n = route.nearest(f.x, f.y);
        f.s = n ? Math.round(n.s) : null;
      }
      this._filters();
      this._markers();
      // (the stored answers arrive while the first finding is shown)
      this.verdicts.load().then(() => this._redraw());
      if (at) {
        [this.T.x, this.T.y, this.yaw, this.pitch, this.dist] = at;
        this.T.z = ground.at(this.T.x, this.T.y);
        this._render();
        this._note(`${this.list.length} findings: tap a pin or choose one in the list`);
      }
      else if (this.list.length) this.select(0);
      else { const p = route.at(0); this.T = { x: p.x, y: p.y, z: ground.at(p.x, p.y) }; }
    });
  }

  // ------------------------------------------------------------------ where a place is
  // named OSM roads (tools/build_line.py "n") in 50 m cells, for "which street"
  _names() {
    this.roadCells = new Map();
    for (const r of this.data.roads || []) {
      if (!r.n) continue;
      for (let i = 1; i < r.p.length; i++) {
        const [x0, y0] = r.p[i - 1], [x1, y1] = r.p[i];
        const k = Math.floor((x0 + x1) / 100) * 100003 + Math.floor((y0 + y1) / 100);
        if (!this.roadCells.has(k)) this.roadCells.set(k, []);
        this.roadCells.get(k).push([x0, y0, x1, y1, r.n]);
      }
    }
  }

  streetAt(x, y) {
    let best = null, bd = 40;
    const ci = Math.floor(x / 50), cj = Math.floor(y / 50);
    for (let i = ci - 1; i <= ci + 1; i++) for (let j = cj - 1; j <= cj + 1; j++) {
      for (const [x0, y0, x1, y1, n] of this.roadCells.get(i * 100003 + j) || []) {
        const dx = x1 - x0, dy = y1 - y0, L = dx * dx + dy * dy, u = L ? Math.max(0, Math.min(1, ((x - x0) * dx + (y - y0) * dy) / L)) : 0;
        const d = Math.hypot(x - x0 - u * dx, y - y0 - u * dy);
        if (d < bd) { bd = d; best = n; }
      }
    }
    return best;
  }

  where(x, y) {
    const n = this.route.nearest(x, y), stops = this.data.stops;
    const st = n ? stops.reduce((a, b) => (Math.abs(b.s - n.s) < Math.abs(a.s - n.s) ? b : a)) : null;
    return { street: this.streetAt(x, y), stop: st?.name, ds: st ? Math.round(n.s - st.s) : null, s: n ? Math.round(n.s) : null, d: n ? Math.round(n.d) : null };
  }

  // ------------------------------------------------------------------ links
  links(x, y) {
    const [lat, lon] = toLatLon(x, y, this.data.frame.origin), la = lat.toFixed(6), lo = lon.toFixed(6);
    const hd = Math.round(((this.yaw * 180) / Math.PI + 360) % 360);
    return {
      lat, lon,
      Mapillary: `https://www.mapillary.com/app/?lat=${la}&lng=${lo}&z=19`,
      Panoramax: `https://api.panoramax.xyz/#focus=map&map=19/${la}/${lo}`,
      'Mapy.com': `https://mapy.com/fnc/v1/showmap?mapset=aerial&center=${lo},${la}&zoom=19&marker=true`,
      'Street View': `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${la},${lo}&heading=${hd}`,
    };
  }

  // ------------------------------------------------------------------ panel
  _ui() {
    const css = document.createElement('style');
    css.textContent = `
body.review #menu, body.review #cab, body.review #mirror, body.review #dash, body.review #help, body.review #action,
body.review #pausePanel, body.review #assist, body.review #top, body.review #minimap, body.review #results { display: none !important }
body.review #gl { touch-action: none }
#review { position: fixed; top: 0; right: 0; width: 380px; max-height: 100%; display: flex; flex-direction: column; z-index: 60;
  background: rgba(18,20,24,.92); color: #eee; font: 13px/1.4 system-ui, sans-serif; box-sizing: border-box; }
#review * { box-sizing: border-box }
#review .rvHead { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-bottom: 1px solid #333 }
#review .rvHead b { flex: 1 }
#review button, #review select, #review a.btn { font: inherit; color: #eee; background: #2c313a; border: 1px solid #444; border-radius: 6px;
  padding: 6px 10px; min-height: 34px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center }
#review button.on { background: #3d5a80; border-color: #6a8fc0 }
#review .rvRow { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 10px }
#review select { flex: 1; min-width: 0 }
#review .rvCard { padding: 8px 10px; border-top: 1px solid #333; border-bottom: 1px solid #333; background: rgba(40,46,56,.6) }
#review .rvCard .kind { font-weight: 700 }
#review .rvCard .dim, #review .dim { opacity: .7 }
#review .rvList { overflow: auto; flex: 1 1 auto; min-height: 0 }
#review .rvItem { padding: 8px 10px; border-top: 1px solid #2a2a2a; cursor: pointer }
#review .rvItem.sel { background: #3a4250 }
#review .rvItem .sw, #review .legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px }
#review .rvItem.done { opacity: .6 }
#review .rvItem .vd { color: #8fd18f }
#review .rvVerdict { padding-top: 8px }
#review textarea { width: 100%; font: inherit; color: #eee; background: #1d2026; border: 1px solid #444; border-radius: 6px; padding: 6px 8px; resize: vertical }
#review .legend { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 0 10px 6px; font-size: 11px }
#review:not(.lay) #rvLayers, #review:not(.lay) .legend { display: none }
#review.min .rvList, #review.min .rvRow.more, #review.min .legend { display: none }
@media (max-width: 700px), (max-height: 500px) and (pointer: coarse) {
  #review { top: auto; bottom: 0; left: 0; right: 0; width: auto; max-height: 52vh; border-radius: 12px 12px 0 0; font-size: 14px;
    overflow-y: auto; display: block }
  #review .rvList { overflow: visible }
  #review button, #review select, #review a.btn { min-height: 42px; padding: 8px 12px }
  #review .rvItem { padding: 11px 12px }
}`;
    document.head.appendChild(css);
    document.body.classList.add('review');
    const box = (this.box = document.createElement('div'));
    box.id = 'review';
    box.innerHTML = `
<div class="rvHead"><b>Review · line ${this.data.line}</b><span class="dim" id="rvCount"></span><button id="rvLay">Layers</button><button id="rvMin" title="fold the panel">▾</button></div>
<div class="rvRow more" id="rvLayers"></div>
<div class="legend" id="rvLegend">${Object.entries(CLASS_COLORS).map(([c, col]) => `<span><span class="sw" style="background:${col}"></span>${c}</span>`).join('')}</div>
<div class="rvRow more"><select id="rvFilter"></select><button id="rvTodo" title="hide the findings with an answer">to do</button></div>
<div class="rvCard" id="rvCard"><span class="dim">loading findings…</span></div>
<div class="rvList" id="rvList"></div>`;
    document.body.appendChild(box);
    const $ = (id) => box.querySelector(`#${id}`);
    const names = { classes: 'Classes', wire: 'Wireframe', kerbs: 'Kerbs', seams: 'Seams', findings: 'Pins', track: 'Track', buildings: 'Buildings', trees: 'Trees, wires' };
    for (const [k, label] of Object.entries(names)) {
      const b = document.createElement('button');
      b.textContent = label;
      b.classList.toggle('on', this.layers[k]);
      b.onclick = () => { this.layers[k] = !this.layers[k]; b.classList.toggle('on', this.layers[k]); this._applyLayers(); };
      $('rvLayers').appendChild(b);
    }
    $('rvLay').onclick = () => { box.classList.toggle('lay'); $('rvLay').classList.toggle('on', box.classList.contains('lay')); this._render(); };
    $('rvMin').onclick = () => { box.classList.toggle('min'); $('rvMin').textContent = box.classList.contains('min') ? '▴' : '▾'; this._render(); };
    $('rvFilter').onchange = () => { this._fill(); if (this.list.length) this.select(0); };
    $('rvTodo').onclick = () => { this.todo = !this.todo; $('rvTodo').classList.toggle('on', this.todo); this._fill(); if (this.list.length) this.select(0); };
    $('rvList').addEventListener('click', (e) => { const r = e.target.closest('.rvItem'); if (r) this.select(+r.dataset.i); });
    $('rvCard').addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.go) this.select(Math.max(0, Math.min(this.list.length - 1, this.cur + +b.dataset.go)));
      if (b.dataset.copy) navigator.clipboard?.writeText(location.href).then(() => { b.textContent = 'Copied'; }, () => { b.textContent = 'Copy failed'; });
      if (b.dataset.v !== undefined) this.verdict(b.dataset.v === '' ? null : options(this.list[this.cur])[+b.dataset.v]);
    });
    // a note typed without a new answer is kept with the answer there is
    $('rvCard').addEventListener('change', (e) => {
      if (e.target.id !== 'rvNote' || this.cur < 0) return;
      const f = this.list[this.cur], old = this.verdicts.get(fid(f));
      if (old || e.target.value.trim()) this._record(f, old?.v ?? null, e.target.value.trim());
    });
    this.$ = $;
  }

  _note(msg) { this.$('rvCard').innerHTML = `<span class="dim">${msg}</span>`; }

  _filters() {
    const sel = this.$('rvFilter'), by = {};
    for (const f of this.findings) by[`${f.src}|${f.kind}`] = (by[`${f.src}|${f.kind}`] || 0) + 1;
    const srcs = {};
    for (const f of this.findings) srcs[f.src] = (srcs[f.src] || 0) + 1;
    sel.innerHTML = `<option value="">all (${this.findings.length})</option>`
      + Object.entries(srcs).map(([s, n]) => `<option value="${s}|">${s}: all (${n})</option>`).join('')
      + Object.entries(by).sort().map(([k, n]) => `<option value="${k}">${k.replace('|', ': ')} (${n})</option>`).join('');
    // the first source with findings that are not grouped seams: the review lists come first
    const first = Object.keys(srcs).find((s) => s !== 'seams') || Object.keys(srcs)[0];
    sel.value = first ? `${first}|` : '';
    this._fill();
  }

  _fill() {
    const v = this.$('rvFilter').value, [src, kind] = v.split('|');
    const all = this.findings.filter((f) => !v || (f.src === src && (!kind || f.kind === kind)));
    this.list = all.filter((f) => !this.todo || !this.verdicts.get(fid(f))?.v).sort((a, b) => b.mag - a.mag);
    this.$('rvCount').textContent = `${all.filter((f) => this.verdicts.get(fid(f))?.v).length} / ${all.length} done`;
    this.$('rvList').innerHTML = this.list.slice(0, 400).map((f, i) => {
      const w = this.where(f.x, f.y);
      const r = this.verdicts.get(fid(f));
      return `<div class="rvItem${r?.v ? ' done' : ''}" data-i="${i}"><span class="sw" style="background:${SRC_COLORS[f.src]}"></span><b>${f.kind}</b> · ${f.mag.toFixed(0)}${r?.v ? ` · <span class="vd">✓ ${esc(r.v)}</span>` : ''}<br>
<span class="dim">${w.street || w.stop || ''}${w.s !== null ? ` · s ${w.s} m` : ''}</span></div>`;
    }).join('') + (this.list.length > 400 ? `<div class="rvItem dim">… ${this.list.length - 400} more (narrow the filter)</div>` : '');
    this.cur = -1;
    this._markers();
  }

  select(i) {
    const f = this.list[i];
    if (!f) return;
    this.cur = i;
    this.T = { x: f.x, y: f.y, z: f.z };
    if (this.dist > 120) this.dist = 60;
    this.box.querySelectorAll('.rvItem').forEach((r) => r.classList.toggle('sel', +r.dataset.i === i));
    // (the list scrolls on its own beside the map; on a phone the sheet scrolls, and stays at the card)
    if (getComputedStyle(this.$('rvList')).overflowY === 'auto') this.box.querySelector(`.rvItem[data-i="${i}"]`)?.scrollIntoView({ block: 'nearest' });
    else this.box.scrollTop = 0;
    this._card(f);
    this._highlight(f);
    this._render();
  }

  _card(f) {
    const w = this.where(f.x, f.y), L = this.links(f.x, f.y);
    const place = [w.street, w.stop && `${w.stop} ${w.ds >= 0 ? '+' : '−'}${Math.abs(w.ds)} m`].filter(Boolean).join(' · ');
    this.$('rvCard').innerHTML = `
<div><span class="kind">${f.kind}</span> <span class="dim">(${f.src}, ${this.cur + 1} / ${this.list.length})</span></div>
<div>${f.info}</div>
<div class="dim">${place || '—'}<br>s ${w.s ?? '?'} m, ${w.d ?? '?'} m from the track · x ${f.x.toFixed(1)}, y ${f.y.toFixed(1)} · ${L.lat.toFixed(6)}, ${L.lon.toFixed(6)}</div>
<div class="rvRow" style="padding:6px 0 0">${['Mapillary', 'Panoramax', 'Mapy.com', 'Street View'].map((k) => `<a class="btn" target="_blank" rel="noopener" href="${L[k]}">${k}</a>`).join('')}</div>
<div class="rvRow" style="padding:6px 0 0"><button data-go="-1">◀ prev</button><button data-go="1">next ▶</button><button data-copy="1">Copy link</button></div>
${this._verdictHtml(f)}`;
  }

  _verdictHtml(f) {
    const r = this.verdicts.get(fid(f));
    return `<div class="rvVerdict"><textarea id="rvNote" rows="2" placeholder="note (optional, before or after the answer)">${esc(r?.note || '')}</textarea>
<div class="rvRow" style="padding:6px 0 0">${options(f).map((o, i) => `<button data-v="${i}" class="${r?.v === o ? 'on' : ''}">${i + 1} · ${esc(o)}</button>`).join('')}${r?.v ? '<button data-v="" title="remove the answer">✕</button>' : ''}</div>
<div class="dim" id="rvSync">${this._syncText()}</div></div>`;
  }

  _syncText() {
    const V = this.verdicts, n = Object.keys(V.pending).length;
    const where = V.mode === 'php' ? 'on the server' : V.mode === 'serve' ? 'in reports/reviews/' : '';
    return V.state === 'loading' ? 'loading the saved answers…' : V.state === 'offline' ? `${n} not sent yet (kept on this device, sent with the next answer)`
      : V.state === 'sending' ? 'sending…' : `answers saved ${where}`;
  }

  _sync() { const e = this.$('rvSync'); if (e) e.textContent = this._syncText(); }

  // an answer (null: none) for the finding on the card, then the next one without an answer
  verdict(v) {
    const f = this.list[this.cur];
    if (!f) return;
    this._record(f, v, this.$('rvNote')?.value.trim() || '');
    const n = this.list.length;
    let next = null;
    if (v !== null) for (let k = 1; k <= n && !next; k++) { const g = this.list[(this.cur + k) % n]; if (!this.verdicts.get(fid(g))?.v) next = g; }
    this._redraw();
    if (next && this.list.includes(next)) this.select(this.list.indexOf(next));
  }

  _record(f, v, note) {
    const w = this.where(f.x, f.y);
    this.verdicts.set(fid(f), { v, note, src: f.src, kind: f.kind, x: +f.x.toFixed(2), y: +f.y.toFixed(2), mag: +f.mag.toFixed(2),
      info: f.info, street: w.street, stop: w.stop, s: w.s, at: location.search.match(/at=([^&]*)/)?.[1] });
  }

  // the list, pins and card again after the answers changed, on the same finding
  _redraw() {
    const f = this.list[this.cur];
    this._fill();
    const i = f ? this.list.indexOf(f) : -1;
    if (i >= 0) {
      this.cur = i;
      this.box.querySelectorAll('.rvItem').forEach((r) => r.classList.toggle('sel', +r.dataset.i === i));
      this._card(f);
    }
  }

  // ------------------------------------------------------------------ layers
  // our track: a 1.2 m ribbon over everything (WebGL draws lines 1 px wide whatever their width)
  _track() {
    const pos = [], idx = [], r = this.route, prof = this.ground.profile;
    for (let s = 0, i = 0; s <= r.length; s += 3, i++) {
      const p = r.at(s), z = prof.height(s) + 0.4;
      pos.push(p.x + p.hy * 0.6, z, -(p.y - p.hx * 0.6), p.x - p.hy * 0.6, z, -(p.y + p.hx * 0.6));
      if (i) idx.push(2 * i - 2, 2 * i - 1, 2 * i, 2 * i - 1, 2 * i + 1, 2 * i);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setIndex(idx);
    this.trackLine = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: '#3ee0ff', transparent: true, opacity: 0.85, depthTest: false, side: THREE.DoubleSide }));
    this.trackLine.renderOrder = 5;
    this.group.add(this.trackLine);
  }

  // a pin per finding in the list (0.5 m thick, 7 m tall: seen and tapped from 100 m away)
  _markers() {
    if (this.markers) { this.group.remove(this.markers); this.markers.dispose(); }
    this.pinGeo ??= new THREE.CylinderGeometry(0.25, 0.25, 7, 6).translate(0, 3.5, 0);
    const m = (this.markers = new THREE.InstancedMesh(this.pinGeo, new THREE.MeshBasicMaterial({ depthTest: false, transparent: true }), Math.max(1, this.list.length)));
    const M = new THREE.Matrix4(), c = new THREE.Color();
    this.list.forEach((f, i) => {
      m.setMatrixAt(i, M.makeTranslation(f.x, f.z, -f.y));
      m.setColorAt(i, c.set(this.verdicts.get(fid(f))?.v ? '#777' : SRC_COLORS[f.src] || '#fff'));
    });
    m.count = this.list.length;
    m.renderOrder = 6;
    m.frustumCulled = false;
    this.group.add(m);
    this._applyLayers();
  }

  // the selected finding: a ring on the ground and, for an area finding, the area's outline
  _highlight(f) {
    if (this.hl) { this.group.remove(this.hl); this.hl.traverse((o) => o.geometry?.dispose()); }
    this.hl = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.RingGeometry(2.2, 2.8, 32), new THREE.MeshBasicMaterial({ color: '#ffffff', depthTest: false, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(f.x, f.z + 0.3, -f.y);
    ring.renderOrder = 7;
    this.hl.add(ring);
    const a = f.c && this.dtm?.areas.find((a) => a.c === f.c && a.l === 0 && inRing(f.x, f.y, a.ring));
    if (a) {
      const pts = [...a.ring, a.ring[0]].map((p) => new THREE.Vector3(p[0], p[2] + 0.25, -p[1]));
      const o = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: '#ffffff', depthTest: false }));
      o.renderOrder = 7;
      this.hl.add(o);
    }
    this.group.add(this.hl);
  }

  // classes, kerb edges and seam points within NEAR of the target
  _near() {
    for (const o of [...this.near.children]) { this.near.remove(o); o.geometry.dispose(); }
    this.nearAt = { x: this.T.x, y: this.T.y };
    if (!this.dtm) return;
    const { x: tx, y: ty } = this.T, R2 = NEAR * NEAR, c = new THREE.Color();
    const tri = [], tcol = [], kerb = [], seam = [], scol = [];
    for (const a of this.dtm.areas) {
      if (a.c === 'wall' || a.c === 'roof') continue;
      a.box ??= bbox(a.ring);
      const [x0, y0, x1, y1] = a.box;
      if (x1 < tx - NEAR || x0 > tx + NEAR || y1 < ty - NEAR || y0 > ty + NEAR) continue;
      c.set(CLASS_COLORS[a.c] || '#888');
      for (const t of a.mesh) {
        const m = t[0];
        if ((m[0] - tx) ** 2 + (m[1] - ty) ** 2 > R2) continue;
        for (const p of t) { tri.push(p[0], p[2] + 0.2, -p[1]); tcol.push(c.r, c.g, c.b); }
      }
      if (a.kerbs) [a.ring, ...a.holes].forEach((r, ri) => {
        for (let i = 0; i < r.length; i++) {
          if (!a.kerbs[ri]?.[i]) continue;
          const p = r[i], q = r[(i + 1) % r.length];
          kerb.push(p[0], p[2] + 0.2, -p[1], q[0], q[2] + 0.2, -q[1]);
        }
      });
    }
    for (const q of this.seams || []) {
      if ((q.x - tx) ** 2 + (q.y - ty) ** 2 > R2) continue;
      c.set(q.kind === 'seam' ? (q.v > 0.1 ? '#ff2a2a' : '#ffd400') : q.kind === 'kerb sunk' ? '#c040ff' : '#3ea0ff');
      const h = q.kind === 'seam' ? Math.min(3, 0.6 + q.v * 10) : 1.2;
      seam.push(q.x, q.z, -q.y, q.x, q.z + h, -q.y);
      scol.push(c.r, c.g, c.b, c.r, c.g, c.b);
    }
    const geo = (p, col) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); if (col) g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); return g; };
    this.classMesh = new THREE.Mesh(geo(tri, tcol), new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.5, depthWrite: false, side: THREE.DoubleSide }));
    this.kerbLines = new THREE.LineSegments(geo(kerb), new THREE.LineBasicMaterial({ color: '#ff3e6c', depthTest: false }));
    this.seamBars = new THREE.LineSegments(geo(seam, scol), new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false }));
    this.kerbLines.renderOrder = this.seamBars.renderOrder = 4;
    // the survey's triangles as drawn (the outline points and the 5 m splits between them)
    this.wire = new THREE.LineSegments(new THREE.WireframeGeometry(this.classMesh.geometry), new THREE.LineBasicMaterial({ color: '#101418', transparent: true, opacity: 0.55 }));
    this.near.add(this.classMesh, this.wire, this.kerbLines, this.seamBars);
    this.kerbCount = kerb.length / 6;
    this._applyLayers();
  }

  _applyLayers() {
    const L = this.layers;
    if (this.classMesh) this.classMesh.visible = L.classes;
    if (this.wire) this.wire.visible = L.wire;
    if (this.kerbLines) this.kerbLines.visible = L.kerbs;
    if (this.seamBars) this.seamBars.visible = L.seams;
    if (this.markers) this.markers.visible = L.findings;
    if (this.trackLine) this.trackLine.visible = L.track;
    // (the world's meshes carry their build part, src/world.js buildWorld)
    for (const o of this.world?.children || []) {
      if (o.userData.part === 'buildings') o.visible = L.buildings;
      else if (o.userData.part === 'trees' || o.userData.part === 'catenary') o.visible = L.trees;
    }
    this.$('rvLegend').style.display = L.classes ? '' : 'none';
  }

  // ------------------------------------------------------------------ camera and input
  _render() {
    const { T, camera: cam } = this, h = Math.cos(this.pitch) * this.dist;
    // the target in the middle of what the panel leaves free (beside it on a desktop, above it on a phone)
    const W = this.canvas.clientWidth, Hh = this.canvas.clientHeight, b = this.box.getBoundingClientRect();
    const side = b.top <= 1 && b.left > W / 3, ox = side ? (W - b.left) / 2 : 0, oy = side ? 0 : Math.max(0, Hh - b.top) / 2;
    if (ox || oy) cam.setViewOffset(W, Hh, ox, oy, W, Hh); else cam.clearViewOffset();
    cam.position.set(T.x - Math.sin(this.yaw) * h, T.z + Math.sin(this.pitch) * this.dist, -(T.y - Math.cos(this.yaw) * h));
    cam.lookAt(T.x, T.z, -T.y);
    if (!this.nearAt || Math.hypot(T.x - this.nearAt.x, T.y - this.nearAt.y) > NEAR / 3) this._near();
    this.dirty = true;
  }

  _pan(dx, dy) {
    const k = (2 * this.dist * Math.tan((this.camera.fov * Math.PI) / 360)) / this.canvas.clientHeight;
    const s = Math.sin(this.yaw), c = Math.cos(this.yaw), f = k / Math.max(0.35, Math.sin(this.pitch));
    this.T.x += -c * dx * k + s * dy * f;
    this.T.y += s * dx * k + c * dy * f;
    this.T.z = this.ground.at(this.T.x, this.T.y);
  }

  _turn(dyaw, dpitch) {
    this.yaw += dyaw;
    this.pitch = Math.max(0.12, Math.min(1.55, this.pitch + dpitch));
  }

  _zoom(k) { this.dist = Math.max(6, Math.min(1500, this.dist * k)); }

  _input() {
    const cv = this.canvas, ptr = new Map();
    let mode = null, tap = null, two = null;
    const pair = () => {
      const [a, b] = [...ptr.values()];
      return { d: Math.hypot(b.x - a.x, b.y - a.y), ang: Math.atan2(b.y - a.y, b.x - a.x), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
    };
    cv.addEventListener('contextmenu', (e) => e.preventDefault());
    cv.addEventListener('pointerdown', (e) => {
      ptr.set(e.pointerId, { x: e.clientX, y: e.clientY });
      try { cv.setPointerCapture(e.pointerId); } catch { /* (a pointer the browser no longer tracks) */ }
      if (ptr.size === 1) { mode = e.button === 2 || e.shiftKey ? 'turn' : 'pan'; tap = { x: e.clientX, y: e.clientY, t: performance.now() }; }
      else { tap = null; two = pair(); }
    });
    cv.addEventListener('pointermove', (e) => {
      const p = ptr.get(e.pointerId);
      if (!p) return;
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (tap && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) > 8) tap = null;
      if (ptr.size >= 2 && two) {
        const q = pair();
        this._zoom(two.d / Math.max(1, q.d));
        // (the map turns with the fingers: a clockwise twist turns the view, i.e. the heading, anticlockwise)
        this._turn(two.ang - q.ang, (q.my - two.my) * 0.004);
        two = q;
      } else if (mode === 'turn') this._turn(-dx * 0.006, dy * 0.005);
      else this._pan(dx, dy);
      this._render();
    });
    const up = (e) => {
      ptr.delete(e.pointerId);
      if (ptr.size < 2) two = null;
      if (ptr.size === 1) { tap = null; mode = 'pan'; } // (from two fingers back to one: panning on)
      if (tap && ptr.size === 0 && performance.now() - tap.t < 500) this._pick(e.clientX, e.clientY);
      if (!ptr.size) tap = null;
    };
    cv.addEventListener('pointerup', up);
    cv.addEventListener('pointercancel', up);
    cv.addEventListener('wheel', (e) => { e.preventDefault(); this._zoom(Math.exp(e.deltaY * 0.0012)); this._render(); }, { passive: false });
    window.addEventListener('keydown', (e) => {
      if (e.target.closest?.('select, input, textarea')) return;
      const k = e.key.toLowerCase();
      const o = this.cur >= 0 && /^[1-9]$/.test(k) && options(this.list[this.cur])[+k - 1];
      if (o) { this.verdict(o); return; }
      if (k === 'n') this.select(Math.min(this.list.length - 1, this.cur + 1));
      else if (k === 'b') this.select(Math.max(0, this.cur - 1));
      else if (k === '+' || k === '=') { this._zoom(0.8); this._render(); }
      else if (k === '-') { this._zoom(1.25); this._render(); }
      else if ('wasdqerf'.includes(k) && k.length === 1) this.held.add(k);
    });
    window.addEventListener('keyup', (e) => this.held.delete(e.key.toLowerCase()));
    window.addEventListener('blur', () => this.held.clear());
    window.addEventListener('resize', () => this._render());
  }

  // a tap or click: the nearest marker on the screen within 28 px
  _pick(cx, cy) {
    const r = this.canvas.getBoundingClientRect(), v = new THREE.Vector3();
    let best = -1, bd = 28;
    this.list.forEach((f, i) => {
      if (i >= 4000) return;
      v.set(f.x, f.z + 3, -f.y).project(this.camera);
      if (v.z > 1) return;
      const d = Math.hypot(r.left + ((v.x + 1) / 2) * r.width - cx, r.top + ((1 - v.y) / 2) * r.height - cy);
      if (d < bd) { bd = d; best = i; }
    });
    if (best >= 0) this.select(best);
  }

  // every frame: held keys, and the address once the camera rests
  update(dt) {
    const h = this.held;
    if (h.size) {
      const v = (this.canvas.clientHeight * 0.8) * dt;
      if (h.has('w')) this._pan(0, v);
      if (h.has('s')) this._pan(0, -v);
      if (h.has('a')) this._pan(v, 0);
      if (h.has('d')) this._pan(-v, 0);
      if (h.has('q')) this._turn(1.2 * dt, 0);
      if (h.has('e')) this._turn(-1.2 * dt, 0);
      if (h.has('r')) this._turn(0, 0.8 * dt);
      if (h.has('f')) this._turn(0, -0.8 * dt);
      this._render();
    }
    this.retry = (this.retry ?? 30) - dt;
    if (this.retry <= 0) { this.retry = 30; if (this.verdicts.state === 'offline') this.verdicts.send(); }
    this.urlWait = (this.urlWait || 0) - dt;
    if (this.dirty && this.urlWait <= 0) {
      this.dirty = false;
      this.urlWait = 0.5;
      const p = new URLSearchParams(location.search), d = (v) => Math.round((v * 180) / Math.PI);
      p.set('at', [this.T.x.toFixed(1), this.T.y.toFixed(1), d(this.yaw), d(this.pitch), Math.round(this.dist)].join(','));
      history.replaceState(null, '', `?${p.toString().replace(/%2C/g, ',').replace(/%2F/g, '/')}`);
    }
  }
}

// ?at=x,y,yaw,pitch,dist (degrees) → [x, y, yaw, pitch, dist] in radians, or null
export function parseAt(v) {
  const a = (v || '').split(',').map(Number);
  if (a.length < 2 || a.slice(0, 2).some((n) => !Number.isFinite(n))) return null;
  const r = (n, d) => (Number.isFinite(n) ? (n * Math.PI) / 180 : d);
  return [a[0], a[1], r(a[2], 0), r(a[3], 0.75), Number.isFinite(a[4]) ? a[4] : 90];
}

function bbox(r) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of r) { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
  return [x0, y0, x1, y1];
}

function inRing(x, y, r) {
  let inside = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    if ((r[i][1] > y) !== (r[j][1] > y) && x < ((r[j][0] - r[i][0]) * (y - r[i][1])) / (r[j][1] - r[i][1]) + r[i][0]) inside = !inside;
  }
  return inside;
}
