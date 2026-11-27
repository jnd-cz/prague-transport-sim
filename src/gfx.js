// SPDX-License-Identifier: AGPL-3.0-or-later
// Drawing switches for measuring what a frame's fill costs on a weak GPU (#705), from the page's address, each change
// alone or several together: ?gfx=nolog,pr1
//   nolog   no logarithmic depth buffer: with it three.js writes every fragment's depth (gl_FragDepth), so the GPU
//           cannot reject a hidden fragment before shading it
//   snowif  the snow's noise only while it snows (src/weather.js)
//   front   front faces only on the ground and the buildings (src/groundDraw.js, src/buildings.js)
//   pr<n>   the pixel ratio at most n (pr1, pr0.75; without it the display's, at most 1.75)
//   noaa    no antialiasing (the canvas's multisampling)
// A performance test's result and a note carry the list (src/perf.js machine), so a number says what it ran with.
import * as THREE from 'three';

const KNOWN = ['nolog', 'snowif', 'front', 'noaa'];
const asked = (new URLSearchParams(location.search).get('gfx') || '').split(',').map((s) => s.trim()).filter(Boolean);
const pr = asked.map((s) => /^pr(\d+(?:\.\d+)?)$/.exec(s)).find(Boolean);
const list = asked.filter((s) => KNOWN.includes(s) || (pr && s === pr[0]));
for (const s of asked) if (!list.includes(s)) console.warn(`gfx: unknown switch "${s}" (${KNOWN.join(', ')}, pr<n>)`);

export const GFX = {
  key: list.join(','),                         // as asked, for the results and to carry to another page
  logDepth: !list.includes('nolog'),
  antialias: !list.includes('noaa'),
  snowBranch: list.includes('snowif'),
  side: list.includes('front') ? THREE.FrontSide : THREE.DoubleSide,
  maxPixelRatio: pr ? Math.max(0.25, +pr[1]) : 1.75,
};
// "&gfx=…" for an address that opens another line with the same switches (the reference test)
export const gfxQuery = GFX.key ? `&gfx=${encodeURIComponent(GFX.key)}` : '';
