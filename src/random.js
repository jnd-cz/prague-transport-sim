// Random numbers (issue #6). The simulation draws from one seeded stream per run, so a seed gives the
// same run every time: rules, traffic, walkers and obstacles alike. Math.random is left to what does not
// change the run (Three.js object ids, rain and snow particles, audio noise); before, those shared the
// benches' seeded Math.random with the simulation, so creating a mesh shifted every later draw.

// mulberry32: small, fast, good enough for gameplay. The state stays a 32-bit integer (the old copies
// let it grow as a float, which loses precision after ~5 million draws: a long traffic run gets there).
export function rng(seed) {
  let t = seed | 0;
  return () => {
    t = (t + 0x6d2b79f5) | 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

// The seed of the next run: `?seed=N` in the address, else `window.runSeed` (set by the benches and
// lints), else a fresh one. The game keeps it as `game.runSeed`, so any run can be replayed.
export function runSeed() {
  const q = new URLSearchParams(location.search).get('seed');
  if (q !== null && q !== '' && Number.isFinite(+q)) return +q >>> 0;
  if (Number.isFinite(window.runSeed)) return window.runSeed >>> 0;
  return (Math.random() * 4294967296) >>> 0;
}
