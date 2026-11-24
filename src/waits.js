// SPDX-License-Identifier: AGPL-3.0-or-later
// Who waits for whom in the traffic (#560): every car, AI tram, walker and our tram notes whom it waits for and why
// (src/traffic.js: c.waitFor and c.why on a car, t.waitFor and t.stop.why on an AI tram, w.waitFor and w.why on a walker;
// our tram's from the autopilot's stop). This module reads those notes as one graph, an edge from each one waiting to
// the one it waits for, and finds:
// - circles: the strongly connected parts of two or more (Tarjan, "Depth-first search and linear graph algorithms",
//   SIAM J. Computing 1(2), 1972), each with the holds along it;
// - the head of each standing chain: following the waits from one standing to the first that stands for no one else
//   (a red light, a stop, a dwell) or that moves (a walker crossing, a tram going), and why that one stands.
// No Three.js and no DOM: plain objects in, plain objects out. The idea of typed holds and chain heads comes from the
// openOMSI study (docs/research/openomsi/traffic-and-people.md, `ai_traffic/deadlock.rs`, `stats.rs`), written anew.

// standing: below this speed (m/s) an agent counts as standing
export const STAND_V = 0.3;

// an agent's kind, for the reports
export function kindOf(a, ours) {
  if (a === ours) return 'our tram';
  if (a.kind === 'road') return 'car';
  if (a.walk !== undefined) return 'walker';
  return 'tram';
}

// the speed of an agent (a walker waiting at the kerb or held in one place stands)
export function speedOf(a, ours) {
  const k = kindOf(a, ours);
  if (k === 'car') return a.vNow ?? 0;
  if (k === 'walker') return a.waitKerb || a.leave ? 0 : a.v ?? 0;
  return a.v ?? 0;
}

// why an agent stands, as noted: a car's c.why (lead, junction, tram, light, curve, speed), an AI tram's t.stop.why,
// a walker's w.why, ours its own note
export function whyOf(a, ours) {
  const k = kindOf(a, ours);
  if (k === 'car' || k === 'walker' || k === 'our tram') return a.why ?? null;
  return a.stop?.why ?? null;
}

// The graph of agents `as` (each with .waitFor: another agent or null): its circles of two or more, each the list of
// its agents in the order of their waits, by Tarjan's algorithm (iterative: a chain may be long)
export function circles(as) {
  const index = new Map(), low = new Map(), on = new Set(), stack = [], out = [];
  let n = 0;
  const inGraph = new Set(as);
  for (const root of as) {
    if (index.has(root)) continue;
    const work = [[root, false]];
    while (work.length) {
      const [v, back] = work.pop();
      if (!back) {
        if (index.has(v)) continue;
        index.set(v, n); low.set(v, n); n++;
        stack.push(v); on.add(v);
        work.push([v, true]);
        const w = v.waitFor;
        if (w && inGraph.has(w)) {
          if (!index.has(w)) work.push([w, false]);
          else if (on.has(w)) low.set(v, Math.min(low.get(v), index.get(w)));
        }
      } else {
        const w = v.waitFor;
        if (w && inGraph.has(w) && on.has(w)) low.set(v, Math.min(low.get(v), low.get(w)));
        if (low.get(v) === index.get(v)) {
          const part = [];
          let x;
          do { x = stack.pop(); on.delete(x); part.push(x); } while (x !== v);
          if (part.length > 1) {
            // (in the order of their waits, from the one with the lowest id: the same circle reads the same way each step)
            const start = part.reduce((a, b) => ((a.id ?? 0) <= (b.id ?? 0) ? a : b));
            const ring = [start];
            for (let y = start.waitFor; y && y !== start && ring.length < part.length; y = y.waitFor) ring.push(y);
            out.push(ring);
          }
        }
      }
    }
  }
  return out;
}

// The head of the chain of waits from agent a: { head, why, kind, length, circle } where circle is true when the waits
// run in a circle (no head: the agent of the circle the chain comes to is given). Follows only standing agents.
export function chainHead(a, ours) {
  const seen = new Set();
  let x = a, length = 0;
  while (x.waitFor && speedOf(x, ours) < STAND_V && !seen.has(x)) {
    seen.add(x);
    x = x.waitFor;
    length++;
  }
  return { head: x, why: whyOf(x, ours), kind: kindOf(x, ours), length, circle: seen.has(x) };
}
