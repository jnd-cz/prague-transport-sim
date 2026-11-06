# Track joins in plan: smooth curves through the survey, switches paired by the track (#204)

Status: accepted (PR #208), line 17; the 18 m hold, the checks' measures and the drawing of the fitted curves
followed (the second PR for #204).

## Why

Since #20 the drawn and driven track follows DI's polyline (resampled at 1 m, a 0.1 m Gaussian), because OSM's
6 m smoothing pulled an 18 m curve 0.2 m inside the real one. DI's vertices then showed as corners, and
switches joined with kinks. The user, driving line 17 on 2026-11-03: "switches joining tracks together appear
too jagged", "even straight direction isn't really straight", "curves should be smooth instead of stepped
line" (reports `report-20261103-073229-s4ki`, `-073606-cwa4`).

## The rule

**Switches paired by the track** (`tools/di_tracks.py`):
- A DI fork is where records end together and leave apart, where a branch ends on the middle of a through
  record (Palackého náměstí), or, on interlaced track, where the branch starts beside the track: at the tip of
  the tongue DI draws, else at the branch's end (Čechův most: 13 cm off for 25 m, then the tracks part at the
  junction). Interlaced is 0.05-0.2 m beside the track for 10 m or more, followed across record joints; a
  switch's branch is 0.2 m off within 4-9 m. Placing that fork where the branch left (as first built) moved
  Čechův most's switches 21 m onto the junction; the user: "The DI fork is wrong while OSM seems right [...]
  the fork starts and ends well in front of/behind the road junction" (2026-11-03).
- A switch DI draws as a section (both legs as records up to `SECTION` = 6 m from the tip, the fork of record
  ends at their far joint) forks at the tip: Dvorecký most's switches on line 17's eastern track moved 4.6-4.8 m
  onto their switch machine covers and OSM's switches (0.09-0.13 m off).
- Where DI starts the branch already 13 cm off at a record joint, the tip is `TONGUE` = 8.5 m back (the tongues
  DI draws elsewhere are 8.4-9 m; Čechův most's OSM switches lie 8.0 and 8.8 m back).
- **Places the user corrects** (`data/truth.json` `trackSources`): a switch tip (`switchTips`: the switch takes the
  point of its through track nearest a mark, Podolská vodárna's eastern switch at the archived map's manhole, 3.3 m
  from DI's fork) and, as an exception, a track measured on the orthophoto (`photoTracks`: Podolská vodárna's north
  curve, where DI's line is 19-34 cm off the rails and reads 14.6 m over 5 m). The measured track takes the edges
  matched to a source chain it covers, joins both switches tangent, its centres held within 5 cm (`PHOTO_TOL`, their
  scatter is 1.6-2.7 cm) and OSM's nodes on it not data. The curve: 17.9 m over 5 m, 3.5 cm from the rails (median);
  the rails' western half alone reads 17.9 m.
- **OSM's shared interlaced way is split** (`di_tracks.split_interlaced`, called by the build before matching):
  OSM draws one way from the switch to where the tracks part. The stretch from the tip to that junction is
  doubled and the copy carries the leg on the branch's side, so each track matches its own DI record, the switch
  sits at the tip, and the routes on either leg take their own track. Pairing OSM's split node with the tip
  instead had pulled it 14 m along the shared way and left a zigzag at OSM's switch node (Čechův most, "a small
  white kink south of the 829 marked DI fork", the user). Line 17: 3 tip nodes added, 12 nodes copied: interlaced
  pairs at Čechův most, Ke Stírce and Březiněveská.
- An OSM switch takes the fork on its through track (a chain its toe or through edge runs on), facing the same
  way, within `FORK` = 15 m (was 5 m), nearest first, one switch per fork. The user's four answered forks lie
  5.3-7.4 m from OSM's switches. "The same side" was dropped: OSM's legs near a switch are a few metres long,
  and in a curved switch OSM and DI disagree which leg is straight (Křižovnická).
- OSM nodes between the switch and its fork (two-edge nodes, the next one beyond the fork) move onto the fork
  with it; a fork behind a junction is still refused (Holešovice).
- A switch's diverging edge matched only to the chain both through edges run on is left to the next source
  (Dvorce: DI has no branch onto the new Dvorecký most).
- **The through track first** (the user, 2026-11-03, at Strossmayerovo náměstí with a photo: "The straight
  direction should be straight without any kinks, first switch is to the left, then further to the right"; "I
  would put higher priority to keep the through track straight, then let other track branch from it to the
  side"). There the straights swung 8-12 cm over 21 m, though DI draws them straight within 0.1°:
  - A stretch is matched with up to `CONTEXT` = 10 m of its straight continuation: through two-edge nodes, and
    through a switch only from its toe or through leg (its legs by their directions over 10 m). Alone, the
    4.75 m between two switches lay nearer the branch DI draws 0.19 m beside the straight, and the straight was
    drawn onto it; the branch's chain does not reach the straight beyond.
  - A DI fork goes to an OSM switch whose branch leaves to the other side (over 10 m) only if no switch nearby
    fits: the westward turn's fork went to OSM's switch 2.1 m on, whose branch leaves the other way, and the turn
    started 3.8 m late at 12°.

**Smooth curves** (`tools/track_curve.py`, called by the build after the match):
- Edges join into through tracks (the straightest pair continues at every node, judged at a junction over
  `PAIR_LOOK` = 10 m on through the next nodes: over 3 m a tangential branch read 0.1° straighter than the
  straight, which DI bends 0.9° at the switch, and the straight was fitted as the branch), fitted longest first as a
  penalised spline on 1 m samples: as little bending as the points allow, within `TOL` = 2 cm of every DI or
  archive point (`FILL_TOL` = 0.3 m of OSM fill). Weights grow only where the curve misses (Lawson).
- Tracks are fitted longest first, but a track through a node before one ending there (Holešovice: a longer
  track ending at a node 2 m off its line fixed it, and the track through it bent at 4 m to reach it).
- A node a track fitted before fixed is held; a track ending there leaves tangent to the track through it it
  starts within `START` = 6° of (113 ends on line 17: 96 within 4°); beyond, at its own angle (`switch-start`).
- A crossing node slides to where the two curves cross. A node off its surveyed track (the point nearest all
  its tracks) is no data point; nodes joined by an edge under 0.5 m are one, the one with more edges kept.
- A switch within `OFF` = 0.2 m of its through track joins it exactly; a node further off, where three edges
  meet, keeps its place and the track passes at its own point (Národní divadlo, 0.34 m). DI's branches start up
  to 0.18 m apart at a fork: with `OFF` = 0.1 m Strossmayerovo náměstí's crossover branches began 0.15-0.17 m
  beside their through tracks, which broke 1.2-1.3° at the joint there.
- Where the curve bends under 20 m over 2 m, the tolerance of the points within 10 m grows by 1.5, at most to
  the mean coordinate error of their records' accuracy class (`data/truth.json` `sourceAccuracy`: DI class 3
  0.14 m, class 2 0.08 m; the archive states none and is taken as class 3, the DTM's minimum; OSM fill 0.5 m).
  The user, 2026-11-03: "keep stricter rules and relax only where we get under the specified radius". Twice the
  error (a 95 % bound; the decree states no limit) gave 6 bends over 10° inside tracks instead of 11 and 32
  joins over 1° instead of 39, and is not used.
- **18 m is held past the class** (`data/truth.json` `min-radius-network`, the user: "18m and over could be some
  exceptions [...] under 18m there shouldn't be anything like that. [...] At which cost can we snap it to 18m
  curve?"; asked how, the user chose "18 m held, cost reported", 2026-11-03): where the curve still bends under
  18 m with every point near it at its class, its bending weight there grows by `STIFFEN` = 1.5 per round and
  those points' tolerance keeps growing, at most to `HOLD_LIMIT` = 0.5 m. The build logs each such place with how
  far its points moved. A wider tolerance alone does not widen a curve, it only stops pulling it: on a 30° test
  corner the bend moved to where the points at their class began (15 m); a factor of 4 at once took a 15° corner
  to 49 m with its points 0.49 m off, 1.5 to 18.2 m with 9 cm.
- The written points leave out samples a chord passes within 3 mm of, except within 2.5 m of a node, and are
  written to the millimetre (to the centimetre, points 0.4 m apart scatter 0.7° in direction). The line data says
  `trackCurve`, and the game draws such data as it is: the tracks' own points, with points added only on segments
  over 1.5 m (`densify`), their heights smoothed over metres instead of points; the route resampled at 1 m with no
  Gaussian. Before, a "0.1 m" window still averaged three points 1.5 m apart and the tracks were resampled: a
  joint the build made 0.9° drew as 3.7° at the end of a 4.6 m piece (Strossmayerovo náměstí).

## Checks

`tools/lint.js`:
- `trackRadius`: the radius over 5 m (the circle through a point and the farthest points within 2.5 m either side)
  along every track and both paths as the build wrote them, flagged under 18 m; 18-20 m listed as `exceptions`.
  It first read points interpolated on the game's 1.5 m resample: a 1 m chord sags 7 mm inside a 19 m curve, and
  it read 19.1 m (the fit's own measure) as 17.6 m at Právnická fakulta.
- `trackJoins`: through tracks breaking over 1° where chains meet, per class; diverging start angles listed. The
  user kept 1° (2026-11-03: "Keep 1°, fix the nodes"). An end's direction is the tangent of the least-squares
  parabola through the drawn points within 2 m (the parabola through the first three read a smooth 21 m curve
  as a 1.2° break where the first step was 0.17 m).

## Left open

- 64 places on line 17 read 18-20 m over 5 m (58 on DI's tracks, 2 each on both paths and the photo curve),
  listed as exceptions: connecting curves held at both switches keep DI's radius, and 20 m needs the switches
  about 0.5 m off. Real curves under 20 m, or switches DI places wrong? #210 closed without measuring DI's forks: the user's
  checks on the orthophoto found them right (2026-11-06: "DI fork position looks good as it is"). Not re-counted
  on the network of #237.
- Dvorecký most: resolved by DI's state of 2026-10-31 (#209, PR #213), which has the new tracks.
