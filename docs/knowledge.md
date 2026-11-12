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
- **Two junctions lie on the ground under 500 m** (#358, 2026-11-08): Královka's loop arms and Malovanka, where the
  user's photos show the paving following the slope. Held at 500 m, Malovanka's curves lay up to 40 cm off the 1 m lidar
  and its junction still needed 355 m (meeting points metres apart). The archive put Královka's arms 15-78 cm above the
  ground: its 12 % ground step had been dropped as steeper than any track. The tracks follow the lidar in the
  user's areas, no tighter than 250 m: unlimited, Malovanka read 131 m, a 2.4 cm lidar bump over 5 m
  (`data/truth.json` radiusAnswers with `area`).
- **The heights read IPR's 1 m raster, the game draws a 2 m grid of it** (`tools/fine_terrain.py` STEP; the 1 m mesh
  is #276): at Královka and Malovanka the 2 m grid lies within mean 0.6-0.9 cm, max 6.4 cm of the raster at the tracks.
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

### Terrain and the street survey (IPR, ČÚZK, ZPS)

- **Sources per layer** ([decision](decisions/2026-10-30-source-per-layer.md)): the order and dates are in
  `tools/sources.py`; every built file says per list where its features came from (`provenance`, `fb`).
- **IPR 1 m terrain** (`tools/ipr_dtm.py`): bare earth from the 2023 lidar, one 2 GB BigTIFF (tiled,
  LZW). Its cell centres sit 0.72 m / 0.61 m off the S-JTSK metre grid (sampled bilinear, never copied);
  it states no datum, and measures Bpv (+0.016 m over the ZPS street lines on line 17, ±0.03 m against
  DMR 5G per line; a Bpv / EVRF2007 mix-up is 0.13 m). The fine 2 m blocks within 120 m of the tracks
  come from it (`tools/fine_terrain.py`, `?nofine`). It has no covers over passages (underpasses,
  culverts: bare earth shows the passage). Near OSM passages, the lines' fine blocks take DMR 5G, which kept the covers.
  The city mesh keeps IPR (#428): a street or track over a passage is a deck in #276's partition. The rule also took
  roofs, garages, building interiors and proposed tunnels (decision record 2026-11-05, "No passages rule").
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
  10 m grid of a line, and the fine blocks' fallback where IPR has no data.
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
  `tools/zps_outline.py` moves those where IPR runs calm, on road, tram and sidewalk: over 0.3 m off, 1,473-4,061 such
  vertices per line → 181-491. 79 % of straight street outline lies in gaps over 5 m between vertices (line 22). A
  platform's edge shared with the tram area is its top (#21), not the tram's foot: its vertices stay out of the rule.
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
    envelope codes 0–4: curved types would need work.
  - CRS: everything is EPSG:5514 metres, M = 0, and no tool reprojects or rejects another CRS.
  - Per district (OPL polygon / KR line / KR point layers): Praha 1 50/28/61, 2 43/26/52, 4 49/28/60,
    7 45/28/56, 8 53/29/63, 10 49/27/62, 12 50/29/58, 17 43/26/47.
  - Versions: the GPKG `user_version` 10301 is GeoPackage 1.3.1, not the JVF version. The GPKG ZIPs
    carry no JVF header; the matching Praha 2 JVF packages say `VerzeJVFDTM=1.4.3`,
    `DatumZapisu=2026-10-01` (OPL SHA-256 `ba86e8f6…`, KR `3384bf02…`; not in the snapshot).

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
  Once it let go it coasts down 1 m/s under the speed it holds before pressing again (0.12 of the speed in slow streets, 0.35 m/s on a
  climb). A turn the drive pedal must make before a point is a limit of its own, from which the 1.5 s without the brake still leaves the
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
- **Driving to the timetable** (#242): the time in hand to the next stop sets how it drives. That is the stop's timetable
  time, less now, less 1.3 times the quickest run there at the limits, less a 15 s dwell.
  - **Up to 10 s in hand it catches up.** The target is 0.2 m/s under the limit, and brake step 1 holds down a descent only to
    0.6 m/s under. At a 15 km/h limit, 0.4 and 1 m/s held it at 10-14.5 km/h, where the drivers of two line 23 rides held 14-16
    down Chotkova (#431). Within reach of a turn's contact the target keeps 0.4: 0.2 under Anděl's 20 km/h put the accelerator
    at 31 coasting, over the switch button's 30.
  - **Over the next 30 s it grows milder:** curves as at 0.8 m/s², 0.4 under the limit, the 1 m/s hold, the target up to
    10 km/h under, coasting up to twice as long, braking a quarter softer (the user, 2026-11-10: "if there's enough time the
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
- Memory: the whole line is built at load (no streaming); fine terrain adds ~0.15–0.2 GB.
- The `gh` CLI lives in `C:\Program Files\GitHub CLI` (not always on the Bash PATH).
- numpy's OpenBLAS starts a thread per core in every process. Several processes side by side (a rebuild's
  steps, two jobs at once) then fight over the cores: an ADMM-sized inverse and 300 products (n 1200) took
  5.1 s with the default 24 threads beside a rebuild, 0.14 s with one and 0.08 s with four (#511). Alone,
  4 threads and 24 run about as fast. The thread count changes BLAS results in their last bits (sums split
  differently); the line heights came out byte-identical at 4 and at 24. `tools/rebuild.py` sets
  `OPENBLAS_NUM_THREADS` per step.
- Python reuses a module's bytecode while the source keeps its size and the second of its date: a file
  rewritten within the same second at the same size runs the old code (a test that edits a module must
  change its size).

## The test host

Measured 2026-11-06 with Firefox 159 on the host itself (#275): nginx in front of Apache, PHP as FastCGI.

- **What it compresses by itself.** A request that accepts brotli gets JSON, scripts and HTML as brotli at about quality 6 (`main.js` 16,347 B against 16,352 B locally at 6), and `.bin` not at all. A request without brotli gets scripts and HTML as gzip at level 1 (`main.js` 19,350 B, the size of local `gzip -1`), and JSON and `.bin` not at all. The `mod_deflate` lines our `.htaccess` used to have changed nothing, and line 17's two `.bin` files went out whole: 10.8 MB of the 15.9 MB a game load transferred.
- **`.br` means Breton there.** A file named `x.json.br` comes with `Content-Language: br`, and neither `RemoveLanguage .br` nor `Header unset Content-Language` takes it off. `x.json.brotli` with `AddEncoding br .brotli` comes clean, also with no plain file beside it and from subfolders.
- **A mangled page after changing Firefox's encodings.** With `network.http.accept-encoding.secure` set to leave out `br`, Firefox revalidates a page it cached as brotli, gets a 304 and shows the raw bytes, since it no longer decodes what it no longer accepts. Ctrl+Shift+R shows the page. The host's answer is right, and a visitor does not change this setting between visits.
