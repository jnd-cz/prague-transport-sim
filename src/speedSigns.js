// The speed signs of D 1/2 § 49.13-22, their faces and where they stand (#211). Pure: no Three.js, no game state, so a
// page can draw them and a test can read the rules. docs/decisions/2026-11-07-speed-limits-and-signs.md says why.
//
// Sizes in metres. The speed signs have no stated size: 200x300 mm with a 30 mm frame is their family's, the U and Z
// plates' (docs/research/prazsketramvaje/signals.md), which D 1/2's drawings match. Heights over width of the triangle
// and the zone plate are read off the drawings (p. 54, 56).
export const PLATE = { w: 0.2, h: 0.3, frame: 0.03 };
// How much larger than real the game shows the signs: on a 1080p screen the real figures read only up to about 12 m
// (the size experiment, docs/decisions/2026-11-07-speed-limits-and-signs.md). 2 for testing (the user, 2026-11-08: "pick
// 200% now for testing ... keep the size of signs a parameter that can be changed later").
export const SIGN_SCALE = 2;
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

// the face's size in the game's world, metres: the real size times `scale`
export function shownSize(sign, scale = SIGN_SCALE) {
  const s = signSize(sign);
  return { w: Math.round(s.w * scale * 1000) / 1000, h: Math.round(s.h * scale * 1000) / 1000 };
}

// ------------------------------------------------------------------ the figures and text
// Every photo shows a heavy condensed DIN (DIN 1451 Engschrift): the user's 60 Rychlostník and 80 gradient board
// (2026-11-08), the website's 10 and 30 restrictions. D 1/2's drawings use a heavy face for speeds and a serif for
// gradients; the photos win. Bahnschrift Condensed Bold, Windows' DIN 1451 ("Bahnschrift bold looks good", the user,
// 2026-11-08); elsewhere the nearest condensed face. Its figures are wider than the signs': two of them are 1.18 as wide
// as high, the photos' 0.86-1.01. Narrowed to 0.8 of its width ("stretch it so it looks close to the real signs", the
// user), it matches the photos side by side, the vertical strokes as heavy as theirs; at its own width it looked too
// wide. The figures are the photos' size, 0.47 of the panel's height.
// Where Bahnschrift is missing (macOS, Linux, phones), D-DIN Condensed Bold: a DIN 1451 recreation by Datto under the SIL
// Open Font License, loaded from its repository through jsDelivr, pinned to a commit (the user, 2026-11-08: "load the font
// externally anyway and use the din one as fallback"). `loadFigureFont` must have settled before faces are drawn.
const FIGURES = '"Bahnschrift Condensed", "D-DIN Condensed", "Bahnschrift SemiCondensed", "DIN Condensed", "Roboto Condensed", "Arial Narrow", sans-serif';
export const DDIN_URL = 'https://cdn.jsdelivr.net/gh/amcchord/datto-d-din@e199c8441e758d6e492cd01ef52c3c67ba4bae26/D-DINCondensed-Bold.woff2';
const FIGURE_H = 0.113;        // m: the speed signs' figures, the same on every plate
const FIGURE_W = 0.86;         // the most of a panel's width the figures take
const TWO_FIGURES = 0.94;      // two figures' width over their height on the photos (0.86-1.01): each font is narrowed to it
                               // (Bahnschrift to 0.79 of its width, D-DIN to 0.88)

let fontLoad = null;
// Resolves true once D-DIN is there, false if it could not load in `wait` ms (offline, the host down): then the next face
// in FIGURES draws, and the game starts anyway.
export function loadFigureFont(wait = 4000) {
  if (typeof FontFace === 'undefined' || typeof document === 'undefined' || !document.fonts) return Promise.resolve(false);
  if (!fontLoad) {
    const face = new FontFace('D-DIN Condensed', `url(${DDIN_URL}) format('woff2')`, { weight: '700' });
    document.fonts.add(face);
    fontLoad = Promise.race([face.load().then(() => true, () => false), new Promise((done) => setTimeout(() => done(false), wait))]);
  }
  return fontLoad;
}

// how much to narrow the face the canvas resolves for FIGURES, so two figures are as wide as on the photos
function squeezeFor(g) {
  g.save(); g.font = `700 100px ${FIGURES}`;
  const m = g.measureText('60'); g.restore();
  const w = (m.actualBoundingBoxLeft || 0) + (m.actualBoundingBoxRight || m.width), h = m.actualBoundingBoxAscent || 72;
  return Math.min(1, TWO_FIGURES / (w / h));
}

