// SPDX-License-Identifier: AGPL-3.0-or-later
// An element's box on the page, kept between the changes that can move it (#706). The mirror and the cab frame asked
// the page for it on every frame (getBoundingClientRect), right after the HUD's writes: the page then lays itself out
// in the middle of the frame. What moves or sizes these fixed elements: the window's size, body's classes and its
// style (chase, touch, the compact panel; --dashH, src/panel.js fit) and the element's own classes, style and size.
// None of them is animated (index.html). A box read after such a change is measured once and kept.
let stamp = 0, wired = false;
const bump = () => { stamp++; };
const kept = new WeakMap(); // element -> { at: the stamp it was measured at, rect }
const ATTRS = { attributes: true, attributeFilter: ['class', 'style'] };

export function rectOf(el) {
  if (!(el instanceof Element)) return el.getBoundingClientRect(); // (a test's stand-in)
  if (!wired) {
    wired = true;
    addEventListener('resize', bump);
    new MutationObserver(bump).observe(document.body, ATTRS);
  }
  let k = kept.get(el);
  if (!k) {
    kept.set(el, k = { at: -1, rect: null });
    new MutationObserver(bump).observe(el, ATTRS);
    new ResizeObserver(bump).observe(el); // (its size by anything else: a media query, a font; seen a frame late)
  }
  if (k.at !== stamp) { k.rect = el.getBoundingClientRect(); k.at = stamp; }
  return k.rect;
}
