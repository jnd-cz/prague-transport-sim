// SPDX-License-Identifier: AGPL-3.0-or-later
// The surveyed street surfaces as drawn (#21): waves along the street, seams between neighbouring
// areas, kerbs between road and sidewalk. Run from the command line:
//   python -P -E tools/headless.py --lines 17,22 --checks surfaces
// or in a page started with ?keepgeo: const { run } = await import('/tools/bench/surfaces.js'); await run()
// Before #21 (main f4cb8ea, line 17 / 22): waves 6.8 / 4.4 % of the samples, seams over 3 cm 13 / 3.9 %,
// kerb step median 0.06 m (the survey's one kerb line gave both sides one height).
// Kerbs lowered on purpose (tools/kerbs.py's stretches at crossings, #303) are counted apart: loweredKerbs, and the
// flat and sunk kerbs are plain kerb's.
// The ground file (#509) is one welded surface, continuous but at its steps, with no areas to tell apart: across the
// route every 0.25 m a step is two neighbouring samples' difference, less the slope on either side (each side's own
// class) where that explains more of it (a crest's change of slope is no step); one inside the street classes is a
// seam, one where road meets a raised class a kerb. `of` counts the street samples' pairs, not the areas' borders.
// (Without the file, #510 removed, the drawn survey's areas were told apart by their triangles.)
// A raised tram belt's kerb is counted apart too (bedKerbs, #770; the user, 2026-11-26: "yes for the count as you
// recommend"): a road or a parking strip beside the tram's surface, the tram's side higher by more than the belt
// that counts as unraised (data/truth.json streetGeometry `raised-belt`, the height from which the build keeps the
// road's own level at the belt's edge, #606) and by no more than BED_KERB. The user on Řepy, 2026-11-21: "yes there
// is kerb at Makovského". Against IPR 1 m either side of the edge (batch D, 1,088 steps of 0.10-0.25 m on the five
// lines): the lidar has the belt 5 cm or more over the road at 69 % of those of 0.10-0.15 m and at 80 % of those of
// 0.15-0.25 m, and has it level or lower at 14 and 6 %. Over 0.25 m (204 samples) the lidar's median is 0.15 m,
// about half of what is built: those stay seams, as does a road standing over the tram's surface.
// `over10cm` is the part of them seams10 counted before.
import { findKerbs } from '../../src/review.js';
const STREETS = new Set(['road', 'tram', 'parking', 'sidewalk', 'island', 'median', 'cycle', 'paved', 'platform']);
const ROAD = new Set(['road', 'tram', 'parking']), RAISED = new Set(['sidewalk', 'island', 'median', 'platform']);
const BED_KERB = 0.25; // m: a raised belt's kerb at most (the calibration above)

