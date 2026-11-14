// SPDX-License-Identifier: AGPL-3.0-or-later
// What each height means (docs/decisions/2026-10-29-what-each-height-means.md, #9). All heights are Bpv
// metres. The track profile is the top of rail (TOR): the tram's wheels stand on it, rails, bed and
// catenary are measured from it. Until 2026-10-29 the profile was the street under the track, with the
// rail heads drawn 0.26 m over it and the street beside them pressed to +0.14 m: the whole track zone
// stood 14-26 cm proud of the surveyed road.

// Shared with the height importer. Missing/conflicting facts must not silently become a different
// rail height in the game. Local deck facts remain importer-only; these are the global style values.
export function trackStyleOffsets(truth) {
  const offsets = {};
  for (const style of ['embedded', 'setts', 'panels', 'grass', 'ballast']) {
    const facts = (truth?.trackHeights?.railAboveDeck || []).filter((f) => f.scope === 'all' && (!f.styles || f.styles.includes(style)));
    if (!facts.length || facts.some((f) => !Number.isFinite(f.metres) || f.metres < 0 || !f.id) ||
        new Set(facts.map((f) => f.metres)).size !== 1) throw new Error(`Missing or conflicting rail offset facts: ${style}`);
    offsets[style] = { metres: facts[0].metres, factIds: facts.map((f) => f.id) };
  }
  return offsets;
}

// These facts are required by both the profile and the drawn track. A failed download must be
// reported by the loading screen; it cannot silently substitute a second table of offsets.
export async function loadHeightFacts(fetcher = fetch) {
  const response = await fetcher('data/truth.json');
  if (!response?.ok) throw new Error(`Could not load required track facts (data/truth.json, ${response?.status ?? 'network error'})`);
  const truth = await response.json();
  trackStyleOffsets(truth);
  return truth;
}

// The drawn layers just around top of rail, apart enough not to flicker: the rail heads a little over
// it, the bed (or the street of an embedded track) a little under, the street beside the bed under that.
export const RAIL_HEAD = 0.012; // drawn rail head over TOR
export const BED_BELOW = 0.006; // bed surface under the surface level the style gives
// The street next to the track, as stored: drawn 0.012 m under the surface level (below the bed). The
// surveyed areas are drawn up to 0.04 m over their stored vertices (terrain.js DTM_LIFT), the OSM road
// ribbons 0.12 m over the ground (world.js), so each is stored that much lower again.
export const STREET_BELOW = 0.012 + 0.04; // a surveyed street vertex next to the track, under the surface level
export const ROAD_BELOW = 0.012 + 0.12; // the ground under an OSM road ribbon next to the track

// The assembled heights of the line data (#197, tools/line_heights.py) come every `step` m with null where there
// is none: `resampleHeights` reads them at another spacing (NaN where a neighbour is null), `meetHeights` fills the
// NaN runs from another profile, shifted at both ends so it meets the data (linear between the two shifts).
export function resampleHeights(arr, step, n, at) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const k = (i * at) / step, i0 = Math.min(Math.floor(k), arr.length - 1), f = k - i0;
    const a = arr[i0], b = arr[Math.min(i0 + 1, arr.length - 1)];
    out[i] = a == null ? NaN : f < 1e-6 || i0 + 1 >= arr.length ? a : b == null ? NaN : a + (b - a) * f;
  }
  return out;
}

export function meetHeights(d, base) {
  const out = Float32Array.from(d), n = d.length;
  for (let i = 0; i < n; i++) {
    if (!Number.isNaN(d[i])) continue;
    let j = i;
    while (j + 1 < n && Number.isNaN(d[j + 1])) j++;
    const a = i > 0 ? d[i - 1] - base[i - 1] : null, b = j < n - 1 ? d[j + 1] - base[j + 1] : null;
    for (let k = i; k <= j; k++) {
      const u = (k - i + 1) / (j - i + 2);
      out[k] = base[k] + (a === null ? (b ?? 0) : b === null ? a : a + (b - a) * u);
    }
    i = j;
  }
  return out;
}

// The line's track styles, as functions of the route position: `at(s)` the style ('panels' where nothing says
// otherwise), `lift(s)` its top of rail over the surface, blended inside the section ends. The sections and the lift
// are the build's (the line data's `styles` and `lift`, tools/track_styles.py, #479, #480: the user's marks in
// data/truth.json, the grassed-track list and the survey's grass track); how high the rails stand over each style
// is truth.json's `railAboveDeck`.
export function trackStyles(truth, data) {
  const offsets = trackStyleOffsets(truth);
  const secs = (data.styles || []).map((x) => {
    const offset = offsets[x.style];
    if (!offset) throw new Error(`Unknown track style: ${x.style}`);
    return { ...x, d: offset.metres, offsetFactIds: offset.factIds };
  });
  const at = (s) => secs.find((x) => s >= x.s0 && s <= x.s1)?.style ?? 'panels';
  const L = data.lift, n = L ? L.v.length : 0;
  const lift = (s) => {
    if (!n) return 0;
    const f = Math.max(0, Math.min(n - 1.001, s / L.step)), i = Math.floor(f), t = f - i;
    return (L.v[i] * (1 - t) + L.v[i + 1] * t) * L.unit;
  };
  return { sections: secs, at, lift };
}
