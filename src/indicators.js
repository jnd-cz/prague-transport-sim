// SPDX-License-Identifier: AGPL-3.0-or-later
// When a tram blinks its indicators by itself: the autopilot (src/main.js) and the AI trams (src/traffic.js); our
// driver works them with keys. The user, 2026-11-10 (#436): "Turning at junction and stopping at street level
// stop across car lane", at such a stop the right ones from braking into it until it pulls away.
const TURN = (30 * Math.PI) / 180; // a junction turn: the branch turns more than this within TURN_RUN m
const TURN_RUN = 40;
const LEAD = 50;                   // on from this far before the switch (the tram's front)
const STOP_LEAD = 60;              // a stop's indicators: braking within this far before its stopping point

// The turns at junctions along a route: each switch after which the route turns more than 30 deg within 40 m
// (a crossover's S-bend comes back and does not count), to the turn's side, from LEAD m before the switch until
// the heading has turned 80 % of the way (`switches`: the line's, src/game.js data.switches, { s })
export function junctionTurns(route, switches) {
  const out = [];
  for (const sw of switches || []) {
    const h0 = route.heading(sw.s, 3);
    const ang = (s) => { const h = route.heading(s, 3); return Math.atan2(h0.hx * h.hy - h0.hy * h.hx, h0.hx * h.hx + h0.hy * h.hy); };
    const d = ang(sw.s + TURN_RUN);
    if (Math.abs(d) < TURN) continue;
    let s1 = sw.s;
    while (s1 < sw.s + 2 * TURN_RUN && Math.abs(ang(s1)) < 0.8 * Math.abs(d)) s1 += 2;
    out.push({ s0: sw.s - LEAD, s1, side: d > 0 ? 'left' : 'right' }); // (counter-clockwise on the map: left)
  }
  return out;
}

// A tram's indicators with its front at s: before and through a junction turn, or at a stop where passengers cross
// a car lane (`kerbStops`: the s where its front stops at each) while it brakes into it or stands there
export function indicating(turns, kerbStops, s, v, braking) {
  for (const t of turns) if (s >= t.s0 && s <= t.s1) return t.side;
  if (braking || v < 0.3) for (const k of kerbStops) if (s >= k - STOP_LEAD && s <= k + 3) return 'right';
  return null;
}
