// The speed signs of D 1/2 § 49.13-22, their faces and where they stand (#211). Pure: no Three.js, no game state, so a
// page can draw them and a test can read the rules. docs/decisions/2026-11-07-speed-limits-and-signs.md says why.
//
// Sizes in metres. The speed signs have no stated size: 200x300 mm with a 30 mm frame is their family's, the U and Z
// plates' (docs/research/prazsketramvaje/signals.md), which D 1/2's drawings match. Heights over width of the triangle
// and the zone plate are read off the drawings (p. 54, 56).
export const PLATE = { w: 0.2, h: 0.3, frame: 0.03 };
const YELLOW = '#f6c500';      // the photos' reflective orange-yellow (D 1/2 draws pure yellow)
const BLACK = '#111';
const WHITE = '#f4f4f0';
const EDGE = '#555';           // the plate's thin edge (black in D 1/2's drawings, weathered grey in the photos)
const BACKING = 0.04;          // m: the yellow reflective frame of a backing board (§ 49.32), not stated: the frame's width
const STRIP = 0.05;            // m: the white strip under the panel for an arrow or a car type (arrow 150x25 mm, website)

export const KINDS = ['restriction', 'slow', 'end', 'warning', 'point', 'higher', 'higherEnd', 'smallRadius', 'switchV',
  'zone', 'zoneEnd', 'climb', 'climbEnd', 'descent', 'descentEnd'];

// the face's size in metres
export function signSize(sign) {
  let w = PLATE.w, h = PLATE.h;
  if (sign.kind === 'warning') { w = 0.4; h = 0.3; }                    // drawn 220 by 165
  else if (sign.kind === 'point') h = PLATE.h + 0.055;                  // a triangle plate under it (28 of 153, p. 54)
  else if (sign.kind === 'zone' || sign.kind === 'zoneEnd') h = PLATE.h * 1.04;   // drawn 111 by 171
  else if (['climb', 'climbEnd', 'descent', 'descentEnd'].includes(sign.kind)) { w = 0.3; h = 0.33; }  // drawn 163 by 181
  if (sign.arrow || sign.carType) h += STRIP;
  if (sign.backing) { w += 2 * BACKING; h += 2 * BACKING; }
  return { w: Math.round(w * 1000) / 1000, h: Math.round(h * 1000) / 1000 };
}

// text filling a box: the drawings' heavy figures are condensed to the panel's width
function fit(g, text, x, y, w, h, { color = BLACK, family = '"Arial Narrow", Arial, sans-serif', weight = 'bold' } = {}) {
  g.save();
  g.fillStyle = color;
  g.textAlign = 'center'; g.textBaseline = 'alphabetic';
  g.font = `${weight} 100px ${family}`;
  const m = g.measureText(text);
  const top = m.actualBoundingBoxAscent ?? 72, bottom = m.actualBoundingBoxDescent ?? 0, wide = m.width || 60;
  const sx = w / wide, sy = h / (top + bottom);
  g.translate(x + w / 2, y + h);
  g.scale(sx, sy);
  g.fillText(text, 0, -bottom);
  g.restore();
}

function diagonal(g, x0, y0, x1, y1, width, color) {
  g.save();
  g.beginPath(); g.rect(x0, y0, x1 - x0, y1 - y0); g.clip();
  g.strokeStyle = color; g.lineWidth = width;
  g.beginPath(); g.moveTo(x0, y1); g.lineTo(x1, y0); g.stroke();
  g.restore();
}

function arrow(g, x, y, w, h, dir) {
  const left = dir === 'left', a = left ? x : x + w, b = left ? x + w : x, head = (left ? 1 : -1) * h * 1.2, mid = y + h / 2;
  g.save();
  g.strokeStyle = BLACK; g.fillStyle = BLACK; g.lineWidth = h * 0.3;
  g.beginPath(); g.moveTo(b, mid); g.lineTo(a + head * 0.6, mid); g.stroke();
  g.beginPath(); g.moveTo(a, mid); g.lineTo(a + head, mid - h / 2); g.lineTo(a + head, mid + h / 2); g.closePath(); g.fill();
  g.restore();
}

