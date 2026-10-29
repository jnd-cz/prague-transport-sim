# Rules for every agent and session (Claude, ChatGPT / Codex, others)

A Tatra T3 tram driving game in a 3D Prague built from real data. Plain ES modules + Three.js, no build
step; Python tools build the world from pinned source snapshots. Read before working:
[README.md](README.md) (run, build, play), [DATA.md](DATA.md) (snapshots, data store),
[ROADMAP.md](ROADMAP.md) (milestones), [docs/knowledge.md](docs/knowledge.md) (what we learned: data
quirks, conventions, why the main heuristics exist), [docs/architecture.md](docs/architecture.md) (the
target design) and [docs/decisions/](docs/decisions/).

## Work

- **Tasks live in GitHub issues** (`jnd-cz/prague-transport-sim`), grouped by milestone. Docs link to
  issues instead of listing tasks. New findings that are not fixed now become an issue.
- One branch per issue (`<number>-<short-name>`), PR into `main`, the PR says which checks were run and
  their numbers. Small doc or data-fact changes may go straight to `main`.
- Commits: what changed and why, with numbers where something was measured. Author email in this repo:
  `2506000+jnd-cz@users.noreply.github.com` (`git config user.email …` per clone).
- **Fix rules, not spots.** Measure an issue on every line (lints, benches, `data/truth.json`), change
  the rule that produced it, measure again on all lines. A local special case needs a fact in
  `data/truth.json`, not a coordinate in code.
- **Realism over convenience.** Keep the driver's real skills (contacts, coasting, signals) instead of
  automating them. Facts from the user (a Prague tram expert) win over heuristics.
- Heuristics standing in for missing data log what they decided (debug overlay F8, `window.game`) so they
  can be reviewed.

## Data

- **Never edit generated data by hand** (`data/line*.json` and sidecars): change the tool and rebuild.
  Hand-made facts go to `data/truth.json`.
- Sources come only from the pinned snapshot in `raw/` (`python -I tools/snapshot.py fetch`); OSM only
  from its local extract (`raw/osm/praha.osm.pbf`). **The public Overpass API is not used.**
- One coordinate conversion for every tool: `tools/geo.py`.
- New source files go into a snapshot (`tools/snapshot.py publish`), with source URL, licence and date.

## Running and checking

- Dev server: `python tools/serve.py 8742` (no-cache headers; `POST /report/<name>.json` saves to
  `reports/`). Port 8740 may belong to another session: never use or stop it.
- Python: `python -I` for stdlib-only tools; `python -P -E` for tools needing the user site packages
  (pyosmium, pyproj, shapely, numpy, Pillow). Write multi-line scripts to a file and run it; shell
  heredocs with quotes break on this machine.
- Checks from the command line: `python -P -E tools/headless.py --lines 17 --checks u3,redruns,traffic,lint
  --seeds 1-3` (headless Chromium, its own server; exit code 1 on a failed threshold).
- Checks in a page: `tools/lint.js` on a page loaded with `?keepgeo` (`lint()`, `lint({ traffic: true })` averages
  seeds 22, 7, 1234), `python tools/lint_report.py` against `reports/baseline/`; benches in `tools/bench/`
  (u3, redruns, walkers; `batch.html`). Run long browser jobs unawaited and poll (script calls time out
  at 45 s); a background window throttles frames, so no fps readings then.
- Dev switches: `?line=N`, `?inspect`, `?bot`, `?keepgeo`, `?nofine`, `?nospread`, `?notunnels`.

## Code style

- Match the surrounding code: plain modules, short names in hot loops, comments that say why (the data
  quirk, the measured case), not what. Units are metres, seconds, m/s unless named otherwise.
- No new dependencies or build steps without an issue that decides it. Tests and benches: Python +
  Playwright (headless Chromium); Node / Deno only once the simulation core is split out.
- Randomness must be reproducible: today the benches override `Math.random` with a seeded one; new
  simulation code takes its randomness from one place so a seeded RNG per run can replace it.
