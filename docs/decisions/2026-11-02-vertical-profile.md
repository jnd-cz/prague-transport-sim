# Vertical track profile: the design radius, not a blur

**Date:** 2026-11-02. **Issue:** #188. **Rule:** `tools/track_profile.py` (`vertical_profile`).
Applying it to the game's profile is #197 (`tools/line_heights.py`): since 2026-11-03 by the band rule
(`banded_profile`, below), the design radius within 10 cm of the data, the rest for the user's review.

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

The design radius, not a fit to the data, is the basis: no source is independent of the archive and precise
enough at 5 m to set a limit (below). The user confirmed it on 2026-11-02: "I confirm the rule should enforce
500m ČSN radius."

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
- **Steps** (points the curve cannot follow within 0.3 m) on the archive alone: 35 runs, 205 points after
  #190's robust start (33 runs and 376 points before it, when one bad record pulled its neighbours along).
  The report's `steps_at` lists them; what they are is `--steps`, below.

## Robust start (#190)

A plain first round bent the curve towards one bad record: at Malovanka an archive record 83 m above the street
over 25 m moved 32 good points by more than 0.3 m, and Tukey then dropped those too. The reweighting now starts
from each point's distance to the median of its 11 neighbours: further than 2c (0.47 m) starts without a pull.
Malovanka's run: 37 step points before, 5 after (the record itself). The calibration above is unchanged by it.

## Steps by cause (#190)

`python -P -E tools/track_profile.py --steps` takes the import's selected heights along every chain of DI paths;
held heights (a hold of the import, a structure) are bridged by the curve at weight 0 up to 60 m, a longer hold
cuts the run. Each group of steps gets a cause (`cause`): `structure` (next to a bridged structure, its deck is
the structure review's), `di` (numeric DI, used as supplied), `dip` (every point below the curve: the archive on
the ground under a deck no source maps, bridged by #184's curve from both sides), `survey`, `terrain` (the terrain
has the same shape, no source disagrees: a question), `archive` (off the terrain by less than the 1 m hold).
It fails on a step over 1 m whose cause is not `di`, `dip` or `structure`.

2026-11-02 (`reports/track-profile-steps.json`, with the Mosty 3D structures of #192): 610 runs, 63,907 bins,
507 bridged. 35 groups, 57 points: `archive` 10 (none over 1 m), `di` 6 (2 over 1 m), `dip` 15 (2), `structure`
1 (none), `terrain` 3 (none). 0 fail. Over 1 m:

- `di` +1.76 m at Strašnice (50.0691 N 14.4687 E): numeric DI rises 1.9 m above the archive, the survey and the
  terrain, which agree; −1.14 m at 50.0861 N 14.4319 E. DI wins by the import's rule; both are flagged
  `known_archive_disagreement`.
- `dip` −4.7 m at the end of the Libeň river bridge (14.4642 E, the street under it, where Mosty 3D has no
  bridge), −3.6 m at Modřany (50.0142 N 14.4018 E). The −5.5 m and −4.2 m dips at 50.0549 N 14.4723 E are a
  Mosty 3D bridge now (feature 237).
- Before the user's answer, `terrain` +3.9 m in both directions on the Libeň bridge's rebuilt eastern approach
  (the archive and the lidar alternate between the deck, ~190 m, and the ground under it, ~184 m). It is now the
  user's structure ([height fallback](2026-10-30-track-height-fallback.md)).

Under 1 m (0.3–1 m): `archive` 10 groups, `di` 4, `dip` 12, `structure` 1, `terrain` 3, most of one or two points.

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

## Assembly in the build (#197, 2026-11-03)

`tools/line_heights.py` does the above for the game; `tools/rebuild.py` runs it after the lines' steps (it reads
every line's survey sidecar). It stages the heights with the user's answers as span evidence
(`track_span_evidence.py` from `data/truth.json`, in the same process), bins them every 5 m along the DI
through-chains (`chains`, copies dropped as in `tools/di_tracks.py`: 656 chains, 66,820 bins on 2026-11-03) and
writes into the line data the heights of path and pathBack every 2 m (`heights`, `heightSource`), the opposite
track beside the path (`backOff`, `backZ`), each drawn track's `zs`, and the staged heights the check compares
with (`heights.staged`).

- **Radius by construction:** 500 m on paved street and where it is unknown, 1000 m on open track, in a turnout
  (from the fork 15 m into the diverging track on both tracks, 3 m behind it) and 5 m either side of a diamond
  crossing. A 20 m zone around every junction first held a 430 m sag at Nádraží Holešovice to 1000 m.
- **Junctions, longest track first:** a chain meeting one already solved is pinned to its height there: a fork
  (the diverging end on the through track), a crossing within 1 m of height, ends meeting each other, and two
  tracks whose meets with a third lie within 2 m of each other along it (two track ends 0.65 m apart near Ke Stírce,
  9 cm apart in height). At one spot a fork's or crossing's own point wins over ends nearby (on a 4 % grade the
  end of a third track 0.5 m off was 4 cm higher), then the longer track. A pin weighs 1000 and is never dropped
  as an outlier (`vertical_profile(pin_weight=…)`; with 10⁶ the solver stopped short of the radius on 30 chains
  after 3000 steps). Crossings each pinned to the mean of their two tracks first: their pins a few metres apart
  and centimetres off along a junction's diamonds asked for radii of a few metres, 172 s for 7 chains.
  2026-11-03: 1514 pinned meets, the largest difference 8.4 mm; no crossing over 1 m apart in the data.
- **The band rule** (the user, 2026-11-03: "If the curve >=500m fits within 10cm then it's solved, otherwise let's keep
  it for review again so we can find the root cause together"; `banded_profile`). The heights nearest the staged ones
  (least squares, with a curvature penalty of h⁴ that smooths noise over ~5 m and leaves no short humps) that stay
  within `BAND` = 10 cm of them and turn no tighter than the design radius. Within a turnout or a diamond the band is
  15 cm (the user: "there can be little play within the junction if we account for input data errors, noise"), and
  a junction's pinned height holds within 5 mm. Not held to the band: a lone bad point (one or two bins the robust
  fit at the design radius misses by over 10 cm) and a stretch steeper than any track (9 %, the archive on the
  ground under a deck); those are the steps by cause, as before.
- **Where no curve at the design radius fits,** the radius gives way ×0.8 at a time within 50 m of the points outside
  the band (at most 12 times, never under 20 m) so the game has a curve within the band, and the place goes to the
  user's review if the band was missed by over 1 cm (a few millimetres at a pin only bend the radius). Where even
  that cannot meet a pin, the rails join first and the band gives way within 15 m of it.
- **Why not the radius held at any cost** (the first assembly, the same day): with L2 and Tukey, a stretch the curve
  missed by over 23 cm was dropped and the curve ran away: at Královka the loop's track, pinned at three junctions
  with five 1000 m zones (a diamond inside the sag), departed 1.22 m from data that a 500 m curve meets within 4 cm
  when neither pins nor zones bind; at Malostranská 1.02 m where 500 m fits within 2 cm. Relaxing the radius there to
  250 m hid that. At junctions, short tracks of 44–58 m with 9–12 heights carried 4–7 pins from tracks with their own
  noise: a 44 m track at Strossmayerovo náměstí missed its data by 12 cm with them, 1 cm without.
- **The user's review** (`reports/review/track-radius.json`, one decision per place `radius-<lat>-<lon>`, the staged
  heights, the terrain, and as the previews of its two answers the curve held to the design radius and the one
  within the band). An answer recorded in `data/truth.json` `trackHeights.radiusAnswers` (the place, `hold the
  radius` or `follow the data`, with its quote) applies to the place it is within 15 m of; `hold the radius` keeps the
  radius there and leaves the band. 2026-11-03: 25 places, 3 on plain track (1.2, 2.2 and 7.8 cm outside the band at
  the design radius) and 22 at junctions (1.1–12 cm; at 2 the band gives way near pins). On line 17 one, at
  Strossmayerovo náměstí (3.5 cm). Malostranská and Královka's plain stretch fit; at Královka two junctions stay:
  the loop's entry, where the through track carries three overlapping 1000 m zones (turnouts and a diamond, 129–160 m)
  on the descent (without them its miss halves, 0.78 → 0.36 m), and an archive record that lies up to 0.43 m from
  the terrain and pulls the loop's track through its pins.
