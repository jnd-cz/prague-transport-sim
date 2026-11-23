// SPDX-License-Identifier: AGPL-3.0-or-later
// Cars and the trams' bodies where the car ways meet the tracks (#602). Static: every way a car drives through a
// junction (a lane, the connector, the next lane), against both tracks, with the tram's body as its bogies place it
// (articulated.js placeUnit: 14.0 x 2.5 m a car, swung out in curves). Seedless; on a page with a run started:
//   (await import('/tools/bench/giveway.js')).run()
// Counts, each with its places [x, y, s on our route]:
//   waitInBody    a spot where a car gives way (as src/traffic.js's give-way loop places it) that a passing body overlaps
//   letGoInBody   the body still over the car's way within LET_GO m of that spot when the loop lets the car go
//   skippedCross  a way that comes into a track's band shallow (the loop skips it: driving along) and then crosses it
//   skippedReach  a way that comes in shallow and passes within the body's reach: neither crosses nor runs on the rails
// and as context: the waits, the band entries by kind and how many the give-way covers, and the let-gos further on.
// The give-way spots and the let-go read the loop's rule (YIELD_GAP before the band, the group of tracks, the spot
// before a junction): a change of that rule changes them here too. The entries' kinds are geometry only.
import { placeUnit } from '../../src/articulated.js';
import { T3, CAR_PITCH } from '../../src/tram.js';

// the loop's (src/traffic.js): band 2.6 m each side of a track's centre, a car's front YIELD_GAP before it, half a car
// CAR_HALF; a car's box (src/models.js makeCar: 4.3 x 1.8 m) and a T3's body (14.0 x 2.5 m)
const BAND = 2.6, YIELD_GAP = 1.5, CAR_HALF = 2.2, LEVEL_APART = 2.5;
const CAR_L = 2.15, CAR_W = 0.9, BODY_L = 7.0, BODY_W = 1.25;
const STEP = 0.5;        // m along a path
const RAILS = 1.6;       // m: a car's middle this near a track's centre is on the rails (traffic.js _carsOnTracks)
const RAILS_RUN = 12;    // m: a way on the rails this far is a lane along them (the loop's `along`)
const CROSSES = 0.3;     // m: a way this near the centre line, or over to its other side, crosses the track
const LET_GO = 2;        // m: a conflict this near the waiting spot when let go is the car's first metres
const ALONG = 0.7;       // |cos| at the band's edge from which the loop takes a way for driving along the track

const box = (x, y, hx, hy, l, w) => ({ x, y, hx, hy, l, w });

// separation of two boxes (separating axes): > 0 apart by that much, < 0 overlapping by that much
export function sep(a, b) {
  let best = -Infinity;
  for (const [ax, ay] of [[a.hx, a.hy], [-a.hy, a.hx], [b.hx, b.hy], [-b.hy, b.hx]]) {
    const r = (q) => q.l * Math.abs(q.hx * ax + q.hy * ay) + q.w * Math.abs(-q.hy * ax + q.hx * ay);
    const d = Math.abs((b.x - a.x) * ax + (b.y - a.y) * ay) - r(a) - r(b);
    if (d > best) best = d;
  }
  return best;
}

// a tram's bodies with its front at route position sF: one box per car, placed by its running gear
export function bodies(rt, sF, cars = 1) {
  const at = (q) => { const p = rt.at(q); return [p.x, p.y, 0, 0]; }, out = [];
  for (let k = 0; k < cars; k++) {
    const s = sF - k * CAR_PITCH;
    if (s - T3.length < -1 || s > rt.length + 1) continue;
    const p = placeUnit(T3, s, at).sections[0];
    out.push(box(p.p[0], p.p[1], Math.sin(p.yaw), -Math.cos(p.yaw), BODY_L, BODY_W));
  }
  return out;
}

export const carBox = (q) => box(q.x, q.y, q.hx, q.hy, CAR_L, CAR_W);

// the side of route rt's centre line a point is on (+ left of its direction), and how far
function side(rt, n, q) {
  const p = rt.at(n.s);
  return p.hx * (q.y - p.y) - p.hy * (q.x - p.x);
}

