// Review mode (?review, #129): the findings of our checks on the map of the game, with layers that show
// the survey and links to street-level imagery at each place, on a desktop or a phone. No shift runs.
//   ?review                     findings from the data: the kerb review list (data/lineN.dtm.json
//                               provenance, tools/kerbs.py) and seams / flat kerbs between survey areas
//   ?review=reports/x.json      plus every {x, y} in that file (lint, headless results, a hand-made list)
//   &at=x,y,yaw,pitch,dist      the camera (the address follows it, so a place can be bookmarked or sent)
//   &todo                       only the findings without an answer (the review directory, reviews.html)
// Mouse, as in the game's free cameras (#342): drag turns and tilts, right-drag (or Shift-drag) moves, wheel zooms,
// click a marker selects it.
// Touch: one finger pans, two fingers pinch, twist and tilt (move up / down together), tap a marker.
// Keys: W/A/S/D move, R/F up / down, Q/E or ← / → turn, ↑ / ↓ tilt, + / − zoom, N / B next / previous finding, 1–4 an answer.
// Verdicts (#136): a button per answer and a note on the card, saved per line (src/verdicts.js) on the
// server; tools/deploy.py --pull-reviews (or reports/reviews/ locally) hands them to the agent.
import * as THREE from 'three';
import { toLatLon } from './geo.js';
import { Verdicts, readLineAnswers } from './verdicts.js';
import { heightProfile } from './trackHeightProfile.js';
import { fid, loadFindings, answerOf } from './reviewFindings.js';

const CARR = new Set(['road', 'tram', 'parking']), RAISED = new Set(['sidewalk', 'island', 'platform']);
const STREETS = new Set([...CARR, ...RAISED, 'paved', 'cycle']);
const CLASS_COLORS = {
  road: '#5b6cff', tram: '#b04bff', parking: '#4fb3ff', sidewalk: '#ffb02e', island: '#ff7a2e', platform: '#ff3e6c',
  paved: '#e6d84a', cycle: '#34d1a6', stairs: '#c9a27a', green: '#4caf50', water: '#2a8cff', deck: '#ffffff', rail: '#9e9e9e',
};
const SRC_COLORS = { kerbs: '#ff3e6c', seams: '#ffd400', file: '#3ee0ff' };
const HEIGHT_COLORS = { review: '#ff9e31', conflict: '#ff3333', di_numeric: '#3e9dff', approved: '#52d976' };
const HL = '#ffe600'; // the selected finding: its ring and its area's outline
const SEAM = 0.03, FLAT = 0.05, CELL = 30; // m: a seam over 3 cm; a kerb under 5 cm; findings per 30 m
// (the class colours are drawn 0.2 m up: the OSM road ribbons lie 0.12 m over the survey)
const NEAR = 130; // m: the survey layers are drawn this far around the camera's target
const fmt = (v, d = 0) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d);
// the answers per kind of finding (a findings file can bring its own: "options": [...]). They compare the
// game with reality (the imagery); whether the source or the build is wrong is for the agent to find
// (the Source layer shows the survey as it comes)
const OPTIONS = {
  kerb: ['wrong in game', 'matches reality', 'other level / wall', 'unsure'],
  seam: ['visible step', 'not visible', 'unsure'],
  file: ['wrong in game', 'matches reality', 'unsure'],
  trackheight: ['archive profile ok', 'follows survey surface', 'other level (deck / under)', 'unsure'],
};
const LEVEL_COLORS = { '-1': '#3ee0ff', 0: '#ffffff', 1: '#ff9a3e' }; // the source's levels: under, at, over ground
// the IPR orthophoto (#201): leaf-off flight 2026, 0.05 m, CC BY 4.0. The browser loads it straight from
// IPR (the service answers CORS for any origin): nothing goes through or stays on our server. One image
// of ORTHO_M around the target at 0.1 m (~280 kB), taken again when the target leaves its middle ORTHO_STEP;
// close up (the camera within ORTHO_NEAR) half of it at the native 0.05 m: a rail head (~6 cm) is lost at 0.1 m.
const ORTHO = 'https://gs-pub.praha.eu/imgs/rest/services/ort/mimovegetacni_letecke_snimkovani/ImageServer';
const ORTHO_M = 150, ORTHO_PX = 1500, ORTHO_STEP = 50, ORTHO_GRID = 2, ORTHO_NEAR = 40; // m, px, m, m between draped vertices, m
const ORTHO_CREDIT = 'Ortofoto: IPR Praha (CC BY 4.0)';
// the line's track centrelines by source (data/lineN.json tracks[].src, tools/build_line.py)
const TRACK_COLORS = { di: '#ff8c1a', osm: '#e040fb', dtmp: '#ffe14a', ortho: '#7cff6b' };
const options = (f) => f.options || (f.kind === 'trackheight' ? OPTIONS.trackheight : f.src === 'kerbs' || f.kind.startsWith('kerb') ? OPTIONS.kerb : f.src === 'seams' ? OPTIONS.seam : OPTIONS.file);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

// the kerb review list in the survey's provenance: wherever the stamp put it
function findKerbs(o) {
  if (!o || typeof o !== 'object') return null;
  if (Array.isArray(o.review) && 'platformSteps' in o) return o;
  for (const v of Object.values(o)) { const r = findKerbs(v); if (r) return r; }
  return null;
}

