// SPDX-License-Identifier: AGPL-3.0-or-later
// How the page draws (#705): the menu's two settings, kept in the browser, and the address's switches for measuring.
//
// A weak GPU is short of fragments, not of triangles. Two things made every fragment dear, each about half of the
// fill cost where it was measured (DEVELOPING.md, "What the fragments cost"), and the page now draws without both:
// the logarithmic depth buffer (with it three.js writes every fragment's depth, gl_FragDepth, and the GPU cannot
// reject a hidden fragment before shading it) and the snow's noise in every weather (src/weather.js).
//
// The menu's settings (SETTINGS):
//   scale  the share of the display's pixels drawn along each axis: auto (src/autoscale.js steps it down while
//          the driving frames are slow), 1, 0.75 or 0.5
//   aa     antialiasing (the canvas's multisampling): on or off. The canvas gets it when the page loads, so a
//          change loads the page again
// The address's switches, each alone or several together: ?gfx=log,pr1
//   log      the logarithmic depth buffer, as before
//   snowall  the snow's noise in every weather, as before
//   front    front faces only on the ground and the buildings (src/groundDraw.js, src/buildings.js). For timing
//            only: roofs are wound inwards, so some vanish and others show their dark insides (2026-11-27)
//   pr<n>    the pixel ratio at most n (pr1, pr0.75; without it the display's, at most 1.75), and no render scale:
//            a measurement draws what it asked for
//   noaa     no antialiasing, whatever the menu's setting
// A performance test's result and a note carry the list, the scale and what the canvas got (src/perf.js machine),
// so a number says what it ran with.
import * as THREE from 'three';

const KNOWN = ['log', 'snowall', 'front', 'noaa'];
const asked = (new URLSearchParams(location.search).get('gfx') || '').split(',').map((s) => s.trim()).filter(Boolean);
const pr = asked.map((s) => /^pr(\d+(?:\.\d+)?)$/.exec(s)).find(Boolean);
const list = asked.filter((s) => KNOWN.includes(s) || (pr && s === pr[0]));
for (const s of asked) if (!list.includes(s)) console.warn(`gfx: unknown switch "${s}" (${KNOWN.join(', ')}, pr<n>)`);

// the menu's settings: their values (the first is the default) and where the browser keeps them
export const SETTINGS = { scale: ['auto', '1', '0.75', '0.5'], aa: ['on', 'off'] };
const STORE = 'tram.gfx';
function stored() {
  try { const o = JSON.parse(localStorage.getItem(STORE) || '{}'); return o && typeof o === 'object' ? o : {}; } catch { return {}; }
}
export function setting(name) {
  const v = stored()[name];
  return SETTINGS[name].includes(v) ? v : SETTINGS[name][0];
}
export function setSetting(name, value) {
  if (!SETTINGS[name].includes(value)) return;
  try { localStorage.setItem(STORE, JSON.stringify({ ...stored(), [name]: value })); } catch { /* storage unavailable */ }
}

export const GFX = {
  key: list.join(','),                         // as asked, for the results and to carry to another page
  logDepth: list.includes('log'),
  antialias: !list.includes('noaa') && setting('aa') === 'on',
  snowAlways: list.includes('snowall'),
  side: list.includes('front') ? THREE.FrontSide : THREE.DoubleSide,
  maxPixelRatio: pr ? Math.max(0.25, +pr[1]) : 1.75,
  fixed: !!pr,                                 // (pr<n>: the pixel ratio as asked, no render scale)
  scale: 1,                                    // the render scale now drawn with (src/main.js applyScale)
  auto: null,                                  // what the automatic scale decided, in order (src/autoscale.js log)
};
// "&gfx=…" for an address that opens another line with the same switches (the reference test)
export const gfxQuery = GFX.key ? `&gfx=${encodeURIComponent(GFX.key)}` : '';
