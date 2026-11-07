// The game's speed limits along the route and what sets them (#211). Seedless.
// On a loaded page, with a shift started: (await import('/tools/bench/speedLimits.js')).run()
//
// For every 5 m bin of the route: the limit in force and the rule that lowers it most (the first of the causes
// equal to it). Reported: km per limit and per cause, the km the game drives faster than data/truth.json's
// `max-speed` allows without a sign (untagged dedicated track), the km the 60 cap holds back, the curves under 25 m
// (`small-radius-speed`), where a facing switch's slow stretch ends: the front's distance past the switch when
// the whole tram has left the limit, and what holds the limit last there (`heldBy`), with the km at that speed by
// cause (`km15`).
import { FROG, trackworkStretches } from '/src/speedRules.js';

const STEP = 5;
const SMALL_RADIUS = 25;   // m (data/truth.json `small-radius-speed`)

function round(v, k = 2) { return Math.round(v * 10 ** k) / 10 ** k; }

function kmBy(values) {
  const out = {};
  for (const v of values) out[v] = (out[v] || 0) + STEP;
  for (const k of Object.keys(out)) out[k] = round(out[k] / 1000);
  return out;
}

// the bins of a route's own rules, before switches and gradients (src/route.js speedLimits)
function causes(game) {
  const route = game.route, n = game.limits.values.length, grades = [], curve = [], posted = [];
  for (let i = 0; i < n; i++) {
    const s = i * STEP, info = route._speedInfo(s);
    posted.push(info.osm ? Math.min(info.osm, route.speedTop) : 50);
    curve.push(route.curveSpeed(s));
    const g = game.profile.grade(s);
    grades.push(g < -0.06 ? 25 : g < -0.045 ? 35 : 99);
  }
  const switches = new Float32Array(n).fill(99);
  for (const e of trackworkStretches(game.switches, game.data.trackwork, game.opts.speedFacts)) {
    for (let s = e.from; s <= e.to; s += STEP) {
      const i = Math.round(s / STEP);
      if (i >= 0 && i < n) switches[i] = Math.min(switches[i], e.v);
    }
  }
  return { curve, posted, grades, switches };
}

// the name of the street nearest a route position, for reading a place (data.roads[].n, tools/build_line.py)
function streetAt(game, s) {
  const p = game.route.at(s);
  let best = null, bd = 25;
  for (const r of game.data.roads) {
    if (!r.n) continue;
    for (let i = 1; i < r.p.length; i++) {
      const a = r.p[i - 1], b = r.p[i], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy || 1e-9;
      const t = Math.max(0, Math.min(1, ((p.x - a[0]) * dx + (p.y - a[1]) * dy) / l2));
      const d = Math.hypot(p.x - a[0] - dx * t, p.y - a[1] - dy * t);
      if (d < bd) { bd = d; best = r.n; }
    }
  }
  return best;
}

function stopsAround(game, s) {
  const st = game.data.stops;
  const k = st.filter((x) => x.s <= s).length;
  return `${st[Math.max(0, k - 1)]?.name} .. ${st[Math.min(st.length - 1, k)]?.name}`;
}

function curvesUnder(game, radius) {
  const route = game.route, out = [];
  let from = null, rMin = 1e9;
  for (let s = 0; s <= route.length; s += STEP) {
    const r = route.radiusAt(s);
    if (r < radius) {
      if (from === null) from = s;
      rMin = Math.min(rMin, r);
    } else if (from !== null) {
      const onSwitch = game.switches.some((w) => w.s > from - 15 && w.s < s + 15);
      out.push({ from, to: s, r: round(rMin, 1), v: route.curveSpeed((from + s) / 2), onSwitch,
                 street: streetAt(game, (from + s) / 2), between: stopsAround(game, (from + s) / 2) });
      from = null; rMin = 1e9;
    }
  }
  return out;
}

// The front's distance past the switch when the tram of this length leaves the restrictions of the first 20 m past the
// fork (`own`: the switch's stretch, and any trailing switch or diamond starting there, so at most 20 m + the tram), and
// when the limit in force first rises above the switch's speed, whatever else holds it (`any`, up to 200 m): the
// lowest bin under the whole tram, as Game.currentLimit.
function liftPast(game, w, length, switches) {
  const lim = game.limits, v = game.opts.speedFacts.facing;
  let own = null, any = null;
  for (let d = 0; d < 200 && (own === null || any === null); d += 1) {
    let low = 99, ownBin = false;
    for (let s = w.s + d - length; s <= w.s + d + 0.1; s += 1) {
      low = Math.min(low, lim.at(s));
      if (s <= w.s + 20 && s >= w.s - 4 && lim.restriction(s) <= v) ownBin = true;
    }
    if (own === null && !ownBin) own = d;
    if (any === null && low > v) any = d;
  }
  return { own, any };
}

