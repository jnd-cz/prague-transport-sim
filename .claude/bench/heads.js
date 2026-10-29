// Dev prototype (not part of the game): what the surveyed traffic signal heads of Prague's technical map
// (data/lineN.dtmpoints.json, .claude/tools/dtm_points.py) are for, and how they stand relative to what
// they serve, against where the game puts its heads. In the page, after a shift has started:
//   const { run } = await import('/.claude/bench/heads.js'); const r = await run(); r.report
// Heads within 1.2 m are one pole. Each pole is labelled by its context (the nearest within reach wins,
// distances scaled by each reach):
//   tram  within 6 m of our track and 0-25 m after the stop point of one of our tram signals (s − 3)
//   car   within 12 m of an OSM car stop-line node (traffic_signals with direction), not behind it by more
//         than 6 m
//   ped   within 8 m of an OSM signalled pedestrian crossing node, or a signalled tram crossing node
//   other none of these (signals of the opposite tram direction, crossings OSM lacks, …)
// Measured per label: along / lateral offsets (m) from what it serves; the game's heads: distance to the
// nearest surveyed pole of the same label.
const q = (a, f) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(f * s.length))].toFixed(1); };
const stats = (a) => ({ n: a.length, p10: q(a, 0.1), median: q(a, 0.5), p90: q(a, 0.9) });

export async function run() {
  const game = window.game, traffic = window.traffic, R = game.route;
  const res = await fetch(`/data/line${game.data.line}.dtmpoints.json`);
  if (!res.ok) throw new Error('no dtmpoints file: run .claude/tools/dtm_points.py first');
  const pts = (await res.json()).points.filter((p) => p.k === 'signal' || p.k === 'signal_on_building');
  // heads -> poles
  const poles = [];
  for (const p of pts) {
    const o = poles.find((o) => Math.hypot(o.x - p.x, o.y - p.y) < 1.2);
    if (o) { o.heads++; o.x = (o.x * (o.heads - 1) + p.x) / o.heads; o.y = (o.y * (o.heads - 1) + p.y) / o.heads; } else poles.push({ x: p.x, y: p.y, heads: 1 });
  }
  const S = game.data.osmSignals || { stop: [], peds: [], tram: [] };
  const pedNodes = [...S.peds, ...S.tram.filter((c) => c.sig)];
  const tramSigs = game.signals.filter((s) => !s.gauntlet);
  for (const p of poles) {
    const cand = [];
    const n = R.nearest(p.x, p.y);
    if (n && n.d < 6) {
      for (const s of tramSigs) {
        const after = n.s - (s.s - 3);
        if (after > -2 && after < 25) { const h = R.at(n.s); cand.push({ label: 'tram', score: Math.abs(after - 6) / 25, along: after, lateral: (p.x - h.x) * h.hy - (p.y - h.y) * h.hx, ref: s }); }
      }
    }
    for (const o of S.stop) {
      const dx = p.x - o.x, dy = p.y - o.y, d = Math.hypot(dx, dy);
      if (d > 12) continue;
      const along = dx * o.hx + dy * o.hy;
      if (along < -6) continue;
      cand.push({ label: 'car', score: d / 12, along, lateral: dx * o.hy - dy * o.hx, ref: o });
    }
    for (const o of pedNodes) { const d = Math.hypot(p.x - o.x, p.y - o.y); if (d < 8) cand.push({ label: 'ped', score: d / 8, dist: d, ref: o }); }
    cand.sort((a, b) => a.score - b.score);
    Object.assign(p, cand[0] || { label: 'other' }, { onTrack: n ? +n.d.toFixed(1) : null });
  }
  const by = (l) => poles.filter((p) => p.label === l);
  // the game's heads against the surveyed poles of the same label (where the survey has one within 20 m)
  const near = (x, y, l) => { let b = null; for (const p of by(l)) { const d = Math.hypot(p.x - x, p.y - y); if (d < 20 && (!b || d < b)) b = d; } return b; };
  const gCar = [], gTram = [];
  const hm = traffic.lights?.group.children[0], M = new (window.THREE_?.Matrix4 || (await import('three')).Matrix4)();
  for (let i = 0; hm && i < hm.count; i++) { hm.getMatrixAt(i, M); const x = M.elements[12], y = -M.elements[14], d = near(x, y, 'car'); if (d !== null) gCar.push(d); }
  for (const s of tramSigs) { const v = s.mesh.getWorldPosition(s.mesh.position.clone()), d = near(v.x, -v.z, 'tram'); if (d !== null) gTram.push(d); }
  const report = {
    heads: pts.length, poles: poles.length,
    labels: Object.fromEntries(['tram', 'car', 'ped', 'other'].map((l) => [l, by(l).length])),
    headsPerPole: stats(poles.map((p) => p.heads)),
    car: { alongFromStopNode: stats(by('car').map((p) => p.along)), lateralRight: stats(by('car').map((p) => p.lateral)) },
    tram: { afterStopPoint: stats(by('tram').map((p) => p.along)), lateralRight: stats(by('tram').map((p) => p.lateral)) },
    ped: { distToCrossingNode: stats(by('ped').map((p) => p.dist)) },
    game: { carHeadToSurveyedCarPole: stats(gCar), tramSignalToSurveyedTramPole: stats(gTram), carHeadsWithSurvey: `${gCar.length} of ${hm?.count ?? 0}`, tramSignalsWithSurvey: `${gTram.length} of ${tramSigs.length}` },
  };
  return { report, poles };
}
