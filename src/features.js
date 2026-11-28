// SPDX-License-Identifier: AGPL-3.0-or-later
// The feature layer (#14): a line's placed objects as records, from data/lineN.features.json (tools/features.py; the
// design: docs/decisions/2026-11-28-feature-layer.md). A record has the source's `id`, its `kind`, `x`, `y` (the city
// frame, m; the world's z is -y), `mount` (ground, wall) and `source`; where known a `heading` (compass degrees,
// clockwise from north, the way the object's front, its model's +Z, faces) with `headingFrom`, and what its source
// knows beside (a shelter's `length`, `width`, `z` and `stop`). The file holds them in groups (kind, source, mount),
// column by column.
// What draws a kind reads it here (`of`): the covers and inlets in src/streets.js. A kind with no model yet has a
// placeholder, a post or a box of its usual size, which the dev overlay shows (src/debugOverlay.js).

export const VERSION = 1; // (the file's; tools/features.py)
const COLUMNS = ['heading', 'z', 'length', 'width', 'stop', 'variant'];

// the rotation about +Y that turns a model's +Z to a compass heading (degrees)
export const yaw = (heading) => Math.PI - (heading * Math.PI) / 180;

// kinds no model draws yet: the placeholder's height (m), half width (m) and colour. A shelter's is its footprint.
export const PLACEHOLDER = {
  light_on_pole: { h: 9, r: 0.09, color: 0xffe066 }, decorative_light_on_pole: { h: 5, r: 0.09, color: 0xffc040 },
  light_on_building: { h: 7, r: 0.09, color: 0xffe066 },
  pole: { h: 8, r: 0.12, color: 0x9aa0a6 }, pole_low_voltage: { h: 8, r: 0.1, color: 0x8d6e4f }, lattice_mast: { h: 14, r: 0.3, color: 0x9aa0a6 },
  signal: { h: 3.3, r: 0.1, color: 0xff4040 }, signal_on_building: { h: 5, r: 0.1, color: 0xff4040 }, light_signal: { h: 3.3, r: 0.1, color: 0xff8040 },
  traffic_sign: { h: 2.6, r: 0.06, color: 0x4080ff }, stop_sign: { h: 2.9, r: 0.08, color: 0x22cc55 }, stop_sign_on_building: { h: 2.9, r: 0.08, color: 0x22cc55 },
  warning_beacon: { h: 1.2, r: 0.1, color: 0xffa000 }, clock: { h: 4.5, r: 0.12, color: 0xffffff }, phone_booth: { h: 2.2, r: 0.45, color: 0xc060ff },
  transformer: { h: 1.6, r: 0.5, color: 0x808890 }, fountain: { h: 1, r: 0.6, color: 0x40c0ff },
  shelter: { h: 2.46, color: 0x00e5ff },
};

export class Features {
  // file: the parsed data/lineN.features.json
  constructor(file) {
    this.file = file;
    this.groups = new Map(); // kind -> its groups
    for (const g of file.groups) {
      if (!this.groups.has(g.kind)) this.groups.set(g.kind, []);
      this.groups.get(g.kind).push(g);
    }
  }

  kinds() { return [...this.groups.keys()]; }

  count(kind) { return (this.groups.get(kind) || []).reduce((n, g) => n + g.id.length, 0); }

  // a kind's records
  of(kind) {
    const out = [];
    for (const g of this.groups.get(kind) || []) {
      for (let i = 0; i < g.id.length; i++) {
        const o = { id: g.id[i], kind, x: g.xy[2 * i], y: g.xy[2 * i + 1], mount: g.mount, source: g.source };
        for (const c of COLUMNS) if (g[c] && g[c][i] !== null) o[c] = g[c][i];
        if (o.heading !== undefined) o.headingFrom = g.headingFrom;
        out.push(o);
      }
    }
    return out;
  }

  // per kind and source: how many (the dev overlay's list, window.game.data.features.counts())
  counts() {
    const out = {};
    for (const [kind, gs] of this.groups) for (const g of gs) (out[kind] ||= {})[g.source] = (out[kind][g.source] || 0) + g.id.length;
    return out;
  }
}

// The parsed file as Features; null (and a warning) for a file of another version.
export function readFeatures(file) {
  if (file?.version !== VERSION) { console.warn(`features file version ${file?.version}, the page reads ${VERSION}: python -P -E tools/features.py`); return null; }
  return new Features(file);
}
