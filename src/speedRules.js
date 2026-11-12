// SPDX-License-Identifier: AGPL-3.0-or-later
// The speeds D 1/2 § 25 sets over switches and crossings, read from data/truth.json `operation`, as stretches of route
// for Route.speedLimits (#211). Pure: docs/decisions/2026-11-07-speed-limits-and-signs.md measures and explains them.
//
// A stretch runs over the trackwork itself, from the blades to the frog, and `restriction-past` metres on (the user's
// margin, 0 since 2026-11-08). Game.currentLimit holds it until the rear has left it (`restriction-start-end`: front in,
// rear out), so the stretch does not add the tram's length.
const TIP = 4;       // m before the fork: DI draws 48 of its switches as a section whose fork lies 4-5 m past the tip (docs/knowledge.md)
export const FROG = 11.5; // m past the fork, where the other leg lies one gauge off: median of the 82 facing switches of the five lines, 10.5-13.5 m p10-p90 (#211); the build's `frog` when it has one
const DIAMOND = 3;   // m either side of a crossing node: its rails (a diamond's own length, read off DI's chains)
const NEAR_TRACKWORK = 15;   // m: an OSM 15 km/h piece this near a switch or crossing is that rule's own stretch

const FACTS = { facing: 'switch-facing-speed', trailingDiverging: 'switch-trailing-diverging-speed',
                trailingStraight: 'switch-trailing-straight-speed', crossing: 'crossing-speed',
                general: 'max-speed', smallRadius: 'small-radius-speed', past: 'restriction-past',
                loop: 'loop-speed', stopPass: 'stop-pass-speed', curveAccel: 'curve-lateral-acceleration' };
const PLACES = ['trojska-descent'];   // the local rules by place: only where OSM tags no speed (placeStretches)

// {facing, trailingDiverging, trailingStraight, crossing, general, smallRadius, loop, stopPass} km/h, `past` m and `curveAccel` m/s², by the facts' ids;
// `places`: [{from, to, v}], a local rule between two stops, at the highest speed it names
export function speedFacts(truth) {
  const out = {}, facts = truth?.operation?.facts || [];
  const fact = (id) => facts.find((x) => x.id === id);
  for (const [k, id] of Object.entries(FACTS)) {
    const f = fact(id);
    if (!Number.isFinite(f?.value)) throw new Error(`data/truth.json operation: no value for the fact ${id}`);
    out[k] = f.value;
  }
  out.places = PLACES.map((id) => {
    const f = fact(id);
    if (!f?.place || !Array.isArray(f.value)) throw new Error(`data/truth.json operation: no place and speeds for the fact ${id}`);
    return { ...f.place, v: Math.max(...f.value) };
  });
  return out;
}

// [{from, to, v}]: `switches` the route's facing switches ({s, frog?}), `trackwork` the line's {trailing: [{s, fromDiverging,
// frog?}], crossings: [s], loops: [{from, to}]} (tools/build_line.py; absent from data built before #211, loops before
// 2026-11-09)
export function trackworkStretches(switches, trackwork, facts) {
  const past = facts.past;
  const out = switches.map((w) => ({ from: w.s - TIP, to: w.s + (w.frog ?? FROG) + past, v: facts.facing }));
  for (const w of trackwork?.trailing || []) {
    out.push({ from: w.s - (w.frog ?? FROG), to: w.s + TIP + past, v: w.fromDiverging ? facts.trailingDiverging : facts.trailingStraight });
  }
  for (const s of trackwork?.crossings || []) out.push({ from: s - DIAMOND, to: s + DIAMOND + past, v: facts.crossing });
  // turning loops, from the switch into the loop to the switch out of it (§ 25.4 e; found on DI's network by the user's
  // rule, tools/track_loops.py)
  for (const l of trackwork?.loops || []) out.push({ from: l.from, to: l.to + past, v: facts.loop });
  return out;
}

// [{s, v, stop}] by s: limits the front alone keeps at a point (`point-restriction`, D 1/2 § 49.16): the stop sign of
// each stop but the first at `stop-pass-speed` (§ 25.5 b, the front passing the sign of a stop where the train does not
// stop; a train that stops there comes to its sign at a crawl anyway). `stops` the game's, `target` where the front stops
// beside the sign. The user, 2026-11-09 (#211): "point limit with overspeed penalty, autopilot has to follow".
export function stopPassPoints(stops, facts) {
  return stops.slice(1).map((st) => ({ s: st.target, v: facts.stopPass, stop: st.name })).sort((a, b) => a.s - b.s);
}

// Derailment, a game rule (#451; the user, 2026-11-10: "Instead of flat offset I would build something like 40-50% over speed limit or
// something over 2-2.5 m/s² for at least one second"): for DERAIL.secs on end, a curve under any part of the tram taken at more than
// DERAIL.lateral unbalanced, 1.5 times the speed `curve-lateral-acceleration` allows there, or a switch, crossing or loop restriction of
// DERAIL.upTo km/h or less taken at more than DERAIL.over times its speed. It was 22 km/h over any limit of 20 and under: 37 km/h on
// a 15 km/h hairpin, and none at all on the curves #451 raised over 20.
export const DERAIL = { lateral: 2.25, over: 1.5, upTo: 20, secs: 1 };

// 'curve', 'trackwork' or null: what the tram (front at s, `length` m, v m/s) would derail on if it kept this up, on `route`
// (radiusAt, cantAt) under `limits` (the game's speedLimits: restriction)
export function derailRisk(route, limits, s, length, v) {
  const kmh = v * 3.6;
  for (let x = s - length; x <= s + 0.1; x += 2) {
    if ((v * v) / route.radiusAt(x) - (route.cantAt(x) * 9.81) / 1.5 > DERAIL.lateral) return 'curve';
    const r = limits.restriction(x);
    if (r <= DERAIL.upTo && kmh > DERAIL.over * r) return 'trackwork';
  }
  return null;
}

// [{from, to, v}]: a local rule's speed where a line runs from its first stop straight to its second (so not the other
// way, uphill at Trojská) and OSM tags no speed: `posted` is data.speed.osm, `step` m apart, 0 where untagged. OSM comes
// first; the fact is the backup (the user, 2026-11-07, `trojska-descent`).
export function placeStretches(places, stops, posted, step) {
  const out = [];
  for (const p of places) {
    for (let i = 0; i + 1 < stops.length; i++) {
      if (stops[i].name !== p.from || stops[i + 1].name !== p.to) continue;
      let from = null;
      for (let s = stops[i].s; s <= stops[i + 1].s; s += step) {
        const free = !posted?.[Math.round(s / step)];
        if (free && from === null) from = s;
        const end = s + step > stops[i + 1].s;
        if (from !== null && (!free || end)) {
          const to = free ? stops[i + 1].s : s;
          if (to > from) out.push({ from, to, v: p.v });
          from = null;
        }
      }
    }
  }
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
