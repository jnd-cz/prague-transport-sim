// The game's speed limits along the route and what sets them (#211). Seedless.
// On a loaded page, with a shift started: (await import('/tools/bench/speedLimits.js')).run()
//
// For every 5 m bin of the route: the limit in force and the rule that lowers it most (the first of the causes
// equal to it). Reported: km per limit and per cause, the km the game drives faster than data/truth.json's
// `max-speed` allows without a sign (untagged dedicated track), the km the 60 cap holds back, the curves under 25 m
// (`small-radius-speed`), where a facing switch's slow stretch ends: the front's distance past the switch when
// the whole tram has left the limit, and what holds the limit last there (`heldBy`), with the km at that speed by
// cause (`km15`). `curveEnd`: how far past a curve's end its limit runs (`restriction-past`), and `descents`: the steep
// stretches and what is posted on them, now that a slope itself sets no speed.
import { FROG, trackworkStretches } from '/src/speedRules.js';

const STEP = 5;
const SMALL_RADIUS = 25;   // m (data/truth.json `small-radius-speed`)
const STEEP = -0.045;      // the steepest grades the game used to limit by themselves (#211)
const SHORT = 3;           // m: half the short radius estimate for a curve's end, against the game's 8

function round(v, k = 2) { return Math.round(v * 10 ** k) / 10 ** k; }

function kmBy(values) {
  const out = {};
  for (const v of values) out[v] = (out[v] || 0) + STEP;
  for (const k of Object.keys(out)) out[k] = round(out[k] / 1000);
  return out;
}

// the bins of a route's own rules, each its lowest, before the restrictions (src/route.js speedLimits)
function causes(game) {
  const route = game.route, n = game.limits.values.length, curve = new Float32Array(n).fill(99), posted = new Float32Array(n).fill(99);
  for (let m = 0; m < n * STEP; m++) {
    const i = Math.floor(m / STEP), info = route._speedInfo(m);
    posted[i] = Math.min(posted[i], info.osm ? Math.min(info.osm, route.speedTop) : 50);
    curve[i] = Math.min(curve[i], route.curveSpeed(m));
  }
  const switches = new Float32Array(n).fill(99);
  for (const e of trackworkStretches(game.switches, game.data.trackwork, game.opts.speedFacts)) {
    for (let m = Math.floor(e.from); m <= e.to; m++) {
      const i = Math.floor(m / STEP);
      if (i >= 0 && i < n) switches[i] = Math.min(switches[i], e.v);
    }
  }
  return { curve, posted, switches };
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
function liftPast(game, w, length) {
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

// Why a bin stands at v or lower. `spilled`: only because speedLimits carried a neighbour's limit here.
function whyLow(c, i, v) {
  if (c.switches[i] <= v) return 'trackwork';
  if (c.posted[i] <= v) return 'posted';
  if (c.curve[i] <= v) return 'curve';
  for (let j = i - 1; j <= i + 1; j++) if (c.posted[j] <= v) return 'posted, spilled';
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

function percentiles(list) {
  const a = list.filter((v) => v !== null).sort((x, y) => x - y), at = (p) => a[Math.min(a.length - 1, Math.floor(a.length * p))];
  return a.length ? { n: a.length, p10: at(0.1), median: at(0.5), p90: at(0.9) } : { n: 0 };
}

// How far past a curve's end its limit runs: for each stretch where the curve holds the limit under the posted speed, the
// metres from the last place a short radius estimate (±SHORT against the game's ±8, so it lags much less) still asks for
// less than the posted speed. The limit climbs along a transition curve as the radius grows, so `top` is where it is back
// at the posted speed, and `lowest` where it leaves its lowest speed, from the same end. Only stretches a restriction does not hold.
function curveEnds(game) {
  const route = game.route, lim = game.limits, L = Math.floor(route.length), top = [], lowest = [];
  const shortSpeed = (m) => {
    const a = route.heading(m - SHORT, SHORT), b = route.heading(m + SHORT, SHORT);
    const t = Math.acos(Math.max(-1, Math.min(1, a.hx * b.hx + a.hy * b.hy)));
    return route._designSpeed(m, t > 1e-4 ? 2 * SHORT / t : 1e6, false, route.cantAt(m));
  };
  const posted = (m) => { const o = route._speedInfo(m).osm; return o ? Math.min(o, route.speedTop) : 50; };
  for (let m = 1; m < L; m++) {
    const held = (x) => route.curveSpeed(x) < posted(x);
    if (lim.at(m) >= posted(m) || !held(m) && lim.at(m - 1) >= posted(m - 1)) continue;
    let e = m;
    while (e + 1 < L && lim.at(e + 1) < posted(e + 1)) e++;
    let free = true, low = 99, lowEnd = m;
    for (let x = m; x <= e; x++) {
      if (lim.restriction(x) < 99) free = false;
      if (lim.at(x) <= low) { low = lim.at(x); lowEnd = x; }
    }
    let end = null;
    for (let x = Math.min(L - 1, e + 15); x >= m; x--) if (shortSpeed(x) < posted(x)) { end = x; break; }
    if (free && end !== null) { top.push(e - end); lowest.push(lowEnd - end); }
    m = e;
  }
  return { top: percentiles(top), lowest: percentiles(lowest) };
}

// The steep stretches, at least 20 m, with what is posted on them.
function descents(game) {
  const route = game.route, out = [];
  for (let s = 0; s < route.length; s += STEP) {
    if (game.profile.grade(s) >= STEEP) continue;
    let e = s, g = 0;
    const posted = {};
    for (; e < route.length && game.profile.grade(e) < STEEP; e += STEP) {
      g = Math.min(g, game.profile.grade(e));
      const o = route._speedInfo(e).osm || 'none';
      posted[o] = (posted[o] || 0) + STEP;
    }
    if (e - s >= 20) out.push({ from: s, to: e, steepest: round(g * 100, 1), posted, limit: round(game.limits.at((s + e) / 2), 0), between: stopsAround(game, (s + e) / 2) });
    s = e;
  }
  return out;
}

export function run(game = window.game) {
  const lim = game.limits, n = lim.values.length, c = causes(game);
  const cause = [], values = [];
  for (let i = 0; i < n; i++) {
    const v = lim.values[i];
    values.push(v);
    cause.push(c.switches[i] <= v ? 'switch' : c.posted[i] <= v ? 'posted' : 'curve');
  }
  const unsigned = [], capped = [];
  for (let i = 0; i < n; i++) {
    const info = game.route._speedInfo(i * STEP);
    if (!info.osm && info.dedicated && values[i] > 50) unsigned.push(i);
    if (info.osm > 60 && values[i] === 60) capped.push(i);
  }
  const small = curvesUnder(game, SMALL_RADIUS);
  const lengths = { single: game.tram.length };
  const lifts = game.switches.map((w) => ({ s: w.s, diverging: w.routeDiverging, one: liftPast(game, w, 15), two: liftPast(game, w, 30) }));
  const median = (a) => { const b = a.filter((v) => v !== null).sort((x, y) => x - y); return b.length ? b[b.length >> 1] : null; };
  return {
    checks: {
      speedLimits: {
        km: round(game.route.length / 1000),
        tramLength: lengths.single,
        byLimit: kmBy(values),
        byCause: kmBy(cause),
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
        curveEnd: curveEnds(game),
        descents: descents(game),
      },
    },
  };
}
