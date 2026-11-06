// The game's speed limits along the route and what sets them (#211). Seedless.
// On a loaded page, with a shift started: (await import('/tools/bench/speedLimits.js')).run()
//
// For every 5 m bin of the route: the limit in force and the rule that lowers it most (the first of the causes
// equal to it). Reported: km per limit and per cause, the km the game drives faster than data/truth.json's
// `max-speed` allows without a sign (untagged dedicated track), the km the 60 cap holds back, the curves under 25 m
// (`small-radius-speed`), and where a facing switch's slow stretch ends: the front's distance past the switch when
// the whole tram has left the limit.
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
    posted.push(Math.min(60, info.osm || (info.dedicated ? 60 : 50)));
    curve.push(route.curveSpeed(s));
    const g = game.profile.grade(s);
    grades.push(g < -0.06 ? 25 : g < -0.045 ? 35 : 99);
  }
  const switches = new Float32Array(n).fill(99);
  for (const w of game.switches) {
    const v = w.routeDiverging ? 15 : 30;
    for (let s = w.s - 4; s <= w.s + 14; s += STEP) {
      const i = Math.round(s / STEP);
      if (i >= 0 && i < n) switches[i] = Math.min(switches[i], v);
    }
  }
  return { curve, posted, grades, switches };
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
      out.push({ from, to: s, r: round(rMin, 1), v: route.curveSpeed((from + s) / 2), onSwitch });
      from = null; rMin = 1e9;
    }
  }
  return out;
}

// The front's distance past the switch when the tram of this length leaves the switch's own stretch (`own`), and
// when the limit in force first rises above the switch's speed, whatever else holds it (`any`, up to 200 m): the
// lowest bin under the whole tram, as Game.currentLimit.
function liftPast(game, w, length, switches) {
  const lim = game.limits, v = w.routeDiverging ? 15 : 30;
  let own = null, any = null;
  for (let d = 0; d < 200 && (own === null || any === null); d += 1) {
    let low = 99, ownBin = false;
    for (let s = w.s + d - length; s <= w.s + d + 0.1; s += STEP) {
      low = Math.min(low, lim.at(s));
      const i = Math.floor(s / STEP);
      if (Math.abs(i * STEP - w.s) <= 20 && switches[i] <= v && s >= w.s - 4) ownBin = true;
    }
    if (own === null && !ownBin) own = d;
    if (any === null && low > v) any = d;
  }
  return { own, any };
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
      },
    },
  };
}
