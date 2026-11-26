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

// the one agent a waits for, as noted (the default edges of the graph)
const waitsFor = (a) => (a.waitFor ? [a.waitFor] : []);

// The graph of agents `as`, an edge from each to every agent next(a) lists (by default its .waitFor): its circles of two
// or more, by Tarjan's algorithm (iterative: a chain may be long). A circle of one wait each is listed in the order of
// its waits from the agent with the lowest id; one where an agent waits for two of it, by id (the same circle reads the
// same way each step).
export function circles(as, next = waitsFor) {
  const index = new Map(), low = new Map(), on = new Set(), stack = [], out = [];
  let n = 0;
  const inGraph = new Set(as);
  const id = (a) => a.id ?? 0;
  for (const root of as) {
    if (index.has(root)) continue;
    const work = [[root, next(root), 0]];
    index.set(root, n); low.set(root, n); n++; stack.push(root); on.add(root);
    while (work.length) {
      const top = work[work.length - 1], [v, ws] = top;
      if (top[2] < ws.length) {
        const w = ws[top[2]++];
        if (!w || !inGraph.has(w)) continue;
        if (!index.has(w)) {
          index.set(w, n); low.set(w, n); n++; stack.push(w); on.add(w);
          work.push([w, next(w), 0]);
        } else if (on.has(w)) low.set(v, Math.min(low.get(v), index.get(w)));
        continue;
      }
      work.pop();
      if (work.length) { const u = work[work.length - 1][0]; low.set(u, Math.min(low.get(u), low.get(v))); }
      if (low.get(v) !== index.get(v)) continue;
      const part = [];
      let x;
      do { x = stack.pop(); on.delete(x); part.push(x); } while (x !== v);
      if (part.length < 2) continue;
      const set = new Set(part), start = part.reduce((a, b) => (id(a) <= id(b) ? a : b));
      const ring = [start];
      for (let y = start; ring.length <= part.length;) {
        const ins = next(y).filter((w) => set.has(w));
        if (ins.length !== 1 || ins[0] === start) break;
        ring.push((y = ins[0]));
      }
      out.push(ring.length === part.length ? ring : part.sort((a, b) => id(a) - id(b)));
    }
  }
  return out;
}

// Does o come from c's right (#560, the user, 2026-11-24: "the traffic rule that car on the right should go first")? Their
// poses { x, y, hx, hy }: o heads across c's way from right to left (its heading turned left of c's by 0.5 to π − 0.5,
// read as turnOf in src/traffic.js reads a turn) and stands on c's right, within `near` m.
export function fromRight(c, o, near = 25) {
  const dx = o.x - c.x, dy = o.y - c.y;
  if (Math.hypot(dx, dy) > near) return false;
  const ang = Math.atan2(c.hx * o.hy - c.hy * o.hx, c.hx * o.hx + c.hy * o.hy);
  return ang > 0.5 && ang < Math.PI - 0.5 && c.hx * dy - c.hy * dx < 0;
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
