// The speeds D 1/2 § 25 sets over switches and crossings, read from data/truth.json `operation`, as stretches of route
// for Route.speedLimits (#211). Pure: docs/decisions/2026-11-07-speed-limits-and-signs.md measures and explains them.
//
// One extension only: a stretch runs over the trackwork itself, from the blades to the frog. Game.currentLimit holds it
// until the rear has left it (`restriction-start-end`: front in, rear out), so the stretch does not add the tram's length.
const TIP = 4;       // m before the fork: DI draws 48 of its switches as a section whose fork lies 4-5 m past the tip (docs/knowledge.md)
export const FROG = 11.5; // m past the fork, where the other leg lies one gauge off: median of the 82 facing switches of the five lines, 10.5-13.5 m p10-p90 (#211); the build's `frog` when it has one
const DIAMOND = 3;   // m either side of a crossing node: its rails (a diamond's own length, read off DI's chains)
const NEAR_TRACKWORK = 15;   // m: an OSM 15 km/h piece this near a switch or crossing is that rule's own stretch

const FACTS = { facing: 'switch-facing-speed', trailingDiverging: 'switch-trailing-diverging-speed',
                trailingStraight: 'switch-trailing-straight-speed', crossing: 'crossing-speed',
                general: 'max-speed', smallRadius: 'small-radius-speed' };

// {facing, trailingDiverging, trailingStraight, crossing, general, smallRadius} km/h, by the facts' ids
export function speedFacts(truth) {
  const out = {}, facts = truth?.operation?.facts || [];
  for (const [k, id] of Object.entries(FACTS)) {
    const f = facts.find((x) => x.id === id);
    if (!Number.isFinite(f?.value)) throw new Error(`data/truth.json operation: no value for the fact ${id}`);
    out[k] = f.value;
  }
  return out;
}

// [{from, to, v}]: `switches` the route's facing switches ({s, frog?}), `trackwork` the line's {trailing: [{s, fromDiverging,
// frog?}], crossings: [s]} (tools/build_line.py; absent from data built before #211)
export function trackworkStretches(switches, trackwork, facts) {
  const out = switches.map((w) => ({ from: w.s - TIP, to: w.s + (w.frog ?? FROG), v: facts.facing }));
  for (const w of trackwork?.trailing || []) {
    out.push({ from: w.s - (w.frog ?? FROG), to: w.s + TIP, v: w.fromDiverging ? facts.trailingDiverging : facts.trailingStraight });
  }
  for (const s of trackwork?.crossings || []) out.push({ from: s - DIAMOND, to: s + DIAMOND, v: facts.crossing });
  return out;
}

// The posted speeds (data.speed.osm, 5 m apart) without the 15 km/h pieces OSM tags on a switch or crossing: those are
// the stretches above, and they ran on for a median 17-52 m past it. Only with the line's trackwork: without its trailing
// switches and crossings, these pieces are all the game knows of them.
export function withoutOwnPieces(posted, step, switches, trackwork, facts) {
  if (!trackwork) return posted;
  const at = [...switches.map((w) => w.s), ...(trackwork.trailing || []).map((w) => w.s), ...(trackwork.crossings || [])];
  const out = posted.slice();
  for (let i = 0, j; i < out.length; i = j) {
    for (j = i; j < out.length && out[j] === out[i];) j++;
    if (out[i] !== facts.facing) continue;
    const from = i * step, to = j * step;
    if (at.some((s) => s > from - NEAR_TRACKWORK && s < to + NEAR_TRACKWORK)) out.fill(0, i, j);
  }
  return out;
}
