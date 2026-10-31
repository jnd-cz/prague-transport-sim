// The surveyed street surfaces as drawn (#21): waves along the street, seams between neighbouring
// areas, kerbs between road and sidewalk. Run from the command line:
//   python -P -E tools/headless.py --lines 17,22 --checks surfaces
// or in a page started with ?keepgeo: const { run } = await import('/tools/bench/surfaces.js'); await run()
// Before #21 (main f4cb8ea, line 17 / 22): waves 6.8 / 4.4 % of the samples, seams over 3 cm 13 / 3.9 %,
// kerb step median 0.06 m (the survey's one kerb line gave both sides one height).
const STREETS = new Set(['road', 'tram', 'parking', 'sidewalk', 'island', 'cycle', 'paved', 'platform']);
const ROAD = new Set(['road', 'tram', 'parking']), RAISED = new Set(['sidewalk', 'island', 'platform']);

export async function run() {
  const g = window.game, r = g.route, dtm = r.ground.dtm, T = r.ground.terrain;
  if (!dtm) return { checks: {} };
  // which area a point lies on: the triangle _hitTri picks, and the area that owns it
  const owner = new Map();
  dtm.areas.forEach((a, i) => { for (const t of a.mesh) owner.set(t, i); });
  const hit = (x, y) => {
    const ix = dtm.grid, k = ix.at(x, y);
    if (k < 0) return null;
    const gz = T.height(x, y);
    let best = null, bs = Infinity, bz = 0;
    for (let n = ix.start[k], e = ix.start[k + 1]; n < e; n++) {
      const id = ix.ids[n], t = ix.tris[id], p = t[0], q = t[1], u = t[2];
      const d = (q[1] - u[1]) * (p[0] - u[0]) + (u[0] - q[0]) * (p[1] - u[1]);
      if (Math.abs(d) < 1e-9) continue;
      const w1 = ((q[1] - u[1]) * (x - u[0]) + (u[0] - q[0]) * (y - u[1])) / d, w2 = ((u[1] - p[1]) * (x - u[0]) + (p[0] - u[0]) * (y - u[1])) / d, w3 = 1 - w1 - w2;
      if (w1 < -1e-6 || w2 < -1e-6 || w3 < -1e-6) continue;
      const z = w1 * p[2] + w2 * q[2] + w3 * u[2], sc = Math.abs(z - gz) - ix.val[id] * 0.05;
      if (sc < bs) { bs = sc; best = owner.get(t); bz = z; }
    }
    return best === null || best === undefined ? null : { a: best, z: bz, c: dtm.areas[best].c };
  };
  // waves: lint streetWaviness's samples (6-20 m either side, every 1 m), over 8 cm off the 21 m mean
  let wn = 0, waves = 0;
  for (const lat of [-20, -14, -9, -6, 6, 9, 14, 20]) {
    const zs = [], cs = [];
    for (let s = 0; s < r.length; s++) { const o = r.offset(s, lat), t = dtm.surfaceAt(o.x, o.y); zs.push(t ? t.z : null); cs.push(t ? t.c : null); }
    for (let i = 10; i < zs.length - 10; i++) {
      if (zs[i] === null || !STREETS.has(cs[i])) continue;
      let sum = 0, ok = true;
      for (let k = -10; k <= 10 && ok; k++) { if (zs[i + k] === null || cs[i + k] !== cs[i]) ok = false; else sum += zs[i + k]; }
      if (!ok) continue;
      wn++;
      if (Math.abs(zs[i] - sum / 21) > 0.08) waves++;
    }
  }
  // seams and kerbs: across the route every 0.25 m, a row every 4 m, where two areas meet
  const seams = [], kerbs = [];
  for (let s = 0; s < r.length; s += 4) {
    let prev = null;
    for (let lat = -25; lat <= 25; lat += 0.25) {
      const o = r.offset(s, lat), h = hit(o.x, o.y);
      if (h && prev && h.a !== prev.a) {
        // (street classes only: lawns and water meet at any height; over 1 m apart is another level)
        if (STREETS.has(h.c) && (h.c === prev.c || (ROAD.has(h.c) && ROAD.has(prev.c))) && Math.abs(h.z - prev.z) <= 1) seams.push(Math.abs(h.z - prev.z));
        else if (ROAD.has(h.c) && RAISED.has(prev.c)) kerbs.push(prev.z - h.z);
        else if (RAISED.has(h.c) && ROAD.has(prev.c)) kerbs.push(h.z - prev.z);
      }
      prev = h;
    }
  }
  const n = (a, f) => a.filter(f).length;
  const med = (a) => { const b = [...a].sort((x, y) => x - y); return b.length ? b[b.length >> 1] : 0; };
  return {
    checks: {
      waves: { count: waves, of: wn },
      seams3: { count: n(seams, (v) => v > 0.03), of: seams.length },
      seams10: { count: n(seams, (v) => v > 0.1), of: seams.length },
      flatKerbs: { count: n(kerbs, (v) => v < 0.05), of: kerbs.length },
      sunkKerbs: { count: n(kerbs, (v) => v < -0.02), of: kerbs.length },
      kerbMedianCm: { count: Math.round(med(kerbs) * 100) },
    },
  };
}