// Text in a box: as large as the box allows, centred in it, `squeeze` times as wide as the font draws it. `bold`: an
// outline of that width (of the height) in the same colour, heavier than the font's own bold.
function fit(g, text, x, y, w, h, { color = BLACK, family = FIGURES, weight = '700', bold = 0, squeeze = 1 } = {}) {
  text = String(text);
  g.save();
  g.font = `${weight} 100px ${family}`;
  g.textAlign = 'left'; g.textBaseline = 'alphabetic';
  const m = g.measureText(text);
  const left = m.actualBoundingBoxLeft || 0, right = m.actualBoundingBoxRight || m.width || 60;
  const up = m.actualBoundingBoxAscent || 72, down = m.actualBoundingBoxDescent || 0;
  const line = bold * h, k0 = (h - line) / (up + down);
  const k = Math.min(k0, (w - line) / ((left + right) * squeeze));
  g.translate(x + w / 2, y + h / 2);
  g.scale(k * squeeze, k);
  g.fillStyle = color;
  g.fillText(text, -(right - left) / 2, (up - down) / 2);
  if (line) { g.strokeStyle = color; g.lineJoin = 'round'; g.lineWidth = line / k; g.strokeText(text, -(right - left) / 2, (up - down) / 2); }
  g.restore();
}

// figures of height h (or narrower than maxW) centred on cx, cy
function figures(g, text, cx, cy, h, color, { maxW = Infinity, bold = 0 } = {}) {
  const w = Math.min(maxW, h * 4);
  fit(g, text, cx - w / 2, cy - h / 2, w, h, { color, bold, squeeze: squeezeFor(g) });
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

// a speed on a panel, the same size on every plate (restriction, point, Rychlostník, zone), smaller only if it is too wide
function number(g, p, text, color, u) {
  figures(g, text, p.x + p.w / 2, p.y + p.h / 2, FIGURE_H * u, color, { maxW: p.w * FIGURE_W });
}

function triangle(g, x, y, w, h, digit, u) {
  const path = (m) => {
    g.beginPath();
    g.moveTo(x + m * 1.73, y + m); g.lineTo(x + w - m * 1.73, y + m); g.lineTo(x + w / 2, y + h - m * 2); g.closePath();
  };
  g.fillStyle = WHITE; path(0); g.fill();
  g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); path(0); g.stroke();
  g.fillStyle = YELLOW; path(0.018 * u); g.fill();
  if (digit !== undefined && digit !== null) figures(g, digit, x + w / 2, y + h * 0.38, h * 0.5, BLACK, { maxW: w * 0.3 });
}

