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
- **Kept**: the curve fit (`tools/track_curve.py`) and the heights.

## What it changed

Line 17 (on DI since #20): routes within 0.23 m of before, the same 19 facing switches, drawn tracks 16 m of
60.1 km different. The other lines: the PR's table.
