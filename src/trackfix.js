// Track axes from OSM sometimes come too close together: two tracks of a double-track line 2.1 m
// apart (line 17 before the Vyšehrad tunnel), where two T3s (2.5 m wide) could not pass. Where the
// opposite direction's track runs alongside ours (anti-parallel, between 0.5 m and MIN apart, at least
// 40 m from any switch), its axis is pushed out to MIN, blended over ±20 m; the drawn tracks that are
// that track move with it. Our own route stays where it is (every stop, signal and profile is on it).
// Interlaced track (a gauntlet: under 1.8 m, Letenská 0.7 m) and 40 m around it are left alone.
const MIN = 3.0, BLEND = 20, SWITCH_CLEAR = 40;

// points every <= step m along a polyline (a long OSM segment has no vertex where it comes too close)
function densify(line, step = 4) {
  const out = [line[0]];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1], b = line[i], n = Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / step);
    for (let k = 1; k <= n; k++) out.push([a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n]);
  }
  return out;
}

export function spreadTracks(data) {
  if (!data.pathBack || data.pathBack.length < 2) return { moved: 0, min: null };
  data.pathBack = densify(data.pathBack);
  for (const t of data.tracks || []) t.p = densify(t.p);
  const ours = data.path, back = data.pathBack;
  // our path: cumulative s and a 20 m grid of segments
  const acc = [0];
  for (let i = 1; i < ours.length; i++) acc.push(acc[i - 1] + Math.hypot(ours[i][0] - ours[i - 1][0], ours[i][1] - ours[i - 1][1]));
  const grid = new Map();
  for (let i = 1; i < ours.length; i++) {
    const a = ours[i - 1], b = ours[i];
    for (let x = Math.floor(Math.min(a[0], b[0]) / 20); x <= Math.floor(Math.max(a[0], b[0]) / 20); x++) {
      for (let y = Math.floor(Math.min(a[1], b[1]) / 20); y <= Math.floor(Math.max(a[1], b[1]) / 20); y++) {
        const k = x * 100003 + y;
        if (!grid.has(k)) grid.set(k, []);
        grid.get(k).push(i);
      }
    }
  }
  const nearest = (x, y) => {
    let best = null;
    for (let gx = Math.floor(x / 20) - 1; gx <= Math.floor(x / 20) + 1; gx++) for (let gy = Math.floor(y / 20) - 1; gy <= Math.floor(y / 20) + 1; gy++) {
      for (const i of grid.get(gx * 100003 + gy) || []) {
        const a = ours[i - 1], b = ours[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
        const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2));
        const px = a[0] + dx * t, py = a[1] + dy * t, d = Math.hypot(x - px, y - py);
        if (!best || d < best.d) { const l = Math.sqrt(l2); best = { d, s: acc[i - 1] + l * t, px, py, hx: dx / l, hy: dy / l }; }
      }
    }
    return best;
  };
  const switches = (data.switches || []).map((w) => w.s ?? w);
  // the push each back point needs (along our normal, away from our track)
  const bacc = [0];
  for (let i = 1; i < back.length; i++) bacc.push(bacc[i - 1] + Math.hypot(back[i][0] - back[i - 1][0], back[i][1] - back[i - 1][1]));
  const near = back.map(([x, y]) => nearest(x, y));
  const gauntlet = bacc.filter((_, i) => near[i] && near[i].d < 1.8);
  const need = back.map(([x, y], i) => {
    const n = near[i];
    if (!n || n.d >= MIN || gauntlet.some((s) => Math.abs(s - bacc[i]) < SWITCH_CLEAR)) return null;
    const j = Math.min(back.length - 1, i + 1), k = Math.max(0, i - 1);
    const bx = back[j][0] - back[k][0], by = back[j][1] - back[k][1], bl = Math.hypot(bx, by) || 1;
    if ((bx * n.hx + by * n.hy) / bl > -0.97) return null; // not alongside, the other way
    if (switches.some((s) => Math.abs(s - n.s) < SWITCH_CLEAR)) return null;
    const ux = (x - n.px) / n.d, uy = (y - n.py) / n.d;
    return { push: MIN - n.d, ux, uy };
  });
  // blended displacement: the largest push within BLEND m, tapering linearly
  const disp = back.map((_, i) => {
    let best = null;
    for (let j = 0; j < back.length; j++) {
      if (!need[j]) continue;
      const d = Math.abs(bacc[j] - bacc[i]);
      if (d > BLEND) continue;
      const w = need[j].push * (1 - d / BLEND);
      if (!best || w > best.w) best = { w, ux: need[j].ux, uy: need[j].uy };
    }
    return best ? [best.ux * best.w, best.uy * best.w] : null;
  });
  let moved = 0, minD = Infinity;
  for (const n of need) if (n) minD = Math.min(minD, MIN - n.push);
  // the drawn tracks lying on the back path move with it (same displacement as the nearest back point)
  const cell = new Map();
  back.forEach((p, i) => { if (disp[i]) { const k = Math.round(p[0]) * 100003 + Math.round(p[1]); if (!cell.has(k)) cell.set(k, []); cell.get(k).push(i); } });
  for (const t of data.tracks || []) {
    for (const p of t.p) {
      let bi = -1, bd = 0.6;
      for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
        for (const i of cell.get((Math.round(p[0]) + dx) * 100003 + Math.round(p[1]) + dy) || []) {
          const d = Math.hypot(back[i][0] - p[0], back[i][1] - p[1]);
          if (d < bd) { bd = d; bi = i; }
        }
      }
      if (bi >= 0) { p[0] += disp[bi][0]; p[1] += disp[bi][1]; }
    }
  }
  back.forEach((p, i) => { if (disp[i]) { p[0] += disp[i][0]; p[1] += disp[i][1]; moved++; } });
  return { moved, min: Number.isFinite(minD) ? minD : null };
}
