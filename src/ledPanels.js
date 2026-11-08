// The LED panels of junction signals and switches, drawn on a 2D canvas (#376). Pure: no Three.js, no game state, so a
// page can draw them and a test can count their LEDs. Shapes from D 1/2 (p. 37, 44, 45) and photos, measured below.

const PANEL = '#0b0b0b';
const dot = (g, x, y, r) => { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); };

// ------------------------------------------------------------------ the call signal (výzvové návěstidlo, § 42.3, 46.2)
// Three strips of 7 LED pairs, \ | /. D 1/2 draws them 2 LEDs wide and 7 long (p. 37, 45). The photos (two from
// Wikimedia, 2026-11-08) put the vertical strip in the middle, spanning 0.63 of the panel's height; each leaning strip is
// the same strip turned 24° about its middle (the user: "the same led strip rectangular design for left and right, just
// rotated, not stretched and shifted"), its bottom end beside the vertical one's without touching. Measured on a photo, in
// steps along a strip: a pair's LEDs 0.69 apart, a leaning strip's bottom pair 1.14 from the middle, LEDs 0.38 wide.
const CALL = { rows: 7, step: 0.105, pair: 0.69, lean: 24 * Math.PI / 180, foot: 1.14, r: 0.19 };
export const CALL_LIT = '#ffb81c';      // the photos' amber; D 1/2 draws pure yellow
const CALL_DARK = '#2a2922';

// The LED centres of each strip in a W x H panel, [x, y] px, top row first.
export function callLeds(W, H) {
  const s = CALL.step * H, half = (CALL.rows - 1) / 2, out = {};
  const off = (CALL.foot + half * Math.sin(CALL.lean)) * s;            // a leaning strip's middle from the panel's
  for (const [k, side] of [['left', -1], ['straight', 0], ['right', 1]]) {
    const a = side * CALL.lean, ux = Math.sin(a), uy = -Math.cos(a);   // up the strip (y down)
    const cx = W / 2 + side * off, cy = H / 2;
    out[k] = [];
    for (let j = 0; j < CALL.rows; j++) {
      const u = (half - j) * s;                                         // top row first
      for (const o of [-0.5, 0.5]) {
        const v = o * CALL.pair * s;                                    // across the strip
        out[k].push([cx + u * ux - v * uy, cy + u * uy + v * ux]);
      }
    }
  }
  return out;
}

// `lit`: the strips lit, a list of 'left' | 'straight' | 'right' (two when two requests are registered); empty: dark
export function drawCallSignal(g, lit, W, H) {
  g.fillStyle = PANEL; g.fillRect(0, 0, W, H);
  const on = new Set(lit || []), r = CALL.r * CALL.step * H;
  for (const [k, leds] of Object.entries(callLeds(W, H))) {
    g.fillStyle = on.has(k) ? CALL_LIT : CALL_DARK;
    for (const [x, y] of leds) dot(g, x, y, r);
  }
}

// ------------------------------------------------------------------ the switch signal (§ 45.3-5, p. 44)
// One matrix of red LEDs holds every symbol; the LEDs of the symbols not shown are dark, the rest of the panel is black.
// Right: a broad dart with a swallow-tail notch, its wings reaching the corners and its tip one LED; left: mirrored;
// straight: a bar 4 LEDs wide with a pointed top; undetermined: a cluster in the middle. Grid units, the panel's middle at
// 0 and y down, read off p. 44: columns at half steps either side of the middle, their rows shifted half a step in every
// other pair of columns as there.
const SW_ROWS = 18.5;                   // the panel's height in grid steps (D 1/2: 18, the width 25)
export const SWITCH_LIT = '#ff2a12';
const SWITCH_DARK = '#2c2422';
const DART = { tail: -9.8, tip: 10.3, wing: 5.3, notch: -2.0, notchWing: 2.3 };

function inDart(x, y) {
  if (x < DART.tail || x > DART.tip) return false;
  const outer = DART.wing * (DART.tip - x) / (DART.tip - DART.tail);
  const notch = x < DART.notch ? DART.notchWing * (DART.notch - x) / (DART.notch - DART.tail) : -1;
  return Math.abs(y) <= outer && Math.abs(y) > notch;
}

// does the LED at grid x, y belong to the symbol?
function inSymbol(sym, x, y) {
  if (sym === 'right') return inDart(x, y);
  if (sym === 'left') return inDart(-x, y);
  if (sym === 'straight') return Math.abs(x) <= 1.6 && y <= 7 && y >= -8.3 + 1.5 * Math.abs(x) / 1.8;
  if (sym === 'undetermined') return Math.abs(x) <= 1.6 && Math.abs(y) <= 1.2;
  return false;
}
export const SWITCH_SYMBOLS = ['left', 'straight', 'right', 'undetermined'];

// The matrix's LEDs in a W x H panel: [{x, y, symbols}] px, each with the symbols it belongs to.
export function switchLeds(W, H) {
  const p = H / SW_ROWS, half = W / p / 2, out = [];
  for (let i = 0.5; i < half; i++) for (const gx of [i, -i]) {
    const shift = Math.floor((i + 0.5) / 2) % 2 ? 0.5 : 0;   // the middle pair on whole rows, the next pairs on halves
    for (let j = -Math.ceil(SW_ROWS / 2); j <= Math.ceil(SW_ROWS / 2); j++) {
      const gy = j + shift, symbols = SWITCH_SYMBOLS.filter((s) => inSymbol(s, gx, gy));
      if (symbols.length) out.push({ x: W / 2 + gx * p, y: H / 2 + gy * p, symbols });
    }
  }
  return out;
}

// `sym`: 'left' | 'straight' | 'right' | 'undetermined'; anything else: every LED dark (a blink's dark phase)
export function drawSwitchSignal(g, sym, W, H) {
  g.fillStyle = PANEL; g.fillRect(0, 0, W, H);
  const r = 0.32 * H / SW_ROWS;
  for (const l of switchLeds(W, H)) {
    g.fillStyle = l.symbols.includes(sym) ? SWITCH_LIT : SWITCH_DARK;
    dot(g, l.x, l.y, r);
  }
}
