// SPDX-License-Identifier: AGPL-3.0-or-later
// The street vehicles' types (#250): five car, van and truck types from the project's asset lab, each a near model
// (wheels, steering, lamps, plates) and a far one (one primitive), assets/cars/<id>-near.glb and -far.glb. Their sizes
// are the models' (tools/test_cartypes.py measures them from the GLBs): in metres, `length` bumper to bumper, `width`
// over the tyres (the widest part below the mirrors: the tyres stand 6.5 cm out from the sills on every type),
// `mirrors` over the mirrors, `height` to the roof, `wheelbase` and `track` between the wheel centres, `wheelRadius`.
// A car's position is its middle (the models' origin: on the ground, midway between the axles).
// `weight`: its share of the cars spawned, the lab's illustrative defaults ("not measured Prague proportions").
export const CAR_TYPES = [
  { id: 'compact', weight: 42, length: 4.430, width: 1.893, mirrors: 2.150, height: 1.478, wheelbase: 2.64, track: 1.66, wheelRadius: 0.315 },
  { id: 'sedan', weight: 25, length: 4.850, width: 1.973, mirrors: 2.230, height: 1.469, wheelbase: 2.82, track: 1.74, wheelRadius: 0.325 },
  { id: 'estate', weight: 20, length: 4.930, width: 1.973, mirrors: 2.230, height: 1.518, wheelbase: 2.82, track: 1.74, wheelRadius: 0.325 },
  { id: 'van', weight: 10, length: 5.430, width: 2.213, mirrors: 2.470, height: 2.268, wheelbase: 3.20, track: 1.98, wheelRadius: 0.36 },
  { id: 'box', weight: 3, length: 6.438, width: 2.433, mirrors: 2.690, height: 2.850, wheelbase: 3.70, track: 2.20, wheelRadius: 0.39 },
];

export const carFiles = (t) => ({ near: `assets/cars/${t.id}-near.glb`, far: `assets/cars/${t.id}-far.glb` });

const TOTAL = CAR_TYPES.reduce((s, t) => s + t.weight, 0);
// the type for a draw u in [0, 1) (from the run's seeded random, src/random.js), by the weights
export function pickCarType(u) {
  let w = u * TOTAL;
  for (const t of CAR_TYPES) if ((w -= t.weight) < 0) return t;
  return CAR_TYPES[CAR_TYPES.length - 1];
}

// the type of car number n (a car's id, a parked car's or a signal scene's number): from a hash of n, as a driver's
// boldness comes from the id (src/traffic.js), not a draw from the run's stream: adding the types left every seeded
// run's draws where they were. (Each caller numbers its cars in its own range.)
export function carTypeOf(n) {
  let h = Math.imul((n | 0) ^ 0x9e3779b9, 0x85ebca6b);
  h ^= h >>> 13;
  h = Math.imul(h, 0xc2b2ae35);
  h ^= h >>> 16;
  return pickCarType((h >>> 0) / 4294967296);
}