// where a path is in a track's band, per track: [{ rt, sIn, sOut, sxIn, cosIn, minD, sides: [first, last], flips,
// startsIn, endsIn }] (cached on the path)
export function stretches(path, tracks) {
  if (path._gwStretches) return path._gwStretches;
  const out = [];
  for (const rt of tracks) {
    let cur = null;
    for (let s = 0; ; s = Math.min(path.length, s + STEP)) {
      const q = path.at(s), n = rt.nearest(q.x, q.y), inBand = !!n && n.d < BAND;
      if (inBand) {
        const sd = Math.sign(side(rt, n, q)) || 1;
        if (!cur) {
          const h = rt.at(n.s);
          cur = { rt, sIn: s, sOut: path.length, sxIn: n.s, sxOut: n.s, cosIn: Math.abs(q.hx * h.hx + q.hy * h.hy), minD: n.d, sides: [sd, sd], flips: 0, startsIn: s === 0, endsIn: true, at: [q.x, q.y] };
          out.push(cur);
        }
        if (sd !== cur.sides[1] && n.d > 0.05) cur.flips++;
        if (n.d > 0.05) cur.sides[1] = sd;
        cur.minD = Math.min(cur.minD, n.d);
        cur.sxOut = n.s;
      } else if (cur) {
        cur.sOut = s; cur.endsIn = false; cur = null;
      }
      if (s >= path.length) break;
    }
  }
  return (path._gwStretches = out);
}

// a way: [{ path, off, conn, hf }]: the point at distance d along it (past its ends straight on)
export function wayAt(seq, d) {
  for (let i = seq.length - 1; i >= 0; i--) if (d >= seq[i].off || i === 0) {
    const { path, off } = seq[i], ls = d - off, q = path.at(Math.max(0, Math.min(path.length, ls)));
    const e = ls < 0 ? ls : ls > path.length && i === seq.length - 1 ? ls - path.length : 0;
    return { x: q.x + q.hx * e, y: q.y + q.hy * e, hx: q.hx, hy: q.hy, k: i };
  }
  return null;
}

// a way's band stretches (pieces of consecutive paths joined), each with its kind: cross, rails, reach or clear
export function wayStretches(seq, tracks) {
  const out = [];
  for (const piece of seq) {
    for (const st of stretches(piece.path, tracks)) {
      const prev = out.findLast((o) => o.rt === st.rt);
      const dIn = piece.off + st.sIn, dOut = piece.off + st.sOut;
      if (prev && prev.endsIn && st.startsIn && Math.abs(prev.dOut - dIn) < 1e-6) {
        prev.flips += st.flips + (prev.sides[1] !== st.sides[0] ? 1 : 0);
        prev.sides[1] = st.sides[1]; prev.dOut = dOut; prev.endsIn = st.endsIn; prev.sxOut = st.sxOut;
        prev.minD = Math.min(prev.minD, st.minD);
        continue;
      }
      out.push({ ...st, sides: [...st.sides], dIn, dOut, k: seq.indexOf(piece) });
    }
  }
  // (leaving the band on the other side: across; along the rails RAILS_RUN m or more: on them, also where the way ends
  // there; over to the centre line and back to the same side: across it too, the tram's way is driven over. The rest
  // is judged by the body's reach, reach())
  for (const w of out) {
    const long = w.dOut - w.dIn >= RAILS_RUN && w.minD < RAILS, over = w.flips > 0 || w.minD < CROSSES;
    w.kind = !w.endsIn && w.sides[0] !== w.sides[1] ? 'cross' : long ? 'rails' : over ? 'cross' : null;
  }
  return out;
}

// least separation between a car on the way in [dIn, dOut] and a tram's body passing there (centred about each point)
export function reach(seq, w) {
  let least = Infinity, where = null;
  for (let d = w.dIn; d <= w.dOut + 1e-6; d += 1) {
    const q = wayAt(seq, d), n = w.rt.nearest(q.x, q.y);
    if (!n) continue;
    const car = carBox(q);
    for (const dc of [-7, -3.5, 0, 3.5, 7]) {
      for (const b of bodies(w.rt, n.s + T3.length / 2 + dc, 1)) {
        const v = sep(car, b);
        if (v < least) { least = v; where = q; }
      }
    }
  }
  return { least, where };
}

