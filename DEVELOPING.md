# Developing

The game for players: [README.md](README.md) (Czech), [README.en.md](README.en.md) (English).

Project docs: [ROADMAP.md](ROADMAP.md) (milestones; tasks are GitHub issues), [AGENTS.md](AGENTS.md)
(working rules for agents and contributors), [docs/knowledge.md](docs/knowledge.md),
[docs/architecture.md](docs/architecture.md), [docs/decisions/](docs/decisions/).

## Set up

The game data (`data/`) and the raw sources (`raw/`) are not in git: a fresh clone gets them from the
data store, see **[DATA.md](DATA.md)** (one-time SSH setup, then):

```bash
python -I tools/snapshot.py data-fetch     # data/ to play and tune the game (~110 MB)
python -I tools/snapshot.py fetch          # raw/ to build the world (~4.3 GB, the pinned source snapshot)
```

## Rebuild the line data

Every build reads the pinned source snapshot in `raw/` (DATA.md); OSM comes from its local extract
(`raw/osm/praha.osm.pbf`, pyosmium, so the OSM tools run with `-P -E`). The Overpass API is not used.
All lines share one frame: S-JTSK metres from the Marian column (`tools/geo.py`).

The whole chain for a line (logs in `reports/rebuild/`): `build_line` first, then its independent steps
side by side; `--parallel` also builds the lines side by side, as many as free memory holds (~2.5 GB each).
The OSM extract is read once per build (~1 min), and a line takes ~2-4 min:

```bash
python -P -E tools/rebuild.py 17 22          # or all lines: python -P -E tools/rebuild.py --parallel
```

The single steps:

```bash
python -P -E tools/build_line.py --line 37         # no OSM route relation: from its GTFS shapes
python -P -E tools/build_line.py --line 22 --headsign "Zahradní Město"
python -P -E tools/build_line.py --line 23         # any Prague tram line
python -P -E tools/build_line.py --line 17 --refresh  # recompute the OSM answers cached in raw/line17/
python -P -E tools/build_line.py --line 9 --then 10   # a vehicle run: 9, continuing as 10 at the terminus
python -P -E tools/line_heights.py 17 22           # top of rail (#197), after the lines' survey sidecars
```

