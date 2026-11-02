# Vertical track profile: the design radius, not a blur

**Date:** 2026-11-02. **Issue:** #188. **Rule:** `tools/track_profile.py` (`vertical_profile`).
Applying it to the game's profile is #20's profile assembly.

## Why

The game smooths track heights with a Gaussian over ±9 m (`src/world.js`), chosen when the height data was
rough and not classified. It removes wiggles but also blunts real crests and sags, and it does not join
the tracks of several lines and directions into one network. The selected heights now come from classified
sources (DI, the archive, the survey, reviewed spans: [height fallback](2026-10-30-track-height-fallback.md)),
and the archive still wiggles by 0.1–0.3 m at record joints and between vertices. The roughest of the 27
review profiles was a 0.27 m bump over 7 m at Hlavní nádraží, the curvature of a ~35–75 m radius.

## The rule

A tram track is built of grades joined by vertical curves. The design minimum radius is 1000 m on open track
(own or shared bed) and in switches, and 500 m in a street in closed built-up areas (ČSN 73 6412:2017 as quoted
by Hradil 2020; `data/truth.json` `trackGeometry.facts`). `vertical_profile` finds the heights that change the
data least (weighted least squares) while no point's change of grade is tighter than its radius:

- solved exactly, by ADMM on the second differences with one banded factorisation (no SciPy);
- robust: after each round a point the curve misses by more than 4.685 × 0.05 m stops pulling it (Tukey), so a
  lone bump is dropped instead of spread over its neighbours;
- `rmin` per point (street, open track, switch), `pins` hold a point fixed: a junction's height shared by the
  tracks that meet there, a reviewed point; `weight` per point (0 drops one);
- a point the curve misses by more than 0.3 m (#184's departure threshold) is reported in `steps`, not a
  wiggle: a step, dip or wrong level belongs to the span rules, and the caller holds it.

On synthetic profiles: a sharp break of grade from +2 % to −2 % becomes a 500 m curve that moves at most 7 cm,
a 0.27 m one-point bump stays 2 cm above the grade while its neighbours move under 5 mm, and a real 600 m
crest and a straight −5.8 % grade (Klárov) are kept (`tools/test_track_profile.py`).

## Calibration (2026-11-02)

`python -P -E tools/track_profile.py --calibrate` on `reports/track-heights.json` (snapshot 2026-11-01):
684 chains of DI paths (joined where ends meet within 0.3 m and continue within 15°), 61,240 bins of 5 m,
structures, tunnels and known archive disagreements left out. The archive alone is smoothed to 500 m.

- **Numeric DI is not an independent judge here.** Where the rule acts, the archive equals DI to a median of
  3 mm (the shared source history noted in the fallback decision), so DI has the same wiggles.
- **The lidar breaks 500 m as often as the archive.** Over three 5 m bins a 500 m radius allows a 5 cm second
  difference, and 1–2 cm of noise in any source exceeds it. Of 12,200 paved bins with three lidar points, the
  archive breaks the radius on 18.3 %, the 2023 lidar on 19.6 %, both on 11.2 %. Most of these breaks are below
  every source's precision (lidar ±3 cm, survey ±3 cm), and moving them costs nothing.
- **Where the rule acts on runs without a step** (8448 bins): it moves p50 1.4 / p90 5.0 / p99 10.3 cm. On paved
  track (rails flush with the surface) against the lidar: raw p50 0.027 / p90 0.153 / p99 0.303 m, smoothed
  0.040 / 0.137 / 0.274 m; 38 % of bins closer, 42 % further. The tails shrink and the median shift stays
  inside the lidar's precision.
- At record joints (1449 bins) and inside records (9759) the moves are alike (p90 6.1 and 5.4 cm); joints are not
  the main source of the wiggles.
- **33 runs have steps** (376 points the curve cannot follow within 0.3 m), largest −76.6 m near Malovanka
  (50.0900 N, 14.3860 E: an archive height from a much lower level), −7.2 m at 50.1033 N, 14.4592 E, +4.5 m at
  50.0549 N, 14.4723 E and at 50.0969 N, 14.4027 E. They are listed in the report's `steps_at`: data for #20's
  source checks, not for smoothing.

## Check

`python -P -E tools/track_profile.py --check` smooths every imported review profile (52 profiles of the 27
decisions) to the street radius and prints the tightest radius before and after; it fails if any is left
tighter. 2026-11-02: 14 profiles broke 500 m before, none after; the largest move 0.12 m (Hlavní nádraží,
pathBack, from 35 m), Šumavská 0.06 m (from 100 m), Modřany 0.10–0.11 m.

## For #20

Assemble one profile per track chain across all lines and directions, smooth it once with `vertical_profile`,
radius by construction (paved street 500 m, open track 1000 m, unknown 500 m) and 1000 m through switches; pin a
junction's height so the tracks that meet there share it; hold the `steps`. The Gaussian in `src/world.js` then
goes.