export function kerbFindings(raw) {
  const k = findKerbs(raw?.provenance);
  return (k?.review || []).map((r) => {
    const osm = Object.entries(r.osmKerb || {}).map(([v, n]) => `kerb=${v} ×${n}`).join(', ');
    return {
      src: 'kerbs', kind: `${r.c} ${r.line}`, x: r.x, y: r.y, mag: Math.abs(r.terrainOff) * 100, c: r.c,
      info: `terrain ${fmt(r.terrainOff * 100)} cm off the ${r.c} along ${r.kerb} m of kerb (the survey line taken as the kerb's ${r.line}, decided by the ${r.basis})${osm ? ` · OSM: ${osm} along this kerb` : ''}`,
    };
  });
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

// (the findings' reading and identity: src/reviewFindings.js, shared with the review directory, #288)
export { loadFindings };

export class Review {
  constructor({ scene, camera, canvas, data, route, ground, world, url = '', at = null }) {
    Object.assign(this, { scene, camera, canvas, data, route, ground, world, dtm: ground.dtm });
    this.findings = [];
    this.list = [];
    this.cur = -1;
    this.T = { x: 0, y: 0, z: 0 };
    this.yaw = 0; this.pitch = 0.75; this.dist = 90;
    this.layers = { classes: true, wire: false, source: false, kerbs: true, seams: true, findings: true, track: true, buildings: true, trees: true, ortho: false, sources: false };
    this.look = { contrast: false, lines: false }; // the orthophoto's (orthoLook)
    this.held = new Set();
    this.group = new THREE.Group();
    scene.add(this.group);
    this.near = new THREE.Group(); // the survey layers around the target, rebuilt as it moves
    this.group.add(this.near);
    this.nearAt = null;
    // (&todo: only the findings without an answer, as the review directory's links open it, #288)
    this.todo = new URLSearchParams(location.search).has('todo');
    // (findings answered since the list was last filtered stay in it, to be revisited or changed: they
    // left it at once, and a point placed took its card away, #310)
    this.kept = new Set();
    this._names();
    this._ui();
    this.file = url || null; // (the findings file it was opened with: the list starts on it)
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
    this.ready = (url ? loadFindings(url).then((items) => this.findings.push(...items))
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
      if (this.findings.some((f) => f.kind === 'trackheight')) this._loadOtherAnswers();
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
#review .rvCard { padding: 8px 10px; border-top: 1px solid #333; border-bottom: 1px solid #333; background: rgba(40,46,56,.6);
  flex: 0 1 auto; min-height: 6em; overflow-y: auto; overscroll-behavior: contain }
#review .rvCard .kind { font-weight: 700 }
#review .rvCard .dim, #review .dim { opacity: .7 }
/* (the card first: a taller one, e.g. a track-height chart, scrolls on its own, the list keeps four rows, #178) */
#review .rvList { overflow: auto; flex: 1 1 0; min-height: 16em }
#review .rvItem { padding: 8px 10px; border-top: 1px solid #2a2a2a; cursor: pointer }
#review .rvItem.sel { background: #3a4250 }
#review .rvItem .sw, #review .legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px }
#review .rvItem.done { opacity: .6 }
.rvTip { position: fixed; z-index: 61; pointer-events: none; display: none; background: rgba(18,20,24,.92); color: #eee;
  font: 12px/1.3 system-ui, sans-serif; padding: 4px 8px; border-radius: 6px; white-space: nowrap }
#review .rvItem .vd { color: #8fd18f }
#review .rvVerdict { padding-top: 8px }
#review textarea { width: 100%; font: inherit; color: #eee; background: #1d2026; border: 1px solid #444; border-radius: 6px; padding: 6px 8px; resize: vertical }
#review .legend { display: flex; flex-wrap: wrap; gap: 4px 10px; padding: 0 10px 6px; font-size: 11px }
#review:not(.lay) #rvLayers, #review:not(.lay) .legend { display: none }
#rvCredit { position: fixed; top: 6px; left: 6px; z-index: 60; max-width: calc(100% - 12px); background: rgba(18,20,24,.8); color: #eee;
  font: 12px/1.3 system-ui, sans-serif; padding: 3px 8px; border-radius: 6px; display: none }
#rvCredit.err { color: #ffb0b0 }
#review label.chk { display: inline-flex; align-items: center; gap: 4px; padding: 0 6px 0 2px; cursor: pointer }
#review label.chk input { width: 18px; height: 18px; margin: 0 }
#review.min .rvList, #review.min .rvRow.more, #review.min .legend { display: none }
@media (max-width: 700px), (max-height: 500px) and (pointer: coarse) {
  #review { top: auto; bottom: 0; left: 0; right: 0; width: auto; max-height: 52vh; border-radius: 12px 12px 0 0; font-size: 14px;
    overflow-y: auto; display: block }
  #review .rvList { overflow: visible; min-height: 0 }
  #review .rvCard { overflow: visible }
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
<div class="legend" id="rvTrackLegend">tracks: ${Object.entries(TRACK_COLORS).map(([c, col]) => `<span><span class="sw" style="background:${col}"></span>${c}</span>`).join('')}</div>
<div class="rvRow more"><select id="rvFilter"></select><button id="rvTodo" title="hide the findings with an answer">to do</button></div>
<div class="rvCard" id="rvCard"><span class="dim">loading findings…</span></div>
<div class="rvList" id="rvList"></div>`;
    document.body.appendChild(box);
    // (over the map, where the panel is not: the orthophoto's credit and whether it loaded)
    this.credit = document.createElement('div');
    this.credit.id = 'rvCredit';
    document.body.appendChild(this.credit);
    const $ = (id) => box.querySelector(`#${id}`);
    const names = { classes: 'Classes', wire: 'Wireframe', source: 'Source', kerbs: 'Kerbs', seams: 'Seams', findings: 'Pins', track: 'Track', buildings: 'Buildings', trees: 'Trees, wires', ortho: 'Orthophoto', sources: 'Track sources' };
    for (const [k, label] of Object.entries(names)) {
      const b = document.createElement('button');
      b.textContent = label;
      b.dataset.layer = k;
      b.classList.toggle('on', this.layers[k]);
      b.onclick = () => {
        this.layers[k] = !this.layers[k];
        b.classList.toggle('on', this.layers[k]);
        if (k === 'source' && this.layers.source) this._loadSource();
        if (k === 'ortho') {
          this.orthoAt = null; this._ortho(); // (switched on again: a failed load is tried again)
          // (the classes are drawn after any opaque mesh, over the photo: off with it, one click brings them back)
          if (this.layers.ortho && this.layers.classes) $('rvLayers').querySelector('[data-layer="classes"]').click();
        }
        if (k === 'sources' && this.layers.sources) this._trackSources();
        this._applyLayers();
      };
      $('rvLayers').appendChild(b);
      // the orthophoto's look, beside its button (orthoLook)
      if (k === 'ortho') for (const [key, text, tip] of [['contrast', 'contrast', 'each spot against its 1 m surround'], ['lines', 'lines', 'thin dark lines (rails, joints) in cyan']]) {
        const l = document.createElement('label');
        l.className = 'chk';
        l.title = tip;
        l.innerHTML = `<input type="checkbox" data-look="${key}"> ${text}`;
        l.firstChild.onchange = (e) => { this.look[key] = e.target.checked; this._orthoMap(); };
        $('rvLayers').appendChild(l);
      }
    }
    $('rvLay').onclick = () => { box.classList.toggle('lay'); $('rvLay').classList.toggle('on', box.classList.contains('lay')); this._render(); };
    $('rvMin').onclick = () => { box.classList.toggle('min'); $('rvMin').textContent = box.classList.contains('min') ? '▴' : '▾'; this._render(); };
    $('rvFilter').onchange = () => { this.kept.clear(); this._fill(); if (this.list.length) this.select(0); };
    $('rvTodo').onclick = () => { this.todo = !this.todo; this.kept.clear(); $('rvTodo').classList.toggle('on', this.todo); this._fill(); if (this.list.length) this.select(0); };
    $('rvTodo').classList.toggle('on', this.todo);
    $('rvList').addEventListener('click', (e) => { const r = e.target.closest('.rvItem'); if (r) this.select(+r.dataset.i); });
    $('rvCard').addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.go) this.select(Math.max(0, Math.min(this.list.length - 1, this.cur + +b.dataset.go)));
      const opt = b.dataset.v ? options(this.list[this.cur])[+b.dataset.v] : null;
      if (b.dataset.place || (opt && opt === this.list[this.cur]?.placeOption)) {
        this.placing = this.list[this.cur]; b.classList.add('on'); b.textContent = 'Now click the map where it is';
        return;
      }
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
    // the file it was opened with, else the first source with findings that are not grouped seams: the review lists
    // come first (a line's kerbs would hide the 27 track-height cards of a named file under 168 of their own)
    const first = this.file && srcs.file ? 'file' : Object.keys(srcs).find((s) => s !== 'seams') || Object.keys(srcs)[0];
    sel.value = first ? `${first}|` : '';
    this._fill();
  }

  _fill() {
    const v = this.$('rvFilter').value, [src, kind] = v.split('|');
    const all = this.findings.filter((f) => !v || (f.src === src && (!kind || f.kind === kind)));
    this.list = all.filter((f) => !this.todo || !this._answer(f)?.v || this.kept.has(fid(f))).sort((a, b) => b.mag - a.mag);
    const height = this.findings.filter((f) => f.kind === 'trackheight');
    const across = height.length ? ` · track heights: ${height.filter((f) => this._answer(f)?.v).length} / ${height.length} answered across lines${this.otherAnswersReady ? '' : ' (loading or offline)'}` : '';
    this.$('rvCount').textContent = `${all.filter((f) => this.verdicts.get(fid(f))?.v).length} / ${all.length} done${across}`;
    this.$('rvList').innerHTML = this.list.slice(0, 400).map((f, i) => {
      const w = this.where(f.x, f.y);
      const r = this._answer(f);
      const lines = f.kind === 'trackheight' ? ` · lines ${[...new Set(f.spans.map((s) => s.line))].sort((a, b) => a - b).join(', ')}` : '';
      return `<div class="rvItem${r?.v ? ' done' : ''}" data-i="${i}"><span class="sw" style="background:${SRC_COLORS[f.src]}"></span><b>${f.kind}</b>${lines} · ${f.mag.toFixed(0)}${r?.v ? ` · <span class="vd">✓ ${esc(r.v)}</span>` : ''}<br>
<span class="dim">${w.street || w.stop || ''}${w.s !== null ? ` · s ${w.s} m` : ''}</span></div>`;
    }).join('') + (this.list.length > 400 ? `<div class="rvItem dim">… ${this.list.length - 400} more (narrow the filter)</div>` : '');
    this.cur = -1;
    this._markers();
  }

  _answer(f) {
    const local = this.verdicts.get(fid(f)), other = f.kind === 'trackheight' ? this.otherAnswers?.[fid(f)] : null;
    return answerOf(f, other && (!local || (other.t || 0) > (local.t || 0)) ? other : local);
  }

  async _loadOtherAnswers() {
    try {
      const response = await fetch('data/lines.json');
      if (!response.ok) throw new Error('line list unavailable');
      const lines = await response.json();
      const stores = await Promise.all(lines.filter((l) => String(l.line) !== String(this.data.line)).map((l) => readLineAnswers(`line${l.line}`)));
      this.otherAnswers = {};
      for (const store of stores) for (const [k, v] of Object.entries(store.items))
        if (!this.otherAnswers[k] || (v.t || 0) >= (this.otherAnswers[k].t || 0)) this.otherAnswers[k] = v;
      this.otherAnswersReady = stores.every((s) => s.available);
    } catch { this.otherAnswersReady = false; }
    this._redraw();
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
    this.$('rvCard').scrollTop = 0;
    this._highlight(f);
    this._render();
  }

  _card(f) {
    const w = this.where(f.x, f.y), L = this.links(f.x, f.y);
    const place = [w.street, w.stop && `${w.stop} ${w.ds >= 0 ? '+' : '−'}${Math.abs(w.ds)} m`].filter(Boolean).join(' · ');
    this.$('rvCard').innerHTML = `
<div><span class="kind">${f.kind}</span> <span class="dim">(${f.src}, ${this.cur + 1} / ${this.list.length})</span></div>
<div>${f.info}</div>
${f.marks ? `<div class="dim">${f.marks.map((m) => `<span style="color:${esc(m.color || '#fff')}">●</span> ${esc(m.label || '')}`).join(' · ')}</div>` : ''}
${f.pick ? `<div class="rvRow" style="padding:6px 0 0">${f.placeOption ? '' : '<button data-place="1">Place it on the map</button>'}<span class="dim" id="rvPlaced">${this._placedText(f)}</span></div>` : ''}
<div id="rvHeight"></div>
<div class="dim">${place || '—'}<br>s ${w.s ?? '?'} m, ${w.d ?? '?'} m from the track · x ${f.x.toFixed(1)}, y ${f.y.toFixed(1)} · ${L.lat.toFixed(6)}, ${L.lon.toFixed(6)}</div>
<div class="rvRow" style="padding:6px 0 0">${['Mapillary', 'Panoramax', 'Mapy.com', 'Street View'].map((k) => `<a class="btn" target="_blank" rel="noopener" href="${L[k]}">${k}</a>`).join('')}</div>
<div class="rvRow" style="padding:6px 0 0"><button data-go="-1">◀ prev</button><button data-go="1">next ▶</button><button data-copy="1">Copy link</button></div>
<div id="rvSrc">${this._srcHtml(f)}</div>
${this._verdictHtml(f)}`;
    this.heightChart = f.kind === 'trackheight' ? heightProfile(f, this.route, this.ground.profile) : null;
    if (this.heightChart) {
      this.$('rvHeight').innerHTML = this.heightChart.html;
      const svg = this.$('heightProfile');
      this.$('rvHeight').querySelectorAll('[data-height-series]').forEach((button) => button.addEventListener('click', () => {
        const visible = button.getAttribute('aria-pressed') !== 'true';
        button.setAttribute('aria-pressed', String(visible));
        svg.querySelectorAll(`[data-series="${button.dataset.heightSeries}"]`).forEach((item) => { item.style.display = visible ? '' : 'none'; });
      }));
      const preview = this.$('rvPreview');
      this.$('rvCard').querySelectorAll('button[data-v]').forEach((button) => {
        const show = () => {
          const answer = options(f)[+button.dataset.v];
          const reason = this.$('rvNote')?.value.trim() ? 'A note keeps this answer held for review.' :
            f.answer_explanations?.[answer] || (['other level (deck / under)', 'unsure'].includes(answer) ? 'This answer stays held for review.' : null);
          const hasPreview = !reason && !!f.answer_previews?.[answer];
          svg.querySelectorAll('[data-preview]').forEach((item) => { item.style.display = hasPreview && item.dataset.preview === answer ? '' : 'none'; });
          preview.textContent = reason ? `Held: ${reason}` : hasPreview ? 'Orange: imported profile at sampled points (DI keeps priority). Uncovered spans keep their existing rule.' : 'Preview unavailable: regenerate the findings file.';
        };
        button.addEventListener('mouseenter', show); button.addEventListener('focus', show);
        const clear = () => {
          if (button.matches(':focus, :hover')) return;
          preview.textContent = ''; svg.querySelectorAll('[data-preview]').forEach((item) => { item.style.display = 'none'; });
        };
        button.addEventListener('mouseleave', clear); button.addEventListener('blur', clear);
      });
      const pick = (e) => {
        const r = svg.getBoundingClientRect(), chart = this.heightChart;
        const px = (e.clientX - r.left) / r.width * chart.width;
        const s = chart.x0 + (px - chart.left) / (chart.right - chart.left) * (chart.x1 - chart.x0);
        return chart.points.reduce((a, b) => Math.abs(b.x - s) < Math.abs(a.x - s) ? b : a);
      };
      svg.addEventListener('pointermove', (e) => this._heightCursor(pick(e)));
      // a click (a tap) on the chart centres the camera on that point, keeping direction and zoom (#182)
      svg.addEventListener('click', (e) => {
        const p = pick(e);
        this._heightCursor(p);
        this.T = { x: p.xy[0], y: p.xy[1], z: p.game ?? this.ground.at(...p.xy) };
        this._render();
      });
    }
  }

  _heightCursor(p) {
    const chart = this.heightChart, cursor = this.$('heightCursor');
    if (!chart || !p || !cursor) return;
    const x = chart.left + (p.x - chart.x0) / (chart.x1 - chart.x0) * (chart.right - chart.left);
    cursor.setAttribute('x1', x); cursor.setAttribute('x2', x); cursor.setAttribute('visibility', 'visible');
    if (!this.heightMarker) {
      this.heightMarker = new THREE.Mesh(new THREE.SphereGeometry(1.2, 12, 8), new THREE.MeshBasicMaterial({ color: '#ffffff', depthTest: false }));
      this.heightMarker.renderOrder = 10; this.group.add(this.heightMarker);
    }
    this.heightMarker.position.set(p.xy[0], (p.game ?? this.ground.at(...p.xy)) + 1.5, -p.xy[1]);
    this.heightMarker.visible = true;
  }

  // ------------------------------------------------------------------ the source (data/lineN.zps.json, tools/zps_source.py)
  _loadSource() {
    if (this.src !== undefined) return;
    this.src = null;
    fetch(`data/line${this.data.line}.zps.json`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))).then((j) => {
      // per line: kind, level, height class, flat x,y,z; bounding boxes for the near layer
      this.src = j.lines.map((l) => { const p = l.slice(3); return { k: j.kinds[l[0]], l: l[1], h: l[2], p, box: bboxFlat(p) }; });
      this.nearAt = null;
      this._render();
      if (this.cur >= 0) { const e = this.$('rvSrc'); if (e) e.innerHTML = this._srcHtml(this.list[this.cur]); }
    }).catch((e) => { this.src = null; this._note(`no source lines for line ${this.data.line} (${e.message})`); });
  }

  // the source lines passing within 5 m of a place: kind, level, their height at the closest point and
  // the accuracy class (a straight kerb has its vertices far apart: the distance is to the segments)
  _srcHtml(f) {
    if (!this.layers.source) return '';
    if (!this.src) return '<div class="dim">source: loading…</div>';
    const R = 5, by = new Map();
    for (const s of this.src) {
      const [x0, y0, x1, y1] = s.box;
      if (f.x < x0 - R || f.x > x1 + R || f.y < y0 - R || f.y > y1 + R) continue;
      const p = s.p;
      for (let i = 0; i + 3 < p.length; i += 3) {
        const ax = p[i], ay = p[i + 1], dx = p[i + 3] - ax, dy = p[i + 4] - ay, L = dx * dx + dy * dy;
        const u = L ? Math.max(0, Math.min(1, ((f.x - ax) * dx + (f.y - ay) * dy) / L)) : 0;
        if (Math.hypot(ax + u * dx - f.x, ay + u * dy - f.y) > R) continue;
        const za = p[i + 2], zb = p[i + 5], k = `${s.k}|${s.l}|${s.h ?? '?'}`, e = by.get(k) || { s, z: [] };
        if (za !== null && zb !== null) e.z.push(za + u * (zb - za));
        by.set(k, e);
      }
    }
    if (!by.size) return '<div class="dim">source: no survey line within 5 m</div>';
    const rows = [...by.values()].sort((a, b) => a.s.l - b.s.l).map(({ s, z }) => {
      const zs = z.length ? `${Math.min(...z).toFixed(2)}${z.length > 1 ? `–${Math.max(...z).toFixed(2)}` : ''} m` : 'no height';
      return `<span style="color:${LEVEL_COLORS[Math.sign(s.l)]}">■</span> ${esc(s.k.replace(/_/g, ' '))} · level ${s.l} · ${zs} · class ${s.h ?? '?'}`;
    });
    return `<div class="dim" style="margin-top:4px">source within 5 m (height class: 3 good … 9 unknown):<br>${rows.join('<br>')}</div>`;
  }

  _verdictHtml(f) {
    const r = this._answer(f);
    const reasons = f.kind === 'trackheight' && f.answer_explanations ? f.answer_explanations : null;
    let explanation = '';
    if (reasons) {
      const lines = [];
      if (reasons['archive profile ok']) lines.push(`Archive answer stays held: ${esc(reasons['archive profile ok'])}.`);
      if (reasons['follows survey surface']) lines.push(`Survey answer unavailable: ${esc(reasons['follows survey surface'])}.`);
      lines.push('Notes, unsure and unspecified other levels stay held for review.');
      explanation = `<div class="dim">${lines.join('<br>')}</div>`;
    }
    const recorded = r && r === f.recorded;
    if (recorded) explanation += `<div class="dim">Answered in ${esc(r.source)} (${esc(r.date)}): “${esc(r.quote)}”</div>`;
    return `<div class="rvVerdict">${explanation}<textarea id="rvNote" rows="2" placeholder="note (optional, before or after the answer)">${esc(r?.note || '')}</textarea>
<div class="rvRow" style="padding:6px 0 0">${options(f).map((o, i) => `<button data-v="${i}" class="${r?.v === o ? 'on' : ''}">${i + 1} · ${esc(o)}</button>`).join('')}${r?.v && !recorded ? '<button data-v="" title="remove the answer">✕</button>' : ''}</div>
${f.kind === 'trackheight' ? '<div class="dim" id="rvPreview" aria-live="polite"></div>' : ''}<div class="dim" id="rvSync">${this._syncText()}</div></div>`;
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
    if (v !== null) for (let k = 1; k <= n && !next; k++) { const g = this.list[(this.cur + k) % n]; if (!this._answer(g)?.v) next = g; }
    this._redraw();
    if (next && this.list.includes(next)) this.select(this.list.indexOf(next));
  }

  // extra: a point placed on the map (px, py); kept with any later answer or note until the answer is
  // removed (✕) or the point placed again. (Kept only while the answer stayed the same, it was lost when
  // an answer button followed the placing: 10 of 10 on line 22's stop signs, 2026-11-04, #258)
  _record(f, v, note, extra = null) {
    const w = this.where(f.x, f.y), old = this.verdicts.get(fid(f));
    if (this.todo) this.kept.add(fid(f));
    const placed = extra || (v && old?.px !== undefined ? { px: old.px, py: old.py } : {});
    this.verdicts.set(fid(f), { v, note, src: f.src, kind: f.kind, x: +f.x.toFixed(2), y: +f.y.toFixed(2), mag: +f.mag.toFixed(2),
      info: f.info, street: w.street, stop: w.stop, s: w.s, at: location.search.match(/at=([^&]*)/)?.[1], ...placed, ...(f.id ? { id: f.id } : {}),
      ...(f.kind === 'trackheight' ? { decision_id: f.id, span_ids: f.decision.span_ids, span_sha256: f.span_sha256 } : {}) });
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
    } else if (this.list.length) this.select(Math.min(Math.max(this.cur, 0), this.list.length - 1));
    else { this.cur = -1; this.$('rvCard').innerHTML = '<div class="dim">nothing left in this list</div>'; }
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
      m.setColorAt(i, c.set(this._answer(f)?.v ? '#777' : HEIGHT_COLORS[f.status] || SRC_COLORS[f.src] || '#fff'));
    });
    m.count = this.list.length;
    m.renderOrder = 6;
    m.frustumCulled = false;
    this.group.add(m);
    this._applyLayers();
  }

  // the selected finding: a ring on the ground and, for an area finding, the area's outline
  _placedText(f) {
    const r = this._answer(f);
    return r?.px !== undefined ? `placed at x ${r.px}, y ${r.py} (${Math.hypot(r.px - f.x, r.py - f.y).toFixed(1)} m from the pin)` : '';
  }

  // a click on the map while placing: the point on the ground under it, saved as the answer (#258)
  _place(cx, cy) {
    const f = this.placing, r = this.canvas.getBoundingClientRect();
    this.placing = null;
    const ray = new THREE.Raycaster();
    this.camera.updateMatrixWorld();
    ray.setFromCamera(new THREE.Vector2(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1), this.camera);
    const hit = new THREE.Vector3();
    if (!ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -(f.z ?? 0)), hit)) { this._redraw(); return; }
    this._record(f, f.placeOption || 'placed on the map', this.$('rvNote')?.value.trim() || '', { px: +hit.x.toFixed(2), py: +(-hit.z).toFixed(2) });
    this._redraw();
    this._highlight(f);
    this._render();
  }

  _highlight(f) {
    if (this.hl) { this.group.remove(this.hl); this.hl.traverse((o) => o.geometry?.dispose()); }
    if (this.heightMarker) this.heightMarker.visible = false;
    this.hl = new THREE.Group();
    // the finding's other points, and a point placed as its answer: a thin pin and a ring each
    const r0 = this._answer(f);
    const marks = [...(f.marks || []), ...(r0?.px !== undefined ? [{ x: r0.px, y: r0.py, color: '#c070ff' }] : [])];
    for (const m of marks) {
      const z = this.ground.at(m.x, m.y), mat = new THREE.MeshBasicMaterial({ color: m.color || '#ffffff', depthTest: false, side: THREE.DoubleSide });
      const pin = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 4, 6).translate(0, 2, 0), mat);
      pin.position.set(m.x, z, -m.y);
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.7, 0.95, 32), mat);
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(m.x, z + 0.3, -m.y);
      pin.renderOrder = ring.renderOrder = 8;
      this.hl.add(pin, ring);
    }
    const ring = new THREE.Mesh(new THREE.RingGeometry(2.25, 2.75, 40), new THREE.MeshBasicMaterial({ color: HL, depthTest: false, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(f.x, f.z + 0.3, -f.y);
    ring.renderOrder = 7;
    this.hl.add(ring);
    if (f.kind === 'trackheight') for (const span of f.spans) {
      const pts = span.profile.map((p) => {
        const n = this.route.nearest(...p.xy);
        return [p.xy[0], p.xy[1], n && n.d < 8 ? this.ground.profile.height(n.s) : this.ground.at(...p.xy)];
      });
      if (pts.length < 2) continue;
      const conflict = span.review_flags?.some((x) => x === 'known_archive_disagreement' || x === 'conflicting_level_evidence');
      const o = new THREE.Mesh(band(pts, 1.2, 0.5), new THREE.MeshBasicMaterial({ color: HEIGHT_COLORS[conflict ? 'conflict' : span.status] || HEIGHT_COLORS.review, depthTest: false, side: THREE.DoubleSide }));
      o.renderOrder = 8; this.hl.add(o);
    }
    const a = f.c && this.dtm?.areas.find((a) => a.c === f.c && a.l === 0 && inRing(f.x, f.y, a.ring));
    if (a) {
      // (WebGL lines are 1 px: the outline is a 0.22 m band, a dark edge under it so it shows on any colour)
      for (const [w, col, dz, ro] of [[0.45, '#000000', 0.24, 7], [0.22, HL, 0.25, 8]]) {
        const o = new THREE.Mesh(band([...a.ring, a.ring[0]], w, dz), new THREE.MeshBasicMaterial({ color: col, depthTest: false, side: THREE.DoubleSide, transparent: true, opacity: col === HL ? 1 : 0.55 }));
        o.renderOrder = ro;
        this.hl.add(o);
      }
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
    const src = [], scl = [], dots = [], dcol = [];
    if (this.src) for (const s of this.src) {
      const [x0, y0, x1, y1] = s.box;
      if (x1 < tx - NEAR || x0 > tx + NEAR || y1 < ty - NEAR || y0 > ty + NEAR) continue;
      c.set(LEVEL_COLORS[Math.sign(s.l)]);
      const p = s.p, z = (i) => (p[i + 2] ?? this.ground.at(p[i], p[i + 1]));
      for (let i = 0; i < p.length; i += 3) {
        dots.push(p[i], z(i) + 0.03, -p[i + 1]);
        const m = p[i + 2] === null ? [1, 0.2, 0.2] : [c.r, c.g, c.b]; // (red: no height in the source)
        dcol.push(...m);
        if (i + 3 < p.length) { src.push(p[i], z(i) + 0.03, -p[i + 1], p[i + 3], z(i + 3) + 0.03, -p[i + 4]); scl.push(c.r, c.g, c.b, c.r, c.g, c.b); }
      }
    }
    const geo = (p, col) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3)); if (col) g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3)); return g; };
    this.classMesh = new THREE.Mesh(geo(tri, tcol), new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.5, depthWrite: false, side: THREE.DoubleSide }));
    this.kerbLines = new THREE.LineSegments(geo(kerb), new THREE.LineBasicMaterial({ color: '#ff3e6c', depthTest: false }));
    this.seamBars = new THREE.LineSegments(geo(seam, scol), new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false }));
    this.kerbLines.renderOrder = this.seamBars.renderOrder = 4;
    // the survey's triangles as drawn (the outline points and the 5 m splits between them)
    this.wire = new THREE.LineSegments(new THREE.WireframeGeometry(this.classMesh.geometry), new THREE.LineBasicMaterial({ color: '#101418', transparent: true, opacity: 0.55 }));
    // (the source at its own heights, seen through the surfaces: where it lies against them is the point)
    this.srcLines = new THREE.LineSegments(geo(src, scl), new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false }));
    this.srcDots = new THREE.Points(geo(dots, dcol), new THREE.PointsMaterial({ vertexColors: true, size: 5, sizeAttenuation: false, depthTest: false }));
    this.srcLines.renderOrder = this.srcDots.renderOrder = 5;
    this.near.add(this.classMesh, this.wire, this.kerbLines, this.seamBars, this.srcLines, this.srcDots);
    this.kerbCount = kerb.length / 6;
    this._applyLayers();
  }

  _applyLayers() {
    const L = this.layers;
    this.moved = performance.now();
    if (this.classMesh) this.classMesh.visible = L.classes;
    if (this.wire) this.wire.visible = L.wire;
    if (this.srcLines) this.srcLines.visible = this.srcDots.visible = L.source;
    if (this.cur >= 0 && this.$('rvSrc')) this.$('rvSrc').innerHTML = this._srcHtml(this.list[this.cur]);
    if (this.kerbLines) this.kerbLines.visible = L.kerbs;
    if (this.seamBars) this.seamBars.visible = L.seams;
    if (this.markers) this.markers.visible = L.findings;
    if (this.trackLine) this.trackLine.visible = L.track;
    if (this.orthoMesh) this.orthoMesh.visible = L.ortho;
    this.credit.style.display = L.ortho ? 'block' : 'none';
    if (this.sourceLines) this.sourceLines.visible = L.sources;
    this.$('rvTrackLegend').style.display = L.sources ? '' : 'none';
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
    this.moved = performance.now();
    if (!this.nearAt || Math.hypot(T.x - this.nearAt.x, T.y - this.nearAt.y) > NEAR / 3) this._near();
    this._ortho();
    this.dirty = true;
  }

  // ------------------------------------------------------------------ the orthophoto and the track sources (#201)
  // the image of the ORTHO_STEP cell around the target, draped over the ground: drawn over the world (the
  // survey surfaces and the track bed lie up to ~0.3 m over the terrain and would cut it), under the overlays
  _ortho() {
    if (!this.layers.ortho) return;
    const k = this.dist < ORTHO_NEAR ? 0.5 : 1, step = ORTHO_STEP * k, M = ORTHO_M * k;
    const cx = Math.round(this.T.x / step) * step, cy = Math.round(this.T.y / step) * step;
    if (this.orthoAt && this.orthoAt[0] === cx && this.orthoAt[1] === cy && this.orthoAt[2] === k) return;
    const at = (this.orthoAt = [cx, cy, k]), [ox, oy] = this.data.frame.origin, h = M / 2;
    const bbox = [ox + cx - h, oy + cy - h, ox + cx + h, oy + cy + h].map((v) => v.toFixed(1)).join(',');
    this.orthoUrl = `${ORTHO}/exportImage?bbox=${bbox}&bboxSR=5514&imageSR=5514&size=${ORTHO_PX},${ORTHO_PX}&format=jpg&f=image`;
    this._credit('loading…');
    new THREE.TextureLoader().setCrossOrigin('anonymous').load(this.orthoUrl, (tex) => {
      if (this.orthoAt !== at) { tex.dispose(); return; } // (the target moved on meanwhile)
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      const n = Math.round(M / ORTHO_GRID), G = M / n, pos = [], uv = [], idx = [], N = n + 1; // (75 m: 38 cells)
      // the ground smoothed over 10 m (5 × 5 vertices): its kerb steps and the track blend, seen close up
      // and off the camera's axis, shifted the photo's rows sideways by up to ~20 px
      const z0 = new Float32Array(N * N), z1 = new Float32Array(N * N), R = 2;
      for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) z0[j * N + i] = this.ground.at(cx - h + i * G, cy - h + j * G);
      for (const [src, dst, di, dj] of [[z0, z1, 1, 0], [z1, z0, 0, 1]]) for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
        let s = 0, c = 0;
        for (let k = -R; k <= R; k++) { const a = i + k * di, b = j + k * dj; if (a >= 0 && a < N && b >= 0 && b < N) { s += src[b * N + a]; c++; } }
        dst[j * N + i] = s / c;
      }
      for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) {
        const x = cx - h + i * G, y = cy - h + j * G;
        pos.push(x, z0[j * N + i] + 0.05, -y);
        uv.push(i / n, j / n);
        if (i && j) { const a = (j - 1) * (n + 1) + i - 1, b = a + n + 1; idx.push(a, a + 1, b, a + 1, b + 1, b); }
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.setIndex(idx);
      this._dropOrtho();
      // (opaque: three.js draws the opaque pass first, by renderOrder, so the overlay lines, which are opaque,
      // come after it; a transparent image would be drawn over all of them)
      this.orthoMesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: tex, depthTest: false, side: THREE.DoubleSide }));
      this.orthoMesh.renderOrder = 2;
      this.orthoMaps = { '00': tex }; // per look, made once per image
      this.orthoM = M;
      this.group.add(this.orthoMesh);
      this._credit(null);
      this._orthoMap();
      this._applyLayers();
    }, undefined, () => {
      if (this.orthoAt === at) this._credit('not available: the IPR service did not answer or refused the page. Switch the layer off and on to try again.');
    });
  }

  _dropOrtho() {
    if (!this.orthoMesh) return;
    this.group.remove(this.orthoMesh);
    this.orthoMesh.geometry.dispose(); this.orthoMesh.material.dispose();
    for (const t of Object.values(this.orthoMaps)) t.dispose();
    this.orthoMesh = null;
  }

  // the photo in the chosen look (orthoLook: ~0.2–0.5 s for a 1500 px image, once per image and look)
  _orthoMap() {
    if (!this.orthoMesh) return;
    const key = `${+this.look.contrast}${+this.look.lines}`;
    if (!this.orthoMaps[key]) {
      const t = new THREE.CanvasTexture(orthoLook(this.orthoMaps['00'].image, this.orthoM, this.look));
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = 4;
      this.orthoMaps[key] = t;
    }
    this.orthoMesh.material.map = this.orthoMaps[key];
    this.orthoMesh.material.needsUpdate = true;
    this.moved = performance.now();
  }

  _credit(state) {
    this.credit.textContent = state ? `${ORTHO_CREDIT}: ${state}` : ORTHO_CREDIT;
    this.credit.classList.toggle('err', !!state && state.startsWith('not'));
  }

  // the line's track centrelines as the build took them, coloured by source: 1 px lines (as thin as can
  // be seen at any zoom), to lay over the rails on the orthophoto
  _trackSources() {
    if (this.sourceLines) return;
    const pos = [], col = [], c = new THREE.Color();
    for (const t of this.data.tracks || []) {
      c.set(TRACK_COLORS[t.src] || '#ffffff');
      for (let i = 1; i < t.p.length; i++) {
        const [x0, y0] = t.p[i - 1], [x1, y1] = t.p[i];
        pos.push(x0, this.ground.at(x0, y0) + 0.3, -y0, x1, this.ground.at(x1, y1) + 0.3, -y1);
        col.push(c.r, c.g, c.b, c.r, c.g, c.b);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    this.sourceLines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, depthTest: false }));
    this.sourceLines.renderOrder = 6;
    this.group.add(this.sourceLines);
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
      // (a finger has no second button, and the map must move: one finger pans, two turn)
      if (ptr.size === 1) { mode = e.pointerType === 'mouse' && e.button === 0 && !e.shiftKey ? 'turn' : 'pan'; tap = { x: e.clientX, y: e.clientY, t: performance.now() }; }
      else { tap = null; two = pair(); }
    });
    cv.addEventListener('pointermove', (e) => {
      const p = ptr.get(e.pointerId);
      if (!p) { if (e.pointerType === 'mouse' && !ptr.size) this._hover(e.clientX, e.clientY); return; }
      if (this.tip) this.tip.style.display = 'none';
      const dx = e.clientX - p.x, dy = e.clientY - p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (tap && Math.hypot(e.clientX - tap.x, e.clientY - tap.y) > 8) tap = null;
      if (ptr.size >= 2 && two) {
        const q = pair();
        this._zoom(two.d / Math.max(1, q.d));
        // (the map turns with the fingers: a clockwise twist turns the view, i.e. the heading, anticlockwise)
        this._turn(two.ang - q.ang, (q.my - two.my) * 0.004);
        two = q;
      } else if (mode === 'turn') this._turn(dx * 0.006, dy * 0.005); // (a drag to the right looks to the right, as src/inspect.js)
      else this._pan(dx, dy);
      this._render();
    });
    const up = (e) => {
      ptr.delete(e.pointerId);
      if (ptr.size < 2) two = null;
      if (ptr.size === 1) { tap = null; mode = 'pan'; } // (from two fingers back to one: panning on)
      if (tap && ptr.size === 0 && performance.now() - tap.t < 500) this._pick(e.clientX, e.clientY, e.pointerType !== 'mouse');
      if (!ptr.size) tap = null;
    };
    cv.addEventListener('pointerup', up);
    cv.addEventListener('pointerleave', () => { if (this.tip) this.tip.style.display = 'none'; });
    cv.addEventListener('pointercancel', up);
    cv.addEventListener('wheel', (e) => { e.preventDefault(); this._zoom(Math.exp(e.deltaY * 0.0012)); this._render(); }, { passive: false });
    window.addEventListener('keydown', (e) => {
      if (e.target.closest?.('select, input, textarea')) return;
      const k = e.key.toLowerCase();
      const o = this.cur >= 0 && /^[1-9]$/.test(k) && options(this.list[this.cur])[+k - 1];
      if (o && o === this.list[this.cur].placeOption) { this.$('rvCard').querySelector(`button[data-v="${+k - 1}"]`)?.click(); return; }
      if (o) { this.verdict(o); return; }
      if (k === 'n') this.select(Math.min(this.list.length - 1, this.cur + 1));
      else if (k === 'b') this.select(Math.max(0, this.cur - 1));
      else if (k === '+' || k === '=') { this._zoom(0.8); this._render(); }
      else if (k === '-') { this._zoom(1.25); this._render(); }
      else if (('wasdqerf'.includes(k) && k.length === 1) || k.startsWith('arrow')) this.held.add(k);
    });
    window.addEventListener('keyup', (e) => this.held.delete(e.key.toLowerCase()));
    window.addEventListener('blur', () => this.held.clear());
    window.addEventListener('resize', () => this._render());
  }

  // a tap or click: the nearest marker on the screen within 28 px
  // the pin under a point of the screen: the nearest to the pin as drawn, foot to head (close up a pin is
  // 100 px tall: its middle alone missed a click on its head), within R px; among pins as near, the front one
  _hit(cx, cy, R) {
    const r = this.canvas.getBoundingClientRect(), a = new THREE.Vector3(), b = new THREE.Vector3();
    this.camera.updateMatrixWorld(); // (moved since the last frame: its matrices follow at the next draw)
    let best = -1, bd = R, bz = 1;
    const n = Math.min(this.list.length, 4000);
    for (let i = 0; i < n; i++) {
      const f = this.list[i];
      a.set(f.x, f.z, -f.y).project(this.camera);
      b.set(f.x, f.z + 7, -f.y).project(this.camera);
      if (a.z > 1 || b.z > 1) continue;
      const ax = r.left + ((a.x + 1) / 2) * r.width, ay = r.top + ((1 - a.y) / 2) * r.height;
      const dx = r.left + ((b.x + 1) / 2) * r.width - ax, dy = r.top + ((1 - b.y) / 2) * r.height - ay, L = dx * dx + dy * dy;
      const u = L ? Math.max(0, Math.min(1, ((cx - ax) * dx + (cy - ay) * dy) / L)) : 0;
      const d = Math.hypot(ax + u * dx - cx, ay + u * dy - cy);
      if (d < bd - 3 || (d < bd + 3 && a.z < bz)) { bd = Math.min(bd, d); bz = a.z; best = i; }
    }
    return best;
  }

  // a tap or click: the pin there (a finger is wider than a mouse)
  _pick(cx, cy, touch) {
    if (this.placing) { this._place(cx, cy); return; }
    const i = this._hit(cx, cy, touch ? 34 : 18);
    if (i >= 0) this.select(i);
  }

  // the mouse over a pin: a pointer and its kind, so a neighbouring finding is one click away
  _hover(cx, cy) {
    if (this.heightChart) {
      const rect = this.canvas.getBoundingClientRect(), v = new THREE.Vector3();
      let best = null, distance = 22;
      for (const p of this.heightChart.points) {
        v.set(p.xy[0], p.game ?? this.ground.at(...p.xy), -p.xy[1]).project(this.camera);
        const d = Math.hypot(rect.left + (v.x + 1) * rect.width / 2 - cx, rect.top + (1 - v.y) * rect.height / 2 - cy);
        if (v.z < 1 && d < distance) { distance = d; best = p; }
      }
      if (best) this._heightCursor(best);
    }
    const i = this._hit(cx, cy, 18), f = this.list[i];
    this.canvas.style.cursor = f ? 'pointer' : '';
    let tip = this.tip;
    if (!tip) { tip = this.tip = document.createElement('div'); tip.className = 'rvTip'; document.body.appendChild(tip); }
    tip.style.display = f ? 'block' : 'none';
    if (!f) return;
    const r = this._answer(f);
    tip.innerHTML = `<b>${esc(f.kind)}</b> · ${f.mag.toFixed(0)}${r?.v ? ` · ✓ ${esc(r.v)}` : ''}`;
    tip.style.left = `${cx + 14}px`;
    tip.style.top = `${cy + 10}px`;
  }

  // main.js draws a resting review 4 times a second (#149): nothing moved for 1 s, no key held
  resting() { return !this.held.size && performance.now() - (this.moved || 0) > 1000; }

  // every frame: held keys, and the address once the camera rests
  update(dt) {
    const h = this.held;
    if (h.size) {
      const v = (this.canvas.clientHeight * 0.8) * dt;
      if (h.has('w')) this._pan(0, v);
      if (h.has('s')) this._pan(0, -v);
      if (h.has('a')) this._pan(v, 0);
      if (h.has('d')) this._pan(-v, 0);
      if (h.has('q') || h.has('arrowleft')) this._turn(-1.2 * dt, 0);
      if (h.has('e') || h.has('arrowright')) this._turn(1.2 * dt, 0);
      if (h.has('arrowup')) this._turn(0, -0.8 * dt);
      if (h.has('arrowdown')) this._turn(0, 0.8 * dt);
      if (h.has('r')) this._zoom(Math.exp(1.5 * dt)); // (up and down: this camera hangs from its target)
      if (h.has('f')) this._zoom(Math.exp(-1.5 * dt));
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

// a flat band along a polyline of [x, y, z] (game frame), w wide, dz over it, as three.js geometry
function band(pts, w, dz) {
  const pos = [], idx = [];
  pts.forEach((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1, nx = (-dy / L) * w / 2, ny = (dx / L) * w / 2;
    pos.push(p[0] + nx, p[2] + dz, -(p[1] + ny), p[0] - nx, p[2] + dz, -(p[1] - ny));
    if (i) idx.push(2 * i - 2, 2 * i - 1, 2 * i, 2 * i - 1, 2 * i + 1, 2 * i);
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setIndex(idx);
  return g;
}

// The orthophoto made easier to read (#201), as a canvas from the loaded image (metres: the image's width):
// - contrast: each pixel's brightness against its 1 m surround (mean and spread), the colour kept, after
//   a 3.5 cm smoothing of the JPEG's grain: the faint rails in the pavement and the kerbs stand out over a
//   box of sun and shade alike;
// - lines: a pixel darker than its 0.2 m surround (rails, joints, gaps) drawn cyan, scaled by the 99.5th
//   percentile of the image.
// Picked on line 17 (Křižovnická, a 12-way junction, Výstaviště, Belárie) against a global stretch,
// unsharp masking, a high-pass and Sobel edges: edges outlined the paving's texture and gave each rail two
// lines; a rail is a thin dark line, not a step.
export function orthoLook(img, metres, { contrast = false, lines = false } = {}) {
  const w = img.naturalWidth || img.width, h = img.naturalHeight || img.height, n = w * h, pm = w / metres;
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  const id = ctx.getImageData(0, 0, w, h), px = id.data;
  const ch = [0, 1, 2].map((c) => { const a = new Float32Array(n); for (let i = 0; i < n; i++) a[i] = px[4 * i + c] / 255; return a; });
  const [R, G, B] = ch.map((a) => gauss(a, w, h, 0.035 * pm));
  const L = new Float32Array(n);
  for (let i = 0; i < n; i++) L[i] = 0.299 * R[i] + 0.587 * G[i] + 0.114 * B[i];
  // the 1 m surround's mean and spread
  const k = new Float32Array(n).fill(1), sq = new Float32Array(n);
  for (let i = 0; i < n; i++) sq[i] = L[i] * L[i];
  const m = gauss(L, w, h, pm), sd = gauss(sq, w, h, pm);
  for (let i = 0; i < n; i++) sd[i] = Math.sqrt(Math.max(sd[i] - m[i] * m[i], 1e-4));
  if (contrast) for (let i = 0; i < n; i++) k[i] = 1 / (1 + Math.exp(-0.9 * (L[i] - m[i]) / (sd[i] + 0.02))) / Math.max(L[i], 1e-3);
  let r = null;
  if (lines) {
    // how much darker than the 0.2 m around, in the 1 m surround's spread: a faint rail in even paving
    // counts as much as a dark joint in busy paving (the image's own top values, set by shadows and car
    // edges over 75 m, left the rails under the threshold, in pieces); under half a spread is the grain
    // (more smoothing first, 5 cm, faded the rails and kept the dots: those are real dark specks)
    const s = gauss(L, w, h, 0.2 * pm);
    r = new Float32Array(n);
    for (let i = 0; i < n; i++) r[i] = Math.max(0, Math.min(1, ((s[i] - L[i]) / (sd[i] + 0.01) - 0.5) / 1.5)) ** 0.6;
  }
  const cyan = [0.1, 0.9, 1.0];
  for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) {
    let v = Math.min(1, [R, G, B][c][i] * k[i]);
    if (r) v = v * 0.8 * (1 - r[i]) + cyan[c] * r[i]; // (the photo a little darker under the lines)
    px[4 * i + c] = v * 255;
  }
  ctx.putImageData(id, 0, 0);
  return cv;
}

// a gaussian of sigma s px, as three box blurs (each a running sum along rows, then columns)
function gauss(a, w, h, s) {
  const r = Math.floor((Math.sqrt(4 * s * s + 1) - 1) / 2 + 0.5); // (3 boxes of 2r+1: variance 3·((2r+1)²−1)/12 ≈ s²)
  if (r < 1) return s < 0.3 ? a : tap3(a, w, h, Math.min(1 / 3, (s * s) / 2)); // (under ~1.2 px: [q, 1−2q, q], variance 2q = s²)
  let x = Float32Array.from(a), y = new Float32Array(a.length);
  for (let pass = 0; pass < 3; pass++) {
    box(x, y, w, h, r, 1, w); // rows
    box(y, x, h, w, r, w, 1); // columns
  }
  return x;
}

function tap3(a, w, h, q) {
  const x = new Float32Array(a.length), y = new Float32Array(a.length), p = 1 - 2 * q;
  for (let j = 0; j < h; j++) for (let i = 0, o = j * w; i < w; i++) x[o + i] = p * a[o + i] + q * (a[o + Math.max(0, i - 1)] + a[o + Math.min(w - 1, i + 1)]);
  for (let j = 0; j < h; j++) for (let i = 0, o = j * w; i < w; i++) y[o + i] = p * x[o + i] + q * (x[Math.max(0, j - 1) * w + i] + x[Math.min(h - 1, j + 1) * w + i]);
  return y;
}

// a box of 2r+1 along lines of len samples (stride step), lines `count` apart by `next`; edges clamped
function box(src, dst, len, count, r, step, next) {
  const d = 2 * r + 1;
  for (let l = 0; l < count; l++) {
    const o = l * next;
    let sum = src[o] * (r + 1);
    for (let i = 1; i <= r; i++) sum += src[o + Math.min(i, len - 1) * step];
    for (let i = 0; i < len; i++) {
      dst[o + i * step] = sum / d;
      sum += src[o + Math.min(i + r + 1, len - 1) * step] - src[o + Math.max(i - r, 0) * step];
    }
  }
}

function bboxFlat(p) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < p.length; i += 3) { if (p[i] < x0) x0 = p[i]; if (p[i] > x1) x1 = p[i]; if (p[i + 1] < y0) y0 = p[i + 1]; if (p[i + 1] > y1) y1 = p[i + 1]; }
  return [x0, y0, x1, y1];
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
