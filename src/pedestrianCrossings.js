// Surveyed pedestrian crossings and footways at track level (#146). Geometry is in city metres.
import { RAIL_HEAD } from './heights.js';
const CELL = 12, REACH = 7, MAX_CROSSING = 20, LEVEL_TOLERANCE = 0.4;
const CLEARANCE = 0.004, FULL_WIDTH = 1.15, FADE_WIDTH = 2.2, MAX_ALIGNMENT = 0.75;
const WALK = new Set(['sidewalk', 'island', 'paved', 'cycle']);

function inside(x, y, ring) {
  let yes = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) yes = !yes;
  }
  return yes;
}

// Chord of the polygon through this point; holes also bound the interval.
function chord(x, y, ux, uy, area) {
  if (!inside(x, y, area.ring) || area.holes.some((h) => inside(x, y, h))) return null;
  let lo = -Infinity, hi = Infinity;
  for (const ring of [area.ring, ...area.holes]) for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length], ex = b[0] - a[0], ey = b[1] - a[1];
    const den = ux * ey - uy * ex;
    if (Math.abs(den) < 1e-9) continue;
    const ax = a[0] - x, ay = a[1] - y, t = (ax * ey - ay * ex) / den, u = (ax * uy - ay * ux) / den;
    if (u < 0 || u > 1) continue;
    if (t <= 0) lo = Math.max(lo, t); else hi = Math.min(hi, t);
  }
  return Number.isFinite(lo) && Number.isFinite(hi) ? [lo, hi] : null;
}

// A crossing is short along the rails and at least as wide across them. A short but parallel
// sidewalk is not a crossing (the reported ZPS crossing is 6.3 m along and 15.2 m across).
function crossingSpan(x, y, ux, uy, area) {
  const along = chord(x, y, ux, uy, area), across = chord(x, y, -uy, ux, area);
  if (!along || !across || along[1] - along[0] > MAX_CROSSING ||
      across[1] - across[0] + 1 < along[1] - along[0]) return null;
  return { along, across };
}

class TrackIndex {
  constructor(tracks, tiltOf) {
    this.cells = new Map();
    for (const [id, t] of tracks.entries()) {
      const tilt = tiltOf(t);
      for (let i = 1; i < t.smooth.length; i++) {
        const a = t.smooth[i - 1], b = t.smooth[i], dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
        if (len < 0.01) continue;
        if (![t.z[i - 1], t.z[i], tilt[i - 1], tilt[i]].every(Number.isFinite)) continue;
        const seg = { id, a, dx, dy, len, z0: t.z[i - 1], z1: t.z[i], t0: tilt[i - 1], t1: tilt[i] };
        const x0 = Math.floor((Math.min(a[0], b[0]) - REACH) / CELL), x1 = Math.floor((Math.max(a[0], b[0]) + REACH) / CELL);
        const y0 = Math.floor((Math.min(a[1], b[1]) - REACH) / CELL), y1 = Math.floor((Math.max(a[1], b[1]) + REACH) / CELL);
        for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) {
          const key = `${x},${y}`;
          if (!this.cells.has(key)) this.cells.set(key, []);
          this.cells.get(key).push(seg);
        }
      }
    }
  }
  nearest(x, y, reach = REACH, ref = null) {
    const list = this.cells.get(`${Math.floor(x / CELL)},${Math.floor(y / CELL)}`) || [];
    let best = null, bestD = reach;
    for (const s of list) {
      const u = Math.max(0, Math.min(1, ((x - s.a[0]) * s.dx + (y - s.a[1]) * s.dy) / (s.len * s.len)));
      const px = s.a[0] + s.dx * u, py = s.a[1] + s.dy * u, d = Math.hypot(x - px, y - py);
      if (d > bestD) continue;
      const lat = (-s.dy * (x - px) + s.dx * (y - py)) / s.len;
      const z = s.z0 + (s.z1 - s.z0) * u + (s.t0 + (s.t1 - s.t0) * u) * lat / 0.72;
      if (ref !== null && Math.abs(z - ref) > LEVEL_TOLERANCE) continue; // an overpass is another level
      bestD = d;
      best = { x: px, y: py, d, z, ux: s.dx / s.len, uy: s.dy / s.len, id: s.id };
    }
    return best;
  }
}

// Lower only pedestrian surfaces that actually cross a matching-level track. Return raw height;
// the caller adds the surface's normal draw lift. Outside the track zone the source is preserved.
function lower(index, x, y, raw, lift) {
  const rail = index.nearest(x, y, FADE_WIDTH, raw + lift);
  if (!rail) return raw;
  const target = rail.z + RAIL_HEAD - CLEARANCE - lift;
  if (raw <= target) return raw;
  const k = Math.max(0, Math.min(1, (rail.d - FULL_WIDTH) / (FADE_WIDTH - FULL_WIDTH)));
  return target + (raw - target) * k * k * (3 - 2 * k);
}

