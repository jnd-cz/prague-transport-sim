// SPDX-License-Identifier: AGPL-3.0-or-later
// The automatic render scale (#705): while driving frames are slow, draw fewer pixels; keep a step only if it helped.
//
// A player's browser keeps vsync, so a GPU that cannot hold the display's rate shows as frames taking two of its
// intervals, not as a longer one: the tester's integrated GPU at 43.5 frames a second had a median of 17 ms and
// 32.7 % of its frames over 20 ms; with the fill cost halved, 1 to 2.4 % (2026-11-27, #705). So a window of frames
// is slow by its share over SLOW ms, which a few long frames (a tile arriving) do not reach.
//   - The first SKIP ms after a start, a pause or a step are left out (programs compile, the buffer is made anew).
//   - Two slow windows in a row: one step down the scales.
//   - The window after a step: if its mean frame is not BETTER times shorter, the pixels were not the limit (the
//     CPU, or a display or browser held to 30 frames a second): the step is taken back and the scale stays.
//     Otherwise the step is kept, and a still slow window steps again.
// It never steps up otherwise: under vsync a frame that keeps up says nothing of the room left. The choice lasts
// for the page; each decision is logged (log, shown in the performance overlay and sent with a note's machine).
export const SCALES = [1, 0.75, 0.5];
const SKIP = 2000, WINDOW = 3000;   // ms
const SLOW = 20.5, SHARE = 0.25;    // a window is slow when over SHARE of its frames took over SLOW ms
const GAP = 250;                    // ms: a longer interval is a pause, a hidden tab or an idle redraw, not a frame
const BETTER = 0.9;                 // a kept step made the mean frame at least a tenth shorter
const FEW = 20;                     // frames: a window with fewer says nothing

export class AutoScale {
  constructor(scales = SCALES) {
    this.scales = scales; this.i = 0;
    this.held = false;      // the scale stays: a step did not help, or the last scale is reached and still slow
    this.trial = null;      // the mean frame before the step being tried (ms)
    this.slowRuns = 0;
    this.log = [];
    this.last = -Infinity; this._begin(-Infinity);
  }

  get scale() { return this.scales[this.i]; }

  _begin(now) { this.t0 = now; this.n = 0; this.slow = 0; this.sum = 0; }

  _step(to, now, why, share, mean) {
    this.log.push({ from: this.scale, to: this.scales[to], why, slow: Math.round(share * 1000) / 10, ms: Math.round(mean * 10) / 10 });
    this.i = to;
    this._begin(now);
    return this.scale;
  }

  // one drawn frame while driving (now in ms): the new scale when it changes, else null
  frame(now) {
    const dt = now - this.last;
    this.last = now;
    if (this.held) return null;
    if (!(dt > 0 && dt < GAP)) { this._begin(now); this.slowRuns = 0; return null; } // (a pause: the window starts anew)
    if (now - this.t0 < SKIP) return null;
    this.n++; this.sum += dt; if (dt > SLOW) this.slow++;
    if (now - this.t0 < SKIP + WINDOW) return null;
    const n = this.n, share = this.slow / n, mean = this.sum / n, slow = share > SHARE;
    this._begin(now - SKIP); // (the next window follows at once: nothing changed that needs settling)
    if (n < FEW) return null;
    if (this.trial !== null) {
      const before = this.trial;
      this.trial = null;
      if (mean > before * BETTER) { this.held = true; return this._step(this.i - 1, now, 'no faster: back', share, mean); }
      this.slowRuns = slow ? 1 : 0; // (kept; still slow, it steps again after one more slow window)
      return null;
    }
    this.slowRuns = slow ? this.slowRuns + 1 : 0;
    if (this.slowRuns < 2) return null;
    this.slowRuns = 0;
    if (this.i === this.scales.length - 1) { this.held = true; this.log.push({ from: this.scale, to: this.scale, why: 'still slow at the last scale', slow: Math.round(share * 1000) / 10, ms: Math.round(mean * 10) / 10 }); return null; }
    this.trial = mean;
    return this._step(this.i + 1, now, 'slow', share, mean);
  }
}
