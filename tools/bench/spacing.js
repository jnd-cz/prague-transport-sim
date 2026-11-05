// Track pair spacing at the pilot cross-sections (#20): our route against the opposite one, every 5 m, as the
// game drives them (after src/trackfix.js and the route smoothing). Seedless.
// On a loaded page: (await import('/tools/bench/spacing.js')).run()

// Sections by stop and route distance from it (along our direction). `expect`: the surveyed spacing, from
// docs/decisions/2026-10-27-track-source.md (Kobylisy north of Březiněveská: DTM 3.49-3.52 m, OSM 2.53-3.31 m,
// the game with its push-out 3.00-3.31 m); a section without it is reported only.
const SECTIONS = [
  { name: 'Kobylisy - Vozovna', stop: 'Kobylisy', from: 300, to: 500, expect: [3.49, 3.52], tol: 0.05 },
  { name: 'Palackého náměstí', stop: 'Palackého náměstí', from: -100, to: 100 },
];
const STEP = 5, REACH = 8;   // m between sections; farther than REACH there is no opposite track alongside
const KINK = 0.1;            // m: spacing changing more than this between neighbouring sections on a straight pair

function nearest(pts, x, y) {
  let best = Infinity;
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
    if (Math.min(a[0], b[0]) > x + REACH || Math.max(a[0], b[0]) < x - REACH ||
        Math.min(a[1], b[1]) > y + REACH || Math.max(a[1], b[1]) < y - REACH) continue;
    const t = Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / l2));
    best = Math.min(best, Math.hypot(x - a[0] - dx * t, y - a[1] - dy * t));
  }
  return best;
}

export function run(game = window.game) {
  const ours = game.route, back = game.backRoute, stops = game.data.stops;
  const sections = [];
  let count = 0;
  for (const sec of SECTIONS) {
    const stop = stops.find((s) => s.name === sec.stop);
    if (!stop || !back) continue;
    const spacing = [];
    for (let s = stop.s + sec.from; s <= stop.s + sec.to + 1e-6; s += STEP) {
      const p = ours.at(s), d = nearest(back.pts, p.x, p.y);
      spacing.push(d <= REACH ? Math.round(d * 1000) / 1000 : null);
    }
    const ds = spacing.filter((d) => d !== null);
    const out = sec.expect ? ds.filter((d) => d < sec.expect[0] - sec.tol || d > sec.expect[1] + sec.tol).length : 0;
    let kinks = 0;
    for (let i = 1; i < spacing.length; i++) if (spacing[i] !== null && spacing[i - 1] !== null && Math.abs(spacing[i] - spacing[i - 1]) > KINK) kinks++;
    if (sec.expect) count += out + kinks;
    sections.push({ name: sec.name, sections: spacing.length, alongside: ds.length,
                    min: ds.length ? Math.min(...ds) : null, max: ds.length ? Math.max(...ds) : null,
                    expect: sec.expect || null, outside: out, kinks, spacing });
  }
  return { checks: { spacing: { count, sections, spread: game.data.trackSpread || null } } };
}