// Why a bin stands at v or lower. `spilled`: only because speedLimits' window (15 m behind, 5 m ahead) carried a
// neighbour's limit here.
function whyLow(c, i, v) {
  if (c.switches[i] <= v) return 'trackwork';
  if (c.posted[i] <= v) return 'posted';
  if (c.curve[i] <= v) return 'curve';
  for (let j = i - 3; j <= i + 1; j++) if (c.posted[j] <= v) return 'posted, spilled';
  return 'curve, spilled';
}

// The metre that holds a tram longest past a fork: the one the rear leaves when the limit first rises (`any`).
function holder(game, w, any, length, c) {
  const lim = game.limits, v = game.opts.speedFacts.facing;
  if (any === null) return null;
  for (let s = w.s + any - 1 - length; s <= w.s + any; s += 1) {
    if (lim.at(s) > v) continue;
    const past = Math.round(s - w.s), frog = w.frog ?? FROG;
    if (lim.restriction(s) <= v) return { past, cause: past <= frog ? 'own switch' : 'trackwork' };
    return { past, cause: whyLow(c, Math.floor(s / STEP), v) };
  }
  return null;
}

function countBy(list) {
  const out = {};
  for (const k of list) if (k) out[k] = (out[k] || 0) + 1;
  return out;
}

function kmOf(bins) {
  const out = countBy(bins);
  for (const k of Object.keys(out)) out[k] = round(out[k] * STEP / 1000);
  return out;
}

export function run(game = window.game) {
  const lim = game.limits, n = lim.values.length, c = causes(game);
  const cause = [], values = [];
  for (let i = 0; i < n; i++) {
    const v = lim.values[i];
    values.push(v);
    cause.push(c.switches[i] <= v ? 'switch' : c.grades[i] <= v ? 'gradient' : c.posted[i] <= v ? 'posted' : 'curve');
  }
  const unsigned = [], capped = [];
  for (let i = 0; i < n; i++) {
    const info = game.route._speedInfo(i * STEP);
    if (!info.osm && info.dedicated && values[i] > 50) unsigned.push(i);
    if (info.osm > 60 && values[i] === 60) capped.push(i);
  }
  const small = curvesUnder(game, SMALL_RADIUS);
  const lengths = { single: game.tram.length };
  const lifts = game.switches.map((w) => ({ s: w.s, diverging: w.routeDiverging, one: liftPast(game, w, 15, c.switches), two: liftPast(game, w, 30, c.switches) }));
  const median = (a) => { const b = a.filter((v) => v !== null).sort((x, y) => x - y); return b.length ? b[b.length >> 1] : null; };
  return {
    checks: {
      speedLimits: {
        km: round(game.route.length / 1000),
        tramLength: lengths.single,
        byLimit: kmBy(values),
        byCause: kmBy(cause),
        gradientKm: round(cause.filter((k) => k === 'gradient').length * STEP / 1000),
        over50WithoutTag: round(unsigned.length * STEP / 1000),
        heldAt60: round(capped.length * STEP / 1000),
        smallRadius: small.map((k) => ({ ...k })),
        smallRadiusNotOnSwitch: small.filter((k) => !k.onSwitch).length,
        facingSwitches: game.switches.length,
        liftPast: { oneCar: median(lifts.map((l) => l.one.own)), twoCars: median(lifts.map((l) => l.two.own)),
                    twoCarsAny: median(lifts.map((l) => l.two.any)) },
        lifts,
        heldBy: countBy(game.switches.map((w, i) => holder(game, w, lifts[i].two.any, 30, c)?.cause)),
        lastSlowPast: median(game.switches.map((w, i) => holder(game, w, lifts[i].two.any, 30, c)?.past ?? null)),
        km15: kmOf(values.flatMap((v, i) => (v <= game.opts.speedFacts.facing ? [whyLow(c, i, v)] : []))),
        pastFrog: median(game.switches.map((w, i) => lifts[i].two.own - (w.frog ?? FROG))),
        trackwork: game.data.trackwork ? { trailing: game.data.trackwork.trailing.length, crossings: game.data.trackwork.crossings.length } : null,
      },
    },
  };
}