// the plate with its frame, in the box x,y,w,h (px); returns the panel's box
function plate(g, x, y, w, h, panel, u) {
  g.fillStyle = WHITE; g.fillRect(x, y, w, h);
  g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y, w, h);
  const f = PLATE.frame * u;
  g.fillStyle = panel; g.fillRect(x + f, y + f, w - 2 * f, h - 2 * f);
  return { x: x + f, y: y + f, w: w - 2 * f, h: h - 2 * f };
}

function number(g, p, text, color = BLACK) {
  const w = p.w * 0.84, h = Math.min(p.h * 0.62, w * 1.25);
  fit(g, text, p.x + (p.w - w) / 2, p.y + (p.h - h) / 2, w, h, { color });
}

function triangle(g, x, y, w, h, digit, u) {
  const path = (m) => {
    g.beginPath();
    g.moveTo(x + m * 1.73, y + m); g.lineTo(x + w - m * 1.73, y + m); g.lineTo(x + w / 2, y + h - m * 2); g.closePath();
  };
  g.fillStyle = WHITE; path(0); g.fill();
  g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); path(0); g.stroke();
  g.fillStyle = YELLOW; path(0.018 * u); g.fill();
  if (digit !== undefined && digit !== null) fit(g, String(digit), x + w * 0.38, y + h * 0.1, w * 0.24, h * 0.56);
}

function pentagon(g, x, y, w, h, up, u) {
  g.fillStyle = '#bdbdbd'; g.fillRect(x, y, w, h);
  g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y, w, h);
  const m = 0.016 * u, s = h * 0.42;
  g.fillStyle = '#fff';
  g.beginPath();
  if (up) {
    g.moveTo(x + w / 2, y + m); g.lineTo(x + w - m, y + s); g.lineTo(x + w - m, y + h - m); g.lineTo(x + m, y + h - m); g.lineTo(x + m, y + s);
  } else {
    g.moveTo(x + m, y + m); g.lineTo(x + w - m, y + m); g.lineTo(x + w - m, y + h - s); g.lineTo(x + w / 2, y + h - m); g.lineTo(x + m, y + h - s);
  }
  g.closePath(); g.fill();
}

