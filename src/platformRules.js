// SPDX-License-Identifier: AGPL-3.0-or-later
// Where the tram platforms are and what kind each of our stops is (#419, #228): the rules' part of the platforms, as
// plain objects. The OSM platforms of both directions where the build placed them (tools/placement.py `place_platform`:
// the path, s0, s1, side, far and `ours`); whether the survey draws each (data/lineN.network.json `platforms`, `stops`,
// tools/network.py Stops). src/platforms.js draws them (buildPlatforms, buildStop) from what these return.

// An OSM platform's strip across its track: from 1.5 m off its centre out to its width (an OSM line usually runs along
// its middle, 2-3.5 m wide unless tagged: it reached over the car lane at Trojská, 5.1 m; an area gives its outer edge)
function across(pl) {
  const inner = 1.5, far = pl.far;
  return { inner, outer: pl.area ? Math.min(inner + 6, Math.max(inner + 2, far)) : inner + (pl.w || Math.max(2.4, Math.min(3.5, pl.gtfs ? far + 1 - inner : 2 * far - 2 * inner))) };
}

// The platforms of both directions: game.platforms ({ rt, back, s0, s1, side, inner, outer, ours, kerb, surveyed, zo,
// ... }: src/traffic.js reads it; zo, the street's surface at the outer kerb of each of the strip's cross-sections in cm,
// for the drawing). The stop type (Vienna: the kerb's offset) is the build's (tools/placement.py vienna).
export function platformsOf({ data, route, backRoute }) {
  const net = new Map((data.network?.platforms || []).map((r) => [r.i, r]));
  const platforms = [], also = [];
  for (const [i, pl] of (data.platforms || []).entries()) {
    if (!('path' in pl)) throw new Error(`line ${data.line} data has platforms without their placement: built before #419, rebuild it (tools/rebuild.py)`);
    if (!pl.path) continue;
    const rt = pl.path === 'back' ? backRoute : route;
    if (!rt) continue;
    const { s0, s1, side } = pl, { inner, outer } = across(pl);
    const ours = pl.ours ? { s0: pl.ours[0], s1: pl.ours[1] } : null;
    const N = net.get(i);
    if (!N) throw new Error(`line ${data.line}: platform ${pl.name} is not in the network (python -P -E tools/network.py --lines ${data.line})`);
    const plat = { rt, back: rt !== route, s0, s1, side, inner, outer, name: pl.name, code: pl.code, lines: pl.lines, stop: pl.stop, shelter: pl.shelter, ours, twin: !!pl.twin, unused: !!pl.unused, zs: N.zs / 100, zh: N.zh / 100, zo: N.zo };
    platforms.push(plat);
    if (pl.also) also.push([plat, pl.also]);
    // (a Vienna-type stop on the doors' side: no platform on the road, the sidewalk is the platform)
    plat.kerb = side < 0 ? pl.vienna ?? null : null;
    if (plat.kerb !== null) { plat.inner = plat.kerb; plat.outer = plat.kerb + 2; plat.surveyed = true; continue; }
    plat.surveyed = N.surveyed; // (its middle a platform, island or sidewalk of the survey)
  }
  // A platform both paths tie on (they run over its track the same way: line 9 from Řepy to Motol) serves both: the
  // other path gets it along its own s, not drawn again and without a sign of its own, its kerb and survey the drawn
  // one's (the user, 2026-11-14, #419: platforms belong to the track, docs/architecture.md)
  for (const [plat, list] of also) for (const a of list) {
    const art = a.path === 'back' ? backRoute : route;
    if (art) platforms.push({ ...plat, rt: art, back: art !== route, s0: a.s0, s1: a.s1, side: a.side, ours: null, twin: true, shared: true });
  }
  return platforms;
}

// One of our stops' kind, once from its stop point (src/game.js _stopZone, #694): stop.vienna (boarding from the
// sidewalk: stop.kerb its offset), stop.standIn (no platform of OSM's or the survey's there: a stand-in strip is drawn)
// and stop.shelterOuter (the shelter's outer edge where OSM has its platform, else null; the survey's where it draws
// the platform: OSM's island at Palackého náměstí is 6.2 m out, the survey's 4.5 m, and the shelter stood on the road).
export function stopOf({ stop, data, platforms }) {
  const N = data.network.stops[stop.i];
  // our platform: the OSM one (built with both directions' platforms) where it covers the stop zone, also one the
  // back path took that the route passes on its doors' side (`ours`), else none (a stand-in on the right: T3 doors are
  // on the right side only)
  const osm = platforms.find((p) => !p.back && p.side < 0 && p.s0 < stop.target - 8 && p.s1 > stop.target - 20)
    || platforms.find((p) => p.back && p.ours && p.ours.s0 < stop.target - 8 && p.ours.s1 > stop.target - 20);
  stop.kerb = osm ? osm.kerb : data.stops[stop.i].vienna ?? null;
  stop.vienna = stop.kerb !== null;
  stop.standIn = N.stand;
  stop.shelterOuter = osm ? N.outer / 100 : null;
}
