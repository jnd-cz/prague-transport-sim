# DI's own network is the drawn track; OSM's routes are matched over it (#237)

Status: proposed (PR #312).

## Why

Since #20 the build moved OSM's track graph onto DI piece by piece (`di_tracks.TrackGeometry`). Where OSM's
junctions lay 2-3 m from DI's this needed a rule per place, and each rule found the next case: Strossmayerovo
náměstí (straight-on context), Malostranské náměstí (the gauntlet), merged nodes (#219), Anděl (OSM's track 2.2 m
east of DI's through three crossings, PR #218). The user, 2026-11-04: "If it's getting too complicated maybe we
should reconsider and start over with the rules?", answered "Rewrite matching on DI".

## The rule

- **The network** (`tools/di_network.py` `Network`): DI's chains (`di_tracks.Source`) split into edges where tracks
  meet: record ends that meet, a branch's lone end on a track's middle, interlaced branches at their tips, chains
  crossing through each other. DI's drawing quirks are rules, counted in the build's log: a switch drawn as a
  section collapses to its tip (legs of 9 m or less), track ends facing each other within 2 m join, dead ends
  under 3 m go, nodes joined by edges under 2 m merge.
- **Passing a node**: only between edges whose directions out of it lie within 16° of opposite. Measured on DI
  2026-10-31: 912 of 913 switches' diverging legs leave within 15° of their toe; the corners of four-way nodes
  start at 15° (Nádraží Braník's shallow crossing 21-29°). Two chains crossing through each other go on as
  themselves however shallow (Vozovna Kobylisy, 14°); parallel tracks meeting at one node and still within 0.2 m
  of each other 10 m out (a gauntlet, Malostranské náměstí) continue the one on their side.
- **Routes** (`Match`): OSM's route nodes (the relations, or a GTFS run as before) matched as one sequence over
  the network, a hidden Markov model solved by Viterbi every 2 m: distance (σ 1.5 m), heading, the distance along
  the network against the route's step, and a state off the network at a cost where DI has no track (listed in the
  build's log). No OSM node is moved or merged; each route node gets its place on the matched line.
- **What is drawn**: the edges the routes run on, the other legs of their facing switches, and of every other
  edge the stretch OSM's track ways of the corridor run on (matched the same way).
- **From OSM**: which tracks a line uses, bridges and tunnels (by route node), the stops and signals as before.
- **Facing switches**: where a route leaves a node by one of two or more passes from the end it arrived by.
- **The user's facts**: a switch tip (`trackSources.switchTips`) moves its fork along the through track; an
  orthophoto track (`photoTracks`) replaces the edges it covers along 80 % of their length.
- **In the junction OSM has little say**: inside a zone (another track within 2.7 m; plain double track lies
  2.75-3.5 m apart) a route sample's position and heading weigh 5 %, and the network's connections between the anchors
  outside decide (the user, 2026-11-05: "ignore the exact place of osm track inside the junction").

## Staying on DI

The drawn curve (`tools/track_curve.py`, as since #204) passes within 2 cm of DI's points unless a rule below lets
it go. What pulled it off DI, measured on five lines (`tools/bench/track_deviation.py`, `tools/bench/track_fit.py`),
each now a rule, none a place:

- **Tightness is read at two scales**: 18 m over 5 m (as `tools/lint.js`), 15 m over 2 m (a bend squeezed into a
  metre). A single 20 m limit over 2 m read DI's own scatter of 2 cm as a 25 m curve and moved points up to 14 cm
  in curves all over the city; most of what lay over 2 cm from DI came from this.
- **A node stands on the straight track**: where record ends meet (within 0.5 m), on the pair continuing each other;
  where two such pairs cross, at their crossing. The mean of the ends lay up to 12 cm off the straight track.
- **A track ending beside its node gives up its points** within sqrt(h x 50 m) of it (h the step, at most 6 m back, none
  under 3 cm), and nothing is put on the chord they leave: the fit takes it to the node in an S bend of about 50 m. The
  user, 2026-11-06: "when you encounter end of di walk back".
- **Surveyed lines reach the fit with points every 2 m** (DI draws straights with vertices tens of metres apart: the
  fit sagged 0.41 m between them), and edges every 1 m before their ends move to their nodes.
- **A section's tracks start at its tip without Y's point**, each with the leg on its own side (Y is the middle of two
  ends 0.2 m apart: each track stepped 10 cm).
- **Crossing nodes stay apart in the fit**, exactly on both chains, however close (three chains crossing within
  0.4 m, merged, passed one point 13 cm off).
- **A gauntlet's tracks never touch**: parallel tracks meeting at one node, still within 0.2 m of each other 10 m out,
  get a node per track (at one node each was pinched 5 cm towards the other, 5.6° in 2 m).
- **What is kept in spite of those rules**: a track beside another is no copy where another track's end faces its end
  across a gap (Ohrada: 35 m, 20 cm beside the through track, its curve starts 5 m on), and an edge under `MIN_SPAN` is
  drawn where drawn tracks go on from both its ends (Strossmayerovo náměstí: 1.3 and 1.2 m between crossings).
  `tools/bench/track_holes.py` lists holes of the second kind.
- **An orthophoto track's chords stay empty**: only its measured centres are data. Filled, the 11.7 m chord from the
  switch at Podolská vodárna put a corner in the curve and moved it 0.48 m off them; empty, it reads 17.9-40.7 m over 5 m
  and lies within 0.114 m (mean 0.033 m). Moving either fork to where the circle through the points touches its through
  track (2 and 3 m along it) makes it worse: 13.8-14.3 m.
- **Connections are read against OSM**: distance to DI cannot see a wrong or missing connection, so
  `tools/bench/track_topology.py` compares the movements through each junction with OSM's graph, both ways round, and
  lists the differences for review. It found one lost connection at once (50.1324 N 14.4526 E). A branch ending past its
  fork now reaches the track it joins (`_folded_stubs`).
- **Copies and folds go**: a record turning back on itself splits, two records leaving one point the same way do not merge, a branch's copy
  running on the track is trimmed per end, and a chain with nothing left is a whole copy (these made the only folds,
  176-180°, at Kobylisy, Ďáblice and Hloubětín).
- **Gaps**: ends facing each other across a crossing track, up to 8 m, join along the archive's axis (Ohrada, the
  user: "sadly missing piece of data"), each going on as itself across the crossing.

What is left over 10 cm on the five lines is DI's own: record joints with a sideways step of up to 26 cm (the curve
passes in the middle), and the middle of a 1.1 m gap, which reads 0.42 m along the track from both ends. Under 18 m
stays held anywhere (`min-radius-network`): in the depots' yards, which no line draws yet, the whole network's fit moves
points up to 0.38 m for it.

- **Kept**: the curve fit's method and the heights.

## What it changed

Line 17 (on DI since #20): routes within 0.23 m of before, the same 19 facing switches, drawn tracks 16 m of
60.1 km different. The other lines: the PR's table.