// Draw a sign's face on a 2D context, filling W x H px (signSize's proportions).
export function drawSign(g, sign, W, H) {
  const size = signSize(sign), u = W / size.w;
  let x = 0, y = 0, w = W, h = H;
  if (sign.backing) {
    g.fillStyle = YELLOW; g.fillRect(0, 0, W, H);
    x = y = BACKING * u; w = W - 2 * x; h = H - 2 * y;
  }
  const strip = sign.arrow || sign.carType ? STRIP * u : 0;
  const k = sign.kind;
  if (k === 'warning') { triangle(g, x, y, w, h, sign.digit, u); return; }
  if (k === 'climb' || k === 'climbEnd' || k === 'descent' || k === 'descentEnd') {
    const up = k.startsWith('climb');
    pentagon(g, x, y, w, h, up, u);
    fit(g, String(sign.permille), x + w * 0.31, y + h * (up ? 0.42 : 0.36), w * 0.38, h * 0.25, { color: '#e01010', family: '"Times New Roman", Times, serif' });
    if (k.endsWith('End')) diagonal(g, x, y, x + w, y + h, 0.016 * u, BLACK);
    return;
  }
  if (k === 'zone' || k === 'zoneEnd') {
    const f = PLATE.frame * u, head = h * 0.25, end = k === 'zoneEnd';
    g.fillStyle = WHITE; g.fillRect(x, y, w, h);
    g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y, w, h);
    const grey = end ? '#aaa' : BLACK;
    fit(g, 'Z Ó N A', x + w * 0.2, y + h * 0.035, w * 0.6, h * 0.075, { color: grey });
    fit(g, sign.hours || '22 - 6 h', x + w * 0.22, y + h * 0.135, w * 0.56, h * 0.075, { color: grey });
    const p = { x: x + f, y: y + head, w: w - 2 * f, h: h - head - f };
    g.fillStyle = end ? WHITE : YELLOW; g.fillRect(p.x, p.y, p.w, p.h);
    g.strokeStyle = BLACK; g.lineWidth = Math.max(1, 0.003 * u); g.strokeRect(p.x, p.y, p.w, p.h);
    const nw = p.w * 0.5, nh = p.h * 0.32;
    fit(g, String(sign.v), p.x + (p.w - nw) / 2, p.y + (p.h - nh) / 2, nw, nh, { color: end ? '#aaa' : BLACK, family: 'Arial, sans-serif' });
    if (end) diagonal(g, x, y, x + w, y + h, 0.014 * u, BLACK);
    return;
  }
  const point = k === 'point' ? 0.055 * u : 0;
  const body = h - strip - point;
  const panel = k === 'higher' || k === 'higherEnd' ? BLACK : YELLOW;
  const p = plate(g, x, y, w, body + (strip ? 0 : 0), panel, u);
  if (strip) {
    g.fillStyle = WHITE; g.fillRect(x, y + body - PLATE.frame * u, w, strip + PLATE.frame * u);
    g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y, w, body + strip);
    const sy = y + body - PLATE.frame * u + (strip + PLATE.frame * u - 0.025 * u) / 2;
    if (sign.arrow) arrow(g, x + (w - 0.15 * u) / 2, sy, 0.15 * u, 0.025 * u, sign.arrow);
    else fit(g, sign.carType, x + w * 0.25, sy - 0.004 * u, w * 0.5, 0.033 * u);
  }
  if (k === 'restriction' || k === 'point') number(g, p, String(sign.v));
  else if (k === 'higher') number(g, p, String(sign.v), '#fff');
  else if (k === 'smallRadius') {
    const nh = p.h * 0.45, nw = p.w * 0.46;
    fit(g, 'r', p.x + (p.w - nw) / 2, p.y + p.h * 0.14, nw, nh, { family: 'Arial, sans-serif' });
    const a = sign.curve || 'right';
    arrow(g, p.x + p.w * 0.14, p.y + p.h * 0.72, p.w * 0.72, 0.02 * u, a);
  } else if (k === 'switchV') {
    g.fillStyle = BLACK;
    const t = p.w * 0.26;
    g.beginPath();
    g.moveTo(p.x, p.y); g.lineTo(p.x + t, p.y); g.lineTo(p.x + p.w / 2, p.y + p.h * 0.72); g.lineTo(p.x + p.w - t, p.y); g.lineTo(p.x + p.w, p.y);
    g.lineTo(p.x + p.w / 2 + t * 0.42, p.y + p.h); g.lineTo(p.x + p.w / 2 - t * 0.42, p.y + p.h); g.closePath(); g.fill();
  } else if (k === 'end' || k === 'higherEnd') {
    diagonal(g, x, y, x + w, y + body, 0.024 * u, k === 'end' ? BLACK : WHITE);
  }
  if (point) {
    const ty = y + body + 0.004 * u, th = point - 0.008 * u;
    g.fillStyle = WHITE; g.fillRect(x, y + body, w, point);
    g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y + body, w, point);
    g.fillStyle = BLACK;
    g.beginPath(); g.moveTo(x + w * 0.06, ty); g.lineTo(x + w * 0.94, ty); g.lineTo(x + w / 2, ty + th); g.closePath(); g.fill();
  }
}