- **A short hold** starts on the straight line between its neighbours, at weight 0.001: at weight 0 the curve was
  free to sag anywhere the radius allowed, 5 cm under a straight grade across 40 m.
- **A line takes the heights of the chains under it,** weighted by how near each is within 1 m: past a fork both
  tracks lie within centimetres and share the junction's height (picking one, the line jumped between them;
  staying on one, it stepped where it let go). Its last sample sits at n × 2 m past its end, along the chain: the
  game reads every sample at k × 2 m. Where a drawn track ends on another, its end takes that track's height,
  fading out over 10 m (ends meeting only ends take their mean): a junction's short edges ended up to 0.3 m off
  the track they join and were sampled 3 cm apart on a 2 % grade.

2026-11-03 (the band rule): 0 steps over 1 m without a rule (`archive` 8, `dip` 14, `di` 5, `structure` 1, `terrain`
7); no pinned junction over 1 cm apart (the largest 7 mm); moved from the staged heights on runs without a step
p50 0.005 / p90 0.03 / p99 0.08 m; 93 held stretches over 60 m
(6,045 m), 48 of them (3,120 m) structures and tunnels. Line 17, path and pathBack 43,632 m: DI 18,656 m, archive
22,120 m, the user's reviewed spans 2,054 m, curve 348 m, no height 454 m (the game's surface profile there: the
archive and the survey disagree over 60 m and more between Čechův most and Strossmayerovo náměstí in both
directions, 115 m past Staroměstská and between Přístaviště and Dvorce). Against the staged heights: p90 0.027 m
(path), 0.037 m (pathBack).

**The game** (`src/terrain.js` Profile): the route's profile is the data's; where it has none, the surface profile
stays, shifted to meet it at both ends (linear between the two shifts). Across the street the profile runs
linearly from our track to the opposite one and is level beyond them (`heightAt`, from `backOff` / `backZ`); the
two directions differ by p50 0.03, p90 0.10, max 0.95 m on line 17, which the opposite track taking our height
would have kept. `trackAt` (the oncoming trams, the drawn track near the route), the street flush, the street rows
and the track support use it. A drawn track with `zs` takes them unsmoothed; the ±9 m Gaussian stays for tracks
without (OSM or archive fill, lines not rebuilt). `python -P -E tools/headless.py --checks heights` measures the
game's track against `heights.staged` (p90 ≤ 0.10 m per direction) and the drawn tracks where they meet (over
1 cm apart: two heights).