// The gradient board: a grey square, a white pentagon whose point takes the half of the height it points to: its
// shoulders at 0.56 of the height from the point's edge (the user's photos 2026-11-08: 0.56 climbing, 0.44 from the top
// descending; D 1/2 p. 52: 0.56, 0.43).
function pentagon(g, x, y, w, h, up, u) {
  g.fillStyle = '#bdbdbd'; g.fillRect(x, y, w, h);
  g.strokeStyle = EDGE; g.lineWidth = Math.max(1, 0.004 * u); g.strokeRect(x, y, w, h);
  const m = 0.016 * u, s = h * 0.56;
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
    // red figures, their middle at 0.575 of the board climbing and 0.47 descending (the photos); larger and bolder than
    // the photos' (0.23 of the board high) to read in the game (the user, 2026-11-08): 0.30 high, Bahnschrift's bold
    // with an outline of 0.035 of the height on top
    figures(g, sign.permille, x + w / 2, y + h * (up ? 0.575 : 0.47), h * 0.30, '#d81e1e', { maxW: w * 0.62, bold: 0.035 });
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
    number(g, p, sign.v, end ? '#aaa' : BLACK, u);
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
  if (k === 'restriction' || k === 'point') number(g, p, sign.v, BLACK, u);
  else if (k === 'higher') number(g, p, sign.v, '#fff', u);
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
// Black boxes with white LED dots: the switch signal, the number, the entry signal. The call signal is the junctions'
// own, drawn by src/ledPanels.js (#376).
const SEGMENTS = { 0: 'abcdef', 1: 'bc', 2: 'abged', 3: 'abgcd', 4: 'fgbc', 5: 'afgcd', 6: 'afgedc', 7: 'abc', 8: 'abcdefg', 9: 'abcdfg' };

function dots(g, x0, y0, x1, y1, r, step, color) {
  const n = Math.max(1, Math.round(Math.hypot(x1 - x0, y1 - y0) / step));
  g.fillStyle = color;
  for (let i = 0; i <= n; i++) {
    g.beginPath(); g.arc(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n, r, 0, Math.PI * 2); g.fill();
  }
}

// The switch signal's dart, from the photos of R01 (the speed-sign page): straight 0.76 of the box's height long and 0.45
// wide, its notch 0.26 deep and 0.20 wide; sideways 1.0 long and 0.51 wide, the notch 0.36 deep and 0.18 wide, in the
// box's heights. `along` runs from the tail to the tip, `across` from the axis.
const DARTS = { straight: { L: 0.76, B: 0.45, D: 0.26, N: 0.20 }, side: { L: 1.0, B: 0.51, D: 0.36, N: 0.18 } };
function inDart(d, along, across) {
  if (along < 0 || along > d.L || Math.abs(across) > d.B / 2 * (d.L - along) / d.L) return false;
  return !(along < d.D && Math.abs(across) < d.N / 2 * (d.D - along) / d.D);
}

// The number box, from the two R01 photos: each figure a single line of LEDs, 0.69 of the box's height, 0.52 as wide as
// high, the two 0.26 of that height apart (D 1/2 p. 46 draws outlined segments filling the box); about 20 LEDs up a figure;
// the unlit LEDs of the other segments show faintly.
const NUMBER = { h: 0.69, w: 0.52, gap: 0.26, leds: 19 };

// `panel`: {kind: 'chevron', dir: 'straight'|'left'|'right'|null, dark} | {kind: 'number', v, dark}
// | {kind: 'entry', state: 'go'|'stop'|'dark'} | {kind: 'undetermined'} (a dot, § 46.5). W x H px.
export function drawLedPanel(g, panel, W, H) {
  const k = panel.kind;
  g.fillStyle = '#0a0a0a';
  if (k === 'entry') {
    // a round disc with a solid bar, as D 1/2 draws it; nothing outside the disc
    g.beginPath(); g.arc(W / 2, H / 2, Math.min(W, H) * 0.48, 0, Math.PI * 2); g.fill();
    if (panel.state === 'dark') return;
    const r = Math.min(W, H) * 0.42, t = r * 0.25, go = panel.state === 'go';
    g.fillStyle = '#fff';
    if (go) g.fillRect(W / 2 - t, H / 2 - r, 2 * t, 2 * r); else g.fillRect(W / 2 - r, H / 2 - t, 2 * r, 2 * t);
    return;
  }
  // the box, its corners cut as on the photos
  const c = H * 0.07;
  g.beginPath(); g.moveTo(c, 0); g.lineTo(W - c, 0); g.lineTo(W, c); g.lineTo(W, H - c); g.lineTo(W - c, H); g.lineTo(c, H); g.lineTo(0, H - c); g.lineTo(0, c);
  g.closePath(); g.fill();
  if (panel.dark && k !== 'number') return;
  const r = W * 0.012, step = W * 0.034, on = '#fffef0';
  if (k === 'chevron') {
    // a dart with a notch at its tail, in LED dots, centred in the box (D 1/2 p. 46; the photos of R01)
    const shape = (x, y) => {   // in box heights from the middle, y down
      if (panel.dir === 'straight') return inDart(DARTS.straight, DARTS.straight.L / 2 - y, x);
      const along = (panel.dir === 'right' ? x : -x) + DARTS.side.L / 2;
      return inDart(DARTS.side, along, y);
    };
    g.fillStyle = on;
    for (let y = step / 2; y < H; y += step) for (let x = step / 2; x < W; x += step) {
      if (shape((x - W / 2) / H, (y - H / 2) / H)) { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
    }
  } else if (k === 'undetermined') {
    for (let i = -2; i <= 2; i++) for (let j = -2; j <= 2; j++) if (i * i + j * j <= 5) { g.fillStyle = on; g.beginPath(); g.arc(W / 2 + i * step * 0.8, H / 2 + j * step * 0.8, r, 0, Math.PI * 2); g.fill(); }
  } else if (k === 'number') {
    // dark: both places' LEDs unlit
    const digits = panel.dark ? ['', ''] : String(panel.v).split(''), dh = H * NUMBER.h, dw = dh * NUMBER.w, gap = dh * NUMBER.gap;
    const pitch = dh / NUMBER.leds, lr = pitch * 0.36, x0 = (W - digits.length * dw - (digits.length - 1) * gap) / 2, y0 = (H - dh) / 2;
    digits.forEach((d, i) => {
      const x = x0 + i * (dw + gap), y = y0, m = y + dh / 2, e = x + dw, b = y + dh;
      const seg = { a: [x, y, e, y], b: [e, y, e, m], c: [e, m, e, b], d: [x, b, e, b], e: [x, m, x, b], f: [x, y, x, m], g: [x, m, e, m] };
      const lit = SEGMENTS[d] || '';
      for (const s of 'abcdefg') if (!lit.includes(s)) dots(g, ...seg[s], lr, pitch, '#242422');
      for (const s of lit) dots(g, ...seg[s], lr, pitch, on);
    });
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

// ------------------------------------------------------------------ the facts the signs read (data/truth.json)
// `dangerous-gradients`: the boards stand only where the list has one (a slope alone is no dangerous gradient, D 1/2
// § 49.9-12).
export function signFacts(truth) {
  const lists = truth?.operation?.lists || [];
  const list = (id) => lists.find((l) => l.id === id)?.entries || [];
  return {
    gradients: list('dangerous-gradients').filter((e) => e.kind === 'dangerous-gradient' && e.from && e.to)
      .map((e) => ({ place: e.place, from: e.from, to: e.to, descending: !!e.descending, permille: Math.round(e.gradient), length: e.length })),
  };
}

// The listed gradients on this route as [{from, to, permille, up}] (route metres), for planSigns. A list entry names the
// stops either side and which way it falls; the route may pass them either way. The board stands where the listed length
// falls or rises the most between the two stops, read off `heightAt(s)` in 10 m steps.
export function locateGradients(gradients, stops, heightAt) {
  const out = [];
  for (const gr of gradients) {
    const a = stops.find((q) => q.name === gr.from), b = stops.find((q) => q.name === gr.to);
    if (!a || !b) continue;
    const s0 = Math.min(a.s, b.s), s1 = Math.max(a.s, b.s), len = Math.min(gr.length || s1 - s0, s1 - s0);
    // the route descends where it meets `from` first and the list says it falls from there
    const up = (a.s < b.s) !== gr.descending;
    let best = s0, most = -Infinity;
    for (let s = s0; s + len <= s1 + 0.1; s += 10) {
      const d = (heightAt(s + len) - heightAt(s)) * (up ? 1 : -1);
      if (d > most) { most = d; best = s; }
    }
    out.push({ from: Math.round(best), to: Math.round(best + len), permille: gr.permille, up });
  }
  return out;
}

// Curves under 25 m radius (D 1/2 § 49.19), [{from, to, side}] in route metres: `radiusAt(s)` and `turnAt(s)` (the
// heading's change, + left) read every `step` m. A run shorter than `min` m is the radius estimate's noise.
export const SMALL_RADIUS = 25;
export function smallRadiusCurves(length, radiusAt, turnAt, step = 2, min = 6) {
  const out = [];
  let run = null;
  for (let s = 0; s <= length; s += step) {
    if (radiusAt(s) < SMALL_RADIUS) {
      if (!run) run = { from: s, to: s, turn: 0 };
      run.to = s; run.turn += turnAt(s);
    } else if (run) {
      if (run.to - run.from >= min) out.push({ from: run.from, to: run.to, side: run.turn > 0 ? 'left' : 'right' });
      run = null;
    }
  }
  if (run && run.to - run.from >= min) out.push({ from: run.from, to: run.to, side: run.turn > 0 ? 'left' : 'right' });
  return out;
}

// A sign standing within `reach` m past a facing switch the route leaves by its diverging branch holds for that branch:
// it carries the branch's arrow (D 1/2 § 49.13, photo: "10" with an arrow over a fork).
export function withArrows(signs, switches, reach = 15) {
  return signs.map((g) => {
    if (!['restriction', 'point', 'switchV', 'slow'].includes(g.kind)) return g;   // the "r" sign draws its own curve's arrow
    const w = switches.find((x) => x.routeDiverging && g.s >= x.s - 2 && g.s <= x.s + reach);
    return w ? { ...g, arrow: w.routeSide === 'right' ? 'right' : 'left' } : g;
  });
}
