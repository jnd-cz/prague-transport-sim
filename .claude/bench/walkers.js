// Dev check (not part of the game): pedestrians on the footway network. In the page, after a shift
// has started: const { run } = await import('/.claude/bench/walkers.js'); run(seconds)
// The tram stands; only the traffic is stepped, with the camera over the tram. Counts: doors walked
// out of / into, faded away far off, link walks taken, dead-end turns, U-turns (more than 120° within
// 0.8 m of walking, link walks included) and metres walked per U-turn.
export function run(seconds = 180) {
  const game = window.game, traffic = window.traffic, camera = window.camera;
  window.headless = true; game.paused = true;
  const q0 = game.route.at(game.tram.s);
  camera.position.set(q0.x, 50, -q0.y);
  const h = 1 / 30, last = new Map();
  const st = { outs: 0, ins: 0, fadedFar: 0, links: 0, deadEnds: 0, uTurns: 0, metres: 0 };
  for (let k = 0; k < seconds * 30; k++) {
    const pre = traffic.slots ? traffic.slots.map((w) => w && { w, walk: w.walk, dir: w.dir, door: w.door }) : [];
    traffic.update(h, camera, k % 4 === 0);
    traffic.slots.forEach((w, i) => {
      const b = pre[i];
      if (b && b.w !== w) { if (b.door && !b.door.out) st.ins++; else st.fadedFar++; }
      if (!w) return;
      if (!b || b.w !== w) { if (w.door?.out) st.outs++; return; }
      if (b.walk !== w.walk) st.links++;
      else if (b.dir !== w.dir && !w.door) st.deadEnds++;
      if (w.door || w.x === undefined) return;
      const L = last.get(w);
      if (!L) { last.set(w, { x: w.x, y: w.y }); return; }
      const dx = w.x - L.x, dy = w.y - L.y, d = Math.hypot(dx, dy);
      if (d < 0.8) return;
      st.metres += d;
      if (L.hx !== undefined && (dx * L.hx + dy * L.hy) / d < -0.5) st.uTurns++;
      last.set(w, { x: w.x, y: w.y, hx: dx / d, hy: dy / d });
    });
  }
  return { ...st, metres: Math.round(st.metres), metresPerUTurn: Math.round(st.metres / Math.max(1, st.uTurns)), live: traffic.slots.filter(Boolean).length };
}
