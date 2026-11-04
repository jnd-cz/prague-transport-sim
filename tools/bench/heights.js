// Top of rail in the game against the staged heights (#197): our route as driven (the profile) and the opposite track
// as its trams and drawn rails take it (trackAt), at every staged 5 m bin on runs without a step (the line data's
// `heights.staged`, tools/line_heights.py), and the drawn tracks where they meet: no junction with two heights.
// Seedless. On a loaded page: (await import('/tools/bench/heights.js')).run()

const P90 = 0.10;  // m: the game's track against the staged heights on runs without a step (#197 "Done when")
const JOIN = 0.5;  // m: a drawn track's end this near another drawn track meets it
const APART = 0.01; // m: heights further apart than this at a junction are two heights

const pct = (v, f) => { if (!v.length) return null; const a = v.slice().sort((x, y) => x - y); return +a[Math.min(a.length - 1, Math.floor(f * a.length))].toFixed(3); };

// the height of a drawn track at (x, y) if it passes within JOIN, and whether it is assembled there (its `zs` has a
// height within 4 m; else the old surface-plus-style heights fill it), else null
function heightOn(t, x, y) {
  let best = JOIN, z = null, s = 0, at = 0;
  const L = t.smooth;
  for (let i = 1; i < L.length; i++) {
    const a = L[i - 1], b = L[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
    if (Math.min(a[0], b[0]) <= x + JOIN && Math.max(a[0], b[0]) >= x - JOIN && Math.min(a[1], b[1]) <= y + JOIN && Math.max(a[1], b[1]) >= y - JOIN) {
      const u = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2)), d = Math.hypot(a[0] + dx * u - x, a[1] + dy * u - y);
      if (d < best) { best = d; z = t.z[i - 1] + (t.z[i] - t.z[i - 1]) * u; at = s + Math.sqrt(l2) * u; }
    }
    s += Math.sqrt(l2);
  }
  if (z === null) return null;
  const k = Math.round(at / 2), assembled = [k - 2, k - 1, k, k + 1, k + 2].every((j) => j < 0 || j >= t.zs.length || t.zs[j] != null);
  return { z, assembled };
}

export function run(game = window.game) {
  const d = game.data, st = d.heights?.staged;
  if (!st) return { checks: { heights: { count: 0, assembled: false } } };
  const ground = game.route.ground;
  const path = (st.path || []).map(([s, z]) => Math.abs(game.profile.height(s) - z));
  const back = game.backRoute ? (st.pathBack || []).map(([s, z]) => { const o = game.backRoute.at(s); return Math.abs(ground.trackAt(o.x, o.y) - z); }) : [];
  // junctions: each end of a drawn track with assembled heights against the other such tracks it meets
  const tracks = d.tracks.filter((t) => t.zs && t.z && t.smooth?.length > 1);
  const apart = [];
  let junctions = 0, onFill = 0;
  for (const t of tracks) {
    for (const end of [0, t.smooth.length - 1]) {
      const [x, y] = t.smooth[end], own = heightOn(t, x, y);
      for (const o of tracks) {
        if (o === t) continue;
        const h = heightOn(o, x, y);
        if (h === null) continue;
        if (!h.assembled || !own.assembled) { onFill++; continue; } // (the old heights fill one of them here)
        junctions++;
        const dz = Math.abs(h.z - own.z);
        if (dz > APART) apart.push({ x, y, mag: dz, info: `drawn tracks ${dz.toFixed(3)} m apart at a junction` });
      }
    }
  }
  const p = { n: path.length, p50: pct(path, 0.5), p90: pct(path, 0.9), p99: pct(path, 0.99) };
  const b = { n: back.length, p50: pct(back, 0.5), p90: pct(back, 0.9), p99: pct(back, 0.99) };
  const count = (p.p90 > P90) + (b.p90 > P90) + apart.length;
  const src = {};
  for (const v of game.profile.source || []) src[v] = (src[v] || 0) + game.profile.step;
  return { checks: { heights: { count, assembled: true, path: p, pathBack: b, junctions, onFill, apart: apart.slice(0, 50),
                                apartCount: apart.length, profileSource: src } } };
}
