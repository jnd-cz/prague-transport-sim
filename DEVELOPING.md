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

### A Linux build machine (Debian 13 VPS)

A second machine for what needs CPU and memory, not a GPU: world builds (`rebuild.py`, `ground_mesh.py` 21 GB,
`city_terrain.py` 15 GB), the place loop, tool tests, unattended sessions. 8+ cores and 32+ GB. It has no GPU: page
tests run on SwiftShader (slow, right answers), frame time means nothing there, and seeded compares stay on the
machine that holds main's baselines. `heavy.py` queues per machine; the `rebuild` label is on GitHub and holds
across machines. Steps, as a normal user with sudo (not root):

1. **Packages** (Debian's own Python 3.13; `python-is-python3` lets the docs' `python` commands run as written):
   ```bash
   sudo apt update
   sudo apt install -y git curl tmux python-is-python3 python3-pip python3-venv \
       python3-pyosmium python3-pyproj python3-shapely python3-numpy python3-scipy python3-pil
   python -m pip install --user --break-system-packages pydelatin==0.4.0 brotli playwright lameenc
   python -m playwright install --with-deps chromium
   python -P -E -c "import osmium, pyproj, shapely, numpy, scipy, PIL, pydelatin, brotli; print('ok')"
   ```
   (Debian refuses `pip install --user` into its Python; `--break-system-packages` only lets it write
   `~/.local`.) **`gh` from GitHub's own packages, not Debian's:** Debian 13's gh 2.46 has no `blockedBy` field, so
   `board.py`'s issue list fails and it says "GitHub not reachable" (Windows had 2.103.3; 2.106.0 works):
   ```bash
   curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg > /dev/null
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg]" \
       "https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
   sudo apt update && sudo apt install -y gh && gh --version
   ```
   Without sudo, the release's `gh` binary in `~/.local/bin` does too (updated by hand).
2. **Clock and environment.** The night window (23:00-07:00) is the machine's local time. `/tmp` is erased at boot,
   and `heavy.py`'s queue and history live under the temp folder: `TMPDIR=/var/tmp` keeps the history.
   ```bash
   sudo timedatectl set-timezone Europe/Prague
   echo 'export TRAMDATA_CACHE="$HOME/tramdata-cache"' >> ~/.bashrc
   echo 'export TMPDIR=/var/tmp' >> ~/.bashrc
   echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
   source ~/.bashrc && mkdir -p "$TRAMDATA_CACHE"
   ```
3. **Claude Code**, signed in through a link opened on another device:
   ```bash
   curl -fsSL https://claude.ai/install.sh | bash
   claude --version && claude doctor
   claude                  # log in: open the printed URL elsewhere, paste the code back
   ```
4. **GitHub**: a fine-grained token for this repository only, under *Repository permissions*:

   | permission | access | for |
   |---|---|---|
   | Contents | read and write | push branches (and small doc changes to main) |
   | Pull requests | read and write | open, update and comment on PRs |
   | Issues | read and write | comments, labels (`rebuild`, `needs-user`), findings |
   | Actions | read and write | read CI runs and their logs, rerun or cancel a run |
   | Commit statuses | read | the checks on a commit |
   | Workflows | read and write | only for CI work (`.github/workflows/`) |
   | Metadata | read | (always on) |
   | everything else | no access | |

   With Contents left on read, `git push` fails with 403 "Permission … denied" although the account owns the
   repository (the ruleset on main only forbids deletion and force-push); a token's access can be edited in place.
   ```bash
   gh auth login           # GitHub.com, HTTPS, paste the token
   gh auth setup-git && gh auth status   # run setup-git with the gh that stays (it writes that gh's path)
   git push --dry-run origin main        # "Everything up-to-date" or a ref line: the token can push
   ```
5. **Clone**, then the store's key and SSH config as in [DATA.md](DATA.md) (one-time setup, steps 1-3). Copy the
   `Host tramdata` block from a machine that has it; check the server's fingerprint on the first `sftp tramdata`
   against that machine's (`ssh-keygen -lF "[host]:port"`).
   ```bash
   git clone https://github.com/jnd-cz/prague-transport-sim ~/transport-game && cd ~/transport-game
   git config user.name "<name>"
   git config user.email "2506000+jnd-cz@users.noreply.github.com"
   chmod 600 ~/.ssh/config
   python -I tools/snapshot.py fetch && python -I tools/snapshot.py data-fetch
   ```