// A surveyed patch alone can be a platform edge or a short parallel sidewalk. Require an
// independently mapped pedestrian way crossing the track nearby before reshaping it.
function pedestrianEvidence(roads) {
  const cells = new Map(), size = 25, reach = 5;
  for (const way of roads || []) {
    if (!way.z && !way.f) continue;
    for (let i = 1; i < way.p.length; i++) {
      const a = way.p[i - 1], b = way.p[i], seg = { a, b, zebra: !!way.z };
      for (let x = Math.floor((Math.min(a[0], b[0]) - reach) / size); x <= Math.floor((Math.max(a[0], b[0]) + reach) / size); x++)
        for (let y = Math.floor((Math.min(a[1], b[1]) - reach) / size); y <= Math.floor((Math.max(a[1], b[1]) + reach) / size); y++) {
          const key = `${x},${y}`; if (!cells.has(key)) cells.set(key, []); cells.get(key).push(seg);
        }
    }
  }
  return (site) => {
    let found = null;
    for (const seg of cells.get(`${Math.floor(site.x / size)},${Math.floor(site.y / size)}`) || []) {
      const dx = seg.b[0] - seg.a[0], dy = seg.b[1] - seg.a[1], l2 = dx * dx + dy * dy;
      if (l2 < 1e-9 || Math.abs((dx * site.ux + dy * site.uy) / Math.sqrt(l2)) >= MAX_ALIGNMENT) continue;
      const t = Math.max(0, Math.min(1, ((site.x - seg.a[0]) * dx + (site.y - seg.a[1]) * dy) / l2));
      if (Math.hypot(site.x - seg.a[0] - t * dx, site.y - seg.a[1] - t * dy) > reach) continue;
      if (seg.zebra) return 'zebra';
      found = 'footway';
    }
    return found;
  };
}

export function preparePedestrianCrossings(data, route, ground, tiltOf, liftOf) {
  const index = new TrackIndex(data.tracks, tiltOf), evidence = pedestrianEvidence(data.roads), decisions = { survey: [], review: [], footways: [],
    rule: { maxCrossing_m: MAX_CROSSING, levelTolerance_m: LEVEL_TOLERANCE, clearance_m: CLEARANCE,
            fullWidth_m: FULL_WIDTH, fadeWidth_m: FADE_WIDTH, maxFootwayAlignment: MAX_ALIGNMENT } };
  const dtm = ground.dtm;
  let reindex = false;
  if (dtm && !dtm.pedestrianCrossings) {
    for (const [areaId, area] of dtm.areas.entries()) {
      if (area.l < 0 || !WALK.has(area.c)) continue;
      const sites = [];
      const lift = liftOf(area.c, area.l);
      for (const tri of area.mesh) {
        const x = (tri[0][0] + tri[1][0] + tri[2][0]) / 3, y = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
        const z = (tri[0][2] + tri[1][2] + tri[2][2]) / 3;
        const rail = index.nearest(x, y, 6, z + lift);
        if (!rail || z + lift <= rail.z + RAIL_HEAD - CLEARANCE ||
            sites.some((s) => Math.hypot(s.x - rail.x, s.y - rail.y) < 3)) continue;
        const span = crossingSpan(rail.x, rail.y, rail.ux, rail.uy, area);
        if (!span) continue;
        const site = { x: rail.x + (span.along[0] + span.along[1]) * rail.ux / 2,
                     y: rail.y + (span.along[0] + span.along[1]) * rail.uy / 2, track: rail.id, ux: rail.ux, uy: rail.uy,
                     radius: (span.along[1] - span.along[0]) / 2 + 5, width: span.along[1] - span.along[0],
                     across: span.across[1] - span.across[0], heightDifference: z + lift - rail.z };
        site.evidence = evidence(site);
        if (!site.evidence) {
          if (!decisions.review.some((s) => s.area === areaId && Math.hypot(s.x - site.x, s.y - site.y) < 3))
            decisions.review.push({ area: areaId, ...site });
          continue;
        }
        sites.push(site);
      }
      if (!sites.length) continue;
      const mesh = [], adjusted = new Set();
      for (const tri of area.mesh) {
        const x = (tri[0][0] + tri[1][0] + tri[2][0]) / 3, y = (tri[0][1] + tri[1][1] + tri[2][1]) / 3;
        if (sites.some((s) => Math.hypot(s.x - x, s.y - y) <= s.radius + 4)) dtm._split(...tri, false, mesh, 0, 0.75);
        else mesh.push(tri);
      }
      for (const tri of mesh) for (const p of tri) {
        if (adjusted.has(p)) continue;
        adjusted.add(p);
        if (sites.some((s) => Math.hypot(s.x - p[0], s.y - p[1]) <= s.radius)) p[2] = lower(index, p[0], p[1], p[2], lift);
      }
      area.mesh = mesh;
      reindex = true;
      decisions.survey.push({ area: areaId, class: area.c, level: area.l, sites });
    }
    if (reindex) dtm.reindexGround();
    dtm.pedestrianCrossings = { survey: decisions.survey, review: decisions.review };
  } else if (dtm) ({ survey: decisions.survey, review: decisions.review } = dtm.pedestrianCrossings);
  ground.pedestrianCrossings = decisions;
  return {
    // Only a footway crossing a track at a substantial angle is treated as a crossing.
    footway(line, width, height, lift, name = null) {
      let crossing = null;
      for (let i = 1; i < line.length; i++) {
        const a = line[i - 1], b = line[i], dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
        if (len < 0.01) continue;
        const steps = Math.ceil(len / 2);
        for (let k = 0; k <= steps; k++) {
          const x = a[0] + dx * k / steps, y = a[1] + dy * k / steps;
          const rail = index.nearest(x, y, Math.min(REACH, width / 2 + 2), height(x, y) + lift);
          const alignment = rail && Math.abs((dx * rail.ux + dy * rail.uy) / len);
          if (rail && alignment < MAX_ALIGNMENT) { crossing = { x, y, track: rail.id, alignment }; break; }
        }
        if (crossing) break;
      }
      if (!crossing) return null;
      decisions.footways.push({ ...crossing, width, name });
      return (x, y) => lower(index, x, y, height(x, y), lift);
    },
  };
}