`rebuild.py` ends with `line_heights.py` for all the lines it built (~6 min: it stages the network's heights
with the user's answers and assembles one profile per DI track, docs/decisions/2026-11-02-vertical-profile.md);
`reports/line-heights.json` lists the stretches without a height, the junctions where the radius gave way and
the steps. `headless.py --checks heights` compares the game's track with the staged heights.
Where the data does not fit the design radius within 10 cm (15 cm in a junction), the radius gives way down to the floor
of 500 m (`data/truth.json` trackGeometry `vertical-radius-min`, #358) and no further: there the band gives way and the
curve holds 500 m as near the data as it can. Only rails that would not meet at a junction take a tighter curve.
`?line=23&review=reports/review/track-radius.json` shows those places: each answer's preview is its curve;
`hold the radius` recorded in `data/truth.json` (`trackHeights.radiusAnswers`) keeps the radius at that place, with
`"outliers": "drop"` (the note "Discard the outliers") the points it misses the band at are dropped, worst first, and
it is fitted to the rest; `follow the data` given since the floor's date lets it go below 500 m there (one given before
gives way only to the floor). An answered place leaves the list; `reports/line-heights.json` lists the dropped points.
`python -P -E tools/stepped_review.py reports/headless` (after `headless.py --checks lint`) writes
`reports/review/stepped-curves.json`: every curve the `steppedCurves` check flags, with its step's size (the corner over
5 m beyond the curve's own, and how far the track leaves the smooth curve of its flanks); `smooth into one curve`
(`trackSources.steppedAnswers`, read by `tools/di_network.py`) frees DI's vertices within 10 m of the place.

After a rebuild: `python -I tools/snapshot.py data-publish --note "…"` and commit `data/MANIFEST.json`.

With `--then`, the route is not taken from the OSM relations (they describe the regular route, not
diversions) but from the PID GTFS shapes of the two trips, matched onto the whole Prague OSM tram
network; trips are paired only when the next trip in the GTFS vehicle block starts at the same terminus
on the selected pattern. Unmatched or ambiguous trips are reported by the build. The current line 9 is
such a run: Sídliště Řepy → Nákladové nádraží Žižkov as 9, back to Řepy via Vinohradská as 10
(track repairs, autumn 2026).
Stop platforms come from OSM (`public_transport=platform`) for all lines.

The script finds the line's OSM route relations by `ref`, takes the GTFS direction-0 headsign
with the most trips on the service date (override with `--headsign`), checks that the GTFS stops
lie on the chosen OSM route, and writes `data/lineN.json` plus the menu index `data/lines.json`.
The OSM answers are cached in `raw/` (line 22), `raw/runN-M/` (a run such as 9 → 10) and `raw/lineN/`
(other lines), each marked with a key of the extract, the query and the code that answers it
(`tools/osm_local.py`, `tools/geo.py`): a new snapshot's extract or an edit to either file recomputes
them. A line without an OSM route
relation (a substitute line such as 37) is built like a run, from its GTFS shapes (`--gtfs` forces
it). Built lines: 9, 17, 22, 23, 37.

The steps after `build_line` (`tools/rebuild.py` runs them in this order; its docstring is the one
list). Each also runs alone, as `python -P -E tools/<step>.py --line N` (the line-17 tools take the line
as a plain argument, `dtm` also the district packages: `rebuild.py` shows the exact arguments; `-P -E`:
pyosmium, pyproj, shapely, numpy, Pillow and brotli live in the user site packages):

| step | writes | what |
|---|---|---|
| `platforms` | `lineN.json` | tram platforms of both directions: PID GTFS positions, names and lines, OSM shapes where mapped (`--fetch` re-reads them from the snapshot's extract) |
| `osm_speeds` | `lineN.json` | posted speeds and dedicated track: the speed limits and banked curves |
| `clearances` | `lineN.json` | roads passing under the route with their OSM `maxheight` (the profile keeps the track over them) |
| `dtm_points` | `lineN.dtmpoints.json` | street furniture from the archived technical map |
| `osm_signals` | `lineN.signals.json` | line 17 only, until the placement rules (#22): OSM traffic signals |
| `osm_validate` | `lineN.validate.json` | every line: a check of the line against OSM |
| `geoportal` | `lineN.geo.json`, `lineN.bld.bin` | 110 m either side of the route: IPR LOD2 buildings and Mosty 3D bridges (I3S), retaining walls with heights, the city tree register (`--trees-only`); without it the game extrudes OSM footprints |
| `fine_terrain` | `lineN.fine.json`, `.fine.bin` | terrain on a 2 m grid in 128 m blocks within 120 m of either track (`?nofine` loads without it) |
| `dtm` → `zps_source` | `lineN.dtm.json`, `lineN.zps.json` | the surveyed streets (DTM ZPS) with their kerbs put back (`tools/kerbs.py`, #21), then the survey's own lines for review mode; the districts per line are `DTM` in `tools/dtm_packages.py`, lines held from it are `HOLD` |

Underpasses and tunnels on the route (OSM `tunnel`/`covered`/negative `layer`) are spanned in the track
profile. Where each source comes from, how it is refreshed (the GTFS service date, the survey's district
packages, DI, the terrain) and its licence: [DATA.md](DATA.md) and [NOTICE.md](NOTICE.md).

## Deploy

The game is static files: `index.html`, `src/`, `assets/`, `data/`. Three.js comes from jsDelivr and
the outdoor temperature from Open-Meteo, both fetched by the browser. `python tools/make_dist.py`
packs them into `dist/tatra-t3-prague.zip`; unzip it into any web server directory. Enable gzip or
brotli for `.json` and `.bin` on the server (~3x smaller downloads). The detailed tram model is
CC BY-NC 4.0: fine for a non-commercial public test, with its attribution shown in the menu.

To a web host over FTPS (#131): `python -P -E tools/deploy.py` uploads the same files from a clean commit
whose data matches the manifest:
- only the changed files go up (the server keeps `.deploy-manifest.json`), and removed ones are deleted;
- the data heavy packs (`.json`, `.bin`, `.glb`, `.gltf` in `data/` and `assets/`) go up only compressed, as `<name>.brotli` at quality 11 (#275), and the `.htaccess` hands that file to every request for `<name>`. The rest stays plain, for the host to compress on the fly. The site was 114.6 MB plain and is 31.5 MB this way. Browsers accept brotli only over HTTPS, so the host must redirect HTTP (Plesk: Permanent SEO-safe 301 redirect from HTTP to HTTPS);
- it adds `version.json`, shown in the menu's credits, and that `.htaccess`;
- `--dry-run` lists the changes, `--reports` adds `reports/headless/*.json` for review mode, and a rollback is a deploy from the older commit.

The host, the FTP user and the folder go in `deploy.local.json` (git-ignored; format at the top of the tool). The password is asked for each time, or read from `TRAM_DEPLOY_PASSWORD` or `~/.netrc`. The site's own protection is the host's: in Plesk, Password-Protected Directories on `/`. After each upload the tool checks that `version.json` answers 401 without a login.

Automatic (#131): `python -I tools/autodeploy.py` in a checkout kept for deploys (detached HEAD, with
`deploy.local.json`, as `../tg-deploy`) deploys `origin/main` when it moved since the last deploy:
checkout, `snapshot.py data-fetch`, `deploy.py`. `--install` registers a Windows scheduled task that runs
it every 10 minutes while you are logged on (`--uninstall` removes it). It needs the password in
`~/.netrc` (`machine <host> login <user> password <password>`); a failed deploy is retried after an
hour. Log: `reports/autodeploy.log`.

## Dev

**Headless checks from the command line** (Playwright, see DATA.md setup): the benches and lints below,
each in a fresh headless page, with pass / fail per run (exit code 1 on a failure) and the results in
`reports/headless/`:

```bash
python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
python -P -E tools/headless.py --lines 23 --checks traffic,lint --seeds 22,7,1234
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,lint --jobs 3
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks canted
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks crossing
```

`crossing` counts 20 m route sections where a drawn pedestrian surface is above a sampled rail head;
it also reports missing rail samples and the independently mapped evidence for survey adjustments.

`--jobs N` runs N pages at once, each in its own browser process (default: by cores and free memory,
up to ~4 GB a page for line 17). The runs are seeded per page, so the counts are the same as one after another.

The harness verifies its own server before launching a job. An occupied `--port` fails without using
or stopping the existing listener; use `--port 0` to allocate a free port atomically. `--url` explicitly
uses an already-running server.

Regression checks compare with main's baseline in the data store: the key counts of each run, with the code and data they were measured on. `--baseline` also keeps a local copy in `reports/baseline/`, ignored by git.

```bash
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --seeds 1 --compare
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --seeds 1 --baseline
```

`--compare` prints baseline → now per run (also in `reports/headless/compare.md`, for the PR) and marks
problem counts that rose (traffic counts beyond a 15 % + 5 noise band). It warns when the baseline was not
measured on main's code and data. `--baseline` stores the run as the new baseline; it needs the game,
the in-page checks and `data/MANIFEST.json` committed and `data/` matching the manifest.

For a combined GTFS run, independently check every logged pair and the built timetable against the
pinned GTFS, including eligible pairs omitted from both the log and timetable:

```bash
python -I tools/audit_run_timetable.py --line 9 --log reports/rebuild/line9.build_line.log
```

The audit takes the service date from the build log (`service date …`, `SERVICE_DATE` in
`tools/build_line.py`).

`tools/autopilot.js` drives the game headlessly to check the rules. In the browser console:

```js
const { autopilot } = await import('/tools/autopilot.js');
autopilot(0, 99, { obstacles: 'normal', weather: 'rain' });
```

**Lints** ([docs/knowledge.md](docs/knowledge.md)): each check counts one kind of problem over the whole line. With the dev server
(`tools/serve.py`, which saves the reports), the page loaded with **`?keepgeo`** (the game otherwise frees
the meshes' CPU copies after loading) and a shift started on the line:

```js
const { lint } = await import('/tools/lint.js?v=' + Date.now());
await lint();               // consist at every stop, signals in platforms, trees in buildings, bridges
await lint({ bot: true });  // + the street bot where DTM streets exist (about a minute)
await lint({ traffic: true }); // + the whole line driven headless with the real traffic (1–2 minutes)
```

The traffic run (`tools/traffic_lint.js`) starts a shift at the first stop and lets the autopilot drive
to the end with a fixed time step; the page's frame loop only draws meanwhile (`window.headless`).
Every 0.2 s it records every visible car, walker and tram and counts: cars or walkers moving sideways
(`slide`), teleporting (`jump`), vehicles intersecting (`overlap`, once per episode) and walkers inside
a vehicle (`walkerHit`), each with its cause where known (next road, lane beside the tram, …). It is
seeded and uses the first trip, autumn and dry weather, so a run on a **freshly loaded page** gives
the same counts every time (a second run in the same page differs slightly).

Reports go to `reports/lineN.json` (not in git). Regression checks use `tools/headless.py --compare`
(above), whose baseline follows main.

Mirror rendering cost (#79): `python -P -E tools/mirror_bench.py --line 17 --s 5064 --headed`.
Keep its game window in front until it closes: the report records the graphics backend, focus,
frame times and mirror geometry/update counts, alternating mirror off/on. Unfocused frame rates are
rejected. `tools/test_mirror.py` checks cadence and renderer state; `tools/test_mirror_game.py` captures
the real mirror at 1280×720, 3840×2160 and 390×844 in `reports/shots/mirror79/`.

**Compare a view or rebuilt data** (#158):

```bash
python -P -E tools/shot.py --line 17 --s 5064 --view cab --ref origin/main
python -P -E tools/shot.py --line 17 --s 5064 --view review --ref ../other-checkout
python -I tools/datadiff.py --line 17 dtm
python -I tools/datadiff.py --line 17 zps --at=-2489,-8331 --radius 5
python -I tools/datadiff.py --line 17 dtm --ref '5d6c427^'
```

`shot.py` writes individual PNGs, a labelled pair and camera/data hashes to `reports/shots/`.
Views: `cab` (default), `chase`, `review`. The tram is paused at `s`, traffic and HUD are hidden;
review uses `&at=` at that route point. Both sides use the current view's exact camera, so a changed
profile cannot move the comparison camera. It starts its own free-port servers, one view at a time.
The reference defaults to `origin/main`: a git revision is exported temporarily with its published
data from `TRAMDATA_CACHE`; a directory uses its working files. Neither checkout is modified.

`datadiff.py` compares working `dtm`, `zps` or `line` JSON with the SHA-256-verified published version
named by `data/MANIFEST.json`, read from the machine cache. `--ref DIR|REV` selects another published
manifest. Reports in `reports/diffs/` give counts per area class/source kind, the absolute-height-change
histogram in metres, and the largest changed vertices with their record IDs and XY. Shapes match by
class, level and exact XY; reordered rings/records are unchanged, XY edits count as added/removed,
and closed outline endpoints count once. Missing heights count separately. `line` also lists changed
fields and array counts. `--at X,Y` lists nearby working survey areas and source segments (including
their levels and height-accuracy classes); the JSON report retains their vertices.
Both tools accept `--cache DIR`. If an old blob is missing, populate the cache with `snapshot.py data-fetch`
in a separate checkout of that reference; comparisons never restore over the working data.

**Inspect mode** (looking around fast): open `index.html?line=17&inspect` and start a shift, or press
**I** during one. The autopilot drives, time runs at 4× (Space pause, + / − from 1/4× to 32×), the cab
overlay is hidden and the mouse moves the camera: **orbit** around the tram or **fly** (C; Shift faster, wheel = flying speed). PgDn / PgUp
(or . / ,) put the camera at the next / previous stop, T back to the tram, I leaves (the autopilot keeps
driving: O hands back the controls). The camera's route position is on the panel, handy with the lints.

**The free cameras** (the outside view, inspect mode and review mode) take the same controls (#342), the scheme of 3D viewers such as Three.js's `OrbitControls`:
- **Left drag** turns and tilts: a drag to the right looks to the right, a drag down looks further down.
- **Right drag or Shift-drag** moves the camera where it is free (fly, review mode). Tied to the tram (the outside view, orbit), it turns.
- **The wheel** zooms (in fly: flying speed).
- **Keys** (inspect and review mode): W/A/S/D move, R/F up and down, Q/E or ← / → turn, ↑ / ↓ tilt. The outside view has none: the keys drive the tram.
- **Touch:** in review mode one finger moves and two pinch, twist and tilt; in the outside view one finger turns and two zoom.

**The review directory** (`reviews.html`, linked from the menu; #288) lists every review set in
`reports/review/` under the issue that waits for it, with answered, unsure and waiting counted live from
the answer store, a link per line that opens the set with only its unanswered findings (`&todo`), and
the open PRs' questions for the user. Its index (`reports/review/index.json`: the sets, their issues and
lines, the issues' titles and states, the PRs' questions) is built at each deploy by
`tools/review_sets.py`; locally, `python -I tools/review_sets.py` writes it. A set names its issue and
lines in the file (`issue`, `line`, or per finding `line` / `lines_near`); `KNOWN` there covers the
tools that do not write them yet. The kerb review lists are listed there too, under #142, though they lie in each
line's survey data, not in a file.

**Review mode** (the checks' findings on the map, desktop or phone; #129): open
`index.html?line=17&review`, no shift needed. The panel lists findings worst first:
- the kerb review list from the survey's provenance (`tools/kerbs.py`);
- seams and flat or sunk kerbs between neighbouring survey areas, grouped per 30 m;
- with `&review=reports/x.json`, every `{x, y}` in that file (a lint or headless result, a hand-made list).

Choosing one (a row, a tapped pin, N / B) moves the camera there. The card says:
- the street (OSM name) and the nearest stop;
- `s`, `x, y` and lat/lon;
- links to Mapillary, Panoramax, the Mapy.com aerial and Google Street View at that place (facing the camera's heading).

**Layers** toggles the survey classes as colours, the wireframe of the survey triangles, the survey's own lines (**Source**), kerb edges, seam posts, pins, our track, the buildings and the trees.
**Orthophoto** drapes IPR's leaf-off orthophoto (2026, CC BY 4.0) over the ground around the target: 150 m at 0.1 m, or 75 m at the native 0.05 m with the camera within 40 m (rails show only then). The browser loads it straight from IPR's ImageServer; nothing is stored on our server. It is drawn over the world and the classes (switched off with it), under the other overlays; the credit and a failed load show at the top left. Beside it, **contrast** sets each spot's brightness against its 1 m surround (rails in pavement and kerbs show over sun and shade alike) and **lines** draws thin dark lines (rails, joints, also shadow and people outlines) in cyan: `orthoLook` in `src/review.js`, which says what else was tried.
**Track sources** draws the line's track centrelines as the build took them (`tracks[].src`): orange DI, violet OSM, yellow DTM points, green orthophoto. Over the orthophoto they show where a source lies against the rails, e.g. for `reports/review/track-sources-N.json`.
The classes and the wireframe are the game's build of the survey (`tools/dtm.py`: merged areas,
fitted heights). **Source** draws the survey's 3D lines as they come (`data/lineN.zps.json`,
`tools/zps_source.py`, lines with surveyed streets) at their own heights: white at ground level, cyan
below, orange above, red dots where a vertex has no height. The card then lists the source lines
within 5 m with their kind, level, height there and height accuracy class.

The camera takes the free cameras' controls (above). The address follows the camera (`&at=x,y,yaw,pitch,dist`), so a place can be bookmarked or sent. From a phone at home: `python tools/serve.py 8742 --lan` (only the game's files; read-only apart from review answers) prints the address to open; Windows asks once to allow it through the firewall.

**Answers** (#136): the card has a button per answer (1–4 on the keyboard) and a note. The answers compare
the game with reality (the imagery): kerbs wrong in game / matches reality / other level or wall / unsure;
which of the source and the build is wrong is for the agent to find. An answer is saved
and the card moves to the next finding without one; **to do** hides the answered ones, and their pins turn
grey. The answers are kept per line in the browser and sent to the server, which merges them per finding
(the newer wins), so a phone and a computer share one review:
- on the test host: `review.php` (uploaded by `tools/deploy.py`, behind the site's login), stored in
  `reviews/`; `tools/autodeploy.py` pulls them into `reports/reviews/lineN.json` of the deploy checkout
  on every run, and `python -P -E tools/deploy.py --pull-reviews` does it at once;
- with `tools/serve.py`: straight into `reports/reviews/lineN.json`.

Each answer keeps the finding's kind, place, street and info with it, so it can be read without the page.
A findings file can bring its own answers (`"options": [...]`). Lists for review are committed in
`reports/review/` and deployed with the site (the review directory lists them). A set whose issue is
closed while findings wait is out of date and is deleted (the user, 2026-11-05): #106's track-height
disagreements (`track-z.json`, `tools/dtmp_tracks.py --findings`) went that way.
`?line=17&review=reports/review/track-sources-17.json` lists where the track is not from DI and where DI and
OSM disagree on a switch (#20, `tools/track_sources.py`); "matches reality" recorded in `data/truth.json`
(`trackSources.reviewAnswers`) takes a finding off the list, anything else goes in a note.
The grouped structure-height queue uses `?line=17&review=reports/review/track-heights.json`: select a
decision to inspect its linked spans, height profile and sources. Answers with notes, uncertain choices
and unspecified levels remain held. The card explains any held archive answer (a dip under a bridge, a
steep step) and offers `archive, bridged over a dip` and `follows survey surface` only where they import;
`python -P -E tools/track_structure_review.py` rewrites those offers from the committed queue after the
import rules change. Answers talked over with the user are recorded in `data/truth.json`
(`trackHeights.reviewAnswers`, one per decision with its quote): `python -P -E tools/track_span_evidence.py`
converts those; `--from-reviews reports/reviews/line17.json` converts a page's unambiguous answers instead.
Proposals stay separate from approved height evidence;
the [height fallback decision](docs/decisions/2026-10-30-track-height-fallback.md) gives the calibration,
reproduction commands and `--evidence` format.

**Report an issue** (#138): **⚑ Report** at the bottom left of a shift, or F9 (also in inspect mode),
pauses the game and asks for a kind and a note. Send stores the note with the moment's state and a
screenshot of the 3D view. The state covers the line, trip, clock, weather, seed, tram position, speed
and notch, the camera, lat/lon, a review-mode link to the place and the deployed version. The record is
stored as `report-<date>-<time>-<code>`; the id is shown so it can be quoted in chat. It goes into the
same store as the review answers: on the test host it comes back through `autodeploy.py` as
`reports/reviews/report-….json` and `.jpg` in the deploy checkout; locally `serve.py` writes it there
directly. Without a server the record is downloaded as a file instead.

**Street bot** (where DTM streets are imported): open `index.html?line=22&bot` and start a shift. The
bot drives every car lane and walks every footway the traffic uses (1 m steps), compares the car and
walker heights with the triangles actually drawn and the DTM area class under the wheels, and lists
the places that look wrong, worst first: kerb steps, wheels on a sidewalk, height jumps, tilted cars,
floating or sunken cars and walkers, gaps in the surveyed streets, bumpy footways. Click a row (or
`n` / `b`) to fly there; arrows orbit, `+` / `−` zoom; coloured posts mark every place.
`window.streetBot` holds the result (`stats`, `findings`, `raw` samples). One run takes about a minute.

## How the game's parts work

What the player's guide ([README.md](README.md), [README.en.md](README.en.md)) leaves out:

- **The right mirror** grows with the window (a quarter of its height, 110–420 px) and keeps its
  aspect, so its field of view stays the same; its picture is drawn at the frame's size in device
  pixels. The texture updates at most 30 times a second, with a 300 m horizon. Flat covers/grates are
  omitted; people, vehicles, poles, overhead wires and the tram remain. Its cached picture is
  composited after every main redraw, including while paused.
- **The T3's TR 37 equipment** (#221): `src/tr37.js`; sources and derivation in
  `docs/research/prazsketramvaje/t3-accelerator.md`. Acceleration by step: `tools/test_traction.py`.
- **On-screen controls** (#79): `src/touch.js`.
- **Stops and lines:** stop posts come from GTFS `route_stops`, stops and departures from GTFS, platforms
  from OSM. The tram ahead's line is one that serves that stop in GTFS.
- **Speeds:** the posted speed is that of the OSM tram way (`tools/osm_speeds.py`, the data OpenRailwayMap shows).
- **Traffic:** cars drive a lane graph (smooth lanes, turning curves through junctions) and pitch and roll with the road surface. Zebra crossings come from OSM.
- **Idle pages** draw 4 frames a second (#149): the menu, a pause, the results, review mode with its
  camera at rest. Driving and inspect mode draw every frame; a hidden tab draws nothing.
- **Interlaced track in Letenská:** detected automatically from the two OSM route relations.
- **Radio/IRC switching** remains in the code for switches the data marks as such; none are marked now.
- **Terrain:** OSM track geometry is smoothed into curves, and the terrain is lowered under every track
  bed so it never pokes through.
- **Buildings:** the type is read from the OSM tag under each LOD2 building, its roof shape and size;
  Mosty 3D sets the deck height on tagged bridges.
- **Outdoor temperature:** Prague now comes from Open-Meteo, hourly.
- **Tram models:** `assets/t3h/LICENSE.txt`, `assets/t3/LICENSE.txt`, the second car's coupling #248;
  `ASSETS.md` lists them.
- **The autopilot** drives like the headless test bot: the same driver lives in `src/autopilot.js` and is
  used by `tools/autopilot.js`.
- **Language:** strings live in `src/i18n.js`. The player's guide is `README.md` in Czech and `README.en.md`
  in English, one source for the repository and for Help in the game's menu (`src/help.js` shows what stands
  between `<!-- help -->` and `<!-- /help -->`, and renders only the Markdown those files use). A change to one
  changes the other; `tools/test_readme.py` checks that their headings match.