6. **Check**: `python -I tools/board.py`, `python -I tools/test_all.py`, then one line's build through the queue.
   `free -h`: the builds read the `available` column (`sysinfo.available_gb`, MemAvailable, #897), not `free`.
7. **Sessions from the phone**: Claude Code in tmux with Remote Control; the session shows in the Claude app.
   ```bash
   tmux new -s tram        # Ctrl+B D leaves it running; tmux attach -t tram comes back
   cd ~/transport-game && claude remote-control
   ```

On Linux a job's stop ends what it started by walking the process tree; a `kill -9` of `heavy.py` itself leaves
its children running (no Job Object there).

## Rebuild the line data

Every build reads the pinned source snapshot in `raw/` (DATA.md); OSM comes from its local extract
(`raw/osm/praha.osm.pbf`, pyosmium, so the OSM tools run with `-P -E`). The Overpass API is not used.
The extract's tagged ways and nodes and its relations are decoded once per extract and machine into
`TRAMDATA_CACHE/osm-index/` (else `raw/osm/index/`; ~50 s, keyed by the extract's hash and the code that writes
it): `tools/osm_local.py`'s `ways()`, `nodes()` and `relations()` answer from it, where each was a pass of
~15-30 s over the file (#511). DI's and the archive's tracks are parsed, and DI's network built, once per machine
into `TRAMDATA_CACHE/kept/` (else `reports/cache/kept/`; `tools/dtmp_tracks.py` `kept`, keyed by the sources'
provenance hashes and the code that reads them, the last 4 of each kind kept): `build_line`, `dtm` and the heights'
staging read them back, where each spent ~15-25 s on them (#517).
All lines share one frame: S-JTSK metres from the Marian column (`tools/geo.py`).

The whole chain for a line (logs in `reports/rebuild/`): `build_line` first, then its independent steps
side by side; `--parallel` also builds the lines side by side, as many as free memory holds (~2.5 GB each).
A line takes ~2-4 min to its street surfaces; then its ground (4-10 min a line, up to 21 GB), the network on it and
the build ID, one line after another (#702):

```bash
python -P -E tools/rebuild.py 17 22          # or all lines: python -P -E tools/rebuild.py --parallel
python -P -E tools/rebuild.py 9 --from dtm   # that step runs again (track = build_line, heights = line_heights,
                                             # ground = ground_mesh)
python -P -E tools/rebuild.py --force        # every step runs
```

A step runs only when something it read changed (`tools/stepcache.py`, #511): each run is traced (the files it
opened, probed or listed under the checkout, the modules it imported from it, the packages' versions) and
recorded in `TRAMDATA_CACHE/stepcache/` (without a machine cache: `reports/rebuild/cache/` of the checkout; the
records name files by their path under the checkout, so they hold in a fresh worktree, #797); a step whose record still holds is skipped and its outputs put back as that
run left them, so the next step reads what it read before (`data/lineN.json` is rewritten by several steps in
turn). A change to one rule reruns the steps that read what it changed, down to the first whose output stays the
same. `lineN.log` says per step whether it ran and why (`tools/track_profile.py changed`, `data/line9.json
changed`). `data/truth.json` is keyed by the sections a step read (#816): a step that parses it with `json.load`
or `json.loads` gets a dict that notes the top-level keys it reads, so a new place in `groundPlaces` reruns no
build step (`data/truth.json: stopSigns changed` where one did change). A step that reads it whole (iterates,
copies or dumps it) or opens it without parsing keeps the whole file in its key. A tool that reads a file the trace cannot see (C code other than osmium's reader, a subprocess) needs
`--from` or `--force`, or the file declared: `rebuild.py` gives the step a name and a value that changes with it, kept
in its record (`run_step(declared=...)`). The ground declares the city mesh it reads from the machine cache by its
key; where the mesh of the current inputs is not there, `rebuild.py` runs `tools/city_terrain.py` first (#702).
`reports/rebuild/ground.summary.log` names the mesh.

The single steps:

```bash
python -P -E tools/build_line.py --line 37         # no OSM route relation: from its GTFS shapes
python -P -E tools/build_line.py --line 22 --headsign "Zahradní Město"
python -P -E tools/build_line.py --line 23         # any Prague tram line
python -P -E tools/build_line.py --line 17 --refresh  # recompute the OSM answers cached in raw/line17/
python -P -E tools/build_line.py --line 9 --then 10   # a vehicle run: 9, continuing as 10 at the terminus
python -P -E tools/line_heights.py 17 22           # top of rail (#197), after the lines' survey sidecars
```

`rebuild.py` ends with `line_heights.py` for all the lines it built `line_structures.py` and `cross_level.py` per line (~2.5 min: it stages the network's heights
with the maintainer's answers and assembles one profile per DI track, docs/decisions/2026-11-02-vertical-profile.md);
`reports/line-heights.json` lists the stretches without a height, the junctions where the radius gave way and
the steps. `headless.py --checks heights` compares the game's track with the staged heights. Its log says when each
stage ended (`(staged: 97 s from the start)` …), and the staging's parts. The staging matches and decides its samples
in worker processes (#516). The chains' runs are solved in worker processes (#511, #516): every chain's first solve
side by side, then each chain pinned as soon as the chains before it that it meets are final, and the lines written
side by side. A run whose points are as at its chain's earlier solve keeps what it found. With under 16 chains (the
tests) all of it runs in one process, strictly in the order. The workers load what they are given from one pickle
(`tools/sysinfo.py` `pool`). Each ADMM step solves its pentadiagonal system by LAPACK's banded Cholesky factor (SciPy,
docs/decisions/2026-11-13-scipy-banded-solve.md). Of `line_heights`' ~125 s the staging takes ~55, the chains and
answers ~17, the solves ~19 (chains waiting for the chains they are pinned to, not the workers: 4 BLAS threads x 6
workers and 1 x 12 took the same) and the writing ~31 (five lines, 24 cores).
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
pyosmium, pyproj, shapely, numpy, SciPy, Pillow, brotli and pydelatin 0.4.0 live in the user site packages;
`tools/sound_encode.py` also needs lameenc).
Run alone, `build_line`, `dtm`, `line_heights` and `import_track_heights` wait their turn among the heavy jobs, as
`rebuild.py` does; under it they run in its turn. Any other long run (a profile, a bench, a comparison) goes through
`python -I tools/heavy.py "what" -- CMD ...` (AGENTS.md, #536; `--shared GB,CORES` for one that is no timing, #728):

| step | writes | what |
|---|---|---|
| `platforms` | `lineN.json` | tram platforms of both directions: PID GTFS positions, names and lines, OSM shapes where mapped (`--fetch` re-reads them from the snapshot's extract) |
| `osm_speeds` | `lineN.json` | posted speeds and dedicated track: the speed limits and banked curves |
| `clearances` | `lineN.json` | roads passing under the route with their OSM `maxheight` (the profile keeps the track over them); the clearances posted for the ways along the tracks (`headroom`, `tools/headroom.py`: the page lifts a bridge model's underside to them, #71) |
| `dtm_points` | `lineN.dtmpoints.json` | street furniture from the archived technical map |
| `osm_signals` | `lineN.signals.json` | line 17 only, until the placement rules (#22): OSM traffic signals |
| `osm_validate` | `lineN.validate.json` | every line: a check of the line against OSM |
| `geoportal` | `lineN.geo.json`, `lineN.bld.bin` | 110 m either side of the route: IPR LOD2 buildings and Mosty 3D bridges (I3S), retaining walls with heights, the city tree register (`--trees-only`); without it the game extrudes OSM footprints |
| `dtm` → `zps_source` | `lineN.dtm.json`, `lineN.zps.json` | the surveyed streets (DTM ZPS), their ground level judged against IPR (`tools/zps_ground.py`, #446), their decks checked against Mosty 3D and the raised rails, flat over the ways under them, thinner by `maxheight` (`tools/zps_decks.py`, #445), railway yards, lawns and paved yards on IPR's ground marked to take the lidar inside and the passages' plugged portals on IPR's floor (`tools/zps_inside.py`, #444), with their kerbs put back (`tools/kerbs.py`, #21), then the survey's own lines for review mode; the districts per line are `DTM` in `tools/dtm_packages.py`, lines held from it are `HOLD` |
| `placement` | `lineN.json`, `lineN.built.geojson` | where each signal stands and where the front stops beside a hung one, by the game's rules with the rule that decided (`signals`; `signalsRaw` as `build_line` found them), where each platform is drawn, and the stop types from the survey's areas (`vienna`: so after `dtm`, #701). The compiled world for review (docs/architecture.md §10.4). The game logs where its own rules disagree (`game.placementDiffs`, #22). From here on a line with surveyed streets needs its `lineN.dtm.json`: a step that reads it and finds none stops `rebuild.py` (`tools/step_inputs.py`) |
| `track_styles` | `lineN.json` | the track styles (`styles`: the maintainer's marks, prazsketramvaje.cz's grassed-track list, answered review cards, the survey's grass; cut at platforms and crossings, #479, #503) and the rails' height over the bed every 2 m (`lift`, blended inside each section, #480) |
| `line_heights` (all lines once) | `lineN.json` | the top of rail every 2 m along the path, the opposite path and every drawn track (`heights`, `heightSource`, a track's `zs`, #197); where no source has one, the surface plus the lift (`surface`, #480): no sample is left without a height, else the build fails |
| `line_structures` | `lineN.json` | the spans the route runs on a bridge, those with a deck the track lies on, and the roads under it with their clearance (`spans`, `realDecks`, `underpasses`, #480) |
| `cross_level` | `lineN.json` | the cross level of paved track where the road tilts across both tracks: one plane of IPR across them, the rails tilted with it (`crossLevel`, #538) |
| `ground_mesh` (`--no-network`) | `lineN.ground.*` | after `street_profile`: the ground welded into one mesh (below, **Ground**); written only when the file decodes to the mesh built, its vertices and each class's triangles with their names, else the build fails (#702) |
| `network` | `lineN.network.json` | on the ground file: the traffic's roads, lanes, walks, doors, the signals bound to the lanes (below, **The network**) |
| `build_id` | the line's other files | the line's build ID, `data/lineN.json`'s CRC-32, into the provenance (`build`) of the files the page loads with it (`FILES`); the page computes the line file's and refuses a set of another build, or with a file that carries none, naming `rebuild.py N` (`src/buildId.js`, #702). A tool that writes one of those files stamps its provenance afresh, so a file built by hand after a rebuild carries none; a set where no file carries one (built before #702) is refused too (#829). `python -I tools/build_id.py --check N` lists them |

The page computes no profile of its own (#480): it reads the built top of rail, the lift and the structures. Where each source comes from, how it is refreshed (the GTFS service date, the survey's district
packages, DI, the terrain) and its licence: [DATA.md](DATA.md) and [NOTICE.md](NOTICE.md).

**The city terrain** (#428, the first step of #276's ground): `python -P -E tools/city_terrain.py` meshes IPR's
1 m raster of the whole city once, 10 cm within 120 m of DI's tracks and growing beyond (at most 3 m), with no
cell over its tolerance. It is no line step (`rebuild.py` runs it before the ground where the mesh of the current
inputs is not there): the mesh goes into the machine cache
(`TRAMDATA_CACHE/city-terrain/<key>/`, keyed by its inputs and the code that makes the mesh: the three files of
`CODE`, `city_terrain.py` up to its section on the key and the cache, so a change to the command line or the
heavy-job turn keeps the mesh, #757), not `data/`. The ground file is built from it (`tools/ground_mesh.py`). A
heavy job: 13 min and 15 GB on the dev PC; `--box x0,y0,x1,y1` meshes a part at once. Its report and a picture of
the city limits go to `reports/city-terrain/`.

**A place's ground** (#757): `python -P -E tools/ground_place.py NAME` builds the ground of one place of
`data/truth.json` `groundPlaces` (or `--line N --at X,Y`) with the line build's own code
(`ground_mesh.build(within=...)`): the tiles its reach touches and one ring of tiles round them, in one to three
minutes and 3 GB on one core, with no turn among the heavy jobs. `--all` (or several names) takes one shared turn
and builds `--jobs` places at once (4), each in its own process: it queues for one place (3.5 GB and a core; 5 GB
with `--rings`) and takes up to `--jobs` of what the queue leaves once its turn comes; `--jobs 1` builds them one
after another (#843). The 36 places of 2026-11-24 took 18.5 min at 4 at once, 64.8 min one after another. Into `reports/places/NAME/` go its
measures inside the reach (the steps' walls by height, the steep faces that are no wall, the area per class), the
same of the written file, both from above as pictures, and the **locality**: the place's middle tiles against
`data/lineN.ground.*`, vertex for vertex and triangle for triangle. A tile's ground is meant to depend on the tile
and its ring only, so with unchanged tools every difference is a rule that reads something farther away, named by
what gave the vertex its height. A ground rule is tried on its places first; the lines are rebuilt once for a
batch of changes.

**Which places a ground change runs** (#865). Two sets:
- **`--locality`:** a fixed set of 8, one place for each kind of defect #812 found reading past the ring (`tools/ground_rules.py` `LOCALITY`). It is built with one ring and with two in 13.5 min at 4 at once (2026-11-26), and each place must come out with 0 triangles and 0 heights differing.
- **`--rule R`:** the places of the rules the diff changes. `tools/ground_rules.py` `RULES` gives each rule's code (functions, classes and constants of the six tools a place's build runs) and the places that guard it. `tools/tiers.py` names the rules from the definitions that differ from the merge base's.

What changes in no rule (`build`, the weld, the partition's frame) runs the set and places chosen by hand. `--all --rings` runs once a batch, with #757's rebuild, at night. Before this, the places grew from 36 to 48 during #812, and its proof of 61 places with one ring and two took 2 h 10 min of the queue a round.

When places are added:
- a new place goes into a rule (`tools/test_ground_rules.py` holds every place to one);
- a new kind of defect that reads past the ring adds its place to the set, and a unit test that shows it without a place.

A place says how it should look and how that is measured. `seen` is what street-level imagery shows there, in
words, with the points and headings it was looked at from (the pictures themselves are not kept: they are the
provider's). `sections` are lines across the place, each with the most of a measure it may have: the ground is
sampled every 0.25 m along the line and compared with IPR's 1 m raster. A wall between level grounds may slope
for a few metres at most (rise over run between 0.2 and 3) and stay within 0.5 m of the raster but for the wall's
own 2 m; a ramp or a flight of stairs keeps to the straight line between its ends. `--written` measures the
written file alone, in seconds: the quay's section slopes for 10 m of its 30 (2.5 allowed) and Krejcárek's stairs
stray 0.39 m from their chord (0.15 allowed) on the data of 2026-11-19. To see a place as the game draws it from
where a panorama stands, `tools/shot.py --view review --at X,Y --yaw H --pitch P --dist D` with the target `D` m
ahead of the camera along `H`; a compass heading is 7.8° more in the local frame.

## Deploy

The game is static files: `index.html`, `src/`, `assets/`, `data/`. Three.js comes from jsDelivr and
the outdoor temperature from Open-Meteo, both fetched by the browser. `python tools/make_dist.py`
packs them into `dist/tatra-t3-prague.zip`; unzip it into any web server directory. Enable gzip or
brotli for `.json` and `.bin` on the server (~3x smaller downloads). The detailed tram model is
CC BY-NC 4.0: fine for a non-commercial public test, with its attribution shown in the menu.

To a web host over FTPS (#131): `python -P -E tools/deploy.py` uploads the same files from a clean commit
whose data matches the manifest:
- only the changed files go up (the server keeps `.deploy-manifest.json`), and removed ones are deleted;
- a connection the host drops (the alpha's did after ~130 files, #861) is opened again and the step tried again, up to 4 times; the manifest goes up every 20 files too, so a deploy that stops is resumed by the next run, not started over;
- the data heavy packs (`.json`, `.bin`, `.glb`, `.gltf` in `data/` and `assets/`) go up only compressed, as `<name>.brotli` at quality 11 (#275), and the `.htaccess` hands that file to every request for `<name>`. The rest stays plain, for the host to compress on the fly. The site was 114.6 MB plain and is 31.5 MB this way. Browsers accept brotli only over HTTPS, so the host must redirect HTTP (Plesk: Permanent SEO-safe 301 redirect from HTTP to HTTPS). Without it Chromium refuses the files (`ERR_CONTENT_DECODING_FAILED`), a browser that hands the page the raw bytes shows the bar at 5 % with every file ticked, and the loading screen says to open the page over https (#371);
- it adds `version.json`, shown in the menu's credits, and that `.htaccess`;
- `--dry-run` lists the changes, `--reports` adds `reports/headless/*.json` for review mode, and a rollback is a deploy from the older commit.

The host, the FTP user and the folder go in `deploy.local.json` (git-ignored; format at the top of the tool). The password is asked for each time, or read from `TRAM_DEPLOY_PASSWORD` or `~/.netrc` (`machine <host>`, or the config's `"netrc"` name when two FTP users share one host, as the test site and the alpha's `sim.8b.cz`, #350). The site's own protection is the host's: in Plesk, Password-Protected Directories on `/`. After each upload the tool checks that `version.json` answers 401 without a login.

Automatic (#131): `python -I tools/autodeploy.py` in a checkout kept for deploys (detached HEAD, with
`deploy.local.json`, as `../tg-deploy`) deploys `origin/main` when it moved since the last deploy:
checkout, `snapshot.py data-fetch`, `deploy.py`. `--install` registers a Windows scheduled task that runs
it every 10 minutes while you are logged on (`--uninstall` removes it). It needs the password in
`~/.netrc` (`machine <host> login <user> password <password>`); a failed deploy is retried after an
hour. Log: `reports/autodeploy.log`. Every run also pulls the review verdicts and every target's feedback notes
(`deploy.py --pull`). It deploys only the test site.

**The closed alpha** (#350): `sim.8b.cz` on the same host, without a login. `deploy.local.json` names it under
`targets` (`{"alpha": {"user": …, "netrc": "sim.8b.cz", "url": "https://sim.8b.cz/", "public": true}}`); a
named target takes the top level's keys it does not set. A public target:
- gets no review tools (`review.php`, `reviews.html`, `reports/review/`), and `robots.txt` with an
  `X-Robots-Tag: noindex` header ask search engines to keep away;
- is deployed only from a tagged commit (`git tag alpha-N`, pushed), never with `--dirty` or `--reports`;
  `version.json` names the tag, so a tester's note says which version it was;
- is checked after a deploy: the page and `version.json` served, every review tool 404, `feedback/` 403.

`python -P -E tools/deploy.py --target alpha` from a checkout at the tag (`--dry-run` first).

**Feedback** (#350): ✉ Feedback in a shift (F9, `src/report.js`) posts a note to `feedback.php` (`tools/feedback.php`,
on every target): the note, the moment's state (place, tram, run, camera), the errors met on the page, the
machine, the load times, the frame-time log (`src/perf.js`) and, if ticked, a screenshot. It only takes notes in,
within its caps (2 MB a post, 5000 characters, 3000 notes and 500 MB kept, 20 a minute), stores no IP address,
and nothing reads them back over HTTP. `deploy.py --pull` moves them off each host into the machine's feedback
folder (`$TRAM_FEEDBACK`, else beside the data cache: `tramdata/feedback/<target>/`, never in git); `tools/serve.py`
takes them locally into `local/` there. `python -I tools/feedback.py` lists them by kind (`--site`, `--line`,
`--kind`), `--perf` gives frames per second and slow frames per machine. A note becomes an issue only when
someone decides so.

**Package submissions** (#580): the Vehicles… page sends a checked package, or its address, to `submit.php`
(`tools/submit.php`, on every target; its caps beside `tools/submissions.py`'s, which `tools/serve.py` applies
locally). The host's PHP must take a 64 MB upload (`upload_max_filesize`, `post_max_size`). `deploy.py --pull` moves
them into the machine's submissions folder (`$TRAM_SUBMISSIONS`, else beside the data cache:
`tramdata/submissions/<target>/<id>/`, never in git: the contact is the author's). The review:
`python -I tools/submissions.py` lists them; `python -P -E tools/submissions.py --check ID` installs it in a fresh
headless browser, writes the check's report and pictures it beside the hybrid (`reports/submissions/<id>/`);
`--accept ID` adds it to `assets/catalogue.json` (a PR), hosted when its author allowed it (the pack copied to
`tramdata/submissions/hosted/`, which `deploy.py` uploads as `hosted/<name>`: a deploy refuses while the catalogue
names one that is not there) or linked at the author's address (`--url` for an uploaded one; the upload deleted);
`--reject ID "why"`; `--delete ID` once the author has the verdict.

**Sound packs' files** (#636): a pack's WAV masters become the Ogg Opus files it plays and their MP3 fallbacks with
`python -P -E tools/sound_encode.py assets/<id>`: headless Chromium encodes the Opus (WebCodecs), LAME the MP3s
(`python -m pip install --user lameenc`; maintainer, 2026-11-17), and each is checked against its master; the manifest then names the `.ogg` files,
each with its MP3 as `fallback` and its master as `master`, and every file's size and hash. `--check` checks a pack
as it is (`tools/test_sound_encode.py` runs it on the shipped one). The format:
[docs/vehicles.md](docs/vehicles.md#sound-packs).

**Performance on players' machines** (#350): every drawn frame of a shift goes into a 1 ms histogram of frame
intervals (`src/perf.js`; pauses and idle redraws left out), with the places of frames over 33 ms. A player's
browser keeps vsync, so this says whether a machine keeps up with its display; `tools/frametime.py` (vsync off)
says what a frame costs here. A shift's end offers to send the summary; the menu's Performance test drives a
fixed minute (the line's middle stop, the trip nearest 8:00, dry, seed 1; the Reference test below) with the GPU's own time per frame where
the browser has `EXT_disjoint_timer_query_webgl2`; it starts 10 s before the departure, not a shift's 40 s, and the
minute is measured from the departure on, all driving. The Reference test is line 17 from Palackého náměstí (by name, not the middle stop) with
the detailed model. `tools/test_perf.py --runs N` runs it N times here.

**Where a frame's time goes, without the GPU's timer** (#705: Firefox has none, and most weak machines' results
come from it; `tools/feedback.py --perf` shows each):

- **The page's own time a frame** (`cpuMs`, `cpuP90`; of it the game's steps `cpuSim` and the draws' calls
  `cpuDraw`), in a shift's summary and a test's result: its scripts from the frame's start to its end. An interval
  near it is the processor's and no smaller picture shortens it. The reference stretch here (Arc A770, 1280 x
  720, 2026-11-27): 6.2 ms in Chromium (steps 0.8, draws' calls 4.4), 10.6 ms in Playwright's Firefox (1.4, 7.2).
- **A draw waited for** (`drawWaitMs`, a test's 3 s after its minute): each frame reads a pixel back, which
  returns once the GPU has drawn the frame; the time from the draw's first call to that. It holds the draws'
  calls, so it is the upper bound of the GPU's time, and follows it: in Chromium here the timer's 2.2, 5.5 and
  12.1 ms a frame (1280 x 720; 7680 x 4320; that with `gfx=log,snowall`) read 4.9, 11.1 and 17.4 ms.
- **Half the resolution** (`half`, a test's four windows of 3 s after that, in turn at half the resolution each
  way and at the full one, each window's first 0.5 s left out): the frames a second of both, on the same stretch
  of route. Equal rates say the pixels are not the limit: Playwright's Firefox here ran the minute at 45.1 frames
  a second and the windows at 39.9 (640 x 360) and 39.8 (1280 x 720). A display's rate caps both: a machine
  already at it shows nothing here.

**What the fragments cost** (#705): a weak GPU is short of fragments, not of triangles or draw calls (the testers'
phone was no faster with both halved). Two things made every fragment dear, and the page draws without both since
2026-11-27: the logarithmic depth buffer (three.js then writes each fragment's depth, so the GPU cannot reject a
hidden fragment before shading it) and the snow's two octaves of noise, which ran in every weather (now compiled
into a material only while it snows; the snow's first draw compiles them anew, 381 ms once here). The page's address
takes drawing switches to measure with, each alone or several (`?gfx=log,snowall,front,pr1,noaa`, `src/gfx.js`
lists them: `log` and `snowall` draw the old way); a performance test's result and a note's machine facts carry the
list, the renderer's pixel ratio, the render scale and whether the canvas is antialiased, and
`tools/feedback.py --perf` gives each list its own row.

- **Here** the frame interval cannot see the fragments: on the Arc A770 a frame takes 3.0 ms at pixel ratio 1 and
  3.1 ms at 1.75, the CPU's time. `tools/frametime.py --ratio 1,6` sets the renderer's ratio in the bench and
  prints the GPU's own time for a frame's draws and its cost per megapixel; 6 is 7680 x 4320, the largest buffer
  Chromium draws in full (at 8 it cuts the buffer: the row is marked and left out of the cost). Line 17, the
  detailed model, stop 15, ratio 6, GPU ms a frame, 2026-11-27: 10.6 the old way (`log,snowall`); 5.7-5.9 with
  the noise only (`snowall`); 5.9-6.1 with the logarithmic depth only (`log`); 2.9 as drawn now, which is what the frame
  takes at ratio 1 (the GPU is then no longer the limit); with the old way, 6.8 without antialiasing and 9.6 with
  front faces only on the ground and the buildings (nothing more once the two are gone; roofs are wound inwards,
  so `front` is for timing only).
- **On a tester's integrated GPU** (Intel HD Graphics 400 as Firefox names it, 1699 x 1016; the reference test,
  2026-11-27): 43.5 frames a second and 32.7 % of frames over 20 ms the old way; 59.4 and 1.0 % without the
  logarithmic depth; 58.4 and 2.4 % without the noise. Either alone reaches that display's 60 Hz.
- **Flicker** is what the logarithmic depth buffer was for, and `tools/flicker.py` counts it in motion: the same
  drive drawn two ways, the pixels that change and come back. At eight places of lines 17 and 22 (cab and chase)
  the plain buffer has 4-27 flicks a frame of its own, the logarithmic one 33-234: thin dark cracks along the
  seams of the track bed's triangles, which the plain buffer does not draw. With the near plane put at 1 mm
  (`--near 0.001`, its calibration) the plain buffer's own flicks rise from 6 to 103 and from 4 to 54: rails
  against their bed, far windows against their walls. The near plane is 0.3 m and the far one the fog's end (at
  most 970 m).
- **The render scale** (the menu; `src/autoscale.js`): automatic, it steps to 75 % and 50 % of the display's
  pixels along each axis while over a quarter of the driving frames take over 20.5 ms, and takes a step back when
  the frames got no shorter for it (the CPU, or a display held to 30 frames a second). The performance overlay
  and a note's machine facts say what it decided. A performance test and `?gfx=pr<n>` hold the scale.

`tools/shot.py --params gfx=log,snowall --ref origin/main` shows what a switch changes in a picture.

**The HUD's cost** (`python -P -E tools/bench/hud.py`, #706): what one update of the HUD changes in the page (0 when
nothing changed: texts are written only when they change, `src/hud.js` `put`) and how long it takes with the CPU
throttled 4 times. Line 17, 2026-11-19, before -> after: 13 -> 0 changes an idle update, an update 7.2 -> 2.9 ms (the
minimap 4.2 -> 0.35 ms), a frame 45 -> 32-40 ms. A drawing routine that needs an element's box takes it from
`src/boxes.js` `rectOf`, not from the page on every frame.

**The site's icons** (#485): `assets/icons/icon-{32,180,192,512}.png`, the favicon, the iPhone's home-screen icon
(`apple-touch-icon` in `index.html`) and the web manifest's (`app.webmanifest`), are drawn by
`python -P -E tools/make_icons.py`: change the drawing there and run it, never the PNGs by hand.

## Dev

**Headless checks from the command line** (Playwright, see DATA.md setup): the benches and lints below,
a line's runs batched in headless pages (#205, #413; `--batch 1`: a fresh page per run), with pass / fail per
run (exit code 1 on a failure; the thresholds are `judge` in the tool) and the results in `reports/headless/`:

```bash
python -P -E tools/headless.py --lines 17,23 --checks u3,redruns --seeds 1-3
python -P -E tools/headless.py --lines 23 --checks traffic,lint --seeds 22,7,1234
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,lint --jobs 3
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks canted
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks crossing
```

`crossing` counts 20 m route sections where a drawn pedestrian surface is above a sampled rail head;
it also reports missing rail samples and the independently mapped evidence for survey adjustments.

`--jobs N` runs N pages at once, each in its own browser process (default: half the cores, at most 8, and
~4 GB a page for line 17). The runs are seeded per page, so the counts are the same as one after another.
The pages draw nothing (#411): a page takes ~2 cores instead of ~12, with the same counts. `--draw` draws
once a second in software as before; `--gpu` puts the pages' WebGL on the machine's GPU. Tools that need
pictures (`tools/shot.py`, the mirror's screenshots, `tools/frametime.py --headless`) and every page test
(`tools/test_*.py`, `browser = gpu.launch(p)[0]`, #463) draw on the GPU through `tools/gpu.py`, and fall back to
SwiftShader, saying so, where there is none.

The harness verifies its own server before launching a job. An occupied `--port` fails without using
or stopping the existing listener; use `--port 0` to allocate a free port atomically. `--url` explicitly
uses an already-running server.

### Baselines

Regression checks compare a run with main's stored baseline (#89, #156, #282; `/regress` picks the lines and checks):

```bash
python -P -E tools/headless.py --lines 9,17,22,23,37 --checks u3,redruns,traffic,lint --compare
```

- **What is stored:** the key counts of each run and their places, under a key of what the counts depend on
  (`tools/baseline_store.py` `MEASURED`: `src/`, `index.html`, the in-page checks, `data/MANIFEST.json`,
  `data/truth.json`), in the data store.
- **Who measures main:** the deploy PC, at night, after a merge that changes one of those (`tools/autodeploy.py`,
  2 pages at once, not while a heavy job runs). A PR does not refresh the baseline. `--baseline` stores a run as
  one (it needs the game, the checks and `data/MANIFEST.json` committed and `data/` matching the manifest) and
  keeps a local copy in `reports/baseline/`.
- **`--compare`** takes the baseline of the branch's merge base and prints baseline → now per run (also in
  `reports/headless/compare.md`, for the PR), with the places new and gone (#157). It warns when main has moved
  since.
- **Seeded counts** (seeds 1-5 by default) are judged by the branch's mean against the min–max of main's seeds: a
  change to the tram's timing reshuffles traffic like a new seed (#156), so moves inside the spread are listed as
  noise. Stuck, unfinished and penalty runs are listed per seed and need a reason, as does every mean outside the
  spread and every move of a seedless check (lint, surfaces).
- **Which baseline each tier compares with** (#282):
  - a checkpoint's run stores itself under its name (`--baseline --publish --checkpoint W1`: every check, seeds 1-5),
    and loads every line as a player does beside it (`--checks u3 --seeds 1 --player --gpu`, #710: the same counts,
    or each move with its heights from the 10 m grid);
  - every check compares with main at the merge base: its baseline (the night's, or this machine's), else measured
    there once in a pinned worktree through the queue and kept on this machine by its key. A seeded check is
    measured with the seeds asked (#709), so the first compare on a base takes about twice as long;
  - `--against W1` compares with a checkpoint instead; `--no-measure-base` leaves the measuring out, and a seeded
    run then takes the latest checkpoint's.
- **A seeded compare against a checkpoint is not a compare with main** (the note says "not with main"): read no
  move from it. #582's stops moved by up to 50 late seconds against W2 and were identical to main's.
- **One drive a seed:** `u3`, `redruns`, `stops` and `traffic` asked together come from one drive of each line and
  seed, its watchers reporting each (#205, #708, #722; `--separate`: a drive each).

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
the meshes' CPU copies after loading, and draws only the ground's tiles round the camera, #30) and a shift started on the line:

```js
const { lint } = await import('/tools/lint.js?v=' + Date.now());
await lint();               // consist at every stop, signals in platforms, trees in buildings, bridges
await lint({ bot: true });  // + the street bot where DTM streets exist (about a minute)
await lint({ traffic: true }); // + the whole line driven headless with the real traffic (1–2 minutes)
```

The traffic run (`tools/traffic_lint.js`) is a watcher on the `u3` drive (`tools/bench/u3.js`): the autopilot
drives the whole line from the first stop with a fixed time step, trip 40, obstacles normal; the page's frame loop
only draws meanwhile (`window.headless`). Before #722 it drove its own run (trip 0, no obstacles), so no traffic
count is read across that change. Every 0.2 s it records every visible car, walker and tram and counts: cars or
walkers moving sideways
(`slide`), teleporting (`jump`), vehicles intersecting (`overlap`, once per episode), walkers inside
a vehicle (`walkerHit`), each with its cause where known (next road, lane beside the tram, …), and
walkers that keep within 2 m of one place for 30 s while not waiting at a kerb or in a door
(`walkerStuck`: turning, round a loop of walks, or still; #366). It is
seeded and uses autumn and dry weather, so a run on a **freshly loaded page** gives
the same counts every time (a second run in the same page differs slightly).

Reports go to `reports/lineN.json` (not in git). Regression checks use `tools/headless.py --compare`
(above), whose baseline follows main.

**Traffic scenes** (`tools/bench/scenes.js`, `tools/test_traffic_scenes.py`, #566): a few roads, walks, cars and
walkers built in code and driven on the real `Traffic` without the world (a flat ground, no stops, no spawning; our
tram only where the scene has a track), at the game's step, in milliseconds each. A rule's case is shown on a scene
first, then on the lines: `S.play('name', args)` in a page that imports the module gives what a scene reports;
`SCENES` holds them (a jam's scene with its fix switched off shows the jam).

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

`shot.py` writes individual PNGs, a labelled pair and camera/data hashes to `reports/shots/`. The small things drawn near the camera (`src/nearbatch.js`) are refilled round the captured camera before the picture, and the JSON keeps each set's range and drawn count (`near`); two captures of one checkout are the same picture (`tools/test_shot.py`, #689).
Views: `cab` (default), `chase`, `review` (`--drawn`: from above as the game draws the place, without the review's
surface classes, kerbs, seams and track line over it). The tram is paused at `s`, traffic and HUD are hidden;
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

**Pictures in a PR** (#662): GitHub takes uploaded pictures only from its web page (drag and drop into a comment);
`gh` and the API have no upload. A session puts them in its branch instead, so the PR shows them and main never
carries them:

1. Shrink each picture to a JPEG of at most about 200 KB (#662's seven: 27–209 KB) and commit them as
   `docs/reviews/issueN-<what>.jpg` in a commit of their own. Push.
2. Link them from the PR's body by that commit's full SHA, not the branch, which is deleted at the merge:
   `![desktop](https://raw.githubusercontent.com/jnd-cz/prague-transport-sim/<sha>/docs/reviews/issueN-desktop.jpg)`.
   A phone's portrait shot goes in as `<img src="…" width="320" alt="…">`.
3. Remove them in the next commit (`git rm docs/reviews/issueN-*`, only the issue's own: the directory keeps older
   pictures of #162, #176 and #178 on main) and push. The squash merge then adds nothing to main. The links keep working after the merge: `refs/pull/N/head` keeps the commit (#662's still load
   with its branch deleted).

**The limits against real rides** (#451): `python -P -E tools/rides_limits.py --lines 22,23` maps the GPS rides in
`raw/reference/rides/` (`RIDES`, the ones in a line's direction) onto each line's track and lists where a ride went
more than 3 km/h over our limit for 10 m or more, with what sets the limit there, and per stretch a quickest run at our
limits and at them raised to the ride. It needs `raw/` (`snapshot.py fetch`) and starts its own server. On line 22 the
two-car set keeps a limit 15 m longer than the rides' single T3, so it lists more places there.

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

**The project overview** (`overview.html`, test site only; #826) is for the phone: what waits for the user (PRs ready
to merge, the PRs' questions, issues labelled `needs-user`, the review sets' unanswered findings counted as the review
directory counts them), the heavy queue with estimated starts and finishes, the agents' sessions of the last 48 h and
the board. `tools/overview.py` writes `overview.json` from `board.py`'s functions, the heavy queue and the session logs
(Claude Code's and Codex's, `LOGS` there: only the folder a session works in and the PR its harness linked are read,
from the log's end, never a message), and uploads it to the test site over `deploy.py`'s connection when it changed or
9 min went by; the page turns red at 15 min. `python -I tools/overview.py --install` runs it every 5 min as a
scheduled task (pythonw, `--uninstall`), in the deploy checkout (`../tg-deploy`, which has `deploy.local.json`); a run
takes ~3 s of CPU (the board's git answers cached by commit in `reports/overview-cache.json`). A deploy never deletes
`overview.json` (`deploy.py` `KEPT`). `--print` prints the snapshot; locally `python -I tools/overview.py --print >
overview.json` and the dev server show the page.

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
  on every run, and `python -P -E tools/deploy.py --pull` does it at once;
- with `tools/serve.py`: straight into `reports/reviews/lineN.json`.

Each answer keeps the finding's kind, place, street and info with it, so it can be read without the page.
A findings file can bring its own answers (`"options": [...]`). Lists for review are committed in
`reports/review/` and deployed with the site (the review directory lists them). A set whose issue is
closed while findings wait is out of date and is deleted (maintainer, 2026-11-05): #106's track-height
disagreements (`track-z.json`, `tools/dtmp_tracks.py --findings`) went that way.
`?line=17&review=reports/review/grass-track-17.json` lists where OSM maps grass over the track and nothing we know
says so (#503, `python -P -E tools/grass_review.py`, which also prints how near the built grass's holes come to OSM's
edges); `--import` takes the answers into `data/truth.json` `grassReview`, and grass answered lays grass track.
`?line=9&review=reports/review/stairs-9.json` asks what kind of stairs stand where the ground draws a survey stairs area
steeper than 1:1, and at the places #447's thread named (`python -P -E tools/stairs_review.py`, which prints the stairs
per line, one flight or not and how steep; `--table` alone); `--import` takes the kinds into `data/truth.json`
`stairsReview`, keyed by a point inside the area.
`?line=17&review=reports/review/track-sources-17.json` lists where the track is not from DI and where DI and
OSM disagree on a switch (#20, `tools/track_sources.py`); "matches reality" recorded in `data/truth.json`
(`trackSources.reviewAnswers`) takes a finding off the list, anything else goes in a note.
The grouped structure-height queue uses `?line=17&review=reports/review/track-heights.json`: select a
decision to inspect its linked spans, height profile and sources. Answers with notes, uncertain choices
and unspecified levels remain held. The card explains any held archive answer (a dip under a bridge, a
steep step) and offers `archive, bridged over a dip` and `follows survey surface` only where they import;
`python -P -E tools/track_structure_review.py` rewrites those offers from the committed queue after the
import rules change. Regenerated with `--input`, the queue also takes street track where the heights build
(`reports/line-heights.json`, `--heights`) still has no height after its rules, as a `street` decision named
by its nearest stops, offering the archive, the survey and unsure (#202). Answers talked over with the maintainer are recorded in `data/truth.json`
(`trackHeights.reviewAnswers`, one per decision with its quote): `python -P -E tools/track_span_evidence.py`
converts those; `--from-reviews reports/reviews/line17.json` converts a page's unambiguous answers instead.
A decision whose answer there imports carries it in the findings (`recorded`), and its card and the review
directory show it answered where the page holds no answer under that decision's id (#379).
Proposals stay separate from approved height evidence;
the [height fallback decision](docs/decisions/2026-10-30-track-height-fallback.md) gives the calibration,
reproduction commands and `--evidence` format.
`?line=37&review=reports/review/survey-ground-37.json` lists the survey's ground-level areas that sit steadily off
IPR's lidar where neither DI's rails nor DMR 5G say which is right (#446): `tools/dtm.py` writes the set per line
(`tools/zps_ground.py`) and deletes it when nothing is held. `python -I tools/survey_ground_answers.py
reports/reviews/line37.json` turns the answers that are a card's option into `data/truth.json` `surveyGround.places`,
which the next `dtm.py` obeys; others stay held. An area without an answer takes the maintainer's rule
(`surveyGround.heldRule`: courtyards to the lidar, greenery outside to the survey), so a set appears only without it. `python -P -E tools/bench/survey_ground.py` measures every line's
ground level against IPR and the rails (`--dtm DIR` for main's copies). `python -P -E tools/bench/decks.py` measures
the decks (level 1 and up) against Mosty 3D and the raised rails, the Krejcárek viaduct and Divadelní's deck and
clearance (#445; `--dtm DIR` too); the build's own record is `provenance … checks.decks`. `python -P -E
tools/bench/ground_inside.py` measures the inside of every ground-level area against IPR as the page draws it, per line
and class (#444; `--dtm DIR`, `--page main` for main's drawing); the build marks what it drapes in `checks.inside` and
what it took under the decks in `checks.underDecks`. `python -P -E tools/bench/paved_ipr.py` measures paved track
against IPR along each route: the stretches whose surface lies more than 10 cm under IPR for 6 m or more, each with
its cause (the source holding it there, split by which of source and IPR the survey sides with; a curve that did not
follow; no source) and its place (#539; `--json OUT` for every run). `python -X utf8 -P -E tools/bench/kerb_causes.py
DIR` sorts the flat kerbs of a checks folder (`headless.py --checks surfaces --out DIR`, run on the checkout's data) by
what IPR, the written ground and the street surface have across each kerb: no kerb in the raster either, an area drawn
from its outline, a kerb spread wider than the check's row, flat in the street surface, the rest (#800; `--list` for
every sample, `--json OUT`).

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

## Working rules in detail

What [AGENTS.md](AGENTS.md) states in a line: how it is done, and where the rule came from.

**Skills** (Claude Code, `.claude/skills/`): `/issue N` starts an issue's session, `/regress` runs the regression
check before a PR, `/housekeeping` is the weekly pass (also every Monday at 06:30) and with `checkpoint` the
architecture review at a world checkpoint ([docs/housekeeping.md](docs/housekeeping.md)). Housekeeping posts on
the pinned #291 and only proposes.

**Heavy jobs** (`baseline_store.HeavyJob`, first come first served, the short ones first, the long ones at night;
#280, #536, #728, #851):
- Every job that keeps several cores or GBs busy for over a minute waits for the machine's other heavy jobs and
  holds its turn, so that it does not spoil another's measurement (#516). These take their
  turn themselves: `headless.py`, `rebuild.py`, `frametime.py`, `city_terrain.py`, `ground_mesh.py`;
  `build_line.py`, `dtm.py`, `line_heights.py`, `import_track_heights.py`, `street_profile.py` and
  `ground_partition.py` when run alone; `ground_place.py` for several places or `--rings` (one place runs as it
  is); `test_all.py` for the whole suite (`tools/test_heavy.py` holds this list to the code). Anything else runs
  through `heavy.py`.
- Two kinds. A job alone (a timing, or one of unknown size: every tool that does not say otherwise, plain
  `heavy.py`) waits for every job before it and every job running, and holds those after it. A shared job (a count
  run or a build: its result is the same beside another job, only later) declares its peak memory and its cores:
  `headless.py` 4 GB and 2 cores a page, `rebuild.py` 2.5 GB a line built side by side and half the cores,
  `ground_mesh.py` 21 GB and its threads, `city_terrain.py` 15 GB and its threads, `heavy.py --shared GB,CORES`
  what it is told. It waits for the jobs alone and for the shared ones queued before it, then runs beside the
  shared ones running while its cores fit beside theirs and its memory fits in what is free, less what they
  declared and do not hold yet, less 8 GB kept (`city_terrain.py` stops itself under 6 GB free, `ground_mesh.py`
  under 4). `headless.py` sizes its pages by what that leaves. A shared job goes before the alone jobs waiting ahead
  of it, and the shared ones queued behind the first of them, when 1.5× its expected time ends before the jobs
  running now are expected to end: those could not start sooner (`HeavyJob.BACKFILL`, #829; on 2026-11-23 three
  shared jobs of 3-6 min waited an hour behind two test runs that waited for a shared one). With any of those times
  not known it keeps its turn; one that runs over delays a job alone but never runs beside it. A ticket from a
  checkout older than #728 is a job alone, and such a checkout's jobs wait for every job as before. A tool becomes shared when its peak is measured
  and written at its `HeavyJob(...)`.
- By day (07:00-23:00) a job expected over 30 min, or whose time is not known, waits for the night (#851; on 2026-11-24
  three 6-min test suites waited 27-97 min behind a 95-min job of #800, and #800's chains of 56-182 min ran by day).
  Its time is its `--expect`, its tool's plan (`headless.py`, `ground_place.py`), or the median of its kind's last
  runs (`heavy.py --history`); a chain named for the first time has none, so state it. While it waits it stands
  ahead of no other job, and the board shows it "held for the night". On the user's word it runs by day:
  `heavy.py --day`, or `TRAM_HEAVY_DAY=1` for a tool that takes its own turn; say so in the PR. A job already
  running at 07:00 runs on. With the machine left free by day the user may start the night early: `heavy.py --night`
  (until 07:00; `--night off` ends it) lets the held jobs take their turns, after the jobs running now, and the board
  says so.
- A waiting job of 10 min or less goes before longer ones queued earlier (the suites, a one-line run), but not
  before one that has waited 2 h (`baseline_store.rank`, `SHORT`, `PASS_MAX`). It still waits for the jobs running.
- Checkouts of different queue versions may order the waiting jobs differently, and then wait for each other: on
  2026-11-25 three jobs did so for hours with nothing running (#854). From #854 on, a job that waits while none runs
  for 2 min (`HeavyJob.STALL`) waits only for the jobs queued before it by time, the order every version keeps, and
  says so once. Each ticket carries its queue version (`baseline_store.QUEUE`, #856); while a job of a version older
  than #851 waits, the newer ones take their turns first come first served too, its own order, so the two cannot wait
  for each other. The board marks a job whose queue code is older: "its queue code is older (merge main)". Merge main
  into that checkout before its next job (the same night #812's jobs and an older checkout's short job stood still
  that way at 06:24).
- A job that has waited 10 min behind a running one whose processes used under 2 s of CPU ends with an error that
  names it (#585 lost a night behind a job waiting for its own child): look at that job, end it, start again.
- What `tools/heavy.py` starts runs in its turn without waiting again, even a tool that queues itself or a process
  started with a clean environment: a job never waits for a process that started it (#585). A job that waits
  with nothing running ahead of it but its own wrapper is a bug in the queue: stop it and open an issue. Such a
  step's ticket names the job it runs in (an older checkout's step is found in the process table), and the queue
  counts it as that job's (`baseline_store.turns`, #844): a
  shared chain stays shared while a tool of its runs as a step, its share the larger of its own and its steps'.
  The board shows the step on its chain's line. (Before, a step that declared no share was a job alone running:
  on 2026-11-24 three shared ground places waited 22 min beside #800's shared chain, during its
  `street_profile` steps.)
- A batch of heavy steps goes into the queue at its start. A loop that calls one heavy tool after another sends
  each step to the back of the queue, behind every job queued while the last one ran, however short its steps (#800's last of five 5-min street builds still waited at 14:17, nearly 4 h after
  the first was done). The batch is split by kind, its shared steps apart from its alone ones, so that the shared
  ones run beside other jobs (maintainer, 2026-11-24). A shared step inside a job alone holds the whole
  queue for its time: #800's chain of builds of 2026-11-23 (23:11-02:13) ran alone, and three shared jobs of
  9-21 min waited 3 h behind it.
  - Steps that need nothing of each other take a ticket each, all at the start. A tool that takes its own turn
    takes it; any other count or build runs as `heavy.py --shared GB,CORES`, a timing as plain `heavy.py`.
  - Steps that read another's output go into one chain, in one turn: `heavy.py --expect <their sum> "what" --
    python -I chain.py`. When every step is a count or a build, add `--shared <the largest step's GB>,<its cores>`.
  - A timing that reads shared steps' output is queued after them, on its own: a job alone waits for every job
    queued before it.
  - A shared step that reads a job alone's output stays in that job's chain. A shared job may start before a job
    alone queued ahead of it (`HeavyJob.BACKFILL`), and would read the output before it is written.
- Each job prints whom it waits for, and sizes its pages and builds by the memory free when its turn comes
  (`tools/sysinfo.py`). `TRAM_HEAVY_NOWAIT=1` runs one beside the others (it slows both).
- A job in its own turn watches itself (#815; on 2026-11-22 a trace expected to take 5 min ran 100 min and held
  17 GB against the 6 it declared, and the job behind it waited 26 min). Once a minute it reads its process tree
  (`HeavyJob.verdict` has the rules): past 2× its expected time it warns, and it will end past 4× and 30 min over
  it once a week of history has calibrated the rule (`HeavyJob.TIME_ENDS`; `heavy.py --history` shows each
  kind's spread); over its share's memory it warns at 1.25× and ends at 2×, or at 1× with under 4 GB free on the
  machine (a job alone: under 4 GB free), seen at two looks in a row; with its processes under 2 s of CPU in
  10 min, or the process that started it gone, it ends. A warning goes on its ticket, which the board and a
  waiting job's line show (`…, running 100 min, expected 5 (shared: 6 GB, 4 cores): LATE ×20; 17 of 6 GB`), and
  once into the job's output. Ending stops everything the job started (on Windows a Job Object: a stopped
  `heavy.py` stops its command too), exits 86 and prints one line: what, how long, how much against what. The
  board lists the jobs a watch ended in the last hour. The expected time is `heavy.py --expect`, what
  `headless.py` plans from its runs' times, or the median of the same kind's last full runs (a command's script
  and its option names) in `history.jsonl` beside the tickets. `--no-limit` (`TRAM_HEAVY_NOLIMIT=1`) keeps the
  warnings and ends nothing. A job waiting behind one that watches itself gives it 20 min before calling it stuck.
  The board and the overview add each job's estimated start and finish (`baseline_store.schedule`, #826): the
  ticket's expected time, else its kind's median in the history (one full run is enough there), the jobs started in
  queue order as their turns allow (alone after everything, shared while cores and GB fit, or before as above).
- A stopped background task can leave its job running: when the command ended in a Git Bash program (`bash
  chain.sh`), bash handed its process over to it, and the stop kills a pid that is gone (measured 2026-11-22: the
  chain's shells and its python ran on, their parents unchanged; with the outer shell alive the stop ends the
  whole tree). `python -I tools/heavy.py --stop PID` asks such a job to end with what it started; a job of
  another checkout only with `--force`.

**Stacked work:** an issue that needs another branch's unmerged work branches from it and opens its PR with
`--base` on that branch. Before the base's PR merges, move the stacked PR onto main (`gh pr edit N --base main`):
deleting the base's branch closes a PR still based on it, and a closed PR cannot change its base (#745, reopened
by putting the branch back for a moment). Once the base squash-merges, merge main into the stacked branch (no
force-push); a conflict in code only the base changed takes the stacked branch's side. Then rerun its checks and
merge (#578 on #575).

**Merging** (`python -I tools/session.py merge N`, on the user's word): one open PR of the issue's branch, none
standing on it, mergeable, its checks passed, the worktree's changed and untracked files looked at; then the squash
as `<PR title> (#PR)`, the worktree, the local and the remote branch removed and the agent's label taken off. gh's
own `--delete-branch` removes the worktree folder with its untracked files at once (gh 2.103.3, seen at #751 and
#752: each folder was gone right after its merge). An issue split over two branches (#228's two PRs) is merged one
branch at a time with `--branch N-...`; without it the merge refuses, and the label stays until the last one goes (#891).

**Unattended runs:** an investigation script is committed only when it runs like the other tools: its own server
on a free port (as `headless.py`), no fixed agent port, a usage line at the top. Without issues allowed, findings
go into a "Findings" section of the PR.

**Facts in `data/truth.json`:**
- A new section names its reader in the file's `readers`, or says it is reference only (#224).
- No check exemptions, agent audits or lists of generated array indexes: #177's allowlist would have failed every
  line on the next rebuild. What a check can decide from geometry stays a rule in the check, counted per class
  with its places, so `--compare` shows what a rebuild moved.
- A fact that overrides a source records what the source said, and the tool applying it states whether it is
  still needed (DATA.md, Facts over a source; #670).
- Built files carry their `provenance` from `tools/sources.py` (a layer's fallback order, date, credits).

**Review findings files** (`reports/review/`, above):
- Offer only answers an importer turns into evidence, and say on the card why another answer stays held (#162,
  #176).
- The file names its `issue` and `line` (or `lines`): the review directory (`reviews.html`, #288) lists it under
  them, and lists the sets of closed issues apart.
- A set whose issue is closed while findings wait is deleted (maintainer, 2026-11-05), unless a build reads it
  (`tools/review_sets.py` `READ_BY`: deleting one broke the build, #416).

**Page checks and tests:**
- In a page: `tools/lint.js` on a page loaded with `?keepgeo` (`lint()`; `lint({ traffic: true })` averages seeds
  22, 7, 1234); benches in `tools/bench/` (u3, redruns, walkers; `batch.html`).
- Run long browser jobs unawaited and poll: script calls time out at 45 s. A background window throttles frames,
  so no fps readings from one.
- A test that drives a page limits the whole test (`faulthandler.dump_traceback_later`, as `tools/test_review.py`):
  Playwright's `page.evaluate` has no limit, and a promise that never resolves hangs the run without output.
- A test that needs `data/` or `raw/` skips without them, saying what to fetch.

**Dev switches:** `?line=N`, `?inspect`, `?review` (findings on the map), `?bot`, `?keepgeo`, `?notunnels`,
`?boxpeople` (the box figures instead of the pedestrian models, #251), `?boxcars` (the box cars instead of the street vehicles' models, #250), `?profile=<name>` (a trial height profile
from `reports/review/profiles/`, to drive and compare, #358), `?seed=N&at=S` (the traffic check's run of seed N,
replayed up to route s and handed over paused: a stuck scene as it was, #157).

**Where some rules came from:**

| rule | from |
|---|---|
| `Closes #N` only with every point met | #146 was nearly closed with six places still awaiting the maintainer's answers |
| calibrate a check before it holds data | #119's survey check held 4.6 km of line 17's open track: it was calibrated on street track only |
| don't reformat what you don't change | #119's reflow buried its changes |
| no seeded checks on a world change | they measure traffic reshuffled by the new data (#156); the static world is built up first, the traffic checks come where they make sense (maintainer, 2026-11-05) |
| the world first, a lane may pause | the simulation lane paused after its open PRs (maintainer, 2026-11-05), waited for checkpoint W2 and resumed there (#414) |
| heavy jobs take turns | a comparison measured beside another heavy job is spoilt (#516) |
| count runs and builds share the machine | when memory allows, timings staying alone (#728). A night's sessions waited in one line: 33 min behind another job's count run (PR #461) |
| one rebuild at a time | two branches publishing rebuilt data overwrite each other's lines (#280) |
| findings off the path go on a lane's list | issues opened faster than closed: 410 against 251 in 26 days (#731) |
| a finding's own issue only for the next step or a failing check, after a search; one issue for a place's or a batch's reports | 202 open on 2026-11-21, 120-129 opened a week against 41-87 closed; a session opened #797 and #800 in a day and reported a build race on #735 that #701 already held (maintainer, 2026-11-21) |
| merges in batches, the heaviest work at night | the other lanes' sessions were stopped to save machine time and the maintainer's attention, and resumed on this rule (maintainer, 2026-11-21); night from 22:00 to 07:00, from 23:00 since 2026-11-23, plus any time the maintainer says go |
| a ground rule's issue closes at the rule's merge | it stayed open as "Part of" until the batch's rebuild, 5-10 issues between batches, while #757 tracks the batch (maintainer, 2026-11-21) |
| a ground change runs the locality set and its rules' places, `--all --rings` the batch | #812's proof, 61 places with one ring and two, took 2 h 10 min of the queue a round and ran six times as main's merges brought rules and places; the places to check kept growing (#865) |
| a security hole is not written up in public | the repository is public and the alpha is live (maintainer, 2026-11-19) |

## How the game's parts work

What the player's guide ([README.md](README.md), [README.en.md](README.en.md)) leaves out:

- **The right mirror** grows with the window (a quarter of its height, 110–420 px) and keeps its
  aspect, so its field of view stays the same; its picture is drawn at the frame's size in device
  pixels. The texture updates at most 30 times a second, with a 300 m horizon. Flat covers/grates are
  omitted; people, vehicles, poles, overhead wires and the tram remain. Its cached picture is
  composited after every main redraw, including while paused.
- **The T3's TR 37 equipment** (#221, #351): `src/tr37.js`, with the wire and the motor-generator in `src/electric.js`;
  sources and derivation in `docs/research/prazsketramvaje/t3-accelerator.md` (§ 9 the electric system). Acceleration by step:
  `tools/test_traction.py`; the situations (coasting, take-up, a weak wire …): `tools/test_electric.py`; how the autopilot
  drives it on made-up lines (gradients, loads, signals, a tram or a car ahead, contacts, time limits): `tools/test_drives.py`; on the real
  lines, the stops and the timetable: `tools/headless.py --checks stops`. The substations: `tools/substations.py --write` into `data/truth.json`.
- **On-screen controls** (#79): `src/touch.js`.
- **Stops and lines:** stop posts come from GTFS `route_stops`, stops and departures from GTFS, platforms
  from OSM. The tram ahead's line is one that serves that stop in GTFS.
- **Speeds:** the posted speed is that of the OSM tram way (`tools/osm_speeds.py`, the data OpenRailwayMap shows).
- **Traffic:** cars drive a lane graph (smooth lanes, turning curves through junctions) and pitch and roll with the road surface. Zebra crossings come from OSM.
- **Idle pages** draw 4 frames a second (#149): the menu, a pause, the results, review mode with its
  camera at rest. Driving and inspect mode draw every frame; a hidden tab draws nothing.
- **Interlaced track in Letenská:** detected automatically from the two OSM route relations.
- **Radio/IRC switching** remains in the code for switches the data marks as such; none are marked now.
- **Ground:** the page loads it prebuilt (`data/lineN.ground.*`, `tools/ground_mesh.py`, #509): the survey, the track
  beds, the building plots, the water and the terrain welded into one mesh that meets the tracks; the page draws the
  beds the file does not hold (on structures) and the decks, and builds no ground of its own (#510). The file is 500 m
  tiles on the S-JTSK grid, each decoded on its own in a pool of workers (`src/groundFile.js`, #30): every tile's height
  lookup at load, then only those within the fog's end of the camera and of 1 km of route ahead, drawn in detail (9-17
  MB of lookups held, 48-120 MB before #658). `?keepgeo` and `?bot` keep every tile's lookup and meshes. `tools/bench/ground_tiles.py` drives the window along a line:
  what is held, each tile's time, any tile missing in view. The build's report (`reports/ground-mesh/`) holds the
  mesh's error against IPR's raster only where `tools/ground_mesh.py --error` asked for it (0.6-8 minutes a line,
  #704): a checkpoint's run, or a change of the terrain's thinning.
- **The network** (the traffic's roads, lanes, footways and doors, the signals bound to the lanes, what the platforms and
  stops read of the survey) is built once, after `tools/ground_mesh.py`, by `tools/network.py` into
  `data/lineN.network.json` ([the network layer's note](docs/decisions/2026-11-18-network-layer.md), #658), a step of
  `rebuild.py` of its own after the ground's (#702): a change to a traffic rule runs it alone. Start
  builds none of it and reads no lookup past the window: what it places stands on the heights the build read from the
  ground file as the page reads it (`tools/ground_at.py`, held to the page's reads by `tools/test_ground_at.py --browser`,
  #682): the bridges' and road tunnels' ends, the signal heads, the platforms. Our stops' signs and shelters settle once
  their tile's lookup comes (`ground.later`). The road tunnels' mouths are in the ground file (`tools/ground_mesh.py`
  fit_mouths). A change to a traffic rule is a change to `tools/network.py` and a rebuild of the file. The page's
  rules were ported whole: before they went, its network and the build's were the same to the cm on lines 9, 17, 22, 23
  and 37 (#667, #668). `tools/test_network_layer.py` holds Start to it; `tools/bench/network_layer.py` times Start and
  counts its reads.
- **Buildings:** the type is read from the OSM tag under each LOD2 building, its roof shape and size;
  Mosty 3D sets the deck height on tagged bridges.
- **Outdoor temperature:** Prague now comes from Open-Meteo, hourly.
- **Tram models:** `assets/t3h/LICENSE.txt`, `assets/t3/LICENSE.txt`, the second car's coupling #248;
  `ASSETS.md` lists them. How a model plugs into the game, the tiers of movement, and adding or changing one:
  [docs/vehicles.md](docs/vehicles.md) (in Czech [docs/vehicles.cs.md](docs/vehicles.cs.md)).
- **The autopilot** drives like the headless test bot: the same driver lives in `src/autopilot.js` and is
  used by `tools/autopilot.js`.
- **Language:** strings live in `src/i18n.js`. The player's guide is `README.md` in Czech and `README.en.md`
  in English, one source for the repository and for Help in the game's menu (`src/help.js` shows what stands
  between `<!-- help -->` and `<!-- /help -->`, and renders only the Markdown those files use). A change to one
  changes the other; `tools/test_readme.py` checks that their headings match.
