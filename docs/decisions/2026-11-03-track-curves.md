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

**Smooth curves** (`tools/track_curve.py`, called by the build after the match):
- Edges join into through tracks (the straightest pair continues at every node), fitted longest first as a
  penalised spline on 1 m samples: as little bending as the points allow, within `TOL` = 2 cm of every DI or
  archive point (`FILL_TOL` = 0.3 m of OSM fill). Weights grow only where the curve misses (Lawson).
- Tracks are fitted longest first, but a track through a node before one ending there (Holešovice: a longer
  track ending at a node 2 m off its line fixed it, and the track through it bent at 4 m to reach it).
- A node a track fitted before fixed is held; a track ending there leaves tangent to the track through it it
  starts within `START` = 6° of (113 ends on line 17: 96 within 4°); beyond, at its own angle (`switch-start`).
- A crossing node slides to where the two curves cross. A node off its surveyed track (the point nearest all
  its tracks) is no data point; nodes under 0.5 m apart are one.
- Where the curve bends under 20 m over 2 m, the tolerance of the points within 10 m grows by 1.5, at most to
  the mean coordinate error of their records' accuracy class (`data/truth.json` `sourceAccuracy`: DI class 3
  0.14 m, class 2 0.08 m; the archive states none and is taken as class 3, the DTM's minimum; OSM fill 0.5 m).
  The user, 2026-11-03: "keep stricter rules and relax only where we get under the specified radius". Twice the
  error (a 95 % bound; the decree states no limit) gave 6 bends over 10° inside tracks instead of 11 and 32
  joins over 1° instead of 39, and is not used.
- The written points leave out samples a chord passes within 3 mm of, except within 2.5 m of a node. The
  line data says `trackCurve`, and the game draws such data as it is (no Gaussian, `src/route.js`).

## Checks

`tools/lint.js`:
- `trackRadius`: the radius over 5 m along every drawn track and both routes, flagged under 20 m.
- `trackJoins`: through tracks breaking over 1° where chains meet, per class; diverging start angles listed.

## Left open

- 24 connecting curves on line 17 read 18.5-19.9 m: held at both switches, their radius is DI's; 20 m needs the
  switches about 0.5 m off. Real curves under 20 m, or switches DI places wrong (#210 measures DI's forks)?
- Dvorecký most (#209): DI (2026-09-30, the newest state offered) and the archive lack the new tracks, and
  the archive's pieces on the old switch curves take OSM's new edges (a 25° break, 5-7 m curves). What Atlas
  Prahy draws is DI's planned-works set (dataset 8, "_budoucí TT", 2024-08-22): one corridor axis per double
  track, not track axes.
- Strossmayerovo náměstí: OSM joins a crossing and a switch in one node 0.5 m from DI's.