// ------------------------------------------------------------------ the speed switch's LED panels (D 1/2 § 46)
// Black boxes with white LED dots (the switch signal, the number) or yellow bars (the call signal).
const SEGMENTS = { 0: 'abcdef', 1: 'bc', 2: 'abged', 3: 'abgcd', 4: 'fgbc', 5: 'afgcd', 6: 'afgedc', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg' };

function dots(g, x0, y0, x1, y1, r, step, color) {
  const n = Math.max(1, Math.round(Math.hypot(x1 - x0, y1 - y0) / step));
  g.fillStyle = color;
  for (let i = 0; i <= n; i++) {
    g.beginPath(); g.arc(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, r, 0, Math.PI * 2); g.fill();
  }
}

// `panel`: {kind: 'chevron', dir: 'straight'|'left'|'right'|null, dark} | {kind: 'number', v, dark} | {kind: 'call', dir, dark}
// | {kind: 'entry', state: 'go'|'stop'|'dark'} | {kind: 'undetermined'} (a dot, § 46.5). W x H px.
export function drawLedPanel(g, panel, W, H) {
  const k = panel.kind;
  g.fillStyle = '#0a0a0a';
  if (k === 'entry') {
    g.fillRect(0, 0, W, H);
    g.fillStyle = '#050505'; g.beginPath(); g.arc(W / 2, H / 2, Math.min(W, H) * 0.48, 0, Math.PI * 2); g.fill();
    if (panel.state === 'dark') return;
    const r = Math.min(W, H) * 0.42, t = r * 0.25, go = panel.state === 'go';
    g.fillStyle = '#fff';
    if (go) g.fillRect(W / 2 - t, H / 2 - r, 2 * t, 2 * r); else g.fillRect(W / 2 - r, H / 2 - t, 2 * r, 2 * t);
    return;
  }
  g.fillRect(0, 0, W, H);
  if (panel.dark) return;
  const r = W * 0.012, step = W * 0.034, on = '#fffef0';
  if (k === 'chevron') {
    // a filled arrow with a notch at its base, in LED dots (D 1/2 p. 46; the photo on the speed-sign page)
    const shape = (u, v) => {
      const [a, b] = panel.dir === 'right' ? [v, 1 - u] : panel.dir === 'left' ? [1 - v, u] : [u, v];   // to the "up" arrow
      if (b < 0.12 || b > 0.88) return false;
      const half = (b - 0.12) * 0.42, notch = Math.max(0, (b - 0.62) * 0.36);
      return Math.abs(a - 0.5) <= half && Math.abs(a - 0.5) >= notch;
    };
    g.fillStyle = on;
    for (let y = step / 2; y < H; y += step) for (let x = step / 2; x < W; x += step) {
      if (shape(x / W, y / H)) { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
    }
  } else if (k === 'undetermined') {
    for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) if (i * i + j * j <= 5) { g.fillStyle = on; g.beginPath(); g.arc(W / 2 + i * step * 0.8, H / 2 + j * step * 0.8, r, 0, Math.PI * 2); g.fill(); }
  } else if (k === 'number') {
    const digits = String(panel.v).split(''), dw = W * 0.34, dh = H * 0.72, gap = W * 0.08, x0 = (W - digits.length * dw - (digits.length - 1) * gap) / 2, y0 = (H - dh) / 2;
    digits.forEach((d, i) => {
      const x = x0 + i * (dw + gap), y = y0, m = y + dh / 2, e = x + dw, b = y + dh;
      const seg = { a: [x, y, e, y], b: [e, y, e, m], c: [e, m, e, b], d: [x, b, e, b], e: [x, m, x, b], f: [x, y, x, m], g: [x, m, e, m] };
      for (const s of SEGMENTS[d] || '') dots(g, ...seg[s], r, step * 0.7, on);
    });
  } else if (k === 'call') {
    const lean = { left: [[0.28, 0.14], [0.5, 0.86]], straight: [[0.5, 0.14], [0.5, 0.86]], right: [[0.72, 0.14], [0.5, 0.86]] };
    for (const [dir, [[a, b], [c, d]]] of Object.entries(lean)) {
      const lit = panel.dir === dir, wide = W * 0.03;
      for (const o of [-wide, 0, wide]) dots(g, a * W + o, b * H, c * W + o, d * H, r * 1.2, step, lit ? '#ffd21a' : '#2a2a22');
    }
  }
}

// ------------------------------------------------------------------ where the signs stand
const GENERAL = 50;              // km/h: `max-speed`
const MIN_STRETCH = 25;          // m: the game's old rule, a change shorter than this gets no sign (src/game.js _initSigns)
const NEAR_TRACKWORK = 15;       // m: a 15 km/h piece this near a switch or crossing is that rule's own: D 1/2 gives it no sign
const WARN_DROP = 30;            // km/h: § 49.15, the warning board stands where the speed falls by this or more
const SERVICE_BRAKE = 0.7;       // m/s²: the braking distance (D 1/2 § 2.8, the same rate as Game.nextLimitChange)
const NEAR_SIGN = 35;            // m: a sign that would stand this close after the last one gives way (src/game.js _initSigns)

// the braking distance from v km/h, whole 5 m
export function brakingDistance(v) {
  const ms = v / 3.6;
  return Math.ceil(ms * ms / (2 * SERVICE_BRAKE) / 5) * 5;
}

// Runs of equal posted speed (0 = none: the general 50) as [{from, to, v}], step m apart.
export function postedRuns(posted, step = 5) {
  const out = [];
  for (let i = 0, j; i < posted.length; i = j) {
    for (j = i; j < posted.length && posted[j] === posted[i];) j++;
    out.push({ from: i * step, to: j * step, v: posted[i] || GENERAL });
  }
  // a piece shorter than MIN_STRETCH takes the speed around it unless it is lower (a sign must be there to obey it)
  return out;
}

// The signs a line's route takes. `posted`: km/h per step (data.speed.osm); `top`: the car's highest speed; `trackwork`:
// route positions of its switches and crossings; `smallRadius`: [{from, to}] curves under 25 m; `zones`: [{from, to, v, hours}].
// A rule of a stretch, with its places; the kinds with no list of places yet (slow, point, switchV) are not planned.
export function planSigns({ posted, step = 5, top = 65, trackwork = [], smallRadius = [], zones = [], gradients = [] }) {
  const out = [];
  const onTrackwork = (r) => trackwork.some((s) => s > r.from - NEAR_TRACKWORK && s < r.to + NEAR_TRACKWORK);
  // signed stretches: under 50 outside the switches' and crossings' own pieces, over 50 always
  const runs = [];
  for (const r of postedRuns(posted, step)) {
    const v = Math.min(r.v, top);
    const own = v === 15 && onTrackwork(r);
    const short = r.to - r.from < MIN_STRETCH && v !== GENERAL;
    const speed = own || short ? null : v;
    const last = runs[runs.length - 1];
    if (last && (speed === null || speed === last.v)) { last.to = r.to; continue; }
    runs.push({ from: r.from, to: r.to, v: speed ?? GENERAL });
  }
  for (let i = 1; i < runs.length; i++) {
    const a = runs[i - 1], b = runs[i];
    if (b.v === a.v) continue;
    if (b.v > GENERAL) out.push({ kind: 'higher', v: b.v, s: b.from });
    else if (b.v < GENERAL) {
      out.push({ kind: 'restriction', v: b.v, s: b.from });
      if (a.v - b.v >= WARN_DROP && b.from > brakingDistance(a.v)) out.push({ kind: 'warning', digit: Math.floor(b.v / 10), s: b.from - brakingDistance(a.v) });
    } else out.push({ kind: a.v > GENERAL ? 'higherEnd' : 'end', s: b.from });
  }
  for (const c of smallRadius) {
    if (trackwork.some((s) => s > c.from - NEAR_TRACKWORK && s < c.to + NEAR_TRACKWORK)) continue;
    out.push({ kind: 'smallRadius', s: c.from, curve: c.side || 'right', v: 15 });
  }
  for (const z of zones) {
    out.push({ kind: 'zone', v: z.v, hours: z.hours || '22 - 6 h', s: z.from });
    out.push({ kind: 'zoneEnd', v: z.v, hours: z.hours || '22 - 6 h', s: z.to });
  }
  for (const d of gradients) {
    out.push({ kind: d.up ? 'climb' : 'descent', permille: d.permille, s: d.from });
    out.push({ kind: d.up ? 'climbEnd' : 'descentEnd', permille: d.permille, s: d.to });
  }
  out.sort((a, b) => a.s - b.s);
  // a board crowding the one before it gives way, unless it is the restriction itself (it is the rule)
  const kept = [];
  for (const g of out) {
    const prev = kept[kept.length - 1];
    if (prev && g.s - prev.s < NEAR_SIGN && (g.kind === 'warning' || prev.kind === 'warning')) { if (g.kind !== 'warning') { kept.pop(); kept.push(g); } continue; }
    kept.push(g);
  }
  return kept;
}
