# Track joins in plan: smooth curves through the survey, switches paired by the track (#204)

Status: in review (PR for #204), line 17.

## Why

Since #20 the drawn and driven track follows DI's polyline (resampled at 1 m, a 0.1 m Gaussian), because OSM's
6 m smoothing pulled an 18 m curve 0.2 m inside the real one. DI's vertices then showed as corners, and
switches joined with kinks. The user, driving line 17 on 2026-11-03: "switches joining tracks together appear
too jagged", "even straight direction isn't really straight", "curves should be smooth instead of stepped
line" (reports `report-20261103-073229-s4ki`, `-073606-cwa4`).

## The rule

**Switches paired by the track** (`tools/di_tracks.py`):
- A DI fork is where records end together and leave apart, where a branch ends on the middle of a through
  record (Palackého náměstí), or where a branch that ran alongside leaves (Čechův most: 13 cm off for 21 m).
- An OSM switch takes the fork on its through track (a chain its toe or through edge runs on), facing the same
  way, within `FORK` = 15 m (was 5 m), nearest first, one switch per fork. The user's four answered forks lie
  5.3-7.4 m from OSM's switches. "The same side" was dropped: OSM's legs near a switch are a few metres long,
  and in a curved switch OSM and DI disagree which leg is straight (Křižovnická).
- OSM nodes between the switch and its fork (two-edge nodes, the next one beyond the fork) move onto the fork
  with it; a fork behind a junction is still refused (Holešovice).
- A switch's diverging edge matched only to the chain both through edges run on is left to the next source
  (Dvorce: DI has no branch onto the new Dvorecký most).

**Smooth curves** (`tools/track_curve.py`, called by the build after the match):
- Edges join into through tracks (the straightest pair continues at every node), fitted longest first as a
  penalised spline on 1 m samples: as little bending as the points allow, within `TOL` = 2 cm of every DI or
  archive point (`FILL_TOL` = 0.3 m of OSM fill). Weights grow only where the curve misses (Lawson).
- A node a longer track fixed is held; a track ending there leaves tangent to the track through it it starts
  within `START` = 6° of (113 ends on line 17: 96 within 4°); beyond, at its own angle (`switch-start`).
- A crossing node slides to where the two curves cross. A node off its surveyed track (the point nearest all
  its tracks) is no data point; nodes under 0.5 m apart are one.
- Where the curve bends under 90 % of 20 m over 2 m, the tolerance of the points within 10 m grows by 1.5 up
  to 25 cm; what still misses 2 cm by more than 1 cm is listed in the build log (`track curves`).
- The written points leave out samples a chord passes within 3 mm of, except within 2.5 m of a node. The
  line data says `trackCurve`, and the game draws such data as it is (no Gaussian, `src/route.js`).

## Checks

`tools/lint.js`:
- `trackRadius`: the radius over 5 m along every drawn track and both routes, flagged under 18 m. A curve held
  within 2 cm of noisy points reads 90 % of its radius over 5 m (sagitta 0.16 m on a 20 m curve), so 18-20 m
  is counted apart (`nearMin`).
- `trackJoins`: through tracks breaking over 1° where chains meet, per class; diverging start angles listed.

## Left open

- Dvorecký most: DI (2026-09-30) and the archive lack the new tracks; the archive's old connection makes a
  zigzag. Atlas Prahy draws the new junction, so a newer DI state may have it.
- Strossmayerovo náměstí: OSM joins a crossing and a switch in one node 0.5 m from DI's.
