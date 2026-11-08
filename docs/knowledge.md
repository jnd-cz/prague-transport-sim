# Knowledge: data quirks, conventions, why the heuristics exist

What sessions learned and later work needs. Kept current and short; the full logs are in
[history/](history/) (HANDOFF.md §n, REMOTE-CHANGES.md §n). Tasks are GitHub issues, not here.

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

- **OSM** (local extract only, [decision](decisions/2026-10-23-local-osm-extract.md)): route relations
  PTv2; track ways are merged into chains split only at junctions and bridge ends (no smoothing kinks).
  Tunnels from `tunnel`, `covered=yes`, negative `layer`. OSM splits tunnels and bridges into many ways:
  heights must run along the whole chain (`chainTunnels`), or inner ends take the hill top or the river.
  Interlaced track is tagged `railway:interlaced=yes` (Letenská).
- **Switch detection** (facing only): a route node with an extra track neighbour heading forward; a
  neighbour on a track passing straight through is a diamond crossing (line 22: 16 of 33 "switches").
- **PID GTFS**, service date fixed at 2026-10-21. Line 22 needs `--headsign "Zahradní Město"`. Line 9 is
  built as a 9 → 10 run. Line 37 (a substitute line) has no OSM relation: built from its GTFS shapes,
  which run between the two tracks in places; the matcher prefers the right-hand track (regular
  service always uses it, `data/truth.json`).
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
- **Where only the archive has a height, the 2023 terrain checks it** (#190): where a ZPS survey confirms
  the archive, the two differ by more than 1 m on 13 of 45,577 samples (0.03 %); without a survey 848 samples
  do (Malovanka 83 m, the Libeň bridge's dips to the streets, Troja's old alignment). Numeric DI agreeing with
  the archive 7 m under the terrain is a structure the terrain cannot see, not an error
  ([height fallback](decisions/2026-10-30-track-height-fallback.md)).
- **OSM maps a tram under reconstruction as `railway=disused` + `disused:railway=tram`** (Libeňský most,
  `bridge=yes`, 2026-11 extract) while the 2026 DI keeps the track; tools that select `railway=tram` miss it.
  The DI's own track there is new (inserted 2025-01-30, 24 m pieces, Z = 0).
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
- **The robust smoother runs away where its radius is wrong** (#197): `vertical_profile` stops pulling towards
  points it misses by more than 0.23 m (Tukey). Where the design radius cannot follow a real sag (Malostranská,
  ~300 m, the archive and the terrain agreeing to 2 cm), it drops the whole stretch and runs 1–3 m under the data,
  not 0.3 m. Points at weight 0 do not fix a curve either: across a 40 m hold it sagged 5 cm under the straight
  grade (`tools/line_heights.py` starts held points on that line at weight 0.001).
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
- **OSM joins a crossing and a switch in one node** (Strossmayerovo náměstí, Palackého náměstí: nodes of 5-6
  edges) where DI has them 0.4-0.5 m apart; a node placed nearest all its tracks lies off each of them.
- **The archive draws Dvorce's old connection** (#204): DI (2026-09-30) and the archive (2008-2024) have
  no track onto the new Dvorecký most (opened 04/2026: "No data is related to new Dvorecký most put in
  service in 04/2026", the user, track sources review, 2026-11-03); where OSM's new edges come within 2 m of
  the archive's old track it takes them, as a zigzag with 20° breaks.
- **Every DTM record states its accuracy class** (#204; `data/truth.json` `sourceAccuracy`, the classes of
  vyhláška 393/2020 Sb.): DI's tram axes are class 3 (0.14 m in plan, 0.12 m in height) but 7 of 10,371 in
  class 2; ZPS lines are class 3 in plan (3.2 M) or 4 (0.7 M) and **class 5 in height** (3.2 M lines, 0.35 m),
  class 3 for 0.7 M. The archive states none; DMR 5G guarantees 0.18 m (0.30 m under dense vegetation); IPR's
  1 m terrain and the orthophoto state nothing.
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
- **OSM draws interlaced track as one way** (#204): a `railway=switch` node at the tip (often with its number,
  `ref` 111 at Čechův most), one way both routes share, and the split where the tracks part at a
  `railway=railway_crossing` node noted "rozjezdová/sjezdová splítka" (diverging/converging interlace). Where DI
  draws the tongue, its tip lies 0.4-3.3 m from OSM's switch (Dejvice, Chotkova, Čechovo náměstí); where DI starts
  the branch 13 cm off at a record joint, OSM's switch lies a tongue (8.0-8.8 m) before it. Malostranské náměstí
  is a gauntlet with no switch: crossing nodes at both ends, the two directions interlaced for 45 m.
- **Interlaced tracks' record ends lie within JOIN of each other** (#368): 10-15 cm apart, where DI splits both tracks
  at the same places (Nádraží Libeň: every 6-27 m over 39 m) or starts or ends the branch beside a record joint of the
  through track (Ke Stírce 11.7 cm, Čechův most 12 cm with the through track's joint 0.6 m apart). Grouped as one place,
  the node lay on the branch and the line stepped 10-12 cm through it, or the through track's records were dropped as
  copies of the branch's (two records between the same two places, within 20 cm) and line 37 ran the branch for 35 m:
  the user's "sideways jolts" (2026-11-07). 14 such places in the network, 6 on the lines. `di_tracks._meetings`: an end
  whose track goes on in line does not meet an end beside that track, nor two joints side by side.
- **Two junctions lie on the ground under 500 m** (#358, 2026-11-08): Královka's loop arms and Malovanka, where the
  user's photos show the paving following the slope. Held at 500 m, Malovanka's curves lay up to 40 cm off the 1 m lidar
  and its junction still needed 355 m (meeting points metres apart). The archive put Královka's arms 15-78 cm above the
  ground: its 12 % ground step had been dropped as steeper than any track. The tracks follow the lidar in the
  user's areas, no tighter than 250 m: unlimited, Malovanka read 131 m, a 2.4 cm lidar bump over 5 m
  (`data/truth.json` radiusAnswers with `area`).
- **The heights read IPR's 1 m raster, the game draws a 2 m grid of it** (`tools/fine_terrain.py` STEP; the 1 m mesh
  is #276): at Královka and Malovanka the 2 m grid lies within mean 0.6-0.9 cm, max 6.4 cm of the raster at the tracks.
- **PID GTFS shapes are OSM's**: line 17's shapes run on the double track's midline and match OSM's midline
  to p50 0.04 m (#20); they cannot judge OSM against DI.
- **ZPS track areas on bridges are not rail height by themselves** (#184): on the queue's bridges level-0
  tram areas lie p10 −1.53 / median −0.26 / p90 +0.11 m from the smooth archive. At Černý kůň they and the
  level-1 deck meet the archive within 0.2 m on both sides and carry on across the dip (198.9 → 198.2 m).
- **ZPS track areas on the Modřany embankment lie ~2 m below the archive and the lidar ground** (s 408:
  survey 198.6, archive 200.8, lidar 201.0 m; flagged `track_zps_level_unverified`), which is why the
  drawn rail there is low and wavy. The level-1 tram area over the Modřany underpass carries the
  ground's heights (194.9–195.8 m): the survey has the deck's outline but not its height.
- **Sources per layer** ([decision](decisions/2026-10-30-source-per-layer.md)): the order and dates are in
  `tools/sources.py`; every built file says per list where its features came from (`provenance`, `fb`).
- **IPR 1 m terrain** (`tools/ipr_dtm.py`): bare earth from the 2023 lidar, one 2 GB BigTIFF (tiled,
  LZW). Its cell centres sit 0.72 m / 0.61 m off the S-JTSK metre grid (sampled bilinear, never copied);
  it states no datum, and measures Bpv (+0.016 m over the ZPS street lines on line 17, ±0.03 m against
  DMR 5G per line; a Bpv / EVRF2007 mix-up is 0.13 m). The fine 2 m blocks within 120 m of the tracks
  come from it (`tools/fine_terrain.py`, `?nofine`). It has no covers over passages (underpasses,
  culverts: bare earth shows the passage); near OSM passages DMR 5G, which kept them, takes over.
- **ČÚZK DMR 5G**: bare-earth lidar (embankments over underpasses are in it), 2 m TIN raster; the coarse
  10 m grid of a line, and the fine blocks' fallback where IPR has no data.
- **Prague DTM / ZPS survey** (street areas, kerbs, points): every district a line's 80 m corridor touches
  (`tools/dtm_packages.py` `DTM`, `--check` recomputes it from the OSM district boundaries). The hand-made
  lists before #125 covered under half of line 22 (no Praha 1 or 6) and missed line 17's Troja and Libuš,
  with Trojský most. Its vertices are far apart (big river triangles), so terrain is lowered vertex by vertex under surveyed areas.
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
- **Track height checks depend on construction** (#106): paved embedded/panel/setts surfaces can
  describe rail level, including a dedicated raised paved strip. Open-track outlines can describe
  ditches or embankment edges; they neither supply rail Z nor veto the archive. A generic ZPS tram
  area does not identify its material, and the panel drawing default is not evidence of pavement.
  Railway-bridge surfaces can be above the tram and are excluded. Numeric DI calibration, the
  Koh-i-noor – Slavia green-surface sample sites, and the separate drawing/survey height meanings
  are recorded in [the height fallback decision](decisions/2026-10-30-track-height-fallback.md#calibration-and-review-response-2026-11-01).
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
- **OSM `maxheight`** under the route gives underpass clearances (`tools/clearances.py`; default 4.2 m
  car roads, 2.5 m footways), applied only where the track is already ≥ 2 m over the road.
- Tatra T3 figures (ČKD pamphlet, unverified): 16 t empty, 4 × 40 kW, ~39 kN, 1.8 m/s² service accel and
  brake, 5 m/s² emergency, 24 seated + 86 standing.
- T3s can meet anywhere in the Prague network, tight curves included (user, 2026-10-30): a tram/tram
  overlap between T3s is a geometry error (track spacing), not a place where they must not meet. A few
  tight places forbid KT8 and T3R.PLF from meeting; that matters once those models exist.
- Prague signals: 4 white lamps on a white plate (stop = outer two), call box with three orange LED bars,
  distant signal with a yellow "P"; switch indicator a red LED chevron on the span wire.

## Heuristics that stand in for missing data

Review these when realism matters; most move into the build in M2.
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
  Geometric side-surface classes have separate counts and places for rebuild comparisons. Held
  patches go through `tools/crossing_review.py` into `reports/review/pedestrian-crossings.json`, opened
  with `?line=17&review=reports/review/pedestrian-crossings.json`; answers stay held until reviewed
  evidence supplies a place-based fact. Overlapping survey slab sides remain #166.
- **Vienna-type stops**: carriageway on the doors' side 2.2–3.4 m from the track along the stop (the
  tram bed is not a car lane); facts per stop and direction in `truth.json` `stopTypes`.
- **Bridges on the model deck**: on tagged spans with model samples, the model deck is fixed like a
  surveyed bed (floor and ceiling, ±3.3 m sideways search on our own bridges); not on surveyed beds.
- **Tunnel mouths**: chains < 60 m are open roads; longer ones get a portal with a 24 m throat, heights
  from the approach road, the terrain re-covered over it.
- **Trees** ≥ 3.2 m from a track, crowns ≥ 1.9 m; **LOD2 buildings** within 2.5 m of the route lifted to
  track + 6.3 m (passages like Letenská).
- **Speed limits** from curvature, posted OSM speeds and switches; stop zone −20…+12 m; adhesion dry
  0.30, rain 0.17, leaves 0.15; demand peaks 7–9:30 and 15:30–17:30.
- **Traffic**: cars wait at the track only while the tram's body is on the crossing or it is about to
  arrive (16 m / 4 s); AI trams ahead run at the limit, spawned 700–1300 m ahead, board 6–8 s when ours
  is within 300 m; oncoming trams stop at the far end of their own platform.
- **AI tram gridlocks** (#168): line 37 seed 4 at Balabenka closes an oncoming tram → car 307 →
  car 295 → car 297 → that tram cycle before ours arrives. The #154 recovery covered only a car
  immediately ahead of our tram. `Traffic._clearAiTramCycles` follows each vehicle's `waitFor`
  (the controlling stop reason) and fades one car after the same closed cycle stands for 30 s.
  Signal waits, boarding and moving vehicles end the chain. This is recovery for cars that cannot
  reverse out in the present model. `window.game.trafficCycles` records the removed car, cycle and
  reasons; the traffic check retains those events. `tools/bench/stuck.js` names both AI directions
  and the nearby junction cars, including their `why`, `seen` and actual wait chains.

## Checks and what they measure

- `tools/lint.js` (page with `?keepgeo`): consist at stops, signals in platforms (exempts island-tip
  poles marked at placement and heads hung over the track), trees in buildings, bridges, invented walls, tram
  envelope, grade separation, railSupport, verticalCurves, terrainOverSurvey, streetWaviness,
  `deckClip` (ray down against drawn buildings and bridges), `underpassClearance`, lanes, street bot,
  `trackRadius` (over 5 m through the build's points, under 18 m; 18-20 m listed as exceptions) and `trackJoins`
  (through tracks breaking over 1° where chains meet, diverging start angles listed; direction from the parabola
  through the first three drawn points).
- `lint({ traffic: true })` / `tools/traffic_lint.js`: slide, jump, overlap, walker hits, red runs;
  averages seeds 22, 7, 1234; a run that does not finish is a jam (follow `car.seen.car`).
- `tools/bench/`: u3 (signals, junctions, collisions), redruns, walkers, heads; `batch.html` runs them.
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

## The test host

Measured 2026-11-06 with Firefox 159 on the host itself (#275): nginx in front of Apache, PHP as FastCGI.

- **What it compresses by itself.** A request that accepts brotli gets JSON, scripts and HTML as brotli at about quality 6 (`main.js` 16,347 B against 16,352 B locally at 6), and `.bin` not at all. A request without brotli gets scripts and HTML as gzip at level 1 (`main.js` 19,350 B, the size of local `gzip -1`), and JSON and `.bin` not at all. The `mod_deflate` lines our `.htaccess` used to have changed nothing, and line 17's two `.bin` files went out whole: 10.8 MB of the 15.9 MB a game load transferred.
- **`.br` means Breton there.** A file named `x.json.br` comes with `Content-Language: br`, and neither `RemoveLanguage .br` nor `Header unset Content-Language` takes it off. `x.json.brotli` with `AddEncoding br .brotli` comes clean, also with no plain file beside it and from subfolders.
- **A mangled page after changing Firefox's encodings.** With `network.http.accept-encoding.secure` set to leave out `br`, Firefox revalidates a page it cached as brotli, gets a 304 and shows the raw bytes, since it no longer decodes what it no longer accepts. Ctrl+Shift+R shows the page. The host's answer is right, and a visitor does not change this setting between visits.
