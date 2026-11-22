# Knowledge: data quirks, conventions, why the heuristics exist

What sessions learned and later work needs. Kept current and short; the full logs are in
[history/](history/) (HANDOFF.md §n, REMOTE-CHANGES.md §n). Tasks are GitHub issues, not here.

Sections:

- [Coordinates and heights](#coordinates-and-heights)
- [Sources and their quirks](#sources-and-their-quirks): [OSM](#osm), [PID timetable (GTFS)](#pid-timetable-gtfs), [DI track geometry](#di-track-geometry), [Track heights: the archive, DI and the lidar](#track-heights-the-archive-di-and-the-lidar), [Terrain and the street survey (IPR, ČÚZK, ZPS)](#terrain-and-the-street-survey-ipr-čúzk-zps), [Buildings and structures (Geoportál, Mosty 3D)](#buildings-and-structures-geoportál-mosty-3d)
- [The T3 and the network it runs on](#the-t3-and-the-network-it-runs-on)
- [Heuristics that stand in for missing data](#heuristics-that-stand-in-for-missing-data)
- [Checks and what they measure](#checks-and-what-they-measure)
- [Czech tram terms](#czech-tram-terms)
- [Environment (Windows dev machines)](#environment-windows-dev-machines)
- [The test host](#the-test-host)

## Coordinates and heights

- **The city frame** (`tools/geo.py`, every tool; [decision](decisions/2026-10-29-city-frame-and-tiles.md)):
  game metres = S-JTSK (EPSG:5514) minus the Marian column (−742 806, −1 043 024); every line shares it
  (`data/lineN.json` `frame`). Lat/lon goes through ČÚZK's grid as a pinned PROJ pipeline (the grid file
  is in the snapshot, `raw/proj/`); survey data (DTM, DMR 5G, IPR rasters) is a plain shift. S-JTSK is
  9.6 cm/km short of true length, and grid north is 7.8° off true north.
- **The ground's tiles** (#30, 2026-11-17): 500 m squares on the absolute S-JTSK grid (`geo.TILE`, the decision's), named
  by their south-west corner's index (`e-1486_n-2087` holds the origin: it lies 24 m south of N −1 043 000). The build's
  squares and its 5 m and 25 m lattices lie on that grid, so a tile's border holds the same vertices on both sides. The
  page draws only the tiles within the fog's end of the camera and of 1 km of route ahead. A tile's normals on its
  border take its neighbours' triangles: from its own alone, a 500 m line would show where the two sides average
  different triangles. Line 37, driven every 200 m (`tools/bench/ground_tiles.py`): 31 of 106 tiles drawn on average,
  mesh arrays 32 MB of 77, lookups 21 MB of 48.
- Until 2026-10-29 each line had its own lat/lon origin and a flat-earth scale (110 574 m per degree of
  latitude, 111 320·cos(lat0) of longitude): 0.59 % short N–S, 0.20 % E–W (line 17 was 100 m short), so
  positions quoted in older notes (route `s`, x/y) are off by up to that much.
- **Layer registration** (`tools/registration.py --line 17|22`, against the DTM survey; 2026-10-29): IPR LOD2
  buildings 0.04–0.10 m, OSM buildings 0.06–0.10 m, trees 0.2–0.3 m, tree rows 0.16 m from the trees.
  IPR's hosted feature layers are stored in Web Mercator, and each was loaded from S-JTSK with its own
  datum shift: the **tree register's lat/lon is ~10 m off** (ask its service for S-JTSK, `outSR=5514`,
  which `geoportal.py` does), while the tree rows and the archived DTM street points are right as
  lat/lon (asking those for S-JTSK puts them 6–10 m off: −6.24, −7.67 m at Trojanova; naming a
  `datumTransformation` makes it 170–300 m, 2026-11-05, #258). A new Geoportál layer gets measured both ways
  before use. The current DTM's JVF packages (DI, TI, ZPS) are S-JTSK natively.
- **The tree rows are lines drawn along a row, not its trees** (#649, near line 22, 2026-11-18): of the 169 rows
  with register trees along them, 104 lie within 0.5 m of those trees and 141 within 1 m, 6 are 2–4 m off and 6
  more than 4 m. The other ~1100 rows have no register trees (owners other than the city: the castle's limes),
  and nothing but imagery places them. The castle's row south of Mariánské hradby runs 2.5 m into the
  carriageway, its trunks 2.5 m behind the kerb (5 m). A row's samples near a register tree repeat that tree
  (`src/trees.js` ROW_DUP); samples on a carriageway move to the nearest other ground (ROW_SNAP).
- **Heights are Bpv** (Baltic after adjustment) in DMR 5G, the DTM survey and Mosty 3D alike: measured,
  the model tops sit 0–0.5 m over the surveyed decks (an ellipsoid mix-up would be ~45 m).
- Archived track Z is guarded separately from DI geometry by `tools/track_heights.py`; the staging
  command and evidence contract are in [the fallback decision](decisions/2026-10-30-track-height-fallback.md).
- Geoportál I3S layers are Web Mercator with absolute heights; the orthophoto ImageServer is S-JTSK.
- The track ribbon is drawn 0.20 m (bed) and 0.26 m (rails) over the profile height: rendering offsets
  to redefine with "what each height means" (M2).
- Bpv vs EVRF2007 in Prague: 0.13 m (ČÚZK's `vertoffset` in PROJ, EPSG:8357 → 5621).

## Sources and their quirks

### OSM

- **OSM** (local extract only, [decision](decisions/2026-10-23-local-osm-extract.md)): route relations
  PTv2; track ways are merged into chains split only at junctions and bridge ends (no smoothing kinks).
  Tunnels from `tunnel`, `covered=yes`, negative `layer`. OSM splits tunnels and bridges into many ways:
  heights must run along the whole chain (`chainTunnels`), or inner ends take the hill top or the river.
  Interlaced track is tagged `railway:interlaced=yes` (Letenská).
- **Switch detection** (facing only): a route node with an extra track neighbour heading forward; a
  neighbour on a track passing straight through is a diamond crossing (line 22: 16 of 33 "switches").
- **OSM maps a tram under reconstruction as `railway=disused` + `disused:railway=tram`** (Libeňský most,
  `bridge=yes`, 2026-11 extract) while the 2026 DI keeps the track; tools that select `railway=tram` miss it.
  The DI's own track there is new (inserted 2025-01-30, 24 m pieces, Z = 0).
- **OSM joins a crossing and a switch in one node** (Strossmayerovo náměstí, Palackého náměstí: nodes of 5-6
  edges) where DI has them 0.4-0.5 m apart; a node placed nearest all its tracks lies off each of them.
- **OSM draws interlaced track as one way** (#204): a `railway=switch` node at the tip (often with its number,
  `ref` 111 at Čechův most), one way both routes share, and the split where the tracks part at a
  `railway=railway_crossing` node noted "rozjezdová/sjezdová splítka" (diverging/converging interlace). Where DI
  draws the tongue, its tip lies 0.4-3.3 m from OSM's switch (Dejvice, Chotkova, Čechovo náměstí); where DI starts
  the branch 13 cm off at a record joint, OSM's switch lies a tongue (8.0-8.8 m) before it. Malostranské náměstí
  is a gauntlet with no switch: crossing nodes at both ends, the two directions interlaced for 45 m.
- **OSM roads drawn over the rails** (#344, the `railSupport` places left after the heights): where the street way runs
  onto a bridge, `ground.at` gives it the ground under the bridge, at the abutment level with the deck (Most Legií, 8-18 cm
  over the rails); a road tunnel under 60 m is drawn open at its portals' grade, so an underpass under the tram lies across
  the rails (50.0755 N 14.4303 E, 28 cm; 50.0884 N 14.4325 E, 15 cm); a road crossing the track between two of its nodes
  is linear between them (50.0707 N 14.3802 E, 7 cm). W3's ground surface (#276, #301) replaces this drawing.
- **OSM has no grassed-track tag on the tram ways**; mappers draw the grass as areas over the track (`landuse=grass`,
  `village_green`, `leisure=park`: 2026-11 extract, #503). Inside the known grass spans (the user's marks and
  prazsketramvaje.cz's list) they cover 3.7 km and stop 2-5 m short of a footway crossing, 5-15 m of a street's edge
  and 3-4 m of a platform: `tools/track_styles.py` `HOLE`. Switches get no hole: open ballast runs through them
  (the Depo Hostivař branch, the user 2026-11-12), and one in a street lies in the street's hole. They miss 6 km of the known grass
  (Sídliště Řepy - Slánská, most of Malý Břevnov - Obora Hvězda), and some lie under our bridges (Střelecký ostrov's
  park under line 22 at Újezd), so OSM's grass outside the facts goes to the user's review (`tools/grass_review.py`).
- **A platform paves both tracks at most stops in grass track**, the two directions' platforms staggered or not
  (#584, 2026-11-14 orthophoto: line 37 at Českomoravská, line 9 at s 15500). Holes on the platform's track alone
  would have drawn 1.3 km of grass on the other one, most of it the grassed-track list's stop-to-stop extent where
  both tracks are paved. Drinopol (line 22) is the exception the user named, the only one they know: each platform is
  also a (replacement) bus stop, so the asphalt runs from the road across the near track to the platform, and the
  far track stays grass. Nothing in the data tells them apart (the survey maps both as `tram` there, OSM's tram ways carry
  no surface), so a track differs only where a mark says so (`trackStyles` with `track`, data `stylesBack`/`liftBack`).
- **OSM's Vltava is one multipolygon of untagged ways, its islands inner rings** (2026-11 extract, #632). The extract's
  index keeps tagged ways only, so `tools/ground_partition.py` `osm_water` reads the members with a pass over the
  extract (~10 s). The line data's `water` (`tools/build_line.py`) keeps outer rings only: Štvanice, Střelecký and
  Slovanský ostrov lie in the river there (line 17: 0.40 km² of land in its water). Weirs, dams and lock gates are
  `waterway=*` ways, most from bank to island, a few in pieces between piers (Štvanice's south channel); Čertovka and
  the side channels pass the weirs with no weir mapped across them, so the weirs close no pool (`WaterLevels`).
- **OSM `maxheight`** under the route gives underpass clearances (`tools/clearances.py`; default 4.2 m
  car roads, 2.5 m footways), applied only where the track is already ≥ 2 m over the road.

### PID timetable (GTFS)

- **PID GTFS**, service date fixed at 2026-10-21. Line 22 needs `--headsign "Zahradní Město"`. Line 9 is
  built as a 9 → 10 run. Line 37 (a substitute line) has no OSM relation: built from its GTFS shapes,
  which run between the two tracks in places; the matcher prefers the right-hand track (regular
  service always uses it, `data/truth.json`).
- **PID GTFS `route_stops.txt` lists no route at stops only some trips serve** (#407): Pražský hrad and
  Královský letohrádek (lines 22 and 23), Národní divadlo C/D (17, 1, 11) and Brusnice C/D have trams in
  `stop_times.txt` but no route there. Which stops are tram stops comes from the trips of the service date
  (`tools/platform_match.py` `tram_lines`). PID's stop point is where the tram front stops: it can stand past
  the end of the platform OSM drew (Klamovka A on line 9: 38 m), or on the track itself (Pražský hrad B:
  0.6 m off the centre line).
- **PID GTFS `block_id` links through-running trips only** (older notes said it had none): on
  2026-10-21 each of line 9's 427 blocks is one 9 trip and the 10 trip it becomes, and lines 17, 22,
  23 and 37 have no `block_id` at all. It is not a vehicle's day (no run numbers, no depot runs).
  A two-line run pairs trips by it, never by time (#96): 195 of 200 line 9 arrivals at Nákladové
  nádraží Žižkov continue as line 10 with a 0 s gap; the old 2–25 min time window had paired 198, none
  in the same block. `tools/audit_run_timetable.py` checks a built run against the GTFS.
- **A two-line run's `pathBack` holds both directions** of the streets the run covers twice (9 → 10
  leaves Řepy and returns to it over the same tracks: s 0–8 km and 20–28 km): the closest piece of it can be our own track. Matching
  onto another route takes the heading into account (`Route.nearestOnHeading`); plain `nearest` there
  spawned oncoming trams on our track and made two false 8 km gauntlets on line 9 (28 signals lost).
  A platform there lies as near to the back path as to the route, and goes to the back path by a hair
  about half the time: 15 stops of line 9 had a second, opposite-direction sign beside ours. The game marks
  a platform the route passes on its doors' side as `ours` and draws no other sign there, but keeps it on
  the back path, whose trams stop at it (`src/traffic.js` `backStops`, #22).
- **PID GTFS shapes are OSM's**: line 17's shapes run on the double track's midline and match OSM's midline
  to p50 0.04 m (#20); they cannot judge OSM against DI.

### DI track geometry

- **DI track records** (#20): pieces from 0.1 m to a few hundred metres, ending where the next begins
  (19,227 of 20,742 ends exactly, 1,168 more within 0.5 m). Some pieces are there twice under two IDs and
  some have zero length (45 dropped city-wide); counting record ends alone, a straight track looks like a
  fork. OSM differs from DI by p50 0.13 m / p90 0.45 m at line 17's nodes, but draws curves as chords up to
  2–3 m off (Křižovnická, where the orthophoto's rails lie on DI's), switches up to 5 m from DI's forks, and Kobylisy's pair 2.5–3.3 m apart (DI
  3.5 m). DI (state 2026-09-30) lacks the track OSM maps at 50.0502 N 14.4154 E (ways of 2025–26).
- **DI's tracks at junctions** (#197): joined straightest through each fork, the 16 districts' DI is 656 tracks
  with 955 forks and 575 crossings. At a crossing the two tracks' staged heights differ by p50 1.6 cm, p90 7 cm.
  A junction is not one point: a fork's diverging end and its crossing with the through track lie 0.003–1.6 m
  apart, the ends of a junction's short pieces up to 0.5 m apart (on a 4 % grade, 2–4 cm in height), and near
  Ke Stírce a piece lies along another for 30 m under its own records (not caught as a copy: it does not join the
  same two places).
- **DI draws a switch three ways** (#204): records ending together and leaving apart (a fork of record ends);
  a branch ending on the middle of a through record that is not split there (Palackého náměstí, the branch
  19.8 m along it); interlaced track (below), where the switch is the branch's start, not where it leaves. At forks the branches' first points lie up to 0.18 m apart: the fork is their mean. OSM's
  switches lie up to 7.4 m from DI's forks along the track (Jiráskovo náměstí; the user's answers of
  2026-11-03), and OSM and DI can disagree on which leg is the straight one in a curved switch (Křižovnická).
- **DI can be off the rails by more than its class** (#204): Podolská vodárna's north curve (50.0591 N 14.4195 E)
  runs 19-34 cm inside the rails measured on the orthophoto over 14 m and reads 14.6 m over 5 m (16.4 m in the
  state of 2026-09-30, the archive 16.2 m); the rails read 18.3-20.1 m over 6 m. The south curve there agrees with
  its rails within 9 cm. The track there is taken from the photo (`data/truth.json` `photoTracks`).
- **DI draws some switches as a section** (#204): both legs as records from the tip to a joint 4-5 m on, where
  the track and the branch go on (48 in the 16 districts, Dvorecký most's of 2026-10-07 among them). The legs are
  apart only beyond the joint, so the fork of record ends lies there; the tip is where both legs start. At
  Dvorecký most the tip has the ZPS survey's switch machine cover (a small rectangle among its traffic-area lines)
  and OSM's switch (the user: "the OSM marker is on point there, it's right at the yellow rectangle which here fits
  the přestavník"). Elsewhere OSM marks 29 of the 48 nearer the tip, 19 nearer the joint.
- **The archive draws Dvorce's old connection** (#204): DI (2026-09-30) and the archive (2008-2024) have
  no track onto the new Dvorecký most (opened 04/2026: "No data is related to new Dvorecký most put in
  service in 04/2026", the user, track sources review, 2026-11-03); where OSM's new edges come within 2 m of
  the archive's old track it takes them, as a zigzag with 20° breaks.
- **Every DTM record states its accuracy class** (#204; `data/truth.json` `sourceAccuracy`, the classes of
  vyhláška 393/2020 Sb.): DI's tram axes are class 3 (0.14 m in plan, 0.12 m in height) but 7 of 10,371 in
  class 2; ZPS lines are class 3 in plan (3.2 M) or 4 (0.7 M) and **class 5 in height** (3.2 M lines, 0.35 m),
  class 3 for 0.7 M. The archive states none; DMR 5G guarantees 0.18 m (0.30 m under dense vegetation); IPR's
  1 m terrain and the orthophoto state nothing. Counted 2026-11-03 on the state of 2026-09-30, 16 districts (moved
  here from `truth.json`, #224), class: records in plan / in height:
  - DI axes (`tools/dtmp_tracks.py` `di_data()`): 3: 10,364 / 10,364; 2: 7 / 7.
  - ZPS lines (the `ZPS_KR.gpkg` files): 1: 0 / 1; 2: 1,065 / 1,065; 3: 3,226,053 / 700,785; 4: 701,195 / 21;
    5: 5 / 3,156,921; 9: 52,246 / 121,771.
  - ZPS areas (the `ZPS_OPL.gpkg` files): 2: 149 / 149; 3: 266,689 / 50,249; 4: 193,705 / 0; 5: 6 / 378,988;
    9: 15,863 / 47,026.
- **A connecting curve held at both switches keeps the radius DI gives it** (#204): its ends and directions
  are fixed by the through tracks, so widening the tolerance cannot change it; 24 places on line 17 read
  18.5-19.9 m over 5 m (Dlouhá, Strossmayerovo náměstí, Podolí, Kobylisy), needing the switches 0.5 m off
  to reach 20 m. A bend squeezed into a metre reads much wider over 5 m (10° as 29 m), so the curve fit
  measures its own radius over 2 m.
- **Near a switch the branch is the nearer track for metres** (#204, Strossmayerovo náměstí): a tangential
  branch is 0.09 m off the straight at 3 m, 0.16 m at 4.2 m and 0.5 m at 7.3 m, and DI bends the straight 0.9°
  at the switch, so over 3 m the branch reads straighter than the straight, and a 4.75 m OSM edge between two
  switches lies nearer the branch. Two switches 4.6 m apart on each track there (DI): the west track's to the
  left first, then to the right; the east track's mirrored. OSM puts the westward turn's switch on the
  east-west track 3.8 m past DI's fork, beside another switch 2.1 m away whose branch leaves the other way.
- **A resampled curve reads tighter than it is** (#204): points interpolated on chords lie inside the arc (7 mm
  on a 1 m chord of a 19 m curve, 15 mm on a 1.5 m one), so a circle through them read 19.1 m as 17.4-17.6 m
  (Právnická fakulta), and the game's three-point average with a 1.5 m resample turned a 0.9° joint into 3.7°
  at a short piece's end. Rounded to the centimetre, points 0.4 m apart read a 19 m curve as 15.5 m over 2 m.
  Radii and joins are measured on the build's own points, written to the millimetre.
- **The route the game drives is built** (#477, #276 step 2): the path and the run 60 m past both termini
  (`pathExt`, `tools/route.py`), its points as they are. Resampled every metre (until #477), the chords cut each
  point of a curve drawn every ~1 m by about a quarter of its turn: 1.0-1.1 cm on 23-24 m curves of lines 22 and
  23, 1.9 cm at a 4.5° turn on line 9 (s 15958). Read as built, the speed limits moved 1 km/h in 0-2 bins of our
  route per line and 0-8 of the opposite one, the cant at most 0.16 mm, and placement's junction edges
  (`tools/placement.py` shares the sampling) 0.3-0.5 m at three signals, 2.9 m on line 23 (s 4920) and 15 m on
  line 22 (s 14351), where a conflict sits at the rule's threshold. The run follows the drawn
  chains in the most aligned direction and goes straight on where none continues, also where a chain ends
  exactly at the path's end (it wins the walk's choice and has nothing ahead). Built against the page's walk it lies within 0.65 mm on every line (the
  millimetre rounding). The opposite track's spread to 3 m (`trackfix.js`) went with it: since the DI track it
  moved no point on any line.
- **The route's radius and cant are built** (#478, `tools/cant.py`): the radius at every metre (the heading change
  over 16 m, written as 1e9 / r) for our route and the opposite one, the cant every 2 m for ours (0.01 mm). Against
  the page's own computation the speed limits are identical on every line and the cant within 0.005 mm. At 1e6 / r
  the radius was 0.07 % off near 1500 m and three 5 m bins moved 1 km/h (lines 17 and 23), where a whole km/h sat on
  the edge; 1e9 costs 365 KB on line 9. The page keeps `radiusAt`, `cantAt` and `rollAt` as lookups.
- **DI re-enters records and keeps the old ones** (#209): the state 2026-10-31 has 1,112 records of 2025-01-30
  and 2026-05-27 (30 km) lying on records entered 2026-10-07 under new IDs, within 8.8 cm (median 0-1 cm), some
  split at other places. 967 of the old ones had zero Z, their re-entries have heights (height class 3), equal to
  the old where both had them (median 0, p90 2 cm): DI heights now reach 63-71 % of each line's path (were
  25-47 %). The old records at Podolské nábřeží run on through the new Dvorecký most junction, where the re-entries
  end at its switches. `di_tracks._latest` drops an older record lying on newer ones (1,057 city-wide).
- **DI's scatter and joints** (#237): a curve through DI's points within 2 cm reads a 25 m radius over 2 m from scatter
  alone, so a radius is read over 5 m and only a kink over 2 m. Record ends meeting at a fork lie up to 0.5 m apart
  (their mean up to 12 cm off the straight track), some record joints step sideways by up to 26 cm (Čechův most's
  approach, 50.0934 N 14.4168 E), and two records may leave one point the same way, or a whole record copy the track
  it lies on (Kobylisy, Ďáblice, Hloubětín). The rules: [the decision](decisions/2026-11-05-track-network-from-di.md).
- **Interlaced track after a switch** (#204; `data/truth.json` `trackGeometry` `interlaced-switch`): at Čechův
  most, Ke Stírce, Ohrada–Krejcárek, Biskupcova–Ohrada and 15 more places DI draws the branch 9-17 cm (mostly
  12-13 cm) beside the track for 11-87 m from the switch's tip before the tracks part, either from a tongue it
  draws (0 to 12 cm over 8-9 m: Ohrada, Dejvice) or from a record joint already 13 cm off (Čechův most). Where
  both tracks are split into short records, their joints 12 cm apart fall into one cluster of ends. OSM puts
  the switch at the tip (5-7 m from it at Čechův most), the user: "the fork starts and ends well in front
  of/behind the road junction".
- **Interlaced tracks' record ends lie within JOIN of each other** (#368): 10-15 cm apart, where DI splits both tracks
  at the same places (Nádraží Libeň: every 6-27 m over 39 m) or starts or ends the branch beside a record joint of the
  through track (Ke Stírce 11.7 cm, Čechův most 12 cm with the through track's joint 0.6 m apart). Grouped as one place,
  the node lay on the branch and the line stepped 10-12 cm through it, or the through track's records were dropped as
  copies of the branch's (two records between the same two places, within 20 cm) and line 37 ran the branch for 35 m:
  the user's "sideways jolts" (2026-11-07). 14 such places in the network, 6 on the lines. `di_tracks._meetings`: an end
  whose track goes on in line does not meet an end beside that track, nor two joints side by side.
- **An interlaced switch splays both tracks** (#368, 2026-11-08): unlike a classic switch's straight track, neither
  leaving track continues the approach (the user, on a street-view photo of Čechův most). DI agrees: 7 m past the tip
  the two tracks lie +4.7 and -8.7 cm off the approach's axis (rms 0.3 cm along it), and DI draws those first 4.6-10 m
  as one straight from the tip (the 18 tips of the network). Fitted as a straight track and a branch, the branch left
  along the through track's tilt and bent 1.2 degrees over 2 m. `track_curve` `approach`: the approach is fitted first,
  both tracks leave along it, the tongue chord's interpolated points are no data.
- **A track end walked back to its node keeps DI's record end** 1.8-2.3 m from the node (`Drawn`, `walk`): it is no
  node and an answer that frees the points around it frees it too (Čechovo náměstí: held, it hooked line 22's track
  3.5 cm in the last 0.76 m before the fork, 3.4 degrees).

### Track heights: the archive, DI and the lidar

- **The archived track heights (the `archive` candidates, 2008 records) under a structure measure what
  lies below it** (#176): at Modřany → Belárie the archive follows the embankment within 0.2 m of the
  lidar ground, then drops 6.4 m in 5 m to the street under the bridge (201.2 → 194.7 m) and climbs back 40 m on; Hodkovičky and Černý kůň are alike, Palackého most
  stays on the river bed (187.3 m) across its whole span, Hlavní nádraží's tunnel climbs 6 m to the
  street above. A track climbs a few per cent: an archive step over 10 % between points ~5 m apart is the
  archive measuring something else (`tools/track_span_evidence.py` `dips`). It starts down before the steep
  drop (Černý kůň: 4–5 % for 14 m, Modřany inbound ~8 % for 50 m), so a dip extends over the descent
  and climb above 4 % around it (#184).
- **The two directions of a line agree in the archive** (#184): over the 9806 archived axes, parallel axes
  2.5–6 m apart differ by p50 0.02, p90 0.09, p99 0.45 m; more than 1 m on 0.4 % of 64,712 samples, mostly
  structures. Where one direction leaves the other there, it measured something else: Hlavní nádraží
  +6.9 m and +6.6 m (the road over the tram), Modřany inbound −6 m (the street under), Brusnice −1.1 m.
- **Archive and DI share their heights where both exist** (#188): where the archive breaks a 500 m vertical
  radius, it equals numeric DI to a median of 3 mm, so DI cannot judge the archive's wiggles. Over 5 m bins,
  1–2 cm of noise already breaks 500 m: the 2023 lidar does so on 19.6 % of paved bins, the archive on 18.3 %
  ([vertical profile](decisions/2026-11-02-vertical-profile.md)).
- **In the tunnels and structures DI added by 2026-11-06, it does not share the archive's heights** (#390):
  numeric DI lies 0.1–0.2 m under the archive along Hlavní nádraží's Seifertova tunnel, 0.45–0.55 m under it
  in Wilsonova's outbound track, and the raw DI the import rejects runs up to 1.5 m under it through
  Malostranské náměstí. A series mixing the two at 1 m spacing steps 12–46 %, so the review answers
  judge the archive's own heights.
- **Where only the archive has a height, the 2023 terrain checks it** (#190): where a ZPS survey confirms
  the archive, the two differ by more than 1 m on 13 of 45,577 samples (0.03 %); without a survey 848 samples
  do (Malovanka 83 m, the Libeň bridge's dips to the streets, Troja's old alignment). Numeric DI agreeing with
  the archive 7 m under the terrain is a structure the terrain cannot see, not an error
  ([height fallback](decisions/2026-10-30-track-height-fallback.md)).
- **The robust smoother runs away where its radius is wrong** (#197): `vertical_profile` stops pulling towards
  points it misses by more than 0.23 m (Tukey). Where the design radius cannot follow a real sag (Malostranská,
  ~300 m, the archive and the terrain agreeing to 2 cm), it drops the whole stretch and runs 1–3 m under the data,
  not 0.3 m. Points at weight 0 do not fix a curve either: across a 40 m hold it sagged 5 cm under the straight
  grade (`tools/line_heights.py` starts held points on that line at weight 0.001).
- **DI can hump on one track alone** (#344): line 9 at Sídliště Řepy, DI's outbound track rose 0.97 m over the lidar for
  90 m while the return track 3 m beside it, the archive and the lidar under both agreed within 0.2 m. Where DI is the
  source, the archive sided with the lidar at every such stretch of the network; on a bridge it does not (the bare-earth
  lidar and the archive both lie under the deck, DI 6-14 m over them: the `structure_hint` flag). `archive_over_di`.
- **The lidar settles most held heights** (#202, 2026-11-08): where the archive and the survey disagree by over 0.3 m and
  DI has a height too, the source the 1 m lidar lies within 10 cm of matched DI at 148 of 155 bins (the archive 137 of
  141, the survey 11 of 14). On ordinary track the rail lies a median +1 cm over the lidar (p10 -7, p90 +18 cm). The
  lidar alone is no height for a funicular: Petřín's, held its whole length, took the hill's bare earth in steps of
  2-6 m. `held_settled`: held stretches over 60 m 81 -> 50 network-wide, 5 -> 0 on the lines' routes.
- **An archive record states its survey year (`ROK`), which says whether it or the 2023 lidar is the newer** (#539,
  2026-11-22): `DAT_VZNIK` is the database's (2008-03-10 on the 1,892 records of 1999, 53.9 km), `ROK` the survey's.
  Records up to 2022 stand over 0.5 m over the lidar on 0-1.1 % of their points (those within 1.5 m of it), records of
  2023 on 4.9 %, of 2024 on 9.1 %: tracks rebuilt since the flight. Line 9 at Bertramka: both tracks' records of 1999
  hump up to 0.83 and 0.92 m over the lidar for 200 m, the survey 0.3-0.4 m over it, the lidar level across the street
  with its kerbs, DI without heights (`NeuplnaData`); the user: the track lies in the asphalt level with the road.
  Where numeric DI can judge (samples off structures, an older record 0.5-1.5 m over the lidar): on paved track DI
  sides with the lidar at 71 of 76 (the 5: one 20 m stretch at (3405, -439), a record of 2006); where the construction
  is unknown at 23 of 52 (a ballast bed on its own body, small bridges nothing marks), so the rule holds on paved
  track only. Under the lidar the same holds with a smaller margin: where an older record lies 0.2-1.5 m under it on
  paved track, DI lies with the lidar at 694 of 725 samples (within 0.1 m of it at 90 %, median -0.1 cm), and at 176 of
  184 even where the survey agrees with the archive; on track of unknown construction DI lies with the lidar too (868 of
  871) but over it by a ballast bed's height (median +5 cm, p90 +23 cm), so the rule keeps to paved track both ways.
  `archive_before_lidar`: network-wide the over side moves Bertramka (445 m of track) and one track at Letenské
  náměstí (a record of 2013 on a 1.0 m plateau for 25 m beside a track on the lidar; the user, 2026-11-22: "both track
  at the same height ... there shouldn't be 1m step anywhere near").
- **Two junctions lie on the ground under 500 m** (#358, 2026-11-08): Královka's loop arms and Malovanka, where the
  user's photos show the paving following the slope. Held at 500 m, Malovanka's curves lay up to 40 cm off the 1 m lidar
  and its junction still needed 355 m (meeting points metres apart). The archive put Královka's arms 15-78 cm above the
  ground: its 12 % ground step had been dropped as steeper than any track. The tracks follow the lidar in the
  user's areas, no tighter than 250 m: unlimited, Malovanka read 131 m, a 2.4 cm lidar bump over 5 m
  (`data/truth.json` radiusAnswers with `area`).
- **The heights read IPR's 1 m raster, and the ground file draws it** (the city mesh, `tools/city_terrain.py`, #276;
  the 2 m fine blocks it replaced lay within mean 0.6-0.9 cm, max 6.4 cm of the raster at the tracks at Královka and
  Malovanka).
- **ZPS track areas on bridges are not rail height by themselves** (#184): on the queue's bridges level-0
  tram areas lie p10 −1.53 / median −0.26 / p90 +0.11 m from the smooth archive. At Černý kůň they and the
  level-1 deck meet the archive within 0.2 m on both sides and carry on across the dip (198.9 → 198.2 m).
- **ZPS track areas on the Modřany embankment lie ~2 m below the archive and the lidar ground** (s 408:
  survey 198.6, archive 200.8, lidar 201.0 m; flagged `track_zps_level_unverified`), which is why the
  drawn rail there is low and wavy. The level-1 tram area over the Modřany underpass carries the
  ground's heights (194.9–195.8 m): the survey has the deck's outline but not its height.
- **Track height checks depend on construction** (#106): paved embedded/panel/setts surfaces can
  describe rail level, including a dedicated raised paved strip. Open-track outlines can describe
  ditches or embankment edges; they neither supply rail Z nor veto the archive. A generic ZPS tram
  area does not identify its material, and the panel drawing default is not evidence of pavement.
  Railway-bridge surfaces can be above the tram and are excluded. Numeric DI calibration, the
  Koh-i-noor – Slavia green-surface sample sites, and the separate drawing/survey height meanings
  are recorded in [the height fallback decision](decisions/2026-10-30-track-height-fallback.md#calibration-and-review-response-2026-11-01).
- **A DI track crossing ours measures the street's tilt there** (#538): its heights where it meets our left and
  right rail, each taken against our own rail profile at that point (on a 30° crossing the two lie 3 m apart
  along ours), differ by the cross level. Where one DI track crosses both of ours the two values agree within 2 mm
  (median), 6 mm (p90). On the five lines' 120 crossings on paved double track this is the only independent check
  of a street's crossfall: the median of IPR's plane, the survey's plane and our two tracks' slope errs 6 mm
  (median), IPR alone 10 mm and with a +7 mm bias, though the three-cornered hat gives IPR the smallest spread
  (0.2 %, the survey 0.8-1.1 %, the tracks 0.4-0.5 %): IPR agrees with the others most and with DI least.
  Sokolovská: DI 2.6-2.9 % over the gauge, IPR 5.2 %. `tools/cross_level.py` takes DI's value where it exists.

### Terrain and the street survey (IPR, ČÚZK, ZPS)

- **Sources per layer** ([decision](decisions/2026-10-30-source-per-layer.md)): the order and dates are in
  `tools/sources.py`; every built file says per list where its features came from (`provenance`, `fb`).
- **The survey's medians** (Dělící pás, 010000001503, #555) carry no surface, and some are mapped twice: of line
  22's 31 within 40 m of the route, 8 lie mostly under a `tram` area (the tram reservation between the
  carriageways), 6 on `road`, 15 alone. Read since #555 as `median` (raised like an island, green where OSM's grass
  covers it: `tools/zps_medians.py`), they fill strips the page drew as sunken terrain: Modřanská's middle (line 17
  s 4370), Bělohorská beside the track (line 22 s 4160). Where OSM maps the divided road as one two-way way, the
  cars' fit took one carriageway and laid the other direction's lane in the gap or the opposite carriageway; it now
  spans both and divides at the median (`src/traffic.js` `_fitRoad`, `laneOffset`).
- **IPR 1 m terrain** (`tools/ipr_dtm.py`): bare earth from the 2023 lidar, one 2 GB BigTIFF (tiled,
  LZW). Its cell centres sit 0.72 m / 0.61 m off the S-JTSK metre grid (sampled bilinear, never copied);
  it states no datum, and measures Bpv (+0.016 m over the ZPS street lines on line 17, ±0.03 m against
  DMR 5G per line, checked on every city mesh build: `dmr5g.datum_check`; a Bpv / EVRF2007 mix-up is 0.13 m). It has
  no covers over passages (underpasses, culverts: bare earth shows the passage). The lines' 2 m fine blocks took DMR
  5G near OSM passages, which kept the covers (the passages rule, gone with them, #510); the city mesh keeps IPR
  (#428): a street or track over a passage is a deck in #276's partition. The rule also took roofs, garages, building
  interiors and proposed tunnels (decision record 2026-11-05, "No passages rule").
- **Terrain under 170 m is no ground** (`sources.TERRAIN_FLOOR`, read by every terrain source; the user,
  2026-11-09: "I would put lower limit to 170 metres height which is well below lowest point of Prague"). IPR's
  image (35,001 x 26,001 cells) holds 660,025,394 cells of 170.73-421.15 m and 250,035,607 of its declared
  no-data, -3.4e38 (GDAL_NODATA tag 42113, `NoDataValue` in `dtm_1m.tif.xml`): the counts of its own statistics
  (`.aux.xml`), no cell of 0.00 m, none under the floor. The 5,739,063 cells of 0.00 m found in #325 are the padding
  of its 128 m tiles past the image's south and east edges (274 x 204 tiles hold 35,072 x 26,112 cells): a reader
  that decodes whole tiles crops them (`IprDtm.cells` checks the bounds, `tools/bench/terrain_city.py` and
  `tools/city_terrain.py` crop). IPR has ground over the whole of Prague (OSM relation 435514, 496.2 km²) and
  164 km² beyond, its no-data no nearer the limits than 47 m (a 10 m sample; 1.5 km in the median): the city
  terrain needs no fallback (#428). DMR 5G has real cells under the floor: line 17's 10 m grid holds 57 cells of
  163.1-169.8 m at Troja (50.1139 N, 14.4290 E, 334 m from the track), a pit in the 2009-2013 lidar (Trojský most
  and the Blanka tunnel were built there 2010-2014), where IPR's 2023 lidar reads 180.1-187.0 m: the floor fills
  them from their neighbours at line 17's next `build_line.py`.
- **ČÚZK DMR 5G**: bare-earth lidar (embankments over underpasses are in it), 2 m TIN raster; the coarse
  10 m grid of a line, and the city mesh's fallback inside the city where IPR has no data.
- **Prague DTM / ZPS survey** (street areas, kerbs, points): every district a line's 80 m corridor touches
  (`tools/dtm_packages.py` `DTM`, `--check` recomputes it from the OSM district boundaries). The hand-made
  lists before #125 covered under half of line 22 (no Praha 1 or 6) and missed line 17's Troja and Libuš,
  with Trojský most. Its vertices are far apart (big river triangles), so terrain is lowered vertex by vertex under surveyed areas.
- **`lineN.dtm.json` areas keep their holes apart** (`r` the outline, `h` the holes: 958 of line 9's 9,336
  areas), and **some outlines cross themselves** (22 on line 9, among them the 27,644 m² carriageway of
  Seifertova). The game triangulates both as they are (`src/terrain.js`); a tool reading them with shapely
  takes the holes and repairs the ring (`make_valid`), or it loses the area: dropped, Seifertova's carriageway
  hid the Vienna-type stop Lipanská A (#22, `tools/placement.py` `Survey`).
- **An outline along a retaining wall takes the wall's top and foot by turns** (#147): the area's
  vertices coincide with the wall's 3D lines (`Hranice stavby`, ground level), whose heights alternate.
  Beside the tram embankment at Belárie (line 17) the tram area's edge read 195.8 / 199.7 / 196.8 /
  200.3 m with the terrain at ~198.5, and two points took a footbridge's 202.7 m, listed on level 0 and 1.
  `dtm.py` `despike`: on surfaces driven or walked on, a point more than 1 m off its neighbours' median
  (and steeper than 1:5) takes the height along the outline, but only where the terrain agrees with the
  median better than with the point: an outline that really runs on two levels (a riverside walk under
  the street wall) keeps the points the terrain confirms. Without the terrain check the rule lifted
  Novoměstská náplavka's walk 6 m to the street. Line 17: 1,595 points, line 22: 693
  (`provenance … vertexHeights.spikes`).
- **The survey's ground level against the lidar** (#446, `tools/bench/survey_ground.py` on main's data of
  2026-11-08r): at the 2 m stations of DI's and DTMP's tracks under open sky in paved level-0 areas, IPR lies within
  0.3 m of the top of rail at 96.8-99.3 % per line, the survey at 81.9-91.8 %. Whole areas steadily off IPR are few but
  can be large: Kabešova's street block on line 37, 14,600 m², 1.75 m under IPR, DMR 5G and DI's rails, from its own
  ZPS lines (#446). `dtm.py` checks level 0 against IPR 1 m inside the outline: the line's coarse 10 m grid read
  Divadelní's deck (192.99 m) over the road 5 m below it and threw that road out. What tells survey from lidar
  (`tools/zps_ground.py`):
  - **Bare earth leaves out small things.** Planters, raised beds, light wells and short flights of steps sit off
    the lidar but are surveyed right: on line 37, 94 of the 158 areas DMR 5G would have moved were under 10 m². Only
    areas of 100 m² or more, with a point 1 m inside at two thirds of their corners, are judged.
  - **The survey's dates say nothing about change**: line 37's areas that fit IPR mostly carry `DatumZmeny` of
    2025 (3,777 of 4,522), from bulk edits. OSM's construction sites (`landuse` / `building` / `highway` =
    `construction`) mark ground that changed since the lidar: three lawns at 50.0906 N 14.4666 E sit 1.5-1.75 m over
    both lidars.
  - **A ground-level outline that shares its lines with a deck carries the deck's heights**: under Divadelní's
    deck the road's corners read 193.2-193.3 m at 11 of 16, the floor's 187.6-187.8 at the rest, both levels on the
    same line; a height an upper level's line has at the same place, over 2 m above the area's ground, is the deck's.
  - **What neither the rails nor DMR 5G decide** (19 areas on the five lines, the user's answers of 2026-11-10 in
    `data/truth.json` `surveyGround`): mostly courtyards, where the orthophoto shows little and there is no street
    view, given to the lidar (13), and greenery outside, raised beds and shrubs, given to the survey (6). Their rule
    (`heldRule`): a courtyard (OSM buildings within 60 m in 12 of 16 directions) to the lidar, greenery outside to the
    survey, paved outside to the lidar; it matches 14 of the 19 answers.
- **The survey's decks take the heights of the lines they share with the ground** (#445, `tools/zps_decks.py`,
  `tools/bench/decks.py`). A level-1 outline that runs along a wall or a portal takes the wall's foot or the
  underpass's floor from the same 3D line: on the Krejcárek viaduct (line 37) 53 % of the level-1 vertices within
  12 m of the route lay over 2 m under the rails, a tram area ran from 208.19 to 228.41 m; at Divadelní five of the nine
  pieces over the underpass sagged to its floor at the portals. Where the rails, Mosty 3D and the survey all exist,
  2 m under the structure parts them: of the vertices within 1.5 m of DI's and DTMP's raised rails (1,033) three lie
  over 2 m under the model's top, of those over 2 m under the rails (612) one lies within 2 m of it. Under the rails
  the deck's own vertices sit -1.0 to +0.5 m (the surveyed bed under the ballast on Krejcárek, 0.73 m), the model's
  top up to 1.7 m over the deck (parapets). A deck's vertex more than 2 m under its structure takes the structure's
  height and the offset the deck's own vertices keep from it. Where no vertex of a deck is on its structure, the area
  lies inside the model with the ground's heights (Výtoň: the railway and its walkway on Železniční most's land span
  carry the street's 192 m under the model's 197.5 m; the user: three levels, the railway and its walkway on top) and
  takes the model's top. Mosty 3D's edges and the survey's outlines part by up to a metre: of the vertices left on the
  ground beside a model's edge on line 37, 223 of 246 lie within 1 m of a face. Under a deck the floor is the lidar's
  (the user, 2026-11-10: smoother and believable; the survey's level 0 runs 1-2 m under it in a 64 m covered passage on
  line 9, too few cases for a rule). Walkways keep 2.2-2.3 m clear (the user, from street view of the passages).
  One survey area can span several structures: Libeň's railway areas (line 37) lie over separate viaducts side by
  side at about 205.7 and 212 m and sloped 7 m across the gap. Between the nearest vertices of two levels Libeň's
  rise 62-1404 %, a deck sloping along one structure 2-7 % (Most Legií's road: 2.9 m over 139 m, vertices only at
  its ends); over 25 % the area is cut along the model, one piece per deck. Mosty 3D models a slab's top and its
  underside 1.2 m apart, and Libeň's railway areas lie about 1 m under the top: a piece keeps its offset from the top,
  the nearest face flipped between the two.
  The rails, not our track profile, check the decks: `line_heights.py` runs after `dtm.py` and reads its sidecar.
- **Along a kerb the survey and IPR's lidar are equally noisy** (#470, `tools/bench/street_scatter.py` on the five lines'
  data of 2026-11-12). Straight street outline over 8 cm off its 21 m mean, survey / IPR read 1 m inside the area:
  road 1.8-2.7 / 1.6-2.3 %, tram 1.7-3.3 / 0.4-2.1 %, sidewalk 4.0-5.1 / 3.6-5.9 %, parking 1.5-4.3 / 4.5-9.6 %, paved
  6-11 / 22-33 % (IPR read on the outline itself, or 0.5 m in, rounds the kerb and is worse). Against DI's rails the
  noise left in each is alike: median 1.5 cm, 90th percentile 5-10 cm. Of the road samples over 15 cm off, 0.4-0.7 %
  are the survey's alone, as many IPR's alone, 0.1 % both. So IPR does not replace the survey's heights; the survey's
  own large errors are runs of vertices on another line's height (a road edge on a wall's top line, a sawtooth of
  1.2 m by Jižní spojka on line 22; Náhorní's sidewalk 1.40 m low on line 17, #315) and lone vertices off their kerb.
  `tools/zps_outline.py` moves those where IPR runs calm, on road, tram and sidewalk, a run of them whole or not at all
  (moved in part, a stretch 1-3 m off became a sawtooth): over 0.3 m off, 1,135-3,540 vertices per line → 90-260; over
  8 cm off the mean, roads 1.8-2.7 → 1.3-1.6 %, sidewalks 4.0-5.1 → 3.1-4.0 %. A vertex one outline agrees with IPR
  at and another not is a step (a track bed under its kerb on line 9), not an error. 79 % of straight street outline lies in
  gaps over 5 m between vertices (line 22). A platform's edge shared with the tram area is its top (#21), not the
  tram's foot: its vertices stay out of the rule.
- **Railway yards, lawns and paved yards have heights only on their outline** (#444, `tools/zps_inside.py`,
  `tools/bench/ground_inside.py`). A street is dense with surveyed lines; these are not, and the linear sheet between
  their outline vertices left 5-53 % of `rail`'s inside, 7-19 % of `paved`'s and 22-29 % of `green`'s more than 1 m off
  IPR (the street classes 0-4 %). Those lying open on IPR's ground (#446's verdict within 0.5 m, moved there, or off
  it unevenly along walls and slopes) take the lidar inside: the page drapes them on its terrain, 5 m triangles (10 m
  left `green`'s p95 at 0.38-0.44 m, 5 m at 0.13-0.18 m). For the uneven ones a sheet left 30-54 % of the inside
  beyond 1 m, draped 2-17 %; the small ones (planters, raised beds), the covered ones and those held off IPR keep
  their sheet. Cut from the city
  mesh and written as triangles, line 37's were 750,000 triangles, 24 MB more JSON: prebuilt, they wait for #276's
  ground format. Under the decks IPR is not the floor everywhere: of 14,235 ground-level outline vertices under level-1
  areas the middle half lie within -0.25 / +0.12 m of it. Hlavní nádraží has three levels:
  - the tram in its tunnel (s 11801-11867 on line 9) at 197.4-199 m, which is where IPR lies;
  - the forecourt's paving at 205 m, at level 0, over the tunnel;
  - the deck at 208.7 m.

  The survey's tram area there shares the forecourt's line along the tunnel's side, so its sheet stands 1.5-3 m over
  the track. On line 17, IPR reads a deck's cover over stairs going down. In an opening whose floor IPR shows, only the
  vertices of the passage's own street that stand at the deck move: those within 0.5 m under its underside (top less
  slab) or higher. Divadelní's west kerb at 193.3 m goes to the floor at 187.7 m. At Modřany the pair 0.1 m apart, 0.98
  and 1.03 m under the deck's top, moves together, where a fixed 1 m under the top had split it. A level between the
  floor and the deck stays (the forecourt over the tram's tunnel, #449), and so does an area across the way: the tram
  over a footway's underpass at line 37's east end lies at its rails' top, IPR 2.3-4.2 m under them.
- **A kerb is one 3D line in the ZPS survey**, with one height, shared by the road's and the sidewalk's
  outlines (`Hranice dopravní stavby nebo plochy`; a second line one kerb higher lies within 0.6 m at 4 %
  of them). Measured with IPR 1.5 m to either side (#21): along sidewalks it is the kerb's **foot**
  (road −0.005 / +0.006 m, sidewalk +0.095 / +0.109 m on lines 17 / 22); along line 17's platforms the
  **top** (+0.17 m over the road). The sidewalks' far edges lie +0.100 m over the foot: sidewalks are
  nearly flat across (a 2 % crossfall would leave 2–3 cm kerbs).
- **OSM's lowered kerbs show in the terrain at about half a kerb** (IPR 1 m into the raised area minus 1 m into the
  road, medians on lines 17 / 22): `kerb=lowered` +5.9 / +6.3 cm, `flush` +6.1 / +5.8 cm, `raised` +11.1 / +11.8 cm,
  no lowered or flush node within 10 m +11.4 / +11.0 cm. A `kerb=*` node lies within 1.5 m of only 33 % / 48 % of the
  crossing ends on a survey kerb, so a rule that lowers only tagged kerbs leaves most raised (#303). The kerb review
  list is not enriched in them (16 % / 33 % of listed areas, 18 % / 36 % of all kerbed areas), so its cards name them
  and they change no list (#142).
- **The survey does not show a lowered kerb; untagged crossing ends read lowered** (#303, lines 17 / 22, the survey's
  traffic-area edges against OSM's nodes on a kerbed edge): the kerb line at `kerb=lowered` nodes carries the same code
  (`TypDopravniStavbyNeboPlochy` 1, as 88-91 % of them) and sits level with its neighbours (its height against a line
  fitted 2-10 m either way: median 0.000 / -0.004 m, plain kerb 0.000 / +0.001 m); no inner-division line or second edge
  marks the crossing. IPR's step at crossing ends with no `kerb=*` tag, +5.7 / +6.3 cm, is the lowered kerbs' (+5.8 /
  +6.2 cm), not plain kerb's (+12.0 / +11.0 cm). So `tools/kerbs.py` lowers every crossing end to ČSN 73 6110's 2 cm
  unless OSM tags it otherwise (`data/truth.json` kerbFacts.crossing).
- **Street surfaces from the survey**: smoothing fits through the outline vertices (on straight kerbs only
  the corners, tens of metres apart) wave by ±0.5–1 m over 15–30 m; linear between the surveyed vertices
  is the smoothest surface (line 17: 3.6 % of samples over 8 cm against 7.3 % for the old street
  model, #21).
- **Regional DTM ZPS packages: what our tools rely on** (`tools/dtm.py`, `tools/gpkg.py`,
  `tools/registration.py`; audit of the 16 pinned packages of 2026-09-30, #63). What to compare after a
  format change (JVF 1.5.0.2 from 18 Nov 2026; refresh steps in DATA.md):
  - Files: each ZIP holds exactly `ZPS_OPL.gpkg` or `ZPS_KR.gpkg`; `fetch` unzips into the archive's
    name without `.zip`. `tools/dtm_packages.py` selects one OPL/KR month per district for the import,
    registration and rebuild: CURRENT's `dtm` group wins; unpinned districts use the newest local date
    with a warning when several are present. If the pinned pair is unavailable, a newer local month
    may be used with a snapshot/month warning for rebuild-before-publish refreshes; incomplete pairs fail.
  - Layers: classified by the type code, `table.split('#')[-1].split('_')[0]` (the codes in `dtm.py`'s
    table; registration matches a table ending in the code or containing `#<code>_`). Full names matter
    too: height lines need `Hranice` in the name. (The ground-height cloud built from the
    `Hranice_dopravní_stavby_nebo_plochy` … `Terénní_hrana` lines was retired in #21: surfaces are
    linear between their surveyed vertices.)
  - Attributes: only `UrovenUmisteniObjektuZPS` (nullable INTEGER on 981 of the 1,062 layers, absent on
    81; absent or null = level 0). The geometry column is found from `gpkg_geometry_columns` (now
    `shape`).
  - Geometry: OPL polygons / multipolygons (XY); KR line strings with Z (boundary heights) and points
    (registration). `gpkg.py`'s WKB reader takes base types 1–7 with ISO / EWKB Z and M (M dropped) and
    envelope codes 0–4: curved types would need work. The blobs carry no envelope (flags 0) and the packages
    no R-tree index, so a reader that wants only the features near the line reads every box through GEOS
    (`gpkg.features(keep=)`, #517): of line 17's districts' 1 891 580 line and 199 246 area features, 8.7 % and
    9.4 % have a box that reaches its corridor's 40 m cells.
  - CRS: everything is EPSG:5514 metres, M = 0, and no tool reprojects or rejects another CRS.
  - Per district (OPL polygon / KR line / KR point layers): Praha 1 50/28/61, 2 43/26/52, 4 49/28/60,
    7 45/28/56, 8 53/29/63, 10 49/27/62, 12 50/29/58, 17 43/26/47.
  - Versions: the GPKG `user_version` 10301 is GeoPackage 1.3.1, not the JVF version. The GPKG ZIPs
    carry no JVF header; the matching Praha 2 JVF packages say `VerzeJVFDTM=1.4.3`,
    `DatumZapisu=2026-10-01` (OPL SHA-256 `ba86e8f6…`, KR `3384bf02…`; not in the snapshot).
- **The survey under the track beds** (#547, #548, 2026-11-13):
  - Beds are as wide as the survey's area of their style (tram, green, rail), else the style's median width
    measured there: embedded 1.7, panels 1.9, grass 2.0, ballast 2.5 m (`tools/track_beds.py --calibrate`).
  - The survey's raised areas (platforms, sidewalks, islands) lie inside the bed outlines over 1 800-4 200 m² per
    line. Laid under the beds with the street, they flattened 4-5 times the kerbs (line 9 345 → 1 571 flat kerbs).
    They keep their height: a sidewalk inside a bed's outline means the bed is too wide there, and the raised area
    is drawn over it anyway.
  - The survey's street triangles, split to 5 m, rose over a bed between their corners even with every corner
    laid under it (Spojovací's loop, line 17 s 2350). Near every drawn track they are meshed to 2 m
    (`terrain.js` `nearTracks`); each 4 m outline piece is split by its own midpoint, the same for both
    neighbours, so no shared edge gains a point on one side only.
  - Where the band past a bed's edge caps one area's vertices and its neighbour meets it along a longer edge with
    no vertex there, a 3.3 cm seam opens (line 23 s 2332-2460, a track 2.4 m away): +18 and +20 `seams3` on lines
    22 and 23.
- **The survey on our bridges** (#549, the user's photos and Street View, 2026-11-14):
  - Level-1 walkway areas sometimes carry the parapet's top as their surface: Krejcárek's tram areas 0.9-1.3 m over
    the rails, the strip at Modřanská škola (line 17) 0.61 m, Čechův most's sidewalks 0.66-0.73 m (really a kerb
    over the road). `flushDtm` lays them; a flat deck takes its parapets from them.
  - A span from OSM's bridge or the survey's level-1 bed includes the walled ramps up to the bridge: IPR's bare
    earth lies 0.0-0.4 m under the rails there and 2.3-14 m under the spans' bridges (`line_structures.py`
    `ramps`). The ramps stay spans: off a span, the street flush pulls the street beside a walled ramp up to the
    track (Modřanská, 40 kerbs).
  - The bed on the ground ends at the deck's end (`ground_partition.py` `bed_pieces`, #594): near a span the route's
    decks (spans less ramps) decide, not the lidar's 2.5 m test; the two parted by one 2 m bed sample at every deck end,
    and the bed stopped up to 2 m short, a terrain or survey triangle falling under the rails (line 17 s 4062, 5076:
    1.07 and 1.67 m under the bed top). A deck's walkways where the survey has no deck under our track (Krejcárek's
    north end) are laid all the same (`flushDtm`).
- **Open track from the lidar** (#591): the rail top stands 0.14-0.18 m over IPR's bare earth on open track
  (ballast or grass) and -0.02 to +0.02 m on paved track (DI heights only; where our heights come from the lidar the
  measure is circular). It does not tell ballast from grass.
- **The ground partition on the five lines** (`tools/ground_partition.py`, #507, 2026-11-16): the survey covers 6-14 %
  of a line's box and holds almost every bed: the bed class (outside the survey) is 0.013-0.023 km² a line, 20-46
  pieces. A bed sample is on a structure where its ground lies over 2.5 m from IPR's: of the samples along the route,
  the test agrees with the route's spans and tunnels on 1,255 of 1,582 there and calls 22 elsewhere structures; the
  ones it keeps on spans are span ends and low decks. OSM's footprints lie up to a metre off the survey's outlines of
  the same walls: 3,400-11,400 strips under 1 m wide a line (6,300-16,100 m²) lay between them, joined to the plots.
  The city mesh's triangles in a box dropped under the classes above: 11-29 % (line 22 11 %, 17 13 %, 23 18 %, 9 24 %,
  37 29 %); the cut ones' remains roughly double their count.
- **Raised survey areas over the rails** (#508, 2026-11-16): a raised area (sidewalk, island, median, platform) over a
  rail almost always crosses the track, its axis in it: line 37 11 of 11, line 17 32 of 35 (699 of 712 m of rail under
  them). They are pedestrian crossings over a reservation at its stops, classed sidewalk (line 37 U Elektry – Sídliště
  Hloubětín), and the survey's platforms or sidewalks lying over a track. #512's sidewalk profile raises them 8-32 cm
  over the rails, where the page keeps the survey's own heights under the rail heads; the ground mesh lays one across a
  track flush with the rails within the beds' outline. Bridge tracks (`b`) have no ground bed (the page's `bedsNear`
  skips them): their ends on the ground had made bed pieces without a bed surface, 961 corners on line 17. Where one
  DI track ends and the next begins, their rail points lie 1-3 mm apart and their beds' quads leave a sliver between
  them; a mesh point on the 1 mm grid there took the nearest quad's plane, up to 15 mm off the rail on line 37: the
  ground takes the rail's own height at a point on a rail (`ground_mesh.on_rails`). What reaches a rail without crossing
  the track lies at the bed's height within 5 cm of it (`ground_mesh.rail_band`): line 17 s 17128's stop island, classed
  sidewalk, lies along the outer rail (9.5 cm over it before), line 9's depot hall (a plot) over its tracks' ends.
- **Geoportál's retaining walls and the walls the page drew** (#765, measured 2026-11-19). The page drew two kinds of
  wall on top of the ground until #765. Invented ones (`corridorWalls`): where the 10 m terrain grid rose 1.5 m over
  the track 8-15 m beside it, a face 7 m from the track; 1-4 runs a line, 15-126 m, 21.5 m tall at the Vyšehrad
  tunnel's mouths. And Geoportál's retaining walls (`data/lineN.geo.json`: a line and one height a wall, 5-9 a line,
  593-1,641 m) as slabs. Against the survey: 54-75 % of Geoportál's length lies within 2 m of a survey wall line or
  wall area, and with the paved strips up to 1 m across 85-95 %: the survey has many a wall's face as a paved strip
  (under Letná, line 17 area 4166: 0.44 m across and 290 m long, its foot's line along the road and its top's behind
  it). What is left, 35-318 m a line, are walls of the ground from Geoportál's line and height (`wall_lines.retained`):
  such a line lies a metre or so off the raster's rise, and under a steep bank the raster has no step to fit (a
  side's fit read back to the line gave the top anywhere between 191.3 and 195.3 m within 30 m of wall), so the top
  is the foot plus the height, no higher than the ground 4 m behind. A strip that is a wall's face: its outline has
  the foot one side and the top the other without two neighbouring points climbing (`ground_mesh.two_sided`: 10-87
  such strips a line beside the 52-155 that climb); triangulated on its outline it stood as teeth 10 m wide, hidden
  behind the page's slab. The slab was 3.9 m all along; the survey's top steps between 1 and 4 m.
- **A street in a rock tunnel** (#771, measured 2026-11-20). The mirror of a street under a deck: in the Vyšehrad
  tunnel (line 17 s 11385.8-11424.0, the only tunnel through rock on the five lines; lines 9, 22 and 23 have covered
  stretches the lidar is not 8 m over) the lidar is the hill over the vault, and the survey's level-0 areas inside
  (the road beside the tracks, a wall area at each mouth) took the street surface or their outline, which rise with
  it at the mouths: the road stood 4.3 m over the track 1.9 m beside the axis at s 11388.8, a dark spike in the south
  portal, and two slabs in the north one. The page leaves out the terrain in the corridor and nothing else
  (`src/groundDraw.js` attachGround). OSM's tunnel starts 3 m before the lidar's cliff there (s 11385.8 against
  11388.5). In the corridor (8.5 m either side, the page's vault) a survey corner 0.5 m or more over the rails lies
  at the rails' level, and no wall stretch holds it (`ground_mesh.off_the_hill`). The north gate's own masonry is in the survey as one
  wall-like strip 0.64 m across (area 1237): the arch's line across the road and, as a sliver, the wing wall along the
  sidewalk from the pier (197.22 m at s 11424.8) to a point on the ground 12 m on. Stood up as a wall its top fell
  with that line, a grey cone 4 m tall by the road seen from inside the tunnel. A wall-like area with a corner on the
  hill inside the corridor is the portal's masonry: within 15 m of the corridor all of it lies at the rails' level
  (`ground_mesh.portal_masonry`). Street View of September 2025 (the user's links, 2026-11-20): a flat road, kerbs
  and sidewalks, a stone gate and a wing wall about 6 m tall; nothing draws a portal's masonry yet.
- **A street under a deck** (#761, measured 2026-11-20 on the batch's first build). The street surface follows the
  tracks onto a deck, so under the deck it has the deck's level. A level-0 street area on a span keeps its own
  outline for that reason, but one whose outline lies on two levels (`climbs`) cannot, and since #762 took the street
  surface whole: the road under the Modřany viaduct (line 17 (-2428, -9241), area 7120, 1.4 ha with the ramp's
  roadside in one outline) stood at 205.3 m where the lidar has 197.6 m, a slab in the viaduct 1.04 m over the
  deck's underside. The lines' check `groundUnderDecks` found it (0 → 2 places), not the place's sections, which
  lay beside the ramp. Such an area's corners under a span that the street surface puts 2 m or more over the lidar lie
  on the lidar (`ground_mesh.off_the_deck`); the place's steep faces fell from 75.9 to 4.8 m².
- **Abutments: the wall the survey does not have** (#763, measured 2026-11-19). Where a deck lands, the survey's wing
  walls along the ramp are wall lines; the abutment's face under the deck is not. At the Modřany viaduct (line 17
  (-2393, -9247)) the two wing walls' lines turn by 0.5 m at the face's corners and run on along the street at its
  level; without a line across, the ramp's side strips fell 4.5 m in their last metre. The bed's end is not the face:
  the bed reaches the deck's end (#594) and overhangs the abutment, by 1.3 m there. Nor is a span's end: the route's
  span runs s 3971-4152, the ramp included. `ground_mesh.abutments` finds the face behind the bed's end where IPR's
  raster crosses the middle between the ground the deck leaves and the ramp's top; its ends are the wing walls' points
  there that stand over that ground, else the first wall line across, else the bed's edges. Walls that meet: a corner
  past a stretch's free end is left (the ground has no step there), but where two stretches meet (a wing wall and the
  face, a wall's turn) the wedge outside the corner is past both and stood as leaning faces; an end within `WALL_JOIN`
  of another stretch is not free, and a corner at or past such an end reads the wall its triangle's centre lies by.
  No step in the raster, no wall: at Krejcárek (line 37 (3954, 380)) the embankment and a stone cone run under the
  deck's end and the line makes no stretch; that abutment is the structure's (the bridge model, #742).
- **Terraces: where the lidar's ground is not the ground** (#663, measured 2026-11-19). A lawn or a yard on the lidar
  (`g`) lies on the city mesh inside (#444). 38-108 of them a line (of 1,375-3,663) have an outline over 1 m above
  IPR's raster (its points' median); 4-70 lie over 1 m under it. Those over it are of three kinds: terraces inside
  walls as high (a raised courtyard, line 37 (7590, 743): six beds 2.1-3.7 m over the raster, their walls 2.2-4.2 m),
  areas on a deck or a roof, where the raster is the ground under the structure, and outlines that are off. A
  terrace keeps its own outline's surface (`ground_mesh.terraces`: over 1 m, and touching a wall whose outline stands
  as far over the raster): 2-10 areas a line, 18-3,628 m²; the others, 28-105 a line and 0.7-4.0 ha, stay on the
  lidar. The median keeps the raster's smear out: a lawn along a retaining wall's top has only that edge over it. A
  footpath that touches a terrace and has a quarter of its outline's points over 1 m above the raster runs onto it
  and keeps its own outline too (`beside`: 0-5 a line); a street's sidewalk along a terrace's foot touches it with
  none of its points over (2-3 a line, up to 2.3 ha) and stays on the street surface. Not solved: one area on both
  levels (line 37 green 4451, 8,164 m², 37 % of its points over): its strip between a wall and the footpath is a
  pit.
- **Fine cells only by a wall** (#770, measured 2026-11-20). #762 cut every street and lidar-ground cell that bends
  by 0.5 m to 1 m cells, so that the ground beside a wall could carry its two levels. On the lidar's ground away from
  any wall the fine cells draw the raster's bumps: the sides of line 37's cutting at s 2340 as lumps with a spike
  (walls the build had no line of: the next entry). The batch's seams of 10 cm (441 -> 536 on line 37, mostly
  paved / paved and not at a wall) come from there. A lidar-ground cell is cut finer only within 5 m of a wall
  stretch: every place's section holds as before (Chotkova's terraces need the fine cells: without any, 2.25 m of its
  section slope against 1.75), and the steep faces that are no wall fall at four places (Žižkov's depot 41.6 -> 21.9
  m², Krejcárek's abutment 88.5 -> 70.3, Letná 149.0 -> 125.0, Chotkova 498.2 -> 482.2). The price: the ground lies
  farther from the raster where the raster bumps (4.5 m of a 24 m section along that bank more than 0.5 m off, none
  before). Streets keep their fine cells.
- **A paved yard whose sheet misses the ground** (#638, measured 2026-11-20). A paved yard has surveyed heights on
  its outline only, and inside it is a sheet between them unless that sheet misses IPR's raster by more than 0.5 m
  at the 95th percentile (`zps_inside.MISS`), when it lies on the lidar. Under that limit a yard can still be far
  off at one side: line 23 s 557 (-2564, 434), area 3398 (2,031 m², 0.43 m at p95), lay 0.5-0.9 m under the raster
  beside the sidewalk that cuts through it and 0.29-0.37 m under that sidewalk: a step with its wall, over the
  0.3 m `ground_mesh.meet_raised` closes. Of line 23's 707 paved areas kept as sheets, 215 (2.4 ha) are within
  0.2 m of the raster, 308 (6.5 ha) 0.2-0.5 m off and 184 (1.2 ha) farther (held off the lidar: covered, small,
  the user's or the rails' verdict). A paved yard's limit is 0.3 m (`MISS_PAVED`, the step that can be closed): 107-286
  more paved areas a line lie on the lidar (line 9: 706 -> 958, 44.6 -> 50.6 ha; 17: 409 -> 673; 22: 595 -> 881;
  23: 286 -> 464; 37: 221 -> 328), and nothing else in the survey file changes. At the place the step is 0.06 m
  (0.29) and the walls over 0.3 m in its 80 m square fall from 99.2 to 40.3 m. The old limit's reason was the
  page's drape (a yard on its 2 m terrain in 5 m triangles: 8 cm waves the street check read); the ground file lays
  lidar ground in 5 m cells of the city mesh, and the lines' `streetWaviness` comes with the batch.
- **A parking area is such a yard** (#800, measured 2026-11-21 on ground batch C). It has heights on its outline only,
  from the survey's lines in height class 5 (a mean error of 0.35 m). The bay along Vinohradská's north carriageway
  (line 9 s 15360-15420, area 3091, 822 m², 0.42 m at p95) shares one such line with the sidewalk behind it; one
  point of it, (3214.13, -1444.59), stands 0.38 m over IPR between points 31 and 35 m away, and the bay, a sheet
  up to it, stood 0.18 m over the sidewalk where IPR has it 0.2 m under: 15 sunk kerb samples. Held to `MISS_PAVED`
  as paved yards are, 41 / 44 / 29 / 9 / 37 parking areas lie on the lidar (lines 9 / 17 / 22 / 23 / 37; 18.1 ha of
  the 41 ha of parking), the large lots most of all. One with over a third of its inside under a cover keeps its
  sheet (`zps_inside.UNDER_COVER`): `zps_ground.judge` calls an area covered only when it is off IPR at its outline,
  and the two car parks under the Magistrála's bridges at Hlavní nádraží (areas 232 and 233, 50 % and 93 % under
  level-1 areas) fit there while IPR inside them is the bridges: on the lidar they raised the place's steep faces
  from 379 to 640 m². Paved yards under a cover are judged as before (34 on the five lines lie on the lidar with
  over a third under a level-1 area, 0.8 ha).
- **A wall the survey has only as a strip** (#770, measured 2026-11-20). The tram's cutting north of Ohrada (line 37
  (3400, 1)) runs between two upright concrete walls of 4.7 and 5.8 m with a ledge at each foot (the user's photos
  from the footbridge, 2026-11-20). The survey has no `Zeď` line, no wall area and Geoportál no wall there: only a
  paved strip in plan for each, inside paved ground on the lidar. The west wall's top is area 1847 (0.32 m across,
  with heights); the east wall area 1818 (0.53 m across, on the lidar's ground: its outline's heights are neither the
  foot's nor the top's). The raster spreads each wall over 2.5 m, and the ground was a bank. A paved strip up to 1 m
  across is a wall line (`wall_lines.strip_lines`) where the survey has no wall line within 2 m: one with heights by
  its outline (the strip keeps its own level, the ground outside it is held at the raster's level 2.5-4 m off), one
  on the lidar by its low side's edge alone. Such stretches hold the lidar's ground and the terrain, not a street,
  which has its own surface up to the strip. The five lines have 503-1,505 strips with heights and 3-18 on the lidar;
  they make 280-1,014 stretches a line (2.2-7.4 km, the step 1.1-1.4 m at the median, most under 5 m long: parapets,
  edgings, low walls) and the lines' stretches go from 326-610 to 628-1,622. Three things came with it:
  - the weld let a lidar corner on the wall's line, held at the foot, take the strip's top wherever the area's own
    outline there was near the top (one area runs behind the wall's top and along its foot): a spike on the ledge
    every 2 m. A lidar corner a wall holds keeps the wall's level where that is over 0.5 m off the edge it yielded
    to, whatever that edge's rank (`ground_mesh.weld`);
  - past a strip's corner the wedge outside it is outside the strip, whichever side of the last segment's line the
    triangle's centre lies on (`out` of a strip's stretches, `ground_mesh.hold_at_walls`);
  - tried and not taken: wall lines traced along the raster's own faces inside paved lidar ground (a rise of 1.5 m in
    a metre, marching squares): 2.6 km on line 9 in 679 stretches, 532 of them under 5 m, and no place needs them.
  On the place the steep faces that are no wall fall from 220.7 to 41.4 m² and its three sections, which the written
  file fails (3.25, 1.82 and 8.84 m sloping), hold (0.5, 0.78, 0.0).
- **A slot between two wall lines ends with them** (#770, measured 2026-11-20). The survey has many a wall as two
  `Zeď` lines half a metre apart, and `wall_lines._side` gives the strip between them the lower line's surveyed
  height. Between a terrace's foot line and top line that is the lower ground's level. Between a stairwell's two
  walls it lies under the ground on both sides: by the house at line 23 (-2329.4, 571.3) one line is surveyed at
  271.18 m and the other at 272.93 m, the ground at 272.6 m on IPR either side. `ground_mesh.hold_at_walls` held
  every corner within 1.5 m on the strip's side at its level, also past the lines' end: the footpath and the lawn
  passing the end lay in a trench 1.3 m deep, a step of 0.96 m inside one sidewalk in the `surfaces` check. A
  stretch's side that is such a slot (the strip's level 0.7 m or more under the stretch's other side and under IPR
  past the next line) is marked (`sl`, `sr`; 100 of line 23's 618 stretches) and holds nothing past the stretch's
  end, unless another stretch runs on from that end (a wall cut at a turn). Whether a corner is past the end is asked
  of its nearest segment of that stretch: 1 m beyond the end it is still within 1.5 m of the stretch's second
  segment, which has no end to be past. Tried first for every strip between two lines (479 of the 618): it moved
  corners by up to 4 m at the ends of Chotkova's terrace walls and Ohrada's, the places' steep faces up, and put
  teeth of 0.7-0.9 m into the low wall under the park by Krejcárek at a joint of two stretches. (A free end has the
  same gap: a corner up to about 1 m past it is held by the second segment. Left as it is: no place shows it.)
- **A road sunk between walls** (#779, measured 2026-11-20). A garage ramp is a road area in the survey, its outline
  surveyed at the top of its walls, and a wall area stands on some of its sides only: on Na Vápence by the Žižkov
  depot (line 37 (3871, -24), road 22: 259.7 m at the street, 257.8 m at the door) the walls over the door and on
  the east side are area 1419 (0.26 m across, its top alone), the side along the sidewalk has none. Two rules read
  such a road as any other:
  - the sidewalks' surface is tied at a kerb edge to the road 0.5 m beyond plus a kerb (`street_profile.sidewalks`):
    here the ramp, and the walkway's last 1.25 m fell 2.2 m. A kerb edge whose own surveyed height stands 0.3 m or
    more over a kerb on that road, along an edge that stands 0.7 m over it somewhere, is a wall's top and is held at
    its own height as a survey wall's edge is (`wall_tops`), where that height is the walkway's: within 0.5 m of IPR
    1.5 m in. A sidewalk's outline along a parapet on its kerb carries the parapet's top (by the Modřany viaduct,
    line 17 (-2396, -9241): 199.24 m over a walkway at 198.1 m), and without that check 242-1,343 m of kerb a line
    counted; with it 25-256 m (4-35 edges a line, of 47-145 km of kerb). The mirror case (#770): a sidewalk at the
    foot of a road's wall has its kerb edge surveyed at the wall's top (line 22 (1897.5, -2212): the walkway at
    221.2 m, the road at 223.8 m), so the edge is a wall's either way, held at IPR's level 1.5 m in where the
    sidewalk reaches that far. A walkway on a quay wall's top has the drop within those 1.5 m (Rašínovo nábřeží,
    line 17 (-761.2, -1704.8): edge 191.90 m, road 191.87 m, IPR 191.99 m 1 m in and 190.17 m 1.5 m in): read at
    1.5 m alone, its edge was held 1.6 m under the road, 57 such kerb sites in the surfaces check of ground batch B
    against 18 at a wall's foot. The edge's own height is the walkway's also where it is a plain kerb's (within 0.3 m of the
    road plus a kerb) and IPR 0.5, 0.75 or 1 m in comes within 0.3 m of it (`KERB_NEAR`): wall edges 1,215 to 875 m (line 9), 1,519 to 1,040 (17), 624 to 515 (22), 352
    to 280 (23), 386 to 309 (37), the ones lost with their own height -0.16 to +0.23 m off the road (10th-90th
    percentile), plain kerbs;
  - the road's surface follows IPR, whose raster spreads a wall's face over 1-1.5 m: the ramp rose 0.76 m in its last
    metre before the door's wall and the road behind the wall fell 1.6 m towards it. A road's corner within 1.5 m of
    a survey wall area up to 1 m across (101-231 a line, 7.5-22 km of outline), or of a kerb edge that is a wall's
    top, takes the road's own surface 1.5 m out, carried on at its grade there (`ground_mesh.off_the_smear`), unless
    that surface lies 1 m or more off IPR there (under a deck the street surface has the deck's level). The
    raster is not asked whether it steps across the wall: read 2.5 m past a wall's end beside another wall it showed
    no step. In a corner of two walls the point out from one lies in the other's smear and is moved clear of both; at
    a wall's end the short edge across it points through the wall, and the edge taken is the nearest whose point out
    the corner's triangle sees.
  The place's three sections fail on the written file (1.57 m sloping at the sidewalk's edge, the ramp 0.67 m off
  its line, 2.75 m sloping at the door's wall) and hold on the build (0.0, 0.14, 0.0). Seen there and not fixed: the
  generated road east of the ramp lies up to 0.56 m over IPR (#780).
- **A street over a pedestrian underpass** (#783, measured 2026-11-20). IPR's raster is bare earth with the bridges
  taken out, and it takes out the cover of an underpass too: where a street crosses one at grade it shows the
  passage's floor in a slot as long as the passage and 1-2.5 m wider. The survey has the street's areas at level 0
  right across, their outlines at the street's level, and (not always) the passage as areas at level -1. South of
  Čechova čtvrť (line 17 s 3084, (-1453, -9105)) the outlines stand at 214.7-215.4 m and the raster has 211.2 m:
  the verges on the lidar fell 3.6 m, the generated roads up to 1.8 m, a trench across the street that the layered
  ground of `alpha-4` did not have. `tools/covers.py` finds such slots and gives the level-0 areas' own outline
  surface there; the ground build and the street surface read IPR through it (`Covers.over`, `CoveredIpr`). What
  makes a slot a cover:
  - it lies over a passage (half of it or more): a survey area at level -1, or an OSM way in a tunnel of layer -1
    or above from the local extract (not a building's passage, not the metro). The survey's areas alone find 12
    of the five lines' 30 covers (line 17: 7 of 12, 720 of 1,039 m2). A slot that only touches the passage's end
    is the open ramp or the stairs down to it, which the survey outlines at their rim (Nádraží Braník, line 17
    (-2034, -6277)); where such a ramp joins a slot, the cover ends 2.5 m from the passage.
    Without that key 55 more spots on line 17 qualify, mostly sidewalks whose outline carries a wall's top, and the
    garage ramp of #779;
  - a level-0 area's outline triangle stands 2 m or more over the raster there (a walkway's clearance and slab). A
    triangle steeper than 15 % that rises over 1 m joins the cover with the floor (a stair well drawn as one area
    with the sidewalk above) and is no surface; stairs and walls are not covers;
  - it closes within 15 m of the passage. Nádraží Holešovice (line 17 (1512, 1330)) stands on a structure 55 m
    across that the raster leaves out whole: its two underpasses' covers alone stood as blocks 7 m high in it.
  Covers per line (the raster cut out under them): 9: 6 (123 m2), 17: 12 (1,039 m2), 22: 6 (494 m2), 23: 2
  (278 m2), 37: 4 (97 m2); `python -P -E tools/covers.py LINE` lists them. Looked at on plans, all 30 (24 places,
  six of them on two lines): 10 are slots across a street (line 17's six hold 970 m2, lines 22 and 37 two each),
  the rest strips of 4-50 m2 where the raster smears a wall's or a well's face into the street above it, and four
  wells of an underground entrance that the survey has no stairs for (the largest by lines 9 and 22, (-309,
  -1236), 43 m2: level with the sidewalk now, a pit 6 m deep before). Not covered: a
  deck the survey has at level 1 (#449), and the ramps and stairs' wells beside a passage (#786, #447).
- **A paved strip is a wall for the sidewalk beside it** (#786, measured 2026-11-21). The survey has many a
  retaining wall and parapet as a paved area 0.2-0.5 m across and nothing else: no wall area, no `Zeď` line. What
  kept a sidewalk off IPR's smear at a wall (#653: the cells along a wall held at its level, a street corner on its
  outline snapped to it) knew the wall and stairs areas alone. Sidewalk edges on walls and stairs / on strips that
  are a wall's face in plan (`ground_mesh.wall_like`) / on strips the ground steps across by 0.7 m or more: line 9:
  6,086 / 1,750 / 720 m; 17: 10,885 / 5,838 / 1,124 m; 22: 6,822 / 1,191 / 543 m; 23: 4,856 / 705 / 294 m; 37:
  3,271 / 650 / 93 m. Platforms with 5 m or more of such an edge on their side: 1 of 97 (line 9), 12 of 88 (17:
  Belárie, Přístaviště, Nádraží Braník, Pobřežní cesta, Sídliště Modřany, Modřanská rokle, Modřanská škola, Černý
  kůň), 1 of 88 (22), 1 of 47 (23), 2 of 42 (37): the Modřany line runs on walls. Five things went wrong at them,
  each with its rule:
  - *The strip is a wall's face* (its foot's line one side, its top's the other: Nádraží Braník, line 17 (-2040,
    -6262), `paved` 2605, 0.18 m across, 197.43 and 194.84 m). The platform on its top lay on the raster's smear,
    196.35 m at its edge. Such a strip is a wall area for the sidewalks' surface and for the snap
    (`ground_mesh.wall_areas`).
  - *The strip's heights are neither side's ground* (Modřanská škola, line 17 (-2479.7, -8440), `paved` 7924:
    198.7 and 198.3 m between a platform at 199.6 m and a road at 196.4 m; the parapet of the ramp from the bus
    stop). `street_profile.strip_edges` takes a strip's side as a wall edge where the ground steps across the strip:
    the walkway's level against IPR 1.5 m past the strip's other side. The walkway's level is IPR 1.5 m in, or
    halfway across a walkway narrower than 3 m: the ramp north of that stop is 2.15 m wide between two strips, and
    the raster has it at its middle alone (197.5 to 199.9 m in 36 m), the track's 200 m and the road's 196.1 m a
    metre either side. Across such a walkway nothing pulls the surface to IPR. A walkway under 1.5 m across has no
    reading at all and stands a kerb over the road past it (the sidewalk 0.6 m wide between the parapet and the
    road). `wall_lines.stretches` is not used for it: it reads a side 2.5-4 m off, past the ramp, or between two
    wall lines takes one line's own height, the wall's top for the ramp. A run of such edges is cut where the
    strip's outline turns a corner, and a side under 2 m is none: a paved block 2.0 x 1.1 m at the foot of Rašínovo
    quay's wall (line 17 (-746.4, -1445.8), `paved` 1231), one run round it, held the lower quay at the mean of both
    its sides' levels, up to 2 m over the raster.
  - *The surface is read between cells* (`ground_mesh.Streets.at`, cells of 0.5 m), and across a strip thinner than
    a cell the sidewalk on the other side is among them: the platform's corners on Braník's wall read 195.8-196.5 m
    for 197.4 m, teeth. A sidewalk's corner within 0.75 m of a wall's outline reads the surface 0.75 m out on its
    triangle's side (`ground_mesh.own_side`).
  - *Samples every 0.25 m step over a strip 0.2 m across.* The kerb's walkway plane ran from the roadside sidewalk
    over the parapet onto the ramp, and the kerb-wall rule (#779) took IPR 1.5 m in from that sidewalk's kerb, the
    platform's 199.7 m, for its walkway and held the kerb 3.2 m over the road. Both now ask whether the sidewalk
    runs unbroken that far (`street_profile.runs_in`), and a plane cut at a break fills only cells before it.
  - *A strip's own surface, triangulated* (0.2 m across, 194 m long, 15 points a side), gave corners on one side the
    other side's height by turns: a paved area up to 1 m across takes its heights between its two sides
    (`across_outline`). Where its sides' outlines have few points it stands tilted across instead: the coping of
    Ohrada's cutting wall (line 37, `paved` 1847: 0.32 m across, 92 m long, 8 points) by up to 0.3 m for 25 m.
  Three places (`branik-platform-ramps`, `modranska-skola-ramp`, `cerny-kun-platform-wall`): 9 sections fail on the
  written file of 2026-11-20 and hold on the build; steep faces 105.7 to 50.5 m2, 137.1 to 62.1 m2, 153.8 to
  109.4 m2. Not done: Černý kůň's ramps are level-1 areas (the footbridge's), not the ground (#449); a ramp of two
  flights side by side in one area (Braník's lower flights) is one surface between its walls; the platforms stand
  where the kerb rule puts them (#776).
- **A stop's platform is a plane at the top of its corners** (#776, measured 2026-11-20). The survey has a platform
  as a sidewalk, and its street surface runs from one kerb's top to the other's and follows the raster between: at
  Krejcárek (line 37 s 2904-2974) +0.01 to +0.41 m over the rail top 0.6 m behind the edge. `platform_planes` lays
  the corners in a platform's band on one plane over the rail top (one height, one crossfall up to 2 %). Fitted to
  the corners' middle, the plane lay under the kerb tops wherever the road climbs against the rails along the stop
  or the platform tilts more than 2 %: Motol's platform B (line 9 s 25524-25592, an island 2.9 m across between the track and Plzeňská)
  came down 0.08 m at the road, flush with it, and ground batch B's surfaces check counted new flat kerbs at 23 /
  21 / 13 / 5 / 12 platforms (lines 9, 17, 22, 23, 37; on line 9, 176 of its 180 more flat kerb sites). On the street surface's 0.5 m cells, the kerb cells under
  5 cm in the platforms' bands:

  | line | before any plane | plane at the middle | at the 75th percentile | at the 90th | anchored at the high side |
  |---|---|---|---|---|---|
  | 9 | 287 | 1,151 | 501 | 226 | 589 |
  | 17 | 177 | 1,218 | 432 | 171 | 1,071 |
  | 22 | 201 | 680 | 226 | 31 | 529 |
  | 23 | 64 | 157 | 43 | 14 | 40 |
  | 37 | 73 | 599 | 212 | 63 | 324 |

  The plane lies at the 90th percentile of the corners it fits (`PLATFORM_TOP`); the platforms' edges stand a
  median 0.11 m over the rail top (0.10 m at the middle; Krejcárek's 0.34 for 0.30). A bed laid flush with the
  platform's sidewalk (`pits`) follows the plane: the grassy patch behind Krejcárek's shelter stayed 5 cm under it.
  No fact gives a platform's height over the rail top yet.

  Where the survey has the platform as an area of its own (class `platform`: 14 / 14 / 28 / 12 / 4 of the lines'
  platforms, their back edge a median 4.1-5.1 m from the axis, up to 6.3 m) it is drawn by its outline alone, and
  the band of 4 m left its back edge at the survey's few points. In ground batch B, 0.5 m inside the back edge, 10 /
  3 / 15 / 10 / 2 of them strayed over 5 cm from a straight line along the track and 7 / 1 / 5 / 2 / 2 over 10 cm
  (at their edge 0.7 m behind the rails: 2 / 0 / 3 / 1 / 2 over 5 cm); Hlušičkova's two (line 9, 68 m, 12 and 14
  outline points) by 0.30 and 0.43 m, the kerb to Plzeňská from 0.16 m over the road to 0.05 m under it. In such an area
  the plane holds right across (`PLATFORM_WIDE`), and corners fitted at one distance from the axis tell no
  crossfall (`PLATFORM_SPREAD`): IPR has Hlušičkova's level across, +0.21 and +0.22 m over the rail top 0.7 and 2 m
  behind the edge. The sidewalk islands (43-49 platforms on lines 9, 17, 22 whose sidewalk ends within 6.5 m of
  the axis) stray at the back at 13 / 21 / 12 / 4 / 4 over 5 cm; on line 17 most of those stand on the Modřany
  line's walls (#786). They keep the band.
- **How fine the ground is** (measured on line 23's written file, 2026-11-19). The terrain outside the survey's areas
  is the city mesh: IPR's 1 m raster thinned to triangles that keep it within 10 cm up to 120 m from a track
  (`city_terrain.py`; 80 % of the line's box, a triangle's edge 2.5 m at the median). Inside a survey area nothing of
  that mesh is left: the area's outline (the survey's points, a few metres apart) and lattice lines every 5 m make its
  faces, and each corner reads a surface there: the street surface on roads, tram areas and sidewalks (0.5 m cells,
  `street_profile.py`), the city mesh under green and yards on the lidar, the outline's own heights elsewhere. So
  between a street's kerbs and inside a lawn the ground is a 5 m grid of readings, each right to centimetres, with
  straight triangles between them: a step the survey has no area for crossed a cell as one slope (the quay, Chotkova's
  terraces). Since #697 a cell whose surface leaves its plane by over 0.5 m is cut to 1 m, and a surveyed wall line is
  an edge of the faces with a height on either side. Built whole (2026-11-19, 610c3e7, without writing), that costs
  4.2-7.8 % more triangles a line (18.25 M -> 19.28 M on the five) and the ground lies a little nearer the raster:
  within 10 m of a track its mean distance 3.98-5.66 -> 3.94-5.33 cm, the p99 27.9-54.9 -> 27.0-41.4 cm. At the
  places picked for their walls the cost is 2-28 %.
- **What a tile's ground reads** (#812, measured 2026-11-22). A tile's ground is built from the tile and its ring of
  tiles (`ground_place.py --rings` builds it with one ring and with two and compares the middle tile). On main
  lattice-cell's middle tile had 220 triangles in one build only, modrany-viaduct-ramps' 10. What read past the ring,
  or took what the box held into account:
  - The water levels (`ground_partition.WaterLevels`): the sight raster started at the box's corner, the banks were
    sampled evenly from wherever each ring starts, and banks up to 1,000 m off were read. Now the raster is on the
    S-JTSK grid, the banks are sampled where they cross a 10 m grid, and no bank is read farther than a tile's side.
  - Float noise of the box-wide overlays: the cover's union left needles 9 m long and 1e-13 m wide, and GEOS's buffer
    of the whole box's terrain (the thin strips by a plot) put a vertex 0.2 mm apart, 1 mm on the ground file's grid.
    The pieces go on the 1 mm grid before they are united; the strips are opened per tile with a 4 m margin.
  - Ties broken by an STRtree's order: its hits come in the order of its traversal, which every geometry in the
    tree moves, and `query_nearest(all_matches=False)` takes the first of the equally near. A sidewalk corner on
    the vertex two wall edges share read the surface on one side or the other, 230.21 or 230.37 m; a lidar corner
    0.343 m from two stretches laid over one wall in opposite directions 228.78 or 228.81 m. Ten picks take the
    first by place now (`tools/ties.py`).
  - `meet_raised` weighed the edge per corner: its 8 nearest were copies of one point (12 corners, 1 mm apart),
    which by the KD tree's order. It weighs points now.
  Still box-wide: the covers over passages (`covers.Covers`: a passage merges with those the box holds, its cut
  lattice starts at its bounds; lattice-cell's one ring held one cover of 153 m², its two rings three of 273 m²,
  none in the middle tile). street-over-an-underpass, the cover in its middle tile, is the same in both builds.
- **Where walls stand** (#697, measured 2026-11-19 on the five lines; the user: "can we use the open data sources to
  infer where walls should really stand as opposed to blending between the different height points?"). Four sources,
  best first:
  - *The survey's wall areas* (`lineN.dtm.json` class `wall`): used since #653. They lie under only 2-5 % of the
    survey's wall lines.
    An area's outline has its foot's side at the foot's height and its top's side at the top's. Where they part by
    0.7 m or more and the area is a wall's thickness across (twice its area over its outline's length up to 2.5 m:
    95 % of lines 23's and 37's wall areas are under 2.1 m), it stands upright, its top level at the higher side's
    height and its face on its foot's outline (`ground_mesh.wall_face`): Chotkova's road wall, 3.2 m tall and 1.7 m
    across, leaned as a ramp between its sides. A wider one is a battered face and keeps the ramp: the bastion at
    Strahov (line 23, area 860), 16.5 m up over 5 m.
  - *The survey's wall lines* (`lineN.zps.json` kind `Zeď`: a wall too thin to be an area, with heights at its points;
    at level 0 and on structures, a walled ramp's sides being level 1): 7.3-14.0 km a line, to the survey's
    centimetres. IPR's raster steps by 0.7 m or more across 3.7-7.5 km of them (`tools/wall_lines.py` prints the
    table: 368-579 stretches a line; over 4 m on 0.5-1.9 km). The line's own height is the foot
    on about a third of the stepped length, the top on a third and neither on the rest, so the two sides' levels are
    read from the raster 2.5-4 m off the line (past its smear of the step, 2 m at an 8 m wall) as a level and a slope,
    and the line's height replaces a side's where it is within 0.5 m of it. Rašínovo nábřeží's quay wall is such a
    line, 7 cm from the two sidewalk areas' shared edge; no wall area crosses there.
    A side is read up to the next wall only: 28-38 % of the wall lines' sides have another wall line or a wall area's
    outline within the readings' 4 m, 25-30 % within 1 m (a wall's two faces, at one height; or its face's foot and
    top lines, 0.15 m apart under Chotkova at 208.6 and 211.6 m). There the survey's own heights are the levels: the
    raster 2.5-4 m off lies on another terrace. Under Chotkova (line 23 (-896, 720)) the road at 205.3 m, a wall, a
    footpath at 208.5, a wall to 211.5, a terrace, a wall to 214.0 stand within 9 m; the raster is one slope through
    them, and read past the next wall it gave walls of 1.5-2.5 m with wavy tops. With the lines' own heights the
    section is the survey's staircase to 0.1 m. So read, the line's own height is a side's level on 68-74 % of the
    wall lines' length, and 3.0-6.6 km a line are stretches.
  - *OSM `barrier=retaining_wall`*: 12.7-41.5 km a line inside the 1,200 m corridor, 73-78 % of it across a raster
    step of 0.7 m or more (the same reading as for the survey's lines), so its positions are good enough to find the
    step. Most of that (7-27 km a line) lies outside the survey's areas, on the terrain; inside them, 1.5-3.8 km a
    line has neither a survey wall stretch nor a wall area within 2 m. Not used yet: its position is to a metre or
    two and it has no heights.
  - *Geoportál's retaining walls* (`lineN.geo.json` `walls`, with a height): 0.6-1.6 km a line. Not used by the
    ground.
  - *A survey area's own outline* can hold a wall too: two points next to each other on it within 1 m and 1 m or more
    apart in height (`ground_mesh.climbs`). 27-97 sidewalks and 9-30 roads a line have one, and 91-291 paved and
    104-249 green areas. Such an area lies on two levels and its outline's heights, triangulated, are no surface. On
    a span, where a street keeps its own outline, it now takes the street surface (#761: the Modřany abutment's
    sidewalk, area 7214, rose 3.4 m in 12 m under the bridge, where the raster and the street surface are level to
    0.1 m). The paved areas off the lidar still triangulate their outline: not measured yet.
  - *Paved strips*: parapets, edgings and low walls are often surveyed as paved areas half a metre across. Of the
    58-174 paved areas a line off the lidar whose outline climbs a wall, 46-128 are under 1 m across and 6-35 more up
    to 2.5 m; 7-24 % of their area, triangulated on the outline, is steeper than 1:1 (1-2 % of the other paved
    areas'). They take a wall's heights (`ground_mesh.wall_like`): a terraced garden's edgings, line 23 (-1117, 806),
    stood as fins up to 2 m across its lawns. The wider ones (6-23 a line, 0.25-0.53 ha) keep their outline.
  The survey also has 65 km of `Terénní_hrana` (the tops and feet of slopes) on line 17 and 8.4 km of
  `Hranice_schodiště`; neither is read by the ground yet (#447 for the stairs).

### Street design: ČSN 73 6110 (2006, amendment Z1 2010)

The norm for city streets is public: ÚNMZ publishes it with the ministry's consent (`raw/reference/norms/`, with
its text; the user's link and upload, #512). Its minima are for new design; Prague's streets are older.
Grades and vertical curves of streets with a tram in the carriageway follow ČSN 73 6405 instead (not public).

- **Design speed** (table 2): A (rychlostní) 80 km/h, 60 in difficult conditions; B (sběrné) 50, 40;
  C (obslužné) 30–50, 30; D1 (obytné zóny) 20 (the tables' lowest column).
- **Vertical curves** (tables 13 and 14), the least crest / sag radius by design speed: 80 km/h 4,000 / 2,100 m;
  60 1,800 / 1,000; 50 1,000 / 700; 40 450 / 350; 30 200 / 180; 20 100 / 110. Measured on the clean
  streets (#512 calibration, p5): primary 490, trunk 350, secondary and tertiary 300, residential 150,
  living street 100 m. So Prague's streets reach the minima of the difficult-conditions speed (40 km/h on the
  main streets, 20–30 on residential ones); their p25 (700–1,000 m on main streets) is at the 50 km/h minima.
- **Crossfall** (9.5): 2.5 % (2.0 % only in reconstructions), crowned or one-sided on an undivided street,
  one-sided per carriageway on a divided one; sidewalks 0.5–2.0 % falling to the kerb. The change of
  crossfall rises along the edge at most 1.2 % (design speed ≤ 50 km/h). The resulting slope
  √(grade² + crossfall²) is at most 9 % (A, B) or 15 % (C), and at least 0.5 %.
- **Grades** (table 12): B 6 %, 8 % where justified, 9 % over at most 150 m; C 9 %, 12 %, 15 % over at most 50 m;
  D1 5 %, 8.33 %, 12.5 %. At least 0.5 %. Measured p99: primary 6.4 %, residential 12 %, living street 14 %.
- **The tram belt** (3.1.18, 7.3, figures 2–4, 13):
  - a belt raised at most 7 cm counts as unraised;
  - the separating kerb (tvarovka) stands at most 9 cm over the carriageway, its inner edge 1.50 m from the
    track's axis (1.30 m in reconstructions);
  - a raised kerb stands 1.75 m from the axis (ČSN 28 0318);
  - the belt is 7.00 m wide (6.00 m in reconstructions, 5.70 m where tight; 8.00 m with a mast between the
    tracks); the track centres move to 3.50 m apart with buses on the belt, 4.00 m with a mast between them
    (the base distance is drawn in the figures only).
- **Kerbs** (Z1): a lowered kerb is under 80 mm; at driveways 2–5 cm (7 cm where justified).
- **Prague's sidewalks in IPR** (`street_profile.py --sidewalks`, 2026-11-15, the five lines' level-0 sidewalks,
  every 2 m along their kerbs):
  - **IPR's raster smears the kerb** 1–1.5 m into the sidewalk: at Hartigova IPR rises 7–9 cm in the first 1.5 m,
    then 1–1.5 % across. A survey "sidewalk" can also be a wider area: at Hartigova (3687, −70) the first 5 m rise
    1.2 %, the 10 m behind them 0.8 m (a forecourt or a slope).
  - **Crossfall across the walkway** (a line through IPR from 1.5 m off the kerb to 1 m before the far side or 5 m
    from the kerb, 94,689 samples): the median rises 2.3 %, p25–p75 0.9–3.7 %; 24 % are within the norm's 0.5–2 %.
    Hartigova reads 1.8 %. (A first read from 1 m off the kerb across the whole width gave 2.5 %.)
  - **The kerb step** (IPR 1 m into the sidewalk less 1.5 m into the road): p25/50/75 5.9 / 10.4 / 14.8 cm, the
    median `tools/kerbs.py`'s `KERB` 0.10 m.
  - **The user** (#512, 2026-11-15): "Hartigova sidewalks should be pretty flat overall, not sure where that steep
    angle comes from. Small angle is good for draining water but shouldn't be noticeably too much." So the generated
    walkway takes IPR's crossfall held to the norm's 0.5–2 % (data/truth.json `sidewalk-crossfall`); IPR reads the
    sidewalks steeper than they are.
  - **Today's survey surface at Hartigova falls away from the kerb** (median −2.2 %): `kerbs.py`'s +0.10 m may land on
    a line that is already the kerb's top there.
- **The user on Hartigova (line 37):** "hartigova has central tram corridor which is on topside of kerb. Roads
  crossing it come up to the track level." (#512, 2026-11-14.) The raised belt keeps its kerb along the
  street; a crossing street ramps up to the bed.
- **A street's crown ends where a side street leaves it downhill** (#780, measured 2026-11-20). A street's surface
  is its centreline's profile and a crossfall either side, the crossfall smoothed along the street. Its road area
  runs on into a side street's mouth, and there the smooth is not the ground: on Nad Ohradou (line 37 (3877, -10))
  the mouth of Na Vápence falls 6.5 % where the smoothed crossfall is 1.3 %, the crown lay 0.55 m over IPR 9 m
  out, Na Vápence was pinned to it and 69 m2 of road stood 0.3-0.6 m up beside the garage ramp. A side's width
  now ends where its crown still lies within 0.05 m of IPR before it leaves it by 0.15 m for a metre
  (`street_profile.crossfall`), no further than its neighbours' 3 m along the street, and never under 3 m; past
  it the road is the junctions' fill. The least width decides whether that helps: left 1.5 m, the drive lines
  (1.75 m from the centreline) ran on the fill, which meets a street across a step, and line 23's jumps went
  from 45 to 75; at 3 m they go to 31. Road patches of 20 m2 or more standing 0.3-1.5 m off IPR, published ->
  with the rule: line 37 8 -> 2, 23 11 -> 6, 22 43 -> 20, 17 36 -> 19, 9 39 -> 21.
- **The generated street surface on the five lines** (`street_profile.py --wide 300`, #512, 2026-11-15):
  - **Inside the road** (1 m in from its edge) it lies within 0.18-0.25 m of IPR at p99, the survey's surface within
    0.47-0.83 m; sidewalks 0.18-0.21 m against 1.4-2.1 m.
  - **Along the survey's straight outlines** (#470's statistic, 0.3 m inside) it scatters more than the survey's
    outline and less than IPR: roads over 8 cm off their 21 m mean 1.7-2.7 % against the survey's 1.2-1.6 % and
    IPR's 1.9-3.4 %. At the edge it follows what the lidar sees there (walls, ramps, the bed's edge): of Palmovka's
    157 samples over 8 cm, 102 have IPR over 8 cm too.
  - **Triangles** (pydelatin on a 0.5 m raster, both filled off the streets from their nearest street cell): at 2 cm
    22-31 % fewer than IPR's own raster; at 5 cm 6-24 % more, its kerbs kept as 10 cm steps where IPR rounds them.
    The survey's outline triangulation has a tenth as many, linear between noisy vertices. With the terrain beside
    the streets in the raster, the edge between the two drew most of the triangles.

### Tram stops: ČSN 73 6425-1 (2007)

The stops norm (bus, trolleybus and tram stops, part 1: design; `raw/reference/norms/`, the user's upload, #512).
Chapter 7 is the tram's; the platform surface and the bus clauses in 6.2.2 apply to it too.

- **Kinds beside an unraised belt** (7.1.1): a boarding island; a raised carriageway, the lane lifted to the
  sidewalk's level less 20 mm, which cars drive over (pojížděný mys); a stop peninsula (mys), with the cars led
  over the tracks in a lane at least 3.50 m wide. On C and D1 streets in reconstructions the stop may be at
  the carriageway's level, guarded by a signal (časový ostrůvek) or humps (7.1.2).
- **Where** (7.2): after a junction by preference; on grades up to 5 %; not on a curve's outer side
  unless the driver sees every door; opposite stops facing each other between junctions.
- **The edge** (7.3.1–7.3.3): the platform runs 0.50 m beyond its boarding edge at either end; the edge is
  as long as the two longest trains plus 1 m, at most 67 m, or one train where one line stops or at 12 trams
  an hour or fewer.
- **Surface** (6.2.2.3, 7.3.4): crossfall 0.5–2 %, the resulting slope at most 5 %; where trams lay over, the
  track's grade is at most 0.25 %.
- **Width** (7.3.5): free width 2.20 m (2.50 m recommended), where tight 1.70 m (2.00 m); a shelter's side
  wall may take 0.50 m of it.
- **Height** (7.3.6): above the top of rail, to suit the fleet, at most 160 mm under a low floor (a bus edge
  stands 200 mm over the road, 160 mm in reconstructions, 6.2.2.4).

### Buildings and structures (Geoportál, Mosty 3D)

- **IPR Geoportál** (CC BY 4.0): LOD2 buildings (untextured, gzipped I3S, we read the non-Draco buffer:
  breaks if IPR goes Draco-only), retaining walls with `vyska` (which side is retained is not in the
  data), tree register (multipoint) and tree rows.
- **Mosty 3D**: photogrammetry 2001–2008, ±0.5 m, blocks from the highest surface seen from the air
  (parapets) down; can predate rebuilds. **The survey deck wins wherever it exists**; the model gives
  sides, piers and spans elsewhere, and is trimmed over surveyed decks. The whole layer is small (49 meshes,
  672 bridges, 7.7 MB): the height import reads it city-wide (`tools/mosty3d.py`). Its top at a tram bridge's
  end is within 1.05 m of the rail (p50 0.13 m); a bridge over a tram is 3.3 m or more above it (#192). Its
footprints include abutments on land (top within 1.5 m of the lidar terrain): 10 % of the tram bridges' track. Spans
  are flat blocks: Libeňský most's 1.1 % approach is 0.3–1.2 m steps. It has gaps: no bridge between the Libeň
  river bridge and its viaduct (14.4624–14.4660 E).
- **A building's ground height** (#507, `ground_partition.py --calibrate`): the survey's 3D building outlines (ZPS KR
  `Hranice_budovy`) against IPR's ground 0.5 m outside the OSM footprint, 17,240 buildings on the five lines: IPR's
  median along the footprint is off by 0.29 m (median |error|, p90 1.42 m, mean +0.08 m); its 10th percentile 0.49 /
  2.13 m, its lowest 0.67 / 2.48 m (both biased low: a cellar ramp, a yard). The p90 is the buildings on slopes,
  where one flat height cannot match the whole outline.

## The T3 and the network it runs on

- Tatra T3 figures (ČKD pamphlet, unverified): 16 t empty, 4 × 40 kW, ~39 kN, 1.8 m/s² service accel and
  brake, 5 m/s² emergency, 24 seated + 86 standing.
- **The T3's electric system** (#351): `src/tr37.js`, `src/electric.js`, read from ČKD's manuals in
  `docs/research/prazsketramvaje/t3-accelerator.md` § 9. Nothing but the pilot motor moves the accelerator, the relay in
  every mode. The wire's resistances and no-load voltage are assumed; nothing found measures them.
- **How the autopilot drives it** (#351): to a stop or signal it drives until coasting 8 s meets the braking curve, then one curve to the
  point at 0.85 of what step 5 gives, at most 1.0 m/s² (on wet leaves half the grip, 0.74 on the level, less half a downhill's pull;
  to a lower limit less the whole pull, as nothing takes a slide there that the track brakes take at a point), with the steepest downhill to it counted, for
  the coast as for the curve; no crawl and no drive pedal once braking or while coasting in over the drive's target (`tools/headless.py
  --checks stops`, `tools/test_drives.py`). The pedal to the floor only past what step 5 and the gradient make. It pulls away at up to
  1.0 m/s², on step 3 below 20 km/h on the level unless step 3 cannot make it (a full car), and at up to 1.2 m/s² above 20 km/h (step 4).
  Once it let go it coasts down 1 m/s under the speed it holds before pressing again (a fifth of the speed in slow streets, #502;
  0.35 m/s on a climb). A turn the drive pedal must make before a point is a limit of its own, from which the 1.5 s without the brake still leaves the
  point on its curve; only where the limits have it pass the contact faster than the button works coasting (≈19 km/h).
  Smoothness costs the timetable quickly: 4 % slower took line 22's late penalty from 17 to 509, so `stops` counts it too. The button works only
  below ≈19 km/h, so a turn under a contact just before a stop or inside a switch's braking is a limit of its own, 15 km/h, or the tram goes the wrong way.
  A light brake step lifts the accelerator (29 → 34 at 19 km/h, step 1), so holding a limit, or up to 0.6 m/s under it where a lower
  limit's curve begins, it coasts through a diverging contact rather than brake for less than 0.6 m/s over it: at Anděl that brake step had
  the drive pedal make the turn 22 m before the stop, 7.8 m short on the track brakes; the switch's 15 km/h just past the stop begins 2 m
  before the contact.
  The crawl on main was held by drive pulses 1–2 m short. Behind something that moves it may drive and crawl, under that curve
  all the same: a car crossing just past a stop puts its stopping point 6 m short of the stop, and forgetting the stop for that
  second brought the drive pedal back uphill.
  **One brake press into a stop** (#502; the user, 2026-11-15: "consistently stop in a single pedal press"). The fade below ≈9 km/h
  (steps 1–2 to nothing, step 5 handing over to the shoes) was handled by the last metres' rule, but only while the pedal was down.
  Where the plan found it would roll in by itself it asked to coast, and the foot came off: 2–3 m out at 3–6 km/h and on again to
  stand, or off at 11–12 km/h after step 5 and on again 6 m out. Now, braking with a stop or a signal ahead, where it would only
  coast, the foot stays on step 1 (spent below 9 km/h, so it rolls as if coasting), where step 1 does not stand it short and the stop's
  braking begins within ≈3 s. The brake let off and pressed again inside an approach (`stops` pulses, seeds 1–5, against main at
  609a4bc): line 9 15 → 2.6, 17 9 → 1.6, 22 10 → 1, 23 1.8 → 0.6, 37 7 → 1, the stops as precise. A separate braking for a tram, a car
  or a lower limit 75–150 m out, then a coast, stays: the drivers coast there too.
  So does a separate braking for the switch button before a turn's contact close to a stop (#627, PR #631): from the 20 km/h street
  the first brake step lifts the accelerator over the button's 30 (step 1 holds it at 30 only up to 17 km/h), so the tram slows to
  15 km/h 2 s before the contact, coasts through on the button and brakes again for the stop; at Anděl one press more in four of five
  seeds (the user, 2026-11-16: "I would allow another press for the switch contact, that's a fair use and kind of stress test, with
  radio controlled switches it would be easier").
- **Real rides, and how far to follow them** (#351, PR #363): GPS of four rides on line 23 from the user, read from the speed with the
  gradient and the running resistance taken out: car 6921 Lazarská to Královka and car 6312 Královka to Bílá labuť on 2026-10-31,
  T2R 6004 and T3SUCS 7290 on the diverted route on 2026-11-07, the last with a phone's accelerometer for 11 minutes. The drivers
  coasted 38–48 % of the distance; before a stop the drive came off 81–124 m out at 28–35 km/h and they braked the last 22–43 m from
  21–25 km/h at 0.67–0.86 m/s² (p90 0.9–1.1). The accelerometer counts ≈ 6 presses of the drive pedal a km, each ≈ 6 s at ≈ 1 m/s²
  (peaks 1.3, p90 1.7), braking at 0.7 (peaks 1.0, p90 1.6); the GPS reading of the same 3.3 km counts 7.3 a km. The phone's Y axis
  reads the tram's acceleration 1:1 once its zero is taken at each stand (it sat 0.15–0.34 g from the tilt and the stop's
  gradient); its file is named when it was saved, not started. Pulling away on the level the autopilot is about as quick (0.91 m/s² net
  to 30 km/h against 0.51–0.80 on the October rides, the T2R 1.05); where it reached 25 km/h later it was holding a limit on the way. Moving, the rides were up to 10 %
  quicker than the autopilot, a third of that on the climb to Královský letohrádek, where our limits end later after each slow
  spot (#211). The user, 2026-11-07: "I did notice the drivers went a bit milder on the tram, probably because it's Heritage ride
  and on that route they err on the side of bigger delay than aggressively following the timetable. Other difference is our
  inaccurate speed limits and holding them longer after each curve. So the comparison is just rough to get in the ballpark and our
  autopilot can lean a bit on the faster side where it makes sense."; "Later braking to match real driver"; "the general point of
  driving with zrychlovač still seems to be minimizing power waste, so drivers keep the našlápnutí amount low, use it hard to not
  spent burning much power in resistors as well as conserve momentum, save time by coasting at speeds under limit."
- **Which steps the drivers use** (#351): the phone on T3SUCS 7290, zeroed at a stand, reads the traction's acceleration whatever the
  gradient, as the model's on the level. With 40 passengers the model's drive steps 1–5 give 0.51 / 0.75 / 1.01 / 1.29 / 1.59 m/s² up to
  30 km/h (falling above as the field weakens: 0.89 / 1.12 / 1.30 on steps 3–5 at 35 km/h) and the brake steps 0.33 / 0.59 / 0.77 /
  0.93 / 1.11. The phone read 0.95–0.99 pulling away to 20 km/h (step 3), 1.21–1.29 from 20 to 40 km/h (steps 4–5), and braking
  0.81–0.85 below 30 km/h, 1.06 from 30–40 (steps 3–5); whole stops from 20–40 km/h averaged 0.95–1.10 on the phone and the GPS.
  All the recorded cars have the same TR37 (the user, 2026-11-07: "all of recorded cars should have pretty much the same TR37.
  Difference can be mostly tuning and wear between depot servicing").
- **The ride of 2026-11-08, and the presses per stretch** (#396): GPS of T3SUCS 7122 westbound from Jindřišská to Pražský hrad and of
  T3 6921 eastbound from Pražský hrad to Bílá labuť (then on a diversion), and on 6921 a phone held in the hand for two parts (down
  Chotkova from Královský letohrádek; Národní třída to Vodičkova). They approach the stops as rides 1–4: coasting 36–45 % of the distance,
  the drive off 110–124 m out at 29–35 km/h, the last 32–55 m braked from 24–25 km/h at 0.71–0.72 m/s². The user counted 7122's presses
  from zero, drive + brake: 38 + 19 to Pražský hrad, 2–3 + 1–2 a stretch on the level, 12–13 + 2 up the climb to Královský letohrádek
  (the user: "Experienced driver seems to know well where exactly to drive to get most of each press between stops, only traffic adds
  more presses than usual undisturbed ride would"). The GPS estimator reads 44 + 25 there: about a press a stretch too many, and fewer
  up the climb, where a press that only holds the speed does not show. A hand-held phone's zero drifts by 0.4–0.6 m/s² between stands,
  so its levels are taken from the GPS and the gradient, and it shows the shape within a second: a drive from 0.8 m/s² or more ends with
  a drop to coasting within 0.1–0.2 s (5.4–8.3 m/s³), where the model's falls at 1.5–2.4 m/s³ over 0.3–0.7 s, the autopilot stepping
  back through step 1 (T3SU-03 p. 4; the user: "Some zrychlovač shows larger jerks at the end of drive"). The model's car has the sharp
  end too: let go at once, the damping resistors come back in over 2 × 0.1 s and the line contactor opens (`src/tr37.js` `dampStep`,
  assumed), and coasting holds the preparation current (40–90 A on a T3SU, DPP's accelerator exam). So the drivers lift off a high step
  at once, against the manual's step back (the user, 2026-11-09: "I suspect the driver rather than the tram"); the autopilot keeps the
  manual's way. The DPP textbook and the web say nothing more. The recordings: `raw/reference/rides/` (snapshot 2026-11-09r). The autopilot on the same
  stretches (line 23 built westbound for 7122, seeds 1–3) pressed 63 + 45 westbound and 80 + 59 eastbound, where 6921's GPS reads 46 +
  39; besides traffic, from holding a speed on gradients and driving down descents.
  With #396 (a switch contact far ahead no longer hides nearer limits from the drive's target; coasting into a lower limit as into a
  point; no drive pedal down a descent where coasting gets there; brake step 1 held down a descent where it barely slows): down
  Chotkova 4.7 + 10 (main 8.3 + 17). On the five lines, dry, seeds 1–5: drive presses −4 %, brake applications −13 %, the wire's
  energy −4 to −10 %; the mean delay +18–28 s on lines 17, 22 and 23 (inside main's seed spread), the late penalty outside it on
  lines 17 and 23 (19 → 78, 7 → 25). Holding a drive step to 0.6 m/s over up a climb pressed more and ran later; holding brake step 1
  down every descent to 1 m/s under ran line 23 40 s later. On W2's data (73c2a32): brake applications −6 to −18 %, the wire's energy
  −4 to −11 %, the late penalty outside main's spread only on line 23 (11 → 63); the user took the fewer presses for that
  (2026-11-09), the timetable's part being #242.
- **The rides of 2026-11-11** (#500; `raw/reference/rides/`, snapshot 2026-11-12r):
  - **The recordings:**
    - T2R 6003 (5.7 km) and T2R 6004 (5.1 km), TR37, on line 23's diverted loop (Václavské náměstí, Masarykovo nádraží, Těšnov,
      Vltavská, Dlouhá třída), each with a phone lying still for the whole ride.
    - T3M 8088 on line 37 from Strážní toward Palmovka, the phone in the second car.
  - **Reading the phone:**
    - The phone's clock is the file's save time less its length; the GPS acceleration fits it within 3–13 s.
    - The forward axis is fitted per part where the gravity vector holds still, which catches the phone moved once mid ride
      (r 0.80–0.97 against the GPS; 6003's first 207 s 0.44, left out). The zero is taken at each stand.
    - Phases: drive over 0.20 m/s², brake under −0.25, for 1.5 s or more.
  - **The two T2R drivers** (6003 / 6004):
    - presses: 5.8 / 7.6 a km;
    - coasting: 67 / 54 % of the distance;
    - drive level up to 30 km/h: 1.0 / 1.2–1.3 m/s² (the model's steps 3 / 4 with 40 passengers);
    - braking below 20 km/h: 0.5 / 0.9 m/s² (steps 2 / 4);
    - approach to a stop (medians):
      - the drive off 163 / 97 m out, at 26 / 27 km/h;
      - the last braking 30 / 54 m from 21 / 32 km/h, at 0.54 / 0.68 m/s² (GPS).
    - A drive of 0.8 m/s² or more ends within 0.25–0.3 s at this 0.5 s smoothing, as in #396.
  - **Against the autopilot on the four stretches line 23 shares, Vodičkova to Bílá labuť** (dry, seeds 1–3):

    | | 6004's run, presses (drive + brake) | autopilot's |
    |---|---|---|
    | Vodičkova to Václavské náměstí | 67 s, 1 + 2 | 39–70 s, 2–4 + 1–4 |
    | to Jindřišská | 94 s, 2 + 2 | 55–60 s, 1–4 + 1–3 |
    | Jindřišská to Masarykovo nádraží | 76 s, 4 + 4 | 91–155 s, 8–9 + 3–4 |
    | to Bílá labuť | 95 s, 4 + 4 (6003: 81 s, 1 + 3) | 73–79 s, 6–7 + 4–5 |
  - **Jindřišská to Masarykovo nádraží, traced** (#502, seeds 1–3 on main at 609a4bc): our limits allow 74 s. The time
    over that is a red at the junction 237 m out (21–27 s held in two seeds of three) and the timetable's 180 s stop to stop:
    with 110–165 s in hand, the mild driving took the 15 km/h limit after the stop to 9 km/h and the 20 before Masarykovo to 15.
    The presses came from holding those speeds up 5–13 ‰: a press each time it sagged 0.35–0.5 m/s, 3–4 in each zone. 6004
    pressed once in each and let 15 sag to 12 and 20 to 16. Since #502 the mild driving keeps 20 km/h (a lower limit its own
    target) and the hold sags a fifth of the speed (0.35–1 m/s): 6–7 presses there where traffic leaves it alone, and a car on
    the track or a stand at the red adds a press each.
  - **The T3M on line 37** (front 23 m ahead of the phone):
    - **The trip:** it left Vozovna Žižkov 50 s after the game timetable's 08:20 (trip 17; the user: "always assume same or delayed
      trip, never earlier"), Ohrada +107 s, Krejcárek +171 s.
    - **Running times:** 84 s to Ohrada (timetable 60, the autopilot 60–62). To Krejcárek 164 s, 68 of them standing at the
      junction past Ohrada (timetable 120, the autopilot 103–110 with 7–8 brake applications).
    - **Over our limits:**
      - 19.7 km/h over Ohrada's crossings (15; 1.31 times, under the derailment's 1.5);
      - 46.9 in a 43 curve;
      - 54–58 where 50 is posted and 63–67 where 60 is posted, about 200 m down toward Krejcárek;
      - 29.4 where 25 is posted before Palmovka.
  - **T3M 8088 again on 2026-11-12** (the phone at the end of the second car, the front 31 m ahead; snapshot 2026-11-12s), to compare:
    - **The trip:** the same one (trip 17): +50 s at Vozovna Žižkov, +110 s at Ohrada, +201 s at Krejcárek. To Krejcárek 197 s, 87 of
      them standing at the junction past Ohrada.
    - **Down toward Krejcárek the sign says 65, not OSM's 60** (the user, 2026-11-15, with a photo of the sign: "there is actually
      65 km/h limit which seems to be in the same place as osm's 60. So osm is either out of date or wrong"). OSM tags this track
      (way 412908226) 60 and the other direction (way 334167230) 65. This ride's top was 60.7 km/h; the day before's 63–67 was
      within the 65 but for 67.2. The game posts 65 there from `data/truth.json` `postedSpeeds` (#612): `tools/osm_speeds.py`
      reads a way's posted speed there over its `maxspeed`, and says when an extract tags the same (the user changed the
      tag in OSM on 2026-11-15; the snapshot's extract is of 2026-11-04).
    - **Where the limit rises from 50:** both rides ran 53–57 km/h (medians 53–54) 50–100 m before the sign, where 50 still holds:
      the drivers pick up speed as the sign comes into view.
    - **The rest:** 21.4 km/h over Ohrada's crossings (our 15; 1.43×, under the derailment's 1.5×), 46.4 in the 43 curve, 28 where 25
      is posted before Palmovka, and 18.4 over the 15 restriction 38 m before Palmovka.
- **Driving to the timetable** (#242): the time in hand to the next stop sets how it drives. That is the stop's timetable
  time, less now, less 1.3 times the quickest run there at the limits, less a 15 s dwell.
  - **Up to 10 s in hand it catches up.** The target is 0.2 m/s under the limit, and brake step 1 holds down a descent only to
    0.6 m/s under. At a 15 km/h limit, 0.4 and 1 m/s held it at 10-14.5 km/h, where the drivers of two line 23 rides held 14-16
    down Chotkova (#431). Within reach of a turn's contact the target keeps 0.4: 0.2 under Anděl's 20 km/h put the accelerator
    at 31 coasting, over the switch button's 30.
  - **Over the next 30 s it grows milder:** curves as at 0.8 m/s², 0.4 under the limit, the 1 m/s hold, the target up to
    10 km/h under but never under 20 km/h (#502), coasting up to twice as long, braking a quarter softer (the user, 2026-11-10: "if there's enough time the
    autopilot doesn't go as hard into curves and uses less pedal presses to conserve power. If he's late then he uses the
    probe's plan to catch up").
  - **Against main at 973726c** (with #451's curves; stops check, seeds 1-5):

    | line | arrivals within ±30 s | mean delay | drive presses |
    |---|---|---|---|
    | 9 | 40 → 47 % | 52 → 44 s | +7 % |
    | 17 | 6 % → unchanged | 116 → 96 s | −7 % |
    | 22 | 4 → 29 % | 160 → 75 s | −6 % |
    | 23 | 8 → 19 % | 116 → 74 s | −15 % |
    | 37 | 54 → 61 % | 44 → 37 s | unchanged |

    Energy from the wire is 0-2 % lower on every line.
  - **In other weathers** (`--checks autumn,rain,winter`): wheel spin, slides and sand stay within a few per cent of main's,
    and the delay falls in all three.
- **Where line 17 loses its time** (#460; the `stops` check, seeds 1-5, main at f4d03d2; per stretch `arr`, `dep` and the run's
  `depOnTime`): it departs 93 s after the timetable on average, within ±30 s of it at 8 % of the stops. The delay is the timetable's:
  - **The GTFS has whole minutes only** (all 40,116 departures of 2026-10-21 at :00). Levského and Sídliště Modřany, 258 m apart, share
    a minute in all 77 trips, so the run is 43 s late at its second stop and leaves it 50 s late. That is on purpose (the user,
    2026-11-16, #621: "same minute are on purpose to leave as soon as possible and catch up on later stops"): left as it is.
  - **Sídliště Modřany to Přístaviště is 60 s a stretch**: twelve stretches of 286-733 m at 50-65 km/h (65 where OSM has 70), eleven of
    60 s and Nádraží Modřany's 120, 780 s in all, where the quickest run at our limits takes 665 s before any dwell. A 700 m stretch
    from stand to stand takes a T3 ≈57 s at 1.2 m/s² up and 1.1 down. The departure delay grows from 44 s at Modřanská rokle to 158 s
    at Dvorce, and Hercovka's 60 s for 888 m adds 64 s more.
  - **The centre gives it back**: 120 s for 420-470 m from Jiráskovo náměstí to Právnická fakulta and 240 s to Strossmayerovo náměstí.
  - **Our run against the quickest at the limits** (seed 1, 3312 against 2351 s): 407 s standing at stops, 88 s standing for trams,
    signals, obstacles and cars, 170 s braking more gently than the quickest's 0.9 m/s², 257 s over 2 m/s under the limit (most of it
    the last 20-90 m into stops, rolling in at 13-15 km/h after a switch's limit), less 80 s pulling away harder than its 0.8. Rolling in
    only within `coastT` instead of 15 s moved nothing: 93 → 97 s, inside the seeds' spread.
  - **By D 1/2's window** (§ 16, PPS Q51: 0-59 s late from the first stop, 0-179 s from the others, `depOnTime`) the departures are on
    time at 97 % of the stops on line 9, 94 % on 17, 91 % on 22 and 100 % on 23 and 37. Within ±30 s of the timetable (`arrOnTime`,
    #242's measure): 44, 8, 21, 21 and 48 %.
  - **The autopilot keeps catching up to the timetable's minute; D 1/2's window is for the score only** (the user, 2026-11-16, #621:
    "autopilot should be catching up to the timetable. The on time according to d1/2 should matter only for scoring. Real timetables
    are tight, some of our in game timing can be improved by signals, proper placement and tuning the controller, that's for later
    milestones").
- **Running resistance** (`src/tram.js`): 650 N a car, 28 N a car per m/s and 4.2 (0.7 + 0.3 × cars) v² N of air, plus a curve's; gravity
  m g sin θ on the mass alone, the turning parts (2.4 t a car) only in the inertia. Coasting with the preparation current, one car with 40
  passengers slows at 0.067 / 0.077 / 0.090 / 0.110 m/s² at 15 / 25 / 35 / 47 km/h on the level; the phone on 7290 read 0.090 / 0.100 /
  0.089 / 0.090 coasting (p25–p75 0.05–0.15), so the totals agree and the model's rise with speed is not settled by one ride.
- **The track brakes** (#351, `src/tr37.js` `trackPull`, `trackMu`): four ČKD FC33 magnets a car, two a bogie, 60 kN attraction each, fed
  from the battery (T3SU-22 p. 1, T3SU-02 p. 1, T3SU-13 p. 1). The rear bogie's come on at the pedal's first stage past parking, both bogies'
  with the pedal on the floor (the DPP T3 textbook p. 5). Their friction on the rail rises as the speed falls: 0.10 at 70 km/h, 0.12 at 40,
  0.16 at 20, 0.20 at 10 (a tram's curve, TU Dresden's braking lecture 2020/21, slide 97). The pedal on the floor then stops an empty car
  from 42 and 50 km/h at 2.6 m/s² and one with 40 passengers at 2.35, from 2.2 m/s² at 40 km/h to 3 below 15 (4.2 at the end, empty).
  A T3 measured at VUT Brno stopped at 2.85 and 2.65 m/s² from 42 and 50 km/h (Krychtálek 2010 p. 26, the load not given); ČKD's
  informative figure is 2.3 (T3SU-26 p. 5). With a flat friction of 0.1 it had been 2.24 at every speed. They are for danger only
  (D 1/2 § 34.4: when service braking cannot avert it; the textbook: "jen v případě nebezpečí"; the user, 2026-11-08: "those should be
  used only in emergency like walker or car appearing in front of tram or the non dry weather where it can't stop"). The autopilot
  takes them only for a walker, a car or an obstacle in the way, or where the grip is under 0.25 or the wheels slide. A stop, a
  signal, a junction or a tram ahead on dry rail gets step 5 at most.
- **The load** (#351, `tools/headless.py --checks load10,load90`: the stops run with the passengers held at 10 % and 90 % of the
  capacity): a full car's plan brakes gentler and longer, as step 5 gives less over the mass, and boarding slows over 75 %. A full car
  pulls away on step 4 where step 3 cannot make 1.0 m/s² (on step 3 it made 0.8). At 90 % against 10 %, lines 9, 17, 22, 23 and 37
  (seed 1, line 23 seed 2): +79, +320, +302, +206 and +142 s to the terminus (main +4, +263, +240, +46, +50 s); the departures' mean
  delay 99, 308, 251, 214 and 91 s at 90 %. The full car ends within 30 s of main's on four lines, the empty one 3–63 s ahead of
  main's. Line 23's full car came down Chotkova 16 s behind main's and waited a whole cycle (108 s) at the signal main's passed. A
  run's length also moves 35–223 s from seed to seed, as the traffic reshuffles.
- **Where the traction's energy goes** (#351, `--checks stops`: lineKWh, wasteKWh, brakeKWh; `tools/test_drives.py` in Wh): the
  starting resistors take 36 % of what the wire gives on a level test drive and 78 % holding 15 km/h in a slow street, almost all
  of it pulling away. Coasting 1 m/s under the limit before pressing again on step 3 (the drivers' "few presses, hard") cut the
  test drives' presses by 10 % and the waste by 1 %, cost 0.7 % in time and 13 % more pedal steps, and slipped on leaves up a climb:
  not kept. Steps 4–5 from a stand on the level (T3SU-03 p. 4 says 1–3) waste 4–10 % less with a full load, nothing empty.
- **Wet leaves and sand** (#351): the box holds 25 minutes of sanding a shift and is not refilled (`src/tram.js` `sandSecs`; the user, 2026-11-07: "on the level of
  minutes if not more"). That is a tram box's least, 17 dm³ by ČSN 28 1300, at a sander's 400–500 g per 30 s (Matečka 2015, VUT Brno,
  `raw/reference/adhesion/`, #266); the T3's own box is not known. 90 s ran dry on every line 9 run; the
  track brakes sand too. On a leaf patch (0.06) every step slips from a stand (step 1 pulls 0.60 m/s², the grip is 0.59), and
  slipping wheels pull 0.7 of the grip, 0.41 m/s² (main's on/off model; #265's creep curve, half the grip): with the box empty a patch up more than ≈ 38 ‰ cannot be left (line 17 s 18663
  at 58 ‰ and line 9 after Bertramka, on main as with #351's autopilot). With 90 s, sanding at every slip and slide ran the box dry half way
  along lines 9, 17 and 22; sanding only where it decides something, it still ran dry there, while 23 and 37 kept a third to two
  thirds. Pulling away the autopilot sands only where slipping wheels would not climb with 0.15 m/s² to spare, then up to 3 m/s;
  braking, on every slide: an autumn run uses 34–203 s of the box. Rationed to a stop point near ahead, it slid braking for Chotkova's
  20 km/h down 55 ‰ without sand and came in at 35; the autumn runs' speed penalty was 495, main's 53, and 38 with sand on every slide
  and the plan less the downhill's pull (`--checks autumn`, all lines, seeds 1–5). With the box empty the track brakes take a slide toward a
  point and let go once the rail under the tram gives what is still needed: held past a patch's end they stood the tram 13 m short
  of Mezi Hřbitovy up 25 ‰. How it reacts to a spin and a slide on the wheels' own speed: the next entry. A slide over 1.2 s above
  3 m/s costs the flats penalty (`src/game.js`).
- **Driving on slippery rail, the wheels turning on their own** (#265; `--checks autumn,rain,winter`, all lines, seeds 1–5, against
  main's on/off model):
  - **A step's force is fixed by its current** and does not fall with speed until the accelerator has run out
    (`TR37.driveForceAt`). On a two-car set it is 23, 34, 46 and 59 kN on steps 1–4, up to 20 km/h. At 40 km/h steps 3 and 4 pull
    35 and 41 kN.
  - **Snow's 0.12 holds 42 kN standing and 32 kN at 40 km/h** (Curtius–Kniffler, `muSpeed`). Step 3 never stays within it.
    - Let back onto step 3 every 4 s after a spin, it spun again: 270 spins on line 9 in snow.
    - Capped at the grip at the speed, slipping fell to 0–4 s a run (main 29–125 s), and the presses and comfort came to about main's.
    - The cap stops at the lowest step that still climbs the grade. Up Trojská's 80 ‰ in snow that step is at the grip, and only
      sand holds it.
  - **A locked wheel stays locked:**
    - it gets half the grip;
    - the equipment sees it standing, so the shoes come in.
    Stepping off one step at a time, it slid 5–8 s from 25 km/h. Released at once, it grips again within a second.
  - **At 57 km/h down Modřanská rokle in snow the rail gives 0.25 m/s²** after the descent's pull. A signal 272 m ahead then took the
    tram over three limits. Down a descent it now keeps to what stops within 200 m.
  - **Any step spins on a leaf patch (0.06).**
    - Each spin is the pedal off and a press again: autumn's presses were 1.2–1.4 times main's.
    - Sanding while the first axle crosses a patch on the drive pedal brings them within a few per cent of main's, at 2.5–3 times
      main's sand: 270–400 s of the 25-minute box per run (#265's PR).
  - **The trade-offs kept, to re-evaluate once the leaf patches' amount is tuned** (the user, 2026-11-12, PR #426: "that's enough, we
    will tune the amount of slippery patches later"; "I wouldn't sand preemptively on every patch, just where the grip is needed").
    `--checks autumn,rain,winter`, all lines, seeds 1–5, against main's on/off model at 96537a5:
    - **Speed.** It drives within the grip, and it slows only down a descent, to what stops within 200 m; on the level it keeps the limit.
      Autumn runs 3 % longer: line 17's mean delay 170 → 239 s, spread 5–11 s over each stretch, where main spun 139 s a run. Snow's
      delay stays within main's seed spread except line 37's late penalty (36 → 67).
    - **Sand only where the grip is needed:**
      - pulling away over a patch (under 6 m/s);
      - a patch up a climb over 20 ‰, or a climb the bare rail cannot take;
      - before the track brakes where the rail cannot give a stop;
      - on a slide.
      At speed it eases off over a patch instead.

      In autumn this is about twice main's sand: 93–329 s a run, 6–22 % of the box. Rain uses 1–2 %, snow 2–11 %, and the box is
      refilled at each terminus (`data/truth.json` t3-sand-refill).

      The alternatives measured on line 9, 17 and 22, seed 1:

      | patch rule | sand a run | presses | line 9's mean delay |
      |---|---|---|---|
      | sand over every patch it drives onto | 270–400 s | within 5 % of main's | 63 s |
      | ease off over every patch, pulling away too | | | 302 s: it rolled to a stand on the patch and drove again |
    - **Presses** in autumn are 7–33 % over main's: a spin on a patch it did not see coming, or a press after easing off over one.
    - **Slides last longer than main's** (autumn 4–15 s a run, snow 8–32 s, main 1–6 s): on the creep curve a slide lasts until the brake
      is eased, where main's model cut it at once. Most of it is emergency stops for walkers and cars on step 6 with the track brakes.
      Slides begun within 30 m of a stop: line 17 in autumn 17.8 → 4 a run, in snow 9.2 → 4.6.
- T3s can meet anywhere in the Prague network, tight curves included (user, 2026-10-30): a tram/tram
  overlap between T3s is a geometry error (track spacing), not a place where they must not meet. A few
  tight places forbid KT8 and T3R.PLF from meeting; that matters once those models exist.
- Prague signals: 4 white lamps on a white plate (stop = outer two), call box with three orange LED bars,
  distant signal with a yellow "P"; switch indicator a red LED chevron on the span wire.
- **The T3's outline** (#427, `src/t3simple.js`): drawingdatabase.com's general arrangement (`Tatra-T3-1.gif`, side and
  plan, dimensioned at 20 mm a pixel) and its colour elevation (`trams_t3_01.png`, 12.66 mm a pixel) agree with each other
  and with Dynybyl's table 3, Wikipedia and the 1977 Soviet manual: body 14 000 × 2 500 mm, 3 060 mm high, pivots 3 800 / 6 400
  / 3 800 mm. In plan the ends taper from the doors (4.5 m ahead of and 4.8 m behind the centre); the front and rear doors
  stand on the taper. The drawing's plan view ends in corners 0.73–0.78 m off the centreline, too narrow against the user's
  head-on photos of 6892 (below): the model's corners are 1.0 m off it, rounded with 0.32 m, the face bulging 0.21 m (the
  user, 2026-11-10: "Let's try widening"); from above its ends are ±0.97 m wide, the hybrid's ±1.0 m, conflig's ±0.88 m. The
  plan view on p. 10 of Dynybyl's thesis is narrower still (the user, 2026-11-09: "looks more narrow, like t1 or early
  prototype than t3"). Laid over the colour elevation at its scale, the built model's windows, doors, bands and ends fall on
  its lines, except the brows over the windscreen and the rear window: the side view leans them back 0.17 and 0.12 m, the
  photo of 7290 has them upright to 2.86 m, then rolling into the roof over 0.5 m (the user, 2026-11-10: "make the front
  brow less slanted, perhaps even perpendicular? The back should be similar", "a bit thinner, like running a bit down
  towards the front and back"), the route box low on the front one, 3 cm over its lower edge. The windows wrapping round
  the ends meet the sides in upright edges with rounded corners; the livery's u follows the outline's points, which move
  back with the leaning end, so those edges are drawn through each height's own u (`ringU`), not straight in the texture.
- **The T3's driver's seat** (#246, `src/cabframe.js` `EYE`): the general arrangement's plan view has it 0.32 m left of the
  centre line (its middle at 563.5 px against the centre line's 579.5), the backrest 1.44 m and the front edge 0.96 m behind
  the nose; the desk in front of it is centred on the centre line, 0.46–0.88 m behind the nose. The cab view's eye stands
  over the seat's middle, 1.2 m behind the nose. The cab's rear wall is 1.62 m behind the nose, across the first left
  window (1.05–2.35 m behind the nose), so the cab has the window's front 0.57 m; a partition runs from it diagonally to
  the front door's front jamb (the cab view leaves that one out: the user sees the door from the seat).
- **The T3's details in Prague** (the user's photos of 6892, 6921, 7122, 8080 and 8088, 2026-11-09, #427): the red starts lower
  round the cab than along the saloon, under a cream band with a flap; the route plate hangs on the mirror's arm, which drops
  from the cab's roof; rectangular lamp units (indicator over a lamp) by the corners; a side indicator on the pillar between
  the first and second windows on the right, the second and third on the left; fleet numbers golden yellow (#e3b625) in
  bold Arial on both models (2026-11-10: "the new model uses different font from the hybrid model and my photos": it
  had Bahnschrift), their digits 0.14 m tall
  on every side (2026-11-10: "same size in all sides"; on the photos 0.13–0.15 m against the red band's heights, conflig's
  model 0.13–0.146 m; the hybrid's quads were 0.19 m tall on the ends and 0.23 m on the sides under one texture, so 0.106
  and 0.13 m digits): on the front centred on the headlights, on the rear over the white lamp just above the lamps, on the
  sides 1.36–1.50 m up and 4.17 m ahead of the centre (behind the front door on the right, behind the cab window on the left).
- **The T3 head on** (the user's photo of 6892, 2026-11-10, a telephoto from about 25 m): scaled by the skirt's foot (0.35 m),
  the red's top (1.48 m) and the roof (3.02 m), which agree to 3 %, the headlights' centres are 1.11 m up and 1.11 m apart
  (the colour elevation: 1.03 m, 1.06 m apart; the model has them 1.08 m apart, the user finding 1.11 m "a tad to far
  apart"), pointing straight ahead in black rubber surrounds with a chrome rim; the bumper 0.76–0.86 m (the elevation:
  0.70–0.80), the corner units 0.98–1.30 m with the clear lamp's centre (1.06 m) just under the headlights' line, round the
  corners ±0.93–0.99 m off the centreline (the rear's ±0.96 m), the windscreen's posts ±0.71 m, the route box 0.49 × 0.30 m
  with its top 7 cm under the roof's. The ends are open under the bumper between the skirt's corners, which reach in to the
  headlights' outer edges, ±0.65 m (front and rear, "front and back is open under the bumper").
- **The T3's bogie from the side** (the user's photo, 2026-11-10; one over the pit, 2026-11-09): the skirt is cut out in arches
  over the wheels, hugging their treads and level with their tops between them (the colour elevation and conflig's model have
  a lower, square cutout); grey wheel discs with a big hex nut on the hub inside rust-brown tyres; a curved guard inside each
  wheel; the track-brake shoe over the rail with a row of nuts on its upper bar; the ribbed rubber spring in the middle up to
  the skirt with the gearbox's housing beside it, coil springs by the wheels; everything a dusty warm grey. The coupler (the
  user's picture, "only dark"): a round bar from the yoke's pin to a clamp, the cast head with two jaws, the coupling pin
  down through them with its handle on top. Its height over the rail is the other models': conflig's classic has the bar
  at 0.594 m (0.563-0.625), the hybrid at 0.584 m (bar and head 0.527-0.641), so the built-in car's is 0.59 m (the user,
  2026-11-10: "I don't know proper figures so you might as well take it from the others"; it was 0.552 m, no source).
- **The three T3 types in Prague** (the user, 2026-11-10): the T3, fleet numbers 6400–6992, a silver bumper with two thin
  red stripes (6892: 12 mm, a quarter of the bumper in from its edges), the route box square; the T3SUCS, 7001–7292, the
  bumper brown, the route box with rounded corners; the T3M, 8005–8106, as the T3SUCS with the resistors' box on the roof
  towards the rear, short but wide ("Box on top with resistors towards back only for t3m, which has green top number
  plate"), and green dot-matrix displays: the route on the front in the rounded box, and inside the right side's second
  window the route with the destination and the next stop. AI sets take each type as often as its range is long ("their
  proportion in service (probability to appear as AI tram) roughly related to their range sizes"): 60, 30 and 10 %.
- **A T3's lamps in service** (the user, 2026-11-10, #436): "Trams run regular beams by default, off only when the car is
  turned off. High beams can be flashed as warnings or used at night on dark stretches of line." So the dipped
  headlights and the tail lamps are on by day too. The rear: the corner units' lower red lamps are the brake lamps, the
  rear panel's two red lamps the tail lamps, the white one between them the reversing lamp. The indicators: "Turning at
  junction and stopping at street level stop across car lane", at such a stop the right ones from braking into it until
  it pulls away. Between coupled cars "only the rear red lights light up" (the user's photo of 8088 coupled behind
  another, 2026-11-10): the game lights a set's front on its leading car only, the rear red lamps on every car, and
  blinks the indicators on every car, 1.5 times a second (`src/lamps.js`). The hybrid's glows (indicators, brake lamps)
  are stored at scale 0 in its asset: copied by its matrix decomposed they had a NaN rotation and never drew. Its
  asset has no tail lamps: they are added at load, 2 cm over its bumper (found by rays from behind), 0.47 m out.

## Heuristics that stand in for missing data

Review these when realism matters; most move into the build in M2.
- **Junction turns** (`src/indicators.js`, #436), where the autopilot and AI trams indicate: a switch on the route after
  which the route's heading turns more than 30° within 40 m (a crossover's S-bend comes back); on from 50 m before the
  switch until the heading has turned 80 % of the way. On the five lines: 12 on line 9 (Anděl, Újezd, Lazarská, Flora,
  Karlovo náměstí …), 3 on 17 (Výstaviště, Ke Stírce, Vozovna Kobylisy), 6 on 22, 8 on 23, 3 on 37; two switches of
  one junction a few metres apart make overlapping turns. `game.lamps.turns` lists them.
- **Turning loops** (`tools/track_loops.py`, #211): a path from a switch entered by its toe to one left by its toe,
  turning 170°+ street to street, its switches within 150 m, mean radius 18 m+. It finds 47 loops on DI's network,
  all real by the user's review (2026-11-09); it names each by its nearest GTFS stop, so Špejchar's loop shows as
  Chotkovy sady. The loops DI does not draw yet (Libuš, Nádraží Holešovice …) are missing
  ([decision record](decisions/2026-11-07-speed-limits-and-signs.md)).
- **Signals**: from OSM `traffic_signals` clusters near the route; never past the crossing they were
  made for (except along platforms, where the platform-head rules decide); two at one stop line are one.
  GO held for a tram in its dilemma zone (15 + v²/1.6 m). Distant signals where R < 110 m within 140 m.
  A tram standing past its signal before the crossing (stopped behind something): the cross street gives
  way whatever its lights show, and the tram waits until the cars already on the crossing are off it; a
  driver past the signal no longer sees it (the user, 2026-11-05, #268).
- **Gauntlets**: opposite route < 1.8 m away for ≥ 25 m along one continuous opposing traversal
  (needs exact `Route.nearest`, which refines onto the chords: 4 m samples read 0.3 m tracks as up to
  1.9 m apart).
- **Contacts** at switch − 22 m (real positions unknown), worked by the pantograph, moved out of stop
  zones and signal queues; all switches manual on purpose (driver skill).
- **Catenary poles** march out past tracks and carriageway to the kerb; a building within 5.5 m gets a
  wall rosette, else bracket arms.
- **Tram streets**: a road within 2.6 m of a track over 60 % of its length is widened 3.2 m per track.
- **Cars' curve speeds** (`src/traffic.js` Path.curveSpeeds): 2.5 m/s² sideways on the circle through each lane point
  and its neighbours, 1 m apart. A few millimetres of noise reads as a curve there. The lanes' points rounded to the cm
  took the lane points cars drive under 50 km/h on line 22 from 9,161 to 17,206 (5,368 of them slower by over 1 m/s),
  and the seeded trams came later behind them (late 7.6 → 26 s over 15 seeds). The network file keeps its paths in mm:
  9,261, none slower by over 1 m/s (`tools/network.py` path_mm, #658).
- **Pedestrian crossings** (#146): the reported line 17 ZPS sidewalk spans both tracks, 6.3 m along
  and 15.2 m across, with an independently mapped OSM zebra. Its drawn surface was 86–98 mm above
  the rails. Short survey patches crossing track need a nearby transverse mapped pedestrian way or
  an outline spanning the full track ribbon. The latter test matches 30 of 37 independently mapped
  survey crossing sites on lines 17/22; it adds eight sites without mapped footways. Narrow side
  patches stay unchanged. Crossings clear every overlapping same-level track, with refined ribbon
  triangles and survey outlines so their kerb faces also follow the height transition. Downward rays
  miss a vertical kerb: the crossing check intersects its drawn top edge with rail-head chords too.
  Decisions are in `window.game.route.ground.pedestrianCrossings`.
  `--checks crossing` retains raw hits and source IDs, and fails on unexplained crossing obstructions.
  Geometric side-surface classes have separate counts and places for rebuild comparisons. A walkable
  patch over the rail head within 6 m of a track, with no crossing evidence and not spanning the track,
  keeps its survey height (`crossingSurveyReview`). Since #444 (PR #466: the survey's ground-level
  triangles flipped to constrained Delaunay) none of them covers a rail head: on 2026-11-11, line 17 had
  four beside the route's rails (U Libušského potoka, Pobřežní cesta, Nad Trojou twice), line 9 four
  18–22 m from the route on Vozovna Motol's depot track, and the other lines none. #146's queue of six such
  places on line 17 was dropped unanswered: four had stopped being candidates and two cover no rail. A
  patch that covers a rail fails the check as an unexplained section. Overlapping survey slab sides
  remain #166.
- **Vienna-type stops**: carriageway on the doors' side 2.2–3.4 m from the track along the stop (the
  tram bed is not a car lane); facts per stop and direction in `truth.json` `stopTypes`.
- **Bridges on the model deck**: on tagged spans with model samples, the model deck is fixed like a
  surveyed bed (floor and ceiling, ±3.3 m sideways search on our own bridges); not on surveyed beds.
- **Tunnel mouths**: chains < 60 m are open roads; longer ones get a portal with a 24 m throat, heights
  from the approach road, the terrain re-covered over it.
- **Trees** ≥ 3.2 m from a track, crowns ≥ 1.9 m; **LOD2 buildings** within 2.5 m of the route lifted to
  track + 6.3 m (passages like Letenská).
- **Speed limits** (#211, [the decision](decisions/2026-11-07-speed-limits-and-signs.md)): 50 unless OSM
  posts another (up to the T3's 65), 15 from a facing switch's blades to its frog, and a curve's from
  the radius at each metre, from 5 m before it to its end (`restriction-past`: 0 m, the user: the bogie leaves the
  switch before the car's end, so no margin). The rear still has to leave each restriction. The radius is read over
  16 m of heading, which smears a sharp curve's end by about 12 m each way; most curves here have transitions, so the
  limit climbs along them.
- **A curve's speed** (#451): no sign stands at most curves, and D 1/2 only asks for a speed that suits the curvature (§ 25.7),
  so the limit is √((a + cant · g / 1.5) · R) in whole km/h at a = 1.0 m/s² unbalanced (`curve-lateral-acceleration`), and 15
  under R 25 m, where the "r" sign stands (§ 49.19). Two line 23 rides mapped on our track (6312 on 2026-10-31, 6921 on
  2026-11-08; GPS within 0–3 m of the track there) took the unsigned curves of R 30–60 m at 1.2–1.6 m/s² without cant
  (R 54 m past Pražský hrad and above Chotkova's hairpin at 26–34 km/h), and the signed hairpin at Chotkovy sady (R 24 m, 15)
  at 12–17 km/h, so the drivers keep a signed limit. The old 0.8 m/s² was a design value (0.65 comfortable, about 1.0 the
  upper bound) in 5 km/h steps: 20 km/h for R 45–60 m. At 1.0 the rides go over our limit in no curve on 6312's ride and in
  three on 6921's (4–8 km/h). With it the autopilot's moving time in the stops check fell by 95 s on line 22 and 55 s on line 23,
  with fewer presses and the same energy. Derailment (`src/speedRules.js` `derailRisk`): a second over 2.25 m/s² in a curve, 1.5
  times its limit's speed, or 1.5 times a switch's, crossing's or loop's 15 (the user, 2026-11-10: "40-50% over speed limit or
  something over 2-2.5 m/s² for at least one second").
- Stop zone −20…+12 m; adhesion dry 0.30, rain 0.17, leaves 0.15; demand peaks 7–9:30 and 15:30–17:30.
- **Traffic**: cars wait at the track only while the tram's body is on the crossing or it is about to
  arrive (16 m / 4 s); AI trams both ways run 0.2 m/s under the limit (the oncoming ones ran at 0.85 of it until
  #242), spawned 700–1300 m ahead, board 6–8 s when ours
  is within 300 m; oncoming trams stop at the far end of their own platform.
  An AI tram ahead goes on at a blinking GO only if its front gets there while the GO lasts: the blinking left plus the hold
  the controller can still give it (10 s, `PHASE_HOLD`), less a second, on its braking curve to its speed at the signal.
  Otherwise, able to stop on full service braking, it stops. Before, it went on at any blinking GO first seen inside its
  comfortable stopping distance; slowing for a junction's 15 km/h past the signal it outlasted the hold and ran the red 1.4 s
  late (line 17 seed 5, line 22 s 4211; #394). A longer hold was turned down (the user, 2026-11-10: "that would slow up the cycle and cause potential jams").
- **AI tram gridlocks** (#168): line 37 seed 4 at Balabenka closes an oncoming tram → car 307 →
  car 295 → car 297 → that tram cycle before ours arrives. The #154 recovery covered only a car
  immediately ahead of our tram. `Traffic._clearAiTramCycles` follows each vehicle's `waitFor`
  (the controlling stop reason) and fades one car after the same closed cycle stands for 30 s.
  Signal waits, boarding and moving vehicles end the chain. This is recovery for cars that cannot
  reverse out in the present model. `window.game.trafficCycles` records the removed car, cycle and
  reasons; the traffic check retains those events. `tools/bench/stuck.js` names both AI directions
  and the nearby junction cars, including their `why`, `seen` and actual wait chains.

## Checks and what they measure

- **No check reads a drawn pixel** (#411): the 75 runs of every check on every line (seeds 1–2) gave the same
  results, field by field, drawn once a second or not at all. Playwright's headless Chromium draws WebGL in
  software (SwiftShader) unless launched on ANGLE D3D11. Once a second it still took 5–12 cores of a page's ~12,
  against the game's ~1, and slowed the game's own thread (line 23's drive 55 → 41 s without it). The 75 runs took
  1633 s drawing at 4 pages, 721 s without at 8, 706 s at 12. The same GPU draws 60 heavy frames in 0.28 s where
  SwiftShader takes 47.5 s (Intel Arc A770, `tools/gpu.py`).

- `tools/lint.js` (page with `?keepgeo`): consist at stops, signals in platforms (exempts island-tip
  poles marked at placement and heads hung over the track), trees in buildings, bridges, invented walls, tram
  envelope, grade separation, railSupport, verticalCurves, terrainOverSurvey, streetWaviness,
  `deckClip` (ray down against drawn buildings and bridges), `underpassClearance`, lanes, street bot,
  `trackRadius` (over 5 m through the build's points, under 18 m; 18-20 m listed as exceptions) and `trackJoins`
  (through tracks breaking over 1° where chains meet, diverging start angles listed; direction from the parabola
  through the first three drawn points),
  `trackCorners` (a vertex turning over 1.5° between neighbours under 1°, segments up to 1.5 m: the corner a held
  heading leaves where the points begin, which `trackRadius` cannot see within 2.5 m of a track's end, #491).
- `lint({ traffic: true })` / `tools/traffic_lint.js`: slide, jump, overlap, walker hits, red runs;
  averages seeds 22, 7, 1234; a run that does not finish is a jam (follow `car.seen.car`).
- `tools/bench/`: u3 (signals, junctions, collisions), redruns, walkers, heads; `batch.html` runs them.
- `--checks stops` counts the drive pedal's presses from 0 (*našlápnutí*), those made rolling (over 1 m/s), the brake's applies
  and coasting of 20 m or more; `--checks autumn` is the same drive on wet leaves (0.15, patches 0.06) with slip, slide (seconds, episodes, and slides
  begun within 30 m of a stop: `slidesAtStops`, #265), sand and the emergency brake, `rain` in rain (0.17 ± 0.02) and `winter` in snow (ice, 0.08, ±4 m at the pedestrian crossings). A press from a stand is one per stand for any driver; the rolling ones tell pulsing from driving and
  coasting. Dry, main pressed 19–24 times a km (70 % rolling), the #351 autopilot 8.4–13 (lines 37 and 23).
- Line 17's full lint after the merge was the pre-rebuild reference (`reports/line17.json`, a local
  report, not in git); regressions compare with main's baseline in the data store.
- **Where a check's time goes** (#205, `tools/profile_check.py`, line 17 seed 1, 2026-11-04, 3 pages at once):
  the page load to the hidden loading screen takes 56-67 s, 78 % of it in `world.js` and `terrain.js`
  (`finesAt` 11 %, `_hitTri` 9 %, `dist` 7 %, garbage collection 7 %, `route.nearest` 6 %). The seeded runs
  take 85 s each (u3, traffic) with the main thread busy 99 % of it, so drawing is not what costs (headless
  draws once a second): traffic.js 40 %, terrain.js 29 % (all of it `_hitTri`, the ground triangle under a car
  or walker: 23 % of the run), route.js 11 % (`nearest` 7 %), three.js 4 %, game.js 3 %. The JS heap is
  1.1 GB after load and 1.3 GB after a run.
  The lint run is 95 % three.js ray casting (`intersectTriangle`, `getVertexPosition`, `fromBufferAttribute`):
  `railSupport`, `cantedRailVisibility` and `deckClip` cast `THREE.Raycaster` rays at whole meshes without a
  spatial index, so every ray tests every triangle of the merged street meshes (537 s with 7 other jobs running;
  #205 measured 254 s mean per lint run).
- **The ground under cars and walkers** (#245, line 17 u3 seed 1): `_hitTri` is called from `carPose` (4 points per
  car per step, ~9 s of a 66 s run), the walkers (~3 s) and `_fitRoad` at traffic set-up (~2 s). Reading the
  triangles from typed arrays once the load is done (`DtmSurface.seal`) took its share from 22 to 13 %, with the
  same counts on all 75 seeded runs. What did not help, measured:
  - reading the lidar height only when two triangles hold the point: most points have two (kerbs, overlapping
    areas), so the reads stayed;
  - `inLane` in 2 m instead of 4 m cells: the same 6.6 s, the cost is the map lookups, not the points;
  - the triangle found last tried first, when it overlaps no other: a triangle spans several 3 m cells holding
    dozens of others, so proving that cost more (14 s) than the lookups it saved, and the four pose points rarely
    share a triangle.
- **The load by part** (#244, idle machine, `window.loadTimes` / `window.worldTimes`, 5 loads each, 2026-11-05):
  line 17 38.9 s on main 14b71c4 (20.8 s on 2026-10-23, `docs/history/PERF-ANALYSIS.md`), 28.0 s after #244.
  What grew since 10-23 is the part "tracks + tunnel roads" (1.6 -> 11.6 s): the street flush to the rails
  (`flushDtm`, 8 s before #244: `route.nearest` asked about 4 times per vertex, a vertex being listed once per
  triangle around it) and the crossings' split with a full rebuild of the survey index (2.2 s). Not done,
  measured: lowering the terrain once per survey vertex instead of per triangle corner is not exact (the 32-bit
  heights leave a remainder that the repeated calls take off).
- **What the layered ground costs** (#244, 2026-11-05, lines 17 / 22): of the fine terrain's 2 m samples,
  92-94 % within 10 m of a track and 61-78 % at 10-120 m lie under the survey's ground-level areas, lowered
  0.25 m and drawn hidden (line 17 draws ~4.4 M fine triangles). Where it is visible, 2 m against IPR's 1 m
  raster is off by 1.4-2.4 cm on average; the 99th percentile is 36-73 cm within 10 m of the tracks (walls,
  cutting edges) and ~20 cm further out.

  What is left is the number of calls, and the simulation decides that: fewer pose lookups (a car's pitch and roll
  only when it moves a metre) would change the counts, so it is a decision for the traffic work, not a speed-up.
- **Rails under the ground** (`tools/lint.js` `buriedRails`, in `--checks canted`, #548): every 2 m of every drawn
  track, each rail head against the surfaces over it. Before #548: 372-837 places per line, 295-741 of them the
  survey; after: 86-133, mostly another track's bed between a switch's rails (1-5 cm) and OSM road ribbons.
  Its trough measure (the ground 1 m past a bed's edge lower than the edge and the ground 4 m out) is not
  calibrated: its deepest places are real ditches and cuttings (`reports/review/bed-troughs-N.json`).
- **`DownRays` and long slivers:** indexed by its bounding box, a survey sliver lands in thousands of 4 m cells, and
  sampling every drawn track ran for 30 minutes on line 17. A triangle over more than four cells goes only into
  the cells it overlaps (`triInRect`); two indexes of line 17's survey and terrain ran the page out of memory.
- **Probes and screenshots:** `shot.py --view review` colours the surfaces by class and hides the track styles, so
  appearance is judged in `chase` or `cab`. Platforms, stop signs and shelters are added to the scene, not to the
  world group (`window.world`): a probe that walks only the world misses them.

## Czech tram terms

Used in `README.md` and the game's Czech strings (`src/i18n.js`). The user's answers on #330 (2026-11-06), checked against
D 1/2, the exam sets and the training manual (docs/research/prazsketramvaje/README.md lists them):

| term | means | source |
|---|---|---|
| *rozjezdová výhybka*, pojížděná **proti hrotům** | a facing switch | the user; D 1/2 § 2.17 |
| *sjezdová výhybka*, pojížděná **po hrotech** | a trailing switch | D 1/2 § 2.18 |
| *kolejová splítka* | interlaced track | the user; D 1/2 § 2.19 |
| *stavěcí klíč* | the switch iron | the user, to match D 1/2 |
| *zajišťovací brzda*, *zabrzdit / odbrzdit* | the shoe brake holding a standing car; the pedal's position is *zaparkováno* in D 1/2 and the manual; ČKD's *stanicování* is in neither | the user; exam sets |
| *výběh* | coasting; the manual also *setrvačnost* | the user; manual p. 4 |
| *našlápnutí* | pressing the drive pedal from 0 | the user, 2026-11-07 ("in the real world I think that's what called našlápnutí") |
| *spoj* | a trip, which can change its number along the route and at a terminus | the user |
| *trolej*; *trolejové vedení* | the contact wire; the wire with its span wires, rosettes, bracket arms and poles | the user |
| *průjezdný průřez* | the clearance profile | the user; D 1/2 |
| *stanoviště řidiče*, *salón*, *kalorifer* | cab, saloon, cab heater | the user, to match D 1/2; manual p. 8 |
| *sběrač*, *zvonec*, *panel řidiče* | pantograph, bell, driver's panel; the 2009 manual alone says *pantograf* and *zvonek* | D 1/2, exam sets |

## Environment (Windows dev machines)

- Python `-I` ignores `PYTHONIOENCODING`: scripts call `sys.stdout.reconfigure(encoding="utf-8")`.
- Shell heredocs with quotes or backticks break: write scripts to a file.
- ES modules are cached hard: the dev server sends `no-store`; import tools with `?v=` + `Date.now()`.
- A full listen backlog refuses connections on Windows (Linux queues them). Python's HTTP server
  defaults to 5, which several pages loading their ~20 modules at once overflow: every page hung on
  "Loading the 3D engine" (`ERR_CONNECTION_REFUSED`). `tools/serve.py` sets 128; a `headless.py --jobs N
  --url` server needs the same.
- Browser script calls time out at 45 s; a hidden pane throttles `requestAnimationFrame`, so step the
  simulation in JS (`window.headless`) rather than waiting in real time.
- Memory: the whole line is built at load (no streaming).
- The `gh` CLI lives in `C:\Program Files\GitHub CLI` (not always on the Bash PATH).
- numpy's OpenBLAS starts a thread per core in every process. Several processes side by side (a rebuild's
  steps, two jobs at once) then fight over the cores: an ADMM-sized inverse and 300 products (n 1200) took
  5.1 s with the default 24 threads beside a rebuild, 0.14 s with one and 0.08 s with four (#511). Alone,
  4 threads and 24 run about as fast. The thread count changes BLAS results in their last bits (sums split
  differently); the line heights came out byte-identical at 4 and at 24. `tools/rebuild.py` sets
  `OPENBLAS_NUM_THREADS` per step.
- numpy has no banded or triangular solver; SciPy's LAPACK wrappers do: `scipy.linalg.lapack.dpbtrf` factors a
  symmetric positive definite band matrix (upper storage, `ab[u+i-j, j] = A[i, j]`) and `dpbtrs` solves with the
  factor, a 1-d right-hand side included. On the vertical profile's pentadiagonal system (n 3303) a solve took 50 us
  against 1.66 ms for a product with the dense inverse (4 BLAS threads), the factor 0.3 ms against the inverse's 0.87
  s; the answers 2.6e-12 apart, the residual smaller; the heights byte-identical (#516).
- A warm start is not a free speed-up for an iterative solve whose results feed one another: ADMM started from where
  the same solve ended last time stops at another point within its tolerance, and the rounds of meeting half way (one
  chain's heights are another's pins) then ended after 4 rounds instead of 6 and moved one junction's heights by up to
  16 mm (#516).
- Python reuses a module's bytecode while the source keeps its size and the second of its date: a file
  rewritten within the same second at the same size runs the old code (a test that edits a module must
  change its size).
- `np.hypot` and `math.hypot` differ in the last bit in ~17 % of pairs (2 000 000 random pairs, #517), and so does
  `np.sqrt(x*x + y*y)`; numpy's `+ - * /` and Python's floats agree to the bit. A loop moved to numpy keeps its
  results only where it keeps `math.hypot` (`tools/track_curve.py` `misses`: numpy picks, `math.hypot` measures).
  shapely's array functions (`distance`, `line_locate_point`, `line_interpolate_point`, `buffer`, an `STRtree`
  query of many geometries, which lists each one's hits in the order a query of it alone gives) run the same GEOS
  operations as its scalar methods: the same bits.
- `os.replace` onto a file another handle holds open fails on Windows (`PermissionError`, WinError 5), and
  so does opening a file while it is being replaced; POSIX lets both through. Python's `open` does not share
  delete access. Two threads replacing one file at once, or one replacing it while a process reads it,
  stopped a parallel rebuild (#521). A file several threads or processes write needs one writer at a
  time and a retry for the readers (`tools/stepcache.py` `_waiting`).
- A spawned process pool (Windows has no fork) pickles its initializer's arguments for each worker, one after another
  in the parent: the heights' staging gave 12 workers 115 MB that took 2.7 s each to pickle, and its pool came out no
  faster than one process (#516). `tools/sysinfo.py` `pool` pickles them once into a file each worker loads.
- Python's `wave` refuses IEEE float WAVs (format 3, what the user's recorder writes: "unknown format: 3"). Chromium
  decodes them (`decodeAudioData`) and encodes Opus with WebCodecs' `AudioEncoder`, which exists in a secure context
  only (a page on `http://localhost` is one; `about:blank` has no `AudioEncoder`). It gives raw 20 ms packets and an
  `OpusHead` (pre-skip 312) as `decoderConfig.description`; the Ogg pages are ours (`tools/sound_encode.py`). Chromium's
  `decodeAudioData` applies Ogg Opus's pre-skip and end granule: the shipped pack's five files decode to their WAVs'
  length to the sample, with no shift (#636). The same input encodes to the same bytes on this machine.
- lameenc (LAME 3.100) writes MP3 frames without LAME's info frame: Chromium decodes them whole, the sound starting
  1,105 samples late (LAME's encoder delay of 576 and the decoder's 529) and padded at the end to a whole frame. With
  an info frame before them holding the delay (576) and the padding (frames × 1152 − 576 − the master's samples),
  Chromium's `decodeAudioData` trims both: the shipped pack's five MP3s decode to their WAVs' length to the sample,
  with no shift (#636; `tools/sound_encode.py` `lame_info`). Playwright's Firefox 157 decodes them, and the Ogg Opus
  files, to the WAVs' length to the sample as well.
- Playwright's WebKit on Windows (27.2) has no Web Audio (`AudioContext` and `OfflineAudioContext` undefined) and no
  Ogg Opus (`canPlayType` empty; WAV and MP3 "probably"): it cannot play the game's sounds, and it says nothing of
  Safari's own decoders, which are Apple's (#636).
- The Claude desktop app is a packaged (MSIX) Windows app. Playwright's Firefox and WebKit installed from one of its
  sessions landed in the package's private copy of `%LOCALAPPDATA%`
  (`AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\ms-playwright\`), which only the app's processes
  see. Firefox then fails to start ("spawn UNKNOWN"; Windows: "side-by-side configuration is incorrect", the
  dependent assembly `mozglue` not found): Windows looks for `mozglue` in the real folder. Chromium, in the real folder,
  runs. Playwright's browsers are installed from a terminal outside the app
  (`python -m playwright install firefox webkit`); pip's user site packages, written from a session, are in the real
  `AppData\Roaming` (2026-11-17, #636).

## The test host

Measured 2026-11-06 with Firefox 159 on the host itself (#275): nginx in front of Apache, PHP as FastCGI.

- **What it compresses by itself.** A request that accepts brotli gets JSON, scripts and HTML as brotli at about quality 6 (`main.js` 16,347 B against 16,352 B locally at 6), and `.bin` not at all. A request without brotli gets scripts and HTML as gzip at level 1 (`main.js` 19,350 B, the size of local `gzip -1`), and JSON and `.bin` not at all. The `mod_deflate` lines our `.htaccess` used to have changed nothing, and line 17's two `.bin` files went out whole: 10.8 MB of the 15.9 MB a game load transferred.
- **`.br` means Breton there.** A file named `x.json.br` comes with `Content-Language: br`, and neither `RemoveLanguage .br` nor `Header unset Content-Language` takes it off. `x.json.brotli` with `AddEncoding br .brotli` comes clean, also with no plain file beside it and from subfolders.
- **A mangled page after changing Firefox's encodings.** With `network.http.accept-encoding.secure` set to leave out `br`, Firefox revalidates a page it cached as brotli, gets a 304 and shows the raw bytes, since it no longer decodes what it no longer accepts. Ctrl+Shift+R shows the page. The host's answer is right, and a visitor does not change this setting between visits.