export async function run() {
  const g = window.game, r = g.route, dtm = r.ground.dtm;
  if (!dtm) return { checks: {} };
  const truth = await (await fetch('/data/truth.json', { cache: 'no-store' })).json();
  const belt = truth?.streetGeometry?.facts?.find((f) => f.id === 'raised-belt')?.value;
  if (typeof belt !== 'number') throw new Error('data/truth.json streetGeometry raised-belt is missing');
  // waves: lint streetWaviness's samples (6-20 m either side, every 1 m), over 8 cm off the 21 m mean
  let wn = 0, waves = 0;
  for (const lat of [-20, -14, -9, -6, 6, 9, 14, 20]) {
    const zs = [], cs = [];
    for (let s = 0; s < r.length; s++) { const o = r.offset(s, lat), t = dtm.surfaceAt(o.x, o.y); zs.push(t ? t.z : null); cs.push(t ? t.c : null); }
    for (let i = 10; i < zs.length - 10; i++) {
      if (zs[i] === null || !STREETS.has(cs[i])) continue;
      let sum = 0, ok = true;
      for (let k = -10; k <= 10 && ok; k++) { if (zs[i + k] === null || cs[i + k] !== cs[i]) ok = false; else sum += zs[i + k]; }
      if (!ok) continue;
      wn++;
      if (Math.abs(zs[i] - sum / 21) > 0.08) waves++;
    }
  }
  // the lowered stretches: a kerb site within a stretch's half width and ramp (+0.5 m) of its meeting point
  const low = findKerbs(dtm.provenance || g.data.dtm?.provenance)?.lowered, LC = 10, cells = new Map();
  const reach = low ? low.rule.width / 2 + 0.1 / low.rule.ramp + 0.5 : 0;
  for (const t of low?.stretches || []) {
    if (t.h === null) continue;
    const k = `${Math.floor(t.x / LC)},${Math.floor(t.y / LC)}`;
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k).push(t);
  }
  const lowered = (x, y) => {
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++)
      for (const t of cells.get(`${Math.floor(x / LC) + i},${Math.floor(y / LC) + j}`) || []) if (Math.hypot(t.x - x, t.y - y) <= reach) return true;
    return false;
  };
  // seams and kerbs: across the route every 0.25 m, a row every 4 m, where two areas meet
  const seams = [], kerbs = [], seamSites = [], kerbSites = [], lowSites = [], bedKerbs = [];
  const lk = r.ground.lookup;
  for (let s = 0; s < r.length; s += 4) {
    const zs = [], cs = [];
    for (let lat = -25; lat <= 25; lat += 0.25) { const o = r.offset(s, lat), t = lk.survey(o.x, o.y); zs.push(t ? t.z : null); cs.push(t ? t.c : null); }
    for (let i = 1; i < zs.length; i++) {
      if (zs[i] === null || zs[i - 1] === null) continue;
      const a = cs[i - 1], b = cs[i];
      const kerb = (ROAD.has(a) && RAISED.has(b)) || (RAISED.has(a) && ROAD.has(b));
      const same = STREETS.has(b) && (a === b || (ROAD.has(a) && ROAD.has(b)));
      if (!kerb && !same) continue;
      const left = i > 1 && zs[i - 2] !== null && cs[i - 2] === a ? zs[i - 1] - zs[i - 2] : null;
      const right = i + 1 < zs.length && zs[i + 1] !== null && cs[i + 1] === b ? zs[i + 1] - zs[i] : null;
      let jump = zs[i] - zs[i - 1];
      for (const sl of [left, right]) if (sl !== null && Math.abs(zs[i] - zs[i - 1] - sl) < Math.abs(jump)) jump = zs[i] - zs[i - 1] - sl;
      const lat = -25 + (i - 0.5) * 0.25, p = r.offset(s, lat), site = { x: p.x, y: p.y, s, lat, classes: [a, b], heights: [zs[i - 1], zs[i]] };
      if (same) {
        if (Math.abs(jump) > 1) continue; // (another level)
        const up = a === b ? 0 : b === 'tram' ? jump : a === 'tram' ? -jump : 0; // (the tram's side over the road's)
        if (up > belt && up <= BED_KERB) { bedKerbs.push(up); continue; }
        seams.push(Math.abs(jump));
        if (Math.abs(jump) > 0.03) seamSites.push({ ...site, step: Math.abs(jump) });
      } else {
        const step = ROAD.has(b) ? -jump : jump;
        if (lowered(site.x, site.y)) lowSites.push({ ...site, step });
        else { kerbs.push(step); kerbSites.push({ ...site, step }); }
      }
    }
  }
  const n = (a, f) => a.filter(f).length;
  const med = (a) => { const b = [...a].sort((x, y) => x - y); return b.length ? b[b.length >> 1] : 0; };
  return {
    samples: { seams10:seamSites.filter((s) => s.step > 0.1),
      flatKerbs:kerbSites.filter((s) => s.step < 0.05), sunkKerbs:kerbSites.filter((s) => s.step < -0.02) },
    checks: {
      waves: { count: waves, of: wn },
      seams3: { count: n(seams, (v) => v > 0.03), of: seams.length },
      seams10: { count: n(seams, (v) => v > 0.1), of: seams.length, at:seamSites.filter((s) => s.step > 0.1).map((s) => [s.x,s.y,s.s]) },
      flatKerbs: { count: n(kerbs, (v) => v < 0.05), of: kerbs.length, at:kerbSites.filter((s) => s.step < 0.05).map((s) => [s.x,s.y,s.s]) },
      sunkKerbs: { count: n(kerbs, (v) => v < -0.02), of: kerbs.length, at:kerbSites.filter((s) => s.step < -0.02).map((s) => [s.x,s.y,s.s]) },
      kerbMedianCm: { count: Math.round(med(kerbs) * 100) },
      loweredKerbs: { count: lowSites.length, medianCm: Math.round(med(lowSites.map((q) => q.step)) * 100),
        sunk: n(lowSites, (q) => q.step < -0.02), over5cm: n(lowSites, (q) => q.step >= 0.05) },
      bedKerbs: { count: bedKerbs.length, medianCm: Math.round(med(bedKerbs) * 100), over10cm: n(bedKerbs, (v) => v > 0.1) },
    },
  };
}
