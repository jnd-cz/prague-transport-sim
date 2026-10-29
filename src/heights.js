// What each height means (docs/decisions/2026-10-29-what-each-height-means.md, #9). All heights are Bpv
// metres. The track profile is the top of rail (TOR): the tram's wheels stand on it, rails, bed and
// catenary are measured from it. Until 2026-10-29 the profile was the street under the track, with the
// rail heads drawn 0.26 m over it and the street beside them pressed to +0.14 m: the whole track zone
// stood 14-26 cm proud of the surveyed road.

// top of rail over the surface around the track, by construction (data/truth.json trackStyleKinds).
// Embedded and panels are measured flush (Karlovo náměstí - I. P. Pavlova: the lanes 4.5 m off are level
// with the axis); grass (the high variant, ČVUT's green-track study) and ballast (rail and plate over the
// sleeper tops) are design values until a track-axis height or a photo measures them.
export const TOR_OVER_SURFACE = { embedded: 0, panels: 0, grass: 0.04, ballast: 0.17 };

// The drawn layers just around top of rail, apart enough not to flicker: the rail heads a little over
// it, the bed (or the street of an embedded track) a little under, the street beside the bed under that.
export const RAIL_HEAD = 0.012; // drawn rail head over TOR
export const BED_BELOW = 0.006; // bed surface under the surface level the style gives
// The street next to the track, as stored: drawn 0.012 m under the surface level (below the bed). The
// surveyed areas are drawn up to 0.04 m over their stored vertices (terrain.js DTM_LIFT), the OSM road
// ribbons 0.12 m over the ground (world.js), so each is stored that much lower again.
export const STREET_BELOW = 0.012 + 0.04; // a surveyed street vertex next to the track, under the surface level
export const ROAD_BELOW = 0.012 + 0.12; // the ground under an OSM road ribbon next to the track

const RAMP = 15; // m: a style's offset blends in and out over this at the ends of its section

// The line's track styles, as functions of the route position: `at(s)` the style ('panels' where nothing
// says otherwise), `lift(s)` its top of rail over the surface, blended at the section ends. From the
// user's marks (data/truth.json trackStyles, by stops so they hold in any frame) and from the survey:
// a green area under the track axis for 20 m and more is grass track (line 22 Koh-i-noor - Slavia,
// whose bank fell 0.5 m across the rails). The user's marks win where they overlap.
export function trackStyles(truth, data, surveyClass = null, length = 0) {
  const secs = [];
  for (const t of truth?.trackStyles || []) {
    if (String(t.line) !== String(data.line)) continue;
    const a = data.stops.findIndex((st) => st.name === t.from);
    const b = a < 0 ? -1 : data.stops.findIndex((st, i) => i > a && st.name === t.to);
    if (a < 0 || b < 0) continue;
    secs.push({ s0: data.stops[a].s, s1: data.stops[b].s, style: t.style, d: TOR_OVER_SURFACE[t.style] ?? 0, source: 'user' });
  }
  if (surveyClass) {
    const user = secs.slice();
    let a = null;
    for (let s = 0; s <= length + 4; s += 4) {
      const green = s <= length && surveyClass(s) === 'green';
      if (green && a === null) a = s;
      if (!green && a !== null) {
        const s1 = s - 4;
        const last = secs[secs.length - 1];
        if (last?.source === 'survey' && a - last.s1 < 30) last.s1 = s1; // (short gaps: one section)
        else if (s1 - a >= 20 && !user.some((x) => s1 > x.s0 && a < x.s1)) secs.push({ s0: a, s1, style: 'grass', d: TOR_OVER_SURFACE.grass, source: 'survey' });
        a = null;
      }
    }
  }
  const at = (s) => secs.find((x) => s >= x.s0 && s <= x.s1)?.style ?? 'panels';
  const lift = (s) => {
    let v = 0;
    for (const x of secs) {
      if (!x.d || s < x.s0 - RAMP || s > x.s1 + RAMP) continue;
      const k = Math.min(1, (s - (x.s0 - RAMP)) / RAMP, ((x.s1 + RAMP) - s) / RAMP);
      v = Math.max(v, x.d * k * k * (3 - 2 * k));
    }
    return v;
  };
  return { sections: secs, at, lift };
}