export function run(traffic = window.run.traffic, game = window.run.game) {
  const T = traffic, route = T.route, back = T.back, tracks = [route, back].filter(Boolean);
  const prof = T.ground.profile;
  const ourCars = game.tram.cars || 1, aiCars = game.line === '23' ? 1 : 2; // (traffic.js _newTram: two-car sets, 23 one)
  const ourS = (x, y) => { const o = route.nearest(x, y); return o && o.d < 10 ? o.s : null; };
  const r1 = (v) => Math.round(v * 10) / 10, r2 = (v) => Math.round(v * 100) / 100;
  const place = (x, y) => { const s = ourS(x, y); return [r1(x), r1(y), s === null ? null : Math.round(s)]; };
  // (a way on another level than the track there: the road in a tunnel under it, on a bridge over it, the loop's level
  // test; and where our track passes over the road on a bridge)
  const apart = (piece, q) => {
    const s = ourS(q.x, q.y);
    if (s === null) return false;
    if (prof.overBridge && prof.overBridge(s)) return true;
    return !!piece.hf && Math.abs(piece.hf(q.x, q.y) - prof.height(s)) > LEVEL_APART;
  };
  const lanes = T.roads.flatMap((r) => r.lanes);
  const ways = [];
  for (const a of lanes) {
    const A = { path: a.path, off: 0, conn: false, hf: a.road.hf };
    const nb = T.nextLanes(a);
    if (!nb.length) ways.push({ seq: [A], tag: `lane ${a.id}` });
    for (const b of nb) {
      const cn = T.connector(a, b), B = { path: b.path, conn: false, hf: b.road.hf };
      const seq = [A];
      let off = a.path.length;
      if (cn) {
        seq.push({ path: cn.path, off, conn: true, hf: cn.hf });
        // (a car already in the junction when the tram comes: its way starts on the connector)
        ways.push({ seq: [{ path: cn.path, off: 0, conn: true, hf: cn.hf }, { ...B, off: cn.path.length }], tag: `in ${cn.id}`, inJunction: true });
        off += cn.path.length;
      }
      seq.push({ ...B, off });
      ways.push({ seq, tag: `${a.id}>${b.id}` });
    }
  }

  const checks = { waitInBody: { count: 0, at: [], depth: [], byRule: {} }, letGoInBody: { count: 0, at: [] },
    skippedCross: { count: 0, at: [] }, skippedReach: { count: 0, at: [], depth: [] } };
  const kinds = { cross: 0, rails: 0, reach: 0, clear: 0 }, covered = { cross: 0, rails: 0, reach: 0, clear: 0 };
  let waits = 0, letGoLater = 0;
  const seenEntry = new Set(), seenWait = new Set();
  for (const { seq, tag, inJunction } of ways) {
    // the loop's crossings on this way (src/traffic.js: _trackCrossings per path, one copy of each, groups)
    const xs = [];
    seq.forEach((piece, k) => { for (const x of T._trackCrossings(piece.path)) xs.push({ dC: piece.off + x.sIn, dOut: piece.off + x.sOut, sx: x.sx, rt: x.rt, k }); });
    xs.sort((a, b) => a.dC - b.dC);
    for (let i = xs.length - 1; i > 0; i--) if (xs.slice(0, i).some((o) => o.rt === xs[i].rt && Math.abs(o.sx - xs[i].sx) < 4)) xs.splice(i, 1);
    for (let i = 0; i < xs.length; i++) {
      const g = i > 0 && xs[i].dC - xs[i - 1].g.dOut < 2 * CAR_HALF + 2 * YIELD_GAP ? xs[i - 1].g : { dC: xs[i].dC, dOut: xs[i].dOut, k: xs[i].k };
      g.dOut = Math.max(g.dOut, xs[i].dOut); xs[i].g = g;
    }

    // the entries into a band, by kind, and whether the loop gives way there
    if (!inJunction) {
      for (const w of wayStretches(seq, tracks)) {
        if (w.dIn <= 0) continue; // (the way comes in already on it: the way before this lane's)
        const piece = seq[w.k], q0 = wayAt(seq, w.dIn);
        if (apart(piece, q0)) continue;
        const key = `${w.rt === route ? 'o' : 'b'}${Math.round(w.sxIn)} ${Math.round(q0.x)},${Math.round(q0.y)}`;
        if (seenEntry.has(key)) continue;
        seenEntry.add(key);
        let kind = w.kind, rr = null;
        if (!kind) { rr = reach(seq, w); kind = rr.least < 0 ? 'reach' : 'clear'; }
        kinds[kind]++;
        const cov = xs.some((x) => x.rt === w.rt && x.dC >= w.dIn - 1 && x.dC <= w.dOut);
        if (cov) covered[kind]++;
        if (!cov && w.cosIn >= ALONG && kind === 'cross') { checks.skippedCross.count++; checks.skippedCross.at.push(place(q0.x, q0.y)); }
        if (!cov && w.cosIn >= ALONG && kind === 'reach') { checks.skippedReach.count++; checks.skippedReach.at.push(place(rr.where.x, rr.where.y)); checks.skippedReach.depth.push(r2(-rr.least)); }
      }
    }

    // where the loop has the car wait, against the passing body; and the body when it lets the car go
    for (const x of xs) {
      let front = x.g.dC - YIELD_GAP, rule = inJunction ? 'inJunction' : 'band';
      const k = x.g.k, J = seq[k - 1];
      if (J && J.conn && J.off > 0 && front - 2 * CAR_HALF < seq[k].off) { front = J.off - 1; rule = 'junction'; }
      // (on the first lane, not wholly on it: a car there is on the way of the lane before)
      if (!inJunction && k === 0 && front - 2 * CAR_HALF < 0) continue;
      if (inJunction && front - CAR_HALF < 0) continue;
      const qc = wayAt(seq, x.dC), piece = seq[x.k];
      if (apart(piece, qc)) continue;
      const car = carBox(wayAt(seq, front - CAR_HALF));
      const key = `${x.rt === route ? 'o' : 'b'}${Math.round(x.sx)} ${Math.round(car.x)},${Math.round(car.y)}`;
      if (seenWait.has(key)) continue;
      seenWait.add(key);
      waits++;
      const cars = x.rt === route ? ourCars : aiCars, len = T3.length * cars;
      let wait = Infinity;
      for (let sF = x.sx - 20; sF <= x.sx + 40; sF += 0.5) for (const b of bodies(x.rt, sF, cars)) wait = Math.min(wait, sep(car, b));
      if (wait < 0) {
        checks.waitInBody.count++; checks.waitInBody.at.push(place(car.x, car.y)); checks.waitInBody.depth.push(r2(-wait));
        checks.waitInBody.byRule[rule] = (checks.waitInBody.byRule[rule] || 0) + 1;
      }
      // (let go once the tram's front is its length and 2 m past the crossing: the loop's onBody)
      const tb = bodies(x.rt, x.sx + len + 2, cars);
      let rel = Infinity, relAt = null;
      for (let d = front - CAR_HALF; d <= x.g.dOut + CAR_HALF + 0.5; d += 0.5) {
        const cb = carBox(wayAt(seq, d));
        for (const b of tb) { const v = sep(cb, b); if (v < rel) { rel = v; relAt = d - (front - CAR_HALF); } }
      }
      if (rel < 0 && relAt <= LET_GO) { checks.letGoInBody.count++; checks.letGoInBody.at.push(place(car.x, car.y)); }
      else if (rel < 0) letGoLater++;
    }
  }
  return { checks: { ...checks, waits, letGoLater, ways: ways.length, entries: kinds, covered,
    // (the depths sorted, deepest first, for the summary)
    deepest: { wait: checks.waitInBody.depth.slice().sort((a, b) => b - a).slice(0, 5), reach: checks.skippedReach.depth.slice().sort((a, b) => b - a).slice(0, 5) } } };
}
